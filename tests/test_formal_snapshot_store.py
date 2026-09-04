import hashlib
import json
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import tempfile
import unittest

from ashare_pipeline.formal_evidence import (
    EvidenceVerification,
    OfficialFetch,
    OfficialRequest,
    SourcePolicy,
    VerifiedCalendarBinding,
    verify_official_fetch,
)
from ashare_pipeline.formal_snapshot_store import (
    FormalSnapshotStore,
    FormalStoredSnapshot,
    ValidatedFormalSnapshot,
)


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


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def rewrite_manifest(
    stored: FormalStoredSnapshot,
    mutate,
) -> FormalStoredSnapshot:
    envelope = json.loads(Path(stored.manifest_path).read_text(encoding="utf-8"))
    mutate(envelope)
    payload = {key: value for key, value in envelope.items() if key != "manifest_sha256"}
    manifest_sha256 = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    envelope["manifest_sha256"] = manifest_sha256
    manifest_path = Path(stored.manifest_path).with_name(
        f"{manifest_sha256}.manifest.json"
    )
    manifest_path.write_bytes(canonical_json_bytes(envelope))
    return replace(
        stored,
        manifest_path=str(manifest_path),
        manifest_sha256=manifest_sha256,
    )


class FormalSnapshotStoreTests(unittest.TestCase):
    def test_validate_stored_snapshot_recomputes_verification_instead_of_trusting_status(self):
        """A public EvidenceVerification constructor must not mint trusted evidence."""
        cases = (
            (
                lambda fetch: fetch,
                lambda fetch: EvidenceVerification(
                    "verified", fetch.content_sha256, ("forged_reason",), fetch.effective_at_utc
                ),
                "reasons",
            ),
            (
                lambda fetch: fetch,
                lambda fetch: EvidenceVerification(
                    "verified",
                    fetch.content_sha256,
                    (),
                    "2026-03-20T09:00:00+00:00",
                ),
                "effective",
            ),
            (
                lambda fetch: replace(fetch, original_url="http://example.invalid/report.pdf"),
                lambda fetch: EvidenceVerification(
                    "verified", fetch.content_sha256, (), fetch.effective_at_utc
                ),
                "verification",
            ),
            (
                lambda fetch: replace(fetch, published_at_utc="2026-03-20T08:00:00"),
                lambda fetch: EvidenceVerification(
                    "verified", fetch.content_sha256, (), fetch.effective_at_utc
                ),
                "verification",
            ),
        )
        for mutate_fetch, build_verification, expected_error in cases:
            with self.subTest(expected_error=expected_error), tempfile.TemporaryDirectory() as root:
                store = FormalSnapshotStore(root)
                fetch = mutate_fetch(verified_fetch())
                verification = build_verification(fetch)
                stored = store.write_verified(fetch, verification, producing_task_id=None)

                with self.assertRaisesRegex(ValueError, expected_error):
                    store.validate_stored_snapshot(
                        fetch, stored, verification, expected_producing_task_id=None
                    )

    def test_validate_stored_snapshot_rejects_self_consistent_invalid_nested_values(self):
        """Runtime-invalid typed fields must not escape in the validated projection."""
        cases = (
            (
                lambda fetch: replace(
                    fetch,
                    request=replace(fetch.request, security_id="SZ１２３４５６"),
                    declared_security_id="SZ１２３４５６",
                ),
                "security",
            ),
            (
                lambda fetch: replace(
                    fetch,
                    request=replace(fetch.request, period_or_date=20251231),
                    declared_period=20251231,
                ),
                "period_or_date",
            ),
            (
                lambda fetch: replace(
                    fetch,
                    request=replace(fetch.request, exchange=1),
                ),
                "exchange",
            ),
            (lambda fetch: replace(fetch, parser_id=7), "parser_id"),
            (lambda fetch: replace(fetch, parser_version=""), "parser_version"),
            (lambda fetch: replace(fetch, mapping_version=7), "mapping_version"),
            (lambda fetch: replace(fetch, mapping_version=""), "mapping_version"),
            (lambda fetch: replace(fetch, mapping_version="bad/version"), "mapping_version"),
        )
        for mutate_fetch, expected_error in cases:
            with self.subTest(expected_error=expected_error), tempfile.TemporaryDirectory() as root:
                store = FormalSnapshotStore(root)
                fetch = mutate_fetch(verified_fetch())
                verification = EvidenceVerification(
                    "verified", fetch.content_sha256, (), fetch.effective_at_utc
                )
                stored = store.write_verified(fetch, verification, producing_task_id=None)

                with self.assertRaisesRegex(ValueError, expected_error):
                    store.validate_stored_snapshot(
                        fetch, stored, verification, expected_producing_task_id=None
                    )

    def test_validate_stored_snapshot_returns_frozen_manifest_derived_projection(self):
        """Returning caller metadata would let StateStore persist uninspected lineage."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch(raw_bytes=b"\xe5\xae\xa1\xe8\xae\xa1\x00PDF")
            verification = verified(fetch)
            stored = store.write_verified(
                fetch, verification, producing_task_id="formal-task-2"
            )

            inspected = store.validate_stored_snapshot(
                fetch,
                stored,
                verification,
                expected_producing_task_id="formal-task-2",
            )

            self.assertIsInstance(inspected, ValidatedFormalSnapshot)
            self.assertEqual(inspected.source, "cninfo")
            self.assertEqual(inspected.dataset, "annual_report")
            self.assertEqual(
                inspected.request_json,
                '{"dataset":"annual_report","exchange":null,"period_or_date":"2025-12-31",'
                '"security_id":"SZ000001","source":"cninfo"}',
            )
            self.assertEqual(inspected.request_fingerprint, fetch.request.request_fingerprint)
            self.assertEqual(inspected.content_sha256, fetch.content_sha256)
            self.assertEqual(inspected.manifest_sha256, stored.manifest_sha256)
            self.assertEqual(inspected.producing_task_id, "formal-task-2")
            self.assertEqual(inspected.verification_json, json.dumps({
                "content_sha256": fetch.content_sha256,
                "effective_at_utc": "2026-03-20T08:00:00+00:00",
                "reasons": [],
                "status": "verified",
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            with self.assertRaises(FrozenInstanceError):
                inspected.source = "tampered"  # type: ignore[misc]

    def test_validate_stored_snapshot_rejects_wrong_types_status_and_producer(self):
        """Loose input typing or producer matching would let a receipt claim other evidence."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            verification = verified(fetch)
            task_stored = store.write_verified(
                fetch, verification, producing_task_id="formal-task-2"
            )

            invalid_calls = (
                (object(), task_stored, verification, "formal-task-2", "OfficialFetch"),
                (fetch, object(), verification, "formal-task-2", "FormalStoredSnapshot"),
                (fetch, task_stored, object(), "formal-task-2", "EvidenceVerification"),
                (fetch, task_stored, verification, 2, "producing_task_id"),
            )
            for bad_fetch, bad_stored, bad_verification, producer, message in invalid_calls:
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    store.validate_stored_snapshot(
                        bad_fetch,
                        bad_stored,
                        bad_verification,
                        expected_producing_task_id=producer,
                    )

            rejected = EvidenceVerification(
                "rejected", fetch.content_sha256, ("source_not_authoritative",), None
            )
            with self.assertRaisesRegex(ValueError, "verified"):
                store.validate_stored_snapshot(
                    fetch,
                    task_stored,
                    rejected,
                    expected_producing_task_id="formal-task-2",
                )
            for expected_producer in (None, "formal-task-other"):
                with self.subTest(expected_producer=expected_producer), self.assertRaisesRegex(
                    ValueError, "producing_task_id"
                ):
                    store.validate_stored_snapshot(
                        fetch,
                        task_stored,
                        verification,
                        expected_producing_task_id=expected_producer,
                    )

    def test_validate_stored_snapshot_enforces_bootstrap_and_task_producer_rules(self):
        """Implicitly treating null and task-produced manifests alike would break receipts."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            verification = verified(fetch)
            bootstrap = store.write_verified(fetch, verification, producing_task_id=None)
            task = store.write_verified(
                fetch, verification, producing_task_id="formal-task-2"
            )

            self.assertIsNone(store.validate_stored_snapshot(
                fetch, bootstrap, verification, expected_producing_task_id=None
            ).producing_task_id)
            self.assertEqual(store.validate_stored_snapshot(
                fetch, task, verification, expected_producing_task_id="formal-task-2"
            ).producing_task_id, "formal-task-2")
            with self.assertRaisesRegex(ValueError, "producing_task_id"):
                store.validate_stored_snapshot(
                    fetch, bootstrap, verification,
                    expected_producing_task_id="formal-task-2",
                )

    def test_validate_stored_snapshot_preserves_verified_date_only_snapshot(self):
        """Recomputation must retain valid calendar-bound Task 2 evidence."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            binding = VerifiedCalendarBinding(
                snapshot_id="calendar-snapshot-1",
                manifest_sha256="c" * 64,
                exchange="SZ",
                freeze_at_utc="2026-08-31T07:00:00+00:00",
                registry_manifest_hash="r" * 64,
                selector_hash="s" * 64,
                prerequisite_task_id="calendar-task-1",
            )
            fetch = replace(
                verified_fetch(),
                request=replace(verified_fetch().request, exchange="SZ"),
                published_precision="date_only",
                effective_time_evidence_hash=binding.manifest_sha256,
            )
            verification = verify_official_fetch(
                fetch, SourcePolicy.cninfo(), calendar_binding=binding
            )
            self.assertEqual(verification.status, "verified")
            stored = store.write_verified(fetch, verification, producing_task_id=None)

            inspected = store.validate_stored_snapshot(
                fetch, stored, verification, expected_producing_task_id=None
            )

            self.assertEqual(
                inspected.effective_time_evidence_hash, binding.manifest_sha256
            )

    def test_validate_stored_snapshot_rejects_content_and_hash_forgery(self):
        """Trusting stored hashes or filenames would permit substituted bytes or lineage."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            verification = verified(fetch)
            stored = store.write_verified(fetch, verification, producing_task_id=None)

            Path(stored.content_path).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "content hash"):
                store.validate_stored_snapshot(
                    fetch, stored, verification, expected_producing_task_id=None
                )

        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            verification = verified(fetch)
            stored = store.write_verified(fetch, verification, producing_task_id=None)
            forged_hash = "A" * 64
            forged = replace(stored, content_sha256=forged_hash)
            with self.assertRaisesRegex(ValueError, "content hash"):
                store.validate_stored_snapshot(
                    fetch, forged, verification, expected_producing_task_id=None
                )
            forged = replace(
                stored,
                manifest_path=str(Path(stored.manifest_path).with_name("0" * 64 + ".manifest.json")),
            )
            with self.assertRaisesRegex(ValueError, "manifest hash.*path"):
                store.validate_stored_snapshot(
                    fetch, forged, verification, expected_producing_task_id=None
                )
            wrong_content_name = Path(stored.content_path).with_name("0" * 64 + ".bin")
            wrong_content_name.write_bytes(fetch.raw_bytes)
            forged = replace(stored, content_path=str(wrong_content_name))
            with self.assertRaisesRegex(ValueError, "content hash.*path"):
                store.validate_stored_snapshot(
                    fetch, forged, verification, expected_producing_task_id=None
                )

    def test_validate_stored_snapshot_rejects_non_lowercase_effective_evidence_hash(self):
        """Accepting a noncanonical evidence hash would create unstable calendar lineage."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = replace(
                verified_fetch(),
                published_precision="date_only",
                effective_time_evidence_hash="A" * 64,
            )
            verification = EvidenceVerification(
                "verified", fetch.content_sha256, (), fetch.effective_at_utc
            )
            stored = store.write_verified(fetch, verification, producing_task_id=None)

            with self.assertRaisesRegex(ValueError, "effective_time_evidence_hash"):
                store.validate_stored_snapshot(
                    fetch, stored, verification, expected_producing_task_id=None
                )

    def test_validate_stored_snapshot_rejects_self_consistent_manifest_field_mismatches(self):
        """Only exact fetch and verification lineage may survive a rehashed manifest forgery."""
        cases = (
            (lambda envelope: envelope["request"].__setitem__("source", "sse"), "request|lineage"),
            (lambda envelope: envelope["request"].__setitem__("dataset", "balance_sheet"), "request|lineage"),
            (lambda envelope: envelope["request"].__setitem__("security_id", "SZ000002"), "request"),
            (lambda envelope: envelope["request"].__setitem__("period_or_date", "2024-12-31"), "request"),
            (lambda envelope: envelope["request"].__setitem__("exchange", "SZ"), "request"),
            (lambda envelope: envelope.__setitem__("original_url", "https://static.cninfo.com.cn/other.pdf"), "original_url"),
            (lambda envelope: envelope.__setitem__("published_at_utc", "2026-03-20T09:00:00+00:00"), "published_at_utc"),
            (lambda envelope: envelope.__setitem__("published_precision", "date_only"), "published_precision"),
            (lambda envelope: envelope.__setitem__("source_updated_at_utc", "2026-03-20T08:30:00+00:00"), "source_updated_at_utc"),
            (lambda envelope: envelope.__setitem__("captured_at_utc", "2026-09-04T09:00:00+00:00"), "captured_at_utc"),
            (lambda envelope: envelope.__setitem__("effective_at_utc", "2026-03-20T09:00:00+00:00"), "effective_at_utc"),
            (lambda envelope: envelope.__setitem__("effective_time_evidence_hash", "0" * 64), "effective_time_evidence_hash"),
            (lambda envelope: envelope.__setitem__("refresh_generation", "index-v2"), "refresh_generation"),
            (lambda envelope: envelope.__setitem__("parser_id", "other-parser"), "parser_id"),
            (lambda envelope: envelope.__setitem__("parser_version", "other-parser-v2"), "parser_version"),
            (lambda envelope: envelope.__setitem__("mapping_version", "other-mapping-v2"), "mapping_version"),
            (lambda envelope: envelope.__setitem__("declared_security_id", "SZ000002"), "declared_security_id"),
            (lambda envelope: envelope.__setitem__("declared_period", "2024-12-31"), "declared_period"),
            (lambda envelope: envelope["verification"].__setitem__("status", "rejected"), "verification"),
            (lambda envelope: envelope["verification"].__setitem__("reasons", ["forged"]), "verification"),
            (lambda envelope: envelope["verification"].__setitem__("effective_at_utc", None), "verification"),
            (lambda envelope: envelope["verification"].__setitem__("content_sha256", "0" * 64), "verification"),
            (lambda envelope: envelope.__setitem__("content_sha256", "0" * 64), "content_sha256"),
        )
        for mutate, field in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                store = FormalSnapshotStore(root)
                fetch = verified_fetch()
                verification = verified(fetch)
                stored = store.write_verified(fetch, verification, producing_task_id=None)
                forged = rewrite_manifest(stored, mutate)
                with self.assertRaisesRegex(ValueError, field):
                    store.validate_stored_snapshot(
                        fetch, forged, verification, expected_producing_task_id=None
                    )

    def test_validate_stored_snapshot_rejects_duplicate_and_noncanonical_manifest(self):
        """Permissive JSON parsing would make one manifest hash carry ambiguous metadata."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            verification = verified(fetch)
            stored = store.write_verified(fetch, verification, producing_task_id=None)
            path = Path(stored.manifest_path)
            original = path.read_bytes()
            marker = b'"producing_task_id":null,'
            path.write_bytes(original.replace(marker, marker + marker, 1))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                store.validate_stored_snapshot(
                    fetch, stored, verification, expected_producing_task_id=None
                )

        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            verification = verified(fetch)
            stored = store.write_verified(fetch, verification, producing_task_id=None)
            path = Path(stored.manifest_path)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical"):
                store.validate_stored_snapshot(
                    fetch, stored, verification, expected_producing_task_id=None
                )

    def test_validate_stored_snapshot_rejects_unsafe_or_noncanonical_paths(self):
        """Accepting inferred, traversing, or cross-directory paths breaks raw-store isolation."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            verification = verified(fetch)
            stored = store.write_verified(fetch, verification, producing_task_id=None)
            content_path = Path(stored.content_path)
            traversal_path = content_path.parent / ".." / content_path.parent.name / content_path.name
            different_directory = content_path.parent.parent / "other" / content_path.name
            different_directory.parent.mkdir()
            different_directory.write_bytes(fetch.raw_bytes)
            invalid_paths = (
                replace(stored, content_path=os.path.relpath(stored.content_path, root)),
                replace(stored, content_path=str(traversal_path)),
                replace(stored, content_path=str(different_directory)),
            )
            for invalid in invalid_paths:
                with self.subTest(path=invalid.content_path), self.assertRaisesRegex(
                    ValueError, "path|lineage|directory"
                ):
                    store.validate_stored_snapshot(
                        fetch, invalid, verification, expected_producing_task_id=None
                    )

            unsafe_fetch = replace(
                fetch,
                request=replace(fetch.request, source="../cninfo"),
            )
            unsafe_verification = EvidenceVerification(
                "verified", fetch.content_sha256, (), fetch.effective_at_utc
            )
            unsafe_manifest = rewrite_manifest(
                stored,
                lambda envelope: envelope["request"].__setitem__("source", "../cninfo"),
            )
            with self.assertRaisesRegex(ValueError, "safe single path component"):
                store.validate_stored_snapshot(
                    unsafe_fetch,
                    unsafe_manifest,
                    unsafe_verification,
                    expected_producing_task_id=None,
                )
            unsafe_dataset_fetch = replace(
                fetch,
                request=replace(fetch.request, dataset="annual/report"),
            )
            unsafe_dataset_manifest = rewrite_manifest(
                stored,
                lambda envelope: envelope["request"].__setitem__(
                    "dataset", "annual/report"
                ),
            )
            with self.assertRaisesRegex(ValueError, "safe single path component"):
                store.validate_stored_snapshot(
                    unsafe_dataset_fetch,
                    unsafe_dataset_manifest,
                    unsafe_verification,
                    expected_producing_task_id=None,
                )

    def test_validate_stored_snapshot_rejects_symlink_escape_when_available(self):
        """Resolving an evidence file outside the raw-store root would bypass path lineage."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            verification = verified(fetch)
            stored = store.write_verified(fetch, verification, producing_task_id=None)
            content_path = Path(stored.content_path)
            outside_path = Path(outside) / content_path.name
            outside_path.write_bytes(fetch.raw_bytes)
            content_path.unlink()
            try:
                content_path.symlink_to(outside_path)
            except OSError as error:
                self.skipTest(f"file symlinks unavailable in this test environment: {error}")

            with self.assertRaisesRegex(ValueError, "stay inside|canonical"):
                store.validate_stored_snapshot(
                    fetch, stored, verification, expected_producing_task_id=None
                )

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
            Path(stored.manifest_path).write_text(
                json.dumps(envelope, sort_keys=True, separators=(",", ":")), encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "manifest hash"):
                store.read_verified_raw(stored)

    def test_existing_content_symlink_outside_store_is_rejected(self):
        """Following an existing hash-path symlink would accept outside-root bytes."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside_root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            target = (
                Path(root)
                / "data"
                / "raw"
                / "formal"
                / "cninfo"
                / "annual_report"
                / f"{fetch.content_sha256}.bin"
            )
            target.parent.mkdir(parents=True)
            outside_content = Path(outside_root) / "outside.bin"
            outside_content.write_bytes(fetch.raw_bytes)
            try:
                target.symlink_to(outside_content)
            except OSError as error:
                self.skipTest(f"file symlinks unavailable in this test environment: {error}")

            with self.assertRaisesRegex(ValueError, "stay inside"):
                store.write_verified(fetch, verified(fetch), producing_task_id=None)

    def test_existing_manifest_symlink_outside_store_is_rejected(self):
        """Following an existing lineage-manifest symlink would accept outside provenance."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside_root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            target = Path(stored.manifest_path)
            outside_manifest = Path(outside_root) / target.name
            outside_manifest.write_bytes(target.read_bytes())
            target.unlink()
            try:
                target.symlink_to(outside_manifest)
            except OSError as error:
                self.skipTest(f"file symlinks unavailable in this test environment: {error}")

            with self.assertRaisesRegex(ValueError, "stay inside"):
                store.write_verified(fetch, verified(fetch), producing_task_id=None)

    def test_pretty_printed_manifest_bytes_are_rejected(self):
        """Re-canonicalizing instead of checking stored bytes would hide byte-level tampering."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            manifest_path = Path(stored.manifest_path)
            envelope = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "canonical"):
                store.read_verified_raw(stored)

    def test_duplicate_manifest_keys_are_rejected(self):
        """A JSON parser that silently keeps the last duplicate key would hide tampering."""
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            manifest_path = Path(stored.manifest_path)
            original = manifest_path.read_bytes()
            marker = b'"producing_task_id":null,'
            self.assertIn(marker, original)
            manifest_path.write_bytes(original.replace(marker, marker + marker, 1))

            with self.assertRaisesRegex(ValueError, "duplicate"):
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
