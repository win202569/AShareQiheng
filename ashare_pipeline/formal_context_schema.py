"""Canonical Context contracts; official trust is acquired only from signed bundles."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
import weakref
from typing import Protocol

from .formal_evidence import OfficialRequest, OfficialSnapshotRef, VerifiedCalendarBinding
from .formal_sources import CalendarSelector, SignedSourceRegistry
from .formal_registry_manifest import FormalRegistryBundleLoader
from .formal_time import SHANGHAI


CONTEXT_KINDS = ("trading_calendar", "market_close", "security_state", "industry_snapshot",
                 "regulatory_state", "event_calendar", "consensus_snapshot")
_ROLES = {"source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event"}
_FACT_FIELDS = set("context_kind scope_key security_id as_of_utc value no_coverage published_at_utc effective_at_utc source_updated_at_utc captured_at_utc refresh_generation source_snapshot_id source_content_sha256 parser_id parser_version mapping_version registry_manifest_hash evidence".split())
_ISSUE_FIELDS = set("code context_kind scope_key security_id as_of_utc details".split())
_BINDING_FIELDS = set("snapshot_id manifest_sha256 exchange freeze_at_utc registry_manifest_hash selector_hash prerequisite_task_id".split())


def _json_tree(value, seen=None):
    """Reject aliases as well as cycles before detaching a JSON-native tree."""
    if seen is None:
        seen = set()
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) not in (list, dict):
        raise ValueError("Context requires finite JSON-native values")
    if id(value) in seen:
        raise ValueError("Context JSON aliases or cycles are forbidden")
    seen.add(id(value))
    if type(value) is list:
        return [_json_tree(item, seen) for item in value]
    if any(type(key) is not str for key in value):
        raise ValueError("Context JSON keys must be exact strings")
    return {key: _json_tree(item, seen) for key, item in value.items()}


def _canonical(value):
    return json.dumps(_json_tree(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _load(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate Context JSON key")
            result[key] = value
        return result
    if type(raw) is not bytes:
        raise ValueError("canonical Context bytes required")
    try:
        wire = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        if type(wire) is not dict or _canonical(wire) != raw:
            raise ValueError("noncanonical Context object")
        return wire
    except (UnicodeError, TypeError, RecursionError) as error:
        raise ValueError("invalid canonical Context object") from error


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("Context object has missing or extra fields")


def _text(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value) is None:
        raise ValueError("Context requires an exact identifier")
    return value


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("Context requires a lowercase SHA-256")
    return value


def _timestamp(value):
    if type(value) is not str:
        raise ValueError("Context requires an exact aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Context timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.isoformat() != value:
        raise ValueError("Context requires an exact aware ISO-8601 timestamp")
    return parsed


def _date(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Context date is invalid")
    return value


def _security(value):
    if value is not None and (type(value) is not str or re.fullmatch(r"(?:SH|SZ|BJ)[0-9]{6}", value) is None):
        raise ValueError("Context security ID must be exact SH/SZ/BJ identifier")
    return value


def _exchange(value):
    if type(value) is not str or value not in ("SH", "SZ", "BJ"):
        raise ValueError("Context exchange is invalid")
    return value


def _decimal(value, *, positive=False, allow_negative=False):
    if type(value) is not str:
        raise ValueError("Context quantity must be a canonical decimal string")
    try:
        number = Decimal(value)
        if not number.is_finite() or (not allow_negative and number < 0) or (positive and number <= 0):
            raise ValueError("Context quantity is not finite or in range")
        canonical = format(number, "f")
        if "." in canonical:
            canonical = canonical.rstrip("0").rstrip(".")
        if number == 0:
            canonical = "0"
        if value != canonical:
            raise ValueError("Context decimal string is not canonical")
    except InvalidOperation as error:
        raise ValueError("Context decimal is invalid") from error


def _ordered(items, *, nonempty=False):
    if type(items) is not list or (nonempty and not items):
        raise ValueError("Context ordered array is missing")
    if items != sorted(set(items)):
        raise ValueError("Context array must be sorted and unique")


def _logical(wire):
    if type(wire["context_kind"]) is not str or wire["context_kind"] not in CONTEXT_KINDS:
        raise ValueError("unsupported Context kind")
    _text(wire["scope_key"])
    _security(wire["security_id"])
    _timestamp(wire["as_of_utc"])


def _validate_value(kind, value, no_coverage, as_of):
    if type(no_coverage) is not bool:
        raise ValueError("no_coverage must be an exact bool")
    freeze = _timestamp(as_of).astimezone(SHANGHAI).date().isoformat()
    if no_coverage and kind != "consensus_snapshot":
        raise ValueError("no_coverage is consensus-only")
    if kind == "trading_calendar":
        _keys(value, ("exchange", "calendar_version", "trading_days"))
        _exchange(value["exchange"])
        _text(value["calendar_version"])
        _ordered(value["trading_days"], nonempty=True)
        for day in value["trading_days"]:
            _date(day)
    elif kind == "market_close":
        _keys(value, "exchange exchange_allows_trading volume turnover is_effective_trade valid_close valid_close_date stale_trading_days".split())
        _exchange(value["exchange"])
        for field in ("exchange_allows_trading", "is_effective_trade"):
            if type(value[field]) is not bool:
                raise ValueError("market booleans must be exact")
        _decimal(value["volume"])
        _decimal(value["turnover"])
        _decimal(value["valid_close"], positive=True)
        _date(value["valid_close_date"])
        stale = value["stale_trading_days"]
        if type(stale) is not int or stale < 0:
            raise ValueError("stale days must be an exact nonnegative integer")
        if value["is_effective_trade"]:
            if stale != 0 or value["valid_close_date"] != freeze or not value["exchange_allows_trading"]:
                raise ValueError("effective trade must have the freeze-date close and zero stale days")
        elif stale <= 0 or value["valid_close_date"] >= freeze:
            raise ValueError("stale close requires positive stale days and a prior date")
    elif kind == "security_state":
        _keys(value, "is_st is_star_st listing_status forced_delist_risk suspended".split())
        if value["listing_status"] not in ("listed", "delisting_arrangement", "delisted"):
            raise ValueError("unsupported listing status")
        if any(type(value[field]) is not bool for field in value if field != "listing_status"):
            raise ValueError("security state flags must be exact booleans")
    elif kind == "industry_snapshot":
        _keys(value, "classification_system primary_industry secondary_industry source_version effective_date mapping_sha256".split())
        if value["classification_system"] != "SW2021":
            raise ValueError("unsupported industry classification")
        for field in ("primary_industry", "secondary_industry", "source_version"):
            _text(value[field])
        _hash(value["mapping_sha256"])
        if _date(value["effective_date"]) > freeze:
            raise ValueError("future industry effective date")
    elif kind in ("regulatory_state", "event_calendar"):
        key = "flags" if kind == "regulatory_state" else "events"
        _keys(value, (key,))
        entries = value[key]
        if type(entries) is not list:
            raise ValueError("Context entries must be a canonical array")
        ids = []
        for entry in entries:
            if key == "flags":
                _keys(entry, ("flag_id", "active"))
                ids.append(_text(entry["flag_id"]))
                if type(entry["active"]) is not bool:
                    raise ValueError("regulatory active flag must be exact bool")
            else:
                _keys(entry, ("event_id", "event_date", "quantified_value", "unit"))
                ids.append(_text(entry["event_id"]))
                _date(entry["event_date"])
                _decimal(entry["quantified_value"], allow_negative=True)
                _text(entry["unit"])
        _ordered(ids)
    elif kind == "consensus_snapshot":
        _keys(value, ("coverage_status", "estimates"))
        estimates = value["estimates"]
        if type(estimates) is not list or any(type(item) is not dict or not item for item in estimates):
            raise ValueError("consensus estimates must be explicit JSON objects")
        if value["coverage_status"] == "covered":
            if no_coverage or not estimates:
                raise ValueError("covered consensus requires nonempty estimates")
        elif value["coverage_status"] != "no_valid_coverage" or not no_coverage or estimates:
            raise ValueError("no coverage requires explicit status and no estimates")


def _validate_evidence(value):
    _keys(value, ("descriptor_id", "normalizer_version", "normalization_input_hash", "upstream_generation", "relevant_registry_hashes", "request_fingerprint", "calendar_binding"))
    _hash(value["descriptor_id"])
    _hash(value["request_fingerprint"])
    _text(value["normalizer_version"])
    _text(value["upstream_generation"])
    _hash(value["normalization_input_hash"])
    roles = []
    if type(value["relevant_registry_hashes"]) is not list:
        raise ValueError("relevant registry hashes must be an array")
    for pair in value["relevant_registry_hashes"]:
        if type(pair) is not list or len(pair) != 2 or pair[0] not in _ROLES:
            raise ValueError("invalid relevant registry role")
        roles.append(pair[0])
        _hash(pair[1])
    _ordered(roles, nonempty=True)
    if not {"source", "scoring"}.issubset(roles):
        raise ValueError("Context provenance requires source and scoring roles")
    binding = value["calendar_binding"]
    if binding is not None:
        _keys(binding, _BINDING_FIELDS)
        for field in ("manifest_sha256", "registry_manifest_hash", "selector_hash"):
            _hash(binding[field])
        for field in ("snapshot_id", "prerequisite_task_id"):
            _text(binding[field])
        _exchange(binding["exchange"])
        _timestamp(binding["freeze_at_utc"])


def _validate_fact(wire):
    _keys(wire, _FACT_FIELDS)
    _logical(wire)
    for field in ("refresh_generation", "source_content_sha256", "registry_manifest_hash"):
        _hash(wire[field])
    for field in ("source_snapshot_id", "parser_id", "parser_version", "mapping_version"):
        _text(wire[field])
    freeze = _timestamp(wire["as_of_utc"])
    for field in ("published_at_utc", "effective_at_utc", "source_updated_at_utc"):
        if field == "source_updated_at_utc" and wire[field] is None:
            continue
        if _timestamp(wire[field]) > freeze:
            raise ValueError("Context source time exceeds the as-of cutoff")
    _timestamp(wire["captured_at_utc"])
    _validate_evidence(wire["evidence"])
    _validate_value(wire["context_kind"], wire["value"], wire["no_coverage"], wire["as_of_utc"])


def _validate_issue(wire):
    _keys(wire, _ISSUE_FIELDS)
    _logical(wire)
    _text(wire["code"])
    if type(wire["details"]) is not dict:
        raise ValueError("Context issue details must be an object")


def _record_type(name, validate):
    seals = {}

    class Record:
        __slots__ = ("_canonical", "__weakref__")

        def __init__(self, *args, **kwargs):
            raise ValueError(f"{name} requires create/from_dict")

        def __setattr__(self, name, value):
            raise AttributeError("Context records are immutable")

        @classmethod
        def create(cls, **wire):
            if cls is not Record:
                raise ValueError("exact Context record type required")
            raw = _canonical(wire)
            validate(_load(raw))
            item = object.__new__(Record)
            object.__setattr__(item, "_canonical", raw)
            identity = id(item)
            seals[identity] = (weakref.ref(item, lambda _: seals.pop(identity, None)), raw)
            return item

        def canonical_bytes(self):
            seal = seals.get(id(self))
            if type(self) is not Record or seal is None or seal[0]() is not self or type(self._canonical) is not bytes or self._canonical != seal[1]:
                raise ValueError("Context record is forged or mutated")
            return seal[1]

        @property
        def id(self):
            return hashlib.sha256(self.canonical_bytes()).hexdigest()

        def to_dict(self):
            return {**_load(self.canonical_bytes()), "id": self.id}

        @classmethod
        def from_dict(cls, wire):
            detached = _json_tree(wire)
            if type(detached) is not dict or "id" not in detached:
                raise ValueError("Context record ID is missing")
            expected = detached.pop("id")
            item = cls.create(**detached)
            if item.id != expected:
                raise ValueError("Context canonical ID mismatch")
            return item

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            wire = _load(self.canonical_bytes())
            if name not in wire:
                raise AttributeError(name)
            return wire[name]

    Record.__name__ = name
    Record.__qualname__ = name
    return Record


FormalContextFact = _record_type("FormalContextFact", _validate_fact)
FormalContextIssue = _record_type("FormalContextIssue", _validate_issue)
del _record_type


@dataclass(frozen=True)
class FormalContextVersionView:
    published_at_utc: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    content_hash: str

    @classmethod
    def from_fact(cls, fact):
        if type(fact) is not FormalContextFact:
            raise ValueError("exact Context fact required")
        wire = fact.to_dict()
        return cls(wire["published_at_utc"], wire["source_updated_at_utc"],
                   wire["captured_at_utc"], wire["source_content_sha256"])


class FormalContextNormalizer(Protocol):
    normalizer_version: str

    def normalize(self, *, request: FormalContextRequest, snapshot: OfficialSnapshotRef,
                  raw_bytes: bytes) -> tuple[FormalContextFact, ...]: ...


_DESCRIPTOR_FIELDS = set("context_kind scope_key security_scope request_security period_rule exchange_rule fixed_exchange source dataset parser_id parser_version mapping_version request_version normalizer_version generation_namespace referenced_roles calendar_selector bootstrap_calendar allowed_regulatory_flags allowed_event_codes".split())


def _selector(wire):
    if wire is None:
        return None
    _keys(wire, ("context_kind", "scope_key", "exchange", "as_of_rule"))
    return CalendarSelector(**wire)


def _descriptor(wire):
    _keys(wire, _DESCRIPTOR_FIELDS)
    if wire["context_kind"] not in CONTEXT_KINDS:
        raise ValueError("unsupported Context descriptor kind")
    for field in ("scope_key", "source", "dataset", "parser_id", "parser_version", "mapping_version", "request_version", "normalizer_version", "generation_namespace"):
        _text(wire[field])
    if (wire["security_scope"], wire["request_security"]) not in (("none", "none"), ("security", "input_security")):
        raise ValueError("Context descriptor security rules disagree")
    if wire["period_rule"] not in ("none", "freeze_date_cn"):
        raise ValueError("unsupported Context period rule")
    if wire["exchange_rule"] == "fixed_exchange":
        _exchange(wire["fixed_exchange"])
    elif wire["exchange_rule"] not in ("none", "security_exchange") or wire["fixed_exchange"] is not None:
        raise ValueError("Context descriptor exchange rule is invalid")
    if wire["exchange_rule"] == "security_exchange" and wire["security_scope"] != "security":
        raise ValueError("security exchange requires an input security")
    roles = wire["referenced_roles"]
    _ordered(roles, nonempty=True)
    if not set(roles).issubset(_ROLES) or not {"source", "scoring"}.issubset(roles):
        raise ValueError("Context descriptor has invalid referenced roles")
    for field in ("allowed_regulatory_flags", "allowed_event_codes"):
        _ordered(wire[field])
        for value in wire[field]:
            _text(value)
    selector = _selector(wire["calendar_selector"])
    if type(wire["bootstrap_calendar"]) is not bool:
        raise ValueError("bootstrap_calendar must be exact bool")
    if wire["bootstrap_calendar"] and (wire["context_kind"] != "trading_calendar" or selector is not None):
        raise ValueError("only unbound trading calendars may bootstrap")


def _normalization_input_hash(fact, request, snapshot):
    wire = fact.to_dict()
    wire.pop("id")
    wire["evidence"].pop("normalization_input_hash")
    return hashlib.sha256(_canonical(dict(schema_version="formal-context-normalization-input-v1",
        descriptor_id=request.descriptor_id, normalizer_version=request.normalizer_version,
        request=request.to_dict(), source_snapshot_manifest_sha256=snapshot.manifest_sha256,
        source_content_sha256=snapshot.content_sha256, fact=wire))).hexdigest()


def _fact_matches(fact, request, snapshot, descriptor):
    if type(fact) is not FormalContextFact or type(request) is not FormalContextRequest or type(snapshot) is not OfficialSnapshotRef:
        raise ValueError("exact Context records and source reference required")
    wire = fact.to_dict()
    for field in ("context_kind", "scope_key", "security_id", "as_of_utc", "refresh_generation", "registry_manifest_hash", "parser_id", "parser_version", "mapping_version"):
        if _canonical({"value": wire[field]}) != _canonical({"value": getattr(request, field)}):
            raise ValueError(f"Context fact {field} disagrees with signed request")
    evidence = dict(wire["evidence"])
    normalization_hash = evidence.pop("normalization_input_hash")
    if _canonical(evidence) != _canonical(request.evidence):
        raise ValueError("Context fact evidence differs from signed request")
    if normalization_hash != _normalization_input_hash(fact, request, snapshot):
        raise ValueError("Context normalization input hash mismatch")
    for field in ("published_at_utc", "effective_at_utc", "source_updated_at_utc", "captured_at_utc", "parser_id", "parser_version", "mapping_version", "refresh_generation"):
        if wire[field] != getattr(snapshot, field):
            raise ValueError(f"Context fact source {field} mismatch")
    if wire["source_snapshot_id"] != snapshot.snapshot_id or wire["source_content_sha256"] != snapshot.content_sha256:
        raise ValueError("Context fact snapshot identity mismatch")
    official = request.official_request
    if any(getattr(snapshot, field) != getattr(official, field) for field in ("source", "dataset", "security_id", "period_or_date", "exchange")):
        raise ValueError("Context snapshot request identity mismatch")
    if snapshot.request_fingerprint != official.request_fingerprint or snapshot.verification_status != "verified":
        raise ValueError("Context snapshot request or verification mismatch")
    binding = request.calendar_binding
    if binding is None:
        if snapshot.published_precision != "timestamp" or snapshot.effective_time_evidence_hash is not None:
            raise ValueError("timestamp Context cannot use calendar evidence")
    elif snapshot.published_precision != "date_only" or snapshot.effective_time_evidence_hash != binding.manifest_sha256:
        raise ValueError("Context effective-time evidence differs from calendar binding")
    value = wire["value"]
    if wire["context_kind"] in ("trading_calendar", "market_close"):
        if value["exchange"] != official.exchange:
            raise ValueError("Context value exchange differs from signed request")
    if wire["context_kind"] == "regulatory_state":
        if any(entry["flag_id"] not in descriptor["allowed_regulatory_flags"] for entry in value["flags"]):
            raise ValueError("regulatory flag is not descriptor-authorized")
    if wire["context_kind"] == "event_calendar":
        if any(entry["event_id"] not in descriptor["allowed_event_codes"] for entry in value["events"]):
            raise ValueError("event code is not descriptor-authorized")


def _trusted_context_types():
    """Keep every capability mint and seal table in a non-exported closure."""
    def capability(name):
        seals = {}

        class Capability:
            __slots__ = ("_canonical", "__weakref__")

            def __init__(self, *args, **kwargs):
                raise ValueError(f"{name} requires verified Context resolution")

            def __setattr__(self, name, value):
                raise AttributeError("Context capabilities are immutable")

            def canonical_bytes(self):
                seal = seals.get(id(self))
                if type(self) is not Capability or seal is None or seal[0]() is not self or type(self._canonical) is not bytes or self._canonical != seal[1]:
                    raise ValueError("Context capability is forged or mutated")
                return seal[1]

            def to_dict(self):
                return _load(self.canonical_bytes())

            def __getattr__(self, field):
                if field.startswith("_"):
                    raise AttributeError(field)
                wire = self.to_dict()
                if field not in wire:
                    raise AttributeError(field)
                value = wire[field]
                if field == "official_request":
                    return OfficialRequest(**value)
                if field == "calendar_binding":
                    return VerifiedCalendarBinding(**value) if value is not None else None
                if field == "relevant_registry_hashes":
                    return tuple(tuple(pair) for pair in value)
                if field == "facts":
                    return tuple(FormalContextFact.from_dict(item) for item in value)
                return value

        def mint(wire):
            raw = _canonical(wire)
            item = object.__new__(Capability)
            object.__setattr__(item, "_canonical", raw)
            identity = id(item)
            seals[identity] = (weakref.ref(item, lambda _: seals.pop(identity, None)), raw)
            return item

        Capability.__name__ = name
        Capability.__qualname__ = name
        return Capability, mint

    Request, mint_request = capability("FormalContextRequest")
    Normalization, mint_normalization = capability("FormalContextNormalization")
    registry_seals = {}
    resolver_seals = {}
    request_descriptors = {}

    def verify_context_fact(fact, request, snapshot):
        """Use only the private descriptor of a sealed, freshly resolved request."""
        if type(request) is not Request:
            raise ValueError("exact resolved Context request required")
        request.canonical_bytes()
        record = request_descriptors.get(id(request))
        if record is None or record[0]() is not request:
            raise ValueError("Context request descriptor seal is missing")
        raw = record[1]
        if hashlib.sha256(raw).hexdigest() != request.descriptor_id:
            raise ValueError("Context request descriptor identity mismatch")
        _fact_matches(fact, request, snapshot, _load(raw))

    def registry_state(registry):
        record = registry_seals.get(id(registry))
        if type(registry) is not Registry or record is None or record[0]() is not registry:
            raise ValueError("Context registry was not loaded from a verified bundle")
        return record[1:]

    class Registry:
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise ValueError("Context registry requires load from StateStore")

        @classmethod
        def load(cls, state_store, registry_signature_verifier, registry_manifest_hash):
            from .state_store import StateStore
            if cls is not Registry or type(state_store) is not StateStore:
                raise ValueError("Context registry requires exact StateStore")
            bundle = FormalRegistryBundleLoader(state_store, registry_signature_verifier).load(registry_manifest_hash)
            bundle.require_official()
            scoring = bundle.blob("scoring")
            wire = _load(scoring.canonical_json)
            _keys(wire, ("registry_role", "schema_version", "descriptors"))
            if wire["registry_role"] != "scoring" or wire["schema_version"] != "formal-context-registry-v1":
                raise ValueError("unsupported Context registry wrapper")
            if type(wire["descriptors"]) is not list:
                raise ValueError("Context descriptors must be a canonical array")
            seen = set()
            for descriptor in wire["descriptors"]:
                _descriptor(descriptor)
                identity = (descriptor["context_kind"], descriptor["scope_key"], descriptor["security_scope"])
                if identity in seen:
                    raise ValueError("duplicate Context descriptor")
                seen.add(identity)
            source = bundle.blob("source")
            sources = SignedSourceRegistry.from_signed_bytes(source.canonical_json, source.signature, source.key_id, registry_signature_verifier)
            item = object.__new__(Registry)
            identity = id(item)
            registry_seals[identity] = (weakref.ref(item, lambda _: registry_seals.pop(identity, None)),
                state_store, registry_signature_verifier, registry_manifest_hash, scoring.canonical_json,
                tuple((role, bundle.blob(role).registry_hash) for role in sorted(_ROLES)), sources)
            return item

        def descriptor_for(self, request):
            if type(request) is not Request:
                raise ValueError("exact resolved Context request required")
            request.to_dict()
            state, verifier, root, _, _, _ = registry_state(self)
            current = Registry.load(state, verifier, root)
            return select_descriptor(current, request.context_kind, request.scope_key, request.security_id)

        def normalize_verified(self, request, snapshot, raw_bytes, normalizer, *, task_id: str, worker_id: str):
            from .formal_snapshot_repository import FormalSnapshotRepository
            from .formal_context_repository import _require_context_writer
            state, verifier, root, _, _, _ = registry_state(self)
            if type(request) is not Request or type(snapshot) is not OfficialSnapshotRef or type(raw_bytes) is not bytes:
                raise ValueError("normalization requires exact verified Context inputs")
            request_wire = request.to_dict()
            if request.registry_manifest_hash != root:
                raise ValueError("normalization root mismatch")
            current_request = Resolver(state, verifier).resolve(context_kind=request.context_kind, scope_key=request.scope_key,
                security_id=request.security_id, as_of_utc=request.as_of_utc, registry_manifest_hash=root,
                upstream_generation=request.upstream_generation)
            if current_request.canonical_bytes() != request.canonical_bytes():
                raise ValueError("normalization request is stale or mismatched")
            version = getattr(normalizer, "normalizer_version", None)
            if type(version) is not str or version != current_request.normalizer_version or not callable(getattr(normalizer, "normalize", None)):
                raise ValueError("missing or unsupported Context normalizer version")
            repository = FormalSnapshotRepository(state._configured_formal_snapshot_store_for_repository().root, state)
            ref = repository.get_verified_by_manifest(snapshot.manifest_sha256)
            before = asdict(ref)
            if _canonical(asdict(snapshot)) != _canonical(before) or repository.read_verified_raw(ref) != raw_bytes or hashlib.sha256(raw_bytes).hexdigest() != ref.content_sha256:
                raise ValueError("normalization snapshot or raw SHA-256 mismatch")
            with state._transaction() as connection:
                writer = _require_context_writer(state, connection, ref, task_id=task_id, worker_id=worker_id)
            candidates = normalizer.normalize(request=current_request, snapshot=ref, raw_bytes=raw_bytes)
            if type(candidates) is not tuple or not candidates:
                raise ValueError("normalization requires explicit nonempty Context facts")
            if getattr(normalizer, "normalizer_version", None) != version or _canonical(asdict(ref)) != _canonical(before):
                raise ValueError("normalizer mutated its version or verified source reference")
            if current_request.to_dict() != request_wire:
                raise ValueError("normalizer mutated the signed request")
            facts = []
            for fact in candidates:
                verify_context_fact(fact, current_request, ref)
                facts.append(FormalContextFact.from_dict(fact.to_dict()).to_dict())
            if len({fact["id"] for fact in facts}) != len(facts):
                raise ValueError("duplicate normalized Context facts")
            after_request = Resolver(state, verifier).resolve(context_kind=request.context_kind, scope_key=request.scope_key,
                security_id=request.security_id, as_of_utc=request.as_of_utc, registry_manifest_hash=root,
                upstream_generation=request.upstream_generation)
            if after_request.canonical_bytes() != current_request.canonical_bytes() or repository.read_verified_raw(ref) != raw_bytes:
                raise ValueError("Context normalization changed during verification")
            with state._transaction() as connection:
                _require_context_writer(state, connection, ref, task_id=task_id, worker_id=worker_id,
                    expected_writer=writer)
            return mint_normalization(dict(registry_manifest_hash=root, request=request_wire, facts=facts, writer=writer))

    def select_descriptor(registry, kind, scope_key, security_id):
        if type(kind) is not str or kind not in CONTEXT_KINDS:
            raise ValueError("unsupported Context kind")
        _text(scope_key)
        _security(security_id)
        _, _, _, raw, _, _ = registry_state(registry)
        matches = [item for item in _load(raw)["descriptors"] if item["context_kind"] == kind and item["scope_key"] == scope_key
            and item["security_scope"] == ("none" if security_id is None else "security")]
        if len(matches) != 1:
            raise ValueError("Context descriptor absent or ambiguous")
        return matches[0]

    class Resolver:
        __slots__ = ("__weakref__",)

        def __init__(self, state_store, registry_signature_verifier):
            from .state_store import StateStore
            if type(self) is not Resolver or type(state_store) is not StateStore or not callable(getattr(registry_signature_verifier, "verify", None)):
                raise ValueError("Context resolver requires exact StateStore and registry verifier")
            if id(self) in resolver_seals:
                raise ValueError("Context resolver initialization is single-use")
            identity = id(self)
            resolver_seals[identity] = (weakref.ref(self, lambda _: resolver_seals.pop(identity, None)), state_store, registry_signature_verifier)

        def resolve(self, context_kind, scope_key, security_id, as_of_utc, registry_manifest_hash, *, upstream_generation: str):
            return self._resolve(context_kind, scope_key, security_id, as_of_utc, registry_manifest_hash,
                upstream_generation=upstream_generation)

        def _resolve_historical(self, fact):
            if type(fact) is not FormalContextFact:
                raise ValueError("historical Context requires an exact stored Fact")
            fact.to_dict()
            return self._resolve(fact.context_kind, fact.scope_key, fact.security_id, fact.as_of_utc,
                fact.registry_manifest_hash, upstream_generation=fact.evidence["upstream_generation"],
                historical_fact=fact)

        def _resolve(self, context_kind, scope_key, security_id, as_of_utc, registry_manifest_hash, *,
                upstream_generation, historical_fact=None):
            record = resolver_seals.get(id(self))
            if type(self) is not Resolver or record is None or record[0]() is not self:
                raise ValueError("Context resolver is forged")
            state, verifier = record[1:]
            _timestamp(as_of_utc)
            _text(upstream_generation)
            registry = Registry.load(state, verifier, registry_manifest_hash)
            descriptor = select_descriptor(registry, context_kind, scope_key, security_id)
            _, _, _, _, role_hashes, sources = registry_state(registry)
            exchange = None
            if descriptor["exchange_rule"] == "security_exchange":
                exchange = security_id[:2]
            elif descriptor["exchange_rule"] == "fixed_exchange":
                exchange = descriptor["fixed_exchange"]
                if security_id is not None and security_id[:2] != exchange:
                    raise ValueError("fixed Context exchange differs from security")
            elif security_id is not None:
                raise ValueError("Context exchange none rejects an implicit security exchange")
            official = OfficialRequest(source=descriptor["source"], dataset=descriptor["dataset"], security_id=security_id,
                period_or_date=_timestamp(as_of_utc).astimezone(SHANGHAI).date().isoformat() if descriptor["period_rule"] == "freeze_date_cn" else None,
                exchange=exchange)
            try:
                config = sources.select(official)
            except Exception as error:
                raise ValueError("Context signed source selection failed") from error
            for field in ("source", "dataset", "parser_id", "parser_version", "mapping_version", "bootstrap_calendar"):
                if getattr(config, field) != descriptor[field]:
                    raise ValueError(f"Context descriptor/source {field} mismatch")
            expected_scope = None if descriptor["bootstrap_calendar"] else exchange
            if config.exchange_scope != expected_scope:
                raise ValueError("Context source exchange scope mismatch")
            selected_wire = asdict(config.calendar_selector) if config.calendar_selector is not None else None
            if selected_wire != descriptor["calendar_selector"]:
                raise ValueError("Context descriptor/source calendar selector mismatch")
            binding = None
            if config.calendar_selector is not None:
                from .formal_context_repository import FormalContextRepository, _prove_historical_calendar
                from .formal_snapshot_repository import FormalSnapshotRepository
                if historical_fact is not None:
                    binding = _prove_historical_calendar(state, verifier, historical_fact,
                        config.calendar_selector, exchange, as_of_utc, registry_manifest_hash)
                else:
                    snapshots = FormalSnapshotRepository(state._configured_formal_snapshot_store_for_repository().root, state)
                    binding = FormalContextRepository(state, snapshots, verifier).resolve_verified_calendar_binding(
                        config.calendar_selector, exchange, as_of_utc, registry_manifest_hash)
            elif historical_fact is not None:
                raise ValueError("historical Context requires a signed calendar selector")
            relevant = [[role, digest] for role, digest in role_hashes if role in descriptor["referenced_roles"]]
            descriptor_id = hashlib.sha256(_canonical(descriptor)).hexdigest()
            binding_wire = asdict(binding) if binding is not None else None
            generation_wire = dict(schema_version="formal-context-refresh-generation-v1", descriptor_id=descriptor_id,
                request_version=descriptor["request_version"],
                generation_namespace=descriptor["generation_namespace"], upstream_generation=upstream_generation,
                official_request=asdict(official),
                registry_manifest_hash=registry_manifest_hash, relevant_registry_hashes=relevant,
                calendar_selector=selected_wire, calendar_binding=binding_wire)
            generation = hashlib.sha256(_canonical(generation_wire)).hexdigest()
            evidence = dict(descriptor_id=descriptor_id, normalizer_version=descriptor["normalizer_version"],
                upstream_generation=upstream_generation,
                relevant_registry_hashes=[[role, digest] for role, digest in relevant],
                request_fingerprint=official.request_fingerprint, calendar_binding=asdict(binding) if binding is not None else None)
            request = mint_request(dict(context_kind=context_kind, scope_key=scope_key, security_id=security_id, as_of_utc=as_of_utc,
                official_request=asdict(official), registry_manifest_hash=registry_manifest_hash,
                descriptor_id=descriptor_id, normalizer_version=descriptor["normalizer_version"],
                request_version=descriptor["request_version"],
                upstream_generation=upstream_generation, generation_namespace=descriptor["generation_namespace"],
                parser_id=descriptor["parser_id"], parser_version=descriptor["parser_version"], mapping_version=descriptor["mapping_version"],
                relevant_registry_hashes=relevant, refresh_generation=generation, calendar_binding=binding_wire,
                calendar_selector=selected_wire, evidence=evidence))
            identity = id(request)
            request_descriptors[identity] = (weakref.ref(request, lambda _: request_descriptors.pop(identity, None)), _canonical(descriptor))
            return request

    Registry.__name__ = "FormalContextRegistry"
    Registry.__qualname__ = "FormalContextRegistry"
    Resolver.__name__ = "SignedContextRequestResolver"
    Resolver.__qualname__ = "SignedContextRequestResolver"
    return Request, Registry, Resolver, Normalization, verify_context_fact


FormalContextRequest, FormalContextRegistry, SignedContextRequestResolver, FormalContextNormalization, _verify_context_fact = _trusted_context_types()
del _trusted_context_types


__all__ = ["CONTEXT_KINDS", "FormalContextRequest", "SignedContextRequestResolver", "FormalContextFact",
    "FormalContextIssue", "FormalContextVersionView", "FormalContextRegistry", "FormalContextNormalizer", "FormalContextNormalization"]
