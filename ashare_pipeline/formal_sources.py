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
_REGISTRY_CONSTRUCTION_TOKEN = object()


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
        if self.context_kind != "trading_calendar":
            raise ValueError("calendar selector context_kind must be trading_calendar")
        _require_trimmed_text(self.scope_key, "calendar selector scope_key", identifier=True)
        _require_exchange(self.exchange, "calendar selector exchange")
        if self.as_of_rule != "visible_at_freeze":
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
        if self.http_method not in {"GET", "POST"}:
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
        if self.published_precision not in {"timestamp", "date_only"}:
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


@dataclass(frozen=True, init=False)
class SignedSourceRegistry:
    """A canonical, verifier-approved source registry with no default configs."""

    canonical_json: bytes
    registry_hash: str
    signature: str
    key_id: str
    configs: tuple[SourceAdapterConfig, ...]

    def __init__(
        self,
        canonical_json: bytes,
        registry_hash: str,
        signature: str,
        key_id: str,
        configs: tuple[SourceAdapterConfig, ...],
        *,
        _verified_token: object | None = None,
    ) -> None:
        if _verified_token is not _REGISTRY_CONSTRUCTION_TOKEN:
            raise ValueError("SignedSourceRegistry must be loaded with from_signed_bytes")
        object.__setattr__(self, "canonical_json", canonical_json)
        object.__setattr__(self, "registry_hash", registry_hash)
        object.__setattr__(self, "signature", signature)
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(self, "configs", configs)

    @classmethod
    def from_signed_bytes(
        cls,
        registry_bytes: bytes,
        signature: str,
        key_id: str,
        verifier: RegistrySignatureVerifier,
    ) -> "SignedSourceRegistry":
        signature_text, key_text = _verify_signature(
            registry_bytes, signature, key_id, verifier, label="source registry"
        )
        wire = _load_canonical_object(registry_bytes, label="source registry")
        if set(wire) != {"configs", "registry_role", "schema_version"}:
            raise ValueError("source registry has unknown or missing keys")
        if wire["registry_role"] != "source":
            raise ValueError("source registry role must be source")
        if wire["schema_version"] != "formal-source-registry-v1":
            raise ValueError("source registry schema_version is invalid")
        if type(wire["configs"]) is not list:
            raise ValueError("source registry configs must be a list")
        registry_hash = hashlib.sha256(registry_bytes).hexdigest()
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
        return cls(
            registry_bytes,
            registry_hash,
            signature_text,
            key_text,
            tuple(configs),
            _verified_token=_REGISTRY_CONSTRUCTION_TOKEN,
        )

    def select(self, request: OfficialRequest) -> SourceAdapterConfig:
        _, exchange = _validate_request(request)
        matching = [
            config
            for config in self.configs
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
    if request.exchange is not None and request.exchange not in _EXCHANGES:
        raise FormalTerminalSourceError("request exchange must be SH, SZ, BJ, or null")
    if request.exchange is not None and security_exchange is not None and request.exchange != security_exchange:
        raise FormalTerminalSourceError("request security_id and exchange disagree")
    return request, request.exchange or security_exchange


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
        self._transport = transport
        self.registry = registry
        self._policies = dict(policies)
        self._parsers = dict(parsers)
        self._effective_time_resolver = effective_time_resolver
        self.source_registry_hash = source_registry_hash
        self.registry_manifest_hash = registry_manifest_hash
        self.freeze_at_utc = freeze_at_utc
        for config in registry.configs:
            self._registered_policy(config)
            self._registered_parser(config)

    def _registered_policy(self, config: SourceAdapterConfig) -> SourcePolicy:
        policy = self._policies.get(config.source)
        if type(policy) is not SourcePolicy or policy.source != config.source or not policy.is_authoritative:
            raise ValueError("signed source policy is absent or non-authoritative")
        try:
            host = _https_host(config.endpoint_url, "signed endpoint_url")
        except ValueError as error:
            raise ValueError(str(error)) from error
        if host not in policy.allowed_hosts:
            raise ValueError("signed endpoint host is not allowlisted by source policy")
        return policy

    def _registered_parser(self, config: SourceAdapterConfig) -> OfficialDocumentParser:
        parser = self._parsers.get(config.parser_id)
        if not callable(getattr(parser, "parse", None)):
            raise ValueError("signed parser is not registered")
        return parser

    def _resolve_calendar_binding(
        self,
        config: SourceAdapterConfig,
        resolved_exchange: str | None,
        calendar_binding: VerifiedCalendarBinding | None,
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
        try:
            _require_trimmed_text(calendar_binding.snapshot_id, "calendar binding snapshot_id")
            _require_sha256(calendar_binding.manifest_sha256, "calendar binding manifest_sha256")
            _require_exchange(calendar_binding.exchange, "calendar binding exchange")
            _require_aware_timestamp(calendar_binding.freeze_at_utc, "calendar binding freeze_at_utc")
            _require_sha256(
                calendar_binding.registry_manifest_hash,
                "calendar binding registry_manifest_hash",
            )
            _require_sha256(calendar_binding.selector_hash, "calendar binding selector_hash")
            _require_canonical_uuid(calendar_binding.prerequisite_task_id, "calendar binding prerequisite_task_id")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        if calendar_binding.exchange != selector.exchange:
            raise FormalTerminalSourceError("calendar binding exchange does not match signed selector")
        if calendar_binding.freeze_at_utc != self.freeze_at_utc:
            raise FormalTerminalSourceError("calendar binding freeze does not match adapter freeze")
        if calendar_binding.registry_manifest_hash != self.registry_manifest_hash:
            raise FormalTerminalSourceError("calendar binding root does not match adapter root")
        if calendar_binding.selector_hash != selector.selector_hash:
            raise FormalTerminalSourceError("calendar binding selector does not match signed selector")
        return calendar_binding

    def _preflight(
        self,
        request: OfficialRequest,
        refresh_generation: str,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> tuple[OfficialRequest, SourceAdapterConfig, SourcePolicy, OfficialDocumentParser, str | None, VerifiedCalendarBinding | None, TransportRequest]:
        request, resolved_exchange = _validate_request(request)
        try:
            _require_trimmed_text(refresh_generation, "refresh_generation")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        config = self.registry.select(request)
        if config.bootstrap_calendar and (
            request.exchange is not None or request.security_id is not None
        ):
            raise FormalTerminalSourceError(
                "bootstrap calendar request must be a global request without an exchange"
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
            policy = self._registered_policy(config)
            parser = self._registered_parser(config)
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        binding = self._resolve_calendar_binding(config, resolved_exchange, calendar_binding)
        try:
            transport_request = _build_transport_request(config, request, resolved_exchange)
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        return request, config, policy, parser, resolved_exchange, binding, transport_request

    @staticmethod
    def _validate_response(response: object) -> TransportResponse:
        if type(response) is not TransportResponse:
            raise FormalTerminalSourceError("transport response must have exact type TransportResponse")
        if type(response.status_code) is not int:
            raise FormalTerminalSourceError("transport response status_code is invalid")
        if not isinstance(response.headers, Mapping):
            raise FormalTerminalSourceError("transport response headers are invalid")
        if type(response.raw_bytes) is not bytes:
            raise FormalTerminalSourceError("transport response raw_bytes are invalid")
        try:
            _require_aware_timestamp(response.captured_at_utc, "transport response captured_at_utc")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        return response

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

    def _effective_document_fields(
        self,
        document: object,
        *,
        request: OfficialRequest,
        config: SourceAdapterConfig,
        resolved_exchange: str | None,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> tuple[ParsedOfficialDocument, str, str | None]:
        if type(document) is not ParsedOfficialDocument:
            raise FormalTerminalSourceError("parser must return exact ParsedOfficialDocument")
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
            close = self._effective_time_resolver.next_exchange_close(
                exchange=resolved_exchange,
                disclosure_date_cn=disclosure_date,
                calendar_binding=calendar_binding,
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
        (
            request,
            config,
            policy,
            parser,
            resolved_exchange,
            binding,
            transport_request,
        ) = self._preflight(request, refresh_generation, calendar_binding)
        try:
            response = self._transport.send(transport_request)
        except TimeoutError as error:
            raise FormalRetryableSourceError("official transport timed out") from error
        except FormalSourceError:
            raise
        except OSError as error:
            raise FormalRetryableSourceError("official transport failed") from error
        response = self._validate_response(response)
        try:
            host = _https_host(response.original_url, "transport response original_url")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        if host not in policy.allowed_hosts:
            raise FormalTerminalSourceError("transport response URL host is not allowlisted")
        self._classify_response(response)
        try:
            document = parser.parse(response.raw_bytes, request=request, config=config)
        except FormalSourceError:
            raise
        except Exception as error:
            raise FormalTerminalSourceError("official document parser failed") from error
        document, effective_at, evidence_hash = self._effective_document_fields(
            document,
            request=request,
            config=config,
            resolved_exchange=resolved_exchange,
            calendar_binding=binding,
        )
        fetch = OfficialFetch(
            request=request,
            raw_bytes=response.raw_bytes,
            original_url=response.original_url,
            published_at_utc=document.published_at_utc,
            published_precision=document.published_precision,
            source_updated_at_utc=document.source_updated_at_utc,
            captured_at_utc=response.captured_at_utc,
            effective_at_utc=effective_at,
            effective_time_evidence_hash=evidence_hash,
            refresh_generation=refresh_generation,
            parser_id=config.parser_id,
            parser_version=config.parser_version,
            mapping_version=config.mapping_version,
            declared_security_id=document.declared_security_id,
            declared_period=document.declared_period,
        )
        verification = self._verify_or_raise(fetch, policy, binding)
        return fetch, verification, document

    def parse_verified_snapshot(
        self,
        snapshot_ref: OfficialSnapshotRef,
        raw_bytes: bytes,
        *,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> ParsedOfficialDocument:
        if type(snapshot_ref) is not OfficialSnapshotRef:
            raise FormalTerminalSourceError("snapshot_ref must have exact type OfficialSnapshotRef")
        if type(raw_bytes) is not bytes:
            raise FormalTerminalSourceError("snapshot raw_bytes must be bytes")
        try:
            _require_sha256(snapshot_ref.content_sha256, "snapshot content_sha256")
            _require_sha256(snapshot_ref.manifest_sha256, "snapshot manifest_sha256")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        if hashlib.sha256(raw_bytes).hexdigest() != snapshot_ref.content_sha256:
            raise FormalTerminalSourceError("snapshot raw_bytes SHA-256 does not match reference")
        try:
            request = OfficialRequest(
                snapshot_ref.source,
                snapshot_ref.dataset,
                snapshot_ref.security_id,
                snapshot_ref.period_or_date,
                snapshot_ref.exchange,
            )
            request, config, policy, parser, resolved_exchange, binding, _ = self._preflight(
                request, snapshot_ref.refresh_generation, calendar_binding
            )
        except FormalSourceError:
            raise
        if request.request_fingerprint != snapshot_ref.request_fingerprint:
            raise FormalTerminalSourceError("snapshot request fingerprint does not match identity")
        if snapshot_ref.verification_status != "verified":
            raise FormalTerminalSourceError("snapshot is not verified")
        if (
            snapshot_ref.parser_id != config.parser_id
            or snapshot_ref.parser_version != config.parser_version
            or snapshot_ref.mapping_version != config.mapping_version
        ):
            raise FormalTerminalSourceError("snapshot parser or mapping identity does not match signed config")
        try:
            snapshot_host = _https_host(snapshot_ref.original_url, "snapshot original_url")
            _require_aware_timestamp(snapshot_ref.captured_at_utc, "snapshot captured_at_utc")
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error
        if snapshot_host not in policy.allowed_hosts:
            raise FormalTerminalSourceError("snapshot URL host is not allowlisted")
        try:
            document = parser.parse(raw_bytes, request=request, config=config)
        except FormalSourceError:
            raise
        except Exception as error:
            raise FormalTerminalSourceError("official document parser failed") from error
        document, effective_at, evidence_hash = self._effective_document_fields(
            document,
            request=request,
            config=config,
            resolved_exchange=resolved_exchange,
            calendar_binding=binding,
        )
        if (
            snapshot_ref.published_at_utc != document.published_at_utc
            or snapshot_ref.published_precision != document.published_precision
            or snapshot_ref.source_updated_at_utc != document.source_updated_at_utc
            or snapshot_ref.effective_at_utc != effective_at
            or snapshot_ref.effective_time_evidence_hash != evidence_hash
        ):
            raise FormalTerminalSourceError("snapshot publication or effective-time lineage does not match parser")
        fetch = OfficialFetch(
            request=request,
            raw_bytes=raw_bytes,
            original_url=snapshot_ref.original_url,
            published_at_utc=snapshot_ref.published_at_utc,
            published_precision=snapshot_ref.published_precision,
            source_updated_at_utc=snapshot_ref.source_updated_at_utc,
            captured_at_utc=snapshot_ref.captured_at_utc,
            effective_at_utc=snapshot_ref.effective_at_utc,
            effective_time_evidence_hash=snapshot_ref.effective_time_evidence_hash,
            refresh_generation=snapshot_ref.refresh_generation,
            parser_id=snapshot_ref.parser_id,
            parser_version=snapshot_ref.parser_version,
            mapping_version=snapshot_ref.mapping_version,
            declared_security_id=document.declared_security_id,
            declared_period=document.declared_period,
        )
        self._verify_or_raise(fetch, policy, binding)
        return document


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
