"""Operation-scoped current-binding lease regressions for market tickets."""

from __future__ import annotations

from contextvars import copy_context
from datetime import date, timedelta
from pathlib import Path
from types import FunctionType
import sqlite3
import sys
import threading
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

    def test_transient_signed_source_envelope_mutation_is_rejected_and_consumes_scope(self):
        from ashare_pipeline import formal_batch_read_journal as journal_module

        fixture = self._fixture()
        days = _trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = self._journal(fixture, repository)
        source = fixture.bundle.blob("source")
        original = source.signature
        reader_code = market_module._read_binding.__code__
        issue_code = journal_module._issue_current_ticket.__code__
        transitions = []
        market_issues = []

        def inject(frame, event, arg):
            if event == "return" and frame.f_code is reader_code:
                if not transitions:
                    object.__setattr__(source, "signature", "forged")
                    transitions.append("mutated")
                elif transitions == ["mutated"]:
                    object.__setattr__(source, "signature", original)
                    transitions.append("restored")
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
            object.__setattr__(source, "signature", original)
        self.assertEqual(transitions, ["mutated", "restored"])
        self.assertEqual(market_issues, [])
        with self.assertRaisesRegex(ValueError, "closed"):
            journal.checkpoint()

        fresh = self._journal(fixture, repository)
        repository.select_current_batch_ticket(
            fresh, "SH600000", FREEZE, binding=fixture.binding)
        fresh.close()

    def test_cross_thread_close_rejection_keeps_real_token_live_for_owner_thread(self):
        from ashare_pipeline import formal_range_contract as contract

        fixture = self._fixture()
        days = _trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = self._journal(fixture, repository)
        open_lease, close_lease = contract._range_binding_read_lease_authority()
        captured = []
        failures = []

        def inject(frame, event, arg):
            if event == "return" and frame.f_code is open_lease.__code__ and not captured:
                sys.setprofile(None)
                captured.append(arg)
                worker = __import__("threading").Thread(
                    target=lambda: _cross_thread_close(close_lease, arg, failures))
                worker.start()
                worker.join()

        def _cross_thread_close(close, token, errors):
            try:
                close(token)
            except Exception as error:
                errors.append(type(error))

        sys.setprofile(inject)
        try:
            ticket = repository.select_current_batch_ticket(
                journal, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            sys.setprofile(None)
        self.assertIsNotNone(ticket.selected().window)
        self.assertEqual(failures, [ValueError])
        self.assertEqual(len(captured), 1)
        with self.assertRaises(ValueError):
            close_lease(captured[0])
        journal.close()

        fresh = self._journal(fixture, repository)
        repository.select_current_batch_ticket(
            fresh, "SH600000", FREEZE, binding=fixture.binding)
        fresh.close()

    def test_copied_context_close_rejection_keeps_real_token_live_for_owner_context(self):
        from ashare_pipeline import formal_range_contract as contract

        fixture = self._fixture()
        days = _trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = self._journal(fixture, repository)
        open_lease, close_lease = contract._range_binding_read_lease_authority()
        captured = []
        copied_failures = []

        def inject(frame, event, arg):
            if event == "return" and frame.f_code is open_lease.__code__ and not captured:
                sys.setprofile(None)
                captured.append(arg)
                try:
                    copy_context().run(close_lease, arg)
                except Exception as error:
                    copied_failures.append(type(error))

        sys.setprofile(inject)
        try:
            ticket = repository.select_current_batch_ticket(
                journal, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            sys.setprofile(None)
        self.assertIsNotNone(ticket.selected().window)
        self.assertEqual(copied_failures, [ValueError])
        self.assertEqual(len(captured), 1)
        with self.assertRaises(ValueError):
            close_lease(captured[0])
        journal.close()

        fresh = self._journal(fixture, repository)
        repository.select_current_batch_ticket(
            fresh, "SH600000", FREEZE, binding=fixture.binding)
        fresh.close()

    def test_replaced_sys_getframe_cannot_forge_owner_entry_or_issue_ticket(self):
        from ashare_pipeline import formal_batch_read_journal as journal_module

        fixture = self._fixture()
        days = _trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = self._journal(fixture, repository)
        genuine_getframe = sys._getframe
        issue_code = journal_module._issue_current_ticket.__code__
        market_issues = []

        def forged_getframe(depth=0):
            return genuine_getframe(depth + 1)

        def monitor(frame, event, arg):
            if (event == "call" and frame.f_code is issue_code
                    and frame.f_locals.get("kind") == "market"):
                market_issues.append(True)

        sys.setprofile(monitor)
        sys._getframe = forged_getframe
        try:
            with self.assertRaises(ValueError):
                repository.select_current_batch_ticket(
                    journal, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            sys._getframe = genuine_getframe
            sys.setprofile(None)
        self.assertEqual(market_issues, [])
        with self.assertRaisesRegex(ValueError, "closed"):
            journal.checkpoint()

        fresh = self._journal(fixture, repository)
        repository.select_current_batch_ticket(
            fresh, "SH600000", FREEZE, binding=fixture.binding)
        fresh.close()

    def test_replaced_thread_identity_cannot_leave_rejected_owner_scope_replayable(self):
        fixture = self._fixture()
        days = _trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        journal = self._journal(fixture, repository)
        genuine_get_ident = threading.get_ident
        threading.get_ident = lambda: -1
        try:
            with self.assertRaisesRegex(ValueError, "dependency changed"):
                repository.select_current_batch_ticket(
                    journal, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            threading.get_ident = genuine_get_ident

        with self.assertRaisesRegex(ValueError, "closed"):
            journal.checkpoint()
        with self.assertRaisesRegex(ValueError, "closed"):
            repository.select_current_batch_ticket(
                journal, "SH600000", FREEZE, binding=fixture.binding)

        fresh = self._journal(fixture, repository)
        repository.select_current_batch_ticket(
            fresh, "SH600000", FREEZE, binding=fixture.binding)
        fresh.close()

    def test_owner_entry_keys_recursion_and_calendar_child_depth_are_closed(self):
        from ashare_pipeline import formal_range_contract as contract

        fixture = self._fixture()
        days = _trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        open_lease, close_lease = contract._range_binding_read_lease_authority()

        with self.assertRaises(ValueError):
            open_lease(fixture.binding, object(), ("arbitrary",))

        calendar_scope = self._journal(fixture, repository)
        recursive = []
        open_code = open_lease.__code__

        def recurse_calendar(frame, event, arg):
            if event == "return" and frame.f_code is open_code and not recursive:
                sys.setprofile(None)
                try:
                    repository.select_calendar_batch_ticket(
                        calendar_scope, fixture.binding, FREEZE)
                except Exception as error:
                    recursive.append(type(error))

        sys.setprofile(recurse_calendar)
        try:
            with self.assertRaises(ValueError):
                repository.select_calendar_batch_ticket(
                    calendar_scope, fixture.binding, FREEZE)
        finally:
            sys.setprofile(None)
        self.assertEqual(recursive, [ValueError])
        with self.assertRaisesRegex(ValueError, "closed"):
            calendar_scope.checkpoint()

        market_scope = self._journal(fixture, repository)
        nested_close = close_lease.__code__
        second_calendar = []
        outer_tokens = []

        def repeat_calendar(frame, event, arg):
            if event == "return" and frame.f_code is open_code and not outer_tokens:
                outer_tokens.append(arg)
            if (event == "return" and frame.f_code is nested_close
                    and frame.f_locals.get("nested") is True and not second_calendar):
                sys.setprofile(None)
                try:
                    repository.select_calendar_batch_ticket(
                        market_scope, fixture.binding, FREEZE)
                except Exception as error:
                    second_calendar.append(type(error))

        sys.setprofile(repeat_calendar)
        try:
            with self.assertRaises(ValueError):
                repository.select_current_batch_ticket(
                    market_scope, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            sys.setprofile(None)
        self.assertEqual(second_calendar, [ValueError])
        self.assertEqual(len(outer_tokens), 1)
        with self.assertRaisesRegex(ValueError, "closed"):
            market_scope.checkpoint()
        with self.assertRaises(ValueError):
            close_lease(outer_tokens[0])

        fresh = self._journal(fixture, repository)
        phase_tokens = []

        def capture_phase_token(frame, event, arg):
            if event == "return" and frame.f_code is open_code and not phase_tokens:
                phase_tokens.append(arg)

        sys.setprofile(capture_phase_token)
        try:
            repository.select_current_batch_ticket(
                fresh, "SH600000", FREEZE, binding=fixture.binding)
        finally:
            sys.setprofile(None)
        fresh.checkpoint()
        fresh.next_phase()
        with self.assertRaises(ValueError):
            close_lease(phase_tokens[0])
        repository.select_current_batch_ticket(
            fresh, "SH600000", FREEZE, binding=fixture.binding)
        fresh.close()


if __name__ == "__main__":
    unittest.main()
