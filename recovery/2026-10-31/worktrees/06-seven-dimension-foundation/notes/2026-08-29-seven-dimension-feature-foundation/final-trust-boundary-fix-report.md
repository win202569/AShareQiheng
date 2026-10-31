# Final trust-boundary fix report

## Scope and baseline

- Requirements authority: `final-trust-boundary-fix-brief.md`.
- Worktree: `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation`.
- Branch: `feature/seven-dimension-foundation`.
- Verified pre-edit `HEAD`: `e8c7ed8fdca882275c53fe9af9332629403e1060`.
- No subagents/reviewers, network, tracked/runtime data, migrations, formal scoring, stock-pool publication, or operational `120/114` acceptance were used.
- Python: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe`.
- Test TEMP/TMP/TMPDIR stayed beneath worktree-local `.final-trust-boundary-temp`.

## Root-cause reproduction and genuine RED

Tests were added before any production edit. They used real builders, canonical facts and snapshots, public artifact write/read, StateStore first/idempotent boundaries, and real status/progress. The focused RED command was:

```powershell
$env:TEMP='D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation\.final-trust-boundary-temp'; $env:TMP=$env:TEMP; $env:TMPDIR=$env:TEMP; New-Item -ItemType Directory -Force $env:TEMP | Out-Null; D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FeatureBundleBuildTests.test_builder_recomputes_balance_equation_when_caller_omits_blocker tests.test_state_store.StateStoreTestCase.test_balance_equation_semantics_reject_forged_ready_partial_and_blocked tests.test_state_store.StateStoreTestCase.test_balance_equation_is_reauthenticated_before_idempotent_success tests.test_state_store.StateStoreTestCase.test_balance_equation_accepts_exact_tolerance_and_missing_triplet tests.test_orchestrator.OrchestratorTestCase.test_progress_rejects_bundle_industry_that_mismatches_current_context tests.test_orchestrator.OrchestratorTestCase.test_general_ready_round_trips_through_verified_storage_and_progress tests.test_orchestrator.OrchestratorTestCase.test_progress_reauthenticates_balance_equation_without_fallback tests.test_orchestrator.OrchestratorTestCase.test_progress_ignores_only_future_feature_bundle tests.test_orchestrator.OrchestratorTestCase.test_future_bundle_does_not_suppress_exact_cutoff_visible_bundle
```

Reliable checkpoint summary:

- `Ran 9 tests in 1.705s`.
- `FAILED (failures=9)`: nine expected assertion/subtest failures were recorded across the negative cases.
- Two positive-control test methods passed.
- The exact raw unittest progress-glyph line was not retained, so this report does not reconstruct or claim one.

The nine failures were expected and specific:

1. Builder trusted omitted `balance_equation_mismatch` and returned `financial_ready` for canonical facts with FY2021 assets `10000`, liabilities `300`, equity `600`.
2. StateStore accepted the same semantic omission when relabelled `financial_ready`.
3. StateStore accepted the same semantic omission when relabelled `partial`.
4. StateStore accepted a balanced bundle relabelled `blocked` with a forged mismatch marker.
5. StateStore returned idempotent success for a pre-existing exact forged row instead of reauthenticating facts.
6. Progress counted an authenticated `general_nonfinancial` bundle for a currently unclassified candidate.
7. Progress counted an imbalanced forged newest bundle and thereby suppressed the valid older bundle.
8. Progress counted a future-only `2026-09-10` bundle at the earlier status time.
9. A future utility bundle suppressed an exact-cutoff visible general bundle (`template_counts` selected utility instead of general).

The exact-tolerance/missing-triplet StateStore method and matching-context round-trip were the two positive-control methods embedded in the focused set; both passed at the pre-edit checkpoint.

## Implementation

### Shared balance authority

- `ashare_pipeline/financial_schema.py` now owns `balance_equation_blockers`, preserving the prior exact applicability (complete assets/liabilities/equity triplet per security/period), unit handling, and tolerance `max(1000.0, 0.001 * abs(assets))` with strict `>` mismatch.
- `select_visible_facts` and `build_feature_bundle` both consume that authority. The latter closes the caller-supplied blocker omission path without duplicating the equation.
- `StateStore._validate_feature_bundle_evidence` gathers only the exact canonical observed raw facts after DB fact/snapshot/evidence authentication, recomputes the shared invariant, compares the semantic marker in both directions, and requires mismatch bundles plus all financial dimensions to be blocked. This method already runs inside the first insert transaction, before idempotent success, and from verified progress in its read transaction.
- Missing triplets remain non-applicable; equality at the exact tolerance remains valid; no-evidence bundles reject a forged mismatch marker without inventing facts.

### Current candidate context

- `build_deep_progress` retains verified artifact, exact DB header/children, and evidence checks, then binds `bundle.industry.name` exactly to `context.industries[security_id]` and the bundle template identity to `resolve_template` for that current name.
- A mismatch consumes the visible newest row as one bounded unknown and does not fall back. Existing matching-context general and unclassified paths remain covered by production-path tests; the affected suite covers all registered template families.

### Outer status-time visibility

- The `feature_set` query now applies canonical `as_of_utc <= now_utc` before ordering/newest-per-security selection.
- Canonical storage uses normalized `+00:00`, so the indexed text comparison is temporally ordered and equality remains visible.
- Future rows neither count nor mark a security seen, so they cannot suppress the newest visible row.

### Test fixture correction discovered during GREEN

The first post-implementation focused run was `Ran 9 tests in 1.459s`, `FAILED (failures=4)`. The four remaining failures all used bundle `as_of_utc=2026-08-29T16:00:00Z` but status `2026-08-29T20:00:00+08:00`, which is `12:00:00Z`, not equality. The new cutoff correctly excluded those fixtures. Their status time was corrected to `2026-08-30T00:00:00+08:00`, exactly `16:00:00Z`; the future-only test retained the earlier status.

The first affected run similarly reported `Ran 294 tests in 116.613s`, `FAILED (failures=12)`: legacy corruption/progress fixtures expected their default `16:00Z` bundles to be visible at `20:00+08` (`12:00Z`). Only tests whose purpose requires a visible record were corrected to the exact cutoff. A focused orchestrator rerun then reported `Ran 57 tests in 34.637s`, `OK`.

## GREEN and verification

Focused command was the same nine-test command shown above. Final result:

```text
.........
----------------------------------------------------------------------
Ran 9 tests in 1.558s

