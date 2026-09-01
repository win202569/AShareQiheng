from __future__ import annotations

from datetime import date, timedelta
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import ashare_pipeline.financial_features as financial_features_module
import ashare_pipeline.financial_schema as financial_schema_module

from ashare_pipeline.feature_contract import DIMENSIONS, FeatureBundle, canonical_sha256
from ashare_pipeline.financial_features import (
    FORMULA_VERSION,
    QualityIssue,
    build_feature_bundle,
    build_financial_facts,
    feature_input_hash,
    positive_cagr,
    select_visible_facts,
    symmetric_growth,
    trading_days_from_batch,
)
from ashare_pipeline.financial_schema import (
    FinancialFact,
    MAPPING_VERSION,
    raw_financial_slot_descriptor,
)
from ashare_pipeline.industry_templates import TEMPLATE_VERSION, resolve_template
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

PERIOD_KEYS = {
    "2021-12-31": "FY2021",
    "2022-12-31": "FY2022",
    "2023-12-31": "FY2023",
    "2024-12-31": "FY2024",
    "2025-12-31": "FY2025",
    "2025-06-30": "2025H1",
    "2026-06-30": "2026H1",
}

INSTANT_METRICS = {
    "cash", "total_assets", "total_liabilities", "parent_equity", "total_equity",
    "short_term_debt", "current_portion_long_term_debt", "long_term_debt",
    "bonds_payable", "lease_liabilities", "notes_receivable", "accounts_receivable",
    "contract_assets", "inventory", "notes_payable", "accounts_payable",
    "contract_liabilities", "share_capital", "goodwill",
}

BALANCE_METRICS = INSTANT_METRICS
CASH_FLOW_METRICS = {
    "operating_cash_flow", "capital_expenditure", "cash_dividends", "interest_paid",
    "acquisition_cash_paid", "disposal_long_asset_cash", "equity_financing_cash",
    "debt_financing_cash", "debt_repayment_cash", "share_repurchase_cash",
}


def bundle_fact(metric_key: str, period_end: str, value: float, *, serial: int = 0) -> FinancialFact:
    descriptor = raw_financial_slot_descriptor(metric_key)
    nature = "instant" if metric_key in INSTANT_METRICS else "duration"
    statement = (
        "balance" if metric_key in BALANCE_METRICS
        else "cash_flow" if metric_key in CASH_FLOW_METRICS
        else "income"
    )
    period_kind = "FY" if period_end.endswith("12-31") else "H1"
    return FinancialFact.create(
        security_id="SH600001",
        statement=statement,
        metric_key=metric_key,
        period_start=None if nature == "instant" else f"{period_end[:4]}-01-01",
        period_end=period_end,
        period_kind=period_kind,
        value=value,
        unit="shares" if metric_key == "share_capital" else "CNY",
        nature=nature,
        announced_at_utc="2026-03-31T15:59:59+00:00",
        effective_at_utc="2026-04-01T07:00:00+00:00",
        source_updated_at_utc=None,
        source_snapshot_id=f"snapshot-{period_end}-{metric_key}-{serial}",
        source_field=descriptor.source_fields[0],
        raw_row_hash=canonical_sha256({"metric": metric_key, "period": period_end, "value": value, "serial": serial}),
        mapping_version=MAPPING_VERSION,
        created_at="2026-08-29T00:00:00+00:00",
    )


def hand_checked_general_facts(*, fy2025_revenue: float = 1_000.0) -> tuple[FinancialFact, ...]:
    values_by_period = {
        "2024-12-31": {
            "total_assets": 800.0, "total_equity": 400.0, "cash": 100.0,
            "short_term_debt": 100.0, "current_portion_long_term_debt": 100.0,
            "long_term_debt": 100.0, "bonds_payable": 100.0, "lease_liabilities": 100.0,
        },
        "2025-12-31": {
            "revenue": fy2025_revenue, "operating_cost": 600.0, "total_profit": 200.0,
            "interest_expense": 50.0, "income_tax": 40.0, "net_profit": 130.0,
            "operating_cash_flow": 150.0, "capital_expenditure": 20.0,
            "total_assets": 1_000.0, "total_equity": 600.0, "cash": 100.0,
            "short_term_debt": 100.0, "current_portion_long_term_debt": 100.0,
            "long_term_debt": 100.0, "bonds_payable": 100.0, "lease_liabilities": 100.0,
            "notes_receivable": 20.0, "accounts_receivable": 80.0,
            "contract_assets": 30.0, "inventory": 70.0, "notes_payable": 15.0,
            "accounts_payable": 55.0, "contract_liabilities": 10.0,
        },
    }
    return tuple(
        bundle_fact(metric, period, value)
        for period, values in values_by_period.items()
        for metric, value in values.items()
    )


