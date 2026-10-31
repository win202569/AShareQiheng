# Stage D Task 9 implementation report

## Scope and baseline

- Baseline: `ec8781a0a3413f3a1f7f3c13d91974a6a6f2a3f3`.
- Worktree: `C:/Users/Lenovo/.codex/worktrees/formal-final-stage-d/AShareQiheng`.
- Commit: `bc4b2dbdbeea09b453feac40e7a469a5acd1ba32` (`feat: persist atomic formal final runs`). Only the eight Task 9 source/test files are included. This report is local handoff evidence.
- The pre-existing plan edit is preserved. No plan, ledger, production data, production DB/WAL/SHM or release/report artifact is changed by this task.

## Implementation

`FormalFinalRunRepository.commit_complete_run(...)` is the only write entry. It accepts exact genuine coverage, D1, D2, eligibility and pool proof types; checks the source chain and frozen membership; creates unpublished Stage D copies; serializes all canonical content before the write transaction; and appends a new run in all eight V8 tables.

The artifact vocabulary is fixed at the atomic writer:

1. `coverage_manifest`
2. `score_input_batch`
3. `scorecard_batch`
4. `eligibility_batch`
5. `pool_selection_batch`

Each artifact row contains its canonical bytes and SHA-256. The run header contains root/frozen/universe/coverage/input/result/code/contract identities. The transaction checks the header against the artifact identities and checks the exact stored rows, member sets, payloads and hashes against the prepared content. D1–D3 and pool identities remain in their unique artifact rows.

The canonical input/result identities exclude run ID and creation time, allowing independent append-only replays. Decimal values serialize as exact text; float and nonfinite Decimal payloads are rejected. Historical runs have no update/rebind/delete API.

`get_run(...)` and `list_runs_by_input_manifest(...)` return immutable recovery DTOs with immutable nested collections and detached JSON export. They expose no proof authentication method and cannot enter a live scoring builder.

## Publication boundary

- The coordinator alone issues an ephemeral preparation capability. Each module's adapter authenticates that capability, exact source identity and stage. The capability is never returned.
- Prepared D2/D3/pool records point to the matching prepared upstream records. Original published component/B/C proofs remain intact.
- One gate covers every prepared batch and child. `arm()` remains invisible to external proof checks.
- Commit prerequisites and the bound final flip are resolved before entering the SQLite transaction.
- The writer uses the owning StateStore connection with explicit `BEGIN IMMEDIATE`. After SQLite `commit()` returns, the next operation is the captured `mark_committed()` flip. Its body contains only the shared-state assignment, without calls, allocation or I/O.
- Connection cleanup occurs after the flip. A cleanup exception cannot report a durable committed run as failed or revoke its proofs.
- Precommit/commit failure rolls back and revokes this run's prepared gate. A permanent revocation latch prevents a retained flip from resurrecting revoked children.
- Prepared input proofs retain the original D1 authority, so source revocation invalidates committed descendants. Method/adapter replacement, copied/constructed proofs and weak-reference redirection cannot establish authority.

## Tests and evidence

### RED

The requested Task 9 two-module command initially produced two `ModuleNotFoundError` errors for the absent repository and publication modules, as required by the brief. Full behavioral tests were then written before implementation.

### Initial integration run

The first complete requested three-module run finished in `718.215s`: 25 tests, 24 passed and one error.

The error was `test_weak_reference_redirect_does_not_authenticate_forgery`. It required preparation to succeed while `weakref.ref` was replaced. Stage C correctly rejected that changed authority with `ValueError: valuation publication dependency changed`. The test now explicitly requires fail-closed behavior and verifies that unmodified original proofs remain usable after restoration.

### Other completed checks

- Task 8 migration module: 11 tests passed, `146.199s`.
- Pool guard module: 5 tests passed, `0.013s`.
- Pure eligibility guards and threshold rules: 9 tests passed, `0.040s`.
- Task 9 source/test syntax compilation passed.
- `git diff --check` passed; Git only reports the repository's normal LF/CRLF conversion notices.

### Final required run

