"""Complete score provenance: real producer-backed receipts, no proof doubles."""

import importlib
import importlib.util
import copy
import gc
import hashlib
import sys
import weakref
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from decimal import Decimal

from tests.formal_score_input_fixtures import ScoreFixture, FOCAL
from tests.formal_metric_feature_fixtures import FinancialFixture


class FormalScoreInputTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_score_inputs"),
            "complete score input repository must own all provenance")
        return importlib.import_module("ashare_pipeline.formal_score_inputs")

    def build(self, fixture):
        api = self.api()
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        return repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)

    def test_complete_focal_retains_pending_peers_and_all_25_metric_scores(self):
        fixture = ScoreFixture(linked=False)
        self.addCleanup(fixture.close)
        fixture.populate_scores()
        batch = self.build(fixture)
        self.assertEqual(len(batch.security_ids), 22)
        self.assertEqual(tuple(item.security_id for item in batch.inputs), (FOCAL,))
        focal = batch.input_for(FOCAL)
        self.assertEqual(len(focal.slots), 25)
        self.assertEqual(focal.continuous_fy_count, 4)
        self.assertFalse(focal.cyclic)
        self.assertEqual(focal.comparable_quarter_keys[-8:],
            ("2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"))
        self.assertEqual(focal.slots["M.return_persistence"]["metric_score"]["peer_count"], 20)
        self.assertEqual(focal.slots["CA.return_persistence"]["temporal_quality"], Decimal("1"))
        self.assertEqual(len(batch.pending_reasons), 21)
        self.assertIsNone(batch.input_for("SH600000"))
        for selector in ("430001", "bj430001", "BJ430001 ", "SH999999", None, 1):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                batch.input_for(selector)
        for proof in (batch, focal):
            with self.assertRaises(TypeError):
                copy.copy(proof)
            with self.assertRaises((AttributeError, TypeError)):
                proof.security_id = "SH999999"
            detached = proof.to_dict()
            detached.clear()
            proof.require_verified()
            forged = object.__new__(type(proof))
            for method in ("require_verified", "canonical_bytes", "to_dict"):
                with self.assertRaises(ValueError):
                    getattr(forged, method)()
        owner = weakref.ref(batch)
        raw = focal.canonical_bytes()
        del proof, batch
        gc.collect()
        self.assertIsNone(owner())
        self.assertEqual(focal.canonical_bytes(), raw)

    def test_registered_actual_no_coverage_waives_only_expectation(self):
        fixture = ScoreFixture()
        self.addCleanup(fixture.close)
        fixture.populate_scores(missing=("T.expectation_change",), consensus="none")
        focal = self.build(fixture).input_for(FOCAL)
        self.assertIsNotNone(focal)
        slot = focal.slots["T.expectation_change"]
        self.assertEqual(slot["evidence_kind"], "registered_consensus_no_coverage")
        self.assertEqual(slot["value"], Decimal("50"))
        self.assertIsNone(slot["metric_score"])
        self.assertEqual(focal.confidence_cap, Decimal("0.90"))
        self.assertEqual(slot["context_fact"]["value"]["coverage_status"], "no_valid_coverage")
        with self.assertRaises(ValueError):
            fixture.feature_repository.get_verified_formal_feature_bundle(input_hash=focal.feature_state["input_hash"])

    def test_failed_outer_publication_revokes_children_but_not_inner_metric_batch(self):
        api = self.api()
        from ashare_pipeline.formal_metric_engine import MetricInputBatch
        fixture = ScoreFixture(cyclic=True, date_only=True)
        self.addCleanup(fixture.close)
        fixture.populate_scores(five_years=True, consensus="none")
        captured, inner = [], []
        snapshot = fixture.provider.resolve_current_inputs(security_id=FOCAL,
            as_of_utc="2026-08-31T07:00:00+00:00", template_id="general_nonfinancial",
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash)
        def profile(frame, event, result):
            if event != "return" or frame.f_code.co_name != "publish_complete":
                return
            if type(result) is MetricInputBatch and not inner:
                inner.append(result)
            if type(result) is api.FormalScoreInputBatch and not captured:
                focal = result.input_for(FOCAL)
                self.assertIsNotNone(focal)
                self.assertTrue(focal.cyclic)
                self.assertEqual(focal.continuous_fy_count, 5)
                self.assertEqual(focal.slots["T.expectation_change"]["value"], Decimal("50"))
                self.assertEqual(focal.slots["T.expectation_change"]["temporal_quality"], Decimal("0.8"))
                self.assertIsNotNone(focal.consensus_context["evidence"]["calendar_binding"])
                self.assertEqual(focal.slots["T.expectation_change"]["full_feature_values"][0]["status"], "derived")
                captured.extend((result, focal))
                with self.assertRaises(ValueError):
                    fixture.provider.publish(replace(snapshot, batch_id="reentrant-outer-revocation"))
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(ValueError, "changed during complete batch finalization"):
                self.build(fixture)
        finally:
            sys.setprofile(previous)
        self.assertEqual(len(captured), 2)
        self.assertEqual(len(inner), 1)
        inner[0].require_verified()
        for proof in captured:
            for method in ("require_verified", "canonical_bytes", "to_dict"):
                with self.assertRaises(ValueError):
                    getattr(proof, method)()


