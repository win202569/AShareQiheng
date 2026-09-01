"""Point-in-time normalization and deterministic financial-fact selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import math
import re
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from ashare_pipeline.feature_contract import (
    CONTRACT_VERSION,
    DIMENSIONS,
    FINANCIAL_PERIODS,
    ConfidenceInputs,
    DimensionInput,
    EvidenceRef,
    FeatureBundle,
    FeatureValue,
    IndustryContext,
    canonical_sha256,
    require_aware_utc,
)
from ashare_pipeline.financial_formulas import (
    DERIVED_FORMULA_VERSION,
    DerivedFormulaResult,
    FormulaFact,
    evaluate_derived_financial,
    positive_cagr,
    symmetric_growth,
)
from ashare_pipeline.financial_schema import (
    DATASET_TO_STATEMENT,
    MAPPING_VERSION,
    FinancialFact,
    balance_equation_blockers,
    classify_period,
    field_rules,
    raw_financial_slot_descriptor,
)
from ashare_pipeline.industry_templates import (
    TEMPLATE_VERSION,
    TemplateDefinition,
    resolve_template,
)
from ashare_pipeline.sources import FetchBatch


SHANGHAI = ZoneInfo("Asia/Shanghai")
FORMULA_VERSION = DERIVED_FORMULA_VERSION
_CALENDAR_START = date(2021, 1, 1)
_CALENDAR_END = date(2026, 9, 7)
_MISSING_UPDATED_AT = datetime.min.replace(tzinfo=timezone.utc)
_EXACT_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SOURCE_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$"
)
_SECURITY_CODE = re.compile(r"^\d{6}$")
_SECUCODE = re.compile(r"^(\d{6})\.(SH|SZ)$")

_REQUIRED_PERIODS = FINANCIAL_PERIODS
_PERIOD_KEY = dict(_REQUIRED_PERIODS)
def _deep_freeze(value: object) -> object:
    if isinstance(value, Mapping):
        frozen = {
            key: _deep_freeze(value[key])
            for key in sorted(value, key=lambda item: (type(item).__name__, repr(item)))
        }
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_deep_freeze(item) for item in value), key=repr))
    return value


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    code: str
    details: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.severity, str) or not self.severity:
            raise ValueError("quality issue severity is required")
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("quality issue code is required")
        if not isinstance(self.details, Mapping):
            raise ValueError("quality issue details must be a mapping")
        object.__setattr__(self, "details", _deep_freeze(dict(self.details)))


@dataclass(frozen=True)
class FactBuildResult:
    facts: tuple[FinancialFact, ...]
    issues: tuple[QualityIssue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "issues", tuple(self.issues))


@dataclass(frozen=True)
class FactSelection:
    facts: tuple[FinancialFact, ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str) or _EXACT_DATE.fullmatch(value) is None:
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def validate_feature_calendar_request(
    request: object,
) -> dict[str, str]:
    """Validate the exact long-calendar semantic request and normalize its keys."""
    if not isinstance(request, Mapping) or set(request) != {"start_date", "end_date"}:
        raise ValueError("trade calendar request must contain exact start_date/end_date keys")
    start = _parse_date(request.get("start_date"), "trade calendar start_date")
    end = _parse_date(request.get("end_date"), "trade calendar end_date")
    if start != _CALENDAR_START or end < _CALENDAR_END:
        raise ValueError("trade calendar does not cover the required range")
    if start > end:
        raise ValueError("trade calendar range is reversed")
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def trading_days_from_batch(batch: FetchBatch) -> tuple[date, ...]:
    """Extract explicit sessions from a verified trade-date batch, failing closed."""
    if (
        not isinstance(batch, FetchBatch)
        or batch.source != "baostock"
        or batch.dataset != "trade_dates"
    ):
        raise ValueError(
            "verified trade calendar must use baostock/trade_dates"
        )
    request = validate_feature_calendar_request(batch.request)
    start = date.fromisoformat(request["start_date"])
    end = date.fromisoformat(request["end_date"])
    if not isinstance(batch.records, list) or not batch.records:
        raise ValueError("trade calendar records must be a non-empty list")

    flags_by_date: dict[date, bool] = {}
    observed_dates: list[date] = []
    for row in batch.records:
        if not isinstance(row, Mapping) or not {"calendar_date", "is_trading_day"}.issubset(row):
            raise ValueError("trade calendar row is missing required fields")
        session_date = _parse_date(row["calendar_date"], "calendar_date")
        if not start <= session_date <= end:
            raise ValueError("trade calendar row falls outside the requested range")
        if session_date in flags_by_date:
            raise ValueError("trade calendar contains a duplicate date")
        raw_flag = row["is_trading_day"]
        if isinstance(raw_flag, bool) or raw_flag not in (0, 1, "0", "1"):
            raise ValueError("is_trading_day must be exactly 0 or 1")
        is_session = raw_flag in (1, "1")
        flags_by_date[session_date] = is_session
        observed_dates.append(session_date)
    expected_count = (end - start).days + 1
    expected_dates = {start + timedelta(days=offset) for offset in range(expected_count)}
    if len(observed_dates) != expected_count or set(observed_dates) != expected_dates:
        raise ValueError("trade calendar must cover every requested date exactly once")
    sessions = tuple(sorted(item for item, is_session in flags_by_date.items() if is_session))
    if not sessions:
        raise ValueError("trade calendar contains no trading sessions")
    return sessions


def _source_time(
    value: object,
    field: str,
    *,
    allow_none: bool = False,
) -> tuple[str | None, date | None]:
    if value is None:
        if allow_none:
            return None, None
        raise ValueError(f"{field} is required")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be an ISO date or timestamp")
    text = value
    try:
        if _EXACT_DATE.fullmatch(text) is not None:
            local_date = date.fromisoformat(text)
            parsed = datetime.combine(local_date, time(23, 59, 59), SHANGHAI)
        elif _SOURCE_TIMESTAMP.fullmatch(text) is not None:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=SHANGHAI)
            local_date = parsed.astimezone(SHANGHAI).date()
        else:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date or timestamp") from exc
    return parsed.astimezone(timezone.utc).isoformat(), local_date


def _security_identity(
    row: Mapping[str, object], expected_security_id: str
) -> tuple[str | None, str | None]:
    raw_code = row.get("SECURITY_CODE")
    raw_secucode = row.get("SECUCODE")
    if raw_code in (None, "") and raw_secucode in (None, ""):
        return None, "statement_security_missing"

    code: str | None = None
    full_id: str | None = None
    if raw_code not in (None, ""):
        if not isinstance(raw_code, str) or _SECURITY_CODE.fullmatch(raw_code) is None:
            return None, "statement_security_invalid"
        code = raw_code
    if raw_secucode not in (None, ""):
        if not isinstance(raw_secucode, str):
            return None, "statement_security_invalid"
        match = _SECUCODE.fullmatch(raw_secucode)
        if match is None:
            return None, "statement_security_invalid"
        secucode_code, exchange = match.groups()
        full_id = f"{exchange}{secucode_code}"
        if code is not None and code != secucode_code:
            return None, "statement_security_mismatch"
    normalized = full_id or f"{expected_security_id[:2]}{code}"
    if normalized != expected_security_id:
        return normalized, "statement_security_mismatch"
    return normalized, None


def _canonicalizable(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _canonicalizable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalizable(item) for item in value]
    return value


def _record_sort_key(row: object) -> str:
    try:
        return canonical_sha256(_canonicalizable(row))
    except (TypeError, ValueError):
        return canonical_sha256(repr(row))


def build_financial_facts(
    batch: FetchBatch,
    *,
    source_snapshot_id: str,
    expected_security_id: str,
    trading_days: Sequence[date],
    created_at_utc: str,
) -> FactBuildResult:
    if batch.dataset not in DATASET_TO_STATEMENT:
        raise ValueError(f"unsupported financial statement dataset: {batch.dataset!r}")
    if not isinstance(source_snapshot_id, str) or not source_snapshot_id:
        raise ValueError("source_snapshot_id is required")
    if (
        not isinstance(expected_security_id, str)
        or len(expected_security_id) != 8
        or expected_security_id[:2] not in {"SH", "SZ"}
        or not expected_security_id[2:].isdigit()
    ):
        raise ValueError("expected_security_id must be an SH/SZ security identifier")
    require_aware_utc(created_at_utc, "created_at_utc")
    if any(not isinstance(item, date) or isinstance(item, datetime) for item in trading_days):
        raise ValueError("trading_days must contain dates")
    sessions = tuple(sorted(set(trading_days)))
    records = tuple(sorted(batch.records, key=_record_sort_key))
    issues: list[QualityIssue] = []

    # Identity failures invalidate the whole table, even when an earlier row was valid.
    periods = {}
    for index, row in enumerate(records):
        if not isinstance(row, Mapping):
            issues.append(QualityIssue("error", "statement_row_invalid", {"row_index": index}))
            return FactBuildResult((), tuple(issues))
        observed_id, identity_error = _security_identity(row, expected_security_id)
        if identity_error == "statement_security_missing":
            issues.append(QualityIssue(
                "error", "statement_security_missing",
                {"expected": expected_security_id, "row_hash": _record_sort_key(row)},
            ))
            return FactBuildResult((), tuple(issues))
        if identity_error is not None:
            issues.append(QualityIssue(
                "error", identity_error,
                {"expected": expected_security_id, "observed_security_id": observed_id},
            ))
            return FactBuildResult((), tuple(issues))
        report_date = row.get("REPORT_DATE")
        try:
            normalized_report_date = _parse_date(report_date, "REPORT_DATE").isoformat()
        except ValueError:
            normalized_report_date = ""
        period = classify_period(normalized_report_date, row.get("REPORT_DATE_NAME"), row.get("REPORT_TYPE"))
        if period is None:
            issues.append(QualityIssue(
                "error", "statement_report_date_invalid",
                {"security_id": expected_security_id, "row_hash": _record_sort_key(row)},
            ))
            return FactBuildResult((), tuple(issues))
        periods[id(row)] = period

    facts: list[FinancialFact] = []
    rules = field_rules(DATASET_TO_STATEMENT[batch.dataset])
    for row in records:
        period = periods[id(row)]
        try:
            notice_utc, notice_local_date = _source_time(row.get("NOTICE_DATE"), "NOTICE_DATE")
            update_utc, update_local_date = _source_time(
                row.get("UPDATE_DATE"), "UPDATE_DATE", allow_none=True
            )
        except ValueError as exc:
            issues.append(QualityIssue(
                "error", "statement_source_date_invalid",
                {"security_id": expected_security_id, "reason": str(exc), "row_hash": _record_sort_key(row)},
            ))
            continue
        version_date = max(
            item for item in (notice_local_date, update_local_date) if item is not None
        )
        next_session = next((item for item in sessions if item > version_date), None)
        if next_session is None:
            issues.append(QualityIssue(
                "error", "trade_calendar_missing_next_session",
                {"version_date": version_date.isoformat()},
            ))
            continue
        effective = datetime.combine(next_session, time(15, 0), SHANGHAI).astimezone(timezone.utc).isoformat()

        extracted: list[tuple[object, str, float]] = []
        for rule in rules:
            selected_field = None
            selected_value = None
            for source_field in rule.source_fields:
                raw_value = row.get(source_field)
                if raw_value is None:
                    continue
                if (
                    isinstance(raw_value, bool)
                    or not isinstance(raw_value, (int, float))
                    or not math.isfinite(float(raw_value))
                ):
                    issues.append(QualityIssue(
                        "error", "invalid_financial_value",
                        {
                            "metric_key": rule.metric_key,
                            "period_end": period.period_end,
                            "security_id": expected_security_id,
                            "source_field": source_field,
                        },
                    ))
                    continue
                selected_field = source_field
                selected_value = float(raw_value)
                break
            if selected_field is not None:
                extracted.append((rule, selected_field, selected_value))
        if not extracted:
            continue
        raw_row_hash = canonical_sha256(_canonicalizable(row))
        for rule, source_field, numeric in extracted:
            facts.append(FinancialFact.create(
                security_id=expected_security_id,
                statement=rule.statement,
                metric_key=rule.metric_key,
                period_start=period.period_start if rule.nature == "duration" else None,
                period_end=period.period_end,
                period_kind=period.period_kind,
                value=numeric,
                unit=rule.unit,
                nature=rule.nature,
                announced_at_utc=notice_utc,
                effective_at_utc=effective,
                source_updated_at_utc=update_utc,
                source_snapshot_id=source_snapshot_id,
                source_field=source_field,
                raw_row_hash=raw_row_hash,
                mapping_version=MAPPING_VERSION,
                created_at=created_at_utc,
            ))
    return FactBuildResult(tuple(sorted(facts, key=lambda item: item.id)), tuple(issues))


def _utc_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp string")
    return datetime.fromisoformat(require_aware_utc(value, field))


def select_visible_facts(
    facts: Iterable[FinancialFact],
    *,
    as_of_utc: str,
    snapshot_fetched_at: Mapping[str, str],
) -> FactSelection:
    as_of = _utc_datetime(as_of_utc, "as_of_utc")
    visible = [
        fact for fact in facts
        if _utc_datetime(fact.effective_at_utc, "effective_at_utc") <= as_of
    ]
    grouped: dict[tuple[str, str, str], list[FinancialFact]] = {}
    for fact in visible:
        grouped.setdefault((fact.security_id, fact.metric_key, fact.period_end), []).append(fact)

    selected: list[FinancialFact] = []
    blockers: set[str] = set()
    for group_key in sorted(grouped):
        ranked: list[tuple[tuple[datetime, datetime, datetime], FinancialFact]] = []
        unrankable = False
        for fact in grouped[group_key]:
            fetched_value = snapshot_fetched_at.get(fact.source_snapshot_id)
            if fetched_value is None:
                unrankable = True
                blockers.add("snapshot_fetch_time_missing")
                continue
            try:
                fetched_at = _utc_datetime(fetched_value, "snapshot_fetched_at")
            except ValueError:
                unrankable = True
                blockers.add("snapshot_fetch_time_invalid")
                continue
            updated_at = (
                _utc_datetime(fact.source_updated_at_utc, "source_updated_at_utc")
                if fact.source_updated_at_utc is not None else _MISSING_UPDATED_AT
            )
            rank = (
                _utc_datetime(fact.announced_at_utc, "announced_at_utc"),
                updated_at,
                fetched_at,
            )
            ranked.append((rank, fact))
        if unrankable or not ranked:
            continue
        top_rank = max(rank for rank, _ in ranked)
        tied = [fact for rank, fact in ranked if rank == top_rank]
        units = {fact.unit for fact in tied}
        values = {fact.value for fact in tied}
        natures = {fact.nature for fact in tied}
        if len(units) > 1:
            blockers.add("conflicting_fact_units")
        if len(values) > 1 or len(natures) > 1:
            blockers.add("conflicting_fact_versions")
        if len(units) > 1 or len(values) > 1 or len(natures) > 1:
            continue
        selected.append(max(tied, key=lambda item: (item.raw_row_hash, item.id)))

    blockers.update(balance_equation_blockers(selected))
    return FactSelection(
        tuple(sorted(selected, key=lambda item: (item.security_id, item.period_end, item.metric_key, item.id))),
        tuple(blockers),
    )


def feature_input_hash(
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    candidate_set_hash: str,
    statement_snapshot_hashes: Mapping[str, str | None],
    trade_calendar_snapshot_hash: str | None,
) -> str:
    """Commit exactly the frozen, versioned dependencies of one feature build."""
    snapshots = {
        dataset: statement_snapshot_hashes.get(dataset)
        for dataset in ("balance_sheet", "profit_sheet", "cash_flow_sheet")
    }
    return canonical_sha256({
        "security_id": security_id,
        "report_period": report_period,
        "as_of_utc": as_of_utc,
        "candidate_set_hash": candidate_set_hash,
        "statement_snapshot_hashes": snapshots,
        "trade_calendar_snapshot_hash": trade_calendar_snapshot_hash,
        "contract_version": CONTRACT_VERSION,
        "mapping_version": MAPPING_VERSION,
        "template_version": TEMPLATE_VERSION,
        "formula_version": FORMULA_VERSION,
    })


def _evidence(fact: FinancialFact) -> EvidenceRef:
    return EvidenceRef(
        financial_fact_id=fact.id,
        source_snapshot_id=fact.source_snapshot_id,
        source_field=fact.source_field,
        raw_row_hash=fact.raw_row_hash,
        announced_at_utc=fact.announced_at_utc,
        effective_at_utc=fact.effective_at_utc,
    )


def _evidence_tuple(facts: Iterable[FinancialFact]) -> tuple[EvidenceRef, ...]:
    by_content = {
        (
            fact.id,
            fact.source_snapshot_id,
            fact.source_field,
            fact.raw_row_hash,
            fact.announced_at_utc,
            fact.effective_at_utc,
        ): _evidence(fact)
        for fact in facts
    }
    return tuple(by_content[key] for key in sorted(by_content))


def _observed_value(metric_key: str, period_key: str, fact: FinancialFact) -> FeatureValue:
    descriptor = raw_financial_slot_descriptor(metric_key)
    if (
        fact.metric_key != descriptor.metric_key
        or fact.mapping_version != descriptor.formula_version
        or fact.unit != descriptor.unit
        or fact.source_field not in descriptor.source_fields
    ):
        raise ValueError("financial fact does not match its canonical raw slot")
    return FeatureValue(
        key=descriptor.canonical_key(period_key),
        value=fact.value,
        unit=fact.unit,
        period_key=period_key,
        status=descriptor.allowed_statuses[0],
        formula_version=descriptor.formula_version,
        evidence=(_evidence(fact),),
        missing_reason=None,
    )


def _missing_value(
    dimension: str,
    metric_key: str,
    period_key: str,
    unit: str,
    reason: str,
) -> FeatureValue:
    return FeatureValue(
        key=f"{dimension.lower()}.{metric_key}.{period_key}",
        value=None,
        unit=unit,
        period_key=period_key,
        status="missing",
        formula_version=FORMULA_VERSION,
        evidence=(),
        missing_reason=reason,
    )


def _not_applicable_value(
    dimension: str,
    metric_key: str,
    period_key: str,
    unit: str,
    reason: str,
) -> FeatureValue:
    return FeatureValue(
        key=f"{dimension.lower()}.{metric_key}.{period_key}",
        value=None,
        unit=unit,
        period_key=period_key,
        status="not_applicable",
        formula_version=FORMULA_VERSION,
        evidence=(),
        missing_reason=reason,
    )


def _formula_value(
    result: DerivedFormulaResult,
    facts_by_id: Mapping[str, FinancialFact],
) -> FeatureValue:
    spec = result.spec
    if result.status == "not_applicable":
        return _not_applicable_value(
            spec.dimension,
            spec.metric_key,
            spec.period_key,
            spec.unit,
            result.missing_reason or spec.missing_reason,
        )
    if result.status == "missing":
        return _missing_value(
            spec.dimension,
            spec.metric_key,
            spec.period_key,
            spec.unit,
            result.missing_reason or spec.missing_reason,
        )
    evidence_facts = tuple(facts_by_id[identity] for identity in result.operand_ids)
    return FeatureValue(
        key=spec.canonical_key,
        value=result.value,
        unit=spec.unit,
        period_key=spec.period_key,
        status="derived",
        formula_version=spec.formula_version,
        evidence=_evidence_tuple(evidence_facts),
        missing_reason=None,
    )


def _dimension_status(values: Sequence[FeatureValue], *, blocked: bool) -> str:
    if blocked:
        return "blocked"
    if not values:
        return "not_applicable"
    states = {item.status for item in values}
    applicable_states = states - {"not_applicable"}
    if not applicable_states:
        return "not_applicable"
    if applicable_states <= {"observed", "derived"}:
        return "input_ready"
    if applicable_states == {"missing"}:
        return "missing"
    return "partial"


def assemble_bundle_from_registered_slots(
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    candidate_set_hash: str,
    input_hash: str,
    source_industry_name: str,
    template: TemplateDefinition,
    facts: Sequence[FinancialFact],
    financial_blockers: Sequence[str],
    blockers: Sequence[str],
) -> FeatureBundle:
    facts_by_key: dict[tuple[str, str], FinancialFact] = {}
    for fact in facts:
        if fact.period_end in _PERIOD_KEY:
            facts_by_key[(fact.metric_key, fact.period_end)] = fact

    dimensions: dict[str, list[FeatureValue]] = {key: [] for key in DIMENSIONS}
    if template.financial_slots:
        for metric_key in template.financial_slots:
            descriptor = raw_financial_slot_descriptor(metric_key)
            dimension = descriptor.dimension
            for period_end, period_key in _REQUIRED_PERIODS:
                fact = facts_by_key.get((metric_key, period_end))
                if fact is None:
                    dimensions[dimension].append(_missing_value(
                        dimension, metric_key, period_key,
                        descriptor.unit,
                        f"financial_fact_missing:{metric_key}",
                    ))
                else:
                    dimensions[dimension].append(_observed_value(metric_key, period_key, fact))
        formula_inputs = {
            slot: FormulaFact(
                fact.metric_key,
                fact.period_end,
                fact.value,
                fact.unit,
                fact.id,
            )
            for slot, fact in facts_by_key.items()
        }
        facts_by_id = {fact.id: fact for fact in facts_by_key.values()}
        for result in evaluate_derived_financial(formula_inputs):
            dimensions[result.spec.dimension].append(
                _formula_value(result, facts_by_id)
            )

    applicable_values = [
        value
        for dimension in ("G", "M", "EQ", "FS", "CA")
        for value in dimensions[dimension]
        if value.status != "not_applicable"
    ]
    complete_count = sum(
        value.status in {"observed", "derived"} for value in applicable_values
    )
    financial_coverage = complete_count / len(applicable_values) if applicable_values else 0.0
    financial_blocker_set = set(financial_blockers)
    complete_periods = {fact.period_end for fact in facts} >= set(_PERIOD_KEY)
    if not applicable_values or financial_blocker_set:
        financial_status = "blocked"
    elif financial_coverage == 1.0 and complete_periods and template.template_id != "unclassified":
        financial_status = "financial_ready"
    else:
        financial_status = "partial"

    blocked_dimensions = bool(financial_blocker_set)
    dimension_inputs = {
        dimension: (
            DimensionInput("missing", ())
            if dimension in {"V", "T"}
            else DimensionInput(
                _dimension_status(dimensions[dimension], blocked=blocked_dimensions),
                tuple(sorted(dimensions[dimension], key=lambda item: (item.key, item.period_key))),
            )
        )
        for dimension in DIMENSIONS
    }

    date_precision_counts = {"timestamp": 0, "date_only": 0}
    for fact in facts:
        local = datetime.fromisoformat(fact.announced_at_utc).astimezone(SHANGHAI)
        precision = "date_only" if local.time() == time(23, 59, 59) else "timestamp"
        date_precision_counts[precision] += 1
    history_years_present = len({
        fact.period_end[:4] for fact in facts if fact.period_kind == "FY"
    })
    mapping_consistent = (
        all(fact.mapping_version == MAPPING_VERSION for fact in facts)
        and not ({
            "conflicting_fact_units",
            "conflicting_fact_versions",
            "financial_fact_mapping_version_mismatch",
        } & financial_blocker_set)
    )
    return FeatureBundle(
        schema_version=1,
        contract_version=CONTRACT_VERSION,
        security_id=security_id,
        report_period=report_period,
        as_of_utc=as_of_utc,
        candidate_set_hash=candidate_set_hash,
        industry=IndustryContext(
            source="eastmoney-provisional",
            code=None,
            name=source_industry_name,
            template_id=template.template_id,
            template_version=TEMPLATE_VERSION,
            formal_industry_ready=False,
        ),
        input_hash=input_hash,
        financial_status=financial_status,
        financial_coverage=financial_coverage,
        confidence_inputs=ConfidenceInputs(
            data_completeness_ratio=financial_coverage,
            date_precision_counts=date_precision_counts,
            history_years_present=history_years_present,
            mapping_consistent=mapping_consistent,
            formal_confidence=None,
        ),
        dimension_inputs=dimension_inputs,
        blockers=tuple(sorted(set(blockers))),
        is_formal_score_ready=False,
    )


def build_feature_bundle(
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    candidate_set_hash: str,
    source_industry_name: str,
    facts: Iterable[FinancialFact],
    fact_blockers: Sequence[str],
    statement_snapshot_hashes: Mapping[str, str | None],
    trade_calendar_snapshot_hash: str | None,
    reported_target_period: bool,
) -> FeatureBundle:
    template = resolve_template(source_industry_name)
    financial_blockers = set(fact_blockers)
    formal_blockers = {"formal_industry_mapping_missing"}
    supplied_facts = tuple(facts)
    if any(fact.security_id != security_id for fact in supplied_facts):
        financial_blockers.add("financial_fact_security_mismatch")
    if any(fact.mapping_version != MAPPING_VERSION for fact in supplied_facts):
        financial_blockers.add("financial_fact_mapping_version_mismatch")
    selected = tuple(sorted(
        (
            fact for fact in supplied_facts
            if fact.security_id == security_id and fact.mapping_version == MAPPING_VERSION
        ),
        key=lambda item: (item.metric_key, item.period_end, item.effective_at_utc, item.id),
    ))
    financial_blockers.update(balance_equation_blockers(selected))
    if template.template_id == "unclassified":
        financial_blockers.add("industry_template_unclassified")
    if (
        template.specialized_inputs_required
        and template.template_id != "unclassified"
    ):
        financial_blockers.add("specialized_financial_inputs_missing")
    if trade_calendar_snapshot_hash is None:
        financial_blockers.add("trade_calendar_missing")
    missing_statement = any(
        statement_snapshot_hashes.get(dataset) is None
        for dataset in ("balance_sheet", "profit_sheet", "cash_flow_sheet")
    )
    target_statements = {
        fact.statement
        for fact in supplied_facts
        if fact.security_id == security_id and fact.period_end == report_period
    }
    target_period_incomplete = target_statements != {"balance", "income", "cash_flow"}
    cutoff = datetime.fromisoformat("2026-08-31T23:59:59+08:00")
    as_of = datetime.fromisoformat(require_aware_utc(as_of_utc, "as_of_utc"))
    if (
        reported_target_period
        and (missing_statement or target_period_incomplete)
        and as_of > cutoff
    ):
        financial_blockers.add("reported_but_statement_missing")
    input_hash = feature_input_hash(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=as_of_utc,
        candidate_set_hash=candidate_set_hash,
        statement_snapshot_hashes=statement_snapshot_hashes,
        trade_calendar_snapshot_hash=trade_calendar_snapshot_hash,
    )
    return assemble_bundle_from_registered_slots(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=as_of_utc,
        candidate_set_hash=candidate_set_hash,
        input_hash=input_hash,
        source_industry_name=source_industry_name,
        template=template,
        facts=selected,
        financial_blockers=tuple(sorted(financial_blockers)),
        blockers=tuple(sorted(financial_blockers | formal_blockers)),
    )
