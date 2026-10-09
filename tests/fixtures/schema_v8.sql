-- Released V7 literal schema: independent of the migration under test.
CREATE TABLE IF NOT EXISTS schema_migration(
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
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
CREATE INDEX IF NOT EXISTS job_lease_idx ON job(kind, status, next_retry_at);
CREATE TABLE IF NOT EXISTS financial_fact(
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
CREATE TABLE IF NOT EXISTS feature_set(
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
CREATE TABLE IF NOT EXISTS feature_value(
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
CREATE INDEX IF NOT EXISTS financial_fact_lookup_idx
        ON financial_fact(security_id,metric_key,period_end,effective_at_utc);
CREATE INDEX IF NOT EXISTS financial_fact_snapshot_idx
        ON financial_fact(source_snapshot_id);
CREATE INDEX IF NOT EXISTS feature_set_latest_idx
        ON feature_set(security_id,report_period,contract_version,as_of_utc DESC,created_at DESC);
CREATE TABLE IF NOT EXISTS quality_issue_binding(
        issue_id TEXT PRIMARY KEY REFERENCES quality_issue(id),
        job_id TEXT NOT NULL REFERENCES job(id),
        source_snapshot_id TEXT NOT NULL REFERENCES source_snapshot(id)
    );
CREATE TABLE IF NOT EXISTS formal_collection_task(
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
    );
CREATE TABLE IF NOT EXISTS formal_source_snapshot(
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
    );
CREATE TABLE IF NOT EXISTS formal_task_snapshot_receipt(
        task_id TEXT PRIMARY KEY REFERENCES formal_collection_task(id),
        snapshot_id TEXT NOT NULL UNIQUE REFERENCES formal_source_snapshot(id),
        manifest_sha256 TEXT NOT NULL UNIQUE,
        refresh_generation TEXT NOT NULL CHECK(refresh_generation<>''),
        recorded_at TEXT NOT NULL
    );
CREATE TABLE IF NOT EXISTS formal_universe_snapshot(
        id TEXT PRIMARY KEY,
        as_of_utc TEXT NOT NULL,
        registry_manifest_hash TEXT NOT NULL,
        universe_hash TEXT NOT NULL,
        source_audit_hash TEXT NOT NULL,
        frozen_input_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    );
CREATE TABLE IF NOT EXISTS formal_universe_source(
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
    );
CREATE TABLE IF NOT EXISTS formal_universe_member(
        snapshot_id TEXT NOT NULL REFERENCES formal_universe_snapshot(id),
        security_id TEXT NOT NULL,
        exchange TEXT NOT NULL CHECK(exchange IN('SH','SZ','BJ')),
        code6 TEXT NOT NULL,
        security_type TEXT NOT NULL,
        listing_status TEXT NOT NULL,
        raw_json TEXT NOT NULL,
        PRIMARY KEY(snapshot_id,security_id)
    );
CREATE TABLE IF NOT EXISTS formal_universe_status(
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
    );
CREATE TABLE IF NOT EXISTS formal_collection_task_dependency(
        task_id TEXT NOT NULL REFERENCES formal_collection_task(id),
        prerequisite_task_id TEXT NOT NULL REFERENCES formal_collection_task(id),
        created_at TEXT NOT NULL,
        PRIMARY KEY(task_id,prerequisite_task_id)
    );
CREATE UNIQUE INDEX IF NOT EXISTS
        formal_source_snapshot_lineage_idx ON formal_source_snapshot(
            request_fingerprint,
            refresh_generation,
            COALESCE(producing_task_id,'bootstrap')
        );
CREATE INDEX IF NOT EXISTS
        formal_source_snapshot_exact_request_idx ON formal_source_snapshot(
            source,dataset,request_fingerprint,refresh_generation,created_at DESC
        );
CREATE TABLE formal_financial_fact (
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
    );
CREATE TABLE formal_quarter_fact (
        id TEXT PRIMARY KEY, security_id TEXT NOT NULL, statement TEXT NOT NULL,
        metric_key TEXT NOT NULL, quarter_end TEXT NOT NULL, quarter_key TEXT NOT NULL,
        value REAL NOT NULL, unit TEXT NOT NULL, nature TEXT NOT NULL,
        accounting_basis TEXT NOT NULL, mapping_version TEXT NOT NULL,
        component_fact_ids_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
        derivation_version TEXT NOT NULL, created_at_utc TEXT NOT NULL
    );
CREATE TABLE formal_feature_set (
        id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, contract_version TEXT NOT NULL,
        security_id TEXT NOT NULL, as_of_utc TEXT NOT NULL, template_id TEXT NOT NULL,
        registry_manifest_hash TEXT NOT NULL, feature_registry_hash TEXT NOT NULL,
        input_hash TEXT NOT NULL UNIQUE, history_endpoints_json TEXT NOT NULL,
        comparable_quarter_keys_json TEXT NOT NULL, blockers_json TEXT NOT NULL,
        bundle_hash TEXT NOT NULL, bundle_manifest_hash TEXT NOT NULL,
        bundle_path TEXT NOT NULL, manifest_path TEXT NOT NULL, created_at_utc TEXT NOT NULL
    );
CREATE TABLE formal_feature_value (
        feature_set_id TEXT NOT NULL REFERENCES formal_feature_set(id), slot_id TEXT NOT NULL,
        value REAL, unit TEXT NOT NULL, status TEXT NOT NULL, formula_version TEXT NOT NULL,
        evidence_json TEXT NOT NULL, missing_reason TEXT,
        PRIMARY KEY(feature_set_id, slot_id)
    );
CREATE TABLE formal_context_fact (
        id TEXT PRIMARY KEY, context_kind TEXT NOT NULL, scope_key TEXT NOT NULL,
        security_id TEXT, as_of_utc TEXT NOT NULL, value_json TEXT NOT NULL,
        no_coverage INTEGER NOT NULL, published_at_utc TEXT NOT NULL,
        effective_at_utc TEXT NOT NULL, source_updated_at_utc TEXT, captured_at_utc TEXT NOT NULL,
        refresh_generation TEXT NOT NULL, source_snapshot_id TEXT NOT NULL REFERENCES formal_source_snapshot(id),
        source_content_sha256 TEXT NOT NULL, parser_id TEXT NOT NULL, parser_version TEXT NOT NULL,
        mapping_version TEXT NOT NULL, registry_manifest_hash TEXT NOT NULL,
        evidence_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
    );
CREATE TABLE formal_registry_manifest (
        manifest_hash TEXT PRIMARY KEY, purpose TEXT NOT NULL, approval_id TEXT,
        canonical_json BLOB NOT NULL, signature TEXT NOT NULL, key_id TEXT NOT NULL,
        source_registry_hash TEXT NOT NULL, mapping_registry_hash TEXT NOT NULL,
        feature_registry_hash TEXT NOT NULL, scoring_registry_hash TEXT NOT NULL,
        industry_registry_hash TEXT NOT NULL, cyclic_registry_hash TEXT NOT NULL,
        redline_registry_hash TEXT NOT NULL, status_registry_hash TEXT NOT NULL,
        event_registry_hash TEXT NOT NULL, created_at_utc TEXT NOT NULL
    );
CREATE TABLE formal_registry_blob (
        registry_hash TEXT PRIMARY KEY, registry_role TEXT NOT NULL, canonical_json BLOB NOT NULL,
        signature TEXT NOT NULL, key_id TEXT NOT NULL, approval_id TEXT,
        declared_registry_manifest_hash TEXT NOT NULL, binding_signature TEXT NOT NULL,
        binding_key_id TEXT NOT NULL, created_at_utc TEXT NOT NULL
    );
CREATE TABLE formal_source_circuit (
        source TEXT PRIMARY KEY, state TEXT NOT NULL, failure_count INTEGER NOT NULL,
        reason_json TEXT NOT NULL, opened_at_utc TEXT, retry_after_utc TEXT, updated_at_utc TEXT NOT NULL
    );
CREATE INDEX idx_formal_financial_fact_security ON formal_financial_fact(security_id, period_end, statement, metric_key, id);
CREATE INDEX idx_formal_quarter_fact_security ON formal_quarter_fact(security_id, quarter_end, statement, metric_key, id);
CREATE INDEX idx_formal_feature_set_header ON formal_feature_set(security_id, as_of_utc, template_id, registry_manifest_hash, id);
CREATE TABLE formal_range_task (
 id TEXT PRIMARY KEY,
 request_fingerprint TEXT NOT NULL,
 registry_manifest_hash TEXT NOT NULL,
 range_config_id TEXT NOT NULL,
 refresh_generation TEXT NOT NULL CHECK(length(refresh_generation)>0),
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','leased','verified',
   'retryable_failed','terminal_failed','superseded')),
 worker_id TEXT, lease_expires_at TEXT, attempt_no INTEGER NOT NULL DEFAULT 0,
 next_retry_at TEXT, result_json TEXT, error_json TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(request_fingerprint,registry_manifest_hash,range_config_id,refresh_generation),
 CHECK(attempt_no>=0),
 CHECK((status='leased' AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status<>'leased' AND worker_id IS NULL AND lease_expires_at IS NULL)),
 CHECK((status='retryable_failed')=(next_retry_at IS NOT NULL)),
 CHECK(status<>'verified' OR (result_json IS NOT NULL AND error_json IS NULL)),
 CHECK(status NOT IN ('retryable_failed','terminal_failed') OR error_json IS NOT NULL)
);
CREATE TABLE formal_range_attempt (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES formal_range_task(id),
 attempt_no INTEGER NOT NULL CHECK(attempt_no>0), worker_id TEXT NOT NULL,
 leased_at TEXT NOT NULL, lease_expires_at TEXT NOT NULL, finished_at TEXT,
 outcome TEXT CHECK(outcome IN ('verified','retryable_failed','terminal_failed','expired')),
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 UNIQUE(task_id,attempt_no), CHECK((finished_at IS NULL)=(outcome IS NULL))
);
CREATE TABLE formal_range_snapshot (
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL UNIQUE REFERENCES formal_range_task(id),
 request_fingerprint TEXT NOT NULL, registry_manifest_hash TEXT NOT NULL,
 range_config_id TEXT NOT NULL, refresh_generation TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, content_path TEXT NOT NULL,
 manifest_sha256 TEXT NOT NULL UNIQUE, manifest_path TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE formal_range_normalization_receipt (
 task_id TEXT PRIMARY KEY REFERENCES formal_range_task(id),
 snapshot_id TEXT NOT NULL UNIQUE REFERENCES formal_range_snapshot(id),
 attempt_id TEXT NOT NULL REFERENCES formal_range_attempt(id),
 request_fingerprint TEXT NOT NULL, registry_manifest_hash TEXT NOT NULL,
 range_config_id TEXT NOT NULL, refresh_generation TEXT NOT NULL,
 manifest_sha256 TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 normalization_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE INDEX formal_range_task_ready ON formal_range_task(status,next_retry_at,created_at,id);
CREATE INDEX formal_range_snapshot_request ON formal_range_snapshot(request_fingerprint,refresh_generation);
INSERT INTO schema_migration VALUES (2,'released-v2');
INSERT INTO schema_migration VALUES (3,'released-v3');
INSERT INTO schema_migration VALUES (4,'released-v4');
INSERT INTO schema_migration VALUES (5,'released-v5');
INSERT INTO schema_migration VALUES (6,'released-v6');
INSERT INTO schema_migration VALUES (7,'released-v7');

-- Real linked V7 rows plus legacy scoring content, retained byte-for-byte.
INSERT INTO formal_range_task
 (id,request_fingerprint,registry_manifest_hash,range_config_id,refresh_generation,
  payload_json,payload_hash,status,created_at,updated_at)
 VALUES ('range-task','request','root','config','generation','{"decimal":"0.10000000000000000001"}',
  'task-hash','pending','2026-09-28T00:00:00Z','2026-09-28T00:00:00Z');
INSERT INTO formal_range_attempt
 (id,task_id,attempt_no,worker_id,leased_at,lease_expires_at,finished_at,outcome,payload_json,payload_hash)
 VALUES ('range-attempt','range-task',1,'worker','2026-09-28T00:00:00Z','2026-09-28T00:01:00Z',
  '2026-09-28T00:00:30Z','verified','{"unchanged":true}','attempt-hash');
INSERT INTO formal_range_snapshot VALUES
 ('range-snapshot','range-task','request','root','config','generation','content-hash','raw/content.json',
  'manifest-hash','raw/manifest.json','{"original":"原始"}','snapshot-hash','2026-09-28T00:00:30Z');
INSERT INTO formal_range_normalization_receipt VALUES
 ('range-task','range-snapshot','range-attempt','request','root','config','generation',
  'manifest-hash','content-hash','normalization-hash','{"retained":true}','receipt-hash','2026-09-28T00:00:30Z');
INSERT INTO score_run VALUES
 ('legacy-score','2026-06-30','2026-09-28','rules','universe','incremental','provisional',
  '2026-09-28T00:00:00Z',NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO score_item VALUES
 ('legacy-score','SH600001','partial',0.5,'legacy-input','{"total":42.5}','["legacy"]','2026-09-28T00:00:00Z');

-- Frozen V8 Stage D baseline; independent of later migrator definitions.
CREATE TABLE formal_final_run (
 run_id TEXT NOT NULL PRIMARY KEY,
 mode TEXT NOT NULL CHECK(mode IN ('test_preview','official_candidate')),
 status TEXT NOT NULL CHECK(status IN ('preview_ready','blocked')),
 input_manifest_hash TEXT NOT NULL, result_hash TEXT NOT NULL,
 registry_manifest_hash TEXT NOT NULL, frozen_input_hash TEXT NOT NULL,
 universe_hash TEXT NOT NULL, coverage_manifest_hash TEXT NOT NULL,
 as_of_utc TEXT NOT NULL, code_version TEXT NOT NULL,
 contract_version TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE formal_final_artifact (
 run_id TEXT NOT NULL REFERENCES formal_final_run(run_id),
 artifact_kind TEXT NOT NULL, payload_json TEXT NOT NULL, artifact_hash TEXT NOT NULL,
 PRIMARY KEY(run_id,artifact_kind)
);
CREATE TABLE formal_final_input (
 run_id TEXT NOT NULL REFERENCES formal_final_run(run_id),
 security_id TEXT NOT NULL, entry_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 PRIMARY KEY(run_id,security_id)
);
CREATE TABLE formal_final_scorecard (
 run_id TEXT NOT NULL, security_id TEXT NOT NULL, card_hash TEXT NOT NULL,
 S0 TEXT NOT NULL, Sc TEXT NOT NULL, Sbase TEXT NOT NULL,
 B TEXT NOT NULL, R_safety TEXT NOT NULL, C TEXT NOT NULL, grade TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 PRIMARY KEY(run_id,security_id),
 FOREIGN KEY(run_id,security_id) REFERENCES formal_final_input(run_id,security_id)
);
CREATE TABLE formal_final_status (
 run_id TEXT NOT NULL, security_id TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('out_of_scope','pending_evidence','pool_vetoed','formal_scored')),
 reason_codes_json TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 PRIMARY KEY(run_id,security_id),
 FOREIGN KEY(run_id,security_id) REFERENCES formal_final_input(run_id,security_id)
);
CREATE TABLE formal_final_eligibility (
 run_id TEXT NOT NULL, security_id TEXT NOT NULL, eligibility_hash TEXT NOT NULL,
 strong_qualified INTEGER NOT NULL CHECK(strong_qualified IN (0,1)),
 wait_qualified INTEGER NOT NULL CHECK(wait_qualified IN (0,1)),
 hard_veto INTEGER NOT NULL CHECK(hard_veto IN (0,1)),
 strong_prohibited INTEGER NOT NULL CHECK(strong_prohibited IN (0,1)),
 wait_prohibited INTEGER NOT NULL CHECK(wait_prohibited IN (0,1)),
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 PRIMARY KEY(run_id,security_id), CHECK(strong_qualified+wait_qualified<=1),
 CHECK(strong_qualified=0 OR (hard_veto=0 AND strong_prohibited=0)),
 CHECK(wait_qualified=0 OR (hard_veto=0 AND wait_prohibited=0)),
 FOREIGN KEY(run_id,security_id) REFERENCES formal_final_input(run_id,security_id)
);
CREATE TABLE formal_final_pool_decision (
 run_id TEXT NOT NULL, security_id TEXT NOT NULL,
 pool_name TEXT NOT NULL CHECK(pool_name IN ('strong','wait')),
 decision TEXT NOT NULL CHECK(decision IN ('selected','not_qualified','overall_capacity_reached','industry_cap_reached')),
 selected_ordinal INTEGER, decision_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 PRIMARY KEY(run_id,security_id,pool_name),
 CHECK((decision='selected' AND selected_ordinal IS NOT NULL
        AND typeof(selected_ordinal)='integer' AND selected_ordinal>0)
       OR (decision<>'selected' AND selected_ordinal IS NULL)),
 FOREIGN KEY(run_id,security_id) REFERENCES formal_final_eligibility(run_id,security_id)
);
CREATE TABLE formal_final_dependency (
 run_id TEXT NOT NULL REFERENCES formal_final_run(run_id), security_id TEXT,
 source_kind TEXT NOT NULL, source_id TEXT NOT NULL, source_hash TEXT NOT NULL,
 effect_scope TEXT NOT NULL, dependent_key TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 PRIMARY KEY(run_id,source_kind,source_id,effect_scope,dependent_key),
 FOREIGN KEY(run_id,security_id) REFERENCES formal_final_input(run_id,security_id)
);
CREATE INDEX formal_final_run_input ON formal_final_run(input_manifest_hash,run_id);
CREATE UNIQUE INDEX formal_final_selected_ordinal ON formal_final_pool_decision(run_id,pool_name,selected_ordinal) WHERE decision='selected';
CREATE INDEX formal_final_dependency_source ON formal_final_dependency(source_kind,source_id,source_hash,run_id);
CREATE INDEX formal_final_dependency_effect ON formal_final_dependency(effect_scope,dependent_key,run_id);
INSERT INTO schema_migration VALUES (8,'2026-10-09T00:00:00+00:00');
INSERT INTO formal_final_run VALUES ('retained','official_candidate','preview_ready','input','result','root','frozen','universe','coverage','2026-08-31T07:00:00+00:00','code','V3','old-time');
-- Storage-preservation rows only; these are not genuine producer proofs.
INSERT INTO formal_final_artifact VALUES ('retained','coverage_manifest','{"retained":true}','coverage');
INSERT INTO formal_final_artifact VALUES ('retained','score_input_batch','{"retained":true}','inputs');
INSERT INTO formal_final_artifact VALUES ('retained','scorecard_batch','{"retained":true}','scores');
INSERT INTO formal_final_artifact VALUES ('retained','eligibility_batch','{"retained":true}','eligibility');
INSERT INTO formal_final_artifact VALUES ('retained','pool_selection_batch','{"retained":true}','pools');
INSERT INTO formal_final_input VALUES ('retained','SH600001','entry','{"retained":true}','input-payload');
INSERT INTO formal_final_scorecard VALUES ('retained','SH600001','card',
 '70.123456789012345678901234567890','70.123456789012345678901234567890',
 '72','72','80','0.96','B','{"retained":true}','card-payload');
INSERT INTO formal_final_status VALUES ('retained','SH600001','formal_scored','[]','{"retained":true}','status');
INSERT INTO formal_final_eligibility VALUES ('retained','SH600001','eligibility',1,0,0,0,0,'{"retained":true}','eligibility-payload');
INSERT INTO formal_final_pool_decision VALUES ('retained','SH600001','strong','selected',1,'decision','{"retained":true}','decision-payload');
INSERT INTO formal_final_dependency VALUES ('retained','SH600001','snapshot','source','source-hash','security','SH600001','{"retained":true}','dependency-payload');
