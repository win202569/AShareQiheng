import hashlib
import json
import unittest
from dataclasses import replace

import ashare_pipeline.formal_registry_manifest as registry_manifest_module
from ashare_pipeline.formal_registry_manifest import (
    FormalRegistryBundleLoader,
    FormalRegistryManifest,
    VerifiedRegistryBlob,
    VerifiedRegistryBundle,
)


ROLES = (
    "source",
    "mapping",
    "feature",
    "scoring",
    "industry",
    "cyclic",
    "redline",
    "status",
    "event",
)


def canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


class AcceptingVerifier:
    def verify(self, payload, *, signature, key_id):
        return signature == "fixture-signature" and key_id == "fixture-key"


class RaisingVerifier:
    def verify(self, payload, *, signature, key_id):
        raise RuntimeError("verifier unavailable")


class BlobRoleMutatingVerifier(AcceptingVerifier):
    """Rewrites one raw envelope immediately after its child signature check."""

    def __init__(self, blob, child_bytes):
        self.blob = blob
        self.child_bytes = child_bytes
        self.mutated = False

    def verify(self, payload, *, signature, key_id):
        accepted = super().verify(payload, signature=signature, key_id=key_id)
        if accepted and not self.mutated and payload == self.child_bytes:
            object.__setattr__(self.blob, "registry_role", "source")
            self.mutated = True
        return accepted


class CountingVerifier(AcceptingVerifier):
    def __init__(self):
        self.calls = 0

    def verify(self, payload, *, signature, key_id):
        self.calls += 1
        return super().verify(payload, signature=signature, key_id=key_id)


class SignatureMapVerifier:
    """A fixture verifier that proves exactly which canonical bytes were signed."""

    def __init__(self, signatures):
        self.signatures = signatures

    def verify(self, payload, *, signature, key_id):
        return key_id == "fixture-key" and self.signatures.get(payload) == signature


class InMemoryRepository:
    def __init__(self, manifest, blobs):
        self.manifest = manifest
        self.blobs = blobs

    def get_formal_registry_manifest(self, manifest_hash):
        return self.manifest if manifest_hash == self.manifest.manifest_hash else None

    def get_formal_registry_blob(self, registry_hash):
        return self.blobs.get(registry_hash)


class HashBlindRepository(InMemoryRepository):
    """Simulates storage whose index was not trusted after a raw-file swap."""

    def get_formal_registry_manifest(self, manifest_hash):
        return self.manifest


def source_bytes():
    return canonical_bytes(
        {
            "configs": [],
            "registry_role": "source",
            "schema_version": "formal-source-registry-v1",
        }
    )


def fixture_blob(role, raw, manifest_hash, *, registry_role=None, registry_hash=None, **changes):
    return VerifiedRegistryBlob(
        registry_role=role if registry_role is None else registry_role,
        registry_hash=hashlib.sha256(raw).hexdigest() if registry_hash is None else registry_hash,
        canonical_json=raw,
        signature="fixture-signature",
        key_id="fixture-key",
        approval_id=None,
        declared_registry_manifest_hash=manifest_hash,
        binding_signature="fixture-signature",
        binding_key_id="fixture-key",
        **changes,
    )


def untrusted_manifest_envelope(manifest, **changes):
    """Model raw repository fields without granting a verified root capability."""
    envelope = object.__new__(FormalRegistryManifest)
    for field in (
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
    ):
        object.__setattr__(envelope, field, changes.get(field, getattr(manifest, field)))
    return envelope


def binding_bytes(child_sha256, registry_manifest_hash, registry_role):
    return canonical_bytes(
        {
            "child_sha256": child_sha256,
            "registry_manifest_hash": registry_manifest_hash,
            "registry_role": registry_role,
        }
    )


