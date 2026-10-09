# Stage D thin runner acceptance evidence

## Performance acceptance completed (2026-10-09)

All three tests in `tests.test_formal_final_performance.RunnerPerformanceTests`
passed in separate fresh processes on commit
`66d25618d1efe4545ae0dd5c3c3c75d9f793c9d0`. Start and finish revisions were
identical. The driver completed at `2026-10-08T15:29:57.489536+00:00`
(19:29 in Asia/Tbilisi), with state `passed` and all exit codes zero.

Each process used `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest -v`
followed by the full test identifier below, from the Stage D worktree.
`TMPDIR`, `TEMP`, and `TMP` were set to `D:/Projects/AShareQiheng/.tmp`;
`PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` were set before imports.

| Test (prefix: `tests.test_formal_final_performance.RunnerPerformanceTests.`) | unittest seconds | Driver seconds | Result |
| --- | ---: | ---: | --- |
| `test_each_stage_is_built_once_and_diagnostics_do_not_change_result_hash` | 3829.467 | 3830.640 | 1 test, OK |
| `test_source_batch_parses_and_cohort_sorts_have_structural_bounds` | 7353.612 | 7359.438 | 1 test, OK |
| `test_rebuild_appends_once_and_revalidates_even_when_no_input_changed` | 4142.911 | 4146.078 | 1 test, OK |

The structural profiler recorded each observed cohort sort exactly once,
each pool sort exactly once (`strong=1`, `wait=1`), and each observed source
batch parse per stage exactly once. Stage C recorded six cohorts/sorts,
23 securities, 69 valuation rows, one group-index build, one registry full
parse, and zero full financial rederivations. Broader observed counts were
7984 registry loads, 207 financial rederivations and six source checkpoint
rechecks; these counts are diagnostics, not a claim that all repeated
validation has been eliminated. No wall-clock performance threshold is claimed.

An initial interactive run was interrupted to switch to durable logging;
it is not counted as a passing test. The completed three-process run above
supersedes only the performance rerun gap stated in the historical section
below. The two historical combined wide commands remain unclaimed as GREEN.
This acceptance does not establish production data readiness or authorize
formal pool publication. Local driver status and logs are retained under
`D:/Projects/AShareQiheng/.tmp/stage-d-performance-2026-10-08/` and are not
included in this documentation commit.

## Current reviewed candidate (2026-10-06)

The current reviewed Stage D candidate is commit
`3c362c3187a779f3843677af790c85c7cae743e2` on
`codex/formal-final-stage-d`. Its feature commit is
`d08b7d2` (`feat: complete formal final scoring stage D`) and its follow-up
`3c362c3` preserves Git trust in the managed worktree without inheriting
caller-controlled `GIT_*` state. The user's plan and `.gitignore` changes are
not part of either commit. No data, SQLite, WAL/SHM, progress or generated
runtime report file was staged.

Independent review of the final trust patch reported **0 Critical, 0
Important and 0 Minor findings**. The accepted design binds official coverage
to the loaded project's exact `HEAD` and committed `ashare_pipeline` tree,
requires a clean `ashare_pipeline` source index/worktree, double-checks every actual tracked
source blob (including `skip-worktree` attacks), rejects malformed/nonzero or
stderr-producing Git calls, strips inherited Git control variables, and binds
official `code_version` to the coverage revision. Repository and runner gates
capture the relevant coverage method identities; the post-write boundary
rechecks workspace and provenance without hashing the transaction's own DB/WAL.

Post-review verification on the committed source tree:

- `tests.test_formal_workspace_trust`: **13 tests, 0 failures/errors/skips,
  OK**. The post-commit run took 48.007 seconds; the managed-worktree
  `safe.directory` compatibility revision was subsequently re-run by the
  implementer and independent reviewer with all 13 tests passing.
- Genuine official coverage gate:
  `OfficialCoverageBoundaryTests.test_signed_root_exact_requirement_enumeration_and_provenance_can_be_ready`
  — **1 test, 146.568 seconds, OK**.
