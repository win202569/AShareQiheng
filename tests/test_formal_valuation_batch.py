"""Complete policy-adjusted V batches from genuine signed evidence."""

import unittest
from decimal import Decimal

from tests.formal_valuation_fixtures import ValuationRuntimeFixture


class ValuationBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = ValuationRuntimeFixture()
        print("C4 20-member universe ready", flush=True)
        def progress(phase, security_id):
            if phase in ("policy", "metric"):
                print(f"C4 {phase} {security_id}", flush=True)
            else:
                print(f"C4 {phase}", flush=True)
        cls.fixture._valuation_progress = progress
        cls.fixture.populate_valuation_inputs()
        cls.batch = cls.fixture.build_adjusted_batch()
        print("C4 adjusted batch finalized", flush=True)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def test_complete_batch_contains_every_security_and_three_v_metrics(self):
        batch = self.batch
        batch.require_verified()
        self.assertEqual(batch.security_ids, tuple(sorted(self.fixture.templates)))
        self.assertEqual(len(batch.inputs), 3 * len(batch.security_ids))
        focal = batch.input_for("BJ430001", "V.normalized_earnings_yield")
        self.assertEqual(focal.status, "adjusted")
        self.assertEqual(focal.adjusted_value, Decimal("0.12"))
        focal_market = [item for item in focal.policy_result["decisions"]
                        if item["semantic_id"] == "no_effective_trade_20d"]
        self.assertEqual(len(focal_market), 1)
        self.assertEqual(focal_market[0]["evaluation_state"], "clear")
        peer = batch.input_for("SH600000", "V.normalized_earnings_yield")
        decisions = [item for item in peer.policy_result["decisions"] if item["role"] == "cyclic"]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["evaluation_state"], "not_applicable")
        self.assertEqual(peer.status, "passthrough_not_applicable")
        peer_market = [item for item in peer.policy_result["decisions"]
                       if item["semantic_id"] == "no_effective_trade_20d"]
        self.assertEqual(len(peer_market), 1)
        self.assertEqual(peer_market[0]["evaluation_state"], "clear")

    def test_batch_rows_are_canonical_and_bind_three_source_authorities(self):
        batch = self.batch
        wire = batch.to_dict()
        expected = [(sid, mid) for sid in sorted(self.fixture.templates)
                    for mid in ("V.enterprise_value_or_sustainable_roe",
                                "V.normalized_earnings_yield",
                                "V.normalized_free_cash_flow_yield")]
        self.assertEqual([(row["security_id"], row["metric_id"])
                          for row in wire["inputs"]], expected)
        self.assertEqual(wire["registry_manifest_hash"], self.fixture.bundle.manifest.manifest_hash)
        self.assertEqual(wire["valuation_adapter_registry_hash"],
                         self.fixture.bundle.manifest.valuation_adapter_registry_hash)
        self.assertEqual(wire["scoring_registry_hash"], self.fixture.bundle.manifest.scoring_registry_hash)
        self.assertEqual(wire["policy_contract_hash"], self.fixture.policy_registry.contract_hash)
        self.assertEqual(len(wire["base_batch_canonical_sha256"]), 64)
        self.assertEqual(len(wire["policy_batch_canonical_sha256"]), 64)
