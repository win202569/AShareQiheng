# Task 10 Report

- Baseline: `7fb2211365d43af62445e083817174965dbd6af7`
- Scope: created only `ashare_pipeline/deep_worker.py` and `tests/test_deep_worker.py`.
- Runtime data: read curated `prefilter.json` and `performance.json` only; did not open or migrate `data/state.sqlite3`.

## TDD evidence

- RED command: `python -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_old_parent_expands_to_three_dated_unique_statement_jobs -v`
- RED result: import failed with `ModuleNotFoundError: No module named 'ashare_pipeline.deep_worker'` (exit 1).
- GREEN Task 10: 12 tests passed.
- Task 1/2/5 regression: 79 tests passed.
- Full regression: 258 tests passed.
- Compile/diff check: `py_compile` and `git diff --check` exited 0.

## Contract delivered

- Deterministic candidate hash commits to canonical prefilter input hashes and sorted selected `(security_id, performance_input_hash)` pairs.
- Selected candidates without a matching curated performance row fail closed.
- Candidate mappings are defensive copies exposed through read-only proxies.
- Statement keys exclude candidate hash; payload retains first-enqueue candidate/performance hashes as audit evidence.
- Legacy parent transitions use an owned lease and Task 5 atomic completion/follow-ups.
- Current members expand in fixed balance/profit/cash order; removed members become superseded.
- Existing same-day children preserve first-enqueue payload when runtime candidate context changes.

## Commit

- `c3c6ade686774e42a3554cae282c6470fb5affe3` — `feat: expand legacy deep jobs into statement tasks`

## Independent review fix

- RED: focused missing `records_hash` and existing-child security mismatch tests both failed because no `ValueError` was raised.
- Both curated schema-v2 inputs now require a canonical SHA-256 `records_hash` matching the complete records list; prefilter and performance each cover missing, malformed, and mismatched hashes.
- Existing statement jobs are reusable only when kind, security, dataset, report period, and refresh date match the requested spec. Candidate/performance hashes remain first-enqueue audit values.
- Focused review tests: 11 passed, exit 0.
- Task 10: 23 passed, exit 0.
- Task 5 state-store regression: 59 passed, exit 0.
- Full regression: 269 passed, exit 0.
- `py_compile` and `git diff --check`: exit 0.
- Fix commit: `322f1a7ead1d3389c588edf3bb2bb94aa76c78b0` — `fix: validate deep planner reuse inputs`.
