# Task 4B — formal collection-task queue

## Scope and baseline

Implement only the formal V5 collection-task queue after Task 4A is approved.  Work from the then-current `HEAD`, and modify only:

- `ashare_pipeline/state_store.py`
- `tests/test_state_store.py`

Do not change the V5 schema/migration, raw snapshot persistence, universe/status persistence, legacy jobs, worker orchestration, data, SQLite files, or progress artifacts.  Formal tasks are a new, separate system: do not reuse `job`, `JobSpec`, `JOB_STATES`, `recover_expired_leases`, `source_snapshot`, or legacy ownerless completion paths.

Read before coding:

- `docs/superpowers/plans/2026-09-04-formal-v3-evidence-universe-foundation.md` (Task 4)
- `docs/superpowers/specs/2026-09-04-formal-scoring-release-contract-design.md` (§5)
- `.superpowers/sdd/2026-09-04-formal-v3-evidence-universe-foundation/progress.md`
- the approved Task 4A schema in `ashare_pipeline/state_store.py`

## Required state machine and public API

Use exactly these formal states, separate from legacy state names:

`pending`, `leased`, `verified`, `retryable_failed`, `terminal_failed`, `superseded`.

Implement the exact public APIs below, with type-safe input validation:

```python
enqueue_formal_task(kind, idempotency_key, refresh_generation, payload, prerequisite_task_ids=()) -> str
supersede_formal_tasks(scope, before_generation) -> int
get_formal_task(task_id) -> dict[str, object] | None
lease_next_formal_task(kinds, worker_id, lease_seconds, now_utc=None) -> dict[str, object] | None
renew_formal_task_lease(task_id, worker_id, lease_seconds, now_utc=None) -> str
resolve_formal_task_dependencies() -> int
complete_formal_task(task_id, worker_id, result) -> None
fail_formal_task(task_id, worker_id, error, status, next_retry_at) -> None
```

Returned task dictionaries must decode canonical JSON into `payload`, `result`, and `error`, include all material row fields and deterministically sorted prerequisites, and recompute/validate `payload_sha256` before returning any row.  No API may silently coerce formal states to legacy terms.

## Canonical queue rules

- Canonical JSON is UTF-8, sorted keys, compact separators, `ensure_ascii=False`, `allow_nan=False`; payload/result/error must be finite mappings.  Snapshot caller mappings before serialization.
- `payload_sha256` is SHA-256 of the canonical payload JSON UTF-8 bytes.
- Reject empty `kind`, `idempotency_key`, `refresh_generation`, and worker IDs; reject nonpositive lease durations and naive explicit timestamps.
- In a single `BEGIN IMMEDIATE` transaction, exact replay of `(idempotency_key, kind, refresh_generation, canonical payload/hash, complete prerequisite set)` returns the original ID.  Any same-key mismatch must raise `ValueError` containing `idempotency_payload_conflict` without mutating the original task/edges.
- Validate all prerequisites before writing: each exists, no duplicates, no self-edge, no cycle.  Store/read edge IDs in sorted order.
- A dependency is satisfied only if it is `verified`.  Pending/leased/retryable parents block children.  Terminal/superseded parents terminal-fail unleased pending/retryable descendants; cascade transitively in one dependency-resolution transaction with deterministic error JSON and cleared retry/lease/result fields.  Do not rewrite actively leased children.

## Leasing, fencing, and supersession

- `lease_next_formal_task` uses an atomic writer transaction and may acquire only pending, retryable tasks due at `now`, or expired leases.  Repeat the dependency predicate in the compare-and-set mutation.
- Deterministic order: ready time (created/retry/expired-lease), then `created_at`, then `id`.  Boundaries are inclusive (`next_retry_at == now`, `lease_expires_at == now`).
- Set `leased`, owner, and expiry atomically; clear retry time.  Reclaim expired leases directly, without calling legacy recovery.
- Renew/complete/fail must be owner- and unexpired-lease-fenced at the final mutation.  Re-sample time immediately before update.  Wrong owner, expired owner, missing/final/superseded task, and takeover must fail without mutation.
- Renew expiry is based on current time, not previous expiry.  Complete transitions `leased -> verified`, stores canonical result, and clears error/retry/lease fields.  Fail only permits `retryable_failed` or `terminal_failed`; retryable requires aware `next_retry_at`, terminal requires `None`; both clear lease fields.
- Source-receipt completion gates are deferred to Task 4C, except leave API design compatible with that gate.  Nontransport task kinds must remain completable without a receipt.
- Decision recorded for the otherwise ambiguous signature: `scope` is a nonempty exact top-level subset of canonical payload; `before_generation` denotes the generation to retain.  Supersede matching unfinished (`pending`, `leased`, `retryable_failed`) tasks whose `refresh_generation != before_generation`.  Preserve all rows/edges/results/errors, clear only lease/retry fields, and never lexically compare opaque generations.

## Tests and proof

Follow TDD: add focused RED tests first, then minimal production code.  Cover exact replay/order-independent dependencies, same-key conflicts/rollback, caller mutation, nonfinite JSON, missing/duplicate/self/cyclic edges, dependency blocking/cascade, lease timing boundaries/order/races/takeover fencing, renew/complete/fail ownership and expiry, retry validation, permanent non-releasing final states, supersession scope/generation/preservation, stored payload/hash tampering, and legacy state-store regression.

Run at least:

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_state_store
```

Attempt the broader relevant state/snapshot suite once only if it remains bounded; record any non-causal pre-existing full-suite long E2E behaviour rather than modifying unrelated code.

Commit only scoped code/tests with:

`feat: add formal collection task queue`

Write `.superpowers/sdd/2026-09-04-formal-v3-evidence-universe-foundation/task-4b-report.md` with RED/GREEN evidence, exact test counts, schema/API changes, and any bounded-suite observation.
