# F2 implementation report

Base: `f4ed417fe6e64e324e9c725c3b185f7a10c52221`.
Working tree: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
Status: implementation and tests frozen; ready for root independent review and final fresh joint acceptance.

## Scope and implementation

Task files only:

- `ashare_pipeline/formal_policy_financial.py` (new).
- `ashare_pipeline/formal_feature_repository.py` (independent policy installer appended).
- `tests/test_formal_policy_financial.py` (new; 26 tests).
- `tests/formal_policy_runtime_fixtures.py` (constructor-only pre-sign cyclic/AST configuration and genuine Context-backed financial selection).

This report is the separately requested task evidence artifact. No Git writes, production network, production collection, dependencies, database migrations, production data, scoring, or publication operations were performed. Tests create and clean their own temporary databases and source artifacts. Existing unrelated changes and `tmpj4zv9_fq/` were not touched.

The independent current-input path derives selected optional or required slots from active signed policy rule IDs. It reuses the original V6 builder and pure selected-slot evaluator, authenticates the genuine stored receipt with `require_complete=False`, and leaves the original required-only metric selector and history gate unchanged. `current_receipt_absent` is produced only from the actual authenticated receipt lookup returning `None`; no exception-text classification is used.

`PolicyFeatureState` and `PolicyFinancialSelection` are closure-registered internal objects. Their ordinary construction, copying, forged instances, instance shadows, class lookup replacement, added property shadows, and substituted read/provider paths are rejected. Rechecks repeat current selection, and compare canonical identities. Neither object grants public formal publication authority.

Annual FY2021–FY2025 observations are checked in signed order. Every AST fact occurrence keeps its actual path, formal fact ID, complete period, accounting basis, unit, and mapping version. The implementation does not infer years from slot names or count distinct evidence references. The test ROE `FY2021 profit / (FY2020 equity + FY2020 equity)` proves both opening-balance acceptance and repeated-leaf preservation: numerator `1`, equity `2`, result exactly `0.25`, with three AST occurrence records. Missing or conflicting observations retain their declared target year and a typed pending value.

Original V6 numeric values and `repr`, original projection hash, the explicit `v6_feature_decimal_bridge_v1` version, and converted decimal text are retained in selection lineage and covered by the selection hash. Financial, policy contract, nine-role, frozen universe, industry batch, provider generation, and absence identities are bound. Noncyclic members need only applicable scalar evidence; unresolved industry remains `applicability_unresolved`. The same-store Context repository recheck remains W3's responsibility, and the fixture performs it for its own selection.

## Approved architecture details and assurance limits

The root controller approved the import-order adaptation before implementation. `formal_feature_repository` defines the independent installer without reverse-importing `formal_metric_batch_guard`. During `formal_policy_financial` module initialization, the provider module first completes its import, then the installer captures the genuine owned provider type, actual `resolve_current_inputs`, actual `_metric_batch_guard`, and the existing authentic feature-repository registration guard. The installer is removed after installation. No first-selection authority capture and no replacement of the existing repository constructor are used; genuine repositories initialized before financial module import remain usable. The regression suite replaces the provider's public class alias and resolve method before the first selection and verifies rejection.

`StateStore` has no persisted all-formal-issues listing API. As explicitly accepted by the controller, the path compares the complete persisted fact snapshot, retains the completeness owner's full detached issue snapshot, rebuilds the genuine V6 receipt from both, rereads provider facts/issues and persisted sources, and uses the owned provider publication epoch/database read barrier. It does not claim an invented database-wide issue comparison. Provider completeness remains the existing explicit trust dependency for exhaustive extraction issues.

The frozen universe currently serializes the freeze as `2026-08-31T15:00:00+08:00`; requests use `2026-08-31T07:00:00+00:00`. The initial integration run exposed a string-comparison error; the fix compares parsed instants while still requiring the exact contract UTC request cutoff.

## RED and corrective test evidence

All commands were run with cwd equal to the working tree above and the existing project interpreter. The full TDD skill and `writing-good-tests.md` were read before edits.

