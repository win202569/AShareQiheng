"""Hash-pinned root manifest and re-verifying registry bundle loader.

The repository protocol is intentionally read-only here.  V6 persistence is a
later concern; this boundary re-reads raw signed envelopes on every load and
does not trust a previously constructed registry dataclass.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
import weakref
from types import MappingProxyType
from typing import Literal, Protocol

from .formal_sources import RegistrySignatureVerifier, SignedSourceRegistry


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ROLE_FIELDS = {
    "source": "source_registry_hash",
    "mapping": "mapping_registry_hash",
    "feature": "feature_registry_hash",
    "scoring": "scoring_registry_hash",
    "industry": "industry_registry_hash",
    "cyclic": "cyclic_registry_hash",
    "redline": "redline_registry_hash",
    "status": "status_registry_hash",
    "event": "event_registry_hash",
}
_ROOT_KEYS = frozenset({"schema_version", "purpose", "approval_id", *_ROLE_FIELDS.values()})


class _DuplicateJsonKey(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON value {value!r}")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _load_canonical_object(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not bytes:
        raise ValueError(f"{label} must be UTF-8 bytes")
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} must be UTF-8") from error
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateJsonKey as error:
        raise ValueError(f"{label} has duplicate JSON keys") from error
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be valid JSON") from error
    if type(parsed) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    try:
        canonical = _canonical_json_bytes(parsed)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} contains invalid JSON values") from error
    if canonical != value:
        raise ValueError(f"{label} must be canonical JSON")
    return parsed


def _require_trimmed_text(value: object, label: str, *, identifier: bool = False) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an already-trimmed nonempty string")
    if identifier and _VERSION_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a version identifier")
    return value


def _require_hash(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _verify_signature(
    payload: bytes,
    signature: object,
    key_id: object,
    verifier: object,
    *,
    label: str,
) -> tuple[str, str]:
    signature_text = _require_trimmed_text(signature, f"{label} signature")
    key_text = _require_trimmed_text(key_id, f"{label} key_id", identifier=True)
    verify = getattr(verifier, "verify", None)
    if not callable(verify):
        raise ValueError(f"{label} signature verifier is invalid")
    try:
        verified = verify(payload, signature=signature_text, key_id=key_text)
    except Exception as error:
        raise ValueError(f"{label} signature verification failed") from error
    if verified is not True:
        raise ValueError(f"{label} signature verification failed")
    return signature_text, key_text


@dataclass(frozen=True)
class VerifiedRegistryBlob:
    """An untrusted raw child envelope read from a repository.

    It stays publicly constructible because persistence adapters and test
    fixtures model raw storage with it.  The loader deliberately re-verifies
    every field before a blob is present in a trusted bundle.
    """

    registry_role: str
    registry_hash: str
    canonical_json: bytes
    signature: str
    key_id: str
    approval_id: str | None
    declared_registry_manifest_hash: str
    binding_signature: str
    binding_key_id: str


def _make_trusted_registry_types() -> tuple[type[object], type[object], type[object]]:
    """Create trusted types with all minting/sealing state closure-private.

    Public fields remain inspectable for auditability, but neither copying a
    legitimate object nor invoking a module helper can grant its verified
    construction provenance.  Identity records also seal fields against
    ``object.__setattr__`` after signature validation.
    """

    manifest_fields = (
        "manifest_hash",
        "purpose",
        "approval_id",
        "canonical_json",
        "signature",
        "key_id",
        "source_registry_hash",
        "mapping_registry_hash",
        "feature_registry_hash",
        "scoring_registry_hash",
        "industry_registry_hash",
        "cyclic_registry_hash",
        "redline_registry_hash",
        "status_registry_hash",
        "event_registry_hash",
    )
    blob_fields = (
        "registry_role",
        "registry_hash",
        "canonical_json",
        "signature",
        "key_id",
        "approval_id",
        "declared_registry_manifest_hash",
        "binding_signature",
        "binding_key_id",
    )

    @dataclass(frozen=True)
    class _RawManifestEnvelope:
        manifest_hash: str
        purpose: str
        approval_id: str | None
        canonical_json: bytes
        signature: str
        key_id: str
        source_registry_hash: str
        mapping_registry_hash: str
        feature_registry_hash: str
        scoring_registry_hash: str
        industry_registry_hash: str
        cyclic_registry_hash: str
        redline_registry_hash: str
        status_registry_hash: str
        event_registry_hash: str

    @dataclass(frozen=True)
    class _RawBlobEnvelope:
        registry_role: str
        registry_hash: str
        canonical_json: bytes
        signature: str
        key_id: str
        approval_id: str | None
        declared_registry_manifest_hash: str
        binding_signature: str
        binding_key_id: str

    def require_optional_trimmed_text(value: object, label: str) -> str | None:
        if value is None:
            return None
        return _require_trimmed_text(value, label)

    def snapshot_manifest_envelope(stored: object) -> _RawManifestEnvelope:
        if type(stored) is not FormalRegistryManifest:
            raise ValueError("registry manifest is unknown or invalid")
        try:
            manifest_hash = stored.manifest_hash
            purpose = stored.purpose
            approval_id = stored.approval_id
            canonical_json = stored.canonical_json
            signature = stored.signature
            key_id = stored.key_id
            source_registry_hash = stored.source_registry_hash
            mapping_registry_hash = stored.mapping_registry_hash
            feature_registry_hash = stored.feature_registry_hash
            scoring_registry_hash = stored.scoring_registry_hash
            industry_registry_hash = stored.industry_registry_hash
            cyclic_registry_hash = stored.cyclic_registry_hash
            redline_registry_hash = stored.redline_registry_hash
            status_registry_hash = stored.status_registry_hash
            event_registry_hash = stored.event_registry_hash
        except AttributeError as error:
            raise ValueError("registry manifest is unknown or invalid") from error
        if type(canonical_json) is not bytes:
            raise ValueError("registry manifest canonical_json must be immutable bytes")
        try:
            return _RawManifestEnvelope(
                _require_hash(manifest_hash, "stored manifest_hash"),
                _require_trimmed_text(purpose, "stored manifest purpose"),
                require_optional_trimmed_text(approval_id, "stored manifest approval_id"),
                canonical_json,
                _require_trimmed_text(signature, "stored manifest signature"),
                _require_trimmed_text(key_id, "stored manifest key_id", identifier=True),
                _require_hash(source_registry_hash, "stored source_registry_hash"),
                _require_hash(mapping_registry_hash, "stored mapping_registry_hash"),
                _require_hash(feature_registry_hash, "stored feature_registry_hash"),
                _require_hash(scoring_registry_hash, "stored scoring_registry_hash"),
                _require_hash(industry_registry_hash, "stored industry_registry_hash"),
                _require_hash(cyclic_registry_hash, "stored cyclic_registry_hash"),
                _require_hash(redline_registry_hash, "stored redline_registry_hash"),
                _require_hash(status_registry_hash, "stored status_registry_hash"),
                _require_hash(event_registry_hash, "stored event_registry_hash"),
            )
        except ValueError as error:
            raise ValueError(f"registry manifest envelope is invalid: {error}") from error

    def snapshot_blob_envelope(stored: object, *, expected_role: str) -> _RawBlobEnvelope:
        if type(stored) is not VerifiedRegistryBlob:
            raise ValueError(f"registry blob is unknown for role {expected_role}")
        try:
            registry_role = stored.registry_role
            registry_hash = stored.registry_hash
            canonical_json = stored.canonical_json
            signature = stored.signature
            key_id = stored.key_id
            approval_id = stored.approval_id
            declared_registry_manifest_hash = stored.declared_registry_manifest_hash
            binding_signature = stored.binding_signature
            binding_key_id = stored.binding_key_id
        except AttributeError as error:
            raise ValueError(f"registry blob is unknown for role {expected_role}") from error
        if type(canonical_json) is not bytes:
            raise ValueError(
                f"registry blob canonical_json for role {expected_role} must be immutable bytes"
            )
        try:
            return _RawBlobEnvelope(
                _require_trimmed_text(registry_role, f"registry blob role for {expected_role}"),
                _require_hash(registry_hash, f"registry blob stored hash for role {expected_role}"),
                canonical_json,
                _require_trimmed_text(signature, f"registry blob signature for role {expected_role}"),
                _require_trimmed_text(
                    key_id, f"registry blob key_id for role {expected_role}", identifier=True
                ),
                require_optional_trimmed_text(
                    approval_id, f"registry blob approval for role {expected_role}"
                ),
                _require_hash(
                    declared_registry_manifest_hash,
                    f"registry blob declared root for role {expected_role}",
                ),
                _require_trimmed_text(
                    binding_signature,
                    f"registry blob binding signature for role {expected_role}",
                ),
                _require_trimmed_text(
                    binding_key_id,
                    f"registry blob binding key_id for role {expected_role}",
                    identifier=True,
                ),
            )
        except ValueError as error:
            raise ValueError(
                f"registry blob envelope is invalid for role {expected_role}: {error}"
            ) from error

    @dataclass(frozen=True)
    class _VerifiedManifestRecord:
        reference: weakref.ReferenceType[object]
        fingerprint: tuple[tuple[type[object], object], ...]

    @dataclass(frozen=True)
    class _VerifiedBundleRecord:
        reference: weakref.ReferenceType[object]
        manifest: object
        manifest_fingerprint: tuple[tuple[type[object], object], ...]
        blobs: object
        blobs_fingerprint: tuple[tuple[object, ...], ...]

    verified_manifests: dict[int, _VerifiedManifestRecord] = {}
    verified_bundles: dict[int, _VerifiedBundleRecord] = {}

    def fingerprint_fields(
        value: object, field_names: tuple[str, ...]
    ) -> tuple[tuple[type[object], object], ...] | None:
        fields: list[tuple[type[object], object]] = []
        try:
            for name in field_names:
                item = getattr(value, name)
                fields.append((type(item), item))
        except AttributeError:
            return None
        return tuple(fields)

    def manifest_fingerprint(
        manifest: object,
    ) -> tuple[tuple[type[object], object], ...] | None:
        return fingerprint_fields(manifest, manifest_fields)

    def remember_verified_manifest(manifest: object) -> None:
        fingerprint = manifest_fingerprint(manifest)
        if fingerprint is None:
            raise RuntimeError("verified registry manifest fields are incomplete")
        identity = id(manifest)

        def forget(reference: weakref.ReferenceType[object]) -> None:
            record = verified_manifests.get(identity)
            if record is not None and record.reference is reference:
                verified_manifests.pop(identity, None)

        reference = weakref.ref(manifest, forget)
        verified_manifests[identity] = _VerifiedManifestRecord(reference, fingerprint)

    def has_verified_manifest(manifest: object) -> bool:
        record = verified_manifests.get(id(manifest))
        return (
            record is not None
            and record.reference() is manifest
            and manifest_fingerprint(manifest) == record.fingerprint
        )

    def require_manifest_seal(manifest: object) -> None:
        if type(manifest) is not FormalRegistryManifest or not has_verified_manifest(manifest):
            raise ValueError("registry manifest was not verified by from_signed_bytes")

    def require_official_manifest(manifest: object) -> None:
        require_manifest_seal(manifest)
        if manifest.purpose != "official" or manifest.approval_id is None:
            raise ValueError("official registry manifest approval is required")
        _require_trimmed_text(manifest.approval_id, "official approval_id")

    @dataclass(frozen=True, init=False, slots=True, weakref_slot=True)
    class FormalRegistryManifest:
        manifest_hash: str
        purpose: Literal["test", "official"]
        approval_id: str | None
        canonical_json: bytes
        signature: str
        key_id: str
        source_registry_hash: str
        mapping_registry_hash: str
        feature_registry_hash: str
        scoring_registry_hash: str
        industry_registry_hash: str
        cyclic_registry_hash: str
        redline_registry_hash: str
        status_registry_hash: str
        event_registry_hash: str

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("FormalRegistryManifest must be loaded with from_signed_bytes")

        def require_official(self) -> None:
            require_official_manifest(self)

        def assert_member_hashes(self, **hashes: str) -> None:
            require_manifest_seal(self)
            expected_names = set(_ROLE_FIELDS.values())
            if set(hashes) != expected_names:
                raise ValueError("registry manifest member hashes must name exactly every role field")
            for field, expected in hashes.items():
                _require_hash(expected, field)
                if getattr(self, field) != expected:
                    raise ValueError(f"registry manifest member hash mismatch for {field}")

        @classmethod
        def from_signed_bytes(
            cls,
            canonical_json: bytes,
            signature: str,
            key_id: str,
            verifier: RegistrySignatureVerifier,
        ) -> "FormalRegistryManifest":
            if cls is not FormalRegistryManifest:
                raise ValueError("FormalRegistryManifest must have exact type")
            signature_text, key_text = _verify_signature(
                canonical_json, signature, key_id, verifier, label="registry manifest"
            )
            wire = _load_canonical_object(canonical_json, label="registry manifest")
            if set(wire) != _ROOT_KEYS:
                raise ValueError("registry manifest has unknown or missing keys")
            if wire["schema_version"] != "formal-registry-manifest-v1":
                raise ValueError("registry manifest schema_version is invalid")
            purpose = wire["purpose"]
            if purpose not in {"test", "official"}:
                raise ValueError("registry manifest purpose is invalid")
            approval_id = wire["approval_id"]
            if purpose == "official":
                _require_trimmed_text(approval_id, "official approval_id")
            elif approval_id is not None:
                raise ValueError("test registry manifest approval_id must be null")
            fields = {field: _require_hash(wire[field], field) for field in _ROLE_FIELDS.values()}
            if len(set(fields.values())) != len(_ROLE_FIELDS):
                raise ValueError("registry manifest member hashes must be unique")
            return construct_verified_manifest(
                manifest_hash=hashlib.sha256(canonical_json).hexdigest(),
                purpose=purpose,
                approval_id=approval_id,
                canonical_json=canonical_json,
                signature=signature_text,
                key_id=key_text,
                **fields,
            )

    def construct_verified_manifest(
        *,
        manifest_hash: str,
        purpose: Literal["test", "official"],
        approval_id: str | None,
        canonical_json: bytes,
        signature: str,
        key_id: str,
        source_registry_hash: str,
        mapping_registry_hash: str,
        feature_registry_hash: str,
        scoring_registry_hash: str,
        industry_registry_hash: str,
        cyclic_registry_hash: str,
        redline_registry_hash: str,
        status_registry_hash: str,
        event_registry_hash: str,
    ) -> FormalRegistryManifest:
        manifest = object.__new__(FormalRegistryManifest)
        for name, value in (
            ("manifest_hash", manifest_hash),
            ("purpose", purpose),
            ("approval_id", approval_id),
            ("canonical_json", canonical_json),
            ("signature", signature),
            ("key_id", key_id),
            ("source_registry_hash", source_registry_hash),
            ("mapping_registry_hash", mapping_registry_hash),
            ("feature_registry_hash", feature_registry_hash),
            ("scoring_registry_hash", scoring_registry_hash),
            ("industry_registry_hash", industry_registry_hash),
            ("cyclic_registry_hash", cyclic_registry_hash),
            ("redline_registry_hash", redline_registry_hash),
            ("status_registry_hash", status_registry_hash),
            ("event_registry_hash", event_registry_hash),
        ):
            object.__setattr__(manifest, name, value)
        remember_verified_manifest(manifest)
        return manifest

    def blob_fingerprint(
        blob: object,
    ) -> tuple[tuple[type[object], object], ...] | None:
        if type(blob) is not VerifiedRegistryBlob:
            return None
        return fingerprint_fields(blob, blob_fields)

    def blobs_fingerprint(blobs: object) -> tuple[tuple[object, ...], ...] | None:
        if not isinstance(blobs, Mapping):
            return None
        try:
            roles = tuple(sorted(blobs))
        except TypeError:
            return None
        fields: list[tuple[object, ...]] = []
        for role in roles:
            if type(role) is not str:
                return None
            try:
                fingerprint = blob_fingerprint(blobs[role])
            except (KeyError, TypeError):
                return None
            if fingerprint is None:
                return None
            fields.append((role, fingerprint))
        return tuple(fields)

    def remember_verified_bundle(bundle: object) -> None:
        try:
            manifest = bundle.manifest
            blobs = bundle.blobs
        except AttributeError as error:
            raise RuntimeError("verified registry bundle fields are incomplete") from error
        sealed_manifest = manifest_fingerprint(manifest)
        sealed_blobs = blobs_fingerprint(blobs)
        if sealed_manifest is None or sealed_blobs is None:
            raise RuntimeError("verified registry bundle fields are invalid")
        identity = id(bundle)

        def forget(reference: weakref.ReferenceType[object]) -> None:
            record = verified_bundles.get(identity)
            if record is not None and record.reference is reference:
                verified_bundles.pop(identity, None)

        reference = weakref.ref(bundle, forget)
        verified_bundles[identity] = _VerifiedBundleRecord(
            reference,
            manifest,
            sealed_manifest,
            blobs,
            sealed_blobs,
        )

    def has_verified_bundle(bundle: object) -> bool:
        record = verified_bundles.get(id(bundle))
        if record is None or record.reference() is not bundle:
            return False
        try:
            manifest = bundle.manifest
            blobs = bundle.blobs
        except AttributeError:
            return False
        return (
            manifest is record.manifest
            and has_verified_manifest(manifest)
            and manifest_fingerprint(manifest) == record.manifest_fingerprint
            and blobs is record.blobs
            and blobs_fingerprint(blobs) == record.blobs_fingerprint
        )

    def require_bundle_seal(bundle: object) -> None:
        if type(bundle) is not VerifiedRegistryBundle or not has_verified_bundle(bundle):
            raise ValueError("registry bundle was not verified by FormalRegistryBundleLoader")

    @dataclass(frozen=True, init=False, slots=True, weakref_slot=True)
    class VerifiedRegistryBundle:
        manifest: FormalRegistryManifest
        blobs: Mapping[str, VerifiedRegistryBlob]

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("VerifiedRegistryBundle must be constructed by the registry bundle loader")

        def require_official(self) -> None:
            require_bundle_seal(self)
            if type(self.manifest) is not FormalRegistryManifest:
                raise ValueError("registry bundle manifest is invalid")
            require_official_manifest(self.manifest)
            assert self.manifest.approval_id is not None
            if set(self.blobs) != set(_ROLE_FIELDS):
                raise ValueError("registry bundle does not contain every role")
            for role, blob in self.blobs.items():
                if type(blob) is not VerifiedRegistryBlob or blob.registry_role != role:
                    raise ValueError("registry bundle role is invalid")
                if blob.approval_id != self.manifest.approval_id:
                    raise ValueError("registry blob approval does not match official manifest")

        def blob(self, role: str) -> VerifiedRegistryBlob:
            require_bundle_seal(self)
            if type(role) is not str or role not in _ROLE_FIELDS:
                raise ValueError("registry role is unknown")
            blob = self.blobs.get(role)
            if type(blob) is not VerifiedRegistryBlob or blob.registry_role != role:
                raise ValueError("registry bundle role is missing or invalid")
            return blob

    def construct_verified_bundle(
        manifest: FormalRegistryManifest, blobs: Mapping[str, VerifiedRegistryBlob]
    ) -> VerifiedRegistryBundle:
        bundle = object.__new__(VerifiedRegistryBundle)
        object.__setattr__(bundle, "manifest", manifest)
        object.__setattr__(bundle, "blobs", blobs)
        remember_verified_bundle(bundle)
        return bundle

    class FormalRegistryBundleLoader:
        """Reconstruct a hash-pinned bundle from raw signed repository envelopes."""

        def __init__(self, repository: object, verifier: RegistrySignatureVerifier) -> None:
            if not callable(getattr(repository, "get_formal_registry_manifest", None)):
                raise ValueError("registry repository must provide get_formal_registry_manifest")
            if not callable(getattr(repository, "get_formal_registry_blob", None)):
                raise ValueError("registry repository must provide get_formal_registry_blob")
            if not callable(getattr(verifier, "verify", None)):
                raise ValueError("registry signature verifier is invalid")
            self._repository = repository
            self._verifier = verifier

        def _read_manifest(self, manifest_hash: str) -> FormalRegistryManifest:
            try:
                stored = self._repository.get_formal_registry_manifest(manifest_hash)
            except Exception as error:
                raise ValueError("registry manifest repository read failed") from error
            envelope = snapshot_manifest_envelope(stored)
            stored_manifest_hash = _require_hash(envelope.manifest_hash, "stored manifest_hash")
            if stored_manifest_hash != manifest_hash:
                raise ValueError("registry manifest hash does not match requested root")
            manifest = FormalRegistryManifest.from_signed_bytes(
                envelope.canonical_json, envelope.signature, envelope.key_id, self._verifier
            )
            if manifest.manifest_hash != manifest_hash:
                raise ValueError("registry manifest hash does not match requested root")
            return manifest

        def _read_blob(
            self,
            *,
            expected_role: str,
            expected_hash: str,
            manifest: FormalRegistryManifest,
        ) -> VerifiedRegistryBlob:
            try:
                stored = self._repository.get_formal_registry_blob(expected_hash)
            except Exception as error:
                raise ValueError("registry blob repository read failed") from error
            envelope = snapshot_blob_envelope(stored, expected_role=expected_role)
            signature, key_id = _verify_signature(
                envelope.canonical_json,
                envelope.signature,
                envelope.key_id,
                self._verifier,
                label=f"registry blob {expected_role}",
            )
            registry_hash = hashlib.sha256(envelope.canonical_json).hexdigest()
            stored_registry_hash = _require_hash(
                envelope.registry_hash, f"registry blob stored hash for role {expected_role}"
            )
            if registry_hash != expected_hash or stored_registry_hash != expected_hash:
                raise ValueError(f"registry blob hash mismatch for role {expected_role}")
            if type(envelope.registry_role) is not str or envelope.registry_role != expected_role:
                raise ValueError(f"registry blob role mismatch for role {expected_role}")
            wire = _load_canonical_object(envelope.canonical_json, label=f"registry blob {expected_role}")
            if wire.get("registry_role") != expected_role:
                raise ValueError(f"registry blob declared role mismatch for role {expected_role}")
            if expected_role == "source":
                source = SignedSourceRegistry.from_signed_bytes(
                    envelope.canonical_json, signature, key_id, self._verifier
                )
                if source.registry_hash != expected_hash:
                    raise ValueError("source registry hash mismatch")
            declared_root = _require_hash(
                envelope.declared_registry_manifest_hash,
                f"registry blob declared root for role {expected_role}",
            )
            if declared_root != manifest.manifest_hash:
                raise ValueError(f"registry blob declared root mismatch for role {expected_role}")
            binding_bytes = _canonical_json_bytes(
                {
                    "child_sha256": registry_hash,
                    "registry_manifest_hash": manifest.manifest_hash,
                    "registry_role": expected_role,
                }
            )
            binding_signature, binding_key_id = _verify_signature(
                binding_bytes,
                envelope.binding_signature,
                envelope.binding_key_id,
                self._verifier,
                label=f"registry blob binding {expected_role}",
            )
            approval_id = envelope.approval_id
            if manifest.purpose == "official":
                root_approval = _require_trimmed_text(
                    manifest.approval_id, "official manifest approval_id"
                )
                child_approval = _require_trimmed_text(
                    approval_id, f"registry blob approval for role {expected_role}"
                )
                if child_approval != root_approval:
                    raise ValueError(f"registry blob approval mismatch for role {expected_role}")
            elif approval_id is not None:
                raise ValueError(f"test registry blob approval must be null for role {expected_role}")
            return VerifiedRegistryBlob(
                registry_role=expected_role,
                registry_hash=registry_hash,
                canonical_json=envelope.canonical_json,
                signature=signature,
                key_id=key_id,
                approval_id=approval_id,
                declared_registry_manifest_hash=declared_root,
                binding_signature=binding_signature,
                binding_key_id=binding_key_id,
            )

        def load(self, manifest_hash: str) -> VerifiedRegistryBundle:
            _require_hash(manifest_hash, "manifest_hash")
            manifest = self._read_manifest(manifest_hash)
            expected = {field: getattr(manifest, field) for field in _ROLE_FIELDS.values()}
            manifest.assert_member_hashes(**expected)
            blobs: dict[str, VerifiedRegistryBlob] = {}
            for role, field in _ROLE_FIELDS.items():
                blobs[role] = self._read_blob(
                    expected_role=role,
                    expected_hash=expected[field],
                    manifest=manifest,
                )
            if set(blobs) != set(_ROLE_FIELDS):
                raise ValueError("registry bundle has missing or duplicate roles")
            return construct_verified_bundle(manifest, MappingProxyType(blobs))

    return FormalRegistryManifest, VerifiedRegistryBundle, FormalRegistryBundleLoader


FormalRegistryManifest, VerifiedRegistryBundle, FormalRegistryBundleLoader = (
    _make_trusted_registry_types()
)
del _make_trusted_registry_types


class FormalRegistryBundleRepository(Protocol):
    def get_formal_registry_manifest(self, manifest_hash: str) -> FormalRegistryManifest | None: ...

    def get_formal_registry_blob(self, registry_hash: str) -> VerifiedRegistryBlob | None: ...


__all__ = [
    "FormalRegistryBundleLoader",
    "FormalRegistryBundleRepository",
    "FormalRegistryManifest",
    "VerifiedRegistryBlob",
    "VerifiedRegistryBundle",
]
