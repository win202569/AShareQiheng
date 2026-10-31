# Residual Feature-Ready Independent Review

## Review boundary and method

- Baseline: `38037273f4710f4b70cc684884a51502607c1d09`
- Head: `13aea24636744490115f21b78bd696fd538f6400`
- Frozen boundary: `review-3803727..13aea24.diff`, opened exactly once and treated as the complete change set.
- Reviewed the residual brief, prior final-fix re-review, implementation report, changed production/test regions, the registered template definitions, the builder's canonical raw-value construction, and the binding design paragraphs for periods/readiness.
- No git commands, network, runtime data, tracked runtime database, broad/full suite, or fresh probe were run in this review.

## Assessment

**Findings remain open.**

- Critical: 0
- Important: 1
- Minor: 0
- Ready to merge: **No**

The straightforward missing-container/value attacks and the bare raw-slot deletion are rejected, and the real positive persistence path is well exercised. However, the new slot-completeness check identifies a registered raw slot only from a mutable feature key plus `observed/derived` status. A derived feature can therefore be renamed into the missing registered slot and restore the validator's set/count without restoring the raw input. Because persistence, verified reads, and progress all trust this same validator, the target public-boundary integrity defect remains open.

## Strengths

- `ashare_pipeline/feature_contract.py:16-26` centralizes the five financial dimensions and seven financial periods; `ashare_pipeline/financial_features.py:54` consumes the same period tuple, avoiding period-list drift.
- `ashare_pipeline/feature_contract.py:441-447` applies the specialized-template rule through registry metadata instead of a copied template-ID list.
- `tests/test_feature_contract.py:225-273` covers all five financial containers and both missing/blocked container/value states, plus a direct raw-slot omission.
- `tests/test_orchestrator.py:1088-1186` uses real `StateStore`, canonical file writing, verified reading, and status/progress behavior for the simple forged-negative and valid-positive paths; it does not mirror SQL to decide readiness.
- The production diff is small and does not touch scoring, pool selection, network behavior, migrations, runtime data, or the three deferred Minor items.

## Issues

### Important

#### 1. A renamed derived feature can satisfy a missing registered raw slot

- File: `ashare_pipeline/feature_contract.py:477-489`
- Related canonical producer: `ashare_pipeline/financial_features.py:607-618`, `ashare_pipeline/financial_features.py:659-680`, `ashare_pipeline/financial_features.py:935-969`
- Missing regression: `tests/test_feature_contract.py:264-273`, `tests/test_orchestrator.py:1088-1144`

`supplied_slot_periods` accepts a value whenever:

1. its three key segments have a dimension prefix matching the container;
2. the middle segment names any registered template slot;
3. the suffix matches a required `period_key`; and
4. its status is either `observed` or `derived`.

This does not establish that the value is the builder's canonical raw slot. The registry contains raw fact slots, while the real builder emits those values via `_observed_value()` in their `_RAW_DIMENSION` container with the mapping formula version. Derived formulas are separate values produced by `_derived_value()`.

A deterministic counterexample starting from the real valid `general_nonfinancial` builder output is:

1. Remove `g.revenue.FY2021` from `G`.
2. In `M`, rename the existing derived `m.gross_profit.FY2021` to `m.revenue.FY2021`, leaving its status as `derived`, period as `FY2021`, and its valid derived evidence/formula metadata intact.
3. Keep the self-declared coverage/completeness at `1.0` and status at `financial_ready`.

The raw revenue slot is absent, but lines 480-489 count the renamed derived value as `("revenue", "FY2021")`. The number of counted pairs remains equal to the registered set size and the set remains complete, so lines 490-497 do not distinguish this payload from a genuine raw-complete bundle. This also demonstrates that canonical dimension assignment is not enforced: the real builder places `revenue` in `G`, while the validator accepts it in `M` as long as the key prefix is changed to `m`.

Why it matters: this is not only a parser-shape issue. `StateStore.put_feature_bundle()` reuses `FeatureBundle.validate`; `write_feature_bundle()` performs the same public canonical parse; verified reads accept that same contract; and progress trusts the verified bundle/header status. A hash-consistent payload of the form above can therefore follow the normal file/DB path and be counted as `financial_ready`. The new real-boundary regression proves rejection only for a bare deletion, so it does not exercise this accepted replacement attack.

Minimal fix: define the expected canonical registered-slot descriptors from one authoritative, runtime-safe source, including at least `(slot, period, canonical dimension, slot kind/allowed status)`. For the current registry, whose `financial_slots` are raw fact slots, require the exact builder-compatible raw value (`status="observed"`, canonical dimension/key/period, and appropriate raw mapping metadata) exactly once. If future templates register derived slots, declare that explicitly in registry metadata rather than treating every derived feature whose key was renamed as a raw slot. Add focused public-parse and real write/persistence/progress regressions using the derived-retag counterexample above.

