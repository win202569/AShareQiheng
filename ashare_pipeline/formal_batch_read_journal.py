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
        from .formal_range_store import FormalRangeStore, _require_range_batch_journal_owner
        if type(owner) is FormalContextRepository:
            _require_authentic_context_repository(owner)
            return "context", owner._state_store, (owner._snapshots, owner._verifier)
        if type(owner) is FormalFeatureRepository:
            _require_authentic_metric_feature_repository(owner)
            return "feature", owner._store, (owner._bundle_store, owner._verifier, owner._current_input_provider)
        if type(owner) is FormalRangeStore:
            return "range", *_require_range_batch_journal_owner(owner)
        from .formal_policy_state import FormalPolicyStateRepository
        from .formal_policy_financial import FormalPolicyFinancialRepository
        from .formal_policy_market import FormalPolicyMarketRepository
        from .formal_policy_repository import FormalPolicyRepository
        if type(owner) is FormalPolicyRepository:
            state, children = owner._batch_journal_identity()
            return "policy", state, children
        for owner_type, kind in ((FormalPolicyStateRepository, "state"),
                                 (FormalPolicyFinancialRepository, "financial"),
                                 (FormalPolicyMarketRepository, "market")):
            if type(owner) is owner_type:
                state, child = owner._batch_journal_identity()
                return kind, state, (child,)
        raise ValueError("batch journal requires a fixed genuine owner type")

    def _chain(owner):
        kind, state, refs = _owner_state(owner)
        if kind == "policy":
            allowed = {kind: owner}
            expanded = []
            for child in refs:
                child_kind, child_state, child_refs, child_allowed = _chain(child)
                if child_state is not state:
                    raise ValueError("policy batch scope children have different StateStores")
                allowed.update(child_allowed)
                expanded.extend((child, *child_refs))
            unique = tuple(dict.fromkeys((*refs, *expanded)))
            return kind, state, unique, allowed
        children = tuple(item for item in refs if item is not None
                         and type(item).__name__ in {
                             "FormalContextRepository", "FormalFeatureRepository", "FormalRangeStore"})
        expanded = tuple(reference for child in children
                         for reference in _owner_state(child)[2])
        allowed = {kind: owner, **{_owner_state(child)[0]: child for child in children}}
        if kind == "financial" and "feature" in allowed:
            allowed["policy_feature"] = allowed["feature"]
        if kind == "market":
            allowed["calendar"] = owner
        return kind, state, refs + expanded, allowed

    def _scope(scope, *, active=True):
        if (globals().get("_issue_current_ticket") is not issue
                or globals().get("_require_current_scope") is not require_scope
                or globals().get("_require_current_ticket") is not require_ticket):
            raise ValueError("batch journal issuing authority changed")
        record = scopes.get(id(scope))
        if type(scope) is not FormalBatchReadJournal or record is None or record[0]() is not scope:
            raise ValueError("batch scope is forged or copied")
        if active and record[1] != "active":
            raise ValueError("batch scope is closed")
        if threading.get_ident() != record[2]:
            raise ValueError("batch scope belongs to a different thread")
        owner, kind, state, refs, signatures = record[3:8]
        current_kind, current_state, current_refs, current_allowed = _chain(owner)
        if (current_kind != kind or current_state is not state or len(current_refs) != len(refs)
                or any(a is not b for a, b in zip(current_refs, refs, strict=True))
                or current_allowed != record[16]):
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

        def selected(self):
            record = tickets.get(id(self))
            if type(self) is not CurrentReadTicket or record is None or record[0]() is not self:
                raise ValueError("current read ticket is forged or copied")
            _scope(record[1]())
            return record[6]

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
            if (globals().get("_issue_current_ticket") is not issue
                    or globals().get("_require_current_scope") is not require_scope
                    or globals().get("_require_current_ticket") is not require_ticket):
                raise ValueError("batch journal issuing authority changed")
            if (type(registry_manifest_hash) is not str or len(registry_manifest_hash) != 64
                    or any(c not in "0123456789abcdef" for c in registry_manifest_hash)):
                raise ValueError("batch scope requires canonical signed root hash")
            if type(as_of_utc) is not str or not as_of_utc:
                raise ValueError("batch scope requires a frozen cutoff")
            if (type(population) is not tuple or not population
                    or any(type(x) is not str for x in population)
                    or tuple(sorted(set(population))) != population):
                raise ValueError("batch scope requires sorted unique population")
            if (type(required_keys) is not tuple
                    or any(type(x) is not tuple or not x for x in required_keys)
                    or len(set(required_keys)) != len(required_keys)):
                raise ValueError("batch scope requires exact mandatory coverage")
            kind, state, refs, allowed = _chain(owner)
            if not required_keys and kind != "policy":
                raise ValueError("batch scope requires mandatory coverage")
            signatures = tuple(item for instance in (owner, state, *refs) if instance is not None
                               for item in _methods(instance))
            result = object.__new__(FormalBatchReadJournal)
            scope_id = id(result)
            scopes[scope_id] = [weakref.ref(result, lambda _, key=scope_id: scopes.pop(key, None)),
                "active", threading.get_ident(), owner, kind, state, refs, signatures,
                str(state.db_path.resolve()), registry_manifest_hash, as_of_utc, population,
                frozenset(required_keys), {}, 0, {}, allowed]
            return result

        def checkpoint(self):
            record = _scope(self)
            phase = record[14]
            try:
                for ticket in tuple(record[13].values()):
                    ticket_record = _ticket(ticket, self)
                    if record[15].get(id(ticket)) == phase:
                        continue
                    owner = record[16][ticket_record[2][1]]
                    checker = (owner._batch_recheck_policy_ticket if ticket_record[2][1] == "policy_feature"
                               else owner._batch_recheck_ticket)
                    checker(ticket_record[4])
                    record[15][id(ticket)] = phase
            except Exception:
                record[1] = "consumed"
                raise

        def next_phase(self):
            record = _scope(self)
            record[14] += 1

        def close(self):
            # Revocation must still work when the owner graph is no longer
            # valid; ordinary scope reads intentionally reject that graph.
            record = scopes.get(id(self))
            if (type(self) is not FormalBatchReadJournal or record is None
                    or record[0]() is not self or record[1] != "active"
                    or threading.get_ident() != record[2]):
                raise ValueError("batch scope is closed, forged, or cross-thread")
            record[1] = "consumed"

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

    def issue(scope, owner, kind, key, baseline, evidence, coverage, selection):
        record = _scope(scope)
        if record[16].get(kind) is not owner:
            raise ValueError("current ticket owner mismatch")
        issuer_name = {"context": "select_current_batch_ticket",
                       "feature": "select_current_metric_batch_ticket",
                       "policy_feature": "select_current_policy_batch_ticket",
                       "range": "select_current_batch_ticket",
                       "state": "select_current_batch_ticket",
                       "financial": "select_current_batch_ticket",
                       "policy": "_build_batch_in_owner_scope",
                       "calendar": "select_calendar_batch_ticket",
                       "market": "select_current_batch_ticket"}[kind]
        caller = sys._getframe(1)
        if caller.f_code is not vars(type(owner))[issuer_name].__code__:
            if (kind not in {"calendar", "market"}
                    or caller.f_code.co_name != "ticket_evidence"
                    or sys._getframe(2).f_code is not vars(type(owner))[issuer_name].__code__):
                raise ValueError("current ticket must be issued by the fixed owner selector")
        if type(key) is not tuple or type(baseline) is not bytes or type(coverage) is not tuple:
            raise ValueError("current ticket evidence shape invalid")
        member_index = 2 if kind == "context" else 0
        expected_length = 3 if kind in {"context", "feature", "policy_feature"} else 1
        if any(type(item) is not tuple or len(item) != expected_length
               or type(item[member_index]) is not str
               or (item[member_index] not in record[11]
                   and not (record[4] in {"market", "policy"}
                            and (kind == "range" or
                                 (kind == "calendar" and item[member_index] in {"SH", "SZ", "BJ"}))))
               for item in coverage):
            raise ValueError("current ticket coverage is outside frozen population")
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
            weakref.ref(scope), identity, baseline, evidence, coverage, selection)
        record[13][identity] = ticket
        return ticket

    def require_scope(scope, owner, *, root, as_of_utc, population):
        record = _scope(scope)
        if (type(population) is not tuple or not population
                or any(type(item) is not str for item in population)
                or tuple(sorted(set(population))) != population):
            raise ValueError("current read population must be a sorted nonempty subset")
        if (record[16].get(_owner_state(owner)[0]) is not owner
                or root != record[9] or as_of_utc != record[10]
                or (not set(population) <= set(record[11])
                    and not (record[4] in {"market", "policy"} and (type(owner).__name__ == "FormalRangeStore"
                                                           or set(population) <= {"SH", "SZ", "BJ"})))):
            raise ValueError("current read does not match owner build scope")

    def require_ticket(scope, ticket, owner, kind):
        record = _scope(scope)
        saved = _ticket(ticket, scope)
        if record[16].get(kind) is not owner or saved[2][0:2] != (id(owner), kind):
            raise ValueError("current read ticket belongs to another owner")
        return saved[6], saved[3], saved[4]

    return FormalBatchReadJournal, CurrentReadTicket, issue, require_scope, require_ticket


(FormalBatchReadJournal, CurrentReadTicket,
 _issue_current_ticket, _require_current_scope, _require_current_ticket) = _install_journal()
del _install_journal
