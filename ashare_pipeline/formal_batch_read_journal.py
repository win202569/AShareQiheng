"""Build-local journal for owner-issued, current-only read evidence.

The journal does not participate in any production selector. Owners must first
finish their independent selection and then issue a ticket for its exact input
and result evidence. A checkpoint only rereads that evidence.
"""

from __future__ import annotations

import threading
import sys
import weakref


def _install_journal():
    scopes = {}
    tickets = {}

    def _methods(instance):
        target = instance if isinstance(instance, type) else type(instance)
        return tuple((cls, name, value) for cls in target.__mro__
                     if cls is not object for name, value in vars(cls).items()
                     if callable(value) or isinstance(value, (staticmethod, classmethod)))

    def _owner_state(owner):
        from .formal_context_repository import FormalContextRepository, _require_authentic_context_repository
        from .formal_feature_repository import FormalFeatureRepository, _require_authentic_metric_feature_repository
        from .formal_range_store import FormalRangeStore
        if type(owner) is FormalContextRepository:
            _require_authentic_context_repository(owner)
            return "context", owner._state_store, (owner._snapshots, owner._verifier)
        if type(owner) is FormalFeatureRepository:
            _require_authentic_metric_feature_repository(owner)
            return "feature", owner._store, (owner._bundle_store, owner._verifier, owner._current_input_provider)
        if type(owner) is FormalRangeStore:
            return "range", *owner._batch_journal_identity()
        raise ValueError("batch journal requires a fixed genuine owner type")

    def _scope(scope, *, active=True):
        record = scopes.get(id(scope))
        if type(scope) is not FormalBatchReadJournal or record is None or record[0]() is not scope:
            raise ValueError("batch scope is forged or copied")
        if active and record[1] != "active":
            raise ValueError("batch scope is closed")
        if threading.get_ident() != record[2]:
            raise ValueError("batch scope belongs to a different thread")
        owner, kind, state, refs, signatures = record[3:8]
        current_kind, current_state, current_refs = _owner_state(owner)
        if (current_kind != kind or current_state is not state or len(current_refs) != len(refs)
                or any(a is not b for a, b in zip(current_refs, refs, strict=True))):
            raise ValueError("batch owner dependencies changed")
        if str(state.db_path.resolve()) != record[8]:
            raise ValueError("batch StateStore path changed")
        for cls, name, method in signatures:
            if vars(cls).get(name) is not method:
                raise ValueError("batch reader method changed")
        for instance in (owner, state, *refs):
            if instance is None:
                continue
            for cls, name, _ in signatures:
                if type(instance) is cls and name in getattr(instance, "__dict__", {}):
                    raise ValueError("batch reader instance method changed")
        return record

    class CurrentReadTicket:
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("current read tickets are issued only by owners")

        def __copy__(self):
            raise TypeError("current read ticket cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("current read ticket cannot be copied")

    class FormalBatchReadJournal:
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("batch scopes require the checked factory")

        def __copy__(self):
            raise TypeError("batch scope cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("batch scope cannot be copied")

        @classmethod
        def open(cls, owner, *, registry_manifest_hash, as_of_utc, population, required_keys):
            if cls is not FormalBatchReadJournal:
                raise ValueError("batch scope type must be exact")
            if (type(registry_manifest_hash) is not str or len(registry_manifest_hash) != 64
                    or any(c not in "0123456789abcdef" for c in registry_manifest_hash)):
                raise ValueError("batch scope requires canonical signed root hash")
            if type(as_of_utc) is not str or not as_of_utc:
                raise ValueError("batch scope requires a frozen cutoff")
            if (type(population) is not tuple or not population
                    or any(type(x) is not str for x in population)
                    or tuple(sorted(set(population))) != population):
                raise ValueError("batch scope requires sorted unique population")
            if (type(required_keys) is not tuple or not required_keys
                    or any(type(x) is not tuple or not x for x in required_keys)
                    or len(set(required_keys)) != len(required_keys)):
                raise ValueError("batch scope requires exact mandatory coverage")
            kind, state, refs = _owner_state(owner)
            signatures = tuple(item for instance in (owner, state, *refs) if instance is not None
                               for item in _methods(instance))
            result = object.__new__(FormalBatchReadJournal)
            scope_id = id(result)
            scopes[scope_id] = [weakref.ref(result, lambda _, key=scope_id: scopes.pop(key, None)),
                "active", threading.get_ident(), owner, kind, state, refs, signatures,
                str(state.db_path.resolve()), registry_manifest_hash, as_of_utc, population,
                frozenset(required_keys), {}, 0, {}]
            return result

        def checkpoint(self):
            record = _scope(self)
            phase = record[14]
            try:
                for ticket in tuple(record[13].values()):
                    ticket_record = _ticket(ticket, self)
                    if record[15].get(id(ticket)) == phase:
                        continue
                    owner = record[3]
                    owner._batch_recheck_ticket(ticket_record[4])
                    record[15][id(ticket)] = phase
            except Exception:
                record[1] = "consumed"
                raise

        def next_phase(self):
            record = _scope(self)
            record[14] += 1

        def finalize(self):
            record = _scope(self)
            record[1] = "finalizing"
            try:
                coverage = set()
                for ticket in record[13].values():
                    coverage.update(_ticket(ticket, self)[5])
                if not record[12] <= coverage:
                    raise ValueError("batch mandatory coverage is incomplete")
                record[1] = "active"
                record[14] += 1
                self.checkpoint()
            finally:
                record[1] = "consumed"

    def _ticket(ticket, scope):
        record = tickets.get(id(ticket))
        if (type(ticket) is not CurrentReadTicket or record is None
                or record[0]() is not ticket or record[1]() is not scope):
            raise ValueError("current read ticket is forged, copied, or cross-scope")
        return record

    def issue(scope, owner, kind, key, baseline, evidence, coverage):
        record = _scope(scope)
        if owner is not record[3] or kind != record[4]:
            raise ValueError("current ticket owner mismatch")
        issuer_name = {"context": "select_current_batch_ticket",
                       "feature": "select_current_metric_batch_ticket",
                       "range": "select_current_batch_ticket"}[kind]
        if sys._getframe(1).f_code is not vars(type(owner))[issuer_name].__code__:
            raise ValueError("current ticket must be issued by the fixed owner selector")
        if type(key) is not tuple or type(baseline) is not bytes or type(coverage) is not tuple:
            raise ValueError("current ticket evidence shape invalid")
        if any(item not in record[12] for item in coverage):
            raise ValueError("current ticket coverage is outside build scope")
        identity = (id(owner), kind, key)
        previous = record[13].get(identity)
        if previous is not None:
            prior = _ticket(previous, scope)
            if prior[3] != baseline:
                raise ValueError("same current key has a different baseline")
            return previous
        ticket = object.__new__(CurrentReadTicket)
        ticket_id = id(ticket)
        tickets[ticket_id] = (weakref.ref(ticket, lambda _, key=ticket_id: tickets.pop(key, None)),
            weakref.ref(scope), identity, baseline, evidence, coverage)
        record[13][identity] = ticket
        return ticket

    def require_scope(scope, owner, *, root, as_of_utc, population):
        record = _scope(scope)
        if (owner is not record[3] or root != record[9] or as_of_utc != record[10]
                or population != record[11]):
            raise ValueError("current read does not match owner build scope")

    return FormalBatchReadJournal, CurrentReadTicket, issue, require_scope


(FormalBatchReadJournal, CurrentReadTicket,
 _issue_current_ticket, _require_current_scope) = _install_journal()
del _install_journal
