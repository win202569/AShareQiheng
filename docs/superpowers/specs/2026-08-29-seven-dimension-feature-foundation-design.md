# 七维特征基础层与120只候选深抓设计

日期：2026-08-29

状态：书面设计，等待用户审阅
对应总规范：[SCORING_SPEC_V2.md](../../../SCORING_SPEC_V2.md)

## 1. 目标与边界

本阶段建设正式七维评分之前的可审计基础层：消费现有120个 `deep_financial` 作业，逐只保存完整历史三表，把原始字段转换为版本化财务事实，并为每只候选生成统一的七维特征包。特征包必须明确区分“已有输入、缺失输入、不适用、被阻断”，且每个值都能回溯到原始快照。

本阶段的“覆盖120只”是指当前候选集合中的每只证券都出现在深抓进度和特征状态中，不是指120只都会得到完整七维分。银行、保险、券商、地产、周期等模板缺少专用数据时必须保持 `partial` 或 `blocked`，不能套用普通工业模板。

当前120只来自60个源行业、每个行业2只，只适合验证字段和模板覆盖，不足以建立正式行业百分位基线。后续正式评分必须使用更大的行业校准面板。

本阶段不做以下事项：

- 不生成七维模块分、原始总分 `S0`、置信调整分 `Sc` 或股票池。
- 不打开 `finalize` 的正式评分闸门。
- 不把120只开发验证切片表述为全市场评估结果。
- 不抓取半年报PDF正文，不判断治理、重大事件、ESG重大性和审计意见。
- 不实现一致预期、估值、买点、分红回购、融资并购等后续数据源。

后续子项目依次为：行业模板与正式七维计算、市场及资本配置数据、公告正文与治理事件、全市场扩展、8月31日行情锚定和最终股票池。本设计只规定这些模块要消费的稳定接口，不提前实现它们。

## 2. 当前断点

现有管线已经有内容寻址快照、SQLite作业状态机、预筛候选和正式发布闸门，但缺少深抓执行路径：

- 120个 `deep_financial` 作业全部处于 `pending`，没有worker租赁和消费它们。
- 候选三表覆盖为0/120；现有三表样本只有不在候选集合中的浦发银行试采数据。
- `AKShareSource.fetch_financial_statements()` 一次顺序调用三张表，后一次失败会使前面成功结果来不及持久化。
- 当前正式覆盖率只读取预筛记录中不存在的 `formal_features`，所以恒为0。
- 快照读取逻辑若只按数据集取“最新”，逐股深抓后可能误取另一只股票的快照。
- 当前深抓幂等键只含业绩报表行哈希，无法感知三表修订、映射版本或候选集合变化。

五指标预筛继续保留在 `scoring.py`，只负责选择深抓对象。正式特征和未来正式评分放在新模块中，避免代理分与正式分再次混用。

## 3. 核心设计决策

### 3.1 采用“原始快照 → 标准财务事实 → 特征包”三层模型

原始快照不可修改；标准财务事实负责期间、单位、字段映射和公告时点；特征包只引用事实并记录公式。任何映射或公式变化都生成新版本，不覆盖旧结果。

### 3.2 历史窗口至少包含七个期间

每次三表调用保存源返回的完整历史记录。构建2026中报特征时至少选择：

- FY2021、FY2022、FY2023、FY2024、FY2025；
- 2025H1、2026H1。

FY2021—FY2025满足商业质量和盈利质量的五年窗口；2025H1是2026H1同比基期；成长模块的长期口径使用FY2022—FY2025。缺少任一期间不会触发补0，而是降低相应输入覆盖并给出缺失原因。

### 3.3 严格按公告时点选择版本

所有原始版本都保留。特征构建只可选择 `effective_at_utc <= as_of_utc` 的事实；同一事实存在多个合格版本时，依次按公告时点、源更新时间、抓取时间、内容哈希选择最新版本，排序必须与输入顺序无关。

