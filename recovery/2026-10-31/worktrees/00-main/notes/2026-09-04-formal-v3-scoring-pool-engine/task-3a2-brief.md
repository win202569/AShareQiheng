# Task 3A2 — Repository-owned complete score inputs

BASE: 37ab15c6d47213646f88693b975cb5f81eb1fa0e. Task 3A1 is reviewed, verified and committed; this brief becomes active on parent dispatch. Its active scope supersedes the larger Task 3 text copied as authority below. Main has independently inspected the provenance composition; task-3a2-preflight.md records findings, not additional scope.

## Scope and API
Worktree D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation, codex/formal-v3-implementation.
Create ashare_pipeline/formal_score_inputs.py with:
- FormalScoreInputRepository(feature_repository, context_repository, *, registry_signature_verifier)
- repository.build_batch(frozen_input_hash, *, scoring_registry) -> FormalScoreInputBatch or None only when genuine frozen universe is absent
- closure-sealed FormalScoreInputBatch and FormalScoreInput (ready-only) with require_verified(), canonical_bytes(), detached to_dict(), immutable attrs.
- batch.security_ids: complete canonical SH/SZ/BJ tuple; batch.inputs: tuple of ready FormalScoreInput in security order; batch.pending_reasons: immutable mapping of every non-ready SID to nonempty deterministic reason tuple.
- batch.input_for(security_id): exact-string canonical member selector, ready input or None for a genuine pending member, raise for unknown/spoofed selector.
No caller security subset, metric subset, old batch, raw score/evidence object, feature bundle, confidence, year count, cyclic flag, industry string, no-coverage boolean, waiver key, final score or override. Factory owns all provenance reads/calculations. No seven-dimension/confidence/grade/card/policy/pool arithmetic yet (Task 3B/4/5).

## Minimal provenance composition — no new public feature adapter
- Construct one genuine internal FormalMetricInputRepository and one genuine FormalMetricContextRepository from exact same-store repositories/verifier; retain identity closure privately. Reject uninitialized/copied/replaced repositories/providers/transitive read/calculation dependencies even if every member would be pending.
- Begin _metric_batch_guard on the exact owned FormalMetricCurrentInputProvider BEFORE constructing a genuine complete MetricInputBatch with metric_ids=None. It already authenticates current provider facts/issues, V6 rebuild equality, actual persisted source receipts, signed root, complete universe/industry and final member closure.
- While this OUTER guard remains active, authenticate each classified present current full bundle through the captured original FormalFeatureRepository._read_authenticated_bundle(require_complete=False, input_hash=marker.input_hash). The marker MUST be from this internally built genuine batch.feature_states, not caller data. Compare full bundle_hash, input_hash, registry_manifest_hash, feature_registry_hash, security_id, template_id and exact as_of_utc to marker. A missing receipt where the marker said present or any byte/header mismatch is a race/corruption error, not pending.
- This same-generation composition establishes current complete-input provenance without duplicating the provider/rebuild path or adding a public feature-state adapter. Preserve all existing public strict full reads and old V6 bytes/hashes.
- Capture _require_authentic_metric_feature_repository and run before/after full reads and immediately before publication.
- Small permitted integration: export the EXISTING closure-private FormalMetricContextRepository dependencies checker as _require_authentic_metric_context_repository. Reuse it before/after consensus reads and publication. It must retain the exact same transitive class/module validator, source/snapshot, path and verifier identities; no duplicate weaker guard. Do not add it to public __all__, change old payloads or create a mint capability.
- Capture/check genuine metric build, peer-context and percentile helpers plus consumed proof methods against replacement (including inherited __getattr__, require_verified, canonical_bytes, to_dict, input_for). Keep new repository identity registration, immutable source paths/verifier identity and reinitialization rejection closure-private.
- Existing filesystem contract is bounded authenticated immutable reads, not an OS-wide atomic filesystem snapshot. Do not hold a database writer lock during slow reads, canonical serialization, group/rank construction or object freezing.

