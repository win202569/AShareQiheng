# Formal V3 Scoring and Pool Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Implement the isolated V3 metric, seven-dimension, risk, policy, and deterministic dual-pool engine that can score only verified, complete formal inputs and never turn legacy prefilter data into an official score.

**Architecture:** Build a formal registry-and-engine layer on top of the V5 evidence/universe and V6 financial-feature foundations. A frozen registry supplies the five templates, field mappings, policy rules, and metric definitions; pure calculation modules convert verified FormalFeatureBundle inputs into metric percentiles and V3 scores; a separate policy module applies redlines and cyclic protections; the pool module deterministically selects strong and wait members. Persist every raw metric, peer context, score, policy outcome, and selection decision through an additive SQLite V7 schema. The legacy scoring.py and score_item tables remain preview-only and are not imported by this domain.

**Tech Stack:** Python 3.12, Python standard library, SQLite, unittest, existing formal V3 evidence, universe, and feature contracts.

**Spec:** docs/superpowers/specs/2026-09-04-formal-scoring-release-contract-design.md

## Global Constraints

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

---

## File Structure

| File | Responsibility |
|---|---|
| ashare_pipeline/formal_scoring_registry.py | Hash-pinned typed registry, five template contracts, slot definitions, and validation |
| ashare_pipeline/formal_metric_engine.py | Metric eligibility, peer cohorts, midpoint percentile ranks, and immutable metric results |
| ashare_pipeline/formal_scoring.py | V3 confidence, dimensions, S0, Sc, B, R safety, grade bands, and score input validation |
| ashare_pipeline/formal_policy_engine.py | Cyclic protection, redline/status outcomes, hard-veto evaluation, and market-staleness checks |
| ashare_pipeline/formal_pool.py | Strong/wait qualification, industry caps, deterministic scanning, and canonical counts |
| ashare_pipeline/formal_score_runner.py | Offline orchestration from V6 bundles to V7 rows and universe-status decisions |
| ashare_pipeline/state_store.py | Additive SQLite V7 score, metric, peer, policy, and pool persistence APIs |
| tests/fixtures/formal_v3_test_registry.json | Complete fixture-only registry for hermetic score tests |
| tests/test_formal_scoring_registry.py | Registry completeness, hash, and production/test separation tests |
| tests/test_formal_metric_engine.py | Cohort, tie, direction, fallback, and invalid-input tests |
| tests/test_formal_scoring.py | C, seven dimensions, risk, grades, and no-coverage tests |
| tests/test_formal_policy_engine.py | Cyclic, redline, hard-veto, event, and stale-price tests |
| tests/test_formal_pool.py | Qualification, ordering, caps, mutual exclusion, and count tests |
| tests/test_formal_score_runner.py | Fail-closed orchestration, incremental rebuild, and status tests |
| tests/test_state_store.py | V6-to-V7 migration, immutability, and persistence tests |

### Task 1: Hash-Pinned V3 Registry and Template Contract

**Files:**
- Create: ashare_pipeline/formal_scoring_registry.py
- Create: tests/fixtures/formal_v3_test_registry.json
- Create: tests/test_formal_scoring_registry.py

**Interfaces:**
- Produces FormalScoringRegistry, TemplateDefinition, MetricDefinition, RedlineDefinition, StatusRule, RegistryApproval, and load_formal_registry.
- Consumes canonical JSON bytes, the verified V6 formal feature-key vocabulary, and VerifiedRegistryBundle from the financial-feature plan.
- A test registry may be used only with purpose test; FormalScoringRegistry.require_official rejects it and rejects a registry whose approval hash is absent or different from its canonical content hash or whose declared scoring hash does not match the verified bundle.

- [ ] **Step 1: Write the failing registry tests**

~~~python
import unittest

from ashare_pipeline.formal_scoring_registry import (
    RegistryApproval,
    RegistryValidationError,
    load_formal_registry,
)


class FormalScoringRegistryTests(unittest.TestCase):
    def test_complete_test_registry_has_exact_v3_weights_and_five_templates(self):
        registry = load_formal_registry(
            "tests/fixtures/formal_v3_test_registry.json",
            RegistryApproval.for_test_fixture(),
        )
        self.assertEqual(
            tuple(registry.templates),
            ("general_nonfinancial", "bank", "broker", "insurance", "real_estate"),
        )
        self.assertEqual(registry.dimension_weights, {
            "G": 0.18, "V": 0.18, "M": 0.18, "EQ": 0.12,
            "FS": 0.08, "CA": 0.16, "T": 0.10,
        })
        self.assertEqual(registry.internal_weights["G"], (0.35, 0.25, 0.25, 0.15))

    def test_missing_field_map_or_policy_rule_cannot_be_loaded(self):
        payload = complete_registry_json_without("bank.metrics.V.normalized_earnings_yield.field_map")
        with self.assertRaisesRegex(RegistryValidationError, "field_map"):
            load_formal_registry_bytes(payload, RegistryApproval.for_test_fixture())

    def test_test_or_unapproved_registry_cannot_run_official_scoring(self):
        registry = load_fixture_registry()
        with self.assertRaisesRegex(RegistryValidationError, "official"):
            registry.require_official(fixture_registry_bundle())

    def test_root_manifest_rejects_mixed_feature_and_scoring_registries(self):
        registry = load_fixture_registry()
        with self.assertRaisesRegex(RegistryValidationError, "manifest"):
            registry.require_official(bundle_with_other_scoring_hash())
~~~

