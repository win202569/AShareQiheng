# Task 4 Brief — 审计型进度报告生成器

本任务生成“当前方法与采集进度”的技术报告，不生成股票推荐。先读 `PLAN.md`、`SCORING_SPEC_V2.md`、`progress.md`，以及 `data-analytics:build-report` 的 `SKILL.md`、`specifications/technical-report.md`、共享 `src/analytics-app-core.md`。选择 portable HTML 报告模式；本任务只生成规范 `artifact.json`，最终 HTML 由控制器在真实试采后用官方 delivery 脚本打包。

## 文件

创建：

- `ashare_pipeline/reporting.py`
- `tests/test_reporting.py`
- `task-4-report.md`

公开接口：

```python
build_progress_artifact(
    pipeline_status: dict,
    quality: dict | None,
    pilot_status: dict | None,
    generated_at: str,
    plan_path: str,
    scoring_spec_path: str,
) -> dict
```

返回 canonical Data Analytics artifact 顶层：`surface`、`manifest`、`snapshot`、`sources`；surface/manifest.surface 均为 `report`，snapshot status 在当前截止前为 `partial`。不得包含本机绝对路径、凭证、原始大表或个股未经验证的投资分数。

## 报告结构

技术受众，块顺序：

1. 匹配 manifest.title 的 `#` 标题；
2. 技术摘要：V1不完美，V2解决利润重复计分/周期顶部陷阱；当前仅采集和预筛，正式评分未冻结；
3. 指标卡：状态库测试数、数据批次数、已抓取行数（如有）、股票宇宙数（如有）、业绩覆盖率（如有）、正式股票池数量（截止前必须为0）；
4. 评估维度表：七维、权重、角色、缺失时处理；
5. 当前数据源/数据集状态表；
6. 发布闸门表：公告截止、8/31收盘、完整率≥95%、治理/事件核验、七维特征齐备；
7. 限制、稳健性和下一步；
8. 可进一步回答的问题。

没有时间序列或可解释比较时不画图，在限制块明确“当前是单点工程快照，图表不会增加信息，因此使用卡片与表格”。

## 数据与来源规则

- 每张卡/表必须有 sourceId 或 inline source；source 元数据使用安全相对路径或公开 HTTPS 链接。
- source query 的 description、filters、metric_definitions 写清口径；文件来源用相对 path，例如 `work/a_share_pipeline/progress.md`，不得写 `C:\...`。
- snapshot.datasets 只放界面需要的小型已审阅行；大数字使用数值，不预先字符串化。
- 只展示证据中存在的值；缺失保持 null/“待采集”，不填0。例外：正式股票池数量在截止前为0是状态事实。
- snapshot.accessIssues 显示：报告仍为 partial、8/31尚未到/未冻结、免费结构化源无SLA、预筛不是正式评分。
- 任何评分建议必须带“研究筛选，不构成投资建议”。

## 验证

严格 TDD。测试至少覆盖：顶层shape、标题匹配、partial显著提示、七维权重合计100、正式池为0、缺失不伪造、无绝对路径/凭证、每张卡表均可解析来源、每个peer section单独markdown block、有限数据集、确定性（仅 generated_at 可变）。不要调用网络，不打包HTML，不派生子代理。
