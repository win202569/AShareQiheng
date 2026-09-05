"""Fail-closed Formal V3 financial mapping and fact extraction boundary.

This module deliberately has no production mapping registry or fallback to the
legacy financial schema.  A caller must supply a canonical, signature-verified
mapping registry and a verified official snapshot/document pair.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Literal
import uuid
import weakref

from .feature_contract import canonical_json_bytes, canonical_sha256
from .formal_evidence import OfficialSnapshotRef
from .formal_sources import ParsedOfficialDocument, RegistrySignatureVerifier
from .formal_universe import canonical_security_id


_STATEMENTS = frozenset({"income", "balance", "cash_flow"})
_UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})
_NATURES = frozenset({"instant", "duration"})
_PERIOD_KINDS = frozenset({"FY", "H1", "Q1", "Q3", "OTHER"})
_PRECISIONS = frozenset({"timestamp", "date_only"})
_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DATE_ONLY_ANCHOR = re.compile(r"^\d{4}-\d{2}-\d{2}T00:00:00\+00:00$")
_DECIMAL = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_REGISTRY_KEYS = frozenset(
    {"schema_version", "registry_role", "row_format", "mappings", "bindings"}
)
_MAPPING_KEYS = frozenset(
    {
        "mapping_id",
        "statement",
        "metric_key",
        "source_field",
        "unit",
        "nature",
        "period_kind",
        "accounting_basis",
    }
)
_BINDING_KEYS = frozenset(
    {
        "source",
        "dataset",
        "parser_id",
        "parser_version",
        "mapping_version",
        "exchange_scope",
        "mapping_ids",
    }
)
_FACT_FIELDS = (
    "id",
    "security_id",
    "statement",
    "metric_key",
    "period_start",
    "period_end",
    "period_kind",
    "value",
    "unit",
    "nature",
    "accounting_basis",
    "published_at_utc",
    "published_precision",
    "effective_at_utc",
    "effective_time_evidence_hash",
    "source_updated_at_utc",
    "captured_at_utc",
    "source_snapshot_id",
    "source_content_sha256",
    "source_refresh_generation",
    "source_producing_task_id",
    "source_field",
    "raw_value_sha256",
    "parser_id",
    "parser_version",
    "mapping_version",
    "created_at_utc",
)


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
        canonical = canonical_json_bytes(parsed)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} contains unsupported JSON values") from error
    if canonical != value:
        raise ValueError(f"{label} must be canonical JSON")
    return parsed


def _require_exact_keys(value: object, keys: frozenset[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{label} must contain exactly its contractual keys")
    return value


def _require_text(
    value: object, label: str, *, identifier: bool = False, controls: bool = False
) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an already-trimmed nonempty string")
    if controls and _CONTROL.search(value) is not None:
        raise ValueError(f"{label} contains control characters")
    if identifier and _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be an identifier")
    return value


def _require_optional_text(
    value: object, label: str, *, identifier: bool = False, controls: bool = False
) -> str | None:
    if value is None:
        return None
    return _require_text(value, label, identifier=identifier, controls=controls)


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _require_exchange(value: object, label: str) -> str:
    if type(value) is not str or value not in _EXCHANGES:
        raise ValueError(f"{label} must be SH, SZ, or BJ")
    return value


def _require_iso_date(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a canonical ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a canonical ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be a canonical ISO date")
    return value


def _require_utc_timestamp(value: object, label: str) -> str:
    """Require an exact canonical, timezone-aware UTC timestamp string."""

    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a canonical aware UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a canonical aware UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be a canonical aware UTC timestamp")
    normalized = parsed.astimezone(timezone.utc).isoformat()
    if value != normalized:
        raise ValueError(f"{label} must be a canonical aware UTC timestamp")
    return value


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _require_publication(value: object, precision: object, label: str) -> tuple[str, str]:
    if type(precision) is not str or precision not in _PRECISIONS:
        raise ValueError(f"{label} precision is invalid")
    if precision == "timestamp":
        return _require_utc_timestamp(value, label), precision
    if type(value) is not str or _DATE_ONLY_ANCHOR.fullmatch(value) is None:
        raise ValueError(f"{label} date_only must be the UTC day anchor")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} date_only must be the UTC day anchor") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} date_only must be the UTC day anchor")
    return value, precision


def _require_optional_utc_timestamp(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_utc_timestamp(value, label)


def _require_canonical_uuid(value: object, label: str) -> str:
    text = _require_text(value, label)
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError) as error:
        raise ValueError(f"{label} must be a canonical UUID") from error
    if str(parsed) != text:
        raise ValueError(f"{label} must be a canonical UUID")
    return text


def _mapping_fingerprint(mapping: object) -> tuple[object, ...] | None:
    if type(mapping) is not FormalFactMapping:
        return None
    try:
        return (
            mapping.mapping_id,
            mapping.statement,
            mapping.metric_key,
            mapping.source_field,
            mapping.unit,
            mapping.nature,
            mapping.period_kind,
            mapping.accounting_basis,
        )
    except AttributeError:
        return None


def _binding_fingerprint(binding: object) -> tuple[object, ...] | None:
    if type(binding) is not _FormalFactBinding:
        return None
    try:
        return (
            binding.source,
            binding.dataset,
            binding.parser_id,
            binding.parser_version,
            binding.mapping_version,
            binding.exchange_scope,
            binding.mapping_ids,
        )
    except AttributeError:
        return None


@dataclass(frozen=True, slots=True)
class FormalFactMapping:
    mapping_id: str
    statement: Literal["income", "balance", "cash_flow"]
    metric_key: str
    source_field: str
    unit: Literal["CNY", "shares", "ratio", "CNY_per_share"]
    nature: Literal["instant", "duration"]
    period_kind: Literal["FY", "H1", "Q1", "Q3", "OTHER"]
    accounting_basis: str

    def __post_init__(self) -> None:
        _require_text(self.mapping_id, "mapping_id", identifier=True)
        if type(self.statement) is not str or self.statement not in _STATEMENTS:
            raise ValueError("mapping statement is invalid")
        _require_text(self.metric_key, "metric_key", identifier=True)
        _require_text(self.source_field, "source_field", controls=True)
        if type(self.unit) is not str or self.unit not in _UNITS:
            raise ValueError("mapping unit is invalid")
        if type(self.nature) is not str or self.nature not in _NATURES:
            raise ValueError("mapping nature is invalid")
        if type(self.period_kind) is not str or self.period_kind not in _PERIOD_KINDS:
            raise ValueError("mapping period_kind is invalid")
        _require_text(self.accounting_basis, "accounting_basis", controls=True)
        if self.statement == "balance" and self.nature != "instant":
            raise ValueError("balance mapping must be instant")
        if self.statement in {"income", "cash_flow"} and self.nature != "duration":
            raise ValueError("income and cash_flow mappings must be duration")


@dataclass(frozen=True, slots=True)
class _FormalFactBinding:
    source: str
    dataset: str
    parser_id: str
    parser_version: str
    mapping_version: str
    exchange_scope: Literal["SH", "SZ", "BJ"]
    mapping_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.source, "binding source", identifier=True)
        _require_text(self.dataset, "binding dataset", identifier=True)
        _require_text(self.parser_id, "binding parser_id", identifier=True)
        _require_text(self.parser_version, "binding parser_version", identifier=True)
        _require_text(self.mapping_version, "binding mapping_version", identifier=True)
        _require_exchange(self.exchange_scope, "binding exchange_scope")
        if (
            type(self.mapping_ids) is not tuple
            or not self.mapping_ids
            or tuple(sorted(self.mapping_ids)) != self.mapping_ids
            or len(set(self.mapping_ids)) != len(self.mapping_ids)
        ):
            raise ValueError("binding mapping_ids must be nonempty, sorted, and unique")
        for mapping_id in self.mapping_ids:
            _require_text(mapping_id, "binding mapping_id", identifier=True)


def _mapping_from_wire(value: object) -> FormalFactMapping:
    wire = _require_exact_keys(value, _MAPPING_KEYS, "mapping")
    return FormalFactMapping(
        mapping_id=_require_text(wire["mapping_id"], "mapping_id", identifier=True),
        statement=wire["statement"],  # type: ignore[arg-type]
        metric_key=_require_text(wire["metric_key"], "metric_key", identifier=True),
        source_field=_require_text(wire["source_field"], "source_field", controls=True),
        unit=wire["unit"],  # type: ignore[arg-type]
        nature=wire["nature"],  # type: ignore[arg-type]
        period_kind=wire["period_kind"],  # type: ignore[arg-type]
        accounting_basis=_require_text(wire["accounting_basis"], "accounting_basis", controls=True),
    )


def _binding_from_wire(value: object) -> _FormalFactBinding:
    wire = _require_exact_keys(value, _BINDING_KEYS, "mapping binding")
    mapping_ids_value = wire["mapping_ids"]
    if type(mapping_ids_value) is not list:
        raise ValueError("binding mapping_ids must be a JSON list")
    mapping_ids = tuple(
        _require_text(mapping_id, "binding mapping_id", identifier=True)
        for mapping_id in mapping_ids_value
    )
    return _FormalFactBinding(
        source=_require_text(wire["source"], "binding source", identifier=True),
        dataset=_require_text(wire["dataset"], "binding dataset", identifier=True),
        parser_id=_require_text(wire["parser_id"], "binding parser_id", identifier=True),
        parser_version=_require_text(wire["parser_version"], "binding parser_version", identifier=True),
        mapping_version=_require_text(wire["mapping_version"], "binding mapping_version", identifier=True),
        exchange_scope=_require_exchange(wire["exchange_scope"], "binding exchange_scope"),  # type: ignore[arg-type]
        mapping_ids=mapping_ids,
    )


def _parse_registry_bytes(value: object) -> tuple[dict[str, object], tuple[FormalFactMapping, ...], tuple[_FormalFactBinding, ...]]:
    wire = _load_canonical_object(value, label="financial mapping registry")
    _require_exact_keys(wire, _REGISTRY_KEYS, "financial mapping registry")
    if wire["schema_version"] != "formal-financial-mapping-registry-v1":
        raise ValueError("financial mapping registry schema_version is invalid")
    if wire["registry_role"] != "mapping":
        raise ValueError("financial mapping registry role is invalid")
    if wire["row_format"] != "item_value_v1":
        raise ValueError("financial mapping registry row_format is invalid")
    mapping_wires = wire["mappings"]
    binding_wires = wire["bindings"]
    if type(mapping_wires) is not list or type(binding_wires) is not list:
        raise ValueError("financial mapping registry mappings and bindings must be JSON lists")
    if not mapping_wires or not binding_wires:
        raise ValueError("financial mapping registry cannot be empty")
    mappings = tuple(_mapping_from_wire(item) for item in mapping_wires)
    bindings = tuple(_binding_from_wire(item) for item in binding_wires)
    mapping_by_id = {item.mapping_id: item for item in mappings}
    if len(mapping_by_id) != len(mappings):
        raise ValueError("financial mapping IDs must be unique")
    binding_identity = {
        (
            item.source,
            item.dataset,
            item.parser_id,
            item.parser_version,
            item.mapping_version,
            item.exchange_scope,
        )
        for item in bindings
    }
    if len(binding_identity) != len(bindings):
        raise ValueError("financial mapping binding identities must be unique")
    referenced: set[str] = set()
    for item in bindings:
        selected: list[FormalFactMapping] = []
        for mapping_id in item.mapping_ids:
            mapped = mapping_by_id.get(mapping_id)
            if mapped is None:
                raise ValueError("mapping binding references an unknown mapping ID")
            referenced.add(mapping_id)
            selected.append(mapped)
        metric_identity = {
            (mapped.statement, mapped.metric_key, mapped.period_kind, mapped.accounting_basis)
            for mapped in selected
        }
        if len(metric_identity) != len(selected):
            raise ValueError("mapping binding has an ambiguous metric identity")
        fields = {mapped.source_field for mapped in selected}
        if len(fields) != len(selected):
            raise ValueError("mapping binding has duplicate source fields")
    if referenced != set(mapping_by_id):
        raise ValueError("every mapping must be covered by a binding")
    return wire, mappings, bindings


def _verify_registry_signature(
    registry_bytes: object, signature: object, key_id: object, verifier: object
) -> tuple[str, str]:
    if type(registry_bytes) is not bytes:
        raise ValueError("financial mapping registry must be bytes")
    signature_text = _require_text(signature, "financial mapping registry signature")
    key_text = _require_text(key_id, "financial mapping registry key_id", identifier=True)
    verify = getattr(verifier, "verify", None)
    if not callable(verify):
        raise ValueError("financial mapping registry verifier is invalid")
    try:
        accepted = verify(registry_bytes, signature=signature_text, key_id=key_text)
    except Exception as error:
        raise ValueError("financial mapping registry verifier failed") from error
    if accepted is not True:
        raise ValueError("financial mapping registry signature was rejected")
    return signature_text, key_text


def _make_signed_financial_mapping_registry_type() -> type[object]:
    """Create a registry class whose trusted construction record is closure-private."""

    records: dict[int, tuple[weakref.ReferenceType[object], tuple[object, ...]]] = {}

    def forget(identity: int) -> None:
        records.pop(identity, None)

    def fingerprint(registry: object) -> tuple[object, ...] | None:
        if type(registry) is not SignedFinancialMappingRegistry:
            return None
        try:
            mappings = registry.mappings
            bindings = registry.bindings
            mapping_fingerprints = tuple(_mapping_fingerprint(item) for item in mappings)
            binding_fingerprints = tuple(_binding_fingerprint(item) for item in bindings)
            if None in mapping_fingerprints or None in binding_fingerprints:
                return None
            return (
                registry.canonical_json,
                registry.registry_hash,
                registry.signature,
                registry.key_id,
                mappings,
                bindings,
                mapping_fingerprints,
                binding_fingerprints,
            )
        except (AttributeError, TypeError):
            return None

    def require_verified(registry: object) -> tuple[object, ...]:
        identity = id(registry)
        record = records.get(identity)
        current = fingerprint(registry)
        if record is None or current is None or record[0]() is not registry or record[1] != current:
            raise ValueError("signed financial mapping registry was not verified or was mutated")
        return record[1]

    def mapping_snapshots(
        registry: object,
        *,
        source: str,
        dataset: str,
        parser_id: str,
        parser_version: str,
        mapping_version: str,
        exchange: str,
    ) -> tuple[FormalFactMapping, ...]:
        record = require_verified(registry)
        canonical = record[0]
        assert type(canonical) is bytes
        _, parsed_mappings, parsed_bindings = _parse_registry_bytes(canonical)
        matching = [
            binding
            for binding in parsed_bindings
            if (
                binding.source == source
                and binding.dataset == dataset
                and binding.parser_id == parser_id
                and binding.parser_version == parser_version
                and binding.mapping_version == mapping_version
                and binding.exchange_scope == exchange
            )
        ]
        if len(matching) != 1:
            raise ValueError("signed financial mapping binding is absent or ambiguous")
        mapping_by_id = {item.mapping_id: item for item in parsed_mappings}
        return tuple(mapping_by_id[mapping_id] for mapping_id in matching[0].mapping_ids)

    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
    class SignedFinancialMappingRegistry:
        canonical_json: bytes
        registry_hash: str
        signature: str
        key_id: str
        mappings: tuple[FormalFactMapping, ...]
        bindings: tuple[_FormalFactBinding, ...]

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise TypeError("SignedFinancialMappingRegistry must be loaded with from_signed_bytes")

        @classmethod
        def from_signed_bytes(
            cls,
            registry_bytes: bytes,
            *,
            signature: str,
            key_id: str,
            verifier: RegistrySignatureVerifier,
        ) -> "SignedFinancialMappingRegistry":
            if cls is not SignedFinancialMappingRegistry:
                raise ValueError("SignedFinancialMappingRegistry must have exact type")
            # Canonical decoding and signature verification both precede construction.
            _, mappings, bindings = _parse_registry_bytes(registry_bytes)
            signature_text, key_text = _verify_registry_signature(
                registry_bytes, signature, key_id, verifier
            )
            registry = object.__new__(SignedFinancialMappingRegistry)
            object.__setattr__(registry, "canonical_json", registry_bytes)
            object.__setattr__(registry, "registry_hash", hashlib.sha256(registry_bytes).hexdigest())
            object.__setattr__(registry, "signature", signature_text)
            object.__setattr__(registry, "key_id", key_text)
            object.__setattr__(registry, "mappings", mappings)
            object.__setattr__(registry, "bindings", bindings)
            sealed = fingerprint(registry)
            assert sealed is not None
            identity = id(registry)
            records[identity] = (
                weakref.ref(registry, lambda _reference, identity=identity: forget(identity)),
                sealed,
            )
            return registry

        def select(
            self,
            *,
            source: str,
            dataset: str,
            parser_id: str,
            parser_version: str,
            mapping_version: str,
            exchange: str,
        ) -> tuple[FormalFactMapping, ...]:
            return mapping_snapshots(
                self,
                source=source,
                dataset=dataset,
                parser_id=parser_id,
                parser_version=parser_version,
                mapping_version=mapping_version,
                exchange=exchange,
            )

    return SignedFinancialMappingRegistry


SignedFinancialMappingRegistry = _make_signed_financial_mapping_registry_type()
del _make_signed_financial_mapping_registry_type


def _freeze_json(value: object, *, label: str = "value") -> object:
    """Detach a JSON-shaped value without retaining parser-owned containers."""

    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{label} must not contain a non-finite float")
        return value
    if type(value) in {tuple, list}:
        return tuple(_freeze_json(item, label=label) for item in value)
    if isinstance(value, Mapping):
        try:
            items = tuple(value.items())
        except Exception as error:
            raise ValueError(f"{label} must be JSON-shaped") from error
        copied: dict[str, object] = {}
        for key, item in items:
            if type(key) is not str or key in copied:
                raise ValueError(f"{label} must have exact string keys")
            copied[key] = _freeze_json(item, label=label)
        return MappingProxyType(copied)
    raise ValueError(f"{label} must be JSON-shaped")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw_json(item) for item in value]
    return value


def _copy_mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    try:
        items = tuple(value.items())
    except Exception as error:
        raise ValueError(f"{label} must be a stable mapping") from error
    copied: dict[str, object] = {}
    for key, item in items:
        if type(key) is not str or key in copied:
            raise ValueError(f"{label} must have unique exact string keys")
        copied[key] = item
    return copied


@dataclass(frozen=True, slots=True)
class FormalFactIssue:
    code: str
    mapping_id: str | None
    source_field: str | None
    details: Mapping[str, object]

    def __post_init__(self) -> None:
        _require_text(self.code, "fact issue code", identifier=True)
        _require_optional_text(self.mapping_id, "fact issue mapping_id", identifier=True)
        _require_optional_text(self.source_field, "fact issue source_field", controls=True)
        frozen = _freeze_json(self.details, label="fact issue details")
        if not isinstance(frozen, Mapping):
            raise ValueError("fact issue details must be a mapping")
        object.__setattr__(self, "details", frozen)


def _period_kind_for(period_end: str) -> str:
    month_day = period_end[5:]
    return {
        "03-31": "Q1",
        "06-30": "H1",
        "09-30": "Q3",
        "12-31": "FY",
    }.get(month_day, "OTHER")


def _normalize_numeric_value(
    value: object, *, label: str, allow_decimal_string: bool = False
) -> float:
    if type(value) is bool:
        raise ValueError(f"{label} must be a finite numeric scalar")
    if type(value) is int:
        try:
            numeric = float(value)
        except OverflowError as error:
            raise ValueError(f"{label} must be finite") from error
    elif type(value) is float:
        numeric = value
    elif type(value) is str and allow_decimal_string:
        if _DECIMAL.fullmatch(value) is None:
            raise ValueError(f"{label} must be a strict ASCII decimal")
        try:
            numeric = float(value)
        except ValueError as error:
            raise ValueError(f"{label} must be a strict ASCII decimal") from error
    else:
        raise ValueError(f"{label} must be a finite numeric scalar")
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return 0.0 if numeric == 0.0 else numeric


def _fact_identity(values: Mapping[str, object]) -> str:
    return canonical_sha256(
        {key: values[key] for key in _FACT_FIELDS if key not in {"id", "created_at_utc"}}
    )


def _normalize_fact_values(
    supplied: Mapping[str, object], *, require_id: bool
) -> dict[str, object]:
    expected = frozenset(_FACT_FIELDS)
    if require_id:
        if set(supplied) != expected:
            raise ValueError("formal fact must contain exactly its serialization keys")
    elif set(supplied) != expected - {"id"}:
        raise ValueError("formal fact create must contain exactly its scientific fields")
    result: dict[str, object] = {}
    security_id_value = supplied["security_id"]
    if type(security_id_value) is not str:
        raise ValueError("formal fact security_id must be canonical")
    security_id = canonical_security_id(security_id_value)
    if security_id != security_id_value:
        raise ValueError("formal fact security_id must be canonical")
    result["security_id"] = security_id
    statement = supplied["statement"]
    if type(statement) is not str or statement not in _STATEMENTS:
        raise ValueError("formal fact statement is invalid")
    result["statement"] = statement
    result["metric_key"] = _require_text(supplied["metric_key"], "formal fact metric_key", identifier=True)
    period_end = _require_iso_date(supplied["period_end"], "formal fact period_end")
    period_kind = supplied["period_kind"]
    if type(period_kind) is not str or period_kind not in _PERIOD_KINDS:
        raise ValueError("formal fact period_kind is invalid")
    if _period_kind_for(period_end) != period_kind:
        raise ValueError("formal fact period_kind does not match period_end")
    result["period_end"] = period_end
    result["period_kind"] = period_kind
    nature = supplied["nature"]
    if type(nature) is not str or nature not in _NATURES:
        raise ValueError("formal fact nature is invalid")
    if statement == "balance" and nature != "instant":
        raise ValueError("formal balance fact must be instant")
    if statement in {"income", "cash_flow"} and nature != "duration":
        raise ValueError("formal income/cash_flow fact must be duration")
    result["nature"] = nature
    period_start_value = supplied["period_start"]
    if nature == "duration" and period_kind != "OTHER":
        expected_start = f"{period_end[:4]}-01-01"
        if _require_iso_date(period_start_value, "formal fact period_start") != expected_start:
            raise ValueError("formal fact period_start is not the canonical duration start")
        result["period_start"] = expected_start
    else:
        if period_start_value is not None:
            raise ValueError("formal instant/OTHER fact period_start must be null")
        result["period_start"] = None
    result["value"] = _normalize_numeric_value(supplied["value"], label="formal fact value")
    unit = supplied["unit"]
    if type(unit) is not str or unit not in _UNITS:
        raise ValueError("formal fact unit is invalid")
    result["unit"] = unit
    result["accounting_basis"] = _require_text(
        supplied["accounting_basis"], "formal fact accounting_basis", controls=True
    )
    published_at, published_precision = _require_publication(
        supplied["published_at_utc"], supplied["published_precision"], "formal fact published_at_utc"
    )
    effective_at = _require_utc_timestamp(supplied["effective_at_utc"], "formal fact effective_at_utc")
    evidence = supplied["effective_time_evidence_hash"]
    if published_precision == "timestamp":
        if evidence is not None or effective_at != published_at:
            raise ValueError("timestamp formal fact must equal publication and have no evidence hash")
    else:
        evidence = _require_sha256(evidence, "formal fact effective_time_evidence_hash")
        if _timestamp(effective_at) <= _timestamp(published_at):
            raise ValueError("date_only formal fact effective time must follow publication")
    result["published_at_utc"] = published_at
    result["published_precision"] = published_precision
    result["effective_at_utc"] = effective_at
    result["effective_time_evidence_hash"] = evidence
    result["source_updated_at_utc"] = _require_optional_utc_timestamp(
        supplied["source_updated_at_utc"], "formal fact source_updated_at_utc"
    )
    result["captured_at_utc"] = _require_utc_timestamp(
        supplied["captured_at_utc"], "formal fact captured_at_utc"
    )
    result["source_snapshot_id"] = _require_canonical_uuid(
        supplied["source_snapshot_id"], "formal fact source_snapshot_id"
    )
    result["source_content_sha256"] = _require_sha256(
        supplied["source_content_sha256"], "formal fact source_content_sha256"
    )
    result["source_refresh_generation"] = _require_text(
        supplied["source_refresh_generation"], "formal fact source_refresh_generation", controls=True
    )
    result["source_producing_task_id"] = _require_optional_text(
        supplied["source_producing_task_id"], "formal fact source_producing_task_id", controls=True
    )
    result["source_field"] = _require_text(
        supplied["source_field"], "formal fact source_field", controls=True
    )
    result["raw_value_sha256"] = _require_sha256(
        supplied["raw_value_sha256"], "formal fact raw_value_sha256"
    )
    result["parser_id"] = _require_text(supplied["parser_id"], "formal fact parser_id", identifier=True)
    result["parser_version"] = _require_text(
        supplied["parser_version"], "formal fact parser_version", identifier=True
    )
    result["mapping_version"] = _require_text(
        supplied["mapping_version"], "formal fact mapping_version", identifier=True
    )
    result["created_at_utc"] = _require_utc_timestamp(
        supplied["created_at_utc"], "formal fact created_at_utc"
    )
    identity = _fact_identity(result)
    if require_id:
        supplied_id = _require_sha256(supplied["id"], "formal fact id")
        if supplied_id != identity:
            raise ValueError("formal fact id does not match its scientific fields")
    result["id"] = identity
    return {key: result[key] for key in _FACT_FIELDS}


def _make_formal_financial_fact_type() -> type[object]:
    """Create the fact type with closure-private verified-object sealing."""

    records: dict[int, tuple[weakref.ReferenceType[object], tuple[object, ...]]] = {}

    def forget(identity: int) -> None:
        records.pop(identity, None)

    def fingerprint(fact: object) -> tuple[object, ...] | None:
        if type(fact) is not FormalFinancialFact:
            return None
        try:
            return tuple(getattr(fact, field) for field in _FACT_FIELDS)
        except AttributeError:
            return None

    def require_seal(fact: object) -> tuple[object, ...]:
        identity = id(fact)
        record = records.get(identity)
        current = fingerprint(fact)
        if record is None or current is None or record[0]() is not fact or record[1] != current:
            raise ValueError("formal financial fact was not constructed by a validated factory or was mutated")
        values = dict(zip(_FACT_FIELDS, current, strict=True))
        # Revalidate as defense in depth; this also rejects any impossible field mutation.
        if _normalize_fact_values(values, require_id=True) != values:
            raise ValueError("formal financial fact no longer has a valid canonical identity")
        return current

    def construct(values: Mapping[str, object], *, require_id: bool) -> "FormalFinancialFact":
        normalized = _normalize_fact_values(values, require_id=require_id)
        fact = object.__new__(FormalFinancialFact)
        for field in _FACT_FIELDS:
            object.__setattr__(fact, field, normalized[field])
        identity = id(fact)
        record = tuple(normalized[field] for field in _FACT_FIELDS)
        records[identity] = (
            weakref.ref(fact, lambda _reference, identity=identity: forget(identity)),
            record,
        )
        return fact

    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
    class FormalFinancialFact:
        id: str
        security_id: str
        statement: str
        metric_key: str
        period_start: str | None
        period_end: str
        period_kind: str
        value: float
        unit: str
        nature: str
        accounting_basis: str
        published_at_utc: str
        published_precision: Literal["timestamp", "date_only"]
        effective_at_utc: str
        effective_time_evidence_hash: str | None
        source_updated_at_utc: str | None
        captured_at_utc: str
        source_snapshot_id: str
        source_content_sha256: str
        source_refresh_generation: str
        source_producing_task_id: str | None
        source_field: str
        raw_value_sha256: str
        parser_id: str
        parser_version: str
        mapping_version: str
        created_at_utc: str

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise TypeError("FormalFinancialFact must be created with create or from_dict")

        @classmethod
        def create(cls, **values: object) -> "FormalFinancialFact":
            if cls is not FormalFinancialFact:
                raise ValueError("FormalFinancialFact must have exact type")
            return construct(values, require_id=False)

        def to_dict(self) -> Mapping[str, object]:
            sealed = require_seal(self)
            return MappingProxyType(dict(zip(_FACT_FIELDS, sealed, strict=True)))

        @classmethod
        def from_dict(cls, value: Mapping[str, object]) -> "FormalFinancialFact":
            if cls is not FormalFinancialFact:
                raise ValueError("FormalFinancialFact must have exact type")
            return construct(_copy_mapping(value, label="formal fact"), require_id=True)

    return FormalFinancialFact


FormalFinancialFact = _make_formal_financial_fact_type()
del _make_formal_financial_fact_type


@dataclass(frozen=True, slots=True)
class FormalFactExtraction:
    facts: tuple[FormalFinancialFact, ...]
    issues: tuple[FormalFactIssue, ...]

    def __post_init__(self) -> None:
        if type(self.facts) is not tuple or type(self.issues) is not tuple:
            raise ValueError("formal fact extraction values must be tuples")
        if any(type(fact) is not FormalFinancialFact for fact in self.facts):
            raise ValueError("formal fact extraction contains an invalid fact")
        if any(type(issue) is not FormalFactIssue for issue in self.issues):
            raise ValueError("formal fact extraction contains an invalid issue")


@dataclass(frozen=True, slots=True)
class _SnapshotLineage:
    snapshot_id: str
    source: str
    dataset: str
    request_fingerprint: str
    security_id: str
    period_or_date: str
    exchange: str | None
    content_sha256: str
    manifest_sha256: str
    content_path: str
    manifest_path: str
    original_url: str
    published_at_utc: str
    published_precision: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    effective_at_utc: str
    effective_time_evidence_hash: str | None
    refresh_generation: str
    producing_task_id: str | None
    parser_id: str
    parser_version: str
    mapping_version: str


@dataclass(frozen=True, slots=True)
class _DocumentLineage:
    parser_id: str
    parser_version: str
    security_id: str
    period: str
    published_at_utc: str
    published_precision: str
    source_updated_at_utc: str | None
    accounting_basis: str
    rows: tuple["_RowSnapshot", ...]


@dataclass(frozen=True, slots=True)
class _RowSnapshot:
    index: int
    valid_shape: bool
    item: str | None
    raw_value: object


_UNSAFE_RAW = object()


def _snapshot_lineage(snapshot_ref: object) -> _SnapshotLineage:
    """Read every ref field once, validate exact primitives, and detach it."""

    if type(snapshot_ref) is not OfficialSnapshotRef:
        raise ValueError("snapshot identity must have exact type OfficialSnapshotRef")
    try:
        raw_values = (
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
    except AttributeError as error:
        raise ValueError("snapshot identity is incomplete") from error
    (
        raw_snapshot_id,
        raw_source,
        raw_dataset,
        raw_fingerprint,
        raw_security_id,
        raw_period,
        raw_exchange,
        raw_content_hash,
        raw_manifest_hash,
        raw_content_path,
        raw_manifest_path,
        raw_original_url,
        raw_published_at,
        raw_precision,
        raw_source_updated,
        raw_captured_at,
        raw_effective_at,
        raw_evidence,
        raw_refresh_generation,
        raw_producing_task_id,
        raw_parser_id,
        raw_parser_version,
        raw_mapping_version,
        raw_status,
    ) = raw_values
    snapshot_id = _require_canonical_uuid(raw_snapshot_id, "snapshot snapshot_id")
    source = _require_text(raw_source, "snapshot source", identifier=True)
    dataset = _require_text(raw_dataset, "snapshot dataset", identifier=True)
    request_fingerprint = _require_sha256(raw_fingerprint, "snapshot request_fingerprint")
    if type(raw_security_id) is not str:
        raise ValueError("snapshot security identity must be nonnull and canonical")
    security_id = canonical_security_id(raw_security_id)
    if security_id != raw_security_id:
        raise ValueError("snapshot security identity must be nonnull and canonical")
    if type(raw_period) is not str:
        raise ValueError("snapshot period identity must be nonnull and canonical")
    period = _require_iso_date(raw_period, "snapshot period identity")
    exchange: str | None = None
    if raw_exchange is not None:
        exchange = _require_exchange(raw_exchange, "snapshot exchange")
        if exchange != security_id[:2]:
            raise ValueError("snapshot exchange does not match security identity")
    content_sha256 = _require_sha256(raw_content_hash, "snapshot content_sha256")
    manifest_sha256 = _require_sha256(raw_manifest_hash, "snapshot manifest_sha256")
    content_path = _require_text(raw_content_path, "snapshot content_path", controls=True)
    manifest_path = _require_text(raw_manifest_path, "snapshot manifest_path", controls=True)
    original_url = _require_text(raw_original_url, "snapshot original_url", controls=True)
    published_at, precision = _require_publication(
        raw_published_at, raw_precision, "snapshot published_at_utc"
    )
    source_updated = _require_optional_utc_timestamp(
        raw_source_updated, "snapshot source_updated_at_utc"
    )
    captured_at = _require_utc_timestamp(raw_captured_at, "snapshot captured_at_utc")
    effective_at = _require_utc_timestamp(raw_effective_at, "snapshot effective_at_utc")
    if precision == "timestamp":
        if raw_evidence is not None or effective_at != published_at:
            raise ValueError("timestamp snapshot effective lineage is invalid")
        evidence: str | None = None
    else:
        evidence = _require_sha256(raw_evidence, "snapshot effective_time_evidence_hash")
        if _timestamp(effective_at) <= _timestamp(published_at):
            raise ValueError("date_only snapshot effective time must follow publication")
    refresh_generation = _require_text(
        raw_refresh_generation, "snapshot refresh_generation", controls=True
    )
    producing_task_id = _require_optional_text(
        raw_producing_task_id, "snapshot producing_task_id", controls=True
    )
    parser_id = _require_text(raw_parser_id, "snapshot parser_id", identifier=True)
    parser_version = _require_text(raw_parser_version, "snapshot parser_version", identifier=True)
    mapping_version = _require_text(raw_mapping_version, "snapshot mapping_version", identifier=True)
    if type(raw_status) is not str or raw_status != "verified":
        raise ValueError("snapshot verification status must be verified")
    expected_fingerprint = canonical_sha256(
        {
            "dataset": dataset,
            "exchange": exchange,
            "period_or_date": period,
            "security_id": security_id,
            "source": source,
        }
    )
    if request_fingerprint != expected_fingerprint:
        raise ValueError("snapshot request fingerprint is not canonical")
    return _SnapshotLineage(
        snapshot_id=snapshot_id,
        source=source,
        dataset=dataset,
        request_fingerprint=request_fingerprint,
        security_id=security_id,
        period_or_date=period,
        exchange=exchange,
        content_sha256=content_sha256,
        manifest_sha256=manifest_sha256,
        content_path=content_path,
        manifest_path=manifest_path,
        original_url=original_url,
        published_at_utc=published_at,
        published_precision=precision,
        source_updated_at_utc=source_updated,
        captured_at_utc=captured_at,
        effective_at_utc=effective_at,
        effective_time_evidence_hash=evidence,
        refresh_generation=refresh_generation,
        producing_task_id=producing_task_id,
        parser_id=parser_id,
        parser_version=parser_version,
        mapping_version=mapping_version,
    )


def _snapshot_row(index: int, row: object) -> _RowSnapshot:
    """Detach a parser row enough to avoid retaining mutable/custom row values."""

    if not isinstance(row, Mapping):
        return _RowSnapshot(index, False, None, _UNSAFE_RAW)
    try:
        pairs = tuple(row.items())
    except Exception:
        return _RowSnapshot(index, False, None, _UNSAFE_RAW)
    copied: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in copied:
            return _RowSnapshot(index, False, None, _UNSAFE_RAW)
        copied[key] = value
    if set(copied) != {"ITEM", "VALUE"}:
        return _RowSnapshot(index, False, None, _UNSAFE_RAW)
    item = copied["ITEM"]
    if type(item) is not str or not item or item != item.strip() or _CONTROL.search(item) is not None:
        return _RowSnapshot(index, False, None, _UNSAFE_RAW)
    raw_value = copied["VALUE"]
    # A row's VALUE must itself be a raw JSON scalar.  Non-finite floats retain
    # their shape here and become deterministic nonnumeric issues downstream.
    if raw_value is not None and type(raw_value) not in {bool, int, float, str}:
        return _RowSnapshot(index, False, None, _UNSAFE_RAW)
    return _RowSnapshot(index, True, item, raw_value)


def _document_lineage(document: object) -> _DocumentLineage:
    if type(document) is not ParsedOfficialDocument:
        raise ValueError("document must have exact type ParsedOfficialDocument")
    try:
        raw_values = (
            document.parser_id,
            document.parser_version,
            document.declared_security_id,
            document.declared_period,
            document.published_at_utc,
            document.published_precision,
            document.source_updated_at_utc,
            document.rows,
            document.accounting_basis,
            document.bootstrap_calendar,
        )
    except AttributeError as error:
        raise ValueError("document is incomplete") from error
    (
        raw_parser_id,
        raw_parser_version,
        raw_security_id,
        raw_period,
        raw_published_at,
        raw_precision,
        raw_source_updated,
        raw_rows,
        raw_accounting_basis,
        raw_bootstrap,
    ) = raw_values
    if raw_bootstrap is not False:
        raise ValueError("bootstrap calendar documents cannot produce financial facts")
    parser_id = _require_text(raw_parser_id, "document parser_id", identifier=True)
    parser_version = _require_text(raw_parser_version, "document parser_version", identifier=True)
    if type(raw_security_id) is not str:
        raise ValueError("document security identity must be nonnull and canonical")
    security_id = canonical_security_id(raw_security_id)
    if security_id != raw_security_id:
        raise ValueError("document security identity must be nonnull and canonical")
    if type(raw_period) is not str:
        raise ValueError("document period identity must be nonnull and canonical")
    period = _require_iso_date(raw_period, "document period identity")
    published_at, precision = _require_publication(
        raw_published_at, raw_precision, "document published_at_utc"
    )
    source_updated = _require_optional_utc_timestamp(
        raw_source_updated, "document source_updated_at_utc"
    )
    if type(raw_rows) is not tuple:
        raise ValueError("document rows must be an exact tuple")
    rows = tuple(_snapshot_row(index, row) for index, row in enumerate(raw_rows))
    accounting_basis = _require_text(
        raw_accounting_basis, "document accounting_basis", controls=True
    )
    return _DocumentLineage(
        parser_id=parser_id,
        parser_version=parser_version,
        security_id=security_id,
        period=period,
        published_at_utc=published_at,
        published_precision=precision,
        source_updated_at_utc=source_updated,
        accounting_basis=accounting_basis,
        rows=rows,
    )


_ISSUE_PRIORITY = {
    "required_source_field_missing": 0,
    "duplicate_source_field": 1,
    "nonnumeric_value": 2,
    "invalid_row_shape": 3,
    "unknown_source_field": 4,
    "mapping_not_applicable": 5,
}


def _issue_sort_key(issue: FormalFactIssue) -> tuple[object, ...]:
    return (
        _ISSUE_PRIORITY.get(issue.code, 99),
        issue.mapping_id or "",
        issue.source_field or "",
        canonical_sha256(_thaw_json(issue.details)),
    )


def _new_issue(
    code: str,
    mapping_id: str | None,
    source_field: str | None,
    details: Mapping[str, object],
) -> FormalFactIssue:
    return FormalFactIssue(code, mapping_id, source_field, details)


def extract_formal_financial_facts(
    document: ParsedOfficialDocument,
    snapshot_ref: OfficialSnapshotRef,
    registry: SignedFinancialMappingRegistry,
    created_at_utc: str,
) -> FormalFactExtraction:
    """Extract only exact signed-map facts from one verified official document.

    Identity and lineage validation is deliberately all-or-nothing.  Row-level
    uncertainty is represented by deterministic issues, never guessed facts.
    """

    if type(registry) is not SignedFinancialMappingRegistry:
        raise ValueError("registry must have exact type SignedFinancialMappingRegistry")
    snapshot = _snapshot_lineage(snapshot_ref)
    parsed_document = _document_lineage(document)
    created = _require_utc_timestamp(created_at_utc, "formal fact created_at_utc")
    if (
        parsed_document.security_id != snapshot.security_id
        or parsed_document.period != snapshot.period_or_date
    ):
        raise ValueError("document and snapshot identity disagree")
    if snapshot.exchange is not None and snapshot.exchange != parsed_document.security_id[:2]:
        raise ValueError("snapshot exchange and document security disagree")
    if (
        parsed_document.parser_id != snapshot.parser_id
        or parsed_document.parser_version != snapshot.parser_version
    ):
        raise ValueError("document and snapshot parser lineage disagree")
    if (
        parsed_document.published_at_utc != snapshot.published_at_utc
        or parsed_document.published_precision != snapshot.published_precision
        or parsed_document.source_updated_at_utc != snapshot.source_updated_at_utc
    ):
        raise ValueError("document and snapshot publication lineage disagree")
    # SignedFinancialMappingRegistry.select first validates its closure seal and
    # then reconstructs mapping values from its signed canonical bytes.
    selected_mappings = registry.select(
        source=snapshot.source,
        dataset=snapshot.dataset,
        parser_id=snapshot.parser_id,
        parser_version=snapshot.parser_version,
        mapping_version=snapshot.mapping_version,
        exchange=parsed_document.security_id[:2],
    )
    period_kind = _period_kind_for(parsed_document.period)
    applicable = tuple(
        item
        for item in selected_mappings
        if item.accounting_basis == parsed_document.accounting_basis
        and item.period_kind == period_kind
    )
    if not applicable:
        return FormalFactExtraction(
            (),
            (
                _new_issue(
                    "mapping_not_applicable",
                    None,
                    None,
                    {
                        "accounting_basis": parsed_document.accounting_basis,
                        "period_kind": period_kind,
                    },
                ),
            ),
        )
    by_field = {item.source_field: item for item in applicable}
    matches: dict[str, list[_RowSnapshot]] = {field: [] for field in by_field}
    issues: list[FormalFactIssue] = []
    for row in parsed_document.rows:
        if not row.valid_shape:
            issues.append(_new_issue("invalid_row_shape", None, None, {"row_index": row.index}))
            continue
        assert row.item is not None
        if row.item not in by_field:
            issues.append(
                _new_issue(
                    "unknown_source_field",
                    None,
                    row.item,
                    {"row_index": row.index, "source_field": row.item},
                )
            )
            continue
        matches[row.item].append(row)
    facts: list[FormalFinancialFact] = []
    for mapped in sorted(applicable, key=lambda item: (item.mapping_id, item.source_field)):
        field_rows = matches[mapped.source_field]
        if not field_rows:
            issues.append(
                _new_issue(
                    "required_source_field_missing",
                    mapped.mapping_id,
                    mapped.source_field,
                    {"mapping_id": mapped.mapping_id, "source_field": mapped.source_field},
                )
            )
            continue
        if len(field_rows) != 1:
            issues.append(
                _new_issue(
                    "duplicate_source_field",
                    mapped.mapping_id,
                    mapped.source_field,
                    {
                        "mapping_id": mapped.mapping_id,
                        "row_indices": tuple(item.index for item in field_rows),
                        "source_field": mapped.source_field,
                    },
                )
            )
            continue
        raw = field_rows[0].raw_value
        try:
            if raw is _UNSAFE_RAW:
                raise ValueError("unsafe parser scalar")
            value = _normalize_numeric_value(
                raw, label="source row value", allow_decimal_string=True
            )
            raw_hash = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
        except (TypeError, ValueError, OverflowError):
            issues.append(
                _new_issue(
                    "nonnumeric_value",
                    mapped.mapping_id,
                    mapped.source_field,
                    {
                        "mapping_id": mapped.mapping_id,
                        "row_index": field_rows[0].index,
                        "source_field": mapped.source_field,
                    },
                )
            )
            continue
        period_start = (
            f"{parsed_document.period[:4]}-01-01"
            if mapped.nature == "duration" and period_kind != "OTHER"
            else None
        )
        facts.append(
            FormalFinancialFact.create(
                security_id=parsed_document.security_id,
                statement=mapped.statement,
                metric_key=mapped.metric_key,
                period_start=period_start,
                period_end=parsed_document.period,
                period_kind=period_kind,
                value=value,
                unit=mapped.unit,
                nature=mapped.nature,
                accounting_basis=mapped.accounting_basis,
                published_at_utc=snapshot.published_at_utc,
                published_precision=snapshot.published_precision,
                effective_at_utc=snapshot.effective_at_utc,
                effective_time_evidence_hash=snapshot.effective_time_evidence_hash,
                source_updated_at_utc=snapshot.source_updated_at_utc,
                captured_at_utc=snapshot.captured_at_utc,
                source_snapshot_id=snapshot.snapshot_id,
                source_content_sha256=snapshot.content_sha256,
                source_refresh_generation=snapshot.refresh_generation,
                source_producing_task_id=snapshot.producing_task_id,
                source_field=mapped.source_field,
                raw_value_sha256=raw_hash,
                parser_id=snapshot.parser_id,
                parser_version=snapshot.parser_version,
                mapping_version=snapshot.mapping_version,
                created_at_utc=created,
            )
        )
    return FormalFactExtraction(
        tuple(sorted(facts, key=lambda fact: fact.id)),
        tuple(sorted(issues, key=_issue_sort_key)),
    )


__all__ = [
    "FormalFactExtraction",
    "FormalFactIssue",
    "FormalFactMapping",
    "FormalFinancialFact",
    "SignedFinancialMappingRegistry",
    "extract_formal_financial_facts",
]
