"""Exact-purpose authentication contract for genuine signed test roots."""

import copy
import hashlib
import inspect
import json
import sys
import unittest
from dataclasses import replace

from ashare_pipeline import formal_feature_contract as feature_module
from ashare_pipeline import formal_registry_manifest as manifest_module
from ashare_pipeline.formal_feature_contract import load_signed_feature_registry
from ashare_pipeline.formal_policy_registry import (
    _read_authenticated_policy_sources,
    load_formal_policy_registry,
)
from ashare_pipeline.formal_range_contract import load_policy_range_bindings
from ashare_pipeline.formal_registry_manifest import (
    FormalRegistryBundleLoader,
    FormalRegistryManifest,
    VerifiedRegistryBlob,
)
from ashare_pipeline.formal_scoring_registry import (
    RegistryApproval,
    RegistryValidationError,
    load_formal_registry,
)
from ashare_pipeline.formal_valuation_adapter_contract import (
    load_formal_valuation_adapter_registry,
)
from tests.formal_policy_fixtures import (
    add_policy_documents,
    add_valuation_adapter_document,
    rehash_documents,
)
from tests.formal_metric_fixtures import industry_document, update_mapping_digest
from tests.formal_range_fixtures import add_range_documents
from tests.test_formal_registry_manifest import InMemoryRepository
from tests.test_formal_scoring_registry import canonical, fixture_wire, signed_graph


def signed_stage_d_graph(*, purpose="test", mutate=None):
    """Build one HMAC-signed v2 ten-role graph without touching disk."""

    def configure(documents):
        add_policy_documents(documents)
        add_range_documents(documents)
        add_valuation_adapter_document(documents)
        for role in ("industry", "cyclic", "redline", "status", "event", "valuation_adapter"):
            documents[role]["purpose"] = purpose
        if mutate is not None:
            mutate(documents)
        rehash_documents(documents)

    return signed_graph(
        context=True,
        manifest_version="formal-registry-manifest-v2",
        mutate=configure,
        purpose=purpose,
    )


def reload_bundle(repository, verifier, manifest):
    return FormalRegistryBundleLoader(repository, verifier).load(manifest.manifest_hash)


