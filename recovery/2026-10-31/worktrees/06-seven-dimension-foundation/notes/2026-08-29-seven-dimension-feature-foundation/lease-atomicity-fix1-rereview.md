# Lease atomicity residual — Fix Round 1 scoped re-review

Review range: `c76da969ee3b7aed9eee2d45a32b273f02ba42bf..1a299f51e87de9acdcea7430b765a0ec31096184`

## Per-finding verdicts

1. **ADDRESSED — same-refresh fact and issue writes now retain the leased owner.** The same-refresh branch passes both `job_id` and `worker_id` into normalization at `ashare_pipeline/deep_worker.py:1685-1700`. Normalization forwards them to `insert_financial_facts` at `ashare_pipeline/deep_worker.py:1184-1188` and to every issue write through `ashare_pipeline/deep_worker.py:1189-1198` and `ashare_pipeline/deep_worker.py:1123-1138`. Those StateStore APIs select `owned_job_transaction` when the pair is present at `ashare_pipeline/state_store.py:809-837` and `ashare_pipeline/state_store.py:1186-1220`. The two event-gated same-refresh tests at `tests/test_deep_worker.py:1182-1287` reach the real fact/issue APIs, perform real expiry/recovery/takeover before releasing the blocked call, and assert no fact, issue, or follow-up survives. The barriers are non-vacuous.

2. **ADDRESSED — statement process-control exceptions bypass the generic failure transition and survive heartbeat shutdown.** The statement loop now catches `KeyboardInterrupt` and `SystemExit` at `ashare_pipeline/deep_worker.py:1951-1954`, before the generic `BaseException` transition handler at `ashare_pipeline/deep_worker.py:1955-1970`; shutdown still runs in `finally` at `ashare_pipeline/deep_worker.py:1971-1972`. `_LeaseHeartbeat.close` waits for the renewal thread at `ashare_pipeline/deep_worker.py:924-931` without translating renewal loss into `_LeaseLostError`. The statement tests at `tests/test_deep_worker.py:1406-1491` wait until a renewal is genuinely in flight, raise a specific exception instance from the statement source, assert that exact object propagates, assert that the job/follow-up state is unchanged, and assert that the renewal thread is dead. The ordinary-error control at `tests/test_deep_worker.py:2209-2228` confirms the generic terminal transition remains active for ordinary statement failures.

3. **ADDRESSED — snapshot and feature cleanup now includes transaction body, end-owner-check, and commit failures.** `StateStore._transaction` invokes `on_error` before rollback at `ashare_pipeline/state_store.py:285-303`, and `owned_job_transaction` forwards the callback while retaining both ownership checks at `ashare_pipeline/state_store.py:367-381`. A callback failure does not replace the transaction exception: after rollback, line 301 raises the original `error` and chains the cleanup failure as its cause. Snapshot cleanup is registered at `ashare_pipeline/snapshot_repository.py:77-101`, and feature cleanup is registered at `ashare_pipeline/deep_worker.py:1232-1256`. The real repository/store commit-failure controls at `tests/test_snapshot_repository.py:178-198` and `tests/test_deep_worker.py:2092-2145` verify rollback plus attempt-file removal and pre-existing-file preservation; the feature end-expiry barrier at `tests/test_deep_worker.py:2147-2207` verifies the end check removes the fresh file and both DB tables' rows. The pre-`BEGIN` callback flaw reported below is new breakage, not a residual failure of these covered post-`BEGIN` paths.

4. **ADDRESSED — the originally reported owned-loser/ownerless-waiter adoption race is repaired.** An ownerless caller publishes and verifies once before waiting for the writer lock at `ashare_pipeline/snapshot_repository.py:92-97`, then writes/re-publishes and re-verifies again after acquiring the transaction at `ashare_pipeline/snapshot_repository.py:102-106`, before recording and rereading its row at `ashare_pipeline/snapshot_repository.py:108-126`. Because stale owned cleanup runs before rollback while its acquired writer lock is still held, a normally waiting ownerless caller cannot insert between cleanup and rollback and will restore the immutable payload after it acquires the lock. `tests/test_snapshot_repository.py:200-296` coordinates the owned end-expiry and waiting ownerless caller, then proves exactly one created, readable row/file winner. Existing same-content reuse and concurrent first-winner behavior remain exercised at `tests/test_snapshot_repository.py:133-145` and `tests/test_snapshot_repository.py:298-351`. The separate failed-`BEGIN` case below falls outside that acquired-lock protocol and is new breakage introduced by the callback refactor.

