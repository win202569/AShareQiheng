# Formal Policy Contract Stage A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从真实同根签名注册图加载可审计、不可变的政策定义，拒绝不完整或越权合同，不执行证券政策或生成最终评分。

**Architecture:** 将纯格式解析放入 formal_policy_contract.py，将同根绑定、覆盖检查及最终可信入口放入 formal_policy_registry.py。三个任务依次交付纯解析、完整绑定、读取时认证；前两个任务的公开结构或 bytes 都不是政策证明。沿用已有签名验证、Context 描述符和财务 AST，不增加运行取数或通用表达式引擎。

**Tech Stack:** 现有 Python 环境、标准库 unittest/dataclasses/decimal/json/hashlib/types/weakref；已有真实签名测试图。无新增依赖、数据库迁移或网络调用。

**Spec:** [正式 V3 政策合同与证据集成设计](../specs/2026-09-12-formal-policy-contract-design.md)，用户于本轮明确确认。上位经济规则见 [正式评分与发布合同](../specs/2026-09-04-formal-scoring-release-contract-design.md)。本计划仅实现前一规格的阶段 A。

## Global Constraints

- 冻结时点为北京时间 2026-08-31 15:00（UTC 07:00）；SH/SZ/BJ 普通 A 股统一处理。
- 同行资格始终是指标级资格，不能按“七维完整”“可入池”或“未被否决”过滤同行。
- 缺失、冲突和无效分母不填零、不填行业中位数、不改权重。
- 原 `PrePolicyScoreCalculation` 继续明确标识 `pre_policy`，不能借改字段名升级为最终评分卡。
- 本阶段不改生产数据、不抓取、不写 SQLite、不生成股票池或正式报告。
- 保留政策子项现有六键及外层 `formal-scoring-policy-v1`，scoring wrapper 保持 v1/v2；classification 仍只有 secondary_industries。
- 四个执行入口非空；五模板完整覆盖；20/250 日、五 FY、0.80 分位、G/M 80 上限及双池硬否决不得改变。
- 生产分位数算法、真实字段映射、附加阈值和签名仍由生产合同明确批准；合成测试不授予生产权威。
- 保留所有历史数据、SQLite、WAL/SHM、进度、旧发布和无关文件；不合并 main、不推送。

---

## Execution context and file ownership

基线提交：`49237a7dbd41eac58474ac472d914891d696f79b`（已提交的设计规格）。继续使用已建立的隔离工作树，不创建第二份工作树。

```powershell
Set-Location -LiteralPath 'D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation'
$taskPython = 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe'
git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation branch --show-current
git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation status --short
```

预期分支 `codex/formal-v3-implementation`；保留现有 `tmpj4zv9_fq/`。主工作树不是执行目录。所有编辑使用 apply_patch；Git 写入由主代理在通过审查后按文件白名单进行。每个任务先完成 RED，再完成 GREEN；不把导入错误以外的环境故障算作有效 RED。

| 文件 | 职责 | 所属任务 |
| --- | --- | --- |
| Create: ashare_pipeline/formal_policy_contract.py | 有限规则格式、精确类型、静态常量及未认证解析值 | A1 |
| Create: tests/test_formal_policy_contract.py | 纯格式/类型/常量测试 | A1 |
| Create: tests/formal_policy_fixtures.py | 合成规则及签名前构图辅助，无生产映射 | A1 创建纯规则；A2 增加签名图 |
| Create: ashare_pipeline/formal_policy_registry.py | 同根绑定、覆盖检查；最终封闭验证入口 | A2 创建绑定；A3 加入口 |
| Create: tests/test_formal_policy_registry.py | 真实签名图、选择器、覆盖和兼容验证 | A2 |
| Create: tests/test_formal_policy_registry_guards.py | 读取时认证、复制/替换/来源失效边界 | A3 |

无需修改现有生产模块：`FormalScoringRegistry.require_official(bundle)`、`SignedFormalFeatureRegistry.slots_for_template()` 及子项原始字节已足够。若实现发现必须增加适配，先报告具体缺失接口及最小变更，不能自行放宽旧校验。

### Existing interfaces to read before coding