若源只给公告日期，不假设盘中可交易：公告时间按当日23:59:59 Asia/Shanghai记录；生效时点为公告日期之后第一个A股交易日15:00 Asia/Shanghai。这样8月31日盘后披露的报告可以计入披露覆盖，但不能使用8月31日收盘价形成无前视偏差的可交易正式池。该证券最早在下一交易日收盘后具备评分生效资格。

### 3.4 缺失值失败关闭

- 原始字段缺失时不写 `financial_fact` 行。
- 特征缺失时写入 `value=null`、状态 `missing` 和机器可读原因。
- 数值0必须保留；布尔值、NaN和Infinity不得被转换成数值。
- 整个维度的必要输入不齐时，未来评分不得重分配该维权重。
- 本阶段的财务覆盖率不得复用为正式置信度 `C`。

### 3.5 网络抓取与特征重建解耦

深抓worker负责逐表抓取和即时持久化；事实及特征构建只读取已验签快照。映射或特征契约升级时可离线重建，不需要重新请求远端。

## 4. 模块边界

### `feature_contract.py`

定义并验证 `EvidenceRef`、`FeatureValue`、`FeatureBundle`。负责：

- 字段类型、枚举、0—1覆盖率和七维键集合校验；
- 确定性JSON序列化及内容哈希；
- 缺失值、证据引用和状态一致性；
- 明确 `is_formal_score_ready=false`，防止基础特征包冒充正式评分。

### `financial_schema.py`

保存版本化的源字段到规范财务事实映射、期间分类和单位规则。第一版映射标识固定为 `eastmoney-financial-mapping-v1`，不得把映射散落在worker或评分代码中。

### `financial_features.py`

纯函数模块，负责：

- 从验签后的三表记录中选择截至时点可见的报告版本；
- 生成标准 `FinancialFact`；
- 计算不依赖行业排名或市场行情的派生输入；
- 生成七维特征包及缺失原因。

该模块不访问网络、不直接操作SQLite，便于用固定夹具进行回放测试。

### `deep_worker.py`

负责把现有 `deep_financial` 组合任务展开为360个 `deep_statement` 子任务，并消费子任务：

1. 每只证券分别建立资产负债表、利润表、现金流量表子任务；
2. 子任务精确查找并验签相同证券、相同请求的可复用快照；
3. 需要刷新且允许联网时，一个子任务只请求一张表；
4. 成功后立即写入快照、`source_snapshot` 和对应标准财务事实；
5. 每次子任务状态变化都触发一次幂等 `feature_build`，使用当时已有的三表生成partial或financial-ready特征包；
6. 完成、重试或终止子任务，并返回有界结果摘要。

远程请求不包含在数据库事务中。单张表失败不会回滚已成功保存的其他表。每个远程子任务使用900秒租约；执行期间worker每60秒续租一次，进程崩溃后仍由现有过期租约恢复机制接管。

### `state_store.py`

数据库从schema v2增量升级至v3，增加迁移账本、财务事实和特征包存储方法。现有run、job、snapshot、score run和score item数据原样保留。

### `snapshot_repository.py`

提供按 `source + dataset + request_fingerprint` 的精确查询，以及公开的读取验签接口。新代码不得依赖 `orchestrator.py` 的私有快照查询函数，也不得只按数据集取全局最新快照。

### `orchestrator.py` 和 `sources.py`

- `sources.py` 新增单表接口；原三表包装函数保留兼容。
- `orchestrator.py` 增加有界 `deep` 命令并汇总特征进度；普通 `incremental` 仍只做轻量批次与入队，不同步执行360次远程请求。

## 5. 数据契约

### 5.1 标准财务事实

`FinancialFact` 包含以下字段：

