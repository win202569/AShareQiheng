# Task 4 报告 — 审计型进度报告生成器（Fix Round 2）

## 结果

已实现并完成第二轮窄范围修复的 `ashare_pipeline.reporting.build_progress_artifact(...)` 会输出 canonical Data Analytics `report` artifact，顶层仅含 `surface`、`manifest`、`snapshot`、`sources`。`ready` 现为 fail-closed：只有公告截止、2026-08-31 收盘行情、披露覆盖率与核心完整率两个 95% 闸门、治理/事件核验、正式 V2 七维特征/分数、可审计 final marker 全部通过，且强烈关注池和等待价格池数量均被明确提供时才成立；两个池都为 0 是合法最终结果，计数缺失或闸门矛盾则不得 `ready`。

本任务选择技术受众和 portable HTML 的 canonical artifact 输入模式。按 brief 边界，本任务只生成并验证 artifact，不生成或打包最终 HTML，也未联网。

## Fix Round 1 七项修复

1. **直接消费 Task 3 真实状态。** 支持 `curated.prefilter`、`source_errors`、`circuit_breakers`、`blocked_reasons`、`next_actions`；缺失批次来源时按已知数据集安全推断 BaoStock 或 AKShare。新增真实 `orchestrator.run_command(..., "status")` 载荷集成测试，失败与阻断信息在报告中可见，而不是被忽略。
2. **拆分两个 95% 口径。** “已披露合格证券覆盖率”定义为唯一已披露合格证券数除以合格证券宇宙数；“五个必需核心单元格完整率”定义为非空核心单元格数除以已披露合格证券数乘 5。两者分别展示、分别过闸，不再共用业绩快报覆盖率。
3. **落实 Markdown 单一来源规则。** 每个含数字、百分比或敏感度参数的 Markdown 块都只引用一个正确的 canonical source；不同来源的定量陈述拆成独立块。
4. **让 25 行截断可审计。** `source_status_meta` 明确审阅行数、展示行数、是否截断和选择规则；失败、阻断、可重试记录优先保留，表格副标题和 source filters 同时说明截断状态。
5. **递归脱敏。** 在读取字段前递归清洗映射、列表、元组和字符串，覆盖 Windows 盘符路径、UNC、常见 POSIX 绝对路径、URL 凭证、查询令牌、Bearer/Basic、JSON/键值形式的密码与令牌。报告明确这是“已知模式脱敏”，不能保证识别所有秘密；原始任务载荷、个股明细和未知大字段不进入 artifact。
6. **生命周期改为证据驱动。** 截止前强烈关注池、等待价格池和正式合计均为 0；截止后缺少市场或评分证据时为 `blocked` 并展示具体原因；Fix Round 2 进一步要求全部发布闸门、可审计 final marker 和显式两池计数同时成立才可 `ready`。计数缺失或任一闸门失败时保持非 ready。
7. **保持兼容、边界与确定性。** 所有卡片、图表、表格仍解析到 canonical source 和可执行 SQL；每个 snapshot dataset 不超过 25 行，总行数不超过 75；输出除生成时间字段外保持确定性。

## 报告结构

当前有序阅读路径包含：

1. 与 `manifest.title` 完全一致的可见 `#` 标题；
2. 技术摘要，说明 V1 重复计分/周期顶部陷阱、V2 修正和当前生命周期；
3. 九张工程状态卡，分别展示测试、批次、行数、证券宇宙、已披露覆盖率、预筛候选和三个正式池数量；
4. 七维权重、角色和缺失处理表及唯一一张权重结构图；
5. 免费源/数据集状态表与独立截断元数据；
6. 来源错误、熔断器、阻断原因、预筛与下一步的运行状态表；
7. 六道正式发布闸门表，其中两个 95% 闸门使用不同分母；
8. 方法限制与稳健性表、下一步和可进一步回答的问题。

V2 用户展示口径已固定为成长、估值、风险和买点四个 0–100 分等级，风险分越高代表越安全。正式候选还必须核验财报正文、审计/审阅意见和临时公告，并使用行业专门模板、行业内标准化及权重/阈值敏感度检查。