- [ ] **Step 2: Run the registry tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_scoring_registry -v
~~~

Expected: FAIL because the formal registry module and fixture do not exist.

- [ ] **Step 3: Implement canonical registry parsing and validation**

Implement immutable types with this public contract:

~~~python
@dataclass(frozen=True)
class RegistryApproval:
    purpose: Literal["test", "official"]
    approved_content_sha256: str | None
    approval_id: str | None

@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    dimension: Literal["G", "V", "M", "EQ", "FS", "CA", "T"]
    internal_weight: Decimal
    direction: Literal["higher", "lower"]
    required_feature_keys: tuple[str, ...]
    formula_version: str
    field_map_version: str
    denominator_rule: str | None

@dataclass(frozen=True)
class FormalScoringRegistry:
    contract_version: str
    content_sha256: str
    templates: Mapping[str, TemplateDefinition]
    dimension_weights: Mapping[str, Decimal]
    internal_weights: Mapping[str, tuple[Decimal, ...]]
    cyclic_secondary_industries: frozenset[str]
    redlines: tuple[RedlineDefinition, ...]
    status_rules: tuple[StatusRule, ...]

    def require_official(self, registry_bundle: VerifiedRegistryBundle) -> None: ...
    def template_for(self, template_id: str) -> TemplateDefinition: ...
~~~

Canonicalize JSON using UTF-8, sorted keys, compact separators, and Decimal parsing before hashing. Validate all of the following before returning a registry:

- Contract version is V3 and the seven dimension weights sum exactly to Decimal("1.00").
- Each dimension contains the exact V3 internal weights from section 7.2 and every template has a conceptually equivalent definition for every slot.
- Every metric lists nonempty required feature keys, a formula version, field-map version, direction, unit/period rule, and invalid-denominator rule.
- Every template has an explicit template-specific map for financial-equivalent facts, not an implied deletion or reweighting.
- Cyclic classification, redline, status/event, and market-liquidity rules all have registry versions and source evidence categories.
- Test-only registry content declares purpose test and cannot satisfy require_official. An official registry requires purpose official, a nonempty approval_id, exact approved_content_sha256, and a VerifiedRegistryBundle whose loaded source/mapping/feature/scoring/industry/cyclic/redline/status/event blobs all re-hash to the root manifest declarations. The scoring registry itself is loaded only from registry_bundle.blob("scoring"), while the policy engine consumes the named cyclic/redline/status/event blobs from the same bundle.

The fixture registry is internally complete but uses synthetic V6 fixture feature keys and explicitly declares purpose test. It demonstrates engine behavior only; it is not a production investment-policy configuration.

- [ ] **Step 4: Run registry and feature-contract regression tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_scoring_registry tests.test_formal_feature_contract -v
~~~

Expected: PASS; no V1 feature-contract behavior changes.

- [ ] **Step 5: Commit the formal registry contract**

~~~powershell
git add -- ashare_pipeline/formal_scoring_registry.py tests/fixtures/formal_v3_test_registry.json tests/test_formal_scoring_registry.py
git commit -m "feat: add hash-pinned formal scoring registry"
~~~

### Task 2: Metric Eligibility, Peer Cohorts, and Percentile Scores

**Files:**
- Create: ashare_pipeline/formal_metric_engine.py
- Create: tests/test_formal_metric_engine.py

**Interfaces:**
- Produces MetricInput, MetricPeerContext, MetricScore, metric_peer_eligible, build_metric_peer_context, and score_metric_percentile.
- Consumes frozen FormalUniverseMember, frozen industry mapping, FormalFeatureBundle, TemplateDefinition, and MetricDefinition.
- Returns an explicit pending reason for no valid template, no valid industry, missing verified fact, invalid denominator, unsupported unit, or a peer cohort below twenty; it never silently builds a smaller cohort.

- [ ] **Step 1: Write the failing peer and rank tests**

~~~python
class FormalMetricEngineTests(unittest.TestCase):
    def test_tied_higher_metric_uses_average_rank_midpoint_formula(self):
        rows = [
            metric_input("SZ000001", Decimal("1")),
            metric_input("BJ430001", Decimal("2")),
            metric_input("SH600001", Decimal("2")),
            metric_input("SH600002", Decimal("4")),
        ]
        score = score_metric_percentile(rows[1], rows, direction="higher")
        self.assertEqual(score.average_rank, Decimal("2.5"))
        self.assertEqual(score.percentile, Decimal("50.0"))
        self.assertEqual(score.peer_count, 4)

    def test_lower_is_better_reverses_percentile_without_reversing_tie_rank(self):
        rows = [metric_input("SZ000001", Decimal("1")), metric_input("SZ000002", Decimal("3"))]
        self.assertEqual(
            score_metric_percentile(rows[0], rows, direction="lower").percentile,
            Decimal("75.0"),
        )

    def test_secondary_industry_shortfall_falls_back_then_fails_closed_below_twenty(self):
        context = build_metric_peer_context(metric_id="m", inputs=nineteen_secondary_plus_twenty_primary())
        self.assertEqual(context.scope, "template_primary_industry")
        self.assertEqual(context.peer_count, 20)
        self.assertEqual(build_metric_peer_context(metric_id="m", inputs=only_nineteen()).reason, "peer_count_below_20")

    def test_metric_peer_eligible_does_not_require_formal_scored(self):
        candidate = unscored_but_verified_metric_input("BJ430001")
        self.assertTrue(metric_peer_eligible(candidate))
~~~

- [ ] **Step 2: Run metric tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_metric_engine -v
~~~

