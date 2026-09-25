"""Signed valuation adapter definitions bind exactly to same-root policy and metrics."""

import copy
from dataclasses import asdict, replace
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ashare_pipeline.formal_valuation_adapter_contract as adapter_module
import ashare_pipeline.formal_metric_engine as metric_engine
from ashare_pipeline.formal_policy_registry import load_formal_policy_registry
from ashare_pipeline.formal_valuation_adapter_contract import (
    FormalValuationAdapterRegistry, load_formal_valuation_adapter_registry,
)
from tests.formal_policy_fixtures import policy_graph
from ashare_pipeline.formal_scoring_registry import FormalScoringRegistry


def load_graph(*, mutate=None):
    bundle, vocabulary, scoring, _, _ = policy_graph(
        manifest_version="formal-registry-manifest-v2",
        with_valuation_adapter=True, mutate=mutate)
    policy = load_formal_policy_registry(bundle, scoring_registry=scoring,
        feature_registry=vocabulary)
    return bundle, scoring, policy


class ValuationAdapterContractTests(unittest.TestCase):
    def test_each_source_read_authenticates_policy_once(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        calls = 0

        def profile(frame, event, _arg):
            nonlocal calls
            if (event == "call" and frame.f_code.co_name == "proof_record"
                    and frame.f_code.co_filename.endswith("formal_policy_registry.py")):
                calls += 1

        sys.setprofile(profile)
        try:
            registry.require_official(bundle)
            registry.require_official(bundle)
        finally:
            sys.setprofile(None)
        self.assertEqual(calls, 2)

    def test_replaced_policy_reader_revokes_warm_adapter(self):
        from ashare_pipeline import formal_policy_registry as policy_module

        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        original = policy_module._read_authenticated_policy_registry
        with patch.object(policy_module, "_read_authenticated_policy_registry",
                          lambda proof: original(proof)):
            with self.assertRaises(ValueError):
                registry.require_official(bundle)
        registry.require_official(bundle)

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
                registry.require_official(bundle)
            with self.assertRaisesRegex(ValueError, "valuation adapter proof"):
                registry.adapter_for("bank", "V.unknown")
        finally:
            type.__setattr__(FormalValuationAdapterRegistry, "require_official", original)
        registry.require_official(bundle)

    def test_replaced_definition_constructor_cannot_change_validated_operation(self):
        bundle, scoring, policy = load_graph()
        genuine = adapter_module.ValuationAdapterDefinition

        def corrupt(**values):
            return genuine(**(values | {"operation": "wrong"}))

        with patch.object(adapter_module, "ValuationAdapterDefinition", corrupt):
            registry = load_formal_valuation_adapter_registry(bundle,
                scoring_registry=scoring, policy_registry=policy)
        registry.require_official(bundle)
        self.assertEqual(registry.to_dict()["adapters"][0]["operation"],
            "profit_ratio_rescale_v1")

    def test_mutated_definition_initializer_cannot_launder_validated_operation(self):
        bundle, scoring, policy = load_graph()
        definition_type = adapter_module.ValuationAdapterDefinition
        genuine_init = definition_type.__init__

        def corrupt(self, **values):
            genuine_init(self, **values)
            object.__setattr__(self, "operation", "wrong")

        with patch.object(definition_type, "__init__", corrupt):
            with self.assertRaisesRegex(ValueError, "valuation adapter.*definition"):
                load_formal_valuation_adapter_registry(bundle,
                    scoring_registry=scoring, policy_registry=policy)

    def test_replaced_definition_serializer_cannot_change_bound_payload(self):
        bundle, scoring, policy = load_graph()

        def corrupt(value):
            result = asdict(value)
            result["operation"] = "wrong"
            return result

        with patch.object(adapter_module, "asdict", corrupt):
            registry = load_formal_valuation_adapter_registry(bundle,
                scoring_registry=scoring, policy_registry=policy)
        registry.require_official(bundle)
        self.assertEqual(registry.to_dict()["adapters"][0]["operation"],
            "profit_ratio_rescale_v1")

    def test_replaced_scoring_template_reader_cannot_define_adapter_hashes(self):
        bundle, scoring, policy = load_graph()
        genuine = FormalScoringRegistry.template_for

        def altered(self, template_id):
            template = genuine(self, template_id)
            if template_id != "bank":
                return template
            metrics = dict(template.metrics)
            first = metrics["V"][0]
            metrics["V"] = (replace(first,
                direction="higher" if first.direction == "lower" else "lower"),
                *metrics["V"][1:])
            return replace(template, metrics=metrics)

        with patch.object(FormalScoringRegistry, "template_for", altered):
            with self.assertRaisesRegex(ValueError, "valuation adapter.*template_for"):
                load_formal_valuation_adapter_registry(bundle,
                    scoring_registry=scoring, policy_registry=policy)

    def test_protected_attribute_lookup_cannot_be_replaced(self):
        original = FormalValuationAdapterRegistry.__getattribute__
        try:
            with self.assertRaises(TypeError):
                setattr(FormalValuationAdapterRegistry, "__getattribute__",
                    lambda self, name: object.__getattribute__(self, name))
        finally:
            type.__setattr__(FormalValuationAdapterRegistry, "__getattribute__", original)

    def test_swapped_metric_encoder_cannot_leave_an_official_adapter_after_restore(self):
        bundle, scoring, policy = load_graph()
        genuine = metric_engine._canonical

        def poisoned(value):
            if type(value) is dict and "definition" in value:
                return b"poisoned-metric-definition"
            return genuine(value)

        try:
            with patch.object(metric_engine, "_canonical", poisoned):
                registry = load_formal_valuation_adapter_registry(bundle,
                    scoring_registry=scoring, policy_registry=policy)
        except ValueError as error:
            self.assertRegex(str(error), "valuation adapter.*encoder")
        else:
            with self.assertRaisesRegex(ValueError, "valuation adapter.*(encoder|definition)"):
                registry.require_official(bundle)

    def test_existing_adapter_rejects_a_swapped_metric_encoder(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        with patch.object(metric_engine, "_canonical", lambda value: b"wrong"):
            with self.assertRaisesRegex(ValueError, "valuation adapter.*encoder"):
                registry.require_official(bundle)
        registry.require_official(bundle)

    def _metric_dependency_substitutions(self):
        plain = metric_engine._plain
        fields = metric_engine.fields

        def poisoned_plain(value):
            return "lower" if value == "higher" else plain(value)

        def omitted_direction(value):
            return tuple(field for field in fields(value) if field.name != "direction")

        return (
            ("_plain", poisoned_plain),
            ("fields", omitted_direction),
            ("json", SimpleNamespace(dumps=lambda *args, **kwargs: '"poisoned"')),
        )

    def test_all_definition_dependencies_reject_poisoned_public_loads_after_restore(self):
        bundle, scoring, policy = load_graph()
        for name, replacement in self._metric_dependency_substitutions():
            with self.subTest(dependency=name):
                try:
                    with patch.object(metric_engine, name, replacement):
                        registry = load_formal_valuation_adapter_registry(bundle,
                            scoring_registry=scoring, policy_registry=policy)
                except ValueError as error:
                    self.assertRegex(str(error), "valuation adapter.*definition dependencies")
                else:
                    with self.assertRaisesRegex(ValueError, "valuation adapter.*definition dependencies"):
                        registry.require_official(bundle)

    def test_existing_registry_rejects_every_active_definition_dependency_swap(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        for name, replacement in self._metric_dependency_substitutions():
            with self.subTest(dependency=name), patch.object(metric_engine, name, replacement):
                with self.assertRaisesRegex(ValueError, "valuation adapter.*definition dependencies"):
                    registry.require_official(bundle)
        registry.require_official(bundle)

    def _poisoned_json_encoder(self):
        original = json.JSONEncoder

        class PoisonedEncoder(original):
            def encode(self, value):
                if type(value) is dict and "definition" in value:
                    return '"poisoned-metric-definition"'
                return super().encode(value)

        return PoisonedEncoder

    def test_public_loader_rejects_a_replaced_json_encoder(self):
        bundle, scoring, policy = load_graph()
        with patch.object(json, "JSONEncoder", self._poisoned_json_encoder()):
            with self.assertRaisesRegex(ValueError, "valuation adapter.*definition dependencies"):
                load_formal_valuation_adapter_registry(bundle,
                    scoring_registry=scoring, policy_registry=policy)

    def test_existing_registry_reads_reject_an_active_json_encoder_swap(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        with patch.object(json, "JSONEncoder", self._poisoned_json_encoder()):
            with self.assertRaisesRegex(ValueError, "valuation adapter.*definition dependencies"):
                registry.to_dict()
        registry.require_official(bundle)

    def test_json_encoder_swap_cannot_publish_a_proof_official_after_restore(self):
        bundle, scoring, policy = load_graph()
        try:
            with patch.object(json, "JSONEncoder", self._poisoned_json_encoder()):
                registry = load_formal_valuation_adapter_registry(bundle,
                    scoring_registry=scoring, policy_registry=policy)
        except ValueError as error:
            self.assertRegex(str(error), "valuation adapter.*definition dependencies")
        else:
            with self.assertRaisesRegex(ValueError, "valuation adapter.*definition dependencies"):
                registry.require_official(bundle)

    def test_json_encoder_methods_and_both_encoding_branches_are_sealed(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        for owner, name in ((json.JSONEncoder, "__init__"),
                (json.JSONEncoder, "encode"), (json.JSONEncoder, "iterencode"),
                (json.encoder, "encode_basestring"), (json.encoder, "c_make_encoder"),
                (json.encoder, "_make_iterencode")):
            original = getattr(owner, name)
            replacement = lambda *args, _original=original, **kwargs: _original(*args, **kwargs)
            with self.subTest(owner=owner, name=name), patch.object(owner, name, replacement):
                with self.assertRaisesRegex(ValueError, "valuation adapter.*definition dependencies"):
                    registry.require_official(bundle)

    def test_json_encoder_rejects_new_attribute_lookup_method(self):
        bundle, scoring, policy = load_graph()
        registry = load_formal_valuation_adapter_registry(bundle,
            scoring_registry=scoring, policy_registry=policy)
        with patch.object(json.JSONEncoder, "__getattribute__",
                lambda self, name: object.__getattribute__(self, name)):
            with self.assertRaisesRegex(ValueError, "valuation adapter.*definition dependencies"):
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
