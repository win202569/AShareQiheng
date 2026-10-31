# Task 3B report — authenticated pre-policy score arithmetic

## Scope and frozen source

- Worktree: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`
- Required base / observed HEAD: `a2cc2ce3d43d9f51d366464013739179d68bcb36`
- Source allowlist used: new `ashare_pipeline/formal_scoring.py` and `tests/test_formal_scoring.py` only.
- Pre-existing untracked `tmpj4zv9_fq/` was not read, changed, staged, or removed.
- No Git/index/commit, network, data/SQLite, registry, fixture, progress, or pipeline-status mutation was performed.
- Source/test freeze: `2026-09-09T10:42:18.2955367+04:00`. Do not edit the two source files after this report; parent review and final verification own subsequent changes.
- Frozen SHA256:
  - `ashare_pipeline/formal_scoring.py`: `62e6eee897f18161ffda276368191a6c5715b5b4209e0a48d9b482606fe869e5`
  - `tests/test_formal_scoring.py`: `ec561a8eef8ce992d934d969d33a5f617701d7c5842a49d448a7d74dd1be74ca`

## Public API and schema

- `PrePolicyScoreCalculation`: sealed, immutable, weakly registered proof with no public constructor or mutation path.
- `calculate_pre_policy_score(score_input)`: accepts only the exact genuine `FormalScoreInput`; raw/copy/subclass/batch/legacy/detached values and extra override arguments are rejected.
- `grade_for_score(Decimal)`: pure exact finite `[0,100]` grading with no rounding.
- `__all__` exports only those three names. Raw arithmetic helpers are private and return ordinary visibly untrusted dicts.
- Canonical schema: `schema_version=formal-pre-policy-score-v1`, `calculation_stage=pre_policy`, `policy_final=false`.
- Exact score fields: immutable `dimensions`, `dimension_grades`, `global_slot_weights`, `confidence` (`D/P/H/K/C`), `S0/Sc/Sbase/B`, `M_persistence`, `CA_downside`, `R_safety`, `risk_exposure`, and grades only for higher-is-better values. There is deliberately no confidence or risk-exposure grade.
- Audit fields: full detached canonical source payload, source canonical SHA256, calculation hash, and all input/batch/metric-batch/manifest/registry/frozen-input/universe/population/security/template/cutoff bindings.
- This type is deliberately not `FormalScoreCard`, contains no Task 4 policy/cap/veto/pool decision, and is not a final pool input.

## Authenticity and arithmetic design

- The private result record strongly owns the genuine source while the registry holds only a weak result reference; the source has no descendant reference.
- Captured inherited source `require_verified`, `canonical_bytes`, and field methods are checked at calculation start/end, immediately before return, and on every result field/method read. The exact source bytes are compared each time, so later source revocation revokes the descendant.
- Source/result class and method replacement plus calculation, Decimal-context, canonicalization, hashing, freezing, stdlib-module, and immutable-formula dependency replacement fail closed. Tests restore every patched dependency and re-verify the result.
- All 25 dimension-qualified slots, signed dimensions/internal weights, evidence kinds, actual evidence precision, registered neutral context/rule, cap agreement, and dimension/global totals are validated. Quality is recomputed from underlying refs (or the actual neutral Context calendar binding), not trusted from a caller.
- Arithmetic uses the fixed precision-50 `ROUND_HALF_EVEN` context and prescribed intermediate divisions. `M.return_persistence` is distinct from `CA.return_persistence`. No missing redistribution, float, ambient Decimal context, display quantization, normalized-profit substitution, policy adjustment, or risk-direction inversion occurs.
- Complete arithmetic, calculation hash, frozen payload, and canonical bytes are prepared before proof allocation; source bytes are rechecked after registration and immediately before return.

## TDD evidence

Python runtime for every command below:
`C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

### Meaningful initial RED (before production module)

Command:
`<python> -m unittest tests.test_formal_scoring`

Output/timing (chunk `835a27`):
```text
FF
Ran 2 tests in 0.001s
FAILED (failures=2)
DURATION_SECONDS=0.928
```
Both failures were the intended assertion: `ashare_pipeline.formal_scoring` was absent. This RED contained the exact grade-boundary and prescribed hand-arithmetic tests and did not build a fixture.

Initial minimal GREEN (chunk `27c20d`), same command:
```text
..
Ran 2 tests in 0.005s
OK
DURATION_SECONDS=0.12
```

### Confidence RED/GREEN

After first observing missing-helper `AttributeError`, the tests were corrected to make missing behavior an assertion failure and RED was rerun.

Command:
`<python> -m unittest tests.test_formal_scoring`

RED output/timing (chunk `37a06e`):
```text
F..F
Ran 4 tests in 0.002s
FAILED (failures=2)
DURATION_SECONDS=0.112
```
Both intended failures were `confidence arithmetic helper is missing`.

