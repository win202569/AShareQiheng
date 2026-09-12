"""Pure sealed identity for Formal V3 range requests.

This module depends only on the pure range format and the standard library so
source and contract modules can both capture its authority without import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import weakref

from .formal_range_format import _canonical


_HASH = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = (
    "schema_version", "kind", "source", "dataset", "security_id", "exchange",
    "as_of_utc", "start_date", "end_date", "anchor_descriptor_id",
    "calendar_descriptor_id", "range_config_id", "registry_manifest_hash",
    "page_index", "calendar_coverage_hash",
)


def _build_authority():
    @dataclass(frozen=True)
    class _Record:
        reference: weakref.ReferenceType[object]
        wire: dict[str, object]
        fingerprint: str
        config_wire: dict[str, object]
        source_registry_hash: str
        root_guard: object

    records: dict[int, _Record] = {}

    @dataclass(frozen=True, init=False)
    class FormalRangeRequestV1:
        schema_version: str
        kind: str
        source: str
        dataset: str
        security_id: str | None
        exchange: str
        as_of_utc: str
        start_date: str
        end_date: str
        anchor_descriptor_id: str
        calendar_descriptor_id: str
        range_config_id: str
        registry_manifest_hash: str
        page_index: int
        calendar_coverage_hash: str | None

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("FormalRangeRequestV1 cannot be externally constructed")

        def to_dict(self) -> dict[str, object]:
            return dict(_record(self).wire)

        @property
        def request_fingerprint(self) -> str:
            return _record(self).fingerprint

        def __copy__(self):
            raise TypeError("formal range requests cannot be copied")

        def __deepcopy__(self, _memo):
            raise TypeError("formal range requests cannot be copied")

    def _record(request: object) -> _Record:
        record = records.get(id(request))
        if type(request) is not FormalRangeRequestV1 or record is None or record.reference() is not request:
            raise ValueError("formal range request is forged, copied, or unregistered")
        current = {field: object.__getattribute__(request, field) for field in _FIELDS}
        if current != record.wire or hashlib.sha256(_canonical(current)).hexdigest() != record.fingerprint:
            raise ValueError("formal range request fields changed")
        guard = record.root_guard
        if not callable(guard) or guard() is not True:
            raise ValueError("formal range request root is no longer current")
        return record

    def mint(wire: dict[str, object], config_wire: dict[str, object], *,
             source_registry_hash: str, root_guard):
        if type(wire) is not dict or set(wire) != set(_FIELDS):
            raise ValueError("range request has unknown or missing fields")
        if wire["schema_version"] != "formal-range-request-v1":
            raise ValueError("range request schema_version is invalid")
        if wire["kind"] != "calendar_range" or wire["security_id"] is not None:
            raise ValueError("R2 can mint only calendar range requests")
        if wire["calendar_coverage_hash"] is not None or wire["page_index"] != 1:
            raise ValueError("first calendar request identity is invalid")
        for field in ("anchor_descriptor_id", "calendar_descriptor_id", "range_config_id",
                      "registry_manifest_hash"):
            if type(wire[field]) is not str or _HASH.fullmatch(wire[field]) is None:
                raise ValueError(f"range request {field} is invalid")
        if type(source_registry_hash) is not str or _HASH.fullmatch(source_registry_hash) is None:
            raise ValueError("range request private source_registry_hash is invalid")
        expected = {
            "kind": config_wire.get("kind"), "source": config_wire.get("source"),
            "dataset": config_wire.get("dataset"), "exchange": config_wire.get("exchange_scope"),
            "anchor_descriptor_id": config_wire.get("anchor_descriptor_id"),
            "calendar_descriptor_id": config_wire.get("calendar_descriptor_id"),
        }
        if any(type(wire[key]) is not type(value) or wire[key] != value
               for key, value in expected.items()):
            raise ValueError("range request differs from its sealed config")
        if not callable(root_guard) or root_guard() is not True:
            raise ValueError("range request requires a current root guard")
        request = object.__new__(FormalRangeRequestV1)
        for field in _FIELDS:
            object.__setattr__(request, field, wire[field])
        identity = id(request)
        def forget(reference, *, identity=identity):
            existing = records.get(identity)
            if existing is not None and existing.reference is reference:
                records.pop(identity, None)
        fingerprint = hashlib.sha256(_canonical(wire)).hexdigest()
        records[identity] = _Record(
            weakref.ref(request, forget), dict(wire), fingerprint, dict(config_wire),
            source_registry_hash, root_guard
        )
        return request

    def snapshot(request: object) -> tuple[dict[str, object], dict[str, object], str]:
        record = _record(request)
        return dict(record.wire), dict(record.config_wire), record.source_registry_hash

    return FormalRangeRequestV1, mint, snapshot


FormalRangeRequestV1, _mint_range_request, _trusted_range_request_snapshot = _build_authority()
del _build_authority


__all__ = ["FormalRangeRequestV1"]
