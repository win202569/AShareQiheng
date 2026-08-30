CREATE TABLE run (
    id TEXT PRIMARY KEY, mode TEXT NOT NULL, as_of_cn TEXT NOT NULL,
    params_json TEXT NOT NULL, status TEXT NOT NULL,
    error TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE job (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL, status TEXT NOT NULL,
    lease_worker TEXT, lease_expires_at TEXT, next_retry_at TEXT,
    result_json TEXT, last_error_json TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    CHECK (status IN ('pending','running','succeeded','retryable_failed','terminal_failed'))
);
CREATE INDEX job_lease_idx ON job(kind, status, next_retry_at);
CREATE TABLE artifact (
    id TEXT PRIMARY KEY, run_id TEXT REFERENCES run(id), kind TEXT NOT NULL,
    payload_hash TEXT NOT NULL, path TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(run_id, kind, payload_hash)
);
CREATE TABLE source_snapshot (
    id TEXT PRIMARY KEY, source TEXT NOT NULL, dataset TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL, payload_hash TEXT NOT NULL,
    payload_path TEXT NOT NULL, row_count INTEGER NOT NULL, fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source, dataset, request_fingerprint, payload_hash)
);
CREATE TABLE score_run (
    id TEXT PRIMARY KEY, report_period TEXT NOT NULL, as_of_cn TEXT NOT NULL,
    ruleset_hash TEXT NOT NULL, universe_hash TEXT NOT NULL, mode TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, finalized_at TEXT,
    cutoff_utc TEXT, market_ready INTEGER, quality_passed INTEGER,
    market_evidence_json TEXT, quality_evidence_json TEXT,
    CHECK (status IN ('provisional','final','invalidated'))
);
CREATE TABLE score_item (
    score_run_id TEXT NOT NULL REFERENCES score_run(id), security_id TEXT NOT NULL,
    state TEXT NOT NULL, coverage REAL NOT NULL, input_hash TEXT NOT NULL,
    scores_json TEXT, reasons_json TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(score_run_id, security_id),
    CHECK (state IN ('pending','partial','ready','blocked','final')),
    CHECK (coverage >= 0 AND coverage <= 1)
);
CREATE TABLE quality_issue (
    id TEXT PRIMARY KEY, run_id TEXT REFERENCES run(id), score_run_id TEXT REFERENCES score_run(id),
    severity TEXT NOT NULL, code TEXT NOT NULL, details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
