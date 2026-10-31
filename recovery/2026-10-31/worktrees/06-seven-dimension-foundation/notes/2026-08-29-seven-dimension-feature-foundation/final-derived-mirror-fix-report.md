# Final derived authentication and DB mirror fix report

Date: 2026-08-31

Baseline: `ee1a5d78e4e1d123ddd002c54c80bda8f41fd133`

## Independent reproduction and root cause

I reproduced both review findings on the exact baseline before changing production code.

1. Derived output authentication stopped at structural/public metadata and registered raw slots. Formula construction lived privately in `financial_features.py`, while `StateStore._validate_feature_bundle_evidence()` authenticated referenced facts but skipped every non-`observed` value. Consequently, a structurally valid bundle could mutate a derived number, substitute a different real operand fact, use a revenue fact from the wrong period, or omit/add/move a formula output and cross the persistence/progress boundary.
2. Persisted-mirror authentication compared only the feature-set header in progress. The existing child comparison was confined to idempotent writes and accepted expected header/value material from its caller. Progress computed expected values and discarded them, then performed evidence validation through a separate connection. Deleting, updating, or adding a newest `feature_value` row therefore still counted the newest artifact as ready.

## Genuine RED

Environment for all commands:

- Python: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe`
- `TEMP`, `TMP`, `TMPDIR`: `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation\.final-derived-mirror-temp`
- no network and no tracked/runtime database or `data/` access

Focused RED command:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_formulas tests.test_feature_contract.FeatureContractTests.test_public_parse_authenticates_closed_derived_projection tests.test_feature_contract.FeatureContractTests.test_exact_formula_set_applies_to_partial_and_blocked_common_templates tests.test_feature_contract.FeatureContractTests.test_no_output_templates_keep_an_empty_financial_namespace tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_authenticates_derived_values_and_operands tests.test_state_store.StateStoreTestCase.test_idempotent_put_reauthenticates_derived_numeric_projection tests.test_orchestrator.OrchestratorTestCase.test_progress_rejects_newest_derived_numeric_mutation_without_fallback tests.test_orchestrator.OrchestratorTestCase.test_progress_rejects_deleted_newest_feature_child_without_fallback tests.test_orchestrator.OrchestratorTestCase.test_progress_rejects_updated_newest_feature_child_without_fallback tests.test_orchestrator.OrchestratorTestCase.test_progress_rejects_extra_newest_feature_child_without_fallback
```

Result: exit 1, `Ran 12 tests in 1.712s`, `FAILED (failures=18)`.

Expected failures:

- 3 neutral-authority assertions because `ashare_pipeline.financial_formulas` did not exist;
- 5 public closed-projection attacks accepted: formula version mutation, omission, unknown output, wrong dimension, and cross-dimension copy;
- 2 exact-set attacks accepted for partial and specialized-blocked common templates;
- 3 first-persistence attacks accepted: finite derived numeric mutation, gross-profit operand substitution, and growth operand substitution with a real revenue fact from the wrong period;
- 1 idempotent derived numeric forgery accepted;
- 1 newest forged derived projection counted by progress;
- 3 newest child mirror corruptions (delete/update/extra) counted by progress.

The no-output specialized/unclassified positive controls already passed in the same RED run. Test setup used canonical temporary snapshots, facts, verified files, and real StateStore/progress production paths; failures were not stale hashes or malformed setup.

## Architecture and compatibility

