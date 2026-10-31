# Lease atomicity residual repair report

## Status and authority

- Authorized residual task completed on branch `feature/seven-dimension-foundation`.
- Exact pre-edit base: `3ce5a903d9eafb2573c493960c0d8e180f33834e`.
- Commit: `c76da969ee3b7aed9eee2d45a32b273f02ba42bf` (`fix: fence leased durable writes atomically`).
- No network, migration, runtime/tracked database or data mutation, operational `120/114` acceptance, formal scoring, seven-dimension readiness, or stock-pool work was performed.

## RED evidence on untouched production

Tests were added first with `apply_patch`, before any production edit. The exact focused command was:

```powershell
$env:TEMP='D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation\.test-tmp\red'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_owned_job_transaction_fences_wrong_expired_and_valid_owners tests.test_snapshot_repository.SnapshotRepositoryTestCase.test_owned_persist_rejects_stale_owner_and_preserves_immutable_winner tests.test_deep_worker.DeepWorkerTestCase.test_inflight_heartbeat_shutdown_preserves_process_control_exception
```

Expected RED was observed: 3 tests, 4 errors.

- `StateStore` had no `owned_job_transaction` (`AttributeError`).
- `SnapshotRepository.persist()` rejected `job_id`/`worker_id` (`TypeError`).
- Both `KeyboardInterrupt` and `SystemExit` were replaced by `RuntimeError: lease heartbeat thread did not stop` while renewal was in flight.

The final versions of the tests additionally verify commit-boundary expiry rollback and a real statement-worker barrier: worker A reaches persistence after its cached pre-action check, the test expires/recovers the real job and worker B acquires it, then worker A is released and cannot commit an AkShare snapshot/file, facts, issues, feature rows/file, follow-up, or success transition. Event synchronization is used; no arbitrary sleep is used.

## Implementation

- Added a `BEGIN IMMEDIATE` owned-job transaction primitive that validates `job_id`, `worker_id`, `status='running'`, and an unexpired lease both before mutation and immediately before commit.
- Added owner fencing to leased financial-fact and quality-issue writes while preserving compatible ownerless callers.
- Added owner-aware snapshot persistence that spans immutable file publication and `source_snapshot` insertion in one owned transaction, revalidates before commit, and removes only a file created by the failed attempt.
- Made feature file publication and `feature_set`/`feature_value` insertion one owned transaction with end-of-transaction revalidation and attempt-local file cleanup.
- Routed all leased deep-worker statement and feature mutation paths through the owner-fenced variants.
- Changed heartbeat shutdown to wait for the bounded in-flight SQLite renewal, ensuring the renewal thread is dead and preserving active process-control exceptions.
- Updated `progress.md` with exact verification evidence while keeping all operational and readiness gates closed.

## Changed tracked files

- `ashare_pipeline/deep_worker.py`
- `ashare_pipeline/snapshot_repository.py`
- `ashare_pipeline/state_store.py`
- `tests/test_deep_worker.py`
- `tests/test_snapshot_repository.py`
- `tests/test_state_store.py`
- `progress.md`

## GREEN verification

- Initial RED set after implementation: 3/3 passed in 0.110s.
- Final focused set, including ordinary-exception retry positive control: 5/5 passed in 0.260s.
- Affected modules (`test_state_store`, `test_snapshot_repository`, `test_deep_worker`): 172/172 passed in 36.494s.
- Fresh full offline suite with an existing worktree-local temp directory: 411/411 passed in 99.662s.
- Path-specific staging contained exactly the seven tracked files listed above.
- `git diff --cached --check`: passed.
- Final full offline suite on the staged tree: 411/411 passed in 112.409s.
- Post-commit `git diff --check HEAD^ HEAD`: passed.

One earlier full attempt reached all 411 tests but had one environment-only error because the configured D-drive temp directory did not yet exist, so Python `tempfile` fell back to C: and an existing relative-root test rejected a cross-drive `relpath`. The directory was created explicitly before the recorded successful full and staged-full runs; no production change was made for that host condition.

## Self-review

- Every leased durable mutation now performs its authoritative ownership query on the same SQLite connection and inside the same immediate write transaction as the mutation.
- Snapshot and feature transactions revalidate after potentially long file work and before commit.
- Cleanup is gated by the immutable writer's `created` result and executes while the write transaction still excludes a competing database winner; pre-existing immutable winners are left intact.
- Existing ownerless repository/store APIs remain compatible, and affected-module regression covers their idempotent/no-clobber behavior.
- Final owned transitions remain unchanged and fenced; stale-owner failure cannot emit retry/failure transitions because those transitions independently reject the stale owner.
- Heartbeat close has no unbounded external dependency: production renewal remains bounded by the StateStore SQLite timeout.