- `formal_registry_manifest.py`：VerifiedRegistryBundle、require_official、blob；根与九子项验证。
- `formal_scoring_registry.py:197` `_graph`、`:213` `_policies`、`:255` `_formula_requirements`、`:526` require_official：复用语义，不复制另一套经济公式。
- `formal_feature_contract.py:330` FormalFeatureSlot、`:607` slots_for_template：slot.to_dict()["formula"] 是已签名 AST，期间集合不是槽位名。
- `formal_context_schema.py:385` `_descriptor` 与 `:153` `_validate_value`：Context 字段、作用域、白名单及正价格旧格式。
- `formal_scoring.py:142` 至文件尾：当前已审查的 closure-private 证明和依赖替换防护模式；只参考，不改动。
- `tests/test_formal_scoring_registry.py:46` `signed_graph(*, mutate=None, context=False)` 返回 bundle/vocabulary/repository/verifier；回调发生在签名前。
- `tests/test_formal_scoring_consensus_registry.py:18` `v2_graph(*, template_ids=("bank",), descriptor_changes=None, mutate=None)` 返回上述四项及描述符/ID；保留已有一致预期链接。

## Shared wire vocabulary and task interfaces

以下为已批准规则的序列化细化，不选择新经济规则。未知键一律拒绝。所有对象是精确 dict，数组是精确 list，文本是精确非空去首尾空白 str；bool 不能作为数字或整数。解析后容器只使用 MappingProxyType/tuple，结果没有数据库证据权威。

### Selectors

| kind | 精确字段及约束 |
| --- | --- |
| feature | kind/template_id/feature_key/expected_unit/formula_version/period_keys；period_keys 非空、排序、去重；绑定任务核对同模板槽位和完整 AST 期间 |
| annual_series | kind/observations；每项恰好 fy_end/selector，selector 只能为 feature；fy_end 恰为 2021-12-31 至 2025-12-31，按年升序 |
| context | kind/descriptor_id/context_kind/scope_key/field/entry_id/expected_type/expected_unit；descriptor_id 为小写 64 位 SHA-256 |

Context field/expected_type 的有限映射为：security_state 的四个布尔字段→bool、listing_status→enum；regulatory_state 的 active→bool；event_calendar 的 event→event_record；market_close 的 record→market_record；trading_calendar 的 record→calendar_record。前两类状态及市场/日历的 expected_unit=null；event_record 必须声明非空单位。flag/event 的 entry_id 非空，其他类型为 null。event_record 只是类型化声明，不新增以量化事件替代非量化风险的执行器。

### Rules and effects

活动规则精确键：schema_version/kind/semantic_id/template_id/inputs/parameters/outcomes。版本 `formal-policy-rule-v1`。semantic_id 在同一模板全角色范围唯一；物理 rule_id 在角色内唯一，规范排序键为 (role, rule_id)。

所有 outcomes 精确为 on_match/on_clear/on_missing/on_conflict。on_match 为非空效果数组，on_clear=[]，on_missing/on_conflict="pending_evidence"。

| 效果 kind | 精确字段 | 约束 |
| --- | --- | --- |
| dimension_cap | kind/dimension/maximum | 七维之一，maximum 为有限 Decimal 字符串，0≤值≤100 |
| pool_prohibition | kind/pool | strong/wait/both |
| valuation_profit_basis | kind/profit_semantic_id | 与本周期规则 semantic_id 相同 |
| independent_status | kind/status_code | 本规则对应的显式状态码；非空标识符 |
| pending_evidence | kind/reason_code | 非空签名原因码，不吞掉合同错误 |

效果按其规范 JSON 字节排序且无重复。不执行任何效果。模板为 general_nonfinancial/bank/broker/insurance/real_estate。

| 规则 kind / 角色 | inputs 精确键 | parameters 精确键及限制 |
| --- | --- | --- |
| numeric_redline / redline | value（feature） | comparator（lt/lte/gt/gte/eq），threshold（有限有符号 Decimal 字符串） |
| boolean_state / status 或 event | value（bool Context） | expected（精确 bool） |
| enum_state / status 或 event | value（enum Context） | values（排序、唯一、非空，来自 listed/delisting_arrangement/delisted） |
| cyclic_protection / cyclic | current_roe/current_margin/current_profit（feature），annual_roe/annual_margin/annual_profit（annual_series） | fy_ends，quantile_method，quantile_level，median_method，profit_basis_method，valuation_dependencies |
| market_liquidity / status | market（market_record），calendar（calendar_record） | effective_trade_method，veto_trading_days，close_search_trading_days，required_evidence_capability |

