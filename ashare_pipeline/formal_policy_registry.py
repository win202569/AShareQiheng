"""Authenticated same-root policy definitions, without runtime policy authority."""

from __future__ import annotations

import hashlib
import json
import weakref
from decimal import Decimal
from types import MappingProxyType

from . import formal_context_schema as context_module
from . import formal_feature_contract as feature_module
from . import formal_policy_contract as contract_module
from . import formal_registry_manifest as manifest_module
from . import formal_scoring_registry as scoring_module
from . import formal_sources as sources_module
from .formal_context_schema import _canonical as _context_canonical, _descriptor
from .formal_feature_contract import SignedFormalFeatureRegistry
from .formal_policy_contract import PolicyContractError, parse_policy_contract
from .formal_registry_manifest import VerifiedRegistryBundle
from .formal_scoring_registry import FormalScoringRegistry, _formula_requirements


_POLICY_ROLES = ("cyclic", "redline", "status", "event")
_ROLES = ("source", "mapping", "feature", "scoring", "industry", *_POLICY_ROLES)
_TEMPLATES = ("general_nonfinancial", "bank", "broker", "insurance", "real_estate")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")


def _signed_periods(slot):
    return _formula_requirements(slot.to_dict()["formula"])[0]


def _context_index(wrapper):
    result, scopes = {}, set()
    for entry in wrapper["descriptors"]:
        _descriptor(entry)
        identity = hashlib.sha256(_context_canonical(entry)).hexdigest()
        scope = (entry["context_kind"], entry["scope_key"], entry["security_scope"])
        if identity in result or scope in scopes:
            raise PolicyContractError("duplicate Context descriptor", path="descriptors")
        result[identity] = entry
        scopes.add(scope)
    return result


def _source_index(source):
    configs = source.get("configs")
    if type(configs) is not list:
        raise PolicyContractError("source configs must be an array", path="source")
    result = {}
    for config in configs:
        if type(config) is not dict or any(type(config.get(key)) is not str for key in ("source", "dataset")):
            raise PolicyContractError("invalid source config identity", path="source")
        result.setdefault((config["source"], config["dataset"]), []).append(config)
    return result


def _bind_context(selector, descriptors, sources, checked_sources, path):
    entry = descriptors.get(selector["descriptor_id"])
    if entry is None:
        raise PolicyContractError("Context descriptor ENTRY identity is absent", path=path)
    if (selector["context_kind"], selector["scope_key"]) != (entry["context_kind"], entry["scope_key"]):
        raise PolicyContractError("Context kind or scope mismatch", path=path)
    if (entry["security_scope"], entry["request_security"], entry["exchange_rule"]) != (
            "security", "input_security", "security_exchange"):
        raise PolicyContractError("policy requires input security and security_exchange for all exchanges", path=path)
    if entry["bootstrap_calendar"]:
        raise PolicyContractError("input security cannot request a bootstrap calendar", path=path)
    whitelist = {"regulatory_state": "allowed_regulatory_flags", "event_calendar": "allowed_event_codes"}
    if entry["context_kind"] in whitelist and selector["entry_id"] not in entry[whitelist[entry["context_kind"]]]:
        raise PolicyContractError("Context flag/event ID is not authorized", path=path)
    identity = selector["descriptor_id"]
    if identity not in checked_sources:
        configs = sources.get((entry["source"], entry["dataset"]), ())
        for exchange in ("SH", "SZ", "BJ"):
            # Existing resolver semantics: null plus exact is ambiguous, never a fallback.
            matches = [c for c in configs if c.get("exchange_scope") in (None, exchange)]
            if len(matches) != 1:
                raise PolicyContractError(f"source selection requires exactly one config for {exchange}", path=path)
            config = matches[0]
            for field in ("source", "dataset", "parser_id", "parser_version", "mapping_version", "bootstrap_calendar"):
                if type(config.get(field)) is not type(entry[field]) or config[field] != entry[field]:
                    raise PolicyContractError(f"Context/source {field} mismatch for {exchange}", path=path)
            if config.get("exchange_scope") != exchange:
                raise PolicyContractError(f"source exchange_scope mismatch for {exchange}", path=path)
            if "calendar_selector" not in config or _canonical(config["calendar_selector"]) != _canonical(entry["calendar_selector"]):
                raise PolicyContractError(f"Context/source calendar_selector mismatch for {exchange}", path=path)
        checked_sources.add(identity)
    return dict(descriptor_id=identity, descriptor=entry)


