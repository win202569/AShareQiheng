# P2 implementation report — date-only Context lease diagnosis

## Current checkpoint

**ACCEPTED_AFTER_DIAGNOSTIC_FULL_SUITE — the focused test, complete
package-qualified owned module, exact original-discovery prefix, and a fresh
full 1403-test run all passed. The historical owner failure was not reproduced;
no lease/test/production repair was warranted or made.** The fresh full result
supersedes the earlier non-green full-suite gate while preserving it as history.

- Diagnostic task base: `21746b2990b24c79b93521dc75f5d8e7e4a7f176`;
  final full-run branch HEAD: `a90faf4f67f9371df71adbc63415e702f8f4016c`.
- Tracked ownership file `tests/test_formal_context_repository.py` is unchanged;
  SHA-256 remains
  `e61722e6a06ed982376fcdcab8efad8ef1a2b7f8056987a70380f4f9a51e3208`.
- `git diff -- tests/test_formal_context_repository.py` was empty after the run.
- Final tracked status was clean and local HEAD equaled
  `origin/codex/formal-v3-implementation`.
- No production file, other test, database, snapshot, user data, Git state, or
  network resource was changed.
- The prior 1403-test `FAILED(errors=1, skipped=4)` result remains historical
  evidence and is not relabeled; a separate fresh run is GREEN below.

## Stage 1 diagnostic result

Exact test:

```text
tests.test_formal_context_repository.ContextIntegrationTests.test_date_only_uses_calendar_provenance_without_recursive_self_lookup
```

Process record:

```text
SESSION=a61973e9-5fd8-4a23-b518-fc9d7714941a
LAUNCHER_PID=44452
COMPUTING_PID=44452
START_UTC=2026-09-19T13:47:35.035144+00:00
END_UTC=2026-09-19T13:48:25.515428+00:00
ELAPSED_WALL_SECONDS=50.484000
Ran 1 test in 50.198s
OK
TERMINAL_COUNTS={"errors": 0, "failures": 0, "skipped": 0, "testsRun": 1}
TERMINAL_EXIT=0
```

Command:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -u .superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P2-diagnostic.py
```

The launcher used plain non-PTY process I/O and a line-buffered tee with explicit
flushes to retain complete incremental output. The forwarding hooks left the real
clock and gate behavior intact: the clock wrapper called the original once and
returned that exact value; the owner wrapper always invoked the original owner
gate and preserved its return or exception. Row observation used the same
connection and was read-only. Output was restricted to the target date-only
snapshot task.

## Ownership observations

The same synthetic task row was observed at all four relevant checks:

```text
id=fdc55feb-7f7c-4018-a666-237898cec1af
kind=formal_context
status=leased
lease_worker=fixture-worker
lease_expires_at=2026-09-19T13:52:37.078152+00:00
refresh_generation=7b3d54ae6c3a777110a51e969d40c4bbc0700637e7e6304eeb2df26051d3c569
expected_worker=fixture-worker
expected_generation=7b3d54ae6c3a777110a51e969d40c4bbc0700637e7e6304eeb2df26051d3c569
```

| Phase / caller | Elapsed | Original sampled `now` | Headroom | Original verdict |
|---|---:|---|---:|---|
| final normalization, `formal_context_schema.normalize_verified:644` | 31.359s | `2026-09-19T13:48:06.380874+00:00` | 270.697278s | returned |
| initial persistence, `formal_context_repository._put_context_facts:243` | 36.750s | `2026-09-19T13:48:11.780627+00:00` | 265.297525s | returned |
| persistence fact validation, `formal_context_repository.validate:188` | 41.422s | `2026-09-19T13:48:16.450391+00:00` | 260.627761s | returned |
| final persistence, `formal_context_repository._put_context_facts:281` | 44.094s | `2026-09-19T13:48:19.114039+00:00` | 257.964113s | returned |

At every observed gate, all six original SQL predicate components were true:
task ID, allowed kind, leased status, worker match, expiry strictly after the
sampled original `now`, and generation match. There was no gate error.

## Diagnosis and uncertainty

What was actually reproduced: the full date-only calendar-provenance behavior ran
successfully against the real ownership checks. It retained roughly 258 seconds of
lease headroom even at final persistence. The successful final-normalization gate
preceded the successful initial-persistence gate by about 5.4 seconds.

What was not reproduced: no predicate failed, and therefore this run supplies no
new RED and cannot prove which predicate failed in the historical full-suite run.
The historical generic exception still establishes only that at least one combined
owner predicate was false at its persistence gate. Its disposable temporary row is
not available for retrospective inspection, so expiry must not be asserted as the
historical cause.

The evidence does show that the target fixture's identity, kind, status, worker and
generation are stable in the isolated path and that the only time-sensitive
predicate has a fixed 300-second budget. That makes duration sensitivity a
plausible full-suite-only explanation, not a proven root cause.

## Repair ruling

The accumulated evidence does not warrant raising the target lease. The exact
discovery-prefix run closed both known differences in the ordered module probe:
it used the historical short module import identity and executed every discovered
predecessor while retaining the entire 1403-test object graph. The target still
passed with at least 268.939803 seconds of headroom. Changing `lease_seconds` now
would treat an unreproduced duration theory as proven and would violate the
diagnostic constraint.

The historical full-suite result remains valid RED evidence that some combined
owner predicate was false in that one process, but no retained row/timestamp can
identify which one. After three successful fresh configurations, there is no
evidence-supported tracked repair. No further diagnostic workload is launched.

## Unchanged ordered owned-module diagnostic

Controller-authorized command wrapper:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -u .superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P2-module-diagnostic.py
```

