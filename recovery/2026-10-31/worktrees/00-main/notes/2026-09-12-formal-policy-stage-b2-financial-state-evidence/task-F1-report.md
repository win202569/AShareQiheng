# Task F1 implementation report

## Status

Implemented F1 policy scalar values, the explicit V6 Decimal bridge, and the
producer-backed policy runtime fixture. No production data, network access,
Git write, commit, merge, push, or subagent was used.

Controller rulings applied:

- `signed_policy` validation in F1 is syntax/shape only. W2 owns concrete
  current-rule authorization and the non-current-rule semantic test.
- `templates` is an exact `security_id -> template_id` mapping and defines the
  frozen universe as well as signed memberships.
- All four synthetic current slots use signed `fixture.policy.current.*` fact
  keys. The three annual series retain `fixture.policy.*`, so current and
  FY2025 annual facts may differ without a same-key/same-period conflict.
- Policy-only facts persist a genuine but intentionally blocked legacy V6
  bundle. Tests authenticate it with `_read_authenticated_bundle(...,
  require_complete=False)`; F2 owns the independent optional policy projection.
- `range_enabled=True` was integrated provisionally only after R1 reported its
  focused 9-test GREEN and stable `formal_sources.py`.

## TDD evidence

### RED 1 — value module absent

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values -v
```

Exact terminal result:

```text
test_formal_policy_values (unittest.loader._FailedTest.test_formal_policy_values) ... ERROR

