# Formal Final Scoring Stage D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将同一正式冻结宇宙、同一 v2 十角色注册根下的 Stage B 政策批次和 Stage C 调整后估值批次，组合成可审计的最终七维评分、唯一状态、资格判断、最多 20/50 的确定性双池及追加式离线运行记录。

**Architecture:** 采用“分层证明链 + 纯函数核心 + 薄运行器”。D1 只组合真实来源证明，D2 只执行 cap 后最终 Decimal 评分，D3 分离状态/资格与池选择，coverage auditor 独立证明生产证据完备性，D4 通过一个 SQLite V8 原子提交入口保存全宇宙结果；B/C 已发布证明保持独立且不可改写。

**Tech Stack:** Python 3.11、`unittest`、闭包 mint 的不可伪造 proof、Decimal precision 50 / `ROUND_HALF_EVEN`、SQLite 事务与精确 DDL 校验、现有 Formal Universe/Registry/Feature/Metric/Policy/Valuation repositories。

**Spec:** [Stage D design](../specs/2026-09-28-formal-final-scoring-stage-d-design.md)；上位约束见 [正式评分与发布合同](../specs/2026-09-04-formal-scoring-release-contract-design.md)、[Stage B](../specs/2026-09-12-formal-policy-stage-b-design.md) 和 [Stage C](../specs/2026-09-25-formal-valuation-policy-adapter-stage-c-design.md)。

## Global Constraints

冻结时点固定为 `2026-08-31T07:00:00+00:00`。正式范围是该时点 SH/SZ/BJ 普通 A 股全集。

**版本纠偏：** 当前 `state_store.py` 的数据库 `SCHEMA_VERSION = 7` 已由四张正式 range 表占用。设计规格中“V7 persistence / V7 migration”是业务代际称呼；本计划的实际数据库迁移必须是连续 **V8**，不得改写 `_V7_TABLE_DDL` 或版本 7 migration。未来 release/publisher 若需要数据库迁移，顺延为 V9。proof schema 仍各自从 `...-v1` 起步，与数据库版本号分离。

七维权重、置信度、`S0/Sc/Sbase/B/R_safety/risk_exposure` 公式、等级、周期 cap、严格排除、资格阈值、排序、行业 4/10 和容量 20/50 完全继承规格，不在实现中增加隐式默认值。

D1 必须用 22 个真实非 V slot 加 3 个 Stage C 调整后 V percentile；原始 V percentile 只能用于来源闭合，不得进入最终 V。

完整批次必须枚举冻结宇宙每个成员。业务证据不足形成成员级 `pending_evidence`；跨根、跨 frozen input、跨 security、跨 batch、哈希或 proof 生命周期错误拒绝整批。

当前 `FormalFrozenUniverseInput` 已在提取阶段过滤非普通 A 股，因此 `out_of_scope` 保留为兼容枚举，但当前 genuine Stage D 批次必须为 0；调用方不得自行把冻结成员标成 out-of-scope。

状态优先级固定为 `out_of_scope > pending_evidence > pool_vetoed > formal_scored`。在当前普通 A 股批次中实际适用顺序从 `pending_evidence` 开始。pending 不得被已知 veto/cap 掩盖；单池 prohibition 只禁对应池，不自动变成 `pool_vetoed`。

数据库普通行和恢复 DTO 不是 proof。每次正式计算仍须验活 registry、来源批次、规范字节、哈希与 capability；缓存只能复用已验证的解析结果，不能缓存“当前有效”的结论。

长计算不得持有 SQLite 写事务。D1–D3 先形成未发布 prepared records，最终复验与全部 V8 行在一个短 `BEGIN IMMEDIATE` 中提交；事务内只把共享 publication gate 置为外部不可见的 `armed`，此时 `require_verified()` 仍失败。SQLite commit 成功后只执行预先验证、不可失败且不分配资源的 `committed` flip；commit 或之前任一点失败均 rollback 并 revoke。失败不撤销 genuine B/C 证明。

Task 2–6 的公开 builder 可独立发布组件 proof，供单元测试和只读组合使用；正式 runner 不持久化这些早已发布的对象。Task 9 为四个模块增加只供 exact `FormalFinalPublicationCoordinator` 使用的 sealed prepared adapter，共享一个 publication capability，在数据库最终集合复验成功后才一次开放。公开 builder 的签名与语义保持不变，prepared adapter 不导出 proof mint 权限。

Stage D 不访问网络、不生成 V9 release、不对外发布股票池。run mode 只允许 `test_preview/official_candidate`，run status 只允许 `preview_ready/blocked`。`official_candidate` 只有在 purpose=`official`、带批准身份的生产合同根和 official coverage gate 全通过时才允许，但仍只是 Stage D 的未发布候选，只有 V9 才能产生 `validated/published`；门闸未通过时拒绝 `official_candidate` mode，只能用 `test_preview` 保存 `preview_ready` 或 `blocked` 诊断。`test_preview` 可以消费 purpose=`test` 的 genuine 签名根，不能因此获得正式资格。