- Genuine official candidate remains preview-only and never publishes V9:
  `test_official_candidate_is_still_preview_ready_and_never_v9_published`
  — **1 test, 8458.378 seconds, OK**.
- Retained source/registry row tampering is rejected:
  `test_source_and_registry_row_tamper_reject_retained_manifest`
  — **1 test, 2860.392 seconds, OK**.
- A legitimate financial generation correction appends a trusted rebuild and
  preserves history:
  `test_z_legitimate_financial_generation_correction_appends_trusted_rebuild`
  — **1 test, 4452.666 seconds, OK**.

The earlier nine-test suite7 result below remains valid historical evidence
for the pre-final-review implementation, but the full three-test performance
module was **not rerun after** the workspace/code-version hardening. Its
structural assertions and the current focused/long-chain results are recorded
separately; no current-HEAD performance-wide GREEN is claimed. Likewise, the
brief's two wide commands were verified as split modules (and the Stage D
combined process was interrupted after many passing modules to avoid host OOM),
so this document does not relabel either exact combined invocation as GREEN.

All sections below are retained as chronological development evidence. Where
an older paragraph says work or review was still pending, this current section
supersedes it.

Task 11 suite7 acceptance was run at HEAD
`d8540a613ea33736f333270a0b78e196739403ac` from
`C:\Users\Lenovo\.codex\worktrees\formal-final-stage-d\AShareQiheng`.
The launcher set `TMPDIR`, `TEMP`, and `TMP` to
`D:\Projects\AShareQiheng\.tmp` in that order before starting a fresh Python
process, so `tempfile` selected the writable D: location before test imports.
Ordered suite7 launcher (with the required PowerShell environment setup):

```powershell
$env:TMPDIR = 'D:\Projects\AShareQiheng\.tmp'
$env:TEMP = 'D:\Projects\AShareQiheng\.tmp'
$env:TMP = 'D:\Projects\AShareQiheng\.tmp'
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe D:/Projects/AShareQiheng/.superpowers/sdd/2026-09-28-formal-final-scoring-stage-d/task-11-integration-performance-runner.py
```

That runner changes into the Stage D worktree and loads each fully qualified
method in its explicit `TESTS` tuple into a `unittest.TestSuite`, then uses
`TextTestRunner(verbosity=2, failfast=True)`. The nine-method order below is
the tuple order confirmed by suite7 stderr, not ordinary two-module discovery
order. Cases 1–5 and 7 belong to
`tests.test_formal_final_integration.GenuineFullChainTests`; cases 6, 8 and 9
belong to `tests.test_formal_final_performance.RunnerPerformanceTests`.

