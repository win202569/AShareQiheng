import unittest
from decimal import Decimal

from ashare_pipeline.formal_pool import _select_detached_rows


def row(sid, *, industry="industry", strong=False, wait=False, sc="70", b="65", c=".75", safety="45", v="45"):
    return {"security_id": sid, "secondary_industry": industry,
        "state": "formal_scored", "strong_qualified": strong,
        "wait_qualified": wait, "sort_fields": {
            "Sc": Decimal(sc), "B": Decimal(b), "C": Decimal(c),
            "R_safety": Decimal(safety), "V": Decimal(v)},
        "eligibility_hash": sid.lower() + "-hash", "source_entry_hash": sid.lower() + "-entry",
        "source_batch_hash": "batch-hash", "score_batch_hash": "score-hash"}


class FormalPoolSelectionTests(unittest.TestCase):
    def test_strong_sort_is_sc_confidence_safety_then_security_id(self):
        rows = [row("SH000003", strong=True, sc="90", c=".80", safety="80"),
            row("SH000002", strong=True, sc="90", c=".80", safety="80"),
            row("SH000001", strong=True, sc="90", c=".80", safety="81")]
        result = _select_detached_rows(rows)
        self.assertEqual(result.strong_ids, ("SH000001", "SH000002", "SH000003"))

    def test_wait_sort_is_b_confidence_v_then_security_id(self):
        rows = [row("SH000003", wait=True, b="80", c=".80", v="80"),
            row("SH000002", wait=True, b="80", c=".80", v="80"),
            row("SH000001", wait=True, b="80", c=".80", v="81")]
        result = _select_detached_rows(rows)
        self.assertEqual(result.wait_ids, ("SH000001", "SH000002", "SH000003"))

    def test_fifth_strong_industry_member_is_skipped_and_scan_continues(self):
        rows = [row(f"SH00000{i}", industry="same", strong=True) for i in range(1, 6)]
        rows.append(row("SH000006", industry="other", strong=True))
        result = _select_detached_rows(rows, strong_industry_cap=4)
        self.assertEqual(result.strong_ids, tuple(f"SH00000{i}" for i in range(1, 5)) + ("SH000006",))
        self.assertEqual(result.strong_decisions["SH000005"], "industry_cap_reached")

    def test_eleventh_wait_industry_member_is_skipped_and_scan_continues(self):
        rows = [row(f"SH0000{i:02d}", industry="same", wait=True) for i in range(1, 12)]
        rows.append(row("SH000012", industry="other", wait=True))
        result = _select_detached_rows(rows, wait_industry_cap=10)
        self.assertEqual(result.wait_ids, tuple(f"SH0000{i:02d}" for i in range(1, 11)) + ("SH000012",))
        self.assertEqual(result.wait_decisions["SH000011"], "industry_cap_reached")

    def test_overall_caps_are_20_and_50_without_forced_fill(self):
        rows = [row(f"SH{i:06d}", industry=f"i{i}", strong=True) for i in range(1, 23)]
        rows += [row(f"SZ{i:06d}", industry=f"w{i}", wait=True) for i in range(1, 53)]
        result = _select_detached_rows(rows)
        self.assertEqual(len(result.strong_ids), 20)
        self.assertEqual(len(result.wait_ids), 50)
        self.assertEqual(result.strong_decisions["SH000021"], "overall_capacity_reached")
        self.assertEqual(result.wait_decisions["SZ000051"], "overall_capacity_reached")

    def test_strong_cap_rejection_never_falls_into_wait(self):
        rows = [row("SH000001", strong=True, wait=False)]
        result = _select_detached_rows(rows, strong_overall_cap=0)
        self.assertEqual(result.strong_ids, ())
        self.assertEqual(result.wait_ids, ())
        self.assertEqual(result.strong_decisions["SH000001"], "overall_capacity_reached")
        self.assertEqual(result.wait_decisions["SH000001"], "not_qualified")

    def test_pools_are_disjoint_and_every_candidate_has_decision_trace(self):
        rows = [row("SH000001", strong=True), row("SH000002", wait=True), row("SH000003")]
        result = _select_detached_rows(rows)
        self.assertTrue(set(result.strong_ids).isdisjoint(result.wait_ids))
        self.assertEqual(set(result.strong_decisions), {r["security_id"] for r in rows})
        self.assertEqual(set(result.wait_decisions), {r["security_id"] for r in rows})

    def test_pending_nonqualified_member_without_industry_or_sort_fields_is_trace_only(self):
        pending = row("SH000004", industry=None, strong=False, wait=False)
        pending["state"] = "pending_evidence"
        pending["sort_fields"] = None
        result = _select_detached_rows([row("SH000001", strong=True), pending])
        self.assertEqual(result.strong_ids, ("SH000001",))
        self.assertEqual(result.wait_ids, ())
        self.assertEqual(result.strong_decisions["SH000004"], "not_qualified")
        self.assertEqual(result.wait_decisions["SH000004"], "not_qualified")


if __name__ == "__main__":
    unittest.main()
