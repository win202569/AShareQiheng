"""Attack matrix for the genuine D1 publication boundary."""

import copy
from decimal import Decimal
import inspect
import json
import pickle
import sys
import unittest
import weakref
from types import MappingProxyType

from ashare_pipeline import formal_metric_engine
from ashare_pipeline.formal_final_score_inputs import (
    FormalFinalScoreInputRepository, PolicyAdjustedScoreInput,
    PolicyAdjustedScoreInputBatch,
)
from ashare_pipeline.formal_score_inputs import FormalScoreInputBatch
from tests.formal_final_scoring_fixtures import FinalScoringFixture, FOCAL
from tests.formal_metric_fixtures import FREEZE
from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
from tests.formal_valuation_fixtures import ValuationRuntimeFixture


V_METRICS = (
    "V.enterprise_value_or_sustainable_roe",
    "V.normalized_earnings_yield",
    "V.normalized_free_cash_flow_yield",
)


class CrossoverFinalScoringFixture(FinalScoringFixture):
    """A genuine ready universe whose raw and adjusted V ranks diverge."""

    def put_financial(self, sid, values, *args, **kwargs):
        if sid == "SH600017" and kwargs.get("generation") == "stage-d-valuation":
            values = dict(values, **{"V.normalized_earnings_yield": 0.13})
        return super().put_financial(sid, values, *args, **kwargs)


class FinalScoreInputGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = FinalScoringFixture()
        cls.addClassCleanup(cls.fixture.close)
        cls.fixture.populate_final_inputs()
        cls.repository = FormalFinalScoreInputRepository(
            cls.fixture.feature_repository, cls.fixture.context,
            cls.fixture.range_store, registry_signature_verifier=cls.fixture.verifier)
        cls.batch = cls.build()
        cls.sources = cls.fixture.build_d1_sources()

    @classmethod
    def build(cls):
        fixture = cls.fixture
        return cls.repository.build_batch(fixture.frozen.frozen_input_hash,
            scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry,
            valuation_adapter_registry=fixture.valuation_registry)

    @classmethod
    def distinct_root(cls):
        if not hasattr(cls, "other_fixture"):
            fixture = FinalScoringFixture(peer_count=3, cap_ids=(FOCAL, "SH600000"))
            cls.addClassCleanup(fixture.close)
            fixture.populate_final_inputs()
            cls.other_fixture = fixture
            cls.other_sources = fixture.build_d1_sources()
        return cls.other_fixture, cls.other_sources

    def test_cross_root_frozen_security_and_source_batch_are_rejected(self):
        other = ValuationRuntimeFixture(peer_count=3)
        self.addCleanup(other.close)
        self.assertNotEqual(other.bundle.manifest.manifest_hash,
            self.fixture.bundle.manifest.manifest_hash)
        with self.assertRaises(ValueError):
            self.repository.build_batch(other.frozen.frozen_input_hash,
                scoring_registry=self.fixture.scoring,
                policy_registry=self.fixture.policy_registry,
                valuation_adapter_registry=self.fixture.valuation_registry)
        with self.assertRaises(ValueError):
            self.batch.input_for("SH999999")
        closure = inspect.getclosurevars(FormalFinalScoreInputRepository.build_batch).nonlocals
        with self.assertRaises(ValueError):
            closure["close_identity"](other.frozen, other.frozen.frozen_input_hash,
                self.sources, self.fixture.bundle, self.fixture.policy_registry)
        foreign, foreign_sources = self.distinct_root()
        self.assertNotEqual(foreign.bundle.manifest.manifest_hash,
            self.fixture.bundle.manifest.manifest_hash)
        for source in foreign_sources:
            source.require_verified()
        swapped = (foreign_sources.base, self.sources.policy, self.sources.valuation)
        closure["verify_sources"](swapped)
        with self.assertRaises(ValueError):
            closure["close_identity"](self.fixture.frozen,
                self.fixture.frozen.frozen_input_hash, swapped,
                self.fixture.bundle, self.fixture.policy_registry)

    def test_raw_v_percentile_cannot_replace_stage_c_score(self):
        fixture = CrossoverFinalScoringFixture(peer_count=20)
        self.addCleanup(fixture.close)
        fixture.populate_final_inputs()
        repository = FormalFinalScoreInputRepository(
            fixture.feature_repository, fixture.context, fixture.range_store,
            registry_signature_verifier=fixture.verifier)
        batch = repository.build_batch(fixture.frozen.frozen_input_hash,
            scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry,
            valuation_adapter_registry=fixture.valuation_registry)
        self.assertEqual(len(batch.security_ids), 20)
        row = batch.input_for(FOCAL)
        self.assertEqual(row.status, "ready")
        self.assertEqual(len(row.slots), 25)
        record = inspect.getclosurevars(type(row).require_verified).nonlocals["record"]
        proofs = inspect.getclosurevars(record).nonlocals["proofs"]
        saved = proofs[id(row)]
        sources = saved[5][1]
        for source in sources:
            source.require_verified()
        mid = "V.normalized_earnings_yield"
        raw_percentile = sources[0].input_for(FOCAL).slots[mid]["value"]
        stage_c_percentile = row.slots[mid]["value"]
        self.assertNotEqual(Decimal(str(raw_percentile)),
            Decimal(str(stage_c_percentile)))
        self.assertEqual(Decimal(str(row.slots[mid]["valuation_score"]["percentile"])),
            Decimal(str(stage_c_percentile)))

        tampered = row.to_dict()
        tampered["slots"][mid]["value"] = raw_percentile
        proofs[id(row)] = (saved[0], formal_metric_engine._freeze(tampered),
            saved[2], *saved[3:])
        try:
            with self.assertRaises(ValueError):
                row.require_verified()
            with self.assertRaises(ValueError):
                batch.input_for(FOCAL)
        finally:
            proofs[id(row)] = saved
        row.require_verified()

    def test_forged_copied_pickled_inherited_or_weakref_redirected_proofs_are_rejected(self):
        row = self.batch.input_for(FOCAL)
        for proof_type in (PolicyAdjustedScoreInput, PolicyAdjustedScoreInputBatch):
            with self.subTest(proof_type=proof_type.__name__, attack="constructor"):
                with self.assertRaises(TypeError):
                    proof_type()
            with self.subTest(proof_type=proof_type.__name__, attack="forgery"):
                forged = object.__new__(proof_type)
                with self.assertRaises(ValueError):
                    forged.require_verified()
        for proof in (row, self.batch):
            with self.subTest(type=type(proof).__name__, attack="copy"):
                with self.assertRaises(TypeError):
                    copy.copy(proof)
                with self.assertRaises(TypeError):
                    copy.deepcopy(proof)
                with self.assertRaises(TypeError):
                    pickle.dumps(proof)
                forged = object.__new__(type(proof))
                with self.assertRaises(ValueError):
                    weakref.proxy(forged).require_verified()
        with self.assertRaises(TypeError):
            class InheritedProof(PolicyAdjustedScoreInput):
                pass

    def test_v1_root_prepolicy_and_plain_v2_objects_cannot_impersonate_d1(self):
        legacy = PolicyRuntimeFixture()
        self.addCleanup(legacy.close)
        self.assertEqual(legacy.bundle.manifest.schema_version,
            "formal-registry-manifest-v1")
        snapshot = inspect.getclosurevars(
            FormalFinalScoreInputRepository.build_batch).nonlocals["registry_snapshot"]
        with self.assertRaisesRegex(ValueError, "authenticated v2 root"):
            snapshot(legacy.feature_repository, legacy.verifier,
                legacy.bundle.manifest.manifest_hash, legacy.scoring,
                legacy.policy_registry, self.fixture.valuation_registry)
        self.assertNotIsInstance(self.sources.base, PolicyAdjustedScoreInputBatch)
        self.assertIsInstance(self.sources.base, FormalScoreInputBatch)
        for candidate in (self.sources.base, self.sources.policy, self.sources.valuation,
                          self.batch.to_dict(), self.batch.input_for(FOCAL).to_dict()):
            with self.subTest(type=type(candidate).__name__):
                self.assertNotIsInstance(candidate, PolicyAdjustedScoreInputBatch)
                self.assertNotIsInstance(candidate, PolicyAdjustedScoreInput)
        with self.assertRaises(TypeError):
            PolicyAdjustedScoreInputBatch(**self.batch.to_dict())

    def test_method_or_encoder_replacement_is_rejected(self):
        original = formal_metric_engine._freeze
        formal_metric_engine._freeze = lambda value: value
        try:
            with self.assertRaises(ValueError):
                self.batch.require_verified()
            with self.assertRaises(ValueError):
                self.build()
        finally:
            formal_metric_engine._freeze = original
        original_encoder = json.encoder._make_iterencode
        json.encoder._make_iterencode = lambda *args, **kwargs: original_encoder(*args, **kwargs)
        try:
            with self.assertRaises(ValueError):
                self.batch.require_verified()
        finally:
            json.encoder._make_iterencode = original_encoder
        original_method = FormalScoreInputBatch.input_for
        type.__setattr__(FormalScoreInputBatch, "input_for", lambda *args: None)
        try:
            with self.assertRaises(ValueError):
                self.batch.require_verified()
        finally:
            type.__setattr__(FormalScoreInputBatch, "input_for", original_method)
        self.batch.require_verified()

    def _revoked_children(self):
        if hasattr(type(self), "revoked_children"):
            return type(self).revoked_children
        fixture = self.fixture
        member = next(m for m in fixture.industry["memberships"] if m["security_id"] == FOCAL)
        snapshot = fixture.resolve_current_inputs(
            security_id=FOCAL, as_of_utc=FREEZE,
            template_id=member["template_id"],
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash)
        captured = []
        fired = False

        def intercept(frame, event, arg):
            nonlocal fired
            if (event == "call" and not fired and frame.f_code.co_name == "publish"
                    and frame.f_code.co_filename.endswith("formal_final_score_inputs.py")):
                fired = True
                captured.extend(frame.f_locals["children"])
                try:
                    fixture.provider.publish(snapshot)
                except ValueError:
                    pass

        old_profile = sys.getprofile()
        sys.setprofile(intercept)
        try:
            with self.assertRaises(ValueError):
                self.build()
        finally:
            sys.setprofile(old_profile)
        self.assertTrue(fired)
        self.assertEqual(len(captured), len(self.batch.security_ids))
        type(self).revoked_children = tuple(captured)
        return type(self).revoked_children

    def test_source_change_during_final_sweep_revokes_all_d1_children(self):
        for index, child in enumerate(self._revoked_children()):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    child.require_verified()

    def test_capability_cannot_be_replayed_across_batch_or_context(self):
        foreign_fixture, _ = self.distinct_root()
        foreign_repository = FormalFinalScoreInputRepository(
            foreign_fixture.feature_repository, foreign_fixture.context,
            foreign_fixture.range_store,
            registry_signature_verifier=foreign_fixture.verifier)
        foreign_batch = foreign_repository.build_batch(
            foreign_fixture.frozen.frozen_input_hash,
            scoring_registry=foreign_fixture.scoring,
            policy_registry=foreign_fixture.policy_registry,
            valuation_adapter_registry=foreign_fixture.valuation_registry)
        foreign_child = foreign_batch.input_for(FOCAL)
        foreign_batch.require_verified()
        foreign_child.require_verified()
        self.assertNotEqual(foreign_batch.registry_manifest_hash,
            self.batch.registry_manifest_hash)
        self.batch.require_verified()
        self.assertIsNot(foreign_child, self.batch.input_for(FOCAL))
        record = inspect.getclosurevars(type(self.batch).input_for).nonlocals["record"]
        proofs = inspect.getclosurevars(record).nonlocals["proofs"]
        saved = proofs[id(self.batch)]
        crossed = dict(saved[3])
        crossed[FOCAL] = foreign_child
        proofs[id(self.batch)] = saved[:3] + (MappingProxyType(crossed),) + saved[4:]
        try:
            with self.assertRaises(ValueError):
                self.batch.input_for(FOCAL)
        finally:
            proofs[id(self.batch)] = saved
        foreign_child.require_verified()
        foreign_batch.require_verified()
        with self.assertRaises(ValueError):
            self.batch.input_for(123)


if __name__ == "__main__":
    unittest.main()
