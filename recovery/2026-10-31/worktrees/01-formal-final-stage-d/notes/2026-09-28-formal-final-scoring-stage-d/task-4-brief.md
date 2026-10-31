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