Initial RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial -v
```

Actual initial output:

```text
AssertionError: False is not true : independent authenticated financial selection is missing
Ran 7 tests in 24.690s
FAILED (failures=7)
```

Exit code: `1`. The seven initial behavior tests were written before production implementation.

The first attempted implementation run was blocked by the parallel R2 source edit's indirect import cycle (`formal_sources -> formal_range_source -> formal_range_contract -> partially initialized formal_context_schema`). It exited `1`, `Ran 1 test in 0.000s`, loader error. This was reported to R2/root and no repeated known-failing import run was made. Static `py_compile` of all four F2 files passed, exit `0`.

After R2 announced a source-stable window, the expanded 26-test run exposed the freeze-representation mismatch and missing explicit-provider rejection:

```text
Ran 26 tests in 209.595s
FAILED (failures=1, errors=19)
```

Exit code: `1`. Nineteen errors were the common freeze identity guard; the independent actual failure was accepting `current_input_provider=None`. A focused single-test reproduction of the same guard ran `1` test in `3.646s`, exit `1`. A read-only temporary-fixture inspection printed `2026-08-31T15:00:00+08:00` and confirmed all five other root/universe/industry identity comparisons were true.

After correcting that comparison, the targeted corrective RED command was:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_optional_policy_slot_does_not_relax_metric_gate tests.test_formal_policy_financial.PolicyFinancialTests.test_same_leading_fact_versions_fail_integrity tests.test_formal_policy_financial.PolicyFinancialTests.test_state_and_selection_class_lookup_cannot_be_replaced -v
```

Actual output:

```text
test_optional_policy_slot_does_not_relax_metric_gate ... ok
test_same_leading_fact_versions_fail_integrity ... FAIL
AssertionError: ValueError not raised
test_state_and_selection_class_lookup_cannot_be_replaced ... FAIL
AssertionError: TypeError not raised
Ran 3 tests in 47.913s
FAILED (failures=2)
```

Exit code: `1`. These failures preceded their fixes: ambiguous leading versions now terminate with an integrity error, and sealed class lookup/inheritance plus complete class-member snapshots prevent shadowed state/selection reads.

Corrective GREEN command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_same_leading_fact_versions_fail_integrity tests.test_formal_policy_financial.PolicyFinancialTests.test_state_and_selection_class_lookup_cannot_be_replaced tests.test_formal_policy_financial.PolicyFinancialTests.test_financial_repository_requires_explicit_matching_owned_provider tests.test_formal_policy_financial.PolicyFinancialTests.test_legitimate_opening_equity_and_repeated_ast_occurrences tests.test_formal_policy_financial.PolicyFinancialTests.test_noncyclic_needs_only_equity_and_does_not_require_annual_history -v
```

Actual output:

```text
Ran 5 tests in 63.609s
OK
```

Exit code: `0`. A temporary-directory ResourceWarning from the deliberately rejected duplicate-observation fixture constructor was removed by explicit fixture cleanup on initialization failure.

## Prescribed compatibility run

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial tests.test_formal_feature_repository tests.test_formal_metric_features tests.test_formal_metric_batch_guard -v
```

Actual output:

```text
ERROR: test_receipt_tamper_is_integrity_failure
sqlite3.OperationalError: no such table: formal_feature_bundle
Ran 100 tests in 819.768s
FAILED (errors=1)
```

Exit code: `1`; `99` passed, including all `74` legacy tests. There were no other errors or assertion failures. The error occurred in the test's tamper SQL before the production read: V6's actual receipt table is `formal_feature_set`, not `formal_feature_bundle`.

