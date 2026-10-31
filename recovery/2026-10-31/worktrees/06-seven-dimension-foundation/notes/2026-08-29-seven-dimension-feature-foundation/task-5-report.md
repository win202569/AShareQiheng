# Task 5 实施报告：Owned Leases and Atomic Follow-Up Jobs

## 范围与提交

- 提交：`ed3a2d7 feat: add owned leases and atomic follow-up jobs`
- 已提交文件仅有：`ashare_pipeline/state_store.py`、`tests/test_state_store.py`。
- 本报告按简报要求不提交。
- 未实现 Task 10 的 deep 编排、远端抓取或批量展开路径；所有测试仅使用临时 SQLite 数据库，未读写 `data/state.sqlite3` 或其他 `data/` 状态。

## RED 证据

先添加 Task 5 的租约 owner、续租边界、wrong/stale worker、完成/失败事务回滚、follow-up 幂等冲突、规范 JSON、非有限数拒绝、过滤排序和 legacy 兼容测试，再运行简报指定的两个目标测试。

隔离 worktree 没有自己的 `.venv`，首次按简报相对路径执行只得到 PowerShell “命令不存在”，未将环境错误计作 RED。随后使用仓库根的同一虚拟环境解释器运行：

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_state_store.StateStoreTestCase.test_renew_job_lease_requires_current_unexpired_owner tests.test_state_store.StateStoreTestCase.test_statement_completion_and_feature_followup_are_one_transaction -v
```

结果：`Ran 2 tests`，`FAILED (errors=2)`；两项均在导入时因缺少公开 `JobSpec` API 报 `ImportError`，符合 missing API RED。

## GREEN 实现

- 新增 `@dataclass(frozen=True) JobSpec`。
- `renew_job_lease()` 拒绝非正租期，仅允许 `running`、当前 owner 且 `lease_expires_at > now` 的任务续租。
- `complete_job_with_followups()` 和 `fail_job_with_followups()` 在单个 `BEGIN IMMEDIATE` 中先验证当前未过期 owner，再幂等插入 follow-up，最后转换父任务；wrong worker、过期 owner、已完成任务均不能转换。
- follow-up payload 使用既有 canonical JSON（UTF-8 保留、键排序、紧凑分隔符、`allow_nan=False`）。同 key 且 kind/payload 完全一致时复用；kind 或 payload 任一冲突时 fail closed 并回滚父任务与本事务已插入项。
- `list_jobs()` 的 kind 过滤全部使用 SQL 参数，空 kind 列表返回空，并固定按 `created_at, id` 排序。
- 既有 `enqueue_job()` 的重复 key 返回原 ID 契约未改；既有无 worker `complete_job()`/`fail_job()` 保持原行为。严格冲突检测只用于新 atomic follow-up 路径。

## Owner、回滚与幂等证据

- owner：测试覆盖正确 owner 续租、错误 owner 拒绝、到期边界拒绝、completed 拒绝、wrong/stale worker 不能 complete/fail。
- completion rollback：触发器拒绝 `feature_build` 插入后抛 `sqlite3.IntegrityError`；父任务仍为 `running`，follow-up 列表为空。
- failure rollback：同样的触发器失败后父任务仍为 `running`、error 仍为空、follow-up 列表为空。
- idempotency：同一 `JobSpec` 在一个 follow-up 序列重复两次只产生一行；存储 payload 为规范 JSON。预存同 key 后，payload 冲突和 kind 冲突都抛 `ValueError`，父任务保持 `running`，原任务内容不变。
- 非有限数：follow-up payload 含 `NaN` 时抛 `ValueError`，父任务与 follow-up 插入一并回滚。

## 最终验证

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_state_store -v
```

结果：`Ran 55 tests in 1.038s`，`OK`。

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_state_store tests.test_sources tests.test_snapshot_store tests.test_pilot -v
```

结果：Task 1+2 回归 `Ran 87 tests in 2.720s`，`OK`。

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m py_compile ashare_pipeline\state_store.py tests\test_state_store.py
git -c safe.directory='D:/Projects/AShareQiheng/.worktrees/seven-dimension-foundation' diff --check -- ashare_pipeline/state_store.py tests/test_state_store.py
```

结果：两项均退出码 0；提交前 diff 名单仅为两个目标文件。

## 遗留风险

