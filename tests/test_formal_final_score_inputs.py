"""D1 composition over genuine, signed repository outputs."""

from decimal import Decimal
import hashlib
import inspect
import unittest

from ashare_pipeline.formal_final_score_inputs import (
    FormalFinalScoreInputRepository, PolicyAdjustedScoreInput,
)
from ashare_pipeline.formal_valuation_engine import (
    build_valuation_peer_context, score_valuation_percentile,
)
from tests.formal_final_scoring_fixtures import FinalScoringFixture, FOCAL


V_METRICS = (
    "V.enterprise_value_or_sustainable_roe", "V.normalized_earnings_yield",
    "V.normalized_free_cash_flow_yield",
)


def build(fixture):
    repository = FormalFinalScoreInputRepository(fixture.feature_repository,
        fixture.context, fixture.range_store, registry_signature_verifier=fixture.verifier)
    return repository.build_batch(fixture.frozen.frozen_input_hash,
        scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry,
        valuation_adapter_registry=fixture.valuation_registry)


class FinalScoreInputContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = FinalScoringFixture()
        cls.addClassCleanup(cls.fixture.close)
        cls.fixture.populate_final_inputs()
        cls.sources = cls.fixture.build_d1_sources()
        cls.batch = build(cls.fixture)

    def test_batch_enumerates_every_frozen_member_in_canonical_order(self):
        expected = ("BJ430001", "SH600000", "SZ000001")
        self.assertEqual(self.batch.security_ids, expected)
        self.assertEqual(tuple(row.security_id for row in self.batch.inputs), expected)
        for sid in expected:
            self.assertIsInstance(self.batch.input_for(sid), PolicyAdjustedScoreInput)
            self.assertEqual(self.batch.input_for(sid).security_id, sid)
        with self.assertRaises(ValueError):
            self.batch.input_for("SH999999")

    def test_member_business_gaps_become_explicit_pending_entries_not_none(self):
        policy = {row.security_id: row for row in self.sources.policy.results}
        for sid in self.batch.security_ids:
            row = self.batch.input_for(sid)
            self.assertIsInstance(row, PolicyAdjustedScoreInput)
            row.require_verified()
            self.assertEqual(row.status, "pending_evidence")
            self.assertEqual(len(row.entry_hash), 64)
            self.assertTrue(row.reasons)
            self.assertEqual(row.base_pending_reasons, self.sources.base.pending_reasons[sid])
            self.assertEqual(row.policy_result_hash, policy[sid].result_hash)
            self.assertEqual(row.to_dict()["policy_pending_requirements"],
                policy[sid].to_dict()["pending_requirements"])
        self.assertTrue(self.batch.input_for("SH600000").policy_pending_requirements)
        self.assertTrue(self.batch.input_for(FOCAL).valuation_pending_reasons)

    def test_pending_without_base_retains_authenticated_member_identity(self):
        industry = self.sources.policy.evidence_batch.industry["entries"]
        for sid in self.batch.security_ids:
            self.assertIsNone(self.sources.base.input_for(sid))
            row = self.batch.input_for(sid)
            self.assertEqual(row.status, "pending_evidence")
            for field in ("template_id", "primary_industry", "secondary_industry"):
                self.assertIn(field, tuple(row.to_dict()))
                self.assertEqual(getattr(row, field), industry[sid][field])

    def test_member_identity_rejects_inconsistent_genuine_valuation_inputs(self):
        # Inspect only the composition closure; never mint or alter a source proof.
        validate = inspect.getclosurevars(
            FormalFinalScoreInputRepository.build_batch).nonlocals["member_identity"]
        industry = self.sources.policy.evidence_batch.industry["entries"][FOCAL]
        genuine = tuple(self.sources.valuation.input_for(FOCAL, mid) for mid in V_METRICS)
        expected = {field: industry[field] for field in
            ("template_id", "primary_industry", "secondary_industry")}
        self.assertEqual(validate(FOCAL, industry, genuine, None), expected)
        for index, mid in enumerate(V_METRICS):
            with self.subTest(metric=mid):
                other = self.sources.valuation.input_for("SH600000", mid)
                other.require_verified()
                self.assertNotEqual(other.secondary_industry, expected["secondary_industry"])
                conflicting = list(genuine)
                conflicting[index] = other
                with self.assertRaisesRegex(ValueError, "member identity mismatch"):
                    validate(FOCAL, industry, tuple(conflicting), None)

    def test_batch_binds_root_frozen_universe_policy_and_valuation_hashes(self):
        batch, sources = self.batch, self.sources
        self.assertEqual(batch.registry_manifest_hash, self.fixture.bundle.manifest.manifest_hash)
        self.assertEqual(batch.frozen_input_hash, self.fixture.frozen.frozen_input_hash)
        self.assertEqual(batch.universe_hash, sources.base.universe_hash)
        for prefix, source in zip(("base", "policy", "valuation"), sources):
            self.assertEqual(getattr(batch, prefix + "_batch_hash"), source.batch_hash)
            self.assertEqual(getattr(batch, prefix + "_batch_canonical_sha256"),
                hashlib.sha256(source.canonical_bytes()).hexdigest())
        self.assertEqual(batch.policy_contract_hash, sources.policy.policy_contract_hash)
        self.assertEqual(batch.valuation_adapter_registry_hash,
            sources.valuation.valuation_adapter_registry_hash)
        for row in batch.inputs:
            self.assertEqual(row.batch_hash, batch.batch_hash)
            self.assertEqual(row.registry_manifest_hash, batch.registry_manifest_hash)
            self.assertEqual(row.frozen_input_hash, batch.frozen_input_hash)
            self.assertEqual(row.universe_hash, batch.universe_hash)

    def test_identical_inputs_replay_to_identical_canonical_bytes_and_hash(self):
        replay = build(self.fixture)
        self.assertEqual(replay.canonical_bytes(), self.batch.canonical_bytes())
        self.assertEqual(replay.batch_hash, self.batch.batch_hash)
        for sid in replay.security_ids:
            self.assertEqual(replay.input_for(sid).canonical_bytes(),
                self.batch.input_for(sid).canonical_bytes())
            self.assertEqual(replay.input_for(sid).entry_hash, self.batch.input_for(sid).entry_hash)


