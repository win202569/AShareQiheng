"""Pure, fail-closed construction of the formal full-market universe."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

from ashare_pipeline.formal_evidence import OfficialSnapshotRef
from ashare_pipeline.formal_time import FORMAL_FREEZE_AT_CN, is_visible_at


Exchange = Literal["SH", "SZ", "BJ"]
UniverseStatus = Literal["out_of_scope", "pending_evidence", "pool_vetoed", "formal_scored"]
_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_OFFICIAL_LISTING_DATASETS = frozenset({"official_security_listing"})
_SECURITY_ID = re.compile(r"^(?:SH|SZ|BJ)[0-9]{6}$")
_SECURITY_TYPES = frozenset({
    "ordinary_a", "b_share", "fund", "etf", "bond", "convertible",
    "convertible_bond", "reit", "preferred_stock", "depositary_receipt",
})
_LISTING_STATUSES = frozenset({"listed", "suspended", "delisted"})


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            _plain_json(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("formal universe value must be canonical JSON") from exc


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("formal universe JSON object keys must be strings")
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _json_copy(value: object) -> object:
    return json.loads(_canonical_json_bytes(value).decode("utf-8"))


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be non-empty")
    return value


def canonical_security_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("formal security id must be SH/SZ/BJ plus six digits")
    normalized = value.strip().upper()
    if _SECURITY_ID.fullmatch(normalized) is None:
        raise ValueError("formal security id must be SH/SZ/BJ plus six digits")
    return normalized


@dataclass(frozen=True)
class FormalUniverseMember:
    security_id: str
    exchange: Exchange
    security_type: str
    listing_status: str
    raw_row: Mapping[str, object]
    raw_row_hash: str

    def __post_init__(self) -> None:
        copied = _json_copy(self.raw_row)
        assert isinstance(copied, dict)
        security_id = canonical_security_id(self.security_id)
        if security_id != self.security_id or self.exchange not in _EXCHANGES or security_id[:2] != self.exchange:
            raise ValueError("formal universe member identity must be canonical and match exchange")
        if self.security_type != "ordinary_a":
            raise ValueError("formal universe member security_type must be ordinary_a")
        if self.listing_status not in _LISTING_STATUSES:
            raise ValueError("formal universe member listing_status is unknown")
        if (
            copied.get("security_id") != self.security_id
            or copied.get("security_type") != self.security_type
            or copied.get("listing_status") != self.listing_status
        ):
            raise ValueError("formal universe member raw row identity mismatch")
        if _canonical_sha256(copied) != self.raw_row_hash:
            raise ValueError("formal universe member raw_row_hash mismatch")
        object.__setattr__(self, "raw_row", _freeze_json(copied))


@dataclass(frozen=True)
class FormalUniverseDecision:
    security_id: str
    status: UniverseStatus
    reasons: tuple[str, ...]
    veto_flags: tuple[str, ...]
    evidence_hash: str


@dataclass(frozen=True)
class FormalUniverseSourceAudit:
    exchange: Exchange
    source_content_sha256: str
    parser_id: str
    parser_version: str
    source_row_count: int
    accepted_ordinary_a_count: int
    excluded_by_security_type: tuple[tuple[str, int], ...]
    parsed_rows_hash: str
    accepted_members_hash: str
    excluded_rows_hash: str
    audit_hash: str


@dataclass(frozen=True)
class FormalUniverseExtraction:
    exchange: Exchange
    members: tuple[FormalUniverseMember, ...]
    audit: FormalUniverseSourceAudit


@dataclass(frozen=True)
class FormalUniverseSourceEvidence:
    exchange: Exchange
    snapshot: OfficialSnapshotRef
    extraction: FormalUniverseExtraction


@dataclass(frozen=True)
class FormalUniverseSourceDocument:
    exchange: Exchange
    snapshot: OfficialSnapshotRef
    parser_id: str
    parser_version: str
    parsed_rows: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class FormalFrozenUniverseInput:
    as_of_utc: str
    registry_manifest_hash: str
    members: tuple[FormalUniverseMember, ...]
    sources: tuple[FormalUniverseSourceEvidence, ...]
    universe_hash: str
    source_audit_hash: str
    frozen_input_hash: str

    def __post_init__(self) -> None:
        _validate_frozen_universe_input(self)


def classify_universe_status(
    *, in_scope: bool, evidence_complete: bool, veto_flags: tuple[str, ...]
) -> UniverseStatus:
    if not in_scope:
        return "out_of_scope"
    if not evidence_complete:
        return "pending_evidence"
    if veto_flags:
        return "pool_vetoed"
    return "formal_scored"


def _member_payload(member: FormalUniverseMember) -> dict[str, object]:
    return {
        "exchange": member.exchange,
        "listing_status": member.listing_status,
        "raw_row": member.raw_row,
        "raw_row_hash": member.raw_row_hash,
        "security_id": member.security_id,
        "security_type": member.security_type,
    }


def extract_formal_universe_members(
    document: FormalUniverseSourceDocument,
) -> FormalUniverseExtraction:
    if not isinstance(document, FormalUniverseSourceDocument):
        raise ValueError("formal listing document is malformed")
    if document.exchange not in _EXCHANGES:
        raise ValueError("formal listing document exchange must be SH/SZ/BJ")
    if not isinstance(document.snapshot, OfficialSnapshotRef):
        raise ValueError("formal listing document snapshot is malformed")
    if document.snapshot.exchange != document.exchange:
        raise ValueError("formal listing document snapshot exchange must match document exchange")
    parser_id = _nonempty_text(document.parser_id, "parser_id")
    parser_version = _nonempty_text(document.parser_version, "parser_version")
    if parser_id != document.snapshot.parser_id or parser_version != document.snapshot.parser_version:
        raise ValueError("formal listing document parser must match snapshot parser")
    if not isinstance(document.parsed_rows, tuple):
        raise ValueError("parsed_rows must be a tuple of mappings")

    accepted: list[FormalUniverseMember] = []
    excluded: list[dict[str, str]] = []
    row_hashes: list[str] = []
    excluded_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for raw_row in document.parsed_rows:
        if not isinstance(raw_row, Mapping) or any(not isinstance(key, str) for key in raw_row):
            raise ValueError("formal listing row must be a JSON object with string keys")
        copied = _json_copy(raw_row)
        assert isinstance(copied, dict)
        row_hash = _canonical_sha256(copied)
        row_hashes.append(row_hash)
        security_id = canonical_security_id(copied.get("security_id"))
        if security_id[:2] != document.exchange:
            raise ValueError("security_id exchange does not match document exchange")
        if security_id in seen_ids:
            raise ValueError(f"duplicate security_id: {security_id}")
        seen_ids.add(security_id)
        security_type = copied.get("security_type")
        if not isinstance(security_type, str) or security_type not in _SECURITY_TYPES:
            raise ValueError("unknown security_type in formal listing row")
        listing_status = copied.get("listing_status")
        if not isinstance(listing_status, str) or listing_status not in _LISTING_STATUSES:
            raise ValueError("unknown or missing listing_status in formal listing row")
        if security_type != "ordinary_a":
            excluded_counts[security_type] += 1
            excluded.append({"row_hash": row_hash, "security_type": security_type})
            continue
        accepted.append(FormalUniverseMember(
            security_id=security_id,
            exchange=document.exchange,
            security_type=security_type,
            listing_status=listing_status,
            raw_row=copied,
            raw_row_hash=row_hash,
        ))
    if not accepted:
        raise ValueError("formal listing extraction has zero ordinary-A members")

    members = tuple(sorted(accepted, key=lambda member: member.security_id))
    excluded_by_type = tuple(sorted(excluded_counts.items()))
    audit_fields = {
        "accepted_members_hash": _canonical_sha256([_member_payload(member) for member in members]),
        "accepted_ordinary_a_count": len(members),
        "exchange": document.exchange,
        "excluded_by_security_type": excluded_by_type,
        "excluded_rows_hash": _canonical_sha256(sorted(excluded, key=lambda row: (row["security_type"], row["row_hash"]))),
        "parsed_rows_hash": _canonical_sha256(sorted(row_hashes)),
        "parser_id": parser_id,
        "parser_version": parser_version,
        "source_content_sha256": document.snapshot.content_sha256,
        "source_row_count": len(document.parsed_rows),
    }
    audit = FormalUniverseSourceAudit(**audit_fields, audit_hash=_canonical_sha256(audit_fields))
    return FormalUniverseExtraction(document.exchange, members, audit)


def build_universe_snapshot(
    extractions: Sequence[FormalUniverseExtraction],
) -> tuple[tuple[FormalUniverseMember, ...], str]:
    materialized = tuple(extractions)
    if len(materialized) != 3 or {item.exchange for item in materialized if isinstance(item, FormalUniverseExtraction)} != _EXCHANGES:
        raise ValueError("formal universe requires one nonempty extraction for each SH/SZ/BJ exchange")
    if any(not isinstance(item, FormalUniverseExtraction) or not item.members for item in materialized):
        raise ValueError("formal universe requires nonempty verified extractions")
    members = tuple(sorted((member for item in materialized for member in item.members), key=lambda member: member.security_id))
    identifiers = [member.security_id for member in members]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("formal universe contains duplicate security_id across exchanges")
    audit_hashes = [{"exchange": item.exchange, "audit_hash": item.audit.audit_hash} for item in sorted(materialized, key=lambda item: item.exchange)]
    universe_hash = _canonical_sha256({
        "members": [_member_payload(member) for member in members],
        "source_audits": audit_hashes,
    })
    return members, universe_hash


def _audit_fields(audit: FormalUniverseSourceAudit) -> dict[str, object]:
    return {
        "accepted_members_hash": audit.accepted_members_hash,
        "accepted_ordinary_a_count": audit.accepted_ordinary_a_count,
        "exchange": audit.exchange,
        "excluded_by_security_type": audit.excluded_by_security_type,
        "excluded_rows_hash": audit.excluded_rows_hash,
        "parsed_rows_hash": audit.parsed_rows_hash,
        "parser_id": audit.parser_id,
        "parser_version": audit.parser_version,
        "source_content_sha256": audit.source_content_sha256,
        "source_row_count": audit.source_row_count,
    }


def _validate_source_evidence(
    source: FormalUniverseSourceEvidence, as_of_utc: str
) -> None:
    if not isinstance(source, FormalUniverseSourceEvidence):
        raise ValueError("formal frozen universe requires three verified SH/SZ/BJ sources")
    snapshot = source.snapshot
    extraction = source.extraction
    if not isinstance(extraction, FormalUniverseExtraction):
        raise ValueError("formal frozen universe source extraction is malformed")
    if not isinstance(snapshot, OfficialSnapshotRef) or snapshot.verification_status != "verified":
        raise ValueError("formal frozen universe source must be verified")
    if snapshot.dataset not in _OFFICIAL_LISTING_DATASETS:
        raise ValueError("formal frozen universe source must use an official listing dataset")
    if snapshot.security_id is not None:
        raise ValueError("formal frozen universe source must be global")
    if source.exchange != snapshot.exchange or source.exchange != extraction.exchange:
        raise ValueError("formal frozen universe source exchange mismatch")
    if not is_visible_at(snapshot.published_at_utc, as_of_utc) or not is_visible_at(snapshot.effective_at_utc, as_of_utc):
        raise ValueError("formal frozen universe source must be visible at the freeze")
    audit = extraction.audit
    if not isinstance(audit, FormalUniverseSourceAudit):
        raise ValueError("formal frozen universe source audit is malformed")
    if audit.exchange != source.exchange:
        raise ValueError("formal frozen universe source audit exchange mismatch")
    if audit.source_content_sha256 != snapshot.content_sha256:
        raise ValueError("formal frozen universe source content hash mismatch")
    if audit.parser_id != snapshot.parser_id or audit.parser_version != snapshot.parser_version:
        raise ValueError("formal frozen universe source parser mismatch")
    if not extraction.members or tuple(sorted(extraction.members, key=lambda member: member.security_id)) != extraction.members:
        raise ValueError("formal frozen universe extraction must be nonempty and sorted")
    if any(member.exchange != source.exchange for member in extraction.members):
        raise ValueError("formal frozen universe extraction member exchange mismatch")
    if audit.accepted_ordinary_a_count != len(extraction.members):
        raise ValueError("formal frozen universe accepted member count mismatch")
    excluded_count = sum(count for _, count in audit.excluded_by_security_type)
    if any(count <= 0 for _, count in audit.excluded_by_security_type) or audit.source_row_count != len(extraction.members) + excluded_count:
        raise ValueError("formal frozen universe source row count mismatch")
    if audit.accepted_members_hash != _canonical_sha256([_member_payload(member) for member in extraction.members]):
        raise ValueError("formal frozen universe accepted_members_hash mismatch")
    if audit.audit_hash != _canonical_sha256(_audit_fields(audit)):
        raise ValueError("formal frozen universe audit_hash mismatch")


def _source_manifest(sources: Sequence[FormalUniverseSourceEvidence]) -> list[dict[str, str]]:
    return [{
        "audit_hash": source.extraction.audit.audit_hash,
        "content_sha256": source.snapshot.content_sha256,
        "exchange": source.exchange,
        "manifest_sha256": source.snapshot.manifest_sha256,
        "parser_id": source.snapshot.parser_id,
        "parser_version": source.snapshot.parser_version,
    } for source in sources]


def _frozen_input_hash(
    as_of_utc: str,
    registry_manifest_hash: str,
    universe_hash: str,
    source_manifest: Sequence[Mapping[str, str]],
) -> str:
    return _canonical_sha256({
        "as_of_utc": as_of_utc,
        "registry_manifest_hash": registry_manifest_hash,
        "sources": [{
            "audit_hash": item["audit_hash"],
            "exchange": item["exchange"],
            "manifest_sha256": item["manifest_sha256"],
        } for item in source_manifest],
        "universe_hash": universe_hash,
    })


def _validate_frozen_universe_input(frozen: FormalFrozenUniverseInput) -> None:
    if frozen.as_of_utc != FORMAL_FREEZE_AT_CN:
        raise ValueError(f"formal universe freeze must be exactly {FORMAL_FREEZE_AT_CN}")
    _nonempty_text(frozen.registry_manifest_hash, "registry_manifest_hash")
    if not isinstance(frozen.sources, tuple) or len(frozen.sources) != 3:
        raise ValueError("formal frozen universe requires three verified SH/SZ/BJ sources")
    if {source.exchange for source in frozen.sources if isinstance(source, FormalUniverseSourceEvidence)} != _EXCHANGES:
        raise ValueError("formal frozen universe requires three verified SH/SZ/BJ sources")
    if tuple(sorted(frozen.sources, key=lambda source: source.exchange)) != frozen.sources:
        raise ValueError("formal frozen universe sources must be sorted by exchange")
    for source in frozen.sources:
        _validate_source_evidence(source, frozen.as_of_utc)
    expected_members, expected_universe_hash = build_universe_snapshot(
        tuple(source.extraction for source in frozen.sources)
    )
    if not isinstance(frozen.members, tuple) or frozen.members != expected_members:
        raise ValueError("formal frozen universe members must exactly match its source extractions")
    if frozen.universe_hash != expected_universe_hash:
        raise ValueError("formal frozen universe universe_hash mismatch")
    manifest = _source_manifest(frozen.sources)
    if frozen.source_audit_hash != _canonical_sha256(manifest):
        raise ValueError("formal frozen universe source_audit_hash mismatch")
    expected_frozen_hash = _frozen_input_hash(
        frozen.as_of_utc,
        frozen.registry_manifest_hash,
        frozen.universe_hash,
        manifest,
    )
    if frozen.frozen_input_hash != expected_frozen_hash:
        raise ValueError("formal frozen universe frozen_input_hash mismatch")


class FormalUniverseIngestor:
    def build(
        self,
        as_of_utc: str,
        registry_manifest_hash: str,
        documents: Sequence[FormalUniverseSourceDocument],
    ) -> FormalFrozenUniverseInput:
        if as_of_utc != FORMAL_FREEZE_AT_CN:
            raise ValueError(f"formal universe freeze must be exactly {FORMAL_FREEZE_AT_CN}")
        _nonempty_text(registry_manifest_hash, "registry_manifest_hash")
        materialized = tuple(documents)
        if len(materialized) != 3 or {document.exchange for document in materialized if isinstance(document, FormalUniverseSourceDocument)} != _EXCHANGES:
            raise ValueError("formal universe ingress requires exactly one SH/SZ/BJ document")

        sources: list[FormalUniverseSourceEvidence] = []
        for document in sorted(materialized, key=lambda item: item.exchange):
            snapshot = document.snapshot
            if not isinstance(snapshot, OfficialSnapshotRef) or snapshot.verification_status != "verified":
                raise ValueError("formal universe source must be a verified OfficialSnapshotRef")
            if snapshot.security_id is not None:
                raise ValueError("formal universe source snapshot must be global")
            if snapshot.exchange != document.exchange:
                raise ValueError("formal universe source must be exchange-scoped to its document")
            if document.parser_id != snapshot.parser_id or document.parser_version != snapshot.parser_version:
                raise ValueError("formal universe document parser must match its verified snapshot")
            if not is_visible_at(snapshot.published_at_utc, as_of_utc) or not is_visible_at(snapshot.effective_at_utc, as_of_utc):
                raise ValueError("formal universe source snapshot must be visible at the freeze")
            extraction = extract_formal_universe_members(document)
            sources.append(FormalUniverseSourceEvidence(document.exchange, snapshot, extraction))

        members, universe_hash = build_universe_snapshot(tuple(source.extraction for source in sources))
        source_manifest = _source_manifest(sources)
        source_audit_hash = _canonical_sha256(source_manifest)
        frozen_input_hash = _frozen_input_hash(
            as_of_utc, registry_manifest_hash, universe_hash, source_manifest
        )
        return FormalFrozenUniverseInput(
            as_of_utc=as_of_utc,
            registry_manifest_hash=registry_manifest_hash,
            members=members,
            sources=tuple(sources),
            universe_hash=universe_hash,
            source_audit_hash=source_audit_hash,
            frozen_input_hash=frozen_input_hash,
        )


__all__ = [
    "FormalFrozenUniverseInput", "FormalUniverseDecision", "FormalUniverseExtraction",
    "FormalUniverseIngestor", "FormalUniverseMember", "FormalUniverseSourceAudit",
    "FormalUniverseSourceDocument", "FormalUniverseSourceEvidence", "build_universe_snapshot",
    "canonical_security_id", "classify_universe_status", "extract_formal_universe_members",
]
