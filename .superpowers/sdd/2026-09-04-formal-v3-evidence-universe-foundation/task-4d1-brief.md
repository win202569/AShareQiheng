# Task 4D1 — persist immutable formal frozen-universe graph

This first serial Task 4D slice may start only after 4B3 and 4C3 have independently passed review.  Base on those approved commits.  Read the V5 plan/spec, Task4D preflight in the ledger, `formal_universe.py`, formal evidence/snapshot contracts, StateStore schema/APIs/tests, and all relevant SDD rulings.

## Strict scope

Modify only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.  Do not change schema/migrations, FormalSnapshotStore, legacy jobs/snapshots, raw files, orchestration, data/SQLite artifacts, or scoring/release code.

## Public APIs for this slice

```python
put_formal_universe_snapshot(frozen: FormalFrozenUniverseInput) -> str
get_formal_universe_snapshot_by_input_hash(frozen_input_hash: str) -> dict[str, object] | None
list_formal_universe_sources(universe_snapshot_id: str) -> list[dict[str, object]]
```

Do not implement finalizer lookup or status replacement/listing in this slice; those are Task 4D2.

## Typed input and source trust contract

- Require the actual typed `FormalFrozenUniverseInput`, never mappings/lookalikes; re-run the full Task3 validation and canonical hashes before every insert or idempotent return.  Do not introduce a public construction bypass.
- Require exact freeze, sorted/unique sources for SH/SZ/BJ, nonempty canonical members, ordinary-A/exchange/raw-row hash/extraction/audit/hash consistency, visibility and all Task3 frozen-input rules.
- The StateStore must re-load each authoritative formal source row and require it agrees with the caller snapshot on identity, manifest/content hash, canonical request/fingerprint, source/listing dataset, global security ID, exchange, parser/mapping, publication/effective fields, verified state, generation and non-null producer.
- For each source require exactly one valid receipt, its task `verified` and kind `formal_universe_source`, matching source/manifest/generation/producer; canonical task payload/result must agree with frozen registry hash, freeze, exchange, parsed-rows hash, parser/version, root and source evidence.  Bootstrap snapshots or missing/mismatched/duplicate receipts are never eligible.
- Persist canonical JSON after recursively thawing Task3 `MappingProxyType`/tuples to finite plain dict/list values with string keys.  Persist enough complete extraction/audit/member data to reconstruct and revalidate the typed graph on read/idempotent replay.

## Atomic immutable universe graph

Within one `BEGIN IMMEDIATE` transaction, validate typed input and all three persisted source/task/receipt graphs; then:

1. Look up `frozen_input_hash`.
2. If present, reconstruct/revalidate full existing header, three sources, sorted members and initial status coverage; require byte-equivalent canonical frozen graph.  Return existing ID only if exact; otherwise raise `ValueError` containing `frozen_input_hash_conflict`.  Never repair/reset children/statuses.
3. If absent, insert one `formal_universe_snapshot`, exactly three sources, all sorted members, and one initial status per member.

Initial-status ruling (binding for 4D1): every member begins `pending_evidence`, `reasons=("formal_collection_pending",)`, `veto_flags=()`, and `evidence_hash=sha256(canonical UTF-8 JSON of {"frozen_input_hash", "security_id", "status", "reasons", "veto_flags"})`.  Use exact canonical sorted/compact/finiteness rules.  Record this ruling in report/ledger.

Use rollback for any late source/member/status conflict.  Do not treat a unique hash alone as idempotent success.  Existing corrupt/partial data must fail closed.

## TDD proof

Add RED before production code.  Cover a valid real task/receipt-backed SH/SZ/BJ frozen input; exact counts/header/canonical ordering; deep-frozen raw JSON serialization; idempotent exact return without reset; forged/hash-altered conflict; all Task3 recomputation checks; missing/duplicate/cross-exchange source; bootstrap/wrong kind/status/generation/manifest/receipt/task result rejection; late insertion rollback; corrupted existing graph/status coverage failure; legacy isolation.  Run focused then bounded full `tests.test_state_store`.

Commit only scoped files:

`feat: persist formal universe graph`

Write `task-4d1-report.md` with RED/GREEN counts, exact status rule/hash formula, and limitations.  No subagents/reviewers.
