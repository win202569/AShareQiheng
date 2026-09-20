"""Authenticated bounded range requests, transport observations, and replay parsing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re
from types import MappingProxyType, MethodType
import weakref

from .formal_range_format import RangeConfig, _canonical, _range_config_to_dict
from .formal_time import FORMAL_FREEZE_AT_CN


_HASH = re.compile(r"^[0-9a-f]{64}$")
_SECURITY = re.compile(r"^(?:SH|SZ|BJ)[0-9]{6}$")
_REQUEST_FIELDS = (
    "schema_version", "kind", "source", "dataset", "security_id", "exchange",
    "as_of_utc", "start_date", "end_date", "anchor_descriptor_id",
    "calendar_descriptor_id", "range_config_id", "registry_manifest_hash",
    "page_index", "calendar_coverage_hash",
)
_DOCUMENT_FIELDS = frozenset({
    "schema_version", "request_fingerprint", "source", "dataset", "security_id",
    "exchange", "start_date", "end_date", "parser_id", "parser_version",
    "mapping_version", "normalizer_version", "request_version", "page_index",
    "page_count", "record_count", "page_record_count", "coverage", "rows",
    "published_at_utc", "published_precision", "source_updated_at_utc",
    "effective_at_utc", "effective_time_evidence_hash", "captured_at_utc",
    "upstream_generation", "pagination_evidence",
})
_ROW_TIME_FIELDS = frozenset({
    "published_at_utc", "published_precision", "effective_at_utc",
    "effective_time_evidence_hash", "captured_at_utc",
})
_FORBIDDEN_POLICY_FIELDS = frozenset({
    "effective_trade", "stale_days", "pool_veto", "confirmed_no_price",
})
_FREEZE_UTC = datetime.fromisoformat(FORMAL_FREEZE_AT_CN).astimezone(timezone.utc).isoformat()


def _aware(value: object, label: str) -> datetime:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an aware ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be an aware ISO timestamp")
    return parsed


def _date(value: object, label: str) -> date:
    if type(value) is not str:
        raise ValueError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be a canonical ISO date")
    return parsed


def _hash(value: object, label: str) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an already-trimmed nonempty string")
    return value


def backward_interval(end_text, limit):
    """Return an inclusive natural-calendar interval without underflow."""
    if type(limit) is not int or limit <= 0:
        raise ValueError("range limit must be a positive exact integer")
    end = date.fromisoformat(end_text)
    distance = min(limit - 1, (end - date.min).days)
    return (end - timedelta(days=distance)).isoformat(), end.isoformat()


def page_successor(document, max_pages):
    """Read a source-backed page declaration; this function mints no request."""
    if type(max_pages) is not int or max_pages <= 0:
        raise ValueError("max_pages must be a positive exact integer")
    if not isinstance(document, Mapping):
        raise ValueError("page document must be a mapping")
    try:
        page, count = document["page_index"], document["page_count"]
    except KeyError as error:
        raise ValueError("page identity is absent") from error
    if type(page) is not int or type(count) is not int:
        raise ValueError("page identity must use exact integers")
    if not 1 <= page <= count or count > max_pages:
        raise ValueError("unverified or out-of-budget pagination")
    return page + 1 if page < count else None


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_thaw(item) for item in value]
    return value


def _freeze_json(value: object, *, label: str = "JSON value") -> object:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if type(key) is not str or key in result:
                raise ValueError(f"{label} keys must be unique exact strings")
            result[key] = _freeze_json(item, label=label)
        return MappingProxyType(result)
    if type(value) in (list, tuple):
        return tuple(_freeze_json(item, label=label) for item in value)
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError(f"{label} is not canonical JSON data")


from .formal_sources import (
    FormalOfficialSourceAdapter,
    FormalRetryableSourceError,
    FormalSourceBlocked,
    FormalTerminalSourceError,
    TransportRequest,
    TransportResponse,
    _https_host,
    _range_registry_authority,
)
from .formal_range_contract import (
    _range_binding_authority,
    _range_binding_planning_authority,
)


class FormalRangeAcquisitionError(FormalTerminalSourceError):
    """Terminal live response failure, never a persisted-evidence replay failure."""


(
    SignedSourceRegistry,
    _require_source_registry,
    _trusted_range_config_snapshots,
) = _range_registry_authority()
(
    RangeBinding,
    _require_range_binding,
    _calendar_config_get,
    _manifest_hash_get,
    _source_hash_get,
) = _range_binding_authority()
(_, _read_planning_binding) = _range_binding_planning_authority()


def _build_request_authority():
    """Own request minting beside eagerly captured genuine binding authority."""

    @dataclass(frozen=True)
    class _RequestRecord:
        reference: weakref.ReferenceType[object]
        binding: object
        wire: dict[str, object]
        fingerprint: str
        config_wire: dict[str, object]
        source_registry_hash: str
        previous: object = None
        parent: object = None
        owner_store: object = None

    records: dict[int, _RequestRecord] = {}

    @dataclass(frozen=True, init=False)
    class FormalRangeRequestV1:
        schema_version: str
        kind: str
        source: str
        dataset: str
        security_id: str | None
        exchange: str
        as_of_utc: str
        start_date: str
        end_date: str
        anchor_descriptor_id: str
        calendar_descriptor_id: str
        range_config_id: str
        registry_manifest_hash: str
        page_index: int
        calendar_coverage_hash: str | None

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("FormalRangeRequestV1 cannot be externally constructed")

        def to_dict(self) -> dict[str, object]:
            return dict(request_record(self).wire)

        @property
        def request_fingerprint(self) -> str:
            return request_record(self).fingerprint

        def __copy__(self):
            raise TypeError("formal range requests cannot be copied")

        def __deepcopy__(self, _memo):
            raise TypeError("formal range requests cannot be copied")

    def binding_config(binding: object, kind: str) -> RangeConfig:
        identity = _read_planning_binding(binding)
        config = identity["calendar_config" if kind == "calendar_range" else "market_config"]
        if type(config) is not RangeConfig or config.kind != kind:
            raise ValueError("range binding config is invalid")
        return config

    def request_record(request: object) -> _RequestRecord:
        record = records.get(id(request))
        if (
            type(request) is not FormalRangeRequestV1
            or record is None
            or record.reference() is not request
        ):
            raise ValueError("formal range request is forged, copied, or unregistered")
        current = {
            field: object.__getattribute__(request, field) for field in _REQUEST_FIELDS
        }
        if (
            any(
                type(current[field]) is not type(record.wire[field])
                or current[field] != record.wire[field]
                for field in _REQUEST_FIELDS
            )
            or hashlib.sha256(_canonical(current)).hexdigest() != record.fingerprint
        ):
            raise ValueError("formal range request fields changed")
        config = binding_config(record.binding, record.wire["kind"])
        if (
            type(config) is not RangeConfig
            or _range_config_to_dict(config) != record.config_wire
            or _manifest_hash_get(record.binding) != record.wire["registry_manifest_hash"]
            or _source_hash_get(record.binding) != record.source_registry_hash
        ):
            raise ValueError("formal range request binding, root, or config changed")
        return record

    def seal(binding, wire, config, *, previous=None, parent=None, owner_store=None):
        if ((wire["kind"] == "market_range" and previous is None)
                != (owner_store is not None)):
            raise ValueError("initial market request requires exact Store provenance")
        request = object.__new__(FormalRangeRequestV1)
        for field in _REQUEST_FIELDS:
            object.__setattr__(request, field, wire[field])
        identity = id(request)

        def forget(reference, *, identity=identity):
            existing = records.get(identity)
            if existing is not None and existing.reference is reference:
                records.pop(identity, None)

        fingerprint = hashlib.sha256(_canonical(wire)).hexdigest()
        records[identity] = _RequestRecord(
            weakref.ref(request, forget), binding, dict(wire), fingerprint,
            _range_config_to_dict(config), _source_hash_get(binding), previous, parent,
            owner_store,
        )
        request_record(request)
        return request

    def mint_first_calendar(binding: object, as_of_utc: object) -> FormalRangeRequestV1:
        if type(binding) is not RangeBinding:
            raise ValueError("range request requires an exact genuine RangeBinding")
        _require_range_binding(binding)
        parsed = _aware(as_of_utc, "as_of_utc")
        if (
            type(as_of_utc) is not str
            or as_of_utc != _FREEZE_UTC
            or parsed != datetime.fromisoformat(_FREEZE_UTC)
        ):
            raise ValueError("calendar request as_of_utc must equal the formal freeze in UTC")
        config = binding_config(binding, "calendar_range")
        start, end = backward_interval(
            parsed.date().isoformat(), config.max_calendar_days_per_request
        )
        wire = {
            "schema_version": "formal-range-request-v1",
            "kind": "calendar_range",
            "source": config.source,
            "dataset": config.dataset,
            "security_id": None,
            "exchange": config.exchange_scope,
            "as_of_utc": as_of_utc,
            "start_date": start,
            "end_date": end,
            "anchor_descriptor_id": config.anchor_descriptor_id,
            "calendar_descriptor_id": config.calendar_descriptor_id,
            "range_config_id": config.entry_id,
            "registry_manifest_hash": _manifest_hash_get(binding),
            "page_index": 1,
            "calendar_coverage_hash": None,
        }
        if type(wire["page_index"]) is not int or not 1 <= wire["page_index"] <= config.max_pages:
            raise ValueError("first calendar request page must be exact integer one")
        if _date(wire["start_date"], "request start_date") > _date(
            wire["end_date"], "request end_date"
        ) or wire["end_date"] > parsed.date().isoformat():
            raise ValueError("first calendar request interval is invalid")
        return seal(binding, wire, config)

    def mint_market(binding: object, security_id: object, as_of_utc: object,
                    start_date: object, end_date: object,
                    calendar_coverage_hash: object, owner_store: object) -> FormalRangeRequestV1:
        if type(binding) is not RangeBinding:
            raise ValueError("market request requires an exact genuine RangeBinding")
        _require_range_binding(binding)
        if type(security_id) is not str or _SECURITY.fullmatch(security_id) is None:
            raise ValueError("market request security_id is invalid")
        identity = _read_planning_binding(binding)
        if security_id[:2] != identity["exchange"]:
            raise ValueError("market request security exchange differs from binding")
        parsed = _aware(as_of_utc, "as_of_utc")
        if type(as_of_utc) is not str or as_of_utc != _FREEZE_UTC:
            raise ValueError("market request as_of_utc must equal the formal freeze in UTC")
        start = _date(start_date, "market request start_date")
        end = _date(end_date, "market request end_date")
        config = binding_config(binding, "market_range")
        if (start > end or end > parsed.date()
                or (end - start).days + 1 > config.max_calendar_days_per_request):
            raise ValueError("market request interval is invalid")
        _hash(calendar_coverage_hash, "calendar coverage hash")
        wire = {
            "schema_version": "formal-range-request-v1",
            "kind": "market_range",
            "source": config.source,
            "dataset": config.dataset,
            "security_id": security_id,
            "exchange": config.exchange_scope,
            "as_of_utc": as_of_utc,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "anchor_descriptor_id": config.anchor_descriptor_id,
            "calendar_descriptor_id": config.calendar_descriptor_id,
            "range_config_id": config.entry_id,
            "registry_manifest_hash": identity["registry_manifest_hash"],
            "page_index": 1,
            "calendar_coverage_hash": calendar_coverage_hash,
        }
        return seal(binding, wire, config, owner_store=owner_store)

    def mint_continuation(binding, prior, mode, *, previous=None, parent=None):
        old_wire, document = prior
        config = binding_config(binding, old_wire["kind"])
        wire = dict(old_wire)
        if mode == "previous_calendar":
            if old_wire["kind"] != "calendar_range":
                raise ValueError("only calendar requests can scan backwards")
            old_start = _date(old_wire["start_date"], "previous start")
            if old_start == date.min:
                return None
            start, end = backward_interval((old_start - timedelta(days=1)).isoformat(),
                                           config.max_calendar_days_per_request)
            wire.update(start_date=start, end_date=end, page_index=1)
        elif mode == "next_page":
            page = page_successor(document, config.max_pages)
            if page is None:
                return None
            wire["page_index"] = page
        else:
            raise ValueError("unknown range continuation mode")
        return seal(binding, wire, config, previous=previous, parent=parent)

    def snapshot(request: object) -> tuple[dict[str, object], dict[str, object], str]:
        record = request_record(request)
        return dict(record.wire), dict(record.config_wire), record.source_registry_hash

    return (FormalRangeRequestV1, mint_first_calendar, mint_market,
            mint_continuation, snapshot, request_record)


(
    FormalRangeRequestV1,
    _mint_first_calendar_request,
    _mint_market_request,
    _mint_range_continuation,
    _trusted_range_request_snapshot,
    _range_request_record,
) = _build_request_authority()
del _build_request_authority


def _build_request_binding_reader():
    request_record = _range_request_record

    def range_request_binding(request):
        """Authenticate an existing request and return its genuine binding only."""
        return request_record(request).binding

    return range_request_binding


range_request_binding = _build_request_binding_reader()
del _build_request_binding_reader


def _build_select_range():
    """Build the genuine registry method from source-owned request authority."""

    request_type = FormalRangeRequestV1
    request_snapshot = _trusted_range_request_snapshot
    registry_type = SignedSourceRegistry
    require_registry = _require_source_registry
    trusted_configs = _trusted_range_config_snapshots
    config_to_dict = _range_config_to_dict

    def select_range(self, request) -> RangeConfig:
        try:
            if type(self) is not registry_type:
                raise ValueError("range selection requires an exact genuine registry")
            require_registry(self)
            if type(request) is not request_type:
                raise ValueError("range request must have exact genuine type")
            wire, sealed_config, source_registry_hash = request_snapshot(request)
            if source_registry_hash != self.registry_hash:
                raise ValueError("range request source registry differs from this registry")
            matches = [
                config
                for config in trusted_configs(self)
                if config.kind == wire["kind"]
                and config.source == wire["source"]
                and config.dataset == wire["dataset"]
                and config.exchange_scope == wire["exchange"]
                and config.entry_id == wire["range_config_id"]
                and config.anchor_descriptor_id == wire["anchor_descriptor_id"]
                and config.calendar_descriptor_id == wire["calendar_descriptor_id"]
            ]
            if len(matches) != 1 or config_to_dict(matches[0]) != sealed_config:
                raise ValueError(
                    "signed range config is absent, ambiguous, or differs from request"
                )
            return matches[0]
        except FormalTerminalSourceError:
            raise
        except ValueError as error:
            raise FormalTerminalSourceError(str(error)) from error

    return select_range


_sealed_select_range = _build_select_range()
SignedSourceRegistry.select_range = _sealed_select_range
del _sealed_select_range, _build_select_range


_snapshot_transport_response = FormalOfficialSourceAdapter._snapshot_response
_classify_transport_response = FormalOfficialSourceAdapter._classify_response


def _callable_anchor(owner: object, name: str) -> tuple[object, object | None]:
    value = getattr(owner, name, None)
    if not callable(value):
        raise ValueError(f"range implementation {name} method is absent")
    if isinstance(value, MethodType):
        return value.__self__, value.__func__
    return value, None


def _render_text(value: str, substitutions: Mapping[str, str | None], *, quote: bool) -> str:
    from urllib.parse import quote_from_bytes

    result = value
    for name in ("security_id", "exchange", "start_date", "end_date", "page_index"):
        marker = "{" + name + "}"
        if marker not in result:
            continue
        replacement = substitutions[name]
        if replacement is None:
            raise FormalTerminalSourceError(f"range placeholder {name} has a null value")
        if quote:
            replacement = quote_from_bytes(replacement.encode("utf-8"), safe="-._~")
        result = result.replace(marker, replacement)
    return result


def _render_tree(value: object, substitutions: Mapping[str, str | None]) -> object:
    if value is None:
        return None
    if type(value) is str:
        return _render_text(value, substitutions, quote=False)
    if isinstance(value, Mapping):
        return {_render_text(key, substitutions, quote=False): _render_tree(item, substitutions)
                for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_render_tree(item, substitutions) for item in value]
    raise FormalTerminalSourceError("range request template contains invalid data")


def _transport_request(config: RangeConfig, request_wire: Mapping[str, object]) -> TransportRequest:
    values = {
        "security_id": request_wire["security_id"],
        "exchange": request_wire["exchange"],
        "start_date": request_wire["start_date"],
        "end_date": request_wire["end_date"],
        "page_index": str(request_wire["page_index"]),
    }
    query = config.request_template["query"]
    headers = config.request_template["headers"]
    pairs = [
        f"{_render_text(key, values, quote=True)}={_render_text(value, values, quote=True)}"
        for key, value in sorted(query.items())
    ]
    if pairs:
        prefix = "?" if "?" not in config.endpoint_url else "" if config.endpoint_url.endswith(("?", "&")) else "&"
        url = config.endpoint_url + prefix + "&".join(pairs)
    else:
        url = config.endpoint_url
    _https_host(url, "constructed range URL")
    sent_headers = MappingProxyType({
        key: _render_text(value, values, quote=False) for key, value in headers.items()
    })
    body_value = _render_tree(config.request_template["body"], values)
    body = None if body_value is None else _canonical(body_value)
    return TransportRequest(config.http_method, url, sent_headers, body, float(config.timeout_seconds))


def _validate_document_wire(wire: object) -> dict[str, object]:
    if type(wire) is not dict or set(wire) != _DOCUMENT_FIELDS:
        raise ValueError("parsed range document has unknown or missing keys")
    if wire["schema_version"] != "formal-parsed-range-document-v1":
        raise ValueError("parsed range document schema_version is invalid")
    for field in ("request_fingerprint",):
        _hash(wire[field], f"document {field}")
    for field in (
        "source", "dataset", "exchange", "start_date", "end_date", "parser_id",
        "parser_version", "mapping_version", "normalizer_version", "request_version",
    ):
        _text(wire[field], f"document {field}")
    if wire["security_id"] is not None and (
        type(wire["security_id"]) is not str or _SECURITY.fullmatch(wire["security_id"]) is None
    ):
        raise ValueError("document security_id is invalid")
    start = _date(wire["start_date"], "document start_date")
    end = _date(wire["end_date"], "document end_date")
    if start > end:
        raise ValueError("document date interval is reversed")
    for field in ("page_index", "page_count", "record_count", "page_record_count"):
        if type(wire[field]) is not int or wire[field] < (0 if field in {"record_count", "page_record_count"} else 1):
            raise ValueError(f"document {field} must be an exact nonnegative integer")
    if wire["page_index"] > wire["page_count"]:
        raise ValueError("document page identity is inconsistent")
    coverage = wire["coverage"]
    if type(coverage) is not dict or set(coverage) != {"start_date", "end_date", "complete"}:
        raise ValueError("document coverage declaration is invalid")
    if type(coverage["complete"]) is not bool:
        raise ValueError("document coverage complete must be an exact boolean")
    coverage_start = _date(coverage["start_date"], "coverage start_date")
    coverage_end = _date(coverage["end_date"], "coverage end_date")
    if coverage_start > coverage_end or coverage_start < start or coverage_end > end:
        raise ValueError("document coverage is outside its request interval")
    rows = wire["rows"]
    if type(rows) is not list or wire["page_record_count"] != len(rows):
        raise ValueError("document page_record_count does not match rows")
    if wire["record_count"] < wire["page_record_count"]:
        raise ValueError("document total record_count is smaller than this page")
    if not rows and coverage["complete"] is True:
        raise ValueError("empty response cannot claim complete coverage")
    _text(wire["upstream_generation"], "document upstream_generation")
    if wire["pagination_evidence"] not in {
        "signed_single_response_v1", "source_declared_numbered_pages_v1",
    } or type(wire["pagination_evidence"]) is not str:
        raise ValueError("document pagination_evidence is invalid")

    def validate_times(container, label):
        precision = container["published_precision"]
        if precision not in {"timestamp", "date_only"} or type(precision) is not str:
            raise ValueError(f"{label} published_precision is invalid")
        _aware(container["published_at_utc"], f"{label} published_at_utc")
        _aware(container["captured_at_utc"], f"{label} captured_at_utc")
        effective = container["effective_at_utc"]
        evidence = container["effective_time_evidence_hash"]
        if precision == "timestamp":
            _aware(effective, f"{label} effective_at_utc")
            if evidence is not None:
                raise ValueError(f"timestamp {label} cannot carry calendar evidence")
        elif effective is None and evidence is None:
            pass
        elif effective is not None and evidence is not None:
            _aware(effective, f"{label} effective_at_utc")
            _hash(evidence, f"{label} effective_time_evidence_hash")
        else:
            raise ValueError(f"date_only {label} effective-time proof is incomplete")

    validate_times(wire, "document")
    if wire["source_updated_at_utc"] is not None:
        _aware(wire["source_updated_at_utc"], "document source_updated_at_utc")
    for row in rows:
        if type(row) is not dict or not _ROW_TIME_FIELDS <= set(row):
            raise ValueError("range row lacks required visibility fields")
        if _FORBIDDEN_POLICY_FIELDS & set(row):
            raise ValueError("range row contains a forbidden policy conclusion")
        validate_times(row, "row")
    _freeze_json(wire, label="parsed range document")
    return wire


class ParsedRangeDocumentV1:
    """Unprivileged detached range parser DTO; authority lives in source receipts."""

    __slots__ = ("__wire",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise ValueError("use ParsedRangeDocumentV1.from_dict")

    @classmethod
    def from_dict(cls, wire):
        if cls is not ParsedRangeDocumentV1:
            raise ValueError("ParsedRangeDocumentV1 requires exact type")
        validated = _validate_document_wire(wire)
        result = object.__new__(ParsedRangeDocumentV1)
        object.__setattr__(result, "_ParsedRangeDocumentV1__wire", _freeze_json(validated))
        return result

    def to_dict(self) -> dict[str, object]:
        if type(self) is not ParsedRangeDocumentV1:
            raise ValueError("ParsedRangeDocumentV1 requires exact type")
        value = _thaw(object.__getattribute__(self, "_ParsedRangeDocumentV1__wire"))
        assert type(value) is dict
        return value


def _build_fetch_type():
    @dataclass(frozen=True)
    class _FetchRecord:
        reference: weakref.ReferenceType[object]
        fields: tuple[object, ...]

    records: dict[int, _FetchRecord] = {}

    class RangeFetch:
        __slots__ = (
            "request_fingerprint", "range_config_id", "registry_manifest_hash",
            "source", "dataset", "original_url", "headers", "raw_bytes",
            "content_sha256", "captured_at_utc", "parser_id", "parser_version",
            "mapping_version", "normalizer_version", "request_version",
            "published_at_utc", "published_precision", "source_updated_at_utc",
            "effective_at_utc", "effective_time_evidence_hash", "upstream_generation",
            "pagination_evidence", "record_count", "page_record_count", "page_count",
            "__weakref__",
        )

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("RangeFetch cannot be externally constructed")

        def _require(self):
            record = records.get(id(self))
            current = tuple(object.__getattribute__(self, field) for field in self.__slots__[:-1])
            if (
                record is None
                or record.reference() is not self
                or len(current) != len(record.fields)
                or any(
                    type(value) is not type(sealed) or value != sealed
                    for value, sealed in zip(current, record.fields)
                )
            ):
                raise ValueError("range fetch is forged or changed")
            return record

        def to_manifest(self) -> dict[str, object]:
            self._require()
            return {
                "schema_version": "formal-range-fetch-manifest-v1",
                "request_fingerprint": self.request_fingerprint,
                "range_config_id": self.range_config_id,
                "registry_manifest_hash": self.registry_manifest_hash,
                "source": self.source,
                "dataset": self.dataset,
                "original_url": self.original_url,
                "content_sha256": self.content_sha256,
                "captured_at_utc": self.captured_at_utc,
                "parser_id": self.parser_id,
                "parser_version": self.parser_version,
                "mapping_version": self.mapping_version,
                "normalizer_version": self.normalizer_version,
                "request_version": self.request_version,
                "published_at_utc": self.published_at_utc,
                "published_precision": self.published_precision,
                "source_updated_at_utc": self.source_updated_at_utc,
                "effective_at_utc": self.effective_at_utc,
                "effective_time_evidence_hash": self.effective_time_evidence_hash,
                "upstream_generation": self.upstream_generation,
                "pagination_evidence": self.pagination_evidence,
                "record_count": self.record_count,
                "page_record_count": self.page_record_count,
                "page_count": self.page_count,
            }

    def mint(request_wire, config, response, document):
        document_wire = document.to_dict()
        values = (
            hashlib.sha256(_canonical(dict(request_wire))).hexdigest(), config.entry_id,
            request_wire["registry_manifest_hash"], config.source, config.dataset,
            response.original_url, MappingProxyType(dict(response.headers)), response.raw_bytes,
            hashlib.sha256(response.raw_bytes).hexdigest(), response.captured_at_utc,
            config.parser_id, config.parser_version, config.mapping_version,
            config.normalizer_version, config.request_version,
            document_wire["published_at_utc"], document_wire["published_precision"],
            document_wire["source_updated_at_utc"], document_wire["effective_at_utc"],
            document_wire["effective_time_evidence_hash"], document_wire["upstream_generation"],
            document_wire["pagination_evidence"], document_wire["record_count"],
            document_wire["page_record_count"], document_wire["page_count"],
        )
        result = object.__new__(RangeFetch)
        for field, value in zip(RangeFetch.__slots__[:-1], values):
            object.__setattr__(result, field, value)
        identity = id(result)
        def forget(reference, *, identity=identity):
            if records.get(identity) is not None and records[identity].reference is reference:
                records.pop(identity, None)
        records[identity] = _FetchRecord(weakref.ref(result, forget), values)
        return result

    return RangeFetch, mint


RangeFetch, _mint_fetch = _build_fetch_type()
del _build_fetch_type


def _build_source_type():
    require_binding = _require_range_binding
    read_planning_binding = _read_planning_binding
    source_hash_get = _source_hash_get
    manifest_hash_get = _manifest_hash_get
    mint_request = _mint_first_calendar_request
    restore_market_request = _mint_market_request
    mint_continuation = _mint_range_continuation
    mint_fetch = _mint_fetch
    request_record = _range_request_record
    binding_hash_get = RangeBinding.binding_hash.fget
    request_snapshot = _trusted_range_request_snapshot
    fetch_type = RangeFetch
    fetch_require = RangeFetch._require
    fetch_fields = RangeFetch.__slots__[:-1]
    observation_records = {}
    calendar_proof_anchors = [None]

    def install_calendar_proof_authority(anchors):
        if calendar_proof_anchors[0] is not None or type(anchors) is not tuple or len(anchors) != 4:
            raise RuntimeError("calendar proof authority initialization is invalid")
        calendar_proof_anchors[0] = anchors

    def mint_market_request(record, security_id, calendar_coverage, start_date, end_date):
        proof_type, _, _, require_coverage = record.calendar_proof_anchors
        if type(calendar_coverage) is not proof_type:
            raise ValueError("market requests require a genuine calendar coverage proof")
        store = source_store(record)
        payload = require_coverage(
            calendar_coverage, binding=record.binding, range_store=store)
        days = tuple(payload["trading_days"])
        if start_date not in days or end_date not in days:
            raise ValueError("market request bounds require covered trading days")
        return restore_market_request(
            record.binding, security_id, payload["as_of_utc"], start_date, end_date,
            payload["coverage_hash"], store,
        )

    def fetch_snapshot(fetch):
        # Detach both identities and bytes from the original producer registration
        # before any parser callback can mutate the public fetch slots.
        sealed = fetch_require(fetch)
        fields = dict(zip(fetch_fields, sealed.fields))
        manifest = dict(schema_version="formal-range-fetch-manifest-v1", **{
            name: value for name, value in zip(fetch_fields, sealed.fields)
            if name not in ("headers", "raw_bytes")})
        return _canonical(manifest), fields["raw_bytes"]

    def observation_record(value):
        record = observation_records.get(id(value))
        if type(value) is not RangeObservation or record is None or record[0]() is not value:
            raise ValueError("range observation is forged, copied, or foreign")
        store_record(record[1])
        return record

    def observation_wire(value):
        record = observation_record(value)
        return _thaw(record[2]), record[3]

    def require_observation(value, *, current):
        record = observation_record(value)
        if current:
            if record[4]:
                raise ValueError("historical range observation cannot be current")
            store_require_current(record[1], _thaw(record[2]), record[3])
        else:
            fresh = store_read(record[1], record[2]["task"]["id"], historical=True)
            if observation_record(fresh)[3] != record[3]:
                raise ValueError("range observation changed")
        return _thaw(record[2])

    class ObservationType(type):
        def __new__(metaclass, name, bases, namespace):
            if any(isinstance(base, ObservationType) for base in bases):
                raise TypeError("range observation proof type cannot be subclassed")
            return super().__new__(metaclass, name, bases, namespace)

        def __setattr__(self, name, value):
            raise TypeError("range observation proof type is immutable")

        def __delattr__(self, name):
            raise TypeError("range observation proof type is immutable")

    class RangeObservation(metaclass=ObservationType):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise ValueError("range observations require persisted producer receipts")

        def __setattr__(self, name, value):
            raise AttributeError("range observation is immutable")

        def __delattr__(self, name):
            raise AttributeError("range observation is immutable")

        def __getattr__(self, name):
            record = observation_record(self)
            if name == "observation_hash":
                return record[3]
            if name not in ("request", "document", "receipt", "snapshot", "task", "generation"):
                raise AttributeError(name)
            return record[2][name]

        def to_dict(self):
            wire, digest = observation_wire(self)
            return dict(wire, observation_hash=digest)

        def require_current(self):
            require_observation(self, current=True)

        def __copy__(self):
            raise TypeError("range observations cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("range observations cannot be copied")

    def mint_observation(store, wire, historical):
        store_record(store)
        result = object.__new__(RangeObservation)
        semantic = dict(wire)
        semantic["task"] = {"id": wire["task"]["id"]}
        semantic["receipt"] = {key: value for key, value in wire["receipt"].items() if key != "recorded_at"}
        digest = hashlib.sha256(_canonical(semantic)).hexdigest()
        identity = id(result)
        observation_records[identity] = (weakref.ref(result, lambda _: observation_records.pop(identity, None)),
            store, _freeze_json(wire), digest, historical)
        return result

    def describe_request(request):
        sealed = request_record(request)
        return dict(request=dict(sealed.wire), config=dict(sealed.config_wire),
            source_registry_hash=sealed.source_registry_hash, binding_hash=binding_hash_get(sealed.binding),
            parent=sealed.parent)

    def require_execution(request, store):
        sealed = request_record(request)
        if sealed.owner_store is not None and sealed.owner_store is not store:
            raise ValueError("initial market request belongs to another Store")
        if sealed.previous is not None:
            prior = observation_record(sealed.previous)
            origin = store_record(prior[1])
            destination = store_record(store)
            if origin[0] is not destination[0] or origin[1] != destination[1]:
                raise ValueError("range continuation cannot cross StateStore or raw root")
            require_observation(sealed.previous, current=True)

    def continuation(source, previous, mode, *, current):
        record = source_record(source)
        wire = require_observation(previous, current=current)
        config = range_config_for_wire(record, wire["request"])
        if (wire["request"]["registry_manifest_hash"] != manifest_hash_get(record.binding)
                or wire["request"]["range_config_id"] != config.entry_id
                or wire["snapshot"]["task_payload"]["source_registry_hash"] != source_hash_get(record.binding)):
            raise ValueError("range continuation binding differs")
        request = mint_continuation(record.binding, (wire["request"], wire["document"]), mode,
            previous=previous,
            parent=dict(task_id=wire["task"]["id"], observation_hash=observation_record(previous)[3], mode=mode))
        source_record(source)
        return request

    def restore_request(source, wire, previous, mode):
        record = source_record(source)
        # Parent was just reread by the captured store path. Avoid recursive reread.
        if previous is None:
            if wire["kind"] == "calendar_range":
                request = mint_request(record.binding, wire["as_of_utc"])
            elif wire["kind"] == "market_range":
                request = restore_market_request(record.binding, wire["security_id"], wire["as_of_utc"],
                    wire["start_date"], wire["end_date"], wire["calendar_coverage_hash"],
                    source_store(record))
            else:
                raise ValueError("stored range request kind is invalid")
        else:
            prior = observation_record(previous)
            old = _thaw(prior[2])
            config = range_config_for_wire(record, old["request"])
            if (old["request"]["registry_manifest_hash"] != manifest_hash_get(record.binding)
                    or old["request"]["range_config_id"] != config.entry_id
                    or old["snapshot"]["task_payload"]["source_registry_hash"] != source_hash_get(record.binding)):
                raise ValueError("historical range parent binding differs")
            request = mint_continuation(record.binding, (old["request"], old["document"]), mode,
                parent=dict(task_id=old["task"]["id"], observation_hash=prior[3], mode=mode),
                previous=previous)
        if request is None or _canonical(request_record(request).wire) != _canonical(wire):
            raise ValueError("stored range request lacks authentic derivation")
        return request

    @dataclass(frozen=True)
    class _ImplementationRecord:
        parser: object
        normalizer: object
        parser_anchor: tuple[object, object | None]
        normalizer_anchor: tuple[object, object | None]

    @dataclass(frozen=True)
    class _SourceRecord:
        reference: weakref.ReferenceType[object]
        binding: RangeBinding
        transport: object
        transport_anchor: tuple[object, object | None]
        implementations: dict
        implementation_items: tuple[tuple[tuple[str, ...], tuple[object, object]], ...]
        selected: dict[str, _ImplementationRecord]
        config_wires: dict[str, dict[str, object]]
        calendar_proof_anchors: tuple[object, object, object, object]
        store_reference: weakref.ReferenceType[object] | None

    records: dict[int, _SourceRecord] = {}

    def range_config_for_wire(record, wire):
        identity = read_planning_binding(record.binding)
        kind = wire["kind"]
        config = identity["calendar_config" if kind == "calendar_range" else "market_config"]
        if (type(config) is not RangeConfig or _range_config_to_dict(config) != record.config_wires.get(kind)):
            raise FormalTerminalSourceError("range request config differs from sealed source")
        return config

    def binding_identity(binding):
        identity = read_planning_binding(binding)
        return {
            "registry_manifest_hash": identity["registry_manifest_hash"],
            "source_registry_hash": identity["source_registry_hash"],
            "binding_hash": identity["binding_hash"],
            "rule_id": identity["rule_id"],
            "exchange": identity["exchange"],
            "calendar_config": _range_config_to_dict(identity["calendar_config"]),
            "market_config": _range_config_to_dict(identity["market_config"]),
        }

    def range_config_for_request(record, request):
        sealed = request_record(request)
        if binding_identity(sealed.binding) != binding_identity(record.binding):
            raise FormalTerminalSourceError("range request belongs to another source binding")
        config = range_config_for_wire(record, sealed.wire)
        if sealed.config_wire != record.config_wires[sealed.wire["kind"]]:
            raise FormalTerminalSourceError("range request config differs from sealed source")
        return config

    def source_record(source: object) -> _SourceRecord:
        record = records.get(id(source))
        if type(source) is not FormalRangeSource or record is None or record.reference() is not source:
            raise FormalTerminalSourceError("formal range source is forged or unregistered")
        try:
            current_items = tuple(record.implementations.items())
            items_unchanged = (
                len(current_items) == len(record.implementation_items)
                and all(
                    current_key == sealed_key and current_value is sealed_value
                    for (current_key, current_value), (sealed_key, sealed_value)
                    in zip(current_items, record.implementation_items)
                )
            )
            identity = read_planning_binding(record.binding)
            unchanged = (
                source._binding is record.binding
                and source._transport is record.transport
                and source._implementations is record.implementations
                and items_unchanged
                and _callable_anchor(record.transport, "send") == record.transport_anchor
                and all(_callable_anchor(selected.parser, "parse") == selected.parser_anchor
                        and _callable_anchor(selected.normalizer, "normalize") == selected.normalizer_anchor
                        for selected in record.selected.values())
                and all(type(identity[name + "_config"]) is RangeConfig
                        and _range_config_to_dict(identity[name + "_config"]) == record.config_wires[name + "_range"]
                        for name in ("calendar", "market"))
                and calendar_proof_anchors[0] is record.calendar_proof_anchors
            )
        except (AttributeError, TypeError, ValueError):
            unchanged = False
        if not unchanged:
            raise FormalTerminalSourceError("formal range source dependencies changed")
        return record

    def bind_source_store(source, store):
        sealed = source_record(source)
        current = sealed.store_reference
        if current is None:
            object.__setattr__(sealed, "store_reference", weakref.ref(store))
        elif current() is not store:
            raise FormalTerminalSourceError("formal range source belongs to another Store")
        source_record(source)

    def source_store(record):
        reference = record.store_reference
        store = None if reference is None else reference()
        if store is None:
            raise FormalTerminalSourceError(
                "market requests require an owning FormalRangeStore")
        return store

    def require_acquisition_authority(source, request, previous):
        # Error classification must not hide transport/parser callback mutation.
        # Parent replay can itself invoke callbacks, so check both sides of it.
        source_record(source)
        request_record(request)
        if previous is not None:
            require_observation(previous, current=True)
        source_record(source)
        request_record(request)

    class FormalRangeSource:
        """One binding's sealed transport and exact range implementation registry."""

        def __init__(self, binding, *, transport, implementations):
            if type(binding) is not RangeBinding:
                raise ValueError("range source requires an exact genuine RangeBinding")
            identity_view = read_planning_binding(binding)
            configs = {kind: identity_view[name] for kind, name in (
                ("calendar_range", "calendar_config"), ("market_range", "market_config"))}
            if any(type(config) is not RangeConfig or config.kind != kind
                   for kind, config in configs.items()):
                raise ValueError("range binding planning configs are invalid")
            if calendar_proof_anchors[0] is None:
                raise RuntimeError("calendar proof authority was not eagerly initialized")
            if type(implementations) is not dict:
                raise ValueError("range implementations must be an exact dict")
            transport_anchor = _callable_anchor(transport, "send")
            items = tuple(implementations.items())
            sealed = {}
            for key, value in items:
                if (type(key) is not tuple or len(key) != 5
                        or any(type(part) is not str or not part for part in key)):
                    raise ValueError("range implementation key must contain five exact versions")
                if type(value) is not tuple or len(value) != 2:
                    raise ValueError("range implementation value must be a (parser, normalizer) tuple")
                parser, normalizer = value
                sealed[key] = _ImplementationRecord(
                    parser, normalizer, _callable_anchor(parser, "parse"),
                    _callable_anchor(normalizer, "normalize"),
                )
            selected = {}
            for kind, config in configs.items():
                key = (config.parser_id, config.parser_version, config.mapping_version,
                       config.normalizer_version, config.request_version)
                selected[kind] = sealed.get(key)
            if any(value is None for value in selected.values()):
                raise ValueError("signed range implementation is not registered")
            self._binding = binding
            self._transport = transport
            self._implementations = implementations
            identity = id(self)
            def forget(reference, *, identity=identity):
                if records.get(identity) is not None and records[identity].reference is reference:
                    records.pop(identity, None)
            records[identity] = _SourceRecord(
                weakref.ref(self, forget), binding, transport, transport_anchor,
                implementations, items, selected,
                {kind: _range_config_to_dict(config) for kind, config in configs.items()},
                calendar_proof_anchors[0], None,
            )
            source_record(self)

        def first_calendar_request(self, as_of_utc: str) -> FormalRangeRequestV1:
            record = source_record(self)
            request = mint_request(record.binding, as_of_utc)
            source_record(self)
            return request

        def range_config(self, request: FormalRangeRequestV1) -> RangeConfig:
            record = source_record(self)
            return range_config_for_request(record, request)

        def market_requests(self, security_id: str, *, calendar_coverage) -> tuple[FormalRangeRequestV1, ...]:
            record = source_record(self)
            proof_type, _, _, require_coverage = record.calendar_proof_anchors
            if type(calendar_coverage) is not proof_type:
                raise ValueError("market requests require a genuine calendar coverage proof")
            payload = require_coverage(
                calendar_coverage, binding=record.binding,
                range_store=source_store(record))
            days = tuple(payload["trading_days"])[-250:]
            if not days:
                raise ValueError("calendar proof has no trading days")
            config = read_planning_binding(record.binding)["market_config"]
            groups = []
            cursor = len(days)
            while cursor:
                end = date.fromisoformat(days[cursor - 1])
                start_index = cursor - 1
                while start_index > 0:
                    candidate = date.fromisoformat(days[start_index - 1])
                    if (end - candidate).days + 1 > config.max_calendar_days_per_request:
                        break
                    start_index -= 1
                groups.append((days[start_index], days[cursor - 1]))
                cursor = start_index
            requests = tuple(mint_market_request(
                record, security_id, calendar_coverage, start, end,
            ) for start, end in groups)
            source_record(self)
            return requests

        def previous_calendar_request(self, previous: RangeObservation) -> FormalRangeRequestV1 | None:
            return continuation(self, previous, "previous_calendar", current=True)

        def next_page(self, previous: RangeObservation) -> FormalRangeRequestV1 | None:
            return continuation(self, previous, "next_page", current=True)

        @staticmethod
        def _parse(record, request_wire, config, raw_bytes):
            if type(raw_bytes) is not bytes:
                raise FormalTerminalSourceError("range raw_bytes must be exact bytes")
            parser_request = dict(request_wire)
            parser_config = _range_config_to_dict(config)
            try:
                selected = record.selected[config.kind]
                parsed = selected.parser.parse(
                    raw_bytes, request=parser_request, config=dict(parser_config)
                )
                source_record_from = record.reference()
                if source_record_from is None:
                    raise FormalTerminalSourceError("formal range source expired during parsing")
                source_record(source_record_from)
                normalized = selected.normalizer.normalize(
                    parsed, request=dict(request_wire), config=dict(parser_config)
                )
                source_record(source_record_from)
                document = ParsedRangeDocumentV1.from_dict(normalized)
            except FormalRangeAcquisitionError as error:
                # Registered implementations cannot classify saved replay as
                # live acquisition. Only fetch's authenticated boundary can.
                raise FormalTerminalSourceError(str(error)) from error
            except FormalTerminalSourceError:
                raise
            except Exception as error:
                raise FormalTerminalSourceError("registered range parser or normalizer failed") from error
            wire = document.to_dict()
            expected = {
                "request_fingerprint": hashlib.sha256(_canonical(dict(request_wire))).hexdigest(),
                "source": request_wire["source"], "dataset": request_wire["dataset"],
                "security_id": request_wire["security_id"], "exchange": request_wire["exchange"],
                "start_date": request_wire["start_date"], "end_date": request_wire["end_date"],
                "parser_id": config.parser_id, "parser_version": config.parser_version,
                "mapping_version": config.mapping_version,
                "normalizer_version": config.normalizer_version,
                "request_version": config.request_version, "page_index": request_wire["page_index"],
            }
            if any(type(wire[key]) is not type(value) or wire[key] != value for key, value in expected.items()):
                raise FormalTerminalSourceError("parsed range document identity differs from request or config")
            if config.pagination == "single_response_v1":
                if wire["page_index"] != 1 or wire["page_count"] != 1:
                    raise FormalTerminalSourceError("single-response range document claims pagination")
                if wire["pagination_evidence"] != "signed_single_response_v1":
                    raise FormalTerminalSourceError("single-response pagination evidence is invalid")
                if wire["record_count"] != wire["page_record_count"]:
                    raise FormalTerminalSourceError("single-response total differs from page rows")
            elif wire["page_count"] > config.max_pages:
                raise FormalTerminalSourceError("range document pagination exceeds signed budget")
            elif wire["pagination_evidence"] != "source_declared_numbered_pages_v1":
                raise FormalTerminalSourceError("numbered pagination lacks source declaration")
            return document

        def fetch_verified(self, request: FormalRangeRequestV1) -> RangeFetch:
            record = source_record(self)
            try:
                previous = request_record(request).previous
            except ValueError as error:
                raise FormalTerminalSourceError(str(error)) from error
            if previous is not None:
                require_observation(previous, current=True)
            try:
                request_wire, request_config, request_source_hash = (
                    request_snapshot(request)
                )
            except ValueError as error:
                raise FormalTerminalSourceError(str(error)) from error
            config = range_config_for_request(record, request)
            if (
                request_wire["registry_manifest_hash"] != manifest_hash_get(record.binding)
                or request_source_hash != source_hash_get(record.binding)
                or request_config != record.config_wires[config.kind]
                or request_config != _range_config_to_dict(config)
            ):
                raise FormalTerminalSourceError("range request config differs from sealed source")
            sent = _transport_request(config, request_wire)
            try:
                response = record.transport.send(sent)
            except (FormalRetryableSourceError, FormalSourceBlocked):
                require_acquisition_authority(self, request, previous)
                raise
            except Exception as error:
                require_acquisition_authority(self, request, previous)
                raise FormalRetryableSourceError("range transport failed") from error
            source_record(self)
            try:
                response = _snapshot_transport_response(response)
                _classify_transport_response(response)
                if _https_host(response.original_url, "range response original_url") != _https_host(
                    config.endpoint_url, "signed range endpoint_url"
                ):
                    raise FormalTerminalSourceError("range response redirected outside the signed host")
                document = trusted_parse(record, request_wire, config, response.raw_bytes)
                if document.to_dict()["captured_at_utc"] != response.captured_at_utc:
                    raise FormalTerminalSourceError("document capture time differs from transport")
            except FormalRetryableSourceError:
                require_acquisition_authority(self, request, previous)
                raise
            except FormalTerminalSourceError as error:
                # Parser callbacks may have changed authority or invalidated a
                # parent. Those failures must escape as integrity failures.
                require_acquisition_authority(self, request, previous)
                raise FormalRangeAcquisitionError(str(error)) from error
            source_record(self)
            if previous is not None:
                require_observation(previous, current=True)
                source_record(self)
            return mint_fetch(request_wire, config, response, document)

        def parse_verified_snapshot(self, request: FormalRangeRequestV1, *, raw_bytes: bytes,
                                    manifest: dict) -> ParsedRangeDocumentV1:
            record = source_record(self)
            try:
                request_wire, request_config, request_source_hash = (
                    request_snapshot(request)
                )
            except ValueError as error:
                raise FormalTerminalSourceError(str(error)) from error
            config = range_config_for_request(record, request)
            if (
                request_wire["registry_manifest_hash"] != manifest_hash_get(record.binding)
                or request_source_hash != source_hash_get(record.binding)
                or request_config != record.config_wires[config.kind]
                or request_config != _range_config_to_dict(config)
            ):
                raise FormalTerminalSourceError("range request config differs from sealed source")
            expected_keys = frozenset({
                "schema_version", "request_fingerprint", "range_config_id",
                "registry_manifest_hash", "source", "dataset", "original_url",
                "content_sha256", "captured_at_utc", "parser_id", "parser_version",
                "mapping_version", "normalizer_version", "request_version",
                "published_at_utc", "published_precision", "source_updated_at_utc",
                "effective_at_utc", "effective_time_evidence_hash", "upstream_generation",
                "pagination_evidence", "record_count", "page_record_count", "page_count",
            })
            if type(manifest) is not dict or set(manifest) != expected_keys:
                raise FormalTerminalSourceError("range manifest has unknown or missing keys")
            expected = {
                "schema_version": "formal-range-fetch-manifest-v1",
                "request_fingerprint": hashlib.sha256(_canonical(request_wire)).hexdigest(),
                "range_config_id": config.entry_id,
                "registry_manifest_hash": request_wire["registry_manifest_hash"],
                "source": config.source, "dataset": config.dataset,
                "content_sha256": hashlib.sha256(raw_bytes).hexdigest() if type(raw_bytes) is bytes else None,
                "parser_id": config.parser_id, "parser_version": config.parser_version,
                "mapping_version": config.mapping_version,
                "normalizer_version": config.normalizer_version,
                "request_version": config.request_version,
            }
            if any(type(manifest.get(key)) is not type(value) or manifest.get(key) != value
                   for key, value in expected.items()):
                raise FormalTerminalSourceError("range manifest identity or content hash is invalid")
            try:
                if _https_host(manifest["original_url"], "range manifest original_url") != _https_host(
                    config.endpoint_url, "signed range endpoint_url"
                ):
                    raise FormalTerminalSourceError("range manifest URL host is invalid")
                _aware(manifest["captured_at_utc"], "range manifest captured_at_utc")
            except ValueError as error:
                raise FormalTerminalSourceError(str(error)) from error
            document = trusted_parse(record, request_wire, config, raw_bytes)
            document_wire = document.to_dict()
            for key in (
                "published_at_utc", "published_precision", "source_updated_at_utc",
                "effective_at_utc", "effective_time_evidence_hash", "upstream_generation",
                "pagination_evidence", "record_count", "page_record_count", "page_count",
                "captured_at_utc",
            ):
                if type(manifest[key]) is not type(document_wire[key]) or manifest[key] != document_wire[key]:
                    raise FormalTerminalSourceError("range manifest source version differs from parser")
            return document

    trusted_parse = FormalRangeSource._parse
    from . import formal_range_store as store_module
    Store, store_read, store_require_current, store_record = store_module._build_range_store_type(
        describe_request=describe_request, restore_request=restore_request,
        source_type=FormalRangeSource, source_binding=lambda source: source_record(source).binding,
        bind_source_store=bind_source_store,
        source_parse=FormalRangeSource.parse_verified_snapshot, fetch_type=fetch_type,
        fetch_snapshot=fetch_snapshot, mint_observation=mint_observation, observation_wire=observation_wire,
        require_execution=require_execution)
    store_module.FormalRangeStore = Store
    store_module.RangeObservation = RangeObservation
    del store_module._build_range_store_type
    observation_anchors = (RangeObservation, RangeObservation.require_current, RangeObservation.to_dict)

    def observation_authority():
        """Original type/current verifier/wire reader only; never a mint."""
        return observation_anchors

    return FormalRangeSource, RangeObservation, observation_authority, install_calendar_proof_authority


FormalRangeSource, RangeObservation, _range_observation_authority, _install_calendar_proof_authority = _build_source_type()
del _build_source_type

# Complete the two-module cycle before either module becomes usable.  The market
# module defines its proof owner before importing this module, so both import
# orders reach this point with the original anchors available.
from . import formal_policy_market as _formal_policy_market
_install_calendar_proof_authority(_formal_policy_market._calendar_proof_authority())
del _formal_policy_market, _install_calendar_proof_authority
del _mint_first_calendar_request, _mint_market_request, _mint_range_continuation
del _mint_fetch, _range_request_record


__all__ = [
    "FormalRangeRequestV1", "FormalRangeSource", "ParsedRangeDocumentV1", "RangeFetch", "RangeObservation",
    "backward_interval", "page_successor",
    "range_request_binding", "FormalRangeAcquisitionError",
]
