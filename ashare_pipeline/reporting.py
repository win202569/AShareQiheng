"""Build a bounded, source-backed progress report artifact.

The generator deliberately reports engineering readiness rather than security
recommendations.  It accepts reviewed aggregate inputs and never copies raw
pipeline payloads into the reader-facing snapshot.
"""

from __future__ import annotations

import copy
import math
import re
import sqlite3
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping


REPORT_TITLE = "A股2026中报评估方法与增量采集进度"
MAX_SOURCE_ROWS = 25

_SECRET_NAME = r"(?:api[_-]?key|access[_-]?token|token|password|passwd|secret)"
_JSON_SECRET_PATTERN = re.compile(
    rf"(?i)([\"']?{_SECRET_NAME}[\"']?\s*:\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^,}\]\s]+)"
)
_SECRET_PATTERN = re.compile(rf"(?i)\b{_SECRET_NAME}\b\s*[:=]\s*[^\s,;]+")
_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*(?:(?:bearer|basic)\s+)?[^\s,;]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+")
_BASIC_PATTERN = re.compile(r"(?i)\bbasic\s+[A-Za-z0-9._~+/=-]+")
_CREDENTIAL_URL_PATTERN = re.compile(r"(?i)https?://[^\s/:@]+:[^\s/@]+@[^\s]+")
_PUBLIC_URL_PATTERN = re.compile(r"(?i)https?://[^\s,;\]\[(){}<>\"']+")
_WINDOWS_PATH_PATTERN = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/][^\s,;\]\[(){}<>\"']+")
_UNC_PATH_PATTERN = re.compile(r"(?<![\\/])(?:\\\\|//)[^\\/\s]+[\\/][^\s,;\]\[(){}<>\"']+")
_POSIX_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9:])/(?!/)[^\s,;\]\[(){}<>\"']+")


