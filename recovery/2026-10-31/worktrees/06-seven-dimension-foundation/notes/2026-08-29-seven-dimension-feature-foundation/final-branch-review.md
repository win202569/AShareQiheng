# Final Branch Review

审查范围：`e361fbd1e2f019dfe47c82c32880c7a44084e3a9..c8c25bfc9c8a8eefc934fd6e95ac1a5063a5fe9f`，覆盖计划 Tasks 1–13 的跨任务一致性。权威依据为计划、设计规格、SDD 台账、指定的 28-commit 完整审查 diff，以及 Task 13 最终报告和复审报告。

审查方法：按要求分段阅读指定 diff，不重新运行 `git diff`/`git log`，不访问真实网络，不打开或迁移 tracked runtime DB，也未重跑全套测试。现有证据已经足以确定下述问题，因此没有额外运行 focused test；只对 diff 内冻结交易日历 fixture 做了只读结构核对。本文区分“实现代码达到合并条件”与“线上运营验收已经完成”。

## Strengths

- SQLite v2→v3 迁移整体扎实。`ashare_pipeline/state_store.py:280` 使用 `BEGIN IMMEDIATE` 包住升级，逐项核验既有 DDL，失败回滚；迁移测试用七张真实 v2 表和数据验证保留、幂等与失败原子性，没有以空库或镜像断言代替迁移行为。
- 财报快照的基本信任链完整。`ashare_pipeline/deep_worker.py:491`、`ashare_pipeline/deep_worker.py:936` 在入队和执行两侧绑定并复验 `source + dataset + exact request`；`ashare_pipeline/snapshot_repository.py:100` 同时核对内容哈希和数据库元数据，快照为内容寻址。
- point-in-time 选取实现与 Ruling F1 一致。`ashare_pipeline/financial_features.py:447` 先排除 `effective_at > as_of` 的事实，再按公告、更新、抓取顺序选最新可见版本，最高优先级冲突保持阻塞而不是静默任选。
- 作业最终状态和安全 follow-up 的事务边界正确。`ashare_pipeline/state_store.py:537`、`ashare_pipeline/state_store.py:598` 把 owner 校验、完成/失败和 follow-up 入队置于同一事务；远端 attempt 上限和 source circuit 也有持久化状态与对应测试。
- 七维输出形状、可审计证据及 fail-closed 总方向正确。输出固定七个维度，缺失/零值/非有限数大部分路径有显式处理；`ashare_pipeline/orchestrator.py:1117` 将 formal score 与两个官方池硬编码关闭，finalize 在分数不可用时失败关闭。
- Task 13 的三证券 hermetic replay 不是空通过。两套独立 harness 分别走生产执行路径和从 fixture 重建的期望值；确定性 UUID shim 仅替换代理主键，未替换业务判断。日历 alias 在进入内存前仍验证 fixture 的 source、dataset、request identity，作为 hermetic 环境适配是合理的。
- 审查包没有混入 runtime SQLite、raw production row 或运行时 feature 文件；CLI 聚合输出没有直接泄漏 raw 行。完整测试报告记录 337 项通过，可作为先前验证证据，但本次审查没有把该报告当作覆盖下列跨接口缺陷的替代品。

## Issues

### Critical

无。

### Important

1. **冻结交易日历没有隔离已经持久化的旧 financial facts。**

   - 位置：`ashare_pipeline/deep_worker.py:1175`、`ashare_pipeline/deep_worker.py:1182`、`ashare_pipeline/deep_worker.py:1192`；相关 schema：`ashare_pipeline/state_store.py:135`。
   - 问题：feature job 确实用当前冻结日历重新 normalize 每个 statement snapshot，但随后丢弃 `_facts`，转而按 statement snapshot ID 从数据库查询全部历史 facts。`financial_fact` 又没有 calendar snapshot provenance。因此，同一财报快照曾在日历 A 下 normalize、当前任务冻结到日历 B 时，B 的构建仍可看到 A 推导出的 `effective_at`；当前日历缺失时也能重新读到旧 facts。
   - 影响：在两个日历给出不同“下一真实交易日”时，旧事实可能过早进入 as-of 视图，或在同优先级下由哈希/ID 偶然胜出。最终 bundle 的输入不再由冻结快照唯一决定，破坏 point-in-time 正确性、可恢复性及 input hash 的审计语义。
   - 修法：构建时只选择本次、使用当前冻结 calendar normalize 返回的 facts；或给 `financial_fact` 增加并强制查询 exact calendar snapshot provenance。增加回归：同一 statement refs 先后以两个下一交易日不同的日历 normalize，当前 job 不得读取旧日历事实；calendar 为 null 时不得复用旧日历事实。

