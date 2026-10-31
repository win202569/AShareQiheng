# Task R2 brief

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。

## R2：独立请求、可信传输和有来源依据的分页

**Files:** Create `ashare_pipeline/formal_range_request.py`, `ashare_pipeline/formal_range_source.py`, `tests/test_formal_range_source.py`; Modify `tests/formal_range_fixtures.py`, `ashare_pipeline/formal_sources.py`（genuine select_range 接点）、`ashare_pipeline/formal_range_contract.py`（仅增加只读 source_registry_hash）。

**Interfaces:**

- Consumes: R1 RangeBinding；原 `OfficialTransport`/来源主机安全与响应分类函数，仅复用其安全职责。
- Produces: `FormalRangeRequestV1`（规格 §5.2 全部字段）和 `RangeFetch`，均禁止外部铸造；`ParsedRangeDocumentV1.from_dict(wire)` 是无权 DTO；`.to_dict()` 返回脱离副本。
- 在本任务向 `SignedSourceRegistry` 新增 `select_range(request: FormalRangeRequestV1) -> RangeConfig`，仅接受 genuine 新请求、检索 range_configs 并核验其完整配置/根/锚点身份；不调用旧 `select`。相应 `formal_sources.py` 修改由同一 B1 负责人执行，并进入 R2 白名单。
- `FormalRangeSource(binding, *, transport, implementations)` 构造时封闭精确传输及实现注册表依赖；实现键为 `(parser_id,parser_version,mapping_version,normalizer_version,request_version)`，变化即失败。
- `first_calendar_request(as_of_utc: str) -> FormalRangeRequestV1`；本任务实现下文的纯 `backward_interval` 和 `page_successor`，不声明可接受已持久化观察的外部后续请求入口。R3 在真实收据类型可用后一次性新增后续请求方法，R2 不留抛 NotImplementedError 的桩。
- `fetch_verified(request: FormalRangeRequestV1) -> RangeFetch`；`parse_verified_snapshot(request, *, raw_bytes: bytes, manifest: dict) -> ParsedRangeDocumentV1` 重跑已登记实现，不接收已算好的政策结论。
- `formal_range_source.py` 在模块初始化时先封存已完成加载的真实 RangeBinding，再在闭包内持有请求类型、登记表与私有 mint；`formal_range_request.py` 仅兼容重导出请求类型。`formal_sources.py` 不反向依赖请求权威，select_range 由来源模块初始化时安装并捕获真实请求校验和原有真实 registry 读取方法，不提供临时弱入口、调用者注册或首次调用捕获。mint/fetch/replay 重验真实 binding/config/root；请求执行同时匹配来源实例的 manifest 根与完整 source blob。W1 在同一真实闭包增加行情工厂，不暴露任意 mint 或 self-reported root_guard 资格。
- `RangeBinding.source_registry_hash` 从已验证父记录的 source 角色哈希读取，不更改绑定 wire/hash。来源封存真实 getter，将该值保存在请求私有记录中，固定 request wire 不增字段。`select_range` 除 ENTRY/锚点外比较完整 source blob 哈希；`SignedSourceRegistry` 本身没有 manifest-root 身份，同一个完整 source blob 被多个真实根引用可以复用，但不同 source blob 不能仅凭所选 ENTRY 相同混用。请求的 manifest-root 仍由真实 binding 绑定及重验。
- 区间文档保留独立文档级 publication/precision/source_updated/effective/evidence_hash/captured/upstream_generation，并区分来源总 `record_count` 与本页 `page_record_count`；`pagination_evidence` 由实际执行的注册解析合同核对，采用 `signed_single_response_v1` 或 `source_declared_numbered_pages_v1`。抓取或公开晚于冻结时点仍可保存来源观察，不因此声称可见；date_only 未证明时明确保留空生效时间/依据，后续证据层判待补。每行时点独立，不从文档默认继承。upstream_generation 是不透明的一致性身份，不能按其字符串猜新旧。fetch manifest 保存来源版本字段，快照重跑须一致。
- 新测试 `RangeSourceFixture`：构造真实 range_graph/RangeBinding、捕获请求的 FakeTransport、已登记 JSON fixture parser；属性 `.source/.transport/.binding`，方法 `.reply(wire:dict)`、`.close()`。仅临时原始内容，不创建生产文件。

- [ ] **写失败测试。**

```python
def test_first_calendar_request_needs_no_existing_calendar(self):
    from tests.formal_range_fixtures import RangeSourceFixture
    fixture = RangeSourceFixture()
    self.addCleanup(fixture.close)
    request = fixture.source.first_calendar_request("2026-08-31T07:00:00+00:00")
    wire = request.to_dict()
    self.assertEqual(wire["end_date"], "2026-08-31")
    self.assertEqual(wire["start_date"], "2025-07-28")
    self.assertEqual(wire["page_index"], 1)
    self.assertIsNone(wire["security_id"])
    self.assertIsNone(wire["calendar_coverage_hash"])
```

