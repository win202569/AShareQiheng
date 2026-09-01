import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

from ashare_pipeline.feature_contract import canonical_sha256
from ashare_pipeline.snapshot_repository import SnapshotRepository
from ashare_pipeline.snapshot_store import SnapshotStore
from ashare_pipeline.sources import FetchBatch
from ashare_pipeline.state_store import StateStore


def statement_batch(symbol: str, total_assets: float, fetched_at: str) -> FetchBatch:
    return FetchBatch(
        "akshare",
        "balance_sheet",
        {"symbol": symbol, "report_period": "2026-06-30"},
        [{"REPORT_DATE": "2026-06-30", "TOTAL_ASSETS": total_assets}],
        fetched_at,
        "1.0",
        {"report_period_match_count": 1},
    )


class SnapshotRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tempdir.name)
        self.data_root = self.project_root / "data"
        self.state_store = StateStore(self.data_root / "state.sqlite3")
        self.state_store.initialize()
        self.snapshot_store = SnapshotStore(self.data_root)
        self.repository = SnapshotRepository(
            self.data_root, self.state_store, self.snapshot_store
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_find_exact_never_returns_another_symbol_global_latest(self):
        first, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        self.repository.persist(
            statement_batch("SH600002", 200.0, "2026-08-29T01:00:00+00:00")
        )

        observed = self.repository.find_exact(
            "akshare",
            "balance_sheet",
            {"symbol": "SH600001", "report_period": "2026-06-30"},
        )

        self.assertIsNotNone(observed)
        self.assertEqual(observed.id, first.id)

    def test_find_exact_returns_latest_exact_revision_by_fetched_created_and_hash(self):
        first, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        second, _ = self.repository.persist(
            statement_batch("SH600001", 200.0, "2026-08-29T01:00:00+00:00")
        )
        third, _ = self.repository.persist(
            statement_batch("SH600001", 300.0, "2026-08-29T02:00:00+00:00")
        )
        with closing(sqlite3.connect(self.data_root / "state.sqlite3")) as connection:
            connection.execute(
                "UPDATE source_snapshot SET fetched_at = ?, created_at = ? WHERE id = ?",
                ("2026-08-29T03:00:00+00:00", "2026-08-29T04:00:00+00:00", first.id),
            )
            connection.execute(
                "UPDATE source_snapshot SET fetched_at = ?, created_at = ? WHERE id = ?",
                ("2026-08-29T03:00:00+00:00", "2026-08-29T05:00:00+00:00", second.id),
            )
            connection.execute(
                "UPDATE source_snapshot SET fetched_at = ?, created_at = ? WHERE id = ?",
                ("2026-08-29T03:00:00+00:00", "2026-08-29T05:00:00+00:00", third.id),
            )
            connection.commit()

        observed = self.repository.find_exact(
            "akshare", "balance_sheet", {"symbol": "SH600001", "report_period": "2026-06-30"}
        )

        self.assertEqual(observed.id, max((second, third), key=lambda item: item.payload_hash).id)

    def test_find_exact_returns_none_for_unmatched_request_source_or_dataset(self):
        self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )

        self.assertIsNone(self.repository.find_exact(
            "akshare", "balance_sheet", {"symbol": "SH600002", "report_period": "2026-06-30"}
        ))
        self.assertIsNone(self.repository.find_exact(
            "baostock", "balance_sheet", {"symbol": "SH600001", "report_period": "2026-06-30"}
        ))
        self.assertIsNone(self.repository.find_exact(
            "akshare", "profit_sheet", {"symbol": "SH600001", "report_period": "2026-06-30"}
        ))

    def test_get_looks_up_only_the_requested_snapshot_id(self):
        first, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        second, _ = self.repository.persist(
            statement_batch("SH600002", 200.0, "2026-08-29T01:00:00+00:00")
        )

        self.assertEqual(self.repository.get(second.id), second)
        self.assertNotEqual(self.repository.get(second.id), first)
        self.assertIsNone(self.repository.get("does-not-exist"))

    def test_persist_reuses_identical_request_content_without_a_second_row(self):
        first, first_created = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        duplicate, duplicate_created = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-30T00:00:00+00:00")
        )

        self.assertTrue(first_created)
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate, first)
        with closing(sqlite3.connect(self.data_root / "state.sqlite3")) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0], 1)

    def test_concurrent_same_target_persist_keeps_first_published_batch_and_db_ref(self):
        first_batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        second_batch = statement_batch("SH600001", 100.0, "2026-08-29T01:00:00+00:00")
        publish_barrier = threading.Barrier(2)
        first_persisted = threading.Event()
        results: dict[str, tuple[object, bool]] = {}
        errors: list[BaseException] = []
        result_lock = threading.Lock()

        def controlled_publish(real_publish):
            def publish(source, target, *args, **kwargs):
                publish_barrier.wait(timeout=5)
                is_first = first_batch.fetched_at_utc in Path(source).read_text(encoding="utf-8")
                if not is_first and not first_persisted.wait(timeout=5):
                    raise RuntimeError("first writer did not persist before second publish")
                return real_publish(source, target, *args, **kwargs)
            return publish

        def persist(name: str, batch: FetchBatch) -> None:
            try:
                result = self.repository.persist(batch)
                with result_lock:
                    results[name] = result
                if name == "first":
                    first_persisted.set()
            except BaseException as error:
                with result_lock:
                    errors.append(error)

        real_replace = os.replace
        real_link = os.link
        with patch("ashare_pipeline.snapshot_store.os.replace", new=controlled_publish(real_replace)), patch(
            "ashare_pipeline.snapshot_store.os.link", new=controlled_publish(real_link)
        ):
            first = threading.Thread(target=persist, args=("first", first_batch))
            second = threading.Thread(target=persist, args=("second", second_batch))
            first.start()
            second.start()
            first.join(timeout=10)
            second.join(timeout=10)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(set(results), {"first", "second"})
        first_ref, first_created = results["first"]
        second_ref, second_created = results["second"]
        self.assertEqual(first_ref, second_ref)
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first_ref.fetched_at, first_batch.fetched_at_utc)
        winner = self.repository.read_verified(first_ref)
        self.assertEqual(winner.batch.fetched_at_utc, first_batch.fetched_at_utc)
        self.assertEqual(self.repository.read_verified(second_ref).batch, winner.batch)

    def test_read_verified_rejects_tampered_snapshot(self):
        snapshot, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        verified = self.repository.read_verified(snapshot)
        self.assertEqual(verified.batch.records[0]["TOTAL_ASSETS"], 100.0)
        path = self.project_root / snapshot.payload_path
        path.write_text(
            path.read_text(encoding="utf-8").replace("100.0", "999.0"), encoding="utf-8"
        )

        with self.assertRaisesRegex(OSError, "hash"):
            self.repository.read_verified(snapshot)

    def test_read_verified_rejects_a_database_hash_that_does_not_match_the_file(self):
        snapshot, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        with closing(sqlite3.connect(self.data_root / "state.sqlite3")) as connection:
            connection.execute(
                "UPDATE source_snapshot SET payload_hash = ? WHERE id = ?",
                ("0" * 64, snapshot.id),
            )
            connection.commit()

        with self.assertRaisesRegex(OSError, "hash"):
            self.repository.read_verified(self.repository.get(snapshot.id))

    def test_read_verified_rejects_payload_fetch_time_that_differs_from_database(self):
        snapshot, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        path = self.project_root / snapshot.payload_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["fetched_at_utc"] = "2030-01-01T00:00:00+00:00"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(OSError, "metadata"):
            self.repository.read_verified(snapshot)

    def test_read_verified_rejects_database_fetch_time_that_differs_from_payload(self):
        snapshot, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        with closing(sqlite3.connect(self.data_root / "state.sqlite3")) as connection:
            connection.execute(
                "UPDATE source_snapshot SET fetched_at = ? WHERE id = ?",
                ("2030-01-01T00:00:00+00:00", snapshot.id),
            )
            connection.commit()

        with self.assertRaisesRegex(OSError, "metadata"):
            self.repository.read_verified(self.repository.get(snapshot.id))

    def test_persist_records_a_project_relative_data_path(self):
        snapshot, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )

        self.assertFalse(Path(snapshot.payload_path).is_absolute())
        self.assertTrue(snapshot.payload_path.startswith("data/raw/"))
        self.assertTrue((self.project_root / snapshot.payload_path).is_file())

    def test_read_verified_accepts_a_contained_absolute_legacy_path(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        path, digest, _ = self.snapshot_store.write(batch)
        snapshot_id, _ = self.state_store.record_snapshot(
            batch.source,
            batch.dataset,
            canonical_sha256(batch.request),
            digest,
            str(path.resolve()),
            len(batch.records),
            batch.fetched_at_utc,
        )

        verified = self.repository.read_verified(self.repository.get(snapshot_id))

        self.assertEqual(verified.ref.id, snapshot_id)
        self.assertEqual(verified.batch.records, batch.records)

    def test_read_verified_rejects_an_absolute_legacy_path_outside_data_root(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        contained, digest, _ = self.snapshot_store.write(batch)
        outside = self.project_root / "outside-legacy.json"
        outside.write_bytes(contained.read_bytes())
        snapshot_id, _ = self.state_store.record_snapshot(
            batch.source,
            batch.dataset,
            canonical_sha256(batch.request),
            digest,
            str(outside.resolve()),
            len(batch.records),
            batch.fetched_at_utc,
        )

        with self.assertRaisesRegex(
            ValueError, "absolute legacy snapshot path must stay inside"
        ):
            self.repository.read_verified(self.repository.get(snapshot_id))

    def test_read_verified_rejects_relative_parent_traversal(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        _, digest, _ = self.snapshot_store.write(batch)
        snapshot_id, _ = self.state_store.record_snapshot(
            batch.source, batch.dataset, canonical_sha256(batch.request), digest,
            "data/../outside.json", len(batch.records), batch.fetched_at_utc,
        )

        with self.assertRaisesRegex(ValueError, "relative"):
            self.repository.read_verified(self.repository.get(snapshot_id))

    def test_read_verified_rejects_any_backslash_in_new_relative_paths(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        _, digest, _ = self.snapshot_store.write(batch)
        for payload_path in (
            "data/raw\\akshare/balance_sheet/file.json",
            "data\\raw\\akshare\\balance_sheet\\file.json",
        ):
            snapshot_id, _ = self.state_store.record_snapshot(
                batch.source,
                batch.dataset,
                canonical_sha256(batch.request),
                digest,
                payload_path,
                len(batch.records),
                batch.fetched_at_utc,
            )
            with self.assertRaisesRegex(ValueError, "backslash"):
                self.repository.read_verified(self.repository.get(snapshot_id))

    def test_constructor_rejects_an_injected_snapshot_store_for_another_root(self):
        other_root = self.project_root / "other-data"

        with self.assertRaisesRegex(ValueError, "root"):
            SnapshotRepository(
                self.data_root, self.state_store, SnapshotStore(other_root)
            )

    def test_persist_rejects_unsafe_components_without_creating_outside_data(self):
        unsafe = FetchBatch(
            "../../escaped",
            "balance_sheet",
            {"symbol": "SH600001", "report_period": "2026-06-30"},
            [{"TOTAL_ASSETS": 100.0}],
            "2026-08-29T00:00:00+00:00",
            "1.0",
            {},
        )

        with self.assertRaisesRegex(ValueError, "component"):
            self.repository.persist(unsafe)

        self.assertEqual(list(self.project_root.rglob("*.json")), [])

    def test_read_verified_rejects_relative_symlink_escape(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        _, digest, _ = self.snapshot_store.write(batch)
        outside_dir = self.project_root.parent / f"{self.project_root.name}-outside"
        outside_dir.mkdir()
        outside = outside_dir / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        link = self.data_root / "raw" / "escape"
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", f'mklink /J "{link}" "{outside_dir}"'],
                capture_output=True,
                text=True,
                check=False,
            )
            linked = result.returncode == 0
        else:
            try:
                link.symlink_to(outside_dir, target_is_directory=True)
                linked = True
            except OSError as error:
                linked = False
        snapshot_id, _ = self.state_store.record_snapshot(
            batch.source, batch.dataset, canonical_sha256(batch.request), digest,
            "data/raw/escape/outside.json", len(batch.records), batch.fetched_at_utc,
        )

        if linked:
            with self.assertRaisesRegex(ValueError, "data directory"):
                self.repository.read_verified(self.repository.get(snapshot_id))
        else:
            original_resolve = Path.resolve
            escaped_path = self.project_root / "data" / "raw" / "escape" / "outside.json"

            def resolve(path: Path, *args, **kwargs) -> Path:
                if path == escaped_path:
                    return outside
                return original_resolve(path, *args, **kwargs)

            with patch("ashare_pipeline.snapshot_repository.Path.resolve", autospec=True, side_effect=resolve):
                with self.assertRaisesRegex(ValueError, "data directory"):
                    self.repository.read_verified(self.repository.get(snapshot_id))


if __name__ == "__main__":
    unittest.main()
