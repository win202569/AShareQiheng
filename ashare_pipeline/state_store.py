"""SQLite-backed state transitions for resumable pipeline work."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Iterable, Iterator, Mapping, Sequence

from ashare_pipeline.feature_contract import (
    DIMENSIONS,
    FINANCIAL_DIMENSIONS,
    FINANCIAL_PERIODS,
    EvidenceRef,
    FeatureBundle,
    canonical_sha256,
    financial_projection_values,
)
from ashare_pipeline.financial_features import (
    feature_input_hash,
    validate_feature_calendar_request,
)
from ashare_pipeline.financial_formulas import (
    DERIVED_FORMULA_SPECS,
    FormulaFact,
    evaluate_derived_financial,
)
from ashare_pipeline.financial_schema import (
    DATASET_TO_STATEMENT,
    FINANCIAL_REQUEST_VERSION,
    MAPPING_VERSION,
    FinancialFact,
    balance_equation_blockers,
    raw_financial_slot_descriptor,
)


JOB_STATES = {"pending", "running", "succeeded", "retryable_failed", "terminal_failed"}
SCORE_RUN_STATES = {"provisional", "final", "invalidated"}
SCORE_ITEM_STATES = {"pending", "partial", "ready", "blocked", "final"}
RUN_STATES = {"running", "succeeded", "failed", "cancelled"}
_OWNED_JOB_KINDS = frozenset({"deep_financial", "deep_statement", "feature_build"})
SCHEMA_VERSION = 5
_EVIDENCE_QUERY_BATCH_SIZE = 256
_STATEMENT_DATASETS = ("balance_sheet", "profit_sheet", "cash_flow_sheet")
_SHANGHAI = timezone(timedelta(hours=8))
_RECONCILIATION_PRE_MIDNIGHT_WINDOW = timedelta(minutes=5)
_RECONCILIATION_CROSS_MIDNIGHT_GRACE = timedelta(seconds=15)
_RECONCILIATION_STATEMENT_PAYLOAD_KEYS = frozenset(
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
_RECONCILIATION_FEATURE_PAYLOAD_KEYS = frozenset(
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
_FROZEN_STATEMENT_SNAPSHOT_KEYS = frozenset(
    {"source_snapshot_id", "payload_hash"}
)
_FROZEN_CALENDAR_SNAPSHOT_KEYS = frozenset(
    {
        "source_snapshot_id",
        "payload_hash",
        "source",
        "dataset",
        "request",
        "request_fingerprint",
    }
)

FINANCIAL_FACT_COLUMNS = (
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
    "announced_at_utc",
    "effective_at_utc",
    "source_updated_at_utc",
    "source_snapshot_id",
    "source_field",
    "raw_row_hash",
    "mapping_version",
    "created_at",
)

_FEATURE_SET_CONTENT_COLUMNS = (
    "security_id",
    "report_period",
    "as_of_utc",
    "candidate_set_hash",
    "template_id",
    "template_version",
    "contract_version",
    "input_hash",
    "status",
    "financial_coverage",
    "dimension_status_json",
    "confidence_inputs_json",
    "blockers_json",
    "bundle_hash",
    "missing_json",
)

_FEATURE_VALUE_CONTENT_COLUMNS = (
    "dimension",
    "feature_key",
    "period_key",
    "value",
    "unit",
    "status",
    "formula_version",
    "evidence_json",
    "missing_reason",
)

_V2_TABLE_DDL = {
    "run": """CREATE TABLE IF NOT EXISTS run (
        id TEXT PRIMARY KEY, mode TEXT NOT NULL, as_of_cn TEXT NOT NULL,
        params_json TEXT NOT NULL, status TEXT NOT NULL,
        error TEXT, started_at TEXT NOT NULL, finished_at TEXT
    )""",
    "job": """CREATE TABLE IF NOT EXISTS job (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
        payload_json TEXT NOT NULL, status TEXT NOT NULL,
        lease_worker TEXT, lease_expires_at TEXT, next_retry_at TEXT,
        result_json TEXT, last_error_json TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        CHECK (status IN ('pending','running','succeeded','retryable_failed','terminal_failed'))
    )""",
    "artifact": """CREATE TABLE IF NOT EXISTS artifact (
        id TEXT PRIMARY KEY, run_id TEXT REFERENCES run(id), kind TEXT NOT NULL,
        payload_hash TEXT NOT NULL, path TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(run_id, kind, payload_hash)
    )""",
    "source_snapshot": """CREATE TABLE IF NOT EXISTS source_snapshot (
        id TEXT PRIMARY KEY, source TEXT NOT NULL, dataset TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL, payload_hash TEXT NOT NULL,
        payload_path TEXT NOT NULL, row_count INTEGER NOT NULL, fetched_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(source, dataset, request_fingerprint, payload_hash)
    )""",
    "score_run": """CREATE TABLE IF NOT EXISTS score_run (
        id TEXT PRIMARY KEY, report_period TEXT NOT NULL, as_of_cn TEXT NOT NULL,
        ruleset_hash TEXT NOT NULL, universe_hash TEXT NOT NULL, mode TEXT NOT NULL,
        status TEXT NOT NULL, created_at TEXT NOT NULL, finalized_at TEXT,
        cutoff_utc TEXT, market_ready INTEGER, quality_passed INTEGER,
        market_evidence_json TEXT, quality_evidence_json TEXT,
        CHECK (status IN ('provisional','final','invalidated'))
    )""",
    "score_item": """CREATE TABLE IF NOT EXISTS score_item (
        score_run_id TEXT NOT NULL REFERENCES score_run(id), security_id TEXT NOT NULL,
        state TEXT NOT NULL, coverage REAL NOT NULL, input_hash TEXT NOT NULL,
        scores_json TEXT, reasons_json TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(score_run_id, security_id),
        CHECK (state IN ('pending','partial','ready','blocked','final')),
        CHECK (coverage >= 0 AND coverage <= 1)
    )""",
    "quality_issue": """CREATE TABLE IF NOT EXISTS quality_issue (
        id TEXT PRIMARY KEY, run_id TEXT REFERENCES run(id), score_run_id TEXT REFERENCES score_run(id),
        severity TEXT NOT NULL, code TEXT NOT NULL, details_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
}

_V2_INDEX_DDL = {
    "job_lease_idx": "CREATE INDEX IF NOT EXISTS job_lease_idx ON job(kind, status, next_retry_at)",
}

_MIGRATION_TABLE_DDL = """CREATE TABLE IF NOT EXISTS schema_migration(
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
)"""

_V3_TABLE_DDL = {
    "financial_fact": """CREATE TABLE IF NOT EXISTS financial_fact(
        id TEXT PRIMARY KEY,
        security_id TEXT NOT NULL,
        statement TEXT NOT NULL CHECK(statement IN('income','balance','cash_flow')),
        metric_key TEXT NOT NULL,
        period_start TEXT,
        period_end TEXT NOT NULL,
        period_kind TEXT NOT NULL CHECK(period_kind IN('FY','H1','Q1','Q3','OTHER')),
        value REAL NOT NULL CHECK(value BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308),
        unit TEXT NOT NULL CHECK(unit IN('CNY','shares','ratio','CNY_per_share')),
        nature TEXT NOT NULL CHECK(nature IN('instant','duration')),
        announced_at_utc TEXT NOT NULL,
        effective_at_utc TEXT NOT NULL,
        source_updated_at_utc TEXT,
        source_snapshot_id TEXT NOT NULL REFERENCES source_snapshot(id),
        source_field TEXT NOT NULL,
        raw_row_hash TEXT NOT NULL,
        mapping_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK((nature='instant' AND period_start IS NULL) OR
              (nature='duration' AND period_start IS NOT NULL))
    )""",
    "feature_set": """CREATE TABLE IF NOT EXISTS feature_set(
        id TEXT PRIMARY KEY,
        security_id TEXT NOT NULL,
        report_period TEXT NOT NULL,
        as_of_utc TEXT NOT NULL,
        candidate_set_hash TEXT NOT NULL,
        template_id TEXT NOT NULL,
        template_version TEXT NOT NULL,
        contract_version TEXT NOT NULL,
        input_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN('partial','financial_ready','blocked')),
        financial_coverage REAL NOT NULL CHECK(financial_coverage>=0 AND financial_coverage<=1),
        dimension_status_json TEXT NOT NULL,
        confidence_inputs_json TEXT NOT NULL,
        blockers_json TEXT NOT NULL,
        bundle_hash TEXT NOT NULL UNIQUE,
        bundle_path TEXT NOT NULL,
        missing_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(security_id,report_period,as_of_utc,input_hash)
    )""",
    "feature_value": """CREATE TABLE IF NOT EXISTS feature_value(
        feature_set_id TEXT NOT NULL REFERENCES feature_set(id) ON DELETE CASCADE,
        dimension TEXT NOT NULL CHECK(dimension IN('G','V','M','EQ','FS','CA','T')),
        feature_key TEXT NOT NULL,
        period_key TEXT NOT NULL,
        value REAL,
        unit TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN('observed','derived','missing','not_applicable','blocked')),
        formula_version TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        missing_reason TEXT,
        PRIMARY KEY(feature_set_id,dimension,feature_key,period_key),
        CHECK(value IS NULL OR value BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308),
        CHECK((status IN('observed','derived') AND value IS NOT NULL AND missing_reason IS NULL)
           OR (status IN('missing','not_applicable','blocked') AND value IS NULL AND missing_reason IS NOT NULL))
    )""",
}

_V3_INDEX_DDL = {
    "financial_fact_lookup_idx": """CREATE INDEX IF NOT EXISTS financial_fact_lookup_idx
        ON financial_fact(security_id,metric_key,period_end,effective_at_utc)""",
    "financial_fact_snapshot_idx": """CREATE INDEX IF NOT EXISTS financial_fact_snapshot_idx
        ON financial_fact(source_snapshot_id)""",
    "feature_set_latest_idx": """CREATE INDEX IF NOT EXISTS feature_set_latest_idx
        ON feature_set(security_id,report_period,contract_version,as_of_utc DESC,created_at DESC)""",
}

_V4_TABLE_DDL = {
    "quality_issue_binding": """CREATE TABLE IF NOT EXISTS quality_issue_binding(
        issue_id TEXT PRIMARY KEY REFERENCES quality_issue(id),
        job_id TEXT NOT NULL REFERENCES job(id),
        source_snapshot_id TEXT NOT NULL REFERENCES source_snapshot(id)
    )""",
}

_V4_INDEX_DDL: dict[str, str] = {}

