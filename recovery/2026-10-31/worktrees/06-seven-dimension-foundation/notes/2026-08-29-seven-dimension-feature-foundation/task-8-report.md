# Task 8 implementation report

## Scope and baseline

- Worktree: `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation`
- Required baseline verified before edits: `17f5865c354649aa5f9e20d50d690ee642be4748`
- Files changed: only `ashare_pipeline/financial_features.py` and `tests/test_financial_features.py`
- Runtime `data/` and the main checkout were not touched.
- Read before implementation: the complete Task 8 brief, the complete design, the Task 8 plan section, Task 1/2/7 contracts and reviews, and the existing feature contract, template registry, fact normalizer, and their tests.
- No new spec/interface conflict was found. The preflight F2 ruling is applied: an omitted statement key is normalized to explicit null and hashes identically; null changing to a real snapshot changes the hash.

## TDD record

### Baseline

```powershell
$env:TEMP=$env:TMP='D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation\.tmp-tests'
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features -v
```

Result before Task 8 edits: `30/30` passed.

### RED

Tests were written before production changes: 14 `FeatureBundleBuildTests`, 2 formula tests, and 4 input-hash tests.

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FeatureBundleBuildTests -v
```

Result: expected import-stage RED, `1` loader error. Exact failure:

```text
ImportError: cannot import name 'FORMULA_VERSION' from 'ashare_pipeline.financial_features'
Ran 1 test in 0.000s
FAILED (errors=1)
```

This was the required missing-interface failure; production code had not been changed.

### GREEN

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FeatureBundleBuildTests -v
```

Result: `14/14` passed.

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FinancialFormulaTests tests.test_financial_features.FeatureInputHashTests -v
```

Result: `6/6` passed.

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features -v
```

Result: `50/50` passed.

## Implementation

- Added `FORMULA_VERSION`, finite fail-closed `symmetric_growth()` and positive-endpoint `positive_cagr()`.
- Added exact canonical `feature_input_hash()` with the three normalized statement keys plus calendar and contract/mapping/template/formula versions; JSON NaN remains rejected.
- Added deterministic registered-slot bundle construction for common non-financial templates, registered raw facts, evidence propagation, missing values with units/reasons, and the approved accounting formulas.
- Implemented gross profit, EBIT, bounded effective tax rate, NOPAT, FCF, interest-bearing debt, net debt, invested capital, operating working capital, total accruals, ROIC, gross margin, symmetric revenue growth, and revenue CAGR.
- Average assets/invested capital use explicit opening/closing periods. Zero/negative/missing denominators fail closed.
- All seven dimensions are always present. `V`/`T` remain empty missing containers. `CA` contains only accounting allocation/cash-flow inputs. Bank/unclassified templates receive no industrial slots; real estate uses its registered common high-leverage inputs.
- Coverage excludes not-applicable values. Zero applicable slots is blocked at zero coverage. `financial_ready` requires all seven periods, complete applicable inputs, a classified template, and no financial blocker.
- `formal_industry_mapping_missing` is always present but is not a financial blocker by itself. Formal confidence remains null and formal-score readiness false; no score/pool/recommendation output is produced.
- Fact blockers are preserved with deterministic de-duplication/sorting. Missing calendar and post-cutoff reported-target missing-statement blockers follow the brief exactly.
- Bundle output is deterministic under shuffled facts and retains the deep immutability supplied by the Task 1 contract.

## Regression and verification

Initial complete explicit-module run after GREEN:

```powershell
$modules = @(rg --files tests -g 'test_*.py' | ForEach-Object { ($_ -replace '\\','.' -replace '/','.' -replace '\.py$','') } | Sort-Object)
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest @modules -v
```

Result: `235/235` passed.

Fresh pre-commit verification:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract tests.test_financial_schema tests.test_state_store tests.test_snapshot_repository tests.test_sources tests.test_financial_features -v
```

Result: Task 1–8 related regression `156/156` passed.

```powershell
$modules = @(rg --files tests -g 'test_*.py' | ForEach-Object { ($_ -replace '\\','.' -replace '/','.' -replace '\.py$','') } | Sort-Object)
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest @modules
```

Result: full suite `235/235` passed.

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m py_compile ashare_pipeline/financial_features.py tests/test_financial_features.py
git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/seven-dimension-foundation diff --check
```

Result: both commands exited `0`; `diff --check` emitted only Git's existing LF/CRLF working-copy warnings and no whitespace errors.

The explicit `.tmp-tests` directory is removed after the commit and final post-commit status check. Commit hash and final status are appended below.

## Commit and final state

