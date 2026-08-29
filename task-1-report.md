# Task 1 实施报告：SQLite 状态库与增量状态机

## 范围

实现 `StateStore`（仅 Python 3.12 标准库），包括 SQLite schema、可恢复 job 租约状态机、快照内容哈希去重、评分运行发布闸门和不含 payload 的进度快照。未访问网络、未安装依赖、未实现数据源适配器。

## TDD 证据

先创建 `tests/test_state_store.py`（15 个 `unittest`）。首次可执行测试命令为：

```powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

预期失败：`ModuleNotFoundError: No module named 'ashare_pipeline.state_store'`。这是因为状态库实现尚不存在。环境 PATH 中没有 `python` 命令，因此使用工作区提供的 Python 3.12 可执行文件运行测试，未安装任何软件包。

最终验证命令：

```powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile ashare_pipeline\__init__.py ashare_pipeline\state_store.py
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

结果：编译命令退出码 0；`Ran 15 tests in 0.339s`，`OK`，0 failures、0 errors。

## 覆盖的行为

- 幂等 job 入队；租约的原子领取、两连接竞争、可重试等待、终止失败不重试、过期租约审计回收与数据库重开恢复。
- `(source, dataset, request_fingerprint, payload_hash)` 快照去重及新内容版本。
- coverage 约束与缺失 scores 保存为 SQL `NULL`；非法状态拒绝。
- 严格大于带时区截止时间的发布判断、行情/质量闸门、ready-only final、finalize 幂等与 final 运行不可修改。
- JSON 进度快照的 schema 版本、状态计数、最近运行、更新时间及 payload 排除。

## 设计取舍

- 每个操作使用独立 SQLite 连接，并为每个连接启用 `foreign_keys`、WAL 和 `busy_timeout`；领取与回收使用 `BEGIN IMMEDIATE`，避免两个 worker 同时取得同一任务。
- 数据库中由本库生成的时间规范化为带 `+00:00` 的 ISO-8601 UTC；`finalize_score_run` 以带时区的 datetime 比较业务时间边界。
- 按全局计划补充了未公开暴露的 `artifact` 表，且实现了简报要求的 `run`、`job`、`source_snapshot`、`score_run`、`score_item`、`quality_issue` 表。

## 创建/修改文件

- `ashare_pipeline/__init__.py`
- `ashare_pipeline/state_store.py`
- `tests/test_state_store.py`
- `task-1-report.md`

## 未解决问题

无。后续 Task 2/3 可在调用端为 `quality_issue` 和 `artifact` 写入增加领域级 API；这不属于本任务指定的公开接口。

## Fix round 1（审阅修复）

### 新增红灯测试与失败证据

先在同一 `tests/test_state_store.py` 新增 6 个行为测试，再运行：

```powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

结果：`Ran 21 tests`，`FAILED (failures=3, errors=1)`，均为预期缺失行为：

- `start_run`/`create_score_run` 未拒绝 naive `as_of_cn`，且未将 `+08:00` 规范为 `+00:00`。
- provisional score run 可直接写入 `state='final'`。
- `finalize_score_run` 不接受 `market_evidence`，也没有证据审计列。
- `progress_snapshot.updated_at` 未纳入 `run.finished_at`、`artifact` 与 `quality_issue`。

真实线程+屏障租约竞争测试，以及不同时区偏移下“同一绝对时刻阻止、刚超过截止可 final”的边界测试，在红灯轮中已通过，确认原子租约和 aware datetime 比较没有回归。

### 修复内容

- `start_run` 与 `create_score_run` 现在通过统一 UTC 解析器拒绝无时区输入，并将持久化值规范为 ISO-8601 UTC。
- provisional score run 禁止直接写入 `final` score item；只有 `finalize_score_run` 能执行 ready → final。
- schema 版本提升至 2；`score_run` 增加 `cutoff_utc`、两项闸门布尔值及 market/quality evidence JSON，并为已有数据库执行无损列迁移。
- `finalize_score_run` 新增可选 `market_evidence`、`quality_evidence` 参数（默认空字典，旧调用兼容），在同一事务内保存最终闸门和证据；final run 的重复调用继续幂等返回。
- `progress_snapshot.updated_at` 现在聚合 job、score item、run 启动/结束、score run 创建/final、source snapshot、artifact、quality issue 的所有时间字段。

### 最终验证

```powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile ashare_pipeline\__init__.py ashare_pipeline\state_store.py
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

结果：编译退出码 0；`Ran 21 tests in 0.527s`，`OK`（0 failures、0 errors）。
