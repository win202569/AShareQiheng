"""Real signed graphs exercise definition proof ownership, never runtime evidence."""

import copy
import gc
import hashlib
import json
import pickle
import sys
import unittest
import weakref
from unittest.mock import patch

from ashare_pipeline import formal_context_schema as context_module
from ashare_pipeline import formal_feature_contract as feature_module
from ashare_pipeline import formal_policy_contract as contract_module
from ashare_pipeline import formal_policy_registry as policy_module
from ashare_pipeline import formal_registry_manifest as manifest_module
from ashare_pipeline import formal_scoring_registry as scoring_module
from ashare_pipeline import formal_sources as sources_module
from ashare_pipeline.formal_policy_registry import (
    FormalPolicyRegistry, load_formal_policy_registry,
)
from ashare_pipeline.formal_scoring import calculate_pre_policy_score
from tests.formal_policy_fixtures import policy_graph


class _PolicyGraphTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle, cls.feature, cls.scoring, _, _ = policy_graph()

    def load(self, **overrides):
        arguments = dict(bundle=self.bundle, scoring_registry=self.scoring,
            feature_registry=self.feature)
        arguments.update(overrides)
        return load_formal_policy_registry(**arguments)


class PolicyProofTests(_PolicyGraphTestCase):
    def test_loaded_contract_is_immutable_but_does_not_grant_runtime_readiness(self):
        proof = self.load()
        proof.require_verified()
        raw = proof.canonical_bytes()
        self.assertEqual(proof.contract_hash, hashlib.sha256(raw).hexdigest())
        self.assertNotIn("contract_hash", json.loads(raw))
        self.assertEqual(proof.to_dict()["contract_hash"], proof.contract_hash)
        self.assertEqual(proof.to_dict()["role_hashes"], dict(self.scoring.role_hashes))
        self.assertEqual(len(proof.rules), 80)
        self.assertEqual(len(proof.binding_manifest), 170)
        for forbidden in ("pool_eligible", "policy_ready", "evaluate", "apply", "score",
                "security_id", "market_window", "adapter", "__dict__"):
            with self.subTest(name=forbidden), self.assertRaises(AttributeError):
                getattr(proof, forbidden)
        changed = proof.to_dict()
        changed["role_hashes"]["status"] = "0" * 64
        changed["rules"][0]["inputs"].clear()
        proof.require_verified()
        self.assertNotEqual(proof.to_dict(), changed)
        with self.assertRaises(AttributeError):
            proof.contract_hash = "0" * 64
        with self.assertRaises(TypeError):
            proof.rules[0]["inputs"]["current_roe"]["period_keys"] = ()
        with self.assertRaises(TypeError):
            proof.rules[0]["outcomes"]["on_match"][0]["maximum"] = "100"

    def test_direct_and_unregistered_proofs_are_rejected(self):
        with self.assertRaises(TypeError):
            FormalPolicyRegistry()
        forged = object.__new__(FormalPolicyRegistry)
        for access in (lambda: forged.require_verified(), lambda: forged.contract_hash,
                lambda: forged.canonical_bytes(), lambda: forged.to_dict()):
            with self.assertRaises(ValueError):
                access()

    def test_bound_bytes_remain_identical_and_loads_are_deterministic(self):
        proof = self.load()
        expected = policy_module._bind_policy_contract(self.bundle,
            scoring_registry=self.scoring, feature_registry=self.feature)
        self.assertEqual(proof.canonical_bytes(), expected)
        self.assertEqual(self.load().canonical_bytes(), expected)


