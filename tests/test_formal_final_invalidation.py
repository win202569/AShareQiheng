"""Manifest differences are data; only the repository authenticates reuse inputs."""

import copy
import inspect
import json
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FunctionType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ashare_pipeline.formal_final_invalidation import FormalRebuildPlan, _derive_plan
from ashare_pipeline.formal_final_repository import FormalFinalRunRepository
from ashare_pipeline.state_store import StateStore


IDS = ("BJ430001", "SH600000", "SZ000001")
MID = "M.quality"
VMID = "V.normalized_earnings_yield"


def manifests():
    """Detached canonical producer vocabulary for the non-authoritative diff core."""
    common = dict(registry_manifest_hash="root", frozen_input_hash="frozen",
        universe_hash="universe", population_hash="population", as_of_utc="2026-08-31T07:00:00+00:00",
        scoring_registry_hash="scoring", policy_contract_hash="policy", valuation_adapter_registry_hash="adapter",
        base_batch_hash="base", policy_batch_hash="policy-batch", valuation_batch_hash="valuation")
    entries = []
    for sid in IDS:
        context = dict(scope="template_secondary_industry", peer_security_ids=list(IDS[:2] if sid != IDS[2] else IDS[2:]),
            metric_id=MID, definition_hash="definition", direction="higher", cohort_hash="cohort")
        entries.append(dict(common, security_id=sid, template_id="industrial",
            primary_industry="primary", secondary_industry="same" if sid != IDS[2] else "other",
            status="ready", reasons=[], entry_hash="entry-" + sid,
            policy_result=dict(dimension_caps={}, pool_prohibitions=[], states={}, normalization_basis=[],
                pending_requirements=[], evidence_state="complete", decisions=[], result_hash="result-" + sid),
            slots={MID: dict(metric_id=MID, value="50", evidence_refs=[{"content_sha256": "source-" + sid}],
                metric_score=dict(raw_value="10", percentile="50", average_rank="1", peer_context=context)),
                VMID: dict(metric_id=VMID, value="50", valuation_input=dict(adjusted_value="10", status="adjusted"),
                    valuation_context=dict(context, metric_id=VMID),
                    valuation_score=dict(adjusted_value="10", percentile="50", average_rank="1"))},
            confidence_cap=None, consensus_context={"content_sha256": "consensus-" + sid}))
    inputs = dict(common, security_ids=list(IDS), inputs=entries, batch_hash="inputs")
    coverage = dict(rows=[dict(security_id=sid, domain="financial", selector_hash="selector",
        period_or_window="2025", exchange=sid[:2], frozen_input_hash="frozen",
        coverage_class="verified_complete", content_sha256="coverage-" + sid) for sid in IDS])
    identity = dict(mode="test_preview", code_version="code", contract_version="formal-final-v1",
        registry_manifest_hash="root", frozen_input_hash="frozen", universe_hash="universe",
        as_of_utc=common["as_of_utc"], coverage_manifest_hash="coverage", score_input_batch_hash="input")
    return inputs, coverage, identity


def dependencies(inputs):
    """Task 9's persisted hash-path vocabulary, without live-proof authority."""
    result = []
    def walk(value, path, sid):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.endswith(("_hash", "_sha256")) and isinstance(child, str) and child:
                    result.append(dict(security_id=sid, source_kind=key, source_id=path + "." + key,
                        source_hash=child, effect_scope="global" if sid is None else "security",
                        dependent_key="run" if sid is None else sid))
                elif isinstance(child, (dict, list)):
                    walk(child, path + "." + key, sid)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + "." + str(index), sid)
    walk({k: v for k, v in inputs.items() if k != "inputs"}, "batch", None)
    for entry in inputs["inputs"]:
        walk(entry, "input." + entry["security_id"], entry["security_id"])
    return result


