# 阶段 A 验收记录 — 完成

最终提交：29cf92362574945f9ca41d2c9374a56bcc9ffe90。
本阶段形成4个纯代码/测试提交，累计只涉及6个约定文件。所有单项审查及整体审查问题已修复并通过复审。

最终冻结版本：94项政策测试通过；另82项兼容回归通过，共176个不重复测试方法。未执行实际财报抓取、政策执行、正式评分或股票池生成。数据、SQLite/WAL/SHM、旧发布和历史进度均保留；未合并main、未推送。

下一步是另行设计阶段B运行证据层；本次未启动B/C。本阶段只认证政策定义，不认证任何证券已具备运行证据。

Plan: docs/superpowers/plans/2026-09-12-formal-policy-contract-stage-a.md
Code baseline: b9b367d64d1204985ddbea77e7ca6f7832694ae8
Worktree: D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation

## Acceptance matrix

| Boundary | Required evidence | Status |
| --- | --- | --- |
| A1 finite grammar | Exact types/keys, immutable detached parse values, finite algorithm IDs, preserved inactive canonical bytes | Approved; final integrated selector-family correction29cf923 preserves subtype/unknown-kind semantics;31 parser tests pass |
| A2 same-root binding | Actual verified root/nine roles, features/AST/units/periods, Context ENTRY and source matching | A2 commit 6ea72c1; independent task review Approved, no findings; parent 68 A1/A2 tests / 148.825s OK |
| A2 coverage | All five templates and 16 mandatory semantics each; unchanged hard vetoes/caps; complete V dependencies | Approved; separate signed market/calendar/state substitutions now fail at parser before binding |
| A3 authenticated definition | Private ownership, immutable payload, public loader only, repeat source authentication before reads | Approved; private proof boundary and no repeated policy parsing verified |
| A3 replacement guards | Copies, forged objects, changed inputs, class/module/method replacement fail closed; restore cleanly | Missing source exchange enum owner guard fixed; corrected full policy 86 / 275.907s and guard 18 / 125.243s OK; parent targeted new guard 1 / 1.931s OK |
| Stage boundary | No security values, evidence outcomes, final score, runtime readiness or stock pools minted | Integrated review Approved; definition objects and detached inputs rejected by original score entry |
| Legacy compatibility | Signed v1/v2, existing classification, old positive-price Context retained | Passed on final corrected tree,72 legacy plus10 arithmetic/dispatch tests |
| Scope preservation | Exactly six approved code/test files, no existing production modules/JSON fixtures/data changed | Final Git allowlist and9 file hashes verified; empty index/tracked clean; only preserved tmpj4zv9_fq untracked |

## Final corrected-tree evidence

- Worker full policy command below:94 tests /292.440s /OK /exit0, frozen source hashes rechecked afterward.
- Parent independent corrected-tree command: full parser module + PolicySignedSelectorFamilyTests + five legacy modules + PureScoringArithmeticTests + ProofDispatchGuardTests:118 tests /39.758s /OK /exit0 (94775 closed). This contains31 parser +5 signed-selector methods +82 legacy methods; its36 policy methods overlap the94 and are not added again.
- Parent focused selector verification:15 tests /12.611s /OK /exit0 (95734 closed).
- Final broad review's sole selector discriminator finding is ADDRESSED; scoped re-review found no new breakage/out-of-scope issue, conditional approval is now satisfied by the full corrected policy pass. Earlier A1/A3 findings also closed; no parked unresolved finding.
- Final post-commit verification: HEAD29cf923, branch codex/formal-v3-implementation, exact six-file cumulative allowlist, all six current file hashes and three protected legacy hashes match, diff --check passes, empty index and no tracked uncommitted change.

This is the approved Stage A offline acceptance scope, not a claim to have run every historical repository/database-backed integration test.

## Earlier baseline regression (retained for audit)

Pre-integrated-fix committed HEAD101d42a: parent combined168 tests /307.898s /OK /exit0 (38422 closed). This predates the added selector regression and is retained as baseline evidence only; the final evidence is above.

Use D:/Projects/AShareQiheng/.venv/Scripts/python.exe in the isolated worktree.

1. unittest tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v
2. unittest tests.test_formal_registry_manifest tests.test_formal_feature_contract tests.test_formal_scoring_registry tests.test_formal_scoring_consensus_registry tests.test_formal_context_schema -v
3. Git whitespace/scope/index/HEAD checks and unchanged legacy file hashes; all complete. No live data run.

## Protected legacy baseline hashes

Parent independent legacy regression during A3 (only new policy files changing, legacy files hash-checked unchanged):

- `python -m unittest tests.test_formal_registry_manifest tests.test_formal_feature_contract tests.test_formal_scoring_registry tests.test_formal_scoring_consensus_registry tests.test_formal_context_schema -v`: 72 tests / 29.737s / OK / exit 0; session 12918 closed.
- `python -m unittest tests.test_formal_scoring.PureScoringArithmeticTests tests.test_formal_scoring.ProofDispatchGuardTests -v`: 10 tests / 0.005s / OK / exit 0. Focused existing arithmetic and proof-dispatch compatibility; no database-backed scoring fixture invoked.
- The protected hashes below were independently rechecked unchanged again after final commit29cf923; final scope/hash gate passed.

- ashare_pipeline/formal_scoring.py: 7de79034bbbec7147768fac3f58b07d0ea54be4d4ba9fac291f08eebb12953d5
- tests/test_formal_scoring.py: 486c3a9f6c98c1f1e24e3f1fefb6144db8aca06ff15e73bcc7caf46f93c58ce5
- tests/fixtures/formal_v3_test_registry.json: e61b4e20dbfd03396614d392b13b781b59c436ce52676d88308c500cc33174c4

Preserve the existing untracked tmpj4zv9_fq/ and all plan-scoped progress artifacts. No main merge, push, cleanup or actual data collection/scoring is authorized in Stage A.
