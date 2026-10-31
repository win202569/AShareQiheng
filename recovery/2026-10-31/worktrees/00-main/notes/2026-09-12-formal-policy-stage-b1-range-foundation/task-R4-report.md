# R4 implementation report

Current checkpoint: FROZEN for controller acceptance. Final same-process four-module compatibility TERMINAL GREEN: 100 tests in 7067.269 seconds, OK, exit 0. Session `73320`, Python PID `35328` (venv launcher `34740`), start `2026-09-19T14:09:08+04:00` host-local time. Output `task-R4-compatibility.log`; code/tests remained frozen throughout. No owned test process is running. Full log read and all four post-run hashes confirmed unchanged; final verification handoff recorded below.

Latest result: all 100 completed OK, including the final transport-callback integrity regression. No failures, errors, or skips reported. Prescribed command was run once, without restart or duplicate suites.

Scoped fix-round review CLEAN (`task-R4-fix1-review-ba0def6.md`); controller checkpoint `ba0def62a4ffe45cb5e3bee41537ea1b79ff6de0`. Prior focused GREEN: session `83795`, 6 tests in 868.661 seconds, exit 0. All earlier evidence below is retained; its pending-review/compatibility statements are historical and superseded by this current checkpoint.

Fix 1 RED TERMINAL: session `32094`, exit 1, 3 tests in 326.730 seconds, 7 expected assertion failures. `task-R4-fix1-red.log` demonstrates source mutation still recorded retryable task failures, while original-request mutation and current-parent corruption still surfaced retryable/blocked classifications.

Focused run `39023` TERMINAL exit 1: 3 tests in 1100.321 seconds; snapshot subtype and actual subprocess cold resume OK. Callback integrity exception correctly propagated, but its subsequent SQL assertion assumed ordering by tied fixed timestamps: actual `[leased, verified]` versus expected `[verified, leased]`. Full output preserved in `task-R4-focused-green.log` despite its now-known non-GREEN result.

Subtype RED session `13355` terminal exit 1: one test, 18.912 seconds, expected failure because saved replay exposed `FormalRangeAcquisitionError`. Output `task-R4-subtype-red.log`.

Focused run 2 is TERMINAL, session `8215`, exit 1, 3 tests in 367.565 seconds: expiry guard and final permitted attempt OK; parent-replay callback regression FAILED as expected (`FormalTerminalSourceError not raised`). Output `task-R4-focused-2.log`.

Initial focused command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker -v`, partial output `task-R4-focused-1.log`. Owned Python PID `28156` stopped explicitly; session `9061` terminal exit -1, two completed OK, third interrupted. This superseded partial run is not GREEN. No production edits occurred while either affected process was active.

Distinct expiry RED command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_expired_attempts_exhaust_budget_before_another_fetch -v`. Full output `task-R4-expiry-red.log`: one test, 121.459 seconds, exit 1, expected assertion failure `verified != terminal_failed` on attempt 3 with signed maximum 2. Added after initial process loaded its 16 tests; no duplicate case was run. Later test-file insertions shifted traceback display line text, but the executed assertion/result and complete output are preserved.

Base: `3c3b3c12a6a5f8f6c98d054131e4a097cad710c4`, branch `codex/formal-v3-implementation`.
Worktree: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.

## TDD evidence

