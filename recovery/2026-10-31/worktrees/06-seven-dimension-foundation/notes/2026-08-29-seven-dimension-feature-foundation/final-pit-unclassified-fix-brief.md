# Final over-cap targeted remediation brief

Baseline: `dd1e3322dfa73c7c53ca7c0944544c895b781789`

This is one user-authorized, tightly bounded remediation task after the fresh whole-branch review. Read this file first; it is the requirements authority for this task. Do not read or reinterpret the whole implementation plan.

## Objective

Close exactly two independently reproduced trust-boundary findings and update the tracked public progress record:

1. Point-in-time cutoff: no `EvidenceRef` in any bundle may have an effective instant later than that bundle's `as_of_utc`. Because DB-backed validation already binds each evidence reference to a canonical `financial_fact` with equal fields, this also prevents future-effective canonical facts from crossing persistence, idempotent, read, or progress boundaries.
2. Unclassified template semantics: a bundle whose `template_id` is `unclassified` must remain `financial_status=blocked`, must contain blocker `industry_template_unclassified`, and must have `financial_coverage=0` because its applicable financial-slot denominator is zero. It may never be relabelled `partial` or have the hard blocker removed.
3. Bring tracked repository-root `progress.md` forward through the final repair waves without claiming unperformed operational acceptance or formal scoring/pool readiness.

Do not address the deferred heartbeat, legacy absolute-path containment, or plan-table-name Minors in this task.

## Mandatory TDD sequence

First reproduce both reviewer paths with public-contract tests and real storage/progress tests. Run the focused tests and record the genuine RED command, exit code, and exact expected failures in the report before changing production code. Then make the smallest production change that turns those tests GREEN.

### Public contract regressions

Add focused tests through the public parse/validation path. They must prove:

- An observed or derived evidence item with `effective_at_utc > bundle.as_of_utc` is rejected. Exercise evidence outside a single raw-slot happy path so the invariant demonstrably covers every dimension/value/evidence in both ready and non-ready statuses.
- Compare parsed timezone-aware instants, not ISO strings. Exact equality (`effective_at_utc == as_of_utc`) is accepted; earlier evidence remains accepted.
- A forged `unclassified` bundle marked `partial` is rejected even if other fields are structurally valid.
- An `unclassified` bundle marked `blocked` but missing `industry_template_unclassified` is rejected.
- An `unclassified` bundle with non-zero financial coverage is rejected.
- A valid `unclassified` bundle with blocked status, the exact blocker, and zero coverage is accepted.

Use adversarial public serialized inputs where appropriate so the tests exercise the same parser boundary as untrusted files. Preserve canonical hash rules in test fixtures; a failure caused only by a deliberately stale content hash is not sufficient.

### Real persistence/read/progress regressions

Use isolated temporary StateStore/data roots and real production persistence/read/progress code; do not use the runtime DB or tracked data. Prove:

- A structurally valid bundle backed by canonical referenced facts whose effective instants are later than bundle `as_of_utc` cannot be persisted, including the existing/idempotent success path. It cannot be read or counted as ready/partial through progress.
- If the newest/current bundle artifact is invalid for this PIT rule, progress does not silently fall back to an older valid bundle and accounts for the current member as bounded unknown/corrupt according to the existing contract.
- A canonical fact/evidence instant exactly equal to `as_of_utc` (and an earlier instant where useful) persists, reads, and counts normally.
- A forged `unclassified -> partial` bundle with its hard blocker removed cannot cross write/persist/read/progress boundaries.
- A valid builder-produced unclassified bundle persists, reads back, and is counted as blocked, not partial or ready.

The tests must use canonical source snapshots and financial facts where the positive path requires them. Do not weaken the existing DB evidence existence/equality validator.

## Implementation boundaries

Expected production scope is primarily `ashare_pipeline/feature_contract.py`. A defense-in-depth StateStore check is allowed only if the contract-level invariant cannot fully protect a real DB path or if it materially improves fail-closed behavior without duplicating inconsistent policy. Keep a single clear authority for each semantic rule.

Likely test scope:

- `tests/test_feature_contract.py`
- `tests/test_state_store.py`
- `tests/test_orchestrator.py`
- only directly necessary adjacent test helpers

Do not modify source adapters, network behavior, runtime data, formal scoring, pool publication, or unrelated deferred Minors. Do not open or migrate any tracked/runtime database. Do not use the network.

## Public progress record

After the implementation and fresh full suite pass, update tracked repository-root `progress.md` with a concise, temporally accurate seven-dimension-foundation entry that records the subsequent trust-boundary repair waves and current full-suite evidence. It must state plainly that:

- the PIT cutoff and unclassified blocked invariants are now enforced in code and covered by isolated tests;
- DB-backed evidence existence/consistency remains enforced;
- independent scoped and fresh whole-branch review are still required gates unless their outcome is already known at the moment of the edit;
- real bounded network smoke and exact operational denominator/numerator `120/114` have not been performed;
- `formal_score_ready=false`, formal scores are not published, and both stock pools remain closed/empty.

Use wording that remains truthful after later review; do not predict approval.

## Verification

At minimum, after GREEN run with `D:\Projects\AShareQiheng\.venv\Scripts\python.exe` and a worktree-local TEMP/TMP/TMPDIR:

1. Focused new tests.
2. `tests.test_feature_contract tests.test_financial_features tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e`
3. Full `python -m unittest discover -s tests`.
4. A fresh staged-tree full discovery after path-specific staging.
5. `git diff --check`, staged-stat/diff inspection, and verification that no private `.superpowers`, temp files, runtime DB/data, or unrelated files are staged.

Use path-specific `git add`. Preserve the pre-existing controller-owned `.tmp-tests/` and inaccessible `.tmp-root-check/` noise; do not stage, edit, or delete it.

## Deliverables

- Production/tests/public progress changes committed on the current feature branch.
- Private report: `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/final-pit-unclassified-fix-report.md`.
- The report must include: independent reproduction, RED command/output/exit, implementation rationale, changed files, GREEN commands with exact counts/results, staged-tree verification, commit hash, and concerns.
- Return only: `DONE` or `DONE_WITH_CONCERNS`, commit hash, one-line test summary, and concerns.

You must not spawn subagents or reviewers. The controller owns all independent review.