增加 exact bool/int、合法 ISO 下界、冻结后 end、old/new 占位符串线、URL 重定向/挑战/403/429、分页页数/总数/范围/证券不一致、伪造后续页、复制 request、替换 normalizer 或其方法等负例。解析 wire 至少封闭绑定 request_fingerprint、source/dataset/security/exchange/start/end、版本、page_index/page_count/record_count、coverage 声明、有序 rows 及规格时点字段；不能有 effective_trade/stale_days/pool_veto。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source -v`。预期缺失新接口。
- [ ] **实现。** 使用已签名 L 从冻结自然日向前分段，不假定交易日；先完成安全模板及验证，再发请求，网络操作不占数据库事务。实现中的日期内核：

```python
from datetime import date, timedelta

def backward_interval(end_text, limit):
    if type(limit) is not int or limit <= 0:
        raise ValueError("range limit must be a positive exact integer")
    end = date.fromisoformat(end_text)
    distance = min(limit - 1, (end - date.min).days)
    return (end - timedelta(days=distance)).isoformat(), end.isoformat()

def page_successor(document, max_pages):
    page, count = document["page_index"], document["page_count"]
    if type(page) is not int or type(count) is not int:
        raise ValueError("page identity must use exact integers")
    if not 1 <= page <= count or count > max_pages:
        raise ValueError("unverified or out-of-budget pagination")
    return page + 1 if page < count else None
```

`page_successor` 只在请求身份、实际来源分页声明和 R3 收据已认证后调用；超过上限保留未完成，不能调用本函数截断。无后续合法自然日时返回有原因的采集终止，不日期下溢。单页合同只允许 page_count=page_index=1；空响应不自动满足 coverage。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source tests.test_formal_sources tests.test_formal_range_contract -v`。
- [ ] **审查并提交白名单。** 本任务六个文件，提交信息 `feat: authenticate bounded calendar range requests`。

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

## 5. 显式区间请求与签名配置

### 5.1 在 source 角色内增加版本，不增加角色

增加 `formal-source-registry-v2`，顶层字段严格为 `registry_role/schema_version/configs/range_configs`。v1 仍只接受原三个字段。v2 的 `configs` 每项继续使用原 `_CONFIG_KEYS` 和 `SourceAdapterConfig`，不追加可选范围字段；旧 `select(OfficialRequest)` 只检索 `configs`。

`range_configs` 使用独立的封闭 `formal-range-source-config-v1` 项，旧评分 wrapper 与 Context descriptor ENTRY 字节保持原格式。区间项的精确字段为：

| 字段组 | 字段与约束 |
| --- | --- |
| 版本/类型 | `schema_version` 固定上述版本；`capability=verified_market_window_v1`；`kind=calendar_range` 或 `market_range` |
| 同根锚点 | `anchor_descriptor_id` 为对应旧 calendar/market 描述符 ENTRY 哈希；`calendar_descriptor_id` 对日历为自身，对行情为其签名日历锚点 |
| 来源 | `source/dataset/endpoint_url/http_method/parser_id/parser_version/mapping_version/normalizer_version/request_version` 全部显式非空，URL/方法沿用官方来源与安全限制 |
| 作用域 | `exchange_scope` 必须为 SH/SZ/BJ 之一；`calendar_anchor_selector` 对日历为 null，对行情与政策所选交易所的已签名选择器完全一致，仅作静态锚点 |
| 请求 | `request_template` 使用 query/headers/body 的封闭安全模板；`pagination` 为 `single_response_v1` 或 `numbered_pages_v1` |
| 资源界限 | `max_pages`、`max_calendar_days_per_request` 为正整数；single_response 的 max_pages=1；这些上限不能降低 20/250 日证据要求 |
| 传输策略 | `timeout_seconds/retry_base_seconds/retry_max_attempts/challenge_cooldown_seconds` 保留旧同名字段的正数/类型约束 |

区间项的 ID 为完整规范 ENTRY 的哈希，不在 ENTRY 内重复存储自身 ID。唯一键为 `(kind, capability, anchor_descriptor_id, calendar_descriptor_id, exchange_scope)`；没有或多于一个匹配项是合同/配置失败，不是证券数据缺失。

