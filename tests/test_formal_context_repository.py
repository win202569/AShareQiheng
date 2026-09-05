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
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore
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
                published="2026-08-20T07:00:00+00:00", updated=None, captured="2026-09-04T07:00:00+00:00", raw=None):
        request = request or self.request()
        value = dict(is_st=False, is_star_st=False, listing_status="listed", forced_delist_risk=False, suspended=False) if value is None else value
        task = self.store.enqueue_formal_task(task_kind, hashlib.sha256((request.refresh_generation + published + captured + str(value) + repr(raw) + task_kind).encode()).hexdigest(), request.refresh_generation, {})
        worker = "fixture-worker"
        self.store.lease_next_formal_task((task_kind,), worker, 300)
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

    def normalize(self, request, ref, raw, normalizer=None):
        registry = self.schema.FormalContextRegistry.load(self.store, self.verifier, self.manifest.manifest_hash)
        return registry.normalize_verified(request, ref, raw, normalizer or FixtureNormalizer())

    def put(self, **kwargs):
        request, ref, raw = self.produce(**kwargs)
        receipt = self.normalize(request, ref, raw)
        self.store.put_formal_context_facts(receipt)
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
            fact, ref, receipt = self.put()
            self.store.put_formal_context_facts(receipt)
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

    def install_calendars(self, *, date_only=False):
        descriptors = [descriptor("trading_calendar", scope_key="fixture-calendar-" + ex,
            security_scope="none", request_security="none", period_rule="none", exchange_rule="fixed_exchange",
            fixed_exchange=ex, dataset="trading_calendar", bootstrap_calendar=True) for ex in ("SH", "SZ", "BJ")]
        configs = [config(dataset="trading_calendar", bootstrap_calendar=True)]
        if date_only:
            selector = asdict(CalendarSelector("trading_calendar", "fixture-calendar-SZ", "SZ", "visible_at_freeze"))
            descriptors.append(descriptor(calendar_selector=selector))
            configs.append(config(dataset="fixture-state", exchange_scope="SZ", calendar_selector=selector))
        self.install(descriptors, configs)
        calendars = {}
        for exchange in ("SH", "SZ", "BJ"):
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