def _bind_selectors(rules, slots, descriptors, sources):
    manifest, checked_sources = [], set()

    def feature(selector, template, path):
        slot = slots[template].get(selector["feature_key"])
        if selector["template_id"] != template or slot is None:
            raise PolicyContractError("feature is absent from this template", path=path)
        if (selector["expected_unit"] != slot.unit or selector["formula_version"] != slot.formula_version
                or selector["period_keys"] != _signed_periods(slot)):
            raise PolicyContractError("feature unit, formula_version or AST period set mismatch", path=path)
        return slot.to_dict()

    for rule in rules:
        base = f"{rule.role}.{rule.rule_id}"
        for name, selector in sorted(rule.inputs.items()):
            path = f"inputs.{name}"
            if selector["kind"] == "annual_series":
                slot_ids, fingerprints, units = set(), set(), set()
                for index, observation in enumerate(selector["observations"]):
                    item_path = f"{path}.observations[{index}].selector"
                    slot = feature(observation["selector"], rule.template_id, f"{base}.{item_path}")
                    fingerprint = _canonical({key: slot[key] for key in ("formula", "unit", "formula_version")})
                    if slot["slot_id"] in slot_ids or fingerprint in fingerprints:
                        raise PolicyContractError("annual series repeats a slot or complete formula", path=f"{base}.{path}")
                    slot_ids.add(slot["slot_id"])
                    fingerprints.add(fingerprint)
                    units.add(slot["unit"])
                    manifest.append(dict(role=rule.role, rule_id=rule.rule_id, input_path=item_path, slot=slot))
                current = rule.inputs[name.replace("annual_", "current_")]
                if units != {current["expected_unit"]}:
                    raise PolicyContractError("annual/current units differ", path=f"{base}.{path}")
            else:
                definition = (dict(slot=feature(selector, rule.template_id, f"{base}.{path}"))
                    if selector["kind"] == "feature" else
                    _bind_context(selector, descriptors, sources, checked_sources, f"{base}.{path}"))
                manifest.append(dict(role=rule.role, rule_id=rule.rule_id, input_path=path, **definition))
    return manifest


