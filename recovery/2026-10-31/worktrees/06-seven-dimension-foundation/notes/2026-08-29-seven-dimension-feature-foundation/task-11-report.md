# Task 11 Report

- Baseline: `322f1a7ead1d3389c588edf3bb2bb94aa76c78b0`.
- Primary scope: `ashare_pipeline/deep_worker.py` and `tests/test_deep_worker.py`.
- Authorized prerequisite scope: the minimal Task 8 missing-dimension contract correction in `ashare_pipeline/feature_contract.py`, `ashare_pipeline/financial_features.py`, `tests/test_feature_contract.py`, and `tests/test_financial_features.py`.
- Runtime safety: all execution tests used temporary project/data roots and fake statement sources. No real network was used and no repository runtime database or runtime data tree was mutated.

## Root contract ruling

The Task 11 brief used `root` ambiguously. Existing Task 10 code proved that `load_candidate_context(root)` reads `root/curated`, and its tests passed `data_root`. The CLI convention is also `--root data`. By binding ruling, both `run_deep.root` and `execute_queued_deep_work.root` therefore remain the data root, while `write_feature_bundle(project_root, ...)` and `read_verified_feature_bundle(project_root, ...)` retain the project-root contract.

The executor verifies `snapshots.data_root.resolve() == data_root.resolve()` and verifies the stable `StateStore.db_path` parent is the same data root before doing work. It explicitly calls feature-file APIs with `data_root.parent`. `test_feature_path_is_project_relative_and_never_creates_data_data` and `test_database_failure_removes_new_orphan_feature_file` use a non-default `project_root/data/curated` layout, assert DB paths remain project-relative `data/...`, and assert that `data/data` is never created.

## TDD evidence

- Baseline full suite: 269 tests passed.
- Designated RED command: `python -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_limit_counts_only_remote_statement_requests -v`.
- Designated RED result: assertion failure, `run_deep execution API must exist`, because the Task 11 execution API did not exist.
- Task 8 prerequisite RED: a `DimensionInput(status="missing")` containing required missing slots plus excluded `not_applicable` slots was rejected; an empty-facts general-nonfinancial bundle consequently raised instead of producing a valid partial bundle.
- Task 8 prerequisite GREEN: missing dimensions now allow only `missing` plus `not_applicable` values and still reject observed/derived/blocked values. Empty general-nonfinancial and real balance/cash-only partial bundles have explicit coverage/status/missing-reason regressions.
- Frozen-content cutoff RED: after cutoff, all three snapshot hashes with no target-period facts incorrectly remained partial. GREEN derives the target-period blocker from frozen fact content, not statement job state.
- Source identity RED: a source batch for the wrong dataset escaped the run. GREEN classifies it terminal and persists no mismatched snapshot.
- First-heartbeat RED: initial lease renewal failure still called the remote source. GREEN performs no remote request, creates no feature follow-up, and never lets the stale worker complete.
- Atomic-race RED: a different `os.link` race winner surfaced as a generic hash-mismatch `OSError`. GREEN classifies it as `non-deterministic feature conflict` and preserves the winner bytes.
- Executor key-binding RED: an otherwise valid frozen payload queued under the wrong feature input-hash key succeeded. GREEN recomputes the exact Task 8 key from frozen inputs, marks the mismatched job terminal, and creates no feature row.
- Final Task 11 module: 48 tests passed.
- Tasks 4–10 related regression: 219 tests passed.
- Final full regression with a same-drive safe TEMP: 298 tests passed.
- `py_compile` and `git diff --check`: passed.

## Delivered execution contracts

- `limit` counts only calls that actually begin a remote single-table request. Parent expansion, same-date snapshot reuse, and offline feature builds do not consume it.
- Queued feature builds run first and offline. `online=False` neither constructs nor calls a source.
- Each remote leased job gets a daemon heartbeat thread; an initial synchronous renewal gates the request, periodic renewal continues during a blocked call, and `finally` stops and joins the thread. Lost ownership prevents completion. Expired leases are recovered before planning/execution.
- Successful tables are persisted and normalized immediately. Statement completion/failure and its feature follow-up use the Task 5 owned atomic APIs, so a later table failure retains earlier snapshots and yields a frozen partial bundle.
- Retryable, blocked, terminal, malformed, and mismatched-batch outcomes preserve the source error taxonomy. `SourceBlocked` opens the per-run `akshare` circuit and leaves later statement jobs pending. Target 2026H1 absence retries at `now + 6h` before cutoff and is terminal after cutoff; historical absence remains partial.
- Summary objects are deeply immutable, deterministic, and restricted to the allowed item fields; raw source records and markers never appear in summaries or job results.

