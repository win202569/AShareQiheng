# Formal Valuation Policy Adapter Stage C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将阶段 B 的签名利润归一化依据转换为独立的政策调整 V 指标，并在冻结全 A 股宇宙中重建可验证的同行分位数。

**Architecture:** 注册表根 v2 增加独立 `valuation_adapter` 角色，同时保留旧九角色 v1 图的读取能力。封闭适配器先把真实原始 V 批次与真实政策批次组合成不可伪造的调整批次，再用现有同行语义建立新的上下文和分位数证明；原始特征、原始指标和政策证明保持不变。

**Tech Stack:** Python 3.11、`unittest`、不可变 dataclass/closure proof、Decimal 50 位 `ROUND_HALF_EVEN`、SQLite `_metric_batch_guard`、现有 Formal Registry/Metric/Policy repositories。

**Spec:** [Stage C design](../specs/2026-09-25-formal-valuation-policy-adapter-stage-c-design.md)；上位约束见 [正式评分与发布合同](../specs/2026-09-04-formal-scoring-release-contract-design.md) 和 [Stage B](../specs/2026-09-12-formal-policy-stage-b-design.md)。

## Global Constraints

冻结时点固定为 `2026-08-31T07:00:00+00:00`。

阶段 C 不应用 G/M 最终 80 分上限，不生成政策后七维分数，不重算 `Sc/B/R`，不作最终资格或 20/50 选池。

不得改写原始财务事实、原始 feature receipt、既有 `MetricInputBatch`、旧分位数或旧分数。

`valuation_adapter` 必须由正式根 manifest 和签名覆盖；运行时配置、数据库自由行、回调和任意公式均无执行资格。

首版唯一数值 operation 是 `profit_ratio_rescale_v1`：`original_metric_value × normalized_profit ÷ original_current_profit`。

数值运算固定为 50 位 Decimal、`ROUND_HALF_EVEN`、显式指数范围与异常陷阱，不读取全局 Decimal 配置，不经过 float。

完整批次枚举冻结宇宙每只证券和三个 V 指标；逐指标待补可保留，结构错误、篡改和身份错配使整批失败。

同行规则保持“模板 × 二级行业，少于 20 回退同模板一级行业，仍少于 20 不评分，并列平均秩”。

原始输入批次、政策批次和注册表不得在每只证券或每个指标上重复完整解析；每个 cohort 只排序一次。

## Review Focus

1. 旧 `formal-registry-manifest-v1` 九角色图必须继续服务旧能力，但请求 Stage C 适配器时明确失败；Task 1 的 `test_v1_bundle_remains_valid_but_has_no_valuation_adapter_role` 固定此行为。
2. 周期决定待补时，affected 指标必须待补而 unaffected 指标仍可在签名声明支持下透传；Task 3 的 `test_pending_policy_blocks_only_affected_metric` 固定此行为。
3. 原利润为零、单位错误或非有限操作数不得进入除法或生成分位数；Task 3 的 `test_invalid_adapter_operands_fail_closed_without_numeric_output` 固定此行为。
4. 一个成员调整后，同 cohort 的其他成员也必须取得新分位数；Task 5 的 `test_one_adjustment_reranks_every_member_in_the_cohort` 固定此行为。
5. 外层最终发布失败必须撤销所有调整证明，但已独立发布的原始指标和政策证明仍保持真实可用；Task 4 的 `test_outer_finalization_failure_revokes_only_adjusted_children` 固定此行为。

---

## 文件图与执行顺序

新建三个职责单一的生产模块：

- `ashare_pipeline/formal_valuation_adapter_contract.py`：解析十角色图中的适配器文档，闭合 scoring/policy/adapter 三方身份，提供不可变正式注册表。
- `ashare_pipeline/formal_valuation_adapter.py`：纯 Decimal 算术和逐指标状态机；不 mint 正式证明。
- `ashare_pipeline/formal_valuation_engine.py`：构建完整调整批次、管理共享撤销能力、形成同行上下文与分位数证明、输出确定性计数和非规范耗时诊断。

