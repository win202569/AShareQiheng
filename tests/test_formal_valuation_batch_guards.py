"""Atomic publication and forgery rejection for adjusted V batches."""

import copy
import hashlib
import json
import sqlite3
import sys
import threading
import unittest
from pathlib import Path

from ashare_pipeline.formal_registry_manifest import FormalRegistryBundleLoader, VerifiedRegistryBundle
from ashare_pipeline.formal_metric_engine import FormalMetricInputRepository, MetricInputBatch
from ashare_pipeline.formal_policy_repository import VerifiedPolicyResultBatch
from ashare_pipeline.formal_batch_read_journal import (
    FormalBatchReadJournal, _issue_current_ticket, _require_current_scope)
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

    def test_digest_rebinding_after_adjusted_mint_revokes_unpublished_batch(self):
        import ashare_pipeline.formal_valuation_engine as engine

        original = engine.digest
        captured = []

        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_valuation_engine.py")
                    and type(result) is PolicyAdjustedValuationBatch and not captured):
                captured.append(result)
                engine.digest = lambda _wire: "0" * 64

        try:
            with self.assertRaises(ValueError):
                self.run_with_trace(hook)
        finally:
            engine.digest = original
        self.assertEqual(len(captured), 1)
        with self.assertRaisesRegex(ValueError, "unpublished or revoked"):
            captured[0].require_verified()

    def test_c4_decimal_binding_change_rejects_build(self):
        import ashare_pipeline.formal_valuation_engine as engine

        original = engine.Decimal
        try:
            engine.Decimal = lambda _value: "999"
            with self.assertRaisesRegex(ValueError, "valuation publication dependency"):
                self.build()
        finally:
            engine.Decimal = original
        self.build().require_verified()

    def test_adjusted_decimal_mint_pollution_cannot_authenticate_after_restore(self):
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
        poisoned, captured, batches = [], [], []

        def hook(frame, event, result):
            if (event == "call" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_valuation_engine.py")
                    and frame.f_locals.get("cls") is PolicyAdjustedValuationInput
                    and frame.f_locals["attributes"].get("adjusted_value") is not None
                    and not poisoned):
                frame.f_locals["attributes"]["adjusted_value"] = "999"
                poisoned.append(True)
            elif (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_valuation_engine.py")
                    and type(result) is PolicyAdjustedValuationInput):
                captured.append(result)
            elif (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_valuation_engine.py")
                    and type(result) is PolicyAdjustedValuationBatch):
                batches.append(result)

        with self.assertRaisesRegex(ValueError, "adjusted valuation proof Decimal"):
            self.run_with_trace(hook, fixture.build_adjusted_batch)
        self.assertEqual(poisoned, [True])
        self.assertEqual(len(captured), 9)
        self.assertEqual(len(batches), 1)
        for proof in (*captured, *batches):
            with self.assertRaisesRegex(ValueError, "unpublished or revoked"):
                proof.require_verified()

    def test_batch_input_for_reads_do_not_decode_every_child_each_time(self):
        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        batch = fixture.build_adjusted_batch()
        rows = tuple(batch.inputs)
        decodes = []
        import ashare_pipeline.formal_valuation_engine as engine
        decode_code = engine.json.loads.__code__

        def hook(frame, event, _result):
            if (event == "call" and frame.f_code is decode_code
                    and frame.f_back.f_code.co_name == "record"
                    and frame.f_back.f_code.co_filename.endswith("formal_valuation_engine.py")):
                decodes.append(True)

        previous = sys.getprofile()
        try:
            sys.setprofile(hook)
            for row in rows:
                selected = batch.input_for(row.security_id, row.metric_id)
                self.assertIs(selected, row)
                self.assertIsInstance(selected.status, str)
        finally:
            sys.setprofile(previous)
        self.assertLessEqual(len(decodes), len(rows) + 5)

    def test_batch_private_index_is_detached_from_mutable_mint_local(self):
        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        captured = []

        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_valuation_engine.py")
                    and type(result) is PolicyAdjustedValuationBatch):
                captured.append(frame.f_locals["private"]["index"])

        batch = self.run_with_trace(hook, fixture.build_adjusted_batch)
        self.assertEqual(len(captured), 1)
        row = batch.inputs[0]
        captured[0].clear()
        batch.require_verified()
        self.assertIs(batch.input_for(row.security_id, row.metric_id), row)

    def test_c3_dynamic_dependency_rebinding_blocks_formal_valuation_build(self):
        import ashare_pipeline.formal_valuation_adapter as adapter
        import ashare_pipeline.formal_policy_values as policy_values

        changes = (
            (adapter, "_decimal_text", lambda _value: "999"),
            (adapter, "Decimal", object()),
            (adapter, "localcontext", object()),
            (adapter, "Context", object()),
            (adapter, "ROUND_HALF_EVEN", "ROUND_DOWN"),
            (adapter, "_hash", lambda *_args: None),
            (adapter, "digest", lambda _wire: "0" * 64),
            (policy_values, "json", object()),
        )
        for module, name, replacement in changes:
            with self.subTest(module=module.__name__, name=name):
                original = getattr(module, name)
                try:
                    setattr(module, name, replacement)
                    with self.assertRaisesRegex(ValueError, "valuation adapter dependency"):
                        self.build()
                finally:
                    setattr(module, name, original)
        self.build().require_verified()

    def test_metric_own_checkpoint_revokes_base_before_publication_on_last_v_source_change(self):
        from ashare_pipeline.formal_feature_repository import FormalFeatureRepository

        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        fixture.put_financial("SH600000", {
            "V.enterprise_value_or_sustainable_roe": 0.1,
            "V.normalized_earnings_yield": 0.2,
            "V.normalized_free_cash_flow_yield": 0.08})
        fixture.persist_features("SH600000")
        fact = next(item for item in fixture.store.list_formal_financial_facts(
            security_id="SH600000") if item.metric_key == "V.normalized_earnings_yield")
        source = Path(fixture.store.get_formal_snapshot(fact.source_snapshot_id).content_path)
        original = source.read_bytes()
        selected, bases = [], []

        def hook(frame, event, result):
            if event != "return":
                return
            if (frame.f_code is FormalFeatureRepository.select_current_metric_batch_ticket.__code__
                    and frame.f_locals.get("security_id") == "SH600000"):
                selected.append(frame.f_locals["metric_id"])
                if len(selected) == 3:
                    source.write_bytes(original + b"\nchanged-after-third-v-ticket")
            elif (frame.f_code.co_name == "mint"
                    and frame.f_code.co_filename.endswith("formal_metric_engine.py")
                    and type(result) is MetricInputBatch):
                bases.append(result)

        try:
            with self.assertRaises(ValueError):
                self.run_with_trace(hook, fixture.build_adjusted_batch)
            self.assertEqual(len(selected), 3)
            self.assertEqual(len(bases), 1)
            with self.assertRaisesRegex(ValueError, "forged or copied"):
                bases[0].require_verified()
        finally:
            source.write_bytes(original)
        fixture.build_adjusted_batch().require_verified()

    def test_metric_checkpoint_rejects_one_missing_member_metric_ticket(self):
        from ashare_pipeline.formal_feature_repository import FormalFeatureRepository

        fixture = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(fixture.close)
        observed = {"selected": 0}

        def hook(frame, event, result):
            if (event == "return" and frame.f_code.co_name == "open"
                    and frame.f_code.co_filename.endswith("formal_batch_read_journal.py")
                    and type(result) is FormalBatchReadJournal):
                observed["scope"] = result
            if (event == "return" and frame.f_code is
                    FormalFeatureRepository.select_current_metric_batch_ticket.__code__):
                observed["selected"] += 1
                if observed["selected"] == 8:
                    metric = fixture.repository._batch_journal_identity()[1][0]
                    with self.assertRaisesRegex(ValueError, "metric V source ticket coverage"):
                        observed["scope"].checkpoint_metric(metric)
                    observed["incomplete_rejected"] = True

        with self.assertRaises(ValueError):
            self.run_with_trace(hook, fixture.build_adjusted_batch)
        self.assertTrue(observed.get("incomplete_rejected"))
        self.assertEqual(observed["selected"], 8)
        with self.assertRaisesRegex(ValueError, "closed"):
            observed["scope"].checkpoint()
        fixture.build_adjusted_batch().require_verified()

    def test_four_member_signed_universe_without_template_has_three_invalid_v_rows(self):
        fixture = ValuationRuntimeFixture(peer_count=3, extra_members=("SH600001",))
        self.addCleanup(fixture.close)
        batch = fixture.build_adjusted_batch()
        batch.require_verified()
        self.assertEqual(len(batch.inputs), 12)
        self.assertEqual(tuple(batch.security_ids),
            ("BJ430001", "SH600000", "SH600001", "SZ000001"))
        for metric_id in batch.metric_ids:
            row = batch.input_for("SH600001", metric_id)
            row.require_verified()
            self.assertIsNone(row.template_id)
            self.assertEqual(row.original_metric["invalid_reason"], "invalid_template")
            self.assertEqual(row.status, "pending_policy_evidence")
            self.assertIsNone(row.adjusted_value)
        public = FormalMetricInputRepository(fixture.feature_repository,
            fixture.context, registry_signature_verifier=fixture.verifier).build_batch(
                fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring,
                metric_ids=tuple(batch.metric_ids))
        self.assertEqual(len(public.inputs), 12)
        self.assertEqual(batch.base_batch_canonical_sha256,
                         hashlib.sha256(public.canonical_bytes()).hexdigest())

    def test_four_member_invalid_template_token_covers_each_v_in_all_four_phases(self):
        from ashare_pipeline.formal_feature_repository import FormalFeatureRepository

        fixture = ValuationRuntimeFixture(peer_count=3, extra_members=("SH600001",))
        self.addCleanup(fixture.close)
        checkpoints, invalid_checks, feature_checks = [], [], []
        checkpoint_code = FormalBatchReadJournal.checkpoint.__code__
        metric_check_code = FormalMetricInputRepository._batch_recheck_invalid_template_tickets.__code__
        feature_check_code = FormalFeatureRepository._batch_recheck_ticket.__code__

        def hook(frame, event, _result):
            if event != "call":
                return
            if frame.f_code is checkpoint_code:
                checkpoints.append(frame.f_locals["self"])
                print(f"C4 invalid-template checkpoint {len(checkpoints)}", flush=True)
            elif frame.f_code is metric_check_code and frame.f_back.f_code is checkpoint_code:
                self.assertEqual(len(frame.f_locals["evidences"]), 1)
                invalid_checks.append(len(checkpoints) - 1)
            elif frame.f_code is feature_check_code and frame.f_back.f_code is checkpoint_code:
                feature_checks.append(len(checkpoints) - 1)

        batch = self.run_with_trace(hook, fixture.build_adjusted_batch)
        batch.require_verified()
        self.assertEqual(len(checkpoints), 4)
        self.assertTrue(all(scope is checkpoints[0] for scope in checkpoints))
        self.assertEqual(invalid_checks, [0, 1, 2, 3])
        self.assertEqual(feature_checks, [phase for phase in range(4) for _ in range(9)])
        self.assertEqual(len([row for row in batch.inputs if row.security_id == "SH600001"]), 3)

    def test_two_missing_templates_share_one_current_recheck_and_base_parse_per_phase(self):
        from ashare_pipeline.formal_metric_context import FormalMetricContextRepository

        fixture = ValuationRuntimeFixture(peer_count=3,
            extra_members=("SH600001", "SH600002"))
        self.addCleanup(fixture.close)
        context_code = FormalMetricContextRepository.recheck_batch.__code__
        import ashare_pipeline.formal_metric_engine as metric_engine
        decode_code = metric_engine.json.loads.__code__
        rechecks, base_decodes = [], []

        def in_invalid_closure(frame):
            cursor = frame.f_back
            while cursor is not None:
                if (cursor.f_code.co_filename.endswith("formal_metric_engine.py")
                        and cursor.f_code.co_name in {
                            "_batch_recheck_ticket", "_batch_recheck_invalid_template_tickets"}):
                    return True
                cursor = cursor.f_back
            return False

        def hook(frame, event, _result):
            if (event != "call" or frame.f_code not in (context_code, decode_code)
                    or not in_invalid_closure(frame)):
                return
            if frame.f_code is context_code:
                rechecks.append(True)
            elif frame.f_code is decode_code:
                wire = frame.f_locals.get("s")
                if (type(wire) is bytes
                        and b'"schema_version":"formal-metric-input-batch-v1"' in wire):
                    base_decodes.append(True)

        batch = self.run_with_trace(hook, fixture.build_adjusted_batch)
        batch.require_verified()
        self.assertEqual(len(batch.inputs), 15)
        self.assertEqual(len(rechecks), 5)  # one issuance preparation, four phases
        self.assertEqual(len(base_decodes), 5)

    def test_caller_cannot_forge_invalid_template_token_in_genuine_scope(self):
        fixture = ValuationRuntimeFixture(peer_count=3, extra_members=("SH600001",))
        self.addCleanup(fixture.close)
        observed = []

        def hook(frame, event, scope):
            if (event != "return" or frame.f_code.co_name != "open"
                    or not frame.f_code.co_filename.endswith("formal_batch_read_journal.py")
                    or type(scope) is not FormalBatchReadJournal or observed):
                return
            metric = fixture.repository._batch_journal_identity()[1][0]
            sid = "SH600001"
            population = tuple(sorted((*fixture.templates, sid)))
            mids = ("V.enterprise_value_or_sustainable_roe",
                    "V.normalized_earnings_yield", "V.normalized_free_cash_flow_yield")
            with self.assertRaisesRegex(ValueError, "fixed owner selector"):
                _issue_current_ticket(scope, metric, "metric",
                    (fixture.frozen.frozen_input_hash, "invalid_template", sid,
                     fixture.bundle.manifest.manifest_hash, population), b"forged",
                    ("invalid_template",), tuple((sid, mid) for mid in mids), object())
            observed.append(True)

        batch = self.run_with_trace(hook, fixture.build_adjusted_batch)
        batch.require_verified()
        self.assertEqual(observed, [True])
        self.assertEqual(len(batch.inputs), 12)

    def test_invalid_template_token_recheck_rejects_attempted_signed_mapping_change(self):
        fixture = ValuationRuntimeFixture(peer_count=3, extra_members=("SH600001",))
        self.addCleanup(fixture.close)
        evidence = []
        check_code = FormalMetricInputRepository._batch_recheck_invalid_template_tickets.__code__

        def hook(frame, event, _result):
            if event == "call" and frame.f_code is check_code and not evidence:
                evidence.append(frame.f_locals["evidences"][0])

        self.run_with_trace(hook, fixture.build_adjusted_batch).require_verified()
        self.assertEqual(len(evidence), 1)
        root = fixture.bundle.manifest.industry_registry_hash
        blob = fixture.store.get_formal_registry_blob(root)
        mapping = json.loads(blob.canonical_json)
        mapping["memberships"].append(dict(security_id="SH600001",
            template_id="general_nonfinancial", primary_industry="fixture-policy",
            secondary_industry="fixture-cyclic"))
        changed = json.dumps(mapping, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()
        fixture.sql("UPDATE formal_registry_blob SET canonical_json=? WHERE registry_hash=?",
            (changed, root))
        metric = fixture.repository._batch_journal_identity()[1][0]
        with self.assertRaises(ValueError):
            metric._batch_recheck_ticket(evidence[0])

    def test_signed_template_appearance_attempt_after_adjusted_mint_revokes_outer_only(self):
        fixture = ValuationRuntimeFixture(peer_count=3, extra_members=("SH600001",))
        self.addCleanup(fixture.close)
        root = fixture.bundle.manifest.industry_registry_hash
        blob = fixture.store.get_formal_registry_blob(root)
        mapping = json.loads(blob.canonical_json)
        mapping["memberships"].append(dict(security_id="SH600001",
            template_id="general_nonfinancial", primary_industry="fixture-policy",
            secondary_industry="fixture-cyclic"))
        changed = json.dumps(mapping, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()
        captured = {"adjusted": [], "base": [], "policy": []}

        def hook(frame, event, result):
            if (event != "return" or frame.f_code.co_name != "mint"):
                return
            if type(result) is MetricInputBatch:
                captured["base"].append(result)
            elif type(result) is VerifiedPolicyResultBatch:
                captured["policy"].append(result)
            elif type(result) is PolicyAdjustedValuationBatch:
                captured["adjusted"].append(result)
                fixture.sql("UPDATE formal_registry_blob SET canonical_json=? WHERE registry_hash=?",
                    (changed, root))

        with self.assertRaises(ValueError):
            self.run_with_trace(hook, fixture.build_adjusted_batch)
        self.assertEqual([len(captured[kind]) for kind in ("adjusted", "base", "policy")],
                         [1, 1, 1])
        with self.assertRaisesRegex(ValueError, "unpublished or revoked"):
            captured["adjusted"][0].require_verified()
        captured["base"][0].require_verified()
        captured["policy"][0].require_verified()

    def test_invalid_template_token_recheck_rejects_one_missing_v_row(self):
        fixture = ValuationRuntimeFixture(peer_count=3, extra_members=("SH600001",))
        self.addCleanup(fixture.close)
        evidence = []
        check_code = FormalMetricInputRepository._batch_recheck_invalid_template_tickets.__code__

        def hook(frame, event, _result):
            if event == "call" and frame.f_code is check_code and not evidence:
                evidence.append(frame.f_locals["evidences"][0])

        self.run_with_trace(hook, fixture.build_adjusted_batch).require_verified()
        self.assertEqual(len(evidence), 1)
        metric = fixture.repository._batch_journal_identity()[1][0]
        incomplete = evidence[0][:5] + (evidence[0][5][:-1],) + evidence[0][6:]
        with self.assertRaisesRegex(ValueError, "wrong frozen rows"):
            metric._batch_recheck_ticket(incomplete)

    def test_metric_private_early_failures_consume_only_the_genuine_owner_scope(self):
        from ashare_pipeline.formal_feature_repository import FormalFeatureRepository

        metric_ids = ("V.enterprise_value_or_sustainable_roe",
                      "V.normalized_earnings_yield", "V.normalized_free_cash_flow_yield")
        for failure in ("invalid_frozen", "interface_changed", "invalid_metrics"):
            with self.subTest(failure=failure):
                fixture = ValuationRuntimeFixture(peer_count=3)
                self.addCleanup(fixture.close)
                observed = {}

                def hook(frame, event, result):
                    if (event != "return" or frame.f_code.co_name != "open"
                            or not frame.f_code.co_filename.endswith("formal_batch_read_journal.py")
                            or type(result) is not FormalBatchReadJournal or observed):
                        return
                    scope = result
                    _, (metric, _) = fixture.repository._batch_journal_identity()
                    request = dict(scoring_registry=fixture.scoring, metric_ids=metric_ids)
                    fake = object.__new__(FormalBatchReadJournal)
                    try:
                        metric._build_batch_in_owner_scope(fixture.frozen.frozen_input_hash,
                            owner_scope=fake, **request)
                    except ValueError:
                        observed["fake_rejected"] = True
                    try:
                        scope.checkpoint()
                        observed["fake_preserved_true_scope"] = True
                    except ValueError:
                        observed["fake_preserved_true_scope"] = False
                    frozen = fixture.frozen.frozen_input_hash
                    if failure == "invalid_frozen":
                        frozen = "0" * 64
                    elif failure == "invalid_metrics":
                        request["metric_ids"] = ("V.missing_metric",)
                    original = FormalFeatureRepository.select_current_metric_batch_ticket
                    try:
                        if failure == "interface_changed":
                            FormalFeatureRepository.select_current_metric_batch_ticket = lambda *_a, **_k: None
                        try:
                            metric._build_batch_in_owner_scope(frozen, owner_scope=scope, **request)
                        except ValueError:
                            observed["entry_rejected"] = True
                    finally:
                        FormalFeatureRepository.select_current_metric_batch_ticket = original
                    try:
                        scope.checkpoint()
                        observed["true_scope_consumed"] = False
                    except ValueError:
                        observed["true_scope_consumed"] = True

                with self.assertRaises(ValueError):
                    self.run_with_trace(hook, fixture.build_adjusted_batch)
                self.assertEqual(observed, dict(fake_rejected=True,
                    fake_preserved_true_scope=True, entry_rejected=True,
                    true_scope_consumed=True))

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
        self.assertEqual(len(checkpoints), 4)
        self.assertIs(checkpoints[0], checkpoints[1])
        self.assertIs(checkpoints[1], checkpoints[2])
        self.assertIs(checkpoints[2], checkpoints[3])
        for phase in (1, 2, 3):
            for kind in selected:
                self.assertEqual(sorted(checked[(phase, kind)]), sorted(members), (phase, kind))
        for phase in (0, 1, 2, 3):
            self.assertEqual(sorted(checked[(phase, "feature")]),
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
