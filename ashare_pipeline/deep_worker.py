"""Deterministic candidate context and legacy deep-job expansion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping, Sequence

from ashare_pipeline.feature_contract import canonical_json_bytes, canonical_sha256
from ashare_pipeline.financial_schema import FINANCIAL_REQUEST_VERSION
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
