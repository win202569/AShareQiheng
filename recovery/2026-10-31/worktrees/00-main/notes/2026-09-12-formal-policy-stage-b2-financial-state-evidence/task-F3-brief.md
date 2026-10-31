# Task F3 brief

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。

## F3：证券、监管与事件的显式状态证据

**Files:** Create `ashare_pipeline/formal_policy_state.py`, `tests/test_formal_policy_state.py`; Modify `tests/formal_policy_runtime_fixtures.py`, `ashare_pipeline/formal_policy_values.py`, `tests/test_formal_policy_values.py`, `ashare_pipeline/formal_policy_registry.py`（封闭 event_record DTO 及原始模块私有身份/校验读取权威；不改签名规则合同）。

**Interfaces:**

- Consumes: `FormalContextRepository.get_verified_many(kind, scope_key, security_ids, as_of_utc, registry_manifest_hash)`、genuine FormalPolicyRegistry。
- 仓库及值校验的权威须由其原始模块初始化时建立：policy registry 私有 reader 绑定原 proof_record 与规范字节；PolicyValue 私有 operations 绑定原 parser/serializer/type/依赖检查。state 在首次导入时不信任可替换的公共类或方法别名，不以相同 wire 授权；沿用受信任私有实现边界，不声称防御任意解释器/私有 helper 替换。不得以此修改 v1 签名规则。
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

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state tests.test_formal_policy_values tests.test_formal_policy_registry tests.test_formal_context_schema tests.test_formal_context_repository -v`。
- [ ] **审查并提交白名单。** 本任务六个文件；提交信息 `feat: preserve explicit policy state coverage and missing entries`。

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

## 7. 证券、监管和事件证据

继续使用既有 Context repository 的签名请求、来源重验和当前版本选择，不开放“按任意行 ID 取值”的旁路。每个状态输入保存精确 descriptor、请求证券/作用域、entry ID、原值、时点、来源与收据。

- security_state 使用真实 bool/枚举字段；suspended 自身不是新增硬否决。
- regulatory_state 只读已授权 flag_id，必须取得显式值并与规则的 expected 比较；不能把缺旗标当 false。缺旗标/缺响应/未覆盖的审计代码为待补。
- event_calendar 只读已授权 event_id 和可验证日期/单位的量化记录；不把缺少事件条目推成“无风险事件”。非量化事件经已签名监管/状态旗标表达，不填 quantified_value=0。
- 若所需生产状态无法被现有版本可靠表达，保持待补，不临时添加自由文本判断。未来新增事件值格式需另行版本化，不在本阶段扩成任意事件表达式引擎。

已确认的硬否决语义全部覆盖：ST、*ST、退市整理、强制退市风险、治理红灯、权益/净资产非正、保留/否定/无法表示意见、20 日无有效成交。治理橙灯、拥挤、重大解禁、减持、重大事件、周期顶部继续是独立状态；按显式签名结果限制相应池，软件不自行决定严重度。

### 9.2 封闭失败分类

| 分类 | 例子 | 处理 |
| --- | --- | --- |
| 前置条件/合同失败 | 宇宙不存在、完整 provider 未发布、未知版本、range 配置缺失/歧义、跨根/作用域、签名不符 | 终止批次；不制造普通证券待补来掩盖配置错误 |
| 完整性/选择失败 | 篡改/丢失已登记原始文件、同领先版本歧义、伪造对象、依赖替换、批次内更正 | 终止并撤销本次派生证明 |
| 已认证领域证据不足 | 当前收据未落库、实际事实/旗标/某日覆盖缺失、已记录领域冲突、合法计算的无效分母 | 对受影响规则记录 pending，保留独立已证实影响 |
| 采集操作失败 | 超时、403/429、挑战页、未完成分页 | 任务重试/熔断或终止诊断；不能成为“确认无覆盖/无价格” |

新入口使用类型化错误/缺失结果。不得捕获通用 ValueError 的文本或异常字符串猜测业务缺失；旧接口抛出的可信读取异常保持失败。待补原因区分 runtime 与 signed_policy 来源：runtime 代码固定为 applicability_unresolved、current_receipt_absent、financial_input_missing、financial_domain_conflict、unsupported_unit、invalid_denominator、visibility_unproven、state_entry_missing、calendar_coverage_missing、market_coverage_missing、market_price_missing、market_domain_conflict、market_evidence_missing；signed_policy 只接受当前规则已签名的 reason_code。保留原始诊断但不以自由文本改变行为，未知代码拒绝。

## Prior interface cautions

F2 reviewed selector/runtime fixture handoff is accepted; use the genuine helper API and
retained dependency requirements below. The actual regulatory flag field is
active, not value. Constructor-only synthetic cyclic membership is set before graph
signing; state selection has no boolean applicability shortcut. Pure PolicyValue DTOs
must not receive lineage extras; keep source refs/request identity in selection lineage.


## Execution/report contract

Task BASE c7fb672bfe47d2831bb4c1e850d6397407b9464b. Prerequisites R1/R2/F1/F2 accepted with clean reviews and stable 213-case combined coverage.
Work only D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation on codex/formal-v3-implementation.
Use D:/Projects/AShareQiheng/.venv/Scripts/python.exe. No dependency install, production
network/data/DB/signature/scoring, main merge or push. No Git writes or subagents.
Root stages exact task paths only after report; preserve tmpj4zv9_fq/ and all data/progress.
All file edits via apply_patch. Read complete TDD skill and writing-good-tests before
implementation. Observe real RED, implement minimally, focus tests while iterating,
then run prescribed compatibility on frozen files. Ask root about concrete contract
ambiguities/import cycles before widening the file list. Do not introduce first-use
public alias trust or one-shot callback registration that can be hijacked.
Write full report beside this brief as task-F3-report.md: exact RED/GREEN commands,
outputs, exit codes, counts, elapsed times, changed paths, frozen hashes, self-review,
actual API handoff and concerns. Return short status only. Independent review is root's job.


## Accepted predecessor handoff and concurrency
F2 fix1 at 1687440 has clean review and full 34-case financial/18-case values
coverage within root's 182-case joint GREEN. PolicyRuntimeFixture constructor is
(*,cyclic=True,mutate=None, plus existing fixture arguments); cyclic exact bool
and mutate are test-only pre-sign configuration. Actual constructor signatures
must be inspected before use. Default mapping is a genuine synthetic signed
financial-v1 schema, never a production fixture-v1 special case.
financial_selection(security_id) derives true industry applicability. Helpers
and aliases do not confer proof; preserve original provider/receipt/Context
identity and old behavior. Actual regulatory field is active. Actual event fields
are event_id,event_date,quantified_value,unit; selector type is event_record.
Only the event_record closed non-authoritative value branch is activated here;
calendar_record/market_window still reject present values until W1. Keep raw
Context lineage and signed date/unit semantics; no zero substitution for missing
or unquantified events. Existing test that rejects every compound must be adjusted
only for newly supported event records and strengthened for malformed records.

Exact six-file whitelist: ashare_pipeline/formal_policy_state.py,
ashare_pipeline/formal_policy_values.py,tests/test_formal_policy_state.py,
tests/test_formal_policy_values.py,tests/formal_policy_runtime_fixtures.py,
ashare_pipeline/formal_policy_registry.py (owner-authentic private reader only).
No feature_repository/metric/evaluator/legacy Context production edits. If a real
API gap prevents using the genuine current Context boundary, ask root with exact
evidence before adding an API. R3 concurrently owns StateStore/V7 and range
source/fixtures only. Coordinate source/schema-stable test windows via root;
never fix those imports or change other workers' files. All test data lives only
in each fixture's temporary directory. No production collection or score/pool run.
