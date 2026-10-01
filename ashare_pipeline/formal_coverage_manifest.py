"""Fail-closed production coverage audit for the formal scoring run.

This module deliberately treats database row counts as observations only.  A
coverage row is verified only after its source/repository callback has accepted
the complete, hash-bound evidence record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import copy
import hashlib
import json
import pickle
import weakref
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence


COVERAGE_CLASSES = (
    "verified_complete", "verified_partial", "verified_no_coverage",
    "not_applicable_signed", "missing", "pending", "retryable_failed",
    "terminal_failed", "blocked_schema", "blocked_registry",
    "blocked_identity", "blocked_integrity", "blocked_temporal",
    "blocked_ambiguous", "blocked_dependency",
)
_COVERAGE_SET = frozenset(COVERAGE_CLASSES)
_SEALS: dict[int, tuple[weakref.ReferenceType[Any], bytes, type]] = {}
_AUDIT_ROW_FIELDS = (
    "required", "applicability_rule_hash", "source", "dataset",
    "request_fingerprint", "refresh_generation", "task_id", "collection_state",
    "selected_snapshot_id", "content_sha256", "manifest_sha256", "parser_id",
    "parser_version", "mapping_version", "published_at_utc", "effective_at_utc",
    "captured_at_utc", "source_updated_at_utc", "expected_units",
    "observed_units", "missing_units", "verification_state", "temporal_state",
    "coverage_class", "reason_codes", "evidence_hashes", "rechecked_at_utc",
)
_VERIFIED_LINEAGE_FIELDS = (
    "source", "dataset", "request_fingerprint", "selected_snapshot_id",
    "content_sha256", "manifest_sha256", "parser_id", "parser_version",
    "mapping_version", "published_at_utc", "effective_at_utc",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(k) for k in (
        "frozen_input_hash", "security_id", "domain", "selector_hash",
        "period_or_window", "exchange"))


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _official_contract_identity(contract: Any) -> dict[str, str] | None:
    """An unapproved or unidentified bundle is never an official authority."""
    if not isinstance(contract, Mapping) or contract.get("approved") is not True:
        return None
    if contract.get("purpose") != "official":
        return None
    fields = ("signing_identity", "root_manifest_hash")
    if any(type(contract.get(field)) is not str or not contract[field].strip()
           for field in fields):
        return None
    return {field: contract[field] for field in fields}


def _seal(obj: Any, payload: Mapping[str, Any]) -> None:
    raw = _canonical(payload)
    _SEALS[id(obj)] = (weakref.ref(obj, lambda _: _SEALS.pop(id(obj), None)),
                       raw, type(obj))


def _require(obj: Any) -> Mapping[str, Any]:
    item = _SEALS.get(id(obj))
    if item is None or item[0]() is not obj or item[2] is not type(obj):
        raise ValueError("coverage proof is not a genuine verified manifest")
    return json.loads(item[1])


@dataclass(frozen=True)
class CoverageRequirement:
    frozen_input_hash: str
    security_id: str
    domain: str
    selector_hash: str
    period_or_window: str
    exchange: str
    expected_units: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"frozen_input_hash": self.frozen_input_hash,
                "security_id": self.security_id, "domain": self.domain,
                "selector_hash": self.selector_hash,
                "period_or_window": self.period_or_window,
                "exchange": self.exchange,
                "expected_units": list(self.expected_units)}


class _SealedProofType(type):
    def __setattr__(cls, name: str, value: Any) -> None:
        raise TypeError("coverage proof methods cannot be replaced")

    def __delattr__(cls, name: str) -> None:
        raise TypeError("coverage proof methods cannot be removed")


class _Proof(metaclass=_SealedProofType):
    __slots__ = ("__weakref__",)

    def __init__(self, *_: Any, **__: Any) -> None:
        raise TypeError("coverage manifests must be minted by FormalCoverageAuditor")

    def _data(self) -> Mapping[str, Any]:
        return _require(self)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self._data()))

    @property
    def manifest_hash(self) -> str:
        return str(self._data()["manifest_hash"])

    @property
    def rows(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(copy.deepcopy(self._data()["rows"]))

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(self._data()["blockers"])

    @property
    def diagnostics(self) -> Mapping[str, Any]:
        return MappingProxyType(copy.deepcopy(self._data()["diagnostics"]))

    def require_verified(self) -> None:
        _require(self)

    def canonical_bytes(self) -> bytes:
        data = self._data()
        canonical = {k: v for k, v in data.items()
                     if k not in {"diagnostics", "manifest_hash"}}
        canonical["rows"] = [{k: v for k, v in row.items()
                              if k != "rechecked_at_utc"} for row in data["rows"]]
        return _canonical(canonical)

    def __copy__(self) -> Any:
        raise TypeError("coverage proofs cannot be copied")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("coverage proofs cannot be copied")

    def __reduce_ex__(self, protocol: int) -> Any:
        raise TypeError("coverage proofs cannot be reconstructed")

    def __getstate__(self) -> Any:
        raise TypeError("coverage proofs cannot be serialized")


class VerifiedCoverageManifest(_Proof):
    __slots__ = ()

    def require_preview_ready(self) -> None:
        data = self._data()
        if data["blockers"]:
            raise ValueError("coverage preview blocked: " + ",".join(data["blockers"]))

    def require_official_ready(self) -> None:
        data = self._data()
        if data["blockers"]:
            raise ValueError("official coverage blocked: " + ",".join(data["blockers"]))
        if not data["production_contract"]:
            raise ValueError("official coverage requires production contract")


class FormalCoverageAuditor:
    """Audit one frozen requirement universe and mint an authenticated manifest."""

    def __init__(self, *, freeze_at_utc: str = "2026-08-31T07:00:00+00:00",
                 production_contract: Any = None,
                 repository_validators: Mapping[str, Callable[..., Any]] | None = None,
                 validators: Mapping[str, Callable[..., Any]] | None = None) -> None:
        self.freeze_at_utc = freeze_at_utc
        self.production_contract = production_contract
        self.repository_validators = dict(repository_validators or validators or {})

    @staticmethod
    def revoke(manifest: VerifiedCoverageManifest) -> None:
        if type(manifest) is not VerifiedCoverageManifest:
            raise ValueError("coverage proof is not a genuine verified manifest")
        _require(manifest)
        _SEALS.pop(id(manifest), None)

    def audit(self, requirements: Sequence[CoverageRequirement | Mapping[str, Any]],
              records: Sequence[Mapping[str, Any]] | Mapping[Any, Mapping[str, Any]] = (),
              *, repository_validators: Mapping[str, Callable[..., Any]] | None = None,
              validators: Mapping[str, Callable[..., Any]] | None = None,
              production_contract: Any = None, registry: Mapping[str, Any] | None = None,
              db_diagnostics: Mapping[str, Any] | None = None,
              audit_at_utc: str | None = None,
              timing_diagnostics: Mapping[str, Any] | None = None) -> VerifiedCoverageManifest:
        reqs = [r.to_dict() if isinstance(r, CoverageRequirement) else dict(r)
                for r in requirements]
        if not reqs:
            raise ValueError("coverage requirements must be nonempty")
        keys = [_key(r) for r in reqs]
        if any(None in k for k in keys) or len(keys) != len(set(keys)):
            raise ValueError("coverage requirements must be unique and fully enumerated")
        if isinstance(records, Mapping):
            record_rows = list(records.values())
        else:
            record_rows = list(records)
        by_key: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        for row in record_rows:
            key = _key(row)
            if key in by_key:
                # Keep this visible as a member-level ambiguous proof failure.
                by_key[key] = {"coverage_class": "blocked_ambiguous",
                               "reason_codes": ["ambiguous_duplicate"]}
            else:
                by_key[key] = row
        callback_map = dict(self.repository_validators)
        callback_map.update(repository_validators or validators or {})
        registry_disapproved = registry is not None and registry.get("approved") is False
        rows: list[dict[str, Any]] = []
        blockers: set[str] = set()
        for req in reqs:
            key = _key(req)
            source = by_key.get(key)
            row = {field: None for field in _AUDIT_ROW_FIELDS}
            row.update(req)
            row["required"] = True
            reasons: list[str] = []
            identity_mismatch = any(
                tuple(k for i, k in enumerate(candidate_key) if i != 5) ==
                tuple(k for i, k in enumerate(key) if i != 5)
                for candidate_key in by_key if candidate_key != key
            )
            if source is None:
                cls = "blocked_identity" if identity_mismatch else "missing"
                reasons.append("exchange_identity_mismatch" if identity_mismatch else "absent_record")
            else:
                row.update({k: v for k, v in source.items() if k not in req})
                row["required"] = True
                cls = source.get("coverage_class")
                if cls not in _COVERAGE_SET:
                    cls = "blocked_integrity"; reasons.append("invalid_coverage_class")
                reasons.extend(source.get("reason_codes", ()))
                if source.get("table_missing"):
                    cls = "blocked_schema"; reasons.append("missing_table")
                if source.get("registry_purpose") not in (None, req.get("domain")):
                    cls = "blocked_registry"; reasons.append("registry_purpose_mismatch")
                if registry_disapproved:
                    cls = "blocked_registry"; reasons.append("registry_not_approved")
                if source.get("signature_ok") is False or source.get("hash_ok") is False:
                    cls = "blocked_integrity"; reasons.append("signature_or_hash_mismatch")
                if source.get("source_correction") or source.get("ambiguous_duplicate"):
                    cls = "blocked_ambiguous"; reasons.append("source_correction_or_duplicate")
                if cls == "verified_no_coverage" and not (
                    source.get("authenticated") and source.get("explicit_source_statement")):
                    cls = "blocked_integrity"; reasons.append("no_coverage_not_authenticated")
                if cls in {"verified_complete", "verified_partial", "verified_no_coverage"}:
                    if any(type(source.get(field)) is not str or not source[field].strip()
                           for field in _VERIFIED_LINEAGE_FIELDS):
                        cls = "blocked_integrity"; reasons.append("incomplete_verified_lineage")
                    elif source.get("verification_state") != "verified" or source.get("temporal_state") != "visible":
                        cls = "blocked_integrity"; reasons.append("unverified_source_state")
                    elif not isinstance(source.get("observed_units"), (list, tuple)):
                        cls = "blocked_integrity"; reasons.append("missing_observed_units")
                    elif cls == "verified_complete" and set(source["observed_units"]) != set(req.get("expected_units", ())):
                        cls = "blocked_integrity"; reasons.append("units_mismatch")
                if source.get("effective_at_utc") and (_aware(source["effective_at_utc"]) is None or
                        _aware(source["effective_at_utc"]) > _aware(self.freeze_at_utc)):
                    cls = "blocked_temporal"; reasons.append("after_temporal_cutoff")
                if source.get("units_ok") is False:
                    cls = "blocked_integrity"; reasons.append("units_mismatch")
                if source.get("parser_mapping_ok") is False:
                    cls = "blocked_integrity"; reasons.append("parser_mapping_mismatch")
                if source.get("db_status_stale") or source.get("status_stale_mismatch"):
                    cls = "blocked_dependency"; reasons.append("db_status_stale_mismatch")
                validator = callback_map.get(str(req["domain"]))
                if validator is None and cls in {"verified_complete", "verified_partial", "verified_no_coverage"}:
                    cls = "blocked_dependency"; reasons.append("repository_validation_missing")
                elif validator is not None:
                    try:
                        result = validator(req, source)
                    except Exception:
                        result = False
                    if result is not True:
                        cls = "blocked_integrity"; reasons.append("repository_validation_failed")
            row["coverage_class"] = cls
            row["reason_codes"] = tuple(sorted(set(str(x) for x in reasons)))
            row["evidence_hashes"] = dict(source.get("evidence_hashes", {})) if source else {}
            row["missing_units"] = sorted(set(req.get("expected_units", ())) -
                                          set(row.get("observed_units") or ()))
            rows.append(row)
            if cls.startswith("blocked") or cls in {"missing", "pending", "retryable_failed", "terminal_failed"}:
                blockers.add(f"{req['security_id']}:{req['domain']}:{cls}")
        contract = self.production_contract if production_contract is None else production_contract
        official_contract = _official_contract_identity(contract)
        if registry_disapproved:
            blockers.add("registry_not_approved")
        canonical_rows = [{k: v for k, v in row.items() if k != "rechecked_at_utc"}
                          for row in rows]
        canonical = {"schema_version": "formal-coverage-v1", "freeze_at_utc": self.freeze_at_utc,
                     "production_contract": official_contract, "rows": canonical_rows,
                     "blockers": sorted(blockers)}
        payload = dict(canonical, rows=rows, manifest_hash=_digest(canonical),
                       diagnostics={"audit_at_utc": audit_at_utc,
                                    "sql": dict(db_diagnostics or {}),
                                    "timing": dict(timing_diagnostics or {})})
        result = object.__new__(VerifiedCoverageManifest)
        _seal(result, payload)
        return result


__all__ = ["COVERAGE_CLASSES", "CoverageRequirement", "FormalCoverageAuditor",
           "VerifiedCoverageManifest"]
