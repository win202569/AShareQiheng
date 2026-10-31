# Scoped Fix Round 2 re-review

## Scope

- Fix base: `1a299f51e87de9acdcea7430b765a0ec31096184`
- Reviewed head: `4cd2acc0fe777e7e3c3b96d9de8a2752f7ba1f8e`
- Reviewed only the supplied three-file package for the single failed-`BEGIN` cleanup finding.
- Per instruction, the supplied diff was read once; Git and the reported test suites were not rerun. No focused probe was needed because the code and deterministic test resolved the only concrete doubt.

## Verdict

**ADDRESSED**

The transaction now distinguishes a connection that has merely been opened from one whose `BEGIN` completed. A failed `BEGIN IMMEDIATE` therefore re-raises without invoking attempt cleanup or rollback, while the connection is still closed. All post-BEGIN failure paths retain callback-before-rollback ordering, including cleanup-error chaining that keeps the original transaction error as the raised exception.

## Exact evidence

- `ashare_pipeline/state_store.py:290-294` opens the connection with `begun = False`, executes `BEGIN`, and sets `begun = True` only after that statement succeeds.
- `ashare_pipeline/state_store.py:297-306` gates both `on_error` and rollback on `begun`. A failed `BEGIN` reaches the bare re-raise at line 306 without cleanup or rollback. Once begun, ordinary body, end-check, and commit failures still run cleanup before rollback. If cleanup itself fails, lines 302-304 roll back and raise the original transaction error with the cleanup error chained as its cause.
- `ashare_pipeline/state_store.py:307-308` closes the connection in `finally` for success, failed-BEGIN, body failure, cleanup failure, rollback path, and commit failure.
- `ashare_pipeline/snapshot_repository.py:77-90` shows why the guard is necessary: the registered callback may unlink an attempt-created immutable payload when no visible snapshot row protects it. `ashare_pipeline/snapshot_repository.py:92-102` confirms the ownerless caller prepublishes before entering the immediate transaction and passes that callback into `_transaction`; the repair prevents this callback from running when lock acquisition itself fails.
- `ashare_pipeline/snapshot_repository.py:103-130` preserves the established post-lock re-publication, verification, row insertion, and result behavior; the fix does not alter snapshot target semantics.

## Regression-test assessment

- `tests/test_snapshot_repository.py:315-328` wraps the real transaction rather than replacing it, and gives only caller A a real SQLite connection with `PRAGMA busy_timeout = 0`.
- `tests/test_snapshot_repository.py:330-340` observes the real immutable write, proves A created the payload, and proves B's first write adopted it (`created` is false).
- `tests/test_snapshot_repository.py:342-348` blocks B only after the real `record_snapshot` call has inserted its row inside B's still-uncommitted transaction, so B necessarily holds the writer lock.
- `tests/test_snapshot_repository.py:372-384` uses events, not sleeps, to order A's prepublication, B's adoption and row insertion, A's `BEGIN IMMEDIATE` attempt, A's completed failure, and only then B's commit.
- `tests/test_snapshot_repository.py:386-398` verifies A receives a real `sqlite3.OperationalError`, B completes without error, exactly one winner is returned, `read_verified` reads the committed payload, and exactly one snapshot row exists.

This test therefore forces the reported lock-acquisition failure and proves a real committed, readable winner survives it. Its event waits have bounded timeouts and contain no arbitrary sleeps.

## New-breakage review

No new Critical, Important, or Minor finding was identified in the three-file fix package.

- Begin failure: cleanup and rollback are correctly skipped because no transaction lifecycle was acquired; the original exception propagates and the connection closes.
- Body/end-check/commit failure after a successful begin: callback then rollback behavior is unchanged.
- Cleanup failure after a successful begin: rollback still occurs and the original transaction exception remains primary with the cleanup failure chained.
- Connection lifecycle: unconditional close remains in `finally`.
- Test validity: the new test exercises the production snapshot publication, production transaction, production row insertion, real SQLite lock contention, real commit, and verified readback.
- `progress.md:113-117` accurately records this bounded repair and keeps unrelated operational/readiness gates closed.

## Conclusion

The single Important finding is **ADDRESSED** at `4cd2acc0fe777e7e3c3b96d9de8a2752f7ba1f8e`. No scoped follow-up change is required.
