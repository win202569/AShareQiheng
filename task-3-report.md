# Task 3 实施报告

## 结果

已实现整理层、诚实预筛、增量编排和冻结阻断：

- `ashare_pipeline/curation.py`
- `ashare_pipeline/scoring.py`
- `ashare_pipeline/orchestrator.py`
- `tests/test_curation.py`
- `tests/test_scoring.py`
- `tests/test_orchestrator.py`

当前预筛只输出批量业绩表可支持的“成长代理/质量代理”，每行固定
`is_official_score=false` 和“仅供深抓排序，不是V2正式总分”。没有生成成长、估值、风险、买点四项正式分，也没有生成两个股票池。

## TDD 红灯记录

按模块先写测试并观察预期失败：

1. 整理层首次运行因 `ashare_pipeline.curation` 不存在而失败。
2. 预筛首次运行因 `ashare_pipeline.scoring` 不存在而失败。
3. 编排首次运行因 `ashare_pipeline.orchestrator` 不存在而失败。
4. 编排初版测试暴露 SQLite 只提交未关闭连接，在 Windows 清理临时数据库时触发文件锁；改为 `closing(sqlite3.connect(...))` 后通过。
5. 日期粒度公告在采集当日中午被误判为未来数据；新增回归测试后改为日期粒度只比较日期，带时刻记录才比较绝对时刻。
6. 证券宇宙重复代码未进入质量闸门；新增回归测试并将宇宙与业绩两侧唯一性同时纳入闸门。

### Fix round 1 红/绿证据

审阅指出 13 项问题后，先补测试并观察到预期红灯：

- `tests.test_curation tests.test_scoring -v`：16 项中 3 个失败、2 个错误，分别证明 9 月 1 日修订穿透截止、无效公告时点未阻断、缺少披露覆盖分母、689 CDR 被误纳入，以及行业代表阶段突破 120 上限。
- `tests.test_orchestrator -v`：15 项中 5 个失败、10 个错误，覆盖相对根目录不可重建、异常后 run 残留 running、租约状态被误称幂等、过期租约未恢复、规则指纹缺失、正式覆盖率误用预筛覆盖率、9 月 1 日观察未隔离、行情证据可自报、质量审计字段丢失等问题。
- 将 9 月 1 日修订回归进一步收紧为“最新表只返回修订版、不再返回截止内旧版”后，先观察到冻结证券行丢失的 `StopIteration`；补充可信旧冻结行携带逻辑后转绿，并验证冻结文件字节不变。

修复后上述两组分别为 16/16、15/15 通过。

## 测试

Task 3 专项回归：

```text
.venv/Scripts/python.exe -m unittest tests.test_curation tests.test_scoring tests.test_orchestrator -v
Ran 31 tests in 8.324s
OK
```

Task 1–4 完成对接后再次执行全量发现：

```text
.venv/Scripts/python.exe -m unittest discover -s tests -v
Ran 106 tests in 574.449s
OK
```

Task 3 未修改 Task 4 文件；全量回归包含 Task 4 的 21 项测试。

Task 3 专项由 10 项 curation、6 项 scoring、15 项 orchestrator 组成。

字节码编译：

```text
.venv/Scripts/python.exe -m compileall -q ashare_pipeline
exit 0
```

网络只留给控制器后续试跑，本任务测试未访问网络。

## Task 2 接口假设与对接结果

- `FetchBatch.sha256()` 对 source、dataset、request、records、source_version、metadata 的规范 JSON 求哈希，不含 `fetched_at_utc`。
- `SnapshotStore.write()` 返回 `(Path, digest, created)`；内容相同时可返回首次快照路径并令 `created=false`。
- `StateStore.get_job()` 返回公开的 status/result/error/lease/重试字段；在线开始使用 `recover_expired_leases(now_utc)` 后再租约领取。
- `performance_report` 使用 Task 2 固定中文键（股票代码、股票简称、每股收益、营业收入/净利润及同比、每股净资产、ROE、经营现金流/股、毛利率、行业、最新公告日期）。真实接口已完成集成回归，无待解决接口缺口。

## 关键实现口径

- 证券宇宙严格保留 BaoStock `type=1`、`status=1` 且代码匹配 `sh.6xxxxx` 或 `sz.[03]xxxxx` 的证券；ST 只打风险标签；`sh.689xxx` CDR 明确排除并单列计数。
- 业绩表代码强制六位；正式视图先排除晚于 `2026-08-31T23:59:59+08:00` 的版本，再按公告时点与规范 JSON 哈希稳定去重。9 月 1 日以后观察另写 `performance_post_cutoff.json`，不会替换冻结视图。
- 缺失或不可解析公告时点会阻断正式质量；披露证券覆盖率与五项核心字段完整率分别使用95%闸门和独立分母。
- 百分位采用平均并列名次。单一有效观察取中性 50；行业单项有效样本少于 20 时回退全市场。
- 缺失项不填 0，模块按实际可用权重归一，覆盖率按五项原始权重单独下降。
- 候选最多 120；覆盖率至少 0.55 的大行业先保留前二，再按全市场预筛排序补齐。
- Task 2 修复后的 `FetchBatch.sha256()` 不含观察时刻，`SnapshotStore` 可跨观察日对相同内容去重；编排层语义哈希与该口径一致，并沿用首次成功快照证据。
- 深抓幂等键基于单家公司整理后业绩记录的哈希，不使用会被其他公司相对排名影响的预筛分，因此只为新增/变更公司新增任务。
- 每个整理文档的输入指纹都含整理 schema 与规则哈希；即使源哈希未变，旧 schema/规则产物也会重建。
- 在线开始先回收过期租约；租约未取得时通过 `StateStore.get_job()` 如实区分 succeeded/running/retryable/terminal，并保留缓存批次证据。
- `score_item.coverage` 只统计七维正式特征；当前没有正式特征，因此为0。五项预筛覆盖率仍仅保留在预筛记录中。
- 质量纯函数判断披露数据；编排冻结时再核验 2026-08-31 行情。行情文件必须引用状态库内可复算的源快照哈希和匹配的证券宇宙记录哈希，逐行满足唯一证券、精确日期、全宇宙覆盖及有效收盘价；停牌仅接受原始 `preclose` 并生成带原始记录哈希和转换版本的派生证据。自报 `complete`/`row_count` 不再有效。
- `status` 会解析整理文件以提取 metrics，但不打开 raw 快照，也不把整理 records 输出到状态 JSON。
- 所有在线快照路径统一以绝对路径登记；相对 `--root` 已有端到端回归测试。
- `start_run` 之后的整理、快照、SQLite、评分、冻结和状态写入异常均尝试将 run 结束为 failed；若失败状态自身无法写入，仍重新抛出最初异常而不掩盖。