Expected: FAIL because ashare_pipeline.formal_metric_engine does not exist.

- [ ] **Step 3: Implement deterministic cohorts and ranks**

Use immutable input and output records:

~~~python
@dataclass(frozen=True)
class MetricInput:
    security_id: str
    template_id: str
    secondary_industry: str | None
    primary_industry: str | None
    metric_id: str
    raw_value: Decimal | None
    verified_feature_refs: tuple[str, ...]
    invalid_reason: str | None

@dataclass(frozen=True)
class MetricPeerContext:
    metric_id: str
    security_id: str
    scope: Literal["template_secondary_industry", "template_primary_industry"] | None
    peer_security_ids: tuple[str, ...]
    peer_count: int
    reason: str | None

@dataclass(frozen=True)
class MetricScore:
    metric_id: str
    security_id: str
    raw_value: Decimal
    percentile: Decimal
    average_rank: Decimal
    peer_context: MetricPeerContext
~~~

metric_peer_eligible returns true only when the universe member is in scope, has a valid registry template plus frozen primary and secondary industry assignments, has each required feature reference verified and visible at freeze, and has a valid metric-specific denominator. It does not inspect complete seven-dimension status, veto flags, score rows, or pool rows.

build_metric_peer_context first filters by template plus secondary industry and metric_peer_eligible. If N is at least twenty, return that group. Otherwise filter by template plus primary industry; N must then be at least twenty. Return sorted security IDs and a reason instead of fabricating a score for a short cohort.

For a positive direction, calculate:

~~~text
percentile = 100 × (average_rank - 0.5) / N
~~~

Use average ranks for ties, exact Decimal arithmetic, and security ID only as a deterministic output-order tie breaker, never as a rank tie breaker. For lower-is-better metrics, return one hundred minus the positive-direction percentile. Preserve raw negative and zero values where the metric definition permits them; reject only the definition's invalid denominator or non-comparable-unit cases.

- [ ] **Step 4: Run focused peer and formal-universe tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_metric_engine tests.test_formal_universe -v
~~~

Expected: PASS, including BJ fixtures and all peer fallback cases.

- [ ] **Step 5: Commit metric scoring**

~~~powershell
git add -- ashare_pipeline/formal_metric_engine.py tests/test_formal_metric_engine.py
git commit -m "feat: add formal peer percentile engine"
~~~

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

### Task 4: Cyclic Protection, Redlines, Event States, and Pool Vetoes

**Files:**
- Create: ashare_pipeline/formal_policy_engine.py
- Create: tests/test_formal_policy_engine.py

**Interfaces:**
- Produces MarketEvidence, PolicyEvidence, RedlineOutcome, CyclicOutcome, PoolVetoOutcome, and evaluate_formal_policy.
- Consumes registry rules plus only verified source-backed facts and status evidence.
- Produces module caps, normalized-value substitutions, explicit pool prohibition states, or pending reasons; it does not mutate an input score in place.

- [ ] **Step 1: Write the failing policy tests**

~~~python
class FormalPolicyEngineTests(unittest.TestCase):
    def test_cyclic_peak_caps_growth_and_quality_and_uses_lower_profit_base(self):
        outcome = evaluate_cyclic_protection(
            cyclic=True,
            rolling_roe=Decimal("15"),
            rolling_margin=Decimal("20"),
            five_year_roe=(1, 2, 3, 4, 15),
            five_year_margin=(1, 2, 3, 4, 20),
            current_profit=Decimal("100"),
            five_year_median_profit=Decimal("60"),
        )
        self.assertEqual(outcome.growth_cap, Decimal("80"))
        self.assertEqual(outcome.quality_cap, Decimal("80"))
        self.assertEqual(outcome.normalized_profit, Decimal("60"))

    def test_cyclic_security_without_five_complete_observation_points_is_pending(self):
        self.assertEqual(
            evaluate_cyclic_protection(cyclic=True, five_year_roe=(1, 2, 3, 4), five_year_margin=(1, 2, 3, 4)).reason,
            "cyclic_history_incomplete",
        )

    def test_hard_vetoes_and_stale_market_evidence_are_exact(self):
        self.assertTrue(evaluate_pool_veto(st=True).vetoed)
        self.assertTrue(evaluate_pool_veto(net_assets=Decimal("0")).vetoed)
        self.assertTrue(evaluate_pool_veto(audit_opinion="qualified").vetoed)
        self.assertTrue(evaluate_pool_veto(stale_trading_days=20).vetoed)
        self.assertEqual(evaluate_pool_veto(stale_trading_days=250, valid_close=None).reason, "market_evidence_missing")

    def test_unquantifiable_major_event_is_status_not_a_t_score(self):
        outcome = evaluate_event_status(unquantifiable_major_event())
        self.assertIn(outcome.status, {"strong_pool_prohibited", "both_pools_prohibited"})
        self.assertIsNone(outcome.t_component_value)
~~~

- [ ] **Step 2: Run policy tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_policy_engine -v
~~~

Expected: FAIL because ashare_pipeline.formal_policy_engine does not exist.

- [ ] **Step 3: Implement registry-driven policy outcomes**

Implement relevant contracts:

~~~python
@dataclass(frozen=True)
class MarketEvidence:
    as_of_date: str
    valid_close: Decimal | None
    valid_close_date: str | None
    stale_trading_days: int
    exchange_allows_trading: bool
    volume: Decimal
    turnover: Decimal