- Added neutral `financial_formulas.py`, importing no contract, builder, store, templates, source, SQLite, or network code. It owns the literal `financial-derived-v1` version, frozen fact/spec/result records, the immutable exact 90-slot catalog, seven-period/opening relationships, and one pure evaluator.
- `financial_features.py` now converts selected canonical facts into minimal `FormulaFact` inputs, calls that evaluator, and converts results back to the existing `FeatureValue`/`EvidenceRef` shapes. `FORMULA_VERSION` remains import-compatible and exactly `financial-derived-v1`.
- `feature_contract.py` remains context-free. It combines registered raw-slot descriptors with the neutral catalog to enforce the exact 273 raw + 90 formula projection for all common statuses, exact dimension/key/period/unit/version/state/evidence/reason shapes, exact coverage, and an empty financial namespace for bank/insurance/broker/unclassified.
- `StateStore._validate_feature_bundle_evidence()` reuses already bounded, set-based evidence/fact/snapshot reads. It forms evaluator inputs only from authenticated registered observed raw slots, rejects fact/slot reuse, and exactly compares all 90 advertised formula results including canonical numeric JSON (signed zero), state/reason/version/unit, and de-duplicated operand IDs.
- `_validate_stored_feature_bundle_content(connection, feature_set_row, bundle)` internally materializes the expected canonical header and children, compares all content columns exactly, and reads at most `expected child count + 1` ordered rows. It runs on idempotent reuse and after first insertion before commit.
- Progress now performs newest-row selection, verified file read, exact header/child mirror validation, and evidence/formula validation inside one explicit StateStore read transaction. It still marks a candidate seen before validation, never falls back, and records at most one bounded unknown.
- Existing formula arithmetic and bytes are preserved, including tax clamp, negative nonzero denominator behavior, zero values, signed-zero exactness, symmetric growth/CAGR boundaries, exact FY2021 N/A slots, and exact sorted/de-duplicated evidence identities.
- General, utility, and R&D common templates remain ready with 363 outputs; specialized common templates retain their blocker; bank/insurance/broker/unclassified retain empty financial namespaces and existing status semantics. V/T and all formal scoring/publication/pool gates remain unchanged and closed.

## Changed files

Production:

- `ashare_pipeline/financial_formulas.py` (new)
- `ashare_pipeline/financial_features.py`
- `ashare_pipeline/feature_contract.py`
- `ashare_pipeline/state_store.py`
- `ashare_pipeline/orchestrator.py`

Tests:

- `tests/test_financial_formulas.py` (new)
- `tests/test_financial_features.py`
- `tests/test_feature_contract.py`
- `tests/test_state_store.py`
- `tests/test_orchestrator.py`

Tracked record:

- `progress.md`

No schema, migration, deep-worker behavior, source adapter, candidate planning, scoring, publication, pool, runtime/tracked data, ignore, network, or deferred-Minor change was made.

## GREEN and verification

Final focused GREEN (exact derived and mirror regressions plus positive common-template/progress controls):

```text
Ran 17 tests in 2.439s
OK
```

Affected modules command:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_formulas tests.test_feature_contract tests.test_financial_features tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e
```

Result: `Ran 281 tests in 88.949s`, `OK`.

Fresh working-tree full suite:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result: `Ran 386 tests in 92.147s`, `OK`.

Fresh staged-tree full suite, after path-specific staging of only the 11 authorized files:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result: `Ran 386 tests in 97.012s`, `OK`.

Working and staged `git diff --check`: clean (only Git's existing LF-to-CRLF warnings on working-copy inspection). Staged scope contains exactly the five production files, five test files, and `progress.md`; private `.superpowers`, temp directories, `data/`, controller-owned noise, and unrelated files are not staged.

## Commit and concerns

Commit: `b89e76b42a1be355cb92a0ccf3e293a81652cd38`.

Concerns: none. Live bounded network smoke and exact operational `120/114` acceptance remain deliberately unperformed, and all formal/seven-dimension/publication/pool gates remain closed as recorded in `progress.md`.

## Fix round 1/5 — global V/T financial namespace closure

Date: 2026-08-31

Fix-round baseline: `b89e76b42a1be355cb92a0ccf3e293a81652cd38`.

### Independent reproduction and root cause

I independently reproduced the scoped review's remaining Important before editing production code. The public validator built both `supplied_projection` and `supplied_count` solely from `FINANCIAL_DIMENSIONS`, so a canonical `m.gross_profit.FY2021` or registered raw value could be copied into V or T while leaving the expected five-container set unchanged. No-output templates had the same blind spot. StateStore independently repeated the container assumption by selecting formula values only when the tuple already used the catalog dimension. With an exact file/header/child mirror, progress therefore counted the forged newest row and did not fall back.

### Genuine fix-round RED

Command:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract.FeatureContractTests.test_public_parse_rejects_financial_formula_copies_in_v_and_t tests.test_feature_contract.FeatureContractTests.test_no_output_templates_reject_financial_formula_values_in_v_and_t tests.test_state_store.StateStoreTestCase.test_first_persistence_rejects_financial_formula_copy_in_t tests.test_state_store.StateStoreTestCase.test_evidence_authority_rejects_financial_formula_aliases_in_v_and_t tests.test_orchestrator.OrchestratorTestCase.test_progress_rejects_newest_financial_formula_copy_in_t_without_fallback
```

Result: exit 1, `Ran 5 tests in 0.632s`, `FAILED (failures=10)`.