| 字段 | 约束 |
|---|---|
| `id` | 规范内容SHA-256，主键 |
| `security_id` | `SH600000`/`SZ000001`格式 |
| `statement` | `income`、`balance`、`cash_flow` |
| `metric_key` | 版本化规范指标名 |
| `period_start`/`period_end` | ISO日期；时点项目的start为空 |
| `period_kind` | `FY` 或 `H1`；其他期间可保存但本阶段不参与特征 |
| `value` | 有限浮点数；缺失事实不建行 |
| `unit` | `CNY`、`shares`、`ratio`、`CNY_per_share` |
| `nature` | `instant` 或 `duration` |
| `announced_at_utc` | 源公告时点，UTC |
| `effective_at_utc` | 至少滞后一交易日后的生效时点，UTC |
| `source_updated_at_utc` | 源更新时间；缺失时为空 |
| `source_snapshot_id` | 外键指向现有 `source_snapshot` |
| `source_field` | 原始字段名 |
| `raw_row_hash` | 原始报告行的规范哈希 |
| `mapping_version` | 固定为所用映射版本 |
| `created_at` | UTC |

`id` 的哈希输入包含除 `id` 和 `created_at` 外的全部事实字段，因此相同事实离线重建仍得到相同主键。

初始公共事实目录至少包含：

- 利润表：营业收入、营业成本、营业利润、利润总额、所得税、净利润、归母净利润、法定扣非归母净利润、利息费用、研发费用；
- 资产负债表：货币资金、总资产、总负债、归母权益、总权益、短期借款、一年内到期债务、长期借款、应付债券、租赁负债、应收票据及账款、合同资产、存货、应付票据及账款、合同负债、股本、商誉；
- 现金流量表：经营现金流、资本开支现金流、现金分红、利息支付、并购支付、资产处置回款、股权融资流入、债务融资流入、偿债流出、回购支付。

源未提供某项时保持缺失。银行等金融模板可以增加专用事实键，但不得把金融字段硬映射成工业企业概念。

### 5.2 派生财务输入

本阶段只计算会计定义明确且不依赖横截面排名的数据：

- 毛利润 = 营业收入 − 营业成本；
- EBIT = 利润总额 + 利息费用；
- 实际税率 = 所得税 / 利润总额，仅在利润总额大于0时计算，并限制在0—50%；否则缺失；
- NOPAT = EBIT × (1 − 实际税率)，任一输入缺失则缺失；
- FCF = 经营现金流 − 资本开支现金流；
- 有息债务 = 短期借款 + 一年内到期债务 + 长期借款 + 应付债券 + 租赁负债；
- 净债务 = 有息债务 − 货币资金；
- 投入资本 = 总权益 + 有息债务 − 货币资金；
- 经营营运资本 = 应收票据及账款 + 合同资产 + 存货 − 应付票据及账款 − 合同负债；
- 总应计项 = (净利润 − 经营现金流) / 平均总资产；
- ROIC = NOPAT / 平均投入资本；
- 毛利率 = 毛利润 / 营业收入；
- 对称增长率 = `200 × (本期 − 上期) / (|本期| + |上期|)`；两期均为0时缺失；
- CAGR仅在起点和终点均大于0时计算，否则保留序列并将CAGR标为缺失。

平均值使用期初与期末简单平均。除实际税率的明确边界外，本阶段不winsorize、不填行业中位数、不使用默认税率。

规范化后执行两项基础勾稽：

- 资产负债表满足 `|总资产 − 总负债 − 总权益| <= max(1000 CNY, 0.1% × |总资产|)`；
- 同一证券、期间和指标的单位、币种、期间属性必须一致。

超过资产负债容差或出现单位冲突时写入 `quality_issue`，相关特征包状态为 `blocked`。单纯因四舍五入落在容差内只记录通过证据。

### 5.3 七维特征包

模板注册表第一版包含 `bank`、`insurance`、`broker`、`real_estate_high_leverage`、`resource_cycle`、`utility`、`rd_growth`、`general_nonfinancial` 和 `unclassified`。源行业名称只能通过版本化的精确映射进入前八类；没有明确映射时必须进入 `unclassified` 并阻断模板特征，不能默认回退到普通工业模板。当前候选出现的全部源行业名称必须在注册表中显式列出，允许其目标值为 `unclassified`。

每个 `FeatureBundle` 必须包含：

