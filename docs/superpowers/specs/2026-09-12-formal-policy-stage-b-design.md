# 正式 V3 阶段 B：政策运行证据与结果设计

日期：2026-09-12

基线：`29cf92362574945f9ca41d2c9374a56bcc9ffe90`

分支：`codex/formal-v3-implementation`

状态：用户已逐节确认范围与顺序、证据接口与一致性、政策结果与验收，并以“是”确认本书面规格；已进入独立实施计划编写，尚未实现阶段 B。文中的新类型、格式和方法均为拟实现合同，不代表当前代码已具备这些能力。

上位规格：[正式评分与发布合同](2026-09-04-formal-scoring-release-contract-design.md)、[政策合同与三阶段架构](2026-09-12-formal-policy-contract-design.md)。前者固定经济规则，后者第 7 节固定阶段 B 的可信边界；本文不修改这些规则。

## 1. 交付范围与保持不变的条件

阶段 A 已完成同根、类型明确的政策定义。阶段 B 将真实冻结输入变成可审计的政策证据与结果，按“证据先行，再执行政策”实施：

1. 独立的财务政策投影、逐年观察证明、Context 状态证据，以及新的日历区间和行情窗口证明。
2. 工厂自行枚举完整冻结宇宙，获取同根当前证据，检查批次内更正和来源失效。
3. 执行已登记周期、数值红线、布尔/枚举状态和市场流动性规则；输出待补、封顶、池禁止、独立状态与利润正常化依据。
4. 保留可恢复的采集记录和证据历史，用离线合成数据验收上述完整路径。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

## 2. 组件职责与唯一正式入口

| 组件 | 职责 | 不能代替的能力 |
| --- | --- | --- |
| `FormalPolicyRegistry` | 阶段 A 的同根已验证规则 | 不是证券运行证据 |
| 政策财务投影仓库 | 核验当前 provider、持久化收据及所选签名槽位，包含原可选槽位 | 不放宽旧指标投影和 V6 完整度 |
| 区间来源/收据仓库 | 显式区间请求、原始响应、解析、代际和任务收据 | 网络成功不等于覆盖完整 |
| 日历/行情证据工厂 | 从来源记录推导交易日序列、实际有效成交、覆盖与价格状态 | 不接收调用者的停滞天数或无价格结论 |
| 政策纯计算器 | 对已解析规则和脱离外部可变状态的输入计算判定轨迹与效果 | 纯函数结果不具正式证明资格 |
| `FormalPolicyRepository` | 冻结宇宙枚举、同根绑定、全批次取证/重验、计算和封闭发布 | 不计算最终评分、不选池 |

唯一生成正式政策结果的公共入口为：

`FormalPolicyRepository.build_batch(frozen_input_hash, *, scoring_registry, policy_registry) -> VerifiedPolicyResultBatch`

仓库初始化只接受精确且经过既有身份验证的 StateStore、feature/Context/range repositories、当前输入 provider 和同一签名验证器。依赖必须指向同一个数据库和对应原始快照存储。入口不接受证券子集、规则子集、特征键列表、自由 dict、预制政策结果或任意数值回调。

`frozen_input_hash` 是已有持久化冻结宇宙的定位键，不是其真实性证明。工厂重新读出真实冻结输入和行业分配，按证券 ID、模板与活动规则 ID 的规范顺序枚举。无冻结输入时返回明确的前置条件错误，不制造空的完整批次。缺模板或行业归属的证券保留在宇宙清单中，记录 `applicability_unresolved`，不能静默跳过或判为非周期。

取证与纯计算可拆成独立模块，但正式生成由一次批次尝试控制。`VerifiedPolicyEvidenceBatch`、每证券结果及规则判定共享未发布凭据；只有最终重验和数据库/provider 结束检查成功后才一起变为可用。没有独立的公共“把任意 evidence dict 升级为正式结果”入口。

新模块以 `formal_policy_*` 和 `formal_market_*`/`formal_range_*` 为边界；只有为签名来源 v2、区间持久化和可信读取所必需的适配才进入旧模块。实施计划须逐项列明这些接点，不做无关重构。

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

## 6. 日历区间与行情窗口值格式

### 6.1 日历覆盖证明

`VerifiedCalendarCoverageV1` 显式绑定 `formal-calendar-coverage-v1`、registry_manifest_hash、日历 descriptor/config ID、交易所、冻结日、request/parser/mapping/normalizer 版本、有序请求指纹及 snapshot/receipt 身份、upstream/refresh generation、实际请求闭区间，以及另列的 covered_start/covered_end 和其中每天的显式 is_trading_day、升序交易日列表。

