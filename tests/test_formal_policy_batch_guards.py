"""Adversarial changes throughout the genuine complete policy read interval."""

import importlib
import sqlite3
import sys
import unittest
from pathlib import Path

from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture


class PolicyBatchGuardTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
                             "W3 atomic policy publication is missing")
        self.api = importlib.import_module("ashare_pipeline.formal_policy_repository")
        self.fixture = PolicyRuntimeFixture(range_enabled=True)
        self.addCleanup(self.fixture.close)

    def run_hook(self, hook):
        previous = sys.getprofile()
        try:
            sys.setprofile(hook)
            return self.fixture.build_policy_batch()
        finally:
            sys.setprofile(previous)

    def test_after_first_security_read_second_security_provider_changes(self):
        self.fixture.put_industry("BJ430001")
        self.fixture.put_industry("SH600000")
        touched = []
        def hook(frame, event, result):
            if (not touched and event == "return" and frame.f_code.co_name == "select"
                    and frame.f_code.co_filename.endswith("formal_policy_financial.py")
                    and frame.f_locals.get("security_id") == "BJ430001"):
                touched.append(True)
                self.fixture.set_generation("SH600000", "changed-mid-batch")
        with self.assertRaises(ValueError):
            self.run_hook(hook)
        self.assertEqual(touched, [True])

    def test_initially_missing_industry_then_present_rejects(self):
        touched = []
        def hook(frame, event, result):
            if not touched and event == "return" and frame.f_code.co_name == "prepare":
                touched.append(True)
                self.fixture.put_industry("SH600000")
        with self.assertRaises(ValueError):
            self.run_hook(hook)
        self.assertEqual(touched, [True])

    def test_database_write_during_evaluation_rejects(self):
        touched = []
        def hook(frame, event, result):
            if not touched and event == "return" and frame.f_code.co_name == "prepare":
                touched.append(True)
                self.fixture.sql("UPDATE formal_collection_task SET updated_at='2026-09-08T00:00:00+00:00'")
        with self.assertRaises(ValueError):
            self.run_hook(hook)
        self.assertEqual(touched, [True])

    def test_equal_leading_state_ambiguity_rejects(self):
        from tests.test_formal_policy_state import SECURITY
        fixture = self.fixture
        fixture.put_industry("SH600000")
        fixture.put_policy_context("SH600000", "security_state", SECURITY)
        fixture._policy_context_generations[("SH600000", "security_state")]["tie"] = 0
        fixture.put_policy_context("SH600000", "security_state", SECURITY, generation="tie")
        with self.assertRaises(ValueError):
            fixture.build_policy_batch()

    def test_source_raw_bytes_change_without_database_write_rejects(self):
        _, ref = self.fixture.put_industry("SH600000")
        touched = []
        def hook(frame, event, result):
            if not touched and event == "return" and frame.f_code.co_name == "prepare":
                touched.append(True)
                path = Path(ref.content_path)
                path.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.run_hook(hook)
        self.assertEqual(touched, [True])

    def test_signed_source_configuration_replacement_revokes_prepared_children(self):
        blob = self.fixture.bundle.blob("source")
        original = blob.canonical_json
        captured, touched = [], []
        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_policy_repository.py")):
                captured.append(result)
            if not touched and event == "return" and frame.f_code.co_name == "prepare":
                touched.append(True)
                object.__setattr__(blob, "canonical_json", b"{}")
        try:
            with self.assertRaises(ValueError):
                self.run_hook(hook)
        finally:
            object.__setattr__(blob, "canonical_json", original)
        self.assertEqual(touched, [True])
        self.assertGreaterEqual(len(captured), 5)
        for proof in captured:
            with self.assertRaises(ValueError):
                proof.require_official()

    def test_prepare_has_no_writer_reservation_and_children_are_unpublished(self):
        captured = []
        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_policy_repository.py")):
                captured.append(result)
                for method in ("require_verified", "require_official"):
                    with self.assertRaises(ValueError):
                        getattr(result, method)()
                connection = sqlite3.connect(self.fixture.db_path, timeout=0, isolation_level=None)
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.rollback()
                finally:
                    connection.close()
        batch = self.run_hook(hook)
        self.assertGreaterEqual(len(captured), 5)
        self.assertIn(batch, captured)
        for proof in captured:
            proof.require_official()

    def test_captured_decisions_and_results_remain_revoked_after_failed_prepare_interval(self):
        self.fixture.put_industry("SH600000")
        captured, touched = [], []
        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_policy_repository.py")):
                captured.append(result)
                with self.assertRaises(ValueError):
                    result.require_official()
            if not touched and event == "return" and frame.f_code.co_name == "prepare":
                touched.append(True)
                self.fixture.set_generation("SH600000", "invalidate-prepared-decisions")
        with self.assertRaises(ValueError):
            self.run_hook(hook)
        self.assertTrue(any(type(proof) is self.api.PolicyDecision for proof in captured))
        self.assertTrue(any(type(proof) is self.api.PolicyResult for proof in captured))
        for proof in captured:
            for method in ("require_official", "require_verified"):
                with self.assertRaises(ValueError):
                    getattr(proof, method)()

    def test_final_reentrant_publication_or_cleanup_failure_revokes_every_child(self):
        for failure in ("provider", "rollback", "close"):
            captured, fired = [], []
            def hook(frame, event, result):
                if (event == "return" and frame.f_code.co_name == "mint"
                        and frame.f_code.co_filename.endswith("formal_policy_repository.py")):
                    captured.append(result)
                if (not fired and event == "return" and frame.f_code.co_name == "finalize"
                        and frame.f_code.co_filename.endswith("formal_policy_repository.py")):
                    fired.append(True)
                    guard_frame = frame.f_back
                    if failure == "provider":
                        with self.assertRaises(ValueError):
                            self.fixture.set_generation("SH600000", "reentrant-swallowed")
                    elif failure == "rollback":
                        guard_frame.f_locals["observer"].close()
                    else:
                        # A real close of the observer after finalize forces the
                        # context-manager's final rollback/close cleanup to fail.
                        pass
                if (failure == "close" and fired == [True] and event == "return"
                        and frame.f_code.co_name == "finalize"
                        and frame.f_code.co_filename.endswith("formal_metric_batch_guard.py")):
                    fired.append(True)
                    frame.f_locals["observer"].close()
            with self.subTest(failure=failure), self.assertRaises((ValueError, sqlite3.Error)):
                self.run_hook(hook)
            self.assertTrue(fired)
            self.assertGreaterEqual(len(captured), 5)
            for proof in captured:
                for method in ("require_verified", "require_official", "to_dict", "canonical_bytes"):
                    with self.assertRaises(ValueError):
                        getattr(proof, method)()
            self.fixture.build_policy_batch().require_verified()


if __name__ == "__main__":
    unittest.main()
