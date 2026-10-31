# Task 10 implementation report

Baseline: `4be7a8a96375eebad777d234bb484bc8c803eccf` (accepted Task 9).
Worktree: `C:/Users/Lenovo/.codex/worktrees/formal-final-stage-d/AShareQiheng`.
Branch: `codex/formal-final-stage-d`.
Scope: `formal_final_invalidation.py`, `formal_final_repository.py`, and `test_formal_final_invalidation.py` only. The pre-existing unstaged plan edit is preserved. No plan/ledger change, database artifact, push, merge, or Task 11 implementation is included.

## Design and trust boundary

- `FormalFinalRunRepository.plan_rebuild` requires both an exact prior `run_id` and its `input_manifest_hash`, plus genuine current D1 and coverage proofs. There is no changed-ID argument, DTO input authority, latest-run lookup, or recovery proof mint.
- Historical rows pass the existing Task 9 reader, which reconstructs all projections from the five artifacts. The diff additionally checks prior dependency rows against the original hash-path projection. Task 9's writer, projection, schema and recovery semantics are unchanged.
- The live reader captures D1's existing private record/dependency/source-verification authorities, following the established owner-authenticator pattern. It holds the original current-source checkpoint during the read/diff, checks capabilities and bytes before/after, checks source-store identity and coverage method identity, and revalidates the source checkpoint before returning. No new publication or mint capability is exposed. A plan is an immutable DTO, not future reuse authority; eventual writes must still revalidate.
- Diffing separates aggregate seals from local economic evidence. Per-member non-peer evidence rebuilds D1/D2/eligibility and rescans both pools. V/non-V peer inputs expand old and new canonical peer contexts; cohort keys include metric, template, scope, industry, definition and direction. Policy caps rebuild D2; prohibitions/states rebuild D1 and eligibility without unnecessary arithmetic; pending rebuilds score presence/state; normalization expands V cohorts. Global identities, industry mappings, code/contract/mode changes rebuild the full affected population.
- Supported effect scopes are exactly `security`, `cohort`, `pool`, and `global`. Output ordering and reason codes are deterministic. Diagnostic/display data do not create economic rebuilds.

## Parent ruling

The accepted D1 artifacts omit original metric inputs and peer contexts for pending members. Existing Task 9 dependencies cannot always localize a later changed aggregate source hash. The parent explicitly approved a conservative full rebuild in this case, without changing schema or storing richer upstream manifests. The implementation reports `unlocalizable_upstream_change` or `unlocalizable_cohort_change`; it never invents a narrower set. The source family is tracked so a local policy cap cannot excuse an unrelated unlocalized base change.

The parent also confirmed that D1/D2/eligibility rebuild IDs contain only current universe members. Departed securities remain in direct-change diagnostics, but cannot become current stage build targets.

## RED evidence

1. All nine exact named task tests were written before production implementation. Required command:

   `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_invalidation -v`

   Actual result: exit 1; one loader error, `ModuleNotFoundError: No module named 'ashare_pipeline.formal_final_invalidation'`, as the task's expected module/API-missing RED.

2. Self-review added `test_local_policy_change_cannot_hide_unlocalizable_base_change` before repairing the source-family fallback. Actual RED: 1 test in 0.004s, assertion `full_rebuild` was false.

3. Self-review added `test_nested_industry_manifest_change_forces_full_rebuild` before adding nested global dependency comparison. Actual RED: 1 test in 0.002s, assertion `full_rebuild` was false.

4. Producer-vocabulary review added `test_policy_copy_inside_valuation_input_does_not_turn_cap_into_cohort_change`: genuine Stage C repeats PolicyResult inside each valuation input. Actual RED: 1 test in 0.002s, a cap-only change expanded two members instead of one. Result comparison now reads only metric/valuation result fields and contexts, leaving repeated PolicyResult to the policy effect diff.

5. `test_universe_departure_is_diagnostic_but_never_a_current_rebuild_target`: actual RED 1 test in 0.002s, departed `SZ000001` incorrectly appeared in D1 rebuild IDs. The implementation now intersects stage build sets with current members while retaining direct removal diagnostics.

An intermediate initial focused run had four assertion failures caused by the detached test fixture incorrectly giving its unrelated third security a peer list containing the first two securities. The planner correctly expanded that declared consumer. The fixture was corrected to give the third security its own cohort; this is not claimed as a product defect.