修改 `formal_registry_manifest.py` 支持 v1 九角色和 v2 十角色；现有 scoring/policy registry 继续只验证其拥有的九角色依赖，不把第十角色误纳入旧合同。扩展 `tests/formal_policy_fixtures.py` 和新增 `tests/formal_valuation_fixtures.py` 负责十角色签名图及 20 人同行真实夹具。

执行顺序固定为 C1 → C2 → C3 → C4 → C5。每个任务在进入下一个任务前完成 RED、GREEN、受影响回归、审查和独立提交。

### Task 1: Versioned ten-role registry root

**Files:**
- Modify: `ashare_pipeline/formal_registry_manifest.py:24-35,154-210,218-260,377-488,560-727`
- Modify: `tests/test_formal_registry_manifest.py`
- Modify: `tests/test_formal_scoring_registry.py:46-86`

**Interfaces:**
- Consumes: 现有规范 JSON、根签名、child 签名和外层 root/child/role binding。
- Produces: `formal-registry-manifest-v2`；`FormalRegistryManifest.schema_version: str`；`FormalRegistryManifest.valuation_adapter_registry_hash: str | None`；`VerifiedRegistryBundle.roles: tuple[str, ...]`；v1 精确九角色、v2 精确十角色。

- [ ] **Step 1: 写 v1/v2 失败测试。**

```python
def test_v1_bundle_remains_valid_but_has_no_valuation_adapter_role(self):
    repository, manifest, _ = fixture_repository(schema_version="formal-registry-manifest-v1")
    bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)
    self.assertEqual(len(bundle.roles), 9)
    self.assertIsNone(bundle.manifest.valuation_adapter_registry_hash)
    with self.assertRaisesRegex(ValueError, "role is unavailable for this manifest version"):
        bundle.blob("valuation_adapter")

def test_v2_requires_exact_ten_roles_and_signed_adapter_binding(self):
    repository, manifest, _ = fixture_repository(schema_version="formal-registry-manifest-v2")
    bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)
    self.assertEqual(bundle.roles[-1], "valuation_adapter")
    self.assertEqual(bundle.blob("valuation_adapter").registry_hash,
                     manifest.valuation_adapter_registry_hash)
```

同时加入：v2 缺 child、重复 child hash、adapter child 自报错 role、错 root binding、错 approval ID、v1 偷带第十字段、未知 v3 schema、`object.__setattr__` 修改 schema/adapter hash 后 seal 失效。

- [ ] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest -v`

Expected: 新 v2 测试因 schema 和字段不存在而失败；既有 v1 测试仍通过到原断言位置。

- [ ] **Step 3: 实现版本化角色集合。**

```python
_ROLE_FIELDS_V1 = {
    "source": "source_registry_hash", "mapping": "mapping_registry_hash",
    "feature": "feature_registry_hash", "scoring": "scoring_registry_hash",
    "industry": "industry_registry_hash", "cyclic": "cyclic_registry_hash",
    "redline": "redline_registry_hash", "status": "status_registry_hash",
    "event": "event_registry_hash",
}
_ROLE_FIELDS_V2 = dict(_ROLE_FIELDS_V1,
    valuation_adapter="valuation_adapter_registry_hash")
_ROLE_FIELDS_BY_SCHEMA = {
    "formal-registry-manifest-v1": _ROLE_FIELDS_V1,
    "formal-registry-manifest-v2": _ROLE_FIELDS_V2,
}

def role_fields_for_schema(schema_version):
    fields = _ROLE_FIELDS_BY_SCHEMA.get(schema_version)
    if fields is None:
        raise ValueError("registry manifest schema_version is invalid")
    return fields
