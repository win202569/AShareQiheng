from __future__ import annotations

from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import MappingProxyType
import unittest
from unittest.mock import patch

import ashare_pipeline.deep_worker as deep_worker_module
from ashare_pipeline.deep_worker import (
    STATEMENT_DATASETS,
    CandidateContext,
    build_candidate_context,
    deep_statement_key,
    expand_deep_parents,
    feature_build_key,
    load_candidate_context,
    statement_job_specs,
)
from ashare_pipeline.feature_contract import FeatureBundle, canonical_json_bytes, canonical_sha256
from ashare_pipeline.financial_features import SHANGHAI, build_feature_bundle, feature_input_hash
from ashare_pipeline.financial_schema import FINANCIAL_REQUEST_VERSION
from ashare_pipeline.snapshot_repository import SnapshotRepository
from ashare_pipeline.sources import (
    FetchBatch,
    RetryableSourceError,
    SourceBlocked,
)
from ashare_pipeline.state_store import StateStore


REPORT_PERIOD = "2026-06-30"
REFRESH_DATE = "2026-08-29"


def performance_row(
    security_id: str,
    *,
    industry: str = "包装印刷",
    announcement_date: str = "2026-08-20",
) -> dict[str, object]:
    return {
        "security_id": security_id,
        "industry": industry,
        "announcement_date": announcement_date,
        "revenue": 100.0,
    }


