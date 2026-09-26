"""Authenticated calendar coverage and independent market-window outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from types import MappingProxyType
import weakref

from .formal_policy_values import canonical_bytes
from .formal_range_contract import (
    _range_binding_planning_authority, _range_binding_read_lease_authority,
)
from .formal_range_format import RangeConfig, _range_config_to_dict
from .formal_time import FORMAL_FREEZE_AT_CN


_FREEZE_UTC = datetime.fromisoformat(FORMAL_FREEZE_AT_CN).astimezone(timezone.utc).isoformat()
_FREEZE_DATE = datetime.fromisoformat(_FREEZE_UTC).date()
_SECURITY = re.compile(r"^(?:SH|SZ|BJ)[0-9]{6}$")
_binding_type, _read_binding = _range_binding_planning_authority()
_open_binding_read_lease, _close_binding_read_lease = _range_binding_read_lease_authority()


def _detached(value):
    return json.loads(canonical_bytes(value))


def _iso_date(value, label):
    if type(value) is not str:
        raise ValueError(f"{label} must be a canonical ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a canonical ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be a canonical ISO date")
    return parsed


def _aware(value, label):
    if type(value) is not str:
        raise ValueError(f"{label} must be an aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an aware ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be an aware ISO timestamp")
    return parsed


def _decimal_text(value, label, *, positive=False):
    if type(value) is not str:
        raise ValueError(f"{label} must be canonical decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{label} must be canonical decimal text") from error
    if not parsed.is_finite() or parsed < 0 or (positive and parsed <= 0):
        raise ValueError(f"{label} is outside its allowed finite range")
    if parsed.is_zero():
        canonical = "0"
    else:
        canonical = format(parsed, "f")
        if "." in canonical:
            canonical = canonical.rstrip("0").rstrip(".")
    if canonical != value:
        raise ValueError(f"{label} must be canonical decimal text")
    return parsed


def _binding_identity(binding):
    view = _read_binding(binding)
    return {
        "registry_manifest_hash": view["registry_manifest_hash"],
        "source_registry_hash": view["source_registry_hash"],
        "binding_hash": view["binding_hash"],
        "rule_id": view["rule_id"],
        "exchange": view["exchange"],
        "market_config": _range_config_to_dict(view["market_config"]),
        "calendar_config": _range_config_to_dict(view["calendar_config"]),
    }


def _build_proof_types():
    @dataclass(frozen=True)
    class _ProofRecord:
        reference: weakref.ReferenceType
        wire: dict
        wire_bytes: bytes
        binding_identity: dict
        range_store: object
        recheck: object

    calendar_records = {}
    window_records = {}

    class _ProofMeta(type):
        def __new__(metaclass, name, bases, namespace):
            if any(isinstance(base, _ProofMeta) for base in bases):
                raise TypeError("market proof types cannot be subclassed")
            return super().__new__(metaclass, name, bases, namespace)

        def __setattr__(self, name, value):
            raise TypeError("market proof types are immutable")

        def __delattr__(self, name):
            raise TypeError("market proof types are immutable")

    def record(value, expected, records):
        sealed = records.get(id(value))
        if type(value) is not expected or sealed is None or sealed.reference() is not value:
            raise ValueError("market proof is forged, copied, or foreign")
        if canonical_bytes(sealed.wire) != sealed.wire_bytes:
            raise ValueError("market proof payload changed")
        return sealed

    class VerifiedCalendarCoverageV1(metaclass=_ProofMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise ValueError("calendar coverage requires authenticated source receipts")

        def __setattr__(self, name, value):
            raise AttributeError("calendar coverage is immutable")

        def __getattr__(self, name):
            sealed = record(self, VerifiedCalendarCoverageV1, calendar_records)
            if name in sealed.wire:
                value = sealed.wire[name]
                return tuple(value) if name in {"trading_days", "lineage"} else value
            raise AttributeError(name)

        def to_dict(self):
            return _detached(record(self, VerifiedCalendarCoverageV1, calendar_records).wire)

        def canonical_bytes(self):
            return bytes(record(self, VerifiedCalendarCoverageV1, calendar_records).wire_bytes)

        def require_current(self):
            sealed = record(self, VerifiedCalendarCoverageV1, calendar_records)
            sealed.recheck()

        def __copy__(self):
            raise TypeError("calendar coverage cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("calendar coverage cannot be copied")

    class VerifiedMarketWindowV1(metaclass=_ProofMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise ValueError("market windows require authenticated source receipts")

        def __setattr__(self, name, value):
            raise AttributeError("market window is immutable")

        def __getattr__(self, name):
            sealed = record(self, VerifiedMarketWindowV1, window_records)
            if name in sealed.wire:
                value = sealed.wire[name]
                return tuple(value) if name in {"required_trading_days", "lineage", "pending"} else value
            raise AttributeError(name)

        def to_dict(self):
            return _detached(record(self, VerifiedMarketWindowV1, window_records).wire)

        def canonical_bytes(self):
            return bytes(record(self, VerifiedMarketWindowV1, window_records).wire_bytes)

        def require_current(self):
            sealed = record(self, VerifiedMarketWindowV1, window_records)
            sealed.recheck()

        def __copy__(self):
            raise TypeError("market windows cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("market windows cannot be copied")

    def mint(proof_type, records, wire, binding, range_store, recheck, hash_field):
        identity = _binding_identity(binding)
        content = _detached(wire)
        digest = hashlib.sha256(canonical_bytes(content)).hexdigest()
        content[hash_field] = digest
        result = object.__new__(proof_type)
        identity_key = id(result)
        reference = weakref.ref(result, lambda ref, key=identity_key: records.pop(key, None))
        records[identity_key] = _ProofRecord(reference, content, canonical_bytes(content),
                                             identity, range_store, recheck)
        return result

    def mint_calendar(wire, binding, range_store, recheck):
        return mint(VerifiedCalendarCoverageV1, calendar_records, wire, binding, range_store,
                    recheck, "coverage_hash")

    def mint_window(wire, binding, range_store, recheck):
        return mint(VerifiedMarketWindowV1, window_records, wire, binding, range_store,
                    recheck, "window_hash")

    def require_calendar(proof, *, binding, range_store):
        sealed = record(proof, VerifiedCalendarCoverageV1, calendar_records)
        VerifiedCalendarCoverageV1.require_current(proof)
        if _binding_identity(binding) != sealed.binding_identity:
            raise ValueError("calendar coverage belongs to another binding")
        if range_store is not sealed.range_store:
            raise ValueError("calendar coverage belongs to another range store")
        return _detached(sealed.wire)

    proof_type = VerifiedCalendarCoverageV1
    require_current = VerifiedCalendarCoverageV1.require_current
    to_dict = VerifiedCalendarCoverageV1.to_dict

    def calendar_proof_authority():
        return proof_type, require_current, to_dict, require_calendar

    installed = False

    def install_market_owner(dependencies):
        nonlocal installed
        if installed:
            raise RuntimeError("market proof owner is already installed")
        installed = True
        if type(dependencies) is not tuple or len(dependencies) != 13:
            raise RuntimeError("market repository dependencies are invalid")
        (store_type, resolve_binding, select_current, first_calendar_request,
         next_page, previous_calendar_request, market_requests, observation_to_dict,
         observation_require_current, implementation_page_group, implementation_select_calendar,
         implementation_select_market, selection_types) = dependencies
        calendar_selection_type, market_selection_type = selection_types
        batch_capture = ContextVar("policy_market_batch_capture", default=None)
        selection_records = {}
        anchored_binding_identity = _binding_identity
        anchored_read_binding = _read_binding
        anchored_open_binding_read_lease = _open_binding_read_lease
        anchored_close_binding_read_lease = _close_binding_read_lease
        anchored_canonical = canonical_bytes
        selection_fields = {
            calendar_selection_type: ("coverage", "pending", "lineage", "selection_hash", "_check"),
            market_selection_type: ("window", "pending", "lineage", "selection_hash", "_check"),
        }
        selection_interfaces = {
            cls: (cls.__new__, cls.__init__, cls.__getattribute__, cls.__setattr__,
                  cls.__dataclass_fields__, tuple((name, cls.__dataclass_fields__[name],
                      cls.__dataclass_fields__[name].name,
                      cls.__dataclass_fields__[name].type,
                      cls.__dataclass_fields__[name].init,
                      vars(cls).get(name)) for name in names), cls.__slots__)
            for cls, names in selection_fields.items()
        }

        def selection_interface():
            if (globals().get("CalendarSelection") is not calendar_selection_type
                    or globals().get("MarketSelection") is not market_selection_type):
                raise ValueError("market selection type identity changed")
            for cls, names in selection_fields.items():
                (new, init, lookup, setter, fields, entries, slots) = selection_interfaces[cls]
                if (cls.__new__ is not new or cls.__init__ is not init
                        or cls.__getattribute__ is not lookup or cls.__setattr__ is not setter
                        or cls.__dataclass_fields__ is not fields
                        or tuple(cls.__dataclass_fields__) != names
                        or cls.__slots__ != slots
                        or any(cls.__dataclass_fields__.get(name) is not field
                            or field.name != field_name or field.type != field_type
                            or field.init != field_init or vars(cls).get(name) is not descriptor
                            for name, field, field_name, field_type, field_init, descriptor in entries)):
                    raise ValueError("market selection constructor or field interface changed")

        def construct_selection(cls, values):
            selection_interface()
            new, init = selection_interfaces[cls][:2]
            result = new(cls)
            init(result, *values)
            selection_interface()
            names = selection_fields[cls]
            if (type(result) is not cls
                    or any((object.__getattribute__(result, name) is not expected
                            if name in {"coverage", "window", "_check"}
                            else type(object.__getattribute__(result, name)) is not type(expected)
                            or object.__getattribute__(result, name) != expected)
                           for name, expected in zip(names, values, strict=True))):
                raise ValueError("market selection constructor changed its result")
            return result

        @dataclass(frozen=True)
        class _RepositoryRecord:
            reference: weakref.ReferenceType
            range_store: object
            resolve_binding: object
            select_current: object
            first_calendar_request: object
            next_page: object
            previous_calendar_request: object
            market_requests: object
            observation_to_dict: object
            observation_require_current: object

        repository_records = {}

        class _RepositoryMeta(type):
            def __new__(metaclass, name, bases, namespace):
                if any(isinstance(base, _RepositoryMeta) for base in bases):
                    raise TypeError("market repositories cannot be subclassed")
                return super().__new__(metaclass, name, bases, namespace)

            def __setattr__(self, name, value):
                raise TypeError("market repository type is immutable")

            def __delattr__(self, name):
                raise TypeError("market repository type is immutable")

        def repository_record(value):
            selection_interface()
            if (_binding_identity is not anchored_binding_identity
                    or _read_binding is not anchored_read_binding
                    or _open_binding_read_lease is not anchored_open_binding_read_lease
                    or _close_binding_read_lease is not anchored_close_binding_read_lease
                    or canonical_bytes is not anchored_canonical):
                raise ValueError("market ticket binding interface changed")
            sealed = repository_records.get(id(value))
            if (type(value) is not FormalPolicyMarketRepository or sealed is None
                    or sealed.reference() is not value):
                raise ValueError("market repository is forged, copied, or unregistered")
            if type(sealed.range_store) is not store_type:
                raise ValueError("market repository Store identity changed")
            return sealed

        def owner_page_group(sealed, source, first_request):
            capture = batch_capture.get()
            if capture is None:
                return implementation_page_group(sealed, source, first_request)
            observations = []
            request = first_request
            while request is not None:
                ticket = sealed.range_store.select_current_batch_ticket(
                    capture["journal"], request.request_fingerprint, request=request)
                capture["tickets"].append(ticket)
                observation = ticket.selected()
                if observation is None:
                    return tuple(observations), request
                observations.append(observation)
                request = sealed.next_page(source, observation)
            return tuple(observations), None

        def calendar_for_market(sealed, binding, as_of_utc):
            capture = batch_capture.get()
            if capture is None:
                return assemble_calendar(sealed, binding, as_of_utc)
            ticket = capture["owner"].select_calendar_batch_ticket(
                capture["journal"], binding, as_of_utc)
            capture["calendar_ticket"] = ticket
            return ticket.selected()

        def seal_selection(kind, selected, sealed, binding, as_of_utc, security_id):
            capture = batch_capture.get()
            if capture is None:
                return selected
            owner = capture["owner"]
            if repository_record(owner) is not sealed:
                raise ValueError("market selection ticket owner changed")
            proof = selected.coverage if kind == "calendar" else selected.window
            proof_bytes = None if proof is None else proof.canonical_bytes()
            binding_identity = _binding_identity(binding)
            if proof is not None:
                proof_seal = record(proof,
                    VerifiedCalendarCoverageV1 if kind == "calendar" else VerifiedMarketWindowV1,
                    calendar_records if kind == "calendar" else window_records)
                if (proof_seal.range_store is not sealed.range_store
                        or proof_seal.binding_identity != binding_identity
                        or proof_seal.wire_bytes != proof_bytes):
                    raise ValueError("market selection proof owner changed")
            fields = (selected.pending, selected.lineage, selected.selection_hash)
            identity = id(selected)
            reference = weakref.ref(selected, lambda ref, key=identity:
                selection_records.pop(key, None)
                if selection_records.get(key) is not None
                and selection_records[key][0] is ref else None)
            selection_records[identity] = (reference, owner, kind, fields, proof,
                proof_bytes, binding, canonical_bytes(binding_identity), sealed.range_store,
                tuple(capture["tickets"]), capture.get("calendar_ticket"),
                (security_id, as_of_utc, binding_identity["binding_hash"]))
            capture["sealed_selection"] = selected
            return selected

        def selection_record(owner, selected, kind, capture=None):
            saved = selection_records.get(id(selected))
            if (saved is None or saved[0]() is not selected or saved[1] is not owner
                    or saved[2] != kind or type(selected) is not
                    (calendar_selection_type if kind == "calendar" else market_selection_type)
                    or (selected.pending, selected.lineage, selected.selection_hash) != saved[3]
                    or (selected.coverage if kind == "calendar" else selected.window) is not saved[4]
                    or (None if saved[4] is None else saved[4].canonical_bytes()) != saved[5]):
                raise ValueError("market or calendar selection changed after owner seal")
            if capture is not None and (capture.get("sealed_selection") is not selected
                    or tuple(capture["tickets"]) != saved[9]
                    or capture.get("calendar_ticket") is not saved[10]):
                raise ValueError("market selection token changed")
            return saved

        def assemble_calendar(sealed, binding, as_of_utc):
            def owner_mint(wire, owned_binding, recheck):
                return mint_calendar(wire, owned_binding, sealed.range_store, recheck)
            def owner_seal(selected):
                return seal_selection("calendar", selected, sealed, binding, as_of_utc,
                                      _binding_identity(binding)["exchange"])
            constructor = (calendar_selection_type if batch_capture.get() is None else
                lambda *values: construct_selection(calendar_selection_type, values))
            return implementation_select_calendar(
                sealed, binding, as_of_utc, _mint_calendar=owner_mint,
                _page_group=owner_page_group,
                _select_calendar=assemble_calendar,
                _calendar_selection_type=constructor,
                _seal_selection=owner_seal,
            )

        def assemble_market(sealed, security_id, as_of_utc, *, binding):
            def owner_mint(wire, owned_binding, recheck):
                return mint_window(wire, owned_binding, sealed.range_store, recheck)
            def owner_seal(selected):
                return seal_selection("market", selected, sealed, binding, as_of_utc,
                                      security_id)
            constructor = (market_selection_type if batch_capture.get() is None else
                lambda *values: construct_selection(market_selection_type, values))
            return implementation_select_market(
                sealed, security_id, as_of_utc, binding=binding,
                _mint_window=owner_mint, _page_group=owner_page_group,
                _select_calendar=calendar_for_market, _select_market=assemble_market,
                _market_selection_type=constructor,
                _seal_selection=owner_seal,
            )

        def ticket_evidence(owner, journal, kind, selected, binding, as_of_utc,
                            security_id, capture):
            from .formal_batch_read_journal import _issue_current_ticket, _require_current_ticket
            sealed = repository_record(owner)
            saved = selection_record(owner, selected, kind, capture)
            (_, _, _, fields, proof, proof_bytes, sealed_binding, binding_bytes,
             range_store, lower, sealed_calendar_ticket, request) = saved
            if (sealed_binding is not binding or range_store is not sealed.range_store
                    or request[0:2] != (security_id, as_of_utc)):
                raise ValueError("market ticket request differs from sealed selection")
            baselines = tuple(_require_current_ticket(journal, ticket, sealed.range_store,
                                                       "range")[1] for ticket in lower)
            for ticket in lower:
                sealed.range_store._batch_recheck_ticket(_require_current_ticket(
                    journal, ticket, sealed.range_store, "range")[2])
            calendar_ticket = sealed_calendar_ticket
            if calendar_ticket is not None:
                calendar_selected, calendar_baseline, calendar_evidence = _require_current_ticket(
                    journal, calendar_ticket, owner, "calendar")
                for ticket in calendar_evidence[9]:
                    sealed.range_store._batch_recheck_ticket(_require_current_ticket(
                        journal, ticket, sealed.range_store, "range")[2])
            else:
                calendar_selected, calendar_baseline = None, None
            binding_identity = _binding_identity(binding)
            if canonical_bytes(binding_identity) != binding_bytes:
                raise ValueError("market ticket binding changed after selection")
            baseline = canonical_bytes(dict(kind=kind, request=request,
                fields=[list(fields[0]), list(fields[1]), fields[2]],
                proof=None if proof_bytes is None else proof_bytes.decode(),
                binding=binding_identity,
                range=[value.decode() for value in baselines],
                calendar=None if calendar_baseline is None else calendar_baseline.decode()))
            evidence = (kind, selected, fields, proof_bytes, proof, binding,
                binding_bytes, sealed.range_store, journal, lower,
                calendar_ticket, calendar_selected, request)
            coverage = () if kind == "calendar" else ((security_id,),)
            return _issue_current_ticket(journal, owner, kind, request, baseline,
                                         evidence, coverage, selected)

        class FormalPolicyMarketRepository(metaclass=_RepositoryMeta):
            __slots__ = ("__weakref__",)

            def __init__(self, range_store):
                if type(self) is not FormalPolicyMarketRepository or type(range_store) is not store_type:
                    raise ValueError("market repository requires an exact FormalRangeStore")
                identity = id(self)
                reference = weakref.ref(self, lambda ref, key=identity:
                    repository_records.pop(key, None)
                    if repository_records.get(key) is not None
                    and repository_records[key].reference is ref else None)
                repository_records[identity] = _RepositoryRecord(
                    reference, range_store, resolve_binding, select_current,
                    first_calendar_request, next_page, previous_calendar_request,
                    market_requests, observation_to_dict, observation_require_current,
                )
                repository_record(self)

            def __setattr__(self, name, value):
                raise AttributeError("market repositories are immutable")

            def __delattr__(self, name):
                raise AttributeError("market repositories are immutable")

            def select_calendar(self, binding, as_of_utc):
                return assemble_calendar(repository_record(self), binding, as_of_utc)

            def select(self, security_id, as_of_utc, *, binding):
                return assemble_market(repository_record(self), security_id, as_of_utc,
                                       binding=binding)

            def _batch_journal_identity(self):
                sealed = repository_record(self)
                return sealed.range_store._batch_journal_identity()[0], sealed.range_store

            def select_calendar_batch_ticket(self, journal, binding, as_of_utc):
                from .formal_batch_read_journal import _require_current_scope
                sealed = repository_record(self)
                lease = None
                try:
                    lease = _open_binding_read_lease(
                        binding, journal, ("calendar", as_of_utc))
                    identity = _binding_identity(binding)
                    _require_current_scope(journal, self,
                        root=identity["registry_manifest_hash"], as_of_utc=as_of_utc,
                        population=(identity["exchange"],))
                    capture = {"journal": journal, "owner": self, "tickets": []}
                    reset = batch_capture.set(capture)
                    try:
                        selected = assemble_calendar(sealed, binding, as_of_utc)
                    finally:
                        batch_capture.reset(reset)
                    ticket = ticket_evidence(self, journal, "calendar", selected, binding,
                                             as_of_utc, identity["exchange"], capture)
                    _close_binding_read_lease(lease)
                    return ticket
                except BaseException:
                    if lease is not None:
                        try:
                            _close_binding_read_lease(lease)
                        except ValueError:
                            pass
                    try:
                        journal.close()
                    except ValueError:
                        pass
                    raise

            def select_current_batch_ticket(self, journal, security_id, as_of_utc, *, binding):
                from .formal_batch_read_journal import _require_current_scope
                sealed = repository_record(self)
                lease = None
                try:
                    lease = _open_binding_read_lease(
                        binding, journal, ("market", security_id, as_of_utc))
                    identity = _binding_identity(binding)
                    _require_current_scope(journal, self,
                        root=identity["registry_manifest_hash"], as_of_utc=as_of_utc,
                        population=(security_id,))
                    capture = {"journal": journal, "owner": self, "tickets": []}
                    reset = batch_capture.set(capture)
                    try:
                        selected = assemble_market(
                            sealed, security_id, as_of_utc, binding=binding)
                    finally:
                        batch_capture.reset(reset)
                    ticket = ticket_evidence(self, journal, "market", selected, binding,
                                             as_of_utc, security_id, capture)
                    _close_binding_read_lease(lease)
                    return ticket
                except BaseException:
                    if lease is not None:
                        try:
                            _close_binding_read_lease(lease)
                        except ValueError:
                            pass
                    try:
                        journal.close()
                    except ValueError:
                        pass
                    raise

            def _batch_recheck_ticket(self, evidence):
                from .formal_batch_read_journal import _require_current_ticket
                (kind, selected, fields, proof_bytes, proof, binding, binding_bytes,
                 range_store, journal, lower, calendar_ticket, calendar_selected,
                 request) = evidence
                sealed = repository_record(self)
                if (range_store is not sealed.range_store
                        or selection_record(self, selected, kind)[3] != fields
                        or canonical_bytes(_binding_identity(binding)) != binding_bytes
                        or type(selected) is not (calendar_selection_type if kind == "calendar"
                                                    else market_selection_type)
                        or (selected.pending, selected.lineage, selected.selection_hash) != fields
                        or (selected.coverage if kind == "calendar" else selected.window) is not proof
                        or (None if proof is None else proof.canonical_bytes()) != proof_bytes):
                    raise ValueError("market or calendar ticket selection changed")
                if kind == "market":
                    if calendar_ticket is None or _require_current_ticket(
                            journal, calendar_ticket, self, "calendar")[0] is not calendar_selected:
                        raise ValueError("market ticket calendar ownership changed")
                elif kind != "calendar" or calendar_ticket is not None:
                    raise ValueError("calendar ticket evidence is invalid")
                for ticket in lower:
                    _require_current_ticket(journal, ticket, range_store, "range")

            def __copy__(self):
                raise TypeError("market repositories cannot be copied")

            def __deepcopy__(self, memo):
                raise TypeError("market repositories cannot be copied")

        return FormalPolicyMarketRepository

    return (VerifiedCalendarCoverageV1, VerifiedMarketWindowV1,
            calendar_proof_authority, install_market_owner)


(VerifiedCalendarCoverageV1, VerifiedMarketWindowV1,
 _calendar_proof_authority, _install_market_proof_owner) = _build_proof_types()
del _build_proof_types


# Deliberately after proof ownership: this order completes the circular module
# initialization eagerly for source-first and market-first imports alike.
from .formal_range_source import (
    FormalRangeRequestV1,
    FormalRangeSource,
    RangeObservation,
)
from .formal_range_store import FormalRangeStore


def evaluate_window(trading_days: tuple[str, ...], daily_rows: dict[str, dict]) -> dict:
    """Evaluate price completeness and the 20-day veto as independent axes."""
    if type(trading_days) is not tuple or not 1 <= len(trading_days) <= 250:
        raise ValueError("one to 250 trading days are required")
    parsed = tuple(_iso_date(day, "trading day") for day in trading_days)
    if tuple(sorted(trading_days)) != trading_days or len(set(trading_days)) != len(trading_days):
        raise ValueError("trading days must be sorted and unique")
    if parsed[-1] > _FREEZE_DATE:
        raise ValueError("trading days cannot exceed the formal freeze")
    if type(daily_rows) is not dict or any(type(key) is not str for key in daily_rows):
        raise ValueError("daily rows must be an exact date mapping")

    days = trading_days[-250:]
    effective = {}
    unresolved = {}
    for day in days:
        row = daily_rows.get(day)
        if row is None:
            effective[day] = None
            unresolved[day] = "market_coverage_missing"
            continue
        if type(row) is not dict or row.get("coverage") not in {"covered", "missing", "domain_conflict"}:
            raise ValueError("daily coverage state is invalid")
        if row["coverage"] != "covered":
            if row["coverage"] == "domain_conflict":
                if (set(row) != {"coverage", "reason"} or type(row["reason"]) is not str
                        or not row["reason"] or row["reason"] != row["reason"].strip()):
                    raise ValueError("domain conflict row shape is invalid")
                unresolved[day] = "market_domain_conflict"
            else:
                if (set(row) not in ({"coverage"}, {"coverage", "reason"})
                        or ("reason" in row and row["reason"] not in {
                            "market_coverage_missing", "visibility_unproven"})):
                    raise ValueError("missing market row shape is invalid")
                unresolved[day] = row.get("reason", "market_coverage_missing")
            effective[day] = None
            continue
        required = {"coverage", "exchange_allows_trading", "volume", "turnover", "close"}
        if set(row) != required or type(row["exchange_allows_trading"]) is not bool:
            raise ValueError("covered market row shape is invalid")
        volume = _decimal_text(row["volume"], "market volume")
        turnover = _decimal_text(row["turnover"], "market turnover")
        close = row["close"]
        if type(close) is not dict or close.get("state") not in {"positive", "unavailable"}:
            raise ValueError("market close state is invalid")
        if close["state"] == "positive":
            if set(close) != {"state", "value"}:
                raise ValueError("positive close shape is invalid")
            _decimal_text(close["value"], "market close", positive=True)
        elif set(close) != {"state", "reason"} or type(close["reason"]) is not str or not close["reason"]:
            raise ValueError("unavailable close shape is invalid")
        effective[day] = row["exchange_allows_trading"] and volume > 0 and turnover > 0

    tail = [effective[day] for day in days[-20:]]
    veto = ("clear" if any(value is True for value in tail) else
            "proven" if len(tail) == 20 and all(value is False for value in tail) else
            "pending")
    pending = []
    result = dict(price_state="incomplete", price=None, price_date=None,
                  stale_days=None, stale_at_least=None, veto_state=veto,
                  pending=pending)
    for stale, day in enumerate(reversed(days)):
        active = effective[day]
        if active is None:
            pending.append(unresolved[day])
            return result
        if active:
            close = daily_rows[day]["close"]
            if close["state"] != "positive":
                pending.append("market_price_missing")
                return result
            result.update(price_state="positive_close_complete", price=close["value"],
                          price_date=day, stale_days=stale)
            return result
    if len(days) == 250:
        result.update(price_state="confirmed_no_price_250", stale_at_least=250)
        pending.append("market_evidence_missing")
    else:
        pending.append("calendar_coverage_missing")
    return result


@dataclass(frozen=True, slots=True, weakref_slot=True)
class CalendarSelection:
    coverage: VerifiedCalendarCoverageV1 | None
    pending: tuple[str, ...]
    lineage: tuple[str, ...]
    selection_hash: str
    _check: object

    def recheck(self):
        self._check()


@dataclass(frozen=True, slots=True, weakref_slot=True)
class MarketSelection:
    window: VerifiedMarketWindowV1 | None
    pending: tuple[str, ...]
    lineage: tuple[str, ...]
    selection_hash: str
    _check: object

    def recheck(self):
        self._check()


def _visible(container, as_of):
    published = _aware(container["published_at_utc"], "published_at_utc")
    if published > as_of:
        return False
    if container["published_precision"] == "timestamp":
        effective = _aware(container["effective_at_utc"], "effective_at_utc")
        return effective <= as_of
    # A date-only pair is only a reference to possible temporal evidence.  W1
    # owns no authenticated resolver for that reference, so syntax alone never
    # upgrades it to freeze-visible evidence.
    return False


def _dates_between(start, end):
    cursor = _iso_date(start, "coverage start")
    finish = _iso_date(end, "coverage end")
    while cursor <= finish:
        yield cursor.isoformat()
        cursor += timedelta(days=1)


class _MarketRepositoryImplementation:
    def _page_group(sealed, source, first_request):
        observations = []
        request = first_request
        while request is not None:
            observation = sealed.select_current(
                sealed.range_store, request.request_fingerprint)
            if observation is None:
                return tuple(observations), request
            observations.append(observation)
            request = sealed.next_page(source, observation)
        return tuple(observations), None

    def select_calendar(sealed, binding, as_of_utc, *, _mint_calendar, _page_group,
                        _select_calendar, _calendar_selection_type,
                        _seal_selection) -> CalendarSelection:
        if type(binding) is not _binding_type:
            raise ValueError("calendar selection requires a genuine range binding")
        as_of = _aware(as_of_utc, "calendar as_of_utc")
        if as_of_utc != _FREEZE_UTC:
            raise ValueError("calendar selection requires the formal freeze")
        owned_binding, source = sealed.resolve_binding(sealed.range_store, binding)
        request = sealed.first_calendar_request(source, as_of_utc)
        groups = []
        missing = None
        current_request = request
        open_count = 0
        while current_request is not None and open_count < 250:
            group, missing = _page_group(sealed, source, current_request)
            if missing is not None:
                break
            if not group:
                missing = current_request
                break
            groups.append((current_request, group))
            open_count += sum(
                1 for observation in group
                for row in sealed.observation_to_dict(observation)["document"]["rows"]
                if type(row) is dict and row.get("is_open") is True
            )
            current_request = sealed.previous_calendar_request(source, group[-1])
        observations = tuple(item for _, group in groups for item in group)
        if not groups:
            pending = ("calendar_coverage_missing",)
            identity = hashlib.sha256(canonical_bytes({"pending": list(pending),
                "request": request.to_dict()})).hexdigest()
            def check_missing():
                sealed.resolve_binding(sealed.range_store, owned_binding)
                if (missing is not None and sealed.select_current(
                        sealed.range_store, missing.request_fingerprint) is not None):
                    raise ValueError("calendar selection changed")
            return _seal_selection(_calendar_selection_type(None, pending,
                (), identity, check_missing))

        documents = []
        coverage_ranges = []
        coverage_generations = []
        request_ranges = []
        rows = []
        for group_request, group in groups:
            group_wires = [sealed.observation_to_dict(item) for item in group]
            group_documents = [item["document"] for item in group_wires]
            first = group_documents[0]
            count = first["page_count"]
            generation_pairs = {
                (document["upstream_generation"], item["generation"]["refresh_generation"])
                for item, document in zip(group_wires, group_documents)
            }
            if (len(group_documents) != count
                    or [item["page_index"] for item in group_documents] != list(range(1, count + 1))
                    or any(item["record_count"] != first["record_count"]
                           or item["coverage"] != first["coverage"]
                           or item["upstream_generation"] != first["upstream_generation"]
                           for item in group_documents)
                    or len(generation_pairs) != 1
                    or sum(item["page_record_count"] for item in group_documents) != first["record_count"]
                    or not first["coverage"]["complete"]):
                raise ValueError("calendar page group is incomplete or inconsistent")
            documents.extend(group_documents)
            rows.extend(row for document in group_documents for row in document["rows"])
            coverage_ranges.append(first["coverage"])
            coverage_generations.append(next(iter(generation_pairs)))
            request_ranges.append({"start_date": group_request.start_date,
                                   "end_date": group_request.end_date})
        if len(set(coverage_generations)) != 1:
            raise ValueError("calendar coverage generations cannot be spliced")
        ordered_coverage = sorted(coverage_ranges, key=lambda item: item["start_date"])
        if any(_iso_date(left["end_date"], "coverage end") + timedelta(days=1)
               != _iso_date(right["start_date"], "coverage start")
               for left, right in zip(ordered_coverage, ordered_coverage[1:])):
            raise ValueError("calendar coverage intervals must be adjacent")
        expected_fields = {"date", "is_open", "published_at_utc", "published_precision",
            "effective_at_utc", "effective_time_evidence_hash", "captured_at_utc"}
        by_date = {}
        visibility_missing = False
        for row in rows:
            if type(row) is not dict or set(row) != expected_fields or type(row["is_open"]) is not bool:
                raise ValueError("calendar row shape is invalid")
            day = _iso_date(row["date"], "calendar row date").isoformat()
            if day in by_date:
                raise ValueError("calendar coverage has a duplicate date")
            if not _visible(row, as_of):
                visibility_missing = True
            by_date[day] = row
        expected_dates = tuple(sorted(day for coverage in coverage_ranges
            for day in _dates_between(coverage["start_date"], coverage["end_date"])))
        if len(expected_dates) != len(set(expected_dates)):
            raise ValueError("calendar coverage intervals overlap")
        if set(by_date) - set(expected_dates):
            raise ValueError("calendar coverage contains a date outside its declaration")
        if set(expected_dates) - set(by_date):
            pending = ("calendar_coverage_missing",)
            lineage = tuple(sealed.observation_to_dict(item)["observation_hash"]
                            for item in observations)
            identity = hashlib.sha256(canonical_bytes({"pending": list(pending),
                "lineage": list(lineage)})).hexdigest()
            return _seal_selection(_calendar_selection_type(None, pending, lineage, identity,
                lambda: tuple(sealed.observation_require_current(item)
                              for item in observations)))
        if visibility_missing or not all(_visible(document, as_of) for document in documents):
            pending = ("visibility_unproven",)
            identity = hashlib.sha256(canonical_bytes({"pending": list(pending),
                "lineage": [sealed.observation_to_dict(item)["observation_hash"]
                            for item in observations]})).hexdigest()
            return _seal_selection(_calendar_selection_type(None, pending,
                tuple(sealed.observation_to_dict(item)["observation_hash"]
                      for item in observations), identity,
                lambda: tuple(sealed.observation_require_current(item)
                              for item in observations)))
        if as_of.date().isoformat() not in by_date or by_date[as_of.date().isoformat()]["is_open"] is not True:
            raise ValueError("formal freeze is not proven as a trading day")
        trading = tuple(day for day in expected_dates if by_date[day]["is_open"])[-250:]
        view = _read_binding(owned_binding)
        config = view["calendar_config"]
        lineage = tuple(sealed.observation_to_dict(item)["observation_hash"]
                        for item in observations)
        wire = {
            "schema_version": "formal-calendar-coverage-v1",
            "registry_manifest_hash": view["registry_manifest_hash"],
            "source_registry_hash": view["source_registry_hash"],
            "binding_hash": view["binding_hash"],
            "rule_id": view["rule_id"],
            "exchange": view["exchange"],
            "as_of_utc": as_of_utc,
            "calendar_descriptor_id": config.calendar_descriptor_id,
            "calendar_config_id": config.entry_id,
            "request_version": config.request_version,
            "parser_id": config.parser_id,
            "parser_version": config.parser_version,
            "mapping_version": config.mapping_version,
            "normalizer_version": config.normalizer_version,
            "request_start": min(item["start_date"] for item in request_ranges),
            "request_end": max(item["end_date"] for item in request_ranges),
            "request_ranges": sorted(request_ranges, key=lambda item: item["start_date"]),
            "covered_start": min(item["start_date"] for item in coverage_ranges),
            "covered_end": max(item["end_date"] for item in coverage_ranges),
            "calendar_records": [{"date": day, "is_trading_day": by_date[day]["is_open"]}
                                 for day in expected_dates],
            "trading_days": list(trading),
            "lineage": list(lineage),
            "observations": [sealed.observation_to_dict(item) for item in observations],
            "upstream_generations": sorted({item["upstream_generation"] for item in documents}),
        }
        expected_proof_wire = dict(wire,
            coverage_hash=hashlib.sha256(canonical_bytes(wire)).hexdigest())
        def recheck():
            current = _select_calendar(sealed, owned_binding, as_of_utc)
            if (current.coverage is None
                    or current.coverage.canonical_bytes() != canonical_bytes(expected_proof_wire)):
                raise ValueError("calendar coverage selection changed")
        proof = _mint_calendar(wire, owned_binding, recheck)
        selection_hash = hashlib.sha256(proof.canonical_bytes()).hexdigest()
        return _seal_selection(_calendar_selection_type(
            proof, (), lineage, selection_hash, proof.require_current))

    def select(sealed, security_id, as_of_utc, *, binding, _mint_window, _page_group,
               _select_calendar, _select_market,
               _market_selection_type, _seal_selection) -> MarketSelection:
        if type(security_id) is not str or _SECURITY.fullmatch(security_id) is None:
            raise ValueError("market selection security_id is invalid")
        owned_binding, source = sealed.resolve_binding(sealed.range_store, binding)
        calendar = _select_calendar(sealed, owned_binding, as_of_utc)
        if calendar.coverage is None:
            return _seal_selection(_market_selection_type(None, calendar.pending,
                calendar.lineage, calendar.selection_hash, calendar.recheck))
        coverage_payload = calendar.coverage.to_dict()
        days = tuple(coverage_payload["trading_days"])[-250:]
        requests = sealed.market_requests(
            source, security_id, calendar_coverage=calendar.coverage)
        observations = []
        missing_reasons = {}
        rows = {}
        seen_dates = set()
        for request in requests:
            group, missing = _page_group(sealed, source, request)
            observations.extend(group)
            requested_days = {day for day in days if request.start_date <= day <= request.end_date}
            if missing is not None:
                for day in requested_days:
                    missing_reasons.setdefault(day, "market_coverage_missing")
                continue
            documents = [sealed.observation_to_dict(item)["document"] for item in group]
            first = documents[0]
            if (len(documents) != first["page_count"]
                    or [item["page_index"] for item in documents] != list(range(1, first["page_count"] + 1))
                    or sum(item["page_record_count"] for item in documents) != first["record_count"]
                    or any(item["record_count"] != first["record_count"]
                           or item["upstream_generation"] != first["upstream_generation"]
                           for item in documents)):
                raise ValueError("market page group is incomplete or inconsistent")
            for observation, document in zip(group, documents):
                if not _visible(document, _aware(as_of_utc, "market as_of_utc")):
                    for day in requested_days:
                        missing_reasons[day] = "visibility_unproven"
                    continue
                for raw in document["rows"]:
                    visibility = {"published_at_utc", "published_precision", "effective_at_utc",
                                  "effective_time_evidence_hash", "captured_at_utc"}
                    expected = {"date", "exchange_allows_trading", "volume", "volume_unit",
                        "turnover", "turnover_unit", "close", "close_unit", "published_at_utc",
                        "published_precision", "effective_at_utc", "effective_time_evidence_hash",
                        "captured_at_utc"}
                    conflict = {"date", "coverage", "reason"} | visibility
                    if type(raw) is not dict or set(raw) not in (expected, conflict):
                        raise ValueError("market row shape is invalid")
                    day = _iso_date(raw["date"], "market row date").isoformat()
                    if day not in requested_days or day in seen_dates:
                        raise ValueError("market row date is duplicate or outside required trading days")
                    seen_dates.add(day)
                    if not _visible(raw, _aware(as_of_utc, "market as_of_utc")):
                        missing_reasons[day] = "visibility_unproven"
                        continue
                    if set(raw) == conflict:
                        if (raw["coverage"] != "domain_conflict"
                                or type(raw["reason"]) is not str or not raw["reason"]
                                or raw["reason"] != raw["reason"].strip()):
                            raise ValueError("market domain conflict row is invalid")
                        rows[day] = {"coverage": "domain_conflict", "reason": raw["reason"],
                                     "observation_hash": sealed.observation_to_dict(
                                         observation)["observation_hash"]}
                    else:
                        if (raw["volume_unit"] != "shares" or raw["turnover_unit"] != "CNY"
                                or raw["close_unit"] != "CNY_per_share"):
                            raise ValueError("market normalized units differ from signed contract")
                        rows[day] = {"coverage": "covered", "exchange_allows_trading": raw["exchange_allows_trading"],
                            "volume": raw["volume"], "turnover": raw["turnover"], "close": raw["close"],
                            "observation_hash": sealed.observation_to_dict(
                                observation)["observation_hash"]}
            for day in requested_days - set(rows):
                missing_reasons.setdefault(day, "market_coverage_missing")
        algorithm_rows = {}
        daily_records = []
        for day in days:
            if day in rows and day not in missing_reasons:
                if rows[day]["coverage"] == "domain_conflict":
                    algorithm_rows[day] = {key: rows[day][key]
                                           for key in ("coverage", "reason")}
                else:
                    algorithm_rows[day] = {key: rows[day][key] for key in
                        ("coverage", "exchange_allows_trading", "volume", "turnover", "close")}
                daily_records.append(dict(date=day, **rows[day]))
            else:
                reason = missing_reasons.get(day, "market_coverage_missing")
                algorithm_rows[day] = {"coverage": "missing", "reason": reason}
                daily_records.append({"date": day, "coverage": "missing", "reason": reason})
        result = evaluate_window(days, algorithm_rows)
        pending = set(result["pending"])
        lineage = tuple(sealed.observation_to_dict(item)["observation_hash"]
                        for item in observations)
        view = _read_binding(owned_binding)
        market_config = view["market_config"]
        calendar_config = view["calendar_config"]
        wire = {
            "schema_version": "verified-market-window-v1",
            "security_id": security_id,
            "exchange": view["exchange"],
            "as_of_utc": as_of_utc,
            "registry_manifest_hash": view["registry_manifest_hash"],
            "source_registry_hash": view["source_registry_hash"],
            "binding_hash": view["binding_hash"],
            "rule_id": view["rule_id"],
            "market_descriptor_id": market_config.anchor_descriptor_id,
            "calendar_descriptor_id": calendar_config.calendar_descriptor_id,
            "market_config_id": market_config.entry_id,
            "calendar_config_id": calendar_config.entry_id,
            "request_version": market_config.request_version,
            "parser_id": market_config.parser_id,
            "parser_version": market_config.parser_version,
            "mapping_version": market_config.mapping_version,
            "normalizer_version": market_config.normalizer_version,
            "request_ranges": [{"start_date": item.start_date, "end_date": item.end_date,
                                "request_fingerprint": item.request_fingerprint} for item in requests],
            "required_trading_days": list(days),
            "daily_records": daily_records,
            "calendar_coverage_hash": coverage_payload["coverage_hash"],
            "lineage": list(lineage),
            "observations": [sealed.observation_to_dict(item) for item in observations],
            **{key: result[key] for key in ("price_state", "price", "price_date", "stale_days",
                                             "stale_at_least", "veto_state")},
            "pending": sorted(pending),
        }
        expected_window_wire = dict(wire,
            window_hash=hashlib.sha256(canonical_bytes(wire)).hexdigest())
        def recheck():
            current = _select_market(
                sealed, security_id, as_of_utc, binding=owned_binding)
            if (current.window is None
                    or current.window.canonical_bytes() != canonical_bytes(expected_window_wire)):
                raise ValueError("market window selection changed")
        window = _mint_window(wire, owned_binding, recheck)
        return _seal_selection(_market_selection_type(window, tuple(sorted(pending)), lineage,
            hashlib.sha256(window.canonical_bytes()).hexdigest(), window.require_current))


FormalPolicyMarketRepository = _install_market_proof_owner((
    FormalRangeStore,
    FormalRangeStore.resolve_planning_binding,
    FormalRangeStore.select_current,
    FormalRangeSource.first_calendar_request,
    FormalRangeSource.next_page,
    FormalRangeSource.previous_calendar_request,
    FormalRangeSource.market_requests,
    RangeObservation.to_dict,
    RangeObservation.require_current,
    _MarketRepositoryImplementation._page_group,
    _MarketRepositoryImplementation.select_calendar,
    _MarketRepositoryImplementation.select,
    (CalendarSelection, MarketSelection),
))
del _install_market_proof_owner, _MarketRepositoryImplementation


def plan_next_window_request(security_id, as_of_utc, *, binding, range_store):
    """Return only the next authenticated acquisition request; never fetch."""
    repository = FormalPolicyMarketRepository(range_store)
    owned_binding, source = range_store.resolve_planning_binding(binding)
    first_calendar = source.first_calendar_request(as_of_utc)
    calendar_page = range_store.select_current(first_calendar.request_fingerprint)
    if calendar_page is None:
        return first_calendar
    successor = source.next_page(calendar_page)
    while successor is not None:
        page = range_store.select_current(successor.request_fingerprint)
        if page is None:
            return successor
        successor = source.next_page(page)
    calendar = repository.select_calendar(owned_binding, as_of_utc)
    if calendar.coverage is None:
        # A verified first group whose content cannot form coverage needs a new
        # source generation or temporal evidence, not the identical request.
        return None
    requests = source.market_requests(security_id, calendar_coverage=calendar.coverage)
    for request in requests:
        observation = range_store.select_current(request.request_fingerprint)
        if observation is None:
            return request
        successor = source.next_page(observation)
        while successor is not None:
            page = range_store.select_current(successor.request_fingerprint)
            if page is None:
                return successor
            successor = source.next_page(page)
    selection = repository.select(security_id, as_of_utc, binding=owned_binding)
    if selection.window is None:
        return None
    if selection.window.price_state != "incomplete":
        return None
    if (selection.window.price_state == "incomplete"
            and len(selection.window.required_trading_days) < 250
            and tuple(selection.window.pending) == ("calendar_coverage_missing",)):
        payload = calendar.coverage.to_dict()
        last = payload["observations"][-1]
        oldest = range_store.read_verified(last["task"]["id"])
        return source.previous_calendar_request(oldest)
    return None


__all__ = [
    "CalendarSelection", "FormalPolicyMarketRepository", "MarketSelection",
    "VerifiedCalendarCoverageV1", "VerifiedMarketWindowV1", "evaluate_window",
    "plan_next_window_request",
]