```

把 schema_version 和可空 adapter hash 纳入 manifest snapshot/fingerprint；`from_signed_bytes` 先读 schema 再计算精确 keys；v1 构造时 adapter hash 固定为 `None`，v2 必须是唯一 SHA-256。bundle 的 `roles` 从 manifest schema 导出，`require_official`、`blob`、`load` 和 `assert_member_hashes` 只接受该 schema 的精确角色集合。

- [ ] **Step 4: 更新签名图夹具，保持默认 v1。**

```python
def signed_graph(*, mutate=None, context=False,
                 manifest_version="formal-registry-manifest-v1"):
    verifier = HmacVerifier()
    wrapper = fixture_wire()
    scoring = wrapper["scoring"]
    slots = scoring.pop("fixture_feature_slots")
    policies = scoring.pop("fixture_policies")
    scoring["purpose"] = "official"
    configs = []
    if context:
        from tests.test_formal_context_repository import descriptor
        from tests.test_formal_sources import config
        wrapper["descriptors"] = [descriptor()]
        configs = [config(dataset="fixture-state", exchange_scope="SZ")]
    documents = {role: dict(registry_role=role, schema_version="fixture-v1")
                 for role in ROLES}
    documents["source"] = dict(registry_role="source",
        schema_version="formal-source-registry-v1", configs=configs)
    documents["feature"] = dict(registry_role="feature",
        schema_version="formal-feature-registry-v1",
        contract_version="formal-features-v1",
        source_registry_hash=hashlib.sha256(
            canonical(documents["source"])).hexdigest(),
        mapping_registry_hash=hashlib.sha256(
            canonical(documents["mapping"])).hexdigest(),
        template_ids=sorted(TEMPLATES),
        slots=sorted(slots, key=lambda item: item["slot_id"]))
    for role, policy in policies.items():
        policy["purpose"] = "official"
        documents[role] = policy
        scoring["policy_contracts"][role]["registry_hash"] = hashlib.sha256(
            canonical(policy)).hexdigest()
    documents["scoring"] = wrapper
    if mutate:
        mutate(documents)
    active_roles = tuple(ROLES)
    if manifest_version == "formal-registry-manifest-v2":
        active_roles += ("valuation_adapter",)
    if set(documents) != set(active_roles):
        raise ValueError("fixture documents differ from manifest roles")
    raws = {role: canonical(documents[role]) for role in active_roles}
    hashes = {role + "_registry_hash": hashlib.sha256(raw).hexdigest()
              for role, raw in raws.items()}
    root = canonical(dict(schema_version=manifest_version, purpose="official",
                          approval_id="test-graph-approval", **hashes))
    manifest = FormalRegistryManifest.from_signed_bytes(
        root, verifier.sign(root), "scoring-test-key", verifier)
    blobs = {}
    for role, raw in raws.items():
        digest = hashlib.sha256(raw).hexdigest()
        binding = canonical(dict(child_sha256=digest,
            registry_manifest_hash=manifest.manifest_hash,
            registry_role=role))
        blobs[digest] = VerifiedRegistryBlob(
            role, digest, raw, verifier.sign(raw), "scoring-test-key",
            manifest.approval_id, manifest.manifest_hash,
            verifier.sign(binding), "scoring-test-key")
    repository = InMemoryRepository(manifest, blobs)
    bundle = FormalRegistryBundleLoader(repository, verifier).load(
        manifest.manifest_hash)
    feature = bundle.blob("feature")
    vocabulary = load_signed_feature_registry(
        feature.canonical_json, feature.signature, feature.key_id, verifier,
        registry_manifest=bundle.manifest)
    return bundle, vocabulary, repository, verifier
```

默认参数必须让现有测试继续得到 v1；v2 的 mutate 必须显式加入 `documents["valuation_adapter"]`，否则精确集合检查失败。

- [ ] **Step 5: 运行 GREEN 和旧图回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_feature_contract tests.test_formal_sources -v`

Expected: 全部 PASS；v1 和 v2 的角色数、签名、seal 与篡改路径均有明确断言。

- [ ] **Step 6: 提交 C1。**

```powershell
git add ashare_pipeline/formal_registry_manifest.py tests/test_formal_registry_manifest.py tests/test_formal_scoring_registry.py
git commit -m "feat: version the formal registry root for valuation adapters"
```

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

### Task 3: Pure adjustment arithmetic and state machine

**Files:**
- Create: `ashare_pipeline/formal_valuation_adapter.py`
- Create: `tests/test_formal_valuation_adapter.py`

