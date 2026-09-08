"""Metric projections use real signed graphs, source receipts and SQLite facts."""

import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import tests.test_formal_feature_repository as fixtures
from tests.test_formal_feature_contract import feature_registry_bytes, slot_wire, TEMPLATES
from ashare_pipeline.formal_feature_contract import FormalFeatureBundle
from ashare_pipeline.formal_financial_schema import FormalFactIssue
import ashare_pipeline.formal_metric_features as metric_evaluation
from ashare_pipeline.formal_financial_features import FormalFormulaResult
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore


class MetricProjectionTests(unittest.TestCase):
    # Reuse fixture operations, never inherit/import a TestCase into discovery.
    setUp = fixtures.FormalFeatureRepositoryTests.setUp
    install_fact = fixtures.FormalFeatureRepositoryTests.install_fact
    install_eligible_bundle_facts = fixtures.FormalFeatureRepositoryTests.install_eligible_bundle_facts
    install_registry = fixtures.FormalFeatureRepositoryTests.install_registry
    repository = fixtures.FormalFeatureRepositoryTests.repository
    build = fixtures.FormalFeatureRepositoryTests.build
    snapshot = fixtures.FormalFeatureRepositoryTests.snapshot
    sql = fixtures.FormalFeatureRepositoryTests.sql
    correction = fixtures.FormalFeatureRepositoryTests.correction
    persist_unchecked = fixtures.FormalFeatureRepositoryTests.persist_unchecked

    def project(self, *, repo=None, snapshot=None, **changes):
        self.assertTrue(callable(getattr(self.api.FormalFeatureRepository,
            "select_current_verified_metric_features", None)), "metric projection endpoint is missing")
        request = dict(security_id="SZ000001", as_of_utc="2026-08-31T07:00:00+00:00",
            template_id="general_nonfinancial", registry_manifest_hash=self.manifest.manifest_hash,
            required_feature_keys=("general_nonfinancial.growth",))
        request.update(changes)
        repo = repo or self.repository(fixtures.SnapshotProvider(snapshot or self.snapshot()))
        return repo.select_current_verified_metric_features(**request)

    def persist(self, *, issues=()):
        bundle = self.build(issues=issues)
        self.store.put_formal_feature_bundle(bundle, self.files.write(bundle))
        return bundle

    def configure(self, formula=None, unit="CNY", extra=False, required=True):
        formula = formula or {"op": "fact", "fact_key": "revenue", "period_key": "FY2025"}
        slots = [slot_wire(t, unit=unit, required=required, formula=formula) for t in TEMPLATES]
        if extra:
            slots.append(slot_wire("general_nonfinancial", suffix="other", unit="CNY",
                formula={"op": "fact", "fact_key": "unobserved", "period_key": "FY2025"}))
        def registry_bytes(**kwargs):
            kwargs["slots"] = sorted(slots, key=lambda x: x["slot_id"])
            return feature_registry_bytes(**kwargs)
        with patch.object(fixtures, "feature_registry_bytes", side_effect=registry_bytes):
            self.install_registry()

    def only_periods(self, *periods):
        marks = ",".join("?" for _ in periods)
        self.sql(f"DELETE FROM formal_financial_fact WHERE period_end NOT IN ({marks})", periods)

    def add_fact(self, **kwargs):
        original = self.store
        fact = self.install_fact(**kwargs)
        self.store = original
        self.store.insert_formal_financial_facts((fact,))
        return fact

    def test_valid_projection_is_deterministic_and_binds_receipt(self):
        first, second = self.project(), self.project()
        self.assertEqual(first.values[0].value, 100.0)
        self.assertEqual(first.values[0].status, "derived")
        self.assertEqual(first.input_hash, self.bundle.input_hash)
        self.assertEqual(first.bundle_hash, self.bundle.bundle_hash())
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(len(first.projection_hash), 64)
        self.assertEqual(first.required_feature_keys, ("general_nonfinancial.growth",))
        self.assertEqual(first.slots[0].formula.period_key, "FY2025")
        wire = first.to_dict()
        wire["values"][0]["value"] = 999.0
        self.assertEqual(first.values[0].value, 100.0)
        self.assertEqual(self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash).canonical_bytes(), self.bundle.canonical_bytes())

    def test_missing_other_required_slot_does_not_exclude_selected_metric(self):
        self.configure(extra=True)
        bundle = self.persist()
        self.assertIn("feature_required_slot_missing", bundle.blockers)
        self.assertEqual(self.project().values[0].value, 100.0)
        with self.assertRaises(ValueError):
            self.repository().get_verified_formal_feature_bundle(input_hash=bundle.input_hash)

    def test_annual_only_survives_global_history_and_quarter_shortage(self):
        self.only_periods("2025-12-31")
        bundle = self.persist()
        self.assertIn("pending_evidence/history_not_mature", bundle.blockers)
        projection = self.project()
        self.assertEqual(projection.values[0].value, 100.0)
        self.assertEqual(len(projection.values[0].evidence), 1)
        self.assertEqual(projection.blockers, ())
        with self.assertRaises(ValueError):
            self.repository().get_verified_formal_feature_bundle(input_hash=bundle.input_hash)

    def test_requested_quarter_ignores_predecessors_own_missing_predecessor(self):
        self.configure({"op": "fact", "fact_key": "revenue", "period_key": "2025Q4"})
        self.only_periods("2025-09-30", "2025-12-31")
        self.persist()
        value = self.project().values[0]
        self.assertEqual(value.value, 0.0)
        self.assertEqual(value.status, "derived")
        self.assertEqual(len(value.evidence), 2)

    def test_required_fact_or_quarter_predecessor_missing_is_explicit(self):
        self.only_periods("2024-12-31")
        self.persist()
        value = self.project().values[0]
        self.assertIsNone(value.value)
        self.assertEqual(value.missing_reason, "formula_fact_missing")
        self.configure({"op": "fact", "fact_key": "revenue", "period_key": "2024Q4"})
        self.persist()
        value = self.project().values[0]
        self.assertIsNone(value.value)
        self.assertIn("quarter_missing_prerequisite", self.project().blockers)

    def test_zero_denominator_unit_mismatch_and_negative_values(self):
        leaf = {"op": "fact", "fact_key": "revenue", "period_key": "FY2025"}
        zero = {"op": "subtract", "left": leaf, "right": leaf}
        self.configure({"op": "divide", "left": leaf, "right": zero}, "ratio")
        self.persist()
        self.assertEqual(self.project().values[0].missing_reason, "formula_zero_denominator")
        self.configure(leaf, "shares")
        self.persist()
        self.assertEqual(self.project().values[0].missing_reason, "formula_unit_mismatch")
        self.configure({"op": "subtract", "left": zero, "right": leaf})
        self.persist()
        self.assertEqual(self.project().values[0].value, -100.0)

    def test_unresolved_issue_cannot_be_hidden_by_claimed_scope(self):
        issue = FormalFactIssue("unknown_source_field", None, "OTHER", {"period": "FY1900", "metric_key": "unrelated"})
        self.persist(issues=(issue,))
        projection = self.project(snapshot=self.snapshot(issues=(issue,)))
        self.assertEqual(projection.values[0].status, "blocked")
        self.assertIsNone(projection.values[0].value)
        self.assertIn("formal_fact_issue_unknown_source_field", projection.blockers)

    def test_missing_current_receipt_returns_none(self):
        self.correction()
        self.assertIsNone(self.project())

    def state(self, *, snapshot=None):
        repo = self.repository(fixtures.SnapshotProvider(snapshot or self.snapshot()))
        endpoint = getattr(repo, "select_current_verified_metric_feature_state", None)
        self.assertTrue(callable(endpoint), "authenticated absence endpoint is missing")
        return endpoint("SZ000001", "2026-08-31T07:00:00+00:00",
            template_id="general_nonfinancial", registry_manifest_hash=self.manifest.manifest_hash,
            required_feature_keys=("general_nonfinancial.growth",))

    def test_still_unpersisted_inputs_need_distinct_authenticated_markers(self):
        self.correction()
        self.assertIsNone(self.project())
        first = self.state()
        first.require_verified()
        self.assertEqual(first.status, "current_receipt_absent")
        self.assertEqual(first.canonical_bytes(), self.state().canonical_bytes())
        self.add_fact(value=300.0, generation="later-absent",
            source_overrides={"source_updated_at_utc": "2026-05-01T00:00:00+00:00"})
        self.assertIsNone(self.project())  # Bare None equality misses the correction.
        second = self.state()
        self.assertNotEqual(first.absence_hash, second.absence_hash)
        self.assertNotEqual(first.fact_snapshot_hash, second.fact_snapshot_hash)

    def test_absence_binds_issues_and_logical_provider_identity(self):
        self.correction()
        first = self.state()
        issue = FormalFactIssue("unknown_source_field", None, "OTHER", {})
        self.assertNotEqual(first.absence_hash, self.state(snapshot=self.snapshot(issues=(issue,))).absence_hash)
        self.assertNotEqual(first.absence_hash, self.state(snapshot=self.snapshot(batch_id="next-batch")).absence_hash)

    def test_absent_receipt_becomes_present_without_changing_projection_bytes(self):
        self.correction()
        self.assertEqual(self.state().status, "current_receipt_absent")
        self.persist()
        self.assertEqual(self.state().canonical_bytes(), self.project().canonical_bytes())

    def test_absence_proof_cannot_be_constructed_copied_or_mutated(self):
        self.correction()
        proof = self.state()
        with self.assertRaises(TypeError):
            type(proof)()
        for copier in (copy.copy, copy.deepcopy):
            with self.assertRaises((TypeError, ValueError)):
                copier(proof)
        with self.assertRaises((AttributeError, TypeError, ValueError)):
            object.__setattr__(proof, "input_hash", "f" * 64)
        with self.assertRaises(ValueError):
            object.__new__(type(proof)).require_verified()

    def test_absence_does_not_hide_invalid_provider_or_raw_source(self):
        self.correction()
        with self.assertRaises(ValueError):
            self.state(snapshot=self.snapshot(complete=False))
        captured = self.snapshot()
        path = Path(self.store.get_formal_snapshot(self.fact.source_snapshot_id).content_path)
        path.write_bytes(b"invalid absence source")
        with self.assertRaises(ValueError):
            self.state(snapshot=captured)

    def test_absence_rejects_invalid_child_signature(self):
        self.correction()
        captured = self.snapshot()
        self.sql("UPDATE formal_registry_blob SET signature='invalid' WHERE registry_role='feature'")
        with self.assertRaises(ValueError):
            self.state(snapshot=captured)

    def test_proof_constructor_copy_and_low_level_mutation_reject(self):
        original = self.project()
        with self.assertRaises(TypeError):
            type(original)()
        fake = object.__new__(type(original))
        with self.assertRaises(ValueError):
            fake.to_dict()
        for copier in (copy.copy, copy.deepcopy):
            try:
                clone = copier(original)
            except (TypeError, ValueError):
                continue
            self.assertIsNot(clone, original)
            with self.assertRaises(ValueError):
                clone.to_dict()
        object.__setattr__(original, "input_hash", "f" * 64)
        with self.assertRaises(ValueError):
            original.canonical_bytes()

    def test_fake_repository_or_replaced_dependencies_cannot_mint(self):
        real = self.repository(fixtures.SnapshotProvider(self.snapshot()))
        fake = object.__new__(type(real))
        fake.__dict__.update(real.__dict__)
        with self.assertRaises(ValueError):
            self.project(repo=fake)
        real._store = self.repository()._store
        real._bundle_store = object()
        with self.assertRaises(ValueError):
            self.project(repo=real)

    def test_invalid_cutoff_template_security_root_and_keys_reject(self):
        for changes in ({"as_of_utc": "2026-08-30T07:00:00+00:00"}, {"template_id": "bank"},
                {"security_id": "000001"}, {"registry_manifest_hash": "f" * 64},
                {"required_feature_keys": ()}, {"required_feature_keys": ["general_nonfinancial.growth"]},
                {"required_feature_keys": ("general_nonfinancial.growth",) * 2},
                {"required_feature_keys": ("general_nonfinancial.unknown",)},
                {"required_feature_keys": ("bank.growth",)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.project(**changes)
        self.configure(required=False)
        self.persist()
        with self.assertRaises(ValueError):
            self.project()

    def test_sql_bundle_and_raw_source_tamper_reject(self):
        self.sql("UPDATE formal_feature_value SET value=999")
        with self.assertRaises(ValueError):
            self.project()
        self.sql("UPDATE formal_feature_value SET value=100")
        row = self.store.get_formal_feature_bundle_row(self.bundle.input_hash)
        bundle_path = Path(row["bundle_path"])
        original = bundle_path.read_bytes()
        bundle_path.write_bytes(b"{}")
        with self.assertRaises(ValueError):
            self.project()
        bundle_path.write_bytes(original)
        ref = self.store.get_formal_snapshot(self.fact.source_snapshot_id)
        Path(ref.content_path).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.project()

    def test_replaced_evaluation_dependency_cannot_supply_numeric_override(self):
        original = metric_evaluation.evaluate_formula
        def forged(*args, **kwargs):
            result = original(*args, **kwargs)
            return FormalFormulaResult(999.0, result.unit, result.evidence, result.time_reliability, None)
        with patch.object(metric_evaluation, "evaluate_formula", forged), self.assertRaises(ValueError):
            self.project()

    def test_store_trust_dependencies_cannot_be_replaced_after_repository_creation(self):
        repo = self.repository(fixtures.SnapshotProvider(self.snapshot()))
        self.store._registry_signature_verifier = fixtures.DigestVerifier()
        with self.assertRaises(ValueError):
            self.project(repo=repo)

    def test_cached_source_readers_cannot_hide_actual_raw_file_tamper(self):
        source = self.store._formal_snapshot_store
        raw_reader, validator = source.read_verified_raw, source.validate_stored_snapshot
        cached_raw, cached_validation = {}, {}
        def capture_raw(stored, **kwargs):
            result = raw_reader(stored, **kwargs)
            cached_raw[stored.manifest_sha256] = result
            return result
        def capture_validation(fetch, stored, verification, **kwargs):
            result = validator(fetch, stored, verification, **kwargs)
            cached_validation[stored.manifest_sha256] = result
            return result
        with patch.object(source, "read_verified_raw", capture_raw), patch.object(source, "validate_stored_snapshot", capture_validation):
            snapshot = self.snapshot()
            ref = self.store.get_formal_snapshot(self.fact.source_snapshot_id)
        repo = self.repository(fixtures.SnapshotProvider(snapshot))
        Path(ref.content_path).write_bytes(b"corrupted after authentic source read")
        def replay_raw(stored, **kwargs):
            return cached_raw[stored.manifest_sha256]
        def replay_validation(fetch, stored, verification, **kwargs):
            return cached_validation[stored.manifest_sha256]
        with patch.object(source, "read_verified_raw", replay_raw), patch.object(source, "validate_stored_snapshot", replay_validation):
            with self.assertRaises(ValueError):
                result = self.project(repo=repo, snapshot=snapshot)
                result.require_verified()

    def test_source_reader_class_and_classmethod_replacement_rejects(self):
        snapshot = self.snapshot()
        repo = self.repository(fixtures.SnapshotProvider(snapshot))
        reader = FormalSnapshotStore.read_verified_raw
        def replaced_reader(source, *args, **kwargs):
            return reader(source, *args, **kwargs)
        validator = FormalSnapshotStore._validate_formal_fetch_values
        def replaced_class_validator(cls, *args, **kwargs):
            return validator(*args, **kwargs)
        for name, replacement in (("read_verified_raw", replaced_reader),
                ("_validate_formal_fetch_values", classmethod(replaced_class_validator))):
            with self.subTest(method=name), patch.object(FormalSnapshotStore, name, replacement):
                with self.assertRaises(ValueError):
                    self.project(repo=repo, snapshot=snapshot)

    def test_complete_provider_identity_fact_and_issue_boundaries_are_enforced(self):
        for changes in ({"complete": False}, {"batch_id": " "}, {"facts": ()},
                {"facts": []}, {"issues": []}, {"issues": ({},)},
                {"security_id": "SH600001"}, {"template_id": "bank"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.project(snapshot=self.snapshot(**changes))

    def test_nested_proof_value_and_slot_mutation_invalidates_seal(self):
        projection = self.project()
        object.__setattr__(projection.slots[0].formula, "period_key", "FY2024")
        with self.assertRaises(ValueError):
            projection.require_verified()
        projection = self.project()
        object.__setattr__(projection.values[0], "value", 999.0)
        with self.assertRaises(ValueError):
            projection.require_verified()

    def test_relevant_tie_mapping_and_annual_namespace_conflicts_are_pending(self):
        for name, kwargs, expected in (
            ("tie", {"value": 101.0}, "fact_selection_tie_conflict"),
            ("mapping", {"source_overrides": {"mapping_version": "new-mapping"}}, "fact_mapping_version_conflict"),
            ("basis", {"accounting_basis": "standalone"}, "formula_fact_ambiguous"),
        ):
            with self.subTest(name=name):
                changed = self.add_fact(generation="conflict-" + name, **kwargs)
                self.persist()
                result = self.project()
                self.assertIsNone(result.values[0].value)
                self.assertIn(expected, result.blockers)
                self.sql("DELETE FROM formal_financial_fact WHERE id=?", (changed.id,))

    def test_quarter_accounting_conflict_is_not_dismissed_as_history_shortage(self):
        self.configure({"op": "fact", "fact_key": "revenue", "period_key": "2025Q4"})
        self.only_periods("2025-12-31")
        self.add_fact(report_period="2025-09-30", accounting_basis="standalone", generation="basis-Q3")
        self.persist()
        result = self.project()
        self.assertIsNone(result.values[0].value)
        self.assertIn("quarter_accounting_basis_mismatch", result.blockers)

    def test_after_freeze_fact_cannot_supply_missing_annual_leaf(self):
        self.sql("DELETE FROM formal_financial_fact WHERE period_end='2025-12-31'")
        self.add_fact(generation="future", source_overrides={"source_updated_at_utc": "2026-09-01T00:00:00+00:00"})
        self.persist()
        result = self.project()
        self.assertIsNone(result.values[0].value)
        self.assertEqual(result.values[0].missing_reason, "formula_fact_missing")

    def test_correction_during_provider_build_receipt_or_derivation_rejects(self):
        for index, phase in enumerate(("resolve_current_inputs", "build_formal_feature_bundle",
                "_read_authenticated_bundle", "evaluate_selected_features")):
            with self.subTest(phase=phase):
                self.persist()
                snapshot = self.snapshot()
                fired = False
                def profile(frame, event, arg):
                    nonlocal fired
                    if not fired and event == "return" and frame.f_code.co_name == phase:
                        fired = True
                        self.add_fact(value=200.0 + index, generation="race-" + str(index),
                            source_overrides={"source_updated_at_utc": f"2026-04-{index+1:02d}T00:00:00+00:00"})
                previous = sys.getprofile()
                try:
                    sys.setprofile(profile)
                    with self.assertRaises(ValueError):
                        self.project(snapshot=snapshot)
                finally:
                    sys.setprofile(previous)
                self.assertTrue(fired, "race must occur during actual execution")

    def test_late_provider_mutation_and_receipt_mutation_reject(self):
        for target in ("provider", "receipt", "source"):
            with self.subTest(target=target):
                snapshot = self.snapshot()
                source_path = Path(self.store.get_formal_snapshot(self.fact.source_snapshot_id).content_path)
                original_source = source_path.read_bytes()
                fired = False
                def profile(frame, event, arg):
                    nonlocal fired
                    if not fired and event == "return" and frame.f_code.co_name == "evaluate_selected_features":
                        fired = True
                        if target == "provider":
                            object.__setattr__(snapshot, "batch_id", "changed")
                        elif target == "receipt":
                            self.sql("UPDATE formal_feature_value SET value=999")
                        else:
                            source_path.write_bytes(b"corrupt-after-derivation")
                previous = sys.getprofile()
                try:
                    sys.setprofile(profile)
                    with self.assertRaises(ValueError):
                        self.project(snapshot=snapshot)
                finally:
                    sys.setprofile(previous)
                    self.sql("UPDATE formal_feature_value SET value=100")
                    source_path.write_bytes(original_source)
                self.assertTrue(fired)


if __name__ == "__main__":
    unittest.main()
