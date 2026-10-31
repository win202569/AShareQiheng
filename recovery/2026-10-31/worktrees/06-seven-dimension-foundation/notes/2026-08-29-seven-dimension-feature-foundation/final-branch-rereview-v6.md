# Final whole-branch re-review v6

## Verdict

- Review range: `e361fbd..56b0343ce1781e5138fb5de66cb1db8e1e6c5596`
- Exact reviewed HEAD: `56b0343ce1781e5138fb5de66cb1db8e1e6c5596`
- Critical: **0**
- Important: **0**
- Minor: **6**
- **Ready to merge? With fixes**

The branch remains fail-closed: no finding can create a formal score, mark seven-dimensional readiness, populate either official pool, or falsely increase the operational three-snapshot coverage numerator. Four previously deferred Minors remain, and two additional production-relevant Minors are reproducible on the exact HEAD. The fixes are bounded, but four findings affect production behavior or containment and should be resolved before treating this foundation as finished.

## Findings

### Minor 1 — The heartbeat does not cover the whole leased job

- Exact locations: `ashare_pipeline/deep_worker.py:1588` (heartbeat scope begins and covers only the remote call), `ashare_pipeline/deep_worker.py:1712` (snapshot persistence, verification, normalization, fact insertion, issue recording, follow-up, and final transition occur after it), and `ashare_pipeline/deep_worker.py:1359` (feature-build execution has no heartbeat at all).
- Why it matters: a slow local snapshot write/verification/normalization or feature build can outlive the lease. Another worker may then recover and claim the job while the first worker is still making idempotent but real file/DB side effects. Ownership checks prevent a stale final transition and therefore keep correctness fail-closed, but the system can duplicate expensive work, emit avoidable terminal/lease-loss noise, and make operational progress less stable.
- Remediation: hold one heartbeat from lease acquisition through the final owned transition for both statement and feature jobs; check `lost` immediately before every durable side effect and transition; add focused tests that block after fetch during persistence/normalization and during feature construction.

### Minor 2 — Legacy absolute snapshot paths bypass data-root containment

- Exact location: `ashare_pipeline/snapshot_repository.py:146-147`.
- Why it matters: new relative paths are contained and traversal/symlink escapes are rejected, but any absolute legacy path is resolved and accepted without requiring it to remain under the configured project/data root. Payload hash and metadata checks limit substitution, yet a legacy/corrupt DB row can still direct the process to read an arbitrary filesystem location. This is a real containment gap even though integrity validation remains fail-closed.
- Remediation: require resolved absolute legacy paths to be under an explicitly approved legacy root (preferably the current data root), or migrate legacy absolute paths to canonical project-relative paths before enforcing containment. Add an outside-root absolute-path rejection regression while retaining a contained-legacy positive case.

### Minor 3 — The implementation plan names two v2 tables incorrectly

- Exact location: `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md:476`.
- Why it matters: the migration instruction names `snapshot` and `export_artifact`, while the literal v2 schema and regression use `source_snapshot` and `artifact`. The implementation and tests are correct, so this is documentation-only, but following the plan literally would seed/query nonexistent tables and obscure the intended data-retention proof.
- Remediation: replace `snapshot` with `source_snapshot` and `export_artifact` with `artifact` in that paragraph.

### Minor 4 — The unclassified negative regression can pass for the wrong rejection

- Exact locations: `tests/test_orchestrator.py:1770-1779`, especially the shared `except (OSError, ValueError)` at line 1779.
- Why it matters: one broad `try` covers file writing, DB persistence, and verified reading. The test passes if any stage raises either broad exception type, including an unrelated failure, so it does not prove which intended unclassified trust boundary rejected the forged `partial` bundle.
- Remediation: split the test into explicit `assertRaisesRegex` checks at the public/file, persistence, and read/progress boundaries, and assert the expected file/row cardinality after each rejection.

### Minor 5 — A genuine balance mismatch cannot be persisted for no-output specialized templates

- Exact locations: `ashare_pipeline/industry_templates.py:31-33` (bank/insurance/broker have zero financial slots), `ashare_pipeline/financial_features.py:787` (the builder recomputes balance semantics from all selected facts), and `ashare_pipeline/state_store.py:836-840` (persistence rejects `balance_equation_mismatch` whenever the bundle has no evidence).
- Reproduction on exact HEAD: an isolated temporary StateStore was populated through the real fixture helper with a bank candidate and a genuine 2021 balance mismatch. The real builder produced `template='bank'`, zero feature values, `financial_status='blocked'`, and blockers `('balance_equation_mismatch', 'formal_industry_mapping_missing', 'specialized_financial_inputs_missing')`; `put_feature_bundle()` then raised `ValueError: balance equation semantics do not match canonical facts` at line 838.
- Why it matters: legitimate bank/insurance/broker inputs with a balance mismatch terminal-fail feature construction instead of retaining the intended auditable blocked bundle. This stays Minor because it fails closed, the candidate is already specialized-blocked, and statement-snapshot coverage plus all formal/pool gates remain unaffected; nevertheless, it loses a core audit artifact and makes the builder/persistence balance authority inconsistent for real candidate sectors.
- Remediation: bind zero-output specialized bundles to the exact selected snapshot/fact set (for example with explicit authenticated balance-evidence metadata) and recompute from those canonical facts at first insert, idempotent insert, and progress. If the approved contract intentionally excludes balance semantics for zero-slot templates, suppress that blocker consistently in the builder and validators instead. Add bank, insurance, and broker regressions for first insert, idempotent insert, and progress.

