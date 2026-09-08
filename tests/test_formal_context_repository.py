"""Context read/write trust boundary uses complete signed source lineage."""

import importlib
import importlib.util
from contextlib import closing
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_evidence import OfficialFetch, SourcePolicy, verify_official_fetch
from ashare_pipeline.formal_registry_manifest import FormalRegistryManifest, VerifiedRegistryBlob
from ashare_pipeline.formal_snapshot_repository import FormalSnapshotRepository
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore, FormalStoredSnapshot
from ashare_pipeline.formal_sources import CalendarSelector
from ashare_pipeline.state_store import StateStore
from tests.test_formal_sources import config
from tests.test_formal_context_schema import canonical, FREEZE


class DigestVerifier:
    def verify(self, raw, *, signature, key_id):
        return key_id == "fixture-key" and signature == hashlib.sha256(raw).hexdigest()


def descriptor(kind="security_state", **changes):
    wire = dict(context_kind=kind, scope_key="fixture-state", security_scope="security",
        request_security="input_security", period_rule="freeze_date_cn", exchange_rule="security_exchange",
        fixed_exchange=None, source="cninfo", dataset="fixture-state", parser_id="fixture-parser",
        parser_version="fixture-v1", mapping_version="fixture-map-v1", normalizer_version="fixture-normalizer-v1",
        request_version="formal-context-request-v1", generation_namespace="fixture-context", referenced_roles=["scoring", "source"],
        calendar_selector=None, bootstrap_calendar=False, allowed_regulatory_flags=[], allowed_event_codes=[])
    wire.update(changes)
    return wire


class FixtureNormalizer:
    """Only test fixtures define how bytes explicitly prove a Context value."""
    normalizer_version = "fixture-normalizer-v1"

    def normalize(self, *, request, snapshot, raw_bytes):
        from ashare_pipeline.formal_context_schema import FormalContextFact
        parsed = json.loads(raw_bytes)
        if set(parsed) != {"value", "no_coverage"}:
            raise ValueError("fixture has no explicit verified response")
        wire = dict(context_kind=request.context_kind, scope_key=request.scope_key,
            security_id=request.security_id, as_of_utc=request.as_of_utc, value=parsed["value"],
            no_coverage=parsed["no_coverage"], published_at_utc=snapshot.published_at_utc,
            effective_at_utc=snapshot.effective_at_utc, source_updated_at_utc=snapshot.source_updated_at_utc,
            captured_at_utc=snapshot.captured_at_utc, refresh_generation=request.refresh_generation,
            source_snapshot_id=snapshot.snapshot_id, source_content_sha256=snapshot.content_sha256,
            parser_id=snapshot.parser_id, parser_version=snapshot.parser_version, mapping_version=snapshot.mapping_version,
            registry_manifest_hash=request.registry_manifest_hash, evidence=request.evidence)
        # Independent canonical fixture computation; the self-referential field is not yet present.
        digest = hashlib.sha256(canonical(dict(schema_version="formal-context-normalization-input-v1",
            descriptor_id=request.descriptor_id, normalizer_version=request.normalizer_version,
            request=request.to_dict(), source_snapshot_manifest_sha256=snapshot.manifest_sha256,
            source_content_sha256=snapshot.content_sha256, fact=wire))).hexdigest()
        wire["evidence"]["normalization_input_hash"] = digest
        return (FormalContextFact.create(**wire),)


class ScoringWrapperIntegrationTests(unittest.TestCase):
    def load_wrapper(self, mutate=None):
        from tests.test_formal_scoring_registry import signed_graph
        from ashare_pipeline.formal_context_schema import FormalContextRegistry, SignedContextRequestResolver
        bundle, _, repository, verifier = signed_graph(context=True, mutate=mutate)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = StateStore(Path(temp.name) / "context.sqlite", registry_signature_verifier=verifier)
        store.initialize()
        for blob in repository.blobs.values():
            store.put_formal_registry_blob(blob)
        store.put_formal_registry_manifest(repository.manifest)
        registry = FormalContextRegistry.load(store, verifier, bundle.manifest.manifest_hash)
        resolver = SignedContextRequestResolver(store, verifier)
        request = resolver.resolve(context_kind="security_state", scope_key="fixture-state", security_id="SZ000001",
            as_of_utc=FREEZE, registry_manifest_hash=bundle.manifest.manifest_hash, upstream_generation="wrapper-test")
        return registry.descriptor_for(request), request

    def test_combined_scoring_wrapper_preserves_legacy_descriptor_identity(self):
        def legacy(docs):
            docs["scoring"].pop("scoring")
            docs["scoring"]["schema_version"] = "formal-context-registry-v1"
        old_descriptor, old_request = self.load_wrapper(legacy)
        try:
            new_descriptor, new_request = self.load_wrapper()
        except ValueError as error:
            self.fail(f"the explicitly versioned combined wrapper must be accepted: {error}")
        self.assertEqual(old_descriptor, new_descriptor)
        self.assertEqual(old_request.descriptor_id, new_request.descriptor_id)
        self.assertEqual(new_request.official_request.dataset, "fixture-state")

    def test_combined_wrapper_rejects_unknown_keys_versions_and_invalid_descriptors(self):
        for mutation in (lambda d: d["scoring"].update(extra=True),
            lambda d: d["scoring"].update(schema_version="formal-scoring-registry-v2"),
            lambda d: d["scoring"].update(scoring=[]),
            lambda d: d["scoring"]["descriptors"][0].update(extra=True)):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.load_wrapper(mutation)


class ContextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_context_repository"))
        self.api = importlib.import_module("ashare_pipeline.formal_context_repository")
        self.schema = importlib.import_module("ashare_pipeline.formal_context_schema")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "state.sqlite"
        self.verifier = DigestVerifier()
        self.raw_calendar_requests = {}
        self.raw = FormalSnapshotStore(self.root / "raw", calendar_binding_resolver=self.resolve_raw_calendar)
        self.store = StateStore(self.db, formal_snapshot_store=self.raw, registry_signature_verifier=self.verifier)
        self.store.initialize()
        self.snapshots = FormalSnapshotRepository(self.raw.root, self.store)
        self.install()
        self.repo = self.api.FormalContextRepository(self.store, self.snapshots, self.verifier)
        self.resolver = self.schema.SignedContextRequestResolver(self.store, self.verifier)

    def install(self, descriptors=None, configs=None, purpose="official"):
        self.descriptors = [descriptor()] if descriptors is None else descriptors
        configs = [config(dataset="fixture-state", exchange_scope="SZ")] if configs is None else configs
        roles = ("source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event")
        raws = {role: canonical(dict(registry_role=role, schema_version="fixture-v1")) for role in roles}
        raws["source"] = canonical(dict(registry_role="source", schema_version="formal-source-registry-v1", configs=configs))
        raws["scoring"] = canonical(dict(registry_role="scoring", schema_version="formal-context-registry-v1", descriptors=self.descriptors))
        hashes = {role + "_registry_hash": hashlib.sha256(raw).hexdigest() for role, raw in raws.items()}
        approval = "fixture-approval" if purpose == "official" else None
        root = canonical(dict(schema_version="formal-registry-manifest-v1", purpose=purpose, approval_id=approval, **hashes))
        self.manifest = FormalRegistryManifest.from_signed_bytes(root, hashlib.sha256(root).hexdigest(), "fixture-key", self.verifier)
        for role, raw in raws.items():
            digest = hashlib.sha256(raw).hexdigest()
            binding = canonical(dict(child_sha256=digest, registry_manifest_hash=self.manifest.manifest_hash, registry_role=role))
            blob = VerifiedRegistryBlob(registry_role=role, registry_hash=digest, canonical_json=raw,
                signature=digest, key_id="fixture-key", approval_id=approval,
                declared_registry_manifest_hash=self.manifest.manifest_hash,
                binding_signature=hashlib.sha256(binding).hexdigest(), binding_key_id="fixture-key")
            # A fixture root owns its child binding. Each installation replaces only this disposable graph.
            self.sql("DELETE FROM formal_registry_blob WHERE registry_hash = ?", (digest,))
            self.store.put_formal_registry_blob(blob)
        self.store.put_formal_registry_manifest(self.manifest)

    def sql(self, sql, args=()):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(sql, args)
            conn.commit()

    def request(self, **changes):
        args = dict(kind="security_state", scope_key="fixture-state", security_id="SZ000001",
            as_of_utc=FREEZE, registry_manifest_hash=self.manifest.manifest_hash, upstream_generation="fixture-upstream-v1")
        args.update(changes)
        args["context_kind"] = args.pop("kind")
        return self.resolver.resolve(**args)

    def produce(self, request=None, *, value=None, no_coverage=False, task_kind="formal_context",
                published="2026-08-20T07:00:00+00:00", updated=None, captured="2026-09-04T07:00:00+00:00", raw=None,
                complete=False, lease_seconds=300):
        request = request or self.request()
        value = dict(is_st=False, is_star_st=False, listing_status="listed", forced_delist_risk=False, suspended=False) if value is None else value
        task = self.store.enqueue_formal_task(task_kind, hashlib.sha256((request.refresh_generation + published + captured + str(value) + repr(raw) + task_kind).encode()).hexdigest(), request.refresh_generation, {})
        worker = "fixture-worker"
        self.store.lease_next_formal_task((task_kind,), worker, lease_seconds)
        raw = canonical(dict(value=value, no_coverage=no_coverage)) if raw is None else raw
        binding = request.calendar_binding
        if binding is not None:
            request.to_dict()  # Recheck the sealed descriptor-derived input; never cache a binding.
            self.raw_calendar_requests[request.official_request.canonical_json_bytes()] = request
        fetch = OfficialFetch(request=request.official_request, raw_bytes=raw,
            original_url="https://www.cninfo.com.cn/fixture/context.json", published_at_utc=published,
            published_precision="date_only" if binding else "timestamp", source_updated_at_utc=updated,
            captured_at_utc=captured, effective_at_utc="2026-08-21T07:00:00+00:00" if binding else published,
            effective_time_evidence_hash=binding.manifest_sha256 if binding else None,
            refresh_generation=request.refresh_generation, parser_id=request.parser_id,
            parser_version=request.parser_version, mapping_version=request.mapping_version,
            declared_security_id=request.official_request.security_id, declared_period=request.official_request.period_or_date)
        verification = verify_official_fetch(fetch, SourcePolicy.cninfo(), calendar_binding=binding)
        self.assertEqual(verification.status, "verified", verification)
        ref = self.snapshots.persist_verified(fetch, verification, producing_task_id=task, worker_id=worker)
        if complete:
            self.store.complete_formal_task(task, worker, {"snapshot": ref.snapshot_id})
        return request, ref, raw

    def resolve_raw_calendar(self, candidate):
        """Hermetic collection bridge: only signed, seal-checked inputs reach the real resolver."""
        request = self.raw_calendar_requests.get(candidate.canonical_json_bytes())
        if request is None:
            raise ValueError("unregistered fixture calendar request")
        wire = request.to_dict()
        if request.official_request.canonical_json_bytes() != candidate.canonical_json_bytes():
            raise ValueError("fixture calendar request identity mismatch")
        selector = CalendarSelector(**wire["calendar_selector"])
        return self.repo.resolve_verified_calendar_binding(selector, candidate.exchange,
            wire["as_of_utc"], wire["registry_manifest_hash"])

    def normalize(self, request, ref, raw, normalizer=None, *, task_id=None, worker_id="fixture-worker"):
        registry = self.schema.FormalContextRegistry.load(self.store, self.verifier, self.manifest.manifest_hash)
        return registry.normalize_verified(request, ref, raw, normalizer or FixtureNormalizer(),
            task_id=ref.producing_task_id if task_id is None else task_id, worker_id=worker_id)

    def put(self, **kwargs):
        request, ref, raw = self.produce(**kwargs)
        receipt = self.normalize(request, ref, raw)
        self.store.put_formal_context_facts(receipt)
        self.store.complete_formal_task(ref.producing_task_id, "fixture-worker", {"snapshot": ref.snapshot_id})
        return receipt.facts[0], ref, receipt

    def get(self, **changes):
        args = dict(kind="security_state", scope_key="fixture-state", security_id="SZ000001", as_of_utc=FREEZE,
            registry_manifest_hash=self.manifest.manifest_hash)
        args.update(changes)
        return self.repo.get_verified(**args)

    def test_signed_descriptor_exact_identity_and_no_direct_trust_minting(self):
        request = self.request()
        self.assertEqual(request.official_request.period_or_date, "2026-08-31")
        self.assertEqual(request.official_request.exchange, "SZ")
        self.assertEqual(request.descriptor_id, hashlib.sha256(canonical(descriptor())).hexdigest())
        self.assertEqual(request.evidence["normalizer_version"], "fixture-normalizer-v1")
        self.assertEqual(request.request_version, "formal-context-request-v1")
        self.assertEqual(len(request.refresh_generation), 64)
        self.assertEqual(request.refresh_generation, self.request().refresh_generation)
        for cls in (self.schema.FormalContextRegistry, self.schema.FormalContextRequest, self.schema.FormalContextNormalization):
            with self.assertRaises(ValueError):
                cls()
        for change in (dict(scope_key="fixture"), dict(security_id=None), dict(security_id="sz000001"),
            dict(security_id="SH600000"), dict(as_of_utc="2026-08-31"), dict(registry_manifest_hash="f" * 64)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.request(**change)

    def test_context_writer_persists_before_completion_without_publishing_leased_facts(self):
        request, ref, raw = self.produce(complete=False)
        receipt = self.normalize(request, ref, raw)
        self.store.put_formal_context_facts(receipt)
        self.assertEqual(receipt.writer, dict(task_id=ref.producing_task_id, worker_id="fixture-worker",
            refresh_generation=ref.refresh_generation,
            receipt=self.store.get_formal_task_snapshot_receipt(ref.producing_task_id)))
        with self.assertRaisesRegex(ValueError, "verified formal_context producer"):
            self.get()
        with self.assertRaisesRegex(ValueError, "verified formal_context producer"):
            self.store.list_formal_context_facts(registry_manifest_hash=self.manifest.manifest_hash)
        self.store.complete_formal_task(ref.producing_task_id, "fixture-worker", {"snapshot": ref.snapshot_id})
        self.assertEqual(self.get().id, receipt.facts[0].id)

    def test_context_writer_rejects_wrong_worker_and_task(self):
        request, ref, raw = self.produce()
        for changes, reason in ((dict(worker_id="foreign-worker"), "lease expired or ownership changed"),
                (dict(task_id="00000000-0000-4000-8000-000000000099"), "task does not match snapshot producer")):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, reason):
                self.normalize(request, ref, raw, **changes)

    def test_context_writer_rejects_expired_lease_at_normalize_and_put(self):
        request, ref, raw = self.produce()
        receipt = self.normalize(request, ref, raw)
        self.sql("UPDATE formal_collection_task SET lease_expires_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", ref.producing_task_id))
        with self.assertRaisesRegex(ValueError, "lease expired or ownership changed"):
            self.normalize(request, ref, raw)
        with self.assertRaisesRegex(ValueError, "lease expired or ownership changed"):
            self.store.put_formal_context_facts(receipt)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM formal_context_fact").fetchone()[0], 0)

    def test_context_writer_rechecks_lease_after_normalizer_callback(self):
        request, ref, raw = self.produce()
        fixture = self
        class ExpiringNormalizer(FixtureNormalizer):
            def normalize(self, **kwargs):
                facts = super().normalize(**kwargs)
                fixture.sql("UPDATE formal_collection_task SET lease_expires_at=? WHERE id=?",
                    ("2000-01-01T00:00:00+00:00", ref.producing_task_id))
                return facts
        with self.assertRaisesRegex(ValueError, "lease expired or ownership changed"):
            self.normalize(request, ref, raw, ExpiringNormalizer())

    def test_context_writer_new_owner_recovers_same_receipt_and_rejects_old_capability(self):
        request, ref, raw = self.produce()
        original = self.normalize(request, ref, raw)
        self.store.put_formal_context_facts(original)
        self.sql("UPDATE formal_collection_task SET lease_expires_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", ref.producing_task_id))
        recovered = self.store.lease_next_formal_task(("formal_context",), "recovered-worker", 300)
        self.assertEqual(recovered["id"], ref.producing_task_id)
        with self.assertRaisesRegex(ValueError, "lease expired or ownership changed"):
            self.store.put_formal_context_facts(original)
        current = self.normalize(request, ref, raw, worker_id="recovered-worker")
        self.assertEqual(current.facts[0].id, original.facts[0].id)
        self.store.put_formal_context_facts(current)
        with self.assertRaisesRegex(ValueError, "verified formal_context producer"):
            self.get()
        self.store.complete_formal_task(ref.producing_task_id, "recovered-worker", {"snapshot": ref.snapshot_id})
        self.assertEqual(self.get().id, original.facts[0].id)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM formal_context_fact").fetchone()[0], 1)

    def test_context_writer_rolls_back_when_lease_expires_after_insert(self):
        request, ref, raw = self.produce()
        receipt = self.normalize(request, ref, raw)
        self.sql("""CREATE TRIGGER fixture_expire_context_writer AFTER INSERT ON formal_context_fact
            BEGIN UPDATE formal_collection_task SET lease_expires_at='2000-01-01T00:00:00+00:00'
            WHERE id=(SELECT producing_task_id FROM formal_source_snapshot WHERE id=NEW.source_snapshot_id); END""")
        with self.assertRaisesRegex(ValueError, "lease expired or ownership changed"):
            self.store.put_formal_context_facts(receipt)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM formal_context_fact").fetchone()[0], 0)
            expiry = conn.execute("SELECT lease_expires_at FROM formal_collection_task WHERE id=?",
                (ref.producing_task_id,)).fetchone()[0]
        self.assertNotEqual(expiry, "2000-01-01T00:00:00+00:00")

    def test_missing_duplicate_and_mismatched_descriptor_fail_closed(self):
        for descriptors in ([], [descriptor(), descriptor()], [descriptor(parser_id="other")],
            [descriptor(mapping_version="other")], [descriptor(referenced_roles=["source"])],
            [descriptor(exchange_rule="fixed_exchange", fixed_exchange="SH")],
            [descriptor(period_rule="last_day")], [descriptor(scope_key="*")]):
            with self.subTest(descriptors=descriptors):
                self.install(descriptors=descriptors)
                with self.assertRaises(ValueError):
                    self.request()

    def test_normalizer_version_raw_and_direct_persistence_bypass_rejected(self):
        request, ref, raw = self.produce()
        normalizer = FixtureNormalizer()
        normalizer.normalizer_version = "unsigned-version"
        for n, data, snapshot in ((normalizer, raw, ref), (FixtureNormalizer(), b"wrong bytes", ref),
            (FixtureNormalizer(), raw, replace(ref, dataset="other"))):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.normalize(request, snapshot, data, n)
        receipt = self.normalize(request, ref, raw)
        with self.assertRaises(ValueError):
            self.store.put_formal_context_facts(receipt.facts)
        with self.assertRaises(ValueError):
            self.store.put_formal_context_facts(object.__new__(self.schema.FormalContextNormalization))

    def test_normalization_hash_binds_scientific_value_and_verified_source_manifest(self):
        request, ref, raw = self.produce()
        schema = self.schema
        class WrongHashNormalizer(FixtureNormalizer):
            def normalize(self, **kwargs):
                fact = super().normalize(**kwargs)[0]
                wire = fact.to_dict()
                wire.pop("id")
                wire["evidence"]["normalization_input_hash"] = "f" * 64
                return (schema.FormalContextFact.create(**wire),)
        with self.assertRaisesRegex(ValueError, "normalization"):
            self.normalize(request, ref, raw, WrongHashNormalizer())

    def test_persistence_idempotence_list_detachment_and_verified_read(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            request, ref, raw = self.produce()
            receipt = self.normalize(request, ref, raw)
            fact = receipt.facts[0]
            self.store.put_formal_context_facts(receipt)
            self.store.put_formal_context_facts(receipt)
            self.store.complete_formal_task(ref.producing_task_id, "fixture-worker", {"snapshot": ref.snapshot_id})
            found = self.store.list_formal_context_facts(registry_manifest_hash=self.manifest.manifest_hash)
            self.assertEqual([f.id for f in found], [fact.id])
            self.assertEqual(self.get().id, fact.id)
            found[0].value["is_st"] = True
            self.assertFalse(self.get().value["is_st"])
            with closing(sqlite3.connect(self.db)) as conn:
                rows = conn.execute("SELECT created_at_utc FROM formal_context_fact").fetchall()
            self.assertEqual(len(rows), 1)

    def test_non_context_producer_is_never_context_evidence(self):
        for kind in ("formal_statement", "formal_universe_source"):
            with self.subTest(kind=kind):
                request, ref, raw = self.produce(task_kind=kind, captured="2026-09-05T07:00:00+00:00" if kind == "formal_statement" else "2026-09-06T07:00:00+00:00")
                with self.assertRaises(ValueError):
                    self.normalize(request, ref, raw)

    def test_db_receipt_task_and_raw_tamper_fail_closed(self):
        fact, ref, receipt = self.put()
        for table, field, value, key, identity in (
            ("formal_context_fact", "value_json", "{}", "id", fact.id),
            ("formal_context_fact", "registry_manifest_hash", "f" * 64, "id", fact.id),
            ("formal_task_snapshot_receipt", "refresh_generation", "wrong", "task_id", ref.producing_task_id),
            ("formal_collection_task", "kind", "formal_statement", "id", ref.producing_task_id),
            ("formal_collection_task", "result_json", None, "id", ref.producing_task_id),
            ("formal_source_snapshot", "request_fingerprint", "f" * 64, "id", ref.snapshot_id)):
            with self.subTest(table=table, field=field), closing(sqlite3.connect(self.db)) as conn:
                original = conn.execute(f"SELECT {field} FROM {table} WHERE {key}=?", (identity,)).fetchone()[0]
                self.sql(f"UPDATE {table} SET {field}=? WHERE {key}=?", (value, identity))
                try:
                    with self.assertRaises(ValueError):
                        self.get()
                finally:
                    self.sql(f"UPDATE {table} SET {field}=? WHERE {key}=?", (original, identity))
        for path in (Path(ref.content_path), Path(ref.manifest_path)):
            original = path.read_bytes()
            try:
                path.write_bytes(b"tamper")
                with self.assertRaises(ValueError):
                    self.get()
            finally:
                path.write_bytes(original)

    def test_put_revalidates_only_incoming_logical_generation_while_public_list_stays_fail_closed(self):
        self.install(descriptors=[descriptor(), descriptor("industry_snapshot", scope_key="fixture-industry")])
        unrelated, unrelated_ref, _ = self.put(
            request=self.request(kind="industry_snapshot", scope_key="fixture-industry"),
            value=dict(classification_system="SW2021", primary_industry="bank", secondary_industry="regional",
                source_version="fixture-v1", effective_date="2026-08-20", mapping_sha256="1" * 64))
        self.sql("UPDATE formal_source_snapshot SET content_sha256=? WHERE id=?", ("f" * 64, unrelated_ref.snapshot_id))
        request, ref, raw = self.produce()
        receipt = self.normalize(request, ref, raw)
        self.store.put_formal_context_facts(receipt)
        self.store.put_formal_context_facts(receipt)
        self.store.complete_formal_task(ref.producing_task_id, "fixture-worker", {"snapshot": ref.snapshot_id})
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM formal_context_fact WHERE source_snapshot_id=?",
                (ref.snapshot_id,)).fetchone()[0], 1)
        self.assertEqual(self.get().id, receipt.facts[0].id)
        with self.assertRaisesRegex(ValueError, "content hash does not match manifest"):
            self.store.list_formal_context_facts(registry_manifest_hash=self.manifest.manifest_hash)
        self.sql("UPDATE formal_source_snapshot SET content_sha256=? WHERE id=?", (unrelated_ref.content_sha256, unrelated_ref.snapshot_id))
        self.assertEqual({fact.id for fact in self.store.list_formal_context_facts(
            registry_manifest_hash=self.manifest.manifest_hash)}, {unrelated.id, receipt.facts[0].id})

    def test_calendar_exchange_is_a_logical_generation_discriminator(self):
        anchor = self.install_calendars(exchanges=("SH",))["SH"][0]
        wire = anchor.to_dict()
        wire.pop("id")
        wire["value"]["exchange"] = "SZ"
        # A pure key boundary only: this changed record is never normalized or persisted.
        alternate = self.schema.FormalContextFact.create(**wire)
        original_key = self.api._logical_key(anchor)
        alternate_key = self.api._logical_key(alternate)
        self.assertEqual(original_key[:4], alternate_key[:4])
        self.assertEqual(original_key[5:], alternate_key[5:])
        self.assertEqual((original_key[4], alternate_key[4]), ("SH", "SZ"))
        self.assertNotEqual(original_key, alternate_key)

    def test_same_generation_conflicts_preserve_existing_version(self):
        old, _, _ = self.put()
        request, ref, raw = self.produce(value=dict(is_st=True, is_star_st=False, listing_status="listed", forced_delist_risk=False, suspended=False))
        receipt = self.normalize(request, ref, raw)
        with self.assertRaises(ValueError):
            self.store.put_formal_context_facts(receipt)
        self.assertEqual(self.get().id, old.id)

    def test_distinct_upstream_generations_preserve_and_select_history(self):
        old, _, _ = self.put()
        new, _, _ = self.put(request=self.request(upstream_generation="fixture-upstream-v2"),
            published="2026-08-21T07:00:00+00:00", captured="2026-08-21T08:00:00+00:00",
            value=dict(is_st=True, is_star_st=False, listing_status="listed", forced_delist_risk=False, suspended=False))
        self.assertNotEqual(old.refresh_generation, new.refresh_generation)
        self.assertEqual(self.get().id, new.id)
        facts = self.store.list_formal_context_facts(registry_manifest_hash=self.manifest.manifest_hash)
        self.assertEqual([fact.id for fact in facts], sorted([old.id, new.id]))
        with self.assertRaises(TypeError):
            self.resolver.resolve("security_state", "fixture-state", "SZ000001", FREEZE, self.manifest.manifest_hash)

    def test_source_update_order_precedes_capture_and_missing_update(self):
        self.put()
        second, _, _ = self.put(request=self.request(upstream_generation="fixture-upstream-v2"),
            updated="2026-08-20T08:00:00+00:00", captured="2026-08-20T09:00:00+00:00")
        self.assertEqual(self.get().id, second.id)
        third, _, _ = self.put(request=self.request(upstream_generation="fixture-upstream-v3"),
            updated="2026-08-21T08:00:00+00:00", captured="2026-08-21T09:00:00+00:00")
        self.assertEqual(self.get().id, third.id)

    def test_public_resolver_requires_signed_request_version_and_exact_context_kind(self):
        request = self.resolver.resolve(context_kind="security_state", scope_key="fixture-state",
            security_id="SZ000001", as_of_utc=FREEZE, registry_manifest_hash=self.manifest.manifest_hash,
            upstream_generation="fixture-upstream-v1")
        self.assertEqual(request.request_version, "formal-context-request-v1")
        with self.assertRaises(ValueError):
            self.request(upstream_generation="")
        self.install([descriptor(request_version=" ")])
        with self.assertRaises(ValueError):
            self.request()

    def test_read_reloads_signature_gate_and_never_reruns_semantic_normalizer(self):
        fact, _, _ = self.put()
        with patch.object(FixtureNormalizer, "normalize", side_effect=AssertionError("historical semantic replay forbidden")):
            restarted = StateStore(self.db, formal_snapshot_store=self.raw, registry_signature_verifier=self.verifier)
            snapshots = FormalSnapshotRepository(self.raw.root, restarted)
            repo = self.api.FormalContextRepository(restarted, snapshots, self.verifier)
            self.assertEqual(repo.get_verified("security_state", "fixture-state", "SZ000001", FREEZE, self.manifest.manifest_hash).id, fact.id)
        self.sql("UPDATE formal_registry_blob SET signature='tampered' WHERE registry_role='event'")
        with self.assertRaises(ValueError):
            self.get()

    def test_sql_canonical_scientific_rewrite_without_input_hash_update_is_rejected(self):
        fact, _, _ = self.put()
        wire = fact.to_dict()
        wire.pop("id")
        wire["value"]["is_st"] = True
        modified = self.schema.FormalContextFact.create(**wire)
        self.sql("UPDATE formal_context_fact SET id=?,value_json=? WHERE id=?", (modified.id, canonical(modified.value).decode(), fact.id))
        with self.assertRaisesRegex(ValueError, "normalization"):
            self.get()

    def test_missing_receipt_or_source_is_not_no_coverage(self):
        fact, ref, _ = self.put()
        self.sql("DELETE FROM formal_task_snapshot_receipt WHERE task_id=?", (ref.producing_task_id,))
        with self.assertRaises(ValueError):
            self.get()

    def test_duplicate_json_keys_in_stored_fact_are_rejected(self):
        fact, _, _ = self.put()
        self.sql("UPDATE formal_context_fact SET value_json=? WHERE id=?", ('{"is_st":false,"is_st":true}', fact.id))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.get()

    def test_equal_leading_versions_are_explicit_conflict(self):
        self.put()
        self.put(request=self.request(upstream_generation="fixture-upstream-v2"))
        with self.assertRaisesRegex(ValueError, "leading"):
            self.get()

    def install_calendars(self, *, date_only=False, exchanges=("SH", "SZ", "BJ")):
        descriptors = [descriptor("trading_calendar", scope_key="fixture-calendar-" + ex,
            security_scope="none", request_security="none", period_rule="none", exchange_rule="fixed_exchange",
            fixed_exchange=ex, dataset="trading_calendar", bootstrap_calendar=True) for ex in exchanges]
        configs = [config(dataset="trading_calendar", bootstrap_calendar=True)]
        if date_only:
            selector = asdict(CalendarSelector("trading_calendar", "fixture-calendar-SZ", "SZ", "visible_at_freeze"))
            descriptors.append(descriptor(calendar_selector=selector))
            configs.append(config(dataset="fixture-state", exchange_scope="SZ", calendar_selector=selector))
        self.install(descriptors, configs)
        calendars = {}
        for exchange in exchanges:
            request = self.request(kind="trading_calendar", scope_key="fixture-calendar-" + exchange, security_id=None)
            calendars[exchange] = self.put(request=request, published="2026-08-19T07:00:00+00:00",
                value=dict(exchange=exchange, calendar_version="fixture-v1", trading_days=["2026-08-21", "2026-08-31", "2026-09-02"]))
        return calendars

    def test_calendar_exchange_separation_binding_substitutions_and_no_weekday_inference(self):
        calendars = self.install_calendars()
        resolver = self.api.build_effective_time_resolver(self.repo)
        for exchange in ("SH", "SZ", "BJ"):
            selector = CalendarSelector("trading_calendar", "fixture-calendar-" + exchange, exchange, "visible_at_freeze")
            binding = self.repo.resolve_verified_calendar_binding(selector, exchange, FREEZE, self.manifest.manifest_hash)
            self.assertEqual(binding.snapshot_id, calendars[exchange][1].snapshot_id)
            self.assertEqual(resolver.next_exchange_close(exchange, "2026-08-31", binding), "2026-09-02T15:00:00+08:00")
            with self.assertRaisesRegex(ValueError, "next session"):
                resolver.next_exchange_close(exchange, "2026-09-02", binding)
            if exchange != "SZ":
                continue
            for field, bad in dict(snapshot_id="00000000-0000-4000-8000-000000000099", manifest_sha256="f" * 64,
                selector_hash="f" * 64, registry_manifest_hash="f" * 64, prerequisite_task_id="00000000-0000-4000-8000-000000000099",
                freeze_at_utc="2026-08-30T07:00:00+00:00", exchange="SZ" if exchange != "SZ" else "SH").items():
                with self.subTest(exchange=exchange, field=field), self.assertRaises(ValueError):
                    resolver.next_exchange_close(exchange, "2026-08-31", replace(binding, **{field: bad}))

    def test_date_only_uses_calendar_provenance_without_recursive_self_lookup(self):
        self.install_calendars(date_only=True)
        request = self.request()
        self.assertIsNotNone(request.calendar_binding)
        fact, _, _ = self.put(request=request, published="2026-08-19T16:00:00+00:00")
        self.assertEqual(self.get().id, fact.id)
        self.assertEqual(fact.evidence["calendar_binding"]["selector_hash"], request.calendar_binding.selector_hash)
        for change in (dict(dataset="other"), dict(exchange="SH")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.resolve_raw_calendar(replace(request.official_request, **change))
        selector = CalendarSelector("trading_calendar", "fixture-calendar-SH", "SZ", "visible_at_freeze")
        with self.assertRaises(ValueError):
            self.repo.resolve_verified_calendar_binding(selector, "SZ", FREEZE, self.manifest.manifest_hash)
        with self.assertRaises(ValueError):
            self.repo.resolve_verified_calendar_binding(CalendarSelector(**request.calendar_selector), "SZ", FREEZE, "f" * 64)
        original = request.canonical_bytes()
        changed = request.to_dict()
        changed["registry_manifest_hash"] = "f" * 64
        object.__setattr__(request, "_canonical", canonical(changed))
        try:
            with self.assertRaisesRegex(ValueError, "mutated"):
                self.resolve_raw_calendar(self.schema.OfficialRequest(**changed["official_request"]))
        finally:
            object.__setattr__(request, "_canonical", original)

    def test_duplicate_leading_calendar_is_not_resolved_by_insertion_order(self):
        self.install_calendars()
        request = self.request(kind="trading_calendar", scope_key="fixture-calendar-SZ", security_id=None,
            upstream_generation="fixture-upstream-v2")
        self.put(request=request, published="2026-08-19T07:00:00+00:00",
            value=dict(exchange="SZ", calendar_version="fixture-v1", trading_days=["2026-08-21", "2026-08-31", "2026-09-02"]))
        selector = CalendarSelector("trading_calendar", "fixture-calendar-SZ", "SZ", "visible_at_freeze")
        with self.assertRaisesRegex(ValueError, "leading"):
            self.repo.resolve_verified_calendar_binding(selector, "SZ", FREEZE, self.manifest.manifest_hash)

    def test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor(self):
        calendars = self.install_calendars(date_only=True, exchanges=("SZ",))
        c1 = calendars["SZ"][0]
        r1 = self.request(upstream_generation="fixture-context-v1")
        d1, _, _ = self.put(request=r1, published="2026-08-19T16:00:00+00:00", lease_seconds=3600)
        c2_request = self.request(kind="trading_calendar", scope_key="fixture-calendar-SZ",
            security_id=None, upstream_generation="fixture-calendar-v2")
        c2, c2_ref, _ = self.put(request=c2_request, published="2026-08-20T07:00:00+00:00", lease_seconds=3600,
            value=dict(exchange="SZ", calendar_version="fixture-v2",
                trading_days=["2026-08-21", "2026-08-31", "2026-09-02"]))
        self.assertNotEqual(c1.id, c2.id)
        r2 = self.request(upstream_generation="fixture-context-v2")
        self.assertEqual(r2.calendar_binding.manifest_sha256, c2_ref.manifest_sha256)
        self.assertNotEqual(r1.refresh_generation, r2.refresh_generation)
        d2, _, _ = self.put(request=r2, published="2026-08-19T16:00:00+00:00", lease_seconds=3600,
            updated="2026-08-22T07:00:00+00:00",
            value=dict(is_st=True, is_star_st=False, listing_status="listed",
                forced_delist_risk=False, suspended=False))
        facts = self.store.list_formal_context_facts(registry_manifest_hash=self.manifest.manifest_hash,
            context_kind="security_state", scope_key="fixture-state", security_id="SZ000001", as_of_utc=FREEZE)
        self.assertEqual({fact.id for fact in facts}, {d1.id, d2.id})
        self.assertEqual(self.get().id, d2.id)
        self.assertEqual(d1.evidence["calendar_binding"], asdict(r1.calendar_binding))
        self.assertEqual(d2.evidence["calendar_binding"], asdict(r2.calendar_binding))
        # The old row remains evidence, not something a newer leading D2 may hide.
        self.sql("DELETE FROM formal_context_fact WHERE id=?", (c1.id,))
        with self.assertRaises(ValueError):
            self.get()

    def test_historical_read_capability_is_target_bound_and_unforgeable(self):
        calendars = self.install_calendars(date_only=True, exchanges=("SZ",))
        original = self.request()
        fact, ref, _ = self.put(request=original, published="2026-08-19T16:00:00+00:00", lease_seconds=3600)
        capability = self.capture_historical_read()
        snapshots = FormalSnapshotRepository(self.raw.root, self.store)
        expected = snapshots.read_verified_raw(ref, historical_read=capability)
        stored = FormalStoredSnapshot(ref.content_path, ref.manifest_path, ref.content_sha256, ref.manifest_sha256)
        for forged in (object(), original.calendar_binding, object.__new__(type(capability))):
            with self.subTest(forged=type(forged)), self.assertRaisesRegex(ValueError, "historical.*capability"):
                self.raw.read_verified_raw(stored, historical_read=forged)
        other_store = FormalSnapshotStore(self.raw.root, calendar_binding_resolver=self.resolve_raw_calendar)
        with self.assertRaisesRegex(ValueError, "historical.*store"):
            other_store.read_verified_raw(stored, historical_read=capability)
        with self.assertRaisesRegex(ValueError, "historical.*target"):
            snapshots.read_verified_raw(calendars["SZ"][1], historical_read=capability)
        with self.assertRaisesRegex(ValueError, "reference does not match"):
            snapshots.read_verified_raw(replace(ref, security_id="SZ000002"), historical_read=capability)
        self.assertEqual(snapshots.read_verified_raw(ref, historical_read=capability), expected)
        with self.assertRaises(TypeError):
            self.raw.write_verified(None, None, producing_task_id=None, historical_read=capability)

    def test_historical_capability_roundtrips_full_fact_record_and_rejects_id_changes(self):
        calendars = self.install_calendars(date_only=True, exchanges=("SZ",))
        fact, ref, _ = self.put(published="2026-08-19T16:00:00+00:00", lease_seconds=3600)
        record = fact.to_dict()
        scientific = json.loads(fact.canonical_bytes())
        self.assertNotIn("id", scientific)
        self.assertEqual(record["id"], fact.id)
        self.assertEqual(self.schema.FormalContextFact.from_dict(record).canonical_bytes(), fact.canonical_bytes())
        with self.assertRaisesRegex(ValueError, "ID is missing"):
            self.schema.FormalContextFact.from_dict(scientific)
        swapped = dict(record, id=calendars["SZ"][0].id)
        with self.assertRaisesRegex(ValueError, "canonical ID mismatch"):
            self.schema.FormalContextFact.from_dict(swapped)
        capability = self.capture_historical_read()
        expected = self.snapshots.read_verified_raw(ref, historical_read=capability)
        for changed_id in ("f" * 64, None):
            with self.subTest(changed_id=changed_id):
                self.sql("UPDATE formal_context_fact SET id=? WHERE source_snapshot_id=?", (changed_id, ref.snapshot_id))
                try:
                    with self.assertRaisesRegex(ValueError, "historical read persisted Fact changed"):
                        self.snapshots.read_verified_raw(ref, historical_read=capability)
                finally:
                    self.sql("UPDATE formal_context_fact SET id=? WHERE source_snapshot_id=?", (fact.id, ref.snapshot_id))
        self.assertEqual(self.snapshots.read_verified_raw(ref, historical_read=capability), expected)

    def test_historical_calendar_anchor_tamper_invalidates_existing_capability(self):
        calendars = self.install_calendars(date_only=True, exchanges=("SZ",))
        anchor, anchor_ref, _ = calendars["SZ"]
        fact, ref, _ = self.put(published="2026-08-19T16:00:00+00:00", lease_seconds=3600)
        capability = self.capture_historical_read()
        snapshots = FormalSnapshotRepository(self.raw.root, self.store)
        for table, field, bad, key, identity in (
            ("formal_context_fact", "value_json", "{}", "id", anchor.id),
            ("formal_collection_task", "result_json", None, "id", anchor_ref.producing_task_id),
            ("formal_task_snapshot_receipt", "refresh_generation", "wrong", "task_id", anchor_ref.producing_task_id),
            ("formal_source_snapshot", "content_sha256", "f" * 64, "id", anchor_ref.snapshot_id)):
            with self.subTest(table=table), closing(sqlite3.connect(self.db)) as connection:
                original = connection.execute(f"SELECT {field} FROM {table} WHERE {key}=?", (identity,)).fetchone()[0]
                self.sql(f"UPDATE {table} SET {field}=? WHERE {key}=?", (bad, identity))
                try:
                    with self.assertRaises(ValueError):
                        snapshots.read_verified_raw(ref, historical_read=capability)
                finally:
                    self.sql(f"UPDATE {table} SET {field}=? WHERE {key}=?", (original, identity))
        path = Path(anchor_ref.content_path)
        original = path.read_bytes()
        try:
            path.write_bytes(b"tampered historical calendar")
            with self.assertRaises(ValueError):
                snapshots.read_verified_raw(ref, historical_read=capability)
        finally:
            path.write_bytes(original)

    def capture_historical_read(self):
        """Observe only a capability produced by a successful real public read."""
        captured = []
        original_read = self.raw.read_verified_raw
        def observe(stored, *, historical_read=None):
            if historical_read is None:
                return original_read(stored)
            result = original_read(stored, historical_read=historical_read)
            captured.append(historical_read)
            return result
        with patch.object(self.raw, "read_verified_raw", side_effect=observe):
            self.get()
        self.assertTrue(captured, "historical Context must use a sealed historical raw read")
        return captured[-1]

    def test_descriptor_allowlists_reject_unknown_regulatory_and_event_codes(self):
        for kind, value, allowed in (("regulatory_state", dict(flags=[dict(flag_id="fixture-flag", active=True)]), dict(allowed_regulatory_flags=["fixture-flag"])),
            ("event_calendar", dict(events=[dict(event_id="fixture-event", event_date="2026-09-01", quantified_value="1", unit="CNY")]), dict(allowed_event_codes=["fixture-event"]))):
            with self.subTest(kind=kind):
                # Use a fresh signed root before any stored rows; a rejected normalizer must not append.
                self.install([descriptor(kind)])
                request, ref, raw = self.produce(request=self.request(kind=kind), value=value)
                with self.assertRaises(ValueError):
                    self.normalize(request, ref, raw)

    def test_request_capability_rejects_alias_mutation_and_source_identity_substitution(self):
        request, ref, raw = self.produce()
        detached = request.official_request
        object.__setattr__(detached, "security_id", "SZ000002")
        self.assertEqual(request.official_request.security_id, "SZ000001")
        for field, value in (("parser_id", "other"), ("parser_version", "other"), ("mapping_version", "other"),
            ("request_fingerprint", "f" * 64), ("security_id", "SZ000002"), ("period_or_date", "2026-08-30")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.normalize(request, replace(ref, **{field: value}), raw)
        object.__setattr__(request, "_canonical", b"{}")
        with self.assertRaises(ValueError):
            self.normalize(request, ref, raw)

    def test_signed_event_allowlist_preserves_negative_quantified_evidence(self):
        self.install([descriptor("event_calendar", allowed_event_codes=["fixture-change"])])
        value = dict(events=[dict(event_id="fixture-change", event_date="2026-09-01",
            quantified_value="-1.25", unit="CNY")])
        fact, _, _ = self.put(request=self.request(kind="event_calendar"), value=value)
        self.assertEqual(self.get(kind="event_calendar").id, fact.id)
        self.assertEqual(fact.value, value)

    def test_private_fact_check_cannot_use_forged_or_mutated_request(self):
        check = getattr(self.schema, "_verify_context_fact", None)
        self.assertTrue(callable(check), "private validation must enforce the resolved request seal")
        request, ref, raw = self.produce()
        fact = FixtureNormalizer().normalize(request=request, snapshot=ref, raw_bytes=raw)[0]
        check(fact, request, ref)
        forged = object.__new__(self.schema.FormalContextRequest)
        object.__setattr__(forged, "_canonical", request.canonical_bytes())
        with self.assertRaises(ValueError):
            check(fact, forged, ref)
        object.__setattr__(request, "_canonical", b"{}")
        with self.assertRaises(ValueError):
            check(fact, request, ref)

    def test_future_source_is_pending_and_late_capture_is_accepted(self):
        fact, _, _ = self.put(published=FREEZE, updated=FREEZE)
        self.assertEqual(self.get().id, fact.id)
        request, ref, raw = self.produce(published="2026-08-31T07:00:01+00:00")
        with self.assertRaises(ValueError):
            self.normalize(request, ref, raw)

    def test_recheck_detects_correction_during_snapshot_verification(self):
        fact, ref, _ = self.put()
        original = self.snapshots.read_verified_raw
        changed = False
        def race(snapshot):
            nonlocal changed
            result = original(snapshot)
            if not changed:
                changed = True
                self.sql("DELETE FROM formal_context_fact WHERE id=?", (fact.id,))
            return result
        with patch.object(self.snapshots, "read_verified_raw", side_effect=race), self.assertRaises(ValueError):
            self.get()

    def test_consensus_requires_explicit_verified_no_coverage(self):
        self.install([descriptor("consensus_snapshot")])
        request = self.request(kind="consensus_snapshot")
        fact, _, _ = self.put(request=request, value=dict(coverage_status="no_valid_coverage", estimates=[]), no_coverage=True)
        self.assertTrue(self.get(kind="consensus_snapshot").no_coverage)
        for raw in (b"{}", b'{"error":"failed"}', b"[]"):
            request, ref, data = self.produce(request=request, raw=raw, captured="2026-09-06T07:00:00+00:00")
            with self.assertRaises((ValueError, TypeError)):
                self.normalize(request, ref, data)


class ContextRepositoryApiTests(unittest.TestCase):
    def test_verified_context_repository_and_store_apis_exist(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_context_repository"),
            "Context must provide a verified repository, never legacy fallback")
        api = importlib.import_module("ashare_pipeline.formal_context_repository")
        from ashare_pipeline.state_store import StateStore
        self.assertTrue(callable(api.FormalContextRepository))
        self.assertTrue(callable(api.build_effective_time_resolver))
        self.assertTrue(callable(getattr(StateStore, "put_formal_context_facts", None)))
        self.assertTrue(callable(getattr(StateStore, "list_formal_context_facts", None)))
