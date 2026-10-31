# Stage A consolidated selector-family fix

Base: `101d42a24a29fce9f5d101760350ba598cea1630`.
Worktree: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.

## Focused RED / GREEN checkpoint

Read the final fix brief, consolidated review, approved design, and TDD / verification skill guidance. Added tests before changing production code. All commands ran from the worktree using the existing project Python; no Git writes, commits, network, fixture, data, database, binder/proof-source or upstream edits.

Exact focused command, executed once RED and once GREEN:

```powershell
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_contract.PolicySelectorSyntaxTests tests.test_formal_policy_registry_guards.PolicySignedSelectorFamilyTests -v
```

RED output summary (exit 1):

```text
Ran 15 tests in 16.147s
FAILED (failures=16, errors=6)
```

The 12 A1 feature/annual substitution subcases all failed with `PolicyContractError not raised`: boolean and enum values in both status/event roles, market alone, and calendar alone. Four genuinely signed A3 feature substitutions also failed with `PolicyContractError not raised`: market, calendar, additional boolean rule, additional enum rule. Mandatory ST leaked `KeyError: 'context_kind'` from coverage. All five A3 annual substitutions leaked `KeyError: 'expected_unit'` from annual binding. These six errors were the real missing-family-validation behavior reached through the public loader, not test setup errors. Graph creation/signing completed outside each `assertRaises`; no generic exception handler masks them.

GREEN output summary (exit 0), with the same unchanged tests:

```text
Ran 15 tests in 11.385s
OK
```

A1 now checks unknown selector kinds first (`unsupported_contract`, selector `.kind` path), then the expected family (`malformed_contract`, selector `.kind` path), then the existing exact subtype checks. Financial scalar expectations require feature; annual expectations require annual_series; Context value expectations require context. Generic no-expectation syntax is unchanged, including event_record. The existing Context expected_type check remains intact.

Tests add 12 parser rejection subcases and 10 genuinely signed public-loader rejection subcases, with exact error type/code/path assertions. Market and calendar are mutated separately. Extra boolean and enum rules are independently activated before signing; mandatory ST is independently replaced. Positive generic selectors and all accepted rule/role families, plus unknown-kind classification across each active input type, are covered.

Source/tests are frozen at this checkpoint; only this report may be appended during the final run. `git diff --check` produced no whitespace errors (Git reported its existing LF/CRLF conversion warnings). Scoped diff: 3 files, 127 insertions, 9 deletions. Existing unrelated `tmpj4zv9_fq/` is untouched.

Frozen SHA-256 hashes:

| File | SHA-256 |
| --- | --- |
| ashare_pipeline/formal_policy_contract.py | 27da74f7ce2be3aacceb333216ffeb28352e47fc875b6d2e0c0fd72667bc3fc0 |
| tests/test_formal_policy_contract.py | 91e070e34a84c7eb2aa228ba059473382cf0b30672c1a629548408f6de18bee9 |
| tests/test_formal_policy_registry_guards.py | 9ea749318118a96045e2965042317f0592c1cd319d3f7946a7e11cec6a030862 |

Self-review: the production change is confined to `_selector`, adds no helper/dependency/API, and does not accept financial booleans/enums/market/calendar records or weaken canonical numbers, years, source binding, coverage, or proof constraints. Existing A3 capture continues to own the same function. No runtime policy execution was added. Full final policy suite is pending; this checkpoint does not claim completion. Any parent pre-fix imported 168-test run is separate evidence and does not verify these corrected files.

## Final verification and handoff

Exact full command:

```powershell
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v
```

Final output (exit 0):

```text
Ran 94 tests in 292.440s
OK
```

All 94 methods passed, including all ten newly added genuinely signed A3 rejection subcases. The suite covers detached syntax, signed selector binding, mandatory coverage, v1/v2 and legacy compatibility, proof ownership/immutability, upstream dependency replacement, and absence of runtime scoring authority. The original 86 policy tests plus 8 added test methods account for the 94 total.

Recomputed all three SHA-256 hashes after the full suite: identical to the frozen checkpoint table above. No source/test changes were made after focused GREEN. Read-only final whitespace/status checks found no whitespace errors and the same three scoped source/test paths plus the pre-existing unrelated temporary directory; controller staging is outside this implementer's actions. The report is the only subsequent edit.

Final self-review confirms no new public API, dependency, helper, fixture, source binding, coverage or proof bypass; both selector families are rejected per Context input before A2/A3 can authenticate or crash on them. No additional production concern identified. The unchanged legacy and arithmetic/dispatch suites were not repeated, per the final fix brief.

Status: **DONE**. Implementation and full-suite verification complete; parent owns independent scoped review, snapshot and commit. No Git writes or commits performed by this implementer.
