# Task 3A1 — Signed neutral-consensus linkage contract

## Active bounded scope
BASE: be01e65ef1557943b63b84a80383252963512db7.
Work only in D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation on codex/formal-v3-implementation.
This slice adds versioned signed registry metadata and Context wrapper compatibility ONLY. The full original Task 3 is copied below as authority, not as permission to implement all of it now. Task 3A2 will add repository-backed complete score-input proofs; Task 3B will implement formulas/scorecards.

Ruling: separate 3A1 registry linkage from 3A2 input authentication so the versioned contract is reviewed before any completeness exception exists. Financial criteria are unchanged; cost if wrong is a small additional integration slice.

## Exact wire contract
- Preserve canonical bytes, accepted exact keys, semantics and hashes of formal-scoring-registry-v1 and the legacy formal-context-registry-v1.
- Admit formal-scoring-registry-v2 with EXACT top-level fields: registry_role, schema_version, descriptors, scoring, input_alternatives. registry_role is scoring. scoring keeps exactly the existing V3 schema; no extra fields within it.
- input_alternatives is an explicit list, allowed empty, sorted ascending lexicographically by template_id with no duplicate template. Subsets of the five templates are allowed; unlinked templates acquire no alternative.
- Each alternative is an exact object of FIVE fields:
  rule_id = consensus-no-coverage-neutral-v1
  template_id = one of general_nonfinancial, bank, broker, insurance, real_estate
  metric_id = T.expectation_change
  feature_key = the existing sole signed required_feature_keys entry of that template's expectation_change slot
  descriptor_id = lowercase 64-hex SHA256 of one canonical descriptor ENTRY in the same wrapper
- The five fields must be exact nonempty strings. No configurable neutral score, confidence cap, arbitrary predicate, fallback value, custom metric ID or override.
- The descriptor linked by descriptor_id must validate through the existing Context _descriptor validator (not a duplicated weaker schema), have context_kind consensus_snapshot, security_scope security, request_security input_security, and period_rule freeze_date_cn. Other descriptor fields preserve existing validation. This slice registers a request contract, not evidence that a source request succeeded.
- For v2, validate ALL descriptors with that existing validator and reject duplicate selection identities (context_kind, scope_key, security_scope); linked descriptor hashes must resolve unambiguously. Hash canonical descriptor ENTRY bytes exactly like SignedContextRequestResolver, not the surrounding scoring wrapper (no self-reference). Do not relax old descriptor validation.
- The linked feature key must be required, belong to the exact template/dimension T, match the existing sole feature adapter, and not occur in ANY OTHER metric's required_feature_keys for that template. Reject wrong metric, unknown/mismatched key, shared key, wrong descriptor kind/scope/period, absent descriptor/hash mismatch, duplicate/unsorted link, unknown fields/versions.
- No rewriting signed source/feature data in production. Existing official bundle, approval, same-root feature vocabulary and all policy checks remain mandatory. Test-only fixtures remain test-only even with v2 and cannot become official by changing approval.

## Immutable registry access
Add consensus_no_coverage_links to the sealed FormalScoringRegistry as an immutable mapping keyed by template_id. Values are recursively immutable mappings containing the validated five wire fields plus context_kind and scope_key derived from the linked descriptor (both exact strings). For v1 the mapping is empty. Include this new field in existing fingerprint/seal checks, so copying or mutating either registry or nested metadata cannot establish an official proof.
This field describes a signed alternative, NOT a verified no-coverage input and NOT a MetricScore.
No new public proof minting factory or numeric calculation in this slice.

## Context compatibility
FormalContextRegistry.load admits v2 with the exact five top-level keys above, scoring an exact dict and input_alternatives an exact list. It retains descriptor validation, signed graph and source checks. Scoring-specific link semantics belong to load_formal_registry; Context alone does not grant a scoring alternative.
Preserve legacy/v1 request descriptor IDs and resolver semantics. Source config validity is reverified by existing request resolution, never guessed by the scoring loader.