Final required command passed: **33 tests in 606.531s, 0 failures/errors/skips**.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_repository tests.test_formal_final_atomicity tests.test_formal_final_migration -v
```

The tests share one genuine three-member producer chain within the process. No proof doubles, fixture minting authority or 20/23-member long chain are used. Initial diagnostic runs were stopped or suffered a runner failure; they are not counted as passing test runs.

The final code also passed the combined pool guards / pure eligibility guards / pure threshold rules command: 14 tests in `0.034s`.

## Coverage and limits

- The fault matrix includes every V8 table's insert boundary, pre-write and final serialization, final source recheck, exact set/hash recheck, arm and SQLite commit. It checks unchanged pre-existing row counts and revoked prepared batches/children.
- End-to-end tests cover complete blocked-run persistence, no fabricated selected pool, append-only replay, historical collision protection, cross-frozen/forged input rejection, immutable non-authoritative recovery and precommit proof invisibility.
- The minimal genuine fixture is all pending. Its scorecard table is legitimately empty: the fault matrix still exercises that table's batch-insert boundary. Exact Decimal text is additionally checked through the production serializer and SQLite TEXT round-trip. Real populated scorecards and selected ready pools remain Task 11's 20/23-member acceptance coverage.
- Dependency rows preserve root-wide (`global`) and member (`security`) hash paths. Task 10 owns detailed cohort/pool propagation and extends the repository as specified in its plan.
- Official production coverage and real-data execution are not claimed here. The test suite verifies that preview-only coverage cannot create an `official_candidate` run.
- No full-project test run was attempted because the task explicitly bounds validation to Task 9, Task 8 migration and relevant fast guards, and reserves long chains for Task 11.

## Handoff

Tests are green. The implementation is committed as a **review candidate, not an accepted/completed Task 9**. The following points were sent to the parent before closing the task:

1. Current-source freshness: D1 preparation revalidates original proof seals/canonical bytes, repository graph identity and retained derived proofs. The writer re-reads the frozen universe and signed root. Inspection confirms that base/policy/valuation `require_verified()` principally verifies sealed publication state, not fresh database selections. Policy has `recheck_current(batch)`; base and valuation have no corresponding public recheck entry. The prior `_metric_batch_guard` is already closed after D1 construction. A complete current-source freshness contract needs an approved retained checkpoint or equivalent lightweight finalizer, without rerunning the long calculation inside the write transaction. This is a correctness concern, not a passing-test claim.
2. Recovery checks: the reader validates artifact membership and stored artifact/row payload hashes. It does not independently reconstruct all recovered table projections and member sets from the artifacts. Recovery DTOs still grant no live proof authority.
3. Existing ready-pool boundary: `formal_pool.build` passes JSON-decoded `sort_fields` to a selection helper that requires `Decimal` values for qualified members. The all-pending fixture does not exercise this pre-existing ready-member path. The issue was raised for a Task 9 versus Task 11 scope ruling.

The parent task had already ended before these review questions were delivered, so no independent review disposition was available in this turn. The candidate was committed under the existing authorization to preserve a concrete reviewable result. It was not pushed or merged. Final Git status contains only the pre-existing unstaged plan change; the implementation commit has exactly the eight allowed Task 9 files. The current-source freshness concern must be resolved before Task 9 acceptance.

## Review repair — four Important findings (2026-10-02)

This section supersedes the unresolved implementation claims above; earlier evidence is retained as history. Repair scope remains inside the eight Task 9 files. No plan/progress/ledger, upstream provider file, production database, release artifact, push or merge is included.

### Current source checkpoint

D1 now retains a source checkpoint at its original authenticated publication boundary. The checkpoint captures the existing owning provider's authenticated private record, monotonic epoch and lock through its captured `require` closure, using the same upstream-private-authenticator pattern already used by D3. It also fingerprints the schema and complete row content of non-Stage-D user tables from a consistent SQLite read transaction. Preparation checks that original checkpoint, and the writer checks it again against its own write connection inside the final transaction. Stage D history tables are deliberately excluded, so appending or replaying a final run does not invalidate unchanged source evidence.

The provider's publication lock and `finalizing` flag are held across the final write transaction and commit boundary. Reentrant provider publication fails closed and changes its epoch, which subsequent checkpoint verification rejects. No metric/policy/valuation calculation is repeated in the transaction. This is deliberately conservative: changes to unrelated non-Stage-D source/operational tables also invalidate the checkpoint. Content fingerprint work scales with database size; narrowing it to authenticated retained selectors is a future optimization, not permission to omit source verification.

### Recovery consistency

Recovery now parses and canonically re-encodes all five artifacts, verifies their SHA-256 and schema/internal batch/row identities, cross-checks D1/D2/D3/pool member provenance, reconstructs all six child-table projections, and compares every stored column and exact key/member set. Header root/frozen/universe/as-of/coverage identities, derived status, input-manifest identity and result identity are checked against those canonical authorities. The existing released D2 hash preimage includes D1's `batch_hash` before overwriting its own field; recovery intentionally reproduces that established contract without changing D2 hashes.

### Repository-owned publication

The exported coordinator's `prepare` now rejects direct calls before consulting any supplied producer. The real preparation factory is bound once to the exact repository writer and registered initialized repository instances. It returns a read-only prepared proof observer, with no arm/commit/revoke/recheck methods. A one-shot private control handoff additionally requires the immediate authenticated writer frame, so callbacks merely running inside the writer stack cannot acquire authority. The writer alone receives the prevalidated non-failing flip, which retains its assignment-only body. Genuine commit observers continue to see every prepared proof as unpublished until SQLite commit returns. Fault connections are injected only at the writer connection seam, never by replacing the owning StateStore/provider graph.

### Qualified pool boundary and populated storage

After genuine eligibility authentication and canonical-byte comparison, the pool builder converts only validated canonical finite decimal text into exact `Decimal` values. The pure selector still rejects text/floats. A populated canonical DTO fixture exercises the production projection, V8 SQLite tables and recovery reader with a high-precision scorecard and a selected strong-pool ordinal. It does not mint or impersonate live proofs; genuine end-to-end tests continue to share the three-member all-pending chain, while the full qualified 20/23-member producer integration remains Task 11 scope.

### RED evidence

1. `tests.test_formal_final_repository.FormalFinalRecoveryBoundaryTests`: 4 tests in `0.019s`, failed with 12 expected assertion failures (six child-table deletions; score/pool projection, recomputed child payload hash, and header tampering) plus missing `_detach_eligibility_rows` ImportError. The pre-existing populated SQLite round-trip passed.
2. `tests.test_formal_final_atomicity.FormalFinalAuthorityBoundaryTests`: 2 tests in `0.003s`, failed with direct coordinator access reaching the producer tripwire and missing `_current_source_checkpoint` ImportError. These are the intended authority/source-checkpoint RED failures.

### Targeted GREEN evidence

- Six new recovery, decimal, authority and actual SQLite/provider checkpoint tests passed in `0.057s` after implementation.
- Combined command for those six plus `tests.test_formal_pool.FormalPoolSelectionTests`: **14 tests passed in `0.057s`**.
- One intermediate command named a nonexistent `PoolSelectionGuardTests`; that discovery error is not counted as product RED/GREEN. It was corrected to the existing class and rerun successfully.
- Additional genuine-chain tests now mutate a real `formal_source_snapshot.content_sha256` and publish a changed real provider generation after preparation, requiring rollback and revoked prepared descendants. A source correction is restored exactly; the provider-change case is intentionally the last genuine-chain test because its epoch cannot legitimately be reset.
- Exact required Task 9 + Task 8 verification ran once after targeted GREEN and passed: **40 tests in `209.979s`, exit 0, zero failures/errors/skips**. This includes both real post-preparation source-change cases, all eight table fault boundaries, commit-observer invisibility, direct lifecycle rejection and the 11 Task 8 migration cases.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_repository tests.test_formal_final_atomicity tests.test_formal_final_migration -v
```