_V5_TABLE_DDL = {
    "formal_collection_task": """CREATE TABLE IF NOT EXISTS formal_collection_task(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        refresh_generation TEXT NOT NULL CHECK(refresh_generation<>''),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN(
            'pending','leased','verified','retryable_failed','terminal_failed','superseded'
        )),
        lease_worker TEXT,
        lease_expires_at TEXT,
        next_retry_at TEXT,
        result_json TEXT,
        error_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "formal_source_snapshot": """CREATE TABLE IF NOT EXISTS formal_source_snapshot(
        id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        dataset TEXT NOT NULL,
        request_json TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL UNIQUE,
        content_path TEXT NOT NULL,
        manifest_path TEXT NOT NULL,
        original_url TEXT NOT NULL,
        published_at_utc TEXT NOT NULL,
        published_precision TEXT NOT NULL CHECK(published_precision IN('timestamp','date_only')),
        source_updated_at_utc TEXT,
        captured_at_utc TEXT NOT NULL,
        effective_at_utc TEXT NOT NULL,
        effective_time_evidence_hash TEXT,
        parser_id TEXT NOT NULL,
        parser_version TEXT NOT NULL,
        mapping_version TEXT NOT NULL,
        refresh_generation TEXT NOT NULL CHECK(refresh_generation<>''),
        producing_task_id TEXT REFERENCES formal_collection_task(id),
        verification_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    "formal_task_snapshot_receipt": """CREATE TABLE IF NOT EXISTS formal_task_snapshot_receipt(
        task_id TEXT PRIMARY KEY REFERENCES formal_collection_task(id),
        snapshot_id TEXT NOT NULL UNIQUE REFERENCES formal_source_snapshot(id),
        manifest_sha256 TEXT NOT NULL UNIQUE,
        refresh_generation TEXT NOT NULL CHECK(refresh_generation<>''),
        recorded_at TEXT NOT NULL
    )""",
    "formal_universe_snapshot": """CREATE TABLE IF NOT EXISTS formal_universe_snapshot(
        id TEXT PRIMARY KEY,
        as_of_utc TEXT NOT NULL,
        registry_manifest_hash TEXT NOT NULL,
        universe_hash TEXT NOT NULL,
        source_audit_hash TEXT NOT NULL,
        frozen_input_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )""",
    "formal_universe_source": """CREATE TABLE IF NOT EXISTS formal_universe_source(
        universe_snapshot_id TEXT NOT NULL REFERENCES formal_universe_snapshot(id),
        exchange TEXT NOT NULL CHECK(exchange IN('SH','SZ','BJ')),
        source_snapshot_id TEXT NOT NULL REFERENCES formal_source_snapshot(id),
        manifest_sha256 TEXT NOT NULL,
        source_content_sha256 TEXT NOT NULL,
        parser_id TEXT NOT NULL,
        parser_version TEXT NOT NULL,
        extraction_audit_hash TEXT NOT NULL,
        extraction_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(universe_snapshot_id,exchange)
    )""",
    "formal_universe_member": """CREATE TABLE IF NOT EXISTS formal_universe_member(
        snapshot_id TEXT NOT NULL REFERENCES formal_universe_snapshot(id),
        security_id TEXT NOT NULL,
        exchange TEXT NOT NULL CHECK(exchange IN('SH','SZ','BJ')),
        code6 TEXT NOT NULL,
        security_type TEXT NOT NULL,
        listing_status TEXT NOT NULL,
        raw_json TEXT NOT NULL,
        PRIMARY KEY(snapshot_id,security_id)
    )""",
    "formal_universe_status": """CREATE TABLE IF NOT EXISTS formal_universe_status(
        snapshot_id TEXT NOT NULL,
        security_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN(
            'out_of_scope','pending_evidence','pool_vetoed','formal_scored'
        )),
        reasons_json TEXT NOT NULL,
        veto_flags_json TEXT NOT NULL,
        evidence_hash TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(snapshot_id,security_id),
        FOREIGN KEY(snapshot_id,security_id)
            REFERENCES formal_universe_member(snapshot_id,security_id)
    )""",
    "formal_collection_task_dependency": """CREATE TABLE IF NOT EXISTS formal_collection_task_dependency(
        task_id TEXT NOT NULL REFERENCES formal_collection_task(id),
        prerequisite_task_id TEXT NOT NULL REFERENCES formal_collection_task(id),
        created_at TEXT NOT NULL,
        PRIMARY KEY(task_id,prerequisite_task_id)
    )""",
}

_V5_INDEX_DDL = {
    "formal_source_snapshot_lineage_idx": """CREATE UNIQUE INDEX IF NOT EXISTS
        formal_source_snapshot_lineage_idx ON formal_source_snapshot(
            request_fingerprint,
            refresh_generation,
            COALESCE(producing_task_id,'bootstrap')
        )""",
    "formal_source_snapshot_exact_request_idx": """CREATE INDEX IF NOT EXISTS
        formal_source_snapshot_exact_request_idx ON formal_source_snapshot(
            source,dataset,request_fingerprint,refresh_generation,created_at DESC
        )""",
}


class FinalizationBlocked(RuntimeError):
    """The final publication gate has not yet been satisfied."""


@dataclass(frozen=True)
class JobSpec:
    kind: str
    idempotency_key: str
    _payload_json: str = field(init=False, repr=False)

    def __init__(
        self,
        kind: str,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> None:
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "_payload_json", _json(payload))

    @property
    def payload(self) -> dict[str, object]:
        return json.loads(self._payload_json)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_iso(value: str | None) -> str:
    if value is None:
        return _utc_now()
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone offset")
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _reconciliation_sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value.lower())
    ):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return value.lower()


def _reconciliation_date(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a canonical ISO date")
    try:
        normalized = date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} must be a canonical ISO date") from error
    if normalized != value:
        raise ValueError(f"{field} must be a canonical ISO date")
    return normalized


def _validate_reconciliation_statement_identity(
    payload: Mapping[str, object], idempotency_key: str
) -> tuple[str, str, str, str]:
    if set(payload) != _RECONCILIATION_STATEMENT_PAYLOAD_KEYS:
        raise ValueError("reconciliation statement payload is not canonical")
    security_id = payload["security_id"]
    if (
        not isinstance(security_id, str)
        or len(security_id) != 8
        or security_id[:2] not in {"SH", "SZ"}
        or not security_id[2:].isdigit()
    ):
        raise ValueError("reconciliation statement security is invalid")
    dataset = payload["dataset"]
    if dataset not in DATASET_TO_STATEMENT:
        raise ValueError("reconciliation statement dataset is invalid")
    report_period = _reconciliation_date(
        payload["report_period"], "report_period"
    )
    refresh_date = _reconciliation_date(payload["refresh_date"], "refresh_date")
    _reconciliation_sha256(payload["candidate_set_hash"], "candidate_set_hash")
    _reconciliation_sha256(
        payload["performance_input_hash"], "performance_input_hash"
    )
    if payload["request_version"] != FINANCIAL_REQUEST_VERSION:
        raise ValueError("reconciliation statement request version is invalid")
    expected_key = (
        f"deep_statement:v1:{security_id}:{dataset}:{report_period}:{refresh_date}"
    )
    if idempotency_key != expected_key:
        raise ValueError("reconciliation statement key is not canonical")
    return security_id, dataset, report_period, refresh_date