@dataclass(frozen=True)
class PolicyOutcome:
    pending_reason: str | None
    redline_outcomes: tuple[RedlineOutcome, ...]
    cyclic_outcome: CyclicOutcome | None
    status_outcomes: tuple[StatusOutcome, ...]
    pool_veto: PoolVetoOutcome
~~~

An effective trade requires exchange_allows_trading plus volume greater than zero and turnover greater than zero. With stale_trading_days one through nineteen, valuation may use valid_close only if valid_close_date is recorded; carry stale state into the registered T liquidity input. At twenty or more days, issue the explicit hard veto. With no valid close in 250 trading days, return market_evidence_missing.

For a registry-listed cyclic secondary industry, require complete five-year observations. When both rolling ROE and rolling operating margin are at or above their individual five-year 80th-percentile tests, cap post-metric G and M at 80 and provide the lower of current profit and five-year median profit to valuation metric evaluation. Do not apply a cycle cap to an unlisted industry or infer the cyclic list from a name.

Evaluate redlines only from a frozen registry definition plus verified field evidence. Each outcome states its rule ID, evidence references, threshold, result kind (module_cap, pool_veto, or pending), and applied result. Hard vetoes cover ST or star-ST, delisting arrangement or forced-delist risk, non-positive net assets, qualified/adverse/disclaimer audit opinion, and twenty consecutive no-effective-trade days. Unresolved evidence conflict and unavailable source evidence are pending, not vetoes. A nonquantifiable major event remains an independent status or pool-prohibition path; only a registered, quantified, dated, verified event/calendar or liquidity measure may contribute to T's final 15 percent slot.

- [ ] **Step 4: Run policy, time, and market-contract tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_policy_engine tests.test_formal_time tests.test_formal_financial_features -v
~~~

Expected: PASS; date-only disclosures and stale-price rules remain distinct.

- [ ] **Step 5: Commit formal policy evaluation**

~~~powershell
git add -- ashare_pipeline/formal_policy_engine.py tests/test_formal_policy_engine.py
git commit -m "feat: add formal redline and cyclic policy engine"
~~~

### Task 5: Deterministic Strong and Wait Pool Selection

**Files:**
- Create: ashare_pipeline/formal_pool.py
- Create: tests/test_formal_pool.py

**Interfaces:**
- Produces PoolCandidate, PoolDecision, FormalPoolSelection, qualify_strong, qualify_wait, select_formal_pools, and canonical_formal_pool_counts.
- Consumes completed FormalScoreCard plus PolicyOutcome, frozen secondary industry, and security identity.
- Returns separate ordered strong and wait tuples, skipped-by-capacity records, and exactly the strong/wait canonical count mapping.

- [ ] **Step 1: Write the failing pool-selection tests**

~~~python
class FormalPoolTests(unittest.TestCase):
    def test_qualification_uses_exact_sc_b_c_dimension_and_t_thresholds(self):
        strong = candidate(sc=70, c=Decimal("0.75"), m=45, eq=45, fs=45, t=55)
        wait = candidate(b=65, c=Decimal("0.75"), m=45, eq=45, fs=45, t=54.999)
        self.assertTrue(qualify_strong(strong))
        self.assertTrue(qualify_wait(wait))
        self.assertFalse(qualify_wait(candidate(b=99, t=55)))

    def test_industry_cap_skips_and_continues_scanning_later_industries(self):
        candidates = [candidate(security_id=f"SZ0000{i:02}", industry="I1", sc=90-i) for i in range(5)]
        candidates += [candidate(security_id="BJ430001", industry="I2", sc=80)]
        selection = select_formal_pools(candidates, strong_capacity=20, strong_industry_cap=4)
        self.assertEqual([row.security_id for row in selection.strong], [
            "SZ000000", "SZ000001", "SZ000002", "SZ000003", "BJ430001",
        ])
        self.assertEqual(selection.strong_skipped[0].reason, "industry_cap_reached")

    def test_selection_is_ordered_and_mutually_exclusive_without_capacity_transfer(self):
        selection = select_formal_pools(permuted_candidates())
        self.assertEqual(selection.strong, tuple(sorted(selection.strong, key=strong_key)))
        self.assertFalse(set(ids(selection.strong)) & set(ids(selection.wait)))
        self.assertFalse(any(row.reason == "strong_capacity_not_transferred" for row in selection.wait))

    def test_pool_counts_use_only_canonical_keys(self):
        self.assertEqual(canonical_formal_pool_counts(strong=2, wait=3), {"strong": 2, "wait": 3})
~~~

- [ ] **Step 2: Run pool tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_pool -v
~~~

Expected: FAIL because ashare_pipeline.formal_pool does not exist.

- [ ] **Step 3: Implement qualification and scanning**

Strong eligibility is:

~~~text
Sc >= 70 AND C >= .75 AND M >= 45 AND EQ >= 45 AND FS >= 45
AND T >= 55 AND no hard veto AND no strong-pool-prohibited state
~~~

Wait eligibility is:

~~~text
B >= 65 AND C >= .75 AND M >= 45 AND EQ >= 45 AND FS >= 45
AND T < 55 AND no hard veto AND no wait-pool-prohibited state
~~~

Sort strong candidates by:

~~~text
Sc descending, C descending, R safety descending, security_id ascending
~~~

Sort wait candidates by:

~~~text
B descending, C descending, V descending, security_id ascending
~~~

