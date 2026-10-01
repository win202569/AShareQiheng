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

import ashare_pipeline.formal_coverage_manifest as coverage_module
from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor
from ashare_pipeline.formal_registry_manifest import FormalRegistryBundleLoader
from ashare_pipeline.formal_snapshot_repository import FormalSnapshotRepository
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore
from ashare_pipeline.formal_evidence import OfficialRequest
from ashare_pipeline.formal_universe import FormalUniverseIngestor
from ashare_pipeline.state_store import StateStore
from tests.test_formal_coverage_manifest import good
from tests.test_formal_registry_manifest import AcceptingVerifier, fixture_repository
from tests.test_formal_universe import verified_listing_documents
from tests.test_formal_snapshot_repository import cninfo_fetch, verified
from tests.test_formal_feature_contract import formal_fact


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def db_generation(path):
    return {suffix: (hashlib.sha256(candidate.read_bytes()).hexdigest()
                     if candidate.is_file() else None)
            for suffix in ("", "-wal", "-shm")
            for candidate in (path.with_name(path.name + suffix),)}


class CoverageGuardTests(unittest.TestCase):
    def setUp(self):
        self.r = CoverageRequirement("f", "SH600000", "financial", "s", "2025", "SH")
        self.a = FormalCoverageAuditor(production_contract={"approved": True}, repository_validators={"financial": lambda *_: True})
        self.row = dict(self.r.to_dict(), coverage_class="verified_complete", authenticated=True,
                        units_ok=True, parser_mapping_ok=True, signature_ok=True,
                        hash_ok=True, evidence_hashes={"content": "4" * 64},
                        source="official", dataset="annual_report", request_fingerprint="1" * 64,
                        selected_snapshot_id="snapshot", content_sha256="2" * 64,
                        manifest_sha256="3" * 64, parser_id="parser", parser_version="1",
                        mapping_version="1", published_at_utc="2026-08-01T00:00:00+00:00",
                        effective_at_utc="2026-08-01T00:00:00+00:00",
                        source_updated_at_utc="2026-08-01T00:00:00+00:00",
                        captured_at_utc="2026-08-02T00:00:00+00:00",
                        refresh_generation="generation-1", task_id="task-1",
                        collection_state="complete",
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

    def test_revoked_proof_cannot_be_reactivated_through_module_seal_state(self):
        manifest = self.a.audit([self.r], [self.row])
        self.a.revoke(manifest)
        for name in ("_SEALS", "_LIVE_CONTEXTS", "_seal"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(coverage_module, name))
        with self.assertRaises(ValueError):
            manifest.require_verified()

    def test_signed_applicability_and_partial_required_units_fail_closed(self):
        not_applicable = dict(self.row, coverage_class="not_applicable_signed")
        manifest = self.a.audit([self.r], [not_applicable])
        self.assertEqual(manifest.rows[0]["coverage_class"], "blocked_dependency")
        partial = dict(self.row, coverage_class="verified_partial",
                       expected_units=["CNY"], observed_units=[])
        required = CoverageRequirement("f", "SH600000", "financial", "s", "2025", "SH", ("CNY",))
        manifest = self.a.audit([required], [partial])
        with self.assertRaises(ValueError):
            manifest.require_preview_ready()

    def test_caller_applicability_flags_and_permissive_callback_do_not_authorize_preview(self):
        claimed = dict(self.row, coverage_class="not_applicable_signed",
                       explicit_source_statement=True,
                       applicability_rule_hash="a" * 64)
        for callbacks in ({}, {"financial": lambda *_: True}):
            with self.subTest(callbacks=bool(callbacks)):
                manifest = FormalCoverageAuditor(repository_validators=callbacks).audit(
                    [self.r], [claimed])
                with self.assertRaisesRegex(ValueError, "coverage preview blocked"):
                    manifest.require_preview_ready()

    def test_verified_lineage_hashes_and_publication_cutoff_are_required(self):
        for field in ("refresh_generation", "task_id", "collection_state",
                      "captured_at_utc", "source_updated_at_utc"):
            with self.subTest(field=field):
                row = dict(self.row); row.pop(field, None)
                manifest = self.a.audit([self.r], [row])
                self.assertEqual(manifest.rows[0]["coverage_class"], "blocked_integrity")
        for field in ("content_sha256", "manifest_sha256", "request_fingerprint"):
            with self.subTest(field=field):
                manifest = self.a.audit([self.r], [dict(self.row, **{field: "not-a-hash"})])
                self.assertEqual(manifest.rows[0]["coverage_class"], "blocked_integrity")
        future = dict(self.row, published_at_utc="2026-09-01T00:00:00+00:00")
        self.assertEqual(self.a.audit([self.r], [future]).rows[0]["coverage_class"],
                         "blocked_temporal")


class OfficialCoverageBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_path = Path(self.temp.name)
        repository, manifest, _ = fixture_repository(purpose="official")
        self.verifier = AcceptingVerifier()
        self.db_path = self.temp_path / "formal.db"
        self.raw_store = FormalSnapshotStore(self.temp_path / "raw")
        self.registry_repository = StateStore(
            self.db_path, formal_snapshot_store=self.raw_store,
            registry_signature_verifier=self.verifier)
        self.registry_repository.initialize()
        for blob in repository.blobs.values():
            self.registry_repository.put_formal_registry_blob(blob)
        self.registry_repository.put_formal_registry_manifest(manifest)
        self.registry_loader = FormalRegistryBundleLoader(self.registry_repository, self.verifier)
        self.bundle = self.registry_loader.load(manifest.manifest_hash)
        self.snapshot_repository = FormalSnapshotRepository(self.raw_store.root, self.registry_repository)
        self.frozen = FormalUniverseIngestor().build(
            "2026-08-31T07:00:00+00:00", manifest.manifest_hash,
            verified_listing_documents("SH", "SZ", "BJ"),
        )
        self.requirements = [CoverageRequirement(self.frozen.frozen_input_hash, member.security_id,
                                                 "financial", "selector", "2025-12-31", member.exchange,
                                                 ("CNY",)) for member in self.frozen.members]
        self.records = []
        for req in self.requirements:
            key = req.security_id
            generation = f"coverage-{key}"
            task_id = self.registry_repository.enqueue_formal_task(
                "formal_statement", key, generation, {"key": key})
            leased = self.registry_repository.lease_next_formal_task(
                ("formal_statement",), f"worker-{key}", 300)
            self.assertEqual(leased["id"], task_id)
            fetch = cninfo_fetch(
                raw_bytes=f"verified coverage evidence {key}".encode(),
                refresh_generation=generation,
                published_at_utc="2026-08-20T08:00:00+00:00",
                source_updated_at_utc="2026-08-20T08:00:00+00:00",
                captured_at_utc="2026-08-21T08:00:00+00:00",
                request=OfficialRequest("cninfo", "annual_report", key, "2025-12-31", req.exchange),
            )
            ref = self.snapshot_repository.persist_verified(
                fetch, verified(fetch), producing_task_id=task_id,
                worker_id=f"worker-{key}")
            self.registry_repository.insert_formal_financial_facts((formal_fact(
                security_id=key, period_end="2025-12-31",
                published_at_utc=ref.published_at_utc,
                published_precision=ref.published_precision,
                effective_at_utc=ref.effective_at_utc,
                effective_time_evidence_hash=ref.effective_time_evidence_hash,
                source_updated_at_utc=ref.source_updated_at_utc,
                captured_at_utc=ref.captured_at_utc,
                source_snapshot_id=ref.snapshot_id,
                source_content_sha256=ref.content_sha256,
                source_refresh_generation=ref.refresh_generation,
                source_producing_task_id=ref.producing_task_id,
                parser_id=ref.parser_id, parser_version=ref.parser_version,
                mapping_version=ref.mapping_version,
            ),))
            self.records.append(dict(good(req),
                source=ref.source, dataset=ref.dataset,
                request_fingerprint=ref.request_fingerprint,
                selected_snapshot_id=ref.snapshot_id,
                content_sha256=ref.content_sha256, manifest_sha256=ref.manifest_sha256,
                parser_id=ref.parser_id, parser_version=ref.parser_version,
                mapping_version=ref.mapping_version,
                published_at_utc=ref.published_at_utc,
                effective_at_utc=ref.effective_at_utc,
                source_updated_at_utc=ref.source_updated_at_utc,
                captured_at_utc=ref.captured_at_utc,
                refresh_generation=ref.refresh_generation, task_id=ref.producing_task_id,
                evidence_hashes={"content": ref.content_sha256}))
        self.status_path = self.temp_path / "status.json"
        self.status_path.write_text(json.dumps({
            "generated_at_utc": "2026-09-01T00:00:00+00:00",
            "schema_version": 7,
            "db_sha256": hashlib.sha256(self.db_path.read_bytes()).hexdigest(),
            "db_generation_hash": digest(db_generation(self.db_path)),
            "schema_versions": [2, 3, 4, 5, 6, 7],
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
        ref = self.snapshot_repository.get_verified_by_manifest(record["manifest_sha256"])
        facts = tuple(fact for fact in self.registry_repository.list_formal_financial_facts(
            security_id=req["security_id"])
            if fact.source_snapshot_id == ref.snapshot_id
            and fact.period_end == req["period_or_window"])
        evidence_hash = digest({"manifest_sha256": ref.manifest_sha256,
                                "raw_sha256": hashlib.sha256(
                                    self.snapshot_repository.read_verified_raw(ref)).hexdigest(),
                                "facts": [fact.to_dict() for fact in facts]})
        return {"domain": req["domain"], "owner": "formal_snapshot_repository",
                "requirement_hash": digest(req),
                "record_hash": digest({key: value for key, value in record.items()
                                       if key not in {"rechecked_at_utc", "timing_diagnostics"}}),
                "evidence_hash": evidence_hash}

    def audit(self, *, requirements=None, records=None, contract=None, registry_bundle=None,
              validators=None, frozen_universe=None, db_path=None, status_path=None):
        return FormalCoverageAuditor(repository_validators={"financial": self.validate} if validators is None else validators).audit(
            self.requirements if requirements is None else requirements,
            self.records if records is None else records,
            production_contract=self.contract if contract is None else contract,
            contract_verifier=self.verifier,
            registry_loader=self.registry_loader,
            snapshot_repository=self.snapshot_repository,
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
                    "requirement_hash": digest(req),
                    "record_hash": digest({key: value for key, value in record.items()
                                           if key not in {"rechecked_at_utc", "timing_diagnostics"}}),
                    "evidence_hash": "b" * 64}
        with self.assertRaisesRegex(ValueError, "repository"):
            self.audit(requirements=requirements, records=records,
                       contract=self.signed_contract(contract),
                       validators={"financial": self.validate})
        with self.assertRaisesRegex(ValueError, "repository owner"):
            self.audit(requirements=requirements, records=records,
                       contract=self.signed_contract(contract),
                       validators={"financial": self.validate, "context": context_validator})
        self.assertEqual(calls, [])
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

    def test_empty_sqlite_schema_is_not_a_formal_state_store(self):
        empty_db = self.temp_path / "empty.sqlite3"
        sqlite3.connect(empty_db).close()
        empty_status = self.temp_path / "empty-status.json"
        empty_status.write_text(json.dumps({
            "generated_at_utc": "2026-09-01T00:00:00+00:00",
            "schema_version": 7,
            "db_sha256": hashlib.sha256(empty_db.read_bytes()).hexdigest(),
            "db_generation_hash": digest(db_generation(empty_db)),
            "schema_versions": [2, 3, 4, 5, 6, 7],
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "repository|schema"):
            self.audit(db_path=empty_db, status_path=empty_status)

    def test_foreign_sqlite_user_version_is_not_formal_schema(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("PRAGMA user_version=999")
            connection.commit()
        finally:
            connection.close()
        status = json.loads(self.status_path.read_text(encoding="utf-8"))
        status["db_sha256"] = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        status["db_generation_hash"] = digest(db_generation(self.db_path))
        self.status_path.write_text(json.dumps(status), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "schema"):
            self.audit()

    def test_committed_wal_migration_removal_is_seen_by_read_only_schema_gate(self):
        writer = sqlite3.connect(self.db_path)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("DELETE FROM schema_migration WHERE version=7")
            writer.commit()
            self.assertTrue(self.db_path.with_name(self.db_path.name + "-wal").is_file())
            status = json.loads(self.status_path.read_text(encoding="utf-8"))
            status["db_sha256"] = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
            status["db_generation_hash"] = digest(db_generation(self.db_path))
            self.status_path.write_text(json.dumps(status), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema"):
                coverage_module._read_environment(
                    Path(__file__).resolve().parents[1], self.db_path, self.status_path, 7)
        finally:
            writer.close()

    def test_recheck_timestamp_is_noncanonical_even_in_repository_receipt(self):
        early = [dict(row, rechecked_at_utc="2026-10-01T00:00:00+00:00") for row in self.records]
        late = [dict(row, rechecked_at_utc="2026-10-02T00:00:00+00:00") for row in self.records]
        self.assertEqual(self.audit(records=early).manifest_hash,
                         self.audit(records=late).manifest_hash)

    def test_fabricated_callback_and_empty_database_cannot_grant_official(self):
        fabricated = [dict(row, selected_snapshot_id="fabricated") for row in self.records]
        with self.assertRaisesRegex(ValueError, "repository|schema|authority"):
            self.audit(records=fabricated).require_official_ready()

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
        self.verifier.verify = lambda *_args, **_kwargs: False
        with self.assertRaisesRegex(ValueError, "registry|signature"):
            result.require_official_ready()


if __name__ == "__main__": unittest.main()
