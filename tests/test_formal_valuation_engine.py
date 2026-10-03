"""Fast authority-boundary contracts for the formal valuation engine."""

import inspect
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_scoring_registry import FormalScoringRegistry
from ashare_pipeline.formal_valuation_adapter_contract import (
    FormalValuationAdapterRegistry,
)
from ashare_pipeline.formal_valuation_engine import FormalValuationRepository


class FormalValuationPurposeBoundaryTests(unittest.TestCase):
    def test_build_batch_captures_exact_purpose_scoring_authority(self):
        build = FormalValuationRepository.build_batch
        purpose = inspect.signature(build).parameters["expected_purpose"]
        self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(purpose.default, "official")

        captured = inspect.getclosurevars(build).nonlocals
        self.assertIs(
            captured["scoring_verify"],
            FormalScoringRegistry.require_authenticated,
        )
        recheck = FormalValuationRepository._batch_recheck_ticket
        self.assertIn(
            "expected_purpose",
            recheck.__code__.co_varnames,
            "the private root ticket must replay its sealed exact purpose",
        )

    def test_current_adapter_gate_accepts_and_captures_exact_purpose(self):
        current = FormalValuationAdapterRegistry.require_current_bundle
        purpose = inspect.signature(current).parameters["expected_purpose"]
        self.assertIs(purpose.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(purpose.default, "official")

        captured = inspect.getclosurevars(
            FormalValuationRepository.build_batch
        ).nonlocals
        self.assertIs(captured["adapter_verify"], current)

    def test_authenticated_authority_interface_replacement_fails_closed(self):
        build_closure = inspect.getclosurevars(
            FormalValuationRepository.build_batch
        ).nonlocals
        dependency_closure = inspect.getclosurevars(
            build_closure["dependencies"]
        ).nonlocals
        interfaces = dependency_closure["interfaces"]

        for owner, name in (
            (FormalScoringRegistry, "require_authenticated"),
            (FormalValuationAdapterRegistry, "require_current_bundle"),
        ):
            with self.subTest(owner=owner.__name__, name=name):
                with patch.object(owner, name, lambda *_args, **_kwargs: None):
                    with self.assertRaisesRegex(
                        ValueError, "valuation publication dependency changed"
                    ):
                        interfaces()


if __name__ == "__main__":
    unittest.main()
