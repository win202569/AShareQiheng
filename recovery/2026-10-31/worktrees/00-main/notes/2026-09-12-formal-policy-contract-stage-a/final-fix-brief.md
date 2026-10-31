# Stage A integrated fix — selector discriminator

BASE 101d42a24a29fce9f5d101760350ba598cea1630, branch codex/formal-v3-implementation.
Worktree D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation.
Python D:/Projects/AShareQiheng/.venv/Scripts/python.exe.

Read final-review-result.md in this workspace first; it is the consolidated independent review finding. The approved spec is docs/superpowers/specs/2026-09-12-formal-policy-contract-design.md. This is the one bounded final-review fix dispatch, not permission for redesign or new Stage B/C work.

## Root cause and required outcome

A1 _selector currently allows kind=feature/annual_series even when expected_kind describes a Context value (bool, enum, market_record, calendar_record). A2 can bind those signed features and A3 can authenticate a malformed mandatory market rule or extra state rule. Mandatory ST instead crashes with KeyError. Parent inspected the exact parser and coverage path and agrees with the reproduced finding.

Require the correct selector family before subtype dispatch: feature expectation -> feature; annual_series expectation -> annual_series; Context-typed expectations -> context, then the existing exact Context value-type check. Keep no-expectation generic syntax behavior unchanged. Unknown selector kinds still report unsupported_contract, malformed known-kind substitutions report PolicyContractError with a meaningful selector path. Do not blanket-catch downstream errors or weaken any existing input, canonical-number, fiscal-year, source, coverage or proof constraint.

Keep the production change local to existing _selector with no new dependency/global helper unless concretely necessary and reported; A3 captures that function already. Do not change the economic grammar to accept feature-valued booleans, listing state, market or calendar records.

## Allowed edits

- ashare_pipeline/formal_policy_contract.py
- tests/test_formal_policy_contract.py
- tests/test_formal_policy_registry_guards.py
- this workspace's final-fix-report.md

Do not modify registry binder/proof source, old modules, fixtures, data, SQLite/WAL/SHM, outputs, plan or unrelated tmpj4zv9_fq. All edits apply_patch; no Git writes, commits, network/DB, subagents/reviewers. Controller owns scope snapshot, re-review and commit.

## Required TDD and tests

1. Write actual failing tests first. At A1, cover BOTH feature and annual_series substitutions for each active Context-typed input (boolean/enum state, market and calendar separately); maintain positive accepted rule-family coverage and unsupported-kind errors.
2. Through genuinely signed policy_graph and the actual A3 public loader, separately reject malformed market and calendar inputs (not only a combined case that hides the second input), malformed additional boolean/enum state rules, and mandatory ST. Assert PolicyContractError rather than arbitrary exceptions; mandatory ST must not leak KeyError. Use existing synthetic helper factories and sign-before-load mutation; no fixture-only proof mint. Annual substitutions should be included at least in parser coverage and in meaningful end-to-end cases where cheap.
3. Record focused RED and GREEN counts/timings, then final policy suite: python -m unittest tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v. Keep source/tests frozen for final run. No need to repeat unchanged 72 legacy and 10 arithmetic/dispatch suites unless the change creates a concrete extra risk; parent runs appropriate independent verification.
4. When focused GREEN and files frozen, append that evidence/hashes to report and send checkpoint so parent can prepare scoped re-review while full final suite runs. Append final result without altering code/tests.
5. Self-review exact accepted inputs, error code/path semantics, cross-stage rejection and no extra API/dependency edits. Report no completion until the final suite exits successfully.

Full report path: .superpowers/sdd/2026-09-12-formal-policy-contract-stage-a/final-fix-report.md. Include actual RED/GREEN commands/output/count/time, final file hashes, self-review and any concerns. Short DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED handoff. The parent combined 168-suite may still run from the pre-fix imported snapshot; distinguish versions rather than treating it as corrected-tree verification.
