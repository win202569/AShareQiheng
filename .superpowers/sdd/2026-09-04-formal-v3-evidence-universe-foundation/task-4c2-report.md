# Task 4C2 report — formal bootstrap snapshot persistence

## Base, commit, and scope

- Started from reviewed commit `206afd5` in `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
- Implemented commit `c368ff1` (`feat: persist formal bootstrap snapshots`).
- The commit contains only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- No schema/migration, queue completion/supersession, leased receipt writer, universe, formal raw-store, legacy, data/SQLite, or runtime-artifact changes were made.

## Public contract and trust decisions

- `StateStore(db_path, *, formal_snapshot_store=None)` preserves legacy construction and accepts only an explicit `FormalSnapshotStore`; it never derives a raw root from the database, manifest, or caller metadata.
- All three formal APIs fail closed when the dependency is absent.
- `put_formal_snapshot(fetch, stored, verification)` calls the reviewed 4C1 validator with `expected_producing_task_id=None` before opening `BEGIN IMMEDIATE`. It persists only that immutable validated projection, plus a new canonical UUID and UTC creation time.
- One private row-to-reference path is shared by insertion re-read, manifest replay, the snapshot getter, and the receipt getter. It strictly decodes duplicate-free canonical request/verification JSON, requires the exact identity-key sets, recomputes the request fingerprint, checks lowercase SHA-256 values, re-reads raw bytes, revalidates the manifest through `FormalSnapshotStore`, and compares every persisted projection field before constructing `OfficialSnapshotRef`.
- Manifest replay returns the existing row only after revalidation and exact immutable comparison; a mismatch raises `formal_snapshot_manifest_conflict` without repair. A distinct manifest for the same bootstrap request fingerprint and refresh generation raises `formal_snapshot_lineage_conflict`.
- Bootstrap persistence always stores SQL `NULL` producer and never creates a receipt. Equal bytes in a new generation may share the `.bin` path but retain distinct manifests and formal database rows.
- `get_formal_task_snapshot_receipt` validates canonical task payload state, receipt-to-snapshot manifest, producer task, and the task/receipt/snapshot refresh generation. A receipt remains readable after a later `terminal_failed` task state.
- Formal lookup SQL never reads or converts legacy `source_snapshot` rows.

## TDD evidence

### Baseline

- Command: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store`
- Result before edits: `Ran 131 tests in 16.078s` — `OK`.

### RED

- Command: nine explicit new `StateStoreTestCase.test_formal_*` / `test_put_formal_*` tests covering configuration, bootstrap/replay, generation lineage, conflicts, rejected inputs, tampered reads, receipt lineage, and legacy isolation.
- Result: `Ran 9 tests in 0.406s` — `FAILED (errors=18)`.
- Every failure occurred at the intended missing-feature boundary: the constructor rejected `formal_snapshot_store`, and `put_formal_snapshot`, `get_formal_snapshot`, and `get_formal_task_snapshot_receipt` did not exist.

### GREEN

