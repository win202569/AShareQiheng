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
from pathlib import Path
import sqlite3
import subprocess
import weakref
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .formal_registry_manifest import FormalRegistryBundleLoader, VerifiedRegistryBundle
from .formal_universe import FormalFrozenUniverseInput, _validate_frozen_universe_input


COVERAGE_CLASSES = (
    "verified_complete", "verified_partial", "verified_no_coverage",
    "not_applicable_signed", "missing", "pending", "retryable_failed",
    "terminal_failed", "blocked_schema", "blocked_registry",
    "blocked_identity", "blocked_integrity", "blocked_temporal",
    "blocked_ambiguous", "blocked_dependency",
)
_COVERAGE_SET = frozenset(COVERAGE_CLASSES)
_SEALS: dict[int, tuple[weakref.ReferenceType[Any], bytes, type]] = {}
_LIVE_CONTEXTS: dict[int, tuple[weakref.ReferenceType[Any], dict[str, Any]]] = {}
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


_CONTRACT_FIELDS = frozenset({
    "schema_version", "purpose", "approval_id", "signing_identity",
    "registry_manifest_hash", "frozen_input_hash", "requirements",
    "domain_owners", "expected_schema_version", "report_period", "query_version",
})


def _official_inputs(contract: Any, verifier: Any, bundle: Any, loader: Any, frozen: Any,
                     reqs: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Accept only a signed requirement catalog tied to genuine root proofs."""
    if not isinstance(contract, Mapping) or "canonical_json" not in contract:
        return None
    if type(bundle) is not VerifiedRegistryBundle:
        raise ValueError("official coverage requires a verified registry bundle")
    if type(loader) is not FormalRegistryBundleLoader or verifier is not loader._verifier:
        raise ValueError("official coverage requires a trusted registry loader and verifier")
    bundle.require_official()
    current_bundle = loader.load(bundle.manifest.manifest_hash)
    current_bundle.require_official()
    if current_bundle.manifest.manifest_hash != bundle.manifest.manifest_hash:
        raise ValueError("official coverage registry identity changed")
    if type(frozen) is not FormalFrozenUniverseInput:
        raise ValueError("official coverage requires a verified frozen universe")
    _validate_frozen_universe_input(frozen)
    raw = contract.get("canonical_json")
    signature, key_id = contract.get("signature"), contract.get("key_id")
    if type(raw) is not bytes or type(signature) is not str or type(key_id) is not str:
        raise ValueError("coverage contract signature envelope is malformed")
    try:
        wire = json.loads(raw)
        if type(wire) is not dict or set(wire) != _CONTRACT_FIELDS or _canonical(wire) != raw:
            raise ValueError("coverage contract canonical JSON is malformed")
    except (TypeError, ValueError) as exc:
        raise ValueError("coverage contract canonical JSON is malformed") from exc
    try:
        accepted = verifier.verify(raw, signature=signature, key_id=key_id)
    except Exception as exc:
        raise ValueError("coverage contract signature verification failed") from exc
    if (accepted is not True or key_id != wire["signing_identity"]
            or key_id != bundle.manifest.key_id):
        raise ValueError("coverage contract signature verification failed")
    if wire["schema_version"] != "formal-coverage-contract-v1" or wire["purpose"] != "official":
        raise ValueError("coverage contract purpose or version is invalid")
    if (wire["approval_id"] != bundle.manifest.approval_id
            or wire["registry_manifest_hash"] != bundle.manifest.manifest_hash
            or wire["registry_manifest_hash"] != frozen.registry_manifest_hash
            or wire["frozen_input_hash"] != frozen.frozen_input_hash):
        raise ValueError("coverage contract registry or frozen root identity mismatch")
    catalog = wire["requirements"]
    if type(catalog) is not list or not catalog or any(type(row) is not dict for row in catalog):
        raise ValueError("coverage contract requirements are invalid")
    keys = [_key(row) for row in catalog]
    if any(None in key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("coverage contract requirements must be unique")
    members = {member.security_id: member.exchange for member in frozen.members}
    if ({row["security_id"] for row in catalog} != set(members)
            or any(row["frozen_input_hash"] != frozen.frozen_input_hash
                   or members.get(row["security_id"]) != row["exchange"] for row in catalog)):
        raise ValueError("coverage contract must enumerate every frozen member")
    if any(row.get("frozen_input_hash") != frozen.frozen_input_hash for row in reqs):
        raise ValueError("coverage requirements do not match frozen root")
    if sorted(catalog, key=_key) != sorted(reqs, key=_key):
        raise ValueError("coverage requirements do not match signed catalog")
    owners = wire["domain_owners"]
    if (type(owners) is not dict or set(owners) != {row["domain"] for row in catalog}
            or any(type(owner) is not str or not owner for owner in owners.values())):
        raise ValueError("coverage contract repository owners are incomplete")
    if (type(wire["expected_schema_version"]) is not int
            or wire["expected_schema_version"] <= 0
            or any(type(wire[field]) is not str or not wire[field]
                   for field in ("report_period", "query_version"))):
        raise ValueError("coverage contract audit identity is invalid")
    return wire


def _read_environment(workspace_root: Any, db_path: Any, status_path: Any,
                      expected_schema_version: int) -> dict[str, Any]:
    if any(path is None for path in (workspace_root, db_path, status_path)):
        raise ValueError("official coverage requires read-only database and workspace identity")
    root, db, status = (Path(path).resolve() for path in (workspace_root, db_path, status_path))
    if not root.is_dir() or not db.is_file() or not status.is_file():
        raise ValueError("official coverage database or workspace identity is missing")
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False)
    if revision.returncode != 0 or len(revision.stdout.strip()) != 40:
        raise ValueError("official coverage workspace revision is unavailable")
    def db_hashes() -> dict[str, str | None]:
        hashes: dict[str, str | None] = {}
        for suffix in ("", "-wal", "-shm"):
            path = db.with_name(db.name + suffix)
            if not path.exists():
                if not suffix:
                    raise ValueError("official coverage database is missing")
                hashes[suffix] = None
                continue
            if not path.is_file():
                raise ValueError("official coverage database sidecar is invalid")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[suffix] = digest.hexdigest()
        return hashes

    before = db_hashes()
    db_sha256 = before[""]
    try:
        connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()
        status_wire = json.loads(status.read_text(encoding="utf-8"))
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise ValueError("official coverage database or status could not be read") from exc
    if db_hashes() != before:
        raise ValueError("official coverage database changed during identity read")
    status_schema_version = status_wire.get("schema_version") if type(status_wire) is dict else None
    if status_schema_version != expected_schema_version:
        raise ValueError("official coverage database schema version mismatch")
    if (type(status_wire) is not dict or status_wire.get("db_sha256") != db_sha256
            or _aware(status_wire.get("generated_at_utc")) is None):
        raise ValueError("official coverage database status identity mismatch")
    return {"workspace_revision": revision.stdout.strip(), "db_path": str(db),
            "db_sha256": db_sha256,
            "db_sidecar_sha256": {suffix: before[suffix] for suffix in ("-wal", "-shm")},
            "db_schema_versions": {"user_version": version,
                                   "status_schema_version": status_schema_version},
            "expected_schema_version": expected_schema_version,
            "status_generated_at_utc": status_wire["generated_at_utc"],
            "status_path": str(status)}


def _repository_provenance(req: Mapping[str, Any], source: Any,
                           owner: str, validator: Callable[..., Any]) -> dict[str, Any]:
    try:
        result = validator(req, source)
    except Exception as exc:
        raise ValueError("official coverage repository validation failed") from exc
    expected = {"domain": req["domain"], "owner": owner,
                "requirement_hash": _digest(req), "record_hash": _digest(source)}
    if (type(result) is not dict or set(result) != set(expected) | {"evidence_hash"}
            or any(result.get(field) != value for field, value in expected.items())
            or type(result.get("evidence_hash")) is not str
            or len(result["evidence_hash"]) != 64
            or any(char not in "0123456789abcdef" for char in result["evidence_hash"])):
        raise ValueError("official coverage repository provenance mismatch")
    return dict(result)


def _seal(obj: Any, payload: Mapping[str, Any]) -> None:
    raw = _canonical(payload)
    identity = id(obj)
    _SEALS[identity] = (weakref.ref(obj, lambda _: (_SEALS.pop(identity, None),
                                                  _LIVE_CONTEXTS.pop(identity, None))),
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
        if not data.get("authenticated_context"):
            raise ValueError("official coverage requires authenticated production contract")
        if data["blockers"]:
            raise ValueError("official coverage blocked: " + ",".join(data["blockers"]))
        live = _LIVE_CONTEXTS.get(id(self))
        if live is None or live[0]() is not self:
            raise ValueError("official coverage live proof context was revoked")
        context = live[1]
        wire = _official_inputs(context["contract"], context["verifier"],
                                context["bundle"], context["registry_loader"],
                                context["frozen"],
                                context["requirements"])
        if wire is None:
            raise ValueError("official coverage authenticated contract was revoked")
        paths = data["diagnostics"]["identity_paths"]
        current = _read_environment(paths["workspace_root"], paths["db_path"],
                                    paths["status_path"], data["expected_schema_version"])
        if any(data[field] != value for field, value in current.items()):
            raise ValueError("official coverage database or workspace identity changed")
        for row, req, source in zip(data["rows"], context["requirements"],
                                    context["sources"], strict=True):
            provenance = _repository_provenance(
                req, source, wire["domain_owners"][req["domain"]],
                context["validators"][req["domain"]],
            )
            if row.get("repository_provenance") != provenance:
                raise ValueError("official coverage repository provenance changed")


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
        _LIVE_CONTEXTS.pop(id(manifest), None)

    def audit(self, requirements: Sequence[CoverageRequirement | Mapping[str, Any]],
              records: Sequence[Mapping[str, Any]] | Mapping[Any, Mapping[str, Any]] = (),
              *, repository_validators: Mapping[str, Callable[..., Any]] | None = None,
              validators: Mapping[str, Callable[..., Any]] | None = None,
              production_contract: Any = None, registry: Mapping[str, Any] | None = None,
              contract_verifier: Any = None, registry_bundle: Any = None,
              registry_loader: Any = None,
              frozen_universe: Any = None, workspace_root: Any = None,
              db_path: Any = None, status_path: Any = None,
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
        contract = self.production_contract if production_contract is None else production_contract
        official_wire = _official_inputs(contract, contract_verifier, registry_bundle,
                                         registry_loader,
                                         frozen_universe, reqs)
        if official_wire is not None and _aware(self.freeze_at_utc) != _aware(frozen_universe.as_of_utc):
            raise ValueError("coverage freeze does not match frozen universe")
        environment = (_read_environment(workspace_root, db_path, status_path,
                                         official_wire["expected_schema_version"])
                       if official_wire is not None else None)
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
        if official_wire is not None and not set(official_wire["domain_owners"]) <= set(callback_map):
            raise ValueError("official coverage repository validation callback is missing")
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
                if official_wire is None:
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
            if official_wire is not None:
                row["repository_provenance"] = _repository_provenance(
                    req, source, official_wire["domain_owners"][req["domain"]],
                    callback_map[str(req["domain"])],
                )
            row["coverage_class"] = cls
            row["reason_codes"] = tuple(sorted(set(str(x) for x in reasons)))
            row["evidence_hashes"] = dict(source.get("evidence_hashes", {})) if source else {}
            row["missing_units"] = sorted(set(req.get("expected_units", ())) -
                                          set(row.get("observed_units") or ()))
            rows.append(row)
            if cls.startswith("blocked") or cls in {"missing", "pending", "retryable_failed", "terminal_failed"}:
                blockers.add(f"{req['security_id']}:{req['domain']}:{cls}")
        official_contract = ({"contract_hash": hashlib.sha256(contract["canonical_json"]).hexdigest(),
                              "approval_id": official_wire["approval_id"],
                              "signing_identity": official_wire["signing_identity"]}
                             if official_wire is not None else None)
        if registry_disapproved:
            blockers.add("registry_not_approved")
        canonical_rows = [{k: v for k, v in row.items() if k != "rechecked_at_utc"}
                          for row in rows]
        canonical = {"schema_version": "formal-coverage-v1", "freeze_at_utc": self.freeze_at_utc,
                     "production_contract": official_contract, "rows": canonical_rows,
                     "blockers": sorted(blockers)}
        if official_wire is not None:
            assert environment is not None
            canonical.update(environment)
            canonical.update({
                "authenticated_context": True,
                "report_period": official_wire["report_period"],
                "query_version": official_wire["query_version"],
                "registry_manifest_hash": frozen_universe.registry_manifest_hash,
                "frozen_input_hash": frozen_universe.frozen_input_hash,
                "universe_source": frozen_universe.source_audit_hash,
                "universe_records_hash": frozen_universe.universe_hash,
                "member_count": len(frozen_universe.members),
                "member_count_by_exchange": {
                    exchange: sum(member.exchange == exchange for member in frozen_universe.members)
                    for exchange in ("SH", "SZ", "BJ")},
            })
        payload = dict(canonical, rows=rows, manifest_hash=_digest(canonical),
                       diagnostics={"audit_at_utc": audit_at_utc,
                                    "sql": dict(db_diagnostics or {}),
                                    "timing": dict(timing_diagnostics or {}),
                                    "identity_paths": ({"workspace_root": str(Path(workspace_root).resolve()),
                                                        "db_path": environment["db_path"],
                                                        "status_path": environment["status_path"]}
                                                       if environment is not None else None)})
        result = object.__new__(VerifiedCoverageManifest)
        _seal(result, payload)
        if official_wire is not None:
            _LIVE_CONTEXTS[id(result)] = (
                weakref.ref(result),
                {"contract": dict(contract), "verifier": contract_verifier,
                 "bundle": registry_bundle, "registry_loader": registry_loader,
                 "frozen": frozen_universe,
                 "requirements": copy.deepcopy(reqs),
                 "sources": copy.deepcopy([by_key.get(key) for key in keys]),
                 "validators": {domain: callback_map[domain]
                                for domain in official_wire["domain_owners"]}},
            )
        return result


__all__ = ["COVERAGE_CLASSES", "CoverageRequirement", "FormalCoverageAuditor",
           "VerifiedCoverageManifest"]
