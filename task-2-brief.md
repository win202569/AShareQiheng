# Task 2 Brief — 免费数据源适配、原子快照与试采 CLI

先读 `work/a_share_pipeline/PLAN.md`、`work/a_share_pipeline/task-1-brief.md` 的公开状态库接口，以及当前 `ashare_pipeline/state_store.py`。本任务不得修改 Task 1 文件，除非控制器在审阅通过后明确要求。

## 新文件与公开接口

创建：

- `ashare_pipeline/sources.py`
- `ashare_pipeline/snapshot_store.py`
- `ashare_pipeline/pilot.py`
- 对应 `tests/test_sources.py`、`tests/test_snapshot_store.py`、`tests/test_pilot.py`

只在 CLI 运行时导入可选依赖 `akshare==1.18.94`、`baostock==0.9.3`；测试使用完整结构的 fake module，不访问网络。

### 统一批次

```python
@dataclass(frozen=True)
class FetchBatch:
    source: str
    dataset: str
    request: dict
    records: list[dict]
    fetched_at_utc: str
    source_version: str
    metadata: dict

    def canonical_bytes(self) -> bytes: ...
    def sha256(self) -> str: ...
```

规范 JSON 使用 UTF-8、排序键、稳定分隔符；NaN/NaT 转 null，datetime/date 转 ISO 字符串，证券代码保留前导零。

### 错误

```python
class SourceError(RuntimeError): ...
class RetryableSourceError(SourceError): ...
class TerminalSourceError(SourceError): ...
class SourceBlocked(SourceError): ...  # 403/429/验证码/异常HTML，调用方应熔断
```

### BaoStockSource

接受可注入 `module`、`clock` 和 `sleeper`。公开方法：

```python
fetch_security_master() -> FetchBatch
fetch_trade_dates(start_date: str, end_date: str) -> FetchBatch
fetch_daily(code: str, start_date: str, end_date: str) -> FetchBatch
```

- 每次公开方法独立完成匿名 `login()`/`logout()`，`logout()` 放在 finally；非零 error_code 转为 RetryableSourceError。
- 证券主表来自 `query_stock_basic()`，保留原始全部类型，metadata 提供 type/status 计数；不在适配器里决定沪深A股范围。
- 日线固定 `frequency='d'`、`adjustflag='3'`，字段固定为：`date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST`。
- 返回字符串可原样保留，数值规范化在后续 curated 层完成；空结果是成功批次，不等于网络失败。

### AKShareSource

接受可注入 module、clock。公开方法：

```python
fetch_disclosure_schedule() -> FetchBatch
fetch_performance_report(report_period: str = '20260630') -> FetchBatch
fetch_financial_statements(symbol: str, report_period: str = '2026-06-30') -> dict[str, FetchBatch]
fetch_cninfo_halfyear_disclosures(symbol: str, start_date='20260701', end_date='20260831') -> FetchBatch
fetch_spot_snapshot() -> FetchBatch
```

- 披露表调用 `stock_report_disclosure(market='沪深京', period='2026半年报')`，保留5550行级来源结果；范围过滤由编排器处理。
- 全市场业绩表调用 `stock_yjbb_em(date='20260630')`，保存核心字段：代码、简称、EPS、营业总收入及同比、净利润及同比、每股净资产、ROE、每股经营现金流、毛利率、行业、最新公告日期。该批次用于全市场预评分和候选排序，不替代候选完整三表。
- 三表分别调用 `stock_balance_sheet_by_report_em`、`stock_profit_sheet_by_report_em`、`stock_cash_flow_sheet_by_report_em`；symbol 为 `SH600000`/`SZ000001`。输出保留全部返回行并在 metadata 记录目标报告期匹配行数、列数和 `NOTICE_DATE/UPDATE_DATE`。
- 巨潮元数据调用 `stock_zh_a_disclosure_report_cninfo(symbol='000001', market='沪深京', category='半年报', ...)`；只保存公告元数据/链接，不下载PDF。
- 即时快照调用 `stock_zh_a_spot_em()`，远端断开或空结构视为 RetryableSourceError；出现403/429/验证码/异常HTML视为 SourceBlocked。
- pandas DataFrame 转 records 时必须处理 NaN、NaT、Timestamp 和 date；测试 fake 必须镜像真实列结构的最小完整样本。

### SnapshotStore

```python
class SnapshotStore:
    def __init__(self, root: str | Path): ...
    def write(self, batch: FetchBatch) -> tuple[Path, str, bool]: ...
```

- 路径：`raw/{source}/{dataset}/{YYYY-MM-DD}/{sha256}.json`。
- 先写同目录唯一 `.part`，flush+fsync，再 `os.replace`；相同哈希不重写并返回 created=False。
- JSON 包含 schema_version、批次全部元数据与 records；写入后重读验证哈希。异常时清理本次 `.part`，不得删除既有文件。

### pilot CLI

```text
python -m ashare_pipeline.pilot --root <data_root> --db <sqlite> [--online] [--symbols SH600000,SZ000001,SZ300750,SH688001,SZ002594,SH601318]
```

- 无 `--online` 只检查依赖、初始化状态库并输出 JSON，不访问网络。
- `--online` 依次抓 BaoStock证券主表、2026-08-24至最近已完成交易日交易日历、AKShare披露表、20260630全市场业绩表、代表股票日线及三表；每个成功批次原子落盘并调用 `record_snapshot`，每一步使用幂等 job。
- 当前/未来日期由 Asia/Shanghai 交易日收盘规则确定：当天15:30之前不视为完成；未来日期记录 pending，不能当作空数据失败。
- AKShare spot 失败只记 retryable_failed，不阻断 BaoStock/披露表/三表试采。
- 输出 `pilot_status.json`，包括版本、批次、行数、哈希、成功/失败、下一步；不得输出完整数据或凭证。

## TDD与报告

严格先测试失败、再最小实现。覆盖：稳定哈希、NaN/日期规范化、前导零、BaoStock finally logout、空结果、错误分类、三表目标期元数据、spot降级、原子写/去重/part清理、离线CLI不联网、未来/未收盘日期pending、第二次运行幂等。

报告写 `work/a_share_pipeline/task-2-report.md`，记录首次失败、最终单测、在线试采由控制器执行所需命令、文件和风险。不要派生子代理。