## Whole-company readiness, separate from peer eligibility
- Retain ALL universe members. Valid present marker alone is not a complete-company proof. Unknown template/invalid industry, genuine current receipt absence, immature history, incomplete features or insufficient cohorts become explicit pending; corruption/signature/SQL-file mismatch/leading version ties/dependency substitution abort rather than broad exception-catching/string-based classification.
- Read the full signed V6 slot set from the same-root verified feature registry. Inspect full bundle values, NOT selected projection values, with exact signed identity/unit/formula. ALL required signed slots (even outside 25 scoring definitions) must be derived, except the one registered neutral key under the later rules. Optional slots must retain existing derived/missing status rule; blocked/unknown optional status blocks readiness. Any non-exempt required missing/blocked stays pending.
- Preserve strict normal complete semantics: any full bundle blocker precludes normal readiness. For the neutral branch, no arbitrary blocker-string filtering: require typed empty issue snapshot hash from genuine marker, actual full-slot status restrictions, and at least one non-exempt required full slot derived; full V6 builder's global history/conflict/quarter blockers block every value and therefore cannot be waived. A blocked expectation slot is not neutral-eligible.
- Base history is existing require_formal_history using actual bundle.history_endpoints and last eight observed comparable_quarter_keys, exact cutoff 2026-08-31T07:00:00+00:00. It requires FY2022..FY2025 and exactly 2024Q3..2026Q2. All signed longer NON-EXEMPT metric windows remain mandatory via derived values/metric proofs. Do not infer all-field-per-year completeness from observed unions or invent extra field requirements.
- Cyclic is derived ONLY from genuine current secondary_industry membership in scoring_registry.cyclic_secondary_industries. Enforce existing cyclic=True five-FY history gate before readiness. Continuous FY count for later H counts backward from FY2025, capped at five; unrelated old endpoints do not increase it.
- Obtain all 25 metric percentile scores with genuine build_metric_peer_context + score_metric_percentile on this batch (except neutral expectation fixed-subscore alternative). Every normal slot requires genuine cohort N>=20. Do not recalculate/filter peers by company history, full-score readiness, pool veto or other sibling metrics.
- Keep qualified identities everywhere: M.return_persistence differs from CA.return_persistence.

## Registered consensus path
- 3A1 sealed registry field consensus_no_coverage_links maps template_id to immutable validated rule/feature/descriptor/scope metadata.
- For a linked template, read actual consensus_snapshot via same-root FormalContextRepository.get_verified_many, grouping sorted security IDs by linked scope to avoid one full-table scan per security. v1/unlinked templates use their normal feature-only metric path and gain no neutral override.
- Require selected fact descriptor_id EXACTLY equal signed link descriptor_id, same exact root/security/cutoff/scope/kind, and normal existing source/time/request/receipt authenticity. Re-read selected Context scope/absence closure after all reads and compare canonical actual facts before final publication. Missing actual Context is pending even if a financial expectation feature exists; no transport error or missing date becomes no coverage.
- Covered response: expectation uses its normal genuine metric percentile, with all full completeness/cohort gates.
- Verified no_coverage true + value.coverage_status no_valid_coverage + estimates empty: expectation SUBSCORE is fixed Decimal('50'), carries the separate actual Context proof and registered rule, and later C is capped at Decimal('0.90'). Do not fabricate a MetricScore or insert raw 50 into any peer cohort.
- The full expectation value may be derived or missing, never blocked. A derived value is retained for audit but the registered no-coverage branch supplies the focal subscore. Existing genuine metric-level peers remain determined by their valid metric facts; do not rewrite cohorts according to whole-company neutral readiness.
- No registered link, missing response, invalid provenance/date, malformed coverage, unverified fact or caller boolean grants the neutral alternative. Other 24 slots and every non-exempt required full slot/history gate remain mandatory.
- The factory verifies the actual Context bytes before extracting temporal reliability: timestamp source branch yields Decimal('1'); verified date-only with calendar_binding yields Decimal('0.8'). Normal slot quality is the minimum actual FormalEvidenceRef.published_precision quality across all contributing refs. Persist the underlying exact refs, not only quality scalars; do not accept a caller supplied P/D/H/K.

