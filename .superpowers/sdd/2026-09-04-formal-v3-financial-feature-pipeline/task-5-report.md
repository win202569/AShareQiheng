# Task 5 implementation report

RED: `python -m unittest tests.test_state_store.FormalV6PersistenceTests -v`.
7 initial behavioral cases failed against absent V6 migration and persistence APIs.
Migration returned [2,3,4,5] instead of [2,3,4,5,6]; new APIs were absent.
One test cleanup initially retained a sqlite connection; fixture now explicitly
closes connections. Production changes had not begun at this point.

Subsequent RED: receipt source-kind rejection and expiry resampling both failed
before narrow V5 hardening; absent bundle APIs also failed. After implementation,
the signed feature child/root source hash mismatch case failed, then passed after
explicit source/mapping root comparisons. Unicode C1 task-filter control rejection
also failed before printable-token validation and passed afterward.

GREEN: 26 focused `FormalV6PersistenceTests` pass. Required regression
`python -m unittest tests.test_state_store tests.test_formal_financial_schema
tests.test_formal_feature_contract tests.test_formal_feature_store -q` passes:
268 tests, 0 failures/errors, 1 known Windows direct symlink privilege skip,
91.001 seconds. The final small Unicode token hardening was independently rerun
through all 26 focused cases after the broad run began. Compilation and
`git diff --check` pass; Git only warns about configured LF/CRLF conversion.

Implemented exact V6 additive migration, immutable formal source facts and
quarter rederivation, signed raw registry envelopes/root persistence, live verified
bundle audit persistence, detached metadata getter, generic task listing,
source circuits, and the three scoped V5 receipt/dependency hardenings.
Legacy schema assertions now expect version 6, with legacy row preservation
still checked. No legacy records serve as formal evidence.

Limits: provenance validation does not reparse raw numeric values (Task 6);
the feature getter returns metadata, not a trusted recovered bundle (Task 5A).
No full historical Task4 input-manifest reconstruction is claimed.

Tracked scope exactly `ashare_pipeline/state_store.py` and
`tests/test_state_store.py`. No data, SQLite, WAL/SHM, brief, ledger, or report is
staged. Initial transient test directory from a connection-cleanup fixture bug
was removed by exact path after closing handles; current worktree has no such
untracked artifacts. No unresolved API blocker.

Commit: `3938b16a213ba02bd12b5a7f0a42845e26b4b614`
(`feat: persist formal v3 facts and features`). Postcommit `git status --short`
is empty; only the two authorized tracked files are present in the commit.

Final independent review: three fresh read-only review lanes found no
reproducible issue: (1) V6 migration/DDL and V5 task ownership/lease/circuit
boundaries, (2) fact and quarter provenance/rederivation boundaries, and
(3) registry/feature receipt and evidence boundaries. Each independently ran
the 26 focused V6 persistence tests successfully.

Root final verification at `3938b16`: the required four-module regression
ran 268 tests in 145.781s and passed with one expected Windows symlink
privilege skip; `py_compile ashare_pipeline/state_store.py
tests/test_state_store.py`, `git diff --check 1eef9a6..HEAD`, and
`git status --short` all passed/clean. Task 5 is accepted.
