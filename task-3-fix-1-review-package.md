# Task 3 Fix Round 1

Reviewer verdict: **Not Approved**. Apply TDD fixes to Task 3 only. Re-read the now-fixed Task 2 interfaces, especially `FetchBatch.sha256`, `SnapshotStore.write`, `StateStore.get_job`, and the stable performance-report keys.

## Reviewer Critical

1. Eliminate post-cutoff look-ahead. For final-cutoff curation, filter announcement versions to `<= 2026-08-31T23:59:59+08:00` before deterministic latest-version dedupe. A 2026-09-01 late filing/revision must never replace an in-cutoff version. At final quality gate, missing/unparseable announcement timestamps must block formal readiness. Add a September 1 regression test. Preserve a provisional mode that can describe post-cutoff observations separately without mutating the frozen cutoff dataset.

## Reviewer Important

2. Enforce `MAX_CANDIDATES=120` during industry-representative selection as well as global supplementation; test at least 61 industries × 20 rows and deterministic truncation.
3. Normalize snapshot paths. Persist either absolute paths or paths strictly relative to root and resolve exactly once; test a relative `--root` online run through curated rebuild.
4. Wrap every run after `start_run` so curation, SQLite, snapshot, scoring or status-write exceptions always finish the run as failed. Preserve the original error, avoid masking it if failure-status writing also fails, and test injected failures. Finalize exceptions must also close the run.
5. Replace self-declared market evidence with verifiable rows/input hashes. Required evidence for 2026-08-31: unique universe securities, no outside duplicates counted toward coverage, nonempty close for each required security (suspended securities may carry a documented last close/tradestatus policy), exact date, source snapshot hash and matching universe hash. Do not accept only `complete=true` and row_count. Test duplicates, missing close, outside rows and hash mismatch.
6. Put curation schema/ruleset hash into every curated document input fingerprint and reject/rebuild stale schema/ruleset artifacts even when source hashes are unchanged.
7. Preserve `outside_universe_rows`, source duplicate counts and all prior quality audit fields during finalize; test field survival.
8. Resolve `sh.689xxx`: because the requested universe is A shares, either explicitly exclude CDRs or label them 科创板存托凭证 and report a distinct instrument type. Do not classify as 主板. Controller ruling: exclude 689 CDRs from the A-share universe, record their exclusion count, and add a test.

## Controller additions

9. Use `StateStore.recover_expired_leases` at online start and `get_job` whenever a lease is unavailable. Do not call every lease miss “idempotent”; distinguish succeeded/running/retryable/terminal and preserve cached result evidence. Add interrupted/running/expired tests.
10. `score_item.coverage` must represent V2 formal-feature coverage, not completeness of the five-field prefilter. Keep prefilter coverage in curated records, but cap or compute formal coverage from the actual seven-dimensional feature map; at this stage it must clearly remain low/partial and never reach 1.0. Add a full-prefilter-fields regression test.
11. Formal data quality must include a disclosed-universe coverage threshold, because the user requested all A shares. Before final publication require at least 95% eligible-universe disclosure coverage, separately from 95% core-field completeness; report both denominators. If legitimate non-reporting/new-listing exclusions are later defined, they must be explicit evidence, not silent denominator removal.
12. Update `task-3-report.md` for Task 2's fixed timestamp-independent content hash and accurate status behavior. `status` may parse curated files but must not output records; avoid claiming it never reads them unless implementation changes.
13. Re-run Task 1–4 tests after integration. Do not modify Task 1/2/4 implementation or tests; do not access network.

## Acceptance

Append red/green evidence and changed-file list to `task-3-report.md`. Return only after all Task 3 tests and regressions pass.

## Submitted fix hashes

- `ashare_pipeline/curation.py` — `96E441E5F9249CFE4FD6C5015614212E015EB008961A7D42AAFB22E55215192D`
- `ashare_pipeline/scoring.py` — `F62A1F6EA269D7066BC3CBE30BD8AA1AC8EAC9EDE6B6F6FC6299F4BD5B78FE5E`
- `ashare_pipeline/orchestrator.py` — `DF4FDD6AF0341D9200C7E7F594E4F7799721B83B9D9D2BF1F3435CA21C09884E`
- `tests/test_curation.py` — `24EAB3DBF6C470EFE046A9BC087D676E1A5A5133BF46B9DA006FF67C8DBDF676`
- `tests/test_scoring.py` — `E261E517CF53C20F19FDD5913190D9E2F2B73D6542D2431F396904AEA6F8B10E`
- `tests/test_orchestrator.py` — `6AE1F4A3F74AED60E4EE08BC3F85D260517BFCF4A5EC474A05F8B221021DDCB7`
- `task-3-report.md` — `8EFDC8B2431538FABC359F2982C04CA386A23157AAC9E89326AB57C396A73BEA`

Implementer reports 31/31 Task 3 tests, 106/106 full regressions and compileall passing. Re-review all original Critical/Important, controller additions, Task 2 integration and new regressions. `Approved` only if no Critical/Important remains; do not edit or rerun tests.
