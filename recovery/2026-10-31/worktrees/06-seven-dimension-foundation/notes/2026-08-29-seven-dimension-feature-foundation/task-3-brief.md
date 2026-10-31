### Task 3: SQLite v2-to-v3 Migration

**Files:**
- Modify: `ashare_pipeline/state_store.py:11-134`
- Modify: `tests/test_state_store.py`
- Create: `tests/fixtures/schema_v2.sql`

**Interfaces:**
- Consumes: the literal current v2 schema and existing database contents.
- Produces: `SCHEMA_VERSION = 3`, `schema_migration`, `financial_fact`, `feature_set`, and `feature_value`.

- [ ] **Step 1: Add a literal-v2 migration regression test**

Create `tests/fixtures/schema_v2.sql` by copying the current seven-table v2 DDL, including all five added `score_run` evidence columns. In `tests/test_state_store.py`, add:

```python
def test_initialize_migrates_literal_v2_database_to_v3_without_changing_existing_rows(self):
    legacy_path = Path(self.tempdir.name) / "legacy.sqlite3"
    sql = Path("tests/fixtures/schema_v2.sql").read_text(encoding="utf-8")
    with sqlite3.connect(legacy_path) as connection:
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO run VALUES (?,?,?,?,?,?,?,?)",
            ("run-1", "incremental", utc_at(0), "{}", "succeeded", None, utc_at(0), utc_at(1)),
        )
        connection.commit()
        before = connection.execute("SELECT * FROM run").fetchall()

    StateStore(legacy_path).initialize()

    with sqlite3.connect(legacy_path) as connection:
        self.assertEqual(connection.execute("SELECT * FROM run").fetchall(), before)
        self.assertEqual(
            connection.execute("SELECT version FROM schema_migration ORDER BY version").fetchall(),
            [(2,), (3,)],
        )
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    self.assertTrue({"financial_fact", "feature_set", "feature_value"} <= tables)
```

Add tests for two consecutive initializations, foreign-key rejection, invalid feature status/dimension, coverage -0.01 and 1.01, and preservation of final score-run immutability.

The literal-v2 migration regression must not preserve only `run`. Seed representative, foreign-key-consistent rows in every existing v2 table (`run`, `snapshot`, `job`, `score_run`, `score_item`, `quality_issue`, and `export_artifact`), capture each table with a deterministic `SELECT * ... ORDER BY` before initialization, and compare every table row-for-row after migration. The v3 table/version assertions come only after those preservation assertions.

- [ ] **Step 2: Run the migration test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_initialize_migrates_literal_v2_database_to_v3_without_changing_existing_rows -v
```

Expected: FAIL because schema version is still 2 and v3 tables do not exist.

- [ ] **Step 3: Implement additive migration control**

Set `SCHEMA_VERSION = 3`. Refactor `initialize()` into `_create_v2_schema(connection)`, `_assert_v2_schema(connection)`, and `_apply_v3_migration(connection)`. Use one explicit `BEGIN IMMEDIATE`; do not call `executescript()` inside the transaction because it may commit implicitly. Before creating anything, inspect non-system tables: an empty database may receive the v2 base schema, while any non-empty database without a migration ledger must already contain all seven v2 tables and exact required columns/constraints. Reject a partial/corrupt legacy database instead of repairing it and falsely marking it v2. Accept only migration sets `{2}` and `{2, 3}`; reject future versions or gaps.

Use the approved constraints:

```sql
CREATE TABLE IF NOT EXISTS schema_migration(
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS financial_fact(
    id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL,
    statement TEXT NOT NULL CHECK(statement IN('income','balance','cash_flow')),
    metric_key TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT NOT NULL,
    period_kind TEXT NOT NULL CHECK(period_kind IN('FY','H1','Q1','Q3','OTHER')),
    value REAL NOT NULL CHECK(value BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308),
    unit TEXT NOT NULL CHECK(unit IN('CNY','shares','ratio','CNY_per_share')),
    nature TEXT NOT NULL CHECK(nature IN('instant','duration')),
    announced_at_utc TEXT NOT NULL,
    effective_at_utc TEXT NOT NULL,
    source_updated_at_utc TEXT,
    source_snapshot_id TEXT NOT NULL REFERENCES source_snapshot(id),
    source_field TEXT NOT NULL,
    raw_row_hash TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK((nature='instant' AND period_start IS NULL) OR
          (nature='duration' AND period_start IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS financial_fact_lookup_idx
ON financial_fact(security_id,metric_key,period_end,effective_at_utc);
CREATE INDEX IF NOT EXISTS financial_fact_snapshot_idx
ON financial_fact(source_snapshot_id);
CREATE TABLE IF NOT EXISTS feature_set(
    id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL,
    report_period TEXT NOT NULL,
    as_of_utc TEXT NOT NULL,
    candidate_set_hash TEXT NOT NULL,
    template_id TEXT NOT NULL,
    template_version TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN('partial','financial_ready','blocked')),
    financial_coverage REAL NOT NULL CHECK(financial_coverage>=0 AND financial_coverage<=1),
    dimension_status_json TEXT NOT NULL,
    confidence_inputs_json TEXT NOT NULL,
    blockers_json TEXT NOT NULL,
    bundle_hash TEXT NOT NULL UNIQUE,
    bundle_path TEXT NOT NULL,
    missing_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(security_id,report_period,as_of_utc,input_hash)
);
CREATE INDEX IF NOT EXISTS feature_set_latest_idx
ON feature_set(security_id,report_period,contract_version,as_of_utc DESC,created_at DESC);
CREATE TABLE IF NOT EXISTS feature_value(
    feature_set_id TEXT NOT NULL REFERENCES feature_set(id) ON DELETE CASCADE,
    dimension TEXT NOT NULL CHECK(dimension IN('G','V','M','EQ','FS','CA','T')),
    feature_key TEXT NOT NULL,
    period_key TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN('observed','derived','missing','not_applicable','blocked')),
    formula_version TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    missing_reason TEXT,
    PRIMARY KEY(feature_set_id,dimension,feature_key,period_key),
    CHECK(value IS NULL OR value BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308),
    CHECK((status IN('observed','derived') AND value IS NOT NULL AND missing_reason IS NULL)
       OR (status IN('missing','not_applicable','blocked') AND value IS NULL AND missing_reason IS NOT NULL))
);
```

- [ ] **Step 4: Run state-store tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store -v
```

Expected: PASS.

- [ ] **Step 5: Commit the migration**

```powershell
git add -- ashare_pipeline/state_store.py tests/test_state_store.py tests/fixtures/schema_v2.sql
git commit -m "feat: migrate durable state store to schema v3"
```

---

