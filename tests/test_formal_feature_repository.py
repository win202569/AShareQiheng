"""Typed Formal V3 repository trust-boundary regressions."""

from contextlib import closing
from dataclasses import replace
from datetime import datetime
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_feature_contract import FormalEvidenceRef, FormalFeatureBundle, load_signed_feature_registry
from ashare_pipeline.formal_feature_store import FormalFeatureBundleStore
from ashare_pipeline.formal_financial_features import build_formal_feature_bundle
from ashare_pipeline.formal_financial_schema import FormalFactIssue, FormalFinancialFact
from ashare_pipeline.formal_registry_manifest import FormalRegistryBundleLoader, FormalRegistryManifest, VerifiedRegistryBlob
from ashare_pipeline.state_store import StateStore
from tests.test_formal_feature_contract import canonical_bytes, feature_registry_bytes, slot_wire, TEMPLATES
from tests.test_formal_feature_store import project_temporary_directory
import tests.test_state_store as state_store_tests


class DigestVerifier:
    def verify(self, raw, *, signature, key_id):
        return key_id == "fixture-key" and signature == hashlib.sha256(raw).hexdigest()


class SnapshotProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.requests = []

    def resolve_current_inputs(self, **request):
        self.requests.append(request)
        return self.snapshot


class FormalFeatureRepositoryApiTests(unittest.TestCase):
    def test_verified_repository_api_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_feature_repository"))


