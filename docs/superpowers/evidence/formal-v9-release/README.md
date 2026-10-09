# V9 release foundation acceptance

Date: 2026-10-09. Implementation base: `ede86a6` on
`codex/formal-final-stage-d`. This section covers Task 1 foundation only,
not a working release validator, publisher or production release.

## Implemented

- Exact release gate/DTO types, strict canonical JSON, finite lossless Decimal
  strings, immutable containers with nested rechecks, full Git revision/hash checks.
- Validation/preparation domain-separated signature messages bound to key ID and
  exact canonical bytes. Cryptographic validation of a DTO is not live authority.
- Preparation retains raw canonical manifest JSON and checks its SHA-256 and byte
  size; renderer-specific manifest semantics remain a later task.
- Safe relative payload paths, absolute normalized target identity, Windows device
  and case-alias rejection, parent conflicts and reserved manifest-file exclusion.
- Additive V9 five-table migration with candidate/validation/preparation composite
  foreign keys, exclusive release identity/path, file path case uniqueness and
  status/size/fencing structural constraints. No public publication writer exists.
- Static complete V8 SQL fixture including data in all eight Stage D tables,
  inherited V7 range rows and legacy score rows. It is a storage fixture, not a
  genuine official scoring proof or approved production data.

## Verification

Tests ran from the managed Stage D worktree using
`D:/Projects/AShareQiheng/.venv/Scripts/python.exe`, with `TMPDIR`, `TEMP`, `TMP`
set to `D:/Projects/AShareQiheng/.tmp` before imports, and
`PYTHONDONTWRITEBYTECODE=1`.

Final foundation command after all foundation code/schema edits:

```text
python -m unittest tests.test_formal_release_types tests.test_formal_release_migration tests.test_formal_final_migration tests.test_state_store
```

Result: **243 tests, 56.802 seconds, OK** (types 12, V9 migration 9,
V8 migration 11, StateStore 211). RED baselines were observed for missing
types/migration, nested tampering, path aliases, manifest/device collisions and
missing raw manifest binding before their respective implementations.

Tests cover exact V2–V8 DDL/row retention, contiguous historical migrations,
repeat initialize, DDL/ledger/commit rollback, wrong composite bindings,
partial/tampered/missing schema, foreign triggers/indexes/views and future ledgers.
Old test version assertions were updated to V9 without dropping old-data checks.

Final affected Stage D regression command on the final V9 schema:

```text
python -m unittest tests.test_formal_final_atomicity tests.test_formal_final_repository tests.test_formal_coverage_manifest tests.test_formal_workspace_trust
```

Result: **58 tests, 220.587 seconds, OK**. The earlier run of the same command
also passed (191.672 seconds); the final run was repeated after the raw manifest
column was added. Together the two final named commands cover 301 passing tests.
Complete Stage D regression log is retained locally at
`D:/Projects/AShareQiheng/.tmp/v9-foundation-stage-d-regression.log`.

Independent read-only review verified 19 earlier focused tests and 11 existing
migration tests. It found one Important manifest ancestor conflict and one Minor
superscript device alias; both were reproduced RED then fixed. The subsequently
added raw manifest binding was author-reviewed and tested, not independently
re-reviewed. No claim of a final zero-finding independent review is made.

## Scope decisions and remaining work

- Writer mutation authority, append-only API enforcement, leases and release
  lifecycle belong to Task 3; an empty `formal_release_repository.py` was not added
  to Task 1. No DTO or stored row currently exposes a release publishing API.
- Finite exponent Decimal strings remain lossless; display formatting is Task 4.
- Native PowerShell/unittest and a durable local ledger replace Bash bookkeeping
  helpers in this Windows iteration. The ledger is not part of the code commit.
- Production database and evidence were not migrated or modified by this task.
- The full multi-hour project discovery/performance suite was not run for this
  foundation task; results above are the named affected suites, not all-project GREEN.
- Tasks 2–6 remain pending, including the live official validator, trusted writer,
  deterministic renderer/publisher, signed recovery, reporting/CLI and end-to-end tests.

## Task 2 prerequisite: source checkpoint and own V9 writes

The existing source checkpoint treated release audit appends as source changes.
The audit-append regression reproduced `final current-source database evidence
changed` before the fix. Only row contents of the five exact V9 bookkeeping
tables are now excluded; their DDL and unknown release-prefixed source tables
remain part of the checkpoint. Existing V8 history exclusions are unchanged.

`python -m unittest tests.test_formal_release_validation_guards` passed 5 tests
in 0.522 seconds. These use a real migrated SQLite database and genuine current
input provider, not mocked source guards. The database fixture is storage-only:
it neither issues signed validations nor creates release capabilities.

The initial affected command (four guard tests loaded before the fifth was
added) ran `tests.test_formal_release_validation_guards`,
`tests.test_formal_release_types`, `tests.test_formal_release_migration` and
`tests.test_formal_final_atomicity`: **45 tests OK in 281.513 seconds**.
The final command with all five guards, the two release foundation suites and
`tests.test_formal_final_atomicity.FormalFinalAuthorityBoundaryTests` passed
**31 tests in 2.217 seconds**. These are named affected regressions, not a
full-project discovery run; no complete Task 2 or all-project GREEN is claimed.

This is a prerequisite change, not completion of Task 2. The configured live
validator, producer replay and twelve-gate capability are still pending.
