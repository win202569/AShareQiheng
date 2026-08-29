import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from ashare_pipeline import pilot
from ashare_pipeline.sources import FetchBatch, RetryableSourceError, SourceBlocked
from ashare_pipeline.state_store import StateStore


class PilotTestCase(unittest.TestCase):
    def test_offline_cli_initializes_database_and_never_imports_or_calls_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            db = Path(directory) / "state.sqlite3"
            output = io.StringIO()
            with patch("ashare_pipeline.pilot._run_online", side_effect=AssertionError("network")):
                with redirect_stdout(output):
                    exit_code = pilot.main(["--root", str(root), "--db", str(db)])

            status = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(db.exists())
            self.assertEqual(status["mode"], "offline")
            self.assertTrue((root / "pilot_status.json").exists())

    def test_market_date_marks_future_and_preclose_dates_pending(self):
        future = pilot.market_date_status("2026-08-29", datetime(2026, 8, 28, 16, 0, tzinfo=pilot.SHANGHAI))
        preclose = pilot.market_date_status("2026-08-28", datetime(2026, 8, 28, 15, 29, tzinfo=pilot.SHANGHAI))
        complete = pilot.market_date_status("2026-08-28", datetime(2026, 8, 28, 15, 30, tzinfo=pilot.SHANGHAI))

        self.assertEqual(future, "pending")
        self.assertEqual(preclose, "pending")
        self.assertEqual(complete, "completed")

    def test_online_rerun_does_not_refetch_successful_jobs_and_spot_failure_is_nonblocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            db = Path(directory) / "state.sqlite3"
            calls = {"master": 0, "spot": 0}

            def batch(dataset):
                return FetchBatch("fake", dataset, {}, [{"code": "000001"}], "2026-08-28T00:00:00+00:00", "test", {})

            class FakeBao:
                def fetch_security_master(self): calls["master"] += 1; return batch("security_master")
                def fetch_trade_dates(self, *_): return batch("trade_dates")
                def fetch_daily(self, *_): return batch("daily")

            class FakeAK:
                def fetch_disclosure_schedule(self): return batch("disclosure_schedule")
                def fetch_performance_report(self): return batch("performance_report")
                def fetch_financial_statements(self, _): return {name: batch(name) for name in ("balance_sheet", "profit_sheet", "cash_flow_sheet")}
                def fetch_spot_snapshot(self): calls["spot"] += 1; raise RetryableSourceError("temporary")

            with patch("ashare_pipeline.sources.BaoStockSource", FakeBao), patch("ashare_pipeline.sources.AKShareSource", FakeAK):
                with redirect_stdout(io.StringIO()):
                    pilot.main(["--root", str(root), "--db", str(db), "--online"])
                    pilot.main(["--root", str(root), "--db", str(db), "--online"])

            self.assertEqual(calls["master"], 1)
            self.assertEqual(calls["spot"], 2)
            status = json.loads((root / "pilot_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["batches"][-1]["status"], "retryable_failed")

    def test_online_uses_calendar_latest_trading_day_and_persists_pending_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            calls = []
            def batch(dataset, records=None): return FetchBatch("fake", dataset, {}, records or [{"code": "000001"}], "2026-08-28T00:00:00+00:00", "test", {})
            class Bao:
                def fetch_security_master(self): return batch("security_master")
                def fetch_trade_dates(self, start, end):
                    calls.append((start, end))
                    return batch("trade_dates", [{"calendar_date": "2026-08-27", "is_trading_day": "1"}, {"calendar_date": "2026-08-28", "is_trading_day": "1"}])
                def fetch_daily(self, code, start, end): calls.append((code, start, end)); return batch("daily")
            class AK:
                def fetch_disclosure_schedule(self): return batch("disclosure_schedule")
                def fetch_performance_report(self): return batch("performance_report")
                def fetch_financial_statements(self, _): return {name: batch(name) for name in ("balance_sheet", "profit_sheet", "cash_flow_sheet")}
                def fetch_spot_snapshot(self): return batch("spot_snapshot")
            store = StateStore(db); store.initialize()
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                result = pilot._run_online(root, store, ["SH600000"], now=datetime(2026, 8, 28, 15, 29, tzinfo=pilot.SHANGHAI))

            self.assertEqual(result["requested_shanghai_date_status"], "pending")
            self.assertEqual(result["latest_completed_trading_date"], "2026-08-27")
            self.assertIn(("sh.600000", "2026-08-24", "2026-08-27"), calls)
            self.assertTrue(result["trading_calendar_evidence"])

    def test_blocked_source_circuits_its_later_tasks_without_blocking_other_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            calls = {"calendar": 0, "daily": 0, "ak": 0}
            class Bao:
                def fetch_security_master(self): raise SourceBlocked("HTTP 403")
                def fetch_trade_dates(self, *_): calls["calendar"] += 1
                def fetch_daily(self, *_): calls["daily"] += 1
            class AK:
                def _batch(self, dataset): calls["ak"] += 1; return FetchBatch("fake", dataset, {}, [], "2026-08-28T00:00:00+00:00", "test", {})
                def fetch_disclosure_schedule(self): return self._batch("disclosure_schedule")
                def fetch_performance_report(self): return self._batch("performance_report")
                def fetch_financial_statements(self, _): return {name: self._batch(name) for name in ("balance_sheet", "profit_sheet", "cash_flow_sheet")}
                def fetch_spot_snapshot(self): return self._batch("spot_snapshot")
            store = StateStore(db); store.initialize()
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                result = pilot._run_online(root, store, ["SH600000"], now=datetime(2026, 8, 28, 16, tzinfo=pilot.SHANGHAI))

            self.assertEqual(calls["calendar"], 0)
            self.assertEqual(calls["daily"], 0)
            self.assertGreater(calls["ak"], 0)
            self.assertIn("blocked_by_circuit", [item["status"] for item in result["batches"]])

    def test_reused_success_keeps_original_batch_details_and_unexpected_error_becomes_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            def batch(dataset, records=None): return FetchBatch("fake", dataset, {}, records or [{"code": "000001"}], "2026-08-28T00:00:00+00:00", "test-version", {})
            class Bao:
                def fetch_security_master(self): return batch("security_master")
                def fetch_trade_dates(self, *_): return batch("trade_dates", [{"calendar_date": "2026-08-28", "is_trading_day": "1"}])
                def fetch_daily(self, *_): return batch("daily")
            class AK:
                def fetch_disclosure_schedule(self): return batch("disclosure_schedule")
                def fetch_performance_report(self): return batch("performance_report")
                def fetch_financial_statements(self, _): return {name: batch(name) for name in ("balance_sheet", "profit_sheet", "cash_flow_sheet")}
                def fetch_spot_snapshot(self): raise RuntimeError("socket reset")
            store = StateStore(db); store.initialize()
            now = datetime(2026, 8, 28, 16, tzinfo=pilot.SHANGHAI)
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                pilot._run_online(root, store, ["SH600000"], now=now)
                result = pilot._run_online(root, store, ["SH600000"], now=now)

            master = next(item for item in result["batches"] if item["dataset"] == "security_master")
            self.assertEqual(master["source_version"], "test-version")
            self.assertIn("path", master)
            spot = next(item for item in result["batches"] if item["dataset"].startswith("akshare:spot_snapshot:"))
            self.assertEqual(spot["status"], "retryable_failed")

    def test_online_recovers_expired_lease_and_atomic_status_does_not_leave_part(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            store = StateStore(db); store.initialize()
            job_id = store.enqueue_job("unrelated", "expired", {})
            store.lease_next_job(["unrelated"], "worker", 1, "2026-08-28T00:00:00+00:00")
            class Bao:
                def fetch_security_master(self): return FetchBatch("fake", "security_master", {}, [], "2026-08-28T00:00:00+00:00", "test", {})
                def fetch_trade_dates(self, *_): return FetchBatch("fake", "trade_dates", {}, [{"calendar_date": "2026-08-28", "is_trading_day": "1"}], "2026-08-28T00:00:00+00:00", "test", {})
                def fetch_daily(self, *_): return FetchBatch("fake", "daily", {}, [], "2026-08-28T00:00:00+00:00", "test", {})
            class AK:
                def fetch_disclosure_schedule(self): return FetchBatch("fake", "disclosure_schedule", {}, [], "2026-08-28T00:00:00+00:00", "test", {})
                def fetch_performance_report(self): return FetchBatch("fake", "performance_report", {}, [], "2026-08-28T00:00:00+00:00", "test", {})
                def fetch_financial_statements(self, _): return {}
                def fetch_spot_snapshot(self): return FetchBatch("fake", "spot_snapshot", {}, [], "2026-08-28T00:00:00+00:00", "test", {})
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                pilot._run_online(root, store, [], now=datetime(2026, 8, 28, 16, tzinfo=pilot.SHANGHAI))
            self.assertEqual(store.get_job(job_id)["status"], "retryable_failed")

            with patch("ashare_pipeline.pilot.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    pilot._persist_status(root, {"schema_version": 1})
            self.assertEqual(list(root.glob("*.part")), [])

    def test_pilot_summaries_and_job_results_do_not_leak_raw_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            def batch(dataset, marker): return FetchBatch("fake", dataset, {}, [{"raw_marker": marker}], "2026-08-28T00:00:00+00:00", "test", {"unbounded": marker})
            class Bao:
                def fetch_security_master(self): return batch("security_master", "MASTER_RAW_SECRET")
                def fetch_trade_dates(self, *_): return FetchBatch("fake", "trade_dates", {}, [{"calendar_date": "2026-08-28", "is_trading_day": "1"}], "2026-08-28T00:00:00+00:00", "test", {})
                def fetch_daily(self, *_): return batch("daily", "DAILY_RAW_SECRET")
            class AK:
                def fetch_disclosure_schedule(self): return batch("disclosure_schedule", "DISCLOSURE_RAW_SECRET")
                def fetch_performance_report(self): return batch("performance_report", "PERFORMANCE_RAW_SECRET")
                def fetch_financial_statements(self, _): return {name: batch(name, "FINANCIAL_RAW_SECRET") for name in ("balance_sheet", "profit_sheet", "cash_flow_sheet")}
                def fetch_spot_snapshot(self): return batch("spot_snapshot", "SPOT_RAW_SECRET")
            store = StateStore(db); store.initialize()
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                result = pilot._run_online(root, store, ["SH600000"], now=datetime(2026, 8, 28, 16, tzinfo=pilot.SHANGHAI))

            public_text = json.dumps(result, ensure_ascii=False)
            for marker in ("MASTER_RAW_SECRET", "PERFORMANCE_RAW_SECRET", "FINANCIAL_RAW_SECRET"):
                self.assertNotIn(marker, public_text)
            self.assertTrue(any("MASTER_RAW_SECRET" in path.read_text(encoding="utf-8") for path in root.rglob("*.json")))
            connection = sqlite3.connect(db)
            try:
                job_ids = [row[0] for row in connection.execute("SELECT id FROM job")]
            finally:
                connection.close()
            for job in [store.get_job(job_id) for job_id in job_ids]:
                self.assertNotIn("RAW_SECRET", json.dumps(job, ensure_ascii=False))

    def test_old_retryable_job_cannot_be_leased_for_new_as_of_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            store = StateStore(db); store.initialize()
            old_key = "baostock:security_master:2026-08-27"
            old_kind = "pilot_fetch:baostock:security_master"
            old_id = store.enqueue_job(old_kind, old_key, {})
            store.lease_next_job([old_kind], "old", 60, "2026-08-27T00:00:00+00:00")
            store.fail_job(old_id, {"error": "retry"}, True)
            class Bao:
                def fetch_security_master(self): return FetchBatch("fake", "security_master", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_trade_dates(self, *_): return FetchBatch("fake", "trade_dates", {}, [{"calendar_date": "2026-08-28", "is_trading_day": "1"}], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_daily(self, *_): return FetchBatch("fake", "daily", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
            class AK:
                def fetch_disclosure_schedule(self): return FetchBatch("fake", "disclosure_schedule", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_performance_report(self): return FetchBatch("fake", "performance_report", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_financial_statements(self, _): return {}
                def fetch_spot_snapshot(self): return FetchBatch("fake", "spot_snapshot", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                pilot._run_online(root, store, [], now=datetime(2026, 8, 28, 16, tzinfo=pilot.SHANGHAI))
            self.assertEqual(store.get_job(old_id)["status"], "retryable_failed")
            new_id = store.enqueue_job("ignored", "baostock:security_master:2026-08-28", {})
            self.assertEqual(store.get_job(new_id)["status"], "succeeded")

    def test_blocked_same_day_rerun_reopens_circuit_without_later_source_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            calls = {"calendar": 0, "daily": 0}
            class Bao:
                def fetch_security_master(self): raise SourceBlocked("HTTP 403")
                def fetch_trade_dates(self, *_): calls["calendar"] += 1
                def fetch_daily(self, *_): calls["daily"] += 1
            class AK:
                def fetch_disclosure_schedule(self): return FetchBatch("fake", "disclosure_schedule", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_performance_report(self): return FetchBatch("fake", "performance_report", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_financial_statements(self, _): return {}
                def fetch_spot_snapshot(self): return FetchBatch("fake", "spot_snapshot", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
            store = StateStore(db); store.initialize()
            now = datetime(2026, 8, 28, 16, tzinfo=pilot.SHANGHAI)
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                pilot._run_online(root, store, ["SH600000"], now=now)
                second = pilot._run_online(root, store, ["SH600000"], now=now)
            self.assertEqual(calls, {"calendar": 0, "daily": 0})
            trigger = next(item for item in second["batches"] if item["dataset"] == "baostock:security_master:2026-08-28")
            self.assertEqual(trigger["status"], "terminal_failed")
            self.assertEqual(trigger["error"]["classification"], "blocked")

    def test_financial_statements_run_when_calendar_is_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            calls = {"daily": 0, "financial": 0}
            class Bao:
                def fetch_security_master(self): return FetchBatch("fake", "security_master", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_trade_dates(self, *_): raise RetryableSourceError("calendar temporary")
                def fetch_daily(self, *_): calls["daily"] += 1
            class AK:
                def fetch_disclosure_schedule(self): return FetchBatch("fake", "disclosure_schedule", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_performance_report(self): return FetchBatch("fake", "performance_report", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_financial_statements(self, _): calls["financial"] += 1; return {}
                def fetch_spot_snapshot(self): return FetchBatch("fake", "spot_snapshot", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
            store = StateStore(db); store.initialize()
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                pilot._run_online(root, store, ["SH600000"], now=datetime(2026, 8, 28, 16, tzinfo=pilot.SHANGHAI))
            self.assertEqual(calls["daily"], 0)
            self.assertEqual(calls["financial"], 1)

    def test_pilot_kind_running_lease_is_reported_then_recovered_and_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            store = StateStore(db); store.initialize()
            key = "baostock:security_master:2026-08-28"
            job_id = store.enqueue_job(f"pilot_fetch:{key}", key, {})
            store.lease_next_job([f"pilot_fetch:{key}"], "crashed", 300, "2026-08-28T08:00:00+00:00")
            calls = {"master": 0}
            class Bao:
                def fetch_security_master(self): calls["master"] += 1; return FetchBatch("fake", "security_master", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_trade_dates(self, *_): return FetchBatch("fake", "trade_dates", {}, [{"calendar_date": "2026-08-28", "is_trading_day": "1"}], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_daily(self, *_): return FetchBatch("fake", "daily", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
            class AK:
                def fetch_disclosure_schedule(self): return FetchBatch("fake", "disclosure_schedule", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_performance_report(self): return FetchBatch("fake", "performance_report", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
                def fetch_financial_statements(self, _): return {}
                def fetch_spot_snapshot(self): return FetchBatch("fake", "spot_snapshot", {}, [], "2026-08-28T00:00:00+00:00", "v", {})
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                before = pilot._run_online(root, store, [], now=datetime(2026, 8, 28, 16, 1, tzinfo=pilot.SHANGHAI))
                after = pilot._run_online(root, store, [], now=datetime(2026, 8, 28, 16, 6, tzinfo=pilot.SHANGHAI))
            self.assertEqual(next(item for item in before["batches"] if item["dataset"] == key)["status"], "running")
            self.assertEqual(calls["master"], 1)
            self.assertEqual(store.get_job(job_id)["status"], "succeeded")
            self.assertEqual(next(item for item in after["batches"] if item["dataset"] == "security_master")["task_key"], key)

    def test_weekend_calendar_uses_last_friday_for_daily_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root, db = Path(directory) / "data", Path(directory) / "state.sqlite3"
            calls = []
            class Bao:
                def fetch_security_master(self): return FetchBatch("fake", "security_master", {}, [], "2026-08-30T00:00:00+00:00", "v", {})
                def fetch_trade_dates(self, *_): return FetchBatch("fake", "trade_dates", {}, [{"calendar_date": "2026-08-28", "is_trading_day": "1"}, {"calendar_date": "2026-08-29", "is_trading_day": "0"}, {"calendar_date": "2026-08-30", "is_trading_day": "0"}], "2026-08-30T00:00:00+00:00", "v", {})
                def fetch_daily(self, code, start, end): calls.append((code, start, end)); return FetchBatch("fake", "daily", {}, [], "2026-08-30T00:00:00+00:00", "v", {})
            class AK:
                def fetch_disclosure_schedule(self): return FetchBatch("fake", "disclosure_schedule", {}, [], "2026-08-30T00:00:00+00:00", "v", {})
                def fetch_performance_report(self): return FetchBatch("fake", "performance_report", {}, [], "2026-08-30T00:00:00+00:00", "v", {})
                def fetch_financial_statements(self, _): return {}
                def fetch_spot_snapshot(self): return FetchBatch("fake", "spot_snapshot", {}, [], "2026-08-30T00:00:00+00:00", "v", {})
            store = StateStore(db); store.initialize()
            with patch("ashare_pipeline.sources.BaoStockSource", Bao), patch("ashare_pipeline.sources.AKShareSource", AK):
                result = pilot._run_online(root, store, ["SH600000"], now=datetime(2026, 8, 30, 16, tzinfo=pilot.SHANGHAI))
            self.assertEqual(result["latest_completed_trading_date"], "2026-08-28")
            self.assertEqual(calls, [("sh.600000", "2026-08-24", "2026-08-28")])

    def test_reused_calendar_with_bad_hash_is_not_used_for_daily_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "calendar.json"
            path.write_text(json.dumps({"source": "fake", "dataset": "trade_dates", "request": {}, "records": [{"calendar_date": "2026-08-28", "is_trading_day": "1"}], "fetched_at_utc": "2026-08-28T00:00:00+00:00", "source_version": "v", "metadata": {}}), encoding="utf-8")
            records = pilot._calendar_records([{"dataset": "trade_dates", "path": str(path), "hash": "not-the-content-hash"}])
            self.assertEqual(records, [])
