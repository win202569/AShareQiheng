"""Fast purpose-propagation contracts for the final-score D1 boundary."""

import inspect
import re
import unittest
from unittest.mock import patch

from ashare_pipeline import formal_final_score_inputs as final_module
from ashare_pipeline import formal_metric_context as metric_context_module
from ashare_pipeline.formal_context_repository import FormalContextRepository
from ashare_pipeline.formal_context_schema import (
    FormalContextRegistry,
    SignedContextRequestResolver,
)
from ashare_pipeline.formal_feature_repository import FormalFeatureRepository
from ashare_pipeline.formal_final_score_inputs import (
    FormalFinalScoreInputRepository,
)
from ashare_pipeline.formal_metric_context import FormalMetricContextRepository
from ashare_pipeline.formal_metric_engine import FormalMetricInputRepository
from ashare_pipeline.formal_policy_financial import FormalPolicyFinancialRepository
from ashare_pipeline.formal_policy_market import plan_next_window_request
from ashare_pipeline.formal_policy_repository import FormalPolicyRepository
from ashare_pipeline.formal_policy_registry import FormalPolicyRegistry
from ashare_pipeline.formal_policy_registry import (
    _read_authenticated_policy_registry,
    _read_authenticated_policy_sources,
    load_formal_policy_registry,
)
from ashare_pipeline.formal_range_contract import load_policy_range_bindings
from ashare_pipeline.formal_range_store import FormalRangeStore
from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
from ashare_pipeline.formal_score_inputs import FormalScoreInputRepository
from ashare_pipeline.formal_scoring_registry import FormalScoringRegistry
from ashare_pipeline.formal_valuation_adapter_contract import (
    FormalValuationAdapterRegistry,
    load_formal_valuation_adapter_registry,
)
from ashare_pipeline.formal_valuation_engine import FormalValuationRepository