An equivalent test-selection command, suggested for a future run after the
same environment setup and from the Stage D worktree, is:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_integration tests.test_formal_final_performance -v
```

This suggested command does not reproduce suite7's explicit order or fail-fast
behavior and is not the recorded suite7 launcher.

Captured suite7 evidence is in the ignored
`task-11-integration-performance-suite7.stderr.log` and
`task-11-integration-performance-suite7.stdout.log` under the Task 11 SDD
directory. The result was **9 tests, 0 failures/errors/skips, 12077.614s,
OK**. The nine ordered cases were:

1. `test_20_and_23_genuine_members_close_every_hash_and_pool_bound` — ok
2. `test_cross_frozen_security_and_registry_inputs_fail_closed` — ok
3. `test_source_and_registry_row_tamper_reject_retained_manifest` — ok
4. `test_official_candidate_is_still_preview_ready_and_never_v9_published` — ok
5. `test_z_legitimate_financial_generation_correction_appends_trusted_rebuild` — ok
6. `test_rebuild_appends_once_and_revalidates_even_when_no_input_changed` — ok
7. `test_final_recheck_revocation_leaves_no_torn_run_or_revoked_bc` — ok
8. `test_each_stage_is_built_once_and_diagnostics_do_not_change_result_hash` — ok
9. `test_source_batch_parses_and_cohort_sorts_have_structural_bounds` — ok

The stdout profiler recorded 55 cohort-sort events, each count 1; pool sorts:
strong 1 and wait 1. Four full source parses were each observed once: one
`d1_or_orchestration` batch (`b649a601508392f48a6a1d56152b6879d7cd198fcfc8a9fc489694e47a308079`)
and three `stage_c` batches (`4763b59d6c45883f1c03c3f3dfaf58fd1324b0cbded56133163b8d1a961a4dc7`,
`a7492bc5290d006a57e4c4ddcad5496429aa16589efce3fd4f0136ab578dc266`,
`f868061a87d7e8e547bdd31baaedb2a7a19b6428d7a489ed399b2798bae638a8`).
Observed events: financial rederivations 207, registry loads 7984, source
checkpoint rechecks 6. Stage C counts: base and policy batch full validations
1 each; cohort count 6; context count 69; eligible count 69; full financial
rederivations 0; group-index builds 1; peer count below 20 = 0; pending reasons
none; primary scope 3; registry full parses 1; scored inputs 69; secondary
scope 66; securities 23; sorts 6; valuation rows 69. Status counts:
adjusted 1, passthrough_not_applicable 66, passthrough_unaffected 2. These are
test-observer measurements for this suite and fixture, not production telemetry
or a wall-clock performance threshold.

Task 11 runs on `codex/formal-final-stage-d`, based on Task 10A commit
`d5750272517ceaded58382acb7c5c9a364071a02`. Resolve its exact implementation commit with
`git log -1 --format=%H -- ashare_pipeline/formal_final_runner.py`; the full ID
and handoff results are also recorded in the ignored Task 11 report. Code and
contract identities are caller-supplied; tests use `code_version="task11-test"`.

## Executed verification

Commands run from the Stage D worktree with
`D:/Projects/AShareQiheng/.venv/Scripts/python.exe`.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_runner tests.test_formal_final_integration tests.test_formal_final_performance -v
```

Initial RED: 13 tests, 13 assertion failures, 0 errors/skips, 0.105 seconds.
Every assertion failed because the thin runner was missing, before fixture
construction. No production runner existed before this RED.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_runner.RunnerMalformedInputsTests -v
```

Focused GREEN: 2 tests, 0 failures/errors/skips, 0.096 seconds.

Runner configuration hardening received an additional no-fixture RED: class
method replacement was not rejected (1 failure, 0 errors/skips, 0.257 seconds).
After hardening, the configuration/type/builder/unregistered-instance checks
passed: 5 tests, 0 failures/errors/skips, 0.110 seconds.
An additional producer-module-entry RED had 1 failure, 0 errors/skips, 0.394
seconds. It revealed that sealed producer wrappers have an internal `public`
function name; the guard now captures their actual exported module names.

Latest lightweight check after configuration hardening:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -B -m unittest tests.test_formal_final_runner.RunnerIdentityTests tests.test_formal_final_runner.RunnerMethodIntegrityTests tests.test_formal_final_runner.RunnerMalformedInputsTests tests.test_formal_final_eligibility.PureEligibilityRulesTests tests.test_formal_pool tests.test_formal_final_repository.FormalFinalRecoveryBoundaryTests tests.test_formal_coverage_manifest -v
```

Three further fixture-free trust RED assertions failed (0 errors/skips, 0.126
seconds): diagnostic-constructor replacement, dataclass field metadata mutation,
and an equality-spoofing method impostor. The guard now captures diagnostic
methods/code and field metadata, and compares class members by identity.

Coverage-helper freeze regression: 1 assertion failure, 0 errors/skips, 0.025
seconds. That initial helper fix bound the raw frozen representation; the later
genuine D1 run exposed that this was insufficient for the canonical UTC contract.
Helper identity RED: 1 test with 3 failed assertions, 0 errors/skips, 0.131
seconds. Captured bindings now also include `Path`, `Counter`, and
`MappingProxyType`; this does not change the build chain or purpose mapping.
Prior result: 41 tests, 0 failures/errors/skips, 0.407 seconds (prior 40-test
freeze-helper GREEN: 0.443 seconds). Genuine configured
instance mutation/copy/owner checks reuse the single baseline fixture; they
had not yet run against that hardening revision at this historical checkpoint.