GREEN output/timing (chunk `8aa6b3`):
```text
....
Ran 4 tests in 0.003s
OK
DURATION_SECONDS=0.123
```

### Authenticated entry-point RED

Command:
`<python> -m unittest tests.test_formal_scoring.AuthenticatedPrePolicyScoringTests.test_default_linked_covered_input_mints_distinct_immutable_pre_policy_audit`

Output/timing (chunk `34a303`):
```text
F
Ran 1 test in 0.001s
FAILED (failures=1)
DURATION_SECONDS=1.232
```
The intended failure was `authenticated pre-policy entry point is missing`; the assertion occurred before fixture construction.

### Source-backed fixture evidence

Default-linked covered command:
`<python> -m unittest tests.test_formal_scoring.AuthenticatedPrePolicyScoringTests.test_default_linked_covered_input_mints_distinct_immutable_pre_policy_audit`

- First execution reached the scorer but found a test-shape error: comparing the immutable live audit (mapping/tuples) directly with detached dict/lists. Chunk `4851da`: one failure, test `41.748s`, wall `42.104s`. The assertion was corrected to compare `result.to_dict()["source_input"]`; production immutability was retained.
- GREEN chunk `da9571`:
```text
.
Ran 1 test in 88.401s
OK
DURATION_SECONDS=88.951
```
- Coverage: default `ScoreFixture(linked=True)`, focal `BJ430001`, actual covered consensus receipt, 4FY, all 25 slots/seven dimensions, `H=.8`, `P=1`, `C=.98`, immutable/deterministic audit, strong source ownership, construction/copy/raw/detached rejection.

Cyclic/date-only neutral revocation command:
`<python> -m unittest tests.test_formal_scoring.AuthenticatedPrePolicyScoringTests.test_revoked_tentative_source_revokes_cyclic_date_only_neutral_descendant`

GREEN chunk `b394da`:
```text
.
Ran 1 test in 349.033s
OK
DURATION_SECONDS=349.398
```
- Coverage: genuine `cyclic=True`, 5FY (`H=1`), actual date-only no-coverage expectation (`q=.025`, `P=.995`, cap-last `C=.90`), explicit pre-policy/no risk-exposure grade, and descendant revocation after a genuinely leaked tentative source fails its outer guard.

The two integration GREEN runs preceded the final self-review rename to the brief's exact public symbols (`S0/Sc/Sbase/B/...`) and added dependency checks. Their intermediate source hash was not captured and must not be attributed to the frozen hash above. Per parent instruction, they were not repeated; the parent's post-freeze full `tests.test_formal_scoring` run is the authoritative source-backed verification for the frozen hashes.

Post-self-review production changes were: (1) replacing lowercase/descriptive arithmetic fields with the brief's exact `S0/Sc/Sbase/B/M_persistence/CA_downside/R_safety` API, (2) preparing frozen/canonical payload bytes before proof allocation, and (3) extending captured dependency checks to `_plain`, immutable formula constants, imported source/module/class identities, JSON dump/load, SHA256, weak references, MappingProxyType, and Decimal context globals. There was no separate focused RED before these self-review edits; the exact-symbol test expectation and production rename were changed together. This is a disclosed TDD process gap. The corresponding frozen-hash GREEN is the five-test pure command below plus `py_compile`; exact-hash authenticated GREEN remains pending the parent's planned full-file run.

### Fresh frozen-hash focused verification

Command:
`<python> -m unittest tests.test_formal_scoring.PureScoringArithmeticTests -v`

Output/timing (chunk `c63e40`):
```text
test_confidence_uses_weighted_quality_history_and_cap_in_that_order ... ok
test_grade_boundaries_use_unrounded_finite_decimals ... ok
test_hand_example_preserves_specified_intermediate_divisions ... ok
test_pure_arithmetic_ignores_hostile_ambient_decimal_context ... ok
test_raw_helpers_reject_partial_reweighted_or_ambiguous_inputs ... ok
Ran 5 tests in 0.003s
OK
DURATION_SECONDS=0.363
```

Compile command on the frozen hashes:
`<python> -m py_compile ashare_pipeline\formal_scoring.py tests\test_formal_scoring.py`

Chunk `cc01ac`: exit `0`, no output, `0.154s` tool wall time. A separate trailing-whitespace check returned `NO_TRAILING_WHITESPACE` (chunk `f09749`).

## Self-review and concerns