日历区间项必须锚定同根 bootstrap trading_calendar 描述符，沿用不依赖另一份日历才能获取自身的启动边界。行情项必须锚定活动市场规则引用的 market_close 描述符，并与该规则的交易日历选择器、证券作用域和交易所闭合。区间项的 source/dataset 与其锚点相同；新的 endpoint/parser/mapping/normalizer/request 版本由区间项另行显式签名，不冒充旧单日解析版本。`calendar_anchor_selector` 不激活旧 `_resolve_calendar_binding` 路径，不能把单日日历绑定当作区间覆盖；区间读取资格由第 6 节的新证明提供。

source 独立解析只校验格式；与描述符的引用闭合由读取完整九角色图的阶段 B 加载器验证。市场规则必须同时唯一解析出行情区间项和对应日历区间项。未被活动政策引用的配置不获得执行资格。A2 的旧静态绑定仍检索旧 configs；只增加 source v2 的明确解码支持，不将新区间项混入旧选择器。

source 子项改变意味着根和所有依赖身份更新、重新签名。新版本不能复用旧哈希或签名；测试签名不能作为生产批准。v1 根仍可走原 pre-policy/阶段 A 路径，但缺区间能力时不得执行阶段 B。

### 5.2 并行类型而非改写 OfficialRequest

新增 `FormalRangeRequestV1`，字段固定为 schema_version、kind、source、dataset、security_id、exchange、as_of_utc、start_date、end_date、anchor_descriptor_id、calendar_descriptor_id、range_config_id、registry_manifest_hash、page_index、calendar_coverage_hash。schema_version=`formal-range-request-v1`；日期是闭区间 ISO 日期且 end 不晚于冻结日。日历请求 security_id=null、calendar_coverage_hash=null；行情请求证券由冻结宇宙确定，calendar_coverage_hash 必须指向真实日历区间证明。完整规范请求字节的 SHA-256 为请求指纹，每个字段都参与身份。

single_response_v1 的 page_index 固定为 1。numbered_pages_v1 首次只生成第 1 页，后续页只能根据已认证的分页元数据生成，页码满足 `1 <= page_index <= min(page_count,max_pages)`；不能由调用者自由指定。声明页数超过 max_pages 时拆分为新的合法子区间请求或记录未完成，不能截断后声称完整；页数/总数变化按领域冲突或代际变化分类处理。

新模板仅允许 `security_id/exchange/start_date/end_date/page_index`，日历模板不得使用 security_id；字符串参数沿用旧转义/HTTPS/主机白名单规则。旧模板仍只接受旧占位符，不向旧 period_or_date 内编码区间。

`select_range(request)` 只检索 range_configs。日历请求不依赖既有日历证明：采用 `backward_calendar_chunks_v1`，从冻结日作为首段 end，按签名 max_calendar_days_per_request=L 生成闭区间 `[end-(L-1)日,end]`，后段 end 为前段 start 前一天；只执行合法 ISO 日期范围内的请求。它只规定确定性自然日分段，不把自然日当交易日。行情请求才从已完成的 `VerifiedCalendarCoverageV1` 实际交易日序列生成；不接受调用者自由边界。回溯完成所需证明即停止；单请求不足则拆分，服务限制导致证据未齐则保留待补，不缩短目标窗口。

解析器输出独立的 `ParsedRangeDocumentV1`：绑定请求指纹、请求范围、证券/交易所、parser/mapping 身份、页码、页数、记录总数、覆盖声明和规范行。数字分页的页数/总数/页间一致性必须有来源依据；single_response 可由已签名解析合同明确该端点不分页，不能凭短页或空响应猜测结束。无依据的完整性声明不通过验证。

区间文档及其日期行保留 published_at_utc、published_precision、effective_at_utc、effective_time_evidence_hash 和 captured_at_utc；整份文档时点只有在来源明确适用于全部所含行时才能共享。沿用既有正式可见性规则，必须证明相关观察/日历在冻结时点可用；date_only 不能自动补成对结果有利的时分秒，抓取时间不能反向证明历史公开时间。未能证明的实际观察记录为领域待补，不用可信外观的请求 as_of 字段替代时点证据。新区间路径不调用旧单日绑定来伪造该证明。

解析结果只提供来源观察，不接受 parser 直接供应 effective_trade、stale_days、pool_veto 或 confirmed_no_price 等政策结论。normalizer 必须绑定被实际执行且注册的版本；任意调用者函数或一个自报正确版本的对象不授予资格。

### 5.3 原始快照、收据与最小持久化

区间链条使用独立的 `formal-range-task-v1`、`formal-range-snapshot-v1`、`formal-range-normalization-receipt-v1`，不改旧 OfficialRequest、单日期 task 自然键、snapshot manifest 或 ContextFact 格式。

