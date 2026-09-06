# Task 4B2 report — formal task lease fencing

## Base and scope

- Started from reviewed commit `34cff9b` in `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
- Production/test changes are limited to `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- Implemented only `lease_next_formal_task`, `renew_formal_task_lease`, `fail_formal_task`, and the binding addendum's expired-leased-child dependency resolution.
- Did not implement formal completion, supersession, snapshot/receipt persistence, universe persistence, schema/migration changes, or any legacy queue mutation.

## Behavior delivered

- Formal leases use `BEGIN IMMEDIATE`, sample implicit time after the writer lock, normalize UTC timestamps, calculate expiry with `timedelta`, validate the selected row through the 4B1 canonical getter contract before mutation, and repeat state/time/dependency eligibility in the final compare-and-set update.
- Ready tasks are pending tasks, due retryable failures with non-null retry time, and expired leases. Selection is deterministic by ready time, `created_at`, and task ID; retry and expiry equality are eligible.
- Renewal and failure mutations require the exact task, `leased` state, matching worker, and `lease_expires_at > now` at the final update. Equality loses ownership.
- Failure accepts only canonical finite mapping errors and the two failure states. Retryable failure requires an aware normalized retry timestamp; terminal failure requires `None`. Lease fields are cleared without changing payload, dependencies, result, or future receipt rows.
- Dependency resolution preserves live leased children and atomically terminal-fails leased children at or beyond expiry when a prerequisite is terminal/superseded, including transitive cascades.

## TDD evidence

### RED

1. First lease slice:
   - Command: two focused tests for lease eligibility/order and exact-expired dependency resolution.
   - Result: `Ran 2 tests in 1.593s` — `FAILED (failures=2)`.
   - Expected causes: `lease_next_formal_task` was absent; dependency resolution returned `0` instead of terminalizing an exactly expired leased child.
2. Renewal/failure slice, after lease GREEN and before either transition API existed:
   - Command: focused renewal-preservation and retry/terminal-failure tests.
   - Result: `Ran 2 tests in 1.211s` — `FAILED (errors=2)`.
   - Expected causes: `renew_formal_task_lease` and `fail_formal_task` were absent.

### GREEN

- Lease/addendum focused group: `Ran 7 tests in 4.741s` — `OK`.
- Combined lease/renew/fail/addendum group after correcting one test-kind isolation mistake: `Ran 13 tests in 8.293s` — `OK`.
- Adversarial dependency-CAS and non-string failure-state hardening: `Ran 2 tests in 1.799s` — `OK`.
- Required full bounded suite:
  - `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store`
  - `Ran 131 tests in 159.860s` — `OK`.
- `python -m py_compile ashare_pipeline\state_store.py tests\test_state_store.py`: exit 0.
- `git diff --check`: exit 0 (Git emitted only the repository's LF-to-CRLF checkout warnings).

## Coverage highlights

- All three lease eligibility classes and all exclusions, dependency block/release, deterministic ordering, inclusive time boundaries, and two-store one-winner contention.
- Expired takeover by a distinct worker and old-owner fencing for renew/fail.
- Renewal duration/time/owner validation and preservation of task content.
- Retry eligibility, terminal permanence, canonical error snapshots, invalid state/time/error combinations, and owner/expiry rollback.
- Candidate payload/hash tamper detection with byte-for-byte rollback.
- Implicit clock sampling after the writer lock and final failure fencing after error serialization.
- Live versus exactly expired leased-child dependency resolution.
- Full legacy StateStore regression through the 131-test suite.

## Limitation and V6 worker invariant

The fixed V5 API/schema has no lease-incarnation token. Therefore, exact ABA fencing is only guaranteed when every lease-owning worker process/incarnation uses a unique nonempty `worker_id`. V6 workers must not reuse a worker ID from an expired prior incarnation. This slice tests takeovers with distinct worker IDs and does not claim same-ID ABA safety.

Completion, supersession, and formal snapshot receipt gates remain deliberately deferred to later Task 4B/4C slices.