### Minor 6 — Feature processing swallows process-control exceptions

- Exact locations: `ashare_pipeline/deep_worker.py:1368-1399`.
- Reproduction on exact HEAD: with one temporary `feature_build` job and `_execute_feature_job` patched to raise `KeyboardInterrupt`, `_process_feature_jobs()` returned normally with `0`, changed the job to `retryable_failed`, and recorded `feature_build_error`; the interrupt did not propagate.
- Why it matters: catching `BaseException` also catches `KeyboardInterrupt` and `SystemExit`. An operator interrupt or orderly process exit during a feature build can therefore be converted into an ordinary retry and the worker can continue processing, making shutdown unreliable. This does not corrupt accepted output, so severity is Minor.
- Remediation: catch `Exception` for normal feature failures. If a best-effort job transition is required for `KeyboardInterrupt`/`SystemExit`, perform it in a separate clause and then unconditionally re-raise. Add a focused interrupt-propagation regression.

## Whole-spec verification

### Contract, identity, visibility, and templates

- The immutable public contract is exactly seven dimensions `G/V/M/EQ/FS/CA/T` (`ashare_pipeline/feature_contract.py:15-16`); frozen value/evidence/bundle types, canonical sorting/serialization, finite-value rules, zero-versus-missing semantics, exact dimension keys, `formal_confidence is None`, and `is_formal_score_ready is False` are enforced by `FeatureBundle.validate()` (`ashare_pipeline/feature_contract.py:408-548`).
- Candidate membership and industry/performance evidence are defensively frozen, and `candidate_set_hash` is a canonical hash over the approved prefilter dependencies plus selected per-security performance records (`ashare_pipeline/deep_worker.py:92-129`, `186-239`). Feature input identity binds security, period, as-of, candidate hash, exact three statement snapshot hashes, calendar hash, mapping/template/contract versions (`ashare_pipeline/financial_features.py:468-493`); feature-job payload validation additionally binds frozen snapshot IDs, hashes, source/dataset/request identity, and current candidate context (`ashare_pipeline/deep_worker.py:928-1047`, `1210-1263`).
- Point-in-time rules use a verified, complete BaoStock calendar with no weekday fallback (`ashare_pipeline/financial_features.py:125-178`), derive date-only evidence at the next real A-share session at 15:00 Shanghai (`ashare_pipeline/financial_features.py:263-342`), select facts only when `effective_at_utc <= as_of_utc` (`ashare_pipeline/financial_features.py:404-426`), and reject future evidence again at public parse (`ashare_pipeline/feature_contract.py:475-482`) and DB-backed validation.
- There is no implicit template fallback. `unclassified` is forced to blocked/zero coverage with the exact blocker, while every specialized template is forced blocked by `specialized_financial_inputs_missing`; non-specialized common templates alone can become `financial_ready` on complete canonical inputs (`ashare_pipeline/feature_contract.py:487-510`, `ashare_pipeline/financial_features.py:772-814`). Finding 5 is the bounded no-output balance/persistence exception to otherwise-correct specialized behavior.

### Raw facts, derived catalog, and authentication

- `FinancialFact` and schema-v3 `financial_fact` carry the required security, statement, metric, period, value/unit/nature, announced/effective/source-updated instants, snapshot, source field, raw-row hash, mapping version, and created-at fields (`ashare_pipeline/financial_schema.py:232-379`, `ashare_pipeline/state_store.py:152-173`). Fact identity is canonical over semantic/evidence fields and excludes only `id`/`created_at`; revisions therefore retain distinct identities.
- A fresh read-only import probe on exact HEAD returned `count=90`, `unique_logical_ids=90`, `version='financial-derived-v1'`, dimensions `CA/EQ/FS/G/M`. The neutral catalog is closed in `ashare_pipeline/financial_formulas.py:156-159`; public parsing and StateStore authenticate exact result identities, statuses, units, versions, values, missing reasons, and sorted operand fact IDs (`ashare_pipeline/feature_contract.py:248-285`, `515-544`; `ashare_pipeline/state_store.py:965-1002`).
- Financial namespace recognition is global across all seven containers, so copied/retagged registered raw or derived values in `V` or `T` cannot evade the catalog check (`ashare_pipeline/feature_contract.py:248-285`; negative coverage in `tests/test_feature_contract.py:428-438` and `505-514`).
- Balance-equation tolerance and unit checks share `balance_equation_blockers()` (`ashare_pipeline/financial_schema.py:382-412`) across builder (`ashare_pipeline/financial_features.py:787`), first/idempotent persistence (`ashare_pipeline/state_store.py:943-963`, `1004-1032`), and progress revalidation (`ashare_pipeline/orchestrator.py:1080-1084`). Finding 5 identifies the one zero-evidence specialized edge where those consumers do not share the same fact set.

