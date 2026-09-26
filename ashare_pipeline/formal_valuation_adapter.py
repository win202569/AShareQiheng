"""Pure, detached valuation adjustment. This module does not mint formal proofs."""

from __future__ import annotations

from decimal import (Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
                     ROUND_HALF_EVEN, localcontext)

from . import formal_policy_values as _policy_values_module
from .formal_policy_values import digest


_METRIC_KEYS = frozenset(("registry_manifest_hash", "frozen_input_hash", "universe_hash",
    "population_hash", "as_of_utc", "industry_batch_hash", "registry_hashes",
    "universe_proof_hash", "security_id", "metric_id", "template_id",
    "primary_industry", "secondary_industry", "definition_hash", "direction",
    "unit", "raw_value", "verified_feature_refs", "invalid_reason", "status",
    "projection_hash", "feature_state_hash", "input_hash"))
_RESULT_KEYS = frozenset(("registry_manifest_hash", "frozen_input_hash", "universe_hash",
    "as_of_utc", "policy_contract_hash", "role_hashes", "security_id", "decisions",
    "dimension_caps", "pool_prohibitions", "states", "normalization_basis",
    "pending_requirements", "evidence_state", "result_hash"))
_DECISION_KEYS = frozenset(("rule_id", "role", "semantic_id", "template_id",
    "security_id", "definition_hash", "input_references", "operands", "parameters",
    "evaluation_state", "proven_effects", "pending_requirements", "trace",
    "decision_hash"))
_DEPENDENCY_KEYS = frozenset(("metric_id", "policy_dependency", "profit_semantic_id",
    "adapter_id", "adapter_version", "definition_basis"))
_ADAPTER_KEYS = frozenset(("template_id", "metric_id", "adapter_id", "adapter_version",
    "operation", "original_definition_hash", "profit_semantic_id", "metric_unit",
    "profit_unit", "output_unit", "policy_role", "rule_id", "decimal_contract",
    "preconditions", "definition_basis"))
_BASIS_KEYS = frozenset(("profit_semantic_id", "original_current_profit", "annual_profit",
    "ordered_values", "median_method", "median", "profit_basis_method",
    "normalized_profit", "valuation_dependencies"))
_PRECONDITIONS = ("exact_units", "finite_decimals", "nonzero_original_current_profit")


def _arithmetic_context():
    return Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999,
                   Emax=999999, capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])


def profit_ratio_rescale(original_metric_value: Decimal,
                         original_current_profit: Decimal,
                         normalized_profit: Decimal) -> Decimal:
    """Scale a signed linear profit metric using exact finite Decimal operands."""
    values = (original_metric_value, original_current_profit, normalized_profit)
    if any(type(value) is not Decimal or not value.is_finite() for value in values):
        raise ValueError("valuation adapter requires finite exact Decimals")
    if original_current_profit == 0:
        raise ValueError("valuation adapter original profit cannot be zero")
    with localcontext(_arithmetic_context()):
        return original_metric_value * normalized_profit / original_current_profit


def _exact(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"{label} has unknown or missing fields")


def _hash(value, field, label):
    actual = value[field]
    if type(actual) is not str or actual != digest({key: item for key, item in value.items()
                                                     if key != field}):
        raise ValueError(f"{label} hash differs from detached content")


def _text(value, label):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be nonempty trimmed text")


def _decimal(value):
    if type(value) is not str:
        return None, "invalid"
    try:
        with localcontext(_arithmetic_context()):
            parsed = Decimal(value)
    except InvalidOperation:
        return None, "invalid"
    return (parsed, None) if parsed.is_finite() else (None, "nonfinite")


def _decimal_text(value):
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("finite Decimal required")
    if value.is_zero():
        return "0"
    fixed = format(value, "f")
    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed


def _definition_hash(adapter):
    return digest(adapter)


