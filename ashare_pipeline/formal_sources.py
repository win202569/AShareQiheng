"""Injected, signed official-source collection boundary for Formal V3.

This module deliberately contains no production endpoint, parser, or network
client.  Callers supply a signed registry, an injected transport, and an
injected document parser for every collection attempt.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Literal, Protocol
import uuid
import weakref

from .formal_range_format import RangeConfig, parse_range_entry
from .formal_evidence import (
    EvidenceVerification,
    OfficialFetch,
    OfficialRequest,
    OfficialSnapshotRef,
    SourcePolicy,
    VerifiedCalendarBinding,
    verify_official_fetch,
)
from .formal_time import FORMAL_FREEZE_AT_CN, resolve_effective_at


_SOURCES = frozenset({"cninfo", "sse", "szse", "bse", "csrc"})
_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_SECURITY_ID = re.compile(r"^(?:SH|SZ|BJ)[0-9]{6}$")
_VERSION_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATE_ONLY_ANCHOR = re.compile(r"^\d{4}-\d{2}-\d{2}T00:00:00\+00:00$")
_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
_UNRESERVED = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_CONFIG_KEYS = frozenset(
    {
        "source",
        "dataset",
        "endpoint_url",
        "http_method",
        "parser_id",
        "parser_version",
        "mapping_version",
        "request_template",
        "timeout_seconds",
        "retry_base_seconds",
        "retry_max_attempts",
        "challenge_cooldown_seconds",
        "exchange_scope",
        "calendar_selector",
        "bootstrap_calendar",
    }
)
_SELECTOR_KEYS = frozenset({"context_kind", "scope_key", "exchange", "as_of_rule"})


class FormalSourceError(RuntimeError):
    """Base class for a source-boundary failure."""


class FormalRetryableSourceError(FormalSourceError):
    """A collection failure that a worker may retry later."""


class FormalSourceBlocked(FormalRetryableSourceError):
    """Access control or a challenge page blocked collection."""


class FormalTerminalSourceError(FormalSourceError):
    """A signed-config, identity, or document failure that must not retry."""


@dataclass(frozen=True)
class TransportRequest:
    method: Literal["GET", "POST"]
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout_seconds: float


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    original_url: str
    headers: Mapping[str, str]
    raw_bytes: bytes
    captured_at_utc: str


class OfficialTransport(Protocol):
    def send(self, request: TransportRequest) -> TransportResponse: ...


class RegistrySignatureVerifier(Protocol):
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool: ...


class EffectiveTimeResolver(Protocol):
    def next_exchange_close(
        self,
        *,
        exchange: str,
        disclosure_date_cn: str,
        calendar_binding: VerifiedCalendarBinding,
    ) -> str: ...


class _DuplicateJsonKey(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON value {value!r}")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _load_canonical_object(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not bytes:
        raise ValueError(f"{label} must be UTF-8 bytes")
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} must be UTF-8") from error
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateJsonKey as error:
        raise ValueError(f"{label} has duplicate JSON keys") from error
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be valid JSON") from error
    if type(parsed) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    try:
        canonical = _canonical_json_bytes(parsed)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must contain only canonical JSON values") from error
    if canonical != value:
        raise ValueError(f"{label} must be canonical JSON")
    return parsed


def _require_trimmed_text(value: object, label: str, *, identifier: bool = False) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an already-trimmed nonempty string")
    if identifier and _VERSION_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a version identifier")
    return value


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _require_aware_timestamp(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an aware timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be an aware timestamp")
    return value


def _require_canonical_uuid(value: object, label: str) -> str:
    text = _require_trimmed_text(value, label)
    try:
        parsed = uuid.UUID(text)
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError(f"{label} must be a canonical UUID") from error
    if str(parsed) != text:
        raise ValueError(f"{label} must be a canonical UUID")
    return text


def _verify_signature(
    payload: bytes,
    signature: object,
    key_id: object,
    verifier: object,
    *,
    label: str,
) -> tuple[str, str]:
    signature_text = _require_trimmed_text(signature, f"{label} signature")
    key_text = _require_trimmed_text(key_id, f"{label} key_id", identifier=True)
    verify = getattr(verifier, "verify", None)
    if not callable(verify):
        raise ValueError(f"{label} signature verifier is invalid")
    try:
        verified = verify(payload, signature=signature_text, key_id=key_text)
    except Exception as error:
        raise ValueError(f"{label} signature verification failed") from error
    if verified is not True:
        raise ValueError(f"{label} signature verification failed")
    return signature_text, key_text


def _https_host(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an absolute HTTPS URL")
    if any(
        ord(character) <= 0x20 or ord(character) == 0x7F or character.isspace()
        for character in value
    ):
        raise ValueError(f"{label} contains forbidden whitespace or control characters")
    if not value[:8].lower() == "https://":
        raise ValueError(f"{label} must be an absolute HTTPS URL")
    remainder = value[8:]
    if not remainder or "#" in remainder:
        raise ValueError(f"{label} must be an absolute HTTPS URL without a fragment")
    authority = remainder.split("/", 1)[0].split("?", 1)[0]
    if not authority or "@" in authority:
        raise ValueError(f"{label} has forbidden URL credentials")
    if authority.startswith("[") or authority.count(":") > 1:
        raise ValueError(f"{label} hostname is invalid")
    host, separator, port = authority.partition(":")
    if not host or any(character.isspace() for character in host):
        raise ValueError(f"{label} hostname is invalid")
    if separator and (not port or not port.isascii() or not port.isdecimal()):
        raise ValueError(f"{label} port is invalid")
    return host.lower()


def _require_source(value: object, label: str = "source") -> str:
    source = _require_trimmed_text(value, label, identifier=True)
    if source not in _SOURCES:
        raise ValueError(f"{label} is not an eligible official source")
    return source


def _require_exchange(value: object, label: str) -> Literal["SH", "SZ", "BJ"]:
    if type(value) is not str or value not in _EXCHANGES:
        raise ValueError(f"{label} must be SH, SZ, or BJ")
    return value


def _freeze_template(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_template(item) for key, item in value.items()})
    if type(value) is list or type(value) is tuple:
        return tuple(_freeze_template(item) for item in value)
    return value


def _validate_placeholders(value: object, label: str, *, nonempty: bool = False) -> str:
    if type(value) is not str or value != value.strip() or (nonempty and not value):
        raise ValueError(f"{label} must be an already-trimmed string")
    remaining = _PLACEHOLDER.sub("", value)
    if "{" in remaining or "}" in remaining:
        raise ValueError(f"{label} has an invalid placeholder")
    for match in _PLACEHOLDER.finditer(value):
        if match.group(1) not in {"security_id", "period_or_date", "exchange"}:
            raise ValueError(f"{label} has an unknown placeholder")
    return value


def _has_forbidden_raw_control(value: str, *, whitespace: bool) -> bool:
    return any(
        ord(character) < 0x20
        or ord(character) == 0x7F
        or (whitespace and character.isspace())
        for character in value
    )


def _validate_static_template_key(value: object, label: str, *, header: bool) -> str:
    key = _validate_placeholders(value, label, nonempty=True)
    if _PLACEHOLDER.search(key) is not None:
        raise ValueError(f"{label} must be static and cannot contain placeholders")
    if _has_forbidden_raw_control(key, whitespace=True):
        raise ValueError(f"{label} contains forbidden whitespace or control characters")
    if header and re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", key) is None:
        raise ValueError(f"{label} must be a static HTTP field name")
    return key


def _validate_query_template_value(value: object, label: str) -> str:
    item = _validate_placeholders(value, label)
    if _has_forbidden_raw_control(item, whitespace=True):
        raise ValueError(f"{label} contains forbidden whitespace or control characters")
    if "&" in item or "#" in item:
        raise ValueError(f"{label} contains an unsafe raw query delimiter")
    return item


def _validate_header_template_value(value: object, label: str) -> str:
    item = _validate_placeholders(value, label)
    if _has_forbidden_raw_control(item, whitespace=False):
        raise ValueError(f"{label} contains forbidden control characters")
    return item


def _validate_body_template(value: object, label: str) -> None:
    if value is None:
        return
    if type(value) is str:
        _validate_placeholders(value, label)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_placeholders(key, f"{label} key", nonempty=True)
            _validate_body_template(item, label)
        return
    if type(value) is list or type(value) is tuple:
        for item in value:
            _validate_body_template(item, label)
        return
    raise ValueError(f"{label} must be a JSON-like mapping/list/string/null tree")


def _validate_request_template(value: object, method: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != {"query", "headers", "body"}:
        raise ValueError("request_template must contain exactly query, headers, and body")
    query = value["query"]
    headers = value["headers"]
    if not isinstance(query, Mapping) or not isinstance(headers, Mapping):
        raise ValueError("request_template query and headers must be mappings")
    for key, item in query.items():
        _validate_static_template_key(key, "request_template query key", header=False)
        _validate_query_template_value(item, "request_template query value")
    for key, item in headers.items():
        _validate_static_template_key(key, "request_template header key", header=True)
        _validate_header_template_value(item, "request_template header value")
    _validate_body_template(value["body"], "request_template body")
    if method == "GET" and value["body"] is not None:
        raise ValueError("GET request_template body must be null")
    return value


@dataclass(frozen=True)
class CalendarSelector:
    context_kind: Literal["trading_calendar"]
    scope_key: str
    exchange: Literal["SH", "SZ", "BJ"]
    as_of_rule: Literal["visible_at_freeze"]

    def __post_init__(self) -> None:
        if type(self.context_kind) is not str or self.context_kind != "trading_calendar":
            raise ValueError("calendar selector context_kind must be trading_calendar")
        _require_trimmed_text(self.scope_key, "calendar selector scope_key", identifier=True)
        _require_exchange(self.exchange, "calendar selector exchange")
        if type(self.as_of_rule) is not str or self.as_of_rule != "visible_at_freeze":
            raise ValueError("calendar selector as_of_rule must be visible_at_freeze")

    @property
    def selector_hash(self) -> str:
        return hashlib.sha256(
            _canonical_json_bytes(
                {
                    "as_of_rule": self.as_of_rule,
                    "context_kind": self.context_kind,
                    "exchange": self.exchange,
                    "scope_key": self.scope_key,
                }
            )
        ).hexdigest()


@dataclass(frozen=True)
class SourceAdapterConfig:
    source: str
    dataset: str
    endpoint_url: str
    http_method: Literal["GET", "POST"]
    parser_id: str
    parser_version: str
    mapping_version: str
    request_template: Mapping[str, object]
    timeout_seconds: float
    retry_base_seconds: float
    retry_max_attempts: int
    challenge_cooldown_seconds: float
    registry_hash: str
    exchange_scope: Literal["SH", "SZ", "BJ"] | None
    calendar_selector: CalendarSelector | None
    bootstrap_calendar: bool = False

    def __post_init__(self) -> None:
        _require_source(self.source)
        _require_trimmed_text(self.dataset, "dataset", identifier=True)
        _https_host(self.endpoint_url, "endpoint_url")
        if type(self.http_method) is not str or self.http_method not in {"GET", "POST"}:
            raise ValueError("http_method must be GET or POST")
        _require_trimmed_text(self.parser_id, "parser_id", identifier=True)
        _require_trimmed_text(self.parser_version, "parser_version", identifier=True)
        _require_trimmed_text(self.mapping_version, "mapping_version", identifier=True)
        _validate_request_template(self.request_template, self.http_method)
        for label, value in (
            ("timeout_seconds", self.timeout_seconds),
            ("retry_base_seconds", self.retry_base_seconds),
            ("challenge_cooldown_seconds", self.challenge_cooldown_seconds),
        ):
            if type(value) not in {int, float} or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} must be a positive finite number")
        if type(self.retry_max_attempts) is not int or self.retry_max_attempts <= 0:
            raise ValueError("retry_max_attempts must be a positive integer")
        _require_sha256(self.registry_hash, "registry_hash")
        if self.exchange_scope is not None:
            _require_exchange(self.exchange_scope, "exchange_scope")
        if self.calendar_selector is not None and type(self.calendar_selector) is not CalendarSelector:
            raise ValueError("calendar_selector must have exact type CalendarSelector or be null")
        if type(self.bootstrap_calendar) is not bool:
            raise ValueError("bootstrap_calendar must be a boolean")
        if self.bootstrap_calendar:
            if (
                self.dataset != "trading_calendar"
                or self.calendar_selector is not None
                or self.exchange_scope is not None
            ):
                raise ValueError("bootstrap calendar config must be an unbound trading_calendar")
        elif self.dataset == "trading_calendar" and self.calendar_selector is None:
            raise ValueError("non-bootstrap trading_calendar config requires calendar_selector")
        if self.calendar_selector is not None and self.exchange_scope is not None:
            if self.calendar_selector.exchange != self.exchange_scope:
                raise ValueError("calendar selector exchange must match exchange_scope")
        if self.dataset == "universe_listing" and self.exchange_scope is None:
            raise ValueError("universe_listing config requires one exchange_scope")
        object.__setattr__(self, "request_template", _freeze_template(self.request_template))


def _freeze_document_value(value: object) -> object:
    """Freeze only exact JSON-shaped parser row values into detached containers."""

    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("parser document row mapping keys must be exact strings")
            if key in copied:
                raise ValueError("parser document row mapping has duplicate keys")
            copied[key] = _freeze_document_value(item)
        return MappingProxyType(copied)
    if type(value) in {tuple, list}:
        return tuple(_freeze_document_value(item) for item in value)
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("parser document row contains an unsupported value")


@dataclass(frozen=True)
class ParsedOfficialDocument:
    parser_id: str
    parser_version: str
    declared_security_id: str | None
    declared_period: str | None
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    source_updated_at_utc: str | None
    rows: tuple[Mapping[str, object], ...]
    accounting_basis: str
    bootstrap_calendar: bool = False

    def __post_init__(self) -> None:
        _require_trimmed_text(self.parser_id, "document parser_id", identifier=True)
        _require_trimmed_text(self.parser_version, "document parser_version", identifier=True)
        if self.declared_security_id is not None:
            if type(self.declared_security_id) is not str or _SECURITY_ID.fullmatch(self.declared_security_id) is None:
                raise ValueError("document declared_security_id must be canonical or null")
        if self.declared_period is not None:
            _require_trimmed_text(self.declared_period, "document declared_period")
        if type(self.published_precision) is not str or self.published_precision not in {
            "timestamp",
            "date_only",
        }:
            raise ValueError("document published_precision is invalid")
        if self.published_precision == "timestamp":
            _require_aware_timestamp(self.published_at_utc, "document published_at_utc")
        else:
            _require_date_only_anchor(self.published_at_utc)
        if self.source_updated_at_utc is not None:
            _require_aware_timestamp(self.source_updated_at_utc, "document source_updated_at_utc")
        if type(self.rows) is not tuple or any(not isinstance(row, Mapping) for row in self.rows):
            raise ValueError("document rows must be a tuple of mappings")
        _require_trimmed_text(self.accounting_basis, "document accounting_basis")
        if type(self.bootstrap_calendar) is not bool:
            raise ValueError("document bootstrap_calendar must be a boolean")


class OfficialDocumentParser(Protocol):
    def parse(
        self, raw_bytes: bytes, *, request: OfficialRequest, config: SourceAdapterConfig
    ) -> ParsedOfficialDocument: ...


def _copy_verified_document(document: object) -> ParsedOfficialDocument:
    if type(document) is not ParsedOfficialDocument:
        raise FormalTerminalSourceError("parser must return exact ParsedOfficialDocument")
    try:
        parser_id = document.parser_id
        parser_version = document.parser_version
        declared_security_id = document.declared_security_id
        declared_period = document.declared_period
        published_at_utc = document.published_at_utc
        published_precision = document.published_precision
        source_updated_at_utc = document.source_updated_at_utc
        rows = document.rows
        accounting_basis = document.accounting_basis
        bootstrap_calendar = document.bootstrap_calendar
        if type(rows) is not tuple or any(not isinstance(row, Mapping) for row in rows):
            raise ValueError("parser document rows are invalid")
        frozen_rows = tuple(_freeze_document_value(row) for row in rows)
        return ParsedOfficialDocument(
            parser_id=parser_id,
            parser_version=parser_version,
            declared_security_id=declared_security_id,
            declared_period=declared_period,
            published_at_utc=published_at_utc,
            published_precision=published_precision,
            source_updated_at_utc=source_updated_at_utc,
            rows=frozen_rows,
            accounting_basis=accounting_basis,
            bootstrap_calendar=bootstrap_calendar,
        )
    except Exception as error:
        raise FormalTerminalSourceError("parser document cannot be detached") from error


def _require_date_only_anchor(value: object) -> str:
    if type(value) is not str or _DATE_ONLY_ANCHOR.fullmatch(value) is None:
        raise ValueError("date_only publication must be the canonical UTC day anchor")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("date_only publication must be the canonical UTC day anchor") from error
    return value


def _selector_from_wire(value: object) -> CalendarSelector | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != _SELECTOR_KEYS:
        raise ValueError("calendar_selector has invalid keys")
    return CalendarSelector(
        context_kind=value["context_kind"],
        scope_key=value["scope_key"],
        exchange=value["exchange"],
        as_of_rule=value["as_of_rule"],
    )


def _make_signed_source_registry_type() -> type[object]:
    """Build the trusted registry type with its construction state in a closure.

    A source registry is an executable authorization boundary: merely copying
    its public dataclass fields must not make an object trusted.  The weak
    identity map below is deliberately unreachable as a module attribute and
    additionally seals every public field that an adapter may consume.
    """

    registry_fields = (
        "canonical_json",
        "registry_hash",
        "signature",
        "key_id",
    )
    config_fields = (
        "source",
        "dataset",
        "endpoint_url",
        "http_method",
        "parser_id",
        "parser_version",
        "mapping_version",
        "request_template",
        "timeout_seconds",
        "retry_base_seconds",
        "retry_max_attempts",
        "challenge_cooldown_seconds",
        "registry_hash",
        "exchange_scope",
        "calendar_selector",
        "bootstrap_calendar",
    )
    range_config_type = RangeConfig
    parse_range_config = parse_range_entry
    range_config_fields = (
        "schema_version",
        "capability",
        "kind",
        "anchor_descriptor_id",
        "calendar_descriptor_id",
        "source",
        "dataset",
        "endpoint_url",
        "http_method",
        "parser_id",
        "parser_version",
        "mapping_version",
        "normalizer_version",
        "request_version",
        "exchange_scope",
        "calendar_anchor_selector",
        "request_template",
        "pagination",
        "max_pages",
        "max_calendar_days_per_request",
        "timeout_seconds",
        "retry_base_seconds",
        "retry_max_attempts",
        "challenge_cooldown_seconds",
    )

    @dataclass(frozen=True)
    class _RegistryRecord:
        reference: weakref.ReferenceType[object]
        registry_fingerprint: tuple[object, ...]
        configs: tuple[SourceAdapterConfig, ...]
        configs_fingerprint: tuple[object, ...]
        range_configs: tuple[RangeConfig, ...]
        range_configs_fingerprint: tuple[object, ...]
        canonical_json: bytes
        registry_hash: str
        signature: str
        key_id: str

    verified_registries: dict[int, _RegistryRecord] = {}

    def configs_from_canonical(
        canonical_json: bytes, registry_hash: str
    ) -> tuple[tuple[SourceAdapterConfig, ...], tuple[RangeConfig, ...]]:
        wire = _load_canonical_object(canonical_json, label="source registry")
        version = wire.get("schema_version")
        expected_keys = (
            {"configs", "registry_role", "schema_version"}
            if version == "formal-source-registry-v1"
            else {"configs", "range_configs", "registry_role", "schema_version"}
            if version == "formal-source-registry-v2"
            else None
        )
        if expected_keys is None or set(wire) != expected_keys:
            raise ValueError("source registry has unknown or missing keys")
        if wire["registry_role"] != "source":
            raise ValueError("source registry role must be source")
        if type(wire["configs"]) is not list:
            raise ValueError("source registry configs must be a list")
        configs: list[SourceAdapterConfig] = []
        identities: set[tuple[str, str, str | None]] = set()
        for item in wire["configs"]:
            if type(item) is not dict or set(item) != _CONFIG_KEYS:
                raise ValueError("source registry config has unknown or missing keys")
            config = SourceAdapterConfig(
                source=item["source"],
                dataset=item["dataset"],
                endpoint_url=item["endpoint_url"],
                http_method=item["http_method"],
                parser_id=item["parser_id"],
                parser_version=item["parser_version"],
                mapping_version=item["mapping_version"],
                request_template=item["request_template"],
                timeout_seconds=item["timeout_seconds"],
                retry_base_seconds=item["retry_base_seconds"],
                retry_max_attempts=item["retry_max_attempts"],
                challenge_cooldown_seconds=item["challenge_cooldown_seconds"],
                registry_hash=registry_hash,
                exchange_scope=item["exchange_scope"],
                calendar_selector=_selector_from_wire(item["calendar_selector"]),
                bootstrap_calendar=item["bootstrap_calendar"],
            )
            identity = (config.source, config.dataset, config.exchange_scope)
            if identity in identities:
                raise ValueError("source registry has duplicate config identity")
            identities.add(identity)
            configs.append(config)
        range_configs: list[RangeConfig] = []
        range_identities: set[tuple[str, str, str, str, str]] = set()
        if version == "formal-source-registry-v2":
            if type(wire["range_configs"]) is not list:
                raise ValueError("source registry range_configs must be a list")
            for item in wire["range_configs"]:
                config = parse_range_config(item)
                if type(config) is not range_config_type:
                    raise ValueError("range parser returned an unexpected config type")
                identity = (
                    config.kind,
                    config.capability,
                    config.anchor_descriptor_id,
                    config.calendar_descriptor_id,
                    config.exchange_scope,
                )
                if identity in range_identities:
                    raise ValueError("source registry has duplicate range config identity")
                range_identities.add(identity)
                range_configs.append(config)
        return tuple(configs), tuple(range_configs)

    def value_fingerprint(value: object) -> object:
        """Preserve type, order, and nesting so mutation is never normalized away."""

        if type(value) is CalendarSelector:
            return (
                "CalendarSelector",
                value.context_kind,
                value.scope_key,
                value.exchange,
                value.as_of_rule,
            )
        if isinstance(value, Mapping):
            return (
                "Mapping",
                type(value).__module__,
                type(value).__qualname__,
                tuple(
                    (value_fingerprint(key), value_fingerprint(item))
                    for key, item in value.items()
                ),
            )
        if type(value) is tuple or type(value) is list:
            return (type(value).__name__, tuple(value_fingerprint(item) for item in value))
        if type(value) in {str, int, float, bool, bytes, type(None)}:
            return (type(value).__name__, value)
        return ("unexpected", type(value).__module__, type(value).__qualname__, id(value))

    def config_fingerprint(config: object) -> tuple[object, ...]:
        if type(config) is not SourceAdapterConfig:
            return ("invalid-config", type(config).__module__, type(config).__qualname__)
        return tuple(
            (field, value_fingerprint(getattr(config, field, object()))) for field in config_fields
        )

    def range_config_fingerprint(config: object) -> tuple[object, ...]:
        if type(config) is not range_config_type:
            raise ValueError("exact RangeConfig required for source fingerprint")
        return tuple(
            (field, value_fingerprint(object.__getattribute__(config, field)))
            for field in range_config_fields
        )

    def registry_fingerprint(registry: object) -> tuple[object, ...]:
        return tuple(
            (field, value_fingerprint(getattr(registry, field, object()))) for field in registry_fields
        )

    def configs_fingerprint(configs: object) -> tuple[object, ...]:
        if type(configs) is not tuple:
            return ("invalid-configs", type(configs).__module__, type(configs).__qualname__)
        return tuple(config_fingerprint(config) for config in configs)

    def range_configs_fingerprint(configs: object) -> tuple[object, ...]:
        if type(configs) is not tuple:
            raise ValueError("range configs must be an exact tuple")
        return tuple(range_config_fingerprint(config) for config in configs)

    def remember_verified(registry: object) -> None:
        identity = id(registry)

        def discard(reference: weakref.ReferenceType[object], *, identity: int = identity) -> None:
            record = verified_registries.get(identity)
            if record is not None and record.reference is reference:
                verified_registries.pop(identity, None)

        reference = weakref.ref(registry, discard)
        configs = getattr(registry, "configs")
        range_configs = getattr(registry, "range_configs")
        assert type(configs) is tuple
        assert type(range_configs) is tuple
        verified_registries[identity] = _RegistryRecord(
            reference,
            registry_fingerprint(registry),
            configs,
            configs_fingerprint(configs),
            range_configs,
            range_configs_fingerprint(range_configs),
            getattr(registry, "canonical_json"),
            getattr(registry, "registry_hash"),
            getattr(registry, "signature"),
            getattr(registry, "key_id"),
        )

    def verified_record(registry: object) -> _RegistryRecord:
        record = verified_registries.get(id(registry))
        if not (
            record is not None
            and record.reference() is registry
            and getattr(registry, "configs", None) is record.configs
            and getattr(registry, "range_configs", None) is record.range_configs
            and registry_fingerprint(registry) == record.registry_fingerprint
            and configs_fingerprint(getattr(registry, "configs", None)) == record.configs_fingerprint
            and range_configs_fingerprint(getattr(registry, "range_configs", None))
            == record.range_configs_fingerprint
        ):
            raise ValueError("signed source registry was not verified by from_signed_bytes")
        return record

    def is_verified(registry: object) -> bool:
        try:
            verified_record(registry)
        except ValueError:
            return False
        return True

    def trusted_config_snapshots(registry: object) -> tuple[SourceAdapterConfig, ...]:
        record = verified_record(registry)
        return configs_from_canonical(record.canonical_json, record.registry_hash)[0]

    def trusted_range_config_snapshots(registry: object) -> tuple[RangeConfig, ...]:
        record = verified_record(registry)
        return configs_from_canonical(record.canonical_json, record.registry_hash)[1]

    def trusted_config_snapshot(
        registry: object, request: OfficialRequest
    ) -> SourceAdapterConfig:
        _, exchange = _validate_request(request)
        matching = [
            config
            for config in trusted_config_snapshots(registry)
            if config.source == request.source and config.dataset == request.dataset
        ]
        if exchange is None:
            matching = [config for config in matching if config.exchange_scope is None]
        else:
            matching = [
                config
                for config in matching
                if config.exchange_scope is None or config.exchange_scope == exchange
            ]
        if len(matching) != 1:
            raise FormalTerminalSourceError("signed source config is absent or ambiguous")
        return matching[0]

    @dataclass(frozen=True, init=False)
    class SignedSourceRegistry:
        """A canonical, verifier-approved source registry with no default configs."""

        canonical_json: bytes
        registry_hash: str
        signature: str
        key_id: str
        configs: tuple[SourceAdapterConfig, ...]
        range_configs: tuple[RangeConfig, ...]

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise ValueError("SignedSourceRegistry must be loaded with from_signed_bytes")

        def _require_verified(self) -> None:
            if not is_verified(self):
                raise ValueError("signed source registry was not verified by from_signed_bytes")

        @staticmethod
        def _trusted_config_snapshots(registry: object) -> tuple[SourceAdapterConfig, ...]:
            return trusted_config_snapshots(registry)

        @staticmethod
        def _trusted_range_config_snapshots(registry: object) -> tuple[RangeConfig, ...]:
            return trusted_range_config_snapshots(registry)

        @staticmethod
        def _trusted_config_snapshot(
            registry: object, request: OfficialRequest
        ) -> SourceAdapterConfig:
            return trusted_config_snapshot(registry, request)

        @classmethod
        def from_signed_bytes(
            cls,
            registry_bytes: bytes,
            signature: str,
            key_id: str,
            verifier: RegistrySignatureVerifier,
        ) -> "SignedSourceRegistry":
            if cls is not SignedSourceRegistry:
                raise ValueError("SignedSourceRegistry must have exact type")
            signature_text, key_text = _verify_signature(
                registry_bytes, signature, key_id, verifier, label="source registry"
            )
            registry_hash = hashlib.sha256(registry_bytes).hexdigest()
            configs, range_configs = configs_from_canonical(registry_bytes, registry_hash)
            registry = object.__new__(SignedSourceRegistry)
            object.__setattr__(registry, "canonical_json", registry_bytes)
            object.__setattr__(registry, "registry_hash", registry_hash)
            object.__setattr__(registry, "signature", signature_text)
            object.__setattr__(registry, "key_id", key_text)
            object.__setattr__(registry, "configs", configs)
            object.__setattr__(registry, "range_configs", range_configs)
            remember_verified(registry)
            return registry

        def select(self, request: OfficialRequest) -> SourceAdapterConfig:
            return trusted_config_snapshot(self, request)

    return SignedSourceRegistry


SignedSourceRegistry = _make_signed_source_registry_type()
del _make_signed_source_registry_type


def _validate_request(request: object) -> tuple[OfficialRequest, str | None]:
    if type(request) is not OfficialRequest:
        raise FormalTerminalSourceError("request must have exact type OfficialRequest")
    try:
        _require_source(request.source, "request source")
        _require_trimmed_text(request.dataset, "request dataset", identifier=True)
    except ValueError as error:
        raise FormalTerminalSourceError(str(error)) from error
    security_exchange: str | None = None
    if request.security_id is not None:
        if type(request.security_id) is not str or _SECURITY_ID.fullmatch(request.security_id) is None:
            raise FormalTerminalSourceError("request security_id must be canonical or null")
        security_exchange = request.security_id[:2]
    if request.period_or_date is not None:
        try:
            _require_trimmed_text(request.period_or_date, "request period_or_date")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
    exchange: str | None = None
    if request.exchange is not None:
        try:
            exchange = _require_exchange(request.exchange, "request exchange")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
    if exchange is not None and security_exchange is not None and exchange != security_exchange:
        raise FormalTerminalSourceError("request security_id and exchange disagree")
    return request, exchange or security_exchange


def _substitute_text(value: str, values: Mapping[str, str | None], *, percent_encode: bool) -> str:
    result: list[str] = []
    position = 0
    for match in _PLACEHOLDER.finditer(value):
        result.append(value[position : match.start()])
        name = match.group(1)
        replacement = values[name]
        if replacement is None:
            raise FormalTerminalSourceError(f"request template placeholder {name} has a null value")
        result.append(_percent_encode(replacement) if percent_encode else replacement)
        position = match.end()
    result.append(value[position:])
    return "".join(result)


def _percent_encode(value: str) -> str:
    output: list[str] = []
    for byte in value.encode("utf-8"):
        if byte in _UNRESERVED:
            output.append(chr(byte))
        else:
            output.append(f"%{byte:02X}")
    return "".join(output)


def _substitute_body(value: object, values: Mapping[str, str | None]) -> object:
    if value is None:
        return None
    if type(value) is str:
        return _substitute_text(value, values, percent_encode=False)
    if isinstance(value, Mapping):
        return {
            _substitute_text(key, values, percent_encode=False): _substitute_body(item, values)
            for key, item in value.items()
        }
    if type(value) is tuple or type(value) is list:
        return [_substitute_body(item, values) for item in value]
    raise FormalTerminalSourceError("signed request body template is invalid")


def _build_transport_request(
    config: SourceAdapterConfig, request: OfficialRequest, resolved_exchange: str | None
) -> TransportRequest:
    values: Mapping[str, str | None] = {
        "security_id": request.security_id,
        "period_or_date": request.period_or_date,
        "exchange": resolved_exchange,
    }
    query = config.request_template["query"]
    headers = config.request_template["headers"]
    assert isinstance(query, Mapping) and isinstance(headers, Mapping)
    query_pairs = [
        f"{_percent_encode(key)}={_substitute_text(value, values, percent_encode=True)}"
        for key, value in sorted(query.items())
    ]
    if query_pairs:
        if "?" not in config.endpoint_url:
            query_prefix = "?"
        elif config.endpoint_url.endswith(("?", "&")):
            query_prefix = ""
        else:
            query_prefix = "&"
        url = config.endpoint_url + query_prefix + "&".join(query_pairs)
    else:
        url = config.endpoint_url
    try:
        _https_host(url, "constructed transport URL")
    except ValueError as error:
        raise FormalTerminalSourceError(str(error)) from error
    sent_headers = {
        key: _substitute_text(value, values, percent_encode=False) for key, value in headers.items()
    }
    if any(
        _has_forbidden_raw_control(key, whitespace=True)
        or _has_forbidden_raw_control(value, whitespace=False)
        for key, value in sent_headers.items()
    ):
        raise FormalTerminalSourceError("request template header contains forbidden control characters")
    body_value = _substitute_body(config.request_template["body"], values)
    body = None if body_value is None else _canonical_json_bytes(body_value)
    if config.http_method == "GET" and body is not None:
        raise FormalTerminalSourceError("GET request body is forbidden")
    return TransportRequest(config.http_method, url, MappingProxyType(sent_headers), body, float(config.timeout_seconds))


def _copy_template(value: object) -> object:
    if isinstance(value, Mapping):
        return {_copy_template(key): _copy_template(item) for key, item in value.items()}
    if type(value) is tuple or type(value) is list:
        return [_copy_template(item) for item in value]
    return value


def _copy_config(config: SourceAdapterConfig) -> SourceAdapterConfig:
    selector = config.calendar_selector
    selector_copy = (
        None
        if selector is None
        else CalendarSelector(
            selector.context_kind,
            selector.scope_key,
            selector.exchange,
            selector.as_of_rule,
        )
    )
    return SourceAdapterConfig(
        source=config.source,
        dataset=config.dataset,
        endpoint_url=config.endpoint_url,
        http_method=config.http_method,
        parser_id=config.parser_id,
        parser_version=config.parser_version,
        mapping_version=config.mapping_version,
        request_template=_copy_template(config.request_template),
        timeout_seconds=config.timeout_seconds,
        retry_base_seconds=config.retry_base_seconds,
        retry_max_attempts=config.retry_max_attempts,
        challenge_cooldown_seconds=config.challenge_cooldown_seconds,
        registry_hash=config.registry_hash,
        exchange_scope=config.exchange_scope,
        calendar_selector=selector_copy,
        bootstrap_calendar=config.bootstrap_calendar,
    )


def _copy_request(request: OfficialRequest) -> OfficialRequest:
    return OfficialRequest(
        request.source,
        request.dataset,
        request.security_id,
        request.period_or_date,
        request.exchange,
    )


def _copy_calendar_binding(binding: VerifiedCalendarBinding) -> VerifiedCalendarBinding:
    return VerifiedCalendarBinding(
        snapshot_id=binding.snapshot_id,
        manifest_sha256=binding.manifest_sha256,
        exchange=binding.exchange,
        freeze_at_utc=binding.freeze_at_utc,
        registry_manifest_hash=binding.registry_manifest_hash,
        selector_hash=binding.selector_hash,
        prerequisite_task_id=binding.prerequisite_task_id,
    )


def _require_snapshot_path(value: object, label: str) -> str:
    path = _require_trimmed_text(value, label)
    if _has_forbidden_raw_control(path, whitespace=False):
        raise ValueError(f"{label} contains forbidden control characters")
    return path


def _require_optional_aware_timestamp(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_aware_timestamp(value, label)


def _copy_snapshot_ref(snapshot_ref: OfficialSnapshotRef) -> OfficialSnapshotRef:
    """Validate and detach every replay reference value before policy or parser callbacks."""

    if type(snapshot_ref) is not OfficialSnapshotRef:
        raise ValueError("snapshot_ref must have exact type OfficialSnapshotRef")
    (
        raw_snapshot_id,
        raw_source,
        raw_dataset,
        raw_request_fingerprint,
        raw_security_id,
        raw_period_or_date,
        raw_exchange,
        raw_content_sha256,
        raw_manifest_sha256,
        raw_content_path,
        raw_manifest_path,
        raw_original_url,
        raw_published_at_utc,
        raw_published_precision,
        raw_source_updated_at_utc,
        raw_captured_at_utc,
        raw_effective_at_utc,
        raw_effective_time_evidence_hash,
        raw_refresh_generation,
        raw_producing_task_id,
        raw_parser_id,
        raw_parser_version,
        raw_mapping_version,
        raw_verification_status,
    ) = (
        snapshot_ref.snapshot_id,
        snapshot_ref.source,
        snapshot_ref.dataset,
        snapshot_ref.request_fingerprint,
        snapshot_ref.security_id,
        snapshot_ref.period_or_date,
        snapshot_ref.exchange,
        snapshot_ref.content_sha256,
        snapshot_ref.manifest_sha256,
        snapshot_ref.content_path,
        snapshot_ref.manifest_path,
        snapshot_ref.original_url,
        snapshot_ref.published_at_utc,
        snapshot_ref.published_precision,
        snapshot_ref.source_updated_at_utc,
        snapshot_ref.captured_at_utc,
        snapshot_ref.effective_at_utc,
        snapshot_ref.effective_time_evidence_hash,
        snapshot_ref.refresh_generation,
        snapshot_ref.producing_task_id,
        snapshot_ref.parser_id,
        snapshot_ref.parser_version,
        snapshot_ref.mapping_version,
        snapshot_ref.verification_status,
    )
    snapshot_id = _require_trimmed_text(raw_snapshot_id, "snapshot snapshot_id")
    source = _require_source(raw_source, "snapshot source")
    dataset = _require_trimmed_text(raw_dataset, "snapshot dataset", identifier=True)
    request_fingerprint = _require_sha256(raw_request_fingerprint, "snapshot request_fingerprint")
    security_id: str | None = None
    if raw_security_id is not None:
        if type(raw_security_id) is not str or _SECURITY_ID.fullmatch(raw_security_id) is None:
            raise ValueError("snapshot security_id must be canonical or null")
        security_id = raw_security_id
    period_or_date: str | None = None
    if raw_period_or_date is not None:
        period_or_date = _require_trimmed_text(raw_period_or_date, "snapshot period_or_date")
    exchange: Literal["SH", "SZ", "BJ"] | None = None
    if raw_exchange is not None:
        exchange = _require_exchange(raw_exchange, "snapshot exchange")
    content_sha256 = _require_sha256(raw_content_sha256, "snapshot content_sha256")
    manifest_sha256 = _require_sha256(raw_manifest_sha256, "snapshot manifest_sha256")
    content_path = _require_snapshot_path(raw_content_path, "snapshot content_path")
    manifest_path = _require_snapshot_path(raw_manifest_path, "snapshot manifest_path")
    original_url = _require_trimmed_text(raw_original_url, "snapshot original_url")
    _https_host(original_url, "snapshot original_url")
    if type(raw_published_precision) is not str or raw_published_precision not in {
        "timestamp",
        "date_only",
    }:
        raise ValueError("snapshot published_precision is invalid")
    published_precision: Literal["timestamp", "date_only"] = raw_published_precision
    if published_precision == "timestamp":
        published_at_utc = _require_aware_timestamp(raw_published_at_utc, "snapshot published_at_utc")
    else:
        published_at_utc = _require_date_only_anchor(raw_published_at_utc)
    source_updated_at_utc = _require_optional_aware_timestamp(
        raw_source_updated_at_utc, "snapshot source_updated_at_utc"
    )
    captured_at_utc = _require_aware_timestamp(raw_captured_at_utc, "snapshot captured_at_utc")
    effective_at_utc = _require_aware_timestamp(raw_effective_at_utc, "snapshot effective_at_utc")
    if published_precision == "timestamp":
        if raw_effective_time_evidence_hash is not None:
            raise ValueError("timestamp snapshot cannot carry a calendar evidence hash")
        effective_time_evidence_hash: str | None = None
    else:
        effective_time_evidence_hash = _require_sha256(
            raw_effective_time_evidence_hash, "snapshot effective_time_evidence_hash"
        )
    refresh_generation = _require_trimmed_text(raw_refresh_generation, "snapshot refresh_generation")
    producing_task_id: str | None = None
    if raw_producing_task_id is not None:
        producing_task_id = _require_trimmed_text(raw_producing_task_id, "snapshot producing_task_id")
    parser_id = _require_trimmed_text(raw_parser_id, "snapshot parser_id", identifier=True)
    parser_version = _require_trimmed_text(raw_parser_version, "snapshot parser_version", identifier=True)
    mapping_version = _require_trimmed_text(raw_mapping_version, "snapshot mapping_version", identifier=True)
    if type(raw_verification_status) is not str or raw_verification_status != "verified":
        raise ValueError("snapshot verification_status must be verified")
    return OfficialSnapshotRef(
        snapshot_id=snapshot_id,
        source=source,
        dataset=dataset,
        request_fingerprint=request_fingerprint,
        security_id=security_id,
        period_or_date=period_or_date,
        exchange=exchange,
        content_sha256=content_sha256,
        manifest_sha256=manifest_sha256,
        content_path=content_path,
        manifest_path=manifest_path,
        original_url=original_url,
        published_at_utc=published_at_utc,
        published_precision=published_precision,
        source_updated_at_utc=source_updated_at_utc,
        captured_at_utc=captured_at_utc,
        effective_at_utc=effective_at_utc,
        effective_time_evidence_hash=effective_time_evidence_hash,
        refresh_generation=refresh_generation,
        producing_task_id=producing_task_id,
        parser_id=parser_id,
        parser_version=parser_version,
        mapping_version=mapping_version,
        verification_status="verified",
    )


@dataclass(frozen=True)
class _PolicySpec:
    source: str
    allowed_hosts: frozenset[str]


def _policy_specs_from_snapshot(
    snapshot: tuple[tuple[str, str, frozenset[str]], ...],
) -> Mapping[str, _PolicySpec]:
    return MappingProxyType(
        {
            source: _PolicySpec(policy_source, frozenset(allowed_hosts))
            for source, policy_source, allowed_hosts in snapshot
        }
    )


@dataclass(frozen=True)
class _OperationPlan:
    transport: OfficialTransport
    parser: OfficialDocumentParser
    effective_time_resolver: EffectiveTimeResolver
    request: OfficialRequest
    config: SourceAdapterConfig
    policy: SourcePolicy
    resolved_exchange: str | None
    calendar_binding: VerifiedCalendarBinding | None
    transport_request: TransportRequest
    refresh_generation: str


class FormalOfficialSourceAdapter:
    """Turns one signed config and injected response into verified formal evidence."""

    def __init__(
        self,
        *,
        transport: OfficialTransport,
        registry: SignedSourceRegistry,
        policies: Mapping[str, SourcePolicy],
        parsers: Mapping[str, OfficialDocumentParser],
        effective_time_resolver: EffectiveTimeResolver,
        source_registry_hash: str,
        registry_manifest_hash: str,
        freeze_at_utc: str = FORMAL_FREEZE_AT_CN,
    ) -> None:
        if type(registry) is not SignedSourceRegistry:
            raise ValueError("registry must have exact type SignedSourceRegistry")
        SignedSourceRegistry._require_verified(registry)
        if not callable(getattr(transport, "send", None)):
            raise ValueError("transport must implement send")
        if not isinstance(policies, Mapping) or not isinstance(parsers, Mapping):
            raise ValueError("policies and parsers must be mappings")
        if not callable(getattr(effective_time_resolver, "next_exchange_close", None)):
            raise ValueError("effective_time_resolver must implement next_exchange_close")
        _require_sha256(source_registry_hash, "source_registry_hash")
        _require_sha256(registry_manifest_hash, "registry_manifest_hash")
        if source_registry_hash != registry.registry_hash:
            raise ValueError("source_registry_hash does not match signed source registry")
        _require_aware_timestamp(freeze_at_utc, "freeze_at_utc")
        configs = SignedSourceRegistry._trusted_config_snapshots(registry)
        self._transport = transport
        self.registry = registry
        self._policies = MappingProxyType(dict(policies))
        self._parsers = MappingProxyType(dict(parsers))
        self._effective_time_resolver = effective_time_resolver
        self.source_registry_hash = source_registry_hash
        self.registry_manifest_hash = registry_manifest_hash
        self.freeze_at_utc = freeze_at_utc
        policy_specs: dict[str, _PolicySpec] = {}
        for config in configs:
            policy = FormalOfficialSourceAdapter._registered_policy(config, self._policies)
            policy_specs[config.source] = _PolicySpec(policy.source, frozenset(policy.allowed_hosts))
            FormalOfficialSourceAdapter._registered_parser(config, self._parsers)
        self._policy_specs = MappingProxyType(policy_specs)
        SignedSourceRegistry._require_verified(registry)

    @staticmethod
    def _registered_policy(
        config: SourceAdapterConfig, policies: Mapping[str, SourcePolicy]
    ) -> SourcePolicy:
        policy = policies.get(config.source)
        if type(policy) is not SourcePolicy or policy.source != config.source or not policy.is_authoritative:
            raise ValueError("signed source policy is absent or non-authoritative")
        try:
            host = _https_host(config.endpoint_url, "signed endpoint_url")
        except ValueError as error:
            raise ValueError(str(error)) from error
        if host not in policy.allowed_hosts:
            raise ValueError("signed endpoint host is not allowlisted by source policy")
        return policy

    @staticmethod
    def _registered_parser(
        config: SourceAdapterConfig, parsers: Mapping[str, OfficialDocumentParser]
    ) -> OfficialDocumentParser:
        parser = parsers.get(config.parser_id)
        if not callable(getattr(parser, "parse", None)):
            raise ValueError("signed parser is not registered")
        return parser

    @staticmethod
    def _policy_snapshot(
        config: SourceAdapterConfig, policy_specs: Mapping[str, _PolicySpec]
    ) -> SourcePolicy:
        spec = policy_specs.get(config.source)
        if type(spec) is not _PolicySpec:
            raise FormalTerminalSourceError("signed source policy is absent or non-authoritative")
        try:
            policy = SourcePolicy(spec.source, frozenset(spec.allowed_hosts))
            return FormalOfficialSourceAdapter._registered_policy(config, {config.source: policy})
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error

    @staticmethod
    def _resolve_calendar_binding(
        config: SourceAdapterConfig,
        resolved_exchange: str | None,
        calendar_binding: VerifiedCalendarBinding | None,
        *,
        freeze_at_utc: str,
        registry_manifest_hash: str,
    ) -> VerifiedCalendarBinding | None:
        if config.bootstrap_calendar:
            if calendar_binding is not None:
                raise FormalTerminalSourceError("bootstrap calendar config forbids a calendar binding")
            return None
        selector = config.calendar_selector
        if selector is None:
            if calendar_binding is not None:
                raise FormalTerminalSourceError("timestamp config forbids a calendar binding")
            if config.dataset == "trading_calendar":
                raise FormalTerminalSourceError("non-bootstrap trading_calendar config is unusable")
            return None
        if type(calendar_binding) is not VerifiedCalendarBinding:
            raise FormalTerminalSourceError("date_only config requires an exact verified calendar binding")
        if resolved_exchange is None or resolved_exchange != selector.exchange:
            raise FormalTerminalSourceError("date_only config does not resolve its signed exchange")
        binding = _copy_calendar_binding(calendar_binding)
        try:
            _require_trimmed_text(binding.snapshot_id, "calendar binding snapshot_id")
            _require_sha256(binding.manifest_sha256, "calendar binding manifest_sha256")
            _require_exchange(binding.exchange, "calendar binding exchange")
            _require_aware_timestamp(binding.freeze_at_utc, "calendar binding freeze_at_utc")
            _require_sha256(
                binding.registry_manifest_hash,
                "calendar binding registry_manifest_hash",
            )
            _require_sha256(binding.selector_hash, "calendar binding selector_hash")
            _require_canonical_uuid(binding.prerequisite_task_id, "calendar binding prerequisite_task_id")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        if binding.exchange != selector.exchange:
            raise FormalTerminalSourceError("calendar binding exchange does not match signed selector")
        if binding.freeze_at_utc != freeze_at_utc:
            raise FormalTerminalSourceError("calendar binding freeze does not match adapter freeze")
        if binding.registry_manifest_hash != registry_manifest_hash:
            raise FormalTerminalSourceError("calendar binding root does not match adapter root")
        if binding.selector_hash != selector.selector_hash:
            raise FormalTerminalSourceError("calendar binding selector does not match signed selector")
        return binding

    @staticmethod
    def _operation_record(adapter: object) -> object:
        try:
            return FormalOfficialSourceAdapter._trusted_operation_record(adapter)
        except (AttributeError, ValueError) as error:
            if "signed source registry" in str(error):
                raise FormalTerminalSourceError("signed source registry is not verified") from error
            raise FormalTerminalSourceError("formal source adapter was not verified") from error

    @staticmethod
    def _preflight(
        adapter: object,
        request: OfficialRequest,
        refresh_generation: str,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> _OperationPlan:
        record = FormalOfficialSourceAdapter._operation_record(adapter)
        request, resolved_exchange = _validate_request(request)
        request = _copy_request(request)
        try:
            _require_trimmed_text(refresh_generation, "refresh_generation")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        config = SignedSourceRegistry._trusted_config_snapshot(record.registry, request)
        if config.bootstrap_calendar and request.security_id is not None:
            raise FormalTerminalSourceError(
                "bootstrap calendar request must not carry a security_id"
            )
        if config.dataset == "universe_listing" and (
            request.security_id is not None
            or config.exchange_scope is None
            or request.exchange != config.exchange_scope
        ):
            raise FormalTerminalSourceError(
                "universe_listing must be a global request for its signed exchange scope"
            )
        if config.exchange_scope is not None and resolved_exchange is not None and config.exchange_scope != resolved_exchange:
            raise FormalTerminalSourceError("request exchange does not match signed config scope")
        try:
            policy = FormalOfficialSourceAdapter._policy_snapshot(
                config, _policy_specs_from_snapshot(record.policy_snapshot)
            )
            parser = FormalOfficialSourceAdapter._registered_parser(config, record.parsers)
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        binding = FormalOfficialSourceAdapter._resolve_calendar_binding(
            config,
            resolved_exchange,
            calendar_binding,
            freeze_at_utc=record.freeze_at_utc,
            registry_manifest_hash=record.registry_manifest_hash,
        )
        try:
            transport_request = _build_transport_request(config, request, resolved_exchange)
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        return _OperationPlan(
            transport=record.transport,
            parser=parser,
            effective_time_resolver=record.effective_time_resolver,
            request=request,
            config=config,
            policy=policy,
            resolved_exchange=resolved_exchange,
            calendar_binding=binding,
            transport_request=transport_request,
            refresh_generation=refresh_generation,
        )

    @staticmethod
    def _snapshot_response(response: object) -> TransportResponse:
        if type(response) is not TransportResponse:
            raise FormalTerminalSourceError("transport response must have exact type TransportResponse")
        status_code = response.status_code
        original_url = response.original_url
        headers = response.headers
        raw_bytes = response.raw_bytes
        captured_at_utc = response.captured_at_utc
        if type(status_code) is not int:
            raise FormalTerminalSourceError("transport response status_code is invalid")
        if not isinstance(headers, Mapping):
            raise FormalTerminalSourceError("transport response headers are invalid")
        if type(raw_bytes) is not bytes:
            raise FormalTerminalSourceError("transport response raw_bytes are invalid")
        try:
            _https_host(original_url, "transport response original_url")
            _require_aware_timestamp(captured_at_utc, "transport response captured_at_utc")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        try:
            immutable_headers = MappingProxyType(dict(headers.items()))
        except (AttributeError, TypeError, ValueError) as error:
            raise FormalTerminalSourceError("transport response headers are invalid") from error
        return TransportResponse(
            status_code=status_code,
            original_url=original_url,
            headers=immutable_headers,
            raw_bytes=raw_bytes,
            captured_at_utc=captured_at_utc,
        )

    @staticmethod
    def _is_challenge(response: TransportResponse) -> bool:
        markers = response.raw_bytes.lower()
        for key, value in response.headers.items():
            if type(key) is not str or type(value) is not str:
                return True
            markers += (key + ":" + value).encode("utf-8", "ignore").lower()
        return b"captcha" in markers or b"challenge" in markers

    @classmethod
    def _classify_response(cls, response: TransportResponse) -> None:
        if response.status_code in {403, 429} or cls._is_challenge(response):
            raise FormalSourceBlocked("official source access is blocked or challenged")
        if response.status_code in {408, 425} or 500 <= response.status_code <= 599:
            raise FormalRetryableSourceError("official source response is retryable")
        if not 200 <= response.status_code <= 299:
            raise FormalTerminalSourceError("official source returned a terminal HTTP response")

    @staticmethod
    def _effective_document_fields(
        document: object,
        *,
        request: OfficialRequest,
        config: SourceAdapterConfig,
        resolved_exchange: str | None,
        calendar_binding: VerifiedCalendarBinding | None,
        effective_time_resolver: EffectiveTimeResolver,
    ) -> tuple[ParsedOfficialDocument, str, str | None]:
        document = _copy_verified_document(document)
        if document.parser_id != config.parser_id or document.parser_version != config.parser_version:
            raise FormalTerminalSourceError("parser document identity does not match signed config")
        if document.declared_security_id != request.security_id:
            raise FormalTerminalSourceError("parser declared security does not match request")
        if document.declared_period != request.period_or_date:
            raise FormalTerminalSourceError("parser declared period does not match request")
        if document.bootstrap_calendar != config.bootstrap_calendar:
            raise FormalTerminalSourceError("parser bootstrap fact does not match signed config")
        if config.dataset == "universe_listing":
            if request.security_id is not None or config.exchange_scope is None:
                raise FormalTerminalSourceError("universe_listing must be a scoped global request")
            if resolved_exchange != config.exchange_scope:
                raise FormalTerminalSourceError("universe_listing request exchange is invalid")
            for row in document.rows:
                if not all(key in row for key in ("security_id", "security_type", "listing_status")):
                    raise FormalTerminalSourceError("universe listing rows require explicit identity, type, and status")
                security_id = row["security_id"]
                if type(security_id) is not str or _SECURITY_ID.fullmatch(security_id) is None:
                    raise FormalTerminalSourceError("universe listing security_id is not canonical")
                if security_id[:2] != config.exchange_scope:
                    raise FormalTerminalSourceError("universe listing contains another exchange")
                try:
                    _require_trimmed_text(row["security_type"], "universe listing security_type")
                    _require_trimmed_text(row["listing_status"], "universe listing listing_status")
                except ValueError as error:
                    raise FormalTerminalSourceError(str(error)) from error
        if config.calendar_selector is None:
            if document.published_precision != "timestamp":
                raise FormalTerminalSourceError("timestamp signed config received date_only document")
            if calendar_binding is not None:
                raise FormalTerminalSourceError("timestamp document forbids calendar binding")
            return document, document.published_at_utc, None
        if document.published_precision != "date_only":
            raise FormalTerminalSourceError("date_only signed config received timestamp document")
        if calendar_binding is None or resolved_exchange is None:
            raise FormalTerminalSourceError("date_only document requires a resolved calendar binding")
        disclosure_date = _require_date_only_anchor(document.published_at_utc)[:10]
        try:
            close = effective_time_resolver.next_exchange_close(
                exchange=resolved_exchange,
                disclosure_date_cn=disclosure_date,
                calendar_binding=_copy_calendar_binding(calendar_binding),
            )
            effective_at = resolve_effective_at(
                disclosure_date,
                "date_only",
                verified_next_exchange_close=close,
            )
        except (TypeError, ValueError) as error:
            raise FormalTerminalSourceError("verified calendar resolver returned an invalid close") from error
        return document, effective_at, calendar_binding.manifest_sha256

    @staticmethod
    def _verify_or_raise(
        fetch: OfficialFetch,
        policy: SourcePolicy,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> EvidenceVerification:
        verification = verify_official_fetch(fetch, policy, calendar_binding=calendar_binding)
        if verification.status != "verified":
            raise FormalTerminalSourceError(
                "official fetch verification failed: " + ",".join(verification.reasons)
            )
        return verification

    def fetch_verified(
        self,
        request: OfficialRequest,
        *,
        refresh_generation: str,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> tuple[OfficialFetch, EvidenceVerification, ParsedOfficialDocument]:
        plan = FormalOfficialSourceAdapter._preflight(
            self, request, refresh_generation, calendar_binding
        )
        try:
            response = plan.transport.send(plan.transport_request)
        except TimeoutError as error:
            raise FormalRetryableSourceError("official transport timed out") from error
        except FormalSourceError:
            raise
        except OSError as error:
            raise FormalRetryableSourceError("official transport failed") from error
        response = FormalOfficialSourceAdapter._snapshot_response(response)
        try:
            host = _https_host(response.original_url, "transport response original_url")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        if host not in plan.policy.allowed_hosts:
            raise FormalTerminalSourceError("transport response URL host is not allowlisted")
        FormalOfficialSourceAdapter._classify_response(response)
        try:
            document = plan.parser.parse(
                response.raw_bytes,
                request=_copy_request(plan.request),
                config=_copy_config(plan.config),
            )
        except FormalSourceError:
            raise
        except Exception as error:
            raise FormalTerminalSourceError("official document parser failed") from error
        document, effective_at, evidence_hash = FormalOfficialSourceAdapter._effective_document_fields(
            document,
            request=plan.request,
            config=plan.config,
            resolved_exchange=plan.resolved_exchange,
            calendar_binding=plan.calendar_binding,
            effective_time_resolver=plan.effective_time_resolver,
        )
        fetch = OfficialFetch(
            request=plan.request,
            raw_bytes=response.raw_bytes,
            original_url=response.original_url,
            published_at_utc=document.published_at_utc,
            published_precision=document.published_precision,
            source_updated_at_utc=document.source_updated_at_utc,
            captured_at_utc=response.captured_at_utc,
            effective_at_utc=effective_at,
            effective_time_evidence_hash=evidence_hash,
            refresh_generation=plan.refresh_generation,
            parser_id=plan.config.parser_id,
            parser_version=plan.config.parser_version,
            mapping_version=plan.config.mapping_version,
            declared_security_id=document.declared_security_id,
            declared_period=document.declared_period,
        )
        verification = FormalOfficialSourceAdapter._verify_or_raise(
            fetch, plan.policy, plan.calendar_binding
        )
        return fetch, verification, document

    def parse_verified_snapshot(
        self,
        snapshot_ref: OfficialSnapshotRef,
        raw_bytes: bytes,
        *,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> ParsedOfficialDocument:
        FormalOfficialSourceAdapter._operation_record(self)
        if type(snapshot_ref) is not OfficialSnapshotRef:
            raise FormalTerminalSourceError("snapshot_ref must have exact type OfficialSnapshotRef")
        if type(raw_bytes) is not bytes:
            raise FormalTerminalSourceError("snapshot raw_bytes must be bytes")
        try:
            trusted_ref = _copy_snapshot_ref(snapshot_ref)
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        if hashlib.sha256(raw_bytes).hexdigest() != trusted_ref.content_sha256:
            raise FormalTerminalSourceError("snapshot raw_bytes SHA-256 does not match reference")
        try:
            request = OfficialRequest(
                trusted_ref.source,
                trusted_ref.dataset,
                trusted_ref.security_id,
                trusted_ref.period_or_date,
                trusted_ref.exchange,
            )
            plan = FormalOfficialSourceAdapter._preflight(
                self, request, trusted_ref.refresh_generation, calendar_binding
            )
        except FormalSourceError:
            raise
        if plan.request.request_fingerprint != trusted_ref.request_fingerprint:
            raise FormalTerminalSourceError("snapshot request fingerprint does not match identity")
        if trusted_ref.verification_status != "verified":
            raise FormalTerminalSourceError("snapshot is not verified")
        if (
            trusted_ref.parser_id != plan.config.parser_id
            or trusted_ref.parser_version != plan.config.parser_version
            or trusted_ref.mapping_version != plan.config.mapping_version
        ):
            raise FormalTerminalSourceError("snapshot parser or mapping identity does not match signed config")
        try:
            snapshot_host = _https_host(trusted_ref.original_url, "snapshot original_url")
            _require_aware_timestamp(trusted_ref.captured_at_utc, "snapshot captured_at_utc")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        if snapshot_host not in plan.policy.allowed_hosts:
            raise FormalTerminalSourceError("snapshot URL host is not allowlisted")
        try:
            document = plan.parser.parse(
                raw_bytes,
                request=_copy_request(plan.request),
                config=_copy_config(plan.config),
            )
        except FormalSourceError:
            raise
        except Exception as error:
            raise FormalTerminalSourceError("official document parser failed") from error
        document, effective_at, evidence_hash = FormalOfficialSourceAdapter._effective_document_fields(
            document,
            request=plan.request,
            config=plan.config,
            resolved_exchange=plan.resolved_exchange,
            calendar_binding=plan.calendar_binding,
            effective_time_resolver=plan.effective_time_resolver,
        )
        if (
            trusted_ref.published_at_utc != document.published_at_utc
            or trusted_ref.published_precision != document.published_precision
            or trusted_ref.source_updated_at_utc != document.source_updated_at_utc
            or trusted_ref.effective_at_utc != effective_at
            or trusted_ref.effective_time_evidence_hash != evidence_hash
        ):
            raise FormalTerminalSourceError("snapshot publication or effective-time lineage does not match parser")
        fetch = OfficialFetch(
            request=plan.request,
            raw_bytes=raw_bytes,
            original_url=trusted_ref.original_url,
            published_at_utc=trusted_ref.published_at_utc,
            published_precision=trusted_ref.published_precision,
            source_updated_at_utc=trusted_ref.source_updated_at_utc,
            captured_at_utc=trusted_ref.captured_at_utc,
            effective_at_utc=trusted_ref.effective_at_utc,
            effective_time_evidence_hash=trusted_ref.effective_time_evidence_hash,
            refresh_generation=trusted_ref.refresh_generation,
            parser_id=trusted_ref.parser_id,
            parser_version=trusted_ref.parser_version,
            mapping_version=trusted_ref.mapping_version,
            declared_security_id=document.declared_security_id,
            declared_period=document.declared_period,
        )
        FormalOfficialSourceAdapter._verify_or_raise(fetch, plan.policy, plan.calendar_binding)
        return document


def _seal_formal_official_source_adapter_type(
    adapter_type: type[FormalOfficialSourceAdapter],
) -> type[FormalOfficialSourceAdapter]:
    """Seal adapter anchors outside public instance fields.

    Source adapters contain injected collaborators and public audit fields.
    Their operation state is recorded by identity in this closure so changing
    any public or collaborator anchor with ``object.__setattr__`` cannot
    redirect a later request or change calendar-root validation.
    """

    @dataclass(frozen=True)
    class _AdapterRecord:
        reference: weakref.ReferenceType[object]
        registry: SignedSourceRegistry
        transport: OfficialTransport
        effective_time_resolver: EffectiveTimeResolver
        policies: Mapping[str, SourcePolicy]
        parsers: Mapping[str, OfficialDocumentParser]
        policy_specs: Mapping[str, _PolicySpec]
        policy_snapshot: tuple[tuple[str, str, frozenset[str]], ...]
        source_registry_hash: str
        registry_manifest_hash: str
        freeze_at_utc: str

    @dataclass(frozen=True)
    class _AdapterOperationSnapshot:
        """Fresh operation inputs; never expose the closure-held seal record."""

        registry: SignedSourceRegistry
        transport: OfficialTransport
        effective_time_resolver: EffectiveTimeResolver
        parsers: Mapping[str, OfficialDocumentParser]
        policy_snapshot: tuple[tuple[str, str, frozenset[str]], ...]
        source_registry_hash: str
        registry_manifest_hash: str
        freeze_at_utc: str

    verified_adapters: dict[int, _AdapterRecord] = {}
    original_init = adapter_type.__init__
    missing = object()

    def policy_snapshot(
        policy_specs: object,
    ) -> tuple[tuple[str, str, frozenset[str]], ...] | None:
        if not isinstance(policy_specs, Mapping):
            return None
        try:
            sources = tuple(sorted(policy_specs))
        except TypeError:
            return None
        entries: list[tuple[str, str, frozenset[str]]] = []
        for source in sources:
            if type(source) is not str:
                return None
            try:
                spec = policy_specs[source]
            except (KeyError, TypeError):
                return None
            if type(spec) is not _PolicySpec:
                return None
            if type(spec.source) is not str or type(spec.allowed_hosts) is not frozenset:
                return None
            entries.append((source, spec.source, frozenset(spec.allowed_hosts)))
        return tuple(entries)

    def remember(adapter: object) -> None:
        try:
            registry = adapter.registry
            transport = adapter._transport
            effective_time_resolver = adapter._effective_time_resolver
            policies = adapter._policies
            parsers = adapter._parsers
            policy_specs = adapter._policy_specs
            source_registry_hash = adapter.source_registry_hash
            registry_manifest_hash = adapter.registry_manifest_hash
            freeze_at_utc = adapter.freeze_at_utc
        except AttributeError as error:
            raise ValueError("formal source adapter anchors are incomplete") from error
        if type(registry) is not SignedSourceRegistry:
            raise ValueError("formal source adapter registry is invalid")
        SignedSourceRegistry._require_verified(registry)
        if not isinstance(policies, Mapping) or not isinstance(parsers, Mapping):
            raise ValueError("formal source adapter mappings are invalid")
        if not isinstance(policy_specs, Mapping):
            raise ValueError("formal source adapter policy snapshots are invalid")
        sealed_policy_snapshot = policy_snapshot(policy_specs)
        if sealed_policy_snapshot is None:
            raise ValueError("formal source adapter policy snapshots are invalid")
        _require_sha256(source_registry_hash, "source_registry_hash")
        _require_sha256(registry_manifest_hash, "registry_manifest_hash")
        _require_aware_timestamp(freeze_at_utc, "freeze_at_utc")
        identity = id(adapter)

        def forget(reference: weakref.ReferenceType[object]) -> None:
            record = verified_adapters.get(identity)
            if record is not None and record.reference is reference:
                verified_adapters.pop(identity, None)

        verified_adapters[identity] = _AdapterRecord(
            weakref.ref(adapter, forget),
            registry,
            transport,
            effective_time_resolver,
            policies,
            parsers,
            policy_specs,
            sealed_policy_snapshot,
            source_registry_hash,
            registry_manifest_hash,
            freeze_at_utc,
        )

    def trusted_record(adapter: object) -> _AdapterOperationSnapshot:
        record = verified_adapters.get(id(adapter))
        if record is None or record.reference() is not adapter:
            raise ValueError("formal source adapter was not verified")
        try:
            current = (
                adapter.registry,
                adapter._transport,
                adapter._effective_time_resolver,
                adapter._policies,
                adapter._parsers,
                adapter._policy_specs,
                adapter.source_registry_hash,
                adapter.registry_manifest_hash,
                adapter.freeze_at_utc,
            )
        except AttributeError as error:
            raise ValueError("formal source adapter anchors are incomplete") from error
        expected = (
            record.registry,
            record.transport,
            record.effective_time_resolver,
            record.policies,
            record.parsers,
            record.policy_specs,
            record.source_registry_hash,
            record.registry_manifest_hash,
            record.freeze_at_utc,
        )
        if (
            current[0] is not expected[0]
            or current[1] is not expected[1]
            or current[2] is not expected[2]
            or current[3] is not expected[3]
            or current[4] is not expected[4]
            or current[5] is not expected[5]
            or policy_snapshot(current[5]) != record.policy_snapshot
            or any(
                type(current[index]) is not type(expected[index])
                or current[index] != expected[index]
                for index in (6, 7, 8)
            )
        ):
            raise ValueError("formal source adapter anchors have changed")
        SignedSourceRegistry._require_verified(record.registry)
        return _AdapterOperationSnapshot(
            registry=record.registry,
            transport=record.transport,
            effective_time_resolver=record.effective_time_resolver,
            parsers=MappingProxyType(dict(record.parsers)),
            policy_snapshot=tuple(
                (source, policy_source, frozenset(allowed_hosts))
                for source, policy_source, allowed_hosts in record.policy_snapshot
            ),
            source_registry_hash=record.source_registry_hash,
            registry_manifest_hash=record.registry_manifest_hash,
            freeze_at_utc=record.freeze_at_utc,
        )

    def sealed_init(self: FormalOfficialSourceAdapter, *args: object, **kwargs: object) -> None:
        expected_registry = kwargs.get("registry", missing)
        expected_transport = kwargs.get("transport", missing)
        expected_resolver = kwargs.get("effective_time_resolver", missing)
        expected_source_hash = kwargs.get("source_registry_hash", missing)
        expected_root_hash = kwargs.get("registry_manifest_hash", missing)
        expected_freeze = kwargs.get("freeze_at_utc", FORMAL_FREEZE_AT_CN)
        original_init(self, *args, **kwargs)
        if (
            expected_registry is missing
            or expected_transport is missing
            or expected_resolver is missing
            or expected_source_hash is missing
            or expected_root_hash is missing
            or self.registry is not expected_registry
            or self._transport is not expected_transport
            or self._effective_time_resolver is not expected_resolver
            or type(self.source_registry_hash) is not type(expected_source_hash)
            or self.source_registry_hash != expected_source_hash
            or type(self.registry_manifest_hash) is not type(expected_root_hash)
            or self.registry_manifest_hash != expected_root_hash
            or type(self.freeze_at_utc) is not type(expected_freeze)
            or self.freeze_at_utc != expected_freeze
        ):
            raise ValueError("formal source adapter anchors changed during construction")
        remember(self)

    adapter_type.__init__ = sealed_init
    adapter_type._trusted_operation_record = staticmethod(trusted_record)
    return adapter_type


FormalOfficialSourceAdapter = _seal_formal_official_source_adapter_type(
    FormalOfficialSourceAdapter
)
del _seal_formal_official_source_adapter_type


__all__ = [
    "CalendarSelector",
    "EffectiveTimeResolver",
    "FormalOfficialSourceAdapter",
    "FormalRetryableSourceError",
    "FormalSourceBlocked",
    "FormalSourceError",
    "FormalTerminalSourceError",
    "OfficialDocumentParser",
    "OfficialTransport",
    "ParsedOfficialDocument",
    "RegistrySignatureVerifier",
    "SignedSourceRegistry",
    "SourceAdapterConfig",
    "TransportRequest",
    "TransportResponse",
]