2. **交易日历快照没有绑定 BaoStock source 和 exact request。**

   - 位置：`ashare_pipeline/deep_worker.py:509`、`ashare_pipeline/deep_worker.py:919`、`ashare_pipeline/deep_worker.py:1018`；上游依赖：`ashare_pipeline/orchestrator.py:148`；解析器：`ashare_pipeline/financial_features.py:161`。
   - 问题：statement refs 会校验 source、dataset 和 request fingerprint，但 calendar ref 只冻结/复验 ID 与 hash。calendar 内容解析只验证 dataset、日期范围和行结构，不要求 `source == "baostock"`，也不要求 request 与本次规范请求完全相等。依赖抓取返回后也没有在持久化前复验 fetch batch 的 source/dataset/request 与请求相符。
   - 影响：错误 source 或非规范 request 的日历快照可以被持久化、冻结并参与公告日映射；“真实交易日历”与精确验签的跨任务保证在 calendar 这条链上断开。
   - 修法：在 fetch 返回、feature payload 构造及执行解冻三处都校验 BaoStock source、calendar dataset、规范化 exact request/fingerprint；将该 identity 纳入冻结 ref。增加 wrong-source、wrong-dataset、request-tamper 的入队与执行双侧测试。

3. **房地产与资源周期模板仍可用通用财务槽位达到 `financial_ready`。**

   - 位置：`ashare_pipeline/industry_templates.py:30`、`ashare_pipeline/industry_templates.py:34`、`ashare_pipeline/financial_features.py:968`。
   - 问题：`real_estate` 和 `resource_cyclical` 注册项使用 `_COMMON_FINANCIAL_SLOTS`，且 `specialized_inputs_required=False`；该字段之后没有被 readiness 逻辑消费。只要通用槽位覆盖率、期间数和模板条件满足，构建就会标记 `financial_ready`。
   - 影响：这与绑定规格“银行/保险/券商/房地产/资源周期缺少专用输入必须 partial/blocked，不得回退通用模板”冲突。当前测试只验证选中了注册表 key，未证明专用输入缺失时仍失败关闭。
   - 修法：为两类行业实现真实专用 slot 与公式，或在专用输入尚未落地前无条件 fail closed；让 `specialized_inputs_required` 成为实际契约而非未使用元数据。增加“通用财务事实全部齐全但专用输入缺失，仍不得 ready”的回归。

4. **三项公式给分母增加了规格未授权的正数限制。**

   - 位置：`ashare_pipeline/financial_features.py:808`（gross margin）、`ashare_pipeline/financial_features.py:831`（total accruals）、`ashare_pipeline/financial_features.py:846`（ROIC）；相反断言：`tests/test_financial_features.py:896`。
   - 问题：实现只在 revenue、average assets、average invested capital 大于零时计算。绑定规格给出了这些公式，并只对 actual tax rate 明确规定正数边界；通用数值规则要求零分母/非有限数缺失，而没有把负的非零分母定义为不可计算。测试还把负 average invested capital 固化为 missing，因而是测试/计划理解偏离规格，不是合规证据。
   - 影响：合法的负收入、负平均资产或负投入资本场景被静默丢成缺失，改变七维输入与 coverage/status，在困难企业或重组场景尤其会系统性失真。
   - 修法：除规格明确限制外，仅拒绝零或非有限分母；如产品需要把负分母作为数据质量 blocker，应先修改绑定规格并明确状态语义。增加负的非零 revenue/average assets/average invested capital 的公式回归。