## GREEN and affected regression

- Initial focused scope GREEN: 9 tests in 0.022s.
- Focused GREEN after both self-review fixes: 11 tests in 0.028s, exit 0.
- After the repeated-policy fix: 12 tests in 0.026s, exit 0.
- Final focused GREEN after current-universe filtering: 13 tests in 0.030s, exit 0.
- Exact affected command runs the new module plus `tests.test_formal_final_repository` and shares that module's `minimal_batches()` fixture, constructing one genuine three-member chain. Results will be appended below after completion.

The first exact command had already imported the pre-policy-copy-fix core. At the parent's instruction, it was safely stopped during signed fixture setup with Ctrl+C (exit 1, no completed test result). It is **not** counted as final GREEN. After both subsequent focused RED/GREEN fixes, code was frozen and the exact command was restarted against final code. This one restart is recorded rather than hidden as a completed test run.

The genuine cases exercise exact manifest recovery despite a later coverage correction, append-only byte preservation, dictionary/unminted proof rejection, revoked coverage, rollback-revoked prepared D1, and an actual persisted source-content correction while D1 canonical bytes remain unchanged.

## Limits

The pure propagation tests use detached canonical producer-shaped data and grant no live proof authority. Genuine repository coverage uses the accepted all-pending three-member chain. Fully qualified 20/23-member integration and whole-repository regression remain Task 11 as directed. Current-source fingerprint costs are inherited from accepted Task 9. No production-data readiness or V9 release claim is made.

Commit, final verification count and final status will be appended after verification.

## Active final verification checkpoint

Final command started at local `2026-10-02 16:36:40`, tool process session `62035`, Python worker PID `10652`. At `17:13:55` it had elapsed 37m15s and accumulated 1901.36 CPU seconds. Its only stdout remains `Task 9 minimal fixture: signed three-member root`; the D1-start marker has not appeared, and no test case has completed or failed. The parent explicitly directed keeping this CPU-active run even past 35 minutes unless a deterministic fixture defect is established. Read-only checks confirmed `peer_count=3` is forwarded correctly; no installed nonintrusive Python stack utility is available. This is an ongoing run, **not GREEN evidence**. Production/test code has remained frozen since the final command started.

### Sixty-minute performance diagnostic

At local `17:37:03`, elapsed time was **60m23s**, worker CPU was **3095.14s** and working set was about **16.8 MB**. Stdout had not advanced beyond the flushed signed-root marker. The observed phase is bounded by `FinalScoringFixture(peer_count=3)` construction plus the three `put_industry` calls that precede the next flushed D1 marker; there is no stack evidence to distinguish those steps. The new planning API and test bodies have not been entered. CPU is advancing, so this is active computation or a busy loop rather than evidence of a sleeping process; its precise cause remains unproven. No deterministic fixture defect is established and the current run has not been interrupted. The parent directed continuing it past sixty minutes, preserving code freeze, and withholding both GREEN and commit until the exact command completes. Future performance investigation should add phase timing/stack diagnostics around this existing fixture setup; no such instrumentation or out-of-scope fixture edit was made during Task 10.

## Phase 1 root-cause diagnostic — supersedes the uncertain phase above

At the parent's explicit direction, session `62035` was safely stopped with Ctrl+C (exit 1). It is an **unverified 60+ minute busy-run diagnostic**, not a test result. No production or test file was changed.

A separate minimal-only process (session `80783`) enabled `faulthandler.dump_traceback_later(30, repeat=True)`, printed flushed import/call boundaries, then called only `tests.test_formal_final_repository.minimal_batches()`. Its two dumps at 30 and 60 seconds showed the same chain:

```text
Python Lib/tempfile.py:384 / :391 in mkdtemp
Python Lib/tempfile.py:886 in TemporaryDirectory.__init__
tests/test_formal_feature_store.py:32 in project_temporary_directory
tests/formal_metric_feature_fixtures.py:55 in __init__
tests/formal_policy_runtime_fixtures.py:166 in __init__
tests/formal_valuation_fixtures.py:41 in __init__
tests/formal_final_scoring_fixtures.py:132 in __init__
tests/test_formal_final_repository.py:174 in minimal_batches
```

