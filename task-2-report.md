# Task 2 Report — 免费数据源适配、原子快照与试采 CLI

## 完成范围

- 实现 `FetchBatch` 的规范 JSON、日期/NaN/NaT 处理和 SHA-256 内容哈希。
- 实现可注入的 BaoStock、AKShare 适配器；可选依赖只在实例首次在线使用时动态导入。
- 实现内容寻址的原子 raw snapshot 写入：同目录唯一 `.part`、`flush`/`fsync`、`os.replace`、重读哈希校验和去重。
- 实现离线安全的 `python -m ashare_pipeline.pilot`，以及在线试采的独立幂等 job、快照登记和 spot 可重试降级。

## TDD 证据

测试先于对应修复编写并观察失败：

1. `test_online_rerun_does_not_refetch_successful_jobs_and_spot_failure_is_nonblocking` 初次失败：证券主表在第二次运行被访问两次（`2 != 1`）。修复为每个试采任务使用独立 job kind，成功任务不再重复访问源；spot 的 retryable failure 仍会被重试。
2. `tests.test_sources` 的新增用例初次失败：BaoStock login 的 `403` 被错误归类为 retryable，且业绩表保留了非核心字段。修复后分别熔断为 `SourceBlocked`，并仅保存指定核心业绩字段。

最初直接使用 `python`/`py` 的测试命令失败，原因是 PATH 未配置解释器；使用随附运行时后完成实际执行。

## 验证

通过命令：

```powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_sources tests.test_snapshot_store tests.test_pilot -v
```

结果：`Ran 13 tests ... OK`。

全量发现命令运行了 34 个可加载测试；Task 2 与 Task 1 测试均通过，但整体以非本任务错误退出，因为现有 `tests/test_curation.py` 导入尚不存在的 `ashare_pipeline.curation`。本任务未修改该文件或补建该模块。

## 创建文件

- `ashare_pipeline/sources.py`
- `ashare_pipeline/snapshot_store.py`
- `ashare_pipeline/pilot.py`
- `tests/test_sources.py`
- `tests/test_snapshot_store.py`
- `tests/test_pilot.py`
- `task-2-report.md`

## 控制器执行在线试采的命令

在已显式安装且锁定 `akshare==1.18.94`、`baostock==0.9.3` 的环境中运行：

```powershell
python -m ashare_pipeline.pilot --root <data_root> --db <sqlite_path> --online --symbols SH600000,SZ000001,SZ300750,SH688001,SZ002594,SH601318
```

不带 `--online` 时只初始化 SQLite 状态库并写 `pilot_status.json`，不导入可选数据包、也不访问网络。

## 风险与未解决项

- 未执行真实在线试采：按任务约束没有安装依赖或访问网络；真实端点列名/限流行为需要由控制器在受控环境复核。
- 403、429、验证码与 HTML 响应会熔断，不会尝试绕过访问控制。
- 试采的交易日历调用将当前未收盘/未来日期记为 pending；完整的市场假日判定仍应以 BaoStock 返回的交易日历为准。

## Fix round 1（审阅修复）

### TDD 红/绿证据

新增测试先运行并确认失败：

- `tests.test_sources tests.test_snapshot_store tests.test_state_store -v`：9 个预期失败/错误，覆盖 403/429 标量误熔断、真实 AKShare 业绩字段未映射、缺失列未失败、未调用 sleeper、观察时刻影响哈希、损坏快照被错误去重、未校验 `.part`，以及缺少 `StateStore.get_job`。
- `tests.test_pilot -v`：4 个预期错误，显示 `_run_online` 尚不接受受控时间，因而未实现交易日日历证据、租约恢复、熔断/状态重用与原子状态文件流程。

最小修复后，Task 1 + Task 2 合集命令通过：

```powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_state_store tests.test_sources tests.test_snapshot_store tests.test_pilot -v
```

结果：`Ran 47 tests ... OK`。

### 修复内容

- HTTP 状态只在异常、登录和 BaoStock 查询错误上下文中解释；DataFrame 单元格仅识别 HTTP 挑战、验证码或 HTML，不把序号 `403/429` 或代码 `000403/000429` 当成阻断。
- 将 AKShare 1.18.94 的四个带前缀业绩列显式映射为稳定字段，保存映射证据；缺少必填列时终止失败。
- 内容 SHA 不再含观察时刻；快照跨观察日期去重，并保留第一次落盘的时刻。写入前后均验证，损坏既有目标和无效 `.part` 均拒绝。
- 新增 `StateStore.get_job` 公共只读 API；pilot 在开始时回收过期租约，重用时回显既有批次详情并如实报告 running/retryable/terminal 状态，未知异常转 retryable failure。
- pilot 以 BaoStock 日历选择最近已完成交易日，持久化请求日期状态、日历证据和交易日；各 idempotency key 绑定上海 as-of 日期。
- 同一源遭 `SourceBlocked` 后，本轮余下任务标为 `blocked_by_circuit`；另一源继续执行。
- `pilot_status.json` 使用唯一同目录 `.part`、flush/fsync、replace 原子写入并在异常时仅清理本次 part；生成时刻使用 UTC。