Command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker -v`

RED: exit 1; 16 tests, 18 assertion failures, 0.002 seconds. Tests fail because the worker fixture, worker module, and authenticated binding accessor are absent. Complete output: `task-R4-red.log` in this directory.

## Decisions and scope

Controller ruling: introduce a Source-owned terminal acquisition subtype only at live response validation/normalization, with authority rechecks before wrapping. Base terminal source errors and saved-evidence integrity failures propagate. No broad exception classification, network, production signing/data, dependency installation, or Git writes.

Focused expiry defect: enforce signed `retry_max_attempts` before transport for leased attempts beyond the limit, including prior expired attempts. The maximum itself remains allowed. Test clocks control only store/worker scheduling time, retaining genuine signature/raw/source checks. This avoids runtime-dependent retries and lease expiry in expensive fixture verification.

Self-review integrity defect fixed RED→GREEN: a callback during the parent reauthentication of an already-failed live parse could mutate the live source after its first recheck. Source and request are now rechecked again after parent replay, and integrity failure propagates. Shared parser/normalizer handling converts only the newly introduced acquisition subtype back to base terminal failure; the live response boundary deliberately reclassifies it only after authority checks. Pre-existing base terminal behavior remains unchanged.

Controller alone owns commits and the master plan edit. Implementation whitelist: worker module, worker tests, range fixtures, minimal source accessor/acquisition classification. Explicit task report and verification logs are local ignored task artifacts.

## Remaining

Controller acceptance/bookkeeping only. Scoped fix review is clean and the prescribed same-process compatibility run passed all 100 tests, including all 23 worker cases. Runtime concern remains documented separately; no performance changes were made under R4. No further suites are planned by this implementer.

## Implementation inventory

- `FormalRangeWorker.run_once()` leases one task, authenticates its request/binding, creates the genuine source, fetches outside store transactions, persists via the fenced producer attempt, and only then derives/enqueues the genuine successor. It never requests a previous calendar segment or sleeps.
- Retry diagnostics are typed (`source_retryable`, `source_blocked`, `source_terminal`, `attempt_budget_exhausted`). Backoff is exponential capped at signed timeout; blocked responses use signed cooldown. The signed attempt bound includes expired attempts. Terminal outcomes and attempts remain stored.
- `resume(request, refresh_generation=...)` uses exact enqueue identity, authenticates existing receipts, and follows genuine current page successors within signed `max_pages`, stopping at the first unfinished task. It makes no transport calls; a subprocess regression exercises the persisted-page/successor-enqueue crash gap.
- `range_request_binding` closes over the original request validator and exposes only a genuine authenticated binding. It does not mint requests, register objects, or trust caller JSON.
- Fixture changes are test-only fake transport response/error/callback controls and worker restart setup. Existing producer fixture APIs remain intact.
- Diagnostic dictionaries are JSON-serializable and expose task status/identifiers, never genuine handles or a coverage/completion claim.

## Initial implementation self-review checkpoints (historical)

Checked exception boundary placement: enqueue, lease, source construction, persistence, receipt replay, continuation and fencing errors are outside the operational catch. Base terminal exceptions propagate. No exception-string matching is used. Request/source authority checks remain the existing captured implementations.

Checked pagination/recovery identity: refresh generation is carried from the task, not substituted for upstream source version; verified-page continuation comes from current genuine observations; no detached ordinal arithmetic or worker database graph reconstruction is introduced.

Checked scope/data retention: only the four approved code/test paths and ignored task artifacts changed. The controller's master-plan checkbox remains outside implementer ownership. No Git writes, old DDL edits, real HTTP, production signing, production databases, scoring, quantified-event activation, user-data deletion, merge or push. The user-owned `tmpj4zv9_fq` was not touched. Synthetic fixture signatures and temporary test databases are the existing approved test path.

Self-review found no remaining known functional defect within this task after the focused fixes. The test assertion fix orders pages explicitly rather than relying on tied scheduling timestamps; it does not weaken the status/receipt assertions. `git diff --check` exit 0; Git emitted only existing LF-to-CRLF conversion warnings. HEAD is still the BASE; the implementer made no commits or index writes.

## Exact focused commands and terminal outputs

All commands ran from the worktree above. Complete stdout/stderr is preserved in the named logs in this task directory. Output-redirection wrappers preserved each Python exit code.

`task-R4-focused-2.log` (exit 1; 3 tests; 367.565 seconds; expiry tests OK, callback test RED):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_expired_attempts_exhaust_budget_before_another_fetch tests.test_formal_range_worker.FormalRangeWorkerTests.test_last_permitted_attempt_after_expiry_can_still_fetch tests.test_formal_range_worker.FormalRangeWorkerTests.test_parent_recheck_callback_cannot_relabel_source_mutation_as_remote_failure -v
```

`task-R4-subtype-red.log` (exit 1; 1 test; 18.912 seconds; replay exposed live subtype):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_snapshot_parser_cannot_emit_live_acquisition_classification -v
```

`task-R4-focused-green.log` (exit 1; 3 tests; 1100.321 seconds; snapshot subtype and cold resume OK, callback test failed only on tied SQL row order):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_snapshot_parser_cannot_emit_live_acquisition_classification tests.test_formal_range_worker.FormalRangeWorkerTests.test_parent_recheck_callback_cannot_relabel_source_mutation_as_remote_failure tests.test_formal_range_worker.FormalRangeWorkerTests.test_restart_recovers_persist_to_enqueue_gap_without_refetch -v
```

`task-R4-focused-final.log` (exit 0; 3 tests; 521.178 seconds; all OK):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_parent_recheck_callback_cannot_relabel_source_mutation_as_remote_failure tests.test_formal_range_worker.FormalRangeWorkerTests.test_parent_replay_terminal_error_during_fetch_is_not_operational tests.test_formal_range_worker.FormalRangeWorkerTests.test_success_queues_only_next_page_and_missing_page_keeps_first -v -f
```

Final prescribed compatibility command — run once after clean scoped review; 100 tests passed (initial pre-fix collection was 97):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_range_worker -v
```

