"""Fail-closed verified Context persistence and point-in-time selection."""

from dataclasses import asdict
from datetime import datetime, date, time

from .formal_context_schema import (FormalContextFact, FormalContextNormalization, FormalContextRegistry,
    FormalContextVersionView, SignedContextRequestResolver, _canonical, _load, _verify_context_fact,
    _timestamp, _selector, _security, _text, _exchange)
from .formal_evidence import VerifiedCalendarBinding
from .formal_snapshot_repository import FormalSnapshotRepository
from .formal_sources import CalendarSelector
from .formal_time import formal_version_sort_key, SHANGHAI
from .state_store import StateStore


def _require_context_producer(store, connection, ref):
    row = connection.execute("SELECT * FROM formal_source_snapshot WHERE id=?", (ref.snapshot_id,)).fetchone()
    if row is None:
        raise ValueError("Context source snapshot is missing")
    verified = store._formal_verified_snapshot_ref_from_connection(connection, row)
    if _canonical(asdict(verified)) != _canonical(asdict(ref)):
        raise ValueError("Context source reference mismatch")
    task = connection.execute("SELECT * FROM formal_collection_task WHERE id=?", (ref.producing_task_id,)).fetchone()
    if task is None or task["kind"] != "formal_context" or task["status"] != "verified" or task["refresh_generation"] != ref.refresh_generation:
        raise ValueError("Context evidence requires a verified formal_context producer and exact generation")
    prerequisites = [row[0] for row in connection.execute(
        "SELECT prerequisite_task_id FROM formal_collection_task_dependency WHERE task_id=? ORDER BY prerequisite_task_id",
        (ref.producing_task_id,))]
    public = store._formal_task_public(task, prerequisites)
    store._require_formal_verified_task_state(task, public)
    return verified


def _validate_stored_fact(store, connection, fact, verifier):
    if type(fact) is not FormalContextFact:
        raise ValueError("exact Context fact required")
    fact.to_dict()
    request = SignedContextRequestResolver(store, verifier).resolve(fact.context_kind, fact.scope_key,
        fact.security_id, fact.as_of_utc, fact.registry_manifest_hash,
        upstream_generation=fact.evidence["upstream_generation"])
    row = connection.execute("SELECT * FROM formal_source_snapshot WHERE id=?", (fact.source_snapshot_id,)).fetchone()
    if row is None:
        raise ValueError("Context linked source snapshot is absent")
    ref = store._formal_verified_snapshot_ref_from_connection(connection, row)
    _require_context_producer(store, connection, ref)
    _verify_context_fact(fact, request, ref)
    return ref, request


def _row_fact(row):
    wire = dict(row)
    _timestamp(wire.pop("created_at_utc"))
    for field in ("value", "evidence"):
        raw = wire.pop(field + "_json")
        if type(raw) is not str:
            raise ValueError("Context stored JSON must be text")
        wire[field] = _load(raw.encode())
    if type(wire["no_coverage"]) is not int or wire["no_coverage"] not in (0, 1):
        raise ValueError("Context stored no_coverage must be 0 or 1")
    wire["no_coverage"] = bool(wire["no_coverage"])
    return FormalContextFact.from_dict(wire)


def _logical_key(fact):
    return (fact.context_kind, fact.scope_key, fact.security_id, fact.as_of_utc,
        fact.value["exchange"] if fact.context_kind == "trading_calendar" else None,
        fact.registry_manifest_hash, fact.refresh_generation)


def _put_context_facts(store, connection, normalization):
    if type(normalization) is not FormalContextNormalization:
        raise ValueError("Context persistence requires sealed normalization receipt")
    wire = normalization.to_dict()
    verifier = store._require_registry_verifier()
    FormalContextRegistry.load(store, verifier, wire["registry_manifest_hash"])
    facts = normalization.facts
    existing = {}
    for row in connection.execute("SELECT * FROM formal_context_fact ORDER BY id"):
        fact = _row_fact(row)
        _validate_stored_fact(store, connection, fact, verifier)
        key = _logical_key(fact)
        if key in existing and existing[key].id != fact.id:
            raise ValueError("conflicting stored Context generation")
        existing[key] = fact
    for fact in facts:
        if fact.registry_manifest_hash != wire["registry_manifest_hash"]:
            raise ValueError("Context normalization root mismatch")
        _, request = _validate_stored_fact(store, connection, fact, verifier)
        if _canonical(wire["request"]) != request.canonical_bytes():
            raise ValueError("Context normalization request is stale")
        prior = existing.get(_logical_key(fact))
        if prior is not None:
            if prior.canonical_bytes() != fact.canonical_bytes():
                raise ValueError("conflicting Context logical key and refresh generation")
            continue
        payload = fact.to_dict()
        payload["value_json"] = _canonical(payload.pop("value")).decode()
        payload["evidence_json"] = _canonical(payload.pop("evidence")).decode()
        payload["no_coverage"] = int(payload["no_coverage"])
        from .state_store import _utc_now
        payload["created_at_utc"] = _utc_now()
        store._formal_insert_row(connection, "formal_context_fact", payload)
        existing[_logical_key(fact)] = fact


