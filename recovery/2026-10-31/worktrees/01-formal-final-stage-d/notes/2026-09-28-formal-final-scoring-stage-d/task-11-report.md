# Task 11 implementation handoff (suite7 partial acceptance recorded)

Status at the original handoff snapshot below was acceptance-pending. Update at
HEAD `d8540a613ea33736f333270a0b78e196739403ac`: suite7's integration/performance
explicitly ordered runner passed 9/9 in 12077.614s, including genuine 20/23, official-candidate,
legitimate-correction and structural-performance cases. The full brief Step6
and Step7 wide commands were not run as single invocations and remain pending;
independent terminal review remains outstanding. Approved signed purpose=`official` production
contracts and complete SH/SZ/BJ coverage remain genuine blockers, and V9 remains
unvalidated/unpublished. Historical entries below retain the evidence and
status known at each checkpoint.

Workspace: `C:\Users\Lenovo\.codex\worktrees\formal-final-stage-d\AShareQiheng`.
Branch: `codex/formal-final-stage-d`.
Base/current HEAD: `d5750272517ceaded58382acb7c5c9a364071a02`.

## Scope and implementation

Ruling: use this explicitly requested ignored report as the task record, not a
new progress ledger or workspace script — the parent limits deliverables and
requires preservation of its existing plan/ledger — no parent progress is changed.
Ruling (parent): expose only real runner observations; internal full parse,
financial rederive and source recheck counters belong to non-invasive test-side
profiling — no existing production public interface is expanded — heavy numerical
acceptance remains pending rather than being filled with zeros.
Ruling (parent): allow the existing writer's `blocked` result for incomplete
preview evidence; official candidates require complete evidence — changing the
writer solely to force `preview_ready` is outside Task 11 scope.
Ruling (parent): run only one genuine fixture at a time, share the small baseline
and permit at most three D1 builds in the revised small suite — CPU growth alone
is not a deadlock — original-suite output cannot verify the later hardening.

Only the five brief-authorized deliverables were created: thin runner, runner/
integration/performance test modules, and evidence README. Existing production
modules were not edited. Existing plan progress and `.superpowers/sdd/.gitignore`
changes were preserved unstaged. This report is ignored and must not be committed.
No database, WAL/SHM, original user data, progress or report file is staged.

The runner consumes exact configured StateStore, genuine D1 input repository,
authenticated run repository and signature verifier. Purpose is fixed by mode:
`test_preview -> test`, `official_candidate -> official`. It first closes frozen/
root/member/coverage identities, then invokes D1 (whose existing producer owns
B/C closure), D2, D3 eligibility and pool selection, final identity/proof recheck,
and the sole atomic repository writer. Trusted rebuild diff precedes D2/D3 and a
fresh append-only run; every build revalidates rather than caching validity.

Runner configuration is single-use registered, immutable, non-inheritable,
non-copyable and non-pickleable. Every access checks captured type/function/code/
original-module-entry identities, repository/loader ownership, path/version and
bound methods. User-written detached diagnostics cannot affect execution; only
the original run frame updates the private diagnostic reference. The runner has
no economic formula, SQL or network access, and accepts no legacy/pre-policy/
recovery DTO as genuine input. Complete candidate receipts remain V8
`preview_ready`, incomplete previews may be `blocked`; neither mode is V9
validated/published and test roots never gain official authority.

## TDD and executed verification

All commands used `D:/Projects/AShareQiheng/.venv/Scripts/python.exe` from the
Stage D worktree. Exact full commands and pending acceptance commands are in
`docs/superpowers/evidence/formal-final-stage-d/README.md`.

- Three requested modules before implementation: 13 tests, 13 assertion failures,
  0 errors/skips, 0.105s; missing-runner assertion RED before genuine setup.
- Initial malformed inputs GREEN: 2 tests, 0 failures/errors/skips, 0.096s.
- Light eligibility/pool/recovery/migration GREEN: 30 tests,
  0 failures/errors/skips, 106.059s.
- Immutable runner method RED: 1 failure, 0 errors/skips, 0.257s;
  subsequent no-fixture trust/malformed GREEN: 5 tests, 0 failures/errors/skips,
  0.110s.
- Original producer module-entry RED: 1 failure, 0 errors/skips, 0.394s.
  Initial fix still had 1 failure in a 23-test run (1.445s): sealed exported
  wrappers have internal function name `public`. Root cause was verified by
  read-only closure inspection. Capture uses actual exported module names now;
  corrected 23-test GREEN: 0 failures/errors/skips, 1.169s.
- Latest focused command: RunnerMethodIntegrityTests, RunnerMalformedInputsTests,
  PureEligibilityRulesTests, test_formal_pool, FormalFinalRecoveryBoundaryTests,
  test_formal_coverage_manifest: 39 tests, 0 failures/errors/skips, 0.858s
  (initial new-hardening GREEN 1.596s).
- Three additional trust RED assertions: 3 failures, 0 errors/skips, 0.126s;
  diagnostic constructor, mutable dataclass Field metadata, equality-spoofing
  method replacement. Minimal identity/code/metadata guard passes all three in
  the 39-test GREEN above.
- Additional standalone coverage tests: 11 tests, 0 failures/errors/skips, 0.206s.
- Coverage-helper freeze binding RED: 1 assertion failure, 0 errors/skips, 0.025s;
  initial helper-only fix used the raw fixture freeze; later real D1 exposed the
  CN versus canonical UTC representation mismatch. No gate is bypassed.
  Latest same lightweight suite: 40 tests, 0 failures/errors/skips, 0.443s.
- Helper identity RED: 1 test / 3 failed subtest assertions, 0 errors/skips,
  0.131s. Capturing Path/Counter/MappingProxyType is the sole minimal change.
  Latest lightweight suite: 41 tests, 0 failures/errors/skips, 1.571s.
  After removing the functional profiler: 41 tests, 0 failures/errors/skips, 0.407s.
- Fixed-freeze / five-field D1 identity RED: 6 tests, 6 assertion failures,
  0 errors/skips, 0.123s. Tests cover equal CN/UTC instants, changed/naive/malformed
  time, individual/multiple field-name-only errors and exact member order/set.
  Latest lightweight GREEN: 46 tests, 0 failures/errors/skips, 0.956s, including
  RunnerIdentityTests plus the prior 41-test command. AST: all four modules PASS.
- Read-only AST checks: four new Python modules passed. `py_compile` cache write
  was denied by sandbox, so it is not reported as passing.

## Unique genuine baseline and process boundary