`git diff --check` passed after the full run; output contained only ordinary LF/CRLF notices. No code changed after that successful full verification. The repair is ready for the parent's independent re-review; passing tests do not by themselves declare Task 9 accepted.

### Repair commit and remaining limits

Repair commit: **`72b11b832bc15f3434c77778d468a248a3fcd00a`**, `fix: close Stage D publication and recovery gaps`, on top of candidate `bc4b2dbdbeea09b453feac40e7a469a5acd1ba32`. It changes six permitted Task 9 files: repository, publication, score inputs, pool, and the two Task 9 test modules. The scoring and eligibility modules needed no additional changes for these findings. The report itself is not committed.

Post-commit status shows only the pre-existing unstaged plan edit. No data/SQLite/WAL/SHM, progress/ledger, plan, or report file is in the commit. No push or merge occurred; the same branch/worktree is retained for re-review.

The four Important findings are implemented and covered by the evidence above. Remaining limits are explicit: conservative source-table fingerprinting is O(source database contents), populated scorecard storage and qualified decimal boundaries use canonical DTO/pure boundary fixtures (not counterfeit proofs), and a fully qualified genuine 20/23-member end-to-end population remains Task 11 acceptance work. Mixed blocked batches preserve existing genuine selections as diagnostic data; this repair does not invent a new policy for them.

