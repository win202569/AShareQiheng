# Final Fix: DB-Backed Feature Evidence Integrity

## Baseline and finding

- Fix baseline: `c799531f8a8a2173c5557db4d1d9afaf6ebd464e`.
- A fresh whole-branch reviewer confirmed one blocking Important with a minimal isolated probe: an empty StateStore containing zero `source_snapshot` and zero `financial_fact` rows accepted a complete `general_nonfinancial` ready bundle, persisted one feature set and 363 feature values, and progress counted it as `financial_ready` with no unknown failure.
- Public `FeatureBundle` validation is context-free and should remain responsible for canonical shape/semantic metadata. Database-backed evidence existence and consistency belong at persistence and progress boundaries.

## Required behavior

1. `StateStore.put_feature_bundle()` must reject a bundle before inserting or accepting a feature-set row unless every `EvidenceRef` resolves in the same database to a canonical `financial_fact` row and that row's referenced `source_snapshot` exists.
2. For every evidence reference, compare all fields present at the public boundary to the stored canonical fact: fact ID, bundle security, source snapshot ID, source field, raw-row hash, announced timestamp, and effective timestamp. Also require stored fact content to agree with the consuming raw observed feature where the canonical raw-slot descriptor makes that relationship decidable: metric key, period, value, unit, and active mapping/formula version.
3. Derived values may cite one or more operand facts. Every cited fact and snapshot must exist and the shared evidence metadata/security must match; do not invent a formula engine or duplicate every derived formula in StateStore.
4. Validation must use set-based bounded reads of unique evidence/fact/snapshot IDs, fail closed on missing, duplicate, malformed, or mismatched rows, and execute inside the feature persistence transaction before any feature header/value insert or idempotent-success return.
5. Progress/status must revalidate evidence referential integrity for each current verified bundle before counting its declared feature status. This protects against later database deletion/corruption. An invalid bundle is excluded from ready/partial/blocked counts and contributes at most one bounded existing unknown-failure count for that candidate; never emit raw feature values or evidence details.
6. The normal production path must remain valid: source snapshots are persisted, facts are normalized/persisted, feature file and DB row agree, verified read succeeds, and progress counts the legitimate ready bundle.
7. If DB rejection occurs after the deep worker created a feature file, the existing no-orphan cleanup behavior must still remove only the newly created file; pre-existing canonical files must never be deleted.
8. Formal score readiness, seven-dimension readiness, waiting-price pool, and strong-attention pool remain closed. Do not touch network behavior, runtime data, migrations, or the three deferred Minor findings.

## Mandatory TDD regressions

Observe the correct RED before production changes:

1. Real `StateStore.put_feature_bundle` rejects a production-built ready bundle when all evidence facts/snapshots are absent; assert zero feature-set/value rows.
2. Table-driven persistence cases reject: missing fact, missing snapshot, evidence/fact field mismatch, wrong security, and raw observed fact mismatch (metric/period/value/unit/mapping as representable). Include the idempotent existing-row path so invalid evidence cannot return success merely because the feature row already exists.
3. Positive real persistence path first stores the required snapshots and canonical financial facts, then writes/persists/verified-reads the bundle and counts exactly one ready result with all four formal/pool gates closed.
4. After a valid feature row/file exists, remove or corrupt one referenced DB fact/snapshot in the isolated test database. Real progress must stop counting the bundle and increase only the bounded unknown failure count; it must not fall back to an older feature row.
5. Exercise deep-worker cleanup if the new store validation can fail after a newly created file; assert only that new orphan is removed and an existing canonical file is preserved.

## Scope and verification

- Expected production scope: `ashare_pipeline/state_store.py`, `ashare_pipeline/orchestrator.py`, and only the smallest deep-worker helper change if cleanup needs adjustment. Reuse existing `FeatureBundle`, `FinancialFact`, raw-slot descriptors, and verified-file reader; do not duplicate their contracts.
- Expected tests: focused state-store/orchestrator/deep-worker tests. Use isolated temporary roots only; never open or migrate tracked runtime data.
- Use the parent project virtual environment and a worktree-local temporary directory.
- Run focused RED/GREEN, then `tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_contract tests.test_financial_features tests.test_feature_foundation_e2e`, then full discovery and diff checks.
- Commit only intended source/tests with path-specific staging. Never stage `.superpowers/`, `data/`, `.tmp-tests/`, `.tmp-root-check/`, or temp directories.
- Append implementation and verification evidence to private `final-evidence-integrity-fix-report.md`.
