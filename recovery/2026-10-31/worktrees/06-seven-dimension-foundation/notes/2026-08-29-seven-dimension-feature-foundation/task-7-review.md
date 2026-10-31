# Task 7 Independent Re-review

Verdict: **APPROVED**

Reviewed range: `57decb7dccc7116595b92581b65bf6260e760e1e..17f5865c354649aa5f9e20d50d690ee642be4748`

I reread the updated Task 7 report and the new review package before inspecting the committed implementation, all fixtures, and tests. I independently reran the relevant behavior and did not rely on the implementer's GREEN claims.

## Prior findings

### 1. Strict date/time lexical parsing — closed

Files: `ashare_pipeline/financial_features.py:28-34`, `ashare_pipeline/financial_features.py:87-93`, `ashare_pipeline/financial_features.py:138-164`, `ashare_pipeline/financial_features.py:264-270`

Calendar and report dates now require the complete `YYYY-MM-DD` lexical form. `REPORT_DATE` is no longer sliced. Source dates distinguish exact date-only input from an explicit timestamp grammar; date-only values retain the required 23:59:59 Asia/Shanghai semantics. Compact, week-date, suffixed, whitespace-padded, slash-separated, and malformed-separator inputs fail closed.

Independent probes confirmed that `2025-12-31junk` produces no facts with `statement_report_date_invalid`, and compact notice `20260331` produces no facts with `statement_source_date_invalid`.

### 2. `SECUCODE` exchange and dual identity — closed

File: `ashare_pipeline/financial_features.py:167-197`

`SECURITY_CODE` and `SECUCODE` are parsed separately. A suffixed `SECUCODE` must be exactly `dddddd.SH` or `dddddd.SZ`; its full normalized exchange identifier must match the expected security. When both fields are present, their six-digit codes must agree before the full exchange check.

An independent `600001.SZ` versus expected `SH600001` probe produced no facts and `statement_security_mismatch`.

### 3. Complete, order-independent calendar coverage — closed

Files: `ashare_pipeline/financial_features.py:96-134`, `tests/fixtures/financial/trade_calendar_2021_2026.json:1-8324`, `tests/test_financial_features.py:431-480`, `tests/test_financial_features.py:531-558`

The extractor requires every natural date in the requested interval exactly once, rejects duplicates, endpoints missing, and interior holes, but accepts a complete shuffled batch and returns sorted sessions. The test-local fixture validator applies the same complete-set requirement.

Independent validation of the committed fixture found:

- 2076 records, 2076 unique dates, and 2076 expected dates;
- exact ordered coverage from `2021-01-01` through `2026-09-07` with no hole;
- flags restricted to string `0`/`1`;
- a shuffled complete batch accepted with 1377 sessions, while deleting one row raised `trade calendar must cover every requested date exactly once`.

### 4. Non-string snapshot fetch time — closed

Files: `ashare_pipeline/financial_features.py:354-357`, `ashare_pipeline/financial_features.py:403-414`

The UTC parser now rejects non-strings as `ValueError`, which the selector converts to `snapshot_fetch_time_invalid` for the affected logical fact. Integer, boolean, list, and malformed-string cases are covered. An independent integer probe returned no selected fact and blocker `snapshot_fetch_time_invalid`; no parser exception escaped.

### 5. Clean-checkout temporary directory — closed

File: `tests/test_financial_features.py:488-494`

Fixture-copying tests now use `tempfile.TemporaryDirectory()` without requiring a pre-created worktree-local parent. With `TEMP` and `TMP` unset and no `.tmp-tests`, the Task 7 module ran 30/30 tests successfully.

## Regression and provenance review

- The F1 business rank and top-rank conflict behavior remain unchanged and correct: announcement, optional source update sentinel, then snapshot fetch time; hash/ID are used only after semantic equality at the top rank.
- Only the six Task 7 implementation/test/fixture paths differ across the reviewed range.
- The trade-calendar metadata is internally consistent: `row_count=2076`, source version `00.9.30`, aware fetch time `2026-08-30T10:54:24+00:00`, and source-row digest `efd5d2c2ae115305aac5b8239df00a8a780f391a010d4f09ab91126cd43bfe17`.
- Recomputing the compact JSON-pair source digest produced the same value. Recomputing the fixture file SHA-256 produced `4cdb6dc858a5f546f9c824f0eb9df056ce2d74839a840c8398615d25d5b292ad`, matching the report.
- `git diff --check` for the full reviewed range exited 0.

## Fresh test evidence

```text
Task 7 with TEMP/TMP unset and no .tmp-tests:
Ran 30 tests in 0.279s — OK

Full discovery with a validated worktree-local temporary root:
Ran 215 tests in 6.224s — OK
```

A first full-discovery attempt using the host's default C: temporary directory hit the pre-existing Windows cross-drive `relpath` limitation in `test_orchestrator`; it is outside the changed paths. A subsequent local-temp full run initially exposed the existing concurrent snapshot repository test's intermittent failure; that unchanged test passed immediately in isolation, and the fresh complete rerun above passed all 215 tests. Neither event indicates a Task 7 regression.

All five prior findings are closed, the replacement fixture and provenance hashes are consistent, and no blocking regression was found.
