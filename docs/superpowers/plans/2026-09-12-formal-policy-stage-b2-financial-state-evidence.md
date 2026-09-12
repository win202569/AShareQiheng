# Formal Policy Stage B2 Financial and State Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从现有已保存财务及 Context 证据生成政策专用当前输入，支持原 optional 槽位且不改变旧评分资格。

**Architecture:** 值结构和 Decimal 桥是无证明资格的纯计算；财务仓库另外认证完整 provider、重建 V6 bundle 和实际收据，再取政策槽位及年度 AST 叶子。Context 仓库读取现有 genuine factor，精确区分 false、缺旗标和完整性错误。所有内部输入保留当前重验能力，由 B3 唯一工厂最终发布。

**Tech Stack:** Python、Decimal、unittest、现有 FormalFeatureRepository/ContextRepository 与临时 SQLite 测试夹具。

**Spec:** [Stage B design](../specs/2026-09-12-formal-policy-stage-b-design.md) §3、4、7、9、10；[总控计划](2026-09-12-formal-policy-stage-b.md)。

## Global Constraints

不能因为其他七维指标尚未完整就丢掉可证明的政策证据；同样不能因为某条政策已否决就停止检查其他适用规则。原 optional 属性、原 history gate 和旧指标资格不修改。

该桥接不恢复已经损失的原始十进制精度，不重算或改写旧财务公式。

不得捕获通用 ValueError 的文本或异常字符串猜测业务缺失；旧接口抛出的可信读取异常保持失败。

---

## 文件图与接口约束

新建 `ashare_pipeline/formal_policy_values.py`（非正式 DTO、原因码、Decimal 内核）、`formal_policy_financial.py`（政策财务来源读取）、`formal_policy_state.py`（Context 输入选择）。对应新建三个 `tests/test_formal_policy_*.py` 和 `tests/formal_policy_runtime_fixtures.py`。

允许在 `formal_feature_repository.py` 加入独立政策投影安装器及身份接点，不改变 `select_current_verified_metric_feature_state` 的 required-only 条件。原 Context 数据类型和旧仓库读取接口保持不变；新仓库封闭捕获实际依赖，不放开任意 provider 或任意 fact ID 入口。

## F1：政策值结构、Decimal 桥与真实运行夹具

**Files:** Create `ashare_pipeline/formal_policy_values.py`, `tests/test_formal_policy_values.py`, `tests/formal_policy_runtime_fixtures.py`; Modify `tests/formal_metric_feature_fixtures.py`（仅给 FinancialFixture 增加可选 exchange_rows 转发，默认行为不变）。

**Interfaces:**

- Produces: `decimal_context() -> decimal.Context`、`bridge_v6(value: float | int) -> Decimal`、`canonical_bytes(wire: dict) -> bytes`、`digest(wire: dict) -> str`。
- `PolicyPreconditionError`、`PolicyIntegrityError` 为终止类；两者继承 ValueError 以兼容调用者，但不凭旧 ValueError 文本分类。
- 非正式 `PolicyValue.from_dict(wire)` / `.to_dict()` / `.state` / `.value`：wire 严格字段 `state,value,value_type,unit,evidence_hashes,pending`。state 为 value/missing/domain_conflict；value_type 为 decimal/bool/enum/event_record/calendar_record/market_window；非 value 分支 value=null。pending 为 `origin,code,rule_id,evidence_hashes` 四字段条目；runtime 白名单完全复制规格 §9.2；signed_policy 由 W2 对具体规则二次核验。
- decimal 值 wire 用有限规范十进制字符串；bool 为 exact bool；enum 为明确字符串；复杂记录由对应 F3/W1 封闭解析，不允许任意 JSON 当作已证实输入。evidence_hashes 排序去重但不删除底层来源记录。
- `PolicyRuntimeFixture(*, range_enabled=False, templates=None)`：继承 plain `FinancialFixture`，不是 TestCase；保留 `.bundle/.scoring/.vocabulary/.provider/.feature_repository/.context/.store/.root/.frozen` 和原 `.publish_current/.persist_features/.put_industry/.close`；增加 `.policy_registry`。
- templates 明确为 `dict[canonical_security_id, template_id]`，指定时其键就是实际冻结清单，并在签名前构造对应 industry memberships 和 SH/SZ/BJ exchange_rows。FinancialFixture 新增 keyword exchange_rows=None 并将它作为非 population 场景的 rows；原 population=True 及默认三个证券行为保持不变，不复制整套基类初始化。
- `.put_policy_financial(security_id, values, *, fy_end, units, generation="g1", persist=True)` 以真实财务任务/快照/事实/feature 收据生成证据；values 为 fact_key→原数值，units 必须逐 key 提供；fy_end 无默认，不推测 FY0。
- `.policy_financial_values(security_id, *, current_equity=1.0, current_roe=5.0, current_margin=5.0, current_profit=5.0, annual_roe=(1.,2.,3.,4.,5.), annual_margin=(1.,2.,3.,4.,5.), annual_profit=(1.,2.,3.,4.,5.))` 写 FY2021–2025 真实事实及当期 FY2025、发布并保存对应 feature bundle。它只用于合成测试，不证明真实经济意义。

