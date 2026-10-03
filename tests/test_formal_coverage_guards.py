import copy
import gc
import hashlib
import json
import pickle
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import weakref

import ashare_pipeline.formal_coverage_manifest as coverage_module
from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor
from ashare_pipeline.formal_registry_manifest import FormalRegistryBundleLoader
from ashare_pipeline.formal_snapshot_repository import FormalSnapshotRepository
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore
from ashare_pipeline.formal_evidence import OfficialRequest
from ashare_pipeline.formal_universe import FormalUniverseIngestor
from ashare_pipeline.state_store import StateStore, SCHEMA_VERSION
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
            for suffix in ("", "-wal")
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


class OwnerCoverageAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
        def shared_metric_fact(documents):
            # Required fixture slots share one signed input; Policy keeps its
            # separate equity input. Both still use real persisted producers.
            for slot in documents["feature"]["slots"]:
                if ".policy." not in slot["slot_id"]:
                    slot["formula"]["fact_key"] = "coverage.shared"
        cls.fixture = PolicyRuntimeFixture(range_enabled=True, cyclic=False, mutate=shared_metric_fact)
        cls.addClassCleanup(cls.fixture.close)
        f = cls.fixture
        cls.features = {}
        for member in f.industry["memberships"]:
            sid, template = member["security_id"], member["template_id"]
            f.put_industry(sid)
            f.put_policy_context(sid, "security_state", dict(is_st=False, is_star_st=False,
                listing_status="listed", forced_delist_risk=False, suspended=False))
            f.put_policy_financial(sid, {"fixture.policy.current.equity": 1.0},
                fy_end="2025-12-31", units={"fixture.policy.current.equity": "CNY"})
            f.put_financial(sid, {"coverage.shared": 3.0}, generation="coverage-complete")
            cls.features[sid] = f.persist_features(sid)
        cls.batch, cls.revoke_batch, _ = f.policy_repository._build_batch(
            f.frozen.frozen_input_hash, scoring_registry=f.scoring,
            policy_registry=f.policy_registry, owner_scope=None)
        cls.status_path = f.root / "coverage-status.json"
        cls.status_path.write_text(json.dumps({
            "generated_at_utc": "2026-09-01T00:00:00+00:00", "schema_version": SCHEMA_VERSION,
            "db_sha256": hashlib.sha256(f.db_path.read_bytes()).hexdigest(),
            "db_generation_hash": digest(db_generation(f.db_path)),
            "schema_versions": list(range(2, SCHEMA_VERSION + 1)),
        }), encoding="utf-8")

    def catalog(self, domain, *, change=None):
        f = self.fixture
        owner = "formal_" + domain + "_repository"
        descriptors, requirements = {}, []
        for member in f.frozen.members:
            sid = member.security_id
            selector = dict(owner=owner, domain=domain, security_id=sid,
                            exchange=member.exchange, period_or_window=f.frozen.as_of_utc)
            units = []
            if domain == "context":
                selector.update(context_kind="industry_snapshot", scope_key="fixture-industry",
                                as_of_utc=f.frozen.as_of_utc)
            elif domain == "feature":
                bundle = self.features[sid]
                selector.update(input_hash=bundle.input_hash,
                                slot_id=bundle.template_id + ".G.operating_revenue_yoy")
                units = ["CNY"]
            else:
                result = next(item for item in self.batch.results if item.security_id == sid)
                rule = next(item for item in result.decisions if item.semantic_id == "nonpositive_equity")
                selector.update(batch_hash=self.batch.batch_hash, rule_id=rule.rule_id)
            if change:
                selector.update(change(selector))
            selector_hash = digest(selector)
            descriptors[selector_hash] = selector
            requirements.append(dict(frozen_input_hash=f.frozen.frozen_input_hash,
                security_id=sid, domain=domain, selector_hash=selector_hash,
                exchange=member.exchange, period_or_window=f.frozen.as_of_utc, expected_units=units))
        manifest = f.bundle.manifest
        return dict(schema_version="formal-coverage-contract-v1", purpose="official",
            approval_id=manifest.approval_id, signing_identity=manifest.key_id,
            registry_manifest_hash=manifest.manifest_hash, frozen_input_hash=f.frozen.frozen_input_hash,
            requirements=requirements, domain_owners={domain: owner}, selector_descriptors=descriptors,
            expected_schema_version=SCHEMA_VERSION, report_period="2025", query_version="coverage-v1")

    def audit(self, domain, *, wire=None, **changes):
        f = self.fixture
        wire = self.catalog(domain) if wire is None else wire
        raw = canonical(wire)
        args = dict(production_contract=dict(canonical_json=raw, signature=f.verifier.sign(raw),
                    key_id=f.bundle.manifest.key_id), contract_verifier=f.verifier,
            registry_bundle=f.bundle, registry_loader=FormalRegistryBundleLoader(f.store, f.verifier),
            snapshot_repository=f.snapshots, frozen_universe=f.frozen,
            workspace_root=Path(__file__).resolve().parents[1], db_path=f.db_path,
            status_path=self.status_path, context_repository=f.context,
            feature_repository=f.feature_repository, policy_repository=f.policy_repository,
            policy_batch=self.batch)
        args.update(changes)
        return FormalCoverageAuditor().audit(wire["requirements"], **args)

    def assert_owner_ready(self, domain):
        result = self.audit(domain)
        result.require_preview_ready()
        result.require_official_ready()
        self.assertEqual(len(result.rows), 3)
        for row in result.rows:
            provenance = row["repository_provenance"]
            self.assertEqual(provenance["owner"], "formal_" + domain + "_repository")
            self.assertEqual(provenance["requirement_hash"], digest(next(
                req for req in self.catalog(domain)["requirements"]
                if req["security_id"] == row["security_id"])))
            self.assertTrue(provenance["evidence"])
            self.assertTrue(row["evidence_hashes"])

    def test_genuine_context_owner_rows_reach_both_gates(self):
        self.assert_owner_ready("context")

    def test_genuine_feature_owner_rows_reach_both_gates(self):
        self.assert_owner_ready("feature")

    def test_genuine_policy_owner_rows_reach_both_gates(self):
        self.assert_owner_ready("policy")

    def test_wrong_typed_owner_cannot_be_replaced_with_callback_or_dictionary(self):
        for domain in ("context", "feature", "policy"):
            genuine = {"context": self.fixture.context, "feature": self.fixture.feature_repository,
                       "policy": self.fixture.policy_repository}[domain]
            for forged in (True, {}, lambda *_: True, object(), object.__new__(type(genuine))):
                with self.subTest(domain=domain, forged=type(forged)), self.assertRaises(ValueError):
                    self.audit(domain, **{domain + "_repository": forged})
        f = self.fixture
        other_policy_owner = type(f.policy_repository)(f.feature_repository, f.context,
            f.range_store, registry_signature_verifier=f.verifier)
        with self.assertRaises(ValueError):
            self.audit("policy", policy_repository=other_policy_owner)

    def test_signed_wrong_slot_scope_rule_and_member_selection_are_rejected(self):
        changes = {"context": lambda s: dict(scope_key="wrong-scope"),
                   "feature": lambda s: dict(slot_id="bank.nonexistent"),
                   "policy": lambda s: dict(rule_id="wrong-rule")}
        for domain, change in changes.items():
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                self.audit(domain, wire=self.catalog(domain, change=change))
        with self.assertRaises(ValueError):
            self.audit("feature", wire=self.catalog("feature", change=lambda s:
                dict(input_hash=self.features["SH600000"].input_hash)))
        with self.assertRaises(ValueError):
            self.audit("context", wire=self.catalog("context", change=lambda s:
                dict(security_id="SH600000")))

    def assert_raw_change_blocks_gates(self, domain):
        f = self.fixture
        result = self.audit(domain)
        if domain == "context":
            row = next(row for row in result.rows if row["security_id"] == "SH600000")
            snapshot_id = row["repository_provenance"]["selected_item"]["source_snapshot_id"]
        elif domain == "feature":
            row = next(row for row in result.rows if row["security_id"] == "SH600000")
            snapshot_id = row["repository_provenance"]["selected_item"]["evidence"][0]["source_snapshot_id"]
        else:
            fact = next(fact for fact in f.store.list_formal_financial_facts(security_id="SH600000")
                        if fact.metric_key == "fixture.policy.current.equity")
            snapshot_id = fact.source_snapshot_id
        ref = f.store.get_formal_snapshot(snapshot_id)
        path, original = Path(ref.content_path), Path(ref.content_path).read_bytes()
        try:
            path.write_bytes(b"stale source bytes")
            for gate in (result.require_preview_ready, result.require_official_ready):
                with self.subTest(gate=gate.__name__), self.assertRaises(ValueError):
                    gate()
        finally:
            path.write_bytes(original)

    def test_context_gates_recheck_raw_evidence_without_database_change(self):
        self.assert_raw_change_blocks_gates("context")

    def test_feature_gates_recheck_raw_evidence_without_database_change(self):
        self.assert_raw_change_blocks_gates("feature")

    def test_feature_gates_reject_stale_current_inputs_with_intact_historical_receipt(self):
        from ashare_pipeline.formal_financial_schema import FormalFactIssue
        f = self.fixture
        result = self.audit("feature")
        original_generation = db_generation(f.db_path)
        f.set_issues("SH600000", (FormalFactIssue("unknown_source_field", None, "UNKNOWN", {}),))
        try:
            # The historical receipt and all raw files remain authentic. Only
            # the genuine provider's complete current input has changed.
            historical = f.feature_repository._read_authenticated_bundle(
                input_hash=self.features["SH600000"].input_hash, require_complete=False)
            self.assertEqual(historical.input_hash, self.features["SH600000"].input_hash)
            self.assertEqual(db_generation(f.db_path), original_generation)
            for gate in (result.require_preview_ready, result.require_official_ready):
                with self.subTest(gate=gate.__name__), self.assertRaises(ValueError):
                    gate()
        finally:
            f.set_issues("SH600000", ())

    def test_policy_gates_recheck_raw_evidence_without_database_change(self):
        self.assert_raw_change_blocks_gates("policy")

    def test_cross_root_contract_and_plain_policy_batch_are_rejected(self):
        for domain in ("context", "feature", "policy"):
            wire = self.catalog(domain)
            wire["registry_manifest_hash"] = "f" * 64
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                self.audit(domain, wire=wire)
        with self.assertRaises(ValueError):
            self.audit("policy", policy_batch=self.batch.to_dict())

    def test_revoked_policy_publication_invalidates_both_coverage_gates(self):
        f = self.fixture
        batch, revoke, _ = f.policy_repository._build_batch(f.frozen.frozen_input_hash,
            scoring_registry=f.scoring, policy_registry=f.policy_registry, owner_scope=None)
        result = self.audit("policy", policy_batch=batch)
        revoke(batch)
        for gate in (result.require_preview_ready, result.require_official_ready):
            with self.subTest(gate=gate.__name__), self.assertRaises(ValueError):
                gate()


