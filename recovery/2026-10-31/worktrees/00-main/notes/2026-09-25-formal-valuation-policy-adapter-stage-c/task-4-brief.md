### Task 4: Complete adjusted valuation batch and atomic publication

**Files:**
- Create: `ashare_pipeline/formal_valuation_engine.py`
- Create: `tests/formal_valuation_fixtures.py`
- Create: `tests/test_formal_valuation_batch.py`
- Create: `tests/test_formal_valuation_batch_guards.py`
- Modify: `tests/formal_metric_fixtures.py:39-76`
- Modify: `tests/formal_metric_feature_fixtures.py:32-67`
- Modify: `tests/formal_policy_runtime_fixtures.py:125-213`

**Interfaces:**
- Consumes: exact `FormalFeatureRepository`、`FormalContextRepository`、`FormalRangeStore`、签名 verifier、`FormalScoringRegistry`、`FormalPolicyRegistry`、`FormalValuationAdapterRegistry`。
- Produces: `FormalValuationRepository(feature_repository, context_repository, range_store, *, registry_signature_verifier)`；`.build_batch(frozen_input_hash, *, scoring_registry, policy_registry, valuation_adapter_registry) -> PolicyAdjustedValuationBatch`；`PolicyAdjustedValuationInput`；batch `.input_for(security_id, metric_id)`、`.require_verified()`、`.canonical_bytes()`、`.to_dict()`。闭包私有 `prepare_adjusted_rows(base_batch, policy_batch, adapter_registry) -> tuple[dict, ...]` 只组装规范行，不发布证明。

- [ ] **Step 1: 建立 20 人十角色真实 fixture。**

```python
class ValuationRuntimeFixture(PolicyRuntimeFixture):
    def __init__(self):
        securities = {"BJ430001": "general_nonfinancial"}
        securities.update({f"SH{600000 + index}": "general_nonfinancial"
                           for index in range(19)})
        super().__init__(range_enabled=True, templates=securities, cyclic=True,
                         noncyclic_ids=tuple(sorted(set(securities) - {"BJ430001"})),
                         valuation_adapter=True)
        self.templates = securities
        self.valuation_registry = load_formal_valuation_adapter_registry(
            self.bundle, scoring_registry=self.scoring,
            policy_registry=self.policy_registry)
```

fixture 的 `populate_valuation_inputs()` 必须通过现有 `put_financial`、`policy_financial_values`、`persist_features`、Context 和 range producer 写入真实证据；焦点证券原始 earnings yield 为 `0.20`、原利润 `10`、五年中位数 `6`，其余 19 人为非周期透传且值唯一。不得直接 mint `MetricInput` 或 `PolicyResult`。

为支持该 fixture，给 `MetricFixture.__init__`、`FinancialFixture.__init__` 增加默认 `manifest_version="formal-registry-manifest-v1"` 并原样向下传递；给 `PolicyRuntimeFixture.__init__` 增加默认 `valuation_adapter=False`。只有该值为 true 时，configure 在 `add_policy_documents` 之后调用 `add_valuation_adapter_document(documents)`，并以 manifest v2 构图。所有现有调用因默认值继续使用 v1。

- [ ] **Step 2: 写完整批次 RED 测试。**

```python
def test_complete_batch_contains_every_security_and_three_v_metrics(self):
    batch = self.fixture.repository.build_batch(
        self.fixture.frozen.frozen_input_hash,
        scoring_registry=self.fixture.scoring,
        policy_registry=self.fixture.policy_registry,
        valuation_adapter_registry=self.fixture.valuation_registry)
    batch.require_verified()
    self.assertEqual(batch.security_ids, tuple(sorted(self.fixture.templates)))
    self.assertEqual(len(batch.inputs), len(batch.security_ids) * 3)
    focal = batch.input_for("BJ430001", "V.normalized_earnings_yield")
    self.assertEqual(focal.status, "adjusted")
    self.assertEqual(focal.adjusted_value, Decimal("0.12"))
```

加入：原始指标不合格保留行、pending affected 保留行、pending unaffected 透传、无模板/行业仍枚举、证券/指标顺序规范、base/policy/adapter hash 全绑定、原始 base 和 policy 规范字节构建前后相同。

- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_batch -v`

Expected: FAIL with missing `formal_valuation_engine`。

- [ ] **Step 4: 实现仓库、证明和外层 guard。**

```python
_V_METRICS = (
    "V.enterprise_value_or_sustainable_roe",
    "V.normalized_earnings_yield",
    "V.normalized_free_cash_flow_yield",
)

class FormalValuationRepository:
    def build_batch(self, frozen_input_hash, *, scoring_registry,
                    policy_registry, valuation_adapter_registry):
        with guard_factory(feature._current_input_provider, feature._store) as guard:
            base = metric_repository.build_batch(
                frozen_input_hash, scoring_registry=scoring_registry,
                metric_ids=_V_METRICS)
            policy = policy_repository.build_batch(
                frozen_input_hash, scoring_registry=scoring_registry,
                policy_registry=policy_registry)
            rows = prepare_adjusted_rows(base, policy,
                                         valuation_adapter_registry)
            prepared = mint_complete_batch(rows, base, policy,
                                           valuation_adapter_registry,
                                           publication=[False])
            def publish():
                dependencies(self)
                base.require_verified()
                policy.require_verified()
                valuation_adapter_registry.require_official(self._bundle)
                publication_for(prepared)[0] = True
                return prepared
            return guard.finalize(publish)
```

`mint_complete_batch`、`publication_for`、`dependencies` 和 bundle 记录均在 `_install_valuation_engine()` 闭包内定义并捕获；示例中的 `self._bundle` 在实际实现中从闭包 repository record 取出，不能成为可替换实例属性。构造器拒绝外部调用，records 以 weakref 身份登记，payload 深冻结，规范字节只含确定性字段，所有 child 共用外层 `[False]` publication capability。内部创建真实 metric/policy repository并验证它们与同一个 feature provider/store、Context、range store 和 verifier 绑定。nested guard 只允许相同 owner。

- [ ] **Step 5: 写 guard、篡改和恢复测试。**

```python
def test_outer_finalization_failure_revokes_only_adjusted_children(self):
    captured = {"adjusted": [], "base": [], "policy": []}
    closed = []
    def hook(frame, event, result):
        if event == "return" and frame.f_code.co_name == "mint":
            filename = frame.f_code.co_filename
            if filename.endswith("formal_valuation_engine.py"):
                captured["adjusted"].append(result)
            elif filename.endswith("formal_metric_engine.py"):
                captured["base"].append(result)
            elif filename.endswith("formal_policy_repository.py"):
                captured["policy"].append(result)
        if (not closed and event == "return" and frame.f_code.co_name == "finalize"
                and frame.f_code.co_filename.endswith("formal_metric_batch_guard.py")
                and "observer" in frame.f_locals):
            closed.append(True)
            frame.f_locals["observer"].close()
    with self.assertRaises(sqlite3.Error):
        self.run_with_trace(hook, self.build)
    self.assertEqual(closed, [True])
    self.assertTrue(captured["adjusted"])
    with self.assertRaisesRegex(ValueError, "unpublished or revoked"):
        captured["adjusted"][-1].require_verified()
    captured["base"][-1].require_verified()
    captured["policy"][-1].require_verified()
```

`run_with_trace` 按现有 batch-guard 测试的 `sys.settrace`/`sys.setprofile` 配对实现，并在 `finally` 中恢复原 hook；它只观察真实闭包 mint 和 guard frame，不改变生产依赖。生产对象不得公开 base/policy 私有属性。另测 provider reentrant publication、数据库 data_version 改变、注册表替换、range selection 更正、final rollback/close 异常、跨根批次、伪造/复制/继承/方法替换，以及失败后下一次干净构建可恢复。

- [ ] **Step 6: 运行 GREEN 和 Stage B/metric guard 回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_batch tests.test_formal_valuation_batch_guards tests.test_formal_metric_batch_guard tests.test_formal_policy_batch_guards tests.test_formal_policy_repository -v`

Expected: 全部 PASS；任何失败路径都无可用的部分调整证明。

- [ ] **Step 7: 提交 C4。**

```powershell
git add ashare_pipeline/formal_valuation_engine.py tests/formal_valuation_fixtures.py tests/test_formal_valuation_batch.py tests/test_formal_valuation_batch_guards.py
git commit -m "feat: publish complete policy-adjusted valuation batches"
```

