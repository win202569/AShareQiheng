# Task 6C source-bootstrap implementation report

Status: DONE

Worktree: `D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation`

Binding requirements: `task-6c-source-bootstrap-brief.md` in this directory.
Used the test-driven-development skill and its writing-good-tests reference.

## Scope and behavior

Only tracked files changed:

- `ashare_pipeline/formal_sources.py`
- `tests/test_formal_sources.py`

The sole production change is the bootstrap guard in
`FormalOfficialSourceAdapter._preflight`: it now rejects a non-null
`request.security_id`, without rejecting an explicit validated
`request.exchange`. Its error message now names the forbidden security ID.

The request validation, signed registry selection, globally unbound bootstrap
config validation, template rendering, fetch construction, fingerprinting,
calendar-binding validation, and replay checks are unchanged. No default
exchange or mutable cross-request state was introduced.

No worker, Context resolver, schema, state, data, or SQLite files were changed.
No network or collection was performed. Tests used existing injected fixture
transport/parser components. No staging, commits, resets, or subagents were
used. The working tree was clean at initial inspection; final tracked status
contains only the two files above. Existing committed Context worker work was
preserved. HEAD at final inspection: `e149556 docs: preserve formal v3 work records`.
This requested report is ignored (`git check-ignore` confirmed its path).

## RED before production edits

Added `test_bootstrap_calendar_preserves_explicit_request_exchange` first,
initially exercising one `OfficialRequest("cninfo", "trading_calendar", None,
None, "SZ")` under a globally unbound bootstrap config with an empty template.
Its expected successful fetch was caught on terminal rejection solely to
assert zero transport/parser calls and emit an explicit assertion failure.
No production code had been edited at this point.

Initial environment probe:

```powershell
python -m unittest tests.test_formal_sources.FormalSourceTests.test_bootstrap_calendar_preserves_explicit_request_exchange -v
```

Exit 1: `python` was not on PATH. This was not treated as RED. The configured
bundled Python executable was located, then the test was actually executed:

```powershell
& 'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest tests.test_formal_sources.FormalSourceTests.test_bootstrap_calendar_preserves_explicit_request_exchange -v
```

Exit 1, expected RED output:

```text
test_bootstrap_calendar_preserves_explicit_request_exchange (tests.test_formal_sources.FormalSourceTests.test_bootstrap_calendar_preserves_explicit_request_exchange) ... FAIL

======================================================================
FAIL: test_bootstrap_calendar_preserves_explicit_request_exchange (tests.test_formal_sources.FormalSourceTests.test_bootstrap_calendar_preserves_explicit_request_exchange)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_sources.py", line 1148, in test_bootstrap_calendar_preserves_explicit_request_exchange
    fetch, verification, parsed = adapter.fetch_verified(
                                  ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_sources.py", line 1523, in fetch_verified
    plan = FormalOfficialSourceAdapter._preflight(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_sources.py", line 1346, in _preflight
    raise FormalTerminalSourceError(
ashare_pipeline.formal_sources.FormalTerminalSourceError: bootstrap calendar request must be a global request without an exchange

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_sources.py", line 1156, in test_bootstrap_calendar_preserves_explicit_request_exchange
    self.fail(f"explicit bootstrap exchange rejected before transport: {error}")
AssertionError: explicit bootstrap exchange rejected before transport: bootstrap calendar request must be a global request without an exchange

----------------------------------------------------------------------
Ran 1 test in 0.002s

FAILED (failures=1)
```

This demonstrates the old preflight rejects the explicit SZ identity before
transport and parsing, with a valid config, request, and timestamp fixture.

## GREEN coverage and commands

After confirmed RED, expanded behavioral coverage and made the minimal
preflight change. The final bootstrap tests cover:

1. Same adapter and globally unbound config fetch SZ, SH, SZ, and legacy None
   in sequence. All verify; each fetch and parser receives the exact exchange;
   parser config remains `exchange_scope=None`; effective time remains the
   timestamp with no calendar evidence hash. Fetch request fingerprints remain
   equal to their incoming request fingerprints, differ between SZ/SH/None,
   and remain stable for the repeated SZ request.
2. A legal `{exchange}` query template produces exact transport URLs for
   SZ, SH, and SZ under the same adapter, while preserving fetch exchange and
   the unbound parser config.
3. Security identity remains terminal before transport and parser, both with
   explicit SZ and without an explicit exchange.
4. Signed registry loading still rejects a bootstrap `exchange_scope="SZ"`.
5. Valid SZ snapshot replay succeeds. Changing only its exchange to SH or None
   causes a fingerprint rejection before another parser call; replay never
   uses transport.
6. The original global/no-exchange timestamp-only test remains unchanged and
   continues to reject date-only bootstrap publication evidence.

The first narrow post-change run had a test fixture error: it attempted
`exchange=None` with an `{exchange}` placeholder. Existing rendering correctly
rejected that null placeholder (`request template placeholder exchange has a
null value`); output was 5 tests, 1 failure and 1 error. The fixture was
corrected by keeping the four-request sequence on an empty template and
separately checking the template with explicit exchanges. No production
rendering change was made.

Final narrow command (run before the complete source module):

```powershell
& 'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest tests.test_formal_sources -k bootstrap -v
```

Exit 0:

```text
test_bootstrap_calendar_config_cannot_carry_an_exchange_scope ... ok
test_bootstrap_calendar_is_timestamp_only_and_surfaces_the_signed_fact ... ok
test_bootstrap_calendar_preserves_explicit_request_exchange ... ok
test_bootstrap_calendar_rejects_security_identity_before_transport_or_parser ... ok
test_bootstrap_calendar_replay_rejects_changed_exchange_before_parser ... ok
test_bootstrap_calendar_template_uses_each_explicit_exchange ... ok

Ran 6 tests in 0.011s

OK
```

Full source module command:

```powershell
& 'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest tests.test_formal_sources -v
```

Exit 0, every test reported `ok`:

```text
Ran 40 tests in 0.043s

OK
```

No test warnings or errors in either final GREEN run.

## Self-review

- Reviewed the complete diff. Production diff is one narrowed bootstrap
  condition and its accurate error message: 2 insertions, 4 deletions.
- Tracked diff totals: 2 files, 117 insertions, 12 deletions. Test additions
  replace the obsolete request-exchange rejection expectation with the newly
  authorized behavior while preserving config-scope rejection.
- Reinstating the old exchange guard would fail the explicit-exchange fetch,
  transport-template, and valid replay tests. Removing security rejection
  would fail the zero-transport/parser security tests. Defaulting or retaining
  an exchange across requests would fail the SZ/SH/SZ/None identity checks.
- Changing snapshot exchange without recomputing its request fingerprint is
  detected before parsing, preserving snapshot/request exchange binding.
- All tests exercise the actual adapter entry points or signed registry
  loader. Only external transport and parser dependencies use existing
  hermetic fixtures; no implementation branch inspection is used.
- `git diff --check` found no whitespace errors. Git printed its existing
  LF-to-CRLF conversion advisories for the two files; these are not test
  failures and no bulk line-ending rewrite was performed.
- Final `git status --short`: only the two authorized tracked files modified.
- Full repository/integration tests were not requested for this implementer;
  the required complete `tests.test_formal_sources` module passed.

Outstanding concerns: none.
