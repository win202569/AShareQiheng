# Final derived-authentication and DB-mirror remediation brief

Baseline: `ee1a5d78e4e1d123ddd002c54c80bda8f41fd133`

This is one user-authorized, tightly bounded remediation task for the two Important findings in `final-branch-rereview-v3.md`. This brief is the requirements authority. The read-only analyses `derived-formula-analysis.md` and `feature-value-mirror-analysis.md` are implementation-navigation context; if wording differs, this brief controls.

## Objective

Close exactly these two trust-boundary gaps:

1. Authenticate the complete versioned derived financial projection. A canonical bundle backed by real facts must not be able to mutate a derived numeric result or formula version, substitute an operand, omit a required derived output, add an unknown output, or move/copy a logical output across dimensions and still persist or count ready.
2. Authenticate the DB mirror of the verified artifact. Progress must compare the exact persisted `feature_set` header and complete `feature_value` child set with the verified canonical file, detecting deleted, updated, or extra child rows while preserving newest-only/no-fallback and one bounded unknown per candidate.

Keep formal scoring, seven-dimension readiness, formal publication, waiting-price pool, and strong-attention pool hard closed. Do not address heartbeat coverage, legacy absolute snapshot containment, plan table-name typos, or the broad exception catch in the prior unclassified negative test.

## Mandatory root cause and TDD sequence

Before production edits, independently reproduce both findings through public and real isolated boundaries. Write focused tests first, run them against baseline `ee1a5d7`, and record the genuine RED command, exit code, exact failures, and already-passing positive controls in the private report. A test that fails only because of stale bundle/hash bytes, malformed setup, or an unrelated broad exception does not count.

Then implement the smallest shared authorities, one behavior at a time, and turn the focused tests GREEN before related/full suites. Do not write production code before observing the expected RED.

## Derived financial authority

### Fixed contract values

- Contract remains `feature-contract-v1`; schema remains v3; no migration.
- Derived formula version remains exactly `financial-derived-v1`.
- `financial_features.FORMULA_VERSION` must remain import-compatible and equal that value.
- Financial periods remain exactly `FY2021`, `FY2022`, `FY2023`, `FY2024`, `FY2025`, `2025H1`, `2026H1`, mapped to the existing `FINANCIAL_PERIODS` dates.
- Common-output templates are the templates with non-empty `financial_slots`: `general_nonfinancial`, `utility`, `rd_growth`, `real_estate_high_leverage`, and `resource_cycle`.
- No-output templates are `bank`, `insurance`, `broker`, and `unclassified`; their financial value namespace must remain empty and coverage zero. Existing specialized/unclassified blockers and statuses remain unchanged.
- A common-output template has exactly 273 registered raw values plus 90 formula logical outputs = 363 values. The two FY2021 N/A formula slots are excluded from coverage, leaving 361 applicable values.

### Exact 90 formula slots

For every one of the seven periods, require these twelve logical outputs in their exact dimensions, units, version, and current missing behavior:

| Dimension.metric | Formula | Unit | Missing reason |
|---|---|---|---|
| `M.gross_profit` | `revenue - operating_cost` | `CNY` | `missing_operand:gross_profit` |
| `M.ebit` | `total_profit + interest_expense` | `CNY` | `missing_operand:ebit` |
| `M.effective_tax_rate` | clamp `income_tax / total_profit` to `[0, 0.5]`, only when `total_profit > 0` | `ratio` | `invalid_denominator:total_profit` |
| `M.nopat` | `ebit * (1 - effective_tax_rate)`; raw operands are total profit, interest expense, income tax | `CNY` | `missing_operand:nopat` |
| `CA.fcf` | `operating_cash_flow - capital_expenditure` | `CNY` | `missing_operand:fcf` |
| `FS.interest_bearing_debt` | sum the five existing debt metrics | `CNY` | `missing_operand:interest_bearing_debt` |
| `FS.net_debt` | five debt metrics minus cash | `CNY` | `missing_operand:net_debt` |
| `M.invested_capital` | total equity plus five debt metrics minus cash | `CNY` | `missing_operand:invested_capital` |
| `M.operating_working_capital` | receivable notes + receivables + contract assets + inventory - payable notes - payables - contract liabilities | `CNY` | `missing_operand:operating_working_capital` |
| `M.gross_margin` | gross profit / revenue when revenue is finite and nonzero | `ratio` | `invalid_denominator:revenue` |
| `EQ.total_accruals` | `(net_profit - operating_cash_flow) / average(opening,current total_assets)` | `ratio` | `invalid_denominator:average_total_assets` |
| `M.roic` | NOPAT / average(opening,current invested capital) | `ratio` | `invalid_denominator:average_invested_capital` |

