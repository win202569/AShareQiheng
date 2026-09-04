"""Pure point-in-time helpers for the formal scoring contract."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Literal, Protocol
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
FORMAL_FREEZE_AT_CN = "2026-08-31T15:00:00+08:00"


class FormalVersion(Protocol):
    published_at_utc: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    content_hash: str


def _aware_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a timezone-aware ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be a timezone-aware ISO-8601 string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def market_close_as_of(value: str) -> str:
    """Return the 15:00 Asia/Shanghai close for an explicit calendar date."""
    try:
        parsed_date = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("market close date must be a timezone-aware contract date") from exc
    return datetime.combine(parsed_date, time(15), SHANGHAI).isoformat()


def resolve_effective_at(
    published_at: str,
    precision: Literal["timestamp", "date_only"],
    *,
    verified_next_exchange_close: str | None = None,
) -> str:
    """Resolve effective time without inferring exchange calendar sessions."""
    if precision == "timestamp":
        _aware_datetime(published_at)
        if verified_next_exchange_close is not None:
            raise ValueError("timestamp precision must not include a verified next exchange close")
        return published_at
    if precision != "date_only":
        raise ValueError("precision must be timestamp or date_only")
    try:
        published_date = date.fromisoformat(published_at)
    except (TypeError, ValueError) as exc:
        raise ValueError("date_only publication must be an ISO-8601 date") from exc
    if verified_next_exchange_close is None:
        raise ValueError("date_only publication requires a verified next exchange close")
    next_close = _aware_datetime(verified_next_exchange_close)
    shanghai_close = next_close.astimezone(SHANGHAI)
    if shanghai_close.timetz().replace(tzinfo=None) != time(15):
        raise ValueError("verified next exchange close must be 15:00:00 Asia/Shanghai")
    end_of_publication_day = datetime.combine(published_date, time(23, 59, 59), SHANGHAI)
    if next_close <= end_of_publication_day:
        raise ValueError("verified next exchange close must follow the publication date")
    return verified_next_exchange_close


def is_visible_at(effective_at_utc: str, as_of_utc: str) -> bool:
    """Return whether verified evidence was effective by an aware cutoff."""
    return _aware_datetime(effective_at_utc) <= _aware_datetime(as_of_utc)


def formal_version_sort_key(row: FormalVersion) -> tuple[float, int, float, float, str]:
    """Sort newest formal versions first, with a stable hash tie-breaker."""
    published = _aware_datetime(row.published_at_utc).astimezone(timezone.utc)
    captured = _aware_datetime(row.captured_at_utc).astimezone(timezone.utc)
    updated_value = row.source_updated_at_utc
    if updated_value is None:
        updated_missing = 1
        updated_timestamp = 0.0
    else:
        updated_missing = 0
        updated_timestamp = -_aware_datetime(updated_value).astimezone(timezone.utc).timestamp()
    content_hash = row.content_hash
    if not isinstance(content_hash, str) or not content_hash:
        raise ValueError("content_hash must be non-empty")
    return (
        -published.timestamp(),
        updated_missing,
        updated_timestamp,
        -captured.timestamp(),
        content_hash,
    )


__all__ = [
    "FORMAL_FREEZE_AT_CN",
    "formal_version_sort_key",
    "is_visible_at",
    "market_close_as_of",
    "resolve_effective_at",
]