```json
{
  "schema_version": 1,
  "contract_version": "feature-contract-v1",
  "security_id": "SH688331",
  "report_period": "2026-06-30",
  "as_of_utc": "2026-08-29T16:00:00+00:00",
  "candidate_set_hash": "<sha256>",
  "industry": {
    "source": "eastmoney-provisional",
    "code": null,
    "name": "<source value>",
    "template_id": "general_nonfinancial",
    "template_version": "template-registry-v1",
    "formal_industry_ready": false
  },
  "input_hash": "<sha256>",
  "financial_status": "partial",
  "financial_coverage": 0.0,
  "confidence_inputs": {
    "data_completeness_ratio": 0.0,
    "date_precision_counts": {"timestamp": 0, "date_only": 0},
    "history_years_present": 0,
    "mapping_consistent": false,
    "formal_confidence": null
  },
  "dimension_inputs": {
    "G": {"status": "partial", "values": []},
    "V": {"status": "missing", "values": []},
    "M": {"status": "partial", "values": []},
    "EQ": {"status": "partial", "values": []},
    "FS": {"status": "partial", "values": []},
    "CA": {"status": "partial", "values": []},
    "T": {"status": "missing", "values": []}
  },
  "blockers": ["formal_industry_mapping_missing"],
  "is_formal_score_ready": false
}
```

`dimension_inputs` 必须且只能包含 `G/V/M/EQ/FS/CA/T`。每个 `FeatureValue` 包含 `key`、`value`、`unit`、`period_key`、`status`、`formula_version`、`evidence` 和 `missing_reason`。

维度输入状态取值为 `input_ready`、`partial`、`missing`、`not_applicable`、`blocked`。`input_ready` 只表示本阶段注册表规定的财务输入齐全，不表示该维已经具备行业标准化、市场数据或正式模块分。

`confidence_inputs` 只保存可观察的完整度、时间精度、历史长度和映射一致性证据。本阶段不定义它们到正式 `C` 的数值映射，所以 `formal_confidence` 固定为null；后续评分规格确定映射后才能生成0.60—1.00的正式置信度。

`financial_coverage` 定义为模板注册表中适用于该证券的财务输入槽位中，状态为 `observed` 或 `derived` 的数量除以全部适用槽位数量。`not_applicable` 不进入分子或分母；`missing` 和 `blocked` 只进入分母。该覆盖率只评价本阶段财务输入，不代表正式七维覆盖。

`feature_set.status=financial_ready` 仅当七个要求期间齐全、所有适用财务输入槽位均为observed/derived、模板不是unclassified且不存在勾稽或版本冲突；存在有效输入但条件未全满足时为partial；模板未分类、勾稽失败或事实冲突时为blocked。若模板没有任何适用槽位，覆盖率固定为0并设blocked，避免零分母。

`FeatureValue.status` 取值：

- `observed`：直接映射自一个财务事实；
- `derived`：由有证据的事实按已版本化公式计算；
- `missing`：必要输入缺失；
- `not_applicable`：模板明确不适用；
- `blocked`：存在口径冲突、无效期间或无法消除的多版本冲突。

证据引用至少包含 `financial_fact_id`、`source_snapshot_id`、`source_field`、`raw_row_hash`、`announced_at_utc` 和 `effective_at_utc`。后续PDF证据可扩展同一证据对象，不修改现有字段语义。

### 5.4 内容哈希

候选集合哈希定义为以下规范JSON的SHA-256：

- 预筛文档的输入哈希；
- 按 `security_id` 排序的120个 `(security_id, performance_input_hash)`。

特征输入哈希定义为以下规范JSON的SHA-256：

- 证券、报告期、`as_of_utc`、候选集合哈希；
- 三表各自按请求精确匹配的快照payload hash，缺失表写明确的null标记；
- 交易日历快照hash；
- 特征契约、字段映射和模板注册版本。

列表和对象键必须排序，JSON禁止NaN。相同输入必须得到相同哈希和相同特征包；任一源快照或版本变化必须生成新哈希，旧包保留。

## 6. SQLite schema v3