- 为保持 Task 1 的公开兼容性，legacy `enqueue_job()` 仍会对同 key 的不同 payload 返回原任务；新 follow-up 原子 API 已在其自身边界严格拒绝这类冲突。未来调用方不得绕过 atomic API 来建立 deep follow-up。
- `frozen=True` 阻止替换 `JobSpec` 字段，但 Python 的 `dict` payload 本身仍是可变对象；调用方应在创建后把它视为不可变，并避免跨线程修改。
- deep worker 对新 owner-specific API 的实际接线属于后续任务，本任务没有越界修改现有 pilot/orchestrator 调用。

## Independent Review 修复轮

### 提交

- `95d2f56 fix: harden owned job transitions`
- 提交范围仍严格只有 `ashare_pipeline/state_store.py` 和 `tests/test_state_store.py`；本报告继续不提交。

### RED 证据

先添加四个真实行为测试，再运行：

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_state_store.StateStoreTestCase.test_job_spec_payload_is_a_stable_construction_snapshot tests.test_state_store.StateStoreTestCase.test_owned_kinds_reject_ownerless_legacy_transitions_after_release tests.test_state_store.StateStoreTestCase.test_strict_success_clears_recovered_failure_fields tests.test_state_store.StateStoreTestCase.test_legacy_success_clears_recovered_failure_fields -v
```

结果：`Ran 4 tests`，`FAILED (failures=6)`：

- 修改构造时原始 payload 的嵌套 dict/list 会改变 `JobSpec.payload`；
- `deep_financial`、`deep_statement`、`feature_build` 三类任务在 A 租约过期、回收并由 B 重租后，ownerless legacy `complete_job()` 都未拒绝；
- 严格成功与 legacy 成功都保留旧 `lease_expired` error。

这些失败均来自审查指出的生产缺陷，无导入、语法或测试夹具错误。

### GREEN 修复

- `JobSpec(kind, idempotency_key, payload)` 的公开调用方式和 frozen dataclass 语义不变；构造时把 payload 固化为私有 canonical JSON 快照，公开 `.payload` 每次返回完整反序列化副本，atomic follow-up 插入只读取构造快照。修改原始 dict、返回副本、嵌套 dict 或 list 均不能改变规格或最终入库 JSON。
- ownerless legacy complete/fail 在 `BEGIN IMMEDIATE` 内检查任务 kind；对 `deep_financial`、`deep_statement`、`feature_build` 明确拒绝，因而不能清空 B 的租约或改写 running 状态。非 owned kind 继续保留 Task 1 旧调用方式。
- 严格与 legacy 的所有 success UPDATE 同时设置 `last_error_json=NULL`、`next_retry_at=NULL`；租约过期恢复后由新 owner 成功完成时不再出现 `succeeded + lease_expired error` 矛盾状态。
- 既有“completed 不可续租”测试原先用 ownerless legacy API 完成 `deep_statement` 作为夹具；按新契约改为非 owned `fetch`，测试目标与断言不变。

### 最终状态证据

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_state_store -v
```

结果：`Ran 59 tests in 1.681s`，`OK`。

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_state_store tests.test_sources tests.test_snapshot_store tests.test_pilot -v
```

结果：既有 Task 1+2 宽回归 `Ran 91 tests in 10.603s`，`OK`。

`py_compile ashare_pipeline/state_store.py tests/test_state_store.py` 与目标文件 `git diff --check` 均退出码 0；提交前 diff 名单仅含两个目标文件。

额外运行 `unittest discover -s tests -v` 作为更宽探针：163 项中 162 通过，唯一 error 为 `test_relative_root_online_run_persists_resolvable_snapshot_paths_and_rebuilds_curated` 在 Windows 上对 C: 临时目录与 D: 当前工作区调用 `os.path.relpath()`，抛出跨盘 `ValueError`；该夹具错误未进入本轮状态库逻辑，本轮未越界修改 orchestrator 测试。

### 更新后的遗留风险

- 上一节所述 `JobSpec` 浅冻结风险已由 `95d2f56` 消除，不再要求调用方依赖“不要修改 dict”的约定。
- legacy `enqueue_job()` 的重复 key 兼容行为仍不变；atomic follow-up 路径继续对同 key 的 kind/payload 冲突 fail closed。
- owned deep worker 的后续实际消费接线仍属于 Task 10；本修复只封锁 ownerless 旁路，没有越界实现编排。
