"""Bounded worker integration tests using genuine requests and temporary evidence."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_sources import (
    FormalRetryableSourceError,
    FormalSourceBlocked,
    FormalTerminalSourceError,
)
from tests import formal_range_fixtures
from tests.test_formal_range_source import document_wire


NOW = "2026-09-01T00:00:00+00:00"


def numbered(documents):
    for config in documents["source"]["range_configs"]:
        config.update(pagination="numbered_pages_v1", max_pages=2)


class FormalRangeWorkerTests(unittest.TestCase):
    def test_market_request_uses_market_retry_cooldown_and_page_budgets(self):
        def distinct(documents):
            market = next(item for item in documents["source"]["range_configs"]
                          if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            market.update(pagination="numbered_pages_v1", max_pages=2,
                          retry_max_attempts=2, retry_base_seconds=7.0,
                          challenge_cooldown_seconds=23.0)

        fixture = self.fixture(mutate=distinct)
        days = tuple(f"2026-08-{day:02d}" for day in range(12, 32))
        fixture.put_window("SH600000", trading_days=days,
                           rows={day: {"exchange_allows_trading": True, "volume": "0",
                                      "turnover": "0", "close": {"state": "unavailable",
                                      "reason": "source_reports_no_trade"}} for day in days},
                           omit_pages=(1,))
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        calendar = FormalPolicyMarketRepository(fixture.range_store).select_calendar(
            fixture.binding, "2026-08-31T07:00:00+00:00")
        _, source = fixture.range_store.resolve_planning_binding(fixture.binding)
        request = source.market_requests("SH600000", calendar_coverage=calendar.coverage)[0]
        config = source.range_config(request)
        self.assertEqual(config.max_pages, 2)
        self.assertEqual(config.challenge_cooldown_seconds, 23.0)

        first_row = document_wire(request)["rows"][0]
        first_row["date"] = request.start_date
        fixture.reply(document_wire(request, rows=[first_row], page_count=2,
            record_count=2, page_record_count=1,
            pagination_evidence="source_declared_numbered_pages_v1"),
            original_url="https://www.cninfo.com.cn/fixture/range-market.json")
        first = fixture.worker.run_once()
        self.assertEqual(first["state"], "verified")
        self.assertIsNotNone(first["next_task_id"])
        page_one = fixture.range_store.select_current(request.request_fingerprint)
        page_two = source.next_page(page_one)
        second_row = document_wire(page_two)["rows"][0]
        second_row["date"] = request.end_date
        fixture.reply(document_wire(page_two, rows=[second_row], page_index=2, page_count=2,
            record_count=2, page_record_count=1,
            pagination_evidence="source_declared_numbered_pages_v1"),
            original_url="https://www.cninfo.com.cn/fixture/range-market.json")
        second = fixture.worker.run_once()
        self.assertEqual(second["state"], "verified")
        self.assertIsNone(second["next_task_id"])

        retry_request = source.market_requests(
            "SH600001", calendar_coverage=calendar.coverage)[0]
        fixture.range_store.enqueue(retry_request, refresh_generation="g-retry")
        fixture.transport.error = FormalSourceBlocked("blocked")
        result = fixture.worker.run_once()
        self.assertEqual(result["state"], "retryable_failed")
        self.assertEqual(result["next_retry_at"], "2026-09-01T00:00:23+00:00")
        later = "2026-09-01T00:00:23+00:00"
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value=later), \
                patch("ashare_pipeline.formal_range_worker._utc_now", return_value=later):
            terminal = fixture.worker.run_once()
        self.assertEqual(terminal["state"], "terminal_failed")
        self.assertIsNone(terminal["next_retry_at"])

    def fixture(self, **kwargs):
        self.assertTrue(hasattr(formal_range_fixtures, "RangeWorkerFixture"),
                        "bounded range worker fixture is absent")
        fixture = formal_range_fixtures.RangeWorkerFixture(**kwargs)
        self.addCleanup(fixture.close)
        for target in ("ashare_pipeline.formal_range_store._utc_now",
                       "ashare_pipeline.formal_range_worker._utc_now"):
            timer = patch(target, return_value=NOW)
            timer.start()
            self.addCleanup(timer.stop)
        return fixture

    def rows(self, fixture, sql, parameters=()):
        with closing(sqlite3.connect(fixture.store.db_path)) as connection:
            return connection.execute(sql, parameters).fetchall()

    def page(self, request, **changes):
        return document_wire(request, page_index=request.page_index, page_count=2,
                             record_count=2, pagination_evidence="source_declared_numbered_pages_v1",
                             **changes)

    def test_resume_does_not_fetch_verified_bytes_twice(self):
        fixture = self.fixture()
        request = fixture.enqueue_calendar()
        result = fixture.worker.run_once()
        self.assertEqual(result["state"], "verified")
        calls = len(fixture.transport.calls)
        resumed = fixture.worker.resume(request, refresh_generation="g1")
        self.assertEqual(resumed["state"], "verified")
        self.assertEqual(len(fixture.transport.calls), calls)
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_attempt"), [(1,)])
        json.dumps(result)
        json.dumps(resumed)
        self.assertNotIn("coverage", result)
        self.assertNotIn("complete", result)

    def test_idle_and_single_task_execution_do_not_scan_backwards(self):
        fixture = self.fixture()
        self.assertEqual(fixture.worker.run_once()["state"], "idle")
        fixture.enqueue_calendar()
        self.assertEqual(fixture.worker.run_once()["state"], "verified")
        self.assertEqual(fixture.worker.run_once()["state"], "idle")
        self.assertEqual(len(fixture.transport.calls), 1)
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_task"), [(1,)])

    def test_refresh_generation_requires_a_new_attempt(self):
        fixture = self.fixture()
        request = fixture.enqueue_calendar()
        fixture.worker.run_once()
        self.assertEqual(fixture.worker.resume(request, refresh_generation="g2")["state"], "pending")
        self.assertEqual(len(fixture.transport.calls), 1)
        self.assertEqual(fixture.worker.run_once()["state"], "verified")
        self.assertEqual(len(fixture.transport.calls), 2)
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_normalization_receipt"), [(2,)])

    def test_timeout_retries_only_until_signed_attempt_limit(self):
        fixture = self.fixture()
        fixture.enqueue_calendar()
        fixture.transport.error = TimeoutError("fixture timeout")
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value=NOW), \
                patch("ashare_pipeline.formal_range_worker._utc_now", return_value=NOW):
            first = fixture.worker.run_once()
            self.assertEqual(first["state"], "retryable_failed")
            self.assertEqual(first["next_retry_at"], "2026-09-01T00:00:01+00:00")
            self.assertEqual(fixture.worker.run_once()["state"], "idle")
        later = "2026-09-01T00:00:01+00:00"
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value=later), \
                patch("ashare_pipeline.formal_range_worker._utc_now", return_value=later):
            last = fixture.worker.run_once()
            self.assertEqual(last["state"], "terminal_failed")
            self.assertIsNone(last["next_retry_at"])
            self.assertEqual(fixture.worker.run_once()["state"], "idle")
        self.assertEqual(len(fixture.transport.calls), 2)
        self.assertEqual(self.rows(fixture, "SELECT outcome FROM formal_range_attempt ORDER BY attempt_no"),
                         [("retryable_failed",), ("terminal_failed",)])
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_snapshot"), [(0,)])

    def test_expired_attempts_exhaust_budget_before_another_fetch(self):
        fixture = self.fixture()
        fixture.enqueue_calendar()
        for timestamp in (NOW, "2026-09-01T00:01:00+00:00"):
            with patch("ashare_pipeline.formal_range_store._utc_now", return_value=timestamp):
                fixture.range_store.lease_next("crashed", lease_seconds=60)
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value="2026-09-01T00:02:00+00:00"):
            result = fixture.worker.run_once()
        self.assertEqual(result["state"], "terminal_failed")
        self.assertEqual(result["code"], "attempt_budget_exhausted")
        self.assertEqual(len(fixture.transport.calls), 0)
        self.assertEqual(self.rows(fixture, "SELECT outcome FROM formal_range_attempt ORDER BY attempt_no"),
                         [("expired",), ("expired",), ("terminal_failed",)])

    def test_last_permitted_attempt_after_expiry_can_still_fetch(self):
        fixture = self.fixture()
        fixture.enqueue_calendar()
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value=NOW):
            fixture.range_store.lease_next("crashed", lease_seconds=60)
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value="2026-09-01T00:01:00+00:00"):
            result = fixture.worker.run_once()
        self.assertEqual(result["state"], "verified")
        self.assertEqual(len(fixture.transport.calls), 1)

    def test_blocked_responses_use_signed_cooldown_without_evidence(self):
        for status, wire in ((403, {}), (429, {}), (200, {"challenge": "captcha"})):
            with self.subTest(status=status, wire=wire):
                fixture = self.fixture()
                fixture.enqueue_calendar()
                fixture.reply(wire, status_code=status)
                with patch("ashare_pipeline.formal_range_store._utc_now", return_value=NOW), \
                        patch("ashare_pipeline.formal_range_worker._utc_now", return_value=NOW):
                    result = fixture.worker.run_once()
                self.assertEqual(result["state"], "retryable_failed")
                self.assertEqual(result["code"], "source_blocked")
                self.assertEqual(result["next_retry_at"], "2026-09-01T00:00:15+00:00")
                self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_normalization_receipt"), [(0,)])

    def test_failure_does_not_prevent_independent_task(self):
        fixture = self.fixture()
        fixture.enqueue_calendar()
        fixture.transport.error = TimeoutError()
        self.assertEqual(fixture.worker.run_once()["state"], "retryable_failed")
        fixture.transport.error = None
        fixture.enqueue_calendar(refresh_generation="g2")
        self.assertEqual(fixture.worker.run_once()["state"], "verified")
        self.assertEqual(self.rows(fixture, "SELECT status FROM formal_range_task ORDER BY refresh_generation"),
                         [("retryable_failed",), ("verified",)])

    def test_success_queues_only_next_page_and_missing_page_keeps_first(self):
        fixture = self.fixture(mutate=numbered)
        request = fixture.enqueue_calendar()
        fixture.reply(self.page(request))
        first = fixture.worker.run_once()
        self.assertEqual(first["state"], "verified")
        self.assertEqual(len(fixture.transport.calls), 1)
        self.assertEqual(self.rows(fixture, "SELECT status FROM formal_range_task ORDER BY json_extract(payload_json, '$.request.page_index')"),
                         [("verified",), ("pending",)])
        before = fixture.range_store.read_verified(first["task_id"]).observation_hash
        fixture.transport.error = TimeoutError()
        self.assertEqual(fixture.worker.run_once()["state"], "retryable_failed")
        self.assertEqual(fixture.range_store.read_verified(first["task_id"]).observation_hash, before)
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_normalization_receipt"), [(1,)])

    def test_restart_recovers_persist_to_enqueue_gap_without_refetch(self):
        fixture = self.fixture(mutate=numbered)
        request = fixture.enqueue_calendar()
        fixture.reply(self.page(request))
        lease = fixture.range_store.lease_next("crashed", lease_seconds=60)
        first = fixture.range_store.persist(lease["id"], "crashed", lease["attempt_id"],
            fetch=fixture.source.fetch_verified(lease["request"]))
        script = textwrap.dedent("""
            import json
            from pathlib import Path
            import sys
            from ashare_pipeline.formal_range_source import FormalRangeSource
            from ashare_pipeline.formal_range_store import FormalRangeStore
            from ashare_pipeline.formal_range_worker import FormalRangeWorker
            from ashare_pipeline.state_store import StateStore
            from tests.formal_range_fixtures import RangeSourceFixture
            from tests.test_formal_range_worker import numbered
            fixture = RangeSourceFixture(mutate=numbered)
            root = Path(sys.argv[1])
            state = StateStore(root / 'state.sqlite', registry_signature_verifier=fixture.verifier)
            state.initialize()
            def source_factory(binding):
                return FormalRangeSource(binding, transport=fixture.transport, implementations=fixture.implementations)
            store = FormalRangeStore(state, root=root, signature_verifier=fixture.verifier, source_factory=source_factory)
            worker = FormalRangeWorker(store, source_factory=source_factory, worker_id='cold-worker')
            request = fixture.source.first_calendar_request('2026-08-31T07:00:00+00:00')
            result = worker.resume(request, refresh_generation='g1')
            assert len(fixture.transport.calls) == 0
            print(json.dumps(result))
        """)
        cold = subprocess.run([sys.executable, "-c", script, str(fixture.root)], capture_output=True, text=True)
        self.assertEqual(cold.returncode, 0, cold.stderr)
        self.assertEqual(json.loads(cold.stdout)["state"], "pending")
        fixture.restart_worker()
        request = fixture.source.first_calendar_request("2026-08-31T07:00:00+00:00")
        resumed = fixture.worker.resume(request, refresh_generation="g1")
        self.assertEqual(resumed["state"], "pending")
        self.assertEqual(len(fixture.transport.calls), 1)
        second_request = fixture.source.next_page(fixture.range_store.read_verified(first.task["id"]))
        fixture.reply(self.page(second_request))
        self.assertEqual(fixture.worker.run_once()["state"], "verified")
        self.assertEqual(len(fixture.transport.calls), 2)
        self.assertEqual(fixture.worker.resume(request, refresh_generation="g1")["state"], "verified")
        self.assertEqual(fixture.worker.run_once()["state"], "idle")
        self.assertEqual(len(fixture.transport.calls), 2)

    def test_over_budget_page_declaration_is_not_verified(self):
        fixture = self.fixture()
        request = fixture.enqueue_calendar()
        fixture.reply(document_wire(request, page_count=2))
        self.assertEqual(fixture.worker.run_once()["state"], "terminal_failed")
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_normalization_receipt"), [(0,)])

    def test_malformed_remote_document_is_terminal(self):
        fixture = self.fixture()
        fixture.enqueue_calendar()
        fixture.reply({"malformed": True})
        self.assertEqual(fixture.worker.run_once()["state"], "terminal_failed")
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_snapshot"), [(0,)])

    def test_parent_replay_terminal_error_during_fetch_is_not_operational(self):
        class Parser:
            fail_replay = False

            def parse(self, raw_bytes, *, request, config):
                if self.fail_replay and request["page_index"] == 1:
                    raise FormalTerminalSourceError("parent replay failed")
                return json.loads(raw_bytes)

        class Normalizer:
            def normalize(self, value, *, request, config):
                return value

        parser = Parser()
        key = ("fixture-range-parser", "fixture-range-v1", "fixture-range-map-v1",
               "fixture-range-normalizer-v1", "formal-range-request-v1")
        fixture = self.fixture(mutate=numbered, implementations={key: (parser, Normalizer())})
        request = fixture.enqueue_calendar()
        fixture.reply(self.page(request))
        first = fixture.worker.run_once()
        child = fixture.source.next_page(fixture.range_store.read_verified(first["task_id"]))
        fixture.reply(self.page(child))
        fixture.transport.on_send = lambda _request: setattr(parser, "fail_replay", True)
        with self.assertRaises(FormalTerminalSourceError):
            fixture.worker.run_once()
        self.assertEqual(self.rows(fixture, "SELECT status FROM formal_range_task ORDER BY json_extract(payload_json, '$.request.page_index')"),
                         [("verified",), ("leased",)])

    def test_snapshot_parser_cannot_emit_live_acquisition_classification(self):
        from ashare_pipeline.formal_range_source import FormalRangeAcquisitionError

        class Parser:
            fail = False

            def parse(self, raw_bytes, *, request, config):
                if self.fail:
                    raise FormalRangeAcquisitionError("parser-originated terminal failure")
                return json.loads(raw_bytes)

        class Normalizer:
            def normalize(self, value, *, request, config):
                return value

        parser = Parser()
        key = ("fixture-range-parser", "fixture-range-v1", "fixture-range-map-v1",
               "fixture-range-normalizer-v1", "formal-range-request-v1")
        fixture = formal_range_fixtures.RangeSourceFixture(implementations={key: (parser, Normalizer())})
        self.addCleanup(fixture.close)
        request = fixture.source.first_calendar_request("2026-08-31T07:00:00+00:00")
        fixture.reply(document_wire(request))
        fetch = fixture.source.fetch_verified(request)
        parser.fail = True
        with self.assertRaises(FormalTerminalSourceError) as caught:
            fixture.source.parse_verified_snapshot(request, raw_bytes=fetch.raw_bytes,
                                                   manifest=fetch.to_manifest())
        self.assertNotIsInstance(caught.exception, FormalRangeAcquisitionError)

    def test_parent_recheck_callback_cannot_relabel_source_mutation_as_remote_failure(self):
        class Parser:
            armed = False
            live_source = None

            def parse(self, raw_bytes, *, request, config):
                if self.armed and request["page_index"] == 2:
                    raise FormalTerminalSourceError("malformed live page")
                if self.armed and request["page_index"] == 1:
                    self.armed = False
                    self.live_source._binding = object()
                return json.loads(raw_bytes)

        class Normalizer:
            def normalize(self, value, *, request, config):
                return value

        parser = Parser()
        key = ("fixture-range-parser", "fixture-range-v1", "fixture-range-map-v1",
               "fixture-range-normalizer-v1", "formal-range-request-v1")
        fixture = self.fixture(mutate=numbered, implementations={key: (parser, Normalizer())})
        request = fixture.enqueue_calendar()
        fixture.reply(self.page(request))
        first = fixture.worker.run_once()
        child = fixture.source.next_page(fixture.range_store.read_verified(first["task_id"]))
        fixture.reply(self.page(child))

        def source_factory(binding):
            parser.live_source = fixture.source_factory(binding)
            return parser.live_source

        fixture.worker.source_factory = source_factory
        fixture.transport.on_send = lambda _request: setattr(parser, "armed", True)
        with self.assertRaises(FormalTerminalSourceError):
            fixture.worker.run_once()
        self.assertEqual(self.rows(fixture, "SELECT status FROM formal_range_task ORDER BY json_extract(payload_json, '$.request.page_index')"),
                         [("verified",), ("leased",)])

    def test_raw_corruption_on_resume_preserves_old_rows_and_bytes(self):
        fixture = self.fixture()
        request = fixture.enqueue_calendar()
        result = fixture.worker.run_once()
        observation = fixture.range_store.read_verified(result["task_id"])
        path = Path(observation.snapshot["content_path"])
        corrupted = path.read_bytes() + b" "
        path.write_bytes(corrupted)
        with self.assertRaises(ValueError):
            fixture.worker.resume(request, refresh_generation="g1")
        self.assertEqual(path.read_bytes(), corrupted)
        self.assertEqual(len(fixture.transport.calls), 1)
        self.assertEqual(self.rows(fixture, "SELECT status FROM formal_range_task"), [("verified",)])
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_normalization_receipt"), [(1,)])

    def test_fetch_has_no_open_write_transaction_and_expired_owner_cannot_persist(self):
        fixture = self.fixture()
        fixture.enqueue_calendar()
        now = [NOW]

        def expire_and_reclaim(_request):
            with closing(sqlite3.connect(fixture.store.db_path, timeout=0)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.rollback()
            now[0] = "2026-09-01T00:01:00+00:00"
            replacement = fixture.range_store.lease_next("replacement", lease_seconds=60)
            self.assertEqual(replacement["attempt_no"], 2)

        fixture.transport.on_send = expire_and_reclaim
        with patch("ashare_pipeline.formal_range_store._utc_now", side_effect=lambda: now[0]):
            with self.assertRaises(ValueError):
                fixture.worker.run_once()
        self.assertEqual(self.rows(fixture, "SELECT worker_id,status FROM formal_range_task"), [("replacement", "leased")])
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_normalization_receipt"), [(0,)])

    def test_persist_and_replay_errors_are_not_transport_retries(self):
        fixture = self.fixture()
        request = fixture.enqueue_calendar()
        with patch.object(type(fixture.range_store), "persist", side_effect=FormalRetryableSourceError("storage")):
            with self.assertRaises(FormalRetryableSourceError):
                fixture.worker.run_once()
        self.assertEqual(self.rows(fixture, "SELECT status FROM formal_range_task"), [("leased",)])
        with patch.object(type(fixture.range_store), "enqueue", side_effect=FormalRetryableSourceError("replay")):
            with self.assertRaises(FormalRetryableSourceError):
                fixture.worker.resume(request, refresh_generation="g1")
        self.assertEqual(self.rows(fixture, "SELECT outcome FROM formal_range_attempt"), [(None,)])

    def test_transport_error_cannot_hide_source_callback_mutation(self):
        fixture = self.fixture()
        live_source = []

        def source_factory(binding):
            source = fixture.source_factory(binding)
            live_source[:] = [source]
            return source

        fixture.worker.source_factory = source_factory
        fixture.transport.on_send = lambda _request: setattr(live_source[0], "_binding", object())
        errors = (TimeoutError("timeout"), FormalRetryableSourceError("retryable"),
                  FormalSourceBlocked("blocked"))
        for index, error in enumerate(errors, 1):
            with self.subTest(error=type(error).__name__):
                fixture.enqueue_calendar(refresh_generation=f"g{index}")
                fixture.transport.error = error
                with self.assertRaises(FormalTerminalSourceError):
                    fixture.worker.run_once()
        self.assertEqual(len(fixture.transport.calls), 3)
        self.assertEqual(self.rows(fixture, "SELECT status FROM formal_range_task"), [("leased",)] * 3)
        self.assertEqual(self.rows(fixture, "SELECT outcome FROM formal_range_attempt"), [(None,)] * 3)
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_snapshot"), [(0,)])

    def test_retryable_response_cannot_hide_original_request_mutation(self):
        fixture = formal_range_fixtures.RangeSourceFixture()
        self.addCleanup(fixture.close)
        for status in (403, 503):
            with self.subTest(status=status):
                request = fixture.source.first_calendar_request("2026-08-31T07:00:00+00:00")
                fixture.reply({}, status_code=status)
                fixture.transport.on_send = lambda _sent: object.__setattr__(request, "page_index", 2)
                with self.assertRaises(Exception) as caught:
                    fixture.source.fetch_verified(request)
                self.assertIsInstance(caught.exception, ValueError)
        self.assertEqual(len(fixture.transport.calls), 2)

    def test_blocked_response_cannot_hide_current_parent_corruption(self):
        fixture = self.fixture(mutate=numbered)
        first_request = fixture.enqueue_calendar()
        fixture.reply(self.page(first_request))
        lease = fixture.range_store.lease_next("producer", lease_seconds=60)
        parent = fixture.range_store.persist(lease["id"], "producer", lease["attempt_id"],
            fetch=fixture.source.fetch_verified(lease["request"]))
        request = fixture.source.next_page(parent)
        path = Path(parent.snapshot["content_path"])
        corrupted = path.read_bytes() + b" "
        fixture.reply({}, status_code=403)
        fixture.transport.on_send = lambda _sent: path.write_bytes(corrupted)
        with self.assertRaises(Exception) as caught:
            fixture.source.fetch_verified(request)
        self.assertIsInstance(caught.exception, ValueError)
        self.assertEqual(path.read_bytes(), corrupted)
        self.assertEqual(self.rows(fixture, "SELECT status FROM formal_range_task"), [("verified",)])
        self.assertEqual(self.rows(fixture, "SELECT count(*) FROM formal_range_normalization_receipt"), [(1,)])

    def test_authenticated_binding_accessor_rejects_clones_and_replaced_aliases(self):
        from ashare_pipeline import formal_range_source as source_module
        accessor = getattr(source_module, "range_request_binding", None)
        self.assertTrue(callable(accessor), "authenticated request binding reader is absent")
        fixture = self.fixture()
        request = fixture.enqueue_calendar()
        self.assertIs(accessor(request), fixture.binding)
        forged = object.__new__(type(request))
        for name, value in request.to_dict().items():
            object.__setattr__(forged, name, value)
        with patch.object(source_module, "_trusted_range_request_snapshot", return_value=({}, {}, "")), \
                patch.object(source_module, "FormalRangeRequestV1", type("Fake", (), {})):
            self.assertIs(accessor(request), fixture.binding)
            for value in (forged, request.to_dict()):
                with self.assertRaises(ValueError):
                    accessor(value)
        object.__setattr__(request, "page_index", 2)
        with self.assertRaises(ValueError):
            accessor(request)

    def test_retry_delay_is_bounded_and_requires_positive_exact_attempt(self):
        from importlib.util import find_spec
        self.assertIsNotNone(find_spec("ashare_pipeline.formal_range_worker"), "worker module is absent")
        from ashare_pipeline.formal_range_worker import retry_delay
        for attempt, expected in ((1, 1.0), (2, 2.0), (3, 3.0), (10, 3.0)):
            self.assertEqual(retry_delay(1.0, attempt, 3.0), expected)
        for attempt in (True, 0, -1, 1.0, "1"):
            with self.assertRaises(ValueError):
                retry_delay(1.0, attempt, 3.0)