区间任务自然键包含完整新请求指纹、根/配置身份和 refresh generation。原始收据至少绑定任务 ID/请求指纹、配置 ID、manifest/content 哈希、parser/mapping/normalizer 版本、来源/upstream generation 和生产者身份。页和子区间各有自己的任务、快照和收据，不用最后一页代表所有页面。

采用同一 StateStore 的追加式区间记录命名空间：`formal_range_task`、`formal_range_snapshot`、`formal_range_normalization_receipt`、`formal_range_attempt`。新增表的合同版本与旧表隔离；旧 V2–V6 DDL 常量和行格式不改写。表结构必须存储以上逻辑身份/规范 payload，并对请求代际和收据唯一性设约束；同自然键同代际不同字节拒绝，合法更正用新代际。实施计划负责将这些已固定逻辑记录映射到精确 DDL/迁移测试，不借此实现最终分数/发布表。

原始内容继续以内容寻址方式保存并可重验。一个 verified 状态只能在快照和收据持久化、校验成功后产生。区间记录不能由裸 INSERT 后自行声称可信，仍需 producer receipt、来源身份和原始字节检查。数据库外的原始文件同样参与批次最终重验。

### 9.2 封闭失败分类

| 分类 | 例子 | 处理 |
| --- | --- | --- |
| 前置条件/合同失败 | 宇宙不存在、完整 provider 未发布、未知版本、range 配置缺失/歧义、跨根/作用域、签名不符 | 终止批次；不制造普通证券待补来掩盖配置错误 |
| 完整性/选择失败 | 篡改/丢失已登记原始文件、同领先版本歧义、伪造对象、依赖替换、批次内更正 | 终止并撤销本次派生证明 |
| 已认证领域证据不足 | 当前收据未落库、实际事实/旗标/某日覆盖缺失、已记录领域冲突、合法计算的无效分母 | 对受影响规则记录 pending，保留独立已证实影响 |
| 采集操作失败 | 超时、403/429、挑战页、未完成分页 | 任务重试/熔断或终止诊断；不能成为“确认无覆盖/无价格” |

新入口使用类型化错误/缺失结果。不得捕获通用 ValueError 的文本或异常字符串猜测业务缺失；旧接口抛出的可信读取异常保持失败。待补原因区分 runtime 与 signed_policy 来源：runtime 代码固定为 applicability_unresolved、current_receipt_absent、financial_input_missing、financial_domain_conflict、unsupported_unit、invalid_denominator、visibility_unproven、state_entry_missing、calendar_coverage_missing、market_coverage_missing、market_price_missing、market_domain_conflict、market_evidence_missing；signed_policy 只接受当前规则已签名的 reason_code。保留原始诊断但不以自由文本改变行为，未知代码拒绝。

## Prior interfaces and execution rulings

- R1 pure format lives in formal_range_format.py; contract reexports RangeConfig
  and parse_range_entry. Genuine binding factory eagerly captures verified graph
  dependencies; no first-use mutable trust cache. Source registry captures authentic
  config constructor/type and directly rejects wrong types. Keep this boundary.
- R2 owns exactly six task files after root-approved request-authority split
  and read-only RangeBinding.source_registry_hash getter addition.
  The diagnosed context-schema/source/range-source/range-contract import cycle
  must not be solved by first-use trust or one-shot callback registration. Fix1
  supersedes pure-only request-module placement: source module owns the request
  registry/mint after eagerly capturing genuine binding authority; request module
  only reexports the type, and select_range is installed by genuine source module
  initialization. Preserve same-root/full-source/config and live binding checks.
  Test fresh-process imports and pre-first-use substitutions. No seventh file.
- implementations is a trusted constructor-time explicit registration dependency,
  keyed by the five signed versions. Capture exact registry/object and actual
  parser/normalizer methods, recheck before/after executing, reject unregistered
  callbacks and merely self-reported versions. No per-fetch caller-supplied parser.
  The existing trusted Python runtime boundary remains; test-only registration
  does not approve any production normalizer. Record the exact minimal registry
  and ParsedRangeDocument/RangeFetch wire contracts for R3/W1 handoff.
- R2 authenticates first calendar requests and transport/parser observations only.
  Receipt-driven previous_calendar_request/next_page belongs R3, market_requests
  belongs W1. Pure page_successor does not mint authority. No NotImplemented stubs.
- F2 independently owns feature_repository and policy runtime fixture. Do not
  touch its files; notify root/worker before source changes that affect fixture
  imports, then signal source-stable for cross-branch integration tests.

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
files, self-review, concerns and frozen hashes to task-R2-report.md beside brief.
Return only status, short test results, concerns, report path; ask root for a real
contract/architecture ambiguity before broadening scope. Review comes from root.
