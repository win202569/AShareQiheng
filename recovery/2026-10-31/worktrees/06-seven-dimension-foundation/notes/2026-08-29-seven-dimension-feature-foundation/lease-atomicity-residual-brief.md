# Authorized residual repair: atomic lease fencing and reliable heartbeat shutdown

## Authority and exact base

- User explicitly authorized this residual repair on 2026-09-01 after the scoped review of `3ce5a90`.
- Work only in `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation` on `feature/seven-dimension-foundation`.
- Exact pre-edit base: `3ce5a903d9eafb2573c493960c0d8e180f33834e`.
- Requirements authority: this brief, the existing feature-foundation spec/plan, and `final-minor-cleanup-scoped-review.md`.

## Root causes already established

1. `_LeaseHeartbeat.ensure_owned()` checks only a cached event. The check and the following snapshot, fact, quality-issue, or feature write are separate operations. An expired worker A can pass the check, worker B can recover and acquire the job, and A can then commit intermediate durable state. Final transitions are owner-fenced, but these earlier writes are not.
2. `_LeaseHeartbeat.close()` performs a bounded join and raises if the renewal thread remains alive. During an active `KeyboardInterrupt` or `SystemExit`, that cleanup exception masks the process-control exception and the renewal thread survives the worker return.

## Required behavior

### A. Transaction-level lease fencing

- Every durable mutation authorized by a leased `financial_statement` or `financial_feature` job must verify `job_id`, `worker_id`, `status='running'`, and an unexpired lease inside the same `BEGIN IMMEDIATE` transaction as the mutation.
- This applies to all intermediate effects reachable from the leased deep worker:
  - final snapshot-file publication and `source_snapshot` insertion;
  - `financial_fact` insertion;
  - normalization `quality_issue` insertion;
  - final feature-bundle-file publication and `feature_set`/`feature_value` insertion.
- A cached-event check, a lock released before the write, or a separate preliminary query is not sufficient.
- Ownership must be revalidated at the end of a potentially long owned transaction before commit, so expiry during file work rolls back DB state and cleans only the file created by that attempt.
- A stale, wrong, expired, recovered, or released owner must leave no new final file, snapshot row, fact row, issue row, feature-set row, feature-value row, follow-up, success transition, or circuit mutation.
- Existing legitimate immutable winners must never be deleted by stale-worker rollback cleanup.
- Valid current owners and existing idempotent/no-clobber behavior must continue to work.
- Existing non-job repository/store callers may retain compatible ownerless APIs, but the leased deep-worker paths must use the owner-fenced variants exclusively.
- Do not add or migrate schema. Reuse the existing job ownership authority and transaction machinery.

### B. Reliable heartbeat shutdown

- `KeyboardInterrupt` and `SystemExit` raised by feature or statement work must propagate as the original exception even when renewal is in flight; no retry/failure transition may be emitted for them.
- Heartbeat cleanup must not replace an already-active exception with a cleanup `RuntimeError`.
- When the worker operation returns or raises, its heartbeat renewal thread must no longer be alive.
- Production renewal remains bounded by the StateStore SQLite timeout; shutdown may wait for an in-flight bounded renewal to finish rather than abandon the thread.
- Ordinary exceptions must retain the existing retryable/terminal behavior.

## Mandatory TDD evidence

Before any production edit, add deterministic tests and run them against exact base `3ce5a90`; record the command and expected failures in the report.

The RED suite must use real production paths and condition/barrier synchronization, not arbitrary sleeps, and must demonstrate at least:

1. A worker passes its old pre-action ownership check, then loses the lease through real expiry/recovery/release and another worker acquires it; the stale worker cannot create each of the snapshot/file, fact, quality-issue, and feature/file+DB effects.
2. The owner-fenced StateStore/repository APIs reject wrong and expired owners atomically while valid-owner positive controls succeed.
3. Rollback cleanup does not delete a legitimate immutable winner.
4. A renewal call is in flight when `KeyboardInterrupt` and `SystemExit` leave the heartbeat context; each original exception propagates and the heartbeat thread is terminated. Use an event/barrier that eventually releases the bounded fake renewal so the test itself cannot hang.
5. Existing ordinary-exception retry behavior remains a positive control.

After GREEN, run focused tests, every affected test module, the complete offline suite once on the committed/staged tree, and `git diff --check`. Use the short worktree-local TEMP/TMP/TMPDIR convention because long Windows paths are known to fail spuriously.

## Scope boundaries

- Do not touch real network, runtime/tracked databases, or any tracked `data/` content.
- Do not run migrations.
- Do not open formal scoring, seven-dimension readiness, or either official stock pool.
- Do not perform operational `120/114` acceptance.
- Do not refactor unrelated scheduling, feature formulas, templates, progress semantics, source adapters, or CLI behavior.
- Do not edit or stage `.superpowers/` or test-temp directories.
- Preserve unrelated/untracked controller noise.

## Delivery contract

- Implement as one bounded TDD task and commit only relevant tracked files.
- After actual verification, update tracked `progress.md` with the repair and exact test evidence while keeping every operational, formal-score, seven-dimension, and stock-pool gate closed.
- Write the full report to `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/lease-atomicity-residual-report.md` with exact RED/GREEN commands, outputs, changed files, self-review, and concerns.
- Return only status, commit SHA/subject, one-line test summary, concerns, and the report path.
- Do not spawn subagents or reviewers.
