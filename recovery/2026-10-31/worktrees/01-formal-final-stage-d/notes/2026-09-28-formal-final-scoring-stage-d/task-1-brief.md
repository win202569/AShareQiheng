### Task 1: Build one genuine ten-role Stage D fixture graph

**Files:**
- Create: `tests/formal_final_scoring_fixtures.py`
- Modify: `tests/formal_valuation_fixtures.py`
- Create: `tests/test_formal_final_fixture.py`

**Interfaces:**
- Consumes: `ValuationRuntimeFixture`、v2 十角色签名图、真实 Formal Feature/Context/Metric/Policy/Range/Valuation producers。
- Produces: `FinalScoringFixture`；`populate_final_inputs(...)`；`build_d1_sources()`；可配置 20/23 人 cohort、pending、cap、prohibition、veto 和 consensus no-coverage，但不直接 mint 任何 proof。

- [ ] **Step 1: 写失败测试。** 新增 `test_one_v2_root_builds_base_policy_and_adjusted_valuation_batches`，断言三批的 `registry_manifest_hash`、`frozen_input_hash`、`universe_hash`、`security_ids` 完全相同；新增 `test_fixture_never_exposes_proof_mint_or_plain_proof_double`，断言 fixture 无 mint API，返回值均为真实公开 proof 类型。
- [ ] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture -v`

Expected: 因 fixture/module 不存在失败。

- [ ] **Step 3: 最小实现。** 仅给 `ValuationRuntimeFixture.__init__` 增加默认 `None` 的 test-only 签名前文档配置回调；默认路径的签名字节和既有行为不得变化。新 fixture 在一个 v2 root 内配置完整 25 slots、consensus alternative、policy、range 和 valuation adapter。
- [ ] **Step 4: 运行 GREEN 与 fixture 回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture tests.test_formal_valuation_integration tests.test_formal_score_inputs tests.test_formal_policy_integration -v`

Expected: 全部 PASS，现有 fixture 默认输出不变。

- [ ] **Step 5: 独立审查并提交。**

```powershell
git add tests/formal_final_scoring_fixtures.py tests/formal_valuation_fixtures.py tests/test_formal_final_fixture.py
git commit -m "test: add genuine Stage D scoring fixture"
```

