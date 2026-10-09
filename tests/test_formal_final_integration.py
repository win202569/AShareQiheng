"""20/23 member producer-backed, single-root D1 -> D2 -> D3 -> V8 acceptance."""

import atexit
import hashlib
import inspect
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

from ashare_pipeline.formal_coverage_manifest import FormalCoverageAuditor
from tests.formal_final_scoring_fixtures import FinalScoringFixture, FOCAL
from tests.formal_metric_fixtures import FREEZE
from tests.test_formal_final_runner import (
    configured_runner, coverage_for, run_arguments, runner_module,
)


_CHAINS = {}


def complete_score_history(fixture, ids):
    """Complete histories and consensus through the same real evidence producers."""
    for sid in ids:
        if sid == FOCAL:
            continue
        generation = "task11-consensus-" + sid
        request = fixture.resolver.resolve(context_kind="consensus_snapshot",
            scope_key="fixture-consensus", security_id=sid,
            as_of_utc=FREEZE,
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
            upstream_generation=generation, expected_purpose=fixture.purpose)
        fixture.put_context(request, {"coverage_status": "covered", "estimates": [
            {"period": "FY2026", "metric": "profit", "value": 1}]}, False, generation)
        for year in range(2021, 2026):
            fixture.put_financial(sid, {"history": 1}, generation=f"task11-history-{year}",
                period_end=f"{year}-12-31", publish=False)
        for year in (2024, 2025, 2026):
            for kind, end in (("Q1", "03-31"), ("H1", "06-30"), ("Q3", "09-30")):
                if year == 2026 and kind == "Q3":
                    continue
                fixture.put_financial(sid, {"history": 1}, generation=f"task11-history-{year}-{kind}",
                    period_end=f"{year}-{end}", period_kind=kind, publish=False)
        fixture.publish_current(sid)
        fixture.valuation_feature_bundles[sid] = fixture.persist_features(sid)


def official_context_coverage_configuration(fixture):
    """Build signed test configuration, not a coverage proof."""
    from ashare_pipeline.state_store import SCHEMA_VERSION
    from tests.test_formal_coverage_guards import canonical, db_generation, digest
    f = fixture
    descriptors, requirements = {}, []
    for member in f.frozen.members:
        selector = dict(owner="formal_context_repository", domain="context",
            security_id=member.security_id, exchange=member.exchange,
            period_or_window=FREEZE, context_kind="industry_snapshot",
            scope_key="fixture-industry", as_of_utc=FREEZE)
        selector_hash = digest(selector)
        descriptors[selector_hash] = selector
        requirements.append(dict(frozen_input_hash=f.frozen.frozen_input_hash,
            security_id=member.security_id, domain="context", selector_hash=selector_hash,
            exchange=member.exchange, period_or_window=FREEZE, expected_units=[]))
    wire = dict(schema_version="formal-coverage-contract-v1", purpose="official",
        approval_id=f.bundle.manifest.approval_id, signing_identity=f.bundle.manifest.key_id,
        registry_manifest_hash=f.bundle.manifest.manifest_hash, frozen_input_hash=f.frozen.frozen_input_hash,
        requirements=requirements, domain_owners={"context": "formal_context_repository"},
        selector_descriptors=descriptors, expected_schema_version=SCHEMA_VERSION,
        report_period="2025", query_version="task11-context-v1")
    raw = canonical(wire)
    status_path = f.root / "task11-coverage-status.json"
    status_path.write_text(json.dumps(dict(generated_at_utc="2026-09-01T00:00:00+00:00",
        schema_version=SCHEMA_VERSION, db_sha256=hashlib.sha256(f.db_path.read_bytes()).hexdigest(),
        db_generation_hash=digest(db_generation(f.db_path)),
        schema_versions=list(range(2, SCHEMA_VERSION + 1)))), encoding="utf-8")
    return requirements, dict(canonical_json=raw, signature=f.verifier.sign(raw),
                             key_id=f.bundle.manifest.key_id), status_path


