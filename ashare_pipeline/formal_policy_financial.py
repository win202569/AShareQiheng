"""Internal authenticated policy financial selections; no publication authority."""

from __future__ import annotations

import json
import weakref
from datetime import datetime
from types import MappingProxyType

from . import formal_feature_repository as feature_module
from . import formal_metric_batch_guard as provider_module
from .formal_feature_contract import FormalEvidenceRef
from .formal_financial_features import derive_comparable_quarters, select_visible_formal_facts
from .formal_financial_schema import FormalFinancialFact
from .formal_metric_context import VerifiedMetricIndustryBatch
from .formal_policy_registry import FormalPolicyRegistry
from .formal_policy_values import (
    PolicyIntegrityError, PolicyPreconditionError, PolicyValue, _decimal_text,
    bridge_v6, canonical_bytes, digest,
)
from .state_store import StateStore


# The provider module is fully initialized before this captures its owned type
# and actual methods. There is no first-selection capture of replaceable aliases.
PolicyFeatureState, _feature_dependencies = feature_module._install_policy_projection(provider_module)
del feature_module._install_policy_projection

_BRIDGE = "v6_feature_decimal_bridge_v1"
_FREEZE = "2026-08-31T07:00:00+00:00"


def annual_targets(series_selector):
    expected = tuple(f"{year}-12-31" for year in range(2021, 2026))
    observations = tuple(series_selector["observations"])
    actual = tuple(item["fy_end"] for item in observations)
    if actual != expected:
        raise PolicyPreconditionError("annual observations must be the five distinct signed FY ends")
    return tuple(zip(expected, observations, strict=True))


def _leaves(node, path="formula"):
    if node["op"] == "fact":
        yield path, node
    elif node["op"] in {"minimum", "median"}:
        for index, child in enumerate(node["items"]):
            yield from _leaves(child, f"{path}.items[{index}]")
    else:
        yield from _leaves(node["left"], path + ".left")
        yield from _leaves(node["right"], path + ".right")


def _policy_value(raw, unit, projection_hash, reason=None):
    return dict(state="domain_conflict" if reason == "financial_domain_conflict" else
            "missing" if reason else "value",
        value=None if reason else _decimal_text(bridge_v6(raw)), value_type="decimal", unit=unit,
        evidence_hashes=[projection_hash], pending=[] if reason is None else [dict(
            origin="runtime", code=reason, rule_id=None, evidence_hashes=[projection_hash])])