def _validated_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("generated_at must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("generated_at must be a timezone-aware ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("generated_at must include a timezone offset")
    return value


def _safe_relative_path(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty relative path")
    normalized = value.strip().replace("\\", "/")
    if PurePosixPath(normalized).is_absolute() or PureWindowsPath(value).is_absolute():
        raise ValueError(f"{field} must not be an absolute path")
    if ".." in PurePosixPath(normalized).parts or ":" in normalized:
        raise ValueError(f"{field} must be a safe relative path")
    return str(PurePosixPath(normalized))


def _clean_text(value: Any, fallback: str = "待采集") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    text = _CREDENTIAL_URL_PATTERN.sub("[已隐藏凭证URL]", text)
    text = _AUTHORIZATION_PATTERN.sub("[已隐藏凭证]", text)
    text = _BEARER_PATTERN.sub("[已隐藏凭证]", text)
    text = _BASIC_PATTERN.sub("[已隐藏凭证]", text)
    text = _JSON_SECRET_PATTERN.sub(r'\1"[已隐藏凭证]"', text)
    text = _SECRET_PATTERN.sub("[已隐藏凭证]", text)
    public_urls: list[str] = []

    def protect_public_url(match: re.Match[str]) -> str:
        public_urls.append(match.group(0))
        return f"__PUBLIC_URL_{len(public_urls) - 1}__"

    text = _PUBLIC_URL_PATTERN.sub(protect_public_url, text)
    text = _WINDOWS_PATH_PATTERN.sub("[已隐藏本机路径]", text)
    text = _UNC_PATH_PATTERN.sub("[已隐藏本机路径]", text)
    text = _POSIX_PATH_PATTERN.sub("[已隐藏本机路径]", text)
    for index, public_url in enumerate(public_urls):
        text = text.replace(f"__PUBLIC_URL_{index}__", public_url)
    return text[:240]


def _sanitize_dynamic(value: Any) -> Any:
    """Recursively redact known sensitive string patterns in dynamic inputs."""

    if isinstance(value, Mapping):
        return {key: _sanitize_dynamic(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_dynamic(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_dynamic(item) for item in value)
    if isinstance(value, str):
        return _clean_text(value, "")
    return value


def _get_path(mapping: Mapping[str, Any] | None, dotted_path: str) -> Any:
    current: Any = mapping
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _first(mapping: Mapping[str, Any] | None, *paths: str) -> Any:
    for path in paths:
        value = _get_path(mapping, path)
        if value is not None:
            return value
    return None


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _number(value: Any, *, non_negative: bool = True) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)) or (non_negative and value < 0):
        return None
    return int(value) if float(value).is_integer() else float(value)


def _count_from_mapping(value: Any) -> int | float | None:
    direct = _number(value)
    if direct is not None:
        return direct
    if not isinstance(value, Mapping):
        return None
    values = [_number(item) for item in value.values()]
    if not values or any(item is None for item in values):
        return None
    total = sum(values)
    return int(total) if float(total).is_integer() else float(total)


def _coverage(value: Any) -> float | None:
    numeric = _number(value)
    if numeric is None:
        return None
    result = float(numeric)
    if 0 <= result <= 1:
        return result
    if 1 < result <= 100:
        return result / 100
    return None


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError("reviewed dataset contains a non-finite number")
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _materialize_reviewed_rows(
    rows: list[dict[str, Any]], columns: tuple[str, ...]
) -> tuple[list[dict[str, Any]], str]:
    """Materialize bounded rows through runnable SQLite for exact provenance."""

    if not rows:
        raise ValueError("reviewed datasets must contain at least one row")
    for column in columns:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", column):
            raise ValueError(f"unsafe reviewed dataset column: {column}")
    statements = []
    for row in rows:
        expressions = [f'{_sql_literal(row.get(column))} AS "{column}"' for column in columns]
        statements.append("SELECT " + ", ".join(expressions))
    sql = "\nUNION ALL\n".join(statements)
    with sqlite3.connect(":memory:") as connection:
        cursor = connection.execute(sql)
        field_names = [description[0] for description in cursor.description]
        materialized = [dict(zip(field_names, values, strict=True)) for values in cursor.fetchall()]
    return materialized, sql


def _bool_value(mapping: Mapping[str, Any] | None, *paths: str) -> bool | None:
    value = _first(mapping, *paths)
    return value if isinstance(value, bool) else None


def _reviewed_batch_summary(pipeline_status: Mapping[str, Any]) -> tuple[int | None, int | float | None]:
    batches = _first(pipeline_status, "source_batches")
    if not isinstance(batches, list):
        return None, None
    reviewed_counts: list[int | float] = []
    for batch in batches:
        if not isinstance(batch, Mapping):
            continue
        value = _number(_first(batch, "rows", "row_count", "record_count"))
        if value is not None:
            reviewed_counts.append(value)
    if not reviewed_counts:
        return None, None
    total = sum(reviewed_counts)
    return len(reviewed_counts), int(total) if float(total).is_integer() else float(total)


def _candidate_pairs(value: Any) -> list[tuple[str | None, Any]]:
    if isinstance(value, list):
        return [(None, item) for item in value]
    if isinstance(value, Mapping):
        return [(str(key), item) for key, item in value.items()]
    return []


def _infer_source(dataset: str, explicit: Any, parent: Any = None) -> str:
    if explicit is not None:
        return _clean_text(explicit, "待确认")
    if parent is not None:
        return _clean_text(parent, "待确认")
    key = dataset.lower()
    if any(token in key for token in ("security_master", "trade_date", "daily", "market", "baostock")):
        return "BaoStock"
    if any(
        token in key
        for token in (
            "performance",
            "disclosure",
            "balance",
            "profit",
            "cash_flow",
            "cashflow",
            "cninfo",
            "spot",
            "akshare",
        )
    ):
        return "AKShare"
    return "待确认"


def _source_row_priority(row: Mapping[str, Any]) -> tuple[int, str, str]:
    text = f"{row.get('status', '')} {row.get('note', '')}".lower()
    if any(token in text for token in ("blocked", "circuit", "terminal", "retry", "fail", "error", "失败", "阻断")):
        priority = 0
    elif any(token in text for token in ("pending", "running", "待", "进行")):
        priority = 1
    else:
        priority = 2
    return priority, str(row.get("dataset", "")), str(row.get("source", ""))


def _source_rows(
    pilot_status: Mapping[str, Any] | None,
    pipeline_status: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[tuple[str | None, Any, Any]] = []
    if isinstance(pilot_status, Mapping):
        raw = _first(pilot_status, "datasets", "source_status", "batches")
        candidates.extend(
            (fallback_name, item, _first(pilot_status, "source", "provider"))
            for fallback_name, item in _candidate_pairs(raw)
        )
    candidates.extend(
        (fallback_name, item, None)
        for fallback_name, item in _candidate_pairs(_first(pipeline_status, "source_batches"))
    )
    for fallback_name, item in _candidate_pairs(_first(pipeline_status, "source_errors")):
        if isinstance(item, Mapping):
            error_item = dict(item)
        else:
            error_item = {"error": item}
        error_item.setdefault("dataset", fallback_name or "source_error")
        error_item.setdefault("status", error_item.get("classification") or "error")
        error_item.setdefault("note", error_item.get("error") or "数据源错误")
        candidates.append((fallback_name, error_item, None))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for fallback_name, item, parent_source in candidates:
        if not isinstance(item, Mapping):
            item = {"status": item}
        dataset_name = _clean_text(
            _coalesce(_first(item, "dataset", "name", "endpoint", "kind"), fallback_name),
            "未命名数据集",
        )
        row_count = _number(_first(item, "row_count", "rows", "count", "record_count"))
        status_value = _first(item, "status", "state", "classification")
        if status_value is None and row_count is not None:
            status_value = "已采集"
        note_value = _coalesce(_first(item, "note", "message", "error"), "无补充说明")
        row = {
            "dataset": dataset_name,
            "source": _infer_source(dataset_name, _first(item, "source", "provider"), parent_source),
            "status": _clean_text(status_value, "待采集"),
            "row_count": row_count,
            "as_of": _clean_text(_first(item, "as_of", "fetched_at", "date"), "待采集"),
            "note": _clean_text(note_value, "无补充说明"),
        }
        identity = tuple(row.values())
        if identity not in seen:
            rows.append(row)
            seen.add(identity)

    reviewed_row_count = len(rows)
    rows.sort(key=_source_row_priority)
    for row in rows:
        row["priority"] = _source_row_priority(row)[0]
    shown = rows[:MAX_SOURCE_ROWS]
    meta = {
        "reviewed_row_count": reviewed_row_count,
        "shown_row_count": len(shown),
        "truncated": reviewed_row_count > MAX_SOURCE_ROWS,
        "selection_rule": "失败/阻断/可重试优先，其余按数据集和来源稳定排序",
    }
    if shown:
        return shown, meta
    return [
        {
            "dataset": "尚无已审阅数据集",
            "source": "待确认",
            "status": "待采集",
            "row_count": None,
            "as_of": "待采集",
            "note": "未发现可展示的聚合数据集状态；缺失值不填为0。",
            "priority": 9,
        }
    ], meta


def _operational_rows(
    pipeline_status: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fallback, item in _candidate_pairs(_first(pipeline_status, "source_errors")):
        item = item if isinstance(item, Mapping) else {"error": item}
        source = _clean_text(_first(item, "source"), "待确认")
        target = _clean_text(_coalesce(_first(item, "dataset"), fallback), "未知数据集")
        rows.append(
            {
                "priority": 1,
                "category": "数据源错误",
                "subject": f"{source} / {target}",
                "status": _clean_text(_first(item, "classification", "status"), "error"),
                "detail": _clean_text(_first(item, "error", "message"), "未提供错误详情"),
                "next_action": "按错误分类重试、熔断或人工核验",
            }
        )
    for fallback, item in _candidate_pairs(_first(pipeline_status, "circuit_breakers")):
        subject = item if not isinstance(item, Mapping) else _coalesce(_first(item, "source", "name"), fallback)
        rows.append(
            {
                "priority": 1,
                "category": "熔断器",
                "subject": _clean_text(subject, "未知来源"),
                "status": "blocked",
                "detail": "该来源在本轮后续请求中保持熔断",
                "next_action": "等待下轮或人工确认访问恢复",
            }
        )
    for fallback, item in _candidate_pairs(_first(pipeline_status, "blocked_reasons")):
        detail = item if not isinstance(item, Mapping) else _coalesce(_first(item, "reason", "message"), fallback)
        rows.append(
            {
                "priority": 0,
                "category": "发布阻断",
                "subject": "正式发布",
                "status": "blocked",
                "detail": _clean_text(detail, "未提供阻断原因"),
                "next_action": "解决阻断并重新运行质量闸门",
            }
        )
    prefilter = _first(pipeline_status, "curated.prefilter")
    if isinstance(prefilter, Mapping) and prefilter:
        count = _number(_first(prefilter, "candidate_count", "selected_count", "count"))
        reason = _clean_text(_first(prefilter, "reason"), "仅供深抓排序，不是V2正式总分")
        rows.append(
            {
                "priority": 3,
                "category": "预筛队列",
                "subject": "深抓候选",
                "status": "非正式评分",
                "detail": f"候选数={count if count is not None else '待采集'}；{reason}",
                "next_action": "仅用于安排完整三表和正文核验",
            }
        )
    for fallback, item in _candidate_pairs(_first(pipeline_status, "next_actions")):
        detail = item if not isinstance(item, Mapping) else _coalesce(_first(item, "action", "message"), fallback)
        rows.append(
            {
                "priority": 2,
                "category": "下一动作",
                "subject": "管线",
                "status": "planned",
                "detail": _clean_text(detail, "待确认"),
                "next_action": _clean_text(detail, "待确认"),
            }
        )
    reviewed_row_count = len(rows)
    rows.sort(key=lambda row: (row["priority"], row["category"], row["subject"], row["detail"]))
    shown = rows[:MAX_SOURCE_ROWS]
    meta = {
        "reviewed_row_count": reviewed_row_count,
        "shown_row_count": len(shown),
        "truncated": reviewed_row_count > MAX_SOURCE_ROWS,
        "selection_rule": "发布阻断优先，其次来源错误/熔断，再次下一动作与非正式预筛",
    }
    if not shown:
        shown = [
            {
                "priority": 9,
                "category": "运行状态",
                "subject": "管线",
                "status": "待采集",
                "detail": "未提供错误、熔断、阻断、预筛或下一动作证据",
                "next_action": "继续读取编排器状态",
            }
        ]
    return shown, meta


def _has_final_evidence(pipeline_status: Mapping[str, Any]) -> bool:
    final_count = _number(_first(pipeline_status, "state.score_run_counts.final"))
    if final_count is not None and final_count >= 1:
        return True
    evidence = _first(pipeline_status, "final_evidence", "release.final_evidence")
    if not isinstance(evidence, Mapping):
        return False
    evidence_status = str(_first(evidence, "status", "score_run_status") or "").strip().lower()
    finalized_at = _first(evidence, "finalized_at")
    if evidence_status not in {"final", "finalized", "published"} or not isinstance(finalized_at, str):
        return False
    try:
        _validated_timestamp(finalized_at)
    except ValueError:
        return False
    return True


def _lifecycle(
    pipeline_status: Mapping[str, Any],
    quality: Mapping[str, Any] | None,
    disclosure_coverage: float | None,
    core_completeness: float | None,
) -> dict[str, Any]:
    state = str(
        _coalesce(
            _first(pipeline_status, "pipeline_state", "release_status", "score_run_status", "release.status"),
            "partial",
        )
    ).strip().lower()
    cutoff_passed = _bool_value(
        pipeline_status,
        "curated.quality.cutoff_passed",
        "cutoff_passed",
        "announcement_cutoff_reached",
        "gates.announcement_cutoff_reached",
    )
    blocked_reasons = _first(pipeline_status, "blocked_reasons")
    has_blocked_reasons = isinstance(blocked_reasons, (list, tuple, Mapping)) and bool(blocked_reasons)
    reason_texts: list[str] = []
    for fallback, item in _candidate_pairs(blocked_reasons):
        if isinstance(item, Mapping):
            item = _coalesce(_first(item, "reason", "message", "error"), fallback)
        reason_texts.append(_clean_text(item, "未提供阻断原因"))

    market_ready = _coalesce(
        _bool_value(pipeline_status, "market_ready", "curated.quality.market_ready", "gates.market_ready"),
        _bool_value(quality, "market_ready", "gates.market_ready"),
    )
    governance = _coalesce(
        _bool_value(quality, "governance_verified", "gates.governance_verified"),
        _bool_value(pipeline_status, "governance_verified", "curated.quality.governance_verified"),
    )
    events = _coalesce(
        _bool_value(quality, "event_verified", "gates.event_verified"),
        _bool_value(pipeline_status, "event_verified", "curated.quality.event_verified"),
    )
    seven_dimensions = _coalesce(
        _bool_value(quality, "seven_dimension_ready", "seven_dimensions_ready", "gates.seven_dimension_ready"),
        _bool_value(pipeline_status, "seven_dimension_ready", "curated.quality.seven_dimension_ready"),
    )
    formal_score_ready = _coalesce(
        _bool_value(quality, "formal_score_ready", "gates.formal_score_ready"),
        _bool_value(
            pipeline_status,
            "formal_score_ready",
            "curated.quality.formal_score_ready",
            "gates.formal_score_ready",
        ),
    )
    strong_input = _number(
        _first(
            pipeline_status,
            "formal_pool_counts.strong",
            "pool_counts.strong",
            "release.strong_pool_count",
            "strong_pool_count",
        )
    )
    wait_input = _number(
        _first(
            pipeline_status,
            "formal_pool_counts.wait",
            "formal_pool_counts.waiting",
            "pool_counts.wait",
            "release.wait_pool_count",
            "wait_pool_count",
        )
    )
    pool_counts_explicit = strong_input is not None and wait_input is not None
    final_marker = _has_final_evidence(pipeline_status)
    all_release_gates_passed = all(
        (
            cutoff_passed is True,
            market_ready is True,
            disclosure_coverage is not None and disclosure_coverage >= 0.95,
            core_completeness is not None and core_completeness >= 0.95,
            governance is True,
            events is True,
            seven_dimensions is True,
            formal_score_ready is True,
        )
    )
    proven_final = bool(
        state in {"final", "ready", "published"}
        and final_marker
        and all_release_gates_passed
        and pool_counts_explicit
        and not has_blocked_reasons
    )

    if proven_final:
        snapshot_status = "ready"
        derived_lifecycle_state = "ready"
        strong, wait = strong_input, wait_input
        total = strong + wait
    elif cutoff_passed is False:
        snapshot_status = "partial"
        derived_lifecycle_state = (
            "pre_cutoff_blocked"
            if state in {"blocked", "failed", "error", "final", "ready", "published"} or has_blocked_reasons
            else "pre_cutoff_partial"
        )
        strong = wait = total = 0
    elif state in {"blocked", "failed", "error", "final", "ready", "published"} or has_blocked_reasons:
        snapshot_status = "blocked"
        derived_lifecycle_state = "post_cutoff_blocked" if cutoff_passed is True else "blocked_evidence_incomplete"
        strong = wait = total = 0
    else:
        snapshot_status = "partial"
        derived_lifecycle_state = "partial"
        strong = wait = total = 0

    return {
        "snapshot_status": snapshot_status,
        "derived_lifecycle_state": derived_lifecycle_state,
        "pipeline_state": state,
        "cutoff_passed": cutoff_passed,
        "market_ready": market_ready,
        "disclosure_coverage": disclosure_coverage,
        "core_completeness": core_completeness,
        "governance_verified": governance,
        "event_verified": events,
        "seven_dimension_ready": seven_dimensions,
        "formal_score_ready": formal_score_ready,
        "final_marker": final_marker,
        "final_evidence_status": "verified" if final_marker else "missing_or_invalid",
        "all_release_gates_passed": all_release_gates_passed,
        "pool_counts_explicit": pool_counts_explicit,
        "blocked_reason_count": len(reason_texts),
        "blocked_reason_summary": "；".join(reason_texts[:3]) if reason_texts else None,
        "proven_final": proven_final,
        "strong_pool_count": strong,
        "wait_pool_count": wait,
        "formal_pool_count": total,
    }


def _gate_status(value: bool | None, *, false_label: str = "未通过") -> str:
    if value is True:
        return "通过"
    if value is False:
        return false_label
    return "待核验"


def _release_gate_rows(
    pipeline_status: Mapping[str, Any],
    quality: Mapping[str, Any] | None,
    disclosure_coverage: float | None,
    core_completeness: float | None,
) -> list[dict[str, Any]]:
    cutoff = _bool_value(
        pipeline_status,
        "curated.quality.cutoff_passed",
        "announcement_cutoff_reached",
        "cutoff_reached",
        "gates.announcement_cutoff_reached",
    )
    market = _bool_value(
        pipeline_status,
        "market_ready",
        "curated.quality.market_ready",
        "gates.market_ready",
    )
    governance = _coalesce(
        _bool_value(quality, "governance_verified", "gates.governance_verified"),
        _bool_value(pipeline_status, "governance_verified", "curated.quality.governance_verified"),
    )
    events = _coalesce(
        _bool_value(quality, "event_verified", "gates.event_verified"),
        _bool_value(pipeline_status, "event_verified", "curated.quality.event_verified"),
    )
    seven_dimensions = _bool_value(
        quality,
        "seven_dimension_ready",
        "seven_dimensions_ready",
        "gates.seven_dimension_ready",
    )
    if seven_dimensions is None:
        seven_dimensions = _bool_value(
            pipeline_status, "seven_dimension_ready", "curated.quality.seven_dimension_ready"
        )
    formal_score_ready = _coalesce(
        _bool_value(quality, "formal_score_ready", "gates.formal_score_ready"),
        _bool_value(
            pipeline_status,
            "formal_score_ready",
            "curated.quality.formal_score_ready",
            "gates.formal_score_ready",
        ),
    )
    if seven_dimensions is False or formal_score_ready is False:
        formal_v2_ready = False
    elif seven_dimensions is True and formal_score_ready is True:
        formal_v2_ready = True
    else:
        formal_v2_ready = None

    if governance is False or events is False:
        governance_event_status = "未通过"
    elif governance is True and events is True:
        governance_event_status = "通过"
    else:
        governance_event_status = "待核验"

    eligible_count = _number(
        _coalesce(
            _first(quality, "eligible_universe_count", "metrics.eligible_universe_count"),
            _first(pipeline_status, "curated.quality.eligible_universe_count"),
        )
    )
    disclosed_count = _number(
        _coalesce(
            _first(quality, "disclosed_unique_count", "metrics.disclosed_unique_count"),
            _first(pipeline_status, "curated.quality.disclosed_unique_count"),
        )
    )
    if disclosure_coverage is None:
        disclosure_status = "待采集"
        disclosure_evidence = "唯一已披露合格证券数或合格证券宇宙数证据缺失"
    else:
        disclosure_status = "通过" if disclosure_coverage >= 0.95 else "未通过"
        ratio = (
            f"{int(disclosed_count)}/{int(eligible_count)}；"
            if disclosed_count is not None and eligible_count is not None
            else ""
        )
        disclosure_evidence = f"{ratio}覆盖率 {disclosure_coverage:.1%}；正式阈值为95%"

    if core_completeness is None:
        completeness_status = "待采集"
        completeness_evidence = "五个必需核心单元格的非空计数证据缺失"
    else:
        completeness_status = "通过" if core_completeness >= 0.95 else "未通过"
        completeness_evidence = f"核心字段完整率 {core_completeness:.1%}；正式阈值为95%"

    return [
        {
            "order": 1,
            "gate": "公告截止",
            "requirement": "纳入 2026-08-31 23:59:59（北京时间）前的半年报披露",
            "status": _gate_status(cutoff, false_label="尚未到公告截止"),
            "evidence": "截止前仅允许 provisional 采集与预筛",
        },
        {
            "order": 2,
            "gate": "8月31日收盘行情",
            "requirement": "估值与买点使用 2026-08-31 已完成收盘数据",
            "status": _gate_status(market, false_label="行情未就绪"),
            "evidence": "未就绪时不得用盘中价或更早价格替代",
        },
        {
            "order": 3,
            "gate": "已披露合格证券覆盖率",
            "requirement": "唯一已披露合格证券数/合格证券宇宙数不低于95%",
            "status": disclosure_status,
            "evidence": disclosure_evidence,
        },
        {
            "order": 4,
            "gate": "核心字段完整率",
            "requirement": "已披露合格证券的五个必需核心单元格非空比例不低于95%",
            "status": completeness_status,
            "evidence": completeness_evidence,
        },
        {
            "order": 5,
            "gate": "治理与重大事件核验",
            "requirement": "财报正文、审计/审阅意见和临时公告已留证",
            "status": governance_event_status,
            "evidence": "治理红橙灯与重大事件不能被总分平均稀释",
        },
        {
            "order": 6,
            "gate": "七维特征与正式分齐备",
            "requirement": "七维分项、置信度、行业模板、否决状态及正式分均可复算",
            "status": _gate_status(formal_v2_ready),
            "evidence": "缺失维度或未冻结正式分均保持空值并阻断正式发布",
        },
    ]


def _scoring_dimensions() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "dimension": "成长 G",
            "weight_pct": 18,
            "role": "直接形成用户展示的成长等级（0–100）",
            "missing_handling": "缺失保持空值并降低置信度；不重复使用EPS、利润与ROE增速",
        },
        {
            "order": 2,
            "dimension": "估值 V",
            "weight_pct": 18,
            "role": "直接形成用户展示的估值等级（0–100），周期股采用正常化口径",
            "missing_handling": "无正常化盈利或行业模板时不发布该分项",
        },
        {
            "order": 3,
            "dimension": "商业质量 M",
            "weight_pct": 18,
            "role": "衡量护城河代理与稳定性；稳定性部分进入风险等级",
            "missing_handling": "历史不足时降低置信度，新股/重组公司单列",
        },
        {
            "order": 4,
            "dimension": "盈利质量 EQ",
            "weight_pct": 12,
            "role": "现金转化与低应计；按25%权重进入风险等级",
            "missing_handling": "五年现金流或扣非口径不足时不以当期利润替代",
        },
        {
            "order": 5,
            "dimension": "财务安全 FS",
            "weight_pct": 8,
            "role": "偿债与下行韧性；按40%权重进入风险等级，风险等级越高越安全",
            "missing_handling": "债务、受限资金或监管资本不足时阻断风险结论",
        },
        {
            "order": 6,
            "dimension": "资本配置与股东回报 CA",
            "weight_pct": 16,
            "role": "增量ROIC、净股东收益与纪律；下行保护按15%进入风险等级",
            "missing_handling": "只计已完成分红/注销回购，未执行承诺不计分",
        },
        {
            "order": 7,
            "dimension": "预期差/买点 T",
            "weight_pct": 10,
            "role": "直接形成用户展示的买点等级（0–100），决定强池/等待池状态",
            "missing_handling": "无可靠一致预期时相关项取中性50并降低置信度",
        },
    ]


def _method_limits() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "topic": "展示层与内部模型",
            "risk": "七维内部归因若直接展示，可能偏离用户要求的四个等级",
            "control": "固定输出成长、估值、风险、买点四个0–100分；风险分越高代表越安全，并同时显示置信度",
            "current_status": "规则已定义，正式分尚未冻结",
        },
        {
            "order": 2,
            "topic": "财报正文核验",
            "risk": "结构化三表无法覆盖关联交易、受限资金、担保诉讼、减值、质押和董监高异议",
            "control": "正式候选必须从财报正文、审计/审阅意见和临时公告留证；不确定事项只标状态",
            "current_status": "候选深度核验待执行",
        },
        {
            "order": 3,
            "topic": "行业模板与可比性",
            "risk": "银行、资源周期、地产、公用事业与研发型成长公司不可直接同口径比较",
            "control": "使用行业专门模板，先在二级行业内标准化并设置行业入池上限",
            "current_status": "模板规则已定义，特征待齐备",
        },
        {
            "order": 4,
            "topic": "参数敏感性",
            "risk": "池成员可能依赖单组权重、阈值或会计调整",
            "control": "展示权重±5个百分点、阈值±10分及关键会计调整前后的成员变化",
            "current_status": "正式评分后执行",
        },
        {
            "order": 5,
            "topic": "数据源稳定性",
            "risk": "免费结构化源没有SLA，接口可能变更或暂时不可用",
            "control": "原始快照不可覆盖、内容哈希去重、可重试失败与访问阻断分开记录",
            "current_status": "已纳入管线设计",
        },
        {
            "order": 6,
            "topic": "报告载荷安全",
            "risk": "错误文本和状态说明可能包含本机路径、URL凭证或访问令牌",
            "control": "递归遮蔽已知敏感模式，且原始输入、任务载荷和个股明细不进入artifact",
            "current_status": "不能保证识别所有秘密；交付前仍依赖canonical安全校验",
        },
        {
            "order": 7,
            "topic": "单点工程快照",
            "risk": "当前没有足够时间序列或可解释比较，图形容易制造趋势错觉",
            "control": "就采集进度而言，当前是单点工程快照，图表不会增加信息，因此使用卡片与表格",
            "current_status": "仅用一张七维规则权重图解释方法结构，不表示采集趋势或投资结果",
        },
    ]