class FinalScoreInputCanonicalDecodeTests(unittest.TestCase):
    def test_detached_source_payload_preserves_fractional_lexemes_without_float(self):
        import json

        from ashare_pipeline.formal_final_repository import _serialize_payload

        closure = inspect.getclosurevars(
            FormalFinalScoreInputRepository.build_batch).nonlocals
        self.assertIn("detached_source_payload", closure)
        detach = closure["detached_source_payload"]
        builder_source = inspect.getsource(FormalFinalScoreInputRepository.build_batch)
        self.assertIn("detached_source_payload(original)", builder_source)
        for forbidden in ("original.to_dict()", "policy_result.to_dict()", "score.to_dict()",
                "context.to_dict()", "adjusted.to_dict()"):
            self.assertNotIn(forbidden, builder_source)
        for required in ('slot = dict(detached_original["slots"][mid])',
                'dict(detached_original["slots"])',
                "detached_policy_result = detached_source_payload(policy_result)",
                "detached_original = detached_source_payload(original)",
                "valuation_score=detached_source_payload(score)",
                "valuation_context=detached_source_payload(context)",
                "valuation_input=detached_source_payload(adjusted)",
                "policy_pending = detached_policy_result[\"pending_requirements\"]",
                "payload = {} if detached_original is None else dict(detached_original)",
                "policy_result=detached_policy_result"):
            self.assertIn(required, builder_source)
        exact = "0.12345678901234568"
        raw = ('{"count":7,"label":"深证","nested":[{"fraction":' + exact
            + '},[2,3]],"whole":-2}').encode()

        class Source:
            def __init__(self, canonical):
                self.canonical = canonical
                self.calls = []

            def require_verified(self):
                self.calls.append("require_verified")

            def canonical_bytes(self):
                self.calls.append("canonical_bytes")
                return self.canonical

            def to_dict(self):
                raise AssertionError("detached provenance must not use to_dict")

        source = Source(raw)
        payload = detach(source)
        self.assertEqual(source.calls, ["require_verified", "canonical_bytes"])
        self.assertEqual(payload["label"], "深证")
        self.assertEqual(payload["nested"][0]["fraction"], exact)
        self.assertIs(type(payload["count"]), int)
        self.assertIs(type(payload["whole"]), int)

        def values(value):
            if type(value) is dict:
                for item in value.values():
                    yield from values(item)
            elif type(value) is list:
                for item in value:
                    yield from values(item)
            else:
                yield value

        self.assertFalse(any(type(value) is float for value in values(payload)))
        serialized, _ = _serialize_payload(payload)
        self.assertIn('"fraction":"' + exact + '"', serialized)
        decoder = json.JSONDecoder
        json.JSONDecoder = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("module JSONDecoder replacement escaped the captured boundary"))
        try:
            with self.assertRaisesRegex(ValueError, "dependency changed"):
                detach(Source(raw))
        finally:
            json.JSONDecoder = decoder
        self.assertEqual(detach(Source(raw)), payload)
        decode_method = decoder.decode
        decoder.decode = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("mutated JSONDecoder.decode reached the decode boundary"))
        try:
            with self.assertRaisesRegex(ValueError, "dependency changed"):
                detach(Source(raw))
        finally:
            decoder.decode = decode_method
        self.assertEqual(detach(Source(raw)), payload)
        detect_encoding = json.detect_encoding
        json.detect_encoding = lambda *_: (_ for _ in ()).throw(
            AssertionError("detached source decoding must not detect bytes twice"))
        try:
            self.assertEqual(detach(Source(raw)), payload)
        finally:
            json.detect_encoding = detect_encoding
        with self.assertRaisesRegex(ValueError, "canonical bytes are not UTF-8"):
            detach(Source(b'{"label":"\xff"}'))
        for invalid in (
            b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}',
            b' {"value":0.5}', b'{"z":1,"a":0.5}', b'{"value":0.5,"value":1}',
            b'{"value":1e2}', b'{"value":1.2300}', b'{"value":1E+00}',
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                detach(Source(invalid))


