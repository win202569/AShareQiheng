# Final six-Minor cleanup brief

## Authority and fixed scope

The user explicitly authorized this cleanup after the fresh whole-branch review
at `56b0343ce1781e5138fb5de66cb1db8e1e6c5596` returned
`0 Critical / 0 Important / 6 Minor` and `Ready to merge? With fixes`.

This is exactly one consolidated TDD cleanup wave for the six findings below,
followed by one scoped re-review and controller verification. Do not broaden the
scope. In particular: no real network, no runtime/tracked DB or data, no schema
migration, no live 120/114 acceptance, no formal scores, and no stock-pool
publication.

## Binding findings and required outcomes

### 1. Whole-job lease heartbeat

Current feature jobs have no heartbeat around `_execute_feature_job`, while
statement heartbeat covers only the remote call and stops before snapshot
persistence, verification, normalization, fact insertion, issue/follow-up
recording, and final transition.

- Hold one owned heartbeat for the complete leased lifecycle of both feature and
  statement jobs, from lease acquisition through the final owned transition.
- Cover reused-snapshot and new-fetch paths.
- If lease renewal is lost, fail closed before each subsequent durable file/DB
  side effect and transition; do not let a stale worker publish or transition.
- Preserve existing source-error taxonomy, retry behavior, idempotency,
  no-clobber semantics, counters, and item reporting.
- Add deterministic focused tests that block after remote fetch during local
  persistence/normalization and during feature construction, proving renewal;
  also prove a lost heartbeat prevents later side effects/transitions.

### 2. Absolute legacy snapshot containment

`SnapshotRepository._resolve_payload_path` currently accepts any absolute path.

- Treat absolute legacy paths as legacy-compatible only when their fully
  resolved target remains under the repository's configured `data_root`.
- Reject outside-root paths, cross-drive paths, traversal, and symlink escapes.
- Retain a contained absolute-legacy positive and all canonical relative-path
  behavior.
- Add a real outside-root rejection regression and a contained positive.

### 3. Migration-plan table names

In the literal-v2 migration paragraph, replace the nonexistent table names
`snapshot` and `export_artifact` with the real v2 names `source_snapshot` and
`artifact`. This is a human-document correction and does not need an artificial
RED test; do not change migration production code or existing literal-v2 proof.

### 4. Pin the forged-unclassified negative regression to exact boundaries

Replace the broad `try/except (OSError, ValueError)` in
`test_forged_unclassified_partial_cannot_cross_real_boundaries` with explicit,
stage-specific expectations using the exact intended exception type/message for
public/file construction, persistence, verified read, and progress as
applicable. The test must not pass because an unrelated earlier stage failed.
Assert expected file/row/status cardinalities after each rejection. This is a
test-quality repair; do not weaken production validation.

### 5. No-output specialized balance semantics

Ruling: bank/insurance/broker templates currently have zero financial feature
slots and therefore no bundle-level evidence surface capable of authenticating
`balance_equation_mismatch`. For these zero-slot templates the blocker is
**not applicable at the bundle layer**. Canonical raw `financial_fact` rows and
source snapshots remain the audit authority, and the bundle remains blocked by
`specialized_financial_inputs_missing` (plus other independently applicable
blockers). Do not add a new contract/schema field in this cleanup.

- Make the builder and validators consistent: a zero-financial-slot bundle must
  not advertise `balance_equation_mismatch`, even when selected raw facts are
  imbalanced or the caller's fact blocker set contains it.
- Keep StateStore's rejection of a forged balance marker on an evidence-empty
  bundle.
- Preserve full balance recomputation/authentication for templates with
  represented financial slots.
- Add real bank, insurance, and broker regressions covering genuine imbalanced
  canonical facts through build, first insert, idempotent reuse, verified
  progress, and the exact blocked/no-balance-marker result. Prove the raw facts
  remain stored/auditable and no readiness/pool gate opens.

Cost of this ruling if wrong: specialized bundles will not surface the redundant
balance marker until specialized financial projections exist; however they stay
blocked and the canonical raw facts retain the mismatch evidence.

### 6. Process-control exception propagation

`_process_feature_jobs` catches `BaseException` and converts
`KeyboardInterrupt`/`SystemExit` into ordinary retryable failures.

- Catch `Exception` for normal feature-build errors.
- Allow `KeyboardInterrupt` and `SystemExit` to propagate reliably after
  heartbeat cleanup; do not append a normal failure item or convert them into a
  retryable job transition. The leased job may remain running for ordinary lease
  recovery.
- Add focused tests for both process-control exception classes and retain a real
  ordinary-exception retry regression.

## TDD and verification contract

Before any production edit, write real behavior regressions for production
findings 1, 2, 5, and 6 and run them against exact base `56b0343`. Capture a
genuine RED whose failures are caused by the missing behavior. Finding 4 is a
test-quality rewrite and Finding 3 is prose; do not fabricate RED for them.

Use hand-checked fixtures and real components. Mock only an unavoidable
blocking/external boundary, preserve all real side effects needed by the test,
and assert consumer-visible behavior rather than mock existence or source text.
Apply the smallest coherent production changes, then run the focused set GREEN,
all affected suites, and the complete offline suite with a short worktree-local
TEMP/TMP/TMPDIR to avoid Windows path-length noise. The base complete count is
399 tests.

## Delivery contract

- Work only in
  `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation` on
  `feature/seven-dimension-foundation`.
- Use `apply_patch` for edits and path-specific `git add`.
- Never stage `.superpowers/`, temp directories, `data/`, DBs, or unrelated
  files.
- Update tracked `progress.md` only after exact final counts are known; keep live
  smoke, 120/114, formal/seven-dimension readiness, scores, and both pools
  explicitly closed/unperformed.
- Commit the complete cleanup.
- Write the full report to
  `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/final-minor-cleanup-report.md`.
  Include base/head, root-cause verification, exact RED command/output and
  expected failures, changed files/design, focused/affected/full/staged commands
  with counts/exits, scope/status checks, commit hash, and concerns.
- Return only `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or `BLOCKED`, the
  commit hash, one-line test summary, and concerns.
- Do not spawn subagents or reviewers.