Scan each eligible list in its own sorted order. Enforce the frozen secondary-industry cap before capacity: at most four strong and ten wait per industry, and at most twenty strong and fifty wait overall. On a capped industry, record an industry_cap_reached decision and continue scanning; never stop merely because a high-ranked industry candidate was skipped. Do not feed a strong candidate rejected for overall or industry capacity into wait selection. The qualification definitions already make T regimes disjoint; assert mutual exclusion anyway.

Every selected and skipped candidate includes its complete comparison key, secondary industry, running industry count, rule outcome, and evidence/score-hash references. canonical_formal_pool_counts emits only strong and wait. A legacy adapter, if later needed for dashboards, may read strong_attention/waiting_price but cannot be called from selection or persistence.

- [ ] **Step 4: Run pool, score, and policy suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_pool tests.test_formal_scoring tests.test_formal_policy_engine -v
~~~

Expected: PASS, including stable sorted order after input permutation.

- [ ] **Step 5: Commit pool selection**

~~~powershell
git add -- ashare_pipeline/formal_pool.py tests/test_formal_pool.py
git commit -m "feat: add deterministic formal pool selection"
~~~

### Task 6: Additive SQLite V7 Formal Scoring Persistence

**Files:**
- Modify: ashare_pipeline/state_store.py: schema constants, migration dispatcher, V7 DDL, and formal score APIs
- Modify: tests/test_state_store.py: V6 migration fixture and V7 persistence/invariant tests
- Create: tests/fixtures/schema_v6.sql

**Interfaces:**
- Produces StateStore.create_formal_score_run, put_formal_score_input_manifest, replace_formal_score_universe_statuses, list_formal_score_universe_statuses, put_formal_metric_score, put_formal_score_item, put_formal_policy_outcome, replace_formal_pool_memberships, mark_formal_score_run_preview_ready, mark_formal_score_run_blocked, and get_formal_score_run.
- Formal run states are building, preview_ready, validated, blocked, and published. Allowed transitions are building to preview_ready or blocked, preview_ready to validated or blocked, validated to published or blocked before any release is published, and no transition out of published. A retryable V8 validation failure preserves the current pre-publication state (preview_ready on initial validation or validated during post-begin revalidation) so it can be checked again after its external task/circuit condition clears; only a terminal validation failure may move it to blocked. The published transition belongs to the V8 release publisher and requires its validator manifest.
- Formal score persistence is append-only per input_hash; no update API overwrites an item belonging to a validated or published run.

- [ ] **Step 1: Write the failing V6-to-V7 migration and persistence tests**

~~~python
def test_v6_to_v7_migration_preserves_prior_formal_evidence_and_adds_score_tables(self):
    migrate_fixture("schema_v6.sql", self.db_path)
    store = StateStore(self.db_path)
    store.initialize()
    self.assertEqual(store.schema_version(), 7)
    self.assertEqual(store.get_formal_snapshot_count(), 1)
    self.assertTrue(store.has_table("formal_score_run"))

def test_formal_score_run_requires_hash_pinned_registry_and_unique_input_hash(self):
    run_id = self.store.create_formal_score_run(
        universe_snapshot_id=self.universe_id,
        freeze_at_utc=FORMAL_FREEZE_AT_CN,
        input_hash="a" * 64,
        evidence_manifest_hash="b" * 64,
        registry_manifest_hash="d" * 64,
        registry_approval_id="approved-fixture",
        registry_purpose="official",
        registry_hash="c" * 64,
        scoring_contract_version="formal-v3",
    )
    with self.assertRaisesRegex(ValueError, "input_hash"):
        self.store.create_formal_score_run(
            universe_snapshot_id=self.universe_id,
            freeze_at_utc=FORMAL_FREEZE_AT_CN,
            input_hash="a" * 64,
            evidence_manifest_hash="b" * 64,
            registry_manifest_hash="d" * 64,
            registry_approval_id="approved-fixture",
            registry_purpose="official",
            registry_hash="c" * 64,
            scoring_contract_version="formal-v3",
        )
    self.assertEqual(run_id, self.store.get_formal_score_run_by_input_hash("a" * 64)["id"])

def test_score_run_rejects_a_frozen_universe_from_a_different_root_manifest(self):
    with self.assertRaisesRegex(ValueError, "universe registry_manifest_hash"):
        self.store.create_formal_score_run(
            universe_snapshot_id=universe_snapshot_with_root("u" * 64),
            freeze_at_utc=FORMAL_FREEZE_AT_CN,
            input_hash="e" * 64,
            evidence_manifest_hash="f" * 64,
            registry_manifest_hash="r" * 64,
            registry_approval_id="approved-fixture",
            registry_purpose="official",
            registry_hash="s" * 64,
            scoring_contract_version="formal-v3",
        )

def test_preview_ready_score_rows_are_immutable(self):
    kwargs = valid_run_kwargs()
    run_id = self.store.create_formal_score_run(**kwargs)
    self.store.put_formal_score_input_manifest(run_id, complete_input_manifest(kwargs["input_hash"]))
    self.store.replace_formal_score_universe_statuses(run_id, full_run_decisions("pending_evidence"))
    self.store.mark_formal_score_run_preview_ready(run_id)
    with self.assertRaisesRegex(ValueError, "immutable"):
        self.store.put_formal_score_item(run_id, complete_item())

