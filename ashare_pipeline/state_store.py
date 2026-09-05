"""SQLite-backed state transitions for resumable pipeline work."""

from __future__ import annotations

import copy
import hashlib
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
from ashare_pipeline.formal_evidence import (
    EvidenceVerification,
    OfficialFetch,
    OfficialRequest,
    OfficialSnapshotRef,
)
from ashare_pipeline.formal_snapshot_store import (
    FormalSnapshotStore,
    FormalStoredSnapshot,
    ValidatedFormalSnapshot,
)
from ashare_pipeline.formal_time import formal_version_sort_key, is_visible_at
from ashare_pipeline.formal_financial_schema import FormalFinancialFact
from ashare_pipeline.formal_financial_features import FormalQuarterFact, derive_comparable_quarters
from ashare_pipeline.formal_feature_contract import (
    FormalFeatureBundle, FormalFeatureValue, FormalEvidenceRef, load_signed_feature_registry,
)
from ashare_pipeline.formal_feature_store import FormalFeatureBundleStore, FormalStoredFeatureBundle
from ashare_pipeline.formal_registry_manifest import (
    FormalRegistryManifest, FormalRegistryBundleLoader, VerifiedRegistryBlob,
)
from ashare_pipeline.formal_universe import (
    FormalFrozenUniverseInput,
    FormalUniverseDecision,
    FormalUniverseExtraction,
    FormalUniverseMember,
    FormalUniverseSourceAudit,
    FormalUniverseSourceEvidence,
    _create_frozen_universe_input,
    _validate_frozen_universe_input,
    canonical_security_id,
)


JOB_STATES = {"pending", "running", "succeeded", "retryable_failed", "terminal_failed"}
FORMAL_TASK_STATES = {
    "pending",
    "leased",
    "verified",
    "retryable_failed",
    "terminal_failed",
    "superseded",
}
SCORE_RUN_STATES = {"provisional", "final", "invalidated"}
SCORE_ITEM_STATES = {"pending", "partial", "ready", "blocked", "final"}
RUN_STATES = {"running", "succeeded", "failed", "cancelled"}
_OWNED_JOB_KINDS = frozenset({"deep_financial", "deep_statement", "feature_build"})
SCHEMA_VERSION = 6
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
_FORMAL_REQUEST_IDENTITY_KEYS = frozenset(
    {"dataset", "exchange", "period_or_date", "security_id", "source"}
)
_FORMAL_VERIFICATION_KEYS = frozenset(
    {"content_sha256", "effective_at_utc", "reasons", "status"}
)
_FORMAL_SOURCE_FETCH_KINDS = frozenset(
    {"formal_statement", "formal_context", "formal_universe_source"}
)
_FORMAL_UNIVERSE_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_FORMAL_UNIVERSE_STATUSES = frozenset(
    {"out_of_scope", "pending_evidence", "pool_vetoed", "formal_scored"}
)
_FORMAL_UNIVERSE_EXTRACTION_KEYS = frozenset({"audit", "exchange", "members"})
_FORMAL_UNIVERSE_AUDIT_KEYS = frozenset(
    {
        "accepted_members_hash",
        "accepted_ordinary_a_count",
        "audit_hash",
        "exchange",
        "excluded_by_security_type",
        "excluded_rows_hash",
        "parsed_rows_hash",
        "parser_id",
        "parser_version",
        "source_content_sha256",
        "source_row_count",
    }
)
_FORMAL_UNIVERSE_MEMBER_KEYS = frozenset(
    {
        "exchange",
        "listing_status",
        "raw_row",
        "raw_row_hash",
        "security_id",
        "security_type",
    }
)
_FORMAL_UNIVERSE_FINALIZER_PAYLOAD_KEYS = frozenset(
    {"as_of_utc", "registry_manifest_hash", "refresh_generation", "source_task_ids"}
)
_FORMAL_UNIVERSE_FINALIZER_RESULT_KEYS = frozenset(
    {"universe_snapshot_id", "frozen_input_hash", "universe_hash", "registry_manifest_hash"}
)


@dataclass(frozen=True)
class _FormalSnapshotVersion:
    """Adapt the immutable formal reference to the shared version-order protocol."""

    ref: OfficialSnapshotRef

    @property
    def published_at_utc(self) -> str:
        return self.ref.published_at_utc

    @property
    def source_updated_at_utc(self) -> str | None:
        return self.ref.source_updated_at_utc

    @property
    def captured_at_utc(self) -> str:
        return self.ref.captured_at_utc

    @property
    def content_hash(self) -> str:
        return self.ref.content_sha256

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


