"""Pure policy evaluation and aggregation against the signed Stage A shapes."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, localcontext
import hashlib
import json
import unittest

from ashare_pipeline.formal_policy_contract import parse_policy_rule
from ashare_pipeline.formal_policy_market import evaluate_window
from ashare_pipeline.formal_policy_values import PolicyValue, canonical_bytes, digest
from tests.formal_policy_fixtures import (
    boolean_rule,
    cyclic_rule,
    enum_rule,
    market_rule,
    numeric_rule,
)
from tests.test_formal_scoring_registry import canonical


HASHES = tuple(hashlib.sha256(label.encode()).hexdigest() for label in (
    "equity", "roe", "margin", "profit", "annual", "market",
))


def parsed_rule(wire, role, rule_id):
    """Return the exact JSON rule shape only after the real parser accepts it."""
    parse_policy_rule(role, rule_id, canonical(wire))
    return dict(json.loads(canonical(wire)), role=role, rule_id=rule_id)


def policy_value(value, value_type="decimal", unit="ratio", *, evidence=HASHES[0]):
    if value_type == "decimal":
        value = str(value)
    else:
        unit = None
    return PolicyValue.from_dict({
        "state": "value",
        "value": value,
        "value_type": value_type,
        "unit": unit,
        "evidence_hashes": [evidence],
        "pending": [],
    })


def missing_value(code="financial_input_missing", *, evidence=HASHES[4],
                  value_type="decimal", unit="ratio"):
    return PolicyValue.from_dict({
        "state": "missing",
        "value": None,
        "value_type": value_type,
        "unit": unit,
        "evidence_hashes": [evidence],
        "pending": [{
            "origin": "runtime",
            "code": code,
            "rule_id": None,
            "evidence_hashes": [evidence],
        }],
    })


def annual_records(series_selector, numbers, *, missing_index=None, unit="ratio"):
    records = []
    for index, (observation, number) in enumerate(zip(
            series_selector["observations"], numbers, strict=True)):
        selector = observation["selector"]
        evidence = hashlib.sha256((selector["feature_key"] + "-evidence").encode()).hexdigest()
        value = (missing_value(evidence=evidence, unit=unit) if index == missing_index
                 else policy_value(number, unit=unit, evidence=evidence))
        records.append({
            "fy_end": observation["fy_end"],
            "selector_hash": digest(selector),
            "slot_hash": hashlib.sha256((selector["feature_key"] + "-slot").encode()).hexdigest(),
            "formula_hash": hashlib.sha256((selector["feature_key"] + "-formula").encode()).hexdigest(),
            "formula_version": selector["formula_version"],
            "value": value,
            "unit": selector["expected_unit"],
            "facts": (),
            "issues": (),
            "source_refs": (),
            "visibility": {},
            "bridge_version": "v6_feature_decimal_bridge_v1",
            "projection_hash": evidence,
        })
    return tuple(records)


def cyclic_inputs(rule, *, roe="9", margin="9", profit="7",
                  annual_roe=("1", "2", "3", "4", "5"),
                  annual_margin=("1", "2", "3", "4", "5"),
                  annual_profit=("-2", "-1", "0", "1", "2"),
                  missing_margin_index=None):
    inputs = rule["inputs"]
    values = {
        digest(inputs["current_roe"]): policy_value(roe, evidence=HASHES[1]),
        digest(inputs["current_margin"]): policy_value(margin, evidence=HASHES[2]),
        digest(inputs["current_profit"]): policy_value(
            profit, unit="CNY", evidence=HASHES[3]
        ),
    }
    annual = {
        digest(inputs["annual_roe"]): annual_records(inputs["annual_roe"], annual_roe),
        digest(inputs["annual_margin"]): annual_records(
            inputs["annual_margin"], annual_margin, missing_index=missing_margin_index
        ),
        digest(inputs["annual_profit"]): annual_records(
            inputs["annual_profit"], annual_profit, unit="CNY"
        ),
    }
    return values, annual


def decision(rule, *, values=None, annual=None, market=None,
             applicability="applicable"):
    from ashare_pipeline.formal_policy_evaluator import evaluate_rule

    return evaluate_rule(
        rule,
        security_id="SH600000",
        applicability=applicability,
        values={} if values is None else values,
        annual={} if annual is None else annual,
        market=market,
    )


class QuantileTests(unittest.TestCase):
    def test_two_explicit_quantiles_do_not_share_a_default(self):
        from ashare_pipeline.formal_policy_evaluator import quantile80

        values = tuple(Decimal(i) for i in range(1, 6))
        with localcontext() as ambient:
            ambient.prec = 1
            self.assertEqual(quantile80(values, "linear_type7_v1"), Decimal("4.2"))
            self.assertEqual(quantile80(values, "nearest_rank_v1"), Decimal("4"))
        with self.assertRaises(ValueError):
            quantile80(values, "default")

    def test_quantile_requires_exactly_five_finite_exact_decimals(self):
        from ashare_pipeline.formal_policy_evaluator import quantile80

        for values in (
            (Decimal("1"),) * 4,
            (Decimal("1"),) * 4 + (Decimal("NaN"),),
            (Decimal("1"),) * 4 + (1,),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                quantile80(values, "linear_type7_v1")


class ScalarRuleTests(unittest.TestCase):
    def test_all_five_numeric_comparators_and_inclusive_gte_boundary(self):
        cases = (
            ("lt", "2", "1", "matched"),
            ("lte", "2", "2", "matched"),
            ("gt", "2", "3", "matched"),
            ("gte", "2", "2", "matched"),
            ("eq", "2", "2", "matched"),
            ("gte", "2", "1.999", "clear"),
        )
        for index, (comparator, threshold, actual, expected) in enumerate(cases):
            wire = numeric_rule()
            wire["parameters"] = {"comparator": comparator, "threshold": threshold}
            rule = parsed_rule(wire, "redline", f"bank_numeric_{index}")
            key = digest(rule["inputs"]["value"])
            with self.subTest(comparator=comparator, actual=actual):
                result = decision(rule, values={
                    key: policy_value(actual, unit="CNY", evidence=HASHES[0])
                })
                self.assertEqual(result["evaluation_state"], expected)
                self.assertEqual(result["operands"]["value"], actual)
                self.assertEqual(result["operands"]["threshold"], threshold)

    def test_boolean_and_enum_match_exact_values(self):
        boolean = parsed_rule(boolean_rule(), "status", "bank_st")
        boolean_key = digest(boolean["inputs"]["value"])
        self.assertEqual(decision(boolean, values={
            boolean_key: policy_value(True, "bool", evidence=HASHES[0])
        })["evaluation_state"], "matched")
        self.assertEqual(decision(boolean, values={
            boolean_key: policy_value(False, "bool", evidence=HASHES[0])
        })["evaluation_state"], "clear")

        enum = parsed_rule(enum_rule(), "status", "bank_delisting")
        enum_key = digest(enum["inputs"]["value"])
        self.assertEqual(decision(enum, values={
            enum_key: policy_value("delisting_arrangement", "enum", evidence=HASHES[0])
        })["evaluation_state"], "matched")
        self.assertEqual(decision(enum, values={
            enum_key: policy_value("Delisting_arrangement", "enum", evidence=HASHES[0])
        })["evaluation_state"], "clear")

    def test_noncyclic_rule_does_not_require_annual_values(self):
        rule = parsed_rule(numeric_rule(), "redline", "bank_equity")
        key = digest(rule["inputs"]["value"])
        result = decision(rule, values={
            key: policy_value("-1", unit="CNY", evidence=HASHES[0])
        }, annual={})
        self.assertEqual(result["evaluation_state"], "matched")
        self.assertEqual(result["pending_requirements"], [])

    def test_unresolved_applicability_is_pending_before_inputs_are_read(self):
        rule = parsed_rule(cyclic_rule(), "cyclic", "bank_cyclic_top")
        result = decision(rule, applicability="unresolved")
        self.assertEqual(result["evaluation_state"], "pending_evidence")
        self.assertEqual(
            [item["code"] for item in result["pending_requirements"]],
            ["applicability_unresolved"],
        )
        self.assertEqual(result["proven_effects"], [])


class CyclicRuleTests(unittest.TestCase):
    def test_both_metrics_are_required_and_each_boundary_is_inclusive(self):
        rule = parsed_rule(cyclic_rule(), "cyclic", "bank_cyclic_top")
        values, annual = cyclic_inputs(rule, roe="4.2", margin="4.2")
        self.assertEqual(decision(rule, values=values, annual=annual)["evaluation_state"],
                         "matched")
        values, annual = cyclic_inputs(rule, roe="4.2", margin="4.19")
        result = decision(rule, values=values, annual=annual)
        self.assertEqual(result["evaluation_state"], "clear")
        self.assertEqual(result["proven_effects"], [])

    def test_five_profit_median_uses_sorted_third_and_minimum_with_zero_and_negative(self):
        rule = parsed_rule(cyclic_rule(), "cyclic", "bank_cyclic_top")
        values, annual = cyclic_inputs(rule, profit="7",
            annual_profit=("2", "-2", "1", "0", "-1"))
        basis = decision(rule, values=values, annual=annual)["operands"]["normalization_basis"]
        self.assertEqual(basis["original_current_profit"]["value"], "7")
        self.assertEqual([item["value"] for item in basis["annual_profit"]],
                         ["2", "-2", "1", "0", "-1"])
        self.assertEqual(basis["ordered_values"], ["-2", "-1", "0", "1", "2"])
        self.assertEqual(basis["median"], "0")
        self.assertEqual(basis["normalized_profit"], "0")
        self.assertEqual(basis["valuation_dependencies"],
                         rule["parameters"]["valuation_dependencies"])
        self.assertTrue(all(item["evidence_hashes"] for item in basis["annual_profit"]))

        values, annual = cyclic_inputs(rule, profit="-9",
            annual_profit=("-5", "-1", "0", "4", "8"))
        basis = decision(rule, values=values, annual=annual)["operands"]["normalization_basis"]
        self.assertEqual(basis["median"], "0")
        self.assertEqual(basis["normalized_profit"], "-9")

    def test_a_proven_clear_does_not_erase_authenticated_pending_input(self):
        rule = parsed_rule(cyclic_rule(), "cyclic", "bank_cyclic_top")
        values, annual = cyclic_inputs(
            rule, roe="0", margin="9", missing_margin_index=2
        )
        result = decision(rule, values=values, annual=annual)
        self.assertEqual(result["evaluation_state"], "clear")
        self.assertEqual(result["proven_effects"], [])
        self.assertIn("financial_input_missing",
                      {item["code"] for item in result["pending_requirements"]})

    def test_missing_annual_selector_key_is_explicit_pending_evidence(self):
        rule = parsed_rule(cyclic_rule(), "cyclic", "bank_cyclic_top")
        values, annual = cyclic_inputs(rule)
        del annual[digest(rule["inputs"]["annual_roe"])]
        result = decision(rule, values=values, annual=annual)
        self.assertEqual(result["evaluation_state"], "pending_evidence")
        self.assertIn("financial_input_missing",
                      {item["code"] for item in result["pending_requirements"]})
        self.assertEqual(result["proven_effects"], [])


class MarketRuleTests(unittest.TestCase):
    @staticmethod
    def days(count):
        end = date(2026, 8, 31)
        return tuple((end - timedelta(days=count - 1 - index)).isoformat()
                     for index in range(count))

    def test_tail_veto_with_incomplete_price_releases_only_its_pool_effect(self):
        wire = market_rule()
        wire["outcomes"]["on_match"].extend((
            {"kind": "dimension_cap", "dimension": "T", "maximum": "40"},
            {"kind": "independent_status", "status_code": "no_effective_trade_20d"},
        ))
        wire["outcomes"]["on_match"].sort(key=canonical)
        rule = parsed_rule(wire, "status", "bank_market")
        days = self.days(250)
        rows = {day: {"coverage": "covered", "exchange_allows_trading": True,
                      "volume": "0", "turnover": "0",
                      "close": {"state": "unavailable",
                                "reason": "source_reports_no_trade"}}
                for day in days}
        del rows[days[0]]
        market = evaluate_window(days, rows)
        result = decision(rule, market=market)
        self.assertEqual(market["veto_state"], "proven")
        self.assertEqual(market["price_state"], "incomplete")
        self.assertEqual(result["evaluation_state"], "pending_evidence")
        self.assertEqual([item["kind"] for item in result["proven_effects"]],
                         ["pool_prohibition"])
        self.assertIn("market_coverage_missing",
                      {item["code"] for item in result["pending_requirements"]})

    def test_confirmed_no_price_retains_pending_and_both_pool_prohibitions(self):
        rule = parsed_rule(market_rule(), "status", "bank_market")
        days = self.days(250)
        rows = {day: {"coverage": "covered", "exchange_allows_trading": True,
                      "volume": "0", "turnover": "0",
                      "close": {"state": "unavailable",
                                "reason": "source_reports_no_trade"}}
                for day in days}
        market = evaluate_window(days, rows)
        result = decision(rule, market=market)
        self.assertEqual(result["evaluation_state"], "matched")
        self.assertEqual([item["code"] for item in result["pending_requirements"]],
                         ["market_evidence_missing"])

        from ashare_pipeline.formal_policy_evaluator import aggregate_decisions

        aggregate = aggregate_decisions((result,))
        self.assertEqual(set(aggregate["pool_prohibitions"]), {"strong", "wait"})
        self.assertEqual(len(aggregate["pool_prohibitions"]["strong"]), 1)
        self.assertEqual(len(aggregate["pool_prohibitions"]["wait"]), 1)
        self.assertEqual(aggregate["evidence_state"], "pending_evidence")


class MarketRuleValidationTests(unittest.TestCase):
    def setUp(self):
        self.rule = parsed_rule(market_rule(), "status", "bank_market")

    @staticmethod
    def market(**changes):
        result = {
            "price_state": "incomplete",
            "price": None,
            "price_date": None,
            "stale_days": None,
            "stale_at_least": None,
            "veto_state": "proven",
            "pending": ["market_coverage_missing"],
            "window_hash": HASHES[5],
        }
        result.update(changes)
        return result

    def test_unknown_price_state_cannot_release_signed_effects(self):
        malformed = self.market(price_state="unknown", pending=[])
        with self.assertRaises(ValueError):
            decision(self.rule, market=malformed)

    def test_confirmed_no_price_cannot_erase_market_evidence_missing(self):
        malformed = self.market(
            price_state="confirmed_no_price_250",
            stale_at_least=250,
            pending=[],
        )
        with self.assertRaises(ValueError):
            decision(self.rule, market=malformed)

    def test_incomplete_proven_veto_requires_an_explicit_pending_reason(self):
        malformed = self.market(pending=[])
        with self.assertRaises(ValueError):
            decision(self.rule, market=malformed)

    def test_invented_runtime_market_pending_code_is_rejected(self):
        malformed = self.market(pending=["invented_reason"])
        with self.assertRaises(ValueError):
            decision(self.rule, market=malformed)


class AggregationTests(unittest.TestCase):
    def test_caps_take_minimum_pool_union_and_every_effect_trace_is_preserved(self):
        wire = cyclic_rule()
        wire["outcomes"]["on_match"].extend((
            {"kind": "dimension_cap", "dimension": "G", "maximum": "70"},
            {"kind": "pool_prohibition", "pool": "strong"},
        ))
        wire["outcomes"]["on_match"].sort(key=canonical)
        rule = parsed_rule(wire, "cyclic", "bank_cyclic_top")
        values, annual = cyclic_inputs(rule)
        cyclic = decision(rule, values=values, annual=annual)

        veto = parsed_rule(numeric_rule(), "redline", "bank_equity")
        veto_key = digest(veto["inputs"]["value"])
        redline = decision(veto, values={
            veto_key: policy_value("-1", unit="CNY", evidence=HASHES[0])
        })

        from ashare_pipeline.formal_policy_evaluator import aggregate_decisions

        result = aggregate_decisions((redline, cyclic))
        self.assertEqual(result["dimension_caps"], {"G": "70", "M": "80"})
        self.assertEqual(set(result["pool_prohibitions"]), {"strong", "wait"})
        self.assertEqual(len(result["pool_prohibitions"]["strong"]), 2)
        self.assertEqual(len(result["pool_prohibitions"]["wait"]), 2)
        traces = [reason["trace"] for reasons in result["pool_prohibitions"].values()
                  for reason in reasons]
        self.assertEqual(len(traces), 4)
        self.assertTrue(all(trace["definition_hash"] and trace["evidence_hashes"]
                            for trace in traces))
        self.assertEqual(set(result["states"]), {"cyclic_top"})
        self.assertEqual(len(result["normalization_basis"]), 1)
        self.assertNotIn("eligible", result)
        self.assertNotIn("ready", result)
        self.assertNotIn("final_scores", result)
        self.assertTrue(canonical_bytes(result))

    def test_matched_rule_can_itself_carry_a_signed_pending_requirement(self):
        wire = numeric_rule()
        wire["outcomes"]["on_match"].append(
            {"kind": "pending_evidence", "reason_code": "equity-source-missing"}
        )
        wire["outcomes"]["on_match"].sort(key=canonical)
        rule = parsed_rule(wire, "redline", "bank_equity")
        key = digest(rule["inputs"]["value"])
        matched = decision(rule, values={
            key: policy_value("-1", unit="CNY", evidence=HASHES[0])
        })
        self.assertEqual(matched["evaluation_state"], "matched")
        self.assertEqual([item["kind"] for item in matched["proven_effects"]],
                         ["pool_prohibition"])
        self.assertEqual(matched["pending_requirements"][0]["origin"], "signed_policy")
        self.assertEqual(matched["pending_requirements"][0]["code"],
                         "equity-source-missing")

        from ashare_pipeline.formal_policy_evaluator import aggregate_decisions

        aggregate = aggregate_decisions((matched,))
        self.assertEqual(aggregate["evidence_state"], "pending_evidence")
        self.assertEqual(len(aggregate["pending_requirements"]), 1)


if __name__ == "__main__":
    unittest.main()
