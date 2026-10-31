# Task 13 Report: Three-Security Hermetic Replay and Full Regression

## Result

DONE_WITH_CONCERNS

Task 13 adds hermetic end-to-end evidence only. No production interface, tracked runtime database, user data, existing financial fixture, or online source was changed or opened for migration.

## TDD RED evidence

Command (with `TEMP`, `TMP`, and `TMPDIR` set to the worktree-local `.task13-temp` directory):

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_foundation_e2e -v
```

Actual result: exit code 1; 1 test ran and errored for the intended missing test harness:

```text
NameError: name 'HermeticDeepHarness' is not defined
Ran 1 test in 0.004s
FAILED (errors=1)
```

The RED was observed before creating `tests/feature_fixture_helpers.py` or implementing the harness and complete assertions.

## GREEN and regression evidence

All commands used `D:\Projects\AShareQiheng\.venv\Scripts\python.exe` and worktree-local `TEMP`, `TMP`, and `TMPDIR`.

Target GREEN:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_foundation_e2e -v
```

Actual final result: exit code 0; `Ran 3 tests in 2.753s`; `OK`.

Related regression:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_financial_features tests.test_deep_worker tests.test_state_store tests.test_snapshot_repository tests.test_snapshot_store tests.test_orchestrator -v
```

Actual final result: exit code 0; `Ran 243 tests in 18.898s`; `OK`.

Full regression:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

Actual result: exit code 0; `Ran 337 tests in 23.692s`; `OK`. The three new tests raise the suite from 334 to 337 tests with no regression.

Additional verification: `git diff --check` and the staged `git diff --cached --check` both completed without diff errors.

## Changed files

- `tests/test_feature_foundation_e2e.py`
  - Three-security industrial/bank/real-estate-missing replay executed twice with canonical bundle-byte equality.
  - Every emitted evidence reference is resolved to its stored `FinancialFact`, matching snapshot ID, and verified snapshot payload.
  - Exact seven dimension keys, absence of `S0`/`Sc`, post-cutoff missing-statement blocker, closed formal gate, and zero official pools are asserted.
  - A frozen feature build runs with `online=False`, zero remote attempts, and zero fixture-source calls.
  - Unclassified industry and out-of-tolerance balance equation blockers are exercised through the real deep worker and feature builder.
- `tests/feature_fixture_helpers.py`
  - Loads complete semantic statement/calendar fixtures.
  - Writes performance and prefilter documents with independent `records_hash=canonical_sha256(records)`.
  - Enqueues legacy parent fixtures and reads feature rows with an explicitly closed SQLite connection.
- `progress.md`
  - Preserves history and appends schema v3, `feature-contract-v1`, 3/337 test counts, honest unaccepted online deep coverage, financial-input-only scope, `formal_score_ready=false`, zero official pools, and the next market/capital-allocation/governance/formal-scoring work.

## Self-review

- Production interfaces and existing fixtures are unchanged.
- The fake source accepts only canonical SH/SZ identifiers, returns exact semantic `FetchBatch` instances, and never imports or patches orchestrator source defaults.
- Replay assertions inspect persisted bundles, facts, verified snapshots, status payloads, and SQLite rows rather than treating mock existence as the result.
- Offline evidence uses a pre-persisted frozen feature job and passes `source=None`; `remote_attempts == 0`, one feature set is written, and the fixture source has no calls.
- Both curated fixture documents contain and exercise Task 10 `records_hash` validation.
- `latest_feature_set_rows()` uses `with closing(sqlite3.connect(...)) as connection:` for Windows handle safety.
- Only `tests/test_feature_foundation_e2e.py`, `tests/feature_fixture_helpers.py`, and `progress.md` were staged and committed. The controller-owned `.tmp-tests/` and inaccessible `.tmp-root-check/` warning were left unchanged.
- No network command or operational acceptance run was executed.

## Commit

`1d401e645ebd0e3d219c6887b84038b72f9b91d5` — `test: verify financial feature foundation end to end`

## Concern and explicit fixture-alias ruling

The brief requires synthetic candidate `SH600002`, while the committed Task 7 real-estate fixture identifies `SZ000002`. Task 13 is not permitted to modify that existing fixture. Per controller ruling, the test helper has one explicit alias only for `real_estate_statements.json`: it first verifies the original top-level identity and every batch request symbol are exactly `SZ000002`, then copies and normalizes only the in-memory top-level identity and `FetchBatch.request.symbol` to `SH600002`. Raw `SECURITY_CODE=000002` records remain unchanged; arbitrary fixture identity rewriting is rejected.

Cost/risk: this synthetic real-estate path does not itself prove exchange-prefix consistency between the aliased candidate and the unchanged raw row. Existing financial identity/interface tests own that contract. The Task 13 proof remains hermetic and covers the specified industrial, bank, real-estate/missing-statement orchestration paths without changing production code or Task 7 fixtures.

## Fix Round 1 (review Important findings)

### Changed lines

- `tests/test_feature_foundation_e2e.py:81-89, 96-117, 151-201`: each fresh harness owns an independent deterministic UUID sequence at the test boundary; `run()` still counts every persisted feature set but returns exactly the latest verified bundle for each expected security, and fails if any current bundle is absent.
- `tests/test_feature_foundation_e2e.py:220-246`: the deterministic replay test now constructs two fresh `HermeticDeepHarness` instances with identical inputs, runs each exactly once, proves different project roots, asserts exactly three current-security bundles from each build, and compares canonical bytes plus total feature-set counts.
- `tests/test_feature_foundation_e2e.py:247-282`: the trace proof asserts nonempty industrial facts, bank facts, industrial feature values, industrial evidence, and overall evidence before tracing every emitted ref to the matching fact and verified snapshot.
- `tests/test_feature_foundation_e2e.py:342-357`: the unclassified and balance-mismatch branches each require exactly one expected-security bundle, exact `blocked` status, and exact sorted blocker tuples; the prior vacuous `all(...)` and permissive `any(...)` assertions are removed.

No production file, `progress.md`, fixture file, runtime database, or controller temp directory changed in this round.

### RED evidence

Command, with `TEMP`, `TMP`, and `TMPDIR` set to worktree-local `.task13-fix1-temp`:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_foundation_e2e -v
```

