"""Verified persistence and point-in-time lookup for formal official evidence."""

from __future__ import annotations

from pathlib import Path

from .formal_repository_identity import _track_repository_constructor

from .formal_evidence import (
    EvidenceVerification,
    OfficialFetch,
    OfficialRequest,
    OfficialSnapshotRef,
)
from .formal_snapshot_store import FormalSnapshotStore, FormalStoredSnapshot
from .state_store import StateStore


_REF_FIELDS = (
    "snapshot_id",
    "source",
    "dataset",
    "request_fingerprint",
    "security_id",
    "period_or_date",
    "exchange",
    "content_sha256",
    "manifest_sha256",
    "content_path",
    "manifest_path",
    "original_url",
    "published_at_utc",
    "published_precision",
    "source_updated_at_utc",
    "captured_at_utc",
    "effective_at_utc",
    "effective_time_evidence_hash",
    "refresh_generation",
    "producing_task_id",
    "parser_id",
    "parser_version",
    "mapping_version",
    "verification_status",
)


class FormalSnapshotRepository:
    """The sole application boundary for verified formal snapshot references."""

    @_track_repository_constructor
    def __init__(self, root: str | Path, state_store: StateStore) -> None:
        if type(state_store) is not StateStore:
            raise ValueError("state_store must have exact type StateStore")
        resolved_root = Path(root).resolve()
        raw_store = state_store._configured_formal_snapshot_store_for_repository()
        if type(raw_store) is not FormalSnapshotStore:
            raise ValueError("configured formal snapshot store is invalid")
        if resolved_root != raw_store.root:
            raise ValueError("formal snapshot repository root must match configured raw store root")
        self.root = resolved_root
        self._state_store = state_store
        self._raw_store = raw_store

    @staticmethod
    def _require_persistence_inputs(
        fetch: object,
        verification: object,
        producing_task_id: object,
        worker_id: object,
    ) -> tuple[OfficialFetch, EvidenceVerification, str | None, str | None]:
        if type(fetch) is not OfficialFetch:
            raise ValueError("fetch must have exact type OfficialFetch")
        if type(verification) is not EvidenceVerification:
            raise ValueError("verification must have exact type EvidenceVerification")
        if type(fetch.request) is not OfficialRequest:
            raise ValueError("fetch request must have exact type OfficialRequest")
        if verification.status != "verified":
            raise ValueError("verification must be verified")
        if verification.content_sha256 != fetch.content_sha256:
            raise ValueError("verification content hash does not match fetch content hash")
        if (producing_task_id is None) != (worker_id is None):
            raise ValueError("producing_task_id and worker_id must be provided together")
        if producing_task_id is not None:
            if (
                type(producing_task_id) is not str
                or not producing_task_id
                or producing_task_id != producing_task_id.strip()
            ):
                raise ValueError("producing_task_id must be an already-trimmed nonempty string")
            if (
                type(worker_id) is not str
                or not worker_id
                or worker_id != worker_id.strip()
            ):
                raise ValueError("worker_id must be an already-trimmed nonempty string")
        return fetch, verification, producing_task_id, worker_id

    def persist_verified(
        self,
        fetch: OfficialFetch,
        verification: EvidenceVerification,
        *,
        producing_task_id: str | None,
        worker_id: str | None,
    ) -> OfficialSnapshotRef:
        fetch, verification, producing_task_id, worker_id = self._require_persistence_inputs(
            fetch, verification, producing_task_id, worker_id
        )
        stored = self._raw_store.write_verified(
            fetch, verification, producing_task_id=producing_task_id
        )
        if producing_task_id is None:
            return self._state_store.put_formal_snapshot(fetch, stored, verification)
        assert worker_id is not None
        return self._state_store.put_formal_snapshot_for_leased_task(
            fetch,
            stored,
            verification,
            task_id=producing_task_id,
            worker_id=worker_id,
        )

    def find_exact_verified(
        self,
        request: OfficialRequest,
        *,
        parser_id: str,
        parser_version: str,
        mapping_version: str,
        content_sha256: str,
        manifest_sha256: str,
    ) -> OfficialSnapshotRef | None:
        return self._state_store._find_formal_snapshot_exact_verified(
            request,
            parser_id=parser_id,
            parser_version=parser_version,
            mapping_version=mapping_version,
            content_sha256=content_sha256,
            manifest_sha256=manifest_sha256,
        )

    def find_visible_verified(
        self,
        request: OfficialRequest,
        *,
        parser_id: str,
        parser_version: str,
        mapping_version: str,
        as_of_utc: str,
    ) -> OfficialSnapshotRef | None:
        return self._state_store._find_formal_snapshot_visible_verified(
            request,
            parser_id=parser_id,
            parser_version=parser_version,
            mapping_version=mapping_version,
            as_of_utc=as_of_utc,
        )

    def get_verified_by_manifest(self, manifest_sha256: str, *, historical_read=None) -> OfficialSnapshotRef:
        ref = self._state_store._get_formal_snapshot_verified_by_manifest(manifest_sha256, historical_read=historical_read)
        if ref is None:
            raise ValueError("verified formal manifest is unknown")
        return ref

    def read_verified_raw(self, ref: OfficialSnapshotRef, *, historical_read=None) -> bytes:
        if type(ref) is not OfficialSnapshotRef:
            raise ValueError("ref must have exact type OfficialSnapshotRef")
        current = self.get_verified_by_manifest(ref.manifest_sha256, historical_read=historical_read)
        if any(getattr(ref, field) != getattr(current, field) for field in _REF_FIELDS):
            raise ValueError("formal snapshot reference does not match verified storage")
        stored = FormalStoredSnapshot(
            content_path=current.content_path,
            manifest_path=current.manifest_path,
            content_sha256=current.content_sha256,
            manifest_sha256=current.manifest_sha256,
        )
        return self._raw_store.read_verified_raw(stored, historical_read=historical_read)


__all__ = ["FormalSnapshotRepository"]