每个任务严格执行 RED → 最小 GREEN → 受影响回归 → 独立代码审查 → 修复 → 独立提交。不得同时实现后续任务；不得把用户数据、SQLite/WAL/SHM、进度文件或备份加入提交。

## Review Focus

1. 数据库 V7 不得被重用或扩写；Task 8 的 `test_v7_range_schema_and_rows_survive_v8_migration_exactly` 和 `test_v8_migration_is_atomic_and_reopen_verifies_exact_ddl` 固定此行为。
2. raw V 不得冒充 adjusted V；Task 2 的 `test_ready_input_contains_22_base_slots_and_exactly_three_stage_c_scores` 与 guard 测试固定此行为。
3. pending 优先于 veto，单池禁止不升级为双池 veto；Task 5 的 `test_pending_precedes_known_veto_and_emits_no_score_eligibility` 和 `test_single_pool_prohibition_only_blocks_that_pool` 固定此行为。
4. cap 只能降低指定维度，不改变 C；Task 4 的 `test_multiple_caps_take_minimum_without_changing_confidence` 固定此行为。
5. 阈值比较使用未舍入 Decimal；Task 5 的边界矩阵覆盖 `Sc=70/C=.75/M=EQ=FS=45/T=55/B=65` 及每项上下最小 Decimal 邻域。
6. 行业满额后继续扫描、容量不凑数、强池落选不流入 wait；Task 6 的三个容量测试固定此行为。
7. 缺表、空结果或超时不能冒充 `verified_no_coverage`；Task 7 的 `test_absent_record_is_blocked_not_verified_no_coverage` 固定此行为。
8. D4 任一点失败不得留下 torn result 或已公开 proof；Task 9 对 artifact/input/scorecard/status/eligibility/pool/dependency/final-recheck/arm/commit 边界逐点注入失败，并单测 commit 后不可失败 flip。
9. 增量重建由可信 manifest diff 推导，不能相信调用方提供的 changed IDs；Task 10 固定 security/cohort/policy/global 四类传播。
10. 大容量边界用纯选择核心快速测试；真实 20/23 证券 fixture 只做完整证明链集成和诊断。Task 6 的 20/50 纯核心测试与 Task 11 的 `tests/test_formal_final_integration.py`、`tests/test_formal_final_performance.py` 共同固定此分层，避免用弱 proof 换取速度。

---

## 文件图与执行顺序

新增生产模块：

- `ashare_pipeline/formal_final_score_inputs.py`：D1 完整最终输入 proof 和 repository。
- `ashare_pipeline/formal_final_scoring.py`：D2 cap 后评分纯核心及 scorecard proof。
- `ashare_pipeline/formal_final_eligibility.py`：D3a 唯一状态、门槛分解和资格 proof。
- `ashare_pipeline/formal_pool.py`：D3b 纯选择核心和双池 proof。
- `ashare_pipeline/formal_coverage_manifest.py`：coverage 主键、分类、验证 proof 和 production gate。
- `ashare_pipeline/formal_final_repository.py`：V8 唯一批量持久化入口和只读恢复 DTO。
- `ashare_pipeline/formal_final_invalidation.py`：依赖 diff 与重建范围。
- `ashare_pipeline/formal_final_runner.py`：无网络、无公式的薄编排器。

共享 fixture：`tests/formal_final_scoring_fixtures.py`。执行顺序固定为 Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11。Task 2–6 完成 D1–D3；Task 7 可由独立子代理与 Task 8 的 migration RED 并行准备，但合并顺序仍按任务编号。每项进入下一任务前必须由新的 reviewer 审查。

### Task 1: Build one genuine ten-role Stage D fixture graph

**Files:**
- Create: `tests/formal_final_scoring_fixtures.py`
- Modify: `tests/formal_valuation_fixtures.py`
- Create: `tests/test_formal_final_fixture.py`

**Interfaces:**
- Consumes: `ValuationRuntimeFixture`、v2 十角色签名图、真实 Formal Feature/Context/Metric/Policy/Range/Valuation producers。
- Produces: `FinalScoringFixture`；`populate_final_inputs(...)`；`build_d1_sources()`；可配置 20/23 人 cohort、pending、cap、prohibition、veto 和 consensus no-coverage，但不直接 mint 任何 proof。

- [x] **Step 1: 写失败测试。** 新增 `test_one_v2_root_builds_base_policy_and_adjusted_valuation_batches`，断言三批的 `registry_manifest_hash`、`frozen_input_hash`、`universe_hash`、`security_ids` 完全相同；新增 `test_fixture_never_exposes_proof_mint_or_plain_proof_double`，断言 fixture 无 mint API，返回值均为真实公开 proof 类型。
- [x] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture -v`

Expected: 因 fixture/module 不存在失败。

- [x] **Step 3: 最小实现。** 仅给 `ValuationRuntimeFixture.__init__` 增加默认 `None` 的 test-only 签名前文档配置回调；默认路径的签名字节和既有行为不得变化。新 fixture 在一个 v2 root 内配置完整 25 slots、consensus alternative、policy、range 和 valuation adapter。
- [x] **Step 4: 运行 GREEN 与 fixture 回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture tests.test_formal_valuation_integration tests.test_formal_score_inputs tests.test_formal_policy_integration -v`