def _dependencies(values, label):
    if type(values) is not list or not values:
        raise ValueError(f"{label} requires valuation dependencies")
    metric_ids = []
    for item in values:
        _exact(item, _DEPENDENCY_KEYS, label + " item")
        metric_ids.append(item["metric_id"])
    if metric_ids != sorted(set(metric_ids)):
        raise ValueError(f"{label} must be sorted and unique")


def _basis(decision, policy_result, dependency):
    operands = decision["operands"]
    expected_operands = {"current_roe", "annual_roe_quantile", "current_margin",
        "annual_margin_quantile", "quantile_method", "quantile_level",
        "normalization_basis"}
    if type(operands) is not dict or set(operands) != expected_operands:
        raise ValueError("matched cyclic decision requires one normalization basis")
    basis = operands["normalization_basis"]
    _exact(basis, _BASIS_KEYS, "normalization basis")
    profit = basis["original_current_profit"]
    _exact(profit, {"selector_hash", "value", "evidence_hashes"}, "original profit")
    _dependencies(basis["valuation_dependencies"], "normalization basis")
    if (basis["profit_semantic_id"] != decision["semantic_id"]
            or type(basis["valuation_dependencies"]) is not list
            or dependency not in basis["valuation_dependencies"]
            or len([item for item in basis["valuation_dependencies"]
                    if type(item) is dict and item.get("metric_id") == dependency["metric_id"]]) != 1):
        raise ValueError("normalization basis differs from signed dependency")
    matches = policy_result["normalization_basis"]
    if type(matches) is not list or len(matches) != 1:
        raise ValueError("policy result requires one normalization basis")
    _exact(matches[0], _BASIS_KEYS | {"rule_id", "definition_hash", "trace"},
           "policy normalization basis")
    if (matches[0]["rule_id"] != decision["rule_id"]
            or matches[0]["definition_hash"] != decision["definition_hash"]
            or matches[0]["trace"] != decision["trace"]
            or {key: matches[0][key] for key in _BASIS_KEYS} != basis):
        raise ValueError("policy normalization basis differs from cyclic decision")
    refs = decision["input_references"]
    if type(refs) is not list:
        raise ValueError("decision input references must be an array")
    profit_refs = [ref for ref in refs if type(ref) is dict
                   and ref.get("input_name") == "current_profit"]
    if len(profit_refs) != 1 or profit_refs[0].get("selector_hash") != profit["selector_hash"]:
        raise ValueError("original profit selector differs from decision")
    return basis, profit_refs[0]


