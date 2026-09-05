"""Immutable content-addressed filesystem storage for Formal V3 feature bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
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


class _SecureDirectory:
    """Pin the verified directory chain and operate relative to the final directory."""

    __slots__ = ("path", "_posix_descriptors", "_windows_handles")

    def __init__(self, path: Path) -> None:
        self.path = path
        self._posix_descriptors: list[int] = []
        self._windows_handles: list[int] = []

    def __enter__(self) -> "_SecureDirectory":
        try:
            if os.name == "nt":
                self._pin_windows_chain()
            else:
                self._pin_posix_chain()
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        while self._posix_descriptors:
            os.close(self._posix_descriptors.pop())
        if self._windows_handles:
            import ctypes
            from ctypes import wintypes

            close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
            close_handle.argtypes = (wintypes.HANDLE,)
            close_handle.restype = wintypes.BOOL
            while self._windows_handles:
                close_handle(self._windows_handles.pop())

    def _pin_posix_chain(self) -> None:
        required = (os.open, os.stat, os.unlink, os.link)
        if (
            any(operation not in os.supports_dir_fd for operation in required)
            or not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "O_NOFOLLOW")
        ):
            raise ValueError("secure directory-relative filesystem operations are unsupported")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open(self.path.anchor, flags)
        self._posix_descriptors.append(descriptor)
        for component in self.path.parts[1:]:
            descriptor = os.open(component, flags, dir_fd=descriptor)
            self._posix_descriptors.append(descriptor)
        details = os.fstat(self.descriptor)
        if not stat.S_ISDIR(details.st_mode):
            raise ValueError("formal feature store directory is not a directory")

    def _pin_windows_chain(self) -> None:
        import ctypes
        from ctypes import wintypes

        class FileAttributeTagInfo(ctypes.Structure):
            _fields_ = [("file_attributes", wintypes.DWORD), ("reparse_tag", wintypes.DWORD)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        get_info = kernel32.GetFileInformationByHandleEx
        get_info.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        )
        get_info.restype = wintypes.BOOL
        generic_read = 0x80000000
        file_share_read = 0x00000001
        file_share_write = 0x00000002
        open_existing = 3
        backup_semantics = 0x02000000
        open_reparse_point = 0x00200000
        directory_attribute = 0x00000010
        reparse_attribute = 0x00000400
        invalid_handle = ctypes.c_void_p(-1).value
        current = Path(self.path.anchor)
        candidates = [current]
        for component in self.path.parts[1:]:
            current = current / component
            candidates.append(current)
        for candidate in candidates:
            handle = create_file(
                str(candidate),
                generic_read,
                file_share_read | file_share_write,
                None,
                open_existing,
                backup_semantics | open_reparse_point,
                None,
            )
            if handle == invalid_handle:
                raise ValueError(
                    "formal feature directory handle acquisition failed"
                ) from ctypes.WinError(ctypes.get_last_error())
            self._windows_handles.append(handle)
            details = FileAttributeTagInfo()
            if not get_info(handle, 9, ctypes.byref(details), ctypes.sizeof(details)):
                raise ValueError(
                    "formal feature directory handle inspection failed"
                ) from ctypes.WinError(ctypes.get_last_error())
            if (
                details.file_attributes & directory_attribute == 0
                or details.file_attributes & reparse_attribute != 0
            ):
                raise ValueError("formal feature directory chain contains a link or non-directory")

    @property
    def descriptor(self) -> int:
        if not self._posix_descriptors:
            raise ValueError("secure directory descriptor is unavailable")
        return self._posix_descriptors[-1]

    def _path(self, name: str) -> Path:
        if type(name) is not str or Path(name).name != name:
            raise ValueError("formal feature filename is invalid")
        return self.path / name

    def open_exclusive(self, name: str) -> int:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if os.name == "nt":
            return os.open(self._path(name), flags, 0o600)
        return os.open(name, flags | os.O_NOFOLLOW, 0o600, dir_fd=self.descriptor)

    def exists(self, name: str) -> bool:
        if os.name == "nt":
            path = self._path(name)
            return path.exists() or _is_link(path)
        try:
            os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True

    def read_regular(self, name: str, label: str) -> bytes:
        if os.name == "nt":
            return FormalFeatureBundleStore._read_target_path(self._path(name), label)
        try:
            descriptor = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.descriptor
            )
        except OSError as error:
            raise ValueError(f"formal feature {label} read failed") from error
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError(f"formal feature {label} is missing or not a regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError(f"formal feature {label} changed while reading")
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    def link_no_clobber(self, source: str, target: str) -> None:
        if os.name == "nt":
            os.link(self._path(source), self._path(target), follow_symlinks=False)
            return
        os.link(
            source,
            target,
            src_dir_fd=self.descriptor,
            dst_dir_fd=self.descriptor,
            follow_symlinks=False,
        )

    def unlink(self, name: str, *, missing_ok: bool) -> None:
        try:
            if os.name == "nt":
                self._path(name).unlink()
            else:
                os.unlink(name, dir_fd=self.descriptor)
        except FileNotFoundError:
            if not missing_ok:
                raise


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
        def _read_target_path(path: Path, label: str) -> bytes:
            FormalFeatureBundleStore._require_regular_target(path, label)
            try:
                value = path.read_bytes()
            except OSError as error:
                raise ValueError(f"formal feature {label} read failed") from error
            FormalFeatureBundleStore._require_regular_target(path, label)
            return value

        @staticmethod
        def _write_atomic(
            directory: _SecureDirectory,
            target_name: str,
            value: bytes,
            expected_hash: str,
            label: str,
        ) -> None:
            part_name = f"{target_name}.{uuid.uuid4().hex}.part"
            try:
                with os.fdopen(directory.open_exclusive(part_name), "wb") as handle:
                    handle.write(value)
                    handle.flush()
                    os.fsync(handle.fileno())
                if directory.read_regular(part_name, f"{label} part") != value:
                    raise ValueError(f"formal feature {label} part verification failed")
                if hashlib.sha256(value).hexdigest() != expected_hash:
                    raise ValueError(f"formal feature {label} expected hash is invalid")
                try:
                    directory.link_no_clobber(part_name, target_name)
                except FileExistsError:
                    final = directory.read_regular(target_name, label)
                    if final != value or hashlib.sha256(final).hexdigest() != expected_hash:
                        raise ValueError(f"formal feature {label} conflict")
                    return
                final = directory.read_regular(target_name, label)
                if final != value or hashlib.sha256(final).hexdigest() != expected_hash:
                    raise ValueError(f"formal feature {label} final verification failed")
            except ValueError:
                raise
            except OSError as error:
                raise ValueError(f"formal feature {label} write failed") from error
            finally:
                try:
                    directory.unlink(part_name, missing_ok=True)
                except OSError:
                    pass

        @staticmethod
        def _validate_existing(
            directory: _SecureDirectory,
            target_name: str,
            expected: bytes,
            expected_hash: str,
            label: str,
        ) -> None:
            actual = directory.read_regular(target_name, label)
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
            with _SecureDirectory(bundle_path.parent) as directory:
                try:
                    lock_descriptor = directory.open_exclusive(lock_path.name)
                except FileExistsError as error:
                    raise ValueError("formal feature bundle lock already exists") from error
                except OSError as error:
                    raise ValueError("formal feature bundle lock creation failed") from error
                try:
                    with os.fdopen(lock_descriptor, "wb") as lock_handle:
                        lock_handle.write(bundle_hash.encode("ascii"))
                        lock_handle.flush()
                        os.fsync(lock_handle.fileno())
                    bundle_exists = directory.exists(bundle_path.name)
                    manifest_exists = directory.exists(manifest_path.name)
                    if manifest_exists and not bundle_exists:
                        raise ValueError("formal feature manifest-first state is invalid")
                    if bundle_exists:
                        self._validate_existing(
                            directory, bundle_path.name, bundle_bytes, bundle_hash, "bundle"
                        )
                    else:
                        self._write_atomic(
                            directory, bundle_path.name, bundle_bytes, bundle_hash, "bundle"
                        )
                    if manifest_exists:
                        self._validate_existing(
                            directory,
                            manifest_path.name,
                            manifest_bytes,
                            manifest_hash,
                            "manifest",
                        )
                    else:
                        self._write_atomic(
                            directory,
                            manifest_path.name,
                            manifest_bytes,
                            manifest_hash,
                            "manifest",
                        )
                    receipt = construct_receipt(
                        str(bundle_path), str(manifest_path), bundle_hash, manifest_hash
                    )
                    self.read_verified(receipt)
                    return receipt
                finally:
                    try:
                        directory.unlink(lock_path.name, missing_ok=True)
                    except OSError as error:
                        raise ValueError("formal feature bundle lock cleanup failed") from error

        def read_verified(self, receipt: FormalStoredFeatureBundle) -> FormalFeatureBundle:
            bundle_path_text, manifest_path_text, bundle_hash, manifest_hash = require_receipt(
                receipt
            )
            bundle_path, manifest_path, _ = self._paths(bundle_hash, create=False)
            if bundle_path_text != str(bundle_path) or manifest_path_text != str(manifest_path):
                raise ValueError("formal feature receipt paths do not belong to this store")
            with _SecureDirectory(bundle_path.parent) as directory:
                manifest_bytes = directory.read_regular(manifest_path.name, "manifest")
                if hashlib.sha256(manifest_bytes).hexdigest() != manifest_hash:
                    raise ValueError("formal feature manifest hash mismatch")
                manifest_wire = _load_canonical_object(
                    manifest_bytes, label="formal feature manifest"
                )
                if set(manifest_wire) != _MANIFEST_KEYS:
                    raise ValueError("formal feature manifest has unknown or missing keys")
                bundle_bytes = directory.read_regular(bundle_path.name, "bundle")
                if hashlib.sha256(bundle_bytes).hexdigest() != bundle_hash:
                    raise ValueError("formal feature bundle hash mismatch")
                bundle_wire = _load_canonical_object(
                    bundle_bytes, label="formal feature bundle"
                )
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
