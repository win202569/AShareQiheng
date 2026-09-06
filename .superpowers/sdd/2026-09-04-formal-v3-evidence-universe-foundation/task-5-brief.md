# Task 5 — verified formal snapshot repository (binding brief)

## Scope and starting point

Start from reviewed V5 foundation head `8988719`. This is a V5-only repository boundary; it must not begin V6 collection work.

Allowed tracked changes only:

- create `ashare_pipeline/formal_snapshot_repository.py`;
- create `tests/test_formal_snapshot_repository.py`;
- modify `ashare_pipeline/state_store.py` only for narrow formal-snapshot store access and verified formal-snapshot lookup helpers.

Do **not** alter schema/migrations, `formal_snapshot_store.py`, `formal_evidence.py`, time/universe/status/finalizer behavior, worker/orchestration code, legacy snapshot/repository APIs, or data/SQLite/WAL/SHM/progress files. Do not use raw SQL from the repository itself. Keep the D2 full-graph status/finalizer defenses intact.

Write ignored `task-5-report.md` with RED/GREEN evidence and invariants, but never stage it.

## Public API

Create and export exactly this repository class:

```python
class FormalSnapshotRepository:
    def __init__(self, root: str | Path, state_store: StateStore) -> None: ...

    def persist_verified(
        self,
        fetch: OfficialFetch,
        verification: EvidenceVerification,
        *,
        producing_task_id: str | None,
        worker_id: str | None,
    ) -> OfficialSnapshotRef: ...

    def find_exact_verified(
        self,
        request: OfficialRequest,
        *,
        parser_id: str,
        parser_version: str,
        mapping_version: str,
        content_sha256: str,
        manifest_sha256: str,
    ) -> OfficialSnapshotRef | None: ...

    def find_visible_verified(
        self,
        request: OfficialRequest,
        *,
        parser_id: str,
        parser_version: str,
        mapping_version: str,
        as_of_utc: str,
    ) -> OfficialSnapshotRef | None: ...

    def get_verified_by_manifest(self, manifest_sha256: str) -> OfficialSnapshotRef: ...

    def read_verified_raw(self, ref: OfficialSnapshotRef) -> bytes: ...
```

All returned references must be the exact immutable `OfficialSnapshotRef` projection re-read from the formal row plus verified manifest; never synthesize a ref from a mutable request, bare hash, or legacy object. A legacy `SnapshotRef`, legacy `source_snapshot` ID/row, mapping, or bare hash is never accepted by this class.

## Constructor and configured raw-store boundary

- Require a real `StateStore` configured with the one authoritative `FormalSnapshotStore`; an unconfigured store fails closed.
- Resolve `root` and require it to equal that already-configured store's `root`. Do not construct a second `FormalSnapshotStore`, infer a root from DB paths, or bypass its trusted date-only calendar resolver.
- A narrow package-private StateStore accessor may expose its configured formal store for this purpose; the repository must not reach into `_formal_snapshot_store` directly.

## Persistence contract

- Validate before any raw-file mutation that `fetch`/`verification` have the expected formal types and that `producing_task_id`/`worker_id` are either both `None`, or both already-trimmed nonempty strings. Half-pairs, whitespace/padded identifiers, and invalid values fail before `write_verified`.
- Call the configured `FormalSnapshotStore.write_verified(fetch, verification, producing_task_id=...)` first. Raw evidence is immutable/content-addressed; a later failed DB or lease operation may leave a verified raw file but must leave no partial formal DB row or receipt.
- For the null pair, call only `StateStore.put_formal_snapshot(fetch, stored, verification)`.
- For the non-null pair, call only `StateStore.put_formal_snapshot_for_leased_task(fetch, stored, verification, task_id, worker_id)`. Preserve its leased-owner/expiry/generation fences and atomic receipt write.
- Return only the StateStore-returned row/manifest-derived `OfficialSnapshotRef`. Preserve exact replay/idempotence and existing immutable conflict behavior. Never create a receipt for bootstrap evidence or allow an unleased task to claim a snapshot.

## Verified lookup and lineage contract

The repository calls only narrow StateStore helpers, not SQLite directly. Implement helpers behind one explicit SQLite read transaction that validate the DB row, canonical request and verification JSON, manifest and raw bytes, and producer/receipt lineage before returning any candidate.

For exact and visible request lookup, candidate discovery must **not** trust any stored DB identity column (including `request_fingerprint`) as an exclusion predicate: all such fields are mutable tamper targets. Scan and fully revalidate every formal snapshot row in the same transaction, then filter reconstructed immutable refs by the caller's recomputed canonical request identity. A row whose stored fingerprint has been changed to another valid lower-case SHA-256 must therefore fail closed, never be invisibly excluded so an older version can be returned. SQL filtering by a caller-provided manifest is permitted only for the manifest-specific API, where absence is an error rather than an older-version fallback.

