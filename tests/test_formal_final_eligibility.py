"""D3b state and threshold behavior over genuine D1 and D2 publications."""

import unittest
import inspect
import sys
from decimal import Decimal

from ashare_pipeline.formal_final_eligibility import (
    _state_for, _threshold_breakdown, build_formal_eligibility_batch,
)
from ashare_pipeline.formal_final_score_inputs import PolicyAdjustedScoreInputBatch
from ashare_pipeline.formal_final_scoring import (
    FinalScoreCardBatch, build_final_score_card_batch,
)
from tests.formal_final_scoring_fixtures import FinalScoringFixture
from tests.test_formal_final_scoring import d1_batch
from tests.test_formal_final_scoring import shared_ready_batch, NO_CAP_PEER


class PureEligibilityRulesTests(unittest.TestCase):
    def test_out_of_scope_precedes_pending_and_veto(self):
        self.assertEqual(_state_for(True, True, True, True, out_of_scope=True),
            "out_of_scope")

    def test_hard_veto_or_both_prohibition_yields_pool_vetoed(self):
        self.assertEqual(_state_for(False, True, False, False), "pool_vetoed")
        self.assertEqual(_state_for(False, False, True, True), "pool_vetoed")
        self.assertEqual(_state_for(True, True, True, True), "pending_evidence")
        self.assertEqual(_state_for(False, False, True, False), "formal_scored")

    def test_threshold_equalities_are_inclusive_except_wait_t_is_strictly_below_55(self):
        values = dict(Sc=Decimal("70"), B=Decimal("65"), C=Decimal(".75"),
            M=Decimal("45"), EQ=Decimal("45"), FS=Decimal("45"), T=Decimal("55"))
        gates = _threshold_breakdown(**values)
        self.assertTrue(all(gates["strong"].values()))
        self.assertFalse(gates["wait"]["T"])
        values["T"] = Decimal("55").next_minus()
        gates = _threshold_breakdown(**values)
        self.assertTrue(all(gates["wait"].values()))
        self.assertFalse(gates["strong"]["T"])

    def test_each_threshold_uses_unrounded_decimal_at_both_adjacent_values(self):
        thresholds = {"Sc": Decimal("70"), "B": Decimal("65"),
            "C": Decimal(".75"), "M": Decimal("45"),
            "EQ": Decimal("45"), "FS": Decimal("45"), "T": Decimal("55")}
        for name, boundary in thresholds.items():
            for adjacent, expected in ((boundary.next_minus(), False),
                                       (boundary, True), (boundary.next_plus(), True)):
                with self.subTest(name=name, adjacent=adjacent):
                    values = dict(thresholds, **{name: adjacent})
                    gates = _threshold_breakdown(**values)
                    pool = "wait" if name == "B" else "strong"
                    self.assertIs(gates[pool][name], expected)
            if name == "T":
                for adjacent, expected in ((boundary.next_minus(), True),
                                           (boundary, False), (boundary.next_plus(), False)):
                    values = dict(thresholds, T=adjacent)
                    self.assertIs(_threshold_breakdown(**values)["wait"]["T"], expected)


class FormalEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.inputs, cls.cards = shared_ready_batch()
        cls.batch = build_formal_eligibility_batch(cls.inputs, cls.cards)

    def test_pending_precedes_known_veto_and_emits_no_score_eligibility(self):
        self.assertEqual(_state_for(True, True, True, True, out_of_scope=True),
            "out_of_scope")
        self.assertEqual(_state_for(True, True, True, True), "pending_evidence")
        for sid in self.inputs.security_ids:
            row = self.inputs.input_for(sid)
            if row.status != "pending_evidence":
                continue
            item = self.batch.eligibility_for(sid)
            self.assertEqual(item.state, "pending_evidence")
            self.assertFalse(item.strong_qualified)
            self.assertFalse(item.wait_qualified)
            self.assertEqual(item.pending_reasons, row.reasons)

    def test_pending_has_no_card_hash_or_sort_fields_but_remains_not_qualified_traceable(self):
        sid = next(s for s in self.inputs.security_ids
            if self.inputs.input_for(s).status == "pending_evidence")
        item = self.batch.eligibility_for(sid)
        self.assertIsNone(item.card_hash)
        self.assertIsNone(item.sort_fields)
        self.assertEqual(item.source_entry_hash, self.inputs.input_for(sid).entry_hash)
        self.assertTrue(item.reason_codes)

    def test_single_pool_prohibition_only_blocks_that_pool(self):
        found = False
        for sid in self.inputs.security_ids:
            item = self.batch.eligibility_for(sid)
            if item.state == "formal_scored" and item.strong_prohibited != item.wait_prohibited:
                found = True
                self.assertFalse(item.hard_veto)
                self.assertFalse(item.strong_qualified if item.strong_prohibited
                    else item.wait_qualified)
        self.assertTrue(found)

    def test_sort_fields_and_industry_are_bound_to_exact_d1_d2_hashes(self):
        sid = NO_CAP_PEER
        item = self.batch.eligibility_for(sid)
        row, card = self.inputs.input_for(sid), self.cards.card_for(sid)
        self.assertEqual(item.source_entry_hash, row.entry_hash)
        self.assertEqual(item.card_hash, card.card_hash)
        self.assertEqual(item.secondary_industry, row.secondary_industry)
        self.assertEqual(item.sort_fields, {"Sc": card.Sc, "C": card.confidence["C"],
            "R_safety": card.R_safety, "B": card.B, "V": card.dimensions["V"]})

    def test_each_frozen_member_has_exactly_one_state_and_complete_threshold_trace(self):
        self.assertEqual(self.batch.security_ids, self.inputs.security_ids)
        self.assertEqual(len(self.batch.eligibilities), len(self.inputs.security_ids))
        for sid in self.inputs.security_ids:
            item = self.batch.eligibility_for(sid)
            self.assertIn(item.state, {"out_of_scope", "pending_evidence",
                "pool_vetoed", "formal_scored"})
            self.assertEqual(set(item.thresholds), {"strong", "wait"})
            self.assertEqual(set(item.thresholds["strong"]),
                {"Sc", "C", "M", "EQ", "FS", "T"})
            self.assertEqual(set(item.thresholds["wait"]),
                {"B", "C", "M", "EQ", "FS", "T"})
            self.assertFalse(item.strong_qualified and item.wait_qualified)

    def test_genuine_ordinary_a_batch_has_zero_out_of_scope_members(self):
        self.assertNotIn("out_of_scope", [item.state for item in self.batch.eligibilities])


class SmallGenuineEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = FinalScoringFixture(peer_count=3)
        try:
            cls.fixture.populate_final_inputs()
            cls.inputs = d1_batch(cls.fixture)
            cls.cards = build_final_score_card_batch(cls.inputs)
            cls.batch = build_formal_eligibility_batch(cls.inputs, cls.cards)
        except BaseException:
            cls.fixture.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def test_three_member_snapshot_preserves_pending_provenance(self):
        self.assertEqual(len(self.batch.security_ids), 3)
        self.assertEqual(tuple(item.security_id for item in self.batch.eligibilities),
            self.inputs.security_ids)
        for sid in self.inputs.security_ids:
            item = self.batch.eligibility_for(sid)
            self.assertEqual(item.state, "pending_evidence")
            self.assertEqual(item.source_entry_hash, self.inputs.input_for(sid).entry_hash)
            self.assertIsNone(item.card_hash)
            self.assertIsNone(item.sort_fields)
            self.assertFalse(item.strong_qualified or item.wait_qualified)

    def test_repeated_access_revalidates_source_without_replaying_selectors(self):
        item = self.batch.eligibility_for(self.inputs.security_ids[0])
        selector_codes = {PolicyAdjustedScoreInputBatch.input_for.__code__,
            FinalScoreCardBatch.card_for.__code__}
        selected = []

        def observe(frame, event, arg):
            if event == "call" and frame.f_code in selector_codes:
                selected.append(frame.f_code.co_name)

        previous = sys.getprofile()
        sys.setprofile(observe)
        try:
            for _ in range(3):
                item.require_verified()
                self.assertEqual(item.state, "pending_evidence")
                self.assertIsNone(item.card_hash)
        finally:
            sys.setprofile(previous)
        self.assertEqual(selected, [])

        record = inspect.getclosurevars(
            PolicyAdjustedScoreInputBatch.input_for).nonlocals["record"]
        proofs = inspect.getclosurevars(record).nonlocals["proofs"]
        publication = proofs[id(self.inputs)][4]
        publication[0] = False
        try:
            with self.assertRaises(ValueError):
                item.require_verified()
        finally:
            publication[0] = True
        item.require_verified()

    def test_three_member_guards_reject_mismatched_publication_and_plain_values(self):
        replay = d1_batch(self.fixture)
        self.assertEqual(replay.batch_hash, self.inputs.batch_hash)
        self.assertIsNot(replay, self.inputs)
        with self.assertRaises(ValueError):
            build_formal_eligibility_batch(replay, self.cards)
        with self.assertRaises(ValueError):
            build_formal_eligibility_batch(self.inputs.to_dict(), self.cards)
        with self.assertRaises(ValueError):
            build_formal_eligibility_batch(self.inputs, self.cards.to_dict())


if __name__ == "__main__":
    unittest.main()