Canonical fixed-freeze / field-level identity RED: 6 tests, 6 assertion failures,
0 errors/skips, 0.123 seconds. The pure tests cover equivalent CN/UTC instants,
changed/naive/malformed timestamps, all five D1 fields, exact member ordering,
membership and field-name-only errors. The runner now verifies the frozen time
is exactly the fixed instant and uses `2026-08-31T07:00:00+00:00` internally;
historical frozen/proof bytes and their hashes remain untouched. Coverage and
context test inputs use the same UTC contract. Latest lightweight GREEN:
46 tests, 0 failures/errors/skips, 0.956 seconds. AST checks for all four Python
modules passed. No long chain was restarted and no commit was created.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_runner.RunnerMalformedInputsTests tests.test_formal_final_eligibility.PureEligibilityRulesTests tests.test_formal_pool tests.test_formal_final_repository.FormalFinalRecoveryBoundaryTests tests.test_formal_final_migration -v
```

Lightweight GREEN: 30 tests, 0 failures/errors/skips, 106.059 seconds. Coverage
includes unrounded Decimal thresholds, both pool boundaries, canonical recovery
attacks, and preservation of V7 range schema/data and legacy scoring tables.

Read-only `ast.parse` syntax checks passed for all four new Python modules.
An attempted `py_compile` could not write its cache file in the restricted
sandbox (`Permission denied`); the replacement check required no cache.

The original small genuine suite started before fixture sharing was refactored.
Its incomplete-evidence first test exceeded two hours without returning a result,
despite continuing CPU growth; this is performance RED, not functional GREEN.
At 07:17:21 +04:00 (wall 2:15:01, CPU 5561.797 seconds), the requested exact
process stop encountered a PowerShell internal error. The validated child
PID 25256 and direct Python parent PID 11808 were stopped by their native
handles at 07:17:56.553 (wall 2:15:36.553, CPU 5583.62 seconds); both exits
and absence were confirmed. Session 93620 exited 1 without a test result.
No complete runner-suite result is
claimed. The revised small fixture uses `populate_final_inputs()` instead of
industry-only input. Periodic faulthandler stacks were used during the historical
runs below; the current test entry point has removed that timer entirely.
Functional execution has
no profiler; read-only stage profiling belongs only to performance tests.
The revised suite constructs one shared genuine
three-member baseline (with socket connections forbidden), one independent
deterministic replay, and one append-only trusted-diff rebuild: three complete
D1 builds total. Failed identity/purpose/DTO gates do not construct new chains.
Detached baseline diagnostics are saved independently of later failed attempts.
At 2026-10-03 05:58:18 +04:00, the original first test had elapsed 55:58,
with 2155.62 CPU seconds and continuing CPU growth. Its Python PID was 25256;
the current test was
`test_official_candidate_rejects_failed_gates_without_writing_an_official_mode_row`.
The process had loaded the pre-hardening runner/tests, so even its eventual
success will not establish the final revision's genuine acceptance. A stack
snapshot was unavailable: faulthandler was not enabled in that already-running
process and no py-spy/cdb/windbg/procdump attach tool was available. No tool was
installed or code injected into the process.

The first populated single-target baseline finished after 233.584 seconds with
0 tests and 1 setup error: its helper's default coverage freeze did not match
the genuine fixture. The exact runner identity gate rejected it before D1;
fixture setup completed, but this is not a functional assertion RED or GREEN.
Its ignored diagnostic log is retained. After the separate effective helper
RED/GREEN above, only the same single baseline target is retried; replay and
rebuild are not launched before that result.
The retry started at 07:27:18 +04:00, child PID 3748/direct parent PID 9516.
Population completed and a real D1 call was observed by 07:31:57. Its first
300-second stack showed snapshot path/manifest validation during current
financial fact and feature checking. The ignored stack log is not a committed
artifact. This process loaded the revision before the final three helper
bindings; its result will not alone verify that later guard addition.
That globally profiled retry was stopped at 07:45:38.091 +04:00, wall 18:20.091,
CPU 727.047 seconds, only D1 entry observed. Exact child 3748/direct parent 9516
exits and absence were confirmed. Its snapshots included the observer itself;
global profiling contaminated functional timing. It is diagnostic non-GREEN,
not a functional baseline or speed claim. That sole retry had no
`sys.setprofile`/stage observer, retaining only periodic faulthandler. Functional
phase times come from `runner.last_diagnostics` after success.

The unprofiled single target (child 28724/direct parent 11260, start 07:46:45
+04:00) finished in 1261.473 seconds with 0 tests and 1 setUpClass error. Genuine
D1 completed, then runner identity failed before D2/commit; no functional GREEN
or receipt is claimed. At 08:07:29 it still had 906.31 CPU seconds. Both processes
are absent. The exact discrepancy was only `as_of_utc`: historical frozen
`2026-08-31T15:00:00+08:00` versus D1's equivalent canonical UTC. Root,
frozen-input hash, universe hash and sorted membership agree by the existing
producer contracts. The minimal fix above requires parent approval for another
single-target genuine run; the ignored diagnostic log is retained.

The approved UTC single-target retry (session 37107, child 18844/direct parent
3236, start 08:20:45 +04:00) exited 1 at its first 300-second stack, without a
unittest verdict or receipt. Its combined PowerShell output log is 282 bytes,
last written 08:25:51, ending in an incomplete `File` line. A live sample at
08:25:07 was wall 4:22.476/CPU 179.219s. Read-only investigation found no matching
Application 1000/1001 crash event, Python reliability record or recent Python WER
directory; no matching process-exit audit was available. Disk space and available
memory were adequate. No test kill/exit timer or external termination by this
agent occurred; separate native child exit codes were unavailable after exit.
Original session polling had a roughly 3–4 minute gap, not a proven >5 minute
gap. Host idle/session recovery or output-boundary interruption was a hypothesis,
not an established business error or unique root cause.

The parent-approved recovery used native `cmd.exe` stdout/stderr redirection into
two separate ignored logs, with continuous polling of original session 82302 and
same-cycle CPU/working-set/private-memory sampling. Child 20796/direct Python
parent 21448/cmd parent 23404 started at 08:30:42 +04:00. It crossed the earlier
termination point, completed periodic stacks, and passed the sole target:
`RunnerBoundaryTests.test_preview_accepts_genuine_test_root_and_records_explicit_blockers`.
Result: **1 test, 0 failures/errors/skips, 2133.288 seconds, OK**, session exit 0.
All three exact process IDs were confirmed absent afterward. No other heavy
fixture ran in parallel. Success supports the recovery hypothesis but does not
uniquely establish an idle reaper as the cause of the earlier exit.

Actual runner stage durations (seconds): identity 1.9183715999824926;
D1 1903.1622190999915; D2 0.9009510999894701; D3 2.000556000013603;
final recheck 4.21628610001062; atomic commit 37.08851380000124. Total unittest
time includes fixture population and work outside these timed boundaries.
Observed counts: members/eligibilities 3; D1/D2/D3 builds each 1; identity checks
2; final batch rechecks 4; pool orderings 2; scorecards, retained metrics/slots/
cohorts, vetoes, pool qualifications/selections and cap skips all 0. These zeros
describe the real incomplete three-member fixture, not unavailable internal
parse/rederive/recheck instrumentation. All three final states are
`pending_evidence`. Receipt status is `blocked`, with `pending_evidence`,
`test_registry_not_official`, `v9_release_not_implemented`; it conveys no official,
release, coverage or V9 authority. Canonical result hash:
`e76c0fc50d0a5fd5bcf3a82d085d4a0bb03f3b7fad9e383727124846bb5d3ce0`.
This single-target GREEN does not establish the other shared-class attacks,
independent replay/rebuild, 20/23 integration, official success or performance
acceptance. No implementation commit has been made.
After recording the recovery evidence, the full lightweight command above was
rerun: **46 tests, 0 failures/errors/skips, 1.214 seconds, OK**. AST checks passed
for all four Python modules, and `git diff --check` passed (only existing user
file line-ending warnings). The index remains empty; the user's plan and ignore
file changes remain untouched and unstaged.

The subsequent no-fixture MethodType boundary RED ran one test with five failed
assertions, 0 errors/skips, 0.416 seconds. Real configuration access accepted
callable impostors carrying the genuine bound method's `__self__` and `__func__`
for frozen lookup, commit, trusted diff and loader, and ignored replacement of
the then-unprotected `MethodType` binding. The smallest fix requires
`type(current) is MethodType` and captures that binding in the existing authority
guard. Normal real bound methods still pass configuration access before/after
each attack. The test uses memory-only repository configuration (no database
initialization, published input repository, signature or proof) and never calls
run/build/commit; it verifies no database file was created. No authority closure
is edited or proof validity cached. Final lightweight GREEN: **47 tests,
0 failures/errors/skips, 1.089 seconds, OK**. AST all four modules and diff-check
passed. The earlier genuine single-target GREEN predates this minimal MethodType
hardening; it is not latest-revision full-chain acceptance.

All 12 `RunnerBoundaryTests` methods share one genuine fixture and baseline in
one class invocation. The expected actual D1 build count is three: one in
`setUpClass`, one independent replay, one trusted-diff rebuild. The other ten
methods add no D1 build. Running only those ten methods together would still
construct one genuine baseline; the completed single-target process has closed
its fixture and cannot be reused as proof authority in another process. No next
heavy invocation was then authorized, with the non-GREEN result below.

### Shared-class interruption and timer removal

The full 12-method class invocation used whole-process socket denial, native
separate stdout/stderr ignored logs and continuous original-session polling.
The first launcher quoting error ended before any fixture; the corrected stdin
launcher started session 94670, Python child 23608/direct parent 15944/cmd 4884
at 09:22:19 +04:00. Fixture population returned, but the baseline run did not.
The wrapper exited 1 without a unittest verdict, receipt or started test method.
All three exact process IDs and the external sampling process were confirmed
absent. Last live sample: wall 19:53.366, CPU 710.5625 seconds, working set
94,855,168 bytes, private memory 83,189,760 bytes. Stderr was 14,035 bytes, last
written 09:42:35.754 +04:00 (about 20:16 after launch).

Its first three 300-second dumps contained 35/31/34 complete frames ending at
the stdin launcher. The fourth contained one `json.encoder.iterencode` frame
and ended mid-line in literal `  File `, without a newline. The earlier failed
single target also stopped mid-dump. In contrast, the recovery GREEN had seven
dumps with 29/1/33/38/6/31/34 complete frame lines and no unfinished `File` line;
five reached the launcher, while two shorter stacks do not establish complete
call-chain coverage. Scoped Application 1000/1001 and recent Python WER checks
found no matching crash event. Separate logs and continuous polling did not
prevent this interruption, so an idle reaper is not a sufficient explanation.
Timer output is a highly correlated trigger, not a proven CPython/host root
cause. This attempt is diagnostic non-GREEN, not a business assertion failure;
three-D1, replay hash, rebuild and failure-isolation acceptance remain pending.

Parent-approved test-only infrastructure TDD: the new no-fixture test
`test_shared_setup_never_schedules_a_background_traceback_timer` intercepted
both faulthandler timer entry points and stopped immediately before genuine
fixture construction. Effective RED: 1 assertion failure, 0 errors/skips,
0.125 seconds. Minimal fix removes the timer import, scheduling and cleanup
entirely; no environment-variable default re-enables it. Patch contexts and a
`finally` restoration preserve all class attributes, list contents and globals.
The production runner was not changed by this fix.

The three actual run sites now flush start/end markers and print their returned
real diagnostics/counts/timings and canonical hashes, never signature/source
material. Each returned run asserts `d1_builds == 1`; teardown prints the actual
per-run counts and asserts their sum is three when all three returned. A
single-target invocation remains supported and reports its actual smaller sum.
Future functional observation uses only external CPU/memory sampling and these
stage markers, not a background traceback timer or global profiler.

Latest lightweight command above: **48 tests, 0 failures/errors/skips,
0.359 seconds, OK**. Read-only AST checks passed for all four Python modules;
diff-check passed with only unchanged user-file line-ending warnings; index
empty. At that checkpoint no timer-free heavy run or commit had been started.

### Timer-free shared-class GREEN

The subsequently authorized complete class ran once via stdin with whole-process
socket denial and failfast, without faulthandler or any profiler. Native stdout
and stderr went to new separate ignored `task-11-runner-class-timer-free-*` logs.
Original session 35552 returned exit 0: **12 tests, 0 failures/errors/skips,
2725.744 seconds, OK**. All configuration/ownership/method/copy/identity gates,
official rejection, preview blockers, trusted append-only rebuild, independent
hash replay, legacy/DTO rejection and failure isolation passed.

Actual returned D1 counts were `[1, 1, 1]`, total **3**. Actual stage durations
in seconds, in execution order:

| Stage | Baseline preview | Trusted rebuild | Independent preview |
| --- | ---: | ---: | ---: |
| identity | 1.1405561999999918 | 0.7379533000057563 | 2.3185684999916703 |
| D1 | 810.6544373999932 | 808.8937742999988 | 814.3545212000026 |
| trusted diff | not invoked | 1.711817000003066 | not invoked |
| D2 | 0.12118969997391105 | 0.2751026999903843 | 0.09727689999272116 |
| D3 | 0.25383689999580383 | 0.8820817999949213 | 0.21137080001062714 |
| final recheck | 0.8124370999867097 | 2.694821700017201 | 0.6619122999836691 |
| commit | 9.63974660000531 | 36.11860640000668 | 9.3714539000066 |

Baseline and independent preview result hashes were equal:
`c8de3e26fb3db0d7ce06fb9b767ae67be8a896b03744df0b241d1e4edc58e0c9`, with shared
input manifest `5da2ac4bac8825dff5bcf112e33deec38728bae96ad20a614236a469d95a0e56`.
The trusted rebuild appended a distinct run, preserved the prior run, changed
input manifest to `7b3e7b9704536cb80e8620b6f734842b7c34835a4fadf778aca718a58a48cb21`,
and returned result `aafd205e5204e48e207a298d32676ee426aa1bef8fc38f22a8993e9d05e15a3c`.
Its trusted plan and revoked-coverage failure assertions passed. This small
fixture remains `blocked`, conveying no official/release/coverage/V9 authority.

Python leaf 25144, launcher 3868, cmd 2064 and exec parent 14728 were all
confirmed absent. The external resource-observer session was gone; a scoped
native query excluding the diagnostic query found no matching observer command.
Last live sample: wall 2716.4119812 seconds, CPU 2209.640625 seconds, working set
224,788,480 bytes, private memory 213,815,296 bytes. No parallel heavy fixture or
retry was started. Timer-free survival and complete GREEN support the timer-
trigger hypothesis, not a unique host/CPython mechanism or timing attribution.

Monitoring deviation: 176 audited polling rounds included four request gaps
above the required 30 seconds: **40.259, 33.257, 31.577 and 33.107 seconds**,
following phase-log reads. The recorded maximum was 40.259 seconds; this is not
strict <=30-second compliance. No code or commit changed during this run.
20/23 integration, official success, legitimate correction, structural
performance and full affected regressions remain pending.

## Remaining brief-wide regression runs

Suite7 establishes the integration/performance subset above. The brief's
Step 6 Stage D GREEN command and Step 7 affected-regression command have not
each been run as a single invocation; their evidence remains pending independent
terminal-review decision. Do not label either wide command GREEN based on suite7.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture tests.test_formal_final_score_inputs tests.test_formal_final_score_input_guards tests.test_formal_final_scoring tests.test_formal_final_scoring_guards tests.test_formal_final_eligibility tests.test_formal_final_eligibility_guards tests.test_formal_pool tests.test_formal_pool_guards tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_final_migration tests.test_formal_final_repository tests.test_formal_final_atomicity tests.test_formal_final_invalidation tests.test_formal_final_runner tests.test_formal_final_integration tests.test_formal_final_performance -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_feature_repository tests.test_formal_metric_engine tests.test_formal_metric_context tests.test_formal_score_inputs tests.test_formal_scoring tests.test_formal_policy_repository tests.test_formal_policy_integration tests.test_formal_valuation_batch tests.test_formal_valuation_ranking tests.test_formal_valuation_integration tests.test_state_store -v
```

