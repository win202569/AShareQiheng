# Task 4C3 — atomically persist leased-task raw receipt

This is the third serial Task 4C slice.  It may start only after 4C2 passes independent review.  Base on the approved 4C2 commit.  Read the binding V5 plan/spec, Task 4C preflight in the ledger, `task-4c2-brief.md`, current reviewed 4B queue APIs, and 4C1/4C2 helper contracts.

## Strict scope

Modify only:

- `ashare_pipeline/state_store.py`
- `tests/test_state_store.py`

Do not change V5 schema/migrations, FormalSnapshotStore implementation, task completion/supersession, universe code, legacy jobs/snapshots, data/SQLite artifacts, or unrelated files.

## Public API

Implement only:

```python
put_formal_snapshot_for_leased_task(
    fetch: OfficialFetch,
    stored: FormalStoredSnapshot,
    verification: EvidenceVerification,
    *,
    task_id: str,
    worker_id: str,
) -> OfficialSnapshotRef
```

Re-use 4C2's optional injected `FormalSnapshotStore`; fail closed if missing.  Do not alter bootstrap writer semantics or introduce task completion/supersession here.

## Atomic receipt contract

- Validate types/nonempty task/worker IDs and raw snapshot through 4C1 with `expected_producing_task_id=task_id`; no caller-supplied path/metadata may be persisted.
- In one `BEGIN IMMEDIATE` transaction, require task exists, is formal `leased`, owned by `worker_id`, and its expiry is strictly after a freshly sampled UTC time.  Require task `refresh_generation == fetch.refresh_generation == validated manifest generation`.  Recheck ownership immediately before mutation where necessary; wrong owner, expired/taken-over/final/pending task, wrong generation, or mismatched producer must leave no snapshot row or receipt.
- Restrict to source-fetch kinds: `formal_statement`, `formal_context`, `formal_universe_source`; reject other kinds.
- Use only the canonical 4C1 projection and 4C2 row-to-ref validator.  Insert/reuse formal source snapshot immutably with the same manifest-first and lineage-conflict logic as bootstrap.  A task-produced lineage is distinct from bootstrap and includes producer identity.
- Atomically insert exactly one `formal_task_snapshot_receipt` (`task_id`, snapshot ID, manifest hash, generation) once its snapshot is present.  Exact replay with all immutable fields equal returns the existing validated ref.  Any replacement attempt (different snapshot/manifest/generation/metadata), a second receipt for task, or attaching one snapshot/manifest to another task must raise deterministic conflict and never update/delete/replace rows.
- Raw file writes precede DB persistence; a rejected DB transaction may leave immutable unreferenced raw evidence but no partial formal row or receipt.
- Preserve receipts through later `retryable_failed`/`terminal_failed` task transitions; C2 getter must validate them after state changes.

## TDD proof

Add RED tests then minimal implementation.  Cover successful leased atomic snapshot+receipt; no receipt on bootstrap; pending/verified/wrong-worker/expired/taken-over/wrong-generation/non-source/mismatched producer rejection with zero DB rows; exact replay; second snapshot/receipt conflicts; same snapshot prohibited across tasks; raw/manifest mismatch; receipt getter after terminal failure; row/receipt manifest/generation/producer tampering; legacy isolation and existing bootstrap behavior.  Verify both data mutations roll back together on a late insert/constraint failure.

Run focused tests then complete bounded `tests.test_state_store`; do not run project-wide E2E.  Commit only scoped files:

`feat: persist formal task snapshot receipts`

Write `task-4c3-report.md` with RED/GREEN proof, exact results, and no scope expansion.  No subagents/reviewers.
