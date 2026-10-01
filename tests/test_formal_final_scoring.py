"""Stage D final arithmetic over genuine D1 publications."""

import atexit
import hashlib
import unittest
from decimal import Decimal, localcontext
from unittest.mock import patch

from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
from ashare_pipeline.formal_final_scoring import (
    FinalScoreCard, build_final_score_card_batch,
)
from ashare_pipeline.formal_scoring import (
    _arithmetic_context, _calculate_untrusted_arithmetic,
    _calculate_untrusted_confidence, calculate_pre_policy_score,
)
from tests.formal_final_scoring_fixtures import FinalScoringFixture, FOCAL
from tests import formal_final_scoring_fixtures as fixture_module
from tests.test_formal_scoring_registry import canonical


DIMENSIONS = ("G", "V", "M", "EQ", "FS", "CA", "T")
WEIGHTS = {"G": Decimal("0.18"), "V": Decimal("0.18"), "M": Decimal("0.18"),
           "EQ": Decimal("0.12"), "FS": Decimal("0.08"), "CA": Decimal("0.16"),
           "T": Decimal("0.10")}
RISK_IDS = ("M.return_persistence", "M.margin_persistence",
            "CA.shareholder_return_and_dilution", "CA.capital_discipline")
NO_CAP_PEER = "SH600000"
_SHARED = None


def d1_batch(fixture):
    repository = FormalFinalScoreInputRepository(fixture.feature_repository,
        fixture.context, fixture.range_store, registry_signature_verifier=fixture.verifier)
    return repository.build_batch(fixture.frozen.frozen_input_hash,
        scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry,
        valuation_adapter_registry=fixture.valuation_registry)


def shared_ready_batch():
    global _SHARED
    if _SHARED is None:
        original = fixture_module._stage_d_documents

        def with_two_g_caps(documents):
            original(documents)
            effects = documents["cyclic"]["rules"]["general_nonfinancial_cyclic_top"]["outcomes"]["on_match"]
            effects.append({"kind": "dimension_cap", "dimension": "G", "maximum": "1"})
            effects.sort(key=canonical)

        with patch.object(fixture_module, "_stage_d_documents", with_two_g_caps):
            fixture = FinalScoringFixture(peer_count=23, consensus_no_coverage=True)
        atexit.register(fixture.close)
        fixture.pending_ids = tuple(sorted(set(fixture.templates) - {FOCAL, NO_CAP_PEER}))
        fixture.populate_final_inputs()
        generation = "stage-d-peer-consensus"
        consensus_request = fixture.resolver.resolve(
            context_kind="consensus_snapshot", scope_key="fixture-consensus",
            security_id=NO_CAP_PEER, as_of_utc="2026-08-31T07:00:00+00:00",
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
            upstream_generation=generation)
        fixture.put_context(consensus_request,
            {"coverage_status": "covered", "estimates": [
                {"period": "FY2026", "metric": "profit", "value": 1}]},
            False, generation)
        # The stock D1 fixture gives only FOCAL its five-year score history.
        # Complete the second member through the same producer-backed route.
        for year in range(2021, 2026):
            fixture.put_financial(NO_CAP_PEER, {"history": 1},
                generation=f"stage-d-peer-history-{year}",
                period_end=f"{year}-12-31", publish=False)
        for year in (2024, 2025, 2026):
            for kind, end in (("Q1", "03-31"), ("H1", "06-30"), ("Q3", "09-30")):
                if year == 2026 and kind == "Q3":
                    continue
                fixture.put_financial(NO_CAP_PEER, {"history": 1},
                    generation=f"stage-d-peer-history-{year}-{kind}",
                    period_end=f"{year}-{end}", period_kind=kind, publish=False)
        fixture.publish_current(NO_CAP_PEER)
        fixture.valuation_feature_bundles[NO_CAP_PEER] = fixture.persist_features(NO_CAP_PEER)
        inputs = d1_batch(fixture)
        cards = build_final_score_card_batch(inputs)
        _SHARED = fixture, inputs, cards
    return _SHARED


class FinalScoreArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.inputs, cls.cards = shared_ready_batch()
        cls.row = cls.inputs.input_for(FOCAL)
        cls.card = cls.cards.card_for(FOCAL)

    def test_final_card_rebuilds_all_seven_dimensions_from_final_slots(self):
        card, row = self.card, self.row
        self.assertIsInstance(card, FinalScoreCard)
        self.assertEqual(row.status, "ready")
        self.assertEqual(len(row.slots), 25)
        self.assertEqual(len([s for s in row.slots.values()
            if s["evidence_kind"] == "policy_adjusted_valuation"]), 3)
        with localcontext(_arithmetic_context()):
            for dimension in DIMENSIONS:
                expected = sum((slot["internal_weight"] * slot["value"]
                    for mid, slot in row.slots.items() if mid.startswith(dimension + ".")),
                    Decimal("0"))
                self.assertEqual(card.raw_dimensions[dimension], expected)
        self.assertEqual(tuple(card.raw_dimensions), DIMENSIONS)
        self.assertEqual(tuple(card.dimensions), DIMENSIONS)
        self.assertEqual(card.raw_dimensions["V"], card.dimensions["V"])
        self.assertEqual(card.source_entry_hash, row.entry_hash)
        self.assertEqual(card.source_batch_hash, self.inputs.batch_hash)
        self.assertEqual(card.registry_manifest_hash, row.registry_manifest_hash)
        self.assertEqual(card.policy_result_hash, row.policy_result_hash)
        self.assertEqual(card.base_batch_hash, row.base_batch_hash)
        self.assertEqual(card.valuation_batch_hash, row.valuation_batch_hash)
        self.assertEqual(card.source_canonical_sha256,
            hashlib.sha256(row.canonical_bytes()).hexdigest())
        for mid in ("V.enterprise_value_or_sustainable_roe",
                    "V.normalized_earnings_yield", "V.normalized_free_cash_flow_yield"):
            self.assertEqual(card.source_input["slots"][mid]["valuation_score_hash"],
                row.slots[mid]["valuation_score_hash"])
            self.assertEqual(card.source_input["slots"][mid]["valuation_context_hash"],
                row.slots[mid]["valuation_context_hash"])

    def test_multiple_caps_take_minimum_without_changing_confidence(self):
        card = self.card
        self.assertEqual(card.dimension_caps, {"G": Decimal("1"), "M": Decimal("80")})
        self.assertEqual(sorted(item["effect"]["maximum"] for item in card.cap_trace
            if item["effect"]["dimension"] == "G"), ["1", "80"])
        self.assertGreater(card.raw_dimensions["G"], Decimal("1"))
        for dimension, limit in (("G", "1"), ("M", "80")):
            self.assertEqual(card.dimensions[dimension],
                min(card.raw_dimensions[dimension], Decimal(limit)))
            self.assertTrue(any(item["effect"]["dimension"] == dimension
                and item["rule_id"] and item["definition_hash"] and item["trace"]
                for item in card.cap_trace))
        self.assertEqual(card.confidence,
            _calculate_untrusted_confidence(dict(card.global_slot_weights),
                {mid: self.row.slots[mid]["temporal_quality"]
                    for mid in card.global_slot_weights},
                continuous_fy_count=self.row.continuous_fy_count,
                confidence_cap=Decimal(self.row.confidence_cap)))

    def test_cap_never_raises_a_dimension(self):
        for dimension in DIMENSIONS:
            self.assertLessEqual(self.card.dimensions[dimension],
                self.card.raw_dimensions[dimension])
            if dimension not in self.card.dimension_caps:
                self.assertEqual(self.card.dimensions[dimension],
                    self.card.raw_dimensions[dimension])

    def test_exact_sc_b_risk_and_grades_use_unrounded_decimal(self):
        card = self.card
        with localcontext(_arithmetic_context()):
            expected_s0 = sum((WEIGHTS[d] * card.dimensions[d] for d in DIMENSIONS), Decimal("0"))
            expected_sc = Decimal("50") + card.confidence["C"] * (expected_s0 - Decimal("50"))
            expected_sbase = sum((WEIGHTS[d] * card.dimensions[d] for d in DIMENSIONS[:-1]),
                Decimal("0")) / Decimal("0.90")
            expected_b = Decimal("50") + card.confidence["C"] * (expected_sbase - Decimal("50"))
        self.assertEqual((card.S0, card.Sc, card.Sbase, card.B),
            (expected_s0, expected_sc, expected_sbase, expected_b))
        risk = {mid: self.row.slots[mid]["value"] for mid in RISK_IDS}
        expected = _calculate_untrusted_arithmetic(dimensions=dict(card.dimensions),
            confidence=card.confidence["C"], metric_values=risk)
        for key in ("M_persistence", "CA_downside", "R_safety", "risk_exposure"):
            self.assertEqual(getattr(card, key), expected[key])
        for key in (*DIMENSIONS, "S0", "Sc", "Sbase", "B", "M_persistence",
                    "CA_downside", "R_safety"):
            score = card.dimensions[key] if key in DIMENSIONS else getattr(card, key)
            grade = card.dimension_grades[key] if key in DIMENSIONS else getattr(card, key + "_grade")
            if score >= 90:
                expected_grade = "A+"
            elif score >= 80:
                expected_grade = "A"
            elif score >= 70:
                expected_grade = "B"
            elif score >= 60:
                expected_grade = "C"
            elif score >= 50:
                expected_grade = "D"
            else:
                expected_grade = "E"
            self.assertEqual(grade, expected_grade)

    def test_pending_input_has_no_card_and_preserves_all_reasons(self):
        for sid in self.inputs.security_ids:
            row = self.inputs.input_for(sid)
            if row.status == "pending_evidence":
                self.assertIsNone(self.cards.card_for(sid))
                pending = self.cards.pending_for(sid)
                self.assertEqual(pending["reasons"], row.reasons)
                self.assertEqual(pending["base_pending_reasons"], row.base_pending_reasons)
                self.assertEqual(pending["policy_pending_requirements"],
                    row.policy_pending_requirements)
                self.assertEqual(pending["valuation_pending_reasons"],
                    row.valuation_pending_reasons)
                self.assertEqual(pending["source_entry_hash"], row.entry_hash)

    def test_no_cap_parity_matches_existing_arithmetic_but_not_proof_type(self):
        # A second ready member in the same signed batch has no cyclic cap.
        row = self.inputs.input_for(NO_CAP_PEER)
        self.assertEqual(row.status, "ready")
        card = self.cards.card_for(NO_CAP_PEER)
        self.assertEqual(card.dimension_caps, {})
        self.assertEqual(card.raw_dimensions, card.dimensions)
        expected = _calculate_untrusted_arithmetic(dimensions=dict(card.dimensions),
            confidence=card.confidence["C"],
            metric_values={mid: row.slots[mid]["value"] for mid in RISK_IDS})
        for key, value in expected.items():
            self.assertEqual(getattr(card, key), value)
        self.assertNotEqual(type(card), type(calculate_pre_policy_score(
            self.fixture.base_repository.build_batch(self.fixture.frozen.frozen_input_hash,
                scoring_registry=self.fixture.scoring).input_for(NO_CAP_PEER))))

    def test_verified_no_consensus_caps_confidence_at_point_90(self):
        row = self.row
        self.assertEqual(row.status, "ready")
        card = self.card
        self.assertEqual(row.confidence_cap, "0.90")
        self.assertEqual(card.confidence["C"], Decimal("0.90"))


if __name__ == "__main__":
    unittest.main()