Actual result before the harness fix: exit code 1; `Ran 3 tests in 3.388s`; `FAILED (failures=2)`. The intended failures were:

```text
AssertionError: 9 != 3
AssertionError: 3 != 1
```

These exposed the historical-bundle result shape in the main and unclassified paths before the harness was changed to provide one latest current bundle per security.

### GREEN and regression evidence

Target command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_foundation_e2e -v
```

Actual result: exit code 0; `Ran 3 tests in 5.676s`; `OK`.

Related command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_financial_features tests.test_deep_worker tests.test_state_store tests.test_snapshot_repository tests.test_snapshot_store tests.test_orchestrator -v
```

Actual result: exit code 0; `Ran 243 tests in 49.601s`; `OK`.

Full command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

Actual result: exit code 0; `Ran 337 tests in 78.062s`; `OK`.

`git diff --check` exited 0. Git emitted only the existing Windows line-ending notice for the modified test file; it reported no whitespace error. The deferred `.tmp-root-check/` access warning and controller-owned `.tmp-tests/` remain untouched.

### Self-review and mutation reasoning

- If replay returns persisted history instead of one current bundle per security, the exact 3/3 bundle counts fail; if either fresh run omits a current bundle, `run()` raises before comparison.
- If a fresh rebuild changes any canonical bundle field, including fact/snapshot evidence identities, the cross-root `bundle_bytes` equality fails. Deterministic UUID injection is scoped to the test harness's state-store surrogate-ID boundary; real deep planning, normalization, persistence, bundle construction, and verification remain unmocked.
- If facts, values, or evidence disappear, the independent non-vacuity assertions fail before the trace loop. Every surviving ref must still match its persisted fact's snapshot ID and a verified snapshot payload.
- If either blocker branch emits zero or multiple current bundles, the exact count fails. Wrong security, non-blocked status, missing required blocker, or any additional blocker fails an exact assertion.
- Offline frozen-build assertions, formal gate assertions, exact seven dimensions, missing-statement blocker, no `S0`/`Sc`, and zero official pools remain covered.

### Remaining concern

The prior explicit `SZ000002` to `SH600002` real-estate test-only alias limitation remains unchanged. This round adds no new concern. The controller-deferred temp-directory warning remains environmental and was not modified.

### Fix Round 1 commit

`c8c25bfc9c8a8eefc934fd6e95ac1a5063a5fe9f` — `test: harden independent feature replays`