## Immutable audit payload and publication
- Version every new payload. Bind input and batch hashes to canonical data, exact full registry graph/root, frozen universe/population, internal MetricInputBatch.batch_hash, security/template/industry, full feature input/bundle/state identity, provider batch/fact/issue hashes, observed history/continuous FY count/cyclic classification, every slot definition/weight/evidence reference, genuine metric-score/context identities and separate neutral Context/rule when present.
- Normal slot value is Decimal(metric_score.percentile), neutral value Decimal('50'); keep metric/neutral evidence kinds distinguishable and immutable. Persist exact Decimal strings using existing deterministic canonical conventions, with no display quantization.
- Existing scoring registry defines 25 slots; weights/directions/feature bindings come from it, never caller dictionaries. Ready input must contain every slot once, no reweighting. Expose sufficient immutable metadata for Task 3B to recompute D/P/H/K and dimensions without accepting arbitrary objects.
- Hash manifests acyclically; no hash-of-self recursion. No persistence/schema writes in this task.
- Prepare outer batch/ready inputs/canonical data outside final writer fence. Every OUTER FormalScoreInputBatch/FormalScoreInput and later descendants share one private revocable publication capability. Failure of finalizer, final dependency checks, rollback or context-manager exit revokes all outer proofs, including any tentatively leaked children. Proof methods reject copied/forged/unpublished/revoked objects. No strong owner/cache cycle; detached successful ready inputs remain valid historical proofs.
- Inner MetricInputBatch/MetricScore are independently valid historical proofs from their earlier successful inner guard. Their survival after a later outer failure is not an outer complete-input proof. No public constructor/calculation consumes those alone as a complete scoring input; never mutate Task 2C publication semantics to conflate these scopes.

## Tests and scope
TDD real behavior RED before production. Use genuine signed fixtures, real leased producer snapshots/facts/bundles/context and byte-sensitive signatures, no fake official proof minting or always-true verifier.
File allowlist:
- Create ashare_pipeline/formal_score_inputs.py
- Modify ashare_pipeline/formal_metric_context.py ONLY private export of existing dependency checker
- Create tests/formal_score_input_fixtures.py
- Create tests/test_formal_score_inputs.py (split one focused test file if clearly necessary, report before expanding)
- Modify tests/formal_metric_feature_fixtures.py / tests/formal_metric_fixtures.py only narrowly reusable fixture parameters/helpers, preserving existing default behavior.
No StateStore/schema/V6 algorithm/FeatureRepository/metric engine/registry production edits, no existing JSON fixture bytes/data/SQLite/WAL/SHM/progress commits, no live network or main/push.
Tests should cover:
1. normal complete ready proof with all 25 scores and true 4FY/8quarter history; complete universe includes pending unready peers without excluding their eligible metrics;
2. verified registered no-coverage missing expectation produces separate neutral 50 branch and cap metadata, while other missing metrics/history/cyclic fifth FY/N<20 remain pending; derived expectation + no-coverage uses registered neutral branch;
3. v1/unlinked absence cannot neutralize; linked actual missing Context cannot fall back to a derived feature; covered normal path and no-covered-feature pending;
4. full required slots outside scoring definitions, optional blocked statuses, global typed issues/visible conflicts/quarter gaps must not be waived;
5. actual temporal evidence reliability (timestamp/date-only) and continuous endpoint count/cyclic signed classification, not caller overrides;
6. mixed root/hash/security/cutoff, public/legacy bundle/Context objects, copied/spoofed dependency/proof/helper substitutions, actual file/SQL/source tamper fail closed;
7. provider or DB correction during full/consensus final sweep rejects whole outer batch; genuine missing-to-present Context transition invalidates; publication failures revoke batch and ready children, successful detached proofs stay valid.
Test fixture efficiency: reuse existing graph/universe/current-provider helpers; don't import/inherit a TestCase as a fixture. Build all 25 synthetic FY2025 values for peers in one response per peer; only focal company needs mature full history. For duration full-company facts supply cumulative prerequisites for all current-year fields, not just an anchor (otherwise quarter derivation globally blocks). Use distinct task/source generations per period, publish one complete generation only after insertion, and separate actual consensus producer receipt. Extend source/descriptor before signing and recompute feature.source_registry_hash when configs change. Avoid duplicate focal prepopulation. Prefer few whole-universe integration fixtures plus focused input-gate cases, not 22-member rebuilds per validation permutation.
Python D:/Projects/AShareQiheng/.venv/Scripts/python.exe. Worktree-owned temp directories for Windows secure-chain tests; only test-owned cleanup. Verbose focused tests, never duplicate long runs due delayed tool output.

