"""Authenticated pre-policy score arithmetic and provenance boundary tests."""

import importlib
import importlib.util
import copy
import gc
import hashlib
import sys
import unittest
import weakref
from dataclasses import replace
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from tests.formal_score_input_fixtures import FOCAL, ScoreFixture


class PureScoringArithmeticTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_scoring"),
            "pre-policy scoring must be owned by a distinct module")
        return importlib.import_module("ashare_pipeline.formal_scoring")

    def test_grade_boundaries_use_unrounded_finite_decimals(self):
        grade = self.api().grade_for_score
        cases = (
            ("100", "A+"), ("90", "A+"), ("89.999999999999999999999999999999999999999999999999", "A"),
            ("80", "A"), ("79.999999999999999999999999999999999999999999999999", "B"),
            ("70", "B"), ("69.999999999999999999999999999999999999999999999999", "C"),
            ("60", "C"), ("59.999999999999999999999999999999999999999999999999", "D"),
            ("50", "D"), ("49.999999999999999999999999999999999999999999999999", "E"), ("0", "E"),
        )
        for score, expected in cases:
            with self.subTest(score=score):
                self.assertEqual(grade(Decimal(score)), expected)
        for invalid in (-1, 0.0, True, None, Decimal("-0.0001"), Decimal("100.0001"),
                        Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                grade(invalid)

    def test_hand_example_preserves_specified_intermediate_divisions(self):
        arithmetic = self.api()._calculate_untrusted_arithmetic(
            dimensions={key: Decimal(value) for key, value in {
                "G": "80", "V": "70", "M": "60", "EQ": "50", "FS": "40", "CA": "90", "T": "30",
            }.items()},
            confidence=Decimal("1"),
            metric_values={
                "M.return_persistence": Decimal("70"),
                "M.margin_persistence": Decimal("50"),
                "CA.shareholder_return_and_dilution": Decimal("60"),
                "CA.capital_discipline": Decimal("80"),
            },
        )
        self.assertEqual(arithmetic, {
            "S0": Decimal("64.40"),
            "Sc": Decimal("64.40"),
            "Sbase": Decimal("68.222222222222222222222222222222222222222222222222"),
            "B": Decimal("68.222222222222222222222222222222222222222222222222"),
            "M_persistence": Decimal("61.428571428571428571428571428571428571428571428571"),
            "CA_downside": Decimal("68.571428571428571428571428571428571428571428571429"),
            "R_safety": Decimal("51.071428571428571428571428571428571428571428571428"),
            "risk_exposure": Decimal("48.928571428571428571428571428571428571428571428572"),
        })

    def test_confidence_uses_weighted_quality_history_and_cap_in_that_order(self):
        confidence = getattr(self.api(), "_calculate_untrusted_confidence", None)
        self.assertTrue(callable(confidence), "confidence arithmetic helper is missing")
        cases = (
            ({"all": Decimal("1")}, {"all": Decimal("0.8")}, 4, None, "0.8", "0.8", "0.96"),
            ({"all": Decimal("1")}, {"all": Decimal("1")}, 4, None, "1", "0.8", "0.98"),
            ({"all": Decimal("1")}, {"all": Decimal("0.8")}, 5, None, "0.8", "1", "0.98"),
            ({"all": Decimal("1")}, {"all": Decimal("1")}, 5, None, "1", "1", "1.00"),
            ({"expectation": Decimal("0.025"), "other": Decimal("0.975")},
                {"expectation": Decimal("0.8"), "other": Decimal("1")}, 4, Decimal("0.90"),
                "0.9950", "0.8", "0.90"),
        )
        for weights, qualities, years, cap, expected_p, expected_h, expected_c in cases:
            with self.subTest(years=years, quality=expected_p, cap=cap):
                self.assertEqual(confidence(weights, qualities, continuous_fy_count=years, confidence_cap=cap), {
                    "D": Decimal("1"), "P": Decimal(expected_p), "H": Decimal(expected_h),
                    "K": Decimal("1"), "C": Decimal(expected_c),
                })

    def test_pure_arithmetic_ignores_hostile_ambient_decimal_context(self):
        api = self.api()
        confidence = getattr(api, "_calculate_untrusted_confidence", None)
        self.assertTrue(callable(confidence), "confidence arithmetic helper is missing")
        with localcontext(Context(prec=2)):
            result = api._calculate_untrusted_arithmetic(
                dimensions={key: Decimal(value) for key, value in {
                    "G": "80", "V": "70", "M": "60", "EQ": "50", "FS": "40", "CA": "90", "T": "30",
                }.items()},
                confidence=Decimal("1"),
                metric_values={
                    "M.return_persistence": Decimal("70"), "M.margin_persistence": Decimal("50"),
                    "CA.shareholder_return_and_dilution": Decimal("60"), "CA.capital_discipline": Decimal("80"),
                })
            capped = confidence(
                {"expectation": Decimal("0.025"), "other": Decimal("0.975")},
                {"expectation": Decimal("0.8"), "other": Decimal("1")},
                continuous_fy_count=4, confidence_cap=Decimal("0.90"))
        self.assertEqual(result["risk_exposure"],
            Decimal("48.928571428571428571428571428571428571428571428572"))
        self.assertEqual(capped["P"], Decimal("0.9950"))
        self.assertEqual(capped["C"], Decimal("0.90"))

    def test_raw_helpers_reject_partial_reweighted_or_ambiguous_inputs(self):
        api = self.api()
        dimensions = {key: Decimal("50") for key in ("G", "V", "M", "EQ", "FS", "CA", "T")}
        risk = {key: Decimal("50") for key in (
            "M.return_persistence", "M.margin_persistence",
            "CA.shareholder_return_and_dilution", "CA.capital_discipline")}
        bad_dimensions = dict(dimensions)
        bad_dimensions.pop("T")
        wrong_risk = dict(risk)
        wrong_risk["CA.return_persistence"] = wrong_risk.pop("M.return_persistence")
        for candidate_dimensions, candidate_risk, candidate_confidence in (
                (bad_dimensions, risk, Decimal("1")), (dimensions, wrong_risk, Decimal("1")),
                (dict(dimensions, G=50.0), risk, Decimal("1")), (dimensions, risk, Decimal("NaN"))):
            with self.assertRaises(ValueError):
                api._calculate_untrusted_arithmetic(dimensions=candidate_dimensions,
                    confidence=candidate_confidence, metric_values=candidate_risk)
        for weights, qualities, years, cap in (
                ({"a": Decimal("0.5")}, {"a": Decimal("1")}, 4, None),
                ({"a": Decimal("1")}, {"b": Decimal("1")}, 4, None),
                ({"a": Decimal("1")}, {"a": Decimal("1")}, 3, None),
                ({"a": Decimal("1")}, {"a": Decimal("1")}, 4, True)):
            with self.assertRaises(ValueError):
                api._calculate_untrusted_confidence(weights, qualities,
                    continuous_fy_count=years, confidence_cap=cap)


class ProofDispatchGuardTests(unittest.TestCase):
    def api(self):
        return importlib.import_module("ashare_pipeline.formal_scoring")

    def test_class_descriptor_cannot_shadow_forged_field_rejection(self):
        api = self.api()
        forged = object.__new__(api.PrePolicyScoreCalculation)
        with self.assertRaisesRegex(ValueError, "forged, copied or unregistered"):
            _ = forged.S0
        with patch.object(api.PrePolicyScoreCalculation, "S0",
                property(lambda self: Decimal("99")), create=True):
            with self.assertRaises(ValueError):
                _ = forged.S0
        with self.assertRaisesRegex(ValueError, "forged, copied or unregistered"):
            _ = forged.S0

    def test_replaced_verification_method_cannot_bypass_forged_rejection(self):
        api = self.api()
        forged = object.__new__(api.PrePolicyScoreCalculation)
        with self.assertRaisesRegex(ValueError, "forged, copied or unregistered"):
            forged.require_verified()
        with patch.object(api.PrePolicyScoreCalculation, "require_verified",
                lambda self: True, create=True):
            with self.assertRaises(ValueError):
                forged.require_verified()
        with self.assertRaisesRegex(ValueError, "forged, copied or unregistered"):
            forged.require_verified()

    def test_module_export_class_replacement_is_detected_then_restores_normal_rejection(self):
        api = self.api()
        proof_type = api.PrePolicyScoreCalculation
        forged = object.__new__(proof_type)
        inherited_verify = proof_type.__mro__[1].require_verified
        with patch.object(api, "PrePolicyScoreCalculation", object):
            with self.assertRaisesRegex(ValueError, "calculation dependency changed"):
                inherited_verify(forged)
        with self.assertRaisesRegex(ValueError, "forged, copied or unregistered"):
            inherited_verify(forged)

    def test_attribute_resolution_guard_itself_cannot_be_replaced(self):
        api = self.api()
        proof_type = api.PrePolicyScoreCalculation
        for owner in (proof_type, proof_type.__mro__[1]):
            replacement = patch.object(owner, "__getattribute__",
                lambda self, name: Decimal("99"), create=True)
            try:
                with self.subTest(owner=owner.__name__), self.assertRaises(TypeError):
                    replacement.start()
            finally:
                replacement.stop()
        forged = object.__new__(proof_type)
        with self.assertRaisesRegex(ValueError, "forged, copied or unregistered"):
            _ = forged.S0

    def test_attribute_resolution_guard_cannot_be_removed_by_replacing_inheritance(self):
        api = self.api()
        proof_type = api.PrePolicyScoreCalculation
        forged = object.__new__(proof_type)
        original_bases = proof_type.__bases__

        class AlternateBase:
            __slots__ = ("__weakref__",)

            def __getattribute__(self, name):
                return Decimal("99")

        try:
            with self.assertRaises(TypeError):
                proof_type.__bases__ = (AlternateBase,)
        finally:
            if proof_type.__bases__ != original_bases:
                proof_type.__bases__ = original_bases
        with self.assertRaisesRegex(ValueError, "forged, copied or unregistered"):
            _ = forged.S0


class AuthenticatedPrePolicyScoringTests(unittest.TestCase):
    def api(self):
        return importlib.import_module("ashare_pipeline.formal_scoring")

    def build_input(self, fixture):
        from ashare_pipeline.formal_score_inputs import FormalScoreInputRepository
        repository = FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        batch = repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        return batch, batch.input_for(FOCAL)

    def test_default_linked_covered_input_mints_distinct_immutable_pre_policy_audit(self):
        api = self.api()
        calculate = getattr(api, "calculate_pre_policy_score", None)
        proof_type = getattr(api, "PrePolicyScoreCalculation", None)
        self.assertTrue(callable(calculate), "authenticated pre-policy entry point is missing")
        self.assertIsInstance(proof_type, type, "sealed pre-policy result type is missing")
        fixture = ScoreFixture()
        self.addCleanup(fixture.close)
        fixture.populate_scores(consensus="covered")
        batch, source = self.build_input(fixture)
        self.assertEqual(source.consensus_context["value"]["coverage_status"], "covered")
        self.assertIsNone(source.confidence_cap)

        result = calculate(source)
        duplicate = calculate(source)
        self.assertIs(type(result), proof_type)
        self.assertEqual(result.schema_version, "formal-pre-policy-score-v1")
        self.assertEqual(result.calculation_stage, "pre_policy")
        self.assertIs(result.policy_final, False)
        self.assertFalse(hasattr(api, "FormalScoreCard"))
        self.assertEqual(tuple(result.dimensions), ("G", "V", "M", "EQ", "FS", "CA", "T"))
        self.assertEqual(len(result.global_slot_weights), 25)
        self.assertEqual(result.confidence,
            {"D": Decimal("1.0000"), "P": Decimal("1.0000"), "H": Decimal("0.8"),
             "K": Decimal("1"), "C": Decimal("0.980000")})
        self.assertEqual(tuple(result.dimension_grades), tuple(result.dimensions))
        for name in ("S0", "Sc", "Sbase", "B", "M_persistence", "CA_downside", "R_safety", "risk_exposure"):
            self.assertIsInstance(getattr(result, name), Decimal)
        for name in ("S0_grade", "Sc_grade", "Sbase_grade", "B_grade",
                "M_persistence_grade", "CA_downside_grade", "R_safety_grade"):
            self.assertIn(getattr(result, name), ("A+", "A", "B", "C", "D", "E"))
        self.assertNotIn("risk_exposure_grade", result.to_dict())
        self.assertNotIn("confidence_grade", result.to_dict())
        self.assertEqual(result.input_hash, source.input_hash)
        self.assertEqual(result.batch_hash, source.batch_hash)
        self.assertEqual(result.metric_batch_hash, source.metric_batch_hash)
        self.assertEqual(result.registry_manifest_hash, source.registry_manifest_hash)
        self.assertEqual(result.registry_hashes, source.registry_hashes)
        self.assertEqual(result.frozen_input_hash, source.frozen_input_hash)
        self.assertEqual(result.universe_hash, source.universe_hash)
        self.assertEqual(result.population_hash, source.population_hash)
        self.assertEqual(result.security_id, FOCAL)
        self.assertEqual(result.template_id, source.template_id)
        self.assertEqual(result.as_of_utc, source.as_of_utc)
        self.assertEqual(result.to_dict()["source_input"], source.to_dict())
        self.assertEqual(result.source_canonical_sha256, hashlib.sha256(source.canonical_bytes()).hexdigest())
        self.assertEqual(result.canonical_bytes(), duplicate.canonical_bytes())
        self.assertEqual(result.calculation_hash, duplicate.calculation_hash)
        fixed = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
            capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])
        with localcontext(fixed):
            expected_m = (Decimal("0.40") * source.slots["M.return_persistence"]["value"]
                + Decimal("0.30") * source.slots["M.margin_persistence"]["value"]) / Decimal("0.70")
            expected_ca = (Decimal("0.20") * source.slots["CA.shareholder_return_and_dilution"]["value"]
                + Decimal("0.15") * source.slots["CA.capital_discipline"]["value"]) / Decimal("0.35")
        self.assertEqual(result.M_persistence, expected_m)
        self.assertEqual(result.CA_downside, expected_ca)
        self.assertIsInstance(result.dimensions, MappingProxyType)
        with self.assertRaises(TypeError):
            result.dimensions["G"] = Decimal("0")
        detached = result.to_dict()
        detached["dimensions"].clear()
        self.assertEqual(len(result.dimensions), 7)
        with self.assertRaises(TypeError):
            copy.copy(result)
        with self.assertRaises(TypeError):
            copy.deepcopy(result)
        with self.assertRaises(TypeError):
            proof_type()
        forged = object.__new__(proof_type)
        for method in ("require_verified", "canonical_bytes", "to_dict"):
            with self.subTest(method=method), self.assertRaises(ValueError):
                getattr(forged, method)()
        for invalid in ({}, source.to_dict(), result.to_dict(), batch, None,
                SimpleNamespace(require_verified=lambda: None)):
            with self.subTest(invalid=type(invalid).__name__), self.assertRaises((TypeError, ValueError)):
                calculate(invalid)
        class DerivedInput(type(source)):
            __slots__ = ()
        with self.assertRaises(ValueError):
            calculate(object.__new__(DerivedInput))
        with self.assertRaises(TypeError):
            calculate(source, confidence=Decimal("1"))

        from ashare_pipeline import formal_score_inputs as input_api
        source_base = type(source).__mro__[1]
        expected_S0 = result.S0
        with patch.object(proof_type, "S0", property(lambda self: Decimal("99")), create=True):
            with self.assertRaises(ValueError):
                _ = result.S0
        self.assertEqual(result.S0, expected_S0)
        with patch.object(proof_type, "require_verified", lambda self: True, create=True):
            with self.assertRaises(ValueError):
                result.require_verified()
        result.require_verified()
        for owner, name in ((api, "_arithmetic_context"), (api, "_finite_decimal"),
                (api, "_calculate_untrusted_arithmetic"), (api, "_calculate_untrusted_confidence"),
                (api, "_plain"), (api, "_canonical"), (api, "_digest"), (api, "_freeze"), (api, "grade_for_score"),
                (api, "Decimal"), (api, "localcontext"), (api, "_DIMENSION_WEIGHTS"),
                (api, "_RISK_METRIC_IDS"), (api, "_DIMENSION_SLOT_COUNTS"),
                (api, "MappingProxyType"), (api, "Context"), (api, "ROUND_HALF_EVEN"),
                (api, "json"), (api, "hashlib"), (api, "weakref"),
                (api.json, "loads"), (api.json, "dumps"), (hashlib, "sha256"),
                (api.weakref, "ref"), (api, "score_input_module"), (api, "FormalScoreInput"),
                (input_api, "FormalScoreInput"),
                (source_base, "require_verified"), (source_base, "canonical_bytes"),
                (source_base, "to_dict"), (source_base, "__getattr__"),
                (proof_type, "canonical_bytes"), (api, "PrePolicyScoreCalculation")):
            with self.subTest(owner=getattr(owner, "__name__", repr(owner)), name=name), \
                    patch.object(owner, name, lambda *args, **kwargs: None), self.assertRaises(ValueError):
                result.require_verified()
            result.require_verified()

        source_owner = weakref.ref(source)
        expected = result.canonical_bytes()
        del duplicate, batch, source
        gc.collect()
        self.assertIsNotNone(source_owner())
        self.assertEqual(result.canonical_bytes(), expected)

    def test_revoked_tentative_source_revokes_cyclic_date_only_neutral_descendant(self):
        api = self.api()
        from ashare_pipeline import formal_score_inputs as input_api
        fixture = ScoreFixture(cyclic=True, date_only=True)
        self.addCleanup(fixture.close)
        fixture.populate_scores(five_years=True, consensus="none")
        repository = input_api.FormalScoreInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        snapshot = fixture.provider.resolve_current_inputs(security_id=FOCAL,
            as_of_utc="2026-08-31T07:00:00+00:00", template_id="general_nonfinancial",
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash)
        captured = []

        def profile(frame, event, value):
            if (event == "return" and frame.f_code.co_name == "publish_complete"
                    and type(value) is input_api.FormalScoreInputBatch and not captured):
                source = value.input_for(FOCAL)
                result = api.calculate_pre_policy_score(source)
                self.assertEqual(result.confidence,
                    {"D": Decimal("1.0000"), "P": Decimal("0.99500"), "H": Decimal("1"),
                     "K": Decimal("1"), "C": Decimal("0.90")})
                self.assertTrue(source.cyclic)
                self.assertEqual(result.calculation_stage, "pre_policy")
                self.assertIs(result.policy_final, False)
                self.assertNotIn("risk_exposure_grade", result.to_dict())
                captured.append(result)
                with self.assertRaises(ValueError):
                    fixture.provider.publish(replace(snapshot, batch_id="pre-policy-source-revocation"))

        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(ValueError, "changed during complete batch finalization"):
                repository.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        finally:
            sys.setprofile(previous)
        self.assertEqual(len(captured), 1)
        for operation in (lambda: captured[0].require_verified(), lambda: captured[0].canonical_bytes(),
                lambda: captured[0].to_dict(), lambda: captured[0].risk_exposure):
            with self.assertRaises(ValueError):
                operation()


if __name__ == "__main__":
    unittest.main()
