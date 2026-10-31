# Final branch review — `e361fbd..4cd2acc`

## Strengths

- The branch keeps the approved scope hard closed. The versioned seven-dimension contract is immutable and deterministic, formal 0–100 scoring is not implemented or published, and both official pools remain closed. A focused cross-cutting check of the unchanged final gate confirmed that `ashare_pipeline/orchestrator.py:1383` always records `formal_v2_scores_unavailable`, while `ashare_pipeline/orchestrator.py:1395` keeps `formal_score_ready` false; the public status also records `seven_dimension_ready=false` and zero official pool publication.
- The PIT and evidence trust boundaries are unusually thorough. Candidate-context industry/template binding, `effective_at_utc <= as_of_utc`, newest-visible selection, raw-slot identity, derived-formula operands, balance semantics, evidence-to-fact/snapshot linkage, and exact feature file/DB mirrors are authenticated rather than trusted from serialized payloads. Newest-invalid bundles fail closed instead of falling back to an older valid bundle.
- Deterministic persistence is well designed in the main mutation paths. Immutable snapshot and feature artifacts use safe, no-clobber publication and verified reads; leased snapshot/file, fact, quality-issue, and feature file/DB mutations now use the shared owned `BEGIN IMMEDIATE` boundary in `ashare_pipeline/state_store.py:370`, including an owner recheck immediately before commit. `ashare_pipeline/snapshot_repository.py:99` keeps leased snapshot publication and its DB row inside that owned transaction and performs attempt-local cleanup on rollback.
- The v2-to-v3 migration is additive and fail-closed. The literal-v2 regression at `tests/test_state_store.py:331` preserves all seven legacy tables row-for-row before checking v3 additions, and the corrected plan names the real v2 tables at `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md:476`.
- The regression matrix is substantive: it attacks canonical payloads across first insert, idempotent reuse, DB tampering, verified progress, PIT cutoffs, candidate substitution, formula/raw aliasing, file/DB divergence, transaction rollback, takeover barriers, process-control propagation, and deterministic replay. I did not rerun the broad suite, per review instructions; the public controller evidence is 421/421 on exact HEAD.

## Issues by severity

### Critical

1. **Lease renewal and strict final transitions validate a lock-stale timestamp, so an expired worker can renew or commit after its lease has actually expired.** `ashare_pipeline/state_store.py:568` samples `now` before acquiring `BEGIN IMMEDIATE` at line 571. The same ordering appears in `complete_job_with_followups` at `ashare_pipeline/state_store.py:591`–592 and `fail_job_with_followups` at `ashare_pipeline/state_store.py:619`–620. All subsequent ownership predicates compare `lease_expires_at` with that pre-lock value.

   Concrete interleaving: worker A samples time T9 while its lease expires at T10; another SQLite writer keeps the write lock until T11. A then acquires the lock and evaluates `lease_expires_at > T9`, which still passes. Renewal can extend the already expired lease and resurrect A as owner; complete/fail can insert follow-ups and commit a terminal transition after actual expiry. A recovery worker is blocked by the same writer and can lose the lock race to the already-waiting stale worker. `_LeaseHeartbeat.final_transition` in `ashare_pipeline/deep_worker.py:937` serializes finalization against its own renewal thread, but it neither refreshes wall time nor repairs the stale database predicate. This breaks the explicit guarantee that renewal cannot resurrect an expired lease and that every final transition is atomically authorized by an owner whose lease is unexpired at the mutation boundary.

   Remediation: for default real-time operation, acquire `BEGIN IMMEDIATE` first and only then sample the authorization time. For complete/fail, re-sample current time immediately before the guarded terminal `UPDATE`; a zero row count must roll back all inserted follow-ups. Preserve explicit `now_utc` only as a deterministic test/logical-time override. Add deterministic writer-lock contention regressions that hold a second connection's `BEGIN IMMEDIATE` across lease expiry and prove renew, complete, and fail all reject without changing state or inserting follow-ups.

### Important

None beyond the Critical finding above.

### Minor

None.

## Historical/deferred finding status

All six previously deferred Minor cleanup areas are closed:

1. **Whole-job heartbeat coverage — closed.** `_LeaseHeartbeat` spans leased feature and statement work and serializes renewal/finalization (`ashare_pipeline/deep_worker.py:867`–947); process-control regressions also assert the renewal thread terminates (`tests/test_deep_worker.py:1363`–1404 and 1487–1491).
2. **Legacy absolute snapshot containment — closed.** Absolute legacy paths are accepted only after resolution beneath the configured data root (`ashare_pipeline/snapshot_repository.py:192`–219), with traversal/Windows-path regressions.
3. **Plan table-name typo(s) — closed.** The migration plan now lists the actual v2 tables, including `source_snapshot` and `quality_issue` (`docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md:476`).
4. **Broad unclassified negative-test catch — closed.** The boundary test now enumerates exact attacks and requires the `unclassified` validation error, then checks the positive round trip (`tests/test_feature_contract.py:588`–619).
5. **Zero-output specialized balance semantics — closed.** The builder only applies balance-equation blockers when the selected template has financial slots (`ashare_pipeline/financial_features.py:787`–790); zero-output specialized/unclassified projections remain empty, zero-coverage, and blocked under contract authentication.
6. **Process-control exception propagation — closed.** The feature loop catches ordinary `Exception`, not `BaseException` (`ashare_pipeline/deep_worker.py:1462`), and both feature and statement tests prove `KeyboardInterrupt`/`SystemExit` propagate unchanged while heartbeat threads terminate.

The two later residual findings are not both closed at whole-branch level:

- **Heartbeat shutdown masking/thread leak — closed.** Shutdown waits for the bounded in-flight renewal, preserves the active process-control exception, and the deterministic regressions assert the thread is no longer alive.
- **Lease/owner-fencing atomicity — not fully closed.** The previously named snapshot/file/fact/issue/feature mutation TOCTOU paths and their failed-BEGIN cleanup/adoption races are closed by the owned transaction and begun-transaction-aware cleanup. However, the Critical lock-stale timestamp defect above leaves renewal and final transition authorization outside the required real-time atomic fence. Thus the broader guarantee that stale/recovered workers leave no side effects is still open.

The residual repair's earlier 2 Critical/3 Important findings, plus the failed-`BEGIN` cleanup finding introduced during fix round 1, are otherwise closed on their exact paths; I found no regression in same-refresh fact/issue ownership, process-control propagation, commit-failure cleanup, snapshot adoption, or begun-transaction tracking.

## Operational gates

- Existing controller evidence reports the full offline suite 421/421 GREEN on exact `4cd2acc`, clean diff checks, clean tracked state, and no changed `data/` paths. I treated those as supplied evidence and did not rerun the suite or git checks.
- The exact production acceptance of 120 current candidates, 360 unique current child slots, and at least 114 fully complete candidates remains unperformed.
- The bounded live-network smoke remains unperformed.
- No runtime/tracked data migration or mutation was performed; production migration execution therefore remains an operational step, while literal-v2 preservation is covered by the hermetic migration regression.
- Formal scoring publication, the seven-dimension-ready gate, and both official stock-pool publications remain closed and are not acceptance work for this branch.

The unperformed 120/114 acceptance and live-network smoke are operational gates, not code defects. They do not reduce the severity of the owner-fencing defect.

## Assessment

**Ready to integrate? No.** Fix the Critical transaction-time lease check and add lock-contention regressions before integration; then rerun focused lease tests and controller verification. No other Critical, Important, or Minor issue was found in this review.
