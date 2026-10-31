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