class FormalFinalScorePurposeTests(unittest.TestCase):
    def _build_closure(self):
        return inspect.getclosurevars(
            FormalFinalScoreInputRepository.build_batch
        ).nonlocals

    def test_build_batch_exposes_exact_purpose_and_captures_valuation_build(self):
        build = FormalFinalScoreInputRepository.build_batch
        purpose = inspect.signature(build).parameters["expected_purpose"]
        self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(purpose.default, "official")
        self.assertIs(
            self._build_closure()["valuation_build"],
            FormalValuationRepository.build_batch,
        )

    def test_all_public_component_builders_default_to_official(self):
        for builder in (
            FormalMetricInputRepository.build_batch,
            FormalScoreInputRepository.build_batch,
            FormalPolicyRepository.build_batch,
            FormalValuationRepository.build_batch,
            FormalFinalScoreInputRepository.build_batch,
        ):
            with self.subTest(builder=builder.__qualname__):
                purpose = inspect.signature(builder).parameters.get(
                    "expected_purpose"
                )
                self.assertIsNotNone(purpose)
                self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertEqual(purpose.default, "official")

    def test_nested_component_boundaries_accept_one_explicit_purpose(self):
        boundaries = (
            FormalMetricInputRepository._build_batch_in_owner_scope,
            FormalPolicyRepository._build_batch_in_owner_scope,
            FormalMetricContextRepository.load_universe,
            FormalFeatureRepository.select_current_verified_metric_feature_state,
            FormalFeatureRepository.select_current_metric_batch_ticket,
            FormalFeatureRepository.select_current_policy_batch_ticket,
            FormalPolicyFinancialRepository.select,
            FormalPolicyFinancialRepository.select_current_batch_ticket,
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary.__qualname__):
                purpose = inspect.signature(boundary).parameters.get(
                    "expected_purpose"
                )
                self.assertIsNotNone(purpose)
                self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_authentication_helpers_do_not_infer_gate_from_manifest(self):
        score_build = inspect.getclosurevars(
            FormalScoreInputRepository.build_batch
        ).nonlocals["build"]
        metric_build = inspect.getclosurevars(
            FormalMetricInputRepository.build_batch
        ).nonlocals["build"]
        policy_auth = inspect.getclosurevars(
            FormalPolicyRepository._build_batch
        ).nonlocals["authenticate_scoring"]
        for helper in (
            score_build,
            metric_build,
            policy_auth,
            metric_context_module._industry,
            FormalFeatureRepository._registry,
        ):
            with self.subTest(helper=helper.__qualname__):
                self.assertIn(
                    "expected_purpose", inspect.signature(helper).parameters
                )
                self.assertNotIn("manifest.purpose", inspect.getsource(helper))

    def test_context_registry_and_repository_boundaries_propagate_exact_purpose(self):
        public_boundaries = (
            FormalContextRegistry.load,
            FormalContextRepository.get_verified,
            FormalContextRepository.get_verified_many,
            FormalContextRepository.select_current_batch_ticket,
            FormalContextRepository.resolve_verified_calendar_binding,
            SignedContextRequestResolver.resolve,
        )
        for boundary in public_boundaries:
            with self.subTest(boundary=boundary.__qualname__):
                purpose = inspect.signature(boundary).parameters.get(
                    "expected_purpose"
                )
                self.assertIsNotNone(purpose)
                self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertEqual(purpose.default, "official")

        for boundary in (
            FormalContextRepository._load,
            FormalContextRepository._candidates,
            FormalContextRepository._select,
            FormalContextRepository._select_many_with_token,
            SignedContextRequestResolver._resolve,
            SignedContextRequestResolver._resolve_historical,
        ):
            with self.subTest(boundary=boundary.__qualname__):
                purpose = inspect.signature(boundary).parameters.get(
                    "expected_purpose"
                )
                self.assertIsNotNone(purpose)
                self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)

        self.assertIn(
            "expected_purpose=expected_purpose",
            inspect.getsource(FormalContextRepository._load),
        )
        self.assertIn(
            "expected_purpose=expected_purpose",
            inspect.getsource(FormalContextRegistry.descriptor_for),
        )

    def test_registry_loaders_default_official_and_propagate_exact_purpose(self):
        public_loaders = (
            load_formal_policy_registry,
            load_policy_range_bindings,
            load_formal_valuation_adapter_registry,
            FormalRangeStore.__init__,
            FormalRangeStore.resolve_planning_binding,
            FormalPolicyStateRepository.select,
            FormalPolicyStateRepository.select_current_batch_ticket,
        )
        for loader in public_loaders:
            with self.subTest(loader=loader.__qualname__):
                purpose = inspect.signature(loader).parameters.get(
                    "expected_purpose"
                )
                self.assertIsNotNone(purpose)
                self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertEqual(purpose.default, "official")

        for boundary in (
            FormalPolicyStateRepository.select,
            FormalPolicyStateRepository.select_current_batch_ticket,
        ):
            source = inspect.getsource(boundary)
            self.assertIn("expected_purpose=expected_purpose", source)
            self.assertNotIn("manifest.purpose", source)

        policy_closure = inspect.getclosurevars(
            load_formal_policy_registry
        ).nonlocals
        range_closure = inspect.getclosurevars(
            load_policy_range_bindings
        ).nonlocals
        range_store_closure = inspect.getclosurevars(
            FormalRangeStore.resolve_planning_binding
        ).nonlocals
        internal_boundaries = (
            policy_closure["bind"],
            policy_closure["verify_sources"],
            _read_authenticated_policy_registry,
            _read_authenticated_policy_sources,
            range_closure["_capture_graph_snapshot"],
            range_closure["_derive_graph"],
            range_store_closure["load_binding_identity"],
        )
        for boundary in internal_boundaries:
            with self.subTest(boundary=boundary.__qualname__):
                purpose = inspect.signature(boundary).parameters.get(
                    "expected_purpose"
                )
                self.assertIsNotNone(purpose)
                self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)

        for loader in (
            load_formal_policy_registry,
            load_policy_range_bindings,
            load_formal_valuation_adapter_registry,
            range_store_closure["load_binding_identity"],
        ):
            with self.subTest(source=loader.__qualname__):
                source = inspect.getsource(loader)
                self.assertNotRegex(
                    source, r"\bpurpose\s*=\s*bundle\.manifest\.purpose"
                )
                self.assertIn("expected_purpose=expected_purpose", source)

    def test_market_planning_propagates_exact_purpose(self):
        purpose = inspect.signature(plan_next_window_request).parameters.get(
            "expected_purpose"
        )
        self.assertIsNotNone(purpose)
        self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(purpose.default, "official")

        planning_source = inspect.getsource(plan_next_window_request)
        self.assertIn("expected_purpose=expected_purpose", planning_source)
        self.assertNotRegex(
            planning_source, r"\bpurpose\s*=\s*.*manifest\.purpose"
        )
        store_source = inspect.getsource(
            FormalRangeStore.resolve_planning_binding
        )
        self.assertIn("expected_purpose=expected_purpose", store_source)
        self.assertIn("expected_purpose != sealed_purpose", inspect.getsource(
            inspect.getclosurevars(
                FormalRangeStore.resolve_planning_binding
            ).nonlocals["load_binding_identity"]
        ))
        for invalid in (None, True, type("TextSubclass", (str,), {})("test")):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "expected_purpose|purpose"
            ):
                plan_next_window_request(
                    "SH600000", "2026-08-31T07:00:00+00:00",
                    binding=None, range_store=None,
                    expected_purpose=invalid,
                )

    def test_policy_range_build_propagates_exact_purpose(self):
        build_source = inspect.getsource(FormalPolicyRepository._build_batch)
        call = re.search(
            r"bindings\s*=\s*load_bindings\((.*?)\)\s*$",
            build_source,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(call)
        self.assertIn("expected_purpose=expected_purpose", call.group(1))

    def test_genuine_metric_context_requires_explicit_matching_test_purpose(self):
        from tests.formal_metric_feature_fixtures import FinancialFixture

        test_fixture = FinancialFixture(purpose="test")
        self.addCleanup(test_fixture.close)
        with self.assertRaises(ValueError):
            FormalContextRegistry.load(
                test_fixture.store,
                test_fixture.verifier,
                test_fixture.bundle.manifest.manifest_hash,
            )
        context_registry = FormalContextRegistry.load(
            test_fixture.store,
            test_fixture.verifier,
            test_fixture.bundle.manifest.manifest_hash,
            expected_purpose="test",
        )
        context_registry.descriptor_for(
            test_fixture.resolver.resolve(
                context_kind="industry_snapshot",
                scope_key="fixture-industry",
                security_id="BJ430001",
                as_of_utc="2026-08-31T07:00:00+00:00",
                registry_manifest_hash=test_fixture.bundle.manifest.manifest_hash,
                upstream_generation="purpose-boundary",
                expected_purpose="test",
            )
        )
        test_context = FormalMetricContextRepository(
            test_fixture.store,
            test_fixture.context,
            registry_signature_verifier=test_fixture.verifier,
        )
        with self.assertRaises(ValueError):
            test_context.load_universe(
                test_fixture.frozen.frozen_input_hash,
                scoring_registry=test_fixture.scoring,
            )
        with self.assertRaises(ValueError):
            test_context.load_universe(
                test_fixture.frozen.frozen_input_hash,
                scoring_registry=test_fixture.scoring,
                expected_purpose="official",
            )
        proof = test_context.load_universe(
            test_fixture.frozen.frozen_input_hash,
            scoring_registry=test_fixture.scoring,
            expected_purpose="test",
        )
        proof.require_verified()

        official_fixture = FinancialFixture()
        self.addCleanup(official_fixture.close)
        official_context = FormalMetricContextRepository(
            official_fixture.store,
            official_fixture.context,
            registry_signature_verifier=official_fixture.verifier,
        )
        with self.assertRaises(ValueError):
            official_context.load_universe(
                official_fixture.frozen.frozen_input_hash,
                scoring_registry=official_fixture.scoring,
                expected_purpose="test",
            )

    def test_registry_snapshot_captures_purpose_aware_original_authorities(self):
        snapshot = self._build_closure()["registry_snapshot"]
        purpose = inspect.signature(snapshot).parameters["expected_purpose"]
        self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)
        captured = inspect.getclosurevars(snapshot).nonlocals
        self.assertIs(
            captured["scoring_verify"],
            FormalScoringRegistry.require_authenticated,
        )
        self.assertIs(
            captured["policy_verify"],
            FormalPolicyRegistry.require_verified,
        )
        self.assertIs(
            captured["adapter_verify"],
            FormalValuationAdapterRegistry.require_current_bundle,
        )

    def test_build_and_prepare_rechecks_seal_one_exact_purpose(self):
        build_source = inspect.getsource(FormalFinalScoreInputRepository.build_batch)
        self.assertEqual(build_source.count("registry_snapshot("), 2)
        self.assertGreaterEqual(
            build_source.count("expected_purpose=expected_purpose"),
            5,
            "base, policy, valuation, and both registry snapshots must receive one purpose",
        )
        for callee in ("base_build", "policy_build", "valuation_build"):
            self.assertRegex(
                build_source,
                re.compile(
                    rf"{callee}\(.*?expected_purpose=expected_purpose",
                    re.DOTALL,
                ),
            )

        valuation_source = inspect.getsource(FormalValuationRepository.build_batch)
        for callee in ("metric_build", "policy_build"):
            self.assertRegex(
                valuation_source,
                re.compile(
                    rf"{callee}\(.*?expected_purpose=expected_purpose",
                    re.DOTALL,
                ),
            )

        prepare = final_module._prepare_final_inputs
        prepare_source = inspect.getsource(prepare)
        self.assertIn("expected_purpose", prepare_source)
        self.assertIn("registry_snapshot", prepare_source)
        self.assertIs(
            inspect.getclosurevars(prepare).nonlocals["registry_snapshot"],
            self._build_closure()["registry_snapshot"],
        )

    def test_authenticated_authority_interface_replacement_fails_closed(self):
        dependencies = self._build_closure()["dependencies"]
        interfaces = inspect.getclosurevars(dependencies).nonlocals["interfaces"]
        for owner, name in (
            (FormalScoringRegistry, "require_authenticated"),
            (FormalPolicyRegistry, "require_verified"),
            (FormalValuationAdapterRegistry, "require_current_bundle"),
        ):
            with self.subTest(owner=owner.__name__, name=name):
                with patch.object(owner, name, lambda *_args, **_kwargs: None):
                    with self.assertRaisesRegex(
                        ValueError, "final score authority dependency changed"
                    ):
                        interfaces()


if __name__ == "__main__":
    unittest.main()