**Interfaces:**
- Consumes: detached canonical dicts for one base metric row, one policy result, one cyclic decision, one dependency and optional adapter definition。
- Produces: `profit_ratio_rescale(original_metric_value: Decimal, original_current_profit: Decimal, normalized_profit: Decimal) -> Decimal`；`evaluate_valuation_adjustment(*, metric: dict, policy_result: dict, cyclic_decision: dict, dependency: dict, adapter: dict | None) -> dict`。纯结果不能自称正式证明。

- [ ] **Step 1: 写数值与状态 RED 测试。**

```python
def test_matched_affected_uses_normalized_profit_ratio(self):
    result = evaluate_valuation_adjustment(
        metric=metric(value="0.20", unit="ratio"),
        policy_result=policy_result(),
        cyclic_decision=decision("matched", current="10", normalized="6"),
        dependency=affected(), adapter=adapter())
    self.assertEqual(result["status"], "adjusted")
    self.assertEqual(result["adjusted_value"], "0.12")

def test_pending_policy_blocks_only_affected_metric(self):
    pending = decision("pending_evidence")
    blocked = evaluate_valuation_adjustment(
        metric=metric(), policy_result=policy_result(), cyclic_decision=pending,
        dependency=affected(), adapter=adapter())
    passed = evaluate_valuation_adjustment(
        metric=metric(), policy_result=policy_result(), cyclic_decision=pending,
        dependency=unaffected(), adapter=None)
    self.assertEqual(blocked["status"], "pending_policy_evidence")
    self.assertIsNone(blocked["adjusted_value"])
    self.assertEqual(passed["status"], "passthrough_unaffected")
```

加入 clear、not_applicable、matched/unaffected、adjusted_no_numeric_change、错误模板/指标/利润语义、缺 normalization basis、多 basis、非 affected 却给 adapter 的精确测试。

- [ ] **Step 2: 写非法操作数 Review Focus 测试并运行 RED。**

```python
def test_invalid_adapter_operands_fail_closed_without_numeric_output(self):
    cases = (("0", "6", "original_current_profit_zero"),
             ("NaN", "6", "metric_value_nonfinite"),
             ("10", "Infinity", "normalized_profit_nonfinite"))
    for current, normalized, reason in cases:
        with self.subTest(reason=reason):
            result = evaluate_valuation_adjustment(
                metric=metric(value="NaN" if reason == "metric_value_nonfinite" else "0.20"),
                policy_result=policy_result(),
                cyclic_decision=decision("matched", current=current, normalized=normalized),
                dependency=affected(), adapter=adapter())
            self.assertEqual(result["status"], "invalid_adapter_operand")
            self.assertEqual(result["reason"], reason)
            self.assertIsNone(result["adjusted_value"])
```

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_adapter -v`

Expected: FAIL because the module does not exist。

- [ ] **Step 3: 实现固定 Decimal 内核。**

```python
def _arithmetic_context():
    return Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999,
                   Emax=999999, capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])

def profit_ratio_rescale(original_metric_value, original_current_profit,
                         normalized_profit):
    values = (original_metric_value, original_current_profit, normalized_profit)
    if any(type(value) is not Decimal or not value.is_finite() for value in values):
        raise ValueError("valuation adapter requires finite exact Decimals")
    if original_current_profit == 0:
        raise ValueError("valuation adapter original profit cannot be zero")
    with localcontext(_arithmetic_context()):
        return original_metric_value * normalized_profit / original_current_profit
```

状态机先校验所有 detached dict 的精确 keys 和跨对象身份，再根据 decision/dependency 选择透传、待补或 adjustment。输出 Decimal 使用规范字符串，并包含 operation、输入、结果、reason、decision_hash、result_hash、adapter definition hash；不接受调用者提供 status 或 adjusted_value。

- [ ] **Step 4: 验证全局 Decimal 污染和确定性。**

```python
def test_ambient_decimal_context_cannot_change_adjustment(self):
    with localcontext() as ambient:
        ambient.prec = 2
        ambient.rounding = ROUND_DOWN
        first = profit_ratio_rescale(Decimal("0.2"), Decimal("3"), Decimal("2"))
    with localcontext() as ambient:
        ambient.prec = 28
        second = profit_ratio_rescale(Decimal("0.2"), Decimal("3"), Decimal("2"))
    self.assertEqual(first, second)