def fixture_repository():
    hashes = {}
    raw_by_role = {}
    for role in ROLES:
        raw = source_bytes() if role == "source" else canonical_bytes(
            {"registry_role": role, "schema_version": "fixture-v1"}
        )
        registry_hash = hashlib.sha256(raw).hexdigest()
        hashes[f"{role}_registry_hash"] = registry_hash
        raw_by_role[role] = raw
    root = canonical_bytes(
        {
            "schema_version": "formal-registry-manifest-v1",
            "purpose": "test",
            "approval_id": None,
            **hashes,
        }
    )
    manifest = FormalRegistryManifest.from_signed_bytes(
        root, "fixture-signature", "fixture-key", AcceptingVerifier()
    )
    blobs = {
        hashes[f"{role}_registry_hash"]: fixture_blob(
            role, raw, manifest.manifest_hash
        )
        for role, raw in raw_by_role.items()
    }
    return InMemoryRepository(manifest, blobs), manifest, blobs


def strict_binding_fixture():
    repository, manifest, blobs = fixture_repository()
    signatures = {manifest.canonical_json: "fixture-signature"}
    strict_blobs = {}
    for role in ROLES:
        registry_hash = getattr(manifest, f"{role}_registry_hash")
        blob = blobs[registry_hash]
        signatures[blob.canonical_json] = "fixture-signature"
        signed_binding = binding_bytes(registry_hash, manifest.manifest_hash, role)
        binding_signature = hashlib.sha256(signed_binding).hexdigest()
        signatures[signed_binding] = binding_signature
        strict_blobs[registry_hash] = replace(blob, binding_signature=binding_signature)
    return InMemoryRepository(manifest, strict_blobs), manifest, strict_blobs, SignatureMapVerifier(signatures)


