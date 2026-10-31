# Final operational-boundary audit

## Scope and method

- Frozen branch: `e361fbd1e2f019dfe47c82c32880c7a44084e3a9..56b0343ce1781e5138fb5de66cb1db8e1e6c5596`.
- Review package: `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/review-e361fbd..56b0343.diff` (SHA-256 `8D453F7B0CCAA92F934680DAC6667E88C1108633E1FFAB297D69D356720F4C7E`).
- Read-only audit of the frozen diff, design, implementation plan, public/private progress ledgers, current production code, and relevant tests. No source, tracked data, database, or migration was edited or executed. This report is the only intended file write.
- No broad suite or network command was run. One worktree-local, `python -B`, hermetic probe exercised the concrete no-output-template/balance-mismatch doubt and cleaned up its temporary harness.
- Pre-existing untracked controller/test directories and the inaccessible `.tmp-root-check` entry were not touched and are outside the frozen commit.

## Verdict

| Severity | Count | Integrability effect |
|---|---:|---|
| Critical | 0 | None |
| Important | 0 | None |
| Minor | 5 | Non-blocking; four are the known deferred items and one is a newly confirmed fail-closed specialized-template edge case |

**Code/test integration verdict: integrable with five non-blocking Minors.**

**Production operational acceptance verdict: not yet established.** The live bounded-network smoke and exact deployed `120/114` denominator/numerator acceptance remain intentionally unperformed and must not be inferred from code integration readiness.

## Minor findings

### Minor 1 — Lease heartbeat still does not cover the whole leased execution

- Locations: feature jobs have no heartbeat around execution at `ashare_pipeline/deep_worker.py:1337-1401`; statement heartbeat covers only the remote call at `ashare_pipeline/deep_worker.py:1577-1601`, while snapshot persistence/normalization and final transition occur later at `ashare_pipeline/deep_worker.py:1712-1804`.
- Impact: a long post-fetch or feature-build phase can outlive its lease and duplicate content-addressed/idempotent side effects before the owner-checked final transition fails. No silent overwrite or release-gate opening follows because feature/snapshot publication is no-clobber and job terminal transitions require the current unexpired owner.
- Retriage: **still Minor; not Important**.

### Minor 2 — Legacy absolute snapshot paths remain outside data-root containment

- Location: `ashare_pipeline/snapshot_repository.py:142-147` returns any absolute legacy payload path after resolution, without requiring it to be below `data_root`.
- Impact: a legacy/corrupt DB row can direct verified snapshot reading outside the project data directory, although canonical payload-hash and metadata verification remain mandatory and all new writes use contained relative paths.
- Retriage: **still Minor; not Important**.

### Minor 3 — The implementation plan still names two v2 tables incorrectly

- Location: `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md:476` says `snapshot` and `export_artifact`; production uses `source_snapshot` and `artifact` at `ashare_pipeline/state_store.py:107-119`, and the literal migration regression uses the production names at `tests/test_state_store.py:330-409`.
- Impact: documentation-only execution hazard; production migration DDL and row-for-row preservation coverage are correct.
- Retriage: **still Minor; not Important**.

### Minor 4 — One unclassified negative integration test catches too broad a boundary

- Location: `tests/test_orchestrator.py:1750-1780`, especially the `except (OSError, ValueError)` spanning write, persistence, and reread at lines 1770-1780.
- Impact: an unrelated earlier exception can satisfy that single real-boundary negative. Pinpoint public-contract tests, the genuine RED history, shared production validation, and the adjacent positive builder round-trip at `tests/test_orchestrator.py:1801-1810` independently anchor the behavior.
- Retriage: **still Minor; not Important**.

### Minor 5 — A genuine balance mismatch on a no-output template cannot be persisted as the newest blocked bundle

- Locations: the builder adds the balance blocker for every selected fact set at `ashare_pipeline/financial_features.py:775-794`; bank/insurance/broker have no financial slots at `ashare_pipeline/industry_templates.py:30-33`; StateStore rejects a balance marker when the bundle has no evidence at `ashare_pipeline/state_store.py:828-841`; feature execution records the resulting build failure at `ashare_pipeline/deep_worker.py:1368-1399`.
- Focused reproduction: a one-candidate bank replay with a canonical imbalanced 2026H1 balance triplet produced two terminal `feature_build_error` jobs after an earlier intermediate blocked bundle had been stored. The newest stored bundle remained blocked for specialized/missing-input reasons but did not carry the later `balance_equation_mismatch` marker.
- Impact: final rebuild/progress can retain an older already-blocked bundle instead of persisting the newest, more specific blocked state. It cannot promote a no-output template to ready, affect exact three-statement coverage, set either formal readiness flag, or open a pool.
- Classification: **Minor**. Minimum repair is to make balance semantics representable/authenticatable for no-output templates (or explicitly omit the redundant bundle blocker while retaining the canonical quality issue), plus a bank/insurance/broker mismatch rebuild/progress regression.

## Operational and trust-boundary results

### Current CandidateContext versus verified bundle — sound

