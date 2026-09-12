"""Detached, non-authoritative syntax values for formal policy contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import re
from types import MappingProxyType


class PolicyContractError(ValueError):
    """A detached policy declaration has invalid or unsupported syntax."""

    def __init__(self, message, *, code="malformed_contract", path="contract"):
        self.code, self.path = code, path
        super().__init__(f"{code}:{path}: {message}")


@dataclass(frozen=True, slots=True)
class PolicyRule:
    role: str
    rule_id: str
    kind: str
    semantic_id: str
    template_id: str
    inputs: Mapping[str, object]
    parameters: Mapping[str, object]
    outcomes: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ParsedPolicyContract:
    rules: tuple[PolicyRule, ...]
    role_versions: Mapping[str, str]
    evidence_categories: Mapping[str, tuple[str, ...]]
    canonical_json: bytes


_ROLES = ("cyclic", "redline", "status", "event")
_TEMPLATES = (
    "general_nonfinancial",
    "bank",
    "broker",
    "insurance",
    "real_estate",
)
_FY_ENDS = tuple(f"{year}-12-31" for year in range(2021, 2026))
_RULE_KINDS = {
    "numeric_redline": ("redline",),
    "boolean_state": ("status", "event"),
    "enum_state": ("status", "event"),
    "cyclic_protection": ("cyclic",),
    "market_liquidity": ("status",),
}
_CONTEXT_FIELDS = {
    ("security_state", "is_st"): ("bool", False, False),
    ("security_state", "is_star_st"): ("bool", False, False),
    ("security_state", "forced_delist_risk"): ("bool", False, False),
    ("security_state", "suspended"): ("bool", False, False),
    ("security_state", "listing_status"): ("enum", False, False),
    ("regulatory_state", "active"): ("bool", True, False),
    ("event_calendar", "event"): ("event_record", True, True),
    ("market_close", "record"): ("market_record", False, False),
    ("trading_calendar", "record"): ("calendar_record", False, False),
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
_DIMENSIONS = ("G", "V", "M", "EQ", "FS", "CA", "T")
_LISTING_VALUES = ("listed", "delisting_arrangement", "delisted")


def _canonical(value):
    if type(value) is dict:
        return "{" + ",".join(
            _canonical(key) + ":" + _canonical(value[key]) for key in sorted(value)
        ) + "}"
    if type(value) is list:
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("nonfinite JSON")
        return str(value)
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )


def _load(raw, path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"nonfinite JSON {value}")

    if type(raw) is not bytes:
        raise PolicyContractError(
            "canonical JSON must be immutable UTF-8 bytes", path=path
        )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=invalid,
        )
        if type(value) is not dict or _canonical(value).encode("utf-8") != raw:
            raise ValueError("canonical JSON object required")
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise PolicyContractError("invalid canonical JSON", path=path) from error
    return value


def _exact_keys(value, expected, path):
    if type(value) is not dict or set(value) != set(expected):
        raise PolicyContractError("unknown or missing object fields", path=path)


def _text(value, path):
    if type(value) is not str or not value or value != value.strip():
        raise PolicyContractError("nonempty trimmed string required", path=path)
    return value


def _identifier(value, path):
    _text(value, path)
    if _IDENTIFIER.fullmatch(value) is None:
        raise PolicyContractError("identifier required", path=path)
    return value


def _decimal_parameter(value, path):
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise PolicyContractError("finite decimal string required", path=path)
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise PolicyContractError("invalid decimal", path=path) from error
    if not number.is_finite():
        raise PolicyContractError("nonfinite decimal", path=path)
    return number


def _algorithm_identifier(value, allowed, path):
    _identifier(value, path)
    if value not in allowed:
        raise PolicyContractError(
            "unsupported algorithm identifier", code="unsupported_contract", path=path
        )
    return value


def _ordered_texts(value, path, *, expected=None):
    if type(value) is not list or not value:
        raise PolicyContractError("nonempty string array required", path=path)
    result = tuple(_text(item, f"{path}[{index}]") for index, item in enumerate(value))
    if result != tuple(sorted(set(result))):
        raise PolicyContractError("array must be sorted and unique", path=path)
    if expected is not None and result != tuple(expected):
        raise PolicyContractError("array has unsupported fixed values", path=path)
    return result


def _text_array(value, path):
    if type(value) is not list or not value:
        raise PolicyContractError("nonempty string array required", path=path)
    result = tuple(_text(item, f"{path}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise PolicyContractError("array values must be unique", path=path)
    return result


def _feature_selector(value, path, template_id):
    _exact_keys(
        value,
        (
            "kind",
            "template_id",
            "feature_key",
            "expected_unit",
            "formula_version",
            "period_keys",
        ),
        path,
    )
    if value["kind"] != "feature":
        raise PolicyContractError("feature selector required", path=f"{path}.kind")
    if value["template_id"] != template_id:
        raise PolicyContractError(
            "selector template differs from rule", path=f"{path}.template_id"
        )
    for field in ("feature_key", "expected_unit", "formula_version"):
        _text(value[field], f"{path}.{field}")
    _ordered_texts(value["period_keys"], f"{path}.period_keys")


def _context_selector(value, path):
    _exact_keys(
        value,
        (
            "kind",
            "descriptor_id",
            "context_kind",
            "scope_key",
            "field",
            "entry_id",
            "expected_type",
            "expected_unit",
        ),
        path,
    )
    if value["kind"] != "context":
        raise PolicyContractError("Context selector required", path=f"{path}.kind")
    if type(value["descriptor_id"]) is not str or _SHA256.fullmatch(
        value["descriptor_id"]
    ) is None:
        raise PolicyContractError(
            "lowercase SHA-256 required", path=f"{path}.descriptor_id"
        )
    _text(value["scope_key"], f"{path}.scope_key")
    context_kind = _text(value["context_kind"], f"{path}.context_kind")
    field = _text(value["field"], f"{path}.field")
    if context_kind not in {kind for kind, _ in _CONTEXT_FIELDS}:
        raise PolicyContractError(
            "unsupported Context kind",
            code="unsupported_contract",
            path=f"{path}.context_kind",
        )
    signature = _CONTEXT_FIELDS.get((context_kind, field))
    if signature is None:
        raise PolicyContractError(
            "unsupported Context field", path=f"{path}.field"
        )
    expected_type, needs_entry, needs_unit = signature
    if value["expected_type"] != expected_type:
        raise PolicyContractError(
            "Context expected_type differs from field", path=f"{path}.expected_type"
        )
    if needs_entry:
        _text(value["entry_id"], f"{path}.entry_id")
    elif value["entry_id"] is not None:
        raise PolicyContractError("entry_id must be null", path=f"{path}.entry_id")
    if needs_unit:
        _text(value["expected_unit"], f"{path}.expected_unit")
    elif value["expected_unit"] is not None:
        raise PolicyContractError(
            "expected_unit must be null", path=f"{path}.expected_unit"
        )
    return expected_type


def _selector(value, path, template_id, *, expected_kind=None):
    if type(value) is not dict:
        raise PolicyContractError("selector object required", path=path)
    kind = value.get("kind")
    if kind == "feature":
        _feature_selector(value, path, template_id)
    elif kind == "annual_series":
        _exact_keys(value, ("kind", "observations"), path)
        observations = value["observations"]
        if type(observations) is not list:
            raise PolicyContractError(
                "observations must be an array", path=f"{path}.observations"
            )
        years = []
        for index, observation in enumerate(observations):
            item_path = f"{path}.observations[{index}]"
            _exact_keys(observation, ("fy_end", "selector"), item_path)
            years.append(observation["fy_end"])
            _feature_selector(
                observation["selector"], f"{item_path}.selector", template_id
            )
        if tuple(years) != _FY_ENDS:
            raise PolicyContractError(
                "exact ordered FY2021-FY2025 observations required",
                path=f"{path}.observations",
            )
    elif kind == "context":
        actual_type = _context_selector(value, path)
        if expected_kind is not None and expected_kind != actual_type:
            raise PolicyContractError(
                "Context selector has incompatible value type", path=f"{path}.expected_type"
            )
    else:
        raise PolicyContractError(
            "unsupported selector kind", code="unsupported_contract", path=f"{path}.kind"
        )
    if expected_kind in ("feature", "annual_series") and kind != expected_kind:
        raise PolicyContractError(
            f"{expected_kind} selector required", path=f"{path}.kind"
        )


def _valuation_dependencies(value, path, semantic_id):
    if type(value) is not list or not value:
        raise PolicyContractError("nonempty valuation dependency array required", path=path)
    metric_ids = []
    fields = (
        "metric_id",
        "policy_dependency",
        "profit_semantic_id",
        "adapter_id",
        "adapter_version",
        "definition_basis",
    )
    for index, dependency in enumerate(value):
        item_path = f"{path}[{index}]"
        _exact_keys(dependency, fields, item_path)
        metric_id = _identifier(dependency["metric_id"], f"{item_path}.metric_id")
        if not metric_id.startswith("V.") or len(metric_id) == 2:
            raise PolicyContractError(
                "valuation dependency metric_id must identify a V leaf",
                path=f"{item_path}.metric_id",
            )
        metric_ids.append(metric_id)
        _text(dependency["definition_basis"], f"{item_path}.definition_basis")
        policy_dependency = dependency["policy_dependency"]
        identity_fields = ("profit_semantic_id", "adapter_id", "adapter_version")
        if policy_dependency == "affected":
            if dependency["profit_semantic_id"] != semantic_id:
                raise PolicyContractError(
                    "affected profit semantic must reference this cyclic rule",
                    path=f"{item_path}.profit_semantic_id",
                )
            for field in identity_fields:
                _identifier(dependency[field], f"{item_path}.{field}")
        elif policy_dependency == "unaffected":
            if any(dependency[field] is not None for field in identity_fields):
                raise PolicyContractError(
                    "unaffected dependency identities must be null", path=item_path
                )
        else:
            raise PolicyContractError(
                "policy_dependency must be affected or unaffected",
                path=f"{item_path}.policy_dependency",
            )
    if tuple(metric_ids) != tuple(sorted(set(metric_ids))):
        raise PolicyContractError(
            "valuation dependencies must be sorted and unique by metric_id", path=path
        )


def _validate_parameters(kind, value, path, semantic_id):
    if kind == "numeric_redline":
        _exact_keys(value, ("comparator", "threshold"), path)
        if value["comparator"] not in ("lt", "lte", "gt", "gte", "eq"):
            raise PolicyContractError(
                "unsupported comparator", path=f"{path}.comparator"
            )
        _decimal_parameter(value["threshold"], f"{path}.threshold")
    elif kind == "boolean_state":
        _exact_keys(value, ("expected",), path)
        if type(value["expected"]) is not bool:
            raise PolicyContractError("exact bool required", path=f"{path}.expected")
    elif kind == "enum_state":
        _exact_keys(value, ("values",), path)
        values = _ordered_texts(value["values"], f"{path}.values")
        if not set(values).issubset(_LISTING_VALUES):
            raise PolicyContractError(
                "unsupported listing enum value", path=f"{path}.values"
            )
    elif kind == "cyclic_protection":
        _exact_keys(
            value,
            (
                "fy_ends",
                "quantile_method",
                "quantile_level",
                "median_method",
                "profit_basis_method",
                "valuation_dependencies",
            ),
            path,
        )
        _ordered_texts(value["fy_ends"], f"{path}.fy_ends", expected=_FY_ENDS)
        _algorithm_identifier(
            value["quantile_method"],
            ("linear_type7_v1", "nearest_rank_v1"),
            f"{path}.quantile_method",
        )
        if value["quantile_level"] != "0.80":
            raise PolicyContractError(
                "unsupported fixed cyclic parameter", path=f"{path}.quantile_level"
            )
        _algorithm_identifier(
            value["median_method"],
            ("ordered_middle_v1",),
            f"{path}.median_method",
        )
        _algorithm_identifier(
            value["profit_basis_method"],
            ("minimum_current_and_five_fy_median_v1",),
            f"{path}.profit_basis_method",
        )
        _valuation_dependencies(
            value["valuation_dependencies"],
            f"{path}.valuation_dependencies",
            semantic_id,
        )
    else:
        _exact_keys(
            value,
            (
                "effective_trade_method",
                "veto_trading_days",
                "close_search_trading_days",
                "required_evidence_capability",
            ),
            path,
        )
        expected = {
            "effective_trade_method": "exchange_allows_and_positive_volume_turnover_v1",
            "veto_trading_days": 20,
            "close_search_trading_days": 250,
            "required_evidence_capability": "verified_market_window_v1",
        }
        _algorithm_identifier(
            value["effective_trade_method"],
            ("exchange_allows_and_positive_volume_turnover_v1",),
            f"{path}.effective_trade_method",
        )
        for field, required in expected.items():
            actual = value[field]
            if type(required) is int:
                valid = type(actual) is int and actual == required
            else:
                valid = actual == required
            if not valid:
                raise PolicyContractError(
                    "unsupported fixed market parameter", path=f"{path}.{field}"
                )


def _validate_effect(effect, path, semantic_id):
    if type(effect) is not dict:
        raise PolicyContractError("effect object required", path=path)
    kind = effect.get("kind")
    if kind == "dimension_cap":
        _exact_keys(effect, ("kind", "dimension", "maximum"), path)
        if effect["dimension"] not in _DIMENSIONS:
            raise PolicyContractError(
                "unknown scoring dimension", path=f"{path}.dimension"
            )
        maximum = _decimal_parameter(effect["maximum"], f"{path}.maximum")
        if maximum < 0 or maximum > 100:
            raise PolicyContractError(
                "dimension cap must be between 0 and 100", path=f"{path}.maximum"
            )
    elif kind == "pool_prohibition":
        _exact_keys(effect, ("kind", "pool"), path)
        if effect["pool"] not in ("strong", "wait", "both"):
            raise PolicyContractError("unknown pool", path=f"{path}.pool")
    elif kind == "valuation_profit_basis":
        _exact_keys(effect, ("kind", "profit_semantic_id"), path)
        if effect["profit_semantic_id"] != semantic_id:
            raise PolicyContractError(
                "profit basis must reference this rule",
                path=f"{path}.profit_semantic_id",
            )
    elif kind == "independent_status":
        _exact_keys(effect, ("kind", "status_code"), path)
        _identifier(effect["status_code"], f"{path}.status_code")
        if effect["status_code"] != semantic_id:
            raise PolicyContractError(
                "independent status must identify this rule",
                path=f"{path}.status_code",
            )
    elif kind == "pending_evidence":
        _exact_keys(effect, ("kind", "reason_code"), path)
        _identifier(effect["reason_code"], f"{path}.reason_code")
    else:
        raise PolicyContractError(
            "unsupported policy effect",
            code="unsupported_contract",
            path=f"{path}.kind",
        )


def _validate_outcomes(kind, value, path, semantic_id):
    _exact_keys(
        value,
        ("on_match", "on_clear", "on_missing", "on_conflict"),
        path,
    )
    effects = value["on_match"]
    if type(effects) is not list or not effects:
        raise PolicyContractError("on_match must be a nonempty effect array", path=f"{path}.on_match")
    effect_bytes = []
    for index, effect in enumerate(effects):
        if (
            type(effect) is dict
            and effect.get("kind") == "valuation_profit_basis"
            and kind != "cyclic_protection"
        ):
            raise PolicyContractError(
                "valuation profit basis is cyclic-only",
                path=f"{path}.on_match[{index}].kind",
            )
        _validate_effect(effect, f"{path}.on_match[{index}]", semantic_id)
        effect_bytes.append(_canonical(effect).encode("utf-8"))
    if tuple(effect_bytes) != tuple(sorted(set(effect_bytes))):
        raise PolicyContractError(
            "effects must be canonically sorted and unique", path=f"{path}.on_match"
        )
    if type(value["on_clear"]) is not list or value["on_clear"]:
        raise PolicyContractError("on_clear must be an empty array", path=f"{path}.on_clear")
    for field in ("on_missing", "on_conflict"):
        if value[field] != "pending_evidence":
            raise PolicyContractError(
                "missing and conflict dispositions must be pending_evidence",
                path=f"{path}.{field}",
            )
    if kind == "cyclic_protection":
        required = (
            any(
                effect.get("kind") == "dimension_cap"
                and effect.get("dimension") == dimension
                and _decimal_parameter(effect.get("maximum"), f"{path}.on_match") == 80
                for effect in effects
            )
            for dimension in ("G", "M")
        )
        has_g, has_m = required
        has_profit = any(effect.get("kind") == "valuation_profit_basis" for effect in effects)
        has_status = any(
            effect.get("kind") == "independent_status"
            and effect.get("status_code") == "cyclic_top"
            for effect in effects
        )
        has_pool = any(effect.get("kind") == "pool_prohibition" for effect in effects)
        if not (has_g and has_m and has_profit and has_status and has_pool):
            raise PolicyContractError(
                "cyclic rule lacks required G/M caps, profit basis, status, or pool restriction",
                path=f"{path}.on_match",
            )
    elif kind == "market_liquidity" and not any(
        effect.get("kind") == "pool_prohibition" and effect.get("pool") == "both"
        for effect in effects
    ):
        raise PolicyContractError(
            "market liquidity rule must prohibit both pools", path=f"{path}.on_match"
        )


def _frozen(value):
    if type(value) is dict:
        return MappingProxyType({key: _frozen(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_frozen(item) for item in value)
    return value


def parse_policy_rule(role: str, rule_id: str, raw: bytes) -> PolicyRule:
    """Parse one detached policy rule; no source authenticity is implied."""
    root = f"{role}.rules.{rule_id}"
    _text(role, "role")
    _text(rule_id, f"{role}.rule_id")
    if role not in _ROLES:
        raise PolicyContractError("unsupported policy role", path="role")
    wire = _load(raw, root)
    _exact_keys(
        wire,
        (
            "schema_version",
            "kind",
            "semantic_id",
            "template_id",
            "inputs",
            "parameters",
            "outcomes",
        ),
        root,
    )
    if wire["schema_version"] != "formal-policy-rule-v1":
        raise PolicyContractError(
            "unsupported rule schema_version",
            code="unsupported_contract",
            path=f"{root}.schema_version",
        )
    kind = wire["kind"]
    if type(kind) is not str:
        raise PolicyContractError("rule kind must be text", path=f"{root}.kind")
    allowed_roles = _RULE_KINDS.get(kind)
    if allowed_roles is None:
        raise PolicyContractError(
            "unsupported rule kind", code="unsupported_contract", path=f"{root}.kind"
        )
    if role not in allowed_roles:
        raise PolicyContractError("rule kind is invalid for role", path=f"{root}.kind")
    _text(wire["semantic_id"], f"{root}.semantic_id")
    if wire["template_id"] not in _TEMPLATES:
        raise PolicyContractError("unsupported template", path=f"{root}.template_id")
    inputs = wire["inputs"]
    if kind == "numeric_redline":
        _exact_keys(inputs, ("value",), f"{root}.inputs")
        _selector(
            inputs["value"], f"{root}.inputs.value", wire["template_id"], expected_kind="feature"
        )
    elif kind in ("boolean_state", "enum_state"):
        _exact_keys(inputs, ("value",), f"{root}.inputs")
        _selector(
            inputs["value"],
            f"{root}.inputs.value",
            wire["template_id"],
            expected_kind="bool" if kind == "boolean_state" else "enum",
        )
    elif kind == "cyclic_protection":
        _exact_keys(
            inputs,
            (
                "current_roe",
                "current_margin",
                "current_profit",
                "annual_roe",
                "annual_margin",
                "annual_profit",
            ),
            f"{root}.inputs",
        )
        for name in ("current_roe", "current_margin", "current_profit"):
            _selector(
                inputs[name],
                f"{root}.inputs.{name}",
                wire["template_id"],
                expected_kind="feature",
            )
        for name in ("annual_roe", "annual_margin", "annual_profit"):
            _selector(
                inputs[name],
                f"{root}.inputs.{name}",
                wire["template_id"],
                expected_kind="annual_series",
            )
    else:
        _exact_keys(inputs, ("market", "calendar"), f"{root}.inputs")
        _selector(
            inputs["market"],
            f"{root}.inputs.market",
            wire["template_id"],
            expected_kind="market_record",
        )
        _selector(
            inputs["calendar"],
            f"{root}.inputs.calendar",
            wire["template_id"],
            expected_kind="calendar_record",
        )
    _validate_parameters(
        kind, wire["parameters"], f"{root}.parameters", wire["semantic_id"]
    )
    _validate_outcomes(
        kind, wire["outcomes"], f"{root}.outcomes", wire["semantic_id"]
    )
    return PolicyRule(
        role,
        rule_id,
        wire["kind"],
        wire["semantic_id"],
        wire["template_id"],
        _frozen(wire["inputs"]),
        _frozen(wire["parameters"]),
        _frozen(wire["outcomes"]),
    )


def iter_rule_selectors(rule: PolicyRule) -> tuple[Mapping[str, object], ...]:
    if type(rule) is not PolicyRule:
        raise PolicyContractError("exact PolicyRule required", path="rule")
    return tuple(rule.inputs[key] for key in sorted(rule.inputs))


def parse_policy_contract(children: Mapping[str, bytes]) -> ParsedPolicyContract:
    """Parse all four detached policy children without authenticating their source."""
    _exact_keys(children, _ROLES, "children")
    parsed_children = {}
    role_versions = {}
    evidence_categories = {}
    rules = []
    semantic_paths = {}
    shared_purpose = None
    wrapper_fields = (
        "registry_role",
        "schema_version",
        "purpose",
        "registry_version",
        "source_evidence_categories",
        "rules",
    )
    execution_fields = ("schema_version", "role", "rule_ids")
    for role in _ROLES:
        child_path = f"children.{role}"
        wrapper = _load(children[role], child_path)
        _exact_keys(wrapper, wrapper_fields, child_path)
        if wrapper["registry_role"] != role:
            raise PolicyContractError(
                "policy wrapper role mismatch", path=f"{child_path}.registry_role"
            )
        if wrapper["schema_version"] != "formal-scoring-policy-v1":
            raise PolicyContractError(
                "unsupported policy wrapper schema_version",
                code="unsupported_contract",
                path=f"{child_path}.schema_version",
            )
        purpose = _text(wrapper["purpose"], f"{child_path}.purpose")
        if shared_purpose is None:
            shared_purpose = purpose
        elif purpose != shared_purpose:
            raise PolicyContractError(
                "all policy wrapper purposes must agree", path=f"{child_path}.purpose"
            )
        role_versions[role] = _text(
            wrapper["registry_version"], f"{child_path}.registry_version"
        )
        evidence_categories[role] = _text_array(
            wrapper["source_evidence_categories"],
            f"{child_path}.source_evidence_categories",
        )
        raw_rules = wrapper["rules"]
        if type(raw_rules) is not dict or not raw_rules:
            raise PolicyContractError(
                "rules must be a nonempty object", path=f"{child_path}.rules"
            )
        for rule_id, rule_wire in raw_rules.items():
            _text(rule_id, f"{child_path}.rules.rule_id")
            if type(rule_wire) is not dict or not rule_wire:
                raise PolicyContractError(
                    "every rule must be a nonempty object",
                    path=f"{child_path}.rules.{rule_id}",
                )
        execution = raw_rules.get("execution_contract")
        if execution is None:
            raise PolicyContractError(
                "execution_contract entry is required",
                path=f"{child_path}.rules.execution_contract",
            )
        execution_path = f"{child_path}.rules.execution_contract"
        _exact_keys(execution, execution_fields, execution_path)
        if execution["schema_version"] != "formal-policy-execution-contract-v1":
            raise PolicyContractError(
                "unsupported execution contract schema_version",
                code="unsupported_contract",
                path=f"{execution_path}.schema_version",
            )
        if execution["role"] != role:
            raise PolicyContractError(
                "execution contract role mismatch", path=f"{execution_path}.role"
            )
        active_ids = _ordered_texts(
            execution["rule_ids"], f"{execution_path}.rule_ids"
        )
        if "execution_contract" in active_ids:
            raise PolicyContractError(
                "execution contract cannot activate itself",
                path=f"{execution_path}.rule_ids",
            )
        for rule_id in active_ids:
            rule_wire = raw_rules.get(rule_id)
            if type(rule_wire) is not dict:
                raise PolicyContractError(
                    "active rule_id is missing from this role",
                    path=f"{execution_path}.rule_ids",
                )
            rule = parse_policy_rule(role, rule_id, _canonical(rule_wire).encode("utf-8"))
            semantic_key = (rule.template_id, rule.semantic_id)
            if semantic_key in semantic_paths:
                raise PolicyContractError(
                    "semantic_id is duplicated for this template across active roles",
                    path=f"{role}.rules.{rule_id}.semantic_id",
                )
            semantic_paths[semantic_key] = f"{role}.rules.{rule_id}.semantic_id"
            rules.append(rule)
        parsed_children[role] = wrapper
    rules.sort(key=lambda rule: (rule.role, rule.rule_id))
    canonical_json = _canonical(
        {
            "schema_version": "formal-policy-parsed-v1",
            "children": parsed_children,
        }
    ).encode("utf-8")
    return ParsedPolicyContract(
        tuple(rules),
        MappingProxyType(role_versions),
        MappingProxyType(evidence_categories),
        canonical_json,
    )
