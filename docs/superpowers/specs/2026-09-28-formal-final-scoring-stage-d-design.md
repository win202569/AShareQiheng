# 正式 V3 阶段 D：政策后七维评分、资格与双池设计

日期：2026-09-28

状态：用户已确认架构、数据流、状态/持久化和测试/验收设计；本文待书面复核后进入实施计划。

上位规格：

- [正式评分与发布合同](2026-09-04-formal-scoring-release-contract-design.md)
- [正式政策合同与三阶段架构](2026-09-12-formal-policy-contract-design.md)
- [阶段 B 政策运行证据设计](2026-09-12-formal-policy-stage-b-design.md)
- [阶段 C 估值政策适配设计](2026-09-25-formal-valuation-policy-adapter-stage-c-design.md)

本文不重新批准经济规则。权重、公式、阈值、冻结时点、严格排除、同行规则、排序、行业上限和股票池容量均继承上位规格；冲突时以正式评分与发布合同为准。

## 1. 目标、边界与成功标准

阶段 D 将现有 `pre_policy` 七维算术、阶段 B 的可信政策结果和阶段 C 的政策调整后估值分位数连接成一个失败关闭、可重演、可持久化的最终评分与双池候选批次。

阶段 D 完成后，软件必须能够：

1. 对冻结宇宙每只证券形成唯一、可审计的最终状态；
2. 在同一可信根和冻结输入下组合非 V 正式输入、调整后 V 分位数和政策结果；
3. 应用维度封顶并重算七维、置信度、`S0`、`Sc`、`Sbase`、`B`、`R_safety`、风险暴露和等级；
4. 执行严格排除、池级禁止、双池门槛、稳定排序、行业上限和容量上限；
5. 将全宇宙状态、最终评分、决策轨迹和池结果作为同一追加式 V7 运行原子持久化；
6. 在缺少生产签名合同或完整生产证据时明确输出 preview/blocked，而不是冒充正式结果。

阶段 D 不负责：

- 发起网络采集或在数据库写事务中调用外部来源；
- 猜测生产阈值、真实证券字段映射、事件严重度或分位数算法；
- 修改阶段 B/C 已发布证明或把旧原始指标改写为政策调整值；
- 生成 V8 正式 release、对外发布文件或最终展示报告；
- 强制填满 20/50 股票池；
- 把测试夹具、120 只采集候选或历史 provisional run 当作全市场生产结果。

成功标准是“阶段 D 软件合同和离线运行器完成并通过验收”，不是“生产数据已经齐全”或“已经发布投资建议”。正式股票池仍需第 12 节的全部生产门闸及后续 V8 发布验证。

## 2. 不可变经济与身份规则

### 2.1 冻结范围与统一身份

