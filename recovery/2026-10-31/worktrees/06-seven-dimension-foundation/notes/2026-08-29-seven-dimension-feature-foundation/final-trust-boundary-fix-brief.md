# Final trust-boundary fix brief

## Authority and scope

The user explicitly authorized this repair after the fresh whole-branch review at
`e8c7ed8fdca882275c53fe9af9332629403e1060` reported `0 Critical / 3 Important /
4 Minor` and `DO NOT INTEGRATE`.

This is one consolidated, tightly scoped TDD fix wave for exactly the three
confirmed Important findings below. Do not fix the four deferred Minors. Do not
use the network, open or migrate a runtime/tracked database, alter tracked data,
run operational 120/114 acceptance, publish formal scores, or open either stock
pool.

## Binding findings

1. **Current candidate context is not authenticated at progress.**
   `build_deep_progress` selects and verifies bundles by candidate hash, member,
   contract, period, artifact, DB mirror, and evidence, but does not bind the
   bundle's source industry name/template to
   `context.industries[security_id]`. A currently `unclassified` candidate can
   therefore be represented by a self-consistent `general_nonfinancial` bundle
   and counted ready. Relevant flow:
   `ashare_pipeline/deep_worker.py:1217-1225,1298-1311`,
   `ashare_pipeline/feature_contract.py:301-318`, and
   `ashare_pipeline/orchestrator.py:1052-1087` at the reviewed HEAD.

2. **Balance-equation readiness is trusted rather than recomputed at the DB
   trust boundary.** The builder computes the balance-sheet identity in
   `ashare_pipeline/financial_features.py:403-422`, but
   `build_feature_bundle` accepts caller-supplied fact blockers, public bundle
   validation trusts the declared blockers/status, and StateStore authenticates
   individual facts/formulas without independently recomputing the cross-fact
   equation. Canonical raw facts with assets != liabilities + equity can omit
   `balance_equation_mismatch`, be relabelled ready, persist, reread, and count
   ready. Relevant flow:
   `financial_features.py:403-422,482,788-800`,
   `feature_contract.py:490-501,624-647`,
   `state_store.py:803-974`, and `orchestrator.py:1054-1087`.

3. **Future-as-of bundles can enter earlier progress.** The progress query has
   no `feature_value.as_of_utc <= now_utc` visibility predicate and marks the
   newest row for a security as seen before validating/counting it. A valid
   bundle dated `2026-09-10` can count in status evaluated at
   `2026-08-29`, or suppress an older visible valid bundle. Relevant flow:
   `feature_contract.py:475-482` and `orchestrator.py:888-902,1054-1065`.

## Required behavior

### A. Candidate-context binding

- At every progress/status path, authenticate the verified bundle's exact
  industry source name and template identity against the current frozen
  `CandidateContext` entry for that security before it can count ready.
- A mismatch must fail closed and must not fall back to a different/newer or
  older mismatched bundle as though it were current.
- Preserve valid `unclassified`, common-template, bank, insurance, securities,
  and real-estate behavior.
- Keep the normal producer binding, public bundle self-validation, DB/file
  authentication, and progress binding as defense-in-depth; do not weaken any
  existing authority.

### B. Shared balance-equation authority

- Define one shared production authority for the balance equation and its
  tolerance/applicability semantics; the financial fact selector/builder and
  StateStore trust-boundary validation must consume the same authority rather
  than duplicate mutable logic.
- StateStore must recompute the invariant from the exact authenticated canonical
  raw facts used by the bundle before first insert and before idempotent existing
  row success. A forged omission/addition of `balance_equation_mismatch`, or a
  forged ready/partial/blocked status inconsistent with that recomputation, must
  be rejected.
- Progress must reuse the authenticated DB result so later fact corruption/loss
  or semantic mismatch cannot count ready. Preserve legitimate missing-input,
  equality-within-tolerance, no-output-template, and genuinely balanced cases.
- Do not merely check whether a marker string is present; authenticate the
  semantic relationship between facts, blockers, coverage/status, and the
  verified artifact.

### C. Outer status-time visibility

- Progress evaluated at `now_utc` may consider only feature-set/value rows whose
  canonical `as_of_utc <= now_utc`.
- Apply the cutoff before newest-per-security selection, so a future row neither
  counts nor suppresses the newest visible row.
- Equality at the cutoff remains visible. Preserve deterministic newest-only and
  no-fallback behavior among visible rows.

## Mandatory TDD proof

Before any production edit, add minimal real production-path regressions and run
them against `e8c7ed8`. Record a genuine RED with the expected assertion failures
for all three findings. Tests must use hand-checked fixtures and real StateStore /
artifact / progress paths, not source-text assertions or mocks of the behavior
under test.

At minimum cover:

1. Current-context `unclassified` versus persisted authenticated
   `general_nonfinancial` substitution; include a valid matching-context
   positive.
2. Canonical imbalanced assets/liabilities/equity with the mismatch blocker
   omitted and status relabelled ready through first persistence, idempotent
   reuse, reread, and progress; include balanced/equality and legitimate missing
   facts as positives where appropriate.
3. Status at `2026-08-29` with only a `2026-09-10` bundle, and with both a valid
   visible older bundle and a future bundle, proving the future row does not
   count or suppress the older visible row; include exact-cutoff equality.

Then implement the smallest coherent fix, run the focused RED set GREEN, run all
affected suites, and run the complete offline suite with a new worktree-local
TEMP/TMP/TMPDIR. The complete suite baseline is 391 tests. No real network or
runtime/tracked data access is permitted.

## Delivery contract

- Use `apply_patch` for edits.
- Path-specific `git add`; never stage `.superpowers/`, controller temp
  directories, runtime data, or unrelated files.
- Update tracked `progress.md` only after the final test counts are known, keeping
  live network, exact 120/114, formal scoring, seven-dimension formal readiness,
  and both pools explicitly closed/unperformed.
- Commit the complete fix wave on `feature/seven-dimension-foundation`.
- Write the full implementation report to
  `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/final-trust-boundary-fix-report.md`.
  It must include: pre-edit HEAD, exact RED command/output and why each failure
  was expected, changed files/design, focused/affected/full commands with counts
  and exits, staged-tree verification, commit hash, and any concerns.
- Return only status (`DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or
  `BLOCKED`), commit hash, one-line test summary, and concerns.
- Do not spawn subagents or reviewers.
