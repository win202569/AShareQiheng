import io
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from ashare_pipeline.deep_worker import (
    CandidateContext,
    STATEMENT_DATASETS,
    deep_statement_key,
)
from ashare_pipeline.feature_contract import canonical_sha256
from ashare_pipeline.financial_schema import FINANCIAL_REQUEST_VERSION
from ashare_pipeline.snapshot_repository import SnapshotRepository
from ashare_pipeline.snapshot_store import SnapshotStore
from ashare_pipeline.sources import FetchBatch, SourceBlocked
from ashare_pipeline.state_store import StateStore
from ashare_pipeline import orchestrator


def batch(source, dataset, records, request=None, fetched_at="2026-08-29T12:00:00+00:00"):
    return FetchBatch(source, dataset, request or {}, records, fetched_at, "test", {})


def records_hash(records):
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_candidate_documents(root, candidates):
    performance_records = [
        {
            "security_id": security_id,
            "industry": industry,
            "report_period": "2026-06-30",
        }
        for security_id, industry in sorted(candidates.items())
    ]
    prefilter_records = [
        {"security_id": row["security_id"], "industry": row["industry"]}
        for row in performance_records
    ]
    documents = {
        "performance": {
            "schema_version": 2,
            "input_hashes": {"fixture": "performance"},
            "records_hash": canonical_sha256(performance_records),
            "records": performance_records,
        },
        "prefilter": {
            "schema_version": 2,
            "input_hashes": {"fixture": "prefilter"},
            "records_hash": canonical_sha256(prefilter_records),
            "records": prefilter_records,
        },
    }
    for name, document in documents.items():
        path = root / "curated" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )


def exact_statement_batch(security_id, dataset, *, target=True):
    return batch(
        "akshare",
        dataset,
        [
            {
                "SECURITY_CODE": security_id[2:],
                "REPORT_DATE": "2026-06-30" if target else "2025-12-31",
                "NOTICE_DATE": "2026-08-20",
            }
        ],
        {"symbol": security_id, "report_period": "2026-06-30"},
    )


def exact_calendar_batch(now="2026-08-29T12:00:00+00:00"):
    return batch(
        "baostock",
        "trade_dates",
        [
            {"calendar_date": "2026-08-31", "is_trading_day": "1"},
            {"calendar_date": "2026-09-07", "is_trading_day": "1"},
        ],
        {"start_date": "2021-01-01", "end_date": "2026-09-08"},
        now,
    )