5. **真实持久化 bundle 的缺失原因永远不会进入 CLI progress 聚合。**

   - 位置：`ashare_pipeline/state_store.py:1055`、`ashare_pipeline/state_store.py:1061`；消费者：`ashare_pipeline/orchestrator.py:1057`；镜像测试：`tests/test_orchestrator.py:943`。
   - 问题：`put_feature_bundle` 写入的 `missing_summary` 元素字段名为 `reason`，progress 却读取 `missing_reason`。测试手工向数据库塞入 consumer 期望的 `missing_reason`，没有通过真实 bundle 持久化路径，因此在接口两端分别自洽却跨接口失配。
   - 影响：`missing_reason_counts` 对真实构建始终为空，运营人员无法从 bounded progress 看出 coverage/blocker 的主要原因，破坏审计和故障分流。
   - 修法：定义一个规范字段并让生产者/消费者共用（最小修复是按实际 schema 读取 `reason`）；测试必须先通过 `put_feature_bundle` 持久化真实 bundle，再调用 progress 断言聚合结果。

6. **FeatureBundle/进度读取的信任边界不足，孤儿或被篡改的 feature 记录仍会被报告为成功。**

   - 位置：`ashare_pipeline/feature_contract.py:168`、`ashare_pipeline/feature_contract.py:189`、`ashare_pipeline/feature_contract.py:231`；进度读取：`ashare_pipeline/orchestrator.py:1036`；测试：`tests/test_orchestrator.py:943`。
   - 问题：`IndustryContext`、`ConfidenceInputs` 和 `FeatureBundle` 只做部分枚举/真值验证，没有严格校验字段类型、模板版本、count key/非负整数、身份/日期/hash/blocker 类型及关键跨字段不变量。与此同时 progress 直接信任 SQLite `feature_set` header 和 summary，不验证其引用的 bundle 文件是否存在、哈希匹配且内容能通过规范解析；测试甚至以不存在的 bundle path 作为成功计数 fixture。
   - 影响：规范 JSON 但语义无效的 bundle 可通过 public verified read；孤儿、缺失或篡改文件对应的 DB 行仍被计为 `financial_ready` 并进入模板/缺失摘要，使“数据库与 feature file 不产生孤儿或覆盖”的审计承诺无法在读取侧成立。
   - 修法：强化 runtime 类型、hash/日期格式、完整 count 集、模板/version 与 status/coverage/blocker 的跨字段不变量；progress 在计数前必须读取并校验 bundle 内容哈希，并与 DB header 交叉核对。增加 canonical-but-invalid bundle、删除文件、内容篡改和 DB/file header 不一致的回归。

### Minor

1. **heartbeat 没有覆盖完整 leased execution。** `ashare_pipeline/deep_worker.py:1495` 的 heartbeat 仅包围远端 fetch，后续 persist/normalize/follow-up 在 heartbeat 之外；feature job 路径 `ashare_pipeline/deep_worker.py:1244` 也没有 heartbeat。默认 900 秒租期、内容寻址和 owner-checked final transition 降低了概率，但慢持久化/normalize/build 超时后，stale worker 仍可能先写 facts/files 再在最终转移时才发现失去 lease。建议让 heartbeat 覆盖整个 leased job，或至少在每个外部副作用前复验 owner，并用延迟测试证明 stale worker 不写副作用。计划 Task 11 将范围缩成“fetching 时 heartbeat”，而绑定规格写的是 execution 期间续租；应以规格为准修正文档和实现。

2. **legacy 绝对 snapshot 路径绕过 data-root containment。** `ashare_pipeline/snapshot_repository.py:129` 对相对路径做 root containment，但 `ashare_pipeline/snapshot_repository.py:133` 对绝对路径直接 resolve 并接受。即使仍有 hash 校验，本地 DB 中的绝对路径可让 reader 读取 data root 之外的文件。建议仅接受落在允许 data root 内的 legacy absolute path，或迁移后拒绝；对应测试应覆盖 root 外路径。