## Required verdicts

### 1. Financial dimension/value readiness and V/T exclusion — **ADDRESSED**

- `ashare_pipeline/feature_contract.py:457-470` restricts the check to `G/M/EQ/FS/CA`.
- A financial-ready bundle rejects financial containers whose status is not `input_ready` or `not_applicable`, which covers missing, blocked, and partial containers.
- It rejects existing financial values with `missing` or `blocked` status.
- `V` and `T` are not included in `FINANCIAL_DIMENSIONS`, so their current missing containers do not incorrectly block financial readiness.
- The test matrix at `tests/test_feature_contract.py:225-262` covers both states for every financial dimension.

### 2. Registered slot × seven-period completeness and omission resistance — **NOT ADDRESSED (Important)**

- Period authority is correct: the expected Cartesian product is derived from the selected registry template and all seven `FINANCIAL_PERIOD_KEYS` at `ashare_pipeline/feature_contract.py:472-476`.
- A bare deletion such as `g.revenue.FY2021` is rejected, and duplicate counted pairs cause the list-length check to fail. Extra-dot/malformed key shapes are not counted because exactly three segments are required.
- Nevertheless, the derived-retag path above restores the same tuple set/count without restoring the raw slot. The check is therefore not yet a genuine raw-slot completeness check and is not fully aligned with the real builder's canonical dimension/status metadata.

### 3. Specialized classified templates and unclassified semantics — **ADDRESSED**

- The rule at `ashare_pipeline/feature_contract.py:436-447` is metadata-driven and therefore covers all classified `specialized_inputs_required` templates: `bank`, `insurance`, `broker`, `real_estate_high_leverage`, and `resource_cycle`.
- Each can only validate with `financial_status="blocked"` and `specialized_financial_inputs_missing` present.
- `unclassified` remains outside that specialized blocker rule, continues to be rejected as `financial_ready` at lines 448-456, and the existing builder keeps its dedicated `industry_template_unclassified` blocker. The diff does not replace that dedicated producer behavior with the specialized blocker.
- Tests cover the distinct implementation shapes (zero-slot bank and common-slot real-estate/resource templates); insurance and broker use the same generic zero-slot registry path as bank.

### 4. Valid ready compatibility, registry/period authority, and imports — **ADDRESSED**

- The valid `general_nonfinancial` bundle survives public canonical round-trip and the real write/read/persistence/progress path.
- `utility` and `rd_growth` share the same registered slot tuple and the same generic builder/validator path as `general_nonfinancial`; no template-specific rejection was added for them.
- `TEMPLATES` is imported inside `FeatureBundle.validate()`, so module loading remains safe. `financial_features.py` imports `FINANCIAL_PERIODS` from the contract; the contract does not import `financial_features`.
- The registry remains the source of template slots/specialization, and `FINANCIAL_PERIODS` is the shared single source for the seven bound periods.

### 5. Real forged and positive storage/progress regressions — **PARTIALLY ADDRESSED**

- `tests/test_orchestrator.py:1088-1144` is a real negative boundary test: it starts with a production-built ready bundle, mutates it, calls the production `StateStore` and file writer, checks the actual isolated DB/file state, and calls real status/progress. Rejection occurs before a feature-set row or final JSON is committed for the bare-deletion attack.
- `tests/test_orchestrator.py:1146-1186` is a real positive path through parse, file write, DB persistence, verified read, and progress.
- It is not a mirror validator/SQL test. Its limitation is attack coverage: the accepted derived-retag attack is not exercised, so the same real path remains open to that payload.

### 6. Deferred readiness gates and scope guardrails — **ADDRESSED**

- The frozen package changes only `feature_contract.py`, `financial_features.py`, and focused tests.
- No formal score, seven-dimension readiness, waiting-price/strong-attention selection, runtime data, network behavior, migrations, or runtime database is changed.
- The positive and negative real-path tests explicitly assert `formal_score_ready=false`, `seven_dimension_ready=false`, and both official pool counts at zero.
- The three deferred Minor findings remain untouched.

### 7. Test signal and production minimality — **NOT ADDRESSED because of Important #1**

- The tests otherwise use production-built bundles and real producer/consumer boundaries, and the production change is appropriately small.
- The slot-omission test is too narrow: it checks deletion only and therefore mirrors the implementation's assumed tuple-membership model closely enough to miss status/key/container substitution. A mutation that retags a real derived value would have falsified the completeness claim.
- Specialized-template tests are representative of both registry shapes, and the generic metadata-driven implementation covers the unlisted classified variants.

## Final verdict

**Findings remain open.**

The residual repair should not be approved until registered raw slot identity is checked against authoritative builder-compatible metadata and the renamed-derived-value attack is rejected at both the public contract and real persistence/progress boundaries.