class SignedTestRootContractTests(unittest.TestCase):
    """Each test names a concrete downgrade or provenance mutation it catches."""

    def test_warm_test_bundle_authentication_never_reenters_canonical_json_parser(self):
        bundle, _, _, _ = signed_stage_d_graph(purpose="test")
        bundle.require_authenticated(expected_purpose="test")
        parser_code = manifest_module._load_canonical_object.__code__
        parser_calls = 0

        def count_parser_calls(frame, event, _argument):
            nonlocal parser_calls
            if event == "call" and frame.f_code is parser_code:
                parser_calls += 1

        sys.setprofile(count_parser_calls)
        try:
            for _ in range(5):
                bundle.require_authenticated(expected_purpose="test")
        finally:
            sys.setprofile(None)

        self.assertEqual(parser_calls, 0)

    def test_warm_test_bundle_authentication_rejects_mutated_child_bytes(self):
        bundle, _, _, _ = signed_stage_d_graph(purpose="test")
        bundle.require_authenticated(expected_purpose="test")
        industry = bundle.blob("industry")
        mutated = industry.canonical_json.replace(
            b'"purpose":"test"', b'"purpose":"official"', 1
        )
        self.assertNotEqual(mutated, industry.canonical_json)

        object.__setattr__(industry, "canonical_json", mutated)

        with self.assertRaises(ValueError):
            bundle.require_authenticated(expected_purpose="test")

    def test_signed_industry_authenticates_each_distinct_template_only_once(self):
        from ashare_pipeline import formal_metric_context as metric_context

        members = [
            dict(
                security_id=security_id,
                template_id=template_id,
                primary_industry="fixture-primary",
                secondary_industry="fixture-secondary",
            )
            for security_id, template_id in (
                ("BJ430001", "general_nonfinancial"),
                ("BJ430002", "general_nonfinancial"),
                ("SH600000", "bank"),
                ("SH600001", "bank"),
                ("SH600002", "bank"),
                ("SZ000001", "general_nonfinancial"),
                ("SZ000002", "general_nonfinancial"),
                ("SZ000003", "general_nonfinancial"),
            )
        ]

        def install_repeated_templates(documents):
            documents["industry"] = industry_document(purpose="test")
            documents["industry"]["memberships"] = members
            update_mapping_digest(documents["industry"])

        bundle, feature, _, _ = signed_stage_d_graph(
            purpose="test", mutate=install_repeated_templates
        )
        scoring = load_formal_registry(
            bundle,
            RegistryApproval("test", bundle.manifest.scoring_registry_hash, None),
            feature_registry=feature,
        )
        scoring_type = type(scoring)
        sealed_code = inspect.getclosurevars(
            scoring_type.require_authenticated
        ).nonlocals["sealed"].__code__
        watched = {
            scoring_type.require_authenticated.__code__: "source_authentication",
            scoring_type.template_for.__code__: "template_validation",
            sealed_code: "full_registry_seal",
        }
        counts = {name: 0 for name in watched.values()}

        def profile(frame, event, _argument):
            if event == "call" and frame.f_code in watched:
                counts[watched[frame.f_code]] += 1

        previous = sys.getprofile()
        sys.setprofile(profile)
        try:
            industry = metric_context._industry(
                bundle, scoring, expected_purpose="test"
            )
        finally:
            sys.setprofile(previous)

        self.assertEqual(industry["memberships"], members)
        self.assertEqual(counts, {
            "source_authentication": 1,
            "template_validation": 2,
            "full_registry_seal": 3,
        })

    def test_warm_feature_and_scoring_authentication_never_reserializes_slots(self):
        bundle, feature, _, _ = signed_stage_d_graph(purpose="test")
        scoring = load_formal_registry(
            bundle,
            RegistryApproval("test", bundle.manifest.scoring_registry_hash, None),
            feature_registry=feature,
        )
        feature.require_authenticated(bundle, expected_purpose="test")
        scoring.require_authenticated(bundle, expected_purpose="test")
        slot_serializer_code = feature_module._slot_to_dict.__code__
        slot_serializations = 0

        def count_slot_serializations(frame, event, _argument):
            nonlocal slot_serializations
            if event == "call" and frame.f_code is slot_serializer_code:
                slot_serializations += 1

        previous = sys.getprofile()
        sys.setprofile(count_slot_serializations)
        try:
            for _ in range(3):
                feature.require_authenticated(bundle, expected_purpose="test")
                scoring.require_authenticated(bundle, expected_purpose="test")
        finally:
            sys.setprofile(previous)

        self.assertEqual(slot_serializations, 0)

    def test_warm_feature_authentication_rejects_registry_and_slot_mutation(self):
        bundle, feature, _, _ = signed_stage_d_graph(purpose="test")
        feature.require_authenticated(bundle, expected_purpose="test")
        slot = object.__getattribute__(feature, "slots")[0]
        mutations = (
            (feature, "registry_hash", "0" * 64),
            (slot, "unit", "changed"),
        )

        for target, field, replacement in mutations:
            original = object.__getattribute__(target, field)
            try:
                object.__setattr__(target, field, replacement)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    feature.require_authenticated(bundle, expected_purpose="test")
            finally:
                object.__setattr__(target, field, original)
            feature.require_authenticated(bundle, expected_purpose="test")

    def test_warm_policy_source_read_authenticates_each_test_source_once(self):
        bundle, feature, _, _ = signed_stage_d_graph(purpose="test")
        scoring = load_formal_registry(
            bundle,
            RegistryApproval("test", bundle.manifest.scoring_registry_hash, None),
            feature_registry=feature,
        )
        policy = load_formal_policy_registry(
            bundle,
            scoring_registry=scoring,
            feature_registry=feature,
            expected_purpose="test",
        )
        _read_authenticated_policy_sources(
            policy, expected_purpose="test"
        )
        counts = {
            "bundle_authentication": 0,
            "scoring_seal": 0,
            "scoring_fingerprint": 0,
            "feature_seal": 0,
            "feature_fingerprint": 0,
        }

        def count_source_checks(frame, event, _argument):
            if event != "call":
                return
            name = frame.f_code.co_name
            path = frame.f_code.co_filename
            if (name == "require_authenticated_bundle"
                    and path.endswith("formal_registry_manifest.py")):
                counts["bundle_authentication"] += 1
            elif name == "sealed" and path.endswith("formal_scoring_registry.py"):
                counts["scoring_seal"] += 1
            elif (name == "fingerprint" and path.endswith("formal_scoring_registry.py")
                    and frame.f_back is not None
                    and frame.f_back.f_code.co_name == "sealed"):
                counts["scoring_fingerprint"] += 1
            elif name == "require_verified" and path.endswith("formal_feature_contract.py"):
                counts["feature_seal"] += 1
            elif name == "fingerprint" and path.endswith("formal_feature_contract.py"):
                counts["feature_fingerprint"] += 1

        previous = sys.getprofile()
        sys.setprofile(count_source_checks)
        try:
            source_bundle, source_scoring, source_feature, _ = (
                _read_authenticated_policy_sources(
                    policy, expected_purpose="test"
                )
            )
        finally:
            sys.setprofile(previous)

        self.assertIs(source_bundle, bundle)
        self.assertIs(source_scoring, scoring)
        self.assertIs(source_feature, feature)
        self.assertEqual(counts, {
            "bundle_authentication": 1,
            "scoring_seal": 1,
            "scoring_fingerprint": 0,
            "feature_seal": 1,
            "feature_fingerprint": 1,
        })

    def test_test_policy_feature_is_an_explicit_scoring_authenticated_feature(self):
        bundle, construction_feature, _, verifier = signed_stage_d_graph(purpose="test")
        feature_blob = bundle.blob("feature")
        independent_feature = load_signed_feature_registry(
            feature_blob.canonical_json,
            feature_blob.signature,
            feature_blob.key_id,
            verifier,
            registry_manifest=bundle.manifest,
        )
        self.assertIsNot(independent_feature, construction_feature)
        scoring = load_formal_registry(
            bundle,
            RegistryApproval("test", bundle.manifest.scoring_registry_hash, None),
            feature_registry=construction_feature,
        )
        construction_authenticated_feature = scoring.require_authenticated(
            bundle, expected_purpose="test"
        )
        self.assertIs(construction_authenticated_feature, construction_feature)
        explicit_authenticated_feature = scoring.require_authenticated(
            bundle,
            expected_purpose="test",
            feature_registry=independent_feature,
        )
        self.assertIs(explicit_authenticated_feature, independent_feature)

        policy = load_formal_policy_registry(
            bundle,
            scoring_registry=scoring,
            feature_registry=independent_feature,
            expected_purpose="test",
        )
        source_bundle, source_scoring, source_feature, _ = (
            _read_authenticated_policy_sources(
                policy, expected_purpose="test"
            )
        )

        self.assertIs(source_bundle, bundle)
        self.assertIs(source_scoring, scoring)
        self.assertIs(source_feature, independent_feature)

        with self.assertRaisesRegex(ValueError, "feature|verified"):
            scoring.require_authenticated(
                bundle,
                expected_purpose="test",
                feature_registry=copy.copy(independent_feature),
            )

        def change_feature_source(documents):
            documents["mapping"]["fixture_nonce"] = "different-feature-source"

        _, different_feature, _, _ = signed_stage_d_graph(
            purpose="test", mutate=change_feature_source
        )
        with self.assertRaisesRegex(ValueError, "feature|hash|source|mapping"):
            scoring.require_authenticated(
                bundle,
                expected_purpose="test",
                feature_registry=different_feature,
            )

    def test_genuine_test_and_official_roots_require_their_exact_purpose(self):
        test_bundle, _, _, _ = signed_stage_d_graph(purpose="test")
        official_bundle, _, _, _ = signed_stage_d_graph(purpose="official")

        test_bundle.require_authenticated(expected_purpose="test")
        official_bundle.require_authenticated(expected_purpose="official")
        official_bundle.require_official()
        with self.assertRaisesRegex(ValueError, "purpose"):
            test_bundle.require_authenticated(expected_purpose="official")
        with self.assertRaisesRegex(ValueError, "purpose"):
            official_bundle.require_authenticated(expected_purpose="test")
        with self.assertRaisesRegex(ValueError, "official|approval"):
            test_bundle.require_official()

    def test_expected_purpose_is_a_required_exact_enum_keyword(self):
        bundle, _, _, _ = signed_stage_d_graph(purpose="test")

        class TextSubclass(str):
            pass

        class EqualToTest:
            def __eq__(self, other):
                return other == "test"

        with self.assertRaises(TypeError):
            bundle.require_authenticated()
        for invalid in (None, True, TextSubclass("test"), EqualToTest()):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                (TypeError, ValueError), "expected_purpose|purpose"
            ):
                bundle.require_authenticated(expected_purpose=invalid)

    def test_test_root_loads_matching_feature_scoring_policy_range_and_adapter_contracts(self):
        bundle, feature, _, _ = signed_stage_d_graph(purpose="test")
        feature.require_authenticated(bundle, expected_purpose="test")
        scoring = load_formal_registry(
            bundle,
            RegistryApproval("test", bundle.manifest.scoring_registry_hash, None),
            feature_registry=feature,
        )
        scoring.require_authenticated(bundle, expected_purpose="test")
        policy = load_formal_policy_registry(
            bundle,
            scoring_registry=scoring,
            feature_registry=feature,
            expected_purpose="test",
        )
        ranges = load_policy_range_bindings(
            bundle,
            scoring_registry=scoring,
            policy_registry=policy,
            expected_purpose="test",
        )
        adapter = load_formal_valuation_adapter_registry(
            bundle,
            scoring_registry=scoring,
            policy_registry=policy,
            expected_purpose="test",
        )

        policy.require_verified()
        ranges.for_rule("bank_no_effective_trade_20d", "SH").require_current()
        adapter.require_authenticated(bundle, expected_purpose="test")
        self.assertEqual(policy.registry_manifest_hash, bundle.manifest.manifest_hash)
        self.assertEqual(adapter.to_dict()["registry_manifest_hash"], bundle.manifest.manifest_hash)

    def test_mixed_child_purpose_is_rejected_by_authenticated_gate(self):
        for role in ("scoring", "industry", "cyclic", "redline", "status", "event",
                     "valuation_adapter"):
            def mix_purpose(documents, *, role=role):
                target = documents["scoring"]["scoring"] if role == "scoring" else documents[role]
                target["purpose"] = "official"

            with self.subTest(role=role):
                bundle, _, _, _ = signed_stage_d_graph(
                    purpose="test", mutate=mix_purpose
                )
                with self.assertRaisesRegex(ValueError, f"{role}.*purpose|purpose.*{role}"):
                    bundle.require_authenticated(expected_purpose="test")

    def test_preload_parser_replacement_cannot_forge_child_purpose_evidence(self):
        def mix_industry_purpose(documents):
            documents["industry"]["purpose"] = "official"

        mixed_bundle, _, repository, verifier = signed_stage_d_graph(
            purpose="test", mutate=mix_industry_purpose
        )
        with self.assertRaisesRegex(ValueError, "industry.*purpose|purpose.*industry"):
            mixed_bundle.require_authenticated(expected_purpose="test")

        original_parser = manifest_module._load_canonical_object

        def lying_parser(value, *, label):
            parsed = original_parser(value, label=label)
            if label == "registry blob industry":
                parsed = dict(parsed)
                parsed["purpose"] = "test"
            return parsed

        manifest_module._load_canonical_object = lying_parser
        try:
            with self.assertRaisesRegex(
                ValueError, "parser|industry.*purpose|purpose.*industry"
            ):
                reloaded = FormalRegistryBundleLoader(repository, verifier).load(
                    mixed_bundle.manifest.manifest_hash
                )
                reloaded.require_authenticated(expected_purpose="test")
        finally:
            manifest_module._load_canonical_object = original_parser

    def test_missing_child_purpose_is_rejected_by_authenticated_gate(self):
        for role in ("scoring", "industry", "cyclic", "redline", "status", "event",
                     "valuation_adapter"):
            def remove_purpose(documents, *, role=role):
                target = documents["scoring"]["scoring"] if role == "scoring" else documents[role]
                target.pop("purpose")

            with self.subTest(role=role):
                bundle, _, _, _ = signed_stage_d_graph(
                    purpose="test", mutate=remove_purpose
                )
                with self.assertRaisesRegex(ValueError, f"{role}.*purpose|purpose.*{role}"):
                    bundle.require_authenticated(expected_purpose="test")

    def test_test_root_or_child_with_approval_identity_is_rejected(self):
        bundle, _, repository, verifier = signed_stage_d_graph(purpose="test")
        root_wire = json.loads(bundle.manifest.canonical_json)
        root_wire["approval_id"] = "forbidden-test-approval"
        root_bytes = canonical(root_wire)
        with self.assertRaisesRegex(ValueError, "approval_id.*null"):
            FormalRegistryManifest.from_signed_bytes(
                root_bytes,
                verifier.sign(root_bytes),
                "scoring-test-key",
                verifier,
            )

        scoring_blob = bundle.blob("scoring")
        repository.blobs[scoring_blob.registry_hash] = replace(
            repository.blobs[scoring_blob.registry_hash],
            approval_id="forbidden-test-approval",
        )
        with self.assertRaisesRegex(ValueError, "approval.*null"):
            reload_bundle(repository, verifier, bundle.manifest)

    def test_standalone_fixture_registry_cannot_authenticate_a_signed_test_root(self):
        bundle, _, _, _ = signed_stage_d_graph(purpose="test")
        fixture = load_formal_registry(
            canonical(fixture_wire()),
            RegistryApproval.for_test_fixture(),
        )
        with self.assertRaisesRegex(RegistryValidationError, "bundle|root|standalone|authenticated"):
            fixture.require_authenticated(bundle, expected_purpose="test")

    def test_signed_test_scoring_requires_exact_child_hash_and_null_approval(self):
        bundle, feature, _, _ = signed_stage_d_graph(purpose="test")
        exact = RegistryApproval(
            "test", bundle.manifest.scoring_registry_hash, None
        )
        scoring = load_formal_registry(bundle, exact, feature_registry=feature)
        scoring.require_authenticated(bundle, expected_purpose="test")
        for approval in (
            RegistryApproval.for_test_fixture(),
            RegistryApproval("test", "0" * 64, None),
            RegistryApproval("test", bundle.manifest.scoring_registry_hash, "forbidden"),
        ):
            with self.subTest(approval=approval), self.assertRaises(RegistryValidationError):
                load_formal_registry(bundle, approval, feature_registry=feature)

    def test_cross_root_copied_and_mutated_proofs_fail_closed(self):
        first, first_feature, _, _ = signed_stage_d_graph(purpose="test")

        def change_mapping(documents):
            documents["mapping"]["fixture_nonce"] = "different-root"

        second, _, _, _ = signed_stage_d_graph(purpose="test", mutate=change_mapping)
        scoring = load_formal_registry(
            first,
            RegistryApproval("test", first.manifest.scoring_registry_hash, None),
            feature_registry=first_feature,
        )
        with self.assertRaisesRegex(RegistryValidationError, "root|graph|bundle"):
            scoring.require_authenticated(second, expected_purpose="test")
        with self.assertRaisesRegex((TypeError, ValueError), "copied|verified|constructed|seal"):
            copy.copy(first).require_authenticated(expected_purpose="test")

        forged = object.__new__(type(first))
        object.__setattr__(forged, "manifest", first.manifest)
        object.__setattr__(forged, "blobs", first.blobs)
        with self.assertRaisesRegex(ValueError, "verified|forged|seal"):
            forged.require_authenticated(expected_purpose="test")

        object.__setattr__(first.manifest, "purpose", "official")
        with self.assertRaisesRegex(ValueError, "verified|mutated|seal"):
            first.require_authenticated(expected_purpose="official")

    def test_signed_test_root_cannot_be_promoted_by_official_approval(self):
        bundle, feature, _, _ = signed_stage_d_graph(purpose="test")
        approval = RegistryApproval(
            "official",
            hashlib.sha256(bundle.blob("scoring").canonical_json).hexdigest(),
            "test-graph-approval",
        )
        with self.assertRaises(RegistryValidationError):
            load_formal_registry(bundle, approval, feature_registry=feature)


if __name__ == "__main__":
    unittest.main()