class MarketRangeCoverageAdapterTests(unittest.TestCase):
    audit = OwnerCoverageAdapterTests.audit

    @classmethod
    def setUpClass(cls):
        from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
        cls.fixture = PolicyRuntimeFixture(range_enabled=True, cyclic=False, templates={"SH600000": "bank"},
                                          extra_members=("BJ430001", "SZ000001"))
        cls.addClassCleanup(cls.fixture.close)
        f = cls.fixture
        f.populate_policy_evidence(skip_financial=["SH600000"])
        for sid in ("BJ430001", "SZ000001"):
            f.put_policy_context(sid, "security_state", dict(is_st=False, is_star_st=False,
                listing_status="listed", forced_delist_risk=False, suspended=False))
        cls.features = {}
        cls.batch, cls.revoke_batch, _ = f.policy_repository._build_batch(
            f.frozen.frozen_input_hash, scoring_registry=f.scoring,
            policy_registry=f.policy_registry, owner_scope=None)
        cls.status_path = f.root / "coverage-status.json"
        cls.status_path.write_text(json.dumps(dict(generated_at_utc="2026-09-01T00:00:00+00:00",
            schema_version=SCHEMA_VERSION, db_sha256=hashlib.sha256(f.db_path.read_bytes()).hexdigest(),
            db_generation_hash=digest(db_generation(f.db_path)),
            schema_versions=list(range(2, SCHEMA_VERSION + 1)))), encoding="utf-8")

    def catalog(self, domain, *, change=None):
        f = self.fixture
        requirements, descriptors = [], {}
        for member in f.frozen.members:
            market = member.security_id == "SH600000"
            owner = "formal_policy_repository" if market else "formal_context_repository"
            selected_domain = domain if market else "security_state"
            selector = dict(owner=owner, domain=selected_domain, security_id=member.security_id,
                exchange=member.exchange, period_or_window=f.frozen.as_of_utc)
            if market:
                result = next(item for item in self.batch.results if item.security_id == member.security_id)
                rule = next(item for item in result.decisions if item.semantic_id == "no_effective_trade_20d")
                selector.update(batch_hash=self.batch.batch_hash, rule_id=rule.rule_id)
                if change:
                    selector.update(change(selector))
            else:
                selector.update(context_kind="security_state", scope_key="fixture-state", as_of_utc=f.frozen.as_of_utc)
            selector_hash = digest(selector)
            descriptors[selector_hash] = selector
            requirements.append(dict(frozen_input_hash=f.frozen.frozen_input_hash, security_id=member.security_id,
                domain=selected_domain, selector_hash=selector_hash, exchange=member.exchange,
                period_or_window=f.frozen.as_of_utc, expected_units=[]))
        manifest = f.bundle.manifest
        return dict(schema_version="formal-coverage-contract-v1", purpose="official",
            approval_id=manifest.approval_id, signing_identity=manifest.key_id,
            registry_manifest_hash=manifest.manifest_hash, frozen_input_hash=f.frozen.frozen_input_hash,
            requirements=requirements, selector_descriptors=descriptors,
            domain_owners={domain: "formal_policy_repository", "security_state": "formal_context_repository"},
            expected_schema_version=SCHEMA_VERSION, report_period="2025", query_version="coverage-v1")

    def test_genuine_market_and_range_requirements_use_policy_market_evidence(self):
        wire, ranges = self.catalog("market"), self.catalog("range")
        wire["requirements"].extend(req for req in ranges["requirements"] if req["domain"] == "range")
        wire["selector_descriptors"].update(ranges["selector_descriptors"])
        wire["domain_owners"].update(ranges["domain_owners"])
        result = self.audit("market", wire=wire)
        self.assertEqual(len(result.rows), 4)
        for row in result.rows:
            if row["domain"] == "security_state":
                continue
            receipt = row["repository_provenance"]
            self.assertEqual(receipt["owner"], "formal_policy_repository")
            self.assertEqual(receipt["selected_item"]["semantic_id"], "no_effective_trade_20d")
            selected = receipt["evidence"]["market_selection"]
            self.assertEqual(selected["window"]["exchange"], row["exchange"])
            self.assertFalse(selected["pending"])
            self.assertTrue(selected["lineage"])
            source_hashes = {source["manifest_sha256"] for source in receipt["evidence"]["source_snapshots"]}
            for observation in selected["window"]["observations"]:
                self.assertIn(observation["snapshot"]["manifest_sha256"], source_hashes)
        result.require_preview_ready()
        result.require_official_ready()

    def test_market_and_range_cannot_be_relabelled_unrelated_policy_decisions(self):
        for domain in ("market", "range"):
            wrong = next(decision.rule_id for result in self.batch.results if result.security_id == "SH600000"
                         for decision in result.decisions if decision.semantic_id == "st")
            with self.subTest(domain=domain), self.assertRaisesRegex(ValueError, "market|range"):
                self.audit(domain, wire=self.catalog(domain, change=lambda s: dict(rule_id=wrong)))

    def test_market_range_gates_recheck_calendar_and_market_raw_bytes(self):
        result = self.audit("range")
        receipt = next(row["repository_provenance"] for row in result.rows if row["domain"] == "range")
        market = receipt["evidence"]["market_selection"]["window"]["observations"][0]
        f = self.fixture
        calendar_request = f.source.first_calendar_request("2026-08-31T07:00:00+00:00")
        calendar = f.range_store.select_current(calendar_request.request_fingerprint).to_dict()
        generation = db_generation(f.db_path)
        for kind, observation in (("calendar", calendar), ("market", market)):
            path = f.root / "range_raw" / observation["snapshot"]["content_path"]
            original = path.read_bytes()
            try:
                path.write_bytes(b"tampered range source")
                self.assertEqual(db_generation(f.db_path), generation)
                for gate in (result.require_preview_ready, result.require_official_ready):
                    with self.subTest(kind=kind, gate=gate.__name__), self.assertRaises(ValueError):
                        gate()
            finally:
                path.write_bytes(original)