周期 parameters 固定 fy_ends 为上述五日期，quantile_level="0.80"，median_method="ordered_middle_v1"，profit_basis_method="minimum_current_and_five_fy_median_v1"。quantile_method 只能显式选择 linear_type7_v1 或 nearest_rank_v1；解析器不计算任一算法。on_match 必须包含 G/M 各 80 封顶、valuation_profit_basis、cyclic_top 独立状态及显式池限制；其他维度封顶和待补效果不用于代替这些必需结果。

valuation_dependencies 是按 metric_id 排序的非空数组；每项精确字段为 metric_id/policy_dependency/profit_semantic_id/adapter_id/adapter_version/definition_basis。affected 的三个依赖身份非空，其中 profit_semantic_id 指向本周期规则；unaffected 的三个身份均为 null。definition_basis 非空。绑定任务要求列表恰好覆盖本模板所有 `V.<leaf_metric_id>`，无其他维度。

市场 parameters 固定为 effective_trade_method="exchange_allows_and_positive_volume_turnover_v1"、veto_trading_days=20、close_search_trading_days=250、required_evidence_capability="verified_market_window_v1"。on_match 必须包含禁止双池；能力声明不等于已有窗口证据。

### Coverage matrix

下表每个模板都必须覆盖；软件只核对已批准条件和显式签名声明，不猜证券实际状态。

| semantic_id | 必须绑定 | 必需匹配效果 |
| --- | --- | --- |
| st / star_st | security_state.is_st / is_star_st，expected=true | 双池禁止 |
| delisting_arrangement | listing_status，values 至少含 delisting_arrangement | 双池禁止 |
| forced_delist_risk | security_state.forced_delist_risk，expected=true | 双池禁止 |
| governance_red / audit_qualified / audit_adverse / audit_disclaimer | 已授权 regulatory_state.active，expected=true，flag ID 显式绑定该语义 | 双池禁止 |
| nonpositive_equity | numeric_redline，lte，threshold 数值为 0 | 双池禁止 |
| no_effective_trade_20d | market_liquidity，20/250 固定 | 双池禁止 |
| governance_orange / crowding / major_unlock_window / major_reduction_window / major_event | 已签名显式状态规则；本版使用已授权监管旗标，expected=true | 同名 independent_status 和显式 strong/wait/both 限制 |
| cyclic_top | cyclic_protection，取数受原 classification 清单约束 | G/M 80、利润依据、同名状态、显式池限制 |

同一模板的不同监管语义必须使用不同的 (descriptor_id, entry_id)；不能把一个通用“风险”旗标复用为所有审计和治理结论。允许同一语义在不同模板共享实际监管描述符。附加签名规则可以存在，但不能代替必需项或改变硬否决效果。

### Python interfaces

```python
# formal_policy_contract.py -- detached syntax values, never proofs
@dataclass(frozen=True, slots=True)
class PolicyRule:
    role: str
    rule_id: str
    kind: str
    semantic_id: str
    template_id: str
    inputs: Mapping[str, object]
    parameters: Mapping[str, object]
    outcomes: Mapping[str, object]

@dataclass(frozen=True, slots=True)
class ParsedPolicyContract:
    rules: tuple[PolicyRule, ...]
    role_versions: Mapping[str, str]
    evidence_categories: Mapping[str, tuple[str, ...]]
    canonical_json: bytes

class PolicyContractError(ValueError):
    def __init__(self, message, *, code="malformed_contract", path="contract"):
        self.code, self.path = code, path
        super().__init__(f"{code}:{path}: {message}")

# Defined in A1. Exact return types apply; body must not mint trusted objects.
# parse_policy_rule(role: str, rule_id: str, raw: bytes) -> PolicyRule
# parse_policy_contract(children: Mapping[str, bytes]) -> ParsedPolicyContract
# iter_rule_selectors(rule: PolicyRule) -> tuple[Mapping[str, object], ...]

# Defined in A2. Private binding result is canonical bytes, not a proof API.
# _bind_policy_contract(bundle: VerifiedRegistryBundle, *,
#     scoring_registry: FormalScoringRegistry,
#     feature_registry: SignedFormalFeatureRegistry) -> bytes

# Defined in A3. The sole authenticated public entry point.
# load_formal_policy_registry(bundle: VerifiedRegistryBundle, *,
#     scoring_registry: FormalScoringRegistry,
#     feature_registry: SignedFormalFeatureRegistry) -> FormalPolicyRegistry
```

