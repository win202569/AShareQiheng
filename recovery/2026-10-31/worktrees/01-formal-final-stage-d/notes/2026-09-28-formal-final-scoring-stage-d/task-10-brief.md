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

