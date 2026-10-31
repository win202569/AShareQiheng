# Terminal-serialization micro-fix re-review

## Scope and method

- Review range as supplied: base `1f155ef1a037079939c9a2c7fb1d093bf0b071e9`, head `29bac16fc1ee0f690a4ca8eeec6ff213c69bda69`.
- Scope was limited to the three-file package (`ashare_pipeline/state_store.py`, `tests/test_state_store.py`, and `progress.md`), the original serialization/lease Critical, and any breakage introduced by this micro-diff.
- I read `review-1f155ef..29bac16.diff` exactly once, then used narrow read-only inspection of directly relevant current definitions/call sites to resolve two concrete questions: transaction rollback behavior and whether owned terminal calls can bypass the strict APIs.
- Per review constraints, I ran no Git commands and no tests, and touched no data, runtime database, or network. Commit identity, RED/GREEN results, and suite totals are therefore assessed as supplied evidence rather than independently reproduced evidence.

## Verdict for the original Critical

**ADDRESSED.**

The head moves exact result/error serialization ahead of the final authorization clock sample in both owner-aware strict terminal methods. The guarded UPDATE consequently uses a timestamp sampled after serialization, so serialization can no longer consume lease time while the UPDATE retains the pre-serialization T9 authorization value described in the original Critical.

## Detailed checks

1. **Serialization precedes the final clock sample in Python execution order.**
   - `complete_job_with_followups` now executes `result_json = _json(result)` and only then `transition_now = _utc_now()`.
   - `fail_job_with_followups` now executes `error_json = _json(error)` and only then `transition_now = _utc_now()`.
   - The guarded statements consume the precomputed strings. Neither call expression contains a deferred `_json(...)` invocation.

2. **The final sample is adjacent to SQLite execution and is used consistently.**
   - In each method, the statement immediately following `transition_now = _utc_now()` is `connection.execute(...)`; only evaluation of a constant SQL string and construction of the parameter tuple occurs before entry into SQLite.
   - Complete binds the same `transition_now` to both `updated_at` and the final `lease_expires_at > ?` guard.
   - Fail likewise binds the same `transition_now` to both positions. Its `state`, `retry_at`, and `error_json` preparation all happens before the final sample.

3. **The complete and fail regressions are non-vacuous.**
   - `lease_next_job(..., 10, utc_at(0))` creates a T10 expiry. The patched clock returns T9 until `after_expiry` is set.
   - The worker must pass the initial owner check and reach `_json` on the exact terminal `payload` object before `serialization_entered` can be observed. Follow-up insertion is earlier in that same transaction.
   - The main thread sets the clock state to T11 before releasing the exact-object serialization barrier. On the fixed code, the next `_utc_now()` therefore produces T11, and the strict `lease_expires_at > T11` predicate cannot match the T10 lease.
   - With no other mutator and an already-successful T9 owner check, the post-barrier `ValueError` follows from the guarded UPDATE returning zero rows. The simple string-valued payload cannot introduce an alternate `_json` `ValueError`.
   - Equality with the post-lease `job_before` snapshot verifies that the job remains running with its lease state unchanged. Absence of the uniquely keyed follow-up verifies rollback; `_transaction` rolls back when the zero-row guard raises.
   - On the unchanged base ordering shown in the package, the final sample was still T9 before the barrier and the UPDATE used that stale T9 after release, so it would succeed; the assertions expecting one `ValueError`, unchanged running state, and no follow-up would fail. This agrees with the supplied genuine RED result of two tests/two failures.

4. **Both strict owned terminal paths are covered, with no scoped bypass left.**
   - The shared regression helper is invoked once with `complete` and once with `fail`, exercising `complete_job_with_followups` and `fail_job_with_followups` separately.
   - The fail test uses the non-retryable branch, but both retryability outcomes share the same precomputed `error_json`, final sample, and guarded UPDATE; `state` and optional retry-time normalization occur before that final sample.
   - Current direct call-site inspection found the deep-worker owned completion/failure flows calling these two strict methods. The legacy `complete_job` and `fail_job` APIs call `_require_legacy_transition_allowed`, which rejects all `_OWNED_JOB_KINDS` (`deep_financial`, `deep_statement`, and `feature_build`) and therefore do not bypass the owner-aware paths in this scope.

5. **Progress/report claims match the micro-diff and supplied evidence.**
   - The progress entry accurately describes serialization-before-final-sample behavior, zero-row lease fencing, transactional follow-up rollback, and preservation of running state.
   - Its exact RED 2/2, focused 15/15, affected 165/165, and staged full offline 426/426 figures match the supplied review brief. The RED figure is understood as two expected failures on the unchanged base.
   - The stated restrictions and readiness flags are not contradicted by this three-file diff. They were not independently revalidated in this read-only review.

## Test-evidence assessment

The two deterministic regressions directly target the defect mechanism rather than merely exercising terminal success/failure generally: exact-object serialization is the barrier, T9 is used for the initial ownership check, T11 is forced before the post-serialization sample, and observable database assertions cover both the job and inserted follow-up. Static inspection supports the supplied RED/GREEN interpretation.

Supplied run evidence is internally consistent: unchanged-base exact RED was 2 tests/2 failures; head exact tests were 2/2; focused lease tests were 15/15; affected StateStore/DeepWorker tests were 165/165; and staged full offline tests were 426/426. None of those commands was rerun for this review, as explicitly required.

## New findings by severity

- Critical: none.
- Important: none.
- Minor: none.

## Integration assessment

No scoped integration blocker remains for this terminal-serialization micro-fix. It is suitable to integrate with respect to the reviewed Critical and this three-file delta. This is not a whole-branch endorsement and does not independently certify the supplied test executions or commit-range identity.
