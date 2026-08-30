"""SQLite-backed state transitions for resumable pipeline work."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, Iterator, Mapping, Sequence

from ashare_pipeline.feature_contract import DIMENSIONS, FeatureBundle
from ashare_pipeline.financial_schema import FinancialFact


JOB_STATES = {"pending", "running", "succeeded", "retryable_failed", "terminal_failed"}
SCORE_RUN_STATES = {"provisional", "final", "invalidated"}
SCORE_ITEM_STATES = {"pending", "partial", "ready", "blocked", "final"}
RUN_STATES = {"running", "succeeded", "failed", "cancelled"}
SCHEMA_VERSION = 3

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


class FinalizationBlocked(RuntimeError):
    """The final publication gate has not yet been satisfied."""


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
    def _transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
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
                if versions not in ({2}, {2, 3}):
                    raise RuntimeError(f"unsupported migration versions: {sorted(versions)}")
                self._assert_v2_schema(connection)
                if versions == {2}:
                    partial_v3_tables = tables & set(_V3_TABLE_DDL)
                    if partial_v3_tables:
                        raise RuntimeError(
                            f"version-2 ledger has unexpected v3 tables: {sorted(partial_v3_tables)}"
                        )
                    self._apply_v3_migration(connection)
                else:
                    self._assert_schema_ddl(
                        connection,
                        _V3_TABLE_DDL,
                        _V3_INDEX_DDL,
                        "v3 schema",
                    )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

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

    def complete_job(self, job_id: str, result: dict) -> None:
        with self._transaction() as connection:
            cursor = connection.execute(
                """UPDATE job SET status = 'succeeded', result_json = ?, lease_worker = NULL,
                lease_expires_at = NULL, updated_at = ? WHERE id = ? AND status = 'running'""",
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

    def fail_job(
        self, job_id: str, error: dict, retryable: bool, next_retry_at: str | None = None
    ) -> None:
        state = "retryable_failed" if retryable else "terminal_failed"
        retry_at = _utc_iso(next_retry_at) if retryable and next_retry_at else None
        with self._transaction() as connection:
            cursor = connection.execute(
                """UPDATE job SET status = ?, last_error_json = ?, next_retry_at = ?,
                lease_worker = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'running'""",
                (state, _json(error), retry_at, _utc_now(), job_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("only running jobs can fail")

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
        payload_path: str, row_count: int, fetched_at: str
    ) -> tuple[str, bool]:
        snapshot_id = str(uuid.uuid4())
        with self._transaction(immediate=True) as connection:
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
    ) -> tuple[int, int]:
        records = tuple(facts)
        inserted = 0
        with self._transaction(immediate=True) as connection:
            for fact in records:
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
        return inserted, len(records) - inserted

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

    def put_feature_bundle(
        self,
        bundle: FeatureBundle,
        *,
        bundle_path: str,
        bundle_hash: str,
    ) -> tuple[str, bool]:
        bundle.validate()
        if bundle_hash != bundle.bundle_hash():
            raise ValueError("bundle_hash does not match canonical bundle hash")
        self._validate_feature_bundle_path(bundle_path)
        header, values = self._feature_bundle_content(bundle, bundle_hash)

        with self._transaction(immediate=True) as connection:
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
                if not self._stored_feature_content_matches(
                    connection, existing, header, values
                ):
                    raise ValueError("non-deterministic feature conflict")
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
    ) -> str:
        issue_id = str(uuid.uuid4())
        with self._transaction() as connection:
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
                    _json(dict(details)),
                    _utc_now(),
                ),
            )
        return issue_id

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
    def _stored_feature_content_matches(
        connection: sqlite3.Connection,
        existing: sqlite3.Row,
        header: Mapping[str, object],
        values: Sequence[Mapping[str, object]],
    ) -> bool:
        if any(existing[column] != header[column] for column in _FEATURE_SET_CONTENT_COLUMNS):
            return False
        stored_values = connection.execute(
            """SELECT dimension,feature_key,period_key,value,unit,status,
            formula_version,evidence_json,missing_reason FROM feature_value
            WHERE feature_set_id = ? ORDER BY dimension,feature_key,period_key""",
            (existing["id"],),
        ).fetchall()
        expected = sorted(
            (
                tuple(value[column] for column in _FEATURE_VALUE_CONTENT_COLUMNS)
                for value in values
            ),
            key=lambda value: (value[0], value[1], value[2]),
        )
        return [tuple(row) for row in stored_values] == expected

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
        }
