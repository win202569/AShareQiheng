"""Real combined signed graph and producer-backed universe/Context fixtures."""

from contextlib import closing
import hashlib
import sqlite3
import tempfile
from pathlib import Path

from ashare_pipeline.formal_context_repository import FormalContextRepository
from ashare_pipeline.formal_context_schema import FormalContextRegistry, SignedContextRequestResolver
from ashare_pipeline.formal_evidence import OfficialFetch, SourcePolicy, verify_official_fetch
from ashare_pipeline.formal_scoring_registry import RegistryApproval, load_formal_registry
from ashare_pipeline.formal_snapshot_repository import FormalSnapshotRepository
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore
from ashare_pipeline.state_store import StateStore
from tests import test_state_store
from tests.test_formal_context_repository import FixtureNormalizer, descriptor
from tests.test_formal_scoring_registry import canonical, signed_graph
from tests.test_formal_sources import config

FREEZE = "2026-08-31T07:00:00+00:00"
IDS = ("BJ430001", "SH600000", "SZ000001")


def industry_document():
    memberships = [dict(security_id=s, template_id=t, primary_industry=p, secondary_industry=q)
        for s, t, p, q in (("BJ430001", "general_nonfinancial", "manufacturing", "machinery"),
            ("SH600000", "bank", "banks", "joint-stock-banks"), ("SZ000001", "bank", "banks", "joint-stock-banks"))]
    mapping = dict(classification_system="SW2021", source_version="2026.08", effective_date="2026-08-28", memberships=memberships)
    return dict(registry_role="industry", schema_version="formal-industry-registry-v1", purpose="official",
        context_scope_key="fixture-industry", mapping_sha256=hashlib.sha256(canonical(mapping)).hexdigest(), **mapping)


def update_mapping_digest(doc):
    doc["mapping_sha256"] = hashlib.sha256(canonical({k: doc[k] for k in
        ("classification_system", "source_version", "effective_date", "memberships")})).hexdigest()


class MetricFixture:
    """A plain helper; no imported/inherited TestCase can duplicate suite discovery."""

    def __init__(self, *, mutate=None, exchange_rows=None, tempdir=None, calendar_binding_resolver=None):
        self.tempdir = tempdir or tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.db_path = self.root / "metric.sqlite"
        StateStore(self.db_path).initialize()
        self.raw = FormalSnapshotStore(self.root / "raw", calendar_binding_resolver=calendar_binding_resolver)
        def configure(docs):
            docs["industry"] = industry_document()
            docs["scoring"]["descriptors"] = [descriptor("industry_snapshot", scope_key="fixture-industry",
                dataset="fixture-industry", referenced_roles=["industry", "scoring", "source"])]
            docs["source"]["configs"] = [config(dataset="fixture-industry", exchange_scope=e) for e in ("BJ", "SH", "SZ")]
            docs["feature"]["source_registry_hash"] = hashlib.sha256(canonical(docs["source"])).hexdigest()
            if mutate:
                mutate(docs)
        self.bundle, vocabulary, graph, self.verifier = signed_graph(mutate=configure)
        self.industry = __import__("json").loads(self.bundle.blob("industry").canonical_json)
        self.store, self.frozen, self.task_ids = test_state_store.StateStoreTestCase.task_backed_frozen_universe(
            self, registry_manifest_hash=self.bundle.manifest.manifest_hash,
            source_registry_hash=self.bundle.manifest.source_registry_hash,
            registry_signature_verifier=self.verifier, formal_snapshot_store=self.raw, exchange_rows=exchange_rows)
        for blob in graph.blobs.values():
            self.store.put_formal_registry_blob(blob)
        self.store.put_formal_registry_manifest(graph.manifest)
        self.snapshot_id = self.store.put_formal_universe_snapshot(self.frozen)
        self.scoring = load_formal_registry(self.bundle, RegistryApproval("official",
            self.bundle.manifest.scoring_registry_hash, self.bundle.manifest.approval_id), feature_registry=vocabulary)
        self.snapshots = FormalSnapshotRepository(self.raw.root, self.store)
        self.context = FormalContextRepository(self.store, self.snapshots, self.verifier)
        self.resolver = SignedContextRequestResolver(self.store, self.verifier)

    def assertEqual(self, actual, expected):
        if actual != expected:
            raise AssertionError((actual, expected))

    def close(self):
        self.tempdir.cleanup()

    def sql(self, sql, args=()):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(sql, args)
            conn.commit()

    def put_industry(self, security_id, *, changes=None, generation="initial", published="2026-08-28T07:00:00+00:00"):
        doc = self.industry
        member = next((m for m in doc["memberships"] if m["security_id"] == security_id),
            dict(primary_industry="other", secondary_industry="other"))
        value = {k: doc[k] for k in ("classification_system", "source_version", "effective_date", "mapping_sha256")}
        value.update({k: member[k] for k in ("primary_industry", "secondary_industry")})
        value.update(changes or {})
        request = self.resolver.resolve(context_kind="industry_snapshot", scope_key="fixture-industry",
            security_id=security_id, as_of_utc=FREEZE, registry_manifest_hash=self.bundle.manifest.manifest_hash,
            upstream_generation=generation)
        task = self.store.enqueue_formal_task("formal_context", security_id + generation, request.refresh_generation, {})
        self.store.lease_next_formal_task(("formal_context",), "metric-fixture", 300)
        raw = canonical(dict(value=value, no_coverage=False))
        fetch = OfficialFetch(request=request.official_request, raw_bytes=raw,
            original_url="https://www.cninfo.com.cn/fixture/context.json", published_at_utc=published,
            published_precision="timestamp", source_updated_at_utc=None,
            captured_at_utc="2026-09-04T07:00:00+00:00", effective_at_utc=published,
            effective_time_evidence_hash=None, refresh_generation=request.refresh_generation,
            parser_id=request.parser_id, parser_version=request.parser_version, mapping_version=request.mapping_version,
            declared_security_id=security_id, declared_period=request.official_request.period_or_date)
        verified = verify_official_fetch(fetch, SourcePolicy.cninfo())
        self.assertEqual(verified.status, "verified")
        ref = self.snapshots.persist_verified(fetch, verified, producing_task_id=task, worker_id="metric-fixture")
        receipt = FormalContextRegistry.load(self.store, self.verifier, self.bundle.manifest.manifest_hash).normalize_verified(
            request, ref, raw, FixtureNormalizer(), task_id=task, worker_id="metric-fixture")
        self.store.put_formal_context_facts(receipt)
        self.store.complete_formal_task(task, "metric-fixture", {"snapshot": ref.snapshot_id})
        return receipt.facts[0], ref