## 可视化取舍

采集进度是单点工程快照，趋势图不会增加信息，因此进度本身使用卡片与表格。canonical report validator 要求至少一个原生 chart block；报告保留一张“七维评分权重结构”图，只解释规则结构，不表示采集趋势或投资结果，并与精确权重表及解释段落相邻。

## 来源与数据边界

- 每张原生卡片、图表和表格都有可解析 `sourceId`。
- 每个被引用 source 都包含 description、filters、metric_definitions 和实际可执行 SQL。
- 生成器用内存 SQLite 的 `SELECT ... UNION ALL` 物化小型审阅数据集，并把同一 SQL 写入 source metadata，避免伪造查询。
- 文件来源只接受安全相对路径；绝对路径和父目录跳转会被拒绝。
- `source_status` 和 `operational_status` 各最多 25 行；每个 dataset 不超过 25 行，snapshot 合计不超过 75 行。
- Fix Round 2 artifact 包含 9 个 bounded snapshot datasets 和 8 个 canonical sources；生命周期与运行状态审计元数据均为独立有界数据集。

## TDD 证据

Fix Round 1 先扩展到 21 项专项测试，首次运行结果为 14 项通过、7 类失败/错误，分别对应：真实生产者载荷、完整运行状态字段、双 95% 口径、定量 Markdown 单一来源、截断可审计性、递归脱敏和三态生命周期。随后逐项实现，未先改生产代码绕过红灯。

专项测试命令：

```text
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_reporting.py' -v
```

结果：21/21 通过。

全量回归命令：

```text
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

结果：106/106 通过。

Fix Round 1 时，官方 `validate_artifact` 曾分别使用代表性的 `partial`、`blocked`、`ready` 输入复核：

```json
[
  {"case":"partial","ok":true,"surface":"report","status":"partial","datasets":7,"sources":7},
  {"case":"blocked","ok":true,"surface":"report","status":"blocked","datasets":7,"sources":7},
  {"case":"ready","ok":true,"surface":"report","status":"ready","datasets":7,"sources":7}
]
```

## Fix Round 2 最终状态

- 专项测试为 22/22 通过。
- `ready` 改为 fail-closed；状态名或任意非空字符串、布尔值、字典不再足以证明 final。闸门矛盾、final marker 不可审计或两池计数缺失时均不得 ready。
- pre-cutoff blocked 与 post-cutoff blocked 已分开：截止前保持 partial/pre-cutoff 文案并展示实际尝试阻断原因；截止后才使用“截止后阻断”表述。
- 新增独立、可复算、bounded 的 lifecycle dataset/source；生命周期 Markdown 绑定该 source，而不是绑定缺少状态字段的指标 SQL。
- 路径脱敏覆盖任意 Windows 盘符、UNC 与 POSIX 本机绝对路径，同时保留合法公共 `http://`、`https://` URL。
- operational rows 优先保留正式发布阻断，再展示熔断/错误和下一动作；完整审阅数、展示数、截断标记和选择规则同时进入元数据、表格副标题与 source filters。
- canonical artifact 当前为 9 datasets、8 sources。

## 独立复核状态

曾两次启动 Fix Round 2 独立复核，但 reviewer 都因 Windows runner 在读取输入前发生 `spawn_ready` 超时而未能形成技术 verdict。这不是代码审查通过，因此 Task 4 当前只能记录“实现与专项测试完成”，**不能称为 `Approved`**。后续 runner 恢复后仍应重新执行独立只读复核。

## 修改范围与后续动作

本轮只修改 Task 4 文件：

- `ashare_pipeline/reporting.py`
- `tests/test_reporting.py`
- `task-4-report.md`

真实试采后由控制器把 Task 3 状态与质量证据传给报告生成器并保存 `artifact.json`；最终 HTML 打包仍属于总任务的交付阶段，不在本任务中提前执行。报告仅用于研究筛选，不构成投资建议。
