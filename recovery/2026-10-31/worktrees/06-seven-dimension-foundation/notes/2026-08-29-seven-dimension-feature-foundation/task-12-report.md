# Task 12 Report

- Baseline: `6b41ff648ab8e6753b72c821f84ee7e60c1cc596`.
- Scope: `ashare_pipeline/orchestrator.py`, `ashare_pipeline/reporting.py`, `tests/test_orchestrator.py`, and `tests/test_reporting.py`.
- Runtime safety: all execution tests used worktree-local temporary data roots, SQLite databases, snapshot stores, and injected fakes. No real network was used, no main checkout was modified, and no real runtime data was touched.

## TDD evidence

- Baseline orchestrator/reporting regression: 39 tests passed.
- Designated parser RED: `deep` was rejected as an invalid command.
- Parser GREEN: `deep [--online] [--limit 1..360]` accepts the default and exact bounds, and rejects 0/361.
- Offline/source RED-GREEN: offline deep and standalone status construct no default source; a verified exact calendar plus injected deep source constructs no defaults; a tampered exact cache raises the snapshot verifier's explicit `OSError` semantics and is never replaced.
- Calendar RED-GREEN: a historic short-calendar success no longer hides the long feature-calendar request. The job identity includes the exact canonical request hash and calendar request version.
- Bounded collection RED-GREEN: `--limit 1` makes at most one financial-statement request. Calendar acquisition is outside that limit.
- Daily enqueue RED-GREEN: two calls over 120 members return the same ordered 360 job IDs and retain exactly 360 database rows with zero statement-source calls.
- Progress RED-GREEN: stale request versions, refresh dates, report periods, candidate hashes, contracts, and feature report periods cannot satisfy current progress. Three exact verified snapshots must each contain `2026-06-30` before a candidate enters the numerator.
- Taxonomy RED-GREEN: incomplete rows have exact keys and sorted nested lists; retryable network, active blocked-source circuits, terminal source absence, unverified snapshots, missing target period, expired leases, and unknown failures remain distinct.
- Reporting RED-GREEN: operational rows expose only bounded aggregate deep counts and never individual financial values or security identifiers.
- Focused orchestrator/reporting result: 55 tests passed.
- Task 10/11 and storage/source related result: 167 tests passed.
- Final full regression using worktree-local TEMP/TMP/TMPDIR: 330 tests passed in 51.242 seconds.
- `py_compile` and `git diff --check`: passed.

## Delivered contracts

- `deep` records its limit in run configuration, executes queued deep work in offline or online mode, and writes the bounded run summary plus current progress into status.
- Offline deep, offline incremental, and status are physically unable to construct or call default AKShare/BaoStock clients. Online defaults are constructed only inside the deep dependency helper when their exact dependency is absent.
- Incremental curation enqueues the current candidate context's three dated statement jobs per member idempotently without consuming statement calls.
- The feature calendar spans from `2021-01-01` through at least `2026-09-07` and ten days beyond the run date. Exact verified snapshots are reused; changed requests/versioned job keys cannot reuse an old short job.
- Progress is scoped by current candidate membership, financial request version, refresh date, `2026-06-30` statement period, current feature candidate hash, current feature contract, and feature report period. First-enqueue candidate hash remains audit evidence and does not exclude a current child slot.
- Formal scoring and seven-dimension gates remain false, and both official pool counts remain zero.
- Reporting adds bounded aggregate operational rows only; it does not expose statement records or per-candidate financial values.

## Fail-closed boundary review

- Empty deep status is emitted only when both curated candidate documents are absent. If either exists, `load_candidate_context()` verifies the pair; malformed JSON or hash tampering propagates instead of silently becoming a zero-candidate status.
- Statement slots require current member, request version, refresh date, and `report_period == 2026-06-30`. Feature rows additionally require current candidate hash, contract version, and target report period.
- Lease expiry and retry-window decisions parse timezone-aware ISO instants and compare normalized UTC values; string ordering and offset spelling cannot change the result.
- `build_deep_progress()` rejects a snapshot repository rooted outside `data_root` and rejects a repository backed by a different StateStore database.
- Snapshot counts include exact verified files, while financial coverage requires the target period inside all three files. This prevents a verified historical-only snapshot from satisfying coverage.

