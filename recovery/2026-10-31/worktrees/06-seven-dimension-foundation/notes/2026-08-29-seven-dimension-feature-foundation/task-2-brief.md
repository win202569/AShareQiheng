### Task 2: Financial Fact Catalog, Period Rules, and Industry Registry

**Files:**
- Create: `ashare_pipeline/financial_schema.py`
- Create: `ashare_pipeline/industry_templates.py`
- Create: `tests/test_financial_schema.py`
- Create: `tests/fixtures/industry_template_registry_v1.json`

**Interfaces:**
- Consumes: `canonical_sha256` from Task 1.
- Produces: `MAPPING_VERSION`, `FINANCIAL_REQUEST_VERSION`, `StatementDataset`, `StatementKind`, `DATASET_TO_STATEMENT`, `PeriodInfo`, `FieldRule`, `FinancialFact`, `classify_period()`, `field_rules()`, `TEMPLATE_VERSION`, `TemplateDefinition`, and `resolve_template()`.

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

`financial_schema.py` owns `MAPPING_VERSION` and `FINANCIAL_REQUEST_VERSION`. Define `TEMPLATE_VERSION = "template-registry-v1"` exactly once in `industry_templates.py`, beside `TemplateDefinition` and the registry; all later consumers import it from there.

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