`EQ.total_accruals.FY2021` and `M.roic.FY2021` are mandatory `not_applicable` null, evidence-free slots with unit `ratio` and exact reason `frozen_window_no_opening_period`. For later periods use the existing opening map: FY2022←FY2021, FY2023←FY2022, FY2024←FY2023, FY2025←FY2024, 2025H1←FY2024, 2026H1←FY2025.

Also require exactly five `G.revenue_symmetric_growth` slots for FY2022, FY2023, FY2024, FY2025, and 2026H1 using the existing successive-FY and 2026H1/2025H1 pairs, unit `ratio`, version `financial-derived-v1`, and reason `invalid_denominator:symmetric_growth`; and exactly one `G.revenue_cagr.FY2025` over FY2022→FY2025 for 3 years, unit `ratio`, same version, and reason `invalid_endpoint:revenue_cagr`.

Preserve all current arithmetic semantics and bytes: zero results remain values; negative nonzero denominators remain valid except the existing positive-profit effective-tax rule; symmetric growth permits negative bases and rejects both-zero; CAGR requires positive endpoints; evidence is the exact de-duplicated canonical raw operand fact set; no tolerance or imputation is allowed.

### Single source of truth

Create one neutral pure authority, expected as `ashare_pipeline/financial_formulas.py`, that owns:

- the exact formula version;
- immutable formula specifications/catalog for the 90 logical outputs;
- one pure evaluator that returns every expected slot's status, exact numeric value/null, exact reason, unit/version, and exact operand logical facts.

It must not import `feature_contract`, `financial_features`, `state_store`, industry templates, SQLite, source adapters, or network code. It may consume a minimal fact protocol/immutable record. Avoid a contract↔builder import cycle.

`financial_features.py` must use this evaluator rather than retain a second private formula implementation. Convert evaluator results to the existing `FeatureValue`/`EvidenceRef` representation and preserve honest canonical output. Re-export the unchanged formula version for compatibility.

`feature_contract.py` must use the catalog plus the existing raw-slot descriptors to enforce, for every common template and every financial status (`financial_ready`, `partial`, or blocked):

- the exact global raw + formula logical set and cardinality;
- canonical container/dimension, key, period, unit, version, allowed state, evidence/no-evidence shape, exact missing/N/A reason;
- no unknown, missing, duplicate, cross-dimension copy, alias, or key/period mismatch;
- observed raw slots retain descriptor metadata/single-evidence rules; raw-missing slots retain current builder metadata and `financial_fact_missing:<metric>` reason;
- financial coverage is recomputed from the exact applicable set and must equal both declared coverage and confidence completeness.

No-output templates must expose no financial values. Structural public validation cannot authenticate numeric results or fact identity; do not pretend it can.

`StateStore._validate_feature_bundle_evidence()` must, after existing fact/snapshot/public-metadata checks:

- build the frozen formula input map only from exact registered raw observed slots and their already-resolved canonical facts;
- reject raw slot/fact reuse or collision before evaluation;
- run the shared evaluator, then compare the entire advertised formula projection exactly: logical set, dimension/key/period, status, unit, version, canonical numeric representation (including signed zero), reason, no duplicates, and exact de-duplicated operand fact IDs;
- retain existing evidence metadata equality and source-snapshot existence checks;
- run before first insert and before idempotent success, and remain reused by progress on the verified file.

Do not query/reselect every historical fact for a security and do not rebuild the whole bundle. The registered raw observed slots in this artifact are the frozen inputs; authenticate only the derived projection from them.

### Required derived RED regressions

At minimum prove:

- public parse rejects formula-version mutation, one derived omission, one unknown addition, wrong dimension/key/period placement, and a cross-dimension logical copy/collision;
- exact-set enforcement applies to ready, partial, and blocked common templates, while honest no-output specialized/unclassified templates remain valid;
- a finite numeric mutation of `m.gross_profit.FY2021` with otherwise canonical facts/evidence may pass structural parse but is rejected by first persistence, idempotent reuse, verified progress, and newest-invalid/no-fallback;
- replacing gross-profit operating-cost evidence with a different real canonical fact, and replacing a growth operand with a real revenue fact from the wrong period, are rejected by the same DB authority;
- honest general/utility/R&D common bundles, specialized common bundles, bank/insurance/broker, unclassified, partial/missing, exact FY2021 N/A, tax clamp, zero and negative-denominator cases, growth/CAGR boundaries, first insert, idempotent reuse, read, and progress remain correct;
- tests independently assert literal/hand-checked results and exact operand IDs rather than recomputing expected results with the production evaluator.

## Exact persisted feature-value mirror

Promote the existing `StateStore._stored_feature_content_matches()` policy into one shared connection-aware exact validator, expected shape:

```python
_validate_stored_feature_bundle_content(connection, feature_set_row, bundle) -> None
```

