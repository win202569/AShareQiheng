"""Immutable official-source evidence and source-policy verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Literal
from urllib.parse import urlsplit


_SECURITY_ID = re.compile(r"^(?:SH|SZ|BJ)[0-9]{6}$")
_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_AUTHORITATIVE_HOSTS = {
    "cninfo": frozenset({"www.cninfo.com.cn", "static.cninfo.com.cn"}),
    "sse": frozenset({"www.sse.com.cn", "query.sse.com.cn", "static.sse.com.cn"}),
    "szse": frozenset({"www.szse.cn", "docs.static.szse.cn"}),
    "bse": frozenset({"www.bse.cn"}),
    "csrc": frozenset({"www.csrc.gov.cn"}),
}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _aware_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _timestamp_reason(value: object) -> str | None:
    if not isinstance(value, str):
        return "invalid_timestamp"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "invalid_timestamp"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "naive_timestamp"
    return None


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


@dataclass(frozen=True)
class OfficialRequest:
    source: str
    dataset: str
    security_id: str | None
    period_or_date: str | None
    exchange: Literal["SH", "SZ", "BJ"] | None = None

    def canonical_json_bytes(self) -> bytes:
        return _canonical_json_bytes(
            {
                "dataset": self.dataset,
                "exchange": self.exchange,
                "period_or_date": self.period_or_date,
                "security_id": self.security_id,
                "source": self.source,
            }
        )

    @property
    def request_fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json_bytes()).hexdigest()


@dataclass(frozen=True)
class OfficialFetch:
    request: OfficialRequest
    raw_bytes: bytes
    original_url: str
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    source_updated_at_utc: str | None
    captured_at_utc: str
    effective_at_utc: str
    effective_time_evidence_hash: str | None
    refresh_generation: str
    parser_id: str
    parser_version: str
    mapping_version: str
    declared_security_id: str | None
    declared_period: str | None

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()

    @classmethod
    def minimal(
        cls,
        request: OfficialRequest,
        raw_bytes: bytes,
        original_url: str,
        published_at_utc: str,
        published_precision: Literal["timestamp", "date_only"],
        *,
        refresh_generation: str,
    ) -> "OfficialFetch":
        """Build a deterministic fixture-sized fetch without weakening verification."""
        return cls(
            request=request,
            raw_bytes=raw_bytes,
            original_url=original_url,
            published_at_utc=published_at_utc,
            published_precision=published_precision,
            source_updated_at_utc=None,
            captured_at_utc=published_at_utc,
            effective_at_utc=published_at_utc,
            effective_time_evidence_hash=None,
            refresh_generation=refresh_generation,
            parser_id="fixture-parser",
            parser_version="fixture-parser-v1",
            mapping_version="fixture-mapping-v1",
            declared_security_id=request.security_id,
            declared_period=request.period_or_date,
        )


@dataclass(frozen=True)
class EvidenceVerification:
    status: Literal["verified", "rejected"]
    content_sha256: str
    reasons: tuple[str, ...]
    effective_at_utc: str | None = None

    def visible_at(self, as_of_utc: str) -> bool:
        effective = _aware_timestamp(self.effective_at_utc)
        as_of = _aware_timestamp(as_of_utc)
        return self.status == "verified" and effective is not None and as_of is not None and effective <= as_of


@dataclass(frozen=True)
class VerifiedCalendarBinding:
    snapshot_id: str
    manifest_sha256: str
    exchange: Literal["SH", "SZ", "BJ"]
    freeze_at_utc: str
    registry_manifest_hash: str
    selector_hash: str
    prerequisite_task_id: str


@dataclass(frozen=True)
class OfficialSnapshotRef:
    snapshot_id: str
    source: str
    dataset: str
    request_fingerprint: str
    security_id: str | None
    period_or_date: str | None
    exchange: Literal["SH", "SZ", "BJ"] | None
    content_sha256: str
    manifest_sha256: str
    content_path: str
    manifest_path: str
    original_url: str
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    source_updated_at_utc: str | None
    captured_at_utc: str
    effective_at_utc: str
    effective_time_evidence_hash: str | None
    refresh_generation: str
    producing_task_id: str | None
    parser_id: str
    parser_version: str
    mapping_version: str
    verification_status: Literal["verified"]


@dataclass(frozen=True)
class SourcePolicy:
    """A closed set of HTTPS hostnames for one authoritative publisher."""

    source: str
    allowed_hosts: frozenset[str]

    def __post_init__(self) -> None:
        if not _nonempty_text(self.source):
            raise ValueError("source must be non-empty")
        if not self.allowed_hosts or any(not _nonempty_text(host) for host in self.allowed_hosts):
            raise ValueError("allowed_hosts must contain authoritative hostnames")
        object.__setattr__(
            self, "allowed_hosts", frozenset(host.lower() for host in self.allowed_hosts)
        )

    @property
    def is_authoritative(self) -> bool:
        return _AUTHORITATIVE_HOSTS.get(self.source) == self.allowed_hosts

    @classmethod
    def cninfo(cls) -> "SourcePolicy":
        return cls("cninfo", _AUTHORITATIVE_HOSTS["cninfo"])

    @classmethod
    def sse(cls) -> "SourcePolicy":
        return cls("sse", _AUTHORITATIVE_HOSTS["sse"])

    @classmethod
    def szse(cls) -> "SourcePolicy":
        return cls("szse", _AUTHORITATIVE_HOSTS["szse"])

    @classmethod
    def bse(cls) -> "SourcePolicy":
        return cls("bse", _AUTHORITATIVE_HOSTS["bse"])

    @classmethod
    def csrc(cls) -> "SourcePolicy":
        return cls("csrc", _AUTHORITATIVE_HOSTS["csrc"])

    def verify(
        self,
        fetch: OfficialFetch,
        *,
        calendar_binding: VerifiedCalendarBinding | None = None,
    ) -> EvidenceVerification:
        return verify_official_fetch(fetch, self, calendar_binding=calendar_binding)


def _request_exchange(request: OfficialRequest, reasons: set[str]) -> str | None:
    exchange = request.exchange
    if exchange is not None and exchange not in _EXCHANGES:
        reasons.add("invalid_exchange")
        exchange = None
    if request.security_id is None:
        return exchange
    if not isinstance(request.security_id, str) or _SECURITY_ID.fullmatch(request.security_id) is None:
        reasons.add("invalid_security_id")
        return exchange
    identity_exchange = request.security_id[:2]
    if exchange is not None and exchange != identity_exchange:
        reasons.add("security_exchange_mismatch")
    return exchange or identity_exchange


def _binding_is_resolver_valid(binding: object) -> bool:
    if not isinstance(binding, VerifiedCalendarBinding):
        return False
    return (
        binding.exchange in _EXCHANGES
        and _aware_timestamp(binding.freeze_at_utc) is not None
        and all(
            _nonempty_text(value)
            for value in (
                binding.snapshot_id,
                binding.manifest_sha256,
                binding.registry_manifest_hash,
                binding.selector_hash,
                binding.prerequisite_task_id,
            )
        )
    )


def _fetch_content_sha256(fetch: object) -> str:
    raw_bytes = getattr(fetch, "raw_bytes", None)
    return hashlib.sha256(raw_bytes).hexdigest() if isinstance(raw_bytes, bytes) else ""


def verify_official_fetch(
    fetch: OfficialFetch,
    policy: SourcePolicy,
    *,
    calendar_binding: VerifiedCalendarBinding | None = None,
) -> EvidenceVerification:
    """Return a deterministic verification result without performing transport."""
    content_sha256 = _fetch_content_sha256(fetch)
    reasons: set[str] = set()
    if not isinstance(fetch, OfficialFetch):
        reasons.add("invalid_fetch")
        return EvidenceVerification("rejected", content_sha256, tuple(sorted(reasons)))
    if not isinstance(policy, SourcePolicy):
        reasons.add("invalid_policy")
        return EvidenceVerification("rejected", content_sha256, tuple(sorted(reasons)))
    if not policy.is_authoritative:
        reasons.add("source_not_authoritative")

    request = fetch.request
    if not isinstance(request, OfficialRequest):
        reasons.add("invalid_request")
        resolved_exchange = None
    else:
        if not _nonempty_text(request.source):
            reasons.add("request_source_missing")
        if not _nonempty_text(request.dataset):
            reasons.add("request_dataset_missing")
        if request.source != policy.source:
            reasons.add("source_not_authoritative")
        resolved_exchange = _request_exchange(request, reasons)
        if fetch.declared_security_id != request.security_id:
            reasons.add("declared_security_id_mismatch")
        if fetch.declared_period != request.period_or_date:
            reasons.add("declared_period_mismatch")

    if not isinstance(fetch.raw_bytes, bytes):
        reasons.add("raw_bytes_not_bytes")
    elif not fetch.raw_bytes:
        reasons.add("empty_payload")

    try:
        parsed_url = urlsplit(fetch.original_url)
    except (TypeError, ValueError):
        parsed_url = None
    if parsed_url is None or parsed_url.scheme.lower() != "https":
        reasons.add("url_not_https")
    elif parsed_url.hostname is None or parsed_url.hostname.lower() not in policy.allowed_hosts:
        reasons.add("url_host_not_allowlisted")
    elif parsed_url.username is not None or parsed_url.password is not None:
        reasons.add("url_credentials_forbidden")

    for field, value in (
        ("published_at_utc", fetch.published_at_utc),
        ("source_updated_at_utc", fetch.source_updated_at_utc),
        ("captured_at_utc", fetch.captured_at_utc),
        ("effective_at_utc", fetch.effective_at_utc),
    ):
        if field == "source_updated_at_utc" and value is None:
            continue
        reason = _timestamp_reason(value)
        if reason is not None:
            reasons.add(reason)
    published_at = _aware_timestamp(fetch.published_at_utc)
    effective_at = _aware_timestamp(fetch.effective_at_utc)
    if published_at is not None and effective_at is not None and effective_at < published_at:
        reasons.add("effective_before_publication")

    if fetch.published_precision not in {"timestamp", "date_only"}:
        reasons.add("invalid_published_precision")
    elif fetch.published_precision == "timestamp":
        if fetch.effective_time_evidence_hash is not None:
            reasons.add("timestamp_effective_time_evidence_forbidden")
        if calendar_binding is not None:
            reasons.add("timestamp_calendar_binding_forbidden")
    else:
        if not _binding_is_resolver_valid(calendar_binding):
            reasons.add("calendar_binding_missing_or_invalid")
        else:
            assert isinstance(calendar_binding, VerifiedCalendarBinding)
            if fetch.effective_time_evidence_hash != calendar_binding.manifest_sha256:
                reasons.add("calendar_binding_mismatch")
            if resolved_exchange is None or calendar_binding.exchange != resolved_exchange:
                reasons.add("calendar_exchange_mismatch")

    if not _nonempty_text(fetch.refresh_generation):
        reasons.add("refresh_generation_missing")
    if not _nonempty_text(fetch.parser_id):
        reasons.add("parser_id_missing")
    if not _nonempty_text(fetch.parser_version):
        reasons.add("parser_version_missing")

    status: Literal["verified", "rejected"] = "verified" if not reasons else "rejected"
    return EvidenceVerification(
        status,
        content_sha256,
        tuple(sorted(reasons)),
        fetch.effective_at_utc if status == "verified" else None,
    )


__all__ = [
    "EvidenceVerification",
    "OfficialFetch",
    "OfficialRequest",
    "OfficialSnapshotRef",
    "SourcePolicy",
    "VerifiedCalendarBinding",
    "verify_official_fetch",
]
