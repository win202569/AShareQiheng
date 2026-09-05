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

    def require_official(self) -> None:
        if self.purpose != "official" or self.approval_id is None:
            raise ValueError("official registry manifest approval is required")
        _require_trimmed_text(self.approval_id, "official approval_id")

    def assert_member_hashes(self, **hashes: str) -> None:
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
        return cls(
            manifest_hash=hashlib.sha256(canonical_json).hexdigest(),
            purpose=purpose,
            approval_id=approval_id,
            canonical_json=canonical_json,
            signature=signature_text,
            key_id=key_text,
            **fields,
        )


@dataclass(frozen=True)
class VerifiedRegistryBlob:
    registry_role: str
    registry_hash: str
    canonical_json: bytes
    signature: str
    key_id: str
    approval_id: str | None
    declared_registry_manifest_hash: str
    binding_signature: str
    binding_key_id: str


@dataclass(frozen=True)
class VerifiedRegistryBundle:
    manifest: FormalRegistryManifest
    blobs: Mapping[str, VerifiedRegistryBlob]

    def require_official(self) -> None:
        if type(self.manifest) is not FormalRegistryManifest:
            raise ValueError("registry bundle manifest is invalid")
        self.manifest.require_official()
        assert self.manifest.approval_id is not None
        if set(self.blobs) != set(_ROLE_FIELDS):
            raise ValueError("registry bundle does not contain every role")
        for role, blob in self.blobs.items():
            if type(blob) is not VerifiedRegistryBlob or blob.registry_role != role:
                raise ValueError("registry bundle role is invalid")
            if blob.approval_id != self.manifest.approval_id:
                raise ValueError("registry blob approval does not match official manifest")

    def blob(self, role: str) -> VerifiedRegistryBlob:
        if type(role) is not str or role not in _ROLE_FIELDS:
            raise ValueError("registry role is unknown")
        blob = self.blobs.get(role)
        if type(blob) is not VerifiedRegistryBlob or blob.registry_role != role:
            raise ValueError("registry bundle role is missing or invalid")
        return blob


class FormalRegistryBundleRepository(Protocol):
    def get_formal_registry_manifest(self, manifest_hash: str) -> FormalRegistryManifest | None: ...

    def get_formal_registry_blob(self, registry_hash: str) -> VerifiedRegistryBlob | None: ...


class FormalRegistryBundleLoader:
    """Reconstruct a hash-pinned bundle from raw signed repository envelopes."""

    def __init__(
        self, repository: FormalRegistryBundleRepository, verifier: RegistrySignatureVerifier
    ) -> None:
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
        if type(stored) is not FormalRegistryManifest:
            raise ValueError("registry manifest is unknown or invalid")
        manifest = FormalRegistryManifest.from_signed_bytes(
            stored.canonical_json, stored.signature, stored.key_id, self._verifier
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
        if type(stored) is not VerifiedRegistryBlob:
            raise ValueError(f"registry blob is unknown for role {expected_role}")
        signature, key_id = _verify_signature(
            stored.canonical_json,
            stored.signature,
            stored.key_id,
            self._verifier,
            label=f"registry blob {expected_role}",
        )
        registry_hash = hashlib.sha256(stored.canonical_json).hexdigest()
        if registry_hash != expected_hash or stored.registry_hash != expected_hash:
            raise ValueError(f"registry blob hash mismatch for role {expected_role}")
        if stored.registry_role != expected_role:
            raise ValueError(f"registry blob role mismatch for role {expected_role}")
        wire = _load_canonical_object(stored.canonical_json, label=f"registry blob {expected_role}")
        if wire.get("registry_role") != expected_role:
            raise ValueError(f"registry blob declared role mismatch for role {expected_role}")
        if expected_role == "source":
            source = SignedSourceRegistry.from_signed_bytes(
                stored.canonical_json, signature, key_id, self._verifier
            )
            if source.registry_hash != expected_hash:
                raise ValueError("source registry hash mismatch")
        try:
            declared_root = _require_hash(
                stored.declared_registry_manifest_hash,
                f"registry blob declared root for role {expected_role}",
            )
        except ValueError as error:
            raise ValueError(str(error)) from error
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
            stored.binding_signature,
            stored.binding_key_id,
            self._verifier,
            label=f"registry blob binding {expected_role}",
        )
        approval_id = stored.approval_id
        if manifest.purpose == "official":
            if approval_id != manifest.approval_id:
                raise ValueError(f"registry blob approval mismatch for role {expected_role}")
        elif approval_id is not None:
            raise ValueError(f"test registry blob approval must be null for role {expected_role}")
        return VerifiedRegistryBlob(
            registry_role=expected_role,
            registry_hash=registry_hash,
            canonical_json=stored.canonical_json,
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
        expected = {
            field: getattr(manifest, field) for field in _ROLE_FIELDS.values()
        }
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
        return VerifiedRegistryBundle(manifest, MappingProxyType(blobs))


__all__ = [
    "FormalRegistryBundleLoader",
    "FormalRegistryBundleRepository",
    "FormalRegistryManifest",
    "VerifiedRegistryBlob",
    "VerifiedRegistryBundle",
]
