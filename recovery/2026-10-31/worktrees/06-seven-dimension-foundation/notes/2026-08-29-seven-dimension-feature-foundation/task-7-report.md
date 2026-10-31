# Task 7 Report — Point-in-Time Financial-Fact Normalization

## RED / GREEN

- Initial RED: after adding `tests/test_financial_features.py` first, the required
  `FinancialFactSelectionTests` command failed with
  `ModuleNotFoundError: No module named 'ashare_pipeline.financial_features'`
  (exit 1).
- Hardening RED: two fail-closed regressions then demonstrated selection of a
  partially unrankable logical fact, acceptance of a malformed date suffix, and
  leakage of `KeyError` from a calendar row missing `is_trading_day`.
- GREEN: `tests.test_financial_features` passed 21 tests. Task 1–6 contract and
  repository regressions passed 116 tests. Full discovery passed 206 tests.
- `py_compile` passed for the production and test modules; cached
  `git diff --check` passed.

The initial full-suite runs fixed `TEMP` and `TMP` to the worktree-local
`.tmp-tests` directory. Review remediation also ran the Task 7 module with both
variables unset and no pre-created parent. The temporary directory was removed
before each commit.

## Point-in-time and conflict evidence

- Date-only `NOTICE_DATE` and `UPDATE_DATE` values normalize to 23:59:59
  Asia/Shanghai. Effective time is the 15:00 Asia/Shanghai close of the first
  explicitly supplied trading date strictly after the later local source date.
- `effective_at_utc <= as_of_utc` is only the visibility gate. The business
  rank is exactly announcement, optional source update with a fixed missing
  sentinel, then verified snapshot fetch time.
- Content hash, raw hash, fact ID, and effective time do not enter the business
  rank. Top-rank value/nature conflicts produce
  `conflicting_fact_versions`; unit conflicts produce
  `conflicting_fact_units`; tied semantically identical facts alone use raw hash
  and ID for deterministic deduplication.
- Any visible version lacking a valid snapshot fetch time makes its whole
  logical fact unrankable and blocked.
- The approved balance tolerance passes a CNY 500 gap on CNY 1,000,000 assets
  and blocks a CNY 10,000 gap.

## Normalization and calendar evidence

- Numeric zero creates a fact; null creates no fact; bool, NaN, and infinities
  create no affected fact and emit `invalid_financial_value`.
- A missing/mismatched security identifier or invalid report date clears the
  entire statement batch. FY, H1, Q1, Q3, and OTHER facts are retained.
- Trade-calendar extraction accepts only the `trade_dates` schema, a valid
  covering request, exact ISO dates, exact 0/1 flags, no duplicate dates, every
  natural date in the request interval, and no dates outside it. Input record
  order is irrelevant; it returns sorted unique explicit sessions and never
  guesses weekdays.
- `QualityIssue.details` is recursively defensively frozen with deterministic
  mapping order.

## Fixture evidence

Added fixed offline fixtures for a general nonfinancial company, a bank, a
real-estate company, and a trade calendar spanning 2021-01-01 through
2026-09-07. Each company fixture has all three statement batches and FY2021–
FY2025, 2025H1, and 2026H1, with intentional missing-value cases and no scoring
output. The test-local validator rejects a missing batch, missing required
period, missing identity/date field, and insufficient calendar span.

An offline build smoke check produced facts from all nine statement batches:
general 49/41/14, bank 21/28/7, and real estate 48/35/14 (257 total).

## Commit

`da4f5b8 feat: normalize point-in-time financial facts`

Only the six brief-specified implementation/test/fixture paths were committed.
This report is intentionally uncommitted.

## Residual risk

`VerifiedSnapshot.read_verified()` intentionally exposes its verified payload as
the ordinary `FetchBatch` type, so `trading_days_from_batch()` cannot itself
cryptographically distinguish a verified batch from a caller-constructed one.
The trust boundary remains the Task 6 verified-read call; Task 7 validates the
entire calendar batch structure and range and fails closed on malformed input.

The fixed calendar is a deterministic integration fixture, not a replacement
for production exchange-calendar snapshot refreshes.

## Independent-review remediation

### RED

Before changing production code, the following clean-environment command was
run with `TEMP` and `TMP` unset:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features -v
```

It ran 28 tests and failed with 20 assertion failures and 4 errors. The failures
demonstrated permissive report/source dates, discarded SECUCODE exchange
suffixes, sparse/duplicate/missing-endpoint calendars, non-string snapshot
times escaping as `AttributeError`, and the original sparse fixture. A second
focused RED run added ordering independence and produced 2 errors because a
complete shuffled calendar was rejected by both production and the test-local
validator.

### Fixes and GREEN

- `REPORT_DATE` and calendar dates now require the complete lexical form
  `YYYY-MM-DD`. Source dates distinguish that exact date-only form from the
  explicitly accepted ISO timestamp form `YYYY-MM-DD[T ]HH:MM:SS`, optional
  microseconds, and optional `Z` or `±HH:MM`; malformed/basic/week/suffixed and
  whitespace-padded forms fail closed.
- `SECURITY_CODE` requires exactly six digits. `SECUCODE` requires exactly
  `dddddd.SH` or `dddddd.SZ`, maps the suffix to the complete security ID, and
  must agree with both `SECURITY_CODE` and the expected ID when both fields are
  present.
- Calendar records must contain every requested natural date exactly once.
  Duplicate dates, interior holes, and missing endpoints fail closed. Complete
  shuffled input is accepted, and returned sessions remain sorted.
- Missing, malformed, integer, boolean, and list snapshot fetch times block the
  affected logical fact with `snapshot_fetch_time_missing` or
  `snapshot_fetch_time_invalid`; no parser implementation exception escapes.
- Test fixture copying uses the default temporary directory and passes without
  a prebuilt `.tmp-tests` directory.

Fresh final verification on the staged tree:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features
# Ran 30 tests ... OK

D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest `
  tests.test_feature_contract tests.test_financial_schema tests.test_state_store `
  tests.test_sources tests.test_snapshot_store tests.test_snapshot_repository `
  tests.test_financial_features
# Ran 146 tests ... OK

D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest discover -s tests
# Ran 215 tests ... OK
```

`py_compile` and cached `git diff --check` also passed. The final Task 7 run was
performed with `TEMP`/`TMP` unset and no `.tmp-tests`; the full run used the
worktree-local temp directory, which was resolved, containment-checked, and
deleted before commit.

### Calendar provenance

The replacement test fixture came from a successful read-only BaoStock call:

```text
baostock.query_trade_dates(start_date="2021-01-01", end_date="2026-09-07")
login code=0, query code=0, source_version=00.9.30
fetched_at_utc=2026-08-30T10:54:24+00:00
rows=2076, first=2021-01-01/0, last=2026-09-07/1
```

The SHA-256 of the source rows serialized as compact JSON pairs
`[[calendar_date,is_trading_day], ...]` is
`efd5d2c2ae115305aac5b8239df00a8a780f391a010d4f09ab91126cd43bfe17`.
The committed JSON fixture file SHA-256 is
`4cdb6dc858a5f546f9c824f0eb9df056ce2d74839a840c8398615d25d5b292ad`.
The fixture stores the query method, result code/message, row count, source
version, aware UTC fetch time, and this digest in its auditable metadata.

### Remediation commit

`17f5865 fix: harden point-in-time fact inputs`

The original `da4f5b8` commit was not rewritten. This report remains
intentionally uncommitted.