class FormalInvalidationScopeTests(unittest.TestCase):
    def setUp(self):
        self.old, self.coverage, self.identity = manifests()
        self.new = copy.deepcopy(self.old)
        self.new_coverage = copy.deepcopy(self.coverage)
        self.new_identity = dict(self.identity)

    def plan(self):
        return _derive_plan(prior_inputs=self.old, current_inputs=self.new,
            prior_coverage=self.coverage, current_coverage=self.new_coverage,
            prior_dependencies=dependencies(self.old), prior_identity=self.identity,
            current_identity=self.new_identity)

    def test_single_non_peer_evidence_change_rebuilds_one_security_and_rescans_pools(self):
        self.new["inputs"][0]["consensus_context"]["content_sha256"] = "correction"
        plan = self.plan()
        self.assertIsInstance(plan, FormalRebuildPlan)
        self.assertFalse(plan.full_rebuild)
        self.assertEqual(plan.direct_security_ids, IDS[:1])
        self.assertEqual(plan.expanded_security_ids, IDS[:1])
        self.assertEqual(plan.d1_rebuild_ids, IDS[:1])
        self.assertEqual(plan.d2_rebuild_ids, IDS[:1])
        self.assertEqual(plan.eligibility_rebuild_ids, IDS[:1])
        self.assertTrue(plan.rescan_pools)
        self.assertEqual(plan.effect_scopes, ("pool", "security"))

    def test_peer_or_v_change_expands_to_complete_cohort(self):
        for mid in (MID, VMID):
            with self.subTest(mid=mid):
                self.new = copy.deepcopy(self.old)
                slot = self.new["inputs"][0]["slots"][mid]
                if mid == MID:
                    slot["metric_score"]["raw_value"] = "11"
                else:
                    slot["valuation_input"]["adjusted_value"] = "11"
                plan = self.plan()
                self.assertFalse(plan.full_rebuild)
                self.assertEqual(plan.direct_security_ids, IDS[:1])
                self.assertEqual(plan.expanded_security_ids, IDS[:2])
                self.assertEqual(plan.d2_rebuild_ids, IDS[:2])
                self.assertTrue(plan.rescan_pools)
                self.assertTrue(plan.cohort_keys)
                self.assertIn("cohort", plan.effect_scopes)

    def test_policy_cap_prohibition_pending_and_normalization_have_distinct_effects(self):
        cases = (("dimension_caps", {"T": "55"}, IDS[:1], IDS[:1]),
            ("pool_prohibitions", ["strong"], IDS[:1], ()),
            ("pending_requirements", [{"code": "missing"}], IDS[:1], IDS[:1]),
            ("normalization_basis", [{"normalized_profit": "20"}], IDS[:2], IDS[:2]))
        for key, value, expanded, d2 in cases:
            with self.subTest(key=key):
                self.new = copy.deepcopy(self.old)
                self.new["inputs"][0]["policy_result"][key] = value
                plan = self.plan()
                self.assertFalse(plan.full_rebuild)
                self.assertEqual(plan.expanded_security_ids, expanded)
                self.assertEqual(plan.d1_rebuild_ids, expanded)
                self.assertEqual(plan.d2_rebuild_ids, d2)
                self.assertEqual(plan.eligibility_rebuild_ids, expanded)
                self.assertTrue(plan.rescan_pools)

    def test_universe_industry_registry_frozen_or_contract_change_forces_full_rebuild(self):
        for key in ("universe_hash", "registry_manifest_hash", "frozen_input_hash",
                "policy_contract_hash", "population_hash", "secondary_industry", "contract_version"):
            with self.subTest(key=key):
                self.new = copy.deepcopy(self.old)
                self.new_identity = dict(self.identity)
                target = self.new_identity if key == "contract_version" else (
                    self.new["inputs"][0] if key == "secondary_industry" else self.new)
                target[key] = "changed"
                plan = self.plan()
                self.assertTrue(plan.full_rebuild)
                self.assertEqual(plan.d1_rebuild_ids, IDS)
                self.assertEqual(plan.d2_rebuild_ids, IDS)
                self.assertEqual(plan.eligibility_rebuild_ids, IDS)
                self.assertTrue(plan.rescan_pools)

    def test_diagnostic_timing_or_display_change_does_not_rebuild(self):
        self.new_coverage["diagnostics"] = {"timing_ms": 100}
        self.new_coverage["rows"][0]["rechecked_at_utc"] = "later"
        self.new["inputs"][0]["display"] = {"precision": 2}
        plan = self.plan()
        self.assertFalse(plan.full_rebuild)
        self.assertFalse(plan.rescan_pools)
        self.assertEqual(plan.expanded_security_ids, ())
        self.assertEqual(plan.d1_rebuild_ids, ())

    def test_caller_supplied_changed_ids_are_not_an_api_or_authority(self):
        signature = inspect.signature(FormalFinalRunRepository.plan_rebuild)
        self.assertNotIn("changed_ids", signature.parameters)
        self.assertNotIn("changed_security_ids", signature.parameters)
        with self.assertRaises(TypeError):
            FormalFinalRunRepository.plan_rebuild(None, changed_ids=[IDS[0]])
        with self.assertRaises(ValueError):
            _derive_plan(prior_inputs=self.old, current_inputs=self.new,
                prior_coverage=self.coverage, current_coverage=self.new_coverage,
                prior_dependencies=[dict(dependencies(self.old)[0], effect_scope="policy")],
                prior_identity=self.identity, current_identity=self.new_identity)

    def test_unlocalizable_pending_aggregate_change_forces_explicit_full_rebuild(self):
        self.old["inputs"][0]["slots"] = {}
        self.old["inputs"][0]["status"] = "pending_evidence"
        self.new = copy.deepcopy(self.old)
        self.new["base_batch_hash"] = "corrected-but-not-localizable"
        plan = self.plan()
        self.assertTrue(plan.full_rebuild)
        self.assertIn("unlocalizable_upstream_change", plan.reason_codes)

    def test_batch_hash_churn_does_not_expand_localized_evidence(self):
        self.new["inputs"][0]["consensus_context"]["content_sha256"] = "correction"
        self.new["base_batch_hash"] = "corrected"
        for row in self.new["inputs"]:
            row["base_batch_hash"] = "corrected"
            row["entry_hash"] += "-new"
        self.assertEqual(self.plan().expanded_security_ids, IDS[:1])

    def test_local_policy_change_cannot_hide_unlocalizable_base_change(self):
        self.new["inputs"][0]["policy_result"]["dimension_caps"] = {"T": "55"}
        self.new["base_batch_hash"] = "unrelated-correction"
        plan = self.plan()
        self.assertTrue(plan.full_rebuild)
        self.assertIn("unlocalizable_upstream_change", plan.reason_codes)

    def test_local_base_change_cannot_hide_omitted_pending_base_evidence(self):
        self.old["inputs"][2].update(status="pending_evidence", slots={})
        self.new = copy.deepcopy(self.old)
        self.new["inputs"][0]["consensus_context"]["content_sha256"] = "visible-correction"
        self.new["base_batch_hash"] = "visible-and-hidden-corrections"
        plan = self.plan()
        self.assertTrue(plan.full_rebuild)
        self.assertEqual(plan.direct_security_ids, IDS[:1])
        self.assertEqual(plan.d1_rebuild_ids, IDS)
        self.assertEqual(plan.d2_rebuild_ids, IDS)
        self.assertEqual(plan.eligibility_rebuild_ids, IDS)
        self.assertIn("unlocalizable_upstream_change", plan.reason_codes)

    def test_local_cap_cannot_hide_omitted_pending_valuation_evidence(self):
        self.old["inputs"][2].update(status="pending_evidence", slots={})
        self.new = copy.deepcopy(self.old)
        self.new["inputs"][0]["policy_result"]["dimension_caps"] = {"T": "55"}
        self.new["policy_batch_hash"] = "visible-cap"
        self.new["valuation_batch_hash"] = "cap-and-hidden-valuation-correction"
        plan = self.plan()
        self.assertTrue(plan.full_rebuild)
        self.assertEqual(plan.direct_security_ids, IDS[:1])
        self.assertEqual(plan.d1_rebuild_ids, IDS)
        self.assertEqual(plan.d2_rebuild_ids, IDS)
        self.assertEqual(plan.eligibility_rebuild_ids, IDS)
        self.assertIn("unlocalizable_upstream_change", plan.reason_codes)

    def test_aggregate_localization_requires_exact_known_source_path(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                self.old, self.coverage, self.identity = manifests()
                target = self.old.setdefault("base_extra", {}) if nested else self.old
                key = "base_batch_hash" if nested else "base_extra_batch_hash"
                target[key] = "old-opaque-source"
                self.new = copy.deepcopy(self.old)
                target = self.new["base_extra"] if nested else self.new
                target[key] = "new-opaque-source"
                self.new["inputs"][0]["consensus_context"]["content_sha256"] = "visible-correction"
                plan = self.plan()
                self.assertTrue(plan.full_rebuild)
                self.assertIn("unlocalizable_upstream_change", plan.reason_codes)

    def test_complete_retained_evidence_localizes_cap_and_downstream_valuation_seals(self):
        self.new["inputs"][0]["policy_result"]["dimension_caps"] = {"T": "55"}
        for family in ("policy", "valuation"):
            for suffix in ("_batch_hash", "_batch_canonical_sha256"):
                key = family + suffix
                self.old[key] = "old-" + key
                self.new[key] = "corrected-" + key
                for row in self.old["inputs"]:
                    row[key] = self.old[key]
                for row in self.new["inputs"]:
                    row[key] = self.new[key]
        plan = self.plan()
        self.assertFalse(plan.full_rebuild)
        self.assertEqual(plan.d1_rebuild_ids, IDS[:1])
        self.assertEqual(plan.d2_rebuild_ids, IDS[:1])
        self.assertEqual(plan.eligibility_rebuild_ids, IDS[:1])
        self.assertEqual(plan.cohort_keys, ())

    def test_nested_industry_manifest_change_forces_full_rebuild(self):
        self.old["inputs"][0]["slots"][VMID]["valuation_input"]["industry_batch_hash"] = "old-industry"
        self.new = copy.deepcopy(self.old)
        self.new["inputs"][0]["slots"][VMID]["valuation_input"]["industry_batch_hash"] = "new-industry"
        self.assertTrue(self.plan().full_rebuild)

    def test_policy_copy_inside_valuation_input_does_not_turn_cap_into_cohort_change(self):
        for row in self.old["inputs"]:
            row["slots"][VMID]["valuation_input"]["policy_result"] = copy.deepcopy(row["policy_result"])
        self.new = copy.deepcopy(self.old)
        row = self.new["inputs"][0]
        row["policy_result"]["dimension_caps"] = {"T": "55"}
        row["slots"][VMID]["valuation_input"]["policy_result"] = copy.deepcopy(row["policy_result"])
        plan = self.plan()
        self.assertEqual(plan.expanded_security_ids, IDS[:1])
        self.assertEqual(plan.cohort_keys, ())

    def test_universe_departure_is_diagnostic_but_never_a_current_rebuild_target(self):
        self.new["inputs"] = self.new["inputs"][:2]
        self.new["security_ids"] = list(IDS[:2])
        self.new_coverage["rows"] = self.new_coverage["rows"][:2]
        plan = self.plan()
        self.assertTrue(plan.full_rebuild)
        self.assertIn(IDS[2], plan.direct_security_ids)
        self.assertEqual(plan.d1_rebuild_ids, IDS[:2])
        self.assertEqual(plan.d2_rebuild_ids, IDS[:2])
        self.assertEqual(plan.eligibility_rebuild_ids, IDS[:2])

    def test_newly_eligible_peer_rebuilds_old_and_new_cohort_consumers(self):
        self.old["inputs"][0]["slots"][MID]["metric_score"]["peer_context"]["peer_security_ids"] = [IDS[1]]
        self.new = copy.deepcopy(self.old)
        self.new["inputs"][0]["slots"][MID]["metric_score"]["raw_value"] = "11"
        self.new["inputs"][1]["slots"][MID]["metric_score"]["peer_context"]["peer_security_ids"] = list(IDS[:2])
        self.assertEqual(self.plan().expanded_security_ids, IDS[:2])

    def test_captured_rebuild_planner_rechecks_mode_gate_at_both_read_boundaries(self):
        """Exercise the real planner without constructing a D1 score batch."""
        import ashare_pipeline.formal_final_repository as module
        from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor

        inputs, _, identity = manifests()
        coverage = FormalCoverageAuditor().audit([
            CoverageRequirement("frozen", sid, "financial", "selector", "2025", sid[:2])
            for sid in IDS
        ])
        raw = module._serialize_payload(inputs)[0].encode()
        coverage_raw = coverage.canonical_bytes()
        prior = SimpleNamespace(input_manifest_hash="prior", header=identity,
            artifacts={"score_input_batch": raw, "coverage_manifest": coverage_raw},
            artifact_hashes={"score_input_batch": module._serialize_payload(inputs)[1],
                "coverage_manifest": module._serialize_payload(json.loads(coverage_raw))[1]},
            dependencies=dependencies(inputs))

        class Batch:
            pass

        class Checkpoint:
            def hold(self):
                return nullcontext()

            def recheck(self):
                pass

        with TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "planner.db")
            feature = SimpleNamespace(_store=store)
            retention = ((feature,), (), (), (Checkpoint(),))
            saved = (None, None, raw, None, None, retention)

            repository = object.__new__(FormalFinalRunRepository)
            repository._store = store
            repository._path = Path(store.db_path).resolve()
            repository._code_version = "code"
            repository._contract_version = "formal-final-v1"
            gate = Mock(wraps=module._coverage_live_gate)
            overrides = {"record": lambda proof, cls: saved,
                "dependencies": lambda source: (feature,), "verify_sources": lambda sources: (),
                "input_type": Batch, "read_run": lambda self, connection, run_id: prior,
                "coverage_live_gate": gate}
            original = FormalFinalRunRepository.plan_rebuild
            values = dict(zip(original.__code__.co_freevars, original.__closure__, strict=True))
            def cell(value):
                return (lambda: value).__closure__[0]
            planner = FunctionType(original.__code__, original.__globals__, closure=tuple(
                cell(overrides[name]) if name in overrides else values[name]
                for name in original.__code__.co_freevars))
            plan = planner(repository, prior_run_id="run", prior_input_manifest_hash="prior",
                input_batch=Batch(), coverage_manifest=coverage, mode="test_preview")
            self.assertIsInstance(plan, FormalRebuildPlan)
            self.assertEqual(gate.call_count, 2)
            self.assertEqual(gate.call_args_list[0].args, (coverage, "test_preview", "code"))
            self.assertEqual(gate.call_args_list[1].args, (coverage, "test_preview", "code"))


class FormalInvalidationRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_formal_final_repository import minimal_batches
        cls.fixture, cls.batches = minimal_batches()

    def setUp(self):
        self.repository = FormalFinalRunRepository(self.fixture.store, code_version="task10-test")
        self.receipt = self.repository.commit_complete_run(**self.batches)
        self.arguments = dict(prior_run_id=self.receipt.run_id,
            prior_input_manifest_hash=self.receipt.input_manifest_hash,
            input_batch=self.batches["input_batch"], coverage_manifest=self.batches["coverage_manifest"])

    def test_restart_selects_prior_exact_manifest_not_later_correction(self):
        from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor
        requirements = [CoverageRequirement(self.fixture.frozen.frozen_input_hash, sid,
            "financial", "selector", "2025", sid[:2], ("CNY",)) for sid in IDS]
        correction = FormalCoverageAuditor().audit(requirements)
        later = self.repository.commit_complete_run(**dict(self.batches, coverage_manifest=correction))
        self.assertNotEqual(later.input_manifest_hash, self.receipt.input_manifest_hash)
        restarted = FormalFinalRunRepository(self.fixture.store, code_version="task10-test")
        plan = restarted.plan_rebuild(**dict(self.arguments, coverage_manifest=correction))
        self.assertEqual(plan.prior_manifest_hash, self.receipt.input_manifest_hash)
        self.assertEqual(plan.current_manifest_hash, later.input_manifest_hash)
        self.assertTrue(plan.rescan_pools)
        with self.assertRaises(ValueError):
            restarted.plan_rebuild(**dict(self.arguments, prior_input_manifest_hash=later.input_manifest_hash))

    def test_old_run_bytes_never_change_after_new_rebuild(self):
        before = self.repository.get_run(self.receipt.run_id)
        plan = self.repository.plan_rebuild(**self.arguments)
        self.assertFalse(plan.rescan_pools)
        self.assertEqual(plan.prior_manifest_hash, plan.current_manifest_hash)
        later = self.repository.commit_complete_run(**self.batches)
        self.assertNotEqual(later.run_id, before.run_id)
        self.assertEqual(self.repository.get_run(before.run_id), before)

    def test_reuse_requires_current_hash_and_capability_revalidation(self):
        import ashare_pipeline.formal_final_repository as module
        from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor
        self.assertFalse(self.repository.plan_rebuild(**self.arguments).rescan_pools)
        for key in ("input_batch", "coverage_manifest"):
            proof = self.arguments[key]
            for fake in (proof.to_dict(), object.__new__(type(proof))):
                with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                    self.repository.plan_rebuild(**dict(self.arguments, **{key: fake}))
        r = CoverageRequirement(self.fixture.frozen.frozen_input_hash, IDS[0], "financial", "selector", "2025", "BJ")
        revoked = FormalCoverageAuditor().audit([r])
        FormalCoverageAuditor.revoke(revoked)
        with self.assertRaises(ValueError):
            self.repository.plan_rebuild(**dict(self.arguments, coverage_manifest=revoked))
        prepared = []
        original_prepare = module._prepare_publication
        def observe(**kwargs):
            publication = original_prepare(**kwargs)
            prepared.append(publication)
            return publication
        with patch.object(module, "_prepare_publication", observe), patch.object(
                module, "_insert_rows", side_effect=RuntimeError("injected write failure")):
            with self.assertRaises(RuntimeError):
                self.repository.commit_complete_run(**self.batches)
        with self.assertRaises(ValueError):
            self.repository.plan_rebuild(**dict(self.arguments, input_batch=prepared[0].batches[0]))
        # Actual persisted source mutation must fail even though D1 bytes stay sealed.
        with self.fixture.store._transaction() as connection:
            row = connection.execute("SELECT id,content_sha256 FROM formal_source_snapshot LIMIT 1").fetchone()
            connection.execute("UPDATE formal_source_snapshot SET content_sha256=? WHERE id=?", ("0" * 64, row[0]))
        try:
            with self.assertRaises(ValueError):
                self.repository.plan_rebuild(**self.arguments)
        finally:
            with self.fixture.store._transaction() as connection:
                connection.execute("UPDATE formal_source_snapshot SET content_sha256=? WHERE id=?", (row[1], row[0]))


if __name__ == "__main__":
    unittest.main()
