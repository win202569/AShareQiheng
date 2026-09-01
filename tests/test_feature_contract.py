import copy
import math
import unittest
from datetime import datetime

from ashare_pipeline.feature_contract import (
    CONTRACT_VERSION, DIMENSIONS, FINANCIAL_DIMENSIONS, ConfidenceInputs, DimensionInput,
    EvidenceRef, FeatureBundle, FeatureValue, IndustryContext,
)


def evidence(snapshot_id="snapshot-a"):
    return EvidenceRef("fact-a", snapshot_id, "TOTAL_ASSETS", "a" * 64,
                       "2026-08-20T15:59:59+00:00", "2026-08-21T07:00:00+00:00")


def dimensions():
    from tests.test_financial_features import build_bundle_with_overrides

    result = dict(build_bundle_with_overrides(facts=()).dimension_inputs)
    result["V"] = DimensionInput("missing", (FeatureValue(
        "v.market_cap", None, "CNY", "as_of", "missing", "observed-v1",
        (), "market_data_missing"),))
    result["T"] = DimensionInput("partial", (FeatureValue(
        "t.sample", 0.0, "ratio", "2026H1", "observed",
        "observed-v1", (evidence(),), None),))
    return result


def bundle(dimension_inputs=None, *, is_formal_score_ready=False, coverage=0.0,
           formal_confidence=None):
    from tests.test_financial_features import build_bundle_with_overrides

    baseline = build_bundle_with_overrides(facts=())
    return FeatureBundle(
        baseline.schema_version, baseline.contract_version, baseline.security_id,
        baseline.report_period, baseline.as_of_utc, baseline.candidate_set_hash,
        baseline.industry, baseline.input_hash, baseline.financial_status, coverage,
        ConfidenceInputs(coverage, {"timestamp": 0, "date_only": 1}, 3,
                          True, formal_confidence),
        dimensions() if dimension_inputs is None else dimension_inputs,
        baseline.blockers,
        is_formal_score_ready)


def real_general_ready_bundle():
    from tests.test_financial_features import build_bundle_with_overrides

    return build_bundle_with_overrides()


def real_specialized_bundle(industry_name):
    from tests.test_financial_features import build_bundle_with_overrides

    return build_bundle_with_overrides(source_industry_name=industry_name)


def real_unclassified_bundle():
    from tests.test_financial_features import build_bundle_with_overrides

    return build_bundle_with_overrides(source_industry_name="不存在行业")


def copy_financial_value_into_dimension_payload(
    payload,
    target_dimension,
    *,
    source_payload=None,
    source_dimension="M",
    feature_key="m.gross_profit.FY2021",
):
    source = source_payload or payload
    copied = copy.deepcopy(next(
        value
        for value in source["dimension_inputs"][source_dimension]["values"]
        if value["key"] == feature_key
    ))
    payload["dimension_inputs"][target_dimension] = {
        "status": "input_ready",
        "values": [copied],
    }
    return payload


def bundle_with_copied_financial_value(
    candidate,
    target_dimension,
    *,
    source_dimension="M",
    feature_key="m.gross_profit.FY2021",
):
    copied = next(
        value
        for value in candidate.dimension_inputs[source_dimension].values
        if value.key == feature_key
    )
    forged = copy.copy(candidate)
    forged_dimensions = dict(candidate.dimension_inputs)
    forged_dimensions[target_dimension] = DimensionInput("input_ready", (copied,))
    object.__setattr__(forged, "dimension_inputs", forged_dimensions)
    return forged


def retag_missing_revenue_slot(payload, attack):
    dimensions = payload["dimension_inputs"]
    target = next(
        value
        for value in dimensions["G"]["values"]
        if value["key"] == "g.revenue.FY2021"
    )
    dimensions["G"]["values"].remove(target)
    if attack == "derived_wrong_dimension":
        replacement = copy.deepcopy(next(
            value
            for value in dimensions["M"]["values"]
            if value["key"] == "m.gross_profit.FY2021"
        ))
        replacement["key"] = "m.revenue.FY2021"
        dimensions["M"]["values"].append(replacement)
    elif attack == "derived_correct_dimension":
        replacement = copy.deepcopy(next(
            value
            for value in dimensions["M"]["values"]
            if value["key"] == "m.gross_profit.FY2021"
        ))
        replacement["key"] = "g.revenue.FY2021"
        dimensions["G"]["values"].append(replacement)
    elif attack == "observed_wrong_dimension":
        target["key"] = "m.revenue.FY2021"
        dimensions["M"]["values"].append(target)
    elif attack == "observed_wrong_formula":
        target["formula_version"] = "financial-derived-v1"
        dimensions["G"]["values"].append(target)
    elif attack == "other_observed_raw_slot":
        replacement = copy.deepcopy(next(
            value
            for value in dimensions["M"]["values"]
            if value["key"] == "m.operating_cost.FY2021"
        ))
        replacement["key"] = "g.revenue.FY2021"
        dimensions["G"]["values"].append(replacement)
    else:
        raise AssertionError(f"unknown retag attack: {attack}")
    for dimension in dimensions.values():
        dimension["values"].sort(key=lambda value: (value["key"], value["period_key"]))
    return payload


