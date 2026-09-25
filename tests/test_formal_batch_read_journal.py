"""Build-local current-read journal boundary."""

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
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

    def test_checker_is_called_once_per_phase_for_same_evidence(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        self.put()
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SZ000001",),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        self.repo.select_current_batch_ticket(journal, "security_state", "fixture-state",
            ("SZ000001",), FREEZE, root)
        code = type(self.repo)._batch_recheck_ticket.__code__
        calls = []
        def profile(frame, event, arg):
            if event == "call" and frame.f_code is code:
                calls.append(1)
        sys.setprofile(profile)
        try:
            journal.checkpoint()
            journal.checkpoint()
            self.assertEqual(len(calls), 1)
            journal.next_phase()
            journal.checkpoint()
            self.assertEqual(len(calls), 2)
        finally:
            sys.setprofile(None)

    def test_preopen_owner_method_replacement_is_rejected(self):
        from ashare_pipeline import formal_batch_read_journal as journal_module
        FormalBatchReadJournal = journal_module.FormalBatchReadJournal

        root = self.manifest.manifest_hash
        arguments = dict(registry_manifest_hash=root, as_of_utc=FREEZE,
            population=("SZ000001",),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        for method in ("get_verified_many", "select_current_batch_ticket", "_batch_recheck_ticket"):
            with self.subTest(method=method):
                with patch.object(type(self.repo), method, lambda *_a, **_k: None):
                    with self.assertRaises(ValueError):
                        FormalBatchReadJournal.open(self.repo, **arguments)
        with patch.object(self.api, "formal_version_sort_key", lambda *_: ()):
            with self.assertRaises(ValueError):
                FormalBatchReadJournal.open(self.repo, **arguments)
        with patch.object(journal_module, "_issue_current_ticket", lambda *_a, **_k: None):
            with self.assertRaises(ValueError):
                FormalBatchReadJournal.open(self.repo, **arguments)

    def test_two_member_scope_issues_two_current_tickets(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        self.put()
        self.put(request=self.request(security_id="SZ000002"))
        root = self.manifest.manifest_hash
        members = ("SZ000001", "SZ000002")
        required = tuple(("security_state", "fixture-state", item) for item in members)
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=members, required_keys=required)
        for member in members:
            self.repo.select_current_batch_ticket(journal, "security_state", "fixture-state",
                (member,), FREEZE, root)
        journal.checkpoint()
        journal.next_phase()
        journal.finalize()

    def test_population_member_can_issue_optional_ticket(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        self.put()
        self.put(request=self.request(security_id="SZ000002"))
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SZ000001", "SZ000002"),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        self.repo.select_current_batch_ticket(journal, "security_state", "fixture-state",
            ("SZ000002",), FREEZE, root)
        self.repo.select_current_batch_ticket(journal, "security_state", "fixture-state",
            ("SZ000001",), FREEZE, root)
        journal.finalize()

    def test_ticket_exposes_the_exact_selected_result(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        fact, _, _ = self.put()
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SZ000001",),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        ticket = self.repo.select_current_batch_ticket(journal, "security_state",
            "fixture-state", ("SZ000001",), FREEZE, root)
        self.assertEqual(ticket.selected()["SZ000001"].id, fact.id)
        journal.finalize()
        with self.assertRaises(ValueError):
            ticket.selected()

    def test_candidate_added_just_after_selection_cannot_be_issued_as_old_result(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        self.put()
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SZ000001",),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        selected_code = type(self.repo)._select_many_with_token.__code__
        def inject(frame, event, arg):
            if event == "return" and frame.f_code is selected_code:
                sys.setprofile(None)
                self.put(request=self.request(upstream_generation="late-correction"),
                         published="2026-08-25T07:00:00+00:00")
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                self.repo.select_current_batch_ticket(journal, "security_state",
                    "fixture-state", ("SZ000001",), FREEZE, root)
        finally:
            sys.setprofile(None)

    def test_selected_winner_conflict_rejects_finalizing_checkpoint(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        self.put()
        root = self.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(self.repo, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SZ000001",),
            required_keys=(("security_state", "fixture-state", "SZ000001"),))
        self.repo.select_current_batch_ticket(journal, "security_state", "fixture-state",
            ("SZ000001",), FREEZE, root)
        journal.checkpoint()
        self.put(request=self.request(upstream_generation="same-leading-conflict"))
        with self.assertRaises(ValueError):
            journal.finalize()

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
            _issue_current_ticket(journal, self.repo, "context", ("fake",), b"fake", (), (), None)
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

    def test_preopen_feature_ticket_method_replacement_is_rejected(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        provider = feature_tests.SnapshotProvider(self.snapshot())
        repo = self.repository(provider)
        key = self.registry.slots_for_template("general_nonfinancial")[0].slot_id
        arguments = dict(registry_manifest_hash=self.manifest.manifest_hash,
            as_of_utc="2026-08-31T07:00:00+00:00", population=("SZ000001",),
            required_keys=(("SZ000001", "general_nonfinancial", key),))
        for method in ("select_current_metric_batch_ticket", "_batch_recheck_ticket"):
            with self.subTest(method=method):
                with patch.object(type(repo), method, lambda *_a, **_k: None):
                    with self.assertRaises(ValueError):
                        FormalBatchReadJournal.open(repo, **arguments)

    def test_same_input_replaced_bundle_after_selection_never_becomes_ticket_baseline(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        provider = feature_tests.SnapshotProvider(self.snapshot())
        repo = self.repository(provider)
        key = self.registry.slots_for_template("general_nonfinancial")[0].slot_id
        journal = FormalBatchReadJournal.open(repo,
            registry_manifest_hash=self.manifest.manifest_hash,
            as_of_utc="2026-08-31T07:00:00+00:00", population=("SZ000001",),
            required_keys=(("SZ000001", "general_nonfinancial", key),))
        changed_wire = self.bundle.to_dict()
        changed_wire["values"][0]["value"] = 900.0
        changed = feature_tests.FormalFeatureBundle.from_dict(changed_wire)
        self.assertEqual(changed.input_hash, self.bundle.input_hash)
        self.assertNotEqual(changed.bundle_hash(), self.bundle.bundle_hash())
        selected_code = type(repo).select_current_verified_metric_feature_state.__code__
        def inject(frame, event, arg):
            if event == "return" and frame.f_code is selected_code:
                sys.setprofile(None)
                self.persist_unchecked(changed)
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                repo.select_current_metric_batch_ticket(journal, "SZ000001",
                    "2026-08-31T07:00:00+00:00", template_id="general_nonfinancial",
                    registry_manifest_hash=self.manifest.manifest_hash,
                    required_feature_keys=(key,))
        finally:
            sys.setprofile(None)

    def test_same_bundle_with_changed_receipt_metadata_cannot_become_ticket_baseline(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        repo = self.repository(feature_tests.SnapshotProvider(self.snapshot()))
        key = self.registry.slots_for_template("general_nonfinancial")[0].slot_id
        journal = FormalBatchReadJournal.open(repo,
            registry_manifest_hash=self.manifest.manifest_hash,
            as_of_utc="2026-08-31T07:00:00+00:00", population=("SZ000001",),
            required_keys=(("SZ000001", "general_nonfinancial", key),))
        before = repo._metadata(self.bundle.input_hash)
        selected_code = type(repo).select_current_verified_metric_feature_state.__code__
        def inject(frame, event, arg):
            if event == "return" and frame.f_code is selected_code:
                sys.setprofile(None)
                self.persist_unchecked(self.bundle)
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                repo.select_current_metric_batch_ticket(journal, "SZ000001",
                    "2026-08-31T07:00:00+00:00", template_id="general_nonfinancial",
                    registry_manifest_hash=self.manifest.manifest_hash,
                    required_feature_keys=(key,))
        finally:
            sys.setprofile(None)
        self.assertNotEqual(repo._metadata(self.bundle.input_hash), before)

    def test_absence_token_rejects_receipt_appearing_after_selection(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        self.sql("DELETE FROM formal_feature_value")
        self.sql("DELETE FROM formal_feature_set")
        repo = self.repository(feature_tests.SnapshotProvider(self.snapshot()))
        key = self.registry.slots_for_template("general_nonfinancial")[0].slot_id
        journal = FormalBatchReadJournal.open(repo,
            registry_manifest_hash=self.manifest.manifest_hash,
            as_of_utc="2026-08-31T07:00:00+00:00", population=("SZ000001",),
            required_keys=(("SZ000001", "general_nonfinancial", key),))
        selected_code = type(repo).select_current_verified_metric_feature_state.__code__
        def inject(frame, event, arg):
            if event == "return" and frame.f_code is selected_code:
                sys.setprofile(None)
                self.persist_unchecked(self.bundle)
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                repo.select_current_metric_batch_ticket(journal, "SZ000001",
                    "2026-08-31T07:00:00+00:00", template_id="general_nonfinancial",
                    registry_manifest_hash=self.manifest.manifest_hash,
                    required_feature_keys=(key,))
        finally:
            sys.setprofile(None)


class RangeJournalTests(unittest.TestCase):
    def test_preopen_range_selector_and_checker_replacement_is_rejected(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        fixture = RangeStoreFixture()
        self.addCleanup(fixture.close)
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        fingerprint = fixture.source.first_calendar_request(FREEZE).request_fingerprint
        arguments = dict(registry_manifest_hash=first.request["registry_manifest_hash"],
            as_of_utc=FREEZE, population=(fingerprint,), required_keys=((fingerprint,),))
        for method in ("select_current", "select_current_batch_ticket", "_batch_recheck_ticket"):
            with self.subTest(method=method):
                with patch.object(type(fixture.range_store), method, lambda *_a, **_k: None):
                    with self.assertRaises(ValueError):
                        FormalBatchReadJournal.open(fixture.range_store, **arguments)

    def test_conflicting_candidate_inserted_after_selection_cannot_enter_new_baseline(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        fixture = RangeStoreFixture()
        self.addCleanup(fixture.close)
        first = fixture.produce_calendar(days={"2026-08-31": True}, generation="g1")[0]
        fingerprint = fixture.source.first_calendar_request(FREEZE).request_fingerprint
        journal = FormalBatchReadJournal.open(fixture.range_store,
            registry_manifest_hash=first.request["registry_manifest_hash"],
            as_of_utc=FREEZE, population=(fingerprint,), required_keys=((fingerprint,),))
        selected_code = type(fixture.range_store)._select_current_with_token.__code__
        def inject(frame, event, arg):
            if event == "return" and frame.f_code is selected_code:
                sys.setprofile(None)
                fixture.produce_calendar(days={"2026-08-31": False}, generation="g2")
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                fixture.range_store.select_current_batch_ticket(journal, fingerprint)
        finally:
            sys.setprofile(None)

    def test_two_market_requests_share_one_frozen_range_scope(self):
        from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal

        fixture = RangeStoreFixture()
        self.addCleanup(fixture.close)
        day = "2026-08-31"
        row = {"exchange_allows_trading": True, "volume": "0", "turnover": "0",
               "close": {"state": "unavailable", "reason": "source_reports_no_trade"}}
        first = fixture.put_window("SH600000", trading_days=(day,), rows={day: row})
        second = fixture.put_window("SH600001", trading_days=(day,), rows={day: row})
        self.assertTrue(first and second)
        fingerprints = tuple(sorted((first[0].task["request_fingerprint"],
                                     second[0].task["request_fingerprint"])))
        journal = FormalBatchReadJournal.open(fixture.range_store,
            registry_manifest_hash=first[0].request["registry_manifest_hash"],
            as_of_utc=FREEZE, population=fingerprints,
            required_keys=tuple((item,) for item in fingerprints))
        for fingerprint in fingerprints:
            fixture.range_store.select_current_batch_ticket(journal, fingerprint)
        journal.checkpoint()
        journal.next_phase()
        journal.finalize()

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
