"""Final-card proof and numeric boundary guards over a real D1 publication."""

import copy
import inspect
import pickle
import unittest
from decimal import Context, Decimal, localcontext
from unittest.mock import patch

from ashare_pipeline.formal_final_score_inputs import PolicyAdjustedScoreInputBatch
from ashare_pipeline.formal_final_scoring import (
    FinalScoreCard, FinalScoreCardBatch, _calculate_untrusted_final,
    build_final_score_card_batch,
)
from ashare_pipeline.formal_scoring import calculate_pre_policy_score
from tests.formal_final_scoring_fixtures import FOCAL
from tests.test_formal_final_scoring import d1_batch, shared_ready_batch


class FinalScoringGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.inputs, cls.cards = shared_ready_batch()
        cls.row = cls.inputs.input_for(FOCAL)
        cls.card = cls.cards.card_for(FOCAL)

    def test_plain_dict_and_pre_policy_calculation_cannot_create_final_proof(self):
        with self.assertRaises(ValueError):
            build_final_score_card_batch(self.inputs.to_dict())
        base = self.fixture.base_repository.build_batch(
            self.fixture.frozen.frozen_input_hash, scoring_registry=self.fixture.scoring)
        pre_policy = calculate_pre_policy_score(base.input_for(FOCAL))
        with self.assertRaises(ValueError):
            build_final_score_card_batch(pre_policy)
        with self.assertRaises(TypeError):
            FinalScoreCard()
        with self.assertRaises(TypeError):
            FinalScoreCardBatch()

    def test_cross_batch_or_unknown_selector_cannot_launder_a_card(self):
        other = d1_batch(self.fixture)
        self.assertIsNot(other, self.inputs)
        self.assertEqual(other.batch_hash, self.inputs.batch_hash)
        with self.assertRaises(ValueError):
            build_final_score_card_batch((self.inputs, other))
        with self.assertRaises(ValueError):
            self.cards.card_for("SH999999")
        with self.assertRaises(ValueError):
            self.cards.pending_for("SH999999")
        self.assertEqual(self.cards.card_for(FOCAL).source_batch_hash, self.inputs.batch_hash)
        self.assertIsNone(self.cards.pending_for(FOCAL))

    def test_unknown_cap_dimension_and_summary_disagreement_are_rejected(self):
        wire = self.row.to_dict()
        wire["policy_result"]["dimension_caps"]["UNKNOWN"] = "70"
        with self.assertRaises(ValueError):
            _calculate_untrusted_final(wire)
        wire = self.row.to_dict()
        wire["policy_result"]["dimension_caps"]["G"] = "79"
        with self.assertRaises(ValueError):
            _calculate_untrusted_final(wire)

    def test_nonnumeric_slot_values_and_invalid_caps_are_rejected(self):
        mid = "V.normalized_earnings_yield"
        for value in (True, 5, 5.0, None, "NaN", "Infinity", "-Infinity",
                      "1e999999999999999999", "1e-999999"):
            with self.subTest(slot=value):
                wire = self.row.to_dict()
                wire["slots"][mid]["value"] = value
                with self.assertRaises(ValueError):
                    _calculate_untrusted_final(wire)
        for value in (True, 5, 5.0, None, "NaN", "Infinity", "-Infinity",
                      "1e999999999999999999", "1e-999999"):
            with self.subTest(cap=value):
                wire = self.row.to_dict()
                wire["policy_result"]["dimension_caps"]["G"] = value
                with self.assertRaises(ValueError):
                    _calculate_untrusted_final(wire)

    def test_global_decimal_context_cannot_round_or_raise_in_final_arithmetic(self):
        baseline = self.card.canonical_bytes()
        with localcontext(Context(prec=2)):
            hostile = build_final_score_card_batch(self.inputs).card_for(FOCAL)
        self.assertEqual(hostile.canonical_bytes(), baseline)
        self.assertEqual(hostile.Sc, self.card.Sc)
        self.assertEqual(hostile.risk_exposure, self.card.risk_exposure)

    def test_cards_cannot_be_copied_pickled_or_reconstructed(self):
        for proof in (self.card, self.cards):
            with self.subTest(proof=type(proof).__name__):
                with self.assertRaises(TypeError):
                    copy.copy(proof)
                with self.assertRaises(TypeError):
                    copy.deepcopy(proof)
                with self.assertRaises(TypeError):
                    pickle.dumps(proof)
                with self.assertRaises(ValueError):
                    object.__new__(type(proof)).require_verified()

    def test_method_replacement_and_module_helper_rebinding_are_detected(self):
        import ashare_pipeline.formal_final_scoring as module
        with self.assertRaises(TypeError):
            with patch.object(FinalScoreCard, "require_verified", lambda self: None):
                pass
        original = module._calculate_untrusted_arithmetic
        with patch.object(module, "_calculate_untrusted_arithmetic", lambda **kwargs: {}):
            with self.assertRaises(ValueError):
                build_final_score_card_batch(self.inputs)
            with self.assertRaises(ValueError):
                self.card.require_verified()
        self.assertIs(module._calculate_untrusted_arithmetic, original)
        self.card.require_verified()

    def test_revoked_d1_publication_revokes_descendant_on_access(self):
        record = inspect.getclosurevars(
            PolicyAdjustedScoreInputBatch.input_for).nonlocals["record"]
        proofs = inspect.getclosurevars(record).nonlocals["proofs"]
        publication = proofs[id(self.inputs)][4]
        self.assertTrue(publication[0])
        publication[0] = False
        try:
            with self.assertRaises(ValueError):
                build_final_score_card_batch(self.inputs)
            with self.assertRaises(ValueError):
                self.card.require_verified()
        finally:
            publication[0] = True
        self.card.require_verified()


if __name__ == "__main__":
    unittest.main()