def _sources(
    generated_at: str,
    plan_path: str,
    scoring_spec_path: str,
    dataset_sql: Mapping[str, str],
    source_status_meta: Mapping[str, Any],
    operational_status_meta: Mapping[str, Any],
) -> list[dict[str, Any]]:
    common_filters = [
        "报告期=2026-06-30",
        "公告截止=2026-08-31 23:59:59 Asia/Shanghai",
        "范围=沪深A股，不含北交所",
    ]
    return [
        {
            "id": "pipeline_status_snapshot",
            "label": "管线聚合状态快照",
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": dataset_sql["headline_metrics"],
                "description": "用内存SQLite物化调用方提供的已审阅状态库、质量和试采聚合字段；不展开任务载荷、原始大表或个股记录。",
                "executed_at": generated_at,
                "filters": [*common_filters, "仅展示白名单聚合字段；缺失值保持null"],
                "metric_definitions": [
                    "状态库测试数=调用方明确提供的状态库通过测试数量",
                    "数据批次数=内容寻址数据快照批次的已审阅计数",
                    "已抓取行数=已审阅批次行数合计，不代表独立股票数",
                    "股票宇宙数=证券主表过滤后的沪深A股数量",
                    "已披露合格证券覆盖率=唯一已披露合格证券数/合格证券宇宙数；正式闸门为95%",
                    "核心字段完整率=五个必需核心单元格的非空数/(已披露合格证券数×5)；正式闸门为95%",
                    "预筛候选数=仅供深抓排序的非正式候选数量，不是V2正式评分",
                    "正式股票池数量=强烈关注池数+等待价格池数；非ready为0，ready要求两个计数均显式提供",
                ],
            },
        },
        {
            "id": "lifecycle_status_snapshot",
            "label": "正式发布生命周期判定",
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": dataset_sql["lifecycle_status"],
                "description": "将调用方的状态、六类发布闸门、正式评分标记和显式两池计数物化为单行、可复算的生命周期判定。",
                "executed_at": generated_at,
                "filters": [
                    *common_filters,
                    "ready采用fail-closed：所有闸门、final标记和两池计数必须显式通过",
                    "阻断原因摘要最多展示前三项；完整原因保留在运行状态表",
                ],
                "metric_definitions": [
                    "all_release_gates_passed=截止、收盘行情、双95%覆盖、治理、事件、七维特征和正式分均明确通过",
                    "final_marker=至少一个final score run，或含final状态与合法带时区finalized_at的结构化证据",
                    "derived_lifecycle_state=pre_cutoff_partial、pre_cutoff_blocked、partial、post_cutoff_blocked、blocked_evidence_incomplete或ready",
                    "ready还要求强烈关注池和等待价格池计数均显式提供；0是有效计数",
                ],
            },
        },
        {
            "id": "pilot_status_snapshot",
            "label": "免费源试采状态",
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": dataset_sql["source_status"],
                "description": (
                    "用内存SQLite物化调用方提供的已审阅数据集级试采状态；"
                    f"完整审阅{source_status_meta['reviewed_row_count']}行，展示{source_status_meta['shown_row_count']}行。"
                ),
                "executed_at": generated_at,
                "filters": [
                    *common_filters,
                    f"full_reviewed_row_count={source_status_meta['reviewed_row_count']}",
                    f"shown_row_count={source_status_meta['shown_row_count']}",
                    f"truncated={str(bool(source_status_meta['truncated'])).lower()}",
                    f"selection_rule={source_status_meta['selection_rule']}",
                    "最多25个数据集状态",
                    "不含原始证券明细",
                ],
                "metric_definitions": [
                    "row_count=对应数据批次报告的原始记录行数；不同数据集不可相加解释为股票数",
                    "status=数据集在试采时点的采集/校验状态",
                ],
            },
        },
        {
            "id": "operational_status_snapshot",
            "label": "编排器运行问题与下一动作",
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": dataset_sql["operational_status"],
                "description": (
                    "物化编排器的source_errors、circuit_breakers、blocked_reasons、curated.prefilter和next_actions聚合状态；"
                    f"完整审阅{operational_status_meta['reviewed_row_count']}行，展示{operational_status_meta['shown_row_count']}行。"
                ),
                "executed_at": generated_at,
                "filters": [
                    *common_filters,
                    f"full_reviewed_row_count={operational_status_meta['reviewed_row_count']}",
                    f"shown_row_count={operational_status_meta['shown_row_count']}",
                    f"truncated={str(bool(operational_status_meta['truncated'])).lower()}",
                    f"selection_rule={operational_status_meta['selection_rule']}",
                    "发布阻断优先于普通来源错误",
                    "最多25行",
                    "原始载荷不进入报告",
                ],
                "metric_definitions": [
                    "预筛候选=仅供安排深抓的候选，不是V2正式总分或正式股票池",
                    "发布阻断=阻止正式冻结但不删除已有provisional证据的原因",
                ],
            },
        },
        {
            "id": "scoring_spec_v2",
            "label": "A股2026中报评分框架 V2",
            "path": scoring_spec_path,
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": dataset_sql["scoring_dimensions"],
                "description": "从版本化评分规范提取七维权重、四个展示等级、缺失处理规则，并用内存SQLite物化审阅行。",
                "executed_at": generated_at,
                "filters": [*common_filters, "规则版本=V2", "七维权重合计=100%"],
                "metric_definitions": [
                    "原始总分S0=七维加权和",
                    "置信调整分Sc=50+C×(S0-50)",
                    "风险等级越高代表越安全；治理和重大事件在分数旁单列",
                ],
            },
        },
        {
            "id": "execution_plan",
            "label": "沪深A股2026中报增量采集与评分执行计划",
            "path": plan_path,
            "query": {
                "engine": "markdown-document",
                "language": "markdown",
                "description": "读取报告期、公告截止、行情锚点、数据范围、质量阈值和最终发布约束。",
                "executed_at": generated_at,
                "filters": common_filters,
                "metric_definitions": [
                    "披露覆盖率阈值=唯一已披露合格证券数/合格证券宇宙数不低于95%",
                    "核心字段完整率阈值=五个必需核心单元格的非空数/(已披露合格证券数×5)不低于95%",
                    "最终行情锚点=2026-08-31已完成收盘行情",
                ],
            },
        },
        {
            "id": "release_gate_evaluation",
            "label": "正式发布闸门评估",
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": dataset_sql["release_gates"],
                "description": "将执行计划与已审阅聚合状态映射为六道发布闸门，并用内存SQLite物化；缺失证据保持待核验。",
                "executed_at": generated_at,
                "filters": [*common_filters, "六道闸门必须全部通过才允许正式冻结"],
                "metric_definitions": [
                    "披露覆盖率闸门=唯一已披露合格证券数/合格证券宇宙数大于等于95%",
                    "核心完整率闸门=五个必需核心单元格的非空数/(已披露合格证券数×5)大于等于95%",
                    "治理事件闸门=治理与重大事件均已完成证据核验",
                    "七维与正式分闸门=七维特征、置信度、行业模板、否决状态和正式分均可复算",
                ],
            },
        },
        {
            "id": "method_boundary_evaluation",
            "label": "方法限制与稳健性控制",
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": dataset_sql["method_limits"],
                "description": "汇总V2评分规范和执行计划中的已知失败模式、控制措施与当前状态，并用内存SQLite物化。",
                "executed_at": generated_at,
                "filters": [*common_filters, "不生成未经核验的个股分数"],
                "metric_definitions": [
                    "四个展示等级=成长G、估值V、组合风险R、买点T，均为0–100分",
                    "敏感性范围=权重±5个百分点、阈值±10分及关键会计调整",
                ],
            },
        },
    ]


