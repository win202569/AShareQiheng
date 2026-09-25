"""Authenticated valuation adapter definitions, without valuation execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Literal
import weakref

from .formal_metric_engine import _scoring_metric_definitions
from .formal_policy_registry import FormalPolicyRegistry
from .formal_registry_manifest import VerifiedRegistryBundle, _load_canonical_object
from .formal_scoring_registry import FormalScoringRegistry


_COVERAGE_KEYS = frozenset(("template_id", "metric_id", "policy_dependency"))
_ADAPTER_KEYS = frozenset(("template_id", "metric_id", "adapter_id", "adapter_version",
    "operation", "profit_semantic_id", "metric_unit", "profit_unit", "output_unit",
    "policy_role", "rule_id", "decimal_contract", "preconditions", "definition_basis"))
_CHILD_KEYS = frozenset(("registry_role", "schema_version", "purpose", "registry_version",
    "coverage", "adapters"))
_PRECONDITIONS = ("exact_units", "finite_decimals", "nonzero_original_current_profit")


@dataclass(frozen=True, slots=True)
class ValuationAdapterDefinition:
    template_id: str
    metric_id: str
    adapter_id: str
    adapter_version: str
    operation: Literal["profit_ratio_rescale_v1"]
    original_definition_hash: str
    profit_semantic_id: str
    metric_unit: str
    profit_unit: str
    output_unit: str
    policy_role: Literal["cyclic"]
    rule_id: str
    decimal_contract: Literal["decimal50-half-even-v1"]
    preconditions: tuple[str, ...]
    definition_basis: str


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")


def _fail(path, message):
    raise ValueError(f"valuation adapter {path}: {message}")


def _text(value, path):
    if type(value) is not str or not value or value != value.strip():
        _fail(path, "requires nonempty trimmed text")
    return value


def _entries(value, keys, path):
    if type(value) is not list:
        _fail(path, "requires an array")
    for index, entry in enumerate(value):
        if type(entry) is not dict or set(entry) != keys:
            _fail(f"{path}[{index}]", "has wrong fields")
    return value


def _install_registry():
    records = {}
    bundle_type, scoring_type, policy_type = VerifiedRegistryBundle, FormalScoringRegistry, FormalPolicyRegistry
    require_bundle, blob_for = bundle_type.require_official, bundle_type.blob
    require_scoring, require_policy = scoring_type.require_official, policy_type.require_verified
    definitions = _scoring_metric_definitions
    canonical, parse = _canonical, _load_canonical_object

    def sources(bundle, scoring, policy):
        if type(bundle) is not bundle_type or type(scoring) is not scoring_type or type(policy) is not policy_type:
            _fail("graph", "requires exact verified source types")
        require_bundle(bundle)
        if bundle.manifest.schema_version != "formal-registry-manifest-v2":
            raise ValueError("valuation_adapter role is unavailable for this manifest version")
        require_scoring(scoring, bundle)
        require_policy(policy)
        if (policy.registry_manifest_hash != bundle.manifest.manifest_hash
                or policy.role_hashes != {role: scoring.role_hashes[role] for role in policy.role_hashes}):
            _fail("graph", "policy and scoring have different roots")
        blob = blob_for(bundle, "valuation_adapter")
        if (hashlib.sha256(blob.canonical_json).hexdigest() != blob.registry_hash
                or blob.registry_hash != bundle.manifest.valuation_adapter_registry_hash):
            _fail("graph", "signed child hash differs from root")
        return blob.canonical_json

    def contract(bundle, scoring, policy):
        raw = sources(bundle, scoring, policy)
        try:
            child = parse(raw, label="valuation adapter registry")
        except ValueError as error:
            _fail("child", str(error))
        if set(child) != _CHILD_KEYS:
            _fail("child", "has wrong fields")
        for field, value in (("registry_role", "valuation_adapter"),
                ("schema_version", "formal-valuation-adapter-registry-v1"),
                ("purpose", "official")):
            if child[field] != value:
                _fail(field, f"must be {value}")
        _text(child["registry_version"], "registry_version")

        metric_definitions = definitions(scoring)
        policy_wire = policy.to_dict()
        dependencies = policy_wire["valuation_dependencies"]
        cyclic_rules = {item["template_id"]: item for item in policy_wire["rules"]
            if item["role"] == "cyclic" and item["semantic_id"] == "cyclic_top"}
        expected = {}
        for template_id, by_metric in metric_definitions.items():
            dependency_index = {item["metric_id"]: item for item in dependencies[template_id]}
            for metric_id, definition in by_metric.items():
                if not metric_id.startswith("V."):
                    continue
                expected[(template_id, metric_id)] = (dependency_index[metric_id],
                    definition, cyclic_rules[template_id]["rule_id"])

        coverage = _entries(child["coverage"], _COVERAGE_KEYS, "coverage")
        actual_coverage = {}
        previous = None
        for index, entry in enumerate(coverage):
            key = (_text(entry["template_id"], f"coverage[{index}].template_id"),
                _text(entry["metric_id"], f"coverage[{index}].metric_id"))
            if previous is not None and key <= previous:
                _fail("coverage", "must be sorted and unique")
            previous = key
            if key not in expected or entry["policy_dependency"] != expected[key][0]["policy_dependency"]:
                _fail(f"coverage[{index}]", "differs from signed cyclic policy")
            actual_coverage[key] = entry
        if set(actual_coverage) != set(expected):
            _fail("coverage", "must cover exactly every V metric")

        adapters = _entries(child["adapters"], _ADAPTER_KEYS, "adapters")
        parsed_adapters = {}
        previous = None
        for index, entry in enumerate(adapters):
            path = f"adapters[{index}]"
            key = (_text(entry["template_id"], path + ".template_id"),
                _text(entry["metric_id"], path + ".metric_id"))
            if previous is not None and key <= previous:
                _fail("adapters", "must be sorted and unique")
            previous = key
            if key not in expected or expected[key][0]["policy_dependency"] != "affected":
                _fail(path, "requires an affected signed dependency")
            dependency, metric_definition, rule_id = expected[key]
            metric_unit = metric_definition["definition"]["unit_rule"]
            required = dict(adapter_id=dependency["adapter_id"],
                adapter_version=dependency["adapter_version"],
                operation="profit_ratio_rescale_v1",
                profit_semantic_id=dependency["profit_semantic_id"],
                metric_unit=metric_unit, profit_unit="CNY", output_unit=metric_unit,
                policy_role="cyclic", rule_id=rule_id,
                decimal_contract="decimal50-half-even-v1",
                preconditions=list(_PRECONDITIONS),
                definition_basis=dependency["definition_basis"])
            for field, value in required.items():
                if type(entry[field]) is not type(value) or entry[field] != value:
                    _fail(path + "." + field, "differs from signed contract")
            for field in ("adapter_id", "adapter_version", "profit_semantic_id", "definition_basis"):
                _text(entry[field], path + "." + field)
            parsed_adapters[key] = ValuationAdapterDefinition(
                **(entry | {"preconditions": tuple(entry["preconditions"])}),
                original_definition_hash=metric_definition["definition_hash"])
        affected = {key for key, (dependency, _, _) in expected.items()
            if dependency["policy_dependency"] == "affected"}
        if set(parsed_adapters) != affected:
            _fail("adapters", "must cover exactly every affected V metric")
        payload = dict(schema_version="formal-valuation-adapter-bound-definition-v1",
            registry_manifest_hash=bundle.manifest.manifest_hash,
            role_hashes={role: getattr(bundle.manifest, role + "_registry_hash")
                for role in bundle.roles},
            policy_contract_hash=policy.contract_hash,
            signed_child=child, coverage=coverage,
            adapters=[asdict(adapter) for adapter in parsed_adapters.values()],
            metric_definitions={tid: {mid: definition for mid, definition in items.items()
                if mid.startswith("V.")} for tid, items in metric_definitions.items()})
        return raw, payload, actual_coverage, parsed_adapters

    def record(proof, bundle=None):
        current = vars(FormalValuationAdapterRegistry)
        if set(current) != {name for name, _ in own_members} or any(
                current[name] is not value for name, value in own_members):
            _fail("proof", "class contract changed")
        found = records.get(id(proof))
        if type(proof) is not FormalValuationAdapterRegistry or found is None or found[0]() is not proof:
            _fail("proof", "is forged or copied")
        reference, scoring, policy, raw, encoded, coverage, adapters, fingerprints = found[1:]
        if bundle is not None and (type(bundle) is not bundle_type or bundle is not reference):
            _fail("proof", "requires its original verified bundle")
        if sources(reference, scoring, policy) != raw:
            _fail("proof", "signed sources changed")
        if any(canonical(asdict(adapter)) != fingerprints[key] for key, adapter in adapters.items()):
            _fail("proof", "definition changed after loading")
        return found

    class FormalValuationAdapterRegistry:
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("valuation adapter registries require the signed loader")

        def require_official(self, bundle):
            record(self, bundle)

        def dependency_for(self, template_id, metric_id):
            found = record(self)
            if type(template_id) is not str or type(metric_id) is not str:
                _fail("selector", "requires exact strings")
            entry = found[6].get((template_id, metric_id))
            return None if entry is None else json.loads(canonical(entry))

        def adapter_for(self, template_id, metric_id):
            found = record(self)
            if type(template_id) is not str or type(metric_id) is not str:
                _fail("selector", "requires exact strings")
            return found[7].get((template_id, metric_id))

        def to_dict(self):
            return json.loads(record(self)[5])

        def __copy__(self):
            raise TypeError("valuation adapter registry cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("valuation adapter registry cannot be copied")

    own_members = tuple(vars(FormalValuationAdapterRegistry).items())

    def load(bundle, *, scoring_registry, policy_registry):
        raw, payload, coverage, adapters = contract(bundle, scoring_registry, policy_registry)
        encoded = canonical(payload)
        if sources(bundle, scoring_registry, policy_registry) != raw:
            _fail("graph", "signed sources changed during loading")
        result = object.__new__(FormalValuationAdapterRegistry)
        identity = id(result)
        records[identity] = (weakref.ref(result, lambda _: records.pop(identity, None)),
            bundle, scoring_registry, policy_registry, raw, encoded, coverage, adapters,
            {key: canonical(asdict(adapter)) for key, adapter in adapters.items()})
        return result

    return FormalValuationAdapterRegistry, load


(FormalValuationAdapterRegistry, load_formal_valuation_adapter_registry) = _install_registry()
del _install_registry

__all__ = ["ValuationAdapterDefinition", "FormalValuationAdapterRegistry",
    "load_formal_valuation_adapter_registry"]
