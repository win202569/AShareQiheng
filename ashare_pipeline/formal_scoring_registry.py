"""V3 scoring definitions bound to a verified nine-child registry graph.

The v1 adapter ranks an already-derived V6 feature. Its original formula remains
inspectable; this module does not invent financial equivalents or execute policy.
Official input is exclusively the scoring child of an exact verified bundle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Literal
import weakref

from .formal_feature_contract import FormalFeatureSlot, SignedFormalFeatureRegistry
from .formal_registry_manifest import VerifiedRegistryBundle


class RegistryValidationError(ValueError):
    """A scoring contract or its signed graph proof is incomplete or invalid."""


_TEMPLATES = ("general_nonfinancial", "bank", "broker", "insurance", "real_estate")
_DIMENSIONS = ("G", "V", "M", "EQ", "FS", "CA", "T")
_WEIGHTS = tuple(map(Decimal, ("0.18", "0.18", "0.18", "0.12", "0.08", "0.16", "0.10")))
_INTERNAL = (("0.35", "0.25", "0.25", "0.15"), ("0.45", "0.25", "0.30"),
    ("0.40", "0.30", "0.30"), ("0.35", "0.25", "0.20", "0.20"),
    ("0.40", "0.35", "0.25"), ("0.35", "0.30", "0.20", "0.15"), ("0.35", "0.25", "0.25", "0.15"))
_SLOTS = (
    ("operating_profit_per_share_cagr_3y", "operating_profit_per_share_yoy", "operating_revenue_cagr_3y", "operating_revenue_yoy"),
    ("normalized_earnings_yield", "normalized_free_cash_flow_yield", "enterprise_value_or_sustainable_roe"),
    ("return_persistence", "margin_persistence", "cash_conversion_or_asset_efficiency"),
    ("cash_flow_to_operating_profit", "accrual_quality", "core_profit_share", "working_capital_quality"),
    ("leverage_or_regulatory_capital", "liquidity_or_interest_coverage", "asset_or_contingent_risk"),
    ("return_persistence", "incremental_capital_return", "shareholder_return_and_dilution", "capital_discipline"),
    ("historical_valuation", "price_trend_and_volatility", "expectation_change", "quantified_event_and_liquidity"),
)
_POLICY_ROLES = ("cyclic", "redline", "status", "event")
_ROLES = ("source", "mapping", "feature", "scoring", "industry", *_POLICY_ROLES)


def _keys(value, expected, label):
    if type(value) is not dict:
        raise RegistryValidationError(f"{label} must be an object")
    missing, extra = set(expected) - set(value), set(value) - set(expected)
    if missing or extra:
        raise RegistryValidationError(f"{label}: missing {sorted(missing)}; unknown {sorted(extra)}")


def _text(value, label):
    if type(value) is not str or not value or value != value.strip():
        raise RegistryValidationError(f"{label} must be a nonempty trimmed string")
    return value


def _texts(value, label, *, allow_empty=False):
    if type(value) is not list or (not value and not allow_empty):
        raise RegistryValidationError(f"{label} must be an explicit array")
    result = tuple(_text(item, label) for item in value)
    if len(set(result)) != len(result):
        raise RegistryValidationError(f"{label} must be unique")
    return result


def _hash(value, label):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RegistryValidationError(f"{label} must be a SHA-256")
    return value


def _decimal(value, label):
    _text(value, label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise RegistryValidationError(f"{label} must be a decimal string") from error
    if not parsed.is_finite() or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is None:
        raise RegistryValidationError(f"{label} must be a finite nonnegative decimal string")
    return parsed


def _canonical(value):
    # JSON numbers are parsed as Decimal, never rounded through binary floats.
    if type(value) is dict:
        return "{" + ",".join(_canonical(k) + ":" + _canonical(value[k]) for k in sorted(value)) + "}"
    if type(value) is list:
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    if type(value) is Decimal:
        if not value.is_finite():
            raise RegistryValidationError("nonfinite JSON")
        return str(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _load(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RegistryValidationError("duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise RegistryValidationError(f"nonfinite JSON {value}")

    if type(raw) is not bytes:
        raise RegistryValidationError("canonical JSON must be immutable UTF-8 bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_float=Decimal, parse_constant=invalid)
        if type(value) is not dict or _canonical(value).encode("utf-8") != raw:
            raise RegistryValidationError("registry must be a canonical JSON object")
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise RegistryValidationError(f"invalid canonical JSON: {error}") from error
    return value


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if type(value) is list:
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True, slots=True)
class RegistryApproval:
    purpose: Literal["test", "official"]
    approved_content_sha256: str | None
    approval_id: str | None

    @classmethod
    def for_test_fixture(cls):
        return cls("test", None, None)


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    dimension: Literal["G", "V", "M", "EQ", "FS", "CA", "T"]
    internal_weight: Decimal
    direction: Literal["higher", "lower"]
    required_feature_keys: tuple[str, ...]
    formula_version: str
    field_map_version: str
    denominator_rule: str | None
    formula: Mapping[str, str]
    original_formula: Mapping[str, object]
    field_map: Mapping[str, str]
    unit_rule: str
    period_rule: tuple[str, ...]
    invalid_denominator_rule: str
    equivalence_description: str
    source_evidence_categories: tuple[str, ...]
    policy_refs: tuple[Mapping[str, str], ...]


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    template_id: str
    metrics: Mapping[str, tuple[MetricDefinition, ...]]


@dataclass(frozen=True, slots=True)
class RedlineDefinition:
    rule_id: str
    policy_role: str
    registry_hash: str
    registry_version: str
    source_evidence_categories: tuple[str, ...]
    rule: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class StatusRule(RedlineDefinition):
    pass


def _feature_slots(feature_registry, bundle):
    if type(feature_registry) is not SignedFormalFeatureRegistry:
        raise RegistryValidationError("official feature vocabulary must be an exact sealed SignedFormalFeatureRegistry")
    feature_registry.require_release_eligible()
    feature = bundle.blob("feature")
    if (feature_registry.canonical_json != feature.canonical_json or feature_registry.registry_hash != feature.registry_hash
        or feature_registry.source_registry_hash != bundle.blob("source").registry_hash
        or feature_registry.mapping_registry_hash != bundle.blob("mapping").registry_hash):
        raise RegistryValidationError("feature vocabulary differs from registry manifest graph")
    return {t: {slot.slot_id: slot for slot in feature_registry.slots_for_template(t)} for t in _TEMPLATES}


def _graph(bundle):
    if type(bundle) is not VerifiedRegistryBundle:
        raise RegistryValidationError("official scoring requires an exact verified registry bundle")
    bundle.require_official()
    result = {}
    for role in _ROLES:
        blob = bundle.blob(role)
        digest = hashlib.sha256(blob.canonical_json).hexdigest()
        if digest != blob.registry_hash or digest != getattr(bundle.manifest, role + "_registry_hash"):
            raise RegistryValidationError(f"registry manifest {role} hash mismatch")
        result[role] = digest
    return result


def _policies(scoring, bundle, purpose):
    contracts = scoring["policy_contracts"]
    _keys(contracts, _POLICY_ROLES, "policy_contracts")
    if purpose == "test":
        _keys(scoring["fixture_policies"], _POLICY_ROLES, "fixture_policies")
    policies = {}
    for role in _POLICY_ROLES:
        contract = contracts[role]
        _keys(contract, ("registry_hash", "registry_version", "source_evidence_categories"), f"policy_contracts.{role}")
        digest = _hash(contract["registry_hash"], "policy registry_hash")
        raw = bundle.blob(role).canonical_json if bundle is not None else _canonical(scoring["fixture_policies"][role]).encode()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RegistryValidationError(f"policy {role} registry_hash differs from manifest child")
        policy = _load(raw)
        _keys(policy, ("registry_role", "schema_version", "purpose", "registry_version", "source_evidence_categories", "rules"), f"policy {role}")
        if policy["registry_role"] != role or policy["schema_version"] != "formal-scoring-policy-v1" or policy["purpose"] != purpose:
            raise RegistryValidationError(f"policy {role} role, version, or purpose mismatch")
        version = _text(policy["registry_version"], "policy registry_version")
        categories = _texts(policy["source_evidence_categories"], "policy source_evidence_categories")
        if version != contract["registry_version"] or categories != _texts(contract["source_evidence_categories"], "policy source_evidence_categories"):
            raise RegistryValidationError(f"policy {role} version or categories mismatch")
        if type(policy["rules"]) is not dict or not policy["rules"]:
            raise RegistryValidationError(f"policy {role} rules must be nonempty")
        for key, rule in policy["rules"].items():
            _text(key, "policy rule_id")
            if type(rule) is not dict or not rule:
                raise RegistryValidationError("policy rule must be an explicit object")
        policies[role] = policy
    return policies


def _rule(reference, policies, contracts, allowed_roles, cls=StatusRule):
    _keys(reference, ("policy_role", "rule_id"), "policy reference")
    role, rule_id = reference["policy_role"], reference["rule_id"]
    _text(role, "policy_role")
    _text(rule_id, "rule_id")
    if role not in allowed_roles or rule_id not in policies[role]["rules"]:
        raise RegistryValidationError("policy role or rule_id reference is not registered")
    policy = policies[role]
    return cls(rule_id, role, contracts[role]["registry_hash"], policy["registry_version"],
        tuple(policy["source_evidence_categories"]), _freeze(policy["rules"][rule_id]))


def _formula_requirements(formula):
    periods, ops = set(), set()

    def visit(node):
        ops.add(node["op"])
        if node["op"] == "fact":
            periods.add(node["period_key"])
        for key in ("left", "right"):
            if key in node:
                visit(node[key])
        for item in node.get("items", []):
            visit(item)

    visit(formula)
    denominator = {
        (False, False): "not_applicable",
        (True, False): "nonzero",
        (False, True): "positive_endpoints",
        (True, True): "nonzero_divisors_and_positive_cagr_endpoints",
    }[("divide" in ops, "cagr" in ops)]
    return tuple(sorted(periods)), denominator


def _metric(wire, template_id, dimension, metric_id, weight, slots, policies, contracts):
    expected = {field.name for field in fields(MetricDefinition)} - {"original_formula"}
    _keys(wire, expected, f"metric {template_id}.{dimension}.{metric_id}")
    if wire["metric_id"] != metric_id or wire["dimension"] != dimension or _decimal(wire["internal_weight"], "internal_weight") != weight:
        raise RegistryValidationError("metric slot identity or internal_weight differs from V3")
    if wire["direction"] not in ("higher", "lower"):
        raise RegistryValidationError("metric direction must be higher or lower")
    keys = _texts(wire["required_feature_keys"], "required_feature_keys")
    _keys(wire["formula"], ("op", "feature_key"), "formula")
    _keys(wire["field_map"], ("value",), "field_map")
    if len(keys) != 1 or wire["formula"] != {"op": "feature", "feature_key": keys[0]} or wire["field_map"]["value"] != keys[0]:
        raise RegistryValidationError("formula and field_map must reference the sole required feature key")
    slot = slots.get(keys[0])
    if slot is None or slot.template_id != template_id or slot.dimension != dimension or slot.required is not True:
        raise RegistryValidationError("required feature key is absent or incompatible within this template")
    original = slot.to_dict()["formula"]
    periods, denominator = _formula_requirements(original)
    if (_text(wire["formula_version"], "formula_version") != slot.formula_version
        or _text(wire["unit_rule"], "unit_rule") != slot.unit
        or _texts(wire["period_rule"], "period_rule") != periods
        or wire["denominator_rule"] != denominator or wire["invalid_denominator_rule"] != "block"):
        raise RegistryValidationError("formula_version, unit_rule, period_rule or denominator_rule differs from signed feature formula")
    _text(wire["field_map_version"], "field_map_version")
    _text(wire["equivalence_description"], "equivalence_description")
    _texts(wire["source_evidence_categories"], "source_evidence_categories")
    if type(wire["policy_refs"]) is not list or not wire["policy_refs"]:
        raise RegistryValidationError("metric policy_refs must be explicit")
    for reference in wire["policy_refs"]:
        _rule(reference, policies, contracts, _POLICY_ROLES)
    values = {key: _freeze(value) for key, value in wire.items()}
    values.update(internal_weight=weight, original_formula=_freeze(original))
    return MetricDefinition(**values)


def _parse(raw, approval, bundle, feature_registry):
    wrapper = _load(raw)
    _keys(wrapper, ("registry_role", "schema_version", "descriptors", "scoring"), "scoring wrapper")
    if wrapper["registry_role"] != "scoring" or wrapper["schema_version"] != "formal-scoring-registry-v1":
        raise RegistryValidationError("unsupported scoring wrapper")
    if type(wrapper["descriptors"]) is not list:
        raise RegistryValidationError("descriptors must be an array")
    scoring = wrapper["scoring"]
    if type(scoring) is not dict or scoring.get("purpose") not in ("test", "official"):
        raise RegistryValidationError("scoring purpose must be test or official")
    purpose = scoring["purpose"]
    expected = {"contract_version", "purpose", "dimension_weights", "internal_weights", "templates", "policy_contracts",
        "cyclic_rule", "redlines", "status_rules", "market_liquidity_rule"}
    if purpose == "test":
        expected |= {"fixture_feature_slots", "fixture_policies"}
    _keys(scoring, expected, "scoring")
    if scoring["contract_version"] != "V3":
        raise RegistryValidationError("scoring contract_version must be V3")
    if type(approval) is not RegistryApproval or approval.purpose != purpose:
        raise RegistryValidationError("official or test approval purpose differs from content")
    digest = hashlib.sha256(raw).hexdigest()
    if purpose == "official":
        role_hashes = _graph(bundle)
        if (approval.approved_content_sha256 != digest or type(approval.approved_content_sha256) is not str
            or _text(approval.approval_id, "approval_id") != bundle.manifest.approval_id):
            raise RegistryValidationError("official approval hash or approval_id mismatch")
        if raw != bundle.blob("scoring").canonical_json:
            raise RegistryValidationError("scoring bytes differ from registry manifest")
        slots = _feature_slots(feature_registry, bundle)
    else:
        if bundle is not None or approval.approved_content_sha256 is not None or approval.approval_id is not None or feature_registry is not None:
            raise RegistryValidationError("test fixture cannot use an official bundle or approval")
        role_hashes = {}
        values = scoring["fixture_feature_slots"]
        if type(values) is not list or not values:
            raise RegistryValidationError("fixture_feature_slots must be explicit")
        slots = {t: {} for t in _TEMPLATES}
        for value in values:
            slot = FormalFeatureSlot.from_dict(value)
            if slot.slot_id in slots[slot.template_id]:
                raise RegistryValidationError("duplicate fixture feature slot")
            slots[slot.template_id][slot.slot_id] = slot
    _keys(scoring["dimension_weights"], _DIMENSIONS, "dimension_weights")
    weights = {d: _decimal(scoring["dimension_weights"][d], "dimension_weights") for d in _DIMENSIONS}
    if tuple(weights.values()) != _WEIGHTS or sum(weights.values()) != Decimal("1.00"):
        raise RegistryValidationError("dimension_weights must match exact V3 weights")
    _keys(scoring["internal_weights"], _DIMENSIONS, "internal_weights")
    internal = {}
    for d, expected_weights in zip(_DIMENSIONS, _INTERNAL):
        values = scoring["internal_weights"][d]
        if type(values) is not list:
            raise RegistryValidationError("internal_weights must be arrays")
        internal[d] = tuple(_decimal(w, "internal_weights") for w in values)
        if internal[d] != tuple(map(Decimal, expected_weights)):
            raise RegistryValidationError("internal_weights differ from V3")
    policies = _policies(scoring, bundle, purpose)
    contracts = scoring["policy_contracts"]
    _keys(scoring["templates"], _TEMPLATES, "templates")
    templates = {}
    for t in _TEMPLATES:
        template = scoring["templates"][t]
        _keys(template, ("template_id", "metrics"), "template")
        if template["template_id"] != t:
            raise RegistryValidationError("template_id mismatch")
        _keys(template["metrics"], _DIMENSIONS, "template metrics")
        metrics = {}
        for d, metric_ids in zip(_DIMENSIONS, _SLOTS):
            values = template["metrics"][d]
            if type(values) is not list or len(values) != len(metric_ids):
                raise RegistryValidationError(f"template {t}.{d} must contain every V3 slot")
            metrics[d] = tuple(_metric(w, t, d, m, weight, slots[t], policies, contracts)
                for w, m, weight in zip(values, metric_ids, internal[d]))
        templates[t] = TemplateDefinition(t, MappingProxyType(metrics))
    cyclic = _rule(scoring["cyclic_rule"], policies, contracts, ("cyclic",))
    cyclic_wire = policies["cyclic"]["rules"][cyclic.rule_id]
    _keys(cyclic_wire, ("secondary_industries",), "cyclic classification")
    industries = frozenset(_texts(cyclic_wire["secondary_industries"], "cyclic secondary_industries", allow_empty=True))
    references = {}
    for name, roles, cls in (("redlines", ("redline",), RedlineDefinition), ("status_rules", ("status", "event"), StatusRule)):
        if type(scoring[name]) is not list or not scoring[name]:
            raise RegistryValidationError(f"{name} must be explicit nonempty rules")
        rules = tuple(_rule(ref, policies, contracts, roles, cls) for ref in scoring[name])
        if len({(rule.policy_role, rule.rule_id) for rule in rules}) != len(rules) or {r.policy_role for r in rules} != set(roles):
            raise RegistryValidationError(f"{name} requires unique rules for every role")
        references[name] = rules
    market = _rule(scoring["market_liquidity_rule"], policies, contracts, ("status",))
    return dict(contract_version="V3", content_sha256=digest, templates=MappingProxyType(templates),
        dimension_weights=MappingProxyType(weights), internal_weights=MappingProxyType(internal),
        cyclic_secondary_industries=industries, cyclic_rule=cyclic, market_liquidity_rule=market,
        policy_contracts=_freeze(contracts), approval=RegistryApproval(approval.purpose, approval.approved_content_sha256, approval.approval_id),
        registry_manifest_hash=bundle.manifest.manifest_hash if bundle is not None else None,
        role_hashes=MappingProxyType(role_hashes), **references)


def _trusted_registry():
    seals = {}

    def fingerprint(value):
        if type(value) in (str, bytes, int, bool, Decimal, type(None)):
            return (type(value), value)
        if type(value) in (tuple, frozenset):
            return (type(value), tuple(fingerprint(v) for v in (sorted(value) if type(value) is frozenset else value)))
        if type(value) is MappingProxyType:
            return (MappingProxyType, tuple((fingerprint(k), fingerprint(v)) for k, v in value.items()))
        if type(value) in (FormalScoringRegistry, RegistryApproval, TemplateDefinition, MetricDefinition, RedlineDefinition, StatusRule):
            return (type(value), tuple(fingerprint(object.__getattribute__(value, f.name)) for f in fields(value)))
        raise RegistryValidationError("registry contains forged or mutable records")

    def sealed(registry):
        record = seals.get(id(registry))
        try:
            valid = type(registry) is FormalScoringRegistry and record is not None and record[0]() is registry and record[1] == fingerprint(registry)
        except (AttributeError, TypeError, ValueError, RecursionError):
            valid = False
        if not valid:
            raise RegistryValidationError("scoring registry is forged, copied, or mutated")
        return record

    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
    class FormalScoringRegistry:
        contract_version: str
        content_sha256: str
        templates: Mapping[str, TemplateDefinition]
        dimension_weights: Mapping[str, Decimal]
        internal_weights: Mapping[str, tuple[Decimal, ...]]
        cyclic_secondary_industries: frozenset[str]
        redlines: tuple[RedlineDefinition, ...]
        status_rules: tuple[StatusRule, ...]
        cyclic_rule: StatusRule
        market_liquidity_rule: StatusRule
        policy_contracts: Mapping[str, Mapping[str, object]]
        approval: RegistryApproval
        registry_manifest_hash: str | None
        role_hashes: Mapping[str, str]

        def __init__(self, *args, **kwargs):
            raise RegistryValidationError("FormalScoringRegistry requires load_formal_registry")

        def template_for(self, template_id):
            sealed(self)
            if type(template_id) is not str or template_id not in self.templates:
                raise RegistryValidationError("unknown template_id")
            return self.templates[template_id]

        def require_official(self, registry_bundle):
            record = sealed(self)
            if self.approval.purpose != "official":
                raise RegistryValidationError("test registry cannot run official scoring")
            try:
                hashes = _graph(registry_bundle)
                if registry_bundle.manifest.manifest_hash != self.registry_manifest_hash or hashes != dict(self.role_hashes):
                    raise RegistryValidationError("registry manifest graph differs from loaded scoring registry")
                if registry_bundle.blob("scoring").canonical_json != record[2]:
                    raise RegistryValidationError("scoring content differs from registry manifest")
                _feature_slots(record[3], registry_bundle)
            except (ValueError, TypeError, AttributeError) as error:
                raise RegistryValidationError(f"official registry manifest proof failed: {error}") from error

    def load_formal_registry(source, approval, *, feature_registry=None):
        try:
            bundle = source if type(source) is VerifiedRegistryBundle else None
            if type(approval) is not RegistryApproval:
                raise RegistryValidationError("approval must be an exact RegistryApproval")
            if approval.purpose == "official" and bundle is None:
                raise RegistryValidationError("official scoring must load from registry_bundle.blob('scoring')")
            raw = bundle.blob("scoring").canonical_json if bundle is not None else source if type(source) is bytes else Path(source).read_bytes()
            values = _parse(raw, approval, bundle, feature_registry)
            registry = object.__new__(FormalScoringRegistry)
            for name, value in values.items():
                object.__setattr__(registry, name, value)
            identity = id(registry)
            seals[identity] = (weakref.ref(registry, lambda _: seals.pop(identity, None)), fingerprint(registry), raw, feature_registry)
            if bundle is not None:
                registry.require_official(bundle)
            return registry
        except (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError) as error:
            raise RegistryValidationError(f"invalid scoring registry: {error}") from error

    return FormalScoringRegistry, load_formal_registry


FormalScoringRegistry, load_formal_registry = _trusted_registry()
del _trusted_registry

__all__ = ["FormalScoringRegistry", "TemplateDefinition", "MetricDefinition", "RedlineDefinition",
    "StatusRule", "RegistryApproval", "RegistryValidationError", "load_formal_registry"]
