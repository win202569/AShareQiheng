"""Build-local current-read journal boundary."""

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from unittest.mock import patch

import tests.test_formal_context_repository as context_tests
from tests.test_formal_context_schema import FREEZE
import tests.test_formal_feature_repository as feature_tests
from tests.formal_range_fixtures import RangeStoreFixture


class ContextJournalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = context_tests.ContextIntegrationTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def __getattr__(self, name):
        fixture = self.__dict__.get("fixture")
        if fixture is None:
            raise AttributeError(name)
        return getattr(fixture, name)

    def test_current_ticket_checks_once_per_phase_and_rejects_replay(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        self.put()
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(
            self.repo, registry_manifest_hash=root, as_of_utc=FREEZE,
            population=("SZ000001",), required_keys=(("security_state", "fixture-state", "SZ000001"),),
        )
        ticket = self.repo.select_current_batch_ticket(
            journal, "security_state", "fixture-state", ("SZ000001",), FREEZE, root,
        )
        self.assertIsNotNone(ticket)
        self.assertRaises(TypeError, copy.copy, journal)
        self.assertRaises(TypeError, copy.copy, ticket)
        journal.checkpoint()
        journal.checkpoint()
        journal.next_phase()
        journal.checkpoint()
        journal.finalize()
        with self.assertRaises(ValueError):
            journal.checkpoint()

    def test_current_ticket_detects_absence_turning_present(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(
            self.repo, registry_manifest_hash=root, as_of_utc=FREEZE,
            population=("SZ000001",), required_keys=(("security_state", "fixture-state", "SZ000001"),),
        )
        self.repo.select_current_batch_ticket(
            journal, "security_state", "fixture-state", ("SZ000001",), FREEZE, root,
        )
        self.put()
        with self.assertRaises(ValueError):
            journal.checkpoint()

    def test_scope_rejects_forgery_cross_owner_thread_and_changed_baseline(self):
        from ashare_pipeline.formal_batch_read_journal import (
            CurrentReadTicket, FormalBatchReadJournal, _issue_current_ticket)

        self.put()
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SZ000001",),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        with self.assertRaises(ValueError):
            object.__new__(FormalBatchReadJournal).checkpoint()
        with self.assertRaises(TypeError):
            CurrentReadTicket()
        with self.assertRaises(ValueError):
            _issue_current_ticket(journal, self.repo, "context", ("fake",), b"fake", (), ())
        peer = self.api.FormalContextRepository(self.store, self.snapshots, self.verifier)
        with self.assertRaises(ValueError):
            peer.select_current_batch_ticket(journal, "security_state", "fixture-state",
                ("SZ000001",), FREEZE, root)
        ticket = self.repo.select_current_batch_ticket(journal, "security_state",
            "fixture-state", ("SZ000001",), FREEZE, root)
        self.assertIs(ticket, self.repo.select_current_batch_ticket(journal,
            "security_state", "fixture-state", ("SZ000001",), FREEZE, root))
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaises(ValueError):
                pool.submit(journal.checkpoint).result()
        self.put(request=self.request(upstream_generation="correction"),
                 published="2026-08-25T07:00:00+00:00")
        with self.assertRaises(ValueError):
            self.repo.select_current_batch_ticket(journal, "security_state",
                "fixture-state", ("SZ000001",), FREEZE, root)

    def test_reader_replacement_rejected_before_first_and_warm_checkpoint(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        self.put()
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SZ000001",),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        original = type(self.repo)._batch_recheck_ticket
        with patch.object(type(self.repo), "_batch_recheck_ticket", lambda *_: None):
            with self.assertRaises(ValueError):
                self.repo.select_current_batch_ticket(journal, "security_state",
                    "fixture-state", ("SZ000001",), FREEZE, root)
        self.assertIs(type(self.repo)._batch_recheck_ticket, original)
        self.repo.select_current_batch_ticket(journal, "security_state",
            "fixture-state", ("SZ000001",), FREEZE, root)
        journal.checkpoint()
        with patch.object(type(self.repo), "_batch_recheck_ticket", lambda *_: None):
            with self.assertRaises(ValueError):
                journal.checkpoint()

    def test_source_tamper_consumes_scope_and_restoration_needs_new_scope(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        _, source, _ = self.put()
        root = self.manifest.manifest_hash
        def scope():
            return FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
                as_of_utc=FREEZE, population=("SZ000001",),
                required_keys=(("security_state", "fixture-state", "SZ000001"),))
        first = scope()
        self.repo.select_current_batch_ticket(first, "security_state", "fixture-state",
            ("SZ000001",), FREEZE, root)
        path = Path(source.content_path)
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaises(ValueError):
            first.checkpoint()
        path.write_bytes(original)
        with self.assertRaises(ValueError):
            first.checkpoint()
        fresh = scope()
        self.repo.select_current_batch_ticket(fresh, "security_state", "fixture-state",
            ("SZ000001",), FREEZE, root)
        fresh.finalize()

    def test_finalize_rechecks_after_earlier_checkpoint(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        _, source, _ = self.put()
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SZ000001",),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        self.repo.select_current_batch_ticket(journal, "security_state", "fixture-state",
            ("SZ000001",), FREEZE, root)
        journal.checkpoint()
        path = Path(source.content_path)
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            journal.finalize()


class FeatureJournalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = feature_tests.FormalFeatureRepositoryTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def __getattr__(self, name):
        fixture = self.__dict__.get("fixture")
        if fixture is None:
            raise AttributeError(name)
        return getattr(fixture, name)

    def test_ticket_rereads_provider_and_persisted_bundle_without_rebuilding(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        provider = feature_tests.SnapshotProvider(self.snapshot())
        repo = self.repository(provider)
        key = self.registry.slots_for_template("general_nonfinancial")[0].slot_id
        journal = FormalBatchReadJournal.open(repo,
            registry_manifest_hash=self.manifest.manifest_hash,
            as_of_utc="2026-08-31T07:00:00+00:00", population=("SZ000001",),
            required_keys=(("SZ000001", "general_nonfinancial", key),))
        ticket = repo.select_current_metric_batch_ticket(journal, "SZ000001",
            "2026-08-31T07:00:00+00:00", template_id="general_nonfinancial",
            registry_manifest_hash=self.manifest.manifest_hash,
            required_feature_keys=(key,))
        self.assertIsNotNone(ticket)
        baseline_calls = len(provider.requests)
        journal.checkpoint()
        self.assertEqual(len(provider.requests), baseline_calls + 1)
        journal.checkpoint()
        self.assertEqual(len(provider.requests), baseline_calls + 1)
        provider.snapshot = self.snapshot(batch_id="fixture-generation-2")
        journal.next_phase()
        with self.assertRaises(ValueError):
            journal.checkpoint()


class RangeJournalTests(unittest.TestCase):
    def test_raw_change_invalidates_current_ticket_without_version_change(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        fixture = RangeStoreFixture()
        self.addCleanup(fixture.close)
        observation = fixture.produce_calendar(days={"2026-08-31": True})[0]
        fingerprint = fixture.source.first_calendar_request(FREEZE).request_fingerprint
        journal = FormalBatchReadJournal.open(fixture.range_store,
            registry_manifest_hash=observation.request["registry_manifest_hash"],
            as_of_utc=FREEZE, population=(fingerprint,), required_keys=((fingerprint,),))
        fixture.range_store.select_current_batch_ticket(journal, fingerprint)
        journal.checkpoint()
        raw_path = Path(observation.snapshot["content_path"])
        raw_path.write_bytes(raw_path.read_bytes() + b" ")
        journal.next_phase()
        with self.assertRaises(ValueError):
            journal.checkpoint()

    def test_candidate_refresh_revokes_ticket_even_with_same_document(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        fixture = RangeStoreFixture()
        self.addCleanup(fixture.close)
        first = fixture.produce_calendar(days={"2026-08-31": True}, generation="g1")[0]
        fingerprint = fixture.source.first_calendar_request(FREEZE).request_fingerprint
        journal = FormalBatchReadJournal.open(fixture.range_store,
            registry_manifest_hash=first.request["registry_manifest_hash"],
            as_of_utc=FREEZE, population=(fingerprint,), required_keys=((fingerprint,),))
        fixture.range_store.select_current_batch_ticket(journal, fingerprint)
        journal.checkpoint()
        fixture.produce_calendar(days={"2026-08-31": True}, generation="g2")
        journal.next_phase()
        with self.assertRaises(ValueError):
            journal.checkpoint()

if __name__ == "__main__":
    unittest.main()