Expected: 全部 PASS，现有 fixture 默认输出不变。

- [x] **Step 5: 独立审查并提交。**

```powershell
git add tests/formal_final_scoring_fixtures.py tests/formal_valuation_fixtures.py tests/test_formal_final_fixture.py
git commit -m "test: add genuine Stage D scoring fixture"
```

### Task 2: Compose the complete policy-adjusted score input batch

**Files:**
- Create: `ashare_pipeline/formal_final_score_inputs.py`
- Create: `tests/test_formal_final_score_inputs.py`

**Interfaces:**
- Consumes: `FormalScoreInputRepository.build_batch(...) -> FormalScoreInputBatch`、`FormalPolicyRepository.build_batch(...) -> VerifiedPolicyResultBatch`、`FormalValuationRepository.build_batch(...) -> PolicyAdjustedValuationBatch`、同一 authenticated v2 root 的三个 registries 和同一 frozen input；purpose 与 mode 的正式资格由 Task 11 gate 决定。
- Produces: `PolicyAdjustedScoreInput`；`PolicyAdjustedScoreInputBatch.input_for(security_id)`；`FormalFinalScoreInputRepository(...).build_batch(frozen_input_hash, *, scoring_registry, policy_registry, valuation_adapter_registry)`。

- [ ] **Step 1: 写 D1 RED 测试。** 精确测试名：
  - `test_ready_input_contains_22_base_slots_and_exactly_three_stage_c_scores`
  - `test_batch_enumerates_every_frozen_member_in_canonical_order`
  - `test_member_business_gaps_become_explicit_pending_entries_not_none`
  - `test_batch_binds_root_frozen_universe_policy_and_valuation_hashes`
  - `test_identical_inputs_replay_to_identical_canonical_bytes_and_hash`

断言 pending 也是具备 `entry_hash` 的 `PolicyAdjustedScoreInput`，状态只允许 `ready/pending_evidence`；ready 恰有 25 slots，三个 V slot 带 Stage C score/context/hash，22 个非 V 保留 genuine base 来源。

- [ ] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs -v`

Expected: 新模块不存在。

- [ ] **Step 3: 实现闭包 proof 和完整组合。**

```python
class PolicyAdjustedScoreInput: ...

class PolicyAdjustedScoreInputBatch:
    def input_for(self, security_id: str) -> PolicyAdjustedScoreInput: ...

class FormalFinalScoreInputRepository:
    def __init__(self, feature_repository, context_repository, range_store,
                 *, registry_signature_verifier): ...
    def build_batch(self, frozen_input_hash: str, *, scoring_registry,
                    policy_registry, valuation_adapter_registry
                    ) -> PolicyAdjustedScoreInputBatch: ...
```

先闭合三批共同身份，再逐证券合并 reasons；policy pending 不因 veto/cap 消失。只从 Stage C 的三项 genuine score 取得最终 V。发布前重验三 source batches、registries 和规范字节。

- [ ] **Step 4: 运行 GREEN。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs -v`

Expected: 全部 PASS。

- [ ] **Step 5: 运行来源回归、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_score_inputs tests.test_formal_policy_repository tests.test_formal_valuation_batch tests.test_formal_valuation_ranking -v`

```powershell
git add ashare_pipeline/formal_final_score_inputs.py tests/test_formal_final_score_inputs.py
git commit -m "feat: compose policy-adjusted final score inputs"
```

### Task 3: Seal D1 against identity and proof-lifecycle attacks

**Files:**
- Modify: `ashare_pipeline/formal_final_score_inputs.py`
- Create: `tests/test_formal_final_score_input_guards.py`

**Interfaces:**
- Consumes/Produces: Task 2 API unchanged；增加 exact-type、current-method、canonical-byte、publication capability 和 outer revocation guards。

- [ ] **Step 1: 写攻击矩阵 RED。** 精确测试名覆盖：`test_cross_root_frozen_security_and_source_batch_are_rejected`、`test_raw_v_percentile_cannot_replace_stage_c_score`、`test_forged_copied_pickled_inherited_or_weakref_redirected_proofs_are_rejected`、`test_v1_root_prepolicy_and_plain_v2_objects_cannot_impersonate_d1`、`test_method_or_encoder_replacement_is_rejected`、`test_source_change_during_final_sweep_revokes_all_d1_children`、`test_capability_cannot_be_replayed_across_batch_or_context`。
- [ ] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_input_guards -v`

Expected: 至少一种拼批或生命周期攻击被当前最小实现接受。