class FormalFeatureRepositoryTests(unittest.TestCase):
    install_fact = state_store_tests.FormalV6PersistenceTests.install_fact
    install_eligible_bundle_facts = (
        state_store_tests.FormalV6PersistenceTests.install_eligible_bundle_facts
    )

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_feature_repository"))
        self.api = importlib.import_module("ashare_pipeline.formal_feature_repository")
        self.temp = project_temporary_directory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "state.sqlite"
        self.store = StateStore(self.db_path)
        self.store.initialize()
        facts = self.install_eligible_bundle_facts()
        self.fact = next(fact for fact in facts if fact.period_end == "2025-12-31")
        self.store.insert_formal_financial_facts(facts)
        self.verifier = DigestVerifier()
        self.files = FormalFeatureBundleStore(self.root)
        self.install_registry()
        self.bundle = self.build()
        self.assertEqual(self.bundle.blockers, ())
        self.assertEqual(self.bundle.comparable_quarter_keys, (
            "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1",
            "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2",
        ))
        self.store.put_formal_feature_bundle(self.bundle, self.files.write(self.bundle))
        self.repo = self.repository()

    def repository(self, provider=None, **changes):
        args = dict(registry_signature_verifier=self.verifier, current_input_provider=provider)
        args.update(changes)
        return self.api.FormalFeatureRepository(self.store, FormalFeatureBundleStore(self.root), **args)

    def install_registry(self, *, required=True, templates=TEMPLATES, purpose="official", wrong_binding=False,
                         period_key="FY2025"):
        roles = ("source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event")
        raw = {role: canonical_bytes({"registry_role": role, "schema_version": "fixture-v1"}) for role in roles}
        raw["source"] = canonical_bytes({"registry_role": "source", "schema_version": "formal-source-registry-v1", "configs": []})
        raw["feature"] = feature_registry_bytes(template_ids=templates,
            source_registry_hash="f" * 64 if wrong_binding else hashlib.sha256(raw["source"]).hexdigest(),
            mapping_registry_hash=hashlib.sha256(raw["mapping"]).hexdigest(),
            slots=sorted([slot_wire(t, required=required, unit="CNY", formula={"op": "fact", "fact_key": "revenue", "period_key": period_key}) for t in templates], key=lambda s: s["slot_id"]))
        hashes = {f"{role}_registry_hash": hashlib.sha256(value).hexdigest() for role, value in raw.items()}
        approval = "test-approval" if purpose == "official" else None
        root_bytes = canonical_bytes({"schema_version": "formal-registry-manifest-v1", "purpose": purpose, "approval_id": approval, **hashes})
        self.manifest = FormalRegistryManifest.from_signed_bytes(root_bytes, hashlib.sha256(root_bytes).hexdigest(), "fixture-key", self.verifier)
        self.registry = load_signed_feature_registry(raw["feature"], hashes["feature_registry_hash"], "fixture-key", self.verifier, registry_manifest=self.manifest)
        self.blobs = {}
        for role, value in raw.items():
            child_hash = hashes[f"{role}_registry_hash"]
            binding = canonical_bytes({"child_sha256": child_hash, "registry_manifest_hash": self.manifest.manifest_hash, "registry_role": role})
            self.blobs[child_hash] = VerifiedRegistryBlob(registry_hash=child_hash, registry_role=role, canonical_json=value,
                signature=child_hash, key_id="fixture-key", approval_id=approval,
                declared_registry_manifest_hash=self.manifest.manifest_hash,
                binding_signature=hashlib.sha256(binding).hexdigest(), binding_key_id="fixture-key")
        # Each test owns this disposable SQLite database. Replace the fixture graph
        # directly so valid test/non-release graphs can exercise the reader gate.
        self.store = StateStore(self.db_path, formal_snapshot_store=self.store._formal_snapshot_store,
            registry_signature_verifier=self.verifier, formal_feature_bundle_store=self.files)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DELETE FROM formal_registry_manifest")
            connection.execute("DELETE FROM formal_registry_blob")
            connection.commit()
        if purpose == "official":
            for blob in self.blobs.values():
                self.store.put_formal_registry_blob(blob)
            self.store.put_formal_registry_manifest(self.manifest)

    def build(self, *, facts=None, issues=()):
        return build_formal_feature_bundle(security_id="SZ000001", as_of_utc="2026-08-31T07:00:00+00:00",
            template_id="general_nonfinancial", facts=self.store.list_formal_financial_facts(security_id="SZ000001") if facts is None else facts,
            issues=issues, registry=self.registry, registry_manifest=self.manifest)

    def snapshot(self, **changes):
        values = dict(security_id="SZ000001", as_of_utc="2026-08-31T07:00:00+00:00",
            template_id="general_nonfinancial", registry_manifest_hash=self.manifest.manifest_hash,
            batch_id="fixture-generation-1", facts=self.store.list_formal_financial_facts(security_id="SZ000001"), issues=(), complete=True)
        values.update(changes)
        return self.api.FormalFeatureCurrentInput(**values)

    def select(self, repo=None, **changes):
        request = dict(security_id="SZ000001", as_of_utc="2026-08-31T07:00:00+00:00",
            template_id="general_nonfinancial", registry_manifest_hash=self.manifest.manifest_hash)
        request.update(changes)
        return (repo or self.repo).select_current_verified_formal_feature_bundle(**request)

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(statement, parameters)
            connection.commit()

    def persist_unchecked(self, bundle):
        """Simulate coherent SQL/file corruption below the production API."""
        receipt = self.files.write(bundle)
        header = bundle.to_dict()
        values = header.pop("values")
        for field in ("history_endpoints", "comparable_quarter_keys", "blockers"):
            header[field + "_json"] = canonical_bytes(header.pop(field)).decode()
        header.update(id=receipt.bundle_hash, bundle_hash=receipt.bundle_hash,
            bundle_manifest_hash=receipt.manifest_hash, bundle_path=receipt.bundle_path,
            manifest_path=receipt.manifest_path, created_at_utc="2026-09-05T00:00:00+00:00")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DELETE FROM formal_feature_value WHERE feature_set_id IN (SELECT id FROM formal_feature_set WHERE input_hash=?)", (bundle.input_hash,))
            connection.execute("DELETE FROM formal_feature_set WHERE input_hash=?", (bundle.input_hash,))
            connection.execute(f"INSERT INTO formal_feature_set ({','.join(header)}) VALUES ({','.join('?' for _ in header)})", tuple(header.values()))
            for value in values:
                value["feature_set_id"] = receipt.bundle_hash
                value["evidence_json"] = canonical_bytes(value.pop("evidence")).decode()
                connection.execute(f"INSERT INTO formal_feature_value ({','.join(value)}) VALUES ({','.join('?' for _ in value)})", tuple(value.values()))
            connection.commit()

    def correction(self):
        original_store = self.store
        revised = self.install_fact(value=120.0, generation="revision-v2",
            source_overrides={"source_updated_at_utc": "2026-03-21T08:30:00+00:00"})
        self.store = original_store
        self.store.insert_formal_financial_facts((revised,))
        return revised

    def test_restart_exact_historical_returns_typed_detached_bundle_or_absence(self):
        result = self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
        self.assertIs(type(result), FormalFeatureBundle)
        self.assertEqual(result.values[0].value, 100.0)
        self.assertIsNot(result, self.bundle)
        self.assertIsNone(self.repo.get_verified_formal_feature_bundle(input_hash="f" * 64))
        wire = result.to_dict()
        wire["values"][0]["value"] = 999.0
        self.assertEqual(self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash).values[0].value, 100.0)

    def test_invalid_hash_and_current_identity_reject_before_any_io(self):
        with patch.object(StateStore, "get_formal_feature_bundle_row", side_effect=AssertionError("database accessed")):
            for value in (None, 1, "A" * 64, " f" * 32):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.repo.get_verified_formal_feature_bundle(input_hash=value)
        provider = SnapshotProvider(self.snapshot())
        repo = self.repository(provider)
        with patch.object(StateStore, "get_formal_registry_manifest", side_effect=AssertionError("database accessed")):
            for field, value in (("template_id", "unknown"), ("template_id", []), ("security_id", "000001"), ("as_of_utc", "2026-08-31"), ("registry_manifest_hash", "bad")):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.select(repo, **{field: value})
        self.assertEqual(provider.requests, [])

    def test_dependencies_require_exact_stores_and_explicit_verifiers(self):
        for bad_store, bad_files in ((None, self.files), (self.store, None)):
            with self.assertRaises(ValueError):
                self.api.FormalFeatureRepository(bad_store, bad_files, registry_signature_verifier=self.verifier)
        with self.assertRaises(ValueError):
            self.repository(registry_signature_verifier=None)
        unconfigured = StateStore(self.db_path)
        repo = self.api.FormalFeatureRepository(unconfigured, self.files, registry_signature_verifier=self.verifier)
        with self.assertRaises(ValueError):
            repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)

    def test_every_file_projection_is_compared_and_metadata_is_reread(self):
        getter = StateStore.get_formal_feature_bundle_row
        mutations = {"schema_version": 2, "contract_version": "other", "security_id": "SH600001",
            "as_of_utc": "2026-08-30T07:00:00+00:00", "template_id": "bank",
            "registry_manifest_hash": "a" * 64, "feature_registry_hash": "b" * 64,
            "input_hash": "c" * 64, "history_endpoints": [], "comparable_quarter_keys": ["2025Q1"],
            "blockers": ["bad"], "id": "d" * 64, "bundle_hash": "d" * 64,
            "bundle_manifest_hash": "e" * 64, "bundle_path": str(self.root / "bad.json"),
            "manifest_path": str(self.root / "bad.manifest.json")}
        for key, value in mutations.items():
            def changed(store, input_hash):
                row = getter(store, input_hash)
                row[key] = value
                return row
            with self.subTest(key=key), patch.object(StateStore, "get_formal_feature_bundle_row", changed), self.assertRaises(ValueError):
                self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
        calls = 0
        def raced(store, input_hash):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.sql("UPDATE formal_feature_set SET created_at_utc='2026-09-05T01:00:00+00:00'")
            return getter(store, input_hash)
        with patch.object(StateStore, "get_formal_feature_bundle_row", raced), self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)

    def test_sql_values_and_files_tamper_are_rejected(self):
        self.sql("UPDATE formal_feature_value SET value=900")
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
        self.sql("UPDATE formal_feature_value SET value=100")
        row = self.store.get_formal_feature_bundle_row(self.bundle.input_hash)
        for key in ("bundle_path", "manifest_path"):
            path = Path(row[key])
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
            path.write_bytes(original)

    def test_each_registry_child_and_root_failure_is_rejected(self):
        for column, value in (("signature", "wrong"), ("registry_role", "wrong"), ("binding_signature", "wrong"),
                              ("declared_registry_manifest_hash", "a" * 64), ("approval_id", "wrong")):
            for blob in self.blobs.values():
                self.sql(f"UPDATE formal_registry_blob SET {column}=? WHERE registry_hash=?", (value, blob.registry_hash))
                with self.subTest(column=column, role=blob.registry_role), self.assertRaises(ValueError):
                    self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
                self.sql(f"UPDATE formal_registry_blob SET {column}=? WHERE registry_hash=?", (getattr(blob, column), blob.registry_hash))
        self.sql("UPDATE formal_registry_manifest SET signature='wrong'")
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)

    def test_evidence_fact_mutation_deletion_and_raw_tamper_are_rejected(self):
        self.sql("UPDATE formal_financial_fact SET value=999 WHERE id=?", (self.fact.id,))
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
        self.sql("UPDATE formal_financial_fact SET value=100 WHERE id=?", (self.fact.id,))
        with closing(sqlite3.connect(self.db_path)) as connection:
            raw_path = Path(connection.execute("SELECT content_path FROM formal_source_snapshot WHERE id=?", (self.fact.source_snapshot_id,)).fetchone()[0])
        if not raw_path.is_absolute():
            raw_path = self.root / raw_path
        original = raw_path.read_bytes()
        raw_path.write_bytes(original + b"tamper")
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
        raw_path.write_bytes(original)
        self.sql("DELETE FROM formal_financial_fact")
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)

    def test_blocked_required_missing_inapplicable_and_wrong_signed_slots_reject(self):
        variants = [{"blockers": ["audit_only"]}]
        for changes in ({"status": "blocked", "value": None, "evidence": [], "missing_reason": "blocked"},
                        {"status": "missing", "value": None, "evidence": [], "missing_reason": "missing"},
                        {"status": "not_applicable", "value": None, "evidence": [], "missing_reason": "not_applicable"},
                        {"unit": "ratio"}, {"formula_version": "wrong"}, {"slot_id": "general_nonfinancial.extra"}):
            item = self.bundle.to_dict()["values"][0]
            item.update(changes)
            variants.append({"values": [item]})
        for changes in variants:
            wire = self.bundle.to_dict()
            wire.update(changes)
            changed = FormalFeatureBundle.from_dict(wire)
            self.persist_unchecked(changed)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash)

    def test_foreign_evidence_rejects_despite_matching_files_and_sql(self):
        wire = self.bundle.to_dict()
        wire["security_id"] = "SH600001"
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash)

    def test_evidence_cutoff_is_inclusive_and_late_capture_is_allowed(self):
        cutoff = "2026-03-20T08:00:00+00:00"
        for fact in self.store.list_formal_financial_facts(security_id="SZ000001"):
            self.assertEqual(fact.published_at_utc, cutoff)
            self.assertEqual(fact.effective_at_utc, cutoff)
            self.assertIsNone(fact.source_updated_at_utc)
            self.assertGreater(datetime.fromisoformat(fact.captured_at_utc), datetime.fromisoformat(cutoff))
        wire = self.bundle.to_dict()
        wire["as_of_utc"] = cutoff
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        self.assertEqual(self.repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash).canonical_bytes(), changed.canonical_bytes())
        wire["as_of_utc"] = "2026-03-20T07:59:59+00:00"
        self.assertGreater(datetime.fromisoformat(cutoff), datetime.fromisoformat(wire["as_of_utc"]))
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        with self.assertRaisesRegex(ValueError, "after cutoff"):
            self.repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash)

    def test_future_source_update_rejects_despite_matching_files_and_sql(self):
        cutoff = "2026-03-20T08:00:00+00:00"
        updated = "2026-03-20T08:00:01+00:00"
        original_store = self.store
        future = self.install_fact(generation="future-update-boundary",
            source_overrides={"source_updated_at_utc": updated})
        self.store = original_store
        self.store.insert_formal_financial_facts((future,))
        persisted = next(fact for fact in self.store.list_formal_financial_facts(security_id="SZ000001") if fact.id == future.id)
        self.assertEqual(persisted.published_at_utc, cutoff)
        self.assertEqual(persisted.effective_at_utc, cutoff)
        self.assertEqual(persisted.source_updated_at_utc, updated)
        self.assertGreater(datetime.fromisoformat(updated), datetime.fromisoformat(cutoff))
        wire = self.bundle.to_dict()
        wire["as_of_utc"] = cutoff
        wire["values"][0]["evidence"] = [FormalEvidenceRef.from_formal_fact(persisted).to_dict()]
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        with self.assertRaisesRegex(ValueError, "after cutoff"):
            self.repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash)
        wire["as_of_utc"] = updated
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        self.assertEqual(self.repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash).canonical_bytes(), changed.canonical_bytes())

    def test_signed_nonrelease_registry_rejects_historical_and_current(self):
        self.install_registry(templates=("general_nonfinancial",))
        wire = self.bundle.to_dict()
        wire.update(registry_manifest_hash=self.manifest.manifest_hash, feature_registry_hash=self.registry.registry_hash)
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        repo = self.repository(SnapshotProvider(self.snapshot()))
        with self.assertRaises(ValueError):
            repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash)
        with self.assertRaises(ValueError):
            self.select(repo)

    def test_validly_signed_test_graph_is_not_release_approved(self):
        self.install_registry(purpose="test")
        wire = self.bundle.to_dict()
        wire.update(registry_manifest_hash=self.manifest.manifest_hash, feature_registry_hash=self.registry.registry_hash)
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        repo = self.repository(SnapshotProvider(self.snapshot()))
        with patch.object(StateStore, "get_formal_registry_manifest", return_value=self.manifest), patch.object(StateStore, "get_formal_registry_blob", side_effect=self.blobs.get):
            with self.assertRaises(ValueError):
                repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash)
            with self.assertRaises(ValueError):
                self.select(repo)

    def test_optional_missing_slot_is_readable_with_empty_evidence(self):
        # An optional unobserved period must not erase the universal history gate.
        self.install_registry(required=False, period_key="FY2021")
        immature = self.build(facts=())
        self.assertIn("pending_evidence/history_not_mature", immature.blockers)
        self.store.put_formal_feature_bundle(immature, self.files.write(immature))
        with self.assertRaisesRegex(ValueError, "blocked"):
            self.repository().get_verified_formal_feature_bundle(input_hash=immature.input_hash)
        bundle = self.build()
        self.assertEqual(bundle.blockers, ())
        self.store.put_formal_feature_bundle(bundle, self.files.write(bundle))
        result = self.repository().get_verified_formal_feature_bundle(input_hash=bundle.input_hash)
        self.assertEqual(result.values[0].status, "missing")
        self.assertEqual(result.values[0].evidence, ())

    def test_missing_incomplete_mismatched_and_noncanonical_provider_snapshots_reject(self):
        with self.assertRaises(ValueError):
            self.select()
        for changes in ({"complete": False}, {"complete": 1}, {"batch_id": " "}, {"batch_id": "bad\x00batch"},
                        {"security_id": "SH600001"}, {"as_of_utc": "2026-08-30T07:00:00+00:00"},
                        {"template_id": "bank"}, {"registry_manifest_hash": "a" * 64}, {"facts": []}, {"issues": []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.select(self.repository(SnapshotProvider(self.snapshot(**changes))))

    def test_provider_cannot_hide_duplicate_substitute_or_mutate_persisted_facts(self):
        for facts in ((), (self.fact, self.fact), (replace(self.snapshot(), facts=()).facts,)):
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                self.select(self.repository(SnapshotProvider(self.snapshot(facts=facts))))
        object.__setattr__(self.fact, "value", 999.0)
        with self.assertRaises(ValueError):
            self.select(self.repository(SnapshotProvider(self.snapshot(facts=(self.fact,)))))

    def test_current_uses_builder_input_once_and_selects_exact_correction(self):
        provider = SnapshotProvider(self.snapshot())
        selected = self.select(self.repository(provider))
        self.assertEqual(selected.input_hash, self.bundle.input_hash)
        self.assertEqual(len(provider.requests), 1)
        revised = self.correction()
        expected = self.build()
        self.assertNotEqual(expected.input_hash, self.bundle.input_hash)
        current = self.repository(SnapshotProvider(self.snapshot()))
        self.assertIsNone(self.select(current))
        self.store.put_formal_feature_bundle(expected, self.files.write(expected))
        self.assertEqual(self.select(current).values[0].value, 120.0)
        self.assertEqual(self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash).values[0].value, 100.0)

    def test_correction_during_build_or_exact_lookup_rejects_mixed_generation(self):
        for phase in ("build", "lookup"):
            with self.subTest(phase=phase):
                provider = SnapshotProvider(self.snapshot())
                repo = self.repository(provider)
                if phase == "build":
                    def raced_build(**kwargs):
                        result = build_formal_feature_bundle(**kwargs)
                        self.correction()
                        return result
                    context = patch.object(self.api, "build_formal_feature_bundle", side_effect=raced_build)
                else:
                    expected = self.build()
                    self.store.put_formal_feature_bundle(expected, self.files.write(expected))
                    original = self.api.FormalFeatureRepository.get_verified_formal_feature_bundle
                    def raced_lookup(repository, *, input_hash):
                        result = original(repository, input_hash=input_hash)
                        changed = self.install_fact(value=130.0, generation="revision-v3", source_overrides={"source_updated_at_utc": "2026-03-22T08:30:00+00:00"})
                        self.store.insert_formal_financial_facts((changed,))
                        return result
                    context = patch.object(self.api.FormalFeatureRepository, "get_verified_formal_feature_bundle", raced_lookup)
                with context, self.assertRaises(ValueError):
                    self.select(repo)

    def test_historical_provenance_does_not_claim_complete_semantic_rederivation(self):
        wire = self.bundle.to_dict()
        wire["values"][0]["value"] = 900.0
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        self.assertEqual(self.repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash).values[0].value, 900.0)
        with self.assertRaises(ValueError):
            self.select(self.repository(SnapshotProvider(self.snapshot())))

    def test_complete_provider_issues_are_never_replaced_with_empty_issues(self):
        issue = FormalFactIssue("unknown_source_field", None, "UNKNOWN", {})
        repo = self.repository(SnapshotProvider(self.snapshot(issues=(issue,))))
        self.assertIsNone(self.select(repo))
        blocked = self.build(issues=(issue,))
        self.assertNotEqual(blocked.input_hash, self.bundle.input_hash)
        self.store.put_formal_feature_bundle(blocked, self.files.write(blocked))
        with self.assertRaises(ValueError):
            self.select(repo)

    def test_issue_type_seals_and_provider_request_precede_fact_reads(self):
        issue = FormalFactIssue("unknown_source_field", None, "UNKNOWN", {})
        for issues in (({},), (object.__new__(FormalFactIssue),)):
            with self.subTest(issues=issues), self.assertRaises(ValueError):
                self.select(self.repository(SnapshotProvider(self.snapshot(issues=issues))))
        object.__setattr__(issue, "code", "nonnumeric_value")
        with self.assertRaises(ValueError):
            self.select(self.repository(SnapshotProvider(self.snapshot(issues=(issue,)))))
        repo = self.repository(SnapshotProvider(self.snapshot(batch_id=" ", facts=(object(),))))
        with patch.object(StateStore, "list_formal_financial_facts", side_effect=AssertionError("facts read too early")), self.assertRaises(ValueError):
            self.select(repo)

    def test_provider_mutations_during_snapshot_reject_and_builder_uses_detached_facts(self):
        snapshot = self.snapshot()
        provider = SnapshotProvider(snapshot)
        getter = StateStore.list_formal_financial_facts
        changed = False
        def raced(store, **kwargs):
            nonlocal changed
            result = getter(store, **kwargs)
            if not changed:
                changed = True
                object.__setattr__(snapshot.facts[0], "value", 999.0)
            return result
        with patch.object(StateStore, "list_formal_financial_facts", raced), self.assertRaises(ValueError):
            self.select(self.repository(provider))
        snapshot = self.snapshot()
        def mutate_after_snapshot(**kwargs):
            object.__setattr__(snapshot.facts[0], "value", 999.0)
            return build_formal_feature_bundle(**kwargs)
        with patch.object(self.api, "build_formal_feature_bundle", side_effect=mutate_after_snapshot):
            result = self.select(self.repository(SnapshotProvider(snapshot)))
        self.assertEqual(result.values[0].value, 100.0)

    def test_unpersisted_substitute_fact_and_wrong_evidence_fields_are_rejected(self):
        wire = self.fact.to_dict()
        wire.pop("id")
        wire["value"] = 999.0
        substitute = FormalFinancialFact.create(**wire)
        with self.assertRaises(ValueError):
            self.select(self.repository(SnapshotProvider(self.snapshot(facts=(substitute,)))))
        for key, value in (("source_field", "OTHER"), ("raw_value_sha256", "e" * 64),
                           ("source_refresh_generation", "wrong-generation"), ("formal_fact_id", "e" * 64)):
            wire = self.bundle.to_dict()
            wire["values"][0]["evidence"][0][key] = value
            changed = FormalFeatureBundle.from_dict(wire)
            self.persist_unchecked(changed)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash)

    def test_missing_source_snapshot_is_rejected(self):
        self.sql("DELETE FROM formal_source_snapshot WHERE id=?", (self.fact.source_snapshot_id,))
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
    def test_missing_registry_member_is_rejected(self):
        self.sql("DELETE FROM formal_registry_blob WHERE registry_role='event'")
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)

    def test_source_mapping_root_binding_is_required_even_with_valid_signatures(self):
        self.install_registry(wrong_binding=True)
        wire = self.bundle.to_dict()
        wire.update(registry_manifest_hash=self.manifest.manifest_hash, feature_registry_hash=self.registry.registry_hash)
        changed = FormalFeatureBundle.from_dict(wire)
        self.persist_unchecked(changed)
        repo = self.repository(SnapshotProvider(self.snapshot()))
        with self.assertRaises(ValueError):
            repo.get_verified_formal_feature_bundle(input_hash=changed.input_hash)
        with self.assertRaises(ValueError):
            self.select(repo)

    def test_legacy_bundle_and_store_subclasses_never_enter_typed_paths(self):
        from ashare_pipeline.feature_contract import FeatureBundle
        legacy = object.__new__(FeatureBundle)
        with self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=legacy)
        with self.assertRaises(ValueError):
            self.select(self.repository(SnapshotProvider(legacy)))
        with patch.object(FormalFeatureBundleStore, "read_verified", return_value=legacy), self.assertRaises(ValueError):
            self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
        class DerivedStore(StateStore):
            pass
        class DerivedBundleStore(FormalFeatureBundleStore):
            pass
        for store, files in ((DerivedStore(self.db_path), self.files), (self.store, DerivedBundleStore(self.root))):
            with self.assertRaises(ValueError):
                self.api.FormalFeatureRepository(store, files, registry_signature_verifier=self.verifier)

    def test_fy_only_duration_remains_audit_only_despite_available_annual_fact(self):
        audit = self.build(facts=(self.fact,))
        self.assertEqual(audit.blockers, (
            "history_annual_window_incomplete", "history_quarter_window_incomplete",
            "pending_evidence/history_not_mature", "quarter_missing_prerequisite",
        ))
        self.assertEqual(self.fact.value, 100.0)
        self.assertIsNone(audit.values[0].value)
        self.assertEqual(audit.values[0].status, "blocked")
        self.assertEqual(audit.values[0].evidence, ())
        self.assertEqual(audit.values[0].missing_reason, "feature_input_not_trustworthy")
        self.store.put_formal_feature_bundle(audit, self.files.write(audit))
        with self.assertRaisesRegex(ValueError, "blocked"):
            self.repo.get_verified_formal_feature_bundle(input_hash=audit.input_hash)

    def test_raw_receipt_manifest_tamper_and_delete_reject_until_restored(self):
        ref = self.store.get_formal_snapshot(self.fact.source_snapshot_id)
        path = Path(ref.manifest_path)
        original = path.read_bytes()
        for delete in (False, True):
            if delete:
                path.unlink()
            else:
                path.write_bytes(b"{}")
            try:
                with self.subTest(delete=delete), self.assertRaises(ValueError):
                    self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash)
            finally:
                path.write_bytes(original)
            self.assertEqual(self.repo.get_verified_formal_feature_bundle(input_hash=self.bundle.input_hash).values[0].value, 100.0)


if __name__ == "__main__":
    unittest.main()
