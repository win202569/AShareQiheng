# Task 3B — Authenticated PRE-POLICY score arithmetic

COMPLETE: local commit853b9321754f3957f600327ae884fc1cd767e755, reviewed after2fix rounds and verified; details in progress.md and appended report. Do not redispatch. Original BASE: a2cc2ce3d43d9f51d366464013739179d68bcb36; Task3A2 was already reviewed,39parent tests and committed.
Worktree D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation; codex/formal-v3-implementation.
Authority: approved Task 3 arithmetic and spec sections 6.2, 7.2, 7.4 (reproduced below); task-3b-preflight.md records the Task 4 integration ruling.

## Scope and stage
Create only ashare_pipeline/formal_scoring.py and tests/test_formal_scoring.py. Reuse existing genuine ScoreFixture without modifying it unless a concrete missing test capability is reported first. No registry, input-factory, metric-engine, policy, pools, runner, persistence, legacy, data or JSON fixture changes.
Produce one sealed PrePolicyScoreCalculation with calculate_pre_policy_score(score_input), and a pure grade_for_score(Decimal). Public math helpers may return visibly untrusted arithmetic data only; no raw dict/score/confidence/evidence/override can mint this proof.
Use schema_version formal-pre-policy-score-v1 and calculation_stage pre_policy, policy_final false. Do NOT create FormalScoreCard or expose a pool-consumable final score type. Task 4 must first rebuild policy-adjusted whole valuation cohorts and apply module caps before final cards exist. This slice computes the approved raw arithmetic only, never normalized-profit substitutions, policy thresholds, caps, vetoes or pool eligibility.

## Input and descendant authenticity
Accept exact genuine FormalScoreInput only, not a batch, MetricScore, legacy/public feature value, copy, subclass, dict, None or arbitrary override. Consume its sealed immutable fields; no caller registry or alternative source.
Capture the genuine input verification/canonical/field methods including inherited resolution and reject method/module/class replacement. Recheck at calculation start/end and on every result field/read/verification. Calculation helpers, Decimal context, serialization and hash helpers used as authority must also remain captured and authentic; no substitution minting.
No exported raw capability list is needed: the result's private record holds a strong reference to its genuine source input and invokes captured genuine verification/canonical methods on every access. Source revocation must revoke the descendant even when it was computed during tentative outer publication. A copied one-time true flag is insufficient.
Private weak result registration + strong source ownership is acyclic: the source never points to the descendant. Successful detached results remain valid after repository/batch references are released. No public construction or mutation; require_verified(), canonical_bytes(), detached to_dict() plus immutable nested fields. Public serialization cannot restore proof authority. Prepare complete arithmetic/canonical payload before minting and revalidate input/source bytes immediately before return. No persistence/writer fence is added to pure arithmetic.

## Exact input fields
Source exposes slots[mid] with dimension-qualified metric_id, definition, dimension_weight, internal_weight, value (Decimal), temporal_quality (Decimal), evidence_kind, metric_score, evidence_refs, full_feature_values, context_fact, registered_rule.
Source has continuous_fy_count (4 or 5 for ready), confidence_cap (None or Decimal .90), cyclic, history_endpoints, comparable_quarter_keys, full_feature_bundle/full_feature_bundle_hash and consensus_context/rule.
Root/input bindings: input_hash, batch_hash, metric_batch_hash, registry_manifest_hash, registry_hashes, frozen_input_hash, universe_hash, population_hash, security_id, template_id, as_of_utc.
All 25 slots required, exact signed definition/internal/dimension weights retained; M.return_persistence differs from CA.return_persistence. Do not remove a slot, reweight because of missing evidence, infer a missing year, or accept caller D/P/H/K. Invalid purported input should fail, not produce partial arithmetic.
Retain the complete source canonical payload and its SHA256 plus all identity bindings in output so an audit can recompute without a live repository. Do not trust a to_dict reconstruction as a new input.

## Deterministic Decimal contract
Use the existing fixed context equivalent to formal_metric_engine._arithmetic_context: precision 50, ROUND_HALF_EVEN, Emin=-999999, Emax=999999, capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow]. Ignore ambient getcontext/DefaultContext; no binary floats. Preserve specified operation order. Store/compare unquantized Decimal strings. No display rounding in this task.

Dimension order G,V,M,EQ,FS,CA,T, weights .18,.18,.18,.12,.08,.16,.10.
For each dimension, sum signed internal_weight * slot.value. Internal weights total 1; no missing-slot redistribution.
Global q_i=(dimension_weight * internal_weight)/sum(all 25 products).
D=sum(q_i for verified slots), required 1; K=1 only because genuine input proves a single consistent complete mapping/root.
P=sum(q_i*slot.temporal_quality), where quality is already min actual evidence refs; validate/retain underlying refs from source, not caller quality.
H=min(continuous_fy_count/5,1); must be >=.8.
C=.60+.40*(.30D+.25P+.25H+.20K); apply actual registered confidence_cap last.
Actual registered no-coverage expectation value is 50, counts as verified for D, and caps C at .90. It is not a fabricated raw metric or peer member.

