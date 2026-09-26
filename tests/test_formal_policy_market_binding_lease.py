"""Operation-scoped current-binding lease regressions for market tickets."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import FunctionType
import sqlite3
import sys
import unittest

from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal
from ashare_pipeline import formal_policy_market as market_module
from tests.formal_range_fixtures import RangeStoreFixture
from tests.test_formal_policy_market import FREEZE, quiet_row


def _trading_days(count: int) -> tuple[str, ...]:
    end = date(2026, 8, 31)
    return tuple((end - timedelta(days=count - 1 - offset)).isoformat()
                 for offset in range(count))


def _closure_function(root: FunctionType, name: str) -> FunctionType:
    """Locate a captured production function without adding a test hook."""
    pending = [root]
    seen = set()
    while pending:
        function = pending.pop()
        if id(function) in seen:
            continue
        seen.add(id(function))
        if function.__code__.co_name == name:
            return function
        for cell in function.__closure__ or ():
            try:
                captured = cell.cell_contents
            except ValueError:
                continue
            if type(captured) is FunctionType:
                pending.append(captured)
    raise AssertionError(f"production closure {name!r} is absent")


class MarketBindingLeaseTests(unittest.TestCase):
    def _fixture(self, **kwargs):
        fixture = RangeStoreFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def _ticket_capture_count(self, fixture, days):
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = FormalBatchReadJournal.open(repository,
            registry_manifest_hash=fixture.graph.manifest.manifest_hash,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        capture = _closure_function(market_module._read_binding,
                                    "_capture_graph_snapshot")
        calls = 0
        tool_id = next(identifier for identifier in range(6)
                       if sys.monitoring.get_tool(identifier) is None)
        sys.monitoring.use_tool_id(tool_id, "market-binding-lease-test")

        def monitor(code, instruction_offset):
            nonlocal calls
            self.assertIs(code, capture.__code__)
            calls += 1

        sys.monitoring.register_callback(tool_id, sys.monitoring.events.PY_START, monitor)
        sys.monitoring.set_local_events(tool_id, capture.__code__,
                                        sys.monitoring.events.PY_START)
        try:
            ticket = repository.select_current_batch_ticket(
                journal, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            sys.monitoring.set_local_events(tool_id, capture.__code__, 0)
            sys.monitoring.free_tool_id(tool_id)
        self.assertIsNotNone(ticket.selected().window)
        journal.close()
        return calls

    def _journal(self, fixture, repository):
        return FormalBatchReadJournal.open(repository,
            registry_manifest_hash=fixture.graph.manifest.manifest_hash,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))

    def test_owner_ticket_capture_fallback_is_two_and_does_not_scale_with_more_requests(self):
        short_days = _trading_days(20)
        short_count = self._ticket_capture_count(self._fixture(), short_days)

        def split_requests(documents):
            for config in documents["source"]["range_configs"]:
                config["max_calendar_days_per_request"] = 30

        long_days = _trading_days(40)
        long_count = self._ticket_capture_count(
            self._fixture(mutate=split_requests), long_days)

        self.assertEqual((short_count, long_count), (2, 2))

    def test_owner_lease_detects_in_place_source_bytes_before_next_read_and_consumes_scope(self):
        fixture = self._fixture()
        days = _trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = self._journal(fixture, repository)
        source = fixture.bundle.blob("source")
        original = source.canonical_json
        reader_code = market_module._read_binding.__code__
        issue_code = __import__(
            "ashare_pipeline.formal_batch_read_journal", fromlist=["_issue_current_ticket"]
        )._issue_current_ticket.__code__
        changed = []
        market_issues = []
        connection = sqlite3.connect(Path(fixture.store.db_path))
        try:
            before_version = connection.execute("PRAGMA data_version").fetchone()[0]

            def inject(frame, event, arg):
                if event == "return" and frame.f_code is reader_code and not changed:
                    object.__setattr__(source, "canonical_json", original + b" ")
                    changed.append(True)
                elif (event == "call" and frame.f_code is issue_code
                      and frame.f_locals.get("kind") == "market"):
                    market_issues.append(True)

            sys.setprofile(inject)
            try:
                with self.assertRaises(ValueError):
                    repository.select_current_batch_ticket(
                        journal, "SH600000", FREEZE, binding=fixture.binding)
            finally:
                sys.setprofile(None)
                object.__setattr__(source, "canonical_json", original)
            after_version = connection.execute("PRAGMA data_version").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(changed, [True])
        self.assertEqual(market_issues, [])
        self.assertEqual(after_version, before_version)
        with self.assertRaisesRegex(ValueError, "closed"):
            repository.select_current_batch_ticket(
                journal, "SH600000", FREEZE, binding=fixture.binding)

        fresh = self._journal(fixture, repository)
        ticket = repository.select_current_batch_ticket(
            fresh, "SH600000", FREEZE, binding=fixture.binding)
        self.assertIsNotNone(ticket.selected().window)
        fresh.close()

    def test_next_journal_phase_performs_a_new_entry_and_exit_full_capture(self):
        fixture = self._fixture()
        days = _trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = self._journal(fixture, repository)
        capture = _closure_function(market_module._read_binding,
                                    "_capture_graph_snapshot")
        counts = [0, 0]
        phase = 0
        tracking_owner_operation = True
        tool_id = next(identifier for identifier in range(6)
                       if sys.monitoring.get_tool(identifier) is None)
        sys.monitoring.use_tool_id(tool_id, "market-binding-phase-test")

        def monitor(code, instruction_offset):
            self.assertIs(code, capture.__code__)
            if tracking_owner_operation:
                counts[phase] += 1

        sys.monitoring.register_callback(tool_id, sys.monitoring.events.PY_START, monitor)
        sys.monitoring.set_local_events(tool_id, capture.__code__,
                                        sys.monitoring.events.PY_START)
        try:
            repository.select_current_batch_ticket(
                journal, "SH600000", FREEZE, binding=fixture.binding)
            tracking_owner_operation = False
            journal.checkpoint()
            journal.next_phase()
            phase = 1
            tracking_owner_operation = True
            repository.select_current_batch_ticket(
                journal, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            sys.monitoring.set_local_events(tool_id, capture.__code__, 0)
            sys.monitoring.free_tool_id(tool_id)
        journal.close()
        self.assertEqual(counts, [2, 2])

    def test_owner_lease_entry_failure_consumes_scope_before_any_ticket(self):
        fixture = self._fixture()
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = self._journal(fixture, repository)
        source = fixture.bundle.blob("source")
        original = source.canonical_json
        try:
            object.__setattr__(source, "canonical_json", original + b" ")
            with self.assertRaises(ValueError):
                repository.select_current_batch_ticket(
                    journal, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            object.__setattr__(source, "canonical_json", original)
        with self.assertRaisesRegex(ValueError, "closed"):
            repository.select_current_batch_ticket(
                journal, "SH600000", FREEZE, binding=fixture.binding)


if __name__ == "__main__":
    unittest.main()
