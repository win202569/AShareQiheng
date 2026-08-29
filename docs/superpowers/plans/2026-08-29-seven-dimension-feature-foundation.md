# Seven-Dimension Feature Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable, resumable foundation that expands the current 120 deep candidates into 360 independent statement jobs, preserves point-in-time financial facts, and emits deterministic seven-dimension input bundles without producing formal scores or pools.

**Architecture:** Keep the existing five-metric prefilter unchanged. Add a three-layer pipeline—verified source snapshots, normalized financial facts, and versioned feature bundles—backed by an additive SQLite v3 migration. A bounded deep worker performs one remote statement request per child job, atomically schedules follow-up feature builds, and leaves all formal-score gates closed.

**Tech Stack:** Python 3.12, Python standard library, SQLite, `unittest`, existing optional `akshare==1.18.94` and `baostock==0.9.3`.

**Spec:** `docs/superpowers/specs/2026-08-29-seven-dimension-feature-foundation-design.md`

## Global Constraints

- Report period is exactly `2026-06-30`; required feature periods are FY2021—FY2025, 2025H1, and 2026H1.
- Preserve every raw snapshot by SHA-256; no implementation step may overwrite or delete existing `data/` content.
- Missing data remains `None/null`; explicit numeric zero remains zero; no weight redistribution or implicit defaults.
- Formal `S0`, `Sc`, module scores, confidence `C`, and both stock pools remain unavailable in this plan.
- `is_formal_score_ready` remains `False`; `finalize` must continue to fail closed.
- Store UTC internally and retain Asia/Shanghai business semantics.
- Effective time is the first real A-share trading day at 15:00 Asia/Shanghai strictly after `max(NOTICE_DATE, UPDATE_DATE)`; never substitute weekdays for the exchange calendar.
- The verified feature calendar covers `2021-01-01` through at least `max(run_date + 10 days, 2026-09-07)`.
- `period_kind` persists `FY/H1/Q1/Q3/OTHER`; feature construction consumes only FY and H1. This implements the approved requirement that other periods may be retained but excluded from this phase.
- Every code commit uses path-specific `git add`; never mix existing crawl-data changes into code commits.
- Unit tests never require network access. Bounded online collection is a separate operational acceptance step.
- New raw and curated feature data remain tracked under `data/`; no new ignore rule is permitted.

---

## File Structure

| File | Responsibility |
|---|---|
| `ashare_pipeline/feature_contract.py` | Seven-dimension bundle types, validation, canonical serialization, and hashing |
| `ashare_pipeline/financial_schema.py` | Canonical financial facts, source-field catalog, periods, units, and request constants |
| `ashare_pipeline/industry_templates.py` | Explicit provisional industry-to-template mapping and applicable financial slots |
| `ashare_pipeline/snapshot_repository.py` | Exact request-scoped snapshot lookup, persistence, path resolution, and verification |
| `ashare_pipeline/financial_features.py` | Pure point-in-time fact normalization, formulas, evidence, coverage, and bundle construction |
| `ashare_pipeline/deep_worker.py` | Parent expansion, statement execution, lease heartbeat, feature builds, and bounded summaries |
| `ashare_pipeline/state_store.py` | SQLite v3 migration and atomic persistence/job APIs |
| `ashare_pipeline/sources.py` | One-statement AKShare fetch contract with backward-compatible three-table wrapper |
| `ashare_pipeline/snapshot_store.py` | Public verified snapshot read API |
| `ashare_pipeline/orchestrator.py` | `deep` CLI, daily enqueueing, calendar acquisition, and scoped progress |
| `tests/feature_fixture_helpers.py` | Hermetic candidate documents and exact FetchBatch fixture loaders |
| `tests/fixtures/schema_v2.sql` | Literal current v2 schema used for migration regression |
| `tests/fixtures/financial/*.json` | Fixed industrial, bank, real-estate, missing-table, and trade-calendar fixtures |

## Execution Preflight

- [ ] Verify the current dirty state before implementation:

```powershell
git status --short
```

Expected known paths are `data/state.sqlite3`, `data/status/pipeline_status.json`, `data/status/quality.json`, and `data/raw/akshare/disclosure_schedule/2026-08-29/`. Do not stage any additional user-owned path.

- [ ] Checkpoint the known incremental crawl separately so later worker writes have a clean baseline:

```powershell
git add -- data/state.sqlite3 data/status/pipeline_status.json data/status/quality.json data/raw/akshare/disclosure_schedule/2026-08-29
git commit -m "data: checkpoint 2026-08-29 incremental crawl"
```

- [ ] Establish the test baseline with workspace-local temporary directories to avoid the existing C:-to-D: `os.path.relpath` environment failure:

```powershell
$env:TEMP=(Get-Location).Path
$env:TMP=(Get-Location).Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all existing 109 tests pass.

---

### Task 1: Seven-Dimension Contract and Deterministic Hashing

**Files:**
- Create: `ashare_pipeline/feature_contract.py`
- Create: `tests/test_feature_contract.py`

**Interfaces:**
- Consumes: Python standard-library dataclasses, mappings, JSON, SHA-256, and timezone-aware ISO timestamps.
- Produces: `CONTRACT_VERSION`, `DIMENSIONS`, `EvidenceRef`, `FeatureValue`, `DimensionInput`, `IndustryContext`, `ConfidenceInputs`, `FeatureBundle`, `canonical_json_bytes(value)`, and `canonical_sha256(value)`.

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_feature_contract.py` with a helper that constructs all seven dimensions and these core assertions:

```python
import math
import unittest

from ashare_pipeline.feature_contract import (
    DIMENSIONS,
    ConfidenceInputs,
    DimensionInput,
    EvidenceRef,
    FeatureBundle,
    FeatureValue,
    IndustryContext,
)


def evidence(snapshot_id: str = "snapshot-a") -> EvidenceRef:
    return EvidenceRef(
        financial_fact_id="fact-a",
        source_snapshot_id=snapshot_id,
        source_field="TOTAL_ASSETS",
        raw_row_hash="a" * 64,
        announced_at_utc="2026-08-20T15:59:59+00:00",
        effective_at_utc="2026-08-21T07:00:00+00:00",
    )


def dimensions() -> dict[str, DimensionInput]:
    result = {
        key: DimensionInput(
            status="partial",
            values=(
                FeatureValue(
                    key=f"{key.lower()}.sample",
                    value=0.0,
                    unit="ratio",
                    period_key="2026H1",
                    status="observed",
                    formula_version="observed-v1",
                    evidence=(evidence(),),
                    missing_reason=None,
                ),
            ),
        )
        for key in DIMENSIONS
    }
    result["V"] = DimensionInput(
        status="missing",
        values=(
            FeatureValue(
                key="v.market_cap",
                value=None,
                unit="CNY",
                period_key="as_of",
                status="missing",
                formula_version="observed-v1",
                evidence=(),
                missing_reason="market_data_missing",
            ),
        ),
    )
    return result


def bundle(
    dimension_inputs: dict[str, DimensionInput] | None = None,
    *,
    is_formal_score_ready: bool = False,
) -> FeatureBundle:
    return FeatureBundle(
        schema_version=1,
        contract_version="feature-contract-v1",
        security_id="SH600001",
        report_period="2026-06-30",
        as_of_utc="2026-08-29T16:00:00+00:00",
        candidate_set_hash="c" * 64,
        industry=IndustryContext(
            source="eastmoney-provisional",
            code=None,
            name="包装印刷",
            template_id="general_nonfinancial",
            template_version="template-registry-v1",
            formal_industry_ready=False,
        ),
        input_hash="1" * 64,
        financial_status="partial",
        financial_coverage=0.5,
        confidence_inputs=ConfidenceInputs(
            data_completeness_ratio=0.5,
            date_precision_counts={"timestamp": 0, "date_only": 1},
            history_years_present=3,
            mapping_consistent=True,
            formal_confidence=None,
        ),
        dimension_inputs=dimension_inputs or dimensions(),
        blockers=("formal_industry_mapping_missing",),
        is_formal_score_ready=is_formal_score_ready,
    )


class FeatureContractTests(unittest.TestCase):
    def test_bundle_requires_exactly_seven_dimensions_and_is_never_formal(self):
        self.assertEqual(DIMENSIONS, ("G", "V", "M", "EQ", "FS", "CA", "T"))
        with self.assertRaisesRegex(ValueError, "dimension keys"):
            bundle({key: value for key, value in dimensions().items() if key != "G"})
        with self.assertRaisesRegex(ValueError, "formal score"):
            bundle(dimensions(), is_formal_score_ready=True)

    def test_zero_missing_and_nonfinite_values_have_distinct_contracts(self):
        self.assertEqual(dimensions()["G"].values[0].value, 0.0)
        self.assertIsNone(dimensions()["V"].values[0].value)
        for invalid in (True, math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    FeatureValue(
                        key="g.invalid",
                        value=invalid,
                        unit="ratio",
                        period_key="2026H1",
                        status="observed",
                        formula_version="observed-v1",
                        evidence=(evidence(),),
                        missing_reason=None,
                    )

    def test_canonical_hash_is_order_independent_and_evidence_sensitive(self):
        first = bundle(dimensions())
        reversed_dimensions = dict(reversed(tuple(dimensions().items())))
        second = bundle(reversed_dimensions)
        changed = bundle(
            {**dimensions(), "G": DimensionInput(status="partial", values=(
                FeatureValue(
                    key="g.sample",
                    value=0.0,
                    unit="ratio",
                    period_key="2026H1",
                    status="observed",
                    formula_version="observed-v1",
                    evidence=(evidence("snapshot-b"),),
                    missing_reason=None,
                ),
            ))}
        )
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(first.bundle_hash(), second.bundle_hash())
        self.assertNotEqual(first.bundle_hash(), changed.bundle_hash())
```

Additional test methods must cover incomplete evidence, naive timestamps, coverage below 0/above 1, inconsistent observed/missing states, non-null formal confidence, and JSON round-trip.

- [ ] **Step 2: Run the contract tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_feature_contract -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ashare_pipeline.feature_contract'`.

- [ ] **Step 3: Implement the immutable contract**

Add these exact constants and state rules:

```python
CONTRACT_VERSION = "feature-contract-v1"
DIMENSIONS = ("G", "V", "M", "EQ", "FS", "CA", "T")
FEATURE_VALUE_STATES = frozenset({"observed", "derived", "missing", "not_applicable", "blocked"})
DIMENSION_INPUT_STATES = frozenset({"input_ready", "partial", "missing", "not_applicable", "blocked"})
FINANCIAL_STATUSES = frozenset({"partial", "financial_ready", "blocked"})
UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_aware_utc(value: str, field: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc).isoformat()


def require_feature_number(value: object, *, allow_none: bool) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("feature value must be a finite number or allowed null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("feature value must be finite")
    return result
```

Implement frozen dataclasses with `to_dict()`/`from_dict()`. `FeatureValue.__post_init__` must require a unit from `UNITS` in every state, a finite value plus evidence for observed/derived, and null plus a non-empty reason for missing/not_applicable/blocked. `FeatureBundle.validate()` must require exact dimension keys, `0 <= financial_coverage <= 1`, `formal_confidence is None`, and `is_formal_score_ready is False`. Sort dimensions by `DIMENSIONS`, feature values by `(key, period_key)`, evidence by all fields, and blockers lexically in `to_dict()`.

