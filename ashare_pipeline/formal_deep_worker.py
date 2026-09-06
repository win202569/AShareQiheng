"""Typed, fail-closed Task 6A formal collection contracts.

Execution, receipt recovery, context normalization, universe finalization, and
feature rebuilding intentionally belong to later Task 6 deliveries.  This
module establishes the immutable task boundary and the only supported way to
construct a runtime from a verified registry bundle.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
from dataclasses import InitVar, asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from types import MappingProxyType
from typing import Literal, Protocol

from .formal_evidence import OfficialRequest, OfficialSnapshotRef, VerifiedCalendarBinding
from .formal_context_schema import FormalContextRequest
from .formal_feature_contract import SignedFormalFeatureRegistry, load_signed_feature_registry
from .formal_financial_features import select_visible_formal_facts
from .formal_financial_schema import (
    FormalFinancialFact,
    SignedFinancialMappingRegistry,
    extract_formal_financial_facts,
)
from .formal_registry_manifest import FormalRegistryBundleLoader, VerifiedRegistryBundle
from .formal_sources import (
    CalendarSelector,
    EffectiveTimeResolver,
    FormalOfficialSourceAdapter,
    FormalRetryableSourceError,
    FormalSourceBlocked,
    FormalTerminalSourceError,
    OfficialDocumentParser,
    OfficialTransport,
    SignedSourceRegistry,
    SourcePolicy,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECURITY_ID = re.compile(r"^(?:SH|SZ|BJ)[0-9]{6}$")
_STATEMENT_DATASETS = frozenset({"balance_sheet", "profit_sheet", "cash_flow_sheet"})
_FORMAL_KINDS = frozenset(
    {
        "formal_statement",
        "formal_context",
        "formal_universe_source",
        "formal_universe_finalize",
        "formal_feature_build",
    }
)
_STATEMENT_EXECUTION_KINDS = ("formal_statement",)
_STATEMENT_LEASE_SECONDS = 120
# D1 seals this exact non-cyclic baseline into formal-feature-input-v2.  Keep
# the task-generation wire explicit rather than importing D1's private detail.
_FEATURE_HISTORY_GATE_VERSION = "formal-history-gate-noncyclic-v1"


class CalendarBindingPending(ValueError):
    """A signed date-only request cannot proceed until its calendar is verified."""


class _LostFormalTaskLease(RuntimeError):
    def __init__(self, remote_attempts: int) -> None:
        self.remote_attempts = remote_attempts
        super().__init__("formal task lease ownership was lost")


class _RetryableFormalTask(RuntimeError):
    def __init__(self, remote_attempts: int, source: str, *, circuit_open: bool) -> None:
        self.remote_attempts = remote_attempts
        self.source = source
        self.circuit_open = circuit_open
        super().__init__("formal task has a retryable source failure")


class _TerminalFormalTask(RuntimeError):
    def __init__(self, remote_attempts: int, code: str) -> None:
        self.remote_attempts = remote_attempts
        self.code = code
        super().__init__("formal task has a terminal failure")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an already-trimmed nonempty string")
    return value


def _require_hash(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _require_timestamp(value: object, label: str) -> str:
    text = _require_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an aware UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be an aware UTC timestamp")
    normalized = parsed.astimezone(timezone.utc).isoformat()
    if text != normalized:
        raise ValueError(f"{label} must be a canonical aware UTC timestamp")
    return text


def _require_iso_date(value: object, label: str) -> str:
    text = _require_text(value, label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{label} must be a canonical ISO date") from error
    if parsed.isoformat() != text:
        raise ValueError(f"{label} must be a canonical ISO date")
    return text


def _require_security_id(value: object) -> str:
    if type(value) is not str or _SECURITY_ID.fullmatch(value) is None:
        raise ValueError("security_id must be SH/SZ/BJ plus six digits")
    return value


def _canonical_roles(value: object, *, require_order: bool = True) -> tuple[tuple[str, str], ...]:
    try:
        pairs = tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError("relevant_registry_hashes must be role/hash pairs") from error
    normalized: list[tuple[str, str]] = []
    for pair in pairs:
        if type(pair) is not tuple or len(pair) != 2:
            raise ValueError("relevant_registry_hashes must be role/hash pairs")
        role, registry_hash = pair
        normalized.append((_require_text(role, "registry role"), _require_hash(registry_hash, "registry hash")))
    if not normalized or len({role for role, _ in normalized}) != len(normalized):
        raise ValueError("relevant_registry_hashes must have distinct nonempty roles")
    canonical = tuple(sorted(normalized))
    if require_order and pairs != canonical:
        raise ValueError("relevant_registry_hashes must be lexically ordered")
    return canonical


def _validate_calendar_pair(
    *,
    registry_manifest_hash: str,
    exchange: str | None,
    as_of_utc: str | None = None,
    calendar_prerequisite_task_id: str | None,
    calendar_binding: VerifiedCalendarBinding | None,
) -> tuple[str | None, VerifiedCalendarBinding | None]:
    if (calendar_prerequisite_task_id is None) != (calendar_binding is None):
        raise ValueError("calendar prerequisite and binding must be present together or both absent")
    if calendar_binding is None:
        return None, None
    if type(calendar_binding) is not VerifiedCalendarBinding:
        raise ValueError("calendar binding must have exact type VerifiedCalendarBinding")
    prerequisite = _require_text(calendar_prerequisite_task_id, "calendar prerequisite task id")
    _require_text(calendar_binding.snapshot_id, "calendar snapshot id")
    _require_hash(calendar_binding.manifest_sha256, "calendar manifest")
    _require_timestamp(calendar_binding.freeze_at_utc, "calendar freeze")
    _require_hash(calendar_binding.registry_manifest_hash, "calendar registry manifest")
    _require_hash(calendar_binding.selector_hash, "calendar selector")
    if calendar_binding.registry_manifest_hash != registry_manifest_hash:
        raise ValueError("calendar binding registry manifest does not match payload")
    if calendar_binding.prerequisite_task_id != prerequisite:
        raise ValueError("calendar binding prerequisite does not match payload")
    if as_of_utc is not None and calendar_binding.freeze_at_utc != as_of_utc:
        raise ValueError("calendar binding freeze must exactly equal payload as_of_utc")
    if exchange is not None and calendar_binding.exchange != exchange:
        raise ValueError("calendar binding exchange does not match payload")
    return prerequisite, calendar_binding


def _binding_wire(binding: VerifiedCalendarBinding) -> dict[str, object]:
    return {
        "exchange": binding.exchange,
        "freeze_at_utc": binding.freeze_at_utc,
        "manifest_sha256": binding.manifest_sha256,
        "prerequisite_task_id": binding.prerequisite_task_id,
        "registry_manifest_hash": binding.registry_manifest_hash,
        "selector_hash": binding.selector_hash,
        "snapshot_id": binding.snapshot_id,
    }


def _sealed_context_request_wire(request: FormalContextRequest | None) -> dict[str, object]:
    if type(request) is not FormalContextRequest:
        raise ValueError("FormalContextTaskPayload requires an exact resolver-minted Context request capability")
    try:
        raw = request.canonical_bytes()
        wire = json.loads(raw)
    except Exception as error:
        raise ValueError("Context request capability is invalid") from error
    if type(raw) is not bytes or type(wire) is not dict or _canonical_bytes(wire) != raw:
        raise ValueError("Context request capability is not canonical")
    required = {
        "context_kind", "scope_key", "security_id", "as_of_utc", "official_request",
        "request_version", "upstream_generation", "refresh_generation", "registry_manifest_hash",
        "relevant_registry_hashes", "calendar_binding",
    }
    if not required.issubset(wire):
        raise ValueError("Context request capability is incomplete")
    return wire


def _exact_official_request_wire(value: object) -> dict[str, object]:
    if type(value) is not OfficialRequest:
        raise ValueError("Context payload official_request must have exact type OfficialRequest")
    source = _require_text(value.source, "Context official request source")
    dataset = _require_text(value.dataset, "Context official request dataset")
    security_id = None if value.security_id is None else _require_security_id(value.security_id)
    period_or_date = None if value.period_or_date is None else _require_text(
        value.period_or_date, "Context official request period_or_date"
    )
    exchange = value.exchange
    if exchange is not None and (type(exchange) is not str or exchange not in {"SH", "SZ", "BJ"}):
        raise ValueError("Context official request exchange is invalid")
    return {
        "source": source,
        "dataset": dataset,
        "security_id": security_id,
        "period_or_date": period_or_date,
        "exchange": exchange,
    }


def _exact_context_roles_wire(value: object) -> tuple[tuple[tuple[str, str], ...], list[list[str]]]:
    roles = _canonical_roles(value)
    return roles, [[role, digest] for role, digest in roles]


def derive_collection_refresh_generation(
    *,
    upstream_generation: str,
    registry_manifest_hash: str,
    relevant_registry_hashes: Mapping[str, str],
    calendar_selector: CalendarSelector | None = None,
    calendar_binding: VerifiedCalendarBinding | None = None,
) -> str:
    """Derive the sole collection generation from authoritative immutable inputs."""

    upstream = _require_text(upstream_generation, "upstream_generation")
    root = _require_hash(registry_manifest_hash, "registry_manifest_hash")
    if not isinstance(relevant_registry_hashes, Mapping):
        raise ValueError("relevant_registry_hashes must be a mapping")
    roles = _canonical_roles(
        tuple((role, value) for role, value in relevant_registry_hashes.items()), require_order=False
    )
    if (calendar_selector is None) != (calendar_binding is None):
        raise ValueError("calendar selector and binding must be present together or both absent")
    generation: dict[str, object] = {
        "registry_manifest_hash": root,
        "relevant_registry_hashes": [[role, value] for role, value in roles],
        "upstream_generation": upstream,
    }
    if calendar_selector is not None:
        if type(calendar_selector) is not CalendarSelector or type(calendar_binding) is not VerifiedCalendarBinding:
            raise ValueError("calendar selector and binding have invalid types")
        if calendar_binding.registry_manifest_hash != root:
            raise ValueError("calendar binding registry manifest does not match generation")
        if calendar_binding.selector_hash != calendar_selector.selector_hash:
            raise ValueError("calendar selector and binding do not match")
        if calendar_binding.exchange != calendar_selector.exchange:
            raise ValueError("calendar selector and binding exchange do not match")
        _validate_calendar_pair(
            registry_manifest_hash=root,
            exchange=calendar_selector.exchange,
            calendar_prerequisite_task_id=calendar_binding.prerequisite_task_id,
            calendar_binding=calendar_binding,
        )
        generation["calendar_binding"] = _binding_wire(calendar_binding)
        generation["calendar_selector"] = {
            "as_of_rule": calendar_selector.as_of_rule,
            "context_kind": calendar_selector.context_kind,
            "exchange": calendar_selector.exchange,
            "scope_key": calendar_selector.scope_key,
        }
    return hashlib.sha256(_canonical_bytes(generation)).hexdigest()


@dataclass(frozen=True)
class FormalStatementTaskPayload:
    security_id: str
    dataset: Literal["balance_sheet", "profit_sheet", "cash_flow_sheet"]
    report_period: str
    as_of_utc: str
    source: str
    request_version: str
    source_registry_hash: str
    mapping_registry_hash: str
    upstream_generation: str
    refresh_generation: str
    registry_manifest_hash: str
    relevant_registry_hashes: tuple[tuple[str, str], ...]
    calendar_prerequisite_task_id: str | None
    calendar_binding: VerifiedCalendarBinding | None

    def __post_init__(self) -> None:
        security = _require_security_id(self.security_id)
        if self.dataset not in _STATEMENT_DATASETS:
            raise ValueError("statement dataset is unsupported")
        _require_iso_date(self.report_period, "report_period")
        _require_timestamp(self.as_of_utc, "as_of_utc")
        _require_text(self.source, "source")
        _require_text(self.request_version, "request_version")
        _require_hash(self.source_registry_hash, "source_registry_hash")
        _require_hash(self.mapping_registry_hash, "mapping_registry_hash")
        _require_text(self.upstream_generation, "upstream_generation")
        _require_hash(self.refresh_generation, "refresh_generation")
        root = _require_hash(self.registry_manifest_hash, "registry_manifest_hash")
        roles = _canonical_roles(self.relevant_registry_hashes)
        if roles != (("mapping", self.mapping_registry_hash), ("source", self.source_registry_hash)):
            raise ValueError("statement relevant source/mapping registry hashes must exactly match payload")
        _validate_calendar_pair(
            registry_manifest_hash=root,
            exchange=security[:2],
            as_of_utc=self.as_of_utc,
            calendar_prerequisite_task_id=self.calendar_prerequisite_task_id,
            calendar_binding=self.calendar_binding,
        )


@dataclass(frozen=True)
class FormalContextTaskPayload:
    context_kind: str
    scope_key: str
    security_id: str | None
    as_of_utc: str
    official_request: OfficialRequest
    source: str
    request_version: str
    upstream_generation: str
    refresh_generation: str
    registry_manifest_hash: str
    relevant_registry_hashes: tuple[tuple[str, str], ...]
    calendar_prerequisite_task_id: str | None
    calendar_binding: VerifiedCalendarBinding | None
    context_request: InitVar[FormalContextRequest | None] = None

    def __post_init__(self, context_request: FormalContextRequest | None) -> None:
        wire = _sealed_context_request_wire(context_request)
        expected_binding = wire["calendar_binding"]
        binding = VerifiedCalendarBinding(**expected_binding) if expected_binding is not None else None
        expected_roles = tuple(tuple(pair) for pair in wire["relevant_registry_hashes"])
        expected_official = OfficialRequest(**wire["official_request"])
        expected = {
            "context_kind": wire["context_kind"],
            "scope_key": wire["scope_key"],
            "security_id": wire["security_id"],
            "as_of_utc": wire["as_of_utc"],
            "official_request": expected_official,
            "source": wire["official_request"]["source"],
            "request_version": wire["request_version"],
            "upstream_generation": wire["upstream_generation"],
            "refresh_generation": wire["refresh_generation"],
            "registry_manifest_hash": wire["registry_manifest_hash"],
            "relevant_registry_hashes": expected_roles,
            "calendar_prerequisite_task_id": None if binding is None else binding.prerequisite_task_id,
            "calendar_binding": binding,
        }
        context_kind = _require_text(self.context_kind, "Context payload context_kind")
        scope_key = _require_text(self.scope_key, "Context payload scope_key")
        security_id = None if self.security_id is None else _require_security_id(self.security_id)
        as_of_utc = _require_timestamp(self.as_of_utc, "Context payload as_of_utc")
        official_wire = _exact_official_request_wire(self.official_request)
        source = _require_text(self.source, "Context payload source")
        request_version = _require_text(self.request_version, "Context payload request_version")
        upstream_generation = _require_text(self.upstream_generation, "Context payload upstream_generation")
        refresh_generation = _require_hash(self.refresh_generation, "Context payload refresh_generation")
        registry_manifest_hash = _require_hash(self.registry_manifest_hash, "Context payload registry_manifest_hash")
        roles, roles_wire = _exact_context_roles_wire(self.relevant_registry_hashes)
        if self.calendar_binding is not None and type(self.calendar_binding) is not VerifiedCalendarBinding:
            raise ValueError("Context payload calendar_binding must have exact type VerifiedCalendarBinding")
        prerequisite = self.calendar_prerequisite_task_id
        if prerequisite is not None:
            prerequisite = _require_text(prerequisite, "Context payload calendar prerequisite task id")
        exchange = official_wire["exchange"] or (security_id[:2] if security_id else None)
        _validate_calendar_pair(
            registry_manifest_hash=registry_manifest_hash, exchange=exchange, as_of_utc=as_of_utc,
            calendar_prerequisite_task_id=prerequisite, calendar_binding=self.calendar_binding,
        )
        candidate = {
            "context_kind": context_kind, "scope_key": scope_key, "security_id": security_id,
            "as_of_utc": as_of_utc, "official_request": official_wire, "source": source,
            "request_version": request_version, "upstream_generation": upstream_generation,
            "refresh_generation": refresh_generation, "registry_manifest_hash": registry_manifest_hash,
            "relevant_registry_hashes": roles_wire, "calendar_prerequisite_task_id": prerequisite,
            "calendar_binding": None if self.calendar_binding is None else _binding_wire(self.calendar_binding),
        }
        sealed = {
            "context_kind": expected["context_kind"], "scope_key": expected["scope_key"],
            "security_id": expected["security_id"], "as_of_utc": expected["as_of_utc"],
            "official_request": _exact_official_request_wire(expected_official), "source": expected["source"],
            "request_version": expected["request_version"], "upstream_generation": expected["upstream_generation"],
            "refresh_generation": expected["refresh_generation"],
            "registry_manifest_hash": expected["registry_manifest_hash"],
            "relevant_registry_hashes": [[role, digest] for role, digest in expected_roles],
            "calendar_prerequisite_task_id": expected["calendar_prerequisite_task_id"],
            "calendar_binding": None if binding is None else _binding_wire(binding),
        }
        if _canonical_bytes(candidate) != _canonical_bytes(sealed):
            raise ValueError("Context request capability does not match canonical payload")
        for field_name, sealed_value in expected.items():
            object.__setattr__(self, field_name, sealed_value)

    @classmethod
    def from_request(cls, request: FormalContextRequest) -> "FormalContextTaskPayload":
        wire = _sealed_context_request_wire(request)
        binding_wire = wire["calendar_binding"]
        binding = VerifiedCalendarBinding(**binding_wire) if binding_wire is not None else None
        return cls(
            context_kind=wire["context_kind"], scope_key=wire["scope_key"], security_id=wire["security_id"],
            as_of_utc=wire["as_of_utc"], official_request=OfficialRequest(**wire["official_request"]),
            source=wire["official_request"]["source"], request_version=wire["request_version"],
            upstream_generation=wire["upstream_generation"], refresh_generation=wire["refresh_generation"],
            registry_manifest_hash=wire["registry_manifest_hash"],
            relevant_registry_hashes=tuple(tuple(pair) for pair in wire["relevant_registry_hashes"]),
            calendar_prerequisite_task_id=None if binding is None else binding.prerequisite_task_id,
            calendar_binding=binding, context_request=request,
        )


@dataclass(frozen=True)
class FormalUniverseSourceTaskPayload:
    exchange: Literal["SH", "SZ", "BJ"]
    as_of_utc: str
    official_request: OfficialRequest
    source: str
    request_version: str
    upstream_generation: str
    refresh_generation: str
    registry_manifest_hash: str
    relevant_registry_hashes: tuple[tuple[str, str], ...]
    calendar_prerequisite_task_id: str | None
    calendar_binding: VerifiedCalendarBinding | None

    def __post_init__(self) -> None:
        if self.exchange not in {"SH", "SZ", "BJ"}:
            raise ValueError("universe exchange must be SH, SZ, or BJ")
        _require_timestamp(self.as_of_utc, "as_of_utc")
        if type(self.official_request) is not OfficialRequest:
            raise ValueError("official_request must have exact type OfficialRequest")
        if (
            self.official_request.dataset != "universe_listing"
            or self.official_request.security_id is not None
            or self.official_request.exchange != self.exchange
            or self.official_request.source != self.source
        ):
            raise ValueError("universe request must be a global exchange-scoped universe_listing request")
        _require_text(self.source, "source")
        _require_text(self.request_version, "request_version")
        _require_text(self.upstream_generation, "upstream_generation")
        _require_hash(self.refresh_generation, "refresh_generation")
        root = _require_hash(self.registry_manifest_hash, "registry_manifest_hash")
        _canonical_roles(self.relevant_registry_hashes)
        _validate_calendar_pair(
            registry_manifest_hash=root, exchange=self.exchange, as_of_utc=self.as_of_utc,
            calendar_prerequisite_task_id=self.calendar_prerequisite_task_id,
            calendar_binding=self.calendar_binding,
        )


@dataclass(frozen=True)
class FormalUniverseFinalizeTaskPayload:
    as_of_utc: str
    registry_manifest_hash: str
    source_task_ids: tuple[str, str, str]
    refresh_generation: str

    def __post_init__(self) -> None:
        _require_timestamp(self.as_of_utc, "as_of_utc")
        _require_hash(self.registry_manifest_hash, "registry_manifest_hash")
        _require_hash(self.refresh_generation, "refresh_generation")
        if type(self.source_task_ids) is not tuple or len(self.source_task_ids) != 3:
            raise ValueError("universe finalizer requires exactly three source task ids")
        ids = tuple(_require_text(value, "source task id") for value in self.source_task_ids)
        if len(set(ids)) != 3:
            raise ValueError("universe finalizer source task ids must be distinct")


@dataclass(frozen=True)
class FormalFeatureBuildTaskPayload:
    security_id: str
    as_of_utc: str
    template_id: str
    source_registry_hash: str
    mapping_registry_hash: str
    feature_registry_hash: str
    registry_manifest_hash: str
    source_snapshot_ids: tuple[str, ...]
    refresh_generation: str

    def __post_init__(self) -> None:
        _require_security_id(self.security_id)
        _require_timestamp(self.as_of_utc, "as_of_utc")
        _require_text(self.template_id, "template_id")
        _require_hash(self.source_registry_hash, "source_registry_hash")
        _require_hash(self.mapping_registry_hash, "mapping_registry_hash")
        _require_hash(self.feature_registry_hash, "feature_registry_hash")
        _require_hash(self.registry_manifest_hash, "registry_manifest_hash")
        if type(self.source_snapshot_ids) is not tuple or any(type(value) is not str or not value for value in self.source_snapshot_ids):
            raise ValueError("source_snapshot_ids must be an immutable tuple of nonempty ids")
        if self.source_snapshot_ids != tuple(sorted(self.source_snapshot_ids)) or len(set(self.source_snapshot_ids)) != len(self.source_snapshot_ids):
            raise ValueError("source_snapshot_ids must be distinct and lexical")
        _require_hash(self.refresh_generation, "refresh_generation")


_PAYLOAD_KIND: dict[type[object], str] = {
    FormalStatementTaskPayload: "formal_statement",
    FormalContextTaskPayload: "formal_context",
    FormalUniverseSourceTaskPayload: "formal_universe_source",
    FormalUniverseFinalizeTaskPayload: "formal_universe_finalize",
    FormalFeatureBuildTaskPayload: "formal_feature_build",
}


class _FrozenDict(dict[str, object]):
    """An immutable JSON object that can still deep-copy into a persistence wire."""

    def __init__(self, value: Mapping[str, object]) -> None:
        dict.__init__(self, value)

    @staticmethod
    def _immutable(*_args: object, **_kwargs: object) -> None:
        raise TypeError("formal task payload is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __deepcopy__(self, memo: dict[int, object]) -> dict[str, object]:
        result: dict[str, object] = {}
        memo[id(self)] = result
        for key, value in self.items():
            result[copy.deepcopy(key, memo)] = copy.deepcopy(value, memo)
        return result


def _freeze_wire(value: object) -> object:
    if value is None or type(value) in {bool, int, float, str}:
        return value
    if type(value) is list:
        return tuple(_freeze_wire(item) for item in value)
    if type(value) is dict:
        return _FrozenDict({key: _freeze_wire(item) for key, item in value.items()})
    raise ValueError("formal task wire contains an unsupported value")


def _payload_mapping(payload: object) -> Mapping[str, object]:
    if type(payload) not in _PAYLOAD_KIND or not is_dataclass(payload):
        raise ValueError("formal task payload must be one closed typed payload")
    result: dict[str, object] = {}
    for item in fields(payload):
        value = getattr(payload, item.name)
        if type(value) is VerifiedCalendarBinding:
            result[item.name] = _binding_wire(value)
        elif type(value) is OfficialRequest:
            result[item.name] = asdict(value)
        elif type(value) is tuple:
            result[item.name] = [list(pair) if type(pair) is tuple else pair for pair in value]
        else:
            result[item.name] = value
    # JSON round-trip both validates the wire and detaches all caller-owned objects.
    canonical = _canonical_bytes(result)
    loaded = json.loads(canonical)
    frozen = _freeze_wire(loaded)
    assert isinstance(frozen, Mapping)
    return frozen


@dataclass(frozen=True, init=False)
class FormalTaskSpec:
    kind: Literal[
        "formal_statement", "formal_context", "formal_universe_source", "formal_universe_finalize", "formal_feature_build"
    ]
    idempotency_key: str
    refresh_generation: str
    payload: Mapping[str, object]
    prerequisite_task_ids: tuple[str, ...]

    def __init__(
        self,
        kind: str,
        idempotency_key: str,
        refresh_generation: str,
        payload: object,
        prerequisite_task_ids: tuple[str, ...] = (),
    ) -> None:
        expected_kind = _PAYLOAD_KIND.get(type(payload))
        if kind not in _FORMAL_KINDS or expected_kind != kind:
            raise ValueError("formal task kind and payload type must be a closed matching pair")
        generation = _require_hash(refresh_generation, "refresh_generation")
        if getattr(payload, "refresh_generation", None) != generation:
            raise ValueError("formal task generation and payload generation differ")
        key = _require_text(idempotency_key, "idempotency_key")
        if key != _idempotency_key(kind, payload):
            raise ValueError("idempotency_key is not the exact canonical V5 task key")
        if type(prerequisite_task_ids) is not tuple:
            raise ValueError("prerequisite task ids must be an immutable tuple")
        prerequisites = tuple(_require_text(value, "prerequisite task id") for value in prerequisite_task_ids)
        if len(set(prerequisites)) != len(prerequisites):
            raise ValueError("prerequisite task ids must be distinct")
        if expected_kind == "formal_universe_finalize":
            expected_edges = payload.source_task_ids
        else:
            calendar_edge = getattr(payload, "calendar_prerequisite_task_id", None)
            expected_edges = () if calendar_edge is None else (calendar_edge,)
        if prerequisites != expected_edges:
            raise ValueError("formal task prerequisite edge does not match typed calendar payload")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "idempotency_key", key)
        object.__setattr__(self, "refresh_generation", generation)
        object.__setattr__(self, "payload", _payload_mapping(payload))
        object.__setattr__(self, "prerequisite_task_ids", prerequisites)

    @classmethod
    def from_payload(cls, payload: object, *, prerequisite_task_ids: tuple[str, ...] | None = None) -> "FormalTaskSpec":
        kind = _PAYLOAD_KIND.get(type(payload))
        if kind is None:
            raise ValueError("formal task payload has no closed kind")
        if prerequisite_task_ids is None:
            if kind == "formal_universe_finalize":
                prerequisite_task_ids = payload.source_task_ids
            else:
                edge = getattr(payload, "calendar_prerequisite_task_id", None)
                prerequisite_task_ids = () if edge is None else (edge,)
        return cls(
            kind,
            _idempotency_key(kind, payload),
            getattr(payload, "refresh_generation"),
            payload,
            prerequisite_task_ids,
        )


def _idempotency_key(kind: str, payload: object) -> str:
    if type(payload) is FormalStatementTaskPayload:
        fields_ = (payload.security_id, payload.dataset, payload.report_period, payload.source, payload.as_of_utc, payload.request_version)
    elif type(payload) is FormalContextTaskPayload:
        fields_ = (payload.security_id or "global", payload.context_kind, payload.official_request.period_or_date or "none", payload.source, payload.as_of_utc, payload.request_version)
    elif type(payload) is FormalUniverseSourceTaskPayload:
        fields_ = ("global", payload.exchange, payload.official_request.period_or_date or "none", payload.source, payload.as_of_utc, payload.request_version)
    elif type(payload) is FormalUniverseFinalizeTaskPayload:
        fields_ = ("global", "universe_finalize", payload.as_of_utc, "none", payload.as_of_utc, "formal-v5")
    elif type(payload) is FormalFeatureBuildTaskPayload:
        fields_ = (payload.security_id, payload.template_id, "none", "formal", payload.as_of_utc, "formal-v5")
    else:  # guarded by FormalTaskSpec's closed-type check
        raise ValueError("formal task payload has no idempotency form")
    return ":".join((kind, "v5", *fields_, payload.refresh_generation))


@dataclass(frozen=True)
class FormalRegistryRuntime:
    bundle: VerifiedRegistryBundle
    source_adapter: FormalOfficialSourceAdapter
    mapping_registry: SignedFinancialMappingRegistry
    feature_registry: SignedFormalFeatureRegistry

    def __post_init__(self) -> None:
        if type(self.bundle) is not VerifiedRegistryBundle:
            raise ValueError("runtime bundle must be a verified registry bundle")
        self.bundle.blob("source")
        self.bundle.blob("mapping")
        self.bundle.blob("feature")
        if type(self.source_adapter) is not FormalOfficialSourceAdapter:
            raise ValueError("runtime source adapter is invalid")
        if type(self.mapping_registry) is not SignedFinancialMappingRegistry:
            raise ValueError("runtime mapping registry is invalid")
        if type(self.feature_registry) is not SignedFormalFeatureRegistry:
            raise ValueError("runtime feature registry is invalid")
        adapter_record = FormalOfficialSourceAdapter._trusted_operation_record(self.source_adapter)
        if (
            adapter_record.source_registry_hash != self.bundle.manifest.source_registry_hash
            or adapter_record.registry_manifest_hash != self.bundle.manifest.manifest_hash
            or self.mapping_registry.registry_hash != self.bundle.manifest.mapping_registry_hash
            or self.feature_registry.registry_hash != self.bundle.manifest.feature_registry_hash
        ):
            raise ValueError("runtime registry hash does not match verified bundle")


class FormalRegistryRuntimeLoader:
    """Reload every signed child from the exact verified root on each request."""

    def __init__(
        self,
        bundle_loader: FormalRegistryBundleLoader,
        *,
        transport: OfficialTransport,
        policies: Mapping[str, SourcePolicy],
        parsers: Mapping[str, OfficialDocumentParser],
        effective_time_resolver: EffectiveTimeResolver,
    ) -> None:
        if type(bundle_loader) is not FormalRegistryBundleLoader:
            raise ValueError("runtime requires FormalRegistryBundleLoader")
        if not callable(getattr(transport, "send", None)):
            raise ValueError("runtime transport is invalid")
        if not isinstance(policies, Mapping) or not isinstance(parsers, Mapping):
            raise ValueError("runtime policies and parsers must be mappings")
        if not callable(getattr(effective_time_resolver, "next_exchange_close", None)):
            raise ValueError("runtime effective-time resolver is invalid")
        verifier = getattr(bundle_loader, "_verifier", None)
        if not callable(getattr(verifier, "verify", None)):
            raise ValueError("bundle loader has no usable signature verifier")
        self._bundle_loader = bundle_loader
        self._verifier = verifier
        self._transport = transport
        self._policies = MappingProxyType(dict(policies))
        self._parsers = MappingProxyType(dict(parsers))
        self._effective_time_resolver = effective_time_resolver

    def load(
        self,
        manifest_hash: str,
        *,
        adapter_freeze_at_utc: str | None = None,
    ) -> FormalRegistryRuntime:
        root = _require_hash(manifest_hash, "manifest_hash")
        freeze_at_utc = (
            None
            if adapter_freeze_at_utc is None
            else _require_timestamp(adapter_freeze_at_utc, "adapter_freeze_at_utc")
        )
        bundle = self._bundle_loader.load(root)
        if type(bundle) is not VerifiedRegistryBundle or bundle.manifest.manifest_hash != root:
            raise ValueError("verified bundle root does not match requested manifest")
        source_blob = bundle.blob("source")
        mapping_blob = bundle.blob("mapping")
        feature_blob = bundle.blob("feature")
        source_registry = SignedSourceRegistry.from_signed_bytes(
            source_blob.canonical_json, source_blob.signature, source_blob.key_id, self._verifier
        )
        mapping_registry = SignedFinancialMappingRegistry.from_signed_bytes(
            mapping_blob.canonical_json, signature=mapping_blob.signature, key_id=mapping_blob.key_id, verifier=self._verifier
        )
        feature_registry = load_signed_feature_registry(
            feature_blob.canonical_json, feature_blob.signature, feature_blob.key_id, self._verifier,
            registry_manifest=bundle.manifest,
        )
        if (
            source_registry.registry_hash != source_blob.registry_hash
            or mapping_registry.registry_hash != mapping_blob.registry_hash
            or feature_registry.registry_hash != feature_blob.registry_hash
        ):
            raise ValueError("compiled registry hash does not match verified bundle blob")
        adapter_kwargs: dict[str, object] = {
            "transport": self._transport,
            "registry": source_registry,
            "policies": self._policies,
            "parsers": self._parsers,
            "effective_time_resolver": self._effective_time_resolver,
            "source_registry_hash": source_blob.registry_hash,
            "registry_manifest_hash": root,
        }
        if freeze_at_utc is not None:
            adapter_kwargs["freeze_at_utc"] = freeze_at_utc
        adapter = FormalOfficialSourceAdapter(
            **adapter_kwargs,
        )
        return FormalRegistryRuntime(bundle, adapter, mapping_registry, feature_registry)


@dataclass(frozen=True)
class FormalUniverseSourceResolution:
    payload: FormalUniverseSourceTaskPayload
    prerequisite_task_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.payload) is not FormalUniverseSourceTaskPayload or type(self.prerequisite_task_ids) is not tuple:
            raise ValueError("universe resolution must contain an exact source payload and immutable edges")
        expected = () if self.payload.calendar_prerequisite_task_id is None else (self.payload.calendar_prerequisite_task_id,)
        if self.prerequisite_task_ids != expected:
            raise ValueError("universe resolution prerequisite edge does not match payload calendar binding")


class SignedUniverseRequestResolver(Protocol):
    def resolve(
        self,
        *,
        exchange: Literal["SH", "SZ", "BJ"],
        as_of_utc: str,
        upstream_generation: str,
        runtime: FormalRegistryRuntime,
    ) -> FormalUniverseSourceResolution: ...


@dataclass(frozen=True)
class FormalWorkerDependencies:
    store: object
    snapshots: object
    registry_runtime_loader: FormalRegistryRuntimeLoader
    feature_store: object
    context_repository: object


@dataclass(frozen=True)
class FormalCollectionSummary:
    remote_attempts: int
    verified_statement_count: int
    frozen_universe_snapshot_ids: tuple[str, ...]
    retryable_failed: int
    terminal_failed: int
    feature_bundles_written: int
    open_circuits: tuple[str, ...]
    rebuilt_security_ids: tuple[str, ...]


def formal_statement_task_specs(
    security_id: str,
    report_period: str,
    as_of_utc: str,
    source: str,
    source_registry_hash: str,
    mapping_registry_hash: str,
    upstream_generation: str,
    registry_manifest_hash: str,
    calendar_prerequisite_task_id: str | None = None,
    calendar_binding: VerifiedCalendarBinding | None = None,
) -> tuple[FormalTaskSpec, ...]:
    """Create the three lexical statement specs without accepting a caller generation."""

    security = _require_security_id(security_id)
    period = _require_iso_date(report_period, "report_period")
    as_of = _require_timestamp(as_of_utc, "as_of_utc")
    root = _require_hash(registry_manifest_hash, "registry_manifest_hash")
    roles = (("mapping", _require_hash(mapping_registry_hash, "mapping_registry_hash")), ("source", _require_hash(source_registry_hash, "source_registry_hash")))
    selector: CalendarSelector | None = None
    if calendar_binding is not None:
        # A statement caller has no signed selector parameter; only the runtime's signed
        # source config may create date-only statement tasks in a later delivery.
        raise CalendarBindingPending("calendar-bound statement tasks require a signed source selector")
    generation = derive_collection_refresh_generation(
        upstream_generation=upstream_generation,
        registry_manifest_hash=root,
        relevant_registry_hashes=dict(roles),
        calendar_selector=selector,
        calendar_binding=calendar_binding,
    )
    return tuple(
        FormalTaskSpec.from_payload(
            FormalStatementTaskPayload(
                security_id=security, dataset=dataset, report_period=period, as_of_utc=as_of,
                source=_require_text(source, "source"), request_version="formal-v5",
                source_registry_hash=source_registry_hash, mapping_registry_hash=mapping_registry_hash,
                upstream_generation=_require_text(upstream_generation, "upstream_generation"), refresh_generation=generation,
                registry_manifest_hash=root, relevant_registry_hashes=roles,
                calendar_prerequisite_task_id=calendar_prerequisite_task_id, calendar_binding=calendar_binding,
            )
        )
        for dataset in ("balance_sheet", "cash_flow_sheet", "profit_sheet")
    )


def formal_context_task_specs(request: FormalContextRequest) -> tuple[FormalTaskSpec, ...]:
    """Encode exactly one sealed Context resolver request as a formal task spec."""
    return (FormalTaskSpec.from_payload(FormalContextTaskPayload.from_request(request)),)


def formal_universe_task_specs(*_args: object, **_kwargs: object) -> tuple[FormalTaskSpec, ...]:
    """Reserved for Task 6D's persisted source/finalizer edge construction."""
    raise NotImplementedError("formal universe task construction is owned by Task 6D")


