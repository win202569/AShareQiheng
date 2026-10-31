# Important 1 — derived financial formula authority analysis

## Finding verdict

**CONFIRMED — Important.** Direct inspection of the current branch independently reproduces the review's trust-boundary argument. A canonical `financial_ready` bundle can change a derived numeric value or its non-empty `formula_version`, omit a registered derived output, add an unknown derived output, or move/copy a derived logical slot across dimensions without violating the current public contract. If the cited `EvidenceRef` rows still identify real canonical facts, StateStore accepts them because its value/fact comparison is restricted to `status == "observed"`; every `derived`, `missing`, and `not_applicable` value is skipped. Canonical file hashing and verified reading prove bytes and shape, not the approved calculation. Progress reads that same file, checks the DB header, then calls the same incomplete evidence validator, so it counts the forged result.

This contradicts the binding promises that derived values are versioned formulas over auditable facts and that identical inputs rebuild byte-identically. No runtime database, network, broad test, or product-file mutation was used for this analysis.

## Data-flow and root cause

1. `deep_worker._execute_feature_job()` verifies the frozen three statement snapshots and calendar, normalizes each snapshot into `FinancialFact` rows, selects the point-in-time-visible fact version, and calls `build_feature_bundle()` (`deep_worker.py:1201-1321`).
2. `build_feature_bundle()` filters facts to the bundle security and `eastmoney-financial-mapping-v1`, resolves the template, adds blockers, and calls `assemble_bundle_from_registered_slots()` (`financial_features.py:1029-1103`).
3. Assembly emits every template raw slot for all seven periods, then imperatively appends formulas in `_add_period_formulas()` and `_add_growth_formulas()` (`financial_features.py:701-910, 913-1026`). The only formula authority is therefore builder-private code plus the module constant `financial-derived-v1`.
4. `FeatureBundle.validate()` checks generic value shape and, for `financial_ready`, the exact registered **raw** slot/period Cartesian product. Values not recognizable as registered raw slots are ignored by that scan (`feature_contract.py:465-533`). There is no derived-output catalog to establish identity, location, unit, version, cardinality, or required operands.
5. `write_feature_bundle()` and `read_verified_feature_bundle()` enforce safe paths, hash equality, duplicate JSON-object-key rejection, canonical JSON, and public parsing (`deep_worker.py:677-808`). An attacker who changes a semantic value and recomputes canonical bytes/hash still passes this layer.
6. StateStore resolves every cited fact, requires its snapshot row, and compares all public evidence metadata with the canonical `FinancialFact`. It then immediately skips any value whose status is not `observed`; only raw observed descriptors are checked against fact metric, period, value, unit, mapping version, and source field (`state_store.py:796-899`).
7. `put_feature_bundle()` invokes that validator before both first insertion and existing-row/idempotent success (`state_store.py:901-960`), so both paths share the same hole. Progress verifies the newest file/header and calls `validate_feature_bundle_evidence()` (`orchestrator.py:1052-1082`), so it also shares the hole.

The root cause is not weak hashing or untrusted evidence metadata. It is the absence of one contract-visible derived formula registry/evaluator. Provenance is authenticated, but neither the closed derived feature set nor the computation represented by that provenance is authenticated.

## Exact current financial output

### Period and template applicability

The seven output periods are exactly `FY2021`, `FY2022`, `FY2023`, `FY2024`, `FY2025`, `2025H1`, and `2026H1`, mapped respectively to `2021-12-31`, `2022-12-31`, `2023-12-31`, `2024-12-31`, `2025-12-31`, `2025-06-30`, and `2026-06-30` (`feature_contract.py:17-26`).

- `general_nonfinancial`, `utility`, and `rd_growth` emit the common raw and derived set and may be `financial_ready`, `partial`, or blocked by fact/calendar quality.
- `real_estate_high_leverage` and `resource_cycle` emit the identical common raw and derived set, but remain `blocked` with `specialized_financial_inputs_missing`, even when common-input coverage is 1.0.
- `bank`, `insurance`, `broker`, and `unclassified` have no `financial_slots`; assembly therefore emits no raw or derived financial values. The first three are specialized/blocked. `unclassified` is blocked with zero coverage and `industry_template_unclassified`.
- `V` and `T` are empty `missing` containers in every honest builder result. A financial blocker changes financial **dimension statuses** to `blocked`; it does not retag individual formula values.