S0=.18G+.18V+.18M+.12EQ+.08FS+.16CA+.10T
Sc=50+C*(S0-50)
Sbase=(.18G+.18V+.18M+.12EQ+.08FS+.16CA)/.90
B=50+C*(Sbase-50)
M_persistence=(.40*M.return_persistence+.30*M.margin_persistence)/.70
CA_downside=(.20*CA.shareholder_return_and_dilution+.15*CA.capital_discipline)/.35
R_safety=.40FS+.25EQ+.20M_persistence+.15CA_downside
risk_exposure=100-R_safety

Exact signed components are M.return_persistence, M.margin_persistence, CA.shareholder_return_and_dilution and CA.capital_discipline (formal_scoring_registry.py METRIC_IDS). Never select a same-named different dimension.
Output immutable dimensions, global slot weights, confidence D/P/H/K/C, S0/Sc/Sbase/B, both risk subcomponents, R_safety and risk_exposure, grades computed on unrounded values and full source audit. These remain pre-policy values. Grade the seven higher-is-better dimensions, S0/Sc/Sbase/B and R_safety. Do not apply the positive grade scale to risk_exposure (higher is worse) or to unit-interval confidence; preserve those as clearly named raw values.
Pure grade_for_score accepts exact finite Decimal in [0,100], rejects floats/bools/nonfinite/out-of-range. >=90 A+, >=80 A, >=70 B, >=60 C, >=50 D, else E. No rounding before comparison.

## Exact arithmetic evidence / tests
Hand example (pure mathematical test only; never forge FormalScoreInput): G80 V70 M60 EQ50 FS40 CA90 T30 C1; M-return70 M-margin50 CA-shareholder60 CA-discipline80:
S0=Sc=64.4
Sbase=B=68.222222222222222222222222222222222222222222222222
R_safety=51.071428571428571428571428571428571428571428571428
risk_exposure=48.928571428571428571428571428571428571428571428572
These follow the specified intermediate divisions; direct simplified ideal 715/14 yields a different last digit and is not the prescribed arithmetic.
Pure C examples: H.8/P.8 -> .96; H.8/P1 -> .98; H1/P.8 -> .98; H1/P1 ->1; actual neutral cap ->.90. With only the expectation slot date-only, q=.025, P=.995, H=.8 gives uncapped C=.9795 then actual neutral cap .90 (parent executed under the fixed context).
Test all grade boundaries and adjacent unrounded values, negative/over100/nonfinite/non-Decimal, and hostile ambient context settings.
Real integration: use genuine full universe default linked ScoreFixture with focal BJ430001 and actual covered consensus receipt (not linked=False); normal 4FY timestamp input gives H=.8, P=1, C=.98, all 25 source slots and 7 dimensions. This closes Task 3A2 review's deferred minor: exercise actual linked covered -> complete ready input success. Cyclic five-FY source gives H=1; keep result explicitly pre-policy. Actual no-coverage consensus permits separate neutral50 and cap. date_only=True affects only consensus, not ordinary financial source precision, so compute P from actual q_i and that single .8 slot rather than claiming P=.8.
Use at most two expensive source-backed fixture integrations, combine compatible assertions per fixture. Pure math/selector/construction checks should not rebuild 22-member persisted graphs repeatedly. Existing fixtures must remain byte-sensitive genuine source/SQL/registry proof; no fake provenance or always-true verifier.
Test construction/copy/mutation/forged/legacy/cross-input rejection, detached immutable audit/hash determinism, method/helper substitution and dependency restoration, and descendant revocation after a genuinely leaked tentative source fails its outer guard. Capture profiling only while strictly needed; scope the callback and reuse fixture within the same test. Never weaken production guards for speed.
Report exact RED before implementation, final focused GREEN command/output/duration, file hashes, public schema/API and concerns. Parent separately reviews and verifies. No full existing metric/feature suites by worker.

## Agent constraints
No subagents, Git/index writes, commits, live network, production policy signing, data changes or cleanup of existing paths. Use apply_patch for edits. All tests offline synthetic with genuine byte-sensitive signing/receipts, not actual production approvals.
Read TDD and verification skills. Start RED with meaningful pure arithmetic/constructor tests for the missing module; do not first build expensive fixtures merely to fail on an absent import. Add genuine integration assertions and verify them before handoff. Stop only for concrete missing scope/authority; do not silently change input/policy contracts. Parent owns review and code-only commit.
Report .superpowers/sdd/2026-09-04-formal-v3-scoring-pool-engine/task-3b-report.md; freeze source after report and return concise status/tests/concerns.

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
