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

Always normalize exactly the three statement keys before hashing. An omitted caller key becomes the required explicit null marker and therefore hashes identically to an explicitly supplied null; changing that null to a real snapshot hash must change the input hash. `candidate_set_hash` already commits to the prefilter inputs and each sorted performance-row hash, including the target-period disclosure state; therefore the pure bundle builder may consume `reported_target_period` without adding a second unapproved hash dependency.

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