The wrapper loaded `tests.test_formal_context_repository` with the default
unittest loader, preserved its normal name ordering, recorded UTC/monotonic
start/end for every test, and forwarded the same original clock/owner gate only
while the exact target test was active.

```text
SESSION=0f4f0357-fbbb-4c2f-8d05-c48123dedf5c
LAUNCHER_PID=41488
COMPUTING_PID=41488
START_UTC=2026-09-19T13:52:35.649930+00:00
END_UTC=2026-09-19T13:58:02.406547+00:00
ELAPSED_WALL_SECONDS=326.750000
Ran 47 tests in 326.644s
OK
TERMINAL_COUNTS={"errors": 0, "failures": 0, "skipped": 0, "testsRun": 47}
TERMINAL_EXIT=0
```

The target started at module elapsed 128.859 seconds after 15 preceding methods
and completed in 41.235 seconds. Its clock identity record showed that the
installed forwarder was still current and forwarded the captured original
`ashare_pipeline.state_store._utc_now`; no predecessor had replaced it.

The target task row was stable at every check:

```text
id=41b4dc21-847b-48a7-ad41-e714fb4decb5
kind=formal_context
status=leased
lease_worker=fixture-worker
lease_expires_at=2026-09-19T13:59:47.173710+00:00
refresh_generation=93d5724eaf83f4c35b17774577e8d0aa60b48f49c7940860ea44cf274705dbaf
expected_worker=fixture-worker
expected_generation=93d5724eaf83f4c35b17774577e8d0aa60b48f49c7940860ea44cf274705dbaf
```

| Phase | Target-relative time | Headroom | Gate result |
|---|---:|---:|---|
| final normalization | 23.219s | 279.442734s | all predicates true; returned |
| initial persistence | 27.719s | 274.935409s | all predicates true; returned |
| persistence fact validation | 33.282s | 269.375432s | all predicates true; returned |
| final persistence | 36.047s | 266.620234s | all predicates true; returned |

All five required real owner/expiry/rollback regressions were unchanged and
passed before the target:

- `test_context_writer_rejects_wrong_worker_and_task`
- `test_context_writer_rejects_expired_lease_at_normalize_and_put`
- `test_context_writer_rechecks_lease_after_normalizer_callback`
- `test_context_writer_new_owner_recovers_same_receipt_and_rejects_old_capability`
- `test_context_writer_rolls_back_when_lease_expires_after_insert`

The slowest observed predecessor was the neighboring
`test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor`
at 98.344 seconds. This demonstrates localized calendar-test cost, but each test
uses its own fixture and the target's lease begins inside the target, so cumulative
module elapsed alone does not consume its lease.

## Exact original-discovery prefix diagnostic

The final controller-authorized diagnostic loaded the original whole suite with
`discover(start_dir="tests", pattern="test_*.py")`, verified the exact short-name
target was unique, retained the original discovered suite and every discovered
test object, and executed only the ordered prefix through that target.

