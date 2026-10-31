# SDD ledger — plan: docs/superpowers/plans/2026-09-25-formal-valuation-policy-adapter-stage-c.md

Workspace: D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation
Branch: codex/formal-v3-implementation
Plan start HEAD: a5777b2
Baseline: 73 registry/scoring/policy tests passed in 81.761s on a5777b2.

## Pre-flight task/interface scan

| Tasks | Producer → consumer or internal consistency | Finding |
| --- | --- | --- |
| C1 | v1/v2 manifest tests against versioned role implementation | Clean: exact nine/ten role behavior, default v1 fixture and v2 mutation are aligned. |
| C2 | adapter child tests against loader/dataclass/metric-definition extraction | Plan defect: fixture pseudocode reads `rule["rule_id"]`, but raw policy documents identify rules by mapping key. Ruling recorded below. |
| C3 | state tests against pure Decimal and adjustment APIs | Clean: every named status and invalid operand has an implementation step. |
| C4 | complete-batch tests against repository/proof/guard implementation | Clean: constructor inputs, three V metrics, shared publication capability and real fixture are specified. |
| C5 | ranking/diagnostic tests against peer/score APIs | Clean: cohort semantics, caching, proof binding and acceptance commands are specified. |
| C1 → C2 | `formal-registry-manifest-v2`, adapter child and bundle role access → adapter contract loader | Clean: C2 consumes only the v2 capability C1 produces; old v1 remains readable. |
| C1 → C4 | manifest-version fixture plumbing → v2 runtime fixture | Clean: defaults preserve old tests; C4 opts into v2 explicitly. |
| C2 → C3 | immutable dependency/adapter definitions → detached pure state machine | Clean: C3 consumes serialized copies and does not mint authority. |
| C2 → C4 | official adapter registry and fixture helper → complete adjusted batch | Clean subject to the rule-id ruling below. |
| C3 → C4 | `evaluate_valuation_adjustment` → row preparation | Clean: metric-level pending/invalid states remain rows rather than aborting the batch. |
| C4 → C5 | `PolicyAdjustedValuationBatch` and shared publication capability → peer context and score | Clean: C5 extends the same engine file and proof closure without changing raw inputs. |
| C2 ↔ C4 | `tests/formal_policy_fixtures.py` and runtime fixture graph composition | Clean: C2 owns adapter document authoring; C4 only activates it through an explicit option. |
| C4 ↔ C5 | `formal_valuation_engine.py` batch internals → cohort cache and diagnostics | Clean: C5 builds on C4 private indexes and does not alter C4 public batch identity. |

Ruling: In C2 fixture authoring, obtain `rule_id` from the cyclic registry mapping key and pass `(rule_id, rule)` together; do not read a nonexistent `rule["rule_id"]` field — raw Stage A documents key rules externally, while parsed runtime rules may carry the ID — if wrong, the fixture could sign an adapter against no real policy rule and invalidate all downstream tests.

## Task status

C1: complete
C2: complete
C3: complete
C4: complete
C5: complete
Stage C: complete

Ruling: C1 may make the smallest compatibility change in `ashare_pipeline/formal_feature_contract.py` and its focused tests so feature-registry root validation accepts the manifest's exact active role set for both v1 and v2 — the v2 fixture must load a genuine vocabulary before C2 can bind adapters, while feature semantics must remain limited to source/mapping/feature — if wrong, shared feature validation could either reject every v2 graph or accidentally treat adapter content as a feature dependency.

C1 downstream concern: `formal_financial_features.py` and `state_store.py` still enumerate nine root hashes and may reject v2 through exact `assert_member_hashes`; intentionally not expanded into C1. Carry this into the first task that exercises runtime v2 financial/state persistence, expected C4.

Task 1: complete (commits a5777b2..5e36b41, review clean; 22 focused and 142 listed regression tests passed).

Task 2 review gate: candidate `6911834` requires fixes for three Important trust-boundary findings: adapter constructor substitution, unclosed `FormalScoringRegistry.template_for` dependency, and direct `require_official` method substitution. No Critical or Minor findings.

Task 2 fix review: commit `4f7a612` closes the first three findings, but the same shared-producer dependency chain still leaves `formal_metric_engine._canonical` replaceable when deriving `original_definition_hash`; one Important fix remains.