PolicyRule/ParsedPolicyContract 可直接构造，只供解析测试和内部数据传递；不得被后续直接接受为已认证输入。A2 必须自行从 bundle 重新读取、解析，不能接收调用者的 ParsedPolicyContract。A3 封装 A2 返回的规范字节，绝不提供公开 mint/from_dict/from_bytes 入口。

## Task A3: Authenticated read-only policy registry

**Files:** Modify ashare_pipeline/formal_policy_registry.py；Create tests/test_formal_policy_registry_guards.py。

**Interfaces:** Consumes A2 `_bind_policy_contract`；Produces `FormalPolicyRegistry` 与 `load_formal_policy_registry`。对象字段与 A2 payload 一致，另有 contract_hash=sha256(canonical_bytes).hexdigest()。方法为 require_verified()->None、canonical_bytes()->bytes、to_dict()->dict。没有 evaluate/apply/score/policy_ready/pool_eligible；没有接受公开 dict 的认证入口。

- [ ] **Step 1: 对公开入口和不可伪造证明写 RED。**

```python
class PolicyProofTests(unittest.TestCase):
    def test_loaded_contract_is_immutable_but_does_not_grant_runtime_readiness(self):
        bundle, feature, scoring, _, _ = policy_graph()
        proof = load_formal_policy_registry(bundle,
            scoring_registry=scoring, feature_registry=feature)
        proof.require_verified()
        self.assertEqual(proof.contract_hash,
            hashlib.sha256(proof.canonical_bytes()).hexdigest())
        self.assertEqual(proof.to_dict()["role_hashes"], dict(scoring.role_hashes))
        for forbidden in ("pool_eligible", "policy_ready", "evaluate", "score"):
            with self.subTest(name=forbidden), self.assertRaises(AttributeError):
                getattr(proof, forbidden)
        changed = proof.to_dict()
        changed["role_hashes"]["status"] = "0" * 64
        proof.require_verified()
        self.assertNotEqual(proof.to_dict(), changed)

    def test_direct_and_unregistered_proofs_are_rejected(self):
        with self.assertRaises(TypeError):
            FormalPolicyRegistry()
        forged = object.__new__(FormalPolicyRegistry)
        with self.assertRaises(ValueError):
            forged.require_verified()
```

- [ ] **Step 2: 运行目标 RED。**

```powershell
& $taskPython -m unittest tests.test_formal_policy_registry_guards.PolicyProofTests -v
```

预期公共入口尚不存在；不得以绕过签名的 fixture-only mint 修复。

- [ ] **Step 3: 安装 closure-private 加载器和读取时认证。** 沿用 formal_scoring.py 的已审查模式：weakref 所有权表、无实例 payload 槽位、封闭入口、读取前认证、普通方法/继承替换检查。不增加通用安全框架，也不修改旧类型。

```python
# Core record shape inside the module-local installer:
# records[id(proof)] = (weakref.ref(proof, cleanup), frozen_payload,
#     canonical_bytes, bundle, scoring_registry, feature_registry,
#     expected_root_hash, expected_role_hashes)

class ProofMeta(type):
    def __setattr__(cls, name, value):
        if name in ("__getattribute__", "__bases__"):
            raise TypeError("policy proof lookup or inheritance cannot be replaced")
        return super().__setattr__(name, value)

    def __delattr__(cls, name):
        if name in ("__getattribute__", "__bases__"):
            raise TypeError("policy proof lookup or inheritance cannot be removed")
        return super().__delattr__(name)
```

installer 内实现以下完整步骤，名称和职责固定：

