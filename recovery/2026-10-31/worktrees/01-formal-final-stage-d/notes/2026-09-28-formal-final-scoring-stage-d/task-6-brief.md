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

