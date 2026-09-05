"""Signed Formal V3 feature definitions and immutable feature-bundle records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
import struct
import uuid
import weakref
from typing import Literal

from .formal_financial_schema import FormalFinancialFact
from .formal_registry_manifest import FormalRegistryManifest
from .formal_sources import RegistrySignatureVerifier
from .formal_universe import canonical_security_id


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_QUARTER = re.compile(r"^[0-9]{4}Q[1-4]$")
_TEMPLATES = ("bank", "broker", "general_nonfinancial", "insurance", "real_estate")
_DIMENSIONS = frozenset({"G", "V", "M", "EQ", "FS", "CA", "T"})
_UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})
_FORMULA_OPS = frozenset({"fact", "add", "subtract", "divide", "cagr", "median", "minimum"})
_MISSING_STATUSES = frozenset({"missing", "blocked", "not_applicable"})
_REGISTRY_KEYS = frozenset(
    {
        "schema_version",
        "registry_role",
        "contract_version",
        "source_registry_hash",
        "mapping_registry_hash",
        "template_ids",
        "slots",
    }
)
_SLOT_KEYS = frozenset(
    {"slot_id", "template_id", "dimension", "required", "unit", "formula", "formula_version"}
)
_EVIDENCE_KEYS = frozenset(
    {
        "formal_fact_id",
        "source_snapshot_id",
        "source_content_sha256",
        "source_refresh_generation",
        "source_field",
        "raw_value_sha256",
        "published_at_utc",
        "published_precision",
        "effective_at_utc",
        "mapping_version",
    }
)
_VALUE_KEYS = frozenset(
    {"slot_id", "value", "unit", "status", "formula_version", "evidence", "missing_reason"}
)
_BUNDLE_KEYS = frozenset(
    {
        "schema_version",
        "contract_version",
        "security_id",
        "as_of_utc",
        "template_id",
        "registry_manifest_hash",
        "feature_registry_hash",
        "input_hash",
        "values",
        "history_endpoints",
        "comparable_quarter_keys",
        "blockers",
    }
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


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _snapshot_json(value: object, *, label: str = "value") -> object:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite value")
        return value
    if type(value) is list:
        return [_snapshot_json(item, label=label) for item in value]
    if type(value) is dict:
        copied: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str or key in copied:
                raise ValueError(f"{label} must have unique exact string keys")
            copied[key] = _snapshot_json(item, label=label)
        return copied
    raise ValueError(f"{label} must contain only JSON-native values")


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
    if _canonical_json_bytes(parsed) != value:
        raise ValueError(f"{label} must be canonical JSON")
    return parsed


def _require_text(value: object, label: str, *, identifier: bool = False) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be already-trimmed nonempty text")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} must be control-free")
    if identifier and _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a safe identifier")
    return value


def _require_hash(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _require_uuid(value: object, label: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise ValueError(f"{label} must be a canonical UUID") from error
    if str(parsed) != value:
        raise ValueError(f"{label} must be a canonical UUID")
    return value


def _require_utc(value: object, label: str) -> str:
    if type(value) is not str or not value.endswith("+00:00"):
        raise ValueError(f"{label} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a canonical UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be a canonical UTC timestamp")
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be a canonical UTC timestamp")
    return value


def _require_date(value: object, label: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be an ISO date")
    return value


def _require_exact_keys(value: object, expected: frozenset[str], label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"{label} must be an exact JSON object")
    copied = _snapshot_json(value, label=label)
    assert type(copied) is dict
    if set(copied) != expected:
        raise ValueError(f"{label} has unknown or missing keys")
    return copied


@dataclass(frozen=True, slots=True)
class FormulaNode:
    op: Literal["fact", "add", "subtract", "divide", "cagr", "median", "minimum"]
    fact_key: str | None = None
    period_key: str | None = None
    left: "FormulaNode | None" = None
    right: "FormulaNode | None" = None
    items: tuple["FormulaNode", ...] = ()
    intervals: int | None = None

    def __post_init__(self) -> None:
        _formula_to_dict(self, set())

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FormulaNode":
        if cls is not FormulaNode:
            raise ValueError("FormulaNode must have exact type")
        return _parse_formula(value, set())

    def to_dict(self) -> dict[str, object]:
        return _formula_to_dict(self, set())


def _parse_formula(value: object, ancestors: set[int]) -> FormulaNode:
    if type(value) is not dict:
        raise ValueError("formula node must be an exact JSON object")
    identity = id(value)
    if identity in ancestors:
        raise ValueError("formula node must not be cyclic")
    ancestors.add(identity)
    try:
        op = value.get("op")
        if type(op) is not str or op not in _FORMULA_OPS:
            raise ValueError("formula op is invalid")
        expected = {
            "fact": {"op", "fact_key", "period_key"},
            "add": {"op", "left", "right"},
            "subtract": {"op", "left", "right"},
            "divide": {"op", "left", "right"},
            "cagr": {"op", "left", "right", "intervals"},
            "median": {"op", "items"},
            "minimum": {"op", "items"},
        }[op]
        if set(value) != expected or any(type(key) is not str for key in value):
            raise ValueError("formula node has unknown or missing keys")
        if op == "fact":
            return FormulaNode(
                op="fact",
                fact_key=_require_text(value["fact_key"], "formula fact_key", identifier=True),
                period_key=_require_text(value["period_key"], "formula period_key", identifier=True),
            )
        if op in {"add", "subtract", "divide", "cagr"}:
            left = _parse_formula(value["left"], ancestors)
            right = _parse_formula(value["right"], ancestors)
            intervals: int | None = None
            if op == "cagr":
                supplied = value["intervals"]
                if type(supplied) is not int or supplied <= 0:
                    raise ValueError("cagr intervals must be a positive exact integer")
                intervals = supplied
            return FormulaNode(op=op, left=left, right=right, intervals=intervals)
        supplied_items = value["items"]
        if type(supplied_items) is not list:
            raise ValueError(f"{op} items must be a JSON array")
        items = tuple(_parse_formula(item, ancestors) for item in supplied_items)
        return FormulaNode(op=op, items=items)
    finally:
        ancestors.remove(identity)


def _formula_to_dict(node: object, ancestors: set[int]) -> dict[str, object]:
    if type(node) is not FormulaNode:
        raise ValueError("formula children must have exact type FormulaNode")
    identity = id(node)
    if identity in ancestors:
        raise ValueError("formula node must not be cyclic")
    ancestors.add(identity)
    try:
        if type(node.op) is not str or node.op not in _FORMULA_OPS:
            raise ValueError("formula op is invalid")
        if node.op == "fact":
            if (
                node.left is not None or node.right is not None or node.items != ()
                or node.intervals is not None
            ):
                raise ValueError("fact formula has invalid children")
            return {
                "op": "fact",
                "fact_key": _require_text(node.fact_key, "formula fact_key", identifier=True),
                "period_key": _require_text(node.period_key, "formula period_key", identifier=True),
            }
        if node.fact_key is not None or node.period_key is not None:
            raise ValueError("non-fact formula cannot contain fact fields")
        if node.op in {"add", "subtract", "divide", "cagr"}:
            if node.items != ():
                raise ValueError("binary formula cannot contain items")
            left = _formula_to_dict(node.left, ancestors)
            right = _formula_to_dict(node.right, ancestors)
            result: dict[str, object] = {"op": node.op, "left": left, "right": right}
            if node.op == "cagr":
                if type(node.intervals) is not int or node.intervals <= 0:
                    raise ValueError("cagr intervals must be a positive exact integer")
                result["intervals"] = node.intervals
            elif node.intervals is not None:
                raise ValueError("non-cagr binary formula cannot contain intervals")
            return result
        if node.left is not None or node.right is not None or node.intervals is not None:
            raise ValueError("aggregate formula has invalid children")
        if type(node.items) is not tuple or len(node.items) < 2:
            raise ValueError(f"{node.op} requires at least two items")
        items = [_formula_to_dict(item, ancestors) for item in node.items]
        item_bytes = tuple(_canonical_json_bytes(item) for item in items)
        if any(left >= right for left, right in zip(item_bytes, item_bytes[1:])):
            raise ValueError(f"{node.op} items must be strictly sorted and unique")
        return {"op": node.op, "items": items}
    finally:
        ancestors.remove(identity)


@dataclass(frozen=True, slots=True)
class FormalFeatureSlot:
    slot_id: str
    template_id: str
    dimension: Literal["G", "V", "M", "EQ", "FS", "CA", "T"]
    required: bool
    unit: str
    formula: FormulaNode
    formula_version: str

    def __post_init__(self) -> None:
        _slot_to_dict(self)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FormalFeatureSlot":
        if cls is not FormalFeatureSlot:
            raise ValueError("FormalFeatureSlot must have exact type")
        wire = _require_exact_keys(value, _SLOT_KEYS, "formal feature slot")
        formula_wire = wire["formula"]
        if type(formula_wire) is not dict:
            raise ValueError("formal feature slot formula must be an object")
        return cls(
            slot_id=wire["slot_id"],
            template_id=wire["template_id"],
            dimension=wire["dimension"],
            required=wire["required"],
            unit=wire["unit"],
            formula=FormulaNode.from_dict(formula_wire),
            formula_version=wire["formula_version"],
        )

    def to_dict(self) -> dict[str, object]:
        return _slot_to_dict(self)


def _slot_to_dict(slot: object) -> dict[str, object]:
    if type(slot) is not FormalFeatureSlot:
        raise ValueError("formal feature slot must have exact type")
    slot_id = _require_text(slot.slot_id, "feature slot_id", identifier=True)
    if type(slot.template_id) is not str or slot.template_id not in _TEMPLATES:
        raise ValueError("feature slot template_id is invalid")
    if type(slot.dimension) is not str or slot.dimension not in _DIMENSIONS:
        raise ValueError("feature slot dimension is invalid")
    if type(slot.required) is not bool:
        raise ValueError("feature slot required must be an exact bool")
    if type(slot.unit) is not str or slot.unit not in _UNITS:
        raise ValueError("feature slot unit is invalid")
    formula_version = _require_text(
        slot.formula_version, "feature slot formula_version", identifier=True
    )
    return {
        "slot_id": slot_id,
        "template_id": slot.template_id,
        "dimension": slot.dimension,
        "required": slot.required,
        "unit": slot.unit,
        "formula": _formula_to_dict(slot.formula, set()),
        "formula_version": formula_version,
    }


def _parse_registry_bytes(
    registry_bytes: object,
) -> tuple[dict[str, object], tuple[FormalFeatureSlot, ...]]:
    wire = _load_canonical_object(registry_bytes, label="formal feature registry")
    if set(wire) != _REGISTRY_KEYS:
        raise ValueError("formal feature registry has unknown or missing keys")
    if wire["schema_version"] != "formal-feature-registry-v1":
        raise ValueError("formal feature registry schema_version is invalid")
    if wire["registry_role"] != "feature":
        raise ValueError("formal feature registry role is invalid")
    _require_text(wire["contract_version"], "feature contract_version", identifier=True)
    _require_hash(wire["source_registry_hash"], "feature source_registry_hash")
    _require_hash(wire["mapping_registry_hash"], "feature mapping_registry_hash")
    template_values = wire["template_ids"]
    if type(template_values) is not list or not template_values:
        raise ValueError("feature template_ids must be a nonempty JSON array")
    template_ids = tuple(template_values)
    if any(type(item) is not str or item not in _TEMPLATES for item in template_ids):
        raise ValueError("feature template_ids contain an invalid template")
    if tuple(sorted(set(template_ids))) != template_ids:
        raise ValueError("feature template_ids must be sorted and unique")
    slot_values = wire["slots"]
    if type(slot_values) is not list or not slot_values:
        raise ValueError("formal feature registry slots must be a nonempty JSON array")
    slots = tuple(FormalFeatureSlot.from_dict(item) for item in slot_values)
    slot_ids = tuple(slot.slot_id for slot in slots)
    if tuple(sorted(set(slot_ids))) != slot_ids:
        raise ValueError("feature slot IDs must be globally sorted and unique")
    declared_templates = set(template_ids)
    if any(slot.template_id not in declared_templates for slot in slots):
        raise ValueError("feature slot references an undeclared template")
    if {slot.template_id for slot in slots} != declared_templates:
        raise ValueError("every declared template must contain at least one explicit slot")
    return wire, slots


def _verify_registry_signature(
    registry_bytes: object, signature: object, key_id: object, verifier: object
) -> tuple[str, str]:
    if type(registry_bytes) is not bytes:
        raise ValueError("formal feature registry must be bytes")
    signature_text = _require_text(signature, "formal feature registry signature")
    key_text = _require_text(key_id, "formal feature registry key_id", identifier=True)
    verify = getattr(verifier, "verify", None)
    if not callable(verify):
        raise ValueError("formal feature registry signature verifier is invalid")
    try:
        accepted = verify(registry_bytes, signature=signature_text, key_id=key_text)
    except Exception as error:
        raise ValueError("formal feature registry signature verification failed") from error
    if accepted is not True:
        raise ValueError("formal feature registry signature was rejected")
    return signature_text, key_text


def _validate_root(root: object) -> FormalRegistryManifest:
    if type(root) is not FormalRegistryManifest:
        raise ValueError("registry manifest must be an exact sealed FormalRegistryManifest")
    try:
        hashes = {
            field: getattr(root, field)
            for field in (
                "source_registry_hash",
                "mapping_registry_hash",
                "feature_registry_hash",
                "scoring_registry_hash",
                "industry_registry_hash",
                "cyclic_registry_hash",
                "redline_registry_hash",
                "status_registry_hash",
                "event_registry_hash",
            )
        }
        root.assert_member_hashes(**hashes)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("registry manifest is unsealed, forged, or mutated") from error
    return root


def _release_eligible(
    wire: dict[str, object], registry_hash: str, root: FormalRegistryManifest | None
) -> bool:
    if root is None:
        return False
    manifest = _validate_root(root)
    try:
        manifest.require_official()
    except ValueError:
        if manifest.purpose == "test":
            return False
        raise
    return (
        manifest.feature_registry_hash == registry_hash
        and manifest.source_registry_hash == wire["source_registry_hash"]
        and manifest.mapping_registry_hash == wire["mapping_registry_hash"]
        and tuple(wire["template_ids"]) == _TEMPLATES
    )


def _make_signed_registry_type() -> tuple[type[object], object]:
    sensitive_fields = frozenset(
        {
            "canonical_json",
            "registry_hash",
            "signature",
            "key_id",
            "contract_version",
            "source_registry_hash",
            "mapping_registry_hash",
            "template_ids",
            "slots",
            "release_eligible",
        }
    )

    @dataclass(frozen=True)
    class _Seal:
        canonical_json: bytes
        registry_hash: str
        signature: str
        key_id: str
        contract_version: str
        source_registry_hash: str
        mapping_registry_hash: str
        template_ids: tuple[str, ...]
        slots: tuple[FormalFeatureSlot, ...]
        slot_bytes: tuple[bytes, ...]
        release_eligible: bool

    records: dict[int, tuple[weakref.ReferenceType[object], _Seal]] = {}

    def forget(identity: int) -> None:
        records.pop(identity, None)

    def fingerprint(registry: object) -> _Seal | None:
        if type(registry) is not SignedFormalFeatureRegistry:
            return None
        try:
            read = object.__getattribute__
            values = (
                read(registry, "canonical_json"),
                read(registry, "registry_hash"),
                read(registry, "signature"),
                read(registry, "key_id"),
                read(registry, "contract_version"),
                read(registry, "source_registry_hash"),
                read(registry, "mapping_registry_hash"),
                read(registry, "template_ids"),
                read(registry, "slots"),
                read(registry, "release_eligible"),
            )
        except AttributeError:
            return None
        if (
            type(values[0]) is not bytes
            or any(type(value) is not str for value in values[1:7])
            or type(values[7]) is not tuple
            or any(type(item) is not str for item in values[7])
            or type(values[8]) is not tuple
            or any(type(item) is not FormalFeatureSlot for item in values[8])
            or type(values[9]) is not bool
        ):
            return None
        try:
            slot_bytes = tuple(_canonical_json_bytes(item.to_dict()) for item in values[8])
        except (TypeError, ValueError):
            return None
        return _Seal(*values[:9], slot_bytes, values[9])

    def require_verified(registry: object) -> _Seal:
        record = records.get(id(registry))
        current = fingerprint(registry)
        if record is None or current is None or record[0]() is not registry:
            raise ValueError("signed formal feature registry was not verified or was mutated")
        sealed = record[1]
        if (
            current.canonical_json != sealed.canonical_json
            or current.registry_hash != sealed.registry_hash
            or current.signature != sealed.signature
            or current.key_id != sealed.key_id
            or current.contract_version != sealed.contract_version
            or current.source_registry_hash != sealed.source_registry_hash
            or current.mapping_registry_hash != sealed.mapping_registry_hash
            or current.template_ids is not sealed.template_ids
            or current.slots is not sealed.slots
            or current.slot_bytes != sealed.slot_bytes
            or current.release_eligible is not sealed.release_eligible
        ):
            raise ValueError("signed formal feature registry was not verified or was mutated")
        parsed, _ = _parse_registry_bytes(sealed.canonical_json)
        if hashlib.sha256(sealed.canonical_json).hexdigest() != sealed.registry_hash:
            raise ValueError("signed formal feature registry hash no longer matches")
        if parsed["contract_version"] != sealed.contract_version:
            raise ValueError("signed formal feature registry contract changed")
        return sealed

    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
    class SignedFormalFeatureRegistry:
        canonical_json: bytes
        registry_hash: str
        signature: str
        key_id: str
        contract_version: str
        source_registry_hash: str
        mapping_registry_hash: str
        template_ids: tuple[str, ...]
        slots: tuple[FormalFeatureSlot, ...]
        release_eligible: bool

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise TypeError("SignedFormalFeatureRegistry must be loaded from signed bytes")

        def __getattribute__(self, name: str) -> object:
            if name in sensitive_fields:
                return getattr(require_verified(self), name)
            return object.__getattribute__(self, name)

        def slots_for_template(self, template_id: str) -> tuple[FormalFeatureSlot, ...]:
            sealed = require_verified(self)
            if type(template_id) is not str or template_id not in sealed.template_ids:
                raise ValueError("feature template is not declared")
            _, effective_slots = _parse_registry_bytes(sealed.canonical_json)
            return tuple(slot for slot in effective_slots if slot.template_id == template_id)

        def require_release_eligible(self) -> None:
            sealed = require_verified(self)
            if sealed.release_eligible is not True:
                raise ValueError("formal feature registry is not release eligible")

    def construct(
        *, canonical_json: bytes, registry_hash: str, signature: str, key_id: str,
        wire: dict[str, object], slots: tuple[FormalFeatureSlot, ...], release_eligible: bool,
    ) -> SignedFormalFeatureRegistry:
        registry = object.__new__(SignedFormalFeatureRegistry)
        for name, value in (
            ("canonical_json", canonical_json),
            ("registry_hash", registry_hash),
            ("signature", signature),
            ("key_id", key_id),
            ("contract_version", wire["contract_version"]),
            ("source_registry_hash", wire["source_registry_hash"]),
            ("mapping_registry_hash", wire["mapping_registry_hash"]),
            ("template_ids", tuple(wire["template_ids"])),
            ("slots", slots),
            ("release_eligible", release_eligible),
        ):
            object.__setattr__(registry, name, value)
        sealed = fingerprint(registry)
        assert sealed is not None
        identity = id(registry)
        records[identity] = (
            weakref.ref(registry, lambda _reference, identity=identity: forget(identity)), sealed
        )
        return registry

    return SignedFormalFeatureRegistry, construct


SignedFormalFeatureRegistry, _construct_signed_registry = _make_signed_registry_type()
del _make_signed_registry_type


def _make_registry_loader(construct_registry: object) -> object:
    def load_signed_feature_registry(
        registry_bytes: bytes,
        signature: str,
        key_id: str,
        verifier: RegistrySignatureVerifier,
        *,
        registry_manifest: FormalRegistryManifest | None = None,
    ) -> SignedFormalFeatureRegistry:
        wire, slots = _parse_registry_bytes(registry_bytes)
        signature_text, key_text = _verify_registry_signature(
            registry_bytes, signature, key_id, verifier
        )
        registry_hash = hashlib.sha256(registry_bytes).hexdigest()
        eligible = _release_eligible(wire, registry_hash, registry_manifest)
        return construct_registry(
            canonical_json=registry_bytes,
            registry_hash=registry_hash,
            signature=signature_text,
            key_id=key_text,
            wire=wire,
            slots=slots,
            release_eligible=eligible,
        )

    return load_signed_feature_registry


load_signed_feature_registry = _make_registry_loader(_construct_signed_registry)
del _make_registry_loader, _construct_signed_registry


def _make_evidence_type() -> type[object]:
    fields = (
        "formal_fact_id", "source_snapshot_id", "source_content_sha256",
        "source_refresh_generation", "source_field", "raw_value_sha256",
        "published_at_utc", "published_precision", "effective_at_utc", "mapping_version",
    )
    records: dict[int, tuple[weakref.ReferenceType[object], tuple[object, ...]]] = {}

    def forget(identity: int) -> None:
        records.pop(identity, None)

    def validate(ref: object) -> tuple[object, ...]:
        if type(ref) is not FormalEvidenceRef:
            raise ValueError("formal evidence must have exact type")
        try:
            values = tuple(getattr(ref, field) for field in fields)
        except AttributeError as error:
            raise ValueError("formal evidence is incomplete") from error
        if any(type(value) is not str for value in values):
            raise ValueError("formal evidence fields must be exact strings")
        _require_hash(values[0], "evidence formal_fact_id")
        _require_uuid(values[1], "evidence source_snapshot_id")
        _require_hash(values[2], "evidence source_content_sha256")
        _require_text(values[3], "evidence source_refresh_generation")
        _require_text(values[4], "evidence source_field")
        _require_hash(values[5], "evidence raw_value_sha256")
        published = _require_utc(values[6], "evidence published_at_utc")
        if values[7] not in {"timestamp", "date_only"}:
            raise ValueError("evidence published_precision is invalid")
        effective = _require_utc(values[8], "evidence effective_at_utc")
        if values[7] == "timestamp" and effective != published:
            raise ValueError("timestamp evidence effective time must equal publication")
        if values[7] == "date_only" and datetime.fromisoformat(effective) <= datetime.fromisoformat(published):
            raise ValueError("date-only evidence effective time must follow publication")
        _require_text(values[9], "evidence mapping_version", identifier=True)
        return values

    def remember(ref: object) -> None:
        values = validate(ref)
        identity = id(ref)
        records[identity] = (
            weakref.ref(ref, lambda _reference, identity=identity: forget(identity)), values
        )

    def require(ref: object) -> tuple[object, ...]:
        record = records.get(id(ref))
        current = validate(ref)
        if record is None or record[0]() is not ref:
            raise ValueError("formal evidence was not safely constructed or was mutated")
        if any(type(left) is not type(right) or left != right for left, right in zip(current, record[1])):
            raise ValueError("formal evidence was not safely constructed or was mutated")
        return current

    @dataclass(frozen=True, slots=True, weakref_slot=True)
    class FormalEvidenceRef:
        formal_fact_id: str
        source_snapshot_id: str
        source_content_sha256: str
        source_refresh_generation: str
        source_field: str
        raw_value_sha256: str
        published_at_utc: str
        published_precision: Literal["timestamp", "date_only"]
        effective_at_utc: str
        mapping_version: str

        def __post_init__(self) -> None:
            remember(self)

        @classmethod
        def from_formal_fact(cls, fact: FormalFinancialFact) -> "FormalEvidenceRef":
            if cls is not FormalEvidenceRef or type(fact) is not FormalFinancialFact:
                raise ValueError("formal evidence requires an exact FormalFinancialFact")
            values = fact.to_dict()
            return cls(
                formal_fact_id=values["id"],
                source_snapshot_id=values["source_snapshot_id"],
                source_content_sha256=values["source_content_sha256"],
                source_refresh_generation=values["source_refresh_generation"],
                source_field=values["source_field"],
                raw_value_sha256=values["raw_value_sha256"],
                published_at_utc=values["published_at_utc"],
                published_precision=values["published_precision"],
                effective_at_utc=values["effective_at_utc"],
                mapping_version=values["mapping_version"],
            )

        @classmethod
        def from_dict(cls, value: dict[str, object]) -> "FormalEvidenceRef":
            if cls is not FormalEvidenceRef:
                raise ValueError("FormalEvidenceRef must have exact type")
            wire = _require_exact_keys(value, _EVIDENCE_KEYS, "formal evidence")
            return cls(**wire)

        def to_dict(self) -> dict[str, object]:
            return dict(zip(fields, require(self), strict=True))

    return FormalEvidenceRef


FormalEvidenceRef = _make_evidence_type()
del _make_evidence_type


def _make_feature_value_type() -> type[object]:
    records: dict[int, tuple[weakref.ReferenceType[object], tuple[object, ...]]] = {}

    def forget(identity: int) -> None:
        records.pop(identity, None)

    def validate(item: object) -> tuple[object, ...]:
        if type(item) is not FormalFeatureValue:
            raise ValueError("formal feature value must have exact type")
        slot_id = _require_text(item.slot_id, "feature value slot_id", identifier=True)
        if type(item.unit) is not str or item.unit not in _UNITS:
            raise ValueError("feature value unit is invalid")
        formula_version = _require_text(
            item.formula_version, "feature value formula_version", identifier=True
        )
        if type(item.status) is not str or item.status not in {"derived", *_MISSING_STATUSES}:
            raise ValueError("feature value status is invalid")
        if type(item.evidence) is not tuple:
            raise ValueError("feature value evidence must be an immutable tuple")
        evidence_bytes: list[bytes] = []
        evidence_ids: list[str] = []
        for ref in item.evidence:
            if type(ref) is not FormalEvidenceRef:
                raise ValueError("feature value evidence contains an invalid reference")
            wire = ref.to_dict()
            evidence_bytes.append(_canonical_json_bytes(wire))
            evidence_ids.append(ref.formal_fact_id)
        if evidence_ids != sorted(set(evidence_ids)):
            raise ValueError("feature value evidence must be sorted and unique")
        if item.status == "derived":
            if type(item.value) is not float or not math.isfinite(item.value):
                raise ValueError("derived feature value must be a finite float")
            if not evidence_ids or item.missing_reason is not None:
                raise ValueError("derived feature value requires evidence and no missing reason")
        else:
            if item.value is not None or evidence_ids:
                raise ValueError("non-derived feature value must have null value and empty evidence")
            _require_text(item.missing_reason, "feature value missing_reason")
        value_fingerprint = (
            ("float", struct.pack(">d", item.value)) if type(item.value) is float else ("none", None)
        )
        return (
            slot_id,
            value_fingerprint,
            item.unit,
            item.status,
            formula_version,
            item.evidence,
            tuple(evidence_bytes),
            item.missing_reason,
        )

    def remember(item: object) -> None:
        sealed = validate(item)
        identity = id(item)
        records[identity] = (
            weakref.ref(item, lambda _reference, identity=identity: forget(identity)), sealed
        )

    def require(item: object) -> tuple[object, ...]:
        record = records.get(id(item))
        current = validate(item)
        if record is None or record[0]() is not item:
            raise ValueError("formal feature value was not safely constructed or was mutated")
        sealed = record[1]
        if (
            current[:5] != sealed[:5]
            or current[5] is not sealed[5]
            or current[6:] != sealed[6:]
        ):
            raise ValueError("formal feature value was not safely constructed or was mutated")
        return current

    @dataclass(frozen=True, slots=True, weakref_slot=True)
    class FormalFeatureValue:
        slot_id: str
        value: float | None
        unit: str
        status: Literal["derived", "missing", "blocked", "not_applicable"]
        formula_version: str
        evidence: tuple[FormalEvidenceRef, ...]
        missing_reason: str | None

        def __post_init__(self) -> None:
            if type(self.value) is bool:
                raise ValueError("feature value must be finite numeric or null")
            if type(self.value) is int:
                try:
                    normalized = float(self.value)
                except OverflowError as error:
                    raise ValueError("feature value must be finite") from error
                object.__setattr__(self, "value", normalized)
            if type(self.value) is float:
                if not math.isfinite(self.value):
                    raise ValueError("feature value must be finite")
                if self.value == 0.0:
                    object.__setattr__(self, "value", 0.0)
            remember(self)

        @classmethod
        def from_dict(cls, value: dict[str, object]) -> "FormalFeatureValue":
            if cls is not FormalFeatureValue:
                raise ValueError("FormalFeatureValue must have exact type")
            wire = _require_exact_keys(value, _VALUE_KEYS, "formal feature value")
            raw_evidence = wire["evidence"]
            if type(raw_evidence) is not list:
                raise ValueError("formal feature value evidence must be a JSON array")
            item = cls(
                slot_id=wire["slot_id"],
                value=wire["value"],
                unit=wire["unit"],
                status=wire["status"],
                formula_version=wire["formula_version"],
                evidence=tuple(FormalEvidenceRef.from_dict(ref) for ref in raw_evidence),
                missing_reason=wire["missing_reason"],
            )
            if _canonical_json_bytes(item.to_dict()) != _canonical_json_bytes(wire):
                raise ValueError("formal feature value wire is not canonical")
            return item

        def to_dict(self) -> dict[str, object]:
            sealed = require(self)
            return {
                "slot_id": sealed[0],
                "value": self.value,
                "unit": sealed[2],
                "status": sealed[3],
                "formula_version": sealed[4],
                "evidence": [ref.to_dict() for ref in self.evidence],
                "missing_reason": sealed[7],
            }

    return FormalFeatureValue


FormalFeatureValue = _make_feature_value_type()
del _make_feature_value_type


def _make_bundle_type() -> type[object]:
    records: dict[int, tuple[weakref.ReferenceType[object], tuple[object, ...]]] = {}

    def forget(identity: int) -> None:
        records.pop(identity, None)

    def validate(bundle: object) -> tuple[object, ...]:
        if type(bundle) is not FormalFeatureBundle:
            raise ValueError("formal feature bundle must have exact type")
        if type(bundle.schema_version) is not int or bundle.schema_version != 1:
            raise ValueError("formal feature bundle schema_version must be exact integer 1")
        contract_version = _require_text(
            bundle.contract_version, "feature bundle contract_version", identifier=True
        )
        if type(bundle.security_id) is not str or canonical_security_id(bundle.security_id) != bundle.security_id:
            raise ValueError("feature bundle security_id must be canonical")
        as_of_utc = _require_utc(bundle.as_of_utc, "feature bundle as_of_utc")
        if type(bundle.template_id) is not str or bundle.template_id not in _TEMPLATES:
            raise ValueError("feature bundle template_id is invalid")
        registry_manifest_hash = _require_hash(
            bundle.registry_manifest_hash, "feature bundle registry_manifest_hash"
        )
        feature_registry_hash = _require_hash(
            bundle.feature_registry_hash, "feature bundle feature_registry_hash"
        )
        input_hash = _require_hash(bundle.input_hash, "feature bundle input_hash")
        if type(bundle.values) is not tuple:
            raise ValueError("feature bundle values must be an immutable tuple")
        value_bytes: list[bytes] = []
        slot_ids: list[str] = []
        for item in bundle.values:
            if type(item) is not FormalFeatureValue:
                raise ValueError("feature bundle contains an invalid value")
            value_bytes.append(_canonical_json_bytes(item.to_dict()))
            slot_ids.append(item.slot_id)
        if slot_ids != sorted(set(slot_ids)):
            raise ValueError("feature bundle values must be sorted and unique by slot_id")
        if type(bundle.history_endpoints) is not tuple:
            raise ValueError("feature bundle history_endpoints must be an immutable tuple")
        endpoints = tuple(_require_date(item, "feature history endpoint") for item in bundle.history_endpoints)
        if endpoints != tuple(sorted(set(endpoints))):
            raise ValueError("feature history endpoints must be sorted and unique")
        if type(bundle.comparable_quarter_keys) is not tuple:
            raise ValueError("feature comparable quarter keys must be an immutable tuple")
        quarter_keys = bundle.comparable_quarter_keys
        if any(type(item) is not str or _QUARTER.fullmatch(item) is None for item in quarter_keys):
            raise ValueError("feature comparable quarter key is invalid")
        if quarter_keys != tuple(sorted(set(quarter_keys))):
            raise ValueError("feature comparable quarter keys must be sorted and unique")
        if type(bundle.blockers) is not tuple:
            raise ValueError("feature bundle blockers must be an immutable tuple")
        blockers = tuple(_require_text(item, "feature blocker") for item in bundle.blockers)
        if blockers != tuple(sorted(set(blockers))):
            raise ValueError("feature blockers must be sorted and unique")
        return (
            bundle.schema_version,
            contract_version,
            bundle.security_id,
            as_of_utc,
            bundle.template_id,
            registry_manifest_hash,
            feature_registry_hash,
            input_hash,
            bundle.values,
            tuple(value_bytes),
            bundle.history_endpoints,
            endpoints,
            bundle.comparable_quarter_keys,
            bundle.blockers,
        )

    def remember(bundle: object) -> None:
        sealed = validate(bundle)
        identity = id(bundle)
        records[identity] = (
            weakref.ref(bundle, lambda _reference, identity=identity: forget(identity)), sealed
        )

    def require(bundle: object) -> tuple[object, ...]:
        record = records.get(id(bundle))
        current = validate(bundle)
        if record is None or record[0]() is not bundle:
            raise ValueError("formal feature bundle was not safely constructed or was mutated")
        sealed = record[1]
        if (
            current[:8] != sealed[:8]
            or current[8] is not sealed[8]
            or current[9] != sealed[9]
            or current[10] is not sealed[10]
            or current[11] != sealed[11]
            or current[12] is not sealed[12]
            or current[13] is not sealed[13]
        ):
            raise ValueError("formal feature bundle was not safely constructed or was mutated")
        return current

    @dataclass(frozen=True, slots=True, weakref_slot=True)
    class FormalFeatureBundle:
        schema_version: int
        contract_version: str
        security_id: str
        as_of_utc: str
        template_id: str
        registry_manifest_hash: str
        feature_registry_hash: str
        input_hash: str
        values: tuple[FormalFeatureValue, ...]
        history_endpoints: tuple[str, ...]
        comparable_quarter_keys: tuple[str, ...]
        blockers: tuple[str, ...]

        def __post_init__(self) -> None:
            remember(self)

        @classmethod
        def from_dict(cls, value: dict[str, object]) -> "FormalFeatureBundle":
            if cls is not FormalFeatureBundle:
                raise ValueError("FormalFeatureBundle must have exact type")
            wire = _require_exact_keys(value, _BUNDLE_KEYS, "formal feature bundle")
            if type(wire["values"]) is not list:
                raise ValueError("feature bundle values must be a JSON array")
            for field in ("history_endpoints", "comparable_quarter_keys", "blockers"):
                if type(wire[field]) is not list:
                    raise ValueError(f"feature bundle {field} must be a JSON array")
            bundle = cls(
                schema_version=wire["schema_version"],
                contract_version=wire["contract_version"],
                security_id=wire["security_id"],
                as_of_utc=wire["as_of_utc"],
                template_id=wire["template_id"],
                registry_manifest_hash=wire["registry_manifest_hash"],
                feature_registry_hash=wire["feature_registry_hash"],
                input_hash=wire["input_hash"],
                values=tuple(FormalFeatureValue.from_dict(item) for item in wire["values"]),
                history_endpoints=tuple(wire["history_endpoints"]),
                comparable_quarter_keys=tuple(wire["comparable_quarter_keys"]),
                blockers=tuple(wire["blockers"]),
            )
            if _canonical_json_bytes(bundle.to_dict()) != _canonical_json_bytes(wire):
                raise ValueError("formal feature bundle wire is not canonical")
            return bundle

        def to_dict(self) -> dict[str, object]:
            sealed = require(self)
            return {
                "schema_version": sealed[0],
                "contract_version": sealed[1],
                "security_id": sealed[2],
                "as_of_utc": sealed[3],
                "template_id": sealed[4],
                "registry_manifest_hash": sealed[5],
                "feature_registry_hash": sealed[6],
                "input_hash": sealed[7],
                "values": [item.to_dict() for item in self.values],
                "history_endpoints": list(self.history_endpoints),
                "comparable_quarter_keys": list(self.comparable_quarter_keys),
                "blockers": list(self.blockers),
            }

        def canonical_bytes(self) -> bytes:
            return _canonical_json_bytes(self.to_dict())

        def bundle_hash(self) -> str:
            return hashlib.sha256(self.canonical_bytes()).hexdigest()

    return FormalFeatureBundle


FormalFeatureBundle = _make_bundle_type()
del _make_bundle_type


__all__ = [
    "FormulaNode",
    "FormalFeatureSlot",
    "FormalEvidenceRef",
    "FormalFeatureValue",
    "FormalFeatureBundle",
    "SignedFormalFeatureRegistry",
    "load_signed_feature_registry",
]
