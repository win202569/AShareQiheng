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

