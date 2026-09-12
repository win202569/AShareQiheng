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

## Task A1: Pure typed rule contract

**Files:** Create 三个文件：formal_policy_contract.py、test_formal_policy_contract.py、formal_policy_fixtures.py（均按上方完整目录）。

**Interfaces:** Consumes 现有 _load/_canonical 的规范 JSON 语义和上述有限格式；Produces PolicyContractError、PolicyRule、ParsedPolicyContract、parse_policy_rule、parse_policy_contract、iter_rule_selectors，以及测试辅助 `numeric_rule(template_id="bank") -> dict`、`feature_selector(template_id, name, period_key, unit) -> dict`。

- [ ] **Step 1: 写最小有效规则和第一个失败测试。** 测试辅助中的 selector 只表示合成声明；A1 不要求它已登记。

```python
def feature_selector(template_id, name, period_key, unit):
    return dict(kind="feature", template_id=template_id,
        feature_key=f"{template_id}.policy.{name}", expected_unit=unit,
        formula_version="fixture-policy-v1", period_keys=[period_key])

def numeric_rule(template_id="bank"):
    return dict(schema_version="formal-policy-rule-v1", kind="numeric_redline",
        semantic_id="nonpositive_equity", template_id=template_id,
        inputs={"value": feature_selector(template_id, "equity", "FY0", "CNY")},
        parameters={"comparator": "lte", "threshold": "0"},
        outcomes={"on_match": [{"kind": "pool_prohibition", "pool": "both"}],
            "on_clear": [], "on_missing": "pending_evidence",
            "on_conflict": "pending_evidence"})

class PolicySyntaxTests(unittest.TestCase):
    def test_numeric_rule_is_detached_and_deeply_immutable(self):
        wire = numeric_rule()
        rule = parse_policy_rule("redline", "bank_equity", canonical(wire))
        self.assertEqual(rule.semantic_id, "nonpositive_equity")
        with self.assertRaises(TypeError):
            rule.inputs["value"]["period_keys"][0] = "FY1"
        self.assertFalse(hasattr(rule, "require_verified"))
        self.assertFalse(hasattr(rule, "pool_eligible"))
```

canonical 使用现有 tests.test_formal_scoring_registry.canonical。补齐 unittest 和计划所列函数的明确导入，不创建占位生产模块来掩盖首个 RED。

- [ ] **Step 2: 运行首个 RED。**

```powershell
& $taskPython -m unittest tests.test_formal_policy_contract.PolicySyntaxTests -v
```

预期因 formal_policy_contract 尚不存在/入口未定义失败。记录实际错误；若是路径或解释器故障，先修正运行命令，不计入 RED。

- [ ] **Step 3: 实现精确字节解析、冻结及规则族分派。** 使用已有 canonical JSON 解码规则：拒绝重复键、非 UTF-8、非规范编码、NaN/Infinity；不得接受 dict 代替 raw bytes。解析后的全部规则字段按 Shared wire vocabulary 逐字段检查；未知 schema/算法返回 unsupported_contract，结构/类型/范围错误返回 malformed_contract，均带精确 path。

```python
def exact_keys(value, expected, path):
    if type(value) is not dict or set(value) != set(expected):
        raise PolicyContractError("unknown or missing object fields", path=path)

def frozen(value):
    if type(value) is dict:
        return MappingProxyType({key: frozen(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(frozen(item) for item in value)
    return value

def decimal_parameter(value, path):
    if type(value) is not str or re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is None:
        raise PolicyContractError("finite decimal string required", path=path)
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise PolicyContractError("invalid decimal", path=path) from error
    if not number.is_finite():
        raise PolicyContractError("nonfinite decimal", path=path)
    return number
```

decimal_parameter 保留原始字符串进入规范字节，不经 float 转换；阈值支持负数，cap 另核对 0..100。parse_policy_rule 的控制流是：规范解码→精确规则七键→版本/角色/模板→对应族的精确 inputs/parameters→选择器→效果→构造冻结 PolicyRule。族分派必须列出五个固定 kind，不能 getattr 动态调用或 eval。

