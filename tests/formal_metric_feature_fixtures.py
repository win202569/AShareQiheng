"""Same-store, member-specific financial receipts for metric engine tests."""

import hashlib

from ashare_pipeline.formal_evidence import OfficialFetch, OfficialRequest, SourcePolicy, verify_official_fetch
from ashare_pipeline.formal_feature_contract import load_signed_feature_registry
from ashare_pipeline.formal_feature_repository import FormalFeatureCurrentInput, FormalFeatureRepository
from ashare_pipeline.formal_metric_batch_guard import FormalMetricCurrentInputProvider
from ashare_pipeline.formal_feature_store import FormalFeatureBundleStore
from ashare_pipeline.formal_financial_features import build_formal_feature_bundle
from tests.formal_metric_fixtures import MetricFixture, FREEZE, update_mapping_digest
from tests.test_formal_feature_contract import formal_fact
from tests.test_formal_feature_store import project_temporary_directory
from tests.test_formal_scoring_registry import canonical

METRICS = ("G.operating_profit_per_share_cagr_3y", "G.operating_profit_per_share_yoy",
    "G.operating_revenue_cagr_3y", "G.operating_revenue_yoy")


def configuration(docs):
    for template in docs["scoring"]["scoring"]["templates"].values():
        for metrics in template["metrics"].values():
            for metric in metrics:
                metric.update(period_rule=["FY2025"], unit_rule="CNY")
                if metric["metric_id"] == "operating_revenue_yoy":
                    metric["direction"] = "lower"
    for slot in docs["feature"]["slots"]:
        leaf = ".".join(slot["slot_id"].split(".")[1:])
        slot.update(unit="CNY", formula=dict(op="fact", fact_key=leaf, period_key="FY2025"))


