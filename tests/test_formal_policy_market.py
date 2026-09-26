"""Calendar coverage and independent market-window policy evidence."""

from datetime import date, timedelta
from decimal import Decimal
import copy
import subprocess
import sys
import textwrap
import unittest

from tests.formal_range_fixtures import RangeStoreFixture
from tests.test_formal_range_source import document_wire


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

    def persist(self, fixture, request, wire, *, generation="g1"):
        task = fixture.range_store.enqueue(request, refresh_generation=generation)
        fixture.reply(wire, original_url=(
            "https://www.cninfo.com.cn/fixture/range-calendar.json"
            if request.kind == "calendar_range"
            else "https://www.cninfo.com.cn/fixture/range-market.json"
        ))
        lease = fixture.range_store.lease_next("market-review-worker", lease_seconds=3600)
        self.assertIsNotNone(lease)
        self.assertEqual(lease["id"], task["id"])
        return fixture.range_store.persist(task["id"], "market-review-worker",
            lease["attempt_id"], fetch=fixture.source.fetch_verified(request))

    def calendar_wire(self, fixture, request, *, opened=(), coverage=None,
                      upstream_generation="calendar-g1", row_time=None):
        config = fixture.source.range_config(request)
        opened = set(opened)
        start = date.fromisoformat((coverage or {}) .get("start_date", request.start_date))
        end = date.fromisoformat((coverage or {}) .get("end_date", request.end_date))
        times = {
            "published_at_utc": "2026-08-29T08:00:00+00:00",
            "published_precision": "timestamp",
            "effective_at_utc": "2026-08-29T08:00:00+00:00",
            "effective_time_evidence_hash": None,
            "captured_at_utc": "2026-08-31T06:59:00+00:00",
        }
        if row_time is not None:
            times.update(row_time)
        rows = []
        cursor = start
        while cursor <= end:
            day = cursor.isoformat()
            rows.append({"date": day, "is_open": day in opened, **times})
            cursor += timedelta(days=1)
        declared = {"start_date": start.isoformat(), "end_date": end.isoformat(),
                    "complete": True}
        return document_wire(request, rows=rows, record_count=len(rows),
            page_record_count=len(rows), coverage=declared,
            upstream_generation=upstream_generation,
            parser_id=config.parser_id, parser_version=config.parser_version,
            mapping_version=config.mapping_version,
            normalizer_version=config.normalizer_version,
            request_version=config.request_version)

    def test_successful_wire_assembly_reads_each_owned_binding_once(self):
        from ashare_pipeline import formal_policy_market as market_module

        fixture = self.fixture()
        days = trading_days(20)
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: quiet_row() for day in days})
        repository = market_module.FormalPolicyMarketRepository(fixture.range_store)
        reader_code = market_module._read_binding.__code__
        calls = {"select_calendar": [], "select": []}

        tool_id = next(identifier for identifier in range(6)
                       if sys.monitoring.get_tool(identifier) is None)
        sys.monitoring.use_tool_id(tool_id, "market-binding-read-test")

        def monitor(code, instruction_offset):
            self.assertIs(code, reader_code)
            caller_frame = sys._getframe(2)
            caller = caller_frame.f_code.co_name
            if caller in calls:
                for recorded in calls[caller]:
                    if recorded[0] is caller_frame:
                        recorded[1] += 1
                        break
                else:
                    calls[caller].append([caller_frame, 1])

        sys.monitoring.register_callback(tool_id, sys.monitoring.events.PY_START, monitor)
        sys.monitoring.set_local_events(tool_id, reader_code, sys.monitoring.events.PY_START)
        try:
            calendar = repository.select_calendar(fixture.binding, FREEZE)
            window = repository.select("SH600000", FREEZE, binding=fixture.binding)
        finally:
            sys.monitoring.set_local_events(tool_id, reader_code, 0)
            sys.monitoring.free_tool_id(tool_id)

        self.assertIsNotNone(calendar.coverage)
        self.assertIsNotNone(window.window)
        for operation in ("select_calendar", "select"):
            with self.subTest(operation=operation):
                self.assertTrue(calls[operation])
                self.assertEqual({recorded[1] for recorded in calls[operation]}, {1})

    def test_no_module_global_proof_mint_survives_either_import_order(self):
        script = textwrap.dedent("""
            import importlib
            import sys
            order = sys.argv[1]
            if order == "source-first":
                importlib.import_module("ashare_pipeline.formal_range_source")
            market = importlib.import_module("ashare_pipeline.formal_policy_market")
            if order == "market-first":
                importlib.import_module("ashare_pipeline.formal_range_source")
            forbidden = ("_mint_calendar_coverage", "_mint_market_window",
                         "_install_market_proof_owner", "_build_proof_types")
            assert not any(hasattr(market, name) for name in forbidden), forbidden
            for proof_type in (market.VerifiedCalendarCoverageV1,
                               market.VerifiedMarketWindowV1):
                try:
                    proof_type()
                except ValueError:
                    pass
                else:
                    raise AssertionError("external proof construction succeeded")
        """)
        for order in ("source-first", "market-first"):
            with self.subTest(order=order):
                result = subprocess.run([sys.executable, "-c", script, order],
                    cwd=".", text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_repository_rejects_instance_authority_method_shadowing(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        repository = FormalPolicyMarketRepository(self.fixture().range_store)
        for name in ("_page_group", "select_calendar", "select"):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                setattr(repository, name, lambda *args, **kwargs: None)

    def test_repository_rejects_subclass_authority_overrides(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        with self.assertRaises(TypeError):
            class ShadowRepository(FormalPolicyMarketRepository):
                def _page_group(self, source, first_request):
                    return (), None

                def select_calendar(self, binding, as_of_utc):
                    return None

                def select(self, security_id, as_of_utc, *, binding):
                    return None

    def test_repository_rejects_store_replacement(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        owned = self.fixture()
        foreign = self.fixture()
        repository = FormalPolicyMarketRepository(owned.range_store)
        with self.assertRaises(AttributeError):
            repository._store = foreign.range_store

    def test_stale_recheck_cannot_be_bypassed_by_method_shadowing(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository

        calendar_fixture = self.fixture()
        first = calendar_fixture.source.first_calendar_request(FREEZE)
        first_observation = self.persist(calendar_fixture, first,
            self.calendar_wire(calendar_fixture, first, opened=("2026-08-31",)))
        calendar_repository = FormalPolicyMarketRepository(calendar_fixture.range_store)
        calendar_selection = calendar_repository.select_calendar(
            calendar_fixture.binding, FREEZE)
        try:
            object.__setattr__(calendar_repository, "select_calendar",
                lambda *args, **kwargs: calendar_selection)
        except (AttributeError, TypeError):
            pass
        older = calendar_fixture.source.previous_calendar_request(first_observation)
        self.persist(calendar_fixture, older,
            self.calendar_wire(calendar_fixture, older), generation="g1")
        with self.assertRaises(ValueError):
            calendar_selection.coverage.require_current()

        market_fixture = self.fixture()
        recent = trading_days(20)
        first = market_fixture.source.first_calendar_request(FREEZE)
        self.persist(market_fixture, first,
            self.calendar_wire(market_fixture, first, opened=recent))
        market_repository = FormalPolicyMarketRepository(market_fixture.range_store)
        market_selection = market_repository.select(
            "SH600000", FREEZE, binding=market_fixture.binding)
        try:
            object.__setattr__(market_repository, "select",
                lambda *args, **kwargs: market_selection)
        except (AttributeError, TypeError):
            pass
        market_fixture.put_window("SH600000", trading_days=recent,
            rows={day: quiet_row() for day in recent})
        with self.assertRaises(ValueError):
            market_selection.window.require_current()

    def test_calendar_proof_rejects_same_root_cross_store_reuse(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        owner = self.fixture()
        peer = self.fixture()
        recent = trading_days(20)
        first = owner.source.first_calendar_request(FREEZE)
        self.persist(owner, first, self.calendar_wire(owner, first, opened=recent))
        proof = FormalPolicyMarketRepository(owner.range_store).select_calendar(
            owner.binding, FREEZE).coverage

        _, same_store_source = owner.range_store.resolve_planning_binding(peer.binding)
        self.assertTrue(same_store_source.market_requests(
            "SH600000", calendar_coverage=proof))

        _, peer_source = peer.range_store.resolve_planning_binding(peer.binding)
        with self.assertRaises(ValueError):
            peer_source.market_requests("SH600000", calendar_coverage=proof)

    def test_initial_market_request_rejects_same_root_cross_store_enqueue(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        owner = self.fixture()
        peer = self.fixture()
        recent = trading_days(20)
        first = owner.source.first_calendar_request(FREEZE)
        self.persist(owner, first, self.calendar_wire(owner, first, opened=recent))
        proof = FormalPolicyMarketRepository(owner.range_store).select_calendar(
            owner.binding, FREEZE).coverage

        _, same_store_source = owner.range_store.resolve_planning_binding(peer.binding)
        request = same_store_source.market_requests(
            "SH600000", calendar_coverage=proof)[0]
        task = owner.range_store.enqueue(request, refresh_generation="owner-market")
        self.assertEqual(task["status"], "pending")

        with self.assertRaises(ValueError):
            peer.range_store.enqueue(request, refresh_generation="peer-market")

    def test_date_only_hash_without_resolved_temporal_proof_stays_unproven(self):
        from ashare_pipeline.formal_policy_market import (
            FormalPolicyMarketRepository, plan_next_window_request,
        )
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        wire = self.calendar_wire(fixture, request, opened=("2026-08-31",), row_time={
            "published_precision": "date_only",
            "effective_at_utc": "2026-08-29T08:00:00+00:00",
            "effective_time_evidence_hash": "a" * 64,
        })
        self.persist(fixture, request, wire)
        selection = FormalPolicyMarketRepository(fixture.range_store).select_calendar(
            fixture.binding, FREEZE)
        self.assertIsNone(selection.coverage)
        self.assertEqual(selection.pending, ("visibility_unproven",))
        self.assertIsNone(plan_next_window_request("SH600000", FREEZE,
            binding=fixture.binding, range_store=fixture.range_store))

    def test_calendar_rejects_nonadjacent_and_mixed_generation_composition(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        for defect in ("gap", "generation"):
            with self.subTest(defect=defect):
                fixture = self.fixture()
                first = fixture.source.first_calendar_request(FREEZE)
                first_observation = self.persist(fixture, first,
                    self.calendar_wire(fixture, first, opened=("2026-08-31",),
                                       upstream_generation="calendar-g1"),
                    generation="refresh-g1")
                older = fixture.source.previous_calendar_request(first_observation)
                coverage = None
                if defect == "gap":
                    coverage = {"start_date": older.start_date,
                                "end_date": (date.fromisoformat(older.end_date)
                                             - timedelta(days=1)).isoformat()}
                self.persist(fixture, older, self.calendar_wire(fixture, older,
                    coverage=coverage,
                    upstream_generation=("calendar-g2" if defect == "generation"
                                         else "calendar-g1")),
                    generation=("refresh-g2" if defect == "generation" else "refresh-g1"))
                with self.assertRaises(ValueError):
                    FormalPolicyMarketRepository(fixture.range_store).select_calendar(
                        fixture.binding, FREEZE)

    def test_calendar_proof_tracks_absent_older_segment(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        fixture = self.fixture()
        first = fixture.source.first_calendar_request(FREEZE)
        recent = trading_days(20)
        first_observation = self.persist(fixture, first,
            self.calendar_wire(fixture, first, opened=recent))
        repository = FormalPolicyMarketRepository(fixture.range_store)
        proof = repository.select_calendar(fixture.binding, FREEZE).coverage
        self.assertIsNotNone(proof)
        older = fixture.source.previous_calendar_request(first_observation)
        self.persist(fixture, older, self.calendar_wire(fixture, older), generation="g1")
        with self.assertRaises(ValueError):
            proof.require_current()

    def test_market_window_tracks_absent_request_and_numbered_page(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        recent = trading_days(20)
        rows = {day: quiet_row() for day in recent}

        fixture = self.fixture()
        first = fixture.source.first_calendar_request(FREEZE)
        self.persist(fixture, first, self.calendar_wire(fixture, first, opened=recent))
        repository = FormalPolicyMarketRepository(fixture.range_store)
        absent = repository.select("SH600000", FREEZE, binding=fixture.binding).window
        self.assertIsNotNone(absent)
        fixture.put_window("SH600000", trading_days=recent, rows=rows)
        with self.assertRaises(ValueError):
            absent.require_current()

        def numbered(documents):
            market = next(item for item in documents["source"]["range_configs"]
                          if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            market.update(pagination="numbered_pages_v1", max_pages=2)

        paged = self.fixture(mutate=numbered)
        paged.put_window("SH600000", trading_days=recent, rows=rows, omit_pages=(2,))
        repository = FormalPolicyMarketRepository(paged.range_store)
        incomplete = repository.select("SH600000", FREEZE, binding=paged.binding).window
        self.assertIsNotNone(incomplete)
        calendar = repository.select_calendar(paged.binding, FREEZE).coverage
        _, source = paged.range_store.resolve_planning_binding(paged.binding)
        request = source.market_requests("SH600000", calendar_coverage=calendar)[0]
        page_one = paged.range_store.select_current(request.request_fingerprint)
        page_two = source.next_page(page_one)
        selected = [(day, rows[day]) for day in recent
                    if request.start_date <= day <= request.end_date]
        market_rows = []
        base = document_wire(page_two)["rows"][0]
        for day, raw in selected[1::2]:
            market_rows.append({"date": day,
                "exchange_allows_trading": raw["exchange_allows_trading"],
                "volume": raw["volume"], "volume_unit": "shares",
                "turnover": raw["turnover"], "turnover_unit": "CNY",
                "close": dict(raw["close"]), "close_unit": "CNY_per_share",
                **{key: base[key] for key in (
                    "published_at_utc", "published_precision", "effective_at_utc",
                    "effective_time_evidence_hash", "captured_at_utc")}})
        config = source.range_config(page_two)
        wire = document_wire(page_two, rows=market_rows, page_index=2, page_count=2,
            record_count=len(selected), page_record_count=len(market_rows),
            upstream_generation="fixture-market-g1",
            pagination_evidence="source_declared_numbered_pages_v1",
            coverage={"start_date": page_two.start_date, "end_date": page_two.end_date,
                      "complete": True},
            parser_id=config.parser_id, parser_version=config.parser_version,
            mapping_version=config.mapping_version,
            normalizer_version=config.normalizer_version,
            request_version=config.request_version)
        self.persist(paged, page_two, wire, generation="g1")
        with self.assertRaises(ValueError):
            incomplete.require_current()

    def test_planner_does_not_repeat_verified_blocker_or_scan_past_price_blocker(self):
        from ashare_pipeline.formal_policy_market import plan_next_window_request
        fixture = self.fixture()
        first = fixture.source.first_calendar_request(FREEZE)
        wire = self.calendar_wire(fixture, first, opened=("2026-08-31",))
        wire["rows"].pop(0)
        wire["record_count"] -= 1
        wire["page_record_count"] -= 1
        self.persist(fixture, first, wire)
        self.assertIsNone(plan_next_window_request("SH600000", FREEZE,
            binding=fixture.binding, range_store=fixture.range_store))

        blocked = self.fixture()
        recent = trading_days(20)
        rows = {day: quiet_row() for day in recent}
        rows[recent[-1]] = {"exchange_allows_trading": True, "volume": "1",
            "turnover": "1", "close": {"state": "unavailable",
                                          "reason": "source_omits_close"}}
        blocked.put_window("SH600000", trading_days=recent, rows=rows)
        self.assertIsNone(plan_next_window_request("SH600000", FREEZE,
            binding=blocked.binding, range_store=blocked.range_store))

        searching = self.fixture()
        searching.put_window("SH600000", trading_days=recent,
                             rows={day: quiet_row() for day in recent})
        older = plan_next_window_request("SH600000", FREEZE,
            binding=searching.binding, range_store=searching.range_store)
        self.assertIsNotNone(older)
        self.assertEqual(older.kind, "calendar_range")

    def test_authenticated_domain_conflict_survives_repository_path(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        fixture = self.fixture()
        recent = trading_days(20)
        rows = {day: quiet_row() for day in recent}
        rows[recent[-1]] = {"coverage": "domain_conflict",
                            "reason": "source_duplicate_trading_day"}
        fixture.put_window("SH600000", trading_days=recent, rows=rows)
        selection = FormalPolicyMarketRepository(fixture.range_store).select(
            "SH600000", FREEZE, binding=fixture.binding)
        self.assertIn("market_domain_conflict", selection.pending)
        daily = {item["date"]: item for item in selection.window.to_dict()["daily_records"]}
        self.assertEqual(daily[recent[-1]], {"date": recent[-1],
            "coverage": "domain_conflict", "reason": "source_duplicate_trading_day",
            "observation_hash": daily[recent[-1]]["observation_hash"]})

    def test_distinct_signed_config_keys_and_wrong_binding_boundaries(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        def distinct(documents):
            market = next(item for item in documents["source"]["range_configs"]
                          if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            market.update(parser_version="fixture-market-v2",
                          normalizer_version="fixture-market-normalizer-v2")

        fixture = self.fixture(mutate=distinct)
        self.assertNotEqual(fixture.binding.calendar_config.parser_version,
                            fixture.binding.market_config.parser_version)
        recent = trading_days(20)
        fixture.put_window("SH600000", trading_days=recent,
                           rows={day: quiet_row() for day in recent})
        repository = FormalPolicyMarketRepository(fixture.range_store)
        with self.assertRaises(ValueError):
            repository.select("SZ000001", FREEZE, binding=fixture.binding)
        foreign = self.fixture(mutate=distinct)
        self.assertEqual(
            repository.select("SH600000", FREEZE, binding=foreign.binding).window.to_dict(),
            repository.select("SH600000", FREEZE, binding=fixture.binding).window.to_dict(),
        )

        def different_root(documents):
            distinct(documents)
            market = next(item for item in documents["source"]["range_configs"]
                          if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            market["retry_base_seconds"] = 2.0

        wrong_root = self.fixture(mutate=different_root)
        with self.assertRaises(ValueError):
            repository.select("SH600000", FREEZE, binding=wrong_root.binding)

    def test_numbered_market_pages_reject_duplicate_dates(self):
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        def numbered(documents):
            market = next(item for item in documents["source"]["range_configs"]
                          if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            market.update(pagination="numbered_pages_v1", max_pages=2)

        fixture = self.fixture(mutate=numbered)
        recent = trading_days(20)
        first = fixture.source.first_calendar_request(FREEZE)
        self.persist(fixture, first, self.calendar_wire(fixture, first, opened=recent))
        repository = FormalPolicyMarketRepository(fixture.range_store)
        calendar = repository.select_calendar(fixture.binding, FREEZE).coverage
        _, source = fixture.range_store.resolve_planning_binding(fixture.binding)
        request = source.market_requests("SH600000", calendar_coverage=calendar)[0]
        config = source.range_config(request)

        def market_wire(page, index):
            base = document_wire(page)["rows"][0]
            row = {"date": recent[-1], "exchange_allows_trading": True,
                "volume": "0", "volume_unit": "shares", "turnover": "0",
                "turnover_unit": "CNY",
                "close": {"state": "unavailable", "reason": "source_reports_no_trade"},
                "close_unit": "CNY_per_share",
                **{key: base[key] for key in (
                    "published_at_utc", "published_precision", "effective_at_utc",
                    "effective_time_evidence_hash", "captured_at_utc")}}
            return document_wire(page, rows=[row], page_index=index, page_count=2,
                record_count=2, page_record_count=1,
                pagination_evidence="source_declared_numbered_pages_v1",
                coverage={"start_date": page.start_date, "end_date": page.end_date,
                          "complete": True},
                parser_id=config.parser_id, parser_version=config.parser_version,
                mapping_version=config.mapping_version,
                normalizer_version=config.normalizer_version,
                request_version=config.request_version)

        page_one = self.persist(fixture, request, market_wire(request, 1))
        page_two = source.next_page(page_one)
        self.persist(fixture, page_two, market_wire(page_two, 2))
        with self.assertRaises(ValueError):
            repository.select("SH600000", FREEZE, binding=fixture.binding)

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