For a common-output template, the raw set is 39 metrics x 7 periods = 273 values:

| Dimension | Registered raw metrics |
|---|---|
| `G` | `revenue` |
| `M` | `operating_cost`, `operating_profit`, `total_profit`, `income_tax`, `net_profit`, `parent_net_profit`, `deduct_parent_net_profit`, `interest_expense`, `rd_expense` |
| `EQ` | `operating_cash_flow` |
| `FS` | `cash`, `total_assets`, `total_liabilities`, `parent_equity`, `total_equity`, `short_term_debt`, `current_portion_long_term_debt`, `long_term_debt`, `bonds_payable`, `lease_liabilities`, `notes_receivable`, `accounts_receivable`, `contract_assets`, `inventory`, `notes_payable`, `accounts_payable`, `contract_liabilities`, `share_capital`, `goodwill` |
| `CA` | `capital_expenditure`, `cash_dividends`, `interest_paid`, `acquisition_cash_paid`, `disposal_long_asset_cash`, `equity_financing_cash`, `debt_financing_cash`, `debt_repayment_cash`, `share_repurchase_cash` |

An observed raw value uses `eastmoney-financial-mapping-v1`, its descriptor unit/source-field allowlist, and exactly one fact. An absent raw fact currently uses a `missing` value produced by `_missing_value()`, so its version is `financial-derived-v1` and its reason is `financial_fact_missing:<metric>`; this status-sensitive version difference is current byte-level behavior and should not be silently changed in this repair.

### Closed derived set

All derived, derived-missing, and formula-level `not_applicable` outputs use `financial-derived-v1`. All operands below must be finite canonical `FinancialFact` values with unit `CNY`. A successful derived value carries exactly the de-duplicated canonical operand facts; a missing or N/A result carries no evidence.

| Output | Periods | Formula and exact raw operand rule | Unit | Null/N/A rule and reason |
|---|---|---|---|---|
| `M.gross_profit` | all 7 | `revenue - operating_cost`, same period | `CNY` | missing operand -> `missing_operand:gross_profit` |
| `M.ebit` | all 7 | `total_profit + interest_expense`, same period | `CNY` | missing operand -> `missing_operand:ebit` |
| `M.effective_tax_rate` | all 7 | `clamp(income_tax / total_profit, 0, 0.5)`; requires `total_profit > 0` | `ratio` | missing/nonpositive profit -> `invalid_denominator:total_profit` |
| `M.nopat` | all 7 | `(total_profit + interest_expense) * (1 - effective_tax_rate)`; raw evidence is `total_profit`, `interest_expense`, `income_tax` | `CNY` | any unavailable prerequisite -> `missing_operand:nopat` |
| `CA.fcf` | all 7 | `operating_cash_flow - capital_expenditure` | `CNY` | missing operand -> `missing_operand:fcf` |
| `FS.interest_bearing_debt` | all 7 | sum of `short_term_debt`, `current_portion_long_term_debt`, `long_term_debt`, `bonds_payable`, `lease_liabilities` | `CNY` | missing operand -> `missing_operand:interest_bearing_debt` |
| `FS.net_debt` | all 7 | the five debt operands minus `cash` | `CNY` | missing operand -> `missing_operand:net_debt` |
| `M.invested_capital` | all 7 | `total_equity +` the five debt operands `- cash` | `CNY` | missing operand -> `missing_operand:invested_capital` |
| `M.operating_working_capital` | all 7 | `notes_receivable + accounts_receivable + contract_assets + inventory - notes_payable - accounts_payable - contract_liabilities` | `CNY` | missing operand -> `missing_operand:operating_working_capital` |
| `M.gross_margin` | all 7 | `(revenue - operating_cost) / revenue`; evidence de-duplicates `revenue` | `ratio` | `revenue == 0` or missing -> `invalid_denominator:revenue` |
| `EQ.total_accruals` | FY2022-FY2025, 2025H1, 2026H1 | `(net_profit - operating_cash_flow) / ((opening_total_assets + current_total_assets)/2)` | `ratio` | zero/missing average -> `invalid_denominator:average_total_assets` |
| `M.roic` | FY2022-FY2025, 2025H1, 2026H1 | `NOPAT / ((opening_invested_capital + current_invested_capital)/2)`; exact raw evidence is the three NOPAT operands plus seven current and seven opening invested-capital operands | `ratio` | zero/missing average or NOPAT -> `invalid_denominator:average_invested_capital` |
| `G.revenue_symmetric_growth` | FY2022, FY2023, FY2024, FY2025, 2026H1 | `200*(current_revenue-previous_revenue)/(abs(current_revenue)+abs(previous_revenue))`; pairs are successive FY years and 2026H1/2025H1 | `ratio` | both revenues zero or missing -> `invalid_denominator:symmetric_growth` |
| `G.revenue_cagr` | FY2025 only | `100*((FY2025 revenue/FY2022 revenue)^(1/3)-1)` | `ratio` | either endpoint nonpositive/missing -> `invalid_endpoint:revenue_cagr` |