def _observation(selector, slot, projected, state, fy_end=None):
    """Bind every AST occurrence to actual selected fact periods, never slot names."""
    facts = tuple(FormalFinancialFact.from_dict(w) for w in state["facts"])
    leaves, diagnostics, source_refs = [], [], {}
    bases, annual_ends = set(), set()
    for path, leaf in _leaves(slot["formula"]):
        period = leaf["period_key"]
        candidates = tuple(f for f in facts if f.metric_key == leaf["fact_key"])
        if len(period) == 6 and period.startswith("FY") and period[2:].isdigit():
            end = period[2:] + "-12-31"
            selected = select_visible_formal_facts(
                (f for f in candidates if f.period_kind == "FY" and f.period_end == end), _FREEZE)
            if "fact_selection_tie_conflict" in selected.blockers:
                raise PolicyIntegrityError("policy fact selection has ambiguous leading versions")
            diagnostics.extend(selected.blockers)
            if len(selected.facts) != 1:
                diagnostics.append("financial_domain_conflict" if len(selected.facts) > 1 else "financial_input_missing")
                continue
            actual = selected.facts
        elif (fy_end is None and len(period) == 6 and period[:4].isdigit()
                and period[4] == "Q" and period[5] in "1234"):
            # Use the original V6 endpoint/predecessor semantics for this exact
            # AST occurrence, then retain only its derived quarter components.
            year, quarter = period[:4], int(period[5])
            ends = ("03-31", "06-30", "09-30", "12-31")
            end = year + "-" + ends[quarter - 1]
            predecessor = year + "-" + ends[quarter - 2] if quarter > 1 else None
            selected = select_visible_formal_facts((f for f in candidates if f.period_end == end
                or (f.nature == "duration" and f.period_end == predecessor)), _FREEZE)
            if "fact_selection_tie_conflict" in selected.blockers:
                raise PolicyIntegrityError("policy quarter selection has ambiguous leading versions")
            diagnostics.extend(selected.blockers)
            quarters = derive_comparable_quarters(selected.facts)
            derived = tuple(q for q in quarters.facts if q.quarter_key == period)
            quarter_blockers = set(quarters.blockers)
            requested_ids = {f.id for f in selected.facts if f.period_end == end}
            covered_ids = {identity for q in derived for identity in q.component_fact_ids}
            if requested_ids and requested_ids <= covered_ids:
                quarter_blockers.discard("quarter_missing_prerequisite")
            diagnostics.extend(quarter_blockers)
            if len(derived) != 1:
                diagnostics.append("financial_domain_conflict" if len(derived) > 1 else "financial_input_missing")
                continue
            by_id = {f.id: f for f in selected.facts}
            actual = tuple(by_id[identity] for identity in derived[0].component_fact_ids)
        else:
            diagnostics.append("financial_domain_conflict" if fy_end else "financial_input_missing")
            continue
        for fact in actual:
            wire = fact.to_dict()
            bases.add(wire["accounting_basis"])
            if fy_end is not None:
                annual_ends.add(wire["period_end"])
                previous = str(int(fy_end[:4]) - 1) + "-12-31"
                if (wire["period_end"] != fy_end and not
                        (wire["nature"] == "instant" and wire["period_end"] == previous)):
                    diagnostics.append("financial_domain_conflict")
            if (wire["period_kind"] == "FY" and wire["nature"] == "duration"
                    and wire["period_start"] != wire["period_end"][:4] + "-01-01"):
                diagnostics.append("financial_domain_conflict")
            leaves.append(dict(ast_path=path, formal_fact_id=wire["id"],
                fact_key=leaf["fact_key"], period_key=period, **{key: wire[key] for key in
                ("security_id", "period_start", "period_end", "period_kind", "nature", "statement",
                 "accounting_basis", "unit", "mapping_version")}))
            ref = FormalEvidenceRef.from_formal_fact(fact).to_dict()
            source_refs[canonical_bytes(ref)] = ref
    if len(bases) > 1 or (fy_end is not None and annual_ends and fy_end not in annual_ends):
        diagnostics.append("financial_domain_conflict")
    raw = projected["value"] if projected else None
    slot_issues = state["slot_issues"][slot["slot_id"]]
    if state["current_receipt_absent"]:
        reason = "current_receipt_absent"
    elif slot_issues or "financial_domain_conflict" in diagnostics:
        reason = "financial_domain_conflict"
    elif projected is None or projected["status"] != "derived":
        missing = (projected or {}).get("missing_reason")
        reason = {"formula_unit_mismatch": "unsupported_unit",
            "formula_zero_denominator": "invalid_denominator",
            "formula_fact_ambiguous": "financial_domain_conflict"}.get(missing, "financial_input_missing")
    else:
        reason = "financial_input_missing" if diagnostics else None
    if projected is not None and (projected["unit"] != selector["expected_unit"]
            or projected["formula_version"] != selector["formula_version"]):
        raise PolicyIntegrityError("policy value differs from its signed selector")
    refs = [source_refs[key] for key in sorted(source_refs)]
    visibility = dict(as_of_utc=_FREEZE,
        minimum_published_precision="date" if any(r["published_precision"] != "timestamp" for r in refs) else
            "timestamp" if refs else None,
        published_at_utc=sorted({r["published_at_utc"] for r in refs}),
        effective_at_utc=sorted({r["effective_at_utc"] for r in refs}))
    record = dict(selector_hash=digest(selector), slot_hash=digest(slot), formula_hash=digest(slot["formula"]),
        formula_version=slot["formula_version"], value=_policy_value(raw, slot["unit"], state["projection_hash"], reason),
        unit=slot["unit"], facts=leaves, issues=[*slot_issues, *sorted(set(diagnostics))],
        source_refs=refs, visibility=visibility, bridge_version=_BRIDGE, projection_hash=state["projection_hash"])
    if fy_end is not None:
        record = dict(fy_end=fy_end, **record)
    return record, dict(original_value=raw, original_value_repr=repr(raw),
        original_projection_hash=state["projection_hash"], bridge_version=_BRIDGE,
        converted_value=record["value"]["value"])


