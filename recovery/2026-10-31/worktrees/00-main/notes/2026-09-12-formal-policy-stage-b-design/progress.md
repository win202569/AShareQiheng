# Stage B design and planning progress

Date: 2026-09-12
Workspace: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`
Branch: `codex/formal-v3-implementation`
Baseline: `29cf92362574945f9ca41d2c9374a56bcc9ffe90`

## Authority and scope

User asked to continue after Stage A acceptance. The approved parent specification is
`docs/superpowers/specs/2026-09-12-formal-policy-contract-design.md`.
Its sections 7 and 10 require a separate Stage B design before implementation.
This note records exploration and section-level approval, not approval of a complete
new specification or production rules.

Stage A remains complete. Do not rerun or reopen it. Do not modify production data,
SQLite/WAL/SHM, prior outputs, or the main checkout. Do not merge or push.
Retain the unrelated untracked `tmpj4zv9_fq/` directory.

## Design checklist

- [x] Read the approved architecture and Stage A final verification.
- [x] Classify this work as architectural; announce brainstorming and read-only parallel inventory.
- [x] Inspect financial projection, formula evaluation, and batch publication boundaries.
- [x] Receive the parallel market/calendar interface inventory.
- [x] Present alternatives and the recommended Stage B scope/order; user approved with “是”.
- [x] Agree evidence interfaces, numeric boundary, and batch consistency; user approved section 2 with “是”.
- [x] Agree section 3: policy outputs, failure classification, and acceptance criteria; user approved with “是”.
- [x] Write, self-review and locally commit the separate Stage B specification after design approval.
- [x] Obtain user review of the written specification, then invoke writing-plans.

The three chat-design exploration turns performed no implementation, tests, Git
writes, network requests, or database execution. The subsequent documentation turn
created and committed only the written specification; details are recorded below.
This progress note remains local, ignored and retained.

## Verified financial and batch findings

- `FormalFeatureCurrentInput` is a provider-owned complete current generation, not a proof.
  The feature repository rechecks provider snapshots, persisted facts/issues, signed
  registry identity, stored receipts, and generation changes before returning sealed projections.
- The existing metric projection selector in `formal_feature_repository.py` requires every
  selected slot to have `required=true`. Stage A explicitly permits policy rules to depend
  on optional slots without changing legacy completeness. Stage B therefore needs a narrowly
  scoped policy projection rather than relaxing the metric interface.
- `formal_metric_features.evaluate_selected_features` is a pure evaluator and does not
  mint repository proof. Its explicit contract preserves existing V6 float semantics.
- `formal_financial_features._evaluate` performs float feature arithmetic. Existing metric
  ranking converts derived values with `Decimal(str(value))`. Stage B must specify its own
  numeric boundary explicitly; do not silently rewrite V6 arithmetic or claim existing
  evidence has exact source-decimal precision.
- Annual policy observations need actual fact identities and signed AST periods/units;
  generic history endpoint presence or evidence-reference counts do not prove each series.
- `formal_metric_engine` demonstrates frozen-universe enumeration, fresh same-root inputs,
  cross-member rechecks, unpublished batch capabilities, and revocation on failed finalization.
  These are reusable design patterns, not an already implemented policy factory.

## Verified market/calendar findings

Read-only inventory by `/root/policy_b_market_inventory` completed with no changes
or execution of project code.

- Existing `market_close` is a single aggregate with a strictly positive, non-null
  `valid_close`; it has no per-session observations or confirmed-no-price branch.
  Its `is_effective_trade` flag does not itself prove the volume/turnover predicate.
- Existing trading-calendar values provide sorted unique dates and a source binding,
  but do not prove completeness for the requested 20/250-session window.
- Current descriptor/source request vocabulary has a single `period_or_date`, not
  explicit start/end bounds. Do not encode an informal range inside that field.
- `no_coverage` belongs only to consensus. Missing Context or `None` cannot be used
  as confirmed absence of effective trades.
- Reuse source verification, request and generation fingerprints, canonical sealed
  facts, repository conflict/correction checks, and calendar identity binding.
- Add a versioned window/range interface. If collection spans multiple snapshots
  or pages, preserve and revalidate each lineage; the old one-snapshot envelope
  alone is insufficient. Preserve the old market-close format.

## Approved scope and order

Compared evidence-first layering, market-first vertical delivery, and one complete Stage B
integration. User approved evidence-first layering: dedicated financial/annual proof plus versioned
market-window proof and explicit Context coverage, followed by policy outcomes and batch closure.
All alternatives must preserve the approved trust boundaries. None delivers final adjusted V
percentiles, final scores, or stock pools; those remain Stage C and later selection work.

Do not ask again about the frozen cutoff, seven weights, universe scope, strict exclusions,
20/50 pool limits, or industry caps. Do not choose production quantile algorithms or field
mappings from synthetic fixtures.

## Approved section 2 — evidence interfaces, numeric boundary, consistency

Status: user approved the section with “是”. A separate written specification and
implementation plan are still required. This approval does not choose production
rules/mappings or authorize production execution.

1. One policy evidence factory enumerates the verified frozen universe and derives
   requests from the same-root signed policy/template/industry definitions. It does
   not accept caller-selected securities, guessed cyclic membership, raw policy
   values, prefabricated outcomes, or bare coverage booleans. Required keys are
   policy-owned; optional legacy slots remain optional to old metric/completeness APIs.
2. A dedicated financial projection authenticates the complete current provider
   generation, stored feature receipt, facts/issues, and selected signed formulas.
   Each annual observation retains actual underlying fact identities, units and
   dependency periods, including lawful opening/closing balance inputs. Do not
   gate policy evidence on all seven scores being complete. Fetch cyclic history
   only when signed industry applicability is established; unresolved applicability
   is pending, not non-cyclic.
3. Preserve V6 financial/feature arithmetic and values. At the explicit versioned
   policy numeric boundary, convert an authenticated finite derived value using
   Decimal(str(value)); subsequent policy arithmetic uses precision 50 and
   ROUND_HALF_EVEN. Bind both the original projection identity/value and conversion
   version. This does not restore decimal precision lost in existing float facts
   or authorize a rewrite of signed financial formulas. No display rounding before
   comparisons, no silent unit conversion, and no default production quantile method.
4. A new versioned calendar/range proof establishes exact interval completeness and
   ordered trading sessions, separately from the old calendar identity binding.
   The new market window binds that proof, explicit request bounds, per-session
   coverage, and all contributing request/snapshot/parser/mapping generations.
   The factory derives effective trading from exchange permission and positive
   volume/turnover. Existing single-date requests and positive market-close format
   remain unchanged.
5. Market outcomes distinguish a supported nearest effective positive close,
   fully covered 250-session confirmed absence, and incomplete evidence. Effective
   trading with a missing/untrusted close is incomplete, not confirmed absence.
   For a positive close, prove every subsequent session through freeze; for absence,
   prove every session in the full 250-session interval. A separately derived proof
   of the terminal 20 non-effective sessions may survive a longer-window gap, but
   does not remove pending price evidence. The proof is factory-derived, not a
   caller boolean. Sealed incomplete evidence authenticates diagnostics/provenance,
   never completeness.
6. Security/regulatory/event inputs retain the exact authorized entry plus its
   source and request scope. An omitted flag is not false, and unquantified events
   are not assigned a numeric zero. Only the signed type-specific coverage contract
   can justify clear/not-applicable outcomes.
7. Collection/materialization happens outside the short policy batch read barrier.
   Recheck roots, provider generation, persisted inputs, calendar and all raw source
   lineages before releasing a single immutable batch. A source correction or trust
   failure aborts the affected attempt and revokes unpublished descendants; preserve
   existing historical artifacts and recompute only under a new identity. Reusable
   cached content is not automatically proof of the current generation.

Failure-classification constraint for the next section: do not adopt a blanket
`conflict -> incomplete` conversion. Existing leading-version/source-integrity
exceptions abort the attempt. Only explicit authenticated domain issues/absence
states may produce pending evidence. Never classify exceptions by message strings.

Parallel review: `/root/policy_b_market_inventory` returned ten market-contract
recommendations, incorporated above with the source-integrity exception distinction.
Root inspected `FormalFinancialFact.value: float`, the required-only metric selector,
the metric batch publication guard, and the frozen-universe Context proof lifecycle.

## Approved section 3 — policy outputs, failures, and acceptance

Status: user approved the section with “是”. All three chat design sections are
approved. User review of the complete written specification still precedes
implementation planning.

### Outputs and aggregation

- Emit a deterministic, immutable decision for every applicable signed rule and
  frozen security, with rule/template/semantic identity, input/evidence hashes,
  effective algorithm version, actual operands/thresholds, evaluation state,
  independently proven effects, and explicit pending requirements. A missing
  applicability prerequisite remains pending; only a verified non-applicable
  classification may produce `not_applicable`.
- Evaluation states remain `matched`, `clear`, `not_applicable`, and
  `pending_evidence`. `clear` requires sufficient evidence for a false predicate;
  it is not a global safety or pool-eligibility label. A rule whose signed
  `on_match` includes a pending-evidence effect may be matched yet still block
  final evidence completeness; do not infer readiness from decision labels alone.
- Evidence incompleteness does not invent a match. Preserve separately proven
  effects, including the independently verified terminal 20-session market veto,
  even when the longer price window is pending. Ordinary missing scalar/series
  inputs must not execute unproven on-match effects. Evidence gaps are not cured
  by another rule's veto, and evaluation must not short-circuit on the first veto.
- Aggregate dimension caps by the minimum per dimension, pool prohibitions by
  set union, and retain every supporting rule/evidence reference. Preserve
  independent states and all pending requirements. Normalize ordering and retain
  distinct reasons when effects are deduplicated. Record the verified normalized
  profit basis and its full current/five-year lineage; do not replace V percentiles
  or calculate final seven-dimension scores here.
- A successfully assembled policy batch can contain pending securities. Batch
  integrity/completeness of enumeration is distinct from each security's evidence
  completeness. Neither the contract, evidence object, nor policy result alone
  may be accepted as a final scorecard or as proof of selection into either pool.

### Failures and retained progress

- Explicit authenticated missing facts/receipts/coverage, unsupported actual data
  units or denominator conditions, and recorded domain conflicts yield typed
  pending requirements. Missing response or flag never becomes false/clear.
  A transient fetch failure may be recorded as an operational collection outcome,
  but cannot be upgraded into verified market absence.
- Malformed/unsupported contracts, same-root or signature mismatches, forged or
  mutated proof objects, tampered/missing verified source artifacts, leading-version
  ambiguity, provider/DB/source corrections during assembly, and changed validation
  dependencies terminate the affected construction attempt. Do not publish a
  partially valid proof batch; revoke unpublished descendants and keep diagnostic
  failure records separate from policy evidence. No exception-message parsing and
  no catch-all conversion into pending.
- Retain successful raw snapshots, existing historical data and completed work.
  Resume collection only for failed/missing/changed requests under the proper new
  identity. A resumed policy batch must revalidate all reused dependencies and
  deterministically reassemble the full frozen enumeration; a saved cursor is
  not proof that old evidence is still current. Do not extend this phase into
  scheduling, a new production crawler, final-score persistence or publication.

### Offline acceptance matrix (planned, not executed)

1. Genuine signed synthetic fixtures exercise all five templates, all required
   rule semantics, explicit true/false/unknown state coverage, and non-cyclic versus
   unresolved applicability. Synthetic values/mappings/algorithms are not production approval.
2. Financial tests cover optional slots without changing old required-only metric
   behavior; missing receipts, facts and issues; each FY2021–FY2025 observation;
   missing/wrong-year/repeated observations; valid opening/closing balance inputs;
   signed formula/unit/period lineage and forbidden substitutions.
3. Numeric tests cover Decimal(str(value)) compatibility with original finite
   feature values, explicit arithmetic context independent of ambient precision,
   quantile methods (1..5 produces 4.2 versus 4), equality at the 80th percentile,
   both-current-metric conjunction, five-profit median/minimum, zero/negative values
   where valid, nonfinite rejection, and comparisons before display rounding.
4. Market tests derive dates/counts from exact exchange sessions. Cover stale
   0/1/19/20/249/250: the first session in an inclusive 250-session window is
   still usable (249 later sessions); the preceding close is outside. Prove
   early stopping only after all later sessions are covered; require every
   session for confirmed absence. Test holiday calendars, wrong exchange/range,
   pagination/lineage gaps, duplicate/conflicting daily rows, preclose substitution,
   and an effective-trade row with no trustworthy positive close.
5. Mixed market tests include a proved 20-session veto with a gap in sessions
   21–250 (keep veto plus pending), a gap within the latest 20 (no guessed veto),
   valid old in-window close plus veto, and full 250-session absence (veto plus
   market_evidence_missing). Source-integrity failures still abort rather than pending.
6. Aggregation tests cover multiple caps/prohibitions/statuses, canonical order,
   complete trace retention, matched rules that themselves request pending evidence,
   and a known veto coexisting with unrelated missing evidence. Missing outcomes
   cannot be erased by sorting, deduplication, or early return.
7. Trust tests cover cross-root/security/template/cutoff/batch mixing, copied and
   mutated objects, before/after source/calendar/provider/DB corrections, equal-leading
   versions, and failures during finalization. Failed construction exposes no valid
   downstream proof. Historical audit identity is not current evidence eligibility.
8. Compatibility and determinism: old market-close/calendar/request formats, old
   required-slot completeness, V6 feature arithmetic and pre-policy scoring remain
   unchanged. Reordered inputs and resume with unchanged verified inputs produce
   identical canonical results; corrections produce new identities. Unit tests use
   small fixtures; a bounded integrated suite checks complete-batch behavior without
   live-network or production-database access.

Parallel review: `/root/policy_b_market_inventory` supplied nine market-specific
acceptance cases. Root reconciled these with parent sections 5–8 and the existing
typed on-match/pending-effect contract. No tests or project-code execution occurred
in this design turn; only this retained local progress note was updated.

## Written specification handoff

- Specification: `docs/superpowers/specs/2026-09-12-formal-policy-stage-b-design.md`.
- Local document-only commit: `76997ad` (`docs: specify formal policy stage B evidence and outcomes`).
- Specification SHA-256: `9c5b13ca35cd0459f0a65da4256dd64aa12cf07e09ecfb8551791249c89934db`.
- Status: written specification awaiting user review; no Stage B implementation
  plan or code has been started. Stage A remains complete.
- Main agent reread the full document and checked scope, ambiguity, closed versions,
  numeric bridge, evidence/result permissions, failure taxonomy and acceptance.
- `/root/policy_b_market_inventory` independently checked the new signed range,
  calendar/window and current/history sections. Incorporated all four findings:
  non-circular calendar bootstrap, a static `calendar_anchor_selector` distinct
  from old date-only binding, authenticated bounded pagination, and explicit
  current/historical lineage identities on both final evidence objects.
- Additional inline corrections: exact existing financial method name, canonical
  request fingerprint, requested versus proven calendar subinterval, explicit
  publication/effective-time evidence, market units and signed conversion boundary,
  generic boolean expected comparison, and runtime versus signed-policy reason codes.
- New source v2 keeps legacy `configs` unchanged and adds separate `range_configs`;
  the same nine-role graph and old scoring descriptors remain the anchors. New
  range tasks/snapshots/receipts are additive proposed formats, not capabilities
  already implemented in the current code.
- Fresh document checks: no TODO/TBD/FIXME or missing-section placeholders;
  both relative Markdown references resolve; no trailing whitespace; staged
  `git diff --cached --check` clean; staged scope was exactly one specification,
  296 inserted lines, before commit.
- No production code/data, SQLite/WAL/SHM, old outputs or unrelated temporary
  directory changed. No code tests, network collection, merge or push performed.
- Next action only after user approves the written specification: invoke
  writing-plans and create a separate Stage B implementation plan. Do not treat
  approval of the three chat sections as approval of the full written document.

## Written specification approval and implementation planning

The latest user “是” approved the written specification. This turn invoked
writing-plans and dispatching-parallel-agents for planning only. No production
code, test implementation, production database, network collection, scoring,
main merge, or push was performed. The specification's status line alone was
updated to record approval; its technical requirements remain unchanged.

Created one master plan and three subplans:

- `docs/superpowers/plans/2026-09-12-formal-policy-stage-b.md`
- `docs/superpowers/plans/2026-09-12-formal-policy-stage-b1-range-foundation.md`
- `docs/superpowers/plans/2026-09-12-formal-policy-stage-b2-financial-state-evidence.md`
- `docs/superpowers/plans/2026-09-12-formal-policy-stage-b3-window-policy-batch.md`

Eleven implementation tasks: R1–R4 range source/persistence/recovery, F1–F3
values/financial/state evidence, W1–W4 windows/evaluation/batch/integration.
R1 and F1/F2 are independent; shared source/schema/fixture ownership is explicit.
All implementation checkboxes remain unchecked.

Read-only assistants inspected source/request integration and additive storage.
Root performed the plan self-review; it was not delegated. Findings integrated:

- Existing A2 rejects bootstrap calendars as direct policy input. No spec change
  is required: keep policy calendar C; use separate bootstrap Bx, and bind M/C
  to Bx in the signed market entry. The master plan defines the exact closed
  selector/exchange bridge. `_bind_context` remains unchanged.
- Range migration is isolated V7 with four tables, not final-score/publication
  persistence. Actual verification hooks are initialize/_assert_schema_ddl,
  not an invented verify_runtime_contract method.
- Range observations/next-page factories are introduced together in R3; R2
  has no fake observation or unimplemented stub dependency.
- Runtime fixtures use explicit FY2025/FY2021–2025 periods and explicit units
  before signing. Static FY0 tests and old required-only metric gate remain.
- State flags use the actual legacy `flag_id/active` fields, not an invented
  value field. F2 consumes the real VerifiedMetricIndustryBatch type.
- Pending/proven market axes and all failure-revocation cases have named tests;
  final source-file checks remain necessary in addition to DB epochs.

Verification in progress: relative links, balanced fences, trailing whitespace,
placeholder scan and task counts passed for all four plans. Python documentation
snippets are parsed with ast only, not executed. The initial snippet parser
correctly rejected a type-signature illustration marked as Python; that fence
was changed to text, with a fresh parse still required before final handoff.

The unrelated `tmpj4zv9_fq/` and this ignored retained progress directory remain.
Next implementation uses the user's existing subagent preference after planning
handoff; this turn does not claim implementation or production readiness.

### Planning verification and document commit

- Fresh AST-only check passed for all 22 Python documentation snippets. No
  project code or code test was executed. The PowerShell-to-Python check uses
  ASCII-escaped JSON to avoid Windows stdin encoding issues.
- Four plans passed relative-link, trailing-whitespace, placeholder and balanced
  fence checks; task counts are 4 + 3 + 4 = 11. Root checked spec coverage and
  concrete cross-plan interfaces, including actual source/industry/flag APIs.
- Staged names matched exactly the four plans and specification status update;
  `git diff --cached --check` passed. Scope: 917 insertions, 1 deletion in 5 docs.
- Document-only local commit: `7cf6b59` (`docs: plan formal policy stage B evidence implementation`).
- No code/data/SQLite/WAL/SHM/progress file was included. No merge or push.
- Planning is complete; implementation tasks remain unstarted. Begin with R1
  and F1 on independent files using the user's existing parallel-subagent choice;
  use the implementation skill and task review gates before code work.
