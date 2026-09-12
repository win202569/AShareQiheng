"""Pure syntax tests for detached formal policy declarations."""

import json
import unittest

from ashare_pipeline.formal_policy_contract import (
    PolicyContractError,
    iter_rule_selectors,
    parse_policy_contract,
    parse_policy_rule,
)
from tests.formal_policy_fixtures import (
    FY_ENDS,
    boolean_rule,
    canonical,
    context_selector,
    cyclic_rule,
    enum_rule,
    market_rule,
    numeric_rule,
    policy_children,
)


class PolicySyntaxTests(unittest.TestCase):
    def test_numeric_rule_is_detached_and_deeply_immutable(self):
        wire = numeric_rule()
        rule = parse_policy_rule("redline", "bank_equity", canonical(wire))
        self.assertEqual(rule.semantic_id, "nonpositive_equity")
        with self.assertRaises(TypeError):
            rule.inputs["value"]["period_keys"][0] = "FY1"
        self.assertFalse(hasattr(rule, "require_verified"))
        self.assertFalse(hasattr(rule, "pool_eligible"))


class PolicySelectorSyntaxTests(unittest.TestCase):
    def assert_rule_rejected(self, wire, *, role="redline", rule_id="fixture"):
        with self.assertRaises(PolicyContractError):
            parse_policy_rule(role, rule_id, canonical(wire))

    def test_feature_selector_requires_exact_sorted_nonempty_periods(self):
        mutations = (
            lambda selector: selector.update(extra=True),
            lambda selector: selector.update(period_keys=[]),
            lambda selector: selector.update(period_keys=["FY1", "FY0"]),
            lambda selector: selector.update(period_keys=["FY0", "FY0"]),
            lambda selector: selector.update(period_keys=[True]),
            lambda selector: selector.update(template_id="broker"),
        )
        for mutate in mutations:
            wire = numeric_rule()
            mutate(wire["inputs"]["value"])
            with self.subTest(selector=wire["inputs"]["value"]):
                self.assert_rule_rejected(wire)

    def test_annual_series_requires_the_exact_five_ordered_fiscal_years(self):
        for change in ("missing", "duplicate", "unordered"):
            wire = cyclic_rule()
            series = wire["inputs"]["annual_roe"]
            if change == "missing":
                series["observations"].pop()
            elif change == "duplicate":
                series["observations"][-1]["fy_end"] = FY_ENDS[-2]
            else:
                series["observations"][0], series["observations"][1] = (
                    series["observations"][1],
                    series["observations"][0],
                )
            with self.subTest(change=change):
                self.assert_rule_rejected(wire, role="cyclic")

    def test_context_selector_enforces_the_finite_field_type_unit_matrix(self):
        valid = (
            context_selector(),
            context_selector(field="listing_status", expected_type="enum"),
            context_selector("regulatory_state", "active", "bool", entry_id="audit-qualified"),
            context_selector("market_close", "record", "market_record"),
            context_selector("trading_calendar", "record", "calendar_record"),
        )
        for selector in valid:
            wire = boolean_rule()
            wire["inputs"]["value"] = selector
            if selector["expected_type"] != "bool":
                wire["kind"] = "enum_state"
                wire["parameters"] = {"values": ["listed"]}
            if selector["expected_type"] in ("event_record", "market_record", "calendar_record"):
                wire["kind"] = "market_liquidity"
                wire["inputs"] = {
                    "market": context_selector("market_close", "record", "market_record"),
                    "calendar": context_selector("trading_calendar", "record", "calendar_record"),
                }
                wire["parameters"] = {
                    "effective_trade_method": "exchange_allows_and_positive_volume_turnover_v1",
                    "veto_trading_days": 20,
                    "close_search_trading_days": 250,
                    "required_evidence_capability": "verified_market_window_v1",
                }
            role = "status"
            with self.subTest(selector=selector):
                parse_policy_rule(role, "context", canonical(wire))

        invalid = (
            context_selector(field="unknown"),
            context_selector(field="listing_status", expected_type="bool"),
            context_selector("regulatory_state", "active", "bool"),
            context_selector("market_close", "record", "market_record", entry_id="forbidden"),
            context_selector(
                "event_calendar", "event", "event_record", entry_id="event", expected_unit=None
            ),
        )
        for selector in invalid:
            wire = boolean_rule()
            wire["inputs"]["value"] = selector
            with self.subTest(selector=selector):
                self.assert_rule_rejected(wire, role="status")

    def test_unknown_selector_kind_reports_the_input_path(self):
        wire = numeric_rule()
        wire["inputs"]["value"]["kind"] = "jsonpath"
        with self.assertRaises(PolicyContractError) as caught:
            parse_policy_rule("redline", "bank_equity", canonical(wire))
        self.assertEqual(caught.exception.code, "unsupported_contract")
        self.assertEqual(caught.exception.path, "redline.rules.bank_equity.inputs.value.kind")

    def test_malformed_context_discriminators_raise_contract_errors(self):
        for field, value in (("context_kind", []), ("field", [])):
            wire = boolean_rule()
            wire["inputs"]["value"][field] = value
            with self.subTest(field=field), self.assertRaises(PolicyContractError):
                parse_policy_rule("status", "malformed_context", canonical(wire))

    def test_iter_rule_selectors_keeps_annual_series_grouped(self):
        wire = numeric_rule()
        rule = parse_policy_rule("redline", "bank_equity", canonical(wire))
        selectors = iter_rule_selectors(rule)
        self.assertEqual(len(selectors), 1)
        self.assertEqual(selectors[0]["kind"], "feature")

    def test_noncanonical_duplicate_non_utf8_and_mutable_raw_are_rejected(self):
        valid = canonical(numeric_rule())
        cases = (
            b" " + valid,
            b'{"schema_version":"formal-policy-rule-v1","schema_version":"formal-policy-rule-v1"}',
            b"\xff",
            bytearray(valid),
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(PolicyContractError):
                parse_policy_rule("redline", "bank_equity", raw)


class PolicyRuleFamilyTests(unittest.TestCase):
    def assert_rejected(self, role, wire, *, rule_id="fixture"):
        with self.assertRaises(PolicyContractError):
            parse_policy_rule(role, rule_id, canonical(wire))

    def test_unknown_keys_nondecimal_thresholds_and_pending_dispositions_are_rejected(self):
        mutations = (
            lambda wire: wire.update(extra=True),
            lambda wire: wire["parameters"].update(threshold=True),
            lambda wire: wire["parameters"].update(threshold="NaN"),
            lambda wire: wire["outcomes"].update(on_missing="clear"),
        )
        for mutate in mutations:
            wire = numeric_rule()
            mutate(wire)
            with self.subTest(wire=wire):
                self.assert_rejected("redline", wire)

    def test_numeric_comparator_and_signed_decimal_string_boundaries(self):
        for comparator in ("lt", "lte", "gt", "gte", "eq"):
            for threshold in ("-1", "-0.5", "0", "0.0", "1", "1.25"):
                wire = numeric_rule()
                wire["parameters"] = {
                    "comparator": comparator,
                    "threshold": threshold,
                }
                with self.subTest(comparator=comparator, threshold=threshold):
                    parse_policy_rule("redline", "numeric", canonical(wire))

        for comparator, threshold in (
            ("ne", "0"),
            ("lte", "+1"),
            ("lte", "01"),
            ("lte", "-.5"),
            ("lte", ".5"),
            ("lte", "1."),
            ("lte", "Infinity"),
        ):
            wire = numeric_rule()
            wire["parameters"] = {"comparator": comparator, "threshold": threshold}
            with self.subTest(comparator=comparator, threshold=threshold):
                self.assert_rejected("redline", wire)

    def test_boolean_and_enum_parameters_have_exact_types_and_values(self):
        for value in (1, "true", None):
            wire = boolean_rule()
            wire["parameters"]["expected"] = value
            with self.subTest(expected=value):
                self.assert_rejected("status", wire)

        for values in (
            [],
            ["suspended"],
            ["listed", "delisted"],
            ["listed", "listed"],
        ):
            wire = enum_rule()
            wire["parameters"]["values"] = values
            with self.subTest(values=values):
                self.assert_rejected("status", wire)

    def test_both_explicit_quantile_algorithms_are_supported_without_a_default(self):
        for method in ("linear_type7_v1", "nearest_rank_v1"):
            with self.subTest(method=method):
                parse_policy_rule("cyclic", "cyclic_top", canonical(cyclic_rule(quantile_method=method)))

        wire = cyclic_rule()
        del wire["parameters"]["quantile_method"]
        self.assert_rejected("cyclic", wire)
        wire = cyclic_rule(quantile_method="implicit_default")
        with self.assertRaises(PolicyContractError) as caught:
            parse_policy_rule("cyclic", "cyclic_top", canonical(wire))
        self.assertEqual(caught.exception.code, "unsupported_contract")

    def test_cyclic_fixed_parameters_and_valuation_dependencies_are_enforced(self):
        mutations = (
            (lambda wire: wire["parameters"].update(fy_ends=FY_ENDS[:-1]), "malformed_contract"),
            (lambda wire: wire["parameters"].update(quantile_level="0.8"), "malformed_contract"),
            (lambda wire: wire["parameters"].update(median_method="average_middle_v1"), "unsupported_contract"),
            (lambda wire: wire["parameters"].update(profit_basis_method="current_only_v1"), "unsupported_contract"),
            (lambda wire: wire["parameters"]["valuation_dependencies"].reverse(), "malformed_contract"),
            (lambda wire: wire["parameters"]["valuation_dependencies"][0].update(
                metric_id="G.enterprise_value"
            ), "malformed_contract"),
            (lambda wire: wire["parameters"]["valuation_dependencies"][0].update(
                adapter_id="forbidden"
            ), "malformed_contract"),
            (lambda wire: wire["parameters"]["valuation_dependencies"][1].update(
                profit_semantic_id="other"
            ), "malformed_contract"),
        )
        for mutate, expected_code in mutations:
            wire = cyclic_rule()
            mutate(wire)
            with self.subTest(parameters=wire["parameters"]), self.assertRaises(
                PolicyContractError
            ) as caught:
                parse_policy_rule("cyclic", "fixture", canonical(wire))
            self.assertEqual(caught.exception.code, expected_code)

    def test_cyclic_requires_exact_g_and_m_caps_profit_basis_status_and_pool_effects(self):
        def effect(wire, kind, **fields):
            return next(
                item
                for item in wire["outcomes"]["on_match"]
                if item["kind"] == kind and all(item.get(key) == value for key, value in fields.items())
            )

        mutations = (
            lambda wire: effect(wire, "dimension_cap", dimension="G").update(maximum="81"),
            lambda wire: wire["outcomes"]["on_match"].remove(
                effect(wire, "dimension_cap", dimension="M")
            ),
            lambda wire: effect(wire, "valuation_profit_basis").update(
                profit_semantic_id="other"
            ),
            lambda wire: effect(wire, "independent_status").update(status_code="other"),
            lambda wire: wire["outcomes"]["on_match"].remove(
                effect(wire, "pool_prohibition")
            ),
        )
        for mutate in mutations:
            wire = cyclic_rule()
            mutate(wire)
            wire["outcomes"]["on_match"].sort(key=canonical)
            with self.subTest(outcomes=wire["outcomes"]):
                self.assert_rejected("cyclic", wire)

    def test_effects_reject_caps_outside_dimensions_and_any_score_or_rank_override(self):
        invalid_effects = (
            {"kind": "dimension_cap", "dimension": "total", "maximum": "80"},
            {"kind": "dimension_cap", "dimension": "G", "maximum": "101"},
            {"kind": "dimension_cap", "dimension": "G", "maximum": "-1"},
            {
                "kind": "valuation_profit_basis",
                "profit_semantic_id": "nonpositive_equity",
            },
            {"kind": "score_override", "score": "80"},
            {"kind": "rank_override", "rank": 1},
        )
        for candidate in invalid_effects:
            wire = numeric_rule()
            wire["outcomes"]["on_match"] = [candidate]
            with self.subTest(candidate=candidate):
                self.assert_rejected("redline", wire)

    def test_effects_are_canonical_sorted_unique_and_exact(self):
        pending = {"kind": "pending_evidence", "reason_code": "fixture-evidence"}
        prohibition = {"kind": "pool_prohibition", "pool": "both"}
        cases = (
            [prohibition, pending],
            [prohibition, prohibition],
            [{"kind": "pool_prohibition", "pool": "both", "extra": True}],
            [{"kind": "independent_status", "status_code": ""}],
            [{"kind": "pending_evidence", "reason_code": "bad code"}],
        )
        for effects in cases:
            wire = numeric_rule()
            wire["outcomes"]["on_match"] = effects
            with self.subTest(effects=effects):
                self.assert_rejected("redline", wire)

    def test_pending_evidence_effect_does_not_mint_a_required_veto_in_a1(self):
        wire = numeric_rule()
        wire["outcomes"]["on_match"] = [
            {"kind": "pending_evidence", "reason_code": "equity-source-missing"}
        ]
        rule = parse_policy_rule("redline", "nonpositive_equity", canonical(wire))
        self.assertEqual(rule.outcomes["on_match"][0]["kind"], "pending_evidence")

    def test_market_liquidity_constants_and_both_pool_veto_are_fixed(self):
        mutations = (
            (lambda wire: wire["parameters"].update(veto_trading_days=19), "malformed_contract"),
            (lambda wire: wire["parameters"].update(veto_trading_days=True), "malformed_contract"),
            (lambda wire: wire["parameters"].update(close_search_trading_days=249), "malformed_contract"),
            (lambda wire: wire["parameters"].update(effective_trade_method="weekdays_v1"), "unsupported_contract"),
            (lambda wire: wire["parameters"].update(required_evidence_capability="market_record_v1"), "malformed_contract"),
            (lambda wire: wire["outcomes"]["on_match"][0].update(pool="strong"), "malformed_contract"),
        )
        for mutate, expected_code in mutations:
            wire = market_rule()
            mutate(wire)
            with self.subTest(wire=wire), self.assertRaises(PolicyContractError) as caught:
                parse_policy_rule("status", "fixture", canonical(wire))
            self.assertEqual(caught.exception.code, expected_code)

    def test_rule_kind_role_template_and_schema_are_closed(self):
        cases = (
            ("event", numeric_rule()),
            ("redline", boolean_rule()),
            ("status", cyclic_rule()),
            ("cyclic", market_rule()),
        )
        for role, wire in cases:
            with self.subTest(role=role, kind=wire["kind"]):
                self.assert_rejected(role, wire)

        wire = numeric_rule()
        wire["template_id"] = "commodities"
        self.assert_rejected("redline", wire)
        wire = numeric_rule()
        wire["schema_version"] = "formal-policy-rule-v2"
        with self.assertRaises(PolicyContractError) as caught:
            parse_policy_rule("redline", "fixture", canonical(wire))
        self.assertEqual(caught.exception.code, "unsupported_contract")
        wire = numeric_rule()
        wire["kind"] = []
        self.assert_rejected("redline", wire)

    def test_empty_event_entry_and_illegal_listing_enum_are_rejected(self):
        wire = boolean_rule()
        wire["inputs"]["value"] = context_selector(
            "regulatory_state", "active", "bool", entry_id=""
        )
        self.assert_rejected("event", wire)

        wire = enum_rule()
        wire["parameters"]["values"] = ["suspended"]
        self.assert_rejected("status", wire)


class PolicyEntryPointTests(unittest.TestCase):
    def mutate_wrapper(self, children, role, mutate):
        wrapper = json.loads(children[role])
        mutate(wrapper)
        children[role] = canonical(wrapper)

    def assert_contract_rejected(self, children):
        with self.assertRaises(PolicyContractError):
            parse_policy_contract(children)

    def test_four_role_contract_is_deterministic_detached_and_deeply_immutable(self):
        children = policy_children()
        parsed = parse_policy_contract(children)
        self.assertEqual(
            tuple((rule.role, rule.rule_id) for rule in parsed.rules),
            (
                ("cyclic", "bank_cyclic"),
                ("event", "bank_st"),
                ("redline", "bank_equity"),
                ("status", "bank_market"),
            ),
        )
        self.assertEqual(parsed.role_versions["cyclic"], "fixture-cyclic-v1")
        self.assertEqual(parsed.evidence_categories["status"], ("fixture-status",))
        expected_children = {
            role: json.loads(raw.decode("utf-8")) for role, raw in children.items()
        }
        self.assertEqual(
            parsed.canonical_json,
            canonical(
                {
                    "schema_version": "formal-policy-parsed-v1",
                    "children": expected_children,
                }
            ),
        )
        with self.assertRaises(TypeError):
            parsed.role_versions["cyclic"] = "other"
        with self.assertRaises(TypeError):
            parsed.rules[0].outcomes["on_match"][0]["kind"] = "other"
        self.assertFalse(hasattr(parsed, "require_verified"))
        self.assertFalse(hasattr(parsed, "policy_ready"))

    def test_children_and_wrappers_have_exact_closed_fields_and_versions(self):
        cases = []
        children = policy_children()
        del children["event"]
        cases.append(children)
        children = policy_children()
        children["other"] = children["event"]
        cases.append(children)
        children = policy_children()
        self.mutate_wrapper(children, "redline", lambda wrapper: wrapper.update(extra=True))
        cases.append(children)
        children = policy_children()
        self.mutate_wrapper(
            children,
            "redline",
            lambda wrapper: wrapper.update(schema_version="formal-scoring-policy-v2"),
        )
        cases.append(children)
        children = policy_children()
        self.mutate_wrapper(children, "redline", lambda wrapper: wrapper.update(purpose=" "))
        cases.append(children)
        for children in cases:
            with self.subTest(children=children):
                self.assert_contract_rejected(children)

    def test_all_four_wrapper_purposes_must_agree_without_granting_official_status(self):
        children = policy_children()
        self.mutate_wrapper(
            children, "event", lambda wrapper: wrapper.update(purpose="test")
        )
        self.assert_contract_rejected(children)

    def test_every_execution_entry_is_present_exact_nonempty_and_role_bound(self):
        mutations = (
            lambda rules: rules.pop("execution_contract"),
            lambda rules: rules["execution_contract"].update(extra=True),
            lambda rules: rules["execution_contract"].update(rule_ids=[]),
            lambda rules: rules["execution_contract"].update(role="event"),
            lambda rules: rules["execution_contract"].update(
                schema_version="formal-policy-execution-contract-v2"
            ),
        )
        for mutate in mutations:
            children = policy_children()
            self.mutate_wrapper(children, "redline", lambda wrapper: mutate(wrapper["rules"]))
            with self.subTest(children=children):
                self.assert_contract_rejected(children)

    def test_active_ids_reject_duplicates_disorder_self_reference_dangling_and_cross_role(self):
        active_lists = (
            ["bank_equity", "bank_equity"],
            ["z_rule", "bank_equity"],
            ["execution_contract"],
            ["missing"],
            ["bank_market"],
        )
        for active_ids in active_lists:
            children = policy_children()

            def change(wrapper):
                if "z_rule" in active_ids:
                    extra = numeric_rule()
                    extra["semantic_id"] = "additional_redline"
                    wrapper["rules"]["z_rule"] = extra
                wrapper["rules"]["execution_contract"]["rule_ids"] = active_ids

            self.mutate_wrapper(children, "redline", change)
            with self.subTest(active_ids=active_ids):
                self.assert_contract_rejected(children)

    def test_active_semantic_ids_are_unique_per_template_across_roles(self):
        children = policy_children()

        def duplicate(wrapper):
            wrapper["rules"]["bank_st"]["semantic_id"] = "nonpositive_equity"

        self.mutate_wrapper(children, "event", duplicate)
        self.assert_contract_rejected(children)

    def test_inactive_legacy_rule_is_not_parsed_but_remains_in_content_identity(self):
        baseline = parse_policy_contract(policy_children())
        children = policy_children()

        def add_legacy(wrapper):
            wrapper["rules"]["legacy_rule"] = {
                "schema_version": "legacy-policy-v0",
                "opaque": ["preserved", 1, 1e-6],
            }

        self.mutate_wrapper(children, "redline", add_legacy)
        changed = parse_policy_contract(children)
        self.assertEqual(
            tuple((rule.role, rule.rule_id) for rule in changed.rules),
            tuple((rule.role, rule.rule_id) for rule in baseline.rules),
        )
        self.assertNotEqual(changed.canonical_json, baseline.canonical_json)
        self.assertIn(b"1e-06", changed.canonical_json)

    def test_children_must_be_exact_bytes_and_child_json_must_be_canonical(self):
        children = policy_children()
        children["event"] = bytearray(children["event"])
        self.assert_contract_rejected(children)
        children = policy_children()
        children["event"] = b" " + children["event"]
        self.assert_contract_rejected(children)


if __name__ == "__main__":
    unittest.main()
