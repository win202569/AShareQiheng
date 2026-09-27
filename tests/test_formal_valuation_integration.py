"""End-to-end Stage C proof-chain acceptance."""

import unittest

from ashare_pipeline.formal_valuation_engine import (
    build_valuation_peer_context,
    score_valuation_percentile,
)
from ashare_pipeline.formal_policy_values import digest
from tests import test_formal_valuation_ranking as ranking


def _all_keys(value):
    if type(value) is dict:
        result = set(value)
        for child in value.values():
            result.update(_all_keys(child))
        return result
    if type(value) is list:
        result = set()
        for child in value:
            result.update(_all_keys(child))
        return result
    return set()


class ValuationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ranking.FullValuationRankingTests.setUpClass()
        cls.fixture = ranking.FullValuationRankingTests.fixture
        cls.batch = ranking.FullValuationRankingTests.batch

    def test_signed_policy_to_adjusted_value_to_peer_score_is_replayable(self):
        context = build_valuation_peer_context(self.batch,
            security_id="BJ430001", metric_id="V.normalized_earnings_yield")
        first = score_valuation_percentile(self.batch, context)
        owner = ranking.FullValuationRankingTests
        if not hasattr(owner, "second_batch"):
            owner.second_batch = self.fixture.build_adjusted_batch()
        second_context = build_valuation_peer_context(owner.second_batch,
            security_id="BJ430001", metric_id="V.normalized_earnings_yield")
        second = score_valuation_percentile(owner.second_batch, second_context)
        self.assertIsNot(self.batch, owner.second_batch)
        self.assertEqual(self.batch.canonical_bytes(), owner.second_batch.canonical_bytes())
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertIs(first.peer_context, context)

        row = self.batch.input_for("BJ430001", "V.normalized_earnings_yield")
        decision = [item for item in row.policy_result["decisions"]
                    if item["role"] == "cyclic"][0]
        self.assertEqual(first.adjusted_input_hash, row.input_hash)
        self.assertEqual(first.peer_context.batch_hash, self.batch.batch_hash)
        self.assertEqual(row.adjustment["metric_input_hash"], row.original_metric["input_hash"])
        self.assertEqual(row.adjustment["decision_hash"], decision["decision_hash"])
        self.assertEqual(len(row.policy_result["normalization_basis"]), 1)
        basis = decision["operands"]["normalization_basis"]
        aggregated_basis = row.policy_result["normalization_basis"][0]
        for key, value in basis.items():
            self.assertEqual(aggregated_basis[key], value)
        adapter = [item for item in self.fixture.valuation_registry.to_dict()["adapters"]
                   if item["template_id"] == row.template_id
                   and item["metric_id"] == row.metric_id][0]
        self.assertEqual(row.adjustment["adapter_definition_hash"],
                         digest(adapter))
        self.assertEqual(self.batch.registry_manifest_hash,
                         row.original_metric["registry_manifest_hash"])
        self.assertEqual(self.batch.valuation_adapter_registry_hash,
                         first.valuation_adapter_registry_hash)

        forbidden = {"G_cap", "M_cap", "Sc", "B", "R", "R_safety",
                     "eligibility", "pool", "strong_pool", "waiting_pool"}
        self.assertFalse(forbidden & _all_keys(first.to_dict()))

    def test_diagnostics_are_noncanonical_and_bound_to_the_batch(self):
        before = self.batch.canonical_bytes()
        report = self.fixture.repository.diagnostic_report(self.batch)
        self.assertEqual(report["batch_hash"], self.batch.batch_hash)
        self.assertEqual(report["security_count"], 23)
        self.assertEqual(report["valuation_row_count"], 69)
        self.assertEqual(self.batch.canonical_bytes(), before)


if __name__ == "__main__":
    unittest.main()