## Review repair round 2 — frame authority and selected-member closure

Independent re-review of `72b11b8` accepted the source-checkpoint and Decimal fixes but found two remaining Important gaps: the lifecycle frame reader was a replaceable module global, and selected pool lists could contain a frozen-universe outsider absent from all decision rows. This section records their repair without treating round 1 as accepted.

### Changes

- Publication installation now captures the real frame and weak-reference authorities in its closure. Preparation/control authentication, repository binding and owner registration use those captured authorities and reject changed module bindings before consulting frames or producer proofs. A callback that supplies a frame-shaped object with the genuine writer code and a registered real repository cannot pass authentication.
- Each pool's selected list must contain unique string IDs entirely inside the frozen member set, match its declared count, and equal exactly the IDs whose decision for that pool is `selected`. The canonical list continues to define 1-based selected ordinals; recovery's existing all-column comparison checks persisted ordinal identity against it.
- Existing source checkpoint, Decimal conversion, sole writer and append-only/recovery semantics are preserved. No policy change was made for mixed blocked preview batches.

### RED evidence

The short two-test command failed as intended: **2 tests in `0.025s`, three assertion failures**.

1. Replacing publication `_getframe` let external preparation reach a producer tripwire.
2. The same replacement let external control-taking pass the writer check and fail only at absent capability lookup.
3. Recovery accepted `SH600999` appended to the strong selected list despite the frozen universe and all decision rows containing only `SH600000`. The attack recomputed pool batch hash, artifact hash and header result hash, so rejection could not rely on stale hashes.

The same recovery regression also exercises a listed selection with no selected decision and an extra selected decision absent from its list. Those cases were already rejected; the new explicit set-equality check preserves that behavior. Persisted selected-ordinal mismatch remains covered by the earlier projection tampering regression.

### Targeted GREEN and final verification

Combined short authority, source-checkpoint, recovery, qualified Decimal and existing pool tests: **16 tests passed in `0.077s`**. A separate genuine-chain regression attempts to steal controls for an actual still-pending publication by replacing `_getframe` inside the preparation callback; the normal writer must retain control and complete successfully after the attack is rejected.

The exact required Task 9 + Task 8 command ran once for this round after targeted GREEN: **43 tests passed in `131.447s`, exit 0, zero failures/errors/skips**. The genuine pending-publication attack was rejected, the legitimate writer then committed successfully, and all prior source-correction/provider-change, proof lifecycle, eight-table atomicity and migration regressions remained green.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_repository tests.test_formal_final_atomicity tests.test_formal_final_migration -v
```

No production code changed during or after this run. `git diff --check` passed, with only repository LF/CRLF notices.

Round 2 commit: **`4be7a8a96375eebad777d234bb484bc8c803eccf`**, `fix: seal Stage D frame authority and pool membership`, based on `72b11b832bc15f3434c77778d468a248a3fcd00a`. Exactly four allowed files are committed: `formal_final_publication.py`, `formal_final_repository.py`, and the two Task 9 test modules. This report is uncommitted. Post-commit status contains only the pre-existing unstaged plan edit; no plan/ledger/data/database/WAL/SHM/report was staged, and no push or merge occurred.

Both round 2 Important findings are fixed and verified, ready for independent re-review. Previously disclosed whole-source fingerprint cost remains deferred Task 11 performance work; no new scope or policy ruling was needed.
