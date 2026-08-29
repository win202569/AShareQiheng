# Task 3 Brief — 沪深A股整理层、增量编排与诚实预筛

先完整阅读 `PLAN.md`、`SCORING_SPEC_V2.md`、`task-2-brief.md`、`ashare_pipeline/state_store.py`。Task 2 的公开接口以 brief 为准；如果对应文件尚未出现，测试应使用协议兼容 fake，完成后再做一次真实接口对接。不得修改 Task 1/Task 2 文件，除非在报告中明确说明不可绕过的接口缺口并等控制器处理。

## 文件与命令

创建：

- `ashare_pipeline/curation.py`
- `ashare_pipeline/scoring.py`
- `ashare_pipeline/orchestrator.py`
- `tests/test_curation.py`
- `tests/test_scoring.py`
- `tests/test_orchestrator.py`
- `task-3-report.md`

公开 CLI：

```text
python -m ashare_pipeline.orchestrator --root <data_root> --db <sqlite> bootstrap [--online]
python -m ashare_pipeline.orchestrator --root <data_root> --db <sqlite> incremental [--online]
python -m ashare_pipeline.orchestrator --root <data_root> --db <sqlite> status
python -m ashare_pipeline.orchestrator --root <data_root> --db <sqlite> finalize --now-cn <ISO>
```

离线模式不访问网络；`status` 永不访问网络。CLI 输出紧凑 JSON，并原子写 `<root>/status/pipeline_status.json`。

## 整理层

实现纯函数，不依赖网络或数据库：

```python
curate_universe(records: list[dict]) -> tuple[list[dict], dict]
curate_performance(records: list[dict], universe: list[dict]) -> tuple[list[dict], dict]
quality_gate(universe: list[dict], performance: list[dict], as_of_cn: str) -> dict
```

- 宇宙只保留 BaoStock `type == '1'`、`status == '1'` 且代码为 `sh.6xxxxx` 或 `sz.[03]xxxxx` 的证券；排除 `bj.*`、上海B股 `sh.9*`、深圳B股 `sz.2*`、指数/基金/债券。输出 `security_id` 为 `SH600000`/`SZ000001`、`code6`、名称、上市日期、交易所和板块（主板/科创板/创业板）。不能按名称删除 ST，ST 仅作风险标签。
- 业绩报表必须把代码强制为六位字符串，连接证券宇宙，剔除宇宙外记录；同一代码多行时按“最新公告日期”降序保留一行，若日期相同则使用完整规范 JSON 的哈希稳定选择。保留原始字段，并增补规范英文键。
- 质量报告至少包含宇宙数、已披露唯一证券数、覆盖率、宇宙外行数、重复证券数、核心字段非空率、最新公告日期、是否存在未来公告日期。
- 正式质量闸门：只有在公告截止后、宇宙和已披露均非空、核心字段总体完整率至少95%、代码唯一、未来公告为0、8月31日行情存在时才可通过。当前截止前应返回 `status='partial'`，绝不能把未来数据缺失判为失败。

## 预筛而非正式总分

`scoring.py` 实现可审计纯函数：

```python
build_prefilter(performance: list[dict]) -> tuple[list[dict], dict]
```

- 只使用批量业绩报表中实际存在的指标，按行业内百分位（行业样本不足20只时退回全市场）计算：收入同比、净利润同比、ROE、毛利率、每股经营现金流。
- 增长代理分：收入同比与净利润同比各50%；质量代理分：ROE 40%、毛利率30%、经营现金流/股30%。百分位必须稳定处理并列、负值、缺失；缺失指标不填0，只按可用权重重新归一并降低覆盖率。
- `prefilter_score = 55% growth_proxy + 45% quality_proxy`，只用于深抓队列。每行必须包含 `coverage`、`missing_metrics`、`is_official_score=false`、`reason='仅供深抓排序，不是V2正式总分'`。
- 候选队列最多120只：先取行业内前2（有足够覆盖且不少于20只的行业），再按预筛分补齐；不得生成“强烈关注/等待价格”池。

## 编排与状态

- `bootstrap --online` 调用 Task 2 适配器获取证券主表、交易日历、披露计划和20260630业绩报表并通过 SnapshotStore/StateStore 原子持久化；离线时只初始化状态并报告 pending。
- `incremental --online` 使用内容哈希实现幂等：重新请求低频批量源，内容未变不重复产生快照；只为新披露/变更公司推进候选深抓任务。源阻断触发熔断并保留可重试状态，不能覆盖已有成功快照。
- 可从最新原始快照重建整理数据，原子写：`curated/universe.json`、`curated/performance.json`、`curated/prefilter.json`、`status/quality.json`。写入内容含 schema_version、generated_at、输入哈希、records/metrics。
- `status` 汇总 StateStore 进度和上述整理文件；不得扫描或输出原始大表全部行。
- `finalize` 使用截止 `2026-08-31T23:59:59+08:00`。只有 `now > cutoff`、8月31日行情证据和质量闸门通过才调用 StateStore final；否则返回非零、`blocked` 及具体原因，且不修改 provisional。若当前实现尚无完整七维特征，所有 score_item 必须保持 partial/blocked，绝不能冻结预筛分。
- 所有日期比较使用 timezone-aware UTC；所有写文件使用唯一 `.part` + fsync + `os.replace`。

## 测试与报告

严格 TDD。至少覆盖：A/B/北交所过滤、代码前导零、ST保留、稳定去重、未来公告、95%质量边界、行业样本回退、缺失不填0、候选上限与行业代表、离线无网络、幂等重跑、截止时刻与后一秒、无行情/无正式评分阻断、状态文件原子写。网络只由控制器后续试跑。

报告记录红灯测试、最终命令与结果、接口假设和剩余正式评分缺口。不要派生子代理。