```text
SESSION=39e3c789-9d9d-4829-be3f-178fbe1c6afd
LAUNCHER_PID=31988
COMPUTING_PID=31988
START_UTC=2026-09-19T14:00:31.997871+00:00
DISCOVERY_TOTAL=1403
TARGET_MATCH_COUNT=1
TARGET_INDEX_ZERO_BASED=235
DISCOVERY_PREFIX_COUNT=236
DISCOVERY_LATER_RETAINED_COUNT=1167
TARGET_IDENTITY=test_formal_context_repository.ContextIntegrationTests.test_date_only_uses_calendar_provenance_without_recursive_self_lookup
END_UTC=2026-09-19T14:04:21.035643+00:00
ELAPSED_WALL_SECONDS=229.047000
Ran 236 tests in 228.679s
OK
TERMINAL_COUNTS={"errors": 0, "failures": 0, "skipped": 0, "testsRun": 236}
TERMINAL_EXIT=0
```

The target started at prefix elapsed 189.109 seconds after all 235 exact discovery
predecessors and completed in 39.922 seconds. At target start, the forwarding
clock remained installed over the captured original
`ashare_pipeline.state_store._utc_now`; no predecessor leaked another clock.
The original suite, all 1403 test objects and all 1167 later objects were still
retained at terminal exit.

The exact target task row was stable at all gates:

```text
id=2506a941-ebfc-47b0-9141-81c71fe899ee
kind=formal_context
status=leased
lease_worker=fixture-worker
lease_expires_at=2026-09-19T14:08:44.219593+00:00
refresh_generation=1bb30677748049a280bc8f8cb81befcd3fc751e69981ca7ccea08e54c0084ebd
expected_worker=fixture-worker
expected_generation=1bb30677748049a280bc8f8cb81befcd3fc751e69981ca7ccea08e54c0084ebd
```

| Phase | Target-relative time | Original sampled `now` | Headroom | Gate result |
|---|---:|---|---:|---|
| final normalization | 22.281s | `2026-09-19T14:04:03.388712+00:00` | 280.830881s | all predicates true; returned |
| initial persistence | 26.297s | `2026-09-19T14:04:07.398786+00:00` | 276.820807s | all predicates true; returned |
| persistence fact validation | 31.641s | `2026-09-19T14:04:12.738706+00:00` | 271.480887s | all predicates true; returned |
| final persistence | 34.172s | `2026-09-19T14:04:15.279790+00:00` | 268.939803s | all predicates true; returned |

This closes the known import-identity and predecessor-order differences, but it is
still an instrumented prefix rather than a pristine full-project run. The explicit
retention of all discovered objects matches discovery lifetime through the target
but is itself additional diagnostic state. Machine load and other transient
environmental conditions from the historical 4508-second run were not reproduced.
No whole-suite GREEN or Stage-B acceptance is claimed.

## Static full-suite-only discrimination

Read-only inspection after the Stage 1 handoff found:

- The actual package-qualified module run placed the target after 15 methods in
  `ContextIntegrationTests`. Those predecessors include the five explicit
  worker/expiry/recovery/rollback guards and many registry/snapshot validation
  paths. The target therefore does not have the same process/order context in an
  owned-module or full-project run as it did in isolation.
- Every `ContextIntegrationTests.setUp` constructs a fresh temporary directory,
  SQLite file, `StateStore`, snapshot store and repositories, and registers the
  temporary-directory cleanup. The preceding expiry tests update only their own
  per-test SQLite rows/triggers. Static inspection found no shared fixture DB.
- This module contains no patch of `ashare_pipeline.state_store._utc_now` and no
  manual patcher start/stop. Its one socket patch is lexically scoped by a `with`
  block. Thus there is no static evidence that this module leaks a fake clock
  into the target.
- The context request/registry/resolver seal tables and the P1 feature-registry
  record are identity maps backed by weak references with removal callbacks.
  Their records do not strongly retain the sealed registry/request object itself.
  Static inspection therefore found no obvious permanent global verification
  cache whose growth must make the target slower, although process heap/GC load
  and still-live objects elsewhere in a full-suite process remain possible.
- The historical native chunks have no per-chunk wall timestamps, so they cannot
  establish exact historical lease elapsed time.

Controller ruling after this review was not to increase the lease from the
isolated pass. The subsequently authorized unchanged owned-module run also passed.
No full-project run or tracked edit is authorized at this checkpoint.

