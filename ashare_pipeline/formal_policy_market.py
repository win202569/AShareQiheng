"""Authenticated calendar coverage and independent market-window outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from types import MappingProxyType
import weakref

from .formal_policy_values import canonical_bytes
from .formal_range_contract import _range_binding_planning_authority
from .formal_range_format import RangeConfig, _range_config_to_dict
from .formal_time import FORMAL_FREEZE_AT_CN


_FREEZE_UTC = datetime.fromisoformat(FORMAL_FREEZE_AT_CN).astimezone(timezone.utc).isoformat()
_FREEZE_DATE = datetime.fromisoformat(_FREEZE_UTC).date()
_SECURITY = re.compile(r"^(?:SH|SZ|BJ)[0-9]{6}$")
_binding_type, _read_binding = _range_binding_planning_authority()


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

    def mint(proof_type, records, wire, binding, recheck, hash_field):
        identity = _binding_identity(binding)
        content = _detached(wire)
        digest = hashlib.sha256(canonical_bytes(content)).hexdigest()
        content[hash_field] = digest
        result = object.__new__(proof_type)
        identity_key = id(result)
        reference = weakref.ref(result, lambda ref, key=identity_key: records.pop(key, None))
        records[identity_key] = _ProofRecord(reference, content, canonical_bytes(content),
                                             identity, recheck)
        return result

    def mint_calendar(wire, binding, recheck):
        return mint(VerifiedCalendarCoverageV1, calendar_records, wire, binding,
                    recheck, "coverage_hash")

    def mint_window(wire, binding, recheck):
        return mint(VerifiedMarketWindowV1, window_records, wire, binding,
                    recheck, "window_hash")

    def require_calendar(proof, *, binding):
        sealed = record(proof, VerifiedCalendarCoverageV1, calendar_records)
        VerifiedCalendarCoverageV1.require_current(proof)
        if _binding_identity(binding) != sealed.binding_identity:
            raise ValueError("calendar coverage belongs to another binding")
        return _detached(sealed.wire)

    def calendar_record(proof):
        return record(proof, VerifiedCalendarCoverageV1, calendar_records)

    return (VerifiedCalendarCoverageV1, VerifiedMarketWindowV1, mint_calendar,
            mint_window, require_calendar, calendar_record)


(VerifiedCalendarCoverageV1, VerifiedMarketWindowV1, _mint_calendar_coverage,
 _mint_market_window, _require_calendar_coverage,
 _calendar_record) = _build_proof_types()
del _build_proof_types


def _make_calendar_proof_authority():
    proof_type = VerifiedCalendarCoverageV1
    require_current = VerifiedCalendarCoverageV1.require_current
    to_dict = VerifiedCalendarCoverageV1.to_dict
    require = _require_calendar_coverage

    def authority():
        return proof_type, require_current, to_dict, require

    return authority


_calendar_proof_authority = _make_calendar_proof_authority()
del _make_calendar_proof_authority


# Deliberately after proof ownership: this order completes the circular module
# initialization eagerly for source-first and market-first imports alike.
from .formal_range_source import FormalRangeRequestV1, FormalRangeSource
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
    conflict = False
    for day in days:
        row = daily_rows.get(day)
        if row is None:
            effective[day] = None
            continue
        if type(row) is not dict or row.get("coverage") not in {"covered", "missing", "domain_conflict"}:
            raise ValueError("daily coverage state is invalid")
        if row["coverage"] != "covered":
            effective[day] = None
            conflict = conflict or row["coverage"] == "domain_conflict"
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
            pending.append("market_domain_conflict" if conflict else "market_coverage_missing")
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


@dataclass(frozen=True, slots=True)
class CalendarSelection:
    coverage: VerifiedCalendarCoverageV1 | None
    pending: tuple[str, ...]
    lineage: tuple[str, ...]
    selection_hash: str
    _check: object

    def recheck(self):
        self._check()


@dataclass(frozen=True, slots=True)
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
    effective = container["effective_at_utc"]
    evidence = container["effective_time_evidence_hash"]
    return effective is not None and evidence is not None and _aware(effective, "effective_at_utc") <= as_of


def _dates_between(start, end):
    cursor = _iso_date(start, "coverage start")
    finish = _iso_date(end, "coverage end")
    while cursor <= finish:
        yield cursor.isoformat()
        cursor += timedelta(days=1)


class FormalPolicyMarketRepository:
    def __init__(self, range_store):
        if type(range_store) is not FormalRangeStore:
            raise ValueError("market repository requires an exact FormalRangeStore")
        self._store = range_store

    def _page_group(self, source, first_request):
        observations = []
        request = first_request
        while request is not None:
            observation = self._store.select_current(request.request_fingerprint)
            if observation is None:
                return tuple(observations), request
            observations.append(observation)
            request = source.next_page(observation)
        return tuple(observations), None

    def select_calendar(self, binding, as_of_utc) -> CalendarSelection:
        if type(binding) is not _binding_type:
            raise ValueError("calendar selection requires a genuine range binding")
        as_of = _aware(as_of_utc, "calendar as_of_utc")
        if as_of_utc != _FREEZE_UTC:
            raise ValueError("calendar selection requires the formal freeze")
        owned_binding, source = self._store.resolve_planning_binding(binding)
        request = source.first_calendar_request(as_of_utc)
        groups = []
        missing = None
        current_request = request
        open_count = 0
        while current_request is not None and open_count < 250:
            group, missing = self._page_group(source, current_request)
            if missing is not None:
                break
            if not group:
                missing = current_request
                break
            groups.append((current_request, group))
            open_count += sum(
                1 for observation in group
                for row in observation.to_dict()["document"]["rows"]
                if type(row) is dict and row.get("is_open") is True
            )
            current_request = source.previous_calendar_request(group[-1])
        observations = tuple(item for _, group in groups for item in group)
        if not groups:
            pending = ("calendar_coverage_missing",)
            identity = hashlib.sha256(canonical_bytes({"pending": list(pending),
                "request": request.to_dict()})).hexdigest()
            def check_missing():
                self._store.resolve_planning_binding(owned_binding)
                if missing is not None and self._store.select_current(missing.request_fingerprint) is not None:
                    raise ValueError("calendar selection changed")
            return CalendarSelection(None, pending,
                (), identity, check_missing)

        documents = []
        coverage_ranges = []
        request_ranges = []
        rows = []
        for group_request, group in groups:
            group_documents = [item.to_dict()["document"] for item in group]
            first = group_documents[0]
            count = first["page_count"]
            if (len(group_documents) != count
                    or [item["page_index"] for item in group_documents] != list(range(1, count + 1))
                    or any(item["record_count"] != first["record_count"]
                           or item["coverage"] != first["coverage"]
                           or item["upstream_generation"] != first["upstream_generation"]
                           for item in group_documents)
                    or sum(item["page_record_count"] for item in group_documents) != first["record_count"]
                    or not first["coverage"]["complete"]):
                raise ValueError("calendar page group is incomplete or inconsistent")
            documents.extend(group_documents)
            rows.extend(row for document in group_documents for row in document["rows"])
            coverage_ranges.append(first["coverage"])
            request_ranges.append({"start_date": group_request.start_date,
                                   "end_date": group_request.end_date})
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
            lineage = tuple(item.observation_hash for item in observations)
            identity = hashlib.sha256(canonical_bytes({"pending": list(pending),
                "lineage": list(lineage)})).hexdigest()
            return CalendarSelection(None, pending, lineage, identity,
                lambda: tuple(item.require_current() for item in observations))
        if visibility_missing or not all(_visible(document, as_of) for document in documents):
            pending = ("visibility_unproven",)
            identity = hashlib.sha256(canonical_bytes({"pending": list(pending),
                "lineage": [item.observation_hash for item in observations]})).hexdigest()
            return CalendarSelection(None, pending,
                tuple(item.observation_hash for item in observations), identity,
                lambda: tuple(item.require_current() for item in observations))
        if as_of.date().isoformat() not in by_date or by_date[as_of.date().isoformat()]["is_open"] is not True:
            raise ValueError("formal freeze is not proven as a trading day")
        trading = tuple(day for day in expected_dates if by_date[day]["is_open"])[-250:]
        config = _read_binding(owned_binding)["calendar_config"]
        lineage = tuple(item.observation_hash for item in observations)
        wire = {
            "schema_version": "formal-calendar-coverage-v1",
            "registry_manifest_hash": _read_binding(owned_binding)["registry_manifest_hash"],
            "source_registry_hash": _read_binding(owned_binding)["source_registry_hash"],
            "binding_hash": _read_binding(owned_binding)["binding_hash"],
            "rule_id": _read_binding(owned_binding)["rule_id"],
            "exchange": _read_binding(owned_binding)["exchange"],
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
            "observations": [item.to_dict() for item in observations],
            "upstream_generations": sorted({item["upstream_generation"] for item in documents}),
        }
        def recheck():
            _read_binding(owned_binding)
            for item in observations:
                item.require_current()
        proof = _mint_calendar_coverage(wire, owned_binding, recheck)
        selection_hash = hashlib.sha256(proof.canonical_bytes()).hexdigest()
        return CalendarSelection(proof, (), lineage, selection_hash, proof.require_current)

    def select(self, security_id, as_of_utc, *, binding) -> MarketSelection:
        if type(security_id) is not str or _SECURITY.fullmatch(security_id) is None:
            raise ValueError("market selection security_id is invalid")
        owned_binding, source = self._store.resolve_planning_binding(binding)
        calendar = self.select_calendar(owned_binding, as_of_utc)
        if calendar.coverage is None:
            return MarketSelection(None, calendar.pending, calendar.lineage,
                calendar.selection_hash, calendar.recheck)
        coverage_payload = _require_calendar_coverage(calendar.coverage, binding=owned_binding)
        days = tuple(coverage_payload["trading_days"])[-250:]
        requests = source.market_requests(security_id, calendar_coverage=calendar.coverage)
        observations = []
        missing_dates = set()
        rows = {}
        pending = set()
        for request in requests:
            group, missing = self._page_group(source, request)
            observations.extend(group)
            requested_days = {day for day in days if request.start_date <= day <= request.end_date}
            if missing is not None:
                missing_dates.update(requested_days)
                pending.add("market_coverage_missing")
                continue
            documents = [item.to_dict()["document"] for item in group]
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
                    pending.add("visibility_unproven")
                    missing_dates.update(requested_days)
                    continue
                for raw in document["rows"]:
                    expected = {"date", "exchange_allows_trading", "volume", "volume_unit",
                        "turnover", "turnover_unit", "close", "close_unit", "published_at_utc",
                        "published_precision", "effective_at_utc", "effective_time_evidence_hash",
                        "captured_at_utc"}
                    if type(raw) is not dict or set(raw) != expected:
                        raise ValueError("market row shape is invalid")
                    day = _iso_date(raw["date"], "market row date").isoformat()
                    if day not in requested_days or day in rows:
                        raise ValueError("market row date is duplicate or outside required trading days")
                    if (raw["volume_unit"] != "shares" or raw["turnover_unit"] != "CNY"
                            or raw["close_unit"] != "CNY_per_share"):
                        raise ValueError("market normalized units differ from signed contract")
                    if not _visible(raw, _aware(as_of_utc, "market as_of_utc")):
                        pending.add("visibility_unproven")
                        continue
                    rows[day] = {"coverage": "covered", "exchange_allows_trading": raw["exchange_allows_trading"],
                        "volume": raw["volume"], "turnover": raw["turnover"], "close": raw["close"],
                        "observation_hash": observation.observation_hash}
            missing_dates.update(requested_days - set(rows))
        algorithm_rows = {}
        daily_records = []
        for day in days:
            if day in rows and day not in missing_dates:
                algorithm_rows[day] = {key: rows[day][key] for key in
                    ("coverage", "exchange_allows_trading", "volume", "turnover", "close")}
                daily_records.append(dict(date=day, **rows[day]))
            else:
                algorithm_rows[day] = {"coverage": "missing"}
                daily_records.append({"date": day, "coverage": "missing"})
        result = evaluate_window(days, algorithm_rows)
        pending.update(result["pending"])
        lineage = tuple(item.observation_hash for item in observations)
        market_config = _read_binding(owned_binding)["market_config"]
        calendar_config = _read_binding(owned_binding)["calendar_config"]
        wire = {
            "schema_version": "verified-market-window-v1",
            "security_id": security_id,
            "exchange": _read_binding(owned_binding)["exchange"],
            "as_of_utc": as_of_utc,
            "registry_manifest_hash": _read_binding(owned_binding)["registry_manifest_hash"],
            "source_registry_hash": _read_binding(owned_binding)["source_registry_hash"],
            "binding_hash": _read_binding(owned_binding)["binding_hash"],
            "rule_id": _read_binding(owned_binding)["rule_id"],
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
            "observations": [item.to_dict() for item in observations],
            **{key: result[key] for key in ("price_state", "price", "price_date", "stale_days",
                                             "stale_at_least", "veto_state")},
            "pending": sorted(pending),
        }
        def recheck():
            calendar.coverage.require_current()
            _read_binding(owned_binding)
            for item in observations:
                item.require_current()
        window = _mint_market_window(wire, owned_binding, recheck)
        return MarketSelection(window, tuple(sorted(pending)), lineage,
            hashlib.sha256(window.canonical_bytes()).hexdigest(), window.require_current)


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
        return first_calendar
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
    if selection.window.price_state == "incomplete" and len(selection.window.required_trading_days) < 250:
        observations = _calendar_record(calendar.coverage)
        payload = observations.wire
        last = payload["observations"][-1]
        oldest = range_store.read_verified(last["task"]["id"])
        return source.previous_calendar_request(oldest)
    return None


__all__ = [
    "CalendarSelection", "FormalPolicyMarketRepository", "MarketSelection",
    "VerifiedCalendarCoverageV1", "VerifiedMarketWindowV1", "evaluate_window",
    "plan_next_window_request",
]
