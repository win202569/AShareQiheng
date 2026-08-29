# Task 1 Brief — SQLite 状态库与增量状态机

先读 `work/a_share_pipeline/PLAN.md` 的全局约束。本任务只实现本简报范围，不访问网络，不安装依赖，不实现数据源适配器。

## 目录与接口

创建 Python 包 `work/a_share_pipeline/ashare_pipeline/` 和测试 `work/a_share_pipeline/tests/`。仅使用 Python 3.12 标准库。

公开接口：

```python
class StateStore:
    def __init__(self, db_path: str | Path): ...
    def initialize(self) -> None: ...
    def start_run(self, mode: str, as_of_cn: str, params: dict) -> str: ...
    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None: ...
    def enqueue_job(self, kind: str, idempotency_key: str, payload: dict) -> str: ...
    def lease_next_job(self, kinds: list[str], worker_id: str, lease_seconds: int, now_utc: str | None = None) -> dict | None: ...
    def complete_job(self, job_id: str, result: dict) -> None: ...
    def fail_job(self, job_id: str, error: dict, retryable: bool, next_retry_at: str | None = None) -> None: ...
    def recover_expired_leases(self, now_utc: str | None = None) -> int: ...
    def record_snapshot(self, source: str, dataset: str, request_fingerprint: str, payload_hash: str, payload_path: str, row_count: int, fetched_at: str) -> tuple[str, bool]: ...
    def upsert_score_item(self, score_run_id: str, security_id: str, state: str, coverage: float, input_hash: str, scores: dict | None, reasons: list[str]) -> None: ...
    def create_score_run(self, report_period: str, as_of_cn: str, ruleset_hash: str, universe_hash: str, mode: str) -> str: ...
    def finalize_score_run(self, score_run_id: str, now_cn: str, cutoff_cn: str, market_ready: bool, quality_passed: bool) -> None: ...
    def progress_snapshot(self) -> dict: ...
```

## 数据表

必须有 `run`、`job`、`source_snapshot`、`score_run`、`score_item`、`quality_issue`。SQLite 开启 foreign_keys、WAL、busy_timeout。时间字符串统一 ISO-8601 UTC；业务截止比较使用带时区 ISO 字符串转换为 datetime。

Job 状态：`pending`, `running`, `succeeded`, `retryable_failed`, `terminal_failed`。

Score run 状态：`provisional`, `final`, `invalidated`。Score item 状态：`pending`, `partial`, `ready`, `blocked`, `final`。

## 必须行为

1. 相同 `idempotency_key` 重复入队返回同一 job，不创建第二行。
2. `lease_next_job` 只能租 pending 或到期可重试任务；租约包含 worker 和到期时间；同一任务不能同时租给两个 worker。
3. retryable 失败在 `next_retry_at` 前不可租；terminal 失败永不自动重试。
4. 过期 running 租约回收为 retryable_failed，并增加可审计错误说明。
5. 相同 `(source,dataset,request_fingerprint,payload_hash)` 快照去重并返回 `(snapshot_id, created=False)`；新哈希创建新版本。
6. coverage 必须在 0–1；scores 缺失时不能把分数写为 0。
7. `finalize_score_run` 必须同时满足 `now_cn > cutoff_cn`、`market_ready=True`、`quality_passed=True`，否则抛出 `FinalizationBlocked` 且保留 provisional。
8. 已 final 的 score_run 不可原地修改；对其再次 finalize 为幂等成功，但不同输入必须由 `create_score_run` 生成新运行。
9. final 时只把 ready score_item 转 final；partial/blocked 保留状态和原因。
10. `progress_snapshot` 返回 schema_version、各 job/score 状态计数、最近运行、更新时间，不泄露 payload 大字段。

## 测试与证据

严格 TDD：先写 `unittest`，运行并记录预期失败，再写最小实现。至少覆盖上述10项、数据库重开后可恢复、两连接租约竞争、截止时区边界和非法状态。

报告写入 `work/a_share_pipeline/task-1-report.md`，包含：失败测试命令与失败原因、最终测试命令与完整计数、创建文件、设计取舍、未解决问题。不要派生任何子代理。
