"""Immutable content-addressed filesystem storage for Formal V3 feature bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import uuid
import weakref

from .formal_feature_contract import (
    FormalFeatureBundle,
    _canonical_json_bytes,
    _load_canonical_object,
    _require_hash,
)


_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "bundle_hash",
        "input_hash",
        "security_id",
        "as_of_utc",
        "template_id",
        "registry_manifest_hash",
        "feature_registry_hash",
        "bundle_schema_version",
        "contract_version",
    }
)


def _make_receipt_type() -> tuple[type[object], object, object]:
    fields = ("bundle_path", "manifest_path", "bundle_hash", "manifest_hash")
    records: dict[int, tuple[weakref.ReferenceType[object], tuple[str, ...]]] = {}

    def forget(identity: int) -> None:
        records.pop(identity, None)

    def validate(receipt: object) -> tuple[str, ...]:
        if type(receipt) is not FormalStoredFeatureBundle:
            raise ValueError("formal feature receipt must have exact type")
        try:
            values = tuple(getattr(receipt, field) for field in fields)
        except AttributeError as error:
            raise ValueError("formal feature receipt is incomplete") from error
        if any(type(value) is not str for value in values):
            raise ValueError("formal feature receipt fields must be exact strings")
        for path_value in values[:2]:
            path = Path(path_value)
            normalized = Path(os.path.abspath(path_value))
            if not path.is_absolute() or str(normalized) != path_value:
                raise ValueError("formal feature receipt paths must be absolute and canonical")
        _require_hash(values[2], "formal feature receipt bundle_hash")
        _require_hash(values[3], "formal feature receipt manifest_hash")
        return values

    def require(receipt: object) -> tuple[str, ...]:
        record = records.get(id(receipt))
        current = validate(receipt)
        if record is None or record[0]() is not receipt or current != record[1]:
            raise ValueError("formal feature receipt was forged or mutated")
        return current

    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
    class FormalStoredFeatureBundle:
        bundle_path: str
        manifest_path: str
        bundle_hash: str
        manifest_hash: str

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise TypeError("FormalStoredFeatureBundle is created only by the bundle store")

    def construct(
        bundle_path: str, manifest_path: str, bundle_hash: str, manifest_hash: str
    ) -> FormalStoredFeatureBundle:
        receipt = object.__new__(FormalStoredFeatureBundle)
        for field, value in zip(
            fields, (bundle_path, manifest_path, bundle_hash, manifest_hash), strict=True
        ):
            object.__setattr__(receipt, field, value)
        sealed = validate(receipt)
        identity = id(receipt)
        records[identity] = (
            weakref.ref(receipt, lambda _reference, identity=identity: forget(identity)), sealed
        )
        return receipt

    return FormalStoredFeatureBundle, construct, require


FormalStoredFeatureBundle, _construct_receipt, _require_receipt = _make_receipt_type()
del _make_receipt_type


def _is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(os.path, "isjunction", None)
        return bool(is_junction is not None and is_junction(path))
    except OSError as error:
        raise ValueError("formal feature path link inspection failed") from error


def _manifest(bundle: FormalFeatureBundle, bundle_hash: str) -> dict[str, object]:
    wire = bundle.to_dict()
    return {
        "schema_version": 1,
        "kind": "formal_feature_bundle",
        "bundle_hash": bundle_hash,
        "input_hash": wire["input_hash"],
        "security_id": wire["security_id"],
        "as_of_utc": wire["as_of_utc"],
        "template_id": wire["template_id"],
        "registry_manifest_hash": wire["registry_manifest_hash"],
        "feature_registry_hash": wire["feature_registry_hash"],
        "bundle_schema_version": wire["schema_version"],
        "contract_version": wire["contract_version"],
    }


def _make_store_type(construct_receipt: object, require_receipt: object) -> type[object]:
    class FormalFeatureBundleStore:
        __slots__ = ("_root", "_root_fingerprint")

        def __init__(self, root: str | Path) -> None:
            if type(root) not in {str, type(Path())}:
                raise ValueError("formal feature store root must be an exact str or Path")
            resolved = Path(root).resolve()
            object.__setattr__(self, "_root", resolved)
            object.__setattr__(self, "_root_fingerprint", str(resolved))

        def _validated_root(self) -> Path:
            try:
                root = self._root
                fingerprint = self._root_fingerprint
            except AttributeError as error:
                raise ValueError("formal feature store root is incomplete") from error
            if type(root) is not type(Path()) or type(fingerprint) is not str or str(root) != fingerprint:
                raise ValueError("formal feature store root was mutated")
            if root.resolve() != root:
                raise ValueError("formal feature store root is not canonical")
            return root

        def _directory(self, *, create: bool) -> Path:
            root = self._validated_root()
            current = root
            if _is_link(current):
                raise ValueError("formal feature store root must not be a link")
            if create:
                current.mkdir(parents=True, exist_ok=True)
            for component in ("data", "formal", "features"):
                current = current / component
                if current.exists() or _is_link(current):
                    if _is_link(current):
                        raise ValueError("formal feature store path must not contain a link")
                    if not current.is_dir():
                        raise ValueError("formal feature store path component is not a directory")
                elif create:
                    current.mkdir()
                else:
                    raise ValueError("formal feature store directory does not exist")
            if current.resolve() != current:
                raise ValueError("formal feature store directory escaped its root")
            return current

        def _paths(self, bundle_hash: str, *, create: bool) -> tuple[Path, Path, Path]:
            _require_hash(bundle_hash, "formal feature bundle hash")
            directory = self._directory(create=create)
            bundle_path = directory / f"{bundle_hash}.json"
            manifest_path = directory / f"{bundle_hash}.manifest.json"
            lock_path = directory / f"{bundle_hash}.lock"
            for path in (bundle_path, manifest_path, lock_path):
                if path.parent != directory or path.is_absolute() is False:
                    raise ValueError("formal feature path escaped its root")
            return bundle_path, manifest_path, lock_path

        @staticmethod
        def _require_regular_target(path: Path, label: str) -> None:
            if _is_link(path):
                raise ValueError(f"formal feature {label} must not be a link")
            if not path.exists() or not path.is_file():
                raise ValueError(f"formal feature {label} is missing or not a regular file")
            if path.resolve() != path:
                raise ValueError(f"formal feature {label} escaped its directory")

        @staticmethod
        def _read_target(path: Path, label: str) -> bytes:
            FormalFeatureBundleStore._require_regular_target(path, label)
            try:
                value = path.read_bytes()
            except OSError as error:
                raise ValueError(f"formal feature {label} read failed") from error
            FormalFeatureBundleStore._require_regular_target(path, label)
            return value

        @staticmethod
        def _write_atomic(path: Path, value: bytes, expected_hash: str, label: str) -> None:
            part = path.parent / f"{path.name}.{uuid.uuid4().hex}.part"
            try:
                with part.open("xb") as handle:
                    handle.write(value)
                    handle.flush()
                    os.fsync(handle.fileno())
                if _is_link(part) or part.read_bytes() != value:
                    raise ValueError(f"formal feature {label} part verification failed")
                if hashlib.sha256(value).hexdigest() != expected_hash:
                    raise ValueError(f"formal feature {label} expected hash is invalid")
                os.replace(part, path)
                final = FormalFeatureBundleStore._read_target(path, label)
                if final != value or hashlib.sha256(final).hexdigest() != expected_hash:
                    raise ValueError(f"formal feature {label} final verification failed")
            except ValueError:
                raise
            except OSError as error:
                raise ValueError(f"formal feature {label} write failed") from error
            finally:
                try:
                    if part.exists() or _is_link(part):
                        part.unlink()
                except OSError:
                    pass

        @staticmethod
        def _validate_existing(path: Path, expected: bytes, expected_hash: str, label: str) -> None:
            actual = FormalFeatureBundleStore._read_target(path, label)
            if actual != expected or hashlib.sha256(actual).hexdigest() != expected_hash:
                raise ValueError(f"formal feature {label} conflict")

        def write(self, bundle: FormalFeatureBundle) -> FormalStoredFeatureBundle:
            if type(bundle) is not FormalFeatureBundle:
                raise ValueError("formal feature store requires an exact FormalFeatureBundle")
            bundle_bytes = bundle.canonical_bytes()
            bundle_hash = hashlib.sha256(bundle_bytes).hexdigest()
            if bundle.bundle_hash() != bundle_hash:
                raise ValueError("formal feature bundle hash is inconsistent")
            manifest_bytes = _canonical_json_bytes(_manifest(bundle, bundle_hash))
            manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
            bundle_path, manifest_path, lock_path = self._paths(bundle_hash, create=True)
            try:
                lock_descriptor = os.open(
                    lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
            except FileExistsError as error:
                raise ValueError("formal feature bundle lock already exists") from error
            except OSError as error:
                raise ValueError("formal feature bundle lock creation failed") from error
            try:
                with os.fdopen(lock_descriptor, "wb") as lock_handle:
                    lock_handle.write(bundle_hash.encode("ascii"))
                    lock_handle.flush()
                    os.fsync(lock_handle.fileno())
                bundle_exists = bundle_path.exists() or _is_link(bundle_path)
                manifest_exists = manifest_path.exists() or _is_link(manifest_path)
                if manifest_exists and not bundle_exists:
                    raise ValueError("formal feature manifest-first state is invalid")
                if bundle_exists:
                    self._validate_existing(bundle_path, bundle_bytes, bundle_hash, "bundle")
                else:
                    self._write_atomic(bundle_path, bundle_bytes, bundle_hash, "bundle")
                if manifest_exists:
                    self._validate_existing(
                        manifest_path, manifest_bytes, manifest_hash, "manifest"
                    )
                else:
                    self._write_atomic(
                        manifest_path, manifest_bytes, manifest_hash, "manifest"
                    )
                receipt = construct_receipt(
                    str(bundle_path), str(manifest_path), bundle_hash, manifest_hash
                )
                self.read_verified(receipt)
                return receipt
            finally:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as error:
                    raise ValueError("formal feature bundle lock cleanup failed") from error

        def read_verified(self, receipt: FormalStoredFeatureBundle) -> FormalFeatureBundle:
            bundle_path_text, manifest_path_text, bundle_hash, manifest_hash = require_receipt(
                receipt
            )
            bundle_path, manifest_path, _ = self._paths(bundle_hash, create=False)
            if bundle_path_text != str(bundle_path) or manifest_path_text != str(manifest_path):
                raise ValueError("formal feature receipt paths do not belong to this store")
            manifest_bytes = self._read_target(manifest_path, "manifest")
            if hashlib.sha256(manifest_bytes).hexdigest() != manifest_hash:
                raise ValueError("formal feature manifest hash mismatch")
            manifest_wire = _load_canonical_object(
                manifest_bytes, label="formal feature manifest"
            )
            if set(manifest_wire) != _MANIFEST_KEYS:
                raise ValueError("formal feature manifest has unknown or missing keys")
            bundle_bytes = self._read_target(bundle_path, "bundle")
            if hashlib.sha256(bundle_bytes).hexdigest() != bundle_hash:
                raise ValueError("formal feature bundle hash mismatch")
            bundle_wire = _load_canonical_object(bundle_bytes, label="formal feature bundle")
            bundle = FormalFeatureBundle.from_dict(bundle_wire)
            if bundle.canonical_bytes() != bundle_bytes or bundle.bundle_hash() != bundle_hash:
                raise ValueError("formal feature bundle canonical hash mismatch")
            expected_manifest = _manifest(bundle, bundle_hash)
            expected_manifest_bytes = _canonical_json_bytes(expected_manifest)
            if manifest_bytes != expected_manifest_bytes or manifest_wire != expected_manifest:
                raise ValueError("formal feature manifest header mismatch")
            if hashlib.sha256(expected_manifest_bytes).hexdigest() != manifest_hash:
                raise ValueError("formal feature manifest hash mismatch")
            return bundle

    return FormalFeatureBundleStore


FormalFeatureBundleStore = _make_store_type(_construct_receipt, _require_receipt)
del _make_store_type, _construct_receipt, _require_receipt


__all__ = ["FormalStoredFeatureBundle", "FormalFeatureBundleStore"]
