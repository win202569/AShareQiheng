# Residual Feature-Ready Fix Round 1 Re-review

## Review boundary and method

- Fix base: `13aea24636744490115f21b78bd696fd538f6400`
- Fix head: `c799531f8a8a2173c5557db4d1d9afaf6ebd464e`
- Frozen package: `review-13aea24..c799531.diff`, opened exactly once and used as the complete change boundary.
- Re-read the required reviewer skills, the prior independent review, and the Fix round 1 section of `residual-feature-ready-report.md`.
- Inspected the package-referenced current contract/schema/builder/test regions and the existing unmapped share-repurchase declaration.
- Did not run git, network, runtime data, the tracked runtime database, broad/full suites, or a fresh probe. No concrete unresolved suspicion remained after static line-level verification that warranted a probe.

## Assessment

**All findings addressed.**

**APPROVED**

- Critical: 0
- Important: 0
- Minor: 0
- Ready to merge: **Yes**

The prior Important is closed. A registered raw slot is no longer inferred from a mutable three-part key plus an observed/derived state. The validator and builder now share an immutable schema-owned descriptor that binds each raw slot to its canonical dimension, observed-only status, active mapping version, unit, allowed source fields, single evidence record, and unique fact identity. The original derived-retag payload and its adjacent substitution variants fail before normal file/DB/progress handling.

## Strengths

- The fix moves duplicated raw-dimension/unit knowledge out of `financial_features.py` and derives ordinary descriptors from the existing field mapping authority in `financial_schema.py:92-131,176-187`.
- The validator consumes the same resolver at runtime (`feature_contract.py:389-391,473-508`) while template applicability and seven-period authority remain separately owned by the registry and feature contract.
- The regression matrix starts from the real production builder and varies dimension, status, formula metadata, and cross-slot observed substitution rather than reproducing the validator implementation (`tests/test_feature_contract.py:52-94,320-334`).
- The negative integration regression records the former accepted write/persist/verified-read/progress behavior in RED and checks real isolated state after GREEN (`tests/test_orchestrator.py:1147-1201`).
- The change remains limited to three production modules and three focused test modules; no scoring, pools, migration, runtime data, or network path changed.

## Issues

### Critical

None.

### Important

None.

### Minor

None.

## Required verdicts

### 1. Prior Important: renamed derived value filling a registered raw slot — **ADDRESSED**

The exact prior counterexample removed `g.revenue.FY2021` and renamed derived `m.gross_profit.FY2021` into the missing slot.

- In the wrong-dimension form, `feature_contract.py:495-497` rejects `M` because the revenue descriptor requires `G`.
- In the canonical-dimension form, `feature_contract.py:498` rejects `derived` because raw descriptors permit only `observed`.
- The builder creates raw values from the descriptor at `financial_features.py:578-596`, so the accepted canonical representation and the validator's expected representation are aligned.
- The new public regression covers both same-dimension and cross-dimension derived substitutions at `tests/test_feature_contract.py:60-75,320-334`.

The original Important no longer crosses `FeatureBundle.from_dict()`/`validate()`, and therefore cannot enter the normal writer, StateStore, verified-read, or progress path.

### 2. Authoritative descriptor, producer/validator reuse, and imports — **ADDRESSED**

- `RawFinancialSlotDescriptor` is defined and validated only in `financial_schema.py:140-161`.
- Descriptors for mapped facts are generated directly from `_FIELD_RULES` at `financial_schema.py:176-187`; dimension derivation is centralized at lines 164-173.
- `financial_features.py:578-596,931-945` resolves the descriptor for both observed-value creation and registered-slot assembly. The former duplicate `_RAW_DIMENSION` and `_EXPECTED_UNITS` tables are removed.
- `FeatureBundle.validate()` resolves the same descriptor at runtime (`feature_contract.py:389-391,473-508`). It does not copy raw slot metadata.
- Template applicability remains sourced from `TEMPLATES`; period applicability remains sourced from `FINANCIAL_PERIOD_KEYS`.

There is no module-load cycle. `financial_schema` continues to import feature-contract constants/helpers at module load (`financial_schema.py:11-15`), while the reverse dependency is inside `FeatureBundle.validate()` only. `feature_contract` finishes loading before validation can runtime-import the schema, and `financial_features` consumes both completed modules in the existing direction.

### 3. Canonical raw metadata and the five RED substitution classes — **ADDRESSED**

For a candidate value to satisfy a registered raw slot, `feature_contract.py:486-508` now requires:

- a recognized registered metric and one of the seven bound periods;
- the descriptor's canonical dimension and exact canonical key;
- an allowed status, which is exactly `observed` for raw facts;
- the active mapping/formula version;
- the descriptor unit;
- exactly one evidence record;
- an allowed canonical source field.

The collected raw evidence fact IDs must also be globally unique across all required raw slot-periods (`feature_contract.py:509-516`). Consequently:

1. cross-dimension derived retag fails dimension/status;
2. same-dimension derived retag fails observed-only status;
3. wrong-dimension observed retag fails canonical dimension/key;
4. observed data with derived-formula metadata fails mapping/formula version;
5. a cloned/renamed observed raw slot fails source-field authority, and an otherwise relabeled clone cannot satisfy two required slots with one fact ID.

The old structural constraints remain intact:

- `DimensionInput` rejects duplicate `(key, period_key)` entries at `feature_contract.py:219-221`;
- duplicate recognized slot-periods fail the list-length versus set/cardinality check at `feature_contract.py:509-513`;
- wrong-period or malformed replacement keys are not counted at `feature_contract.py:486-493`, leaving the required Cartesian product incomplete at lines 510-516;
- the expected set still comes from every registered descriptor across every `FINANCIAL_PERIOD_KEY` at lines 477-480.

The public format contains evidence references rather than full `FinancialFact` documents, so the parser appropriately validates the canonical metadata and uniqueness available at this boundary without copying builder logic or pretending to recompute a fact ID from absent fields.

### 4. Synthetic/future `share_repurchase_cash` descriptor — **ADDRESSED / COMPATIBLE**

- The explicit declaration that this fact is not mapped from current tracked Eastmoney inputs remains unchanged at `financial_schema.py:133-137` as `source_field_unavailable`.
- `share_repurchase_cash` remains absent from `_FIELD_RULES` (`financial_schema.py:92-131`). Production extraction iterates those field rules, so the new descriptor cannot manufacture an online fact.
- The explicit descriptor at `financial_schema.py:188-198` supplies a narrow future/auditable field identity only for canonical validation and for the existing synthetic complete-bundle test contract.
- The test fact helper now obtains that exact descriptor source field (`tests/test_financial_features.py:73-97`), preserving valid general-ready fixtures without adding the field to online normalization.
- When production facts do not contain this currently unavailable metric, assembly still emits the existing missing slot at `financial_features.py:937-943`; it does not synthesize an observed value.

This is consistent with the existing registry choice to retain the future slot while explicitly marking the current source mapping unavailable.

### 5. Compatibility and real boundaries — **PRESERVED**

- Valid `general_nonfinancial` construction and canonical parse use the same descriptors; the existing real positive path remains at `tests/test_orchestrator.py:1203` onward.
- Specialized/unclassified status and blocker logic is untouched in `feature_contract.py:437-456` and in the builder.
- Financial readiness still inspects only `G/M/EQ/FS/CA`; `V/T` remain outside this gate at `feature_contract.py:458-468`.
- The new negative real-boundary test calls the public parser first, then would use the real writer, StateStore, verified reader, and status/progress if the forged payload were accepted (`tests/test_orchestrator.py:1147-1201`). Its RED evidence in the implementation report confirms that the same payload formerly crossed and was counted ready; GREEN asserts no DB row, no feature JSON, and zero financial-ready count.
- The positive and negative real paths continue to assert `formal_score_ready=false`, `seven_dimension_ready=false`, and zero waiting-price/strong-attention pool counts.

The implementation report records focused GREEN (`Ran 2`, OK), focused contract/schema/builder plus real-boundary GREEN (`Ran 88`, OK), required related modules (`Ran 252`, OK), and full discovery (`Ran 357`, OK). Those are implementation evidence, not fresh commands from this re-review.

### 6. New Critical/Important regressions — **NONE FOUND**

- Descriptor metadata matches the removed builder tables: revenue maps to `G`, other income facts to `M`, operating cash flow to `EQ`, remaining cash-flow facts to `CA`, and balance facts to `FS` (`financial_schema.py:164-173`).
- Units and source fields are derived from the same `FieldRule` used by normalization.
- Unknown future template slots now fail closed through `raw_financial_slot_descriptor()` rather than silently defaulting to `FS/CNY` (`financial_schema.py:201-206`).
- The runtime import is narrow and cycle-safe.
- No changed path opens formal scoring, seven-dimension readiness, either official pool, network behavior, runtime data, migrations, or any deferred Minor item.

## Final verdict

**All findings addressed.**

**APPROVED**

The Fix round 1 package closes the prior Important at the public contract and real persistence/progress boundaries without introducing a new Critical or Important issue.
