"""One signed Stage D root feeding all three genuine scoring inputs."""

from datetime import date, timedelta
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_policy_repository import VerifiedPolicyResultBatch
from ashare_pipeline.formal_policy_market import evaluate_window
from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
from ashare_pipeline.formal_score_inputs import FormalScoreInputBatch
from ashare_pipeline.formal_valuation_engine import PolicyAdjustedValuationBatch
from tests.formal_final_scoring_fixtures import FinalScoringFixture
from tests.formal_valuation_fixtures import ValuationRuntimeFixture


class FinalScoringFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = FinalScoringFixture(peer_count=3)
        try:
            cls.fixture.populate_final_inputs()
            cls.sources = cls.fixture.build_d1_sources()
        except BaseException:
            cls.fixture.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def test_one_v2_root_builds_base_policy_and_adjusted_valuation_batches(self):
        fixture, sources = self.fixture, self.sources
        expected_ids = tuple(member.security_id for member in fixture.frozen.members)
        expected_identity = (fixture.bundle.manifest.manifest_hash,
            fixture.frozen.frozen_input_hash, fixture.frozen.universe_hash, expected_ids)
        for batch in (sources.base, sources.policy, sources.valuation):
            batch.require_verified()
            self.assertEqual((batch.registry_manifest_hash, batch.frozen_input_hash,
                batch.universe_hash, batch.security_ids), expected_identity)
        self.assertEqual(len(expected_ids), 3)
        score_slots = [slot for slot in fixture.vocabulary.slots_for_template(
            "general_nonfinancial") if ".policy." not in slot.slot_id]
        self.assertEqual(len(score_slots), 25)

    def test_fixture_never_exposes_proof_mint_or_plain_proof_double(self):
        fixture, sources = self.fixture, self.sources
        self.assertFalse(any("mint" in name.lower() for name in dir(fixture)))
        for proof, proof_type in ((sources.base, FormalScoreInputBatch),
                (sources.policy, VerifiedPolicyResultBatch),
                (sources.valuation, PolicyAdjustedValuationBatch)):
            self.assertIs(type(proof), proof_type)
            proof.require_verified()

    def test_focal_full_feature_bundle_has_trustworthy_required_slots(self):
        bundle = self.fixture.valuation_feature_bundles["BJ430001"]
        self.assertEqual(bundle.blockers, ())
        required = {slot.slot_id for slot in self.fixture.vocabulary.slots_for_template(
            "general_nonfinancial") if slot.required}
        actual = {value.slot_id: value.status for value in bundle.values
            if value.slot_id in required}
        self.assertEqual(len(required), 25)
        self.assertEqual(actual, {slot_id: "derived" for slot_id in required})


class FinalScoringVetoMarketProtocolTests(unittest.TestCase):
    def test_veto_reply_keeps_a_prior_positive_close_outside_twenty_quiet_days(self):
        fixture = object.__new__(FinalScoringFixture)
        fixture.veto_ids = ("SH600000",)
        fixture.transport = SimpleNamespace()
        end = date(2026, 8, 31)
        days = {(end - timedelta(days=30 - index)).isoformat(): index >= 11
                for index in range(31)}
        produced = []

        def capture_calendar(_fixture, *, days, generation="g1", omit_pages=()):
            produced.append(days)

        with patch.object(ValuationRuntimeFixture, "produce_calendar", capture_calendar):
            FinalScoringFixture.produce_calendar(fixture, days=days)
        self.assertEqual(len(produced), 1)
        trading_days = tuple(day for day, opened in sorted(produced[0].items()) if opened)
        self.assertGreaterEqual(len(trading_days), 21)
        wire = {"security_id": "SH600000", "rows": [
            {"date": day, "exchange_allows_trading": True,
             "volume": "1", "turnover": "2",
             "close": {"state": "positive", "value": "2"}}
            for day in trading_days]}
        fixture.reply(wire, original_url="https://www.cninfo.com.cn/fixture/range-market.json")
        replied = json.loads(fixture.transport.response.raw_bytes)
        rows = {row["date"]: {key: row[key] for key in
            ("exchange_allows_trading", "volume", "turnover", "close")}
            | {"coverage": "covered"} for row in replied["rows"]}
        self.assertEqual((rows[trading_days[-21]]["volume"],
                          rows[trading_days[-21]]["turnover"]), ("1", "2"))
        self.assertEqual(rows[trading_days[-21]]["close"],
                         {"state": "positive", "value": "2"})
        self.assertTrue(all(rows[day]["volume"] == "0" and
                            rows[day]["turnover"] == "0" for day in trading_days[-20:]))
        result = evaluate_window(trading_days, rows)
        self.assertEqual(result["veto_state"], "proven")
        self.assertEqual(result["price_state"], "positive_close_complete")
        self.assertEqual(result["pending"], [])


class SignedTestRootFinalScoringFixtureTests(unittest.TestCase):
    def test_genuine_signed_test_root_builds_stage_a_b_c_and_d1_without_official_authority(self):
        fixture = FinalScoringFixture(peer_count=3, purpose="test")
        self.addCleanup(fixture.close)
        fixture.populate_final_inputs()
        sources = fixture.build_d1_sources()
        d1 = FormalFinalScoreInputRepository(
            fixture.feature_repository,
            fixture.context,
            fixture.range_store,
            registry_signature_verifier=fixture.verifier,
        ).build_batch(
            fixture.frozen.frozen_input_hash,
            scoring_registry=fixture.scoring,
            policy_registry=fixture.policy_registry,
            valuation_adapter_registry=fixture.valuation_registry,
            expected_purpose=fixture.purpose,
        )

        root_hash = fixture.bundle.manifest.manifest_hash
        expected_ids = tuple(member.security_id for member in fixture.frozen.members)
        self.assertEqual(fixture.bundle.manifest.purpose, "test")
        self.assertEqual(fixture.bundle.manifest.schema_version,
                         "formal-registry-manifest-v2")
        self.assertEqual(len(fixture.bundle.roles), 10)
        fixture.bundle.require_authenticated(expected_purpose="test")
        for batch in (*sources, d1):
            batch.require_verified()
            self.assertEqual(batch.registry_manifest_hash, root_hash)
            self.assertEqual(batch.frozen_input_hash, fixture.frozen.frozen_input_hash)
            self.assertEqual(batch.universe_hash, fixture.frozen.universe_hash)
            self.assertEqual(batch.security_ids, expected_ids)

        sources.policy.require_authenticated(expected_purpose="test")
        with self.assertRaises(ValueError):
            sources.policy.require_official()

        with self.assertRaises(ValueError):
            fixture.bundle.require_official()
        with self.assertRaises(ValueError):
            fixture.scoring.require_official(fixture.bundle)
        with self.assertRaises(ValueError):
            fixture.valuation_registry.require_official(fixture.bundle)


if __name__ == "__main__":
    unittest.main()
