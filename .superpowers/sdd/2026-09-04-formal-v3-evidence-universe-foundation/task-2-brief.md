### Task 2: Byte-Preserving Formal Snapshot Store

**Files:**
- Create: ashare_pipeline/formal_snapshot_store.py
- Create: tests/test_formal_snapshot_store.py

**Interfaces:**
- Consumes OfficialFetch and EvidenceVerification from Task 1.
- Produces FormalStoredSnapshot with content_path, manifest_path, content_sha256, and manifest_sha256.
- FormalSnapshotStore.write_verified(fetch, verification, *, producing_task_id: str | None) must write raw bytes without JSON re-encoding and carries task provenance only in the immutable manifest envelope.

- [ ] **Step 1: Write failing raw-storage tests**

~~~python
class FormalSnapshotStoreTests(unittest.TestCase):
    def test_binary_bytes_round_trip_without_json_reencoding(self):
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch(raw_bytes=b"%PDF\x00\xff\n")
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            self.assertEqual(store.read_verified_raw(stored), b"%PDF\x00\xff\n")
            self.assertEqual(stored.content_sha256, sha256(b"%PDF\x00\xff\n").hexdigest())

    def test_tampered_manifest_or_content_is_rejected_and_part_file_is_cleaned(self):
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            Path(stored.content_path).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "content hash"):
                store.read_verified_raw(stored)
            self.assertFalse(list(Path(root).rglob("*.part")))

    def test_same_bytes_in_new_generation_reuses_bin_but_keeps_two_manifests(self):
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            first_fetch = verified_fetch(refresh_generation="index-v1")
            second_fetch = verified_fetch(refresh_generation="index-v2")
            first = store.write_verified(first_fetch, verified(first_fetch), producing_task_id=None)
            second = store.write_verified(second_fetch, verified(second_fetch), producing_task_id=None)
            self.assertEqual(first.content_path, second.content_path)
            self.assertNotEqual(first.manifest_sha256, second.manifest_sha256)
            self.assertNotEqual(first.manifest_path, second.manifest_path)
            self.assertEqual(store.read_verified_raw(first), store.read_verified_raw(second))
~~~

- [ ] **Step 2: Run the storage tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_snapshot_store -v
~~~

Expected: FAIL because FormalSnapshotStore is undefined.

- [ ] **Step 3: Implement content and manifest atomic writes**

Write raw content at:

~~~text
data/raw/formal/<source>/<dataset>/<sha256>.bin
data/raw/formal/<source>/<dataset>/<manifest_sha256>.manifest.json
~~~

Raw .bin files are content-addressed and may be shared only when their bytes have the same content SHA-256. Manifests are lineage-addressed: canonicalize a manifest payload containing every OfficialFetch field (including refresh_generation), verification status/reasons, optional producing_task_id, and content SHA-256; calculate manifest_sha256 over that payload excluding the envelope's manifest_sha256 field; then write one canonical envelope named by that hash. This avoids a self-hash and preserves distinct immutable provenance when identical source bytes are re-collected in a later generation or task. Use a sibling file ending in .part, flush and fsync it, validate bytes against OfficialFetch.content_sha256, then replace it atomically. read_verified_raw must re-read the selected .bin and selected manifest envelope, recompute both hashes, require the named manifest hash to match the canonical payload, and reject a non-verified manifest. It must never select a manifest merely by content SHA.

- [ ] **Step 4: Run the focused storage suite**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_snapshot_store tests.test_snapshot_store -v
~~~

Expected: PASS; legacy SnapshotStore remains independent.

- [ ] **Step 5: Commit the formal raw store**

~~~powershell
git add -- ashare_pipeline/formal_snapshot_store.py tests/test_formal_snapshot_store.py
git commit -m "feat: add byte-preserving formal snapshot store"
~~~