The original `python -m unittest tests.test_formal_final_runner -v` was launched
before fixture sharing and runner hardening. Session 93620, child PID 25256,
parent Python PID 11808, start 2026-10-03 05:02:20 +04:00. Still in first test
`test_official_candidate_rejects_failed_gates_without_writing_an_official_mode_row`.
At 05:58:18 +04:00: wall 55:58, CPU 2155.62 seconds, CPU still rising, no new
test output. Even eventual success only covers the initially loaded runner.
At 07:10:47 +04:00: wall 2:08:27, CPU 5315.797 seconds, 35.9 MB working set,
still no result. Parent ruling treats the over-two-hour incomplete-evidence
baseline as performance RED and requires exact PID/parent termination at 2:15;
it is not functional GREEN. Hypothesis (not established root cause): the
industry-only fixture triggers expensive missing-evidence traversal, whereas
the known complete three-member populate/D1 chain took 1585.369 seconds.
At 07:17:21 +04:00 (wall 2:15:01, CPU 5561.797s), exact authorized termination
hit PowerShell Stop-Process internal NullReference errors. After revalidating
child StartTime and direct parent PID, native handles killed only child 25256
and parent 11808 at 07:17:56.553 (wall 2:15:36.553, CPU 5583.62s). Both
WaitForExit calls returned true; all four prior child/parent IDs were absent.
Old session 93620 exited 1 without any test verdict. No GREEN is inferred.

No second genuine fixture is currently running. A mistakenly started separate
signature fixture process was stopped under the parent ruling, exactly child
PID 29592 and parent Python PID 10948; their termination was confirmed. No broad
process kill was used. Trust RED/GREEN thereafter used unregistered objects and
pure type/module/code identity guards. Genuine configuration mutation/copy/
pickle/ownership checks reuse the revised suite's baseline and have not run.

At the 45-minute threshold, stack diagnosis was unavailable: current Python had
no enabled faulthandler and PATH/project venv/Codex search found no py-spy;
cdb/windbg/procdump were also unavailable. No tool was installed and no code was
injected. Future authorized long runs should enable `faulthandler.dump_traceback_later`
before running tests. Continuing CPU growth was reported rather than inventing
a deadlock diagnosis or a stack trace.

The revised small fixture calls `populate_final_inputs()`, not industry-only
insertion. Its class entry enables repeated 300-second faulthandler stacks and
read-only `sys.setprofile` call/return observation of exact D1/D2/D3/pool/commit
code objects, with one real invocation of each asserted for the baseline.
The revised small suite uses one real three-member baseline protected against
socket connection, one independent replay and one trusted-diff rebuild (three
complete D1 builds maximum). Saved detached baseline diagnostics are independent
of subsequent failed attempts. Failed identity/purpose/DTO attacks precede D1.
No other signature/20/23 fixture was launched in parallel.
The new class-level invocation raced with the parent's narrower single-target
ruling. Only `complete small fixture: start` appeared; no D1 event. The exact
new child 17672/direct parent 27972 were verified and stopped at 07:20:45
(child CPU 52.59s), exits/absence confirmed. No result is claimed for that run.
Only `RunnerBoundaryTests.test_preview_accepts_genuine_test_root_and_records_explicit_blockers`
is now running, session 9978, child 16872/direct parent 17892, start 07:21:04
+04:00. At 07:22:38: CPU 68.469s, working set 53.8 MB, fixture start only.
Its diagnostic stdout/faulthandler stderr is captured in ignored
`task-11-small-baseline.log`; it is not staged or a release artifact.
The second/third complete D1 builds require the baseline result and a parent
decision; they are not launched or inferred passing.
That populated single target finished in 233.584s with 0 tests / 1 setUpClass
error, session 9978 exit 1. Fixture population finished, but the helper's default
coverage freeze was not the exact frozen timestamp. Runner identity rejected
before D1, so this is neither a functional assertion RED nor GREEN. The original
ignored log is retained. After effective lightweight helper RED/GREEN, retry
only the same single target into `task-11-small-baseline-populated.log`.
Retry start 07:27:18 +04:00, child 3748/direct parent 9516, session 92705.
Population completed and D1 call appeared by 07:31:57 (wall 4:39, CPU 174.64s).
First actual 300s stack: ntpath.realpath/pathlib.resolve -> snapshot root/manifest
validation -> current financial fact/feature checking -> base metric build within
D1. At 07:32:27, wall 5:09/CPU196.19s; no D1 return yet. The process loaded
before the last three helper-binding additions, so cannot alone verify them.
Parent ruling rejects global profiling as the functional baseline. Exact child
3748/direct parent 9516 were stopped at 07:45:38.091 +04:00 (wall 18:20.091,
CPU727.047s), both exits and absence confirmed; session92705 exited1 with no
verdict. Repeated snapshots at the global observer indicate measurement cost;
they are diagnostic non-GREEN, not an elapsed-time performance threshold.
Functional setUpClass now installs no sys.setprofile or stage observer. Only
the same single baseline target is retried, session76582, preserving prior
logs and writing `task-11-small-functional.log`. Faulthandler remains enabled.
The performance-only observers use id(code) lookup plus exact is confirmation;
their overhead must not be used to judge functional wall-clock acceptance.
The sole functional retry is child PID28724/direct parent11260, start07:46:45
+04:00. By07:51:16, population was ready. At07:52:52, wall6:07/CPU225.03s,
the real300s stack showed snapshot path/manifest checks during current financial
fact reads in D1/base build, with no observer frames. At08:07:29, wall20:44 and
CPU906.31s, it was still live. The single target subsequently finished in
1261.473s: Ran0tests, FAILED(errors=1), setUpClass ValueError at runner D1 identity
comparison after genuine D1 completion, before D2 or commit. Both processes are
absent and session76582 exited1. This is actual full-chain failure evidence,
not a GREEN or a lightweight assertion RED. Ignored log retained.

Static five-field tracing confirmed only as_of_utc differed: formal_universe
preserves the historical frozen representation 2026-08-31T15:00:00+08:00; D1
closes every upstream source to 2026-08-31T07:00:00+00:00. The other four fields
(registry root, frozen hash, universe hash, canonical sorted securities) use the
same producer identities. The instants are equal. Runner now validates the fixed
instant and uses only canonical UTC internally, and D1 comparison reports only
mismatch field names. No old frozen/proof bytes, hashes or production modules
were changed. Test coverage/context selectors use canonical UTC as required by
their real producers and the existing D4 writer. New normalization/check helpers
are captured by existing runner authority guards. Lightweight TDD above passed;
no long retry or commit was started, pending the parent's explicit decision.