class PolicyProofGuardTests(_PolicyGraphTestCase):
    def assert_rejected(self, proof):
        for access in (lambda: proof.require_verified(), lambda: proof.contract_hash,
                lambda: proof.rules, lambda: proof.canonical_bytes(), lambda: proof.to_dict(),
                lambda: self.load()):
            with self.assertRaises(ValueError):
                access()

    def test_copied_inputs_are_not_authenticated(self):
        proof = self.load()
        for name, original in (("bundle", self.bundle), ("feature_registry", self.feature),
                ("scoring_registry", self.scoring)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.load(**{name: copy.copy(original)})
        proof.require_verified()

    def test_copied_pickled_and_subclass_proofs_cannot_acquire_ownership(self):
        proof = self.load()
        for clone in (copy.copy, copy.deepcopy, pickle.dumps,
                lambda p: p.__reduce__(), lambda p: p.__reduce_ex__(4)):
            with self.subTest(clone=clone), self.assertRaises(TypeError):
                clone(proof)
        class Derived(FormalPolicyRegistry):
            __slots__ = ()
        forged = object.__new__(Derived)
        with self.assertRaises(ValueError):
            forged.require_verified()
        proof.require_verified()

    def test_other_roots_and_changed_feature_content_are_rejected(self):
        proof = self.load()
        def change(documents):
            next(s for s in documents["feature"]["slots"]
                if s["slot_id"] == "bank.policy.equity")["formula"]["fact_key"] = "fixture.changed"
        bundle, feature, scoring, _, _ = policy_graph(mutate=change)
        load_formal_policy_registry(bundle, scoring_registry=scoring, feature_registry=feature).require_verified()
        for overrides in (dict(bundle=bundle), dict(scoring_registry=scoring), dict(feature_registry=feature)):
            with self.subTest(overrides=tuple(overrides)), self.assertRaises(ValueError):
                self.load(**overrides)
        proof.require_verified()

    def test_mutated_source_fields_invalidate_existing_proof_and_loader(self):
        proof = self.load()
        for source, name, replacement in (
                (self.feature, "registry_hash", "0" * 64),
                (self.feature, "slots", ()),
                (self.scoring, "content_sha256", "0" * 64),
                (self.bundle.manifest, "canonical_json", b"{}"),
                (self.bundle.blob("event"), "canonical_json", b"{}")):
            original = object.__getattribute__(source, name)
            try:
                object.__setattr__(source, name, replacement)
                with self.subTest(name=name):
                    self.assert_rejected(proof)
            finally:
                object.__setattr__(source, name, original)
        proof.require_verified()

    def test_replaced_module_types_and_module_aliases_fail_closed(self):
        proof = self.load()
        for module, name in (
                (policy_module, "VerifiedRegistryBundle"), (policy_module, "FormalScoringRegistry"),
                (policy_module, "SignedFormalFeatureRegistry"), (policy_module, "FormalPolicyRegistry"),
                (manifest_module, "VerifiedRegistryBundle"), (manifest_module, "FormalRegistryManifest"),
                (manifest_module, "VerifiedRegistryBlob"), (feature_module, "SignedFormalFeatureRegistry"),
                (feature_module, "FormalFeatureSlot"), (feature_module, "FormulaNode"),
                (scoring_module, "FormalScoringRegistry"), (scoring_module, "SignedFormalFeatureRegistry"),
                (scoring_module, "VerifiedRegistryBundle"), (contract_module, "PolicyRule"),
                (contract_module, "ParsedPolicyContract"), (policy_module, "json"),
                (policy_module, "hashlib")):
            with self.subTest(module=module.__name__, name=name), patch.object(module, name, object()):
                self.assert_rejected(proof)
        proof.require_verified()

    def test_replaced_parser_binder_encoder_and_owner_helpers_fail_closed(self):
        proof = self.load()
        for module, name in (
                (policy_module, "parse_policy_contract"), (contract_module, "parse_policy_contract"),
                (contract_module, "parse_policy_rule"), (contract_module, "_validate_outcomes"),
                (policy_module, "_bind_policy_contract"), (policy_module, "_bind_selectors"),
                (policy_module, "_require_coverage"), (policy_module, "_canonical"),
                (policy_module, "_freeze"), (policy_module, "load_formal_policy_registry"),
                (scoring_module, "_graph"), (scoring_module, "_feature_slots"),
                (scoring_module, "_formula_requirements"), (feature_module, "_parse_registry_bytes"),
                (feature_module, "_formula_to_dict"), (context_module, "_descriptor"),
                (context_module, "_canonical")):
            with self.subTest(module=module.__name__, name=name), patch.object(module, name, lambda *a, **k: None):
                self.assert_rejected(proof)
        proof.require_verified()

    def test_replaced_hash_json_freeze_and_weakref_dependencies_fail_closed(self):
        proof = self.load()
        for module, name in ((hashlib, "sha256"), (json, "loads"), (json, "dumps"),
                (weakref, "ref"), (policy_module, "MappingProxyType")):
            with self.subTest(name=name), patch.object(module, name, lambda *a, **k: None):
                self.assert_rejected(proof)
        proof.require_verified()

    def test_replaced_exchange_enum_invalidates_reads_and_loads_until_restored(self):
        proof = self.load()
        proof.require_verified()
        with patch.object(sources_module, "_EXCHANGES", frozenset({"SH", "SZ", "BJ", "FAKE"})):
            self.assert_rejected(proof)
        proof.require_verified()
        self.load().require_verified()

    def test_replaced_upstream_verifiers_and_slots_fail_closed(self):
        proof = self.load()
        for cls, method in ((type(self.bundle), "require_official"), (type(self.bundle), "blob"),
                (type(self.scoring), "require_official"), (type(self.feature), "require_release_eligible"),
                (type(self.feature), "slots_for_template"), (type(self.feature), "__getattribute__"),
                (feature_module.FormalFeatureSlot, "to_dict")):
            with self.subTest(method=method), patch.object(cls, method, lambda *a: None):
                self.assert_rejected(proof)
        proof.require_verified()

    def test_replacing_class_verifier_or_shadowing_field_cannot_bypass_lookup(self):
        proof = self.load()
        for cls in (FormalPolicyRegistry, FormalPolicyRegistry.__bases__[0]):
            for name, replacement in (("require_verified", lambda self: None),
                    ("contract_hash", "0" * 64), ("to_dict", lambda self: {})):
                with self.subTest(cls=cls.__name__, name=name), patch.object(cls, name, replacement, create=True):
                    self.assert_rejected(proof)
        proof.require_verified()

    def test_lookup_and_inheritance_cannot_be_replaced_or_deleted(self):
        proof = self.load()
        for cls in (FormalPolicyRegistry, FormalPolicyRegistry.__bases__[0]):
            for name, value in (("__getattribute__", lambda *a: True), ("__bases__", (object,))):
                with self.subTest(name=name), self.assertRaises(TypeError):
                    setattr(cls, name, value)
                with self.assertRaises(TypeError):
                    delattr(cls, name)
        proof.require_verified()

    def test_definition_reads_do_not_reparse_or_rebind_policy(self):
        proof = self.load()
        forbidden_codes = {policy_module._bind_policy_contract.__code__,
            contract_module.parse_policy_contract.__code__, contract_module.parse_policy_rule.__code__}
        calls = []
        previous = sys.getprofile()
        def trace(frame, event, arg):
            if event == "call" and frame.f_code in forbidden_codes:
                calls.append(frame.f_code.co_name)
        try:
            sys.setprofile(trace)
            proof.require_verified()
            proof.contract_hash
            proof.canonical_bytes()
            proof.to_dict()
        finally:
            sys.setprofile(previous)
        self.assertEqual(calls, [])

    def test_source_changed_during_binding_cannot_publish_proof(self):
        self.load().require_verified()
        previous = sys.getprofile()
        original = object.__getattribute__(self.feature, "registry_hash")
        bind_code = policy_module._bind_policy_contract.__code__
        def trace(frame, event, arg):
            if event == "return" and frame.f_code is bind_code:
                object.__setattr__(self.feature, "registry_hash", "0" * 64)
        try:
            sys.setprofile(trace)
            with self.assertRaises(ValueError):
                self.load()
        finally:
            sys.setprofile(previous)
            object.__setattr__(self.feature, "registry_hash", original)
        self.load().require_verified()

    def test_discarded_proof_is_not_kept_alive_by_ownership_table(self):
        proof, survivor = self.load(), self.load()
        reference = weakref.ref(proof)
        del proof
        gc.collect()
        self.assertIsNone(reference())
        survivor.require_verified()

    def test_declarations_and_detached_values_are_not_score_inputs(self):
        proof = self.load()
        rules = proof.rules
        market = next(r for r in rules if r["kind"] == "market_liquidity")
        self.assertEqual(market["parameters"]["required_evidence_capability"], "verified_market_window_v1")
        self.assertEqual(market["inputs"]["market"]["expected_type"], "market_record")
        self.assertNotIn("value", market["inputs"]["market"])
        affected = next(d for d in proof.valuation_dependencies["bank"] if d["policy_dependency"] == "affected")
        self.assertEqual(affected["adapter_id"], "fixture_profit_adapter")
        parsed = contract_module.parse_policy_contract({role: self.bundle.blob(role).canonical_json
            for role in ("cyclic", "redline", "status", "event")})
        for value in (proof, parsed, parsed.rules[0], proof.canonical_bytes(), proof.to_dict()):
            with self.subTest(kind=type(value)), self.assertRaises(ValueError):
                calculate_pre_policy_score(value)


if __name__ == "__main__":
    unittest.main()