def _install_financial():
    repositories, selections = {}, {}
    feature_type = feature_module.FormalFeatureRepository
    feature_select = feature_type.select_current_verified_policy_feature_state
    feature_check, state_wire = _feature_dependencies, PolicyFeatureState.to_dict
    require_policy, policy_wire = FormalPolicyRegistry.require_verified, FormalPolicyRegistry.to_dict
    require_industry, industry_wire = VerifiedMetricIndustryBatch.require_verified, VerifiedMetricIndustryBatch.to_dict
    read_universe = StateStore.get_verified_formal_frozen_universe
    captured_functions = tuple((name, value) for name, value in globals().items()
                               if callable(value) and name != "_install_financial")

    def interfaces():
        if any(globals().get(name) is not value for name, value in captured_functions):
            raise PolicyIntegrityError("policy financial calculation dependency changed")
        for cls, methods in own_methods:
            if set(vars(cls)) != set(methods) or any(vars(cls)[k] is not v for k, v in methods.items()):
                raise PolicyIntegrityError("policy financial interface changed")

    def dependencies(repository):
        interfaces()
        saved = repositories.get(id(repository))
        if type(repository) is not FormalPolicyFinancialRepository or saved is None or saved[0]() is not repository:
            raise PolicyIntegrityError("financial repository is forged or copied")
        feature_check(saved[1], saved[2])
        return saved[1], saved[2]

    def record(selection):
        interfaces()
        saved = selections.get(id(selection))
        if type(selection) is not PolicyFinancialSelection or saved is None or saved[0]() is not selection:
            raise PolicyIntegrityError("financial selection is forged or copied")
        return saved

    def freeze(value):
        if type(value) is dict:
            if set(value) == {"state", "value", "value_type", "unit", "evidence_hashes", "pending"}:
                return PolicyValue.from_dict(value)
            return MappingProxyType({k: freeze(v) for k, v in value.items()})
        return tuple(map(freeze, value)) if type(value) is list else value

    class SelectionMeta(type):
        def __setattr__(cls, name, value):
            if name in {"__getattribute__", "__bases__"}:
                raise TypeError("financial selection lookup and inheritance are immutable")
            return super().__setattr__(name, value)

        def __delattr__(cls, name):
            if name in {"__getattribute__", "__bases__"}:
                raise TypeError("financial selection lookup and inheritance are immutable")
            return super().__delattr__(name)

    class PolicyFinancialSelection(metaclass=SelectionMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("financial selections require authenticated repository reads")

        def __getattribute__(self, name):
            record(self)
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            payload = json.loads(record(self)[1])
            if name not in {"values", "annual", "lineage", "selection_hash"}:
                raise AttributeError(name)
            return freeze(payload[name])

        def recheck(self):
            saved = record(self)
            current = select(saved[2], **saved[3])
            if record(current)[1] != saved[1]:
                raise PolicyIntegrityError("financial selection is no longer current")

        def __copy__(self):
            raise TypeError("financial selections cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("financial selections cannot be copied")

    def select(self, security_id, as_of_utc, *, template_id, policy_registry, industry_batch):
        feature_repository, provider = dependencies(self)
        if type(policy_registry) is not FormalPolicyRegistry or type(industry_batch) is not VerifiedMetricIndustryBatch:
            raise PolicyPreconditionError("genuine policy registry and industry batch required")
        require_policy(policy_registry)
        require_industry(industry_batch)
        policy, industry = policy_wire(policy_registry), industry_wire(industry_batch)
        frozen = read_universe(feature_repository._store, industry["frozen_input_hash"])
        if (frozen is None or datetime.fromisoformat(frozen.as_of_utc) != datetime.fromisoformat(as_of_utc) or as_of_utc != _FREEZE
                or frozen.registry_manifest_hash != policy["registry_manifest_hash"]
                or frozen.universe_hash != industry["universe_hash"]
                or industry["registry_manifest_hash"] != policy["registry_manifest_hash"]
                or industry["industry_registry_hash"] != policy["role_hashes"]["industry"]
                or set(industry["entries"]) != {m.security_id for m in frozen.members}):
            raise PolicyPreconditionError("financial industry root/frozen/universe identity mismatch")
        entry = industry["entries"].get(security_id)
        if entry is None or any(entry[k] != industry[k] for k in
                ("registry_manifest_hash", "frozen_input_hash", "universe_hash")):
            raise PolicyPreconditionError("financial security is outside the authenticated universe")
        if entry["status"] == "assigned" and entry["template_id"] != template_id:
            raise PolicyPreconditionError("financial template differs from industry assignment")
        applicability = ("applicability_unresolved" if entry["status"] != "assigned" else
            "applicable" if entry["secondary_industry"] in policy["cyclic_secondary_industries"] else "not_applicable")
        rules = [r for r in policy["rules"] if r["template_id"] == template_id
            and (r["kind"] == "numeric_redline" or (r["kind"] == "cyclic_protection" and applicability == "applicable"))]
        rule_ids = tuple(sorted(r["rule_id"] for r in rules))
        state = feature_select(feature_repository, security_id, as_of_utc, template_id=template_id,
            registry_manifest_hash=policy["registry_manifest_hash"], policy_registry=policy_registry, rule_ids=rule_ids)
        wire = state_wire(state)
        slots = {s["slot_id"]: s for s in wire["slots"]}
        projected = {v["slot_id"]: v for v in wire["values"]}
        values, annual, scalar, bridges = {}, {}, {}, {}
        for rule in rules:
            for selector in rule["inputs"].values():
                key = digest(selector)
                if selector["kind"] == "annual_series":
                    records = []
                    for fy_end, observation in annual_targets(selector):
                        leaf_selector = observation["selector"]
                        slot_id = leaf_selector["feature_key"]
                        result, bridge = _observation(leaf_selector, slots[slot_id], projected.get(slot_id), wire, fy_end)
                        records.append(result)
                        bridges[result["selector_hash"]] = bridge
                    annual[key] = records
                elif selector["kind"] == "feature":
                    slot_id = selector["feature_key"]
                    result, bridge = _observation(selector, slots[slot_id], projected.get(slot_id), wire)
                    values[key], scalar[key], bridges[key] = result["value"], result, bridge
        state.recheck()
        dependencies(self)
        require_policy(policy_registry)
        require_industry(industry_batch)
        payload = dict(values=values, annual=annual, lineage=dict(security_id=security_id, template_id=template_id,
            algorithm_version="formal-policy-financial-selection-v1", contract_version=policy["contract_version"],
            registry_manifest_hash=policy["registry_manifest_hash"], role_hashes=policy["role_hashes"],
            policy_contract_hash=policy["contract_hash"], frozen_input_hash=industry["frozen_input_hash"],
            universe_hash=industry["universe_hash"], industry_batch_hash=industry["batch_hash"], as_of_utc=as_of_utc,
            applicability=applicability, rule_ids=list(rule_ids), scalar=scalar, bridges=bridges,
            all_issues=wire["issues"], slot_issues=wire["slot_issues"],
            projection_hash=wire["projection_hash"], input_hash=wire["input_hash"], bundle_hash=wire["bundle_hash"],
            batch_id=wire["batch_id"], current_receipt_absent=wire["current_receipt_absent"]))
        payload["selection_hash"] = digest(payload)
        result = object.__new__(PolicyFinancialSelection)
        key = id(result)
        selections[key] = (weakref.ref(result, lambda _: selections.pop(key, None)), canonical_bytes(payload), self,
            dict(security_id=security_id, as_of_utc=as_of_utc, template_id=template_id,
                 policy_registry=policy_registry, industry_batch=industry_batch))
        return result

    class FormalPolicyFinancialRepository:
        __slots__ = ("__weakref__",)

        def __init__(self, feature_repository, *, current_input_provider):
            if type(self) is not FormalPolicyFinancialRepository or id(self) in repositories:
                raise PolicyPreconditionError("financial repository initialization must be exact and single-use")
            if current_input_provider is None:
                raise PolicyPreconditionError("an explicit matching owned provider is required")
            feature_check(feature_repository, current_input_provider)
            key = id(self)
            repositories[key] = (weakref.ref(self, lambda _: repositories.pop(key, None)),
                                 feature_repository, current_input_provider)

    FormalPolicyFinancialRepository.select = select
    own_methods = tuple((cls, dict(vars(cls))) for cls in (FormalPolicyFinancialRepository, PolicyFinancialSelection, SelectionMeta))
    return FormalPolicyFinancialRepository, PolicyFinancialSelection


FormalPolicyFinancialRepository, PolicyFinancialSelection = _install_financial()
del _install_financial

__all__ = ["FormalPolicyFinancialRepository", "PolicyFinancialSelection"]