The suite7 test `test_20_and_23_genuine_members_close_every_hash_and_pool_bound`
passed its 20/23 genuine-member acceptance, and the official-candidate,
legitimate-correction, and source-row-tamper cases listed above also passed.
Those results do not substitute for either remaining wide regression command.
No production coverage audit is claimed by these fixtures.

## Diagnostics and structural performance

Immutable runner diagnostics record phase timings; members, retained metrics,
slots/cohorts, rebuilt members, states/reasons, vetoes/qualifications, pool
counts, industry/capacity skips, pool output orderings, and observed runner
boundary invocations. `retained_cohorts` counts only cohorts present in D1
slots, not hidden pending upstream cohorts. Diagnostics do not enter canonical
input-manifest/result hashes.

The runner's public input interface does not expose retained Stage C batch/
repository internals. Parse/rederivation/recheck counts are not invented in its
DTO. The performance tests use a read-only `sys.setprofile` observer and stable
producer code objects to count full source-batch JSON parses, registry loads,
financial feature rederivations, source checkpoint rechecks, non-V/C cohort
sorts and both pool sorts. Stage C's existing ranking summary is observed via
return-frame locals. No captured authority is replaced or verification skipped.
Tests also count the real atomic-writer call and compare append-only run counts.
Event lookup uses `id(code)` followed by `is` confirmation, avoiding recursive
code-object hashing for every frame. Profiling still adds overhead; profiled
elapsed time is not a functional wall-clock threshold.
The final-recheck revocation attack observes the original pool selector's return
event, revokes genuine coverage once, and verifies no run was appended; it does
not replace the selector captured by the runner's identity guard.