## Commit

- Message: `feat: expose bounded deep collection and progress`.

## Independent review — round 1

- Review base: `a79e4270480c6d1cde06765c0e5ed6aac908edbb`.
- Scope remained limited to `ashare_pipeline/orchestrator.py` and `tests/test_orchestrator.py`; no real network, main checkout, or runtime data was used.

### Versioned calendar reuse RED/GREEN

- RED: repeated same-day incremental collection trusted a succeeded versioned calendar job after its exact snapshot was tampered, deleted, or removed from the snapshot index. Missing or wrong cached result metadata was also advertised as success, and wrong-source, wrong-dataset, wrong-request, or multiple fresh batches completed the exact job key.
- GREEN: every succeeded calendar reuse now resolves the current exact request, verifies the indexed snapshot bytes and database metadata, and binds its single cached result to the verified ref's source, dataset, request, hash, and path. Any missing/tampered component raises an explicit `OSError` without calling BaoStock again.
- GREEN: a fresh response must contain one semantic batch with exact `source=baostock`, `dataset=trade_dates`, and the current long request before persistence. The persisted ref is read-verified before the versioned job completes. All malformed cases remain non-succeeded and cannot publish an exact ref.

### Current job slot RED/GREEN

- RED: one current member counted an obsolete parent plus duplicate current parent as three pending parents. A noncanonical duplicate statement row inflated balance-sheet counts and its later list position replaced the canonical slot state.
- GREEN: parents require current member, `2026-06-30`, current performance hash, and the canonical parent key. Historical parents are excluded; same-scope noncanonical parents are counted once as unknown corruption; an impossible duplicate canonical parent fails closed.
- GREEN: statement rows require the current payload scope and canonical `deep_statement_key`. A single `(security_id, dataset)` map now drives statement counts, incomplete state/classification, lease/circuit handling, and unknown raw failures. Same-scope noncanonical rows cannot enter a slot or inflate counts and increment unknown corruption; an impossible duplicate canonical slot fails closed.
- The existing stale-candidate-hash test now uses the canonical statement key while retaining stale first-enqueue audit hashes, preserving the Task 12 rule that candidate hash does not scope a current child slot.

### Review verification

- Focused review cases: 3 test methods covering 10 subcases passed.
- Orchestrator/reporting: 58/58 passed.
- Task 10/11 related deep-worker/state/snapshot/source suites: 167/167 passed.
- Full suite: 333/333 passed in 51.740 seconds.
- `py_compile` and `git diff --check`: passed.
- Fix commit message: `fix: verify calendar cache and current job slots`.

## Independent review — round 2

- Review base: `5510a0556bf5e4dace1dc7a6869bb63d896fc464`.
- Scope remained limited to the cached calendar result in `ashare_pipeline/orchestrator.py` and its focused tests in `tests/test_orchestrator.py`.

### Cached public-result binding RED/GREEN

- RED: a succeeded calendar job with an untouched verified snapshot still returned tampered `rows`, `source_version`, or `semantic_hash`; an extra field leaked into the public result; integer `created=1` was accepted as truthy; valid reuse repeated the historic `created=True` value.
- GREEN: the authoritative source, dataset, request, row count, payload hash/path, source version, and semantic hash are derived from the read-verified exact `SnapshotRef` and `FetchBatch`. The persisted prior item must have the exact storage-result key set, native field types, and exact values for every verifiable field.
- The prior `created` value is required to be a native boolean but is not treated as snapshot-verifiable history. A current reuse always emits `created=False`, `cached=True`, and `status=succeeded`, reconstructed from trusted values. Extra, malformed, or mismatched fields raise `OSError` without source construction, refetch, or replacement.

### Round 2 verification

- Focused calendar cache tests: 2/2 passed; the failure test now covers ten distinct corruption/missing modes.
- Orchestrator/reporting: 59/59 passed.
- Task 10/11 related deep-worker/state/snapshot/source suites: 167/167 passed.
- Full suite: 334/334 passed in 67.217 seconds.
- `py_compile` and `git diff --check`: passed.
- Fix commit message: `fix: derive cached calendar results from verified snapshots`.