def enqueue_frozen_formal_universe(*_args: object, **_kwargs: object) -> str:
    raise NotImplementedError("formal universe enqueue is owned by Task 6D")


def _statement_payload_from_wire(value: object) -> FormalStatementTaskPayload:
    """Restore only the exact persisted JSON shape for a statement task."""

    if type(value) is not dict:
        raise ValueError("formal statement task payload must be an exact JSON object")
    expected_fields = {item.name for item in fields(FormalStatementTaskPayload)}
    if set(value) != expected_fields:
        raise ValueError("formal statement task payload fields are invalid")
    roles = value["relevant_registry_hashes"]
    if type(roles) is not list:
        raise ValueError("formal statement task registry roles must be a JSON array")
    role_pairs: list[tuple[str, str]] = []
    for pair in roles:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError("formal statement task registry role pair is invalid")
        role_pairs.append((pair[0], pair[1]))
    binding_wire = value["calendar_binding"]
    if binding_wire is None:
        binding = None
    else:
        if type(binding_wire) is not dict:
            raise ValueError("formal statement calendar binding must be a JSON object")
        binding = VerifiedCalendarBinding(**binding_wire)
    return FormalStatementTaskPayload(
        security_id=value["security_id"],
        dataset=value["dataset"],
        report_period=value["report_period"],
        as_of_utc=value["as_of_utc"],
        source=value["source"],
        request_version=value["request_version"],
        source_registry_hash=value["source_registry_hash"],
        mapping_registry_hash=value["mapping_registry_hash"],
        upstream_generation=value["upstream_generation"],
        refresh_generation=value["refresh_generation"],
        registry_manifest_hash=value["registry_manifest_hash"],
        relevant_registry_hashes=tuple(role_pairs),
        calendar_prerequisite_task_id=value["calendar_prerequisite_task_id"],
        calendar_binding=binding,
    )