- [ ] **Step 3: 最小加固。** 在 install closure 中捕获来源类型和方法身份；proof 普通构造、copy/deepcopy/pickle/继承失败；batch 外 selector 失败；结构错误拒整批，业务缺口才转换 pending。若真实性能 RED 证明逐成员 Stage C accessor 是瓶颈，才增加闭包私有只读 batch snapshot，不公开 mint 权限。
- [ ] **Step 4: 运行 GREEN、Task 2 回归、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs tests.test_formal_final_score_input_guards -v`

```powershell
git add ashare_pipeline/formal_final_score_inputs.py tests/test_formal_final_score_input_guards.py
git commit -m "test: seal final score input provenance"
```

### Task 4: Calculate capped final scorecards with exact Decimal arithmetic

**Files:**
- Create: `ashare_pipeline/formal_final_scoring.py`
- Create: `tests/test_formal_final_scoring.py`
- Create: `tests/test_formal_final_scoring_guards.py`

**Interfaces:**
- Consumes: genuine `PolicyAdjustedScoreInputBatch`。
- Produces: `FinalScoreCard`；`FinalScoreCardBatch.card_for(security_id)`；`.pending_for(security_id)`；`build_final_score_card_batch(inputs) -> FinalScoreCardBatch`。
- Reuses: captured `formal_scoring._calculate_untrusted_confidence`、`_calculate_untrusted_arithmetic`、`_arithmetic_context` 和 `grade_for_score`；这些纯 helper 不授予 proof。

- [ ] **Step 1: 写算术 RED。** 精确测试名：`test_final_card_rebuilds_all_seven_dimensions_from_final_slots`、`test_multiple_caps_take_minimum_without_changing_confidence`、`test_cap_never_raises_a_dimension`、`test_exact_sc_b_risk_and_grades_use_unrounded_decimal`、`test_verified_no_consensus_caps_confidence_at_point_90`、`test_pending_input_has_no_card_and_preserves_all_reasons`、`test_no_cap_parity_matches_existing_arithmetic_but_not_proof_type`。
- [ ] **Step 2: 写 guard RED。** 覆盖普通 dict、`PrePolicyScoreCalculation`、跨 D1 batch、未知 cap dimension、bool/int/float/string、NaN/Infinity/超大指数、全局 Decimal context 修改、copy/pickle、方法替换和 revoked source。
- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_scoring tests.test_formal_final_scoring_guards -v`

Expected: 新模块不存在。

- [ ] **Step 4: 实现纯计算核心和 proof wrapper。** 顺序固定为 raw dimensions → 同维 cap 取最小 → `min(raw, cap)` → 原 coverage 重算 C → S0/Sc/Sbase/B/R/grades。保存 raw/capped、cap rule/evidence trace、D/P/H/K/C、risk components 和全部 hash；pending 不生成 card。
- [ ] **Step 5: 运行 GREEN 与 pre-policy 回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_scoring tests.test_formal_final_scoring_guards tests.test_formal_scoring tests.test_formal_scoring_consensus_registry -v`

Expected: 全部 PASS；旧 pre-policy bytes/type/字段不变。

- [ ] **Step 6: 独立审查并提交。**

```powershell
git add ashare_pipeline/formal_final_scoring.py tests/test_formal_final_scoring.py tests/test_formal_final_scoring_guards.py
git commit -m "feat: calculate capped formal scorecards"
```

### Task 5: Derive unique final states and pool eligibility

**Files:**
- Create: `ashare_pipeline/formal_final_eligibility.py`
- Create: `tests/test_formal_final_eligibility.py`
- Create: `tests/test_formal_final_eligibility_guards.py`

**Interfaces:**
- Consumes: matching genuine `PolicyAdjustedScoreInputBatch` and `FinalScoreCardBatch`。
- Produces: `FormalEligibility`；`FormalEligibilityBatch.eligibility_for(security_id)`；`build_formal_eligibility_batch(inputs, scores)`。`formal_scored/pool_vetoed` 且有 card 的条目必须携带由 D2 card hash 锁定的不可变 `Sc/C/R_safety/B/V` 排序值及由 D1 input hash 锁定的二级行业；`pending_evidence/out_of_scope` 的 card hash 和排序值必须显式 absent。D3b 不回读数据库或未绑定 DTO。

- [ ] **Step 1: 写状态/阈值 RED。** 精确测试名：`test_pending_precedes_known_veto_and_emits_no_score_eligibility`、`test_pending_has_no_card_hash_or_sort_fields_but_remains_not_qualified_traceable`、`test_hard_veto_or_both_prohibition_yields_pool_vetoed`、`test_single_pool_prohibition_only_blocks_that_pool`、`test_threshold_equalities_are_inclusive_except_wait_t_is_strictly_below_55`、`test_each_threshold_uses_unrounded_decimal_at_both_adjacent_values`、`test_sort_fields_and_industry_are_bound_to_exact_d1_d2_hashes`、`test_each_frozen_member_has_exactly_one_state_and_complete_threshold_trace`、`test_genuine_ordinary_a_batch_has_zero_out_of_scope_members`。
- [ ] **Step 2: 写 guard RED。** `test_mismatched_d1_d2_batches_are_rejected`、`test_missing_duplicate_or_extra_scorecards_are_rejected`、`test_caller_cannot_forge_out_of_scope_state`、`test_plain_mapping_or_prepolicy_score_cannot_enter_eligibility`。
- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility tests.test_formal_final_eligibility_guards -v`

Expected: 新模块不存在。

