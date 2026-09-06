# Task 4B1 Report — formal task enqueue and dependency foundation

## Status and commit

- Status: implemented, verified, and committed.
- Commit: `34cff9b` (`feat: add formal task enqueue semantics`).
- Commit scope: only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- Baseline: approved Task 4A commit `438900f` with a clean worktree.

## TDD evidence

### Baseline

Command:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store
```

Result before Task 4B1 changes: 108 tests run in 166.521s, `OK`.

### RED

The first focused contract test was written before production changes and run as:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store.StateStoreTestCase.test_formal_task_contract_exact_replay_and_initial_public_row
```

Result: expected assertion failure, 1 test run, exit 1. `FORMAL_TASK_STATES` was absent (`None` rather than the required six-state set), isolating the missing formal task contract before any queue implementation existed.

During self-review, a second focused RED exposed Python JSON key coercion:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store.StateStoreTestCase.test_formal_task_snapshots_caller_payload_and_rejects_invalid_inputs
```

Result before the minimal correction: expected assertion failure for `{1: "coerced-key"}`, 1 test run, exit 1. Canonicalization had accepted the integer key by silently converting it to a JSON string. Recursive JSON-object key validation was then added.

### GREEN

Focused Task 4B1 command:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v -k formal_task tests.test_state_store
```

Result after implementation and fixture correction: 10 tests run in 5.469s, `OK`.

Required final StateStore regression command:

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_state_store
```

Result: 118 tests run in 161.710s, `OK` (108 pre-existing tests plus 10 Task 4B1 tests).

## Contract and implementation decisions

- Added a separate `FORMAL_TASK_STATES` set with exactly `pending`, `leased`, `verified`, `retryable_failed`, `terminal_failed`, and `superseded`; legacy `JOB_STATES` is unchanged.
- Added only `enqueue_formal_task`, `get_formal_task`, and `resolve_formal_task_dependencies` for this slice.
- Formal payloads are deep-snapshotted from caller mappings, recursively reject non-string JSON object keys, and serialize with UTF-8-compatible canonical JSON settings: sorted keys, compact separators, `ensure_ascii=False`, and `allow_nan=False`.
- `payload_sha256` is computed from the canonical JSON UTF-8 bytes. Reads reject invalid, duplicate-key, nonmapping, noncanonical, nonfinite, or hash-mismatched stored payload JSON.
- Exact idempotency replay is decided inside `BEGIN IMMEDIATE` by comparing kind, opaque refresh-generation equality, canonical payload bytes/hash, and the complete sorted prerequisite set. All mismatches raise `idempotency_payload_conflict` without changing rows or edges.
- Prerequisites are snapshotted and sorted before persistence. Enqueue rejects empty/non-string IDs, duplicates, missing tasks, self-edges, and graph cycles before inserting either the task or its edges.
- `get_formal_task` returns decoded canonical payload/result/error mappings, all material task fields, and sorted prerequisite IDs.
- Dependency resolution uses one immediate transaction and repeats until no more rows change, so terminal/superseded ancestry cascades transitively. It updates only `pending` or `retryable_failed` children, writes deterministic canonical `prerequisite_terminal_failed` error JSON with sorted blocker IDs, and clears result/retry/lease fields.
- Leased children are not rewritten. A second resolver call after a completed cascade returns zero.
- New formal queue operations use only V5 formal tables. A regression test confirms legacy enqueue/get behavior and the legacy state constant remain unchanged.

## Test coverage

The 10 new tests cover:

- six-state formal contract, exact replay, initial null fields, canonical UTF-8 payload hash, and missing lookup;
- prerequisite-order-independent replay and sorted getter output;
- content, kind, generation, and prerequisite-set conflicts with row/edge rollback proof;
- caller mutation isolation, empty/type-invalid identifiers, nonmapping payloads, NaN/infinities, and non-string object keys;
- missing, duplicate, self, and cyclic prerequisites;
- stored payload hash and noncanonical JSON tampering rejection;
- one-level superseded and multilevel terminal dependency cascades;
- retryable-child terminal transition, sorted multiple blockers, and field clearing;
- leased-child preservation;
- untouched legacy queue behavior.

## Scope and limitations

- Intentionally not implemented: leasing/reclaim, lease renewal, completion, failure APIs, supersession APIs, formal snapshot/receipt persistence, universe/status persistence, schema or migration changes, and legacy queue changes.
- No repository-wide or unrelated E2E suite was run; the binding brief explicitly required the bounded StateStore suite and prohibited an unbounded full suite.
- This report is written beside the brief after the code commit and is not part of commit `34cff9b`, preserving the instruction that the commit contain only the two scoped code/test files.

## Self-review

- `git diff --check` passed before staging.
- Staged-path verification listed exactly `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- Searched the implementation to confirm no leasing, renew/complete/fail, supersession, snapshot, or universe APIs were added.
- Reviewed transaction ordering, idempotency rollback, opaque generation equality, payload tamper handling, cycle traversal, deterministic edge/error ordering, fixed-point cascade behavior, and leased-child exclusion.