## Agent/report contract
Read applicable TDD/verification skills and self-review exact diff. No subagents, no Git/index writes/commits, no network, no data deletion. Parent handles independent review, tests and code-only commit. If scope cannot remain bounded or a requirement cannot be met with named APIs, report NEEDS_CONTEXT/BLOCKED with concrete evidence instead of silently expanding.
Report: .superpowers/sdd/2026-09-04-formal-v3-scoring-pool-engine/task-3a2-report.md. Use apply_patch for all file edits.
Report includes actual RED/GREEN command/output/timing, exact changed files and hashes, immutable schema/API details, self-review/concerns. Freeze code after reporting. Return <=15 lines status, one-line verification and report path; no all-plan completion claim.

## Global Constraints (verbatim)
- This plan depends on the V5 formal evidence/universe migration and V6 formal financial-feature migration. It starts persistence work at schema version 7 and must not rewrite V2-V6 DDL.
- Official nonzero scores require one complete, hash-pinned production VerifiedRegistryBundle whose root FormalRegistryManifest binds source, mapping, feature, scoring, industry, cyclic, redline, status, and event registry hashes. Reject an unsigned, incomplete, test-only, or child-hash-mismatched bundle before calculating an official run.
- The formal universe is SH/SZ/BJ A-share ordinary shares. A BJ member follows identical peer, redline, and pool rules and must never be dropped by an SH/SZ-only helper.
- Metric peer eligibility is metric-level. It depends only on frozen universe membership, valid template/industry classification, and every verified required fact for that metric; it does not depend on formal_scored, pool eligibility, or a completed seven-dimension score.
- Use exactly the V3 templates: general_nonfinancial, bank, broker, insurance, and real_estate. Do not revive V2 resource, utility, or research-growth templates.
- All calculations are point-in-time at FORMAL_FREEZE_AT_CN. Price evidence preserves stale_trading_days and an actual valid-close date; old preclose substitution is forbidden.
- No missing slot receives zero, a peer median, an estimate, or redistributed weight. A missing required formal slot produces pending_evidence rather than a partial score.
- No code path accepts a user-supplied final score, pool rank, pool label, or override. Registry changes and source corrections produce a new input hash/release, not edits to a prior output.
- The engine is offline and deterministic after verified inputs are stored. Unit tests use fixtures and do not contact official or third-party websites.
- The runner obtains typed feature bundles only through FormalFeatureRepository and market/industry/regulatory/event/consensus facts only through FormalContextRepository. It re-verifies their stored hashes and manifest identity; it never reads an unverified row or a legacy data source directly.
- Preserve all data and legacy tables. Do not stage data, SQLite, WAL/SHM, or data/status/pipeline_status.json in code commits.

## Original approved task text

### Task 3: Seven Dimensions, Confidence, Base Scores, Risk, and Grades

**Files:**
- Create: ashare_pipeline/formal_scoring.py
- Create: tests/test_formal_scoring.py

**Interfaces:**
- Produces FormalScoreInput, DimensionScore, ConfidenceBreakdown, FormalScoreCard, calculate_confidence, calculate_score_card, and grade_for_score.
- Consumes every applicable MetricScore, verified slot evidence metadata, FormalFeatureBundle hash, and registry.
- Rejects score construction when any required slot is absent, invalid, unverified, temporally invisible, or internally inconsistent.

- [ ] **Step 1: Write the failing score-formula tests**

