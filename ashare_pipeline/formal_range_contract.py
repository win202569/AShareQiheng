"""Same-root active-policy range bindings; no date coverage or execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import sys
import threading
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
    from . import formal_policy_registry as policy_module
    from .formal_policy_registry import FormalPolicyRegistry as policy_type
    from .formal_registry_manifest import VerifiedRegistryBundle as bundle_type
    from .formal_registry_manifest import (
        FormalRegistryManifest as manifest_type,
        VerifiedRegistryBlob as blob_type,
    )
    from .formal_scoring_registry import FormalScoringRegistry as scoring_type
    from .formal_batch_read_journal import _range_binding_lease_scope_authority
    from .formal_range_format import RangeConfig, parse_range_entry, _range_config_to_dict
    from . import formal_range_format as format_module
    from . import formal_context_schema as context_module

    require_bundle = bundle_type.require_official
    blob_for = bundle_type.blob
    require_scoring = scoring_type.require_official
    read_policy_sources = policy_module._read_authenticated_policy_sources
    validate_lease_scope = _range_binding_lease_scope_authority()
    get_frame = sys._getframe
    get_thread_identity = threading.get_ident
    manifest_envelope_fields = tuple(manifest_type.__dataclass_fields__)
    blob_envelope_fields = tuple(blob_type.__dataclass_fields__)

    module_globals = globals()
    # _range_catalog_from_source reads _load_canonical_object and the immutable
    # _LEGACY_CONFIG_FIELDS global; its parser/type/serializer are captured
    # closure references. parse_range_entry -> _bridge/_context_selector,
    # _request_template and its text/tree helpers, numeric validators and
    # _freeze. The serializer used by
    # current checks -> _thaw (recursive). Inventory every non-builtin global
    # reached by those call chains, including the module aliases they use.
    dependencies = tuple((module_globals, name, module_globals[name]) for name in (
        "_load_canonical_object", "_LEGACY_CONFIG_FIELDS", "_canonical", "_freeze", "_text", "_exchange",
        "RangeConfig", "parse_range_entry", "MappingProxyType", "ContextVar", "json", "hashlib",
        "sys", "threading", "weakref",
    )) + ((vars(sys), "_getframe", get_frame),
          (vars(threading), "get_ident", get_thread_identity)) + tuple((vars(format_module), name, vars(format_module)[name]) for name in (
        "RangeConfig", "parse_range_entry", "_range_config_to_dict", "_canonical",
        "_text", "_hash", "_exchange", "_positive_number", "_positive_integer",
        "_https_url", "_placeholder_text", "_template_tree", "_request_template",
        "_walk_strings", "_context_selector", "_bridge", "_freeze", "_thaw",
        "Mapping", "MappingProxyType", "json", "hashlib", "math", "re",
        "_SOURCES", "_EXCHANGES", "_IDENTIFIER", "_VERSION_IDENTIFIER", "_SHA256",
        "_PLACEHOLDER", "_PLACEHOLDERS", "_RANGE_FIELDS", "_RANGE_FIELD_SET",
        "_CONTEXT_SELECTOR_FIELDS",
    )) + ((vars(context_module), "_descriptor", validate_descriptor),
          (vars(json), "loads", json.loads), (vars(json), "dumps", json.dumps),
          (vars(hashlib), "sha256", hashlib.sha256),
          (vars(format_module.math), "isfinite", format_module.math.isfinite),
          (vars(format_module.re), "fullmatch", format_module.re.fullmatch))
    config_members = tuple(vars(RangeConfig).items())
    interfaces = (
        (bundle_type, "require_official", require_bundle),
        (bundle_type, "blob", blob_for),
        (scoring_type, "require_official", require_scoring),
        (policy_module, "_read_authenticated_policy_sources", read_policy_sources),
    )

    def _check_dependencies() -> None:
        if any(owner.get(name) is not expected for owner, name, expected in dependencies):
            raise ValueError("range binding dependency changed")
        current_members = vars(RangeConfig)
        if (set(current_members) != {name for name, _ in config_members}
                or any(current_members[name] is not value for name, value in config_members)):
            raise ValueError("range configuration interface changed")
        if any(getattr(cls, name, None) is not expected for cls, name, expected in interfaces):
            raise ValueError("range binding verifier changed")


    @dataclass(frozen=True)
    class _GraphSnapshot:
        manifest_bytes: bytes
        root_hash: str
        roles: tuple[tuple[str, bytes, str], ...]
        policy_bytes: bytes
        policy_hash: str


    def _capture_graph_snapshot(bundle, scoring_registry, policy_registry) -> _GraphSnapshot:
        _check_dependencies()
        if (type(bundle) is not bundle_type or type(scoring_registry) is not scoring_type
                or type(policy_registry) is not policy_type):
            raise ValueError("range bindings require exact genuine registry types")
        original_bundle, original_scoring, _, policy_bytes = read_policy_sources(policy_registry)
        if bundle is not original_bundle:
            require_bundle(bundle)
        if bundle is not original_bundle or scoring_registry is not original_scoring:
            require_scoring(scoring_registry, bundle)
        manifest = bundle.manifest
        manifest_bytes = manifest.canonical_json
        root_hash = hashlib.sha256(manifest_bytes).hexdigest()
        if root_hash != manifest.manifest_hash:
            raise ValueError("range binding registry root hash mismatch")
        roles = ("source", "mapping", "feature", "scoring", "industry", "cyclic",
                 "redline", "status", "event")
        if manifest.schema_version == "formal-registry-manifest-v2":
            roles += ("valuation_adapter",)
        snapshots = []
        for role in roles:
            blob = blob_for(bundle, role)
            raw = blob.canonical_json
            digest = hashlib.sha256(raw).hexdigest()
            if digest != blob.registry_hash or digest != getattr(manifest, role + "_registry_hash"):
                raise ValueError("range binding actual child hash mismatch")
            snapshots.append((role, raw, digest))
        return _GraphSnapshot(manifest_bytes, root_hash, tuple(snapshots), policy_bytes,
                              hashlib.sha256(policy_bytes).hexdigest())

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
        snapshot = _capture_graph_snapshot(bundle, scoring_registry, policy_registry)
        policy = json.loads(snapshot.policy_bytes)
        root_hash = snapshot.root_hash
        if policy["registry_manifest_hash"] != root_hash:
            raise ValueError("policy and range registry roots differ")
        role_hashes = {role: digest for role, _, digest in snapshot.roles}
        policy_role_hashes = {role: digest for role, digest in role_hashes.items()
                              if role != "valuation_adapter"}
        if policy["role_hashes"] != policy_role_hashes:
            raise ValueError("policy roles differ from the current range graph")

        raw_roles = {role: raw for role, raw, _ in snapshot.roles}
        source_wire, range_configs = _range_catalog_from_source(raw_roles["source"])
        wrapper = _load_canonical_object(raw_roles["scoring"], "scoring registry")
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
        return snapshot, definitions


    @dataclass(frozen=True)
    class _BindingsRecord:
        reference: weakref.ReferenceType[object]
        bundle: object
        scoring_registry: object
        policy_registry: object
        snapshot: _GraphSnapshot
        bindings: dict[tuple[str, str], object]
        manifest: object
        blobs: object
        role_objects: tuple[tuple[str, object], ...]
        manifest_envelope: tuple[tuple[str, type, object], ...]
        role_envelopes: tuple[tuple[str, tuple[tuple[str, type, object], ...]], ...]


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
    _binding_read_lease = ContextVar("formal_range_current_binding_read_lease", default=None)
    _sibling_request_read = ContextVar("formal_range_sibling_request_read", default=None)
    _lease_records = {}
    _sibling_records = {}


    def _envelope(value, fields):
        return tuple((name, type(object.__getattribute__(value, name)),
                      object.__getattribute__(value, name)) for name in fields)


    def _lightweight_current(record: _BindingsRecord) -> None:
        """Recheck mutable current fields without repeating signed graph parsing."""
        _check_dependencies()
        if (type(record.bundle) is not bundle_type
                or type(record.scoring_registry) is not scoring_type
                or type(record.policy_registry) is not policy_type):
            raise ValueError("range binding lease source identity changed")
        manifest = object.__getattribute__(record.bundle, "manifest")
        blobs = object.__getattribute__(record.bundle, "blobs")
        if manifest is not record.manifest or blobs is not record.blobs:
            raise ValueError("range binding lease graph object changed")
        if (type(manifest) is not manifest_type
                or _envelope(manifest, manifest_envelope_fields) != record.manifest_envelope):
            raise ValueError("range binding lease manifest envelope changed")
        manifest_bytes = object.__getattribute__(manifest, "canonical_json")
        if (type(manifest_bytes) is not bytes
                or manifest_bytes != record.snapshot.manifest_bytes
                or hashlib.sha256(manifest_bytes).hexdigest() != record.snapshot.root_hash
                or object.__getattribute__(manifest, "manifest_hash") != record.snapshot.root_hash):
            raise ValueError("range binding lease manifest changed")
        expected = {role: (raw, digest) for role, raw, digest in record.snapshot.roles}
        expected_envelopes = dict(record.role_envelopes)
        if tuple(role for role, _ in record.role_objects) != tuple(expected):
            raise ValueError("range binding lease roles changed")
        for role, sealed_blob in record.role_objects:
            blob = blobs.get(role)
            raw, digest = expected[role]
            if (blob is not sealed_blob or type(blob) is not blob_type or type(raw) is not bytes
                    or _envelope(blob, blob_envelope_fields) != expected_envelopes.get(role)):
                raise ValueError("range binding lease child object changed")
            current_raw = object.__getattribute__(blob, "canonical_json")
            if (type(current_raw) is not bytes or current_raw != raw
                    or hashlib.sha256(current_raw).hexdigest() != digest
                    or object.__getattribute__(blob, "registry_hash") != digest
                    or object.__getattribute__(blob, "registry_role") != role
                    or object.__getattribute__(manifest, role + "_registry_hash") != digest):
                raise ValueError("range binding lease child bytes changed")


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
            snapshot = _capture_graph_snapshot(
                record.bundle, record.scoring_registry, record.policy_registry
            )
            if snapshot != record.snapshot:
                raise ValueError("range binding sources changed")
        return record


    def _binding_record(value: object, *, current: bool = False) -> _BindingRecord:
        record = _binding_records.get(id(value))
        if type(value) is not RangeBinding or record is None or record.reference() is not value:
            raise ValueError("range binding is forged, copied, or unregistered")
        parent = record.parent()
        if parent is None or object.__getattribute__(value, "_RangeBinding__parent") is not parent:
            raise ValueError("range binding parent changed")
        lease = _binding_read_lease.get() if current else None
        if lease is not None:
            parent_record = _bindings_record(parent)
            identity = (parent_record.snapshot.root_hash, record.binding_hash, record.key)
            exact_binding = identity == lease[2]
            sibling = _sibling_request_read.get() if not exact_binding else None
            sibling_matches = (
                sibling is not None
                and sibling[0] is lease
                and sibling[1] == get_thread_identity()
                and sibling[2] is lease[1]
                and sibling[3:5] == tuple(lease[7:9])
                and parent_record.snapshot == lease[5]
                and parent_record.snapshot.root_hash == sibling[7]
                and next(digest for role, _, digest in parent_record.snapshot.roles
                         if role == "source") == sibling[6]
                and record.key[1] == sibling[8]
                and (record.calendar_bytes if sibling[10] == "calendar_range"
                     else record.market_bytes) == sibling[5]
            )
            if (get_thread_identity() != lease[0]
                    or parent_record.snapshot != lease[5]
                    or (not exact_binding and not sibling_matches)):
                raise ValueError("range binding lease is cross-thread, cross-binding, or stale")
            current_owner, current_epoch, current_phase = validate_lease_scope(lease[1])
            if ((current_owner, current_epoch, current_phase) != tuple(lease[6:9])):
                raise ValueError("range binding lease owner phase changed")
            _lightweight_current(lease[4])
            _lightweight_current(parent_record)
        else:
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


    class _BindingReadLease:
        __slots__ = ("__weakref__",)

        def __init__(self, *_args, **_kwargs):
            raise TypeError("range binding read leases require their sealed owner")

        def __copy__(self):
            raise TypeError("range binding read leases cannot be copied")

        def __deepcopy__(self, _memo):
            raise TypeError("range binding read leases cannot be copied")

        def __reduce__(self):
            raise TypeError("range binding read leases cannot be exported")

        def __reduce_ex__(self, _protocol):
            raise TypeError("range binding read leases cannot be exported")


    class _SiblingRequestRead:
        __slots__ = ("__weakref__",)

        def __init__(self, *_args, **_kwargs):
            raise TypeError("sibling request reads require their sealed range owner")

        def __copy__(self):
            raise TypeError("sibling request reads cannot be copied")

        def __deepcopy__(self, _memo):
            raise TypeError("sibling request reads cannot be copied")

        def __reduce__(self):
            raise TypeError("sibling request reads cannot be exported")

        def __reduce_ex__(self, _protocol):
            raise TypeError("sibling request reads cannot be exported")


    def open_sibling_request_read(request_description, request_fingerprint):
        """Authorize one genuine request to read an identical persisted sibling."""
        _check_dependencies()
        lease = _binding_read_lease.get()
        if lease is None:
            raise ValueError("sibling request read requires one active owner lease")
        prior = _sibling_request_read.get()
        if prior is not None:
            if prior[0] is not lease:
                raise ValueError("sibling request read belongs to another owner lease")
            prior_capability = lease[11]
            close_sibling_request_read(prior_capability)
        current_owner, current_epoch, current_phase = validate_lease_scope(lease[1])
        if ((current_owner, current_epoch, current_phase) != tuple(lease[6:9])
                or get_thread_identity() != lease[0]):
            raise ValueError("sibling request read owner phase changed")
        if (type(request_description) is not dict
                or set(request_description) != {"request", "config", "source_registry_hash",
                                                "binding_hash", "parent"}
                or type(request_description["request"]) is not dict
                or type(request_description["config"]) is not dict
                or type(request_description["source_registry_hash"]) is not str
                or type(request_description["binding_hash"]) is not str
                or type(request_fingerprint) is not str):
            raise ValueError("sibling request read contract is invalid")
        request = request_description["request"]
        if (request.get("kind") not in {"calendar_range", "market_range"}
                or hashlib.sha256(_canonical(request)).hexdigest() != request_fingerprint):
            raise ValueError("sibling request fingerprint differs")
        owner_reference = lease[4].bindings.get(lease[2][2])
        owner_binding = None if owner_reference is None else owner_reference()
        owner_record = _binding_record(owner_binding)
        kind = request["kind"]
        config_bytes = _canonical(request_description["config"])
        expected_config = (owner_record.calendar_config if kind == "calendar_range"
                           else owner_record.market_config)
        expected_bytes = (owner_record.calendar_bytes if kind == "calendar_range"
                          else owner_record.market_bytes)
        source_hash = next(digest for role, _, digest in lease[4].snapshot.roles
                           if role == "source")
        if (config_bytes != expected_bytes
                or request_description["binding_hash"] != owner_record.binding_hash
                or request_description["source_registry_hash"] != source_hash
                or request.get("registry_manifest_hash") != lease[2][0]
                or request.get("exchange") != owner_record.key[1]
                or request.get("range_config_id") != expected_config.entry_id):
            raise ValueError("sibling request differs from owner binding contract")
        state = (lease, get_thread_identity(), lease[1], current_epoch, current_phase,
                 config_bytes, source_hash, lease[2][0], owner_record.key[1],
                 request_fingerprint, kind)
        context_token = _sibling_request_read.set(state)
        result = object.__new__(_SiblingRequestRead)
        identity = id(result)
        reference = weakref.ref(result, lambda ref, key=identity:
            _sibling_records.pop(key, None)
            if _sibling_records.get(key) is not None
            and _sibling_records[key][0] is ref else None)
        _sibling_records[identity] = [reference, state, context_token, True]
        lease[11] = result
        return result


    def close_sibling_request_read(capability):
        saved = _sibling_records.get(id(capability))
        if (type(capability) is not _SiblingRequestRead or saved is None
                or saved[0]() is not capability or saved[3] is not True):
            raise ValueError("sibling request read is forged, copied, or closed")
        state, token = saved[1:3]
        if (get_thread_identity() != state[1]
                or _sibling_request_read.get() is not state
                or _binding_read_lease.get() is not state[0]):
            raise ValueError("sibling request read is cross-thread or out of order")
        _sibling_request_read.reset(token)
        saved[3] = False
        state[0][11] = None


    def open_current_binding_read_lease(value, owner_scope, operation_key):
        """Open one bounded owner operation; the returned token has no public behavior."""
        _check_dependencies()
        caller = get_frame(1)
        owner, epoch, phase = validate_lease_scope(owner_scope)
        owner_type = type(owner)
        calendar_code = vars(owner_type).get("select_calendar_batch_ticket")
        market_code = vars(owner_type).get("select_current_batch_ticket")
        calendar_code = None if calendar_code is None else calendar_code.__code__
        market_code = None if market_code is None else market_code.__code__
        if caller.f_locals.get("self") is not owner or caller.f_code not in {
                calendar_code, market_code}:
            raise ValueError("range binding lease cannot be nested, copied, or unbound")
        expected_key = (("calendar", caller.f_locals.get("as_of_utc"))
                        if caller.f_code is calendar_code else
                        ("market", caller.f_locals.get("security_id"),
                         caller.f_locals.get("as_of_utc")))
        if (operation_key != expected_key or any(type(item) is not str or not item
                                                  for item in expected_key)):
            raise ValueError("range binding lease operation key is not owner-derived")
        active = _binding_read_lease.get()
        if active is not None:
            _binding_record(value, current=True)
            nested = (caller.f_code is calendar_code and active[1] is owner_scope
                      and active[3][0] == "market"
                      and operation_key == ("calendar", active[3][-1])
                      and active[6] is owner and active[7] is epoch
                      and active[8] == phase and active[9] is False
                      and active[10] is False)
            if not nested:
                raise ValueError("range binding lease cannot be nested, copied, or unbound")
            active[9] = True
            active[10] = True
            state = active
            token = _binding_read_lease.set(state)
        else:
            child = _binding_record(value)
            parent = child.parent()
            parent_record = _bindings_record(parent)
            entry = _capture_graph_snapshot(
                parent_record.bundle, parent_record.scoring_registry,
                parent_record.policy_registry
            )
            if entry != parent_record.snapshot:
                raise ValueError("range binding sources changed before owner operation")
            _lightweight_current(parent_record)
            identity = (parent_record.snapshot.root_hash, child.binding_hash, child.key)
            state = [get_thread_identity(), owner_scope, identity, operation_key,
                     parent_record, entry, owner, epoch, phase, False, False, None]
            token = _binding_read_lease.set(state)
            nested = False
        lease = object.__new__(_BindingReadLease)
        identity = id(lease)
        reference = weakref.ref(lease, lambda ref, key=identity:
            _lease_records.pop(key, None)
            if _lease_records.get(key) is not None
            and _lease_records[key][0] is ref else None)
        _lease_records[identity] = [reference, state, token, nested, True]
        return lease


    def close_current_binding_read_lease(lease):
        saved = _lease_records.get(id(lease))
        if (type(lease) is not _BindingReadLease or saved is None
                or saved[0]() is not lease or saved[4] is not True):
            raise ValueError("range binding read lease is forged, copied, or closed")
        state, token, nested = saved[1:4]
        if get_thread_identity() != state[0] or _binding_read_lease.get() is not state:
            raise ValueError("range binding read lease is cross-thread or out of order")
        pending = None
        try:
            current_scope = validate_lease_scope(state[1])
            if current_scope != (state[6], state[7], state[8]):
                raise ValueError("range binding read lease owner phase changed")
        except BaseException as error:
            pending = error
        if nested:
            if state[10] is not True:
                raise ValueError("range binding calendar child lease is out of order")
            if state[11] is not None:
                close_sibling_request_read(state[11])
            _binding_read_lease.reset(token)
            state[10] = False
            saved[4] = False
            if pending is not None:
                raise pending
            return
        if state[10] is not False:
            raise ValueError("range binding outer lease still owns a calendar child")
        if state[11] is not None:
            close_sibling_request_read(state[11])
        parent_record, entry = state[4:6]
        try:
            exit_snapshot = _capture_graph_snapshot(
                parent_record.bundle, parent_record.scoring_registry,
                parent_record.policy_registry
            )
            if exit_snapshot != entry or exit_snapshot != parent_record.snapshot:
                raise ValueError("range binding sources changed during owner operation")
        except BaseException as error:
            if pending is None:
                pending = error
        _binding_read_lease.reset(token)
        saved[4] = False
        if pending is not None:
            raise pending


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
            return _bindings_record(_binding_record(self).parent()).snapshot.root_hash

        @property
        def source_registry_hash(self) -> str:
            return next(digest for role, _, digest in
                        _bindings_record(_binding_record(self).parent()).snapshot.roles
                        if role == "source")

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
        snapshot, definitions = _derive_graph(
            bundle, scoring_registry, policy_registry
        )
        root_hash = snapshot.root_hash
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

        if _capture_graph_snapshot(bundle, scoring_registry, policy_registry) != snapshot:
            raise ValueError("range binding sources changed during loading")
        reference = weakref.ref(result, forget_bindings)
        _bindings_records[identity] = _BindingsRecord(
            reference,
            bundle,
            scoring_registry,
            policy_registry,
            snapshot,
            {key: weakref.ref(binding) for key, binding in binding_objects.items()},
            object.__getattribute__(bundle, "manifest"),
            object.__getattribute__(bundle, "blobs"),
            tuple((role, blob_for(bundle, role)) for role, _, _ in snapshot.roles),
            _envelope(object.__getattribute__(bundle, "manifest"), manifest_envelope_fields),
            tuple((role, _envelope(blob_for(bundle, role), blob_envelope_fields))
                  for role, _, _ in snapshot.roles),
        )
        return result

    def read_planning_binding(value: object) -> Mapping[str, object]:
        """Read a current binding through the original owner's sealed records."""
        child = _binding_record(value, current=True)
        parent = _bindings_record(child.parent())
        return MappingProxyType({
            "market_config": child.market_config,
            "calendar_config": child.calendar_config,
            "registry_manifest_hash": parent.snapshot.root_hash,
            "source_registry_hash": dict((role, digest) for role, _, digest in parent.snapshot.roles)["source"],
            "binding_hash": child.binding_hash,
            "rule_id": child.key[0],
            "exchange": child.key[1],
        })

    def lookup_planning_binding(bindings, binding_hash, exchange):
        """Select one sealed binding without probing unrelated child bindings."""
        parent = _bindings_record(bindings)
        _text(binding_hash, "range binding hash")
        if len(binding_hash) != 64 or any(c not in "0123456789abcdef" for c in binding_hash):
            raise ValueError("range binding hash must be canonical sha256")
        _exchange(exchange, "range binding exchange")
        matches = []
        for key, reference in parent.bindings.items():
            child = reference()
            record = None if child is None else _binding_records.get(id(child))
            if (record is not None and record.reference() is child and key[1] == exchange
                    and record.binding_hash == binding_hash):
                matches.append(child)
        if len(matches) != 1:
            raise ValueError("range task binding absent or ambiguous")
        _binding_record(matches[0], current=True)
        return matches[0]

    return (RangeBinding, RangeBindings, load_policy_range_bindings, read_planning_binding,
            lookup_planning_binding, open_current_binding_read_lease,
            close_current_binding_read_lease, open_sibling_request_read,
            close_sibling_request_read)