def _list_context_facts(store, connection, *, registry_manifest_hash, context_kind=None, scope_key=None, security_id=None, as_of_utc=None, source_snapshot_id=None):
    verifier = store._require_registry_verifier()
    FormalContextRegistry.load(store, verifier, registry_manifest_hash)
    result = []
    keys = set()
    # Parse canonical IDs before filtering; replay only matching source chains.
    # Calendar resolution must not recursively validate unrelated date-only facts.
    for row in connection.execute("SELECT * FROM formal_context_fact ORDER BY id"):
        fact = _row_fact(row)
        key = _logical_key(fact)
        if key in keys:
            raise ValueError("duplicate Context logical generation")
        keys.add(key)
        if fact.registry_manifest_hash != registry_manifest_hash:
            continue
        if context_kind is not None and fact.context_kind != context_kind:
            continue
        if scope_key is not None and fact.scope_key != scope_key:
            continue
        if security_id is not None and fact.security_id != security_id:
            continue
        if as_of_utc is not None and fact.as_of_utc != as_of_utc:
            continue
        if source_snapshot_id is not None and fact.source_snapshot_id != source_snapshot_id:
            continue
        _validate_stored_fact(store, connection, fact, verifier)
        result.append(FormalContextFact.from_dict(fact.to_dict()))
    return tuple(result)


class FormalContextRepository:
    def __init__(self, state_store, snapshot_repository, registry_signature_verifier):
        if type(state_store) is not StateStore or type(snapshot_repository) is not FormalSnapshotRepository:
            raise ValueError("Context repository requires exact StateStore and FormalSnapshotRepository")
        if snapshot_repository._state_store is not state_store or not callable(getattr(registry_signature_verifier, "verify", None)):
            raise ValueError("Context repository source store/verifier mismatch")
        self._state_store = state_store
        self._snapshots = snapshot_repository
        self._verifier = registry_signature_verifier

    def _load(self, root):
        return FormalContextRegistry.load(self._state_store, self._verifier, root)

    def _candidates(self, kind, scope_key, security_id, as_of_utc, root, exchange=None):
        facts = self._state_store.list_formal_context_facts(registry_manifest_hash=root,
            context_kind=kind, scope_key=scope_key, as_of_utc=as_of_utc)
        return tuple(fact for fact in facts if fact.security_id == security_id
            and (exchange is None or fact.value["exchange"] == exchange))

    def _select(self, kind, scope_key, security_id, as_of_utc, root, exchange=None):
        self._load(root)
        _timestamp(as_of_utc)
        _text(scope_key)
        _security(security_id)
        before = self._candidates(kind, scope_key, security_id, as_of_utc, root, exchange)
        if not before:
            raise ValueError("verified Context is missing or pending")
        for fact in before:
            request = SignedContextRequestResolver(self._state_store, self._verifier).resolve(kind, scope_key,
                security_id, as_of_utc, root, upstream_generation=fact.evidence["upstream_generation"])
            ref = self._state_store.get_formal_snapshot(fact.source_snapshot_id)
            if ref is None:
                raise ValueError("Context source snapshot is missing")
            current = self._snapshots.get_verified_by_manifest(ref.manifest_sha256)
            self._snapshots.read_verified_raw(current)
            _verify_context_fact(fact, request, current)
            for field in ("published_at_utc", "effective_at_utc", "source_updated_at_utc"):
                if getattr(fact, field) is not None and _timestamp(getattr(fact, field)) > _timestamp(as_of_utc):
                    raise ValueError("Context future source time")
        ordered = sorted(before, key=lambda fact: formal_version_sort_key(FormalContextVersionView.from_fact(fact)))
        key = formal_version_sort_key(FormalContextVersionView.from_fact(ordered[0]))
        if sum(formal_version_sort_key(FormalContextVersionView.from_fact(fact)) == key for fact in before) != 1:
            raise ValueError("multiple equal leading Context versions")
        self._load(root)
        after = self._candidates(kind, scope_key, security_id, as_of_utc, root, exchange)
        if tuple(fact.canonical_bytes() for fact in before) != tuple(fact.canonical_bytes() for fact in after):
            raise ValueError("Context correction race during verification")
        return FormalContextFact.from_dict(ordered[0].to_dict())

    def get_verified(self, kind, scope_key, security_id, as_of_utc, registry_manifest_hash):
        if kind == "trading_calendar":
            self._load(registry_manifest_hash)
            raise ValueError("trading calendars require an exchange selector")
        return self._select(kind, scope_key, security_id, as_of_utc, registry_manifest_hash)

    def resolve_verified_calendar_binding(self, selector, exchange, as_of_utc, registry_manifest_hash):
        self._load(registry_manifest_hash)
        if type(selector) is not CalendarSelector:
            raise ValueError("exact signed calendar selector required")
        selector_wire = asdict(selector)
        copied = _selector(selector_wire)
        if copied.exchange != _exchange(exchange):
            raise ValueError("calendar selector exchange mismatch")
        fact = self._select("trading_calendar", copied.scope_key, None, as_of_utc, registry_manifest_hash, exchange)
        ref = self._state_store.get_formal_snapshot(fact.source_snapshot_id)
        if ref is None:
            raise ValueError("calendar source missing")
        ref = self._snapshots.get_verified_by_manifest(ref.manifest_sha256)
        self._snapshots.read_verified_raw(ref)
        if asdict(selector) != selector_wire:
            raise ValueError("calendar selector mutated during verification")
        after = self._select("trading_calendar", copied.scope_key, None, as_of_utc, registry_manifest_hash, exchange)
        if after.id != fact.id:
            raise ValueError("calendar correction race during source verification")
        return VerifiedCalendarBinding(snapshot_id=ref.snapshot_id, manifest_sha256=ref.manifest_sha256,
            exchange=exchange, freeze_at_utc=as_of_utc, registry_manifest_hash=registry_manifest_hash,
            selector_hash=copied.selector_hash, prerequisite_task_id=ref.producing_task_id)


