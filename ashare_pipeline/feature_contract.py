"""Immutable, auditable inputs for the seven-dimension feature layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping
from types import MappingProxyType

CONTRACT_VERSION = "feature-contract-v1"
DIMENSIONS = ("G", "V", "M", "EQ", "FS", "CA", "T")
FEATURE_VALUE_STATES = frozenset({"observed", "derived", "missing", "not_applicable", "blocked"})
DIMENSION_INPUT_STATES = frozenset({"input_ready", "partial", "missing", "not_applicable", "blocked"})
FINANCIAL_STATUSES = frozenset({"partial", "financial_ready", "blocked"})
UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_aware_utc(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc).isoformat()


def require_feature_number(value: object, *, allow_none: bool) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("feature value must be a finite number or allowed null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("feature value must be finite")
    return result


@dataclass(frozen=True)
class EvidenceRef:
    financial_fact_id: str
    source_snapshot_id: str
    source_field: str
    raw_row_hash: str
    announced_at_utc: str
    effective_at_utc: str

    def __post_init__(self) -> None:
        for name in ("financial_fact_id", "source_snapshot_id", "source_field", "raw_row_hash"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} is required")
        if len(self.raw_row_hash) != 64 or any(c not in "0123456789abcdef" for c in self.raw_row_hash.lower()):
            raise ValueError("raw_row_hash must be a SHA-256 hex digest")
        object.__setattr__(self, "announced_at_utc", require_aware_utc(self.announced_at_utc, "announced_at_utc"))
        object.__setattr__(self, "effective_at_utc", require_aware_utc(self.effective_at_utc, "effective_at_utc"))

    def to_dict(self) -> dict[str, Any]:
        return {"financial_fact_id": self.financial_fact_id, "source_snapshot_id": self.source_snapshot_id,
                "source_field": self.source_field, "raw_row_hash": self.raw_row_hash,
                "announced_at_utc": self.announced_at_utc, "effective_at_utc": self.effective_at_utc}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceRef":
        return cls(**dict(value))


@dataclass(frozen=True)
class FeatureValue:
    key: str
    value: float | None
    unit: str
    period_key: str
    status: str
    formula_version: str
    evidence: tuple[EvidenceRef, ...] = ()
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if self.unit not in UNITS:
            raise ValueError(f"unit must be one of {sorted(UNITS)}")
        if self.status not in FEATURE_VALUE_STATES:
            raise ValueError("invalid feature value status")
        if not self.key or not self.period_key or not self.formula_version:
            raise ValueError("feature key, period_key and formula_version are required")
        evidence = tuple(self.evidence)
        if any(not isinstance(item, EvidenceRef) for item in evidence):
            raise ValueError("evidence must contain EvidenceRef values")
        object.__setattr__(self, "evidence", evidence)
        requires_value = self.status in {"observed", "derived"}
        normalized = require_feature_number(self.value, allow_none=not requires_value)
        if requires_value:
            if not evidence:
                raise ValueError("observed/derived feature value requires evidence")
            if self.missing_reason is not None:
                raise ValueError("observed/derived feature value cannot have missing_reason")
        else:
            if normalized is not None or not isinstance(self.missing_reason, str) or not self.missing_reason.strip():
                raise ValueError("missing/not_applicable/blocked feature requires null and a reason")
            if evidence:
                raise ValueError("missing/not_applicable/blocked feature cannot have evidence")
        object.__setattr__(self, "value", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "unit": self.unit, "period_key": self.period_key,
                "status": self.status, "formula_version": self.formula_version,
                "evidence": [x.to_dict() for x in sorted(self.evidence, key=lambda x: tuple(x.to_dict().values()))],
                "missing_reason": self.missing_reason}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FeatureValue":
        data = dict(value)
        data["evidence"] = tuple(EvidenceRef.from_dict(x) for x in data.get("evidence", ()))
        return cls(**data)


@dataclass(frozen=True)
class DimensionInput:
    status: str
    values: tuple[FeatureValue, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in DIMENSION_INPUT_STATES:
            raise ValueError("invalid dimension input status")
        values = tuple(self.values)
        if any(not isinstance(item, FeatureValue) for item in values):
            raise ValueError("dimension values must contain FeatureValue values")
        keys = [(item.key, item.period_key) for item in values]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate feature key and period")
        states = {item.status for item in values}
        if self.status == "missing" and states - {"missing"}:
            raise ValueError("missing dimension cannot contain observed values")
        if self.status == "not_applicable" and states - {"not_applicable"}:
            raise ValueError("not_applicable dimension has inconsistent values")
        if self.status == "input_ready":
            if states & {"missing", "blocked"} or not states & {"observed", "derived"}:
                raise ValueError("input_ready dimension has incomplete values")
        object.__setattr__(self, "values", values)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "values": [x.to_dict() for x in sorted(self.values, key=lambda x: (x.key, x.period_key))]}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DimensionInput":
        return cls(value["status"], tuple(FeatureValue.from_dict(x) for x in value.get("values", ())))


@dataclass(frozen=True)
class IndustryContext:
    source: str
    code: str | None
    name: str
    template_id: str
    template_version: str
    formal_industry_ready: bool

    def __post_init__(self) -> None:
        if self.formal_industry_ready:
            raise ValueError("formal industry mapping is not ready")

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "code": self.code, "name": self.name, "template_id": self.template_id,
                "template_version": self.template_version, "formal_industry_ready": self.formal_industry_ready}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IndustryContext":
        return cls(**dict(value))


@dataclass(frozen=True)
class ConfidenceInputs:
    data_completeness_ratio: float
    date_precision_counts: Mapping[str, int]
    history_years_present: int
    mapping_consistent: bool
    formal_confidence: float | None

    def __post_init__(self) -> None:
        ratio = require_feature_number(self.data_completeness_ratio, allow_none=False)
        if not 0 <= ratio <= 1:
            raise ValueError("data_completeness_ratio must be between 0 and 1")
        if self.formal_confidence is not None:
            raise ValueError("formal_confidence must be None")
        object.__setattr__(self, "data_completeness_ratio", ratio)
        object.__setattr__(self, "date_precision_counts", MappingProxyType(dict(self.date_precision_counts)))

    def to_dict(self) -> dict[str, Any]:
        return {"data_completeness_ratio": self.data_completeness_ratio,
                "date_precision_counts": dict(sorted(self.date_precision_counts.items())),
                "history_years_present": self.history_years_present, "mapping_consistent": self.mapping_consistent,
                "formal_confidence": None}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ConfidenceInputs":
        return cls(**dict(value))


@dataclass(frozen=True)
class FeatureBundle:
    schema_version: int
    contract_version: str
    security_id: str
    report_period: str
    as_of_utc: str
    candidate_set_hash: str
    industry: IndustryContext
    input_hash: str
    financial_status: str
    financial_coverage: float
    confidence_inputs: ConfidenceInputs
    dimension_inputs: Mapping[str, DimensionInput]
    blockers: tuple[str, ...]
    is_formal_score_ready: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension_inputs", MappingProxyType(dict(self.dimension_inputs)))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        self.validate()

    def validate(self) -> None:
        if self.contract_version != CONTRACT_VERSION or self.schema_version != 1:
            raise ValueError("unsupported feature contract")
        if set(self.dimension_inputs) != set(DIMENSIONS):
            raise ValueError("dimension keys must be exactly the seven contract dimensions")
        if self.financial_status not in FINANCIAL_STATUSES:
            raise ValueError("invalid financial status")
        coverage = require_feature_number(self.financial_coverage, allow_none=False)
        if not 0 <= coverage <= 1:
            raise ValueError("financial_coverage must be between 0 and 1")
        require_aware_utc(self.as_of_utc, "as_of_utc")
        if self.confidence_inputs.formal_confidence is not None or self.is_formal_score_ready:
            raise ValueError("formal score must not be ready in the feature contract")
        if any(not isinstance(v, DimensionInput) for v in self.dimension_inputs.values()):
            raise ValueError("dimension inputs must be DimensionInput values")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "contract_version": self.contract_version,
                "security_id": self.security_id, "report_period": self.report_period, "as_of_utc": require_aware_utc(self.as_of_utc, "as_of_utc"),
                "candidate_set_hash": self.candidate_set_hash, "industry": self.industry.to_dict(), "input_hash": self.input_hash,
                "financial_status": self.financial_status, "financial_coverage": self.financial_coverage,
                "confidence_inputs": self.confidence_inputs.to_dict(),
                "dimension_inputs": {key: self.dimension_inputs[key].to_dict() for key in DIMENSIONS},
                "blockers": sorted(self.blockers), "is_formal_score_ready": False}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    def bundle_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FeatureBundle":
        data = dict(value)
        data["industry"] = IndustryContext.from_dict(data["industry"])
        data["confidence_inputs"] = ConfidenceInputs.from_dict(data["confidence_inputs"])
        data["dimension_inputs"] = {k: DimensionInput.from_dict(v) for k, v in data["dimension_inputs"].items()}
        data["blockers"] = tuple(data.get("blockers", ()))
        return cls(**data)