The parent approved one UTC-fixed single-target retry. Session37107 launched via
PowerShell7.6.5 login:false, exact command:
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -B -u -m unittest tests.test_formal_final_runner.RunnerBoundaryTests.test_preview_accepts_genuine_test_root_and_records_explicit_blockers -v > .superpowers/sdd/2026-09-28-formal-final-scoring-stage-d/task-11-small-functional-utc.log 2>&1`.
Child18844/direct Python parent3236 started08:20:45+04:00. Last live sample
08:25:07 wall4:22.476/CPU179.219s. Session later returnedexit1 with no stdout.
Log282bytes, LastWrite08:25:51, ends with UTF-8/ASCII bytes
`20-20-46-69-6C-65-20-0D-0A` (`  File \r\n`) after the first300s stack's
pathlib.py:415 _load_parts line. No unittest verdict, D2/commit evidence or receipt.
Both exact processes absent. No effective assertion RED or GREEN is claimed.

Read-only systematic-debugging audit:
- Facts: only dump_traceback_later(300,repeat=True), no exit=True, kill/abort/
  os._exit timer, global profiler or this agent's process termination call.
  Original session37107 was polled once near08:22:16, then next after exit:
  roughly3–4minute gap, not >5minutes. Earlier21minute run's continuous polling
  details are unavailable in the compressed history and are not invented.
- Exclusions/limits: Application1000/1001 query08:20–08:30 explicitly found no
  matching events; no Python ReliabilityRecords/WER directory or relevant4689
  audit. Native child/launcher exit codes are unavailable because no handle was
  retained; wrapperexit1 is not asserted to equal either. No evidence rules out
  all external termination. DiskfreeC77.7GB/D532.8GB; observed availablephysical
  memory2.47GB and virtual13.16GB. PowerShellErrorActionPreferenceContinue,
  PSNativeCommandUseErrorActionPreferenceFalse. No disk/memory exhaustion evidence.
- Hypothesis: host/session idle recovery or stderr-output boundary interruption
  is consistent with the timing and partial dump, but not uniquely established.
- Minimal parent-approved verification: one recovery target, native separated
  stdout/stderr file handles plus continuous original-session polls and same-cycle
  CPU/WorkingSet64/PrivateMemorySize64 samples; no code or fixture-authority change.

Recovery command used shellcmd.exe login:false:
`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -B -u -m unittest tests.test_formal_final_runner.RunnerBoundaryTests.test_preview_accepts_genuine_test_root_and_records_explicit_blockers -v 1> .superpowers\sdd\2026-09-28-formal-final-scoring-stage-d\task-11-small-functional-recovery-stdout.log 2> .superpowers\sdd\2026-09-28-formal-final-scoring-stage-d\task-11-small-functional-recovery-stderr.log`.
Session82302, child20796/direct Python parent21448/cmd23404, start08:30:42+04:00.
Continuous original-session polling and CPU/memory sampling crossed the old
termination point; initial working set50,778,112/private39,219,200bytes. Last
live sample09:06:01 wall35:19.157/CPU1295.40625s, working set125,935,616 and private
114,618,368bytes. Periodic stacks showed real proof work, not a global profiler.
Result: Ran1test in2133.288s, OK, 0failure/error/skip; original session exit0.
Child20796/parent21448/cmd23404 all absent after completion. No parallel heavy
fixture or next heavy test was started. Recovery supports, but does not uniquely
prove, an idle-reaper/output-boundary cause for the preceding abnormal exit.

Actual stage_seconds: identity1.9183715999824926, d1=1903.1622190999915,
d2=0.9009510999894701, d3=2.000556000013603, final_recheck4.21628610001062,
commit37.08851380000124. Counts: members3/eligibilities3; D1/D2/D3each1;
identity checks2; final batch rechecks4; pool orderings2; trusted diffs0;
rebuilt members3; scorecards/metrics/slots/retained cohorts/hard veto/pool
qualifications/selections/cap skips0. These are real pending fixture outputs,
not fabricated unavailable internal parse/rederive/recheck counts. All3members
pending_evidence; receiptblocked with pending_evidence/test_registry_not_official/
v9_release_not_implemented. Result hash
e76c0fc50d0a5fd5bcf3a82d085d4a0bb03f3b7fad9e383727124846bb5d3ce0.
No official/release/coverage/V9 permission was gained. This single target does
not validate the remaining shared-class attacks, replay/rebuild, 20/23, official
success or structural performance. No commit yet; next heavy test awaits ruling.

After the recovery evidence update, reran the complete lightweight Task11/
eligibility/pool/recovery/coverage command:46tests, 0failure/error/skip,1.214s,OK.
AST all4Python modules PASS; git diff--check PASS with existing-user-file line
ending warnings only; empty index; userplan/ignore edits preserved unstaged.

Next runner-class planning, not executed: all12methods below share the single
genuine class fixture, saved detached baseline diagnostics and baseline receipt
when selected in one class invocation. setUpClass always adds1realD1. Only
independent replay and trusted rebuild add1D1 each, so full class expected3D1,
not12. Identity/purpose/DTO/config failures occur beforeD1; no validity caching.
- test_runner_has_no_network_or_legacy_score_input_path (+0D1)
- test_runner_closes_root_and_all_batch_identities_before_d1 (+0D1)
- test_preview_accepts_genuine_test_root_and_records_explicit_blockers (+0D1)
- test_official_candidate_rejects_failed_gates_without_writing_an_official_mode_row (+0D1)
- test_v1_v2_prepolicy_and_recovery_dtos_cannot_impersonate_stage_d_inputs (+0D1)
- test_two_independent_runs_have_identical_canonical_result_hash (+1D1)
- test_rebuild_affected_derives_changes_from_current_verified_manifest (+1D1)
- test_initialized_runner_configuration_and_diagnostics_are_not_writable (+0D1)
- test_runner_cannot_be_copied_or_pickled (+0D1)
- test_repository_and_loader_ownership_changes_fail_closed (+0D1)
- test_repository_instance_method_replacement_fails_closed (+0D1)
- test_nonexact_modes_are_rejected_on_a_registered_runner (+0D1)

The previous single-target process closed its genuine fixture; proof authority
cannot be transferred using its persisted recovery DTO. A new single class
invocation would build one new shared baseline, then only the two extraD1calls.
Official-success is in the separate genuine integration class, not this class.
No next heavy test has started; await parent ruling. At this planning snapshot,
MethodType was unproven; the later no-fixture TDD below resolves that concern.

MethodType follow-up (parent-requested, strict TDD, no fixture): new
test_callable_bound_method_impostors_fail_configuration_access. RED1test with
5failedsubassertions, 0errors/skips,0.416s. The actual runner record accepted
callable impostors carrying exact genuine __self__/__func__ at StateStore frozen
lookup, RunRepository commit/plan and loader load, and accepted a replaced global
MethodType binding. The test touches only actual configuration access. It uses
real memory-only StateStore/RunRepository construction, an exact uninitialized
InputRepository allocation, and an ordinary verifier callback; no SQL initialize,
signature fixture, producer build, commit or verified proof is invoked. The
nonexistent database path remains absent. No private authority registry is
modified. This skeleton is not claimed to be a publishable input repository.

Minimal fix: import types.MethodType; protect MethodType in the existing captured
bindings; require type(current) is MethodType before __self__/__func__ identity
checks. Normal actual bound methods pass configuration access before and after
each attack. Full lightweight command now47tests PASS,0failure/error/skip,1.089s.
AST all4modules PASS; diff-check PASS with unchanged userfile line-ending warnings;
index empty. README/report updated; no next heavy test or commit. The genuine
single-target2133.288s GREEN predates this three-line boundary hardening and is
not misrepresented as latest-revision full-chain acceptance.

## Shared-class interruption and minimal timer-infrastructure TDD

Authorized full12-class command used whole-process socket.create_connection
and socket.socket.connect denial, native cmd stdout/stderr redirection to
task-11-runner-class-stdin-stdout.log / -stderr.log, failfast, no sys.setprofile,
and original-session polls at <=45s with external CPU/working-set/private
sampling. Initial cmd quoting error was an immediate SyntaxError before any
fixture; corrected stdin launcher was the only true full-class attempt.
Session94670 child23608/direct parent15944/cmd4884 started09:22:19+04:00.
Fixture:start/ready printed; no baseline-return JSON or test methods started.
Session exited1 without unittest verdict/receipt, not a business assertion RED.
Last live09:42:13.051+04 wall19:53.366 CPU710.5625s WS94855168 private83189760.
Stderr14035bytes LastWrite09:42:35.754+04 (about20:16 after launch); fourth300s
dump ended in literal '  File ' without LF after json.encoder.iterencode.
First three dumps35/31/34 completeframes to stdinlauncher. Exact23608/15944/4884
all absent; observer session53304 exited0 after detecting child absence. No
other heavy fixture ran, no automatic retry/commit occurred.

Scoped Application1000/1001 query09:41:30–09:44 and recent PythonWER checks found
no matching event. Earlier failed single target also ended mid-dump; recovered
GREEN had7 dumps29/1/33/38/6/31/34 completeframe lines, nounfinishedFile. Five
reached launcher, two shorter dumps have unknown completecallchain coverage.
Continuous original-session polling and separate native logs did not prevent
full-class interruption: idle-reaper hypothesis alone is insufficient. Timer
output is a high-correlation trigger, not unique proof of a CPython/host cause.
Actual3D1, identical replayhash, trustedappend and failureisolation still pending.

Parent-approved minimal test-only change: removed faulthandler import,
dump_traceback_later scheduling and cleanup completely from runner test entry;
no env/default re-enable. Added no-fixture test
test_shared_setup_never_schedules_a_background_traceback_timer using raising
sentinels for both timer functions and stopbeforegenuinefixture. Effective
RED1assertionfailure0errors/skips0.125s. Patches restore originals; finally
restores classdict/list contents so shared state is unchanged. No proof double,
genuine fixture, SQL or build occurs. Production runner unchanged.
Baseline/independent/trustedrebuild sites flush start/end markers and print only
returned real diagnostics/hash/counts/timings. Each returned actual d1_builds
must equal1. Teardown prints real perrun list/sum and asserts3 if all3 returned;
partial singletarget remains valid and reports its actual count. No sensitive
signature/source material is printed. External CPU/memory observation remains
the functional monitoring method; no global profiler or background dump timer.

Latest full lightweight command (README exact command):48testsPASS,
0failure/error/skip,0.359s,exit0. AST4PASS. diff-checkPASS (existing userfile
lineending warnings only), indexempty, userplan/ignore unchanged. This update
edits only tests/test_formal_final_runner.py, evidenceREADME and this ignored
report. No timerfree heavy invocation or commit; await parent ruling.

## Timer-free full shared class: genuine GREEN

One authorized stdin invocation, whole-process socket denial/failfast, native
separate task-11-runner-class-timer-free-stdout.log / -stderr.log, no
faulthandler/profile, no parallel heavy fixture or repeat. Originalsession35552
exit0: Ran12tests in2725.744s, OK,0failures/errors/skips. All12 methods:

- test_initialized_runner_configuration_and_diagnostics_are_not_writable: ok
- test_nonexact_modes_are_rejected_on_a_registered_runner: ok
- test_official_candidate_rejects_failed_gates_without_writing_an_official_mode_row: ok
- test_preview_accepts_genuine_test_root_and_records_explicit_blockers: ok
- test_rebuild_affected_derives_changes_from_current_verified_manifest: ok
- test_repository_and_loader_ownership_changes_fail_closed: ok
- test_repository_instance_method_replacement_fails_closed: ok
- test_runner_cannot_be_copied_or_pickled: ok
- test_runner_closes_root_and_all_batch_identities_before_d1: ok
- test_runner_has_no_network_or_legacy_score_input_path: ok
- test_two_independent_runs_have_identical_canonical_result_hash: ok
- test_v1_v2_prepolicy_and_recovery_dtos_cannot_impersonate_stage_d_inputs: ok

Real returned d1_builds=[1,1,1], total3. Exact seconds:
baseline identity1.1405561999999918,d1=810.6544373999932,d2=.12118969997391105,
d3=.25383689999580383,final_recheck=.8124370999867097,commit9.63974660000531.
trusted rebuild identity=.7379533000057563,d1=808.8937742999988,
trusted_diff1.711817000003066,d2=.2751026999903843,d3=.8820817999949213,
final_recheck2.694821700017201,commit36.11860640000668.
independent identity2.3185684999916703,d1=814.3545212000026,
d2=.09727689999272116,d3=.21137080001062714,
final_recheck=.6619122999836691,commit9.3714539000066.

Baseline/independent result hash equal:
c8de3e26fb3db0d7ce06fb9b767ae67be8a896b03744df0b241d1e4edc58e0c9;
shared input_manifest5da2ac4bac8825dff5bcf112e33deec38728bae96ad20a614236a469d95a0e56.
Prior run f5ae367acf784e8cbff0222c78719762; trusted newrun
df9143b605de473bb16b36d1960e6b1d; independent newrun
bf5dc6e452de4df38a21019c8debe34f. Trusted input_manifest
7b3e7b9704536cb80e8620b6f734842b7c34835a4fadf778aca718a58a48cb21;
trusted result aafd205e5204e48e207a298d32676ee426aa1bef8fc38f22a8993e9d05e15a3c.
Append/oldrun preservation/trusted manifest-derived plan/revoked gate isolation
and independent artifacts/hash equality assertions all passed. Small fixture
remains blocked with genuine pending evidence and no official/release/V9 power.

Exact native testtree25144→3868→2064→14728 absent. Observer session31335 is gone;
scoped native query excluding itself found no matching observer command.
Lastlive10:39:54.0656387+04:00 wall2716.4119812,CPU2209.640625s,WS224788480,
private213815296. Logs lastwritten10:40:03+04:00,stdout8872bytes,stderr2339bytes.
Timer-free complete GREEN supports timer-trigger hypothesis, not a unique
host/CPython cause or performance attribution.

Monitoring deviation:176 audited rounds, four request gaps>30s after phase-log
reads: cycles31/46/106/136=40.259/33.257/31.577/33.107s. Recorded max40.259s;
do not claim exact <=30s compliance. No code edits/commits or new heavy test
during run. Remaining acceptance not started; await parent direction.

## Static remaining integration/performance plan (NOT executed)

One fresh process with integration module followed by performance module uses
unittest's alphabetical method order, not source-definition order. This is
static entry-point accounting, not measured actual calls or a GREEN claim.
Fixtures populate B/C inputs separately; they do not build runner D1 until the
listed run call. _CHAINS shares genuine20/23 fixtures and current receipts only
inside that same process; it does not skip verification on fresh runs.

| Default order/test | D1 entries added | Cache/operation | Profiler |
| --- | --- | --- | --- |
| integration:test_20_and_23_genuine_members_close_every_hash_and_pool_bound | 2 full | create _CHAINS[20] and [23], test-preview baselines | none |
| integration:test_cross_frozen_security_and_registry_inputs_fail_closed | 0 | reuse both caches, foreign-root/member/official gates before D1 | none |
| integration:test_final_recheck_revocation_leaves_no_torn_run_or_revoked_bc | 1 full then final-gate rejection | reuse20; revoke at original D3 selector return; finally refresh coverage, preserve prior receipt | return-event revocation hook, not StageDObserver |
| integration:test_official_candidate_is_still_preview_ready_and_never_v9_published | 1 full | separate official20 fixture, complete every member history, signed production coverage audit; not cached | none |
| integration:test_source_and_registry_row_tamper_reject_retained_manifest | 1 failing D1 entry, not completed proof | reuse23; registry attack before D1; retained source-row attack enters fresh D1 and rejects; row/projection state restored | none |
| integration:test_z_legitimate_financial_generation_correction_appends_trusted_rebuild | 1 full | reuse23, genuine financial correction and new generation, fresh trusted rebuild, update _CHAINS[23] to current receipt | none |
| performance:test_each_stage_is_built_once_and_diagnostics_do_not_change_result_hash | 1 full | reuse20, independent preview/append/hash comparison | fast id(code)+is call counter |
| performance:test_rebuild_appends_once_and_revalidates_even_when_no_input_changed | 1 full | reuse corrected23, fresh no-change trusted rebuild/append; prior kept | none |
| performance:test_source_batch_parses_and_cohort_sorts_have_structural_bounds | 1 full | reuse corrected23, fresh preview/hash/structural budgets | StageDObserver full parse/rederive/checkpoint/cohort/pool observations |

Expected aggregate if every gate behaves as specified:9 runner D1 entry attempts,
8 complete returned D1 proofs (including revocation run's D1),7 appended runs,
3 genuine fixture constructors (test20,test23,official20). Source tamper's entry
fails inside producer validation and cannot be counted as a completed D1.
The count includes current-generation correction, not arbitrary caller IDs.
If failfast encounters a failure, subsequent counts do not occur. These numbers
are NOT instrumented numerical acceptance; pending real profiling must verify.

Recommended explicit failfast order in one process:20/23 hash-chain test →
cross-input gates → source/registry tamper (before correction) → official
candidate → legitimate correction (updates23 cache) → unprofiled no-change
rebuild → final-recheck revocation → fast stage/append profiler → structural
StageDObserver last. This front-loads functional/gate failures before profiler
cost, preserves tamper-before-correction and current23 cache requirements, and
does not construct additional fixtures/D1. Use an explicit TestSuite/name list
to preserve this order; simple module invocation has the default order above.
No remaining heavy test has been launched and no commit has been created.

## Performance and attack observability

Runner diagnostics expose only true observed stage duration/boundary calls,
members/metrics/slots/retained cohorts/rebuilt members, state/reason/veto/
qualification/pool/cap-skip counts. They are not part of canonical result hash.
Internal full parse/rederive/recheck counts are not publicly exposed or invented.
The test profiler observes stable real function code objects via sys.setprofile,
full source JSON parses, financial producer events, source checkpoint rechecks,
registry loads, cohort/pool sorts and Stage C return-frame summary. Actual writer
call and append-only row-count assertions are included. At most one parse per
source batch per observed phase and one sort per cohort are asserted; wall clock
is diagnostic, never a brittle hard threshold. Numerical full-chain profiler
results remain unavailable until the genuine performance test runs, not zero.

The final revocation attack now profiles the original pool function's return and
revokes coverage once, instead of replacing the module function and being caught
prematurely by the new authority guard. It asserts that the revocation was really
triggered and no run was appended. This full integration test has not run.
The integration module now also declares a separate legitimate financial
generation correction, reusing genuine_chain(23): genuine producer write with
later source update, trusted current-input publication and feature persistence,
fresh runner D1/rebuild, same root/frozen, new append/hash/dependency, retained
new snapshot evidence, old run unchanged, and manifest-derived targets/reasons
without caller changed_ids. Its successful current chain replaces the cached
baseline for later performance tests. This heavy test has NOT run.
Correction source_updated_at is now2026-08-30T07:00:00+00:00: later than the real
producer's original2026-03-20T08:00:00+00:00 publication, before the fixed freeze.

## Self-review and remaining concerns

- Spec: purpose exact, genuine frozen/root closure, same existing immutable
  receipt, fixed runner order, trusted rebuild and append-only writer delegation.
- Trust: no Boolean bypass or manifest-purpose auto-downgrade; immutable runner
  configuration and genuine type boundaries. Registered runtime checks passed
  final-revision small-fixture acceptance; full20/23 acceptance remains pending.
  MethodType concern is now demonstrated and resolved by the no-fixture five-
  assertion RED/47-test GREEN above. Exact type and binding protection reject
  callable metadata impostors while retaining normal bound-method configuration
  access. The later timer-free class passed all12 genuine small-fixture
  boundaries; 20/23 and full acceptance remain pending.
- Atomicity: proof-derived diagnostics before commit, repository alone publishes
  prepared children and transaction rechecks; final revocation test pending.
- Economics: formulas and selection rules delegated unchanged to D1/D2/D3/pools;
  light Decimal equality/cap/sort/recovery/coverage tests passed.
- Performance: no validity cache or substituted captured authority; exact heavy
  counts and structural-budget results pending. Existing genuine run is much
  slower than the old 13–15 minute benchmark; no arbitrary speed claim is made.
- V8/V9: only preview/candidate V8 storage; signed approved production official
  root, complete SH/SZ/BJ coverage and separate V9 validator/publisher/reporting
  remain production blockers. Both official pools remain unpublished.

20/23 chains, official-success fixture, all Stage D tests, affected regressions
and independent terminal review are still required. Do not declare Task 11 or
Stage D complete from focused results. A commit, if authorized for handoff before
those checks, must contain only the five listed deliverables and explicitly
retain these acceptance concerns.

## Task 11 veto-fixture fix round (2026-10-03)

Status: DONE for the bounded fixture/expectation edit; full 20/23 integration
remains unverified under the explicit no-D1/no-heavy-chain instruction.

Observed failure: the prior single 20-member integration run exited 1 after
2042.396 s: SH600000 actual `pending_evidence`, expected `pool_vetoed`.
Inspection of the genuine fixture showed only the last 20 calendar dates open,
then the veto reply zeroed every market row. Formal `evaluate_window` correctly
returned a proven 20-day veto alongside incomplete price evidence and
`calendar_coverage_missing`; D3 correctly ranks pending before hard veto.
Separately, a 20-member T.expectation_change cohort has only 19 eligible peers,
so SH600000 must remain D1 pending in that size even when market evidence is fixed.

Strict light TDD, with no fixture D1/build_batch or 20/23 chain invoked:

- Added `FinalScoringVetoMarketProtocolTests` first. It passes the fixture's
  calendar map through its actual override boundary and the veto market reply,
  then calls production `evaluate_window`. The test requires at least 21 open
  days; the 21st-prior day has volume 1, turnover 2 and positive close 2;
  recent 20 have zero volume/turnover; result is `veto_state=proven`,
  `price_state=positive_close_complete`, `pending=[]`.
- RED 1, focused unittest exit 1: `AssertionError: 20 not greater than or
  equal to 21` at the trading-day count. This failed on real fixture behavior.
- After only the calendar override, RED 2, focused unittest exit 1:
  oldest trading-day volume/turnover `('0','0') != ('1','2')`. This isolated
  the independent reply defect.
- GREEN, focused unittest exit 0: 1 test in 0.002 s, OK. Extended light
  command including production `EvaluateWindowTests`: 7 tests in 0.011 s,
  exit 0, no failures/errors/skips. AST parse of all three edited Python
  files: `AST 3 PASS`, exit 0. Scoped `git diff --check`: exit 0; Git printed
  only LF/CRLF working-copy conversion warnings.

Fixture edit: `produce_calendar` adds the prior 21st open day when a veto
scenario exists, keeping the base producer path and proof creation intact.
`reply` zeroes exactly the newest 20 market dates, retaining the older valid
trade and positive close. No production module changed. The test patches only
the downstream calendar persistence method so it can inspect the genuine
fixture override without building a database or D1 proof; it uses the real
fixture market reply and real evaluator.

Integration expectation edit: both counts require SH600000 `hard_veto`.
At count 20, D1 is exactly pending, D2 has no card, D3 is pending, and D1
reasons include `T.expectation_change:peer_count_below_20`. At count 23, D1
is ready, D2 has a card and D3 is `pool_vetoed`. The integration test was
not executed after this edit by instruction; these are assertions, not a
claim of full-chain GREEN.

Self-review: the new test would fail if the prior open day disappears,
is zeroed, or moves inside the quiet 20; the real evaluator catches a
missing positive close or a remaining pending market reason. The fixture
changes only a test scenario and delegates calendar persistence unchanged.
Risk: the light protocol test does not itself prove that all signed calendar
and market producers complete the 20/23 chain. That exact acceptance awaits
the parent's authorized heavy run. No commit was made.

## Task 11 FOCAL single-pool assertion correction (2026-10-03)

RED: the existing suite3 genuine 20-member integration run reached the
FOCAL assertion and failed at `tests/test_formal_final_integration.py:150`:
`self.assertTrue(rows[FOCAL]["strong_prohibited"])`, actual False. The run
reported one failure in one test after 1634.777 s; it is not GREEN.
Two read-only investigations identified the fixture's signed `cyclic_top`
rule as wait-only prohibition. The Stage D plan requires single-pool
prohibition and cyclic cap coverage, without requiring strong-only direction.

Minimal test-only fix: switch exactly the two FOCAL expectations to
`strong_prohibited=False`, `wait_prohibited=True`. No production code,
fixture, or other assertion changed. This preserves the strict assertion
that exactly the signed wait pool is prohibited.

GREEN within the permitted light scope: `CyclicRuleTests` ran 4/4 in
0.011 s, exit 0. A separate pure call through the real parsed rule,
`evaluate_rule`, and `aggregate_decisions` found `cyclic_top` matched and
`pool_prohibitions` contained only `wait`, exit 0. AST and trailing-whitespace
check of the integration file passed; scoped `git diff --check` exited 0.
No D1 or 20/23 chain was run after this edit, so full integration GREEN
remains unclaimed. No commit was made.

Ruling: Task 11 uses FOCAL's signed `cyclic_top` wait-only prohibition to
satisfy single-pool coverage; cost if wrong is that strong-only direction
remains untested, but the plan/spec do not require that direction.

## Task 11 suite4 official-candidate WAL/SHM fix round (2026-10-04)

Suite4 genuine official-candidate acceptance stopped after its first three
integration cases passed. The fourth errored at the writer's first
transaction-internal `_recheck_sources` (`formal_final_repository.py:463`):
`coverage.require_official_ready()` reached `_read_environment.db_hashes`,
whose raw `-shm` read raised Windows `PermissionError [Errno 13]` while the
same SQLite database held `BEGIN IMMEDIATE`. Suite4 reported 4 tests in
18931.544 s, one error; this is RED, not full integration GREEN.

Root cause/ruling: the main DB and committed `-wal` define the durable
audited generation. SQLite `-shm` is transient coordination state and was
already excluded from the status generation hash and returned sidecar
identity; scanning it still created a Windows lock failure. The writer must
run the full live official environment gate once after reserving the writer
and before its first Stage D insert. After inserts, that transaction has
changed the WAL, so comparing the entire physical environment to the
pre-run audit would reject its own writes. Both transaction-internal source
rechecks retain genuine coverage proof liveness and exact member/root
identity, frozen membership, loaded official registry root, and source
checkpoint verification. The second recheck omits only the physical live
environment gate; no public downgrade parameter was added.

Strict light TDD, with no D1 or full integration run:

- RED coverage command:
  `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.OfficialCoverageBoundaryTests.test_active_writer_reservation_never_reads_transient_shm_identity -v`
  exited 1, one expected assertion failure: `official environment read
  transient SHM: SQLite owns transient SHM`. The test holds real SQLite
  `BEGIN IMMEDIATE` and makes a raw SHM open deterministically fail.
- RED source-boundary command:
  `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_atomicity.FormalFinalAuthorityBoundaryTests.test_post_write_source_recheck_keeps_identity_liveness_root_and_checkpoint_without_live_hash -v`
  exited 1: post-write `_recheck_sources` invoked the physical official gate
  against its own WAL. Its synthetic identity graph isolates writer ordering
  without constructing D1; the real `_recheck_sources` body runs.
- RED writer-order command:
  `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_atomicity.FormalFinalAuthorityBoundaryTests.test_official_writer_gates_live_environment_inside_reservation_before_first_insert -v`
  first had a test-setup `eligibilities` KeyError, corrected before counting
  RED. The valid RED exited 1 because the full official gate ran after the
  first insert. It executes the real writer transaction orchestration with
  proof assembly/row projection replaced by light test witnesses.
- GREEN focused command over those three tests: 3/3 in 0.374 s, exit 0.
  Additional failure injections in the real `_recheck_sources` function
  confirm wrong coverage root, changed source checkpoint, changed frozen
  universe, revoked official registry and revoked coverage still fail closed.

Implementation changed only `formal_coverage_manifest.py` and
`formal_final_repository.py`: stop hash-scanning `-shm`; split exact
coverage identity/proof checks from the live mode gate; call the latter
before proof assembly and again under `BEGIN IMMEDIATE` before insertion;
keep source/root/coverage rechecks before and after insertion. The
`official_candidate` mode still requires `require_official_ready()`;
preview keeps its existing readiness behavior.

Regressions: the first broad coverage-guard run exposed pre-existing V7
status/contract literals against the current V8 StateStore; it was
interrupted during a long policy fixture and was not counted as GREEN.
Those fixture literals in the allowed guard test file now use
`SCHEMA_VERSION`. A focused official/WAL set then passed 4/4 in 4.650 s;
official guard + basic guard + recovery + atomicity authority command
passed 45/45 in 44.530 s, exit 0; calendar adapter passed 5/5 in
172.974 s, exit 0. The MarketRange adapter-only run was stopped after
about fifteen minutes of CPU-active shared fixture construction with no
first test result; no result is inferred. Owner/MarketRange full adapter
classes and D1/full integration were not run. Four-file AST parse and
scoped `git diff --check` passed (line-ending warnings only).

Self-review: the SHM test would fail if raw SHM access returns, while the
existing committed-WAL migration-removal and sidecar-tamper tests still
reject durable changes. The ordering witness would fail if the live gate
moves before reservation or after insertion, or if either source recheck
disappears. Source/root/coverage mutation checks remain strict. The
light orchestration witness substitutes proof construction and row
projection; genuine official-candidate 20-member GREEN remains a Task 11
acceptance step outside this no-D1 fix round.

Final fresh bounded regression after the last test edit:
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.OfficialCoverageBoundaryTests tests.test_formal_coverage_guards.CoverageGuardTests tests.test_formal_final_repository.FormalFinalRecoveryBoundaryTests tests.test_formal_final_atomicity.FormalFinalAuthorityBoundaryTests -v`
reported 45/45 in 70.440 s, exit 0, zero failures/errors/skips.
The separate exact calendar command was
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.CalendarCoverageAdapterTests -v`
and reported 5/5 in 172.974 s, exit 0. `git diff --check` on the four
allowed tracked files exited 0; AST parsed all four, exit 0. These
commands intentionally name only test classes that do not build D1.

Focused commit: `c6b0896` (`fix: keep official coverage gate before Stage D
writes`). `git show` and `git diff HEAD^ HEAD --name-only` confirmed exactly
the four authorized tracked files: `formal_coverage_manifest.py`,
`formal_final_repository.py`, `test_formal_coverage_guards.py`, and
`test_formal_final_atomicity.py`. The Task 11 runner/integration/performance
files, plan, `.gitignore`, evidence README and these ignored ledgers were
not staged or committed.

## Task 11 suite4 fix round 2/5 — captured planner arity and post-write provenance

Independent review found two Important defects in `c6b0896`. Captured
`plan_rebuild` still called the now three-argument `_coverage_identity` with
four arguments at both read boundaries, so valid rebuild plans raised
`TypeError`. Removing the full official live gate after Stage D writes also
removed authenticated owner/contract/raw provenance revalidation. A real
financial validator can change without altering the source checkpoint's
SQL/provider fingerprint.

Strict RED 1: added
`FormalInvalidationScopeTests.test_captured_rebuild_planner_rechecks_mode_gate_at_both_read_boundaries`,
executing the actual captured planner code with a genuine coverage proof and
a small stand-in for costly D1-produced input authority. Command:
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_invalidation.FormalInvalidationScopeTests.test_captured_rebuild_planner_rechecks_mode_gate_at_both_read_boundaries -v`.
It failed at `formal_final_repository.py:596` with
`_coverage_identity() takes 3 positional arguments but 4 were given`.
The test also requires two calls to the captured mode gate on a valid plan.

