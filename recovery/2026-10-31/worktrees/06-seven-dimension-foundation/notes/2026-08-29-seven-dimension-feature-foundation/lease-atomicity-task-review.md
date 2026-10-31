# Lease atomicity residual task review

## Spec Compliance verdict

**Not compliant.** The new owned transaction primitive correctly uses `BEGIN IMMEDIATE` and checks the current running, unexpired owner at both transaction boundaries, and the newly fetched snapshot path plus the feature-bundle path use a shared SQLite connection for their file/DB work. However, one reachable leased statement-reuse path still performs ownerless fact/issue writes, and statement `KeyboardInterrupt`/`SystemExit` still enters the failure-transition handler. Those are direct violations of binding requirements. File rollback and the mandatory RED/test matrix also remain incomplete.

Review method: I consumed the supplied review package once, did not run Git, and did not rerun the implementer's evidenced suites. The conclusions below come from the supplied package plus direct read-only inspection of the committed files. No focused probe was needed because the failing control flow is explicit.

## Strengths

- `ashare_pipeline/state_store.py:357` introduces a small reusable ownership transaction that opens an immediate write transaction and revalidates ownership at `:362` and `:366`.
- `ashare_pipeline/snapshot_repository.py:98` and `ashare_pipeline/deep_worker.py:1230` keep their DB mutation on the same connection as file publication and perform an end check after file work. The newly fetched statement path passes `job_id`/`worker_id` at `ashare_pipeline/deep_worker.py:1826`, and the feature path does so at `:1380`.
- `ashare_pipeline/state_store.py:1051` accepts an existing connection for feature persistence, so the feature path avoids a nested write transaction. Fact and quality-issue APIs retain paired ownerless compatibility and reject half-specified ownership arguments.
- `_LeaseHeartbeat.close()` now waits for the renewal thread instead of raising a cleanup `RuntimeError`, and the feature-job handler catches `Exception`, not `BaseException`, so feature process-control exceptions reach the `finally` cleanup.
- The supplied package is limited to the seven reported tracked files and contains no schema change, migration, tracked data, scoring/readiness/pool work, or unrelated refactor.
- Named unchanged-code cross-cutting check — **lease clock/SQLite lock ordering and bounded heartbeat shutdown**: I checked `StateStore._connect/_transaction` (`ashare_pipeline/state_store.py:276` and `:285`), `renew_job_lease` (`:543`), the evidence-validation path on the injected feature connection, `_lease_next_at_logical_time`, and heartbeat lock/join ordering (`ashare_pipeline/deep_worker.py:893` and `:924`). Production renewal uses one SQLite connection with a 5-second connection/busy timeout and one `BEGIN IMMEDIATE`; the file transactions inject their existing connection rather than opening a nested writer; and worker shutdown does not join while retaining a file transaction or `_renew_lock`. I found no additional lock-order deadlock in that named risk. Under normal SQLite lock contention, shutdown can wait for the configured bounded renewal, as intended.

## Issues

### Critical

1. **The leased same-refresh statement path still writes facts and quality issues without authoritative fencing.** At `ashare_pipeline/deep_worker.py:1688`, the `same_refresh` call to `_normalize_statement_snapshot` passes only `ensure_owned`; it omits `job_id` and `worker_id`, so their defaults remain `None`. Consequently, the calls at `ashare_pipeline/deep_worker.py:1186` and `:1126` select the ownerless StateStore transactions. A worker can pass the cached event check, expire or be recovered/taken over before either write transaction, and still commit new `financial_fact` rows and (especially, because they use new UUIDs) `quality_issue` rows. The final transition may reject the stale worker, but the intermediate rows remain. This contradicts the exclusive fenced-path requirement and the implementer report's claim at `lease-atomicity-residual-report.md:35`.

   **Remediation:** pass `job_id=str(job["id"])` and `worker_id=worker` in the reuse branch, and add deterministic production-path barriers for takeover immediately before both the fact and issue mutations. Assert wrong/expired/recovered owners leave no rows, follow-up, transition, or feature effect, with a valid-owner reuse positive control.