def test_run_bound_statuses_and_input_manifest_do_not_mutate_another_run(self):
    first = create_complete_building_run(self.store, self.universe_id, input_hash="a" * 64)
    self.store.put_formal_score_input_manifest(first, complete_input_manifest("a" * 64))
    self.store.replace_formal_score_universe_statuses(first, full_run_decisions("pending_evidence"))
    second = create_complete_building_run(self.store, self.universe_id, input_hash="b" * 64)
    self.store.put_formal_score_input_manifest(second, complete_input_manifest("b" * 64))
    self.store.replace_formal_score_universe_statuses(second, full_run_decisions("pool_vetoed"))
    self.assertEqual(
        self.store.list_formal_score_universe_statuses(first)["BJ430001"]["status"],
        "pending_evidence",
    )
    self.assertEqual(self.store.get_formal_score_input_manifest(first)["manifest_sha256"], "a" * 64)

def test_terminal_block_reason_is_canonical_and_cannot_be_replaced(self):
    run_id = self.store.create_formal_score_run(**valid_run_kwargs())
    reason = {"code": "unapproved_registry", "registry_manifest_hash": "m" * 64}
    self.store.mark_formal_score_run_blocked(run_id, reason)
    self.assertEqual(self.store.get_formal_score_run(run_id)["blocked_reason_json"], canonical_json(reason))
    self.store.mark_formal_score_run_blocked(run_id, reason)  # exact retry is idempotent
    with self.assertRaisesRegex(ValueError, "blocked reason"):
        self.store.mark_formal_score_run_blocked(run_id, {"code": "different_terminal_reason"})
~~~

- [ ] **Step 2: Run migration tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_v6_to_v7_migration_preserves_prior_formal_evidence_and_adds_score_tables -v
~~~

Expected: FAIL because schema V7 and formal score APIs do not exist.

- [ ] **Step 3: Implement V7 schema and immutable APIs**

Set SCHEMA_VERSION to 7 after V5/V6 are present. Add a contiguous _apply_v7_migration and extend initialize validation to accept exactly these complete ledgers:

~~~text
{2}
{2,3}
{2,3,4}
{2,3,4,5}
{2,3,4,5,6}
{2,3,4,5,6,7}
~~~

Add tables with these core columns:

~~~text
formal_score_run:
  id, universe_snapshot_id, freeze_at_utc, input_hash UNIQUE,
  evidence_manifest_hash, registry_manifest_hash, registry_approval_id,
  registry_purpose, registry_hash, scoring_contract_version,
  status, validation_manifest_hash, blocked_reason_json, created_at, updated_at

formal_score_input_manifest:
  run_id PRIMARY KEY, manifest_sha256, canonical_json, universe_hash,
  frozen_universe_input_hash, universe_registry_manifest_hash,
  trading_calendar_hash, registry_manifest_hash, selected_feature_inputs_json, selection_algorithm_version,
  capacities_json, industry_caps_json, refresh_generations_json, created_at

formal_score_universe_status:
  run_id, security_id, status, reasons_json, veto_flags_json, evidence_hash,
  feature_bundle_hash, context_hashes_json, policy_outcome_hash, score_hash, created_at
  PRIMARY KEY (run_id, security_id)

formal_metric_score:
  run_id, security_id, metric_id, raw_value, percentile, average_rank,
  peer_scope, peer_count, peer_security_ids_json, input_feature_hash,
  evidence_refs_json, created_at

formal_score_item:
  run_id, security_id, template_id, secondary_industry, primary_industry,
  dimensions_json, confidence_json, S0, Sc, Sbase, B, r_safety,
  risk_exposure, grades_json, feature_bundle_hash, score_hash, created_at

formal_policy_outcome:
  run_id, security_id, outcome_json, evidence_refs_json, outcome_hash, created_at

formal_pool_membership:
  run_id, pool_name, ordinal, security_id, decision,
  comparison_key_json, secondary_industry, industry_count_at_selection,
  reason, score_hash, policy_outcome_hash, created_at
~~~

Use CHECK constraints for pool_name limited to strong/wait, run-universe status limited to formal_scored/pending_evidence/pool_vetoed/out_of_scope, unique run/security/metric, unique run/security for score items, and unique run/pool/ordinal. All JSON fields use canonical serialization. Store exact Decimal strings, not binary floats.

create_formal_score_run first reads the referenced V5 formal_universe_snapshot and requires its registry_manifest_hash to exactly equal the supplied formal score-run registry_manifest_hash; it refuses an unavailable, unverified, or cross-root universe. put_formal_score_input_manifest stores the canonical complete input component list before score rows: sorted universe member IDs/hash, frozen_universe_input_hash, universe_registry_manifest_hash, trading calendar, each selected feature's exact input_hash and bundle_hash, selected fact/context/snapshot hashes, selected context refresh generations, all child registry hashes, capacities, industry caps, and selection algorithm version. It recomputes manifest_sha256 and requires it to equal formal_score_run.input_hash, rechecks that both recorded universe-root fields equal the linked V5 snapshot and the run root, and rejects a mismatch. replace_formal_score_universe_statuses requires exactly one row for every member of that run's frozen V5 universe snapshot and stores the score/policy/context/evidence hashes used for that run. It is immutable after preview_ready, validated, or published.

mark_formal_score_run_preview_ready requires a complete input manifest, full run-bound status ledger, and no incomplete write transaction. blocked_reason_json is null until a terminal block and then stores a canonical object with a stable code plus the exact source lineage or validation-manifest hash responsible for the block. mark_formal_score_run_blocked(run_id, reason) recomputes canonical JSON, allows only building, preview_ready, or validated to blocked, and requires null blocked_reason_json before its compare-and-set update; an already blocked run is a no-op only when the canonical reason bytes are identical. It rejects any call for a retryable validation result and any call after published. V7 deliberately has no public validated transition because its migration cannot inspect the future V8 formal_release_validation table; V8 adds mark_formal_score_run_validated only after it can prove a passed stored validation hash for the same run, then atomically stores it in validation_manifest_hash. V8 exposes mark_formal_score_run_published only as a public idempotence assertion after a matching V8 row is already published; it must reject a publishing intent and never perform a state transition. Only V8's private transaction-internal completion CAS may change validated to published, after the StateStore itself has verified the durable signed preparation and exact target tree. V7's preview/blocked methods and V8's validated/private-published transitions use compare-and-set expected source statuses and are idempotent only for identical target state and hashes.