class FeatureContractTests(unittest.TestCase):
    def test_bundle_requires_exactly_seven_dimensions_and_is_never_formal(self):
        self.assertEqual(DIMENSIONS, ("G", "V", "M", "EQ", "FS", "CA", "T"))
        with self.assertRaisesRegex(ValueError, "dimension keys"):
            bundle({key: value for key, value in dimensions().items() if key != "G"})
        with self.assertRaisesRegex(ValueError, "formal score"):
            bundle(dimensions(), is_formal_score_ready=True)

    def test_zero_missing_and_nonfinite_values_have_distinct_contracts(self):
        self.assertEqual(dimensions()["T"].values[0].value, 0.0)
        self.assertIsNone(dimensions()["V"].values[0].value)
        for invalid in (True, math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                FeatureValue("g.invalid", invalid, "ratio", "2026H1", "observed",
                             "observed-v1", (evidence(),), None)

    def test_canonical_hash_is_order_independent_and_evidence_sensitive(self):
        first = bundle()
        second = bundle(dict(reversed(tuple(dimensions().items()))))
        changed = bundle({**dimensions(), "T": DimensionInput("partial", (FeatureValue(
            "t.sample", 0.0, "ratio", "2026H1", "observed", "observed-v1",
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

    def test_missing_dimension_accepts_missing_slots_mixed_with_not_applicable(self):
        missing = FeatureValue(
            "m.required", None, "ratio", "FY2022", "missing", "derived-v1",
            (), "financial_fact_missing:required",
        )
        not_applicable = FeatureValue(
            "m.opening", None, "ratio", "FY2021", "not_applicable",
            "derived-v1", (), "frozen_window_no_opening_period",
        )

        candidate = DimensionInput("missing", (missing, not_applicable))

        self.assertEqual(candidate.status, "missing")
        self.assertEqual(
            {value.status for value in candidate.values},
            {"missing", "not_applicable"},
        )

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
            IndustryContext("eastmoney-provisional", None, "包装印刷", "general_nonfinancial", "template-registry-v2", False),
            "1" * 64, "partial", 0.0,
            ConfidenceInputs(0.0, raw_counts, 3, True, None), raw_dimensions,
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

    def test_input_ready_accepts_ready_values_mixed_with_not_applicable(self):
        observed = FeatureValue(
            "g.observed", 1.0, "ratio", "FY2022", "observed", "observed-v1",
            (evidence(),), None,
        )
        derived = FeatureValue(
            "g.derived", 2.0, "ratio", "FY2022", "derived", "derived-v1",
            (evidence(),), None,
        )
        not_applicable = FeatureValue(
            "g.not_applicable", None, "ratio", "FY2021", "not_applicable",
            "derived-v1", (), "frozen_window_no_opening_period",
        )
        candidate = DimensionInput("input_ready", (observed, derived, not_applicable))
        self.assertEqual(candidate.status, "input_ready")
        self.assertEqual(
            {value.status for value in candidate.values},
            {"observed", "derived", "not_applicable"},
        )

    def test_input_ready_rejects_missing_or_blocked_applicable_values(self):
        observed = FeatureValue(
            "g.observed", 1.0, "ratio", "FY2022", "observed", "observed-v1",
            (evidence(),), None,
        )
        for status in ("missing", "blocked"):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "input_ready"):
                incomplete = FeatureValue(
                    f"g.{status}", None, "ratio", "FY2021", status,
                    "derived-v1", (), f"{status}_reason",
                )
                DimensionInput("input_ready", (observed, incomplete))

    def test_input_ready_requires_at_least_one_observed_or_derived_value(self):
        not_applicable = FeatureValue(
            "g.not_applicable", None, "ratio", "FY2021", "not_applicable",
            "derived-v1", (), "frozen_window_no_opening_period",
        )
        for values in ((), (not_applicable,)):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "input_ready"):
                DimensionInput("input_ready", values)

    def test_public_parse_rejects_canonical_but_semantically_invalid_bundles(self):
        cases = {
            "schema_type": lambda value: value.__setitem__("schema_version", True),
            "security_id": lambda value: value.__setitem__("security_id", "600001"),
            "report_date": lambda value: value.__setitem__("report_period", "2026-6-30"),
            "as_of_type": lambda value: value.__setitem__("as_of_utc", 7),
            "candidate_hash": lambda value: value.__setitem__("candidate_set_hash", "c" * 63),
            "input_hash": lambda value: value.__setitem__("input_hash", "not-a-hash"),
            "template_version": lambda value: value["industry"].__setitem__(
                "template_version", "template-registry-v0"
            ),
            "template_binding": lambda value: value["industry"].__setitem__(
                "template_id", "bank"
            ),
            "count_keys": lambda value: value["confidence_inputs"].__setitem__(
                "date_precision_counts", {"timestamp": 0}
            ),
            "negative_history_count": lambda value: value["confidence_inputs"].__setitem__(
                "history_years_present", -1
            ),
            "mapping_boolean": lambda value: value["confidence_inputs"].__setitem__(
                "mapping_consistent", 1
            ),
            "ready_coverage": lambda value: value.__setitem__(
                "financial_status", "financial_ready"
            ),
            "coverage_mismatch": lambda value: value["confidence_inputs"].__setitem__(
                "data_completeness_ratio", 0.4
            ),
            "blocker_type": lambda value: value.__setitem__(
                "blockers", ["formal_industry_mapping_missing", 7]
            ),
        }
        baseline = bundle().to_dict()
        for field, mutate in cases.items():
            with self.subTest(field=field):
                payload = copy.deepcopy(baseline)
                mutate(payload)
                with self.assertRaises(ValueError):
                    FeatureBundle.from_dict(payload)

    def test_public_parse_rejects_ready_missing_or_blocked_financial_inputs(self):
        baseline = real_general_ready_bundle().to_dict()

        def replace_first_applicable_value(value, dimension, status):
            target = next(
                item
                for item in value["dimension_inputs"][dimension]["values"]
                if item["status"] in {"observed", "derived"}
            )
            target.update({
                "value": None,
                "status": status,
                "evidence": [],
                "missing_reason": f"forged_{status}",
            })
            value["dimension_inputs"][dimension]["status"] = "partial"

        for dimension in FINANCIAL_DIMENSIONS:
            cases = {
                "missing_dimension": lambda value, dimension=dimension: value[
                    "dimension_inputs"
                ].__setitem__(dimension, {"status": "missing", "values": []}),
                "blocked_dimension": lambda value, dimension=dimension: value[
                    "dimension_inputs"
                ][dimension].__setitem__("status", "blocked"),
                "missing_value": lambda value, dimension=dimension: replace_first_applicable_value(
                    value, dimension, "missing"
                ),
                "blocked_value": lambda value, dimension=dimension: replace_first_applicable_value(
                    value, dimension, "blocked"
                ),
            }
            for attack, mutate in cases.items():
                with self.subTest(dimension=dimension, attack=attack):
                    payload = copy.deepcopy(baseline)
                    mutate(payload)
                    with self.assertRaises(ValueError):
                        FeatureBundle.from_dict(payload)

    def test_public_parse_rejects_ready_with_registered_slot_period_omitted(self):
        payload = real_general_ready_bundle().to_dict()
        payload["dimension_inputs"]["G"]["values"] = [
            value
            for value in payload["dimension_inputs"]["G"]["values"]
            if value["key"] != "g.revenue.FY2021"
        ]

        with self.assertRaises(ValueError):
            FeatureBundle.from_dict(payload)

    def test_public_parse_authenticates_closed_derived_projection(self):
        baseline = real_general_ready_bundle().to_dict()

        def target(value):
            return next(
                item
                for item in value["dimension_inputs"]["M"]["values"]
                if item["key"] == "m.gross_profit.FY2021"
            )

        def omit(value):
            value["dimension_inputs"]["M"]["values"].remove(target(value))

        def add_unknown(value):
            extra = copy.deepcopy(target(value))
            extra["key"] = "m.unknown_formula.FY2021"
            value["dimension_inputs"]["M"]["values"].append(extra)

        def move_wrong_dimension(value):
            moved = target(value)
            value["dimension_inputs"]["M"]["values"].remove(moved)
            value["dimension_inputs"]["G"]["values"].append(moved)

        def copy_cross_dimension(value):
            value["dimension_inputs"]["G"]["values"].append(
                copy.deepcopy(target(value))
            )

        attacks = {
            "formula_version": lambda value: target(value).__setitem__(
                "formula_version", "financial-derived-v2"
            ),
            "omission": omit,
            "unknown": add_unknown,
            "wrong_key": lambda value: target(value).__setitem__(
                "key", "m.gross_profit.FY2099"
            ),
            "wrong_period": lambda value: target(value).__setitem__(
                "period_key", "FY2022"
            ),
            "wrong_dimension": move_wrong_dimension,
            "cross_dimension_copy": copy_cross_dimension,
        }
        for case, attack in attacks.items():
            with self.subTest(case=case):
                payload = copy.deepcopy(baseline)
                attack(payload)
                with self.assertRaisesRegex(ValueError, "financial projection"):
                    FeatureBundle.from_dict(payload)

    def test_public_parse_rejects_financial_projection_copies_in_v_and_t(self):
        sources = (
            ("formula", "M", "m.gross_profit.FY2021"),
            ("raw", "G", "g.revenue.FY2021"),
        )
        for case, source_dimension, feature_key in sources:
            for target_dimension in ("V", "T"):
                with self.subTest(
                    case=case, target_dimension=target_dimension
                ):
                    payload = copy_financial_value_into_dimension_payload(
                        real_general_ready_bundle().to_dict(),
                        target_dimension,
                        source_dimension=source_dimension,
                        feature_key=feature_key,
                    )
                    with self.assertRaisesRegex(ValueError, "financial projection"):
                        FeatureBundle.from_dict(payload)

        restored = FeatureBundle.from_dict(bundle().to_dict())
        self.assertEqual(restored.dimension_inputs["V"].values[0].key, "v.market_cap")
        self.assertEqual(restored.dimension_inputs["T"].values[0].key, "t.sample")

    def test_exact_formula_set_applies_to_partial_and_blocked_common_templates(self):
        from tests.test_financial_features import build_bundle_with_overrides

        candidates = (
            build_bundle_with_overrides(facts=()),
            real_specialized_bundle("房地产开发"),
        )
        self.assertEqual(
            tuple(candidate.financial_status for candidate in candidates),
            ("partial", "blocked"),
        )
        for candidate in candidates:
            with self.subTest(status=candidate.financial_status):
                payload = candidate.to_dict()
                values = payload["dimension_inputs"]["M"]["values"]
                values.remove(
                    next(
                        value
                        for value in values
                        if value["key"] == "m.gross_profit.FY2021"
                    )
                )
                with self.assertRaisesRegex(ValueError, "financial projection"):
                    FeatureBundle.from_dict(payload)

    def test_no_output_templates_keep_an_empty_financial_namespace(self):
        for industry_name in ("银行", "保险", "证券", "不存在行业"):
            with self.subTest(industry=industry_name):
                candidate = real_specialized_bundle(industry_name)
                restored = FeatureBundle.from_dict(candidate.to_dict())
                self.assertEqual(restored.financial_coverage, 0.0)
                self.assertEqual(
                    sum(
                        len(restored.dimension_inputs[dimension].values)
                        for dimension in FINANCIAL_DIMENSIONS
                    ),
                    0,
                )
                payload = candidate.to_dict()
                payload["dimension_inputs"]["M"] = {
                    "status": "missing",
                    "values": [
                        {
                            "key": "m.unknown_formula.FY2021",
                            "value": None,
                            "unit": "CNY",
                            "period_key": "FY2021",
                            "status": "missing",
                            "formula_version": "financial-derived-v1",
                            "evidence": [],
                            "missing_reason": "missing_operand:unknown_formula",
                        }
                    ],
                }
                with self.assertRaisesRegex(ValueError, "financial projection"):
                    FeatureBundle.from_dict(payload)

    def test_no_output_templates_reject_financial_formula_values_in_v_and_t(self):
        financial_source = real_general_ready_bundle().to_dict()
        for industry_name in ("银行", "不存在行业"):
            for target_dimension in ("V", "T"):
                with self.subTest(
                    industry=industry_name, target_dimension=target_dimension
                ):
                    payload = copy_financial_value_into_dimension_payload(
                        real_specialized_bundle(industry_name).to_dict(),
                        target_dimension,
                        source_payload=financial_source,
                    )
                    with self.assertRaisesRegex(ValueError, "financial projection"):
                        FeatureBundle.from_dict(payload)

    def test_public_parse_rejects_registered_raw_slot_retag_substitutions(self):
        attacks = (
            "derived_wrong_dimension",
            "derived_correct_dimension",
            "observed_wrong_dimension",
            "observed_wrong_formula",
            "other_observed_raw_slot",
        )
        for attack in attacks:
            with self.subTest(attack=attack):
                payload = retag_missing_revenue_slot(
                    real_general_ready_bundle().to_dict(), attack
                )
                with self.assertRaises(ValueError):
                    FeatureBundle.from_dict(payload)

    def test_public_parse_enforces_specialized_template_blocker(self):
        for industry_name in ("房地产开发", "工业金属", "银行"):
            baseline = real_specialized_bundle(industry_name).to_dict()
            self.assertIn("specialized_financial_inputs_missing", baseline["blockers"])
            for status in ("financial_ready", "blocked"):
                with self.subTest(industry=industry_name, status=status):
                    payload = copy.deepcopy(baseline)
                    payload["financial_status"] = status
                    payload["blockers"].remove("specialized_financial_inputs_missing")
                    with self.assertRaises(ValueError):
                        FeatureBundle.from_dict(payload)

    def test_public_parse_enforces_point_in_time_cutoff_for_all_evidence(self):
        attacks = (
            (bundle().to_dict(), "T", "t.sample", "observed_nonfinancial_partial"),
            (
                real_general_ready_bundle().to_dict(),
                "M",
                "m.gross_profit.FY2021",
                "derived_financial_ready",
            ),
        )
        for payload, dimension, feature_key, case in attacks:
            with self.subTest(case=case):
                target = next(
                    value
                    for value in payload["dimension_inputs"][dimension]["values"]
                    if value["key"] == feature_key
                )
                target["evidence"][0]["effective_at_utc"] = (
                    "2026-08-29T12:30:00-04:00"
                )
                with self.assertRaisesRegex(ValueError, "effective.*as_of"):
                    FeatureBundle.from_dict(payload)

        accepted = (
            ("exact_equal", "2026-08-30T00:00:00+08:00"),
            ("earlier_despite_later_wall_clock", "2026-08-29T17:00:00+02:00"),
        )
        for case, effective_at in accepted:
            with self.subTest(case=case):
                payload = bundle().to_dict()
                target = payload["dimension_inputs"]["T"]["values"][0]
                target["evidence"][0]["effective_at_utc"] = effective_at
                restored = FeatureBundle.from_dict(payload)
                self.assertLessEqual(
                    datetime.fromisoformat(
                        restored.dimension_inputs["T"]
                        .values[0]
                        .evidence[0]
                        .effective_at_utc
                    ),
                    datetime.fromisoformat(restored.as_of_utc),
                )

    def test_public_parse_keeps_unclassified_blocked_with_zero_coverage(self):
        baseline = real_unclassified_bundle().to_dict()
        attacks = {
            "partial_with_blocker": lambda value: value.__setitem__(
                "financial_status", "partial"
            ),
            "partial_without_blocker": lambda value: (
                value.__setitem__("financial_status", "partial"),
                value["blockers"].remove("industry_template_unclassified"),
            ),
            "blocked_without_blocker": lambda value: value["blockers"].remove(
                "industry_template_unclassified"
            ),
            "nonzero_coverage": lambda value: (
                value.__setitem__("financial_coverage", 0.25),
                value["confidence_inputs"].__setitem__(
                    "data_completeness_ratio", 0.25
                ),
            ),
        }
        for case, attack in attacks.items():
            with self.subTest(case=case):
                payload = copy.deepcopy(baseline)
                attack(payload)
                with self.assertRaisesRegex(ValueError, "unclassified"):
                    FeatureBundle.from_dict(payload)

        restored = FeatureBundle.from_dict(copy.deepcopy(baseline))
        self.assertEqual(restored.industry.template_id, "unclassified")
        self.assertEqual(restored.financial_status, "blocked")
        self.assertEqual(restored.financial_coverage, 0.0)
        self.assertIn("industry_template_unclassified", restored.blockers)

    def test_general_ready_bundle_still_has_canonical_public_round_trip(self):
        candidate = real_general_ready_bundle()

        restored = FeatureBundle.from_dict(candidate.to_dict())

        self.assertEqual(restored.financial_status, "financial_ready")
        self.assertEqual(restored.financial_coverage, 1.0)
        self.assertEqual(restored.canonical_bytes(), candidate.canonical_bytes())


if __name__ == "__main__":
    unittest.main()