### Fix round 1 修改文件

- `ashare_pipeline/sources.py`
- `ashare_pipeline/snapshot_store.py`
- `ashare_pipeline/pilot.py`
- `ashare_pipeline/state_store.py`（控制器授权的 `get_job` 最小只读接口）
- `tests/test_sources.py`
- `tests/test_snapshot_store.py`
- `tests/test_pilot.py`
- `tests/test_state_store.py`
- `task-2-report.md`

## Fix round 2（审阅修复）

### TDD 红/绿证据

新增 pilot 红测首次运行：`Ran 11 tests`，其中 3 个失败、1 个错误，分别暴露原始行/metadata 泄露到公开状态、旧日期 retryable job 被新日期任务租走、同日 SourceBlocked 未重建熔断、以及日历失败时财务三表被跳过。

修复后执行：

```powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_state_store tests.test_sources tests.test_snapshot_store tests.test_pilot -v
```

结果：`Ran 51 tests ... OK`。

### 修复内容

- pilot/job/status/stdout 的批次摘要只保留 dataset/source、行数、内容 hash、source version、快照路径、抓取时刻和 request fingerprint；原始 records 与 metadata 只存在 content-addressed snapshot。交易日历从刚写入或复用的快照内部读取，只公开最多 10 条日期/交易标志证据。
- job kind 现在包含完整 task + Shanghai as-of identity，旧日期 retryable/pending 任务不能被新日期任务租走或错误完成。
- failure error 以 `classification`/`message` 结构化保存。复用同日 blocked terminal job 时，立即恢复源级熔断，后续同源任务不会被调用。
- 财务三表任务仅受 AKShare circuit 影响；BaoStock 日历失败、空或 blocked 时，只跳过 daily，仍尝试代表股票三表。
- BaoStock 的所有单元测试注入 no-delay sleeper，不在测试中真实 sleep。

### Task 3 集成检查

按修复包要求运行：

```powershell
& '...python.exe' -m unittest tests.test_orchestrator tests.test_scoring tests.test_curation -v
```

结果：`Ran 29 tests`，22 通过、7 失败。失败均为 `tests/test_orchestrator.py` 的现有 Task 3 curated 文档/运行结束/恢复状态断言（例如缺少 `curated.universe`、`recovered_expired_leases`、post-cutoff 文件）；本轮明确禁止修改 Task 3/4，未跨范围处理。

### Fix round 2 修改文件

- `ashare_pipeline/pilot.py`
- `tests/test_pilot.py`
- `tests/test_sources.py`
- `task-2-report.md`

## Fix round 3（窄范围审阅修复）

### TDD 红/绿证据

新增 pilot 测试首次运行：`Ran 14 tests`，2 个失败、1 个错误。红灯证明同日复用的 blocked trigger 被错误报告为 `blocked_by_circuit` 而丢失 terminal classification、复用日历快照未核验 hash、成功摘要缺少 task key。

最小修复后 pilot 测试 `Ran 14 tests ... OK`；随后 Task 1+2 集合通过：

```powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_state_store tests.test_sources tests.test_snapshot_store tests.test_pilot -v
```

结果：`Ran 54 tests ... OK`。

### 修复内容

- 同日已存在的 `SourceBlocked` terminal trigger 会先重开对应 source circuit，但该触发任务本身返回真实 `terminal_failed`、结构化 `classification=blocked` 和原因；仅后续同源任务报告 `blocked_by_circuit`。
- 增加真实 `pilot_fetch:<task-key>` 的租约生命周期覆盖：租约未过期时如实报告 running、不调用远端；过期后恢复、重租、抓取并完成同一 job。
- 周末日历回退到最近交易日（2026-08-30 选择 2026-08-28），daily 请求使用该日期。
- 复用交易日历快照前，按摘要记录的 hash 重建 `FetchBatch` 并验证；不匹配则不用于日线日期选择。
- 批次摘要加入安全的 `task_key` 和 `job_id`，保持日线/三表可归因，且不泄露 request/records/metadata。

### Fix round 3 修改文件

- `ashare_pipeline/pilot.py`
- `tests/test_pilot.py`
- `task-2-report.md`
