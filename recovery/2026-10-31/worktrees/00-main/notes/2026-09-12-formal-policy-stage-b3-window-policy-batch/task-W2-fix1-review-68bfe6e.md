# W2 Fix Round 1 review — `6078c5f..68bfe6e`

## Finding Verdicts

### Prior Important finding 1 — RESOLVED

The focused fix closes the detached market-axis validation gap.

- `_closed_market_payload` requires all seven W1 axis fields, copies only those fields into a fresh `PolicyValue` envelope, and delegates validation to the existing F1 `market_window` DTO parser (`ashare_pipeline/formal_policy_evaluator.py:236-247`). This deliberately ignores surrounding W1 metadata for DTO validation rather than treating that metadata as source authority.
- `evaluate_rule` invokes that validation before `_market_reference`, pending-reason conversion, state derivation, or effect release (`ashare_pipeline/formal_policy_evaluator.py:393-415`). Malformed market axes therefore cannot reach the former full-match or partial-effect branches.
- The delegated F1 contract is closed over the allowed `price_state` and `veto_state` values, validates runtime codes and sorted uniqueness, enforces complete-price consistency, requires the exact `market_evidence_missing` reason for `confirmed_no_price_250`, and requires at least one pending reason for every `incomplete` price result (`ashare_pipeline/formal_policy_values.py:174-220`). Thus accepted incomplete results cannot produce aggregate `complete` evidence merely because their runtime pending list was absent.
- Four focused regressions cover the required reproductions: unknown `price_state`, missing mandatory no-price pending evidence, incomplete/proven without pending evidence, and an invented runtime code (`tests/test_formal_policy_evaluator.py:327-368`). Their shared fixture also includes extra `window_hash` metadata, confirming that surrounding metadata remains tolerated (`tests/test_formal_policy_evaluator.py:331-344`).
- The appended report contains the requested focused RED (`4` failures), focused GREEN (`4` tests, `OK`), amended evaluator run (`18` tests, `OK`), and mandatory compatibility run (`71` tests, `OK`) (`.superpowers/sdd/2026-09-12-formal-policy-stage-b3-window-policy-batch/task-W2-report.md:148-223`).

No independent test was run in this review: the supplied diff and the appended evidence answered the scoped verification without a remaining concrete doubt, consistent with the fix-round instruction.

## New Breakage

None found in the fix diff.

The new helper preserves valid outer evidence metadata, canonicalizes the accepted axis through the F1 DTO, and leaves effect binding unchanged after successful validation (`ashare_pipeline/formal_policy_evaluator.py:236-247`, `ashare_pipeline/formal_policy_evaluator.py:396-415`). The stricter rejection of tuple/noncanonical pending containers and other previously tolerated shapes is required by the closed F1 wire contract, not a regression.

## Out-of-Scope Observations

The previously noted Minor concerning positive-price complete-axis branch coverage remains deferred and was not reconsidered in this fix-round verdict, as directed. The implementer report records the same deferral (`.superpowers/sdd/2026-09-12-formal-policy-stage-b3-window-policy-batch/task-W2-report.md:245-247`). No untouched W2 behavior was re-reviewed.

## Final Fix Round verdict

**PASS.** The sole blocking finding under verification is resolved, all four required regression cases are present with appended RED/GREEN evidence, and no new breakage was found within `6078c5f..68bfe6e`.
