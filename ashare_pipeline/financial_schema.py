"""Versioned contracts for normalized, point-in-time financial facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
import re
from typing import Any, Iterable, Literal, Mapping

from ashare_pipeline.feature_contract import (
    FINANCIAL_DIMENSIONS,
    canonical_sha256,
    require_aware_utc,
)


MAPPING_VERSION = "eastmoney-financial-mapping-v2"
FINANCIAL_REQUEST_VERSION = "eastmoney-financial-request-v1"

StatementDataset = Literal["balance_sheet", "profit_sheet", "cash_flow_sheet"]
StatementKind = Literal["balance", "income", "cash_flow"]

DATASET_TO_STATEMENT: dict[str, str] = {
    "balance_sheet": "balance",
    "profit_sheet": "income",
    "cash_flow_sheet": "cash_flow",
}
STATEMENT_TO_DATASET = {value: key for key, value in DATASET_TO_STATEMENT.items()}
TARGET_PERIOD_ENDS = frozenset({
    "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31",
    "2025-12-31", "2025-06-30", "2026-06-30",
})

FACT_UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})
PERIOD_KINDS = frozenset({"FY", "H1", "Q1", "Q3", "OTHER"})
NATURES = frozenset({"instant", "duration"})
_SECURITY_ID = re.compile(r"^(?:SH|SZ)\d{6}$")
_PERIOD_KIND_BY_MONTH_DAY = {
    (12, 31): "FY",
    (6, 30): "H1",
    (3, 31): "Q1",
    (9, 30): "Q3",
}


@dataclass(frozen=True)
class PeriodInfo:
    period_start: str
    period_end: str
    period_kind: str
    is_feature_period: bool


def classify_period(
    report_date: str, report_date_name: str | None, report_type: str | None
) -> PeriodInfo | None:
    """Classify valid statement dates without discarding non-feature periods."""
    del report_date_name, report_type  # Report dates are the authoritative classification input.
    try:
        parsed = date.fromisoformat(report_date)
    except (TypeError, ValueError):
        return None
    period_end = parsed.isoformat()
    month_day = (parsed.month, parsed.day)
    period_kind = _PERIOD_KIND_BY_MONTH_DAY.get(month_day, "OTHER")
    return PeriodInfo(
        period_start=date(parsed.year, 1, 1).isoformat(),
        period_end=period_end,
        period_kind=period_kind,
        is_feature_period=period_end in TARGET_PERIOD_ENDS,
    )


@dataclass(frozen=True)
class FieldRule:
    statement: StatementKind
    metric_key: str
    source_fields: tuple[str, ...]
    unit: str
    nature: str

    def __post_init__(self) -> None:
        if self.statement not in STATEMENT_TO_DATASET:
            raise ValueError("invalid statement")
        if not self.metric_key or not self.source_fields:
            raise ValueError("field rules require a metric key and source fields")
        if self.unit not in FACT_UNITS or self.nature not in NATURES:
            raise ValueError("invalid field rule unit or nature")


_FIELD_RULES: tuple[FieldRule, ...] = (
    FieldRule("income", "revenue", ("TOTAL_OPERATE_INCOME", "OPERATE_INCOME"), "CNY", "duration"),
    FieldRule("income", "operating_cost", ("TOTAL_OPERATE_COST", "OPERATE_COST"), "CNY", "duration"),
    FieldRule("income", "operating_profit", ("OPERATE_PROFIT",), "CNY", "duration"),
    FieldRule("income", "total_profit", ("TOTAL_PROFIT",), "CNY", "duration"),
    FieldRule("income", "income_tax", ("INCOME_TAX",), "CNY", "duration"),
    FieldRule("income", "net_profit", ("NETPROFIT",), "CNY", "duration"),
    FieldRule("income", "parent_net_profit", ("PARENT_NETPROFIT",), "CNY", "duration"),
    FieldRule("income", "deduct_parent_net_profit", ("DEDUCT_PARENT_NETPROFIT",), "CNY", "duration"),
    FieldRule("income", "interest_expense", ("INTEREST_EXPENSE",), "CNY", "duration"),
    FieldRule("income", "rd_expense", ("RESEARCH_EXPENSE", "RD_EXPENSE"), "CNY", "duration"),
    FieldRule("balance", "cash", ("MONETARYFUNDS",), "CNY", "instant"),
    FieldRule("balance", "total_assets", ("TOTAL_ASSETS",), "CNY", "instant"),
    FieldRule("balance", "total_liabilities", ("TOTAL_LIABILITIES",), "CNY", "instant"),
    FieldRule("balance", "parent_equity", ("TOTAL_PARENT_EQUITY", "PARENT_EQUITY_BALANCE"), "CNY", "instant"),
    FieldRule("balance", "total_equity", ("TOTAL_EQUITY",), "CNY", "instant"),
    FieldRule("balance", "short_term_debt", ("SHORT_LOAN", "SHORT_FIN_PAYABLE"), "CNY", "instant"),
    FieldRule("balance", "current_portion_long_term_debt", ("NONCURRENT_LIAB_1YEAR",), "CNY", "instant"),
    FieldRule("balance", "long_term_debt", ("LONG_LOAN",), "CNY", "instant"),
    FieldRule("balance", "bonds_payable", ("BOND_PAYABLE",), "CNY", "instant"),
    FieldRule("balance", "lease_liabilities", ("LEASE_LIAB",), "CNY", "instant"),
    FieldRule("balance", "notes_receivable", ("NOTE_RECE",), "CNY", "instant"),
    FieldRule("balance", "accounts_receivable", ("ACCOUNTS_RECE",), "CNY", "instant"),
    FieldRule("balance", "contract_assets", ("CONTRACT_ASSET",), "CNY", "instant"),
    FieldRule("balance", "inventory", ("INVENTORY",), "CNY", "instant"),
    FieldRule("balance", "notes_payable", ("NOTE_PAYABLE",), "CNY", "instant"),
    FieldRule("balance", "accounts_payable", ("ACCOUNTS_PAYABLE",), "CNY", "instant"),
    FieldRule("balance", "contract_liabilities", ("CONTRACT_LIAB",), "CNY", "instant"),
    FieldRule("balance", "share_capital", ("SHARE_CAPITAL",), "shares", "instant"),
    FieldRule("balance", "goodwill", ("GOODWILL",), "CNY", "instant"),
    FieldRule("cash_flow", "operating_cash_flow", ("NETCASH_OPERATE", "OPERATE_NETCASH_BALANCE"), "CNY", "duration"),
    FieldRule("cash_flow", "capital_expenditure", ("CONSTRUCT_LONG_ASSET",), "CNY", "duration"),
    FieldRule("cash_flow", "cash_dividends", ("ASSIGN_DIVIDEND_PORFIT",), "CNY", "duration"),
    FieldRule("cash_flow", "interest_paid", ("PAY_INTEREST",), "CNY", "duration"),
    FieldRule("cash_flow", "acquisition_cash_paid", ("INVEST_PAY_CASH",), "CNY", "duration"),
    FieldRule("cash_flow", "disposal_long_asset_cash", ("DISPOSAL_LONG_ASSET",), "CNY", "duration"),
    FieldRule("cash_flow", "equity_financing_cash", ("ACCEPT_INVEST_CASH", "RECEIVE_ADD_EQUITY"), "CNY", "duration"),
    FieldRule("cash_flow", "debt_financing_cash", ("ISSUE_BOND",), "CNY", "duration"),
    FieldRule("cash_flow", "debt_repayment_cash", ("PAY_DEBT_CASH",), "CNY", "duration"),
)

# The tracked Eastmoney cash-flow snapshots expose no dedicated, auditable share-repurchase field.
# Mixed fields such as PAY_OTHER_FINANCE must not be presented as a repurchase payment.
UNMAPPED_COMMON_FACTS: dict[str, str] = {
    "share_repurchase_cash": "source_field_unavailable",
}


@dataclass(frozen=True)
class RawFinancialSlotDescriptor:
    metric_key: str
    dimension: str
    kind: str
    allowed_statuses: tuple[str, ...]
    formula_version: str
    unit: str
    source_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.metric_key or self.dimension not in FINANCIAL_DIMENSIONS:
            raise ValueError("raw financial slot requires a canonical dimension")
        if self.kind != "raw_fact" or self.allowed_statuses != ("observed",):
            raise ValueError("raw financial slot must require observed raw facts")
        if self.formula_version != MAPPING_VERSION:
            raise ValueError("raw financial slot must use the active mapping version")
        if self.unit not in FACT_UNITS or not self.source_fields:
            raise ValueError("raw financial slot requires unit and source-field metadata")

    def canonical_key(self, period_key: str) -> str:
        return f"{self.dimension.lower()}.{self.metric_key}.{period_key}"


def _raw_dimension(rule: FieldRule) -> str:
    if rule.metric_key == "revenue":
        return "G"
    if rule.statement == "income":
        return "M"
    if rule.metric_key == "operating_cash_flow":
        return "EQ"
    if rule.statement == "cash_flow":
        return "CA"
    return "FS"


_RAW_FINANCIAL_SLOT_DESCRIPTORS = {
    rule.metric_key: RawFinancialSlotDescriptor(
        metric_key=rule.metric_key,
        dimension=_raw_dimension(rule),
        kind="raw_fact",
        allowed_statuses=("observed",),
        formula_version=MAPPING_VERSION,
        unit=rule.unit,
        source_fields=rule.source_fields,
    )
    for rule in _FIELD_RULES
}
_RAW_FINANCIAL_SLOT_DESCRIPTORS["share_repurchase_cash"] = (
    RawFinancialSlotDescriptor(
        metric_key="share_repurchase_cash",
        dimension="CA",
        kind="raw_fact",
        allowed_statuses=("observed",),
        formula_version=MAPPING_VERSION,
        unit="CNY",
        source_fields=("SHARE_REPURCHASE_CASH",),
    )
)


def raw_financial_slot_descriptor(metric_key: str) -> RawFinancialSlotDescriptor:
    """Return the canonical metadata for one registered raw fact slot."""
    try:
        return _RAW_FINANCIAL_SLOT_DESCRIPTORS[metric_key]
    except KeyError as error:
        raise ValueError(f"unknown raw financial slot: {metric_key!r}") from error


def field_rules(statement: StatementKind | str) -> tuple[FieldRule, ...]:
    """Return the immutable, ordered fact mappings for one statement kind."""
    if statement not in STATEMENT_TO_DATASET:
        raise ValueError(f"invalid statement: {statement!r}")
    return tuple(rule for rule in _FIELD_RULES if rule.statement == statement)


def _require_iso_date(value: str | None, field: str, *, allow_none: bool) -> str | None:
    if value is None and allow_none:
        return None
    try:
        return date.fromisoformat(value or "").isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def _require_sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return value.lower()


@dataclass(frozen=True)
class FinancialFact:
    id: str
    security_id: str
    statement: StatementKind
    metric_key: str
    period_start: str | None
    period_end: str
    period_kind: str
    value: float
    unit: str
    nature: str
    announced_at_utc: str
    effective_at_utc: str
    source_updated_at_utc: str | None
    source_snapshot_id: str
    source_field: str
    raw_row_hash: str
    mapping_version: str
    created_at: str

    @classmethod
    def create(cls, **fields: Any) -> "FinancialFact":
        data = dict(fields)
        data.pop("id", None)
        normalized = cls._normalized_fields(data)
        identity_fields = dict(normalized)
        identity_fields.pop("created_at")
        fact_id = canonical_sha256(identity_fields)
        return cls(id=fact_id, **normalized)

    @classmethod
    def from_record(cls, value: Mapping[str, Any]) -> "FinancialFact":
        data = dict(value)
        supplied_id = data.pop("id", None)
        fact = cls.create(**data)
        if supplied_id is not None and supplied_id != fact.id:
            raise ValueError("financial fact id does not match canonical content")
        return fact

    @classmethod
    def _normalized_fields(cls, data: Mapping[str, Any]) -> dict[str, Any]:
        expected = {
            "security_id", "statement", "metric_key", "period_start", "period_end", "period_kind",
            "value", "unit", "nature", "announced_at_utc", "effective_at_utc", "source_updated_at_utc",
            "source_snapshot_id", "source_field", "raw_row_hash", "mapping_version", "created_at",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            extra = sorted(set(data) - expected)
            raise ValueError(f"financial fact fields mismatch; missing={missing}, extra={extra}")
        security_id = data["security_id"]
        if not isinstance(security_id, str) or not _SECURITY_ID.fullmatch(security_id):
            raise ValueError("security_id must be an SH/SZ security identifier")
        statement = data["statement"]
        if statement not in STATEMENT_TO_DATASET:
            raise ValueError("invalid statement")
        metric_key = data["metric_key"]
        if not isinstance(metric_key, str) or not metric_key:
            raise ValueError("metric_key is required")
        period_end = _require_iso_date(data["period_end"], "period_end", allow_none=False)
        period_start = _require_iso_date(data["period_start"], "period_start", allow_none=True)
        period_kind = data["period_kind"]
        if period_kind not in PERIOD_KINDS:
            raise ValueError("invalid period_kind")
        expected_period_kind = _PERIOD_KIND_BY_MONTH_DAY.get(
            (date.fromisoformat(period_end).month, date.fromisoformat(period_end).day), "OTHER"
        )
        if period_kind != expected_period_kind:
            raise ValueError("period_kind must match period_end")
        nature = data["nature"]
        if nature not in NATURES:
            raise ValueError("invalid nature")
        if nature == "instant" and period_start is not None:
            raise ValueError("instant facts cannot have period_start")
        if nature == "duration" and period_start is None:
            raise ValueError("duration facts require period_start")
        if nature == "duration" and period_start != f"{period_end[:4]}-01-01":
            raise ValueError("duration period_start must be the report year's January 1")
        if period_start is not None and period_start > period_end:
            raise ValueError("period_start cannot be after period_end")
        raw_value = data["value"]
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError("value must be a finite number")
        numeric_value = float(raw_value)
        if not math.isfinite(numeric_value):
            raise ValueError("value must be a finite number")
        unit = data["unit"]
        if unit not in FACT_UNITS:
            raise ValueError("invalid unit")
        source_snapshot_id = data["source_snapshot_id"]
        source_field = data["source_field"]
        if not isinstance(source_snapshot_id, str) or not source_snapshot_id:
            raise ValueError("source_snapshot_id is required")
        if not isinstance(source_field, str) or not source_field:
            raise ValueError("source_field is required")
        mapping_version = data["mapping_version"]
        if mapping_version != MAPPING_VERSION:
            raise ValueError("unsupported mapping_version")
        source_updated = data["source_updated_at_utc"]
        if source_updated is not None:
            source_updated = require_aware_utc(source_updated, "source_updated_at_utc")
        announced_at = require_aware_utc(data["announced_at_utc"], "announced_at_utc")
        effective_at = require_aware_utc(data["effective_at_utc"], "effective_at_utc")
        if datetime.fromisoformat(effective_at) < datetime.fromisoformat(announced_at):
            raise ValueError("effective_at_utc cannot be earlier than announced_at_utc")
        if source_updated is not None and datetime.fromisoformat(effective_at) < datetime.fromisoformat(source_updated):
            raise ValueError("effective_at_utc cannot be earlier than source_updated_at_utc")
        return {
            "security_id": security_id,
            "statement": statement,
            "metric_key": metric_key,
            "period_start": period_start,
            "period_end": period_end,
            "period_kind": period_kind,
            "value": numeric_value,
            "unit": unit,
            "nature": nature,
            "announced_at_utc": announced_at,
            "effective_at_utc": effective_at,
            "source_updated_at_utc": source_updated,
            "source_snapshot_id": source_snapshot_id,
            "source_field": source_field,
            "raw_row_hash": _require_sha256(data["raw_row_hash"], "raw_row_hash"),
            "mapping_version": mapping_version,
            "created_at": require_aware_utc(data["created_at"], "created_at"),
        }

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "security_id": self.security_id,
            "statement": self.statement,
            "metric_key": self.metric_key,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "period_kind": self.period_kind,
            "value": self.value,
            "unit": self.unit,
            "nature": self.nature,
            "announced_at_utc": self.announced_at_utc,
            "effective_at_utc": self.effective_at_utc,
            "source_updated_at_utc": self.source_updated_at_utc,
            "source_snapshot_id": self.source_snapshot_id,
            "source_field": self.source_field,
            "raw_row_hash": self.raw_row_hash,
            "mapping_version": self.mapping_version,
            "created_at": self.created_at,
        }


def balance_equation_blockers(
    facts: Iterable[FinancialFact],
) -> frozenset[str]:
    """Evaluate the canonical balance identity with frozen applicability/tolerance."""
    blockers: set[str] = set()
    by_period: dict[tuple[str, str], dict[str, FinancialFact]] = {}
    for fact in facts:
        if fact.metric_key in {"total_assets", "total_liabilities", "total_equity"}:
            by_period.setdefault(
                (fact.security_id, fact.period_end), {}
            )[fact.metric_key] = fact
    for period_facts in by_period.values():
        if set(period_facts) != {
            "total_assets",
            "total_liabilities",
            "total_equity",
        }:
            continue
        units = {item.unit for item in period_facts.values()}
        if len(units) != 1:
            blockers.add("conflicting_fact_units")
            continue
        assets = period_facts["total_assets"].value
        liabilities = period_facts["total_liabilities"].value
        equity = period_facts["total_equity"].value
        tolerance = max(1000.0, 0.001 * abs(assets))
        if abs(assets - liabilities - equity) > tolerance:
            blockers.add("balance_equation_mismatch")
    return frozenset(blockers)
