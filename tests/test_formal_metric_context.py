"""Authenticated complete-universe industry prerequisites; no metric arithmetic."""

import copy
import hashlib
import importlib
import importlib.util
import json
import sys
import subprocess
import unittest
from unittest.mock import patch

from tests.formal_metric_fixtures import FREEZE, IDS, MetricFixture, update_mapping_digest


class FormalMetricContextTests(unittest.TestCase):
    def fixture(self, **kwargs):
        fixture = MetricFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_metric_context"),
            "authenticated metric context repository is required")
        return importlib.import_module("ashare_pipeline.formal_metric_context")

    def repo(self, f):
        return self.api().FormalMetricContextRepository(f.store, f.context, registry_signature_verifier=f.verifier)

    def test_verified_universe_getter_preserves_original_cn_bytes_and_header(self):
        f = self.fixture()
        before = f.store.get_formal_universe_snapshot_by_input_hash(f.frozen.frozen_input_hash)
        self.assertTrue(callable(getattr(f.store, "get_verified_formal_frozen_universe", None)), "verified universe getter is required")
        frozen = f.store.get_verified_formal_frozen_universe(f.frozen.frozen_input_hash)
        self.assertEqual(frozen.as_of_utc, "2026-08-31T15:00:00+08:00")
        self.assertEqual(frozen.frozen_input_hash, f.frozen.frozen_input_hash)
        self.assertEqual(tuple(m.security_id for m in frozen.members), IDS)
        self.assertEqual(f.store.get_formal_universe_snapshot_by_input_hash(f.frozen.frozen_input_hash), before)
        self.assertIsNone(f.store.get_verified_formal_frozen_universe("0" * 64))

    def test_complete_signed_industries_preserve_all_exchanges_and_late_capture(self):
        f = self.fixture()
        facts = {sid: f.put_industry(sid)[0] for sid in IDS}
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        batch = repo.resolve_industries(universe)
        self.assertEqual(universe.security_ids, IDS)
        self.assertEqual(universe.as_of_utc, FREEZE)
        self.assertEqual(universe.frozen_as_of_utc, "2026-08-31T15:00:00+08:00")
        self.assertEqual(tuple(batch.entries), IDS)
        for sid in IDS:
            entry = batch.entries[sid]
            self.assertEqual(entry["status"], "assigned")
            self.assertEqual(entry["context_fact_id"], facts[sid].id)
            self.assertEqual(entry["context_canonical_sha256"], hashlib.sha256(facts[sid].canonical_bytes()).hexdigest())
            self.assertEqual(entry["universe_hash"], universe.universe_hash)
        self.assertEqual(batch.entries["SH600000"]["template_id"], "bank")
        self.assertEqual(batch.entries["BJ430001"]["secondary_industry"], "machinery")
        self.assertIsNone(repo.recheck_batch(universe, batch))

    def test_pending_distinguishes_missing_mapping_context_and_authentic_mismatch(self):
        def mutate(docs):
            docs["industry"]["memberships"] = docs["industry"]["memberships"][1:]
            update_mapping_digest(docs["industry"])
        f = self.fixture(mutate=mutate)
        f.put_industry("SZ000001", changes={"secondary_industry": "different"})
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        batch = repo.resolve_industries(universe)
        self.assertEqual([batch.entries[s]["pending_reason"] for s in IDS],
            ["signed_membership_absent", "context_absent", "context_membership_mismatch"])
        self.assertTrue(all(batch.entries[s]["status"] == "pending" for s in IDS))
        self.assertIsNone(repo.recheck_batch(universe, batch))

    def test_invalid_signed_industry_is_fatal(self):
        mutations = (
            lambda d: d.update(mapping_sha256="0" * 64),
            lambda d: d.update(schema_version="formal-industry-registry-v2"),
            lambda d: d.update(purpose="test"),
            lambda d: d.update(effective_date="2026-09-01"),
            lambda d: d.update(extra=True),
            lambda d: d["memberships"][0].update(template_id="unknown"),
            lambda d: d["memberships"].reverse(),
            lambda d: d["memberships"].append(dict(d["memberships"][0])),
            lambda d: d["memberships"][0].update(extra=True),
            lambda d: d.update(source_version=" "),
            lambda d: d["memberships"][0].update(security_id="bj430001"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                f = self.fixture(mutate=lambda docs: mutate(docs["industry"]))
                repo = self.repo(f)
                with self.assertRaises(ValueError):
                    repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)

    def test_universe_missing_source_member_status_receipt_or_raw_is_fatal(self):
        mutations = (
            lambda f: f.sql("DELETE FROM formal_universe_source WHERE exchange='BJ'"),
            lambda f: f.sql("DELETE FROM formal_universe_member WHERE security_id='SH600000'"),
            lambda f: f.sql("DELETE FROM formal_universe_status WHERE security_id='SZ000001'"),
            lambda f: f.sql("DELETE FROM formal_task_snapshot_receipt WHERE task_id=?", (f.task_ids["BJ"],)),
            lambda f: (__import__("pathlib").Path(f.frozen.sources[0].snapshot.content_path)).unlink(),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                f = self.fixture()
                repo = self.repo(f)
                mutate(f)
                with self.assertRaises((ValueError, OSError)):
                    repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)

    def test_extra_signed_member_cannot_join_the_frozen_population(self):
        def mutate(docs):
            docs["industry"]["memberships"].append(dict(security_id="SZ000002", template_id="bank",
                primary_industry="banks", secondary_industry="joint-stock-banks"))
            update_mapping_digest(docs["industry"])
        f = self.fixture(mutate=mutate)
        f.put_industry("SZ000002")
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        self.assertEqual(tuple(repo.resolve_industries(universe).entries), IDS)

    def test_final_recheck_detects_earlier_member_correction_and_absence_change(self):
        f = self.fixture()
        f.put_industry("BJ430001")
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        batch = repo.resolve_industries(universe)
        # Represents a correction to A after A's inputs were read, while later
        # members' feature work happens outside this Context prerequisite slice.
        f.put_industry("BJ430001", generation="correction", published="2026-08-29T07:00:00+00:00")
        with self.assertRaises(ValueError):
            repo.recheck_batch(universe, batch)
        current = repo.resolve_industries(universe)
        f.put_industry("SH600000")
        with self.assertRaises(ValueError):
            repo.recheck_batch(universe, current)

    def test_foreign_forged_copied_and_mutated_capabilities_fail(self):
        f = self.fixture()
        repo = self.repo(f)
        api = self.api()
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        batch = repo.resolve_industries(universe)
        for cls in (api.VerifiedMetricUniverse, api.VerifiedMetricIndustryBatch):
            with self.assertRaises((ValueError, TypeError)):
                cls()
        for proof in (universe, batch):
            for copier in (copy.copy, copy.deepcopy):
                with self.assertRaises((ValueError, TypeError)):
                    copier(proof)
            with self.assertRaises((ValueError, TypeError, AttributeError)):
                object.__setattr__(proof, "universe_hash", "0" * 64)
        with self.assertRaises(ValueError):
            repo.resolve_industries(object.__new__(api.VerifiedMetricUniverse))
        with self.assertRaises(ValueError):
            self.repo(f).resolve_industries(universe)
        wire = batch.to_dict()
        wire["entries"]["BJ430001"]["status"] = "assigned"
        self.assertEqual(batch.entries["BJ430001"]["status"], "pending")
        with self.assertRaises(TypeError):
            batch.entries["BJ430001"]["status"] = "assigned"
        with self.assertRaises(ValueError):
            object.__new__(api.FormalMetricContextRepository).resolve_industries(universe)

    def test_changed_real_read_dependencies_cannot_mint_or_recheck(self):
        f = self.fixture()
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        batch = repo.resolve_industries(universe)
        for owner, method, replacement in (
            (f.store, "get_verified_formal_frozen_universe", lambda _: f.frozen),
            (f.context, "get_verified_many", lambda *args: {s: None for s in IDS}),
            (f.snapshots, "read_verified_raw", lambda *args, **kwargs: b"cached"),
            (f.raw, "read_verified_raw", lambda *args, **kwargs: b"cached"),
            (f.raw, "validate_stored_snapshot", lambda *args, **kwargs: None),
        ):
            with self.subTest(method=method), patch.object(owner, method, replacement), self.assertRaises(ValueError):
                repo.recheck_batch(universe, batch)

    def test_context_corruption_propagates_even_without_signed_membership(self):
        def mutate(docs):
            docs["industry"]["memberships"] = docs["industry"]["memberships"][1:]
            update_mapping_digest(docs["industry"])
        f = self.fixture(mutate=mutate)
        _, ref = f.put_industry("BJ430001")
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        f.sql("DELETE FROM formal_task_snapshot_receipt WHERE task_id=?", (ref.producing_task_id,))
        with self.assertRaises(ValueError):
            repo.resolve_industries(universe)

    def test_copied_context_repository_cannot_supply_provenance(self):
        f = self.fixture()
        api = self.api()
        copied = copy.copy(f.context)
        with self.assertRaises(ValueError):
            api.FormalMetricContextRepository(f.store, copied, registry_signature_verifier=f.verifier)

    def test_combined_copied_stores_cannot_mint_a_universe(self):
        from ashare_pipeline.formal_context_repository import FormalContextRepository
        f = self.fixture()
        api = self.api()
        store, snapshots, raw = copy.copy(f.store), copy.copy(f.snapshots), copy.copy(f.raw)
        store._formal_snapshot_store = raw
        snapshots._state_store, snapshots._raw_store = store, raw
        context = FormalContextRepository(store, snapshots, f.verifier)
        with self.assertRaises(ValueError):
            repository = api.FormalMetricContextRepository(store, context, registry_signature_verifier=f.verifier)
            repository.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)

    def test_individual_copied_or_fabricated_dependencies_cannot_mint(self):
        from ashare_pipeline.formal_context_repository import FormalContextRepository
        from ashare_pipeline.formal_snapshot_repository import FormalSnapshotRepository
        from ashare_pipeline.state_store import StateStore
        f = self.fixture()
        api = self.api()
        def fabricated(original):
            item = object.__new__(type(original))
            item.__dict__.update(original.__dict__)
            return item
        for clone in (copy.copy, fabricated):
            for dependency in ("store", "snapshots", "raw"):
                with self.subTest(clone=clone.__name__, dependency=dependency):
                    if dependency == "store":
                        store = clone(f.store)
                        snapshots = FormalSnapshotRepository(f.raw.root, store)
                    elif dependency == "snapshots":
                        store, snapshots = f.store, clone(f.snapshots)
                    else:
                        raw = clone(f.raw)
                        store = StateStore(f.db_path, formal_snapshot_store=raw, registry_signature_verifier=f.verifier)
                        snapshots = FormalSnapshotRepository(raw.root, store)
                    context = FormalContextRepository(store, snapshots, f.verifier)
                    with self.assertRaises(ValueError):
                        repository = api.FormalMetricContextRepository(store, context, registry_signature_verifier=f.verifier)
                        repository.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)

    def test_genuine_dependencies_constructed_before_metric_import_are_accepted(self):
        program = '''
import sys
from tests.formal_metric_fixtures import MetricFixture, IDS
assert "ashare_pipeline.formal_metric_context" not in sys.modules
fixture = MetricFixture()
try:
    from ashare_pipeline.formal_metric_context import FormalMetricContextRepository
    repository = FormalMetricContextRepository(fixture.store, fixture.context, registry_signature_verifier=fixture.verifier)
    proof = repository.load_universe(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
    assert proof.security_ids == IDS
    repository.recheck_batch(proof, repository.resolve_industries(proof))
finally:
    fixture.close()
'''
        result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legitimate_dependency_reinitialization_preserves_metric_reads(self):
        f = self.fixture()
        # Legitimate explicit constructor invocation remains legal for legacy
        # callers; copied fields without such construction remain insufficient.
        type(f.raw).__init__(f.raw, f.raw.root)
        type(f.store).__init__(f.store, f.db_path, formal_snapshot_store=f.raw, registry_signature_verifier=f.verifier)
        type(f.snapshots).__init__(f.snapshots, f.raw.root, f.store)
        repository = self.repo(f)
        proof = repository.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        self.assertEqual(proof.security_ids, IDS)
        self.assertIsNone(repository.recheck_batch(proof, repository.resolve_industries(proof)))

    def test_every_context_metadata_mismatch_is_explicit_pending(self):
        f = self.fixture()
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        for index, (field, value) in enumerate((
            ("primary_industry", "other"), ("source_version", "different-v2"),
            ("effective_date", "2026-08-27"), ("mapping_sha256", "0" * 64))):
            f.put_industry("BJ430001", changes={field: value}, generation=f"metadata-{index}",
                published=f"2026-08-{20 + index:02d}T07:00:00+00:00")
            batch = repo.resolve_industries(universe)
            self.assertEqual(batch.entries["BJ430001"]["pending_reason"], "context_membership_mismatch")

    def test_signed_industry_digest_uses_canonical_bytes_and_full_membership(self):
        f = self.fixture()
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        wire = universe.to_dict()
        mapping = {k: wire["industry"][k] for k in ("classification_system", "source_version", "effective_date", "memberships")}
        expected = json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(universe.mapping_sha256, hashlib.sha256(expected).hexdigest())
        self.assertEqual(universe.population_hash, hashlib.sha256(b'["BJ430001","SH600000","SZ000001"]').hexdigest())
        self.assertEqual(universe.canonical_bytes(), json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    def test_full_universe_includes_multiple_members_of_one_exchange(self):
        rows = {exchange: [dict(security_id=sid, security_type="ordinary_a", listing_status="listed")]
            for exchange, sid in zip(("BJ", "SH", "SZ"), IDS)}
        rows["SH"].append(dict(security_id="SH600001", security_type="ordinary_a", listing_status="listed"))
        f = self.fixture(exchange_rows=rows)
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        self.assertEqual(universe.security_ids, ("BJ430001", "SH600000", "SH600001", "SZ000001"))
        batch = repo.resolve_industries(universe)
        self.assertEqual(batch.entries["SH600001"]["pending_reason"], "signed_membership_absent")

    def test_global_signature_or_scoring_root_failure_is_fatal(self):
        f = self.fixture()
        repo = self.repo(f)
        other = self.fixture(mutate=lambda docs: docs["industry"].update(source_version="other"))
        with self.assertRaises(ValueError):
            repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=other.scoring)
        with self.assertRaises(ValueError):
            repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=copy.copy(f.scoring))
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        batch = repo.resolve_industries(universe)
        f.sql("UPDATE formal_registry_blob SET signature='invalid' WHERE registry_hash=?", (f.bundle.manifest.industry_registry_hash,))
        with self.assertRaises(ValueError):
            repo.recheck_batch(universe, batch)

    def test_final_recheck_uses_one_universe_graph_and_one_batch(self):
        f = self.fixture()
        for sid in IDS:
            f.put_industry(sid)
        repo = self.repo(f)
        universe = repo.load_universe(f.frozen.frozen_input_hash, scoring_registry=f.scoring)
        batch = repo.resolve_industries(universe)
        # Observe actual Python calls without replacing any trusted read path.
        codes = {f.store.get_verified_formal_frozen_universe.__func__.__code__: "universe",
            f.context.get_verified_many.__func__.__code__: "batch",
            f.store.list_formal_context_facts.__func__.__code__: "scope"}
        counts = dict(universe=0, batch=0, scope=0)
        def profile(frame, event, arg):
            if event == "call" and frame.f_code in codes:
                counts[codes[frame.f_code]] += 1
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            repo.recheck_batch(universe, batch)
        finally:
            sys.setprofile(previous)
        self.assertEqual(counts, dict(universe=1, batch=1, scope=2))