def _reconciliation_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} is not canonical")
    try:
        return datetime.fromisoformat(_utc_iso(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} is not canonical") from error


def reconciliation_snapshot_matches_job_refresh_date(
    *,
    snapshot_fetched_at: object,
    refresh_date: object,
    job_created_at: object,
    job_updated_at: object,
) -> bool:
    """Permit a tightly proven source fetch that crossed Shanghai midnight."""
    refresh_day = date.fromisoformat(
        _reconciliation_date(refresh_date, "reconciliation refresh_date")
    )
    snapshot_at = _reconciliation_timestamp(
        snapshot_fetched_at, "reconciliation snapshot fetched_at"
    )
    snapshot_cn = snapshot_at.astimezone(_SHANGHAI)
    if snapshot_cn.date() == refresh_day:
        return True

    next_day = refresh_day + timedelta(days=1)
    if snapshot_cn.date() != next_day:
        return False
    job_started_at = _reconciliation_timestamp(
        job_created_at, "reconciliation job created_at"
    )
    job_finished_at = _reconciliation_timestamp(
        job_updated_at, "reconciliation job updated_at"
    )
    next_midnight = datetime.combine(next_day, datetime.min.time(), tzinfo=_SHANGHAI)
    deadline = next_midnight + _RECONCILIATION_CROSS_MIDNIGHT_GRACE
    if not (
        next_midnight - _RECONCILIATION_PRE_MIDNIGHT_WINDOW
        <= job_started_at.astimezone(_SHANGHAI)
        < next_midnight
        <= snapshot_cn
        <= deadline
        and job_started_at <= snapshot_at <= job_finished_at <= deadline
    ):
        return False
    return True


def _validate_cross_midnight_reconciliation_chronology(
    *,
    snapshot_fetched_at: object,
    snapshot_created_at: object,
    quality_issue_created_at: object,
    refresh_date: object,
    job_created_at: object,
    job_updated_at: object,
) -> None:
    refresh_day = date.fromisoformat(
        _reconciliation_date(refresh_date, "reconciliation refresh_date")
    )
    snapshot_at = _reconciliation_timestamp(
        snapshot_fetched_at, "reconciliation snapshot fetched_at"
    )
    if snapshot_at.astimezone(_SHANGHAI).date() == refresh_day:
        return
    if not reconciliation_snapshot_matches_job_refresh_date(
        snapshot_fetched_at=snapshot_fetched_at,
        refresh_date=refresh_date,
        job_created_at=job_created_at,
        job_updated_at=job_updated_at,
    ):
        raise ValueError("reconciliation snapshot refresh date is invalid")
    snapshot_created_at = _reconciliation_timestamp(
        snapshot_created_at, "reconciliation snapshot created_at"
    )
    issue_created_at = _reconciliation_timestamp(
        quality_issue_created_at, "reconciliation quality issue created_at"
    )
    job_finished_at = _reconciliation_timestamp(
        job_updated_at, "reconciliation job updated_at"
    )
    if not snapshot_at <= snapshot_created_at <= issue_created_at <= job_finished_at:
        raise ValueError("reconciliation cross-midnight chronology is invalid")


def _require_reconciliation_snapshot(
    connection: sqlite3.Connection,
    *,
    snapshot_id: str,
    source: str,
    dataset: str,
    request_fingerprint: str,
    payload_hash: str,
    label: str,
) -> sqlite3.Row:
    row = connection.execute(
        """SELECT source,dataset,request_fingerprint,payload_hash,fetched_at
        FROM source_snapshot WHERE id = ?""",
        (snapshot_id,),
    ).fetchone()
    if row is None or (
        row["source"] != source
        or row["dataset"] != dataset
        or row["request_fingerprint"] != request_fingerprint
        or row["payload_hash"] != payload_hash
    ):
        raise ValueError(f"reconciliation follow-up {label} snapshot identity is invalid")
    return row


def _validate_reconciliation_sibling_job(
    connection: sqlite3.Connection,
    *,
    statement_payload: Mapping[str, object],
    dataset: str,
    snapshot_hash: str,
) -> None:
    sibling_payload = dict(statement_payload)
    sibling_payload["dataset"] = dataset
    sibling_key = (
        f"deep_statement:v1:{statement_payload['security_id']}:{dataset}:"
        f"{statement_payload['report_period']}:{statement_payload['refresh_date']}"
    )
    row = connection.execute(
        """SELECT kind,payload_json,status,result_json FROM job
        WHERE idempotency_key = ?""",
        (sibling_key,),
    ).fetchone()
    normal_results = {
        _json({"outcome": outcome, "snapshot_hash": snapshot_hash})
        for outcome in ("snapshot_reused", "statement_persisted")
    }
    legacy_result = _json(
        {
            "outcome": "reconciled_verified_snapshot",
            "snapshot_hash": snapshot_hash,
            "mapping_version": MAPPING_VERSION,
            "recovered_error": "malformed_statement",
        }
    )
    if row is None or (
        row["kind"] != "deep_statement"
        or row["payload_json"] != _json(sibling_payload)
        or row["status"] != "succeeded"
        or row["result_json"] not in normal_results | {legacy_result}
    ):
        raise ValueError(
            "reconciliation follow-up sibling statement job is not canonical"
        )


def _validate_reconciliation_followup(
    connection: sqlite3.Connection,
    followup: JobSpec,
    *,
    statement_payload: Mapping[str, object],
    source_snapshot_id: str,
    source_snapshot_hash: str,
    reconciliation_job_created_at: object,
    reconciliation_job_updated_at: object,
) -> None:
    if followup.kind != "feature_build":
        raise ValueError("reconciliation follow-up must be feature_build")
    payload = followup.payload
    if set(payload) != _RECONCILIATION_FEATURE_PAYLOAD_KEYS:
        raise ValueError("reconciliation follow-up payload is not canonical")
    for field in (
        "security_id",
        "report_period",
        "candidate_set_hash",
        "performance_input_hash",
    ):
        if payload[field] != statement_payload[field]:
            raise ValueError(
                "reconciliation follow-up does not match statement identity"
            )
    if not isinstance(payload["as_of_utc"], str):
        raise ValueError(
            "reconciliation follow-up as_of_utc is not canonical"
        )
    as_of = _reconciliation_timestamp(
        payload["as_of_utc"], "reconciliation follow-up as_of_utc"
    )
    normalized_as_of = as_of.isoformat()
    industry = payload["industry"]
    if not isinstance(industry, str) or not industry.strip():
        raise ValueError("reconciliation follow-up industry is invalid")
    if not isinstance(payload["reported_target_period"], bool):
        raise ValueError(
            "reconciliation follow-up reported_target_period is invalid"
        )
    statement_snapshots = payload["statement_snapshots"]
    if (
        not isinstance(statement_snapshots, Mapping)
        or set(statement_snapshots) != set(_STATEMENT_DATASETS)
    ):
        raise ValueError("reconciliation follow-up snapshots are not canonical")
    statement_hashes: dict[str, str | None] = {}
    seen_snapshot_ids: set[str] = set()
    statement_fingerprint = canonical_sha256(
        {
            "symbol": statement_payload["security_id"],
            "report_period": statement_payload["report_period"],
        }
    )
    for dataset in _STATEMENT_DATASETS:
        value = statement_snapshots[dataset]
        if value is None:
            statement_hashes[dataset] = None
            continue
        if (
            not isinstance(value, Mapping)
            or set(value) != _FROZEN_STATEMENT_SNAPSHOT_KEYS
            or not isinstance(value["source_snapshot_id"], str)
            or not value["source_snapshot_id"]
        ):
            raise ValueError("reconciliation follow-up snapshots are not canonical")
        snapshot_id = value["source_snapshot_id"]
        if snapshot_id in seen_snapshot_ids:
            raise ValueError(
                "reconciliation follow-up snapshot occupies multiple slots"
            )
        seen_snapshot_ids.add(snapshot_id)
        snapshot_hash = _reconciliation_sha256(
            value["payload_hash"], "statement snapshot hash"
        )
        statement_hashes[dataset] = snapshot_hash
        snapshot = _require_reconciliation_snapshot(
            connection,
            snapshot_id=snapshot_id,
            source="akshare",
            dataset=dataset,
            request_fingerprint=statement_fingerprint,
            payload_hash=snapshot_hash,
            label="statement",
        )
        fetched_at = _reconciliation_timestamp(
            snapshot["fetched_at"], "reconciliation statement snapshot fetched_at"
        )
        if fetched_at > as_of:
            raise ValueError(
                "reconciliation follow-up statement snapshot is newer than as_of_utc"
            )
        is_recovered_snapshot = (
            dataset == statement_payload["dataset"]
            and snapshot_id == source_snapshot_id
            and snapshot_hash == source_snapshot_hash
        )
        if is_recovered_snapshot:
            refresh_date_matches = reconciliation_snapshot_matches_job_refresh_date(
                snapshot_fetched_at=snapshot["fetched_at"],
                refresh_date=statement_payload["refresh_date"],
                job_created_at=reconciliation_job_created_at,
                job_updated_at=reconciliation_job_updated_at,
            )
        else:
            refresh_date_matches = (
                fetched_at.astimezone(_SHANGHAI).date().isoformat()
                == statement_payload["refresh_date"]
            )
        if not refresh_date_matches:
            raise ValueError(
                "reconciliation follow-up statement snapshot refresh date is invalid"
            )
        if dataset != statement_payload["dataset"]:
            _validate_reconciliation_sibling_job(
                connection,
                statement_payload=statement_payload,
                dataset=dataset,
                snapshot_hash=snapshot_hash,
            )
    recovered = statement_snapshots[statement_payload["dataset"]]
    if (
        not isinstance(recovered, Mapping)
        or recovered["source_snapshot_id"] != source_snapshot_id
        or recovered["payload_hash"] != source_snapshot_hash
    ):
        raise ValueError(
            "reconciliation follow-up does not bind the recovered snapshot"
        )
    calendar = payload["trade_calendar_snapshot"]
    if (
        isinstance(calendar, Mapping)
        and set(calendar) == _FROZEN_CALENDAR_SNAPSHOT_KEYS
        and isinstance(calendar["source_snapshot_id"], str)
        and bool(calendar["source_snapshot_id"])
        and calendar["source"] == "baostock"
        and calendar["dataset"] == "trade_dates"
    ):
        calendar_hash = _reconciliation_sha256(
            calendar["payload_hash"], "trade calendar snapshot hash"
        )
        calendar_request = validate_feature_calendar_request(
            calendar["request"]
        )
        if dict(calendar["request"]) != calendar_request:
            raise ValueError(
                "reconciliation follow-up calendar request is not canonical"
            )
        calendar_fingerprint = _reconciliation_sha256(
            calendar["request_fingerprint"],
            "trade calendar request fingerprint",
        )
        if calendar_fingerprint != canonical_sha256(calendar_request):
            raise ValueError(
                "reconciliation follow-up calendar fingerprint is invalid"
            )
        calendar_snapshot = _require_reconciliation_snapshot(
            connection,
            snapshot_id=calendar["source_snapshot_id"],
            source="baostock",
            dataset="trade_dates",
            request_fingerprint=calendar_fingerprint,
            payload_hash=calendar_hash,
            label="calendar",
        )
        calendar_fetched_at = _reconciliation_timestamp(
            calendar_snapshot["fetched_at"],
            "reconciliation calendar snapshot fetched_at",
        )
        if calendar_fetched_at > as_of:
            raise ValueError(
                "reconciliation follow-up calendar snapshot is newer than as_of_utc"
            )
    else:
        raise ValueError(
            "reconciliation follow-up calendar is required and must be canonical"
        )
    input_hash = feature_input_hash(
        security_id=payload["security_id"],
        report_period=payload["report_period"],
        as_of_utc=normalized_as_of,
        candidate_set_hash=payload["candidate_set_hash"],
        statement_snapshot_hashes=statement_hashes,
        trade_calendar_snapshot_hash=calendar_hash,
    )
    expected_key = (
        f"feature_build:v1:{payload['security_id']}:{payload['report_period']}:"
        f"{input_hash}"
    )
    if followup.idempotency_key != expected_key:
        raise ValueError("reconciliation follow-up key is not canonical")


def _legacy_malformed_statement_job_ids(
    connection: sqlite3.Connection,
    *,
    security_id: str,
    dataset: str,
) -> tuple[str, ...]:
    malformed_error_json = _json(
        {"error_classification": "malformed_statement"}
    )
    matching_jobs: list[str] = []
    for candidate in connection.execute(
        """SELECT id,payload_json FROM job
        WHERE kind='deep_statement' AND status='terminal_failed'
        AND last_error_json=? ORDER BY id""",
        (malformed_error_json,),
    ):
        try:
            candidate_payload = json.loads(candidate["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            isinstance(candidate_payload, Mapping)
            and candidate_payload.get("security_id") == security_id
            and candidate_payload.get("dataset") == dataset
        ):
            matching_jobs.append(str(candidate["id"]))
    return tuple(matching_jobs)


def _legacy_issue_falls_within_job_lifetime(
    connection: sqlite3.Connection,
    *,
    issue_id: str,
    job_id: str,
) -> bool:
    row = connection.execute(
        """SELECT issue.created_at AS issue_created_at,
        job.created_at AS job_created_at,job.updated_at AS job_updated_at
        FROM quality_issue AS issue JOIN job ON job.id=? WHERE issue.id=?""",
        (job_id, issue_id),
    ).fetchone()
    if row is None:
        return False
    try:
        issue_created_at = _reconciliation_timestamp(
            row["issue_created_at"], "legacy quality issue created_at"
        )
        job_created_at = _reconciliation_timestamp(
            row["job_created_at"], "legacy reconciliation job created_at"
        )
        job_updated_at = _reconciliation_timestamp(
            row["job_updated_at"], "legacy reconciliation job updated_at"
        )
    except ValueError:
        return False
    return job_created_at <= issue_created_at <= job_updated_at


def _validate_and_bind_reconciliation_issue(
    connection: sqlite3.Connection,
    *,
    issue_id: str,
    issue_details: Mapping[str, object],
    job_id: str,
    source_snapshot_id: str,
    security_id: str,
    dataset: str,
    facts: Sequence[FinancialFact],
    refresh_date: str,
    snapshot_fetched_at: object,
    snapshot_created_at: object,
    job_created_at: object,
    job_updated_at: object,
) -> None:
    if not isinstance(issue_id, str) or not issue_id:
        raise ValueError("reconciliation quality issue id is invalid")
    if not isinstance(issue_details, Mapping):
        raise ValueError("reconciliation quality issue details are invalid")
    details_json = _json(dict(issue_details))
    row = connection.execute(
        """SELECT issue.created_at AS issue_created_at,
        binding.job_id,binding.source_snapshot_id
        FROM quality_issue AS issue
        LEFT JOIN quality_issue_binding AS binding ON binding.issue_id=issue.id
        WHERE issue.id=? AND issue.severity='error'
        AND issue.code='statement_report_date_invalid'
        AND issue.details_json=?""",
        (issue_id, details_json),
    ).fetchone()
    if row is None:
        raise ValueError("reconciliation quality issue does not match exact evidence")
    nested = issue_details.get("details")
    if (
        issue_details.get("security_id") != security_id
        or issue_details.get("dataset") != dataset
        or not isinstance(nested, Mapping)
        or nested.get("security_id") != security_id
    ):
        raise ValueError("reconciliation quality issue identity is invalid")
    row_hash = nested.get("row_hash")
    if not isinstance(row_hash, str) or row_hash not in {
        fact.raw_row_hash for fact in facts
    }:
        raise ValueError(
            "reconciliation quality issue row hash does not belong to facts"
        )
    _validate_cross_midnight_reconciliation_chronology(
        snapshot_fetched_at=snapshot_fetched_at,
        snapshot_created_at=snapshot_created_at,
        quality_issue_created_at=row["issue_created_at"],
        refresh_date=refresh_date,
        job_created_at=job_created_at,
        job_updated_at=job_updated_at,
    )

    bound_job_id = row["job_id"]
    bound_snapshot_id = row["source_snapshot_id"]
    if bound_job_id is not None or bound_snapshot_id is not None:
        if (
            bound_job_id != job_id
            or bound_snapshot_id != source_snapshot_id
        ):
            raise ValueError(
                "reconciliation quality issue binding does not match job and snapshot"
            )
        return

    unbound = connection.execute(
        """SELECT issue.id FROM quality_issue AS issue
        LEFT JOIN quality_issue_binding AS binding ON binding.issue_id=issue.id
        WHERE issue.severity='error'
        AND issue.code='statement_report_date_invalid'
        AND issue.details_json=? AND binding.issue_id IS NULL
        ORDER BY issue.id""",
        (details_json,),
    ).fetchall()
    if tuple(str(candidate["id"]) for candidate in unbound) != (issue_id,):
        raise ValueError(
            "legacy quality issue is not the unique unbound exact match"
        )
    conflicting_bound = connection.execute(
        """SELECT 1 FROM quality_issue AS issue
        JOIN quality_issue_binding AS binding ON binding.issue_id=issue.id
        WHERE issue.severity='error' AND issue.code='statement_report_date_invalid'
        AND issue.details_json=? LIMIT 1""",
        (details_json,),
    ).fetchone()
    if conflicting_bound is not None:
        raise ValueError(
            "legacy quality issue has conflicting bound provenance"
        )

    if _legacy_malformed_statement_job_ids(
        connection, security_id=security_id, dataset=dataset
    ) != (job_id,):
        raise ValueError(
            "legacy quality issue does not have a unique malformed statement job"
        )
    if not _legacy_issue_falls_within_job_lifetime(
        connection, issue_id=issue_id, job_id=job_id
    ):
        raise ValueError(
            "legacy quality issue does not fall within current job lifetime"
        )
    connection.execute(
        """INSERT INTO quality_issue_binding
        (issue_id,job_id,source_snapshot_id) VALUES (?,?,?)""",
        (issue_id, job_id, source_snapshot_id),
    )


class StateStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _transaction(
        self,
        immediate: bool = False,
        on_error: Callable[[sqlite3.Connection], None] | None = None,
    ) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        begun = False
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            begun = True
            yield connection
            connection.commit()
        except BaseException as error:
            if begun:
                try:
                    if on_error is not None:
                        on_error(connection)
                except BaseException as cleanup_error:
                    connection.rollback()
                    raise error from cleanup_error
                connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            tables = self._user_tables(connection)
            if not tables:
                self._create_v2_schema(connection)
                connection.execute(_MIGRATION_TABLE_DDL)
                connection.execute(
                    "INSERT INTO schema_migration(version, applied_at) VALUES (2, ?)",
                    (_utc_now(),),
                )
                self._apply_v3_migration(connection)
                self._apply_v4_migration(connection)
                self._apply_v5_migration(connection)
            elif "schema_migration" not in tables:
                if tables != set(_V2_TABLE_DDL):
                    raise RuntimeError("database does not match the complete v2 schema")
                self._assert_v2_schema(connection)
                connection.execute(_MIGRATION_TABLE_DDL)
                connection.execute(
                    "INSERT INTO schema_migration(version, applied_at) VALUES (2, ?)",
                    (_utc_now(),),
                )
                self._apply_v3_migration(connection)
                self._apply_v4_migration(connection)
                self._apply_v5_migration(connection)
            else:
                self._assert_schema_ddl(
                    connection,
                    {"schema_migration": _MIGRATION_TABLE_DDL},
                    {},
                    "migration ledger",
                )
                versions = {
                    int(row[0])
                    for row in connection.execute("SELECT version FROM schema_migration")
                }
                if versions not in ({2}, {2, 3}, {2, 3, 4}, {2, 3, 4, 5}):
                    raise RuntimeError(f"unsupported migration versions: {sorted(versions)}")
                self._assert_v2_schema(connection)
                if versions == {2}:
                    later_tables = tables & (
                        set(_V3_TABLE_DDL) | set(_V4_TABLE_DDL) | set(_V5_TABLE_DDL)
                    )
                    if later_tables:
                        raise RuntimeError(
                            "version-2 ledger has unexpected later tables: "
                            f"{sorted(later_tables)}"
                        )
                    self._apply_v3_migration(connection)
                    self._apply_v4_migration(connection)
                    self._apply_v5_migration(connection)
                elif versions == {2, 3}:
                    self._assert_schema_ddl(
                        connection,
                        _V3_TABLE_DDL,
                        _V3_INDEX_DDL,
                        "v3 schema",
                    )
                    later_tables = tables & (set(_V4_TABLE_DDL) | set(_V5_TABLE_DDL))
                    if later_tables:
                        raise RuntimeError(
                            "version-3 ledger has unexpected v4 tables: "
                            f"{sorted(later_tables)}"
                        )
                    self._apply_v4_migration(connection)
                    self._apply_v5_migration(connection)
                elif versions == {2, 3, 4}:
                    self._assert_schema_ddl(
                        connection,
                        _V3_TABLE_DDL,
                        _V3_INDEX_DDL,
                        "v3 schema",
                    )
                    self._assert_schema_ddl(
                        connection,
                        _V4_TABLE_DDL,
                        _V4_INDEX_DDL,
                        "v4 schema",
                    )
                    partial_v5_tables = tables & set(_V5_TABLE_DDL)
                    if partial_v5_tables:
                        raise RuntimeError(
                            "version-4 ledger has unexpected v5 tables: "
                            f"{sorted(partial_v5_tables)}"
                        )
                    self._apply_v5_migration(connection)
                else:
                    self._assert_schema_ddl(
                        connection,
                        _V3_TABLE_DDL,
                        _V3_INDEX_DDL,
                        "v3 schema",
                    )
                    self._assert_schema_ddl(
                        connection,
                        _V4_TABLE_DDL,
                        _V4_INDEX_DDL,
                        "v4 schema",
                    )
                    self._assert_schema_ddl(
                        connection,
                        _V5_TABLE_DDL,
                        _V5_INDEX_DDL,
                        "v5 schema",
                    )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def owned_job_transaction(
        self,
        job_id: str,
        worker_id: str,
        on_error: Callable[[sqlite3.Connection], None] | None = None,
    ) -> Iterator[sqlite3.Connection]:
        """Fence a mutation with ownership checks at both transaction boundaries."""
        with self._transaction(immediate=True, on_error=on_error) as connection:
            self._require_unexpired_job_owner(
                connection, job_id, worker_id, _utc_now()
            )
            yield connection
            self._require_unexpired_job_owner(
                connection, job_id, worker_id, _utc_now()
            )

    @staticmethod
    def _user_tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"""
            )
        }

    @staticmethod
    def _normalized_ddl(sql: str) -> str:
        tokens: list[str] = []
        index = 0
        while index < len(sql):
            character = sql[index]
            if character.isspace():
                index += 1
                continue
            if character == "'":
                literal_start = index
                index += 1
                while index < len(sql):
                    if sql[index] != "'":
                        index += 1
                        continue
                    if index + 1 < len(sql) and sql[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                tokens.append(sql[literal_start:index])
                continue
            if character.isalnum() or character in "_$":
                token_start = index
                index += 1
                while index < len(sql) and (sql[index].isalnum() or sql[index] in "_$"):
                    index += 1
                tokens.append(sql[token_start:index].lower())
                continue
            tokens.append(character.lower())
            index += 1

        if tokens and tokens[-1] == ";":
            tokens.pop()
        normalized: list[str] = []
        index = 0
        while index < len(tokens):
            if (
                tokens[index:index + 3] == ["if", "not", "exists"]
                and (
                    normalized[-2:] in (["create", "table"], ["create", "index"])
                    or normalized[-3:] == ["create", "unique", "index"]
                )
            ):
                index += 3
                continue
            normalized.append(tokens[index])
            index += 1
        return " ".join(normalized)

    @classmethod
    def _assert_schema_ddl(
        cls,
        connection: sqlite3.Connection,
        table_ddl: dict[str, str],
        index_ddl: dict[str, str],
        label: str,
    ) -> None:
        for object_type, definitions in (("table", table_ddl), ("index", index_ddl)):
            for name, expected_sql in definitions.items():
                row = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
                    (object_type, name),
                ).fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError(f"{label} is missing {object_type} {name}")
                if cls._normalized_ddl(str(row[0])) != cls._normalized_ddl(expected_sql):
                    raise RuntimeError(f"{label} does not exactly match {object_type} {name}")

    @classmethod
    def _create_v2_schema(cls, connection: sqlite3.Connection) -> None:
        for statement in (*_V2_TABLE_DDL.values(), *_V2_INDEX_DDL.values()):
            connection.execute(statement)

    @classmethod
    def _assert_v2_schema(cls, connection: sqlite3.Connection) -> None:
        cls._assert_schema_ddl(connection, _V2_TABLE_DDL, _V2_INDEX_DDL, "v2 schema")

    @classmethod
    def _apply_v3_migration(cls, connection: sqlite3.Connection) -> None:
        for statement in (*_V3_TABLE_DDL.values(), *_V3_INDEX_DDL.values()):
            connection.execute(statement)
        cls._assert_schema_ddl(
            connection,
            _V3_TABLE_DDL,
            _V3_INDEX_DDL,
            "v3 schema",
        )
        connection.execute(
            "INSERT INTO schema_migration(version, applied_at) VALUES (3, ?)",
            (_utc_now(),),
        )

    @classmethod
    def _apply_v4_migration(cls, connection: sqlite3.Connection) -> None:
        for statement in (*_V4_TABLE_DDL.values(), *_V4_INDEX_DDL.values()):
            connection.execute(statement)
        cls._assert_schema_ddl(
            connection,
            _V4_TABLE_DDL,
            _V4_INDEX_DDL,
            "v4 schema",
        )
        connection.execute(
            "INSERT INTO schema_migration(version, applied_at) VALUES (4, ?)",
            (_utc_now(),),
        )

    @classmethod
    def _apply_v5_migration(cls, connection: sqlite3.Connection) -> None:
        for statement in (*_V5_TABLE_DDL.values(), *_V5_INDEX_DDL.values()):
            connection.execute(statement)
        cls._assert_schema_ddl(
            connection,
            _V5_TABLE_DDL,
            _V5_INDEX_DDL,
            "v5 schema",
        )
        connection.execute(
            "INSERT INTO schema_migration(version, applied_at) VALUES (5, ?)",
            (_utc_now(),),
        )

    def start_run(self, mode: str, as_of_cn: str, params: dict) -> str:
        run_id = str(uuid.uuid4())
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO run VALUES (?, ?, ?, ?, 'running', NULL, ?, NULL)",
                (run_id, mode, _utc_iso(as_of_cn), _json(params), _utc_now()),
            )
        return run_id

    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None:
        if status not in RUN_STATES - {"running"}:
            raise ValueError(f"invalid terminal run status: {status}")
        with self._transaction() as connection:
            cursor = connection.execute(
                "UPDATE run SET status = ?, error = ?, finished_at = ? WHERE id = ? AND status = 'running'",
                (status, error, _utc_now(), run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("run does not exist or is already finished")

    def enqueue_job(self, kind: str, idempotency_key: str, payload: dict) -> str:
        job_id = str(uuid.uuid4())
        now = _utc_now()
        with self._transaction(immediate=True) as connection:
            existing = connection.execute(
                "SELECT id FROM job WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return str(existing["id"])
            connection.execute(
                """INSERT INTO job (id, kind, idempotency_key, payload_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (job_id, kind, idempotency_key, _json(payload), now, now),
            )
        return job_id

    def lease_next_job(
        self, kinds: list[str], worker_id: str, lease_seconds: int, now_utc: str | None = None
    ) -> dict | None:
        if not kinds:
            return None
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = _utc_iso(now_utc)
        expires = datetime.fromisoformat(now).timestamp() + lease_seconds
        expiry = datetime.fromtimestamp(expires, timezone.utc).isoformat()
        marks = ",".join("?" for _ in kinds)
        with self._transaction(immediate=True) as connection:
            row = connection.execute(
                f"""SELECT id FROM job WHERE kind IN ({marks}) AND
                (status = 'pending' OR (status = 'retryable_failed' AND
                 (next_retry_at IS NULL OR next_retry_at <= ?)))
                ORDER BY created_at, id LIMIT 1""",
                (*kinds, now),
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                """UPDATE job SET status = 'running', lease_worker = ?, lease_expires_at = ?,
                next_retry_at = NULL, updated_at = ? WHERE id = ? AND
                (status = 'pending' OR (status = 'retryable_failed' AND
                 (next_retry_at IS NULL OR next_retry_at <= ?)))""",
                (worker_id, expiry, now, row["id"], now),
            )
            if cursor.rowcount != 1:
                return None
            leased = connection.execute("SELECT * FROM job WHERE id = ?", (row["id"],)).fetchone()
        return self._job_public(leased)

    def renew_job_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
        now_utc: str | None = None,
    ) -> str:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._transaction(immediate=True) as connection:
            now = _utc_iso(now_utc)
            expires = datetime.fromisoformat(now).timestamp() + lease_seconds
            expiry = datetime.fromtimestamp(expires, timezone.utc).isoformat()
            cursor = connection.execute(
                """UPDATE job SET lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running' AND lease_worker = ?
                AND lease_expires_at > ?""",
                (expiry, now, job_id, worker_id, now),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "job is not held by the current unexpired lease owner"
                )
        return expiry

    def complete_job_with_followups(
        self,
        job_id: str,
        worker_id: str,
        result: dict,
        followups: Iterable[JobSpec],
    ) -> None:
        with self._transaction(immediate=True) as connection:
            now = _utc_now()
            self._require_unexpired_job_owner(connection, job_id, worker_id, now)
            self._insert_followups(connection, followups, now)
            result_json = _json(result)
            transition_now = _utc_now()
            cursor = connection.execute(
                """UPDATE job SET status = 'succeeded', result_json = ?,
                last_error_json = NULL, next_retry_at = NULL,
                lease_worker = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'running' AND lease_worker = ?
                AND lease_expires_at > ?""",
                (result_json, transition_now, job_id, worker_id, transition_now),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "job is not held by the current unexpired lease owner"
                )

    def fail_job_with_followups(
        self,
        job_id: str,
        worker_id: str,
        error: dict,
        retryable: bool,
        next_retry_at: str | None,
        followups: Iterable[JobSpec],
    ) -> None:
        state = "retryable_failed" if retryable else "terminal_failed"
        retry_at = _utc_iso(next_retry_at) if retryable and next_retry_at else None
        with self._transaction(immediate=True) as connection:
            now = _utc_now()
            self._require_unexpired_job_owner(connection, job_id, worker_id, now)
            self._insert_followups(connection, followups, now)
            error_json = _json(error)
            transition_now = _utc_now()
            cursor = connection.execute(
                """UPDATE job SET status = ?, last_error_json = ?, next_retry_at = ?,
                lease_worker = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'running' AND lease_worker = ?
                AND lease_expires_at > ?""",
                (
                    state,
                    error_json,
                    retry_at,
                    transition_now,
                    job_id,
                    worker_id,
                    transition_now,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "job is not held by the current unexpired lease owner"
                )

    @staticmethod
    def _require_unexpired_job_owner(
        connection: sqlite3.Connection,
        job_id: str,
        worker_id: str,
        now: str,
    ) -> None:
        owned = connection.execute(
            """SELECT 1 FROM job WHERE id = ? AND status = 'running'
            AND lease_worker = ? AND lease_expires_at > ?""",
            (job_id, worker_id, now),
        ).fetchone()
        if owned is None:
            raise ValueError("job is not held by the current unexpired lease owner")

    @staticmethod
    def _insert_followups(
        connection: sqlite3.Connection,
        followups: Iterable[JobSpec],
        now: str,
    ) -> None:
        for followup in followups:
            payload_json = followup._payload_json
            existing = connection.execute(
                """SELECT kind, payload_json FROM job
                WHERE idempotency_key = ?""",
                (followup.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["kind"] != followup.kind
                    or existing["payload_json"] != payload_json
                ):
                    raise ValueError(
                        "follow-up idempotency key conflicts with an existing job"
                    )
                continue
            connection.execute(
                """INSERT INTO job
                (id, kind, idempotency_key, payload_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    str(uuid.uuid4()),
                    followup.kind,
                    followup.idempotency_key,
                    payload_json,
                    now,
                    now,
                ),
            )

    def complete_job(self, job_id: str, result: dict) -> None:
        with self._transaction(immediate=True) as connection:
            self._require_legacy_transition_allowed(connection, job_id, "completed")
            cursor = connection.execute(
                """UPDATE job SET status = 'succeeded', result_json = ?,
                last_error_json = NULL, next_retry_at = NULL, lease_worker = NULL,
                lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'running'""",
                (_json(result), _utc_now(), job_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("only running jobs can be completed")

    def get_job(self, job_id: str) -> dict | None:
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
        finally:
            connection.close()
        return self._job_public(row) if row is not None else None

    def list_jobs(self, kinds: Sequence[str] | None = None) -> list[dict]:
        query = "SELECT * FROM job"
        parameters: list[object] = []
        if kinds is not None:
            if not kinds:
                return []
            marks = ",".join("?" for _ in kinds)
            query += f" WHERE kind IN ({marks})"
            parameters.extend(kinds)
        query += " ORDER BY created_at, id"
        with closing(self._connect()) as connection:
            return [
                self._job_public(row)
                for row in connection.execute(query, parameters)
            ]

    def fail_job(
        self, job_id: str, error: dict, retryable: bool, next_retry_at: str | None = None
    ) -> None:
        state = "retryable_failed" if retryable else "terminal_failed"
        with self._transaction(immediate=True) as connection:
            self._require_legacy_transition_allowed(connection, job_id, "failed")
            retry_at = _utc_iso(next_retry_at) if retryable and next_retry_at else None
            cursor = connection.execute(
                """UPDATE job SET status = ?, last_error_json = ?, next_retry_at = ?,
                lease_worker = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'running'""",
                (state, _json(error), retry_at, _utc_now(), job_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("only running jobs can fail")

    @staticmethod
    def _require_legacy_transition_allowed(
        connection: sqlite3.Connection,
        job_id: str,
        action: str,
    ) -> None:
        row = connection.execute(
            "SELECT kind, status FROM job WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None or row["status"] != "running":
            raise ValueError(f"only running jobs can be {action}")
        if row["kind"] in _OWNED_JOB_KINDS:
            raise ValueError("owned jobs require an explicit lease owner")

    def recover_expired_leases(self, now_utc: str | None = None) -> int:
        now = _utc_iso(now_utc)
        with self._transaction(immediate=True) as connection:
            rows = connection.execute(
                "SELECT id, lease_worker, lease_expires_at FROM job WHERE status = 'running' AND lease_expires_at <= ?",
                (now,),
            ).fetchall()
            for row in rows:
                error = {"reason": "lease_expired", "worker_id": row["lease_worker"], "expired_at": row["lease_expires_at"]}
                connection.execute(
                    """UPDATE job SET status = 'retryable_failed', last_error_json = ?,
                    next_retry_at = ?, lease_worker = NULL, lease_expires_at = NULL, updated_at = ? WHERE id = ?""",
                    (_json(error), now, now, row["id"]),
                )
            return len(rows)

    def record_snapshot(
        self, source: str, dataset: str, request_fingerprint: str, payload_hash: str,
        payload_path: str, row_count: int, fetched_at: str,
        *,
        _connection: sqlite3.Connection | None = None,
    ) -> tuple[str, bool]:
        if _connection is not None:
            return self._record_snapshot(
                _connection, source, dataset, request_fingerprint, payload_hash,
                payload_path, row_count, fetched_at,
            )
        with self._transaction(immediate=True) as connection:
            return self._record_snapshot(
                connection, source, dataset, request_fingerprint, payload_hash,
                payload_path, row_count, fetched_at,
            )

    @staticmethod
    def _record_snapshot(
        connection: sqlite3.Connection,
        source: str,
        dataset: str,
        request_fingerprint: str,
        payload_hash: str,
        payload_path: str,
        row_count: int,
        fetched_at: str,
    ) -> tuple[str, bool]:
        snapshot_id = str(uuid.uuid4())
        existing = connection.execute(
            """SELECT id FROM source_snapshot WHERE source = ? AND dataset = ?
            AND request_fingerprint = ? AND payload_hash = ?""",
            (source, dataset, request_fingerprint, payload_hash),
        ).fetchone()
        if existing:
            return str(existing["id"]), False
        connection.execute(
            "INSERT INTO source_snapshot VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, source, dataset, request_fingerprint, payload_hash, payload_path,
             row_count, _utc_iso(fetched_at), _utc_now()),
        )
        return snapshot_id, True

    def insert_financial_facts(
        self,
        facts: Iterable[FinancialFact],
        *,
        job_id: str | None = None,
        worker_id: str | None = None,
    ) -> tuple[int, int]:
        records = tuple(facts)
        if (job_id is None) != (worker_id is None):
            raise ValueError("job_id and worker_id must be provided together")
        transaction = (
            self.owned_job_transaction(job_id, worker_id)
            if job_id is not None and worker_id is not None
            else self._transaction(immediate=True)
        )
        with transaction as connection:
            inserted = self._insert_financial_facts(connection, records)
        return inserted, len(records) - inserted

    @staticmethod
    def _insert_financial_facts(
        connection: sqlite3.Connection,
        facts: Iterable[FinancialFact],
    ) -> int:
        inserted = 0
        for fact in facts:
            record = fact.to_record()
            cursor = connection.execute(
                """INSERT OR IGNORE INTO financial_fact
                (id,security_id,statement,metric_key,period_start,period_end,period_kind,
                 value,unit,nature,announced_at_utc,effective_at_utc,source_updated_at_utc,
                 source_snapshot_id,source_field,raw_row_hash,mapping_version,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(record[key] for key in FINANCIAL_FACT_COLUMNS),
            )
            inserted += cursor.rowcount
        return inserted

    @staticmethod
    def _insert_or_verify_reconciliation_facts(
        connection: sqlite3.Connection,
        facts: Iterable[FinancialFact],
    ) -> None:
        for fact in facts:
            record = fact.to_record()
            existing = connection.execute(
                "SELECT * FROM financial_fact WHERE id = ?", (fact.id,)
            ).fetchone()
            if existing is not None:
                try:
                    stored = FinancialFact.from_record(dict(existing))
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        "stored financial fact conflicts with reconciliation"
                    ) from error
                if stored != fact:
                    raise ValueError(
                        "stored financial fact conflicts with reconciliation"
                    )
                continue
            connection.execute(
                """INSERT INTO financial_fact
                (id,security_id,statement,metric_key,period_start,period_end,period_kind,
                 value,unit,nature,announced_at_utc,effective_at_utc,source_updated_at_utc,
                 source_snapshot_id,source_field,raw_row_hash,mapping_version,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(record[key] for key in FINANCIAL_FACT_COLUMNS),
            )

    def reconcile_malformed_statement(
        self,
        job_id: str,
        *,
        expected_idempotency_key: str,
        expected_payload: Mapping[str, object],
        expected_quality_issue_id: str,
        expected_quality_issue_details: Mapping[str, object],
        source_snapshot_id: str,
        source_snapshot_hash: str,
        facts: Iterable[FinancialFact],
        followup: JobSpec,
        result: Mapping[str, object],
    ) -> bool:
        records = tuple(facts)
        payload_json = _json(dict(expected_payload))
        malformed_error_json = _json(
            {"error_classification": "malformed_statement"}
        )
        with self._transaction(immediate=True) as connection:
            current = connection.execute(
                """SELECT created_at,updated_at FROM job WHERE id = ? AND kind = 'deep_statement'
                AND idempotency_key = ? AND payload_json = ?
                AND status = 'terminal_failed' AND last_error_json = ?""",
                (
                    job_id,
                    expected_idempotency_key,
                    payload_json,
                    malformed_error_json,
                ),
            ).fetchone()
            if current is None:
                return False
            security_id, dataset, report_period, refresh_date = (
                _validate_reconciliation_statement_identity(
                    expected_payload, expected_idempotency_key
                )
            )
            request_fingerprint = canonical_sha256(
                {"symbol": security_id, "report_period": report_period}
            )
            snapshot = connection.execute(
                """SELECT fetched_at,created_at FROM source_snapshot
                WHERE id = ? AND source = 'akshare' AND dataset = ?
                AND request_fingerprint = ? AND payload_hash = ?""",
                (
                    source_snapshot_id,
                    dataset,
                    request_fingerprint,
                    source_snapshot_hash,
                ),
            ).fetchone()
            if snapshot is None:
                return False
            if not reconciliation_snapshot_matches_job_refresh_date(
                snapshot_fetched_at=snapshot["fetched_at"],
                refresh_date=refresh_date,
                job_created_at=current["created_at"],
                job_updated_at=current["updated_at"],
            ):
                raise ValueError("reconciliation snapshot refresh date is invalid")
            if not records:
                raise ValueError("reconciliation facts must not be empty")
            if not all(isinstance(fact, FinancialFact) for fact in records):
                raise ValueError("reconciliation facts must be FinancialFact values")
            mapping_versions = {fact.mapping_version for fact in records}
            if len(mapping_versions) != 1:
                raise ValueError(
                    "reconciliation facts must use exactly one mapping version"
                )
            if mapping_versions != {MAPPING_VERSION}:
                raise ValueError(
                    "reconciliation facts must use the current mapping version"
                )
            expected_statement = DATASET_TO_STATEMENT.get(dataset)
            for fact in records:
                try:
                    canonical_fact = FinancialFact.from_record(fact.to_record())
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        "reconciliation facts must be canonical"
                    ) from error
                if (
                    canonical_fact != fact
                    or fact.source_snapshot_id != source_snapshot_id
                    or fact.security_id != security_id
                    or fact.statement != expected_statement
                ):
                    raise ValueError(
                        "reconciliation facts do not match job and snapshot identity"
                    )
            _validate_reconciliation_followup(
                connection,
                followup,
                statement_payload=expected_payload,
                source_snapshot_id=source_snapshot_id,
                source_snapshot_hash=source_snapshot_hash,
                reconciliation_job_created_at=current["created_at"],
                reconciliation_job_updated_at=current["updated_at"],
            )
            mapping_version = next(iter(mapping_versions))
            expected_result = {
                "outcome": "reconciled_verified_snapshot",
                "snapshot_hash": source_snapshot_hash,
                "mapping_version": mapping_version,
                "recovered_error": "malformed_statement",
            }
            if dict(result) != expected_result:
                raise ValueError(
                    "reconciliation result does not match verified recovery"
                )
            result_json = _json(expected_result)
            transition_now = _utc_now()
            _validate_and_bind_reconciliation_issue(
                connection,
                issue_id=expected_quality_issue_id,
                issue_details=expected_quality_issue_details,
                job_id=job_id,
                source_snapshot_id=source_snapshot_id,
                security_id=security_id,
                dataset=dataset,
                facts=records,
                refresh_date=refresh_date,
                snapshot_fetched_at=snapshot["fetched_at"],
                snapshot_created_at=snapshot["created_at"],
                job_created_at=current["created_at"],
                job_updated_at=current["updated_at"],
            )
            self._insert_or_verify_reconciliation_facts(connection, records)
            self._insert_followups(connection, (followup,), transition_now)
            cursor = connection.execute(
                """UPDATE job SET status = 'succeeded', result_json = ?,
                last_error_json = NULL, next_retry_at = NULL,
                lease_worker = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND kind = 'deep_statement'
                AND idempotency_key = ? AND payload_json = ?
                AND status = 'terminal_failed' AND last_error_json = ?""",
                (
                    result_json,
                    transition_now,
                    job_id,
                    expected_idempotency_key,
                    payload_json,
                    malformed_error_json,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("malformed statement reconciliation CAS failed")
        return True

    def list_financial_facts(
        self,
        security_id: str,
        *,
        effective_at_or_before: str | None = None,
        source_snapshot_ids: Sequence[str] | None = None,
    ) -> list[FinancialFact]:
        query = "SELECT * FROM financial_fact WHERE security_id = ?"
        parameters: list[object] = [security_id]
        if effective_at_or_before is not None:
            query += " AND effective_at_utc <= ?"
            parameters.append(_utc_iso(effective_at_or_before))
        if source_snapshot_ids is not None:
            if not source_snapshot_ids:
                return []
            marks = ",".join("?" for _ in source_snapshot_ids)
            query += f" AND source_snapshot_id IN ({marks})"
            parameters.extend(source_snapshot_ids)
        query += " ORDER BY metric_key,period_end,effective_at_utc,id"
        with closing(self._connect()) as connection:
            return [
                FinancialFact.from_record(dict(row))
                for row in connection.execute(query, parameters)
            ]

    def validate_feature_bundle_evidence(self, bundle: FeatureBundle) -> None:
        """Revalidate one bundle against the canonical facts in this store."""
        bundle.validate()
        with self._transaction() as connection:
            self._validate_feature_bundle_evidence(connection, bundle)

    @staticmethod
    def _validate_feature_bundle_evidence(
        connection: sqlite3.Connection,
        bundle: FeatureBundle,
    ) -> None:
        from ashare_pipeline.industry_templates import TEMPLATES

        projection_entries = financial_projection_values(bundle.dimension_inputs)
        template = TEMPLATES[bundle.industry.template_id]
        if (
            (not template.financial_slots and projection_entries)
            or any(
                dimension_name not in FINANCIAL_DIMENSIONS
                for dimension_name, _value in projection_entries
            )
        ):
            raise ValueError("financial projection has a noncanonical container")

        evidence_by_id: dict[str, EvidenceRef] = {}
        for dimension in bundle.dimension_inputs.values():
            for value in dimension.values:
                for evidence in value.evidence:
                    existing = evidence_by_id.get(evidence.financial_fact_id)
                    if existing is not None and existing != evidence:
                        raise ValueError("feature evidence metadata conflicts for one fact")
                    evidence_by_id[evidence.financial_fact_id] = evidence
        if not evidence_by_id:
            if "balance_equation_mismatch" in bundle.blockers:
                raise ValueError(
                    "balance equation semantics do not match canonical facts"
                )
            return

        facts_by_id: dict[str, FinancialFact] = {}
        fact_ids = sorted(evidence_by_id)
        try:
            for offset in range(0, len(fact_ids), _EVIDENCE_QUERY_BATCH_SIZE):
                batch = fact_ids[offset : offset + _EVIDENCE_QUERY_BATCH_SIZE]
                marks = ",".join("?" for _item in batch)
                rows = connection.execute(
                    f"SELECT * FROM financial_fact WHERE id IN ({marks})", batch
                ).fetchall()
                for row in rows:
                    fact = FinancialFact.from_record(dict(row))
                    if fact.id in facts_by_id:
                        raise ValueError("duplicate canonical financial fact evidence")
                    facts_by_id[fact.id] = fact
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("feature evidence contains a malformed financial fact") from error
        if set(facts_by_id) != set(fact_ids):
            raise ValueError("feature evidence financial fact is missing")

        snapshot_ids = sorted({fact.source_snapshot_id for fact in facts_by_id.values()})
        observed_snapshot_ids: set[str] = set()
        for offset in range(0, len(snapshot_ids), _EVIDENCE_QUERY_BATCH_SIZE):
            batch = snapshot_ids[offset : offset + _EVIDENCE_QUERY_BATCH_SIZE]
            marks = ",".join("?" for _item in batch)
            rows = connection.execute(
                f"SELECT id FROM source_snapshot WHERE id IN ({marks})", batch
            ).fetchall()
            for row in rows:
                snapshot_id = row["id"]
                if not isinstance(snapshot_id, str) or snapshot_id in observed_snapshot_ids:
                    raise ValueError("feature evidence snapshot row is malformed or duplicated")
                observed_snapshot_ids.add(snapshot_id)
        if observed_snapshot_ids != set(snapshot_ids):
            raise ValueError("feature evidence source snapshot is missing")

        for fact_id, evidence in evidence_by_id.items():
            fact = facts_by_id[fact_id]
            if (
                fact.security_id != bundle.security_id
                or evidence.source_snapshot_id != fact.source_snapshot_id
                or evidence.source_field != fact.source_field
                or evidence.raw_row_hash != fact.raw_row_hash
                or evidence.announced_at_utc != fact.announced_at_utc
                or evidence.effective_at_utc != fact.effective_at_utc
            ):
                raise ValueError("feature evidence does not match canonical financial fact")

        period_end_by_key = {
            period_key: period_end for period_end, period_key in FINANCIAL_PERIODS
        }
        formula_inputs: dict[tuple[str, str], FormulaFact] = {}
        observed_raw_fact_ids: set[str] = set()
        observed_raw_facts: list[FinancialFact] = []
        for dimension_name, dimension in bundle.dimension_inputs.items():
            for value in dimension.values:
                if value.status != "observed":
                    continue
                parts = value.key.split(".")
                if len(parts) != 3:
                    continue
                try:
                    descriptor = raw_financial_slot_descriptor(parts[1])
                except ValueError:
                    continue
                period_end = period_end_by_key.get(value.period_key)
                if (
                    period_end is None
                    or dimension_name != descriptor.dimension
                    or value.key != descriptor.canonical_key(value.period_key)
                    or value.status not in descriptor.allowed_statuses
                    or value.formula_version != descriptor.formula_version
                    or value.unit != descriptor.unit
                    or len(value.evidence) != 1
                ):
                    raise ValueError("raw observed feature evidence is noncanonical")
                fact = facts_by_id[value.evidence[0].financial_fact_id]
                if (
                    fact.metric_key != descriptor.metric_key
                    or fact.period_end != period_end
                    or fact.value != value.value
                    or fact.unit != descriptor.unit
                    or fact.mapping_version != descriptor.formula_version
                    or fact.source_field not in descriptor.source_fields
                ):
                    raise ValueError("raw observed feature evidence does not match its fact")
                if fact.id in observed_raw_fact_ids:
                    raise ValueError("raw observed financial fact is reused across slots")
                observed_raw_fact_ids.add(fact.id)
                slot = (descriptor.metric_key, period_end)
                if slot in formula_inputs:
                    raise ValueError("raw observed financial slot is duplicated")
                formula_inputs[slot] = FormulaFact(
                    fact.metric_key,
                    fact.period_end,
                    fact.value,
                    fact.unit,
                    fact.id,
                )
                observed_raw_facts.append(fact)

        expected_balance_mismatch = (
            "balance_equation_mismatch"
            in balance_equation_blockers(observed_raw_facts)
        )
        advertised_balance_mismatch = (
            "balance_equation_mismatch" in bundle.blockers
        )
        if expected_balance_mismatch != advertised_balance_mismatch:
            raise ValueError(
                "balance equation semantics do not match canonical facts"
            )
        if expected_balance_mismatch and (
            bundle.financial_status != "blocked"
            or any(
                bundle.dimension_inputs[dimension].status != "blocked"
                for dimension in FINANCIAL_DIMENSIONS
            )
        ):
            raise ValueError(
                "balance equation semantics require blocked financial status"
            )

        formula_identities = {
            (spec.dimension, spec.canonical_key, spec.period_key)
            for spec in DERIVED_FORMULA_SPECS
        }
        formula_values = {
            (dimension_name, value.key, value.period_key): value
            for dimension_name, value in projection_entries
            if (dimension_name, value.key, value.period_key) in formula_identities
        }
        if formula_values:
            expected_results = evaluate_derived_financial(formula_inputs)
            if len(formula_values) != len(expected_results):
                raise ValueError("derived financial projection does not match canonical facts")
            for result in expected_results:
                identity = (
                    result.spec.dimension,
                    result.spec.canonical_key,
                    result.spec.period_key,
                )
                value = formula_values.get(identity)
                if value is None:
                    raise ValueError(
                        "derived financial projection does not match canonical facts"
                    )
                advertised_ids = tuple(
                    sorted(evidence.financial_fact_id for evidence in value.evidence)
                )
                if (
                    value.status != result.status
                    or value.unit != result.spec.unit
                    or value.formula_version != result.spec.formula_version
                    or _json(value.value) != _json(result.value)
                    or value.missing_reason != result.missing_reason
                    or advertised_ids != result.operand_ids
                ):
                    raise ValueError(
                        "derived financial projection does not match canonical facts"
                    )

    def put_feature_bundle(
        self,
        bundle: FeatureBundle,
        *,
        bundle_path: str,
        bundle_hash: str,
        _connection: sqlite3.Connection | None = None,
    ) -> tuple[str, bool]:
        bundle.validate()
        if bundle_hash != bundle.bundle_hash():
            raise ValueError("bundle_hash does not match canonical bundle hash")
        self._validate_feature_bundle_path(bundle_path)
        header, values = self._feature_bundle_content(bundle, bundle_hash)

        if _connection is not None:
            return self._put_feature_bundle(
                _connection, bundle, header, values, bundle_path, bundle_hash
            )
        with self._transaction(immediate=True) as connection:
            return self._put_feature_bundle(
                connection, bundle, header, values, bundle_path, bundle_hash
            )

    def _put_feature_bundle(
        self,
        connection: sqlite3.Connection,
        bundle: FeatureBundle,
        header: Mapping[str, object],
        values: Sequence[Mapping[str, object]],
        bundle_path: str,
        bundle_hash: str,
    ) -> tuple[str, bool]:
        self._validate_feature_bundle_evidence(connection, bundle)
        existing = connection.execute(
            """SELECT * FROM feature_set
            WHERE security_id = ? AND report_period = ? AND as_of_utc = ? AND input_hash = ?""",
            (
                header["security_id"],
                header["report_period"],
                header["as_of_utc"],
                header["input_hash"],
            ),
        ).fetchone()
        if existing is not None:
            self._validate_stored_feature_bundle_content(
                connection, existing, bundle
            )
            return str(existing["id"]), False

        feature_set_id = bundle_hash
        connection.execute(
            """INSERT INTO feature_set
            (id,security_id,report_period,as_of_utc,candidate_set_hash,
             template_id,template_version,contract_version,input_hash,status,
             financial_coverage,dimension_status_json,confidence_inputs_json,
             blockers_json,bundle_hash,bundle_path,missing_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                feature_set_id,
                *(header[column] for column in _FEATURE_SET_CONTENT_COLUMNS[:-2]),
                header["bundle_hash"],
                bundle_path,
                header["missing_json"],
                _utc_now(),
            ),
        )
        for value in values:
            connection.execute(
                """INSERT INTO feature_value
                (feature_set_id,dimension,feature_key,period_key,value,unit,status,
                 formula_version,evidence_json,missing_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    feature_set_id,
                    *(value[column] for column in _FEATURE_VALUE_CONTENT_COLUMNS),
                ),
            )
        inserted = connection.execute(
            "SELECT * FROM feature_set WHERE id=?", (feature_set_id,)
        ).fetchone()
        if inserted is None:
            raise ValueError("stored feature bundle content mismatch")
        self._validate_stored_feature_bundle_content(
            connection, inserted, bundle
        )
        return feature_set_id, True

    def get_feature_bundle_row(
        self,
        security_id: str,
        report_period: str,
        input_hash: str,
    ) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT * FROM feature_set
                WHERE security_id = ? AND report_period = ? AND input_hash = ?
                ORDER BY as_of_utc DESC, created_at DESC, id DESC LIMIT 1""",
                (security_id, report_period, input_hash),
            ).fetchone()
        return self._feature_set_public(row) if row is not None else None

    def latest_feature_set(
        self,
        security_id: str,
        report_period: str,
        contract_version: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict | None:
        query = "SELECT * FROM feature_set WHERE security_id = ? AND report_period = ?"
        parameters: list[object] = [security_id, report_period]
        if contract_version is not None:
            query += " AND contract_version = ?"
            parameters.append(contract_version)
        if as_of_utc is not None:
            query += " AND as_of_utc = ?"
            parameters.append(_utc_iso(as_of_utc))
        query += " ORDER BY as_of_utc DESC, created_at DESC, id DESC LIMIT 1"
        with closing(self._connect()) as connection:
            row = connection.execute(query, parameters).fetchone()
        return self._feature_set_public(row) if row is not None else None

    def record_quality_issue(
        self,
        *,
        run_id: str | None,
        score_run_id: str | None,
        severity: str,
        code: str,
        details: Mapping[str, object],
        job_id: str | None = None,
        worker_id: str | None = None,
        source_snapshot_id: str | None = None,
    ) -> str:
        issue_id = str(uuid.uuid4())
        if (job_id is None) != (worker_id is None):
            raise ValueError("job_id and worker_id must be provided together")
        if source_snapshot_id is not None and job_id is None:
            raise ValueError(
                "source_snapshot_id requires job_id and worker_id"
            )
        if source_snapshot_id is not None and (
            not isinstance(source_snapshot_id, str) or not source_snapshot_id
        ):
            raise ValueError("source_snapshot_id must identify a snapshot")
        details_json = _json(dict(details))
        transaction = (
            self.owned_job_transaction(job_id, worker_id)
            if job_id is not None and worker_id is not None
            else self._transaction()
        )
        with transaction as connection:
            connection.execute(
                """INSERT INTO quality_issue
                (id,run_id,score_run_id,severity,code,details_json,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    issue_id,
                    run_id,
                    score_run_id,
                    severity,
                    code,
                    details_json,
                    _utc_now(),
                ),
            )
            if source_snapshot_id is not None:
                snapshot = connection.execute(
                    "SELECT 1 FROM source_snapshot WHERE id = ?",
                    (source_snapshot_id,),
                ).fetchone()
                if snapshot is None:
                    raise ValueError("source_snapshot_id does not exist")
                connection.execute(
                    """INSERT INTO quality_issue_binding
                    (issue_id,job_id,source_snapshot_id) VALUES (?,?,?)""",
                    (issue_id, job_id, source_snapshot_id),
                )
        return issue_id

    def find_quality_issue_ids(
        self,
        *,
        severity: str,
        code: str,
        details: Mapping[str, object],
    ) -> tuple[str, ...]:
        with closing(self._connect()) as connection:
            return tuple(
                str(row["id"])
                for row in connection.execute(
                    """SELECT id FROM quality_issue
                    WHERE severity = ? AND code = ? AND details_json = ?
                    ORDER BY id""",
                    (severity, code, _json(dict(details))),
                )
            )

    def resolve_reconciliation_quality_issue(
        self,
        *,
        severity: str,
        code: str,
        details: Mapping[str, object],
        job_id: str,
        source_snapshot_id: str,
    ) -> tuple[str, str] | None:
        """Return direct evidence, or the only safely attributable legacy issue.

        The returned evidence kind is ``"bound"`` when its provenance exactly
        matches the requested job and snapshot, otherwise ``"legacy"``.  A
        legacy issue is intentionally usable only when it is the sole unbound
        exact match, has no conflicting bound match, was recorded during the
        current job lifetime, and the job is the sole malformed statement
        failure for that security and dataset.
        """
        if not isinstance(details, Mapping):
            raise ValueError("reconciliation quality issue details are invalid")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("reconciliation quality issue job id is invalid")
        if not isinstance(source_snapshot_id, str) or not source_snapshot_id:
            raise ValueError(
                "reconciliation quality issue source snapshot id is invalid"
            )
        details_json = _json(dict(details))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT issue.id,binding.job_id,binding.source_snapshot_id
                FROM quality_issue AS issue
                LEFT JOIN quality_issue_binding AS binding
                ON binding.issue_id=issue.id
                WHERE issue.severity=? AND issue.code=? AND issue.details_json=?
                ORDER BY issue.id""",
                (severity, code, details_json),
            ).fetchall()
            exact_bound = tuple(
                str(row["id"])
                for row in rows
                if row["job_id"] == job_id
                and row["source_snapshot_id"] == source_snapshot_id
            )
            if exact_bound:
                return exact_bound[0], "bound"
            if any(
                row["job_id"] is not None
                or row["source_snapshot_id"] is not None
                for row in rows
            ):
                return None
            unbound = tuple(str(row["id"]) for row in rows)
            if len(unbound) != 1:
                return None
            security_id = details.get("security_id")
            dataset = details.get("dataset")
            if not isinstance(security_id, str) or not isinstance(dataset, str):
                return None
            if _legacy_malformed_statement_job_ids(
                connection, security_id=security_id, dataset=dataset
            ) != (job_id,):
                return None
            if not _legacy_issue_falls_within_job_lifetime(
                connection, issue_id=unbound[0], job_id=job_id
            ):
                return None
            return unbound[0], "legacy"

    def has_quality_issue(
        self,
        *,
        severity: str,
        code: str,
        details: Mapping[str, object],
    ) -> bool:
        with closing(self._connect()) as connection:
            return connection.execute(
                """SELECT 1 FROM quality_issue
                WHERE severity = ? AND code = ? AND details_json = ?
                LIMIT 1""",
                (severity, code, _json(dict(details))),
            ).fetchone() is not None

    def create_score_run(
        self, report_period: str, as_of_cn: str, ruleset_hash: str, universe_hash: str, mode: str
    ) -> str:
        score_run_id = str(uuid.uuid4())
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO score_run (id, report_period, as_of_cn, ruleset_hash, universe_hash, mode, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'provisional', ?)""",
                (score_run_id, report_period, _utc_iso(as_of_cn), ruleset_hash, universe_hash, mode, _utc_now()),
            )
        return score_run_id

    def upsert_score_item(
        self, score_run_id: str, security_id: str, state: str, coverage: float, input_hash: str,
        scores: dict | None, reasons: list[str]
    ) -> None:
        if state not in SCORE_ITEM_STATES:
            raise ValueError(f"invalid score item state: {state}")
        if state == "final":
            raise ValueError("score items become final only through score run finalization")
        if not 0 <= coverage <= 1:
            raise ValueError("coverage must be between 0 and 1")
        with self._transaction() as connection:
            score_run = connection.execute("SELECT status FROM score_run WHERE id = ?", (score_run_id,)).fetchone()
            if score_run is None:
                raise ValueError("score run does not exist")
            if score_run["status"] != "provisional":
                raise ValueError("final or invalidated score runs cannot be modified")
            connection.execute(
                """INSERT INTO score_item (score_run_id, security_id, state, coverage, input_hash, scores_json, reasons_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(score_run_id, security_id) DO UPDATE SET state = excluded.state,
                coverage = excluded.coverage, input_hash = excluded.input_hash, scores_json = excluded.scores_json,
                reasons_json = excluded.reasons_json, updated_at = excluded.updated_at""",
                (score_run_id, security_id, state, coverage, input_hash,
                 _json(scores) if scores is not None else None, _json(reasons), _utc_now()),
            )

    def finalize_score_run(
        self, score_run_id: str, now_cn: str, cutoff_cn: str, market_ready: bool, quality_passed: bool,
        market_evidence: dict | None = None, quality_evidence: dict | None = None,
    ) -> None:
        now_utc = _utc_iso(now_cn)
        cutoff_utc = _utc_iso(cutoff_cn)
        now = datetime.fromisoformat(now_utc)
        cutoff = datetime.fromisoformat(cutoff_utc)
        with self._transaction(immediate=True) as connection:
            score_run = connection.execute("SELECT status FROM score_run WHERE id = ?", (score_run_id,)).fetchone()
            if score_run is None:
                raise ValueError("score run does not exist")
            if score_run["status"] == "final":
                return
            if score_run["status"] != "provisional":
                raise ValueError("only provisional score runs can be finalized")
            if not (now > cutoff and market_ready and quality_passed):
                raise FinalizationBlocked("cutoff, market readiness, and quality gate must all pass")
            connection.execute(
                "UPDATE score_item SET state = 'final', updated_at = ? WHERE score_run_id = ? AND state = 'ready'",
                (now_utc, score_run_id),
            )
            connection.execute(
                """UPDATE score_run SET status = 'final', finalized_at = ?, cutoff_utc = ?,
                market_ready = ?, quality_passed = ?, market_evidence_json = ?, quality_evidence_json = ?
                WHERE id = ?""",
                (now_utc, cutoff_utc, int(market_ready), int(quality_passed),
                 _json(market_evidence or {}), _json(quality_evidence or {}), score_run_id),
            )

    def progress_snapshot(self) -> dict:
        connection = self._connect()
        try:
            job_counts = {state: 0 for state in JOB_STATES}
            job_counts.update(dict(connection.execute("SELECT status, COUNT(*) FROM job GROUP BY status")))
            score_counts = {state: 0 for state in SCORE_ITEM_STATES}
            score_counts.update(dict(connection.execute("SELECT state, COUNT(*) FROM score_item GROUP BY state")))
            score_run_counts = {state: 0 for state in SCORE_RUN_STATES}
            score_run_counts.update(dict(connection.execute("SELECT status, COUNT(*) FROM score_run GROUP BY status")))
            recent = connection.execute(
                "SELECT id, mode, as_of_cn, status, started_at, finished_at FROM run ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            update_values = []
            for table, column in (("job", "updated_at"), ("score_item", "updated_at"),
                                  ("run", "started_at"), ("run", "finished_at"),
                                  ("score_run", "created_at"), ("score_run", "finalized_at"),
                                  ("source_snapshot", "created_at"), ("source_snapshot", "fetched_at"),
                                  ("artifact", "created_at"), ("quality_issue", "created_at")):
                value = connection.execute(f"SELECT MAX({column}) FROM {table}").fetchone()[0]
                if value is not None:
                    update_values.append(value)
        finally:
            connection.close()
        return {
            "schema_version": SCHEMA_VERSION,
            "job_counts": job_counts,
            "score_item_counts": score_counts,
            "score_run_counts": score_run_counts,
            "recent_run": dict(recent) if recent else None,
            "updated_at": max(update_values, default=_utc_now()),
        }

    @staticmethod
    def _validate_feature_bundle_path(bundle_path: str) -> None:
        prefix_parts = ("data", "curated", "formal_features")
        if not isinstance(bundle_path, str) or not bundle_path or "\\" in bundle_path:
            raise ValueError("bundle_path must be a forward-slash project-relative path")
        raw_parts = bundle_path.split("/")
        path = PurePosixPath(bundle_path)
        if (
            path.is_absolute()
            or PureWindowsPath(bundle_path).is_absolute()
            or tuple(raw_parts[:3]) != prefix_parts
            or len(raw_parts) == len(prefix_parts)
            or any(part in {"", ".", ".."} for part in raw_parts)
        ):
            raise ValueError(
                "bundle_path must begin with data/curated/formal_features/ and stay within it"
            )

    @staticmethod
    def _feature_bundle_content(
        bundle: FeatureBundle,
        bundle_hash: str,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        payload = bundle.to_dict()
        dimension_status = {
            dimension: payload["dimension_inputs"][dimension]["status"]
            for dimension in DIMENSIONS
        }
        values: list[dict[str, object]] = []
        missing: list[dict[str, object]] = []
        for dimension in DIMENSIONS:
            for value in payload["dimension_inputs"][dimension]["values"]:
                values.append(
                    {
                        "dimension": dimension,
                        "feature_key": value["key"],
                        "period_key": value["period_key"],
                        "value": value["value"],
                        "unit": value["unit"],
                        "status": value["status"],
                        "formula_version": value["formula_version"],
                        "evidence_json": _json(value["evidence"]),
                        "missing_reason": value["missing_reason"],
                    }
                )
                if value["status"] in {"missing", "not_applicable", "blocked"}:
                    missing.append(
                        {
                            "dimension": dimension,
                            "feature_key": value["key"],
                            "period_key": value["period_key"],
                            "reason": value["missing_reason"],
                        }
                    )
        header: dict[str, object] = {
            "security_id": payload["security_id"],
            "report_period": payload["report_period"],
            "as_of_utc": payload["as_of_utc"],
            "candidate_set_hash": payload["candidate_set_hash"],
            "template_id": payload["industry"]["template_id"],
            "template_version": payload["industry"]["template_version"],
            "contract_version": payload["contract_version"],
            "input_hash": payload["input_hash"],
            "status": payload["financial_status"],
            "financial_coverage": payload["financial_coverage"],
            "dimension_status_json": _json(dimension_status),
            "confidence_inputs_json": _json(payload["confidence_inputs"]),
            "blockers_json": _json(payload["blockers"]),
            "bundle_hash": bundle_hash,
            "missing_json": _json(missing),
        }
        return header, values

    @staticmethod
    def _validate_stored_feature_bundle_content(
        connection: sqlite3.Connection,
        feature_set_row: sqlite3.Row,
        bundle: FeatureBundle,
    ) -> None:
        header, values = StateStore._feature_bundle_content(
            bundle, bundle.bundle_hash()
        )
        if any(
            feature_set_row[column] != header[column]
            for column in _FEATURE_SET_CONTENT_COLUMNS
        ):
            raise ValueError("stored feature bundle content mismatch")
        stored_values = connection.execute(
            """SELECT dimension,feature_key,period_key,value,unit,status,
            formula_version,evidence_json,missing_reason FROM feature_value
            WHERE feature_set_id = ? ORDER BY dimension,feature_key,period_key
            LIMIT ?""",
            (feature_set_row["id"], len(values) + 1),
        ).fetchall()
        expected = sorted(
            (
                tuple(value[column] for column in _FEATURE_VALUE_CONTENT_COLUMNS)
                for value in values
            ),
            key=lambda value: (value[0], value[1], value[2]),
        )
        if [tuple(row) for row in stored_values] != expected:
            raise ValueError("stored feature bundle content mismatch")

    @staticmethod
    def _feature_set_public(row: sqlite3.Row) -> dict:
        result = dict(row)
        for stored_name, public_name in (
            ("dimension_status_json", "dimension_status"),
            ("confidence_inputs_json", "confidence_inputs"),
            ("blockers_json", "blockers"),
            ("missing_json", "missing"),
        ):
            result[public_name] = json.loads(result.pop(stored_name))
        return result

    @staticmethod
    def _job_public(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"], "kind": row["kind"], "idempotency_key": row["idempotency_key"],
            "status": row["status"], "lease_worker": row["lease_worker"],
            "lease_expires_at": row["lease_expires_at"], "payload": json.loads(row["payload_json"]),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": json.loads(row["last_error_json"]) if row["last_error_json"] else None,
            "next_retry_at": row["next_retry_at"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }
