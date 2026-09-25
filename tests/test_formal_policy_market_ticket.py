"""Market owner tickets tie calendar and range requests to one selection."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal
from ashare_pipeline.formal_policy_market import (
    CalendarSelection, FormalPolicyMarketRepository, MarketSelection,
)
from ashare_pipeline import formal_policy_market as market_module
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
        implementation_codes = set()
        def capture_implementation(frame, event, arg):
            if event == "call" and frame.f_code.co_filename.endswith("formal_policy_market.py"):
                if (frame.f_code.co_name == "select_calendar"
                        and "_calendar_selection_type" in frame.f_locals):
                    implementation_codes.add(frame.f_code)
                if (frame.f_code.co_name == "select"
                        and "_market_selection_type" in frame.f_locals):
                    implementation_codes.add(frame.f_code)
        sys.setprofile(capture_implementation)
        try:
            ticket = repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
                binding=fixture.binding)
        finally:
            sys.setprofile(None)
        self.assertIsNone(ticket.selected().window)
        self.assertEqual({code.co_name for code in implementation_codes},
                         {"select", "select_calendar"})
        banned = implementation_codes | {type(repository).select.__code__,
                  type(repository).select_calendar.__code__,
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

    def test_calendar_result_mutated_at_implementation_return_is_rejected(self):
        fixture = self.fixture
        repository = FormalPolicyMarketRepository(fixture.range_store)
        root = fixture.graph.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(repository, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        mutated = []
        def inject(frame, event, arg):
            if (event == "return" and frame.f_code.co_name == "select_calendar"
                    and "_calendar_selection_type" in frame.f_locals):
                sys.setprofile(None)
                object.__setattr__(arg, "pending", ("forged-calendar",))
                object.__setattr__(arg, "selection_hash", "0" * 64)
                mutated.append(arg)
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                repository.select_calendar_batch_ticket(journal, fixture.binding, FREEZE)
        finally:
            sys.setprofile(None)
        self.assertEqual(len(mutated), 1)

    def test_market_result_mutated_at_implementation_return_is_rejected(self):
        fixture = self.fixture
        repository = FormalPolicyMarketRepository(fixture.range_store)
        root = fixture.graph.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(repository, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        mutated = []
        def inject(frame, event, arg):
            if (event == "return" and frame.f_code.co_name == "select"
                    and "_market_selection_type" in frame.f_locals):
                sys.setprofile(None)
                object.__setattr__(arg, "pending", ("forged-market",))
                object.__setattr__(arg, "selection_hash", "0" * 64)
                mutated.append(arg)
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
                    binding=fixture.binding)
        finally:
            sys.setprofile(None)
        self.assertEqual(len(mutated), 1)

    def test_preopen_selection_constructor_replacement_is_rejected(self):
        fixture = self.fixture
        repository = FormalPolicyMarketRepository(fixture.range_store)
        args = dict(registry_manifest_hash=fixture.graph.manifest.manifest_hash,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        for selection_type in (CalendarSelection, MarketSelection):
            for name in ("__init__", "__new__"):
                with self.subTest(selection=selection_type.__name__, method=name):
                    had_local = name in vars(selection_type)
                    replacement = (lambda self, *a, **k: None) if name == "__init__" else \
                                  staticmethod(lambda cls, *a, **k: object.__new__(cls))
                    try:
                        with patch.object(selection_type, name, replacement):
                            with self.assertRaises(ValueError):
                                FormalBatchReadJournal.open(repository, **args)
                    finally:
                        if not had_local and name in vars(selection_type):
                            delattr(selection_type, name)

    def test_warm_selection_constructor_replacement_is_rejected(self):
        fixture = self.fixture
        repository = FormalPolicyMarketRepository(fixture.range_store)
        args = dict(registry_manifest_hash=fixture.graph.manifest.manifest_hash,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        for selection_type in (CalendarSelection, MarketSelection):
            for name in ("__init__", "__new__"):
                with self.subTest(selection=selection_type.__name__, method=name):
                    journal = FormalBatchReadJournal.open(repository, **args)
                    repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
                        binding=fixture.binding)
                    journal.checkpoint()
                    had_local = name in vars(selection_type)
                    replacement = (lambda self, *a, **k: None) if name == "__init__" else \
                                  staticmethod(lambda cls, *a, **k: object.__new__(cls))
                    try:
                        with patch.object(selection_type, name, replacement):
                            with self.assertRaises(ValueError):
                                journal.checkpoint()
                    finally:
                        if not had_local and name in vars(selection_type):
                            delattr(selection_type, name)

    def test_constructor_result_pollution_cannot_become_ticket_baseline(self):
        fixture = self.fixture
        repository = FormalPolicyMarketRepository(fixture.range_store)
        root = fixture.graph.manifest.manifest_hash
        for selection_type, kind in ((CalendarSelection, "calendar"),
                                     (MarketSelection, "market")):
            with self.subTest(kind=kind):
                journal = FormalBatchReadJournal.open(repository,
                    registry_manifest_hash=root, as_of_utc=FREEZE,
                    population=("SH600000",), required_keys=(("SH600000",),))
                constructed = []
                init_code = selection_type.__init__.__code__
                def inject(frame, event, arg):
                    if (event == "return" and frame.f_code is init_code
                            and type(frame.f_locals.get("self")) is selection_type):
                        sys.setprofile(None)
                        selected = frame.f_locals["self"]
                        object.__setattr__(selected, "pending", ("forged-at-construction",))
                        constructed.append(selected)
                sys.setprofile(inject)
                try:
                    with self.assertRaises(ValueError):
                        if kind == "calendar":
                            repository.select_calendar_batch_ticket(journal, fixture.binding, FREEZE)
                        else:
                            repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
                                binding=fixture.binding)
                finally:
                    sys.setprofile(None)
                self.assertEqual(len(constructed), 1)

    def test_unrelated_repr_change_does_not_block_ticket_scope(self):
        fixture = self.fixture
        repository = FormalPolicyMarketRepository(fixture.range_store)
        args = dict(registry_manifest_hash=fixture.graph.manifest.manifest_hash,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        with patch.object(MarketSelection, "__repr__", lambda self: "market selection"):
            journal = FormalBatchReadJournal.open(repository, **args)
            ticket = repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
                binding=fixture.binding)
            self.assertIsNone(ticket.selected().window)
            journal.finalize()

    def test_preopen_selection_field_and_type_alias_replacement_are_rejected(self):
        fixture = self.fixture
        repository = FormalPolicyMarketRepository(fixture.range_store)
        args = dict(registry_manifest_hash=fixture.graph.manifest.manifest_hash,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        with patch.object(market_module, "CalendarSelection", MarketSelection):
            with self.assertRaises(ValueError):
                FormalBatchReadJournal.open(repository, **args)
        with patch.object(CalendarSelection, "pending", property(lambda self: ("forged",))):
            with self.assertRaises(ValueError):
                FormalBatchReadJournal.open(repository, **args)
        fields = CalendarSelection.__dataclass_fields__
        original = fields["pending"]
        try:
            fields["pending"] = fields["lineage"]
            with self.assertRaises(ValueError):
                FormalBatchReadJournal.open(repository, **args)
        finally:
            fields["pending"] = original


if __name__ == "__main__":
    unittest.main()