- Read only `formal_source_snapshot`, never `source_snapshot`.
- Reuse the trusted `_formal_snapshot_row_to_ref` / raw-store validation projection. Do not trust stored paths, JSON, fingerprints, or hashes without revalidation.
- For every non-null producer, require exactly one matching formal receipt whose task ID, snapshot ID, manifest SHA, parser lineage, and refresh generation agree with the task and source row. For a null producer, reject any receipt that references the snapshot. Orphan/extra/fractured task-receipt graphs fail closed.
- `find_exact_verified` accepts only an exact `OfficialRequest`, already-trimmed nonempty parser/mapping identities, and lower-case 64-hex content/manifest hashes. Recompute canonical request JSON and fingerprint; match *all* of source, dataset, security ID, exchange, period/date, request JSON/fingerprint, parser ID/version, mapping version, content SHA, and manifest SHA. A syntactically valid absent exact combination returns `None`; it never picks another version.
- `find_visible_verified` accepts only an exact `OfficialRequest`, already-trimmed nonempty parser/mapping identities, and an explicit aware/canonical `as_of_utc`. Recompute canonical request JSON/fingerprint, consider only exact request/parser/mapping candidates, revalidate every matching candidate (a corrupt candidate is an error, not silently skipped), and retain only `effective_at_utc <= as_of_utc`. Do not require capture time to predate `as_of_utc`: later capture may support historical replay when effective evidence already did. Select deterministically using `formal_version_sort_key`; because its `FormalVersion` protocol calls the field `content_hash`, adapt immutable `OfficialSnapshotRef.content_sha256` rather than changing shared time code. Add `manifest_sha256` ascending as the final tie-breaker for otherwise identical keys. Never use SQL insertion order or global dataset latest.
- `get_verified_by_manifest` accepts only lower-case 64-hex. It is the sole manifest/root-lineage lookup; an unknown but well-formed manifest raises `ValueError` (not `None`), and malformed input raises. It must apply the same row/raw/receipt graph validation.
- `read_verified_raw` accepts an exact `OfficialSnapshotRef` only. Re-fetch its current canonical formal ref by manifest via the verified lookup, compare every immutable reference field (not just hashes), reconstruct the minimal `FormalStoredSnapshot` only from the revalidated ref, then delegate to the configured raw store's `read_verified_raw`. Any changed ref field, missing row, legacy ref, DB/manifest/path/raw tamper, or lineage fracture fails closed; returned bytes remain byte-identical.

## Required TDD proof

Write focused RED tests before production code. At minimum cover:

1. Constructor rejects an unconfigured StateStore and a root different from its configured raw store; the valid constructor reuses the exact store/resolver.
2. Bootstrap persistence returns a fully populated row-derived ref; exact retry is idempotent; rejected evidence/invalid pair fails before raw write; raw bytes under a changed generation retain existing snapshot-store semantics.
3. Leased persistence writes raw first, then one matching formal receipt; wrong/lost/expired lease or half-pair leaves no formal row/receipt; verified raw may remain immutable.
4. Exact lookup succeeds only on all exact request/version/hash fields; valid absence returns `None`; altered canonical JSON/fingerprint, lower/upper hash form, parser/mapping identity, or legacy row never passes. Directly tampering a newer matching row's stored `request_fingerprint` to a different valid lower-case SHA-256 must make both exact and visible lookup fail closed rather than silently return an older row.
5. Visible lookup tests cutoff exclusion, later-capture historical visibility, each `formal_version_sort_key` dimension, null `source_updated_at_utc` ordering, deterministic manifest tie-break, and independence from insertion order.
6. Manifest lookup succeeds only for one verified formal graph and raises for malformed/unknown manifests.
7. Raw read returns byte-identical data and rejects modified `OfficialSnapshotRef`, legacy ref/ID/mapping/hash, missing source row, DB/manifest/raw/path tamper, and any producer/receipt/generation fracture.
8. Directly persisted corrupt matching candidates make exact/visible/manifest lookup fail closed rather than falling back to another candidate; bootstrap rows reject receipts and task-produced rows require their receipt.
9. A real D1/D2 universe-source snapshot remains retrievable through verified manifest lookup without mutating universe, task, receipt, status, or finalizer state.
10. Legacy rows/APIs remain isolated, and existing formal snapshot-store, formal evidence, and StateStore tests stay green.

Run first to demonstrate RED:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_snapshot_repository -v
```

Then run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_snapshot_repository tests.test_formal_snapshot_store tests.test_formal_evidence tests.test_state_store -v
.\.venv\Scripts\python.exe -m py_compile ashare_pipeline/formal_snapshot_repository.py ashare_pipeline/state_store.py tests/test_formal_snapshot_repository.py
git diff --check 8988719..HEAD
```

Verify only the three allowed tracked files changed. Commit only those files with:

```text
feat: persist verified formal snapshots
```

Do not spawn subagents or reviewers; send a checkpoint after RED and a final report with commit, scope, and exact test results.
