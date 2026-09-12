"""Same-root active-policy range bindings; no date coverage or execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
import weakref

from .formal_range_format import (
    RangeConfig, parse_range_entry, _canonical, _exchange, _freeze, _text,
)

_LEGACY_CONFIG_FIELDS = frozenset(
    {
        "source",
        "dataset",
        "endpoint_url",
        "http_method",
        "parser_id",
        "parser_version",
        "mapping_version",
        "request_template",
        "timeout_seconds",
        "retry_base_seconds",
        "retry_max_attempts",
        "challenge_cooldown_seconds",
        "exchange_scope",
        "calendar_selector",
        "bootstrap_calendar",
    }
)


def _load_canonical_object(raw: object, label: str) -> dict[str, object]:
    if type(raw) is not bytes:
        raise ValueError(f"{label} must be canonical UTF-8 bytes")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"{label} has duplicate JSON keys")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"{label} has non-finite value {value}")

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant
        )
    except (UnicodeError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if type(value) is not dict or _canonical(value) != raw:
        raise ValueError(f"{label} must be a canonical JSON object")
    return value


def _build_range_bindings_contract():
    # Source imports only the pure format module, so trust interfaces can be
    # captured now, before callers can replace methods ahead of the first load.
    from .formal_context_schema import _descriptor as validate_descriptor
    from .formal_policy_registry import FormalPolicyRegistry as policy_type
    from .formal_registry_manifest import VerifiedRegistryBundle as bundle_type
    from .formal_scoring_registry import FormalScoringRegistry as scoring_type
    from .formal_range_format import RangeConfig, parse_range_entry, _range_config_to_dict

    require_bundle = bundle_type.require_official
    blob_for = bundle_type.blob
    require_scoring = scoring_type.require_official
    require_policy = policy_type.require_verified
    policy_bytes_for = policy_type.canonical_bytes

    def _range_catalog_from_source(raw: bytes) -> tuple[dict[str, object], tuple[RangeConfig, ...]]:
        source = _load_canonical_object(raw, "source registry")
        if set(source) != {"registry_role", "schema_version", "configs", "range_configs"}:
            raise ValueError("Stage B requires a closed formal-source-registry-v2")
        if source["registry_role"] != "source" or source["schema_version"] != "formal-source-registry-v2":
            raise ValueError("Stage B requires formal-source-registry-v2")
        if type(source["configs"]) is not list or any(
            type(item) is not dict or set(item) != _LEGACY_CONFIG_FIELDS
            for item in source["configs"]
        ):
            raise ValueError("source registry legacy configs are not closed")
        if type(source["range_configs"]) is not list:
            raise ValueError("source registry range_configs must be a list")
        configs = tuple(parse_range_entry(item) for item in source["range_configs"])
        identities = set()
        for config in configs:
            if type(config) is not RangeConfig:
                raise ValueError("range parser returned an unexpected config type")
            wire = _range_config_to_dict(config)
            identity = (
                wire["kind"],
                wire["capability"],
                wire["anchor_descriptor_id"],
                wire["calendar_descriptor_id"],
                wire["exchange_scope"],
            )
            if identity in identities:
                raise ValueError("source registry has duplicate range config identity")
            identities.add(identity)
        return source, configs


    def _calendar_bridge(selector: dict[str, object], exchange: str) -> dict[str, object]:
        return {"selector": dict(selector), "exchange": exchange}


    def _pair_key(entry: dict[str, object]):
        return (
            entry["capability"],
            entry["exchange_scope"],
            entry["calendar_descriptor_id"],
        )


    def _require_pair(
        market: dict[str, object],
        calendar: dict[str, object],
        selector: dict[str, object],
        exchange: str,
    ) -> None:
        if market["kind"] != "market_range" or calendar["kind"] != "calendar_range":
            raise ValueError("range pair kind mismatch")
        if _pair_key(market) != _pair_key(calendar):
            raise ValueError("range calendar identity mismatch")
        if calendar["anchor_descriptor_id"] != calendar["calendar_descriptor_id"]:
            raise ValueError("calendar anchor must identify itself")
        if market["calendar_anchor_selector"] != _calendar_bridge(selector, exchange):
            raise ValueError("policy calendar bridge mismatch")


    def _derive_graph(bundle, scoring_registry, policy_registry):
        if (
            type(bundle) is not bundle_type
            or type(scoring_registry) is not scoring_type
            or type(policy_registry) is not policy_type
        ):
            raise ValueError("range bindings require exact genuine registry types")
        require_bundle(bundle)
        require_scoring(scoring_registry, bundle)
        require_policy(policy_registry)
        policy = json.loads(policy_bytes_for(policy_registry))
        root_hash = hashlib.sha256(bundle.manifest.canonical_json).hexdigest()
        if root_hash != bundle.manifest.manifest_hash:
            raise ValueError("range binding registry root hash mismatch")
        if policy["registry_manifest_hash"] != root_hash:
            raise ValueError("policy and range registry roots differ")
        role_hashes = {}
        for role in ("source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event"):
            blob = blob_for(bundle, role)
            digest = hashlib.sha256(blob.canonical_json).hexdigest()
            if digest != blob.registry_hash or digest != getattr(bundle.manifest, role + "_registry_hash"):
                raise ValueError("range binding actual child hash mismatch")
            role_hashes[role] = digest
        if policy["role_hashes"] != role_hashes:
            raise ValueError("policy roles differ from the current range graph")

        source_wire, range_configs = _range_catalog_from_source(blob_for(bundle, "source").canonical_json)
        wrapper = _load_canonical_object(blob_for(bundle, "scoring").canonical_json, "scoring registry")
        descriptors = {}
        scopes = set()
        raw_descriptors = wrapper.get("descriptors")
        if type(raw_descriptors) is not list:
            raise ValueError("scoring registry Context descriptors are absent")
        for descriptor in raw_descriptors:
            validate_descriptor(descriptor)
            identity = hashlib.sha256(_canonical(descriptor)).hexdigest()
            scope = (descriptor["context_kind"], descriptor["scope_key"], descriptor["security_scope"])
            if identity in descriptors or scope in scopes:
                raise ValueError("duplicate Context descriptor in range graph")
            descriptors[identity] = descriptor
            scopes.add(scope)

        legacy_configs = source_wire["configs"]
        definitions = {}
        market_rules = [rule for rule in policy["rules"] if rule["kind"] == "market_liquidity"]
        if not market_rules:
            raise ValueError("active market policy is absent")
        for rule in market_rules:
            capability = rule["parameters"]["required_evidence_capability"]
            if capability != "verified_market_window_v1":
                raise ValueError("active market policy lacks authorized range capability")
            market_selector = rule["inputs"]["market"]
            calendar_selector = rule["inputs"]["calendar"]
            if (
                market_selector["kind"] != "context"
                or market_selector["context_kind"] != "market_close"
                or calendar_selector["kind"] != "context"
                or calendar_selector["context_kind"] != "trading_calendar"
            ):
                raise ValueError("market policy Context selectors are invalid")
            market_descriptor = descriptors.get(market_selector["descriptor_id"])
            policy_calendar_descriptor = descriptors.get(calendar_selector["descriptor_id"])
            if market_descriptor is None or policy_calendar_descriptor is None:
                raise ValueError("market policy Context descriptor is absent")
            for exchange in ("SH", "SZ", "BJ"):
                market_matches = [
                    config
                    for config in range_configs
                    if config.kind == "market_range"
                    and config.capability == capability
                    and config.anchor_descriptor_id == market_selector["descriptor_id"]
                    and config.exchange_scope == exchange
                ]
                if len(market_matches) != 1:
                    raise ValueError("market range config is absent or ambiguous")
                market_config = market_matches[0]
                calendar_matches = [
                    config
                    for config in range_configs
                    if config.kind == "calendar_range"
                    and config.capability == capability
                    and config.calendar_descriptor_id == market_config.calendar_descriptor_id
                    and config.exchange_scope == exchange
                ]
                if len(calendar_matches) != 1:
                    raise ValueError("calendar range config is absent or ambiguous")
                calendar_config = calendar_matches[0]
                market_wire = _range_config_to_dict(market_config)
                calendar_wire = _range_config_to_dict(calendar_config)
                _require_pair(market_wire, calendar_wire, calendar_selector, exchange)
                bootstrap = descriptors.get(calendar_config.calendar_descriptor_id)
                if bootstrap is None:
                    raise ValueError("range bootstrap calendar descriptor is absent")
                if (
                    bootstrap["context_kind"] != "trading_calendar"
                    or bootstrap["security_scope"] != "none"
                    or bootstrap["request_security"] != "none"
                    or bootstrap["exchange_rule"] != "fixed_exchange"
                    or bootstrap["fixed_exchange"] != exchange
                    or bootstrap["bootstrap_calendar"] is not True
                    or bootstrap["calendar_selector"] is not None
                ):
                    raise ValueError("range calendar anchor is not the exchange bootstrap descriptor")
                if calendar_selector["descriptor_id"] == calendar_config.calendar_descriptor_id:
                    raise ValueError("policy calendar C cannot be used as bootstrap calendar Bx")
                if (market_config.source, market_config.dataset) != (
                    market_descriptor["source"],
                    market_descriptor["dataset"],
                ):
                    raise ValueError("market range source differs from its M descriptor")
                if (calendar_config.source, calendar_config.dataset) != (
                    bootstrap["source"],
                    bootstrap["dataset"],
                ):
                    raise ValueError("calendar range source differs from its Bx descriptor")
                bootstrap_sources = [
                    config
                    for config in legacy_configs
                    if config["source"] == bootstrap["source"]
                    and config["dataset"] == bootstrap["dataset"]
                    and config["exchange_scope"] is None
                ]
                if len(bootstrap_sources) != 1:
                    raise ValueError("bootstrap source config is absent or ambiguous")
                old = bootstrap_sources[0]
                for field in (
                    "source",
                    "dataset",
                    "parser_id",
                    "parser_version",
                    "mapping_version",
                    "bootstrap_calendar",
                    "calendar_selector",
                ):
                    if type(old[field]) is not type(bootstrap[field]) or old[field] != bootstrap[field]:
                        raise ValueError("bootstrap descriptor and legacy source config differ")

                binding_wire = {
                    "schema_version": "formal-policy-range-binding-v1",
                    "rule_id": rule["rule_id"],
                    "exchange": exchange,
                    "market_config_id": market_config.entry_id,
                    "calendar_config_id": calendar_config.entry_id,
                    "policy_calendar_selector": _calendar_bridge(calendar_selector, exchange),
                    "registry_manifest_hash": root_hash,
                }
                binding_hash = hashlib.sha256(_canonical(binding_wire)).hexdigest()
                definitions[(rule["rule_id"], exchange)] = (
                    market_config,
                    calendar_config,
                    binding_wire["policy_calendar_selector"],
                    binding_hash,
                )
        return root_hash, role_hashes, definitions


    @dataclass(frozen=True)
    class _BindingsRecord:
        reference: weakref.ReferenceType[object]
        bundle: object
        scoring_registry: object
        policy_registry: object
        root_hash: str
        role_hashes: dict[str, str]
        definition_fingerprint: bytes
        bindings: dict[tuple[str, str], object]


    @dataclass(frozen=True)
    class _BindingRecord:
        reference: weakref.ReferenceType[object]
        parent: weakref.ReferenceType[object]
        key: tuple[str, str]
        market_config: RangeConfig
        calendar_config: RangeConfig
        selector: Mapping[str, object]
        binding_hash: str
        market_bytes: bytes
        calendar_bytes: bytes


    _bindings_records: dict[int, _BindingsRecord] = {}
    _binding_records: dict[int, _BindingRecord] = {}


    def _definitions_fingerprint(definitions) -> bytes:
        rows = []
        for (rule_id, exchange), (market, calendar, selector, binding_hash) in sorted(definitions.items()):
            rows.append(
                {
                    "rule_id": rule_id,
                    "exchange": exchange,
                    "market": _range_config_to_dict(market),
                    "calendar": _range_config_to_dict(calendar),
                    "selector": selector,
                    "binding_hash": binding_hash,
                }
            )
        return _canonical(rows)


    def _bindings_record(value: object, *, current: bool = False) -> _BindingsRecord:
        record = _bindings_records.get(id(value))
        if type(value) is not RangeBindings or record is None or record.reference() is not value:
            raise ValueError("range bindings are forged, copied, or unregistered")
        children = object.__getattribute__(value, "_RangeBindings__bindings")
        if (
            type(children) is not MappingProxyType
            or children.keys() != record.bindings.keys()
            or any(reference() is not children[key] for key, reference in record.bindings.items())
        ):
            raise ValueError("range binding set children changed")
        if current:
            root_hash, role_hashes, definitions = _derive_graph(
                record.bundle, record.scoring_registry, record.policy_registry
            )
            if (
                root_hash != record.root_hash
                or role_hashes != record.role_hashes
                or _definitions_fingerprint(definitions) != record.definition_fingerprint
            ):
                raise ValueError("range binding sources changed")
        return record


    def _binding_record(value: object, *, current: bool = False) -> _BindingRecord:
        record = _binding_records.get(id(value))
        if type(value) is not RangeBinding or record is None or record.reference() is not value:
            raise ValueError("range binding is forged, copied, or unregistered")
        parent = record.parent()
        if parent is None or object.__getattribute__(value, "_RangeBinding__parent") is not parent:
            raise ValueError("range binding parent changed")
        parent_record = _bindings_record(parent, current=current)
        child_reference = parent_record.bindings.get(record.key)
        if child_reference is None or child_reference() is not value:
            raise ValueError("range binding no longer belongs to its binding set")
        if (
            type(record.market_config) is not RangeConfig
            or type(record.calendar_config) is not RangeConfig
            or _canonical(_range_config_to_dict(record.market_config)) != record.market_bytes
            or _canonical(_range_config_to_dict(record.calendar_config)) != record.calendar_bytes
        ):
            raise ValueError("range binding configuration changed")
        return record


    class RangeBinding:
        """A current, same-root M/C/Bx configuration authorization."""

        __slots__ = ("__parent", "__weakref__")

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("RangeBinding must be loaded from a verified graph")

        @property
        def market_config(self) -> RangeConfig:
            return _binding_record(self).market_config

        @property
        def calendar_config(self) -> RangeConfig:
            return _binding_record(self).calendar_config

        @property
        def policy_calendar_selector(self) -> Mapping[str, object]:
            return _binding_record(self).selector

        @property
        def registry_manifest_hash(self) -> str:
            return _bindings_record(_binding_record(self).parent()).root_hash

        @property
        def source_registry_hash(self) -> str:
            return _bindings_record(_binding_record(self).parent()).role_hashes["source"]

        @property
        def binding_hash(self) -> str:
            return _binding_record(self).binding_hash

        def require_current(self) -> None:
            _binding_record(self, current=True)

        def __copy__(self):
            raise TypeError("range bindings cannot be copied")

        def __deepcopy__(self, _memo):
            raise TypeError("range bindings cannot be copied")


    class RangeBindings:
        """All range authorizations for the active market rules in one signed root."""

        __slots__ = ("__bindings", "__weakref__")

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("RangeBindings must be loaded from a verified graph")

        def for_rule(self, rule_id: str, exchange: str) -> RangeBinding:
            record = _bindings_record(self)
            _text(rule_id, "range binding rule_id")
            _exchange(exchange, "range binding exchange")
            reference = record.bindings.get((rule_id, exchange))
            binding = None if reference is None else reference()
            if type(binding) is not RangeBinding:
                raise ValueError("range binding is absent")
            _binding_record(binding)
            return binding

        def __copy__(self):
            raise TypeError("range binding sets cannot be copied")

        def __deepcopy__(self, _memo):
            raise TypeError("range binding sets cannot be copied")


    def load_policy_range_bindings(
        bundle, *, scoring_registry, policy_registry
    ) -> RangeBindings:
        """Bind signed range configs to every active market rule and exchange."""
        root_hash, role_hashes, definitions = _derive_graph(
            bundle, scoring_registry, policy_registry
        )
        result = object.__new__(RangeBindings)
        binding_objects = {}
        for key, (market, calendar, selector, binding_hash) in definitions.items():
            binding = object.__new__(RangeBinding)
            object.__setattr__(binding, "_RangeBinding__parent", result)
            selector_snapshot = _freeze(selector)
            binding_objects[key] = binding
            binding_identity = id(binding)

            def forget_binding(reference, *, identity=binding_identity):
                record = _binding_records.get(identity)
                if record is not None and record.reference is reference:
                    _binding_records.pop(identity, None)

            reference = weakref.ref(binding, forget_binding)
            _binding_records[binding_identity] = _BindingRecord(
                reference,
                weakref.ref(result),
                key,
                market,
                calendar,
                selector_snapshot,
                binding_hash,
                _canonical(_range_config_to_dict(market)),
                _canonical(_range_config_to_dict(calendar)),
            )
        object.__setattr__(result, "_RangeBindings__bindings", MappingProxyType(binding_objects))
        identity = id(result)

        def forget_bindings(reference, *, identity=identity):
            record = _bindings_records.get(identity)
            if record is not None and record.reference is reference:
                _bindings_records.pop(identity, None)

        reference = weakref.ref(result, forget_bindings)
        _bindings_records[identity] = _BindingsRecord(
            reference,
            bundle,
            scoring_registry,
            policy_registry,
            root_hash,
            dict(role_hashes),
            _definitions_fingerprint(definitions),
            {key: weakref.ref(binding) for key, binding in binding_objects.items()},
        )
        return result

    return RangeBinding, RangeBindings, load_policy_range_bindings


RangeBinding, RangeBindings, load_policy_range_bindings = _build_range_bindings_contract()
del _build_range_bindings_contract


__all__ = [
    "RangeBinding",
    "RangeBindings",
    "RangeConfig",
    "load_policy_range_bindings",
    "parse_range_entry",
]