## Concerns

- No known correctness concern remains in the authorized scope.
- Heartbeat shutdown can now wait up to the configured SQLite timeout for an already-running renewal; this is intentional and required to guarantee no renewal thread survives worker return.
- Formal scoring, seven-dimension readiness, stock pools, network smoke, and operational acceptance remain explicitly unexecuted and closed.

## Fix Round 1 — independent review findings

Base for this round: `c76da969ee3b7aed9eee2d45a32b273f02ba42bf`.

### RED before further production edits

The missing deterministic tests were added first and run against the unchanged Fix Round 1 base with worktree-local `TEMP`, `TMP`, and `TMPDIR`:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_same_refresh_takeover_before_fact_write_is_fenced tests.test_deep_worker.DeepWorkerTestCase.test_same_refresh_takeover_before_issue_write_is_fenced tests.test_deep_worker.DeepWorkerTestCase.test_statement_keyboard_interrupt_with_inflight_renewal_is_unchanged tests.test_deep_worker.DeepWorkerTestCase.test_statement_system_exit_with_inflight_renewal_is_unchanged tests.test_deep_worker.DeepWorkerTestCase.test_feature_commit_failure_cleans_only_attempt_created_file tests.test_snapshot_repository.SnapshotRepositoryTestCase.test_owned_snapshot_commit_failure_removes_attempt_file_and_row tests.test_snapshot_repository.SnapshotRepositoryTestCase.test_ownerless_winner_republishes_after_owned_end_expiry_cleanup
```

Observed genuine RED: 7 tests, 4 failures and 3 errors in 0.815s.

- Finding 1: the same-refresh fact barrier left 49 `financial_fact` rows; the issue barrier left 1 `quality_issue` row after worker B recovered/acquired the job.
- Finding 2: both statement process-control cases propagated `_LeaseLostError` caused by the in-flight renewal instead of the exact original `KeyboardInterrupt`/`SystemExit`.
- Finding 3: forced SQLite commit failure left both the fresh snapshot final file and fresh feature final file while their DB rows rolled back.
- Finding 4: the ownerless winner inserted a snapshot row after waiting for the owned transaction, but the stale owned cleanup had deleted its adopted immutable file; `read_verified` failed with `FileNotFoundError`.
- Finding 5: those real-path failures established the previously missing statement reuse, statement process-control, commit-exit cleanup, and concurrent-winner evidence. Additional feature end-expiry, feature in-flight process-control, valid same-refresh reuse, and ordinary-exception controls were retained/added for the final matrix.

### Fixes

- Passed `job_id` and `worker_id` through the same-refresh normalization call so facts and issues exclusively use owner-fenced StateStore APIs.
- Added a statement `except (KeyboardInterrupt, SystemExit): raise` branch before the generic `BaseException` failure-transition handler.
- Extended the StateStore transaction lifecycle with an `on_error` callback invoked for body, end-owner-check, and commit failures before rollback releases the SQLite writer lock; cleanup failures cannot replace the original transaction error.
- Routed snapshot and feature attempt cleanup through that transaction lifecycle. Cleanup removes only an attempt-created file and preserves pre-existing committed DB winners/content.
- Kept compatible concurrent ownerless snapshot publication, then reacquired/re-published/reverified the immutable target after any SQLite writer-lock wait and before inserting its row. Thus stale cleanup may remove the first adopted link, but the legitimate waiter deterministically restores and verifies it while holding the write transaction.

### GREEN evidence

- Exact former RED set: 7/7 passed in 0.707s.
- Final focused matrix, including feature in-flight process control, end-expiry, valid reuse, and ordinary exception controls: 13/13 passed in 1.460s.
- Affected modules: StateStore 74/74, SnapshotRepository 21/21, DeepWorker 86/86; 181/181 total.
- Fresh full offline suite before staging: 420/420 passed in 40.749s.
- Final staged-tree full offline suite: 420/420 passed in 41.607s.
- Path-specific staging contained exactly the six tracked files listed for this round; `git diff --cached --check` passed.
- Fix Round 1 commit: `1a299f51e87de9acdcea7430b765a0ec31096184` (`fix: close lease atomicity review gaps`).
- Post-commit `git diff --check HEAD^ HEAD`: passed.

### Review-finding mapping and concerns

1. Same-refresh ownerless facts/issues: fixed and covered by separate event-barrier takeover tests.
2. Statement process-control masking/transition: fixed for both exact exception objects with renewal in flight; job/follow-up state remains unchanged and heartbeat thread is dead. Ordinary statement failure remains terminal as a positive control.
3. Context-exit/commit cleanup: fixed for fresh snapshot and feature files; pre-existing feature content survives.
4. Ownerless adopter race: fixed by post-lock re-publication and verification; the concurrent winner finishes with exactly one verified row/file pair.
5. Matrix completeness: real production paths now cover fresh/reused statements, fact/issue mutations, snapshot/feature file+DB transactions, commit and end-expiry rollback, winner preservation, statement/feature process control, valid-owner reuse, and ordinary failures without arbitrary sleeps.

No known correctness concern remains within this review round. The equivalent ownerless target protocol performs a second immutable write/verification after acquiring the SQLite lock; this is intentional and bounded local I/O required to close the adoption race without weakening concurrent no-clobber behavior.

## Fix Round 2 — failed-BEGIN cleanup race

Base for this round: `1a299f51e87de9acdcea7430b765a0ec31096184`.

### RED before production edit

An event-gated real `SnapshotRepository.persist` test was added before changing production. Caller A created and verified the immutable file, caller B adopted it, acquired the real SQLite writer lock, reverified and inserted its row, and paused before commit. Caller A then used a thread-specific `PRAGMA busy_timeout = 0` connection so its real `BEGIN IMMEDIATE` failed deterministically; only after A returned was B allowed to commit. No arbitrary sleep was used.

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_snapshot_repository.SnapshotRepositoryTestCase.test_failed_begin_cannot_delete_uncommitted_ownerless_winner_file
```