def _decode_leased_statement_task(task: object) -> tuple[str, FormalStatementTaskPayload]:
    if type(task) is not dict:
        raise ValueError("leased formal task must be an exact JSON object")
    if task.get("kind") != "formal_statement" or task.get("status") != "leased":
        raise ValueError("leased task is not a formal statement")
    task_id = _require_text(task.get("id"), "formal statement task id")
    payload = _statement_payload_from_wire(task.get("payload"))
    spec = FormalTaskSpec.from_payload(payload)
    if (
        task.get("idempotency_key") != spec.idempotency_key
        or task.get("refresh_generation") != spec.refresh_generation
        or task.get("prerequisite_task_ids") != list(spec.prerequisite_task_ids)
        or _canonical_bytes(task["payload"]) != _canonical_bytes(spec.payload)
    ):
        raise ValueError("leased formal statement task does not match its canonical payload")
    return task_id, payload


def _statement_request(payload: FormalStatementTaskPayload) -> OfficialRequest:
    return OfficialRequest(
        payload.source,
        payload.dataset,
        payload.security_id,
        payload.report_period,
        payload.security_id[:2],
    )


def _require_statement_snapshot_identity(
    receipt: object,
    snapshot: object,
    *,
    task_id: str,
    payload: FormalStatementTaskPayload,
    request: OfficialRequest,
) -> OfficialSnapshotRef:
    """Bind replay evidence to this immutable leased statement request before parsing."""

    if type(receipt) is not dict or type(snapshot) is not OfficialSnapshotRef:
        raise ValueError("formal statement receipt or snapshot identity is invalid")
    receipt_fields = {
        "task_id": task_id,
        "snapshot_id": snapshot.snapshot_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "refresh_generation": payload.refresh_generation,
    }
    for field, expected in receipt_fields.items():
        actual = receipt.get(field)
        if type(actual) is not str or actual != expected:
            raise ValueError("formal statement receipt does not match its persisted snapshot")
    expected_request_fields = {
        "source": request.source,
        "dataset": request.dataset,
        "security_id": request.security_id,
        "period_or_date": request.period_or_date,
        "exchange": request.exchange,
        "request_fingerprint": request.request_fingerprint,
    }
    for field, expected in expected_request_fields.items():
        actual = getattr(snapshot, field)
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError("formal statement persisted snapshot request does not match payload")
    if (
        type(snapshot.refresh_generation) is not str
        or snapshot.refresh_generation != payload.refresh_generation
        or type(snapshot.producing_task_id) is not str
        or snapshot.producing_task_id != task_id
    ):
        raise ValueError("formal statement persisted snapshot lineage does not match task")
    return snapshot