- 冻结时点为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`。
- 正式范围为冻结时点的 SH/SZ/BJ 普通 A 股全集；北交所不得因旧 curated 名单缺失而被静默排除。
- 一个 Stage D 批次只能绑定一个冻结宇宙哈希、一个正式 v2 十角色注册根、一个 frozen input hash、一个阶段 B 批次和一个阶段 C 批次。
- 所有证券、行业、模板、指标、政策、适配器和证据身份必须来自上述同一根与冻结输入。
- v1 九角色图可继续旧能力，但没有 Stage C/D 正式资格。

### 2.2 七维、置信度与公式

七维权重固定：

| 维度 | 符号 | 权重 |
|---|---:|---:|
| 成长 | G | 18% |
| 估值 | V | 18% |
| 商业质量 | M | 18% |
| 盈利质量 | EQ | 12% |
| 财务安全 | FS | 8% |
| 资本配置 | CA | 16% |
| 买点 | T | 10% |

维度内部指标、权重、单位、方向和适用模板完全由同根 `FormalScoringRegistry` 定义。缺项不得填零、填同行中位数或重新分配权重。

置信度固定为：

```text
C = 0.60 + 0.40 × (0.30D + 0.25P + 0.25H + 0.20K)
```

正式评分要求 `D=1`、`K=1`，且 `H` 至少覆盖五个要求端点中的四个。经签名且已验证的“无一致预期覆盖”使用中性预期槽位，并令 `C <= 0.90`；无响应、未验证响应或 schema 缺失不等于无覆盖。

最终公式固定为：

```text
S0 = .18G + .18V + .18M + .12EQ + .08FS + .16CA + .10T
Sc = 50 + C × (S0 - 50)
Sbase = (.18G + .18V + .18M + .12EQ + .08FS + .16CA) / .90
B = 50 + C × (Sbase - 50)
R_safety = .40FS + .25EQ + .20M_sustainability + .15CA_downside_protection
risk_exposure = 100 - R_safety
```

`M_sustainability` 与 `CA_downside_protection` 继续使用正式评分合同固定的内部子式，不在阶段 D 另行定义。所有计算使用项目正式 Decimal 上下文：precision 50、`ROUND_HALF_EVEN`、显式指数范围和异常陷阱；比较、排序和持久化计算值不得提前显示舍入。

等级固定：`A+ >= 90`、`A >= 80`、`B >= 70`、`C >= 60`、`D >= 50`、否则 `E`。等级是展示/审计结果，不能替代未舍入分数参与资格判断。

### 2.3 同行与周期保护

- 同行优先使用“模板 × 申万 2021 二级行业 × 指标”；有效样本少于 20 时回退到同模板一级行业；仍少于 20 时该指标不生成正式分位数。
- 并列值使用平均秩；指标方向为 `lower` 时只反转方向性 percentile，不改变原始排序证明。
- 周期规则只作用于签名周期行业。连续五 FY 的 ROE 和营业利润率必须同时达到各自签名 80 分位，才命中周期顶部。
- 命中后 G、M 各自 cap 为 80；V 的受影响指标使用 `min(当期利润, 五年利润中位数)` 所形成的阶段 C 调整结果。
- 五年系列、算法版本或依赖证据不完整时是 pending，不得假定 clear 或自行选择分位数算法。
- 多个维度 cap 取最严格的最小值；池禁止取并集；全部来源规则和证据必须保留。

### 2.4 严格排除与双池规则

硬双池否决固定覆盖：

- ST 或 *ST；
- 退市整理或强制退市风险；
- 治理红灯；
- 权益/净资产非正；
- 保留、否定或无法表示审计意见；
- 连续 20 个交易日无有效成交。

治理橙灯、拥挤、重大解禁/减持窗口、重大事件和周期顶部保持独立状态，由真实签名政策声明禁止 strong、wait 或 both。软件不自行推断严重度。未量化重大事件不能进入 T 的伪精确分数。

强烈关注池资格：

```text
Sc >= 70
C >= .75
M >= 45
EQ >= 45
FS >= 45
T >= 55
无硬否决且无 strong 禁止
```

等待合适价格池资格：

```text
B >= 65
C >= .75
M >= 45
EQ >= 45
FS >= 45
T < 55
无硬否决且无 wait 禁止
```

两个资格定义天然互斥，仍须显式断言互斥。强池排序为 `Sc desc, C desc, R_safety desc, security_id asc`；等待池排序为 `B desc, C desc, V desc, security_id asc`。二级行业上限分别为 4 和 10，总量上限分别为 20 和 50。超过某行业上限后继续扫描其他行业；容量是上限，不凑数。强池因行业或总容量落选者不得转入等待池。

## 3. 选择的架构

阶段 D 采用“分层证明链 + 纯计算核心 + 薄运行器”。

```text
Frozen Universe + FormalScoreInputBatch
                    │
VerifiedPolicyResultBatch (Stage B)
                    │
PolicyAdjustedValuationBatch (Stage C)
                    ▼
D1 PolicyAdjustedScoreInputBatch
                    ▼
D2 FinalScoreCardBatch
                    ▼
D3 FormalEligibilityBatch + PoolSelectionBatch
                    ▼
