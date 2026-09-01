# 执行账本 — plan: work/a_share_pipeline/PLAN.md

## 环境

- 工作区：项目型对话生成的隔离目录。
- Git：不可用；使用本账本、任务报告、测试输出和内容哈希代替提交记录。
- Python：3.12.13；pandas 已安装；akshare、baostock、requests、pytest 初始未安装。

## 预检接口表

| 生产者 | 消费者 | 接口 | 预检结果 |
|---|---|---|---|
| Task 1 状态库 | Task 2 数据适配器 | job、artifact、snapshot 状态及幂等键 | 一致；适配器不得直接改库 |
| Task 1 状态库 | Task 3 编排器 | 租约、重试、进度和发布闸门 | 一致；final 必须不可变 |
| Task 2 数据适配器 | Task 3 编排器 | 规范化记录、源版本和错误分类 | 一致；网络错误与无数据必须区分 |
| Task 3 编排器 | Task 4 报告/自动化 | JSON 状态快照与退出码 | 一致；自动化只调用公开 CLI |
| Task 1 自洽 | Task 1 测试 | 先失败测试后最小实现 | 一致 |
| Task 2 自洽 | Task 2 测试 | 外部网络以边界夹具测试，试采另行验证 | 一致 |
| Task 3 自洽 | Task 3 测试 | 未来日期不得被当作缺失，final 失败不得发布 | 一致 |
| Task 4 自洽 | Task 4 验证 | 报告读取同一状态库，自动化不复制业务规则 | 一致 |

## Rulings

- Ruling: 不初始化 Git 仓库 — 当前为项目型对话隔离目录，用户未要求版本库；以文件账本和测试证据代替 — 若后续需要协作式代码审查，缺少提交级差异会增加复核成本。
- Ruling: 8月31日夜间仍为 provisional，9月1日06:30（北京时间）才尝试 final — 截止口径包含8月31日全天公告 — 若用户只想收盘即刻结果，会晚数小时，但能避免漏掉晚间公告。
- Ruling: 巨潮自动化只做低频元数据/定向取证，不做全市场PDF镜像 — 降低合规与限流风险 — 深度候选的PDF核验会晚于结构化预评分。

## 状态

- Task 1 + Task 2: complete；合计 54/54 测试通过，独立复核均为 `Approved`。
- Task 3: complete；专项 33/33 测试通过，独立复核为 `Approved`。正式评分门槛已闭合：预筛与 partial score 不能冒充 V2 正式评分，证据不足时 formal scores/pools 保持 0。
- Task 4: Fix Round 2 已实现；专项 22/22 测试通过，canonical artifact 为 9 个 bounded datasets、8 个 sources。两次独立复核均因 runner `spawn_ready` 超时未能读取输入，因此当前**不能称为 Approved**。
- 总体状态：增量采集管线可继续运行，当前仍是 cutoff 前的 `partial` 工程状态，不发布正式股票池。

## 真实在线增量采集状态（2026-08-29）

- 沪深 A 股证券宇宙：5211；已披露合格证券：5053；披露覆盖率：96.9679524%。
- 五项核心字段完整率：99.4062933%；两个 95% 数据质量闸门均已达到。
- 诚实预筛候选：120；partial score items：120；formal scores：0；正式强烈关注池/等待价格池：0。
- `cutoff_passed=false`，所以即使当前覆盖与完整率达标，也不得进入 final 或发布正式池。
- 作业状态：pending 120、retryable_failed 2、succeeded 15。失败作业保留供重试与审计，不会被成功计数隐藏。

## 数据源试采记录（2026-08-28）

- 隔离环境：`.venv`；已锁定安装 `akshare==1.18.94`、`baostock==0.9.3`。
- BaoStock：匿名 login/logout 成功；2026-08-24至2026-08-28均返回交易日；`query_stock_basic()` 返回8928行，其中 type=1 为5549行；`query_all_stock(2026-08-28)` 返回7366行。
- AKShare：`stock_report_disclosure(market='沪深京', period='2026半年报')` 成功返回5550行；浦发银行 SH600000 的资产负债表、利润表、现金流量表均含2026-06-30中报记录。
- AKShare：`stock_zh_a_spot_em()` 被远端断开，记为可重试失败；主行情仍由 BaoStock 承担。
- 试采结论：免费混合源具备继续实施条件，但东方财富接口没有SLA，必须缓存、限速并允许单源降级。
- 可扩展性调整：新增 `stock_yjbb_em(date='20260630')` 全市场业绩报表作为预评分主批次；完整三表只拉约120只候选，避免截止日前逐股全量三表请求。

## 评分框架审计

- V1 四维存在利润重复计分和周期峰值陷阱。
- V2 规范已写入 `SCORING_SPEC_V2.md`：成长18%、估值18%、商业质量18%、盈利质量12%、财务安全8%、资本配置16%、预期差/买点10%，再由数据置信度向50分收缩。
- 治理、事件、ESG重大性、拥挤和周期阶段使用否决/状态/口径修正，不继续叠加普通权重。

## 七维财务特征基础层（2026-08-31）