def _validated_statement_runtime(
    dependencies: FormalWorkerDependencies,
    payload: FormalStatementTaskPayload,
) -> tuple[FormalRegistryRuntime, OfficialRequest, object]:
    if type(dependencies.registry_runtime_loader) is not FormalRegistryRuntimeLoader:
        raise ValueError("formal statement worker requires the exact runtime loader")
    runtime = dependencies.registry_runtime_loader.load(
        payload.registry_manifest_hash,
        adapter_freeze_at_utc=payload.as_of_utc,
    )
    if type(runtime) is not FormalRegistryRuntime:
        raise ValueError("formal statement runtime loader returned an invalid runtime")
    runtime.bundle.require_official()
    manifest = runtime.bundle.manifest
    if (
        manifest.manifest_hash != payload.registry_manifest_hash
        or manifest.source_registry_hash != payload.source_registry_hash
        or manifest.mapping_registry_hash != payload.mapping_registry_hash
        or runtime.source_adapter.source_registry_hash != payload.source_registry_hash
        or runtime.mapping_registry.registry_hash != payload.mapping_registry_hash
    ):
        raise ValueError("formal statement runtime registry hashes do not match payload")
    request = _statement_request(payload)
    config = runtime.source_adapter.registry.select(request)
    selector = config.calendar_selector
    if selector is None:
        if payload.calendar_binding is not None or payload.calendar_prerequisite_task_id is not None:
            raise ValueError("timestamp-only statement task cannot carry calendar evidence")
    else:
        if payload.calendar_binding is None or payload.calendar_prerequisite_task_id is None:
            raise CalendarBindingPending("date-only statement task requires a verified calendar binding")
        repository = dependencies.context_repository
        resolver = getattr(repository, "resolve_verified_calendar_binding", None)
        if not callable(resolver):
            raise ValueError("date-only statement task requires a verified context repository")
        current = resolver(
            selector,
            request.exchange,
            payload.as_of_utc,
            payload.registry_manifest_hash,
        )
        if type(current) is not VerifiedCalendarBinding or _binding_wire(current) != _binding_wire(payload.calendar_binding):
            raise ValueError("statement calendar binding no longer matches verified context")
    expected_generation = derive_collection_refresh_generation(
        upstream_generation=payload.upstream_generation,
        registry_manifest_hash=payload.registry_manifest_hash,
        relevant_registry_hashes={
            "mapping": payload.mapping_registry_hash,
            "source": payload.source_registry_hash,
        },
        calendar_selector=selector,
        calendar_binding=payload.calendar_binding,
    )
    if expected_generation != payload.refresh_generation:
        raise ValueError("formal statement refresh generation does not match runtime")
    return runtime, request, config


