# Task 4B3 — formal completion and generation supersession

This final serial slice of Task 4B may start only after 4C3 passes independent review.  Base on that approved commit and read the V5 plan/spec, parent 4B brief, Task 4C receipt contracts, ledger rulings, and current StateStore APIs/tests.

## Strict scope

Modify only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.  Do not change schema/migrations, FormalSnapshotStore, universe/status persistence, legacy jobs/snapshots, data/SQLite artifacts, or unrelated code.

## Deliver only

```python
complete_formal_task(task_id, worker_id, result) -> None
supersede_formal_tasks(scope, before_generation) -> int
```

Reuse approved formal lease/JSON/receipt helpers.  Do not modify queue enqueue/lease/renew/fail behavior except minimal shared private helpers necessary to enforce the contracts below.

## Completion fence and evidence gate

- Require nonempty exact task/worker IDs and a finite canonical result mapping.  In one formal writer transaction, final mutation must be fenced by task ID, state `leased`, same worker, and `lease_expires_at > freshly sampled now`.  Wrong/missing/final/superseded/expired/taken-over owner fails without any mutation.
- Successful completion transitions to `verified`, stores canonical result JSON, clears error/retry/lease fields, and preserves payload/prerequisites/receipt.
- For source-fetch kinds `formal_statement`, `formal_context`, `formal_universe_source`, completion requires exactly one valid formal receipt in the same consistent database transaction: matching task, snapshot producer, manifest hash, refresh generation, and fully validated formal source row.  No receipt/extra/orphan/mismatch/tamper must fail closed without completing.  Never use legacy snapshots.
- `formal_feature_build` requires no raw receipt.  `formal_universe_finalize` must fail closed in this slice unless a later 4D verified-universe validator explicitly supplies matching proof; do not mark it verified from an arbitrary result before 4D.
- Later `fail_formal_task` transitions must leave an existing receipt untouched (already guaranteed, retain regression).

## Supersession rule

- Scope is a nonempty exact top-level subset match against canonical formal task payload; reject invalid/nonfinite/empty scope.
- `before_generation` denotes the generation to retain.  For scope matches, supersede only unfinished `pending`, `leased`, `retryable_failed` tasks whose `refresh_generation != before_generation`; never compare generations lexicographically.
- In one `BEGIN IMMEDIATE` transaction mark only those tasks `superseded`, clear lease/retry fields, preserve rows/payload/results/errors/dependencies/receipts, and immediately fence old owners.  Never alter `verified`, `terminal_failed`, already superseded, current-generation, or other-scope tasks.

## TDD proof

Write RED tests first.  Cover canonical result / nonfinite rejection; owner/expiry/takeover fencing; successful non-source completion; source completion missing/valid/invalid receipt graphs; source receipt preservation after later failure; finalizer fail-closed pre-4D; completion atomic rollback; scope validation and supersession exact set/preservation/owner fencing; direct task/race boundary and legacy isolation.  Run focused tests then bounded full `tests.test_state_store`; no unbounded whole project suite.

Commit only scoped files:

`feat: complete formal tasks safely`

Write `task-4b3-report.md` in this SDD directory with RED/GREEN proof and note the 4D finalizer gate remains pending.  No subagents/reviewers.
