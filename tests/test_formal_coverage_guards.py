import copy
import gc
import hashlib
import json
import pickle
from pathlib import Path
import sqlite3
import tempfile
import unittest
import weakref

from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor
from ashare_pipeline.formal_registry_manifest import FormalRegistryBundleLoader
from ashare_pipeline.formal_universe import FormalUniverseIngestor
from tests.test_formal_coverage_manifest import good
from tests.test_formal_registry_manifest import AcceptingVerifier, fixture_repository
from tests.test_formal_universe import verified_listing_documents


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


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

    def test_caller_supplied_contract_identity_does_not_authorize_or_bind_manifest(self):
        def audit(root):
            return FormalCoverageAuditor(
                production_contract={"approved": True, "purpose": "official",
                                     "signing_identity": "production-signer",
                                     "root_manifest_hash": root},
                repository_validators={"financial": lambda *_: True},
            ).audit([self.r], [self.row])

        first, second = audit("root-a"), audit("root-b")
        with self.assertRaisesRegex(ValueError, "authenticated"):
            first.require_official_ready()
        self.assertEqual(first.manifest_hash, second.manifest_hash)

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

    def test_coverage_proof_seal_does_not_keep_abandoned_manifest_alive(self):
        manifest = self.a.audit([self.r], [self.row])
        reference = weakref.ref(manifest)
        del manifest
        gc.collect()
        self.assertIsNone(reference())


class OfficialCoverageBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_path = Path(self.temp.name)
        repository, manifest, _ = fixture_repository(purpose="official")
        self.registry_repository = repository
        self.verifier = AcceptingVerifier()
        self.registry_loader = FormalRegistryBundleLoader(repository, self.verifier)
        self.bundle = self.registry_loader.load(manifest.manifest_hash)
        self.frozen = FormalUniverseIngestor().build(
            "2026-08-31T07:00:00+00:00", manifest.manifest_hash,
            verified_listing_documents("SH", "SZ", "BJ"),
        )
        self.requirements = [CoverageRequirement(self.frozen.frozen_input_hash, member.security_id,
                                                 "financial", "selector", "2025", member.exchange,
                                                 ("CNY",)) for member in self.frozen.members]
        self.records = [good(req) for req in self.requirements]
        self.db_path = self.temp_path / "formal.db"
        connection = sqlite3.connect(self.db_path)
        connection.close()
        self.status_path = self.temp_path / "status.json"
        self.status_path.write_text(json.dumps({
            "generated_at_utc": "2026-09-01T00:00:00+00:00",
            "schema_version": 7,
            "db_sha256": hashlib.sha256(self.db_path.read_bytes()).hexdigest(),
        }), encoding="utf-8")
        self.contract_wire = {
            "schema_version": "formal-coverage-contract-v1",
            "purpose": "official", "approval_id": manifest.approval_id,
            "signing_identity": manifest.key_id,
            "registry_manifest_hash": manifest.manifest_hash,
            "frozen_input_hash": self.frozen.frozen_input_hash,
            "requirements": [req.to_dict() for req in self.requirements],
            "domain_owners": {"financial": "formal_snapshot_repository"},
            "expected_schema_version": 7, "report_period": "2025",
            "query_version": "coverage-v1",
        }
        self.contract = self.signed_contract(self.contract_wire)
        self.calls = []

    @staticmethod
    def signed_contract(wire, signature="fixture-signature"):
        return {"canonical_json": canonical(wire), "signature": signature,
                "key_id": "fixture-key"}

    def validate(self, req, record):
        self.calls.append(req["security_id"])
        return {"domain": req["domain"], "owner": "formal_snapshot_repository",
                "requirement_hash": digest(req), "record_hash": digest(record),
                "evidence_hash": "a" * 64}

    def audit(self, *, requirements=None, records=None, contract=None, registry_bundle=None,
              validators=None, frozen_universe=None, db_path=None, status_path=None):
        return FormalCoverageAuditor(repository_validators={"financial": self.validate} if validators is None else validators).audit(
            self.requirements if requirements is None else requirements,
            self.records if records is None else records,
            production_contract=self.contract if contract is None else contract,
            contract_verifier=self.verifier,
            registry_loader=self.registry_loader,
            frozen_universe=self.frozen if frozen_universe is None else frozen_universe,
            registry_bundle=self.bundle if registry_bundle is None else registry_bundle,
            workspace_root=Path(__file__).resolve().parents[1],
            db_path=self.db_path if db_path is None else db_path,
            status_path=self.status_path if status_path is None else status_path,
        )

    def test_signed_root_exact_requirement_enumeration_and_provenance_can_be_ready(self):
        result = self.audit()
        result.require_official_ready()
        self.assertEqual(sorted(set(self.calls)), sorted(req.security_id for req in self.requirements))
        self.assertEqual(len(result.rows), len(self.frozen.members))
        self.assertTrue(all("repository_provenance" in row for row in result.rows))
        for field in ("workspace_revision", "db_path", "db_sha256", "db_schema_versions",
                      "expected_schema_version", "status_generated_at_utc", "universe_source",
                      "universe_records_hash", "frozen_input_hash", "registry_manifest_hash",
                      "member_count", "member_count_by_exchange", "report_period", "query_version"):
            with self.subTest(field=field): self.assertIn(field, result.to_dict())

    def test_requirement_omission_and_cross_root_identity_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "requirements"):
            self.audit(requirements=self.requirements[:-1])
        wrong = [CoverageRequirement("f" * 64, req.security_id, req.domain,
                                     req.selector_hash, req.period_or_window,
                                     req.exchange, req.expected_units) for req in self.requirements]
        with self.assertRaisesRegex(ValueError, "frozen"):
            self.audit(requirements=wrong)
        incomplete = dict(self.contract_wire, requirements=[self.requirements[0].to_dict()])
        with self.assertRaisesRegex(ValueError, "member"):
            self.audit(contract=self.signed_contract(incomplete))

    def test_plain_or_unapproved_registry_and_unsigned_contract_cannot_authorize_official(self):
        with self.assertRaisesRegex(ValueError, "registry"):
            self.audit(registry_bundle={"approved": True, "purpose": "official"})
        with self.assertRaisesRegex(ValueError, "signature"):
            self.audit(contract=self.signed_contract(self.contract_wire, signature="invalid"))
        raw = dict(self.contract_wire, purpose="test")
        with self.assertRaisesRegex(ValueError, "purpose"):
            self.audit(contract=self.signed_contract(raw))
        test_repository, test_manifest, _ = fixture_repository(purpose="test")
        test_bundle = FormalRegistryBundleLoader(test_repository, AcceptingVerifier()).load(test_manifest.manifest_hash)
        with self.assertRaisesRegex(ValueError, "official"):
            self.audit(registry_bundle=test_bundle)

    def test_every_domain_callback_must_return_matching_repository_provenance(self):
        with self.assertRaisesRegex(ValueError, "repository"):
            self.audit(validators={})
        def wrong_owner(req, record):
            return dict(self.validate(req, record), owner="wrong_repository")
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.audit(validators={"financial": wrong_owner})
        def wrong_record(req, record):
            return dict(self.validate(req, record), record_hash="b" * 64)
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.audit(validators={"financial": wrong_record})

    def test_signed_catalog_enumerates_each_domain_and_invokes_each_owner(self):
        extra = [CoverageRequirement(self.frozen.frozen_input_hash, member.security_id,
                                     "context", "context-selector", "2025", member.exchange)
                 for member in self.frozen.members]
        requirements = self.requirements + extra
        records = self.records + [good(req) for req in extra]
        contract = dict(self.contract_wire,
                        requirements=[req.to_dict() for req in requirements],
                        domain_owners={"financial": "formal_snapshot_repository",
                                       "context": "formal_context_repository"})
        calls = []
        def context_validator(req, record):
            calls.append(req["security_id"])
            return {"domain": "context", "owner": "formal_context_repository",
                    "requirement_hash": digest(req), "record_hash": digest(record),
                    "evidence_hash": "b" * 64}
        with self.assertRaisesRegex(ValueError, "repository"):
            self.audit(requirements=requirements, records=records,
                       contract=self.signed_contract(contract),
                       validators={"financial": self.validate})
        result = self.audit(requirements=requirements, records=records,
                            contract=self.signed_contract(contract),
                            validators={"financial": self.validate, "context": context_validator})
        result.require_official_ready()
        self.assertEqual(set(calls), {member.security_id for member in self.frozen.members})
        with self.assertRaisesRegex(ValueError, "requirements"):
            self.audit(requirements=requirements[:-1], records=records,
                       contract=self.signed_contract(contract),
                       validators={"financial": self.validate, "context": context_validator})

    def test_db_and_status_are_read_only_bound_and_rechecked_at_gate(self):
        result = self.audit()
        result.require_official_ready()
        with self.db_path.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "database"):
            result.require_official_ready()

    def test_stale_status_blocks_audit_before_manifest_is_minted(self):
        self.status_path.write_text(json.dumps({
            "generated_at_utc": "2026-09-01T00:00:00+00:00",
            "schema_version": 7,
            "db_sha256": "0" * 64,
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "database status"):
            self.audit()

    def test_database_sidecar_changes_invalidate_official_gate(self):
        result = self.audit()
        result.require_official_ready()
        wal_path = self.db_path.with_name(self.db_path.name + "-wal")
        wal_path.write_bytes(b"new-uncheckpointed-content")
        with self.assertRaisesRegex(ValueError, "database"):
            result.require_official_ready()

    def test_official_gate_rechecks_repository_and_registry_proofs(self):
        live = {"accept": True}
        def validator(req, record):
            if not live["accept"]:
                raise ValueError("repository changed")
            return self.validate(req, record)
        result = self.audit(validators={"financial": validator})
        result.require_official_ready()
        live["accept"] = False
        with self.assertRaisesRegex(ValueError, "repository"):
            result.require_official_ready()

    def test_official_gate_reloads_registry_from_read_only_repository(self):
        result = self.audit()
        result.require_official_ready()
        object.__setattr__(self.registry_repository.manifest, "signature", "tampered")
        with self.assertRaisesRegex(ValueError, "registry"):
            result.require_official_ready()


if __name__ == "__main__": unittest.main()
