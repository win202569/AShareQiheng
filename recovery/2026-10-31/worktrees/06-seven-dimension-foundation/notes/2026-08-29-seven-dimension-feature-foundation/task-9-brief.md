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

