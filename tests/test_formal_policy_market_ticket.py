"""Market owner tickets tie calendar and range requests to one selection."""

import sys
import unittest
from pathlib import Path

from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal
from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
from tests.formal_range_fixtures import RangeStoreFixture
from tests.test_formal_policy_market import trading_days


FREEZE = "2026-08-31T07:00:00+00:00"


class MarketTicketTests(unittest.TestCase):
    def setUp(self):
        self.fixture = RangeStoreFixture()
        self.addCleanup(self.fixture.close)

    def test_absent_calendar_is_bound_without_reselection_at_checkpoint(self):
        fixture = self.fixture
        repository = FormalPolicyMarketRepository(fixture.range_store)
        root = fixture.graph.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(repository, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        ticket = repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
            binding=fixture.binding)
        self.assertIsNone(ticket.selected().window)
        banned = {type(repository).select.__code__, type(repository).select_calendar.__code__,
                  type(fixture.range_store)._select_current_with_token.__code__,
                  type(fixture.parser).parse.__code__,
                  type(fixture.market_parser).parse.__code__}
        calls = []
        def profile(frame, event, arg):
            if event == "call" and frame.f_code in banned:
                calls.append(frame.f_code.co_name)
        sys.setprofile(profile)
        try:
            journal.checkpoint()
        finally:
            sys.setprofile(None)
        self.assertEqual(calls, [])
        fixture.produce_calendar(days={"2026-08-31": True})
        journal.next_phase()
        with self.assertRaises(ValueError):
            journal.checkpoint()

    def test_present_calendar_and_absent_market_range_are_ticketed(self):
        fixture = self.fixture
        request = fixture.source.first_calendar_request(FREEZE)
        from tests.test_formal_policy_market import MarketRepositoryTests
        helper = MarketRepositoryTests("runTest")
        wire = helper.calendar_wire(fixture, request, opened=trading_days())
        helper.persist(fixture, request, wire)
        repository = FormalPolicyMarketRepository(fixture.range_store)
        root = fixture.graph.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(repository, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        ticket = repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
            binding=fixture.binding)
        self.assertIsNotNone(ticket.selected().window)
        self.assertIn("market_coverage_missing", ticket.selected().pending)
        banned = {type(repository).select.__code__, type(repository).select_calendar.__code__,
                  type(fixture.range_store)._select_current_with_token.__code__,
                  type(fixture.parser).parse.__code__,
                  type(fixture.market_parser).parse.__code__}
        calls = []
        def profile(frame, event, arg):
            if event == "call" and frame.f_code in banned:
                calls.append(frame.f_code.co_name)
        sys.setprofile(profile)
        try:
            journal.checkpoint()
        finally:
            sys.setprofile(None)
        self.assertEqual(calls, [])
        journal.finalize()

    def test_present_market_raw_change_revokes_ticket_without_version_change(self):
        fixture = self.fixture
        request = fixture.source.first_calendar_request(FREEZE)
        from tests.test_formal_policy_market import MarketRepositoryTests, quiet_row
        helper = MarketRepositoryTests("runTest")
        days = trading_days()
        helper.persist(fixture, request, helper.calendar_wire(fixture, request, opened=days))
        observations = fixture.put_window("SH600000", trading_days=days,
            rows={day: quiet_row() for day in days})
        repository = FormalPolicyMarketRepository(fixture.range_store)
        root = fixture.graph.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(repository, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SH600000",), required_keys=(("SH600000",),))
        ticket = repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
            binding=fixture.binding)
        self.assertIsNotNone(ticket.selected().window)
        journal.checkpoint()
        raw = Path(observations[0].snapshot["content_path"])
        raw.write_bytes(raw.read_bytes() + b" ")
        journal.next_phase()
        with self.assertRaises(ValueError):
            journal.checkpoint()


if __name__ == "__main__":
    unittest.main()