Tests assert at most one full parse per source batch per observed phase and at
most one sort per cohort. Suite7's exact structural observations are recorded
above. Wall-clock timings have no hard pass threshold; the profiled 12077.614s
suite duration is descriptive and not a pass criterion.

## Review boundaries and production blockers

Self-review covers each boundary separately:

- Specification: preview, official candidate and trusted append-only rebuild
  APIs return the existing immutable receipt and detached diagnostics.
- Trust: fixed mappings are `test_preview -> test` and
  `official_candidate -> official`. Coverage/frozen/root identities close before
  D1; D1's existing producer closes B/C identities before minting. Plain mappings,
  recovered DTOs and legacy score arguments confer no proof authority.
  Runner configuration uses registered weak references and read-only slots;
  copy/pickle/inheritance/method replacement are rejected. Every invocation
  checks captured type/function/code identities, repository/loader ownership,
  database path, versions, and bound instance entry points. Only the original
  runner execution frame can update its detached diagnostic reference.
- Atomicity: diagnostics read live proofs before the durable boundary. The
  authenticated repository alone prepares and commits D1-D3 children, with
  transactional source rechecks. Runner final-recheck failure precedes any run
  write. Old runs and independent B/C proofs remain independent.
- Economics: existing D1/D2/D3 and pool boundaries own every calculation; the
  runner contains no economic formula or direct SQL.
- Performance: every rebuild creates fresh proofs. The trusted diff describes
  impact without caching a validity conclusion. Internal counters are measured
  by the test-side observer, not inferred from elapsed time.
- Versions: the writer persists V8. Complete runs are `preview_ready`;
  incomplete previews may be `blocked`. Official candidate rejects pending or
  out-of-scope evidence. Neither mode validates or publishes V9.

Independent terminal review and the two brief-wide regression invocations
remain outstanding. No production coverage audit is claimed by these fixtures.
Approved signed purpose=`official` contracts and complete SH/SZ/BJ coverage
remain required production gates. Both official pools remain unpublished
pending separate V9 validator/publisher/reporting work.

No database, WAL/SHM, raw user data, progress file or generated report is stored
with this evidence. Synthetic temporary fixture artifacts are untracked.
