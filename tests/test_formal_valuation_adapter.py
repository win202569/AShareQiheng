"""Detached valuation arithmetic and per-metric policy state contract."""

from decimal import Decimal, ROUND_DOWN, localcontext
import copy
import unittest

from ashare_pipeline.formal_policy_values import digest
from ashare_pipeline.formal_valuation_adapter import (
    evaluate_valuation_adjustment, profit_ratio_rescale,
)


H = "a" * 64
ROOT = "b" * 64
RULE = "bank_cyclic_top"
METRIC = "V.earnings_yield"


def fixtures(*, state="matched", dependency_state="affected", current="10",
             normalized="6", value="0.20"):
    dependency = dict(metric_id=METRIC, policy_dependency=dependency_state,
        profit_semantic_id="cyclic_top" if dependency_state == "affected" else None,
        adapter_id="ratio" if dependency_state == "affected" else None,
        adapter_version="v1" if dependency_state == "affected" else None,
        definition_basis="linear current profit")
    adapter = None if dependency_state == "unaffected" else dict(
        template_id="bank", metric_id=METRIC, adapter_id="ratio", adapter_version="v1",
        operation="profit_ratio_rescale_v1", original_definition_hash=H,
        profit_semantic_id="cyclic_top", metric_unit="ratio", profit_unit="CNY",
        output_unit="ratio", policy_role="cyclic", rule_id=RULE,
        decimal_contract="decimal50-half-even-v1",
        preconditions=("exact_units", "finite_decimals", "nonzero_original_current_profit"),
        definition_basis="linear current profit")
    basis = dict(profit_semantic_id="cyclic_top",
        original_current_profit=dict(selector_hash=H, value=current, evidence_hashes=[H]),
        annual_profit=[], ordered_values=[], median_method="ordered_middle_v1",
        median=normalized, profit_basis_method="minimum_current_and_five_fy_median_v1",
        normalized_profit=normalized, valuation_dependencies=[copy.deepcopy(dependency)])
    decision = dict(rule_id=RULE, role="cyclic", semantic_id="cyclic_top",
        template_id="bank", security_id="SH600000", definition_hash=H,
        input_references=[dict(input_name="current_profit", selector_hash=H,
            state="value", value_type="decimal", unit="CNY", evidence_hashes=[H])],
        operands=(dict(current_roe="5", annual_roe_quantile="4", current_margin="5",
            annual_margin_quantile="4", quantile_method="linear_type7_v1",
            quantile_level="0.80", normalization_basis=basis) if state == "matched" else {}),
        parameters={"valuation_dependencies": [copy.deepcopy(dependency)]},
        evaluation_state=state, proven_effects=[], pending_requirements=[], trace={})
    decision["decision_hash"] = digest(decision)
    result = dict(registry_manifest_hash=ROOT, frozen_input_hash=H, universe_hash=H,
        as_of_utc="2026-08-31T07:00:00+00:00", policy_contract_hash=H,
        role_hashes={}, security_id="SH600000", decisions=[copy.deepcopy(decision)],
        dimension_caps={}, pool_prohibitions={}, states={},
        normalization_basis=[dict(**copy.deepcopy(basis), rule_id=RULE,
            definition_hash=H, trace={})] if state == "matched" else [],
        pending_requirements=[], evidence_state="complete")
    result["result_hash"] = digest(result)
    metric = dict(registry_manifest_hash=ROOT, frozen_input_hash=H, universe_hash=H,
        population_hash=H, as_of_utc="2026-08-31T07:00:00+00:00",
        industry_batch_hash=H, registry_hashes={}, universe_proof_hash=H,
        security_id="SH600000", metric_id=METRIC, template_id="bank",
        primary_industry="bank", secondary_industry="bank", definition_hash=H,
        direction="higher", unit="ratio", raw_value=value, verified_feature_refs=[H],
        invalid_reason=None, status="eligible", projection_hash=H, feature_state_hash=H)
    metric["input_hash"] = digest(metric)
    return dict(metric=metric, policy_result=result, cyclic_decision=decision,
        dependency=dependency, adapter=adapter)


def rehash(args):
    args["cyclic_decision"]["decision_hash"] = digest({k: v for k, v in args["cyclic_decision"].items()
        if k != "decision_hash"})
    args["policy_result"]["decisions"] = [copy.deepcopy(args["cyclic_decision"])]
    args["policy_result"]["result_hash"] = digest({k: v for k, v in args["policy_result"].items()
        if k != "result_hash"})
    args["metric"]["input_hash"] = digest({k: v for k, v in args["metric"].items()
        if k != "input_hash"})