After the controller required the running suite to finish, the test-only table identifier was corrected and the exact case was rerun:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_receipt_tamper_is_integrity_failure -v
```

Actual output:

```text
test_receipt_tamper_is_integrity_failure ... ok
Ran 1 test in 14.206s
OK
```

Exit code: `0`. Thus every one of the 26 F2 cases has passed on the final production implementation; the final single-line test correction was verified directly. The controller explicitly instructed this worker not to repeat the complete compatibility group and will include the four prescribed modules plus R2 range source in the final fresh joint run. This is not represented as a single all-green 100-test run.

During this process, R2/root announced additional controller-approved changes to R2-only range request/document/manifest timing and pagination fields. F2 files remained frozen. The controller instructed this existing process to finish, and reserved a later fresh joint run after both workers freeze; this report therefore does not claim final cross-worker acceptance.

`git diff --check -- ashare_pipeline/formal_feature_repository.py tests/formal_policy_runtime_fixtures.py` passed, exit `0`; only the repository's existing LF-to-CRLF advisory warnings were emitted.

## Frozen F2 hashes (initial handoff; superseded by fix round 1 below)

Final SHA-256 verified at handoff. Both production files and the runtime fixture were unchanged throughout the prescribed compatibility process. Only the receipt-test table identifier changed afterward. Its earlier hash was `7e788728efed5cc50a5f2aedd6de6cb08665eb655597e7c466e4850b15d34391`.

| File | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_policy_financial.py` | `5d25b58db624e0246fd91fbd3a294968cbea3bbc1a425a280e4d1819a5d5133b` |
| `ashare_pipeline/formal_feature_repository.py` | `fa9445e84fbc4cf266c6aa8326fc5adfec82dbcbb3329e022664706aa6edf784` |
| `tests/formal_policy_runtime_fixtures.py` | `8ab3940a807bd066accac25b3a298e72e2134bc83144539b8508494da2eabc68` |
| `tests/test_formal_policy_financial.py` | `30464b8f059b17e608b3bacf35646294455821ff0af2cb727826778ea70d7a79` |

Unmodified foundation SHA-256:

| File | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_financial_features.py` | `ca51be19432d9867af43de2777c960f4897f1721c7266b5d34d2a498924c794a` |
| `ashare_pipeline/formal_metric_features.py` | `11368f252701abae052baf86489b98cf2f00c25cbad931c75f8a50bc581876e5` |
| `ashare_pipeline/formal_metric_batch_guard.py` | `13ee31fb3742337f985ab852599fa4a9a42253879232fbc6388da66b7e141b1a` |
| `ashare_pipeline/formal_policy_registry.py` | `4dd60dd588e4f19deae5e9c7e378237c774610ac2c35cad158eaa67b4ec080b3` |
| `ashare_pipeline/formal_policy_values.py` | `9d8679b9f343e9c18a821204c237df89d3d4d74d84a7eaa93a47eba905d14772` |
| `ashare_pipeline/formal_metric_context.py` | `d408fe49e959d0aa1767ef968aa13117f5ae61a4b90dcb1a9395400cd45fe513` |

## Self-review and remaining boundaries

- Original metric required-slot checks and historical completeness behavior are unchanged; the new path is independently installed.
- Annual coverage uses actual AST leaf occurrences and full financial periods. Opening instant balances may belong to the preceding FY; target-year duration periods must cover the target full year, and mixed accounting bases cannot produce valid observations.
- Receipt tampering, provider substitution, cross-root/frozen/universe/template requests, changed sources, changed issue generations, appearance of an absent receipt, and forged/copied/shadowed selections are tested as failures.
- Domain missing values retain typed reasons and target years. No zero, unit conversion, name-based year inference, or peer median is substituted.
- Internal audit getters return detached immutable views, while current validity requires recheck. Industry Context freshness at W3 publication is intentionally not claimed by this financial selection alone.
- Exhaustive issues remain provider-owned because no independent formal-issue table API exists. No production economic mapping or final publication readiness is asserted.
- Root is responsible for independent review, final fresh joint acceptance, and any exact-whitelist commit.

## Fix round 1/5 — review HEAD fb4f9a6

Review: `task-F2-review-fb4f9a6.md`, read in full after the controller saved it. The first read preceded file creation; no edits preceded reading the saved review and agreement on safe issue scoping. Base HEAD is `fb4f9a681303dbe5ce53ef2007e69e0cb42ab0fe`. Status: both Important findings fixed; final amended-code focused run GREEN; four task files frozen for independent re-review. No Git writes, subagents, R2 edits, production data, network, or old V6/metric-evaluator edits.

### Changes and controller rulings

1. Each quarterly scalar AST occurrence now selects its own exact quarter endpoint and duration predecessor with the existing V6 semantics, calls the unchanged `derive_comparable_quarters`, selects the exact `quarter_key`, and records only that quarter's real `component_fact_ids`. A Q1 leaf carries its own one fact; a Q2 leaf carries its own Q1/H1 components. Cross-year leaves no longer reuse the entire formula's evidence-ID set. Quarter leading-version ties now raise `PolicyIntegrityError`, just as FY ties do. Unsupported annual period forms still cannot produce valid annual observations.

2. Complete issues remain detached, authenticated, hashed, and reread. The policy-only evaluator now receives a per-slot issue projection. Exclusion is allowed only for the three field-level extraction codes `required_source_field_missing`, `duplicate_source_field`, and `nonnumeric_value`, with a declared same-root signed mapping ID, a matching signed `source_field`, and an actual signed binding for the request exchange. The mapping's `metric_key` is compared with the slot's actual AST fact dependencies. Unknown IDs, mismatched fields, absent exchange bindings, and nonlocalizable codes stay global. No free `details` text, year label, or `source_field == fact_key` inference grants exclusion.

   `FormalFactIssue` carries no authenticated observation year/source occurrence, so the controller approved conservative **metric-level**, not year-level, scoping. An annual-ROE mapping issue affects every annual-ROE observation while independent current equity/current selectors remain usable. Full original issues are exposed in selection lineage as `all_issues`, with `slot_issues` recording the actual dependency projection. Changes to even free issue details still invalidate prior selection identity, without those details altering the affected metric.

3. The controller subsequently tightened mapping capability handling: there is no approved production no-financial-mapping schema, and `fixture-v1` must not be special-cased in production. The final policy path therefore always uses the existing real `SignedFinancialMappingRegistry.from_signed_bytes` financial-v1 loader. Placeholder/unknown/v2/malformed mappings fail; no exception-text fallback exists. `PolicyRuntimeFixture` now installs a real synthetic signed financial-v1 mapping by default before signing, preserving its values, security membership, and constructor behavior. `FinancialFixture`, existing metric fixtures, and old V6 semantics are unchanged. This is a test-graph realism correction, not a new production version whitelist. The controller will include F1 `test_formal_policy_values` consumers in the fresh joint run.

4. Genuine mapping type, loader/select methods, schema parsing/validation callable bindings, and mapping/binding class members are captured during the existing controlled module installation and rechecked. No first-use public alias becomes authority. Tests replace the public mapping type and loader method before first selection and verify failure.

Only the original four task files changed. The test module now contains 34 test methods. Both prior Important findings have direct failing-then-passing behavioral regressions.

### Fix-round RED commands and complete outputs

All commands below use the same project interpreter and working directory as above. The first RED command was:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_leading_version_conflict_is_integrity_failure tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot tests.test_formal_policy_financial.PolicyFinancialTests.test_declared_financial_mapping_corruption_is_not_global_pending tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail -v
```

Complete output (the initial process loaded the earlier local-issue test body; its incidental None-sorting assertion error was corrected and independently rerun below before implementation):

