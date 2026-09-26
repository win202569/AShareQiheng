"""Atomic publication and forgery rejection for adjusted V batches."""

import copy
import hashlib
import sqlite3
import sys
import threading
import unittest
from pathlib import Path

from ashare_pipeline.formal_registry_manifest import FormalRegistryBundleLoader, VerifiedRegistryBundle
from ashare_pipeline.formal_metric_engine import FormalMetricInputRepository
from ashare_pipeline.formal_policy_repository import VerifiedPolicyResultBatch
from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal, _require_current_scope
from tests.formal_policy_fixtures import REGULATORY_SEMANTICS

from ashare_pipeline.formal_valuation_engine import (
    FormalValuationRepository, PolicyAdjustedValuationBatch,
    PolicyAdjustedValuationInput,
)
from tests.formal_valuation_fixtures import ValuationRuntimeFixture


class ValuationBatchGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = ValuationRuntimeFixture(peer_count=3)
        for security_id in cls.fixture.templates:
            cls.fixture.put_industry(security_id)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def build(self):
        return self.fixture.build_adjusted_batch()

    def test_store_reload_requires_original_adapter_and_exact_signed_ten_role_closure(self):
        fixture = self.fixture
        original = fixture.bundle
        reloaded = FormalRegistryBundleLoader(fixture.store, fixture.verifier).load(
            original.manifest.manifest_hash)
        self.assertIsNot(reloaded, original)
        self.assertEqual(len(reloaded.roles), 10)
        fixture.valuation_registry.require_current_bundle(reloaded)
        with self.assertRaises(ValueError):
            fixture.valuation_registry.require_official(reloaded)
        with self.assertRaises(ValueError):
            fixture.valuation_registry.require_current_bundle(object.__new__(VerifiedRegistryBundle))
        blob = reloaded.blob("valuation_adapter")
        raw = blob.canonical_json
        try:
            object.__setattr__(blob, "canonical_json", b"{}")
            with self.assertRaises(ValueError):
                fixture.valuation_registry.require_current_bundle(reloaded)
        finally:
            object.__setattr__(blob, "canonical_json", raw)

    def test_cross_root_store_reload_is_rejected(self):
        foreign = ValuationRuntimeFixture(peer_count=4)
        self.addCleanup(foreign.close)
        foreign_bundle = FormalRegistryBundleLoader(foreign.store, foreign.verifier).load(
            foreign.bundle.manifest.manifest_hash)
        # A separately signed root cannot inherit this adapter's authority.
        with self.assertRaises(ValueError):
            self.fixture.valuation_registry.require_current_bundle(foreign_bundle)

    def test_signed_membership_without_context_still_publishes_three_pending_v_rows(self):
        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        original_metric = FormalMetricInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier).build_batch(
                fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring,
                metric_ids=("V.enterprise_value_or_sustainable_roe",
                            "V.normalized_earnings_yield", "V.normalized_free_cash_flow_yield"))
        original_policy = fixture.build_policy_batch()
        metric_wire, policy_wire = original_metric.canonical_bytes(), original_policy.canonical_bytes()
        batch = fixture.build_adjusted_batch()
        batch.require_verified()
        self.assertEqual(len(batch.inputs), 9)
        self.assertTrue(all(row.status == "pending_policy_evidence" for row in batch.inputs))
        self.assertTrue(all(row.adjusted_value is None for row in batch.inputs))
        self.assertEqual(original_metric.canonical_bytes(), metric_wire)
        self.assertEqual(original_policy.canonical_bytes(), policy_wire)
        self.assertEqual(batch.base_batch_canonical_sha256, hashlib.sha256(metric_wire).hexdigest())
        self.assertEqual(batch.policy_batch_canonical_sha256, hashlib.sha256(policy_wire).hexdigest())

    def test_pending_affected_unaffected_and_invalid_original_keep_their_rows(self):
        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        fixture.put_industry("BJ430001")
        fixture.put_policy_context("BJ430001", "security_state", dict(is_st=False,
            is_star_st=False, listing_status="listed", forced_delist_risk=False,
            suspended=False))
        fixture.put_policy_context("BJ430001", "regulatory_state", dict(flags=[
            dict(flag_id=flag, active=False) for flag in REGULATORY_SEMANTICS]))
        fixture.put_financial("BJ430001", {"V.normalized_earnings_yield": 0.2,
            "V.normalized_free_cash_flow_yield": 0.08})
        fixture.persist_features("BJ430001")
        batch = fixture.build_adjusted_batch()
        self.assertEqual(len(batch.inputs), 9)
        self.assertEqual(batch.input_for("BJ430001", "V.normalized_earnings_yield").status,
                         "pending_policy_evidence")
        self.assertEqual(batch.input_for("BJ430001", "V.normalized_free_cash_flow_yield").status,
                         "passthrough_unaffected")
        self.assertEqual(batch.input_for("BJ430001", "V.enterprise_value_or_sustainable_roe").status,
                         "invalid_adapter_operand")

    def test_genuine_three_member_market_slices_clear_independent_trade_rule(self):
        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        fixture.populate_valuation_inputs()
        policy = fixture.build_policy_batch()
        policy.require_verified()
        rows = {row["security_id"]: row for row in policy.to_dict()["results"]}
        self.assertEqual(set(rows), set(fixture.templates))
        for sid in rows:
            decisions = [item for item in rows[sid]["decisions"]
                         if item["semantic_id"] == "no_effective_trade_20d"]
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["evaluation_state"], "clear")

    def test_policy_source_disappears_after_preparation_revokes_entire_adjusted_batch(self):
        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        _, ref = fixture.put_industry("BJ430001")
        source = Path(ref.content_path)
        original = source.read_bytes()
        captured = []
        observer = sqlite3.connect(fixture.store.db_path)
        self.addCleanup(observer.close)
        before = observer.execute("PRAGMA data_version").fetchone()[0]

        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_valuation_engine.py")
                    and type(result) is PolicyAdjustedValuationBatch and not captured):
                captured.append(result)
                source.write_bytes(b"source-invalidated-after-policy")

        try:
            with self.assertRaises(ValueError):
                self.run_with_trace(hook, fixture.build_adjusted_batch)
            self.assertEqual(observer.execute("PRAGMA data_version").fetchone()[0], before)
            self.assertEqual(len(captured), 1)
            with self.assertRaisesRegex(ValueError, "unpublished or revoked"):
                captured[0].require_verified()
        finally:
            source.write_bytes(original)

    def run_with_trace(self, hook, build=None):
        previous_profile, previous_trace = sys.getprofile(), sys.gettrace()
        try:
            sys.setprofile(hook)
            return (build or self.build)()
        finally:
            sys.setprofile(previous_profile)
            sys.settrace(previous_trace)

    def test_outer_finalization_failure_revokes_only_adjusted_children(self):
        captured = {"adjusted": [], "base": [], "policy": []}
        closed = []

        def hook(frame, event, result):
            if event == "return" and frame.f_code.co_name == "mint":
                filename = frame.f_code.co_filename
                if filename.endswith("formal_valuation_engine.py"):
                    captured["adjusted"].append(result)
                elif filename.endswith("formal_metric_engine.py"):
                    captured["base"].append(result)
                elif filename.endswith("formal_policy_repository.py"):
                    captured["policy"].append(result)
            if (not closed and captured["adjusted"] and event == "return"
                    and frame.f_code.co_name == "finalize"
                    and frame.f_code.co_filename.endswith("formal_metric_batch_guard.py")
                    and "observer" in frame.f_locals):
                closed.append(True)
                frame.f_locals["observer"].close()

        with self.assertRaises((sqlite3.Error, ValueError)):
            self.run_with_trace(hook)
        self.assertEqual(closed, [True])
        self.assertTrue(captured["adjusted"])
        with self.assertRaisesRegex(ValueError, "unpublished or revoked"):
            captured["adjusted"][-1].require_verified()
        captured["base"][-1].require_verified()
        captured["policy"][-1].require_verified()
        self.build().require_verified()

    def test_proofs_and_repository_reject_direct_construction_and_copy(self):
        for cls in (PolicyAdjustedValuationBatch, PolicyAdjustedValuationInput):
            with self.assertRaises(TypeError):
                cls()
            with self.assertRaises(ValueError):
                cls.require_verified(object.__new__(cls))
            subclass = type("UntrustedAdjustedProof", (cls,), {})
            with self.assertRaises(ValueError):
                cls.require_verified(object.__new__(subclass))
        with self.assertRaises(ValueError):
            FormalValuationRepository(object(), object(), object(), registry_signature_verifier=object())
        with self.assertRaises(ValueError):
            FormalValuationRepository.build_batch(object.__new__(FormalValuationRepository),
                self.fixture.frozen.frozen_input_hash, scoring_registry=self.fixture.scoring,
                policy_registry=self.fixture.policy_registry,
                valuation_adapter_registry=self.fixture.valuation_registry)
        batch = self.build()
        with self.assertRaises(TypeError):
            copy.copy(batch)
        with self.assertRaises(TypeError):
            copy.copy(batch.inputs[0])
        with self.assertRaises(AttributeError):
            batch.inputs[0].status = "adjusted"
        try:
            type.__setattr__(PolicyAdjustedValuationInput, "require_verified", lambda _self: None)
            with self.assertRaisesRegex(ValueError, "authority interface changed"):
                batch.inputs[0].require_verified()
        finally:
            type.__delattr__(PolicyAdjustedValuationInput, "require_verified")
        batch.inputs[0].require_verified()

    def test_replaced_adapter_entry_point_fails_before_any_publication(self):
        from ashare_pipeline.formal_valuation_adapter_contract import FormalValuationAdapterRegistry
        original = FormalValuationAdapterRegistry.require_current_bundle
        try:
            type.__setattr__(FormalValuationAdapterRegistry, "require_current_bundle",
                lambda _self, _bundle: None)
            with self.assertRaisesRegex(ValueError, "dependency changed"):
                self.build()
        finally:
            type.__setattr__(FormalValuationAdapterRegistry, "require_current_bundle", original)


class ValuationSourceClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = ValuationRuntimeFixture(peer_count=3)
        cls.fixture.populate_valuation_inputs()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def test_outer_scope_rejects_public_open_foreign_owner_thread_copy_and_replay(self):
        fixture = self.fixture
        population = tuple(sorted(fixture.templates))
        required = tuple((sid, "V.normalized_earnings_yield") for sid in population)
        with self.assertRaisesRegex(ValueError, "authentic owner build"):
            FormalBatchReadJournal.open(fixture.repository,
                registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
                as_of_utc="2026-08-31T07:00:00+00:00", population=population,
                required_keys=required, frozen_input_hash=fixture.frozen.frozen_input_hash)
        captured = []
        foreign = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(foreign.close)

        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "open"
                    and frame.f_code.co_filename.endswith("formal_batch_read_journal.py")
                    and type(result) is FormalBatchReadJournal and not captured):
                captured.append(result)
                with self.assertRaises(ValueError):
                    _require_current_scope(result, foreign.repository,
                        root=fixture.bundle.manifest.manifest_hash,
                        as_of_utc="2026-08-31T07:00:00+00:00", population=population)
                failures = []
                worker = threading.Thread(target=lambda: _cross_thread_probe(result, failures))
                worker.start()
                worker.join()
                self.assertEqual(failures, [ValueError])

        def _cross_thread_probe(scope, failures):
            try:
                scope.checkpoint()
            except Exception as error:
                failures.append(type(error))

        batch = ValuationBatchGuardTests.run_with_trace(self, hook, fixture.build_adjusted_batch)
        batch.require_verified()
        self.assertEqual(len(captured), 1)
        with self.assertRaises(TypeError):
            copy.copy(captured[0])
        with self.assertRaisesRegex(ValueError, "closed"):
            captured[0].checkpoint()

    def test_provider_epoch_change_after_adjusted_mint_revokes_adjusted_batch(self):
        fixture = self.fixture
        member = "BJ430001"
        snapshot = fixture.provider.resolve_current_inputs(security_id=member,
            as_of_utc="2026-08-31T07:00:00+00:00", template_id=fixture.templates[member],
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash)
        adjusted, changed = [], []

        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_valuation_engine.py")
                    and type(result) is PolicyAdjustedValuationBatch and not changed):
                adjusted.append(result)
                changed.append(True)
                fixture.provider.publish(snapshot)

        with self.assertRaises(ValueError):
            ValuationBatchGuardTests.run_with_trace(self, hook, fixture.build_adjusted_batch)
        self.assertEqual(changed, [True])
        with self.assertRaisesRegex(ValueError, "unpublished or revoked"):
            adjusted[0].require_verified()
        fixture.build_adjusted_batch().require_verified()

    def test_three_member_owner_selects_once_and_all_checkpoint_phases_cover_every_member(self):
        from ashare_pipeline.formal_feature_repository import FormalFeatureRepository
        from ashare_pipeline.formal_policy_financial import FormalPolicyFinancialRepository
        from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        from ashare_pipeline.formal_financial_features import build_formal_feature_bundle
        from ashare_pipeline.formal_metric_features import evaluate_selected_features
        from ashare_pipeline.formal_range_source import FormalRangeSource

        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        members = set(fixture.templates)
        for index, sid in enumerate(sorted(members)):
            fixture.put_industry(sid)
            fixture.put_financial(sid, {
                "V.enterprise_value_or_sustainable_roe": 0.1 + index / 1000,
                "V.normalized_earnings_yield": 0.2 + index / 1000,
                "V.normalized_free_cash_flow_yield": 0.08 + index / 1000})
            fixture.persist_features(sid)
        first_v = []
        selected = {kind: [] for kind in ("financial", "state", "market")}
        checkpoints = []
        checked = {}
        forbidden = []
        checkpoint_code = FormalBatchReadJournal.checkpoint.__code__
        feature_select_code = FormalFeatureRepository.select_current_verified_metric_feature_state.__code__
        feature_ticket_code = FormalFeatureRepository.select_current_metric_batch_ticket.__code__
        selectors = {
            FormalPolicyFinancialRepository.select_current_batch_ticket.__code__: "financial",
            FormalPolicyStateRepository.select_current_batch_ticket.__code__: "state",
            FormalPolicyMarketRepository.select_current_batch_ticket.__code__: "market",
        }
        checkers = {
            FormalPolicyFinancialRepository._batch_recheck_ticket.__code__: "financial",
            FormalPolicyStateRepository._batch_recheck_ticket.__code__: "state",
            FormalPolicyMarketRepository._batch_recheck_ticket.__code__: "market",
            FormalFeatureRepository._batch_recheck_ticket.__code__: "feature",
        }
        banned_codes = {build_formal_feature_bundle.__code__, evaluate_selected_features.__code__,
            FormalRangeSource.parse_verified_snapshot.__code__, feature_select_code,
            FormalPolicyFinancialRepository.select.__code__,
            FormalPolicyStateRepository.select.__code__,
            FormalPolicyMarketRepository.select.__code__,
            FormalPolicyMarketRepository.select_calendar.__code__}

        def hook(frame, event, result):
            if event != "call":
                return
            code = frame.f_code
            if code is checkpoint_code:
                checkpoints.append(frame.f_locals["self"])
                print(f"C4 journal checkpoint {len(checkpoints)}", flush=True)
            elif code is feature_select_code and frame.f_back.f_code is feature_ticket_code:
                first_v.append((frame.f_locals["security_id"], frame.f_back.f_locals["metric_id"]))
            elif code in selectors:
                selected[selectors[code]].append(frame.f_locals["security_id"])
            elif code in checkers and frame.f_back.f_code is checkpoint_code:
                kind = checkers[code]
                evidence = frame.f_locals["evidence"]
                if kind != "market" or evidence[0] == "market":
                    sid = evidence[0]["security_id"] if kind == "feature" else evidence[-1][0]
                    checked.setdefault((len(checkpoints) - 1, kind), []).append(sid)
            if code in banned_codes:
                cursor = frame.f_back
                while cursor is not None:
                    if cursor.f_code is checkpoint_code:
                        forbidden.append(code.co_name)
                        break
                    cursor = cursor.f_back

        batch = ValuationBatchGuardTests.run_with_trace(self, hook, fixture.build_adjusted_batch)
        batch.require_verified()
        self.assertEqual(sorted(first_v), sorted((sid, mid) for sid in members for mid in batch.metric_ids))
        for kind, calls in selected.items():
            self.assertEqual(sorted(calls), sorted(members), kind)
        self.assertEqual(len(checkpoints), 3)
        self.assertIs(checkpoints[0], checkpoints[1])
        self.assertIs(checkpoints[1], checkpoints[2])
        for phase in (0, 1, 2):
            for kind in selected:
                self.assertEqual(sorted(checked[(phase, kind)]), sorted(members), (phase, kind))
        self.assertEqual(sorted(checked[(2, "feature")]),
                         sorted(sid for sid in members for _ in batch.metric_ids))
        self.assertEqual(forbidden, [])
        rereads = []
        previous = sys.getprofile()
        try:
            sys.setprofile(lambda frame, event, _result: rereads.append(frame.f_code.co_name)
                if event == "call" and frame.f_code.co_name in {
                    "_batch_recheck_ticket", "select_state", "build_formal_feature_bundle"} else None)
            for item in batch.inputs:
                self.assertIsInstance(item.status, str)
                self.assertIsInstance(item.security_id, str)
        finally:
            sys.setprofile(previous)
        self.assertEqual(rereads, [])
        public_metric = FormalMetricInputRepository(fixture.feature_repository,
            fixture.context, registry_signature_verifier=fixture.verifier).build_batch(
                fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring,
                metric_ids=tuple(batch.metric_ids))
        public_policy = fixture.build_policy_batch()
        self.assertEqual(batch.base_batch_canonical_sha256,
                         hashlib.sha256(public_metric.canonical_bytes()).hexdigest())
        self.assertEqual(batch.policy_batch_canonical_sha256,
                         hashlib.sha256(public_policy.canonical_bytes()).hexdigest())

    def test_v_only_file_changes_revoke_outer_publication_without_database_version_change(self):
        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        fixture.put_industry("BJ430001")
        fixture.put_policy_context("BJ430001", "security_state", dict(is_st=False,
            is_star_st=False, listing_status="listed", forced_delist_risk=False,
            suspended=False))
        fixture.put_policy_context("BJ430001", "regulatory_state", dict(flags=[
            dict(flag_id=flag, active=False) for flag in REGULATORY_SEMANTICS]))
        fixture.policy_financial_values("BJ430001")
        fixture.put_financial("SH600000", {
            "V.enterprise_value_or_sustainable_roe": 0.1,
            "V.normalized_earnings_yield": 0.2,
            "V.normalized_free_cash_flow_yield": 0.08})
        bundle = fixture.persist_features("SH600000")
        facts = fixture.store.list_formal_financial_facts(security_id="SH600000")
        raw_fact = next(item for item in facts if item.metric_key == "V.normalized_earnings_yield")
        source = fixture.store.get_formal_snapshot(raw_fact.source_snapshot_id)
        receipt = fixture.store.get_formal_feature_bundle_row(bundle.input_hash)
        targets = ((Path(source.content_path), "modify"),
                   (Path(source.manifest_path), "delete"),
                   (Path(receipt["bundle_path"]), "modify"),
                   (Path(receipt["manifest_path"]), "delete"))
        observer = sqlite3.connect(fixture.store.db_path)
        self.addCleanup(observer.close)
        for target, mode in targets:
            with self.subTest(target=target.name, mode=mode):
                print(f"C4 V-only closure {mode} {target.name}", flush=True)
                original = target.read_bytes()
                before = observer.execute("PRAGMA data_version").fetchone()[0]
                adjusted, policies, changed = [], [], []

                def hook(frame, event, result):
                    if event != "return" or frame.f_code.co_name != "mint":
                        return
                    if type(result) is VerifiedPolicyResultBatch:
                        policies.append(result)
                    if (type(result) is PolicyAdjustedValuationBatch and not changed
                            and frame.f_code.co_filename.endswith("formal_valuation_engine.py")):
                        adjusted.append(result)
                        changed.append(True)
                        if mode == "delete":
                            target.unlink()
                        else:
                            target.write_bytes(original + b"\nchanged-after-adjusted-mint")

                try:
                    with self.assertRaises(ValueError):
                        ValuationBatchGuardTests.run_with_trace(self, hook, fixture.build_adjusted_batch)
                    self.assertEqual(changed, [True])
                    self.assertEqual(observer.execute("PRAGMA data_version").fetchone()[0], before)
                    with self.assertRaisesRegex(ValueError, "unpublished or revoked"):
                        adjusted[0].require_verified()
                    self.assertTrue(policies)
                    policies[-1].require_verified()
                    self.assertEqual(policies[-1].to_dict()["evidence_batch"]["selections"]["SH600000"], {})
                finally:
                    target.write_bytes(original)

        fixture.build_adjusted_batch().require_verified()
