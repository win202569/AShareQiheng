"""Calendar coverage and independent market-window policy evidence."""

from datetime import date, timedelta
from decimal import Decimal
import copy
import unittest

from tests.formal_range_fixtures import RangeStoreFixture


FREEZE = "2026-08-31T07:00:00+00:00"


def trading_days(count=250):
    end = date(2026, 8, 31)
    return tuple((end - timedelta(days=count - 1 - index)).isoformat()
                 for index in range(count))


def quiet_row(*, close_state="unavailable", close_value=None):
    close = {"state": close_state}
    if close_state == "positive":
        close["value"] = close_value
    else:
        close["reason"] = "source_reports_no_trade"
    return {
        "exchange_allows_trading": True,
        "volume": "0",
        "turnover": "0",
        "close": close,
    }


class EvaluateWindowTests(unittest.TestCase):
    def evaluate(self, days, rows):
        from ashare_pipeline.formal_policy_market import evaluate_window
        return evaluate_window(days, rows)

    def test_tail_veto_survives_older_gap(self):
        days = trading_days()
        rows = {day: dict(coverage="covered", **quiet_row()) for day in days}
        del rows[days[0]]
        result = self.evaluate(days, rows)
        self.assertEqual(result["veto_state"], "proven")
        self.assertEqual(result["price_state"], "incomplete")
        self.assertIsNone(result["price"])
        self.assertIn("market_coverage_missing", result["pending"])

    def test_stale_boundaries_and_window_exclusion_use_actual_trading_days(self):
        days = trading_days()
        for stale in (0, 1, 19, 20, 249):
            with self.subTest(stale=stale):
                rows = {day: dict(coverage="covered", **quiet_row()) for day in days}
                chosen = days[-1 - stale]
                rows[chosen] = dict(coverage="covered", exchange_allows_trading=True,
                    volume="1", turnover="2",
                    close={"state": "positive", "value": "3.5"})
                result = self.evaluate(days, rows)
                self.assertEqual(result["price_state"], "positive_close_complete")
                self.assertEqual(result["price"], "3.5")
                self.assertEqual(result["price_date"], chosen)
                self.assertEqual(result["stale_days"], stale)
                self.assertEqual(result["veto_state"], "clear" if stale < 20 else "proven")

        outside = (date.fromisoformat(days[0]) - timedelta(days=1)).isoformat()
        rows = {day: dict(coverage="covered", **quiet_row()) for day in days}
        rows[outside] = dict(coverage="covered", exchange_allows_trading=True,
            volume="1", turnover="2", close={"state": "positive", "value": "99"})
        result = self.evaluate(days, rows)
        self.assertEqual(result["price_state"], "confirmed_no_price_250")
        self.assertIsNone(result["price"])

    def test_tail_gap_is_pending_but_effective_trade_without_close_clears_veto(self):
        days = trading_days(20)
        rows = {day: dict(coverage="covered", **quiet_row()) for day in days}
        del rows[days[-1]]
        self.assertEqual(self.evaluate(days, rows)["veto_state"], "pending")
        rows[days[-1]] = dict(coverage="covered", exchange_allows_trading=True,
            volume="1", turnover="1",
            close={"state": "unavailable", "reason": "source_omits_close"})
        result = self.evaluate(days, rows)
        self.assertEqual(result["veto_state"], "clear")
        self.assertEqual(result["price_state"], "incomplete")
        self.assertIn("market_price_missing", result["pending"])

    def test_complete_no_trade_window_keeps_veto_and_market_pending(self):
        days = trading_days()
        rows = {day: dict(coverage="covered", **quiet_row()) for day in days}
        result = self.evaluate(days, rows)
        self.assertEqual(result["price_state"], "confirmed_no_price_250")
        self.assertEqual(result["stale_at_least"], 250)
        self.assertEqual(result["veto_state"], "proven")
        self.assertIn("market_evidence_missing", result["pending"])

    def test_older_gap_before_latest_complete_price_is_irrelevant(self):
        days = trading_days()
        rows = {day: dict(coverage="covered", **quiet_row()) for day in days}
        del rows[days[0]]
        rows[days[-21]] = dict(coverage="covered", exchange_allows_trading=True,
            volume="1", turnover="2", close={"state": "positive", "value": "4"})
        result = self.evaluate(days, rows)
        self.assertEqual(result["price_state"], "positive_close_complete")
        self.assertEqual(result["stale_days"], 20)
        self.assertEqual(result["veto_state"], "proven")
        self.assertNotIn("market_coverage_missing", result["pending"])

    def test_window_input_is_closed_and_finite(self):
        days = trading_days(2)
        good = {day: dict(coverage="covered", **quiet_row()) for day in days}
        mutations = [
            ((days[1], days[0]), good),
            ((days[0], days[0]), good),
            (days, {**good, days[0]: {**good[days[0]], "volume": "Infinity"}}),
            (days, {**good, days[0]: {**good[days[0]], "exchange_allows_trading": 1}}),
            (days, {**good, days[0]: {**good[days[0]], "turnover": "-1"}}),
            (days, {**good, days[0]: {**good[days[0]], "close": {"state": "positive", "value": "0"}}}),
        ]
        for supplied_days, rows in mutations:
            with self.subTest(days=supplied_days, rows=rows), self.assertRaises(ValueError):
                self.evaluate(supplied_days, rows)


