### Task 4: Additive SQLite V5 Formal Evidence and Universe Tables

**Files:**
- Modify: ashare_pipeline/state_store.py: schema constants, initialize, migrations, and public APIs
- Modify: tests/test_state_store.py: migration fixtures and StateStore tests
- Create: tests/fixtures/schema_v4.sql

**Interfaces:**
- Produces StateStore.put_formal_snapshot, put_formal_snapshot_for_leased_task, get_formal_task_snapshot_receipt, put_formal_universe_snapshot, get_formal_universe_snapshot_by_input_hash, get_formal_universe_snapshot_from_task, list_formal_universe_sources, replace_formal_universe_statuses, list_formal_universe_statuses, enqueue_formal_task, supersede_formal_tasks, lease_next_formal_task, resolve_formal_task_dependencies, complete_formal_task, and fail_formal_task.
- StateStore.put_formal_snapshot(fetch: OfficialFetch, stored: FormalStoredSnapshot, verification: EvidenceVerification) -> OfficialSnapshotRef and put_formal_snapshot_for_leased_task(fetch: OfficialFetch, stored: FormalStoredSnapshot, verification: EvidenceVerification, *, task_id: str, worker_id: str) -> OfficialSnapshotRef are the only V5 formal snapshot writers; they never accept a pre-persistence OfficialSnapshotRef.
- Formal task states are pending, leased, verified, retryable_failed, terminal_failed, and superseded; they are not legacy job states.
- V5 tables are formal_source_snapshot, formal_task_snapshot_receipt, formal_universe_snapshot, formal_universe_source, formal_universe_member, formal_universe_status, formal_collection_task, and formal_collection_task_dependency.

- [ ] **Step 1: Write failing V4-to-V5 migration and status-invariant tests**

