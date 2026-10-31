# Task 6C — date-only bootstrap fixture repair report

## Scope and implementation

Worktree: `D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation`.

Read and followed `task-6c-calendar-fixture-repair-brief.md`. The sole tracked
file edited for this repair is `tests/test_formal_deep_worker.py`. At entry,
`ashare_pipeline/formal_sources.py` and `tests/test_formal_sources.py` already
had uncommitted source-layer repair changes; this task did not edit either.

Made exactly the two specified fixture corrections in `date_only_context_fixture()`:

1. Override the bootstrap calendar config's inherited generic request template
   with `query={"exchange": "{exchange}"}`, the existing JSON accept header,
   and a null body. This binds the signed explicit `SZ` exchange and no null
   security or period fields.
2. Set `bootstrap_calendar=True` on the timestamp fixture document, matching
   its signed source config.

Strengthened the existing bootstrap worker test, with no new bypass or
replacement of production components. It now checks:

- Signed request has exchange `SZ`, null security/period, and no calendar binding.
- Worker completes verified with one remote attempt and one transport call;
  the real adapter emits the exact `?exchange=SZ` request URL.
- Both initial parsing and persisted-raw replay occur with the signed request,
  original raw bytes, and bootstrap config.
- The task receipt resolves through the real snapshot repository to a verified
  snapshot with matching task, request fingerprint, null security/period,
  `trading_calendar` dataset, `SZ` exchange, timestamp precision, and no
  effective-time calendar evidence hash; verified raw reads match transport bytes.
- Exactly one Context fact exists for the signed registry root, with the
  expected calendar kind, scope, null security, `SZ`, calendar version,
  two literal trading days, source snapshot/content lineage, refresh generation,
  timestamp effective time, and no calendar binding. The verified task result
  names that snapshot and fact.

## RED — actual terminal reproduction before fixture edits

An initial environment probe using `python -m unittest ...` did not run the
test because `python` is not on PATH. This was not treated as RED. The parent
provided the repository virtualenv executable; the following command was run
before any fixture edit:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_bootstrap_calendar_executes_signed_exchange_request
```

Exit code: **1**. Actual terminal output:

```text
test_context_bootstrap_calendar_executes_signed_exchange_request (tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_bootstrap_calendar_executes_signed_exchange_request) ... FAIL

======================================================================
FAIL: test_context_bootstrap_calendar_executes_signed_exchange_request (tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_bootstrap_calendar_executes_signed_exchange_request)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_deep_worker.py", line 1596, in test_context_bootstrap_calendar_executes_signed_exchange_request
    self.assertEqual(fixture.store.get_formal_task(task_id)["status"], "verified")
AssertionError: 'terminal_failed' != 'verified'
- terminal_failed
+ verified

----------------------------------------------------------------------
Ran 1 test in 0.187s

FAILED (failures=1)
```

## GREEN — targeted tests

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_bootstrap_calendar_executes_signed_exchange_request tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_date_only_dependent_requires_exact_binding_and_raw_bridge
```

Exit code: **0**. Actual result:

```text
test_context_bootstrap_calendar_executes_signed_exchange_request (tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_bootstrap_calendar_executes_signed_exchange_request) ... ok
test_context_date_only_dependent_requires_exact_binding_and_raw_bridge (tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_date_only_dependent_requires_exact_binding_and_raw_bridge) ... ok

----------------------------------------------------------------------
Ran 2 tests in 51.050s

OK
```

The dependent test retains all five existing subcases: valid, missing,
substituted, stale, and bridge_missing. Its body was not edited.

## Full worker module

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker
```

Exit code: **0**. All listed tests returned `ok`, with no failures or skips.
Actual terminal summary:

```text
----------------------------------------------------------------------
Ran 82 tests in 141.464s

OK
```

Final status: **complete** within the requested fixture-only scope. No unresolved
correctness concerns were found in this repair. Verification covers the requested
worker module against the source repair already present in the worktree; it is not
a claim about the entire repository test suite.

## Diff and self-review

`git diff --check -- tests/test_formal_deep_worker.py` exited **0**, with only
Git's existing LF-to-CRLF conversion notice and no whitespace errors.
The worker test diff contains **39 insertions and 3 deletions**. The overall
status shows the same two pre-existing source repair files plus this worker test.
`git check-ignore` confirms this report path is ignored.

The test's expected exchange, URL, calendar values, null binding, and publication
timestamp are literal independently chosen fixture expectations. Lineage equality
checks link actual transport, persisted evidence, normalized fact, and task result;
they do not replace those components with mocks. Existing fixture transport and
parser isolate external I/O while the signed resolver, adapter validation, worker,
snapshot verification/persistence, normalization, and Context insertion remain real.

Mental mutation review: dropping/changing the exchange fails the exact URL and
snapshot identity assertions; skipping either parse fails the two-pass assertion;
omitting persistence fails verified receipt/raw retrieval; skipping or duplicating
normalization fails the exact fact count; changing calendar contents fails literal
value assertions; introducing a date-only binding fails the request/fact/evidence
checks. Production null-placeholder and parser-bootstrap validations remain untouched.

No production code, source tests, Context schema/repository, StateStore, or existing
data/SQLite was manually changed. Only the requested hermetic tests created their
normal disposable fixtures. No network, staging, commit, reset, or subagents were used.

The TDD skill guided preserving the actual pre-edit RED and limiting fixture changes;
the verification-before-completion skill guided recording fresh targeted/module
results and checking the final diff before completion. No skill blocked execution.