Observed RED: 1 test, 1 error in 0.075s. Caller A's failed `BEGIN IMMEDIATE` invoked snapshot cleanup, could not see B's uncommitted row, unlinked the shared payload, and B committed a row whose `read_verified` raised `FileNotFoundError`.

### Minimal fix and finding mapping

- `StateStore._transaction` now tracks whether `BEGIN` succeeded.
- `on_error` and rollback run only when that transaction actually began and therefore owns the transaction lifecycle required for safe pre-rollback cleanup.
- A lock-acquisition error propagates unchanged without touching the ownerless prepublished immutable file.
- Existing post-BEGIN cleanup order remains unchanged for body failures, owned end-expiry, and commit failures; cleanup-error chaining still preserves the original transaction exception.

This directly closes the single Important Fix Round 2 finding without changing snapshot target semantics, schemas, or unrelated worker behavior.

### GREEN evidence

- Exact former RED test: 1/1 passed in 0.042s.
- Focused failed-BEGIN plus post-BEGIN cleanup regression: 6/6 passed in 0.325s.
- Affected StateStore/SnapshotRepository/DeepWorker modules: 182/182 passed in 16.508s.
- Fresh full offline suite before staging: 421/421 passed in 45.298s.
- Final staged-tree full offline suite: 421/421 passed in 58.086s.
- Path-specific staging contained exactly `ashare_pipeline/state_store.py`, `tests/test_snapshot_repository.py`, and `progress.md`; `git diff --cached --check` passed.
- Fix Round 2 commit: `4cd2acc0fe777e7e3c3b96d9de8a2752f7ba1f8e` (`fix: guard cleanup after transaction begin`).
- Post-commit `git diff --check HEAD^ HEAD`: passed.

No known scoped concern remains. A failed `BEGIN` may leave caller A's prepublished immutable file without A's row, but this is intentional: immutable orphan preservation is safer than deleting content adopted by an uncommitted legitimate writer, and subsequent persisted callers reverify/reuse it deterministically.

## Final whole-branch fix wave — post-lock authorization time

Base for this wave: `4cd2acc0fe777e7e3c3b96d9de8a2752f7ba1f8e`.

### RED before production edit