def _feature_refresh_generation(
    facts: tuple[FormalFinancialFact, ...],
    registry_manifest_hash: str,
) -> tuple[str, tuple[str, ...]]:
    snapshots: dict[str, dict[str, str]] = {}
    fact_ids: list[str] = []
    for fact in facts:
        if type(fact) is not FormalFinancialFact:
            raise ValueError("feature rebuild requires exact formal facts")
        wire = fact.to_dict()
        fact_ids.append(wire["id"])
        snapshot = {
            "content_sha256": wire["source_content_sha256"],
            "refresh_generation": wire["source_refresh_generation"],
            "snapshot_id": wire["source_snapshot_id"],
        }
        prior = snapshots.setdefault(snapshot["snapshot_id"], snapshot)
        if prior != snapshot:
            raise ValueError("one feature snapshot ID has conflicting evidence lineage")
    snapshot_ids = tuple(sorted(snapshots))
    wire = {
        "formal_fact_ids": sorted(set(fact_ids)),
        "history_gate_version": _FEATURE_HISTORY_GATE_VERSION,
        "registry_manifest_hash": registry_manifest_hash,
        "selected_statement_snapshots": [snapshots[item] for item in snapshot_ids],
    }
    return hashlib.sha256(_canonical_bytes(wire)).hexdigest(), snapshot_ids


