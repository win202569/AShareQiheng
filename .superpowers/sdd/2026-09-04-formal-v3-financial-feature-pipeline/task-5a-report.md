# Task 5A implementation report

Base: `3938b16`. Scope: formal feature store/repository and their two test files.

## RED

Recovery restart/read-only, canonical/path/corruption regressions, and absent
repository API: 4 tests, 4 expected assertion failures because APIs were absent.
Command: `python -m unittest tests.test_formal_feature_repository tests.test_formal_feature_store.FormalFeatureStoreTests.test_recovery_after_restart_verifies_without_writing tests.test_formal_feature_store.FormalFeatureStoreTests.test_recovery_rejects_noncanonical_or_substituted_receipt_fields tests.test_formal_feature_store.FormalFeatureStoreTests.test_recovery_rejects_corrupt_files_and_canonical_manifest_header_mismatch -v`.

Detailed repository RED: 18 new repository assertions failed on the absent
module. The initial module-level fixture import also collected 26 already-existing
StateStore tests (44 total, 18 expected failures, no errors); replaced with a
module import to prevent duplicate discovery. Recovery GREEN: all 3 tests pass.

Historical reads validate
receipt/config/evidence provenance, not complete historical semantics: V6 lacks
the then-visible candidate/issue manifest. Current selection explicitly trusts
the provider's issue completeness and rebuilds with the unchanged Task 4 builder.

## Fixture diagnosis

First repository GREEN attempt: 18 tests, 3 errors. The three positive paths
(`test_current_uses_builder_input_once_and_selects_exact_correction`,
`test_historical_provenance_does_not_claim_complete_semantic_rederivation`,
`test_restart_exact_historical_returns_typed_detached_bundle_or_absence`) all
raised `ValueError: formal feature bundle is blocked` at the repository's signed
value gate. Minimal fixture diagnosis printed:
`blockers=('quarter_missing_prerequisite',), growth=100.0/derived, quarters=()`.
Task 4 requires Q3 for cumulative FY, H1 for Q3, and Q1 for H1. The fixture now
provides 20/45/75/100 cumulative facts for Q1/H1/Q3/FY; the positive setup asserts
no blockers and four comparable quarters. The production gate is unchanged.
A dedicated regression keeps FY-only input audit-only despite a derived annual
slot. Raw receipt manifest tamper/deletion uses the public snapshot manifest_path;
bootstrap fixtures intentionally have no producing task, so dedicated producer
task-receipt deletion remains covered by the required StateStore regression.

The four-test positive/FY-only diagnostic rerun passed (306.616 seconds,
exit 0). The first full required regression completed all 272 tests in
3427.942 seconds: one fixture failure, one existing Windows symlink skip.
The complete failure traceback was:

```text
FAIL: test_foreign_and_future_evidence_reject_despite_matching_files_and_sql
  (tests.test_formal_feature_repository.FormalFeatureRepositoryTests)
Traceback (most recent call last):
  File "tests/test_formal_feature_repository.py", line 293, in test_foreign_and_future_evidence_reject_despite_matching_files_and_sql
    with self.assertRaises(ValueError):
AssertionError: ValueError not raised
```

This was the second (time) assertion, not the foreign-security assertion.
Real fixture and public StateStore fact diagnostics both showed published and
effective `2026-03-20T08:00:00+00:00`, source update `None`, captured
`2026-09-04T08:00:00+00:00`. The test's alleged future cutoff was
`2026-03-20T08:15:00+00:00`, which legitimately allows that evidence.
Only the test changed: foreign evidence remains a separate rejection;
cutoff equal to 08:00 permits late capture, 07:59:59 rejects, and an explicitly
persisted 08:00:01 source update rejects at 08:00 but permits equality at
08:00:01. All three boundary tests passed in 1.383 seconds (exit 0).
The production cutoff and score-eligibility gates were not relaxed.

## Final GREEN

Required command (using the project virtual environment):
`python -m unittest tests.test_formal_feature_repository tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_state_store -v`.
Result: **274 tests in 46.052 seconds, OK (skipped=1), exit 0**.
The skip is the existing Windows symlink test: WinError 1314, unavailable
symlink privilege. Other path/race/recovery tests passed.

`python -m py_compile` over exactly the four scoped files and
`git diff --check` both passed with explicit exit-code guards (exit 0).
Before staging, status contained only the two scoped modified store files
and the two new repository files. No data fetch, production database change,
SQLite/WAL/SHM, or progress/report artifact is part of the code commit.

Historical provenance-only versus trusted complete current-input semantics
remain the accepted limitation, not a claim of historical input reconstruction.

## Commit handoff

Committed `e2b85fef97fb8ba144b8d38a5a2daaa1a603aebd`
(`feat: read verified formal feature bundles`). Staged name-list and cached
diff check verified exactly the four authorized files; commit stat is four
files, 925 insertions. Post-commit `git status --short` is empty. This report
remains ignored and uncommitted. No main-branch merge was performed.
Two independent final reviews reported no findings.