The diagnostic was stopped after those two repeated stacks (exit 1). A single direct `os.mkdir(probe, 0o700)` under the actual fixture parent reproduced the cause immediately:

```text
parent = C:/Users/Lenovo/.codex/worktrees/formal-final-stage-d/AShareQiheng/.tmp/formal-feature-store-tests
parent.is_dir() == True
os.access(parent, os.W_OK) == True
os.mkdir(unique_probe, 0o700) -> PermissionError: [WinError 5] Access is denied
```

No probe directory was created. Python's Windows `tempfile.mkdtemp` handler catches `PermissionError` and retries candidate names when the existing parent reports writable. That exact retry branch appears in the second stack dump. The current sandbox writable-root list omits this C: worktree, which explains the disagreement between the access check and actual directory creation. The established failure is temporary-directory authorization, before fixture/signature/scoring work; previous references to root preparation described only the last printed marker.

Read-only Git comparison with accepted Task 9 `4be7a8a` showed no changes to `test_formal_feature_store.py`, `formal_metric_feature_fixtures.py`, `formal_final_scoring_fixtures.py`, or `test_formal_final_repository.py`. The accepted Task 9 report records 43 tests in 131.447s; the current sandboxed runs never passed temporary-directory creation, so their elapsed time is not comparable scoring performance. No fixture or production fix was proposed/applied before collecting this evidence. Environment permission correction and final exact verification remain outstanding.

### Permission differential confirmed

The identical single-directory probe was run through the supported `require_escalated` execution path. It immediately printed `SINGLE_MKDIR_SUCCEEDED`, removed its uniquely named empty directory, printed `PROBE_REMOVED`, and exited 0. Default sandbox failure versus escalated success under the same parent conclusively identifies sandbox authorization as the cause. No code, fixture, ACL, or operating-system configuration was changed.

A brief dispatch race occurred after this proof: the implementer started the exact command through escalation (session `86246`) just before receiving the parent's message that the parent had already started that same final command. The implementer's duplicate reached `Task 9 minimal fixture: D1` within the first ten seconds, then was immediately stopped with Ctrl+C (exit 1). It is not counted as GREEN. The parent's exact command remains the sole final verification run; its actual output will be recorded below. Production and test files remain frozen.

## Final exact verification — GREEN

The parent ran the required command in this same worktree against the frozen final code through the verified supported escalation path:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_invalidation tests.test_formal_final_repository -v
```

Actual result supplied by the parent: **Ran 30 tests in 103.387s; OK; exit 0; zero failures, errors, or skips.** This consists of 16 Task 10 tests (three genuine repository/recovery/reuse tests plus thirteen detached scope tests) and fourteen accepted Task 9 repository regressions. This is the final-code exact GREEN evidence; none of the interrupted default-sandbox or duplicate diagnostic runs is counted as a passing run. No production or test code changed after the final code freeze, and no additional tests were run after this result.

The successful 103.387s run is consistent with the previously reported Task 9 runtime order of magnitude. The 60+ minute attempt was conclusively a denied-temporary-directory busy loop under the restricted execution context, not evidence of slow scoring or a Task 10 algorithm regression. No production performance claim beyond these test observations is made.

## Commit and handoff

Commit: **`2bdb21512e991f4398af4bb9fee335caa34e9ac2`** — `feat: plan formal score invalidation scopes`.

Exactly the three authorized files are included: the new invalidation module, the repository planner entry, and the new invalidation tests. `git diff --check` and staged `git diff --cached --check` passed; ordinary LF/CRLF notices were the only messages. Final status contains only the pre-existing unstaged plan edit. This report and the progress ledger remain uncommitted; no source data, SQLite/WAL/SHM, outputs, push, merge, or plan/ledger completion update is included.

Status: **DONE — ready for the parent's independent review**, not an accepted/completed plan task. There is no unresolved correctness finding from the implementer's self-review. Retained limitations are the approved explicit full-rebuild fallback for insufficient historical detail, inherited source-fingerprint costs, and Task 11's separate production/20–23-member/full-suite acceptance. Future worktree test runs require an execution context authorized to create the fixture's C: worktree temporary directories; the default sandbox here is not such a context.

## Fix round 1 — aggregate attribution completeness

The independent review of candidate `2bdb21512e991f4398af4bb9fee335caa34e9ac2` reported one Important finding and no Critical finding; that candidate was **not accepted**. A visible base or policy difference incorrectly excused a changed whole-batch seal even while another pending member's omitted evidence could have changed. The prior handoff's no-unresolved-finding statement was an implementer self-review result, superseded by this independent finding.

Four pure test methods were added before changing production behavior: simultaneous visible consensus plus hidden pending base change; visible cap plus hidden pending valuation change; exact source-path matching (unknown sibling and nested paths); and a positive control for complete retained evidence with changed policy/valuation hash and canonical seals. The existing thirteen scope tests were retained.

Actual RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_invalidation.FormalInvalidationScopeTests -v
```