- First focused run after implementation: 8 of 9 tests passed; one test fixture reused the same manifest across a second raw-store root in the same database and correctly triggered a manifest conflict. The fixture was isolated to its own database; production code was unchanged for that correction.
- Fresh focused command: the same nine explicit new tests.
- Fresh focused result: `Ran 9 tests in 0.796s` — `OK`.
- Full bounded command: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store`
- Full bounded result: `Ran 140 tests in 21.490s` — `OK`.
- Fresh post-commit full bounded verification: `Ran 140 tests in 18.651s` — `OK`.
- `python -m py_compile ashare_pipeline\state_store.py tests\test_state_store.py`: exit 0.
- `git diff --check`: exit 0; Git emitted only the repository's LF-to-CRLF checkout warnings.

## Coverage and self-review

- Injection, unconfigured fail-closed behavior, valid bootstrap persistence, exact replay, SQL-null producer, and zero receipts.
- Same-byte/new-generation shared binary behavior with distinct UUID rows and manifests.
- Manifest conflict, lineage conflict, no mutation/repair, rejected verification, task-produced bootstrap rejection, fetch/manifest mismatch, and zero database mutation.
- Missing and malformed lookup IDs; noncanonical/incomplete request and verification JSON; fingerprint, metadata, creation-time, raw-byte, and manifest tamper rejection.
- Direct canonical task-produced receipt success, manifest/generation/producer/task/time mismatch rejection, and terminal-failure preservation.
- Legacy `source_snapshot` isolation.
- Self-review confirmed no `INSERT OR IGNORE`, `REPLACE`, formal-row mutation, raw-root inference, deferred API, or schema edit in the production diff.

## Limitations

- `put_formal_snapshot_for_leased_task`, formal task completion/supersession, and receipt creation remain deliberately deferred to Task 4C3.
- Task-produced receipt tests insert a canonical row/receipt fixture directly because the leased writer is not yet in scope.
- Raw files are written before this API is called; a later SQLite failure rolls back database changes but may leave those immutable raw files, as required.
- Local concurrent-filesystem TOCTOU limits remain those documented by Task 4C1; this slice delegates raw path/manifest enforcement to the reviewed validator and does not alter it.

## Review fix — complete receipt producer set

- Commit: `8aa169a` (`fix: harden formal receipt lineage`).
- The receipt getter now queries the complete `formal_source_snapshot.producing_task_id` set before interpreting absence or validating a receipt. A missing receipt is legitimate only when that set is empty; an existing receipt is valid only when the set contains exactly its referenced snapshot ID.
- Deleted-receipt orphans, extra producer rows, and any mismatching producer set raise a fail-closed `ValueError`; the getter never repairs or deletes the graph.
- RED: `Ran 2 tests in 0.134s` — `FAILED (failures=2)` because both the deleted-receipt orphan and extra-producer graph returned normally.
- Focused GREEN, including existing receipt success, mismatch, terminal-failed preservation, and legacy isolation: `Ran 5 tests in 0.603s` — `OK`.
- Full bounded suite before commit: `Ran 142 tests in 35.917s` — `OK`.
- Fresh post-commit full bounded verification: `Ran 142 tests in 29.263s` — `OK`.
- `python -m py_compile ashare_pipeline\state_store.py tests\test_state_store.py` and `git diff --check`: exit 0, with only the repository's LF-to-CRLF checkout warnings.

## Review fix 2 — consistent receipt graph reads

- Commit: `5518c28` (`fix: make formal receipt reads consistent`).
- Root cause: the receipt getter used one autocommit connection but no explicit transaction, so its receipt, producer-set, task, and snapshot queries could observe different committed database states.
- The complete getter read/validation path now runs under one explicit deferred SQLite transaction begun before the receipt query. It validates and returns only rows from that single read snapshot; the existing transaction context commits successful reads and rolls back/closes cleanly on every fail-closed error.
- Deterministic RED interleaving: start with one receipt and two producer rows; immediately after the receipt `fetchone`, a second WAL connection atomically deletes the receipt and extra producer. Before the fix, the getter combined the cached deleted receipt with the newly visible one-producer state and did not raise.
- RED result: `Ran 1 test in 0.128s` — `FAILED (failures=1)` because `ValueError` was not raised.
- Focused GREEN covering consistent snapshot, genuine absence, orphan/multiple/mismatch rejection, terminal-failed preservation, and legacy isolation: `Ran 6 tests in 0.639s` — `OK`.
- Full bounded suite before commit: `Ran 143 tests in 15.509s` — `OK`.
- Fresh post-commit full bounded verification: `Ran 143 tests in 8.581s` — `OK`.
- `python -m py_compile ashare_pipeline\state_store.py tests\test_state_store.py` and `git diff --check`: exit 0, with only the repository's LF-to-CRLF checkout warnings.