- [ ] **Step 4: 实现唯一状态与门槛分解。** strong 固定 `Sc>=70,C>=.75,M/EQ/FS>=45,T>=55`；wait 固定 `B>=65,C>=.75,M/EQ/FS>=45,T<55`。保存 hard veto、prohibition、每项布尔门槛、reason codes、不可变排序字段和来源 hashes，并显式断言两池资格互斥。对每个阈值用 `Decimal.next_minus()/next_plus()` 或精确等价值测试上下邻域，不经过显示舍入。
- [ ] **Step 5: 运行 GREEN、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility tests.test_formal_final_eligibility_guards -v`

```powershell
git add ashare_pipeline/formal_final_eligibility.py tests/test_formal_final_eligibility.py tests/test_formal_final_eligibility_guards.py
git commit -m "feat: derive formal score eligibility"
```

### Task 6: Select deterministic strong and waiting-price pools

**Files:**
- Create: `ashare_pipeline/formal_pool.py`
- Create: `tests/test_formal_pool.py`
- Create: `tests/test_formal_pool_guards.py`

**Interfaces:**
- Consumes: genuine `FormalEligibilityBatch`；内部纯函数只消费 detached validated rows。
- Produces: `PoolSelectionDecision`；`PoolSelectionBatch.decision_for(security_id, pool)`；`select_formal_pools(eligibility)`；immutable `strong_security_ids`、`wait_security_ids` 和规范 count mapping `{"strong": n, "wait": n}`。

- [ ] **Step 1: 写纯选择 RED。** 精确测试名：`test_strong_sort_is_sc_confidence_safety_then_security_id`、`test_wait_sort_is_b_confidence_v_then_security_id`、`test_fifth_strong_industry_member_is_skipped_and_scan_continues`、`test_eleventh_wait_industry_member_is_skipped_and_scan_continues`、`test_overall_caps_are_20_and_50_without_forced_fill`、`test_strong_cap_rejection_never_falls_into_wait`、`test_pools_are_disjoint_and_every_candidate_has_decision_trace`。
- [ ] **Step 2: 写 proof guard RED。** 覆盖重复/缺失/未知 security、缺行业、非规范 ID、NaN/Infinity/float/bool key、跨 batch、普通 DTO、trace/hash 篡改。
- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_pool tests.test_formal_pool_guards -v`

Expected: 新模块不存在。

- [ ] **Step 4: 实现稳定排序与独立扫描。** 先生成每池完整候选排序，再独立应用行业/总容量；所有成员每池都保存 `selected/not_qualified/industry_cap_reached/overall_capacity_reached` 之一。内部 key 固定 `strong/wait`。
- [ ] **Step 5: 运行 GREEN、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_pool tests.test_formal_pool_guards -v`

```powershell
git add ashare_pipeline/formal_pool.py tests/test_formal_pool.py tests/test_formal_pool_guards.py
git commit -m "feat: select deterministic formal stock pools"
```

### Task 7: Audit production coverage and enforce fail-closed gates

**Files:**
- Create: `ashare_pipeline/formal_coverage_manifest.py`
- Create: `tests/test_formal_coverage_manifest.py`
- Create: `tests/test_formal_coverage_guards.py`

**Interfaces:**
- Consumes: verified frozen universe、registry bundle、repository validation callbacks、数据库/工作区只读身份和每项 `(frozen_input_hash, security_id, domain, selector_hash, period_or_window, exchange)` 需求。
- Produces: `VerifiedCoverageManifest`；`FormalCoverageAuditor.audit(...)`；`.require_preview_ready()`；`.require_official_ready()`；规范 member requirement rows、blockers、manifest hash 和非规范 timing diagnostics。

- [ ] **Step 1: 写 coverage class RED。** 允许值严格为规格 15 类。精确测试名：`test_absent_record_is_blocked_not_verified_no_coverage`、`test_verified_no_coverage_requires_authenticated_explicit_source_statement`、`test_missing_table_is_blocked_schema_not_zero_rows`、`test_exchange_calendar_cannot_be_reused_across_sh_sz_bj`、`test_every_required_member_domain_key_is_unique_and_enumerated`、`test_sql_counts_are_diagnostic_only_and_never_grant_readiness`、`test_audit_time_and_timing_diagnostics_do_not_change_canonical_hash`。
- [ ] **Step 2: 写 gate/guard RED。** 覆盖 registry purpose、approval、签名/哈希、temporal cutoff、units、parser/mapping version、ambiguous duplicate、source correction、DB/status stale mismatch；缺 production contract 时 preview 可审计但 official 阻断。另加 `test_coverage_proof_rejects_plain_construction_copy_pickle_weakref_redirect_method_replacement_and_revocation` 及旧 v1/v2 普通对象冒充测试。
- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v`

Expected: 新模块不存在。

