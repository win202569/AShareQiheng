# Task 4D2 — formal universe status ledger and finalizer proof

This serial Task 4D2 starts only after reviewed Task 4D1 is complete (`5e6dc8a`, `bc34b67`). Read the V5 plan/spec, V6 worker finalizer payload contract, progress ledger, Task 3 universe contracts, all reviewed 4B/4C/4D1 code/tests, and the D1 report before acting.

## Strict scope

Modify only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`. Do not change schema/migrations, raw snapshot store/repository, Task 3 universe types, legacy paths, V6 worker code, data/SQLite artifacts, or orchestration. This slice makes only the already-declared V5 StateStore APIs usable.

## Public APIs

Implement:

```python
replace_formal_universe_statuses(
    universe_snapshot_id: str,
    decisions: Sequence[FormalUniverseDecision],
) -> None

list_formal_universe_statuses(
    universe_snapshot_id: str,
) -> list[dict[str, object]]

get_formal_universe_snapshot_from_task(
    finalizer_task_id: str,
) -> dict[str, object] | None
```

Extend `complete_formal_task` so a correctly leased `formal_universe_finalize` task can become `verified` only after its full formal-universe proof is revalidated. All other formal task behavior must remain exactly as reviewed.

## Status-ledger contract

- Require a configured `FormalSnapshotStore` and revalidate the complete immutable universe graph with the D1 helper before reading or replacing statuses. A corrupt/missing source/member/status graph must fail closed; do not repair it.
- `universe_snapshot_id` and every decision identity must be canonical. A nonexistent snapshot returns `[]` from the list method, while malformed IDs/inputs raise; a replacement against a nonexistent snapshot raises.
- Require exact `FormalUniverseDecision` objects, not mappings/subclasses/lookalikes. Materialize the input once; require exactly one decision for every existing universe member and no duplicate, missing, extra, cross-universe, or noncanonical security IDs.
- Require a recognized universe status, canonical `tuple[str, ...]` reasons and veto flags (nonempty strings, lexical sorted order, no duplicates), and a lowercase 64-hex evidence hash. Enforce stable minimum semantics: `out_of_scope` and `pending_evidence` need at least one reason; `pool_vetoed` needs at least one veto flag; `formal_scored` cannot carry a veto flag. `pending_evidence` may carry a veto flag (for example ST plus missing evidence), matching the binding spec’s precedence rule.
- The general later-stage evidence hash remains a typed caller-supplied immutable evidence reference in V5; do not invent a fake scoring/fact hash formula. However, the exact D1 initial tuple (`pending_evidence`, `("formal_collection_pending",)`, empty veto flags) must preserve and revalidate the binding D1 canonical hash formula. Do not loosen the reviewed D1 read behavior.
- Write a complete replacement atomically under `BEGIN IMMEDIATE`: validate first, update every row deterministically, then revalidate through the normal full graph/status read path before commit. No partial updates, delete/reinsert gaps, or update of a member outside this snapshot. Set one canonical `updated_at` value for the replacement. Equal replacement may be accepted but must still validate every input/row.
- `list_formal_universe_statuses` returns canonical parsed public mappings in `security_id` order (not raw JSON strings) only after complete-graph revalidation. Do not return partial data.

## Finalizer proof and task binding

The V6 plan fixes the finalizer payload shape now; enforce it at the StateStore boundary rather than accepting an unrelated task as a universe proof.

For a `formal_universe_finalize` task, its canonical payload must have exactly:

```json
{
  "as_of_utc": "...",
  "registry_manifest_hash": "...",
  "refresh_generation": "...",
  "source_task_ids": ["BJ task UUID", "SH task UUID", "SZ task UUID"]
}
```

- `as_of_utc` and `registry_manifest_hash` must equal the reconstructed universe header; `refresh_generation` must exactly equal the task row’s generation; `source_task_ids` must be canonical UUIDs in BJ/SH/SZ exchange order and exactly match both the universe’s three source-producing task IDs and the task’s immutable prerequisite-edge set. No missing/extra/duplicate source task can be accepted.
- The result must have exactly `universe_snapshot_id`, `frozen_input_hash`, `universe_hash`, and `registry_manifest_hash`; all values must be canonical and exactly equal the fully revalidated target header. Never infer the snapshot from a bare task ID or from a result that names only one field.
- `complete_formal_task` must prove, in the same `BEGIN IMMEDIATE` transaction and before its final owner/strict-expiry CAS, that the current task is the leased finalizer and its payload/result/full target graph/complete status coverage meet the above contract. Resample time for the final CAS exactly as the reviewed source-task path does. On failure leave task, result, lease and status rows unchanged.
- `get_formal_universe_snapshot_from_task` redoes the exact proof from the persisted task/result and graph. Return `None` only when the task ID is genuinely absent; wrong kind, non-verified/impossible verified state, malformed payload/result, stale/mismatched header, incomplete statuses, or corrupted sources all fail closed. It must revalidate the strict verified task lifecycle introduced in D1.
- Do not require every universe status to be `formal_scored`: a full classified ledger may include `pending_evidence`, `pool_vetoed`, and `out_of_scope`. V5’s finalizer freezes a complete status ledger, not a release-grade scoring result.

## TDD proof

Add focused RED tests before production changes. Cover at least:

1. Exact complete status replacement/listing with all four states, parsed canonical output/order, stable initial-tuple hash, and valid precedence case (pending plus veto).
2. Rejection with no mutation for non-typed decisions, malformed/unsorted/duplicate reasons or vetoes, bad enum/hash, semantic minimum violations, duplicate/missing/extra IDs, a foreign member, and a bad initial-tuple hash.
3. Atomic rollback on a late status-row failure and fail-closed read/replace against a pre-corrupted D1 graph or incomplete status coverage.
4. A direct single-row `updated_at` tamper to another canonical timestamp, and an `updated_at` earlier than the universe header creation time, both fail closed from listing, replacement tail revalidation, finalizer proof, and verified-task lookup. Legitimate D1 initialization and each full replacement must prove one shared ledger timestamp not earlier than the header creation time.
5. Whitespace-only or padded reason/veto strings are rejected without mutation; canonical nonempty reason/veto values must be already trimmed/nonblank (`token == token.strip()`). Persisted whitespace-only or padded tampering must fail closed from listing, replacement, finalizer proof/completion, and verified-task lookup.
6. Valid finalizer lease/completion and lookup after three real D1 task/receipt-backed sources; prove exact payload/dependency BJ/SH/SZ binding and result/header equality.
7. Finalizer rejection and no mutation for incorrect/missing/extra result fields; wrong snapshot/header/root/frozen/universe hash; wrong task kind/status/worker/expiry; malformed or unrelated payload; reordered/missing/extra source task IDs; dependency mismatch; corrupt target source/member/status graph; and a forged impossible verified state.
8. Getter rejection for every corresponding persisted task/result/graph tamper and `None` only for genuinely absent task; legacy task/table isolation.
9. Existing source-task receipt completion, feature-build completion, D1 APIs/replay, and legacy StateStore behavior stay green.

Run focused tests, then bounded `tests.test_state_store`, `py_compile`, and `git diff --check`.

Commit only the two scoped tracked files with:

`feat: complete formal universe lifecycle`

Write ignored `task-4d2-report.md` with RED/GREEN evidence, the finalizer payload/result binding, status decisions/limitations, and no data artifacts. Do not spawn subagents/reviewers.
