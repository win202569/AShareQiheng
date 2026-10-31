# Task F2 brief

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。

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
- 为独立 F2 单测增加 fixture `.financial_selection(security_id, *, cyclic=True)`：内部先用真实 industry Context 及 FormalMetricContextRepository 取得归属，再调用上述仓库，cyclic 参数只改变签名前的合成行业清单，不直接传入证明。

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

## Binding spec excerpts

## 3. 身份、证据对象与读取资格

每个正式批次共同绑定：合同/算法版本、根清单哈希、九角色哈希、policy registry 合同哈希、冻结输入哈希、宇宙/证券集合哈希、冻结时点、行业批次身份，以及全部实际读取证据的内容身份。证券级对象另外绑定证券、交易所、模板和适用规则。缺失标记也必须绑定它所对应的请求和当前代际。

证据分三种，不以一个 `verified=true` 混淆：

- 已验证的值及其来源。
- 对特定当前请求的已验证缺失/领域问题记录；证明“当前证据不足”，不证明该事实为零或为假。
- 无法建立可信读取的失败诊断；不属于可供政策计算消费的证据对象。

公开对象提供 `require_verified()`、规范字节、只读审计视图和内容哈希。普通构造、复制、继承替换、字段/方法影子或跨仓库拼装不得制造正式资格。仍沿用既有可信 Python 运行时边界，不新增对任意解释器篡改的防御承诺。

规范序列化使用严格 JSON、UTF-8、固定键排序，无 NaN/Infinity；精确区分 bool/int/float/string/null。集合显式去重排序，具有时序含义的交易日、年度和分页序列按合同顺序存储。新 Decimal 结果用无指数、无无意义尾零的十进制字符串，负零规范成 `0`；原 V6 数值字节/身份单独保留，不通过新规范化改写历史记录。哈希字段不包含自身；子对象先形成内容身份，再形成外层批次身份，避免自引用。

运行耗时、重试次数、当前机器时间和日志行不进入语义结果哈希。真实抓取时间、请求/收据和来源代际属于证据身份，必须保留。相同的已验证输入和合同产生相同结果；来源更正产生新身份，即使数值相等也不能冒用旧证明。

历史对象可用于准确的历史审计，不承诺永久代表“当前最新”。进入新的批次或后续阶段 C 时必须重新验证同根、同冻结输入及来源关系；序列化文件或旧进度本身不授予当前资格。

## 4. 财务政策投影与年度观察

### 4.1 独立投影，不放宽旧接口

现有 `select_current_verified_metric_feature_state` 所对应的指标读取逻辑只允许 `required=true` 的签名槽位；阶段 A 允许政策要求原可选槽位。新增独立政策投影，所选槽位由本模板活动政策的财务选择器导出，不能由调用者随意提供。

投影沿用原完整当前输入与真实持久化路径：

1. 核验 provider 明确发布的完整当前请求，脱离可变输入保存事实/问题快照。
2. 逐项重新验证持久化事实、来源、冻结日可见性和同根 feature/source/mapping；provider 的“完整”不能替代这些验证。
3. 以现有 V6 规则重建期望 feature bundle 身份，认证对应已存收据；不要求整份 bundle 或七维全部完整。
4. 在有效收据下按所选签名 AST 计算/核验每个政策槽位，保留该槽位自己的值、单位、期间、证据、缺失原因与时点可靠度。
5. 重读当前 provider、持久化收据和所有实际来源，确认未发生更正。

存在完整 provider 但对应收据未落库时，可以生成绑定当前输入代际的 `current_receipt_absent`；不能自行绕过收据拼出正式值。provider 没有发布完整请求、异常返回或仓库来源验证失败属于前置条件/完整性失败，不捕获异常消息伪装成该缺失状态。

不能因为其他七维指标尚未完整就丢掉可证明的政策证据；同样不能因为某条政策已否决就停止检查其他适用规则。原 optional 属性、原 history gate 和旧指标资格不修改。

### 4.2 逐年证明与数值桥接

每个财务标量记录 selector 身份、slot/公式版本与 AST 哈希、原值/单位、实际依赖 fact ID 和完整期间、会计口径、来源快照、公开/有效时点及最低时点精度。

年度观察另外记录目标 `fy_end`，按 FY2021–FY2025 顺序分别验证 ROE、利润率、利润三个序列。不得从 slot 名字、引用数量或通用 history_endpoints 推断年份齐全。一个合法 ROE 可引用目标年度利润及前后两年权益余额；检查实际 AST 叶子对应事实的期间，不要求全部事实的 period_end 都等于目标 FY。重复观察、目标年度与实际 AST 不符、不同证券/会计口径、缺少叶子或未消解事实问题均不能产生有效该项值。

周期归属来自同根已验证行业清单：清单外为 `not_applicable`，不要求额外五年周期输入；归属未解决为待补，不能按“清单外”处理。清单内必须取得三组完整五年序列和三个当期标量，再判断周期顶部。

采用版本 `v6_feature_decimal_bridge_v1`：保留 V6 财务事实/特征的原 float 计算语义，认证有限原值后以 `Decimal(str(value))` 转换；转换版本、原投影身份及转换结果共同进入政策输入身份。该桥接不恢复已经损失的原始十进制精度，不重算或改写旧财务公式。

