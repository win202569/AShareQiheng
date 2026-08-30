import hashlib
import unittest
from datetime import date, datetime, timezone

from ashare_pipeline.sources import (
    AKShareSource,
    BaoStockSource,
    FetchBatch,
    RetryableSourceError,
    SourceBlocked,
    TerminalSourceError,
)


class FakeResult:
    def __init__(self, fields, rows, error_code="0", error_msg=""):
        self.fields = fields
        self._rows = rows
        self.error_code = error_code
        self.error_msg = error_msg
        self._index = -1

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


class FakeBaoStock:
    __version__ = "0.9.3"

    def __init__(self, result=None, login_code="0"):
        self.result = result or FakeResult(["code", "code_name", "type", "status"], [["sh.600000", "浦发银行", "1", "1"]])
        self.login_code = login_code
        self.logins = 0
        self.logouts = 0
        self.daily_kwargs = None

    def login(self):
        self.logins += 1
        return FakeResult([], [], self.login_code, "network")

    def logout(self):
        self.logouts += 1

    def query_stock_basic(self):
        return self.result

    def query_trade_dates(self, start_date, end_date):
        return self.result

    def query_history_k_data_plus(self, **kwargs):
        self.daily_kwargs = kwargs
        return self.result


class FakeFrame:
    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return [dict(zip(self.columns, row, strict=True)) for row in self.rows]


class FakeAKShare:
    __version__ = "1.18.94"

    def __init__(self):
        self.calls = []
        self.disclosure = FakeFrame(["股票代码", "股票简称", "公告日期"], [["000001", "平安银行", date(2026, 8, 20)]])
        self.performance = FakeFrame(
            ["股票代码", "股票简称", "每股收益", "营业总收入-营业总收入", "营业总收入-同比增长", "净利润-净利润", "净利润-同比增长", "每股净资产", "净资产收益率", "每股经营现金流量", "销售毛利率", "所处行业", "最新公告日期", "不应保存"],
            [["000001", "平安银行", 1.2, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, "银行", date(2026, 8, 20), "extra"]],
        )
        self.statement = FakeFrame(["REPORT_DATE", "NOTICE_DATE", "UPDATE_DATE", "VALUE"], [["2026-06-30", date(2026, 8, 20), datetime(2026, 8, 20, tzinfo=timezone.utc), float("nan")]])
        self.cninfo = FakeFrame(["公告标题", "公告时间", "公告链接"], [["2026年半年度报告", date(2026, 8, 20), "https://example.test/a"]])
        self.spot = FakeFrame(["代码", "名称", "最新价"], [["000001", "平安银行", 12.3]])

    def stock_report_disclosure(self, **kwargs): self.calls.append(("disclosure", kwargs)); return self.disclosure
    def stock_yjbb_em(self, **kwargs): self.calls.append(("performance", kwargs)); return self.performance
    def stock_balance_sheet_by_report_em(self, **kwargs): self.calls.append(("balance", kwargs)); return self.statement
    def stock_profit_sheet_by_report_em(self, **kwargs): self.calls.append(("profit", kwargs)); return self.statement
    def stock_cash_flow_sheet_by_report_em(self, **kwargs): self.calls.append(("cash", kwargs)); return self.statement
    def stock_zh_a_disclosure_report_cninfo(self, **kwargs): self.calls.append(("cninfo", kwargs)); return self.cninfo
    def stock_zh_a_spot_em(self): self.calls.append(("spot", {})); return self.spot


