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