def evaluate_valuation_adjustment(*, metric: dict, policy_result: dict,
                                  cyclic_decision: dict, dependency: dict,
                                  adapter: dict | None) -> dict:
    """Evaluate detached copies only; returned hashes describe data, not authority."""
    _exact(metric, _METRIC_KEYS, "metric")
    _exact(policy_result, _RESULT_KEYS, "policy result")
    _exact(cyclic_decision, _DECISION_KEYS, "cyclic decision")
    _exact(dependency, _DEPENDENCY_KEYS, "dependency")
    if adapter is not None:
        _exact(adapter, _ADAPTER_KEYS, "adapter")
    _hash(metric, "input_hash", "metric")
    _hash(policy_result, "result_hash", "policy result")
    _hash(cyclic_decision, "decision_hash", "cyclic decision")
    for key in ("registry_manifest_hash", "frozen_input_hash", "universe_hash", "as_of_utc", "security_id"):
        if metric[key] != policy_result[key]:
            raise ValueError(f"metric and policy result differ in {key}")
    if (type(policy_result["decisions"]) is not list
            or len([item for item in policy_result["decisions"]
                    if type(item) is dict and item.get("role") == "cyclic"]) != 1
            or cyclic_decision not in policy_result["decisions"]):
        raise ValueError("cyclic decision is not uniquely bound to policy result")
    if (cyclic_decision["role"] != "cyclic"
            or cyclic_decision["semantic_id"] != "cyclic_top"
            or cyclic_decision["security_id"] != metric["security_id"]
            or cyclic_decision["template_id"] != metric["template_id"]):
        raise ValueError("cyclic decision identity differs from metric")
    _text(cyclic_decision["rule_id"], "cyclic rule ID")
    if (type(cyclic_decision["parameters"]) is not dict
            or type(cyclic_decision["parameters"].get("valuation_dependencies")) is not list
            or not cyclic_decision["parameters"]["valuation_dependencies"]
            or dependency not in cyclic_decision["parameters"]["valuation_dependencies"]
            or len([item for item in cyclic_decision["parameters"]["valuation_dependencies"]
                    if type(item) is dict and item.get("metric_id") == dependency["metric_id"]]) != 1
            or dependency["metric_id"] != metric["metric_id"]):
        raise ValueError("dependency differs from cyclic policy or metric")
    _dependencies(cyclic_decision["parameters"]["valuation_dependencies"],
                  "cyclic decision")
    dependency_state = dependency["policy_dependency"]
    if dependency_state not in ("affected", "unaffected"):
        raise ValueError("unknown valuation dependency")
    if dependency_state == "unaffected":
        if adapter is not None or any(dependency[field] is not None for field in
                ("profit_semantic_id", "adapter_id", "adapter_version")):
            raise ValueError("unaffected dependency cannot carry an adapter")
    else:
        if adapter is None:
            raise ValueError("affected dependency requires its signed adapter definition")
        if dependency["profit_semantic_id"] != cyclic_decision["semantic_id"]:
            raise ValueError("affected profit semantic differs from cyclic decision")
        required = dict(template_id=metric["template_id"], metric_id=metric["metric_id"],
            adapter_id=dependency["adapter_id"], adapter_version=dependency["adapter_version"],
            profit_semantic_id=dependency["profit_semantic_id"],
            original_definition_hash=metric["definition_hash"],
            definition_basis=dependency["definition_basis"], policy_role="cyclic",
            rule_id=cyclic_decision["rule_id"], operation="profit_ratio_rescale_v1",
            decimal_contract="decimal50-half-even-v1", preconditions=list(_PRECONDITIONS))
        if any(adapter[key] != value or type(adapter[key]) is not type(value)
               for key, value in required.items()):
            raise ValueError("adapter differs from signed dependency or metric")
        if (adapter["metric_unit"] != adapter["output_unit"]
                or adapter["profit_unit"] != "CNY"):
            raise ValueError("adapter unit contract is unsupported")
    state = cyclic_decision["evaluation_state"]
    if state not in ("clear", "not_applicable", "matched", "pending_evidence"):
        raise ValueError("unknown cyclic decision state")
    if state != "matched" and cyclic_decision["operands"].get("normalization_basis") is not None:
        raise ValueError("unmatched cyclic decision cannot carry normalization basis")
    if state == "matched":
        basis, profit_ref = _basis(cyclic_decision, policy_result, dependency)
    elif policy_result["normalization_basis"]:
        raise ValueError("unmatched cyclic decision cannot yield normalization basis")
    else:
        basis, profit_ref = None, None

    result = dict(metric_input_hash=metric["input_hash"],
        policy_result_hash=policy_result["result_hash"],
        decision_hash=cyclic_decision["decision_hash"],
        adapter_definition_hash=None if adapter is None else _definition_hash(adapter),
        security_id=metric["security_id"], template_id=metric["template_id"],
        metric_id=metric["metric_id"], policy_dependency=dependency_state,
        operation=None, original_metric_value=None,
        original_current_profit=None, normalized_profit=None,
        adjusted_value=None, status=None, reason=None)
    raw, raw_error = _decimal(metric["raw_value"])
    if raw_error is None:
        result["original_metric_value"] = _decimal_text(raw)
    if basis is not None:
        current, current_error = _decimal(basis["original_current_profit"]["value"])
        normalized, normalized_error = _decimal(basis["normalized_profit"])
        if current_error is None:
            result["original_current_profit"] = _decimal_text(current)
        if normalized_error is None:
            result["normalized_profit"] = _decimal_text(normalized)
    if metric["direction"] not in ("higher", "lower"):
        result.update(status="invalid_adapter_operand", reason="metric_direction_invalid")
    elif adapter is not None and metric["unit"] != adapter["metric_unit"]:
        result.update(status="invalid_adapter_operand", reason="metric_unit_mismatch")
    elif raw_error is not None:
        result.update(status="invalid_adapter_operand", reason="metric_value_" + raw_error)
    elif metric["status"] != "eligible" or metric["invalid_reason"] is not None:
        result.update(status="invalid_adapter_operand", reason="metric_ineligible")
    elif state == "pending_evidence" and dependency_state == "affected":
        result.update(status="pending_policy_evidence", reason="cyclic_decision_pending")
    elif state in ("clear", "not_applicable") or dependency_state == "unaffected":
        status = "passthrough_" + (state if state in ("clear", "not_applicable") else "unaffected")
        result.update(status=status, reason=state,
                      adjusted_value=_decimal_text(raw))
    else:
        result["operation"] = adapter["operation"]
        if profit_ref.get("unit") != adapter["profit_unit"]:
            result.update(status="invalid_adapter_operand", reason="profit_unit_mismatch")
        elif current_error is not None:
            result.update(status="invalid_adapter_operand", reason="original_current_profit_" + current_error)
        elif normalized_error is not None:
            result.update(status="invalid_adapter_operand", reason="normalized_profit_" + normalized_error)
        elif current == 0:
            result.update(status="invalid_adapter_operand", reason="original_current_profit_zero")
        else:
            try:
                adjusted = profit_ratio_rescale(raw, current, normalized)
                if not adjusted.is_finite():
                    raise ValueError("nonfinite adjusted value")
            except (ValueError, ArithmeticError):
                result.update(status="invalid_adapter_operand", reason="adjustment_arithmetic_failed")
            else:
                result.update(status="adjusted_no_numeric_change" if adjusted == raw else "adjusted",
                    reason="cyclic_policy_matched", adjusted_value=_decimal_text(adjusted))
    result["result_hash"] = digest(result)
    return result