初始化过程增加 `schema_migration(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)`。对于没有迁移账本但符合现有v2结构的数据库，先在事务中登记v2，再应用v3；重复调用 `initialize()` 必须幂等。

新增三张表：

### `financial_fact`

保存5.1中的字段。`id` 为主键，`source_snapshot_id` 为外键；建立 `(security_id, metric_key, period_end, effective_at_utc)` 索引。

### `feature_set`

字段为：`id`、`security_id`、`report_period`、`as_of_utc`、`candidate_set_hash`、`template_id`、`template_version`、`contract_version`、`input_hash`、`status`、`financial_coverage`、`dimension_status_json`、`confidence_inputs_json`、`blockers_json`、`bundle_hash`、`bundle_path`、`missing_json`、`created_at`。

`status` 取值为 `partial`、`financial_ready`、`blocked`；覆盖率限制在0—1。唯一键为 `(security_id, report_period, as_of_utc, input_hash)`。

### `feature_value`

字段为：`feature_set_id`、`dimension`、`feature_key`、`period_key`、`value`、`unit`、`status`、`formula_version`、`evidence_json`、`missing_reason`。主键为 `(feature_set_id, dimension, feature_key, period_key)`。

特征包同时原子写入 `data/curated/formal_features/2026-06-30/<security_id>/<input_hash>.json`。数据库保存项目相对路径和内容哈希；读取时验签。该目录属于 `data/`，继续纳入Git，不增加忽略规则。

## 7. 深抓作业和幂等语义

新增报表子任务使用以下幂等键：

`deep_statement:v1:<security_id>:<dataset>:<report_period>:<as_of_cn_date>`

其中 `dataset` 只能是 `balance_sheet`、`profit_sheet`、`cash_flow_sheet`。payload包含证券、报表名、报告期、候选集合哈希、请求版本和刷新日期。按日期重抓可以发现三表修订；相同内容由快照哈希去重。字段映射升级只需新增离线 `feature_build`，不强制重抓。

`feature_build` 的幂等键包含证券、报告期、截至时点、候选集合哈希、当时三表快照hash、交易日历hash和特征契约/映射/模板版本。新增或修订任一报表只重建受影响证券。

现有120个旧格式pending `deep_financial` 作业必须保持可消费：worker把它当作规划任务，事务性入队三个子任务后把作业状态置为 `succeeded`，并在结果中写 `outcome=expanded`，不直接访问网络。若证券已不属于payload对应的候选集合，组合任务同样以 `succeeded` 完成，结果写 `outcome=superseded`，且不建立子任务。

`deep` 命令接口为：

```powershell
python -m ashare_pipeline.orchestrator --root data --db data/state.sqlite3 deep --online --limit 10
```

- `--online` 是远端访问的显式开关；
- `--limit` 必须是1—360，默认10，表示本次最多执行的远程报表子任务数；规划和离线特征构建不计入该上限；
- 每处理一张报表就提交一次状态，不把整个批次放进一个事务；
- 退出载荷只返回数量、证券ID、快照hash、特征包hash和错误分类，不返回原始三表；
- `incremental` 只入队新的日版本作业，避免一次增量命令阻塞数百次网络调用。

## 8. 错误处理

- HTTP 403、429、验证码或挑战页：标记 `SourceBlocked`，触发本轮同源熔断，已保存快照不删除。
- 连接中断、超时、源临时空结果：对应报表子任务进入 `retryable_failed`；其他报表子任务及其快照不受影响。
- 缺少 `REPORT_DATE`、证券标识或无法识别的期间：终止当前表的规范化并写 `quality_issue`，不得静默选行。
- 截止日前已披露但报表没有2026H1：对应子任务可重试；截止后仍缺失时子任务转为 `terminal_failed`，特征包 `blocked`，原因 `reported_but_statement_missing`。
- 历史期间或单个事实缺失：特征包 `partial`，不让网络作业无限重试。
- 同一时点存在无法按既定顺序消除的冲突：保留全部事实版本，对相关特征写 `blocked/conflicting_fact_versions`。
- 单只证券失败不能中断其他证券；每个失败必须出现在进度快照中。

