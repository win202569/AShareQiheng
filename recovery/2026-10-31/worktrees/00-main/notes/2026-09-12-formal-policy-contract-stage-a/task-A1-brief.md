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


## Controller dispatch constraints

- Workdir: D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation; BASE b9b367d64d1204985ddbea77e7ca6f7832694ae8.
- Implement A1 only. Read the linked approved specification fully for authority; do not read the entire multi-task plan.
- Allowed edits: ashare_pipeline/formal_policy_contract.py; tests/test_formal_policy_contract.py; tests/formal_policy_fixtures.py; this workspace's task-A1-report.md. Use apply_patch for all edits.
- No Git writes, commits, data/network/SQLite changes or unrelated cleanup. The controller stages and commits after independent review. Do not dispatch subagents or reviewers.
- Baseline already uses the installed Python; do not install dependencies. Focused TDD and one final A1 suite; no 22-member/cohort/financial-population fixtures.
- Follow test-driven-development including writing-good-tests; record exact commands, RED/GREEN outputs/counts/times and final source SHA256 in task-A1-report.md. Self-review and report DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT in fewer than 15 lines.
- Semantic enforcement split: A1 validates syntax, rule-family constants/effects and unsupported versions; mandatory per-template coverage, source identity, nonpositive_equity required veto and signed AST binding belong A2. No runtime evidence is authenticated in A1.
- Plan example unittest imports may initially raise ModuleNotFoundError. Prefer an explicit missing-module/entrypoint assertion for an informative RED when practical; never count a typo/path/environment failure as RED.

