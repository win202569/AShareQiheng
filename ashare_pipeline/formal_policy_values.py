"""Non-authoritative policy values and the explicit V6 Decimal bridge."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
)
import hashlib
import json
import math
import re


_FIELDS = frozenset(("state", "value", "value_type", "unit", "evidence_hashes", "pending"))
_PENDING_FIELDS = frozenset(("origin", "code", "rule_id", "evidence_hashes"))
_STATES = frozenset(("value", "missing", "domain_conflict"))
_VALUE_TYPES = frozenset((
    "decimal", "bool", "enum", "event_record", "calendar_record", "market_window",
))
_COMPOUND_TYPES = frozenset(("event_record", "calendar_record", "market_window"))
_RUNTIME_REASONS = frozenset((
    "applicability_unresolved",
    "current_receipt_absent",
    "financial_input_missing",
    "financial_domain_conflict",
    "unsupported_unit",
    "invalid_denominator",
    "visibility_unproven",
    "state_entry_missing",
    "calendar_coverage_missing",
    "market_coverage_missing",
    "market_price_missing",
    "market_domain_conflict",
    "market_evidence_missing",
))
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")


class PolicyPreconditionError(ValueError):
    """A trusted policy prerequisite was absent or invalid."""


class PolicyIntegrityError(ValueError):
    """Policy evidence or its verified identity changed unexpectedly."""


def decimal_context() -> Context:
    """Return the isolated context for new policy arithmetic."""
    return Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )


def bridge_v6(value: float | int) -> Decimal:
    """Preserve a finite V6 float/int's existing string identity as Decimal."""
    if type(value) is int:
        return Decimal(str(value))
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("finite V6 numeric value required")
    return Decimal(str(value))


def canonical_bytes(wire: dict) -> bytes:
    if type(wire) is not dict:
        raise ValueError("policy wire must be an exact object")
    return json.dumps(
        wire,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(wire: dict) -> str:
    return hashlib.sha256(canonical_bytes(wire)).hexdigest()


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical identifier")
    return value


def _controlled_text(value: object, label: str) -> str:
    if (type(value) is not str or not value or value.strip() != value
            or any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value)):
        raise ValueError(f"{label} must be nonempty control-free text")
    return value


def _unit(value: object, value_type: str) -> str | None:
    if value_type == "decimal":
        return _identifier(value, "decimal unit")
    if value is not None:
        raise ValueError("only decimal values carry a unit")
    return None


def _hashes(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise ValueError(f"{label} must be an array")
    copied = []
    for item in value:
        if type(item) is not str or _SHA256.fullmatch(item) is None:
            raise ValueError(f"{label} must contain canonical SHA-256 values")
        copied.append(item)
    return tuple(sorted(set(copied)))


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("finite decimal required")
    if value.is_zero():
        return "0"
    fixed = format(value, "f")
    if "." in fixed:
        fixed = fixed.rstrip("0").rstrip(".")
    return fixed


def _decimal(value: object) -> Decimal:
    if type(value) is not str:
        raise ValueError("decimal wire value must be text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid decimal wire value") from error
    if _decimal_text(parsed) != value:
        raise ValueError("decimal wire value is not canonical")
    return parsed


@dataclass(frozen=True, slots=True)
class _Pending:
    origin: str
    code: str
    rule_id: str | None
    evidence_hashes: tuple[str, ...]

    @classmethod
    def from_dict(cls, wire: object) -> "_Pending":
        if type(wire) is not dict or set(wire) != _PENDING_FIELDS:
            raise ValueError("pending reason has unknown or missing fields")
        origin = wire["origin"]
        code = wire["code"]
        rule_id = wire["rule_id"]
        if origin == "runtime":
            if type(code) is not str or code not in _RUNTIME_REASONS:
                raise ValueError("unknown runtime pending reason")
            if rule_id is not None:
                raise ValueError("runtime pending reasons cannot claim a signed rule")
        elif origin == "signed_policy":
            code = _controlled_text(code, "signed policy reason")
            rule_id = _controlled_text(rule_id, "signed policy rule")
        else:
            raise ValueError("unknown pending reason origin")
        return cls(origin, code, rule_id, _hashes(wire["evidence_hashes"], "pending evidence_hashes"))

    def to_dict(self) -> dict:
        return {
            "origin": self.origin,
            "code": self.code,
            "rule_id": self.rule_id,
            "evidence_hashes": list(self.evidence_hashes),
        }


@dataclass(frozen=True, slots=True)
class PolicyValue:
    """Detached scalar value or typed evidence-shortfall record."""

    state: str
    value: Decimal | bool | str | None
    value_type: str
    unit: str | None
    evidence_hashes: tuple[str, ...]
    _pending: tuple[_Pending, ...]

    @classmethod
    def from_dict(cls, wire: object) -> "PolicyValue":
        if type(wire) is not dict or set(wire) != _FIELDS:
            raise ValueError("policy value has unknown or missing fields")
        state = wire["state"]
        value_type = wire["value_type"]
        if type(state) is not str or state not in _STATES:
            raise ValueError("unknown policy value state")
        if type(value_type) is not str or value_type not in _VALUE_TYPES:
            raise ValueError("unknown policy value type")
        unit = _unit(wire["unit"], value_type)
        if type(wire["pending"]) is not list:
            raise ValueError("pending must be an array")
        pending = tuple(_Pending.from_dict(item) for item in wire["pending"])

        if state == "value":
            if pending:
                raise ValueError("a present policy value cannot be pending")
            if value_type in _COMPOUND_TYPES:
                raise ValueError("compound policy values require their closed producer validator")
            if value_type == "decimal":
                value: Decimal | bool | str | None = _decimal(wire["value"])
            elif value_type == "bool":
                if type(wire["value"]) is not bool:
                    raise ValueError("bool policy value must be exact bool")
                value = wire["value"]
            else:
                value = _identifier(wire["value"], "enum policy value")
        else:
            if wire["value"] is not None:
                raise ValueError("missing or conflicting policy value must be null")
            if not pending:
                raise ValueError("missing or conflicting policy value requires a pending reason")
            value = None

        return cls(
            state=state,
            value=value,
            value_type=value_type,
            unit=unit,
            evidence_hashes=_hashes(wire["evidence_hashes"], "evidence_hashes"),
            _pending=pending,
        )

    def to_dict(self) -> dict:
        value: object = self.value
        if self.value_type == "decimal" and value is not None:
            value = _decimal_text(value)
        return {
            "state": self.state,
            "value": value,
            "value_type": self.value_type,
            "unit": self.unit,
            "evidence_hashes": list(self.evidence_hashes),
            "pending": [item.to_dict() for item in self._pending],
        }


__all__ = [
    "PolicyIntegrityError",
    "PolicyPreconditionError",
    "PolicyValue",
    "bridge_v6",
    "canonical_bytes",
    "decimal_context",
    "digest",
]