- Commit: `7d7657f` (`feat: build deterministic financial feature bundles`)
- The commit contains exactly the two allowed source/test paths; this ignored report is not committed.
- `.tmp-tests` was removed after resolving and validating the exact absolute target under the worktree.
- Final HEAD: `7d7657f59f4ff7de64e01fbb642ffa5c333f67a6`.
- Final Git status: clean (`## feature/seven-dimension-foundation`, no short-status entries).

## Review fix round 1

Independent review requested P1 fact-identity/version isolation and P2 explicit FY2021 average-formula applicability.

### Fix RED

Four focused regression tests were added before production changes:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest `
  tests.test_financial_features.FeatureBundleBuildTests.test_fy2021_average_formula_slots_are_explicitly_not_applicable `
  tests.test_financial_features.FeatureBundleBuildTests.test_cross_security_facts_are_filtered_blocked_and_never_become_evidence `
  tests.test_financial_features.FeatureBundleBuildTests.test_mixed_security_facts_filter_wrong_inputs_and_keep_bundle_blocked `
  tests.test_financial_features.FeatureBundleBuildTests.test_old_mapping_facts_are_filtered_and_mapping_inconsistency_blocks -v
```

After correcting one test-fixture setup error and rerunning against unchanged production code, RED was:

- P2: two `KeyError` failures for absent `eq.total_accruals.FY2021` and `m.roic.FY2021`.
- P1: three assertion failures because all-wrong-security, mixed-security, and old-mapping inputs returned `financial_ready`.
- Command result: `4` tests, `3` failures and `2` subtest errors.

### Partial GREEN and discovered contract conflict

The minimal Task 8 implementation filters mismatched-security/mapping facts, adds stable blockers, and prevents their evidence from entering the bundle. All three P1 tests passed.

P2 then exposed a cross-task contract conflict: the new explicit `not_applicable` values plus required `input_ready` dimension status are rejected by Task 1 `DimensionInput.__post_init__`, which currently forbids any `not_applicable` value inside an `input_ready` dimension. Task 8's original two-file scope cannot satisfy both constraints. Work paused before editing Task 1 files and the controller was asked to authorize or reject the minimal contract expansion.

The controller authorized the minimal expansion to `ashare_pipeline/feature_contract.py` and `tests/test_feature_contract.py`, because the binding specification excludes N/A slots from applicability while the old validator treated them as incomplete.

Contract tests were written before the contract change. RED evidence:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest `
  tests.test_feature_contract.FeatureContractTests.test_input_ready_accepts_ready_values_mixed_with_not_applicable `
  tests.test_feature_contract.FeatureContractTests.test_input_ready_rejects_missing_or_blocked_applicable_values `
  tests.test_feature_contract.FeatureContractTests.test_input_ready_requires_at_least_one_observed_or_derived_value -v
```

Result: `3` tests; the ready+N/A case errored because the old validator rejected it, and the empty input-ready subcase failed because no error was raised. The existing missing/blocked and N/A-only safety branches were already green.

The minimum contract change now permits observed/derived plus N/A, still rejects missing/blocked, and requires at least one observed/derived value for `input_ready`. Combined contract and P1/P2 focused GREEN: `7/7`. Complete Task 1 plus Task 8 GREEN: `66/66`.

Fresh fix-round verification:

- Task 1–8 related modules: `163/163` passed.
- Full explicit-module suite with `TEMP`, `TMP`, and `TMPDIR` on the worktree drive: `242/242` passed.
- `py_compile` for all four changed files: exit `0`.
- `git diff --check`: exit `0`, no whitespace errors (only existing LF/CRLF notices).
- Self-review confirmed the diff contains only the controller-authorized Task 1 contract expansion, P1/P2 production fixes, and their regression tests.

Fix commit: `0ec27e0` (`fix: isolate financial feature bundle inputs`), created as a new commit after `7d7657f` without history rewriting.

Final fix HEAD: `0ec27e0544112e5a1eaa8ae8fe12b655ea326d8b`. The exact absolute `.tmp-tests` path was validated as the worktree child and removed. Final Git status is clean (`## feature/seven-dimension-foundation`, no short-status entries).

## Self-review and risks

- The feature-slot registry is intentionally local to `financial_features.py` because the task permits changes in only two files. A future versioned template expansion may justify moving derived-slot metadata into a dedicated registry, but doing so now would violate scope.
- Coverage includes both registered observed slots and the deterministic derived slots emitted for the template. This makes an invalid formula denominator visible as incomplete coverage rather than hiding it behind complete raw facts.
- Financial templates with zero registered common slots (bank, insurance, broker, unclassified) remain blocked at zero coverage until specialized facts are defined; no industrial proxy fields are synthesized.
- No production network, SQLite, filesystem persistence, formal scoring, or market-data behavior was added.
