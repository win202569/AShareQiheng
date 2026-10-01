"""D3b accepts only matching, complete genuine Stage D proof chains."""

import copy
import unittest

from ashare_pipeline.formal_final_eligibility import (
    FormalEligibility, FormalEligibilityBatch, _validate_scorecard_coverage,
    build_formal_eligibility_batch,
)
from ashare_pipeline.formal_scoring import calculate_pre_policy_score
from tests.test_formal_final_scoring import d1_batch, shared_ready_batch, NO_CAP_PEER


class PureEligibilityGuardTests(unittest.TestCase):
    def test_plain_values_cannot_enter_public_builder(self):
        for inputs, scores in (({}, {}), ([], []), (None, None)):
            with self.subTest(types=(type(inputs), type(scores))):
                with self.assertRaises(ValueError):
                    build_formal_eligibility_batch(inputs, scores)

    def test_proof_classes_cannot_be_constructed_or_forged(self):
        with self.assertRaises(TypeError):
            FormalEligibility(state="out_of_scope")
        with self.assertRaises(TypeError):
            FormalEligibilityBatch()
        forged = object.__new__(FormalEligibility)
        with self.assertRaises(ValueError):
            forged.require_verified()


class FormalEligibilityGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.inputs, cls.cards = shared_ready_batch()

    def test_mismatched_d1_d2_batches_are_rejected(self):
        other_inputs = d1_batch(self.fixture)
        self.assertEqual(other_inputs.batch_hash, self.inputs.batch_hash)
        self.assertIsNot(other_inputs, self.inputs)
        with self.assertRaises(ValueError):
            build_formal_eligibility_batch(other_inputs, self.cards)

    def test_missing_duplicate_or_extra_scorecards_are_rejected(self):
        genuine = self.cards.to_dict()
        ids = self.inputs.security_ids
        _validate_scorecard_coverage(ids, genuine)
        for variant in ("missing", "duplicate", "extra"):
            with self.subTest(variant=variant):
                wire = copy.deepcopy(genuine)
                if variant == "missing":
                    wire["cards"] = [c for c in wire["cards"]
                        if c["security_id"] != NO_CAP_PEER]
                elif variant == "duplicate":
                    wire["cards"].append(copy.deepcopy(wire["cards"][0]))
                else:
                    wire["cards"].append(dict(wire["cards"][0], security_id="SH999999"))
                with self.assertRaises(ValueError):
                    _validate_scorecard_coverage(ids, wire)

    def test_caller_cannot_forge_out_of_scope_state(self):
        with self.assertRaises(TypeError):
            FormalEligibility(state="out_of_scope")
        with self.assertRaises(TypeError):
            FormalEligibilityBatch()
        batch = build_formal_eligibility_batch(self.inputs, self.cards)
        with self.assertRaises((AttributeError, TypeError)):
            batch.eligibility_for(NO_CAP_PEER).state = "out_of_scope"

    def test_plain_mapping_or_prepolicy_score_cannot_enter_eligibility(self):
        base = self.fixture.base_repository.build_batch(
            self.fixture.frozen.frozen_input_hash, scoring_registry=self.fixture.scoring)
        pre_policy = calculate_pre_policy_score(base.input_for(NO_CAP_PEER))
        for a, b in ((self.inputs.to_dict(), self.cards),
                     (self.inputs, self.cards.to_dict()),
                     (self.inputs, pre_policy)):
            with self.subTest(types=(type(a), type(b))):
                with self.assertRaises(ValueError):
                    build_formal_eligibility_batch(a, b)


if __name__ == "__main__":
    unittest.main()