桥接后的所有新增政策运算用局部 Decimal context：precision=50、ROUND_HALF_EVEN，不依赖调用者的全局 context；比较前不作显示舍入，不换算未签名单位，不补零或同行中位数。缺失/无效分母走有原因的待补。封闭对象中出现非有限数或与其声明单位/身份不符则说明验证失效，不能当普通有效输入。

### 9.2 封闭失败分类

| 分类 | 例子 | 处理 |
| --- | --- | --- |
| 前置条件/合同失败 | 宇宙不存在、完整 provider 未发布、未知版本、range 配置缺失/歧义、跨根/作用域、签名不符 | 终止批次；不制造普通证券待补来掩盖配置错误 |
| 完整性/选择失败 | 篡改/丢失已登记原始文件、同领先版本歧义、伪造对象、依赖替换、批次内更正 | 终止并撤销本次派生证明 |
| 已认证领域证据不足 | 当前收据未落库、实际事实/旗标/某日覆盖缺失、已记录领域冲突、合法计算的无效分母 | 对受影响规则记录 pending，保留独立已证实影响 |
| 采集操作失败 | 超时、403/429、挑战页、未完成分页 | 任务重试/熔断或终止诊断；不能成为“确认无覆盖/无价格” |

新入口使用类型化错误/缺失结果。不得捕获通用 ValueError 的文本或异常字符串猜测业务缺失；旧接口抛出的可信读取异常保持失败。待补原因区分 runtime 与 signed_policy 来源：runtime 代码固定为 applicability_unresolved、current_receipt_absent、financial_input_missing、financial_domain_conflict、unsupported_unit、invalid_denominator、visibility_unproven、state_entry_missing、calendar_coverage_missing、market_coverage_missing、market_price_missing、market_domain_conflict、market_evidence_missing；signed_policy 只接受当前规则已签名的 reason_code。保留原始诊断但不以自由文本改变行为，未知代码拒绝。

## Controller preflight rulings / actual interfaces

1. Fixture cyclic choice must occur before signing: extend only the task-owned
   PolicyRuntimeFixture constructor with cyclic=True (exact bool) to configure
   synthetic membership before update_mapping_digest/rehash/sign. Default behavior
   unchanged; noncyclic uses a secondary industry outside the signed cyclic list.
   financial_selection(security_id) derives actual membership with no free bool.
   Do not implement the original method-level cyclic=True mutation wording.
   Cost: small test-helper signature correction, no production API/rule change.
   A test-only mutate=None hook may also run before final rehash/sign to exercise
   alternate signed ASTs; never mutate a signed graph or copy a whole constructor.
2. Preserve independent current fixture.policy.current.* vs annual fixture.policy.*
   identities. Consume signed selectors/AST, not hard-coded fixture fact keys.
   Policy-only F1 facts create a genuine blocked old V6 bundle by design. Optional
   F2 projection evaluates selected slots under authenticated require_complete=False
   receipt; old history gate and required-only metric API must remain unchanged.
3. FinancialFixture auto-publishes an empty complete provider for each initial
   member. To test no complete publication, use a genuinely new unregistered
   FormalMetricCurrentInputProvider from formal_metric_batch_guard.py with a
   genuinely initialized matching repository, not the default fixture state.
4. Actual metric Context methods: load_universe(frozen_input_hash, *,scoring_registry),
   resolve_industries(universe_proof), recheck_batch(universe_proof,industry_batch).
   Proof requires require_verified, exact genuine type and same-root/frozen/IDs;
   repository lifetime must be retained (existing proofs reference it weakly).
5. Existing _require_authentic_metric_feature_repository captures legacy read
   dependencies. Add an independent installer, never weaken/copy the old metric
   gate or bypass authentication. formal_metric_batch_guard imports feature_repository;
   inspect import order before introducing eager reverse imports. If an installer
   hook adjustment is necessary, explain the concrete minimal design to root.
6. The completeness owner publishes the complete issues snapshot; inspect actual
   persisted issue API before claiming a DB-wide issue comparison not supported by
   existing storage. Maintain real issue snapshot/receipt validation and exact
   typed failure handling; no exception-text classification.
7. All four task files only; R2 separately edits formal_sources and range fixture.
   Coordinate source-stable windows for fixture tests. No free applicability flag,
   arbitrary fact IDs or public final-proof factory. No final policy scoring.

## Execution/report contract

Work only D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation, branch codex/formal-v3-implementation.
Task BASE f4ed417fe6e64e324e9c725c3b185f7a10c52221. R1/F1 accepted; do not redo them.
Use D:/Projects/AShareQiheng/.venv/Scripts/python.exe. No dependency installs.
No Git writes or subagents. Root alone stages/commits exact task whitelist after
reports. No production network/data/DB/signatures/scoring/main merge/push. Tests
use their own TemporaryDirectory only. Preserve tmpj4zv9_fq/ and all data/progress.
All file edits through apply_patch. Read full TDD skill and writing-good-tests
before edits; write real failing tests then minimal implementation. Run focused
tests while iterating and prescribed full compatibility once on final frozen code.
Report exact RED/GREEN commands, output excerpts, exit codes/counts/time, changed
files, self-review, concerns and frozen hashes to task-F2-report.md beside brief.
Return only status, short test results, concerns, report path; ask root for a real
contract/architecture ambiguity before broadening scope. Review comes from root.