Task 2 dependency-chain reviews: `fddab7c` closed direct `_canonical` replacement; `a83668c` closed project-owned `_plain`/`fields`/`json` replacements. One Important encoder-primitive boundary remains because captured `json.dumps` still dynamically resolves `json.JSONEncoder` and its implementation path.

Task 2: complete (commits `6911834`, `4f7a612`, `fddab7c`, `a83668c`, `aaa06e9`; final independent review clean; 123 C2 compatibility and 19 metric-engine tests passed). The encoder-primitive boundary now covers ordinary module-binding and class-attribute substitution while preserving the pinned definition hash.

Task 3 review gate: candidate `228b33f` requires three Important fixes: accept C2 canonical wire lists for adapter preconditions, remove fixture-specific rule-id derivation, and isolate Decimal parsing from ambient traps. No Critical or Minor findings.

Task 3: complete (commits `228b33f`, `5516548`; final independent review clean; 13 focused and 70 C3/C2/affected regression tests passed). Canonical C2 wire lists, arbitrary signed rule IDs, and ambient Decimal trap invariance are covered.

C4 prerequisite performance optimization: complete (commits `38f18b9`, `defd528`; final independent review clean). Repeated scoring official verification preserves one full feature fingerprint while eliminating discarded five-template/125-slot rematerialization; focused 22, guard 67, and range-contract 17 tests passed. The broader 263-test run was stopped in the late range store/worker group after one test produced no output for over 15 minutes and is not claimed as passed.

C4 prerequisite range-current optimization: complete (commits `c28ad97`, cleanup `41b38b15`, fixes `b9951e68`, `c634d5b6`; final independent review clean). First load still derives the complete range graph and verifies again before publication; current reads revalidate exact source snapshots without rebuilding definitions/bindings. Final focused suite: 29 tests passed. The mistakenly tracked coordination report was removed in the cleanup commit and remains only in the ignored SDD directory.

C4 prerequisite single-call authentication optimization: complete (commit `0a252fb`; independent review clean). Adapter policy proof reads and range snapshot source authentication now reuse one owner-authenticated wire per call while preserving object-identity and cross-root checks; 91 targeted contract tests passed.

Perf4a owner-ticket foundation: complete (commits `ec7f550`, fixes `ee2bbc2`, `5cb3e64`; independent review clean). Build-local journals and feature/Context/range tickets bind the exact selection token, candidate set, bundle/receipt, owner, phase, population, and source evidence without changing production build flows.

Perf4a2 policy evidence tickets: complete (commits `d5df5cc`, fixes `8a73af8`, `72f7946`; test-isolation fixes `930e1d2`, `750e091`; independent reviews clean). Financial/state/market/calendar/PolicyFeatureState tickets and range absence are owner-minted from the same selection evidence; market constructor and test-process isolation guards are covered.

Perf4b composite policy journal: complete (commits `c89f9da`, fix `4a60f6e`; independent review clean). First policy selection runs once per member; preparation and policy-finalize checkpoints each revalidate full phase/member coverage. Public `recheck_current` remains a full independent reselect, and private owner scopes are consumed on every early failure.

C4 final implementation and hardening: complete (commits `493e88d`, `8e43eb9`,
`2434712`, `a3984ed`, `1af0e2b`, `bf0f694`, `a484cfe`, `ae3828d`,
`237b907`). Final independent review of `237b907` and the operation-scoped
range read lease was clean. Exactly one authorized final 20-member full-module
acceptance ran `python -u -m unittest tests.test_formal_valuation_batch -v`:
policy/metric production completed at approximately 8.5 minutes, final closure
completed after approximately 29 minutes, and the module passed 2/2 with exit
code 0 in 2409.766 seconds. HEAD and the tracked worktree remained clean; no
report, data, SQLite/WAL/SHM, or progress artifact was committed, and nothing
was pushed.

C5 final implementation, hardening, baseline-debt repair, diagnostic capture,
and evidence closure are complete. The independent whole-branch review was
CLEAN. At final implementation HEAD `f399d07`, the root agent ran the six Stage
C modules fresh from the beginning: 88/88 tests passed in 11875.957 seconds,
with 0 failures, 0 errors, 0 skips and exit code 0. The exact 23-member
diagnostic snapshot is recorded in ignored `task-C5-report.md`; Stage C is
complete. No report, data, SQLite, WAL/SHM, or progress file is included in the
tracked submission, and nothing was pushed or merged.
