"""Real signed full-company and peer receipts for complete-score boundary tests."""

import hashlib
from dataclasses import asdict

from ashare_pipeline.formal_context_schema import FormalContextRegistry
from ashare_pipeline.formal_evidence import OfficialFetch, SourcePolicy, verify_official_fetch
from ashare_pipeline.formal_sources import CalendarSelector
from tests.formal_metric_feature_fixtures import FinancialFixture
from tests.formal_metric_fixtures import FREEZE
from tests.test_formal_context_repository import FixtureNormalizer, descriptor
from tests.test_formal_scoring_registry import canonical
from tests.test_formal_sources import config

FOCAL = "BJ430001"


class ScoreFixture(FinancialFixture):
    def __init__(self, *, linked=True, cyclic=False, extra_required=False, date_only=False, population=True):
        self.calendar_requests = {}
        self.date_only = date_only
        def configure(docs):
            # Twenty-four independently signed slots deliberately share one toy
            # source field; expectation remains separately missing-capable.
            for slot in docs["feature"]["slots"]:
                slot["formula"]["fact_key"] = "T.expectation_change" if slot["slot_id"].endswith(
                    ".T.expectation_change") else "score_leaf"
            if linked:
                desc = descriptor("consensus_snapshot", scope_key="fixture-consensus", dataset="fixture-consensus")
                selector = None
                if date_only:
                    selector = asdict(CalendarSelector("trading_calendar", "fixture-calendar-BJ", "BJ", "visible_at_freeze"))
                    desc.update(calendar_selector=selector, exchange_rule="fixed_exchange", fixed_exchange="BJ")
                    docs["scoring"]["descriptors"].append(descriptor("trading_calendar", scope_key="fixture-calendar-BJ",
                        security_scope="none", request_security="none", period_rule="none", exchange_rule="fixed_exchange",
                        fixed_exchange="BJ", dataset="trading_calendar", bootstrap_calendar=True))
                    docs["source"]["configs"].append(config(dataset="trading_calendar", bootstrap_calendar=True))
                wrapper = docs["scoring"]
                metric = wrapper["scoring"]["templates"]["general_nonfinancial"]["metrics"]["T"][2]
                wrapper.update(schema_version="formal-scoring-registry-v2", input_alternatives=[dict(
                    rule_id="consensus-no-coverage-neutral-v1", template_id="general_nonfinancial",
                    metric_id="T.expectation_change", feature_key=metric["required_feature_keys"][0],
                    descriptor_id=hashlib.sha256(canonical(desc)).hexdigest())])
                wrapper["descriptors"].append(desc)
                docs["source"]["configs"].extend(config(dataset="fixture-consensus", exchange_scope=e,
                    calendar_selector=selector) for e in (("BJ",) if date_only else ("BJ", "SH", "SZ")))
            if cyclic:
                industries = docs["cyclic"]["rules"]["classification"]["secondary_industries"]
                industries.append("machinery")
                industries.sort()
                docs["scoring"]["scoring"]["policy_contracts"]["cyclic"]["registry_hash"] = hashlib.sha256(
                    canonical(docs["cyclic"])).hexdigest()
            if extra_required:
                slot = dict(docs["feature"]["slots"][0])
                slot.update(slot_id="general_nonfinancial.extra", template_id="general_nonfinancial",
                    formula=dict(op="fact", fact_key="extra", period_key="FY2025"))
                docs["feature"]["slots"].append(slot)
                docs["feature"]["slots"].sort(key=lambda s: s["slot_id"])
            docs["feature"]["source_registry_hash"] = hashlib.sha256(canonical(docs["source"])).hexdigest()
        super().__init__(population=population, mutate=configure, calendar_binding_resolver=self.resolve_raw_calendar)

    def resolve_raw_calendar(self, candidate):
        request = self.calendar_requests.get(candidate.canonical_json_bytes())
        if request is None:
            raise ValueError("unregistered fixture calendar request")
        wire = request.to_dict()
        if request.official_request.canonical_json_bytes() != candidate.canonical_json_bytes():
            raise ValueError("fixture calendar request identity mismatch")
        return self.context.resolve_verified_calendar_binding(CalendarSelector(**wire["calendar_selector"]),
            candidate.exchange, wire["as_of_utc"], wire["registry_manifest_hash"])

    def populate_scores(self, *, missing=(), mature=True, five_years=False, consensus="covered"):
        for index, member in enumerate(self.industry["memberships"]):
            sid = member["security_id"]
            self.put_industry(sid)
            values = {slot.formula.fact_key: index + 10
                for slot in self.vocabulary.slots_for_template(member["template_id"])
                if not (sid == FOCAL and slot.formula.fact_key in missing)}
            # Synthetic signed FY leaves are balance snapshots. A separate real
            # duration series proves observed history without repeating 25 toy
            # fields at every cumulative endpoint.
            self.put_financial(sid, values, publish=False, nature="instant")
            if sid == FOCAL and mature:
                for year in range(2021 if five_years else 2022, 2026):
                    self.put_financial(sid, {"history": 1}, generation=f"history-{year}",
                        period_end=f"{year}-12-31", publish=False)
                for year in (2024, 2025, 2026):
                    for kind, end in (("Q1", "03-31"), ("H1", "06-30"), ("Q3", "09-30")):
                        if year == 2026 and kind == "Q3":
                            continue
                        self.put_financial(sid, {"history": 1}, generation=f"history-{year}-{kind}",
                            period_end=f"{year}-{end}", period_kind=kind, publish=False)
            self.publish_current(sid)
            self.persist_features(sid)
        if consensus is not None and self.scoring.consensus_no_coverage_links:
            if self.date_only:
                self.put_calendar()
            self.put_consensus(no_coverage=consensus == "none")

    def put_calendar(self):
        request = self.resolver.resolve(context_kind="trading_calendar", scope_key="fixture-calendar-BJ",
            security_id=None, as_of_utc=FREEZE, registry_manifest_hash=self.bundle.manifest.manifest_hash,
            upstream_generation="calendar-1")
        return self.put_context(request, dict(exchange="BJ", calendar_version="fixture-v1",
            trading_days=["2026-08-21", "2026-08-31", "2026-09-02"]), False, "calendar-1")

    def put_consensus(self, *, no_coverage=True, generation="consensus-1"):
        request = self.resolver.resolve(context_kind="consensus_snapshot", scope_key="fixture-consensus",
            security_id=FOCAL, as_of_utc=FREEZE, registry_manifest_hash=self.bundle.manifest.manifest_hash,
            upstream_generation=generation)
        value = dict(coverage_status="no_valid_coverage" if no_coverage else "covered",
            estimates=[] if no_coverage else [dict(period="FY2026", metric="profit", value=1)])
        return self.put_context(request, value, no_coverage, generation)

    def put_context(self, request, value, no_coverage, generation):
        task = self.store.enqueue_formal_task("formal_context", FOCAL + generation, request.refresh_generation, {})
        self.store.lease_next_formal_task(("formal_context",), "score-fixture", 300)
        raw = canonical(dict(value=value, no_coverage=no_coverage))
        binding = request.calendar_binding
        if binding is not None:
            self.calendar_requests[request.official_request.canonical_json_bytes()] = request
        fetch = OfficialFetch(request=request.official_request, raw_bytes=raw,
            original_url="https://www.cninfo.com.cn/fixture/consensus.json",
            published_at_utc="2026-08-19T16:00:00+00:00" if binding else "2026-08-19T07:00:00+00:00",
            published_precision="date_only" if binding else "timestamp",
            source_updated_at_utc=None, captured_at_utc="2026-09-04T07:00:00+00:00",
            effective_at_utc="2026-08-21T07:00:00+00:00" if binding else "2026-08-19T07:00:00+00:00",
            effective_time_evidence_hash=binding.manifest_sha256 if binding else None,
            refresh_generation=request.refresh_generation, parser_id=request.parser_id,
            parser_version=request.parser_version, mapping_version=request.mapping_version,
            declared_security_id=request.official_request.security_id, declared_period=request.official_request.period_or_date)
        verified = verify_official_fetch(fetch, SourcePolicy.cninfo(), calendar_binding=binding)
        ref = self.snapshots.persist_verified(fetch, verified, producing_task_id=task, worker_id="score-fixture")
        receipt = FormalContextRegistry.load(self.store, self.verifier, self.bundle.manifest.manifest_hash).normalize_verified(
            request, ref, raw, FixtureNormalizer(), task_id=task, worker_id="score-fixture")
        self.store.put_formal_context_facts(receipt)
        self.store.complete_formal_task(task, "score-fixture", {"snapshot": ref.snapshot_id})
        return receipt.facts[0]