(RangeBinding, RangeBindings, load_policy_range_bindings,
 _read_range_binding_planning, _lookup_range_binding_planning,
 _open_current_binding_read_lease,
 _close_current_binding_read_lease, _open_sibling_request_read,
 _close_sibling_request_read) = _build_range_bindings_contract()
del _build_range_bindings_contract


def _make_range_binding_authority():
    """Expose immutable genuine anchors to the range source during module init."""

    binding_type = RangeBinding
    require_current = RangeBinding.require_current
    calendar_config_get = RangeBinding.calendar_config.fget
    manifest_hash_get = RangeBinding.registry_manifest_hash.fget
    source_hash_get = RangeBinding.source_registry_hash.fget
    assert calendar_config_get is not None and manifest_hash_get is not None
    assert source_hash_get is not None

    def authority():
        return (
            binding_type,
            require_current,
            calendar_config_get,
            manifest_hash_get,
            source_hash_get,
        )

    return authority


_range_binding_authority = _make_range_binding_authority()
del _make_range_binding_authority


def _make_range_binding_planning_authority():
    """Expose the original type and owner reader, without changing legacy anchors."""
    binding_type = RangeBinding
    read = _read_range_binding_planning

    def authority():
        return binding_type, read

    return authority


_range_binding_planning_authority = _make_range_binding_planning_authority()
del _make_range_binding_planning_authority, _read_range_binding_planning


def _make_range_binding_lookup_authority():
    lookup = _lookup_range_binding_planning

    def authority():
        return lookup

    return authority


_range_binding_lookup_authority = _make_range_binding_lookup_authority()
del _make_range_binding_lookup_authority, _lookup_range_binding_planning


def _make_range_binding_read_lease_authority():
    open_lease = _open_current_binding_read_lease
    close_lease = _close_current_binding_read_lease

    def authority():
        return open_lease, close_lease

    return authority


_range_binding_read_lease_authority = _make_range_binding_read_lease_authority()
del (_make_range_binding_read_lease_authority, _open_current_binding_read_lease,
     _close_current_binding_read_lease)


def _make_range_binding_sibling_read_authority():
    open_read = _open_sibling_request_read
    close_read = _close_sibling_request_read

    def authority():
        return open_read, close_read

    return authority


_range_binding_sibling_read_authority = _make_range_binding_sibling_read_authority()
del (_make_range_binding_sibling_read_authority, _open_sibling_request_read,
     _close_sibling_request_read)


__all__ = [
    "RangeBinding",
    "RangeBindings",
    "RangeConfig",
    "load_policy_range_bindings",
    "parse_range_entry",
]