- [ ] **Step 4: 实现验证器。** 每个 formal domain 必须调用所属 repository 验证入口；记录 source/dataset/request/refresh/task/snapshot/content/manifest/parser/mapping/timestamps/units/class/reasons/evidence hashes。`audit_at_utc` 与 timing diagnostics 不进入规范结果 hash。
- [ ] **Step 5: 运行 GREEN、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v`

```powershell
git add ashare_pipeline/formal_coverage_manifest.py tests/test_formal_coverage_manifest.py tests/test_formal_coverage_guards.py
git commit -m "feat: audit formal production coverage"
```

### Task 8: Add the continuous SQLite V8 Stage D schema

**Files:**
- Modify: `ashare_pipeline/state_store.py`
- Create: `tests/test_formal_final_migration.py`
- Create: `tests/fixtures/schema_v7.sql`
- Modify: `tests/test_state_store.py`

**Interfaces:**
- Consumes: exact V2–V7 migration ledger and existing tables。
- Produces: `SCHEMA_VERSION = 8`、`_V8_TABLE_DDL`、`_V8_INDEX_DDL`、`StateStore._apply_v8_migration(connection)`；仅提供给 `formal_final_repository` 使用的内部事务边界，不增加逐表公共写 API。

- [ ] **Step 1: 写 migration RED。** 精确测试名：`test_v7_range_schema_and_rows_survive_v8_migration_exactly`、`test_fresh_database_records_contiguous_versions_2_through_8`、`test_v8_migration_is_atomic_and_reopen_verifies_exact_ddl`、`test_partial_or_extra_v8_object_rejects_without_advancing_ledger`、`test_legacy_score_run_and_score_item_are_not_repurposed`。
- [ ] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration -v`

Expected: schema version 7 且 V8 表不存在。

- [ ] **Step 3: 实现八表 schema。** 新增 `formal_final_run`、`formal_final_artifact`、`formal_final_input`、`formal_final_scorecard`、`formal_final_status`、`formal_final_eligibility`、`formal_final_pool_decision`、`formal_final_dependency`。所有 Decimal 使用规范文本，禁止 REAL；run id/time 不进入 canonical result hash；同一 input manifest 允许独立重放。
- [ ] **Step 4: 加约束与索引。** pool name/decision 精确 CHECK；run `mode IN ('test_preview','official_candidate')`、`status IN ('preview_ready','blocked')`；selected ordinal partial unique；dependency 按 source 和 effect scope 索引；外键和主键保证全表从属同一 run。
- [ ] **Step 5: 运行 GREEN 与完整 state-store migration 回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration tests.test_state_store -v`

Expected: 全部 PASS，现有 V7 range DDL/数据逐字节保留。

- [ ] **Step 6: 独立审查并提交。**

```powershell
git add ashare_pipeline/state_store.py tests/test_state_store.py tests/test_formal_final_migration.py tests/fixtures/schema_v7.sql
git commit -m "feat: add formal final scoring schema v8"
```

### Task 9: Persist one append-only Stage D result atomically

**Files:**
- Create: `ashare_pipeline/formal_final_repository.py`
- Create: `ashare_pipeline/formal_final_publication.py`
- Modify: `ashare_pipeline/formal_final_score_inputs.py`
- Modify: `ashare_pipeline/formal_final_scoring.py`
- Modify: `ashare_pipeline/formal_final_eligibility.py`
- Modify: `ashare_pipeline/formal_pool.py`
- Create: `tests/test_formal_final_repository.py`
- Create: `tests/test_formal_final_atomicity.py`

**Interfaces:**
- Consumes: `StateStore`、genuine coverage/D1/D2/D3 batches and shared unpublished Stage D capability。
- Produces: `FormalFinalRunRepository.commit_complete_run(...) -> FormalFinalRunReceipt`；`get_run(run_id) -> FormalFinalRunSnapshot | None`；`list_runs_by_input_manifest(hash) -> tuple[...]`。恢复对象是只读 DTO，不是 proof。
- Internal: `FormalFinalPublicationCoordinator.prepare(...)` 是 D1–D3 sealed prepared adapters 的唯一调用者；它不导出 mint token。事务内 `arm()` 后外部 `require_verified()` 仍失败；SQLite commit 成功后执行已预检、不可失败、无 I/O/分配的 `mark_committed()`，proof 才统一生效。任何 commit 异常调用 `revoke()`。

```python
def commit_complete_run(self, *, mode, coverage_manifest, input_batch,
                        score_batch, eligibility_batch, pool_batch
                        ) -> FormalFinalRunReceipt: ...
```

- [ ] **Step 1: 写 repository RED。** `test_complete_run_persists_exact_universe_and_all_artifact_hashes`、`test_decimals_round_trip_as_canonical_text_without_float`、`test_same_input_allows_two_append_only_replays_with_same_result_hash`、`test_historical_run_cannot_be_updated_or_rebound`、`test_cross_root_or_forged_batch_is_rejected_before_write`、`test_recovery_dto_never_authenticates_as_live_proof`。
- [ ] **Step 2: 写原子故障矩阵 RED。** 对每张子表插入、规范序列化、最终来源复验、集合复验、`arm()` 和 SQLite commit 注入异常；`test_every_commit_failure_leaves_zero_stage_d_rows_and_revokes_children` 断言全无或全有，`test_armed_proofs_remain_invisible_until_commit_returns` 断言无短暂可见窗口，`test_post_commit_mark_committed_is_prevalidated_and_cannot_fail` 固定 flip 合同。另测合法 blocked run 一次性写入且无伪池，并覆盖普通构造/copy/pickle/弱引用重定向/方法替换与撤销攻击。
- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_repository tests.test_formal_final_atomicity -v`