def enqueue_formal_feature_build(
    store: object,
    *,
    security_id: str,
    as_of_utc: str,
    runtime: FormalRegistryRuntime,
    facts: tuple[FormalFinancialFact, ...],
    before_mutation: Callable[[], None] | None = None,
) -> tuple[str, ...]:
    """Schedule only the affected security's immutable V6 feature inputs."""

    if type(runtime) is not FormalRegistryRuntime:
        raise ValueError("feature rebuild enqueue requires an exact formal runtime")
    security = _require_security_id(security_id)
    as_of = _require_timestamp(as_of_utc, "as_of_utc")
    selected = select_visible_formal_facts(facts, as_of).facts
    generation, snapshot_ids = _feature_refresh_generation(
        selected, runtime.bundle.manifest.manifest_hash
    )
    task_ids: list[str] = []
    for template_id in runtime.feature_registry.template_ids:
        payload = FormalFeatureBuildTaskPayload(
            security_id=security,
            as_of_utc=as_of,
            template_id=template_id,
            source_registry_hash=runtime.bundle.manifest.source_registry_hash,
            mapping_registry_hash=runtime.bundle.manifest.mapping_registry_hash,
            feature_registry_hash=runtime.bundle.manifest.feature_registry_hash,
            registry_manifest_hash=runtime.bundle.manifest.manifest_hash,
            source_snapshot_ids=snapshot_ids,
            refresh_generation=generation,
        )
        spec = FormalTaskSpec.from_payload(payload)
        enqueue = getattr(store, "enqueue_formal_task", None)
        if not callable(enqueue):
            raise ValueError("formal feature rebuild requires formal task persistence")
        if before_mutation is not None:
            before_mutation()
        task_ids.append(
            enqueue(
                spec.kind,
                spec.idempotency_key,
                spec.refresh_generation,
                spec.payload,
                spec.prerequisite_task_ids,
            )
        )
        supersede = getattr(store, "supersede_formal_tasks", None)
        if not callable(supersede):
            raise ValueError("formal feature rebuild requires task supersession persistence")
        if before_mutation is not None:
            before_mutation()
        supersede(
            {
                "as_of_utc": as_of,
                "security_id": security,
                "template_id": template_id,
            },
            spec.refresh_generation,
        )
    return tuple(task_ids)