- 状态库已为 schema v3；当前财务特征合约版本为 `feature-contract-v1`。
- 本阶段新增 3 个密封端到端测试；完整 `unittest` 回归为 337/337 通过。
- 现有 tracked 线上运营状态记录了 120 个候选，但不包含 schema v3 deep 财务契约所需的三表覆盖字段；因此尚未按 v3 deep 契约完成线上运营验收，不声明当前分子/分母或 `>=95%` 覆盖。
- 本阶段仅产出七维模型所需的财务特征输入，不代表七维正式评分已就绪；`formal_score_ready=false`。
- 正式等待价格池为 0，正式强烈关注池为 0，两个正式池的发布门闸仍关闭。
- 下一步：补齐市场、资本配置和治理输入，完成正式评分与发布验收。

## 七维财务特征信任边界修复（2026-08-31）

- 后续修复波次已收紧公共合约与真实持久化边界：所有证据的生效时点不得晚于 bundle `as_of_utc`；`unclassified` 模板只能保持 `blocked`、零财务覆盖率并携带 `industry_template_unclassified`。上述 PIT cutoff 与 unclassified blocked 不变量均由隔离测试覆盖。
- DB-backed 财务证据存在性、字段一致性以及 canonical source snapshot 参照核验仍在 StateStore 事务与 verified progress 读取路径中强制执行；本轮完整 `unittest` 回归为 370/370 通过。
- 后续独立 scoped review 与 fresh whole-branch review 仍是必须完成的门闸；本记录不预判其结论。
- 尚未执行真实 bounded network smoke，也未按 exact operational denominator/numerator `120/114` 完成线上验收。
- `formal_score_ready=false`，未发布 formal scores；正式等待价格池与正式强烈关注池均保持关闭且为空。

## 七维派生公式与 DB 镜像认证（2026-08-31）

- `financial-derived-v1` 的 90 个派生逻辑输出现由单一中立公式目录与 evaluator 生成并按 canonical raw facts 重算认证；公共合约同时强制 common template 的完整 raw + formula 闭集、元数据与覆盖率，无输出模板仍保持空财务命名空间。
- verified artifact 与 SQLite `feature_set` header 及完整 `feature_value` child set 现按 canonical 标量/JSON 精确比较；首写、幂等复用和 progress 共用同一 validator，progress 在一个 read transaction 内保持 newest-only、no-fallback 与每候选至多一个 bounded unknown。
- V/T 维容器现同样参与全局财务命名空间认证，common template 的财务公式/原始槽位不能通过复制到非财务容器绕过闭集，无输出模板也拒绝该类值；本轮 fresh full `unittest` 回归为 391/391 通过。后续独立 scoped review 与 fresh whole-branch review 仍是必须门闸，本记录不预判结论。
- 尚未执行真实 bounded network smoke，也未按 exact operational denominator/numerator `120/114` 完成线上验收。
- `formal_score_ready=false`，未发布 formal scores；正式等待价格池与正式强烈关注池继续关闭且为空。

## 七维最终信任边界收口（2026-09-01）

- verified progress 现将 bundle 的精确行业来源名称与注册模板绑定到当前冻结的 `CandidateContext`；不匹配记录 fail closed，且保持 visible newest-only、no-fallback。
- 资产负债恒等式及容差/适用性由单一生产 authority 定义；builder 与 StateStore 首写、幂等复用、verified progress 路径均从已认证 canonical raw facts 重算，拒绝 blocker 或财务状态的语义伪造。
- progress 在按证券选择最新记录之前强制 `feature_set.as_of_utc <= now_utc`；未来 bundle 不计数、不制造 unknown，也不能压制当前时点可见的较旧记录，等于截止时刻仍可见。
- 本轮 focused 9/9、受影响模块 294/294、fresh full `unittest` 399/399 通过；尚未执行真实 bounded network smoke，也未按 exact operational denominator/numerator `120/114` 完成线上验收。
- `formal_score_ready=false`、`seven_dimension_ready=false`；未发布 formal scores，正式等待价格池与正式强烈关注池继续关闭且为空。

## 七维最终六项 Minor 收口（2026-09-01）

- deep statement 与 feature job 现由同一个 owned heartbeat 覆盖完整租约生命周期；本地持久化、标准化、feature 构造及最终 owned transition 前均 fail closed，最终 transition 与周期续租串行化，`KeyboardInterrupt`/`SystemExit` 清理 heartbeat 后继续向外传播。
- legacy absolute snapshot 仅在 resolved target 保持于配置 `data_root` 内时兼容；零财务槽位的 bank/insurance/broker bundle 不再宣告不适用的资产负债恒等式 marker，但 canonical raw facts 继续保留且 bundle 仍由 specialized blocker 保持 blocked。
- migration 计划表名与 forged-unclassified 回归的阶段边界已校正；本轮 focused 9/9、受影响模块 329/329、fresh full offline `unittest` 407/407 通过。后续 scoped re-review 与 controller verification 仍是独立门闸，本记录不预判其结论。
- 尚未执行真实 bounded network smoke，也未按 exact operational denominator/numerator `120/114` 完成线上验收；未迁移或改写 runtime/tracked data。
- `formal_score_ready=false`、`seven_dimension_ready=false`；未发布 formal scores，正式等待价格池与正式强烈关注池继续关闭且为空。