1. `dependencies()`：捕获并比较本模块 parse/bind/encode/freeze/hash 函数、上游模块及精确类型导出、实际使用的 require_official/require_release_eligible/blob/slots_for_template 方法；核对证明类全部成员和继承关系。依赖列表只覆盖实际调用路径，包括调用函数所属模块的绑定，不仅检查本模块别名。
2. `verify_sources(bundle, scoring, feature)`：用捕获的原方法认证 exact 三类型及九角色/source/mapping/原始字节；返回根与角色身份。读取时若上游 mutate、被复制或验证依赖替换即失败。签名图对象是不可变历史定义，不引入不存在的数据库 generation。
3. `proof_record(proof)`：先 dependencies，再 exact proof 类型、弱引用身份、记录存在；再 verify_sources 并与记录身份一致。闭包私有 frozen_payload/bytes 保证结果未变；不能接受仅 hash 相同的公开值对象。
4. 证明类 `__getattribute__` 在方法/字段解析前调用 proof_record；`__getattr__` 只读取记录里的白名单 payload 和 contract_hash，其他 AttributeError。require_verified/canonical_bytes/to_dict 都再次经过认证；to_dict 只返回深层脱离副本。__copy__/__deepcopy__/序列化重建禁止。
5. loader 调用 dependencies、verify_sources、A2 bind；解析冻结规范 payload，sha256 放在返回字段 contract_hash 而不写入被 hash 的 bytes；在最终发布前再 verify_sources 比较身份，并且只在全部成功后注册新 proof。构造失败不留可用记录。
6. weakref cleanup 只移除对应对象的私有记录；不能持有 proof 自己的强引用，也不能用自定义闭包引用形成环。成功的 proof 可以保留源注册对象作为历史审计依据。

不借新类“修复”Python 解释器/元类底层任意篡改，维护现有普通替换威胁边界。避免在同一字段读取重复解析全部政策图；源身份验证不可去掉，完整规则重解析只在加载发生。A1/A2 的 detached 结果永远无法自行注册到此私有表。

- [ ] **Step 4: 分组验证替换、失效和不越权边界。** 新增 PolicyProofGuardTests。具体场景为：复制三种输入；其他根混用；object.__new__ 的 proof；copy.copy/deepcopy(proof)；规则嵌套字段写入；上游特征 hash/slots 替换；模块导出类型、parse_policy_contract、_bind_policy_contract、sha256 或 verify 方法替换；Proof.require_verified 替换成 lambda、普通属性遮蔽 contract_hash、__bases__/__getattribute__ 替换。替换在测试 cleanup/finally 恢复；每个测试都先证明原始图可以加载，再证明被替换后旧 proof 读取和新 loader 均失败。

```python
def test_replacing_class_verifier_does_not_bypass_attribute_guard(self):
    bundle, feature, scoring, _, _ = policy_graph()
    proof = load_formal_policy_registry(bundle,
        scoring_registry=scoring, feature_registry=feature)
    original = FormalPolicyRegistry.require_verified
    try:
        FormalPolicyRegistry.require_verified = lambda self: None
        with self.assertRaises(ValueError):
            proof.require_verified()
        with self.assertRaises(ValueError):
            _ = proof.contract_hash
    finally:
        FormalPolicyRegistry.require_verified = original
    proof.require_verified()
```

加显式阶段边界测试：合同无证券/行情/年度实际值仍可验证定义；market_window 和 adapter 只有声明；PolicyRule、ParsedPolicyContract、绑定 bytes 均不能成为 FormalScoreInput 或 PrePolicyScoreCalculation 输入（用原 calculate_pre_policy_score 对这些值失败，不构造完整评分 fixture）。继承的旧 v1/v2 格式、原 classification 和旧正价 Context 规则仍保持。

- [ ] **Step 5: 最终验收、独立审查及提交。**

```powershell
& $taskPython -m unittest tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v
& $taskPython -m unittest tests.test_formal_registry_manifest tests.test_formal_feature_contract tests.test_formal_scoring_registry tests.test_formal_scoring_consensus_registry tests.test_formal_context_schema -v
git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation diff --check
```

预期全部通过；记录实际命令、退出码、计数、时长和最后修改后的文件哈希。主代理验证独立审查结论及代码差异后，仅 stage 本任务两个文件，提交 `feat: expose authenticated read-only policy registry`。最后核对 HEAD 文件清单、空 index、无 tracked 未提交变更；不删除无关 tmp。


## Controller handoff — ACTIVE

