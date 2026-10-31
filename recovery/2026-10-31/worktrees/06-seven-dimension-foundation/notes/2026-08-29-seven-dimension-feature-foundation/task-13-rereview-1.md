# Task 13 Fix Round 1 Re-review

## Finding verdicts

### 1. ADDRESSED

原 finding：“二次重放”复用同一 harness 和已持久化结果，没有重新构建，确定性比较近乎同值自比。

修复现在从同一 `replay_inputs` 分别构造两个 `HermeticDeepHarness`（`tests/test_feature_foundation_e2e.py:233`、`tests/test_feature_foundation_e2e.py:234`），各自只执行一次 `run()`（`tests/test_feature_foundation_e2e.py:238`、`tests/test_feature_foundation_e2e.py:239`），并明确验证两个临时 project root 不同（`tests/test_feature_foundation_e2e.py:241`）。每次 `run()` 都从自己的 StateStore 执行真实 `run_deep`，随后要求每个预期 security 都存在 current bundle，否则直接失败（`tests/test_feature_foundation_e2e.py:171`、`tests/test_feature_foundation_e2e.py:188`、`tests/test_feature_foundation_e2e.py:194`）。最后比较两个独立构建的 canonical bundle bytes（`tests/test_feature_foundation_e2e.py:244`）。这符合 controller 对“两个独立 hermetic harness 重建并比较 bytes”的绑定裁定。

`DeterministicUuid4` shim 不使该证明失效。它为每个 harness 分别提供从同一初值开始的 UUID 序列（`tests/test_feature_foundation_e2e.py:81`、`tests/test_feature_foundation_e2e.py:96`），patch 点仅是 StateStore 所使用的随机 surrogate-ID 来源（`tests/test_feature_foundation_e2e.py:115`）；初始化、入队、snapshot persistence 和 deep run 均在各自的固定序列上下文中执行（`tests/test_feature_foundation_e2e.py:98`、`tests/test_feature_foundation_e2e.py:151`、`tests/test_feature_foundation_e2e.py:171`）。它没有替换 deep planning、financial normalization、feature/bundle construction、canonical serialization 或 verification。固定本来随机且会进入 evidence bytes 的代理 ID，是让两个独立状态库拥有相同测试输入的一部分；若两次执行的 ID 分配顺序或任何 canonical bundle 字段发生偏差，bytes 比较仍会失败。

### 2. ADDRESSED

原 finding：blocker 测试的 `all(...)` 可在零 bundle 时误通过，且两个分支都只检查包含关系，没有执行“精确 blocker”契约。

两个分支现在都先断言恰好一个 bundle（`tests/test_feature_foundation_e2e.py:342`、`tests/test_feature_foundation_e2e.py:350`），再分别断言目标 security 和精确 `blocked` 状态（`tests/test_feature_foundation_e2e.py:344`、`tests/test_feature_foundation_e2e.py:345`、`tests/test_feature_foundation_e2e.py:352`、`tests/test_feature_foundation_e2e.py:353`）。blocker 断言已经改成完整 tuple 相等，而不是 `in`/`all`/`any`（`tests/test_feature_foundation_e2e.py:346`、`tests/test_feature_foundation_e2e.py:354`）。零 bundle、多 bundle、额外 blocker、缺失 blocker 或错误顺序都会失败；原空集合与宽松匹配路径已关闭。

### 3. ADDRESSED

原 finding：evidence 验证没有断言任何非空 value/fact/evidence，七维全部为空时三层循环不会执行。

测试现在分别要求工业 facts、银行 facts、工业 feature values、工业 evidence refs 非空（`tests/test_feature_foundation_e2e.py:260`、`tests/test_feature_foundation_e2e.py:261`、`tests/test_feature_foundation_e2e.py:262`、`tests/test_feature_foundation_e2e.py:263`），并在完成所有 bundle 的逐 ref fact/snapshot 校验后再次要求全局 evidence 集非空（`tests/test_feature_foundation_e2e.py:284`）。因此七维存在但 values/evidence 全空时不再可能通过。

## Covering commands/results in implementer report

覆盖证据齐全：报告记录了本轮定向 RED（`task-13-report.md:112`），定向 GREEN 为 3/3、exit 0（`task-13-report.md:129`），相关回归为 243/243、exit 0（`task-13-report.md:137`），完整回归为 337/337、exit 0（`task-13-report.md:145`）。本次只读复审按要求未重跑这些命令。

## New Critical/Important breakage

无。修复包只修改 `tests/test_feature_foundation_e2e.py`，未见修复三项 finding 时引入新的 Critical 或 Important 破坏。

## Out-of-scope observations

- 既有 `SZ000002` → `SH600002` 测试别名限制未在本轮改变；它仍不证明交易所前缀一致性，但不影响本轮三项 finding 的关闭。
- 报告仍记录既有 Windows line-ending notice、`.tmp-root-check/` access warning 与 controller-owned `.tmp-tests/`（`task-13-report.md:147`、`task-13-report.md:159`）。它们未由本轮 fix diff 引入，按本轮限定范围为非阻塞观察。
- 线上 operational acceptance 仍未执行；这是 Task 13 代码 review 之后的独立运营步骤，不属于本轮三项修复。

## Overall

**All findings addressed. Task 13 fix round 1 is approved for the scoped gate.**
