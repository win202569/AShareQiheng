"""Filesystem-boundary tests for immutable Formal V3 feature bundles."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_feature_contract import (
    FormalEvidenceRef,
    FormalFeatureBundle,
    FormalFeatureValue,
)
from ashare_pipeline.formal_feature_store import (
    FormalFeatureBundleStore,
    FormalStoredFeatureBundle,
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def fixture_bundle(**changes: object) -> FormalFeatureBundle:
    evidence = FormalEvidenceRef(
        formal_fact_id="1" * 64,
        source_snapshot_id="11111111-1111-4111-8111-111111111111",
        source_content_sha256="2" * 64,
        source_refresh_generation="refresh-v1",
        source_field="REVENUE",
        raw_value_sha256="3" * 64,
        published_at_utc="2026-03-20T08:00:00+00:00",
        published_precision="timestamp",
        effective_at_utc="2026-03-20T08:00:00+00:00",
        mapping_version="mapping-v1",
    )
    feature = FormalFeatureValue(
        slot_id="general_nonfinancial.growth",
        value=0.25,
        unit="ratio",
        status="derived",
        formula_version="formula-v1",
        evidence=(evidence,),
        missing_reason=None,
    )
    values: dict[str, object] = {
        "schema_version": 1,
        "contract_version": "formal-features-v1",
        "security_id": "SH600001",
        "as_of_utc": "2026-09-04T00:00:00+00:00",
        "template_id": "general_nonfinancial",
        "registry_manifest_hash": "4" * 64,
        "feature_registry_hash": "5" * 64,
        "input_hash": "6" * 64,
        "values": (feature,),
        "history_endpoints": ("2024-12-31", "2025-12-31"),
        "comparable_quarter_keys": ("2025Q1", "2025Q2"),
        "blockers": (),
    }
    values.update(changes)
    return FormalFeatureBundle(**values)


def create_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise OSError(result.stderr or result.stdout or "junction creation failed")
    else:
        os.symlink(target, link, target_is_directory=True)


class FormalFeatureStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.store = FormalFeatureBundleStore(self.root)
        self.bundle = fixture_bundle()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def expected_paths(self) -> tuple[Path, Path, Path]:
        directory = self.root.resolve() / "data" / "formal" / "features"
        bundle_hash = self.bundle.bundle_hash()
        return (
            directory / f"{bundle_hash}.json",
            directory / f"{bundle_hash}.manifest.json",
            directory / f"{bundle_hash}.lock",
        )

    def test_write_and_verified_read_use_exact_content_addressed_files(self) -> None:
        saved = self.store.write(self.bundle)
        bundle_path, manifest_path, _ = self.expected_paths()

        self.assertEqual(saved.bundle_path, str(bundle_path))
        self.assertEqual(saved.manifest_path, str(manifest_path))
        self.assertEqual(saved.bundle_hash, self.bundle.bundle_hash())
        self.assertEqual(bundle_path.read_bytes(), self.bundle.canonical_bytes())
        manifest_bytes = manifest_path.read_bytes()
        self.assertEqual(saved.manifest_hash, hashlib.sha256(manifest_bytes).hexdigest())
        self.assertEqual(self.store.read_verified(saved), self.bundle)
        manifest = json.loads(manifest_bytes)
        self.assertEqual(
            set(manifest),
            {
                "schema_version", "kind", "bundle_hash", "input_hash", "security_id",
                "as_of_utc", "template_id", "registry_manifest_hash",
                "feature_registry_hash", "bundle_schema_version", "contract_version",
            },
        )
        self.assertNotIn("path", repr(manifest))
        self.assertNotIn("created", repr(manifest))

    def test_repeated_identical_write_is_idempotent(self) -> None:
        first = self.store.write(self.bundle)
        bundle_path, manifest_path, _ = self.expected_paths()
        before = (bundle_path.read_bytes(), manifest_path.read_bytes())

        second = self.store.write(self.bundle)

        self.assertEqual(second, first)
        self.assertEqual((bundle_path.read_bytes(), manifest_path.read_bytes()), before)

    def test_read_rejects_tampered_bundle_or_manifest(self) -> None:
        for target in ("bundle", "manifest"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as root:
                store = FormalFeatureBundleStore(root)
                saved = store.write(self.bundle)
                path = Path(saved.bundle_path if target == "bundle" else saved.manifest_path)
                path.write_bytes(b'{"tampered":true}')
                with self.assertRaisesRegex(ValueError, target):
                    store.read_verified(saved)

    def test_existing_bundle_conflict_never_overwrites_bytes(self) -> None:
        bundle_path, manifest_path, _ = self.expected_paths()
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_bytes(b"conflicting bundle")

        with self.assertRaisesRegex(ValueError, "bundle conflict"):
            self.store.write(self.bundle)

        self.assertEqual(bundle_path.read_bytes(), b"conflicting bundle")
        self.assertFalse(manifest_path.exists())

    def test_competing_target_created_during_publication_is_never_overwritten(self) -> None:
        bundle_path, manifest_path, _ = self.expected_paths()
        real_link = os.link
        raced = False

        def competing_link(source: object, target: object, *args: object, **kwargs: object) -> None:
            nonlocal raced
            if not raced:
                raced = True
                bundle_path.write_bytes(b"competing writer")
            real_link(source, target, *args, **kwargs)

        with patch("ashare_pipeline.formal_feature_store.os.link", side_effect=competing_link):
            with self.assertRaisesRegex(ValueError, "bundle conflict"):
                self.store.write(self.bundle)

        self.assertTrue(raced)
        self.assertEqual(bundle_path.read_bytes(), b"competing writer")
        self.assertFalse(manifest_path.exists())
        self.assertEqual(list(bundle_path.parent.glob("*.part")), [])
        self.assertEqual(list(bundle_path.parent.glob("*.lock")), [])

    def test_existing_manifest_conflict_never_overwrites_bytes(self) -> None:
        bundle_path, manifest_path, _ = self.expected_paths()
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_bytes(self.bundle.canonical_bytes())
        manifest_path.write_bytes(b"conflicting manifest")

        with self.assertRaisesRegex(ValueError, "manifest conflict"):
            self.store.write(self.bundle)

        self.assertEqual(bundle_path.read_bytes(), self.bundle.canonical_bytes())
        self.assertEqual(manifest_path.read_bytes(), b"conflicting manifest")

    def test_orphan_complete_bundle_can_finish_manifest_but_manifest_first_is_rejected(self) -> None:
        bundle_path, manifest_path, _ = self.expected_paths()
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_bytes(self.bundle.canonical_bytes())
        saved = self.store.write(self.bundle)
        self.assertTrue(manifest_path.exists())
        self.assertEqual(self.store.read_verified(saved), self.bundle)

        with tempfile.TemporaryDirectory() as root:
            store = FormalFeatureBundleStore(root)
            other = fixture_bundle(input_hash="7" * 64)
            directory = Path(root).resolve() / "data" / "formal" / "features"
            directory.mkdir(parents=True)
            manifest_first = directory / f"{other.bundle_hash()}.manifest.json"
            manifest_first.write_bytes(b"premature manifest")
            with self.assertRaisesRegex(ValueError, "manifest-first"):
                store.write(other)
            self.assertFalse((directory / f"{other.bundle_hash()}.json").exists())

    def test_active_or_stale_lock_fails_without_waiting_or_deleting_lock(self) -> None:
        bundle_path, manifest_path, lock_path = self.expected_paths()
        lock_path.parent.mkdir(parents=True)
        lock_path.write_bytes(b"active writer")

        with self.assertRaisesRegex(ValueError, "lock"):
            self.store.write(self.bundle)

        self.assertEqual(lock_path.read_bytes(), b"active writer")
        self.assertFalse(bundle_path.exists())
        self.assertFalse(manifest_path.exists())

    def test_orphan_part_is_not_trusted_and_own_failure_parts_are_cleaned(self) -> None:
        bundle_path, manifest_path, lock_path = self.expected_paths()
        bundle_path.parent.mkdir(parents=True)
        orphan = bundle_path.parent / f"{self.bundle.bundle_hash()}.orphan.part"
        orphan.write_bytes(b"untrusted partial")
        saved = self.store.write(self.bundle)
        self.assertEqual(self.store.read_verified(saved), self.bundle)
        self.assertEqual(orphan.read_bytes(), b"untrusted partial")

        with tempfile.TemporaryDirectory() as root:
            store = FormalFeatureBundleStore(root)
            failed_bundle = fixture_bundle(input_hash="8" * 64)
            directory = Path(root).resolve() / "data" / "formal" / "features"
            with patch("ashare_pipeline.formal_feature_store.os.link", side_effect=OSError("disk failure")):
                with self.assertRaisesRegex(ValueError, "write failed"):
                    store.write(failed_bundle)
            self.assertEqual(list(directory.glob("*.part")), [])
            self.assertEqual(list(directory.glob("*.lock")), [])
            self.assertEqual(list(directory.glob("*.json")), [])
        self.assertFalse(lock_path.exists())

    def test_directory_replacement_race_cannot_write_through_external_link(self) -> None:
        bundle_path, _, lock_path = self.expected_paths()
        directory = bundle_path.parent
        displaced = directory.parent / "features.displaced"
        external = self.root / "external-target"
        external.mkdir()
        real_open = os.open
        raced = False

        def replacing_open(
            path: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
        ) -> int:
            nonlocal raced
            if not raced and str(path).endswith(".lock"):
                raced = True
                directory.rename(displaced)
                create_directory_link(directory, external)
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with patch("ashare_pipeline.formal_feature_store.os.open", side_effect=replacing_open):
            with self.assertRaises(ValueError):
                self.store.write(self.bundle)

        self.assertTrue(raced)
        self.assertEqual(list(external.iterdir()), [])
        self.assertEqual(list(displaced.glob("*.part")), [])
        self.assertEqual(list(displaced.glob("*.lock")), [])
        self.assertFalse(lock_path.exists())

    def test_forged_or_mutated_receipt_and_wrong_store_root_are_rejected(self) -> None:
        saved = self.store.write(self.bundle)
        with self.assertRaises(TypeError):
            FormalStoredFeatureBundle(
                saved.bundle_path, saved.manifest_path, saved.bundle_hash, saved.manifest_hash
            )
        forged = object.__new__(FormalStoredFeatureBundle)
        for field in ("bundle_path", "manifest_path", "bundle_hash", "manifest_hash"):
            object.__setattr__(forged, field, getattr(saved, field))
        with self.assertRaises(ValueError):
            self.store.read_verified(forged)

        object.__setattr__(saved, "bundle_path", str(self.root.parent / "escape.json"))
        with self.assertRaises(ValueError):
            self.store.read_verified(saved)

        healthy = self.store.write(self.bundle)
        with tempfile.TemporaryDirectory() as other_root:
            with self.assertRaises(ValueError):
                FormalFeatureBundleStore(other_root).read_verified(healthy)

    def test_symlinked_bundle_is_rejected_when_platform_allows_symlinks(self) -> None:
        saved = self.store.write(self.bundle)
        bundle_path = Path(saved.bundle_path)
        external = self.root / "external.json"
        external.write_bytes(self.bundle.canonical_bytes())
        bundle_path.unlink()
        try:
            os.symlink(external, bundle_path)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")

        with self.assertRaisesRegex(ValueError, "link"):
            self.store.read_verified(saved)


if __name__ == "__main__":
    unittest.main()
