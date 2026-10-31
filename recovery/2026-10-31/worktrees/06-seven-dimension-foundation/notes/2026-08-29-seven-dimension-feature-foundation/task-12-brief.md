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

Compute `denominator = len(context.members)` so hermetic contexts remain coherent. The operational acceptance script below separately requires the deployed candidate context denominator to be exactly 120 and coverage to be at least 114; a truncated production context must not pass acceptance.

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

