"""One signed Stage D root feeding all three genuine scoring inputs."""

import unittest

from ashare_pipeline.formal_policy_repository import VerifiedPolicyResultBatch
from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
from ashare_pipeline.formal_score_inputs import FormalScoreInputBatch
from ashare_pipeline.formal_valuation_engine import PolicyAdjustedValuationBatch
from tests.formal_final_scoring_fixtures import FinalScoringFixture


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