D4 Append-only V7 persistence + thin offline runner
```

排除两种主架构：

- 单体 runner：评分、证明、资格、选池和持久化过度耦合，难以独立验证撤销与跨批攻击。
- DB-first 信任：数据库适合恢复和物化，但普通数据库行不能替代真实闭包产生、逐次验活的证明对象。数据库物化只能作为 D4 实现细节。

## 4. D1：政策调整后最终评分输入批次

新增闭包 mint 的不可伪造类型 `PolicyAdjustedScoreInputBatch`。它完整枚举冻结宇宙，并为每只证券生成一条最终输入记录；证据不足的成员也必须保留 pending 记录。

D1 消费：

- 同根 `VerifiedRegistryBundle`；
- `FormalScoringRegistry`、`FormalPolicyRegistry`、`FormalValuationAdapterRegistry`；
- 完整冻结宇宙及行业映射；
- `FormalScoreInputRepository.build_batch(...) -> FormalScoreInputBatch`；
- `FormalPolicyRepository.build_batch(...) -> VerifiedPolicyResultBatch`；
- `FormalValuationRepository.build_batch(...) -> PolicyAdjustedValuationBatch`。

每条 D1 记录保存并验证：

- security、模板、一级/二级行业和冻结成员身份；
- 非 V 指标的真实 `FormalScoreInput` 来源；
- 三个 V 指标对应的 `PolicyAdjustedValuationScore` 或精确 pending 原因；
- 同证券 `PolicyResult`、dimension caps、池禁止、状态、pending requirements；
- frozen input、注册根、阶段 B/C 批次和所有输入证明哈希；
- 规范 payload、条目哈希和批次哈希。

任一跨证券、跨根、跨 frozen input、跨批次、失效 capability、复制/伪造证明或发布后源变化都必须拒绝整个 D1 发布。一个成员的业务证据 pending 不拒绝完整批次，而是成为该成员明确的 `pending_evidence` 候选状态。

`PrePolicyScoreCalculation` 只作为兼容和公式对照证据存在。D1 不接受它作为可信最终输入，也不通过改名、复制字段或附加标志将其升级。

## 5. D2：最终评分卡批次

新增 `FinalScoreCardBatch` 和只能由所属批次读取的 `FinalScoreCard`。

D2 对每条可评分 D1 记录：

1. 从可信非 V 指标和 Stage C 三项 V 分位数重建七维原始分；
2. 按 `PolicyResult.dimension_caps` 对各维应用最严格 cap；
3. 同时保存 raw 与 capped 维度值、cap rule IDs 和证据哈希；
4. 从最终维度及可信 coverage 重算 C、S0、Sc、Sbase、B、R_safety、risk exposure 和 grade；
5. 生成完整规范计算轨迹和 final score hash。

D2 不修改原始指标、Stage C 调整值或 pre-policy 结果。cap 只能降低指定维度，不修改 C、不更改其他维度权重，也不能消除 pending。

存在任何必需指标缺失、无效单位、无效分母、同行不足、时间不可见、政策 pending 或身份不一致时，不产生 `FinalScoreCard`；批次中保留原因完整的 pending 条目。

## 6. D3：正式状态、资格与确定性双池

### 6.1 唯一最终状态

每只冻结成员必须拥有且只拥有一个最终状态。优先级固定：

1. `out_of_scope`
2. `pending_evidence`
3. `pool_vetoed`
4. `formal_scored`

状态含义：

- `out_of_scope`：冻结成员合同明确判定不属于普通 A 股正式范围；
- `pending_evidence`：必需 schema、registry、身份、完整性、时点、依赖、同行或业务证据未满足；
- `pool_vetoed`：最终评分卡可存在，但硬否决或签名 both 禁止使其不得进入任何池；
- `formal_scored`：最终评分卡完整且不存在双池硬否决，是否满足具体池门槛由独立资格决定。

pending 的优先级高于 veto，防止已有否决掩盖未完成证据。没有记录、空表或来源超时不能解释为“无风险”“无事件”“无覆盖”或中性值。

### 6.2 资格与选择批次

`FormalEligibilityBatch` 保存每只证券对 strong/wait 的门槛分解、政策禁止、硬否决、最终资格和原因。`PoolSelectionBatch` 消费完整资格批次和冻结二级行业，输出：

- 独立有序 strong/wait 元组；
- 每个候选的排序键；
- `industry_cap_reached`、`overall_capacity_reached`、`not_qualified` 等决策轨迹；
- 规范 count mapping 和批次哈希。

选择器先分别过滤资格，再使用第 2.4 节固定排序扫描。每个池独立应用行业与总量上限，不进行跨池回填。

## 7. D4：追加式 V7 持久化与薄运行器

### 7.1 追加式运行

V7 运行是 append-only。每次运行绑定：

- freeze time、冻结宇宙和成员清单哈希；
- production/test registry purpose 与正式 v2 根；
- frozen input hash；
- Stage B policy batch hash；
- Stage C adjusted valuation batch hash；
- D1/D2/D3 批次哈希；
- 完整 coverage manifest hash；
- 代码/合同版本及规范输入 manifest。

必须持久化：

- 全宇宙唯一状态与 reason codes；
- D1 最终输入来源和证明哈希；
- raw/capped 七维、cap 轨迹、C 分解、S0/Sc/Sbase/B/R/grade；
- 硬否决、池禁止和 pending requirements；
- strong/wait 资格、排序键、选择或跳过原因；
- 两个池的规范结果和 count mapping。

已 validated 或 published 的运行不可修改。更正数据、注册表、宇宙或代码版本必须创建新运行。旧 legacy `score_run/score_item` 和 V5 collection 状态不得被改写成 V7 结果。

### 7.2 原子边界

Stage D 的状态、最终评分、资格和双池结果作为一个外层原子结果提交。任何最终复验、序列化或提交失败都不能留下部分分数、部分状态或部分股票池。

Stage B/C 是独立已发布证明。Stage D 失败只撤销 D1-D4 未发布的子证明和数据库写入，不撤销或改写 genuine B/C 批次。

### 7.3 薄离线运行器

`FormalFinalScoreRunner` 只负责：

1. 加载并验活同根宇宙、registries、B/C repositories 和 coverage manifest；
2. 在任何正式计算前完成全批身份闭合；
3. 顺序调用 D1、D2、D3 的纯边界；
4. 最终复验并通过 D4 原子持久化；
5. 返回不可变诊断 DTO，不直接发布 V8 release。

runner 不复制经济公式，不读取旧 provisional 结果作为正式输入，不访问网络，也不把数据库 `COUNT(*)` 当作证明。

## 8. 增量失效与重建

Stage D 必须保存依赖图和每个输入哈希，按影响范围决定重建：

- 非同行、非政策的单证券证据变化：重建该证券及最终双池选择；
- V 指标值或资格变化：重建受影响的完整模板/行业/指标同行组，再重建所有受影响评分卡和双池；
- 非 V 同行指标变化：重建对应同行组及受影响评分卡和双池；
- PolicyResult 变化：按其 caps、normalization dependency、prohibitions 和 pending requirements 传播；
- 行业映射、注册根、冻结宇宙或 frozen input 变化：创建新的完整批次，不复用旧最终结果；
- 只改变显示格式或诊断 timing：不得改变规范结果哈希。

运行器可复用内容相同、身份仍当前的独立证明，但必须逐次验活，不能缓存“仍正式有效”的结论。

## 9. Production Coverage Manifest

生产数据审计独立于评分执行。顶层 manifest 至少包含：

```text
manifest_version, audit_at_utc, freeze_at_utc, report_period,
workspace_revision, db_path, db_sha256, db_schema_versions,
expected_schema_version, status_generated_at_utc,
universe_source, universe_records_hash, frozen_input_hash,
registry_manifest_hash, member_count, member_count_by_exchange,
query_version, blockers
```

逐成员逐证据需求的规范主键为：

```text
(frozen_input_hash, security_id, domain,
 selector_hash, period_or_window, exchange)