Strict RED 2: added
`OfficialCoverageBoundaryTests.test_postwrite_gate_ignores_own_wal_but_rechecks_live_owner_provenance`
using a genuine signed official coverage audit and genuine
`_current_source_checkpoint`. A transaction's `formal_final_*` write changes
its own WAL while structural identity and source checkpoint pass; the test
then flips the auditor-captured financial validator from accepting to
rejecting. After correcting the test's initial scratch-table name (a
non-Stage-D table correctly failed the source checkpoint), command
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.OfficialCoverageBoundaryTests.test_postwrite_gate_ignores_own_wal_but_rechecks_live_owner_provenance -v`
failed because `_coverage_postwrite_gate` did not exist. It now requires
unchanged owner provenance to pass after self WAL writes, changed provenance
to raise, and replacement of the captured class method to fail closed.

Implementation: both planner sites now call `_coverage_identity` with exactly
three arguments and then the captured `_coverage_live_gate(..., mode)`. Search
confirmed every identity caller has three arguments and both planner
boundaries retain mode gating. The coverage proof authority now has a
private sealed `_recheck_official_provenance` method verifying authenticated
contract, live context, signed owner bindings, registry, raw/row provenance
and validator result without reading physical DB/WAL. The existing full
official gate still hashes the physical environment before and after that
same provenance validation. After inserts, the writer performs its second
`_recheck_sources` plus an identity-captured `_coverage_postwrite_gate`,
without comparing its own WAL with the pre-run audit. Authenticated preview
also retains provenance revalidation. The first full gate remains under
`BEGIN IMMEDIATE` before inserts; no public downgrade flag/API was added.

Focused GREEN command naming the two new tests and the writer-ordering
witness: 3/3, exit 0. Final no-D1 regression command:
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.OfficialCoverageBoundaryTests tests.test_formal_coverage_guards.CoverageGuardTests tests.test_formal_final_repository.FormalFinalRecoveryBoundaryTests tests.test_formal_final_atomicity.FormalFinalAuthorityBoundaryTests tests.test_formal_final_invalidation.FormalInvalidationScopeTests -q`
reported 64/64 in 53.867 s, exit 0. `git diff --check` on the five
changed tracked files exited 0; read-only AST parsing reported `AST OK 5`.
A `compileall` attempt could not write Python cache files in the managed
worktree (Windows PermissionError); successful import/test execution plus
read-only AST parse cover syntax. D1-building
`FormalInvalidationRepositoryTests`, full integration and 20/23-member
chains were intentionally not run.