def complete_general_facts() -> tuple[FinancialFact, ...]:
    facts = []
    for index, period_end in enumerate(PERIOD_KEYS, start=1):
        for metric in resolve_template("包装印刷").financial_slots:
            value = 10.0 + index
            if metric == "revenue":
                value = 100.0 + index * 10.0
            elif metric == "operating_cost":
                value = 60.0 + index
            elif metric == "total_profit":
                value = 20.0 + index
            elif metric == "income_tax":
                value = 4.0
            elif metric == "interest_expense":
                value = 2.0
            elif metric == "net_profit":
                value = 18.0 + index
            elif metric == "operating_cash_flow":
                value = 20.0 + index
            elif metric == "capital_expenditure":
                value = 5.0
            elif metric == "cash":
                value = 50.0
            elif metric == "total_assets":
                value = 800.0 + index * 100.0
            elif metric == "total_liabilities":
                value = 300.0
            elif metric in {"total_equity", "parent_equity"}:
                value = 500.0 + index * 100.0
            elif metric in {
                "short_term_debt", "current_portion_long_term_debt", "long_term_debt",
                "bonds_payable", "lease_liabilities",
            }:
                value = 10.0
            facts.append(bundle_fact(metric, period_end, value, serial=index))
    return tuple(facts)


def build_bundle_with_overrides(**overrides):
    arguments = {
        "security_id": "SH600001",
        "report_period": "2026-06-30",
        "as_of_utc": "2026-08-29T16:00:00+00:00",
        "candidate_set_hash": "c" * 64,
        "source_industry_name": "包装印刷",
        "facts": complete_general_facts(),
        "fact_blockers": (),
        "statement_snapshot_hashes": {
            "balance_sheet": "1" * 64,
            "profit_sheet": "2" * 64,
            "cash_flow_sheet": "3" * 64,
        },
        "trade_calendar_snapshot_hash": "4" * 64,
        "reported_target_period": True,
    }
    arguments.update(overrides)
    return build_feature_bundle(**arguments)