~~~python
def test_v4_migration_preserves_legacy_rows_and_adds_formal_tables(self):
    migrate_fixture("schema_v4.sql", self.db_path)
    store = StateStore(self.db_path)
    store.initialize()
    with sqlite3.connect(self.db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    self.assertTrue({"formal_source_snapshot", "formal_universe_source", "formal_universe_status", "formal_collection_task"} <= tables)
    self.assertIn("request_fingerprint", table_columns(self.db_path, "formal_source_snapshot"))
    self.assertEqual(legacy_score_run_count(self.db_path), 1)

def test_universe_status_requires_one_row_per_member(self):
    snapshot_id = self.store.put_formal_universe_snapshot(frozen_universe_input())
    with self.assertRaisesRegex(ValueError, "exactly one status"):
        self.store.replace_formal_universe_statuses(snapshot_id, decisions()[:-1])

def test_frozen_universe_requires_one_verified_visible_source_for_each_exchange(self):
    with self.assertRaisesRegex(ValueError, "SH/SZ/BJ"):
        self.store.put_formal_universe_snapshot(
            FormalUniverseIngestor().build(
                FORMAL_FREEZE_AT_CN, "m" * 64, verified_listing_documents_for("SH", "SZ")
            )
        )

def test_same_frozen_input_recovers_the_existing_snapshot_without_duplicate_members(self):
    frozen = frozen_universe_input()
    first_id = self.store.put_formal_universe_snapshot(frozen)
    second_id = self.store.put_formal_universe_snapshot(frozen)
    self.assertEqual(second_id, first_id)
    self.assertEqual(
        self.store.get_formal_universe_snapshot_by_input_hash(frozen.frozen_input_hash)["id"],
        first_id,
    )

def test_frozen_input_hash_cannot_alias_different_root_or_source_lineage(self):
    frozen = frozen_universe_input()
    self.store.put_formal_universe_snapshot(frozen)
    conflicting = replace(frozen, registry_manifest_hash="n" * 64)
    with self.assertRaisesRegex(ValueError, "frozen_input_hash"):
        self.store.put_formal_universe_snapshot(conflicting)

def test_task_prerequisite_is_not_leased_early_and_terminal_parent_cascades(self):
    calendar_id = self.store.enqueue_formal_task(
        "formal_context", "calendar-v1", "calendar-v1", {"kind": "trading_calendar"}
    )
    dependent_id = self.store.enqueue_formal_task(
        "formal_statement", "statement-v1", "discovery-v1", {"kind": "profit_sheet"},
        prerequisite_task_ids=(calendar_id,),
    )
    self.assertIsNone(
        self.store.lease_next_formal_task(("formal_statement",), "worker-a", 30)
    )
    leased_calendar = self.store.lease_next_formal_task(("formal_context",), "worker-calendar", 30)
    self.assertEqual(leased_calendar["id"], calendar_id)
    self.store.fail_formal_task(calendar_id, "worker-calendar", {"code": "calendar_failed"}, "terminal_failed", None)
    self.store.resolve_formal_task_dependencies()
    self.assertEqual(self.store.get_formal_task(dependent_id)["status"], "terminal_failed")
    self.assertEqual(self.store.get_formal_task(dependent_id)["error"]["code"], "prerequisite_terminal_failed")

def test_verified_raw_receipt_survives_later_terminal_parse_failure(self):
    task_id = self.store.enqueue_formal_task(
        "formal_statement", "statement-v1", "discovery-v1", {"kind": "profit_sheet"}
    )
    self.store.lease_next_formal_task(("formal_statement",), "worker-a", 30)
    fetch, stored, verification = written_verified_formal_snapshot(
        refresh_generation="discovery-v1", producing_task_id=task_id
    )
    snapshot = self.store.put_formal_snapshot_for_leased_task(
        fetch, stored, verification, task_id=task_id, worker_id="worker-a"
    )
    self.store.fail_formal_task(
        task_id, "worker-a", {"code": "fact_schema_invalid", "snapshot_id": snapshot.snapshot_id},
        "terminal_failed", None,
    )
    self.assertEqual(self.store.get_formal_task_snapshot_receipt(task_id)["snapshot_id"], snapshot.snapshot_id)
    self.assertEqual(self.store.get_formal_snapshot(snapshot.snapshot_id)["verification_status"], "verified")

def test_snapshot_recomputes_request_fingerprint_from_canonical_request_json(self):
    fetch, stored, verification = written_verified_formal_snapshot(
        refresh_generation="bootstrap-v1", producing_task_id=None
    )
    ref = self.store.put_formal_snapshot(fetch, stored, verification)
    self.assertEqual(ref.request_fingerprint, fetch.request.request_fingerprint)
    mismatched_fetch = replace(
        fetch, request=OfficialRequest(fetch.request.source, fetch.request.dataset, "SZ000002", fetch.request.period_or_date)
    )
    with self.assertRaisesRegex(ValueError, "request_fingerprint"):
        self.store.put_formal_snapshot(mismatched_fetch, stored, verification)

def test_retryable_and_expired_leased_tasks_are_reclaimed_only_when_ready(self):
    task_id = self.store.enqueue_formal_task(
        "formal_statement", "statement-v1", "root-aware-v1", {"kind": "profit_sheet"}
    )
    first = self.store.lease_next_formal_task(
        ("formal_statement",), "worker-a", 30, now_utc="2026-09-04T00:00:00+00:00"
    )
    self.store.fail_formal_task(
        task_id, "worker-a", {"code": "timeout"}, "retryable_failed",
        "2026-09-04T00:01:00+00:00",
    )
    self.assertIsNone(self.store.lease_next_formal_task(
        ("formal_statement",), "worker-b", 30, now_utc="2026-09-04T00:00:59+00:00"
    ))
    retry = self.store.lease_next_formal_task(
        ("formal_statement",), "worker-b", 30, now_utc="2026-09-04T00:01:00+00:00"
    )
    self.assertEqual(retry["id"], task_id)
    reclaimed = self.store.lease_next_formal_task(
        ("formal_statement",), "worker-c", 30, now_utc="2026-09-04T00:01:31+00:00"
    )
    self.assertEqual(reclaimed["id"], task_id)

def test_same_key_with_changed_canonical_payload_is_rejected(self):
    self.store.enqueue_formal_task(
        "formal_statement", "statement-v1", "root-aware-v1", {"root_manifest": "a" * 64}
    )
    with self.assertRaisesRegex(ValueError, "idempotency_payload_conflict"):
        self.store.enqueue_formal_task(
            "formal_statement", "statement-v1", "root-aware-v1", {"root_manifest": "b" * 64}
        )
~~~

- [ ] **Step 2: Run migration tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_v4_migration_preserves_legacy_rows_and_adds_formal_tables -v
~~~

Expected: FAIL because schema v5 and APIs do not exist.

- [ ] **Step 3: Implement V5 migration and persistence APIs**

Set SCHEMA_VERSION to 5. Add _V5_TABLE_DDL, _V5_INDEX_DDL, _apply_v5_migration, and extend initialize() so only continuous migrations 2,3,4,5 are accepted. Use these core columns:

~~~text
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
~~~

Require all formal status rows to reference an existing member, reject duplicate member/status rows, and reject a source snapshot whose verification JSON is not verified. formal_source_snapshot is lineage-addressed by manifest_sha256, not merely raw content_sha256: identical bytes from different refresh generations or producing tasks create separate snapshot rows that may share only the immutable .bin path. On every write and read, recompute request_fingerprint from canonical request_json and reject a mismatch; add a unique expression index over (request_fingerprint, refresh_generation, COALESCE(producing_task_id, 'bootstrap')) plus an index for exact request lookup. Every formal source snapshot has a nonempty immutable refresh_generation; producing_task_id is either null for an explicitly verified bootstrap/discovery snapshot or foreign-references formal_collection_task.id. A nonnull producing_task_id must be paired with exactly one formal_task_snapshot_receipt for the same task/snapshot in the same transaction; do not create a circular source-snapshot-to-receipt foreign key. The snapshot write APIs accept OfficialFetch, FormalStoredSnapshot, and EvidenceVerification—not OfficialSnapshotRef—and return an OfficialSnapshotRef only after the row and signed manifest have been stored and re-read. put_formal_snapshot accepts only a stored manifest whose producing_task_id is null. put_formal_snapshot_for_leased_task atomically inserts the snapshot row and its receipt while the named task is leased by the named worker; it requires the task generation, snapshot generation, signed manifest linkage, request fingerprint, and receipt manifest_sha256 to agree. The receipt proves a verified raw fetch even if a later parse/feature step changes that task to terminal_failed; no source snapshot may claim a task merely because that task later became verified. complete_formal_task for a source-fetch task requires its exact receipt, while fail_formal_task may retain that receipt together with a deterministic downstream parse/build error. put_formal_universe_snapshot(frozen: FormalFrozenUniverseInput) accepts only the typed output of FormalUniverseIngestor and recomputes frozen_input_hash from its freeze instant, registry_manifest_hash, canonical member set, and exact source manifest/extraction lineage. For every source it requires a nonnull producing_task_id whose receipt points back to that snapshot, then requires that task to be a verified formal_universe_source task whose canonical payload and result both carry the same registry_manifest_hash and declared exchange as frozen; bootstrap/discovery snapshots are never eligible as universe sources. It rechecks the root/task linkage, member set, every extraction JSON/hash, source content hash, parser ID/version, and source manifest against those linked verified formal snapshots and task receipts. In one transaction it either returns the one pre-existing row with the identical frozen_input_hash and byte-equivalent canonical frozen input, or inserts a frozen snapshot, all members, one formal_universe_source row for exactly each SH/SZ/BJ exchange, and an initial full pending_evidence collection-status ledger; an equal input hash paired with any different canonical field raises frozen_input_hash_conflict. Each source must resolve to a verified formal snapshot visible at the freeze, have the matching exchange and nonempty audited ordinary-A extraction, and have a manifest/audit hash equal to its row. It rejects missing/duplicate exchanges, duplicate cross-exchange member IDs, or any source/member/audit mismatch. get_formal_universe_snapshot_by_input_hash returns only that immutable row. get_formal_universe_snapshot_from_task(finalizer_task_id) requires a verified formal_universe_finalize task whose canonical result_json names the snapshot ID, frozen_input_hash, universe_hash, and registry_manifest_hash, then rechecks all four against formal_universe_snapshot before returning it; it never infers a universe from a bare task ID. formal_collection_task.payload_sha256 is the SHA-256 of canonical payload JSON and is immutable after creation. formal_collection_task_dependency rejects self-edges, missing tasks, duplicate edges, and cycles. Do not copy any legacy source_snapshot into formal_source_snapshot.

The formal-task idempotency key is the canonical hash of kind, security ID, category, report period or market date, source, freeze instant, request version, and refresh_generation; prerequisite edges are not part of that key. refresh_generation is an immutable identifier derived from an authoritative discovery/index snapshot hash or explicitly persisted source revision; it is never a wall-clock retry number. For every registry-governed task, including timestamp-only statement and context collection, it is the canonical SHA-256 of the authoritative discovery/index generation, the root registry manifest hash, and the task's relevant signed role hashes. A date-only downstream task additionally includes the signed calendar selector and selected calendar manifest hash. Thus either a root/role configuration change or a calendar-binding change necessarily creates a new key. enqueue_formal_task canonicalizes the payload, stores payload_sha256, and accepts a same-key replay only when refresh_generation, canonical payload, and the full prerequisite-edge set are identical; any other same-key replay raises idempotency_payload_conflict rather than reusing an old verified task. A later verified discovery/index or configuration lineage generation produces a new task key, marks unfinished older tasks superseded through supersede_formal_tasks, and leaves verified old snapshots immutable for historical selection.

Task states are pending, leased, verified, retryable_failed, terminal_failed, and superseded. lease_next_formal_task may atomically acquire only a dependency-satisfied pending row, a retryable_failed row with non-null next_retry_at at or before now_utc, or a leased row whose lease_expires_at is at or before now_utc. It chooses candidates deterministically by ready time, created_at, and ID, then performs one compare-and-set UPDATE which sets the new worker and expiry; it never first rewrites an expired lease or retryable failure to pending. A retryable failure must carry a finite non-null next_retry_at, and terminal_failed, verified, superseded, and unexpired leased rows are never leaseable. resolve_formal_task_dependencies turns an unleased pending or retryable_failed dependent whose parent is terminal_failed or superseded into terminal_failed with prerequisite_terminal_failed; a worker that discovers that condition after an expired-lease takeover performs the same terminal transition before transport. Add tests that equal generations deduplicate while a changed discovery or root-registry generation creates a new task and preserves both audit records, that a same-key payload mismatch is rejected, that a dependent cannot lease before its calendar prerequisite verifies, that a retryable failure leases exactly once after next_retry_at, and that an expired lease can be reclaimed to parse its stored receipt without a second transport call.

- [ ] **Step 4: Run migration and regression suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store tests.test_snapshot_repository -v
~~~

Expected: PASS; v2-v4 migration and legacy job tests continue to pass.

- [ ] **Step 5: Commit the schema foundation**

~~~powershell
git add -- ashare_pipeline/state_store.py tests/test_state_store.py tests/fixtures/schema_v4.sql
git commit -m "feat: add formal evidence and universe schema"
~~~

