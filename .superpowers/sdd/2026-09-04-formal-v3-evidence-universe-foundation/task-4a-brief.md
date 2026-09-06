# Task 4A — V5 schema migration and literal V4 fixture

This is the first serial subunit of plan Task 4. Implement only the additive SQLite schema/migration foundation. Do not add the formal task-queue, snapshot writer/receipt, or universe/status persistence APIs yet; those have separate reviewed subunits.

## Files and scope

- Modify `ashare_pipeline/state_store.py`: `SCHEMA_VERSION`, V5 DDL/index constants, migration application, and initialization/migration-ledger validation only.
- Modify `tests/test_state_store.py`: V4-to-V5 migration and legacy-preservation coverage only.
- Create `tests/fixtures/schema_v4.sql`: a literal historical V4 database schema/ledger fixture.

Keep legacy V1–V4 tables and APIs behavior-identical. Do not edit data, SQLite/WAL/SHM, `data/status/pipeline_status.json`, or the legacy snapshot repository.

## Required RED test

First add a focused V4-to-V5 migration test. It must create a database from `schema_v4.sql`, seed at least legacy `score_run` (and preserve the existing legacy fixture rows), initialize `StateStore`, and assert:

- migration succeeds with schema ledger `2,3,4,5`;
- legacy rows remain available and unchanged;
- formal tables include at least `formal_source_snapshot`, `formal_universe_source`, `formal_universe_status`, and `formal_collection_task`;
- `formal_source_snapshot` has `request_fingerprint`;
- a non-continuous historical migration ledger is rejected rather than repaired or skipped.

Run the focused test before production migration code and record the expected RED caused by absent V5 schema/migration.

## V5 migration contract

Set `SCHEMA_VERSION = 5`. Add `_V5_TABLE_DDL`, `_V5_INDEX_DDL`, and `_apply_v5_migration`; `initialize()` accepts only continuous migration prefixes through `{2,3,4,5}` and applies V5 atomically after validating prior V2/V3/V4 structures. It must never copy legacy `source_snapshot` rows into formal tables.

Create all eight V5 formal tables now, with the plan's core columns:

```text
formal_source_snapshot:
  id, source, dataset, request_json, request_fingerprint, content_sha256, manifest_sha256,
  content_path, manifest_path, original_url, published_at_utc,
  published_precision, source_updated_at_utc, captured_at_utc,
  effective_at_utc, effective_time_evidence_hash, parser_id, parser_version, mapping_version,
  refresh_generation, producing_task_id, verification_json, created_at

formal_task_snapshot_receipt:
  task_id PRIMARY KEY, snapshot_id UNIQUE, manifest_sha256 UNIQUE, refresh_generation, recorded_at

formal_universe_snapshot:
  id, as_of_utc, registry_manifest_hash, universe_hash, source_audit_hash,
  frozen_input_hash UNIQUE, created_at

formal_universe_source:
  universe_snapshot_id, exchange, source_snapshot_id, manifest_sha256,
  source_content_sha256, parser_id, parser_version,
  extraction_audit_hash, extraction_json, created_at
  PRIMARY KEY (universe_snapshot_id, exchange)

formal_universe_member:
  snapshot_id, security_id, exchange, code6, security_type, listing_status, raw_json

formal_universe_status:
  snapshot_id, security_id, status, reasons_json, veto_flags_json, evidence_hash, updated_at

formal_collection_task:
  id, kind, idempotency_key, refresh_generation, payload_json, payload_sha256, status, lease_worker,
  lease_expires_at, next_retry_at, result_json, error_json, created_at, updated_at

formal_collection_task_dependency:
  task_id, prerequisite_task_id, created_at
  PRIMARY KEY (task_id, prerequisite_task_id)
```

Use explicit primary keys/unique constraints/FKs required by those relationships: source snapshot `id` primary key and `manifest_sha256` unique; member/status primary keys `(snapshot_id, security_id)`; FKs from universe source/member/status, receipt, and task dependency to their formal parents; task idempotency key unique; and no circular snapshot-to-receipt foreign key. Add the required unique expression index on `(request_fingerprint, refresh_generation, COALESCE(producing_task_id, 'bootstrap'))` and an exact-request lookup index. Future subunits enforce application-level same-transaction receipt linkage; do not attempt a circular DDL constraint.

The literal `schema_v4.sql` must contain exact V2 DDL, V3 financial/feature DDL/indexes, V4 `quality_issue_binding`, and migration ledger rows 2/3/4. It is a historical fixture, not a runtime schema generator.

## Existing contract/rulings

- Formal domain is additive and isolated: legacy `job`, `source_snapshot`, `score_item`, and old 23:59:59 cutoff behavior remain legacy-only.
- Formal task states will later be `pending`, `leased`, `verified`, `retryable_failed`, `terminal_failed`, `superseded`; do not reuse legacy job state code in this subunit.
- Task 3's typed `FormalFrozenUniverseInput` and its frozen-input hash formula are authoritative for later universe persistence; no universe persistence API belongs here.
- “Signed manifest” in later Task 4 prose means the existing canonical hash-verified raw-store manifest; do not introduce cryptographic signing here.

## GREEN and commit

After the minimal migration is implemented, run the focused migration test and the relevant legacy state-store regression suite. Run the full suite once before commit if it completes; the controller has documented a pre-existing load-sensitive deep-worker lease test and will separately triage it if it recurs. Commit only the three listed Task 4A files with subject `feat: add formal v5 schema migration`.
