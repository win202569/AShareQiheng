# Task 4C2 — persist/bootstrap immutable formal source snapshots

This is the second serial Task 4C slice.  It may start only after 4C1 passes independent review.  Base on that approved commit and read the V5 plan/spec, the 4C preflight in the ledger, `task-4c1-brief.md`, `task-4c2-state_store_analyst` conclusions recorded in the ledger, and the reviewed `FormalSnapshotStore.validate_stored_snapshot(...) -> ValidatedFormalSnapshot` contract.

## Strict scope

Modify only:

- `ashare_pipeline/state_store.py`
- `tests/test_state_store.py`

Do not change V5 DDL/migrations, queue completion/supersession, leased receipt writer, universe code, formal snapshot-store code, legacy repositories/jobs, data/SQLite files, or runtime artifacts.

## Public contract

Preserve existing construction and add optional explicit dependency injection:

```python
StateStore(db_path, *, formal_snapshot_store: FormalSnapshotStore | None = None)
```

Never infer a raw-store root from a DB path, manifest path, or caller metadata.  Existing legacy-only callers remain compatible; formal snapshot APIs fail closed when no formal snapshot store is configured.

Implement only:

```python
put_formal_snapshot(
    fetch: OfficialFetch,
    stored: FormalStoredSnapshot,
    verification: EvidenceVerification,
) -> OfficialSnapshotRef

get_formal_snapshot(snapshot_id: str) -> OfficialSnapshotRef | None

get_formal_task_snapshot_receipt(task_id: str) -> dict[str, object] | None
```

`put_formal_snapshot_for_leased_task` is deferred to 4C3.  Do not introduce it here.

## Trust and immutable-lineage rules

- Bootstrap persistence invokes the 4C1 helper with `expected_producing_task_id=None`.  Persist only fields from its validated canonical projection, never untrusted caller metadata.
- All formal reads must reconstruct/revalidate exact canonical request/verification JSON, fingerprint, row fields, raw bytes, and manifest through the helper before returning a ref.  Make one private row-to-ref validation path shared by writer/getters.
- Canonical request/verification JSON is UTF-8, sorted, compact, finite and duplicate-key-free.  Recompute request fingerprint on write/read.  Enforce lowercase 64-hex hashes; require exact request identity keys.
- Bootstrap producer is SQL `NULL`; bootstrap writes never create a receipt.
- Use `BEGIN IMMEDIATE`.  First validate the raw snapshot.  On `manifest_sha256` replay, revalidate existing row/raw data and return it only if every immutable field matches; otherwise raise `ValueError` containing `formal_snapshot_manifest_conflict` without repairing data.
- On same `(request_fingerprint, refresh_generation, producing_task_id IS NULL)` but a different manifest, raise `ValueError` containing `formal_snapshot_lineage_conflict`.  Never use `INSERT OR IGNORE`, `REPLACE`, mutation, or legacy `source_snapshot`.
- For a new valid lineage insert exactly one UUID formal snapshot row and canonical UTC creation time, then re-read/revalidate in the same transaction to construct `OfficialSnapshotRef`.
- Same bytes in a new generation may share the binary but must have a distinct validated manifest and formal DB row.  DB failure may leave immutable raw files but not partial database rows.
- Getter returns `None` only for a genuinely absent formal row/receipt; bad ID type/empty is an error and any stored tamper is failure, not `None`.
- Receipt getter only reads/rechecks formal receipt/source/task lineage.  It must validate task → receipt → snapshot/manifest/producer and matching refresh generations; it remains readable after a task later reaches `terminal_failed`.  A canonical task-produced fixture may be inserted directly in tests until 4C3 provides the leased writer.

## TDD proof

Write RED first, then minimal production code.  Test injection/fail-closed unconfigured store; valid bootstrap ref with no receipt; helper invocation/producer null; exact replay; new generation/shared binary behavior; manifest and lineage conflicts; producer/non-verified/mismatch rejection and zero DB mutation; missing/malformed lookups; database and raw/manifest tamper fail-closed; tampered replay no repair; direct canonical formal receipt lineage success/mismatches/terminal-failure preservation; legacy `source_snapshot` isolation.  Run focused tests then full bounded `tests.test_state_store`.

Commit only the two scoped files:

`feat: persist formal bootstrap snapshots`

Write `task-4c2-report.md` with RED/GREEN proof, exact counts, injection/lineage decisions, and limitations.  No subagents/reviewers.
