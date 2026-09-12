"""Synthetic policy rule declarations for pure grammar tests."""

from tests.test_formal_scoring_registry import canonical


FY_ENDS = [f"{year}-12-31" for year in range(2021, 2026)]


def feature_selector(template_id, name, period_key, unit):
    return dict(
        kind="feature",
        template_id=template_id,
        feature_key=f"{template_id}.policy.{name}",
        expected_unit=unit,
        formula_version="fixture-policy-v1",
        period_keys=[period_key],
    )


def numeric_rule(template_id="bank"):
    return dict(
        schema_version="formal-policy-rule-v1",
        kind="numeric_redline",
        semantic_id="nonpositive_equity",
        template_id=template_id,
        inputs={
            "value": feature_selector(template_id, "equity", "FY0", "CNY")
        },
        parameters={"comparator": "lte", "threshold": "0"},
        outcomes={
            "on_match": [{"kind": "pool_prohibition", "pool": "both"}],
            "on_clear": [],
            "on_missing": "pending_evidence",
            "on_conflict": "pending_evidence",
        },
    )


def annual_selector(template_id, name, unit="ratio"):
    return {
        "kind": "annual_series",
        "observations": [
            {
                "fy_end": fy_end,
                "selector": feature_selector(
                    template_id, f"{name}_{fy_end[:4]}", f"FY{fy_end[:4]}", unit
                ),
            }
            for fy_end in FY_ENDS
        ],
    }


def context_selector(
    context_kind="security_state",
    field="is_st",
    expected_type="bool",
    *,
    entry_id=None,
    expected_unit=None,
):
    return {
        "kind": "context",
        "descriptor_id": "a" * 64,
        "context_kind": context_kind,
        "scope_key": "fixture-security",
        "field": field,
        "entry_id": entry_id,
        "expected_type": expected_type,
        "expected_unit": expected_unit,
    }


def boolean_rule(template_id="bank", *, role="status"):
    del role
    return {
        "schema_version": "formal-policy-rule-v1",
        "kind": "boolean_state",
        "semantic_id": "st",
        "template_id": template_id,
        "inputs": {"value": context_selector()},
        "parameters": {"expected": True},
        "outcomes": {
            "on_match": [{"kind": "pool_prohibition", "pool": "both"}],
            "on_clear": [],
            "on_missing": "pending_evidence",
            "on_conflict": "pending_evidence",
        },
    }


def enum_rule(template_id="bank"):
    wire = boolean_rule(template_id)
    wire.update(kind="enum_state", semantic_id="delisting_arrangement")
    wire["inputs"] = {
        "value": context_selector(field="listing_status", expected_type="enum")
    }
    wire["parameters"] = {"values": ["delisting_arrangement"]}
    return wire


def cyclic_rule(template_id="bank", *, quantile_method="linear_type7_v1"):
    outcomes = [
        {"kind": "dimension_cap", "dimension": "G", "maximum": "80"},
        {"kind": "dimension_cap", "dimension": "M", "maximum": "80"},
        {"kind": "valuation_profit_basis", "profit_semantic_id": "cyclic_top"},
        {"kind": "independent_status", "status_code": "cyclic_top"},
        {"kind": "pool_prohibition", "pool": "wait"},
    ]
    return {
        "schema_version": "formal-policy-rule-v1",
        "kind": "cyclic_protection",
        "semantic_id": "cyclic_top",
        "template_id": template_id,
        "inputs": {
            "current_roe": feature_selector(template_id, "roe", "FY0", "ratio"),
            "current_margin": feature_selector(template_id, "margin", "FY0", "ratio"),
            "current_profit": feature_selector(template_id, "profit", "FY0", "CNY"),
            "annual_roe": annual_selector(template_id, "roe"),
            "annual_margin": annual_selector(template_id, "margin"),
            "annual_profit": annual_selector(template_id, "profit", "CNY"),
        },
        "parameters": {
            "fy_ends": list(FY_ENDS),
            "quantile_method": quantile_method,
            "quantile_level": "0.80",
            "median_method": "ordered_middle_v1",
            "profit_basis_method": "minimum_current_and_five_fy_median_v1",
            "valuation_dependencies": [
                {
                    "metric_id": "V.enterprise_value",
                    "policy_dependency": "unaffected",
                    "profit_semantic_id": None,
                    "adapter_id": None,
                    "adapter_version": None,
                    "definition_basis": "fixture enterprise-value definition",
                },
                {
                    "metric_id": "V.normalized_earnings_yield",
                    "policy_dependency": "affected",
                    "profit_semantic_id": "cyclic_top",
                    "adapter_id": "fixture-normalized-profit",
                    "adapter_version": "fixture-adapter-v1",
                    "definition_basis": "fixture normalized-profit definition",
                },
            ],
        },
        "outcomes": {
            "on_match": sorted(outcomes, key=canonical),
            "on_clear": [],
            "on_missing": "pending_evidence",
            "on_conflict": "pending_evidence",
        },
    }


def market_rule(template_id="bank"):
    return {
        "schema_version": "formal-policy-rule-v1",
        "kind": "market_liquidity",
        "semantic_id": "no_effective_trade_20d",
        "template_id": template_id,
        "inputs": {
            "market": context_selector("market_close", "record", "market_record"),
            "calendar": context_selector(
                "trading_calendar", "record", "calendar_record"
            ),
        },
        "parameters": {
            "effective_trade_method": "exchange_allows_and_positive_volume_turnover_v1",
            "veto_trading_days": 20,
            "close_search_trading_days": 250,
            "required_evidence_capability": "verified_market_window_v1",
        },
        "outcomes": {
            "on_match": [{"kind": "pool_prohibition", "pool": "both"}],
            "on_clear": [],
            "on_missing": "pending_evidence",
            "on_conflict": "pending_evidence",
        },
    }


def policy_wrapper(role, rules, active_ids=None):
    active_ids = sorted(rules) if active_ids is None else active_ids
    all_rules = dict(rules)
    all_rules["execution_contract"] = {
        "schema_version": "formal-policy-execution-contract-v1",
        "role": role,
        "rule_ids": active_ids,
    }
    return {
        "registry_role": role,
        "schema_version": "formal-scoring-policy-v1",
        "purpose": "official",
        "registry_version": f"fixture-{role}-v1",
        "source_evidence_categories": [f"fixture-{role}"],
        "rules": all_rules,
    }


def policy_children():
    wrappers = {
        "cyclic": policy_wrapper("cyclic", {"bank_cyclic": cyclic_rule()}),
        "redline": policy_wrapper("redline", {"bank_equity": numeric_rule()}),
        "status": policy_wrapper("status", {"bank_market": market_rule()}),
        "event": policy_wrapper("event", {"bank_st": boolean_rule()}),
    }
    return {role: canonical(wrapper) for role, wrapper in wrappers.items()}