class FinalScoreInputReadyTests(unittest.TestCase):
    def test_ready_input_contains_22_base_slots_and_exactly_three_stage_c_scores(self):
        fixture = FinalScoringFixture(peer_count=20)
        self.addCleanup(fixture.close)
        fixture.populate_final_inputs()
        sources = fixture.build_d1_sources()
        batch = build(fixture)
        self.assertEqual(batch.security_ids, tuple(sorted(fixture.templates)))
        self.assertEqual(len(batch.security_ids), 20)
        for sid in batch.security_ids:
            if sid != FOCAL:
                peer = batch.input_for(sid)
                self.assertEqual(peer.status, "pending_evidence")
                self.assertTrue(peer.policy_pending_requirements)
        for value in sources.valuation.inputs:
            if value.security_id != FOCAL:
                self.assertEqual(value.status, "passthrough_not_applicable")
        row = batch.input_for(FOCAL)
        self.assertEqual(row.status, "ready")
        self.assertEqual(row.reasons, ())
        self.assertEqual(len(row.slots), 25)
        base = sources.base.input_for(FOCAL)
        non_v = set(row.slots) - set(V_METRICS)
        self.assertEqual(len(non_v), 22)
        for mid in non_v:
            self.assertEqual(row.slots[mid], base.slots[mid])
        for mid in V_METRICS:
            context = build_valuation_peer_context(sources.valuation, metric_id=mid, security_id=FOCAL)
            score = score_valuation_percentile(sources.valuation, context)
            self.assertIsNotNone(score)
            self.assertEqual(score.peer_count, 20)
            slot = row.slots[mid]
            self.assertEqual(slot["evidence_kind"], "policy_adjusted_valuation")
            self.assertEqual(slot["value"], score.percentile)
            self.assertEqual(row.to_dict()["slots"][mid]["valuation_score"], score.to_dict())
            self.assertEqual(row.to_dict()["slots"][mid]["valuation_context"], context.to_dict())
            self.assertEqual(slot["valuation_score_hash"], score.score_hash)
            self.assertEqual(slot["valuation_context_hash"], context.context_hash)
            self.assertIsNone(slot["metric_score"])
        earnings = row.slots["V.normalized_earnings_yield"]
        # 0.20 * median(4, 5, 6, 7, 8) / 10 = 0.12, still above
        # the nineteen peers (0.101 through 0.119): rank 20 => 97.5.
        self.assertEqual(Decimal(earnings["valuation_score"]["adjusted_value"]), Decimal("0.12"))
        self.assertEqual(earnings["value"], Decimal("97.5"))


class FinalScoreInputTypeSealTests(unittest.TestCase):
    def test_minted_entry_relabelled_as_batch_is_rejected(self):
        fixture = FinalScoringFixture()
        self.addCleanup(fixture.close)
        fixture.populate_final_inputs()
        batch = build(fixture)
        proof = batch.input_for(FOCAL)
        proof.require_verified()
        minted_type = type(proof)
        object.__setattr__(proof, "__class__", type(batch))
        try:
            with self.assertRaises(ValueError):
                proof.require_verified()
        finally:
            object.__setattr__(proof, "__class__", minted_type)
        proof.require_verified()


if __name__ == "__main__":
    unittest.main()