def _execute_statement_task(
    dependencies: FormalWorkerDependencies,
    task: dict[str, object],
    *,
    worker_id: str,
) -> tuple[int, str]:
    """Execute a single leased statement task; return remote attempts and security."""

    task_id, payload = _decode_leased_statement_task(task)
    runtime, request, config = _validated_statement_runtime(dependencies, payload)
    receipt_getter = getattr(dependencies.store, "get_formal_task_snapshot_receipt", None)
    if not callable(receipt_getter):
        raise ValueError("formal statement worker requires task receipt persistence")
    receipt = receipt_getter(task_id)
    remote_attempts = 0
    if receipt is None:
        retry_after = _active_source_circuit_retry_after(
            dependencies.store,
            payload.source,
        )
        if retry_after is not None:
            _fail_statement_retryable(
                dependencies.store,
                task_id,
                worker_id,
                code="source_circuit_open",
                next_retry_at=retry_after,
                remote_attempts=remote_attempts,
            )
            raise _RetryableFormalTask(0, payload.source, circuit_open=True)
        remote_attempts = 1
        try:
            fetch, verification, _ignored_document = runtime.source_adapter.fetch_verified(
                request,
                refresh_generation=payload.refresh_generation,
                calendar_binding=payload.calendar_binding,
            )
        except FormalSourceBlocked:
            retry_after = _open_source_circuit(
                dependencies.store,
                payload.source,
                cooldown_seconds=config.challenge_cooldown_seconds,
                code="source_blocked",
            )
            _fail_statement_retryable(
                dependencies.store,
                task_id,
                worker_id,
                code="source_blocked",
                next_retry_at=retry_after,
                remote_attempts=remote_attempts,
            )
            raise _RetryableFormalTask(remote_attempts, payload.source, circuit_open=True)
        except FormalRetryableSourceError:
            _opened_at, retry_after = _retry_window(config.retry_base_seconds)
            _fail_statement_retryable(
                dependencies.store,
                task_id,
                worker_id,
                code="source_retryable_failed",
                next_retry_at=retry_after,
                remote_attempts=remote_attempts,
            )
            raise _RetryableFormalTask(remote_attempts, payload.source, circuit_open=False)
        except FormalTerminalSourceError as error:
            raise _TerminalFormalTask(
                remote_attempts, "statement_terminal_source_error"
            ) from error
        try:
            dependencies.snapshots.persist_verified(
                fetch,
                verification,
                producing_task_id=task_id,
                worker_id=worker_id,
            )
        except FormalTerminalSourceError as error:
            raise _TerminalFormalTask(
                remote_attempts, "statement_terminal_source_error"
            ) from error
        except ValueError as error:
            if _is_lost_formal_task_lease_error(error):
                raise _LostFormalTaskLease(remote_attempts) from error
            raise _TerminalFormalTask(
                remote_attempts, "statement_validation_failed"
            ) from error
        receipt = receipt_getter(task_id)
    try:
        if type(receipt) is not dict or type(receipt.get("manifest_sha256")) is not str:
            raise ValueError("formal statement source receipt is missing after persistence")
        snapshot = _require_statement_snapshot_identity(
            receipt,
            dependencies.snapshots.get_verified_by_manifest(receipt["manifest_sha256"]),
            task_id=task_id,
            payload=payload,
            request=request,
        )
        raw_bytes = dependencies.snapshots.read_verified_raw(snapshot)
        document = runtime.source_adapter.parse_verified_snapshot(
            snapshot,
            raw_bytes,
            calendar_binding=payload.calendar_binding,
        )
        _renew_statement_lease(
            dependencies.store,
            task_id,
            worker_id,
            remote_attempts=remote_attempts,
        )
        extraction = extract_formal_financial_facts(
            document,
            snapshot,
            runtime.mapping_registry,
            datetime.now(timezone.utc).isoformat(),
        )
        if not extraction.facts:
            raise ValueError("formal statement extraction produced no usable facts")
        _renew_statement_lease(
            dependencies.store,
            task_id,
            worker_id,
            remote_attempts=remote_attempts,
        )
        dependencies.store.insert_formal_financial_facts(extraction.facts)
        _renew_statement_lease(
            dependencies.store,
            task_id,
            worker_id,
            remote_attempts=remote_attempts,
        )
        current_facts = dependencies.store.list_formal_financial_facts(
            security_id=payload.security_id
        )

        def renew_for_feature_mutation() -> None:
            _renew_statement_lease(
                dependencies.store,
                task_id,
                worker_id,
                remote_attempts=remote_attempts,
            )

        feature_task_ids = enqueue_formal_feature_build(
            dependencies.store,
            security_id=payload.security_id,
            as_of_utc=payload.as_of_utc,
            runtime=runtime,
            facts=current_facts,
            before_mutation=renew_for_feature_mutation,
        )
        _renew_statement_lease(
            dependencies.store,
            task_id,
            worker_id,
            remote_attempts=remote_attempts,
        )
        dependencies.store.complete_formal_task(
            task_id,
            worker_id,
            {
                "fact_ids": [fact.to_dict()["id"] for fact in extraction.facts],
                "feature_task_ids": list(feature_task_ids),
                "kind": "formal_statement",
                "manifest_sha256": snapshot.manifest_sha256,
                "refresh_generation": payload.refresh_generation,
                "registry_manifest_hash": payload.registry_manifest_hash,
                "security_id": payload.security_id,
                "snapshot_id": snapshot.snapshot_id,
            },
        )
    except FormalTerminalSourceError as error:
        raise _TerminalFormalTask(remote_attempts, "statement_terminal_source_error") from error
    except FormalSourceBlocked:
        retry_after = _open_source_circuit(
            dependencies.store,
            payload.source,
            cooldown_seconds=config.challenge_cooldown_seconds,
            code="source_blocked",
        )
        _fail_statement_retryable(
            dependencies.store,
            task_id,
            worker_id,
            code="source_blocked",
            next_retry_at=retry_after,
            remote_attempts=remote_attempts,
        )
        raise _RetryableFormalTask(remote_attempts, payload.source, circuit_open=True)
    except FormalRetryableSourceError:
        _opened_at, retry_after = _retry_window(config.retry_base_seconds)
        _fail_statement_retryable(
            dependencies.store,
            task_id,
            worker_id,
            code="source_retryable_failed",
            next_retry_at=retry_after,
            remote_attempts=remote_attempts,
        )
        raise _RetryableFormalTask(remote_attempts, payload.source, circuit_open=False)
    except ValueError as error:
        raise _TerminalFormalTask(remote_attempts, "statement_validation_failed") from error
    return remote_attempts, payload.security_id