- [ ] **写失败测试。**

```python
from decimal import Decimal, localcontext

def test_bridge_preserves_v6_float_not_original_decimal(self):
    from ashare_pipeline.formal_policy_values import bridge_v6, decimal_context
    value = 0.1 + 0.2
    self.assertEqual(bridge_v6(value), Decimal(str(value)))
    self.assertNotEqual(bridge_v6(value), Decimal("0.3"))
    with localcontext() as ambient:
        ambient.prec = 2
        with localcontext(decimal_context()):
            self.assertEqual(Decimal("4") + Decimal("0.2"), Decimal("4.2"))
    for bad in (True, float("nan"), float("inf")):
        with self.subTest(bad=bad), self.assertRaises(ValueError):
            bridge_v6(bad)
```

增加未知 runtime reason、signed_policy 缺少/错误类型的 rule_id/code、decimal 非规范串、复制 wire 之后修改原容器不改变 DTO、错误 value_type、缺失分支偷偷携带 value 等测试。F1 是无证明资格的 DTO，只验证 signed_policy 语法；非当前规则和未签名 reason 的授权拒绝测试在拥有具体规则的 W2 执行，不改变 from_dict(wire) 签名。真实夹具签名后的改动必须失败；测试图修改必须在签名前完成。

F1 的非缺失值先支持 decimal/bool/enum；复杂 value_type 可表达有原因的 missing/domain_conflict，但不得接受非缺失任意 dict。event/calendar/market 的非缺失封闭解析由 F3/W1 的生产者合同负责实现；届时对 values 模块的修改由协调者串行分配。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values -v`。
- [ ] **实现数值内核和夹具。**

```python
import hashlib
import json
import math
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN

def decimal_context():
    return Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                   capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])