`EQ.total_accruals.FY2021` and `M.roic.FY2021` are still mandatory logical outputs, but are exactly `not_applicable`, null, evidence-free, unit `ratio`, and reason `frozen_window_no_opening_period`. The opening periods are FY2021 for FY2022, each prior FY thereafter, FY2024 for 2025H1, and FY2025 for 2026H1.

There are exactly 84 per-period formula slots plus 5 symmetric-growth slots plus 1 CAGR slot = **90 derived logical outputs**. Together with 273 raw outputs, a common template has **363 values**. The two FY2021 N/A slots are excluded from coverage, leaving the existing **361 applicable values**. Zero arithmetic results are preserved. Except for effective tax rate's positive-profit rule and clamp, a negative nonzero revenue/average denominator remains valid. Symmetric growth permits negative bases; CAGR does not.

## Exact authority and reuse/refactor boundary

Create one neutral pure module, recommended as `ashare_pipeline/financial_formulas.py`, with no imports from `feature_contract.py`, `financial_features.py`, `state_store.py`, templates, SQLite, or network code. It should own and export:

- `DERIVED_FORMULA_VERSION = "financial-derived-v1"` (re-export it as the existing `financial_features.FORMULA_VERSION` for compatibility);
- immutable `DerivedFormulaSpec` records containing canonical dimension, metric key, applicable period keys, unit, version, allowed result state, exact missing/N/A reason, and operand/evaluation rule;
- the closed ordered 90-slot catalog for the common formula profile;
- a pure `evaluate_derived_financial(facts_by_metric_period)` that returns, for every catalog slot, exact status, numeric value or null, missing reason, and the exact operand logical fact slots used as evidence.

The evaluator should operate on a minimal read-only fact protocol (`metric_key`, `period_end`, `value`, `unit`, stable identity) or on immutable input records. It must not manufacture `FeatureValue` or query a database. `financial_features.py` converts evaluator results into `FeatureValue`/`EvidenceRef`; StateStore converts the same results into an expected canonical projection using its resolved canonical `FinancialFact` rows.

Public contract validation should combine two existing authorities rather than create a third list:

1. raw output identities from `financial_schema.raw_financial_slot_descriptor()` and `template.financial_slots`;
2. derived identities/metadata from the new formula catalog when `template.financial_slots` is non-empty, otherwise an empty derived set.

For contract v1, compare the complete financial namespace globally, not separately per dimension: exact cardinality and logical set; canonical `dimension.lower().metric.period` key; key period equal to `period_key`; correct container, unit, version, and status/reason rules. This rejects cross-dimension duplicates and logical aliases that the current per-container duplicate check misses. It should also recompute coverage from the closed set (excluding the two N/A slots) rather than trust the supplied number. Honest serialized bytes and existing versions remain unchanged.

Do **not** make `feature_contract.py` import `financial_features.py`. That creates a contract/builder cycle because `financial_features.py` already imports the contract. Importing the whole builder from StateStore is not currently a direct cycle, but it makes persistence depend on template/status/confidence assembly and cannot faithfully rebuild bank/insurance/broker confidence inputs: those templates emit no evidence although assembly still counts supplied facts. A whole-bundle rebuild is therefore the wrong comparison boundary.