parse_policy_contract 要求 children 键恰为 cyclic/redline/status/event，逐项解析六键 wrapper、execution_contract 三键和非空排序 rule_ids。禁止入口自身、悬空 ID、重复 ID及跨角色；inactive 旧规则不执行也不篡改。保留原始子项内容进入 canonical_json 的 `{"schema_version":"formal-policy-parsed-v1","children":...}`；parsed role_versions/evidence_categories 来自 wrapper。四角色用途必须一致；正式用途限定由 A2 处理。iter_rule_selectors 返回每条规则顶层输入选择器；annual_series 保留分组，由 A2 逐 observation 遍历。

- [ ] **Step 4: 补全具体参数化 RED/GREEN。** 增加 PolicySelectorSyntaxTests、PolicyRuleFamilyTests、PolicyEntryPointTests 三个 unittest 类。分别先提交失败用例，再实现对应分支，每组独立运行。

```python
def test_unknown_keys_and_nondecimal_thresholds_are_rejected(self):
    mutations = [lambda w: w.update(extra=True),
        lambda w: w["parameters"].update(threshold=True),
        lambda w: w["parameters"].update(threshold="NaN"),
        lambda w: w["outcomes"].update(on_missing="clear")]
    for mutate in mutations:
        wire = numeric_rule()
        mutate(wire)
        with self.subTest(wire=wire), self.assertRaises(PolicyContractError):
            parse_policy_rule("redline", "bank_equity", canonical(wire))
```

族用例使用表中完整 literals 构造：两个 quantile_method 均成功，缺失/未知算法失败；5 FY 缺年/重复/乱序失败；20→19、250→249、20→true、G cap→81、M cap 缺失失败；on_match 总分覆盖/排名覆盖/未知维度失败；unknown comparator、无符号/有符号阈值边界、Infinity、空事件 ID、非法 listing enum、未知 selector path 分别失败。验证 on_match pending_evidence 是合法红线结果，但不能替代 nonpositive_equity 的必需双池禁止（后者由 A2 覆盖检查验证）。

四入口测试基于各族的有效规则：空入口、重复/乱序活动 ID、漏角色、schema 不支持、循环引用 execution_contract 失败；增加一个未激活旧规则不会让其出现在 parsed.rules，仍会改变内容身份。不要在 A1 验证签名或来源真实数值。

- [ ] **Step 5: 运行本任务 GREEN、审查并提交。**

```powershell
& $taskPython -m unittest tests.test_formal_policy_contract -v
git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation diff --check
```

预期全绿；记录真实用例数和源文件哈希。主代理独立审查纯格式、不可变和不越权边界；通过后仅 stage 本任务三个文件，核对 cached name-only，再提交 `feat: add typed formal policy contract grammar`。不提交进度或数据。

## Task A2: Same-root binding and complete contract coverage

**Files:** Create formal_policy_registry.py、test_formal_policy_registry.py；Modify tests/formal_policy_fixtures.py。

**Interfaces:** Consumes A1 解析接口及既有 bundle/scoring/feature 类型；Produces 私有 `_bind_policy_contract(bundle, *, scoring_registry, feature_registry) -> bytes`。测试辅助新增 `policy_graph(*, version="v1", mutate=None) -> (bundle, vocabulary, scoring_registry, repository, verifier)`，`add_policy_documents(documents) -> None`，`rehash_documents(documents) -> None`。不产生 FormalPolicyRegistry。

- [ ] **Step 1: 创建轻量完整签名图与绑定失败测试。** policy_graph 通过 signed_graph（v1）或 v2_graph（v2）完成真实验签。在其签前回调内先 add_policy_documents，再应用 mutate，再 rehash_documents；从返回的 bundle 正式加载 scoring_registry。测试改变合同错误时保持外层哈希正确，避免所有错误都只测试“哈希不一致”。

