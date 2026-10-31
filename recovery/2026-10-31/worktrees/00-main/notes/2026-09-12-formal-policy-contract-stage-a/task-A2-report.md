# Task A2 implementation report

Status: DONE. All three task files are frozen for controller review. Controller owns independent review and Git writes.

Base verified: `6809363ed3e96f039fb300dbb9be36da40d49305`, branch `codex/formal-v3-implementation`, existing linked worktree. Initial status only `?? tmpj4zv9_fq/`; preserved. No AGENTS.md found in this worktree. Approved specification read from `docs/superpowers/specs/2026-09-12-formal-policy-contract-design.md` (the brief's relative link did not resolve from its copied location). ACTIVE handoff takes precedence over earlier plan text.

All commands below ran in `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`; Python is `D:/Projects/AShareQiheng/.venv/Scripts/python.exe`. Every edit uses apply_patch. No network, SQLite, production-data, Git-write, subagent, or reviewer actions.

## TDD evidence

1. Baseline: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_contract -q`
   Output: `Ran 28 tests in 0.057s`, `OK` (exit 0).
2. Initial RED: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_registry.PolicyBindingTests -v`
   Existing official feature/scoring loaders succeeded inside the fixture before the API import. Output: `ModuleNotFoundError: No module named 'ashare_pipeline.formal_policy_registry'`; `Ran 1 test in 0.402s`; `FAILED (errors=1)` (exit 1). This is the allowed missing-target-interface RED, not an environment or fixture failure.
3. Initial GREEN: same command. Output: `Ran 1 test in 0.607s`, `OK` (exit 0).
4. Selector RED: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_registry.PolicySelectorBindingTests -v`
   Output: `Ran 15 tests in 81.811s`; `FAILED (failures=30, errors=2)` (exit 1). Failures were accepted wrong selectors/scope/source/annual declarations (`AssertionError: PolicyContractError not raised`); two errors were absent binding-manifest entries (`StopIteration`). Context type/template cases already rejected by A1 remained passing. All graph mutations occur before signing and update hashes.

5. Selector GREEN: same selector command. Output: `Ran 15 tests in 65.889s`, `OK` (exit 0).
6. Coverage RED: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_registry.PolicyCoverageTests -v`
   Output: `Ran 13 tests in 63.005s`, `FAILED (failures=35)` (exit 1). All failures were `PolicyContractError not raised` for missing mandatory semantics, weaker/reversed vetoes, wrong fields, inactive/cross-template references, alias flags, or incomplete V dependencies. A1 duplicate-semantic and invalid dependency grammar cases already passed.
7. Coverage GREEN: same coverage command. Output: `Ran 13 tests in 23.079s`, `OK` (exit 0).
8. Compatibility RED: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_registry.PolicyCompatibilityTests -v`
   Output: `Ran 10 tests in 14.029s`, `FAILED (failures=1)` (exit 1). Only the additional signed regulatory semantic alias failed (`PolicyContractError not raised`). Existing root/content compatibility, copies, original verifier calls, metadata errors and v1/v2 checks passed.
9. Compatibility GREEN: same compatibility command. Output: `Ran 10 tests in 14.343s`, `OK` (exit 0).
10. Self-review characterization: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_registry.PolicySelectorBindingTests.test_matching_calendar_text_cannot_bind_sz_calendar_for_sh_and_bj -v`
    Initial expectation of an A2 PolicyContractError was incorrect: `Ran 1 test in 0.032s`, `FAILED (errors=1)`, with the existing earlier `ValueError: calendar selector exchange must match exchange_scope`. `FormalRegistryBundleLoader._read_blob` loads `SignedSourceRegistry`, whose `SourceAdapterConfig` already enforces this invariant. This is **not** an A2 RED. The characterization now preserves that earliest ValueError; controller explicitly agreed no duplicate validation should be added. Also corrected the descriptor/calendar-mismatch test to use valid `visible_at_freeze`, ensuring it exercises A2 mismatch validation rather than the calendar format parser.

## Final validation

- `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_contract tests.test_formal_policy_registry -v`: all named cases printed `ok`; `Ran 68 tests in 142.542s`, `OK` (exit 0). This is 28 unchanged A1 tests plus 40 A2 tests, including all subcases and the corrected upstream calendar-boundary characterization.
- `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_scoring_registry tests.test_formal_scoring_consensus_registry -v`: all named cases printed `ok`; `Ran 27 tests in 19.679s`, `OK` (exit 0).
- `git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation diff --check`: exit 0, no whitespace errors. Only the existing Git LF-to-CRLF advisory for the edited fixture.
- New untracked files also checked with `git ... diff --no-index --check -- NUL ashare_pipeline/formal_policy_registry.py` and the equivalent test-file command: no whitespace diagnostics; exit 1 means the new files differ from NUL, with LF-to-CRLF advisories.
- Final Git status: exactly the two new task files, modified `tests/formal_policy_fixtures.py`, and preserved `tmpj4zv9_fq/`. This report is in the ignored Stage A workspace. No unrelated tracked changes.

## Scope and self-review

- Fixture adds 80 active rules and 95 optional feature slots. Signed source configs cover SH/SZ/BJ without duplicating the original SZ entry. A1 helper defaults, mapping/source originals, inactive rules, classification, and v2 consensus entries/links are preserved.
- Root identity and all nine actual child hashes are bound; feature equivalence is genuine content/source/mapping equivalence, not an invented original minting-root identity. Changed definition text changes the root and output; unchanged genuine feature content can be reused under a different valid root, while changed feature content rejects the old object.
- The binder invokes captured original bundle/scoring/feature verification methods, including a captured slot lookup. Copy/mutation and shadowed verifier tests use the real sealed objects. A2 does not mint or expose a FormalPolicyRegistry.
- Selector binding indexes signed descriptors and source configs once, obtains fresh signed slots once per template in its own binding pass, and reuses existing `_formula_requirements` for complete AST periods. Existing scoring `require_official` also performs its required internal feature verification; its own calls are intentionally retained. No cross-load cache.
- Annual observation IDs and complete formula/unit/version fingerprints must differ within each series; every series unit matches its current scalar. Cross-year opening/closing balance formulas remain legal, with exact AST periods preserved.
- Context ENTRY hashes, full raw definitions, scopes, source identities, parser/mapping versions, calendar selectors, and all three exchange matches are validated. Source null-plus-exact ambiguity is rejected. Input-security bootstrap declarations are rejected under the controller ruling. Descriptor request/normalizer/generation fields stay signed and are preserved without claiming runtime installation.
- All five templates require the 16 approved semantics; mandatory delisting values are exactly `["delisting_arrangement"]`. Hard vetoes require both pools, regulatory flags cannot alias different active semantics, independent statuses retain explicit pools, and current-template V dependencies are exhaustive. A1 validates dependency identities/self-reference, versions/null declarations, exact constants and legal effects; A2 validates graph closure and target membership. Adapter names are never imported or executed.
- Every existing scoring entry and metric policy reference must be active; metric references must be same-template, with only the original cyclic classification exception. Cyclic classification remains the signed secondary-industry list.
- Output uses exact top-level fields and retains all 80 complete rule definitions and 170 selector binding entries, including original slot definitions/Context ENTRYs. No self hash, runtime security ID, actual values, computed readiness, evidence result, final score, or pool eligibility is added.

## Final source SHA-256

These are working-file byte hashes, before any controller Git line-ending normalization.

| File | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_policy_registry.py` | `3730be0a64008373c5dbdd56fabf0f47dc5e4d430a2fad3013f25ab962a5b9d7` |
| `tests/test_formal_policy_registry.py` | `b8ba421f18ead1ea5c03affa5db6590fcf7df0870c3ee8373c888ed5c9801f0e` |
| `tests/formal_policy_fixtures.py` | `fcbb488b82cd4ab5f63ebd5277cdd63adaeb30185a9551c1a9756f837a3ee5f8` |
| unchanged `ashare_pipeline/formal_policy_contract.py` | `d0d8de7b5e4e52c9715c51c36b097b1e3f72072f16cbadcaca42935029955fa4` |
| unchanged `tests/test_formal_policy_contract.py` | `e1cdf8ee724091ce6f8aea5982f1fb9f00368c7bfb4ee3054fa4ba8b9cd65f27` |
| unchanged `tests/fixtures/formal_v3_test_registry.json` | `e61b4e20dbfd03396614d392b13b781b59c436ce52676d88308c500cc33174c4` |

## Concerns and handoff boundaries

No unresolved implementation failure identified. Independent review remains the controller's responsibility.

- A2's private bytes are definitions, not a trusted policy proof. A3 must add the authenticated public entry and reading/dependency guards; this task does not claim those exist.
- Typed event_record syntax exists in A1, but no current active rule input family consumes it. Mandatory major_event uses the approved regulatory-state declaration. A2's Context helper includes event whitelist checking, but the active signed-graph tests exercise regulatory flags; the grammar was not widened to create an event executor. Event-record unit equality is a Stage B runtime concern, and no equality is claimed here.
- Production mappings, quantile choice, adapter implementations, market-window evidence, scoring and database integration remain outside A2. Synthetic signed declarations do not approve production economic equivalence or supply evidence.
