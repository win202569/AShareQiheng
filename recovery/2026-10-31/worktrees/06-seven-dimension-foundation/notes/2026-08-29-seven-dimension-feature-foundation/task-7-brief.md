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

Also add a small test-local JSON fixture-structure validator in `tests/test_financial_features.py`. Its rejection tests must cover a missing statement batch, a missing required FY/H1 period, missing identity/date fields, and a trade-calendar fixture that does not span the mandated range. Keep this validator local to Task 7; do not import the Task 13 helper or Task 10 worker code.

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

Use `effective_at_utc <= as_of_utc` only as the visibility gate and group visible facts by `(security_id, metric_key, period_end)`. Within each group, compute the maximum business version rank `(announced_at_utc, source_updated_at_utc with a deterministic missing sentinel, snapshot_fetched_at[source_snapshot_id])` **without** content hash or fact ID. Inspect every fact tied at that top business rank: differing finite values, units, or natures add `conflicting_fact_versions`/`conflicting_fact_units` and select none. Only when tied facts are semantically identical may raw/content hash and then ID be used for deterministic deduplication. This follows the binding announcement → source update → fetch ordering while keeping the conflict branch reachable. Effective time remains the first verified trading close strictly after `max(NOTICE_DATE, UPDATE_DATE)`.

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

