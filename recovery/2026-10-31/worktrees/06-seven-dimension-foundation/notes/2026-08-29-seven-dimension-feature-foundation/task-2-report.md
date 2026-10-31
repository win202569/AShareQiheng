# Task 2 Report — Financial Fact Catalog, Period Rules, and Industry Registry

## Summary

Implemented the versioned financial fact contract, ordered industrial financial field mappings, period classification, and an explicit provisional industry-template registry. Unknown industries fail closed to `unclassified`; no bank, insurance, or trading-liability fields are mapped into industrial debt/payable facts.

## RED / GREEN

- RED: `python -m unittest tests.test_financial_schema -v` failed as expected with `ModuleNotFoundError: No module named 'ashare_pipeline.financial_schema'`.
- GREEN: the same test suite passed after implementation.

## Verification

- Task 2 tests: 6 passed.
- Task 1 regression: 9 passed.
- `py_compile` passed for both new production modules.
- `git diff --check` passed.

## Commit

- `2290be9acc31569aaea07b2f1ddb69d7ad54f0d9` — `feat: add versioned financial fact and template registry`.
- Committed files only: `ashare_pipeline/financial_schema.py`, `ashare_pipeline/industry_templates.py`, `tests/test_financial_schema.py`, and `tests/fixtures/industry_template_registry_v1.json`.

## Registry coverage and residual risk

- Explicit current candidate industries: 60; fixture, `prefilter.json`, and production mapping matched exactly.
- Residual risk: the mapping is intentionally provisional and exact-label based. New or renamed source labels resolve to `unclassified` until explicitly reviewed and versioned.

## Review-remediation pass

- RED: the first run failed because the test imported the intentionally absent `UNMAPPED_COMMON_FACTS`; after making that audit constant available, the regression suite failed on inconsistent `period_kind`/duration start/effective timestamps, the absent repurchase slot, and the absent fixture `candidate_templates` map.
- GREEN: Task 2 now has 8 passing tests and the Task 1 contract regression has 9 passing tests (17 total). Both production modules also passed `py_compile`; `git diff --check` passed.
- Fix commit: `44da01065e6345875638ab2f4005d138ce8483b4` — `fix: close financial schema validation gaps`.
- Local repurchase-field evidence: `data/raw/akshare/cash_flow_sheet/2026-08-28/cb1c57872b5ca6e43a0ef3b2190d733e0ad29647c777c7174c4ea314faabc786.json` has 316 fields, no field containing `REPURCHASE` or `BUYBACK`, and does contain the mixed `PAY_OTHER_FINANCE` field. The latter remains deliberately unmapped. `share_repurchase_cash` therefore stays as an applicable nonfinancial slot with the versioned reason `source_field_unavailable`.
- Residual risk: share-repurchase cash remains unavailable until a dedicated, semantically verified source field is introduced and this versioned mapping is updated; it must not be inferred from mixed financing fields.
