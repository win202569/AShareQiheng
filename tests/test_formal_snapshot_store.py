import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ashare_pipeline.formal_evidence import (
    OfficialFetch,
    OfficialRequest,
    SourcePolicy,
    verify_official_fetch,
)
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore


def verified_fetch(
    *, raw_bytes: bytes = b"%PDF-1.7 official", refresh_generation: str = "index-v1"
) -> OfficialFetch:
    return OfficialFetch(
        request=OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31"),
        raw_bytes=raw_bytes,
        original_url="https://static.cninfo.com.cn/finalpage/2026-03-20/123.pdf",
        published_at_utc="2026-03-20T08:00:00+00:00",
        published_precision="timestamp",
        source_updated_at_utc=None,
        captured_at_utc="2026-09-04T08:00:00+00:00",
        effective_at_utc="2026-03-20T08:00:00+00:00",
        effective_time_evidence_hash=None,
        refresh_generation=refresh_generation,
        parser_id="cninfo-pdf",
        parser_version="cninfo-pdf-v1",
        mapping_version="cninfo-annual-v1",
        declared_security_id="SZ000001",
        declared_period="2025-12-31",
    )


def verified(fetch: OfficialFetch):
    result = verify_official_fetch(fetch, SourcePolicy.cninfo())
    assert result.status == "verified"
    return result


class FormalSnapshotStoreTests(unittest.TestCase):
    def test_binary_bytes_round_trip_without_json_reencoding(self):
        """Removing raw-byte storage would turn this non-UTF-8 payload into a failure."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch(raw_bytes=b"%PDF\x00\xff\n")

            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)

            self.assertEqual(store.read_verified_raw(stored), b"%PDF\x00\xff\n")
            self.assertEqual(Path(stored.content_path).read_bytes(), b"%PDF\x00\xff\n")
            self.assertEqual(
                stored.content_sha256, hashlib.sha256(b"%PDF\x00\xff\n").hexdigest()
            )

    def test_tampered_content_is_rejected_and_part_file_is_cleaned(self):
        """Removing content-hash verification would allow corrupted source bytes through."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            Path(stored.content_path).write_bytes(b"tampered")

            with self.assertRaisesRegex(ValueError, "content hash"):
                store.read_verified_raw(stored)

            self.assertFalse(list(Path(root).rglob("*.part")))

    def test_tampered_manifest_is_rejected(self):
        """Skipping manifest lineage-hash validation would allow altered provenance through."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            envelope = json.loads(Path(stored.manifest_path).read_text(encoding="utf-8"))
            envelope["producing_task_id"] = "tampered-task"
            Path(stored.manifest_path).write_text(json.dumps(envelope), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "manifest hash"):
                store.read_verified_raw(stored)

    def test_same_bytes_in_new_generation_reuses_bin_but_keeps_two_manifests(self):
        """Leaving refresh generation out of lineage would collapse distinct collections."""
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

    def test_manifest_carries_fetch_verification_and_task_provenance(self):
        """Dropping any persisted provenance field would make the envelope incomplete."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()

            stored = store.write_verified(fetch, verified(fetch), producing_task_id="formal-task-2")

            envelope = json.loads(Path(stored.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(envelope["content_sha256"], fetch.content_sha256)
            self.assertEqual(envelope["refresh_generation"], "index-v1")
            self.assertEqual(envelope["request"], {
                "dataset": "annual_report",
                "exchange": None,
                "period_or_date": "2025-12-31",
                "security_id": "SZ000001",
                "source": "cninfo",
            })
            self.assertEqual(envelope["verification"], {
                "content_sha256": fetch.content_sha256,
                "effective_at_utc": "2026-03-20T08:00:00+00:00",
                "reasons": [],
                "status": "verified",
            })
            self.assertEqual(envelope["producing_task_id"], "formal-task-2")

    def test_rejected_or_mismatched_verification_cannot_be_stored(self):
        """Accepting unverified evidence or a different payload hash breaks the trust boundary."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            rejected = verify_official_fetch(
                OfficialFetch(**{**fetch.__dict__, "raw_bytes": b""}), SourcePolicy.cninfo()
            )

            with self.assertRaisesRegex(ValueError, "verified"):
                store.write_verified(fetch, rejected, producing_task_id=None)

            other_fetch = verified_fetch(raw_bytes=b"other bytes")
            with self.assertRaisesRegex(ValueError, "content hash"):
                store.write_verified(fetch, verified(other_fetch), producing_task_id=None)


if __name__ == "__main__":
    unittest.main()
