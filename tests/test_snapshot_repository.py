import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing, contextmanager
from datetime import datetime, timezone
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


class CommitFailConnection:
    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def commit(self):
        raise sqlite3.OperationalError("forced commit failure")


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

    def test_list_exact_returns_all_and_only_exact_revisions_in_winner_order(self):
        request = {"symbol": "SH600001", "report_period": "2026-06-30"}
        first, _ = self.repository.persist(
            statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        )
        second, _ = self.repository.persist(
            statement_batch("SH600001", 200.0, "2026-08-29T01:00:00+00:00")
        )
        self.repository.persist(
            statement_batch("SH600002", 300.0, "2026-08-29T02:00:00+00:00")
        )

        observed = self.repository.list_exact(
            "akshare", "balance_sheet", request
        )

        self.assertEqual([item.id for item in observed], [second.id, first.id])
        self.assertTrue(all(dict(item.request) == request for item in observed))
        self.assertEqual(
            self.repository.list_exact("akshare", "profit_sheet", request),
            (),
        )

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

    def test_owned_persist_rejects_stale_owner_and_preserves_immutable_winner(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        winner_job = self.state_store.enqueue_job(
            "deep_statement", "snapshot-owner:winner", {}
        )
        self.state_store.lease_next_job(["deep_statement"], "worker-b", 3600)
        winner, created = self.repository.persist(
            batch, job_id=winner_job, worker_id="worker-b"
        )
        winner_path = self.project_root / winner.payload_path
        winner_bytes = winner_path.read_bytes()

        stale_job = self.state_store.enqueue_job(
            "deep_statement", "snapshot-owner:stale", {}
        )
        self.state_store.lease_next_job(["deep_statement"], "worker-a", 3600)
        with closing(sqlite3.connect(self.data_root / "state.sqlite3")) as connection:
            connection.execute(
                "UPDATE job SET lease_expires_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", stale_job),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.repository.persist(batch, job_id=stale_job, worker_id="worker-a")

        self.assertTrue(created)
        self.assertEqual(winner_path.read_bytes(), winner_bytes)
        with closing(sqlite3.connect(self.data_root / "state.sqlite3")) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0], 1)

    def test_owned_snapshot_commit_failure_removes_attempt_file_and_row(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        job_id = self.state_store.enqueue_job(
            "deep_statement", "snapshot-owner:commit-failure", {}
        )
        self.state_store.lease_next_job(["deep_statement"], "worker-a", 3600)
        real_connect = self.state_store._connect

        with patch.object(
            self.state_store,
            "_connect",
            side_effect=lambda: CommitFailConnection(real_connect()),
        ), self.assertRaisesRegex(sqlite3.OperationalError, "commit failure"):
            self.repository.persist(batch, job_id=job_id, worker_id="worker-a")

        with closing(sqlite3.connect(self.state_store.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0],
                0,
            )
        self.assertEqual(list((self.data_root / "raw").rglob("*.json")), [])

    def test_ownerless_winner_republishes_after_owned_end_expiry_cleanup(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        job_id = self.state_store.enqueue_job(
            "deep_statement", "snapshot-owner:adoption-race", {}
        )
        self.state_store.lease_next_job(["deep_statement"], "worker-a", 3600)
        ownerless_transaction_started = threading.Event()
        owned_published = threading.Event()
        owned_errors: list[BaseException] = []
        ownerless_errors: list[BaseException] = []
        ownerless_results: list[tuple[object, bool]] = []
        real_transaction = self.state_store._transaction
        real_write = self.snapshot_store.write
        snapshot_clock_calls = 0
        state_clock_calls = 0

        @contextmanager
        def observed_transaction(*args, **kwargs):
            if threading.current_thread().name == "ownerless-winner":
                ownerless_transaction_started.set()
            with real_transaction(*args, **kwargs) as connection:
                yield connection

        def observed_write(value):
            result = real_write(value)
            if threading.current_thread().name == "owned-loser":
                owned_published.set()
            return result

        def snapshot_clock():
            nonlocal snapshot_clock_calls
            if threading.current_thread().name != "owned-loser":
                return datetime.now(timezone.utc).isoformat()
            snapshot_clock_calls += 1
            if snapshot_clock_calls == 2:
                self.assertTrue(ownerless_transaction_started.wait(timeout=5))
                return "2099-01-01T00:00:00+00:00"
            return datetime.now(timezone.utc).isoformat()

        def state_clock():
            nonlocal state_clock_calls
            if threading.current_thread().name != "owned-loser":
                return datetime.now(timezone.utc).isoformat()
            state_clock_calls += 1
            if state_clock_calls == 3:
                self.assertTrue(ownerless_transaction_started.wait(timeout=5))
                return "2099-01-01T00:00:00+00:00"
            return datetime.now(timezone.utc).isoformat()

        def owned_loser():
            try:
                self.repository.persist(
                    batch, job_id=job_id, worker_id="worker-a"
                )
            except BaseException as error:
                owned_errors.append(error)

        def ownerless_winner():
            try:
                ownerless_results.append(self.repository.persist(batch))
            except BaseException as error:
                ownerless_errors.append(error)

        with (
            patch.object(self.state_store, "_transaction", new=observed_transaction),
            patch.object(self.snapshot_store, "write", side_effect=observed_write),
            patch(
                "ashare_pipeline.snapshot_repository._utc_now",
                side_effect=snapshot_clock,
                create=True,
            ),
            patch("ashare_pipeline.state_store._utc_now", side_effect=state_clock),
        ):
            owned = threading.Thread(target=owned_loser, name="owned-loser")
            owned.start()
            self.assertTrue(owned_published.wait(timeout=5))
            ownerless = threading.Thread(
                target=ownerless_winner, name="ownerless-winner"
            )
            ownerless.start()
            owned.join(timeout=10)
            ownerless.join(timeout=10)

        self.assertFalse(owned.is_alive())
        self.assertFalse(ownerless.is_alive())
        self.assertEqual(len(owned_errors), 1)
        self.assertIsInstance(owned_errors[0], ValueError)
        self.assertEqual(ownerless_errors, [])
        self.assertEqual(len(ownerless_results), 1)
        winner, created = ownerless_results[0]
        self.assertTrue(created)
        self.assertEqual(self.repository.read_verified(winner).batch, batch)
        with closing(sqlite3.connect(self.state_store.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0],
                1,
            )

    def test_failed_begin_cannot_delete_uncommitted_ownerless_winner_file(self):
        batch = statement_batch("SH600001", 100.0, "2026-08-29T00:00:00+00:00")
        a_ready_for_begin = threading.Event()
        allow_a_begin = threading.Event()
        b_adopted = threading.Event()
        b_row_inserted = threading.Event()
        allow_b_commit = threading.Event()
        a_errors: list[BaseException] = []
        b_errors: list[BaseException] = []
        b_results: list[tuple[object, bool]] = []
        real_transaction = self.state_store._transaction
        real_connect = self.state_store._connect
        real_record = self.state_store.record_snapshot
        real_write = self.snapshot_store.write
        a_created = False
        b_write_calls = 0

        @contextmanager
        def coordinated_transaction(*args, **kwargs):
            if threading.current_thread().name == "begin-loser-a":
                a_ready_for_begin.set()
                if not allow_a_begin.wait(timeout=5):
                    raise RuntimeError("test did not release caller A BEGIN")
            with real_transaction(*args, **kwargs) as connection:
                yield connection

        def thread_connection():
            connection = real_connect()
            if threading.current_thread().name == "begin-loser-a":
                connection.execute("PRAGMA busy_timeout = 0")
            return connection

        def observed_write(value):
            nonlocal a_created, b_write_calls
            target, digest, created = real_write(value)
            if threading.current_thread().name == "begin-loser-a":
                a_created = created
            elif threading.current_thread().name == "winner-b":
                b_write_calls += 1
                if b_write_calls == 1:
                    self.assertFalse(created)
                    b_adopted.set()
            return target, digest, created

        def blocked_record(*args, **kwargs):
            result = real_record(*args, **kwargs)
            if threading.current_thread().name == "winner-b":
                b_row_inserted.set()
                if not allow_b_commit.wait(timeout=5):
                    raise RuntimeError("test did not release caller B commit")
            return result

        def caller_a():
            try:
                self.repository.persist(batch)
            except BaseException as error:
                a_errors.append(error)

        def caller_b():
            try:
                b_results.append(self.repository.persist(batch))
            except BaseException as error:
                b_errors.append(error)

        with (
            patch.object(
                self.state_store, "_transaction", new=coordinated_transaction
            ),
            patch.object(self.state_store, "_connect", side_effect=thread_connection),
            patch.object(
                self.state_store, "record_snapshot", side_effect=blocked_record
            ),
            patch.object(self.snapshot_store, "write", side_effect=observed_write),
        ):
            a = threading.Thread(target=caller_a, name="begin-loser-a")
            a.start()
            self.assertTrue(a_ready_for_begin.wait(timeout=5))
            self.assertTrue(a_created)
            b = threading.Thread(target=caller_b, name="winner-b")
            b.start()
            self.assertTrue(b_adopted.wait(timeout=5))
            self.assertTrue(b_row_inserted.wait(timeout=5), repr(b_errors))
            allow_a_begin.set()
            a.join(timeout=10)
            self.assertFalse(a.is_alive())
            allow_b_commit.set()
            b.join(timeout=10)

        self.assertFalse(b.is_alive())
        self.assertEqual(len(a_errors), 1)
        self.assertIsInstance(a_errors[0], sqlite3.OperationalError)
        self.assertEqual(b_errors, [])
        self.assertEqual(len(b_results), 1)
        winner, created = b_results[0]
        self.assertTrue(created)
        self.assertEqual(self.repository.read_verified(winner).batch, batch)
        with closing(sqlite3.connect(self.state_store.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0],
                1,
            )

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
