# Task 3B preflight — arithmetic and policy boundary

Not an implementation dispatch. Task 3A2 complete-input factory is active. Freeze actual proof API and review/commit before dispatching arithmetic.

## Arithmetic requirements already verified

- Reuse Task 2C exact Decimal context: precision 50, ROUND_HALF_EVEN, explicit exponents/traps/flags. Preserve formula operation order and compare/store unrounded values; display quantization is separate.
- Hand example G80,V70,M60,EQ50,FS40,CA90,T30,C1 with M-return70/M-margin50/CA-shareholder60/CA-discipline80: S0=64.4; Sc=64.4; Sbase=B=68.222222222222222222222222222222222222222222222222; R_safety=51.071428571428571428571428571428571428571428571428; risk_exposure=48.928571428571428571428571428571428571428571428572. These were executed under actual context, not guessed from reduced ideal fractions; direct 715/14 rounding ends differently by one ULP.
- C uses actual globally normalized q_i=dimension_weight*internal_weight. D=1 and K=1 are qualification requirements, not caller-supplied constants that bless missing evidence. P is each actual slot's minimum evidence temporal quality, H is actual backward-contiguous FY count/5 capped1. No-coverage registered subscore counts as verified D and caps C at .90 after the normal formula.
- Useful exact ordinary C expectations: H=.8/P=.8 -> .96; H=.8/P=1 -> .98; H=1/P=.8 -> .98; H=1/P=1 ->1. With verified no-coverage every current strict eligible example caps to .90.
- There are 25 slots and equal-leaf IDs remain dimension-qualified. Normal weights are unchanged across all five templates.
- Mathematical helpers for hand examples must be clearly separate from proof-bearing ready-input/card construction. Arbitrary dimensions/confidence/slot objects must never mint an official or policy-final scorecard.
- Grade thresholds: >=90 A+, >=80 A, >=70 B, >=60 C, >=50 D, else E, over finite exact Decimal in [0,100]. No display rounding at boundaries.

## Newly named Task 3B ↔ Task 4 integration risk

Task 4 requires module caps after metric aggregation and a lower current/five-year-median profit base BEFORE valuation metric evaluation. Task 2C currently accepts only signed feature adapters and calculates a complete cohort from those authenticated raw features; 3A2 therefore prepares pre-policy verified metrics, not automatically policy-adjusted valuation percentiles. A post-hoc score scalar override would violate same-root evidence, immutable metric identities and cohort completeness.

Need explicit staged contract before Task 3B dispatch:
- Decide whether Task 3B produces an auditable pre-policy calculation object or a card explicitly marked not policy-final; never present it as a final formal/pool score merely because all arithmetic ran.
- Final cards/pools must require same-input, same-root policy proof and recomputation of capped dimensions/totals; no user-provided final caps or score dictionaries.
- If policy changes raw valuation metric values, rebuild the affected full-universe cohorts under a versioned signed adapter and bind both original and adjusted identities. Do not silently replace a percentile after ranking, drop peer members, or reuse unrelated pre-policy peer ranks.
- Quantile convention and actual policy evidence field links must be explicit signed contracts; do not choose production economic thresholds or source equivalence from arbitrary fixture data. The existing fixture policy rules are not production financial policy authority.

Independent score_input_boundary_preflight agrees: current raw-value assignment and immutable cohort caches cannot accept a later profit override, and a changed cyclic valuation value can change noncyclic peer ranks. Existing signed cyclic rule only carries secondary_industries, not executable peak quantile convention or valuation mappings. These are prerequisites for the policy-adjusted adapter, not permission to invent production policy values.

Ruling for Task 3B dispatch: produce an explicitly pre-policy arithmetic intermediate over genuine FormalScoreInput, not a policy-final FormalScoreCard or a pool-consumable object. Implement the approved arithmetic now; defer final card construction until authenticated policy-adjusted metric cohorts and module caps are integrated. Preserve current adapter semantics and all raw identities; no post-hoc V percentile override. Cost if wrong: a renamed/staged arithmetic interface, not a misleading final financial score.

No Task 4 code or production policy values are authorized by this draft. A future signed policy contract must name its executable quantile convention and valuation formulas; actual production approval remains distinct from synthetic software fixtures.