def official_context_coverage(fixture):
    """Authenticate a signed member-specific context catalog and live V8 DB."""
    from ashare_pipeline.formal_registry_manifest import FormalRegistryBundleLoader
    f = fixture
    requirements, contract, status_path = official_context_coverage_configuration(f)
    return FormalCoverageAuditor().audit(requirements,
        production_contract=contract,
        contract_verifier=f.verifier, registry_bundle=f.bundle,
        registry_loader=FormalRegistryBundleLoader(f.store, f.verifier),
        snapshot_repository=f.snapshots, context_repository=f.context,
        frozen_universe=f.frozen, workspace_root=Path(__file__).resolve().parents[1],
        db_path=f.db_path, status_path=status_path)


def genuine_chain(case, count):
    if count not in _CHAINS:
        module = runner_module(case)
        fixture = FinalScoringFixture(peer_count=count, purpose="test",
            consensus_no_coverage=True, veto_ids=("SH600000",),
            prohibition_ids=("SH600001",))
        atexit.register(fixture.close)
        fixture.populate_final_inputs()
        complete_score_history(fixture, ("SH600000", "SH600001"))
        runner, repository = configured_runner(module, fixture)
        coverage = coverage_for(fixture)
        receipt = runner.run_preview(**run_arguments(fixture, coverage))
        _CHAINS[count] = fixture, runner, repository, coverage, receipt
    return _CHAINS[count]


