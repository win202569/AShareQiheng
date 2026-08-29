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

    @staticmethod
    def _verify(path: Path, digest: str) -> None:
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            verified = FetchBatch(stored["source"], stored["dataset"], stored["request"], stored["records"], stored["fetched_at_utc"], stored["source_version"], stored["metadata"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise OSError(f"invalid snapshot payload: {path}") from error
        if verified.sha256() != digest:
            raise OSError(f"snapshot hash verification failed: {path}")