def build_progress_artifact(
    pipeline_status: dict,
    quality: dict | None,
    pilot_status: dict | None,
    generated_at: str,
    plan_path: str,
    scoring_spec_path: str,
) -> dict:
    """Return a deterministic canonical Data Analytics progress artifact."""

    if not isinstance(pipeline_status, Mapping):
        raise TypeError("pipeline_status must be a mapping")
    if quality is not None and not isinstance(quality, Mapping):
        raise TypeError("quality must be a mapping or None")
    if pilot_status is not None and not isinstance(pilot_status, Mapping):
        raise TypeError("pilot_status must be a mapping or None")

    pipeline_status = _sanitize_dynamic(pipeline_status)
    quality = _sanitize_dynamic(quality) if quality is not None else None
    pilot_status = _sanitize_dynamic(pilot_status) if pilot_status is not None else None

    generated_at = _validated_timestamp(generated_at)
    plan_path = _safe_relative_path(plan_path, "plan_path")
    scoring_spec_path = _safe_relative_path(scoring_spec_path, "scoring_spec_path")

    batch_count_from_status, fetched_rows_from_status = _reviewed_batch_summary(pipeline_status)
    source_rows, source_status_meta = _source_rows(pilot_status, pipeline_status)
    operational_rows, operational_status_meta = _operational_rows(pipeline_status)
    coverage = _coverage(
        _coalesce(
            _first(
                quality,
                "disclosure_coverage_rate",
                "coverage_rate",
                "performance_coverage",
                "coverage",
                "metrics.disclosure_coverage_rate",
                "metrics.coverage_rate",
            ),
            _first(
                pipeline_status,
                "disclosure_coverage_rate",
                "performance_coverage",
                "coverage",
                "curated.quality.disclosure_coverage_rate",
                "curated.quality.coverage_rate",
                "curated.performance.coverage_rate",
            ),
            _first(pilot_status, "disclosure_coverage_rate", "performance_coverage", "coverage"),
        )
    )
    core_completeness = _coverage(
        _coalesce(
            _first(quality, "core_field_completeness", "metrics.core_field_completeness"),
            _first(
                pipeline_status,
                "core_field_completeness",
                "curated.quality.core_field_completeness",
                "curated.performance.core_field_completeness",
            ),
            _first(pilot_status, "core_field_completeness"),
        )
    )
    lifecycle = _lifecycle(pipeline_status, quality, coverage, core_completeness)
    batch_count = _count_from_mapping(
        _first(
            pipeline_status,
            "data_batch_count",
            "source_snapshot_count",
            "snapshot_count",
            "snapshot_counts",
        )
    )
    if batch_count is None:
        batch_count = batch_count_from_status
    fetched_rows = _number(
        _coalesce(
            _first(pipeline_status, "fetched_row_count", "fetched_rows", "row_count"),
            fetched_rows_from_status,
            _first(pilot_status, "fetched_row_count", "fetched_rows", "total_rows"),
        )
    )
    if fetched_rows is None:
        row_counts = [row["row_count"] for row in source_rows]
        if row_counts and all(value is not None for value in row_counts):
            fetched_rows = _count_from_mapping({str(index): value for index, value in enumerate(row_counts)})

    headline_metrics = [
        {
            "state_store_test_count": _number(
                _first(
                    pipeline_status,
                    "state_store_test_count",
                    "state_store_tests",
                    "tests.state_store_passed",
                    "tests.passed",
                )
            ),
            "data_batch_count": batch_count,
            "fetched_row_count": fetched_rows,
            "universe_count": _number(
                _coalesce(
                    _first(
                        pipeline_status,
                        "universe_count",
                        "stock_universe_count",
                        "security_count",
                        "curated.universe.universe_count",
                        "curated.quality.universe_count",
                    ),
                    _first(pilot_status, "universe_count", "stock_universe_count"),
                )
            ),
            "performance_coverage": coverage,
            "disclosure_coverage": coverage,
            "prefilter_candidate_count": _number(
                _first(
                    pipeline_status,
                    "curated.prefilter.candidate_count",
                    "curated.prefilter.selected_count",
                    "prefilter_candidate_count",
                )
            ),
            "strong_pool_count": lifecycle["strong_pool_count"],
            "wait_pool_count": lifecycle["wait_pool_count"],
            "formal_pool_count": lifecycle["formal_pool_count"],
        }
    ]

    headline_metrics, headline_sql = _materialize_reviewed_rows(
        headline_metrics,
        (
            "state_store_test_count",
            "data_batch_count",
            "fetched_row_count",
            "universe_count",
            "performance_coverage",
            "disclosure_coverage",
            "prefilter_candidate_count",
            "strong_pool_count",
            "wait_pool_count",
            "formal_pool_count",
        ),
    )
    source_rows, source_status_sql = _materialize_reviewed_rows(
        source_rows, ("priority", "dataset", "source", "status", "row_count", "as_of", "note")
    )
    operational_rows, operational_status_sql = _materialize_reviewed_rows(
        operational_rows,
        ("priority", "category", "subject", "status", "detail", "next_action"),
    )
    operational_meta_rows, operational_status_meta_sql = _materialize_reviewed_rows(
        [dict(operational_status_meta)],
        ("reviewed_row_count", "shown_row_count", "truncated", "selection_rule"),
    )
    lifecycle_rows, lifecycle_status_sql = _materialize_reviewed_rows(
        [dict(lifecycle)],
        (
            "pipeline_state",
            "cutoff_passed",
            "market_ready",
            "disclosure_coverage",
            "core_completeness",
            "governance_verified",
            "event_verified",
            "seven_dimension_ready",
            "formal_score_ready",
            "final_marker",
            "final_evidence_status",
            "all_release_gates_passed",
            "pool_counts_explicit",
            "blocked_reason_count",
            "blocked_reason_summary",
            "derived_lifecycle_state",
            "snapshot_status",
            "proven_final",
            "strong_pool_count",
            "wait_pool_count",
            "formal_pool_count",
        ),
    )
    scoring_dimensions, scoring_dimensions_sql = _materialize_reviewed_rows(
        _scoring_dimensions(), ("order", "dimension", "weight_pct", "role", "missing_handling")
    )
    release_gates, release_gates_sql = _materialize_reviewed_rows(
        _release_gate_rows(pipeline_status, quality, coverage, core_completeness),
        ("order", "gate", "requirement", "status", "evidence"),
    )
    method_limits, method_limits_sql = _materialize_reviewed_rows(
        _method_limits(), ("order", "topic", "risk", "control", "current_status")
    )
    dataset_sql = {
        "headline_metrics": headline_sql,
        "source_status": source_status_sql,
        "operational_status": operational_status_sql,
        "operational_status_meta": operational_status_meta_sql,
        "lifecycle_status": lifecycle_status_sql,
        "scoring_dimensions": scoring_dimensions_sql,
        "release_gates": release_gates_sql,
        "method_limits": method_limits_sql,
    }

    sources = _sources(
        generated_at,
        plan_path,
        scoring_spec_path,
        dataset_sql,
        source_status_meta,
        operational_status_meta,
    )
    source_inventory = copy.deepcopy(sources)
    cards = [
        {
            "id": "state_store_tests_card",
            "description": "已明确报告为通过的状态库单元测试数量；缺失时显示待采集。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "状态库测试数", "field": "state_store_test_count", "format": "number"}],
        },
        {
            "id": "data_batches_card",
            "description": "内容寻址并登记的已审阅数据批次数。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "数据批次数", "field": "data_batch_count", "format": "number"}],
        },
        {
            "id": "fetched_rows_card",
            "description": "已审阅批次的记录行数；不同数据集可能重叠，不解释为股票数。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "已抓取行数", "field": "fetched_row_count", "format": "compact"}],
        },
        {
            "id": "universe_card",
            "description": "证券主表过滤后的沪深A股目标数量。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "股票宇宙数", "field": "universe_count", "format": "compact"}],
        },
        {
            "id": "coverage_card",
            "description": "唯一已披露合格证券覆盖合格证券宇宙的比例；正式阈值为95%。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "已披露覆盖率", "field": "disclosure_coverage", "format": "percent"}],
        },
        {
            "id": "prefilter_card",
            "description": "仅供安排完整三表和正文核验的候选数量，不是V2正式评分或正式股票池。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "预筛候选数", "field": "prefilter_candidate_count", "format": "number"}],
        },
        {
            "id": "strong_pool_card",
            "description": "非ready时为0；ready要求显式提供并显示实际强烈关注池数量，0为有效计数。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "强烈关注池", "field": "strong_pool_count", "format": "number"}],
        },
        {
            "id": "wait_pool_card",
            "description": "非ready时为0；ready要求显式提供并显示实际等待价格池数量，0为有效计数。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "等待价格池", "field": "wait_pool_count", "format": "number"}],
        },
        {
            "id": "formal_pool_card",
            "description": "两池合计；非ready为0，缺少任一显式计数时阻断ready。",
            "dataset": "headline_metrics",
            "sourceId": "pipeline_status_snapshot",
            "metrics": [{"label": "正式股票池数量", "field": "formal_pool_count", "format": "number"}],
        },
    ]

    tables = [
        {
            "id": "scoring_dimensions_table",
            "title": "七维内部评分框架",
            "subtitle": "V2权重、对四个用户展示等级的作用及缺失处理",
            "dataset": "scoring_dimensions",
            "sourceId": "scoring_spec_v2",
            "defaultSort": {"field": "order", "direction": "asc"},
            "density": "spacious",
            "columns": [
                {"field": "order", "label": "序号", "format": "number"},
                {"field": "dimension", "label": "维度", "type": "text"},
                {"field": "weight_pct", "label": "权重（%）", "format": "number"},
                {"field": "role", "label": "角色", "type": "text"},
                {"field": "missing_handling", "label": "缺失时处理", "type": "text"},
            ],
        },
        {
            "id": "source_status_table",
            "title": "当前数据源与数据集状态",
            "subtitle": (
                f"审阅{source_status_meta['reviewed_row_count']}条，展示{source_status_meta['shown_row_count']}条；"
                f"截断={'是' if source_status_meta['truncated'] else '否'}；失败/阻断/可重试优先"
            ),
            "dataset": "source_status",
            "sourceId": "pilot_status_snapshot",
            "defaultSort": {"field": "priority", "direction": "asc"},
            "density": "spacious",
            "columns": [
                {"field": "priority", "label": "优先级", "format": "number"},
                {"field": "dataset", "label": "数据集", "type": "text"},
                {"field": "source", "label": "来源", "type": "text"},
                {"field": "status", "label": "状态", "type": "text"},
                {"field": "row_count", "label": "记录行数", "format": "number"},
                {"field": "as_of", "label": "数据时点", "type": "text"},
                {"field": "note", "label": "说明", "type": "text"},
            ],
        },
        {
            "id": "operational_status_table",
            "title": "编排器问题、阻断与下一动作",
            "subtitle": (
                f"审阅{operational_status_meta['reviewed_row_count']}条，展示{operational_status_meta['shown_row_count']}条；"
                f"截断={'是' if operational_status_meta['truncated'] else '否'}；发布阻断优先"
            ),
            "dataset": "operational_status",
            "sourceId": "operational_status_snapshot",
            "defaultSort": {"field": "priority", "direction": "asc"},
            "density": "spacious",
            "columns": [
                {"field": "priority", "label": "优先级", "format": "number"},
                {"field": "category", "label": "类别", "type": "text"},
                {"field": "subject", "label": "对象", "type": "text"},
                {"field": "status", "label": "状态", "type": "text"},
                {"field": "detail", "label": "证据/原因", "type": "text"},
                {"field": "next_action", "label": "下一动作", "type": "text"},
            ],
        },
        {
            "id": "release_gates_table",
            "title": "正式评分与股票池发布闸门",
            "subtitle": "六道闸门全部通过前保持partial或blocked，不发布正式池",
            "dataset": "release_gates",
            "sourceId": "release_gate_evaluation",
            "defaultSort": {"field": "order", "direction": "asc"},
            "density": "spacious",
            "columns": [
                {"field": "order", "label": "序号", "format": "number"},
                {"field": "gate", "label": "闸门", "type": "text"},
                {"field": "requirement", "label": "要求", "type": "text"},
                {"field": "status", "label": "当前状态", "type": "text"},
                {"field": "evidence", "label": "证据与解释", "type": "text"},
            ],
        },
        {
            "id": "method_limits_table",
            "title": "方法限制与稳健性控制",
            "subtitle": "新增展示映射、正文核验、行业模板和敏感性要求",
            "dataset": "method_limits",
            "sourceId": "method_boundary_evaluation",
            "defaultSort": {"field": "order", "direction": "asc"},
            "density": "spacious",
            "columns": [
                {"field": "order", "label": "序号", "format": "number"},
                {"field": "topic", "label": "主题", "type": "text"},
                {"field": "risk", "label": "限制/失败模式", "type": "text"},
                {"field": "control", "label": "控制与稳健性检查", "type": "text"},
                {"field": "current_status", "label": "当前状态", "type": "text"},
            ],
        },
    ]
    charts = [
        {
            "id": "scoring_weight_chart",
            "title": "七维评分权重结构",
            "subtitle": "规则权重合计100%；用于解释模型结构，不表示采集趋势或投资结果",
            "type": "bar",
            "dataset": "scoring_dimensions",
            "sourceId": "scoring_spec_v2",
            "valueFormat": "number",
            "unit": "%",
            "encodings": {
                "x": {"field": "dimension", "type": "nominal", "label": "评分维度"},
                "y": {"field": "weight_pct", "type": "quantitative", "label": "权重", "unit": "%"},
                "tooltip": [
                    {"field": "role", "type": "text", "label": "角色"},
                    {"field": "missing_handling", "type": "text", "label": "缺失时处理"},
                ],
            },
            "layout": "full",
        }
    ]

    reason_summary = lifecycle.get("blocked_reason_summary") or "未提供阻断原因"
    if lifecycle["snapshot_status"] == "ready":
        strong_text = (
            str(lifecycle["strong_pool_count"])
            if lifecycle["strong_pool_count"] is not None
            else "未知"
        )
        wait_text = (
            str(lifecycle["wait_pool_count"])
            if lifecycle["wait_pool_count"] is not None
            else "未知"
        )
        lifecycle_body = (
            "## 当前生命周期：final证据已确认\n\n"
            f"状态输入证明最终冻结已完成；强烈关注池为{strong_text}，等待价格池为{wait_text}。"
            "只有调用方明确提供两个正式计数且全部发布闸门通过时才会进入ready。"
        )
    elif lifecycle["derived_lifecycle_state"] == "pre_cutoff_blocked":
        lifecycle_body = (
            "## 当前生命周期：截止前冻结尝试被阻断\n\n"
            f"尚未到公告截止；本次提前冻结尝试的阻断原因为：{reason_summary}。"
            "正式评分未冻结，两个正式股票池均保持0；当前仍按partial采集与预筛处理。"
        )
    elif lifecycle["snapshot_status"] == "blocked":
        timing = "公告截止已经通过" if lifecycle["cutoff_passed"] is True else "公告截止证据尚未确认"
        lifecycle_body = (
            "## 当前生命周期：截止后仍被阻断\n\n"
            f"{timing}，但正式发布仍被阻断；阻断原因为：{reason_summary}。"
            "正式评分未冻结，两个正式股票池均保持0；具体下一动作见运行状态表。"
        )
    else:
        timing = (
            "尚未到公告截止"
            if lifecycle["cutoff_passed"] is False
            else "尚未取得最终冻结证据"
        )
        lifecycle_body = (
            "## 当前生命周期：仍为partial采集与预筛\n\n"
            f"{timing}；正式评分未冻结，两个正式股票池及其合计均为0。"
            "预筛候选只用于安排深抓，不属于正式评分。"
        )

    blocks = [
        {"id": "report_title", "type": "markdown", "body": f"# {REPORT_TITLE}"},
        {
            "id": "method_summary",
            "type": "markdown",
            "body": (
                "## 技术摘要：V1并不完美，V2降低利润信号重复计分\n\n"
                "成长、估值和安全若重复依赖利润，容易在周期盈利顶部产生错误共振。"
                "V2采用七维内部归因，并把治理、重大事件、周期顶部和拥挤状态放在普通加权分之外处理。"
            ),
            "sourceId": "scoring_spec_v2",
        },
        {
            "id": "lifecycle_summary",
            "type": "markdown",
            "body": lifecycle_body + "\n\n> **研究筛选，不构成投资建议。**",
            "sourceId": "lifecycle_status_snapshot",
        },
        {
            "id": "headline_metrics",
            "type": "metric-strip",
            "cardIds": [card["id"] for card in cards],
        },
        {
            "id": "dimensions_intro",
            "type": "markdown",
            "body": (
                "## 七维框架通过四个用户等级解释\n\n"
                "成长G和估值V直接对应同名等级；风险等级组合财务安全、盈利质量、商业稳定性和资本配置下行保护；"
                "买点等级对应T。所有等级为0–100分，风险等级越高代表越安全；缺失数据降低置信度或阻断结论。"
            ),
            "sourceId": "scoring_spec_v2",
        },
        {"id": "dimensions_chart_block", "type": "chart", "chartId": "scoring_weight_chart"},
        {"id": "dimensions_table_block", "type": "table", "tableId": "scoring_dimensions_table"},
        {
            "id": "data_status_intro",
            "type": "markdown",
            "body": (
                "## 数据源状态优先暴露失败与阻断\n\n"
                f"本快照完整审阅{source_status_meta['reviewed_row_count']}条数据集状态，"
                f"展示{source_status_meta['shown_row_count']}条；截断={'是' if source_status_meta['truncated'] else '否'}。"
                "选择规则为失败、阻断和可重试状态优先，其余按数据集与来源稳定排序。"
            ),
            "sourceId": "pilot_status_snapshot",
        },
        {"id": "source_status_table_block", "type": "table", "tableId": "source_status_table"},
        {
            "id": "operational_status_intro",
            "type": "markdown",
            "body": (
                "## 编排器问题与下一动作保持可见\n\n"
                f"完整审阅{operational_status_meta['reviewed_row_count']}条运行状态，"
                f"展示{operational_status_meta['shown_row_count']}条；截断={'是' if operational_status_meta['truncated'] else '否'}。"
                "发布阻断优先，其次为数据源错误/熔断和下一动作；"
                "预筛只安排深抓，不替代正式评分。"
            ),
            "sourceId": "operational_status_snapshot",
        },
        {"id": "operational_status_table_block", "type": "table", "tableId": "operational_status_table"},
        {
            "id": "release_gates_intro",
            "type": "markdown",
            "body": (
                "## 六道发布闸门全部通过前不生成正式股票池\n\n"
                "公告截止、8月31日收盘行情、至少95%的已披露合格证券覆盖率、至少95%的五项核心字段完整率、"
                "治理/重大事件核验以及七维特征与正式分齐备分别判定，任一证据缺失即保持partial或blocked。"
            ),
            "sourceId": "release_gate_evaluation",
        },
        {"id": "release_gates_table_block", "type": "table", "tableId": "release_gates_table"},
        {
            "id": "limitations_intro",
            "type": "markdown",
            "body": (
                "## 单点快照只支持工程审计，不支持趋势或投资结论\n\n"
                "就采集进度而言，当前是单点工程快照，进度图不会增加信息，因此使用卡片与表格。"
                "唯一权重图只解释规则结构。结构化三表不足以覆盖财报正文风险，已知敏感模式会被遮蔽，"
                "但不能保证识别所有秘密。"
            ),
            "sourceId": "method_boundary_evaluation",
        },
        {"id": "method_limits_table_block", "type": "table", "tableId": "method_limits_table"},
        {
            "id": "pipeline_next_steps",
            "type": "markdown",
            "body": (
                "## 下一步：按截止与行情锚点继续增量采集\n\n"
                "1. 按内容哈希刷新披露、全市场业绩和最新已完成交易日。\n"
                "2. 对预筛候选定向拉取完整三表、半年报正文与重大公告。\n"
                "3. 在2026年8月31日收盘与公告截止证据齐备后才尝试最终冻结。"
            ),
            "sourceId": "execution_plan",
        },
        {
            "id": "sensitivity_next_step",
            "type": "markdown",
            "body": (
                "## 正式评分后执行参数敏感性检查\n\n"
                "冻结候选后比较权重±5个百分点、阈值±10分及关键会计调整前后的池成员变化。"
            ),
            "sourceId": "scoring_spec_v2",
        },
        {
            "id": "further_questions",
            "type": "markdown",
            "body": (
                "## 可进一步回答的问题\n\n"
                "- 哪些数据集仍限制披露覆盖或核心完整率闸门？\n"
                "- 哪些候选因正文风险、治理状态或行业模板被降级？\n"
                "- 参数与关键会计调整会改变哪些池成员？\n"
                "- 最终行情与买点条件满足后，两池是否仍互斥并符合行业上限？"
            ),
        },
    ]

    if lifecycle["snapshot_status"] == "ready":
        access_issues: list[dict[str, Any]] = []
    elif lifecycle["derived_lifecycle_state"] == "pre_cutoff_blocked":
        access_issues = [
            {
                "id": "report_pre_cutoff_blocked",
                "scope": "release",
                "sourceId": "lifecycle_status_snapshot",
                "message": (
                    "尚未到公告截止；本次提前冻结尝试被阻断："
                    f"{reason_summary}。当前仍按partial采集与预筛处理。"
                ),
            },
            {
                "id": "prescreen_not_final",
                "scope": "score",
                "sourceId": "pipeline_status_snapshot",
                "message": "预筛不是正式评分，截止和其余发布闸门全部通过前两个正式股票池均保持0。研究筛选，不构成投资建议。",
            },
        ]
    elif lifecycle["snapshot_status"] == "blocked":
        blocked_timing = (
            "公告截止已经通过"
            if lifecycle["cutoff_passed"] is True
            else "公告截止证据尚未确认"
        )
        access_issues = [
            {
                "id": "report_blocked",
                "scope": "release",
                "sourceId": "lifecycle_status_snapshot",
                "message": f"{blocked_timing}，正式发布仍被阻断：{reason_summary}；下一动作见编排器运行状态表。",
            },
            {
                "id": "prescreen_not_final",
                "scope": "score",
                "sourceId": "pipeline_status_snapshot",
                "message": "预筛不是正式评分，阻断解除前两个正式股票池均保持0。研究筛选，不构成投资建议。",
            },
        ]
    else:
        timing_message = (
            "尚未到公告截止，当前只能采集和预筛。"
            if lifecycle["cutoff_passed"] is False
            else "公告截止与最终冻结证据尚未齐备，当前只能采集和预筛。"
        )
        access_issues = [
            {
                "id": "report_partial",
                "scope": "report",
                "sourceId": "pipeline_status_snapshot",
                "message": "当前报告为partial工程快照，正式评分未冻结。",
            },
            {
                "id": "cutoff_not_frozen",
                "scope": "release",
                "sourceId": "execution_plan",
                "message": timing_message,
            },
            {
                "id": "prescreen_not_final",
                "scope": "score",
                "sourceId": "pipeline_status_snapshot",
                "message": "当前预筛不是正式评分，不得据此形成正式股票池。研究筛选，不构成投资建议。",
            },
        ]
    if access_issues:
        access_issues.append(
            {
                "id": "free_source_no_sla",
                "scope": "data",
                "sourceId": "pilot_status_snapshot",
                "message": "免费结构化源没有SLA，接口失败或变更需通过缓存、重试和交叉核验处理。",
            }
        )

    snapshot = {
        "version": 1,
        "generatedAt": generated_at,
        "status": lifecycle["snapshot_status"],
        "datasets": {
            "headline_metrics": headline_metrics,
            "scoring_dimensions": scoring_dimensions,
            "source_status": source_rows,
            "source_status_meta": [dict(source_status_meta)],
            "operational_status": operational_rows,
            "operational_status_meta": operational_meta_rows,
            "lifecycle_status": lifecycle_rows,
            "release_gates": release_gates,
            "method_limits": method_limits,
        },
    }
    if access_issues:
        snapshot["accessIssues"] = access_issues

    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": REPORT_TITLE,
            "description": f"A股2026中报评分方法审计与增量采集{lifecycle['snapshot_status']}报告。",
            "generatedAt": generated_at,
            "cards": cards,
            "charts": charts,
            "tables": tables,
            "sources": source_inventory,
            "blocks": blocks,
        },
        "snapshot": snapshot,
        "sources": sources,
    }
    return artifact


__all__ = ["build_progress_artifact"]
