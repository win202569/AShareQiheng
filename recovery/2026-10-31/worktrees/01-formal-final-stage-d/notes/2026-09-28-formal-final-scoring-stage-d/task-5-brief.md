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

