# Stage D Task 8 implementation report

Baseline: `ef89225241ba88dcd6171ec95ebc9fb9a160afbe`.
Worktree: `C:\Users\Lenovo\.codex\worktrees\formal-final-stage-d\AShareQiheng`.

## Scope and resulting schema

Only the four files in the Task 8 brief are implementation deliverables:

- `ashare_pipeline/state_store.py`
- `tests/test_formal_final_migration.py`
- `tests/fixtures/schema_v7.sql`
- `tests/test_state_store.py`

`SCHEMA_VERSION = 8`, `_V8_TABLE_DDL`, `_V8_INDEX_DDL`, and
`StateStore._apply_v8_migration(connection)` extend the contiguous V2–V7 ledger.
Migration runs within the existing short internal `BEGIN IMMEDIATE` transaction.
No public per-table write APIs, Stage D repository/publication logic, or later
Task 9–11 behavior was added.

Eight tables are created: `formal_final_run`, `formal_final_artifact`,
`formal_final_input`, `formal_final_scorecard`, `formal_final_status`,
`formal_final_eligibility`, `formal_final_pool_decision`, and
`formal_final_dependency`. Run headers hold input/result/root/frozen/universe/
coverage/code/contract identities. `run_id` and `created_at` are separate from
`result_hash`; input manifest and result hashes are intentionally nonunique so
independent replays can persist. Artifacts use `(run_id, artifact_kind)` keys,
canonical payload TEXT and `artifact_hash`. Members use `(run_id, security_id)`
keys; pool decisions additionally key by `pool_name`.

The schema uses no REAL columns. `S0`, `Sc`, `Sbase`, `B`, `R_safety`, and `C` are
TEXT projections; all richer canonical proof data remains JSON TEXT. Exact
Decimal lexical serialization, canonical hash verification, the exact five
artifact kinds, and proof semantics belong to Task 9's authenticated repository.
The orchestrator explicitly accepted this division and did not require artifact
kind enumeration or redundant B/C/D1–D3 hashes in the run header.

Run mode/status, member status, booleans, mutually exclusive pool qualifications,
pool prohibition implications, pool names, decision values, and selected ordinal
shape are constrained. Selected ordinals have a partial unique index scoped to
`(run_id, pool_name)`; nonselected decisions require NULL ordinals. Dependency
indexes support source identity/hash and effect scope/dependent key queries.
Composite foreign keys prevent children from borrowing a member or eligibility
from another run. Batch/global dependencies may omit `security_id`, but retain
their mandatory owning run foreign key.

## TDD and commands

All Python commands used the shared interpreter and fixed worktree, with
PowerShell `login:false` and escalated permission for this authorized managed
worktree outside the writable roots.

1. Required RED:

   ```powershell
   & D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration -v
   ```

   Five exact brief-named tests ran in 20.478s; exit 1, nine expected assertion
   failures. The ledger ended at V7 and V8 namespace objects were accepted.
   There were no import/setup errors.

2. Expanded RED, same command: eight tests ran in 46.110s; exit 1, twelve
   expected failures before production implementation. Additional tests cover
   actual Decimal TEXT roundtrips, replay identity, composite foreign keys,
   pool checks/ordinal uniqueness, missing/tampered/extra objects, failure after
   ledger insertion, and an actual failing SQLite connection commit.

3. First GREEN, same command: eight tests passed in 68.419s, exit 0.

4. Self-review identified case-insensitive SQLite namespace handling. Added:

   ```powershell
   & D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration.FormalFinalMigrationTests.test_v8_namespace_rejects_case_variant_extra_objects_before_and_after_migration -v
   ```

   An initial probe inadvertently placed the existing commit-test tail within
   the new method, causing three failures (two genuine namespace failures plus
   an unrelated snapshot mismatch). Corrected the test placement before the
   production fix and reran: one test, 17.524s, exit 1, exactly two expected
   namespace failures, before and after V8 migration. Changed the namespace
   scan to compare names/table ownership case-insensitively.

5. Focused GREEN, required migration command: nine tests passed in 72.561s,
   exit 0.

6. Exact required migration + state-store regression:

   ```powershell
   & D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration tests.test_state_store -v
   ```

   Result: **220 tests passed in 1057.777s, exit 0, OK**. No failures, errors,
   permission problems or temporary-directory cleanup errors. This includes
   nine Task 8 tests and 211 existing state-store regressions.

7. Scoped whitespace verification:

   ```powershell
   git diff --check -- ashare_pipeline/state_store.py tests/test_state_store.py tests/test_formal_final_migration.py tests/fixtures/schema_v7.sql
   ```

   Exit 0. An AST comparison against the exact baseline commit also exited 0:
   all V2–V7 schema declarations and V3–V7 migration methods exactly match the
   baseline. Existing state-store edits only advance eight ledger/version
   expectations to V8.

   A strengthened exact-source audit (including the annotated V4 index map)
   verified all twelve V2–V7 DDL declarations and all five V3–V7 migration
   methods preserve their baseline source text exactly; exit 0.

Repository-wide discovery is explicitly deferred to Task 11 by the orchestrator
under the existing ledger ruling; it was not run in Task 8. The focused and exact
state-store regression are the authorized verification scope for this task.

## Self-review evidence

- The fixture is a frozen literal of the released V7 schema, generated before
  implementation and containing real linked rows in all four range tables plus
  legacy `score_run`/`score_item` rows. Migration tests compare every original
  `sqlite_master` SQL entry and original ledger timestamp exactly, and compare
  the stored range/legacy row values exactly.