- [ ] **Step 4: Run the contract tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_feature_contract -v
```

Expected: PASS.

- [ ] **Step 5: Commit the contract**

```powershell
git add -- ashare_pipeline/feature_contract.py tests/test_feature_contract.py
git commit -m "feat: define auditable seven-dimension feature contract"
```

---

### Task 2: Financial Fact Catalog, Period Rules, and Industry Registry

**Files:**
- Create: `ashare_pipeline/financial_schema.py`
- Create: `ashare_pipeline/industry_templates.py`
- Create: `tests/test_financial_schema.py`
- Create: `tests/fixtures/industry_template_registry_v1.json`

**Interfaces:**
- Consumes: `canonical_sha256` from Task 1.
- Produces: `MAPPING_VERSION`, `TEMPLATE_VERSION`, `FINANCIAL_REQUEST_VERSION`, `StatementDataset`, `StatementKind`, `DATASET_TO_STATEMENT`, `PeriodInfo`, `FieldRule`, `FinancialFact`, `classify_period()`, `field_rules()`, `TemplateDefinition`, and `resolve_template()`.

- [ ] **Step 1: Write failing period, fact-ID, mapping, and registry tests**

```python
class FinancialSchemaTests(unittest.TestCase):
    def test_classify_period_preserves_other_periods_but_marks_feature_window(self):
        self.assertEqual(classify_period("2025-12-31", "2025年报", "年报").period_kind, "FY")
        self.assertEqual(classify_period("2026-06-30", "2026中报", "中报").period_kind, "H1")
        self.assertEqual(classify_period("2026-03-31", "2026一季报", "一季报").period_kind, "Q1")
        self.assertEqual(classify_period("2026-09-30", "2026三季报", "三季报").period_kind, "Q3")

    def test_financial_fact_identity_excludes_created_at_but_includes_revision(self):
        first = FinancialFact.create(**fact_fields(created_at="2026-08-29T00:00:00+00:00"))
        rebuilt = FinancialFact.create(**fact_fields(created_at="2026-08-30T00:00:00+00:00"))
        revised = FinancialFact.create(**fact_fields(
            created_at="2026-08-30T00:00:00+00:00",
            raw_row_hash="b" * 64,
        ))
        self.assertEqual(first.id, rebuilt.id)
        self.assertNotEqual(first.id, revised.id)

    def test_registry_has_no_implicit_general_fallback(self):
        self.assertEqual(resolve_template("半导体").template_id, "rd_growth")
        self.assertEqual(resolve_template("房地产开发").template_id, "real_estate_high_leverage")
        self.assertEqual(resolve_template("银行").template_id, "bank")
        self.assertEqual(resolve_template("不存在行业").template_id, "unclassified")
```

Add `test_registry_explicitly_lists_all_design_candidate_industries`: read `data/curated/prefilter.json`, compare its industry set with the fixture's `candidate_industries`, and require every fixture name to appear explicitly in `INDUSTRY_TO_TEMPLATE`. Add subtests rejecting bool, NaN, Infinity, unknown units, and instant facts with a non-null `period_start`.

- [ ] **Step 2: Run schema tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_financial_schema -v
```

Expected: FAIL because `financial_schema` and `industry_templates` do not exist.

- [ ] **Step 3: Implement period and fact contracts**

Use these exact declarations:

```python
MAPPING_VERSION = "eastmoney-financial-mapping-v1"
TEMPLATE_VERSION = "template-registry-v1"
FINANCIAL_REQUEST_VERSION = "eastmoney-financial-request-v1"
StatementDataset = Literal["balance_sheet", "profit_sheet", "cash_flow_sheet"]
StatementKind = Literal["balance", "income", "cash_flow"]
DATASET_TO_STATEMENT: dict[str, str] = {
    "balance_sheet": "balance",
    "profit_sheet": "income",
    "cash_flow_sheet": "cash_flow",
}
STATEMENT_TO_DATASET = {value: key for key, value in DATASET_TO_STATEMENT.items()}
TARGET_PERIOD_ENDS = frozenset({
    "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31",
    "2025-12-31", "2025-06-30", "2026-06-30",
})
```

`classify_period()` returns `FY` for December 31, `H1` for June 30, `Q1` for March 31, `Q3` for September 30, and `OTHER` for a valid unmatched report date. Duration periods start January 1 of the report year. `FinancialFact.create()` normalizes aware timestamps to UTC and hashes all fields except `id`/`created_at`.

Populate `FieldRule` entries for every approved common fact. Use ordered source-field candidates including:

- Income: `TOTAL_OPERATE_INCOME/OPERATE_INCOME`, `TOTAL_OPERATE_COST/OPERATE_COST`, `OPERATE_PROFIT`, `TOTAL_PROFIT`, `INCOME_TAX`, `NETPROFIT`, `PARENT_NETPROFIT`, `DEDUCT_PARENT_NETPROFIT`, `INTEREST_EXPENSE`, `RESEARCH_EXPENSE/RD_EXPENSE`.
- Balance: `MONETARYFUNDS`, `TOTAL_ASSETS`, `TOTAL_LIABILITIES`, `TOTAL_PARENT_EQUITY/PARENT_EQUITY_BALANCE`, `TOTAL_EQUITY`, `SHORT_LOAN/SHORT_FIN_PAYABLE`, `NONCURRENT_LIAB_1YEAR`, `LONG_LOAN`, `BOND_PAYABLE`, `LEASE_LIAB`, `NOTE_RECE`, `ACCOUNTS_RECE`, `CONTRACT_ASSET`, `INVENTORY`, `NOTE_PAYABLE`, `ACCOUNTS_PAYABLE`, `CONTRACT_LIAB`, `SHARE_CAPITAL`, `GOODWILL`.
- Cash flow: `NETCASH_OPERATE/OPERATE_NETCASH_BALANCE`, `CONSTRUCT_LONG_ASSET`, `ASSIGN_DIVIDEND_PORFIT`, `PAY_INTEREST`, `INVEST_PAY_CASH`, `DISPOSAL_LONG_ASSET`, `ACCEPT_INVEST_CASH/RECEIVE_ADD_EQUITY`, `ISSUE_BOND`, `PAY_DEBT_CASH`.

Do not map bank deposits, trading liabilities, or insurance reserves into industrial debt/payable facts.

- [ ] **Step 4: Implement the explicit template registry**

Create `TemplateDefinition(template_id, financial_slots, specialized_inputs_required)`. Define IDs `bank`, `insurance`, `broker`, `real_estate_high_leverage`, `resource_cycle`, `utility`, `rd_growth`, `general_nonfinancial`, and `unclassified`.

Generate the exact candidate-label checklist once, then copy the names into the versioned fixture and production mapping:

```powershell
$d=Get-Content -LiteralPath 'data\curated\prefilter.json' -Raw | ConvertFrom-Json
$d.records | ForEach-Object industry | Sort-Object -Unique
```

Assign `房地产开发` to real-estate/high-leverage; `工业金属、炼化及贸易、煤炭开采、普钢、小金属、化学原料、水泥` to resource-cycle; `电力、燃气Ⅱ` to utility; R&D-heavy semiconductor, battery, photovoltaic, electronic, pharmaceutical, medical-device, automation, game, and IT labels to R&D growth; `多元金融` to unclassified until a financial subtype is evidenced; explicitly assign every remaining current label to general non-financial. Unknown runtime values always return unclassified.

- [ ] **Step 5: Run schema tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_financial_schema -v
```

Expected: PASS.

- [ ] **Step 6: Commit schema and registry**

```powershell
git add -- ashare_pipeline/financial_schema.py ashare_pipeline/industry_templates.py tests/test_financial_schema.py tests/fixtures/industry_template_registry_v1.json
git commit -m "feat: add versioned financial fact and template registry"
```

---

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

### Task 4: Financial-Fact, Feature-Bundle, and Quality-Issue Persistence

**Files:**
- Modify: `ashare_pipeline/state_store.py:254-341`
- Modify: `tests/test_state_store.py`

**Interfaces:**
- Consumes: `FinancialFact` from Task 2 and `FeatureBundle` from Task 1.
- Produces: `insert_financial_facts()`, `list_financial_facts()`, `put_feature_bundle()`, `get_feature_bundle_row()`, `latest_feature_set()`, and `record_quality_issue()`.

- [ ] **Step 1: Add failing persistence and deterministic-conflict tests**

```python
def test_insert_financial_facts_is_idempotent_and_preserves_revision(self):
    snapshot_id, _ = self.store.record_snapshot(
        "akshare", "balance_sheet", "request-a", "a" * 64,
        "data/raw/a.json", 1, utc_at(0),
    )
    first = financial_fact(snapshot_id=snapshot_id, raw_row_hash="1" * 64, value=100.0)
    revised = financial_fact(snapshot_id=snapshot_id, raw_row_hash="2" * 64, value=101.0)

    self.assertEqual(self.store.insert_financial_facts([first, first]), (1, 1))
    self.assertEqual(self.store.insert_financial_facts([revised]), (1, 0))
    self.assertEqual(len(self.store.list_financial_facts("SH600001")), 2)


def test_put_feature_bundle_is_atomic_and_rejects_nondeterministic_conflict(self):
    bundle = valid_feature_bundle(input_hash="b" * 64)
    feature_id, created = self.store.put_feature_bundle(
        bundle,
        bundle_path="data/curated/formal_features/2026-06-30/SH600001/b.json",
        bundle_hash=bundle.bundle_hash(),
    )
    self.assertTrue(created)
    self.assertEqual(feature_id, bundle.bundle_hash())
    self.assertEqual(
        self.store.put_feature_bundle(
            bundle,
            bundle_path="data/curated/formal_features/2026-06-30/SH600001/b.json",
            bundle_hash=bundle.bundle_hash(),
        ),
        (feature_id, False),
    )
    conflicting = replace(bundle, blockers=("changed-without-input-hash",))
    with self.assertRaisesRegex(ValueError, "non-deterministic feature conflict"):
        self.store.put_feature_bundle(
            conflicting,
            bundle_path="data/curated/formal_features/2026-06-30/SH600001/c.json",
            bundle_hash=conflicting.bundle_hash(),
        )
    stored = self.store.get_feature_bundle_row("SH600001", "2026-06-30", "b" * 64)
    self.assertEqual(stored["bundle_hash"], bundle.bundle_hash())
```

Add a trigger-based rollback test: abort one `feature_value` insert and assert neither header nor values remains. Add tests that absolute bundle paths are rejected, source-snapshot filters are exact, and quality-issue details are canonical JSON.

- [ ] **Step 2: Run new persistence tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_insert_financial_facts_is_idempotent_and_preserves_revision tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_is_atomic_and_rejects_nondeterministic_conflict -v
```

Expected: FAIL with missing `StateStore` methods.

- [ ] **Step 3: Implement the exact persistence APIs**

Use these signatures:

```python
def insert_financial_facts(
    self,
    facts: Iterable[FinancialFact],
) -> tuple[int, int]:
    records = tuple(facts)
    inserted = 0
    with self._transaction(immediate=True) as connection:
        for fact in records:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO financial_fact
                (id,security_id,statement,metric_key,period_start,period_end,period_kind,
                 value,unit,nature,announced_at_utc,effective_at_utc,source_updated_at_utc,
                 source_snapshot_id,source_field,raw_row_hash,mapping_version,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(fact.to_record()[key] for key in FINANCIAL_FACT_COLUMNS),
            )
            inserted += cursor.rowcount
    return inserted, len(records) - inserted


def list_financial_facts(
    self,
    security_id: str,
    *,
    effective_at_or_before: str | None = None,
    source_snapshot_ids: Sequence[str] | None = None,
) -> list[FinancialFact]:
    query = "SELECT * FROM financial_fact WHERE security_id = ?"
    parameters: list[object] = [security_id]
    if effective_at_or_before is not None:
        query += " AND effective_at_utc <= ?"
        parameters.append(_utc_iso(effective_at_or_before))
    if source_snapshot_ids is not None:
        if not source_snapshot_ids:
            return []
        marks = ",".join("?" for _ in source_snapshot_ids)
        query += f" AND source_snapshot_id IN ({marks})"
        parameters.extend(source_snapshot_ids)
    query += " ORDER BY metric_key,period_end,effective_at_utc,id"
    with closing(self._connect()) as connection:
        return [FinancialFact.from_record(dict(row)) for row in connection.execute(query, parameters)]
```

`put_feature_bundle()` validates `bundle_hash == bundle.bundle_hash()`, requires a forward-slash project-relative path beginning `data/curated/formal_features/`, sets `feature_set.id = bundle_hash`, and writes the header plus all seven dimensions in one immediate transaction. On the logical unique key `(security_id, report_period, as_of_utc, input_hash)`, return `(existing_id, False)` only if the hash and canonical content match; otherwise raise the exact conflict error without updating.

`record_quality_issue()` inserts a UUID and returns it. Do not add a second feature database or duplicate score table.

`latest_feature_set(security_id, report_period, contract_version=None, as_of_utc=None)` orders by `as_of_utc DESC, created_at DESC, id DESC`; optional filters are exact and it returns parsed JSON fields for reporting without loading raw financial values.