Exact expected failures:

- common-template formula copy was accepted in both V and T (2 failures);
- bank and unclassified no-output bundles accepted the formula in both V and T (4 failures);
- real first persistence accepted and wrote the T-copy bundle (1 failure);
- the connection-aware evidence authority ignored the copy in both V and T (2 failures);
- a newest forged verified file plus exactly matching DB header/child mirror counted `financial_ready=1` instead of zero/one bounded unknown, proving the real progress/no-fallback bypass (1 failure).

The failures were specifically `ValueError not raised` or the ready count mismatch; setup used real canonical facts/snapshots, a temporary StateStore, canonical artifact bytes, and an exact DB mirror. No stale hash, malformed payload, network, runtime DB, or broad exception produced the RED.

### Minimal shared-authority change

- `feature_contract.financial_projection_values()` is now the single runtime-safe recognizer for the financial namespace across all seven containers. It derives raw metric/version authority from the registered template slots plus raw-slot descriptors and formula metric/period/version authority from the neutral 90-slot catalog.
- Every value in G/M/EQ/FS/CA remains in the closed financial namespace. V/T values join it only when they use a registered financial version or an exact catalog/raw metric-period alias, so legitimate nonfinancial V/T values such as `v.market_cap` and `t.sample` remain valid.
- Public exact set/count and coverage now consume that global projection. Common templates reject copied formula/raw values in V/T, while bank/insurance/broker/unclassified continue to require a truly empty financial namespace.
- StateStore consumes the same projection before evidence early-return, rejects any recognized V/T financial alias, enforces no-output template emptiness defensively, and uses the shared entries for formula selection. It therefore cannot silently ignore financial-version, catalog, or registered-raw aliases even if a caller bypasses public object construction.
- The exact DB mirror, one-transaction verified progress path, formula arithmetic/catalog, schema, scoring/publication/pools, and all deferred Minors are unchanged.

Changed files in this round:

- `ashare_pipeline/feature_contract.py`
- `ashare_pipeline/state_store.py`
- `tests/test_feature_contract.py`
- `tests/test_state_store.py`
- `tests/test_orchestrator.py`
- `progress.md`

### Fix-round GREEN and complete commands

Final focused GREEN command (including formula and raw copies in both V/T, no-output specialized/unclassified, real first persistence, direct StateStore defense, and real newest progress/no-fallback):

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract.FeatureContractTests.test_public_parse_rejects_financial_projection_copies_in_v_and_t tests.test_feature_contract.FeatureContractTests.test_no_output_templates_reject_financial_formula_values_in_v_and_t tests.test_state_store.StateStoreTestCase.test_first_persistence_rejects_financial_formula_copy_in_t tests.test_state_store.StateStoreTestCase.test_evidence_authority_rejects_financial_formula_aliases_in_v_and_t tests.test_orchestrator.OrchestratorTestCase.test_progress_rejects_newest_financial_formula_copy_in_t_without_fallback
```

Result: `Ran 5 tests in 0.604s`, `OK`.

Affected-module command:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_formulas tests.test_feature_contract tests.test_financial_features tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e
```

The first covering run produced `Ran 286 tests in 148.808s`, `FAILED (errors=1)` because `tests.test_deep_worker.DeepWorkerTestCase.test_target_period_missing_is_terminal_and_blocked_after_cutoff` hit its existing lease-owner expiry check. Isolation command:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_target_period_missing_is_terminal_and_blocked_after_cutoff
```

Result: `Ran 1 test in 0.246s`, `OK`. A fresh retry of the exact affected-module command then produced `Ran 286 tests in 91.242s`, `OK`; no lease/deep-worker production or test change was made.

Fresh working-tree full command:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result: `Ran 391 tests in 118.313s`, `OK`.

Fresh staged-tree full command after path-specific staging:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result: `Ran 391 tests in 104.908s`, `OK`.

Working and staged `git diff --check`: clean, apart from Git's existing LF-to-CRLF informational warnings. Staged scope is exactly the six files listed above; no `.superpowers`, temp/controller noise, `data/`, runtime DB, ignore file, or unrelated file is staged.

Fix-round commit: `e8c7ed8fdca882275c53fe9af9332629403e1060`.

Fix-round concerns: none. The one lease test transient passed in isolation and in the fresh covering retry. Live bounded network smoke and exact operational `120/114` acceptance remain intentionally unperformed; formal scoring, seven-dimension readiness, publication, and both official pools remain closed.