Three deterministic tests were added before changing production. They use real second-connection `BEGIN IMMEDIATE` contention, events for lock-attempt and clock boundaries, and a controlled `_utc_now`; no arbitrary sleep is used.

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_renew_samples_default_time_after_writer_lock_wait tests.test_state_store.StateStoreTestCase.test_final_transitions_sample_time_after_writer_lock_wait tests.test_state_store.StateStoreTestCase.test_final_transitions_resample_after_followup_preparation
```

Observed genuine RED on unchanged `4cd2acc`: 3 tests, 5 failures in 0.153s.

- Renew sampled `_utc_now` before the blocked real `BEGIN IMMEDIATE` (`[True]` instead of `[False]`) and renewed after the controlled clock crossed expiry.
- Complete and fail each sampled before the writer-lock wait and performed their stale terminal transition after expiry.
- Complete and fail each reused the initial authorization time after follow-up preparation, so the boundary test observed no rejection and a committed terminal transition/follow-up.

### Minimal fix and finding mapping

- Default `renew_job_lease` now enters the immediate transaction before calling `_utc_iso(None)` and calculating the new expiry. Explicit `now_utc` remains a deterministic override and is interpreted inside the same transaction.
- `complete_job_with_followups` and `fail_job_with_followups` now sample their initial owner-check time after acquiring the writer transaction.
- Both terminal methods re-sample immediately before their guarded `UPDATE`; if the lease expires during follow-up preparation, the zero-row update raises and the transaction rolls back every inserted follow-up.
- No lease-next logical-time, heartbeat, schema, retry, or unrelated behavior changed.

### GREEN evidence

- Exact former RED set: 3/3 passed in 0.164s.
- Focused lease matrix: 13/13 passed in 1.053s.
- Affected StateStore/DeepWorker modules: 163/163 passed in 15.292s.
- Final staged-tree full offline suite with worktree-local `TEMP`/`TMP`/`TMPDIR`: 424/424 passed in 44.732s.
- Pre-stage scoped `git diff --check`: passed; path-specific staging contains only `ashare_pipeline/state_store.py`, `tests/test_state_store.py`, and `progress.md`.
- Final-wave commit: `1f155ef1a037079939c9a2c7fb1d093bf0b071e9` (`fix: sample lease time inside transaction`).
- Post-commit `git diff --check HEAD^ HEAD`: passed; the three tracked paths and index are clean.

No known scoped correctness concern remains. The terminal transition intentionally uses a later timestamp than follow-up creation because they bracket potentially non-trivial follow-up preparation; both remain atomic in one SQLite transaction.

## Authorized terminal-serialization micro-fix

Base for this micro-fix: `1f155ef1a037079939c9a2c7fb1d093bf0b071e9`.

### RED before production edit

Two deterministic real-StateStore tests were added first. Each patches `_json` only to place an event barrier when it receives the exact result/error object, delegates the actual serialization to the real helper, and controls `_utc_now` at T9/T11 for a T10 lease. The initial in-transaction owner check sees T9; the test advances to T11 while exact payload serialization is blocked. No arbitrary sleep is used.

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_complete_resamples_after_result_serialization tests.test_state_store.StateStoreTestCase.test_fail_resamples_after_error_serialization
```

Observed genuine RED on unchanged `1f155ef`: 2 tests, 2 failures in 0.042s. Both complete and fail committed after the controlled clock crossed expiry (`errors=[]`) rather than rejecting, keeping the job running, and rolling back the inserted follow-up.

### Minimal fix

- Complete now computes `result_json = _json(result)` before its final `_utc_now()` sample.
- Fail now computes `error_json = _json(error)` before its final `_utc_now()` sample.
- Each guarded UPDATE uses the precomputed string, leaving no non-trivial preparation between the final authorization sample and `connection.execute`.
- Renewal semantics, initial post-lock owner checks, follow-up transactionality, heartbeat, schemas, retry logic, and all unrelated paths are untouched.

### GREEN evidence

- Exact former RED set: 2/2 passed in 0.042s.
- Focused lease matrix: 15/15 passed in 1.072s.
- Affected StateStore/DeepWorker modules: 165/165 passed in 15.201s.
- Final staged-tree full offline suite with worktree-local `TEMP`/`TMP`/`TMPDIR`: 426/426 passed in 41.499s.
- Pre-stage scoped `git diff --check`: passed; path-specific staging is limited to `ashare_pipeline/state_store.py`, `tests/test_state_store.py`, and `progress.md`.
- Micro-fix commit: `29bac16fc1ee0f690a4ca8eeec6ff213c69bda69` (`fix: fence terminal serialization expiry`).
- Post-commit `git diff --check HEAD^ HEAD`: passed; the three tracked paths and index are clean.

No known scoped correctness concern remains. Serialization remains inside the same immediate transaction, so a serialization error still rolls back inserted follow-ups before any terminal update.