Expected: repository 不存在。

- [ ] **Step 4: 实现唯一批量写入口。** 事务前完成长计算并预检 committed flip；事务内重验冻结宇宙/根/依赖，写 header、五种 canonical artifacts、全成员 input/status/eligibility/两池 decision、可用 scorecards 和 dependency rows，逐表比较精确 security 集合及 hash，最后只 `arm()` 并提交 SQLite。commit 返回后立即执行不可失败 `mark_committed()`；异常路径 rollback/revoke，绝不先开放 proof。
- [ ] **Step 5: 明确禁止逐表 API。** 不实现 `put_*`、`replace_*`、`mark_ready`；run status 只允许 `preview_ready/blocked`，`validated/published` 留给 V9 release。
- [ ] **Step 6: 运行 GREEN、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_repository tests.test_formal_final_atomicity tests.test_formal_final_migration -v`

```powershell
git add ashare_pipeline/formal_final_repository.py ashare_pipeline/formal_final_publication.py ashare_pipeline/formal_final_score_inputs.py ashare_pipeline/formal_final_scoring.py ashare_pipeline/formal_final_eligibility.py ashare_pipeline/formal_pool.py tests/test_formal_final_repository.py tests/test_formal_final_atomicity.py
git commit -m "feat: persist atomic formal final runs"
```

### Task 10: Plan incremental invalidation from trusted manifest differences

**Files:**
- Create: `ashare_pipeline/formal_final_invalidation.py`
- Create: `tests/test_formal_final_invalidation.py`
- Modify: `ashare_pipeline/formal_final_repository.py`

**Interfaces:**
- Consumes: prior run dependency rows and a current verified final input/coverage manifest；不接受调用方自报 changed IDs。
- Produces: `FormalRebuildPlan` with `full_rebuild`、direct/expanded security IDs、cohort keys、D1/D2/eligibility rebuild IDs、`rescan_pools`、reason codes and prior/current manifest hashes；`FormalFinalRunRepository.plan_rebuild(...)`。

- [ ] **Step 1: 写传播 RED。** 精确测试名：`test_single_non_peer_evidence_change_rebuilds_one_security_and_rescans_pools`、`test_peer_or_v_change_expands_to_complete_cohort`、`test_policy_cap_prohibition_pending_and_normalization_have_distinct_effects`、`test_universe_industry_registry_frozen_or_contract_change_forces_full_rebuild`、`test_diagnostic_timing_or_display_change_does_not_rebuild`、`test_caller_supplied_changed_ids_are_not_an_api_or_authority`。
- [ ] **Step 2: 写恢复 RED。** `test_restart_selects_prior_exact_manifest_not_later_correction`、`test_old_run_bytes_never_change_after_new_rebuild`、`test_reuse_requires_current_hash_and_capability_revalidation`。
- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_invalidation -v`

Expected: 模块/API 不存在。

- [ ] **Step 4: 实现规范 dependency diff。** effect scopes 固定 `security/cohort/pool/global`；任何会改变资格或排序的变化都 `rescan_pools=True`。policy normalization 扩展 Stage C cohort；cap 进入 D2；prohibition/pending 进入状态/资格；global context 进入全宇宙。
- [ ] **Step 5: 运行 GREEN、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_invalidation tests.test_formal_final_repository -v`

```powershell
git add ashare_pipeline/formal_final_invalidation.py ashare_pipeline/formal_final_repository.py tests/test_formal_final_invalidation.py
git commit -m "feat: plan formal score invalidation scopes"
```

### Task 11: Wire the offline runner and complete full-chain acceptance

**Files:**
- Create: `ashare_pipeline/formal_final_runner.py`
- Create: `tests/test_formal_final_runner.py`
- Create: `tests/test_formal_final_integration.py`
- Create: `tests/test_formal_final_performance.py`
- Create: `docs/superpowers/evidence/formal-final-stage-d/README.md`

**Interfaces:**
- Consumes: configured repositories、exact frozen input、与 mode 匹配的 authenticated registries 和 `VerifiedCoverageManifest`；`test_preview` 接受 genuine purpose=`test` root，`official_candidate` 只接受带批准身份的 purpose=`official` root；不访问网络。
- Produces: `FormalFinalScoreRunner.run_preview(...) -> FormalFinalRunReceipt`；`.run_official_candidate(...) -> FormalFinalRunReceipt`；`.rebuild_affected(...) -> FormalFinalRunReceipt`；immutable diagnostics DTO。前者写 `mode=test_preview`，后者仅在 official gate 全通过时写 `mode=official_candidate`；两者成功 status 都是 `preview_ready`，均不等于 V9 的 validated/published。runner 不复制公式、不直接 SQL、不发布 V9。

- [ ] **Step 1: 写 runner RED。** `test_runner_closes_root_and_all_batch_identities_before_d1`、`test_preview_accepts_genuine_test_root_and_records_explicit_blockers`、`test_official_candidate_rejects_failed_gates_without_writing_an_official_mode_row`、`test_official_candidate_is_still_preview_ready_and_never_v9_published`、`test_runner_has_no_network_or_legacy_score_input_path`、`test_v1_v2_prepolicy_and_recovery_dtos_cannot_impersonate_stage_d_inputs`、`test_two_independent_runs_have_identical_canonical_result_hash`、`test_rebuild_affected_derives_changes_from_current_verified_manifest`。
- [ ] **Step 2: 写 20/23 genuine integration RED。** 从一个十角色 root 跑 D1→D2→D3→V8，反向核对 frozen/root/B/C/D1/D2/D3/coverage hashes；覆盖 ready、pending、veto、single-pool prohibition、cyclic cap、no-consensus 和同行回退。断言 strong≤20、wait≤50、行业≤4/10、池互斥、完整成员唯一状态。
- [ ] **Step 3: 写攻击与性能 RED。** 对跨根/冻结/证券/批次、DB row tamper、registry/source correction、最终复验撤销执行集成攻击。记录各阶段耗时、完整验证次数、成员/指标/cohort/排序/重建数、状态/reason/veto/资格/池数、cap skip、parse/rederive/recheck 次数；设结构性上限“每个 source batch 每阶段至多一次完整解析、每 cohort 至多一次排序”，不写易波动墙钟硬阈值。
- [ ] **Step 4: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_runner tests.test_formal_final_integration tests.test_formal_final_performance -v`