## Initial frozen owned-file SHA-256 (superseded by fix-round hashes below)

| Path | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_range_worker.py` | `BF017A1927AE42E4B6EE1512AE5489FADB909F945EF65269E367256BF91F56CF` |
| `ashare_pipeline/formal_range_source.py` | `B8D9AFFDF9A254DCFE289AA380B2308E4746085AC26C1BC3ED3A1E11B596EB5D` |
| `tests/formal_range_fixtures.py` | `B881D2DCA4681688F6F76482940E7F4AC10E0B77DB7C34FA6361DED7C87A86F7` |
| `tests/test_formal_range_worker.py` | `2E9538571961348B42D3287F46FD6594CDC325FA56328F7550044013FBD6D587` |

## Observed runtime concern (separate from correctness)

The three-case `39023` integration run took 1100.321 seconds. It includes repeated authenticated pagination/current-parent replay and a fresh subprocess cold resume. No performance rewrite, authority bypass, or test restart was used to shorten it. Scheduling-clock isolation makes retry/expiry assertions deterministic; these tests do not establish completion within the default real-time 60-second lease or production throughput. Production collection remains out of scope.

## R4 fix round 1/5 — callback integrity on retryable paths

Base: `bc1d137d5eb40b1b56538ab3da905e6ad96fd368`.
Independent verdict: `task-R4-review-bc1d137.md`, Important finding: callback integrity failures can still become ordinary retry diagnostics.

Root cause verified: transport exceptions leave before `source_record(self)` and blocked/retryable response classification leaves before original-request/current-parent checks. `Store.fail()` fences the producer but cannot validate the original acquisition dependencies. The prior terminal-only reauthentication was insufficient.

Minimal fix: a private owner-held `require_acquisition_authority(source, request, previous)` authenticates original source and request, then current parent, then original source/request again after parent callbacks. Transport's generic and typed retry errors, retryable/blocked response errors, and the existing terminal response handler invoke that same sequence. Checks run inside exception handlers, outside the blocks that convert acquisition errors, so authentication failures propagate. The success path, worker catch boundary, persistence, and lease fencing are unchanged. Only `formal_range_source.py` and `test_formal_range_worker.py` changed in this round; the other two owned files remain unchanged.

RED command, session `32094`, `task-R4-fix1-red.log`: 3 tests in 326.730 seconds, 7 expected assertion failures, exit 1. Source mutation with timeout/typed retry/typed block incorrectly became three `retryable_failed` tasks; request mutation under 403/503 and current-parent raw corruption under 403 incorrectly surfaced ordinary source acquisition errors.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_transport_error_cannot_hide_source_callback_mutation tests.test_formal_range_worker.FormalRangeWorkerTests.test_retryable_response_cannot_hide_original_request_mutation tests.test_formal_range_worker.FormalRangeWorkerTests.test_blocked_response_cannot_hide_current_parent_corruption -v
```

GREEN command, session `83795`, `task-R4-fix1-green.log`: TERMINAL, 6 tests in 868.661 seconds, OK, exit 0. Includes all new regressions, genuine unchanged timeout/backoff/attempt-limit and 403/429/challenge cooldown behavior, plus the post-parent callback regression for the shared helper.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_transport_error_cannot_hide_source_callback_mutation tests.test_formal_range_worker.FormalRangeWorkerTests.test_retryable_response_cannot_hide_original_request_mutation tests.test_formal_range_worker.FormalRangeWorkerTests.test_blocked_response_cannot_hide_current_parent_corruption tests.test_formal_range_worker.FormalRangeWorkerTests.test_timeout_retries_only_until_signed_attempt_limit tests.test_formal_range_worker.FormalRangeWorkerTests.test_blocked_responses_use_signed_cooldown_without_evidence tests.test_formal_range_worker.FormalRangeWorkerTests.test_parent_recheck_callback_cannot_relabel_source_mutation_as_remote_failure -v -f
```

Fix-round self-review complete. The helper closes over the existing source/request/parent validators; request validation still authenticates its original binding/config and source validation checks its sealed dependencies. `FormalSourceBlocked` inherits `FormalRetryableSourceError`, so the response catch includes blocked classifications. All helper invocations occur inside error handlers, outside acquisition conversion; an integrity exception cannot be recaught by a sibling handler. The shared sequence repeats source/request validation after parent replay callbacks. Success ordering, worker/store behavior, public parser contracts, and lease fencing are unchanged. Regressions use genuine signed fixture authority and saved raw corruption, not mocked verification. Source mutation is checked through the worker and leaves tasks leased with no attempt diagnosis/snapshot; request/parent variants exercise the source boundary directly. No additional known defect identified in this scoped review.

`git diff --check`: exit 0 (only LF-to-CRLF warnings). Working tree diff from `bc1d137` contains only this round's source/tests changes plus the unrelated controller-owned master plan. No Git writes by implementer. No full compatibility command was launched. No tests or runtime checks were bypassed to improve performance.

Collection-only command (exit 0, output `100`, no test bodies executed):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -c "import unittest; modules = ['tests.test_formal_range_contract', 'tests.test_formal_range_source', 'tests.test_formal_range_store', 'tests.test_formal_range_worker']; print(unittest.defaultTestLoader.loadTestsFromNames(modules).countTestCases())"
```