Self-review: the planner test executes the real function body and proves
both captured gates run, while substituting only costly input proof/read-run
authorities; it cannot replace a future genuine D1 end-to-end rerun. The
official coverage test does not mock the coverage authority or checkpoint
and proves self-WAL tolerance plus validator revocation after pre-write.
The isolated ordering witness patches the post-write gate only because its
coverage class is synthetic; the genuine authority test covers security.
The class-method identity is captured at binding and replacement rejected.
No data, SQLite, WAL/SHM, Task 11 runner/integration/performance, plan, or
`.gitignore` file was staged. Per parent request, this round remains
uncommitted pending independent re-review.

## Task 11 suite5 fix round 3/5 — empty WAL is not a durable generation

The independent scoped re-review of fix round 2 marked both Important
findings ADDRESSED, no new Critical/Important, and the five-file fix was
committed as `34eb8c6` (`fix: preserve postwrite coverage provenance checks`).
The next full suite (`task-11-integration-performance-suite5.stderr.log`)
passed its first three integration tests, then failed the official candidate
test at the first pre-insert full gate: `_read_environment` line 328 raised
`official coverage database status identity mismatch`. The suite's four
tests took 17684.669 s; this is a functional RED, not a GREEN. A lightweight
real reproduction traced the transition: official audit/status had no WAL;
`StateStore._connect()` ran `PRAGMA journal_mode=WAL` and created a 0-byte
`-wal`, while `BEGIN IMMEDIATE` did not change the main DB or add WAL frames.
The prior hash treated absent WAL as `None` and empty WAL as SHA256(empty),
falsely declaring a new durable generation before any Stage D insert.

