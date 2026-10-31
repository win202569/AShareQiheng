# Task 5 Independent Re-review

**APPROVED**

计数：Critical 0，Important 0，Minor 0。

## 原 3 个 Important 闭环确认

### 1. `JobSpec` 已保存 canonical 私有快照

- `ashare_pipeline/state_store.py:210-228` 保留 frozen dataclass 和 `JobSpec(kind, idempotency_key, payload)` 构造方式，但在构造时就通过 `_json(payload)` 将完整嵌套值固化为私有 `_payload_json`。调用方后改原 dict 或其嵌套 dict/list 不再影响规格。
- `.payload` 每次通过 `json.loads()` 返回全新深副本；修改一次返回值也不能回写规格。`ashare_pipeline/state_store.py:603-637` 的 follow-up 插入只读取构造快照，exact replay 不再受外部可变容器影响。
- `tests/test_state_store.py:774-814` 覆盖原 payload 后改、返回副本后改和最终入库值；canonical JSON 与非有限数拒绝语义保持。

### 2. owned deep kind 的 legacy ownerless 旁路已封锁

- `ashare_pipeline/state_store.py:22` 将 `deep_financial`、`deep_statement`、`feature_build` 明确列为 owned kinds。
- legacy `complete_job()` / `fail_job()` 现在都使用 `BEGIN IMMEDIATE`，并在同一写事务内通过 `ashare_pipeline/state_store.py:692-704` 的 guard 确认 `running` 后拒绝上述三种 kind。检查与 UPDATE 之间没有 writer 竞态窗口。
- `tests/test_state_store.py:904-922` 对三种 kind 逐一覆盖“A 过期 → recovery → B 重租 → stale ownerless complete/fail”，两个操作均被拒绝且 B 的 owner/expiry 不变。
- `tests/test_state_store.py:1137-1149` 仍验证非 deep `fetch` 的 ownerless legacy complete/fail，Task 1 兼容行为未被削弱。

### 3. 所有 job success 路径已清理历史失败字段

- 严格 `complete_job_with_followups()` 在 `ashare_pipeline/state_store.py:549-554` 的同一 UPDATE 内设置 `last_error_json = NULL, next_retry_at = NULL`，并清理租约。
- legacy `complete_job()` 在 `ashare_pipeline/state_store.py:643-647` 执行相同清理。作业表的两条 success UPDATE 均已覆盖，不再产生 `succeeded + lease_expired error`。
- `tests/test_state_store.py:924-972` 分别覆盖 strict deep 和 legacy fetch 在租约过期恢复后成功，最终 `error` 与 `next_retry_at` 均为 `None`。

## 新回归、并发与范围

- payload 快照仍是规范 JSON 字符串，重复插入、kind/payload 冲突、部分插入回滚及 `BEGIN IMMEDIATE` 并发序列化语义保持不变。
- legacy guard 的 SELECT 与 transition 位于同一 immediate transaction；无作业和非 running 作业仍保持拒绝语义。严格 owner/expiry API 未被放宽。
- 修复提交 `95d2f56bcee288e4088a624b75e3b1d1ed7c8d4f` 及累计审查包只修改 `ashare_pipeline/state_store.py` 和 `tests/test_state_store.py`，未越界 Task 10；工作树无未提交实现变更，目标 diff check 通过。

## 验证边界

- 按复审要求信任报告中 `tests.test_state_store` 59 项与 Task 1+2 宽回归 91 项 GREEN，未重跑已报告测试。
- 完整 discover 中唯一 C:/D: `os.path.relpath()` 跨盘 fixture error 未进入本轮状态库逻辑，diff 也没有修改相关 orchestrator/fixture，因此不计为 Task 5 回归。
- 复审未打开、读取或写入 `data/state.sqlite3` 及任何现有 `data/` 数据库；静态证据已足够，未创建额外临时库探针。