def _require_coverage(rules, scoring, children):
    by_template = {template: {} for template in _TEMPLATES}
    active = {(rule.role, rule.rule_id): rule for rule in rules}
    for rule in rules:
        by_template[rule.template_id][rule.semantic_id] = rule
    security_fields = {"st": "is_st", "star_st": "is_star_st", "forced_delist_risk": "forced_delist_risk"}
    regulatory_hard = ("governance_red", "audit_qualified", "audit_adverse", "audit_disclaimer")
    independent = ("governance_orange", "crowding", "major_unlock_window", "major_reduction_window", "major_event")
    required = (*security_fields, "delisting_arrangement", *regulatory_hard,
        "nonpositive_equity", "no_effective_trade_20d", *independent, "cyclic_top")
    for template, semantic_rules in by_template.items():
        flag_bindings = {}
        for candidate in semantic_rules.values():
            for selector in candidate.inputs.values():
                if selector.get("context_kind") == "regulatory_state":
                    identity = (selector["descriptor_id"], selector["entry_id"])
                    previous = flag_bindings.setdefault(identity, candidate.semantic_id)
                    if previous != candidate.semantic_id:
                        raise PolicyContractError("regulatory semantics reuse the same flag binding",
                            path=f"coverage.{template}.{candidate.semantic_id}")
        for semantic in required:
            path = f"coverage.{template}.{semantic}"
            rule = semantic_rules.get(semantic)
            if rule is None:
                raise PolicyContractError("missing mandatory semantic", path=path)
            if semantic in security_fields or semantic in regulatory_hard or semantic in independent:
                if rule.kind != "boolean_state" or rule.parameters["expected"] is not True:
                    raise PolicyContractError("mandatory state must match expected=true", path=path)
                selector = rule.inputs["value"]
                expected = (("security_state", security_fields[semantic]) if semantic in security_fields
                    else ("regulatory_state", "active"))
                if (selector["context_kind"], selector["field"]) != expected:
                    raise PolicyContractError("mandatory semantic has the wrong Context field", path=path)
            elif semantic == "delisting_arrangement":
                if (rule.kind != "enum_state" or rule.parameters["values"] != ("delisting_arrangement",)
                        or (rule.inputs["value"]["context_kind"], rule.inputs["value"]["field"]) != ("security_state", "listing_status")):
                    raise PolicyContractError("delisting_arrangement must match exactly its approved listing state", path=path)
            elif semantic == "nonpositive_equity":
                if (rule.kind != "numeric_redline" or rule.parameters["comparator"] != "lte"
                        or Decimal(rule.parameters["threshold"]) != 0):
                    raise PolicyContractError("nonpositive_equity requires lte zero", path=path)
            else:
                kind = "cyclic_protection" if semantic == "cyclic_top" else "market_liquidity"
                if rule.kind != kind:
                    raise PolicyContractError(f"mandatory semantic requires {kind}", path=path)
            effects = rule.outcomes["on_match"]
            pools = {effect["pool"] for effect in effects if effect["kind"] == "pool_prohibition"}
            if semantic in independent or semantic == "cyclic_top":
                if not pools or not any(effect["kind"] == "independent_status"
                        and effect["status_code"] == semantic for effect in effects):
                    raise PolicyContractError("independent semantic needs its status and explicit pool restriction", path=path)
            elif "both" not in pools:
                raise PolicyContractError("mandatory hard veto must prohibit both pools", path=path)

        cyclic = semantic_rules["cyclic_top"]
        expected_metrics = {"V." + metric.metric_id for metric in scoring.templates[template].metrics["V"]}
        actual_metrics = {dependency["metric_id"] for dependency in cyclic.parameters["valuation_dependencies"]}
        if actual_metrics != expected_metrics:
            raise PolicyContractError("valuation dependencies must cover exactly this template's V metrics",
                path=f"coverage.{template}.valuation_dependencies")

    classification = (scoring.cyclic_rule.policy_role, scoring.cyclic_rule.rule_id)
    classification_wire = children[classification[0]]["rules"][classification[1]]
    if (set(classification_wire) != {"secondary_industries"}
            or set(classification_wire["secondary_industries"]) != set(scoring.cyclic_secondary_industries)):
        raise PolicyContractError("cyclic classification differs from signed scoring", path="classification")

    def reference(role, rule_id, path, template=None, allow_classification=False):
        if allow_classification and (role, rule_id) == classification:
            return
        rule = active.get((role, rule_id))
        if rule is None:
            raise PolicyContractError("scoring reference does not name an active rule", path=path)
        if template is not None and rule.template_id != template:
            raise PolicyContractError("metric policy reference belongs to another template", path=path)
        return rule

    for name in ("redlines", "status_rules"):
        for item in getattr(scoring, name):
            reference(item.policy_role, item.rule_id, name)
    market = scoring.market_liquidity_rule
    if reference(market.policy_role, market.rule_id, "market_liquidity_rule").kind != "market_liquidity":
        raise PolicyContractError("market_liquidity_rule must name an active market rule", path="market_liquidity_rule")
    for template, definition in scoring.templates.items():
        for dimension, metrics in definition.metrics.items():
            for metric in metrics:
                for item in metric.policy_refs:
                    reference(item["policy_role"], item["rule_id"], f"{template}.{dimension}.{metric.metric_id}.policy_refs",
                        template=template, allow_classification=True)