def rebuild_fact(fact: FinancialFact, **overrides) -> FinancialFact:
    fields = fact.to_record()
    fields.pop("id")
    fields.update(overrides)
    return FinancialFact.create(**fields)


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

    def calendar_batch(
        self,
        *,
        records=None,
        request=None,
        source="baostock",
        dataset="trade_dates",
    ):
        return FetchBatch(
            source, dataset,
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
            self.calendar_batch(source="not-baostock"),
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


class FinancialFormulaTests(unittest.TestCase):
    def test_growth_edges_do_not_invent_denominators(self):
        self.assertAlmostEqual(symmetric_growth(120.0, 100.0), 18.181818181818183)
        self.assertEqual(symmetric_growth(100.0, -100.0), 200.0)
        self.assertIsNone(symmetric_growth(0.0, 0.0))
        self.assertAlmostEqual(positive_cagr(100.0, 133.1, 3), 10.0)
        self.assertIsNone(positive_cagr(0.0, 133.1, 3))
        self.assertIsNone(positive_cagr(100.0, -1.0, 3))
        self.assertIsNone(positive_cagr(100.0, 133.1, 0))

    def test_growth_helpers_fail_closed_on_nonfinite_values(self):
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                self.assertIsNone(symmetric_growth(invalid, 1.0))
                self.assertIsNone(positive_cagr(1.0, invalid, 1))


class FeatureInputHashTests(unittest.TestCase):
    def hash_arguments(self):
        return {
            "security_id": "SH600001",
            "report_period": "2026-06-30",
            "as_of_utc": "2026-08-29T16:00:00+00:00",
            "candidate_set_hash": "c" * 64,
            "statement_snapshot_hashes": {
                "balance_sheet": "1" * 64,
                "profit_sheet": "2" * 64,
                "cash_flow_sheet": "3" * 64,
            },
            "trade_calendar_snapshot_hash": "4" * 64,
        }

    def test_hash_matches_the_exact_declared_canonical_payload(self):
        expected = canonical_sha256({
            "security_id": "SH600001",
            "report_period": "2026-06-30",
            "as_of_utc": "2026-08-29T16:00:00+00:00",
            "candidate_set_hash": "c" * 64,
            "statement_snapshot_hashes": {
                "balance_sheet": "1" * 64,
                "profit_sheet": "2" * 64,
                "cash_flow_sheet": "3" * 64,
            },
            "trade_calendar_snapshot_hash": "4" * 64,
            "contract_version": "feature-contract-v1",
            "mapping_version": "eastmoney-financial-mapping-v1",
            "template_version": "template-registry-v1",
            "formula_version": "financial-derived-v1",
        })
        self.assertEqual(feature_input_hash(**self.hash_arguments()), expected)

    def test_omitted_statement_key_equals_explicit_null_but_real_snapshot_changes_hash(self):
        arguments = self.hash_arguments()
        omitted = dict(arguments["statement_snapshot_hashes"])
        del omitted["cash_flow_sheet"]
        explicit_null = {**omitted, "cash_flow_sheet": None}
        real = {**omitted, "cash_flow_sheet": "f" * 64}
        self.assertEqual(
            feature_input_hash(**{**arguments, "statement_snapshot_hashes": omitted}),
            feature_input_hash(**{**arguments, "statement_snapshot_hashes": explicit_null}),
        )
        self.assertNotEqual(
            feature_input_hash(**{**arguments, "statement_snapshot_hashes": explicit_null}),
            feature_input_hash(**{**arguments, "statement_snapshot_hashes": real}),
        )

    def test_hash_is_sensitive_to_each_runtime_and_version_dependency(self):
        arguments = self.hash_arguments()
        baseline = feature_input_hash(**arguments)
        changes = {
            "security_id": "SZ600001",
            "report_period": "2025-12-31",
            "as_of_utc": "2026-08-30T16:00:00+00:00",
            "candidate_set_hash": "d" * 64,
            "trade_calendar_snapshot_hash": "5" * 64,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                self.assertNotEqual(feature_input_hash(**{**arguments, field: value}), baseline)
        for dataset in ("balance_sheet", "profit_sheet", "cash_flow_sheet"):
            with self.subTest(dataset=dataset):
                snapshots = {**arguments["statement_snapshot_hashes"], dataset: "9" * 64}
                self.assertNotEqual(
                    feature_input_hash(**{**arguments, "statement_snapshot_hashes": snapshots}),
                    baseline,
                )
        for constant in ("CONTRACT_VERSION", "MAPPING_VERSION", "TEMPLATE_VERSION", "FORMULA_VERSION"):
            with self.subTest(constant=constant), patch.object(financial_features_module, constant, f"changed-{constant}"):
                self.assertNotEqual(feature_input_hash(**arguments), baseline)

    def test_hash_rejects_nan_instead_of_serializing_it(self):
        arguments = self.hash_arguments()
        with self.assertRaises(ValueError):
            feature_input_hash(**{
                **arguments,
                "statement_snapshot_hashes": {"balance_sheet": math.nan},
            })


class FeatureBundleBuildTests(unittest.TestCase):
    @staticmethod
    def values(bundle):
        return {
            value.key: value
            for dimension in bundle.dimension_inputs.values()
            for value in dimension.values
        }

    @staticmethod
    def replace_fact(facts, metric_key, period_end, value):
        return tuple(
            bundle_fact(metric_key, period_end, value, serial=99)
            if fact.metric_key == metric_key and fact.period_end == period_end
            else fact
            for fact in facts
        )

    def test_general_bundle_computes_hand_checked_inputs(self):
        bundle = build_bundle_with_overrides(facts=hand_checked_general_facts())
        values = {key: item.value for key, item in self.values(bundle).items()}
        self.assertEqual(values["m.gross_profit.FY2025"], 400.0)
        self.assertEqual(values["m.ebit.FY2025"], 250.0)
        self.assertEqual(values["m.effective_tax_rate.FY2025"], 0.2)
        self.assertEqual(values["m.nopat.FY2025"], 200.0)
        self.assertEqual(values["ca.fcf.FY2025"], 130.0)
        self.assertEqual(values["fs.interest_bearing_debt.FY2025"], 500.0)
        self.assertEqual(values["fs.net_debt.FY2025"], 400.0)
        self.assertEqual(values["m.invested_capital.FY2025"], 1_000.0)
        self.assertEqual(values["m.operating_working_capital.FY2025"], 120.0)
        self.assertAlmostEqual(values["eq.total_accruals.FY2025"], -20.0 / 900.0)
        self.assertAlmostEqual(values["m.roic.FY2025"], 200.0 / 900.0)
        self.assertEqual(values["m.gross_margin.FY2025"], 0.4)

    def test_general_bundle_with_no_facts_is_valid_partial_with_explicit_missing_slots(self):
        bundle = build_bundle_with_overrides(facts=())
        values = self.values(bundle)

        self.assertEqual(bundle.financial_status, "partial")
        self.assertEqual(bundle.financial_coverage, 0.0)
        self.assertEqual(bundle.dimension_inputs["M"].status, "missing")
        self.assertEqual(values["m.roic.FY2021"].status, "not_applicable")
        self.assertEqual(
            values["g.revenue.FY2022"].missing_reason,
            "financial_fact_missing:revenue",
        )

    def test_general_bundle_with_only_balance_and_cash_facts_is_valid_partial(self):
        partial_facts = tuple(
            fact
            for fact in complete_general_facts()
            if fact.statement in {"balance", "cash_flow"}
        )

        bundle = build_bundle_with_overrides(facts=partial_facts)

        self.assertEqual(bundle.financial_status, "partial")
        self.assertGreater(bundle.financial_coverage, 0.0)
        self.assertLess(bundle.financial_coverage, 1.0)
        self.assertEqual(bundle.dimension_inputs["M"].status, "partial")

    def test_tax_rate_is_bounded_and_invalid_ratio_denominators_fail_closed(self):
        negative_tax = self.replace_fact(hand_checked_general_facts(), "income_tax", "2025-12-31", -10.0)
        excessive_tax = self.replace_fact(hand_checked_general_facts(), "income_tax", "2025-12-31", 200.0)
        zero_profit = self.replace_fact(hand_checked_general_facts(), "total_profit", "2025-12-31", 0.0)
        zero_revenue = hand_checked_general_facts(fy2025_revenue=0.0)
        for facts, expected in ((negative_tax, 0.0), (excessive_tax, 0.5)):
            with self.subTest(expected=expected):
                values = self.values(build_bundle_with_overrides(facts=facts))
                self.assertEqual(values["m.effective_tax_rate.FY2025"].value, expected)
        self.assertEqual(
            self.values(build_bundle_with_overrides(facts=zero_profit))["m.effective_tax_rate.FY2025"].status,
            "missing",
        )
        self.assertEqual(
            self.values(build_bundle_with_overrides(facts=zero_revenue))["m.gross_margin.FY2025"].status,
            "missing",
        )

    def test_zero_average_assets_and_invested_capital_fail_closed(self):
        facts = self.replace_fact(hand_checked_general_facts(), "total_assets", "2024-12-31", -1_000.0)
        values = self.values(build_bundle_with_overrides(facts=facts))
        self.assertEqual(values["eq.total_accruals.FY2025"].status, "missing")
        facts = self.replace_fact(hand_checked_general_facts(), "total_equity", "2024-12-31", -1_400.0)
        values = self.values(build_bundle_with_overrides(facts=facts))
        self.assertEqual(values["m.roic.FY2025"].status, "missing")

    def test_negative_nonzero_ratio_denominators_are_hand_calculated(self):
        negative_revenue = hand_checked_general_facts(fy2025_revenue=-1_000.0)
        revenue_values = self.values(
            build_bundle_with_overrides(facts=negative_revenue)
        )
        self.assertEqual(revenue_values["m.gross_margin.FY2025"].status, "derived")
        self.assertEqual(revenue_values["m.gross_margin.FY2025"].value, 1.6)

        negative_average_assets = self.replace_fact(
            hand_checked_general_facts(),
            "total_assets",
            "2024-12-31",
            -1_200.0,
        )
        accrual_values = self.values(
            build_bundle_with_overrides(facts=negative_average_assets)
        )
        self.assertEqual(
            accrual_values["eq.total_accruals.FY2025"].status, "derived"
        )
        self.assertEqual(
            accrual_values["eq.total_accruals.FY2025"].value, 0.2
        )

        negative_average_invested = self.replace_fact(
            hand_checked_general_facts(),
            "total_equity",
            "2024-12-31",
            -2_000.0,
        )
        roic_values = self.values(
            build_bundle_with_overrides(facts=negative_average_invested)
        )
        self.assertEqual(roic_values["m.roic.FY2025"].status, "derived")
        self.assertAlmostEqual(
            roic_values["m.roic.FY2025"].value, -2.0 / 3.0
        )

    def test_fact_blockers_survive_verbatim_and_keep_bundle_blocked(self):
        bundle = build_bundle_with_overrides(
            fact_blockers=(
                "trade_calendar_missing_next_session", "conflicting_fact_versions",
                "conflicting_fact_versions",
            )
        )
        self.assertEqual(bundle.blockers, (
            "conflicting_fact_versions",
            "formal_industry_mapping_missing",
            "trade_calendar_missing_next_session",
        ))
        self.assertEqual(bundle.financial_status, "blocked")

    def test_builder_recomputes_balance_equation_when_caller_omits_blocker(self):
        imbalanced = self.replace_fact(
            complete_general_facts(), "total_assets", "2021-12-31", 10_000.0
        )

        bundle = build_bundle_with_overrides(
            facts=imbalanced, fact_blockers=()
        )

        self.assertEqual(bundle.financial_status, "blocked")
        self.assertIn("balance_equation_mismatch", bundle.blockers)
        for dimension in ("G", "M", "EQ", "FS", "CA"):
            self.assertEqual(bundle.dimension_inputs[dimension].status, "blocked")

    def test_complete_financial_inputs_are_ready_despite_formal_mapping_blocker(self):
        bundle = build_bundle_with_overrides()
        self.assertEqual(bundle.financial_status, "financial_ready")
        self.assertEqual(bundle.financial_coverage, 1.0)
        self.assertEqual(tuple(bundle.dimension_inputs), DIMENSIONS)
        self.assertEqual(bundle.blockers, ("formal_industry_mapping_missing",))
        self.assertIsNone(bundle.confidence_inputs.formal_confidence)
        self.assertFalse(bundle.is_formal_score_ready)
        self.assertNotIn("score", bundle.to_dict())
        serialized = json.dumps(bundle.to_dict(), ensure_ascii=False)
        for forbidden in ('"S0"', '"Sc"', '"pool"', '"buy"', '"sell"'):
            self.assertNotIn(forbidden, serialized)

    def test_all_nonspecialized_common_templates_keep_the_exact_ready_projection(self):
        cases = (
            ("包装印刷", "general_nonfinancial"),
            ("电力", "utility"),
            ("半导体", "rd_growth"),
        )
        for industry_name, template_id in cases:
            with self.subTest(template=template_id):
                bundle = build_bundle_with_overrides(
                    source_industry_name=industry_name
                )
                restored = FeatureBundle.from_dict(bundle.to_dict())
                financial_values = tuple(
                    value
                    for dimension in ("G", "M", "EQ", "FS", "CA")
                    for value in restored.dimension_inputs[dimension].values
                )
                self.assertEqual(restored.industry.template_id, template_id)
                self.assertEqual(restored.financial_status, "financial_ready")
                self.assertEqual(restored.financial_coverage, 1.0)
                self.assertEqual(len(financial_values), 363)
                self.assertEqual(restored.to_dict(), bundle.to_dict())

    def test_fy2021_average_formula_slots_are_explicitly_not_applicable(self):
        bundle = build_bundle_with_overrides()
        values = self.values(bundle)
        for key in ("eq.total_accruals.FY2021", "m.roic.FY2021"):
            with self.subTest(key=key):
                value = values[key]
                self.assertEqual(value.status, "not_applicable")
                self.assertIsNone(value.value)
                self.assertEqual(value.unit, "ratio")
                self.assertEqual(value.evidence, ())
                self.assertEqual(value.missing_reason, "frozen_window_no_opening_period")
        applicable = [
            value
            for dimension in bundle.dimension_inputs.values()
            for value in dimension.values
            if value.status != "not_applicable"
        ]
        self.assertEqual(len(applicable), 361)
        self.assertEqual(bundle.financial_coverage, 1.0)
        self.assertEqual(bundle.financial_status, "financial_ready")
        self.assertEqual(bundle.dimension_inputs["M"].status, "input_ready")
        self.assertEqual(bundle.dimension_inputs["EQ"].status, "input_ready")

    def test_cross_security_facts_are_filtered_blocked_and_never_become_evidence(self):
        wrong_facts = tuple(
            rebuild_fact(fact, security_id="SZ000001")
            for fact in complete_general_facts()
        )
        wrong_ids = {fact.id for fact in wrong_facts}
        bundle = build_bundle_with_overrides(facts=wrong_facts)
        evidence_ids = {
            evidence.financial_fact_id
            for dimension in bundle.dimension_inputs.values()
            for value in dimension.values
            for evidence in value.evidence
        }
        self.assertEqual(bundle.financial_status, "blocked")
        self.assertIn("financial_fact_security_mismatch", bundle.blockers)
        self.assertTrue(evidence_ids.isdisjoint(wrong_ids))
        self.assertEqual(bundle.financial_coverage, 0.0)

    def test_mixed_security_facts_filter_wrong_inputs_and_keep_bundle_blocked(self):
        correct = complete_general_facts()
        wrong = tuple(
            rebuild_fact(fact, security_id="SZ000001")
            for fact in correct[:8]
        )
        wrong_ids = {fact.id for fact in wrong}
        bundle = build_bundle_with_overrides(facts=(*correct, *wrong))
        evidence_ids = {
            evidence.financial_fact_id
            for dimension in bundle.dimension_inputs.values()
            for value in dimension.values
            for evidence in value.evidence
        }
        self.assertEqual(bundle.financial_status, "blocked")
        self.assertIn("financial_fact_security_mismatch", bundle.blockers)
        self.assertTrue(evidence_ids.isdisjoint(wrong_ids))
        self.assertEqual(bundle.financial_coverage, 1.0)

    def test_old_mapping_facts_are_filtered_and_mapping_inconsistency_blocks(self):
        old_mapping = "eastmoney-financial-mapping-v0"
        current_facts = complete_general_facts()
        with patch.object(financial_schema_module, "MAPPING_VERSION", old_mapping):
            old_facts = tuple(
                rebuild_fact(fact, mapping_version=old_mapping)
                for fact in current_facts
            )
        old_ids = {fact.id for fact in old_facts}
        bundle = build_bundle_with_overrides(facts=old_facts)
        evidence_ids = {
            evidence.financial_fact_id
            for dimension in bundle.dimension_inputs.values()
            for value in dimension.values
            for evidence in value.evidence
        }
        self.assertEqual(bundle.financial_status, "blocked")
        self.assertIn("financial_fact_mapping_version_mismatch", bundle.blockers)
        self.assertFalse(bundle.confidence_inputs.mapping_consistent)
        self.assertTrue(evidence_ids.isdisjoint(old_ids))
        self.assertEqual(bundle.financial_coverage, 0.0)

    def test_each_required_period_is_required_for_financial_ready(self):
        complete = complete_general_facts()
        for period_end in PERIOD_KEYS:
            with self.subTest(period_end=period_end):
                incomplete = tuple(fact for fact in complete if fact.period_end != period_end)
                bundle = build_bundle_with_overrides(facts=incomplete)
                self.assertEqual(bundle.financial_status, "partial")
                self.assertLess(bundle.financial_coverage, 1.0)

    def test_bank_has_zero_applicable_slots_and_no_industrial_debt_or_roic(self):
        bundle = build_bundle_with_overrides(source_industry_name="银行")
        keys = set(self.values(bundle))
        self.assertEqual(bundle.financial_status, "blocked")
        self.assertEqual(bundle.financial_coverage, 0.0)
        self.assertFalse(any("interest_bearing_debt" in key or ".roic." in key for key in keys))

    def test_specialized_real_estate_and_resource_templates_never_ready_on_common_inputs(self):
        cases = (
            ("房地产开发", "real_estate_high_leverage"),
            ("工业金属", "resource_cycle"),
        )
        for industry, template_id in cases:
            with self.subTest(industry=industry):
                template = resolve_template(industry)
                bundle = build_bundle_with_overrides(
                    source_industry_name=industry
                )
                values = self.values(bundle)
                self.assertEqual(bundle.industry.template_id, template_id)
                self.assertTrue(template.specialized_inputs_required)
                self.assertIn("fs.interest_bearing_debt.FY2025", values)
                self.assertIn("m.roic.FY2025", values)
                self.assertEqual(bundle.financial_coverage, 1.0)
                self.assertEqual(bundle.financial_status, "blocked")
                self.assertIn(
                    "specialized_financial_inputs_missing", bundle.blockers
                )

    def test_unclassified_template_blocks_instead_of_falling_back(self):
        bundle = build_bundle_with_overrides(source_industry_name="不存在行业")
        self.assertEqual(bundle.industry.template_id, "unclassified")
        self.assertIn("industry_template_unclassified", bundle.blockers)
        self.assertEqual(bundle.financial_status, "blocked")

    def test_v_and_t_are_missing_containers_and_ca_only_has_accounting_allocation_inputs(self):
        bundle = build_bundle_with_overrides()
        for dimension in ("V", "T"):
            self.assertEqual(bundle.dimension_inputs[dimension].status, "missing")
            self.assertEqual(bundle.dimension_inputs[dimension].values, ())
        allowed_ca_fragments = {
            "fcf", "capital_expenditure", "cash_dividends", "interest_paid",
            "acquisition_cash_paid", "disposal_long_asset_cash",
            "equity_financing_cash", "debt_financing_cash", "debt_repayment_cash",
            "share_repurchase_cash",
        }
        for value in bundle.dimension_inputs["CA"].values:
            self.assertIn(value.key.split(".")[1], allowed_ca_fragments)

    def test_coverage_counts_observed_and_derived_and_excludes_not_applicable(self):
        bundle = build_bundle_with_overrides(facts=hand_checked_general_facts())
        applicable = [
            value
            for dimension in bundle.dimension_inputs.values()
            for value in dimension.values
            if value.status != "not_applicable"
        ]
        complete = [value for value in applicable if value.status in {"observed", "derived"}]
        self.assertAlmostEqual(bundle.financial_coverage, len(complete) / len(applicable))

    def test_missing_snapshot_and_post_cutoff_reported_target_add_exact_blockers(self):
        snapshots = {"balance_sheet": "1" * 64, "profit_sheet": "2" * 64}
        before = build_bundle_with_overrides(
            statement_snapshot_hashes=snapshots,
            as_of_utc="2026-08-31T15:59:59+00:00",
        )
        after = build_bundle_with_overrides(
            statement_snapshot_hashes=snapshots,
            as_of_utc="2026-08-31T16:00:00+00:00",
        )
        not_reported = build_bundle_with_overrides(
            statement_snapshot_hashes=snapshots,
            as_of_utc="2026-08-31T16:00:00+00:00",
            reported_target_period=False,
        )
        self.assertNotIn("reported_but_statement_missing", before.blockers)
        self.assertIn("reported_but_statement_missing", after.blockers)
        self.assertNotIn("reported_but_statement_missing", not_reported.blockers)

    def test_post_cutoff_target_facts_missing_blocks_even_when_all_snapshots_exist(self):
        historical_only = tuple(
            fact
            for fact in complete_general_facts()
            if fact.period_end != "2026-06-30"
        )

        bundle = build_bundle_with_overrides(
            facts=historical_only,
            as_of_utc="2026-08-31T16:00:00+00:00",
        )

        self.assertIn("reported_but_statement_missing", bundle.blockers)
        self.assertEqual(bundle.financial_status, "blocked")

    def test_missing_calendar_blocks_and_fact_order_is_deterministic(self):
        facts = list(complete_general_facts())
        first = build_bundle_with_overrides(facts=facts, trade_calendar_snapshot_hash=None)
        random.Random(31).shuffle(facts)
        second = build_bundle_with_overrides(facts=facts, trade_calendar_snapshot_hash=None)
        self.assertIn("trade_calendar_missing", first.blockers)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.bundle_hash(), second.bundle_hash())

    def test_bundle_remains_deeply_immutable(self):
        bundle = build_bundle_with_overrides()
        with self.assertRaises(TypeError):
            bundle.dimension_inputs["G"] = bundle.dimension_inputs["V"]
        with self.assertRaises((AttributeError, TypeError)):
            bundle.dimension_inputs["G"].values += bundle.dimension_inputs["G"].values[:1]


if __name__ == "__main__":
    unittest.main()
