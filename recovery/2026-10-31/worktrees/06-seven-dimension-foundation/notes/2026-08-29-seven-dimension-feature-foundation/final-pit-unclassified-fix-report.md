# Final PIT / unclassified remediation report

Date: 2026-08-31

Baseline: `dd1e3322dfa73c7c53ca7c0944544c895b781789`

## Independent reproduction and root cause

Before changing production code, I exercised the public serialized parser and isolated real `write_feature_bundle -> StateStore -> read_verified_feature_bundle -> status/progress` path.

- A non-financial observed value and a financial-ready derived value both accepted evidence whose absolute effective instant was later than the bundle `as_of_utc`.
- A canonical ready bundle with canonical source snapshots and financial facts could be relabelled to an earlier `as_of_utc`; the existing/idempotent `StateStore.put_feature_bundle` path returned success.
- A newest canonical artifact whose evidence became future-effective after its header/as-of was forged still passed verified read and would be selected rather than bounded as unknown; the older valid row was therefore not the relevant current-member result.
- A builder-produced `unclassified` bundle could be relabelled `partial`, have `industry_template_unclassified` removed, and cross real file, database, verified-read, and progress boundaries.

Root cause: `FeatureBundle.validate()` normalized evidence and bundle timestamps individually but did not enforce their cross-field PIT ordering. It also had ready and specialized-template semantics but no complete invariant for the registry's `unclassified` template. StateStore and progress intentionally rely on the public bundle contract plus the existing DB evidence existence/equality validator, so the missing contract invariant propagated through every boundary.

## Genuine RED

Command (worktree-local `TEMP`, `TMP`, and `TMPDIR` were all `.final-pit-temp`):

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract.FeatureContractTests.test_public_parse_enforces_point_in_time_cutoff_for_all_evidence tests.test_feature_contract.FeatureContractTests.test_public_parse_keeps_unclassified_blocked_with_zero_coverage tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_future_fact_on_idempotent_success_path tests.test_orchestrator.OrchestratorTestCase.test_equal_effective_instant_persists_reads_and_counts_ready tests.test_orchestrator.OrchestratorTestCase.test_progress_rejects_newest_future_evidence_artifact_without_fallback tests.test_orchestrator.OrchestratorTestCase.test_forged_unclassified_partial_cannot_cross_real_boundaries tests.test_orchestrator.OrchestratorTestCase.test_builder_unclassified_persists_reads_and_counts_blocked
```

Result: exit code 1, `Ran 7 tests`, `FAILED (failures=9)`.

Exact expected failures:

- 2 public PIT subtests: observed non-financial partial and derived financial-ready evidence were not rejected.
- 4 public unclassified subtests: partial with blocker, partial without blocker, blocked without blocker, and non-zero coverage were not rejected.
- 1 StateStore regression: future canonical evidence was accepted on the existing/idempotent success path.
- 1 newest-artifact regression: verified read did not raise for the forged PIT artifact.
- 1 real unclassified boundary regression: the forged partial bundle crossed write/store/read.

The exact-equality canonical-fact path and the valid builder-produced unclassified blocked path already passed, confirming that the RED was specific to the two missing invariants.

## Minimal implementation

Changed production authority only in `ashare_pipeline/feature_contract.py`:

- After canonical UTC normalization, parse the normalized bundle `as_of_utc` and every `EvidenceRef.effective_at_utc` with timezone-aware `datetime.fromisoformat`; reject any evidence instant strictly greater than the bundle instant. The traversal covers every dimension, every value status, and every evidence item. Equality remains allowed.
- Resolve the existing registered industry template and require `unclassified` bundles to be `blocked`, coverage `0.0`, and contain `industry_template_unclassified`.

No second policy implementation was added to StateStore or progress. New-file persistence and the idempotent path both begin with `bundle.validate()`. Verified reads parse through `FeatureBundle.from_dict()`, and progress reuses verified read before the existing StateStore DB evidence existence/consistency check. Thus the single public contract authority closes file, transaction, read, and progress boundaries while retaining the transaction-bound DB fact/snapshot validator.

## Tests and changed files

- `tests/test_feature_contract.py`: adversarial public payloads across observed/derived and partial/ready states, timezone-offset absolute comparison, exact equality and earlier-positive cases, complete unclassified table.
- `tests/test_state_store.py`: canonical facts and snapshots plus the existing/idempotent success-path attack, with row/value cardinality preserved.
- `tests/test_orchestrator.py`: real equality persistence/read/ready count; newest-invalid/no-fallback bounded unknown; forged unclassified negative boundary; builder unclassified blocked positive boundary; all formal/seven-dimension/pool gates remain closed.
- `progress.md`: truthful post-repair status, fresh full-suite evidence, review gates, unperformed bounded network/`120/114` acceptance, and closed formal/pool gates.

## GREEN and verification

All commands used `D:\Projects\AShareQiheng\.venv\Scripts\python.exe` and the worktree-local `.final-pit-temp` for all three temporary-directory variables.

1. Focused new regressions: exit 0, `Ran 7 tests in 0.737s`, `OK`.
2. Required related modules (`test_feature_contract`, `test_financial_features`, `test_state_store`, `test_deep_worker`, `test_orchestrator`, `test_feature_foundation_e2e`): exit 0, `Ran 265 tests in 81.681s`, `OK`.
3. Full discovery before staging: exit 0, `Ran 370 tests in 95.542s`, `OK`.
4. Fresh full discovery after path-specific staging: exit 0, `Ran 370 tests in 73.484s`, `OK`.
5. Working and staged `git diff --check`: clean (only Git's pre-existing line-ending notices were emitted).
6. Staged scope: exactly five files, 358 insertions and 1 deletion: production contract, three directly relevant test modules, and tracked `progress.md`.
7. `git status --short` showed only those five staged files plus untracked `.final-pit-temp/` and controller-owned `.tmp-tests/`; inaccessible `.tmp-root-check/` remained untouched. No `.superpowers`, temp, data, database, network artifact, or unrelated file was staged.

## Self-review

- The PIT comparison is instant-based, not lexicographic, and is strict only for `>`; equality is covered at public and real DB/file/progress boundaries.
- Traversal is not coupled to raw financial slots, so non-financial and derived evidence cannot bypass it.
- Unclassified policy uses the already-resolved registry template identity and does not copy a template-ID table.
- DB evidence existence/field equality and canonical source-snapshot checks were not weakened or duplicated.
- Formal score readiness, seven-dimension readiness, and both official pools remain false/empty in all new progress regressions and in public progress.
- Deferred heartbeat, absolute-path containment, plan-table-name, networking, runtime data, migrations, scoring, and pool publication were not touched.

## Commit

`ee1a5d78e4e1d123ddd002c54c80bda8f41fd133` (`fix: enforce feature evidence PIT boundaries`)

## Concerns

None. The controller-owned `.tmp-tests/` and inaccessible `.tmp-root-check/` noise remain intentionally untouched and untracked.
