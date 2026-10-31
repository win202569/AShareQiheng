# Task 9 Independent Review — Isolated AKShare Statement Fetching

## Conclusion

APPROVED

## Findings

No blocking or non-blocking findings in `0ec27e0544112e5a1eaa8ae8fe12b655ea326d8b..7fb2211365d43af62445e083817174965dbd6af7`.

## Evidence

- Read the complete Task 9 plan section, the complete design, `task-9-brief.md`, `task-9-report.md`, and `review-0ec27e0..7fb2211.diff`; then inspected the actual `ashare_pipeline/sources.py`, `ashare_pipeline/pilot.py`, `tests/test_sources.py`, and `tests/test_pilot.py`.
- The changed-path boundary is exact: only `ashare_pipeline/sources.py`, `tests/test_sources.py`, and `tests/test_pilot.py` differ in the reviewed range. The worktree was clean before review and clean again after verification.
- `fetch_financial_statement()` validates the three-item dataset whitelist at `ashare_pipeline/sources.py:264-270`, before `_batch()`, `_module()`, or any remote method can run. Each accepted dataset selects exactly one AKShare API at `ashare_pipeline/sources.py:264-277`.
- `_batch()` preserves the required taxonomy: missing AKShare import becomes `TerminalSourceError` at `ashare_pipeline/sources.py:212-217`; call-time ordinary exceptions become `RetryableSourceError`, while 403/429/challenge signals become `SourceBlocked` at `ashare_pipeline/sources.py:220-231`; empty statement frames are retryable because Task 9 passes `require_rows=True`.
- The returned `FetchBatch` preserves source, dataset, request, records, fetch time, and source version, and adds deterministic metadata at `ashare_pipeline/sources.py:279-294`. The request is exactly `symbol` plus `report_period`. Common normalized target-date shapes (`YYYY-MM-DD`, ISO datetime with `T`, and datetime with a space) all produce the expected match count. Re-normalization in `FetchBatch.__post_init__` produces independent containers; a narrow reproduction confirmed the three compatibility-wrapper batches do not alias one another's request, records, or metadata.
- `report_period_match_count` is informational rather than a source-level success gate, which is consistent with preserving full statement history and leaving target-period retry/terminal decisions to the later worker policy.
- The compatibility wrapper delegates in fixed balance/profit/cash order at `ashare_pipeline/sources.py:296-300`. The pilot remains on the legacy wrapper at `ashare_pipeline/pilot.py:180-181`; its new guard test would fail if the pilot called the one-table method directly.
- `FinancialStatementSource` is importable and exposes the expected structural protocol method and `FetchBatch` return annotation.
- The new tests exercise the real dispatch boundary using a fake AKShare module, guard `_module()` against invalid-dataset access, require retryable empty results, and intercept the compatibility wrapper through an override. These checks are behavior-focused rather than assertions copied from implementation internals.

## Verification Run

- `python -m unittest tests.test_sources tests.test_pilot -v`: 31 tests passed.
- Independent no-network reproduction: dependency absence classified Terminal; socket/reset ordinary errors Retryable; HTTP 403, HTTP 429, captcha, and HTML challenge results SourceBlocked; date metadata, exact batch fields, protocol annotation, and cross-batch non-aliasing passed.
- First full discovery run exposed the documented Windows cross-drive temporary-directory issue (`C:` temporary path versus `D:` worktree), not an implementation failure. After setting `TEMP`, `TMP`, and `TMPDIR` to the worktree, `python -m unittest discover -s tests -t tests -p 'test_*.py'` passed all 246 tests.
- `git diff --check` for the reviewed range passed.

