"""Byte-preserving, content-addressed storage for verified formal evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import tempfile
from typing import Callable

from .formal_evidence import EvidenceVerification, OfficialFetch, OfficialRequest


@dataclass(frozen=True)
class FormalStoredSnapshot:
    """Paths and immutable identifiers for one verified formal snapshot."""

    content_path: str
    manifest_path: str
    content_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class ValidatedFormalSnapshot:
    """Canonical manifest metadata safe for persistence after strict raw inspection."""

    source: str
    dataset: str
    request_json: str
    request_fingerprint: str
    security_id: str | None
    period_or_date: str | None
    exchange: str | None
    content_sha256: str
    manifest_sha256: str
    content_path: str
    manifest_path: str
    original_url: str
    published_at_utc: str
    published_precision: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    effective_at_utc: str
    effective_time_evidence_hash: str | None
    refresh_generation: str
    producing_task_id: str | None
    parser_id: str
    parser_version: str
    mapping_version: str
    verification_json: str


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class _DuplicateManifestKeyError(ValueError):
    pass


def _unique_manifest_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateManifestKeyError(key)
        result[key] = value
    return result


class FormalSnapshotStore:
    """Persist verified official fetches without decoding or re-encoding their bytes."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def write_verified(
        self,
        fetch: OfficialFetch,
        verification: EvidenceVerification,
        *,
        producing_task_id: str | None,
    ) -> FormalStoredSnapshot:
        """Atomically write one verified raw payload and its immutable lineage manifest."""
        self._validate_write_inputs(fetch, verification, producing_task_id)
        assert isinstance(fetch.request, OfficialRequest)
        source = self._safe_path_component(fetch.request.source, "source")
        dataset = self._safe_path_component(fetch.request.dataset, "dataset")
        content_sha256 = fetch.content_sha256
        directory = self.root / "data" / "raw" / "formal" / source / dataset
        self._require_target_within_root(directory)

        content_path = directory / f"{content_sha256}.bin"
        self._write_content(content_path, fetch.raw_bytes, content_sha256)

        payload = self._manifest_payload(fetch, verification, producing_task_id, content_sha256)
        manifest_sha256 = _sha256_bytes(_canonical_json_bytes(payload))
        envelope = {**payload, "manifest_sha256": manifest_sha256}
        manifest_path = directory / f"{manifest_sha256}.manifest.json"
        self._write_manifest(manifest_path, envelope, manifest_sha256)

        return FormalStoredSnapshot(
            content_path=str(content_path),
            manifest_path=str(manifest_path),
            content_sha256=content_sha256,
            manifest_sha256=manifest_sha256,
        )

    def read_verified_raw(self, stored: FormalStoredSnapshot) -> bytes:
        """Return raw bytes only after validating selected content and lineage files."""
        if not isinstance(stored, FormalStoredSnapshot):
            raise ValueError("stored snapshot must be a FormalStoredSnapshot")
        self._require_sha256(stored.content_sha256, "content hash")
        self._require_sha256(stored.manifest_sha256, "manifest hash")

        manifest_path = self._path_inside_root(stored.manifest_path)
        content_path = self._path_inside_root(stored.content_path)
        if manifest_path.name != f"{stored.manifest_sha256}.manifest.json":
            raise ValueError("manifest hash does not match manifest path")

        envelope = self._read_manifest(manifest_path, stored.manifest_sha256)
        request = envelope.get("request")
        if not isinstance(request, dict):
            raise ValueError("invalid manifest request")
        source = self._safe_path_component(request.get("source"), "source")
        dataset = self._safe_path_component(request.get("dataset"), "dataset")
        expected_directory = self.root / "data" / "raw" / "formal" / source / dataset
        if manifest_path.parent != expected_directory:
            raise ValueError("manifest path does not match manifest lineage")

        manifest_content_sha256 = envelope.get("content_sha256")
        if manifest_content_sha256 != stored.content_sha256:
            raise ValueError("content hash does not match manifest")
        verification = envelope.get("verification")
        if not isinstance(verification, dict) or verification.get("status") != "verified":
            raise ValueError("manifest verification is not verified")
        if verification.get("content_sha256") != stored.content_sha256:
            raise ValueError("content hash does not match verification")

        expected_content_path = expected_directory / f"{stored.content_sha256}.bin"
        if content_path != expected_content_path:
            raise ValueError("content hash does not match content path")
        try:
            raw_bytes = content_path.read_bytes()
        except OSError as error:
            raise ValueError(f"unable to read stored content: {content_path}") from error
        if _sha256_bytes(raw_bytes) != stored.content_sha256:
            raise ValueError("content hash verification failed")
        return raw_bytes

    def validate_stored_snapshot(
        self,
        fetch: OfficialFetch,
        stored: FormalStoredSnapshot,
        verification: EvidenceVerification,
        *,
        expected_producing_task_id: str | None,
    ) -> ValidatedFormalSnapshot:
        """Inspect exact fetch, verification, manifest, paths, and raw bytes.

        The returned frozen projection is populated from the re-read canonical manifest and
        is suitable for a persistence boundary; no caller-supplied path or metadata is
        returned until every immutable linkage has been checked.
        """
        self._validate_inspection_inputs(
            fetch, stored, verification, expected_producing_task_id
        )
        content_sha256 = fetch.content_sha256
        self._require_sha256(content_sha256, "fetch content hash")
        self._require_sha256(verification.content_sha256, "verification content hash")
        self._require_sha256(stored.content_sha256, "stored content hash")
        self._require_sha256(stored.manifest_sha256, "stored manifest hash")
        if fetch.effective_time_evidence_hash is not None:
            self._require_sha256(
                fetch.effective_time_evidence_hash, "effective_time_evidence_hash"
            )
        if verification.content_sha256 != content_sha256:
            raise ValueError("verification content_sha256 does not match fetch content_sha256")
        if stored.content_sha256 != content_sha256:
            raise ValueError("stored content_sha256 does not match fetch content_sha256")

        if Path(stored.manifest_path).name != f"{stored.manifest_sha256}.manifest.json":
            raise ValueError("manifest hash does not match manifest path")
        if Path(stored.content_path).name != f"{stored.content_sha256}.bin":
            raise ValueError("content hash does not match content path")
        manifest_path = self._path_inside_root(stored.manifest_path)
        content_path = self._path_inside_root(stored.content_path)

        envelope = self._read_manifest(manifest_path, stored.manifest_sha256)
        manifest_hash = envelope.get("manifest_sha256")
        self._require_sha256(manifest_hash, "manifest envelope hash")
        manifest_content_hash = envelope.get("content_sha256")
        self._require_sha256(manifest_content_hash, "manifest content_sha256")
        manifest_verification = envelope.get("verification")
        if not isinstance(manifest_verification, dict):
            raise ValueError("invalid manifest verification")
        self._require_sha256(
            manifest_verification.get("content_sha256"),
            "manifest verification content_sha256",
        )

        request = envelope.get("request")
        if not isinstance(request, dict):
            raise ValueError("invalid manifest request")
        source = self._safe_path_component(request.get("source"), "source")
        dataset = self._safe_path_component(request.get("dataset"), "dataset")
        expected_directory = self.root / "data" / "raw" / "formal" / source / dataset
        if manifest_path.parent != expected_directory:
            raise ValueError("manifest path does not match manifest lineage")
        if content_path.parent != manifest_path.parent:
            raise ValueError("content and manifest paths must be sibling files")

        expected_payload = self._manifest_payload(
            fetch, verification, expected_producing_task_id, content_sha256
        )
        payload = {key: value for key, value in envelope.items() if key != "manifest_sha256"}
        self._require_exact_manifest_payload(payload, expected_payload)

        try:
            raw_bytes = content_path.read_bytes()
        except OSError as error:
            raise ValueError(f"unable to read stored content: {content_path}") from error
        if _sha256_bytes(raw_bytes) != content_sha256:
            raise ValueError("content hash verification failed")
        if raw_bytes != fetch.raw_bytes:
            raise ValueError("stored raw bytes do not match fetch raw bytes")

        request_json_bytes = _canonical_json_bytes(request)
        verification_json_bytes = _canonical_json_bytes(manifest_verification)
        return ValidatedFormalSnapshot(
            source=source,
            dataset=dataset,
            request_json=request_json_bytes.decode("utf-8"),
            request_fingerprint=_sha256_bytes(request_json_bytes),
            security_id=request["security_id"],
            period_or_date=request["period_or_date"],
            exchange=request["exchange"],
            content_sha256=manifest_content_hash,
            manifest_sha256=manifest_hash,
            content_path=str(content_path),
            manifest_path=str(manifest_path),
            original_url=payload["original_url"],
            published_at_utc=payload["published_at_utc"],
            published_precision=payload["published_precision"],
            source_updated_at_utc=payload["source_updated_at_utc"],
            captured_at_utc=payload["captured_at_utc"],
            effective_at_utc=payload["effective_at_utc"],
            effective_time_evidence_hash=payload["effective_time_evidence_hash"],
            refresh_generation=payload["refresh_generation"],
            producing_task_id=payload["producing_task_id"],
            parser_id=payload["parser_id"],
            parser_version=payload["parser_version"],
            mapping_version=payload["mapping_version"],
            verification_json=verification_json_bytes.decode("utf-8"),
        )

    @staticmethod
    def _validate_inspection_inputs(
        fetch: object,
        stored: object,
        verification: object,
        expected_producing_task_id: object,
    ) -> None:
        if type(fetch) is not OfficialFetch:
            raise ValueError("fetch must have exact type OfficialFetch")
        if type(stored) is not FormalStoredSnapshot:
            raise ValueError("stored must have exact type FormalStoredSnapshot")
        if type(verification) is not EvidenceVerification:
            raise ValueError("verification must have exact type EvidenceVerification")
        if type(fetch.request) is not OfficialRequest:
            raise ValueError("fetch request must have exact type OfficialRequest")
        if type(fetch.raw_bytes) is not bytes:
            raise ValueError("fetch raw_bytes must have exact type bytes")
        if verification.status != "verified":
            raise ValueError("verification must be verified")
        if expected_producing_task_id is not None and (
            type(expected_producing_task_id) is not str or not expected_producing_task_id
        ):
            raise ValueError("expected producing_task_id must be a nonempty string or None")
        if type(stored.content_path) is not str or type(stored.manifest_path) is not str:
            raise ValueError("stored snapshot paths must have exact type str")

    @staticmethod
    def _require_exact_manifest_payload(
        payload: dict[str, object], expected: dict[str, object]
    ) -> None:
        if payload.keys() != expected.keys():
            raise ValueError("manifest payload fields do not exactly match expected fields")
        for field, expected_value in expected.items():
            if _canonical_json_bytes(payload[field]) != _canonical_json_bytes(expected_value):
                raise ValueError(f"manifest {field} does not match fetch or verification")

    def _validate_write_inputs(
        self,
        fetch: object,
        verification: object,
        producing_task_id: object,
    ) -> None:
        if not isinstance(fetch, OfficialFetch):
            raise ValueError("fetch must be an OfficialFetch")
        if not isinstance(verification, EvidenceVerification):
            raise ValueError("verification must be an EvidenceVerification")
        if verification.status != "verified":
            raise ValueError("verification must be verified")
        if verification.content_sha256 != fetch.content_sha256:
            raise ValueError("verification content hash does not match fetch content hash")
        if not isinstance(fetch.request, OfficialRequest):
            raise ValueError("fetch request must be an OfficialRequest")
        if not isinstance(producing_task_id, str) and producing_task_id is not None:
            raise ValueError("producing_task_id must be a string or None")

    @staticmethod
    def _manifest_payload(
        fetch: OfficialFetch,
        verification: EvidenceVerification,
        producing_task_id: str | None,
        content_sha256: str,
    ) -> dict[str, object]:
        request = fetch.request
        return {
            "schema_version": 1,
            "request": {
                "source": request.source,
                "dataset": request.dataset,
                "security_id": request.security_id,
                "period_or_date": request.period_or_date,
                "exchange": request.exchange,
            },
            "content_sha256": content_sha256,
            "original_url": fetch.original_url,
            "published_at_utc": fetch.published_at_utc,
            "published_precision": fetch.published_precision,
            "source_updated_at_utc": fetch.source_updated_at_utc,
            "captured_at_utc": fetch.captured_at_utc,
            "effective_at_utc": fetch.effective_at_utc,
            "effective_time_evidence_hash": fetch.effective_time_evidence_hash,
            "refresh_generation": fetch.refresh_generation,
            "parser_id": fetch.parser_id,
            "parser_version": fetch.parser_version,
            "mapping_version": fetch.mapping_version,
            "declared_security_id": fetch.declared_security_id,
            "declared_period": fetch.declared_period,
            "verification": {
                "status": verification.status,
                "content_sha256": verification.content_sha256,
                "reasons": list(verification.reasons),
                "effective_at_utc": verification.effective_at_utc,
            },
            "producing_task_id": producing_task_id,
        }

    def _write_content(self, target: Path, raw_bytes: bytes, content_sha256: str) -> None:
        self._require_target_within_root(target)
        if target.exists():
            try:
                existing = target.read_bytes()
            except OSError as error:
                raise ValueError(f"unable to read stored content: {target}") from error
            if _sha256_bytes(existing) != content_sha256 or existing != raw_bytes:
                raise ValueError("content hash verification failed for existing content")
            return
        self._atomic_write(
            target,
            raw_bytes,
            lambda part: self._validate_content_file(part, content_sha256),
        )

    def _write_manifest(self, target: Path, envelope: dict[str, object], manifest_sha256: str) -> None:
        self._require_target_within_root(target)
        encoded = _canonical_json_bytes(envelope)
        if target.exists():
            existing = self._read_manifest(target, manifest_sha256)
            if _canonical_json_bytes(existing) != encoded:
                raise ValueError("manifest hash verification failed for existing manifest")
            return
        self._atomic_write(
            target,
            encoded,
            lambda part: self._read_manifest(part, manifest_sha256),
        )

    def _atomic_write(
        self, target: Path, payload: bytes, validator: Callable[[Path], object]
    ) -> None:
        self._require_target_within_root(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        part_path: Path | None = None
        try:
            descriptor, part_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".part", dir=target.parent
            )
            part_path = Path(part_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            validator(part_path)
            os.replace(part_path, target)
            part_path = None
        finally:
            if part_path is not None:
                part_path.unlink(missing_ok=True)

    @staticmethod
    def _validate_content_file(path: Path, expected_sha256: str) -> None:
        try:
            actual = _sha256_bytes(path.read_bytes())
        except OSError as error:
            raise ValueError(f"unable to validate stored content: {path}") from error
        if actual != expected_sha256:
            raise ValueError("content hash verification failed before replacement")

    def _read_manifest(self, path: Path, expected_sha256: str) -> dict[str, object]:
        self._require_target_within_root(path)
        try:
            raw_bytes = path.read_bytes()
            envelope = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_unique_manifest_object)
        except _DuplicateManifestKeyError as error:
            raise ValueError("duplicate manifest key") from error
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid manifest: {path}") from error
        if not isinstance(envelope, dict):
            raise ValueError("invalid manifest envelope")
        if raw_bytes != _canonical_json_bytes(envelope):
            raise ValueError("manifest envelope is not canonical")
        manifest_sha256 = envelope.get("manifest_sha256")
        if manifest_sha256 != expected_sha256:
            raise ValueError("manifest hash does not match envelope")
        payload = {key: value for key, value in envelope.items() if key != "manifest_sha256"}
        if _sha256_bytes(_canonical_json_bytes(payload)) != expected_sha256:
            raise ValueError("manifest hash verification failed")
        return envelope

    @staticmethod
    def _require_sha256(value: object, label: str) -> None:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"invalid {label}")

    @staticmethod
    def _safe_path_component(value: object, field: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or PureWindowsPath(value).drive
            or PureWindowsPath(value).root
        ):
            raise ValueError(f"formal snapshot {field} must be a safe single path component")
        return value

    def _path_inside_root(self, value: str) -> Path:
        if not isinstance(value, str) or not value:
            raise ValueError("formal snapshot path must be a nonempty string")
        supplied = Path(value)
        if not supplied.is_absolute():
            raise ValueError("formal snapshot path must be absolute")
        normalized = Path(os.path.abspath(value))
        if os.path.normcase(str(supplied)) != os.path.normcase(str(normalized)):
            raise ValueError("formal snapshot path must be normalized")
        try:
            resolved = supplied.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"unable to resolve formal snapshot path: {supplied}") from error
        self._require_target_within_root(resolved)
        return resolved

    def _require_target_within_root(self, target: Path) -> None:
        try:
            target.resolve().relative_to(self.root)
        except ValueError as error:
            raise ValueError("formal snapshot path must stay inside the store root") from error


__all__ = ["FormalSnapshotStore", "FormalStoredSnapshot", "ValidatedFormalSnapshot"]