def _install_binder():
    # Call the authentic class implementations, even if callers shadow methods.
    bundle_type, scoring_type, feature_type = VerifiedRegistryBundle, FormalScoringRegistry, SignedFormalFeatureRegistry
    require_bundle, blob_for = bundle_type.require_official, bundle_type.blob
    require_scoring = scoring_type.require_official
    require_feature = feature_type.require_release_eligible
    slots_for_template = feature_type.slots_for_template

    def bind(bundle: VerifiedRegistryBundle, *, scoring_registry: FormalScoringRegistry,
            feature_registry: SignedFormalFeatureRegistry) -> bytes:
        """Reparse verified children and return auditable definitions, never runtime evidence."""
        if (type(bundle) is not bundle_type or type(scoring_registry) is not scoring_type
                or type(feature_registry) is not feature_type):
            raise PolicyContractError("exact verified bundle, scoring and feature types required", path="graph")
        require_bundle(bundle)
        require_scoring(scoring_registry, bundle)
        require_feature(feature_registry)
        blobs = {role: blob_for(bundle, role) for role in _ROLES}
        hashes = {role: hashlib.sha256(blob.canonical_json).hexdigest() for role, blob in blobs.items()}
        if (hashlib.sha256(bundle.manifest.canonical_json).hexdigest() != bundle.manifest.manifest_hash
                or any(hashes[role] != blobs[role].registry_hash
                    or hashes[role] != getattr(bundle.manifest, role + "_registry_hash") for role in _ROLES)):
            raise PolicyContractError("actual root or child hash mismatch", path="graph")
        if (feature_registry.canonical_json != blobs["feature"].canonical_json
                or feature_registry.registry_hash != hashes["feature"]
                or feature_registry.source_registry_hash != hashes["source"]
                or feature_registry.mapping_registry_hash != hashes["mapping"]):
            raise PolicyContractError("feature content differs from current root", path="graph.feature")
        parsed = parse_policy_contract({role: blobs[role].canonical_json for role in _POLICY_ROLES})
        children = {role: json.loads(blobs[role].canonical_json) for role in _POLICY_ROLES}
        for role, child in children.items():
            declared = scoring_registry.policy_contracts[role]
            if (child["purpose"] != "official" or declared["registry_hash"] != hashes[role]
                    or child["registry_version"] != declared["registry_version"]
                    or tuple(child["source_evidence_categories"]) != declared["source_evidence_categories"]):
                raise PolicyContractError("policy purpose, version or categories mismatch", path=role)
        rules = [dict(children[rule.role]["rules"][rule.rule_id], role=rule.role, rule_id=rule.rule_id)
            for rule in parsed.rules]
        slots = MappingProxyType({template: MappingProxyType({slot.slot_id: slot
            for slot in slots_for_template(feature_registry, template)}) for template in _TEMPLATES})
        wrapper = json.loads(blobs["scoring"].canonical_json)
        binding_manifest = _bind_selectors(parsed.rules, slots, _context_index(wrapper),
            _source_index(json.loads(blobs["source"].canonical_json)))
        _require_coverage(parsed.rules, scoring_registry, children)
        return _canonical(dict(schema_version="formal-policy-bound-definition-v1",
            contract_version="formal-policy-execution-contract-v1",
            registry_manifest_hash=bundle.manifest.manifest_hash, role_hashes=hashes,
            role_versions=dict(parsed.role_versions),
            source_evidence_categories={role: list(values) for role, values in parsed.evidence_categories.items()},
            rules=rules, valuation_dependencies={rule.template_id:
                children[rule.role]["rules"][rule.rule_id]["parameters"]["valuation_dependencies"]
                for rule in parsed.rules if rule.kind == "cyclic_protection"},
            cyclic_secondary_industries=sorted(scoring_registry.cyclic_secondary_industries),
            binding_manifest=binding_manifest))

    return bind