## Frozen feature evidence and files

- Feature payloads freeze every statement/calendar snapshot as `source_snapshot_id + payload_hash`. Execution resolves only `SnapshotRepository.get(id)`, rechecks each hash, and never substitutes a later snapshot for an enqueued feature job.
- The idempotency key uses Task 8's exact `feature_input_hash` over the frozen dependencies. `performance_input_hash` remains audit evidence and is not hashed twice. `test_feature_build_key_rejects_conflicting_frozen_payload` proves an existing key cannot silently accept a different audit payload; `test_feature_build_reads_frozen_snapshot_ids_not_later_latest` proves later latest evidence is ignored.
- Feature files use canonical bytes, a same-directory `mkstemp`, flush/fsync, part parse/hash verification, and atomic no-replace hard-link creation. Existing files and link-race winners are reusable only for identical canonical bytes/hash. Conflicts preserve old/winner bytes.
- Database insertion occurs only after file verification. A DB failure removes only a file created by the current call and only when no committed exact path/hash row exists. Versioned prior files remain intact and DB rows never intentionally reference missing files.

## Commit

- Message: `feat: execute resumable deep financial feature builds`.

## Independent review — round 1

- Review base: `b467e2086f88088c834eee23898e10643aadae3a`.
- Scope remained limited to `ashare_pipeline/deep_worker.py` and `tests/test_deep_worker.py`; no runtime DB/data or real network was used.

### Frozen statement binding RED/GREEN

- RED: public enqueue accepted a profit snapshot in the balance slot; direct queued feature jobs with a wrong slot, wrong-security request, or duplicate cross-slot ref all succeeded and created feature artifacts.
- GREEN: every non-null statement ref is bound to `source=akshare`, its exact slot dataset, and `canonical_sha256({symbol: security_id, report_period})`. The executor rechecks both stored `SnapshotRef` metadata and the verified batch request before any fact insertion; repeated snapshot IDs across slots are terminal. Public enqueue rejects metadata mismatches it can see immediately.
- Focused result: 4/4 passed after all four reproduced failures.

### Candidate context and key binding RED/GREEN

- RED: direct-enqueue changes to security membership, candidate-set hash, performance hash, industry, or reported-target flag all succeeded. A wrong feature key with a real statement snapshot inserted 49 facts before becoming terminal.
- GREEN: the run's frozen `CandidateContext` now flows through offline feature processing. All five fields must match exactly before snapshot parsing or facts/files/rows. The exact Task 8 feature key is recomputed and verified after frozen ref validation but before fact normalization/persistence.
- Focused result: 6/6 passed after the five context failures and pre-fix 49-fact wrong-key failure.

### Periodic heartbeat precedence RED/GREEN

- RED: after periodic renewal failure, each of SourceBlocked, RetryableSourceError, and TerminalSourceError attempted a stale owned transition. A real owner handoff escaped as run-level `ValueError`; a transient renewal exception while worker-a's DB lease remained live produced stale fail/follow-up/circuit behavior.
- GREEN: remote taxonomy exceptions are captured as outcomes, the heartbeat context stops/joins, and `heartbeat.lost` is checked before every outcome transition. Lost ownership now yields only the bounded `lease_lost` item and stops remote processing: no snapshot, fact, fail/complete, follow-up, feature processing, or circuit mutation. The job remains with worker-b after a real handoff or running under worker-a until recovery after a transient renewal failure.
- Focused result: all 6 combinations (three source taxonomies × real handoff/transient renewal failure) passed.

### Review verification

- Task 11: 64/64 passed.
- Tasks 4–10 related suites: 235/235 passed.
- Full suite with same-drive safe TEMP: 314/314 passed.
- `py_compile` and `git diff --check`: passed.
- Fix commit message: `fix: bind frozen deep work to evidence ownership`.