Frozen fix-round owned-file SHA-256:

| Path | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_range_worker.py` | `BF017A1927AE42E4B6EE1512AE5489FADB909F945EF65269E367256BF91F56CF` |
| `ashare_pipeline/formal_range_source.py` | `7B36D3929A606B7D1BE626F7305086C46A177F85BED93AC830DBE54BA00CBFC9` |
| `tests/formal_range_fixtures.py` | `B881D2DCA4681688F6F76482940E7F4AC10E0B77DB7C34FA6361DED7C87A86F7` |
| `tests/test_formal_range_worker.py` | `D4B45CAD45C30967C44C2B6652D9CB2E88814637CAC444FF493A2ECF65AB6E4E` |

Remaining concern is validation breadth/runtime, not a claimed new correctness finding: six focused tests took 868.661 seconds; this is not production throughput or default lease-duration evidence. The final four-module compatibility run remains gated on controller review/resume. Hand-off status: DONE_WITH_CONCERNS for this scoped fix round, not acceptance of R4 or all compatibility cases.

## Final compatibility verification and acceptance handoff

Controller resumed verification after clean scoped review at `ba0def62a4ffe45cb5e3bee41537ea1b79ff6de0`. One invocation, all four modules in the same unittest process:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_range_worker -v
```

Actual wrapper redirected stdout/stderr with `*> .superpowers/sdd/2026-09-12-formal-policy-stage-b1-range-foundation/task-R4-compatibility.log`, captured `$testExit = $LASTEXITCODE`, displayed the tail, and returned `exit $testExit`. Log was absent before launch; no previous output was overwritten. Session `73320`, runtime Python PID `35328`, venv launcher PID `34740`; start `2026-09-19T14:09:08+04:00` host-local. Log final write `2026-09-19T16:06:55+04:00`; terminal exit collected and full output read. PIDs are no longer present. The read-only PID-absence query itself returned 1 because neither process existed; this is separate from the actual unittest session exit 0.

Terminal output:

```text
----------------------------------------------------------------------
Ran 100 tests in 7067.269s

OK
```

Result: exit 0; 100/100 OK (16 contract, 31 source, 30 store, 23 worker), no failures, errors or skips. Full output is `task-R4-compatibility.log` in this directory, 18,868 bytes. The cold-resume subprocess is part of its planned worker test; no extra suite, restart, profiler or code/test edit was introduced while this run was active. All incremental observations and original RED/GREEN evidence remain preserved.

Post-run `git diff --check`: exit 0, only the controller master-plan LF-to-CRLF warning. The four owned paths have no working-tree diff from the clean review checkpoint; index is empty. Only the unrelated controller-owned master plan is dirty. No Git writes, production data/network, optimization, or subagents were used by this implementer.

Post-run SHA-256 (all match pre-run frozen hashes):

| Path | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_range_worker.py` | `BF017A1927AE42E4B6EE1512AE5489FADB909F945EF65269E367256BF91F56CF` |
| `ashare_pipeline/formal_range_source.py` | `7B36D3929A606B7D1BE626F7305086C46A177F85BED93AC830DBE54BA00CBFC9` |
| `tests/formal_range_fixtures.py` | `B881D2DCA4681688F6F76482940E7F4AC10E0B77DB7C34FA6361DED7C87A86F7` |
| `tests/test_formal_range_worker.py` | `D4B45CAD45C30967C44C2B6652D9CB2E88814637CAC444FF493A2ECF65AB6E4E` |

Final self-review: scoped callback-integrity finding is addressed, independently re-reviewed clean, and the complete prescribed compatibility command passed on unchanged reviewed files. No known outstanding R4 correctness defect. Runtime remains a concrete concern: 7067.269 seconds (about 117.8 minutes) for the full suite; this is not production throughput evidence and does not establish completion within the default real-time lease. No authority checks or tests were weakened to shorten execution. Status: DONE_WITH_CONCERNS (runtime), frozen for controller acceptance; implementation/verification work for R4 is complete, and any subsequently approved performance work is separate.