```python
def rehash_documents(documents):
    feature = documents["feature"]
    feature["source_registry_hash"] = hashlib.sha256(canonical(documents["source"])).hexdigest()
    feature["mapping_registry_hash"] = hashlib.sha256(canonical(documents["mapping"])).hexdigest()
    scoring = documents["scoring"]["scoring"]
    for role in ("cyclic", "redline", "status", "event"):
        child = documents[role]
        scoring["policy_contracts"][role] = dict(
            registry_hash=hashlib.sha256(canonical(child)).hexdigest(),
            registry_version=child["registry_version"],
            source_evidence_categories=child["source_evidence_categories"])

def policy_graph(*, version="v1", mutate=None):
    if version not in ("v1", "v2"):
        raise ValueError("unknown fixture wrapper version")
    def prepare(documents):
        add_policy_documents(documents)
        if mutate is not None:
            mutate(documents)
        rehash_documents(documents)
    values = (signed_graph(context=True, mutate=prepare) if version == "v1"
        else v2_graph(mutate=prepare))
    bundle, vocabulary, repository, verifier = values[:4]
    approval = RegistryApproval("official", bundle.manifest.scoring_registry_hash,
        bundle.manifest.approval_id)
    scoring = load_formal_registry(bundle, approval, feature_registry=vocabulary)
    return bundle, vocabulary, scoring, repository, verifier

class PolicyBindingTests(unittest.TestCase):
    def test_complete_signed_graph_binds_without_runtime_evidence(self):
        bundle, feature, scoring, _, _ = policy_graph()
        raw = _bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature)
        wire = json.loads(raw)
        self.assertEqual(wire["registry_manifest_hash"], bundle.manifest.manifest_hash)
        self.assertEqual(set(wire["role_hashes"]), set(scoring.role_hashes))
        self.assertEqual(wire["contract_version"], "formal-policy-execution-contract-v1")
        self.assertNotIn("security_id", wire)
        self.assertNotIn("pool_eligible", wire)
```

add_policy_documents 的数据构造顺序必须如下，固定为合成样本，不读取生产文件：

1. 保留 mapping 和 source 既有配置；在 source.configs 中补齐同一 fixture-state 数据集的 SH/SZ/BJ 配置，使用 tests.test_formal_sources.config(dataset="fixture-state", exchange_scope=exchange)，对 (source,dataset,exchange_scope) 去重，不重复原 SZ 项。新增 Context 描述符沿用现有 descriptor 工厂的已签名 source/dataset/parser/mapping 字段；新增 scope_key 区分 regulatory/event/market/calendar，不删 v2 consensus 描述符。日历使用允许的 security_scope=security、request_security=input_security、exchange_rule=security_exchange，避免把 SZ 固定日历误当三交易所日历。该样本只是签名声明，不代表已配置运行适配器。
2. regulatory descriptor 的 allowed_regulatory_flags 显式覆盖每个审计/治理/独立状态语义且排序。市场、日历描述符用完整记录选择器；事件 fixture 的重大事件使用监管旗标，不伪造 quantified_value。
3. 每模板追加 equity、current_roe/current_margin/current_profit 和三组各五年度的 distinct slot。维度仅用于已签名槽位分类：equity→FS，ROE/margin→M，profit→V；unit 分别 CNY/ratio/ratio/CNY，required=false，公式版本 fixture-policy-v1。每年使用对应 FY2021..FY2025 的 fact 叶子，current 使用 FY0。按全局 slot_id 排序，不改任何旧指标的公式。
4. 依 Coverage matrix 生成每模板 16 条规则：cyclic_top→cyclic；nonpositive_equity→redline；major_event→event；其余→status。物理 ID 为 `<template>_<semantic>`。构造 context selector 时使用描述符 ENTRY canonical SHA-256。附加状态池限制在测试中统一显式 strong，仅是 fixture 值。
5. cyclic 测试依赖清单读取本模板三个 V 指标，第一项声明 affected、adapter_id="fixture_profit_adapter"、adapter_version="fixture-v1"；其余显式 unaffected。依据写为 fixture-only 文本，不声称经济等价。将 effects 按 canonical 字节排序。
6. 替换 scoring.redlines/status_rules 为生成的相应角色活动引用；market_liquidity_rule 引用 general_nonfinancial 对应市场规则，其他四模板市场规则仍在 status 活动入口内并由覆盖检查保证。保留 scoring.cyclic_rule 的原 classification 引用。每个指标的 policy_refs 显式指向该指标模板内 nonpositive_equity（可保留原 classification 引用），消除旧占位规则引用。
7. 每角色新增非空 execution_contract，活动 ID 排序；保留原 inactive 规则与原 classification。调用 rehash_documents 后才由原 helper 签署根/子项/绑定；不能签后修补。