class FakeBaoSource:
    def __init__(self):
        self.round = 0
        self.calls = {"security_master": 0, "trade_dates": 0}
        self.trade_date_requests = []
        self.master = [
            {"code": "sz.000001", "code_name": "平安银行", "ipoDate": "1991-04-03", "type": "1", "status": "1"},
            {"code": "sh.600000", "code_name": "浦发银行", "ipoDate": "1999-11-10", "type": "1", "status": "1"},
            {"code": "sh.900901", "code_name": "云赛B股", "type": "1", "status": "1"},
            {"code": "bj.430047", "code_name": "北交样本", "type": "1", "status": "1"},
        ]

    def _time(self):
        return f"2026-08-{29 + self.round:02d}T12:00:00+00:00"

    def fetch_security_master(self):
        self.calls["security_master"] += 1
        return batch("baostock", "security_master", self.master, fetched_at=self._time())

    def fetch_trade_dates(self, start_date, end_date):
        self.calls["trade_dates"] += 1
        self.trade_date_requests.append((start_date, end_date))
        self.round += 1
        return batch(
            "baostock",
            "trade_dates",
            [
                {
                    "calendar_date": (
                        date.fromisoformat(start_date) + timedelta(days=offset)
                    ).isoformat(),
                    "is_trading_day": "1",
                }
                for offset in range(
                    (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days
                    + 1
                )
            ],
            {"start_date": start_date, "end_date": end_date},
            self._time(),
        )


class FakeAKSource:
    def __init__(self):
        self.round = 0
        self.blocked = False
        self.calls = {"disclosure_schedule": 0, "performance_report": 0}
        self.statement_calls = []
        self.performance = [
            {
                "股票代码": "000001", "股票简称": "平安银行", "营业总收入同比增长": 5,
                "净利润同比增长": 6, "净资产收益率": 7, "销售毛利率": 8,
                "每股经营现金流量": 1, "所处行业": "银行", "最新公告日期": "2026-08-20",
            },
            {
                "股票代码": "600000", "股票简称": "浦发银行", "营业总收入同比增长": 4,
                "净利润同比增长": 5, "净资产收益率": 6, "销售毛利率": 7,
                "每股经营现金流量": 2, "所处行业": "银行", "最新公告日期": "2026-08-21",
            },
        ]

    def _time(self):
        self.round += 1
        return f"2026-08-{min(29 + self.round, 31):02d}T13:00:00+00:00"

    def fetch_disclosure_schedule(self):
        self.calls["disclosure_schedule"] += 1
        if self.blocked:
            raise SourceBlocked("429 challenge")
        return batch("akshare", "disclosure_schedule", [{"股票代码": "000001"}], fetched_at=self._time())

    def fetch_performance_report(self):
        self.calls["performance_report"] += 1
        if self.blocked:
            raise AssertionError("circuit breaker should skip later AKShare calls")
        return batch("akshare", "performance_report", self.performance, {"date": "20260630"}, self._time())

    def fetch_financial_statement(self, symbol, dataset, report_period="2026-06-30"):
        self.statement_calls.append((symbol, dataset, report_period))
        return exact_statement_batch(symbol, dataset)


class FakeStatementSource:
    def __init__(self):
        self.calls = []

    def fetch_financial_statement(self, symbol, dataset, report_period="2026-06-30"):
        self.calls.append((symbol, dataset, report_period))
        return exact_statement_batch(symbol, dataset)


class OrchestratorTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.root = self.base / "data"
        self.db = self.base / "state.sqlite3"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_deep_parser_accepts_limit_bounds_and_rejects_outside(self):
        self.assertEqual(
            orchestrator._parser().parse_args(
                ["--root", "data", "--db", "data/state.sqlite3", "deep"]
            ).limit,
            10,
        )
        for valid in (1, 360):
            parsed = orchestrator._parser().parse_args(
                [
                    "--root",
                    "data",
                    "--db",
                    "data/state.sqlite3",
                    "deep",
                    "--limit",
                    str(valid),
                ]
            )
            self.assertEqual(parsed.limit, valid)
        for invalid in (0, 361):
            with self.assertRaises(SystemExit):
                orchestrator._parser().parse_args(
                    [
                        "--root",
                        "data",
                        "--db",
                        "data/state.sqlite3",
                        "deep",
                        "--limit",
                        str(invalid),
                    ]
                )

    def test_enqueue_daily_statement_jobs_is_360_style_idempotent_without_source_calls(self):
        members = {f"SH{index:06d}" for index in range(1, 121)}
        context = CandidateContext(
            candidate_set_hash="a" * 64,
            members=frozenset(members),
            performance_input_hashes={item: "b" * 64 for item in members},
            industries={item: "包装印刷" for item in members},
            reported_target_period={item: True for item in members},
        )
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()

        first = orchestrator.enqueue_daily_statement_jobs(
            store, context, "2026-06-30", "2026-08-29"
        )
        second = orchestrator.enqueue_daily_statement_jobs(
            store, context, "2026-06-30", "2026-08-29"
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 360)
        self.assertEqual(len(store.list_jobs(["deep_statement"])), 360)

    def test_incremental_enqueues_without_statement_calls(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        payload, code = orchestrator.run_command(
            self.root,
            self.root / "state.sqlite3",
            "incremental",
            online=True,
            now_cn="2026-08-29T20:00:00+08:00",
            sources=(bao, ak),
        )

        self.assertEqual(code, 0)
        self.assertEqual(ak.statement_calls, [])
        store = StateStore(self.root / "state.sqlite3")
        self.assertEqual(len(store.list_jobs(["deep_statement"])), 6)
        self.assertFalse(payload["formal_score_ready"])

    def test_verified_calendar_cache_and_injected_deep_source_construct_no_defaults(self):
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        repository = SnapshotRepository(self.root, store)
        expected, _ = repository.persist(exact_calendar_batch())
        source = FakeStatementSource()

        with patch(
            "ashare_pipeline.orchestrator._default_calendar_source",
            side_effect=AssertionError("calendar default constructed"),
        ), patch(
            "ashare_pipeline.orchestrator._default_deep_source",
            side_effect=AssertionError("deep default constructed"),
        ):
            observed_repository, observed_source, calendar = orchestrator._deep_dependencies(
                self.root,
                store,
                now=orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
                online=True,
                sources=None,
                snapshot_store=None,
                deep_source=source,
            )

        self.assertEqual(observed_repository.data_root, self.root.resolve())
        self.assertIs(observed_source, source)
        self.assertEqual(calendar.id, expected.id)

    def test_tampered_calendar_cache_fails_closed(self):
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        repository = SnapshotRepository(self.root, store)
        calendar, _ = repository.persist(exact_calendar_batch())
        (self.base / calendar.payload_path).write_text("{}", encoding="utf-8")
        source = FakeStatementSource()
        bao = FakeBaoSource()

        with self.assertRaisesRegex(OSError, "hash|invalid snapshot payload"):
            orchestrator._deep_dependencies(
                self.root,
                store,
                now=orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
                online=True,
                sources=(bao, source),
                snapshot_store=None,
                deep_source=source,
            )
        self.assertEqual(source.calls, [])
        self.assertEqual(bao.trade_date_requests, [])

    def test_changed_calendar_request_is_not_hidden_by_cached_short_job(self):
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        old_key = "fetch_source:baostock:trade_dates:2026-08-29"
        old = store.enqueue_job(old_key, old_key, {"request": "short"})
        store.lease_next_job([old_key], "seed", 3600, "2026-08-29T00:00:00+00:00")
        store.complete_job(old, {"batches": [{"dataset": "trade_dates"}]})
        bao, ak = FakeBaoSource(), FakeAKSource()

        orchestrator.run_command(
            self.root,
            self.root / "state.sqlite3",
            "bootstrap",
            online=True,
            now_cn="2026-08-29T20:00:00+08:00",
            sources=(bao, ak),
        )

        self.assertEqual(bao.trade_date_requests, [("2021-01-01", "2026-09-08")])
        current_key = orchestrator._feature_calendar_job_key(
            orchestrator._now_cn("2026-08-29T20:00:00+08:00")
        )
        current = next(
            item for item in store.list_jobs() if item["idempotency_key"] == current_key
        )
        self.assertEqual(current["status"], "succeeded")

    def test_cached_long_calendar_reuse_verifies_exact_snapshot_without_refetch(self):
        for failure_mode in (
            "tampered",
            "missing_file",
            "missing_ref",
            "missing_result",
            "wrong_result",
            "wrong_rows",
            "wrong_source_version",
            "wrong_semantic_hash",
            "extra_field",
            "nonboolean_created",
        ):
            with self.subTest(failure_mode=failure_mode):
                data_root = self.base / failure_mode / "data"
                database = data_root / "state.sqlite3"
                bao, ak = FakeBaoSource(), FakeAKSource()
                _, first_code = orchestrator.run_command(
                    data_root,
                    database,
                    "bootstrap",
                    online=True,
                    now_cn="2026-08-29T20:00:00+08:00",
                    sources=(bao, ak),
                )
                self.assertEqual(first_code, 0)
                store = StateStore(database)
                repository = SnapshotRepository(data_root, store)
                calendar = repository.find_exact(
                    "baostock",
                    "trade_dates",
                    {"start_date": "2021-01-01", "end_date": "2026-09-08"},
                )
                self.assertIsNotNone(calendar)
                calendar_path = repository.project_root / calendar.payload_path
                if failure_mode == "tampered":
                    calendar_path.write_text("{}", encoding="utf-8")
                elif failure_mode == "missing_file":
                    calendar_path.unlink()
                elif failure_mode == "missing_ref":
                    with closing(sqlite3.connect(database)) as connection:
                        connection.execute(
                            "DELETE FROM source_snapshot WHERE id=?", (calendar.id,)
                        )
                        connection.commit()
                else:
                    current_key = orchestrator._feature_calendar_job_key(
                        orchestrator._now_cn("2026-08-29T20:00:00+08:00")
                    )
                    with closing(sqlite3.connect(database)) as connection:
                        stored = connection.execute(
                            "SELECT result_json FROM job WHERE idempotency_key=?",
                            (current_key,),
                        ).fetchone()
                        cached_result = json.loads(stored[0])
                        if failure_mode == "missing_result":
                            cached_result = {"batches": []}
                        elif failure_mode == "wrong_result":
                            cached_result["batches"][0]["request"] = {
                                "start_date": "2026-08-24",
                                "end_date": "2026-09-08",
                            }
                        elif failure_mode == "wrong_rows":
                            cached_result["batches"][0]["rows"] = 1
                        elif failure_mode == "wrong_source_version":
                            cached_result["batches"][0]["source_version"] = "tampered"
                        elif failure_mode == "wrong_semantic_hash":
                            cached_result["batches"][0]["semantic_hash"] = "0" * 64
                        elif failure_mode == "extra_field":
                            cached_result["batches"][0]["secret"] = "must-not-leak"
                        else:
                            cached_result["batches"][0]["created"] = 1
                        connection.execute(
                            "UPDATE job SET result_json=? WHERE idempotency_key=?",
                            (json.dumps(cached_result), current_key),
                        )
                        connection.commit()

                with self.assertRaisesRegex(OSError, "calendar|snapshot|hash|payload"):
                    orchestrator.run_command(
                        data_root,
                        database,
                        "incremental",
                        online=True,
                        now_cn="2026-08-29T20:01:00+08:00",
                        sources=(bao, ak),
                    )
                self.assertEqual(bao.calls["trade_dates"], 1)

    def test_cached_long_calendar_public_result_is_derived_from_verified_snapshot(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        _, first_code = orchestrator.run_command(
            self.root,
            self.root / "state.sqlite3",
            "bootstrap",
            online=True,
            now_cn="2026-08-29T20:00:00+08:00",
            sources=(bao, ak),
        )
        payload, second_code = orchestrator.run_command(
            self.root,
            self.root / "state.sqlite3",
            "incremental",
            online=True,
            now_cn="2026-08-29T20:01:00+08:00",
            sources=(bao, ak),
        )

        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(bao.calls["trade_dates"], 1)
        store = StateStore(self.root / "state.sqlite3")
        repository = SnapshotRepository(self.root, store)
        calendar = repository.find_exact(
            "baostock",
            "trade_dates",
            {"start_date": "2021-01-01", "end_date": "2026-09-08"},
        )
        verified = repository.read_verified(calendar)
        semantic_payload = {
            "source": verified.batch.source,
            "dataset": verified.batch.dataset,
            "request": dict(verified.batch.request),
            "records": list(verified.batch.records),
            "source_version": verified.batch.source_version,
            "metadata": dict(verified.batch.metadata),
        }
        semantic_hash = hashlib.sha256(
            json.dumps(
                semantic_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        cached = next(
            item
            for item in payload["source_batches"]
            if item.get("dataset") == "trade_dates"
        )

        self.assertEqual(
            cached,
            {
                "source": "baostock",
                "dataset": "trade_dates",
                "status": "succeeded",
                "cached": True,
                "source_version": verified.batch.source_version,
                "request": {
                    "start_date": "2021-01-01",
                    "end_date": "2026-09-08",
                },
                "rows": calendar.row_count,
                "hash": calendar.payload_hash,
                "path": calendar.payload_path,
                "semantic_hash": semantic_hash,
                "created": False,
            },
        )

    def test_versioned_calendar_job_rejects_nonexact_or_multiple_batches(self):
        exact = exact_calendar_batch()
        cases = {
            "wrong_source": batch(
                "akshare", "trade_dates", list(exact.records), dict(exact.request)
            ),
            "wrong_dataset": batch(
                "baostock", "security_master", list(exact.records), dict(exact.request)
            ),
            "wrong_request": batch(
                "baostock",
                "trade_dates",
                list(exact.records),
                {"start_date": "2026-08-24", "end_date": "2026-09-08"},
            ),
            "multiple": {"first": exact, "second": exact},
        }
        for label, response in cases.items():
            with self.subTest(label=label):
                data_root = self.base / label / "data"
                database = data_root / "state.sqlite3"
                bao, ak = FakeBaoSource(), FakeAKSource()

                def malformed_fetch(start_date, end_date, *, value=response):
                    bao.calls["trade_dates"] += 1
                    bao.trade_date_requests.append((start_date, end_date))
                    return value

                bao.fetch_trade_dates = malformed_fetch
                payload, code = orchestrator.run_command(
                    data_root,
                    database,
                    "bootstrap",
                    online=True,
                    now_cn="2026-08-29T20:00:00+08:00",
                    sources=(bao, ak),
                )

                self.assertEqual(code, 0)
                store = StateStore(database)
                current_key = orchestrator._feature_calendar_job_key(
                    orchestrator._now_cn("2026-08-29T20:00:00+08:00")
                )
                current = next(
                    job
                    for job in store.list_jobs()
                    if job["idempotency_key"] == current_key
                )
                self.assertNotEqual(current["status"], "succeeded")
                self.assertFalse(
                    any(
                        item.get("dataset") == "trade_dates"
                        and item.get("status") == "succeeded"
                        for item in payload["source_batches"]
                    )
                )
                self.assertIsNone(
                    SnapshotRepository(data_root, store).find_exact(
                        "baostock",
                        "trade_dates",
                        {"start_date": "2021-01-01", "end_date": "2026-09-08"},
                    )
                )

    def test_offline_deep_constructs_no_source(self):
        write_candidate_documents(self.root, {"SH600001": "包装印刷"})
        with patch(
            "ashare_pipeline.orchestrator._default_calendar_source",
            side_effect=AssertionError("calendar default constructed"),
        ), patch(
            "ashare_pipeline.orchestrator._default_deep_source",
            side_effect=AssertionError("deep default constructed"),
        ), patch(
            "ashare_pipeline.orchestrator._default_sources",
            side_effect=AssertionError("legacy defaults constructed"),
        ):
            payload, code = orchestrator.run_command(
                self.root,
                self.root / "state.sqlite3",
                "deep",
                online=False,
                now_cn="2026-08-29T20:00:00+08:00",
            )

        self.assertEqual(code, 0)
        self.assertEqual(payload["deep_run"]["remote_attempts"], 0)
        with closing(sqlite3.connect(self.root / "state.sqlite3")) as connection:
            params = json.loads(
                connection.execute(
                    "SELECT params_json FROM run ORDER BY started_at DESC LIMIT 1"
                ).fetchone()[0]
            )
        self.assertEqual(params, {"limit": 10, "online": False})

    def test_online_limit_one_calls_at_most_one_statement(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        orchestrator.run_command(
            self.root,
            self.root / "state.sqlite3",
            "bootstrap",
            online=True,
            now_cn="2026-08-29T20:00:00+08:00",
            sources=(bao, ak),
        )
        source = FakeStatementSource()

        payload, code = orchestrator.run_command(
            self.root,
            self.root / "state.sqlite3",
            "deep",
            online=True,
            now_cn="2026-08-29T20:01:00+08:00",
            deep_source=source,
            limit=1,
        )

        self.assertEqual(code, 0)
        self.assertEqual(len(source.calls), 1)
        self.assertEqual(payload["deep_run"]["remote_attempts"], 1)

    def test_status_financial_coverage_requires_three_verified_target_snapshots(self):
        write_candidate_documents(
            self.root, {"SH600001": "包装印刷", "SH600002": "包装印刷"}
        )
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        context = orchestrator.load_candidate_context(self.root)
        orchestrator.enqueue_daily_statement_jobs(
            store, context, "2026-06-30", "2026-08-29"
        )
        repository = SnapshotRepository(self.root, store)
        for security_id, datasets in {
            "SH600001": STATEMENT_DATASETS,
            "SH600002": ("balance_sheet", "profit_sheet"),
        }.items():
            for dataset in datasets:
                repository.persist(exact_statement_batch(security_id, dataset))

        status, code = orchestrator.run_command(
            self.root,
            self.root / "state.sqlite3",
            "status",
            now_cn="2026-08-29T20:00:00+08:00",
        )

        self.assertEqual(code, 0)
        self.assertEqual(
            status["deep"]["candidate_financial_coverage"],
            {"numerator": 1, "denominator": 2, "rate": 0.5},
        )
        self.assertEqual(len(status["deep"]["incomplete_candidates"]), 1)
        self.assertEqual(
            status["deep"]["incomplete_candidates"][0]["missing_datasets"],
            ["cash_flow_sheet"],
        )
        self.assertEqual(status["deep"]["expired_current_lease_count"], 0)
        self.assertEqual(status["deep"]["unknown_failure_count"], 0)
        self.assertFalse(status["formal_score_ready"])

    def test_verified_snapshot_count_does_not_excuse_a_missing_target_period(self):
        write_candidate_documents(self.root, {"SH600001": "包装印刷"})
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        context = orchestrator.load_candidate_context(self.root)
        orchestrator.enqueue_daily_statement_jobs(
            store, context, "2026-06-30", "2026-08-29"
        )
        repository = SnapshotRepository(self.root, store)
        for dataset in STATEMENT_DATASETS:
            repository.persist(
                exact_statement_batch(
                    "SH600001", dataset, target=dataset != "cash_flow_sheet"
                )
            )

        progress = orchestrator.build_deep_progress(
            self.root,
            store,
            repository,
            context,
            orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
        )

        self.assertEqual(
            progress["statement_snapshot_counts"],
            {dataset: 1 for dataset in sorted(STATEMENT_DATASETS)},
        )
        self.assertEqual(progress["candidate_financial_coverage"]["numerator"], 0)
        self.assertEqual(
            progress["incomplete_candidates"][0]["error_classifications"],
            ["target_period_missing"],
        )

    def test_progress_excludes_stale_request_versions(self):
        write_candidate_documents(self.root, {"SH600001": "包装印刷"})
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        context = orchestrator.load_candidate_context(self.root)
        common = {
            "security_id": "SH600001",
            "report_period": "2026-06-30",
            "candidate_set_hash": "f" * 64,
            "performance_input_hash": context.performance_input_hashes["SH600001"],
        }
        store.enqueue_job(
            "deep_statement",
            "stale-version",
            {
                **common,
                "dataset": "profit_sheet",
                "request_version": "old-request-version",
                "refresh_date": "2026-08-29",
            },
        )
        store.enqueue_job(
            "deep_statement",
            "stale-date",
            {
                **common,
                "dataset": "cash_flow_sheet",
                "request_version": FINANCIAL_REQUEST_VERSION,
                "refresh_date": "2026-08-28",
            },
        )
        store.enqueue_job(
            "deep_statement",
            deep_statement_key(
                "SH600001", "balance_sheet", "2026-06-30", "2026-08-29"
            ),
            {
                **common,
                "dataset": "balance_sheet",
                "request_version": FINANCIAL_REQUEST_VERSION,
                "refresh_date": "2026-08-29",
            },
        )
        store.enqueue_job(
            "deep_statement",
            "stale-report-period",
            {
                **common,
                "dataset": "balance_sheet",
                "report_period": "2025-12-31",
                "request_version": FINANCIAL_REQUEST_VERSION,
                "refresh_date": "2026-08-29",
            },
        )

        progress = orchestrator.build_deep_progress(
            self.root,
            store,
            SnapshotRepository(self.root, store),
            context,
            orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
        )

        self.assertEqual(progress["deep_statement_job_counts"]["balance_sheet"], {"pending": 1})
        self.assertEqual(progress["deep_statement_job_counts"]["profit_sheet"], {})
        self.assertEqual(progress["deep_statement_job_counts"]["cash_flow_sheet"], {})
        self.assertEqual(len(progress["incomplete_candidates"]), 1)

    def test_progress_uses_only_canonical_current_parent_and_statement_slots(self):
        write_candidate_documents(self.root, {"SH600001": "包装印刷"})
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        context = orchestrator.load_candidate_context(self.root)
        current_hash = context.performance_input_hashes["SH600001"]
        current_parent_key = f"deep_financial:SH600001:{current_hash}"
        store.enqueue_job(
            "deep_financial",
            "historical-parent",
            {
                "security_id": "SH600001",
                "input_hash": "c" * 64,
                "report_period": "2026-06-30",
            },
        )
        store.enqueue_job(
            "deep_financial",
            current_parent_key,
            {
                "security_id": "SH600001",
                "input_hash": current_hash,
                "report_period": "2026-06-30",
            },
        )
        store.enqueue_job(
            "deep_financial",
            "corrupt-current-parent",
            {
                "security_id": "SH600001",
                "input_hash": current_hash,
                "report_period": "2026-06-30",
            },
        )
        orchestrator.enqueue_daily_statement_jobs(
            store, context, "2026-06-30", "2026-08-29"
        )
        corrupt_statement = store.enqueue_job(
            "deep_statement",
            "corrupt-current-balance-slot",
            {
                "security_id": "SH600001",
                "dataset": "balance_sheet",
                "report_period": "2026-06-30",
                "candidate_set_hash": context.candidate_set_hash,
                "performance_input_hash": current_hash,
                "request_version": FINANCIAL_REQUEST_VERSION,
                "refresh_date": "2026-08-29",
            },
        )
        with closing(sqlite3.connect(store.db_path)) as connection:
            connection.execute(
                "UPDATE job SET status='terminal_failed',last_error_json=? WHERE id=?",
                (json.dumps({"error_classification": "worker_error"}), corrupt_statement),
            )
            connection.commit()

        progress = orchestrator.build_deep_progress(
            self.root,
            store,
            SnapshotRepository(self.root, store),
            context,
            orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
        )

        self.assertEqual(progress["deep_parent_job_counts"], {"pending": 1})
        self.assertEqual(
            progress["deep_statement_job_counts"],
            {
                "balance_sheet": {"pending": 1},
                "profit_sheet": {"pending": 1},
                "cash_flow_sheet": {"pending": 1},
            },
        )
        self.assertEqual(progress["unknown_failure_count"], 2)
        self.assertEqual(
            progress["incomplete_candidates"][0]["job_states"], ["pending"]
        )
        self.assertEqual(
            progress["incomplete_candidates"][0]["error_classifications"],
            ["pending"],
        )

    def test_progress_classifies_current_circuits_expired_leases_and_unknown_failures(self):
        write_candidate_documents(
            self.root,
            {
                "SH600001": "包装印刷",
                "SH600002": "包装印刷",
                "SH600003": "包装印刷",
            },
        )
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        context = orchestrator.load_candidate_context(self.root)
        orchestrator.enqueue_daily_statement_jobs(
            store, context, "2026-06-30", "2026-08-29"
        )
        jobs = store.list_jobs(["deep_statement"])
        by_slot = {
            (job["payload"]["security_id"], job["payload"]["dataset"]): job["id"]
            for job in jobs
        }
        with closing(sqlite3.connect(store.db_path)) as connection:
            connection.execute(
                """UPDATE job SET status='retryable_failed',last_error_json=?,
                next_retry_at=? WHERE id=?""",
                (
                    json.dumps({"error_classification": "source_blocked"}),
                    "2026-08-29T21:00:00+08:00",
                    by_slot[("SH600001", "balance_sheet")],
                ),
            )
            connection.execute(
                """UPDATE job SET status='running',lease_worker='worker',
                lease_expires_at=? WHERE id=?""",
                (
                    "2026-08-29T19:00:00+08:00",
                    by_slot[("SH600002", "balance_sheet")],
                ),
            )
            connection.execute(
                "UPDATE job SET status='terminal_failed',last_error_json=? WHERE id=?",
                (
                    json.dumps({"error_classification": "worker_error"}),
                    by_slot[("SH600003", "balance_sheet")],
                ),
            )
            connection.commit()

        progress = orchestrator.build_deep_progress(
            self.root,
            store,
            SnapshotRepository(self.root, store),
            context,
            orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
        )

        self.assertEqual(progress["active_circuit_breakers"], ["akshare"])
        self.assertEqual(progress["expired_current_lease_count"], 1)
        self.assertEqual(progress["unknown_failure_count"], 1)
        self.assertEqual(
            [item["security_id"] for item in progress["incomplete_candidates"]],
            ["SH600001", "SH600002", "SH600003"],
        )
        for item in progress["incomplete_candidates"]:
            self.assertEqual(item["missing_datasets"], sorted(item["missing_datasets"]))
            self.assertEqual(item["job_states"], sorted(item["job_states"]))
            self.assertEqual(
                item["error_classifications"],
                sorted(item["error_classifications"]),
            )
            self.assertTrue(
                set(item["error_classifications"])
                <= orchestrator._PROGRESS_CLASSIFICATIONS
            )

    def test_progress_feature_counts_require_current_candidate_hash_and_contract(self):
        write_candidate_documents(self.root, {"SH600001": "包装印刷"})
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        context = orchestrator.load_candidate_context(self.root)
        rows = [
            ("current", context.candidate_set_hash, "feature-contract-v1", "2026-06-30", "partial"),
            ("stale-hash", "f" * 64, "feature-contract-v1", "2026-06-30", "blocked"),
            ("stale-contract", context.candidate_set_hash, "feature-contract-v0", "2026-06-30", "blocked"),
            ("stale-period", context.candidate_set_hash, "feature-contract-v1", "2025-12-31", "blocked"),
        ]
        with closing(sqlite3.connect(store.db_path)) as connection:
            for index, (row_id, candidate_hash, contract, report_period, status) in enumerate(rows):
                connection.execute(
                    """INSERT INTO feature_set
                    (id,security_id,report_period,as_of_utc,candidate_set_hash,
                     template_id,template_version,contract_version,input_hash,status,
                     financial_coverage,dimension_status_json,confidence_inputs_json,
                     blockers_json,bundle_hash,bundle_path,missing_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row_id,
                        "SH600001",
                        report_period,
                        f"2026-08-29T0{index}:00:00+00:00",
                        candidate_hash,
                        "general_nonfinancial",
                        "template-registry-v1",
                        contract,
                        str(index) * 64,
                        status,
                        0.5,
                        "{}",
                        "{}",
                        "[]",
                        canonical_sha256(row_id),
                        f"data/curated/formal_features/{row_id}.json",
                        json.dumps([{"missing_reason": "fact_missing"}]),
                        f"2026-08-29T0{index}:00:00+00:00",
                    ),
                )
            connection.commit()

        progress = orchestrator.build_deep_progress(
            self.root,
            store,
            SnapshotRepository(self.root, store),
            context,
            orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
        )

        self.assertEqual(
            progress["feature_set_counts"],
            {"partial": 1, "financial_ready": 0, "blocked": 0},
        )
        self.assertEqual(progress["template_counts"], {"general_nonfinancial": 1})
        self.assertEqual(progress["missing_reason_counts"], {"fact_missing": 1})

    def test_status_fails_closed_when_curated_candidate_documents_are_tampered(self):
        write_candidate_documents(self.root, {"SH600001": "包装印刷"})
        path = self.root / "curated" / "prefilter.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["records"][0]["industry"] = "被篡改"
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "records_hash"):
            orchestrator.run_command(
                self.root,
                self.root / "state.sqlite3",
                "status",
                now_cn="2026-08-29T20:00:00+08:00",
            )

    def test_build_deep_progress_rejects_mismatched_repository_root_or_store(self):
        write_candidate_documents(self.root, {"SH600001": "包装印刷"})
        store = StateStore(self.root / "state.sqlite3")
        store.initialize()
        context = orchestrator.load_candidate_context(self.root)
        other_root = self.base / "other-data"
        other_store = StateStore(other_root / "state.sqlite3")
        other_store.initialize()
        other_repository = SnapshotRepository(other_root, other_store)

        with self.assertRaisesRegex(ValueError, "root"):
            orchestrator.build_deep_progress(
                self.root,
                store,
                other_repository,
                context,
                orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
            )
        with self.assertRaisesRegex(ValueError, "state store"):
            orchestrator.build_deep_progress(
                self.root,
                store,
                SnapshotRepository(self.root, other_store),
                context,
                orchestrator._now_cn("2026-08-29T20:00:00+08:00"),
            )

    def install_market_evidence(self, records, *, universe_hash=None, declared_snapshot_hashes=None):
        universe_document = json.loads(
            (self.root / "curated" / "universe.json").read_text(encoding="utf-8")
        )
        batch_value = FetchBatch(
            "baostock",
            "daily",
            {"date": "2026-08-31"},
            records,
            "2026-08-31T08:00:00+00:00",
            "test",
            {},
        )
        path, digest, _ = SnapshotStore(self.root).write(batch_value)
        store = StateStore(self.db)
        store.initialize()
        store.record_snapshot(
            "baostock", "daily", "test-market", digest, str(path.resolve()),
            len(records), batch_value.fetched_at_utc,
        )
        expected_universe_hash = records_hash(universe_document["records"])
        evidence = {
            "schema_version": 2,
            "date": "2026-08-31",
            "input_hashes": {
                "universe_records": universe_hash or expected_universe_hash,
                "source_snapshots": declared_snapshot_hashes or [digest],
            },
            "records": records,
        }
        (self.root / "curated" / "market_2026-08-31.json").write_text(
            json.dumps(evidence, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        return digest

    def latest_run(self):
        with closing(sqlite3.connect(self.db)) as connection:
            return connection.execute(
                "SELECT mode, status, error FROM run ORDER BY started_at DESC LIMIT 1"
            ).fetchone()

    def test_offline_bootstrap_never_builds_sources_and_atomically_writes_status(self):
        output = io.StringIO()
        real_replace = os.replace
        with patch("ashare_pipeline.orchestrator._default_sources", side_effect=AssertionError("network")):
            with patch("ashare_pipeline.orchestrator.os.replace", side_effect=real_replace) as replaced:
                with redirect_stdout(output):
                    exit_code = orchestrator.main(
                        ["--root", str(self.root), "--db", str(self.db), "bootstrap"]
                    )

        status = json.loads(output.getvalue())
        status_path = self.root / "status" / "pipeline_status.json"
        self.assertEqual(exit_code, 0)
        self.assertEqual(status["pipeline_state"], "pending")
        self.assertEqual(status["mode"], "offline")
        self.assertTrue(self.db.exists())
        self.assertEqual(json.loads(status_path.read_text(encoding="utf-8"))["pipeline_state"], "pending")
        status_replace = next(call for call in replaced.call_args_list if Path(call.args[1]) == status_path)
        self.assertTrue(str(status_replace.args[0]).endswith(".part"))
        self.assertEqual(list(self.root.rglob("*.part")), [])

    def test_failures_after_start_run_close_run_as_failed_and_preserve_original_error(self):
        with patch("ashare_pipeline.orchestrator._rebuild_curated", side_effect=RuntimeError("curation exploded")):
            with self.assertRaisesRegex(RuntimeError, "curation exploded"):
                orchestrator.run_command(
                    self.root, self.db, "bootstrap", online=True,
                    now_cn="2026-08-29T22:00:00+08:00",
                    sources=(FakeBaoSource(), FakeAKSource()),
                )
        self.assertEqual(self.latest_run()[1], "failed")
        self.assertIn("curation exploded", self.latest_run()[2])

        with patch("ashare_pipeline.orchestrator._atomic_write_json", side_effect=OSError("status disk full")):
            with self.assertRaisesRegex(OSError, "status disk full"):
                orchestrator.run_command(
                    self.root, self.db, "incremental", online=False,
                    now_cn="2026-08-30T22:00:00+08:00",
                )
        self.assertEqual(self.latest_run()[1], "failed")
        self.assertIn("status disk full", self.latest_run()[2])

        with patch("ashare_pipeline.orchestrator._finalize", side_effect=ValueError("final gate exploded")):
            with self.assertRaisesRegex(ValueError, "final gate exploded"):
                orchestrator.run_command(
                    self.root, self.db, "finalize", now_cn="2026-09-01T00:00:00+08:00"
                )
        self.assertEqual(self.latest_run()[1], "failed")
        self.assertIn("final gate exploded", self.latest_run()[2])

    def test_failure_status_write_error_does_not_mask_original_pipeline_error(self):
        with patch("ashare_pipeline.orchestrator._rebuild_curated", side_effect=RuntimeError("original failure")):
            with patch.object(StateStore, "finish_run", side_effect=OSError("cannot mark failed")):
                with self.assertRaisesRegex(RuntimeError, "original failure"):
                    orchestrator.run_command(
                        self.root, self.db, "bootstrap", online=True,
                        now_cn="2026-08-29T22:00:00+08:00",
                        sources=(FakeBaoSource(), FakeAKSource()),
                    )

    def test_online_incremental_is_content_idempotent_and_enqueues_only_changed_company(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        first, first_code = orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(bao, ak),
        )

        self.assertEqual(first_code, 0)
        universe_doc = json.loads((self.root / "curated" / "universe.json").read_text(encoding="utf-8"))
        prefilter_doc = json.loads((self.root / "curated" / "prefilter.json").read_text(encoding="utf-8"))
        self.assertEqual(universe_doc["metrics"]["universe_count"], 2)
        self.assertEqual(prefilter_doc["metrics"]["candidate_count"], 2)
        self.assertFalse(prefilter_doc["metrics"]["is_official_score"])

        with closing(sqlite3.connect(self.db)) as connection:
            initial_snapshots = connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0]
            initial_deep_jobs = connection.execute("SELECT COUNT(*) FROM job WHERE kind = 'deep_financial'").fetchone()[0]
            score_states = connection.execute("SELECT DISTINCT state, scores_json FROM score_item").fetchall()
        self.assertEqual(initial_snapshots, 4)
        self.assertEqual(initial_deep_jobs, 2)
        self.assertEqual(score_states, [("partial", None)])

        _, second_code = orchestrator.run_command(
            self.root, self.db, "incremental", online=True,
            now_cn="2026-08-30T22:00:00+08:00", sources=(bao, ak),
        )
        with closing(sqlite3.connect(self.db)) as connection:
            unchanged_snapshots = connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0]
            unchanged_deep_jobs = connection.execute("SELECT COUNT(*) FROM job WHERE kind = 'deep_financial'").fetchone()[0]
        self.assertEqual(second_code, 0)
        self.assertEqual(unchanged_snapshots, initial_snapshots + 1)
        self.assertEqual(unchanged_deep_jobs, initial_deep_jobs)

        ak.performance[0] = {**ak.performance[0], "净利润同比增长": 20, "最新公告日期": "2026-08-31"}
        _, third_code = orchestrator.run_command(
            self.root, self.db, "incremental", online=True,
            now_cn="2026-08-31T22:00:00+08:00", sources=(bao, ak),
        )
        with closing(sqlite3.connect(self.db)) as connection:
            changed_deep_jobs = connection.execute("SELECT COUNT(*) FROM job WHERE kind = 'deep_financial'").fetchone()[0]
        self.assertEqual(third_code, 0)
        self.assertEqual(changed_deep_jobs, initial_deep_jobs + 1)

    def test_relative_root_online_run_persists_resolvable_snapshot_paths_and_rebuilds_curated(self):
        relative_root = Path(os.path.relpath(self.root, Path.cwd()))
        relative_db = Path(os.path.relpath(self.db, Path.cwd()))

        status, code = orchestrator.run_command(
            relative_root,
            relative_db,
            "bootstrap",
            online=True,
            now_cn="2026-08-29T22:00:00+08:00",
            sources=(FakeBaoSource(), FakeAKSource()),
        )

        self.assertEqual(code, 0)
        self.assertEqual(status["curated"]["universe"]["universe_count"], 2)
        self.assertTrue((self.root / "curated" / "performance.json").exists())
        with closing(sqlite3.connect(self.db)) as connection:
            paths = [row[0] for row in connection.execute("SELECT payload_path FROM source_snapshot")]
        self.assertTrue(paths)
        self.assertTrue(
            all(Path(path).is_absolute() or path.startswith("data/") for path in paths)
        )

    def test_curated_documents_embed_ruleset_fingerprint_and_stale_artifact_is_rebuilt(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(bao, ak),
        )
        paths = [
            self.root / "curated" / "universe.json",
            self.root / "curated" / "performance.json",
            self.root / "curated" / "prefilter.json",
            self.root / "status" / "quality.json",
        ]
        for path in paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("curation_schema_version", document["input_hashes"])
            self.assertIn("curation_ruleset_hash", document["input_hashes"])

        stale_path = paths[0]
        stale = json.loads(stale_path.read_text(encoding="utf-8"))
        stale["schema_version"] = 0
        stale["input_hashes"]["curation_ruleset_hash"] = "stale"
        stale["records"] = []
        stale_path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

        orchestrator.run_command(
            self.root, self.db, "incremental", online=True,
            now_cn="2026-08-29T22:05:00+08:00", sources=(bao, ak),
        )
        rebuilt = json.loads(stale_path.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["schema_version"], orchestrator.CURATED_SCHEMA_VERSION)
        self.assertNotEqual(rebuilt["input_hashes"]["curation_ruleset_hash"], "stale")
        self.assertEqual(len(rebuilt["records"]), 2)

    def test_full_prefilter_inputs_do_not_claim_full_v2_formal_feature_coverage(self):
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(FakeBaoSource(), FakeAKSource()),
        )

        prefilter = json.loads(
            (self.root / "curated" / "prefilter.json").read_text(encoding="utf-8")
        )
        self.assertTrue(all(row["coverage"] == 1.0 for row in prefilter["records"]))
        with closing(sqlite3.connect(self.db)) as connection:
            formal_coverages = [row[0] for row in connection.execute("SELECT coverage FROM score_item")]
        self.assertTrue(formal_coverages)
        self.assertTrue(all(coverage == 0.0 for coverage in formal_coverages))

    def test_post_cutoff_revision_is_separate_and_never_mutates_frozen_performance(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        original = dict(ak.performance[0])
        original["最新公告日期"] = "2026-08-31T23:00:00+08:00"
        ak.performance = [original, ak.performance[1]]
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-31T23:30:00+08:00", sources=(bao, ak),
        )
        frozen_path = self.root / "curated" / "performance.json"
        before_late_observation = frozen_path.read_bytes()

        revision = {
            **original,
            "净利润同比增长": 99,
            "最新公告日期": "2026-09-01T00:01:00+08:00",
        }
        # Real latest-only tables may replace the in-cutoff row with the late revision.
        ak.performance = [revision, ak.performance[1]]

        orchestrator.run_command(
            self.root, self.db, "incremental", online=True,
            now_cn="2026-09-01T06:00:00+08:00", sources=(bao, ak),
        )

        frozen = json.loads(
            frozen_path.read_text(encoding="utf-8")
        )
        observed = json.loads(
            (self.root / "curated" / "performance_post_cutoff.json").read_text(encoding="utf-8")
        )
        frozen_row = next(row for row in frozen["records"] if row["security_id"] == "SZ000001")
        observed_row = next(row for row in observed["records"] if row["security_id"] == "SZ000001")
        self.assertEqual(frozen_row["net_profit_yoy"], 6.0)
        self.assertEqual(observed_row["net_profit_yoy"], 99.0)
        self.assertEqual(frozen_path.read_bytes(), before_late_observation)
        self.assertTrue(frozen["metrics"]["frozen_cutoff"])
        self.assertFalse(observed["metrics"]["is_official_score"])
        quality = json.loads(
            (self.root / "status" / "quality.json").read_text(encoding="utf-8")
        )["metrics"]
        self.assertEqual(quality["post_cutoff_observation_rows"], 1)

    def test_source_block_opens_circuit_and_preserves_previous_curated_success(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(bao, ak),
        )
        prior = (self.root / "curated" / "performance.json").read_bytes()
        ak.blocked = True

        status, code = orchestrator.run_command(
            self.root, self.db, "incremental", online=True,
            now_cn="2026-08-30T22:00:00+08:00", sources=(bao, ak),
        )

        self.assertEqual(code, 0)
        self.assertIn("akshare", status["circuit_breakers"])
        self.assertEqual(status["source_errors"][0]["classification"], "blocked")
        self.assertEqual((self.root / "curated" / "performance.json").read_bytes(), prior)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertGreater(
                connection.execute("SELECT COUNT(*) FROM job WHERE status = 'retryable_failed'").fetchone()[0], 0
            )

    def test_cached_blocked_job_reopens_circuit_and_preserves_trigger_error(self):
        store = StateStore(self.db)
        store.initialize()
        kind = "fetch_source:akshare:disclosure_schedule:2026-08-29"
        job_id = store.enqueue_job(kind, kind, {"source": "akshare", "dataset": "disclosure_schedule"})
        store.lease_next_job([kind], "seed", 3600, "2026-08-29T12:00:00+00:00")
        store.fail_job(
            job_id,
            {"classification": "blocked", "error": "429 cached challenge"},
            True,
            "2026-08-30T00:00:00+00:00",
        )
        bao, ak = FakeBaoSource(), FakeAKSource()

        status, code = orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(bao, ak),
        )

        self.assertEqual(code, 0)
        self.assertIn("akshare", status["circuit_breakers"])
        by_dataset = {item["dataset"]: item for item in status["source_batches"]}
        self.assertEqual(by_dataset["disclosure_schedule"]["status"], "retryable_failed")
        self.assertEqual(by_dataset["disclosure_schedule"]["error"]["classification"], "blocked")
        self.assertEqual(by_dataset["performance_report"]["status"], "circuit_open")
        self.assertEqual(status["source_errors"][0]["classification"], "blocked")
        self.assertEqual(status["source_errors"][0]["error"], "429 cached challenge")
        self.assertEqual(ak.calls, {"disclosure_schedule": 0, "performance_report": 0})

    def test_lease_miss_reports_cached_running_retryable_and_terminal_states_truthfully(self):
        store = StateStore(self.db)
        store.initialize()
        now_utc = "2026-08-29T14:00:00+00:00"

        def seed(source, dataset, terminal_state):
            kind = (
                orchestrator._feature_calendar_job_key(
                    orchestrator._now_cn("2026-08-29T22:00:00+08:00")
                )
                if dataset == "trade_dates"
                else f"fetch_source:{source}:{dataset}:2026-08-29"
            )
            job_id = store.enqueue_job(kind, kind, {"source": source, "dataset": dataset})
            store.lease_next_job([kind], "seed", 3600, now_utc)
            if terminal_state == "succeeded":
                store.complete_job(job_id, {"batches": [{"dataset": dataset, "rows": 1, "hash": "cached-hash"}]})
            elif terminal_state == "retryable_failed":
                store.fail_job(job_id, {"error": "later"}, True, "2026-08-29T15:00:00+00:00")
            elif terminal_state == "terminal_failed":
                store.fail_job(job_id, {"error": "bad request"}, False)
            return job_id

        seed("baostock", "security_master", "succeeded")
        seed("baostock", "trade_dates", "running")
        seed("akshare", "disclosure_schedule", "retryable_failed")
        seed("akshare", "performance_report", "terminal_failed")
        bao, ak = FakeBaoSource(), FakeAKSource()

        status, code = orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(bao, ak),
        )

        self.assertEqual(code, 0)
        by_dataset = {item["dataset"]: item for item in status["source_batches"]}
        self.assertEqual(by_dataset["security_master"]["status"], "succeeded")
        self.assertTrue(by_dataset["security_master"]["cached"])
        self.assertEqual(by_dataset["security_master"]["hash"], "cached-hash")
        self.assertEqual(by_dataset["trade_dates"]["status"], "running")
        self.assertEqual(by_dataset["disclosure_schedule"]["status"], "retryable_failed")
        self.assertEqual(by_dataset["performance_report"]["status"], "terminal_failed")
        self.assertEqual(bao.calls, {"security_master": 0, "trade_dates": 0})
        self.assertEqual(ak.calls, {"disclosure_schedule": 0, "performance_report": 0})

    def test_prefilter_artifact_has_independent_ruleset_identity_and_invalidates_on_change(self):
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(FakeBaoSource(), FakeAKSource()),
        )
        prefilter_path = self.root / "curated" / "prefilter.json"
        performance_path = self.root / "curated" / "performance.json"
        before = json.loads(prefilter_path.read_text(encoding="utf-8"))
        performance_before = performance_path.read_bytes()
        self.assertEqual(
            before["input_hashes"]["prefilter_ruleset_hash"],
            orchestrator.PREFILTER_RULESET_HASH,
        )
        self.assertNotEqual(orchestrator.PREFILTER_RULESET_HASH, orchestrator.CURATION_RULESET_HASH)

        replacement_hash = "f" * 64
        with patch("ashare_pipeline.orchestrator.PREFILTER_RULESET_HASH", replacement_hash):
            orchestrator.run_command(
                self.root, self.db, "incremental", online=True,
                now_cn="2026-08-30T22:00:00+08:00",
                sources=(FakeBaoSource(), FakeAKSource()),
            )

        after = json.loads(prefilter_path.read_text(encoding="utf-8"))
        self.assertEqual(after["input_hashes"]["prefilter_ruleset_hash"], replacement_hash)
        self.assertNotEqual(before["input_hashes"], after["input_hashes"])
        self.assertEqual(performance_path.read_bytes(), performance_before)

    def test_online_start_recovers_expired_lease_and_retries_it(self):
        store = StateStore(self.db)
        store.initialize()
        kind = "fetch_source:baostock:security_master:2026-08-29"
        job_id = store.enqueue_job(kind, kind, {"source": "baostock", "dataset": "security_master"})
        store.lease_next_job([kind], "interrupted", 1, "2026-08-29T00:00:00+00:00")
        bao, ak = FakeBaoSource(), FakeAKSource()

        status, code = orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(bao, ak),
        )

        self.assertEqual(code, 0)
        self.assertGreaterEqual(status["recovered_expired_leases"], 1)
        self.assertEqual(bao.calls["security_master"], 1)
        self.assertEqual(store.get_job(job_id)["status"], "succeeded")

    def test_status_never_builds_sources_or_outputs_curated_records(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-29T22:00:00+08:00", sources=(bao, ak),
        )
        with patch("ashare_pipeline.orchestrator._default_sources", side_effect=AssertionError("network")):
            status, code = orchestrator.run_command(
                self.root, self.db, "status", now_cn="2026-08-29T22:01:00+08:00"
            )

        self.assertEqual(code, 0)
        self.assertNotIn("records", status)
        self.assertEqual(status["curated"]["universe"]["universe_count"], 2)
        self.assertEqual(status["curated"]["prefilter"]["candidate_count"], 2)

    def test_finalize_blocks_at_cutoff_then_on_market_and_formal_score_gaps_without_mutation(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-31T23:00:00+08:00", sources=(bao, ak),
        )

        at_cutoff, cutoff_code = orchestrator.run_command(
            self.root, self.db, "finalize", now_cn="2026-08-31T23:59:59+08:00"
        )
        after_cutoff, market_code = orchestrator.run_command(
            self.root, self.db, "finalize", now_cn="2026-09-01T00:00:00+08:00"
        )
        self.assertNotEqual(cutoff_code, 0)
        self.assertIn("cutoff_not_passed", at_cutoff["blocked_reasons"])
        self.assertNotEqual(market_code, 0)
        self.assertIn("market_2026_08_31_missing", after_cutoff["blocked_reasons"])

        self.install_market_evidence(
            [
                {"code": "sz.000001", "date": "2026-08-31", "close": "10.0", "tradestatus": "1"},
                {
                    "code": "sh.600000", "date": "2026-08-31", "close": "999",
                    "tradestatus": "0", "preclose": "9.5",
                },
            ]
        )
        formal_gap, formal_code = orchestrator.run_command(
            self.root, self.db, "finalize", now_cn="2026-09-01T00:00:00+08:00"
        )

        self.assertNotEqual(formal_code, 0)
        self.assertIn("formal_v2_scores_unavailable", formal_gap["blocked_reasons"])
        final_quality = json.loads((self.root / "status" / "quality.json").read_text(encoding="utf-8"))["metrics"]
        self.assertEqual(final_quality["status"], "passed")
        self.assertTrue(final_quality["market_ready"])
        suspended_price = next(
            row for row in final_quality["market_evidence"]["effective_prices"]
            if row["security_id"] == "SH600000"
        )
        self.assertEqual(suspended_price["effective_close"], 9.5)
        self.assertEqual(suspended_price["price_basis"], "suspended_preclose")
        self.assertEqual(suspended_price["raw_record_hash"], orchestrator._hash({
            "code": "sh.600000", "date": "2026-08-31", "close": "999",
            "tradestatus": "0", "preclose": "9.5",
        }))
        self.assertEqual(
            suspended_price["transformation_version"],
            orchestrator.MARKET_PRICE_TRANSFORMATION_VERSION,
        )
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(set(connection.execute("SELECT status FROM score_run")), {("provisional",)})
            self.assertEqual(set(connection.execute("SELECT state FROM score_item")), {("partial",)})

    def test_market_evidence_rejects_duplicates_missing_close_outside_rows_dates_and_hash_mismatch(self):
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-31T23:00:00+08:00", sources=(FakeBaoSource(), FakeAKSource()),
        )
        valid = [
            {"code": "sz.000001", "date": "2026-08-31", "close": "10", "tradestatus": "1"},
            {"code": "sh.600000", "date": "2026-08-31", "close": "11", "tradestatus": "1"},
        ]
        scenarios = [
            (valid + [dict(valid[0])], {}, "market_duplicate_security"),
            ([{**valid[0], "close": ""}, valid[1]], {}, "market_missing_close"),
            ([valid[0], {**valid[1], "close": "", "tradestatus": "0", "preclose": ""}], {}, "market_missing_close"),
            ([valid[0], {**valid[1], "tradestatus": "0", "preclose": ""}], {}, "market_missing_close"),
            ([valid[0], {key: value for key, value in valid[1].items() if key != "tradestatus"}], {}, "market_invalid_tradestatus"),
            (valid + [{"code": "sz.000999", "date": "2026-08-31", "close": "1", "tradestatus": "1"}], {}, "market_outside_universe"),
            ([{**valid[0], "date": "2026-08-30"}, valid[1]], {}, "market_wrong_date"),
            (valid, {"universe_hash": "wrong-universe"}, "market_universe_hash_mismatch"),
            (valid, {"declared_snapshot_hashes": ["0" * 64]}, "market_snapshot_hash_unverified"),
        ]

        for records, kwargs, expected_error in scenarios:
            with self.subTest(expected_error=expected_error):
                self.install_market_evidence(records, **kwargs)
                result, code = orchestrator.run_command(
                    self.root, self.db, "finalize", now_cn="2026-09-01T00:00:00+08:00"
                )
                self.assertNotEqual(code, 0)
                self.assertIn("market_2026_08_31_missing", result["blocked_reasons"])
                quality = json.loads(
                    (self.root / "status" / "quality.json").read_text(encoding="utf-8")
                )["metrics"]
                self.assertIn(expected_error, quality["market_validation_errors"])
                self.assertFalse(quality["market_ready"])

    def test_finalize_preserves_prior_quality_audit_fields(self):
        bao, ak = FakeBaoSource(), FakeAKSource()
        duplicate = {**ak.performance[0], "最新公告日期": "2026-08-19"}
        outside = {**ak.performance[0], "股票代码": "920001", "股票简称": "北交样本"}
        ak.performance.extend([duplicate, outside])
        orchestrator.run_command(
            self.root, self.db, "bootstrap", online=True,
            now_cn="2026-08-31T23:00:00+08:00", sources=(bao, ak),
        )
        quality_path = self.root / "status" / "quality.json"
        prior = json.loads(quality_path.read_text(encoding="utf-8"))
        prior["metrics"]["custom_audit_marker"] = "keep-me"
        quality_path.write_text(json.dumps(prior, ensure_ascii=False), encoding="utf-8")
        self.install_market_evidence(
            [
                {"code": "sz.000001", "date": "2026-08-31", "close": "10", "tradestatus": "1"},
                {"code": "sh.600000", "date": "2026-08-31", "close": "11", "tradestatus": "1"},
            ]
        )

        orchestrator.run_command(
            self.root, self.db, "finalize", now_cn="2026-09-01T00:00:00+08:00"
        )

        final_quality = json.loads(quality_path.read_text(encoding="utf-8"))["metrics"]
        self.assertEqual(final_quality["outside_universe_rows"], 1)
        self.assertEqual(final_quality["source_duplicate_security_count"], 1)
        self.assertEqual(final_quality["source_duplicate_row_count"], 1)
        self.assertEqual(final_quality["custom_audit_marker"], "keep-me")


if __name__ == "__main__":
    unittest.main()
