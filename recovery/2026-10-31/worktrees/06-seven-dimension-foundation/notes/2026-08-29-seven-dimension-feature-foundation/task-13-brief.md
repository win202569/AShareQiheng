### Task 13: Three-Security Hermetic Replay and Full Regression

**Files:**
- Create: `tests/test_feature_foundation_e2e.py`
- Create: `tests/feature_fixture_helpers.py`
- Modify: `progress.md`

**Interfaces:**
- Consumes: all prior tasks and the fixed industrial, bank, real-estate/missing fixtures.
- Produces: a hermetic fake-source proof, a true offline frozen-job proof, and an updated project-facing status document; no new production interface.

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

This repository-root `progress.md` is the committed project-facing status document. It is distinct from the ignored private SDD recovery ledger under `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/progress.md`; never stage the private ledger.

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
