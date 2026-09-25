"""Full signed policy population and restart paths with temporary raw evidence."""

from contextlib import closing
from pathlib import Path
import socket
import sqlite3
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
from ashare_pipeline.formal_range_contract import load_policy_range_bindings
from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
from tests.formal_range_fixtures import RangeWorkerFixture, _CapturingRangeTransport
from tests.test_formal_range_source import document_wire
from tests.test_formal_scoring_registry import canonical


TEMPLATES = {
    "BJ430001": "general_nonfinancial",
    "SH600000": "bank",
    "SH600001": "bank",
    "SH600002": "broker",
    "SH600003": "insurance",
    "SZ000001": "real_estate",
}
UNKNOWN = "SZ000002"


def numbered(documents):
    for config in documents["source"]["range_configs"]:
        config.update(pagination="numbered_pages_v1", max_pages=2)


class FormalPolicyIntegrationTests(unittest.TestCase):
    def policy_fixture(self, **kwargs):
        fixture = PolicyRuntimeFixture(range_enabled=True, **kwargs)
        self.addCleanup(fixture.close)
        self.assertTrue(fixture.db_path.resolve().is_relative_to(fixture.root.resolve()))
        self.assertEqual(fixture.root.resolve(), Path(fixture.tempdir.name).resolve())
        self.assertTrue(fixture.raw.root.resolve().is_relative_to(fixture.root.resolve()))
        self.assertIs(type(fixture.transport), _CapturingRangeTransport)
        return fixture

    def worker_fixture(self):
        fixture = RangeWorkerFixture(mutate=numbered)
        self.addCleanup(fixture.close)
        self.assertTrue(fixture.store.db_path.resolve().is_relative_to(fixture.root.resolve()))
        self.assertEqual(fixture.root.resolve(), Path(fixture.temp.name).resolve())
        self.assertIs(type(fixture.transport), _CapturingRangeTransport)
        return fixture

    def test_complete_universe_all_templates_pending_and_veto(self):
        fixture = self.policy_fixture(templates=TEMPLATES, extra_members=(UNKNOWN,),
                                      noncyclic_ids=("SH600001",))
        self.assertEqual(tuple(sorted((*TEMPLATES, UNKNOWN))),
                         tuple(member.security_id for member in fixture.frozen.members))
        with patch.object(socket, "create_connection", side_effect=AssertionError("real HTTP forbidden")):
            fixture.populate_policy_evidence(skip_financial=tuple(
                sid for sid in TEMPLATES if sid != "BJ430001"),
                security_state_overrides={"SH600002": {"is_st": True}})
            batch = fixture.build_policy_batch()
        bindings = load_policy_range_bindings(fixture.bundle, scoring_registry=fixture.scoring,
                                               policy_registry=fixture.policy_registry)
        bank = bindings.for_rule("bank_no_effective_trade_20d", "SH")
        broker = bindings.for_rule("broker_no_effective_trade_20d", "SH")
        bank_request = fixture.source_factory(bank).first_calendar_request("2026-08-31T07:00:00+00:00")
        broker_request = fixture.source_factory(broker).first_calendar_request("2026-08-31T07:00:00+00:00")
        self.assertEqual(bank_request.request_fingerprint, broker_request.request_fingerprint)
        with closing(sqlite3.connect(fixture.db_path)) as connection:
            fingerprint = bank_request.request_fingerprint
            self.assertEqual(connection.execute("SELECT count(*) FROM formal_range_task WHERE request_fingerprint=?",
                                                (fingerprint,)).fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM formal_range_snapshot WHERE request_fingerprint=?",
                                                (fingerprint,)).fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM formal_range_normalization_receipt WHERE task_id IN "
                                                "(SELECT id FROM formal_range_task WHERE request_fingerprint=?)",
                                                (fingerprint,)).fetchone()[0], 1)
        calendar_calls = [call for call in fixture.transport.calls if "/range-calendar.json" in call.url
                          and "exchange=SH" in call.url]
        self.assertEqual(len(calendar_calls), 1)
        market = FormalPolicyMarketRepository(fixture.range_store)
        bank_proof = market.select_calendar(bank, "2026-08-31T07:00:00+00:00").coverage
        broker_proof = market.select_calendar(broker, "2026-08-31T07:00:00+00:00").coverage
        self.assertIsNotNone(bank_proof)
        self.assertIsNotNone(broker_proof)
        self.assertNotEqual(bank_proof.binding_hash, broker_proof.binding_hash)
        self.assertNotEqual(bank_proof.coverage_hash, broker_proof.coverage_hash)
        self.assertEqual(bank_proof.lineage, broker_proof.lineage)
        with self.assertRaises(ValueError):
            fixture.range_store.resolve_planning_binding(broker)[1].market_requests(
                "SH600002", calendar_coverage=bank_proof)
        batch.require_verified()
        wire = batch.to_dict()
        expected = tuple(sorted((*TEMPLATES, UNKNOWN)))
        self.assertEqual(tuple(wire["security_ids"]), expected)
        self.assertEqual(len(wire["results"]), 7)
        by_id = {item["security_id"]: item for item in wire["results"]}
        self.assertEqual(set(by_id), set(expected))
        for sid, template in TEMPLATES.items():
            self.assertTrue(by_id[sid]["decisions"])
            self.assertTrue(all(d["template_id"] == template for d in by_id[sid]["decisions"]))
        self.assertEqual(by_id["BJ430001"]["evidence_state"], "complete")
        self.assertEqual(by_id[UNKNOWN]["decisions"], [])
        self.assertEqual(by_id[UNKNOWN]["evidence_state"], "pending_evidence")
        self.assertTrue(any(p["code"] == "applicability_unresolved"
                            for p in by_id[UNKNOWN]["pending_requirements"]))
        noncyclic = next(d for d in by_id["SH600001"]["decisions"] if d["semantic_id"] == "cyclic_top")
        self.assertEqual(noncyclic["evaluation_state"], "not_applicable")
        self.assertFalse(any("annual" in p.get("code", "") for p in noncyclic["pending_requirements"]))
        vetoed = by_id["SH600002"]
        self.assertEqual(next(d for d in vetoed["decisions"] if d["semantic_id"] == "st")["evaluation_state"], "matched")
        self.assertTrue(vetoed["pending_requirements"])
        self.assertNotIn("strong_pool", wire)
        self.assertNotIn("wait_pool", wire)
        self.assertNotIn("final_scores", wire)
        for result in wire["results"]:
            self.assertNotIn("eligible", result)
            self.assertNotIn("final_score", result)

    def test_rebuild_is_identical_then_append_only_correction_changes_identity(self):
        fixture = self.policy_fixture(cyclic=False)
        fixture.put_industry("SH600000")
        state = dict(is_st=False, is_star_st=False, listing_status="listed",
                     forced_delist_risk=False, suspended=False)
        _, old_ref = fixture.put_policy_context("SH600000", "security_state", state)
        old_path = Path(old_ref.content_path)
        old_bytes = old_path.read_bytes()
        with patch.object(socket, "create_connection", side_effect=AssertionError("real HTTP forbidden")):
            selection = fixture.state_selection("SH600000")
            first = fixture.build_policy_batch()
            second = fixture.build_policy_batch()
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(first.batch_hash, second.batch_hash)
        _, new_ref = fixture.put_policy_context("SH600000", "security_state",
            dict(state, is_st=True), generation="g2")
        with patch.object(socket, "create_connection", side_effect=AssertionError("real HTTP forbidden")):
            corrected = fixture.build_policy_batch()
        self.assertNotEqual(first.batch_hash, corrected.batch_hash)
        self.assertNotEqual(first.canonical_bytes(), corrected.canonical_bytes())
        self.assertEqual(old_path.read_bytes(), old_bytes)
        self.assertNotEqual(old_ref.snapshot_id, new_ref.snapshot_id)
        with closing(sqlite3.connect(fixture.db_path)) as connection:
            self.assertTrue(connection.execute("SELECT 1 FROM formal_source_snapshot WHERE id=?",
                                               (old_ref.snapshot_id,)).fetchone())
            self.assertTrue(connection.execute("SELECT 1 FROM formal_source_snapshot WHERE id=?",
                                               (new_ref.snapshot_id,)).fetchone())
        with self.assertRaises(ValueError):
            selection.recheck()
        first.require_verified()  # Historical publication remains auditable.

    def test_restart_reuses_authenticated_page_without_transport_duplicate(self):
        clock = patch("ashare_pipeline.formal_range_store._utc_now",
                      return_value="2026-09-01T00:00:00+00:00")
        clock.start()
        self.addCleanup(clock.stop)
        crashed = self.worker_fixture()
        control = self.worker_fixture()
        with patch.object(socket, "create_connection", side_effect=AssertionError("real HTTP forbidden")):
            first_request = crashed.enqueue_calendar()
            first_wire = document_wire(first_request, page_count=2, record_count=2,
                pagination_evidence="source_declared_numbered_pages_v1")
            crashed.reply(first_wire)
            lease = crashed.range_store.lease_next("crashed", lease_seconds=60)
            first = crashed.range_store.persist(lease["id"], "crashed", lease["attempt_id"],
                                                fetch=crashed.source.fetch_verified(lease["request"]))
            first_raw = Path(first.snapshot["content_path"])
            first_bytes = first_raw.read_bytes()
            self.assertEqual(len(crashed.transport.calls), 1)
            crashed.restart_worker()
            resumed = crashed.worker.resume(first_request, refresh_generation="g1")
            self.assertEqual(resumed["state"], "pending")
            self.assertEqual(len(crashed.transport.calls), 1)
            second_request = crashed.source.next_page(crashed.range_store.read_verified(first.task["id"]))
            second_wire = document_wire(second_request, page_index=2, page_count=2,
                record_count=2, pagination_evidence="source_declared_numbered_pages_v1")
            crashed.reply(second_wire)
            self.assertEqual(crashed.worker.run_once()["state"], "verified")
            self.assertEqual(crashed.worker.resume(first_request, refresh_generation="g1")["state"], "verified")
            self.assertEqual(len(crashed.transport.calls), 2)

            control_request = control.enqueue_calendar()
            control.reply(document_wire(control_request, page_count=2, record_count=2,
                pagination_evidence="source_declared_numbered_pages_v1"))
            self.assertEqual(control.worker.run_once()["state"], "verified")
            control_second = control.source.next_page(control.range_store.select_current(control_request.request_fingerprint))
            control.reply(document_wire(control_second, page_index=2, page_count=2,
                record_count=2, pagination_evidence="source_declared_numbered_pages_v1"))
            self.assertEqual(control.worker.run_once()["state"], "verified")
        recovered = crashed.range_store.select_current(second_request.request_fingerprint)
        uninterrupted = control.range_store.select_current(control_second.request_fingerprint)
        # Full proof hashes include temporary raw paths and task/worker identity.
        # Compare the canonical source observation/result carried by each proof.
        self.assertEqual(canonical(dict(request=recovered.to_dict()["request"],
                                        document=recovered.to_dict()["document"])),
                         canonical(dict(request=uninterrupted.to_dict()["request"],
                                        document=uninterrupted.to_dict()["document"])))
        self.assertEqual(Path(recovered.snapshot["content_path"]).read_bytes(),
                         Path(uninterrupted.snapshot["content_path"]).read_bytes())
        self.assertEqual(first_raw.read_bytes(), first_bytes)
        with closing(sqlite3.connect(crashed.store.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM formal_range_normalization_receipt").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM formal_range_attempt").fetchone()[0], 2)