```text
test_quarter_scalar_leaves_bind_their_own_years_and_components (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components) ...
  test_quarter_scalar_leaves_bind_their_own_years_and_components (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components) (quarter='Q1') ... FAIL
  test_quarter_scalar_leaves_bind_their_own_years_and_components (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components) (quarter='Q2') ... FAIL
test_quarter_leading_version_conflict_is_integrity_failure (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_leading_version_conflict_is_integrity_failure) ... FAIL
test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot (tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot) ... ERROR
test_declared_financial_mapping_corruption_is_not_global_pending (tests.test_formal_policy_financial.PolicyFinancialTests.test_declared_financial_mapping_corruption_is_not_global_pending) ... FAIL
test_mapping_type_and_parser_substitution_before_first_selection_fail (tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail) ...
  test_mapping_type_and_parser_substitution_before_first_selection_fail (tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail) (name='SignedFinancialMappingRegistry') ... FAIL
  test_mapping_type_and_parser_substitution_before_first_selection_fail (tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail) (name='from_signed_bytes') ... FAIL

======================================================================
ERROR: test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot (tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 232, in test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot
    self.assertTrue(all(v.state == "value" for v in current.values.values()))
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: '<' not supported between instances of 'NoneType' and 'NoneType'

======================================================================
FAIL: test_quarter_scalar_leaves_bind_their_own_years_and_components (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components) (quarter='Q1')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 313, in test_quarter_scalar_leaves_bind_their_own_years_and_components
    self.assertEqual(len(leaves), expected_count)
AssertionError: 2 != 1

======================================================================
FAIL: test_quarter_scalar_leaves_bind_their_own_years_and_components (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components) (quarter='Q2')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 313, in test_quarter_scalar_leaves_bind_their_own_years_and_components
    leaves = [f for f in scalar["facts"] if f["ast_path"] == path]
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 4 != 2

======================================================================
FAIL: test_quarter_leading_version_conflict_is_integrity_failure (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_leading_version_conflict_is_integrity_failure)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 327, in test_quarter_leading_version_conflict_is_integrity_failure
    fixture.persist_features("SH600000")
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_declared_financial_mapping_corruption_is_not_global_pending (tests.test_formal_policy_financial.PolicyFinancialTests.test_declared_financial_mapping_corruption_is_not_global_pending)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 278, in test_declared_financial_mapping_corruption_is_not_global_pending
    fixture.persist_features("SH600000")
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_mapping_type_and_parser_substitution_before_first_selection_fail (tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail) (name='SignedFinancialMappingRegistry')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 290, in test_mapping_type_and_parser_substitution_before_first_selection_fail
    (mapping_module.SignedFinancialMappingRegistry, "from_signed_bytes", lambda *_a, **_k: None)):
                                                                      ^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_mapping_type_and_parser_substitution_before_first_selection_fail (tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail) (name='from_signed_bytes')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 290, in test_mapping_type_and_parser_substitution_before_first_selection_fail
    (mapping_module.SignedFinancialMappingRegistry, "from_signed_bytes", lambda *_a, **_k: None)):
                                                                      ^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 5 tests in 111.999s

FAILED (failures=6, errors=1)
```

Exit `1`. The two quarterly subcases fail on exact leaf count, not expected values computed using production helpers.

Corrected local-issue RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot -v
```

Complete output, exit `1`:

```text
test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot (tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot) ... FAIL

