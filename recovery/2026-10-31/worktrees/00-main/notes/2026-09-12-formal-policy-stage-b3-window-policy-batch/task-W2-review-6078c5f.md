# W2 review — 6078c5f

## Spec Compliance

**Changes required.** The valid-input implementation substantially follows W2, but the market-input boundary permits states and pending codes outside the closed contract, and can report complete evidence while the market decision itself remains pending. This prevents specification approval.

Scope: task W2 only, base `b875b053317e872ebf48a8b379345a3f462ad330`, head `6078c5f`. Reviewed the supplied brief, implementer report, and full supplied diff (the initial output truncated part of the evaluator, so only that unread portion was retrieved afterward). The diff adds only the two authorized implementation/test files. No Git operations, broad test runs, source-data access, network, or production actions were performed. The only written artifact is this requested review.

The implementer's RED/GREEN history is a report, not independently witnessed execution evidence. The test source does use the real fixture-exported rules and passes them through `parse_policy_rule`; there is no evidence of simplified substitute rule shapes or dishonest assertions. I did not rerun the reported 67-test suite or claim its reported timing as independently verified.

### Required-case audit

| Requirement | Review result |
| --- | --- |
| Both explicit quantiles; hostile Decimal precision | Covered in tests. Isolated F1 context is used. An additional focused check passed with precision 1, alternate rounding, and Inexact/Rounded traps enabled. |
| Five numeric operators, exact boolean/enum, inclusive boundary | Covered by real parsed rules and meaningful result assertions. |
| Both cyclic metrics required | Covered, including equality and one metric below its threshold. |
| Five-profit median/minimum, negative and zero | Covered. Original current profit, five annual profit values/evidence, sorted values, median, result, and signed V dependencies are retained. |
| Non-cyclic rules need no annual history | Covered. |
| Unresolved applicability | Covered; no effects released. The implementation also branches explicitly for not-applicable. |
| Missing selector keys | Scalar and annual code preserve explicit runtime shortages; missing annual key is covered. |
| Minimum cap and union of pool prohibitions | Covered. Caps remain signed decimal text; both expands to strong/wait. |
| Every underlying reason/trace retained | Decisions retain all signed effects; separate pool/status reasons retain their rule identity and copied trace. Cap combination does not remove source decisions. |
| Matched rule with signed pending requirement | Covered; matched and pending coexist. |
| Tail-20 proof with incomplete price | Covered for a valid W1 result, including withholding extra cap/status effects. Malformed DTO handling fails; see Important issue 1. |
| Confirmed no-price retains pending and both prohibitions | Covered for a valid W1 result. An inconsistent detached no-price DTO can erase the pending requirement; see Important issue 1. |
| Clear rule retains authenticated input pending | Covered by the cyclic conjunction case. |
| Complete market axes yield signed matched/clear effects | Code branches exist; positive-price cases are absent from tests. See Minor issue 2. |
| Exact seven aggregate fields; no scores/ready/eligible | Return shape is closed by inspection and passed an independent exact-key assertion. |
| Pure inputs, no proof authority or V adapter | Satisfied by the implementation; it performs no repository, network, scoring, or adapter operations. |

## Strengths

- The evaluator separates selector reads, quantiles, normalization, pending binding, effect selection, and aggregation into small helpers. The 558-line module is understandable at this scope; the large `evaluate_rule` dispatcher is the main place to keep future changes contained.
- Cyclic normalization retains original profit values and evidence without imposing cap defaults in the evaluator (`ashare_pipeline/formal_policy_evaluator.py:254`, `:328`).
- Pending evidence survives clear decisions and aggregation, and signed pending effects are kept separate from executable effects (`ashare_pipeline/formal_policy_evaluator.py:243`, `:355`, `:498`).
- Input-derived rule parameters/effects and aggregate reasons are copied. A focused valid-input check confirmed that mutating the original rule/annual records does not alter the decision and mutating a decision does not alter its already-built aggregate (`ashare_pipeline/formal_policy_evaluator.py:46`, `:446`, `:496`).
- Canonical ordering works for distinct active-rule decisions in the intended per-security input: reversing their input order produced identical canonical aggregate bytes. Arithmetic also passed the additional hostile-context check. No issue was found in those focused checks.

## Issues by severity

### Critical

None found.

### Important

**1. Validate the closed market result before deriving effects or evidence completeness.**

Locations: `ashare_pipeline/formal_policy_evaluator.py:378`, `:386`, `:391`, `:396`, `:409`, `:554`.

The market branch requires only `price_state`, `veto_state`, and `pending`; it does not validate the price-state enum, complete/incomplete payload consistency, or the closed runtime pending codes. Any price state other than the literal `incomplete` bypasses the incomplete branch. In addition, the special proven-veto/incomplete-price branch skips the missing-pending fallback used by the following branch.

A focused, read-only reproduction using a real parsed market rule with an additional signed T cap produced:

| Detached market input | Actual result |
| --- | --- |
| `price_state="unknown"`, `veto_state="proven"`, `pending=[]` | `matched`; cap and pool prohibition released; aggregate evidence `complete` |
| `price_state="confirmed_no_price_250"`, correct null price fields and stale-at-least 250, but `pending=[]` | `matched`; aggregate evidence `complete`, losing required `market_evidence_missing` |
| `price_state="incomplete"`, `veto_state="proven"`, `pending=[]` | Decision `pending_evidence`, pool prohibition released, but aggregate evidence `complete` |
| `price_state="incomplete"`, `veto_state="proven"`, `pending=["invented_reason"]` | Unknown runtime reason copied into output |

These are syntactically invalid DTOs, not evidence-authentication scenarios; rejecting them does not grant the evaluator any source authority. The existing F1 market DTO already expresses the relevant closed state/field/pending relationships (`ashare_pipeline/formal_policy_values.py:174`). W2 should validate the detached W1 axis payload against that contract, while allowing the documented surrounding W1 evidence metadata, before selecting effects. Invalid/inconsistent shapes and unknown runtime codes must fail; every accepted incomplete result must retain an explicit pending requirement. Add regression coverage for the cases above.

This violates the closed failure taxonomy and market/pending invariants in Stage B design sections 8.1 and 9.2, and the brief's requirement that confirmed no-price keep market evidence missing. W3 authentication should not be used to substitute for this pure DTO validation.

### Minor

**2. Add the untested valid positive-price market branches to the focused matrix.**

Locations: `tests/test_formal_policy_evaluator.py:279`, `:304`; exercised implementation branches are `ashare_pipeline/formal_policy_evaluator.py:409` and `:411`.

The two market tests cover an incomplete price with a proven veto and confirmed no-price. Neither constructs a `positive_close_complete` W1 result. Consequently, the explicit requirement that two complete axes yield matched or clear is only partially exercised. Add small real `evaluate_window` fixtures for a recent effective trade (clear, no effects) and a complete price older than the tail-20 window (matched, all and only signed effects). Include a veto-pending/incomplete case and not-applicable/invalid-applicability assertions when extending the existing matrix; these states currently lack direct tests. This is a coverage gap, not a claim that those valid branches presently compute incorrectly.

## Assessment

**Spec Compliance: not approved. Task Code Quality: not approved pending Important issue 1. Overall: changes required; do not advance the W2 gate yet.**

The central arithmetic, normalization, aggregation, and valid-input detachment behavior are sound in the reviewed scope. The blocking issue is localized to market DTO validation and pending consistency. Fix that boundary and add the focused regressions; the minor branch-coverage improvement can be completed in the same test update. No whole-branch or production-readiness verdict is implied.