- [ ] **Step 4: Run all state-store tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store -v
```

Expected: PASS.

- [ ] **Step 5: Commit persistence**

```powershell
git add -- ashare_pipeline/state_store.py tests/test_state_store.py
git commit -m "feat: persist financial facts and feature bundles"
```

---

### Task 5: Owned Leases and Atomic Follow-Up Jobs

**Files:**
- Modify: `ashare_pipeline/state_store.py:156-252`
- Modify: `tests/test_state_store.py`

**Interfaces:**
- Consumes: existing job table and lease state machine.
- Produces: `JobSpec`, `renew_job_lease()`, `complete_job_with_followups()`, `fail_job_with_followups()`, and filtered `list_jobs()`. Existing `complete_job()`/`fail_job()` remain compatible.

- [ ] **Step 1: Add failing owner, renewal, and atomicity tests**

```python
def test_renew_job_lease_requires_current_unexpired_owner(self):
    job_id = self.store.enqueue_job("deep_statement", "statement-a", {})
    self.store.lease_next_job(["deep_statement"], "worker-a", 60, utc_at(0))
    expiry = self.store.renew_job_lease(job_id, "worker-a", 120, utc_at(30))
    self.assertEqual(expiry, utc_at(150))
    with self.assertRaisesRegex(ValueError, "lease owner"):
        self.store.renew_job_lease(job_id, "worker-b", 120, utc_at(31))


def test_statement_completion_and_feature_followup_are_one_transaction(self):
    job_id = self.store.enqueue_job("deep_statement", "statement-b", {})
    self.store.lease_next_job(["deep_statement"], "worker-a", 60, utc_at(0))
    followup = JobSpec("feature_build", "feature-b", {"security_id": "SH600001"})
    with sqlite3.connect(self.db_path) as connection:
        connection.execute(
            """CREATE TRIGGER reject_feature BEFORE INSERT ON job
            WHEN NEW.kind='feature_build' BEGIN
              SELECT RAISE(ABORT,'reject feature');
            END"""
        )
        connection.commit()
    with self.assertRaises(sqlite3.IntegrityError):
        self.store.complete_job_with_followups(
            job_id, "worker-a", {"snapshot": "a" * 64}, (followup,)
        )
    job = self.store.get_job(job_id)
    self.assertEqual(job["status"], "running")
    self.assertEqual(self.store.list_jobs(["feature_build"]), [])
```

Mirror the transaction test for `fail_job_with_followups()`. Add tests that a wrong worker cannot complete/fail a deep job, expired/completed jobs cannot renew, repeated follow-up insertion is idempotent, and legacy calls without `worker_id` still pass existing tests.

- [ ] **Step 2: Run the new lease tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_renew_job_lease_requires_current_unexpired_owner tests.test_state_store.StateStoreTestCase.test_statement_completion_and_feature_followup_are_one_transaction -v
```

Expected: FAIL with missing renewal/follow-up APIs.

- [ ] **Step 3: Implement JobSpec and transactional transitions**

```python
@dataclass(frozen=True)
class JobSpec:
    kind: str
    idempotency_key: str
    payload: dict[str, object]


def renew_job_lease(
    self,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
    now_utc: str | None = None,
) -> str:
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    now = _utc_iso(now_utc)
    expiry = datetime.fromtimestamp(
        datetime.fromisoformat(now).timestamp() + lease_seconds,
        timezone.utc,
    ).isoformat()
    with self._transaction(immediate=True) as connection:
        cursor = connection.execute(
            """UPDATE job SET lease_expires_at=?,updated_at=?
            WHERE id=? AND status='running' AND lease_worker=?
              AND lease_expires_at>?""",
            (expiry, now, job_id, worker_id, now),
        )
        if cursor.rowcount != 1:
            raise ValueError("job is not held by the current unexpired lease owner")
    return expiry
```

Implement `complete_job_with_followups(job_id, worker_id, result, followups)` and `fail_job_with_followups(job_id, worker_id, error, retryable, next_retry_at, followups)` with one `BEGIN IMMEDIATE`: verify running status and owner, `INSERT OR IGNORE` each follow-up by idempotency key, then update the parent/statement state. Existing methods delegate with empty follow-ups; only deep-worker calls require explicit owner.