- Candidate documents authenticate `records_hash`, current membership, performance hashes, industries, and candidate hash at `ashare_pipeline/deep_worker.py:140-242,267-273`.
- Progress scopes by current `candidate_set_hash`, contract, and period, then verifies the canonical feature artifact, exact DB header/complete child mirror, and canonical evidence before comparing the exact current industry name and resolved template at `ashare_pipeline/orchestrator.py:1053-1095`.
- A mismatching newest visible row is marked seen before validation, contributes exactly one bounded unknown, and cannot fall back to an older row (`ashare_pipeline/orchestrator.py:1068-1095`).

### Balance-equation semantic authentication — sound for represented financial bundles

- One authority defines complete-triplet applicability, common-unit handling, strict `>` comparison, and `max(1000, 0.1% * |assets|)` tolerance at `ashare_pipeline/financial_schema.py:382-410`.
- The builder consumes it at `ashare_pipeline/financial_features.py:780-794`.
- StateStore reconstructs authenticated observed raw facts and checks the marker in both directions plus blocked status at `ashare_pipeline/state_store.py:878-963`.
- That validator executes inside the immediate transaction before both first insert and existing-row/idempotent success at `ashare_pipeline/state_store.py:1017-1035`; progress calls the same validator in its read transaction at `ashare_pipeline/orchestrator.py:1055-1083`.
- Exact file/header/all-child mirror authentication also runs on first insert, idempotent reuse, and progress at `ashare_pipeline/state_store.py:1029-1070,1309-1337` and `ashare_pipeline/orchestrator.py:1073-1083`.
- The no-output-template representability edge is Minor 5; it fails closed and does not invalidate these readiness protections.

### Point-in-time newest selection, no fallback, and unknown accounting — sound

- Bundle timestamps are normalized to UTC at `ashare_pipeline/feature_contract.py:76-85,465`.
- SQL applies `as_of_utc <= now_utc` before ordering and per-security newest selection at `ashare_pipeline/orchestrator.py:1055-1067`; future rows therefore neither count nor enter the seen set, and exact-cutoff equality remains visible.
- For a visible newest invalid persisted row, the security enters the seen set before verification and contributes one unknown without fallback at `ashare_pipeline/orchestrator.py:1068-1095`.
- Future-only and future-suppressor/equality regressions are at `tests/test_orchestrator.py:1429-1503`; current-context and balance no-fallback regressions are at `tests/test_orchestrator.py:1323-1427`.

### Formal readiness and official pools — closed

- Every status payload hard-codes `formal_score_ready=false`, `seven_dimension_ready=false`, and both official pool counts to zero at `ashare_pipeline/orchestrator.py:1178-1180`.
- `FeatureBundle` rejects any formal-score-ready value at `ashare_pipeline/feature_contract.py:468-472`.
- The end-to-end replay independently asserts both flags and both zero pools at `tests/test_feature_foundation_e2e.py:265-298`.

### Exact 120/114 and live-network separation — correctly separate, still outstanding

- Runtime progress remains generic with denominator `len(context.members)` at `ashare_pipeline/orchestrator.py:1109-1123`; the implementation plan deliberately applies exact `120` and numerator `>=114` only in the later deployment acceptance script at `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md:2558-2640`.
- Offline deep execution processes frozen feature work and returns before any statement source is required at `ashare_pipeline/deep_worker.py:1491-1523`. Default AKShare/BaoStock construction is guarded by `online` at `ashare_pipeline/orchestrator.py:139-175`, and online statement attempts are bounded to `1..360` at `ashare_pipeline/deep_worker.py:1525-1534,1868-1879`.
- Public `progress.md:84-89` accurately states that live smoke and exact `120/114` were not performed and keeps the formal/seven-dimension/pool gates closed.

### Data/migration safety, determinism, and report redaction — sound

- The frozen diff changes no tracked `data/`, DB, SQLite, or migration artifact. Migration remains one additive transaction with rollback and exact v2/v3 schema checks at `ashare_pipeline/state_store.py:297-354,437-458`; literal-v2 row preservation, idempotency, corrupt-schema rejection, ledger-gap rejection, and rollback tests are at `tests/test_state_store.py:330-546`.
- Canonical file publication is contained, hash-verified, fsynced, and no-clobber at `ashare_pipeline/deep_worker.py:686-808`; feature header/children are atomically materialized and then compared exactly at `ashare_pipeline/state_store.py:1017-1071,1254-1337`.
- Independent fresh harnesses prove byte-identical rebuilds and traceability at `tests/test_feature_foundation_e2e.py:218-298`; offline frozen rebuilding proves zero remote attempts at `tests/test_feature_foundation_e2e.py:300-327`.
- State progress omits raw payloads at `ashare_pipeline/state_store.py:1203-1233` with regression `tests/test_state_store.py:2089-2102`. Reader-facing reporting exposes only aggregate deep counts at `ashare_pipeline/reporting.py:397-451`, recursively redacts secrets/local paths at `ashare_pipeline/reporting.py:23-102`, and has adversarial redaction and no-individual-value coverage at `tests/test_reporting.py:310-350,498-543`.

## Final assessment

**Critical: 0. Important: 0. Minor: 5.**

The three final trust-boundary repairs and all formal/pool gates are sound. None of the four known deferred Minors rises to Important. The branch is code/test-integrable with the five documented non-blocking Minors, but it is not yet production-operationally accepted until the separate live bounded-network and exact `120/114` checks pass without touching unreviewed runtime data.
