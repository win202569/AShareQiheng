# Task 2 Fix Round 2

Reviewer verdict after round 1: **Not Approved**. Fix only remaining Task 2 issues below with TDD. Do not modify Task 3/4 or access network.

## Critical

1. Remove all raw `records` and unbounded `metadata` from `_write_batch` public summaries, SQLite job result, `pilot_status.json`, and stdout. Persist raw rows only in content-addressed snapshot files. Compact evidence may include dataset/source, row count, content hash, source version, snapshot path, fetched time and request fingerprint. For trade-date selection, consume the just-fetched batch internally or re-read the referenced snapshot; expose only the small filtered trade-calendar evidence, never other raw batches. Add assertions that unique raw marker values from master/performance/financial statements are absent from serialized status and job result.
2. Bind `job_kind` to the exact as-of/task identity, or otherwise lease and transition the exact `leased['id']`. Ensure an older pending/retryable job can never be leased while complete/fail is called on a newer pending job. Add a two-date regression with an old retryable and a new job.

## Important

3. Persist structured failure classification. On same-day rerun, an existing terminal `SourceBlocked` must re-open the in-run circuit before later tasks from that source are considered. Test blocked twice and prove the second run makes zero later calls.
4. Decouple AKShare financial statements from BaoStock calendar availability. Only daily-price requests depend on `latest_completed_trading_date`; six representative symbols' balance/profit/cash-flow batches must still be attempted when BaoStock/calendar is blocked, retryable or empty, subject only to AKShare's own circuit.
5. Add true pilot-task expired-lease recovery, cross-date retry/pending, same-day blocked rerun, and weekend/holiday latest-trading-date tests. Inject a no-delay sleeper into every BaoStock unit test/fake; unit suite must not sleep.

## Acceptance

- Re-run Task 1+2 and relevant Task 3 integration tests.
- Append red/green evidence and changed files to `task-2-report.md`.
- Return exact test counts and any remaining issue.

## Submitted fix hashes

- `ashare_pipeline/pilot.py` — `69B38D3607B501265E9790F094636E9E18619E8F3D55E92C85C56B9881CE8997`
- `tests/test_pilot.py` — `11526A9DC931D61FC0C122FE6C02588F2250F6892A58917D98DE21540800A26D`
- `tests/test_sources.py` — `5E43F702F831E6E02BD0A856B0E7D031A03A12089CE3273E37A2CF80DD50D5D2`
- `task-2-report.md` — `40793262457D39023396CC7E9A29F2FA24B729229191A573F059D0128E653A00`

Implementer reports 51/51 Task 1+2 tests passing. Review the two original Critical and three Important items, test adequacy and new regressions. `Approved` only if no Critical/Important remains; do not edit or rerun tests.