class FinancialFixture(MetricFixture):
    def __init__(self, *, population=False, missing_memberships=False, mutate=None, calendar_binding_resolver=None):
        rows = None
        def configure(docs):
            configuration(docs)
            if missing_memberships:
                docs["industry"]["memberships"] = [dict(security_id="SH600099", template_id="bank",
                    primary_industry="banks", secondary_industry="banks")]
                update_mapping_digest(docs["industry"])
            if mutate:
                mutate(docs)
            if population:
                ids = ["BJ430001"] + [f"SH{600000 + i}" for i in range(20)] + ["SZ000001"]
                docs["industry"]["memberships"] = [dict(security_id=sid,
                    template_id="bank" if sid == "SZ000001" else "general_nonfinancial",
                    primary_industry="manufacturing", secondary_industry="other" if sid == "SH600019" else "machinery")
                    for sid in sorted(ids)]
                update_mapping_digest(docs["industry"])
        if population:
            rows = {exchange: [dict(security_id=sid, listing_status="listed", security_type="ordinary_a") for sid in ids]
                for exchange, ids in {"BJ": ["BJ430001"], "SH": [f"SH{600000+i}" for i in range(20)], "SZ": ["SZ000001"]}.items()}
        super().__init__(mutate=configure, exchange_rows=rows, tempdir=project_temporary_directory(),
            calendar_binding_resolver=calendar_binding_resolver)
        self.files = FormalFeatureBundleStore(self.root / "features")
        self.store._formal_feature_bundle_store = self.files
        self.issues = {}
        self.generations = {}
        child = self.bundle.blob("feature")
        self.vocabulary = load_signed_feature_registry(child.canonical_json, child.signature, child.key_id,
            self.verifier, registry_manifest=self.bundle.manifest)
        self.provider = FormalMetricCurrentInputProvider(self.store)
        for member in self.industry["memberships"]:
            self.publish_current(member["security_id"])
        self.feature_repository = FormalFeatureRepository(self.store, self.files,
            registry_signature_verifier=self.verifier, current_input_provider=self.provider)

    def resolve_current_inputs(self, **request):
        sid = request["security_id"]
        return FormalFeatureCurrentInput(**request, batch_id=self.generations.get(sid, "generation-1"),
            facts=self.store.list_formal_financial_facts(security_id=sid), issues=self.issues.get(sid, ()), complete=True)

    def publish_current(self, sid):
        if hasattr(self, "provider"):
            member = next(m for m in self.industry["memberships"] if m["security_id"] == sid)
            self.provider.publish(self.resolve_current_inputs(security_id=sid, as_of_utc=FREEZE,
                template_id=member["template_id"], registry_manifest_hash=self.bundle.manifest.manifest_hash))

    def set_generation(self, sid, generation):
        self.generations[sid] = generation
        self.publish_current(sid)

    def set_issues(self, sid, issues):
        self.issues[sid] = issues
        self.publish_current(sid)

    def put_financial(self, sid, values, *, generation="financial-1", updated=None, publish=True,
                      period_end="2025-12-31", period_kind="FY", nature="duration"):
        raw = canonical(values)
        task = self.store.enqueue_formal_task("formal_statement", sid + generation, generation, {})
        leased = self.store.lease_next_formal_task(("formal_statement",), "financial-fixture", 300)
        self.assertEqual(leased["id"], task)
        fetch = OfficialFetch(request=OfficialRequest("cninfo", "annual_report", sid, period_end, sid[:2]),
            raw_bytes=raw, original_url="https://www.cninfo.com.cn/fixture/annual.json",
            published_at_utc="2026-03-20T08:00:00+00:00", published_precision="timestamp",
            source_updated_at_utc=updated, captured_at_utc="2026-09-04T07:00:00+00:00",
            effective_at_utc="2026-03-20T08:00:00+00:00", effective_time_evidence_hash=None,
            refresh_generation=generation, parser_id="fixture-annual", parser_version="fixture-annual-v1",
            mapping_version="fixture-annual-map-v1", declared_security_id=sid, declared_period=period_end)
        verification = verify_official_fetch(fetch, SourcePolicy.cninfo())
        ref = self.snapshots.persist_verified(fetch, verification, producing_task_id=task, worker_id="financial-fixture")
        facts = tuple(formal_fact(security_id=sid, metric_key=key, value=float(value), source_field=key,
            period_end=period_end, period_kind=period_kind, nature=nature,
            statement="income" if nature == "duration" else "balance",
            period_start=period_end[:4] + "-01-01" if nature == "duration" else None,
            raw_value_sha256=hashlib.sha256(canonical(value)).hexdigest(), source_snapshot_id=ref.snapshot_id,
            source_content_sha256=ref.content_sha256, source_refresh_generation=ref.refresh_generation,
            source_producing_task_id=ref.producing_task_id, parser_id=ref.parser_id, parser_version=ref.parser_version,
            mapping_version=ref.mapping_version, source_updated_at_utc=ref.source_updated_at_utc,
            captured_at_utc=ref.captured_at_utc) for key, value in values.items())
        self.store.insert_formal_financial_facts(facts)
        self.store.complete_formal_task(task, "financial-fixture", {"snapshot": ref.snapshot_id})
        if publish:
            self.publish_current(sid)
        return ref

    def persist_features(self, sid):
        member = next(m for m in self.industry["memberships"] if m["security_id"] == sid)
        bundle = build_formal_feature_bundle(security_id=sid, as_of_utc=FREEZE, template_id=member["template_id"],
            facts=self.store.list_formal_financial_facts(security_id=sid), issues=self.issues.get(sid, ()),
            registry=self.vocabulary, registry_manifest=self.bundle.manifest)
        self.store.put_formal_feature_bundle(bundle, self.files.write(bundle))
        return bundle

    def populate(self):
        for index, member in enumerate(self.industry["memberships"]):
            sid = member["security_id"]
            self.put_industry(sid)
            values = {METRICS[0]: index - 1, METRICS[3]: index - 1}
            if sid != "SH600018":
                values[METRICS[1]] = index - 1  # 19 secondary, 20 primary.
            if sid not in ("SH600018", "SH600019"):
                values[METRICS[2]] = index - 1  # Only 19 in this template.
            self.put_financial(sid, values)
            self.persist_features(sid)
