"""Pure curation and disclosure-data quality checks for the A-share pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
CUTOFF_CN = datetime(2026, 8, 31, 23, 59, 59, tzinfo=SHANGHAI)
CORE_FIELDS = (
    "revenue_yoy",
    "net_profit_yoy",
    "roe",
    "gross_margin",
    "operating_cash_flow_per_share",
)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def _normal_json_value(value: Any) -> Any:
    if _is_missing(value):
        return None
    if isinstance(value, dict):
        return {str(key): _normal_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normal_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _normal_json_value(value.item())
        except (TypeError, ValueError):
            pass
    return value


def _canonical_hash(record: dict) -> str:
    payload = json.dumps(
        _normal_json_value(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _code6(value: object) -> str | None:
    if _is_missing(value):
        return None
    if isinstance(value, int):
        return f"{value:06d}" if 0 <= value <= 999999 else None
    if isinstance(value, float):
        return f"{int(value):06d}" if value.is_integer() and 0 <= value <= 999999 else None
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    match = re.fullmatch(r"(?:(?:sh|sz)\.)?(\d{1,6})", text, flags=re.IGNORECASE)
    return match.group(1).zfill(6) if match else None


def _number(value: object) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.endswith("%"):
            text = text[:-1]
        value = text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _first(record: dict, *keys: str) -> object:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _date_text(value: object) -> str | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if text.endswith(" 00:00:00"):
        return text[:10]
    return text


def _announcement_instant(value: object, *, end_of_day: bool = False) -> datetime | None:
    text = _date_text(value)
    if text is None:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        if "T" not in normalized and " " not in normalized:
            parsed = datetime.combine(parsed.date(), time.max if end_of_day else time.min)
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI)


def curate_universe(records: list[dict]) -> tuple[list[dict], dict]:
    """Keep only active Shanghai/Shenzhen A-share equities and add canonical IDs."""

    kept: list[dict] = []
    excluded_cdr_689_count = 0
    for raw in records:
        code = str(raw.get("code", "")).strip().lower()
        if str(raw.get("type", "")) != "1" or str(raw.get("status", "")) != "1":
            continue
        if re.fullmatch(r"sh\.689\d{3}", code):
            excluded_cdr_689_count += 1
            continue
        if not (re.fullmatch(r"sh\.6\d{5}", code) or re.fullmatch(r"sz\.[03]\d{5}", code)):
            continue
        exchange = "SH" if code.startswith("sh.") else "SZ"
        code6 = code.split(".", 1)[1]
        name = str(_first(raw, "code_name", "name", "证券简称") or "").strip()
        if exchange == "SH" and code6.startswith("688"):
            board = "科创板"
        elif exchange == "SZ" and code6.startswith(("300", "301")):
            board = "创业板"
        else:
            board = "主板"
        curated = dict(raw)
        curated.update(
            {
                "security_id": f"{exchange}{code6}",
                "code6": code6,
                "name": name,
                "listing_date": _date_text(_first(raw, "ipoDate", "listing_date")),
                "exchange": exchange,
                "board": board,
                "risk_tags": ["ST"] if "ST" in name.upper() else [],
            }
        )
        kept.append(_normal_json_value(curated))
    kept.sort(key=lambda row: row["security_id"])
    return kept, {
        "input_count": len(records),
        "universe_count": len(kept),
        "excluded_count": len(records) - len(kept),
        "excluded_cdr_689_count": excluded_cdr_689_count,
        "st_count": sum("ST" in row["risk_tags"] for row in kept),
    }


_PERFORMANCE_FIELDS = {
    "name": ("股票简称", "证券简称", "name"),
    "eps": ("每股收益", "eps"),
    "revenue": ("营业总收入-营业总收入", "营业总收入", "revenue"),
    "revenue_yoy": ("营业总收入-同比增长", "营业总收入同比增长", "revenue_yoy"),
    "net_profit": ("净利润-净利润", "净利润", "net_profit"),
    "net_profit_yoy": ("净利润-同比增长", "净利润同比增长", "net_profit_yoy"),
    "book_value_per_share": ("每股净资产", "book_value_per_share"),
    "roe": ("净资产收益率", "roe"),
    "operating_cash_flow_per_share": ("每股经营现金流量", "operating_cash_flow_per_share"),
    "gross_margin": ("销售毛利率", "gross_margin"),
    "industry": ("所处行业", "行业", "industry"),
    "announcement_date": ("最新公告日期", "公告日期", "announcement_date"),
}


def curate_performance(
    records: list[dict], universe: list[dict], cutoff_cn: str | None = None
) -> tuple[list[dict], dict]:
    """Join, normalize, and deterministically deduplicate the bulk performance report."""

    universe_by_code = {str(row["code6"]): row for row in universe}
    candidates: dict[str, list[dict]] = {}
    outside_count = 0
    post_cutoff_rows = 0
    post_cutoff_codes: set[str] = set()
    missing_announcement_rows = 0
    unparseable_announcement_rows = 0
    cutoff: datetime | None = None
    if cutoff_cn is not None:
        normalized_cutoff = cutoff_cn[:-1] + "+00:00" if cutoff_cn.endswith("Z") else cutoff_cn
        cutoff = datetime.fromisoformat(normalized_cutoff)
        if cutoff.tzinfo is None:
            raise ValueError("cutoff_cn must include a timezone offset")
        cutoff = cutoff.astimezone(SHANGHAI)
    for raw in records:
        code = _code6(_first(raw, "股票代码", "代码", "code6", "code"))
        if code is None or code not in universe_by_code:
            outside_count += 1
            continue
        normalized = dict(raw)
        canonical: dict[str, object] = {}
        for target, source_keys in _PERFORMANCE_FIELDS.items():
            value = _first(raw, *source_keys)
            if target in {"name", "industry"}:
                canonical[target] = None if _is_missing(value) else str(value).strip()
            elif target == "announcement_date":
                canonical[target] = _date_text(value)
            else:
                canonical[target] = _number(value)
        universe_row = universe_by_code[code]
        normalized.update(canonical)
        normalized.update({"code6": code, "security_id": universe_row["security_id"]})
        normalized = _normal_json_value(normalized)
        announcement_text = normalized.get("announcement_date")
        if _is_missing(announcement_text):
            missing_announcement_rows += 1
        else:
            date_only = bool(
                isinstance(announcement_text, str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", announcement_text)
            )
            announcement = _announcement_instant(announcement_text, end_of_day=date_only)
            if announcement is None:
                unparseable_announcement_rows += 1
            elif cutoff is not None and (
                announcement.date() > cutoff.date()
                or (not date_only and announcement > cutoff)
            ):
                post_cutoff_rows += 1
                post_cutoff_codes.add(code)
                continue
        candidates.setdefault(code, []).append(normalized)

    result: list[dict] = []
    duplicate_security_count = 0
    duplicate_row_count = 0
    for code, rows in candidates.items():
        if len(rows) > 1:
            duplicate_security_count += 1
            duplicate_row_count += len(rows) - 1
        rows.sort(
            key=lambda row: (
                -(_announcement_instant(row.get("announcement_date")) or datetime.min.replace(tzinfo=SHANGHAI)).timestamp(),
                _canonical_hash(row),
            )
        )
        result.append(rows[0])
    result.sort(key=lambda row: row["security_id"])

    available = sum(not _is_missing(row.get(field)) for row in result for field in CORE_FIELDS)
    denominator = len(result) * len(CORE_FIELDS)
    dates = [row.get("announcement_date") for row in result if row.get("announcement_date")]
    return result, {
        "input_count": len(records),
        "disclosed_unique_count": len(result),
        "outside_universe_rows": outside_count,
        "duplicate_security_count": duplicate_security_count,
        "duplicate_row_count": duplicate_row_count,
        "core_field_completeness": available / denominator if denominator else 0.0,
        "latest_announcement_date": max(dates, default=None),
        "cutoff_cn": cutoff.isoformat() if cutoff is not None else None,
        "post_cutoff_observation_rows": post_cutoff_rows,
        "post_cutoff_security_count": len(post_cutoff_codes),
        "announcement_timestamp_missing_rows": missing_announcement_rows,
        "announcement_timestamp_unparseable_rows": unparseable_announcement_rows,
    }


def quality_gate(universe: list[dict], performance: list[dict], as_of_cn: str) -> dict:
    """Evaluate disclosure-data checks; market evidence is composed by the orchestrator."""

    normalized = as_of_cn[:-1] + "+00:00" if as_of_cn.endswith("Z") else as_of_cn
    as_of = datetime.fromisoformat(normalized)
    if as_of.tzinfo is None:
        raise ValueError("as_of_cn must include a timezone offset")
    as_of = as_of.astimezone(SHANGHAI)

    security_ids = [str(row.get("security_id", "")) for row in performance]
    unique_ids = set(security_ids)
    duplicate_count = len(security_ids) - len(unique_ids)
    universe_ids = [str(row.get("security_id", "")) for row in universe]
    unique_universe_ids = set(universe_ids)
    universe_duplicate_count = len(universe_ids) - len(unique_universe_ids)
    available = sum(not _is_missing(row.get(field)) for row in performance for field in CORE_FIELDS)
    denominator = len(performance) * len(CORE_FIELDS)
    completeness = available / denominator if denominator else 0.0

    future = 0
    missing_announcement_count = 0
    unparseable_announcement_count = 0
    parsed_dates: list[datetime] = []
    for row in performance:
        raw_announcement = row.get("announcement_date")
        announcement_text = _date_text(raw_announcement)
        if announcement_text is None:
            missing_announcement_count += 1
            continue
        date_only = bool(announcement_text and re.fullmatch(r"\d{4}-\d{2}-\d{2}", announcement_text))
        announcement = _announcement_instant(raw_announcement, end_of_day=date_only)
        if announcement is None:
            unparseable_announcement_count += 1
            continue
        parsed_dates.append(announcement)
        if announcement.date() > as_of.date() or (not date_only and announcement > as_of):
            future += 1

    disclosed_universe_ids = unique_ids & unique_universe_ids
    outside_performance_ids = unique_ids - unique_universe_ids
    eligible_universe_count = len(unique_universe_ids)
    disclosure_coverage = (
        len(disclosed_universe_ids) / eligible_universe_count if eligible_universe_count else 0.0
    )
    data_checks = (
        bool(universe)
        and bool(performance)
        and completeness >= 0.95
        and disclosure_coverage >= 0.95
        and duplicate_count == 0
        and universe_duplicate_count == 0
        and not outside_performance_ids
        and missing_announcement_count == 0
        and unparseable_announcement_count == 0
        and future == 0
    )
    after_cutoff = as_of > CUTOFF_CN
    if not after_cutoff:
        status = "partial"
    elif data_checks:
        status = "data_ready"
    else:
        status = "failed"
    return {
        "status": status,
        "cutoff_passed": after_cutoff,
        "universe_count": len(universe),
        "eligible_universe_count": eligible_universe_count,
        "disclosure_exclusion_count": 0,
        "disclosure_exclusions": [],
        "disclosed_unique_count": len(disclosed_universe_ids),
        "disclosure_coverage_rate": disclosure_coverage,
        "coverage_rate": disclosure_coverage,
        "outside_performance_security_count": len(outside_performance_ids),
        "duplicate_security_count": duplicate_count,
        "universe_duplicate_security_count": universe_duplicate_count,
        "core_field_completeness": completeness,
        "latest_announcement_date": max((item.isoformat() for item in parsed_dates), default=None),
        "announcement_timestamp_missing_count": missing_announcement_count,
        "announcement_timestamp_unparseable_count": unparseable_announcement_count,
        "announcement_timestamp_valid_rate": (
            len(parsed_dates) / len(performance) if performance else 0.0
        ),
        "future_announcement_count": future,
        "data_quality_passed": after_cutoff and data_checks,
        "market_evidence_required": True,
    }