covered 区间必须被真实请求区间覆盖；其中每个自然日须恰有一条来源支持的日历判定。相关请求的分页须按签名合同完整验证，不能跳过未验证页面。证明区间内缺日、重复日或无法解释的来源冲突不能形成完整覆盖；普通的区间外领域缺口不使区间内完整覆盖失效，但若其揭示整个来源/请求的完整性失败则仍终止尝试。这样可保留请求范围内已独立证明的较短区间，不强迫最近有效价之前的日历领域缺口成为当前价格的依赖。

可将具有相同根、版本和无矛盾重叠日期的相邻区间组合；组合时重新验证每个成员。日历来源若仅返回交易日列表，只有已签名且已实现的响应完整性合同能证明该请求区间内未列出的日期均非交易日，才可形成上述日历值。不能仅凭数组排序、长度、周一至周五或已有 VerifiedCalendarBinding 证明区间完整。

窗口搜索从冻结日向前，逐步取得经证明的实际交易日。冻结日必须在所属交易所日历中被证明为交易日；否则是冻结输入/日历不一致的失败，不将日期自动改为前一交易日。满窗口取包含冻结日的最近 250 个交易日，尾部否决窗口取最近 20 个。找到有效价格可只保留证明它及其后全部交易日所需的完整日历区间，不强迫继续取得更老行情。

旧 calendar binding 可以提供同根身份锚点或独立交叉核对，但不替代新区间完整性证明。新区间启动不要求先伪造旧 calendar fact。跨交易所、根、选择器或覆盖代际不能拼接。

### 6.2 每日行情证据

`verified_market_window_v1` 的每天记录包括 date、coverage 状态、来源收据引用，以及已覆盖时的 exchange_allows_trading、volume、turnover、close。permission 必须精确 bool，成交量/额为有限非负十进制值；标准化单位固定为 volume=shares、turnover=CNY、close=CNY_per_share。原始手数/金额尺度的转换必须由区间配置所签名的 mapping/normalizer 版本明确授权并已实现，不能凭字段名猜测换算。close 使用 `positive`（严格正数）或 `unavailable`（显式原因）判别。缺行/缺响应不能写为零成交行。

coverage 的封闭状态为 covered、missing、domain_conflict。传输失败属于任务诊断；可导致该日 missing，但失败消息本身不是来源事实。只有真正认证的领域问题可以产生 domain_conflict；原始快照篡改、领先版本歧义等按第 9 节直接中止。

有效成交由工厂计算：exchange_allows_trading 且 volume>0 且 turnover>0。只有真实所需操作数齐全才能把该日作为完整覆盖；不信任旧 is_effective_trade 字段。有效成交但 close 无可信正值时，价格证据待补，不能把它改成“无有效成交”，也不能退回更早价格并声称最近价格已证明。

窗口对象除第 3 节共同身份外，显式绑定 registry_manifest_hash、market/calendar descriptor ID、所用 range_config ID、request/parser/mapping/normalizer 版本、有序请求指纹与 snapshot/receipt 身份、upstream/refresh generation、实际请求范围和 required_trading_days、每日记录、日历证明哈希，以及以下两个相互独立的结果轴。

日历和行情两类对象的历史读取必须使用其精确保存的全部成员；当前批次则重新选择并核验各成员的领先身份。真实但旧的覆盖对象不能仅凭相同交易日列表或相同价格充当当前代际证据。

### 6.3 价格与停滞两个结果轴

| 价格状态 | 必须满足 | 值与限制 |
| --- | --- | --- |
| positive_close_complete | 找到窗口内最近有效成交日及实际正 close，并证明其后直到冻结日每个交易日均无有效成交 | 保存 actual_close/date 和按实际交易日推导的 stale_days；不用 preclose |
| confirmed_no_price_250 | 完整证明最近 250 个交易日均被覆盖且无有效成交 | 无 price，增加 market_evidence_missing；不生成价格依赖的最终分数 |
| incomplete | 搜索/日历/来源领域证据不齐，或有效成交日缺可信正价 | 无可供最终价格计算的 value；允许保存明确标为未完成的候选观察，不授予有效价格资格 |

窗口外旧价格不作为输入。最近有效交易在满窗口第一日时 stale_days=249，仍是窗口内价格；再早一日已在窗口外，不得把 stale=250 的价格挪进窗口。

