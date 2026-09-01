"""Exact, verified access to persisted source snapshots."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Mapping

from .feature_contract import canonical_sha256, require_aware_utc
from .snapshot_store import SnapshotStore
from .sources import FetchBatch
from .state_store import StateStore, _utc_now


@dataclass(frozen=True)
class SnapshotRef:
    id: str
    source: str
    dataset: str
    request_fingerprint: str
    payload_hash: str
    payload_path: str
    row_count: int
    fetched_at: str
    created_at: str
    request: Mapping[str, object] | None = field(
        default=None, compare=False, repr=False
    )


@dataclass(frozen=True)
class VerifiedSnapshot:
    ref: SnapshotRef
    batch: FetchBatch


class SnapshotRepository:
    def __init__(
        self,
        data_root: str | Path,
        state_store: StateStore,
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self.data_root = Path(data_root).resolve()
        self.project_root = self.data_root.parent
        self.state_store = state_store
        self.snapshot_store = snapshot_store or SnapshotStore(self.data_root)
        if self.snapshot_store.root.resolve() != self.data_root:
            raise ValueError("snapshot store root must match repository data root")

    def persist(
        self,
        batch: FetchBatch,
        *,
        job_id: str | None = None,
        worker_id: str | None = None,
    ) -> tuple[SnapshotRef, bool]:
        if (job_id is None) != (worker_id is None):
            raise ValueError("job_id and worker_id must be provided together")
        if job_id is not None and worker_id is not None:
            return self._persist_owned(batch, job_id, worker_id)
        request_fingerprint = canonical_sha256(batch.request)
        target, digest, _ = self.snapshot_store.write(batch)
        winner = self.snapshot_store.read_verified(target, digest)
        winner_fingerprint = canonical_sha256(winner.request)
        if (
            winner.canonical_bytes() != batch.canonical_bytes()
            or winner_fingerprint != request_fingerprint
        ):
            raise OSError("published snapshot does not match the requested content")
        fetched_at = require_aware_utc(winner.fetched_at_utc, "snapshot fetched_at")
        relative_path = self._project_relative_data_path(target)
        snapshot_id, created = self.state_store.record_snapshot(
            winner.source,
            winner.dataset,
            winner_fingerprint,
            digest,
            relative_path,
            len(winner.records),
            fetched_at,
        )
        snapshot = self.get(snapshot_id)
        if snapshot is None:
            raise RuntimeError("recorded snapshot could not be retrieved")
        return replace(
            snapshot,
            request=MappingProxyType(dict(winner.request)),
        ), created

    def _persist_owned(
        self, batch: FetchBatch, job_id: str, worker_id: str
    ) -> tuple[SnapshotRef, bool]:
        request_fingerprint = canonical_sha256(batch.request)
        target: Path | None = None
        file_created = False
        with self.state_store._transaction(immediate=True) as connection:
            self.state_store._require_unexpired_job_owner(
                connection, job_id, worker_id, _utc_now()
            )
            try:
                target, digest, file_created = self.snapshot_store.write(batch)
                winner = self.snapshot_store.read_verified(target, digest)
                winner_fingerprint = canonical_sha256(winner.request)
                if (
                    winner.canonical_bytes() != batch.canonical_bytes()
                    or winner_fingerprint != request_fingerprint
                ):
                    raise OSError(
                        "published snapshot does not match the requested content"
                    )
                fetched_at = require_aware_utc(
                    winner.fetched_at_utc, "snapshot fetched_at"
                )
                relative_path = self._project_relative_data_path(target)
                snapshot_id, created = self.state_store.record_snapshot(
                    winner.source,
                    winner.dataset,
                    winner_fingerprint,
                    digest,
                    relative_path,
                    len(winner.records),
                    fetched_at,
                    _connection=connection,
                )
                row = connection.execute(
                    """SELECT id, source, dataset, request_fingerprint, payload_hash,
                              payload_path, row_count, fetched_at, created_at
                       FROM source_snapshot WHERE id = ?""",
                    (snapshot_id,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("recorded snapshot could not be retrieved")
                self.state_store._require_unexpired_job_owner(
                    connection, job_id, worker_id, _utc_now()
                )
                snapshot = self._ref_from_row(row)
            except BaseException:
                if file_created and target is not None:
                    try:
                        target.unlink()
                    except FileNotFoundError:
                        pass
                raise
        return replace(
            snapshot,
            request=MappingProxyType(dict(winner.request)),
        ), created

    def find_exact(
        self, source: str, dataset: str, request: dict
    ) -> SnapshotRef | None:
        fingerprint = canonical_sha256(request)
        with closing(self.state_store._connect()) as connection:
            row = connection.execute(
                """SELECT id, source, dataset, request_fingerprint, payload_hash,
                          payload_path, row_count, fetched_at, created_at
                   FROM source_snapshot
                   WHERE source = ? AND dataset = ? AND request_fingerprint = ?
                   ORDER BY fetched_at DESC, created_at DESC, payload_hash DESC
                   LIMIT 1""",
                (source, dataset, fingerprint),
            ).fetchone()
        if row is None:
            return None
        return replace(
            self._ref_from_row(row),
            request=MappingProxyType(dict(request)),
        )

    def get(self, snapshot_id: str) -> SnapshotRef | None:
        with closing(self.state_store._connect()) as connection:
            row = connection.execute(
                """SELECT id, source, dataset, request_fingerprint, payload_hash,
                          payload_path, row_count, fetched_at, created_at
                   FROM source_snapshot WHERE id = ?""",
                (snapshot_id,),
            ).fetchone()
        return self._ref_from_row(row) if row is not None else None

    def read_verified(self, snapshot: SnapshotRef) -> VerifiedSnapshot:
        path = self._resolve_payload_path(snapshot.payload_path)
        batch = self.snapshot_store.read_verified(path, snapshot.payload_hash)
        try:
            fetched_at_matches = (
                require_aware_utc(batch.fetched_at_utc, "payload fetched_at")
                == require_aware_utc(snapshot.fetched_at, "snapshot fetched_at")
            )
        except ValueError as error:
            raise OSError("snapshot database metadata does not match verified payload") from error
        if (
            batch.source != snapshot.source
            or batch.dataset != snapshot.dataset
            or canonical_sha256(batch.request) != snapshot.request_fingerprint
            or len(batch.records) != snapshot.row_count
            or not fetched_at_matches
        ):
            raise OSError("snapshot database metadata does not match verified payload")
        return VerifiedSnapshot(snapshot, batch)

    def _project_relative_data_path(self, target: Path) -> str:
        try:
            relative_path = target.resolve().relative_to(self.project_root.resolve()).as_posix()
        except ValueError as error:
            raise ValueError("snapshot path must stay inside the project data directory") from error
        if not relative_path.startswith("data/"):
            raise ValueError("snapshot path must stay inside the project data directory")
        return relative_path

    def _resolve_payload_path(self, payload_path: str) -> Path:
        if not isinstance(payload_path, str) or not payload_path:
            raise ValueError("snapshot payload path is required")
        posix_path = PurePosixPath(payload_path)
        if Path(payload_path).is_absolute() or PureWindowsPath(payload_path).is_absolute() or posix_path.is_absolute():
            resolved = Path(payload_path).resolve()
            try:
                resolved.relative_to(self.data_root.resolve())
            except (OSError, ValueError) as error:
                raise ValueError(
                    "absolute legacy snapshot path must stay inside repository data root"
                ) from error
            return resolved
        if "\\" in payload_path:
            raise ValueError("relative snapshot path must not contain a backslash")
        posix_parts = posix_path.parts
        if ".." in posix_parts:
            raise ValueError("relative snapshot paths cannot include parent traversal")
        if not posix_parts or posix_parts[0] != "data":
            raise ValueError("relative snapshot path must stay inside the project data directory")
        resolved = self.project_root.joinpath(*posix_parts).resolve()
        try:
            resolved.relative_to(self.data_root)
        except ValueError as error:
            raise ValueError(
                "relative snapshot path must stay inside the project data directory"
            ) from error
        return resolved

    @staticmethod
    def _ref_from_row(row: object) -> SnapshotRef:
        return SnapshotRef(
            str(row["id"]),
            str(row["source"]),
            str(row["dataset"]),
            str(row["request_fingerprint"]),
            str(row["payload_hash"]),
            str(row["payload_path"]),
            int(row["row_count"]),
            str(row["fetched_at"]),
            str(row["created_at"]),
        )