======================================================================
FAIL: test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot (tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 232, in test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot
    self.assertTrue(all(v.state == "value" for v in current.values.values()))
AssertionError: False is not true

----------------------------------------------------------------------
Ran 1 test in 31.045s

FAILED (failures=1)
```

The unknown-financial-version regression then exposed the intermediate fallback before its removal:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_unknown_mapping_version_cannot_downgrade_to_global_pending -v
```

Complete output, exit `1`:

```text
test_unknown_mapping_version_cannot_downgrade_to_global_pending (tests.test_formal_policy_financial.PolicyFinancialTests.test_unknown_mapping_version_cannot_downgrade_to_global_pending) ... FAIL

======================================================================
FAIL: test_unknown_mapping_version_cannot_downgrade_to_global_pending (tests.test_formal_policy_financial.PolicyFinancialTests.test_unknown_mapping_version_cannot_downgrade_to_global_pending)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 293, in test_unknown_mapping_version_cannot_downgrade_to_global_pending
    with self.assertRaises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 1 test in 8.192s

FAILED (failures=1)
```

Following the controller's final no-placeholder-fallback ruling:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_unsupported_mapping_schema_is_a_contract_failure -v
```

Complete output, exit `1`:

```text
test_unsupported_mapping_schema_is_a_contract_failure (tests.test_formal_policy_financial.PolicyFinancialTests.test_unsupported_mapping_schema_is_a_contract_failure) ... FAIL

======================================================================
FAIL: test_unsupported_mapping_schema_is_a_contract_failure (tests.test_formal_policy_financial.PolicyFinancialTests.test_unsupported_mapping_schema_is_a_contract_failure)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_financial.py", line 272, in test_unsupported_mapping_schema_is_a_contract_failure
    with self.assertRaises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 1 test in 9.137s

FAILED (failures=1)
```

### Intermediate and final amended-code GREEN

The intermediate 7-case run preceded the final controller tightening and is recorded for chronology, not used as final acceptance:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_leading_version_conflict_is_integrity_failure tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot tests.test_formal_policy_financial.PolicyFinancialTests.test_unscoped_issue_remains_global_despite_free_scope_details tests.test_formal_policy_financial.PolicyFinancialTests.test_legacy_mapping_schema_cannot_authorize_local_issue_exclusion tests.test_formal_policy_financial.PolicyFinancialTests.test_declared_financial_mapping_corruption_is_not_global_pending tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail -v
```

Complete output, exit `0`:

```text
test_quarter_scalar_leaves_bind_their_own_years_and_components (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components) ... ok
test_quarter_leading_version_conflict_is_integrity_failure (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_leading_version_conflict_is_integrity_failure) ... ok
test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot (tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot) ... ok
test_unscoped_issue_remains_global_despite_free_scope_details (tests.test_formal_policy_financial.PolicyFinancialTests.test_unscoped_issue_remains_global_despite_free_scope_details) ... ok
test_legacy_mapping_schema_cannot_authorize_local_issue_exclusion (tests.test_formal_policy_financial.PolicyFinancialTests.test_legacy_mapping_schema_cannot_authorize_local_issue_exclusion) ... ok
test_declared_financial_mapping_corruption_is_not_global_pending (tests.test_formal_policy_financial.PolicyFinancialTests.test_declared_financial_mapping_corruption_is_not_global_pending) ... ok
test_mapping_type_and_parser_substitution_before_first_selection_fail (tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail) ... ok

----------------------------------------------------------------------
Ran 7 tests in 156.250s

OK
```

Final amended-code command, after removing every mapping fallback and installing the real default mapping fixture:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_leading_version_conflict_is_integrity_failure tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot tests.test_formal_policy_financial.PolicyFinancialTests.test_unscoped_issue_remains_global_despite_free_scope_details tests.test_formal_policy_financial.PolicyFinancialTests.test_unsupported_mapping_schema_is_a_contract_failure tests.test_formal_policy_financial.PolicyFinancialTests.test_declared_financial_mapping_corruption_is_not_global_pending tests.test_formal_policy_financial.PolicyFinancialTests.test_unknown_mapping_version_cannot_downgrade_to_global_pending tests.test_formal_policy_financial.PolicyFinancialTests.test_missing_exchange_mapping_binding_cannot_scope_an_issue tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail tests.test_formal_policy_financial.PolicyFinancialTests.test_optional_policy_slot_does_not_relax_metric_gate tests.test_formal_policy_financial.PolicyFinancialTests.test_legitimate_opening_equity_and_repeated_ast_occurrences tests.test_formal_policy_financial.PolicyFinancialTests.test_receipt_absence_is_bound_and_appearance_invalidates_selection -v
```

Complete output, exit `0`:

```text
test_quarter_scalar_leaves_bind_their_own_years_and_components (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_scalar_leaves_bind_their_own_years_and_components) ... ok
test_quarter_leading_version_conflict_is_integrity_failure (tests.test_formal_policy_financial.PolicyFinancialTests.test_quarter_leading_version_conflict_is_integrity_failure) ... ok
test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot (tests.test_formal_policy_financial.PolicyFinancialTests.test_signed_local_issue_preserves_independent_equity_and_rechecks_full_snapshot) ... ok
test_unscoped_issue_remains_global_despite_free_scope_details (tests.test_formal_policy_financial.PolicyFinancialTests.test_unscoped_issue_remains_global_despite_free_scope_details) ... ok
test_unsupported_mapping_schema_is_a_contract_failure (tests.test_formal_policy_financial.PolicyFinancialTests.test_unsupported_mapping_schema_is_a_contract_failure) ... ok
test_declared_financial_mapping_corruption_is_not_global_pending (tests.test_formal_policy_financial.PolicyFinancialTests.test_declared_financial_mapping_corruption_is_not_global_pending) ... ok
test_unknown_mapping_version_cannot_downgrade_to_global_pending (tests.test_formal_policy_financial.PolicyFinancialTests.test_unknown_mapping_version_cannot_downgrade_to_global_pending) ... ok
test_missing_exchange_mapping_binding_cannot_scope_an_issue (tests.test_formal_policy_financial.PolicyFinancialTests.test_missing_exchange_mapping_binding_cannot_scope_an_issue) ... ok
test_mapping_type_and_parser_substitution_before_first_selection_fail (tests.test_formal_policy_financial.PolicyFinancialTests.test_mapping_type_and_parser_substitution_before_first_selection_fail) ... ok
test_optional_policy_slot_does_not_relax_metric_gate (tests.test_formal_policy_financial.PolicyFinancialTests.test_optional_policy_slot_does_not_relax_metric_gate) ... ok
test_legitimate_opening_equity_and_repeated_ast_occurrences (tests.test_formal_policy_financial.PolicyFinancialTests.test_legitimate_opening_equity_and_repeated_ast_occurrences) ... ok
test_receipt_absence_is_bound_and_appearance_invalidates_selection (tests.test_formal_policy_financial.PolicyFinancialTests.test_receipt_absence_is_bound_and_appearance_invalidates_selection) ... ok

----------------------------------------------------------------------
Ran 12 tests in 211.058s

OK
```

### Final fix-round hashes and self-review

Final four-file SHA-256 (all four unchanged during the final 12-case process):

| File | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_policy_financial.py` | `912ea318ae25d83511c89e9aa196a72afb79d2cfb35d40e30a67a7cfb2b68348` |
| `ashare_pipeline/formal_feature_repository.py` | `af31ee82b3e474681baf248e515cf70ea130c683a5c835f92b886ae2491ad6f4` |
| `tests/test_formal_policy_financial.py` | `920ad544de5a846566c5186c7cedd9db760223dfe744ecd703f9d7ecd2ff3014` |
| `tests/formal_policy_runtime_fixtures.py` | `ae23bd2b2e3a338b80a2f2f4759fb13c21e5f1be5415163c48f5291b3037320a` |

`git diff --check -- ashare_pipeline/formal_policy_financial.py ashare_pipeline/formal_feature_repository.py tests/test_formal_policy_financial.py tests/formal_policy_runtime_fixtures.py` exited `0`. Its complete output was the existing line-ending advisory for all four files:

```text
warning: in the working copy of 'ashare_pipeline/formal_feature_repository.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'ashare_pipeline/formal_policy_financial.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/formal_policy_runtime_fixtures.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_formal_policy_financial.py', LF will be replaced by CRLF the next time Git touches it
```

Self-review: no shared evaluator/history gate changes; no ignored current-issue snapshot; no guessed issue year, unsigned metric scope, or manufactured final-proof authority. Signed schema parsing fails closed. Quarter fact occurrence order is deterministic and each component keeps its full real period. The test mapping is synthetic and signature-authenticated, not a claim of approved production economic mappings. Existing provider-owned exhaustive-issues and W3 same-store Context freshness boundaries remain. The controller explicitly deferred the full compatibility/joint run until after independent re-review; this round claims the 12 amended cases above, not a new full-suite GREEN.