- [ ] **Step 2: 运行签名绑定首个 RED。**

```powershell
& $taskPython -m unittest tests.test_formal_policy_registry.PolicyBindingTests -v
```

预期缺少 `_bind_policy_contract`。如果 fixture 在既有 feature/scoring loader 先失败，修复 fixture 的跨引用/排序并证明旧 loader 成功后再测试目标缺失接口。

- [ ] **Step 3: 从真实同根对象绑定合同。** 入口首先验证 exact type；调用原类中捕获的验证方法，而不是相信调用者替换的方法。无 StateStore 或 ContextRepository 构造。按根→四子项→选择器→覆盖→规范输出顺序处理。

```python
def _signed_periods(slot):
    periods = set()
    def visit(node):
        if node["op"] == "fact":
            periods.add(node["period_key"])
        for key in ("left", "right"):
            if key in node:
                visit(node[key])
        for child in node.get("items", []):
            visit(child)
    visit(slot.to_dict()["formula"])
    return tuple(sorted(periods))

def _context_index(wrapper):
    result, scopes = {}, set()
    for entry in wrapper["descriptors"]:
        _descriptor(entry)
        identity = hashlib.sha256(_context_canonical(entry)).hexdigest()
        scope = (entry["context_kind"], entry["scope_key"], entry["security_scope"])
        if identity in result or scope in scopes:
            raise PolicyContractError("duplicate Context descriptor", path="descriptors")
        result[identity] = entry
        scopes.add(scope)
    return result
```

_signed_periods/_context_index 为此任务定义的模块私有辅助。_descriptor 和 _context_canonical 来自现有 formal_context_schema，不重新设计 Context 格式。

具体绑定必须全部完成：

- exact VerifiedRegistryBundle、FormalScoringRegistry、SignedFormalFeatureRegistry；bundle.require_official、scoring.require_official(bundle)、feature.require_release_eligible；核对九角色实际 SHA、根哈希、feature canonical/source/mapping。正式入口不接受测试用途或 RegistryApproval 覆盖参数。
- feature 对象没有其最初加载根的字段；这里的“同根”严格指其已认证内容及 source/mapping 是当前已验证根的实际子项，不宣称核验一个不存在的原始 minting-root。相同真实 feature 内容属于两个合法根时可以使用；不同内容的旧 feature 不能混入。两个场景分别测试，不用无条件“其他根 feature 必须失败”替代实际内容检查。
- 从 bundle.blob(role).canonical_json 调用 A1；再核对四子项 purpose=official、version/categories 与 scoring.policy_contracts 完全一致。不能仅比较对象暴露的 hash 字符串。
- feature selector 的 template/slot/unit/formula_version/全部期间与 fresh slots_for_template 结果精确一致；可选槽位仍可作为政策必需，原 required 不变。年度组内 slot ID 不能重复，去除 ID 后的完整公式/单位/版本指纹也不能重复；FY 标签不等于运行期已证明年度。
- ROE/margin 的 current 与相应年度系列单位保持一致，current_profit 与年度利润单位一致；不在本层转换币种或把 ratio 改为百分数。年度 ROE 可以引用本年和上年余额；不能强制其所有叶子期间等于 fy_end。
- Context descriptor_id 必须匹配 ENTRY hash；kind/scope 和声明 field 类型一致。证券字段只允许 security/input_security；本首版单选择器、每模板全市场规则要求 security_exchange，不能使用固定 SZ 描述符代替 SH/BJ。绑定中的市场和日历选择器都须采用这一相同交易所解释；暂不引入按交易所分派选择器的新格式。解析层可表示 none/fixed 的既有描述符，但它们不能满足此全市场规则的绑定。不能拿全市场描述符冒充证券状态。
- 对被政策引用的 Context 描述符，读取已通过 bundle 验证的 source 子项 configs，以 source/dataset/实际交易所匹配。对 security_exchange 分别检查 SH/SZ/BJ：每个交易所恰好一项与现有 resolver 选择语义一致的配置，逐项比较 parser_id/parser_version/mapping_version/bootstrap_calendar、exchange_scope、calendar_selector；缺项、歧义或声明不一致拒绝。request_version/normalizer_version/generation_namespace 是描述符自身的签名字段，source config 无对应字段时不伪造比较；只验证其格式及身份保留，不证明运行 normalizer 已安装。
- regulatory/event ID 必须在已有白名单；expected_unit 对 event_record 只能验证签名声明非空，描述符没有 unit 字段，实际事件记录单位相等属于阶段 B；A2 不伪造已验证单位。对市场原值不新增 nullable valid_close。
- 每个模板按 Coverage matrix 验证必需语义、规则族、输入字段、expected=true、数值红线和必需效果；附加规则不能以相同 semantic_id 重定义必需项。不能用 expected=false 的 ST 规则反向禁止正常股票。
- 校验 scoring.redlines/status_rules/market_liquidity_rule/所有 metric.policy_refs 均指向当前活动规则，唯一特例为原 cyclic classification；指标引用必须同模板，不能复用另一模板的红线。原 classification 内容和 scoring.cyclic_secondary_industries 相同。
- valuation_dependencies 恰好等于当前模板全部维度限定 V IDs；affected 利润语义指本规则；unaffected 提供依据和 null 依赖。仅登记 adapter 身份，不 import 或执行任意 adapter。确认无跨规则/跨模板循环引用。