def _retry_window(seconds: object) -> tuple[str, str]:
    if type(seconds) not in {int, float} or isinstance(seconds, bool) or seconds <= 0:
        raise ValueError("signed retry interval must be a positive finite number")
    now = datetime.now(timezone.utc)
    return now.isoformat(), (now + timedelta(seconds=float(seconds))).isoformat()


def _open_source_circuit(
    store: object,
    source: str,
    *,
    cooldown_seconds: object,
    code: str,
) -> str:
    opened_at, retry_after = _retry_window(cooldown_seconds)
    existing = store.get_formal_source_circuit(source)
    failures = 1
    if type(existing) is dict and existing.get("state") == "open":
        count = existing.get("failure_count")
        if type(count) is int and count > 0:
            failures = count + 1
    store.set_formal_source_circuit(
        source,
        state="open",
        failure_count=failures,
        reason={"code": code},
        opened_at_utc=opened_at,
        retry_after_utc=retry_after,
    )
    return retry_after


def _active_source_circuit_retry_after(store: object, source: str) -> str | None:
    circuit = store.get_formal_source_circuit(source)
    if circuit is None:
        return None
    if type(circuit) is not dict:
        raise ValueError("formal source circuit state is invalid")
    if circuit.get("state") != "open":
        return None
    retry_after = _require_timestamp(circuit.get("retry_after_utc"), "circuit retry time")
    if datetime.fromisoformat(retry_after) > datetime.now(timezone.utc):
        return retry_after
    store.set_formal_source_circuit(
        source,
        state="closed",
        failure_count=0,
        reason={},
        opened_at_utc=None,
        retry_after_utc=None,
    )
    return None


def _fail_statement_retryable(
    store: object,
    task_id: str,
    worker_id: str,
    *,
    code: str,
    next_retry_at: str,
    remote_attempts: int,
) -> None:
    try:
        store.fail_formal_task(
            task_id,
            worker_id,
            {"code": code},
            "retryable_failed",
            next_retry_at,
        )
    except ValueError as error:
        if _is_lost_formal_task_lease_error(error):
            raise _LostFormalTaskLease(remote_attempts) from error
        raise


def _is_lost_formal_task_lease_error(error: ValueError) -> bool:
    message = str(error)
    return (
        "not held by the current unexpired lease owner" in message
        or "lease expired or ownership changed" in message
    )


def _renew_statement_lease(
    store: object,
    task_id: str,
    worker_id: str,
    *,
    remote_attempts: int,
) -> None:
    try:
        store.renew_formal_task_lease(
            task_id,
            worker_id,
            _STATEMENT_LEASE_SECONDS,
        )
    except ValueError as error:
        if _is_lost_formal_task_lease_error(error):
            raise _LostFormalTaskLease(remote_attempts) from error
        raise


def _fail_statement_terminal(
    store: object,
    task_id: str,
    worker_id: str,
    *,
    code: str,
) -> bool:
    """Record a deterministic terminal result unless ownership was lost."""

    try:
        store.fail_formal_task(
            task_id,
            worker_id,
            {"code": code},
            "terminal_failed",
            None,
        )
    except ValueError as error:
        if _is_lost_formal_task_lease_error(error):
            return False
        raise
    return True


def execute_queued_formal_work(
    dependencies: FormalWorkerDependencies,
    *,
    worker_id: str,
    max_jobs: int | None = None,
) -> FormalCollectionSummary:
    """Run the currently implemented safe subset: leased formal statements only."""

    if type(dependencies) is not FormalWorkerDependencies:
        raise ValueError("formal worker dependencies must have exact type")
    owner = _require_text(worker_id, "worker_id")
    if max_jobs is not None and (
        type(max_jobs) is not int or isinstance(max_jobs, bool) or max_jobs < 0
    ):
        raise ValueError("max_jobs must be a nonnegative integer or None")
    resolver = getattr(dependencies.store, "resolve_formal_task_dependencies", None)
    lease_next = getattr(dependencies.store, "lease_next_formal_task", None)
    if not callable(resolver) or not callable(lease_next):
        raise ValueError("formal worker requires formal task lease persistence")
    resolver()
    remote_attempts = 0
    verified_statement_count = 0
    retryable_failed = 0
    terminal_failed = 0
    open_circuits: set[str] = set()
    rebuilt_security_ids: set[str] = set()
    processed = 0
    while max_jobs is None or processed < max_jobs:
        task = lease_next(_STATEMENT_EXECUTION_KINDS, owner, _STATEMENT_LEASE_SECONDS)
        if task is None:
            break
        if type(task) is not dict:
            raise ValueError("formal task lease returned an invalid task")
        try:
            attempts, security_id = _execute_statement_task(
                dependencies, task, worker_id=owner
            )
        except _LostFormalTaskLease as error:
            remote_attempts += error.remote_attempts
            processed += 1
            continue
        except _RetryableFormalTask as error:
            remote_attempts += error.remote_attempts
            retryable_failed += 1
            if error.circuit_open:
                open_circuits.add(error.source)
            processed += 1
            continue
        except _TerminalFormalTask as error:
            remote_attempts += error.remote_attempts
            task_id = _require_text(task.get("id"), "formal statement task id")
            if _fail_statement_terminal(
                dependencies.store,
                task_id,
                owner,
                code=error.code,
            ):
                terminal_failed += 1
            processed += 1
            continue
        except FormalTerminalSourceError:
            task_id = _require_text(task.get("id"), "formal statement task id")
            if _fail_statement_terminal(
                dependencies.store,
                task_id,
                owner,
                code="statement_terminal_source_error",
            ):
                terminal_failed += 1
            processed += 1
            continue
        except ValueError:
            task_id = _require_text(task.get("id"), "formal statement task id")
            if _fail_statement_terminal(
                dependencies.store,
                task_id,
                owner,
                code="statement_validation_failed",
            ):
                terminal_failed += 1
            processed += 1
            continue
        remote_attempts += attempts
        verified_statement_count += 1
        rebuilt_security_ids.add(security_id)
        processed += 1
    return FormalCollectionSummary(
        remote_attempts=remote_attempts,
        verified_statement_count=verified_statement_count,
        frozen_universe_snapshot_ids=(),
        retryable_failed=retryable_failed,
        terminal_failed=terminal_failed,
        feature_bundles_written=0,
        open_circuits=tuple(sorted(open_circuits)),
        rebuilt_security_ids=tuple(sorted(rebuilt_security_ids)),
    )


__all__ = [
    "CalendarBindingPending", "FormalCollectionSummary", "FormalContextTaskPayload", "FormalFeatureBuildTaskPayload",
    "FormalRegistryRuntime", "FormalRegistryRuntimeLoader", "FormalStatementTaskPayload", "FormalTaskSpec",
    "FormalUniverseFinalizeTaskPayload", "FormalUniverseSourceResolution", "FormalUniverseSourceTaskPayload",
    "FormalWorkerDependencies", "SignedUniverseRequestResolver", "derive_collection_refresh_generation",
    "enqueue_formal_feature_build", "enqueue_frozen_formal_universe", "execute_queued_formal_work",
    "formal_context_task_specs", "formal_statement_task_specs", "formal_universe_task_specs",
]