class CalendarCoverageAdapterTests(unittest.TestCase):
    def setUp(self):
        from tests.formal_metric_fixtures import MetricFixture
        from tests.test_formal_context_repository import descriptor
        from tests.test_formal_sources import config

        def calendar_documents(documents):
            for exchange in ("BJ", "SH", "SZ"):
                documents["scoring"]["descriptors"].append(descriptor("trading_calendar",
                    scope_key="coverage-calendar-" + exchange, security_scope="none",
                    request_security="none", period_rule="none", exchange_rule="fixed_exchange",
                    fixed_exchange=exchange, dataset="trading_calendar", bootstrap_calendar=True))
            documents["source"]["configs"].append(config(dataset="trading_calendar", bootstrap_calendar=True))
            documents["feature"]["source_registry_hash"] = digest(documents["source"])

        self.fixture = MetricFixture(mutate=calendar_documents)
        self.addCleanup(self.fixture.close)
        self.batch = None
        self.status_path = self.fixture.root / "coverage-status.json"
        self.calendars = {exchange: self.put_calendar(exchange) for exchange in ("BJ", "SH", "SZ")}
        self.write_status()

    def put_calendar(self, exchange, *, generation="calendar-v1", published="2026-08-19T07:00:00+00:00"):
        from ashare_pipeline.formal_context_schema import FormalContextRegistry
        from ashare_pipeline.formal_evidence import OfficialFetch, SourcePolicy, verify_official_fetch
        from tests.test_formal_context_repository import FixtureNormalizer
        f = self.fixture
        request = f.resolver.resolve(context_kind="trading_calendar", scope_key="coverage-calendar-" + exchange,
            security_id=None, as_of_utc="2026-08-31T07:00:00+00:00", registry_manifest_hash=f.bundle.manifest.manifest_hash,
            upstream_generation=generation)
        task = f.store.enqueue_formal_task("formal_context", exchange + generation, request.refresh_generation, {})
        lease = f.store.lease_next_formal_task(("formal_context",), "coverage-calendar", 300)
        self.assertEqual(lease["id"], task)
        raw = canonical(dict(value=dict(exchange=exchange, calendar_version=generation,
            trading_days=["2026-08-21", "2026-08-31", "2026-09-02"]), no_coverage=False))
        fetch = OfficialFetch(request=request.official_request, raw_bytes=raw,
            original_url="https://www.cninfo.com.cn/fixture/calendar.json", published_at_utc=published,
            published_precision="timestamp", source_updated_at_utc=None,
            captured_at_utc="2026-09-04T07:00:00+00:00", effective_at_utc=published,
            effective_time_evidence_hash=None, refresh_generation=request.refresh_generation,
            parser_id=request.parser_id, parser_version=request.parser_version, mapping_version=request.mapping_version,
            declared_security_id=None, declared_period=None)
        verified = verify_official_fetch(fetch, SourcePolicy.cninfo())
        self.assertEqual(verified.status, "verified")
        ref = f.snapshots.persist_verified(fetch, verified, producing_task_id=task, worker_id="coverage-calendar")
        receipt = FormalContextRegistry.load(f.store, f.verifier, f.bundle.manifest.manifest_hash).normalize_verified(
            request, ref, raw, FixtureNormalizer(), task_id=task, worker_id="coverage-calendar")
        f.store.put_formal_context_facts(receipt)
        f.store.complete_formal_task(task, "coverage-calendar", {"snapshot": ref.snapshot_id})
        return receipt.facts[0], ref

    def write_status(self):
        f = self.fixture
        self.status_path.write_text(json.dumps(dict(generated_at_utc="2026-09-01T00:00:00+00:00",
            schema_version=SCHEMA_VERSION, db_sha256=hashlib.sha256(f.db_path.read_bytes()).hexdigest(),
            db_generation_hash=digest(db_generation(f.db_path)),
            schema_versions=list(range(2, SCHEMA_VERSION + 1)))), encoding="utf-8")

    def catalog(self, domain="trading_calendar", *, change=None):
        f = self.fixture
        descriptors, requirements = {}, []
        for member in f.frozen.members:
            selector = dict(owner="formal_context_repository", domain=domain, security_id=member.security_id,
                exchange=member.exchange, period_or_window=f.frozen.as_of_utc, context_kind="trading_calendar",
                scope_key="coverage-calendar-" + member.exchange, as_of_utc=f.frozen.as_of_utc,
                as_of_rule="visible_at_freeze")
            if change:
                selector.update(change(selector))
            selector_hash = digest(selector)
            descriptors[selector_hash] = selector
            requirements.append(dict(frozen_input_hash=f.frozen.frozen_input_hash, security_id=member.security_id,
                domain=domain, selector_hash=selector_hash, exchange=member.exchange,
                period_or_window=f.frozen.as_of_utc, expected_units=[]))
        manifest = f.bundle.manifest
        return dict(schema_version="formal-coverage-contract-v1", purpose="official",
            approval_id=manifest.approval_id, signing_identity=manifest.key_id,
            registry_manifest_hash=manifest.manifest_hash, frozen_input_hash=f.frozen.frozen_input_hash,
            requirements=requirements, domain_owners={domain: "formal_context_repository"},
            selector_descriptors=descriptors, expected_schema_version=SCHEMA_VERSION,
            report_period="2025", query_version="coverage-v1")

    def audit(self, *, wire=None, **changes):
        f = self.fixture
        wire = self.catalog() if wire is None else wire
        raw = canonical(wire)
        args = dict(production_contract=dict(canonical_json=raw, signature=f.verifier.sign(raw),
            key_id=f.bundle.manifest.key_id), contract_verifier=f.verifier, registry_bundle=f.bundle,
            registry_loader=FormalRegistryBundleLoader(f.store, f.verifier), snapshot_repository=f.snapshots,
            context_repository=f.context, frozen_universe=f.frozen, workspace_root=Path(__file__).resolve().parents[1],
            db_path=f.db_path, status_path=self.status_path)
        args.update(changes)
        return FormalCoverageAuditor().audit(wire["requirements"], **args)

    def test_genuine_sh_sz_bj_calendar_selectors_reach_both_gates(self):
        from ashare_pipeline.formal_sources import CalendarSelector
        result = self.audit()
        result.require_preview_ready()
        result.require_official_ready()
        self.assertEqual({row["exchange"] for row in result.rows}, {"SH", "SZ", "BJ"})
        requirements = {req["security_id"]: req for req in self.catalog()["requirements"]}
        for row in result.rows:
            receipt = row["repository_provenance"]
            selected = receipt["evidence"]["calendar_binding"]
            fact, ref = self.calendars[row["exchange"]]
            self.assertEqual(selected["snapshot_id"], ref.snapshot_id)
            self.assertEqual(selected["manifest_sha256"], ref.manifest_sha256)
            self.assertEqual(selected["prerequisite_task_id"], ref.producing_task_id)
            self.assertEqual(selected["exchange"], row["exchange"])
            self.assertEqual(selected["selector_hash"], CalendarSelector("trading_calendar",
                "coverage-calendar-" + row["exchange"], row["exchange"], "visible_at_freeze").selector_hash)
            self.assertEqual(receipt["selected_item"], fact.to_dict())
            self.assertEqual(receipt["requirement_hash"], digest(requirements[row["security_id"]]))
            self.assertEqual(receipt["evidence"]["source_snapshots"][0]["content_sha256"], ref.content_sha256)

    def test_calendar_descriptor_rejects_wrong_scope_exchange_kind_and_as_of_rule(self):
        for change in (dict(scope_key="coverage-calendar-SH"), dict(exchange="SH"),
                       dict(context_kind="security_state"), dict(as_of_rule="latest"),
                       dict(as_of_utc="2026-08-30T07:00:00+00:00")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.audit(wire=self.catalog(change=lambda _: change))
        with self.assertRaises(ValueError):
            self.audit(wire=self.catalog("context"))

    def test_calendar_gates_recheck_raw_evidence_without_database_change(self):
        result = self.audit()
        f = self.fixture
        generation = db_generation(f.db_path)
        ref = self.calendars["SH"][1]
        path, original = Path(ref.content_path), Path(ref.content_path).read_bytes()
        try:
            path.write_bytes(b"changed calendar bytes")
            self.assertEqual(db_generation(f.db_path), generation)
            for gate in (result.require_preview_ready, result.require_official_ready):
                with self.subTest(gate=gate.__name__), self.assertRaises(ValueError):
                    gate()
        finally:
            path.write_bytes(original)

    def test_calendar_current_correction_invalidates_existing_coverage(self):
        old = self.audit()
        _, current = self.put_calendar("SH", generation="calendar-v2", published="2026-08-20T07:00:00+00:00")
        self.write_status()
        replacement = self.audit()
        replacement.require_official_ready()
        row = next(row for row in replacement.rows if row["exchange"] == "SH")
        self.assertEqual(row["repository_provenance"]["evidence"]["calendar_binding"]["snapshot_id"], current.snapshot_id)
        self.assertNotEqual(old.manifest_hash, replacement.manifest_hash)
        for gate in (old.require_preview_ready, old.require_official_ready):
            with self.subTest(gate=gate.__name__), self.assertRaises(ValueError):
                gate()

    def test_calendar_revoked_source_producer_invalidates_fresh_and_existing_coverage(self):
        result = self.audit()
        f = self.fixture
        task_id = self.calendars["BJ"][1].producing_task_id
        f.sql("UPDATE formal_collection_task SET status='terminal_failed' WHERE id=?", (task_id,))
        self.write_status()
        with self.assertRaises(ValueError):
            self.audit()
        for gate in (result.require_preview_ready, result.require_official_ready):
            with self.subTest(gate=gate.__name__), self.assertRaises(ValueError):
                gate()


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
        self.selector_descriptors = {}
        self.requirements = []
        for member in self.frozen.members:
            descriptor = {"owner": "formal_snapshot_repository", "domain": "financial",
                          "security_id": member.security_id, "exchange": member.exchange,
                          "period_or_window": "2025-12-31", "source": "cninfo",
                          "dataset": "annual_report"}
            selector_hash = digest(descriptor)
            self.selector_descriptors[selector_hash] = descriptor
            self.requirements.append(CoverageRequirement(
                self.frozen.frozen_input_hash, member.security_id,
                "financial", selector_hash, "2025-12-31", member.exchange,
                ("CNY",)))
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
            "schema_version": SCHEMA_VERSION,
            "db_sha256": hashlib.sha256(self.db_path.read_bytes()).hexdigest(),
            "db_generation_hash": digest(db_generation(self.db_path)),
            "schema_versions": list(range(2, SCHEMA_VERSION + 1)),
        }), encoding="utf-8")
        self.contract_wire = {
            "schema_version": "formal-coverage-contract-v1",
            "purpose": "official", "approval_id": manifest.approval_id,
            "signing_identity": manifest.key_id,
            "registry_manifest_hash": manifest.manifest_hash,
            "frozen_input_hash": self.frozen.frozen_input_hash,
            "requirements": [req.to_dict() for req in self.requirements],
            "domain_owners": {"financial": "formal_snapshot_repository"},
            "selector_descriptors": self.selector_descriptors,
            "expected_schema_version": SCHEMA_VERSION, "report_period": "2025",
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

    def test_signed_selector_descriptor_must_match_canonical_hash_and_owner(self):
        bad = dict(self.contract_wire, selector_descriptors={
            key: dict(value, source="fabricated")
            for key, value in self.selector_descriptors.items()})
        with self.assertRaisesRegex(ValueError, "selector"):
            self.audit(contract=self.signed_contract(bad))
        wrong_owner = dict(self.contract_wire, selector_descriptors={
            key: dict(value, owner="formal_context_repository")
            for key, value in self.selector_descriptors.items()})
        with self.assertRaisesRegex(ValueError, "selector"):
            self.audit(contract=self.signed_contract(wrong_owner))

    def test_catalog_rejects_unsupported_domain_owner_pairs_before_evidence_reads(self):
        for domain in ("made_up", "trading_calendar", "context", "feature", "policy",
                       "market", "range", "metric", "valuation", "score_input", "final_input"):
            requirements, descriptors, records = [], {}, []
            for req, record in zip(self.requirements, self.records, strict=True):
                selector = dict(self.selector_descriptors[req.selector_hash], domain=domain)
                selector_hash = digest(selector)
                descriptors[selector_hash] = selector
                requirements.append(dict(req.to_dict(), domain=domain, selector_hash=selector_hash))
                records.append(dict(record, domain=domain, selector_hash=selector_hash))
            wire = dict(self.contract_wire, requirements=requirements, selector_descriptors=descriptors,
                domain_owners={domain: "formal_snapshot_repository"})
            self.calls.clear()
            with self.subTest(domain=domain):
                with self.assertRaisesRegex(ValueError, "domain.*owner|owner.*domain"):
                    self.audit(requirements=requirements, records=records, contract=self.signed_contract(wire),
                               validators={domain: self.validate})
                self.assertEqual(self.calls, [])

    def contract_for_route(self, domain, owner, fields):
        descriptors, requirements = {}, []
        for member in self.frozen.members:
            selector = dict(owner=owner, domain=domain, security_id=member.security_id,
                exchange=member.exchange, period_or_window=self.frozen.as_of_utc, **fields)
            selector_hash = digest(selector)
            descriptors[selector_hash] = selector
            requirements.append(dict(frozen_input_hash=self.frozen.frozen_input_hash,
                security_id=member.security_id, domain=domain, selector_hash=selector_hash,
                exchange=member.exchange, period_or_window=self.frozen.as_of_utc, expected_units=[]))
        return dict(self.contract_wire, requirements=requirements, selector_descriptors=descriptors,
                    domain_owners={domain: owner})

    def verify_catalog(self, wire):
        return coverage_module._official_inputs(self.signed_contract(wire), self.verifier,
            self.bundle, self.registry_loader, self.frozen, wire["requirements"], self.db_path,
            self.snapshot_repository)

    def test_signed_catalog_routes_all_design_source_families(self):
        routes = [
            ("financial", "formal_snapshot_repository", dict(source="cninfo", dataset="annual_report")),
            ("feature", "formal_feature_repository", dict(input_hash="a" * 64, slot_id="bank.G.revenue")),
            ("policy", "formal_policy_repository", dict(batch_hash="b" * 64, rule_id="signed-rule")),
            ("market", "formal_policy_repository", dict(batch_hash="b" * 64, rule_id="signed-market-rule")),
            ("range", "formal_policy_repository", dict(batch_hash="b" * 64, rule_id="signed-market-rule")),
        ]
        for kind in ("trading_calendar", "market_close", "security_state", "industry_snapshot",
                     "regulatory_state", "event_calendar", "consensus_snapshot"):
            fields = dict(context_kind=kind, scope_key="signed-scope", as_of_utc=self.frozen.as_of_utc)
            if kind == "trading_calendar":
                fields["as_of_rule"] = "visible_at_freeze"
            routes.append((kind, "formal_context_repository", fields))
        for domain, owner, fields in routes:
            with self.subTest(domain=domain):
                wire = self.contract_for_route(domain, owner, fields)
                self.assertEqual(self.verify_catalog(wire)["requirements"], wire["requirements"])

    def test_catalog_rejects_unmapped_derived_proofs_and_mismatched_context_kind(self):
        for domain, owner in (("metric", "formal_metric_repository"),
                              ("valuation", "formal_valuation_repository"),
                              ("score_input", "formal_score_input_repository"),
                              ("final_input", "formal_final_score_input_repository")):
            with self.subTest(domain=domain), self.assertRaisesRegex(ValueError, "domain/owner"):
                self.verify_catalog(self.contract_for_route(domain, owner, {}))
        for domain in ("market_close", "security_state", "regulatory_state", "event_calendar", "consensus_snapshot"):
            with self.subTest(domain=domain), self.assertRaisesRegex(ValueError, "domain.*kind"):
                self.verify_catalog(self.contract_for_route(domain, "formal_context_repository",
                    dict(context_kind="industry_snapshot", scope_key="signed-scope", as_of_utc=self.frozen.as_of_utc)))

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
        extra_descriptors = {}
        extra = []
        for member in self.frozen.members:
            descriptor = {"owner": "formal_context_repository", "domain": "context",
                          "security_id": member.security_id, "exchange": member.exchange,
                          "period_or_window": "2025", "context_kind": "security_state",
                          "scope_key": "fixture-state", "as_of_utc": self.frozen.as_of_utc}
            selector_hash = digest(descriptor)
            extra_descriptors[selector_hash] = descriptor
            extra.append(CoverageRequirement(self.frozen.frozen_input_hash,
                                             member.security_id, "context",
                                             selector_hash, "2025", member.exchange))
        requirements = self.requirements + extra
        records = self.records + [good(req) for req in extra]
        contract = dict(self.contract_wire,
                        requirements=[req.to_dict() for req in requirements],
                        selector_descriptors=dict(self.selector_descriptors, **extra_descriptors),
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
            "schema_version": SCHEMA_VERSION,
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
            "schema_version": SCHEMA_VERSION,
            "db_sha256": hashlib.sha256(empty_db.read_bytes()).hexdigest(),
            "db_generation_hash": digest(db_generation(empty_db)),
            "schema_versions": list(range(2, SCHEMA_VERSION + 1)),
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
            writer.execute("DELETE FROM schema_migration WHERE version=?", (SCHEMA_VERSION,))
            writer.commit()
            self.assertTrue(self.db_path.with_name(self.db_path.name + "-wal").is_file())
            status = json.loads(self.status_path.read_text(encoding="utf-8"))
            status["db_sha256"] = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
            status["db_generation_hash"] = digest(db_generation(self.db_path))
            self.status_path.write_text(json.dumps(status), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema"):
                coverage_module._read_environment(
                    Path(__file__).resolve().parents[1], self.db_path, self.status_path,
                    SCHEMA_VERSION)
        finally:
            writer.close()

    def test_valid_writer_open_wal_read_does_not_reject_transient_shm_marks(self):
        writer = sqlite3.connect(self.db_path)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("UPDATE schema_migration SET version=version WHERE version=?",
                           (SCHEMA_VERSION,))
            writer.commit()
            self.assertTrue(self.db_path.with_name(self.db_path.name + "-wal").is_file())
            status = json.loads(self.status_path.read_text(encoding="utf-8"))
            status["db_sha256"] = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
            status["db_generation_hash"] = digest(db_generation(self.db_path))
            self.status_path.write_text(json.dumps(status), encoding="utf-8")
            first = coverage_module._read_environment(
                Path(__file__).resolve().parents[1], self.db_path, self.status_path,
                SCHEMA_VERSION)
            second = coverage_module._read_environment(
                Path(__file__).resolve().parents[1], self.db_path, self.status_path,
                SCHEMA_VERSION)
            self.assertEqual(first, second)
        finally:
            writer.close()

    def test_active_writer_reservation_never_reads_transient_shm_identity(self):
        writer = sqlite3.connect(self.db_path)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("UPDATE schema_migration SET version=version WHERE version=?",
                           (SCHEMA_VERSION,))
            writer.commit()
            status = json.loads(self.status_path.read_text(encoding="utf-8"))
            status["schema_version"] = SCHEMA_VERSION
            status["schema_versions"] = list(range(2, SCHEMA_VERSION + 1))
            status["db_sha256"] = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
            status["db_generation_hash"] = digest(db_generation(self.db_path))
            self.status_path.write_text(json.dumps(status), encoding="utf-8")
            writer.execute("BEGIN IMMEDIATE")
            shm = self.db_path.with_name(self.db_path.name + "-shm")
            self.assertTrue(shm.is_file())
            original_open = Path.open

            def deny_shm(path, *args, **kwargs):
                if path == shm:
                    raise PermissionError("SQLite owns transient SHM")
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", deny_shm):
                try:
                    identity = coverage_module._read_environment(
                        Path(__file__).resolve().parents[1], self.db_path,
                        self.status_path, SCHEMA_VERSION)
                except PermissionError as exc:
                    self.fail(f"official environment read transient SHM: {exc}")
            self.assertEqual(set(identity["db_sidecar_sha256"]), {"-wal"})
        finally:
            writer.rollback()
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