_bind_policy_contract = _install_binder()
del _install_binder


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    if type(value) not in (str, int, bool, type(None)):
        raise ValueError("policy definition contains a non-JSON value")
    return value


def _install_policy_registry():
    records = {}
    module_globals = globals()
    bundle_type, scoring_type, feature_type = VerifiedRegistryBundle, FormalScoringRegistry, SignedFormalFeatureRegistry
    require_bundle, blob_for = bundle_type.require_official, bundle_type.blob
    require_scoring, require_feature = scoring_type.require_official, feature_type.require_release_eligible
    bind, encode, freeze = _bind_policy_contract, _canonical, _freeze
    loads, sha256, weak_ref = json.loads, hashlib.sha256, weakref.ref
    fields = frozenset(("schema_version", "contract_version", "registry_manifest_hash", "role_hashes",
        "role_versions", "source_evidence_categories", "rules", "valuation_dependencies",
        "cyclic_secondary_industries", "binding_manifest"))
    public_fields = fields | {"contract_hash"}

    # Explicit call-path inventory, without inferring a dependency graph or
    # running a second policy parser. Check owner bindings and imported aliases.
    binding_names = (
        (module_globals, "context_module feature_module contract_module manifest_module scoring_module sources_module "
            "VerifiedRegistryBundle FormalScoringRegistry SignedFormalFeatureRegistry PolicyContractError "
            "parse_policy_contract _bind_policy_contract _canonical _freeze _signed_periods _context_index "
            "_source_index _bind_context _bind_selectors _require_coverage _context_canonical _descriptor "
            "_formula_requirements json hashlib weakref MappingProxyType Decimal _POLICY_ROLES _ROLES _TEMPLATES"),
        (vars(contract_module), "parse_policy_contract parse_policy_rule _canonical _load _exact_keys _text "
            "_identifier _decimal_parameter _algorithm_identifier _ordered_texts _text_array _feature_selector "
            "_context_selector _selector _valuation_dependencies _validate_parameters _validate_effect "
            "_validate_outcomes _frozen PolicyRule ParsedPolicyContract PolicyContractError Decimal InvalidOperation "
            "MappingProxyType json _ROLES _TEMPLATES _FY_ENDS _RULE_KINDS _CONTEXT_FIELDS _SHA256 _IDENTIFIER "
            "_DECIMAL _DIMENSIONS _LISTING_VALUES"),
        (vars(scoring_module), "_graph _feature_slots _formula_requirements VerifiedRegistryBundle "
            "SignedFormalFeatureRegistry FormalScoringRegistry RegistryApproval TemplateDefinition MetricDefinition "
            "RedlineDefinition StatusRule RegistryValidationError fields Decimal MappingProxyType hashlib _ROLES _TEMPLATES"),
        (vars(feature_module), "SignedFormalFeatureRegistry FormalFeatureSlot FormulaNode _parse_registry_bytes "
            "_load_canonical_object _canonical_json_bytes _unique_json_object _reject_json_constant _DuplicateJsonKey "
            "_require_text _require_hash _require_exact_keys _snapshot_json _parse_formula _formula_to_dict "
            "_slot_to_dict _SHA256 _IDENTIFIER _TEMPLATES _DIMENSIONS _UNITS _FORMULA_OPS _REGISTRY_KEYS "
            "_SLOT_KEYS json hashlib math"),
        (vars(manifest_module), "VerifiedRegistryBundle FormalRegistryManifest VerifiedRegistryBlob "
            "_require_trimmed_text _VERSION_IDENTIFIER _ROLE_FIELDS Mapping"),
        (vars(context_module), "_descriptor _canonical _json_tree _keys _text _exchange _ordered _selector "
            "CalendarSelector CONTEXT_KINDS _DESCRIPTOR_FIELDS _ROLES json math re"),
        (vars(sources_module), "CalendarSelector _require_trimmed_text _require_exchange _VERSION_IDENTIFIER _EXCHANGES"),
        (vars(json), "loads dumps"), (vars(hashlib), "sha256"), (vars(weakref), "ref"),
        (vars(feature_module.math), "isfinite"), (vars(context_module.re), "fullmatch"),
    )
    bindings = tuple((owner, name, owner[name]) for owner, names in binding_names for name in names.split())
    source_interfaces = (
        (bundle_type, "require_official blob"), (scoring_type, "require_official"),
        (feature_type, "require_release_eligible slots_for_template"),
        (manifest_module.FormalRegistryManifest, ""), (manifest_module.VerifiedRegistryBlob, ""),
        (feature_module.FormalFeatureSlot, "__init__ __post_init__ from_dict to_dict"),
        (feature_module.FormulaNode, "__init__ __post_init__ from_dict"),
        (scoring_module.RegistryApproval, ""), (scoring_module.TemplateDefinition, ""),
        (scoring_module.MetricDefinition, ""), (scoring_module.RedlineDefinition, ""),
        (scoring_module.StatusRule, ""), (contract_module.PolicyRule, "__init__"),
        (contract_module.ParsedPolicyContract, "__init__"),
        (sources_module.CalendarSelector, "__init__ __post_init__"),
    )

    def resolved_member(cls, name):
        return next((vars(base)[name] for base in cls.__mro__ if name in vars(base)), None)

    # Upstream records are inspected through these exact lookup methods and
    # dataclass fields; unrelated convenience methods are not dependencies.
    source_members = tuple((cls, name, resolved_member(cls, name))
        for cls, methods in source_interfaces
        for name in (*methods.split(), "__getattribute__", "__getattr__", "__dataclass_fields__",
            *cls.__dataclass_fields__))
    source_bases = tuple((cls, cls.__bases__, cls.__mro__) for cls, _ in source_interfaces)

    def class_snapshot(classes):
        return tuple((cls, tuple(vars(cls).items()), cls.__bases__, cls.__mro__) for cls in classes)

    def dependencies():
        if any(owner.get(name) is not expected for owner, name, expected in bindings):
            raise ValueError("policy proof dependency changed")
        if (module_globals.get("FormalPolicyRegistry") is not proof_type
                or module_globals.get("load_formal_policy_registry") is not load
                or module_globals.get("_read_authenticated_policy_registry") is not read):
            raise ValueError("policy proof entry point changed")
        if (any(resolved_member(cls, name) is not expected for cls, name, expected in source_members)
                or any(cls.__bases__ != bases or cls.__mro__ != mro for cls, bases, mro in source_bases)):
            raise ValueError("policy proof source interface changed")
        for cls, expected, bases, mro in own_members:
            current = vars(cls)
            if (cls.__bases__ != bases or cls.__mro__ != mro
                    or set(current) != {name for name, _ in expected}
                    or any(current[name] is not value for name, value in expected)):
                raise ValueError("policy proof class member or inheritance changed")

    def verify_sources(bundle, scoring, feature):
        if type(bundle) is not bundle_type or type(scoring) is not scoring_type or type(feature) is not feature_type:
            raise ValueError("policy proof requires exact genuine registry sources")
        require_bundle(bundle)
        require_scoring(scoring, bundle)
        require_feature(feature)
        blobs = {role: blob_for(bundle, role) for role in _ROLES}
        hashes = {role: sha256(blob.canonical_json).hexdigest() for role, blob in blobs.items()}
        root_hash = sha256(bundle.manifest.canonical_json).hexdigest()
        if (root_hash != bundle.manifest.manifest_hash
                or any(hashes[role] != blobs[role].registry_hash
                    or hashes[role] != getattr(bundle.manifest, role + "_registry_hash") for role in _ROLES)):
            raise ValueError("policy proof actual root or child bytes changed")
        # The original feature verifier just checked its complete sealed record.
        # Read those actual fields without repeating its expensive slot reparse
        # for each scalar. Scoring already checks all five template slot sets.
        read = object.__getattribute__
        if (read(feature, "canonical_json") != blobs["feature"].canonical_json
                or read(feature, "registry_hash") != hashes["feature"]
                or read(feature, "source_registry_hash") != hashes["source"]
                or read(feature, "mapping_registry_hash") != hashes["mapping"]):
            raise ValueError("policy proof feature/source/mapping differs from current root")
        return root_hash, hashes

    def proof_record(proof):
        dependencies()
        record = records.get(id(proof))
        if type(proof) is not proof_type or record is None or record[0]() is not proof:
            raise ValueError("policy proof is forged, copied or unregistered")
        root_hash, hashes = verify_sources(record[3], record[4], record[5])
        if root_hash != record[6] or hashes != record[7]:
            raise ValueError("policy proof source identity changed")
        return record

    class ProofMeta(type):
        def __setattr__(cls, name, value):
            if name in ("__getattribute__", "__bases__"):
                raise TypeError("policy proof lookup or inheritance cannot be replaced")
            return super().__setattr__(name, value)

        def __delattr__(cls, name):
            if name in ("__getattribute__", "__bases__"):
                raise TypeError("policy proof lookup or inheritance cannot be removed")
            return super().__delattr__(name)

    class Proof(metaclass=ProofMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("policy proofs require load_formal_policy_registry")

        def __getattribute__(self, name):
            proof_record(self)
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            record = proof_record(self)
            if name not in public_fields:
                raise AttributeError(name)
            return record[1][name]

        def require_verified(self):
            """Authenticate the definition and its historical registry sources."""
            proof_record(self)

        def canonical_bytes(self):
            """Return A2's bound bytes, excluding the derived contract_hash."""
            return proof_record(self)[2]

        def to_dict(self):
            record = proof_record(self)
            return dict(loads(record[2]), contract_hash=record[1]["contract_hash"])

        def __copy__(self):
            raise TypeError("policy proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("policy proofs cannot be copied")

        def __reduce__(self):
            raise TypeError("policy proofs cannot be serialized for reconstruction")

        def __reduce_ex__(self, protocol):
            raise TypeError("policy proofs cannot be serialized for reconstruction")

    class FormalPolicyRegistry(Proof):
        """Immutable policy definitions; no security evidence or scoring readiness."""
        __slots__ = ()

    proof_type = FormalPolicyRegistry

    def load(bundle: VerifiedRegistryBundle, *, scoring_registry: FormalScoringRegistry,
            feature_registry: SignedFormalFeatureRegistry) -> FormalPolicyRegistry:
        """Authenticate and bind one complete signed graph without executing it."""
        dependencies()
        root_hash, hashes = verify_sources(bundle, scoring_registry, feature_registry)
        canonical = bind(bundle, scoring_registry=scoring_registry, feature_registry=feature_registry)
        payload = loads(canonical)
        if type(canonical) is not bytes or type(payload) is not dict or set(payload) != fields or encode(payload) != canonical:
            raise ValueError("policy binder returned a noncanonical definition")
        frozen_payload = freeze(dict(payload, contract_hash=sha256(canonical).hexdigest()))
        dependencies()
        if verify_sources(bundle, scoring_registry, feature_registry) != (root_hash, hashes):
            raise ValueError("policy proof sources changed during loading")
        result = object.__new__(proof_type)
        identity = id(result)

        def forget(reference):
            record = records.get(identity)
            if record is not None and record[0] is reference:
                records.pop(identity, None)

        records[identity] = (weak_ref(result, forget), frozen_payload, canonical,
            bundle, scoring_registry, feature_registry, root_hash, hashes)
        return result

    def read(proof):
        """Internal consumer read anchored in this owner's original proof record."""
        record = proof_record(proof)
        return dict(loads(record[2]), contract_hash=record[1]["contract_hash"])

    own_members = class_snapshot((ProofMeta, Proof, proof_type))
    return proof_type, load, read


(FormalPolicyRegistry, load_formal_policy_registry,
 _read_authenticated_policy_registry) = _install_policy_registry()
del _install_policy_registry


__all__ = ["FormalPolicyRegistry", "load_formal_policy_registry"]