规范返回 bytes 的顶层精确键：schema_version="formal-policy-bound-definition-v1"、contract_version、registry_manifest_hash、role_hashes（九角色）、role_versions（四政策）、source_evidence_categories（四政策）、rules（角色/ID 排序的完整定义）、valuation_dependencies（按模板组织）、cyclic_secondary_industries（排序）、binding_manifest。

binding_manifest 保留每个选择器的规则角色/ID、输入位置、签名槽位原始定义或 Context ENTRY 原文及 ID；同一来源可按 canonical ID 去重并引用，但不能丢字段或只留人工描述。返回值不含自身 hash、不含证券 ID/实际数值/pending 状态/ready 标志；A3 在字节外计算 contract_hash，避免自引用。使用既有 canonical JSON 规则保留 Decimal 字符串。

- [ ] **Step 4: 逐组新增绑定 RED/GREEN。** 测试类为 PolicySelectorBindingTests、PolicyCoverageTests、PolicyCompatibilityTests。通过签前 mutate 构造错误；每组记录真实 RED/GREEN，至少包含如下具体测试。

```python
def test_missing_mandatory_semantic_is_rejected_after_valid_signing(self):
    def remove_st(documents):
        policy = documents["status"]["rules"]
        key = "bank_st"
        policy["execution_contract"]["rule_ids"].remove(key)
        refs = documents["scoring"]["scoring"]["status_rules"]
        refs[:] = [ref for ref in refs if ref["rule_id"] != key]
    bundle, feature, scoring, _, _ = policy_graph(mutate=remove_st)
    with self.assertRaisesRegex(PolicyContractError, "st"):
        _bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature)
```

其它用例：未知/跨模板 feature、unit/version/AST 期间不同、年度复用同槽位、不同槽位同公式伪五年、合法跨年余额 ROE 成功；Context wrapper hash 冒充 ENTRY hash、错 scope、证券字段用 none scope、非法 flag/event、expected_type 错、删除 BJ source config、source/parser/mapping/calendar 声明不匹配；删除任一必需语义、取消双池禁止、权益阈值从0改1、expected=true改false、同模板重复语义、删除原 scoring 引用活动 ID；V 依赖漏项/重复/非 V/跨模板/affected 无版本/unaffected 非 null 失败。真实旧图无 execution_contract 时，旧 load_formal_registry 仍成功，而新绑定失败。

