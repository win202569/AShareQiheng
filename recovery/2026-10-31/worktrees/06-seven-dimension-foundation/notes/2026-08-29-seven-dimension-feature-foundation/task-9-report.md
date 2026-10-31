# Task 9 Report — Isolated AKShare Statement Fetching

## Summary

Added the `FinancialStatementSource` protocol and `AKShareSource.fetch_financial_statement()` for one-table-at-a-time financial collection. The compatibility `fetch_financial_statements()` wrapper remains available and delegates in the fixed balance, profit, cash order. The pilot caller remains unchanged.

Unknown datasets fail with `ValueError` before module resolution or network access. Empty statement frames remain classified as `RetryableSourceError`. Existing normalization, challenge-page blocking, and source-error taxonomy continue through `_batch()`.

## RED / GREEN

- Baseline: `tests.test_sources tests.test_pilot` passed 27 tests before edits.
- RED: the required focused one-table test exited 1; all three dataset subtests failed with the expected `AttributeError` because `AKShareSource.fetch_financial_statement` did not exist.
- Focused GREEN: the four new source behaviors plus the pilot compatibility guard passed 5 tests.
- Source and pilot GREEN: 31 tests passed.

## Verification

- Full regression: 246 tests passed with `unittest discover -s tests -t tests -p 'test_*.py' -v`.
- `py_compile` passed for `ashare_pipeline/sources.py`, `tests/test_sources.py`, and `tests/test_pilot.py`.
- `git diff --check` and staged `git diff --cached --check` passed.
- No real network request was made and no runtime data was modified.
- `TEMP`, `TMP`, and `TMPDIR` were directed to the worktree-local `.tmp-tests`; its resolved path was verified beneath the worktree and the directory was removed safely after testing.

## Commit

- `7fb2211365d43af62445e083817174965dbd6af7` — `feat: expose isolated financial statement fetches`
- Committed files only: `ashare_pipeline/sources.py`, `tests/test_sources.py`, and `tests/test_pilot.py`.

## Contract coverage

- Each supported dataset invokes exactly one corresponding AKShare method.
- The request contains exactly `symbol` and `report_period`.
- Metadata records target-period match count, column count, notice dates, and update dates.
- The compatibility wrapper delegates to the new method in deterministic balance/profit/cash order.
- The pilot continues to call only the compatibility wrapper.