```

记录至少包含：

```text
required, applicability_rule_hash, source, dataset,
request_fingerprint, refresh_generation, task_id, collection_state,
selected_snapshot_id, content_sha256, manifest_sha256,
parser_id, parser_version, mapping_version,
published_at_utc, effective_at_utc, captured_at_utc,
source_updated_at_utc, expected_units, observed_units, missing_units,
verification_state, temporal_state, coverage_class, reason_codes,
evidence_hashes, rechecked_at_utc
```

`coverage_class` 只允许：

- `verified_complete`
- `verified_partial`
- `verified_no_coverage`
- `not_applicable_signed`
- `missing`
- `pending`
- `retryable_failed`
- `terminal_failed`
- `blocked_schema`
- `blocked_registry`
- `blocked_identity`
- `blocked_integrity`
- `blocked_temporal`
- `blocked_ambiguous`
- `blocked_dependency`

`verified_no_coverage` 必须有可信来源明确证明，且签名规则允许相应处理。缺表记作 `blocked_schema`，不能伪装为查询成功的 0 行。交易日历按交易所证明，不能把一份无 exchange 日历复制到所有证券来虚增覆盖。

正式覆盖统计必须调用对应 repository 的验证入口，重验签名来源、当前版本、时点、内容哈希和身份；普通 SQL 行数只用于诊断，不能授予评分资格。

## 10. 生产合同包

Stage D 软件必须配置驱动。正式运行前，用户需另行批准真实签名 production registry，至少包括：

- 周期 80 分位的明确算法版本；
- 各模板数值 redline 的真实字段映射、单位、比较符和阈值；
- 治理橙灯、拥挤、解禁/减持、重大事件分别禁止 strong、wait 或 both 的选择；
- 全部正式来源、parser/mapping 版本和作用域；
- production signing identity 与根 manifest。

软件不得提供隐式生产默认值。缺少生产合同包时可运行 test preview，但必须阻断 official run 和两个正式池。

## 11. 错误处理与安全边界

- 结构错误（伪造、跨根、字段多余/缺失、哈希或身份不一致）拒绝当前批次，不转换成普通证券 pending。
- 业务证据不足或来源失败在完整批次中形成证券级 pending，并保留精确 reason codes。
- 已有 veto/cap 不消除 pending；已知部分分数不补齐缺失维度。
- 发布前必须重新验证所有来源批次、注册对象、规范字节、哈希、冻结时点和当前 capability。
- 外部网络访问只发生在独立采集阶段；评分事务不等待网络。
- 诊断信息不进入规范结果哈希，且不得包含非确定 timing 或进程局部身份。
- 公开对象必须防止普通构造、复制、pickle、弱引用重定向、闭包/方法替换和跨批次 capability 重放。

## 12. 测试与验收

### 12.1 单元与经济规则

- 七维原始/封顶值、C、S0、Sc、Sbase、B、R、风险暴露和等级的精确 Decimal 测试；
- 多 cap 最小值、池禁止并集和 pending 保留；
- strong/wait 边界值、互斥、固定排序、行业 4/10、总量 20/50；
- 行业满额后继续扫描、容量不凑数、强池容量落选不进入 wait；
- 无一致预期覆盖与无响应/未验证响应的区别。

### 12.2 身份与攻击矩阵

- 跨 registry root、frozen input、security、policy batch、valuation batch 和 peer context；
- 直接构造、复制、序列化、弱引用重定向和 capability 重放；
- 发布后源变化、注册方法替换、规范编码器替换和数据库行篡改；
- 旧 v1/v2 对象、pre-policy 对象和普通 mapping 不能冒充 D1-D4 证明。

### 12.3 状态与失败关闭

- schema/registry/identity/integrity/temporal/dependency 阻断；
- 缺失、冲突、无效分母、同行不足和政策 pending；
- genuine `verified_no_coverage` 与不存在记录；
- pending 优先于 pool veto，pool-vetoed 可保留审计评分卡但永不入池；
- 完整宇宙逐成员恰好一个最终状态。

### 12.4 持久化、恢复与增量

- V7 migration 保留旧 V2-V6 数据并只增加完整新表；
- building/validated/published 生命周期和不可变性；
- 部分写、最终复验失败、序列化失败、提交失败均无 torn result；
- 重启后按 exact input manifest 恢复，不静默选择后来更正；
- 单证券、同行组、政策传播和完整宇宙四类失效范围；
- 同一输入独立重放得到相同规范字节和哈希。

### 12.5 性能与全量验收

先使用 20/23 证券真实性能夹具验证完整证明链、同行重排和攻击矩阵，再使用正式冻结全宇宙执行带诊断验收。诊断至少记录：

- 各阶段耗时和全量验证次数；
- 成员、指标、同行 cohort、排序和重建数量；
- 各最终状态、pending reason、veto、资格和池计数；
- 行业 cap、总容量跳过数量；
- registry/repository full parse、财务重推导和 source recheck 次数。

性能优化不得削弱逐次验活、完整身份闭合、同行完整性或发布前最终复验。

## 13. 正式生产门闸

只有全部满足时，Stage D 结果才有 official 候选资格：

1. 建立含 SH/SZ/BJ 的正式冻结普通 A 股宇宙；
2. 数据库安全迁移到 V7，并通过旧数据保留和新表完整性验证；
3. production registry 真实签名且经过用户批准；
4. coverage manifest 覆盖完整冻结宇宙，所有必需证据均为允许正式评分的状态；
5. Stage B/C/D 根、frozen input、成员和批次来源全部闭合；
6. Stage D 全宇宙运行通过状态完整性、公式、排序、容量和确定性复验；
7. 后续 V8 validator、publisher 和正式报告验证通过。

任一门闸不满足时，系统只能保存 preview/blocked 诊断，正式强烈关注池和等待合适价格池均保持未发布。合法正式结果可以少于 20/50，甚至为 0。

## 14. 旧 V7 任务收口

旧 [V7 scoring/pool plan](../plans/2026-09-04-formal-v3-scoring-pool-engine.md) 的任务按以下方式收口：

- Task 1–3：保留已实现的 registry、同行内核与 pre-policy 算术；Stage D 只复用经对照验证的纯 Decimal/排名内核，不把旧证明升级为最终证明。
- Task 4：由 Stage A/B/C 的签名政策、证据、结果和估值调整链正式取代；禁止再实现第二套 `PolicyOutcome` 真相。
- Task 5：经济规则保留，由 D3 使用新 final scorecard 和 genuine `PolicyResult` 吸收实现。
- Task 6：由 D4 修订吸收，增加 v2 root、policy/valuation/D1-D3 hashes 和完整状态/决策谱系。
- Task 7：由 D4 薄运行器修订吸收，依赖升级为 Stage B/C repositories 和 Stage D 批次。

V8 release/reporting 计划不纳入 Stage D，待 D 完成后独立实施。

## 15. 当前生产数据审计基线

截至本文设计时，只读审计显示：

- 旧 curated 宇宙 5,213 只，仅 SH 2,315、SZ 2,898、BJ 0；
- 本地数据库迁移账本最高 V4，当前代码期望 V7，正式 V5-V7 表不存在；
- 旧三表 raw 每表 6 只，旧规范化财务事实 14,894 行但仅覆盖 5 只；
- 旧 feature set 16 个，13 blocked、3 partial，`financial_ready=0`；
- 冻结日 2026-08-31 行情覆盖为 0；
- 正式行业映射、Context、Policy、Range、监管事件、事件日历和共识证据不存在；
- 状态文件和实库已有计数错位，`pipeline_state=data_ready` 仅表示旧摘要门闸，不是正式评分资格。

这些数字只是下一轮 coverage manifest 的起点，不进入 Stage D 经济规则，也不能被写成已核验无覆盖。

## 16. 实施分解边界

Stage D 实施计划应至少按以下可独立审查边界拆分：

1. D1 最终输入合同、身份闭合和完整批次；
2. D2 cap 与最终七维/Sc/B/R/grade 计算；
3. D3 状态、资格和确定性双池；
4. D4 V7 migration、append-only repository 和原子事务；
5. 薄 runner、增量失效与恢复；
6. coverage manifest 审计器和生产门闸；
7. 全链攻击、性能与全量诊断验收。

每个子阶段先写有效 RED，再实现最小能力，独立审查并修复后才能进入下一阶段。生产取数可与软件实现并行，但不得在 coverage manifest 和 production registry 批准前宣称正式评分或发布股票池。