2. **Statement process-control exceptions still emit a forbidden failure transition and can be masked.** The handler at `ashare_pipeline/deep_worker.py:1951` catches all `BaseException`, including `KeyboardInterrupt` and `SystemExit`, then invokes `fail_job_with_followups` at `:1955-1963`. With a valid lease this changes the statement job to `terminal_failed`, violating the requirement that process-control exceptions emit no retry/failure transition. If the in-flight renewal instead set `heartbeat.lost`, `final_transition()` raises `_LeaseLostError`; the nested handler catches only `ValueError` at `:1964`, so `_LeaseLostError` replaces the original process-control exception. The existing feature-only assertions at `tests/test_deep_worker.py:1169` do not cover this statement control flow.

   **Remediation:** add an `except (KeyboardInterrupt, SystemExit): raise` branch before the generic statement `BaseException` handler and let the existing `finally` close the heartbeat. Add real statement-worker tests for both exception types with renewal deterministically in flight; assert the exact original exception object/type propagates, the job remains running with no follow-up/circuit mutation, and the heartbeat thread is dead. Preserve the current ordinary-exception transition as a control.

### Important

1. **Attempt-local file cleanup does not cover transaction commit failures.** In both `ashare_pipeline/snapshot_repository.py:98-145` and `ashare_pipeline/deep_worker.py:1230-1258`, the cleanup `try/except` is inside the transaction `with`. `StateStore._transaction()` performs `connection.commit()` only after that inner suite returns (`ashare_pipeline/state_store.py:285-295`). Therefore a commit exception bypasses the cleanup handler: DB work rolls back, but a newly published final snapshot or feature file remains. The existing feature failure test injects `put_feature_bundle` failure before context exit, so it cannot detect this case.

   **Remediation:** make cleanup cover the full transaction lifecycle, including context exit/commit, while retaining serialization until cleanup is complete (for example, a transaction helper with an error callback or explicit lifecycle that cleans before rollback/lock release). Add deterministic commit-failure tests for snapshot and feature publication and verify no DB row or attempt-created final file remains, while pre-existing content survives.

2. **Snapshot cleanup can race a legitimate ownerless adopter of the immutable payload.** The compatible ownerless path publishes and verifies the file before starting its DB transaction (`ashare_pipeline/snapshot_repository.py:64-83`). An owned attempt can hold `BEGIN IMMEDIATE`, create that same final path (`:98-103`), then expire at its end check. During the file-work window, an ownerless caller can observe and adopt the identical immutable file, block while trying to record its row, and then have the owned attempt unlink the shared path at `:139-143`. Once the lock is released, the ownerless call can insert a `source_snapshot` row without re-reading the now-missing payload. `file_created` proves who first linked the path, not that no legitimate caller has subsequently adopted it.

   **Remediation:** serialize all `SnapshotRepository.persist` variants across file publication and row insertion (or add an equivalent per-target ownership/reference protocol), and revalidate the payload after any lock wait before inserting its row. Add an event-barrier regression in which an ownerless caller adopts the target while an owned attempt reaches end-of-transaction expiry; the legitimate caller must finish with a verified file/row pair.

3. **The mandatory test and genuine-RED evidence matrix is incomplete and allows the two Critical gaps.** The reported RED command at `lease-atomicity-residual-report.md:18` runs only the generic transaction primitive, an already-expired snapshot entry check, and the isolated heartbeat context. The stale-worker test at `tests/test_deep_worker.py:1107-1167` transfers ownership before `real_persist` starts, so rejection occurs at the initial snapshot owner check; the absence of facts, issues, features, and follow-ups is downstream/vacuous rather than a barrier at each mutation. The winner test at `tests/test_snapshot_repository.py:135-164` also expires before entering persistence, so its cleanup branch never runs. The only end-expiry test (`tests/test_state_store.py:1627-1684`) mutates a generic DB row, not either production file transaction. There is no same-refresh takeover test and no statement process-control test. Thus the report does not evidence the required pre-edit RED for all production paths, transaction-end file expiry, cleanup winner preservation, or both worker process-control paths.

   **Remediation:** add deterministic real-path/event-barrier tests for fresh snapshot publication, same-refresh fact and issue writes, feature file+DB work, expiry after file publication but before commit, concurrent winner preservation, and statement plus feature `KeyboardInterrupt`/`SystemExit` with renewal in flight. Demonstrate that each missing test fails against the exact base/reverted production behavior before the repair and then passes, alongside valid-owner and ordinary-exception controls.

### Minor

None.

## Assessment

**Needs fixes.** The two Critical production paths must be repaired, and the file rollback/no-clobber plus deterministic TDD gaps need coverage before this residual task can be approved.