class ScoreInputGateTests(unittest.TestCase):
    """Pure diagnostics are not proofs; all minting tests above use real stores."""

    def test_consensus_absence_requires_context_and_unlinked_cannot_neutralize(self):
        from ashare_pipeline import formal_score_inputs as api
        self.assertTrue(callable(getattr(api, "_consensus_branch", None)))
        link = {"metric_id": "T.expectation_change"}
        actual = dict(no_coverage=True, value=dict(coverage_status="no_valid_coverage", estimates=[]))
        self.assertEqual(api._consensus_branch(link, None), (False, ("consensus_context_absent",)))
        self.assertEqual(api._consensus_branch(None, actual), (False, ()))
        self.assertEqual(api._consensus_branch(link, actual), (True, ()))
        covered = dict(no_coverage=False, value=dict(coverage_status="covered", estimates=[{"profit": 1}]))
        self.assertEqual(api._consensus_branch(link, covered), (False, ()))
        for bad in (dict(no_coverage=True, value=covered["value"]),
                    dict(no_coverage=False, value=actual["value"])):
            with self.assertRaises(ValueError):
                api._consensus_branch(link, bad)

    def test_temporal_quality_is_minimum_actual_ref_precision(self):
        from ashare_pipeline import formal_score_inputs as api
        self.assertTrue(callable(getattr(api, "_temporal_quality", None)))
        self.assertEqual(api._temporal_quality(({"published_precision": "timestamp"},)), Decimal("1"))
        self.assertEqual(api._temporal_quality(({"published_precision": "timestamp"},
            {"published_precision": "date_only"})), Decimal("0.8"))
        for bad in ((), ({"published_precision": "guess"},)):
            with self.assertRaises(ValueError):
                api._temporal_quality(bad)

    def test_full_slots_history_and_global_issues_cannot_be_waived(self):
        from ashare_pipeline.formal_score_inputs import _full_company_gate
        quarters = ("2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2")
        def slot(key, required=True):
            return SimpleNamespace(slot_id=key, unit="CNY", formula_version="v1", required=required)
        def value(key, status="derived"):
            return SimpleNamespace(slot_id=key, unit="CNY", formula_version="v1", status=status)
        slots = (slot("extra"), slot("normal"), slot("optional", False), slot("prediction"))
        bundle = SimpleNamespace(history_endpoints=("2010-12-31", "2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"),
            comparable_quarter_keys=quarters, blockers=("feature_required_slot_missing",),
            values=(value("extra"), value("normal"), value("optional", "missing"), value("prediction", "missing")))
        marker = {"issue_snapshot_hash": hashlib.sha256(b"[]").hexdigest()}
        gate = lambda **kw: _full_company_gate(bundle, slots, marker, cyclic=kw.get("cyclic", False),
            exempt_key=kw.get("exempt_key", "prediction"))
        self.assertEqual(gate(), ((), 4))
        self.assertIn("feature_required_slot_missing", gate(exempt_key=None)[0])
        self.assertIn("history_annual_window_incomplete", gate(cyclic=True)[0])
        for index, status, reason in ((0, "missing", "full_required_slot_missing:extra"),
                (2, "blocked", "full_slot_blocked:optional"), (3, "blocked", "full_slot_blocked:prediction")):
            original = bundle.values
            bundle.values = tuple(value(item.slot_id, status) if i == index else item for i, item in enumerate(original))
            self.assertIn(reason, gate()[0])
            bundle.values = original
        marker["issue_snapshot_hash"] = "f" * 64
        self.assertIn("nonempty_current_issues", gate()[0])
        bundle.comparable_quarter_keys = quarters[:-1]
        self.assertIn("history_quarter_window_incomplete", gate()[0])

    def test_dependencies_reject_substitution_even_with_no_classified_members(self):
        from ashare_pipeline import formal_score_inputs as api
        from ashare_pipeline import formal_metric_engine as engine
        fixture = FinancialFixture(missing_memberships=True)
        self.addCleanup(fixture.close)
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        run = lambda: repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        for cls, name in ((engine.MetricInputBatch.__mro__[1], "__getattr__"),
                          (engine.MetricInputBatch.__mro__[1], "require_verified"),
                          (engine.MetricInputBatch, "input_for"),
                          (engine.FormalMetricInputRepository, "build_batch")):
            with self.subTest(name=name), patch.object(cls, name, lambda *a, **k: None), self.assertRaises(ValueError):
                run()
        for name in ("build_metric_peer_context", "score_metric_percentile"):
            with patch.object(engine, name, lambda *a, **k: None), self.assertRaises(ValueError):
                run()
        with self.assertRaises(ValueError):
            repository.__init__(fixture.feature_repository, fixture.context, registry_signature_verifier=fixture.verifier)
        with self.assertRaises(ValueError):
            object.__new__(api.FormalScoreInputRepository).build_batch(fixture.frozen.frozen_input_hash,
                scoring_registry=fixture.scoring)
        batch = run()
        self.assertEqual(batch.inputs, ())
        self.assertEqual(len(batch.pending_reasons), 3)
        for reasons in batch.pending_reasons.values():
            self.assertIn("invalid_template", reasons)
            self.assertNotIn("current_receipt_absent", reasons)

    def test_concrete_proof_cannot_shadow_inherited_verification(self):
        from ashare_pipeline import formal_score_inputs as api
        from ashare_pipeline import formal_metric_engine as engine
        fixture = FinancialFixture(missing_memberships=True)
        self.addCleanup(fixture.close)
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        for name in ("require_verified", "canonical_bytes", "to_dict", "__getattr__"):
            original = getattr(engine.MetricInputBatch, name)
            with self.subTest(name=name), patch.object(engine.MetricInputBatch, name,
                    lambda *args, **kwargs: original(*args, **kwargs), create=True):
                with self.assertRaises(ValueError):
                    repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)

    def test_transitive_universe_proof_verification_cannot_be_replaced(self):
        from ashare_pipeline import formal_score_inputs as api
        from ashare_pipeline.formal_metric_context import VerifiedMetricUniverse, VerifiedMetricIndustryBatch
        from ashare_pipeline.formal_feature_repository import VerifiedMetricFeatureAbsence, VerifiedMetricFeatureProjection
        fixture = FinancialFixture(missing_memberships=True)
        self.addCleanup(fixture.close)
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        for cls in (VerifiedMetricUniverse, VerifiedMetricIndustryBatch, VerifiedMetricFeatureAbsence, VerifiedMetricFeatureProjection):
            for name in ("require_verified", "canonical_bytes", "to_dict"):
                with self.subTest(cls=cls.__name__, name=name), patch.object(cls, name, lambda self: None, create=True):
                    with self.assertRaises(ValueError):
                        repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)

    def test_context_missing_to_present_transition_aborts_even_all_pending(self):
        from ashare_pipeline import formal_score_inputs as api
        fixture = ScoreFixture(population=False)
        self.addCleanup(fixture.close)
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        changed = []
        def profile(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "read_consensus"
                    and frame.f_globals.get("__name__") == api.__name__ and not changed):
                changed.append(True)
                fixture.put_consensus()
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(ValueError, "consensus correction or absence changed"):
                repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        finally:
            sys.setprofile(previous)
        self.assertTrue(changed)

    def test_outer_exit_failure_revokes_already_published_batch(self):
        from ashare_pipeline import formal_score_inputs as api
        fixture = FinancialFixture(missing_memberships=True)
        self.addCleanup(fixture.close)
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        captured = []
        def profile(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "publish_complete"
                    and type(result) is api.FormalScoreInputBatch):
                captured.append(result)
            if (event == "return" and frame.f_code.co_name == "guard" and captured
                    and frame.f_globals.get("__name__") == "ashare_pipeline.formal_metric_batch_guard"):
                raise RuntimeError("injected outer exit failure")
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(RuntimeError, "outer exit failure"):
                repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        finally:
            sys.setprofile(previous)
        self.assertEqual(len(captured), 1)
        with self.assertRaises(ValueError):
            captured[0].require_verified()

    def test_actual_source_sql_and_signed_root_tamper_fail_closed(self):
        from ashare_pipeline import formal_score_inputs as api
        fixture = ScoreFixture(population=False)
        self.addCleanup(fixture.close)
        fact = fixture.put_consensus()
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        run = lambda: repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        path = Path(fixture.store.get_formal_snapshot(fact.source_snapshot_id).content_path)
        original = path.read_bytes()
        try:
            path.write_bytes(b"tampered actual consensus source")
            with self.assertRaises(ValueError):
                run()
        finally:
            path.write_bytes(original)
        fixture.sql("UPDATE formal_context_fact SET value_json=? WHERE id=?", ('{}', fact.id))
        with self.assertRaises(ValueError):
            run()
        fixture.sql("UPDATE formal_registry_manifest SET signature='invalid-byte-sensitive-signature'")
        with self.assertRaises(ValueError):
            run()

    def test_absence_and_same_store_dependency_boundary(self):
        from ashare_pipeline import formal_score_inputs as api
        from ashare_pipeline.formal_metric_batch_guard import FormalMetricCurrentInputProvider
        fixture = FinancialFixture(missing_memberships=True)
        self.addCleanup(fixture.close)
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        self.assertIsNone(repository.build_batch("f" * 64, scoring_registry=fixture.scoring))
        for source, context in ((object.__new__(type(fixture.feature_repository)), fixture.context),
                (fixture.feature_repository, object.__new__(type(fixture.context)))):
            with self.assertRaises(ValueError):
                api.FormalScoreInputRepository(source, context, registry_signature_verifier=fixture.verifier)
        original = fixture.feature_repository._current_input_provider
        try:
            fixture.feature_repository._current_input_provider = object.__new__(FormalMetricCurrentInputProvider)
            with self.assertRaises(ValueError):
                repository.build_batch("f" * 64, scoring_registry=fixture.scoring)
        finally:
            fixture.feature_repository._current_input_provider = original
        for kwargs in ({"security_ids": (FOCAL,)}, {"metric_ids": ("T.expectation_change",)},
                       {"cyclic": False}, {"no_coverage": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(TypeError):
                repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, **kwargs)

    def test_actual_linked_absence_and_small_cohort_stay_pending(self):
        from ashare_pipeline import formal_score_inputs as api
        fixture = ScoreFixture(population=False)
        self.addCleanup(fixture.close)
        fixture.populate_scores(consensus=None)
        repository = api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        missing = repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        self.assertIn("consensus_context_absent", missing.pending_reasons[FOCAL])
        self.assertIsNone(missing.input_for(FOCAL))
        fixture.put_consensus()
        neutral = repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        self.assertIsNone(neutral.input_for(FOCAL))
        self.assertEqual(len(neutral.pending_reasons[FOCAL]), 24)
        self.assertTrue(all("peer_count_below_20" in reason for reason in neutral.pending_reasons[FOCAL]))


if __name__ == "__main__":
    unittest.main()
