"""Synthetic policy declarations and byte-sensitive signed graphs, never production mappings."""

import hashlib

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


REGULATORY_SEMANTICS = (
    "audit_adverse", "audit_disclaimer", "audit_qualified", "crowding",
    "governance_orange", "governance_red", "major_event",
    "major_reduction_window", "major_unlock_window",
)
INDEPENDENT_SEMANTICS = (
    "governance_orange", "crowding", "major_unlock_window",
    "major_reduction_window", "major_event",
)


def rehash_documents(documents):
    feature = documents["feature"]
    for role in ("source", "mapping"):
        feature[f"{role}_registry_hash"] = hashlib.sha256(canonical(documents[role])).hexdigest()
    scoring = documents["scoring"]["scoring"]
    for role in ("cyclic", "redline", "status", "event"):
        child = documents[role]
        scoring["policy_contracts"][role] = dict(
            registry_hash=hashlib.sha256(canonical(child)).hexdigest(),
            registry_version=child["registry_version"],
            source_evidence_categories=child["source_evidence_categories"],
        )


def add_policy_documents(documents):
    """Add static fixture contracts before signing, preserving original declarations."""
    from tests.test_formal_context_repository import descriptor
    from tests.test_formal_sources import config
    from tests.test_formal_scoring_registry import TEMPLATES

    configs = documents["source"]["configs"]
    identities = {(c["source"], c["dataset"], c["exchange_scope"]) for c in configs}
    for exchange in ("SH", "SZ", "BJ"):
        added = config(dataset="fixture-state", exchange_scope=exchange)
        if (added["source"], added["dataset"], exchange) not in identities:
            configs.append(added)
    wrapper = documents["scoring"]
    descriptors = {"security_state": next(d for d in wrapper["descriptors"]
        if d["context_kind"] == "security_state")}
    for kind in ("regulatory_state", "event_calendar", "market_close", "trading_calendar"):
        entry = descriptor(kind, scope_key=f"fixture-policy-{kind}")
        if kind == "regulatory_state":
            entry["allowed_regulatory_flags"] = list(REGULATORY_SEMANTICS)
        if kind == "event_calendar":
            entry["allowed_event_codes"] = ["fixture_quantified_event"]
        wrapper["descriptors"].append(entry)
        descriptors[kind] = entry

    def bind_context(selector):
        entry = descriptors[selector["context_kind"]]
        selector.update(descriptor_id=hashlib.sha256(canonical(entry)).hexdigest(),
            scope_key=entry["scope_key"])

    active = {role: [] for role in ("cyclic", "redline", "status", "event")}
    scoring = wrapper["scoring"]
    for template in TEMPLATES:
        for name, unit, dimension in (("equity", "CNY", "FS"), ("roe", "ratio", "M"),
                ("margin", "ratio", "M"), ("profit", "CNY", "V")):
            for year in ([None] if name == "equity" else [None, *range(2021, 2026)]):
                suffix = name if year is None else f"{name}_{year}"
                documents["feature"]["slots"].append(dict(
                    slot_id=f"{template}.policy.{suffix}", template_id=template,
                    dimension=dimension, required=False, unit=unit,
                    formula_version="fixture-policy-v1",
                    formula=dict(op="fact", fact_key=f"fixture.policy.{name}",
                        period_key="FY0" if year is None else f"FY{year}")))
        rules = [numeric_rule(template), cyclic_rule(template), market_rule(template), enum_rule(template)]
        for semantic, field in (("st", "is_st"), ("star_st", "is_star_st"),
                ("forced_delist_risk", "forced_delist_risk")):
            rule = boolean_rule(template)
            rule["semantic_id"] = semantic
            rule["inputs"]["value"]["field"] = field
            rules.append(rule)
        for semantic in REGULATORY_SEMANTICS:
            rule = boolean_rule(template)
            rule["semantic_id"] = semantic
            rule["inputs"]["value"] = context_selector("regulatory_state", "active", "bool", entry_id=semantic)
            if semantic in INDEPENDENT_SEMANTICS:
                rule["outcomes"]["on_match"] = sorted([
                    dict(kind="independent_status", status_code=semantic),
                    dict(kind="pool_prohibition", pool="strong")], key=canonical)
            rules.append(rule)
        for rule in rules:
            semantic = rule["semantic_id"]
            role = ("cyclic" if semantic == "cyclic_top" else "redline" if semantic == "nonpositive_equity"
                else "event" if semantic == "major_event" else "status")
            if role == "cyclic":
                metric_ids = sorted("V." + m["metric_id"] for m in scoring["templates"][template]["metrics"]["V"])
                rule["parameters"]["valuation_dependencies"] = [dict(
                    metric_id=metric_id, policy_dependency="affected" if index == 0 else "unaffected",
                    profit_semantic_id="cyclic_top" if index == 0 else None,
                    adapter_id="fixture_profit_adapter" if index == 0 else None,
                    adapter_version="fixture-v1" if index == 0 else None,
                    definition_basis="fixture-only declared definition; no economic equivalence asserted")
                    for index, metric_id in enumerate(metric_ids)]
            for selector in rule["inputs"].values():
                if selector["kind"] == "context":
                    bind_context(selector)
            rule_id = f"{template}_{semantic}"
            documents[role]["rules"][rule_id] = rule
            active[role].append(rule_id)
        for metrics in scoring["templates"][template]["metrics"].values():
            for metric in metrics:
                metric["policy_refs"] = [dict(policy_role="redline", rule_id=f"{template}_nonpositive_equity")]
    documents["feature"]["slots"].sort(key=lambda slot: slot["slot_id"])
    for role, ids in active.items():
        documents[role]["rules"]["execution_contract"] = dict(
            schema_version="formal-policy-execution-contract-v1", role=role, rule_ids=sorted(ids))
    scoring["redlines"] = [dict(policy_role="redline", rule_id=key) for key in sorted(active["redline"])]
    scoring["status_rules"] = [dict(policy_role=role, rule_id=key)
        for role in ("status", "event") for key in sorted(active[role])]
    scoring["market_liquidity_rule"] = dict(policy_role="status", rule_id="general_nonfinancial_no_effective_trade_20d")


def policy_graph(*, version="v1", mutate=None):
    from ashare_pipeline.formal_scoring_registry import RegistryApproval, load_formal_registry
    from tests.test_formal_scoring_registry import signed_graph
    from tests.test_formal_scoring_consensus_registry import v2_graph

    if version not in ("v1", "v2"):
        raise ValueError("unknown fixture wrapper version")

    def prepare(documents):
        add_policy_documents(documents)
        if mutate is not None:
            mutate(documents)
        rehash_documents(documents)

    values = (signed_graph(context=True, mutate=prepare) if version == "v1" else v2_graph(mutate=prepare))
    bundle, vocabulary, repository, verifier = values[:4]
    approval = RegistryApproval("official", bundle.manifest.scoring_registry_hash, bundle.manifest.approval_id)
    scoring = load_formal_registry(bundle, approval, feature_registry=vocabulary)
    return bundle, vocabulary, scoring, repository, verifier
