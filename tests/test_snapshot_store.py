import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ashare_pipeline.snapshot_store import SnapshotStore
from ashare_pipeline.sources import FetchBatch


class SnapshotStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.batch = FetchBatch("baostock", "daily", {"code": "000001"}, [{"code": "000001"}], "2026-08-25T10:00:00+00:00", "0.9.3", {"row_kind": "daily"})

    def tearDown(self): self.tempdir.cleanup()

    def test_write_uses_hash_path_and_deduplicates_without_rewrite(self):
        store = SnapshotStore(self.root)
        path, digest, created = store.write(self.batch)
        duplicate_path, duplicate_digest, duplicate_created = store.write(self.batch)

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual((path, digest), (duplicate_path, duplicate_digest))
        self.assertEqual(path, self.root / "raw" / "baostock" / "daily" / "2026-08-25" / f"{digest}.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["records"][0]["code"], "000001")

    def test_failed_replace_removes_only_own_part_file(self):
        store = SnapshotStore(self.root)
        with patch("ashare_pipeline.snapshot_store.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.write(self.batch)

        self.assertEqual(list(self.root.rglob("*.part")), [])
        self.assertEqual(list(self.root.rglob("*.json")), [])

    def test_same_content_at_later_observation_time_deduplicates_and_keeps_first_timestamp(self):
        store = SnapshotStore(self.root)
        path, digest, created = store.write(self.batch)
        later = FetchBatch("baostock", "daily", {"code": "000001"}, [{"code": "000001"}], "2026-08-26T10:00:00+00:00", "0.9.3", {"row_kind": "daily"})
        duplicate_path, duplicate_digest, duplicate_created = store.write(later)

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual((duplicate_path, duplicate_digest), (path, digest))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["fetched_at_utc"], "2026-08-25T10:00:00+00:00")

    def test_corrupt_existing_hash_target_is_rejected(self):
        store = SnapshotStore(self.root)
        path, _, _ = store.write(self.batch)
        path.write_text("{broken", encoding="utf-8")

        with self.assertRaises(OSError):
            store.write(self.batch)

    def test_invalid_part_payload_is_not_replaced_or_left_behind(self):
        store = SnapshotStore(self.root)
        def write_invalid(_payload, handle, *_args, **_kwargs): handle.write("{broken")
        with patch("ashare_pipeline.snapshot_store.json.dump", side_effect=write_invalid), patch("ashare_pipeline.snapshot_store.os.replace") as replace:
            with self.assertRaises(OSError):
                store.write(self.batch)

        replace.assert_not_called()
        self.assertEqual(list(self.root.rglob("*.part")), [])
        self.assertEqual(list(self.root.rglob("*.json")), [])

    def test_read_verified_returns_the_stored_batch_only_when_hash_matches(self):
        store = SnapshotStore(self.root)
        path, digest, _ = store.write(self.batch)

        observed = store.read_verified(path, digest)

        self.assertEqual(observed, self.batch)

    def test_read_verified_fails_safely_for_missing_payload_fields(self):
        store = SnapshotStore(self.root)
        path = self.root / "malformed.json"
        path.write_text('{"source":"baostock"}', encoding="utf-8")

        with self.assertRaisesRegex(OSError, "invalid snapshot payload"):
            store.read_verified(path, "0" * 64)