### Artifact/DB mirror, evidence, and progress trust boundary

- `put_feature_bundle()` validates the artifact hash/path and writes the `feature_set` header plus every `feature_value` atomically in one immediate transaction (`ashare_pipeline/state_store.py:1004-1073`). Existing idempotent rows are accepted only after DB-backed evidence/formula/balance revalidation and exact stored header/child comparison.
- Progress opens one read transaction before selecting feature rows and keeps artifact verification, exact `feature_set`/`feature_value` mirror comparison, evidence/fact/snapshot resolution, formula/balance recomputation, and current CandidateContext industry/template binding inside it (`ashare_pipeline/orchestrator.py:1053-1096`). Canonical fact and snapshot existence plus evidence identity are checked in `ashare_pipeline/state_store.py:828-888`.
- The outer SQL applies `as_of_utc <= now_utc` before newest-per-security selection (`ashare_pipeline/orchestrator.py:1055-1067`). `seen_feature_securities` is set before verification (`1068-1073`), so an invalid newest visible artifact becomes a bounded unknown and cannot fall back to an older apparently-good row. Exact ties are deterministic by `as_of_utc`, `created_at`, then `id`.

### Persistence, execution, offline behavior, reporting, and closed gates

- Schema v3 is additive (`ashare_pipeline/state_store.py:39`, `146-219`, `456`); literal-v2 migration tests seed and compare all seven real v2 tables row-for-row, preserve score immutability, reject partial/corrupt schemas, and verify idempotent migration (`tests/test_state_store.py:216-405`). Finding 3 is only the plan wording.
- Snapshot/feature publication is canonical and no-clobber, old revisions/files remain retained, and identical independent replay is byte-stable (`ashare_pipeline/snapshot_store.py:35-67`, `ashare_pipeline/deep_worker.py:686-805`, `tests/test_feature_foundation_e2e.py:219-245`). No fallback behavior and tamper/missing-child/snapshot-loss cases are covered by focused progress regressions.
- Lease ownership, expiry recovery, atomic parent/follow-up transitions, bounded execution, source taxonomy, and current-context job identity are implemented and tested. Findings 1 and 6 are the remaining operational lease/shutdown limitations.
- Offline paths do not construct or call sources (`tests/test_deep_worker.py:1319-1337`, `tests/test_orchestrator.py:779-806`, `2089-2104`, `2448-2460`). This review performed no network call and touched no tracked/runtime database or data.
- Reporting exposes bounded aggregate counts only—coverage, statement jobs/snapshots, feature-set totals, incomplete count, lease/failure totals—and omits security IDs and individual financial values (`ashare_pipeline/reporting.py:397-450`; `tests/test_reporting.py:491-549`).
- `formal_score_ready`, `seven_dimension_ready`, and both official pool counts remain hard-closed in status (`ashare_pipeline/orchestrator.py:1178-1180`). Feature bundles prohibit formal readiness and contain no score/pool payload. Nothing in this branch authorizes operational acceptance to open those gates.

## Operational acceptance remains separate and unperformed

The live bounded network smoke was **not run**. The production acceptance requiring the exact current-context denominator **120** and at least **114** candidates with all three verified target-period snapshots was also **not run or accepted**. `build_deep_progress()` computes a generic denominator from the actual current CandidateContext and a numerator only after exact request lookup, hash/metadata verification, and target-period presence for all three datasets (`ashare_pipeline/orchestrator.py:967-1015`, `1109-1123`); it does not silently substitute the old tracked 120-candidate state for the missing v3 operational proof. Tracked `progress.md:88-89` and the private final repair report explicitly preserve this separation and keep formal/seven-dimension gates and both pools closed.

## Verification evidence used

- The frozen review package was consumed once, together with the authoritative design, implementation plan, tracked progress, and relevant private repair/review ledgers.
- Controller-provided exact-HEAD evidence reports **399/399 offline tests passed**. Per review instructions, the full suite was not rerun.
- Fresh read-only checks in this review:
  - `git rev-parse HEAD` returned the required exact hash.
  - `git diff --check e361fbd..56b0343ce1781e5138fb5de66cb1db8e1e6c5596` exited 0 with no output.
  - The formula-catalog probe returned exactly 90 unique `financial-derived-v1` logical IDs.
  - Two isolated temporary-DB probes reproduced Findings 5 and 6; neither used network or repository runtime/tracked data.

