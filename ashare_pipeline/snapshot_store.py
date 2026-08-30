"""Content-addressed, atomically written raw fetch snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .sources import FetchBatch


class SnapshotStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def write(self, batch: FetchBatch) -> tuple[Path, str, bool]:
        digest = batch.sha256()
        day = datetime.fromisoformat(batch.fetched_at_utc.replace("Z", "+00:00")).date().isoformat()
        target = self.root / "raw" / batch.source / batch.dataset / day / f"{digest}.json"
        payload = {"schema_version": 1, "source": batch.source, "dataset": batch.dataset, "request": batch.request,
                   "records": batch.records, "fetched_at_utc": batch.fetched_at_utc, "source_version": batch.source_version,
                   "metadata": batch.metadata}
        existing = self._find_existing(batch.source, batch.dataset, digest)
        if existing is not None:
            self._verify(existing, digest)
            return existing, digest, False
        target.parent.mkdir(parents=True, exist_ok=True)
        part_path: Path | None = None
        try:
            descriptor, part_name = tempfile.mkstemp(prefix=f".{digest}.", suffix=".part", dir=target.parent)
            part_path = Path(part_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            self._verify(part_path, digest)
            existing = self._find_existing(batch.source, batch.dataset, digest)
            if existing is not None:
                self._verify(existing, digest)
                part_path.unlink()
                part_path = None
                return existing, digest, False
            os.replace(part_path, target)
            part_path = None
            try:
                self._verify(target, digest)
            except OSError:
                target.unlink(missing_ok=True)
                raise
            return target, digest, True
        except BaseException:
            if part_path is not None:
                part_path.unlink(missing_ok=True)
            raise

    def _find_existing(self, source: str, dataset: str, digest: str) -> Path | None:
        directory = self.root / "raw" / source / dataset
        if not directory.exists():
            return None
        matches = sorted(directory.glob(f"*/{digest}.json"))
        return matches[0] if matches else None

    def read_verified(self, path: str | Path, digest: str) -> FetchBatch:
        """Return a stored batch only after its content hash has been verified."""
        candidate = Path(path)
        self._verify(candidate, digest)
        try:
            return self._batch_from_payload(
                json.loads(candidate.read_text(encoding="utf-8"))
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise OSError(f"invalid snapshot payload: {candidate}") from error

    @staticmethod
    def _verify(path: Path, digest: str) -> None:
        try:
            verified = SnapshotStore._batch_from_payload(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise OSError(f"invalid snapshot payload: {path}") from error
        if verified.sha256() != digest:
            raise OSError(f"snapshot hash verification failed: {path}")

    @staticmethod
    def _batch_from_payload(stored: object) -> FetchBatch:
        if not isinstance(stored, dict) or stored.get("schema_version") != 1:
            raise ValueError("unsupported snapshot payload")
        required_strings = ("source", "dataset", "fetched_at_utc", "source_version")
        if any(not isinstance(stored.get(key), str) for key in required_strings):
            raise ValueError("snapshot payload has invalid scalar fields")
        if not isinstance(stored.get("request"), dict):
            raise ValueError("snapshot request must be an object")
        if not isinstance(stored.get("records"), list):
            raise ValueError("snapshot records must be a list")
        if not isinstance(stored.get("metadata"), dict):
            raise ValueError("snapshot metadata must be an object")
        return FetchBatch(
            stored["source"],
            stored["dataset"],
            stored["request"],
            stored["records"],
            stored["fetched_at_utc"],
            stored["source_version"],
            stored["metadata"],
        )