def candidate_documents(
    candidates: dict[str, str],
    *,
    prefilter_input_hashes: dict[str, object] | None = None,
    performance_rows: list[dict[str, object]] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    rows = performance_rows or [
        performance_row(security_id, industry=industry)
        for security_id, industry in sorted(candidates.items())
    ]
    prefilter_records = [
        {"security_id": security_id, "industry": industry}
        for security_id, industry in sorted(candidates.items())
    ]
    prefilter = {
        "schema_version": 2,
        "input_hashes": prefilter_input_hashes
        or {"performance": "a" * 64, "prefilter_rules": "b" * 64},
        "records": prefilter_records,
        "records_hash": canonical_sha256(prefilter_records),
    }
    performance = {
        "schema_version": 2,
        "input_hashes": {"fixture": "c" * 64},
        "records": rows,
        "records_hash": canonical_sha256(rows),
    }
    return prefilter, performance


def candidate_context(members: set[str]) -> CandidateContext:
    ordered = sorted(members)
    return CandidateContext(
        candidate_set_hash="c" * 64,
        members=frozenset(ordered),
        performance_input_hashes={item: "d" * 64 for item in ordered},
        industries={item: "包装印刷" for item in ordered},
        reported_target_period={item: True for item in ordered},
    )


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "financial"


def fixture_statement_batch(
    dataset: str,
    *,
    security_id: str = "SH600001",
    fetched_at_utc: str = "2026-08-29T00:00:00+00:00",
) -> FetchBatch:
    fixture = json.loads(
        (FIXTURE_ROOT / "general_nonfinancial_statements.json").read_text(
            encoding="utf-8"
        )
    )["batches"][dataset]
    records = json.loads(json.dumps(fixture["records"], ensure_ascii=False))
    for row in records:
        if "SECURITY_CODE" in row:
            row["SECURITY_CODE"] = security_id[2:]
        if "SECUCODE" in row:
            row["SECUCODE"] = f"{security_id[2:]}.{security_id[:2]}"
    return FetchBatch(
        "akshare",
        dataset,
        {"symbol": security_id, "report_period": REPORT_PERIOD},
        records,
        fetched_at_utc,
        str(fixture["source_version"]),
        dict(fixture["metadata"]),
    )


class FakeStatementSource:
    def __init__(
        self,
        *,
        failures: dict[str, BaseException] | None = None,
        batch_factory=None,
        entered: threading.Event | None = None,
        release: threading.Event | None = None,
    ) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.failures = dict(failures or {})
        self.batch_factory = batch_factory or fixture_statement_batch
        self.entered = entered
        self.release = release

    def fetch_financial_statement(
        self, security_id: str, dataset: str, report_period: str
    ) -> FetchBatch:
        self.calls.append((security_id, dataset, report_period))
        if self.entered is not None:
            self.entered.set()
        if self.release is not None and not self.release.wait(timeout=5):
            raise RuntimeError("test did not release blocked statement source")
        failure = self.failures.get(dataset)
        if failure is not None:
            raise failure
        return self.batch_factory(dataset, security_id=security_id)


def fixture_calendar_batch() -> FetchBatch:
    fixture = json.loads(
        (FIXTURE_ROOT / "trade_calendar_2021_2026.json").read_text(
            encoding="utf-8"
        )
    )
    return FetchBatch(
        fixture["source"],
        fixture["dataset"],
        fixture["request"],
        fixture["records"],
        fixture["fetched_at_utc"],
        fixture["source_version"],
        fixture["metadata"],
    )


class DeepWorkerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tempdir.name)
        self.data_root = self.project_root / "data"
        self.store = StateStore(self.data_root / "state.sqlite3")
        self.store.initialize()
        self.repository = SnapshotRepository(self.data_root, self.store)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_candidates(self, candidates: dict[str, str]) -> None:
        prefilter, performance = candidate_documents(candidates)
        curated = self.data_root / "curated"
        curated.mkdir(parents=True, exist_ok=True)
        (curated / "prefilter.json").write_bytes(canonical_json_bytes(prefilter))
        (curated / "performance.json").write_bytes(
            canonical_json_bytes(performance)
        )

    def _calendar_ref(self):
        return self.repository.persist(fixture_calendar_batch())[0]

    def _enqueue_statement(
        self,
        *,
        security_id: str = "SH600001",
        dataset: str = "balance_sheet",
        refresh_date: str = REFRESH_DATE,
    ) -> str:
        context = load_candidate_context(self.data_root)
        spec = next(
            item
            for item in statement_job_specs(
                context,
                security_id=security_id,
                report_period=REPORT_PERIOD,
                as_of_cn_date=refresh_date,
            )
            if item.payload["dataset"] == dataset
        )
        return self.store.enqueue_job(spec.kind, spec.idempotency_key, spec.payload)

    def _run(
        self,
        *,
        source=None,
        now_cn: datetime | None = None,
        online: bool = True,
        limit: int = 3,
        trade_calendar_snapshot=None,
        lease_seconds: int = 2,
        heartbeat_seconds: float = 0.05,
    ):
        return deep_worker_module.run_deep(
            self.data_root,
            self.store,
            source=source,
            snapshots=self.repository,
            trade_calendar_snapshot=trade_calendar_snapshot,
            now_cn=now_cn
            or datetime(2026, 8, 29, 20, 0, tzinfo=SHANGHAI),
            online=online,
            limit=limit,
            worker_id="worker-a",
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
        )

    def _enqueue_parent(self, security_id: str = "SH600001", *, suffix: str = "") -> str:
        return self.store.enqueue_job(
            "deep_financial",
            f"legacy:{security_id}:{suffix}",
            {"security_id": security_id, "report_period": REPORT_PERIOD},
        )

    def test_limit_counts_only_remote_statement_requests(self) -> None:
        candidates = {f"SH{index:06d}": "包装印刷" for index in range(1, 11)}
        self._write_candidates(candidates)
        for security_id in candidates:
            self.store.enqueue_job(
                "deep_financial",
                f"legacy:{security_id}",
                {"security_id": security_id, "report_period": REPORT_PERIOD},
            )
        source = FakeStatementSource()

        self.assertTrue(
            hasattr(deep_worker_module, "run_deep"),
            "run_deep execution API must exist",
        )
        summary = deep_worker_module.run_deep(
            self.data_root,
            self.store,
            source=source,
            snapshots=self.repository,
            trade_calendar_snapshot=None,
            now_cn=datetime(2026, 8, 29, 20, 0, tzinfo=SHANGHAI),
            online=True,
            limit=1,
            worker_id="worker-a",
            lease_seconds=2,
            heartbeat_seconds=0.05,
        )

        self.assertEqual(summary.remote_attempts, 1)
        self.assertEqual(len(source.calls), 1)
        self.assertEqual(len(self.store.list_jobs(["deep_statement"])), 30)

    def test_second_statement_failure_preserves_first_snapshot_and_partial_bundle(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        self._enqueue_parent()
        calendar = self._calendar_ref()
        source = FakeStatementSource(
            failures={"profit_sheet": RetryableSourceError("temporary")}
        )

        summary = self._run(
            source=source, trade_calendar_snapshot=calendar, limit=3
        )

        balance = self.repository.find_exact(
            "akshare",
            "balance_sheet",
            {"symbol": "SH600001", "report_period": REPORT_PERIOD},
        )
        cash = self.repository.find_exact(
            "akshare",
            "cash_flow_sheet",
            {"symbol": "SH600001", "report_period": REPORT_PERIOD},
        )
        self.assertIsNotNone(balance)
        self.assertIsNotNone(cash)
        self.assertEqual(summary.retryable_failed, 1)
        feature = self.store.latest_feature_set("SH600001", REPORT_PERIOD)
        self.assertIsNotNone(feature)
        self.assertEqual(feature["status"], "partial")

    def test_feature_build_reads_frozen_snapshot_ids_not_later_latest(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        context = load_candidate_context(self.data_root)
        calendar = self._calendar_ref()
        frozen = {
            dataset: self.repository.persist(fixture_statement_batch(dataset))[0]
            for dataset in STATEMENT_DATASETS
        }
        frozen_input_hash = feature_input_hash(
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_utc="2026-08-29T12:00:00+00:00",
            candidate_set_hash=context.candidate_set_hash,
            statement_snapshot_hashes={
                dataset: frozen[dataset].payload_hash for dataset in STATEMENT_DATASETS
            },
            trade_calendar_snapshot_hash=calendar.payload_hash,
        )
        job_id = deep_worker_module.enqueue_feature_build(
            self.store,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_utc="2026-08-29T12:00:00+00:00",
            candidate_context=context,
            statement_snapshots=frozen,
            trade_calendar_snapshot=calendar,
        )

        def revised_profit(dataset: str, *, security_id: str):
            batch = fixture_statement_batch(
                dataset,
                security_id=security_id,
                fetched_at_utc="2026-08-30T00:00:00+00:00",
            )
            if dataset == "profit_sheet":
                batch.records[0]["TOTAL_OPERATE_INCOME"] = 999.0
            return batch

        revised = self.repository.persist(
            revised_profit("profit_sheet", security_id="SH600001")
        )[0]
        self.assertNotEqual(revised.id, frozen["profit_sheet"].id)

        self._run(source=None, online=False, limit=1, trade_calendar_snapshot=calendar)

        self.assertEqual(self.store.get_job(job_id)["status"], "succeeded")
        feature = self.store.latest_feature_set("SH600001", REPORT_PERIOD)
        self.assertEqual(feature["input_hash"], frozen_input_hash)
        bundle_text = (self.project_root / feature["bundle_path"]).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("999.0", bundle_text)

    def test_feature_build_key_rejects_conflicting_frozen_payload(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        context = load_candidate_context(self.data_root)
        snapshots = {
            dataset: self.repository.persist(fixture_statement_batch(dataset))[0]
            for dataset in STATEMENT_DATASETS
        }
        calendar = self._calendar_ref()
        first_id = deep_worker_module.enqueue_feature_build(
            self.store,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_utc="2026-08-29T12:00:00+00:00",
            candidate_context=context,
            statement_snapshots=snapshots,
            trade_calendar_snapshot=calendar,
        )
        changed_context = replace(
            context,
            performance_input_hashes={"SH600001": "9" * 64},
        )

        with self.assertRaisesRegex(ValueError, "idempotency key conflicts"):
            deep_worker_module.enqueue_feature_build(
                self.store,
                security_id="SH600001",
                report_period=REPORT_PERIOD,
                as_of_utc="2026-08-29T12:00:00+00:00",
                candidate_context=changed_context,
                statement_snapshots=snapshots,
                trade_calendar_snapshot=calendar,
            )

        self.assertEqual(
            self.store.get_job(first_id)["payload"]["performance_input_hash"],
            context.performance_input_hashes["SH600001"],
        )

    def test_feature_executor_rejects_key_not_bound_to_frozen_payload(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        context = load_candidate_context(self.data_root)
        calendar = self._calendar_ref()
        payload = deep_worker_module.feature_build_payload(
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_utc="2026-08-29T12:00:00+00:00",
            context=context,
            statement_snapshots={dataset: None for dataset in STATEMENT_DATASETS},
            trade_calendar_snapshot=calendar,
        )
        job_id = self.store.enqueue_job(
            "feature_build",
            feature_build_key("SH600001", REPORT_PERIOD, "0" * 64),
            payload,
        )

        self._run(source=None, online=False, trade_calendar_snapshot=calendar)

        self.assertEqual(self.store.get_job(job_id)["status"], "terminal_failed")
        self.assertIsNone(self.store.latest_feature_set("SH600001", REPORT_PERIOD))

    def test_remote_job_renews_lease_while_source_call_is_blocked(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        self._enqueue_statement()
        calendar = self._calendar_ref()
        entered = threading.Event()
        release = threading.Event()
        source = FakeStatementSource(entered=entered, release=release)
        renewals: list[str] = []
        real_renew = self.store.renew_job_lease

        def renew(*args, **kwargs):
            expiry = real_renew(*args, **kwargs)
            renewals.append(expiry)
            if len(renewals) >= 2:
                release.set()
            return expiry

        with patch.object(self.store, "renew_job_lease", side_effect=renew):
            summary = self._run(
                source=source,
                trade_calendar_snapshot=calendar,
                limit=1,
                lease_seconds=2,
                heartbeat_seconds=0.02,
            )

        self.assertTrue(entered.is_set())
        self.assertGreaterEqual(len(renewals), 2)
        self.assertEqual(summary.statements_succeeded, 1)

    def test_heartbeat_failure_prevents_stale_worker_completion(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        job_id = self._enqueue_statement()
        calendar = self._calendar_ref()
        source = FakeStatementSource()

        with patch.object(
            self.store,
            "renew_job_lease",
            side_effect=ValueError("lease owner changed"),
        ):
            summary = self._run(
                source=source,
                trade_calendar_snapshot=calendar,
                limit=1,
                heartbeat_seconds=0.001,
            )

        self.assertEqual(summary.statements_succeeded, 0)
        self.assertEqual(source.calls, [])
        self.assertNotEqual(self.store.get_job(job_id)["status"], "succeeded")
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_run_recovers_expired_statement_lease_before_processing(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        job_id = self._enqueue_statement()
        self.store.lease_next_job(
            ["deep_statement"],
            "dead-worker",
            1,
            "2026-08-29T10:00:00+00:00",
        )
        calendar = self._calendar_ref()

        summary = self._run(
            source=FakeStatementSource(),
            trade_calendar_snapshot=calendar,
            limit=1,
        )

        self.assertEqual(summary.statements_succeeded, 1)
        self.assertEqual(self.store.get_job(job_id)["status"], "succeeded")

    def test_exact_same_refresh_date_snapshot_is_reused_without_remote_limit(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        existing = self.repository.persist(fixture_statement_batch("balance_sheet"))[0]
        self._enqueue_statement()
        source = FakeStatementSource()

        summary = self._run(
            source=source,
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
        )

        self.assertEqual(source.calls, [])
        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(summary.snapshots_reused, 1)
        self.assertIn(
            existing.payload_hash,
            {item.get("snapshot_hash") for item in summary.items},
        )

    def test_new_refresh_date_fetch_deduplicates_identical_snapshot_content(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        first = self.repository.persist(fixture_statement_batch("balance_sheet"))[0]
        self._enqueue_statement(refresh_date="2026-08-30")

        def next_day(dataset: str, *, security_id: str):
            return fixture_statement_batch(
                dataset,
                security_id=security_id,
                fetched_at_utc="2026-08-30T00:00:00+00:00",
            )

        source = FakeStatementSource(batch_factory=next_day)
        summary = self._run(
            source=source,
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
            now_cn=datetime(2026, 8, 30, 20, 0, tzinfo=SHANGHAI),
        )

        self.assertEqual(summary.remote_attempts, 1)
        self.assertEqual(len(source.calls), 1)
        self.assertEqual(
            self.repository.find_exact(
                "akshare",
                "balance_sheet",
                {"symbol": "SH600001", "report_period": REPORT_PERIOD},
            ).id,
            first.id,
        )
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM source_snapshot WHERE dataset='balance_sheet'"
                ).fetchone()[0],
                1,
            )

    def test_source_blocked_opens_akshare_circuit_and_leaves_later_jobs_pending(self) -> None:
        candidates = {"SH600001": "包装印刷", "SH600002": "包装印刷"}
        self._write_candidates(candidates)
        for security_id in candidates:
            self._enqueue_parent(security_id)
        source = FakeStatementSource(
            failures={
                dataset: SourceBlocked("HTTP 429")
                for dataset in STATEMENT_DATASETS
            }
        )

        summary = self._run(
            source=source,
            trade_calendar_snapshot=self._calendar_ref(),
            limit=6,
        )

        self.assertEqual(summary.remote_attempts, 1)
        self.assertEqual(summary.circuit_breakers, ("akshare",))
        statement_jobs = self.store.list_jobs(["deep_statement"])
        self.assertEqual(sum(job["status"] == "pending" for job in statement_jobs), 5)
        self.assertEqual(sum(job["status"] == "retryable_failed" for job in statement_jobs), 1)

    def test_malformed_statement_is_terminal_and_records_quality_issue(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        job_id = self._enqueue_statement()

        def malformed(dataset: str, *, security_id: str):
            batch = fixture_statement_batch(dataset, security_id=security_id)
            del batch.records[0]["REPORT_DATE"]
            return batch

        summary = self._run(
            source=FakeStatementSource(batch_factory=malformed),
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
        )

        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(self.store.get_job(job_id)["status"], "terminal_failed")
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            issues = connection.execute(
                "SELECT code, details_json FROM quality_issue ORDER BY created_at, id"
            ).fetchall()
        self.assertIn("statement_report_date_invalid", {row[0] for row in issues})

    def test_terminal_source_error_marks_job_terminal_without_crashing_run(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        job_id = self._enqueue_statement()
        source = FakeStatementSource(
            failures={"balance_sheet": deep_worker_module.TerminalSourceError("bad request")}
        )

        summary = self._run(
            source=source,
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
        )

        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(self.store.get_job(job_id)["status"], "terminal_failed")

    def test_mismatched_source_batch_fails_closed_without_persisting_wrong_dataset(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        job_id = self._enqueue_statement(dataset="balance_sheet")

        def mismatched(_dataset: str, *, security_id: str):
            return fixture_statement_batch("profit_sheet", security_id=security_id)

        summary = self._run(
            source=FakeStatementSource(batch_factory=mismatched),
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
        )

        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(self.store.get_job(job_id)["status"], "terminal_failed")
        self.assertIsNone(
            self.repository.find_exact(
                "akshare",
                "profit_sheet",
                {"symbol": "SH600001", "report_period": REPORT_PERIOD},
            )
        )

    def test_target_period_missing_retries_six_hours_before_cutoff(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        job_id = self._enqueue_statement()

        def missing_target(dataset: str, *, security_id: str):
            batch = fixture_statement_batch(dataset, security_id=security_id)
            batch.records[:] = [
                row
                for row in batch.records
                if str(row.get("REPORT_DATE", ""))[:10] != REPORT_PERIOD
            ]
            batch.metadata["report_period_match_count"] = 0
            return batch

        now_cn = datetime(2026, 8, 29, 20, 0, tzinfo=SHANGHAI)
        summary = self._run(
            source=FakeStatementSource(batch_factory=missing_target),
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
            now_cn=now_cn,
        )

        job = self.store.get_job(job_id)
        self.assertEqual(summary.retryable_failed, 1)
        self.assertEqual(job["status"], "retryable_failed")
        self.assertEqual(
            job["next_retry_at"],
            (now_cn.astimezone(timezone.utc) + timedelta(hours=6)).isoformat(),
        )
        self.assertEqual(
            self.store.latest_feature_set("SH600001", REPORT_PERIOD)["status"],
            "partial",
        )

    def test_target_period_missing_is_terminal_and_blocked_after_cutoff(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        job_id = self._enqueue_statement(refresh_date="2026-09-01")

        def missing_target(dataset: str, *, security_id: str):
            batch = fixture_statement_batch(
                dataset,
                security_id=security_id,
                fetched_at_utc="2026-09-01T00:00:00+00:00",
            )
            batch.records[:] = [
                row
                for row in batch.records
                if str(row.get("REPORT_DATE", ""))[:10] != REPORT_PERIOD
            ]
            batch.metadata["report_period_match_count"] = 0
            return batch

        summary = self._run(
            source=FakeStatementSource(batch_factory=missing_target),
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
            now_cn=datetime(2026, 9, 1, 0, 0, tzinfo=SHANGHAI),
        )

        feature = self.store.latest_feature_set("SH600001", REPORT_PERIOD)
        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(self.store.get_job(job_id)["status"], "terminal_failed")
        self.assertEqual(feature["status"], "blocked")
        self.assertIn("reported_but_statement_missing", feature["blockers"])

    def test_revised_snapshot_creates_new_feature_without_overwriting_old_file(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        self._enqueue_parent(suffix="first")
        calendar = self._calendar_ref()
        self._run(
            source=FakeStatementSource(),
            trade_calendar_snapshot=calendar,
            limit=3,
        )
        old = self.store.latest_feature_set("SH600001", REPORT_PERIOD)
        old_bytes = (self.project_root / old["bundle_path"]).read_bytes()
        self._enqueue_parent(suffix="second")

        def revised(dataset: str, *, security_id: str):
            batch = fixture_statement_batch(
                dataset,
                security_id=security_id,
                fetched_at_utc="2026-08-30T00:00:00+00:00",
            )
            if dataset == "profit_sheet":
                batch.records[0]["TOTAL_OPERATE_INCOME"] = 123456789.0
            return batch

        self._run(
            source=FakeStatementSource(batch_factory=revised),
            trade_calendar_snapshot=calendar,
            limit=3,
            now_cn=datetime(2026, 8, 30, 20, 0, tzinfo=SHANGHAI),
        )
        newest = self.store.latest_feature_set("SH600001", REPORT_PERIOD)

        self.assertNotEqual(newest["input_hash"], old["input_hash"])
        self.assertTrue((self.project_root / old["bundle_path"]).is_file())
        self.assertEqual((self.project_root / old["bundle_path"]).read_bytes(), old_bytes)
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            self.assertGreaterEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM feature_set WHERE security_id='SH600001'"
                ).fetchone()[0],
                2,
            )

    def test_summary_and_job_results_never_leak_raw_statement_markers(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        self._enqueue_statement()

        def marked(dataset: str, *, security_id: str):
            batch = fixture_statement_batch(dataset, security_id=security_id)
            batch.records[0]["RAW_SECRET_MARKER"] = "must-not-leak"
            return batch

        summary = self._run(
            source=FakeStatementSource(batch_factory=marked),
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
        )
        allowed = {
            "security_id",
            "dataset",
            "snapshot_hash",
            "bundle_hash",
            "outcome",
            "error_classification",
        }

        self.assertTrue(all(set(item) <= allowed for item in summary.items))
        serialized = json.dumps(summary.to_dict(), ensure_ascii=False)
        self.assertNotIn("RAW_SECRET_MARKER", serialized)
        self.assertNotIn("must-not-leak", serialized)
        for job in self.store.list_jobs():
            result_text = json.dumps(job["result"], ensure_ascii=False)
            self.assertNotIn("RAW_SECRET_MARKER", result_text)
            self.assertNotIn("must-not-leak", result_text)

    def test_offline_mode_expands_parents_without_touching_source(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        self._enqueue_parent()

        class ForbiddenSource:
            def fetch_financial_statement(self, *args, **kwargs):
                raise AssertionError("offline mode touched source")

        summary = self._run(
            source=ForbiddenSource(),
            trade_calendar_snapshot=None,
            online=False,
            limit=1,
        )

        self.assertEqual(summary.expanded, 1)
        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(
            {job["status"] for job in self.store.list_jobs(["deep_statement"])},
            {"pending"},
        )

    def test_run_rejects_mismatched_repository_root_and_invalid_execution_inputs(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        other_data = self.project_root / "other-data"
        other_store = StateStore(other_data / "state.sqlite3")
        other_store.initialize()
        other_repository = SnapshotRepository(other_data, other_store)
        common = dict(
            root=self.data_root,
            store=self.store,
            source=None,
            snapshots=self.repository,
            trade_calendar_snapshot=None,
            now_cn=datetime(2026, 8, 29, 20, 0, tzinfo=SHANGHAI),
            online=False,
            limit=1,
        )
        cases = (
            {**common, "snapshots": other_repository},
            {**common, "limit": 0},
            {**common, "limit": 361},
            {**common, "lease_seconds": 0},
            {**common, "lease_seconds": True},
            {**common, "heartbeat_seconds": 0},
            {**common, "heartbeat_seconds": float("nan")},
            {**common, "now_cn": datetime(2026, 8, 29, 20, 0)},
            {
                **common,
                "now_cn": datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
            },
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(
                (TypeError, ValueError)
            ):
                deep_worker_module.run_deep(**arguments)

    def test_summary_items_are_deeply_immutable_and_to_dict_is_detached(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        self._enqueue_statement()
        summary = self._run(
            source=FakeStatementSource(),
            trade_calendar_snapshot=self._calendar_ref(),
            limit=1,
        )

        with self.assertRaises(TypeError):
            summary.items[0]["outcome"] = "changed"
        exposed = summary.to_dict()
        exposed["items"][0]["outcome"] = "changed"
        exposed["circuit_breakers"].append("changed")
        self.assertNotEqual(summary.items[0]["outcome"], "changed")
        self.assertEqual(summary.circuit_breakers, ())

    def _empty_feature_bundle(self) -> FeatureBundle:
        return build_feature_bundle(
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_utc="2026-08-29T12:00:00+00:00",
            candidate_set_hash="c" * 64,
            source_industry_name="包装印刷",
            facts=(),
            fact_blockers=(),
            statement_snapshot_hashes={
                "balance_sheet": None,
                "profit_sheet": None,
                "cash_flow_sheet": None,
            },
            trade_calendar_snapshot_hash="4" * 64,
            reported_target_period=True,
        )

    def test_existing_feature_conflict_preserves_original_file(self) -> None:
        bundle = self._empty_feature_bundle()
        relative_path, digest, created = deep_worker_module.write_feature_bundle(
            self.project_root, bundle
        )
        target = self.project_root / relative_path
        original = target.read_bytes()
        conflicting = replace(bundle, blockers=("changed-without-input-hash",))

        with self.assertRaisesRegex(
            ValueError, "non-deterministic feature conflict"
        ):
            deep_worker_module.write_feature_bundle(self.project_root, conflicting)

        self.assertTrue(created)
        self.assertEqual(digest, bundle.bundle_hash())
        self.assertEqual(target.read_bytes(), original)

    def test_link_race_with_different_winner_is_deterministic_conflict(self) -> None:
        bundle = self._empty_feature_bundle()
        target = self.project_root / (
            f"data/curated/formal_features/{REPORT_PERIOD}/SH600001/"
            f"{bundle.input_hash}.json"
        )
        winner = b'{"different":"winner"}\n'

        def lose_link(_source, destination):
            Path(destination).write_bytes(winner)
            raise FileExistsError("simulated link race")

        with patch.object(deep_worker_module.os, "link", side_effect=lose_link):
            with self.assertRaisesRegex(
                ValueError, "non-deterministic feature conflict"
            ):
                deep_worker_module.write_feature_bundle(self.project_root, bundle)

        self.assertEqual(target.read_bytes(), winner)

    def test_database_failure_removes_new_orphan_feature_file(self) -> None:
        self._write_candidates({"SH600001": "包装印刷"})
        context = load_candidate_context(self.data_root)
        calendar = self._calendar_ref()
        deep_worker_module.enqueue_feature_build(
            self.store,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_utc="2026-08-29T12:00:00+00:00",
            candidate_context=context,
            statement_snapshots={dataset: None for dataset in STATEMENT_DATASETS},
            trade_calendar_snapshot=calendar,
        )

        with patch.object(
            self.store,
            "put_feature_bundle",
            side_effect=sqlite3.IntegrityError("forced database failure"),
        ):
            self._run(
                source=None,
                online=False,
                trade_calendar_snapshot=calendar,
                limit=1,
            )

        feature_root = (
            self.data_root
            / "curated"
            / "formal_features"
            / REPORT_PERIOD
            / "SH600001"
        )
        self.assertEqual(list(feature_root.glob("*.json")), [])
        self.assertFalse((self.data_root / "data").exists())
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                0,
            )

    def test_feature_path_is_project_relative_and_never_creates_data_data(self) -> None:
        bundle = self._empty_feature_bundle()
        relative_path, digest, _ = deep_worker_module.write_feature_bundle(
            self.project_root, bundle
        )
        observed = deep_worker_module.read_verified_feature_bundle(
            self.project_root, relative_path, digest
        )

        self.assertEqual(observed, bundle)
        self.assertEqual(
            relative_path,
            f"data/curated/formal_features/{REPORT_PERIOD}/SH600001/{bundle.input_hash}.json",
        )
        self.assertTrue((self.project_root / relative_path).is_file())
        self.assertFalse((self.data_root / "data").exists())

    def test_old_parent_expands_to_three_dated_unique_statement_jobs(self) -> None:
        context = candidate_context({"SH600001"})
        parent_id = self.store.enqueue_job(
            "deep_financial",
            "legacy:SH600001",
            {
                "security_id": "SH600001",
                "report_period": REPORT_PERIOD,
                "input_hash": "a" * 64,
            },
        )

        summary = expand_deep_parents(
            self.store,
            context,
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )

        self.assertEqual(summary, {"expanded": 1, "superseded": 0, "children": 3})
        self.assertEqual(
            self.store.get_job(parent_id)["result"],
            {"outcome": "expanded", "child_count": 3},
        )
        children = self.store.list_jobs(["deep_statement"])
        self.assertEqual(
            {job["idempotency_key"] for job in children},
            {
                "deep_statement:v1:SH600001:balance_sheet:2026-06-30:2026-08-29",
                "deep_statement:v1:SH600001:profit_sheet:2026-06-30:2026-08-29",
                "deep_statement:v1:SH600001:cash_flow_sheet:2026-06-30:2026-08-29",
            },
        )
        self.assertEqual(
            {job["payload"]["candidate_set_hash"] for job in children},
            {context.candidate_set_hash},
        )

    def test_reexpansion_is_idempotent_and_120_parents_make_360_children(self) -> None:
        context = candidate_context({f"SH{index:06d}" for index in range(1, 121)})
        for security_id in context.members:
            self.store.enqueue_job(
                "deep_financial",
                f"legacy:{security_id}",
                {"security_id": security_id, "report_period": REPORT_PERIOD},
            )

        first = expand_deep_parents(
            self.store,
            context,
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )
        second = expand_deep_parents(
            self.store,
            context,
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )

        self.assertEqual(first, {"expanded": 120, "superseded": 0, "children": 360})
        self.assertEqual(second, {"expanded": 0, "superseded": 0, "children": 0})
        self.assertEqual(len(self.store.list_jobs(["deep_statement"])), 360)

    def test_removed_parent_is_superseded_without_children(self) -> None:
        parent_id = self.store.enqueue_job(
            "deep_financial",
            "legacy:SH600999",
            {"security_id": "SH600999", "report_period": REPORT_PERIOD},
        )

        summary = expand_deep_parents(
            self.store,
            candidate_context({"SH600001"}),
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )

        self.assertEqual(summary, {"expanded": 0, "superseded": 1, "children": 0})
        self.assertEqual(
            self.store.get_job(parent_id)["result"],
            {"outcome": "superseded", "child_count": 0},
        )
        self.assertEqual(self.store.list_jobs(["deep_statement"]), [])

    def test_child_insert_failure_rolls_back_all_children_and_parent_completion(self) -> None:
        parent_id = self.store.enqueue_job(
            "deep_financial",
            "legacy:rollback",
            {"security_id": "SH600001", "report_period": REPORT_PERIOD},
        )
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            connection.execute(
                """CREATE TRIGGER reject_profit_child BEFORE INSERT ON job
                WHEN NEW.kind='deep_statement'
                 AND json_extract(NEW.payload_json, '$.dataset')='profit_sheet'
                BEGIN SELECT RAISE(ABORT, 'reject profit child'); END"""
            )
            connection.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            expand_deep_parents(
                self.store,
                candidate_context({"SH600001"}),
                as_of_cn_date=REFRESH_DATE,
                worker_id="planner",
            )

        self.assertEqual(self.store.get_job(parent_id)["status"], "running")
        self.assertEqual(self.store.list_jobs(["deep_statement"]), [])

    def test_candidate_hash_is_order_independent_and_has_exact_dependencies(self) -> None:
        inputs = {"rules": "1" * 64, "performance": "2" * 64}
        rows = [
            performance_row("SZ000002", industry="银行", announcement_date="2026-08-22"),
            performance_row("SH600001", announcement_date="2026-08-21"),
            performance_row("SH600999", announcement_date="2026-08-23"),
        ]
        prefilter, performance = candidate_documents(
            {"SZ000002": "银行", "SH600001": "包装印刷"},
            prefilter_input_hashes=inputs,
            performance_rows=rows,
        )

        first = build_candidate_context(prefilter, performance)
        shuffled_prefilter = dict(prefilter)
        shuffled_prefilter["input_hashes"] = dict(reversed(tuple(inputs.items())))
        shuffled_prefilter["records"] = list(reversed(prefilter["records"]))
        shuffled_prefilter["records_hash"] = canonical_sha256(
            shuffled_prefilter["records"]
        )
        shuffled_performance = dict(performance)
        shuffled_performance["records"] = list(reversed(rows))
        shuffled_performance["records_hash"] = canonical_sha256(
            shuffled_performance["records"]
        )
        second = build_candidate_context(shuffled_prefilter, shuffled_performance)

        expected_pairs = [
            ["SH600001", canonical_sha256(rows[1])],
            ["SZ000002", canonical_sha256(rows[0])],
        ]
        expected = canonical_sha256(
            {
                "prefilter_input_hashes": inputs,
                "performance_input_hashes": expected_pairs,
            }
        )
        self.assertEqual(first.candidate_set_hash, expected)
        self.assertEqual(second.candidate_set_hash, expected)
        self.assertEqual(
            dict(first.performance_input_hashes), dict(expected_pairs)
        )

    def test_candidate_hash_changes_with_prefilter_or_selected_performance_input(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        original = build_candidate_context(prefilter, performance).candidate_set_hash

        changed_prefilter = json.loads(json.dumps(prefilter))
        changed_prefilter["input_hashes"]["performance"] = "9" * 64
        changed_row = json.loads(json.dumps(performance))
        changed_row["records"][0]["announcement_date"] = "2026-08-21"
        changed_row["records_hash"] = canonical_sha256(changed_row["records"])

        self.assertNotEqual(
            build_candidate_context(changed_prefilter, performance).candidate_set_hash,
            original,
        )
        self.assertNotEqual(
            build_candidate_context(prefilter, changed_row).candidate_set_hash,
            original,
        )

    def test_selected_candidate_without_performance_record_fails_closed(self) -> None:
        prefilter, performance = candidate_documents(
            {"SH600001": "包装印刷"},
            performance_rows=[performance_row("SH600002")],
        )

        with self.assertRaisesRegex(ValueError, "performance record"):
            build_candidate_context(prefilter, performance)

    def test_context_defensively_copies_and_freezes_all_member_mappings(self) -> None:
        performance_hashes = {"SH600001": "a" * 64}
        industries = {"SH600001": "包装印刷"}
        reported = {"SH600001": True}
        context = CandidateContext(
            candidate_set_hash="b" * 64,
            members=frozenset({"SH600001"}),
            performance_input_hashes=performance_hashes,
            industries=industries,
            reported_target_period=reported,
        )

        performance_hashes["SH600001"] = "c" * 64
        industries["SH600001"] = "银行"
        reported["SH600001"] = False
        self.assertEqual(context.performance_input_hashes["SH600001"], "a" * 64)
        self.assertEqual(context.industries["SH600001"], "包装印刷")
        self.assertTrue(context.reported_target_period["SH600001"])
        for mapping in (
            context.performance_input_hashes,
            context.industries,
            context.reported_target_period,
        ):
            self.assertIsInstance(mapping, MappingProxyType)
            with self.assertRaises(TypeError):
                mapping["SH600001"] = "changed"
        with self.assertRaises(FrozenInstanceError):
            context.candidate_set_hash = "d" * 64

    def test_load_candidate_context_reads_curated_documents_without_mutating_them(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        curated = self.data_root / "curated"
        curated.mkdir(parents=True)
        prefilter_bytes = canonical_json_bytes(prefilter)
        performance_bytes = canonical_json_bytes(performance)
        (curated / "prefilter.json").write_bytes(prefilter_bytes)
        (curated / "performance.json").write_bytes(performance_bytes)

        loaded = load_candidate_context(self.data_root)

        self.assertEqual(loaded.members, frozenset({"SH600001"}))
        self.assertTrue(loaded.reported_target_period["SH600001"])
        self.assertEqual((curated / "prefilter.json").read_bytes(), prefilter_bytes)
        self.assertEqual((curated / "performance.json").read_bytes(), performance_bytes)

    def test_statement_specs_have_fixed_order_and_first_enqueue_audit_payload(self) -> None:
        context = candidate_context({"SH600001"})

        specs = statement_job_specs(
            context,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_cn_date=REFRESH_DATE,
        )

        self.assertEqual(STATEMENT_DATASETS, ("balance_sheet", "profit_sheet", "cash_flow_sheet"))
        self.assertEqual(tuple(spec.payload["dataset"] for spec in specs), STATEMENT_DATASETS)
        for spec in specs:
            self.assertEqual(spec.kind, "deep_statement")
            self.assertEqual(spec.payload, {
                "security_id": "SH600001",
                "dataset": spec.payload["dataset"],
                "report_period": REPORT_PERIOD,
                "candidate_set_hash": context.candidate_set_hash,
                "performance_input_hash": context.performance_input_hashes["SH600001"],
                "request_version": FINANCIAL_REQUEST_VERSION,
                "refresh_date": REFRESH_DATE,
            })

    def test_same_date_candidate_change_reuses_first_enqueued_child_payload(self) -> None:
        old_context = candidate_context({"SH600001"})
        for spec in statement_job_specs(
            old_context,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_cn_date=REFRESH_DATE,
        ):
            self.store.enqueue_job(spec.kind, spec.idempotency_key, spec.payload)
        changed_context = CandidateContext(
            candidate_set_hash="e" * 64,
            members=frozenset({"SH600001"}),
            performance_input_hashes={"SH600001": "f" * 64},
            industries={"SH600001": "银行"},
            reported_target_period={"SH600001": True},
        )
        parent_id = self.store.enqueue_job(
            "deep_financial",
            "legacy:changed-context",
            {"security_id": "SH600001", "report_period": REPORT_PERIOD},
        )

        summary = expand_deep_parents(
            self.store,
            changed_context,
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )

        self.assertEqual(summary["expanded"], 1)
        self.assertEqual(self.store.get_job(parent_id)["status"], "succeeded")
        self.assertEqual(
            {job["payload"]["candidate_set_hash"] for job in self.store.list_jobs(["deep_statement"])},
            {old_context.candidate_set_hash},
        )

    def test_keys_and_documents_reject_malformed_security_dates_and_digests(self) -> None:
        for call in (
            lambda: deep_statement_key("600001", "balance_sheet", REPORT_PERIOD, REFRESH_DATE),
            lambda: deep_statement_key("SH600001", "unknown", REPORT_PERIOD, REFRESH_DATE),
            lambda: deep_statement_key("SH600001", "balance_sheet", "2026-02-30", REFRESH_DATE),
            lambda: deep_statement_key("SH600001", "balance_sheet", REPORT_PERIOD, "20260829"),
            lambda: feature_build_key("SH600001", REPORT_PERIOD, "not-a-digest"),
        ):
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

        with self.assertRaises(ValueError):
            CandidateContext(
                candidate_set_hash="bad",
                members=frozenset({"SH600001"}),
                performance_input_hashes={"SH600001": "a" * 64},
                industries={"SH600001": "包装印刷"},
                reported_target_period={"SH600001": True},
            )

    def test_prefilter_document_requires_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        del prefilter["records_hash"]

        with self.assertRaisesRegex(ValueError, "prefilter records_hash"):
            build_candidate_context(prefilter, performance)

    def test_prefilter_document_rejects_malformed_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        prefilter["records_hash"] = "not-a-digest"

        with self.assertRaisesRegex(ValueError, "prefilter records_hash"):
            build_candidate_context(prefilter, performance)

    def test_prefilter_document_rejects_mismatched_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        prefilter["records_hash"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "records_hash"):
            build_candidate_context(prefilter, performance)

    def test_performance_document_requires_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        del performance["records_hash"]

        with self.assertRaisesRegex(ValueError, "performance records_hash"):
            build_candidate_context(prefilter, performance)

    def test_performance_document_rejects_malformed_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        performance["records_hash"] = "not-a-digest"

        with self.assertRaisesRegex(ValueError, "performance records_hash"):
            build_candidate_context(prefilter, performance)

    def test_performance_document_rejects_mismatched_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        performance["records_hash"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "performance records_hash"):
            build_candidate_context(prefilter, performance)

    def _assert_existing_statement_mismatch_fails_closed(
        self,
        *,
        payload_field: str | None = None,
        replacement: object | None = None,
        existing_kind: str = "deep_statement",
    ) -> None:
        context = candidate_context({"SH600001"})
        requested = statement_job_specs(
            context,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_cn_date=REFRESH_DATE,
        )[0]
        existing_payload = requested.payload
        if payload_field is not None:
            existing_payload[payload_field] = replacement
        self.store.enqueue_job(
            existing_kind,
            requested.idempotency_key,
            existing_payload,
        )
        parent_id = self.store.enqueue_job(
            "deep_financial",
            f"legacy:mismatch:{payload_field or 'kind'}",
            {"security_id": "SH600001", "report_period": REPORT_PERIOD},
        )

        with self.assertRaisesRegex(ValueError, "existing deep statement"):
            expand_deep_parents(
                self.store,
                context,
                as_of_cn_date=REFRESH_DATE,
                worker_id="planner",
            )

        self.assertEqual(self.store.get_job(parent_id)["status"], "running")
        self.assertEqual(
            len(self.store.list_jobs(["deep_statement"])),
            0 if existing_kind != "deep_statement" else 1,
        )

    def test_existing_statement_security_must_match_requested_key(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            payload_field="security_id", replacement="SH600002"
        )

    def test_existing_statement_dataset_must_match_requested_key(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            payload_field="dataset", replacement="profit_sheet"
        )

    def test_existing_statement_period_must_match_requested_key(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            payload_field="report_period", replacement="2025-12-31"
        )

    def test_existing_statement_refresh_date_must_match_requested_key(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            payload_field="refresh_date", replacement="2026-08-28"
        )

    def test_existing_statement_kind_must_match_requested_spec(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            existing_kind="feature_build"
        )


if __name__ == "__main__":
    unittest.main()
