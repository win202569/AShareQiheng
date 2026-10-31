# Task 6C receipt-replay lease-fence repair

Worktree: `D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation`.
Binding brief: `task-6c-replay-lease-fence-brief.md` in this directory.
Status: DONE. Outstanding concerns: none within this repair's scope.

## Exact changes

- `ashare_pipeline/formal_deep_worker.py`: added one `fence()` call in
  `_execute_context_task`, after the real verified raw read and SHA-256 check,
  immediately before `source_call(...parse_verified_snapshot...)`.
- `tests/test_formal_deep_worker.py`: added
  `test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers`.
  It seeds valid receipt/raw evidence under an old owner using the real signed
  runtime and snapshot repository, expires the seed lease, and runs receipt
  recovery under that old owner. The real `read_verified_raw` is wrapped only
  to expire the active recovery lease immediately after returning verified bytes.
  Before recovery by a new owner, assertions require zero parser callbacks and
  transport calls; leased status with old owner and expired lease; null result,
  error, and retry time; no failure/circuit summary or stored circuit; no facts;
  and the unchanged receipt. The new owner then verifies the task with exactly
  one parser call, one fact, unchanged receipt/raw bytes, matching result/fact
  snapshot lineage, and zero transport calls.

All commands below ran in the worktree above. `python` was absent from PATH;
the repository virtualenv executable was used. No failing environment probe
was counted as RED.

## RED before production edits

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -B -m unittest tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers -v
```

Exit 1. The test was added and this command completed before production edits.
Actual terminal output:

```text
test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers (tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers) ... FAIL

======================================================================
FAIL: test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers (tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_deep_worker.py", line 1480, in test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers
    self.assertEqual(len(fixture.parser.calls), 0)
AssertionError: 1 != 0

----------------------------------------------------------------------
Ran 1 test in 0.279s

FAILED (failures=1)
```

The state, circuit, facts, immutable receipt, and no-transport assertions
preceding the parser-count assertion passed in RED. The observed failure is
the required stale parser invocation, not a fixture or initialization failure.

## Focused GREEN

After adding the single production fence, reran the exact RED command.
Exit 0; actual terminal output:

```text
test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers (tests.test_formal_deep_worker.FormalContextWorkerExecutionTests.test_context_receipt_replay_lease_loss_after_raw_read_skips_parser_and_recovers) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.702s

OK
```

## Broader verification

Full worker module:

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -B -m unittest tests.test_formal_deep_worker
```

Exit 0. Actual terminal summary:

```text
Ran 83 tests in 148.338s

OK
```

Source and Context repository suites:

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -B -m unittest tests.test_formal_sources tests.test_formal_context_repository
```

Exit 0. Actual terminal summary:

```text
Ran 79 tests in 379.298s

OK
```

These cover all 40 source adapter tests (including bootstrap exchange, replay
lineage, and date-only binding) and all 39 Context repository tests. The full
worker suite and this combined source/Context run were independent commands
run concurrently. There were no test failures, skips, or warnings in GREEN.
The long combined run continued emitting passing results and its Python
process accumulated CPU time; it required no input. Verification is scoped to
these modules, not the entire repository test suite.

## Self-review and scope

The production change uses the existing lease renewal helper with the same
task, owner, and remote-attempt accounting. Lost ownership still propagates
through the existing `_LostFormalTaskLease` path; no catch, terminal/retry
mapping, circuit mutation, lineage validation, or later fence was changed.
Removing the new fence reproduces the observed RED by permitting one stale
parser callback. The successful new-owner half also catches a repair that
incorrectly disables valid receipt replay or forces refetching.

The regression keeps real signed request/runtime validation, raw verification,
receipt persistence, hashing, task leasing, parser replay, normalization, fact
insertion, and completion. It uses the existing hermetic transport/parser
fixtures and existing lease-expiry helper. The patched read delegates to the
real read before the deliberately injected expiry.

Existing uncommitted changes to `formal_sources.py`, `test_formal_sources.py`,
the date-only worker fixture, and its bootstrap test were present at entry and
were preserved. `tmpj4zv9_fq/` was already an untracked directory at initial
inspection and was not modified or removed. This task made no manual data or
SQLite changes; only requested tests create their normal disposable fixtures.
No network, collection, staging, commit, reset, or subagents were used.
The report path is ignored (`git check-ignore` confirmed this before writing).

`git diff --check` returned 0 with no whitespace errors; Git printed existing
LF-to-CRLF conversion advisories. The TDD skill and writing-good-tests reference
guided the actual RED-first test and boundary assertions. The
verification-before-completion skill guided fresh test results and diff review.