Reject score/pool writes for a run not in building status and reject all writes once status is validated or published. Require metrics, policy, and score rows to reference the same frozen universe member, a verified V6 feature bundle returned by FormalFeatureRepository whose registry_manifest_hash equals the V7 run root, and verified V6 context facts returned by FormalContextRepository under that same root. Require registry_manifest_hash to reference the persisted V6 root manifest; registry_purpose must be official for an official candidate run and test for a test preview. Do not add foreign keys or conversion code from legacy score_run/score_item. V5 formal_universe_status remains collection-stage state only and must never be overwritten or read as a V7/V8 release classification.

- [ ] **Step 4: Run state-store migration and scoring regressions**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store tests.test_scoring -v
~~~

Expected: PASS; V1/V2 score persistence stays independent.

- [ ] **Step 5: Commit V7 persistence**

~~~powershell
git add -- ashare_pipeline/state_store.py tests/test_state_store.py tests/fixtures/schema_v6.sql
git commit -m "feat: persist formal V3 score runs"
~~~

### Task 7: Fail-Closed Offline Formal Score Runner

**Files:**
- Create: ashare_pipeline/formal_score_runner.py
- Create: tests/test_formal_score_runner.py
- Modify: ashare_pipeline/state_store.py: narrowly scoped formal-run lookup/status helpers only

**Interfaces:**
- Produces FormalScoreRunner.run_preview and FormalScoreRunner.rebuild_affected.
- Consumes a verified V5 universe snapshot, FormalFeatureRepository, FormalContextRepository, FormalRegistryBundleLoader, VerifiedRegistryBundle, FormalScoringRegistry, and StateStore.
- Produces V7 score and pool rows plus complete formal universe-status decisions; it does not publish a release or call legacy orchestrator._finalize.

- [ ] **Step 1: Write the failing runner tests**

~~~python
class FormalScoreRunnerTests(unittest.TestCase):
    def test_unapproved_registry_blocks_before_any_score_row_is_written(self):
        result = self.runner.run_preview(unapproved_registry_request())
        self.assertEqual(result.status, "blocked")
        self.assertEqual(self.store.list_formal_score_items(result.run_id), [])

    def test_tampered_feature_bundle_or_missing_context_is_pending_not_scored(self):
        result = self.runner.run_preview(fixture_request(tampered_bundle=True, missing_context_kind="industry_snapshot"))
        self.assertEqual(result.statuses["BJ430001"], "pending_evidence")
        self.assertIn("verified_context_missing", result.pending_reasons["BJ430001"])

    def test_peer_shortfall_and_missing_evidence_become_pending_universe_status(self):
        result = self.runner.run_preview(fixture_request(with_short_peer_and_missing_evidence=True))
        statuses = self.store.list_formal_score_universe_statuses(result.run_id)
        self.assertEqual(statuses["BJ430001"].status, "pending_evidence")
        self.assertIn("peer_count_below_20", statuses["BJ430001"].reasons)

    def test_complete_vetoed_member_can_keep_score_but_never_pool_membership(self):
        result = self.runner.run_preview(fixture_request(st_member=True))
        self.assertEqual(result.statuses["SZ000001"], "pool_vetoed")
        self.assertIsNotNone(self.store.get_formal_score_item(result.run_id, "SZ000001"))
        self.assertNotIn("SZ000001", pool_ids(self.store, result.run_id))

    def test_changed_metric_rebuilds_peer_closure_and_full_pool_selection_in_new_run(self):
        first = self.runner.run_preview(fixture_request())
        changed = self.runner.rebuild_affected(first.run_id, changed_snapshot_ids={"snap-SZ000001"})
        self.assertNotEqual(changed.run_id, first.run_id)
        self.assertIn("SZ000001", changed.rebuilt_security_ids)
        self.assertIn("BJ430001", changed.rebuilt_security_ids)

    def test_changed_context_rebuilds_context_dependents_and_peer_closure_in_new_run(self):
        first = self.runner.run_preview(fixture_request())
        changed = self.runner.rebuild_affected(
            first.run_id, changed_snapshot_ids=set(), changed_context_snapshot_ids={"ctx-SZ000001"}
        )
        self.assertNotEqual(changed.run_id, first.run_id)
        self.assertIn("SZ000001", changed.rebuilt_security_ids)
        self.assertIn("BJ430001", changed.rebuilt_security_ids)
        self.assertEqual(pool_ids(self.store, first.run_id), original_pool_ids(first.run_id))

    def test_corrected_financial_lineage_uses_new_feature_input_in_new_run_but_old_run_is_exact(self):
        first = self.runner.run_preview(fixture_request())
        old_feature_input = first.input_manifest.selected_feature_inputs["SZ000001"]
        insert_corrected_visible_fact_and_rebuild_feature("SZ000001")
        changed = self.runner.rebuild_affected(first.run_id, changed_snapshot_ids={"snap-corrected"})
        self.assertNotEqual(
            changed.input_manifest.selected_feature_inputs["SZ000001"],
            old_feature_input,
        )
        self.assertEqual(
            self.feature_repository.get_verified_formal_feature_bundle(
                input_hash=old_feature_input["input_hash"]
            ).input_hash,
            old_feature_input["input_hash"],
        )
