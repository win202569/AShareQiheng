# Task 3 修复复审：SQLite v2 → v3 迁移

## 结论

**APPROVED**

- Critical: 0
- Important: 0
- Minor: 0

本轮完整阅读了更新后的 `task-3-report.md` 和 `review-44da010..16c8b64.diff`，重点复核上一轮两个 Important finding 的闭环，并检查修复是否引入迁移、事务或测试回归。默认信任报告的 50/50 测试结果，未重跑测试，未打开或操作 `data/state.sqlite3`。

## 原 Finding 1：DDL 字符串字面量语义 — 已闭环

- `StateStore._normalized_ddl()` 现在逐 token 扫描 SQL。遇到单引号后，从开始引号到最终闭合引号整段按原文加入 token，不执行小写或空白折叠。
- 扫描器正确识别 SQL 标准的成对单引号转义：遇到 `''` 时一次前进两个字符并继续处于同一字面量内，因此例如 `'It''s Ready'` 的大小写和转义形式完整保留。
- 仅在字面量之外对单词 token 小写、忽略空白；`IF NOT EXISTS` 也按 token 序列且仅在 `CREATE TABLE`、`CREATE INDEX` 或 `CREATE UNIQUE INDEX` 后移除，不再通过全文字符串替换破坏字面量。
- 新增 `test_ddl_normalization_preserves_escaped_single_quoted_literals` 同时验证外部关键字/空白差异被规范化、转义字面量自身的大小写差异不相等。
- 新增完整七表语义错配回归：只把 `job.status` CHECK 的 `'pending'` 改为 `'PENDING'`，`initialize()` 必须拒绝；测试进一步断言失败后没有 ledger 或 v3 表残留。该测试独立使用 literal v2 fixture，不与生产规范化逻辑共享预期值。

## 原 Finding 2：同名错误索引与原子回滚 — 已闭环

- `_apply_v3_migration()` 在逐条创建 v3 表/索引后立即调用 `_assert_schema_ddl(connection, _V3_TABLE_DDL, _V3_INDEX_DDL, "v3 schema")`，同时复核全部三张表和三个批准索引。
- postcondition 位于 `INSERT INTO schema_migration(version, ...) VALUES (3, ...)` 之前。错误同名索引导致 `RuntimeError` 时，不可能先登记版本 3。
- 异常继续由 `initialize()` 的现有 `except BaseException` 路径执行 `connection.rollback()`；迁移仍使用同一个 `BEGIN IMMEDIATE`，postcondition 和 ledger 写入都在该事务内。
- 新增回归在完整、无 ledger 的 v2 临时数据库上预占 `feature_set_latest_idx ON job(id)`。测试断言迁移报错后 `schema_migration`、三张 v3 表及本次已创建的两个 financial 索引均不存在，而迁移前已有的错误索引仍原样属于 `job`。这同时证明了失败识别和本次事务写入的整笔 rollback。

## 无新回归核对

- 单一 `BEGIN IMMEDIATE`、异常 rollback、迁移事务内无 `executescript()` 的结构未改变。
- 空库、完整 literal v2、部分/语义不匹配 v2、ledger `{2}` / `{2,3}` / 非法集合的分支逻辑保持不变；新 postcondition 同时覆盖空库、无 ledger v2 和 ledger `{2}` 的 v3 应用路径。
- `PRAGMA foreign_keys = ON` 仍在迁移事务开始前设置；并发初始化仍由 `BEGIN IMMEDIATE` 与 busy timeout 串行化。
- v2 七表、列、约束及 `job_lease_idx` 的批准定义未改变；F3 的七表种数与逐行比较未改变。
- v3 三表的 DDL、CHECK、FK、UNIQUE、级联约束及三个指定索引未改变。
- final `score_run` 的不可变路径和对应迁移回归未改变。
- 修复提交只修改 `ashare_pipeline/state_store.py` 与 `tests/test_state_store.py`；未见任务外实现或数据文件变更。