~~~python
class FormalScoringTests(unittest.TestCase):
    def test_confidence_uses_global_slot_weight_and_no_coverage_cap(self):
        slots = complete_slots(timestamp_quality=Decimal("0.8"), annual_endpoints=4)
        confidence = calculate_confidence(slots, no_consensus_coverage=True)
        self.assertEqual(confidence.D, Decimal("1"))
        self.assertEqual(confidence.K, Decimal("1"))
        self.assertEqual(confidence.H, Decimal("0.8"))
        self.assertEqual(confidence.P, Decimal("0.8"))
        self.assertEqual(confidence.C, Decimal("0.90"))

    def test_score_card_applies_v3_s0_sc_b_and_risk_formulas(self):
        card = calculate_score_card(
            dimensions={"G": 80, "V": 70, "M": 60, "EQ": 50, "FS": 40, "CA": 90, "T": 30},
            confidence=Decimal("1"),
            m_return_persistence=Decimal("70"),
            m_margin_persistence=Decimal("50"),
            ca_shareholder_dilution=Decimal("60"),
            ca_discipline=Decimal("80"),
        )
        self.assertEqual(card.S0, Decimal("64.4"))
        self.assertEqual(card.Sc, Decimal("64.4"))
        self.assertEqual(card.Sbase, Decimal("68.22222222222222222222222222"))
        self.assertEqual(card.B, card.Sbase)
        self.assertEqual(card.r_safety, Decimal("51.07142857142857142857142858"))
        self.assertEqual(card.risk_exposure, Decimal("48.92857142857142857142857142"))

    def test_absent_required_slot_is_pending_not_a_reweighted_dimension(self):
        with self.assertRaisesRegex(ValueError, "missing required slot"):
            calculate_dimensions(slots_without("T.expectation_change"))

    def test_grade_boundaries_are_exact(self):
        self.assertEqual(grade_for_score(Decimal("90")), "A+")
        self.assertEqual(grade_for_score(Decimal("89.999")), "A")
        self.assertEqual(grade_for_score(Decimal("0")), "E")
~~~

- [ ] **Step 2: Run score tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_scoring -v
~~~

Expected: FAIL because ashare_pipeline.formal_scoring does not exist.

- [ ] **Step 3: Implement V3 formulas and evidence gates**

For every applicable slot set:

~~~text
q_i = (dimension_weight × slot_internal_weight) / sum(applicable dimension_weight × slot_internal_weight)
D   = sum(q_i for verified slots)
P   = sum(q_i × minimum timestamp quality among the slot's evidence references)
H   = min(continuous_complete_fy_endpoint_count / 5, 1)
C   = 0.60 + 0.40 × (0.30D + 0.25P + 0.25H + 0.20K)
~~~

Require D=1, K=1, at least four continuous FY endpoints, and all metric-specific windows before a FormalScoreCard exists. For verified no-consensus coverage, preserve the neutral expectation slot at 50 and set C to the lower of C and 0.90. An unverified consensus response is not no coverage and creates pending evidence.

Calculate:

~~~text
S0 = .18G + .18V + .18M + .12EQ + .08FS + .16CA + .10T
Sc = 50 + C × (S0 - 50)
Sbase = (.18G + .18V + .18M + .12EQ + .08FS + .16CA) / .90
B = 50 + C × (Sbase - 50)
M持续性 = (.40 × M回报持续性 + .30 × M利润率持续性) / .70
CA下行保护 = (.20 × CA股东回报与反稀释 + .15 × CA资本纪律) / .35
R安全 = .40FS + .25EQ + .20M持续性 + .15CA下行保护
风险暴露 = 100 - R安全
~~~

Quantize only serialized display values, not comparison operands or persisted calculation values. Grade bands are A+ from 90 inclusive, A from 80 inclusive, B from 70 inclusive, C from 60 inclusive, D from 50 inclusive, and E below 50. Persist C's D/P/H/K components and every slot evidence reference so a release audit card can recompute the result.

- [ ] **Step 4: Run scoring and feature-contract suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_scoring tests.test_formal_metric_engine tests.test_formal_feature_contract -v
~~~

Expected: PASS; V1 feature bundles remain unable to enter FormalScoreInput.

- [ ] **Step 5: Commit score formulas**

~~~powershell
git add -- ashare_pipeline/formal_scoring.py tests/test_formal_scoring.py
git commit -m "feat: add formal V3 score formulas"
~~~