5. **ADDRESSED — the regression matrix now has non-vacuous real-path coverage for the five previously missing areas.** Same-refresh fact/issue takeover is covered at `tests/test_deep_worker.py:1182-1287`; statement process control with an in-flight renewal at `tests/test_deep_worker.py:1406-1491`; fresh snapshot commit cleanup at `tests/test_snapshot_repository.py:178-198`; snapshot end-expiry plus concurrent-winner preservation at `tests/test_snapshot_repository.py:200-296`; and fresh/pre-existing feature commit cleanup plus fresh feature end-expiry at `tests/test_deep_worker.py:2092-2207`. Valid same-refresh reuse remains covered at `tests/test_deep_worker.py:1599-1617`, while ordinary feature and statement failures are positive controls at `tests/test_deep_worker.py:1493-1524` and `tests/test_deep_worker.py:2209-2228`. The new synchronization uses events/transaction contention and asserts that the intended production points were reached; it does not rely on arbitrary sleeps.

## New breakage

### Important — `on_error` may delete an adopted snapshot after `BEGIN IMMEDIATE` fails without acquiring the writer lock

`StateStore._transaction` places `BEGIN IMMEDIATE` inside the same `try` whose `except` unconditionally invokes `on_error` (`ashare_pipeline/state_store.py:290-302`). Therefore the callback runs not only after body/end-check/commit failures, when the transaction owns the writer lock, but also when `BEGIN IMMEDIATE` itself times out and never acquires that lock. The configured SQLite/busy timeout is five seconds (`ashare_pipeline/state_store.py:276-281`).

That distinction is unsafe for the newly reworked ownerless snapshot path. It may create the immutable file before attempting the transaction (`ashare_pipeline/snapshot_repository.py:92-97`). On a failed `BEGIN`, its callback sees `file_created=True` and `database_created=None`, performs a non-exclusive row lookup, and unlinks the target when no committed row is currently visible (`ashare_pipeline/snapshot_repository.py:77-90`).

The exact two-caller interleaving is:

1. Ownerless caller A performs its first `snapshot_store.write`, creates and verifies the final immutable payload, and pauses before entering `_transaction`.
2. Legitimate caller B sees/adopts A's payload, acquires `BEGIN IMMEDIATE`, performs its required post-lock write/reverification, inserts the matching `source_snapshot` row, and pauses before commit while still holding the writer lock.
3. A attempts `BEGIN IMMEDIATE`, exhausts the configured busy timeout, and enters `_transaction`'s unconditional error callback even though A never acquired the writer lock.
4. A's cleanup `SELECT` cannot see B's uncommitted row, so A unlinks the payload.
5. B resumes and commits successfully, leaving a durable `source_snapshot` row whose `payload_path` is missing.

The winner test at `tests/test_snapshot_repository.py:200-296` covers a waiter that eventually acquires the lock after stale owned rollback; it never drives the wait through a failed `BEGIN`, so it does not close this schedule.

**Minimal fix:** track successful transaction start separately. Invoke `on_error` only after `BEGIN` has succeeded, and only rollback that begun transaction. For the ownerless prepublication case, preserve the immutable payload when `BEGIN` itself fails, or perform any attempted deletion only inside a newly and successfully acquired writer transaction. This keeps the current pre-rollback callback ordering for body, end-check, and commit errors.

**Required RED:** add an event-gated real `SnapshotRepository.persist` concurrency test implementing the five steps above. Caller A must be proven to create the file before caller B adopts it; B must be proven to insert its row while holding the real SQLite writer lock; A's real `BEGIN IMMEDIATE` must then be forced to fail deterministically (for example, a thread-specific test connection with zero/short busy timeout, not an arbitrary sleep); only after A returns may B commit. On the current fix the test must show the missing payload behind B's committed row. GREEN must prove B returns one readable verified row/file pair and A's lock-acquisition error cannot delete it.

No new Critical or Minor finding was identified.

## Out-of-scope observations

None.

## Final verdict

**CHANGES REQUESTED.** All five prior findings are addressed, but Fix Round 1 introduces the Important failed-`BEGIN` cleanup race above. The package should not be accepted until ownerless snapshot cleanup is safe when writer-lock acquisition itself fails and that case has a non-vacuous concurrent-winner regression test.