停滞否决状态为 proven、clear、pending：最近 20 个交易日全部覆盖且无有效成交为 proven；在尾部 20 日内有已验证有效成交即可证明“连续 20 日无成交”为假；其余为 pending。价格 complete 与否不替代这个状态。有效成交日没有 close 也能反证“无有效成交”，但仍不能产生有效价格。

停滞天数只在最近有效成交日及其后连续区间已证明时给出精确值；在完整 250 日无成交时保留 `at_least=250`，不伪造精确停牌长度。stale=0 必须为冻结日真实有效成交；1–19 保留真实旧 close；20–249 可同时保留有效价格证明和已触发的双池否决。

最近 20 日已证明无成交而更老区间有缺口时，保留 proven 否决与 incomplete 价格。最近 20 日中有缺口且没有反证时不得猜否决。确认 250 日无价格同时带有已证明的 20 日否决和 market_evidence_missing。任何否决都不能消除待补。

新区间描述符是旧市场/日历选择器的能力锚点，不要求先存在一个旧正价 market_close 才能表达“确认无价格”；旧对象也不自动升级为完整窗口。阶段 B 不给停滞状态额外扣 T 分。

## 7. 证券、监管和事件证据

继续使用既有 Context repository 的签名请求、来源重验和当前版本选择，不开放“按任意行 ID 取值”的旁路。每个状态输入保存精确 descriptor、请求证券/作用域、entry ID、原值、时点、来源与收据。

- security_state 使用真实 bool/枚举字段；suspended 自身不是新增硬否决。
- regulatory_state 只读已授权 flag_id，必须取得显式值并与规则的 expected 比较；不能把缺旗标当 false。缺旗标/缺响应/未覆盖的审计代码为待补。
- event_calendar 只读已授权 event_id 和可验证日期/单位的量化记录；不把缺少事件条目推成“无风险事件”。非量化事件经已签名监管/状态旗标表达，不填 quantified_value=0。
- 若所需生产状态无法被现有版本可靠表达，保持待补，不临时添加自由文本判断。未来新增事件值格式需另行版本化，不在本阶段扩成任意事件表达式引擎。

已确认的硬否决语义全部覆盖：ST、*ST、退市整理、强制退市风险、治理红灯、权益/净资产非正、保留/否定/无法表示意见、20 日无有效成交。治理橙灯、拥挤、重大解禁、减持、重大事件、周期顶部继续是独立状态；按显式签名结果限制相应池，软件不自行决定严重度。

## 8. 政策执行和结果结构

### 8.1 规则判定

每个模板活动规则恰有一条 `PolicyDecision`：rule_id、role、semantic_id、template_id、security_id、definition_hash、input/evidence 引用、实际操作数/阈值/算法版本、evaluation_state、proven_effects、pending_requirements、trace。没有模板时证券结果记录适用性待补而不伪造五套模板判定。

evaluation_state 只有 matched、clear、not_applicable、pending_evidence。clear 表示本条有足够证据证明未命中，不表示公司整体安全。not_applicable 需要已验证适用性依据，不以输入缺失替代。

规则执行顺序不影响结果，具体行为为：

| 规则族 | 执行 |
| --- | --- |
| numeric_redline | 对真实标量执行签名 lt/lte/gt/gte/eq 与同单位阈值；非正权益固定 lte/0 |
| boolean_state / enum_state | 精确类型匹配显式 expected/values；缺失不能作 false |
| cyclic_protection | 清单内且完整证据下，当前 ROE 与利润率分别 >= 自身五年 80 分位才命中；二者必须同时满足 |
| market_liquidity | 分别消费价格轴和 20 日否决轴，不以价格缺失推出无成交 |

周期 quantile_method 只能使用规则显式登记的 linear_type7_v1 或 nearest_rank_v1：五值升序，前者 h=(n-1)*0.8 并线性插值，后者取一基 ceil(n*0.8)；五年利润中位数取排序第三个。命中时正常化利润=min(当期利润,五年利润中位数)，记录 G/M 各 80 分上限、cyclic_top 状态和已签名池限制。未命中保留判定轨迹，不输出利润替换或封顶。不存在默认生产分位数算法。

一般规则缺少必需操作数时不得执行未证明的 on_match 效果。市场规则是明确的双轴组合：价格或否决轴待补时整体判定为 pending_evidence，仍可保留独立 20 日证明允许的 pool_prohibition；不能把其他依赖整体匹配的附加效果一起放行。两个轴齐全时，按 20 日否决谓词判为 matched 或 clear，并只产生已签名的相应效果。

某条已命中规则的 on_match 本身可要求 pending_evidence；此时 matched 与待补要求可以同时存在。证券证据完整度检查所有 pending_requirements，而不是只看 evaluation_state。