兼容用例分别用 policy_graph(version="v1") 和 policy_graph(version="v2")，证明原 descriptor ENTRY/consensus links 不变、输出包含正确根身份；不修改原 JSON fixture。故意让同一规则在签名前改变 definition_basis 文字并 rehash，应产生不同 root/规范绑定字节；混用旧 scoring 必须失败。feature 内容未变且满足当前根绑定时允许合法复用；feature 内容变化则旧 feature 失败。边界异常来自旧 loader 时保留 ValueError/原因，不把它转换成空合同。

- [ ] **Step 5: 本任务验收、独立审查和提交。**

```powershell
& $taskPython -m unittest tests.test_formal_policy_contract tests.test_formal_policy_registry -v
& $taskPython -m unittest tests.test_formal_scoring_registry tests.test_formal_scoring_consensus_registry -v
git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation diff --check
```

记录实际用例数、时长及源文件哈希。只承诺“完整绑定字节可构造”，不宣称可信政策证明或可评分。审查通过后仅提交本任务三个文件：`feat: bind formal policy contracts to signed registry graph`。

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

## Review, performance and handoff

- A1→A2→A3 是依赖链，不并行改同一文件。每任务使用新子代理实施，独立审查后才启动下一任务；可并行开展只读接口核对或不重叠的回归检查。修复回原实施者及原审查者，不重启已完成任务。
- 既有 source/feature/context 生产代码和原 fixture 不在白名单，默认只回归纯合同测试。若确有批准的 Context 包装层改动，再加 `tests.test_formal_context_repository.ScoringWrapperIntegrationTests`；该类写临时 SQLite，不能混入当前“不写 SQLite”的阶段 A 执行范围。
- 不运行 ScoreFixture.populate_scores、22 证券同行、全年抓取或完整财务集成样本来验证纯政策格式。旧 Task 3B 测试结果按原哈希保留，不伪称本次全部重跑。
- 每次修改后的验证和审查都绑定具体 SHA-256；代码再变必须覆盖对应差异，不累计成虚假的“最终版本全测通过”。运行变慢时报告实际进程/耗时，不无依据说卡死，也不重复开相同套件。
- 台账位置为 `.superpowers/sdd/2026-09-04-formal-v3-scoring-pool-engine/progress.md`，主代理以 apply_patch 保留任务状态、RED/GREEN、审查与提交。台账不随纯代码提交，但不得删除。
- 阶段 A 完成只可宣称“政策定义和静态绑定已验证”。阶段 B 的窗口/无价格证据、新事件格式、实际政策执行；阶段 C 的利润适配器、全同行重算、置信度和最终评分；Task 5 的双池及后续持久化/发布，均不属于本计划。

## Plan self-review and coverage

| 规格要求 | 验收任务 |
| --- | --- |
| §1–3 三阶段权限、旧 wrapper/注册图、同根签名 | A1 解析；A2 真签名绑定；A3 不越权入口 |
| §4 财务 AST/FY/Context 描述符和白名单 | A1 精确格式；A2 完整静态绑定；实际证据留在 B |
| §5 周期/红线/硬否决/独立状态/流动性/V 依赖 | A1 规则族与常量；A2 五模板语义及引用闭合 |
| §6 失败分类、规范身份及不制造 pending 证券 | A1 error；A2 canonical payload；A3 read guard |
| §7–8 B/C 运行及重算边界 | A3 拒绝把定义作为评分输入；本计划不执行 B/C |
| §9 离线、真实签名、兼容/失败/复制替换测试 | A1–A3 对应测试和最终回归 |
| §10–11 审批与分阶段交付 | 三次独立审查/纯代码提交；保留台账与生产审批边界 |

计划作者自检：所有新增函数/类型由对应任务定义；生产权威入口只有 A3；没有“给规则签个名就能评分”的路径。上位经济规则、已批准规格和本计划冲突时，停止对应实现并报告精确冲突，不能靠测试 fixture 修改经济口径。