def _install_valuation_adapter_owner():
    """Keep C3's pure evaluator private dependency graph fixed for C4 owners."""
    names = (
        "Context", "Decimal", "DivisionByZero", "InvalidOperation", "Overflow",
        "ROUND_HALF_EVEN", "localcontext", "digest", "_policy_values_module",
        "_METRIC_KEYS", "_RESULT_KEYS", "_DECISION_KEYS", "_DEPENDENCY_KEYS",
        "_ADAPTER_KEYS", "_BASIS_KEYS", "_PRECONDITIONS", "_arithmetic_context",
        "profit_ratio_rescale", "_exact", "_hash", "_text", "_decimal",
        "_decimal_text", "_definition_hash", "_dependencies", "_basis",
        "evaluate_valuation_adjustment",
    )
    originals = tuple((name, globals()[name]) for name in names)
    policy_values = _policy_values_module
    policy_dependencies = tuple((name, getattr(policy_values, name)) for name in
        ("digest", "canonical_bytes", "json", "hashlib"))
    json_dumps = policy_values.json.dumps
    sha256 = policy_values.hashlib.sha256
    evaluator = evaluate_valuation_adjustment

    def require_owner():
        if (globals().get("_require_valuation_adapter_owner") is not require_owner
                or any(globals().get(name) is not value for name, value in originals)
                or any(getattr(policy_values, name, None) is not value
                       for name, value in policy_dependencies)
                or policy_values.json.dumps is not json_dumps
                or policy_values.hashlib.sha256 is not sha256):
            raise ValueError("valuation adapter dependency changed")
        return evaluator

    return require_owner


_require_valuation_adapter_owner = _install_valuation_adapter_owner()
del _install_valuation_adapter_owner


__all__ = ["profit_ratio_rescale", "evaluate_valuation_adjustment"]