_FORMAL_REGISTRY_ROLES = (
    "source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event",
)
_FORMAL_ROOT_FIELDS = (
    "manifest_hash", "purpose", "approval_id", "canonical_json", "signature", "key_id",
    *(f"{role}_registry_hash" for role in _FORMAL_REGISTRY_ROLES),
)
_FORMAL_BLOB_FIELDS = (
    "registry_hash", "registry_role", "canonical_json", "signature", "key_id", "approval_id",
    "declared_registry_manifest_hash", "binding_signature", "binding_key_id",
)
_V6_TABLE_DDL = {
    "formal_financial_fact": """CREATE TABLE formal_financial_fact (
        id TEXT PRIMARY KEY, security_id TEXT NOT NULL, statement TEXT NOT NULL,
        metric_key TEXT NOT NULL, period_start TEXT, period_end TEXT NOT NULL,
        period_kind TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL,
        nature TEXT NOT NULL, accounting_basis TEXT NOT NULL,
        published_at_utc TEXT NOT NULL, published_precision TEXT NOT NULL,
        effective_at_utc TEXT NOT NULL, effective_time_evidence_hash TEXT,
        source_updated_at_utc TEXT, captured_at_utc TEXT NOT NULL,
        source_snapshot_id TEXT NOT NULL REFERENCES formal_source_snapshot(id),
        source_content_sha256 TEXT NOT NULL, source_refresh_generation TEXT NOT NULL,
        source_producing_task_id TEXT, source_field TEXT NOT NULL,
        raw_value_sha256 TEXT NOT NULL, parser_id TEXT NOT NULL,
        parser_version TEXT NOT NULL, mapping_version TEXT NOT NULL, created_at_utc TEXT NOT NULL
    )""",
    "formal_quarter_fact": """CREATE TABLE formal_quarter_fact (
        id TEXT PRIMARY KEY, security_id TEXT NOT NULL, statement TEXT NOT NULL,
        metric_key TEXT NOT NULL, quarter_end TEXT NOT NULL, quarter_key TEXT NOT NULL,
        value REAL NOT NULL, unit TEXT NOT NULL, nature TEXT NOT NULL,
        accounting_basis TEXT NOT NULL, mapping_version TEXT NOT NULL,
        component_fact_ids_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
        derivation_version TEXT NOT NULL, created_at_utc TEXT NOT NULL
    )""",
    "formal_feature_set": """CREATE TABLE formal_feature_set (
        id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, contract_version TEXT NOT NULL,
        security_id TEXT NOT NULL, as_of_utc TEXT NOT NULL, template_id TEXT NOT NULL,
        registry_manifest_hash TEXT NOT NULL, feature_registry_hash TEXT NOT NULL,
        input_hash TEXT NOT NULL UNIQUE, history_endpoints_json TEXT NOT NULL,
        comparable_quarter_keys_json TEXT NOT NULL, blockers_json TEXT NOT NULL,
        bundle_hash TEXT NOT NULL, bundle_manifest_hash TEXT NOT NULL,
        bundle_path TEXT NOT NULL, manifest_path TEXT NOT NULL, created_at_utc TEXT NOT NULL
    )""",
    "formal_feature_value": """CREATE TABLE formal_feature_value (
        feature_set_id TEXT NOT NULL REFERENCES formal_feature_set(id), slot_id TEXT NOT NULL,
        value REAL, unit TEXT NOT NULL, status TEXT NOT NULL, formula_version TEXT NOT NULL,
        evidence_json TEXT NOT NULL, missing_reason TEXT,
        PRIMARY KEY(feature_set_id, slot_id)
    )""",
    "formal_context_fact": """CREATE TABLE formal_context_fact (
        id TEXT PRIMARY KEY, context_kind TEXT NOT NULL, scope_key TEXT NOT NULL,
        security_id TEXT, as_of_utc TEXT NOT NULL, value_json TEXT NOT NULL,
        no_coverage INTEGER NOT NULL, published_at_utc TEXT NOT NULL,
        effective_at_utc TEXT NOT NULL, source_updated_at_utc TEXT, captured_at_utc TEXT NOT NULL,
        refresh_generation TEXT NOT NULL, source_snapshot_id TEXT NOT NULL REFERENCES formal_source_snapshot(id),
        source_content_sha256 TEXT NOT NULL, parser_id TEXT NOT NULL, parser_version TEXT NOT NULL,
        mapping_version TEXT NOT NULL, registry_manifest_hash TEXT NOT NULL,
        evidence_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
    )""",
    "formal_registry_manifest": """CREATE TABLE formal_registry_manifest (
        manifest_hash TEXT PRIMARY KEY, purpose TEXT NOT NULL, approval_id TEXT,
        canonical_json BLOB NOT NULL, signature TEXT NOT NULL, key_id TEXT NOT NULL,
        source_registry_hash TEXT NOT NULL, mapping_registry_hash TEXT NOT NULL,
        feature_registry_hash TEXT NOT NULL, scoring_registry_hash TEXT NOT NULL,
        industry_registry_hash TEXT NOT NULL, cyclic_registry_hash TEXT NOT NULL,
        redline_registry_hash TEXT NOT NULL, status_registry_hash TEXT NOT NULL,
        event_registry_hash TEXT NOT NULL, created_at_utc TEXT NOT NULL
    )""",
    "formal_registry_blob": """CREATE TABLE formal_registry_blob (
        registry_hash TEXT PRIMARY KEY, registry_role TEXT NOT NULL, canonical_json BLOB NOT NULL,
        signature TEXT NOT NULL, key_id TEXT NOT NULL, approval_id TEXT,
        declared_registry_manifest_hash TEXT NOT NULL, binding_signature TEXT NOT NULL,
        binding_key_id TEXT NOT NULL, created_at_utc TEXT NOT NULL
    )""",
    "formal_source_circuit": """CREATE TABLE formal_source_circuit (
        source TEXT PRIMARY KEY, state TEXT NOT NULL, failure_count INTEGER NOT NULL,
        reason_json TEXT NOT NULL, opened_at_utc TEXT, retry_after_utc TEXT, updated_at_utc TEXT NOT NULL
    )""",
}
_V6_INDEX_DDL = {
    "idx_formal_financial_fact_security": "CREATE INDEX idx_formal_financial_fact_security ON formal_financial_fact(security_id, period_end, statement, metric_key, id)",
    "idx_formal_quarter_fact_security": "CREATE INDEX idx_formal_quarter_fact_security ON formal_quarter_fact(security_id, quarter_end, statement, metric_key, id)",
    "idx_formal_feature_set_header": "CREATE INDEX idx_formal_feature_set_header ON formal_feature_set(security_id, as_of_utc, template_id, registry_manifest_hash, id)",
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


def _validate_json_object_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            _validate_json_object_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _validate_json_object_keys(nested)


def _canonical_mapping_json(value: Mapping[str, object], field: str) -> str:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    try:
        snapshot = copy.deepcopy(dict(value))
        _validate_json_object_keys(snapshot)
        return _json(snapshot)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a finite JSON mapping") from error


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode_canonical_mapping_json(value: str, field: str) -> dict[str, object]:
    try:
        decoded = json.loads(
            value,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"nonfinite JSON value: {constant}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"stored formal task {field} JSON is invalid") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"stored formal task {field} JSON is not a mapping")
    if _json(decoded) != value:
        raise ValueError(f"stored formal task {field} JSON is not canonical")
    return decoded


def _decode_canonical_formal_json(value: object, field: str) -> dict[str, object]:
    if type(value) is not str:
        raise ValueError(f"stored formal snapshot {field} JSON must be text")
    try:
        decoded = json.loads(
            value,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"nonfinite JSON value: {constant}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"stored formal snapshot {field} JSON is invalid") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"stored formal snapshot {field} JSON is not a mapping")
    if _json(decoded) != value:
        raise ValueError(f"stored formal snapshot {field} JSON is not canonical")
    return decoded


def _plain_formal_universe_json(value: object) -> object:
    if isinstance(value, Mapping):
        plain: dict[str, object] = {}
        for key, nested in value.items():
            if type(key) is not str:
                raise ValueError("formal universe JSON object keys must be strings")
            plain[key] = _plain_formal_universe_json(nested)
        return plain
    if isinstance(value, (list, tuple)):
        return [_plain_formal_universe_json(nested) for nested in value]
    return value


def _canonical_formal_universe_json(value: object, field: str) -> str:
    try:
        return _json(_plain_formal_universe_json(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be finite canonical JSON") from error


def _decode_canonical_formal_array(value: object, field: str) -> list[object]:
    if type(value) is not str:
        raise ValueError(f"stored formal universe {field} JSON must be text")
    try:
        decoded = json.loads(
            value,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"nonfinite JSON value: {constant}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"stored formal universe {field} JSON is invalid") from error
    if type(decoded) is not list:
        raise ValueError(f"stored formal universe {field} JSON is not an array")
    if _json(decoded) != value:
        raise ValueError(f"stored formal universe {field} JSON is not canonical")
    return decoded


def _formal_universe_member_payload(
    member: FormalUniverseMember,
) -> dict[str, object]:
    return {
        "exchange": member.exchange,
        "listing_status": member.listing_status,
        "raw_row": _plain_formal_universe_json(member.raw_row),
        "raw_row_hash": member.raw_row_hash,
        "security_id": member.security_id,
        "security_type": member.security_type,
    }


def _formal_universe_audit_payload(
    audit: FormalUniverseSourceAudit,
) -> dict[str, object]:
    return {
        "accepted_members_hash": audit.accepted_members_hash,
        "accepted_ordinary_a_count": audit.accepted_ordinary_a_count,
        "audit_hash": audit.audit_hash,
        "exchange": audit.exchange,
        "excluded_by_security_type": audit.excluded_by_security_type,
        "excluded_rows_hash": audit.excluded_rows_hash,
        "parsed_rows_hash": audit.parsed_rows_hash,
        "parser_id": audit.parser_id,
        "parser_version": audit.parser_version,
        "source_content_sha256": audit.source_content_sha256,
        "source_row_count": audit.source_row_count,
    }


def _formal_universe_extraction_payload(
    extraction: FormalUniverseExtraction,
) -> dict[str, object]:
    return {
        "audit": _formal_universe_audit_payload(extraction.audit),
        "exchange": extraction.exchange,
        "members": [
            _formal_universe_member_payload(member) for member in extraction.members
        ],
    }


def _formal_snapshot_ref_payload(ref: OfficialSnapshotRef) -> dict[str, object]:
    return {
        field: getattr(ref, field)
        for field in (
            "snapshot_id",
            "source",
            "dataset",
            "request_fingerprint",
            "security_id",
            "period_or_date",
            "exchange",
            "content_sha256",
            "manifest_sha256",
            "content_path",
            "manifest_path",
            "original_url",
            "published_at_utc",
            "published_precision",
            "source_updated_at_utc",
            "captured_at_utc",
            "effective_at_utc",
            "effective_time_evidence_hash",
            "refresh_generation",
            "producing_task_id",
            "parser_id",
            "parser_version",
            "mapping_version",
            "verification_status",
        )
    }


def _formal_frozen_universe_payload(
    frozen: FormalFrozenUniverseInput,
) -> dict[str, object]:
    return {
        "as_of_utc": frozen.as_of_utc,
        "frozen_input_hash": frozen.frozen_input_hash,
        "members": [
            _formal_universe_member_payload(member) for member in frozen.members
        ],
        "registry_manifest_hash": frozen.registry_manifest_hash,
        "source_audit_hash": frozen.source_audit_hash,
        "sources": [
            {
                "exchange": source.exchange,
                "extraction": _formal_universe_extraction_payload(source.extraction),
                "snapshot": _formal_snapshot_ref_payload(source.snapshot),
            }
            for source in frozen.sources
        ],
        "universe_hash": frozen.universe_hash,
    }


def _formal_universe_initial_status_evidence_hash(
    frozen_input_hash: str, security_id: str
) -> str:
    payload = {
        "frozen_input_hash": frozen_input_hash,
        "reasons": ["formal_collection_pending"],
        "security_id": security_id,
        "status": "pending_evidence",
        "veto_flags": [],
    }
    return hashlib.sha256(
        _canonical_formal_universe_json(
            payload, "formal universe initial status evidence"
        ).encode("utf-8")
    ).hexdigest()


def _require_formal_universe_status_values(
    *,
    security_id: object,
    status: object,
    reasons: object,
    veto_flags: object,
    evidence_hash: object,
    frozen_input_hash: str,
) -> tuple[str, str, tuple[str, ...], tuple[str, ...], str]:
    if type(security_id) is not str:
        raise ValueError("formal universe status security ID is invalid")
    try:
        canonical = canonical_security_id(security_id)
    except (TypeError, ValueError) as error:
        raise ValueError("formal universe status security ID is invalid") from error
    if canonical != security_id:
        raise ValueError("formal universe status security ID is not canonical")
    if type(status) is not str or status not in _FORMAL_UNIVERSE_STATUSES:
        raise ValueError("formal universe status is not recognized")
    if type(reasons) is not tuple or any(
        type(reason) is not str
        or not reason
        or reason != reason.strip()
        for reason in reasons
    ):
        raise ValueError("formal universe status reasons must be canonical strings")
    if type(veto_flags) is not tuple or any(
        type(flag) is not str
        or not flag
        or flag != flag.strip()
        for flag in veto_flags
    ):
        raise ValueError("formal universe status veto flags must be canonical strings")
    if tuple(sorted(reasons)) != reasons or len(set(reasons)) != len(reasons):
        raise ValueError("formal universe status reasons must be sorted and unique")
    if tuple(sorted(veto_flags)) != veto_flags or len(set(veto_flags)) != len(veto_flags):
        raise ValueError("formal universe status veto flags must be sorted and unique")
    if status in {"out_of_scope", "pending_evidence"} and not reasons:
        raise ValueError(f"{status} requires at least one reason")
    if status == "pool_vetoed" and not veto_flags:
        raise ValueError("pool_vetoed requires at least one veto flag")
    if status == "formal_scored" and veto_flags:
        raise ValueError("formal_scored cannot carry veto flags")
    digest = _require_formal_sha256(evidence_hash, "universe status evidence hash")
    if (
        status == "pending_evidence"
        and reasons == ("formal_collection_pending",)
        and not veto_flags
        and digest
        != _formal_universe_initial_status_evidence_hash(frozen_input_hash, security_id)
    ):
        raise ValueError("stored formal universe initial status evidence hash mismatch")
    return security_id, status, reasons, veto_flags, digest


def _require_canonical_uuid(value: object, field: str) -> str:
    if type(value) is not str:
        raise ValueError(f"stored formal {field} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise ValueError(f"stored formal {field} must be a canonical UUID") from error
    if str(parsed) != value:
        raise ValueError(f"stored formal {field} must be a canonical UUID")
    return value


def _require_canonical_utc(value: object, field: str) -> str:
    if type(value) is not str:
        raise ValueError(f"stored formal {field} must be canonical UTC")
    try:
        normalized = _utc_iso(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"stored formal {field} must be canonical UTC") from error
    if normalized != value or not value.endswith("+00:00"):
        raise ValueError(f"stored formal {field} must be canonical UTC")
    return value


def _require_formal_sha256(value: object, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"stored formal {field} must be a lowercase SHA-256")
    return value


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
    def __init__(
        self,
        db_path: str | Path,
        *,
        formal_snapshot_store: FormalSnapshotStore | None = None,
        registry_signature_verifier: object | None = None,
        formal_feature_bundle_store: FormalFeatureBundleStore | None = None,
    ):
        if formal_snapshot_store is not None and not isinstance(
            formal_snapshot_store, FormalSnapshotStore
        ):
            raise ValueError(
                "formal_snapshot_store must be a FormalSnapshotStore or None"
            )
        self.db_path = Path(db_path)
        self._formal_snapshot_store = formal_snapshot_store
        if registry_signature_verifier is not None and not callable(getattr(registry_signature_verifier, "verify", None)):
            raise ValueError("registry_signature_verifier must provide verify")
        if formal_feature_bundle_store is not None and type(formal_feature_bundle_store) is not FormalFeatureBundleStore:
            raise ValueError("formal_feature_bundle_store must have exact type")
        self._registry_signature_verifier = registry_signature_verifier
        self._formal_feature_bundle_store = formal_feature_bundle_store

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
        with self._transaction(immediate=True) as connection:
            tables = self._user_tables(connection)
            schemas = {
                2: (_V2_TABLE_DDL, _V2_INDEX_DDL),
                3: (_V3_TABLE_DDL, _V3_INDEX_DDL),
                4: (_V4_TABLE_DDL, _V4_INDEX_DDL),
                5: (_V5_TABLE_DDL, _V5_INDEX_DDL),
                6: (_V6_TABLE_DDL, _V6_INDEX_DDL),
            }
            if not tables:
                self._create_v2_schema(connection)
                connection.execute(_MIGRATION_TABLE_DDL)
                connection.execute("INSERT INTO schema_migration VALUES (2, ?)", (_utc_now(),))
                versions = {2}
            elif "schema_migration" not in tables:
                if tables != set(_V2_TABLE_DDL):
                    raise RuntimeError("database does not match the complete v2 schema")
                self._assert_v2_schema(connection)
                connection.execute(_MIGRATION_TABLE_DDL)
                connection.execute("INSERT INTO schema_migration VALUES (2, ?)", (_utc_now(),))
                versions = {2}
            else:
                self._assert_schema_ddl(connection, {"schema_migration": _MIGRATION_TABLE_DDL}, {}, "migration ledger")
                versions = {row[0] for row in connection.execute("SELECT version FROM schema_migration")}
                if any(type(v) is not int for v in versions) or versions not in (
                    {2}, {2, 3}, {2, 3, 4}, {2, 3, 4, 5}, {2, 3, 4, 5, 6}
                ):
                    raise RuntimeError(f"unsupported migration versions: {sorted(versions, key=str)}")
            objects = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
            for version, (table_ddl, index_ddl) in schemas.items():
                if version in versions:
                    self._assert_schema_ddl(connection, table_ddl, index_ddl, f"v{version} schema")
                elif objects & (set(table_ddl) | set(index_ddl)):
                    raise RuntimeError(f"unexpected v{version} schema before its migration ledger")
            for version in range(max(versions) + 1, 7):
                getattr(self, f"_apply_v{version}_migration")(connection)

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

    @classmethod
    def _apply_v6_migration(cls, connection: sqlite3.Connection) -> None:
        for statement in (*_V6_TABLE_DDL.values(), *_V6_INDEX_DDL.values()):
            connection.execute(statement)
        cls._assert_schema_ddl(connection, _V6_TABLE_DDL, _V6_INDEX_DDL, "v6 schema")
        connection.execute("INSERT INTO schema_migration VALUES (6, ?)", (_utc_now(),))

    @staticmethod
    def _formal_insert_row(connection, table: str, row: dict[str, object]) -> None:
        # Only fixed internal table/column names enter this helper.
        columns = tuple(row)
        connection.execute(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            tuple(row[k] for k in columns),
        )

    @staticmethod
    def _formal_security_filter(value: object) -> str:
        if type(value) is not str or canonical_security_id(value) != value:
            raise ValueError("formal security ID must be canonical")
        return value

    def _formal_fact_from_connection(self, connection, row) -> FormalFinancialFact:
        wire = dict(row)
        fact = FormalFinancialFact.from_dict(wire)
        wire = fact.to_dict()
        source = connection.execute("SELECT * FROM formal_source_snapshot WHERE id=?", (wire["source_snapshot_id"],)).fetchone()
        if source is None:
            raise ValueError("formal fact source snapshot is missing")
        ref = self._formal_verified_snapshot_ref_from_connection(connection, source)
        expected = {
            "security_id": ref.security_id, "period_end": ref.period_or_date,
            "source_snapshot_id": ref.snapshot_id, "source_content_sha256": ref.content_sha256,
            "source_refresh_generation": ref.refresh_generation, "source_producing_task_id": ref.producing_task_id,
            "parser_id": ref.parser_id, "parser_version": ref.parser_version, "mapping_version": ref.mapping_version,
            "published_at_utc": ref.published_at_utc, "published_precision": ref.published_precision,
            "effective_at_utc": ref.effective_at_utc, "effective_time_evidence_hash": ref.effective_time_evidence_hash,
            "source_updated_at_utc": ref.source_updated_at_utc, "captured_at_utc": ref.captured_at_utc,
        }
        if any(type(wire[k]) is not type(v) or wire[k] != v for k, v in expected.items()):
            raise ValueError("formal fact source lineage mismatch")
        return fact

    def insert_formal_financial_facts(self, facts: Iterable[FormalFinancialFact]) -> None:
        wires = []
        for fact in facts:
            if type(fact) is not FormalFinancialFact:
                raise ValueError("formal fact must have exact type")
            wires.append(fact.to_dict())
        with self._transaction(immediate=True) as connection:
            for wire in wires:
                self._formal_fact_from_connection(connection, wire)
                old = connection.execute("SELECT * FROM formal_financial_fact WHERE id=?", (wire["id"],)).fetchone()
                if old is not None:
                    previous = self._formal_fact_from_connection(connection, old).to_dict()
                    previous.pop("created_at_utc")
                    content = {k: v for k, v in wire.items() if k != "created_at_utc"}
                    if _json(previous) != _json(content):
                        raise ValueError("formal financial fact content conflict")
                else:
                    self._formal_insert_row(connection, "formal_financial_fact", wire)
            for wire in wires:
                row = connection.execute("SELECT * FROM formal_financial_fact WHERE id=?", (wire["id"],)).fetchone()
                if row is None:
                    raise ValueError("formal financial fact insert is missing")
                inserted = self._formal_fact_from_connection(connection, row).to_dict()
                if _json({k: v for k, v in inserted.items() if k != "created_at_utc"}) != _json({k: v for k, v in wire.items() if k != "created_at_utc"}):
                    raise ValueError("formal financial fact insert conflict")

    def list_formal_financial_facts(self, *, security_id: str | None = None) -> tuple[FormalFinancialFact, ...]:
        args = () if security_id is None else (self._formal_security_filter(security_id),)
        with self._transaction() as connection:
            rows = connection.execute("SELECT * FROM formal_financial_fact" + (" WHERE security_id=?" if args else ""), args).fetchall()
            facts = [self._formal_fact_from_connection(connection, row) for row in rows]
            return tuple(sorted(facts, key=lambda fact: _json({k: v for k, v in fact.to_dict().items() if k != "created_at_utc"})))

    def _formal_quarter_from_connection(self, connection, wire: dict) -> FormalQuarterFact:
        quarter = FormalQuarterFact.from_dict(wire)
        wire = quarter.to_dict()
        components = []
        for fact_id in wire["component_fact_ids"]:
            row = connection.execute("SELECT * FROM formal_financial_fact WHERE id=?", (fact_id,)).fetchone()
            if row is None:
                raise ValueError("formal quarter component fact is missing")
            components.append(self._formal_fact_from_connection(connection, row))
        candidates = derive_comparable_quarters(components).facts
        if not any(_json(candidate.to_dict()) == _json(wire) for candidate in candidates):
            raise ValueError("formal quarter does not match exact component rederivation")
        return quarter

    @staticmethod
    def _formal_quarter_wire(row) -> dict:
        wire = dict(row)
        _require_canonical_utc(wire.pop("created_at_utc"), "quarter creation time")
        for key in ("component_fact_ids", "evidence"):
            wire[key] = _decode_canonical_formal_array(wire.pop(key + "_json"), key)
        return wire

    def insert_formal_quarter_facts(self, quarters: Iterable[FormalQuarterFact]) -> None:
        wires = []
        for quarter in quarters:
            if type(quarter) is not FormalQuarterFact:
                raise ValueError("formal quarter must have exact type")
            wires.append(quarter.to_dict())
        with self._transaction(immediate=True) as connection:
            for wire in wires:
                self._formal_quarter_from_connection(connection, wire)
                old = connection.execute("SELECT * FROM formal_quarter_fact WHERE id=?", (wire["id"],)).fetchone()
                if old is not None:
                    previous = self._formal_quarter_from_connection(connection, self._formal_quarter_wire(old))
                    if _json(previous.to_dict()) != _json(wire):
                        raise ValueError("formal quarter content conflict")
                else:
                    row = dict(wire)
                    for key in ("component_fact_ids", "evidence"):
                        row[key + "_json"] = _json(row.pop(key))
                    row["created_at_utc"] = _require_canonical_utc(_utc_now(), "quarter creation time")
                    self._formal_insert_row(connection, "formal_quarter_fact", row)
            for wire in wires:
                row = connection.execute("SELECT * FROM formal_quarter_fact WHERE id=?", (wire["id"],)).fetchone()
                if row is None or _json(self._formal_quarter_from_connection(connection, self._formal_quarter_wire(row)).to_dict()) != _json(wire):
                    raise ValueError("formal quarter insert conflict")

    def list_formal_quarter_facts(self, *, security_id: str | None = None) -> tuple[FormalQuarterFact, ...]:
        args = () if security_id is None else (self._formal_security_filter(security_id),)
        with self._transaction() as connection:
            rows = connection.execute("SELECT * FROM formal_quarter_fact" + (" WHERE security_id=?" if args else ""), args).fetchall()
            quarters = [self._formal_quarter_from_connection(connection, self._formal_quarter_wire(row)) for row in rows]
            return tuple(sorted(quarters, key=lambda quarter: _json(quarter.to_dict())))

    def put_formal_context_facts(self, normalization) -> None:
        """Append a sealed semantic normalization through verified V6 lineage."""
        from .formal_context_repository import _put_context_facts
        with self._transaction(immediate=True) as connection:
            _put_context_facts(self, connection, normalization)

    def list_formal_context_facts(self, *, registry_manifest_hash: str,
            context_kind: str | None = None, scope_key: str | None = None,
            security_id: str | None = None, as_of_utc: str | None = None,
            source_snapshot_id: str | None = None):
        """Revalidate every stored Context record before returning detached facts."""
        from .formal_context_repository import _list_context_facts
        with self._transaction() as connection:
            return _list_context_facts(self, connection,
                registry_manifest_hash=registry_manifest_hash, context_kind=context_kind,
                scope_key=scope_key, security_id=security_id, as_of_utc=as_of_utc,
                source_snapshot_id=source_snapshot_id)

    def _require_registry_verifier(self):
        verifier = self._registry_signature_verifier
        if verifier is None or not callable(getattr(verifier, "verify", None)):
            raise ValueError("formal registry signature verifier is not configured")
        return verifier

    @staticmethod
    def _formal_token(value: object, field: str) -> str:
        if type(value) is not str or not value or value != value.strip() or not value.isprintable():
            raise ValueError(f"{field} must be an exact canonical token")
        return value

    def _verify_formal_signature(self, raw: bytes, signature: object, key_id: object) -> None:
        signature = self._formal_token(signature, "signature")
        key_id = self._formal_token(key_id, "key ID")
        try:
            result = self._require_registry_verifier().verify(raw, signature=signature, key_id=key_id)
        except Exception as error:
            raise ValueError("formal registry signature verification failed") from error
        if result is not True:
            raise ValueError("formal registry signature verification failed")

    def _formal_blob_snapshot(self, blob: VerifiedRegistryBlob) -> dict:
        self._require_registry_verifier()
        if type(blob) is not VerifiedRegistryBlob:
            raise ValueError("formal registry blob must have exact type")
        try:
            wire = {key: getattr(blob, key) for key in _FORMAL_BLOB_FIELDS}
        except AttributeError as error:
            raise ValueError("formal registry blob envelope is incomplete") from error
        raw = wire["canonical_json"]
        if type(raw) is not bytes:
            raise ValueError("formal registry canonical JSON must be exact bytes")
        try:
            parsed = _decode_canonical_formal_json(raw.decode("utf-8"), "registry blob")
        except UnicodeError as error:
            raise ValueError("formal registry canonical JSON must be UTF-8") from error
        role = self._formal_token(wire["registry_role"], "registry role")
        if role not in _FORMAL_REGISTRY_ROLES or parsed.get("registry_role") != role:
            raise ValueError("formal registry child role mismatch")
        registry_hash = _require_formal_sha256(wire["registry_hash"], "registry hash")
        if hashlib.sha256(raw).hexdigest() != registry_hash:
            raise ValueError("formal registry child hash mismatch")
        root_hash = _require_formal_sha256(wire["declared_registry_manifest_hash"], "declared registry root")
        if wire["approval_id"] is not None:
            self._formal_token(wire["approval_id"], "approval ID")
        self._verify_formal_signature(raw, wire["signature"], wire["key_id"])
        binding = _json({"child_sha256": registry_hash, "registry_manifest_hash": root_hash, "registry_role": role}).encode("utf-8")
        self._verify_formal_signature(binding, wire["binding_signature"], wire["binding_key_id"])
        return wire

    def _formal_blob_from_connection(self, connection, registry_hash: str):
        self._require_registry_verifier()
        row = connection.execute("SELECT * FROM formal_registry_blob WHERE registry_hash=?", (registry_hash,)).fetchone()
        if row is None:
            return None
        _require_canonical_utc(row["created_at_utc"], "registry blob creation time")
        wire = self._formal_blob_snapshot(VerifiedRegistryBlob(**{key: row[key] for key in _FORMAL_BLOB_FIELDS}))
        if wire["registry_hash"] != registry_hash:
            raise ValueError("registry child stored identity mismatch")
        return VerifiedRegistryBlob(**wire)

    def put_formal_registry_blob(self, blob: VerifiedRegistryBlob) -> None:
        wire = self._formal_blob_snapshot(blob)
        with self._transaction(immediate=True) as connection:
            old = self._formal_blob_from_connection(connection, wire["registry_hash"])
            if old is not None:
                if self._formal_blob_snapshot(old) != wire:
                    raise ValueError("formal registry blob immutable envelope conflict")
            else:
                self._formal_insert_row(connection, "formal_registry_blob", {**wire, "created_at_utc": _require_canonical_utc(_utc_now(), "registry creation time")})
            inserted = self._formal_blob_from_connection(connection, wire["registry_hash"])
            if inserted is None or self._formal_blob_snapshot(inserted) != wire:
                raise ValueError("formal registry blob insert conflict")

    def get_formal_registry_blob(self, registry_hash: str) -> VerifiedRegistryBlob | None:
        registry_hash = _require_formal_sha256(registry_hash, "registry hash")
        with self._transaction() as connection:
            return self._formal_blob_from_connection(connection, registry_hash)

    def _formal_root_snapshot(self, manifest: FormalRegistryManifest) -> dict:
        verifier = self._require_registry_verifier()
        if type(manifest) is not FormalRegistryManifest:
            raise ValueError("formal registry manifest must have exact type")
        try:
            hashes = {f"{role}_registry_hash": getattr(manifest, f"{role}_registry_hash") for role in _FORMAL_REGISTRY_ROLES}
            manifest.assert_member_hashes(**hashes)
            wire = {key: getattr(manifest, key) for key in _FORMAL_ROOT_FIELDS}
        except AttributeError as error:
            raise ValueError("formal registry manifest is incomplete") from error
        fresh = FormalRegistryManifest.from_signed_bytes(wire["canonical_json"], wire["signature"], wire["key_id"], verifier)
        expected = {key: getattr(fresh, key) for key in _FORMAL_ROOT_FIELDS}
        if any(type(wire[k]) is not type(v) or wire[k] != v for k, v in expected.items()):
            raise ValueError("formal registry manifest public fields mismatch")
        return expected

    def _formal_root_from_connection(self, connection, manifest_hash: str):
        verifier = self._require_registry_verifier()
        row = connection.execute("SELECT * FROM formal_registry_manifest WHERE manifest_hash=?", (manifest_hash,)).fetchone()
        if row is None:
            return None
        _require_canonical_utc(row["created_at_utc"], "registry root creation time")
        fresh = FormalRegistryManifest.from_signed_bytes(row["canonical_json"], row["signature"], row["key_id"], verifier)
        expected = self._formal_root_snapshot(fresh)
        if any(type(row[k]) is not type(v) or row[k] != v for k, v in expected.items()):
            raise ValueError("formal registry root stored fields mismatch")
        return fresh

    def _formal_registry_bundle_from_connection(self, connection, manifest_hash, pending_root=None):
        owner = self

        class Repository:
            def get_formal_registry_manifest(self, key):
                if pending_root is not None and key == manifest_hash:
                    return pending_root
                return owner._formal_root_from_connection(connection, key)

            def get_formal_registry_blob(self, key):
                return owner._formal_blob_from_connection(connection, key)

        return FormalRegistryBundleLoader(Repository(), self._require_registry_verifier()).load(manifest_hash)

    def put_formal_registry_manifest(self, manifest: FormalRegistryManifest) -> None:
        wire = self._formal_root_snapshot(manifest)
        detached = FormalRegistryManifest.from_signed_bytes(wire["canonical_json"], wire["signature"], wire["key_id"], self._require_registry_verifier())
        with self._transaction(immediate=True) as connection:
            self._formal_registry_bundle_from_connection(connection, wire["manifest_hash"], detached)
            old = self._formal_root_from_connection(connection, wire["manifest_hash"])
            if old is not None:
                if self._formal_root_snapshot(old) != wire:
                    raise ValueError("formal registry root immutable envelope conflict")
            else:
                self._formal_insert_row(connection, "formal_registry_manifest", {**wire, "created_at_utc": _require_canonical_utc(_utc_now(), "registry creation time")})
            loaded = self._formal_registry_bundle_from_connection(connection, wire["manifest_hash"])
            if self._formal_root_snapshot(loaded.manifest) != wire:
                raise ValueError("formal registry root insert conflict")

    def get_formal_registry_manifest(self, manifest_hash: str) -> FormalRegistryManifest | None:
        manifest_hash = _require_formal_sha256(manifest_hash, "manifest hash")
        with self._transaction() as connection:
            return self._formal_root_from_connection(connection, manifest_hash)

    def list_formal_tasks(self, *, kinds: Sequence[str] | None = None, statuses: Sequence[str] | None = None) -> list[dict[str, object]]:
        clauses, args = [], []
        empty = False
        for name, values in (("kind", kinds), ("status", statuses)):
            if values is None:
                continue
            if type(values) not in (tuple, list):
                raise ValueError("formal task filters must be exact lists or tuples")
            requested = tuple(self._formal_token(value, name) for value in values)
            if name == "status" and any(value not in FORMAL_TASK_STATES for value in requested):
                raise ValueError("formal task status filter is invalid")
            if not requested:
                empty = True
            else:
                clauses.append(f"{name} IN ({','.join('?' for _ in requested)})")
                args.extend(requested)
        if empty:
            return []
        with self._transaction() as connection:
            rows = connection.execute("SELECT * FROM formal_collection_task" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY created_at, id", args).fetchall()
            result = []
            for row in rows:
                prerequisites = [item[0] for item in connection.execute("SELECT prerequisite_task_id FROM formal_collection_task_dependency WHERE task_id=? ORDER BY prerequisite_task_id", (row["id"],))]
                self._formal_token(row["kind"], "stored task kind")
                if type(row["status"]) is not str or row["status"] not in FORMAL_TASK_STATES:
                    raise ValueError("stored formal task status is invalid")
                result.append(self._formal_task_public(row, prerequisites))
            return result

    def _formal_circuit_payload(self, source, state, failure_count, reason, opened_at_utc, retry_after_utc):
        source = self._formal_token(source, "source")
        if type(state) is not str or state not in {"open", "closed"}:
            raise ValueError("formal source circuit state is invalid")
        if type(failure_count) is not int or failure_count < 0:
            raise ValueError("formal source circuit failure count is invalid")
        def snapshot(value):
            if type(value) is dict:
                return {self._formal_json_key(k): snapshot(v) for k, v in value.items()}
            if type(value) is list:
                return [snapshot(v) for v in value]
            if value is None or type(value) in (str, bool, int, float):
                return value
            raise ValueError("formal circuit reason requires exact JSON types")
        if type(reason) is not dict:
            raise ValueError("formal circuit reason must be an exact mapping")
        try:
            reason_json = _json(snapshot(reason))
        except (TypeError, ValueError, RecursionError) as error:
            raise ValueError("formal circuit reason must be finite canonical JSON") from error
        if state == "closed":
            if failure_count != 0 or reason_json != "{}" or opened_at_utc is not None or retry_after_utc is not None:
                raise ValueError("closed formal circuit must have no failure state")
        else:
            opened_at_utc = _require_canonical_utc(opened_at_utc, "circuit opened time")
            retry_after_utc = _require_canonical_utc(retry_after_utc, "circuit retry time")
            if failure_count <= 0 or reason_json == "{}" or datetime.fromisoformat(retry_after_utc) < datetime.fromisoformat(opened_at_utc):
                raise ValueError("open formal circuit requires failures, reason and ordered times")
        return dict(source=source, state=state, failure_count=failure_count, reason_json=reason_json, opened_at_utc=opened_at_utc, retry_after_utc=retry_after_utc)

    @staticmethod
    def _formal_json_key(key):
        if type(key) is not str:
            raise ValueError("formal JSON keys must be exact strings")
        return key

    def _formal_circuit_from_connection(self, connection, source):
        row = connection.execute("SELECT * FROM formal_source_circuit WHERE source=?", (source,)).fetchone()
        if row is None:
            return None
        reason = _decode_canonical_formal_json(row["reason_json"], "circuit reason")
        expected = self._formal_circuit_payload(row["source"], row["state"], row["failure_count"], reason, row["opened_at_utc"], row["retry_after_utc"])
        expected["updated_at_utc"] = _require_canonical_utc(row["updated_at_utc"], "circuit update time")
        if any(type(row[k]) is not type(v) or row[k] != v for k, v in expected.items()):
            raise ValueError("formal source circuit row is not canonical")
        expected.pop("reason_json")
        expected["reason"] = reason
        return expected

    def get_formal_source_circuit(self, source: str) -> dict[str, object] | None:
        source = self._formal_token(source, "source")
        with self._transaction() as connection:
            return self._formal_circuit_from_connection(connection, source)

    def set_formal_source_circuit(self, source: str, *, state: str, failure_count: int, reason: Mapping[str, object], opened_at_utc: str | None, retry_after_utc: str | None) -> None:
        wire = self._formal_circuit_payload(source, state, failure_count, reason, opened_at_utc, retry_after_utc)
        with self._transaction(immediate=True) as connection:
            old = self._formal_circuit_from_connection(connection, wire["source"])
            if old is not None:
                previous = {k: v for k, v in old.items() if k != "updated_at_utc"}
                previous["reason_json"] = _json(previous.pop("reason"))
                if previous == wire:
                    return
            wire["updated_at_utc"] = _require_canonical_utc(_utc_now(), "circuit update time")
            if old is None:
                self._formal_insert_row(connection, "formal_source_circuit", wire)
            else:
                connection.execute("UPDATE formal_source_circuit SET state=?,failure_count=?,reason_json=?,opened_at_utc=?,retry_after_utc=?,updated_at_utc=? WHERE source=?", tuple(wire[k] for k in ("state", "failure_count", "reason_json", "opened_at_utc", "retry_after_utc", "updated_at_utc", "source")))
            result = self._formal_circuit_from_connection(connection, wire["source"])
            if result is None:
                raise ValueError("formal circuit update is missing")
            result["reason_json"] = _json(result.pop("reason"))
            if result != wire:
                raise ValueError("formal circuit update conflict")

    def _formal_bundle_receipt_snapshot(self, stored, canonical: bytes) -> dict:
        store = self._formal_feature_bundle_store
        if type(store) is not FormalFeatureBundleStore or type(stored) is not FormalStoredFeatureBundle:
            raise ValueError("formal feature bundle store and live receipt are required")
        verified = store.read_verified(stored)
        if type(verified) is not FormalFeatureBundle or verified.canonical_bytes() != canonical:
            raise ValueError("formal feature live receipt bytes mismatch")
        receipt = {key: getattr(stored, key) for key in ("bundle_hash", "manifest_hash", "bundle_path", "manifest_path")}
        if any(type(v) is not str for v in receipt.values()) or receipt["bundle_hash"] != hashlib.sha256(canonical).hexdigest():
            raise ValueError("formal feature receipt hash mismatch")
        _require_formal_sha256(receipt["manifest_hash"], "feature manifest hash")
        return receipt

    def _validate_formal_bundle_sources(self, connection, wire: dict) -> None:
        root_bundle = self._formal_registry_bundle_from_connection(connection, wire["registry_manifest_hash"])
        child = root_bundle.blob("feature")
        if child.registry_hash != wire["feature_registry_hash"]:
            raise ValueError("formal feature child registry header mismatch")
        registry = load_signed_feature_registry(child.canonical_json, child.signature, child.key_id,
            self._require_registry_verifier(), registry_manifest=root_bundle.manifest)
        slots = registry.slots_for_template(wire["template_id"])
        if registry.source_registry_hash != root_bundle.manifest.source_registry_hash or registry.mapping_registry_hash != root_bundle.manifest.mapping_registry_hash:
            raise ValueError("formal feature child source/mapping root binding mismatch")
        if registry.contract_version != wire["contract_version"] or [slot.slot_id for slot in slots] != [value["slot_id"] for value in wire["values"]]:
            raise ValueError("formal feature signed header or applicable slots mismatch")
        cutoff = datetime.fromisoformat(wire["as_of_utc"])
        for slot, value in zip(slots, wire["values"], strict=True):
            if value["unit"] != slot.unit or value["formula_version"] != slot.formula_version:
                raise ValueError("formal feature signed unit or formula version mismatch")
            for evidence in value["evidence"]:
                row = connection.execute("SELECT * FROM formal_financial_fact WHERE id=?", (evidence["formal_fact_id"],)).fetchone()
                if row is None:
                    raise ValueError("formal feature evidence fact is missing")
                fact = self._formal_fact_from_connection(connection, row)
                fact_wire = fact.to_dict()
                if fact_wire["security_id"] != wire["security_id"] or _json(FormalEvidenceRef.from_formal_fact(fact).to_dict()) != _json(evidence):
                    raise ValueError("formal feature evidence lineage mismatch")
                for field in ("published_at_utc", "effective_at_utc", "source_updated_at_utc"):
                    if fact_wire[field] is not None and datetime.fromisoformat(fact_wire[field]) > cutoff:
                        raise ValueError("formal feature evidence is after cutoff")

    @staticmethod
    def _formal_feature_projection(wire: dict, receipt: dict) -> tuple[dict, list[dict]]:
        header = {k: v for k, v in wire.items() if k != "values"}
        for key in ("history_endpoints", "comparable_quarter_keys", "blockers"):
            header[key + "_json"] = _json(header.pop(key))
        header.update(id=receipt["bundle_hash"], bundle_hash=receipt["bundle_hash"],
            bundle_manifest_hash=receipt["manifest_hash"], bundle_path=receipt["bundle_path"], manifest_path=receipt["manifest_path"])
        values = []
        for item in wire["values"]:
            value = dict(item)
            value["feature_set_id"] = receipt["bundle_hash"]
            value["evidence_json"] = _json(value.pop("evidence"))
            values.append(value)
        return header, values

    def _formal_feature_metadata_from_connection(self, connection, input_hash: str):
        row = connection.execute("SELECT * FROM formal_feature_set WHERE input_hash=?", (input_hash,)).fetchone()
        if row is None:
            return None
        header = dict(row)
        _require_canonical_utc(header["created_at_utc"], "feature creation time")
        _require_canonical_utc(header["as_of_utc"], "feature cutoff")
        self._formal_security_filter(header["security_id"])
        for key in ("id", "input_hash", "registry_manifest_hash", "feature_registry_hash", "bundle_hash", "bundle_manifest_hash"):
            _require_formal_sha256(header[key], key)
        if header["input_hash"] != input_hash or header["id"] != header["bundle_hash"]:
            raise ValueError("formal feature metadata identity mismatch")
        for key in ("contract_version", "template_id", "bundle_path", "manifest_path"):
            self._formal_token(header[key], key)
        if type(header["schema_version"]) is not int or header["schema_version"] != 1:
            raise ValueError("formal feature metadata schema version mismatch")
        for key in ("history_endpoints", "comparable_quarter_keys", "blockers"):
            header[key] = _decode_canonical_formal_array(header.pop(key + "_json"), key)
        values = []
        for stored_value in connection.execute("SELECT * FROM formal_feature_value WHERE feature_set_id=? ORDER BY slot_id", (header["id"],)):
            value = dict(stored_value)
            value.pop("feature_set_id")
            value["evidence"] = _decode_canonical_formal_array(value.pop("evidence_json"), "feature evidence")
            values.append(FormalFeatureValue.from_dict(value).to_dict())
        header["values"] = values
        # This is a plain metadata integrity check, not a trusted bundle or an input-hash reconstruction.
        bundle_wire = {k: header[k] for k in ("schema_version", "contract_version", "security_id", "as_of_utc", "template_id", "registry_manifest_hash", "feature_registry_hash", "input_hash", "values", "history_endpoints", "comparable_quarter_keys", "blockers")}
        if hashlib.sha256(_json(bundle_wire).encode("utf-8")).hexdigest() != header["bundle_hash"]:
            raise ValueError("formal feature metadata bundle hash mismatch")
        return header

    def put_formal_feature_bundle(self, bundle: FormalFeatureBundle, stored: FormalStoredFeatureBundle) -> tuple[str, bool]:
        if type(bundle) is not FormalFeatureBundle:
            raise ValueError("formal feature bundle must have exact type")
        wire = bundle.to_dict()
        canonical = bundle.canonical_bytes()
        if _json(wire).encode("utf-8") != canonical:
            raise ValueError("formal feature bundle snapshot changed")
        receipt = self._formal_bundle_receipt_snapshot(stored, canonical)
        header, values = self._formal_feature_projection(wire, receipt)
        with self._transaction(immediate=True) as connection:
            self._validate_formal_bundle_sources(connection, wire)
            old = self._formal_feature_metadata_from_connection(connection, wire["input_hash"])
            inserted = old is None
            if inserted:
                self._formal_insert_row(connection, "formal_feature_set", {**header, "created_at_utc": _require_canonical_utc(_utc_now(), "feature creation time")})
                for value in values:
                    self._formal_insert_row(connection, "formal_feature_value", value)
            actual_header = connection.execute("SELECT * FROM formal_feature_set WHERE input_hash=?", (wire["input_hash"],)).fetchone()
            actual_values = [dict(row) for row in connection.execute("SELECT * FROM formal_feature_value WHERE feature_set_id=? ORDER BY slot_id", (header["id"],))]
            if actual_header is None or any(type(actual_header[k]) is not type(v) or actual_header[k] != v for k, v in header.items()) or actual_values != values:
                raise ValueError("formal feature immutable input hash conflict")
            self._formal_feature_metadata_from_connection(connection, wire["input_hash"])
            self._validate_formal_bundle_sources(connection, wire)
            if self._formal_bundle_receipt_snapshot(stored, canonical) != receipt:
                raise ValueError("formal feature receipt changed during persistence")
            return header["id"], inserted

    def get_formal_feature_bundle_row(self, input_hash: str) -> dict[str, object] | None:
        input_hash = _require_formal_sha256(input_hash, "feature input hash")
        with self._transaction() as connection:
            return self._formal_feature_metadata_from_connection(connection, input_hash)

    def _require_formal_snapshot_store(self) -> FormalSnapshotStore:
        if self._formal_snapshot_store is None:
            raise ValueError("formal snapshot store is not configured")
        return self._formal_snapshot_store

    def _configured_formal_snapshot_store_for_repository(self) -> FormalSnapshotStore:
        """Expose the one configured formal raw boundary to the sibling repository.

        This deliberately returns the already-injected instance.  A repository must not
        infer a raw root or construct a second store, because that would lose the trusted
        date-only calendar resolver carried by the configured instance.
        """
        return self._require_formal_snapshot_store()

    @staticmethod
    def _require_formal_repository_identifier(value: object, field: str) -> str:
        if type(value) is not str or not value or value != value.strip():
            raise ValueError(f"{field} must be an already-trimmed nonempty string")
        return value

    def _formal_repository_request_identity(
        self, request: object
    ) -> tuple[OfficialRequest, str, str]:
        """Return the canonical request JSON/fingerprint for a strict lookup request."""
        raw_store = self._require_formal_snapshot_store()
        if type(request) is not OfficialRequest:
            raise ValueError("request must have exact type OfficialRequest")
        try:
            raw_store._validate_request_values(request)
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("formal repository request is invalid") from error
        request_json_bytes = request.canonical_json_bytes()
        if type(request_json_bytes) is not bytes:
            raise ValueError("formal repository request JSON is invalid")
        try:
            request_json = request_json_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("formal repository request JSON is invalid") from error
        payload = _decode_canonical_formal_json(request_json, "formal repository request")
        if frozenset(payload) != _FORMAL_REQUEST_IDENTITY_KEYS or payload != {
            "source": request.source,
            "dataset": request.dataset,
            "security_id": request.security_id,
            "period_or_date": request.period_or_date,
            "exchange": request.exchange,
        }:
            raise ValueError("formal repository request identity is invalid")
        return request, request_json, hashlib.sha256(request_json_bytes).hexdigest()

    @staticmethod
    def _require_formal_repository_as_of(value: object) -> str:
        if type(value) is not str:
            raise ValueError("as_of_utc must be a canonical timezone-aware timestamp")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(
                "as_of_utc must be a canonical timezone-aware timestamp"
            ) from error
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() is None
            or parsed.isoformat() != value
        ):
            raise ValueError("as_of_utc must be a canonical timezone-aware timestamp")
        return value

    @staticmethod
    def _formal_ref_matches_repository_request(
        ref: OfficialSnapshotRef,
        request: OfficialRequest,
        request_fingerprint: str,
    ) -> bool:
        return (
            ref.source == request.source
            and ref.dataset == request.dataset
            and ref.security_id == request.security_id
            and ref.period_or_date == request.period_or_date
            and ref.exchange == request.exchange
            and ref.request_fingerprint == request_fingerprint
        )

    def _require_formal_snapshot_receipt_lineage(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        ref: OfficialSnapshotRef,
    ) -> None:
        """Verify the source-row/receipt/task graph for one revalidated reference."""
        if row["id"] != ref.snapshot_id or row["manifest_sha256"] != ref.manifest_sha256:
            raise ValueError("formal snapshot row identity mismatch")
        receipt_rows = connection.execute(
            "SELECT * FROM formal_task_snapshot_receipt WHERE snapshot_id = ?",
            (ref.snapshot_id,),
        ).fetchall()
        producer_task_id = ref.producing_task_id
        if producer_task_id is None:
            if receipt_rows:
                raise ValueError("formal bootstrap snapshot must not have a receipt")
            return

        task_id = _require_canonical_uuid(
            producer_task_id, "snapshot producing task ID"
        )
        if len(receipt_rows) != 1:
            raise ValueError("formal task-produced snapshot requires exactly one receipt")
        receipt = receipt_rows[0]
        if (
            _require_canonical_uuid(receipt["task_id"], "receipt task ID") != task_id
            or _require_canonical_uuid(receipt["snapshot_id"], "receipt snapshot ID")
            != ref.snapshot_id
            or _require_formal_sha256(
                receipt["manifest_sha256"], "receipt manifest hash"
            )
            != ref.manifest_sha256
        ):
            raise ValueError("formal snapshot receipt linkage mismatch")
        receipt_generation = receipt["refresh_generation"]
        if (
            type(receipt_generation) is not str
            or not receipt_generation
            or receipt_generation != ref.refresh_generation
        ):
            raise ValueError("formal snapshot receipt generation mismatch")
        _require_canonical_utc(receipt["recorded_at"], "receipt time")

        producer_rows = connection.execute(
            """SELECT id FROM formal_source_snapshot
            WHERE producing_task_id = ? ORDER BY id""",
            (task_id,),
        ).fetchall()
        if [str(item["id"]) for item in producer_rows] != [ref.snapshot_id]:
            raise ValueError("formal snapshot producer set mismatch")
        task_row = connection.execute(
            "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
        ).fetchone()
        if task_row is None or task_row["id"] != task_id:
            raise ValueError("formal snapshot receipt task is missing")
        prerequisites = [
            str(item["prerequisite_task_id"])
            for item in connection.execute(
                """SELECT prerequisite_task_id
                FROM formal_collection_task_dependency
                WHERE task_id = ? ORDER BY prerequisite_task_id""",
                (task_id,),
            )
        ]
        task = self._formal_task_public(task_row, prerequisites)
        if task["kind"] not in _FORMAL_SOURCE_FETCH_KINDS:
            raise ValueError("formal snapshot receipt task is not a source task")
        if task["refresh_generation"] != ref.refresh_generation:
            raise ValueError("formal snapshot task generation mismatch")

    def _formal_verified_snapshot_ref_from_connection(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> OfficialSnapshotRef:
        ref = self._formal_snapshot_row_to_ref(row)
        self._require_formal_snapshot_receipt_lineage(connection, row, ref)
        return ref

    def _formal_repository_candidates_from_connection(
        self, connection: sqlite3.Connection
    ) -> list[OfficialSnapshotRef]:
        """Revalidate every snapshot before applying caller-owned lookup identity."""
        rows = connection.execute(
            "SELECT * FROM formal_source_snapshot ORDER BY manifest_sha256"
        ).fetchall()
        return [
            self._formal_verified_snapshot_ref_from_connection(connection, row)
            for row in rows
        ]

    def _find_formal_snapshot_exact_verified(
        self,
        request: OfficialRequest,
        *,
        parser_id: str,
        parser_version: str,
        mapping_version: str,
        content_sha256: str,
        manifest_sha256: str,
    ) -> OfficialSnapshotRef | None:
        request, _request_json, request_fingerprint = self._formal_repository_request_identity(
            request
        )
        parser_id = self._require_formal_repository_identifier(parser_id, "parser_id")
        parser_version = self._require_formal_repository_identifier(
            parser_version, "parser_version"
        )
        mapping_version = self._require_formal_repository_identifier(
            mapping_version, "mapping_version"
        )
        content_sha256 = _require_formal_sha256(content_sha256, "content hash")
        manifest_sha256 = _require_formal_sha256(manifest_sha256, "manifest hash")
        with self._transaction() as connection:
            candidates = self._formal_repository_candidates_from_connection(connection)
            matches = [
                ref
                for ref in candidates
                if self._formal_ref_matches_repository_request(
                    ref, request, request_fingerprint
                )
                and ref.parser_id == parser_id
                and ref.parser_version == parser_version
                and ref.mapping_version == mapping_version
                and ref.content_sha256 == content_sha256
                and ref.manifest_sha256 == manifest_sha256
            ]
            if len(matches) > 1:
                raise ValueError("formal exact snapshot lookup is ambiguous")
            return matches[0] if matches else None

    def _find_formal_snapshot_visible_verified(
        self,
        request: OfficialRequest,
        *,
        parser_id: str,
        parser_version: str,
        mapping_version: str,
        as_of_utc: str,
    ) -> OfficialSnapshotRef | None:
        request, _request_json, request_fingerprint = self._formal_repository_request_identity(
            request
        )
        parser_id = self._require_formal_repository_identifier(parser_id, "parser_id")
        parser_version = self._require_formal_repository_identifier(
            parser_version, "parser_version"
        )
        mapping_version = self._require_formal_repository_identifier(
            mapping_version, "mapping_version"
        )
        as_of_utc = self._require_formal_repository_as_of(as_of_utc)
        with self._transaction() as connection:
            candidates = self._formal_repository_candidates_from_connection(connection)
            visible = [
                ref
                for ref in candidates
                if self._formal_ref_matches_repository_request(
                    ref, request, request_fingerprint
                )
                and ref.parser_id == parser_id
                and ref.parser_version == parser_version
                and ref.mapping_version == mapping_version
                and is_visible_at(ref.effective_at_utc, as_of_utc)
            ]
            if not visible:
                return None
            return min(
                visible,
                key=lambda ref: (
                    formal_version_sort_key(_FormalSnapshotVersion(ref)),
                    ref.manifest_sha256,
                ),
            )

    def _get_formal_snapshot_verified_by_manifest(
        self, manifest_sha256: str
    ) -> OfficialSnapshotRef | None:
        manifest_sha256 = _require_formal_sha256(manifest_sha256, "manifest hash")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE manifest_sha256 = ?",
                (manifest_sha256,),
            ).fetchone()
            if row is None:
                return None
            return self._formal_verified_snapshot_ref_from_connection(connection, row)

    def _formal_snapshot_row_to_ref(self, row: sqlite3.Row) -> OfficialSnapshotRef:
        raw_store = self._require_formal_snapshot_store()
        snapshot_id = _require_canonical_uuid(row["id"], "snapshot ID")
        request_payload = _decode_canonical_formal_json(row["request_json"], "request")
        if frozenset(request_payload) != _FORMAL_REQUEST_IDENTITY_KEYS:
            raise ValueError("stored formal snapshot request identity keys mismatch")
        verification_payload = _decode_canonical_formal_json(
            row["verification_json"], "verification"
        )
        if frozenset(verification_payload) != _FORMAL_VERIFICATION_KEYS:
            raise ValueError("stored formal snapshot verification keys mismatch")
        reasons = verification_payload["reasons"]
        if type(reasons) is not list or any(type(reason) is not str for reason in reasons):
            raise ValueError("stored formal snapshot verification reasons are invalid")
        if verification_payload["status"] != "verified":
            raise ValueError("stored formal snapshot verification is not verified")

        request_json = str(row["request_json"])
        request_fingerprint = _require_formal_sha256(
            row["request_fingerprint"], "request fingerprint"
        )
        if request_fingerprint != hashlib.sha256(request_json.encode("utf-8")).hexdigest():
            raise ValueError("stored formal snapshot request fingerprint mismatch")
        request = OfficialRequest(
            source=request_payload["source"],
            dataset=request_payload["dataset"],
            security_id=request_payload["security_id"],
            period_or_date=request_payload["period_or_date"],
            exchange=request_payload["exchange"],
        )
        stored = FormalStoredSnapshot(
            content_path=row["content_path"],
            manifest_path=row["manifest_path"],
            content_sha256=_require_formal_sha256(row["content_sha256"], "content hash"),
            manifest_sha256=_require_formal_sha256(row["manifest_sha256"], "manifest hash"),
        )
        raw_bytes = raw_store.read_verified_raw(stored)
        verification = EvidenceVerification(
            status=verification_payload["status"],
            content_sha256=verification_payload["content_sha256"],
            reasons=tuple(reasons),
            effective_at_utc=verification_payload["effective_at_utc"],
        )
        fetch = OfficialFetch(
            request=request,
            raw_bytes=raw_bytes,
            original_url=row["original_url"],
            published_at_utc=row["published_at_utc"],
            published_precision=row["published_precision"],
            source_updated_at_utc=row["source_updated_at_utc"],
            captured_at_utc=row["captured_at_utc"],
            effective_at_utc=row["effective_at_utc"],
            effective_time_evidence_hash=row["effective_time_evidence_hash"],
            refresh_generation=row["refresh_generation"],
            parser_id=row["parser_id"],
            parser_version=row["parser_version"],
            mapping_version=row["mapping_version"],
            declared_security_id=request.security_id,
            declared_period=request.period_or_date,
        )
        validated = raw_store.validate_stored_snapshot(
            fetch,
            stored,
            verification,
            expected_producing_task_id=row["producing_task_id"],
        )
        if type(validated) is not ValidatedFormalSnapshot:
            raise ValueError("formal snapshot validation returned an invalid projection")
        for field in (
            "source", "dataset", "request_json", "request_fingerprint",
            "content_sha256", "manifest_sha256", "content_path", "manifest_path",
            "original_url", "published_at_utc", "published_precision",
            "source_updated_at_utc", "captured_at_utc", "effective_at_utc",
            "effective_time_evidence_hash", "parser_id", "parser_version",
            "mapping_version", "refresh_generation", "producing_task_id",
            "verification_json",
        ):
            stored_value = row[field]
            validated_value = getattr(validated, field)
            if type(stored_value) is not type(validated_value) or stored_value != validated_value:
                raise ValueError(f"stored formal snapshot {field} mismatch")
        _require_canonical_utc(row["created_at"], "snapshot creation time")
        return OfficialSnapshotRef(
            snapshot_id=snapshot_id,
            source=validated.source,
            dataset=validated.dataset,
            request_fingerprint=validated.request_fingerprint,
            security_id=validated.security_id,
            period_or_date=validated.period_or_date,
            exchange=validated.exchange,
            content_sha256=validated.content_sha256,
            manifest_sha256=validated.manifest_sha256,
            content_path=validated.content_path,
            manifest_path=validated.manifest_path,
            original_url=validated.original_url,
            published_at_utc=validated.published_at_utc,
            published_precision=validated.published_precision,
            source_updated_at_utc=validated.source_updated_at_utc,
            captured_at_utc=validated.captured_at_utc,
            effective_at_utc=validated.effective_at_utc,
            effective_time_evidence_hash=validated.effective_time_evidence_hash,
            refresh_generation=validated.refresh_generation,
            producing_task_id=validated.producing_task_id,
            parser_id=validated.parser_id,
            parser_version=validated.parser_version,
            mapping_version=validated.mapping_version,
            verification_status="verified",
        )

    @staticmethod
    def _formal_ref_matches_projection(
        ref: OfficialSnapshotRef, validated: ValidatedFormalSnapshot
    ) -> bool:
        return all(
            getattr(ref, field) == getattr(validated, field)
            for field in (
                "source", "dataset", "request_fingerprint", "security_id",
                "period_or_date", "exchange", "content_sha256", "manifest_sha256",
                "content_path", "manifest_path", "original_url", "published_at_utc",
                "published_precision", "source_updated_at_utc", "captured_at_utc",
                "effective_at_utc", "effective_time_evidence_hash",
                "refresh_generation", "producing_task_id", "parser_id",
                "parser_version", "mapping_version",
            )
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

    def put_formal_snapshot(
        self,
        fetch: OfficialFetch,
        stored: FormalStoredSnapshot,
        verification: EvidenceVerification,
    ) -> OfficialSnapshotRef:
        raw_store = self._require_formal_snapshot_store()
        validated = raw_store.validate_stored_snapshot(
            fetch,
            stored,
            verification,
            expected_producing_task_id=None,
        )
        if type(validated) is not ValidatedFormalSnapshot:
            raise ValueError("formal snapshot validation returned an invalid projection")
        request_payload = _decode_canonical_formal_json(validated.request_json, "request")
        if frozenset(request_payload) != _FORMAL_REQUEST_IDENTITY_KEYS:
            raise ValueError("formal snapshot request identity keys mismatch")
        if validated.request_fingerprint != hashlib.sha256(
            validated.request_json.encode("utf-8")
        ).hexdigest():
            raise ValueError("formal snapshot request fingerprint mismatch")

        with self._transaction(immediate=True) as connection:
            existing = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE manifest_sha256 = ?",
                (validated.manifest_sha256,),
            ).fetchone()
            if existing is not None:
                try:
                    ref = self._formal_snapshot_row_to_ref(existing)
                    if not self._formal_ref_matches_projection(ref, validated):
                        raise ValueError("immutable formal snapshot fields differ")
                except ValueError as error:
                    raise ValueError("formal_snapshot_manifest_conflict") from error
                return ref

            lineage = connection.execute(
                """SELECT * FROM formal_source_snapshot
                WHERE request_fingerprint = ? AND refresh_generation = ?
                  AND producing_task_id IS NULL""",
                (validated.request_fingerprint, validated.refresh_generation),
            ).fetchone()
            if lineage is not None:
                self._formal_snapshot_row_to_ref(lineage)
                raise ValueError("formal_snapshot_lineage_conflict")

            snapshot_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO formal_source_snapshot
                (id,source,dataset,request_json,request_fingerprint,content_sha256,
                 manifest_sha256,content_path,manifest_path,original_url,published_at_utc,
                 published_precision,source_updated_at_utc,captured_at_utc,effective_at_utc,
                 effective_time_evidence_hash,parser_id,parser_version,mapping_version,
                 refresh_generation,producing_task_id,verification_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    validated.source,
                    validated.dataset,
                    validated.request_json,
                    validated.request_fingerprint,
                    validated.content_sha256,
                    validated.manifest_sha256,
                    validated.content_path,
                    validated.manifest_path,
                    validated.original_url,
                    validated.published_at_utc,
                    validated.published_precision,
                    validated.source_updated_at_utc,
                    validated.captured_at_utc,
                    validated.effective_at_utc,
                    validated.effective_time_evidence_hash,
                    validated.parser_id,
                    validated.parser_version,
                    validated.mapping_version,
                    validated.refresh_generation,
                    validated.producing_task_id,
                    validated.verification_json,
                    _utc_now(),
                ),
            )
            inserted = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE id = ?", (snapshot_id,)
            ).fetchone()
            if inserted is None:
                raise ValueError("formal snapshot insert was not visible")
            return self._formal_snapshot_row_to_ref(inserted)

    def get_formal_snapshot(self, snapshot_id: str) -> OfficialSnapshotRef | None:
        self._require_formal_snapshot_store()
        if type(snapshot_id) is not str or not snapshot_id.strip():
            raise ValueError("snapshot_id must be a nonempty string")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE id = ?", (snapshot_id,)
            ).fetchone()
            return self._formal_snapshot_row_to_ref(row) if row is not None else None

    def _formal_task_snapshot_receipt_from_connection(
        self, connection: sqlite3.Connection, task_id: str
    ) -> dict[str, object] | None:
        receipt = connection.execute(
            "SELECT * FROM formal_task_snapshot_receipt WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        producer_snapshot_ids = [
            str(row["id"])
            for row in connection.execute(
                """SELECT id FROM formal_source_snapshot
                WHERE producing_task_id = ? ORDER BY id""",
                (task_id,),
            )
        ]
        if receipt is None:
            if producer_snapshot_ids:
                raise ValueError("formal snapshot producer has no exact receipt")
            return None
        if producer_snapshot_ids != [receipt["snapshot_id"]]:
            raise ValueError("formal snapshot receipt producer set mismatch")
        task = connection.execute(
            "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
        ).fetchone()
        if task is None:
            raise ValueError("formal snapshot receipt task is missing")
        prerequisites = [
            str(row["prerequisite_task_id"])
            for row in connection.execute(
                """SELECT prerequisite_task_id
                FROM formal_collection_task_dependency
                WHERE task_id = ? ORDER BY prerequisite_task_id""",
                (task_id,),
            )
        ]
        task_public = self._formal_task_public(task, prerequisites)
        if task_public["kind"] not in _FORMAL_SOURCE_FETCH_KINDS:
            raise ValueError("formal snapshot receipt task is not a source task")
        snapshot = connection.execute(
            "SELECT * FROM formal_source_snapshot WHERE id = ?",
            (receipt["snapshot_id"],),
        ).fetchone()
        if snapshot is None:
            raise ValueError("formal snapshot receipt snapshot is missing")
        ref = self._formal_snapshot_row_to_ref(snapshot)
        if receipt["task_id"] != task_id or ref.producing_task_id != task_id:
            raise ValueError("formal snapshot receipt producer mismatch")
        manifest_sha256 = _require_formal_sha256(
            receipt["manifest_sha256"], "receipt manifest hash"
        )
        if manifest_sha256 != ref.manifest_sha256:
            raise ValueError("formal snapshot receipt manifest mismatch")
        refresh_generation = receipt["refresh_generation"]
        if (
            type(refresh_generation) is not str
            or not refresh_generation
            or refresh_generation != ref.refresh_generation
            or refresh_generation != task_public["refresh_generation"]
        ):
            raise ValueError("formal snapshot receipt refresh generation mismatch")
        return {
            "task_id": task_id,
            "snapshot_id": ref.snapshot_id,
            "manifest_sha256": manifest_sha256,
            "refresh_generation": refresh_generation,
            "recorded_at": _require_canonical_utc(
                receipt["recorded_at"], "receipt time"
            ),
        }

    def put_formal_snapshot_for_leased_task(
        self,
        fetch: OfficialFetch,
        stored: FormalStoredSnapshot,
        verification: EvidenceVerification,
        *,
        task_id: str,
        worker_id: str,
    ) -> OfficialSnapshotRef:
        raw_store = self._require_formal_snapshot_store()
        if type(task_id) is not str or not task_id.strip():
            raise ValueError("task_id must be a nonempty string")
        if type(worker_id) is not str or not worker_id.strip():
            raise ValueError("worker_id must be a nonempty string")
        validated = raw_store.validate_stored_snapshot(
            fetch,
            stored,
            verification,
            expected_producing_task_id=task_id,
        )
        if type(validated) is not ValidatedFormalSnapshot:
            raise ValueError("formal snapshot validation returned an invalid projection")
        request_payload = _decode_canonical_formal_json(validated.request_json, "request")
        if frozenset(request_payload) != _FORMAL_REQUEST_IDENTITY_KEYS:
            raise ValueError("formal snapshot request identity keys mismatch")
        if validated.request_fingerprint != hashlib.sha256(
            validated.request_json.encode("utf-8")
        ).hexdigest():
            raise ValueError("formal snapshot request fingerprint mismatch")
        if (
            validated.producing_task_id != task_id
            or validated.refresh_generation != fetch.refresh_generation
        ):
            raise ValueError("formal snapshot task producer or generation mismatch")

        with self._transaction(immediate=True) as connection:
            now = _utc_iso(_utc_now())
            task = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
            ).fetchone()
            if task is None:
                raise ValueError("formal snapshot task does not exist")
            prerequisites = [
                str(row["prerequisite_task_id"])
                for row in connection.execute(
                    """SELECT prerequisite_task_id
                    FROM formal_collection_task_dependency
                    WHERE task_id = ? ORDER BY prerequisite_task_id""",
                    (task_id,),
                )
            ]
            task_public = self._formal_task_public(task, prerequisites)
            lease_expires_at = _require_canonical_utc(
                task_public["lease_expires_at"], "task lease expiry"
            ) if task_public["lease_expires_at"] is not None else None
            if (
                task_public["kind"] not in _FORMAL_SOURCE_FETCH_KINDS
                or task_public["status"] != "leased"
                or task_public["lease_worker"] != worker_id
                or lease_expires_at is None
                or lease_expires_at <= now
            ):
                raise ValueError(
                    "formal snapshot task is not held by the current unexpired source-task lease owner"
                )
            task_generation = task_public["refresh_generation"]
            if (
                type(task_generation) is not str
                or not task_generation
                or task_generation != fetch.refresh_generation
                or task_generation != validated.refresh_generation
            ):
                raise ValueError("formal snapshot task refresh generation mismatch")

            existing_receipt = self._formal_task_snapshot_receipt_from_connection(
                connection, task_id
            )
            if existing_receipt is not None:
                existing = connection.execute(
                    "SELECT * FROM formal_source_snapshot WHERE id = ?",
                    (existing_receipt["snapshot_id"],),
                ).fetchone()
                if existing is None:
                    raise ValueError("formal_task_snapshot_receipt_conflict")
                ref = self._formal_snapshot_row_to_ref(existing)
                if not self._formal_ref_matches_projection(ref, validated):
                    raise ValueError("formal_task_snapshot_receipt_conflict")
                self._require_formal_snapshot_owner(connection, task_id, worker_id, validated.refresh_generation)
                return ref

            existing_manifest = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE manifest_sha256 = ?",
                (validated.manifest_sha256,),
            ).fetchone()
            if existing_manifest is not None:
                try:
                    self._formal_snapshot_row_to_ref(existing_manifest)
                except ValueError as error:
                    raise ValueError("formal_snapshot_manifest_conflict") from error
                raise ValueError("formal_task_snapshot_receipt_conflict")

            lineage = connection.execute(
                """SELECT * FROM formal_source_snapshot
                WHERE request_fingerprint = ? AND refresh_generation = ?
                  AND producing_task_id = ?""",
                (
                    validated.request_fingerprint,
                    validated.refresh_generation,
                    task_id,
                ),
            ).fetchone()
            if lineage is not None:
                self._formal_snapshot_row_to_ref(lineage)
                raise ValueError("formal_snapshot_lineage_conflict")

            now = _require_canonical_utc(_utc_now(), "snapshot ownership time")
            ownership = connection.execute(
                """SELECT 1 FROM formal_collection_task
                WHERE id = ? AND kind IN (?,?,?) AND status = 'leased'
                  AND lease_worker = ? AND lease_expires_at > ?
                  AND refresh_generation = ?""",
                (
                    task_id,
                    *_FORMAL_SOURCE_FETCH_KINDS,
                    worker_id,
                    now,
                    validated.refresh_generation,
                ),
            ).fetchone()
            if ownership is None:
                raise ValueError(
                    "formal snapshot task is not held by the current unexpired source-task lease owner"
                )

            snapshot_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO formal_source_snapshot
                (id,source,dataset,request_json,request_fingerprint,content_sha256,
                 manifest_sha256,content_path,manifest_path,original_url,published_at_utc,
                 published_precision,source_updated_at_utc,captured_at_utc,effective_at_utc,
                 effective_time_evidence_hash,parser_id,parser_version,mapping_version,
                 refresh_generation,producing_task_id,verification_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    validated.source,
                    validated.dataset,
                    validated.request_json,
                    validated.request_fingerprint,
                    validated.content_sha256,
                    validated.manifest_sha256,
                    validated.content_path,
                    validated.manifest_path,
                    validated.original_url,
                    validated.published_at_utc,
                    validated.published_precision,
                    validated.source_updated_at_utc,
                    validated.captured_at_utc,
                    validated.effective_at_utc,
                    validated.effective_time_evidence_hash,
                    validated.parser_id,
                    validated.parser_version,
                    validated.mapping_version,
                    validated.refresh_generation,
                    task_id,
                    validated.verification_json,
                    now,
                ),
            )
            try:
                connection.execute(
                    """INSERT INTO formal_task_snapshot_receipt
                    (task_id,snapshot_id,manifest_sha256,refresh_generation,recorded_at)
                    VALUES (?,?,?,?,?)""",
                    (
                        task_id,
                        snapshot_id,
                        validated.manifest_sha256,
                        validated.refresh_generation,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("formal_task_snapshot_receipt_conflict") from error

            receipt = self._formal_task_snapshot_receipt_from_connection(
                connection, task_id
            )
            if receipt is None or receipt["snapshot_id"] != snapshot_id:
                raise ValueError("formal_task_snapshot_receipt_conflict")
            inserted = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE id = ?", (snapshot_id,)
            ).fetchone()
            if inserted is None:
                raise ValueError("formal snapshot insert was not visible")
            ref = self._formal_snapshot_row_to_ref(inserted)
            if not self._formal_ref_matches_projection(ref, validated):
                raise ValueError("formal_task_snapshot_receipt_conflict")
            self._require_formal_snapshot_owner(connection, task_id, worker_id, validated.refresh_generation)
            return ref

    def _require_formal_snapshot_owner(self, connection, task_id, worker_id, generation):
        now = _require_canonical_utc(_utc_now(), "snapshot ownership time")
        row = connection.execute(
            """SELECT 1 FROM formal_collection_task WHERE id=? AND kind IN (?,?,?)
            AND status='leased' AND lease_worker=? AND lease_expires_at>?
            AND refresh_generation=?""",
            (task_id, *_FORMAL_SOURCE_FETCH_KINDS, worker_id, now, generation),
        ).fetchone()
        if row is None:
            raise ValueError("formal snapshot task lease expired or ownership changed")

    def get_formal_task_snapshot_receipt(
        self, task_id: str
    ) -> dict[str, object] | None:
        self._require_formal_snapshot_store()
        if type(task_id) is not str or not task_id.strip():
            raise ValueError("task_id must be a nonempty string")
        with self._transaction() as connection:
            return self._formal_task_snapshot_receipt_from_connection(
                connection, task_id
            )

    @staticmethod
    def _require_formal_frozen_universe_input(
        frozen: object,
    ) -> FormalFrozenUniverseInput:
        if type(frozen) is not FormalFrozenUniverseInput:
            raise ValueError(
                "frozen must have exact type FormalFrozenUniverseInput"
            )
        try:
            _validate_frozen_universe_input(frozen)
        except (AssertionError, AttributeError, TypeError, ValueError) as error:
            raise ValueError("formal frozen universe input is invalid") from error
        for field in (
            "registry_manifest_hash",
            "universe_hash",
            "source_audit_hash",
            "frozen_input_hash",
        ):
            _require_formal_sha256(getattr(frozen, field), f"universe {field}")
        _canonical_formal_universe_json(
            _formal_frozen_universe_payload(frozen), "formal frozen universe"
        )
        return frozen

    @staticmethod
    def _formal_universe_extraction_from_payload(
        payload: dict[str, object],
    ) -> FormalUniverseExtraction:
        if frozenset(payload) != _FORMAL_UNIVERSE_EXTRACTION_KEYS:
            raise ValueError("stored formal universe extraction keys mismatch")
        exchange = payload["exchange"]
        if type(exchange) is not str or exchange not in _FORMAL_UNIVERSE_EXCHANGES:
            raise ValueError("stored formal universe extraction exchange is invalid")
        member_payloads = payload["members"]
        if type(member_payloads) is not list or not member_payloads:
            raise ValueError("stored formal universe extraction members are invalid")
        members: list[FormalUniverseMember] = []
        for member_payload in member_payloads:
            if (
                type(member_payload) is not dict
                or frozenset(member_payload) != _FORMAL_UNIVERSE_MEMBER_KEYS
                or type(member_payload["raw_row"]) is not dict
            ):
                raise ValueError("stored formal universe member payload is invalid")
            members.append(FormalUniverseMember(
                security_id=member_payload["security_id"],
                exchange=member_payload["exchange"],
                security_type=member_payload["security_type"],
                listing_status=member_payload["listing_status"],
                raw_row=member_payload["raw_row"],
                raw_row_hash=_require_formal_sha256(
                    member_payload["raw_row_hash"], "universe member raw row hash"
                ),
            ))
        audit_payload = payload["audit"]
        if (
            type(audit_payload) is not dict
            or frozenset(audit_payload) != _FORMAL_UNIVERSE_AUDIT_KEYS
        ):
            raise ValueError("stored formal universe audit keys mismatch")
        for count_field in ("source_row_count", "accepted_ordinary_a_count"):
            count = audit_payload[count_field]
            if type(count) is not int or count < 0:
                raise ValueError(f"stored formal universe {count_field} is invalid")
        excluded_payload = audit_payload["excluded_by_security_type"]
        if type(excluded_payload) is not list:
            raise ValueError("stored formal universe exclusion audit is invalid")
        excluded: list[tuple[str, int]] = []
        for item in excluded_payload:
            if (
                type(item) is not list
                or len(item) != 2
                or type(item[0]) is not str
                or not item[0]
                or type(item[1]) is not int
                or item[1] <= 0
            ):
                raise ValueError("stored formal universe exclusion audit is invalid")
            excluded.append((item[0], item[1]))
        if excluded != sorted(excluded) or len({item[0] for item in excluded}) != len(excluded):
            raise ValueError("stored formal universe exclusion audit is not canonical")
        for text_field in ("parser_id", "parser_version"):
            if type(audit_payload[text_field]) is not str or not audit_payload[text_field]:
                raise ValueError(f"stored formal universe {text_field} is invalid")
        audit = FormalUniverseSourceAudit(
            exchange=audit_payload["exchange"],
            source_content_sha256=_require_formal_sha256(
                audit_payload["source_content_sha256"],
                "universe audit source content hash",
            ),
            parser_id=audit_payload["parser_id"],
            parser_version=audit_payload["parser_version"],
            source_row_count=audit_payload["source_row_count"],
            accepted_ordinary_a_count=audit_payload["accepted_ordinary_a_count"],
            excluded_by_security_type=tuple(excluded),
            parsed_rows_hash=_require_formal_sha256(
                audit_payload["parsed_rows_hash"], "universe parsed rows hash"
            ),
            accepted_members_hash=_require_formal_sha256(
                audit_payload["accepted_members_hash"],
                "universe accepted members hash",
            ),
            excluded_rows_hash=_require_formal_sha256(
                audit_payload["excluded_rows_hash"], "universe excluded rows hash"
            ),
            audit_hash=_require_formal_sha256(
                audit_payload["audit_hash"], "universe extraction audit hash"
            ),
        )
        return FormalUniverseExtraction(exchange, tuple(members), audit)

    def _require_formal_universe_source_lineage(
        self,
        connection: sqlite3.Connection,
        frozen: FormalFrozenUniverseInput,
        source: FormalUniverseSourceEvidence,
    ) -> OfficialSnapshotRef:
        snapshot_row = connection.execute(
            "SELECT * FROM formal_source_snapshot WHERE id = ?",
            (source.snapshot.snapshot_id,),
        ).fetchone()
        if snapshot_row is None:
            raise ValueError("formal universe source snapshot is missing")
        persisted_ref = self._formal_snapshot_row_to_ref(snapshot_row)
        if persisted_ref != source.snapshot:
            raise ValueError("formal universe source snapshot identity mismatch")
        task_id = persisted_ref.producing_task_id
        if type(task_id) is not str or not task_id:
            raise ValueError("formal universe bootstrap snapshot is not eligible")
        receipt = self._formal_task_snapshot_receipt_from_connection(
            connection, task_id
        )
        if receipt is None or (
            receipt["snapshot_id"] != persisted_ref.snapshot_id
            or receipt["manifest_sha256"] != persisted_ref.manifest_sha256
            or receipt["refresh_generation"] != persisted_ref.refresh_generation
        ):
            raise ValueError("formal universe source receipt mismatch")
        task_row = connection.execute(
            "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
        ).fetchone()
        if task_row is None:
            raise ValueError("formal universe source task is missing")
        prerequisites = [
            str(row["prerequisite_task_id"])
            for row in connection.execute(
                """SELECT prerequisite_task_id
                FROM formal_collection_task_dependency
                WHERE task_id = ? ORDER BY prerequisite_task_id""",
                (task_id,),
            )
        ]
        task = self._formal_task_public(task_row, prerequisites)
        if task["kind"] != "formal_universe_source" or task["status"] != "verified":
            raise ValueError("formal universe source task must be verified")
        self._require_formal_verified_task_state(task_row, task)
        if task["refresh_generation"] != persisted_ref.refresh_generation:
            raise ValueError("formal universe source task generation mismatch")
        payload = task["payload"]
        result = task["result"]
        if type(payload) is not dict or type(result) is not dict:
            raise ValueError("formal universe source task payload/result is missing")
        expected_request = json.loads(
            OfficialRequest(
                persisted_ref.source,
                persisted_ref.dataset,
                persisted_ref.security_id,
                persisted_ref.period_or_date,
                persisted_ref.exchange,
            ).canonical_json_bytes().decode("utf-8")
        )
        expected_payload = {
            "as_of_utc": frozen.as_of_utc,
            "exchange": source.exchange,
            "official_request": expected_request,
            "refresh_generation": persisted_ref.refresh_generation,
            "registry_manifest_hash": frozen.registry_manifest_hash,
            "source": persisted_ref.source,
        }
        if any(payload.get(key) != value for key, value in expected_payload.items()):
            raise ValueError("formal universe source task payload lineage mismatch")
        expected_result = {
            "exchange": source.exchange,
            "manifest_sha256": persisted_ref.manifest_sha256,
            "parsed_rows_hash": source.extraction.audit.parsed_rows_hash,
            "parser_id": persisted_ref.parser_id,
            "parser_version": persisted_ref.parser_version,
            "refresh_generation": persisted_ref.refresh_generation,
            "registry_manifest_hash": frozen.registry_manifest_hash,
            "snapshot_id": persisted_ref.snapshot_id,
            "source_content_sha256": persisted_ref.content_sha256,
        }
        if any(result.get(key) != value for key, value in expected_result.items()):
            raise ValueError("formal universe source task result lineage mismatch")
        return persisted_ref

    def _formal_universe_from_connection(
        self,
        connection: sqlite3.Connection,
        header: sqlite3.Row,
    ) -> tuple[FormalFrozenUniverseInput, list[dict[str, object]]]:
        snapshot_id = _require_canonical_uuid(header["id"], "universe snapshot ID")
        header_created_at = _require_canonical_utc(
            header["created_at"], "universe creation time"
        )
        for field in (
            "registry_manifest_hash",
            "universe_hash",
            "source_audit_hash",
            "frozen_input_hash",
        ):
            _require_formal_sha256(header[field], f"universe {field}")
        source_rows = connection.execute(
            """SELECT * FROM formal_universe_source
            WHERE universe_snapshot_id = ? ORDER BY exchange""",
            (snapshot_id,),
        ).fetchall()
        if (
            len(source_rows) != 3
            or {row["exchange"] for row in source_rows} != _FORMAL_UNIVERSE_EXCHANGES
        ):
            raise ValueError("stored formal universe requires exactly three SH/SZ/BJ sources")
        sources: list[FormalUniverseSourceEvidence] = []
        public_sources: list[dict[str, object]] = []
        for row in source_rows:
            if row["universe_snapshot_id"] != snapshot_id:
                raise ValueError("stored formal universe source parent mismatch")
            extraction_payload = _decode_canonical_formal_json(
                row["extraction_json"], "universe extraction"
            )
            extraction = self._formal_universe_extraction_from_payload(
                extraction_payload
            )
            snapshot_row = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE id = ?",
                (row["source_snapshot_id"],),
            ).fetchone()
            if snapshot_row is None:
                raise ValueError("stored formal universe source snapshot is missing")
            ref = self._formal_snapshot_row_to_ref(snapshot_row)
            if (
                row["exchange"] != extraction.exchange
                or row["exchange"] != ref.exchange
                or row["manifest_sha256"] != ref.manifest_sha256
                or row["source_content_sha256"] != ref.content_sha256
                or row["parser_id"] != ref.parser_id
                or row["parser_version"] != ref.parser_version
                or row["extraction_audit_hash"] != extraction.audit.audit_hash
            ):
                raise ValueError("stored formal universe source fields mismatch")
            _require_formal_sha256(
                row["manifest_sha256"], "universe source manifest hash"
            )
            _require_formal_sha256(
                row["source_content_sha256"], "universe source content hash"
            )
            _require_formal_sha256(
                row["extraction_audit_hash"], "universe source extraction hash"
            )
            _require_canonical_utc(row["created_at"], "universe source creation time")
            source = FormalUniverseSourceEvidence(row["exchange"], ref, extraction)
            sources.append(source)
            public = dict(row)
            public.pop("extraction_json")
            public["extraction"] = extraction_payload
            public_sources.append(public)

        member_rows = connection.execute(
            """SELECT * FROM formal_universe_member
            WHERE snapshot_id = ? ORDER BY security_id""",
            (snapshot_id,),
        ).fetchall()
        if not member_rows:
            raise ValueError("stored formal universe has no members")
        members: list[FormalUniverseMember] = []
        for row in member_rows:
            raw_payload = _decode_canonical_formal_json(
                row["raw_json"], "universe member raw row"
            )
            member = FormalUniverseMember(
                security_id=row["security_id"],
                exchange=row["exchange"],
                security_type=row["security_type"],
                listing_status=row["listing_status"],
                raw_row=raw_payload,
                raw_row_hash=hashlib.sha256(
                    row["raw_json"].encode("utf-8")
                ).hexdigest(),
            )
            if (
                row["snapshot_id"] != snapshot_id
                or row["code6"] != member.security_id[2:]
            ):
                raise ValueError("stored formal universe member fields mismatch")
            members.append(member)

        status_rows = connection.execute(
            """SELECT * FROM formal_universe_status
            WHERE snapshot_id = ? ORDER BY security_id""",
            (snapshot_id,),
        ).fetchall()
        if (
            len(status_rows) != len(members)
            or [row["security_id"] for row in status_rows]
            != [member.security_id for member in members]
        ):
            raise ValueError("stored formal universe must have exactly one status per member")
        status_updated_at_values: set[str] = set()
        for row in status_rows:
            reasons_list = _decode_canonical_formal_array(row["reasons_json"], "reasons")
            veto_flags_list = _decode_canonical_formal_array(
                row["veto_flags_json"], "veto flags"
            )
            if row["snapshot_id"] != snapshot_id:
                raise ValueError("stored formal universe status fields are invalid")
            _require_formal_universe_status_values(
                security_id=row["security_id"],
                status=row["status"],
                reasons=tuple(reasons_list),
                veto_flags=tuple(veto_flags_list),
                evidence_hash=row["evidence_hash"],
                frozen_input_hash=header["frozen_input_hash"],
            )
            status_updated_at_values.add(
                _require_canonical_utc(
                    row["updated_at"], "universe status update time"
                )
            )
        if len(status_updated_at_values) != 1:
            raise ValueError(
                "stored formal universe statuses must share one update time"
            )
        status_updated_at = next(iter(status_updated_at_values))
        if datetime.fromisoformat(status_updated_at) < datetime.fromisoformat(
            header_created_at
        ):
            raise ValueError(
                "stored formal universe status update time predates snapshot"
            )

        frozen = _create_frozen_universe_input(
            as_of_utc=header["as_of_utc"],
            registry_manifest_hash=header["registry_manifest_hash"],
            members=tuple(members),
            sources=tuple(sources),
            universe_hash=header["universe_hash"],
            source_audit_hash=header["source_audit_hash"],
            frozen_input_hash=header["frozen_input_hash"],
        )
        for source in frozen.sources:
            self._require_formal_universe_source_lineage(
                connection, frozen, source
            )
        return frozen, public_sources

    def put_formal_universe_snapshot(
        self, frozen: FormalFrozenUniverseInput
    ) -> str:
        self._require_formal_snapshot_store()
        frozen = self._require_formal_frozen_universe_input(frozen)
        expected_graph_json = _canonical_formal_universe_json(
            _formal_frozen_universe_payload(frozen), "formal frozen universe"
        )
        with self._transaction(immediate=True) as connection:
            frozen = self._require_formal_frozen_universe_input(frozen)
            for source in frozen.sources:
                self._require_formal_universe_source_lineage(
                    connection, frozen, source
                )
            existing = connection.execute(
                """SELECT * FROM formal_universe_snapshot
                WHERE frozen_input_hash = ?""",
                (frozen.frozen_input_hash,),
            ).fetchone()
            if existing is not None:
                try:
                    persisted, _ = self._formal_universe_from_connection(
                        connection, existing
                    )
                    persisted_json = _canonical_formal_universe_json(
                        _formal_frozen_universe_payload(persisted),
                        "stored formal frozen universe",
                    )
                    if persisted_json != expected_graph_json:
                        raise ValueError("immutable formal universe graph differs")
                except ValueError as error:
                    raise ValueError("frozen_input_hash_conflict") from error
                return str(existing["id"])

            snapshot_id = str(uuid.uuid4())
            now = _utc_iso(_utc_now())
            connection.execute(
                """INSERT INTO formal_universe_snapshot
                (id,as_of_utc,registry_manifest_hash,universe_hash,source_audit_hash,
                 frozen_input_hash,created_at) VALUES (?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    frozen.as_of_utc,
                    frozen.registry_manifest_hash,
                    frozen.universe_hash,
                    frozen.source_audit_hash,
                    frozen.frozen_input_hash,
                    now,
                ),
            )
            for source in frozen.sources:
                extraction_json = _canonical_formal_universe_json(
                    _formal_universe_extraction_payload(source.extraction),
                    "formal universe extraction",
                )
                connection.execute(
                    """INSERT INTO formal_universe_source
                    (universe_snapshot_id,exchange,source_snapshot_id,manifest_sha256,
                     source_content_sha256,parser_id,parser_version,
                     extraction_audit_hash,extraction_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        snapshot_id,
                        source.exchange,
                        source.snapshot.snapshot_id,
                        source.snapshot.manifest_sha256,
                        source.snapshot.content_sha256,
                        source.snapshot.parser_id,
                        source.snapshot.parser_version,
                        source.extraction.audit.audit_hash,
                        extraction_json,
                        now,
                    ),
                )
            for member in frozen.members:
                raw_json = _canonical_formal_universe_json(
                    member.raw_row, "formal universe member raw row"
                )
                connection.execute(
                    """INSERT INTO formal_universe_member
                    (snapshot_id,security_id,exchange,code6,security_type,
                     listing_status,raw_json) VALUES (?,?,?,?,?,?,?)""",
                    (
                        snapshot_id,
                        member.security_id,
                        member.exchange,
                        member.security_id[2:],
                        member.security_type,
                        member.listing_status,
                        raw_json,
                    ),
                )
                status = "pending_evidence"
                reasons = ["formal_collection_pending"]
                veto_flags: list[str] = []
                evidence_hash = _formal_universe_initial_status_evidence_hash(
                    frozen.frozen_input_hash, member.security_id
                )
                connection.execute(
                    """INSERT INTO formal_universe_status
                    (snapshot_id,security_id,status,reasons_json,veto_flags_json,
                     evidence_hash,updated_at) VALUES (?,?,?,?,?,?,?)""",
                    (
                        snapshot_id,
                        member.security_id,
                        status,
                        _json(reasons),
                        _json(veto_flags),
                        evidence_hash,
                        now,
                    ),
                )
            inserted = connection.execute(
                "SELECT * FROM formal_universe_snapshot WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
            if inserted is None:
                raise ValueError("formal universe insert was not visible")
            persisted, _ = self._formal_universe_from_connection(
                connection, inserted
            )
            if _canonical_formal_universe_json(
                _formal_frozen_universe_payload(persisted),
                "stored formal frozen universe",
            ) != expected_graph_json:
                raise ValueError("formal universe inserted graph mismatch")
            return snapshot_id

    def get_formal_universe_snapshot_by_input_hash(
        self, frozen_input_hash: str
    ) -> dict[str, object] | None:
        self._require_formal_snapshot_store()
        _require_formal_sha256(frozen_input_hash, "universe frozen input hash")
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT * FROM formal_universe_snapshot
                WHERE frozen_input_hash = ?""",
                (frozen_input_hash,),
            ).fetchone()
            if row is None:
                return None
            self._formal_universe_from_connection(connection, row)
            return dict(row)

    def list_formal_universe_sources(
        self, universe_snapshot_id: str
    ) -> list[dict[str, object]]:
        self._require_formal_snapshot_store()
        if type(universe_snapshot_id) is not str or not universe_snapshot_id.strip():
            raise ValueError("universe_snapshot_id must be a nonempty string")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM formal_universe_snapshot WHERE id = ?",
                (universe_snapshot_id,),
            ).fetchone()
            if row is None:
                return []
            _, sources = self._formal_universe_from_connection(connection, row)
            return sources

    def replace_formal_universe_statuses(
        self,
        universe_snapshot_id: str,
        decisions: Sequence[FormalUniverseDecision],
    ) -> None:
        self._require_formal_snapshot_store()
        snapshot_id = _require_canonical_uuid(
            universe_snapshot_id, "universe snapshot ID"
        )
        if isinstance(decisions, (str, bytes)):
            raise ValueError("formal universe decisions must be a sequence")
        try:
            materialized = tuple(decisions)
        except TypeError as error:
            raise ValueError("formal universe decisions must be a sequence") from error

        with self._transaction(immediate=True) as connection:
            header = connection.execute(
                "SELECT * FROM formal_universe_snapshot WHERE id = ?", (snapshot_id,)
            ).fetchone()
            if header is None:
                raise ValueError("formal universe snapshot does not exist")
            frozen, _ = self._formal_universe_from_connection(connection, header)
            expected_ids = tuple(member.security_id for member in frozen.members)
            validated: dict[str, tuple[str, tuple[str, ...], tuple[str, ...], str]] = {}
            for decision in materialized:
                if type(decision) is not FormalUniverseDecision:
                    raise ValueError(
                        "formal universe decisions must have exact type FormalUniverseDecision"
                    )
                security_id, status, reasons, veto_flags, evidence_hash = (
                    _require_formal_universe_status_values(
                        security_id=decision.security_id,
                        status=decision.status,
                        reasons=decision.reasons,
                        veto_flags=decision.veto_flags,
                        evidence_hash=decision.evidence_hash,
                        frozen_input_hash=frozen.frozen_input_hash,
                    )
                )
                if security_id in validated:
                    raise ValueError("duplicate formal universe decision security ID")
                validated[security_id] = (status, reasons, veto_flags, evidence_hash)
            if tuple(sorted(validated)) != expected_ids:
                raise ValueError(
                    "formal universe decisions must exactly cover existing members"
                )

            updated_at = _utc_iso(_utc_now())
            for security_id in expected_ids:
                status, reasons, veto_flags, evidence_hash = validated[security_id]
                cursor = connection.execute(
                    """UPDATE formal_universe_status
                    SET status=?,reasons_json=?,veto_flags_json=?,evidence_hash=?,updated_at=?
                    WHERE snapshot_id=? AND security_id=?""",
                    (
                        status,
                        _json(list(reasons)),
                        _json(list(veto_flags)),
                        evidence_hash,
                        updated_at,
                        snapshot_id,
                        security_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError("formal universe status replacement lost coverage")
            refreshed = connection.execute(
                "SELECT * FROM formal_universe_snapshot WHERE id = ?", (snapshot_id,)
            ).fetchone()
            if refreshed is None:
                raise ValueError("formal universe snapshot disappeared")
            self._formal_universe_from_connection(connection, refreshed)

    def list_formal_universe_statuses(
        self, universe_snapshot_id: str
    ) -> list[dict[str, object]]:
        self._require_formal_snapshot_store()
        snapshot_id = _require_canonical_uuid(
            universe_snapshot_id, "universe snapshot ID"
        )
        with self._transaction() as connection:
            header = connection.execute(
                "SELECT * FROM formal_universe_snapshot WHERE id = ?", (snapshot_id,)
            ).fetchone()
            if header is None:
                return []
            self._formal_universe_from_connection(connection, header)
            result: list[dict[str, object]] = []
            for row in connection.execute(
                """SELECT * FROM formal_universe_status
                WHERE snapshot_id=? ORDER BY security_id""",
                (snapshot_id,),
            ):
                public = dict(row)
                public.pop("reasons_json")
                public.pop("veto_flags_json")
                public["reasons"] = tuple(
                    _decode_canonical_formal_array(row["reasons_json"], "reasons")
                )
                public["veto_flags"] = tuple(
                    _decode_canonical_formal_array(row["veto_flags_json"], "veto flags")
                )
                result.append(public)
            return result

    def _require_formal_universe_finalizer_proof(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        task: Mapping[str, object],
        result: object,
    ) -> dict[str, object]:
        _require_canonical_uuid(row["id"], "finalizer task ID")
        if task["kind"] != "formal_universe_finalize":
            raise ValueError("formal universe proof requires a finalizer task")
        payload = task["payload"]
        if type(payload) is not dict or frozenset(payload) != _FORMAL_UNIVERSE_FINALIZER_PAYLOAD_KEYS:
            raise ValueError("formal universe finalizer payload keys mismatch")
        if type(result) is not dict or frozenset(result) != _FORMAL_UNIVERSE_FINALIZER_RESULT_KEYS:
            raise ValueError("formal universe finalizer result keys mismatch")
        generation = task["refresh_generation"]
        if type(generation) is not str or not generation or payload["refresh_generation"] != generation:
            raise ValueError("formal universe finalizer generation mismatch")
        snapshot_id = _require_canonical_uuid(
            result["universe_snapshot_id"], "universe snapshot ID"
        )
        header_row = connection.execute(
            "SELECT * FROM formal_universe_snapshot WHERE id = ?", (snapshot_id,)
        ).fetchone()
        if header_row is None:
            raise ValueError("formal universe finalizer target is missing")
        frozen, _ = self._formal_universe_from_connection(connection, header_row)
        header = dict(header_row)

        source_by_exchange = {source.exchange: source for source in frozen.sources}
        expected_source_ids: list[str] = []
        for exchange in ("BJ", "SH", "SZ"):
            source = source_by_exchange.get(exchange)
            if source is None:
                raise ValueError("formal universe finalizer source graph is incomplete")
            expected_source_ids.append(
                _require_canonical_uuid(
                    source.snapshot.producing_task_id,
                    f"{exchange} universe source task ID",
                )
            )
        payload_source_ids = payload["source_task_ids"]
        if type(payload_source_ids) is not list:
            raise ValueError("formal universe finalizer source task IDs must be a list")
        canonical_payload_source_ids = [
            _require_canonical_uuid(value, "finalizer source task ID")
            for value in payload_source_ids
        ]
        if canonical_payload_source_ids != expected_source_ids:
            raise ValueError("formal universe finalizer source task order or identity mismatch")
        prerequisite_ids = task["prerequisite_task_ids"]
        if (
            type(prerequisite_ids) is not list
            or len(prerequisite_ids) != 3
            or sorted(prerequisite_ids) != sorted(expected_source_ids)
        ):
            raise ValueError("formal universe finalizer prerequisite set mismatch")
        if self._formal_task_snapshot_receipt_from_connection(connection, row["id"]) is not None:
            raise ValueError("formal universe finalizer cannot own a source receipt")

        if (
            payload["as_of_utc"] != frozen.as_of_utc
            or payload["registry_manifest_hash"] != frozen.registry_manifest_hash
        ):
            raise ValueError("formal universe finalizer payload header mismatch")
        expected_result = {
            "universe_snapshot_id": snapshot_id,
            "frozen_input_hash": frozen.frozen_input_hash,
            "universe_hash": frozen.universe_hash,
            "registry_manifest_hash": frozen.registry_manifest_hash,
        }
        for field in ("frozen_input_hash", "universe_hash", "registry_manifest_hash"):
            _require_formal_sha256(result[field], f"finalizer result {field}")
        if result != expected_result:
            raise ValueError("formal universe finalizer result does not match target header")
        return header

    def get_formal_universe_snapshot_from_task(
        self, finalizer_task_id: str
    ) -> dict[str, object] | None:
        self._require_formal_snapshot_store()
        task_id = _require_canonical_uuid(finalizer_task_id, "finalizer task ID")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            prerequisites = [
                str(item["prerequisite_task_id"])
                for item in connection.execute(
                    """SELECT prerequisite_task_id
                    FROM formal_collection_task_dependency
                    WHERE task_id=? ORDER BY prerequisite_task_id""",
                    (task_id,),
                )
            ]
            task = self._formal_task_public(row, prerequisites)
            if task["kind"] != "formal_universe_finalize":
                raise ValueError("formal universe task lookup requires a finalizer")
            self._require_formal_verified_task_state(row, task)
            return self._require_formal_universe_finalizer_proof(
                connection, row, task, task["result"]
            )

    def enqueue_formal_task(
        self,
        kind: str,
        idempotency_key: str,
        refresh_generation: str,
        payload: Mapping[str, object],
        prerequisite_task_ids: Iterable[str] = (),
    ) -> str:
        for value, field in (
            (kind, "kind"),
            (idempotency_key, "idempotency_key"),
            (refresh_generation, "refresh_generation"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a nonempty string")
        payload_json = _canonical_mapping_json(payload, "payload")
        payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if isinstance(prerequisite_task_ids, (str, bytes)):
            raise ValueError("prerequisite task IDs must be an iterable of strings")
        try:
            requested_prerequisites = tuple(prerequisite_task_ids)
        except TypeError as error:
            raise ValueError("prerequisite task IDs must be iterable") from error
        for prerequisite_id in requested_prerequisites:
            if not isinstance(prerequisite_id, str) or not prerequisite_id.strip():
                raise ValueError("prerequisite task IDs must be nonempty strings")
        if len(set(requested_prerequisites)) != len(requested_prerequisites):
            raise ValueError("duplicate prerequisite task ID")
        prerequisites = tuple(sorted(requested_prerequisites))
        task_id = str(uuid.uuid4())
        now = _utc_now()

        with self._transaction(immediate=True) as connection:
            existing = connection.execute(
                """SELECT id,kind,refresh_generation,payload_json,payload_sha256
                FROM formal_collection_task WHERE idempotency_key = ?""",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                existing_prerequisites = tuple(
                    row["prerequisite_task_id"]
                    for row in connection.execute(
                        """SELECT prerequisite_task_id
                        FROM formal_collection_task_dependency
                        WHERE task_id = ? ORDER BY prerequisite_task_id""",
                        (existing["id"],),
                    )
                )
                if (
                    existing["kind"] != kind
                    or existing["refresh_generation"] != refresh_generation
                    or existing["payload_json"] != payload_json
                    or existing["payload_sha256"] != payload_sha256
                    or existing_prerequisites != prerequisites
                ):
                    raise ValueError("idempotency_payload_conflict")
                return str(existing["id"])

            if task_id in prerequisites:
                raise ValueError("formal task cannot depend on itself")
            if prerequisites:
                marks = ",".join("?" for _ in prerequisites)
                found = {
                    str(row["id"])
                    for row in connection.execute(
                        f"SELECT id FROM formal_collection_task WHERE id IN ({marks})",
                        prerequisites,
                    )
                }
                missing = sorted(set(prerequisites) - found)
                if missing:
                    raise ValueError(f"missing prerequisite task IDs: {missing}")
                for prerequisite_id in prerequisites:
                    cycle = connection.execute(
                        """WITH RECURSIVE prerequisite_chain(id) AS (
                            SELECT ?
                            UNION
                            SELECT dependency.prerequisite_task_id
                            FROM formal_collection_task_dependency AS dependency
                            JOIN prerequisite_chain
                              ON dependency.task_id = prerequisite_chain.id
                        )
                        SELECT 1 FROM prerequisite_chain WHERE id = ? LIMIT 1""",
                        (prerequisite_id, task_id),
                    ).fetchone()
                    if cycle is not None:
                        raise ValueError("formal task dependency cycle")

            connection.execute(
                """INSERT INTO formal_collection_task
                (id,kind,idempotency_key,refresh_generation,payload_json,payload_sha256,
                 status,lease_worker,lease_expires_at,next_retry_at,result_json,error_json,
                 created_at,updated_at)
                VALUES (?,?,?,?,?,?,'pending',NULL,NULL,NULL,NULL,NULL,?,?)""",
                (
                    task_id,
                    kind,
                    idempotency_key,
                    refresh_generation,
                    payload_json,
                    payload_sha256,
                    now,
                    now,
                ),
            )
            for prerequisite_id in prerequisites:
                connection.execute(
                    """INSERT INTO formal_collection_task_dependency
                    (task_id,prerequisite_task_id,created_at) VALUES (?,?,?)""",
                    (task_id, prerequisite_id, now),
                )
        return task_id

    def get_formal_task(self, task_id: str) -> dict[str, object] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            prerequisites = [
                str(item["prerequisite_task_id"])
                for item in connection.execute(
                    """SELECT prerequisite_task_id
                    FROM formal_collection_task_dependency
                    WHERE task_id = ? ORDER BY prerequisite_task_id""",
                    (task_id,),
                )
            ]
            return self._formal_task_public(row, prerequisites)

    def lease_next_formal_task(
        self,
        kinds: Iterable[str],
        worker_id: str,
        lease_seconds: int,
        now_utc: str | None = None,
    ) -> dict[str, object] | None:
        if isinstance(kinds, (str, bytes)):
            raise ValueError("kinds must be an iterable of nonempty strings")
        try:
            requested_kinds = tuple(kinds)
        except TypeError as error:
            raise ValueError("kinds must be iterable") from error
        if not requested_kinds:
            return None
        if any(not isinstance(kind, str) or not kind.strip() for kind in requested_kinds):
            raise ValueError("kinds must contain only nonempty strings")
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a nonempty string")
        if (
            not isinstance(lease_seconds, int)
            or isinstance(lease_seconds, bool)
            or lease_seconds <= 0
        ):
            raise ValueError("lease_seconds must be a positive integer")
        if now_utc is not None and not isinstance(now_utc, str):
            raise ValueError("now_utc must be a timezone-aware timestamp")
        explicit_now = _utc_iso(now_utc) if now_utc is not None else None
        marks = ",".join("?" for _ in requested_kinds)

        with self._transaction(immediate=True) as connection:
            now = explicit_now if explicit_now is not None else _utc_iso(_utc_now())
            expiry = (
                datetime.fromisoformat(now) + timedelta(seconds=lease_seconds)
            ).astimezone(timezone.utc).isoformat()
            row = connection.execute(
                f"""SELECT task.*
                FROM formal_collection_task AS task
                WHERE task.kind IN ({marks})
                  AND (
                    task.status = 'pending'
                    OR (
                        task.status = 'retryable_failed'
                        AND task.next_retry_at IS NOT NULL
                        AND task.next_retry_at <= ?
                    )
                    OR (
                        task.status = 'leased'
                        AND task.lease_expires_at IS NOT NULL
                        AND task.lease_expires_at <= ?
                    )
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM formal_collection_task_dependency AS dependency
                    LEFT JOIN formal_collection_task AS prerequisite
                      ON prerequisite.id = dependency.prerequisite_task_id
                    WHERE dependency.task_id = task.id
                      AND (prerequisite.id IS NULL OR prerequisite.status <> 'verified')
                  )
                ORDER BY CASE
                    WHEN task.status = 'pending' THEN task.created_at
                    WHEN task.status = 'retryable_failed' THEN task.next_retry_at
                    ELSE task.lease_expires_at
                END, task.created_at, task.id
                LIMIT 1""",
                (*requested_kinds, now, now),
            ).fetchone()
            if row is None:
                return None
            task_id = str(row["id"])
            prerequisites = [
                str(item["prerequisite_task_id"])
                for item in connection.execute(
                    """SELECT prerequisite_task_id
                    FROM formal_collection_task_dependency
                    WHERE task_id = ? ORDER BY prerequisite_task_id""",
                    (task_id,),
                )
            ]
            self._formal_task_public(row, prerequisites)
            cursor = connection.execute(
                f"""UPDATE formal_collection_task
                SET status = 'leased', lease_worker = ?, lease_expires_at = ?,
                    next_retry_at = NULL, updated_at = ?
                WHERE id = ? AND kind IN ({marks})
                  AND (
                    status = 'pending'
                    OR (
                        status = 'retryable_failed'
                        AND next_retry_at IS NOT NULL
                        AND next_retry_at <= ?
                    )
                    OR (
                        status = 'leased'
                        AND lease_expires_at IS NOT NULL
                        AND lease_expires_at <= ?
                    )
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM formal_collection_task_dependency AS dependency
                    LEFT JOIN formal_collection_task AS prerequisite
                      ON prerequisite.id = dependency.prerequisite_task_id
                    WHERE dependency.task_id = formal_collection_task.id
                      AND (prerequisite.id IS NULL OR prerequisite.status <> 'verified')
                  )""",
                (
                    worker_id,
                    expiry,
                    now,
                    task_id,
                    *requested_kinds,
                    now,
                    now,
                ),
            )
            if cursor.rowcount != 1:
                return None
            leased = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
            ).fetchone()
            return self._formal_task_public(leased, prerequisites)

    def renew_formal_task_lease(
        self,
        task_id: str,
        worker_id: str,
        lease_seconds: int,
        now_utc: str | None = None,
    ) -> str:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a nonempty string")
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a nonempty string")
        if (
            not isinstance(lease_seconds, int)
            or isinstance(lease_seconds, bool)
            or lease_seconds <= 0
        ):
            raise ValueError("lease_seconds must be a positive integer")
        if now_utc is not None and not isinstance(now_utc, str):
            raise ValueError("now_utc must be a timezone-aware timestamp")
        explicit_now = _utc_iso(now_utc) if now_utc is not None else None

        with self._transaction(immediate=True) as connection:
            now = explicit_now if explicit_now is not None else _utc_iso(_utc_now())
            expiry = (
                datetime.fromisoformat(now) + timedelta(seconds=lease_seconds)
            ).astimezone(timezone.utc).isoformat()
            cursor = connection.execute(
                """UPDATE formal_collection_task
                SET lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_worker = ?
                  AND lease_expires_at > ?""",
                (expiry, now, task_id, worker_id, now),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "formal task is not held by the current unexpired lease owner"
                )
        return expiry

    def complete_formal_task(
        self,
        task_id: str,
        worker_id: str,
        result: Mapping[str, object],
    ) -> None:
        if type(task_id) is not str or not task_id.strip():
            raise ValueError("task_id must be a nonempty string")
        if type(worker_id) is not str or not worker_id.strip():
            raise ValueError("worker_id must be a nonempty string")
        result_json = _canonical_mapping_json(result, "result")

        with self._transaction(immediate=True) as connection:
            now = _utc_iso(_utc_now())
            row = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise ValueError(
                    "formal task is not held by the current unexpired lease owner"
                )
            prerequisites = [
                str(item["prerequisite_task_id"])
                for item in connection.execute(
                    """SELECT prerequisite_task_id
                    FROM formal_collection_task_dependency
                    WHERE task_id = ? ORDER BY prerequisite_task_id""",
                    (task_id,),
                )
            ]
            task = self._formal_task_public(row, prerequisites)
            if (
                task["status"] != "leased"
                or task["lease_worker"] != worker_id
                or task["lease_expires_at"] is None
                or _require_canonical_utc(
                    task["lease_expires_at"], "task lease expiry"
                ) <= now
            ):
                raise ValueError(
                    "formal task is not held by the current unexpired lease owner"
                )
            if task["kind"] == "formal_universe_finalize":
                self._require_formal_universe_finalizer_proof(
                    connection,
                    row,
                    task,
                    _decode_canonical_mapping_json(result_json, "result"),
                )

            source_task = task["kind"] in _FORMAL_SOURCE_FETCH_KINDS
            if source_task:
                receipt = self._formal_task_snapshot_receipt_from_connection(
                    connection, task_id
                )
                if receipt is None:
                    raise ValueError(
                        "formal source task completion requires an exact receipt"
                    )

            now = _utc_iso(_utc_now())
            source_receipt_predicate = ""
            if source_task:
                source_receipt_predicate = """
                  AND (
                    SELECT COUNT(*)
                    FROM formal_task_snapshot_receipt AS receipt
                    JOIN formal_source_snapshot AS snapshot
                      ON snapshot.id = receipt.snapshot_id
                    WHERE receipt.task_id = formal_collection_task.id
                      AND snapshot.producing_task_id = formal_collection_task.id
                      AND receipt.manifest_sha256 = snapshot.manifest_sha256
                      AND receipt.refresh_generation = snapshot.refresh_generation
                      AND receipt.refresh_generation = formal_collection_task.refresh_generation
                  ) = 1
                  AND (
                    SELECT COUNT(*) FROM formal_source_snapshot AS produced
                    WHERE produced.producing_task_id = formal_collection_task.id
                  ) = 1"""
            cursor = connection.execute(
                f"""UPDATE formal_collection_task
                SET status = 'verified', result_json = ?, error_json = NULL,
                    next_retry_at = NULL, lease_worker = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_worker = ?
                  AND lease_expires_at > ? AND kind = ?
                  AND refresh_generation = ? AND payload_json = ?
                  AND payload_sha256 = ?{source_receipt_predicate}""",
                (
                    result_json,
                    now,
                    task_id,
                    worker_id,
                    now,
                    task["kind"],
                    task["refresh_generation"],
                    row["payload_json"],
                    row["payload_sha256"],
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "formal task is not held by the current unexpired lease owner"
                )

    def supersede_formal_tasks(
        self,
        scope: Mapping[str, object],
        before_generation: str,
    ) -> int:
        if type(before_generation) is not str or not before_generation.strip():
            raise ValueError("before_generation must be a nonempty string")
        scope_json = _canonical_mapping_json(scope, "scope")
        scope_values = _decode_canonical_mapping_json(scope_json, "scope")
        if not scope_values:
            raise ValueError("scope must be a nonempty mapping")

        changed = 0
        with self._transaction(immediate=True) as connection:
            now = _utc_iso(_utc_now())
            candidates = connection.execute(
                """SELECT * FROM formal_collection_task
                WHERE status IN ('pending','leased','retryable_failed')
                  AND refresh_generation <> ?
                ORDER BY id""",
                (before_generation,),
            ).fetchall()
            for row in candidates:
                task_id = str(row["id"])
                prerequisites = [
                    str(item["prerequisite_task_id"])
                    for item in connection.execute(
                        """SELECT prerequisite_task_id
                        FROM formal_collection_task_dependency
                        WHERE task_id = ? ORDER BY prerequisite_task_id""",
                        (task_id,),
                    )
                ]
                task = self._formal_task_public(row, prerequisites)
                payload = task["payload"]
                if any(
                    key not in payload or _json(payload[key]) != _json(value)
                    for key, value in scope_values.items()
                ):
                    continue
                cursor = connection.execute(
                    """UPDATE formal_collection_task
                    SET status = 'superseded', lease_worker = NULL,
                        lease_expires_at = NULL, next_retry_at = NULL, updated_at = ?
                    WHERE id = ? AND status = ? AND refresh_generation = ?
                      AND refresh_generation <> ? AND payload_json = ?
                      AND payload_sha256 = ?""",
                    (
                        now,
                        task_id,
                        row["status"],
                        row["refresh_generation"],
                        before_generation,
                        row["payload_json"],
                        row["payload_sha256"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError("formal task changed during supersession")
                changed += 1
        return changed

    def fail_formal_task(
        self,
        task_id: str,
        worker_id: str,
        error: Mapping[str, object],
        status: str,
        next_retry_at: str | None,
    ) -> None:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a nonempty string")
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a nonempty string")
        if (
            not isinstance(status, str)
            or status not in {"retryable_failed", "terminal_failed"}
        ):
            raise ValueError("status must be retryable_failed or terminal_failed")
        error_json = _canonical_mapping_json(error, "error")
        if status == "retryable_failed":
            if not isinstance(next_retry_at, str):
                raise ValueError("retryable failure requires next_retry_at")
            retry_at = _utc_iso(next_retry_at)
        else:
            if next_retry_at is not None:
                raise ValueError("terminal failure requires next_retry_at to be None")
            retry_at = None

        with self._transaction(immediate=True) as connection:
            now = _utc_iso(_utc_now())
            cursor = connection.execute(
                """UPDATE formal_collection_task
                SET status = ?, error_json = ?, next_retry_at = ?,
                    lease_worker = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_worker = ?
                  AND lease_expires_at > ?""",
                (status, error_json, retry_at, now, task_id, worker_id, now),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "formal task is not held by the current unexpired lease owner"
                )

    def resolve_formal_task_dependencies(self) -> int:
        changed = 0
        with self._transaction(immediate=True) as connection:
            now = _utc_iso(_utc_now())
            while True:
                candidates = connection.execute(
                    """SELECT task.id
                    FROM formal_collection_task AS task
                    WHERE (
                        task.status IN ('pending','retryable_failed')
                        OR (
                            task.status = 'leased'
                            AND task.lease_expires_at IS NOT NULL
                            AND task.lease_expires_at <= ?
                        )
                      )
                      AND EXISTS (
                        SELECT 1
                        FROM formal_collection_task_dependency AS dependency
                        JOIN formal_collection_task AS prerequisite
                          ON prerequisite.id = dependency.prerequisite_task_id
                        WHERE dependency.task_id = task.id
                          AND prerequisite.status IN ('terminal_failed','superseded')
                      )
                    ORDER BY task.id""",
                    (now,),
                ).fetchall()
                if not candidates:
                    break
                iteration_changed = 0
                for candidate in candidates:
                    task_id = str(candidate["id"])
                    blockers = [
                        str(row["prerequisite_task_id"])
                        for row in connection.execute(
                            """SELECT dependency.prerequisite_task_id
                            FROM formal_collection_task_dependency AS dependency
                            JOIN formal_collection_task AS prerequisite
                              ON prerequisite.id = dependency.prerequisite_task_id
                            WHERE dependency.task_id = ?
                              AND prerequisite.status IN ('terminal_failed','superseded')
                            ORDER BY dependency.prerequisite_task_id""",
                            (task_id,),
                        )
                    ]
                    error_json = _json(
                        {
                            "blocking_prerequisite_task_ids": blockers,
                            "code": "prerequisite_terminal_failed",
                        }
                    )
                    cursor = connection.execute(
                        """UPDATE formal_collection_task
                        SET status = 'terminal_failed', lease_worker = NULL,
                            lease_expires_at = NULL, next_retry_at = NULL,
                            result_json = NULL, error_json = ?, updated_at = ?
                        WHERE id = ?
                          AND (
                            status IN ('pending','retryable_failed')
                            OR (
                                status = 'leased'
                                AND lease_expires_at IS NOT NULL
                                AND lease_expires_at <= ?
                            )
                          )
                          AND EXISTS (
                            SELECT 1
                            FROM formal_collection_task_dependency AS dependency
                            JOIN formal_collection_task AS prerequisite
                              ON prerequisite.id = dependency.prerequisite_task_id
                            WHERE dependency.task_id = formal_collection_task.id
                              AND prerequisite.status IN (
                                'terminal_failed','superseded'
                              )
                          )""",
                        (error_json, now, task_id, now),
                    )
                    iteration_changed += cursor.rowcount
                if iteration_changed == 0:
                    break
                changed += iteration_changed
        return changed

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
    def _formal_task_public(
        row: sqlite3.Row, prerequisite_task_ids: Sequence[str]
    ) -> dict[str, object]:
        payload_json = str(row["payload_json"])
        payload = _decode_canonical_mapping_json(payload_json, "payload")
        payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if row["payload_sha256"] != payload_sha256:
            raise ValueError("stored formal task payload hash mismatch")
        result_json = row["result_json"]
        error_json = row["error_json"]
        public = dict(row)
        public.pop("payload_json")
        public.pop("result_json")
        public.pop("error_json")
        public["payload"] = payload
        public["result"] = (
            _decode_canonical_mapping_json(str(result_json), "result")
            if result_json is not None
            else None
        )
        public["error"] = (
            _decode_canonical_mapping_json(str(error_json), "error")
            if error_json is not None
            else None
        )
        public["prerequisite_task_ids"] = sorted(prerequisite_task_ids)
        return public

    @staticmethod
    def _require_formal_verified_task_state(
        row: sqlite3.Row, task: Mapping[str, object]
    ) -> None:
        _require_canonical_uuid(row["id"], "task ID")
        created_at = _require_canonical_utc(row["created_at"], "task creation time")
        updated_at = _require_canonical_utc(row["updated_at"], "task update time")
        if datetime.fromisoformat(updated_at) < datetime.fromisoformat(created_at):
            raise ValueError("stored formal verified task timestamps are out of order")
        if (
            task["status"] != "verified"
            or task["result"] is None
            or task["error"] is not None
            or any(
                row[field] is not None
                for field in (
                    "error_json",
                    "lease_worker",
                    "lease_expires_at",
                    "next_retry_at",
                )
            )
        ):
            raise ValueError("stored formal verified task state is invalid")

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