Strict TDD RED: added
`OfficialCoverageBoundaryTests.test_empty_wal_created_by_writer_connection_is_same_durable_generation`.
It mints a genuine signed official coverage proof with no WAL, asserts the
status/audit path leaves no WAL, then uses the real `StateStore._connect()`
and `BEGIN IMMEDIATE` to assert a 0-byte WAL and unchanged main DB. The full
official gate is expected to remain ready before insertion. Exact command:
The initial RED command used the test's original name,
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.OfficialCoverageBoundaryTests.test_empty_wal_created_by_writer_reservation_is_same_durable_generation -v`.
It failed at the expected `coverage.require_official_ready()` call with
`ValueError: official coverage database status identity mismatch` (exit 1).
Self-review renamed the test to `...writer_connection...` because
`StateStore._connect()`, not `BEGIN IMMEDIATE`, creates the empty WAL.

Minimal fix: `_read_environment.db_hashes` now counts bytes actually read
and maps only a zero-byte `-wal` to `None`; any nonempty WAL retains its
SHA256 digest. Both `before` and `after` use the same normalization, so
absent/empty transitions compare equal, but appearance/removal/change of
nonempty WAL still differs and fails closed. The existing file-type check,
schema/status verification, and authenticated provenance/contract gates are
unchanged. Existing sidecar-change test now explicitly asserts its WAL
content is nonempty. No size-based pre-read shortcut was used, avoiding a
stat/read TOCTOU; a concurrent nonempty WAL appearing during the gate is
seen by the before/after generation comparison.

Focused GREEN command naming the new empty-WAL test and existing nonempty
sidecar rejection: 2/2 in 11.233 s, exit 0. Final no-D1 regression command:
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.OfficialCoverageBoundaryTests tests.test_formal_coverage_guards.CoverageGuardTests tests.test_formal_final_repository.FormalFinalRecoveryBoundaryTests tests.test_formal_final_atomicity.FormalFinalAuthorityBoundaryTests tests.test_formal_final_invalidation.FormalInvalidationScopeTests -q`
reported 65/65 in 76.710 s, exit 0. AST parsed the two changed files,
`AST OK 2`; scoped `git diff --check` exited 0. No D1/full integration was
run this round, and no commit/staging was made pending independent review.

Self-review: the regression uses the real audit, writer connection and full
official gate, not a mocked physical identity. It fails if empty WAL is
hashed as material again; existing nonempty sidecar and committed-WAL schema
tests fail if WAL checks are broadly disabled. The only production change is
the empty-WAL normalization inside `db_hashes`. On an exists/is_file/open
race, an unreadable or replaced path still raises or is caught by the
before/after material comparison; zero bytes cannot contain a committed
SQLite frame. D1/integration acceptance remains for the parent to rerun.

Task 11 suite6 temporary-root fix: the new isolated regression failed quickly
before calling the helper because the stable root resolved under the checkout,
not `tempfile.gettempdir()`. The helper now keeps its dedicated
`AShareQiheng/formal-feature-store-tests` root below the resolved OS temp
directory while retaining `TemporaryDirectory(dir=...)`. Focused regression
passed (1/1). The complete `tests.test_formal_feature_store` module ran 18 tests
but did not pass in this sandbox: 13 errors and 6 failures, chiefly existing
`_SecureDirectory` Windows handle acquisition failures (`WinError 5`) under the
test temporary directories. Fixture smoke constructed and closed
`FinalScoringFixture(peer_count=3, purpose="test")` within the 30-second bound.
`git diff --check` and AST parse passed. No D1/full Task 11 suite run.

