"""Offline scoring registry contract and signed graph boundary tests."""

import copy
import hashlib
import hmac
import importlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import unittest

from ashare_pipeline.formal_feature_contract import load_signed_feature_registry
from ashare_pipeline.formal_registry_manifest import (
    FormalRegistryBundleLoader, FormalRegistryManifest, VerifiedRegistryBlob,
)
from tests.test_formal_registry_manifest import InMemoryRepository, ROLES


FIXTURE = Path(__file__).parent / "fixtures" / "formal_v3_test_registry.json"
TEMPLATES = ("general_nonfinancial", "bank", "broker", "insurance", "real_estate")
WEIGHTS = {"G": "0.18", "V": "0.18", "M": "0.18", "EQ": "0.12", "FS": "0.08", "CA": "0.16", "T": "0.10"}
INTERNAL = {"G": ("0.35", "0.25", "0.25", "0.15"), "V": ("0.45", "0.25", "0.30"),
    "M": ("0.40", "0.30", "0.30"), "EQ": ("0.35", "0.25", "0.20", "0.20"),
    "FS": ("0.40", "0.35", "0.25"), "CA": ("0.35", "0.30", "0.20", "0.15"),
    "T": ("0.35", "0.25", "0.25", "0.15")}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fixture_wire():
    return json.loads(FIXTURE.read_bytes())


class HmacVerifier:
    """A real byte-sensitive offline signature verifier with a test-only key."""
    def sign(self, raw):
        return hmac.new(b"scoring-contract-test-only-key", raw, hashlib.sha256).hexdigest()

    def verify(self, raw, *, signature, key_id):
        return key_id == "scoring-test-key" and hmac.compare_digest(self.sign(raw), signature)


def signed_graph(*, mutate=None, context=False):
    """Author one complete synthetic official-wire graph, never promote the test registry by approval."""
    verifier = HmacVerifier()
    wrapper = fixture_wire()
    scoring = wrapper["scoring"]
    slots = scoring.pop("fixture_feature_slots")
    policies = scoring.pop("fixture_policies")
    scoring["purpose"] = "official"
    configs = []
    if context:
        from tests.test_formal_context_repository import descriptor
        from tests.test_formal_sources import config
        wrapper["descriptors"] = [descriptor()]
        configs = [config(dataset="fixture-state", exchange_scope="SZ")]
    documents = {role: dict(registry_role=role, schema_version="fixture-v1") for role in ROLES}
    documents["source"] = dict(registry_role="source", schema_version="formal-source-registry-v1", configs=configs)
    documents["feature"] = dict(registry_role="feature", schema_version="formal-feature-registry-v1",
        contract_version="formal-features-v1", source_registry_hash=hashlib.sha256(canonical(documents["source"])).hexdigest(),
        mapping_registry_hash=hashlib.sha256(canonical(documents["mapping"])).hexdigest(),
        template_ids=sorted(TEMPLATES), slots=sorted(slots, key=lambda s: s["slot_id"]))
    for role, policy in policies.items():
        policy["purpose"] = "official"
        documents[role] = policy
        scoring["policy_contracts"][role]["registry_hash"] = hashlib.sha256(canonical(policy)).hexdigest()
    documents["scoring"] = wrapper
    if mutate:
        mutate(documents)
    raws = {role: canonical(doc) for role, doc in documents.items()}
    hashes = {role + "_registry_hash": hashlib.sha256(raw).hexdigest() for role, raw in raws.items()}
    root = canonical(dict(schema_version="formal-registry-manifest-v1", purpose="official", approval_id="test-graph-approval", **hashes))
    manifest = FormalRegistryManifest.from_signed_bytes(root, verifier.sign(root), "scoring-test-key", verifier)
    blobs = {}
    for role, raw in raws.items():
        digest = hashlib.sha256(raw).hexdigest()
        binding = canonical(dict(child_sha256=digest, registry_manifest_hash=manifest.manifest_hash, registry_role=role))
        blobs[digest] = VerifiedRegistryBlob(role, digest, raw, verifier.sign(raw), "scoring-test-key",
            manifest.approval_id, manifest.manifest_hash, verifier.sign(binding), "scoring-test-key")
    repository = InMemoryRepository(manifest, blobs)
    bundle = FormalRegistryBundleLoader(repository, verifier).load(manifest.manifest_hash)
    feature = bundle.blob("feature")
    vocabulary = load_signed_feature_registry(feature.canonical_json, feature.signature, feature.key_id, verifier, registry_manifest=bundle.manifest)
    return bundle, vocabulary, repository, verifier


class FormalScoringRegistryTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("ashare_pipeline.formal_scoring_registry")

    def load_test(self, wire=None):
        return self.api.load_formal_registry(FIXTURE if wire is None else canonical(wire), self.api.RegistryApproval.for_test_fixture())

    def load_official(self, bundle, vocabulary, approval=None):
        approval = approval or self.api.RegistryApproval("official", bundle.manifest.scoring_registry_hash, bundle.manifest.approval_id)
        return self.api.load_formal_registry(bundle, approval, feature_registry=vocabulary)

    def test_all_five_templates_preserve_exact_seven_dimension_slots_and_weights(self):
        registry = self.load_test()
        self.assertEqual(tuple(registry.templates), TEMPLATES)
        self.assertEqual(registry.dimension_weights, {k: Decimal(v) for k, v in WEIGHTS.items()})
        self.assertEqual(registry.internal_weights, {k: tuple(map(Decimal, v)) for k, v in INTERNAL.items()})
        for template in TEMPLATES:
            for dimension, weights in INTERNAL.items():
                metrics = registry.template_for(template).metrics[dimension]
                self.assertEqual(tuple(m.internal_weight for m in metrics), tuple(map(Decimal, weights)))
                for metric in metrics:
                    self.assertEqual(metric.required_feature_keys, (metric.field_map["value"],))
                    self.assertEqual(metric.formula["feature_key"], metric.field_map["value"])
                    self.assertEqual(metric.original_formula["period_key"], "FY0")
                    self.assertEqual(metric.period_rule, ("FY0",))
        self.assertEqual(registry.cyclic_secondary_industries, frozenset({"fixture-cyclic"}))
        with self.assertRaises(self.api.RegistryValidationError):
            registry.template_for("unknown")

    def test_complete_official_graph_is_accepted_and_all_nine_children_are_bound(self):
        bundle, vocabulary, _, _ = signed_graph()
        registry = self.load_official(bundle, vocabulary)
        registry.require_official(bundle)
        self.assertEqual(registry.content_sha256, hashlib.sha256(bundle.blob("scoring").canonical_json).hexdigest())
        self.assertEqual(registry.registry_manifest_hash, bundle.manifest.manifest_hash)
        self.assertEqual(set(registry.role_hashes), set(ROLES))
        self.assertEqual(registry.redlines[0].rule["evidence_kind"], "fixture-redline")

    def test_test_purpose_cannot_be_promoted_by_official_approval(self):
        bundle, vocabulary, _, _ = signed_graph()
        with self.assertRaisesRegex(self.api.RegistryValidationError, "official"):
            self.load_test().require_official(bundle)
        raw = FIXTURE.read_bytes()
        approval = self.api.RegistryApproval("official", hashlib.sha256(raw).hexdigest(), "test-graph-approval")
        with self.assertRaisesRegex(self.api.RegistryValidationError, "bundle|official"):
            self.api.load_formal_registry(raw, approval, feature_registry=vocabulary)
        def test_scoring(docs):
            docs["scoring"]["scoring"]["purpose"] = "test"
        test_bundle, _, _, _ = signed_graph(mutate=test_scoring)
        with self.assertRaises(self.api.RegistryValidationError):
            self.load_official(test_bundle, vocabulary)

    def test_official_approval_requires_matching_hash_id_and_purpose(self):
        bundle, vocabulary, _, _ = signed_graph()
        for approval in (self.api.RegistryApproval("official", None, "test-graph-approval"),
            self.api.RegistryApproval("official", "0" * 64, "test-graph-approval"),
            self.api.RegistryApproval("official", bundle.manifest.scoring_registry_hash, None),
            self.api.RegistryApproval("official", bundle.manifest.scoring_registry_hash, "another"),
            self.api.RegistryApproval.for_test_fixture()):
            with self.subTest(approval=approval), self.assertRaises(self.api.RegistryValidationError):
                self.load_official(bundle, vocabulary, approval)

    def test_metric_missing_contract_fields_fail_closed(self):
        fields = ("field_map", "formula", "formula_version", "field_map_version", "direction", "unit_rule", "period_rule",
            "denominator_rule", "invalid_denominator_rule", "required_feature_keys", "equivalence_description", "source_evidence_categories", "policy_refs")
        for field in fields:
            wire = fixture_wire()
            del wire["scoring"]["templates"]["bank"]["metrics"]["V"][0][field]
            with self.subTest(field=field), self.assertRaisesRegex(self.api.RegistryValidationError, field):
                self.load_test(wire)

    def test_slot_weight_identity_or_template_deletion_is_rejected(self):
        for mutation in (lambda s: s["templates"].pop("insurance"),
            lambda s: s["templates"]["bank"]["metrics"]["V"].pop(),
            lambda s: s["dimension_weights"].update(G="0.19", V="0.17"),
            lambda s: s["internal_weights"]["G"].__setitem__(0, "0.34"),
            lambda s: s["templates"]["bank"]["metrics"]["G"][0].update(internal_weight="0.34"),
            lambda s: s["templates"]["bank"]["metrics"]["G"][0].update(metric_id="wrong_concept")):
            wire = fixture_wire()
            mutation(wire["scoring"])
            with self.subTest(mutation=mutation), self.assertRaises(self.api.RegistryValidationError):
                self.load_test(wire)

    def test_unknown_or_cross_template_feature_and_mismatched_contract_are_rejected(self):
        for change in ({"required_feature_keys": ["unknown"]}, {"field_map": {"value": "general_nonfinancial.G.operating_profit_per_share_cagr_3y"}},
            {"formula_version": "other-v2"}, {"unit_rule": "CNY"}, {"period_rule": ["FY1"]},
            {"denominator_rule": "positive"}, {"invalid_denominator_rule": "zero"},
            {"formula": {"op": "constant", "value": "100"}}, {"direction": "unknown"}):
            wire = fixture_wire()
            wire["scoring"]["templates"]["bank"]["metrics"]["G"][0].update(change)
            with self.subTest(change=change), self.assertRaises(self.api.RegistryValidationError):
                self.load_test(wire)

    def test_signed_divide_and_cagr_preserve_actual_v6_denominator_semantics(self):
        left = {"op": "fact", "fact_key": "fixture.numerator", "period_key": "FY0"}
        right = {"op": "fact", "fact_key": "fixture.denominator", "period_key": "FY1"}
        divide = {"op": "divide", "left": left, "right": right}
        cagr = {"op": "cagr", "left": left, "right": right, "intervals": 3}
        cases = ((divide, "nonzero"), (cagr, "positive_endpoints"),
            ({"op": "divide", "left": cagr, "right": right}, "nonzero_divisors_and_positive_cagr_endpoints"))
        for formula, rule in cases:
            def mutate(docs, formula=formula, rule=rule):
                metric = docs["scoring"]["scoring"]["templates"]["bank"]["metrics"]["G"][0]
                key = metric["required_feature_keys"][0]
                slot = next(s for s in docs["feature"]["slots"] if s["slot_id"] == key)
                slot["formula"] = formula
                metric.update(period_rule=["FY0", "FY1"], denominator_rule=rule)
            bundle, vocabulary, _, _ = signed_graph(mutate=mutate)
            with self.subTest(rule=rule):
                try:
                    registry = self.load_official(bundle, vocabulary)
                except self.api.RegistryValidationError as error:
                    self.fail(f"the registry must preserve V6 {rule} semantics: {error}")
                metric = registry.template_for("bank").metrics["G"][0]
                self.assertEqual(metric.denominator_rule, rule)
                self.assertEqual(metric.original_formula["left"]["op"], formula["left"]["op"])

    def test_high_precision_decimal_weights_are_not_rounded_into_valid_weights(self):
        wire = fixture_wire()
        wire["scoring"]["dimension_weights"]["G"] = "0.18000000000000000000000000000000001"
        wire["scoring"]["dimension_weights"]["V"] = "0.17999999999999999999999999999999999"
        with self.assertRaises(self.api.RegistryValidationError):
            self.load_test(wire)

    def test_official_feature_vocabulary_must_be_exact_sealed_and_same_graph(self):
        bundle, vocabulary, _, _ = signed_graph()
        def different_feature(docs):
            docs["feature"]["contract_version"] = "formal-features-v2"
        _, other, _, _ = signed_graph(mutate=different_feature)
        for candidate in (None, object(), copy.copy(vocabulary), other):
            with self.subTest(candidate=type(candidate)), self.assertRaises(self.api.RegistryValidationError):
                self.load_official(bundle, candidate)
        object.__setattr__(vocabulary, "registry_hash", "0" * 64)
        with self.assertRaises(self.api.RegistryValidationError):
            self.load_official(bundle, vocabulary)

    def test_official_required_key_must_exist_in_its_signed_template(self):
        def missing_slot(docs):
            docs["feature"]["slots"].pop()
        bundle, vocabulary, _, _ = signed_graph(mutate=missing_slot)
        with self.assertRaisesRegex(self.api.RegistryValidationError, "feature"):
            self.load_official(bundle, vocabulary)

    def test_mixed_root_and_mutated_bundle_are_rejected_on_reuse(self):
        bundle, vocabulary, _, _ = signed_graph()
        registry = self.load_official(bundle, vocabulary)
        other, _, _, _ = signed_graph(mutate=lambda d: d["industry"].update(version="other"))
        with self.assertRaisesRegex(self.api.RegistryValidationError, "manifest"):
            registry.require_official(other)
        object.__setattr__(bundle.blob("event"), "canonical_json", b"{}")
        with self.assertRaises(self.api.RegistryValidationError):
            registry.require_official(bundle)

    def test_every_policy_role_binds_hash_version_categories_purpose_and_rule_ids(self):
        for role in ("cyclic", "redline", "status", "event"):
            for field in ("registry_hash", "registry_version", "source_evidence_categories"):
                wire = fixture_wire()
                del wire["scoring"]["policy_contracts"][role][field]
                with self.subTest(role=role, field=field), self.assertRaisesRegex(self.api.RegistryValidationError, field):
                    self.load_test(wire)
            for field, value in (("registry_hash", "0" * 64), ("registry_version", "other"), ("source_evidence_categories", ["other"])):
                wire = fixture_wire()
                wire["scoring"]["policy_contracts"][role][field] = value
                with self.subTest(role=role, field=field), self.assertRaises(self.api.RegistryValidationError):
                    self.load_test(wire)
        for role in ("cyclic", "redline", "status", "event"):
            for field, value in (("purpose", "test"), ("rules", {}), ("registry_version", ""), ("source_evidence_categories", []), ("registry_role", "other")):
                def mutate(docs, role=role, field=field, value=value):
                    docs[role][field] = value
                    docs["scoring"]["scoring"]["policy_contracts"][role]["registry_hash"] = hashlib.sha256(canonical(docs[role])).hexdigest()
                if field == "registry_role":
                    with self.assertRaises(ValueError):
                        signed_graph(mutate=mutate)
                    continue
                bundle, vocabulary, _, _ = signed_graph(mutate=mutate)
                with self.subTest(role=role, field=field), self.assertRaises(self.api.RegistryValidationError):
                    self.load_official(bundle, vocabulary)

    def test_noncanonical_duplicate_nonfinite_and_malformed_json_are_rejected(self):
        raw = FIXTURE.read_bytes()
        for bad in (b" " + raw, raw + b"\n", b"\xff", b"[]", b'{"a":NaN}', b'{"a":Infinity}',
            b'{"a":1,"a":2}', raw.replace(b'"0.18"', b'0.18', 1)):
            with self.subTest(raw=bad[:25]), self.assertRaises(self.api.RegistryValidationError):
                self.api.load_formal_registry(bad, self.api.RegistryApproval.for_test_fixture())

    def test_nested_records_are_immutable_and_forced_mutation_invalidates_seal(self):
        bundle, vocabulary, _, _ = signed_graph()
        registry = self.load_official(bundle, vocabulary)
        metric = registry.template_for("bank").metrics["V"][0]
        for mutate in (lambda: registry.templates.__setitem__("bank", None),
            lambda: metric.field_map.__setitem__("value", "unknown"),
            lambda: metric.original_formula.__setitem__("period_key", "FY1"),
            lambda: registry.redlines[0].rule.__setitem__("x", "1")):
            with self.assertRaises((AttributeError, TypeError)):
                mutate()
        object.__setattr__(metric, "direction", "lower")
        with self.assertRaises(self.api.RegistryValidationError):
            registry.require_official(bundle)

    def test_copied_forged_and_approval_mutated_registries_cannot_be_official(self):
        bundle, vocabulary, _, _ = signed_graph()
        registry = self.load_official(bundle, vocabulary)
        for fake in (copy.copy(registry), object.__new__(self.api.FormalScoringRegistry)):
            with self.assertRaises(self.api.RegistryValidationError):
                fake.require_official(bundle)
        object.__setattr__(registry.approval, "approved_content_sha256", "0" * 64)
        with self.assertRaises(self.api.RegistryValidationError):
            registry.require_official(bundle)

    def test_outer_child_binding_signature_is_verified_before_scoring(self):
        bundle, _, repository, verifier = signed_graph()
        blob = bundle.blob("redline")
        repository.blobs[blob.registry_hash] = replace(blob, binding_signature=verifier.sign(b"wrong-root"))
        with self.assertRaisesRegex(ValueError, "signature"):
            FormalRegistryBundleLoader(repository, verifier).load(bundle.manifest.manifest_hash)


if __name__ == "__main__":
    unittest.main()