def build_effective_time_resolver(repository):
    if type(repository) is not FormalContextRepository:
        raise ValueError("effective-time resolver requires exact Context repository")

    class Resolver:
        def next_exchange_close(self, exchange, disclosure_date_cn, calendar_binding):
            if type(calendar_binding) is not VerifiedCalendarBinding:
                raise ValueError("exact verified calendar binding required")
            wire = asdict(calendar_binding)
            root = wire["registry_manifest_hash"]
            repository._load(root)
            facts = repository._state_store.list_formal_context_facts(registry_manifest_hash=root,
                context_kind="trading_calendar", as_of_utc=wire["freeze_at_utc"], source_snapshot_id=wire["snapshot_id"])
            matches = [fact for fact in facts if fact.source_snapshot_id == wire["snapshot_id"] and fact.value["exchange"] == exchange]
            if len(matches) != 1:
                raise ValueError("calendar binding source is absent or ambiguous")
            fact = matches[0]
            selector = CalendarSelector("trading_calendar", fact.scope_key, exchange, "visible_at_freeze")
            current = repository.resolve_verified_calendar_binding(selector, exchange, wire["freeze_at_utc"], root)
            if _canonical(asdict(current)) != _canonical(wire) or asdict(calendar_binding) != wire:
                raise ValueError("calendar binding changed or was substituted")
            if type(disclosure_date_cn) is not str or date.fromisoformat(disclosure_date_cn).isoformat() != disclosure_date_cn:
                raise ValueError("disclosure must be an exact ISO date")
            selected = repository._select("trading_calendar", fact.scope_key, None, wire["freeze_at_utc"], root, exchange)
            if selected.source_snapshot_id != wire["snapshot_id"]:
                raise ValueError("calendar binding changed during final selection")
            next_days = [day for day in selected.value["trading_days"] if day > disclosure_date_cn]
            if not next_days:
                raise ValueError("verified calendar has no next session")
            return datetime.combine(date.fromisoformat(next_days[0]), time(15), SHANGHAI).isoformat()

    return Resolver()


__all__ = ["FormalContextRepository", "build_effective_time_resolver"]