Follow-up environment diagnosis from the parent: the default
`C:\Users\Lenovo\AppData\Local\Temp` test run's handle failures are caused
by `_SecureDirectory` opening each ancestor with `GENERIC_READ` while the
sandbox token cannot read a `C:\Users\Lenovo` ancestor; they are not caused by
the helper's directory creation. On the same unchanged code, setting
`TEMP`/`TMP` to `D:\Projects\AShareQiheng\.tmp` for the child process made
`python -m unittest tests.test_formal_feature_store -v` pass 18/18 with one
skip in 0.331s. An independent real `_SecureDirectory` smoke on D: also
returned `SECURE_OK`. For suite7, its launcher must set `TEMP` and `TMP` to the
writable D: temporary location before starting Python; do not hard-code this
environment workaround in product or test code.

Exact RED command and observed output from the implementation run:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_store.ProjectTemporaryDirectoryTests.test_helper_uses_writable_user_temp_root -v
test_helper_uses_writable_user_temp_root (tests.test_formal_feature_store.ProjectTemporaryDirectoryTests.test_helper_uses_writable_user_temp_root) ... FAIL
  File "C:\Users\Lenovo\.codex\worktrees\formal-final-stage-d\AShareQiheng\tests\test_formal_feature_store.py", line 98, in test_helper_uses_writable_user_temp_root
    self.assertTrue(PROJECT_TEST_TEMP_ROOT.resolve().is_relative_to(declared_temp_root))
AssertionError: False is not true
Ran 1 test in 0.001s
FAILED (failures=1)
```

Suite7 launcher ruling: before starting Python, align `TMPDIR`, `TEMP`, and
`TMP` to `D:\Projects\AShareQiheng\.tmp`, and do so before runner import;
`tempfile` candidate selection may consult `TMPDIR` first.

## Task 11 suite7 acceptance update

At HEAD `d8540a613ea33736f333270a0b78e196739403ac`, the fresh-process launcher
set `TMPDIR`, `TEMP`, then `TMP` to `D:\Projects\AShareQiheng\.tmp` before
Python import. It launched
`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe D:/Projects/AShareQiheng/.superpowers/sdd/2026-09-28-formal-final-scoring-stage-d/task-11-integration-performance-runner.py`.
That runner changes into the Stage D worktree, adds the nine fully qualified
test methods from its explicit `TESTS` tuple to a `unittest.TestSuite` in tuple
order, and uses `TextTestRunner(verbosity=2, failfast=True)`. Ordinary
`-m unittest tests.test_formal_final_integration tests.test_formal_final_performance -v`
selects the same tests but does not reproduce the explicit suite7 order or
fail-fast behavior; it is only an equivalent test-selection suggestion.
The ignored suite7 stderr log reports the following nine tests, all `ok`, then
`Ran 9 tests in 12077.614s` and `OK`: 20/23 hash/pool closure; cross-frozen,
security and registry rejection; retained-manifest tamper rejection; official
candidate remains preview-ready and not V9-published; legitimate financial
generation correction and trusted rebuild; no-change rebuild revalidation;
final-recheck revocation atomicity; one build per stage and hash-independent
diagnostics; structural source-parse/cohort-sort bounds. Exact test identifiers
and order are recorded in the evidence README.

The stdout profiler observed 55 cohort sorts (each once), strong/wait pool sorts
1 each, four full source parses (one D1/orchestration and three Stage C, each
once), 207 financial rederivations, 7984 registry loads, six source checkpoint
rechecks, and Stage C counts as recorded in the README. These are measured
test-side events, not inferred zeroes or a wall-clock threshold. Brief Step6 and
Step7 remain pending and not run as single wide invocations; their evidence is awaiting
independent terminal-review ruling. This suite7 result does not remove the
approved official-contract and full SH/SZ/BJ production coverage blockers or
publish/validate V9.