```

- [ ] **Step 5: 运行 GREEN。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_adapter tests.test_formal_policy_evaluator tests.test_formal_metric_engine -v`

Expected: 全部 PASS。

- [ ] **Step 6: 提交 C3。**

```powershell
git add ashare_pipeline/formal_valuation_adapter.py tests/test_formal_valuation_adapter.py
git commit -m "feat: evaluate deterministic valuation policy adjustments"
```

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

### Task 5: Full-universe peer reranking, diagnostics and acceptance

**Files:**
- Modify: `ashare_pipeline/formal_valuation_engine.py`
- Create: `tests/test_formal_valuation_ranking.py`
- Create: `tests/test_formal_valuation_integration.py`
- Modify: `docs/superpowers/plans/2026-09-25-formal-valuation-policy-adapter-stage-c.md`

**Interfaces:**
- Consumes: genuine published `PolicyAdjustedValuationBatch`。
- Produces: `PolicyAdjustedValuationPeerContext`；`PolicyAdjustedValuationScore`；`valuation_peer_eligible(item) -> bool`；`build_valuation_peer_context(batch, *, metric_id, security_id)`；`score_valuation_percentile(batch, context)`；`FormalValuationRepository.diagnostic_report(batch) -> MappingProxyType`。

- [ ] **Step 1: 写同行语义 RED 测试。**

```python
def test_one_adjustment_reranks_every_member_in_the_cohort(self):
    batch = self.fixture.build_adjusted_batch()
    before = self.fixture.base_percentiles("V.normalized_earnings_yield")
    after = {}
    for security_id in batch.security_ids:
        context = build_valuation_peer_context(
            batch, security_id=security_id,
            metric_id="V.normalized_earnings_yield")
        after[security_id] = score_valuation_percentile(batch, context).percentile
    self.assertNotEqual(after["BJ430001"], before["BJ430001"])
    changed_peers = [sid for sid in batch.security_ids
                     if sid != "BJ430001" and after[sid] != before[sid]]
    self.assertTrue(changed_peers)
```

加入：二级 20、二级 19 回退一级 20、一级仍 19、焦点入样、并列平均秩、lower 只反转分位数、负/零/极值、pending affected 排除、pending unaffected 保留、跨批次 context 拒绝、同 cohort context 共享同一不可变同行 tuple。

- [ ] **Step 2: 写确定性计数和一次排序测试。**

```python
def test_each_cohort_is_grouped_and_sorted_once(self):
    batch = self.fixture.build_adjusted_batch()
    for security_id in batch.security_ids:
        context = build_valuation_peer_context(
            batch, security_id=security_id,
            metric_id="V.normalized_earnings_yield")
        score_valuation_percentile(batch, context)
    counts = self.fixture.repository.diagnostic_report(batch)
    self.assertEqual(counts["group_index_builds"], 1)
    self.assertEqual(counts["sorts_by_cohort"][context.cohort_hash], 1)
    self.assertEqual(counts["full_financial_rederivations"], 0)
    self.assertEqual(counts["registry_full_parses"], 1)
    self.assertEqual(counts["base_batch_full_validations"], 1)
    self.assertEqual(counts["policy_batch_full_validations"], 1)
```

规范 payload 只保存确定性计数；墙钟耗时由 `repository.diagnostic_report(batch)` 的非规范、只读报告返回，并绑定 `batch_hash`。测试不得对毫秒阈值作脆弱断言。

- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_ranking -v`

Expected: peer/score API 尚不存在或没有 cohort cache，测试失败。

- [ ] **Step 4: 实现一次分组、一次排序和独立证明。**

```python
def build_groups(rows):
    groups = {}
    for item in rows:
        if not valuation_peer_eligible(item):
            continue
        for scope, industry_id in (
                ("template_secondary_industry", item.secondary_industry),
                ("template_primary_industry", item.primary_industry)):
            key = (item.metric_id, item.template_id, scope, industry_id)
            groups.setdefault(key, []).append(item.security_id)
    return {key: tuple(sorted(ids)) for key, ids in groups.items()}