3. **计划中的 v2 表名与实际 schema 不一致。** `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md:476` 写成 `snapshot`、`export_artifact`，实际既有表和迁移使用 `source_snapshot`、`artifact`。实现和迁移 fixture 使用的是正确字面 schema，因此这是文档缺陷而非迁移阻塞；应修正计划，避免以后按错误表名做演练。

## Rulings/deferred triage

- **Ruling F1 — 接受。** 可见事实先按 `effective_at <= as_of` 过滤，再按 announcement/update/fetch 排序；冲突保持 blocker，符合规格。
- **Ruling F2 — 接受。** `feature_input_hash` 的三个固定 key 均进入规范 JSON，缺项规范化为 null，没有通过省略 key 改变哈希域。
- **Ruling F3 — 接受实现，保留文档 Minor。** 迁移测试使用真实 legacy DDL 和七表数据；计划中两个表名的笔误按上面的 Minor 修正即可。
- **Ruling F4 — 接受。** Task 7 的生产侧最小 validator 与 Task 13 的共享严格 fixture helper 分工清楚；两者都在其信任边界验证 identity/shape，未形成空通过。
- **Ruling F5 — 接受。** public root progress 属于计划交付物；private SDD 台账未进入审查 diff，继续不应提交。
- **Ruling F6 — 接受。** `TEMPLATE_VERSION` 只有 `ashare_pipeline/industry_templates.py:8` 一个生产定义点，各消费者引用同一常量。
- **Ruling F7 — 接受。** coverage 分母使用完整 context members，而不是只数成功证券；运营脚本仍要求 exact 120 denominator / 114 numerator。
- **Task 13 calendar alias ruling — 接受并记录边界。** alias 只在验证 fixture source/dataset/request identity 后用于 hermetic replay；它不独立证明交易所前缀路由，但独立 identity 测试已覆盖该生产边界。
- **Task 13 双 harness/deterministic UUID ruling — 接受。** 两套 harness 的期望构造来源独立，UUID shim 仅稳定 surrogate IDs，不替代业务路径或断言。
- **Deferred `.tmp-root-check/` — 向 merge operator/controller 显式升级。** 指定审查包本身没有 runtime DB/raw data，但 raw clean-status 日志不在包内，且本次审查被要求不得重新运行 `git diff`/`git log`，所以不能在本文中关闭。它不是代码 blocker；合并前必须由有权限的一方确认该目录未被跟踪、未污染 worktree。若 clean-status 发现 tracked/runtime 数据，则必须先清除污染再合并。

## Recommendations

1. 先修复上述 6 项 Important，并为每项添加从真实生产者到真实消费者的 focused regression；特别避免继续用手工 DB row 代替 feature-file/SQLite 双持久化路径。
2. 修复后做一次针对性跨接口复审：`calendar fetch → exact freeze → normalize → PIT select → feature bundle → persisted file/hash → progress`，并重新检查 formal score、两个官方池和 finalize 仍保持关闭。
3. 合并前由 merge operator 完成 clean-status/runtime-data 检查，关闭 `.tmp-root-check/` deferred；这项检查不能由本审查包推断完成。
4. 代码修复并通过 hermetic 回归后可以达到“可合并的基础层”，但不能宣称线上运营验收已完成。仍需按计划单独执行 bounded online smoke、source circuit/attempt 观测以及 exact 120 denominator / 114 numerator invariant；在这些线上证据完成前，生产就绪状态应表述为“代码完成，运营验收待执行”。

## Assessment

**Ready to merge? With fixes — 当前 HEAD 不应合并。**

没有 Critical；有 6 项 Important 阻塞：冻结日历未隔离旧 facts、calendar identity 未做 source+exact-request 验签、房地产/资源周期模板可错误 ready、三项公式擅自要求正分母、真实 missing reason 无法聚合，以及 bundle/file/DB 读取信任边界不足。修复并通过 focused regression 与复审后，可进入合并；三个 Minor 不阻塞，但 heartbeat 边界宜在上线前处理。

即使代码阻塞全部关闭，formal score 与两只官方池仍应继续失败关闭；线上 114/120 等运营验收未执行，不能把“代码可合并”表述为“生产运营已验收”。
