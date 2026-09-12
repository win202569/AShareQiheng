"""Closed signed range-source declarations and active-policy bindings.

This module authorizes configuration only.  It deliberately does not create a
range request or claim that any date interval has been covered.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
import weakref


_SOURCES = frozenset({"cninfo", "sse", "szse", "bse", "csrc"})
_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_VERSION_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
_PLACEHOLDERS = frozenset(
    {"security_id", "exchange", "start_date", "end_date", "page_index"}
)
_RANGE_FIELDS = (
    "schema_version",
    "capability",
    "kind",
    "anchor_descriptor_id",
    "calendar_descriptor_id",
    "source",
    "dataset",
    "endpoint_url",
    "http_method",
    "parser_id",
    "parser_version",
    "mapping_version",
    "normalizer_version",
    "request_version",
    "exchange_scope",
    "calendar_anchor_selector",
    "request_template",
    "pagination",
    "max_pages",
    "max_calendar_days_per_request",
    "timeout_seconds",
    "retry_base_seconds",
    "retry_max_attempts",
    "challenge_cooldown_seconds",
)
_RANGE_FIELD_SET = frozenset(_RANGE_FIELDS)
_CONTEXT_SELECTOR_FIELDS = frozenset(
    {
        "kind",
        "descriptor_id",
        "context_kind",
        "scope_key",
        "field",
        "entry_id",
        "expected_type",
        "expected_unit",
    }
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


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _text(value: object, label: str, *, version: bool = False) -> str:
    pattern = _VERSION_IDENTIFIER if version else _IDENTIFIER
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{label} must be an exact identifier")
    return value


def _hash(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _exchange(value: object, label: str = "exchange") -> str:
    if type(value) is not str or value not in _EXCHANGES:
        raise ValueError(f"{label} must be SH, SZ, or BJ")
    return value


def _positive_number(value: object, label: str) -> int | float:
    if (
        type(value) not in (int, float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{label} must be a positive finite number")
    return value


def _positive_integer(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _https_url(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an absolute HTTPS URL")
    if any(ord(char) <= 0x20 or ord(char) == 0x7F or char.isspace() for char in value):
        raise ValueError(f"{label} contains forbidden whitespace or controls")
    if not value[:8].lower() == "https://" or "#" in value:
        raise ValueError(f"{label} must be an absolute HTTPS URL without a fragment")
    authority = value[8:].split("/", 1)[0].split("?", 1)[0]
    if not authority or "@" in authority or authority.startswith("[") or authority.count(":") > 1:
        raise ValueError(f"{label} hostname is invalid")
    host, separator, port = authority.partition(":")
    if not host or (separator and (not port or not port.isascii() or not port.isdecimal())):
        raise ValueError(f"{label} hostname or port is invalid")
    return value


def _placeholder_text(value: object, label: str, *, nonempty: bool = False) -> str:
    if type(value) is not str or value != value.strip() or (nonempty and not value):
        raise ValueError(f"{label} must be an already-trimmed string")
    remaining = _PLACEHOLDER.sub("", value)
    if "{" in remaining or "}" in remaining:
        raise ValueError(f"{label} has an invalid placeholder")
    if any(match.group(1) not in _PLACEHOLDERS for match in _PLACEHOLDER.finditer(value)):
        raise ValueError(f"{label} has an unknown placeholder")
    return value


def _template_tree(value: object, label: str, seen: set[int]) -> object:
    if value is None:
        return None
    if type(value) is str:
        _placeholder_text(value, label)
        return value
    if type(value) is list:
        if id(value) in seen:
            raise ValueError("range request template aliases or cycles are forbidden")
        seen.add(id(value))
        return [_template_tree(item, label, seen) for item in value]
    if type(value) is dict:
        if id(value) in seen:
            raise ValueError("range request template aliases or cycles are forbidden")
        seen.add(id(value))
        result = {}
        for key, item in value.items():
            _placeholder_text(key, f"{label} key", nonempty=True)
            result[key] = _template_tree(item, label, seen)
        return result
    raise ValueError(f"{label} must be a JSON mapping/list/string/null tree")


def _request_template(value: object, method: str, kind: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != {"query", "headers", "body"}:
        raise ValueError("request_template must contain exactly query, headers, and body")
    if type(value["query"]) is not dict or type(value["headers"]) is not dict:
        raise ValueError("request_template query and headers must be exact objects")
    copied = _template_tree(value, "request_template", set())
    assert type(copied) is dict
    placeholders = {
        match.group(1)
        for text in _walk_strings(copied)
        for match in _PLACEHOLDER.finditer(text)
    }
    if kind == "calendar_range" and "security_id" in placeholders:
        raise ValueError("calendar range template cannot use security_id")
    if method == "GET" and copied["body"] is not None:
        raise ValueError("GET request_template body must be null")
    for key, item in copied["query"].items():
        if _PLACEHOLDER.search(key) or any(char in item for char in ("&", "#")):
            raise ValueError("range query template is unsafe")
    for key, item in copied["headers"].items():
        if _PLACEHOLDER.search(key) or re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", key) is None:
            raise ValueError("range header template is unsafe")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in item):
            raise ValueError("range header template contains controls")
    return copied


def _walk_strings(value: object):
    if type(value) is str:
        yield value
    elif type(value) is list:
        for item in value:
            yield from _walk_strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk_strings(item)


def _context_selector(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != _CONTEXT_SELECTOR_FIELDS:
        raise ValueError("policy calendar selector has unknown or missing keys")
    result = dict(value)
    if result["kind"] != "context" or result["context_kind"] != "trading_calendar":
        raise ValueError("policy calendar selector must identify trading_calendar Context")
    _hash(result["descriptor_id"], "policy calendar descriptor_id")
    for field in ("scope_key", "field", "expected_type"):
        _text(result[field], f"policy calendar {field}")
    for field in ("entry_id", "expected_unit"):
        if result[field] is not None:
            _text(result[field], f"policy calendar {field}")
    return result


def _bridge(value: object, kind: str, exchange: str) -> dict[str, object] | None:
    if kind == "calendar_range":
        if value is not None:
            raise ValueError("calendar range calendar_anchor_selector must be null")
        return None
    if type(value) is not dict or set(value) != {"selector", "exchange"}:
        raise ValueError("market range calendar_anchor_selector has invalid keys")
    bridge_exchange = _exchange(value["exchange"], "calendar anchor exchange")
    if bridge_exchange != exchange:
        raise ValueError("calendar anchor exchange must match exchange_scope")
    return {"selector": _context_selector(value["selector"]), "exchange": bridge_exchange}


def _freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, init=False)
class RangeConfig:
    schema_version: str
    capability: str
    kind: str
    anchor_descriptor_id: str
    calendar_descriptor_id: str
    source: str
    dataset: str
    endpoint_url: str
    http_method: str
    parser_id: str
    parser_version: str
    mapping_version: str
    normalizer_version: str
    request_version: str
    exchange_scope: str
    calendar_anchor_selector: Mapping[str, object] | None
    request_template: Mapping[str, object]
    pagination: str
    max_pages: int
    max_calendar_days_per_request: int
    timeout_seconds: int | float
    retry_base_seconds: int | float
    retry_max_attempts: int
    challenge_cooldown_seconds: int | float

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise ValueError("RangeConfig must be constructed by parse_range_entry")

    def to_dict(self) -> dict[str, object]:
        return _range_config_to_dict(self)

    @property
    def entry_id(self) -> str:
        return hashlib.sha256(_canonical(_range_config_to_dict(self))).hexdigest()


def _range_config_to_dict(config: object) -> dict[str, object]:
    if type(config) is not RangeConfig:
        raise ValueError("exact RangeConfig required")
    return {
        field: _thaw(object.__getattribute__(config, field)) for field in _RANGE_FIELDS
    }


def parse_range_entry(wire: dict) -> RangeConfig:
    """Parse one independent, closed range configuration ENTRY."""
    if type(wire) is not dict or set(wire) != _RANGE_FIELD_SET:
        raise ValueError("range config has unknown or missing keys")
    if wire["schema_version"] != "formal-range-source-config-v1":
        raise ValueError("range config schema_version is invalid")
    if wire["capability"] != "verified_market_window_v1":
        raise ValueError("range config capability is invalid")
    if type(wire["kind"]) is not str or wire["kind"] not in {"calendar_range", "market_range"}:
        raise ValueError("range config kind is invalid")
    kind = wire["kind"]
    _hash(wire["anchor_descriptor_id"], "range anchor_descriptor_id")
    _hash(wire["calendar_descriptor_id"], "range calendar_descriptor_id")
    if type(wire["source"]) is not str or wire["source"] not in _SOURCES:
        raise ValueError("range source is not an eligible official source")
    _text(wire["dataset"], "range dataset", version=True)
    _https_url(wire["endpoint_url"], "range endpoint_url")
    if type(wire["http_method"]) is not str or wire["http_method"] not in {"GET", "POST"}:
        raise ValueError("range http_method must be GET or POST")
    for field in (
        "parser_id",
        "parser_version",
        "mapping_version",
        "normalizer_version",
        "request_version",
    ):
        _text(wire[field], f"range {field}", version=True)
    if wire["request_version"] != "formal-range-request-v1":
        raise ValueError("range request_version is invalid")
    exchange = _exchange(wire["exchange_scope"], "range exchange_scope")
    bridge = _bridge(wire["calendar_anchor_selector"], kind, exchange)
    template = _request_template(wire["request_template"], wire["http_method"], kind)
    if type(wire["pagination"]) is not str or wire["pagination"] not in {
        "single_response_v1",
        "numbered_pages_v1",
    }:
        raise ValueError("range pagination is invalid")
    max_pages = _positive_integer(wire["max_pages"], "range max_pages")
    if wire["pagination"] == "single_response_v1" and max_pages != 1:
        raise ValueError("single_response_v1 requires max_pages=1")
    _positive_integer(
        wire["max_calendar_days_per_request"],
        "range max_calendar_days_per_request",
    )
    for field in (
        "timeout_seconds",
        "retry_base_seconds",
        "challenge_cooldown_seconds",
    ):
        _positive_number(wire[field], f"range {field}")
    _positive_integer(wire["retry_max_attempts"], "range retry_max_attempts")

    values = dict(wire)
    values["calendar_anchor_selector"] = bridge
    values["request_template"] = template
    result = object.__new__(RangeConfig)
    for field in _RANGE_FIELDS:
        value = values[field]
        if field in {"calendar_anchor_selector", "request_template"}:
            value = _freeze(value)
        object.__setattr__(result, field, value)
    return result


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


_interfaces = None


def _trusted_interfaces():
    global _interfaces
    if _interfaces is None:
        from .formal_context_schema import _descriptor
        from .formal_policy_registry import FormalPolicyRegistry
        from .formal_registry_manifest import VerifiedRegistryBundle
        from .formal_scoring_registry import FormalScoringRegistry

        _interfaces = (
            VerifiedRegistryBundle,
            VerifiedRegistryBundle.require_official,
            VerifiedRegistryBundle.blob,
            FormalScoringRegistry,
            FormalScoringRegistry.require_official,
            FormalPolicyRegistry,
            FormalPolicyRegistry.require_verified,
            FormalPolicyRegistry.canonical_bytes,
            _descriptor,
        )
    return _interfaces


def _derive_graph(bundle, scoring_registry, policy_registry):
    (
        bundle_type,
        require_bundle,
        blob_for,
        scoring_type,
        require_scoring,
        policy_type,
        require_policy,
        policy_bytes_for,
        validate_descriptor,
    ) = _trusted_interfaces()
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
    parent: object
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
    parent_record = _bindings_record(record.parent, current=current)
    if parent_record.bindings.get(record.key) is not value:
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

    __slots__ = ("__weakref__",)

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
        return _bindings_record(_binding_record(self).parent).root_hash

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

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise ValueError("RangeBindings must be loaded from a verified graph")

    def for_rule(self, rule_id: str, exchange: str) -> RangeBinding:
        record = _bindings_record(self)
        _text(rule_id, "range binding rule_id")
        _exchange(exchange, "range binding exchange")
        binding = record.bindings.get((rule_id, exchange))
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
            result,
            key,
            market,
            calendar,
            selector_snapshot,
            binding_hash,
            _canonical(_range_config_to_dict(market)),
            _canonical(_range_config_to_dict(calendar)),
        )
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
        binding_objects,
    )
    return result


__all__ = [
    "RangeBinding",
    "RangeBindings",
    "RangeConfig",
    "load_policy_range_bindings",
    "parse_range_entry",
]