It must compute the expected header and child values internally from the verified bundle and its canonical hash. Do not make orchestrator duplicate column lists or pass a header while discarding values.

Comparison semantics:

- compare every `_FEATURE_SET_CONTENT_COLUMNS` value exactly;
- compare the complete `_FEATURE_VALUE_CONTENT_COLUMNS` tuple set exactly, ordered by `(dimension, feature_key, period_key)`;
- compare canonical JSON text, finite numbers/nulls, statuses, versions, evidence JSON, and missing reasons exactly; no epsilon;
- query stored children by `feature_set_id`, return at most `len(expected_values) + 1` rows, and reject missing, updated, or extra rows;
- do not redefine `id`, `created_at`, or `bundle_path` as artifact-payload columns; existing verified safe path/hash checks remain authoritative;
- keep public metadata reader return shapes unchanged and require no schema/index migration.

Use the shared validator:

1. on the idempotent existing-row path before success;
2. after first header/child insertion and before commit, so materialization drift rolls back;
3. in progress after verified file read and before counting.

For progress, keep selected header rows, exact child comparison, and connection-aware evidence/formula authentication within one explicit SQLite read transaction/snapshot. Preserve the existing sort, mark a security seen before validation, never fall back to an older row, and add exactly one bounded unknown for an invalid newest candidate. No network or sleep may occur inside this path.

### Required mirror RED regressions

Using a real temporary StateStore, canonical file, facts, and snapshots, persist older and newer valid ready rows for one candidate, then independently mutate only the newer `feature_value` table:

- delete one known child and assert exactly one affected row;
- update one numeric/status-safe child and assert exactly one affected row;
- insert one unique syntactically valid extra child and assert the count grows by one.

For every case prove the newer file still verifies, progress counts no feature status, reports exactly one bounded unknown, and does not fall back to the older valid row; all formal/seven/pool gates stay closed. Add an unmutated positive exact-match case.

Also prove idempotent re-put rejects each child corruption without repairing it, and first-insert validation remains transactionally atomic. Do not satisfy these tests by catching an unrelated broad exception.

## Public progress record

After fresh full and staged-tree suites pass, append a concise, temporally accurate tracked `progress.md` entry recording derived formula authentication and exact DB child-mirror validation plus the current full-suite count. It must not predict review approval and must continue to state that live bounded network smoke and exact `120/114` operational acceptance are unperformed, `formal_score_ready=false`, no formal scores are published, and both official pools remain closed/empty.

## Scope and safety

Expected production scope:

- new `ashare_pipeline/financial_formulas.py`;
- `ashare_pipeline/financial_features.py`;
- `ashare_pipeline/feature_contract.py`;
- `ashare_pipeline/state_store.py`;
- `ashare_pipeline/orchestrator.py` only for the shared DB snapshot/mirror call.

Expected tests:

- new/focused `tests/test_financial_formulas.py`;
- `tests/test_financial_features.py`;
- `tests/test_feature_contract.py`;
- `tests/test_state_store.py`;
- `tests/test_orchestrator.py`;
- directly affected E2E regressions only.

Do not modify schema DDL/migrations, deep-worker behavior, source adapters, candidate planning, network behavior, scoring, publication, pools, runtime/tracked data, ignore rules, the three unrelated code/doc Minors, or the prior broad-exception Minor. Do not open or migrate a runtime database. Do not use the network.

Preserve the pre-existing controller-owned `.final-pit-temp/`, `.final-derived-temp/`, `.tmp-tests/`, and inaccessible `.tmp-root-check/` noise; do not stage, edit, or delete it.

## Verification and deliverables

Use `D:\Projects\AShareQiheng\.venv\Scripts\python.exe` with a new worktree-local `.final-derived-mirror-temp` for TEMP/TMP/TMPDIR. At minimum run:

1. focused new RED/GREEN tests;
2. formula/contract/financial/state-store/orchestrator/E2E affected modules;
3. the full `python -m unittest discover -s tests` suite;
4. a fresh staged-tree full suite after path-specific staging;
5. working and staged `git diff --check`, staged stat/diff inspection, and exact scope verification.

Use `apply_patch` for edits and path-specific `git add`. Stage no private `.superpowers`, temp, runtime DB/data, ignore, or unrelated file. Commit all authorized production/tests/tracked-progress changes.

Private report: `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/final-derived-mirror-fix-report.md`.

The report must contain: independent reproduction/root cause; genuine RED command/output/exit and exact failures; architectural choice and preserved compatibility; changed files; focused/related/full/staged-full commands with exact counts/results; staged scope/diff checks; commit hash; concerns. Return only `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or `BLOCKED`, plus commit, one-line tests, and concerns.

You must not spawn subagents or reviewers. The controller owns independent review.
