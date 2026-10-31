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

