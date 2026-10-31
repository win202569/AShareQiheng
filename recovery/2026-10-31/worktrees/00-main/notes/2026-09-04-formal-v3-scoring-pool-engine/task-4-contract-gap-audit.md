# Task 4 executable-contract gap audit

Read-only audit by policy_contract_gap_audit (gpt-6-astra/high), 2026-09-09. No implementation, tests, network or production policy approval. Parent independently read the named plan, registry and Context sections.

| Required behavior | Current support | Missing contract / authority |
| --- | --- | --- |
| Cyclic protection | Plan lines 487/489/491 fixes five FY, own-history 80th percentile, G/M cap 80; registry line 444 accepts only secondary_industries | Signed selectors for rolling ROE/margin, current profit and five-year series, periods/units/completeness; versioned quantile convention and affected valuation formulas as previously recorded. Schema is software design; production mappings/convention need explicit signed content. |
| Redlines | RedlineDefinition.rule is a Mapping (registry line 172), loader checks nonempty object (233) | Executable evidence selectors, comparator/threshold, cap target/value, prohibited pools, missing/conflict results and mandatory hard-veto coverage. Extra financial thresholds/mappings are not authorized by synthetic fixtures. |
| ST/retirement states | Context line 185 provides is_st/is_star_st/listing_status/forced_delist_risk; registry line 449 only checks references | Bind known fields to signed rules. Existing hard-veto categories are already approved; no new threshold is necessary. |
| Audit opinion / net assets | Regulatory Context line 208 exposes flag_id/active only | Signed audit-code/flag semantics and net-asset feature/period binding. Hard-veto semantics approved, production source correspondence not supplied. |
| Nonquantifiable major events | Event Context line 213 requires a numeric quantified_value | Choose explicitly authorized regulatory flag binding or versioned schema. Software route is design work; major-event classification and one/both-pool prohibition mappings need production policy approval. |
| No valid close in 250 days | Plan line 471 permits None, Context lines 174-175 require positive close and valid date | Authenticated representation of no valid close over a proven 250-trading-day window. Do not map absent/corrupt transport data to confirmed no close. |
| Effective trade / staleness | Context line 179 does not enforce positive volume AND turnover; market rule (registry 456) is arbitrary object | Recompute/enforce the approved effective-trade formula, bind trading-day count evidence and signed stale-state -> T liquidity mapping; no unregistered T adjustment. |
| Policy proof and outcomes | Plan 412 names input interfaces and 479 names result fields | Same-root/freeze/current-input closure, precise missing/conflict representation and sealed result authority. Plain caller booleans/dicts are not evidence. |

Conclusion: software contract structure and already-approved constants can be developed, but current registry bodies cannot directly execute complete Task 4. Production financial equivalences and any additional policy contents require separate signed approval. This audit neither selects a production quantile convention nor authorizes source/registry changes. Task 3B remains a pre-policy intermediate.

Parent sequencing: finish/review/verify Task 3B; then resolve a bounded versioned policy contract before its implementation. Do not silently reinterpret legacy Context bytes or the v1 raw metric adapter. The earlier whole-cohort valuation normalization ruling remains binding.

Additional integration requirement (parent): a policy-adjusted valuation slot must bind its newly contributing current/five-year financial evidence and source precision, not merely the old raw feature's refs. Recompute slot temporal reliability/global P and confidence from the final authenticated slot set before final aggregates. A pre-policy C cache cannot establish final confidence when normalized-profit evidence changed. This follows the approved confidence minimum-evidence rule; no formula or policy value is changed.
