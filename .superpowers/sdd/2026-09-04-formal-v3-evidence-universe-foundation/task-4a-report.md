# Task 4A Report — V5 schema migration and literal V4 fixture

## Status and commit

- Status: implemented and committed.
- Commit: `438900f` (`feat: add formal v5 schema migration`).
- Scope: additive V5 schema/migration only. No formal queue, snapshot/receipt writer, universe persistence, or status persistence APIs were added.

## TDD evidence

### RED

Command:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_initialize_migrates_literal_v4_database_to_v5_without_changing_legacy_rows
```

Result before production changes: expected failure, 1 test run. The assertion observed ledger rows `[(2,), (3,), (4,)]` instead of the required `[(2,), (3,), (4,), (5,)]`. The literal V4 fixture itself loaded successfully, isolating the missing V5 migration.

### Focused GREEN

The same command passed after the minimal V5 migration implementation: 1 test run, `OK`.

Final focused migration matrix command covered literal V2 and V4 migration, idempotent initialization, incomplete/corrupt schema rejection, discontinuous ledger rejection, V2-prefix migration, V3-prefix migration, and transactional rollback on an occupied V3 index name. Result: 9 tests run in 7.572s, `OK`.

## Migration choices

- Raised `SCHEMA_VERSION` from 4 to 5.
- Added all eight requested formal tables through `_V5_TABLE_DDL` and the two requested snapshot indexes through `_V5_INDEX_DDL`.
- Used `TEXT` for identifiers, hashes, paths, JSON, and timestamps; formal refresh generations are nonempty `TEXT`; task statuses and universe statuses use checks matching the approved closed sets.
- Added the unique lineage expression index over `(request_fingerprint, refresh_generation, COALESCE(producing_task_id, 'bootstrap'))` and an exact-request lookup index beginning with `(source, dataset, request_fingerprint)`.
- Added required primary keys, unique constraints, and foreign keys. Universe status uses a composite foreign key to the corresponding universe member. Snapshot rows may reference their producing task, while receipts reference task and snapshot; no circular snapshot-to-receipt foreign key was introduced.
- Extended initialization to accept only continuous prefixes `{2}`, `{2,3}`, `{2,3,4}`, and `{2,3,4,5}`. V5 is applied within the existing immediate transaction only after V2/V3/V4 DDL validation. Partial V5 tables under a V4 ledger are rejected.
- The migration performs DDL and ledger insertion only; it never selects from or copies legacy `source_snapshot`.

## Literal V4 fixture and legacy preservation

- `tests/fixtures/schema_v4.sql` is literal SQL containing the exact V2 tables/index, V3 financial/feature tables and indexes, V4 `quality_issue_binding`, and migration-ledger rows 2/3/4.
- Successful migration of the literal fixture through the runtime V2/V3/V4 DDL validators proves the historical DDL matches the accepted schemas.
- The focused V4 test seeds legacy `source_snapshot` and `score_run`, compares complete rows before and after initialization, verifies the formal source table is empty, and verifies a `2,4` historical ledger is rejected.
- Relevant legacy regression: `python -m unittest -v tests.test_state_store` ran 108 tests in 166.833s, all `OK`.

## Full-suite attempt

- The initial unqualified `python -m unittest discover -v` was non-evidentiary because it discovered 0 tests; it was not treated as a pass.
- The documented full command `python -m unittest discover -s tests -p "test_*.py" -v` was attempted once. It emitted only passing results through the complete deep-worker module and subsequent feature-contract tests. During `test_feature_foundation_e2e.FeatureFoundationEndToEndTests.test_three_security_replay_is_traceable_deterministic_and_nonformal`, it produced no new output for 60 seconds and was stopped as a bounded attempt per controller direction. No assertion failure and no documented deep-worker 2-second lease flake appeared. This incomplete full-suite attempt is distinct from the clean targeted StateStore result.

## Files

- `ashare_pipeline/state_store.py`
- `tests/test_state_store.py`
- `tests/fixtures/schema_v4.sql`

## Self-review and concerns

- `git diff --check` passed; only the three scoped implementation/test/fixture files were committed, and no SQLite/WAL/SHM artifacts were present under the fixture directory.
- Reviewed every requested table/column, PK/unique/FK relationship, both required indexes, continuous-ledger branches, validation ordering, and the absence of legacy-row copy SQL.
- No schema ambiguity remains for Task 4A. The only concern is that the repository-wide suite did not complete because the long feature-foundation E2E test became silent for the agreed 60-second bound; targeted migration and legacy StateStore suites are clean.