def bridge_v6(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError("finite V6 numeric value required")
    return Decimal(str(value))

def canonical_bytes(wire):
    return json.dumps(wire, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(wire):
    return hashlib.sha256(canonical_bytes(wire)).hexdigest()
```

夹具配置顺序固定：现有 FinancialFixture 的基础 industry/metrics → 新增 security_state descriptor 和三个旧 config → `add_policy_documents` → 将当期 selector 和 AST 的 FY0 同时改为 FY2025 → 如果 range_enabled 则调用 R1 `add_range_documents` → `rehash_documents` → 构造真实签名 bundle。逐年槽位保持各自 FY2021–2025；当期 ROE/利润率/利润使用独立 `fixture.policy.current.*` 事实键，年度序列保留 `fixture.policy.*`，不因同为 FY2025 而混淆独立输入。保存 financial fact 时沿用原真实 fetch/task 路径，但使用明确 units：权益/利润 CNY，ROE/利润率 ratio；不得直接把默认 CNY 的事实当 ratio。

仅提供政策事实时，旧 V6 全指标历史门槛仍使 feature bundle 处于 blocked；F1 不放宽旧门槛。F1 测试核对签名 AST、实际事实值/期间/单位，并经既有 `require_complete=False` 认证路径读取真实保存的 blocked 收据。独立政策派生值由 F2 的可选投影负责验证。

默认 fixture 用三个证券和小数据集；五模板组合测试传 templates 明确映射，不把每条格式单测扩大到全体证券。旧 `tests/formal_policy_fixtures.py` 的 FY0 静态用例不改。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values tests.test_formal_policy_registry tests.test_formal_metric_features -v`。
- [ ] **审查并提交白名单。** 本任务四个文件；提交信息 `feat: define policy values and explicit V6 decimal bridge`。

## F2：独立财务投影和年度实际叶子认证

**Files:** Create `ashare_pipeline/formal_policy_financial.py`, `tests/test_formal_policy_financial.py`; Modify `ashare_pipeline/formal_feature_repository.py`（新增独立政策路径）, `tests/formal_policy_runtime_fixtures.py`。

**Interfaces:**

- Consumes: 精确现有 FormalFeatureRepository、FormalMetricCurrentInputProvider、genuine FormalPolicyRegistry。
- 新内部 `select_current_verified_policy_feature_state(security_id, as_of_utc, *, template_id, registry_manifest_hash, policy_registry, rule_ids: tuple[str,...]) -> PolicyFeatureState`。方法从这些活动规则解析需要的签名槽位，不接收任意 feature_key 列表。允许其中 required=false，不改变旧 metric 方法。
- `FormalPolicyFinancialRepository(feature_repository, *, current_input_provider)`；`.select(security_id, as_of_utc, *, template_id, policy_registry, industry_batch: VerifiedMetricIndustryBatch) -> PolicyFinancialSelection`。消费现有真实类型，先 require_verified，再比较 root/frozen/universe 身份及 entries[security_id]；行业 unresolved 不按清单外处理。W3 负责对应同库 Context repository 的 recheck_batch，不接受自由 bool 授予 not_applicable 资格。
- 内部 PolicyFeatureState 提供 `values,blockers,slots,facts,issues,slot_issues,source_refs,input_hash,bundle_hash,projection_hash,batch_id` 只读属性及 `.to_dict()`、`.recheck()`；同时保存所选 rule_ids/selector 身份及当前 absence 标记。它只能由新增安装器铸造，供本仓库消费，不是公开结果 proof。
- 完整 issues 始终参与身份和重验，`slot_issues` 仅表示已证明的依赖影响范围。只允许同根真实 financial mapping 的 mapping_id、source_field 与交易所绑定，将指定字段级提取问题关联到 AST metric；不以自由 details 或字段名猜事实键/年份。不能定位的问题仍整体阻断；不改旧 V6/metric 全局门槛。季度标量也必须按每个实际 period_key 解析 V6 季度组成事实，版本同领先歧义保持完整性失败。
- 政策路径按实际受支持的 financial v1 loader 验证映射，未知版本或畸形已声明映射失败；生产逻辑不特判 `fixture-v1`。本任务把 `PolicyRuntimeFixture` 默认 mapping 提升为真实结构的合成签名 financial v1，仍在最终 rehash/sign 前配置，保持数值、成员和旧夹具行为；F1 的 policy_values 消费者纳入最终联合回归。
- PolicyFinancialSelection 是内部闭包登记对象，提供 `.values`（selector hash→PolicyValue）、`.annual`（series selector hash→五条年度记录）、`.lineage`、`.selection_hash`、`.recheck()`，无公开正式证据工厂。
- 年度记录字段固定 `fy_end,selector_hash,slot_hash,formula_hash,formula_version,value,unit,facts,issues,source_refs,visibility,bridge_version,projection_hash`；facts 每个叶子保存真实 fact ID、AST 路径、完整期间、会计口径；缺失记录保留目标年份及待补，不伪造有效 value。
- 为独立 F2 单测增加 fixture `.financial_selection(security_id)`：内部先用真实 industry Context 及 FormalMetricContextRepository 取得归属，再调用上述仓库，不接收能改变适用性的布尔参数。`PolicyRuntimeFixture` 在本任务扩展构造参数 `cyclic=True`（exact bool），在签名前配置合成行业成员；非周期场景使用签名周期清单外的行业，默认行为保持不变。可增加仅测试用 `mutate=None` 接点，在默认图配置后、最终重哈希和签名前修改 AST/选择器；不得在读取时更改已签名图。

- [ ] **写失败测试。**

```python
def test_optional_policy_slot_does_not_relax_metric_gate(self):
    from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
    fixture = PolicyRuntimeFixture()
    self.addCleanup(fixture.close)
    sid = "SH600000"
    fixture.policy_financial_values(sid, current_equity=-1.0)
    selected = fixture.financial_selection(sid)
    from decimal import Decimal
    self.assertTrue(any(Decimal(v.value) == Decimal("-1") for v in selected.values.values()
                        if v.state == "value"))
    with self.assertRaises(ValueError):
        fixture.feature_repository.select_current_verified_metric_feature_state(
            sid, "2026-08-31T07:00:00+00:00", template_id="bank",
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
            required_feature_keys=("bank.policy.equity",))
```

增加完整 provider 未发布→失败；provider 已发布但 receipt 未保存→current_receipt_absent；receipt 篡改→失败；FY2021 缺/重复/错年；正确期初 FY2020 权益+FY2021 利润构成 FY2021 ROE；AST/单位/口径/事实问题/公开时点不符；跨证券/模板/根；旧来源更正；当前缺失变出现；方法影子、copy/deepcopy 和伪造 selection。非周期只取适用标量，不要求五年序列。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial -v`。
- [ ] **实现独立投影。** 在原仓库新增闭包私有安装器，捕获真实 `_registry`、`_persisted_facts`、`_read_authenticated_bundle`、provider 及完整 issue 快照路径。复用纯 `evaluate_selected_features`，不调用 required-only metric 入口，也不放松其条件。读取算法顺序固定：

```python
def annual_targets(series_selector):
    expected = tuple(f"{year}-12-31" for year in range(2021, 2026))
    observations = tuple(series_selector["observations"])
    actual = tuple(item["fy_end"] for item in observations)
    if actual != expected:
        raise ValueError("annual observations must be the five distinct signed FY ends")
    return tuple(zip(expected, observations, strict=True))
```

对于每个目标，遍历签名 AST 的每个 fact 叶子，而不是数引用；按叶子的 period_key 和事实完整期间匹配，保存实际 AST 路径和 fact ID。期间解析仅使用已有财务期间语义；不从 slot 名字猜年份。target年度必须与声明的观察一致，合法期初余额不被“所有事实年末必须相同”误杀。

执行重验序列：provider 完整身份及 facts/issues 脱离快照 → 与全部持久化 facts 对比并保留完整 provider-owned issues（既有 StateStore 无全量正式 issue 列表 API） → 同根验证 → 原 V6 builder 重建 → `_read_authenticated_bundle` 认证真实收据且 require_complete=False → 逐项政策投影 → 逐年 actual leaf 核验 → bridge_v6 → 重读 provider/事实/问题/收据/来源。保存原投影 hash、原有限数的精确表示、bridge_version 和转换后字符串进入 selection_hash。仅“真实当前收据不存在”可产生 current_receipt_absent；任何可信读取异常不翻译成缺失。

`.recheck()` 重复实际依赖选择并比对规范身份，历史 selection 仅可审计；未进入 W3 publication 的 selection 不对外提供 require_official 方法。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_financial tests.test_formal_feature_repository tests.test_formal_metric_features tests.test_formal_metric_batch_guard -v`。
- [ ] **审查并提交白名单。** 本任务四个文件；提交信息 `feat: authenticate policy-specific financial and annual evidence`。

## F3：证券、监管与事件的显式状态证据

**Files:** Create `ashare_pipeline/formal_policy_state.py`, `tests/test_formal_policy_state.py`; Modify `tests/formal_policy_runtime_fixtures.py`, `ashare_pipeline/formal_policy_values.py`, `tests/test_formal_policy_values.py`（仅接通 F1 留给 F3 的封闭 event_record 值格式及其测试）。

**Interfaces:**

- Consumes: `FormalContextRepository.get_verified_many(kind, scope_key, security_ids, as_of_utc, registry_manifest_hash)`、genuine FormalPolicyRegistry。
- 内部 lineage 的完整引用为所选 Context Fact 原文加精确签名 descriptor/selector/读取身份；normalization_input_hash 绑定完整请求及 manifest/content，genuine get_verified_many 重验生产者、收据、原始字节和历史日历关系。这不是内嵌完整 OfficialSnapshotRef/receipt 导出或可独立授信的序列化证明；收据/文件丢失撤销 selection，W3 必须重新认证，不增加破坏历史读取的 current-only 快照读取。
- 可构造内部真实 FormalMetricContextRepository companion，仅复用既有同库 Context/raw/verifier 的 captured authenticity guard；不读取 universe/industry，不增加其证据前置条件，实际状态读取仍使用封存的 get_verified_many。
- Produces: `FormalPolicyStateRepository(context_repository)`；`.select(security_id, as_of_utc, *, template_id, policy_registry) -> PolicyStateSelection`；selection 提供 `.values/.lineage/.selection_hash/.recheck()`，内部身份边界与 F2 相同。
- `read_flag(flags: tuple[dict,...], flag_id: str) -> bool | None` 为纯内部辅助；显式 false 返回 false，实际缺条目返回 None，重复 ID/非 bool 返回错误。
- F1 对 present compound 的拒绝在本任务仅为 event_record 接通封闭校验：保留实际 Context 的 event_id/event_date/quantified_value/unit 四字段、已签名选择器单位和有效日期，不用裸 decimal 代替事件。普通值 DTO 不授予证据资格，来源与时点仍保存在 selection.lineage；calendar_record/market_window 留给 W1，不引入动态验证器注册。
- 用户已选择本轮保持 v1：现有规则种类不能消费 event_record，量化事件消费明确留作缺口，本任务不新增规则/更改签名合同。事件 DTO 校验不等于运行取证支持；只消费实际活动规则的既有 bool/enum 事件旗标，不读取未请求的事件描述符，不制造不存在规则的待补结果。未来启用量化事件需要独立版本化规格。
- 测试 fixture `.put_policy_context(security_id, kind, value, *, generation="g1")` 通过已签名 resolver→task→snapshot→FixtureNormalizer→Context receipt 写入；`.state_selection(security_id)` 调用 genuine 仓库。不得用 `.sql()` 直接制造正常的 proof；`.sql()` 仅负例篡改测试使用。

- [ ] **写失败测试。**

```python
def test_false_flag_is_not_missing_flag(self):
    from ashare_pipeline.formal_policy_state import read_flag
    self.assertIs(read_flag(({"flag_id": "audit", "active": False},), "audit"), False)
    self.assertIsNone(read_flag((), "audit"))
    with self.assertRaises(ValueError):
        read_flag(({"flag_id": "audit", "active": 0},), "audit")
```

另测真实存储 factor 的 false 命中 expected=false、缺审计旗标待补、白名单外 ID 合同失败、已有事件旗标不以缺失代替 false、suspended 不产生未签名否决；当前 factor 更正、来源失效、equal-leading conflict、复制和方法影子失败。量化事件的日期/单位/数值只作封闭 DTO 格式测试，并证明现有 v1 规则拒绝 event_record 输入，不伪造可消费该类型的签名规则。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state -v`。
- [ ] **实现。** 按 kind/scope 分组批量读取，security_ids 使用排序去重 tuple；保留所有 factor 来源再投影单个 entry。`get_verified_many` 返回 None 是有界的真实缺失信号，旧 `get_verified` 抛错不能当作这个信号。

```python
def read_flag(flags, flag_id):
    matches = [item for item in flags if item["flag_id"] == flag_id]
    if not matches:
        return None
    if len(matches) != 1 or type(matches[0]["active"]) is not bool:
        raise ValueError("flag must have one explicit boolean observation")
    return matches[0]["active"]
```

旧规范 regulatory flags 的实际字段就是 flag_id/active，保持原样。selection.values 以 selector_hash 为键，完整请求/来源引用保存在 lineage 中，不向 F1 封闭 PolicyValue 偷加字段。真正缺条目使用 runtime/state_entry_missing，错误单位用 unsupported_unit，时点未证明用 visibility_unproven。已登记原始来源文件不存在则整次失败，不 pending。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state tests.test_formal_policy_values tests.test_formal_context_schema tests.test_formal_context_repository -v`。
- [ ] **审查并提交白名单。** 本任务五个文件；提交信息 `feat: preserve explicit policy state coverage and missing entries`。

## B2 交接

财务/状态输入均须含当前重验方法、完整来源和明确待补，不能因为测试夹具已构造就免去 W3 再认证。所有方法及 DTO 在这三任务中定名；新增公开接口需先更新本计划并检查 B3 调用点，不能由子代理各自另起名字。