The recommended boundary is an extracted evaluator plus a deterministic, byte-exact comparison of the **derived financial projection**. It is both smaller and more authoritative than duplicating formulas in StateStore or rebuilding the complete `FeatureBundle`.

## Validation layers

### 1. Public construction and parsing

- Require the exact raw + 90-derived set for common-output templates and the exact empty set for no-slot templates.
- Reject missing, unknown, wrongly placed, cross-dimension duplicate/logical-collision, key/period mismatch, wrong-unit, and wrong-version outputs for every status (`financial_ready`, `partial`, and `blocked`).
- Raw observed slots retain mapping-v1/single-evidence rules; raw missing slots retain current v1 builder bytes and exact missing reason.
- Formula slots permit only the evaluator-defined `derived` or `missing` outcome; the two FY2021 slots require exact N/A metadata.
- Structural parsing deliberately cannot authenticate a finite numeric result or choose the canonical fact revision. That remains StateStore's responsibility.

### 2. StateStore canonical authentication

Extend the existing shared `_validate_feature_bundle_evidence()` after fact/snapshot metadata verification:

1. Build `facts_by_metric_period` only from exact registered raw `observed` slots and their resolved canonical fact IDs. Reject fact reuse, slot collision, and any raw feature/fact mismatch first.
2. Run the shared evaluator on that frozen raw fact map. Do not query all facts for the security or rerun point-in-time selection; unrelated revisions may coexist in SQLite and are not part of this bundle's selected input.
3. Build the expected derived projection from evaluator output and canonical facts. Compare exact logical set, status, unit, formula version, canonical numeric representation (no tolerance and no `-0.0`/`0.0` collapse), missing reason, and exact operand fact IDs.
4. Continue comparing each advertised evidence object's snapshot/source field/hash/timestamps with its canonical fact, as today. Exact operand IDs plus existing metadata checks authenticate both the formula and provenance.

Because `put_feature_bundle()` already calls this validator before looking up an existing row, the change covers first insert and idempotent reuse without a second code path. Because progress already calls the public validator after canonical file/header verification, it covers progress too. Important 2's separate file-versus-`feature_value` row comparison remains separate and is not silently claimed closed here.

### 3. File and progress

Keep canonical JSON, duplicate object-key rejection, safe relative paths, no-clobber writes, and hash verification unchanged. A hash is a content identifier, not semantic authorization. Progress must retain newest-only/no-fallback behavior and bounded unknown-failure accounting; a newest formula-invalid file contributes one unknown failure and is not counted under any feature status.

## Adversarial RED and positive test matrix

| Case | Boundary and required assertion | Why it is RED now |
|---|---|---|
| Numeric mutation | Change only `m.gross_profit.FY2021.value` to another finite number with canonical evidence. Public parse may succeed; first `put_feature_bundle`, idempotent re-put, and progress must reject an exact-result mismatch. | Current parser accepts; StateStore skips `derived`. |
| Formula-version mutation | Change one formula slot to any other non-empty version. `FeatureBundle.from_dict()` must reject before file/DB work. | Current generic validation requires only non-empty text. |
| Operand substitution | Replace `gross_profit`'s `operating_cost` evidence with another real canonical fact, or replace a growth operand with the wrong period's revenue. StateStore must reject exact operand IDs on first insert, idempotent reuse, and progress. | Current evidence metadata is real, so it passes; no formula operand rule exists. |
| Derived omission | Remove one mandatory formula value while leaving all raw slots and supplied coverage/header unchanged. Public parse must reject exact-set mismatch for ready, partial, and blocked common templates. | Ready validation checks only raw slots. |
| Unknown addition | Add a well-formed `m.unknown_formula.FY2021` derived value. Public parse must reject. | It is ignored by the raw-slot scan. |
| Wrong placement | Move `m.gross_profit.FY2021` to `G`, or make key prefix/period disagree with its container/`period_key`. Public parse must reject. | Derived keys have no registered dimension binding. |
| Duplicate/logical collision | Keep the legitimate M slot and copy it into G, or encode one catalog slot twice using a key/period mismatch. Public parse must reject global cardinality/identity. Also retain the existing same-container exact-duplicate test. | Duplicate detection is currently local to one `DimensionInput`. |