## 9. 进度与质量指标

状态报告新增但不替换现有字段：

- `deep_candidate_count`；
- `deep_parent_job_counts` 和 `deep_statement_job_counts`，仅统计当前候选集合、当前请求版本，并按三张表分别展示；
- `statement_snapshot_counts`，分别统计三表；
- `feature_set_counts`：partial、financial_ready、blocked；
- `candidate_financial_coverage`；
- `template_counts` 和 `missing_reason_counts`；
- `latest_feature_contract_version`。

历史score item统计继续保留，但不得用全部历史score run的累计数冒充当前运行进度。正式七维覆盖、正式池数量和 `formal_score_ready` 在本阶段仍为0/false。

`candidate_financial_coverage` 定义为拥有三张已验签且含2026H1目标期快照的当前候选数除以120；同时显示精确分子、分母，不能只显示百分比。

## 10. 测试策略

### 数据库迁移

- 用真实v2表结构升级到v3，验证原run、job、snapshot、score数据逐行不变；
- 重复初始化不重复迁移；
- 外键、唯一键、状态枚举和覆盖率边界生效；
- 现有final不可修改语义保持不变。

### 契约和财务提取

- 显式0被保留，null不变成0，NaN/Infinity/布尔值被拒绝；
- 选择截至时点版本，截止后的NOTICE_DATE/UPDATE_DATE不可穿越；
- 输入乱序、并列更新时间和重复行仍产生确定结果；
- FY、H1累计期间正确，2025H1与2026H1不会和单季值混用；
- 对称增长、零分母、负基数、ROIC、应计项和FCF公式逐项验证；
- 普通工业、银行、地产/高杠杆至少各有一套固定字段夹具；
- 任一报表或历史期间缺失时状态为partial/blocked且数值不补0。

### worker和快照

- 120个旧组合任务稳定展开为360个唯一子任务，重复展开不增行；
- 两个worker不能租到同一子任务，执行中可续租，进程退出后的过期租约可恢复；
- 第二或第三张表失败时，前面成功快照仍可验签读取；
- 重试只补缺失或应刷新的表；
- 精确请求查询不会返回另一只股票的快照；
- 相同输入不重复feature set，源修订或版本变化生成新版本；
- 现有旧格式120个pending作业可直接消费；
- SourceBlocked触发熔断，结果载荷保持有界且不含原始记录。

### 端到端

- 以3只离线夹具证券验证工业、银行、缺失三表三种路径；
- 以 `deep --online --limit 1` 验证一次真实候选抓取，原始三表、事实、特征包和作业结果哈希可相互追溯；
- 跑完整现有109项回归测试，确保预筛、final闸门、报告和截止时间行为不变；
- 本阶段完成后 `formal_score_ready` 仍为false，正式池仍为0。

## 11. 验收标准

1. schema v2数据库可以无损、幂等升级到v3。
2. 120只当前候选全部出现在当前契约版本的深抓进度中，并且稳定展开为360个唯一报表子任务，不存在静默遗漏。
3. worker能断点续抓和续租；每张成功报表立即内容寻址保存，失败重试不丢其他报表数据。
4. 在线深抓完成标准为至少114/120只候选三张目标期报表齐备，即 `candidate_financial_coverage >= 95%`；其余候选必须有明确的重试或终止原因，不能被成功计数掩盖。
5. 每只已处理候选都有一个可验签特征包或明确的重试/阻断状态。
6. 特征包固定包含七维输入容器、证据、缺失原因、行业模板和版本哈希。
7. 所有财务特征能回溯至原始snapshot和字段；同输入重建结果逐字节一致。
8. FY2021—FY2025、2025H1和2026H1的期间规则通过固定夹具验证。
9. 缺失维度不补0、不重分配权重、不生成正式总分。
10. 五指标预筛仍明确标记为非正式；`finalize` 在正式七维、治理、事件和市场证据完成前继续失败关闭。
11. 新增原始数据与特征数据继续位于已跟踪的 `data/` 目录，不修改数据保留策略。