======================================================================
ERROR: test_formal_policy_values (unittest.loader._FailedTest.test_formal_policy_values)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_formal_policy_values
Traceback (most recent call last):
  File "C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\unittest\loader.py", line 137, in loadTestsFromName
    module = __import__(module_name)
             ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_values.py", line 6, in <module>
    from ashare_pipeline.formal_policy_values import (
ModuleNotFoundError: No module named 'ashare_pipeline.formal_policy_values'

----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (errors=1)
```

### GREEN 1 — scalar contract

Same command after the minimal value module:

```text
----------------------------------------------------------------------
Ran 10 tests in 0.002s

OK
```

This covered the prescribed V6 float identity, isolated precision-50 context,
canonical fixed Decimal strings, exact bool/enum types, strict wire keys,
runtime reason whitelist, context-free signed-policy syntax, typed missing and
domain-conflict records, rejection of nonmissing compound dictionaries, hash
normalization, deep input/output detachment, and terminal error inheritance.

### RED 2 — runtime fixture absent

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values -v
```

Exact result summary and repeated causal error:

```text
test_five_template_mapping_defines_matching_frozen_universe_and_memberships ... ERROR
test_fixture_builds_one_genuine_signed_policy_runtime_graph ... ERROR
test_fixture_registry_detects_signed_child_mutation ... ERROR
test_policy_financial_values_writes_distinct_real_fy_evidence_and_receipt ... ERROR
test_put_policy_financial_requires_explicit_year_and_per_key_units ... ERROR

ModuleNotFoundError: No module named 'tests.formal_policy_runtime_fixtures'

----------------------------------------------------------------------
Ran 15 tests in 0.002s

FAILED (errors=5)
```

The first fixture implementation run then exposed two real construction
mistakes before GREEN: the actual template identifier is `insurance`, not
`insurer`, and legacy inactive fixture declarations without `inputs` must not
be traversed as active rules. The exact failures were:

```text
ValueError: templates contains an invalid security or template
KeyError: 'inputs'

----------------------------------------------------------------------
Ran 15 tests in 0.289s

FAILED (errors=5)
```

### RED/GREEN 3 — large V6 integers

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values.DecimalBridgeTests.test_bridge_preserves_v6_float_not_original_decimal -v
```

Exact RED cause:

```text
OverflowError: int too large to convert to float

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (errors=1)
```

Exact GREEN output after checking integers without float coercion:

```text
test_bridge_preserves_v6_float_not_original_decimal ... ok

----------------------------------------------------------------------
Ran 1 test in 0.002s

OK
```

### RED/GREEN 4 — context-free signed-policy text

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values.PolicyValueTests.test_runtime_and_signed_policy_pending_reasons_are_strict -v
```

Exact RED cause (the first implementation was stricter than the controller
ruling and rejected a valid control-free code containing a space):

```text
ValueError: signed policy reason must be a canonical identifier

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (errors=1)
```

Exact GREEN output after limiting F1 to nonempty, trimmed, control-free text:

```text
test_runtime_and_signed_policy_pending_reasons_are_strict ... ok

----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
```

### RED 5 — current/annual FY2025 collision and legacy gate

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values -v
```

Exact causal output:

```text
ERROR: test_policy_financial_values_writes_distinct_real_fy_evidence_and_receipt
ValueError: current FY2025 values must equal their FY2025 annual observations

ERROR: test_put_policy_financial_requires_explicit_year_and_per_key_units
ValueError: formal feature bundle is blocked

----------------------------------------------------------------------
Ran 15 tests in 24.946s

FAILED (errors=2)
```

The first error proved the same-key/same-period collision. The implementation
now signs distinct current fact keys and writes 19 facts across five distinct
producer tasks. Investigation of the second error showed the legacy builder's
global history gate deliberately marks policy-only bundles
`feature_input_not_trustworthy`; the corrected test authenticates that blocked
receipt without weakening V6 or pretending the policy values were derived.

An intermediate run after the identity fix caught the old derived-value
expectation and an unclosed test SQLite handle:

```text
FAIL: test_policy_financial_values_writes_distinct_real_fy_evidence_and_receipt
AssertionError: None != 9.0

ERROR: test_put_policy_financial_requires_explicit_year_and_per_key_units
PermissionError: [WinError 32] ... metric.sqlite

----------------------------------------------------------------------
Ran 15 tests in 8.897s

FAILED (failures=1, errors=1)
```

The SQLite read now uses `closing(...)`. Signed AST/fact identities and the
authenticated blocked receipt, rather than an impossible legacy derivation,
are the asserted boundary behavior.

### Focused GREEN and deferred range integration

Focused default fixture command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values -v
```

Exact output:

```text
----------------------------------------------------------------------
Ran 15 tests in 19.289s

OK
```

Deferred R1 integration command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_range_enabled_fixture_integrates_real_signed_range_documents -v
```

Exact output:

```text
test_range_enabled_fixture_integrates_real_signed_range_documents ... ok

----------------------------------------------------------------------
Ran 1 test in 1.439s

OK
```

## Final prescribed GREEN

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values tests.test_formal_policy_registry tests.test_formal_metric_features -v
```

Exact final terminal result:

```text
----------------------------------------------------------------------
Ran 85 tests in 265.839s

OK
```

Exit code: `0`.

This final run includes 16 F1 tests (including `range_enabled=True`), all policy
registry regressions, and all legacy metric-feature projection tests.

## Changed files

- `ashare_pipeline/formal_policy_values.py` — new scalar DTO, typed pending
  records, exact failure classes, canonical JSON/hash helpers, isolated Decimal
  context, and V6 bridge.
- `tests/test_formal_policy_values.py` — new F1 unit, mutation, fixture,
  financial-evidence, five-template, and range-integration coverage.
- `tests/formal_policy_runtime_fixtures.py` — new genuine signed runtime fixture,
  explicit current/annual fact identities, real task/snapshot/fact/feature
  receipt path, and optional R1 range documents.
- `tests/formal_metric_feature_fixtures.py` — controller-approved minimal
  compatibility extension: optional `exchange_rows=None`, preserving default
  and `population=True` behavior.
- `.superpowers/sdd/2026-09-12-formal-policy-stage-b2-financial-state-evidence/task-F1-report.md`
  — this report.

No other implementation or test file was edited by F1. Concurrent R1 and
controller plan/ledger changes were left untouched.

## Self-review

- Decimal formatting is derived with fixed notation and no arithmetic or
  ambient-context rounding; exponent forms, meaningless fractional zeros,
  non-finite values, and negative zero wires are rejected. `to_dict()` maps a
  Decimal zero to `"0"`. V6 floats retain `Decimal(str(value))`; integers do not
  pass through float and therefore preserve arbitrarily large exact values.
- Runtime reasons exactly match spec section 9.2. `signed_policy` code/rule
  authorization is deliberately not guessed by F1 and remains a W2 gate.
- Scalar types are exact. Nonmissing event/calendar/market compound dictionaries
  are rejected until the F3/W1 closed validators exist. The same types remain
  available for typed missing/conflict records.
- DTO inputs and outputs detach nested evidence and pending containers.
  Evidence hashes are canonical lowercase SHA-256 strings, sorted and deduped.
- All graph mutations happen before signing. The fixture's policy registry
  rejects post-sign child-byte mutation.
- The configured `templates` mapping controls both the exact frozen member set
  and signed industry memberships; the five-template test covers all template
  families across SH/SZ/BJ.
- Fiscal years use distinct producer task identities. Units are explicit per
  fact (`CNY` for equity/profit and `ratio` for ROE/margin); no inherited default
  CNY shortcut is used for ratios.
- Current and annual FY2025 selectors both remain explicit FY2025 but bind
  distinct signed facts. F2 must consume the signed selector/AST and must not
  hard-code these synthetic fact keys.
- Existing V2–V6 source, formula, persistence, and old policy fixture behavior
  were not changed. The only old helper change is optional exchange-row
  forwarding, covered by the 85-test final run.
- Mutation check: wrong Decimal normalization, wrong scalar branch, unknown
  reason, malformed hash/keys, compound-value acceptance, unit loss, colliding
  FY tasks, current/annual fact aliasing, unsigned graph mutation, and wrong
  frozen-template membership each cause at least one F1 test to fail.
- `git diff --check` on the tracked helper change and a trailing-whitespace scan
  over all F1 files were clean (the repository emitted only its existing LF to
  CRLF conversion warning for the tracked test helper).

## Concerns / handoff

- R1 range integration is a provisional dependency observation: its focused
  suite was GREEN and the real six-config range graph passed F1, but independent
  controller review/acceptance of R1 was still pending when this report froze.
- The genuine policy-only V6 receipt is expected to be blocked by the legacy
  all-metric history gate. F2 must use the approved independent optional policy
  projection and authenticate this receipt with `require_complete=False`; it
  must not weaken the old gate.
- W2 must reject any `signed_policy` reason not signed by the concrete current
  rule before formal publication.
- F3/W1 must install the closed producer validators before a nonmissing
  `event_record`, `calendar_record`, or `market_window` can enter `PolicyValue`.

## F1 fix round 1

Baseline: `db093077c57a180499a96c1182a603c50ebdb00e`.
Both Important findings were accepted by the controller in task-F1-fix1-brief.md.
The TDD skill and writing-good-tests reference were read before edits.

### Changes and regression intent

- `ashare_pipeline/formal_policy_values.py`: enum now requires exact `str` and
  preserves its complete value. No trimming, identifier grammar, Unicode
  restriction, or enum allowlist is applied. The regression catches reinstated
  identifier validation, normalization, and acceptance of non-string values or
  a `str` subclass. The obsolete rejection expectation for a leading space was
  removed and replaced with exact-preservation assertions.
- `tests/formal_policy_runtime_fixtures.py`: the first check in
  `put_policy_financial` requires an exact canonical security spelling and
  membership in `self.frozen.members`, before enqueue, snapshot/fact persistence,
  publication, or feature receipt persistence.
- `tests/test_formal_policy_values.py`: both financial helpers reject
  `" sh600000 "` and `"SH600099"` without changing the complete SQLite logical
  contents or any raw snapshot / feature receipt file bytes. The state assertion
  runs even when the call raises the wrong exception. Existing tests retain the
  valid canonical-member persistence and authenticated receipt path.
- No changes to `tests/formal_metric_feature_fixtures.py`, R1 files, Git state,
  production data, network, or production scoring.

### Focused RED

Exact command (before the two implementation changes):

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_values.PolicyValueTests.test_enum_preserves_exact_strings_without_identifier_restrictions tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_financial_helpers_reject_invalid_security_without_persistence -v
```

Exit code: `1`. Exact causal output excerpts and terminal summary:

```text
ValueError: enum policy value must be a canonical identifier
StopIteration
AssertionError: Tuples differ:

Ran 2 tests in 7.906s

FAILED (failures=4, errors=5)
```

Five positive enum cases reached the existing identifier guard and errored.
All four security/helper combinations failed the persisted-state equality
assertion: malformed spelling left a collection task, and a nonmember reached
`publish_current` only after persisting evidence, then raised `StopIteration`.
The Unicode enum subtest label rendered incorrectly in Windows terminal output;
the source file and reviewed diff preserve the intended Unicode literal.

### Focused GREEN

The same exact command after the two implementation changes exited `0`:

```text
test_enum_preserves_exact_strings_without_identifier_restrictions (tests.test_formal_policy_values.PolicyValueTests.test_enum_preserves_exact_strings_without_identifier_restrictions) ... ok
test_financial_helpers_reject_invalid_security_without_persistence (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_financial_helpers_reject_invalid_security_without_persistence) ... ok

----------------------------------------------------------------------
Ran 2 tests in 6.891s

OK
```

### Fix-round checks

`git diff --check -- ashare_pipeline/formal_policy_values.py tests/formal_policy_runtime_fixtures.py tests/test_formal_policy_values.py tests/formal_metric_feature_fixtures.py`
exited `0`; only existing LF-to-CRLF conversion warnings were emitted for the
three changed files. The reviewed implementation/test diff contains 48 additions
and 3 deletions across those three files. No implementation/test edits followed
the focused GREEN.

The R1 worker confirmed its production files were frozen before the fixture RED,
focused GREEN, and prescribed compatibility run. The stable window was released
after the successful final result below.

### Fix-round prescribed compatibility GREEN

Exact command:

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_values tests.test_formal_policy_registry tests.test_formal_metric_features -v
```

Exit code: `0`. All 87 emitted test results were `ok`; exact terminal summary:

```text
----------------------------------------------------------------------
Ran 87 tests in 287.816s

OK
```

This includes all 18 F1 tests, the unchanged valid canonical-member financial
persistence and authenticated receipt cases, signed policy compatibility, and
legacy metric projection regressions. No test-output warnings were emitted.
Implementation and test files are frozen for independent fix review. Both
accepted Important findings are addressed; no remaining fix-round concerns.
