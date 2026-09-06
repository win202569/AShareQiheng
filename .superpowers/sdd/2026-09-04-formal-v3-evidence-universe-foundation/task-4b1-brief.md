# Task 4B1 — formal task enqueue and dependency foundation

This is the first serial, independently reviewed slice of Task 4B.  Start from approved Task 4A commit `438900f`; do not implement leasing, renewals, completion/failure, raw receipts, or supersession in this slice.

## Allowed scope

Modify only:

- `ashare_pipeline/state_store.py`
- `tests/test_state_store.py`

Do not change V5 DDL/migrations, legacy jobs, raw snapshot/universe code, data/SQLite/WAL/SHM, progress artifacts, or unrelated files.  Preserve every legacy behavior.

Read `task-4b-brief.md`, the V5 plan/spec, and ledger before coding.  This brief narrows only implementation order; its parent brief remains binding.

## Deliver exactly

1. A separate `FORMAL_TASK_STATES` contract containing exactly `pending`, `leased`, `verified`, `retryable_failed`, `terminal_failed`, `superseded`; do not change legacy state constants.
2. `StateStore.enqueue_formal_task(kind, idempotency_key, refresh_generation, payload, prerequisite_task_ids=()) -> str`.
3. `StateStore.get_formal_task(task_id) -> dict[str, object] | None`.
4. `StateStore.resolve_formal_task_dependencies() -> int` for dependency state propagation only.  It must not lease or change actively leased children.

Canonical serialization must be UTF-8 / sorted keys / compact separators / `ensure_ascii=False` / `allow_nan=False`; snapshot caller mappings before serialization.  `payload_sha256` is SHA-256 of canonical payload UTF-8 bytes.  Reject nonmapping/nonfinite payloads and empty identifiers.

Inside a `BEGIN IMMEDIATE` transaction, exact replay of an idempotency key returns the existing ID only if kind, refresh generation, canonical payload/hash, and the complete prerequisite set match.  Any mismatch raises `ValueError` containing `idempotency_payload_conflict` and makes no mutation.  Do not use lexicographic generation comparison.

Validate dependencies before inserts: IDs exist, no duplicates, no self-edge, no cycles, deterministic sorted storage/readback.  New tasks are `pending` with all lease/retry/result/error fields null.  Returned rows must decode canonical payload/result/error and expose sorted prerequisite IDs; revalidate stored payload JSON/hash and fail closed on tampering/noncanonical JSON.

Dependency resolution must run atomically and repeatedly cascade a terminal/superseded parent through unleased `pending`/`retryable_failed` descendants to `terminal_failed`, returning the number of changed children.  Use deterministic canonical error JSON with code `prerequisite_terminal_failed` and sorted blocking prerequisite IDs; clear result/retry/lease fields.  Pending/leased/retryable parents merely block later leasing, and actively leased children must not be rewritten.

## TDD and required tests

Write focused RED tests first, then minimal production code.  Cover: exact replay; prerequisite-order-independent replay; content/kind/generation/prerequisite-set conflicts with rollback; caller mutation; NaN/infinite rejection; missing/duplicate/self/cyclic prerequisites; sorted getter output; tampered payload JSON/hash/noncanonical JSON rejection; one-level and multilevel terminal/superseded cascade; retryable child transition; no rewrite of leased child; untouched legacy queue behavior.

Run `D:\\Projects\\AShareQiheng\\.venv\\Scripts\\python.exe -m unittest -v tests.test_state_store`.  Do not run an unbounded full suite.  Self-review scope/diff, commit only the two scoped files as:

`feat: add formal task enqueue semantics`

Write `task-4b1-report.md` beside this brief with RED/GREEN evidence, test count, decisions, and limitations.  Do not spawn subagents/reviewers.
