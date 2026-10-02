"""Atomic Stage D persistence contracts, using genuine producer proofs."""

import atexit
import copy
import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from decimal import Decimal
from unittest.mock import patch

from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor
from ashare_pipeline.formal_final_eligibility import build_formal_eligibility_batch
from ashare_pipeline.formal_final_scoring import build_final_score_card_batch
from ashare_pipeline.formal_pool import select_formal_pools
from tests.formal_final_scoring_fixtures import FinalScoringFixture
from tests.test_formal_final_scoring import d1_batch
from tests.test_formal_coverage_manifest import good
from tests.test_formal_final_migration import TABLES


_SHARED = None


class FormalFinalRecoveryBoundaryTests(unittest.TestCase):
    """Short storage tests use canonical DTOs, never counterfeit live proofs."""

    def setUp(self):
        import ashare_pipeline.formal_final_repository as repository
        from ashare_pipeline.state_store import _V8_TABLE_DDL
        self.module = repository
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        # Recovery does not mint proofs or depend on the frozen-root FK target.
        for ddl in _V8_TABLE_DDL.values():
            self.connection.execute(ddl)
        seal = lambda row, key: dict(row, **{key: repository._serialize_payload(row)[1]})
        sid = "SH600000"
        common = dict(registry_manifest_hash="root", frozen_input_hash="frozen",
            universe_hash="universe", as_of_utc="2026-08-31T07:00:00+00:00")
        entry = seal(dict(schema_version="policy-adjusted-score-input-v1", security_id=sid,
            secondary_industry="industry", status="ready", **common), "entry_hash")
        inputs = seal(dict(schema_version="policy-adjusted-score-input-batch-v1",
            security_ids=[sid], inputs=[entry], **common), "batch_hash")
        card = seal(dict(schema_version="formal-final-score-card-v1", security_id=sid,
            source_entry_hash=entry["entry_hash"], source_batch_hash=inputs["batch_hash"],
            secondary_industry="industry", S0="80", Sc="80.12345678901234567890123456789",
            Sbase="80", B="80", R_safety="80", confidence={"C": "0.9"}, Sc_grade="A"), "card_hash")
        scores = seal(dict(schema_version="formal-final-score-card-batch-v1", security_ids=[sid],
            cards=[card], pending={}, source_batch_hash=inputs["batch_hash"],
            batch_hash=inputs["batch_hash"], **common), "batch_hash")
        eligibility = seal(dict(schema_version="formal-eligibility-v1", security_id=sid,
            secondary_industry="industry", state="formal_scored", reason_codes=[],
            strong_qualified=True, wait_qualified=False, hard_veto=False,
            strong_prohibited=False, wait_prohibited=False, source_entry_hash=entry["entry_hash"],
            source_batch_hash=inputs["batch_hash"], score_batch_hash=scores["batch_hash"],
            card_hash=card["card_hash"], sort_fields=dict(Sc=card["Sc"], B="80", C="0.9",
                R_safety="80", V="75")), "eligibility_hash")
        eligible = seal(dict(schema_version="formal-eligibility-batch-v1", security_ids=[sid],
            eligibilities=[eligibility], source_batch_hash=inputs["batch_hash"],
            score_batch_hash=scores["batch_hash"]), "batch_hash")
        decisions = [seal(dict(schema_version="formal-pool-decision-v1", security_id=sid,
            pool=pool, decision="selected" if pool == "strong" else "not_qualified",
            eligibility_hash=eligibility["eligibility_hash"], source_batch_hash=eligible["batch_hash"]),
            "decision_hash") for pool in ("strong", "wait")]
        pools = seal(dict(schema_version="formal-pool-batch-v1", security_ids=[sid],
            source_batch_hash=eligible["batch_hash"], strong_security_ids=[sid], wait_security_ids=[],
            counts=dict(strong=1, wait=0), decisions=decisions), "batch_hash")
        coverage = dict(schema_version="formal-coverage-v1", blockers=[],
            authenticated_context=False, freeze_at_utc=common["as_of_utc"],
            rows=[dict(security_id=sid, exchange="SH", frozen_input_hash="frozen")])
        self.wires = inputs, scores, eligible, pools
        artifacts = {}
        for name, payload in zip(repository.ARTIFACT_KINDS, (coverage, *self.wires)):
            raw, digest = repository._serialize_payload(payload)
            artifacts[name] = dict(run_id="test", artifact_kind=name, payload_json=raw, artifact_hash=digest)
        header = dict(run_id="test", mode="test_preview", status="preview_ready", **common,
            coverage_manifest_hash=artifacts["coverage_manifest"]["artifact_hash"],
            code_version="test", contract_version="formal-final-v1", created_at="2026-10-02T00:00:00+00:00")
        header["input_manifest_hash"] = repository._serialize_payload(repository._input_identity(header, artifacts))[1]
        header["result_hash"] = repository._result_hash(header, artifacts)
        self.expected = {"formal_final_run": [header], "formal_final_artifact": list(artifacts.values()),
            **repository._project_rows("test", self.wires)}
        for name, rows in self.expected.items():
            repository._insert_rows(self.connection, name, rows, tuple(rows[0]))

    def read(self):
        return self.module.FormalFinalRunRepository._read_run(None, self.connection, "test")

    def test_populated_scorecard_and_selected_ordinals_round_trip_exactly(self):
        snapshot = self.read()
        self.assertEqual(snapshot.scorecards[0]["Sc"], self.wires[1]["cards"][0]["Sc"])
        row = self.connection.execute("SELECT Sc,typeof(Sc) FROM formal_final_scorecard").fetchone()
        self.assertEqual(tuple(row), (snapshot.scorecards[0]["Sc"], "text"))
        self.assertEqual(self.connection.execute("SELECT selected_ordinal FROM formal_final_pool_decision "
            "WHERE pool_name='strong'").fetchone()[0], 1)

    def test_recovery_rejects_deletion_from_every_child_table(self):
        for table in TABLES[2:]:
            with self.subTest(table=table):
                self.connection.execute("SAVEPOINT damage")
                self.connection.execute("DELETE FROM " + table)
                with self.assertRaises(ValueError):
                    self.read()
                self.connection.execute("ROLLBACK TO damage")

    def test_recovery_rejects_projection_payload_and_header_tampering(self):
        altered = dict(self.wires[1]["cards"][0], Sc="1")
        raw, digest = self.module._serialize_payload(altered)
        attacks = [
            ("UPDATE formal_final_scorecard SET Sc='1'", ()),
            ("UPDATE formal_final_pool_decision SET selected_ordinal=2 WHERE pool_name='strong'", ()),
            ("UPDATE formal_final_scorecard SET Sc='1',payload_json=?,payload_hash=?", (raw, digest)),
            ("UPDATE formal_final_run SET result_hash='wrong'", ()),
            ("UPDATE formal_final_run SET input_manifest_hash='wrong'", ()),
            ("UPDATE formal_final_run SET universe_hash='wrong'", ()),
        ]
        for sql, args in attacks:
            with self.subTest(sql=sql):
                self.connection.execute("SAVEPOINT damage")
                self.connection.execute(sql, args)
                with self.assertRaises(ValueError):
                    self.read()
                self.connection.execute("ROLLBACK TO damage")

    def test_qualified_canonical_decimal_boundary_preserves_exact_values(self):
        from ashare_pipeline.formal_pool import _detach_eligibility_rows, _select_detached_rows
        rows = _detach_eligibility_rows(self.wires[2]["eligibilities"])
        self.assertEqual(rows[0]["sort_fields"]["Sc"], Decimal(self.wires[1]["cards"][0]["Sc"]))
        self.assertEqual(_select_detached_rows(rows).strong_ids, ("SH600000",))
        for bad in ("NaN", "Infinity", " 80", "+80", 80.0):
            damaged = copy.deepcopy(self.wires[2]["eligibilities"])
            damaged[0]["sort_fields"]["Sc"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _detach_eligibility_rows(damaged)


def minimal_batches():
    global _SHARED
    if _SHARED is None:
        print("Task 9 minimal fixture: signed three-member root", flush=True)
        fixture = FinalScoringFixture(peer_count=3)
        atexit.register(fixture.close)
        for sid in fixture.templates:
            fixture.put_industry(sid)
        print("Task 9 minimal fixture: D1", flush=True)
        inputs = d1_batch(fixture)
        print("Task 9 minimal fixture: D2", flush=True)
        scores = build_final_score_card_batch(inputs)
        print("Task 9 minimal fixture: D3 and pools", flush=True)
        eligibility = build_formal_eligibility_batch(inputs, scores)
        pools = select_formal_pools(eligibility)
        requirements = [CoverageRequirement(fixture.frozen.frozen_input_hash,
            sid, "financial", "selector", "2025", sid[:2], ("CNY",))
            for sid in inputs.security_ids]
        coverage = FormalCoverageAuditor(repository_validators={
            "financial": lambda *_: True}).audit(requirements, [good(r) for r in requirements])
        _SHARED = fixture, dict(mode="test_preview", coverage_manifest=coverage,
            input_batch=inputs, score_batch=scores, eligibility_batch=eligibility, pool_batch=pools)
    return _SHARED


class FormalFinalRepositoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.batches = minimal_batches()

    def setUp(self):
        from ashare_pipeline.formal_final_repository import FormalFinalRunRepository
        self.repository = FormalFinalRunRepository(self.fixture.store, code_version="task9-test")

    def test_complete_run_persists_exact_universe_and_all_artifact_hashes(self):
        receipt = self.repository.commit_complete_run(**self.batches)
        snapshot = self.repository.get_run(receipt.run_id)
        self.assertEqual(snapshot.security_ids, ("BJ430001", "SH600000", "SZ000001"))
        expected = {"coverage_manifest", "score_input_batch", "scorecard_batch",
            "eligibility_batch", "pool_selection_batch"}
        self.assertEqual(set(snapshot.artifacts), expected)
        for name, raw in snapshot.artifacts.items():
            self.assertEqual(hashlib.sha256(raw).hexdigest(), snapshot.artifact_hashes[name])
        self.assertEqual(snapshot.result_hash, receipt.result_hash)
        self.assertEqual(len(snapshot.inputs), 3)
        self.assertEqual(len(snapshot.statuses), 3)
        self.assertEqual(len(snapshot.eligibilities), 3)
        self.assertEqual(len(snapshot.pool_decisions), 6)
        self.assertTrue(snapshot.dependencies)
        for proof in receipt.batches:
            proof.require_verified()
        self.assertIsNot(receipt.input_batch, self.batches["input_batch"])

    def test_decimals_round_trip_as_canonical_text_without_float(self):
        from ashare_pipeline.formal_final_repository import _serialize_payload
        exact = "0.1234567890123456789012345678901234567890123456789"
        raw, digest = _serialize_payload({"Sc": Decimal(exact)})
        self.assertEqual(raw, '{"Sc":"' + exact + '"}')
        self.assertEqual(digest, hashlib.sha256(raw.encode()).hexdigest())
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE TABLE sample(payload TEXT)")
            connection.execute("INSERT INTO sample VALUES (?)", (raw,))
            restored = json.loads(connection.execute("SELECT payload FROM sample").fetchone()[0])
        self.assertEqual(Decimal(restored["Sc"]), Decimal(exact))
        for invalid in (0.1, float("nan"), Decimal("Infinity")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                _serialize_payload({"Sc": invalid})

    def test_same_input_allows_two_append_only_replays_with_same_result_hash(self):
        first = self.repository.commit_complete_run(**self.batches)
        second = self.repository.commit_complete_run(**self.batches)
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(first.input_manifest_hash, second.input_manifest_hash)
        self.assertEqual(first.result_hash, second.result_hash)
        runs = self.repository.list_runs_by_input_manifest(first.input_manifest_hash)
        self.assertTrue({first.run_id, second.run_id} <= {r.run_id for r in runs})

    def test_historical_run_cannot_be_updated_or_rebound(self):
        receipt = self.repository.commit_complete_run(**self.batches)
        before = self.repository.get_run(receipt.run_id)
        with patch("ashare_pipeline.formal_final_repository._new_run_id", return_value=receipt.run_id):
            with self.assertRaises(sqlite3.IntegrityError):
                self.repository.commit_complete_run(**self.batches)
        self.assertEqual(self.repository.get_run(receipt.run_id), before)
        for prefix in ("put_", "replace_", "mark_ready", "update_", "delete_"):
            self.assertFalse(any(name.startswith(prefix) for name in dir(self.repository)))

    def test_cross_root_or_forged_batch_is_rejected_before_write(self):
        before = self.counts()
        for key in ("coverage_manifest", "input_batch", "score_batch", "eligibility_batch", "pool_batch"):
            source = self.batches[key]
            for fake in (source.to_dict(), object.__new__(type(source))):
                with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                    self.repository.commit_complete_run(**dict(self.batches, **{key: fake}))
        r = CoverageRequirement("different-frozen", "SH600000", "financial", "selector", "2025", "SH")
        other = FormalCoverageAuditor().audit([r])
        with self.assertRaises(ValueError):
            self.repository.commit_complete_run(**dict(self.batches, coverage_manifest=other))
        self.assertEqual(self.counts(), before)

    def test_recovery_dto_never_authenticates_as_live_proof(self):
        receipt = self.repository.commit_complete_run(**self.batches)
        snapshot = self.repository.get_run(receipt.run_id)
        self.assertFalse(hasattr(snapshot, "require_verified"))
        self.assertEqual(copy.deepcopy(snapshot.to_dict()), snapshot.to_dict())
        with self.assertRaises(TypeError):
            snapshot.artifacts["score_input_batch"] = b"{}"
        with self.assertRaises((TypeError, ValueError)):
            build_final_score_card_batch(snapshot)
        self.assertIsNone(self.repository.get_run("missing"))

    def test_blocked_run_is_complete_and_has_no_fabricated_pool(self):
        receipt = self.repository.commit_complete_run(**self.batches)
        snapshot = self.repository.get_run(receipt.run_id)
        self.assertEqual(snapshot.status, "blocked")
        self.assertEqual(snapshot.scorecards, ())
        self.assertEqual({row["state"] for row in snapshot.statuses}, {"pending_evidence"})
        self.assertEqual({row["decision"] for row in snapshot.pool_decisions}, {"not_qualified"})

    def test_official_mode_does_not_accept_preview_coverage(self):
        before = self.counts()
        with self.assertRaises(ValueError):
            self.repository.commit_complete_run(**dict(self.batches, mode="official_candidate"))
        for mode in ("preview", "validated", "published", None):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.repository.commit_complete_run(**dict(self.batches, mode=mode))
        self.assertEqual(self.counts(), before)

    def test_artifact_vocabulary_is_enforced_by_the_atomic_writer(self):
        import ashare_pipeline.formal_final_repository as module
        before = self.counts()
        wrong = ("coverage_manifest", "input_manifest", "scorecard_batch",
            "eligibility_batch", "pool_selection_batch")
        with patch.object(module, "ARTIFACT_KINDS", wrong), self.assertRaises(ValueError):
            self.repository.commit_complete_run(**self.batches)
        self.assertEqual(self.counts(), before)

    def counts(self):
        with closing(self.fixture.store._connect()) as connection:
            return tuple(connection.execute("SELECT COUNT(*) FROM " + name).fetchone()[0] for name in TABLES)