Positive paths must use the honest production builder and the same shared evaluator:

- complete `general_nonfinancial`, `utility`, and `rd_growth`: 363 values, 361 applicable, formula results/evidence exact, `financial_ready`, canonical round trip, first insert, idempotent reuse, verified read, and progress count;
- no facts and mixed statement facts: exact slot set retained, formula values become exact evidence-free missing outputs, coverage/status remain partial;
- common-template fact/calendar/conflict blocker: values remain authentic while financial dimensions/status are blocked;
- `real_estate_high_leverage` and `resource_cycle`: common raw + 90-formula set authenticates but specialized blocker keeps status blocked;
- `bank`, `insurance`, and `broker`: no industrial raw/formula outputs, zero coverage, specialized blocked;
- `unclassified`: no outputs, zero coverage, exact unclassified blocker, verified read and blocked progress count;
- FY2021 exact N/A pair; effective-tax clamp; zero profit/revenue/averages; negative nonzero denominator results; both-zero symmetric growth; nonpositive CAGR endpoint; formula evidence ID sets for simple, NOPAT, accrual, and ROIC formulas;
- mutation after an honest persistence must fail the same validator on idempotent reuse and progress, proving there is no bypass.

Every integration test must continue to assert `is_formal_score_ready == false`, `formal_confidence is None`, no formal module score, and zero formal/waiting-price/strong-attention pool publication.

## Risks and YAGNI constraints

- Preserve the current formulas, missing reasons, units, period openings, float operations, canonical ordering, contract version, mapping version, template version, and honest output bytes. A formula semantic change requires a new formula version and therefore a new input hash; do not reinterpret `financial-derived-v1`.
- Do not add tolerances, default tax rates, filling, winsorization, industry ranks, market inputs, or scoring behavior. Exact recomputation is possible because builder and validator share the same pure evaluator and canonical floats.
- Do not query every DB fact and attempt to reselect revisions. The bundle's registered raw observed slots are the selected frozen inputs; using unrelated revisions would create false failures and a second selection implementation.
- Do not claim that absence of a raw fact is authenticated against every snapshot. This repair authenticates the derived projection against the bundle's exact selected canonical raw inputs; snapshot-to-fact selection remains the existing worker boundary.
- Do not add signatures or schema migration. Content hashing plus canonical-fact/formula validation is sufficient for this finding. Tightened v1 parsing may cause previously stored noncanonical artifacts to fail progress, which is the intended fail-closed behavior; honest builder bytes should not change.
- Keep Important 2 separate: formula authentication does not compare persisted `feature_value` rows with the verified file.

## Recommended touched files

Production:

- **new** `ashare_pipeline/financial_formulas.py` — neutral catalog and pure shared evaluator;
- `ashare_pipeline/financial_features.py` — replace private formula construction with evaluator output and re-export `FORMULA_VERSION`;
- `ashare_pipeline/feature_contract.py` — exact global financial slot/catalog, metadata, version, N/A, duplicate, and coverage validation;
- `ashare_pipeline/state_store.py` — canonical raw fact map and exact derived projection/evidence authentication in the existing shared validator.

No production change is required in `deep_worker.py` or `orchestrator.py` for this finding because both already traverse the shared construction/validation paths.

Tests:

- **new or focused** `tests/test_financial_formulas.py` for catalog cardinality, formula branches, operands, and boundary arithmetic;
- `tests/test_financial_features.py` for exact honest builder outputs across ready/partial/blocked/specialized/unclassified cases;
- `tests/test_feature_contract.py` for omission, addition, version, placement, and global collision attacks;
- `tests/test_state_store.py` for numeric/operand attacks on first insert and idempotent reuse;
- `tests/test_orchestrator.py` for newest invalid/no fallback and honest positive progress paths.

No schema, migration, scoring, pool, source, or network test file belongs in this repair.
