import unittest

from ashare_pipeline.curation import curate_performance, curate_universe, quality_gate


class CurationTestCase(unittest.TestCase):
    def test_universe_keeps_only_active_shenzhen_shanghai_a_shares_and_labels_st(self):
        records = [
            {"code": "sh.600000", "code_name": "浦发银行", "ipoDate": "1999-11-10", "type": "1", "status": "1"},
            {"code": "sh.688001", "code_name": "华兴源创", "ipoDate": "2019-07-22", "type": "1", "status": "1"},
            {"code": "sz.000001", "code_name": "平安银行", "ipoDate": "1991-04-03", "type": "1", "status": "1"},
            {"code": "sz.300750", "code_name": "宁德时代", "ipoDate": "2018-06-11", "type": "1", "status": "1"},
            {"code": "sz.002001", "code_name": "*ST新例", "ipoDate": "2004-06-25", "type": "1", "status": "1"},
            {"code": "sh.900901", "code_name": "云赛B股", "type": "1", "status": "1"},
            {"code": "sh.689009", "code_name": "九号公司", "type": "1", "status": "1"},
            {"code": "sz.200002", "code_name": "万科B", "type": "1", "status": "1"},
            {"code": "bj.430047", "code_name": "诺思兰德", "type": "1", "status": "1"},
            {"code": "sh.000001", "code_name": "上证指数", "type": "2", "status": "1"},
            {"code": "sz.000003", "code_name": "退市样本", "type": "1", "status": "0"},
        ]

        curated, metrics = curate_universe(records)

        self.assertEqual(
            [row["security_id"] for row in curated],
            ["SH600000", "SH688001", "SZ000001", "SZ002001", "SZ300750"],
        )
        by_id = {row["security_id"]: row for row in curated}
        self.assertEqual(by_id["SH688001"]["board"], "科创板")
        self.assertEqual(by_id["SZ300750"]["board"], "创业板")
        self.assertEqual(by_id["SZ000001"]["code6"], "000001")
        self.assertEqual(by_id["SZ002001"]["risk_tags"], ["ST"])
        self.assertEqual(metrics["universe_count"], 5)
        self.assertEqual(metrics["excluded_count"], 6)
        self.assertEqual(metrics["excluded_cdr_689_count"], 1)

    def test_final_cutoff_filters_september_revision_before_latest_version_dedupe(self):
        universe, _ = curate_universe(
            [{"code": "sz.000001", "code_name": "平安银行", "type": "1", "status": "1"}]
        )
        in_cutoff = {
            "股票代码": "000001", "股票简称": "平安银行", "营业总收入同比增长": 5,
            "净利润同比增长": 6, "净资产收益率": 7, "销售毛利率": 8,
            "每股经营现金流量": 1, "所处行业": "银行",
            "最新公告日期": "2026-08-31T23:00:00+08:00",
        }
        late_revision = {
            **in_cutoff,
            "净利润同比增长": 99,
            "最新公告日期": "2026-09-01T00:01:00+08:00",
        }

        frozen, metrics = curate_performance(
            [late_revision, in_cutoff],
            universe,
            cutoff_cn="2026-08-31T23:59:59+08:00",
        )
        observed, _ = curate_performance([late_revision, in_cutoff], universe)

        self.assertEqual(frozen[0]["net_profit_yoy"], 6.0)
        self.assertEqual(frozen[0]["announcement_date"], "2026-08-31T23:00:00+08:00")
        self.assertEqual(metrics["post_cutoff_observation_rows"], 1)
        self.assertEqual(metrics["post_cutoff_security_count"], 1)
        self.assertEqual(observed[0]["net_profit_yoy"], 99.0)

    def test_performance_preserves_leading_zero_filters_outside_and_deduplicates_stably(self):
        universe, _ = curate_universe(
            [
                {"code": "sz.000001", "code_name": "平安银行", "type": "1", "status": "1"},
                {"code": "sh.600000", "code_name": "浦发银行", "type": "1", "status": "1"},
            ]
        )
        older = {
            "股票代码": 1,
            "股票简称": "平安银行",
            "营业总收入-同比增长": "3.5",
            "净利润-同比增长": "4.5",
            "净资产收益率": "5.5",
            "销售毛利率": "6.5",
            "每股经营现金流量": "0.7",
            "所处行业": "银行",
            "最新公告日期": "2026-08-20",
        }
        latest_b = {**older, "营业总收入-同比增长": "9", "最新公告日期": "2026-08-28", "tie": "b"}
        latest_a = {**older, "营业总收入-同比增长": "8", "最新公告日期": "2026-08-28", "tie": "a"}
        outside = {**older, "股票代码": "920001", "股票简称": "北交样本"}

        first, first_metrics = curate_performance([older, latest_b, outside, latest_a], universe)
        second, second_metrics = curate_performance([latest_a, outside, latest_b, older], universe)

        self.assertEqual(first, second)
        self.assertEqual(first_metrics, second_metrics)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["code6"], "000001")
        self.assertEqual(first[0]["security_id"], "SZ000001")
        self.assertEqual(first[0]["announcement_date"], "2026-08-28")
        self.assertIn(first[0]["revenue_yoy"], (8.0, 9.0))
        self.assertIn("股票简称", first[0])
        self.assertEqual(first_metrics["outside_universe_rows"], 1)
        self.assertEqual(first_metrics["duplicate_security_count"], 1)

    def test_quality_gate_is_partial_before_cutoff_and_flags_future_announcements(self):
        universe = [{"security_id": "SZ000001", "code6": "000001"}]
        performance = [
            {
                "security_id": "SZ000001",
                "code6": "000001",
                "announcement_date": "2026-08-30",
                "revenue_yoy": 1.0,
                "net_profit_yoy": 2.0,
                "roe": 3.0,
                "gross_margin": 4.0,
                "operating_cash_flow_per_share": 5.0,
            }
        ]

        report = quality_gate(universe, performance, "2026-08-29T12:00:00+08:00")

        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["future_announcement_count"], 1)
        self.assertFalse(report["data_quality_passed"])

    def test_date_only_announcement_on_as_of_date_is_not_treated_as_future(self):
        universe = [{"security_id": "SZ000001", "code6": "000001"}]
        performance = [
            {
                "security_id": "SZ000001",
                "code6": "000001",
                "announcement_date": "2026-08-29",
                "revenue_yoy": 1.0,
                "net_profit_yoy": 2.0,
                "roe": 3.0,
                "gross_margin": 4.0,
                "operating_cash_flow_per_share": 5.0,
            }
        ]

        report = quality_gate(universe, performance, "2026-08-29T12:00:00+08:00")

        self.assertEqual(report["future_announcement_count"], 0)

    def test_quality_gate_accepts_exactly_ninety_five_percent_completeness_after_cutoff(self):
        universe = [{"security_id": f"SZ{i:06d}", "code6": f"{i:06d}"} for i in range(1, 5)]
        performance = []
        for i in range(1, 5):
            performance.append(
                {
                    "security_id": f"SZ{i:06d}",
                    "code6": f"{i:06d}",
                    "announcement_date": "2026-08-31",
                    "revenue_yoy": float(i),
                    "net_profit_yoy": float(i),
                    "roe": float(i),
                    "gross_margin": float(i),
                    "operating_cash_flow_per_share": None if i == 4 else float(i),
                }
            )

        report = quality_gate(universe, performance, "2026-09-01T00:00:00+08:00")

        self.assertEqual(report["core_field_completeness"], 0.95)
        self.assertTrue(report["data_quality_passed"])
        self.assertEqual(report["status"], "data_ready")

    def test_quality_gate_rejects_duplicate_codes_after_cutoff(self):
        universe = [{"security_id": "SZ000001", "code6": "000001"}]
        row = {
            "security_id": "SZ000001",
            "code6": "000001",
            "announcement_date": "2026-08-31",
            "revenue_yoy": 1.0,
            "net_profit_yoy": 1.0,
            "roe": 1.0,
            "gross_margin": 1.0,
            "operating_cash_flow_per_share": 1.0,
        }

        report = quality_gate(universe, [row, dict(row)], "2026-09-01T00:00:00+08:00")

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["duplicate_security_count"], 1)

    def test_quality_gate_rejects_duplicate_universe_codes_after_cutoff(self):
        universe = [
            {"security_id": "SZ000001", "code6": "000001"},
            {"security_id": "SZ000001", "code6": "000001"},
        ]
        performance = [
            {
                "security_id": "SZ000001",
                "code6": "000001",
                "announcement_date": "2026-08-31",
                "revenue_yoy": 1.0,
                "net_profit_yoy": 1.0,
                "roe": 1.0,
                "gross_margin": 1.0,
                "operating_cash_flow_per_share": 1.0,
            }
        ]

        report = quality_gate(universe, performance, "2026-09-01T00:00:00+08:00")

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["universe_duplicate_security_count"], 1)

    def test_quality_gate_blocks_missing_and_unparseable_announcement_timestamps(self):
        universe = [
            {"security_id": "SZ000001", "code6": "000001"},
            {"security_id": "SZ000002", "code6": "000002"},
        ]
        base = {
            "revenue_yoy": 1.0,
            "net_profit_yoy": 1.0,
            "roe": 1.0,
            "gross_margin": 1.0,
            "operating_cash_flow_per_share": 1.0,
        }
        performance = [
            {**base, "security_id": "SZ000001", "code6": "000001", "announcement_date": None},
            {**base, "security_id": "SZ000002", "code6": "000002", "announcement_date": "not-a-date"},
        ]

        report = quality_gate(universe, performance, "2026-09-01T00:00:00+08:00")

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["announcement_timestamp_missing_count"], 1)
        self.assertEqual(report["announcement_timestamp_unparseable_count"], 1)
        self.assertFalse(report["data_quality_passed"])

    def test_quality_gate_requires_ninety_five_percent_disclosed_universe_coverage(self):
        universe = [{"security_id": f"SZ{i:06d}", "code6": f"{i:06d}"} for i in range(1, 21)]
        performance = [
            {
                "security_id": f"SZ{i:06d}", "code6": f"{i:06d}", "announcement_date": "2026-08-31",
                "revenue_yoy": 1.0, "net_profit_yoy": 1.0, "roe": 1.0,
                "gross_margin": 1.0, "operating_cash_flow_per_share": 1.0,
            }
            for i in range(1, 20)
        ]

        at_boundary = quality_gate(universe, performance, "2026-09-01T00:00:00+08:00")
        below_boundary = quality_gate(universe, performance[:-1], "2026-09-01T00:00:00+08:00")

        self.assertEqual(at_boundary["eligible_universe_count"], 20)
        self.assertEqual(at_boundary["disclosed_unique_count"], 19)
        self.assertEqual(at_boundary["disclosure_coverage_rate"], 0.95)
        self.assertTrue(at_boundary["data_quality_passed"])
        self.assertEqual(below_boundary["disclosure_coverage_rate"], 0.9)
        self.assertFalse(below_boundary["data_quality_passed"])


if __name__ == "__main__":
    unittest.main()
