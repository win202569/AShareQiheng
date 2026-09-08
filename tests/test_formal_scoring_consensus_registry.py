"""Signed neutral-consensus linkage contract tests."""

import hashlib
import importlib
import copy
from types import MappingProxyType
import unittest

from tests.test_formal_context_repository import descriptor
from tests.test_formal_context_schema import canonical
from tests.test_formal_scoring_registry import FIXTURE, TEMPLATES, fixture_wire, signed_graph


def consensus_descriptor(**changes):
    return descriptor("consensus_snapshot", scope_key="fixture-consensus", **changes)


def v2_graph(*, template_ids=("bank",), descriptor_changes=None, mutate=None):
    linked_descriptor = consensus_descriptor(**(descriptor_changes or {}))
    descriptor_id = hashlib.sha256(canonical(linked_descriptor)).hexdigest()
    post_mutate = mutate

    def make_v2(documents):
        wrapper = documents["scoring"]
        wrapper["schema_version"] = "formal-scoring-registry-v2"
        wrapper["descriptors"].append(linked_descriptor)
        links = []
        for template_id in sorted(template_ids):
            metric = wrapper["scoring"]["templates"][template_id]["metrics"]["T"][2]
            links.append(dict(rule_id="consensus-no-coverage-neutral-v1", template_id=template_id,
                metric_id="T.expectation_change", feature_key=metric["required_feature_keys"][0],
                descriptor_id=descriptor_id))
        wrapper["input_alternatives"] = links
        if post_mutate is not None:
            post_mutate(documents)

    bundle, vocabulary, repository, verifier = signed_graph(context=True, mutate=make_v2)
    return bundle, vocabulary, repository, verifier, linked_descriptor, descriptor_id


class FormalScoringConsensusRegistryTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("ashare_pipeline.formal_scoring_registry")

    def load_v2(self, **kwargs):
        bundle, vocabulary, repository, verifier, linked_descriptor, descriptor_id = v2_graph(**kwargs)
        approval = self.api.RegistryApproval("official", bundle.manifest.scoring_registry_hash,
            bundle.manifest.approval_id)
        registry = self.api.load_formal_registry(bundle, approval, feature_registry=vocabulary)
        return registry, bundle, vocabulary, repository, verifier, linked_descriptor, descriptor_id

    def load_official(self, bundle, vocabulary, approval=None):
        approval = approval or self.api.RegistryApproval("official", bundle.manifest.scoring_registry_hash,
            bundle.manifest.approval_id)
        return self.api.load_formal_registry(bundle, approval, feature_registry=vocabulary)

    def test_valid_v2_signed_registry_loads_canonical_descriptor_link(self):
        registry, bundle, _, _, _, linked_descriptor, descriptor_id = self.load_v2()
        registry.require_official(bundle)
        self.assertEqual(tuple(registry.consensus_no_coverage_links), ("bank",))
        self.assertEqual(registry.consensus_no_coverage_links["bank"], {
            "rule_id": "consensus-no-coverage-neutral-v1",
            "template_id": "bank",
            "metric_id": "T.expectation_change",
            "feature_key": "bank.T.expectation_change",
            "descriptor_id": descriptor_id,
            "context_kind": "consensus_snapshot",
            "scope_key": "fixture-consensus",
        })
        self.assertEqual(descriptor_id, hashlib.sha256(canonical(linked_descriptor)).hexdigest())

    def test_v1_fixture_and_signed_official_graph_keep_empty_immutable_links(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "e61b4e20dbfd03396614d392b13b781b59c436ce52676d88308c500cc33174c4")
        fixture_registry = self.api.load_formal_registry(FIXTURE, self.api.RegistryApproval.for_test_fixture())
        bundle, vocabulary, _, _ = signed_graph()
        official_registry = self.load_official(bundle, vocabulary)
        for registry in (fixture_registry, official_registry):
            self.assertEqual(registry.consensus_no_coverage_links, {})
            with self.assertRaises(TypeError):
                registry.consensus_no_coverage_links["bank"] = {}
        official_registry.require_official(bundle)

    def test_v2_allows_empty_subset_and_all_five_sorted_template_links(self):
        for template_ids in ((), ("bank", "insurance"), TEMPLATES):
            with self.subTest(template_ids=template_ids):
                registry, bundle, _, _, _, _, _ = self.load_v2(template_ids=template_ids)
                self.assertEqual(tuple(registry.consensus_no_coverage_links), tuple(sorted(template_ids)))
                registry.require_official(bundle)

    def test_v2_links_and_nested_values_are_immutable_and_seal_checked(self):
        registry, bundle, _, _, _, _, _ = self.load_v2()
        with self.assertRaises(TypeError):
            registry.consensus_no_coverage_links["bank"] = {}
        with self.assertRaises(TypeError):
            registry.consensus_no_coverage_links["bank"]["scope_key"] = "other"
        with self.assertRaises(self.api.RegistryValidationError):
            copy.copy(registry).require_official(bundle)
        object.__setattr__(registry, "consensus_no_coverage_links", MappingProxyType({}))
        with self.assertRaises(self.api.RegistryValidationError):
            registry.require_official(bundle)

    def test_v2_rejects_wrong_rule_template_metric_key_hash_and_exact_fields(self):
        def change_link(**changes):
            return lambda docs: docs["scoring"]["input_alternatives"][0].update(changes)

        cases = (
            change_link(rule_id="other"),
            change_link(template_id="unknown"),
            change_link(metric_id="T.historical_valuation"),
            change_link(feature_key="bank.T.historical_valuation"),
            change_link(feature_key="unknown"),
            change_link(feature_key="broker.T.expectation_change"),
            change_link(descriptor_id="0" * 64),
            change_link(descriptor_id="A" * 64),
            change_link(extra="forbidden"),
            change_link(rule_id=""),
            lambda docs: docs["scoring"]["input_alternatives"][0].pop("metric_id"),
            lambda docs: docs["scoring"].update(input_alternatives=[None]),
            lambda docs: docs["scoring"]["descriptors"].pop(),
        )
        for mutation in cases:
            with self.subTest(mutation=mutation), self.assertRaises(self.api.RegistryValidationError):
                bundle, vocabulary, _, _, _, _ = v2_graph(mutate=mutation)
                self.load_official(bundle, vocabulary)

    def test_v2_rejects_shared_expectation_key_and_invalid_descriptor_semantics(self):
        def share_key(documents):
            metrics = documents["scoring"]["scoring"]["templates"]["bank"]["metrics"]["T"]
            source, target = metrics[2], metrics[0]
            for field in ("required_feature_keys", "formula", "field_map", "formula_version", "unit_rule",
                    "period_rule", "denominator_rule"):
                target[field] = copy.deepcopy(source[field])

        with self.assertRaisesRegex(self.api.RegistryValidationError, "shared"):
            bundle, vocabulary, _, _, _, _ = v2_graph(mutate=share_key)
            self.load_official(bundle, vocabulary)

        descriptor_cases = (
            {"context_kind": "security_state"},
            {"security_scope": "none", "request_security": "none", "exchange_rule": "none"},
            {"period_rule": "none"},
        )
        for changes in descriptor_cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(self.api.RegistryValidationError, "semantics"):
                bundle, vocabulary, _, _, _, _ = v2_graph(descriptor_changes=changes)
                self.load_official(bundle, vocabulary)

    def test_v2_rejects_duplicate_unsorted_or_ambiguous_descriptor_selections(self):
        def duplicate_link(documents):
            documents["scoring"]["input_alternatives"].append(
                copy.deepcopy(documents["scoring"]["input_alternatives"][0]))

        def unsorted_links(documents):
            documents["scoring"]["input_alternatives"].reverse()

        def duplicate_descriptor(documents):
            documents["scoring"]["descriptors"].append(copy.deepcopy(documents["scoring"]["descriptors"][-1]))

        for template_ids, mutation in ((("bank",), duplicate_link), (TEMPLATES, unsorted_links),
                (("bank",), duplicate_descriptor)):
            with self.subTest(mutation=mutation), self.assertRaises(self.api.RegistryValidationError):
                bundle, vocabulary, _, _, _, _ = v2_graph(template_ids=template_ids, mutate=mutation)
                self.load_official(bundle, vocabulary)

    def test_v2_reuses_full_context_descriptor_validation(self):
        for mutation in (
                lambda docs: docs["scoring"]["descriptors"][-1].update(extra=True),
                lambda docs: docs["scoring"]["descriptors"][-1].update(source=" "),
                lambda docs: docs["scoring"]["descriptors"][-1].update(referenced_roles=["source"])):
            with self.subTest(mutation=mutation), self.assertRaises(self.api.RegistryValidationError):
                bundle, vocabulary, _, _, _, _ = v2_graph(mutate=mutation)
                self.load_official(bundle, vocabulary)

    def test_v2_rejects_unknown_missing_extra_wrapper_keys_and_non_list_alternatives(self):
        cases = (
            lambda docs: docs["scoring"].update(schema_version="formal-scoring-registry-v999"),
            lambda docs: docs["scoring"].update(extra=True),
            lambda docs: docs["scoring"].pop("input_alternatives"),
            lambda docs: docs["scoring"].update(input_alternatives={}),
            lambda docs: docs["scoring"].update(scoring=[]),
        )
        for mutation in cases:
            with self.subTest(mutation=mutation), self.assertRaises(self.api.RegistryValidationError):
                bundle, vocabulary, _, _, _, _ = v2_graph(mutate=mutation)
                self.load_official(bundle, vocabulary)

    def test_v2_keeps_approval_root_byte_integrity_and_test_purpose_separate(self):
        registry, bundle, vocabulary, _, _, linked_descriptor, descriptor_id = self.load_v2()
        wrong = self.api.RegistryApproval("official", "0" * 64, bundle.manifest.approval_id)
        with self.assertRaises(self.api.RegistryValidationError):
            self.load_official(bundle, vocabulary, wrong)
        other, _, _, _, _, _ = v2_graph(template_ids=("broker",))
        with self.assertRaises(self.api.RegistryValidationError):
            registry.require_official(other)
        object.__setattr__(bundle.blob("scoring"), "canonical_json", b"{}")
        with self.assertRaises(self.api.RegistryValidationError):
            registry.require_official(bundle)

        wire = fixture_wire()
        wire.update(schema_version="formal-scoring-registry-v2", descriptors=[linked_descriptor],
            input_alternatives=[dict(rule_id="consensus-no-coverage-neutral-v1", template_id="bank",
                metric_id="T.expectation_change", feature_key="bank.T.expectation_change",
                descriptor_id=descriptor_id)])
        test_registry = self.api.load_formal_registry(canonical(wire), self.api.RegistryApproval.for_test_fixture())
        with self.assertRaisesRegex(self.api.RegistryValidationError, "test registry"):
            test_registry.require_official(other)


if __name__ == "__main__":
    unittest.main()