class GenuineFullChainTests(unittest.TestCase):
    def setUp(self):
        self.module = runner_module(self)

    def test_20_and_23_genuine_members_close_every_hash_and_pool_bound(self):
        for count in (20, 23):
            with self.subTest(count=count):
                fixture, runner, repository, coverage, receipt = genuine_chain(self, count)
                snapshot = repository.get_run(receipt.run_id)
                wires = [json.loads(snapshot.artifacts[key]) for key in
                    ("score_input_batch", "scorecard_batch", "eligibility_batch", "pool_selection_batch")]
                inputs, scores, eligibility, pools = wires
                ids = tuple(sorted(fixture.templates))
                self.assertEqual(len(fixture.bundle.roles), 10)
                self.assertEqual(snapshot.security_ids, ids)
                self.assertEqual(snapshot.coverage_manifest_hash, coverage.manifest_hash)
                for key in ("registry_manifest_hash", "frozen_input_hash", "universe_hash"):
                    self.assertEqual(inputs[key], getattr(snapshot, key))
                    self.assertEqual(scores[key], inputs[key])
                self.assertEqual(inputs["registry_manifest_hash"], fixture.bundle.manifest.manifest_hash)
                self.assertEqual(inputs["frozen_input_hash"], fixture.frozen.frozen_input_hash)
                for kind, raw in snapshot.artifacts.items():
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), snapshot.artifact_hashes[kind])
                self.assertEqual(scores["source_batch_hash"], inputs["batch_hash"])
                self.assertEqual(eligibility["source_batch_hash"], inputs["batch_hash"])
                self.assertEqual(eligibility["score_batch_hash"], scores["batch_hash"])
                self.assertEqual(pools["source_batch_hash"], eligibility["batch_hash"])
                rows = {row["security_id"]: row for row in eligibility["eligibilities"]}
                self.assertEqual(tuple(rows), ids)
                self.assertEqual(len(rows), count)
                self.assertNotIn("out_of_scope", [row["state"] for row in rows.values()])
                self.assertTrue(any(row["state"] == "pending_evidence" for row in rows.values()))
                self.assertTrue(any(row["state"] == "formal_scored" for row in rows.values()))
                veto = receipt.input_batch.input_for("SH600000")
                veto_card = receipt.score_batch.card_for("SH600000")
                self.assertTrue(rows["SH600000"]["hard_veto"])
                if count == 20:
                    self.assertEqual(veto.status, "pending_evidence")
                    self.assertIsNone(veto_card)
                    self.assertEqual(rows["SH600000"]["state"], "pending_evidence")
                    self.assertTrue(any("T.expectation_change:peer_count_below_20" in reason
                                        for reason in veto.reasons))
                else:
                    self.assertEqual(veto.status, "ready")
                    self.assertIsNotNone(veto_card)
                    self.assertEqual(rows["SH600000"]["state"], "pool_vetoed")
                self.assertFalse(rows[FOCAL]["strong_prohibited"])
                self.assertTrue(rows[FOCAL]["wait_prohibited"])
                self.assertFalse(set(pools["strong_security_ids"]) & set(pools["wait_security_ids"]))
                for pool, capacity, cap in (("strong", 20, 4), ("wait", 50, 10)):
                    selected = pools[pool + "_security_ids"]
                    self.assertLessEqual(len(selected), capacity)
                    industries = Counter(rows[sid]["secondary_industry"] for sid in selected)
                    self.assertTrue(all(number <= cap for number in industries.values()))
                    self.assertTrue(all(rows[sid][pool + "_qualified"] for sid in selected))
                focal = receipt.input_batch.input_for(FOCAL)
                card = receipt.score_batch.card_for(FOCAL)
                self.assertEqual(focal.status, "ready")
                self.assertIsNotNone(card)
                self.assertEqual(focal.confidence_cap, "0.90")
                self.assertTrue(card.cap_trace)
                self.assertTrue(focal.policy_batch_hash)
                self.assertTrue(focal.valuation_batch_hash)
                self.assertEqual(card.policy_batch_hash, focal.policy_batch_hash)
                self.assertEqual(card.valuation_batch_hash, focal.valuation_batch_hash)
                record = inspect.getclosurevars(type(receipt.input_batch).require_verified).nonlocals["record"]
                saved = inspect.getclosurevars(record).nonlocals["proofs"][id(receipt.input_batch)]
                base, policy, valuation = saved[5][1]
                for proof in (base, policy, valuation):
                    proof.require_verified()
                    self.assertEqual(proof.registry_manifest_hash, snapshot.registry_manifest_hash)
                    self.assertEqual(proof.frozen_input_hash, snapshot.frozen_input_hash)
                    self.assertEqual(proof.security_ids, ids)
                self.assertEqual(inputs["base_batch_hash"], base.batch_hash)
                self.assertEqual(inputs["policy_batch_hash"], policy.batch_hash)
                self.assertEqual(inputs["valuation_batch_hash"], valuation.batch_hash)
                self.assertEqual(valuation.policy_batch_hash, policy.batch_hash)
                for kind, proof in (("base", base), ("policy", policy), ("valuation", valuation)):
                    self.assertEqual(inputs[kind + "_batch_canonical_sha256"],
                                     hashlib.sha256(proof.canonical_bytes()).hexdigest())
                vslot = focal.slots["V.normalized_earnings_yield"]
                self.assertTrue(vslot["valuation_score_hash"])
                self.assertTrue(vslot["valuation_context_hash"])
                self.assertEqual(vslot["valuation_context"]["scope"], "template_primary_industry")
                self.assertTrue(runner.last_diagnostics.blockers)

    def test_final_recheck_revocation_leaves_no_torn_run_or_revoked_bc(self):
        fixture, _, repository, coverage, old = genuine_chain(self, 20)
        runner, _ = configured_runner(self.module, fixture)
        before = repository.get_run(old.run_id)
        selector_code = self.module.select_formal_pools.__code__
        revoked = []
        def revoke_after_d3(frame, event, argument):
            if event == "return" and frame.f_code is selector_code:
                FormalCoverageAuditor.revoke(coverage)
                revoked.append(True)
        previous_profiler = sys.getprofile()
        try:
            sys.setprofile(revoke_after_d3)
            try:
                with self.assertRaises(ValueError):
                    runner.run_preview(**run_arguments(fixture, coverage))
            finally:
                sys.setprofile(previous_profiler)
            self.assertEqual(revoked, [True])
            self.assertEqual(repository.get_run(old.run_id), before)
            self.assertEqual(repository.list_runs_by_input_manifest(old.input_manifest_hash), (before,))
            # Previously committed Stage D and retained upstream proofs stay live.
            for batch in old.batches:
                batch.require_verified()
            record = inspect.getclosurevars(type(old.input_batch).require_verified).nonlocals["record"]
            saved = inspect.getclosurevars(record).nonlocals["proofs"][id(old.input_batch)]
            for source in saved[5][1]:
                source.require_verified()
        finally:
            _CHAINS[20] = fixture, runner, repository, coverage_for(fixture), old

    def test_cross_frozen_security_and_registry_inputs_fail_closed(self):
        fixture, runner, repository, coverage, old = genuine_chain(self, 23)
        foreign, _, _, _, _ = genuine_chain(self, 20)
        self.assertNotEqual(fixture.bundle.manifest.manifest_hash,
                            foreign.bundle.manifest.manifest_hash)
        for key, value in (("scoring_registry", foreign.scoring),
                           ("policy_registry", foreign.policy_registry),
                           ("valuation_adapter_registry", foreign.valuation_registry)):
            with self.subTest(cross_root=key), self.assertRaises(ValueError):
                runner.run_preview(**dict(run_arguments(fixture, coverage), **{key: value}))
        for bad in (coverage_for(fixture, frozen_hash="a" * 64),
                    coverage_for(fixture, ids=[FOCAL]), coverage.to_dict()):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                runner.run_preview(**run_arguments(fixture, bad))
        with self.assertRaises(ValueError):
            runner.run_official_candidate(**run_arguments(fixture, coverage))
        self.assertEqual(repository.get_run(old.run_id).mode, "test_preview")

    def test_official_candidate_is_still_preview_ready_and_never_v9_published(self):
        fixture = FinalScoringFixture(peer_count=20, purpose="official", pending_ids=())
        self.addCleanup(fixture.close)
        fixture.populate_final_inputs()
        complete_score_history(fixture, sorted(fixture.templates))
        coverage = official_context_coverage(fixture)
        coverage.require_official_ready()
        runner, repository = configured_runner(self.module, fixture,
            code_version=coverage.to_dict()["workspace_revision"])
        receipt = runner.run_official_candidate(**run_arguments(fixture, coverage))
        snapshot = repository.get_run(receipt.run_id)
        self.assertEqual(snapshot.mode, "official_candidate")
        self.assertEqual(receipt.status, "preview_ready")
        self.assertTrue(runner.last_diagnostics.official_ready)
        self.assertNotIn(snapshot.status, ("validated", "published"))
        self.assertIn("v9_release_not_implemented", runner.last_diagnostics.blockers)

    def test_source_and_registry_row_tamper_reject_retained_manifest(self):
        fixture, _, repository, coverage, old = genuine_chain(self, 23)
        runner, _ = configured_runner(self.module, fixture)
        before = repository.get_run(old.run_id)
        with fixture.store._transaction() as connection:
            blob = connection.execute("SELECT registry_hash,canonical_json FROM formal_registry_blob "
                "WHERE registry_role='scoring'").fetchone()
            connection.execute("UPDATE formal_registry_blob SET canonical_json=? WHERE registry_hash=?",
                               (b"{}", blob[0]))
        try:
            with self.assertRaises(ValueError):
                runner.run_preview(**run_arguments(fixture, coverage))
            self.assertEqual(repository.get_run(old.run_id), before)
        finally:
            with fixture.store._transaction() as connection:
                connection.execute("UPDATE formal_registry_blob SET canonical_json=? WHERE registry_hash=?",
                                   (blob[1], blob[0]))
        referenced_sources = {ref["source_snapshot_id"]
            for slot in old.input_batch.input_for(FOCAL).slots.values()
            for ref in slot.get("evidence_refs", ())}
        self.assertTrue(referenced_sources)
        with fixture.store._transaction() as connection:
            row = connection.execute("SELECT id,content_sha256 FROM formal_source_snapshot WHERE id=?",
                (sorted(referenced_sources)[0],)).fetchone()
            self.assertIsNotNone(row)
            connection.execute("UPDATE formal_source_snapshot SET content_sha256=? WHERE id=?", ("0" * 64, row[0]))
        try:
            with self.assertRaises(ValueError):
                repository.plan_rebuild(prior_run_id=old.run_id,
                    prior_input_manifest_hash=old.input_manifest_hash,
                    input_batch=old.input_batch, coverage_manifest=coverage)
            with self.assertRaises(ValueError):
                runner.rebuild_affected(**run_arguments(fixture, coverage), prior_run_id=old.run_id,
                    prior_input_manifest_hash=old.input_manifest_hash)
        finally:
            with fixture.store._transaction() as connection:
                connection.execute("UPDATE formal_source_snapshot SET content_sha256=? WHERE id=?", (row[1], row[0]))
        old.input_batch.require_verified()
        saved = repository.get_run(old.run_id)
        with fixture.store._transaction() as connection:
            connection.execute("UPDATE formal_final_status SET state='formal_scored' WHERE run_id=? AND security_id=?",
                (old.run_id, next(row["security_id"] for row in saved.statuses if row["state"] == "pending_evidence")))
        try:
            with self.assertRaises(ValueError):
                repository.get_run(old.run_id)
        finally:
            with fixture.store._transaction() as connection:
                for item in saved.statuses:
                    connection.execute("UPDATE formal_final_status SET state=? WHERE run_id=? AND security_id=?",
                        (item["state"], old.run_id, item["security_id"]))
        self.assertEqual(repository.get_run(old.run_id), saved)

    def test_z_legitimate_financial_generation_correction_appends_trusted_rebuild(self):
        fixture, _, repository, _, old = genuine_chain(self, 23)
        before = repository.get_run(old.run_id)
        old_inputs = json.loads(before.artifacts["score_input_batch"])
        old_root = fixture.frozen.registry_manifest_hash
        old_frozen = fixture.frozen.frozen_input_hash
        generation = "task11-legitimate-financial-correction"
        # Genuine verified producer data, not an UPDATE to a retained source.
        # A later source update wins the existing formal version selection.
        source = fixture.put_financial(FOCAL, {"score_leaf": 999}, generation=generation,
            updated="2026-08-30T07:00:00+00:00", nature="instant", publish=False)
        fixture.set_generation(FOCAL, generation)
        fixture.valuation_feature_bundles[FOCAL] = fixture.persist_features(FOCAL)
        current_coverage = coverage_for(fixture)
        runner, _ = configured_runner(self.module, fixture)
        after = runner.rebuild_affected(**run_arguments(fixture, current_coverage),
            prior_run_id=old.run_id, prior_input_manifest_hash=old.input_manifest_hash)
        inputs = after.input_batch.to_dict()
        plan = runner.last_diagnostics.rebuild_plan
        self.assertEqual(inputs["registry_manifest_hash"], old_root)
        self.assertEqual(inputs["frozen_input_hash"], old_frozen)
        self.assertNotEqual(after.run_id, old.run_id)
        self.assertNotEqual(after.input_manifest_hash, old.input_manifest_hash)
        self.assertNotEqual(inputs["base_batch_hash"], old_inputs["base_batch_hash"])
        self.assertNotEqual(after.result_hash, old.result_hash)
        self.assertEqual(repository.get_run(old.run_id), before)
        self.assertEqual(repository.list_runs_by_input_manifest(after.input_manifest_hash),
            (repository.get_run(after.run_id),))
        focal = after.input_batch.input_for(FOCAL)
        self.assertEqual(focal.status, "ready")
        retained_source_ids = {ref["source_snapshot_id"] for slot in focal.slots.values()
            for ref in slot.get("evidence_refs", ())}
        self.assertIn(source.snapshot_id, retained_source_ids)
        self.assertEqual(plan.prior_manifest_hash, old.input_manifest_hash)
        self.assertEqual(plan.current_manifest_hash, after.input_manifest_hash)
        self.assertIn(FOCAL, plan.direct_security_ids)
        self.assertIn(FOCAL, plan.d1_rebuild_ids)
        self.assertIn(FOCAL, plan.d2_rebuild_ids)
        self.assertTrue(plan.reason_codes)
        self.assertTrue(plan.rescan_pools)
        self.assertTrue(set(plan.expanded_security_ids) <= set(inputs["security_ids"]))
        self.assertNotIn("changed_ids", inspect.signature(runner.rebuild_affected).parameters)
        # Later performance cases must use the current genuinely rebuilt chain,
        # not pretend that the old source checkpoint still authenticates it.
        _CHAINS[23] = fixture, runner, repository, current_coverage, after


if __name__ == "__main__":
    unittest.main()
