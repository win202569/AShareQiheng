# Task C5 final diagnostic snapshot

This report complements `task-5-report.md` with the exact final read-only
23-member diagnostic snapshot requested after the complete Step 7 acceptance.

## Invocation

- HEAD: `f196952`
- Started: 2026-09-28 00:10:39 +04:00
- Completed: 2026-09-28 00:55:33 +04:00
- Measured build and snapshot time: `2693.3325926000252` seconds
- Exit code: `0`
- Construction: exactly one call to
  `FullValuationRankingTests.setUpClass()` followed by
  `fixture.repository.diagnostic_report(batch)` and `batch.to_dict()`.
- No second replay batch and no unittest suite were run.

The command used the project interpreter with `python -u -c` and recursively
converted mappings/tuples to ordinary JSON values before printing the complete
diagnostic report and `batch.to_dict()["ranking_summary"]`.

## Exact identity and dimensions

- Batch hash: `9c99c957a648a893ffa1d670422f4351a9779bc4281524cbbb3580bfd1aeec69`
- Security count: `23`
- Valuation/input row count: `69`

## Complete diagnostic report

```json
{
  "base_batch_full_validations": 1,
  "batch_hash": "9c99c957a648a893ffa1d670422f4351a9779bc4281524cbbb3580bfd1aeec69",
  "cohort_count": 3,
  "context_count": 69,
  "eligible_count": 62,
  "full_financial_rederivations": 0,
  "group_index_builds": 1,
  "peer_count_below_20": 19,
  "pending_reason_counts": {
    "cyclic_decision_pending": 2,
    "metric_value_invalid": 5
  },
  "phase_seconds": {
    "final_verification": 231.72724370006472,
    "identity_closure": 0.00043079990427941084,
    "input_registry_validation": 1914.1098954000045,
    "peer_grouping": 0.00033380009699612856,
    "peer_sorting": 0.0007510000141337514,
    "publication": 9.00006853044033e-07,
    "row_adjustment": 0.42974790011066943
  },
  "policy_batch_full_validations": 1,
  "registry_full_parses": 1,
  "scope_counts": {
    "template_primary_industry": 23,
    "template_secondary_industry": 20
  },
  "scored_input_count": 43,
  "security_count": 23,
  "sort_count": 3,
  "sorts_by_cohort": {
    "55f1ec3e8502e4c7f27ce2dcccf6060333ca470032a2755a071f3fc030904c29": 1,
    "7aa905f368f01cf9840800d04abf6cd3b2bc28e01d21373196177e3d3357d9d5": 1,
    "cd62bb528f182028417ca81ba0d0b44551b77c90b3df1e9cc8ad00996d5d2b9a": 1
  },
  "status_counts": {
    "adjusted": 1,
    "invalid_adapter_operand": 5,
    "passthrough_not_applicable": 58,
    "passthrough_unaffected": 3,
    "pending_policy_evidence": 2
  },
  "valuation_row_count": 69
}
```

## Canonical ranking summary

This is the exact `ranking_summary` embedded in `batch.to_dict()` and therefore
bound by the batch canonical identity.

```json
{
  "base_batch_full_validations": 1,
  "cohort_count": 3,
  "context_count": 69,
  "eligible_count": 62,
  "full_financial_rederivations": 0,
  "group_index_builds": 1,
  "peer_count_below_20": 19,
  "pending_reason_counts": [
    {"count": 2, "reason": "cyclic_decision_pending"},
    {"count": 5, "reason": "metric_value_invalid"}
  ],
  "policy_batch_full_validations": 1,
  "primary_scope_count": 23,
  "registry_full_parses": 1,
  "scored_input_count": 43,
  "secondary_scope_count": 20,
  "security_count": 23,
  "sort_count": 3,
  "status_counts": [
    {"count": 1, "status": "adjusted"},
    {"count": 5, "status": "invalid_adapter_operand"},
    {"count": 58, "status": "passthrough_not_applicable"},
    {"count": 3, "status": "passthrough_unaffected"},
    {"count": 2, "status": "pending_policy_evidence"}
  ],
  "valuation_row_count": 69
}
```

No missing field or counter is inferred in this report.

## Plan checkbox state

At final implementation HEAD `f399d07`, the independent whole-branch review was
CLEAN. The root agent then ran the six Stage C modules fresh from the beginning:
88/88 tests passed in 11875.957s, with 0 failures, 0 errors, 0 skips and exit
code 0. The command was:

`D:/Projects/AShareQiheng/.venv/Scripts/python.exe -u -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_valuation_adapter tests.test_formal_valuation_batch tests.test_formal_valuation_batch_guards tests.test_formal_valuation_ranking tests.test_formal_valuation_integration -v`

The tracked Stage C plan now records all 34 steps complete, including C5 Step 8
(independent review and root-level fresh verification) and C5 Step 9 (final
evidence closure and plan submission). Earlier interrupted runs remain recorded
only as interrupted and are not counted as passing evidence.
