### Task 6: Exact Verified Snapshot Repository

**Files:**
- Create: `ashare_pipeline/snapshot_repository.py`
- Modify: `ashare_pipeline/snapshot_store.py:11-66`
- Create: `tests/test_snapshot_repository.py`
- Modify: `tests/test_snapshot_store.py`

**Interfaces:**
- Consumes: `StateStore.record_snapshot()`, `FetchBatch`, `SnapshotStore.write()`, and `canonical_sha256()`.
- Produces: `SnapshotRef`, `VerifiedSnapshot`, `SnapshotRepository.persist()`, `find_exact()`, `get()`, `read_verified()`, and `SnapshotStore.read_verified()`.

- [ ] **Step 1: Write exact-request and tamper tests**

```python
def test_find_exact_never_returns_another_symbol_global_latest(self):
    first, _ = self.repository.persist(statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00"))
    self.repository.persist(statement_batch("SH600002", 200.0, "2026-08-29T01:00:00+00:00"))
    observed = self.repository.find_exact(
        "akshare",
        "balance_sheet",
        {"symbol": "SH600001", "report_period": "2026-06-30"},
    )
    self.assertEqual(observed.id, first.id)


def test_read_verified_rejects_tampered_snapshot(self):
    snapshot, _ = self.repository.persist(statement_batch(
        "SH600001", 100.0, "2026-08-29T00:00:00+00:00"
    ))
    verified = self.repository.read_verified(snapshot)
    self.assertEqual(verified.batch.records[0]["TOTAL_ASSETS"], 100.0)
    path = self.project_root / snapshot.payload_path
    path.write_text(path.read_text(encoding="utf-8").replace("100.0", "999.0"), encoding="utf-8")
    with self.assertRaisesRegex(OSError, "hash"):
        self.repository.read_verified(snapshot)
```

Add tests for latest exact revision ordering `(fetched_at, created_at, payload_hash)`, unmatched requests, `get(snapshot_id)`, identical-content reuse, and both legacy absolute paths and new project-relative paths.

- [ ] **Step 2: Run repository tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_snapshot_repository tests.test_snapshot_store -v
```

Expected: FAIL because `snapshot_repository` and the public read API do not exist.

- [ ] **Step 3: Implement public verified reads**

In `SnapshotStore`, add:

```python
def read_verified(self, path: str | Path, digest: str) -> FetchBatch:
    candidate = Path(path)
    self._verify(candidate, digest)
    stored = json.loads(candidate.read_text(encoding="utf-8"))
    return FetchBatch(
        stored["source"],
        stored["dataset"],
        stored["request"],
        stored["records"],
        stored["fetched_at_utc"],
        stored["source_version"],
        stored["metadata"],
    )
```

Define `SnapshotRef` with DB fields and `VerifiedSnapshot(ref, batch)`. `SnapshotRepository` receives the data root, derives `project_root = data_root.parent`, and stores every new path as:

```python
relative_path = target.resolve().relative_to(self.project_root.resolve()).as_posix()
if not relative_path.startswith("data/"):
    raise ValueError("snapshot path must stay inside the project data directory")
```

Use this exact constructor:

```python
def __init__(
    self,
    data_root: str | Path,
    state_store: StateStore,
    snapshot_store: SnapshotStore | None = None,
) -> None:
    self.data_root = Path(data_root).resolve()
    self.project_root = self.data_root.parent
    self.state_store = state_store
    self.snapshot_store = snapshot_store or SnapshotStore(self.data_root)
```

`find_exact()` computes the canonical request fingerprint and filters source, dataset, and fingerprint before ordering. `get()` fetches by snapshot ID. `read_verified()` resolves relative paths against project root, accepts existing absolute legacy paths, verifies the resolved path remains inside project root for new relative records, and calls the public snapshot-store API.

- [ ] **Step 4: Run snapshot tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_snapshot_repository tests.test_snapshot_store -v
```

Expected: PASS.

- [ ] **Step 5: Commit snapshot repository**

```powershell
git add -- ashare_pipeline/snapshot_repository.py ashare_pipeline/snapshot_store.py tests/test_snapshot_repository.py tests/test_snapshot_store.py
git commit -m "feat: add exact verified snapshot repository"
```

---

