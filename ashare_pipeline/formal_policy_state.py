"""Internal policy state selections from current, authenticated Context reads."""

from __future__ import annotations

import json
import weakref
from types import MappingProxyType

from .formal_context_repository import FormalContextRepository
from .formal_metric_context import (
    FormalMetricContextRepository, _require_authentic_metric_context_repository,
)
from .formal_policy_registry import _read_authenticated_policy_registry
from .formal_policy_values import (
    PolicyIntegrityError, PolicyPreconditionError, _policy_value_operations, canonical_bytes, digest,
)
from .formal_universe import canonical_security_id


_FREEZE = "2026-08-31T07:00:00+00:00"
_STATE_KINDS = frozenset(("security_state", "regulatory_state"))


def read_flag(flags: tuple[dict, ...], flag_id: str) -> bool | None:
    """An absent entry is not an observed false state."""
    matches = [item for item in flags if item["flag_id"] == flag_id]
    if not matches:
        return None
    if len(matches) != 1 or type(matches[0]["active"]) is not bool:
        raise ValueError("flag must have one explicit boolean observation")
    return matches[0]["active"]


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    return tuple(map(_freeze, value)) if type(value) is list else value


def _install_state():
    repositories, selections = {}, {}
    context_type = FormalContextRepository
    companion_type = FormalMetricContextRepository
    companion_init = companion_type.__init__
    check_context = _require_authentic_metric_context_repository
    read_many = context_type.get_verified_many
    read_policy = _read_authenticated_policy_registry
    parse_value, serialize_value, check_values = _policy_value_operations()
    captured = tuple((name, value) for name, value in globals().items()
                     if callable(value) and name != "_install_state")

    def interfaces():
        check_values()
        if any(globals().get(name) is not value for name, value in captured):
            raise PolicyIntegrityError("policy state calculation dependency changed")
        for cls, methods in own_methods:
            if set(vars(cls)) != set(methods) or any(vars(cls)[key] is not value for key, value in methods.items()):
                raise PolicyIntegrityError("policy state interface changed")
        if context_type.get_verified_many is not read_many or companion_type.__init__ is not companion_init:
            raise PolicyIntegrityError("policy state retained read dependency changed")

    def dependencies(repository):
        interfaces()
        saved = repositories.get(id(repository))
        if type(repository) is not FormalPolicyStateRepository or saved is None or saved[0]() is not repository:
            raise PolicyIntegrityError("state repository is forged or copied")
        _, context, _ = check_context(saved[1])
        return context

    def record(selection):
        interfaces()
        saved = selections.get(id(selection))
        if type(selection) is not PolicyStateSelection or saved is None or saved[0]() is not selection:
            raise PolicyIntegrityError("state selection is forged or copied")
        return saved

    class SelectionMeta(type):
        def __setattr__(cls, name, value):
            if name in {"__getattribute__", "__bases__"}:
                raise TypeError("state selection lookup and inheritance are immutable")
            return super().__setattr__(name, value)

        def __delattr__(cls, name):
            if name in {"__getattribute__", "__bases__"}:
                raise TypeError("state selection lookup and inheritance are immutable")
            return super().__delattr__(name)

    class PolicyStateSelection(metaclass=SelectionMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("state selections require authenticated repository reads")

        def __getattribute__(self, name):
            record(self)
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            payload = json.loads(record(self)[1])
            if name == "values":
                return MappingProxyType({key: parse_value(value) for key, value in payload[name].items()})
            if name not in {"lineage", "selection_hash"}:
                raise AttributeError(name)
            return _freeze(payload[name])

        def recheck(self):
            saved = record(self)
            current = select(saved[2], **saved[3])
            if record(current)[1] != saved[1]:
                raise PolicyIntegrityError("state selection is no longer current")

        def __copy__(self):
            raise TypeError("state selections cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("state selections cannot be copied")

    def select(self, security_id, as_of_utc, *, template_id, policy_registry):
        context = dependencies(self)
        if (type(security_id) is not str or canonical_security_id(security_id) != security_id
                or type(as_of_utc) is not str or as_of_utc != _FREEZE
                or type(template_id) is not str):
            raise PolicyPreconditionError("state selection requires canonical security, freeze and genuine registry")
        policy = read_policy(policy_registry)
        if template_id not in {rule["template_id"] for rule in policy["rules"]}:
            raise PolicyPreconditionError("state template is not signed")
        rules = [rule for rule in policy["rules"] if rule["template_id"] == template_id
                 and any(selector.get("context_kind") in _STATE_KINDS for selector in rule["inputs"].values())]
        selectors, bindings = {}, {}
        manifest = {(item["role"], item["rule_id"], item["input_path"]): item
                    for item in policy["binding_manifest"]}
        for rule in rules:
            for name, selector in rule["inputs"].items():
                if selector.get("context_kind") not in _STATE_KINDS:
                    continue
                key = digest(selector)
                selectors[key] = selector
                bindings[key] = manifest[(rule["role"], rule["rule_id"], "inputs." + name)]
        groups = sorted({(s["context_kind"], s["scope_key"]) for s in selectors.values()})
        security_ids = tuple(sorted({security_id}))

        def read():
            result = {}
            for kind, scope in groups:
                selected = read_many(context, kind, scope, security_ids, as_of_utc, policy["registry_manifest_hash"])
                fact = selected[security_id]
                result[(kind, scope)] = None if fact is None else fact.to_dict()
            return result

        factors = read()
        values, entries = {}, {}
        for key, selector in sorted(selectors.items()):
            fact = factors[(selector["context_kind"], selector["scope_key"])]
            binding = bindings[key]
            if fact is not None and fact["evidence"]["descriptor_id"] != selector["descriptor_id"]:
                raise PolicyIntegrityError("selected Context descriptor differs from signed selector")
            request = dict(security_id=security_id, security_ids=list(security_ids),
                context_kind=selector["context_kind"], scope_key=selector["scope_key"],
                as_of_utc=as_of_utc, registry_manifest_hash=policy["registry_manifest_hash"],
                descriptor_id=selector["descriptor_id"], descriptor=binding["descriptor"])
            entry = dict(selector=selector, request=request, factor=fact,
                rule_ids=sorted(rule["rule_id"] for rule in rules
                    if any(digest(s) == key for s in rule["inputs"].values())))
            entry_hash = digest(entry)
            raw = None if fact is None else (fact["value"][selector["field"]]
                if selector["context_kind"] == "security_state"
                else read_flag(tuple(fact["value"]["flags"]), selector["entry_id"]))
            reason = "state_entry_missing" if raw is None else None
            value = dict(state="missing" if reason else "value", value=raw,
                value_type=selector["expected_type"], unit=None, evidence_hashes=[entry_hash],
                pending=[] if reason is None else [dict(origin="runtime", code=reason,
                    rule_id=None, evidence_hashes=[entry_hash])])
            values[key] = serialize_value(parse_value(value))
            entries[key] = dict(entry, entry_hash=entry_hash)
        # Close cross-kind correction/absence races after every factor has been consumed.
        if factors != read():
            raise PolicyIntegrityError("Context state changed during selection")
        dependencies(self)
        if read_policy(policy_registry) != policy:
            raise PolicyIntegrityError("policy registry changed during state selection")
        payload = dict(values=values, lineage=dict(security_id=security_id, exchange=security_id[:2],
            template_id=template_id, as_of_utc=as_of_utc,
            algorithm_version="formal-policy-state-selection-v1", contract_version=policy["contract_version"],
            registry_manifest_hash=policy["registry_manifest_hash"], role_hashes=policy["role_hashes"],
            policy_contract_hash=policy["contract_hash"], rule_ids=sorted(r["rule_id"] for r in rules), entries=entries))
        payload["selection_hash"] = digest(payload)
        result = object.__new__(PolicyStateSelection)
        key = id(result)
        selections[key] = (weakref.ref(result, lambda _: selections.pop(key, None)), canonical_bytes(payload), self,
            dict(security_id=security_id, as_of_utc=as_of_utc, template_id=template_id, policy_registry=policy_registry))
        return result

    class FormalPolicyStateRepository:
        __slots__ = ("__weakref__",)

        def __init__(self, context_repository):
            interfaces()
            if type(self) is not FormalPolicyStateRepository or id(self) in repositories:
                raise PolicyPreconditionError("state repository initialization must be exact and single-use")
            if type(context_repository) is not context_type:
                raise PolicyPreconditionError("genuine Context repository required")
            companion = companion_type(context_repository._state_store, context_repository,
                registry_signature_verifier=context_repository._verifier)
            check_context(companion)
            key = id(self)
            repositories[key] = (weakref.ref(self, lambda _: repositories.pop(key, None)), companion)

        def __copy__(self):
            raise TypeError("state repositories cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("state repositories cannot be copied")

    FormalPolicyStateRepository.select = select
    own_methods = tuple((cls, dict(vars(cls))) for cls in
                        (FormalPolicyStateRepository, PolicyStateSelection, SelectionMeta))
    return FormalPolicyStateRepository, PolicyStateSelection


FormalPolicyStateRepository, PolicyStateSelection = _install_state()
del _install_state

__all__ = ["FormalPolicyStateRepository", "PolicyStateSelection"]