### 8.2 聚合与输出权限

`PolicyResult` 包含：所有规则判定、同维最严 cap、strong/wait 禁止集合、带所有理由的独立状态、完整利润正常化依据、待补清单和证券级证据状态。多个 cap 取最小上限，池禁止取并集，重复效果可合并显示但其全部规则/证据来源必须保留。待补不能被已知否决、去重或早返回移除。

`VerifiedPolicyResultBatch` 包含完整冻结证券清单、各证券结果和真实 evidence batch；允许其中有待补证券。完整枚举/完整性验证成功与每证券证据齐全是两个概念。计数等审计摘要从结果导出，不接受人工输入“ready/eligible”覆盖字段。

正常化依据保存原利润、五年值及年度证据、median、实际取低结果和签名 V 依赖清单。这里不执行适配器、不替换既有 V 分位数、不应用最终维度上限、不重算 C/Sc/B/R。阶段 C 必须在全冻结宇宙重建受影响指标的完整同行样本，包含非周期同行；不能拿本阶段结果给旧分数改名。

## 9. 批次一致性、失败分类与恢复

### 9.1 批次生命周期

1. 区间采集与收据落库在评分读取之外完成；不在跨证券数据库事务内发网络请求。
2. 捕获受信任 provider 的发布代际和同一数据库观察连接的 data_version，读真实宇宙、行业和同根合同。
3. 对每证券取得财务/Context/市场证据及其显式缺失标记，离线计算全部规则，准备未发布对象。
4. 在首轮完成后重读每个实际当前输入、缺失状态、日历/行情成员及所有原始来源；对缺失变出现、数值更正、版本冲突同样敏感。
5. 沿用短暂 writer exclusion 与 provider 锁的最终校验模式，不在昂贵取证期间持有写锁。最终校验负责调用依赖、根身份、provider/数据库代际和原始文件成员；成功后才释放整批证明。
6. 包括最终回滚/关闭失败在内的任何异常均撤销未完成批次及其派生对象。部分已算完的证券只能留作诊断，不能外泄成已正式验证的结果。

原始文件不受 SQLite 锁保护，因此不能只检查 data_version；必须通过来源仓库重验实际内容/manifest 和身份。成功快照证明其构建时点的读取事实，不声称永远没有后续版本；新的消费尝试再次检查当前关系。

### 9.2 封闭失败分类

| 分类 | 例子 | 处理 |
| --- | --- | --- |
| 前置条件/合同失败 | 宇宙不存在、完整 provider 未发布、未知版本、range 配置缺失/歧义、跨根/作用域、签名不符 | 终止批次；不制造普通证券待补来掩盖配置错误 |
| 完整性/选择失败 | 篡改/丢失已登记原始文件、同领先版本歧义、伪造对象、依赖替换、批次内更正 | 终止并撤销本次派生证明 |
| 已认证领域证据不足 | 当前收据未落库、实际事实/旗标/某日覆盖缺失、已记录领域冲突、合法计算的无效分母 | 对受影响规则记录 pending，保留独立已证实影响 |
| 采集操作失败 | 超时、403/429、挑战页、未完成分页 | 任务重试/熔断或终止诊断；不能成为“确认无覆盖/无价格” |

新入口使用类型化错误/缺失结果。不得捕获通用 ValueError 的文本或异常字符串猜测业务缺失；旧接口抛出的可信读取异常保持失败。待补原因区分 runtime 与 signed_policy 来源：runtime 代码固定为 applicability_unresolved、current_receipt_absent、financial_input_missing、financial_domain_conflict、unsupported_unit、invalid_denominator、visibility_unproven、state_entry_missing、calendar_coverage_missing、market_coverage_missing、market_price_missing、market_domain_conflict、market_evidence_missing；signed_policy 只接受当前规则已签名的 reason_code。保留原始诊断但不以自由文本改变行为，未知代码拒绝。

### 9.3 增量恢复与数据保留

区间任务沿用 pending、leased、verified、retryable_failed、terminal_failed、superseded 的状态语义和有限退避/租约检查。只重取未完成、缺失或实际已变化的请求；同请求/同代际且原始收据仍真实的已验证数据不重复抓取。单证券/来源失败不妨碍其他独立采集任务推进；跨证券政策批次仍须保持一致，不能把不同尝试拼成一个批次。

