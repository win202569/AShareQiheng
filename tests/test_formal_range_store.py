"""Real range persistence and producer fencing regressions."""
import unittest
import copy
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

FREEZE = "2026-08-31T07:00:00+00:00"
NOW = "2026-09-01T00:00:00+00:00"


class FormalRangeStoreTests(unittest.TestCase):
    def fixture(self, **kwargs):
        from tests import formal_range_fixtures
        self.assertTrue(hasattr(formal_range_fixtures, "RangeStoreFixture"))
        fixture = formal_range_fixtures.RangeStoreFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def task(self, fixture, generation="g1"):
        request = fixture.source.first_calendar_request(FREEZE)
        return request, fixture.range_store.enqueue(request, refresh_generation=generation)

    def test_lease_exact_expiry_replaces_attempt_even_for_same_worker(self):
        fixture = self.fixture()
        request, task = self.task(fixture)
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value=NOW):
            first = fixture.range_store.lease_next("worker", lease_seconds=60)
            self.assertIsNone(fixture.range_store.lease_next("other", lease_seconds=60))
        end = "2026-09-01T00:01:00+00:00"
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value=end):
            second = fixture.range_store.lease_next("worker", lease_seconds=60)
            self.assertEqual(second["attempt_no"], 2)
            self.assertNotEqual(first["attempt_id"], second["attempt_id"])
            with self.assertRaises(ValueError):
                fixture.range_store.renew(task["id"], "worker", first["attempt_id"], lease_seconds=60)
            self.assertEqual(fixture.range_store.renew(task["id"], "worker", second["attempt_id"], lease_seconds=90)["lease_expires_at"], "2026-09-01T00:02:30+00:00")
        with closing(sqlite3.connect(fixture.store.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT outcome FROM formal_range_attempt WHERE id=?", (first["attempt_id"],)).fetchone()[0], "expired")

    def test_retry_and_terminal_failure_never_create_evidence(self):
        fixture = self.fixture()
        _, task = self.task(fixture)
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value=NOW):
            lease = fixture.range_store.lease_next("worker", lease_seconds=60)
            fixture.range_store.fail(task["id"], "worker", lease["attempt_id"], code="timeout", retryable=True, next_retry_at="2026-09-01T00:00:30+00:00")
            self.assertIsNone(fixture.range_store.lease_next("worker", lease_seconds=60))
        with patch("ashare_pipeline.formal_range_store._utc_now", return_value="2026-09-01T00:00:30+00:00"):
            lease = fixture.range_store.lease_next("worker", lease_seconds=60)
            result = fixture.range_store.fail(task["id"], "worker", lease["attempt_id"], code="blocked", retryable=False, next_retry_at=None)
        self.assertEqual(result["status"], "terminal_failed")
        with self.assertRaises(ValueError):
            fixture.range_store.read_verified(task["id"])

    def test_enqueue_replay_and_noncanonical_payload_tamper(self):
        fixture = self.fixture()
        request, task = self.task(fixture)
        self.assertEqual(fixture.range_store.enqueue(request, refresh_generation="g1"), task)
        with closing(sqlite3.connect(fixture.store.db_path)) as connection:
            connection.execute("UPDATE formal_range_task SET payload_json=payload_json || ' '")
            connection.commit()
        with self.assertRaises(ValueError):
            fixture.range_store.enqueue(request, refresh_generation="g1")

    def test_observation_is_immutable_and_cannot_be_forged_or_copied(self):
        fixture = self.fixture()
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        with self.assertRaises((TypeError, AttributeError)):
            first.task["id"] = "forged"
        with self.assertRaises((TypeError, ValueError)):
            copy.copy(first)
        with self.assertRaises(ValueError):
            fixture.source.next_page(first.to_dict())
        with self.assertRaises(ValueError):
            type(first)()

    def test_raw_bytes_and_manifest_tamper_invalidate_reads(self):
        for field in ("content_path", "manifest_path"):
            with self.subTest(field=field):
                fixture = self.fixture()
                first = fixture.produce_calendar(days={"2026-08-31": True})[0]
                path = Path(first.snapshot[field])
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises(ValueError):
                    fixture.range_store.read_verified(first.task["id"])
                with self.assertRaises(ValueError):
                    first.require_current()

    def test_orphan_receipt_and_extra_producer_fail_closed(self):
        for tamper in ("DELETE FROM formal_range_normalization_receipt", "UPDATE formal_range_attempt SET worker_id='other'"):
            with self.subTest(tamper=tamper):
                fixture = self.fixture()
                first = fixture.produce_calendar(days={"2026-08-31": True})[0]
                with closing(sqlite3.connect(fixture.store.db_path)) as connection:
                    connection.execute(tamper)
                    connection.commit()
                with self.assertRaises(ValueError):
                    fixture.range_store.read_verified(first.task["id"])

    def test_later_refresh_same_content_coexists_without_lexical_generation_order(self):
        fixture = self.fixture()
        first = fixture.produce_calendar(days={"2026-08-31": True}, generation="z-old")[0]
        second = fixture.produce_calendar(days={"2026-08-31": True}, generation="a-new")[0]
        self.assertNotEqual(first.task["id"], second.task["id"])
        self.assertEqual(first.snapshot["content_sha256"], second.snapshot["content_sha256"])
        first.require_current()
        second.require_current()
        history = fixture.range_store.read_history(first.task["id"])
        self.assertEqual(history.observation_hash, first.observation_hash)
        with self.assertRaises(ValueError):
            history.require_current()

    def test_current_source_correction_invalidates_old_observation_and_continuation(self):
        from tests.test_formal_range_source import document_wire
        fixture = self.fixture()
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        request, task = self.task(fixture, "g2")
        fixture.reply(document_wire(request, source_updated_at_utc="2026-08-31T05:00:00+00:00", upstream_generation="correction"))
        lease = fixture.range_store.lease_next("worker", lease_seconds=600)
        second = fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=fixture.source.fetch_verified(request))
        self.assertEqual(fixture.range_store.select_current(request.request_fingerprint).observation_hash, second.observation_hash)
        with self.assertRaises(ValueError):
            first.require_current()
        with self.assertRaises(ValueError):
            fixture.source.previous_calendar_request(first)
        self.assertEqual(fixture.range_store.read_history(first.task["id"]).document["rows"][0]["is_open"], True)

    def test_same_leading_version_different_content_is_ambiguous(self):
        fixture = self.fixture()
        first = fixture.produce_calendar(days={"2026-08-31": True}, generation="g1")[0]
        fixture.produce_calendar(days={"2026-08-31": False}, generation="g2")
        with self.assertRaises(ValueError):
            fixture.range_store.select_current(first.request["request_fingerprint"] if "request_fingerprint" in first.request else fixture.source.first_calendar_request(FREEZE).request_fingerprint)

    def test_both_import_orders_and_no_exposed_authority_builder(self):
        for first in ("formal_range_source", "formal_range_store"):
            script = f"""
import importlib
importlib.import_module('ashare_pipeline.{first}')
from ashare_pipeline import formal_range_source as source, formal_range_store as store
assert source.RangeObservation is store.RangeObservation
assert not hasattr(store, '_build_range_store_type')
assert not hasattr(source, '_mint_first_calendar_request')
assert not hasattr(source, '_mint_fetch')
assert not hasattr(source, '_build_source_type')
try:
    store.RangeObservation()
except ValueError:
    pass
else:
    raise AssertionError('unbacked observation constructed')
"""
            result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_concurrent_leasing_has_one_winner(self):
        fixture = self.fixture()
        _, task = self.task(fixture)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda worker: fixture.range_store.lease_next(worker, lease_seconds=600), ("a", "b")))
        winners = [result for result in results if result is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]["id"], task["id"])

    def test_lease_supplies_authenticated_request_and_binding_to_worker(self):
        fixture = self.fixture()
        request, task = self.task(fixture)
        lease = fixture.range_store.lease_next("worker", lease_seconds=600)
        self.assertIn("request", lease)
        self.assertIn("binding", lease)
        source = fixture.source_factory(lease["binding"])
        from tests.test_formal_range_source import document_wire
        fixture.reply(document_wire(lease["request"]))
        result = fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=source.fetch_verified(lease["request"]))
        self.assertEqual(result.request["end_date"], "2026-08-31")

    def test_receipt_failure_rolls_back_snapshot_and_completion_but_keeps_files(self):
        from tests.test_formal_range_source import document_wire
        fixture = self.fixture()
        request, task = self.task(fixture)
        fixture.reply(document_wire(request))
        lease = fixture.range_store.lease_next("worker", lease_seconds=600)
        fetch = fixture.source.fetch_verified(request)
        with closing(sqlite3.connect(fixture.store.db_path)) as connection:
            connection.execute("CREATE TRIGGER fixture_interrupt BEFORE INSERT ON formal_range_normalization_receipt BEGIN SELECT RAISE(ABORT, 'fixture interrupt'); END")
            connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=fetch)
        with closing(sqlite3.connect(fixture.store.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM formal_range_snapshot").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT status FROM formal_range_task").fetchone()[0], "leased")
            connection.execute("DROP TRIGGER fixture_interrupt")
            connection.commit()
        self.assertTrue(list(fixture.root.rglob("*.raw")))
        verified = fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=fetch)
        with self.assertRaises(ValueError):
            fixture.range_store.persist(task["id"], "other", lease["attempt_id"], fetch=fetch)
        self.assertEqual(verified.receipt["attempt_id"], lease["attempt_id"])

    def test_reopen_replays_authenticated_page_chain_and_history_cannot_continue(self):
        from ashare_pipeline.formal_range_store import FormalRangeStore
        def paginate(documents):
            for config in documents["source"]["range_configs"]:
                if config["kind"] == "calendar_range":
                    config.update(pagination="numbered_pages_v1", max_pages=3)
        fixture = self.fixture(mutate=paginate)
        observations = fixture.produce_calendar(days={"2026-08-30": False, "2026-08-31": True})
        self.assertEqual([value.document["page_index"] for value in observations], [1, 2])
        reopened = FormalRangeStore(fixture.store, root=fixture.root, signature_verifier=fixture.verifier,
            source_factory=fixture.source_factory)
        replay = reopened.read_verified(observations[1].task["id"])
        self.assertEqual(replay.observation_hash, observations[1].observation_hash)
        historical = reopened.read_history(observations[0].task["id"])
        with self.assertRaises(ValueError):
            fixture.source.next_page(historical)
        previous = fixture.source.previous_calendar_request(replay)
        self.assertEqual(previous.end_date, "2025-07-27")

    def test_uninitialized_copied_and_redirected_state_store_are_rejected(self):
        from ashare_pipeline.formal_range_store import FormalRangeStore
        from ashare_pipeline.state_store import StateStore
        fixture = self.fixture()
        for state in (object.__new__(StateStore), copy.copy(fixture.store)):
            with self.assertRaises(ValueError):
                FormalRangeStore(state, root=fixture.root, signature_verifier=fixture.verifier, source_factory=fixture.source_factory)
        request, task = self.task(fixture)
        fixture.store.db_path = fixture.root / "different.sqlite"
        with self.assertRaises(ValueError):
            fixture.range_store.lease_next("worker", lease_seconds=60)

    def test_raw_file_removed_after_commit_is_not_reusable(self):
        fixture = self.fixture()
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        Path(first.snapshot["content_path"]).unlink()
        with self.assertRaises(ValueError):
            fixture.range_store.read_history(first.task["id"])
        with self.assertRaises(ValueError):
            fixture.range_store.enqueue(fixture.source.first_calendar_request(FREEZE), refresh_generation="g1")

    def test_attempt_payload_boolean_does_not_equal_integer(self):
        import hashlib
        import json
        fixture = self.fixture()
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        with closing(sqlite3.connect(fixture.store.db_path)) as connection:
            raw = connection.execute("SELECT payload_json FROM formal_range_attempt").fetchone()[0]
            payload = json.loads(raw)
            payload["attempt_no"] = True
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            connection.execute("UPDATE formal_range_attempt SET payload_json=?, payload_hash=?", (raw, hashlib.sha256(raw.encode()).hexdigest()))
            connection.commit()
        with self.assertRaises(ValueError):
            fixture.range_store.read_verified(first.task["id"])

    def test_public_state_store_alias_before_import_does_not_replace_genuine_type(self):
        script = """
import tempfile
from pathlib import Path
from ashare_pipeline import state_store as state
Real = state.StateStore
class Fake:
    pass
state.StateStore = Fake
from ashare_pipeline.formal_range_store import FormalRangeStore
class Verifier:
    def verify(self, *args):
        return False
with tempfile.TemporaryDirectory() as directory:
    store = Real(Path(directory) / 'state.sqlite')
    store.initialize()
    FormalRangeStore(store, root=directory, signature_verifier=Verifier(), source_factory=lambda b: None)
"""
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_continuation_cannot_be_enqueued_under_a_different_raw_root(self):
        from ashare_pipeline.formal_range_store import FormalRangeStore
        fixture = self.fixture()
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        previous = fixture.source.previous_calendar_request(first)
        other = FormalRangeStore(fixture.store, root=fixture.root / "other",
            signature_verifier=fixture.verifier, source_factory=fixture.source_factory)
        with self.assertRaises(ValueError):
            other.enqueue(previous, refresh_generation="g1")

    def test_parent_correction_revokes_child_current_but_preserves_history(self):
        from tests.test_formal_range_source import document_wire
        fixture = self.fixture()
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        child_request = fixture.source.previous_calendar_request(first)
        task = fixture.range_store.enqueue(child_request, refresh_generation="g1")
        fixture.reply(document_wire(child_request))
        lease = fixture.range_store.lease_next("worker", lease_seconds=3600)
        child = fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=fixture.source.fetch_verified(child_request))
        request, correction_task = self.task(fixture, "g2")
        fixture.reply(document_wire(request, source_updated_at_utc="2026-08-31T05:00:00+00:00", upstream_generation="correction"))
        correction_lease = fixture.range_store.lease_next("worker", lease_seconds=3600)
        fixture.range_store.persist(correction_task["id"], "worker", correction_lease["attempt_id"], fetch=fixture.source.fetch_verified(request))
        with self.assertRaises(ValueError):
            child.require_current()
        with self.assertRaises(ValueError):
            fixture.source.fetch_verified(child_request)
        self.assertEqual(fixture.range_store.read_history(task["id"]).observation_hash, child.observation_hash)

    def test_correction_during_selection_is_integrity_failure(self):
        import json
        from tests.test_formal_range_source import document_wire

        class InterleavingParser:
            action = None

            def parse(self, raw_bytes, *, request, config):
                action, self.action = self.action, None
                if action is not None:
                    action()
                return json.loads(raw_bytes)

        class Normalizer:
            def normalize(self, value, *, request, config):
                return value

        parser = InterleavingParser()
        key = ("fixture-range-parser", "fixture-range-v1", "fixture-range-map-v1", "fixture-range-normalizer-v1", "formal-range-request-v1")
        fixture = self.fixture(implementations={key: (parser, Normalizer())})
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        request, task = self.task(fixture, "g2")
        fixture.reply(document_wire(request, source_updated_at_utc="2026-08-31T05:00:00+00:00", upstream_generation="correction"))
        lease = fixture.range_store.lease_next("worker", lease_seconds=3600)
        fetch = fixture.source.fetch_verified(request)
        parser.action = lambda: fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=fetch)
        with self.assertRaises(ValueError):
            fixture.range_store.select_current(first.task["request_fingerprint"])
        self.assertEqual(fixture.range_store.select_current(first.task["request_fingerprint"]).task["id"], task["id"])

    def test_parent_correction_during_persist_rolls_back_child_receipt(self):
        import json
        from tests.test_formal_range_source import document_wire

        class InterleavingParser:
            action = None
            target = None

            def parse(self, raw_bytes, *, request, config):
                if self.action is not None and request["end_date"] == self.target:
                    action, self.action = self.action, None
                    action()
                return json.loads(raw_bytes)

        class Normalizer:
            def normalize(self, value, *, request, config):
                return value

        parser = InterleavingParser()
        key = ("fixture-range-parser", "fixture-range-v1", "fixture-range-map-v1", "fixture-range-normalizer-v1", "formal-range-request-v1")
        fixture = self.fixture(implementations={key: (parser, Normalizer())})
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        child_request = fixture.source.previous_calendar_request(first)
        child_task = fixture.range_store.enqueue(child_request, refresh_generation="g1")
        fixture.reply(document_wire(child_request))
        child_lease = fixture.range_store.lease_next("worker", lease_seconds=3600)
        child_fetch = fixture.source.fetch_verified(child_request)
        request, correction = self.task(fixture, "g2")
        fixture.reply(document_wire(request, source_updated_at_utc="2026-08-31T05:00:00+00:00", upstream_generation="correction"))
        correction_lease = fixture.range_store.lease_next("worker", lease_seconds=3600)
        correction_fetch = fixture.source.fetch_verified(request)
        parser.target = child_request.end_date
        parser.action = lambda: fixture.range_store.persist(correction["id"], "worker", correction_lease["attempt_id"], fetch=correction_fetch)
        with self.assertRaises(ValueError):
            fixture.range_store.persist(child_task["id"], "worker", child_lease["attempt_id"], fetch=child_fetch)
        with closing(sqlite3.connect(fixture.store.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT status FROM formal_range_task WHERE id=?", (child_task["id"],)).fetchone()[0], "leased")
            self.assertEqual(connection.execute("SELECT count(*) FROM formal_range_snapshot WHERE task_id=?", (child_task["id"],)).fetchone()[0], 0)

    def test_parent_correction_during_fetch_rejects_standalone_continuation(self):
        import json
        from tests.test_formal_range_source import document_wire

        class InterleavingParser:
            action = None
            target = None

            def parse(self, raw_bytes, *, request, config):
                if self.action is not None and request["end_date"] == self.target:
                    action, self.action = self.action, None
                    action()
                return json.loads(raw_bytes)

        class Normalizer:
            def normalize(self, value, *, request, config):
                return value

        parser = InterleavingParser()
        key = ("fixture-range-parser", "fixture-range-v1", "fixture-range-map-v1", "fixture-range-normalizer-v1", "formal-range-request-v1")
        fixture = self.fixture(implementations={key: (parser, Normalizer())})
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        child_request = fixture.source.previous_calendar_request(first)
        request, correction = self.task(fixture, "g2")
        fixture.reply(document_wire(request, source_updated_at_utc="2026-08-31T05:00:00+00:00", upstream_generation="correction"))
        correction_lease = fixture.range_store.lease_next("worker", lease_seconds=3600)
        correction_fetch = fixture.source.fetch_verified(request)
        fixture.reply(document_wire(child_request))
        parser.target = child_request.end_date
        parser.action = lambda: fixture.range_store.persist(correction["id"], "worker", correction_lease["attempt_id"], fetch=correction_fetch)
        with self.assertRaises(ValueError):
            fixture.source.fetch_verified(child_request)

    def test_fetch_verifier_alias_cannot_authorize_an_unregistered_clone(self):
        from tests.test_formal_range_source import document_wire
        fixture = self.fixture()
        request, task = self.task(fixture)
        fixture.reply(document_wire(request))
        lease = fixture.range_store.lease_next("worker", lease_seconds=3600)
        fetch = fixture.source.fetch_verified(request)
        forged = object.__new__(type(fetch))
        for field in type(fetch).__slots__[:-1]:
            object.__setattr__(forged, field, getattr(fetch, field))
        with patch.object(type(fetch), "_require", lambda self: None):
            with self.assertRaises(ValueError):
                fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=forged)
        def altered_checker(value):
            raise AssertionError("consumer dispatched a replaced fetch checker")
        with patch.object(type(fetch), "_require", altered_checker):
            with self.assertRaises(ValueError):
                fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=forged)
        persisted = fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=fetch)
        self.assertEqual(persisted.snapshot["content_sha256"], fetch.content_sha256)

    def test_observation_proof_methods_and_lookup_cannot_be_shadowed(self):
        from ashare_pipeline.formal_range_store import RangeObservation
        for name, replacement in (("require_current", lambda self: None),
                                  ("to_dict", lambda self: {}),
                                  ("__getattr__", lambda self, name: None),
                                  ("__getattribute__", object.__getattribute__)):
            original = getattr(RangeObservation, name)
            try:
                with self.subTest(name=name), self.assertRaises(TypeError):
                    setattr(RangeObservation, name, replacement)
            finally:
                if getattr(RangeObservation, name) is not original:
                    setattr(RangeObservation, name, original)
        with self.assertRaises(TypeError):
            type("ForgedObservation", (RangeObservation,), {})
        forged = object.__new__(RangeObservation)
        with self.assertRaises(ValueError):
            forged.require_current()
        with self.assertRaises((TypeError, AttributeError)):
            forged.require_current = lambda: None
        with self.assertRaises(TypeError):
            copy.copy(forged)
        class Replacement:
            __slots__ = ("__weakref__",)
            def require_current(self):
                return None
        with self.assertRaises((TypeError, AttributeError)):
            forged.__class__ = Replacement

    def test_original_observation_authority_survives_public_alias_replacement(self):
        from ashare_pipeline import formal_range_source as source
        self.assertTrue(hasattr(source, "_range_observation_authority"))
        original, require_current, read_wire = source._range_observation_authority()
        class Fake:
            def require_current(self):
                return None
            def to_dict(self):
                return {"observation_hash": "f" * 64}
        with patch.object(source, "RangeObservation", Fake):
            self.assertIs(source._range_observation_authority()[0], original)
            with self.assertRaises(ValueError):
                require_current(Fake())
            with self.assertRaises(ValueError):
                read_wire(Fake())

    def test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence(self):
        import json
        from ashare_pipeline.formal_sources import FormalTerminalSourceError
        from tests.test_formal_range_source import document_wire

        class InterleavingParser:
            action = None

            def parse(self, raw_bytes, *, request, config):
                action, self.action = self.action, None
                if action is not None:
                    action()
                return json.loads(raw_bytes)

        class Normalizer:
            def normalize(self, value, *, request, config):
                return value

        parser = InterleavingParser()
        key = ("fixture-range-parser", "fixture-range-v1", "fixture-range-map-v1", "fixture-range-normalizer-v1", "formal-range-request-v1")
        fixture = self.fixture(implementations={key: (parser, Normalizer())})
        request, task = self.task(fixture)
        fixture.reply(document_wire(request))
        lease = fixture.range_store.lease_next("worker", lease_seconds=3600)
        fetch = fixture.source.fetch_verified(request)
        original_bytes, original_hash = fetch.raw_bytes, fetch.content_sha256
        parser.action = lambda: object.__setattr__(fetch, "raw_bytes", original_bytes + b" ")
        try:
            fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=fetch)
        except (ValueError, FormalTerminalSourceError):
            pass  # A clean pre-commit rejection is also safe.
        with closing(sqlite3.connect(fixture.store.db_path)) as connection:
            status = connection.execute("SELECT status FROM formal_range_task WHERE id=?", (task["id"],)).fetchone()[0]
            snapshots = connection.execute("SELECT content_sha256,content_path FROM formal_range_snapshot WHERE task_id=?", (task["id"],)).fetchall()
        if status == "verified":
            self.assertEqual(snapshots[0][0], original_hash)
            self.assertEqual(Path(snapshots[0][1]).read_bytes(), original_bytes)
            self.assertEqual(fixture.range_store.read_verified(task["id"]).snapshot["content_sha256"], original_hash)
        else:
            self.assertEqual(status, "leased")
            self.assertEqual(snapshots, [])

    def test_verified_replay_retains_one_producer(self):
        from tests import formal_range_fixtures
        self.assertTrue(hasattr(formal_range_fixtures, "RangeStoreFixture"),
                        "the genuine enqueue/lease/fetch/persist fixture is absent")
        fixture = formal_range_fixtures.RangeStoreFixture()
        self.addCleanup(fixture.close)
        first = fixture.produce_calendar(days={"2026-08-31": True})[0]
        replay = fixture.range_store.read_verified(first.task["id"])
        self.assertEqual(first.observation_hash, replay.observation_hash)
        self.assertEqual(first.receipt["attempt_id"], replay.receipt["attempt_id"])
