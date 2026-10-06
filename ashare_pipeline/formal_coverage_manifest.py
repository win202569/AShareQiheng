"""Fail-closed production coverage audit for the formal scoring run.

This module deliberately treats database row counts as observations only.  A
coverage row is verified only after its owner has revalidated the complete,
hash-bound evidence record.

The signed catalog has a closed source-evidence vocabulary for design section 9:
financial -> Snapshot/financial facts; trading_calendar -> Context's exchange
calendar selector; the six other Context kinds (or the legacy context umbrella)
-> Context facts; feature -> the current signed Feature slot; policy -> a Policy
decision; market/range -> a Policy market-liquidity decision with its complete
calendar/market range evidence. These last two domains mean the policy's signed
trading window, not arbitrary market queries. Their owner is Policy, whose
recheck authenticates the underlying Market and Range repositories.

Metric percentiles, Stage C valuation, and D1 final-input batches are downstream
calculation proofs, not source domains of this independent data audit (design
sections 3-5, 7.3, 9 and 13). Their own repositories/gates remain necessary for a
Stage D run. No catalog may relabel them as financial/features/policy coverage;
unmapped domain/owner pairs are rejected before evidence reads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import copy
import hashlib
import json
import os
import pickle
from pathlib import Path
import re
import sqlite3
import subprocess
import weakref
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .formal_registry_manifest import FormalRegistryBundleLoader, VerifiedRegistryBundle
from .formal_snapshot_repository import FormalSnapshotRepository
from .formal_context_repository import FormalContextRepository, _require_authentic_context_repository
from .formal_sources import CalendarSelector
from .formal_feature_repository import FormalFeatureRepository
from .formal_policy_financial import _feature_dependencies
from .formal_metric_batch_guard import _metric_batch_guard
from .formal_policy_repository import FormalPolicyRepository, VerifiedPolicyResultBatch
from .formal_repository_identity import _require_repository_initialization
from .formal_universe import FormalFrozenUniverseInput, _validate_frozen_universe_input
from . import state_store as _state_schema


COVERAGE_CLASSES = (
    "verified_complete", "verified_partial", "verified_no_coverage",
    "not_applicable_signed", "missing", "pending", "retryable_failed",
    "terminal_failed", "blocked_schema", "blocked_registry",
    "blocked_identity", "blocked_integrity", "blocked_temporal",
    "blocked_ambiguous", "blocked_dependency",
)
_COVERAGE_SET = frozenset(COVERAGE_CLASSES)
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
    "refresh_generation", "task_id", "collection_state", "captured_at_utc",
    "source_updated_at_utc",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT_FACT_DOMAINS = frozenset({"market_close", "security_state", "industry_snapshot",
    "regulatory_state", "event_calendar", "consensus_snapshot"})
_DOMAIN_ADAPTERS = MappingProxyType({
    "financial": ("formal_snapshot_repository", "financial"),
    "trading_calendar": ("formal_context_repository", "calendar"),
    "context": ("formal_context_repository", "context"),
    **{kind: ("formal_context_repository", "context") for kind in _CONTEXT_FACT_DOMAINS},
    "feature": ("formal_feature_repository", "feature"),
    "policy": ("formal_policy_repository", "policy"),
    "market": ("formal_policy_repository", "policy_market"),
    "range": ("formal_policy_repository", "policy_market"),
})


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _record_digest(value: Any) -> str:
    if isinstance(value, Mapping):
        value = {key: item for key, item in value.items()
                 if key not in {"rechecked_at_utc", "timing_diagnostics"}}
    return _digest(value)


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
    "domain_owners", "selector_descriptors", "expected_schema_version",
    "report_period", "query_version",
})


def _official_inputs(contract: Any, verifier: Any, bundle: Any, loader: Any, frozen: Any,
                     reqs: Sequence[Mapping[str, Any]], db_path: Any,
                     snapshot_repository: Any) -> dict[str, Any] | None:
    """Accept only a signed requirement catalog tied to genuine root proofs."""
    if not isinstance(contract, Mapping) or "canonical_json" not in contract:
        return None
    if type(bundle) is not VerifiedRegistryBundle:
        raise ValueError("official coverage requires a verified registry bundle")
    if type(loader) is not FormalRegistryBundleLoader or verifier is not loader._verifier:
        raise ValueError("official coverage requires a trusted registry loader and verifier")
    if (type(loader._repository) is not _state_schema.StateStore
            or type(snapshot_repository) is not FormalSnapshotRepository):
        raise ValueError("official coverage requires owning production repositories")
    store = loader._repository
    _require_repository_initialization(store)
    _require_repository_initialization(snapshot_repository)
    if (snapshot_repository._state_store is not store
            or Path(store.db_path).resolve() != Path(db_path).resolve()
            or verifier is not store._require_registry_verifier()):
        raise ValueError("official coverage repository authority or database identity mismatch")
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
    if any(domain not in _DOMAIN_ADAPTERS or owner != _DOMAIN_ADAPTERS[domain][0]
           for domain, owner in owners.items()):
        raise ValueError("coverage contract domain/owner pair has no authenticated adapter")
    descriptors = wire["selector_descriptors"]
    adapter_fields = {
        "financial": {"source", "dataset"},
        "context": {"context_kind", "scope_key", "as_of_utc"},
        "calendar": {"context_kind", "scope_key", "as_of_utc", "as_of_rule"},
        "feature": {"input_hash", "slot_id"},
        "policy": {"batch_hash", "rule_id"},
        "policy_market": {"batch_hash", "rule_id"},
    }
    common_fields = {"owner", "domain", "security_id", "exchange", "period_or_window"}
    if type(descriptors) is not dict or set(descriptors) != {row["selector_hash"] for row in catalog}:
        raise ValueError("coverage contract selector catalog is incomplete")
    for row in catalog:
        selector = descriptors[row["selector_hash"]]
        owner = owners[row["domain"]]
        adapter = _DOMAIN_ADAPTERS[row["domain"]][1]
        if (type(selector) is not dict
                or set(selector) != common_fields | adapter_fields[adapter]
                or _digest(selector) != row["selector_hash"]
                or selector["owner"] != owner
                or any(selector[field] != row[field] for field in
                       ("domain", "security_id", "exchange", "period_or_window"))
                or any(type(value) is not str or not value for value in selector.values())):
            raise ValueError("coverage contract selector descriptor or owner mismatch")
        if ((owner == "formal_context_repository" and _aware(selector["as_of_utc"]) is None)
                or (owner == "formal_feature_repository" and
                    _SHA256.fullmatch(selector["input_hash"]) is None)
                or (owner == "formal_policy_repository" and
                    _SHA256.fullmatch(selector["batch_hash"]) is None)):
            raise ValueError("coverage contract selector descriptor is invalid")
        if adapter == "context" and (selector["context_kind"] not in _CONTEXT_FACT_DOMAINS
                or row["domain"] != "context" and selector["context_kind"] != row["domain"]):
            raise ValueError("coverage contract Context domain and selected kind mismatch")
        if adapter == "calendar":
            CalendarSelector(**{field: selector[field] for field in
                ("context_kind", "scope_key", "exchange", "as_of_rule")})
    if (type(wire["expected_schema_version"]) is not int
            or wire["expected_schema_version"] <= 0
            or any(type(wire[field]) is not str or not wire[field]
                   for field in ("report_period", "query_version"))):
        raise ValueError("coverage contract audit identity is invalid")
    return wire


_GIT_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


def _run_workspace_git(root: Path, args: tuple[str, ...], binary: bool = False,
                       runner: Callable[..., Any] = subprocess.run,
                       environ: Mapping[str, str] = os.environ) -> Any:
    clean_environment = {key: value for key, value in environ.items()
                         if not key.upper().startswith("GIT_")}
    clean_environment.update({
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": str(root),
    })
    try:
        result = runner(["git", "-C", str(root), *args], capture_output=True,
                        text=not binary, check=False, env=clean_environment)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("official coverage Git command failed") from exc
    output_type = bytes if binary else str
    if (type(getattr(result, "returncode", None)) is not int
            or type(getattr(result, "stdout", None)) is not output_type
            or type(getattr(result, "stderr", None)) is not output_type):
        raise ValueError("official coverage Git command output is malformed")
    if result.returncode != 0:
        raise ValueError("official coverage Git command failed")
    if result.stderr:
        raise ValueError("official coverage Git command emitted stderr")
    return result.stdout


def _read_workspace_git_identity(workspace_root: Any,
                                 _git: Callable[..., Any] = _run_workspace_git,
                                 _oid_pattern: Any = _GIT_OBJECT_ID,
                                 _path_type: Any = Path) -> dict[str, str]:
    root = _path_type(workspace_root).resolve()
    if not root.is_dir():
        raise ValueError("official coverage workspace is missing")

    def git(*args: str, binary: bool = False) -> Any:
        return _git(root, tuple(args), binary)

    def scalar(*args: str) -> str:
        output = git(*args)
        lines = output.splitlines()
        if len(lines) != 1 or not lines[0] or output.strip() != lines[0]:
            raise ValueError("official coverage Git command output is malformed")
        return lines[0]

    top = _path_type(scalar("rev-parse", "--show-toplevel")).resolve()
    if top != root:
        raise ValueError("official coverage workspace must be the Git project root")

    def status() -> bytes:
        return git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
                   "ashare_pipeline", binary=True)

    def objects() -> tuple[str, str]:
        values = (scalar("rev-parse", "HEAD"),
                  scalar("rev-parse", "HEAD:ashare_pipeline"))
        if any(_oid_pattern.fullmatch(value) is None for value in values):
            raise ValueError("official coverage workspace Git identity is invalid")
        return values

    def parse_head_tree() -> dict[str, tuple[str, str]]:
        raw = git("ls-tree", "-r", "-z", "HEAD", "--", "ashare_pipeline", binary=True)
        if not raw or not raw.endswith(b"\0") or b"\0\0" in raw:
            raise ValueError("official coverage Git tree output is malformed")
        records: dict[str, tuple[str, str]] = {}
        for item in raw[:-1].split(b"\0"):
            header, separator, path_bytes = item.partition(b"\t")
            fields = header.split(b" ")
            try:
                mode, kind, object_id = (field.decode("ascii") for field in fields)
                path = path_bytes.decode("utf-8")
            except (UnicodeDecodeError, ValueError):
                raise ValueError("official coverage Git tree output is malformed") from None
            if (not separator or len(fields) != 3 or kind != "blob"
                    or mode not in {"100644", "100755"}
                    or _oid_pattern.fullmatch(object_id) is None
                    or not path.startswith("ashare_pipeline/")
                    or "\\" in path or "" in path.split("/")
                    or any(part in {".", ".."} for part in path.split("/"))
                    or path in records):
                raise ValueError("official coverage Git tree output is malformed")
            records[path] = (mode, object_id)
        if not records:
            raise ValueError("official coverage Git tree output is malformed")
        return records

    def parse_index() -> dict[str, tuple[str, str]]:
        raw = git("ls-files", "--stage", "-z", "--", "ashare_pipeline", binary=True)
        if not raw or not raw.endswith(b"\0") or b"\0\0" in raw:
            raise ValueError("official coverage Git index output is malformed")
        records: dict[str, tuple[str, str]] = {}
        for item in raw[:-1].split(b"\0"):
            header, separator, path_bytes = item.partition(b"\t")
            fields = header.split(b" ")
            try:
                mode, object_id, stage = (field.decode("ascii") for field in fields)
                path = path_bytes.decode("utf-8")
            except (UnicodeDecodeError, ValueError):
                raise ValueError("official coverage Git index output is malformed") from None
            if (not separator or len(fields) != 3 or stage != "0"
                    or mode not in {"100644", "100755"}
                    or _oid_pattern.fullmatch(object_id) is None
                    or not path.startswith("ashare_pipeline/") or "\\" in path
                    or "" in path.split("/")
                    or any(part in {".", ".."} for part in path.split("/"))
                    or path in records):
                raise ValueError("official coverage Git index output is malformed")
            records[path] = (mode, object_id)
        return records

    if status():
        raise ValueError("official coverage workspace source tree is dirty")
    revision, tree = objects()
    head_files = parse_head_tree()
    if parse_index() != head_files:
        raise ValueError("official coverage workspace index differs from HEAD")

    def actual_blobs() -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for path in head_files:
            candidate = root.joinpath(*path.split("/"))
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError("official coverage workspace tracked source type changed")
            actual_blob = scalar("hash-object", f"--path={path}", str(candidate))
            if _oid_pattern.fullmatch(actual_blob) is None:
                raise ValueError("official coverage Git command output is malformed")
            snapshot[path] = actual_blob
        return snapshot

    expected_blobs = {path: blob for path, (_, blob) in head_files.items()}
    first_blobs = actual_blobs()
    if first_blobs != expected_blobs:
        raise ValueError("official coverage workspace tracked source changed")
    after_status = status()
    after_revision, after_tree = objects()
    if after_status:
        raise ValueError("official coverage workspace source tree is dirty")
    if (revision, tree) != (after_revision, after_tree):
        raise ValueError("official coverage workspace identity changed during read")
    if parse_index() != head_files:
        raise ValueError("official coverage workspace index changed during read")
    second_blobs = actual_blobs()
    if second_blobs != expected_blobs or second_blobs != first_blobs:
        raise ValueError("official coverage workspace tracked source changed during read")
    final_status = status()
    final_revision, final_tree = objects()
    if final_status:
        raise ValueError("official coverage workspace source tree is dirty")
    if (revision, tree) != (final_revision, final_tree):
        raise ValueError("official coverage workspace identity changed during read")
    return {"workspace_revision": revision, "workspace_tree": tree}


def _require_workspace_git_identity(workspace_root: Any,
                                    expected: Mapping[str, Any],
                                    _read: Callable[..., Any] = _read_workspace_git_identity) -> None:
    if (type(expected) is not dict
            or set(expected) != {"workspace_revision", "workspace_tree"}
            or any(type(value) is not str for value in expected.values())):
        raise ValueError("official coverage workspace identity is invalid")
    if _read(workspace_root) != expected:
        raise ValueError("official coverage workspace identity changed")


def _read_environment(workspace_root: Any, db_path: Any, status_path: Any,
                      expected_schema_version: int) -> dict[str, Any]:
    if any(path is None for path in (workspace_root, db_path, status_path)):
        raise ValueError("official coverage requires read-only database and workspace identity")
    root, db, status = (Path(path).resolve() for path in (workspace_root, db_path, status_path))
    if root != Path(__file__).resolve().parent.parent:
        raise ValueError("official coverage workspace is not the loaded coverage project root")
    if not root.is_dir() or not db.is_file() or not status.is_file():
        raise ValueError("official coverage database or workspace identity is missing")
    workspace_identity = _read_workspace_git_identity(root)
    def db_hashes() -> dict[str, str | None]:
        hashes: dict[str, str | None] = {}
        for suffix in ("", "-wal"):
            path = db.with_name(db.name + suffix)
            if not path.exists():
                if not suffix:
                    raise ValueError("official coverage database is missing")
                hashes[suffix] = None
                continue
            if not path.is_file():
                raise ValueError("official coverage database sidecar is invalid")
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            # SQLite can create an empty WAL when a writer enters WAL mode. With no
            # frames it carries no durable generation beyond the main DB.
            hashes[suffix] = None if suffix == "-wal" and size == 0 else digest.hexdigest()
        return hashes

    before = db_hashes()
    db_sha256 = before[""]
    try:
        # Immutable mode is safe only for a checkpointed DB. With a WAL,
        # normal read-only mode must see the committed frames; a sidecar race
        # then fails the before/after generation comparison below.
        read_mode = "?mode=ro" if before["-wal"] is not None else "?mode=ro&immutable=1"
        connection = sqlite3.connect(db.as_uri() + read_mode, uri=True)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            # StateStore owns schema_migration, not SQLite user_version. A
            # foreign nonzero marker means another schema authority touched it.
            if version != 0:
                raise ValueError("official coverage database schema user_version mismatch")
            versions = tuple(row[0] for row in connection.execute(
                "SELECT version FROM schema_migration ORDER BY version"))
            expected_versions = tuple(range(2, _state_schema.SCHEMA_VERSION + 1))
            if versions != expected_versions or expected_schema_version != _state_schema.SCHEMA_VERSION:
                raise ValueError("official coverage database schema migrations mismatch")
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            expected_tables = {"schema_migration"}
            for schema_version in expected_versions:
                table_ddl = getattr(_state_schema, f"_V{schema_version}_TABLE_DDL")
                index_ddl = getattr(_state_schema, f"_V{schema_version}_INDEX_DDL")
                _state_schema.StateStore._assert_schema_ddl(
                    connection, table_ddl, index_ddl, f"v{schema_version} schema")
                expected_tables.update(table_ddl)
            _state_schema.StateStore._assert_schema_ddl(
                connection, {"schema_migration": _state_schema._MIGRATION_TABLE_DDL},
                {}, "migration ledger")
            if tables != expected_tables:
                raise ValueError("official coverage database schema tables mismatch")
        finally:
            connection.close()
        status_wire = json.loads(status.read_text(encoding="utf-8"))
    except (sqlite3.Error, OSError, RuntimeError) as exc:
        raise ValueError("official coverage database schema or status could not be read") from exc
    # SHM read marks are transient SQLite coordination bytes. Only main DB
    # and committed WAL bytes identify the durable generation.
    material = lambda hashes: {suffix: hashes[suffix] for suffix in ("", "-wal")}
    if material(db_hashes()) != material(before):
        raise ValueError("official coverage database changed during identity read")
    status_schema_version = status_wire.get("schema_version") if type(status_wire) is dict else None
    if status_schema_version != expected_schema_version:
        raise ValueError("official coverage database schema version mismatch")
    if (type(status_wire) is not dict or status_wire.get("db_sha256") != db_sha256
            or status_wire.get("db_generation_hash") != _digest(material(before))
            or status_wire.get("schema_versions") != list(versions)
            or _aware(status_wire.get("generated_at_utc")) is None):
        raise ValueError("official coverage database status identity mismatch")
    return {**workspace_identity, "db_path": str(db),
            "db_sha256": db_sha256,
            "db_sidecar_sha256": {"-wal": before["-wal"]},
            "db_schema_versions": {"user_version": version,
                                   "migrations": list(versions),
                                   "status_schema_version": status_schema_version},
            "expected_schema_version": expected_schema_version,
            "status_generated_at_utc": status_wire["generated_at_utc"],
            "status_path": str(status)}


def _repository_provenance(req: Mapping[str, Any], source: Any,
                           owner: str, validator: Callable[..., Any] | None,
                           snapshots: FormalSnapshotRepository,
                           selector: Mapping[str, Any], *, typed_context=None,
                           cache=None) -> dict[str, Any]:
    if owner != "formal_snapshot_repository":
        return _typed_repository_provenance(req, source, owner, snapshots, selector,
                                            typed_context, cache)
    if not isinstance(source, Mapping) or source.get("coverage_class") not in {
            "verified_complete", "verified_partial", "verified_no_coverage"}:
        raise ValueError("official coverage requires verified source repository evidence")
    try:
        ref = snapshots.get_verified_by_manifest(source["manifest_sha256"])
        raw = snapshots.read_verified_raw(ref)
    except Exception as exc:
        raise ValueError("official coverage source repository evidence is missing") from exc
    bindings = {
        "snapshot_id": "selected_snapshot_id", "source": "source", "dataset": "dataset",
        "request_fingerprint": "request_fingerprint", "security_id": "security_id",
        "period_or_date": "period_or_window", "exchange": "exchange",
        "content_sha256": "content_sha256", "manifest_sha256": "manifest_sha256",
        "parser_id": "parser_id", "parser_version": "parser_version",
        "mapping_version": "mapping_version", "published_at_utc": "published_at_utc",
        "effective_at_utc": "effective_at_utc", "captured_at_utc": "captured_at_utc",
        "source_updated_at_utc": "source_updated_at_utc",
        "refresh_generation": "refresh_generation", "producing_task_id": "task_id",
    }
    if (any(getattr(ref, attribute) != source.get(field) if field not in req
            else getattr(ref, attribute) != req[field]
            for attribute, field in bindings.items())
            or ref.verification_status != "verified"
            or hashlib.sha256(raw).hexdigest() != ref.content_sha256
            or ref.source != selector["source"] or ref.dataset != selector["dataset"]):
        raise ValueError("official coverage source repository lineage mismatch")
    facts = tuple(fact for fact in snapshots._state_store.list_formal_financial_facts(
        security_id=req["security_id"])
        if fact.source_snapshot_id == ref.snapshot_id
        and fact.period_end == req["period_or_window"])
    actual_units = {fact.unit for fact in facts}
    if (source.get("coverage_class") != "verified_complete"
            or not facts
            or actual_units != set(source.get("observed_units", ()))
            or not set(req.get("expected_units", ())) <= actual_units):
        raise ValueError("official coverage owning financial repository unit proof is incomplete")
    evidence_hash = _digest({"manifest_sha256": ref.manifest_sha256,
                             "raw_sha256": hashlib.sha256(raw).hexdigest(),
                             "facts": [fact.to_dict() for fact in facts]})
    try:
        result = validator(req, source)
    except Exception as exc:
        raise ValueError("official coverage repository validation failed") from exc
    expected = {"domain": req["domain"], "owner": owner,
                "requirement_hash": _digest(req), "record_hash": _record_digest(source),
                "evidence_hash": evidence_hash}
    if (type(result) is not dict or set(result) != set(expected) | {"evidence_hash"}
            or any(result.get(field) != value for field, value in expected.items())
            or type(result.get("evidence_hash")) is not str
            or len(result["evidence_hash"]) != 64
            or any(char not in "0123456789abcdef" for char in result["evidence_hash"])):
        raise ValueError("official coverage repository provenance mismatch")
    return dict(result)


def _typed_repository_provenance(req, source, owner, snapshots, selector, context, cache):
    """Fixed owner adapters. Only repository reads and sealed batches authorize rows.

    Aggregate lineage columns contain sorted distinct values; the full selected
    item and dependency evidence remain in the canonical provenance receipt.
    The signed period/window for these as-of selections is the frozen cutoff.
    """
    if context is None or owner not in {
            "formal_context_repository", "formal_feature_repository", "formal_policy_repository"}:
        raise ValueError("coverage repository owner has no authenticated adapter")
    frozen, graph = context["frozen"], context["bundle"]
    root, freeze = frozen.registry_manifest_hash, _aware(frozen.as_of_utc).isoformat()
    store = snapshots._state_store
    if (req["frozen_input_hash"] != frozen.frozen_input_hash
            or _aware(req["period_or_window"]) != _aware(freeze)
            or req["exchange"] != req["security_id"][:2]):
        raise ValueError("coverage repository owner requirement root, window or exchange mismatch")
    evidence, units = {}, []
    calendar_selector = calendar_binding = None
    coverage_class = "verified_complete"
    if owner == "formal_context_repository":
        repository = context["context_repository"]
        if type(repository) is not FormalContextRepository:
            raise ValueError("coverage repository owner requires genuine Context repository")
        _require_authentic_context_repository(repository)
        if (repository._state_store is not store or repository._snapshots is not snapshots
                or repository._verifier is not store._require_registry_verifier()
                or _aware(selector["as_of_utc"]) != _aware(freeze)):
            raise ValueError("coverage Context owner or cutoff mismatch")
        if _DOMAIN_ADAPTERS[req["domain"]][1] == "calendar":
            calendar_selector = CalendarSelector(**{field: selector[field] for field in
                ("context_kind", "scope_key", "exchange", "as_of_rule")})
            calendar_binding = repository.resolve_verified_calendar_binding(
                calendar_selector, req["exchange"], freeze, root)
            binding = asdict(calendar_binding)
            if any(binding[field] != expected for field, expected in (
                    ("exchange", req["exchange"]), ("freeze_at_utc", freeze),
                    ("registry_manifest_hash", root), ("selector_hash", calendar_selector.selector_hash))):
                raise ValueError("coverage calendar selector binding mismatch")
            candidates = store.list_formal_context_facts(registry_manifest_hash=root,
                context_kind="trading_calendar", scope_key=selector["scope_key"], as_of_utc=freeze,
                source_snapshot_id=binding["snapshot_id"])
            matches = [fact for fact in candidates if fact.security_id is None
                       and fact.value["exchange"] == req["exchange"]]
            if len(matches) != 1:
                raise ValueError("coverage calendar selected fact is absent or ambiguous")
            fact = matches[0]
            ref = snapshots.get_verified_by_manifest(binding["manifest_sha256"])
            if (ref.snapshot_id != fact.source_snapshot_id or ref.snapshot_id != binding["snapshot_id"]
                    or ref.security_id is not None or ref.exchange != req["exchange"]
                    or ref.producing_task_id != binding["prerequisite_task_id"]):
                raise ValueError("coverage calendar source identity mismatch")
            evidence.update(calendar_selector=asdict(calendar_selector), calendar_binding=binding)
        else:
            fact = repository.get_verified(selector["context_kind"], selector["scope_key"],
                req["security_id"], freeze, root)
        selected = fact.to_dict()
        if (fact.security_id != (None if calendar_selector is not None else req["security_id"])
                or fact.as_of_utc != freeze
                or fact.registry_manifest_hash != root
                or fact.context_kind != selector["context_kind"]
                or fact.scope_key != selector["scope_key"]):
            raise ValueError("coverage Context selected fact key mismatch")
        evidence["fact"] = selected
        if fact.no_coverage:
            coverage_class = "verified_no_coverage"
        _require_authentic_context_repository(repository)
    elif owner == "formal_feature_repository":
        repository = context["feature_repository"]
        if type(repository) is not FormalFeatureRepository:
            raise ValueError("coverage repository owner requires genuine Feature repository")
        provider = _feature_dependencies(repository)
        if (repository._store is not store
                or repository._verifier is not store._require_registry_verifier()):
            raise ValueError("coverage Feature owner store or verifier mismatch")
        with _metric_batch_guard(provider, store) as guard:
            historical = repository._read_authenticated_bundle(
                input_hash=selector["input_hash"], require_complete=False)
            if (historical is None or historical.security_id != req["security_id"]
                    or historical.registry_manifest_hash != root or historical.as_of_utc != freeze):
                raise ValueError("coverage Feature input key or root mismatch")
            _, registry = repository._registry(root)
            slots = {slot.slot_id: slot for slot in registry.slots_for_template(historical.template_id)}
            slot = slots.get(selector["slot_id"])
            if slot is None:
                raise ValueError("coverage Feature selected slot is absent")
            if slot.required:
                current = repository.select_current_verified_metric_features(req["security_id"],
                    freeze, template_id=historical.template_id, registry_manifest_hash=root,
                    required_feature_keys=(selector["slot_id"],))
                same_bundle = current is not None and current.bundle_hash == historical.bundle_hash()
            else:
                current = repository.select_current_verified_formal_feature_bundle(req["security_id"],
                    freeze, template_id=historical.template_id, registry_manifest_hash=root)
                same_bundle = current is not None and current.canonical_bytes() == historical.canonical_bytes()
            if (current is None or current.input_hash != selector["input_hash"]
                    or not same_bundle or current.blockers):
                raise ValueError("coverage Feature signed input is stale")
            matches = [value for value in current.values if value.slot_id == selector["slot_id"]]
            if len(matches) != 1 or matches[0].status != "derived" or not matches[0].evidence:
                raise ValueError("coverage Feature selected slot is absent or incomplete")
            selected = matches[0].to_dict()
            units = [matches[0].unit]
            evidence = {"bundle": historical.to_dict(), "selection": current.to_dict(),
                "bundle_hash": historical.bundle_hash(),
                "facts": [fact.to_dict() for fact in store.list_formal_financial_facts(
                    security_id=req["security_id"])]}
            guard.finalize(lambda: _feature_dependencies(repository))
    else:
        repository, batch = context["policy_repository"], context["policy_batch"]
        if type(repository) is not FormalPolicyRepository or type(batch) is not VerifiedPolicyResultBatch:
            raise ValueError("coverage repository owner requires genuine Policy repository and batch")
        if repository._batch_journal_identity()[0] is not store:
            raise ValueError("coverage Policy owner store mismatch")
        wire = cache["policy"] if "policy" in cache else batch.to_dict()
        if (wire["batch_hash"] != selector["batch_hash"]
                or wire["frozen_input_hash"] != frozen.frozen_input_hash
                or wire["registry_manifest_hash"] != root or wire["as_of_utc"] != freeze
                or wire["universe_hash"] != frozen.universe_hash
                or wire["security_ids"] != [member.security_id for member in frozen.members]):
            raise ValueError("coverage Policy batch key or root mismatch")
        matches = [decision for result in wire["results"] if result["security_id"] == req["security_id"]
                   for decision in result["decisions"] if decision["rule_id"] == selector["rule_id"]]
        if (len(matches) != 1 or matches[0]["security_id"] != req["security_id"]
                or matches[0]["evaluation_state"] not in {"matched", "clear", "not_applicable"}
                or matches[0]["pending_requirements"]):
            raise ValueError("coverage Policy selected security/rule is absent or incomplete")
        selected = matches[0]
        evidence = {"batch": wire}
        if _DOMAIN_ADAPTERS[req["domain"]][1] == "policy_market":
            rule_input = wire["evidence_batch"]["rule_inputs"][req["security_id"]].get(selector["rule_id"])
            market = wire["evidence_batch"]["selections"][req["security_id"]].get(selector["rule_id"])
            window = None if market is None else market.get("window")
            if (rule_input is None or rule_input["rule"]["kind"] != "market_liquidity"
                    or market is None or market["pending"] or window is None or window["pending"]
                    or window != rule_input["market"]
                    or any(window[field] != expected for field, expected in (
                        ("security_id", req["security_id"]), ("exchange", req["exchange"]),
                        ("as_of_utc", freeze), ("registry_manifest_hash", root), ("rule_id", selector["rule_id"])))
                    or not window["observations"] or not window["lineage"]
                    or not window["calendar_coverage_hash"] or not window["required_trading_days"]
                    or any(day["coverage"] != "covered" for day in window["daily_records"])
                    or [day["date"] for day in window["daily_records"]] != window["required_trading_days"]):
                raise ValueError("coverage market/range requires the complete signed market-liquidity selection")
            evidence.update(market_selection=market, market_rule=rule_input["rule"])
        if "policy" not in cache:
            # Reject a mismatched signed selection before expensive source
            # reads; every accepted row still requires the original owner to
            # recheck the complete published batch before evidence is returned.
            repository.recheck_current(batch)
            cache["policy"] = wire
        if selected["evaluation_state"] == "not_applicable":
            coverage_class = "not_applicable_signed"
    if set(req.get("expected_units", ())) != set(units):
        raise ValueError("coverage owner selected item units mismatch")

    # Preserve every underlying source ref, including the facts used to derive
    # an aggregate feature or policy decision. The owner validates its complete
    # evidence graph above; these reads also bind raw source bytes to this row.
    ids = set()
    def collect(value):
        if isinstance(value, dict):
            if type(value.get("source_snapshot_id")) is str:
                ids.add(value["source_snapshot_id"])
            for item in value.values():
                collect(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)
    collect(evidence)
    lineage = []
    for snapshot_id in sorted(ids):
        ref = store.get_formal_snapshot(snapshot_id)
        if ref is None or ref.verification_status != "verified":
            raise ValueError("coverage owner source snapshot is missing")
        raw = snapshots.read_verified_raw(ref)
        if hashlib.sha256(raw).hexdigest() != ref.content_sha256:
            raise ValueError("coverage owner raw source hash mismatch")
        task = store.get_formal_task(ref.producing_task_id)
        if task is None or task["status"] != "verified":
            raise ValueError("coverage owner source task is not verified")
        lineage.append(dict(asdict(ref), collection_state=task["status"]))
    # Policy owns the Range observations: its original current-state recheck
    # above reauthenticates their signed parser/config, tasks, receipts and raw
    # bytes (including the bound calendar coverage). Project those authenticated
    # source identities too, so market/range rows retain real source lineage.
    if "market_selection" in evidence:
        for observation in evidence["market_selection"]["window"]["observations"]:
            document, snapshot, task = observation["document"], observation["snapshot"], observation["task"]
            lineage.append(dict(document, snapshot_id=snapshot["id"],
                manifest_sha256=snapshot["manifest_sha256"], content_sha256=snapshot["content_sha256"],
                content_path=snapshot["content_path"], manifest_path=snapshot["manifest_path"],
                producing_task_id=task["id"], collection_state=task["status"],
                refresh_generation=observation["generation"]["refresh_generation"],
                observation_hash=observation["observation_hash"]))
    evidence["source_snapshots"] = lineage
    evidence["selector_descriptor"] = dict(selector)
    evidence["registry_manifest_hash"] = root
    evidence["registry_hashes"] = {role: graph.blob(role).registry_hash for role in graph.roles}
    if calendar_selector is not None:
        current = repository.resolve_verified_calendar_binding(calendar_selector, req["exchange"], freeze, root)
        if asdict(current) != asdict(calendar_binding):
            raise ValueError("coverage calendar selection changed during evidence read")
        _require_authentic_context_repository(repository)
    bindings = {"selected_snapshot_id": "snapshot_id", "task_id": "producing_task_id"}
    record = dict(req)
    for field in _VERIFIED_LINEAGE_FIELDS:
        values = { _canonical(item.get(bindings.get(field, field))) for item in lineage }
        detached = [json.loads(value) for value in sorted(values)]
        record[field] = detached[0] if len(detached) == 1 else detached
    record.update(required=True, coverage_class=coverage_class, observed_units=units,
        verification_state="verified", temporal_state="visible", reason_codes=[],
        evidence_hashes={"selection": _digest(selected), "evidence": _digest(evidence),
                         "registry": root, "frozen_input": frozen.frozen_input_hash})
    if source is not None and _record_digest(source) != _record_digest(record):
        raise ValueError("coverage owner record differs from authenticated selection")
    return dict(domain=req["domain"], owner=owner, requirement_hash=_digest(req),
        record_hash=_record_digest(record), evidence_hash=_digest(evidence),
        selected_item=selected, evidence=evidence, record=record)


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
        raise ValueError("coverage proof authority is unavailable")

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
        self._data()

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

    def _recheck_official_provenance(self) -> None:
        raise ValueError("coverage proof authority is unavailable")

    def _recheck_official_workspace(self) -> None:
        raise ValueError("coverage proof authority is unavailable")

    def require_preview_ready(self) -> None:
        data = self._data()
        if data["blockers"]:
            raise ValueError("coverage preview blocked: " + ",".join(data["blockers"]))

    def require_official_ready(self) -> None:
        raise ValueError("coverage proof authority is unavailable")


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
        raise ValueError("coverage proof authority is unavailable")

    def _audit_payload(self, requirements: Sequence[CoverageRequirement | Mapping[str, Any]],
              records: Sequence[Mapping[str, Any]] | Mapping[Any, Mapping[str, Any]] = (),
              *, repository_validators: Mapping[str, Callable[..., Any]] | None = None,
              validators: Mapping[str, Callable[..., Any]] | None = None,
              production_contract: Any = None, registry: Mapping[str, Any] | None = None,
              contract_verifier: Any = None, registry_bundle: Any = None,
              registry_loader: Any = None,
              snapshot_repository: Any = None,
              context_repository: Any = None, feature_repository: Any = None,
              policy_repository: Any = None, policy_batch: Any = None,
              frozen_universe: Any = None, workspace_root: Any = None,
              db_path: Any = None, status_path: Any = None,
              db_diagnostics: Mapping[str, Any] | None = None,
              audit_at_utc: str | None = None,
              timing_diagnostics: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
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
                                         frozen_universe, reqs, db_path,
                                         snapshot_repository)
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
        if official_wire is not None and any(domain not in callback_map
                for domain, owner in official_wire["domain_owners"].items()
                if owner == "formal_snapshot_repository"):
            raise ValueError("official coverage repository validation callback is missing")
        typed_context = dict(context_repository=context_repository, feature_repository=feature_repository,
            policy_repository=policy_repository, policy_batch=policy_batch,
            frozen=frozen_universe, bundle=registry_bundle)
        owner_cache = {}
        registry_disapproved = registry is not None and registry.get("approved") is False
        rows: list[dict[str, Any]] = []
        blockers: set[str] = set()
        for req in reqs:
            key = _key(req)
            source = by_key.get(key)
            provenance = None
            if official_wire is not None and official_wire["domain_owners"][req["domain"]] != "formal_snapshot_repository":
                provenance = _repository_provenance(req, source,
                    official_wire["domain_owners"][req["domain"]], None, snapshot_repository,
                    official_wire["selector_descriptors"][req["selector_hash"]],
                    typed_context=typed_context, cache=owner_cache)
            row = {field: None for field in _AUDIT_ROW_FIELDS}
            row.update(req)
            row["required"] = True
            reasons: list[str] = []
            identity_mismatch = any(
                tuple(k for i, k in enumerate(candidate_key) if i != 5) ==
                tuple(k for i, k in enumerate(key) if i != 5)
                for candidate_key in by_key if candidate_key != key
            )
            if provenance is not None:
                source = provenance["record"]
                row.update(source)
                cls = source["coverage_class"]
            elif source is None:
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
                if cls == "not_applicable_signed":
                    # A caller's flags, hash and generic callback are not an
                    # owning-repository applicability proof. No existing
                    # coverage adapter can authenticate this class yet.
                    cls = "blocked_dependency"; reasons.append("applicability_owner_proof_missing")
                if cls in {"verified_complete", "verified_partial", "verified_no_coverage"}:
                    if any(type(source.get(field)) is not str or not source[field].strip()
                           for field in _VERIFIED_LINEAGE_FIELDS):
                        cls = "blocked_integrity"; reasons.append("incomplete_verified_lineage")
                    elif (source.get("authenticated") is not True
                          or source.get("signature_ok") is not True
                          or source.get("hash_ok") is not True
                          or any(type(source.get(field)) is not str
                                 or _SHA256.fullmatch(source[field]) is None
                                 for field in ("request_fingerprint", "content_sha256", "manifest_sha256"))
                          or not isinstance(source.get("evidence_hashes"), Mapping)
                          or not source["evidence_hashes"]
                          or any(type(value) is not str or _SHA256.fullmatch(value) is None
                                 for value in source["evidence_hashes"].values())):
                        cls = "blocked_integrity"; reasons.append("source_hash_or_signature_invalid")
                    elif source.get("verification_state") != "verified" or source.get("temporal_state") != "visible":
                        cls = "blocked_integrity"; reasons.append("unverified_source_state")
                    elif not isinstance(source.get("observed_units"), (list, tuple)):
                        cls = "blocked_integrity"; reasons.append("missing_observed_units")
                    elif cls == "verified_complete" and set(source["observed_units"]) != set(req.get("expected_units", ())):
                        cls = "blocked_integrity"; reasons.append("units_mismatch")
                if any(source.get(field) is not None and
                       (_aware(source[field]) is None or _aware(source[field]) > _aware(self.freeze_at_utc))
                       for field in ("published_at_utc", "effective_at_utc", "source_updated_at_utc")):
                    cls = "blocked_temporal"; reasons.append("after_temporal_cutoff")
                if source.get("captured_at_utc") is not None and _aware(source["captured_at_utc"]) is None:
                    cls = "blocked_temporal"; reasons.append("invalid_capture_time")
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
                row["repository_provenance"] = provenance or _repository_provenance(
                    req, source, official_wire["domain_owners"][req["domain"]],
                    callback_map.get(str(req["domain"])), snapshot_repository,
                    official_wire["selector_descriptors"][req["selector_hash"]],
                )
            row["coverage_class"] = cls
            row["reason_codes"] = tuple(sorted(set(str(x) for x in reasons)))
            row["evidence_hashes"] = dict(source.get("evidence_hashes", {})) if source else {}
            row["missing_units"] = sorted(set(req.get("expected_units", ())) -
                                          set(row.get("observed_units") or ()))
            rows.append(row)
            if cls.startswith("blocked") or cls in {"missing", "pending", "retryable_failed", "terminal_failed"}:
                blockers.add(f"{req['security_id']}:{req['domain']}:{cls}")
            if cls == "verified_partial" and row["missing_units"]:
                blockers.add(f"{req['security_id']}:{req['domain']}:required_units_incomplete")
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
        context = None
        if official_wire is not None:
            if _read_environment(workspace_root, db_path, status_path,
                                 official_wire["expected_schema_version"]) != environment:
                raise ValueError("coverage environment changed during owner validation")
            context = {"contract": dict(contract), "verifier": contract_verifier,
                 "bundle": registry_bundle, "registry_loader": registry_loader,
                 "snapshot_repository": snapshot_repository, "db_path": db_path,
                 "frozen": frozen_universe,
                 "typed_context": typed_context,
                 "requirements": copy.deepcopy(reqs),
                 "sources": copy.deepcopy([by_key.get(key) for key in keys]),
                 "validators": {domain: callback_map.get(domain)
                                for domain in official_wire["domain_owners"]}}
        return payload, context


def _install_coverage_authority() -> None:
    # The only minting/revocation state lives in this closure. In particular,
    # there is no module-level seal registry or callable resealing a proof.
    seals: dict[int, tuple[weakref.ReferenceType[Any], bytes, type]] = {}
    live_contexts: dict[int, tuple[weakref.ReferenceType[Any], dict[str, Any]]] = {}
    build_payload = FormalCoverageAuditor._audit_payload
    workspace_authorities = tuple((name, function, function.__code__, function.__defaults__)
        for name, function in (
            ("_run_workspace_git", _run_workspace_git),
            ("_read_workspace_git_identity", _read_workspace_git_identity),
            ("_require_workspace_git_identity", _require_workspace_git_identity)))
    require_workspace = _require_workspace_git_identity

    def require_workspace_authority() -> None:
        if any(globals().get(name) is not function
                or function.__code__ is not code
                or function.__defaults__ is not defaults
                for name, function, code, defaults in workspace_authorities):
            raise ValueError("official coverage workspace authority changed")

    def read(obj: Any) -> Mapping[str, Any]:
        item = seals.get(id(obj))
        if item is None or item[0]() is not obj or item[2] is not type(obj):
            raise ValueError("coverage proof is not a genuine verified manifest")
        return json.loads(item[1])

    def audit(self: FormalCoverageAuditor, *args: Any, **kwargs: Any) -> VerifiedCoverageManifest:
        payload, context = build_payload(self, *args, **kwargs)
        result = object.__new__(VerifiedCoverageManifest)
        identity = id(result)
        raw = _canonical(payload)
        seals[identity] = (
            weakref.ref(result, lambda _: (seals.pop(identity, None),
                                           live_contexts.pop(identity, None))),
            raw, type(result),
        )
        if context is not None:
            live_contexts[identity] = (weakref.ref(result), context)
        return result

    def revoke(manifest: VerifiedCoverageManifest) -> None:
        if type(manifest) is not VerifiedCoverageManifest:
            raise ValueError("coverage proof is not a genuine verified manifest")
        read(manifest)
        seals.pop(id(manifest), None)
        live_contexts.pop(id(manifest), None)

    def official_provenance_gate(self: VerifiedCoverageManifest) -> None:
        data = read(self)
        if not data.get("authenticated_context"):
            raise ValueError("official coverage requires authenticated production contract")
        if data["blockers"]:
            raise ValueError("official coverage blocked: " + ",".join(data["blockers"]))
        live = live_contexts.get(id(self))
        if live is None or live[0]() is not self:
            raise ValueError("official coverage live proof context was revoked")
        context = live[1]
        wire = _official_inputs(context["contract"], context["verifier"],
                                context["bundle"], context["registry_loader"],
                                context["frozen"], context["requirements"],
                                context["db_path"], context["snapshot_repository"])
        if wire is None:
            raise ValueError("official coverage authenticated contract was revoked")
        owner_cache = {}
        for row, req, source in zip(data["rows"], context["requirements"],
                                    context["sources"], strict=True):
            provenance = _repository_provenance(
                req, source, wire["domain_owners"][req["domain"]],
                context["validators"][req["domain"]], context["snapshot_repository"],
                wire["selector_descriptors"][req["selector_hash"]],
                typed_context=context["typed_context"], cache=owner_cache,
            )
            if row.get("repository_provenance") != provenance:
                raise ValueError("official coverage repository provenance changed")

    def official_workspace_gate(self: VerifiedCoverageManifest) -> None:
        require_workspace_authority()
        data = read(self)
        if not data.get("authenticated_context"):
            raise ValueError("official coverage requires authenticated production contract")
        paths = data["diagnostics"]["identity_paths"]
        require_workspace(paths["workspace_root"], {
            "workspace_revision": data["workspace_revision"],
            "workspace_tree": data["workspace_tree"],
        })

    def official_gate(self: VerifiedCoverageManifest) -> None:
        data = read(self)
        if not data.get("authenticated_context"):
            raise ValueError("official coverage requires authenticated production contract")
        if data["blockers"]:
            raise ValueError("official coverage blocked: " + ",".join(data["blockers"]))
        official_workspace_gate(self)
        paths = data["diagnostics"]["identity_paths"]
        current = _read_environment(paths["workspace_root"], paths["db_path"],
                                    paths["status_path"], data["expected_schema_version"])
        if any(data[field] != value for field, value in current.items()):
            raise ValueError("official coverage database or workspace identity changed")
        official_provenance_gate(self)
        after = _read_environment(paths["workspace_root"], paths["db_path"],
                                  paths["status_path"], data["expected_schema_version"])
        if after != current:
            raise ValueError("coverage environment changed during gate recheck")

    def preview_gate(self: VerifiedCoverageManifest) -> None:
        data = read(self)
        if data["blockers"]:
            raise ValueError("coverage preview blocked: " + ",".join(data["blockers"]))
        if data.get("authenticated_context"):
            official_gate(self)

    type.__setattr__(_Proof, "_data", read)
    type.__setattr__(VerifiedCoverageManifest, "_recheck_official_provenance", official_provenance_gate)
    type.__setattr__(VerifiedCoverageManifest, "_recheck_official_workspace", official_workspace_gate)
    type.__setattr__(VerifiedCoverageManifest, "require_official_ready", official_gate)
    type.__setattr__(VerifiedCoverageManifest, "require_preview_ready", preview_gate)
    FormalCoverageAuditor.audit = audit
    FormalCoverageAuditor.revoke = staticmethod(revoke)


_install_coverage_authority()
del _install_coverage_authority


__all__ = ["COVERAGE_CLASSES", "CoverageRequirement", "FormalCoverageAuditor",
           "VerifiedCoverageManifest"]