保存实际请求、尝试、失败码、收据和完成进度；不删除或覆盖旧快照。重启可复用通过重验的原始字节，必须重新认证和组装完整冻结批次。游标和完成勾选仅用于工作调度，不证明当前有效性。语义内容相同但无证据代际变化时重算结果确定；有来源更正时新身份与旧历史共存。

## 10. 离线验收标准

以下是未来测试要求，本文不声称这些测试已经执行或通过。使用真实字节敏感签名的合成注册图、临时数据库和原始响应 fixture；不访问生产库或真实网络。

| 领域 | 必须覆盖 |
| --- | --- |
| 范围 | 五模板全部必需语义；完整宇宙枚举；无模板/行业待补；非周期不取五年序列；不按入池/七维完整过滤 |
| 财务 | optional 仅供政策，不放宽旧指标入口；收据缺失与 provider 未完整发布区分；逐年/错年/重复/缺叶子；合法期初期末余额；source/unit/formula/会计口径与冻结时点 |
| 数值 | Decimal 桥接保留原值身份；环境 context 不影响结果；1..5 的两种 80 分位分别为 4.2/4；门槛恰等于也命中；两个当期指标必须同时达标；median/minimum、允许的负值/零、非有限拒绝和显示舍入前比较 |
| 区间签名 | v1/v2 严格字段；旧 select 不见 range_configs；锚点/来源/交易所闭合；无配置、重复项、错根和自报解析器拒绝；新参数不能经旧模板通道使用；date_only/冻结后更正与有效时点证据，不以 capture/as_of 冒充公开时点 |
| 日历 | 节假日与真实交易日；自然日区间完整性及证明子区间与请求区间的区别；不能用稀疏日期数组冒充完整；bootstrap 无循环；错交易所、分页缺漏和重叠矛盾 |
| 行情 | stale=0/1/19/20/249/250；真实 close，不用 preclose；有效成交缺价格不变无成交；旧正价格式不接受 null；旧单条记录不冒充窗口 |
| 覆盖 | 最近有效价之后任一缺日都不 complete；已证明有效价之前不强求继续回溯；确认无价必须完整 250 日；20 日证明与更老缺口并存；20 日内缺口无反证时不猜否决 |
| 分页/收据 | single_response 页码只许 1；后续页必须由已验证元数据生成且不超上限；缺页、重复/冲突日期、错证券/区间、总数不一致、错误结束声明、多快照成员替换；只验最后一页必须失败 |
| 状态 | 显式 false 与缺旗标区分；未知审计代码待补；未量化事件不填零；suspended 不自行变新硬否决；独立状态保留签名池范围 |
| 聚合 | 多上限取严、多禁池取并集；全部 trace 保留；matched 自带 pending；已否决仍收集其他待补；market 部分证明不放行其他未证实效果 |
| 信任 | 复制/伪造/普通方法影子；跨根/证券/模板/冻结/批次混用；同领先版本冲突；前后更正；数据库/provider/原始文件变化；finalize/close 失败无有效后代 |
| 兼容/恢复 | 旧 DDL/描述符/单日请求/快照/V6 算术/pre-policy 行为不变；重复请求不重复爬；未变输入重组规范字节一致；更正新身份；历史对象不冒充当前；中断后保留数据 |

测试按来源合同、财务投影、市场证明、纯规则、批次集成分层。单元测试使用最小样本；完整批次集成保留必要的跨证券/跨交易所用例，不为每个类型错误重复构建昂贵全市场样本。最终回归覆盖所有实际受影响的旧合同与纯代码/测试范围，不用测试夹具替代生产批准。

## 11. 实施边界与书面复核

采用证据先行方案，是因为现有 required-only 投影、单日请求和正价 Context 都不能直接承载新的证据语义。对比先打通单一行情纵向流程或一次联调整个 B，该方案允许财务和区间证据在共同身份合同确定后独立开发，再统一验证政策结果。

实施顺序为：共同身份/签名区间合同与追加式收据；财务投影和日历/市场证据独立实施；状态读取与纯政策结果；全冻结批次、失败撤销与恢复；兼容和集成验收。子代理仅在边界明确的独立任务上并行，共享 schema 和仓库写入由明确负责人串行协调。

书面自检项目：版本与锚点闭合、日历与价格双轴、数值桥接不改 V6、pending 与完整性失败区分、所有效果有证据、历史与当前区分、无自引用哈希、无阶段 C/生产执行越界。

用户复核本文后才进入 writing-plans 编写独立实施计划。本文批准软件结构和以上执行边界，不选择生产分位数算法、不批准任何真实字段/来源映射或额外经济阈值，不授权生产签名、实爬、main 合并、推送或发布。
