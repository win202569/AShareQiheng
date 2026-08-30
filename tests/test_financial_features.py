from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import random
import tempfile
import unittest

from ashare_pipeline.feature_contract import canonical_sha256
from ashare_pipeline.financial_features import (
    QualityIssue,
    build_financial_facts,
    select_visible_facts,
    trading_days_from_batch,
)
from ashare_pipeline.financial_schema import FinancialFact, MAPPING_VERSION
from ashare_pipeline.sources import FetchBatch


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "financial"
REQUIRED_PERIODS = {
    "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31",
    "2025-12-31", "2025-06-30", "2026-06-30",
}
STATEMENT_FIXTURES = (
    "general_nonfinancial_statements.json",
    "bank_statements.json",
    "real_estate_statements.json",
)


def _validate_fixture_structure(root: Path) -> None:
    """Task-7-local guard; the later worker/fixture helpers are not dependencies."""
    for name in STATEMENT_FIXTURES:
        path = root / name
        if not path.is_file():
            raise ValueError(f"missing statement fixture: {name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload.get("security_id"), str) or not payload["security_id"]:
            raise ValueError(f"{name}: missing security_id")
        batches = payload.get("batches")
        if not isinstance(batches, dict):
            raise ValueError(f"{name}: missing batches")
        for dataset in ("balance_sheet", "profit_sheet", "cash_flow_sheet"):
            batch = batches.get(dataset)
            if not isinstance(batch, dict):
                raise ValueError(f"{name}: missing statement batch {dataset}")
            records = batch.get("records")
            if not isinstance(records, list):
                raise ValueError(f"{name}: invalid records for {dataset}")
            observed = set()
            for row in records:
                if not isinstance(row, dict):
                    raise ValueError(f"{name}: statement row must be an object")
                for field in ("SECURITY_CODE", "REPORT_DATE", "NOTICE_DATE"):
                    if row.get(field) in (None, ""):
                        raise ValueError(f"{name}: missing identity/date field {field}")
                observed.add(row["REPORT_DATE"][:10])
            missing = REQUIRED_PERIODS - observed
            if missing:
                raise ValueError(f"{name}: missing required periods {sorted(missing)}")

    calendar_path = root / "trade_calendar_2021_2026.json"
    if not calendar_path.is_file():
        raise ValueError("missing trade calendar fixture")
    calendar = json.loads(calendar_path.read_text(encoding="utf-8"))
    request = calendar.get("request")
    records = calendar.get("records")
    if not isinstance(request, dict) or not isinstance(records, list):
        raise ValueError("invalid trade calendar fixture")
    if request.get("start_date", "") > "2021-01-01" or request.get("end_date", "") < "2026-09-07":
        raise ValueError("trade calendar fixture does not span required range")
    start = date.fromisoformat(request["start_date"])
    end = date.fromisoformat(request["end_date"])
    calendar_dates = [date.fromisoformat(row["calendar_date"]) for row in records]
    expected_count = (end - start).days + 1
    if len(calendar_dates) != expected_count or set(calendar_dates) != {
        start + timedelta(days=offset) for offset in range(expected_count)
    }:
        raise ValueError("trade calendar fixture must cover every date exactly once")
    trading_days_from_batch(FetchBatch(
        calendar["source"], calendar["dataset"], request, records,
        calendar["fetched_at_utc"], calendar["source_version"], calendar["metadata"],
    ))


def one_row_batch(
    *,
    dataset: str = "balance_sheet",
    notice: object = "2026-03-31",
    update: object = None,
    report_date: object = "2025-12-31",
    security_code: object = "600001",
    **fields: object,
) -> FetchBatch:
    row = {
        "SECURITY_CODE": security_code,
        "REPORT_DATE": report_date,
        "REPORT_DATE_NAME": "2025年报",
        "REPORT_TYPE": "年报",
        "NOTICE_DATE": notice,
        "UPDATE_DATE": update,
        **fields,
    }
    return FetchBatch(
        "akshare", dataset, {"symbol": "SH600001"}, [row],
        "2026-08-29T00:00:00+00:00", "test", {},
    )


def fact_version(
    *,
    value: float = 100.0,
    metric_key: str = "total_assets",
    period_end: str = "2025-12-31",
    announced_at: str = "2026-03-31T15:59:59+00:00",
    updated_at: str | None = None,
    effective_at: str = "2026-04-01T07:00:00+00:00",
    snapshot: str = "snapshot-a",
    raw_hash: str | None = None,
    unit: str = "CNY",
    nature: str = "instant",
) -> FinancialFact:
    return FinancialFact.create(
        security_id="SH600001",
        statement="balance",
        metric_key=metric_key,
        period_start=None if nature == "instant" else f"{period_end[:4]}-01-01",
        period_end=period_end,
        period_kind="FY",
        value=value,
        unit=unit,
        nature=nature,
        announced_at_utc=announced_at,
        effective_at_utc=effective_at,
        source_updated_at_utc=updated_at,
        source_snapshot_id=snapshot,
        source_field="TOTAL_ASSETS",
        raw_row_hash=raw_hash or canonical_sha256({"snapshot": snapshot, "value": value}),
        mapping_version=MAPPING_VERSION,
        created_at="2026-08-29T00:00:00+00:00",
    )


class FinancialFactSelectionTests(unittest.TestCase):
    def test_effective_at_uses_later_notice_or_update_then_next_trading_close(self):
        result = build_financial_facts(
            one_row_batch(
                notice="2026-03-31", update="2026-08-28",
                report_date="2025-12-31", TOTAL_ASSETS=1_000_000.0,
            ),
            source_snapshot_id="snapshot-a",
            expected_security_id="SH600001",
            trading_days=(date(2026, 8, 28), date(2026, 8, 31)),
            created_at_utc="2026-08-29T00:00:00+00:00",
        )
        fact = next(item for item in result.facts if item.metric_key == "total_assets")
        self.assertEqual(fact.announced_at_utc, "2026-03-31T15:59:59+00:00")
        self.assertEqual(fact.source_updated_at_utc, "2026-08-28T15:59:59+00:00")
        self.assertEqual(fact.effective_at_utc, "2026-08-31T07:00:00+00:00")

    def test_calendar_missing_next_session_blocks_instead_of_guessing_weekday(self):
        result = build_financial_facts(
            one_row_batch(notice="2026-08-31", report_date="2026-06-30", TOTAL_ASSETS=1.0),
            source_snapshot_id="snapshot-a", expected_security_id="SH600001",
            trading_days=(date(2026, 8, 31),),
            created_at_utc="2026-08-31T16:00:00+00:00",
        )
        self.assertEqual(result.facts, ())
        self.assertEqual(tuple(issue.code for issue in result.issues), ("trade_calendar_missing_next_session",))

    def test_future_revision_is_not_selected_before_its_effective_time(self):
        old = fact_version(value=100.0, snapshot="old")
        revised = fact_version(
            value=999.0, announced_at="2026-08-28T15:59:59+00:00",
            effective_at="2026-09-01T07:00:00+00:00", snapshot="new",
        )
        selection = select_visible_facts(
            (revised, old), as_of_utc="2026-08-31T15:00:00+00:00",
            snapshot_fetched_at={
                "old": "2026-04-01T08:00:00+00:00",
                "new": "2026-09-01T08:00:00+00:00",
            },
        )
        self.assertEqual(tuple(item.value for item in selection.facts), (100.0,))
        self.assertEqual(selection.blockers, ())

    def test_top_business_rank_conflict_is_not_hidden_by_effective_hash_or_id(self):
        first = fact_version(value=100.0, effective_at="2026-04-01T07:00:00+00:00", raw_hash="1" * 64)
        second = fact_version(value=101.0, effective_at="2026-04-02T07:00:00+00:00", raw_hash="f" * 64)
        selection = select_visible_facts(
            (first, second), as_of_utc="2026-04-03T00:00:00+00:00",
            snapshot_fetched_at={"snapshot-a": "2026-04-01T09:00:00+00:00"},
        )
        self.assertEqual(selection.facts, ())
        self.assertEqual(selection.blockers, ("conflicting_fact_versions",))

    def test_business_rank_is_announcement_then_update_then_snapshot_fetch(self):
        earlier_announcement = fact_version(
            value=900.0, announced_at="2026-03-30T15:59:59+00:00",
            updated_at="2026-04-10T15:59:59+00:00",
            effective_at="2026-04-11T07:00:00+00:00", snapshot="late-fetch",
        )
        later_announcement = fact_version(
            value=100.0, announced_at="2026-03-31T15:59:59+00:00",
            updated_at=None, snapshot="early-fetch",
        )
        selection = select_visible_facts(
            (earlier_announcement, later_announcement), as_of_utc="2026-05-01T00:00:00+00:00",
            snapshot_fetched_at={
                "late-fetch": "2026-04-20T00:00:00+00:00",
                "early-fetch": "2026-04-01T00:00:00+00:00",
            },
        )
        self.assertEqual(selection.facts[0].value, 100.0)

    def test_semantically_identical_top_rank_duplicates_are_deterministic(self):
        low = fact_version(value=100.0, raw_hash="1" * 64)
        high = fact_version(value=100.0, raw_hash="f" * 64)
        expected_id = max(low.id, high.id) if low.raw_row_hash == high.raw_row_hash else high.id
        for seed in range(8):
            shuffled = [low, high]
            random.Random(seed).shuffle(shuffled)
            selected = select_visible_facts(
                shuffled, as_of_utc="2026-04-02T00:00:00+00:00",
                snapshot_fetched_at={"snapshot-a": "2026-04-01T09:00:00+00:00"},
            )
            self.assertEqual(tuple(item.id for item in selected.facts), (expected_id,))

    def test_top_rank_unit_and_nature_conflicts_block_without_selection(self):
        base = fact_version(value=100.0)
        unit_conflict = fact_version(value=100.0, unit="shares", raw_hash="2" * 64)
        nature_conflict = fact_version(value=100.0, nature="duration", raw_hash="3" * 64)
        unit_result = select_visible_facts(
            (base, unit_conflict), as_of_utc="2026-04-02T00:00:00+00:00",
            snapshot_fetched_at={"snapshot-a": "2026-04-01T09:00:00+00:00"},
        )
        nature_result = select_visible_facts(
            (base, nature_conflict), as_of_utc="2026-04-02T00:00:00+00:00",
            snapshot_fetched_at={"snapshot-a": "2026-04-01T09:00:00+00:00"},
        )
        self.assertEqual(unit_result.blockers, ("conflicting_fact_units",))
        self.assertEqual(nature_result.blockers, ("conflicting_fact_versions",))
        self.assertEqual(unit_result.facts, ())
        self.assertEqual(nature_result.facts, ())

    def test_zero_builds_fact_null_does_not_and_invalid_numeric_values_issue(self):
        zero = build_financial_facts(
            one_row_batch(TOTAL_ASSETS=0), source_snapshot_id="zero",
            expected_security_id="SH600001", trading_days=(date(2026, 4, 1),),
            created_at_utc="2026-04-01T08:00:00+00:00",
        )
        self.assertEqual(tuple(item.value for item in zero.facts), (0.0,))
        null = build_financial_facts(
            one_row_batch(TOTAL_ASSETS=None), source_snapshot_id="null",
            expected_security_id="SH600001", trading_days=(date(2026, 4, 1),),
            created_at_utc="2026-04-01T08:00:00+00:00",
        )
        self.assertEqual(null.facts, ())
        self.assertEqual(null.issues, ())
        for invalid in (True, float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=invalid):
                batch = one_row_batch(TOTAL_ASSETS=1.0)
                batch.records[0]["TOTAL_ASSETS"] = invalid
                result = build_financial_facts(
                    batch, source_snapshot_id="invalid", expected_security_id="SH600001",
                    trading_days=(date(2026, 4, 1),), created_at_utc="2026-04-01T08:00:00+00:00",
                )
                self.assertEqual(result.facts, ())
                self.assertEqual(tuple(issue.code for issue in result.issues), ("invalid_financial_value",))

    def test_security_and_report_identity_errors_clear_entire_batch(self):
        valid_row = one_row_batch(TOTAL_ASSETS=1.0).records[0]
        cases = (
            ({**valid_row, "SECURITY_CODE": None}, "statement_security_missing"),
            ({**valid_row, "SECURITY_CODE": "600002"}, "statement_security_mismatch"),
            ({**valid_row, "REPORT_DATE": None}, "statement_report_date_invalid"),
        )
        for bad_row, code in cases:
            with self.subTest(code=code):
                batch = one_row_batch(TOTAL_ASSETS=2.0)
                batch.records[:] = [valid_row, bad_row]
                result = build_financial_facts(
                    batch, source_snapshot_id="bad-row", expected_security_id="SH600001",
                    trading_days=(date(2026, 4, 1),), created_at_utc="2026-04-01T08:00:00+00:00",
                )
                self.assertEqual(result.facts, ())
                self.assertEqual(result.issues[-1].code, code)

    def test_report_date_rejects_noncanonical_iso_lexical_forms(self):
        invalid_dates = (
            "2025-12-31junk", "20251231", "2025-W52-3", " 2025-12-31",
            "2025-12-31 ", "2025/12/31", "garbage",
        )
        for report_date in invalid_dates:
            with self.subTest(report_date=report_date):
                result = build_financial_facts(
                    one_row_batch(report_date=report_date, TOTAL_ASSETS=1.0),
                    source_snapshot_id="strict-report-date", expected_security_id="SH600001",
                    trading_days=(date(2026, 4, 1),), created_at_utc="2026-04-01T08:00:00+00:00",
                )
                self.assertEqual(result.facts, ())
                self.assertEqual(result.issues[-1].code, "statement_report_date_invalid")

    def test_source_dates_reject_compact_week_suffix_and_malformed_separators(self):
        invalid_dates = (
            "20260331", "2026-W14-2", "2026-03-31junk", "2026/03/31",
            "2026-03-31X12:00:00", "2026-03-31T12-00-00", " 2026-03-31",
        )
        for field in ("notice", "update"):
            for invalid in invalid_dates:
                with self.subTest(field=field, invalid=invalid):
                    values = {"notice": "2026-03-31", "update": None}
                    values[field] = invalid
                    result = build_financial_facts(
                        one_row_batch(**values, TOTAL_ASSETS=1.0),
                        source_snapshot_id="strict-source-date", expected_security_id="SH600001",
                        trading_days=(date(2026, 4, 1),), created_at_utc="2026-04-01T08:00:00+00:00",
                    )
                    self.assertEqual(result.facts, ())
                    self.assertEqual(result.issues[-1].code, "statement_source_date_invalid")

    def test_source_timestamp_accepts_explicit_iso_form_without_date_only_rewrite(self):
        result = build_financial_facts(
            one_row_batch(notice="2026-03-31T12:34:56+08:00", TOTAL_ASSETS=1.0),
            source_snapshot_id="timestamp", expected_security_id="SH600001",
            trading_days=(date(2026, 4, 1),), created_at_utc="2026-04-01T08:00:00+00:00",
        )
        self.assertEqual(result.facts[0].announced_at_utc, "2026-03-31T04:34:56+00:00")

    def test_secucode_exchange_suffix_and_dual_identity_must_match_expected(self):
        cases = (
            ({"SECURITY_CODE": None, "SECUCODE": "600001.SZ"}, "statement_security_mismatch"),
            ({"SECURITY_CODE": "600001", "SECUCODE": "600001.SZ"}, "statement_security_mismatch"),
            ({"SECURITY_CODE": "600001", "SECUCODE": "600002.SH"}, "statement_security_mismatch"),
            ({"SECURITY_CODE": None, "SECUCODE": "600001.BAD"}, "statement_security_invalid"),
        )
        for identity, expected_code in cases:
            with self.subTest(identity=identity):
                batch = one_row_batch(TOTAL_ASSETS=1.0)
                batch.records[0].update(identity)
                result = build_financial_facts(
                    batch, source_snapshot_id="identity", expected_security_id="SH600001",
                    trading_days=(date(2026, 4, 1),), created_at_utc="2026-04-01T08:00:00+00:00",
                )
                self.assertEqual(result.facts, ())
                self.assertEqual(result.issues[-1].code, expected_code)

    def test_fy_h1_quarters_and_other_periods_are_all_retained(self):
        report_dates = (
            ("2025-12-31", "FY"), ("2026-06-30", "H1"),
            ("2026-03-31", "Q1"), ("2026-09-30", "Q3"),
            ("2026-02-28", "OTHER"),
        )
        for report_date, expected_kind in report_dates:
            with self.subTest(report_date=report_date):
                result = build_financial_facts(
                    one_row_batch(report_date=report_date, TOTAL_ASSETS=1.0),
                    source_snapshot_id=report_date, expected_security_id="SH600001",
                    trading_days=(date(2026, 4, 1),), created_at_utc="2026-04-01T08:00:00+00:00",
                )
                self.assertEqual(result.facts[0].period_kind, expected_kind)

    def test_balance_equation_uses_approved_absolute_and_relative_tolerance(self):
        fetched = {
            "assets": "2026-04-01T09:00:00+00:00",
            "liabilities": "2026-04-01T09:00:00+00:00",
            "equity": "2026-04-01T09:00:00+00:00",
        }
        def selection_for(equity: float):
            facts = (
                fact_version(metric_key="total_assets", value=1_000_000.0, snapshot="assets"),
                fact_version(metric_key="total_liabilities", value=600_000.0, snapshot="liabilities"),
                fact_version(metric_key="total_equity", value=equity, snapshot="equity"),
            )
            return select_visible_facts(facts, as_of_utc="2026-04-02T00:00:00+00:00", snapshot_fetched_at=fetched)
        self.assertEqual(selection_for(399_500.0).blockers, ())
        self.assertEqual(selection_for(390_000.0).blockers, ("balance_equation_mismatch",))

    def test_quality_issue_details_are_deeply_immutable_and_defensively_copied(self):
        supplied = {"z": {"values": [1, 2]}, "a": "first"}
        issue = QualityIssue("error", "example", supplied)
        supplied["z"]["values"].append(3)
        self.assertEqual(tuple(issue.details), ("a", "z"))
        self.assertEqual(issue.details["z"]["values"], (1, 2))
        with self.assertRaises(TypeError):
            issue.details["new"] = "blocked"
        with self.assertRaises(TypeError):
            issue.details["z"]["values"] += (3,)

    def test_missing_snapshot_fetch_time_fails_closed(self):
        selected = select_visible_facts(
            (fact_version(snapshot="unknown"),), as_of_utc="2026-04-02T00:00:00+00:00",
            snapshot_fetched_at={},
        )
        self.assertEqual(selected.facts, ())
        self.assertEqual(selected.blockers, ("snapshot_fetch_time_missing",))

    def test_one_unrankable_version_blocks_the_whole_logical_fact(self):
        known = fact_version(value=100.0, snapshot="known", raw_hash="1" * 64)
        unknown = fact_version(value=999.0, snapshot="unknown", raw_hash="f" * 64)
        selected = select_visible_facts(
            (known, unknown), as_of_utc="2026-04-02T00:00:00+00:00",
            snapshot_fetched_at={"known": "2026-04-01T09:00:00+00:00"},
        )
        self.assertEqual(selected.facts, ())
        self.assertEqual(selected.blockers, ("snapshot_fetch_time_missing",))

    def test_non_string_and_malformed_snapshot_fetch_times_fail_closed(self):
        for invalid in (123, True, ["2026-04-01T09:00:00+00:00"], "not-a-time"):
            with self.subTest(invalid=invalid):
                selected = select_visible_facts(
                    (fact_version(snapshot="bad-time"),),
                    as_of_utc="2026-04-02T00:00:00+00:00",
                    snapshot_fetched_at={"bad-time": invalid},
                )
                self.assertEqual(selected.facts, ())
                self.assertEqual(selected.blockers, ("snapshot_fetch_time_invalid",))


class TradeCalendarTests(unittest.TestCase):
    @staticmethod
    def complete_records():
        start = date(2021, 1, 1)
        end = date(2026, 9, 7)
        records = []
        current = start
        while current <= end:
            records.append({"calendar_date": current.isoformat(), "is_trading_day": "0"})
            current += timedelta(days=1)
        for session in (date(2026, 8, 28), date(2026, 8, 31)):
            records[(session - start).days]["is_trading_day"] = "1"
        return records

    def calendar_batch(self, *, records=None, request=None, dataset="trade_dates"):
        return FetchBatch(
            "baostock", dataset,
            request or {"start_date": "2021-01-01", "end_date": "2026-09-07"},
            self.complete_records() if records is None else records,
            "2026-08-30T00:00:00+00:00", "test", {"verified_snapshot_id": "calendar-a"},
        )

    def test_calendar_extracts_only_explicit_trading_days_sorted_and_deduplicated(self):
        self.assertEqual(
            trading_days_from_batch(self.calendar_batch()),
            (date(2026, 8, 28), date(2026, 8, 31)),
        )

    def test_calendar_accepts_complete_shuffled_batch_and_sorts_sessions(self):
        records = self.complete_records()
        random.Random(17).shuffle(records)
        self.assertEqual(
            trading_days_from_batch(self.calendar_batch(records=records)),
            (date(2026, 8, 28), date(2026, 8, 31)),
        )

    def test_calendar_rejects_interior_hole_duplicate_and_missing_endpoint(self):
        complete = self.complete_records()
        cases = (
            complete[:100] + complete[101:],
            complete[:100] + [dict(complete[100])] + complete[100:],
            complete[1:],
            complete[:-1],
        )
        for records in cases:
            with self.subTest(row_count=len(records)):
                with self.assertRaises(ValueError):
                    trading_days_from_batch(self.calendar_batch(records=records))

    def test_calendar_rejects_wrong_dataset_malformed_rows_flags_and_range(self):
        invalid_batches = (
            self.calendar_batch(dataset="daily"),
            self.calendar_batch(records=[{"calendar_date": "bad", "is_trading_day": "1"}]),
            self.calendar_batch(records=[{"calendar_date": "2026-08-28", "is_trading_day": "yes"}]),
            self.calendar_batch(records=[{"calendar_date": "2026-08-28", "extra": "1"}]),
            self.calendar_batch(records=[{"calendar_date": "2026-08-28junk", "is_trading_day": "1"}]),
            self.calendar_batch(request={"start_date": "2022-01-01", "end_date": "2026-09-07"}),
            self.calendar_batch(request={"start_date": "2021-01-01", "end_date": "2026-09-06"}),
        )
        for batch in invalid_batches:
            with self.subTest(batch=batch):
                with self.assertRaises(ValueError):
                    trading_days_from_batch(batch)


class FinancialFixtureStructureTests(unittest.TestCase):
    def copied_fixture_root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        for name in (*STATEMENT_FIXTURES, "trade_calendar_2021_2026.json"):
            (root / name).write_text((FIXTURE_ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
        return temporary, root

    def test_committed_financial_fixtures_have_required_structure(self):
        _validate_fixture_structure(FIXTURE_ROOT)

    def test_validator_rejects_missing_statement_batch(self):
        temporary, root = self.copied_fixture_root()
        with temporary:
            path = root / STATEMENT_FIXTURES[0]
            payload = json.loads(path.read_text(encoding="utf-8"))
            del payload["batches"]["cash_flow_sheet"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing statement batch"):
                _validate_fixture_structure(root)

    def test_validator_rejects_missing_required_fy_or_h1_period(self):
        temporary, root = self.copied_fixture_root()
        with temporary:
            path = root / STATEMENT_FIXTURES[0]
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["batches"]["balance_sheet"]["records"] = [
                row for row in payload["batches"]["balance_sheet"]["records"]
                if row["REPORT_DATE"] != "2025-06-30"
            ]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing required periods"):
                _validate_fixture_structure(root)

    def test_validator_rejects_missing_identity_or_date_fields(self):
        temporary, root = self.copied_fixture_root()
        with temporary:
            path = root / STATEMENT_FIXTURES[1]
            payload = json.loads(path.read_text(encoding="utf-8"))
            del payload["batches"]["profit_sheet"]["records"][0]["NOTICE_DATE"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing identity/date field"):
                _validate_fixture_structure(root)

    def test_validator_rejects_trade_calendar_without_mandated_span(self):
        temporary, root = self.copied_fixture_root()
        with temporary:
            path = root / "trade_calendar_2021_2026.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["request"]["start_date"] = "2021-01-04"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not span required range"):
                _validate_fixture_structure(root)

    def test_validator_rejects_trade_calendar_interior_hole(self):
        temporary, root = self.copied_fixture_root()
        with temporary:
            path = root / "trade_calendar_2021_2026.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            del payload["records"][len(payload["records"]) // 2]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "every date exactly once"):
                _validate_fixture_structure(root)

    def test_validator_accepts_complete_shuffled_trade_calendar(self):
        temporary, root = self.copied_fixture_root()
        with temporary:
            path = root / "trade_calendar_2021_2026.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            random.Random(23).shuffle(payload["records"])
            path.write_text(json.dumps(payload), encoding="utf-8")
            _validate_fixture_structure(root)


if __name__ == "__main__":
    unittest.main()