Result before production edits: **Ran 17 tests in 0.036s; FAILED (failures=4); exit 1.** The two reviewer cases and both exact-path subcases failed specifically because `full_rebuild` was false. The positive control and all thirteen prior tests passed.

The minimal fix requires both authenticated D1 populations to be complete before using visible family-local changes to explain aggregate seal changes. D1's genuine producer enforces that a `ready` member retains 22 base and three adjusted Stage C slots; pending rows may omit original metrics and adjusted inputs, so no batch-wide completeness is inferred from a different member's local change. Changed aggregates with any such uncertainty continue to emit deterministic `unlocalizable_upstream_change` and rebuild all current members. The readiness check is performed only inside the private arithmetic core after the repository's unchanged historical/current artifact and capability authentication, not on caller-supplied manifests.

Only the six exact top-level D1 seal paths (`batch.{base,policy,valuation}_batch_hash` and corresponding `_batch_canonical_sha256`) can be attributed to known retained source families. A similarly prefixed sibling or nested source is not automatically treated as the same provenance. Stage C's transitive base/policy seal churn is still localized when both complete retained populations establish that no other member input is omitted. No schema, repository authority, or Task 9 recovery code changed in this round.

Actual targeted GREEN, same command after the production edit: **Ran 17 tests in 0.042s; OK; exit 0.** Both requested regressions, path-specific negative cases, complete-ready positive control, and all thirteen prior scope tests pass. `git diff --check` passed (only ordinary LF/CRLF warnings); status shows the two allowed changed code/test files and the untouched pre-existing plan edit.

Code/test freeze was reported to the parent immediately after this GREEN. The implementer has not launched a genuine suite; the parent owns the final exact affected run through the verified authorized main execution path to avoid the previously diagnosed C: temporary-directory sandbox retry loop. Final exact verification and the fix candidate commit are pending below.

### Fix round 1 final exact verification — GREEN

The parent ran the frozen fix code through the authorized main path:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_invalidation tests.test_formal_final_repository -v
```

Actual parent-supplied result: **Ran 34 tests in 127.318s; OK; exit 0; zero failures, errors, or skips.** This includes twenty invalidation tests (three genuine repository/reuse tests and seventeen pure scope tests) plus fourteen accepted repository regressions. No production or test edits occurred after the freeze, and no further tests were run after this result. This supersedes the prior candidate's 30-test GREEN for the fix-round code. The previously diagnosed temporary-directory authorization issue was avoided through the supported main execution path without fixture, ACL, or product changes.

### Fix round 1 candidate commit and status

Candidate commit: **`84c4e046f854c8fa7f493d9afd1e3010809cced5`** — `fix: require complete formal invalidation evidence`.

Only `ashare_pipeline/formal_final_invalidation.py` and `tests/test_formal_final_invalidation.py` changed in this commit (80 insertions, six deletions). The authorized repository file required no additional edit. Both unstaged and staged `git diff --check` passed; the staged file list was inspected before commit. Post-commit status contains only the pre-existing unstaged plan edit. Plan, report, and ledger remain uncommitted; no push or merge occurred.

Status: **fix-round candidate ready for independent re-review**, not accepted or plan-completed. The reviewed Important finding is addressed by tested completeness and exact-path guards. Remaining intentional limitation: an aggregate change with any unproven population completeness conservatively rebuilds all current members rather than guessing a narrower scope; fully retained ready populations preserve precise local/cohort behavior. No additional implementer correctness concern is currently identified.
