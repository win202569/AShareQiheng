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