## CLI

```text
python -m ashare_pipeline.orchestrator --root <data_root> --db <sqlite> bootstrap [--online]
python -m ashare_pipeline.orchestrator --root <data_root> --db <sqlite> incremental [--online]
python -m ashare_pipeline.orchestrator --root <data_root> --db <sqlite> status
python -m ashare_pipeline.orchestrator --root <data_root> --db <sqlite> finalize --now-cn <ISO>
```

CLI 输出紧凑 JSON；状态原子写入 `<root>/status/pipeline_status.json`。

## 正式评分剩余缺口

Task 3 不具备 V2 七维正式特征、行业专用模板、半年报正文风险核验、治理/事件证据和 2026-08-31 收盘估值。因而所有 `score_item` 保持 `partial` 且 `scores_json=NULL`；`finalize` 即使过了截止、质量和行情证据齐全，也会以 `formal_v2_scores_unavailable` 阻断，不调用 `StateStore.finalize_score_run()`，不修改 provisional 状态。

控制器已完成一次真实在线全市场增量采集：证券宇宙 5211、已披露合格证券 5053、披露覆盖率 96.9679524%、五项核心字段完整率 99.4062933%。预筛候选与 partial score items 均为 120；formal scores 和两个正式股票池仍为 0。当前 `cutoff_passed=false`，作业状态为 pending 120、retryable_failed 2、succeeded 15；候选完整三表/正文、治理事件证据与最终行情仍按增量任务继续处理。

本轮实现与 Task 1–4 集成无阻塞。正式发布仍按设计被
`formal_v2_scores_unavailable` 阻断；这是缺少正式证据时的安全闸门，不是把预筛冒充正式评分。

## Fix round 2

独立复核提出的三个剩余问题已按测试驱动修复：

- 同日缓存任务若保存的是 `classification=blocked`，控制器会保留该触发批次的 `retryable_failed` 与原错误，同时恢复该来源熔断，后续同来源任务标记 `circuit_open` 而不再调用接口。
- 预筛产物新增独立的 `PREFILTER_RULESET_HASH` 输入身份；在线增量重建时，预筛规则变化会使产物失效并重写，而不改动稳定的冻结业绩文件。
- 停牌价格不再要求原始 Task 2 行情包含人为派生的 `last_close` 字段。原始 `tradestatus=0` 且 `close` 缺失时只接受 BaoStock 原始 `preclose`，派生记录明确保存 `effective_close`、`price_basis=suspended_preclose`、原始记录 SHA-256 与转换版本；交易中证券仍必须有 `close`，两者都缺失会阻断行情闸门。

定向红灯先暴露了离线状态命令不重建预筛产物；测试随即收紧到真实的在线增量重建路径。最终四个边界测试全部通过，Task 3 专项回归为：

```text
.venv/Scripts/python.exe -m unittest -v tests.test_curation tests.test_scoring tests.test_orchestrator
Ran 33 tests in 387.533s
OK
```

Fix round 2 复核输入哈希：

- `ashare_pipeline/orchestrator.py`: `F52719204B756FA9F0738B1500507826DD01D85D2B5ED2AC1715E243E277EDA0`
- `tests/test_orchestrator.py`: `5ED22C097FB30B4C3A12BF0C60EE50B88E9B1EAF1CB2020FC77B8E377A554B80`
- `ashare_pipeline/curation.py`: `96E441E5F9249CFE4FD6C5015614212E015EB008961A7D42AAFB22E55215192D`
- `ashare_pipeline/scoring.py`: `F62A1F6EA269D7066BC3CBE30BD8AA1AC8EAC9EDE6B6F6FC6299F4BD5B78FE5E`

## 最终复核状态

- Task 3 专项回归为 33/33 通过，独立复核结论为 `Approved`。
- Task 1 + Task 2 合计 54/54 通过且均已 `Approved`；Task 3 与其公开接口对接无未解决缺口。
- 正式评分门槛已经 fail-closed：当前 120 个候选和 120 个 partial score items 仅用于深抓排序；在截止、2026-08-31 收盘行情、正文/治理/事件、行业模板及正式 V2 七维特征全部留证前，formal scores/pools 必须保持 0。
- 真实在线数据已跨过两个 95% 数据闸门，但 `cutoff_passed=false`，因此当前正确生命周期仍是 `partial`，不是 final。

## Fix round 1 修改文件

- `ashare_pipeline/curation.py`
- `ashare_pipeline/scoring.py`
- `ashare_pipeline/orchestrator.py`
- `tests/test_curation.py`
- `tests/test_scoring.py`
- `tests/test_orchestrator.py`
- `task-3-report.md`