def rank_values(values, direction):
    ordered = sorted(values)
    ranks = {}
    first = 0
    with localcontext(_arithmetic_context()):
        while first < len(ordered):
            last = first + 1
            while last < len(ordered) and ordered[last] == ordered[first]:
                last += 1
            rank = (Decimal(first + 1) + Decimal(last)) / 2
            percentile = Decimal(100) * (rank - Decimal("0.5")) / len(ordered)
            ranks[ordered[first]] = (rank, Decimal(100) - percentile
                                     if direction == "lower" else percentile)
            first = last
    return MappingProxyType(ranks)
```

cohort hash 必须覆盖 adjusted batch hash、metric、definition、adapter registry、direction、scope 和同行 ID；score hash 覆盖焦点 adjusted input hash、平均秩、分位数和完整 peer context。所有证明复用 batch publication capability，不能脱离所属 batch 使用。

- [ ] **Step 5: 写端到端与诊断验收。**

```python
def test_signed_policy_to_adjusted_value_to_peer_score_is_replayable(self):
    first = self.fixture.build_adjusted_batch()
    score1 = self.fixture.score(first, "BJ430001",
                                "V.normalized_earnings_yield")
    second = self.fixture.build_adjusted_batch()
    score2 = self.fixture.score(second, "BJ430001",
                                "V.normalized_earnings_yield")
    self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
    self.assertEqual(score1.canonical_bytes(), score2.canonical_bytes())
    report = self.fixture.repository.diagnostic_report(second)
    self.assertEqual(report["batch_hash"], second.batch_hash)
    self.assertEqual(report["security_count"], 20)
    self.assertEqual(report["valuation_row_count"], 60)
```

集成测试还要从 score 反向核对 peer context、adjusted row、policy decision、normalization basis、base metric input、adapter definition 和根角色哈希；证明没有 G/M cap、Sc/B/R、eligibility 或 pool 字段。

- [ ] **Step 6: 运行 Stage C GREEN。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_valuation_adapter tests.test_formal_valuation_batch tests.test_formal_valuation_batch_guards tests.test_formal_valuation_ranking tests.test_formal_valuation_integration -v`

Expected: 全部 PASS，0 failure，0 error。

- [ ] **Step 7: 运行受影响完整回归并保存诊断。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards tests.test_formal_policy_evaluator tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_policy_integration tests.test_formal_metric_context tests.test_formal_metric_features tests.test_formal_metric_engine tests.test_formal_metric_batch_guard tests.test_formal_score_inputs tests.test_formal_scoring tests.test_formal_valuation_adapter_contract tests.test_formal_valuation_adapter tests.test_formal_valuation_batch tests.test_formal_valuation_batch_guards tests.test_formal_valuation_ranking tests.test_formal_valuation_integration -v`

Expected: 全部 PASS；把模块数、测试数、耗时、失败/错误/跳过、五个分阶段耗时、cohort/排序/待补计数写入 `.superpowers/sdd/2026-09-25-formal-valuation-policy-adapter-stage-c/task-C5-report.md`。报告不纳入正式证明哈希。

- [ ] **Step 8: 独立审查、修复并作根级新鲜复验。**

审查白名单为本计划列出的生产、测试、fixture、spec 和 plan 文件。审查必须核对：v1/v2 兼容边界、证明伪造面、跨根/跨批次、pending affected/unaffected、Decimal 失败关闭、整组重排、缓存失效、外层回滚和无最终评分越界。每个审查发现用单独失败测试复现后修复；修复后重跑 Step 6、Step 7，并在最终 HEAD 上由根代理再跑 Stage C 六模块验收。

- [ ] **Step 9: 更新计划证据并提交 C5。**

```powershell
git add ashare_pipeline/formal_valuation_engine.py tests/test_formal_valuation_ranking.py tests/test_formal_valuation_integration.py docs/superpowers/plans/2026-09-25-formal-valuation-policy-adapter-stage-c.md
git commit -m "feat: rerank policy-adjusted valuation peers"
```

最终完成条件：所有计划框勾选；工作区无意外文件；提交不含生产数据、SQLite、WAL/SHM 或进度文件；未获用户单独授权时不推送、不合并 main、不开始 Stage D。
