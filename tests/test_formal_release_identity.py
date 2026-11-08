"""Release content identity is deterministic data, never publication authority."""
import hashlib
import unittest
from ashare_pipeline import formal_release_types as release

class ReleaseIdentityTests(unittest.TestCase):
    def values(self):
        return dict(contract_version="V3", input_manifest_hash="a"*64,
                    result_hash="b"*64, renderer_version="renderer-v1")

    def test_exact_canonical_content_and_full_release_id(self):
        raw = release.canonical_release_identity_bytes(**self.values())
        expected = ('{"contract_version":"V3","freeze_at_utc":"2026-08-31T07:00:00+00:00",'
                    '"input_manifest_hash":"' + "a"*64 + '","renderer_version":"renderer-v1",'
                    '"result_hash":"' + "b"*64 + '","schema":"formal-release-identity-v1"}').encode()
        self.assertEqual(raw, expected)
        self.assertEqual(release.release_id_for_content(**self.values()),
                         "20260831-formal-v3-" + hashlib.sha256(expected).hexdigest())

    def test_each_content_dependency_changes_identity(self):
        original = release.release_id_for_content(**self.values())
        for name, value in (("contract_version", "V3-revised"),
                            ("input_manifest_hash", "c"*64), ("result_hash", "d"*64),
                            ("renderer_version", "renderer-v2")):
            with self.subTest(field=name):
                args=self.values(); args[name]=value
                self.assertNotEqual(release.release_id_for_content(**args), original)

    def test_run_and_operational_metadata_cannot_enter_identity(self):
        for field in ("run_id", "created_at", "validation_hash", "freeze_at_utc"):
            with self.subTest(field=field), self.assertRaises(TypeError):
                release.canonical_release_identity_bytes(**self.values(), **{field:"override"})
        self.assertEqual(release.release_id_for_content(**self.values()),
                         release.release_id_for_content(**dict(reversed(list(self.values().items())))))

    def test_invalid_content_is_rejected_before_hashing(self):
        for name, value in (("contract_version", ""), ("renderer_version", " x"),
                            ("renderer_version", True), ("input_manifest_hash", "A"*64),
                            ("result_hash", "bad"), ("result_hash", b"b"*64)):
            with self.subTest(field=name,value=value), self.assertRaises(ValueError):
                args=self.values(); args[name]=value
                release.release_id_for_content(**args)