Expected: runner 不存在或完整链未接通。

- [ ] **Step 5: 实现薄 runner。** 顺序固定：coverage/root/frozen identity closure → B/C 与 D1 prepared → D2 → D3 → final recheck → repository atomic commit。`rebuild_affected` 先调用 trusted diff，再构造全新 append-only run；复用不绕过逐次验活。
- [ ] **Step 6: 运行 Stage D GREEN。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture tests.test_formal_final_score_inputs tests.test_formal_final_score_input_guards tests.test_formal_final_scoring tests.test_formal_final_scoring_guards tests.test_formal_final_eligibility tests.test_formal_final_eligibility_guards tests.test_formal_pool tests.test_formal_pool_guards tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_final_migration tests.test_formal_final_repository tests.test_formal_final_atomicity tests.test_formal_final_invalidation tests.test_formal_final_runner tests.test_formal_final_integration tests.test_formal_final_performance -v`

Expected: 全部 PASS，0 failure/error/skip。

- [ ] **Step 7: 运行受影响完整回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_feature_repository tests.test_formal_metric_engine tests.test_formal_metric_context tests.test_formal_score_inputs tests.test_formal_scoring tests.test_formal_policy_repository tests.test_formal_policy_integration tests.test_formal_valuation_batch tests.test_formal_valuation_ranking tests.test_formal_valuation_integration tests.test_state_store -v`

Expected: 全部 PASS，现有 A/B/C proof bytes、V7 range schema 和旧 provisional score tables 均未被改写。

- [ ] **Step 8: 保存验收证据并独立终审。** README 记录精确 commit、命令、计数、耗时、诊断和已知 production blockers；不得保存数据库、WAL/SHM 或原始用户数据。终审必须分别检查 spec coverage、trust boundary、原子性、经济规则、性能结构和 V8/V9 版本边界。
- [ ] **Step 9: 提交 runner 与验收。**

```powershell
git add ashare_pipeline/formal_final_runner.py tests/test_formal_final_runner.py tests/test_formal_final_integration.py tests/test_formal_final_performance.py docs/superpowers/evidence/formal-final-stage-d/README.md
git commit -m "feat: complete formal final scoring stage D"
```

## Definition of Done

- [ ] D1–D4 的所有新测试和受影响回归为 0 failure/error/skip。
- [ ] 冻结宇宙每个成员恰有一个最终状态；当前 ordinary-A 批次 `out_of_scope=0`。
- [ ] 七维、C、S0、Sc、Sbase、B、R、risk exposure、grades 与 cap trace 可从规范输入精确重演。
- [ ] strong/wait 资格、排序、行业 cap、容量、互斥和不回填全部有未舍入 Decimal 边界测试。
- [ ] coverage manifest 对缺失、无覆盖、schema、registry、identity、integrity、temporal、ambiguous 和 dependency 失败关闭。
- [ ] SQLite 从 V2–V7 连续迁移到 V8，V7 range 数据与精确 DDL 保持不变；无 torn Stage D run。
- [ ] 单证券、cohort、policy 和 global 失效范围可解释，所有变化产生新 append-only run。
- [ ] 20/23 genuine 集成通过；全量正式运行仍被带批准身份的 purpose=`official` 生产合同根或完整 SH/SZ/BJ coverage gate 阻断时，两个正式池保持未发布。
- [ ] 每个任务均有独立提交、独立 reviewer 结论和对应 evidence；未提交任何数据、SQLite、WAL/SHM、进度或备份文件。