class FormalRegistryManifestTests(unittest.TestCase):
    def test_loader_rereads_exact_nine_role_blobs_and_test_bundle_cannot_be_official(self):
        repository, manifest, _ = fixture_repository()

        bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(
            manifest.manifest_hash
        )

        self.assertEqual(tuple(sorted(bundle.blobs)), tuple(sorted(ROLES)))
        self.assertEqual(bundle.blob("source").registry_hash, manifest.source_registry_hash)
        with self.assertRaisesRegex(ValueError, "official"):
            bundle.require_official()
        with self.assertRaisesRegex(ValueError, "member"):
            manifest.assert_member_hashes(source_registry_hash="0" * 64)

    def test_loader_rejects_root_or_child_signature_tampering_after_storage(self):
        repository, manifest, blobs = fixture_repository()
        repository.manifest = untrusted_manifest_envelope(manifest, signature="tampered")
        with self.assertRaisesRegex(ValueError, "signature"):
            FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)

        repository, manifest, blobs = fixture_repository()
        source = blobs[manifest.source_registry_hash]
        repository.blobs[source.registry_hash] = replace(source, signature="tampered")
        with self.assertRaisesRegex(ValueError, "signature"):
            FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)

    def test_loader_snapshots_raw_blob_before_verifier_can_mutate_its_envelope(self):
        repository, manifest, blobs = fixture_repository()
        source = replace(blobs[manifest.source_registry_hash], registry_role="mapping")
        repository.blobs[source.registry_hash] = source
        verifier = BlobRoleMutatingVerifier(source, source.canonical_json)

        with self.assertRaisesRegex(ValueError, "role"):
            FormalRegistryBundleLoader(repository, verifier).load(manifest.manifest_hash)
        self.assertTrue(verifier.mutated)

    def test_loader_rejects_mutable_raw_bytes_before_signature_verification(self):
        repository, manifest, blobs = fixture_repository()
        source = replace(
            blobs[manifest.source_registry_hash],
            canonical_json=bytearray(blobs[manifest.source_registry_hash].canonical_json),
        )
        repository.blobs[source.registry_hash] = source
        verifier = CountingVerifier()

        with self.assertRaises(ValueError):
            FormalRegistryBundleLoader(repository, verifier).load(manifest.manifest_hash)
        self.assertEqual(verifier.calls, 1)

    def test_scoring_hash_swap_and_role_swap_are_rejected_before_runtime_use(self):
        repository, manifest, blobs = fixture_repository()
        replacement_raw = canonical_bytes({"registry_role": "scoring", "schema_version": "other"})
        replacement_hash = hashlib.sha256(replacement_raw).hexdigest()
        root = json.loads(manifest.canonical_json)
        root["scoring_registry_hash"] = replacement_hash
        swapped = FormalRegistryManifest.from_signed_bytes(
            canonical_bytes(root), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        repository.blobs[replacement_hash] = fixture_blob(
            "scoring", replacement_raw, swapped.manifest_hash
        )
        tampered_index = HashBlindRepository(swapped, repository.blobs)
        with self.assertRaisesRegex(ValueError, "manifest hash"):
            FormalRegistryBundleLoader(tampered_index, AcceptingVerifier()).load(
                manifest.manifest_hash
            )

        repository, manifest, blobs = fixture_repository()
        source = blobs[manifest.source_registry_hash]
        repository.blobs[source.registry_hash] = replace(source, registry_role="mapping")
        with self.assertRaisesRegex(ValueError, "role"):
            FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)

    def test_loader_rejects_rehashed_child_bytes_and_duplicate_or_unknown_roles(self):
        repository, manifest, blobs = fixture_repository()
        source = blobs[manifest.source_registry_hash]
        repository.blobs[source.registry_hash] = replace(source, registry_hash="0" * 64)
        with self.assertRaisesRegex(ValueError, "hash"):
            FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)

        repository, manifest, blobs = fixture_repository()
        root = json.loads(manifest.canonical_json)
        root["mapping_registry_hash"] = root["source_registry_hash"]
        with self.assertRaisesRegex(ValueError, "unique"):
            FormalRegistryManifest.from_signed_bytes(
                canonical_bytes(root), "fixture-signature", "fixture-key", AcceptingVerifier()
            )

        repository, manifest, blobs = fixture_repository()
        raw = canonical_bytes({"registry_role": "event", "schema_version": "other-v1"})
        role_swapped_hash = hashlib.sha256(raw).hexdigest()
        root = json.loads(manifest.canonical_json)
        root["mapping_registry_hash"] = role_swapped_hash
        swapped = FormalRegistryManifest.from_signed_bytes(
            canonical_bytes(root), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        rebound_blobs = {
            registry_hash: replace(
                blob, declared_registry_manifest_hash=swapped.manifest_hash
            )
            for registry_hash, blob in blobs.items()
        }
        repository = InMemoryRepository(
            swapped,
            {
                **rebound_blobs,
                role_swapped_hash: fixture_blob(
                    "mapping", raw, swapped.manifest_hash
                ),
            },
        )
        with self.assertRaisesRegex(ValueError, "declared role"):
            FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(swapped.manifest_hash)

    def test_loader_requires_a_signed_outer_binding_to_the_exact_root_child_and_role(self):
        repository, manifest, blobs = fixture_repository()
        source = blobs[manifest.source_registry_hash]
        repository.blobs[source.registry_hash] = replace(
            source, declared_registry_manifest_hash="0" * 64
        )
        with self.assertRaisesRegex(ValueError, "declared root"):
            FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)

        repository, manifest, blobs = fixture_repository()
        source = blobs[manifest.source_registry_hash]
        repository.blobs[source.registry_hash] = replace(source, binding_signature="tampered")
        with self.assertRaisesRegex(ValueError, "binding.*signature"):
            FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)

        repository, manifest, _ = fixture_repository()
        with self.assertRaisesRegex(ValueError, "signature"):
            FormalRegistryBundleLoader(repository, RaisingVerifier()).load(manifest.manifest_hash)

    def test_official_child_approval_requires_an_exact_trimmed_string(self):
        repository, manifest, blobs = fixture_repository()
        root = json.loads(manifest.canonical_json)
        root["purpose"] = "official"
        root["approval_id"] = "release-1"
        official = FormalRegistryManifest.from_signed_bytes(
            canonical_bytes(root), "fixture-signature", "fixture-key", AcceptingVerifier()
        )

        class AlwaysEqualApproval:
            def __eq__(self, _other):
                return True

            def __ne__(self, _other):
                return False

        official_blobs = {
            registry_hash: replace(
                blob,
                approval_id="release-1",
                declared_registry_manifest_hash=official.manifest_hash,
            )
            for registry_hash, blob in blobs.items()
        }
        source_hash = official.source_registry_hash
        official_blobs[source_hash] = replace(
            official_blobs[source_hash], approval_id=AlwaysEqualApproval()
        )
        repository = InMemoryRepository(official, official_blobs)

        with self.assertRaisesRegex(ValueError, "approval"):
            FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(official.manifest_hash)

    def test_outer_binding_signature_covers_canonical_root_child_and_role_bytes(self):
        repository, manifest, blobs, verifier = strict_binding_fixture()
        FormalRegistryBundleLoader(repository, verifier).load(manifest.manifest_hash)
        source = blobs[manifest.source_registry_hash]
        wrong_bindings = (
            binding_bytes(source.registry_hash, "0" * 64, "source"),
            binding_bytes("0" * 64, manifest.manifest_hash, "source"),
            binding_bytes(source.registry_hash, manifest.manifest_hash, "mapping"),
        )
        for wrong_binding in wrong_bindings:
            with self.subTest(wrong_binding=wrong_binding):
                repository.blobs[source.registry_hash] = replace(
                    source, binding_signature=hashlib.sha256(wrong_binding).hexdigest()
                )
                with self.assertRaisesRegex(ValueError, "binding.*signature"):
                    FormalRegistryBundleLoader(repository, verifier).load(manifest.manifest_hash)
                repository.blobs[source.registry_hash] = source

    def test_root_rejects_noncanonical_and_official_requires_trimmed_approval(self):
        repository, manifest, _ = fixture_repository()
        pretty = json.dumps(json.loads(manifest.canonical_json), indent=2).encode()
        with self.assertRaisesRegex(ValueError, "canonical"):
            FormalRegistryManifest.from_signed_bytes(
                pretty, "fixture-signature", "fixture-key", AcceptingVerifier()
            )
        duplicate = manifest.canonical_json.replace(
            b'"purpose":"test",', b'"purpose":"test","purpose":"test",', 1
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            FormalRegistryManifest.from_signed_bytes(
                duplicate, "fixture-signature", "fixture-key", AcceptingVerifier()
            )
        official = json.loads(manifest.canonical_json)
        official["purpose"] = "official"
        official["approval_id"] = " release "
        with self.assertRaisesRegex(ValueError, "approval"):
            FormalRegistryManifest.from_signed_bytes(
                canonical_bytes(official), "fixture-signature", "fixture-key", AcceptingVerifier()
            )

    def test_release_gates_reject_direct_or_fabricated_manifest_and_bundle_objects(self):
        hashes = [f"{index:064x}" for index in range(1, 10)]
        with self.assertRaisesRegex(ValueError, "from_signed_bytes"):
            FormalRegistryManifest(
                "a" * 64,
                "official",
                "release-1",
                b"{}",
                "signature",
                "fixture-key",
                *hashes,
            )
        fabricated_manifest = object.__new__(FormalRegistryManifest)
        object.__setattr__(fabricated_manifest, "purpose", "official")
        object.__setattr__(fabricated_manifest, "approval_id", "release-1")
        with self.assertRaisesRegex(ValueError, "verified"):
            fabricated_manifest.require_official()

        repository, manifest, _ = fixture_repository()
        with self.assertRaises(ValueError):
            replace(manifest, signature="tampered")
        with self.assertRaisesRegex(ValueError, "loader"):
            VerifiedRegistryBundle(manifest, {})
        fabricated_bundle = object.__new__(VerifiedRegistryBundle)
        object.__setattr__(fabricated_bundle, "manifest", fabricated_manifest)
        object.__setattr__(fabricated_bundle, "blobs", {})
        with self.assertRaisesRegex(ValueError, "verified"):
            fabricated_bundle.require_official()
        with self.assertRaisesRegex(ValueError, "verified"):
            fabricated_bundle.blob("source")

    def test_verified_construction_capability_is_not_exposed_on_public_objects(self):
        repository, manifest, _ = fixture_repository()
        bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(
            manifest.manifest_hash
        )
        with self.assertRaises(AttributeError):
            getattr(manifest, "_verified_provenance")
        with self.assertRaises(AttributeError):
            getattr(bundle, "_verified_provenance")
        with self.assertRaisesRegex(ValueError, "from_signed_bytes"):
            FormalRegistryManifest(_verified_token=object())
        with self.assertRaisesRegex(ValueError, "loader"):
            VerifiedRegistryBundle(manifest, {}, _verified_token=object())

    def test_trusted_manifest_and_bundle_factories_are_not_module_capabilities(self):
        for name in (
            "_construct_verified_manifest",
            "_remember_verified_manifest",
            "_has_verified_manifest",
            "_construct_verified_bundle",
            "_remember_verified_bundle",
            "_has_verified_bundle",
            "_VERIFIED_MANIFESTS",
            "_VERIFIED_BUNDLES",
            "_make_trusted_registry_types",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(registry_manifest_module, name))

        _, manifest, _ = fixture_repository()
        forged = object.__new__(FormalRegistryManifest)
        for field in (
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
        ):
            object.__setattr__(forged, field, getattr(manifest, field))
        with self.assertRaisesRegex(ValueError, "verified"):
            forged.assert_member_hashes(
                **{f"{role}_registry_hash": getattr(forged, f"{role}_registry_hash") for role in ROLES}
            )

    def test_manifest_provenance_rejects_object_setattr_mutation(self):
        _, manifest, _ = fixture_repository()
        object.__setattr__(manifest, "purpose", "official")
        object.__setattr__(manifest, "approval_id", "release-1")
        member_hashes = {
            f"{role}_registry_hash": getattr(manifest, f"{role}_registry_hash")
            for role in ROLES
        }
        with self.assertRaisesRegex(ValueError, "verified"):
            manifest.require_official()
        with self.assertRaisesRegex(ValueError, "verified"):
            manifest.assert_member_hashes(**member_hashes)

    def test_instance_guard_injection_cannot_bypass_manifest_or_bundle_seals(self):
        repository, manifest, _ = fixture_repository()
        try:
            object.__setattr__(manifest, "_require_verified", lambda: None)
        except AttributeError:
            pass
        object.__setattr__(manifest, "purpose", "official")
        object.__setattr__(manifest, "approval_id", "release-1")
        member_hashes = {
            f"{role}_registry_hash": getattr(manifest, f"{role}_registry_hash")
            for role in ROLES
        }
        with self.assertRaisesRegex(ValueError, "verified"):
            manifest.require_official()
        with self.assertRaisesRegex(ValueError, "verified"):
            manifest.assert_member_hashes(**member_hashes)

        repository, manifest, _ = fixture_repository()
        bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(
            manifest.manifest_hash
        )
        source = bundle.blob("source")
        try:
            object.__setattr__(bundle, "_require_verified", lambda: None)
        except AttributeError:
            pass
        object.__setattr__(bundle, "blobs", {"source": source})
        with self.assertRaisesRegex(ValueError, "verified"):
            bundle.blob("source")
        with self.assertRaisesRegex(ValueError, "verified"):
            bundle.require_official()

    def test_bundle_provenance_rejects_manifest_mapping_and_blob_mutation(self):
        repository, manifest, _ = fixture_repository()
        bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(
            manifest.manifest_hash
        )
        _, replacement_manifest, _ = fixture_repository()
        object.__setattr__(bundle, "manifest", replacement_manifest)
        with self.assertRaisesRegex(ValueError, "verified"):
            bundle.blob("source")

        repository, manifest, _ = fixture_repository()
        bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(
            manifest.manifest_hash
        )
        object.__setattr__(bundle, "blobs", {})
        with self.assertRaisesRegex(ValueError, "verified"):
            bundle.blob("source")

        repository, manifest, _ = fixture_repository()
        bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(
            manifest.manifest_hash
        )
        source = bundle.blob("source")
        object.__setattr__(source, "binding_signature", "tampered")
        with self.assertRaisesRegex(ValueError, "verified"):
            bundle.blob("source")


if __name__ == "__main__":
    unittest.main()
