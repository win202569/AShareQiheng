import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ashare_pipeline.state_store import FinalizationBlocked, StateStore


UTC = timezone.utc


def utc_at(seconds: int) -> str:
    return (datetime(2026, 8, 31, tzinfo=UTC) + timedelta(seconds=seconds)).isoformat()


class StateStoreTestCase(unittest.TestCase):
    """Each test guards a durable public state-transition contract."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "state.sqlite3"
        self.store = StateStore(self.db_path)
        self.store.initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def create_score_run(self) -> str:
        return self.store.create_score_run(
            "2026-06-30", "2026-08-31T08:00:00+08:00", "rules-v1", "universe-v1", "incremental"
        )

    def test_duplicate_enqueue_returns_original_job_without_second_row(self) -> None:
        job_id = self.store.enqueue_job("fetch", "source:000001", {"request": "first"})
        repeated_id = self.store.enqueue_job("fetch", "source:000001", {"request": "changed"})

        self.assertEqual(job_id, repeated_id)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM job").fetchone()[0], 1)

    def test_leasing_claims_one_pending_job_exclusively(self) -> None:
        job_id = self.store.enqueue_job("fetch", "lease:one", {"x": 1})

        first = self.store.lease_next_job(["fetch"], "worker-a", 60, utc_at(0))
        second = self.store.lease_next_job(["fetch"], "worker-b", 60, utc_at(1))

        self.assertEqual(first["id"], job_id)
        self.assertEqual(first["status"], "running")
        self.assertEqual(first["lease_worker"], "worker-a")
        self.assertIsNone(second)

    def test_two_connections_cannot_lease_same_job(self) -> None:
        self.store.enqueue_job("fetch", "lease:race", {})
        other_connection = StateStore(self.db_path)
        other_connection.initialize()

        first = self.store.lease_next_job(["fetch"], "worker-a", 60, utc_at(0))
        second = other_connection.lease_next_job(["fetch"], "worker-b", 60, utc_at(0))

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_concurrent_workers_claim_only_one_job_after_barrier(self) -> None:
        job_id = self.store.enqueue_job("fetch", "lease:thread-race", {})
        barrier = threading.Barrier(3)
        results: list[dict | None] = []
        errors: list[BaseException] = []

        def claim(worker_id: str) -> None:
            try:
                barrier.wait(timeout=5)
                result = StateStore(self.db_path).lease_next_job(["fetch"], worker_id, 60, utc_at(0))
                results.append(result)
            except BaseException as error:
                errors.append(error)

        workers = [threading.Thread(target=claim, args=(worker_id,)) for worker_id in ("worker-a", "worker-b")]
        for worker in workers:
            worker.start()
        barrier.wait(timeout=5)
        for worker in workers:
            worker.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual([result["id"] for result in results if result is not None], [job_id])
        self.assertEqual(sum(result is None for result in results), 1)

    def test_retryable_failure_waits_until_retry_time(self) -> None:
        job_id = self.store.enqueue_job("fetch", "retry:future", {})
        self.store.lease_next_job(["fetch"], "worker", 60, utc_at(0))
        self.store.fail_job(job_id, {"reason": "temporary"}, True, utc_at(120))

        self.assertIsNone(self.store.lease_next_job(["fetch"], "worker", 60, utc_at(119)))
        self.assertEqual(
            self.store.lease_next_job(["fetch"], "worker", 60, utc_at(120))["id"], job_id
        )

    def test_terminal_failure_is_never_automatically_released(self) -> None:
        job_id = self.store.enqueue_job("fetch", "retry:terminal", {})
        self.store.lease_next_job(["fetch"], "worker", 60, utc_at(0))
        self.store.fail_job(job_id, {"reason": "bad input"}, False)

        self.assertIsNone(self.store.lease_next_job(["fetch"], "worker", 60, utc_at(10_000)))

    def test_expired_lease_is_recovered_with_audit_error(self) -> None:
        job_id = self.store.enqueue_job("fetch", "lease:expired", {})
        self.store.lease_next_job(["fetch"], "worker-a", 10, utc_at(0))

        self.assertEqual(self.store.recover_expired_leases(utc_at(11)), 1)
        with closing(sqlite3.connect(self.db_path)) as connection:
            status, error_text = connection.execute(
                "SELECT status, last_error_json FROM job WHERE id = ?", (job_id,)
            ).fetchone()
        self.assertEqual(status, "retryable_failed")
        self.assertIn("lease_expired", error_text)
        self.assertEqual(self.store.lease_next_job(["fetch"], "worker-b", 10, utc_at(11))["id"], job_id)

    def test_completed_job_remains_completed_after_reopen(self) -> None:
        job_id = self.store.enqueue_job("fetch", "persist:job", {"symbol": "000001"})
        self.store.lease_next_job(["fetch"], "worker", 10, utc_at(0))
        self.store.complete_job(job_id, {"rows": 1})

        reopened = StateStore(self.db_path)
        reopened.initialize()
        self.assertIsNone(reopened.lease_next_job(["fetch"], "new-worker", 10, utc_at(100)))

    def test_get_job_returns_public_status_result_error_and_retry_fields(self) -> None:
        job_id = self.store.enqueue_job("fetch", "read:job", {"symbol": "000001"})
        self.store.lease_next_job(["fetch"], "worker", 60, utc_at(0))
        self.store.fail_job(job_id, {"reason": "temporary"}, True, utc_at(60))

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "retryable_failed")
        self.assertEqual(job["payload"], {"symbol": "000001"})
        self.assertEqual(job["error"], {"reason": "temporary"})
        self.assertEqual(job["next_retry_at"], utc_at(60))
        self.assertIsNone(self.store.get_job("missing"))

    def test_snapshot_deduplicates_same_content_and_versions_new_hash(self) -> None:
        first_id, first_created = self.store.record_snapshot(
            "baostock", "daily", "request-a", "hash-a", "raw/a.json", 1, utc_at(0)
        )
        duplicate_id, duplicate_created = self.store.record_snapshot(
            "baostock", "daily", "request-a", "hash-a", "raw/duplicate.json", 99, utc_at(1)
        )
        second_id, second_created = self.store.record_snapshot(
            "baostock", "daily", "request-a", "hash-b", "raw/b.json", 2, utc_at(2)
        )

        self.assertEqual((duplicate_id, duplicate_created), (first_id, False))
        self.assertTrue(first_created)
        self.assertTrue(second_created)
        self.assertNotEqual(first_id, second_id)

    def test_score_item_rejects_invalid_coverage_and_does_not_default_missing_scores(self) -> None:
        score_run_id = self.create_score_run()
        with self.assertRaises(ValueError):
            self.store.upsert_score_item(score_run_id, "000001", "partial", 1.01, "input-a", None, ["missing"])

        self.store.upsert_score_item(score_run_id, "000001", "partial", 0.5, "input-a", None, ["missing"])
        with closing(sqlite3.connect(self.db_path)) as connection:
            score_json = connection.execute("SELECT scores_json FROM score_item").fetchone()[0]
        self.assertIsNone(score_json)

    def test_run_as_of_rejects_naive_time_and_persists_utc(self) -> None:
        with self.assertRaises(ValueError):
            self.store.start_run("incremental", "2026-08-31T08:00:00", {})
        with self.assertRaises(ValueError):
            self.store.create_score_run("2026-06-30", "2026-08-31T08:00:00", "r", "u", "incremental")

        run_id = self.store.start_run("incremental", "2026-08-31T08:00:00+08:00", {})
        score_run_id = self.store.create_score_run("2026-06-30", "2026-08-31T08:00:00+08:00", "r", "u", "incremental")
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored_run = connection.execute("SELECT as_of_cn FROM run WHERE id = ?", (run_id,)).fetchone()[0]
            stored_score_run = connection.execute("SELECT as_of_cn FROM score_run WHERE id = ?", (score_run_id,)).fetchone()[0]
        self.assertEqual(stored_run, "2026-08-31T00:00:00+00:00")
        self.assertEqual(stored_score_run, "2026-08-31T00:00:00+00:00")

    def test_provisional_run_cannot_directly_write_final_score_item(self) -> None:
        score_run_id = self.create_score_run()

        with self.assertRaises(ValueError):
            self.store.upsert_score_item(score_run_id, "000001", "final", 1.0, "a", {"total": 90}, [])

    def test_finalization_persists_utc_gate_and_evidence(self) -> None:
        score_run_id = self.create_score_run()
        self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "a", {"total": 90}, [])

        self.store.finalize_score_run(
            score_run_id,
            "2026-09-01T00:00:00+08:00",
            "2026-08-31T23:59:59+08:00",
            True,
            True,
            market_evidence={"daily_snapshot": "hash-market"},
            quality_evidence={"coverage": 0.96},
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored = connection.execute(
                """SELECT cutoff_utc, market_ready, quality_passed, market_evidence_json, quality_evidence_json
                FROM score_run WHERE id = ?""", (score_run_id,)
            ).fetchone()
        self.assertEqual(stored[0], "2026-08-31T15:59:59+00:00")
        self.assertEqual(stored[1:3], (1, 1))
        self.assertEqual(stored[3], '{"daily_snapshot":"hash-market"}')
        self.assertEqual(stored[4], '{"coverage":0.96}')

    def test_equal_offset_time_blocks_but_later_absolute_time_finalizes(self) -> None:
        cutoff_cn = "2026-08-31T23:59:59+08:00"
        equal_absolute_time = "2026-08-31T15:59:59+00:00"
        blocked_run = self.create_score_run()
        with self.assertRaises(FinalizationBlocked):
            self.store.finalize_score_run(blocked_run, equal_absolute_time, cutoff_cn, True, True)

        final_run = self.create_score_run()
        self.store.finalize_score_run(final_run, "2026-08-31T16:00:00+00:00", cutoff_cn, True, True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT status FROM score_run WHERE id = ?", (final_run,)).fetchone()[0], "final")

    def test_finalize_blocks_at_cutoff_including_timezone_boundary(self) -> None:
        score_run_id = self.create_score_run()

        with self.assertRaises(FinalizationBlocked):
            self.store.finalize_score_run(
                score_run_id,
                "2026-08-31T23:59:59+08:00",
                "2026-08-31T23:59:59+08:00",
                True,
                True,
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT status FROM score_run").fetchone()[0], "provisional")

    def test_finalize_requires_market_and_quality_gates(self) -> None:
        score_run_id = self.create_score_run()
        for market_ready, quality_passed in ((False, True), (True, False)):
            with self.assertRaises(FinalizationBlocked):
                self.store.finalize_score_run(
                    score_run_id, "2026-09-01T00:00:00+08:00", "2026-08-31T23:59:59+08:00", market_ready, quality_passed
                )

    def test_finalization_promotes_only_ready_items_and_is_idempotent(self) -> None:
        score_run_id = self.create_score_run()
        self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "a", {"total": 90}, [])
        self.store.upsert_score_item(score_run_id, "000002", "partial", 0.5, "b", None, ["missing report"])
        self.store.upsert_score_item(score_run_id, "000003", "blocked", 0.0, "c", None, ["quality hold"])

        arguments = (score_run_id, "2026-09-01T00:00:00+08:00", "2026-08-31T23:59:59+08:00", True, True)
        self.store.finalize_score_run(*arguments)
        self.store.finalize_score_run(*arguments)
        with closing(sqlite3.connect(self.db_path)) as connection:
            states = dict(connection.execute("SELECT security_id, state FROM score_item"))
            run_status = connection.execute("SELECT status FROM score_run").fetchone()[0]
        self.assertEqual(run_status, "final")
        self.assertEqual(states, {"000001": "final", "000002": "partial", "000003": "blocked"})

    def test_final_run_cannot_be_modified_and_new_input_creates_new_run(self) -> None:
        score_run_id = self.create_score_run()
        self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "a", {"total": 90}, [])
        self.store.finalize_score_run(
            score_run_id, "2026-09-01T00:00:00+08:00", "2026-08-31T23:59:59+08:00", True, True
        )

        with self.assertRaises(ValueError):
            self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "changed", {"total": 91}, [])
        replacement_id = self.store.create_score_run(
            "2026-06-30", "2026-08-31T08:00:00+08:00", "rules-v2", "universe-v1", "incremental"
        )
        self.assertNotEqual(score_run_id, replacement_id)

    def test_illegal_state_is_rejected(self) -> None:
        job_id = self.store.enqueue_job("fetch", "invalid:state", {})
        with self.assertRaises(ValueError):
            self.store.finish_run(job_id, "not-a-run-status")
        score_run_id = self.create_score_run()
        with self.assertRaises(ValueError):
            self.store.upsert_score_item(score_run_id, "000001", "unknown", 0.5, "a", None, [])

    def test_progress_snapshot_has_counts_recent_run_update_and_no_payloads(self) -> None:
        run_id = self.store.start_run("incremental", "2026-08-31T08:00:00+08:00", {"secret": "payload"})
        self.store.finish_run(run_id, "succeeded")
        self.store.enqueue_job("fetch", "progress:job", {"large": "payload"})
        score_run_id = self.create_score_run()
        self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "a", {"total": 90}, [])

        snapshot = self.store.progress_snapshot()
        self.assertGreaterEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["job_counts"]["pending"], 1)
        self.assertEqual(snapshot["score_item_counts"]["ready"], 1)
        self.assertEqual(snapshot["recent_run"]["id"], run_id)
        self.assertIn("updated_at", snapshot)
        self.assertNotIn("payload", repr(snapshot))

    def test_progress_updated_at_includes_finished_run_artifact_and_quality_issue(self) -> None:
        run_id = self.store.start_run("incremental", "2026-08-31T08:00:00+08:00", {})
        self.store.finish_run(run_id, "succeeded")
        marker = "2099-01-01T00:00:00+00:00"
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("UPDATE run SET finished_at = ? WHERE id = ?", (marker, run_id))
            connection.execute(
                "INSERT INTO artifact VALUES (?, ?, ?, ?, ?, ?)",
                ("artifact-1", run_id, "raw", "hash-a", "raw/a.json", marker),
            )
            connection.execute(
                "INSERT INTO quality_issue VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("issue-1", run_id, None, "warning", "coverage", "{}", marker),
            )
            connection.commit()

        self.assertEqual(self.store.progress_snapshot()["updated_at"], marker)


if __name__ == "__main__":
    unittest.main()
