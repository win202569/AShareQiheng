"""Pure evaluation of detached formal-policy values and signed rule copies."""

from __future__ import annotations

import copy
from decimal import Decimal, ROUND_CEILING, localcontext

from .formal_policy_contract import parse_policy_rule
from .formal_policy_values import PolicyValue, canonical_bytes, decimal_context, digest


_APPLICABILITY = frozenset(("applicable", "not_applicable", "unresolved"))
_DECISION_STATES = frozenset(("matched", "clear", "not_applicable", "pending_evidence"))
_DECISION_FIELDS = frozenset((
    "rule_id", "role", "semantic_id", "template_id", "security_id",
    "definition_hash", "input_references", "operands", "parameters",
    "evaluation_state", "proven_effects", "pending_requirements", "trace",
))
_MARKET_FIELDS = (
    "price_state", "price", "price_date", "stale_days", "stale_at_least",
    "veto_state", "pending",
)


def _decimal_text(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("finite Decimal required")
    if value.is_zero():
        return "0"
    fixed = format(value, "f")
    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed


def _effect_key(effect: dict) -> bytes:
    return canonical_bytes(effect)


def _pending_key(item: dict):
    return (
        item["origin"], item["code"], item.get("rule_id") or "",
        item.get("input_name") or "", item.get("selector_hash") or "",
        item.get("fy_end") or "", tuple(item["evidence_hashes"]),
    )


def _rule_copy(rule: dict) -> tuple[dict, str]:
    if type(rule) is not dict:
        raise ValueError("rule must be an exact detached object")
    expected = {
        "schema_version", "kind", "semantic_id", "template_id", "inputs",
        "parameters", "outcomes", "role", "rule_id",
    }
    if set(rule) != expected:
        raise ValueError("rule has unknown or missing fields")
    detached = copy.deepcopy(rule)
    declaration = {key: detached[key] for key in (
        "schema_version", "kind", "semantic_id", "template_id", "inputs",
        "parameters", "outcomes",
    )}
    parse_policy_rule(detached["role"], detached["rule_id"], canonical_bytes(declaration))
    return detached, digest(detached)


def quantile80(values: tuple[Decimal, ...], method: str) -> Decimal:
    """Evaluate one of the two signed five-observation quantile methods."""
    if (type(values) is not tuple or len(values) != 5
            or any(type(value) is not Decimal or not value.is_finite() for value in values)):
        raise ValueError("five finite Decimal annual observations required")
    ordered = sorted(values)
    with localcontext(decimal_context()):
        if method == "nearest_rank_v1":
            rank = int((Decimal(len(ordered)) * Decimal("0.8")).to_integral_value(
                rounding=ROUND_CEILING
            ))
            return ordered[rank - 1]
        if method == "linear_type7_v1":
            h = Decimal(len(ordered) - 1) * Decimal("0.8")
            lower = int(h)
            return ordered[lower] + (h - lower) * (ordered[lower + 1] - ordered[lower])
    raise ValueError("unsupported signed quantile method")


def _runtime_pending(code, *, input_name, selector_hash, evidence_hashes=(), fy_end=None):
    item = {
        "origin": "runtime",
        "code": code,
        "rule_id": None,
        "evidence_hashes": sorted(set(evidence_hashes)),
        "input_name": input_name,
        "selector_hash": selector_hash,
    }
    if fy_end is not None:
        item["fy_end"] = fy_end
    return item


def _bound_pending(pending, *, input_name, selector_hash, fy_end=None):
    item = copy.deepcopy(pending)
    item["input_name"] = input_name
    item["selector_hash"] = selector_hash
    if fy_end is not None:
        item["fy_end"] = fy_end
    return item


def _value_reference(input_name, selector_hash, value, *, fy_end=None):
    if type(value) is not PolicyValue:
        raise ValueError("policy inputs must be exact PolicyValue instances")
    reference = {
        "input_name": input_name,
        "selector_hash": selector_hash,
        "state": value.state,
        "value_type": value.value_type,
        "unit": value.unit,
        "evidence_hashes": list(value.evidence_hashes),
    }
    if fy_end is not None:
        reference["fy_end"] = fy_end
    pending = [
        _bound_pending(item, input_name=input_name, selector_hash=selector_hash,
                       fy_end=fy_end)
        for item in value.to_dict()["pending"]
    ]
    return reference, pending


def _missing_code(selector):
    if selector["kind"] == "feature" or selector["kind"] == "annual_series":
        return "financial_input_missing"
    return "state_entry_missing"


def _scalar(rule, values, name, references, pending):
    selector = rule["inputs"][name]
    selector_hash = digest(selector)
    value = values.get(selector_hash)
    if value is None:
        pending.append(_runtime_pending(
            _missing_code(selector), input_name=name, selector_hash=selector_hash
        ))
        return None
    reference, value_pending = _value_reference(name, selector_hash, value)
    references.append(reference)
    pending.extend(value_pending)
    if value.state != "value":
        return None
    if selector["kind"] == "feature":
        if value.value_type != "decimal" or value.unit != selector["expected_unit"]:
            raise ValueError("financial value differs from its signed selector")
    elif selector["kind"] == "context":
        if value.value_type != selector["expected_type"] or value.unit is not None:
            raise ValueError("context value differs from its signed selector")
    else:
        raise ValueError("scalar input requires a scalar selector")
    return value.value


def _annual(rule, annual, name, references, pending):
    selector = rule["inputs"][name]
    series_hash = digest(selector)
    records = annual.get(series_hash)
    if records is None:
        pending.append(_runtime_pending(
            "financial_input_missing", input_name=name, selector_hash=series_hash
        ))
        return (None,) * 5, []
    if type(records) not in (tuple, list) or len(records) != 5:
        raise ValueError("annual inputs require five observation records")
    expected = tuple(selector["observations"])
    values = []
    originals = []
    for record, observation in zip(records, expected, strict=True):
        if not hasattr(record, "keys"):
            raise ValueError("annual observation record must be a mapping")
        fy_end = observation["fy_end"]
        leaf = observation["selector"]
        leaf_hash = digest(leaf)
        if record.get("fy_end") != fy_end or record.get("selector_hash") != leaf_hash:
            raise ValueError("annual observation differs from its signed selector")
        value = record.get("value")
        reference, value_pending = _value_reference(
            name, leaf_hash, value, fy_end=fy_end
        )
        references.append(reference)
        pending.extend(value_pending)
        if (value.state == "value"
                and (value.value_type != "decimal" or value.unit != leaf["expected_unit"])):
            raise ValueError("annual value differs from its signed selector")
        if value.state == "value":
            values.append(value.value)
            originals.append({
                "fy_end": fy_end,
                "selector_hash": leaf_hash,
                "value": _decimal_text(value.value),
                "evidence_hashes": list(value.evidence_hashes),
            })
        else:
            values.append(None)
    return tuple(values), originals


def _comparison(comparator, left, right):
    if comparator == "lt":
        return left < right
    if comparator == "lte":
        return left <= right
    if comparator == "gt":
        return left > right
    if comparator == "gte":
        return left >= right
    if comparator == "eq":
        return left == right
    raise ValueError("unsupported signed comparator")


def _market_reference(rule, market):
    evidence = []
    for key in ("window_hash", "calendar_coverage_hash"):
        value = market.get(key)
        if type(value) is str:
            evidence.append(value)
    lineage = market.get("lineage", ())
    if type(lineage) in (tuple, list):
        evidence.extend(value for value in lineage if type(value) is str)
    evidence = sorted(set(evidence))
    return [{
        "input_name": name,
        "selector_hash": digest(rule["inputs"][name]),
        "state": "value",
        "value_type": "market_window",
        "unit": None,
        "evidence_hashes": evidence,
    } for name in sorted(rule["inputs"])]


def _closed_market_payload(market):
    if any(field not in market for field in _MARKET_FIELDS):
        raise ValueError("market input lacks a closed W1 result axis")
    parsed = PolicyValue.from_dict({
        "state": "value",
        "value": {field: copy.deepcopy(market[field]) for field in _MARKET_FIELDS},
        "value_type": "market_window",
        "unit": None,
        "evidence_hashes": [],
        "pending": [],
    })
    return parsed.to_dict()["value"]


def _signed_pending(effect, rule, evidence_hashes):
    return {
        "origin": "signed_policy",
        "code": effect["reason_code"],
        "rule_id": rule["rule_id"],
        "evidence_hashes": list(evidence_hashes),
        "input_name": "on_match",
        "selector_hash": None,
    }


def _match_effects(rule, evidence_hashes, *, pool_only=False):
    proven, pending = [], []
    for effect in rule["outcomes"]["on_match"]:
        if effect["kind"] == "pending_evidence":
            if not pool_only:
                pending.append(_signed_pending(effect, rule, evidence_hashes))
        elif not pool_only or effect["kind"] == "pool_prohibition":
            proven.append(copy.deepcopy(effect))
    return sorted(proven, key=_effect_key), pending


def _normalization_basis(rule, current_profit, current_ref, annual_profit,
                         annual_originals):
    ordered = sorted(annual_profit)
    median = ordered[2]
    with localcontext(decimal_context()):
        normalized = min(current_profit, median)
    return {
        "profit_semantic_id": rule["semantic_id"],
        "original_current_profit": {
            "selector_hash": current_ref["selector_hash"],
            "value": _decimal_text(current_profit),
            "evidence_hashes": list(current_ref["evidence_hashes"]),
        },
        "annual_profit": copy.deepcopy(annual_originals),
        "ordered_values": [_decimal_text(value) for value in ordered],
        "median_method": rule["parameters"]["median_method"],
        "median": _decimal_text(median),
        "profit_basis_method": rule["parameters"]["profit_basis_method"],
        "normalized_profit": _decimal_text(normalized),
        "valuation_dependencies": copy.deepcopy(
            rule["parameters"]["valuation_dependencies"]
        ),
    }


def evaluate_rule(rule: dict, *, security_id: str, applicability: str,
                  values: dict, annual: dict, market: dict | None) -> dict:
    """Evaluate one detached, syntactically valid Stage A rule copy."""
    rule, definition_hash = _rule_copy(rule)
    if type(security_id) is not str or not security_id:
        raise ValueError("security_id must be nonempty text")
    if applicability not in _APPLICABILITY:
        raise ValueError("unknown applicability state")
    if type(values) is not dict or type(annual) is not dict:
        raise ValueError("values and annual must be selector-indexed objects")

    references = []
    pending = []
    operands = {}
    steps = []
    state = None
    proven = []

    if applicability == "not_applicable":
        state = "not_applicable"
        steps.append({"operation": "applicability", "result": "not_applicable"})
    elif applicability == "unresolved":
        state = "pending_evidence"
        pending.append(_runtime_pending(
            "applicability_unresolved", input_name="applicability", selector_hash=None
        ))
        steps.append({"operation": "applicability", "result": "unresolved"})
    elif rule["kind"] == "numeric_redline":
        actual = _scalar(rule, values, "value", references, pending)
        threshold = Decimal(rule["parameters"]["threshold"])
        operands.update(value=None if actual is None else _decimal_text(actual),
                        threshold=_decimal_text(threshold),
                        comparator=rule["parameters"]["comparator"])
        if actual is None:
            state = "pending_evidence"
        else:
            matched = _comparison(rule["parameters"]["comparator"], actual, threshold)
            state = "matched" if matched else "clear"
        steps.append({"operation": "numeric_comparison", "result": state})
    elif rule["kind"] in ("boolean_state", "enum_state"):
        actual = _scalar(rule, values, "value", references, pending)
        if rule["kind"] == "boolean_state":
            operands.update(value=actual, expected=rule["parameters"]["expected"])
            matched = actual is not None and type(actual) is bool and actual is operands["expected"]
        else:
            operands.update(value=actual, values=copy.deepcopy(rule["parameters"]["values"]))
            matched = actual is not None and type(actual) is str and actual in operands["values"]
        state = "pending_evidence" if actual is None else "matched" if matched else "clear"
        steps.append({"operation": "exact_state_comparison", "result": state})
    elif rule["kind"] == "cyclic_protection":
        current_roe = _scalar(rule, values, "current_roe", references, pending)
        current_margin = _scalar(rule, values, "current_margin", references, pending)
        current_profit = _scalar(rule, values, "current_profit", references, pending)
        annual_roe, _ = _annual(rule, annual, "annual_roe", references, pending)
        annual_margin, _ = _annual(rule, annual, "annual_margin", references, pending)
        annual_profit, profit_originals = _annual(
            rule, annual, "annual_profit", references, pending
        )
        method = rule["parameters"]["quantile_method"]
        roe_quantile = (quantile80(annual_roe, method)
                        if all(value is not None for value in annual_roe) else None)
        margin_quantile = (quantile80(annual_margin, method)
                           if all(value is not None for value in annual_margin) else None)
        roe_match = (None if current_roe is None or roe_quantile is None
                     else current_roe >= roe_quantile)
        margin_match = (None if current_margin is None or margin_quantile is None
                        else current_margin >= margin_quantile)
        operands.update(
            current_roe=None if current_roe is None else _decimal_text(current_roe),
            annual_roe_quantile=None if roe_quantile is None else _decimal_text(roe_quantile),
            current_margin=None if current_margin is None else _decimal_text(current_margin),
            annual_margin_quantile=(None if margin_quantile is None
                                    else _decimal_text(margin_quantile)),
            quantile_method=method,
            quantile_level=rule["parameters"]["quantile_level"],
        )
        if roe_match is False or margin_match is False:
            state = "clear"
        elif roe_match is None or margin_match is None or current_profit is None or any(
                value is None for value in annual_profit):
            state = "pending_evidence"
        else:
            state = "matched"
            current_ref = next(item for item in references
                               if item["input_name"] == "current_profit")
            operands["normalization_basis"] = _normalization_basis(
                rule, current_profit, current_ref, annual_profit, profit_originals
            )
        steps.append({"operation": "two_metric_cyclic_conjunction", "result": state})
    elif rule["kind"] == "market_liquidity":
        if market is None:
            pending.append(_runtime_pending(
                "market_coverage_missing", input_name="market", selector_hash=None
            ))
            state = "pending_evidence"
            operands.update(price_state=None, veto_state=None)
        else:
            if type(market) is not dict:
                raise ValueError("market must be a detached object or None")
            payload = _closed_market_payload(market)
            references.extend(_market_reference(rule, market))
            evidence_hashes = sorted({value for item in references
                                      for value in item["evidence_hashes"]})
            for code in payload["pending"]:
                pending.append(_runtime_pending(
                    code, input_name="market", selector_hash=None,
                    evidence_hashes=evidence_hashes,
                ))
            price_state, veto_state = payload["price_state"], payload["veto_state"]
            operands.update(price_state=price_state, veto_state=veto_state,
                            price=payload["price"], price_date=payload["price_date"],
                            stale_days=payload["stale_days"],
                            stale_at_least=payload["stale_at_least"])
            if veto_state == "proven" and price_state == "incomplete":
                state = "pending_evidence"
                proven, signed_pending = _match_effects(
                    rule, evidence_hashes, pool_only=True
                )
                pending.extend(signed_pending)
            elif veto_state == "pending" or price_state == "incomplete":
                state = "pending_evidence"
                if not pending:
                    pending.append(_runtime_pending(
                        "market_coverage_missing", input_name="market", selector_hash=None,
                        evidence_hashes=evidence_hashes,
                    ))
            elif veto_state == "proven":
                state = "matched"
            elif veto_state == "clear":
                state = "clear"
            else:
                raise ValueError("market veto state is invalid")
        steps.append({"operation": "independent_market_axes", "result": state})
    else:
        raise ValueError("unsupported signed policy rule kind")

    references.sort(key=lambda item: (
        item["input_name"], item.get("fy_end") or "", item["selector_hash"]
    ))
    evidence_hashes = sorted({value for item in references
                              for value in item["evidence_hashes"]})
    if state == "matched" and not proven:
        proven, signed_pending = _match_effects(rule, evidence_hashes)
        pending.extend(signed_pending)
    pending.sort(key=_pending_key)
    trace = {
        "definition_hash": definition_hash,
        "applicability": applicability,
        "evidence_hashes": evidence_hashes,
        "input_references": copy.deepcopy(references),
        "steps": steps,
    }
    if state not in _DECISION_STATES:
        raise ValueError("evaluator produced an invalid decision state")
    return {
        "rule_id": rule["rule_id"],
        "role": rule["role"],
        "semantic_id": rule["semantic_id"],
        "template_id": rule["template_id"],
        "security_id": security_id,
        "definition_hash": definition_hash,
        "input_references": references,
        "operands": operands,
        "parameters": copy.deepcopy(rule["parameters"]),
        "evaluation_state": state,
        "proven_effects": proven,
        "pending_requirements": pending,
        "trace": trace,
    }


def combine_caps(caps):
    result = {}
    for dimension, limit in caps:
        result[dimension] = min(result.get(dimension, limit), limit)
    return result


def _effect_reason(decision, effect):
    return {
        "rule_id": decision["rule_id"],
        "role": decision["role"],
        "semantic_id": decision["semantic_id"],
        "template_id": decision["template_id"],
        "security_id": decision["security_id"],
        "definition_hash": decision["definition_hash"],
        "effect": copy.deepcopy(effect),
        "trace": copy.deepcopy(decision["trace"]),
    }


def _reason_key(reason):
    return (
        reason["security_id"], reason["role"], reason["rule_id"],
        _effect_key(reason["effect"]),
    )


def aggregate_decisions(decisions: tuple[dict, ...]) -> dict:
    """Combine decisions without erasing any effect or pending-evidence reason."""
    if type(decisions) is not tuple:
        raise ValueError("decisions must be a tuple")
    copied = []
    caps = []
    pools = {"strong": [], "wait": []}
    states = {}
    normalization = []
    pending = []
    for decision in decisions:
        if type(decision) is not dict or set(decision) != _DECISION_FIELDS:
            raise ValueError("decision has unknown or missing fields")
        if decision["evaluation_state"] not in _DECISION_STATES:
            raise ValueError("decision state is invalid")
        item = copy.deepcopy(decision)
        copied.append(item)
        for requirement in item["pending_requirements"]:
            pending.append({
                **copy.deepcopy(requirement),
                "decision": {
                    key: item[key] for key in (
                        "rule_id", "role", "semantic_id", "template_id",
                        "security_id", "definition_hash",
                    )
                },
                "trace": copy.deepcopy(item["trace"]),
            })
        for effect in item["proven_effects"]:
            kind = effect["kind"]
            reason = _effect_reason(item, effect)
            if kind == "dimension_cap":
                caps.append((effect["dimension"], Decimal(effect["maximum"])))
            elif kind == "pool_prohibition":
                targets = ("strong", "wait") if effect["pool"] == "both" else (effect["pool"],)
                for target in targets:
                    pools[target].append(copy.deepcopy(reason))
            elif kind == "independent_status":
                states.setdefault(effect["status_code"], []).append(reason)
            elif kind == "valuation_profit_basis":
                basis = item["operands"].get("normalization_basis")
                if basis is None:
                    raise ValueError("proven profit-basis effect lacks normalization operands")
                normalization.append({
                    **copy.deepcopy(basis),
                    "rule_id": item["rule_id"],
                    "definition_hash": item["definition_hash"],
                    "trace": copy.deepcopy(item["trace"]),
                })
            else:
                raise ValueError("decision carries an unsupported proven effect")
    copied.sort(key=lambda item: (
        item["security_id"], item["role"], item["rule_id"], item["definition_hash"]
    ))
    pools = {pool: sorted(reasons, key=_reason_key)
             for pool, reasons in pools.items() if reasons}
    states = {code: sorted(reasons, key=_reason_key)
              for code, reasons in sorted(states.items())}
    normalization.sort(key=lambda item: (item["rule_id"], item["definition_hash"]))
    pending.sort(key=lambda item: (
        item["decision"]["security_id"], item["decision"]["role"],
        item["decision"]["rule_id"], *_pending_key(item),
    ))
    return {
        "decisions": copied,
        "dimension_caps": {
            dimension: _decimal_text(limit)
            for dimension, limit in sorted(combine_caps(caps).items())
        },
        "pool_prohibitions": pools,
        "states": states,
        "normalization_basis": normalization,
        "pending_requirements": pending,
        "evidence_state": "pending_evidence" if pending else "complete",
    }


__all__ = ["aggregate_decisions", "evaluate_rule", "quantile80"]
