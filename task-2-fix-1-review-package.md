# Task 2 Fix Round 1

Reviewer verdict: **Not Approved**. Apply TDD fixes to Task 2. Controller explicitly authorizes the minimal Task 1 public read API change described below; update its tests and preserve all prior behavior.

## Critical fixes

1. Replace cell-wide substring matching for `403`/`429`. Never stringify/search an entire DataFrame and never classify ordinary scalar codes/sequence numbers as HTTP status. Separate access-error detection (exception/login/query code+message) from HTML/captcha cell detection. Test rows containing sequence 403/429 and stock codes 000403/000429 remain valid, while representative `HTTP 403`, `429 Too Many Requests`, captcha and HTML challenge inputs block.
2. Use the pinned AKShare 1.18.94 real performance columns:
   - `营业总收入-营业总收入`
   - `营业总收入-同比增长`
   - `净利润-净利润`
   - `净利润-同比增长`
   Map them explicitly to stable curated Chinese keys expected by the brief, preserve zero-padded codes, record the source mapping, and fail loudly if required columns are absent instead of silently returning incomplete success. Make fake/fixture structure mirror the real schema.
3. Make interrupted jobs resumable and status truthful. At online start call `recover_expired_leases`. Add a minimal `StateStore.get_job(job_id)` read method returning public status/result/error/retry fields, with tests; use it when `lease_next_job` is None to distinguish succeeded/running/retryable/terminal rather than claiming success. Catch unexpected ordinary exceptions after source-specific exceptions and move running jobs to retryable failure. A deliberate crash may remain running until lease expiry, but rerun must show running before expiry and recover it after expiry.

## Important fixes

4. Implement source-level circuit breaking: after `SourceBlocked`, do not call later tasks from the same source in that run. Record them as `blocked_by_circuit`/pending without overwriting previous successes.
5. In BaoStock query errors, classify using `error_code + error_msg`, matching login behavior.
6. Verify a new `.part` payload before `os.replace`. If the final hash-path already exists, re-read and verify it before returning deduped. A corrupt existing target must raise, not be accepted; a newly created invalid target must not remain.
7. Determine the latest completed **trading** date from the BaoStock calendar, not `today - 1`. Persist requested Shanghai date status (`pending` before 15:30 or future), latest completed trading date and evidence in `pilot_status.json`. Include the as-of date in daily refresh idempotency keys so security master/calendar/disclosure/performance can be checked again on later days without refetching twice on the same day.
8. Reused successful jobs must retain original batch rows/hash/source_version/path in the current status output. `generated_at_utc` must be UTC, not local offset.
9. Expand tests for all above behaviors, including blocked/terminal rerun, expired leases, circuit breaker, holiday/weekend calendar selection, pending persistence, actual performance schema, bad existing snapshot, and stable timestamp/NaT normalization.

## Additional controller ruling

10. A snapshot digest must represent source/business content, not observation time. Two otherwise identical `FetchBatch` values with different `fetched_at_utc` must have the same content SHA and deduplicate; the stored JSON still preserves the first observation timestamp. Request/source/dataset/records/source_version/material metadata remain in the digest. Add a test.
11. Use the injected BaoStock sleeper in the request lifecycle, with a no-delay fake in tests; online default may use a small conservative delay. Do not make unit tests sleep.
12. Write `pilot_status.json` atomically via unique same-directory `.part`, flush/fsync, `os.replace`; clean only the attempt's part on failure.

## Acceptance

- Run Task 1 + Task 2 tests; all must pass.
- Append red/green evidence and changed files to `task-2-report.md`.
- Do not edit Task 3/4 files and do not perform network calls.

## Submitted fix hashes

- `ashare_pipeline/sources.py` — `FBD3697CDC54BC1F76B5A94ACD50FA9A2670C0C13CF3A4F89FF980DFA2343487`
- `ashare_pipeline/snapshot_store.py` — `1EE1D31B17A2D719C10B4C02B220544CB0B2D220021D6AEFF2616C03B52DE4C6`
- `ashare_pipeline/pilot.py` — `9A3A65B63CB7894574A4955471B52AC66F249340F8DBD7355252F9E1ED22F4DC`
- `ashare_pipeline/state_store.py` — `B94930EDB7B8EFB72941BCC26F627AA670A0E30DDE61E1EC5063A474D53AAB43`
- `tests/test_sources.py` — `91778672A1378AF8CF89D9DD45F074389BD40C1D2DA8FA02C1FCC7F6A27DDBE4`
- `tests/test_snapshot_store.py` — `E6AA08082DB92A935655D24A9D7C84C458BD12098DAFD582D7F2B01BF39FC293`
- `tests/test_pilot.py` — `954B66D9790C599BFBE78CCFC94617A9C63A13EBF84FEBE7212C5E7B94F4C36B`
- `tests/test_state_store.py` — `18CF827D9FAEDF62B3DC5E774E2780E4265D641A1A6FE5BA14F341DD8E2D6173`
- `task-2-report.md` — `4A29F8B1D8AE2E2F6F76756E22827BB6E7884B323B3BF9214B2FF82CE1D5BC28`

Implementer reports 47/47 Task 1+2 tests passing. Reviewer: verify every original Critical/Important/Minor and all controller additions by code/test inspection, check for new regressions, and return `Approved` only if no Critical/Important remains. Do not edit or rerun tests.