- [ ] **Step 4: Run all state-store tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store -v
```

Expected: PASS.

- [ ] **Step 5: Commit job-state extensions**

```powershell
git add -- ashare_pipeline/state_store.py tests/test_state_store.py
git commit -m "feat: add owned leases and atomic follow-up jobs"
```

---

### Task 6: Exact Verified Snapshot Repository

**Files:**
- Create: `ashare_pipeline/snapshot_repository.py`
- Modify: `ashare_pipeline/snapshot_store.py:11-66`
- Create: `tests/test_snapshot_repository.py`
- Modify: `tests/test_snapshot_store.py`

**Interfaces:**
- Consumes: `StateStore.record_snapshot()`, `FetchBatch`, `SnapshotStore.write()`, and `canonical_sha256()`.
- Produces: `SnapshotRef`, `VerifiedSnapshot`, `SnapshotRepository.persist()`, `find_exact()`, `get()`, `read_verified()`, and `SnapshotStore.read_verified()`.

- [ ] **Step 1: Write exact-request and tamper tests**

```python
def test_find_exact_never_returns_another_symbol_global_latest(self):
    first, _ = self.repository.persist(statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00"))
    self.repository.persist(statement_batch("SH600002", 200.0, "2026-08-29T01:00:00+00:00"))
    observed = self.repository.find_exact(
        "akshare",
        "balance_sheet",
        {"symbol": "SH600001", "report_period": "2026-06-30"},
    )
    self.assertEqual(observed.id, first.id)


def test_read_verified_rejects_tampered_snapshot(self):
    snapshot, _ = self.repository.persist(statement_batch(
        "SH600001", 100.0, "2026-08-29T00:00:00+00:00"
    ))
    verified = self.repository.read_verified(snapshot)
    self.assertEqual(verified.batch.records[0]["TOTAL_ASSETS"], 100.0)
    path = self.project_root / snapshot.payload_path
    path.write_text(path.read_text(encoding="utf-8").replace("100.0", "999.0"), encoding="utf-8")
    with self.assertRaisesRegex(OSError, "hash"):
        self.repository.read_verified(snapshot)
```

Add tests for latest exact revision ordering `(fetched_at, created_at, payload_hash)`, unmatched requests, `get(snapshot_id)`, identical-content reuse, and both legacy absolute paths and new project-relative paths.

- [ ] **Step 2: Run repository tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_snapshot_repository tests.test_snapshot_store -v
```

Expected: FAIL because `snapshot_repository` and the public read API do not exist.

- [ ] **Step 3: Implement public verified reads**

In `SnapshotStore`, add:

```python
def read_verified(self, path: str | Path, digest: str) -> FetchBatch:
    candidate = Path(path)
    self._verify(candidate, digest)
    stored = json.loads(candidate.read_text(encoding="utf-8"))
    return FetchBatch(
        stored["source"],
        stored["dataset"],
        stored["request"],
        stored["records"],
        stored["fetched_at_utc"],
        stored["source_version"],
        stored["metadata"],
    )
```

Define `SnapshotRef` with DB fields and `VerifiedSnapshot(ref, batch)`. `SnapshotRepository` receives the data root, derives `project_root = data_root.parent`, and stores every new path as:

```python
relative_path = target.resolve().relative_to(self.project_root.resolve()).as_posix()
if not relative_path.startswith("data/"):
    raise ValueError("snapshot path must stay inside the project data directory")
```

Use this exact constructor:

```python
def __init__(
    self,
    data_root: str | Path,
    state_store: StateStore,
    snapshot_store: SnapshotStore | None = None,
) -> None:
    self.data_root = Path(data_root).resolve()
    self.project_root = self.data_root.parent
    self.state_store = state_store
    self.snapshot_store = snapshot_store or SnapshotStore(self.data_root)
```

`find_exact()` computes the canonical request fingerprint and filters source, dataset, and fingerprint before ordering. `get()` fetches by snapshot ID. `read_verified()` resolves relative paths against project root, accepts existing absolute legacy paths, verifies the resolved path remains inside project root for new relative records, and calls the public snapshot-store API.

- [ ] **Step 4: Run snapshot tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_snapshot_repository tests.test_snapshot_store -v
```

Expected: PASS.

- [ ] **Step 5: Commit snapshot repository**

```powershell
git add -- ashare_pipeline/snapshot_repository.py ashare_pipeline/snapshot_store.py tests/test_snapshot_repository.py tests/test_snapshot_store.py
git commit -m "feat: add exact verified snapshot repository"
```

---

### Task 7: Point-in-Time Financial-Fact Normalization

**Files:**
- Create: `ashare_pipeline/financial_features.py`
- Create: `tests/test_financial_features.py`
- Create: `tests/fixtures/financial/general_nonfinancial_statements.json`
- Create: `tests/fixtures/financial/bank_statements.json`
- Create: `tests/fixtures/financial/real_estate_statements.json`
- Create: `tests/fixtures/financial/trade_calendar_2021_2026.json`

**Interfaces:**
- Consumes: `FetchBatch`, Task 2 fact rules, and verified trade dates.
- Produces: `QualityIssue`, `FactBuildResult`, `FactSelection`, `trading_days_from_batch()`, `build_financial_facts()`, and `select_visible_facts()`.

- [ ] **Step 1: Write failing time, normalization, and selection tests**

```python
def test_effective_at_uses_later_notice_or_update_then_next_trading_close(self):
    batch = one_row_batch(
        notice="2026-03-31",
        update="2026-08-28",
        report_date="2025-12-31",
        total_assets=1_000_000.0,
    )
    result = build_financial_facts(
        batch,
        source_snapshot_id="snapshot-a",
        expected_security_id="SH600001",
        trading_days=(date(2026, 8, 28), date(2026, 8, 31)),
        created_at_utc="2026-08-29T00:00:00+00:00",
    )
    fact = next(item for item in result.facts if item.metric_key == "total_assets")
    self.assertEqual(fact.announced_at_utc, "2026-03-31T15:59:59+00:00")
    self.assertEqual(fact.source_updated_at_utc, "2026-08-28T15:59:59+00:00")
    self.assertEqual(fact.effective_at_utc, "2026-08-31T07:00:00+00:00")


def test_calendar_missing_next_session_blocks_instead_of_guessing_weekday(self):
    result = build_financial_facts(
        one_row_batch(notice="2026-08-31", update=None, report_date="2026-06-30"),
        source_snapshot_id="snapshot-a",
        expected_security_id="SH600001",
        trading_days=(date(2026, 8, 31),),
        created_at_utc="2026-08-31T16:00:00+00:00",
    )
    self.assertEqual(result.facts, ())
    self.assertEqual(result.issues[0].code, "trade_calendar_missing_next_session")


def test_future_revision_is_not_selected_before_its_effective_time(self):
    old = fact_version(value=100.0, effective_at="2026-04-01T07:00:00+00:00", snapshot="old")
    revised = fact_version(value=999.0, effective_at="2026-09-01T07:00:00+00:00", snapshot="new")
    selection = select_visible_facts(
        (revised, old),
        as_of_utc="2026-08-31T15:00:00+00:00",
        snapshot_fetched_at={"old": "2026-04-01T08:00:00+00:00", "new": "2026-09-01T08:00:00+00:00"},
    )
    self.assertEqual(selection.facts[0].value, 100.0)
```

Add tests for numeric zero vs null/nonfinite/bool, missing security/report date, security mismatch, FY/H1 vs quarter retention, deterministic shuffled duplicates, conflicting units, and the approved asset-balance tolerance: a CNY 500 difference on CNY 1,000,000 passes; a CNY 10,000 difference blocks.

- [ ] **Step 2: Run fact-normalization tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FinancialFactSelectionTests -v
```

Expected: FAIL because `financial_features` does not exist.

- [ ] **Step 3: Implement point-in-time normalization**

Use these types and signatures:

```python
@dataclass(frozen=True)
class QualityIssue:
    severity: str
    code: str
    details: Mapping[str, object]


@dataclass(frozen=True)
class FactBuildResult:
    facts: tuple[FinancialFact, ...]
    issues: tuple[QualityIssue, ...]


@dataclass(frozen=True)
class FactSelection:
    facts: tuple[FinancialFact, ...]
    blockers: tuple[str, ...]


def build_financial_facts(
    batch: FetchBatch,
    *,
    source_snapshot_id: str,
    expected_security_id: str,
    trading_days: Sequence[date],
    created_at_utc: str,
) -> FactBuildResult:
    records = tuple(sorted(batch.records, key=canonical_sha256))
    facts: list[FinancialFact] = []
    issues: list[QualityIssue] = []
    for row in records:
        code = str(row.get("SECURITY_CODE") or row.get("SECUCODE") or "").split(".")[0].zfill(6)
        if not code or not expected_security_id.endswith(code):
            issues.append(QualityIssue("error", "statement_security_mismatch", {"expected": expected_security_id}))
            return FactBuildResult((), tuple(issues))
        period = classify_period(str(row.get("REPORT_DATE") or ""), row.get("REPORT_DATE_NAME"), row.get("REPORT_TYPE"))
        if period is None:
            issues.append(QualityIssue("error", "statement_report_date_invalid", {"security_id": expected_security_id}))
            return FactBuildResult((), tuple(issues))
        notice_utc, notice_local_date = source_time(row.get("NOTICE_DATE"), "NOTICE_DATE")
        update_utc, update_local_date = source_time(row.get("UPDATE_DATE"), "UPDATE_DATE", allow_none=True)
        version_date = max(item for item in (notice_local_date, update_local_date) if item is not None)
        next_sessions = [item for item in trading_days if item > version_date]
        if not next_sessions:
            issues.append(QualityIssue("error", "trade_calendar_missing_next_session", {"version_date": version_date.isoformat()}))
            continue
        effective = datetime.combine(next_sessions[0], time(15, 0), SHANGHAI).astimezone(timezone.utc).isoformat()
        raw_row_hash = canonical_sha256(row)
        for rule in field_rules(DATASET_TO_STATEMENT[batch.dataset]):
            source_field, numeric = first_finite_numeric(row, rule.source_fields)
            if source_field is None:
                continue
            facts.append(FinancialFact.create(
                security_id=expected_security_id,
                statement=rule.statement,
                metric_key=rule.metric_key,
                period_start=period.period_start if rule.nature == "duration" else None,
                period_end=period.period_end,
                period_kind=period.period_kind,
                value=numeric,
                unit=rule.unit,
                nature=rule.nature,
                announced_at_utc=notice_utc,
                effective_at_utc=effective,
                source_updated_at_utc=update_utc,
                source_snapshot_id=source_snapshot_id,
                source_field=source_field,
                raw_row_hash=raw_row_hash,
                mapping_version=MAPPING_VERSION,
                created_at=created_at_utc,
            ))
    return FactBuildResult(tuple(sorted(facts, key=lambda item: item.id)), tuple(issues))
```

`source_time()` treats a date-only value as 23:59:59 Asia/Shanghai. Use this exact selector declaration:

```python
def select_visible_facts(
    facts: Iterable[FinancialFact],
    *,
    as_of_utc: str,
    snapshot_fetched_at: Mapping[str, str],
) -> FactSelection:
```

Filter `effective_at <= as_of` and group by `(security_id, metric_key, period_end)`. Within each group, compute the maximum version rank `(effective_at, source_updated_at or announced_at, snapshot_fetched_at[source_snapshot_id])` **without** the fact ID. Inspect every fact tied at that top rank: differing finite values, units, or natures add `conflicting_fact_versions`/`conflicting_fact_units` and select none. Only when the tied facts are semantically identical may ID be used as the final deterministic deduplication order. This keeps the conflict branch reachable.

After selection, `validate_balance_equation()` checks `|assets - liabilities - equity| <= max(1000, 0.001 * |assets|)`. A material gap adds `balance_equation_mismatch`; mixed units for one logical fact add `conflicting_fact_units`. Both blockers flow unchanged into Task 8.

- [ ] **Step 4: Run normalization tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FinancialFactSelectionTests -v
```

Expected: PASS.

- [ ] **Step 5: Commit fact normalization and fixtures**

```powershell
git add -- ashare_pipeline/financial_features.py tests/test_financial_features.py tests/fixtures/financial
git commit -m "feat: normalize point-in-time financial facts"
```

---

### Task 8: Derived Inputs, Coverage, and Feature-Bundle Construction

**Files:**
- Modify: `ashare_pipeline/financial_features.py`
- Modify: `tests/test_financial_features.py`

**Interfaces:**
- Consumes: selected facts/blockers from Task 7, templates from Task 2, and contract types from Task 1.
- Produces: `FORMULA_VERSION`, `symmetric_growth()`, `positive_cagr()`, `feature_input_hash()`, and `build_feature_bundle()`.

- [ ] **Step 1: Add failing hand-calculation and safety tests**

```python
def test_general_bundle_computes_hand_checked_inputs(self):
    bundle = build_feature_bundle(
        security_id="SH600001",
        report_period="2026-06-30",
        as_of_utc="2026-08-29T16:00:00+00:00",
        candidate_set_hash="c" * 64,
        source_industry_name="包装印刷",
        facts=hand_checked_general_facts(),
        fact_blockers=(),
        statement_snapshot_hashes={
            "balance_sheet": "1" * 64,
            "profit_sheet": "2" * 64,
            "cash_flow_sheet": "3" * 64,
        },
        trade_calendar_snapshot_hash="4" * 64,
        reported_target_period=True,
    )
    values = {
        value.key: value.value
        for dimension in bundle.dimension_inputs.values()
        for value in dimension.values
    }
    self.assertEqual(values["m.gross_profit.FY2025"], 400.0)
    self.assertEqual(values["m.ebit.FY2025"], 250.0)
    self.assertEqual(values["m.effective_tax_rate.FY2025"], 0.2)
    self.assertEqual(values["m.nopat.FY2025"], 200.0)
    self.assertEqual(values["ca.fcf.FY2025"], 130.0)
    self.assertEqual(values["fs.interest_bearing_debt.FY2025"], 500.0)
    self.assertEqual(values["fs.net_debt.FY2025"], 400.0)
    self.assertEqual(values["m.invested_capital.FY2025"], 1_000.0)
    self.assertAlmostEqual(values["eq.total_accruals.FY2025"], -20.0 / 900.0)
    self.assertAlmostEqual(values["m.roic.FY2025"], 200.0 / 900.0)
    self.assertEqual(values["m.gross_margin.FY2025"], 0.4)


def test_growth_edges_do_not_invent_denominators(self):
    self.assertAlmostEqual(symmetric_growth(120.0, 100.0), 18.181818181818183)
    self.assertEqual(symmetric_growth(100.0, -100.0), 200.0)
    self.assertIsNone(symmetric_growth(0.0, 0.0))
    self.assertAlmostEqual(positive_cagr(100.0, 133.1, 3), 10.0)
    self.assertIsNone(positive_cagr(0.0, 133.1, 3))


def test_fact_blockers_survive_verbatim_and_keep_bundle_blocked(self):
    bundle = build_bundle_with_overrides(
        fact_blockers=("conflicting_fact_versions", "trade_calendar_missing_next_session")
    )
    self.assertEqual(
        bundle.blockers,
        (
            "conflicting_fact_versions",
            "formal_industry_mapping_missing",
            "trade_calendar_missing_next_session",
        ),
    )
    self.assertEqual(bundle.financial_status, "blocked")
```

Add tests for missing denominator/fact, every required period, no industrial ROIC/debt slots in bank bundles, real-estate applicability, unclassified blocking, V/T missing containers, formal confidence null, no `S0/Sc/pool` keys, coverage treatment, and hash sensitivity to every declared dependency.

- [ ] **Step 2: Run bundle tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FeatureBundleBuildTests -v
```

Expected: FAIL with missing formula and bundle-builder functions.

- [ ] **Step 3: Implement formulas and the frozen input hash**

```python
FORMULA_VERSION = "financial-derived-v1"


def symmetric_growth(current: float, previous: float) -> float | None:
    denominator = abs(current) + abs(previous)
    if denominator == 0:
        return None
    return 200.0 * (current - previous) / denominator


def positive_cagr(start: float, end: float, years: int) -> float | None:
    if start <= 0 or end <= 0 or years <= 0:
        return None
    return 100.0 * ((end / start) ** (1.0 / years) - 1.0)


def feature_input_hash(
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    candidate_set_hash: str,
    statement_snapshot_hashes: Mapping[str, str | None],
    trade_calendar_snapshot_hash: str | None,
) -> str:
    snapshots = {
        dataset: statement_snapshot_hashes.get(dataset)
        for dataset in ("balance_sheet", "profit_sheet", "cash_flow_sheet")
    }
    return canonical_sha256({
        "security_id": security_id,
        "report_period": report_period,
        "as_of_utc": as_of_utc,
        "candidate_set_hash": candidate_set_hash,
        "statement_snapshot_hashes": snapshots,
        "trade_calendar_snapshot_hash": trade_calendar_snapshot_hash,
        "contract_version": CONTRACT_VERSION,
        "mapping_version": MAPPING_VERSION,
        "template_version": TEMPLATE_VERSION,
        "formula_version": FORMULA_VERSION,
    })
```

Omitting a statement key is not equivalent to explicit null: normalize all three keys before hashing. `candidate_set_hash` already commits to the prefilter inputs and each sorted performance-row hash, including the target-period disclosure state; therefore the pure bundle builder may consume `reported_target_period` without adding a second unapproved hash dependency.

- [ ] **Step 4: Implement deterministic feature construction**

Use this exact public signature:

```python
def build_feature_bundle(
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    candidate_set_hash: str,
    source_industry_name: str,
    facts: Iterable[FinancialFact],
    fact_blockers: Sequence[str],
    statement_snapshot_hashes: Mapping[str, str | None],
    trade_calendar_snapshot_hash: str | None,
    reported_target_period: bool,
) -> FeatureBundle:
    selected = tuple(sorted(facts, key=lambda item: (
        item.metric_key, item.period_end, item.effective_at_utc, item.id
    )))
    template = resolve_template(source_industry_name)
    financial_blockers = set(fact_blockers)
    formal_blockers = {"formal_industry_mapping_missing"}
    if template.template_id == "unclassified":
        financial_blockers.add("industry_template_unclassified")
    if trade_calendar_snapshot_hash is None:
        financial_blockers.add("trade_calendar_missing")
    missing_statement = any(
        statement_snapshot_hashes.get(dataset) is None
        for dataset in ("balance_sheet", "profit_sheet", "cash_flow_sheet")
    )
    cutoff = datetime.fromisoformat("2026-08-31T23:59:59+08:00")
    as_of = datetime.fromisoformat(as_of_utc.replace("Z", "+00:00"))
    if reported_target_period and missing_statement and as_of > cutoff:
        financial_blockers.add("reported_but_statement_missing")
    input_hash = feature_input_hash(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=as_of_utc,
        candidate_set_hash=candidate_set_hash,
        statement_snapshot_hashes=statement_snapshot_hashes,
        trade_calendar_snapshot_hash=trade_calendar_snapshot_hash,
    )
    return assemble_bundle_from_registered_slots(
        security_id=security_id,
        report_period=report_period,
        as_of_utc=as_of_utc,
        candidate_set_hash=candidate_set_hash,
        input_hash=input_hash,
        template=template,
        facts=selected,
        financial_blockers=tuple(sorted(financial_blockers)),
        blockers=tuple(sorted(financial_blockers | formal_blockers)),
    )
```

`assemble_bundle_from_registered_slots()` computes only the approved accounting formulas: gross profit, EBIT, bounded actual tax rate, NOPAT, FCF, interest-bearing debt, net debt, invested capital, operating working capital, total accruals, ROIC, gross margin, symmetric growth, and positive-endpoint CAGR. Average assets/invested capital use simple opening/closing averages. If any required operand or valid denominator is absent, emit a missing `FeatureValue` with its expected non-null unit and evidence-free reason.

Coverage is `(observed + derived) / (observed + derived + missing + blocked)`; not-applicable slots are excluded. Zero applicable slots yields 0 and blocked. `financial_ready` requires all seven periods, every applicable financial slot, a classified template, and no financial blocker. The separate `formal_industry_mapping_missing` blocker is always present because this phase has only provisional source-industry labels; it keeps formal scoring closed but does not by itself turn financially complete inputs into `blocked`. Always create all seven dimensions: V and T remain missing because this phase has neither market valuation nor buy-point evidence, while CA contains only actually observed accounting allocation inputs such as FCF, dividends, financing, debt repayment, and repurchase cash flows. The bundle remains non-formal.

- [ ] **Step 5: Run all financial-feature tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_financial_features -v
```

Expected: PASS.

- [ ] **Step 6: Commit formulas and bundle construction**

```powershell
git add -- ashare_pipeline/financial_features.py tests/test_financial_features.py
git commit -m "feat: build deterministic financial feature bundles"
```

---

### Task 9: Isolated AKShare Statement Fetching

**Files:**
- Modify: `ashare_pipeline/sources.py:195-265`
- Modify: `tests/test_sources.py`
- Modify: `tests/test_pilot.py`

**Interfaces:**
- Consumes: existing `FetchBatch`, error taxonomy, and Task 2 statement dataset names.
- Produces: `FinancialStatementSource`, `AKShareSource.fetch_financial_statement()`; preserves `fetch_financial_statements()`.

- [ ] **Step 1: Add one-call, validation, empty-result, and wrapper tests**

```python
def test_fetch_financial_statement_calls_exactly_one_requested_method(self):
    for dataset, expected_call in (
        ("balance_sheet", "balance"),
        ("profit_sheet", "profit"),
        ("cash_flow_sheet", "cash"),
    ):
        with self.subTest(dataset=dataset):
            module = FakeAKShare()
            batch = AKShareSource(module=module).fetch_financial_statement(
                "SH600000", dataset, "2026-06-30"
            )
            self.assertEqual([name for name, _ in module.calls], [expected_call])
            self.assertEqual(batch.dataset, dataset)
            self.assertEqual(batch.request, {
                "symbol": "SH600000",
                "report_period": "2026-06-30",
            })
            self.assertEqual(batch.metadata["report_period_match_count"], 1)


def test_fetch_financial_statement_rejects_unknown_dataset_before_network(self):
    module = FakeAKShare()
    with self.assertRaisesRegex(ValueError, "unsupported financial dataset"):
        AKShareSource(module=module).fetch_financial_statement(
            "SH600000", "unknown_sheet", "2026-06-30"
        )
    self.assertEqual(module.calls, [])
```

Set a fake statement to an empty frame and require `RetryableSourceError`. Keep the existing three-table test and assert the compatibility wrapper calls the new method in balance/profit/cash order.

- [ ] **Step 2: Run source tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sources.SourcesTestCase.test_fetch_financial_statement_calls_exactly_one_requested_method -v
```

Expected: FAIL with missing method.

- [ ] **Step 3: Implement the single-table contract**

```python
class FinancialStatementSource(Protocol):
    def fetch_financial_statement(
        self,
        symbol: str,
        dataset: str,
        report_period: str = "2026-06-30",
    ) -> FetchBatch:
        raise NotImplementedError


def fetch_financial_statement(
    self,
    symbol: str,
    dataset: str,
    report_period: str = "2026-06-30",
) -> FetchBatch:
    methods = {
        "balance_sheet": "stock_balance_sheet_by_report_em",
        "profit_sheet": "stock_profit_sheet_by_report_em",
        "cash_flow_sheet": "stock_cash_flow_sheet_by_report_em",
    }
    if dataset not in methods:
        raise ValueError(f"unsupported financial dataset: {dataset}")
    request = {"symbol": symbol, "report_period": report_period}
    method_name = methods[dataset]
    batch = self._batch(
        dataset,
        request,
        lambda module: getattr(module, method_name)(symbol=symbol),
        require_rows=True,
    )
    matches = sum(str(row.get("REPORT_DATE", ""))[:10] == report_period for row in batch.records)
    metadata = {
        "report_period_match_count": matches,
        "column_count": len(batch.records[0]) if batch.records else 0,
        "NOTICE_DATE": [row.get("NOTICE_DATE") for row in batch.records if row.get("NOTICE_DATE") is not None],
        "UPDATE_DATE": [row.get("UPDATE_DATE") for row in batch.records if row.get("UPDATE_DATE") is not None],
    }
    return FetchBatch(
        batch.source, batch.dataset, batch.request, batch.records,
        batch.fetched_at_utc, batch.source_version, metadata,
    )
```

Rewrite `fetch_financial_statements()` as a fixed-order dictionary comprehension over the three allowed datasets. Do not change pilot callers.

- [ ] **Step 4: Run all source and pilot tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sources tests.test_pilot -v
```

Expected: PASS.

- [ ] **Step 5: Commit the source change**

```powershell
git add -- ashare_pipeline/sources.py tests/test_sources.py tests/test_pilot.py
git commit -m "feat: expose isolated financial statement fetches"
```

---

### Task 10: Candidate Context and Legacy Parent Expansion

**Files:**
- Create: `ashare_pipeline/deep_worker.py`
- Create: `tests/test_deep_worker.py`

**Interfaces:**
- Consumes: Task 1 hashing, Task 2 request constants, and Task 5 atomic follow-ups.
- Produces: `STATEMENT_DATASETS`, `CandidateContext`, `build_candidate_context()`, `load_candidate_context()`, `deep_statement_key()`, `feature_build_key()`, `statement_job_specs()`, and `expand_deep_parents()`.

- [ ] **Step 1: Add failing 120-to-360 and candidate-hash tests**

```python
def test_old_parent_expands_to_three_dated_unique_statement_jobs(self):
    context = candidate_context({"SH600001"})
    parent_id = self.store.enqueue_job(
        "deep_financial",
        "legacy:SH600001",
        {"security_id": "SH600001", "report_period": "2026-06-30", "input_hash": "a" * 64},
    )
    summary = expand_deep_parents(
        self.store,
        context,
        as_of_cn_date="2026-08-29",
        worker_id="planner",
    )
    self.assertEqual(summary, {"expanded": 1, "superseded": 0, "children": 3})
    self.assertEqual(self.store.get_job(parent_id)["result"]["outcome"], "expanded")
    keys = {job["idempotency_key"] for job in self.store.list_jobs(["deep_statement"])}
    self.assertEqual(keys, {
        "deep_statement:v1:SH600001:balance_sheet:2026-06-30:2026-08-29",
        "deep_statement:v1:SH600001:profit_sheet:2026-06-30:2026-08-29",
        "deep_statement:v1:SH600001:cash_flow_sheet:2026-06-30:2026-08-29",
    })


def test_reexpansion_is_idempotent_and_120_parents_make_360_children(self):
    context = candidate_context({f"SH{index:06d}" for index in range(1, 121)})
    for security_id in context.members:
        self.store.enqueue_job(
            "deep_financial", f"legacy:{security_id}",
            {"security_id": security_id, "report_period": "2026-06-30"},
        )
    expand_deep_parents(self.store, context, as_of_cn_date="2026-08-29", worker_id="planner")
    expand_deep_parents(self.store, context, as_of_cn_date="2026-08-29", worker_id="planner")
    self.assertEqual(len(self.store.list_jobs(["deep_statement"])), 360)
```

Add tests for superseded securities, transaction rollback, candidate hash order independence, and exact inclusion of prefilter input hashes plus sorted `(security_id, performance_input_hash)` pairs.

- [ ] **Step 2: Run parent-expansion test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_old_parent_expands_to_three_dated_unique_statement_jobs -v
```

Expected: FAIL because `deep_worker` does not exist.

- [ ] **Step 3: Implement deterministic candidate context and keys**

```python
STATEMENT_DATASETS = ("balance_sheet", "profit_sheet", "cash_flow_sheet")


@dataclass(frozen=True)
class CandidateContext:
    candidate_set_hash: str
    members: frozenset[str]
    performance_input_hashes: Mapping[str, str]
    industries: Mapping[str, str]
    reported_target_period: Mapping[str, bool]


def deep_statement_key(
    security_id: str,
    dataset: str,
    report_period: str,
    as_of_cn_date: str,
) -> str:
    if dataset not in STATEMENT_DATASETS:
        raise ValueError(f"unsupported statement dataset: {dataset}")
    return f"deep_statement:v1:{security_id}:{dataset}:{report_period}:{as_of_cn_date}"


def feature_build_key(
    security_id: str,
    report_period: str,
    input_hash: str,
) -> str:
    return f"feature_build:v1:{security_id}:{report_period}:{input_hash}"
```

`build_candidate_context()` canonicalizes the prefilter input hashes and sorted performance-row hashes, derives `reported_target_period[security_id]` from membership in the curated 2026H1 performance document, and fails closed if a selected candidate has no corresponding performance record. `statement_job_specs()` creates three `JobSpec` values. The child key intentionally excludes candidate hash: if the candidate set changes during one date, reuse the same fetch job; its payload's candidate hash is first-enqueue audit evidence only. Feature builds always use the runtime current context.

- [ ] **Step 4: Implement legacy parent expansion**

Lease `deep_financial` jobs until none remain. For a current member, complete it with three child follow-ups and `{"outcome":"expanded","child_count":3}`; for a removed member, complete it with no children and `{"outcome":"superseded","child_count":0}`. Never call a source. Use Task 5's atomic API so a partial child set cannot coexist with a succeeded parent.

- [ ] **Step 5: Run deep-worker planning tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_old_parent_expands_to_three_dated_unique_statement_jobs tests.test_deep_worker.DeepWorkerTestCase.test_reexpansion_is_idempotent_and_120_parents_make_360_children -v
```

Expected: PASS.

- [ ] **Step 6: Commit the planner**

```powershell
git add -- ashare_pipeline/deep_worker.py tests/test_deep_worker.py
git commit -m "feat: expand legacy deep jobs into statement tasks"
```

---

### Task 11: Deep Statement Worker and Frozen Feature Builds

**Files:**
- Modify: `ashare_pipeline/deep_worker.py`
- Modify: `tests/test_deep_worker.py`

**Interfaces:**
- Consumes: Tasks 4–10, exact verified snapshot refs, and a verified trade-calendar snapshot.
- Produces: `DeepRunSummary`, `enqueue_feature_build()`, `write_feature_bundle()`, `read_verified_feature_bundle()`, and `run_deep()`.

- [ ] **Step 1: Add failing limit, partial-success, frozen-input, and circuit tests**

```python
def test_limit_counts_only_remote_statement_requests(self):
    add_legacy_parents(self.store, count=10)
    source = FakeStatementSource()
    summary = run_deep(
        self.data_root,
        self.store,
        source=source,
        snapshots=self.repository,
        trade_calendar_snapshot=self.calendar_ref,
        now_cn=datetime(2026, 8, 29, 20, 0, tzinfo=SHANGHAI),
        online=True,
        limit=1,
        worker_id="worker-a",
        lease_seconds=2,
        heartbeat_seconds=0.05,
    )
    self.assertEqual(summary.remote_attempts, 1)
    self.assertEqual(len(source.calls), 1)
    self.assertEqual(len(self.store.list_jobs(["deep_statement"])), 30)


def test_second_statement_failure_preserves_first_snapshot_and_partial_bundle(self):
    source = FakeStatementSource(failures={"profit_sheet": RetryableSourceError("temporary")})
    summary = run_fixture_candidate(self, source=source, online=True, limit=3)
    balance = self.repository.find_exact("akshare", "balance_sheet", statement_request("SH600001"))
    cash = self.repository.find_exact("akshare", "cash_flow_sheet", statement_request("SH600001"))
    self.assertIsNotNone(balance)
    self.assertIsNotNone(cash)
    self.assertEqual(summary.retryable_failed, 1)
    feature = self.store.latest_feature_set("SH600001", "2026-06-30")
    self.assertEqual(feature["status"], "partial")


def test_feature_build_reads_frozen_snapshot_ids_not_later_latest(self):
    frozen = persist_three_statements(self, profit_value=100.0)
    job_id = enqueue_feature_build_for_refs(self, frozen)
    persist_revised_profit(self, profit_value=999.0)
    run_one_feature_build(self, job_id)
    feature = self.store.latest_feature_set("SH600001", "2026-06-30")
    self.assertEqual(feature["input_hash"], frozen["input_hash"])
    self.assertNotIn("999.0", read_bundle_text(self, feature))
```

Add tests for real heartbeat renewal during a blocked fake call, expired-lease recovery, reuse of an exact same-date snapshot, date-refresh dedup by content hash, SourceBlocked round circuit, malformed statement terminal issue, target-period missing retry before cutoff/terminal after cutoff, old feature version retention, no raw marker leakage, and offline mode never constructing a source.

- [ ] **Step 2: Run worker execution tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_limit_counts_only_remote_statement_requests -v
```

Expected: FAIL because execution APIs do not exist.

- [ ] **Step 3: Implement frozen feature-build payloads**

Use these exact public declarations:

```python
def enqueue_feature_build(
    store: StateStore,
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    candidate_context: CandidateContext,
    statement_snapshots: Mapping[str, SnapshotRef | None],
    trade_calendar_snapshot: SnapshotRef | None,
) -> str:


def write_feature_bundle(
    project_root: str | Path,
    bundle: FeatureBundle,
) -> tuple[str, str, bool]:


def read_verified_feature_bundle(
    project_root: str | Path,
    relative_path: str,
    expected_hash: str,
) -> FeatureBundle:
```

`write_feature_bundle()` returns `(project_relative_path, bundle_hash, created)`.

Every `feature_build` payload stores exact source evidence:

```python
def frozen_snapshot_payload(snapshot: SnapshotRef | None) -> dict[str, str] | None:
    if snapshot is None:
        return None
    return {"source_snapshot_id": snapshot.id, "payload_hash": snapshot.payload_hash}


def feature_build_payload(
    *,
    security_id: str,
    report_period: str,
    as_of_utc: str,
    context: CandidateContext,
    statement_snapshots: Mapping[str, SnapshotRef | None],
    trade_calendar_snapshot: SnapshotRef | None,
) -> dict[str, object]:
    return {
        "security_id": security_id,
        "report_period": report_period,
        "as_of_utc": as_of_utc,
        "candidate_set_hash": context.candidate_set_hash,
        "industry": context.industries[security_id],
        "reported_target_period": context.reported_target_period[security_id],
        "performance_input_hash": context.performance_input_hashes[security_id],
        "statement_snapshots": {
            dataset: frozen_snapshot_payload(statement_snapshots.get(dataset))
            for dataset in STATEMENT_DATASETS
        },
        "trade_calendar_snapshot": frozen_snapshot_payload(trade_calendar_snapshot),
    }
```

Compute the feature input hash with Task 8's exact function from the frozen candidate-set, statement, calendar, and version dependencies, then use it in `feature_build_key()`. The per-security performance hash is retained as audit evidence and must be consistent with the frozen candidate context; it is already committed by `candidate_set_hash` and is not hashed twice. Execution calls `SnapshotRepository.get(snapshot_id)`, verifies the stored hash equals the frozen hash, and never calls `find_exact()` for an already-enqueued feature build.

- [ ] **Step 4: Implement lease heartbeat and bounded run summary**

```python
@dataclass(frozen=True)
class DeepRunSummary:
    expanded: int
    superseded: int
    remote_attempts: int
    snapshots_reused: int
    statements_succeeded: int
    retryable_failed: int
    terminal_failed: int
    feature_sets_written: int
    circuit_breakers: tuple[str, ...]
    items: tuple[Mapping[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "expanded": self.expanded,
            "superseded": self.superseded,
            "remote_attempts": self.remote_attempts,
            "snapshots_reused": self.snapshots_reused,
            "statements_succeeded": self.statements_succeeded,
            "retryable_failed": self.retryable_failed,
            "terminal_failed": self.terminal_failed,
            "feature_sets_written": self.feature_sets_written,
            "circuit_breakers": list(self.circuit_breakers),
            "items": [dict(item) for item in self.items],
        }
```

Add a context manager that starts one daemon thread per leased remote job, calls `renew_job_lease()` every heartbeat interval, and always joins/stops in `finally`. Default lease is 900 seconds and heartbeat 60 seconds. `items` may contain only security ID, dataset, snapshot hash, bundle hash, outcome, and error classification.

- [ ] **Step 5: Implement statement and feature-build execution**

Use this exact public entry point:

```python
def run_deep(
    root: str | Path,
    store: StateStore,
    *,
    source: FinancialStatementSource | None,
    snapshots: SnapshotRepository,
    trade_calendar_snapshot: SnapshotRef | None,
    now_cn: datetime,
    online: bool,
    limit: int,
    worker_id: str = "deep-worker",
    lease_seconds: int = 900,
    heartbeat_seconds: float = 60.0,
) -> DeepRunSummary:
    if not 1 <= limit <= 360:
        raise ValueError("limit must be between 1 and 360")
    context = load_candidate_context(root)
    store.recover_expired_leases(now_cn.astimezone(timezone.utc).isoformat())
    planning = expand_deep_parents(
        store, context, as_of_cn_date=now_cn.date().isoformat(), worker_id=worker_id
    )
    return execute_queued_deep_work(
        root=Path(root),
        store=store,
        context=context,
        source=source,
        snapshots=snapshots,
        trade_calendar_snapshot=trade_calendar_snapshot,
        now_cn=now_cn,
        online=online,
        limit=limit,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        planning=planning,
    )
```

The private executor called by `run_deep()` has the exact keyword-only declaration below and returns the same summary type:

```python
def execute_queued_deep_work(
    *,
    root: Path,
    store: StateStore,
    context: CandidateContext,
    source: FinancialStatementSource | None,
    snapshots: SnapshotRepository,
    trade_calendar_snapshot: SnapshotRef | None,
    now_cn: datetime,
    online: bool,
    limit: int,
    worker_id: str,
    lease_seconds: int,
    heartbeat_seconds: float,
    planning: Mapping[str, int],
) -> DeepRunSummary:
```

Execution order is fixed:

1. Process queued `feature_build` jobs offline; these do not consume remote limit.
2. If `online=False`, return without constructing/calling AKShare.
3. Lease one `deep_statement`; if a verified snapshot was already fetched on its refresh date, reuse it.
4. Otherwise count one remote attempt, heartbeat while fetching one table, persist immediately, normalize facts, and record issues.
5. Freeze all current exact statement refs plus the calendar ref.
6. Complete or fail the statement and enqueue its feature build in the same Task 5 transaction.
7. Process that feature build from frozen refs.
8. On SourceBlocked, record `akshare` in the summary circuit and leave later statement jobs pending.

Before cutoff, a verified table without target 2026H1 is retryable at `now + 6 hours`; after cutoff it is terminal. Missing historical periods still completes the source job and creates a partial bundle. Bundle status is derived only from hashed inputs, not retry/terminal job state.

- [ ] **Step 6: Implement atomic feature files**

Write canonical bytes to:

```text
data/curated/formal_features/2026-06-30/<security_id>/<input_hash>.json
```

Use `tempfile.mkstemp()`, flush, `os.fsync()`, and hash/parse the part file. Never overwrite a target that already exists: verify the existing bundle first and reuse it only when both canonical bytes and hash match; otherwise raise `non-deterministic feature conflict` while leaving the old bytes untouched. For a new target, use an atomic no-replace operation (same-directory hard-link creation is acceptable), handle a race by verifying the winner, and remove the part file in `finally`.

Only after file verification call `put_feature_bundle()`. If the database transaction fails and this call created the target, query `get_feature_bundle_row()`; delete the new file only when no committed row references that exact path/hash, then re-raise. Add tests named `test_existing_feature_conflict_preserves_original_file` and `test_database_failure_removes_new_orphan_feature_file`. Store the path relative to project root; a DB row must never point to a missing file.

- [ ] **Step 7: Run all deep-worker tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_deep_worker -v
```

Expected: PASS.

- [ ] **Step 8: Commit the worker**

```powershell
git add -- ashare_pipeline/deep_worker.py tests/test_deep_worker.py
git commit -m "feat: execute resumable deep financial feature builds"
```

---

### Task 12: Deep CLI, Long Trade Calendar, and Scoped Progress

**Files:**
- Modify: `ashare_pipeline/orchestrator.py:27-35,143-180,517-620,842-957`
- Modify: `tests/test_orchestrator.py`
- Modify: `ashare_pipeline/reporting.py`
- Modify: `tests/test_reporting.py`

**Interfaces:**
- Consumes: `run_deep()`, `SnapshotRepository`, Task 2 request version, and current curated candidate documents.
- Produces: `deep [--online] [--limit 1..360]`, `enqueue_daily_statement_jobs()`, `build_deep_progress()`, long calendar snapshots, and current-candidate feature progress.

- [ ] **Step 1: Add failing parser, offline, limit, and status tests**

```python
def test_deep_parser_accepts_limit_bounds_and_rejects_outside(self):
    self.assertEqual(
        orchestrator._parser().parse_args(
            ["--root", "data", "--db", "data/state.sqlite3", "deep"]
        ).limit,
        10,
    )
    for valid in (1, 360):
        parsed = orchestrator._parser().parse_args(
            ["--root", "data", "--db", "data/state.sqlite3", "deep", "--limit", str(valid)]
        )
        self.assertEqual(parsed.limit, valid)
    for invalid in (0, 361):
        with self.assertRaises(SystemExit):
            orchestrator._parser().parse_args(
                ["--root", "data", "--db", "data/state.sqlite3", "deep", "--limit", str(invalid)]
            )


def test_status_financial_coverage_requires_three_verified_target_snapshots(self):
    seed_two_candidate_snapshot_states(self)
    status, code = orchestrator.run_command(
        self.root, self.db, "status", now_cn="2026-08-29T20:00:00+08:00"
    )
    self.assertEqual(code, 0)
    self.assertEqual(status["deep"]["candidate_financial_coverage"], {
        "numerator": 1,
        "denominator": 2,
        "rate": 0.5,
    })
    self.assertEqual(len(status["deep"]["incomplete_candidates"]), 1)
    self.assertEqual(
        status["deep"]["incomplete_candidates"][0]["missing_datasets"],
        ["cash_flow_sheet"],
    )
    self.assertEqual(status["deep"]["expired_current_lease_count"], 0)
    self.assertEqual(status["deep"]["unknown_failure_count"], 0)
    self.assertFalse(status["formal_score_ready"])
```

Also add these named tests with injected raising factories/fakes: `test_offline_deep_constructs_no_source`, `test_verified_calendar_cache_and_injected_deep_source_construct_no_defaults`, `test_tampered_calendar_cache_fails_closed`, `test_changed_calendar_request_is_not_hidden_by_cached_short_job`, `test_online_limit_one_calls_at_most_one_statement`, `test_incremental_enqueues_without_statement_calls`, and `test_progress_excludes_stale_request_versions`. Each fake records constructor and method calls; assert exact empty/call-count lists, not log text. Keep existing formal-score/finalization assertions unchanged.

- [ ] **Step 2: Run the parser test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_orchestrator.OrchestratorTestCase.test_deep_parser_accepts_limit_bounds_and_rejects_outside -v
```

Expected: FAIL because the parser has no `deep` command.

- [ ] **Step 3: Add the long verified trade-calendar request**

Define:

```python
FEATURE_CALENDAR_START = date(2021, 1, 1)
FEATURE_CALENDAR_MIN_END = date(2026, 9, 7)
FEATURE_CALENDAR_REQUEST_VERSION = "trade-calendar-feature-v1"


def _feature_calendar_end(now: datetime) -> str:
    return max(now.date() + timedelta(days=10), FEATURE_CALENDAR_MIN_END).isoformat()


def _feature_calendar_request(now: datetime) -> dict[str, str]:
    return {
        "start_date": FEATURE_CALENDAR_START.isoformat(),
        "end_date": _feature_calendar_end(now),
    }


def _feature_calendar_job_key(now: datetime) -> str:
    request_hash = canonical_sha256(_feature_calendar_request(now))
    return f"collect:baostock:trade_dates:{FEATURE_CALENDAR_REQUEST_VERSION}:{request_hash}"
```

Change the canonical BaoStock calendar batch to request `2021-01-01` through `_feature_calendar_end(now)`. Its collection job must use `_feature_calendar_job_key(now)`, not the old source/dataset/day key; this prevents an already-succeeded short-calendar job from hiding the versioned request. Persist it through `SnapshotRepository`; a missing or unverifiable calendar is an explicit feature blocker. Update old tests that asserted the short 2026-08-24 request. Never synthesize holidays from weekdays.

- [ ] **Step 4: Enqueue current daily statement jobs without remote calls**

After rebuilding curated candidates, call this exact helper:

```python
def enqueue_daily_statement_jobs(
    store: StateStore,
    context: CandidateContext,
    report_period: str,
    as_of_cn_date: str,
) -> tuple[str, ...]:
    job_ids: list[str] = []
    for security_id in sorted(context.members):
        for dataset in STATEMENT_DATASETS:
            job_ids.append(store.enqueue_job(
                "deep_statement",
                deep_statement_key(security_id, dataset, report_period, as_of_cn_date),
                {
                    "security_id": security_id,
                    "dataset": dataset,
                    "report_period": report_period,
                    "candidate_set_hash": context.candidate_set_hash,
                    "performance_input_hash": context.performance_input_hashes[security_id],
                    "request_version": FINANCIAL_REQUEST_VERSION,
                    "refresh_date": as_of_cn_date,
                },
            ))
    return tuple(job_ids)
```

It inserts exactly one `deep_statement` per current member/dataset/date and returns IDs in security/dataset order. The child key excludes candidate hash, while first-enqueue payload retains it as audit evidence. Existing legacy parents remain consumable and expand to the same child keys. Test 120 members twice and assert both returned sequences refer to the same 360 database rows with zero source calls.

- [ ] **Step 5: Wire the deep command**

Extend the public `run_command()` signature with `deep_source` and `limit`, then add the following helper and branch. The helper is the only place that may construct online sources, so `deep` without `--online` remains physically incapable of constructing AKShare/BaoStock clients:

```python
def _deep_dependencies(
    root: Path,
    store: StateStore,
    *,
    now: datetime,
    online: bool,
    sources: tuple[Any, Any] | None,
    snapshot_store: Any | None,
    deep_source: FinancialStatementSource | None = None,
) -> tuple[SnapshotRepository, FinancialStatementSource | None, SnapshotRef | None]:
    repository = SnapshotRepository(root, store, snapshot_store)
    request = _feature_calendar_request(now)
    calendar = repository.find_exact("baostock", "trade_dates", request)
    if calendar is not None:
        repository.read_verified(calendar)
    source = None
    if online:
        source = deep_source
        if source is None:
            source = sources[1] if sources is not None else _default_deep_source()
        if calendar is None:
            bao = sources[0] if sources is not None else _default_calendar_source()
            calendar, _ = repository.persist(
                bao.fetch_trade_dates(request["start_date"], request["end_date"])
            )
    return repository, source, calendar


def _default_calendar_source() -> BaoStockSource:
    from .sources import BaoStockSource
    return BaoStockSource()


def _default_deep_source() -> AKShareSource:
    from .sources import AKShareSource
    return AKShareSource()


def _bounded_int(value: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(
            f"value must be between {minimum} and {maximum}"
        )
    return parsed


# Insert this inside the existing try block, after start_run()/write_then_finish().
if command == "deep":
    repository, source, calendar = _deep_dependencies(
        root_path,
        store,
        now=now,
        online=online,
        sources=sources,
        snapshot_store=snapshot_store,
        deep_source=deep_source,
    )
    summary = run_deep(
        root_path,
        store,
        source=source,
        snapshots=repository,
        trade_calendar_snapshot=calendar,
        now_cn=now,
        online=online,
        limit=limit,
    )
    payload = _status_payload(
        root_path,
        store,
        now,
        command,
        "online" if online else "offline",
        circuit_breakers=list(summary.circuit_breakers),
    )
    payload["deep_run"] = summary.to_dict()
    write_then_finish(payload, "succeeded")
    return payload, 0
```

The final public declaration keeps the existing body and adds only these two keyword parameters:

```text
def run_command(
    root: str | Path,
    db: str | Path,
    command: str,
    *,
    online: bool = False,
    now_cn: str | None = None,
    sources: tuple[Any, Any] | None = None,
    snapshot_store: Any | None = None,
    deep_source: Any | None = None,
    limit: int = 10,
) -> tuple[dict, int]
```

Retain `status`, `finalize`, `bootstrap`, and `incremental` behavior exactly, and insert the concrete `deep` branch shown above. Include `limit` in the run configuration recorded by `start_run()`. A valid exact calendar is verified and reused across repeated deep batches; a tampered exact cache fails closed and is never silently replaced. BaoStock is called only when that exact cache is absent, and its call is not a financial-statement attempt, so it does not consume `--limit`.

Add parser `deep` options using `type=lambda value: _bounded_int(value, 1, 360)`. Pass `limit` through `main()`.

- [ ] **Step 6: Add current-context progress**

Implement the progress builder with this exact declaration:

```python
def build_deep_progress(
    data_root: Path,
    store: StateStore,
    repository: SnapshotRepository,
    context: CandidateContext,
    now: datetime,
) -> dict[str, object]:
```

It returns the following stable contract; `_status_payload()` places the progress under `deep` and emits the three top-level formal fields:

```json
{
  "formal_score_ready": false,
  "seven_dimension_ready": false,
  "official_pool_counts": {"waiting_price": 0, "strong_attention": 0},
  "deep": {
    "deep_candidate_count": 120,
    "deep_parent_job_counts": {},
    "deep_statement_job_counts": {
      "balance_sheet": {},
      "profit_sheet": {},
      "cash_flow_sheet": {}
    },
    "statement_snapshot_counts": {},
    "feature_set_counts": {
      "partial": 0,
      "financial_ready": 0,
      "blocked": 0
    },
    "candidate_financial_coverage": {
      "numerator": 0,
      "denominator": 120,
      "rate": 0.0
    },
    "incomplete_candidates": [],
    "expired_current_lease_count": 0,
    "unknown_failure_count": 0,
    "active_circuit_breakers": [],
    "template_counts": {},
    "missing_reason_counts": {},
    "latest_feature_contract_version": "feature-contract-v1"
  }
}
```

Scope child jobs by current member, request version, and refresh date—not by the first-enqueue candidate hash. Count a candidate in the numerator only when all three exact verified snapshots contain 2026H1. For every non-counted member emit one sorted `incomplete_candidates` item with exactly `security_id`, `missing_datasets`, `job_states`, and statement-level `error_classifications`; allowed classifications are `pending`, `retryable_network`, `source_blocked`, `terminal_source_missing`, `unverified_snapshot`, and `target_period_missing`. Template/feature blockers do not explain statement coverage and remain in feature-set counts.

Derive `active_circuit_breakers` from current retryable jobs whose stored `source_blocked` retry window has not expired, so a later standalone `status` command preserves circuit state. Count expired current leases and any failure outside the allowed taxonomy explicitly. Scope feature sets to current candidate hash/contract. Require `len(incomplete_candidates) == denominator - numerator`; sort items and all nested lists. Do not aggregate all historical score items into current deep progress.

Expose the same bounded counts in `reporting.py` operational rows if present, but do not add individual financial values. Keep `seven_dimension_ready=false`, `formal_score_ready=false`, and pool counts zero.

- [ ] **Step 7: Run orchestrator and reporting tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_orchestrator tests.test_reporting -v
```

Expected: PASS.

- [ ] **Step 8: Commit CLI and progress**

```powershell
git add -- ashare_pipeline/orchestrator.py ashare_pipeline/reporting.py tests/test_orchestrator.py tests/test_reporting.py
git commit -m "feat: expose bounded deep collection and progress"
```

---

### Task 13: Three-Security Hermetic Replay and Full Regression

**Files:**
- Create: `tests/test_feature_foundation_e2e.py`
- Create: `tests/feature_fixture_helpers.py`
- Modify: `progress.md`

**Interfaces:**
- Consumes: all prior tasks and the fixed industrial, bank, real-estate/missing fixtures.
- Produces: a hermetic fake-source proof, a true offline frozen-job proof, and an updated execution ledger; no new production interface.

- [ ] **Step 1: Write the failing hermetic and offline replay tests**

```python
class FeatureFoundationEndToEndTests(unittest.TestCase):
    def test_three_security_replay_is_traceable_deterministic_and_nonformal(self):
        harness = HermeticDeepHarness(
            candidates={
                "SH600001": "包装印刷",
                "SZ000001": "银行",
                "SH600002": "房地产开发",
            },
            fixture_names={
                "SH600001": "general_nonfinancial_statements.json",
                "SZ000001": "bank_statements.json",
                "SH600002": "real_estate_statements.json",
            },
            missing_datasets={"SH600002": {"cash_flow_sheet"}},
        )
        first = harness.run()
        second = harness.run()
        self.assertEqual(first.bundle_bytes, second.bundle_bytes)
        self.assertEqual(first.feature_set_count, second.feature_set_count)
        for bundle in first.bundles:
            self.assertFalse(bundle.is_formal_score_ready)
            self.assertEqual(set(bundle.dimension_inputs), {"G", "V", "M", "EQ", "FS", "CA", "T"})
            for dimension in bundle.dimension_inputs.values():
                for value in dimension.values:
                    for ref in value.evidence:
                        fact = harness.store.list_financial_facts(bundle.security_id)
                        self.assertIn(ref.financial_fact_id, {item.id for item in fact})
                        self.assertIsNotNone(harness.repository.get(ref.source_snapshot_id))
        missing = next(item for item in first.bundles if item.security_id == "SH600002")
        self.assertEqual(missing.financial_status, "blocked")
        self.assertIn("reported_but_statement_missing", missing.blockers)
        self.assertNotIn("S0", repr(first.bundles))
        self.assertNotIn("Sc", repr(first.bundles))
        self.assertFalse(first.status["formal_score_ready"])
        self.assertFalse(first.status["seven_dimension_ready"])
        self.assertEqual(
            first.status["official_pool_counts"],
            {"waiting_price": 0, "strong_attention": 0},
        )

    def test_frozen_feature_job_rebuilds_with_online_false(self):
        harness = HermeticDeepHarness.single_general_candidate()
        harness.enqueue_frozen_feature_job()
        summary = run_deep(
            harness.data_root,
            harness.store,
            source=None,
            snapshots=harness.repository,
            trade_calendar_snapshot=harness.calendar_ref,
            now_cn=datetime(2026, 9, 1, 16, 0, tzinfo=SHANGHAI),
            online=False,
            limit=1,
        )
        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(summary.feature_sets_written, 1)
        self.assertEqual(harness.source.calls, [])
```

The missing cash-flow case runs after cutoff and is reported, so it must be blocked rather than partial. Add `test_unclassified_and_balance_mismatch_are_blocked`: build one `不存在行业` fixture and one balance sheet outside tolerance, then assert exact blockers `industry_template_unclassified` and `balance_equation_mismatch`.

- [ ] **Step 2: Run the end-to-end test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_feature_foundation_e2e -v
```

Expected: FAIL with `NameError: HermeticDeepHarness is not defined`.

- [ ] **Step 3: Complete the hermetic replay and verify GREEN**

Implement these test-local components before the test class:

```python
class FixtureStatementSource:
    def __init__(self, batches: Mapping[tuple[str, str], FetchBatch], missing: set[tuple[str, str]]):
        self._batches = dict(batches)
        self._missing = set(missing)
        self.calls: list[tuple[str, str]] = []

    def fetch_financial_statement(
        self, symbol: str, dataset: str, report_period: str = "2026-06-30"
    ) -> FetchBatch:
        security_id = symbol.upper()
        if not re.fullmatch(r"(?:SH|SZ)\d{6}", security_id):
            raise AssertionError(f"worker supplied non-canonical fixture symbol: {symbol}")
        key = (security_id, dataset)
        self.calls.append(key)
        if key in self._missing:
            raise TerminalSourceError(f"fixture statement missing: {security_id}/{dataset}")
        return self._batches[key]


@dataclass(frozen=True)
class ReplayResult:
    bundles: tuple[FeatureBundle, ...]
    bundle_bytes: tuple[bytes, ...]
    feature_set_count: int
    status: Mapping[str, object]


class HermeticDeepHarness:
    def __init__(self, candidates, fixture_names, missing_datasets):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.data_root = self.project_root / "data"
        self.store = StateStore(self.data_root / "state.sqlite3")
        self.store.initialize()
        write_candidate_fixture_documents(self.data_root, candidates)
        self.repository = SnapshotRepository(
            self.data_root, self.store, SnapshotStore(self.data_root)
        )
        calendar_batch = load_calendar_fixture("trade_calendar_2021_2026.json")
        self.calendar_ref, _ = self.repository.persist(calendar_batch)
        self.batches = load_statement_fixture_batches(candidates, fixture_names)
        missing = {
            (security_id, dataset)
            for security_id, datasets in missing_datasets.items()
            for dataset in datasets
        }
        self.source = FixtureStatementSource(self.batches, missing)
        enqueue_legacy_parent_fixtures(self.store, candidates)

    @classmethod
    def single_general_candidate(cls) -> "HermeticDeepHarness":
        return cls(
            candidates={"SH600001": "包装印刷"},
            fixture_names={"SH600001": "general_nonfinancial_statements.json"},
            missing_datasets={},
        )

    def enqueue_frozen_feature_job(self) -> str:
        refs = {
            dataset: self.repository.persist(
                self.batches[("SH600001", dataset)]
            )[0]
            for dataset in STATEMENT_DATASETS
        }
        context = load_candidate_context(self.data_root)
        self.source.calls.clear()
        return enqueue_feature_build(
            self.store,
            security_id="SH600001",
            report_period="2026-06-30",
            as_of_utc="2026-09-01T08:00:00+00:00",
            candidate_context=context,
            statement_snapshots=refs,
            trade_calendar_snapshot=self.calendar_ref,
        )

    def run(self) -> ReplayResult:
        run_deep(
            self.data_root,
            self.store,
            source=self.source,
            snapshots=self.repository,
            trade_calendar_snapshot=self.calendar_ref,
            now_cn=datetime(2026, 9, 1, 16, 0, tzinfo=SHANGHAI),
            online=True,
            limit=9,
            heartbeat_seconds=0.01,
        )
        rows = latest_feature_set_rows(
            self.store, report_period="2026-06-30", contract_version=CONTRACT_VERSION
        )
        bundles = tuple(
            read_verified_feature_bundle(
                self.project_root, row["bundle_path"], row["bundle_hash"]
            )
            for row in sorted(rows, key=lambda item: item["security_id"])
        )
        status, exit_code = orchestrator.run_command(
            self.data_root,
            self.store.db_path,
            "status",
            now_cn="2026-09-01T16:00:00+08:00",
        )
        if exit_code != 0:
            raise AssertionError(f"fixture status failed: {exit_code}")
        return ReplayResult(
            bundles=bundles,
            bundle_bytes=tuple(bundle.canonical_bytes() for bundle in bundles),
            feature_set_count=len(rows),
            status=status,
        )
```

Add `single_general_candidate()` as a classmethod that constructs only SH600001. `enqueue_frozen_feature_job()` persists its three fixture batches, builds exact statement refs, and calls `enqueue_feature_build()` without calling the fixture source; clear `source.calls` before the offline assertion. The main `run()` deliberately passes `online=True` only to traverse the remote-worker branch with an in-memory `FinancialStatementSource`; it never imports or patches orchestrator defaults.

Put the shared helpers in `tests/feature_fixture_helpers.py` with the exact implementations below:

```python
import json
import sqlite3
from pathlib import Path
from typing import Mapping

from ashare_pipeline.deep_worker import STATEMENT_DATASETS
from ashare_pipeline.feature_contract import canonical_json_bytes, canonical_sha256
from ashare_pipeline.sources import FetchBatch
from ashare_pipeline.state_store import StateStore


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "financial"


def _fetch_batch(document: Mapping[str, object]) -> FetchBatch:
    return FetchBatch(
        str(document["source"]),
        str(document["dataset"]),
        dict(document["request"]),
        list(document["records"]),
        str(document["fetched_at_utc"]),
        str(document["source_version"]),
        dict(document["metadata"]),
    )


def load_calendar_fixture(name: str) -> FetchBatch:
    document = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    batch = _fetch_batch(document)
    if batch.dataset != "trade_dates":
        raise AssertionError("calendar fixture must be trade_dates")
    return batch


def load_statement_fixture_batches(
    candidates: Mapping[str, str],
    fixture_names: Mapping[str, str],
) -> dict[tuple[str, str], FetchBatch]:
    result: dict[tuple[str, str], FetchBatch] = {}
    for security_id in sorted(candidates):
        document = json.loads(
            (FIXTURE_ROOT / fixture_names[security_id]).read_text(encoding="utf-8")
        )
        if document["security_id"] != security_id:
            raise AssertionError("fixture security mismatch")
        if set(document["batches"]) != set(STATEMENT_DATASETS):
            raise AssertionError("fixture must define all three statement batches")
        for dataset in STATEMENT_DATASETS:
            batch = _fetch_batch(document["batches"][dataset])
            expected_request = {
                "symbol": security_id,
                "report_period": "2026-06-30",
            }
            if batch.dataset != dataset or batch.request != expected_request:
                raise AssertionError("fixture request mismatch")
            result[(security_id, dataset)] = batch
    return result


def write_candidate_fixture_documents(
    data_root: Path,
    candidates: Mapping[str, str],
) -> None:
    records = [
        {
            "security_id": security_id,
            "industry": candidates[security_id],
            "announcement_date": "2026-08-29",
            "report_period": "2026-06-30",
        }
        for security_id in sorted(candidates)
    ]
    performance = {
        "schema_version": 2,
        "input_hashes": {"fixture_records": canonical_sha256(records)},
        "records": records,
    }
    prefilter = {
        "schema_version": 2,
        "input_hashes": {"performance": canonical_sha256(performance)},
        "records": [
            {"security_id": row["security_id"], "industry": row["industry"]}
            for row in records
        ],
    }
    for name, document in (("performance", performance), ("prefilter", prefilter)):
        path = data_root / "curated" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(document))


def enqueue_legacy_parent_fixtures(
    store: StateStore,
    candidates: Mapping[str, str],
) -> tuple[str, ...]:
    return tuple(
        store.enqueue_job(
            "deep_financial",
            f"fixture:deep_financial:{security_id}",
            {
                "security_id": security_id,
                "report_period": "2026-06-30",
                "input_hash": canonical_sha256(
                    {"security_id": security_id, "industry": candidates[security_id]}
                ),
            },
        )
        for security_id in sorted(candidates)
    )


def latest_feature_set_rows(
    store: StateStore,
    report_period: str,
    contract_version: str,
) -> list[dict[str, object]]:
    with sqlite3.connect(store.db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT * FROM feature_set
            WHERE report_period=? AND contract_version=?
            ORDER BY security_id""",
            (report_period, contract_version),
        ).fetchall()
    return [dict(row) for row in rows]
```

Each statement fixture has top-level `security_id` and `batches`; each batch is the exact seven-field semantic `FetchBatch` document consumed above. All three batches contain raw `SECURITY_CODE`, `REPORT_DATE`, `NOTICE_DATE`, optional `UPDATE_DATE`, and mapped source fields for FY2021–FY2025, 2025H1, and 2026H1. The calendar fixture is one semantic `FetchBatch` with `calendar_date` and `is_trading_day` records covering 2021-01-01 through 2026-09-07. Task 7 tests must reject a fixture missing any of these structural requirements.

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_feature_foundation_e2e -v
```

Expected: PASS with no network calls.

- [ ] **Step 4: Run the complete regression suite**

```powershell
$env:TEMP=(Get-Location).Path
$env:TMP=(Get-Location).Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all tests pass; the original 109 tests have zero regressions.

- [ ] **Step 5: Update the execution ledger**

In `progress.md`, record:

- schema v3 and feature contract version;
- number of new tests and full-suite result;
- current online candidate statement coverage;
- explicit statement that this phase produces financial feature inputs only;
- `formal_score_ready=false` and both official pools remain zero;
- next project is market/capital-action/governance inputs plus formal scoring.

- [ ] **Step 6: Commit end-to-end evidence**

```powershell
git add -- tests/test_feature_foundation_e2e.py tests/feature_fixture_helpers.py progress.md
git commit -m "test: verify financial feature foundation end to end"
```

---

## Operational Acceptance After Code Review

Run this only after all code tasks pass review. It is not a stable unit test and its data changes use a separate commit boundary.

- [ ] Verify code commits did not absorb runtime data:

```powershell
git status --short
```

- [ ] Execute exactly one remote statement task:

```powershell
.\.venv\Scripts\python.exe -m ashare_pipeline.orchestrator --root data --db data/state.sqlite3 deep --online --limit 1
```

Expected:

- no more than one remote financial-statement request;
- one new or reused verified statement snapshot;
- any created fact and bundle links back to exact snapshot ID/hash;
- no raw statement rows in CLI output;
- no `.part` file remains;
- `formal_score_ready` remains false and official pools remain zero.

If the source returns SourceBlocked or a retryable network error, preserve that classified job state and do not convert the smoke run into a false success.

- [ ] Continue in bounded batches until the current-candidate acceptance threshold is reached or the source circuit opens:

```powershell
.\.venv\Scripts\python.exe -m ashare_pipeline.orchestrator --root data --db data/state.sqlite3 deep --online --limit 10
.\.venv\Scripts\python.exe -m ashare_pipeline.orchestrator --root data --db data/state.sqlite3 status
```

Repeat the two commands only while the prior `deep.incomplete_candidates` contains pending/retryable current work and `deep.active_circuit_breakers` does not contain `akshare`. Each run remains independently resumable and commits every verified statement immediately. Stop rather than hammering the source when SourceBlocked opens the circuit; resume in a later approved run.

- [ ] Verify the full operational acceptance invariant from `pipeline_status.json`:

```powershell
$status = Get-Content -LiteralPath 'data\status\pipeline_status.json' -Raw | ConvertFrom-Json
$deep = $status.deep
$coverage = $deep.candidate_financial_coverage
$errors = [System.Collections.Generic.List[string]]::new()
$allowed = @(
    'pending',
    'retryable_network',
    'source_blocked',
    'terminal_source_missing',
    'unverified_snapshot',
    'target_period_missing'
)

if ($coverage.denominator -ne 120) { $errors.Add('denominator_not_120') }
if ($coverage.numerator -lt 114) { $errors.Add('numerator_below_114') }
if ($coverage.rate -lt 0.95) { $errors.Add('coverage_below_95_percent') }
if ($deep.incomplete_candidates.Count -ne (120 - $coverage.numerator)) {
    $errors.Add('incomplete_candidate_count_mismatch')
}
foreach ($item in $deep.incomplete_candidates) {
    if ($item.missing_datasets.Count -eq 0) {
        $errors.Add("missing_dataset_classification:$($item.security_id)")
    }
    if ($item.error_classifications.Count -eq 0) {
        $errors.Add("missing_error_classification:$($item.security_id)")
    }
    foreach ($classification in $item.error_classifications) {
        if ($allowed -notcontains $classification) {
            $errors.Add("unknown_classification:$($item.security_id):$classification")
        }
    }
}
if ($deep.expired_current_lease_count -ne 0) { $errors.Add('expired_current_leases') }
if ($deep.unknown_failure_count -ne 0) { $errors.Add('unknown_failures') }
if ($status.formal_score_ready) { $errors.Add('formal_score_gate_open') }
if ($status.seven_dimension_ready) { $errors.Add('seven_dimension_gate_open') }
if ($status.official_pool_counts.waiting_price -ne 0) { $errors.Add('waiting_pool_nonzero') }
if ($status.official_pool_counts.strong_attention -ne 0) { $errors.Add('attention_pool_nonzero') }
if ($errors.Count -ne 0) { throw ($errors -join ',') }
```

The numerator definition itself guarantees that every counted member has all three exact verified 2026H1 snapshots. Remaining classifications are statement-level only; template and feature blockers are reported separately and cannot be used to excuse a missing target statement.

The code phase can be considered complete before this online threshold is reached, but the financial-data foundation cannot be declared operationally accepted until this invariant passes. Network/source blocking is a recorded external dependency, never silently treated as coverage.

- [ ] Commit only verified runtime data:

```powershell
git add -- data/state.sqlite3 data/status data/raw/akshare data/curated/formal_features
git commit -m "data: record verified deep financial progress"
```

Do not commit `data/curated/formal_features` if no bundle was created; the state/error evidence is still retained. Because project data is intentionally tracked, retain all verified incremental snapshots and status history needed to resume without refetching.

---

## Plan Self-Review Map

| Approved spec requirement | Implemented by |
|---|---|
| Immutable contract, null safety, exact seven dimensions | Tasks 1, 8 |
| FY2021—FY2025 plus 2025H1/2026H1 | Tasks 2, 7, 8 |
| Point-in-time notice/update and next real session | Tasks 7, 12 |
| Reachable top-rank conflict detection | Task 7 |
| SQLite v3 and deterministic persistence | Tasks 3, 4 |
| Exact request-scoped snapshots | Task 6 |
| 120 parents → 360 independent statement jobs | Tasks 5, 10 |
| Per-table persistence, retries, heartbeat, circuit | Tasks 9, 11 |
| Frozen evidence and content-addressed bundles | Tasks 6, 8, 11 |
| No-overwrite feature files and DB-failure cleanup | Task 11 |
| Scoped deep progress and 95% readiness metric | Task 12 |
| Verifiable calendar caching and versioned calendar jobs | Task 12 |
| No formal score/pools and final remains closed | Tasks 1, 8, 12, 13 |
| Tracked data, bounded online smoke, and ≥95% coverage acceptance | Operational Acceptance |
