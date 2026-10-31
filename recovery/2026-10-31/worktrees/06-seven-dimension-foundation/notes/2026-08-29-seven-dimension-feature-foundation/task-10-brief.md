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