~~~

- [ ] **Step 2: Run runner tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_score_runner -v
~~~

Expected: FAIL because ashare_pipeline.formal_score_runner does not exist.

- [ ] **Step 3: Implement isolated score-run orchestration**

run_preview first:

1. Loads the specified frozen universe and rejects duplicates, future evidence, missing collection-stage rows, active formal collection tasks, or a universe whose three persisted V5 source links, verified source-task receipts, extraction hashes, root registry manifest, and frozen-input hash do not exactly bind together. It requires that frozen universe registry_manifest_hash to equal the requested V7 scoring root before it creates a run.
2. Loads one VerifiedRegistryBundle through FormalRegistryBundleLoader using that same root hash and calls both registry_bundle.require_official and scoring_registry.require_official(registry_bundle) for an official request. A test registry/bundle may run only in test_preview mode and marks the result preview.
3. For each member of a new V7 run, selects its current typed bundle through FormalFeatureRepository.select_current_verified_formal_feature_bundle with the V7 run root and frozen industry, market-close, security-state, regulatory, event, and consensus facts through FormalContextRepository under that same root. It rechecks all stored hashes, manifest identity, source evidence, root identity, and freeze visibility before any metric is built. A prior run is inspected only via the exact feature input_hash recorded in its immutable input manifest; it must never silently resolve to a later correction.
4. Builds metric-level cohorts before score completion, calculates score cards for complete inputs, retains score cards for pool-vetoed members, and converts unresolved evidence/conflicts, history gaps, invalid cohorts, or invalid registry mappings to pending_evidence.
5. Applies pool selection only to scored, non-vetoed, state-permitted candidates. Writes a full immutable run-bound universe-decision ledger containing every frozen universe member exactly once; it never replaces the V5 collection-stage status ledger or another run's decision ledger.
6. Calculates input_hash from universe hash, frozen_universe_input_hash, universe registry manifest hash, verified trading-calendar hash, every selected feature input_hash/bundle_hash and evidence hash, the root registry manifest hash and every child registry hash, policy/status hashes, capacities, industry caps, source refresh generations, and selection-algorithm version. It rejects unless the two root hashes are equal. Persists the canonical complete component manifest whose SHA-256 equals input_hash before writing score rows.

The runner may create a preview_ready V7 run, but it must not mark it validated or published. If root approval or another pre-score invariant is terminally unavailable, it creates or reuses the same immutable candidate run and calls mark_formal_score_run_blocked with its canonical source-backed reason before writing score/pool rows. It may not call scoring.py, curation.py, orchestrator.py, legacy score tables, or legacy official_pool_counts. rebuild_affected accepts changed_snapshot_ids and changed_context_snapshot_ids, uses formal financial evidence/fact-to-feature and formal-context-to-score dependency references plus their authoritative refresh generations to create a new immutable V7 run. For an affected financial lineage it first requires the worker's new exact feature input bundle to be durable, then selects that current input; it never treats the earlier bundle as an error or overwrites the prior score run. It first finds direct bundle or context dependents, then expands to every member of every metric peer cohort whose percentile can change; it recalculates all pool-eligible candidates and the full deterministic pool scan because an affected score can alter ranking or industry-cap selection. A global context maps to every frozen universe member in sorted order; a security-scoped context maps only to its security before peer expansion. It may reuse byte-identical metric/score artifacts only where the dependency and peer-context hashes prove no change. It never updates a prior run or claims that only the directly changed security was recomputed when a peer or pool effect exists.

- [ ] **Step 4: Run focused formal integration suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_score_runner tests.test_formal_pool tests.test_formal_policy_engine tests.test_state_store -v
~~~

Expected: PASS; preview status remains visibly nonofficial.

- [ ] **Step 5: Commit score orchestration**

~~~powershell
git add -- ashare_pipeline/formal_score_runner.py ashare_pipeline/state_store.py tests/test_formal_score_runner.py
git commit -m "feat: add fail-closed formal score runner"
~~~

## Plan Self-Review

- Spec coverage: Task 1 freezes the V3 five-template policy contract and prevents unaudited production configuration. Tasks 2-3 cover metric-level peer eligibility, same-template industry fallback, midpoint percentiles, seven dimensions, C, S0, Sc, B, R safety, risk exposure, and grades. Task 4 implements cyclic peak protection, registry redlines, quantitative-event boundaries, market staleness, and hard vetoes. Task 5 implements both pool thresholds, stable sort keys, independent caps, industry scan behavior, and canonical count keys. Tasks 6-7 make the formal run append-only, point-in-time, incremental, fully classified, and separate from legacy scoring/finalization.
- Placeholder scan: every source file, table, public interface, rule outcome, persistence state, validation gate, fixture, and test command is named. The unavailable production registry is a fail-closed input requirement, not an unspecified calculation behavior.
- Type consistency: V6 FormalFeatureRepository returns a verified FormalFeatureBundle and FormalContextRepository returns verified market/industry/policy context under one VerifiedRegistryBundle; they feed MetricInput and PolicyEvidence. MetricScore feeds FormalScoreInput; FormalScoreCard plus PolicyOutcome feed PoolCandidate; score, policy, metric, and pool records share one immutable V7 run and frozen universe snapshot.