OK
```

Affected-suite command:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features tests.test_financial_formulas tests.test_feature_contract tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e
```

Result:

```text
Ran 294 tests in 131.214s
OK
```

Fresh complete offline command, with TEMP/TMP/TMPDIR set to `.final-trust-boundary-temp\full`:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

Result:

```text
Ran 399 tests in 119.081s
OK
```

After path-specific staging of only the eight authorized files, the same complete command was rerun with TEMP/TMP/TMPDIR set to `.final-trust-boundary-temp\staged-full`:

```text
Ran 399 tests in 83.320s
OK
```

Working and staged `git diff --check` both exited 0 (working inspection printed only Git's existing LF-to-CRLF informational warnings). Staged scope was exactly:

```text
ashare_pipeline/financial_features.py
ashare_pipeline/financial_schema.py
ashare_pipeline/orchestrator.py
ashare_pipeline/state_store.py
progress.md
tests/test_financial_features.py
tests/test_orchestrator.py
tests/test_state_store.py
```

There were no unstaged differences in those files. `.superpowers`, all temporary/controller directories, `data`, runtime DBs, and unrelated files were not staged.

## Takeover audit and fresh GREEN evidence

- The takeover began after two prior execution contexts stopped reporting. By then the branch had advanced to commit `56b0343ce1781e5138fb5de66cb1db8e1e6c5596`, the eight authorized tracked files were clean, and this report already existed. Process inspection found no running `python`/`pythonw` process, so there was no lingering test command to stop. The report's affected/full runs of 116-131 seconds are the available evidence for the silence being an execution-yield/reporting issue rather than an unfinished mutation.
- The nine-test RED result above is inherited evidence captured against pre-edit `e8c7ed8fdca882275c53fe9af9332629403e1060`; the takeover did not rerun or claim a post-edit reconstruction as RED.
- Fresh takeover focused verification at the committed tree ran the same nine-test command and reported `Ran 9 tests in 1.588s`, `OK`.
- A first takeover affected-suite run used an unnecessarily long worktree-local TEMP path and reported `Ran 294 tests in 105.012s`, with two unrelated failures in the longest calendar-cache subtest directory names. The exact failing test passed `1/1` in `2.213s` under a shorter worktree-local TEMP path, confirming Windows path-length pressure in the verification harness. The affected suite was then rerun under `.ftb2\affected` and reported `Ran 294 tests in 48.996s`, `OK`.
- Fresh takeover complete offline verification under `.ftb2\full` reported `Ran 399 tests in 85.956s`, `OK`. This exercised the committed tree, which is the exact tree recorded by the inherited staged-tree verification above.

## Commit, self-review, and concerns

- Commit: `56b0343ce1781e5138fb5de66cb1db8e1e6c5596` (`fix final feature trust boundaries`).
- Self-review confirmed: public `FeatureBundle` parsing remains context-free; DB reference validation remains transaction-bound; candidate matching occurs only after file/DB/evidence authentication; cutoff precedes newest selection; no formula authority, schema, scoring, pool, or deferred-Minor scope was changed.
- Formal gates remain closed: `formal_score_ready=false`, `seven_dimension_ready=false`, official pool counts remain zero.
- Concerns: none within the authorized scope. Live bounded network smoke and exact operational `120/114` acceptance remain intentionally unperformed.

## Evidence correction

- A documentation-only follow-up removed the earlier unsupported claim that `FFFFFFFFF` was the exact raw unittest progress line. The reliable retained evidence is: 9 test methods ran, 9 expected assertion/subtest failures were recorded across negative cases, and 2 positive-control methods passed. Commands, failure descriptions, GREEN evidence, tracked files, and commit state were unchanged.