class ValuationAdjustmentTests(unittest.TestCase):
    def test_affected_matched_rescales_value_and_binds_inputs(self):
        args = fixtures()
        result = evaluate_valuation_adjustment(**args)
        self.assertEqual((result["status"], result["adjusted_value"]), ("adjusted", "0.12"))
        self.assertEqual(result["decision_hash"], args["cyclic_decision"]["decision_hash"])
        self.assertEqual(result["operation"], "profit_ratio_rescale_v1")
        self.assertEqual(result["original_current_profit"], "10")
        self.assertEqual(result["normalized_profit"], "6")
        self.assertEqual(result["adapter_definition_hash"], digest({**args["adapter"],
            "preconditions": list(args["adapter"]["preconditions"])}))
        self.assertEqual(result["result_hash"], digest({k: v for k, v in result.items()
            if k != "result_hash"}))
        self.assertNotIn("proof", result)

    def test_states_obey_metric_dependency(self):
        for state, dependency, expected in (
                ("clear", "affected", "passthrough_clear"),
                ("not_applicable", "affected", "passthrough_not_applicable"),
                ("matched", "unaffected", "passthrough_unaffected"),
                ("pending_evidence", "unaffected", "passthrough_unaffected"),
                ("pending_evidence", "affected", "pending_policy_evidence")):
            with self.subTest(state=state, dependency=dependency):
                result = evaluate_valuation_adjustment(**fixtures(
                    state=state, dependency_state=dependency))
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["adjusted_value"], None if expected == "pending_policy_evidence" else "0.2")

    def test_adjusted_no_numeric_change_remains_adjustment(self):
        result = evaluate_valuation_adjustment(**fixtures(normalized="10"))
        self.assertEqual((result["status"], result["adjusted_value"]),
                         ("adjusted_no_numeric_change", "0.2"))

    def test_invalid_operands_fail_closed(self):
        for current, normalized, value, reason in (
                ("0", "6", "0.20", "original_current_profit_zero"),
                ("10", "6", "NaN", "metric_value_nonfinite"),
                ("10", "Infinity", "0.20", "normalized_profit_nonfinite"),
                ("bogus", "6", "0.20", "original_current_profit_invalid")):
            with self.subTest(reason=reason):
                result = evaluate_valuation_adjustment(**fixtures(
                    current=current, normalized=normalized, value=value))
                self.assertEqual((result["status"], result["reason"], result["adjusted_value"]),
                                 ("invalid_adapter_operand", reason, None))

    def test_unit_and_direction_mismatch_fail_closed(self):
        for field, changed, reason in (("unit", "CNY", "metric_unit_mismatch"),
                                       ("direction", "sideways", "metric_direction_invalid")):
            with self.subTest(field=field):
                args = fixtures()
                args["metric"][field] = changed
                rehash(args)
                result = evaluate_valuation_adjustment(**args)
                self.assertEqual((result["reason"], result["adjusted_value"]), (reason, None))

    def test_rejects_extra_fields_and_cross_object_identity_mismatch_before_state(self):
        for target, field, value in (("metric", "status", "adjusted"),
                                     ("adapter", "adjusted_value", "9"),
                                     ("policy_result", "security_id", "SZ000001"),
                                     ("cyclic_decision", "template_id", "broker"),
                                     ("dependency", "metric_id", "V.other"),
                                     ("adapter", "profit_semantic_id", "other")):
            with self.subTest(target=target, field=field):
                args = fixtures(state="clear")
                args[target][field] = value
                with self.assertRaises(ValueError):
                    evaluate_valuation_adjustment(**args)

    def test_rejects_missing_or_multiple_normalization_basis_and_unaffected_adapter(self):
        for mutation in (lambda x: x["cyclic_decision"]["operands"].clear(),
                         lambda x: x["cyclic_decision"]["operands"]["normalization_basis"].update(
                             extra="basis"),
                         lambda x: x["policy_result"]["normalization_basis"].extend([{}, {}])):
            args = fixtures()
            mutation(args)
            rehash(args)
            with self.assertRaises(ValueError):
                evaluate_valuation_adjustment(**args)
        args = fixtures(dependency_state="unaffected")
        args["adapter"] = fixtures()["adapter"]
        with self.assertRaises(ValueError):
            evaluate_valuation_adjustment(**args)

    def test_rejects_extra_nested_dependency_fields_even_on_other_metric(self):
        args = fixtures()
        foreign = dict(args["dependency"], metric_id="V.other", unexpected="input")
        args["cyclic_decision"]["parameters"]["valuation_dependencies"].append(foreign)
        args["cyclic_decision"]["operands"]["normalization_basis"]["valuation_dependencies"].append(
            copy.deepcopy(foreign))
        args["policy_result"]["normalization_basis"][0]["valuation_dependencies"].append(
            copy.deepcopy(foreign))
        rehash(args)
        with self.assertRaises(ValueError):
            evaluate_valuation_adjustment(**args)

    def test_affected_profit_semantic_must_identify_cyclic_decision(self):
        args = fixtures()
        args["dependency"]["profit_semantic_id"] = "other_profit"
        args["adapter"]["profit_semantic_id"] = "other_profit"
        args["cyclic_decision"]["parameters"]["valuation_dependencies"][0][
            "profit_semantic_id"] = "other_profit"
        args["cyclic_decision"]["operands"]["normalization_basis"][
            "valuation_dependencies"][0]["profit_semantic_id"] = "other_profit"
        args["policy_result"]["normalization_basis"][0]["valuation_dependencies"][0][
            "profit_semantic_id"] = "other_profit"
        rehash(args)
        with self.assertRaises(ValueError):
            evaluate_valuation_adjustment(**args)

    def test_local_decimal_context_is_deterministic_and_requires_exact_decimal(self):
        with localcontext() as ambient:
            ambient.prec = 2
            ambient.rounding = ROUND_DOWN
            first = profit_ratio_rescale(Decimal("0.2"), Decimal("3"), Decimal("2"))
        self.assertEqual(first, profit_ratio_rescale(Decimal("0.2"), Decimal("3"), Decimal("2")))
        with self.assertRaises(ValueError):
            profit_ratio_rescale(0.2, Decimal("3"), Decimal("2"))


if __name__ == "__main__":
    unittest.main()
