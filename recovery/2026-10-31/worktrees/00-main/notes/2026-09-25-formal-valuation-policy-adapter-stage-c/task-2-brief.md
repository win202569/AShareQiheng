### Task 2: Signed valuation adapter contract

**Files:**
- Create: `ashare_pipeline/formal_valuation_adapter_contract.py`
- Create: `tests/test_formal_valuation_adapter_contract.py`
- Modify: `ashare_pipeline/formal_metric_engine.py:166-180`
- Modify: `tests/test_formal_metric_engine.py`
- Modify: `tests/formal_policy_fixtures.py:225-347`

**Interfaces:**
- Consumes: genuine v2 `VerifiedRegistryBundle`、`FormalScoringRegistry`、`FormalPolicyRegistry` 和 `valuation_adapter` child 原始规范字节。
- Produces: `ValuationAdapterDefinition`；`FormalValuationAdapterRegistry`；`load_formal_valuation_adapter_registry(bundle, *, scoring_registry, policy_registry) -> FormalValuationAdapterRegistry`；`.dependency_for(template_id, metric_id)`；`.adapter_for(template_id, metric_id)`；`.require_official(bundle)`；`.to_dict()`；fixture helper `add_valuation_adapter_document(documents) -> None`。

- [ ] **Step 1: 写合同 RED 测试和十角色 fixture 文档。**

```python
def valuation_adapter_document(scoring, cyclic_rules):
    adapters = []
    coverage = []
    for template_id in sorted(scoring["templates"]):
        rule = cyclic_rules[template_id]
        by_metric = {item["metric_id"]: item
                     for item in rule["parameters"]["valuation_dependencies"]}
        for metric in scoring["templates"][template_id]["metrics"]["V"]:
            metric_id = "V." + metric["metric_id"]
            dependency = by_metric[metric_id]
            coverage.append(dict(template_id=template_id, metric_id=metric_id,
                                 policy_dependency=dependency["policy_dependency"]))
            if dependency["policy_dependency"] == "affected":
                adapters.append(dict(
                    template_id=template_id, metric_id=metric_id,
                    adapter_id=dependency["adapter_id"],
                    adapter_version=dependency["adapter_version"],
                    operation="profit_ratio_rescale_v1",
                    profit_semantic_id=dependency["profit_semantic_id"],
                    metric_unit=metric["unit_rule"], profit_unit="CNY",
                    output_unit=metric["unit_rule"], policy_role="cyclic",
                    rule_id=rule["rule_id"],
                    decimal_contract="decimal50-half-even-v1",
                    preconditions=["exact_units", "finite_decimals",
                                   "nonzero_original_current_profit"],
                    definition_basis=dependency["definition_basis"]))
    return dict(registry_role="valuation_adapter",
                schema_version="formal-valuation-adapter-registry-v1",
                purpose="official", registry_version="fixture-adapter-v1",
                coverage=sorted(coverage, key=lambda x: (x["template_id"], x["metric_id"])),
                adapters=sorted(adapters, key=lambda x: (x["template_id"], x["metric_id"])))
```

测试精确覆盖五模板 × 三 V 指标、每个 affected 唯一 adapter、unaffected 不得有 adapter、operation 白名单、定义哈希、利润语义、rule/template/metric/unit、Decimal contract 和 preconditions。逐项 mutation 必须报稳定的合同错误。

- [ ] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_adapter_contract -v`

Expected: FAIL with `ModuleNotFoundError: ashare_pipeline.formal_valuation_adapter_contract`。

- [ ] **Step 3: 实现严格 parser 和不可伪造 registry。**

```python
@dataclass(frozen=True, slots=True)
class ValuationAdapterDefinition:
    template_id: str
    metric_id: str
    adapter_id: str
    adapter_version: str
    operation: Literal["profit_ratio_rescale_v1"]
    original_definition_hash: str
    profit_semantic_id: str
    metric_unit: str
    profit_unit: str
    output_unit: str
    policy_role: Literal["cyclic"]
    rule_id: str
    decimal_contract: Literal["decimal50-half-even-v1"]
    preconditions: tuple[str, ...]
    definition_basis: str
```

child 文档不序列化 `original_definition_hash`，避免 adapter child → root hash → metric definition hash → adapter child 的循环。loader 从同根真实 scoring 定义按 `_scoring_metric_definitions` 的完全相同 payload 规则派生 root-bound `original_definition_hash`，并把它固定到加载后的 `ValuationAdapterDefinition`。loader 必须从 `bundle.blob("valuation_adapter")` 重新读取规范字节，调用 scoring/policy 的正式 seal，按每个模板的 V 定义和周期依赖构建精确期望集合。registry 构造能力、seal、规范 payload 和索引放在闭包内；公开 dataclass 复制不能取得正式资格，`object.__setattr__` 后 `.require_official()` 必须失败。

把 `formal_metric_engine.py` 当前闭包内 `definitions(scoring)` 原样提升为模块私有 `_scoring_metric_definitions(scoring)`，指标引擎与 adapter loader 捕获同一个函数身份；保留其 payload 字段和 hash 算法不变。新增回归断言：重构前 fixture 的 definition hash 常量不变，运行时替换模块同名函数不能改变已安装引擎的结果。

扩展 fixture 入口时使用明确参数：

```python
def policy_graph(*, version="v1", manifest_version="formal-registry-manifest-v1",
                 with_valuation_adapter=False, mutate=None):
    def prepare(documents):
        add_policy_documents(documents)
        if with_valuation_adapter:
            add_valuation_adapter_document(documents)
        if mutate is not None:
            mutate(documents)
        rehash_documents(documents)
    if version == "v1":
        values = signed_graph(context=True, mutate=prepare,
                              manifest_version=manifest_version)
    else:
        if (manifest_version != "formal-registry-manifest-v1"
                or with_valuation_adapter):
            raise ValueError("fixture scoring v2 does not author Stage C roots")
        values = v2_graph(mutate=prepare)
    bundle, vocabulary, repository, verifier = values[:4]
    approval = RegistryApproval("official",
        bundle.manifest.scoring_registry_hash, bundle.manifest.approval_id)
    scoring = load_formal_registry(bundle, approval,
                                   feature_registry=vocabulary)
    return bundle, vocabulary, scoring, repository, verifier
```

`with_valuation_adapter=True` 必须同时要求 manifest v2；其他组合明确报错。现有 scoring wrapper v2 fixture 继续使用九角色 manifest v1，不扩大本阶段改动面。

- [ ] **Step 4: 证明旧 v1 不能进入 Stage C。**

```python
def test_v1_graph_cannot_load_a_formal_valuation_adapter(self):
    bundle, vocabulary, scoring, _, _ = policy_graph(
        manifest_version="formal-registry-manifest-v1")
    policy = load_formal_policy_registry(bundle, scoring_registry=scoring,
                                         feature_registry=vocabulary)
    with self.assertRaisesRegex(ValueError, "valuation_adapter role is unavailable"):
        load_formal_valuation_adapter_registry(bundle, scoring_registry=scoring,
                                               policy_registry=policy)
```

- [ ] **Step 5: 运行 GREEN 和注册表兼容回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v`

Expected: 全部 PASS；现有 v1 policy/scoring 图不需要 adapter 即可继续通过旧测试。

- [ ] **Step 6: 提交 C2。**

```powershell
git add ashare_pipeline/formal_valuation_adapter_contract.py ashare_pipeline/formal_metric_engine.py tests/test_formal_valuation_adapter_contract.py tests/test_formal_metric_engine.py tests/formal_policy_fixtures.py
git commit -m "feat: validate signed valuation adapter contracts"
```

