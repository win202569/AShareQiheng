# Stage D Task 4 implementation report

Status: GREEN, 37/37 tests passed. Commit `3916065333df1a7c2686185c5d1f0dbde7b75915` (`feat: calculate capped formal scorecards`).

## Scope

- Added only the requested production module and two test modules.
- `build_final_score_card_batch` accepts an exact, verified `PolicyAdjustedScoreInputBatch`; the calculation path uses no score double and cannot mint proof through its detached pure helper.
- The final fixture uses the already-supported, signed 23-member universe: FOCAL and SH600000 are ready; the other 21 are pending. FOCAL has signed G caps 80 and 1, M cap 80, and a verified no-consensus confidence cap 0.90; SH600000 has no dimension cap and receives producer-backed five-year score history.
- SH600000 also receives its own producer-backed covered consensus Context; the stock fixture only publishes one for FOCAL.
- The final score follows raw seven dimensions -> per-dimension minimum of all proven cap effects -> `min(raw, cap)` -> original weighted coverage and confidence -> S0/Sc/Sbase/B/risk/grades. It retains raw and capped dimensions, cap rule/evidence trace, D/P/H/K/C, risk components, the complete source input and all source/card/batch hashes. Pending D1 entries yield no card and retain all reason categories.

## RED

Command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_scoring tests.test_formal_final_scoring_guards -v`

Result: exit 1, two expected import errors; both new test modules failed with `ModuleNotFoundError: No module named 'ashare_pipeline.formal_final_scoring'` before production code existed. This common missing-module RED covers each named arithmetic and guard test in those modules.

Per-test RED -> GREEN (each had the common missing-module RED, then passed in the final 37-test run):

| Area | Test | Final |
| --- | --- | --- |
| Arithmetic | `test_final_card_rebuilds_all_seven_dimensions_from_final_slots` | PASS |
| Arithmetic | `test_multiple_caps_take_minimum_without_changing_confidence` | PASS |
| Arithmetic | `test_cap_never_raises_a_dimension` | PASS |
| Arithmetic | `test_exact_sc_b_risk_and_grades_use_unrounded_decimal` | PASS |
| Arithmetic | `test_verified_no_consensus_caps_confidence_at_point_90` | PASS |
| Arithmetic | `test_pending_input_has_no_card_and_preserves_all_reasons` | PASS |
| Arithmetic | `test_no_cap_parity_matches_existing_arithmetic_but_not_proof_type` | PASS |
| Guard | `test_plain_dict_and_pre_policy_calculation_cannot_create_final_proof` | PASS |
| Guard | `test_cross_batch_or_unknown_selector_cannot_launder_a_card` | PASS |
| Guard | `test_unknown_cap_dimension_and_summary_disagreement_are_rejected` | PASS |
| Guard | `test_nonnumeric_slot_values_and_invalid_caps_are_rejected` | PASS |
| Guard | `test_global_decimal_context_cannot_round_or_raise_in_final_arithmetic` | PASS |
| Guard | `test_cards_cannot_be_copied_pickled_or_reconstructed` | PASS |
| Guard | `test_method_replacement_and_module_helper_rebinding_are_detected` | PASS |
| Guard | `test_revoked_d1_publication_revokes_descendant_on_access` | PASS |

## GREEN and regression

Command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_scoring tests.test_formal_final_scoring_guards tests.test_formal_scoring tests.test_formal_scoring_consensus_registry -v`

Final GREEN: `Ran 37 tests in 7603.696s`, exit 0, `OK`: seven new arithmetic, eight new guards, and 22 existing pre-policy/consensus-registry tests all passed.

Second GREEN attempt: 37 tests in 5942.017s, exit 1: 36 passed, one assertion failure. All eight new guards, all 22 old pre-policy/registry tests, and six of seven new arithmetic tests passed. Only `test_no_cap_parity_matches_existing_arithmetic_but_not_proof_type` failed because SH600000 was still `pending_evidence`. No production implementation was changed.

Narrow diagnostic command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -B -u -c 'from tests.test_formal_final_scoring import shared_ready_batch, NO_CAP_PEER; fixture, batch, cards = shared_ready_batch(); row = batch.input_for(NO_CAP_PEER); print("STATUS", row.status, "REASONS", row.reasons, "BASE", row.base_pending_reasons, "POLICY", row.policy_pending_requirements, "VALUATION", row.valuation_pending_reasons, flush=True)'`. Exit 0. The genuine 20-member batch returned `reasons=('base:metric_pending:T.expectation_change:peer_count_below_20',)`, with the same underlying base reason, empty policy pending requirements, and empty valuation pending reasons. FOCAL's verified no-consensus branch leaves only 19 numeric T peers in a 20-member universe. The new test fixture therefore uses the existing signed 23-member configuration, leaving at least 20 numeric T peers without altering any D1 or pre-policy behavior.

First GREEN attempt: 37 tests in 6232.319s, exit 1: 34 passed, two assertion failures and one error. All eight new guards and all 22 old pre-policy/registry tests passed. The two assertions treated D1's canonical `confidence_cap` text as a Decimal; corrected those tests to compare text at the D1 boundary and convert to Decimal only for the detached pure helper. The error expected SH600000 ready while the stock fixture had no consensus Context for SH; added a genuine producer-backed covered Context in the new test fixture. No production implementation changed after this attempt. A separate three-member diagnostic was stopped before returning a row and is not validation evidence.

## Guard diagnosis

- Ambient Decimal context: final dimension sums use an explicit 50-digit context; captured confidence/arithmetic helpers each use their own explicit context. The test compares full card canonical bytes and scores under hostile `Context(prec=2)`.
- Source revocation: each card access rechecks the original D1 batch, row, their canonical bytes, and row membership. The guard test temporarily revokes the D1 publication flag and expects both new card creation and an existing card access to fail, then restores it.
- Numeric boundary: the detached core rejects non-text canonical values, non-finite values, and huge exponents before arithmetic. The public proof constructor accepts only genuine D1 batch and row types.
- Captured pure helpers do not mint proof; module rebinding and class-method replacement are detected by proof dependency sealing. Cross-batch selectors, copies, pickle, and unregistered instances are rejected.

## Uncovered items

The named four-module regression passed. The entire repository-wide suite was not run. No new source, schema, data, SQLite/WAL/SHM artifact, progress file, backup, or pre-policy module edit was added. The ignored report is not part of the commit. The genuine 23-member fixture is intentionally slow (final full run 7603.696s); performance optimization is outside Task 4.

Post-commit `git status --short` contains only the two pre-existing, untouched modifications: `.superpowers/sdd/.gitignore` and `docs/superpowers/plans/2026-09-28-formal-final-scoring-stage-d.md`. The staged path check and `git diff --cached --check` passed before committing exactly the three new files.