- Every V8 DDL interruption is injected in a real transaction and checked
  against the complete pre-migration snapshot. Failures after ledger insertion
  and at SQLite commit likewise preserve all old rows/schema/ledger and leave
  no V8 objects.
- Fresh initialization records exactly versions 2 through 8; repeated reopening
  leaves the complete snapshot unchanged.
- Every V8 table's extra-column DDL and missing-table corruption, every missing
  V8 index, unexpected attached indexes/triggers, unknown named tables/indexes/
  views/triggers, and uppercase namespace objects are rejected without advancing
  the ledger. SQLite's expected primary-key autoindexes are the only implicit
  V8 objects accepted. Approved table/index SQL uses the existing exact token
  normalizer, preserving CHECK literal spelling/values.
- Foreign-key, primary-key, pool decision CHECK, selected-ordinal type/shape,
  ordinal uniqueness, replay acceptance, long Decimal TEXT and absence of REAL
  columns are exercised through actual SQLite inserts, not mocked assertions.
- No schema objects, data, legacy DDL, V7 migration, or public write APIs were
  repurposed. Hash serialization/publication/revalidation remain subsequent-task
  responsibilities; this task claims only schema/migration behavior.

## Commit boundary

Commit: `671793e97b8897d00cf5dcbe94f4410e701d4f78`
(`feat: add formal final scoring schema v8`).

After the successful regression, `git diff --cached --check` exited 0;
`git diff --cached --name-only` contained exactly the four authorized files.
`git commit -m "feat: add formal final scoring schema v8"` exited 0, and
`git show --format=fuller --stat HEAD` confirmed four files, 752 insertions,
11 deletions. Final `git status --short` showed only the pre-existing plan edit.

The report itself, pre-existing plan change, task ledger, runtime SQLite/WAL/SHM,
data and backups are excluded from the commit. No subagents were spawned.

Status: Task 8 implementation and required verification complete. No unresolved
Task 8 concerns. Independent external review remains the orchestrator's next
gate; Task 9 repository semantics and Task 11 full-project verification are
intentionally outside this task.

## Independent review fix round 1 of 5

The reviewer found one Important defect in the initial commit: the V8 object
allowlist compared names without their SQLite object types. SQLite permits a
trigger to share a table or index name, so an extra trigger named exactly
`formal_final_run` (or another approved object) could pass the namespace scan
and the normal DDL checks. The initial no-concerns status above describes the
pre-review implementation; this section supersedes it for the reviewed defect.

Added two behavioral regressions:
`test_v8_table_named_trigger_rejects_without_advancing_ledger` and
`test_v8_index_named_trigger_rejects_without_advancing_ledger`. They exercise
all eight literal V8 table names and all four literal index names across three
real SQLite scenarios: before migration on a legacy `score_run` table, after
migration on that legacy table, and after migration on `formal_final_run`.
Each attempted reopen must reject the extra trigger and preserve the exact
schema, ledger timestamps, and released range/legacy rows. A test-only helper
drops each synthetic trigger after the assertion so the scenarios remain
independent. There are 36 trigger-collision scenarios in total.

RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration.FormalFinalMigrationTests.test_v8_table_named_trigger_rejects_without_advancing_ledger tests.test_formal_final_migration.FormalFinalMigrationTests.test_v8_index_named_trigger_rejects_without_advancing_ledger -v
```

Result: two tests in 30.335s, exit 1, 24 expected `RuntimeError not raised`
failures (all post-migration cases), no errors. The 12 pre-migration cases
already rejected premature objects correctly. Production code was changed
only after this RED completed.

The fix builds exact approved `("table", name)` and `("index", name)` pairs.
The only implicit-object exception remains an index with NULL SQL named
`sqlite_autoindex_<known V8 table>_1`, when V8 is applied; it now also explicitly
requires the owning table to be in `_V8_TABLE_DDL`. Unknown objects and all
triggers remain unapproved regardless of a colliding name or owning table.
No DDL, migration ledger semantics, repository API, fixture, or legacy behavior
was changed.

GREEN and regression commands:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_migration tests.test_state_store -v
```

Focused GREEN: **11 tests passed in 159.589s, exit 0, OK**. Exact migration plus
state-store regression: **222 tests passed in 758.587s, exit 0, OK**, including
11 migration tests and 211 state-store tests. No failures, errors, permission
problems, or temporary-directory cleanup errors. The full exact regression is necessary
because the validation helper participates in general `StateStore.initialize`.
The existing missing/tampered/extra-object, atomic migration, reopen, uppercase
namespace, foreign-key, precision, replay, and V2–V7 preservation checks remain
in the focused suite.

Fix commit: `ec8781a0a3413f3a1f7f3c13d91974a6a6f2a3f3`
(`fix: reject formal final schema trigger name collisions`).

Scoped `git diff --check` and staged `git diff --cached --check` both exited 0.
`git diff --cached --name-only` contained exactly `ashare_pipeline/state_store.py`
and `tests/test_formal_final_migration.py`. The commit exited 0 and recorded
two files, 40 insertions and two deletions. Final `git status --short` showed
only the pre-existing plan edit. The report, plan, ledger, fixtures, data and
runtime SQLite/WAL/SHM were excluded; no subagents were spawned.

Self-review: the approved pairs cannot admit a trigger even when its name is
identical to an approved table or index; the autoindex exception requires the
correct type, NULL SQL, known owner, expected PK-index name and applied V8.
The real trigger matrix proves rejection on both legacy and V8 owners, before
and after migration, without schema/data/ledger mutations. All previous exact
DDL, missing/extra/tampered object and atomicity tests still pass. The reviewed
Important defect is addressed and the fix is ready for independent re-review.