- Seven tests exist: five pure tests and exactly two expensive genuine source-backed integrations.
- Pure coverage includes every grade boundary and adjacent unrounded values, invalid types/ranges/nonfinite values, exact hand constants including the required final risk digit, D/P/H/K/C examples, cap-last behavior, hostile ambient Decimal context, partial/reweighted slot maps, and ambiguous same-name dimension selectors.
- Authenticated coverage includes default linked covered success, exact source/audit bindings, deterministic canonical hash, immutable nested fields, detached lifetime, constructor/copy/forged/raw/legacy/batch/subclass/override rejection, captured dependency restoration, cyclic/date-only neutral arithmetic, and transitive revocation.
- Concern requiring parent verification: the final exact-symbol/API-hardening changes are compile- and pure-tested but were made after the two expensive GREEN runs. Parent should run the complete seven-test module on the frozen hashes as already planned. The revocation case uses narrowly scoped `sys.setprofile` around the genuine build and took about 349 seconds; preserve its active session if it appears quiet.
- TDD concern: the post-self-review changes listed above do not have their own prior RED. Do not characterize the frozen source as a fully clean per-change RED/GREEN cycle unless the parent independently establishes that evidence.
- No other known contract gap was found in final line-by-line review of the active Task 3B brief.

## Fix round 1 — class dispatch and exported-class substitution

### Reviewed finding and root cause

Independent review found that class-level descriptors and methods resolved before `Proof.__getattr__`, so a new `S0` property returned arbitrary data and a replaced `require_verified` method returned success even for `object.__new__(PrePolicyScoreCalculation)`. Investigation also confirmed that the `PrePolicyScoreCalculation` reference inside `dependencies()` resolved to the nested class's closure-local binding, not the replaceable module export; consequently the original linked-covered test's module-export substitution did not raise.

The root causes were therefore both at dispatch, not in `proof_record`: (1) validation occurred only after ordinary lookup failed, and (2) the module export was never actually consulted. The fix guards instance attribute resolution before dispatch, validates the exact class-member set and identities without depending on namespace insertion order, checks the actual module globals mapping for the exported class, and uses a narrow metaclass rule to prevent replacement/removal of the `__getattribute__` guard itself. Other supported class-member substitutions remain possible so tests can prove they fail on access and restore cleanly.

The revoked-descendant regression was also changed from eagerly retrieving bound methods to lazy lambdas. This keeps both attribute resolution and invocation inside `assertRaises` now that revocation is enforced during method lookup.

### Focused TDD evidence

Initial dispatch RED command:
`<python> -m unittest tests.test_formal_scoring.ProofDispatchGuardTests -v`

Output/timing (chunk `cd4393`):
```text
test_class_descriptor_cannot_shadow_forged_field_rejection ... FAIL
test_module_export_class_replacement_is_detected_then_restores_normal_rejection ... FAIL
test_replaced_verification_method_cannot_bypass_forged_rejection ... FAIL
Ran 3 tests in 0.004s
FAILED (failures=3)
DURATION_SECONDS=0.39
```
The failures respectively proved the property returned without validation, exported-class replacement reached the ordinary forged error rather than the dependency guard, and the replaced verifier returned without validation.

Guard-self RED command:
`<python> -m unittest tests.test_formal_scoring.ProofDispatchGuardTests.test_attribute_resolution_guard_itself_cannot_be_replaced -v`

Output/timing (chunk `f80f13`):
```text
... (owner='PrePolicyScoreCalculation') ... FAIL
... (owner='Proof') ... FAIL
Ran 1 test in 0.003s
FAILED (failures=2)
DURATION_SECONDS=0.34
```
Both proof classes permitted replacement of the newly introduced dispatch guard before the bounded metaclass rule was added.

Focused guard GREEN command:
`<python> -m unittest tests.test_formal_scoring.ProofDispatchGuardTests -v`

Output/timing (chunk `26d8ef`):
```text
test_attribute_resolution_guard_itself_cannot_be_replaced ... ok
test_class_descriptor_cannot_shadow_forged_field_rejection ... ok
test_module_export_class_replacement_is_detected_then_restores_normal_rejection ... ok
test_replaced_verification_method_cannot_bypass_forged_rejection ... ok
Ran 4 tests in 0.007s
OK
DURATION_SECONDS=0.333
```

Combined cheap regression command:
`<python> -m unittest tests.test_formal_scoring.PureScoringArithmeticTests tests.test_formal_scoring.ProofDispatchGuardTests -v`

Output/timing (chunk `9010e9`): all 5 pure arithmetic tests and all 4 dispatch-guard tests passed; `Ran 9 tests in 0.004s`, `OK`, `DURATION_SECONDS=0.494`.

Compile command:
`<python> -m py_compile ashare_pipeline\formal_scoring.py tests\test_formal_scoring.py`

Chunk `b20356`: exit `0`, no output.

### Frozen-hash genuine integration

Fix-round frozen SHA256, independently matched by the parent before heavy verification:

- `ashare_pipeline/formal_scoring.py`: `b3bede39fe332ba9eb27ef8272207717705e5d2ab74b918db1a7f73d20ed6b18`
- `tests/test_formal_scoring.py`: `72469344b328b62c04d67523915b211f4d51423c94bd0ec667cf2a02da6c3392`

Linked-covered command on those exact hashes:
`<python> -m unittest tests.test_formal_scoring.AuthenticatedPrePolicyScoringTests.test_default_linked_covered_input_mints_distinct_immutable_pre_policy_audit -v`

Output/timing (session `98681`, chunk `7799bc`):
```text
test_default_linked_covered_input_mints_distinct_immutable_pre_policy_audit ... ok
Ran 1 test in 124.161s
OK
DURATION_SECONDS=124.595
```

This genuine test now covers normal result reads, forged/raw rejection, class-property shadowing on a registered result, direct invocation of a replaced `require_verified`, actual module-export class replacement, every dependency restoration, immutable audit/hash determinism, and the default linked-covered 25-slot/7-dimension confidence path.

Production and test files were frozen at `2026-09-09T11:00:26.8547573+04:00` before this integration and still matched the hashes above afterward. The parent owns the complementary final-hash revoked cyclic/date-only neutral integration and affected contract/arithmetic suite; it was running separately at report time. No broad suite was duplicated.

### Fix-round concerns

- The `__getattribute__` guard is protected by a deliberately bounded proof-class metaclass rule. This addresses ordinary proof class/base method substitution without claiming defense against mutation of Python's interpreter or metaclass machinery itself.
- The original report's disclosed pre-fix TDD gap remains historical fact and has not been rewritten. Fix round 1 itself has the focused failing and passing evidence above.
- No Git/index/data/network/fixture/source-boundary operation was performed; the pre-existing `tmpj4zv9_fq/` remains untouched.

## Fix round 2 — inheritance replacement of the dispatch guard

### Finding and bounded fix

A parent `-B` probe showed that ordinary assignment to the exact exported proof class's `__bases__` could replace inherited `Proof.__getattribute__` before any proof validation ran. A layout-compatible `AlternateBase` returning `Decimal("99")` made a forged result's `S0` read return `99`; restoration of the original bases restored the normal forged-proof error.

The minimal fix extends the existing bounded `ProofMeta` mutation rule from `__getattribute__` to `__bases__` for both replacement and removal. It does not change arithmetic, source ownership, serialization, or the supported patch-and-restore path for ordinary fields/methods. The existing round-1 descriptor/verifier/export/restoration regressions remain intact.

### Exact RED/GREEN evidence

Focused RED command on round-1 production:
`<python> -B -m unittest tests.test_formal_scoring.ProofDispatchGuardTests.test_attribute_resolution_guard_cannot_be_removed_by_replacing_inheritance -v`

Output/timing (chunk `3d3894`):
```text
test_attribute_resolution_guard_cannot_be_removed_by_replacing_inheritance ... FAIL
AssertionError: TypeError not raised
Ran 1 test in 0.107s
FAILED (failures=1)
DURATION_SECONDS=11.281
```
The regression's `finally` restored the original bases, after which the normal forged-object rejection was exercised.

Focused GREEN command, identical to RED (chunk `29010d`):
```text
test_attribute_resolution_guard_cannot_be_removed_by_replacing_inheritance ... ok
Ran 1 test in 0.086s
OK
DURATION_SECONDS=3.491
```

Covering cheap command:
`<python> -B -m unittest tests.test_formal_scoring.PureScoringArithmeticTests tests.test_formal_scoring.ProofDispatchGuardTests -v`

Output/timing (chunk `3d0619`): all five pure arithmetic tests and all five dispatch-guard tests passed; `Ran 10 tests in 0.005s`, `OK`, `DURATION_SECONDS=0.489`.

Compile command:
`<python> -B -m py_compile ashare_pipeline\formal_scoring.py tests\test_formal_scoring.py`

Chunk `628ba7`: exit `0`, no output.

### Frozen hashes and verification boundary

Frozen at `2026-09-09T11:12:16.5462504+04:00`:

- `ashare_pipeline/formal_scoring.py`: `7de79034bbbec7147768fac3f58b07d0ea54be4d4ba9fac291f08eebb12953d5`
- `tests/test_formal_scoring.py`: `486c3a9f6c98c1f1e24e3f1fefb6144db8aca06ff15e73bcc7caf46f93c58ce5`

No genuine fixture was run in this narrow round, as directed. Round 1's frozen-hash linked-covered integration had already passed, and this round changes only the proof-class mutation guard. The parent owns any final scoped genuine verification. No further production/test changes were made after the covering GREEN and hash capture.

No Git/index/data/network/fixture/subagent operation was performed; the pre-existing `tmpj4zv9_fq/` remains untouched.
