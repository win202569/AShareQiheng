"""Signed valuation adapter definitions bind exactly to same-root policy and metrics."""

import copy
import unittest

from ashare_pipeline.formal_policy_registry import load_formal_policy_registry
from ashare_pipeline.formal_valuation_adapter_contract import (
    FormalValuationAdapterRegistry, load_formal_valuation_adapter_registry,
)
from tests.formal_policy_fixtures import policy_graph


def load_graph(*, mutate=None):
    bundle, vocabulary, scoring, _, _ = policy_graph(
        manifest_version="formal-registry-manifest-v2",
        with_valuation_adapter=True, mutate=mutate)
    policy = load_formal_policy_registry(bundle, scoring_registry=scoring,
        feature_registry=vocabulary)
    return bundle, scoring, policy


class ValuationAdapterContractTests(unittest.TestCase):
    def test_exact_signed_coverage_and_derived_definition_hash(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        self.assertIs(type(registry), FormalValuationAdapterRegistry)
        registry.require_official(bundle)
        wire = registry.to_dict()
        self.assertEqual(wire["registry_manifest_hash"], bundle.manifest.manifest_hash)
        self.assertEqual(len(wire["coverage"]), 15)
        self.assertEqual(len(wire["adapters"]), 5)
        self.assertEqual(set(wire["role_hashes"]), set(bundle.roles))
        self.assertNotIn("original_definition_hash", wire["signed_child"]["adapters"][0])
        for template_id in scoring.templates:
            metrics = scoring.template_for(template_id).metrics["V"]
            self.assertEqual(len(metrics), 3)
            for metric in metrics:
                metric_id = "V." + metric.metric_id
                dependency = registry.dependency_for(template_id, metric_id)
                adapter = registry.adapter_for(template_id, metric_id)
                if dependency["policy_dependency"] == "affected":
                    self.assertIsNotNone(adapter)
                    self.assertEqual(adapter.original_definition_hash,
                        wire["metric_definitions"][template_id][metric_id]["definition_hash"])
                    self.assertEqual((adapter.policy_role, adapter.rule_id),
                        ("cyclic", f"{template_id}_cyclic_top"))
                    self.assertEqual((adapter.metric_unit, adapter.output_unit),
                        (metric.unit_rule, metric.unit_rule))
                    self.assertEqual((adapter.profit_unit, adapter.profit_semantic_id),
                        ("CNY", "cyclic_top"))
                    self.assertEqual(adapter.preconditions,
                        ("exact_units", "finite_decimals", "nonzero_original_current_profit"))
                else:
                    self.assertIsNone(adapter)
        self.assertIsNone(registry.adapter_for("bank", "V.unknown"))

    def test_each_signed_contract_mutation_is_rejected(self):
        changes = {
            "coverage_missing": lambda d: d["valuation_adapter"]["coverage"].pop(),
            "coverage_duplicate": lambda d: d["valuation_adapter"]["coverage"].append(
                copy.deepcopy(d["valuation_adapter"]["coverage"][0])),
            "coverage_dependency": lambda d: d["valuation_adapter"]["coverage"][0].update(
                policy_dependency="wrong"),
            "adapter_missing": lambda d: d["valuation_adapter"]["adapters"].pop(),
            "adapter_duplicate": lambda d: d["valuation_adapter"]["adapters"].append(
                copy.deepcopy(d["valuation_adapter"]["adapters"][0])),
            "adapter_unaffected": lambda d: d["valuation_adapter"]["adapters"].append(dict(
                d["valuation_adapter"]["adapters"][0],
                metric_id=next(c["metric_id"] for c in d["valuation_adapter"]["coverage"]
                    if c["template_id"] == d["valuation_adapter"]["adapters"][0]["template_id"]
                    and c["policy_dependency"] == "unaffected"))),
            "operation": lambda d: d["valuation_adapter"]["adapters"][0].update(operation="divide_v1"),
            "adapter_id": lambda d: d["valuation_adapter"]["adapters"][0].update(adapter_id="wrong"),
            "adapter_version": lambda d: d["valuation_adapter"]["adapters"][0].update(adapter_version="wrong"),
            "profit_semantic": lambda d: d["valuation_adapter"]["adapters"][0].update(profit_semantic_id="wrong"),
            "metric_unit": lambda d: d["valuation_adapter"]["adapters"][0].update(metric_unit="shares"),
            "profit_unit": lambda d: d["valuation_adapter"]["adapters"][0].update(profit_unit="ratio"),
            "output_unit": lambda d: d["valuation_adapter"]["adapters"][0].update(output_unit="shares"),
            "policy_role": lambda d: d["valuation_adapter"]["adapters"][0].update(policy_role="status"),
            "rule_id": lambda d: d["valuation_adapter"]["adapters"][0].update(rule_id="wrong"),
            "decimal_contract": lambda d: d["valuation_adapter"]["adapters"][0].update(decimal_contract="decimal28"),
            "preconditions": lambda d: d["valuation_adapter"]["adapters"][0].update(preconditions=["exact_units"]),
            "definition_basis": lambda d: d["valuation_adapter"]["adapters"][0].update(definition_basis="wrong"),
            "forged_definition_hash": lambda d: d["valuation_adapter"]["adapters"][0].update(
                original_definition_hash="0" * 64),
            "purpose": lambda d: d["valuation_adapter"].update(purpose="test"),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "valuation adapter"):
                bundle, scoring, policy = load_graph(mutate=mutate)
                load_formal_valuation_adapter_registry(bundle,
                    scoring_registry=scoring, policy_registry=policy)

    def test_registry_and_definition_copy_or_mutation_cannot_claim_official_status(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        with self.assertRaises((TypeError, ValueError)):
            FormalValuationAdapterRegistry()
        with self.assertRaises(ValueError):
            object.__new__(FormalValuationAdapterRegistry).require_official(bundle)
        adapter = next(registry.adapter_for(c["template_id"], c["metric_id"])
            for c in registry.to_dict()["coverage"] if c["policy_dependency"] == "affected")
        original = adapter.operation
        try:
            object.__setattr__(adapter, "operation", "wrong")
            with self.assertRaises(ValueError):
                registry.require_official(bundle)
        finally:
            object.__setattr__(adapter, "operation", original)
        registry.require_official(bundle)
        changed = registry.to_dict()
        changed["adapters"][0]["operation"] = "wrong"
        registry.require_official(bundle)

    def test_replaced_registry_method_invalidates_existing_proof(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        original = FormalValuationAdapterRegistry.require_official
        try:
            type.__setattr__(FormalValuationAdapterRegistry, "require_official",
                lambda self, root: None)
            with self.assertRaisesRegex(ValueError, "valuation adapter proof"):
                registry.adapter_for("bank", "V.unknown")
        finally:
            type.__setattr__(FormalValuationAdapterRegistry, "require_official", original)
        registry.require_official(bundle)

    def test_v1_graph_cannot_load_a_formal_valuation_adapter(self):
        bundle, vocabulary, scoring, _, _ = policy_graph(
            manifest_version="formal-registry-manifest-v1")
        policy = load_formal_policy_registry(bundle, scoring_registry=scoring,
            feature_registry=vocabulary)
        with self.assertRaisesRegex(ValueError, "valuation_adapter role is unavailable"):
            load_formal_valuation_adapter_registry(bundle, scoring_registry=scoring,
                policy_registry=policy)

    def test_fixture_requires_a_stage_c_root_for_adapter_document(self):
        with self.assertRaises(ValueError):
            policy_graph(with_valuation_adapter=True)
        with self.assertRaises(ValueError):
            policy_graph(version="v2", manifest_version="formal-registry-manifest-v2",
                with_valuation_adapter=True)


if __name__ == "__main__":
    unittest.main()
