import unittest

from ashare_pipeline.scoring import build_prefilter


def performance_row(code: int, industry: str, value: float | None, **overrides):
    row = {
        "security_id": f"SZ{code:06d}",
        "code6": f"{code:06d}",
        "industry": industry,
        "revenue_yoy": value,
        "net_profit_yoy": value,
        "roe": value,
        "gross_margin": value,
        "operating_cash_flow_per_share": value,
    }
    row.update(overrides)
    return row


class ScoringTestCase(unittest.TestCase):
    def test_percentiles_average_ties_handle_negatives_and_do_not_fill_missing_with_zero(self):
        rows = [
            performance_row(1, "小行业", -10, roe=None, gross_margin=None, operating_cash_flow_per_share=None),
            performance_row(2, "小行业", -10, roe=None, gross_margin=None, operating_cash_flow_per_share=None),
            performance_row(3, "小行业", 20, roe=None, gross_margin=None, operating_cash_flow_per_share=None),
        ]

        candidates, metrics = build_prefilter(rows)
        by_id = {row["security_id"]: row for row in candidates}

        self.assertEqual(by_id["SZ000001"]["metric_percentiles"]["revenue_yoy"], 25.0)
        self.assertEqual(by_id["SZ000002"]["metric_percentiles"]["revenue_yoy"], 25.0)
        self.assertEqual(by_id["SZ000003"]["metric_percentiles"]["revenue_yoy"], 100.0)
        self.assertEqual(by_id["SZ000001"]["prefilter_score"], 25.0)
        self.assertEqual(by_id["SZ000001"]["coverage"], 0.55)
        self.assertIsNone(by_id["SZ000001"]["quality_proxy"])
        self.assertCountEqual(
            by_id["SZ000001"]["missing_metrics"],
            ["roe", "gross_margin", "operating_cash_flow_per_share"],
        )
        self.assertFalse(by_id["SZ000001"]["is_official_score"])
        self.assertEqual(by_id["SZ000001"]["reason"], "仅供深抓排序，不是V2正式总分")
        self.assertEqual(metrics["candidate_count"], 3)

    def test_industry_with_fewer_than_twenty_observations_uses_market_percentile(self):
        rows = [performance_row(index + 1, "大行业", float(100 + index)) for index in range(20)]
        rows.append(performance_row(100, "小行业", 50.0))

        candidates, _ = build_prefilter(rows)
        small = next(row for row in candidates if row["security_id"] == "SZ000100")

        self.assertEqual(small["metric_percentiles"]["revenue_yoy"], 0.0)
        self.assertEqual(small["percentile_scope"]["revenue_yoy"], "market")
        large_low = next(row for row in candidates if row["security_id"] == "SZ000001")
        self.assertEqual(large_low["metric_percentiles"]["revenue_yoy"], 0.0)
        self.assertEqual(large_low["percentile_scope"]["revenue_yoy"], "industry")

    def test_candidate_queue_caps_at_120_and_retains_two_representatives_per_large_industry(self):
        rows = []
        for code in range(1, 21):
            rows.append(performance_row(code, "行业甲", float(code)))
        for code in range(21, 41):
            rows.append(performance_row(code, "行业乙", float(code)))
        for code in range(41, 131):
            rows.append(performance_row(code, "行业丙", float(code)))

        candidates, metrics = build_prefilter(rows)

        self.assertEqual(len(candidates), 120)
        self.assertEqual(metrics["candidate_count"], 120)
        representatives = {row["security_id"] for row in candidates if row["selection_origin"] == "industry_representative"}
        self.assertTrue({"SZ000019", "SZ000020"}.issubset(representatives))
        self.assertTrue({"SZ000039", "SZ000040"}.issubset(representatives))
        self.assertTrue({"SZ000129", "SZ000130"}.issubset(representatives))
        self.assertNotIn("pool", repr(candidates).lower())

    def test_industry_representatives_alone_never_exceed_120_and_truncate_deterministically(self):
        rows = []
        code = 1
        for industry_index in range(61):
            for value in range(20):
                rows.append(performance_row(code, f"行业{industry_index:02d}", float(value)))
                code += 1

        first, first_metrics = build_prefilter(rows)
        second, second_metrics = build_prefilter(list(reversed(rows)))

        self.assertEqual(len(first), 120)
        self.assertEqual(first, second)
        self.assertEqual(first_metrics, second_metrics)
        self.assertEqual(first_metrics["industry_representative_count"], 120)
        self.assertNotIn("行业60", {row["industry"] for row in first})

    def test_tied_scores_are_stable_across_input_order(self):
        rows = [performance_row(index, "稳定行业", 10.0) for index in range(1, 26)]

        first, first_metrics = build_prefilter(rows)
        second, second_metrics = build_prefilter(list(reversed(rows)))

        self.assertEqual(first, second)
        self.assertEqual(first_metrics, second_metrics)
        self.assertEqual([row["security_id"] for row in first[:3]], ["SZ000001", "SZ000002", "SZ000003"])

    def test_row_without_any_available_metric_is_not_selected(self):
        candidates, metrics = build_prefilter([performance_row(1, "缺失行业", None)])

        self.assertEqual(candidates, [])
        self.assertEqual(metrics["unscorable_count"], 1)


if __name__ == "__main__":
    unittest.main()
