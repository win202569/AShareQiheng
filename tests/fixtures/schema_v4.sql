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
CREATE TABLE financial_fact(
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
);
CREATE TABLE feature_set(
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
);
CREATE TABLE feature_value(
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
);
CREATE INDEX financial_fact_lookup_idx
    ON financial_fact(security_id,metric_key,period_end,effective_at_utc);
CREATE INDEX financial_fact_snapshot_idx
    ON financial_fact(source_snapshot_id);
CREATE INDEX feature_set_latest_idx
    ON feature_set(security_id,report_period,contract_version,as_of_utc DESC,created_at DESC);
CREATE TABLE quality_issue_binding(
    issue_id TEXT PRIMARY KEY REFERENCES quality_issue(id),
    job_id TEXT NOT NULL REFERENCES job(id),
    source_snapshot_id TEXT NOT NULL REFERENCES source_snapshot(id)
);
CREATE TABLE schema_migration(
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
INSERT INTO schema_migration(version, applied_at) VALUES
    (2, '2026-08-01T00:00:02+00:00'),
    (3, '2026-08-01T00:00:03+00:00'),
    (4, '2026-08-01T00:00:04+00:00');
