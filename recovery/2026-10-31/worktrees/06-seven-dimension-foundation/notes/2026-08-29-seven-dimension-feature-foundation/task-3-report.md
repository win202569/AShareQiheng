# Task 3 报告：SQLite v2 → v3 迁移

## 摘要

- 将 `SCHEMA_VERSION` 提升至 3，并把初始化重构为精确 v2 建库、v2 结构核验与 additive v3 迁移三个阶段。
- 初始化只使用一个显式 `BEGIN IMMEDIATE`；迁移事务内逐条执行 DDL，不使用 `executescript()`。
- 空库先创建精确 v2 基座并登记版本 2；非空无 ledger 数据库只有在完整匹配 v2 七表和索引时才登记 v2，否则 fail closed。
- migration ledger 仅接受 `{2}` 和 `{2,3}`；`{2}` 应用 v3，`{2,3}` 核验现有 v3 DDL 后幂等返回，未来版本和缺口均拒绝。
- 新增 `schema_migration`、`financial_fact`、`feature_set`、`feature_value` 以及三个指定索引，CHECK、UNIQUE、FK 和级联约束均按批准设计实现。

## TDD 证据

### RED

命令：

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_initialize_migrates_literal_v2_database_to_v3_without_changing_existing_rows -v`

结果：按预期失败；literal v2 夹具和七表代表行均成功建立，旧表逐行保存断言通过，失败点为 `sqlite3.OperationalError: no such table: schema_migration`，证明当前 v2 尚未提供迁移 ledger/v3。

### GREEN / 回归

- `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_state_store -v`：30 个测试全部通过。
- `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract tests.test_financial_schema -v`：Task 1/2 共 17 个测试全部通过。
- 合计：47 个测试通过，0 failures，0 errors。
- `git diff --check` 与 staged `git diff --cached --check`：通过（仅有 Git 的 LF→CRLF 工作区提示，无空白错误）。

## v2 旧表逐行比较范围

literal `tests/fixtures/schema_v2.sql` 包含当前七张 v2 表及 `job_lease_idx`，并包含 `score_run` 的五个证据列：`cutoff_utc`、`market_ready`、`quality_passed`、`market_evidence_json`、`quality_evidence_json`。

迁移回归对下列每张表均种入外键一致的代表行，并在迁移前后使用确定性排序执行 `SELECT *` 逐行比较；所有 preservation 断言均先于 v3 table/version 断言：

- `run`：`ORDER BY id`
- `source_snapshot`：`ORDER BY id`
- `job`：`ORDER BY id`
- `score_run`：`ORDER BY id`（代表行为既有 `final`）
- `score_item`：`ORDER BY score_run_id, security_id`
- `quality_issue`：`ORDER BY id`，同时引用已有 run/score_run
- `artifact`：`ORDER BY id`，引用已有 run

迁移后还通过公共 API 验证既有 final score run 仍不可修改，且对应 `score_item` 行保持不变。

## 提交

- 提交：`9621105` (`feat: migrate durable state store to schema v3`)
- 文件：
  - `ashare_pipeline/state_store.py`
  - `tests/test_state_store.py`
  - `tests/fixtures/schema_v2.sql`

## 迁移与回滚遗留风险

- v2 识别刻意 fail closed：除忽略空白、大小写和 `IF NOT EXISTS` 外，表/索引 DDL 必须精确匹配当前 v2。由其他工具生成、但语义等价而文本结构不同的历史数据库会被拒绝，需要先人工审计，不能自动标记为 v2。
- v3 是 additive migration，没有自动 down migration。若需回滚代码，应从迁移前备份恢复数据库；手工删除 v3 表和版本 3 ledger 行存在误删新写入数据的风险。
- 本任务仅验证临时测试数据库；未打开、迁移或改写 `data/state.sqlite3` 及任何 `data/` 文件。

## 独立审查修复轮次

### Finding 1：DDL 字符串字面量语义

- RED：在完整七表、无 ledger 的 literal v2 临时数据库中，仅把 `job.status` CHECK 的 `'pending'` 改为 `'PENDING'`；旧实现未抛错并错误接受迁移，测试以 `RuntimeError not raised` 失败。
- 补充 RED：旧 `_normalized_ddl()` 把含 SQL 转义的 `'It''s Ready'` 与 `'it''s ready'` 归一化成相同文本。
- GREEN：改为 token-aware 扫描；单引号字符串字面量及成对 `''` 转义逐字符保留原文，只在字面量外规范化关键字/标识符大小写、忽略空白，并按 token 移除 `CREATE TABLE/INDEX IF NOT EXISTS`。
- fail-closed 证据：语义不一致的完整 v2 schema 被拒绝，临时数据库中不残留 `schema_migration` 或任何 v3 表。

### Finding 2：错误同名索引与原子回滚

- RED：完整 v2 临时数据库预先包含 `feature_set_latest_idx ON job(id)` 时，旧实现首次 `initialize()` 未抛错，测试以 `RuntimeError not raised` 失败。
- GREEN：`_apply_v3_migration()` 在写入 version 3 之前，事务内对三张 v3 表及三个批准索引执行精确 postcondition；错误同名对象导致 `RuntimeError`，进入现有 rollback 路径。
- rollback 证据：异常后不存在 `schema_migration`、`financial_fact`、`feature_set`、`feature_value`、`financial_fact_lookup_idx` 或 `financial_fact_snapshot_idx`；迁移前已有的错误索引仍原样保留在 `job`，证明只回滚本次迁移写入。

### 修复轮次验证与提交

- `tests.test_state_store -v`：33 个测试全部通过。
- Task 1/2 回归：17 个测试全部通过。
- 合计：50 个测试通过，0 failures，0 errors。
- `git diff --check` 与 staged `git diff --cached --check`：通过。
- 修复提交：`16c8b64` (`fix: verify migrated sqlite schema semantics`)，仅修改 `ashare_pipeline/state_store.py` 与 `tests/test_state_store.py`。
- 本轮仍只操作全新临时数据库，未打开或修改任何 `data/` 文件。
