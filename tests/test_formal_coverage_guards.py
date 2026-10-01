import copy
import pickle
import unittest
import weakref

from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor


class CoverageGuardTests(unittest.TestCase):
    def setUp(self):
        self.r = CoverageRequirement("f", "SH600000", "financial", "s", "2025", "SH")
        self.a = FormalCoverageAuditor(production_contract={"approved": True}, repository_validators={"financial": lambda *_: True})
        self.row = dict(self.r.to_dict(), coverage_class="verified_complete", authenticated=True,
                        units_ok=True, parser_mapping_ok=True, source="official",
                        dataset="annual_report", request_fingerprint="request",
                        selected_snapshot_id="snapshot", content_sha256="content",
                        manifest_sha256="manifest", parser_id="parser", parser_version="1",
                        mapping_version="1", published_at_utc="2026-08-01T00:00:00+00:00",
                        effective_at_utc="2026-08-01T00:00:00+00:00",
                        verification_state="verified", temporal_state="visible",
                        observed_units=[])
        self.m = self.a.audit([self.r], [self.row])

    def test_registry_purpose_approval_signature_temporal_units_parser_and_mapping_block(self):
        cases = [
            ({"coverage_class": "verified_complete", "registry_purpose": "wrong"}, "blocked_registry"),
            ({"coverage_class": "verified_complete", "signature_ok": False}, "blocked_integrity"),
            ({"coverage_class": "verified_complete", "effective_at_utc": "2026-09-01T00:00:00+00:00"}, "blocked_temporal"),
            ({"coverage_class": "verified_complete", "units_ok": False}, "blocked_integrity"),
            ({"coverage_class": "verified_complete", "parser_mapping_ok": False}, "blocked_integrity"),
        ]
        for updates, expected in cases:
            row = dict(self.row, **updates)
            if expected == "blocked_registry":
                m = self.a.audit([self.r], [row], registry={"approved": False})
                self.assertIn("registry_not_approved", m.blockers)
            else:
                self.assertEqual(self.a.audit([self.r], [row]).rows[0]["coverage_class"], expected)

    def test_ambiguous_duplicate_source_correction_and_stale_mismatch_block(self):
        duplicate = self.a.audit([self.r], [self.row, self.row])
        self.assertEqual(duplicate.rows[0]["coverage_class"], "blocked_ambiguous")
        corrected = self.a.audit([self.r], [dict(self.row, source_correction=True)])
        self.assertEqual(corrected.rows[0]["coverage_class"], "blocked_ambiguous")

    def test_missing_production_contract_preview_can_be_audited_but_official_is_blocked(self):
        a = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True})
        m = a.audit([self.r], [self.row])
        m.require_preview_ready()
        with self.assertRaisesRegex(ValueError, "production contract"):
            m.require_official_ready()

    def test_unapproved_or_nonofficial_contract_cannot_grant_official_readiness(self):
        for contract in ({"approved": False}, {"approved": True, "purpose": "test"},
                         {"approved": True, "purpose": "official"}, object()):
            with self.subTest(contract=contract):
                auditor = FormalCoverageAuditor(
                    production_contract=contract,
                    repository_validators={"financial": lambda *_: True},
                )
                manifest = auditor.audit([self.r], [self.row])
                manifest.require_preview_ready()
                with self.assertRaisesRegex(ValueError, "production contract"):
                    manifest.require_official_ready()

    def test_approved_official_contract_identity_is_bound_to_manifest_hash(self):
        def audit(root):
            return FormalCoverageAuditor(
                production_contract={"approved": True, "purpose": "official",
                                     "signing_identity": "production-signer",
                                     "root_manifest_hash": root},
                repository_validators={"financial": lambda *_: True},
            ).audit([self.r], [self.row])

        first, second = audit("root-a"), audit("root-b")
        first.require_official_ready()
        self.assertNotEqual(first.manifest_hash, second.manifest_hash)

    def test_registry_disapproval_blocks_member_class_and_preview_gate(self):
        manifest = self.a.audit([self.r], [self.row], registry={"approved": False})
        self.assertEqual(manifest.rows[0]["coverage_class"], "blocked_registry")
        with self.assertRaises(ValueError):
            manifest.require_preview_ready()

    def test_repository_validator_must_return_exact_true(self):
        for verdict in (None, 1, {"verified": True}):
            with self.subTest(verdict=verdict):
                auditor = FormalCoverageAuditor(
                    repository_validators={"financial": lambda *_: verdict},
                )
                manifest = auditor.audit([self.r], [self.row])
                self.assertEqual(manifest.rows[0]["coverage_class"], "blocked_integrity")

    def test_coverage_proof_rejects_plain_construction_copy_pickle_weakref_redirect_method_replacement_and_revocation(self):
        with self.assertRaises(TypeError):
            from ashare_pipeline.formal_coverage_manifest import VerifiedCoverageManifest
            VerifiedCoverageManifest()
        forged = object.__new__(VerifiedCoverageManifest)
        with self.assertRaises(ValueError): forged.require_verified()
        with self.assertRaises(TypeError): copy.copy(self.m)
        with self.assertRaises(TypeError): copy.deepcopy(self.m)
        with self.assertRaises(TypeError): pickle.dumps(self.m)
        with self.assertRaises(ValueError): weakref.proxy(forged).require_verified()
        original = self.m.require_verified
        with self.assertRaises(AttributeError):
            self.m.require_verified = lambda: None
        with self.assertRaises(TypeError):
            VerifiedCoverageManifest.require_verified = lambda self: None
        self.assertIsNotNone(original)
        self.a.revoke(self.m)
        with self.assertRaises(ValueError): self.m.require_verified()

    def test_old_v1_v2_plain_objects_are_not_manifests(self):
        for old in ({"schema_version": "v1"}, {"schema_version": "v2"}):
            with self.assertRaises(AttributeError): old.require_verified()


if __name__ == "__main__": unittest.main()
