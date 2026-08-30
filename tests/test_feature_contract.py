import math
import unittest

from ashare_pipeline.feature_contract import (
    CONTRACT_VERSION, DIMENSIONS, ConfidenceInputs, DimensionInput,
    EvidenceRef, FeatureBundle, FeatureValue, IndustryContext,
)


def evidence(snapshot_id="snapshot-a"):
    return EvidenceRef("fact-a", snapshot_id, "TOTAL_ASSETS", "a" * 64,
                       "2026-08-20T15:59:59+00:00", "2026-08-21T07:00:00+00:00")


def dimensions():
    result = {key: DimensionInput("partial", (FeatureValue(
        f"{key.lower()}.sample", 0.0, "ratio", "2026H1", "observed",
        "observed-v1", (evidence(),), None),)) for key in DIMENSIONS}
    result["V"] = DimensionInput("missing", (FeatureValue(
        "v.market_cap", None, "CNY", "as_of", "missing", "observed-v1",
        (), "market_data_missing"),))
    return result


def bundle(dimension_inputs=None, *, is_formal_score_ready=False, coverage=0.5,
           formal_confidence=None):
    return FeatureBundle(
        1, CONTRACT_VERSION, "SH600001", "2026-06-30",
        "2026-08-29T16:00:00+00:00", "c" * 64,
        IndustryContext("eastmoney-provisional", None, "包装印刷",
                        "general_nonfinancial", "template-registry-v1", False),
        "1" * 64, "partial", coverage,
        ConfidenceInputs(coverage, {"timestamp": 0, "date_only": 1}, 3,
                          True, formal_confidence),
        dimension_inputs or dimensions(), ("formal_industry_mapping_missing",),
        is_formal_score_ready)


class FeatureContractTests(unittest.TestCase):
    def test_bundle_requires_exactly_seven_dimensions_and_is_never_formal(self):
        self.assertEqual(DIMENSIONS, ("G", "V", "M", "EQ", "FS", "CA", "T"))
        with self.assertRaisesRegex(ValueError, "dimension keys"):
            bundle({key: value for key, value in dimensions().items() if key != "G"})
        with self.assertRaisesRegex(ValueError, "formal score"):
            bundle(dimensions(), is_formal_score_ready=True)

    def test_zero_missing_and_nonfinite_values_have_distinct_contracts(self):
        self.assertEqual(dimensions()["G"].values[0].value, 0.0)
        self.assertIsNone(dimensions()["V"].values[0].value)
        for invalid in (True, math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                FeatureValue("g.invalid", invalid, "ratio", "2026H1", "observed",
                             "observed-v1", (evidence(),), None)

    def test_canonical_hash_is_order_independent_and_evidence_sensitive(self):
        first = bundle()
        second = bundle(dict(reversed(tuple(dimensions().items()))))
        changed = bundle({**dimensions(), "G": DimensionInput("partial", (FeatureValue(
            "g.sample", 0.0, "ratio", "2026H1", "observed", "observed-v1",
            (evidence("snapshot-b"),), None),))})
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(first.bundle_hash(), second.bundle_hash())
        self.assertNotEqual(first.bundle_hash(), changed.bundle_hash())

    def test_rejects_incomplete_evidence_and_naive_timestamps(self):
        with self.assertRaises(ValueError):
            EvidenceRef("fact", "snap", "field", "a" * 64, "2026-08-20", "2026-08-21T00:00:00+00:00")
        with self.assertRaises(ValueError):
            FeatureValue("g.x", 1, "ratio", "2026H1", "observed", "v1", (), None)

    def test_rejects_invalid_coverage_and_formal_confidence(self):
        for coverage in (-0.01, 1.01):
            with self.assertRaises(ValueError):
                bundle(coverage=coverage)
        with self.assertRaisesRegex(ValueError, "formal_confidence"):
            bundle(formal_confidence=0.8)

    def test_rejects_inconsistent_observed_and_missing_states(self):
        bad = dict(dimensions())
        with self.assertRaises(ValueError):
            bad["V"] = DimensionInput("missing", (FeatureValue(
                "v.x", 1.0, "CNY", "as_of", "observed", "v1", (evidence(),), None),))
            bundle(bad)

    def test_json_round_trip(self):
        restored = FeatureBundle.from_dict(bundle().to_dict())
        self.assertEqual(restored.to_dict(), bundle().to_dict())

    def test_bundle_defensively_freezes_nested_inputs(self):
        raw_dimensions = dimensions()
        raw_counts = {"timestamp": 0, "date_only": 1}
        raw_blockers = ["formal_industry_mapping_missing"]
        candidate = FeatureBundle(
            1, CONTRACT_VERSION, "SH600001", "2026-06-30",
            "2026-08-29T16:00:00+00:00", "c" * 64,
            IndustryContext("eastmoney-provisional", None, "包装印刷", "general_nonfinancial", "template-registry-v1", False),
            "1" * 64, "partial", 0.5,
            ConfidenceInputs(0.5, raw_counts, 3, True, None), raw_dimensions,
            raw_blockers, False)
        before = (candidate.to_dict(), candidate.bundle_hash())
        raw_dimensions["G"] = raw_dimensions["V"]
        raw_counts["timestamp"] = 99
        raw_blockers.append("changed-after-construction")
        self.assertEqual((candidate.to_dict(), candidate.bundle_hash()), before)

    def test_dimension_rejects_duplicate_key_and_period(self):
        value = FeatureValue("g.sample", 0.0, "ratio", "2026H1", "observed", "observed-v1", (evidence(),), None)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            DimensionInput("partial", (value, value))


if __name__ == "__main__":
    unittest.main()