## Behavioral meaning reserved for later slices
Only an actually reverified same-root/cutoff consensus_snapshot with no_coverage=true, coverage_status=no_valid_coverage and estimates=[] can eventually use this rule. It grants expectation SUBSCORE 50 and caps C at 0.90, preserving D=1 and all other evidence/history gates. Missing response, transport error, invalid date or missing metric are not no coverage. Do not insert raw value 50 into a percentile cohort or fabricate MetricScore. Do not weaken FormalFeatureRepository or implement its exception here.
Freeze remains 2026-08-31T07:00:00+00:00. Final scoring retains required four FY/eight quarters, cyclic five FY, all longer windows and all other metric cohorts.

## File allowlist
- Modify ashare_pipeline/formal_scoring_registry.py
- Modify ashare_pipeline/formal_context_schema.py (wrapper admission only)
- Create tests/test_formal_scoring_consensus_registry.py
- Modify tests/test_formal_context_repository.py (only ScoringWrapperIntegrationTests compatibility coverage / unknown version)
- Optional small reusable helper addition to tests/test_formal_scoring_registry.py ONLY if existing signed_graph(mutate=..., context=True) is insufficient; explain necessity first.
No feature repository, metric engine/guard, StateStore, schema, data, production policy, old JSON fixture bytes, main, pushes or live collection changes.
Use apply_patch for edits. No Git/index writes; parent stages exact code/tests and commits after independent review.

## TDD and acceptance
Use real byte-sensitive signed_graph fixture mutation BEFORE signing; never mocked approvals, fake proof constructors, always-true verifiers or hash substitutions. Existing signed_graph(context=True) supplies source dataset fixture-state for SZ, so use descriptor('consensus_snapshot', scope_key='fixture-consensus') with that dataset and source, avoiding source-graph mutation. A v2 helper may construct sorted per-template links from existing metric keys before signatures. Do not edit original fixture bytes.

RED must assert real missing behavior (valid v2 load fails before change), not only missing-module import. Focused GREEN must cover:
1. unchanged v1 test and official registries load, empty immutable links, unchanged original fixture hash;
2. valid v2 genuine signed graph, exact canonical descriptor hash, subset and all-five-template links, empty links legal;
3. immutable mapping and nested values; forged/copied/mutated registry rejected by require_official;
4. rejection cases listed above, including re-signed invalid graphs so test reaches semantic checks;
5. wrong approval/mixed root/tampered bytes/test-purpose separation remain enforced;
6. Context legacy/v1/v2 resolve SAME existing security_state descriptor with IDENTICAL descriptor_id; v2 linked consensus request resolves and descriptor_id equals hash of canonical entry;
7. v2 unknown/missing extra top-level keys or non-list alternatives rejected; use formal-scoring-registry-v999 for unknown-version regression instead of v2.
Run only focused new registry suite + existing registry suite + ScoringWrapperIntegrationTests; no expensive full metric universe suites. Parent will run additional affected compatibility tests after freeze.
Python: D:/Projects/AShareQiheng/.venv/Scripts/python.exe. Test-owned temp resources only; use existing worktree-local tempfile pattern if Windows secure-chain permissions require it, without unrelated edits. Commands should be verbose to expose progress.
Read applicable TDD/verification skills before work, self-review exact diff, then freeze changes and write report via apply_patch.

## Report and agent rules
No subagents, no broad repository audit, no Git staging/commits/network. Raise concrete questions before expanding scope.
Report path: .superpowers/sdd/2026-09-04-formal-v3-scoring-pool-engine/task-3a1-report.md
Include implementation, exact files, actual RED/GREEN command/output/duration, final relevant hashes, self-review findings and concerns. Return only status DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT, one-line tests, concerns, report path; under 15 lines.
A genuine signed synthetic official-wire graph tests software provenance only; it is not a production approved financial registry.

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



