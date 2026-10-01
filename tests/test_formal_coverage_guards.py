import copy
import pickle
import unittest

from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor


class CoverageGuardTests(unittest.TestCase):
    def setUp(self):
        self.r = CoverageRequirement("f", "SH600000", "financial", "s", "2025", "SH")
        self.a = FormalCoverageAuditor(production_contract={"approved": True}, repository_validators={"financial": lambda *_: True})
        self.row = dict(self.r.to_dict(), coverage_class="verified_complete", authenticated=True, units_ok=True, parser_mapping_ok=True)
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

    def test_coverage_proof_rejects_plain_construction_copy_pickle_weakref_redirect_method_replacement_and_revocation(self):
        with self.assertRaises(TypeError):
            from ashare_pipeline.formal_coverage_manifest import VerifiedCoverageManifest
            VerifiedCoverageManifest()
        with self.assertRaises(TypeError): copy.copy(self.m)
        with self.assertRaises(TypeError): pickle.dumps(self.m)
        original = self.m.require_verified
        with self.assertRaises(AttributeError):
            self.m.require_verified = lambda: None
        self.assertIsNotNone(original)

    def test_old_v1_v2_plain_objects_are_not_manifests(self):
        for old in ({"schema_version": "v1"}, {"schema_version": "v2"}):
            with self.assertRaises(AttributeError): old.require_verified()


if __name__ == "__main__": unittest.main()