- BASE: 6ea72c16ba206cdf69f5f1ac6aaaa9a1258fd670. A2 accepted with no review findings and committed; parent independently reran A1+A2 68 tests / 148.825s OK. Current index/tracked tree clean, only pre-existing tmpj4zv9_fq/ untracked. Use this actual committed binder and fixture. The interface inventory below is unchanged and now final, not provisional.
- Allowed edits only: ashare_pipeline/formal_policy_registry.py; tests/test_formal_policy_registry_guards.py; this workspace's task-A3-report.md. Preserve existing A1/A2 tests and helpers. No Git writes/commits, subagents/reviewers, network, SQLite or production data changes. Controller owns commit after independent review. All edits apply_patch and TDD.
- Approved spec actual worktree path: docs/superpowers/specs/2026-09-12-formal-policy-contract-design.md (copied brief's original relative Markdown link is relative to the plan directory, not this workspace).
- Existing A2 tests: 40 binding/coverage/compatibility cases; combined A1/A2 68, legacy scoring/consensus 27. A2 output retains 80 rules and 170 selector binding entries. Real policy_graph returns bundle, feature, scoring, repository, verifier and supports v1/v2; synthetic declarations are never production evidence.
- Retain upstream root/feature/scoring authentication; do not duplicate repeated full policy parsing on reads. A2's template-keyed cyclic dependency output is protected by A1's one cyclic_top semantic per template; do not widen that grammar. Generic event_record syntax has no current active consuming rule; major_event is the approved regulatory flag; no runtime unit/evidence claim.

### Read-only guard preflight (settled before activation)

- A2 initial review snapshot actual interface inventory (not yet accepted base): binder is a closure installed then installer deleted; it captures upstream exact types and original verifier/blob/slot methods. Remaining call-path helpers are module globals _canonical, _signed_periods, _context_index, _source_index, _bind_context, _bind_selectors and _require_coverage, plus parser/descriptor/formula helper imports. A3 must verify the FINAL reviewed definitions/owner bindings; do not bypass captured methods or execute binding on each attribute read. Current A2 has no freeze helper or public proof yet. Final base and any fix deltas will be appended on activation.

- Existing formal_scoring.py:132-209 and :309-377 provide the approved local proof pattern: capture exact callable/module identities, guarded lookup, weakref ownership, two source checks. Use this pattern locally; do not redesign or modify old proof types.
- VerifiedRegistryBundle.require_official(self) and blob(self, role) are direct methods of the closure-created type (formal_registry_manifest.py:564-586). Official validation checks seals/roles/approvals; the scoring module's _graph additionally rehashes all nine actual child bytes.
- FormalScoringRegistry.require_official(self, registry_bundle) (formal_scoring_registry.py:516-528) calls owner-module globals _graph and _feature_slots. Capture and check these actual owner bindings, not merely the imported method. _feature_slots checks its retained feature and reparses all five template slots. Do not duplicate all five slot parses separately on each proof read; authenticate the supplied feature independently and compare its actual canonical/source/mapping identity to the current root. There is no original minting-root field on the feature type.
- SignedFormalFeatureRegistry.require_release_eligible and slots_for_template are direct methods (formal_feature_contract.py:607-614); FormalFeatureSlot.to_dict preserves the detached signed AST. Only check actual call-path dependencies, including module owners reached by captured functions; ordinary module/type/method replacement must fail closed, not just changes to local aliases.
- Include the local and defining-module parse_policy_contract bindings, binder, canonical encoder/freeze/hash helpers, json.loads/dumps, hashlib.sha256, weakref.ref, MappingProxyType, own proof/loader exports and class member/MRO/bases identities as applicable to the final actual implementation. Restore mutations in tests.
- No full policy reparse or binder execution in proof_record. Source identity reauthentication remains mandatory. Weakref cleanup compares the callback reference with the current record, captures only the object ID (not the proof), and removes only its own record. Reject pickle/reconstruction as well as shallow/deep copy. Use a fixed public-field whitelist.
- Ruling: contract_hash is an extra read-only public field and is included in the detached to_dict result, but canonical_bytes remains exactly A2's bound bytes and excludes contract_hash. This follows the planned extra object field and avoids self-referential hashing. Pin both behaviors in tests; cost if wrong is a narrow serialization-view incompatibility, not changed signed bytes.

Workdir: D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation. This is A3 only; read the approved spec linked above. Do not read the entire multi-task plan. The predecessor must be reviewed and committed before activation. Controller owns Git staging/commits; worker performs no Git writes. No subagents/reviewers. Use TDD/apply_patch; no data, network, SQLite or unrelated cleanup. Report in this workspace's task-A3-report.md with exact RED/GREEN commands/output/counts/times, source hashes and self-review; short DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED response. Earlier task API/commit facts will be appended before activation.
