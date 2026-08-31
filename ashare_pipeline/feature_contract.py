"""Immutable, auditable inputs for the seven-dimension feature layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping
from types import MappingProxyType

CONTRACT_VERSION = "feature-contract-v1"
DIMENSIONS = ("G", "V", "M", "EQ", "FS", "CA", "T")
FEATURE_VALUE_STATES = frozenset({"observed", "derived", "missing", "not_applicable", "blocked"})
DIMENSION_INPUT_STATES = frozenset({"input_ready", "partial", "missing", "not_applicable", "blocked"})
FINANCIAL_STATUSES = frozenset({"partial", "financial_ready", "blocked"})
UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECURITY_ID = re.compile(r"^(?:SH|SZ)\d{6}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _require_exact_keys(
    value: object, expected: frozenset[str], field: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{field} must contain exactly the contract keys")
    return value


def _require_nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _require_iso_date(value: object, field: str) -> str:
    if not isinstance(value, str) or _ISO_DATE.fullmatch(value) is None:
        raise ValueError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be a canonical ISO date")
    return value


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_aware_utc(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
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
            _require_nonempty_text(getattr(self, name), name)
        _require_sha256(self.raw_row_hash, "raw_row_hash")
        object.__setattr__(self, "announced_at_utc", require_aware_utc(self.announced_at_utc, "announced_at_utc"))
        object.__setattr__(self, "effective_at_utc", require_aware_utc(self.effective_at_utc, "effective_at_utc"))

    def to_dict(self) -> dict[str, Any]:
        return {"financial_fact_id": self.financial_fact_id, "source_snapshot_id": self.source_snapshot_id,
                "source_field": self.source_field, "raw_row_hash": self.raw_row_hash,
                "announced_at_utc": self.announced_at_utc, "effective_at_utc": self.effective_at_utc}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceRef":
        data = _require_exact_keys(
            value,
            frozenset(
                {
                    "financial_fact_id",
                    "source_snapshot_id",
                    "source_field",
                    "raw_row_hash",
                    "announced_at_utc",
                    "effective_at_utc",
                }
            ),
            "evidence",
        )
        return cls(**dict(data))


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
        if not isinstance(self.unit, str) or self.unit not in UNITS:
            raise ValueError(f"unit must be one of {sorted(UNITS)}")
        if not isinstance(self.status, str) or self.status not in FEATURE_VALUE_STATES:
            raise ValueError("invalid feature value status")
        _require_nonempty_text(self.key, "feature key")
        _require_nonempty_text(self.period_key, "period_key")
        _require_nonempty_text(self.formula_version, "formula_version")
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
        data = dict(
            _require_exact_keys(
                value,
                frozenset(
                    {
                        "key",
                        "value",
                        "unit",
                        "period_key",
                        "status",
                        "formula_version",
                        "evidence",
                        "missing_reason",
                    }
                ),
                "feature value",
            )
        )
        if not isinstance(data["evidence"], (list, tuple)):
            raise ValueError("feature evidence must be a list")
        data["evidence"] = tuple(EvidenceRef.from_dict(x) for x in data["evidence"])
        return cls(**data)


@dataclass(frozen=True)
class DimensionInput:
    status: str
    values: tuple[FeatureValue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or self.status not in DIMENSION_INPUT_STATES:
            raise ValueError("invalid dimension input status")
        values = tuple(self.values)
        if any(not isinstance(item, FeatureValue) for item in values):
            raise ValueError("dimension values must contain FeatureValue values")
        keys = [(item.key, item.period_key) for item in values]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate feature key and period")
        states = {item.status for item in values}
        if self.status == "missing" and states - {"missing", "not_applicable"}:
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
        data = _require_exact_keys(
            value, frozenset({"status", "values"}), "dimension input"
        )
        if not isinstance(data["values"], (list, tuple)):
            raise ValueError("dimension values must be a list")
        return cls(
            data["status"],
            tuple(FeatureValue.from_dict(x) for x in data["values"]),
        )


@dataclass(frozen=True)
class IndustryContext:
    source: str
    code: str | None
    name: str
    template_id: str
    template_version: str
    formal_industry_ready: bool

    def __post_init__(self) -> None:
        from .industry_templates import TEMPLATE_VERSION, TEMPLATES, resolve_template

        if self.source != "eastmoney-provisional":
            raise ValueError("industry source must be eastmoney-provisional")
        if self.code is not None and (
            not isinstance(self.code, str) or not self.code
        ):
            raise ValueError("industry code must be a non-empty string or null")
        _require_nonempty_text(self.name, "industry name")
        if self.template_id not in TEMPLATES:
            raise ValueError("industry template_id is not registered")
        if resolve_template(self.name).template_id != self.template_id:
            raise ValueError("industry name does not match its registered template")
        if self.template_version != TEMPLATE_VERSION:
            raise ValueError("industry template_version is unsupported")
        if self.formal_industry_ready is not False:
            raise ValueError("formal industry mapping is not ready")

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "code": self.code, "name": self.name, "template_id": self.template_id,
                "template_version": self.template_version, "formal_industry_ready": self.formal_industry_ready}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IndustryContext":
        data = _require_exact_keys(
            value,
            frozenset(
                {
                    "source",
                    "code",
                    "name",
                    "template_id",
                    "template_version",
                    "formal_industry_ready",
                }
            ),
            "industry",
        )
        return cls(**dict(data))


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
        if (
            not isinstance(self.date_precision_counts, Mapping)
            or set(self.date_precision_counts) != {"timestamp", "date_only"}
        ):
            raise ValueError(
                "date_precision_counts must contain timestamp and date_only"
            )
        counts = dict(self.date_precision_counts)
        if any(
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for count in counts.values()
        ):
            raise ValueError("date precision counts must be non-negative integers")
        if (
            isinstance(self.history_years_present, bool)
            or not isinstance(self.history_years_present, int)
            or self.history_years_present < 0
        ):
            raise ValueError("history_years_present must be a non-negative integer")
        if not isinstance(self.mapping_consistent, bool):
            raise ValueError("mapping_consistent must be boolean")
        object.__setattr__(self, "data_completeness_ratio", ratio)
        object.__setattr__(self, "date_precision_counts", MappingProxyType(counts))

    def to_dict(self) -> dict[str, Any]:
        return {"data_completeness_ratio": self.data_completeness_ratio,
                "date_precision_counts": dict(sorted(self.date_precision_counts.items())),
                "history_years_present": self.history_years_present, "mapping_consistent": self.mapping_consistent,
                "formal_confidence": None}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ConfidenceInputs":
        data = _require_exact_keys(
            value,
            frozenset(
                {
                    "data_completeness_ratio",
                    "date_precision_counts",
                    "history_years_present",
                    "mapping_consistent",
                    "formal_confidence",
                }
            ),
            "confidence inputs",
        )
        return cls(**dict(data))


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
        if not isinstance(self.dimension_inputs, Mapping):
            raise ValueError("dimension_inputs must be a mapping")
        object.__setattr__(self, "dimension_inputs", MappingProxyType(dict(self.dimension_inputs)))
        if not isinstance(self.blockers, (list, tuple)):
            raise ValueError("blockers must be a list")
        object.__setattr__(self, "blockers", tuple(self.blockers))
        self.validate()

    def validate(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != 1
            or self.contract_version != CONTRACT_VERSION
        ):
            raise ValueError("unsupported feature contract")
        if not isinstance(self.security_id, str) or _SECURITY_ID.fullmatch(self.security_id) is None:
            raise ValueError("security_id must use SH/SZ plus six digits")
        _require_iso_date(self.report_period, "report_period")
        _require_sha256(self.candidate_set_hash, "candidate_set_hash")
        _require_sha256(self.input_hash, "input_hash")
        if not isinstance(self.industry, IndustryContext):
            raise ValueError("industry must be IndustryContext")
        if not isinstance(self.confidence_inputs, ConfidenceInputs):
            raise ValueError("confidence_inputs must be ConfidenceInputs")
        if set(self.dimension_inputs) != set(DIMENSIONS):
            raise ValueError("dimension keys must be exactly the seven contract dimensions")
        if not isinstance(self.financial_status, str) or self.financial_status not in FINANCIAL_STATUSES:
            raise ValueError("invalid financial status")
        coverage = require_feature_number(self.financial_coverage, allow_none=False)
        if not 0 <= coverage <= 1:
            raise ValueError("financial_coverage must be between 0 and 1")
        object.__setattr__(self, "financial_coverage", coverage)
        object.__setattr__(self, "as_of_utc", require_aware_utc(self.as_of_utc, "as_of_utc"))
        if self.confidence_inputs.data_completeness_ratio != coverage:
            raise ValueError("financial coverage must match confidence completeness")
        if (
            self.confidence_inputs.formal_confidence is not None
            or self.is_formal_score_ready is not False
        ):
            raise ValueError("formal score must not be ready in the feature contract")
        if any(not isinstance(v, DimensionInput) for v in self.dimension_inputs.values()):
            raise ValueError("dimension inputs must be DimensionInput values")
        if any(
            not isinstance(blocker, str) or not blocker
            for blocker in self.blockers
        ):
            raise ValueError("blockers must contain non-empty strings")
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("blockers must not contain duplicates")
        financial_blockers = set(self.blockers) - {
            "formal_industry_mapping_missing"
        }
        if self.financial_status == "financial_ready":
            if (
                coverage != 1.0
                or financial_blockers
                or self.industry.template_id == "unclassified"
            ):
                raise ValueError(
                    "financial_ready requires full coverage and no financial blocker"
                )

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
        data = dict(
            _require_exact_keys(
                value,
                frozenset(
                    {
                        "schema_version",
                        "contract_version",
                        "security_id",
                        "report_period",
                        "as_of_utc",
                        "candidate_set_hash",
                        "industry",
                        "input_hash",
                        "financial_status",
                        "financial_coverage",
                        "confidence_inputs",
                        "dimension_inputs",
                        "blockers",
                        "is_formal_score_ready",
                    }
                ),
                "feature bundle",
            )
        )
        data["industry"] = IndustryContext.from_dict(data["industry"])
        data["confidence_inputs"] = ConfidenceInputs.from_dict(data["confidence_inputs"])
        if not isinstance(data["dimension_inputs"], Mapping):
            raise ValueError("dimension_inputs must be a mapping")
        data["dimension_inputs"] = {
            k: DimensionInput.from_dict(v)
            for k, v in data["dimension_inputs"].items()
        }
        if not isinstance(data["blockers"], (list, tuple)):
            raise ValueError("blockers must be a list")
        data["blockers"] = tuple(data["blockers"])
        return cls(**data)