class MarketRepositoryTests(unittest.TestCase):
    def fixture(self, **kwargs):
        fixture = RangeStoreFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def test_genuine_source_path_proves_tail_veto_and_keeps_older_gap_pending(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        fixture = self.fixture()
        days = trading_days()
        rows = {day: quiet_row() for day in days}
        del rows[days[0]]
        fixture.put_window("SH600000", trading_days=days, rows=rows)
        repository = FormalPolicyMarketRepository(fixture.range_store)
        selection = repository.select("SH600000", FREEZE, binding=fixture.binding)
        selection.recheck()
        self.assertIsNotNone(selection.window)
        self.assertEqual(selection.window.veto_state, "proven")
        self.assertEqual(selection.window.price_state, "incomplete")
        self.assertIn("market_coverage_missing", selection.pending)
        selection.window.require_current()
        self.assertEqual(selection.window.to_dict()["required_trading_days"], list(days))

    def test_calendar_proof_is_genuine_current_and_drives_bounded_market_request(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        fixture = self.fixture()
        days = trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = FormalPolicyMarketRepository(fixture.range_store)
        calendar = repository.select_calendar(fixture.binding, FREEZE)
        calendar.recheck()
        proof = calendar.coverage
        self.assertIsNotNone(proof)
        proof.require_current()
        binding, source = fixture.range_store.resolve_planning_binding(fixture.binding)
        requests = source.market_requests("SH600000", calendar_coverage=proof)
        self.assertTrue(requests)
        self.assertTrue(all(request.kind == "market_range" for request in requests))
        self.assertTrue(all(proof.covered_start <= request.start_date <= request.end_date <= proof.covered_end
                            for request in requests))
        with self.assertRaises(TypeError):
            copy.copy(proof)
        with self.assertRaises(ValueError):
            type(proof)(**proof.to_dict())
        self.assertIs(binding, source._binding)

    def test_planner_requests_calendar_then_market_and_stops_when_decidable(self):
        from ashare_pipeline.formal_policy_market import plan_next_window_request
        fixture = self.fixture()
        first = plan_next_window_request("SH600000", FREEZE,
            binding=fixture.binding, range_store=fixture.range_store)
        self.assertEqual(first.kind, "calendar_range")
        days = trading_days(20)
        rows = {day: quiet_row() for day in days}
        rows[days[-1]] = dict(exchange_allows_trading=True, volume="1", turnover="2",
                              close={"state": "positive", "value": "3.5"})
        fixture.put_window("SH600000", trading_days=days, rows=rows)
        self.assertIsNone(plan_next_window_request("SH600000", FREEZE,
            binding=fixture.binding, range_store=fixture.range_store))

    def test_freeze_day_must_be_explicitly_proven_open(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        fixture = self.fixture()
        days = trading_days(20)
        with self.assertRaises(ValueError):
            fixture.put_window("SH600000", trading_days=days[:-1],
                               rows={day: quiet_row() for day in days[:-1]})


if __name__ == "__main__":
    unittest.main()
