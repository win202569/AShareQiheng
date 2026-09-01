"""Deterministic planning and resumable deep financial feature execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from ashare_pipeline.feature_contract import (
    FeatureBundle,
    canonical_json_bytes,
    canonical_sha256,
    require_aware_utc,
)
from ashare_pipeline.financial_features import (
    SHANGHAI,
    build_feature_bundle,
    build_financial_facts,
    feature_input_hash,
    select_visible_facts,
    trading_days_from_batch,
    validate_feature_calendar_request,
)
from ashare_pipeline.financial_schema import FINANCIAL_REQUEST_VERSION
from ashare_pipeline.snapshot_repository import SnapshotRef, SnapshotRepository
from ashare_pipeline.sources import (
    FinancialStatementSource,
    RetryableSourceError,
    SourceBlocked,
    TerminalSourceError,
)
from ashare_pipeline.state_store import JobSpec, StateStore


STATEMENT_DATASETS = ("balance_sheet", "profit_sheet", "cash_flow_sheet")

_SECURITY_ID = re.compile(r"^(?:SH|SZ)\d{6}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_STATEMENT_PAYLOAD_KEYS = frozenset(
    {
        "security_id",
        "dataset",
        "report_period",
        "candidate_set_hash",
        "performance_input_hash",
        "request_version",
        "refresh_date",
    }
)


def _require_security_id(value: object) -> str:
    if not isinstance(value, str) or _SECURITY_ID.fullmatch(value) is None:
        raise ValueError("security_id must be an SH/SZ security identifier")
    return value


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return value.lower()


def _require_iso_date(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        normalized = date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error
    if normalized != value:
        raise ValueError(f"{field} must be a canonical ISO date")
    return normalized


def _require_nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True)
class CandidateContext:
    candidate_set_hash: str
    members: frozenset[str]
    performance_input_hashes: Mapping[str, str]
    industries: Mapping[str, str]
    reported_target_period: Mapping[str, bool]

    def __post_init__(self) -> None:
        candidate_hash = _require_sha256(
            self.candidate_set_hash, "candidate_set_hash"
        )
        members = frozenset(_require_security_id(value) for value in self.members)
        if set(self.performance_input_hashes) != set(members):
            raise ValueError("performance_input_hashes keys must match candidate members")
        if set(self.industries) != set(members):
            raise ValueError("industries keys must match candidate members")
        if set(self.reported_target_period) != set(members):
            raise ValueError("reported_target_period keys must match candidate members")

        performance_hashes: dict[str, str] = {}
        industries: dict[str, str] = {}
        reported: dict[str, bool] = {}
        for security_id in sorted(members):
            performance_hashes[security_id] = _require_sha256(
                self.performance_input_hashes[security_id],
                f"performance_input_hashes[{security_id}]",
            )
            industries[security_id] = _require_nonempty_text(
                self.industries[security_id], f"industries[{security_id}]"
            )
            reported_value = self.reported_target_period[security_id]
            if not isinstance(reported_value, bool):
                raise ValueError(
                    f"reported_target_period[{security_id}] must be boolean"
                )
            reported[security_id] = reported_value

        object.__setattr__(self, "candidate_set_hash", candidate_hash)
        object.__setattr__(self, "members", members)
        object.__setattr__(
            self, "performance_input_hashes", MappingProxyType(performance_hashes)
        )
        object.__setattr__(self, "industries", MappingProxyType(industries))
        object.__setattr__(
            self, "reported_target_period", MappingProxyType(reported)
        )


def _validated_document(
    value: object,
    *,
    label: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} document must be an object")
    document = dict(value)
    if document.get("schema_version") != 2:
        raise ValueError(f"{label} document must use schema_version 2")

    input_hashes = document.get("input_hashes")
    if not isinstance(input_hashes, Mapping):
        raise ValueError(f"{label} input_hashes must be an object")
    normalized_inputs: dict[str, object] = {}
    for key, item in input_hashes.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} input_hashes keys must be non-empty strings")
        normalized_inputs[key] = item
    try:
        normalized_inputs = json.loads(canonical_json_bytes(normalized_inputs))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} input_hashes must be canonical JSON") from error

    raw_records = document.get("records")
    if not isinstance(raw_records, list):
        raise ValueError(f"{label} records must be a list")
    records: list[dict[str, object]] = []
    for row in raw_records:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} records must contain objects")
        try:
            records.append(json.loads(canonical_json_bytes(dict(row))))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} records must be canonical JSON") from error

    if "records_hash" not in document:
        raise ValueError(f"{label} records_hash is required")
    stored_hash = _require_sha256(
        document["records_hash"], f"{label} records_hash"
    )
    if stored_hash != canonical_sha256(records):
        raise ValueError(f"{label} records_hash does not match records")
    return normalized_inputs, records


def build_candidate_context(
    prefilter_document: Mapping[str, object],
    performance_document: Mapping[str, object],
) -> CandidateContext:
    """Build the frozen current-candidate view from verified curated documents."""

    prefilter_inputs, prefilter_records = _validated_document(
        prefilter_document, label="prefilter"
    )
    _, performance_records = _validated_document(
        performance_document, label="performance"
    )

    performance_by_id: dict[str, dict[str, object]] = {}
    for row in performance_records:
        security_id = _require_security_id(row.get("security_id"))
        if security_id in performance_by_id:
            raise ValueError(f"duplicate performance record for {security_id}")
        performance_by_id[security_id] = row

    industries: dict[str, str] = {}
    for row in prefilter_records:
        security_id = _require_security_id(row.get("security_id"))
        if security_id in industries:
            raise ValueError(f"duplicate prefilter record for {security_id}")
        industries[security_id] = _require_nonempty_text(
            row.get("industry"), f"industry for {security_id}"
        )

    missing = sorted(set(industries) - set(performance_by_id))
    if missing:
        raise ValueError(
            "selected candidate has no corresponding performance record: "
            + ",".join(missing)
        )

    performance_hashes = {
        security_id: canonical_sha256(performance_by_id[security_id])
        for security_id in sorted(industries)
    }
    performance_pairs = [
        [security_id, performance_hashes[security_id]]
        for security_id in sorted(performance_hashes)
    ]
    candidate_set_hash = canonical_sha256(
        {
            "prefilter_input_hashes": prefilter_inputs,
            "performance_input_hashes": performance_pairs,
        }
    )
    return CandidateContext(
        candidate_set_hash=candidate_set_hash,
        members=frozenset(industries),
        performance_input_hashes=performance_hashes,
        industries=industries,
        reported_target_period={security_id: True for security_id in industries},
    )


def _no_duplicate_object_keys(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _read_curated_document(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicate_object_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read curated candidate document: {path}") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"curated candidate document must be an object: {path}")
    return value


def load_candidate_context(root: str | Path) -> CandidateContext:
    data_root = Path(root)
    curated_root = data_root / "curated"
    return build_candidate_context(
        _read_curated_document(curated_root / "prefilter.json"),
        _read_curated_document(curated_root / "performance.json"),
    )


def deep_statement_key(
    security_id: str,
    dataset: str,
    report_period: str,
    as_of_cn_date: str,
) -> str:
    security = _require_security_id(security_id)
    if dataset not in STATEMENT_DATASETS:
        raise ValueError(f"unsupported statement dataset: {dataset}")
    period = _require_iso_date(report_period, "report_period")
    refresh_date = _require_iso_date(as_of_cn_date, "as_of_cn_date")
    return f"deep_statement:v1:{security}:{dataset}:{period}:{refresh_date}"


def feature_build_key(
    security_id: str,
    report_period: str,
    input_hash: str,
) -> str:
    security = _require_security_id(security_id)
    period = _require_iso_date(report_period, "report_period")
    digest = _require_sha256(input_hash, "input_hash")
    return f"feature_build:v1:{security}:{period}:{digest}"


def statement_job_specs(
    candidate_context: CandidateContext,
    *,
    security_id: str,
    report_period: str,
    as_of_cn_date: str,
) -> tuple[JobSpec, JobSpec, JobSpec]:
    if not isinstance(candidate_context, CandidateContext):
        raise TypeError("candidate_context must be CandidateContext")
    security = _require_security_id(security_id)
    if security not in candidate_context.members:
        raise ValueError("security_id is not a current candidate")
    period = _require_iso_date(report_period, "report_period")
    refresh_date = _require_iso_date(as_of_cn_date, "as_of_cn_date")
    return tuple(
        JobSpec(
            "deep_statement",
            deep_statement_key(security, dataset, period, refresh_date),
            {
                "security_id": security,
                "dataset": dataset,
                "report_period": period,
                "candidate_set_hash": candidate_context.candidate_set_hash,
                "performance_input_hash": candidate_context.performance_input_hashes[
                    security
                ],
                "request_version": FINANCIAL_REQUEST_VERSION,
                "refresh_date": refresh_date,
            },
        )
        for dataset in STATEMENT_DATASETS
    )


def _validate_statement_payload(payload: object) -> None:
    if not isinstance(payload, Mapping) or set(payload) != _STATEMENT_PAYLOAD_KEYS:
        raise ValueError("existing deep statement payload has invalid keys")
    _require_security_id(payload["security_id"])
    dataset = payload["dataset"]
    if dataset not in STATEMENT_DATASETS:
        raise ValueError(f"unsupported statement dataset: {dataset}")
    _require_iso_date(payload["report_period"], "report_period")
    _require_sha256(payload["candidate_set_hash"], "candidate_set_hash")
    _require_sha256(payload["performance_input_hash"], "performance_input_hash")
    if payload["request_version"] != FINANCIAL_REQUEST_VERSION:
        raise ValueError("unsupported financial request version")
    _require_iso_date(payload["refresh_date"], "refresh_date")


def _followups_preserving_first_enqueue(
    store: StateStore,
    requested: Sequence[JobSpec],
) -> tuple[JobSpec, ...]:
    existing_by_key = {
        job["idempotency_key"]: job
        for job in store.list_jobs()
    }
    followups: list[JobSpec] = []
    for spec in requested:
        existing = existing_by_key.get(spec.idempotency_key)
        if existing is None:
            followups.append(spec)
            continue
        if existing["kind"] != spec.kind:
            raise ValueError(
                "existing deep statement job does not match requested spec"
            )
        _validate_statement_payload(existing["payload"])
        requested_payload = spec.payload
        if any(
            existing["payload"][field] != requested_payload[field]
            for field in (
                "security_id",
                "dataset",
                "report_period",
                "refresh_date",
            )
        ):
            raise ValueError(
                "existing deep statement payload does not match requested spec"
            )
        followups.append(
            JobSpec(existing["kind"], existing["idempotency_key"], existing["payload"])
        )
    return tuple(followups)


def expand_deep_parents(
    store: StateStore,
    candidate_context: CandidateContext,
    *,
    as_of_cn_date: str,
    worker_id: str,
    lease_seconds: int = 900,
) -> dict[str, int]:
    """Atomically expand every leasable legacy parent, stopping at an empty queue."""

    if not isinstance(store, StateStore):
        raise TypeError("store must be StateStore")
    if not isinstance(candidate_context, CandidateContext):
        raise TypeError("candidate_context must be CandidateContext")
    refresh_date = _require_iso_date(as_of_cn_date, "as_of_cn_date")
    worker = _require_nonempty_text(worker_id, "worker_id")
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
        raise ValueError("lease_seconds must be a positive integer")

    summary = {"expanded": 0, "superseded": 0, "children": 0}
    while True:
        parent = store.lease_next_job(
            ["deep_financial"], worker, lease_seconds
        )
        if parent is None:
            return summary

        payload = parent["payload"]
        if not isinstance(payload, Mapping):
            raise ValueError("deep_financial payload must be an object")
        security_id = _require_security_id(payload.get("security_id"))
        report_period = _require_iso_date(
            payload.get("report_period"), "report_period"
        )
        if "input_hash" in payload:
            _require_sha256(payload["input_hash"], "input_hash")

        if security_id not in candidate_context.members:
            store.complete_job_with_followups(
                parent["id"],
                worker,
                {"outcome": "superseded", "child_count": 0},
                (),
            )
            summary["superseded"] += 1
            continue

        requested = statement_job_specs(
            candidate_context,
            security_id=security_id,
            report_period=report_period,
            as_of_cn_date=refresh_date,
        )
        followups = _followups_preserving_first_enqueue(store, requested)
        store.complete_job_with_followups(
            parent["id"],
            worker,
            {"outcome": "expanded", "child_count": len(requested)},
            followups,
        )
        summary["expanded"] += 1
        summary["children"] += len(requested)


_FEATURE_PAYLOAD_KEYS = frozenset(
    {
        "security_id",
        "report_period",
        "as_of_utc",
        "candidate_set_hash",
        "industry",
        "reported_target_period",
        "performance_input_hash",
        "statement_snapshots",
        "trade_calendar_snapshot",
    }
)
_FROZEN_SNAPSHOT_KEYS = frozenset({"source_snapshot_id", "payload_hash"})
_FROZEN_CALENDAR_KEYS = frozenset(
    {
        "source_snapshot_id",
        "payload_hash",
        "source",
        "dataset",
        "request",
        "request_fingerprint",
    }
)
_SUMMARY_ITEM_KEYS = frozenset(
    {
        "security_id",
        "dataset",
        "snapshot_hash",
        "bundle_hash",
        "outcome",
        "error_classification",
    }
)
_TARGET_PERIOD_CUTOFF_CN = datetime(2026, 8, 31, 23, 59, 59, tzinfo=SHANGHAI)


def frozen_snapshot_payload(snapshot: SnapshotRef | None) -> dict[str, str] | None:
    if snapshot is None:
        return None
    if not isinstance(snapshot, SnapshotRef):
        raise TypeError("snapshot must be SnapshotRef or None")
    return {
        "source_snapshot_id": _require_nonempty_text(
            snapshot.id, "source_snapshot_id"
        ),
        "payload_hash": _require_sha256(snapshot.payload_hash, "payload_hash"),
    }


def _validate_statement_snapshot_ref(
    snapshot: SnapshotRef,
    *,
    dataset: str,
    security_id: str,
    report_period: str,
) -> None:
    expected_fingerprint = canonical_sha256(
        _statement_request(security_id, report_period)
    )
    if (
        snapshot.source != "akshare"
        or snapshot.dataset != dataset
        or snapshot.request_fingerprint != expected_fingerprint
    ):
        raise ValueError("statement snapshot does not match its frozen slot")


def _validate_calendar_snapshot_ref(snapshot: SnapshotRef) -> dict[str, str]:
    if not isinstance(snapshot, SnapshotRef):
        raise TypeError("trade calendar snapshot must be SnapshotRef")
    request = validate_feature_calendar_request(snapshot.request)
    expected_fingerprint = canonical_sha256(request)
    if (
        snapshot.source != "baostock"
        or snapshot.dataset != "trade_dates"
        or snapshot.request_fingerprint != expected_fingerprint
    ):
        raise ValueError("trade calendar snapshot does not match exact request")
    return request


def frozen_calendar_payload(snapshot: SnapshotRef | None) -> dict[str, object] | None:
    if snapshot is None:
        return None
    request = _validate_calendar_snapshot_ref(snapshot)
    return {
        "source_snapshot_id": _require_nonempty_text(
            snapshot.id, "source_snapshot_id"
        ),
        "payload_hash": _require_sha256(snapshot.payload_hash, "payload_hash"),
        "source": "baostock",
        "dataset": "trade_dates",
        "request": request,
        "request_fingerprint": canonical_sha256(request),
    }


def feature_build_payload(
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    context: CandidateContext,
    statement_snapshots: Mapping[str, SnapshotRef | None],
    trade_calendar_snapshot: SnapshotRef | None,
) -> dict[str, object]:
    if not isinstance(context, CandidateContext):
        raise TypeError("context must be CandidateContext")
    security = _require_security_id(security_id)
    if security not in context.members:
        raise ValueError("security_id is not a current candidate")
    period = _require_iso_date(report_period, "report_period")
    as_of = require_aware_utc(as_of_utc, "as_of_utc")
    if not isinstance(statement_snapshots, Mapping):
        raise TypeError("statement_snapshots must be a mapping")
    seen_snapshot_ids: set[str] = set()
    for dataset in STATEMENT_DATASETS:
        snapshot = statement_snapshots.get(dataset)
        if snapshot is None:
            continue
        if not isinstance(snapshot, SnapshotRef):
            raise TypeError("statement snapshots must contain SnapshotRef or None")
        _validate_statement_snapshot_ref(
            snapshot,
            dataset=dataset,
            security_id=security,
            report_period=period,
        )
        if snapshot.id in seen_snapshot_ids:
            raise ValueError("statement snapshot cannot occupy multiple slots")
        seen_snapshot_ids.add(snapshot.id)
    return {
        "security_id": security,
        "report_period": period,
        "as_of_utc": as_of,
        "candidate_set_hash": context.candidate_set_hash,
        "industry": context.industries[security],
        "reported_target_period": context.reported_target_period[security],
        "performance_input_hash": context.performance_input_hashes[security],
        "statement_snapshots": {
            dataset: frozen_snapshot_payload(statement_snapshots.get(dataset))
            for dataset in STATEMENT_DATASETS
        },
        "trade_calendar_snapshot": frozen_calendar_payload(trade_calendar_snapshot),
    }


def _feature_build_spec(
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    candidate_context: CandidateContext,
    statement_snapshots: Mapping[str, SnapshotRef | None],
    trade_calendar_snapshot: SnapshotRef | None,
) -> JobSpec:
    payload = feature_build_payload(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=as_of_utc,
        context=candidate_context,
        statement_snapshots=statement_snapshots,
        trade_calendar_snapshot=trade_calendar_snapshot,
    )
    frozen = payload["statement_snapshots"]
    if not isinstance(frozen, Mapping):
        raise ValueError("statement_snapshots must be a mapping")
    input_hash = feature_input_hash(
        security_id=payload["security_id"],
        report_period=payload["report_period"],
        as_of_utc=payload["as_of_utc"],
        candidate_set_hash=payload["candidate_set_hash"],
        statement_snapshot_hashes={
            dataset: (
                frozen[dataset]["payload_hash"]
                if frozen[dataset] is not None
                else None
            )
            for dataset in STATEMENT_DATASETS
        },
        trade_calendar_snapshot_hash=(
            payload["trade_calendar_snapshot"]["payload_hash"]
            if payload["trade_calendar_snapshot"] is not None
            else None
        ),
    )
    return JobSpec(
        "feature_build",
        feature_build_key(payload["security_id"], payload["report_period"], input_hash),
        payload,
    )


def enqueue_feature_build(
    store: StateStore,
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    candidate_context: CandidateContext,
    statement_snapshots: Mapping[str, SnapshotRef | None],
    trade_calendar_snapshot: SnapshotRef | None,
) -> str:
    if not isinstance(store, StateStore):
        raise TypeError("store must be StateStore")
    spec = _feature_build_spec(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=as_of_utc,
        candidate_context=candidate_context,
        statement_snapshots=statement_snapshots,
        trade_calendar_snapshot=trade_calendar_snapshot,
    )
    job_id = store.enqueue_job(spec.kind, spec.idempotency_key, spec.payload)
    stored = store.get_job(job_id)
    if (
        stored is None
        or stored["kind"] != spec.kind
        or stored["payload"] != spec.payload
    ):
        raise ValueError("feature-build idempotency key conflicts with existing job")
    return job_id


def _safe_feature_relative_path(bundle: FeatureBundle) -> str:
    if not isinstance(bundle, FeatureBundle):
        raise TypeError("bundle must be FeatureBundle")
    security = _require_security_id(bundle.security_id)
    period = _require_iso_date(bundle.report_period, "report_period")
    digest = _require_sha256(bundle.input_hash, "input_hash")
    return f"data/curated/formal_features/{period}/{security}/{digest}.json"


def _read_feature_bytes(
    project_root: Path, relative_path: str, expected_hash: str
) -> tuple[bytes, FeatureBundle]:
    digest = _require_sha256(expected_hash, "expected_hash")
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or "\\" in relative_path
        or Path(relative_path).is_absolute()
    ):
        raise ValueError("feature path must be project-relative")
    parts = relative_path.split("/")
    if (
        parts[:3] != ["data", "curated", "formal_features"]
        or len(parts) < 6
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("feature path must stay inside data/curated/formal_features")
    resolved_root = project_root.resolve()
    data_root = (resolved_root / "data").resolve()
    target = resolved_root.joinpath(*parts).resolve()
    try:
        target.relative_to(data_root)
    except ValueError as error:
        raise ValueError("feature path must stay inside project data") from error
    try:
        payload = target.read_bytes()
    except OSError as error:
        raise OSError("cannot read feature bundle") from error
    if hashlib.sha256(payload).hexdigest() != digest:
        raise OSError("feature bundle hash mismatch")
    try:
        decoded = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_no_duplicate_object_keys
        )
        if not isinstance(decoded, Mapping):
            raise ValueError("feature bundle must be an object")
        bundle = FeatureBundle.from_dict(decoded)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise OSError("feature bundle is malformed") from error
    if bundle.canonical_bytes() != payload or bundle.bundle_hash() != digest:
        raise OSError("feature bundle is not canonical")
    return payload, bundle


def read_verified_feature_bundle(
    project_root: str | Path,
    relative_path: str,
    expected_hash: str,
) -> FeatureBundle:
    return _read_feature_bytes(Path(project_root), relative_path, expected_hash)[1]


def write_feature_bundle(
    project_root: str | Path,
    bundle: FeatureBundle,
) -> tuple[str, str, bool]:
    root = Path(project_root).resolve()
    relative_path = _safe_feature_relative_path(bundle)
    target = root.joinpath(*relative_path.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    data_root = (root / "data").resolve()
    try:
        target.parent.resolve().relative_to(data_root)
    except ValueError as error:
        raise ValueError("feature target must stay inside project data") from error
    payload = bundle.canonical_bytes()
    digest = bundle.bundle_hash()
    descriptor, part_name = tempfile.mkstemp(
        prefix=f".{bundle.input_hash}.", suffix=".part", dir=target.parent
    )
    part = Path(part_name)
    created = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        part_payload = part.read_bytes()
        if hashlib.sha256(part_payload).hexdigest() != digest:
            raise OSError("feature part hash mismatch")
        try:
            parsed = FeatureBundle.from_dict(
                json.loads(
                    part_payload.decode("utf-8"),
                    object_pairs_hook=_no_duplicate_object_keys,
                )
            )
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise OSError("feature part is malformed") from error
        if parsed.canonical_bytes() != part_payload or parsed != bundle:
            raise OSError("feature part does not match canonical bundle")

        if target.exists():
            try:
                target.resolve().relative_to(data_root)
            except ValueError as error:
                raise ValueError("feature target must stay inside project data") from error
            existing = target.read_bytes()
            if existing != payload:
                raise ValueError("non-deterministic feature conflict")
            _read_feature_bytes(root, relative_path, digest)
            return relative_path, digest, False
        try:
            os.link(part, target)
            created = True
        except FileExistsError:
            try:
                target.resolve().relative_to(data_root)
            except ValueError as error:
                raise ValueError(
                    "feature target must stay inside project data"
                ) from error
            existing = target.read_bytes()
            if existing != payload:
                raise ValueError("non-deterministic feature conflict")
            _read_feature_bytes(root, relative_path, digest)
        return relative_path, digest, created
    finally:
        try:
            part.unlink()
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class DeepRunSummary:
    expanded: int
    superseded: int
    remote_attempts: int
    snapshots_reused: int
    statements_succeeded: int
    retryable_failed: int
    terminal_failed: int
    feature_sets_written: int
    circuit_breakers: tuple[str, ...]
    items: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        numeric_fields = (
            "expanded",
            "superseded",
            "remote_attempts",
            "snapshots_reused",
            "statements_succeeded",
            "retryable_failed",
            "terminal_failed",
            "feature_sets_written",
        )
        for field in numeric_fields:
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        circuits = tuple(dict.fromkeys(self.circuit_breakers))
        frozen_items: list[Mapping[str, object]] = []
        for item in self.items:
            if not isinstance(item, Mapping) or set(item) - _SUMMARY_ITEM_KEYS:
                raise ValueError("summary item contains non-whitelisted fields")
            frozen_items.append(MappingProxyType(dict(item)))
        object.__setattr__(self, "circuit_breakers", circuits)
        object.__setattr__(self, "items", tuple(frozen_items))

    def to_dict(self) -> dict[str, object]:
        return {
            "expanded": self.expanded,
            "superseded": self.superseded,
            "remote_attempts": self.remote_attempts,
            "snapshots_reused": self.snapshots_reused,
            "statements_succeeded": self.statements_succeeded,
            "retryable_failed": self.retryable_failed,
            "terminal_failed": self.terminal_failed,
            "feature_sets_written": self.feature_sets_written,
            "circuit_breakers": list(self.circuit_breakers),
            "items": [dict(item) for item in self.items],
        }


class _LeaseLostError(RuntimeError):
    """Signal that an owned job lease can no longer authorize side effects."""


class _LeaseHeartbeat:
    def __init__(
        self,
        store: StateStore,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
        heartbeat_seconds: float,
    ) -> None:
        self.store = store
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._stop = threading.Event()
        self._renew_lock = threading.Lock()
        self.lost = threading.Event()
        self.error: BaseException | None = None
        self.thread = threading.Thread(
            target=self._run,
            name=f"deep-heartbeat-{job_id}",
            daemon=True,
        )
        self.started = False
        self.closed = False

    def _run(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                with self._renew_lock:
                    if self._stop.is_set():
                        return
                    self.store.renew_job_lease(
                        self.job_id, self.worker_id, self.lease_seconds
                    )
            except BaseException as error:
                self.error = error
                self.lost.set()
                return

    def __enter__(self) -> "_LeaseHeartbeat":
        try:
            with self._renew_lock:
                self.store.renew_job_lease(
                    self.job_id, self.worker_id, self.lease_seconds
                )
        except BaseException as error:
            self.error = error
            self.lost.set()
            return self
        self.thread.start()
        self.started = True
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._stop.set()
        if not self.started:
            return
        self.thread.join(timeout=max(1.0, self.heartbeat_seconds * 2.0))
        if self.thread.is_alive():
            raise RuntimeError("lease heartbeat thread did not stop")

    def ensure_owned(self) -> None:
        if self.lost.is_set():
            raise _LeaseLostError("job lease heartbeat was lost") from self.error

    def final_transition(
        self,
        transition: Callable[..., None],
        *args: object,
        **kwargs: object,
    ) -> None:
        """Serialize the final owned transition against periodic renewal."""
        with self._renew_lock:
            self.ensure_owned()
            transition(*args, **kwargs)
            self._stop.set()


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _validate_feature_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping) or set(payload) != _FEATURE_PAYLOAD_KEYS:
        raise ValueError("feature-build payload has invalid keys")
    normalized = dict(payload)
    _require_security_id(normalized["security_id"])
    _require_iso_date(normalized["report_period"], "report_period")
    normalized["as_of_utc"] = require_aware_utc(normalized["as_of_utc"], "as_of_utc")
    _require_sha256(normalized["candidate_set_hash"], "candidate_set_hash")
    _require_sha256(normalized["performance_input_hash"], "performance_input_hash")
    _require_nonempty_text(normalized["industry"], "industry")
    if not isinstance(normalized["reported_target_period"], bool):
        raise ValueError("reported_target_period must be boolean")
    statements = normalized["statement_snapshots"]
    if not isinstance(statements, Mapping) or set(statements) != set(STATEMENT_DATASETS):
        raise ValueError("statement_snapshots must contain exactly three datasets")
    for dataset in STATEMENT_DATASETS:
        _validate_frozen_snapshot(statements[dataset])
    _validate_frozen_calendar_snapshot(normalized["trade_calendar_snapshot"])
    return normalized


def _validate_frozen_snapshot(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping) or set(value) != _FROZEN_SNAPSHOT_KEYS:
        raise ValueError("frozen snapshot payload has invalid keys")
    _require_nonempty_text(value["source_snapshot_id"], "source_snapshot_id")
    _require_sha256(value["payload_hash"], "payload_hash")


def _validate_frozen_calendar_snapshot(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping) or set(value) != _FROZEN_CALENDAR_KEYS:
        raise ValueError("frozen trade calendar payload has invalid keys")
    _require_nonempty_text(value["source_snapshot_id"], "source_snapshot_id")
    _require_sha256(value["payload_hash"], "payload_hash")
    if value["source"] != "baostock" or value["dataset"] != "trade_dates":
        raise ValueError("frozen trade calendar has invalid source or dataset")
    request = validate_feature_calendar_request(value["request"])
    fingerprint = _require_sha256(
        value["request_fingerprint"], "request_fingerprint"
    )
    if fingerprint != canonical_sha256(request):
        raise ValueError("frozen trade calendar request fingerprint mismatch")


def _resolve_frozen_snapshot(
    snapshots: SnapshotRepository, value: object
) -> SnapshotRef | None:
    _validate_frozen_snapshot(value)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("frozen snapshot payload must be a mapping")
    snapshot = snapshots.get(value["source_snapshot_id"])
    if snapshot is None:
        raise ValueError("frozen snapshot id does not exist")
    if snapshot.payload_hash != value["payload_hash"]:
        raise ValueError("frozen snapshot payload hash does not match repository")
    snapshots.read_verified(snapshot)
    return snapshot


def _resolve_frozen_calendar_snapshot(
    snapshots: SnapshotRepository, value: object
) -> SnapshotRef | None:
    _validate_frozen_calendar_snapshot(value)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("frozen trade calendar payload must be a mapping")
    snapshot = snapshots.get(value["source_snapshot_id"])
    if snapshot is None:
        raise ValueError("frozen trade calendar snapshot id does not exist")
    if (
        snapshot.payload_hash != value["payload_hash"]
        or snapshot.source != value["source"]
        or snapshot.dataset != value["dataset"]
        or snapshot.request_fingerprint != value["request_fingerprint"]
    ):
        raise ValueError("frozen trade calendar identity does not match repository")
    verified = snapshots.read_verified(snapshot)
    expected_request = validate_feature_calendar_request(value["request"])
    if (
        verified.batch.source != "baostock"
        or verified.batch.dataset != "trade_dates"
        or verified.batch.request != expected_request
        or canonical_sha256(verified.batch.request) != value["request_fingerprint"]
    ):
        raise ValueError("verified trade calendar does not match frozen identity")
    return snapshot


def _resolve_frozen_statement_snapshot(
    snapshots: SnapshotRepository,
    value: object,
    *,
    dataset: str,
    security_id: str,
    report_period: str,
) -> SnapshotRef | None:
    snapshot = _resolve_frozen_snapshot(snapshots, value)
    if snapshot is None:
        return None
    _validate_statement_snapshot_ref(
        snapshot,
        dataset=dataset,
        security_id=security_id,
        report_period=report_period,
    )
    verified = snapshots.read_verified(snapshot)
    expected_request = _statement_request(security_id, report_period)
    if (
        verified.batch.source != "akshare"
        or verified.batch.dataset != dataset
        or verified.batch.request != expected_request
    ):
        raise ValueError("verified statement snapshot does not match its frozen slot")
    return snapshot


def _lease_next_at_logical_time(
    store: StateStore,
    kinds: list[str],
    worker_id: str,
    lease_seconds: int,
    logical_now_utc: str,
) -> dict[str, object] | None:
    logical = datetime.fromisoformat(require_aware_utc(logical_now_utc, "logical_now_utc"))
    wall = datetime.now(timezone.utc)
    clock_skew = max(0, math.ceil((wall - logical).total_seconds()))
    return store.lease_next_job(
        kinds,
        worker_id,
        lease_seconds + clock_skew,
        logical.isoformat(),
    )


def _statement_request(security_id: str, report_period: str) -> dict[str, str]:
    return {"symbol": security_id, "report_period": report_period}


def _current_statement_refs(
    snapshots: SnapshotRepository,
    security_id: str,
    report_period: str,
) -> dict[str, SnapshotRef | None]:
    request = _statement_request(security_id, report_period)
    return {
        dataset: snapshots.find_exact("akshare", dataset, request)
        for dataset in STATEMENT_DATASETS
    }


def _record_fact_issues(
    store: StateStore,
    security_id: str,
    dataset: str,
    issues: Sequence[object],
    ensure_owned: Callable[[], None] | None = None,
) -> None:
    for issue in issues:
        if ensure_owned is not None:
            ensure_owned()
        store.record_quality_issue(
            run_id=None,
            score_run_id=None,
            severity=issue.severity,
            code=issue.code,
            details={
                "security_id": security_id,
                "dataset": dataset,
                "details": _thaw(issue.details),
            },
        )


def _verified_calendar_days(
    snapshots: SnapshotRepository,
    calendar_ref: SnapshotRef | None,
) -> tuple[date, ...] | None:
    if calendar_ref is None:
        return None
    stored = snapshots.get(calendar_ref.id)
    if (
        stored is None
        or stored.payload_hash != calendar_ref.payload_hash
        or stored.source != "baostock"
        or stored.dataset != "trade_dates"
    ):
        raise ValueError("trade calendar snapshot does not match repository")
    verified = snapshots.read_verified(stored)
    request = validate_feature_calendar_request(verified.batch.request)
    if stored.request_fingerprint != canonical_sha256(request):
        raise ValueError("trade calendar request fingerprint mismatch")
    return trading_days_from_batch(verified.batch)


def _normalize_statement_snapshot(
    *,
    store: StateStore,
    snapshots: SnapshotRepository,
    snapshot: SnapshotRef,
    security_id: str,
    trading_days: Sequence[date] | None,
    record_issues: bool,
    ensure_owned: Callable[[], None] | None = None,
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    if trading_days is None:
        return (), ()
    verified = snapshots.read_verified(snapshot)
    result = build_financial_facts(
        verified.batch,
        source_snapshot_id=snapshot.id,
        expected_security_id=security_id,
        trading_days=trading_days,
        created_at_utc=snapshot.fetched_at,
    )
    if ensure_owned is not None:
        ensure_owned()
    store.insert_financial_facts(result.facts)
    if record_issues:
        _record_fact_issues(
            store,
            security_id,
            snapshot.dataset,
            result.issues,
            ensure_owned,
        )
    return result.facts, result.issues


def _target_period_present(snapshot_batch: object, report_period: str) -> bool:
    return any(
        isinstance(row, Mapping)
        and isinstance(row.get("REPORT_DATE"), str)
        and row["REPORT_DATE"][:10] == report_period
        for row in snapshot_batch.records
    )


def _feature_file_target(project_root: Path, relative_path: str) -> Path:
    return project_root.joinpath(*relative_path.split("/"))


def _write_and_store_feature_bundle(
    *,
    project_root: Path,
    store: StateStore,
    bundle: FeatureBundle,
    ensure_owned: Callable[[], None],
) -> tuple[str, str, bool]:
    ensure_owned()
    relative_path, bundle_hash, file_created = write_feature_bundle(
        project_root, bundle
    )
    try:
        ensure_owned()
        _feature_set_id, database_created = store.put_feature_bundle(
            bundle,
            bundle_path=relative_path,
            bundle_hash=bundle_hash,
        )
    except BaseException:
        if file_created:
            committed = store.get_feature_bundle_row(
                bundle.security_id, bundle.report_period, bundle.input_hash
            )
            if (
                committed is None
                or committed["bundle_path"] != relative_path
                or committed["bundle_hash"] != bundle_hash
            ):
                target = _feature_file_target(project_root, relative_path)
                try:
                    current = target.read_bytes()
                    if hashlib.sha256(current).hexdigest() == bundle_hash:
                        target.unlink()
                except FileNotFoundError:
                    pass
        raise
    return relative_path, bundle_hash, database_created


def _execute_feature_job(
    *,
    root: Path,
    store: StateStore,
    snapshots: SnapshotRepository,
    context: CandidateContext,
    job: Mapping[str, object],
    worker_id: str,
    heartbeat: _LeaseHeartbeat,
) -> tuple[bool, Mapping[str, object]]:
    payload = _validate_feature_payload(job["payload"])
    security_id = payload["security_id"]
    report_period = payload["report_period"]
    if not isinstance(security_id, str) or not isinstance(report_period, str):
        raise ValueError("feature identity must contain string values")
    if security_id not in context.members:
        raise ValueError("feature security is not in the candidate context")
    if (
        payload["candidate_set_hash"] != context.candidate_set_hash
        or payload["performance_input_hash"]
        != context.performance_input_hashes[security_id]
        or payload["industry"] != context.industries[security_id]
        or payload["reported_target_period"]
        != context.reported_target_period[security_id]
    ):
        raise ValueError("feature payload does not match candidate context")
    frozen_statement_payloads = payload["statement_snapshots"]
    if not isinstance(frozen_statement_payloads, Mapping):
        raise ValueError("statement_snapshots must be a mapping")
    statement_refs = {
        dataset: _resolve_frozen_statement_snapshot(
            snapshots,
            frozen_statement_payloads[dataset],
            dataset=dataset,
            security_id=security_id,
            report_period=report_period,
        )
        for dataset in STATEMENT_DATASETS
    }
    statement_ids = [
        snapshot.id for snapshot in statement_refs.values() if snapshot is not None
    ]
    if len(statement_ids) != len(set(statement_ids)):
        raise ValueError("statement snapshot cannot occupy multiple slots")
    calendar_ref = _resolve_frozen_calendar_snapshot(
        snapshots, payload["trade_calendar_snapshot"]
    )
    statement_hashes = {
        dataset: (
            statement_refs[dataset].payload_hash
            if statement_refs[dataset] is not None
            else None
        )
        for dataset in STATEMENT_DATASETS
    }
    expected_input_hash = feature_input_hash(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=payload["as_of_utc"],
        candidate_set_hash=payload["candidate_set_hash"],
        statement_snapshot_hashes=statement_hashes,
        trade_calendar_snapshot_hash=(
            calendar_ref.payload_hash if calendar_ref is not None else None
        ),
    )
    expected_key = feature_build_key(
        security_id, report_period, expected_input_hash
    )
    if job.get("idempotency_key") != expected_key:
        raise ValueError("feature-build key does not match frozen payload")
    trading_days = _verified_calendar_days(snapshots, calendar_ref)

    issue_codes: set[str] = set()
    normalized_facts: list[object] = []
    for dataset in STATEMENT_DATASETS:
        snapshot = statement_refs[dataset]
        if snapshot is None:
            continue
        facts, issues = _normalize_statement_snapshot(
            store=store,
            snapshots=snapshots,
            snapshot=snapshot,
            security_id=security_id,
            trading_days=trading_days,
            record_issues=False,
            ensure_owned=heartbeat.ensure_owned,
        )
        normalized_facts.extend(facts)
        issue_codes.update(issue.code for issue in issues)

    selection = select_visible_facts(
        normalized_facts,
        as_of_utc=payload["as_of_utc"],
        snapshot_fetched_at={
            snapshot.id: snapshot.fetched_at
            for snapshot in statement_refs.values()
            if snapshot is not None
        },
    )
    bundle = build_feature_bundle(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=payload["as_of_utc"],
        candidate_set_hash=payload["candidate_set_hash"],
        source_industry_name=payload["industry"],
        facts=selection.facts,
        fact_blockers=tuple(sorted(set(selection.blockers) | issue_codes)),
        statement_snapshot_hashes=statement_hashes,
        trade_calendar_snapshot_hash=(
            calendar_ref.payload_hash if calendar_ref is not None else None
        ),
        reported_target_period=payload["reported_target_period"],
    )
    if bundle.input_hash != expected_input_hash:
        raise ValueError("feature bundle input hash does not match frozen payload")
    heartbeat.ensure_owned()
    relative_path, bundle_hash, created = _write_and_store_feature_bundle(
        project_root=root.parent,
        store=store,
        bundle=bundle,
        ensure_owned=heartbeat.ensure_owned,
    )
    verified = read_verified_feature_bundle(root.parent, relative_path, bundle_hash)
    if verified != bundle:
        raise OSError("stored feature bundle does not match built bundle")
    heartbeat.final_transition(
        lambda: store.complete_job_with_followups(
            job["id"],
            worker_id,
            {"outcome": "feature_built", "bundle_hash": bundle_hash},
            (),
        )
    )
    return created, MappingProxyType(
        {
            "security_id": security_id,
            "bundle_hash": bundle_hash,
            "outcome": "feature_built" if created else "feature_reused",
        }
    )


def _process_feature_jobs(
    *,
    root: Path,
    store: StateStore,
    snapshots: SnapshotRepository,
    context: CandidateContext,
    logical_now_utc: str,
    worker_id: str,
    lease_seconds: int,
    heartbeat_seconds: float,
    items: list[Mapping[str, object]],
) -> int:
    created_count = 0
    while True:
        job = _lease_next_at_logical_time(
            store,
            ["feature_build"],
            worker_id,
            lease_seconds,
            logical_now_utc,
        )
        if job is None:
            return created_count
        heartbeat = _LeaseHeartbeat(
            store,
            job["id"],
            worker_id,
            lease_seconds,
            heartbeat_seconds,
        )
        heartbeat.__enter__()
        try:
            heartbeat.ensure_owned()
            created, item = _execute_feature_job(
                root=root,
                store=store,
                snapshots=snapshots,
                context=context,
                job=job,
                worker_id=worker_id,
                heartbeat=heartbeat,
            )
        except _LeaseLostError:
            payload = job.get("payload")
            item_data: dict[str, object] = {
                "outcome": "lease_lost",
                "error_classification": "lease_lost",
            }
            if isinstance(payload, Mapping) and isinstance(
                payload.get("security_id"), str
            ):
                item_data["security_id"] = payload["security_id"]
            items.append(MappingProxyType(item_data))
            break
        except Exception as error:
            retryable = not isinstance(error, ValueError)
            try:
                heartbeat.final_transition(
                    lambda: store.fail_job_with_followups(
                        job["id"],
                        worker_id,
                        {"error_classification": "feature_build_error"},
                        retryable,
                        (
                            datetime.fromisoformat(logical_now_utc)
                            + timedelta(hours=6)
                        ).isoformat()
                        if retryable
                        else None,
                        (),
                    )
                )
            except _LeaseLostError:
                payload = job.get("payload")
                item_data = {
                    "outcome": "lease_lost",
                    "error_classification": "lease_lost",
                }
                if isinstance(payload, Mapping) and isinstance(
                    payload.get("security_id"), str
                ):
                    item_data["security_id"] = payload["security_id"]
                items.append(MappingProxyType(item_data))
                break
            except ValueError:
                raise error
            payload = job.get("payload")
            security_id = (
                payload.get("security_id")
                if isinstance(payload, Mapping)
                else None
            )
            item_data: dict[str, object] = {
                "outcome": "feature_failed",
                "error_classification": "feature_build_error",
            }
            if isinstance(security_id, str):
                item_data["security_id"] = security_id
            items.append(MappingProxyType(item_data))
            continue
        finally:
            heartbeat.close()
        created_count += int(created)
        items.append(item)
    return created_count


def _statement_followup(
    *,
    context: CandidateContext,
    snapshots: SnapshotRepository,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    trade_calendar_snapshot: SnapshotRef | None,
) -> JobSpec:
    return _feature_build_spec(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=as_of_utc,
        candidate_context=context,
        statement_snapshots=_current_statement_refs(
            snapshots, security_id, report_period
        ),
        trade_calendar_snapshot=trade_calendar_snapshot,
    )


def _statement_item(
    *,
    security_id: str,
    dataset: str,
    outcome: str,
    snapshot_hash: str | None = None,
    error_classification: str | None = None,
) -> Mapping[str, object]:
    item: dict[str, object] = {
        "security_id": security_id,
        "dataset": dataset,
        "outcome": outcome,
    }
    if snapshot_hash is not None:
        item["snapshot_hash"] = snapshot_hash
    if error_classification is not None:
        item["error_classification"] = error_classification
    return MappingProxyType(item)


def execute_queued_deep_work(
    *,
    root: Path,
    store: StateStore,
    context: CandidateContext,
    source: FinancialStatementSource | None,
    snapshots: SnapshotRepository,
    trade_calendar_snapshot: SnapshotRef | None,
    now_cn: datetime,
    online: bool,
    limit: int,
    worker_id: str,
    lease_seconds: int,
    heartbeat_seconds: float,
    planning: Mapping[str, int],
) -> DeepRunSummary:
    data_root, normalized_now, worker = _validate_run_inputs(
        root=root,
        store=store,
        source=source,
        snapshots=snapshots,
        now_cn=now_cn,
        online=online,
        limit=limit,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
    )
    if not isinstance(context, CandidateContext):
        raise TypeError("context must be CandidateContext")
    if not isinstance(planning, Mapping):
        raise TypeError("planning must be a mapping")
    expanded = planning.get("expanded", 0)
    superseded = planning.get("superseded", 0)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (expanded, superseded)
    ):
        raise ValueError("planning counts must be non-negative integers")
    if trade_calendar_snapshot is not None:
        if not isinstance(trade_calendar_snapshot, SnapshotRef):
            raise TypeError("trade_calendar_snapshot must be SnapshotRef or None")
        _verified_calendar_days(snapshots, trade_calendar_snapshot)

    logical_now_utc = normalized_now.astimezone(timezone.utc).isoformat()
    items: list[Mapping[str, object]] = []
    feature_sets_written = _process_feature_jobs(
        root=data_root,
        store=store,
        snapshots=snapshots,
        context=context,
        logical_now_utc=logical_now_utc,
        worker_id=worker,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        items=items,
    )
    counters = {
        "remote_attempts": 0,
        "snapshots_reused": 0,
        "statements_succeeded": 0,
        "retryable_failed": 0,
        "terminal_failed": 0,
    }
    circuits: list[str] = []
    if not online:
        return DeepRunSummary(
            expanded,
            superseded,
            counters["remote_attempts"],
            counters["snapshots_reused"],
            counters["statements_succeeded"],
            counters["retryable_failed"],
            counters["terminal_failed"],
            feature_sets_written,
            tuple(circuits),
            tuple(items),
        )
    if source is None:
        raise ValueError("online deep execution requires an explicit source")

    while counters["remote_attempts"] < limit:
        job = _lease_next_at_logical_time(
            store,
            ["deep_statement"],
            worker,
            lease_seconds,
            logical_now_utc,
        )
        if job is None:
            break
        heartbeat = _LeaseHeartbeat(
            store,
            job["id"],
            worker,
            lease_seconds,
            heartbeat_seconds,
        )
        heartbeat.__enter__()
        security_id: str | None = None
        dataset: str | None = None
        try:
            heartbeat.ensure_owned()
            _validate_statement_payload(job["payload"])
            payload = job["payload"]
            if not isinstance(payload, Mapping):
                raise ValueError("deep statement payload must be a mapping")
            security_id = payload["security_id"]
            dataset = payload["dataset"]
            report_period = payload["report_period"]
            refresh_date = payload["refresh_date"]
            if not all(
                isinstance(value, str)
                for value in (security_id, dataset, report_period, refresh_date)
            ):
                raise ValueError("deep statement identity fields must be strings")
            if security_id not in context.members:
                raise ValueError("statement job security is not a current candidate")
            request = _statement_request(security_id, report_period)
            existing = snapshots.find_exact("akshare", dataset, request)
            same_refresh = False
            if existing is not None:
                fetched = datetime.fromisoformat(
                    require_aware_utc(existing.fetched_at, "snapshot fetched_at")
                )
                same_refresh = (
                    fetched.astimezone(SHANGHAI).date().isoformat() == refresh_date
                )

            if same_refresh:
                snapshot = existing
                verified = snapshots.read_verified(snapshot)
                facts, issues = _normalize_statement_snapshot(
                    store=store,
                    snapshots=snapshots,
                    snapshot=snapshot,
                    security_id=security_id,
                    trading_days=_verified_calendar_days(
                        snapshots, trade_calendar_snapshot
                    ),
                    record_issues=True,
                    ensure_owned=heartbeat.ensure_owned,
                )
                counters["snapshots_reused"] += 1
            else:
                batch = None
                source_error: (
                    SourceBlocked | RetryableSourceError | TerminalSourceError | None
                ) = None
                heartbeat.ensure_owned()
                counters["remote_attempts"] += 1
                try:
                    batch = source.fetch_financial_statement(
                        security_id, dataset, report_period
                    )
                except (
                    SourceBlocked,
                    RetryableSourceError,
                    TerminalSourceError,
                ) as error:
                    source_error = error
                heartbeat.ensure_owned()
                if source_error is not None:
                    blocked = isinstance(source_error, SourceBlocked)
                    retryable = blocked or isinstance(
                        source_error, RetryableSourceError
                    )
                    classification = (
                        "source_blocked"
                        if blocked
                        else "retryable_source"
                        if retryable
                        else "terminal_source"
                    )
                    followup = _statement_followup(
                        context=context,
                        snapshots=snapshots,
                        security_id=security_id,
                        report_period=report_period,
                        as_of_utc=logical_now_utc,
                        trade_calendar_snapshot=trade_calendar_snapshot,
                    )
                    heartbeat.final_transition(
                        store.fail_job_with_followups,
                        job["id"],
                        worker,
                        {"error_classification": classification},
                        retryable,
                        (
                            normalized_now.astimezone(timezone.utc)
                            + timedelta(hours=6)
                        ).isoformat()
                        if retryable
                        else None,
                        (followup,),
                    )
                    counter = "retryable_failed" if retryable else "terminal_failed"
                    counters[counter] += 1
                    items.append(
                        _statement_item(
                            security_id=security_id,
                            dataset=dataset,
                            outcome=counter,
                            error_classification=classification,
                        )
                    )
                    if blocked:
                        circuits.append("akshare")
                    heartbeat.close()
                    feature_sets_written += _process_feature_jobs(
                        root=data_root,
                        store=store,
                        snapshots=snapshots,
                        context=context,
                        logical_now_utc=logical_now_utc,
                        worker_id=worker,
                        lease_seconds=lease_seconds,
                        heartbeat_seconds=heartbeat_seconds,
                        items=items,
                    )
                    if blocked:
                        break
                    continue
                if batch is None:
                    raise RuntimeError("remote statement request produced no batch")
                if (
                    batch.source != "akshare"
                    or batch.dataset != dataset
                    or batch.request != request
                ):
                    followup = _statement_followup(
                        context=context,
                        snapshots=snapshots,
                        security_id=security_id,
                        report_period=report_period,
                        as_of_utc=logical_now_utc,
                        trade_calendar_snapshot=trade_calendar_snapshot,
                    )
                    heartbeat.final_transition(
                        store.fail_job_with_followups,
                        job["id"],
                        worker,
                        {"error_classification": "mismatched_source_batch"},
                        False,
                        None,
                        (followup,),
                    )
                    counters["terminal_failed"] += 1
                    items.append(
                        _statement_item(
                            security_id=security_id,
                            dataset=dataset,
                            outcome="terminal_failed",
                            error_classification="mismatched_source_batch",
                        )
                    )
                    heartbeat.close()
                    feature_sets_written += _process_feature_jobs(
                        root=data_root,
                        store=store,
                        snapshots=snapshots,
                        context=context,
                        logical_now_utc=logical_now_utc,
                        worker_id=worker,
                        lease_seconds=lease_seconds,
                        heartbeat_seconds=heartbeat_seconds,
                        items=items,
                    )
                    continue
                heartbeat.ensure_owned()
                snapshot, _created = snapshots.persist(batch)
                verified = snapshots.read_verified(snapshot)
                facts, issues = _normalize_statement_snapshot(
                    store=store,
                    snapshots=snapshots,
                    snapshot=snapshot,
                    security_id=security_id,
                    trading_days=_verified_calendar_days(
                        snapshots, trade_calendar_snapshot
                    ),
                    record_issues=True,
                    ensure_owned=heartbeat.ensure_owned,
                )

            del facts
            followup = _statement_followup(
                context=context,
                snapshots=snapshots,
                security_id=security_id,
                report_period=report_period,
                as_of_utc=logical_now_utc,
                trade_calendar_snapshot=trade_calendar_snapshot,
            )
            terminal_issue = next(
                (issue for issue in issues if issue.severity == "error"), None
            )
            target_present = _target_period_present(
                verified.batch, report_period
            )
            if terminal_issue is not None:
                heartbeat.final_transition(
                    store.fail_job_with_followups,
                    job["id"],
                    worker,
                    {"error_classification": "malformed_statement"},
                    False,
                    None,
                    (followup,),
                )
                counters["terminal_failed"] += 1
                items.append(
                    _statement_item(
                        security_id=security_id,
                        dataset=dataset,
                        snapshot_hash=snapshot.payload_hash,
                        outcome="terminal_failed",
                        error_classification="malformed_statement",
                    )
                )
            elif context.reported_target_period[security_id] and not target_present:
                after_cutoff = normalized_now > _TARGET_PERIOD_CUTOFF_CN
                heartbeat.final_transition(
                    store.fail_job_with_followups,
                    job["id"],
                    worker,
                    {"error_classification": "target_period_missing"},
                    not after_cutoff,
                    (
                        normalized_now.astimezone(timezone.utc)
                        + timedelta(hours=6)
                    ).isoformat()
                    if not after_cutoff
                    else None,
                    (followup,),
                )
                counter = "terminal_failed" if after_cutoff else "retryable_failed"
                counters[counter] += 1
                items.append(
                    _statement_item(
                        security_id=security_id,
                        dataset=dataset,
                        snapshot_hash=snapshot.payload_hash,
                        outcome=counter,
                        error_classification="target_period_missing",
                    )
                )
            else:
                heartbeat.final_transition(
                    store.complete_job_with_followups,
                    job["id"],
                    worker,
                    {
                        "outcome": "snapshot_reused" if same_refresh else "statement_persisted",
                        "snapshot_hash": snapshot.payload_hash,
                    },
                    (followup,),
                )
                counters["statements_succeeded"] += 1
                items.append(
                    _statement_item(
                        security_id=security_id,
                        dataset=dataset,
                        snapshot_hash=snapshot.payload_hash,
                        outcome="snapshot_reused" if same_refresh else "statement_succeeded",
                    )
                )
            heartbeat.close()
            feature_sets_written += _process_feature_jobs(
                root=data_root,
                store=store,
                snapshots=snapshots,
                context=context,
                logical_now_utc=logical_now_utc,
                worker_id=worker,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                items=items,
            )
        except _LeaseLostError:
            item_data: dict[str, object] = {
                "outcome": "lease_lost",
                "error_classification": "lease_lost",
            }
            if security_id is not None:
                item_data["security_id"] = security_id
            if dataset is not None:
                item_data["dataset"] = dataset
            items.append(MappingProxyType(item_data))
            break
        except (SourceBlocked, RetryableSourceError, TerminalSourceError):
            raise
        except BaseException:
            # Unexpected local errors are allowed to surface only after the owned
            # job is safely transitioned when its lease is still valid.
            try:
                heartbeat.final_transition(
                    store.fail_job_with_followups,
                    job["id"],
                    worker,
                    {"error_classification": "worker_error"},
                    False,
                    None,
                    (),
                )
            except ValueError:
                pass
            raise
        finally:
            heartbeat.close()

    return DeepRunSummary(
        expanded,
        superseded,
        counters["remote_attempts"],
        counters["snapshots_reused"],
        counters["statements_succeeded"],
        counters["retryable_failed"],
        counters["terminal_failed"],
        feature_sets_written,
        tuple(circuits),
        tuple(items),
    )


def _validate_run_inputs(
    *,
    root: str | Path,
    store: StateStore,
    source: FinancialStatementSource | None,
    snapshots: SnapshotRepository,
    now_cn: datetime,
    online: bool,
    limit: int,
    worker_id: str,
    lease_seconds: int,
    heartbeat_seconds: float,
) -> tuple[Path, datetime, str]:
    data_root = Path(root).resolve()
    if not isinstance(store, StateStore):
        raise TypeError("store must be StateStore")
    if not isinstance(snapshots, SnapshotRepository):
        raise TypeError("snapshots must be SnapshotRepository")
    if snapshots.data_root.resolve() != data_root:
        raise ValueError("snapshot repository root must match deep data root")
    if Path(store.db_path).resolve().parent != data_root:
        raise ValueError("state store database must be inside the deep data root")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 360:
        raise ValueError("limit must be between 1 and 360")
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
        raise ValueError("lease_seconds must be a positive integer")
    if (
        isinstance(heartbeat_seconds, bool)
        or not isinstance(heartbeat_seconds, (int, float))
        or not math.isfinite(float(heartbeat_seconds))
        or heartbeat_seconds <= 0
        or heartbeat_seconds >= lease_seconds
    ):
        raise ValueError("heartbeat_seconds must be finite, positive, and below lease_seconds")
    if not isinstance(now_cn, datetime) or now_cn.tzinfo is None:
        raise ValueError("now_cn must be timezone-aware Asia/Shanghai time")
    if getattr(now_cn.tzinfo, "key", None) != "Asia/Shanghai":
        raise ValueError("now_cn must use the Asia/Shanghai timezone")
    normalized_now = now_cn.astimezone(SHANGHAI)
    if not isinstance(online, bool):
        raise TypeError("online must be boolean")
    if online and source is None:
        raise ValueError("online deep execution requires an explicit source")
    worker = _require_nonempty_text(worker_id, "worker_id")
    return data_root, normalized_now, worker


def run_deep(
    root: str | Path,
    store: StateStore,
    *,
    source: FinancialStatementSource | None,
    snapshots: SnapshotRepository,
    trade_calendar_snapshot: SnapshotRef | None,
    now_cn: datetime,
    online: bool,
    limit: int,
    worker_id: str = "deep-worker",
    lease_seconds: int = 900,
    heartbeat_seconds: float = 60.0,
) -> DeepRunSummary:
    data_root, normalized_now, worker = _validate_run_inputs(
        root=root,
        store=store,
        source=source,
        snapshots=snapshots,
        now_cn=now_cn,
        online=online,
        limit=limit,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
    )
    context = load_candidate_context(data_root)
    if trade_calendar_snapshot is not None:
        if not isinstance(trade_calendar_snapshot, SnapshotRef):
            raise TypeError("trade_calendar_snapshot must be SnapshotRef or None")
        _verified_calendar_days(snapshots, trade_calendar_snapshot)
    now_utc = normalized_now.astimezone(timezone.utc).isoformat()
    store.recover_expired_leases(now_utc)
    planning = expand_deep_parents(
        store,
        context,
        as_of_cn_date=normalized_now.date().isoformat(),
        worker_id=worker,
    )
    return execute_queued_deep_work(
        root=data_root,
        store=store,
        context=context,
        source=source,
        snapshots=snapshots,
        trade_calendar_snapshot=trade_calendar_snapshot,
        now_cn=normalized_now,
        online=online,
        limit=limit,
        worker_id=worker,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        planning=planning,
    )