## Artifacts and hashes

- `task-P2-focused-diagnostic.log`: complete actual test output and exact gate
  records; SHA-256
  `a159bb760a23ea2ab4245936b18a0ff2214962146cadda64f348878a140f9d34`.
- `task-P2-diagnostic.py`: temporary forwarding diagnostic launcher; SHA-256
  `043b08330292f7d1e63a5b4a2a954c6a3419d900b1ef86f2a29835dba236cd4f`.
- `task-P2-diagnostic-launcher-error.log`: two disclosed launcher-only setup
  failures that occurred before unittest import/load and ran zero tests; SHA-256
  `917bf7dc7e683b2b7e3622d0e7ad782eb86eb35f213cf703230acb2a547e1673`.
- `task-P2-module-diagnostic.log`: complete 47-test ordered module output,
  per-test timings and target gate records; SHA-256
  `b38feaedb895aece318b4eb746eb2d965b2c869cd45b0572f652c4dee91eb821`.
- `task-P2-module-diagnostic.py`: unchanged module diagnostic launcher; SHA-256
  `9380b976f15c3f100639cbc7d88b2f7bdedf1a5446dfee7a1cadb7dd04f03aef`.
- `task-P2-discovery-prefix-diagnostic.log`: complete 236-test original-discovery
  prefix output, timings, retention proof and target gate records; SHA-256
  `d4b751dc0a89ab3f61844cbf3b6f467f10ba6bb9aac6d51f4e0447d89b6f066d`.
- `task-P2-discovery-prefix-diagnostic.py`: final bounded diagnostic launcher;
  it was later extended for target-lifetime-only full-suite diagnostics.

## Fresh diagnostic full-suite result

Final valid session `97640`, diagnostic UUID
`118406ec-f9d1-4d7c-8b82-a6829f41e852`, PID `48900`:

```text
START_UTC=2026-09-19T15:03:24.999167+00:00
Ran 1403 tests in 4987.503s
OK (skipped=4)
TERMINAL_COUNTS={"errors": 0, "failures": 0, "skipped": 4, "testsRun": 1403}
END_UTC=2026-09-19T16:26:32.803490+00:00
ELAPSED_WALL_SECONDS=4987.812000
TERMINAL_EXIT=0
```

The four skips are unchanged Windows `WinError 1314` file-symlink privilege
limitations. There were no test warnings or failure/error markers. The target's
real clock remained intact; all six owner predicates were true at every gate.
Lease headroom was `278.263861s` at initial persistence and `271.037473s` at
final persistence. The target hook was removed immediately at `stopTest`, proven
by `TARGET_DIAGNOSTIC_HOOKS_RESTORED=true`; the other 1402 tests used original
functions. The final log SHA-256 is
`5d219f119d872625eef12c0273c603d22963d2711399b68528271bed65e22cc4`.

Two stopped harness-validation attempts are retained separately and never counted
as project verdicts: one held a second strong tuple of all TestCase objects; one
left forwarding hooks installed after the target. Their errors demonstrated
diagnostic interference, not product failures. The valid runner retained neither
condition.

All seven pre-run code/test hashes matched post-run, Git tracked status remained
clean and equal to `origin/codex/formal-v3-implementation`, and no Python process
remained. This clears the P1/P2 full-project compatibility gate; it does not mark
the remaining Stage B W1-W4 tasks complete.

## Self-review and concerns

- Instrumentation forwarded the original clock sample and original gate; it did
  not substitute a verdict or time.
- The row reads were on the gate's connection and did not write state.
- Only the date-only task was logged; no broad or repeated stack walk was used.
- Exactly one actual focused workload, one controller-authorized unchanged module
  workload, and one controller-authorized original-discovery prefix workload ran.
  Two preliminary launcher mistakes exited before importing/loading unittest and
  are separately preserved.
- No tracked-file edit has started. TDD RED/GREEN evidence is therefore not yet
  claimed.
- The final prefix reproduced short-name imports and all discovery predecessors,
  while retaining the complete discovery object graph, but instrumentation and
  explicit object retention differ from a pristine full-project run. The
  historical failed predicate remains unknown.
- No RED was reproduced and no tracked repair was made. Fresh full-project GREEN
  is established above; whole-Stage-B acceptance is not claimed.
