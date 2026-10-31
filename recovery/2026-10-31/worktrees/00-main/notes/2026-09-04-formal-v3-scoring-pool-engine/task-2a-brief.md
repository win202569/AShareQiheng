# Task 2A — Repository-authenticated metric feature projection

Read this first: requirements for the first integration slice of approved Task 2 (Metric Eligibility, Peer Cohorts, and Percentile Scores). Parent owns industry/universe/pure-rank integration in following slices. Base commit fb6deda06ee4e9759cab60e35e6253de1c281bc1.

## Approved Task 2 rule
metric_peer_eligible is metric-level: frozen A-share universe, valid template and frozen industries, all verified visible required facts for that metric, valid denominator/unit; it does not depend on all-seven-dimensional completion, veto flags or pool/score rows. No zero/median/imputation/reweighting. No live requests or legacy scorer imports.

## Why this integration is necessary
Existing FormalFeatureRepository rejects any full bundle blocker, and build_formal_feature_bundle deliberately suppresses all values on global history/input blockers. Merely skipping the repository completeness check is insufficient and unsafe. Do not modify old V6 bundle bytes/hashes, global mature-history behavior, or old strict public reads.

## Required output/API
Add FormalFeatureRepository.select_current_verified_metric_features(security_id, as_of_utc, *, template_id, registry_manifest_hash, required_feature_keys: tuple[str,...]) -> VerifiedMetricFeatureProjection | None.
- Exact frozen cutoff: 2026-08-31T07:00:00+00:00 for this new endpoint, canonical security SH/SZ/BJ and five templates.
- Selected keys exact nonempty sorted unique tuple, each resolves to an applicable required signed V6 slot in the same template. The scoring MetricDefinition-to-key binding is the later metric factory's job; this endpoint authenticates a selected signed feature projection, not a final score.
- Only exact existing stores/repository provenance. Use injected complete current input provider; never default missing issues to empty, never accept a caller bundle or raw numeric override.
- Capture complete provider facts/issues once as detached finite tuples and check identity/batch/complete, compare the full fact snapshot to actual reverified StateStore facts. Preserve all existing current-selector race checks and add end-of-operation provider/dependency checks as needed; source or receipt/SQL mutation during projection rejects.
- Build the unchanged expected V6 full bundle from the full captured inputs. Read the already persisted receipt at its exact input_hash with full SQL/file/header/signed slot/unit/formula/source/cutoff authenticity checks, but separate those checks from full-score completeness in a narrow shared private reader. Compare the stored canonical bundle exactly to the rebuilt bundle. No persisted bundle => None; never synthesize a successful current read or silently write it. Old get/select methods still enforce full blockers/history/required-slot gates unchanged.
- Evaluate each selected signed V6 original AST from the verified current facts using existing public select_visible_formal_facts, derive_comparable_quarters and evaluate_formula. Do not modify original evaluator or use caller-defined expressions. Only required formula fact/period dependency closure is relevant; a missing other feature or unrelated history-window shortage must not exclude this metric. Annual leaves use exactly requested FY; quarter leaves include their needed duration predecessor endpoints. Preserve all relevant parser/mapping/accounting/tie conflicts and ambiguous namespace detection.
- Do not accidentally let an unrelated missing quarter predecessor in the existing aggregate derivation veto a successfully derived requested quarter: select only dependency inputs, require the requested quarter proof, and retain meaningful local conflicts.
- FormalFactIssue lacks trustworthy universal period/source scope. Explicit conservative rule: unresolved provider extraction issues cannot be dismissed by arbitrary details fields; keep selected projection pending for such issues unless existing signed mapping proves them outside the selected metric. No guessing issue scope. Record that conservative limitation. A missing other signed feature alone (feature_required_slot_missing) is not such an extraction issue.
- Return explicit missing/blocked selected FormalFeatureValue plus reasons for legitimate missing facts, denominator/unit failure, or unresolved issues; do not invent numeric values. Only storage/proof/identity errors throw. Missing global mature history alone does not prevent a selected metric with sufficient own AST history.
- Preserve float-based V6 calculation semantics (no historical rewrite). The later Decimal engine converts via the canonical decimal spelling of verified V6 values; do not claim recovered original arbitrary decimal precision here.

VerifiedMetricFeatureProjection is a closure-sealed, non-publicly-constructible capability. It binds security/cutoff/template/root/feature hash, exact stored full bundle input_hash and bundle_hash, selected key tuple and selected signed slot definitions, derived values + evidence, complete captured fact/issue hashes, algorithm version, and deterministic projection hash. Public data is deep-immutable/detached; object.__new__, copy, low-level mutation cannot mint/reuse proof. No module-visible mint helper or caller-supplied verified flag. Provide canonical_bytes/to_dict (recheck seal) and enough clear properties for later MetricFactory. Ensure fake exact repository objects or changed dependencies cannot mint arbitrary proof; use closure-private factory/registration/captured real-read path as appropriate. No V7 schema or storage writes.

## Allowed files
- ashare_pipeline/formal_feature_repository.py: narrow authenticity/completeness factoring + new sealed current projection endpoint.
- ashare_pipeline/formal_metric_features.py: optional focused pure selected-AST evaluation helper if keeping it separate avoids bloating repository. It must not mint official proof.
- tests/test_formal_metric_features.py: new real-evidence/receipt projection regressions.
- tests/test_formal_feature_repository.py: only focused compatibility fixtures/tests if required; do not rewrite existing expectations or import TestCase subclasses causing duplicate legacy tests.
No StateStore, feature builder/evaluator/contract/schema, Context, scoring registry, industry, pool or runner changes in this slice. Escalate if actual API requires another file.

## Tests/verification
TDD required (read skill + writing-good-tests). Real temporary StateStore, raw source lineage, signed graph and persisted feature receipts; no accepting booleans as provenance. Reuse existing fixture helpers but do not copy huge TestCase suites.
Cover: full-valid projection; other required feature missing still valid metric; short global history but metric-own FY/quarter window complete still valid; required fact or predecessor absent pending; zero denominator/unit mismatch pending; valid negative/zero preserved; relevant tie/mapping/accounting conflict pending; complete-provider issues remain explicit; forged or copied or mutated proof rejected; missing receipt/current bundle => None; SQL/file/source tamper rejected; after-freeze fact cannot supply missing earlier value; mixed root/security/template/keys rejected; correction during provider/build/receipt/derivation rejects; determinism and unchanged legacy strict reads.
Run focused new tests frequently. Report actual RED then GREEN commands/output. Parent will run affected legacy regression in parallel once files freeze.

## Operations/report
Workdir D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation; Python D:/Projects/AShareQiheng/.venv/Scripts/python.exe.
Use apply_patch; no network, no git stage/commit, no nested agents. Preserve data and unrelated tmpj4zv9_fq/. Parent commits exact code/test allowlist after independent review.
Write full result, API/wire, TDD evidence and concerns to .superpowers/sdd/2026-09-04-formal-v3-scoring-pool-engine/task-2a-report.md. Parent owns progress.md. Final <=15 lines: status DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT, test summary, concerns, report path.

