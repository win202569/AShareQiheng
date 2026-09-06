# Task 4C3 report — atomic leased-task snapshot receipts

## Base, commit, and scope

- Started from reviewed commit `5518c28` in `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
- Implemented commit `d4ce87a` (`feat: persist formal task snapshot receipts`).
- The commit contains only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- Implemented only `put_formal_snapshot_for_leased_task` plus a private extraction of the already-reviewed receipt getter logic so writer replay and public reads validate the same graph.
- No schema/migration, formal completion/supersession, universe, FormalSnapshotStore, legacy queue/snapshot, data, or SQLite artifact changes were made.

## Contract delivered

- The writer fails closed without an injected `FormalSnapshotStore`, validates exact nonempty task/worker IDs, and obtains every persisted field from `validate_stored_snapshot(..., expected_producing_task_id=task_id)`.
- It acquires `BEGIN IMMEDIATE`, samples current UTC after the writer lock, validates the canonical task payload, and requires one of the exact source-fetch kinds: `formal_statement`, `formal_context`, or `formal_universe_source`.
- The task must be `leased` by the supplied worker with expiry strictly later than the sampled time. Task, fetch, and validated manifest generations must match. A final ownership/kind/expiry/generation query runs immediately before mutation.
- Bootstrap and task-produced lineages remain distinct. Manifest and request/generation/producer lineage are immutable, and exact replay returns the fully revalidated existing `OfficialSnapshotRef`.
- Replacement evidence, a second receipt, cross-task snapshot attachment, producer mismatch, generation mismatch, and corrupted existing lineage fail closed without repair.
- A new formal snapshot row and its one task receipt are inserted in the same transaction. A forced late receipt constraint failure rolls the snapshot row back as well.
- Receipt reads still validate the complete task/receipt/producer-set/snapshot/raw-manifest graph in one explicit SQLite read snapshot and remain valid after later terminal task failure.
- Legacy `source_snapshot` and existing bootstrap writer semantics are unchanged.

## TDD evidence

### RED

Before production edits, six focused tests were added and run for configuration, atomic success/replay/failure durability, exact allowed source kinds, lease/evidence rejection with zero rows, replacement/cross-task conflicts, and late receipt-insert rollback.

Command:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store.StateStoreTestCase.test_formal_snapshot_store_injection_is_optional_but_formal_apis_fail_closed tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_is_atomic_replayable_and_durable_after_failure tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_accepts_only_source_fetch_kinds tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_rejects_fencing_and_evidence_mismatches_without_rows tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_rejects_replacement_and_cross_task_attachment tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_rolls_back_snapshot_when_receipt_insert_fails
```

Result: `Ran 6 tests in 0.700s` — `FAILED (errors=16)`. Every error was the intended missing-feature failure: `StateStore` had no `put_formal_snapshot_for_leased_task` method.

### GREEN

- Same six focused tests after minimal implementation: `Ran 6 tests in 0.826s` — `OK`.
- Formal snapshot-focused group: `Ran 9 tests in 1.220s` — `OK`.
- Receipt integrity/consistent-read group: `Ran 5 tests in 0.759s` — `OK`.
- Complete bounded StateStore suite:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store
```

Result: `Ran 148 tests in 9.764s` — `OK`.

- `python -m py_compile ashare_pipeline\state_store.py tests\test_state_store.py`: exit 0.
- `git diff --check`: exit 0; Git emitted only the repository's LF-to-CRLF checkout warnings.

## Coverage highlights

- Atomic successful snapshot plus receipt and exact immutable replay.
- Distinct bootstrap versus task-produced manifests sharing the same content-addressed binary.
- Nonempty exact task/worker ID validation.
- Pending, verified, wrong-worker, exactly expired, taken-over, wrong-generation, non-source-kind, mismatched-producer, and substituted-raw rejection with zero formal snapshot/receipt rows.
- All three allowed source-fetch kinds.
- Second snapshot/receipt replacement conflict and cross-task attachment rejection.
- Forced receipt-trigger failure after snapshot insertion, proving both database mutations roll back together.
- Receipt getter survival after terminal failure.
- Receipt-row and snapshot-row manifest/generation/producer tamper rejection, including the previously reviewed orphan, multiple-producer, and fractured-read regressions.
- Existing bootstrap and legacy isolation tests remain green in the full suite.

## Limitations and deferred work

- Formal task completion, supersession, universe/status persistence, schema/migration changes, and repository integration remain deliberately deferred.
- Raw files are written before the StateStore call. A rejected transaction may therefore leave immutable unreferenced raw evidence, while database snapshot/receipt rows remain atomic as required.
- The fixed V5 worker identity limitation remains: callers must use unique worker IDs per lease-owning process/incarnation because the schema has no lease token.
- No unbounded project E2E suite was run; the binding brief requires only focused and complete bounded `tests.test_state_store` verification.

## Self-review

- Verified the staged commit paths were exactly `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- Reviewed trust projection, transaction ordering, fresh-time sampling, strict expiry boundary, generation/source-kind/owner fencing, exact replay, conflict paths, rollback behavior, receipt graph consistency, bootstrap separation, and legacy isolation.
- Confirmed no `INSERT OR IGNORE`, `REPLACE`, update/delete repair, task state transition, or legacy table access was added to the formal writer.
