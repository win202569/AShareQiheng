### Task 8: Add the continuous SQLite V8 Stage D schema

**Files:**
- Modify: `ashare_pipeline/state_store.py`
- Create: `tests/test_formal_final_migration.py`
- Create: `tests/fixtures/schema_v7.sql`
- Modify: `tests/test_state_store.py`

**Interfaces:**
- Consumes: exact V2–V7 migration ledger and existing tables。
- Produces: `SCHEMA_VERSION = 8`、`_V8_TABLE_DDL`、`_V8_INDEX_DDL`、`StateStore._apply_v8_migration(connection)`；仅提供给 `formal_final_repository` 使用的内部事务边界，不增加逐表公共写 API。

- [ ] **Step 1: 写 migration RED。** 精确测试名：`test_v7_range_schema_and_rows_survive_v8_migration_exactly`、`test_fresh_database_records_contiguous_versions_2_through_8`、`test_v8_migration_is_atomic_and_reopen_verifies_exact_ddl`、`test_partial_or_extra_v8_object_rejects_without_advancing_ledger`、`test_legacy_score_run_and_score_item_are_not_repurposed`。
- [ ] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration -v`

Expected: schema version 7 且 V8 表不存在。

- [ ] **Step 3: 实现八表 schema。** 新增 `formal_final_run`、`formal_final_artifact`、`formal_final_input`、`formal_final_scorecard`、`formal_final_status`、`formal_final_eligibility`、`formal_final_pool_decision`、`formal_final_dependency`。所有 Decimal 使用规范文本，禁止 REAL；run id/time 不进入 canonical result hash；同一 input manifest 允许独立重放。
- [ ] **Step 4: 加约束与索引。** pool name/decision 精确 CHECK；run `mode IN ('test_preview','official_candidate')`、`status IN ('preview_ready','blocked')`；selected ordinal partial unique；dependency 按 source 和 effect scope 索引；外键和主键保证全表从属同一 run。
- [ ] **Step 5: 运行 GREEN 与完整 state-store migration 回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration tests.test_state_store -v`

Expected: 全部 PASS，现有 V7 range DDL/数据逐字节保留。

- [ ] **Step 6: 独立审查并提交。**

```powershell
git add ashare_pipeline/state_store.py tests/test_state_store.py tests/test_formal_final_migration.py tests/fixtures/schema_v7.sql
git commit -m "feat: add formal final scoring schema v8"
```

