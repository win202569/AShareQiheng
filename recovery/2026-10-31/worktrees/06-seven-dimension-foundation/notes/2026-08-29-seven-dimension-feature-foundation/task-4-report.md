# Task 4 Report — Financial-Fact, Feature-Bundle, and Quality-Issue Persistence

## Summary

Implemented the Task 4 persistence APIs in the existing SQLite state store:
`insert_financial_facts()`, `list_financial_facts()`, `put_feature_bundle()`,
`get_feature_bundle_row()`, `latest_feature_set()`, and keyword-only
`record_quality_issue()`. No second database or score table was added, and no
file under `data/` was opened, migrated, or modified.

## RED

The brief's relative `\.venv\Scripts\python.exe` does not exist inside the
isolated worktree, so the repository venv at
`D:\Projects\AShareQiheng\.venv\Scripts\python.exe` was used while keeping the
working directory in the isolated worktree.

- Required two-test RED: 2 tests errored with the expected missing-method
  failures: `StateStore.insert_financial_facts` and
  `StateStore.put_feature_bundle` were absent.
- Expanded seven-test RED: all new API targets failed because the requested
  persistence methods were absent.
- Boundary RED: after the first GREEN, the exact directory path
  `data/curated/formal_features` was shown to be incorrectly accepted; the
  unsafe-path test failed before the minimal prefix-boundary fix.

## GREEN and verification

- New Task 4 tests: 8 tests passed, covering financial-fact idempotency and
  revision retention, exact/empty snapshot filters, deterministic bundle
  conflict, trigger rollback, hash/path rejection, exact latest filters and
  full tie ordering, parsed JSON, and canonical quality details.
- Full state-store suite: 41 tests passed.
- Task 1 and Task 2 regressions: 17 tests passed.
- `py_compile` passed for `state_store.py` and `test_state_store.py`.
- `git diff --check` passed.
- Pre-commit diff and committed diff both contained only the two approved
  files; `data/` was absent.

## Transaction, conflict, and path evidence

- Financial-fact insertion materializes the iterable once, uses one immediate
  transaction, returns `(inserted, ignored)`, ignores an identical fact ID, and
  retains a revised fact with a different canonical ID.
- Feature headers and all feature values are written in one immediate
  transaction. A trigger abort on the `FS` value left zero `feature_set` and
  zero `feature_value` rows.
- `feature_set.id` and stored `bundle_hash` equal the bundle's canonical hash.
  A logical-key replay returns the existing ID only when the stored canonical
  header and complete value set match; changed canonical content raises
  `ValueError("non-deterministic feature conflict")` without updating the row.
- Bundle paths reject POSIX absolute paths, Windows drive-absolute paths,
  backslashes, traversal, the prefix directory without a child, and paths
  outside `data/curated/formal_features/`.
- `source_snapshot_ids=[]` returns an empty result, and nonempty snapshot IDs
  are matched with exact SQL `IN` semantics.
- Quality issue details use sorted, compact, Unicode-preserving canonical JSON.
- Latest feature selection filters contract/as-of exactly and orders by
  `as_of_utc DESC, created_at DESC, id DESC`; reporting JSON columns are parsed
  without joining or loading raw financial facts.

## Commit

- Commit: `cd43906599e17335409bb486ba5ed7cb1d9ac2e0`
- Message: `feat: persist financial facts and feature bundles`
- Files:
  - `ashare_pipeline/state_store.py`
  - `tests/test_state_store.py`

## Residual risk

This task persists and reads database metadata only. Atomic feature-bundle file
creation, on-read file hash verification, and orphan-file cleanup remain the
responsibility of the later feature writer/reader task. The current SQLite v2
quality-issue table deliberately leaves severity/code taxonomy validation to
the calling domain layer.

## Independent-review remediation — strict persisted JSON

The review found that Python's default `json.dumps()` behavior allowed NaN and
positive/negative Infinity tokens to reach persisted JSON. The shared
persistence serializer now explicitly uses `allow_nan=False` while retaining
`ensure_ascii=False`, sorted keys, and compact separators.

### RED

- Added a real-database regression over `math.nan`, `math.inf`, and
  `-math.inf` using subtests.
- Old behavior failed all three `ValueError` assertions and left 3
  `quality_issue` rows instead of 0 (`Ran 1 test`, 4 failures, exit 1).

### GREEN and no-residue evidence

- The focused rejection test and existing canonical Unicode JSON test both
  passed after the one-function serializer change.
- Task 4 targeted suite: 9 tests passed.
- Full state-store suite: 42 tests passed, covering every existing caller of
  the shared persisted-JSON serializer.
- Task 1 and Task 2 regressions: 17 tests passed.
- `py_compile` and `git diff --check` passed.
- Each invalid `record_quality_issue()` call raises before insertion; the
  temporary database assertion confirms `quality_issue` row count remains 0.
- No `data/` path was opened or changed; all database tests used their existing
  per-test temporary databases.

### Remediation commit

- Commit: `b3d0c0ce4ad669ad9499bf5a14b94f7de9673c89`
- Message: `fix: reject nonfinite persisted json`
- Committed files only:
  - `ashare_pipeline/state_store.py`
  - `tests/test_state_store.py`