class SourcesTestCase(unittest.TestCase):
    def test_canonical_hash_normalizes_nan_dates_and_preserves_leading_zero_code(self):
        batch = FetchBatch("akshare", "x", {"code": "000001"}, [{"code": "000001", "n": float("nan"), "when": date(2026, 8, 1)}], "2026-08-01T00:00:00+00:00", "1", {})

        self.assertEqual(batch.records[0]["code"], "000001")
        self.assertIn(b'"n":null', batch.canonical_bytes())
        self.assertEqual(batch.sha256(), hashlib.sha256(batch.canonical_bytes()).hexdigest())

    def test_content_hash_ignores_observation_time_but_keeps_normalized_nat(self):
        class NaT:
            def __str__(self): return "NaT"
        first = FetchBatch("akshare", "spot", {}, [{"code": "000403", "at": NaT()}], "2026-08-01T00:00:00+00:00", "1", {})
        later = FetchBatch("akshare", "spot", {}, [{"code": "000403", "at": NaT()}], "2026-08-02T00:00:00+00:00", "1", {})

        self.assertEqual(first.records[0]["at"], None)
        self.assertEqual(first.sha256(), later.sha256())

    def test_baostock_logs_out_in_finally_and_keeps_empty_result_successful(self):
        module = FakeBaoStock(FakeResult(["code", "code_name", "type", "status"], []))
        batch = BaoStockSource(module=module, clock=lambda: "2026-08-25T00:00:00+00:00", sleeper=lambda _delay: None).fetch_security_master()

        self.assertEqual(batch.records, [])
        self.assertEqual(batch.metadata["type_counts"], {})
        self.assertEqual(module.logins, 1)
        self.assertEqual(module.logouts, 1)

    def test_baostock_nonzero_result_is_retryable_and_still_logs_out(self):
        module = FakeBaoStock(FakeResult(["code"], [], error_code="100", error_msg="temporary"))

        with self.assertRaises(RetryableSourceError):
            BaoStockSource(module=module, sleeper=lambda _delay: None).fetch_security_master()
        self.assertEqual(module.logouts, 1)

    def test_baostock_query_error_uses_code_and_message_for_block_classification(self):
        module = FakeBaoStock(FakeResult(["code"], [], error_code="403", error_msg="HTTP 403 forbidden"))

        with self.assertRaises(SourceBlocked):
            BaoStockSource(module=module, sleeper=lambda _delay: None).fetch_security_master()

    def test_baostock_uses_injected_sleeper_once_per_query_lifecycle(self):
        sleeps = []
        BaoStockSource(module=FakeBaoStock(), sleeper=sleeps.append).fetch_security_master()

        self.assertEqual(sleeps, [0.2])

    def test_baostock_login_access_control_is_blocked_and_still_logs_out(self):
        module = FakeBaoStock(login_code="403")

        with self.assertRaises(SourceBlocked):
            BaoStockSource(module=module, sleeper=lambda _delay: None).fetch_security_master()
        self.assertEqual(module.logouts, 1)

    def test_baostock_daily_uses_required_unadjusted_contract(self):
        fields = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST".split(",")
        module = FakeBaoStock(FakeResult(fields, [["2026-08-24", "sh.600000"] + [""] * 16]))
        batch = BaoStockSource(module=module, sleeper=lambda _delay: None).fetch_daily("sh.600000", "2026-08-24", "2026-08-25")

        self.assertEqual(batch.records[0]["code"], "sh.600000")
        self.assertEqual(module.daily_kwargs["frequency"], "d")
        self.assertEqual(module.daily_kwargs["adjustflag"], "3")
        self.assertEqual(module.daily_kwargs["fields"], ",".join(fields))

    def test_akshare_financial_batches_record_target_period_metadata_and_normalize_frame_values(self):
        module = FakeAKShare()
        batches = AKShareSource(module=module, clock=lambda: "2026-08-25T00:00:00+00:00").fetch_financial_statements("SH600000")

        self.assertEqual(set(batches), {"balance_sheet", "profit_sheet", "cash_flow_sheet"})
        self.assertEqual([name for name, _ in module.calls], ["balance", "profit", "cash"])
        self.assertEqual(batches["balance_sheet"].metadata["report_period_match_count"], 1)
        self.assertEqual(batches["balance_sheet"].metadata["column_count"], 4)
        self.assertIsNone(batches["balance_sheet"].records[0]["VALUE"])
        self.assertEqual(batches["balance_sheet"].records[0]["NOTICE_DATE"], "2026-08-20")

    def test_fetch_financial_statement_calls_exactly_one_requested_method(self):
        for dataset, expected_call in (
            ("balance_sheet", "balance"),
            ("profit_sheet", "profit"),
            ("cash_flow_sheet", "cash"),
        ):
            with self.subTest(dataset=dataset):
                module = FakeAKShare()
                batch = AKShareSource(module=module).fetch_financial_statement(
                    "SH600000", dataset, "2026-06-30"
                )

                self.assertEqual([name for name, _ in module.calls], [expected_call])
                self.assertEqual(batch.dataset, dataset)
                self.assertEqual(batch.request, {
                    "symbol": "SH600000",
                    "report_period": "2026-06-30",
                })
                self.assertEqual(batch.metadata["report_period_match_count"], 1)

    def test_fetch_financial_statement_rejects_unknown_dataset_before_module_access(self):
        module = FakeAKShare()

        class GuardedAKShareSource(AKShareSource):
            def _module(self):
                raise AssertionError("module access")

        with self.assertRaisesRegex(ValueError, "unsupported financial dataset"):
            GuardedAKShareSource(module=module).fetch_financial_statement(
                "SH600000", "unknown_sheet", "2026-06-30"
            )

        self.assertEqual(module.calls, [])

    def test_fetch_financial_statement_retries_empty_result(self):
        module = FakeAKShare()
        module.statement = FakeFrame([], [])

        with self.assertRaises(RetryableSourceError):
            AKShareSource(module=module).fetch_financial_statement(
                "SH600000", "balance_sheet", "2026-06-30"
            )

        self.assertEqual([name for name, _ in module.calls], ["balance"])

    def test_financial_statements_wrapper_reuses_single_statement_method_in_fixed_order(self):
        class RecordingSource(AKShareSource):
            def __init__(self):
                super().__init__(module=FakeAKShare())
                self.statement_requests = []

            def fetch_financial_statement(self, symbol, dataset, report_period="2026-06-30"):
                self.statement_requests.append((symbol, dataset, report_period))
                return FetchBatch(
                    "akshare",
                    dataset,
                    {"symbol": symbol, "report_period": report_period},
                    [{"REPORT_DATE": report_period}],
                    "2026-08-25T00:00:00+00:00",
                    "test",
                    {"report_period_match_count": 1},
                )

        source = RecordingSource()
        batches = source.fetch_financial_statements("SH600000", "2026-06-30")

        self.assertEqual(list(batches), ["balance_sheet", "profit_sheet", "cash_flow_sheet"])
        self.assertEqual(source.statement_requests, [
            ("SH600000", "balance_sheet", "2026-06-30"),
            ("SH600000", "profit_sheet", "2026-06-30"),
            ("SH600000", "cash_flow_sheet", "2026-06-30"),
        ])

    def test_akshare_spot_blocks_access_control_and_retries_empty_structure(self):
        module = FakeAKShare()
        module.spot = FakeFrame(["html"], [["<html>403 forbidden</html>"]])
        with self.assertRaises(SourceBlocked):
            AKShareSource(module=module).fetch_spot_snapshot()

        module.spot = FakeFrame([], [])
        with self.assertRaises(RetryableSourceError):
            AKShareSource(module=module).fetch_spot_snapshot()

    def test_frame_scalar_codes_do_not_trigger_http_blocking_but_challenge_text_does(self):
        module = FakeAKShare()
        module.spot = FakeFrame(["序号", "代码", "名称"], [[403, "000403", "甲"], [429, "000429", "乙"]])
        result = AKShareSource(module=module).fetch_spot_snapshot()
        self.assertEqual([row["代码"] for row in result.records], ["000403", "000429"])

        module.spot = FakeFrame(["message"], [["429 Too Many Requests"]])
        with self.assertRaises(SourceBlocked):
            AKShareSource(module=module).fetch_spot_snapshot()

    def test_akshare_uses_fixed_source_requests_and_preserves_cninfo_metadata(self):
        module = FakeAKShare()
        source = AKShareSource(module=module)
        source.fetch_disclosure_schedule()
        source.fetch_performance_report()
        batch = source.fetch_cninfo_halfyear_disclosures("000001")

        self.assertIn(("disclosure", {"market": "沪深京", "period": "2026半年报"}), module.calls)
        self.assertIn(("performance", {"date": "20260630"}), module.calls)
        self.assertEqual(batch.records[0]["公告链接"], "https://example.test/a")
        performance = source.fetch_performance_report()
        self.assertNotIn("不应保存", performance.records[0])
        self.assertEqual(performance.records[0]["营业总收入"], 1.0)
        self.assertEqual(performance.records[0]["净利润同比增长"], 4.0)
        self.assertEqual(performance.metadata["source_column_mapping"]["营业总收入"], "营业总收入-营业总收入")

    def test_performance_report_rejects_incomplete_real_schema(self):
        module = FakeAKShare()
        module.performance = FakeFrame(["股票代码", "股票简称"], [["000001", "平安银行"]])

        with self.assertRaises(TerminalSourceError):
            AKShareSource(module=module).fetch_performance_report()
