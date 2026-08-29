"""SQLite-backed state transitions for resumable pipeline work."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


JOB_STATES = {"pending", "running", "succeeded", "retryable_failed", "terminal_failed"}
SCORE_RUN_STATES = {"provisional", "final", "invalidated"}
SCORE_ITEM_STATES = {"pending", "partial", "ready", "blocked", "final"}
RUN_STATES = {"running", "succeeded", "failed", "cancelled"}
SCHEMA_VERSION = 2


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
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS run (
                    id TEXT PRIMARY KEY, mode TEXT NOT NULL, as_of_cn TEXT NOT NULL,
                    params_json TEXT NOT NULL, status TEXT NOT NULL,
                    error TEXT, started_at TEXT NOT NULL, finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS job (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL, status TEXT NOT NULL,
                    lease_worker TEXT, lease_expires_at TEXT, next_retry_at TEXT,
                    result_json TEXT, last_error_json TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    CHECK (status IN ('pending','running','succeeded','retryable_failed','terminal_failed'))
                );
                CREATE INDEX IF NOT EXISTS job_lease_idx ON job(kind, status, next_retry_at);
                CREATE TABLE IF NOT EXISTS artifact (
                    id TEXT PRIMARY KEY, run_id TEXT REFERENCES run(id), kind TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, path TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(run_id, kind, payload_hash)
                );
                CREATE TABLE IF NOT EXISTS source_snapshot (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, dataset TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    payload_path TEXT NOT NULL, row_count INTEGER NOT NULL, fetched_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(source, dataset, request_fingerprint, payload_hash)
                );
                CREATE TABLE IF NOT EXISTS score_run (
                    id TEXT PRIMARY KEY, report_period TEXT NOT NULL, as_of_cn TEXT NOT NULL,
                    ruleset_hash TEXT NOT NULL, universe_hash TEXT NOT NULL, mode TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, finalized_at TEXT,
                    cutoff_utc TEXT, market_ready INTEGER, quality_passed INTEGER,
                    market_evidence_json TEXT, quality_evidence_json TEXT,
                    CHECK (status IN ('provisional','final','invalidated'))
                );
                CREATE TABLE IF NOT EXISTS score_item (
                    score_run_id TEXT NOT NULL REFERENCES score_run(id), security_id TEXT NOT NULL,
                    state TEXT NOT NULL, coverage REAL NOT NULL, input_hash TEXT NOT NULL,
                    scores_json TEXT, reasons_json TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(score_run_id, security_id),
                    CHECK (state IN ('pending','partial','ready','blocked','final')),
                    CHECK (coverage >= 0 AND coverage <= 1)
                );
                CREATE TABLE IF NOT EXISTS quality_issue (
                    id TEXT PRIMARY KEY, run_id TEXT REFERENCES run(id), score_run_id TEXT REFERENCES score_run(id),
                    severity TEXT NOT NULL, code TEXT NOT NULL, details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(score_run)")}
            for name, definition in (
                ("cutoff_utc", "TEXT"),
                ("market_ready", "INTEGER"),
                ("quality_passed", "INTEGER"),
                ("market_evidence_json", "TEXT"),
                ("quality_evidence_json", "TEXT"),
            ):
                if name not in existing_columns:
                    connection.execute(f"ALTER TABLE score_run ADD COLUMN {name} {definition}")
        finally:
            connection.close()

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
    def _job_public(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"], "kind": row["kind"], "idempotency_key": row["idempotency_key"],
            "status": row["status"], "lease_worker": row["lease_worker"],
            "lease_expires_at": row["lease_expires_at"], "payload": json.loads(row["payload_json"]),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": json.loads(row["last_error_json"]) if row["last_error_json"] else None,
            "next_retry_at": row["next_retry_at"],
        }
