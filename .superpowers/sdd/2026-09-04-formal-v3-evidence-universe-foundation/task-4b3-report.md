# Task 4B3 report — formal completion and generation supersession

## Base, commit, and scope

- Started from reviewed commit `d4ce87a` in `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
- Implemented commit `f2a5199` (`feat: complete formal tasks safely`).
- The commit contains only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- Added only the public `complete_formal_task` and `supersede_formal_tasks` APIs. No schema/migration, FormalSnapshotStore, universe/status, legacy queue/snapshot, data, or SQLite artifact changes were made.

## Contract delivered

- `complete_formal_task` requires exact nonempty task/worker strings and a finite canonical result mapping snapshotted before the writer transaction.
- Completion uses `BEGIN IMMEDIATE`, validates the canonical task row, requires the named live lease owner, and re-samples UTC immediately before the final compare-and-set mutation. The final CAS repeats task ID, leased state, owner, strict expiry, kind, generation, and immutable payload identity.
- Successful non-source completion stores canonical result JSON, moves to `verified`, clears error/retry/lease fields, and leaves payload, prerequisites, and audit rows intact.
- The three source-fetch kinds (`formal_statement`, `formal_context`, `formal_universe_source`) must have exactly one fully revalidated 4C receipt/source/task/raw-manifest graph in the same transaction. Missing, orphaned, extra-producer, mismatched, or tampered graphs fail closed. The final source CAS repeats the exact receipt/producer/generation predicates.
- Existing receipts remain immutable through failure/supersession transitions. Legacy `source_snapshot` rows are never consulted.
- `formal_universe_finalize` always fails closed in this slice. Task 4D must provide and validate the matching persisted universe proof before finalizer completion can be enabled.
- `supersede_formal_tasks` accepts only a nonempty finite canonical mapping scope and nonempty retained generation. It uses exact canonical top-level subset equality and direct generation inequality, never lexical generation ordering.
- In one writer transaction it changes only matching old-generation `pending`, `leased`, and `retryable_failed` tasks to `superseded`; clears lease/retry fields; preserves payload/result/error/dependencies/receipts; leaves current-generation, final, already-superseded, and other-scope rows unchanged; and immediately fences old owners.
- Per-row supersession CAS repeats status, generation, and immutable canonical payload/hash. Any direct candidate change aborts and rolls back the transaction.

## TDD evidence

### Baseline

Before edits:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store
```

Result: `Ran 148 tests in 20.728s` — `OK`.

### RED

Nine focused completion/supersession tests were added before either production API existed. They cover canonical results, input validation, ownership/expiry/takeover/final fencing, non-source success, all three source kinds, missing and invalid receipt graphs, pre-4D finalizer failure, completion rollback, exact scope/generation selection, audit preservation, owner fencing, legacy isolation, and direct supersession CAS rollback.

Focused RED result: `Ran 9 tests in 0.423s` — `FAILED (errors=24)`. Every error was the intended missing-feature failure: `StateStore` had no `complete_formal_task` or `supersede_formal_tasks` method.

After the first minimal GREEN, self-review identified a lease-expiry boundary during receipt validation. A tenth focused test was added before the fix and produced the intended RED: `Ran 1 test in 0.061s` — `FAILED (failures=1)` because completion incorrectly succeeded after the lease expired during receipt validation.

### GREEN

- Receipt-validation expiry regression after moving the fresh time sample to the final CAS: `Ran 1 test in 0.061s` — `OK`.
- Complete focused Task 4B3 group: `Ran 10 tests in 0.756s` — `OK`.
- Complete bounded StateStore suite: `Ran 158 tests in 23.488s` — `OK`.
- `python -m py_compile ashare_pipeline\state_store.py tests\test_state_store.py`: exit 0.
- `git diff --check`: exit 0; Git emitted only the repository's LF-to-CRLF checkout warnings.

## Coverage highlights

- Canonical result JSON and caller-mutation isolation; nonmapping/NaN/infinity rejection.
- Missing, wrong, exactly expired, taken-over, already-final, and superseded lease-owner fencing.
- Fresh-time sampling after result serialization and again after raw receipt validation.
- Successful `formal_feature_build` completion without a receipt.
- Exact valid receipts for every source-fetch kind; missing/mismatched/tampered receipt graphs fail without task mutation.
- Receipt preservation after later failure (existing 4C regression) and after supersession.
- Forced SQLite completion failure rolls the transition back.
- Legacy snapshot IDs cannot satisfy the formal receipt gate.
- Exact top-level scope matching, opaque retained-generation inequality on both lexical sides, terminal/current/other-scope preservation, and idempotent repeat supersession.
- Direct in-transaction candidate mutation before supersession CAS triggers full rollback.

## Deferred boundary

Task 4D's verified-universe persistence and proof validator remain pending. Until that validator exists and explicitly supplies matching proof, `formal_universe_finalize` cannot transition to `verified` through `complete_formal_task`.

## Self-review

- Re-read the binding Task 4B3 brief, parent Task 4B brief, V5 plan/spec, ledger rulings, approved 4B queue code/tests, and approved 4C receipt code/tests before implementation.
- Reviewed final owner/expiry sampling and CAS predicates, consistent receipt validation, canonical JSON/type equality, scope/generation selection, preservation rules, rollback paths, legacy isolation, and the pre-4D finalizer fence.
- Verified the commit contains exactly the two scoped files and no schema, migration, FormalSnapshotStore, universe, legacy, data, or runtime artifact changes.
