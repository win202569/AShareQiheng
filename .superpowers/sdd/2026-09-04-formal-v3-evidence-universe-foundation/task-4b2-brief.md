# Task 4B2 — formal task leasing, renewal, and failure fencing

This is the second serial slice of Task 4B.  It may start only after 4B1 has passed independent review.  Base on that approved commit, and read the parent `task-4b-brief.md`, V5 plan/spec, ledger, and the final 4B1 review result.

## Strict scope

Modify only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.  Do not alter schema/migrations, legacy jobs or recovery, snapshot/universe code, data/SQLite artifacts, or unrelated files.  Reuse the formal enqueue/get/dependency foundation; do not rename or weaken it.

## Deliver only these APIs/behaviors

```python
lease_next_formal_task(kinds, worker_id, lease_seconds, now_utc=None) -> dict[str, object] | None
renew_formal_task_lease(task_id, worker_id, lease_seconds, now_utc=None) -> str
fail_formal_task(task_id, worker_id, error, status, next_retry_at) -> None
```

`complete_formal_task` and `supersede_formal_tasks` are deliberately deferred to the next slices.  Do not pre-implement them.

Use the formal state machine only.  Leases must be acquired in one writer transaction and only from: pending; retryable failed with non-null due retry time; or an expired lease.  Recheck all eligibility (including every prerequisite being verified) in the compare-and-set update.  Never lease final/superseded rows, future/null-retry rows, or unexpired leases.  Empty kinds return `None`; empty worker ID/nonpositive duration/naive explicit time are rejected.  For implicit time sample `_utc_now()` after the writer lock.

Order candidates deterministically by ready time (created/retry/expired-lease), then `created_at`, then task ID.  Both retry and expiry equality boundaries are eligible.  On acquisition atomically set formal `leased`, worker, and a normalized UTC expiry; clear retry time.  Directly reclaim expired leases; never call or alter legacy lease recovery.

Renew and failure mutations must fence ownership at the final update: exact task, `leased`, same worker, expiry strictly after a freshly sampled time.  A previous owner after expiry/takeover, wrong worker, missing/final/superseded task, and expiry exactly at now must fail without mutation.  Renewal derives expiry from current time rather than prior expiry and changes no payload/result/error/dependencies.

Failure accepts only `retryable_failed` or `terminal_failed` and canonical finite error mappings.  Retryable requires an aware normalized `next_retry_at`; terminal requires `None`.  Clear lease fields, preserve payload/prerequisites, never manufacture/change a result, and preserve any later-added receipt.  Existing dependency resolution remains responsible for terminal parent cascades; do not build completion/receipt gates here.

All rows returned by lease must pass the 4B1 payload integrity/getter validation.  Use canonical JSON and transaction handling already approved in 4B1.

## TDD proof

Write RED tests first.  Cover every eligibility class, dependency block/release, deterministic ordering and exact boundaries, two-store one-winner contention, expired takeover fencing the old owner, renew variants, invalid durations/timestamps, fail validation/retry eligibility/terminal permanence, owner/expiry rollback guarantees, malformed payload detection on lease, and legacy StateStore regression.  Run the full `tests.test_state_store` suite; do not launch unbounded whole-project E2E.

Self-review and commit only scoped code/tests as:

`feat: add formal task lease fencing`

Write `task-4b2-report.md` in this SDD directory with RED/GREEN evidence, test count, and limitations.  No subagents/reviewers.
