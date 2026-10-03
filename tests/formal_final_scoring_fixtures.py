"""One real signed Stage D test root for base, policy, and valuation inputs."""

from collections import namedtuple
import hashlib

from ashare_pipeline.formal_evidence import (
    OfficialFetch, OfficialRequest, SourcePolicy, verify_official_fetch,
)
from ashare_pipeline.formal_score_inputs import FormalScoreInputRepository
from tests.formal_score_input_fixtures import ScoreFixture
from tests.formal_valuation_fixtures import ValuationRuntimeFixture
from tests.test_formal_context_repository import descriptor
from tests.test_formal_feature_contract import formal_fact
from tests.test_formal_scoring_registry import canonical
from tests.test_formal_sources import config


D1Sources = namedtuple("D1Sources", "base policy valuation")
FOCAL = "BJ430001"


def _stage_d_documents(documents):
    for range_config in documents["source"]["range_configs"]:
        range_config["max_calendar_days_per_request"] = 400
    for slot in documents["feature"]["slots"]:
        if ".policy." in slot["slot_id"] or ".V." in slot["slot_id"]:
            continue
        slot["formula"]["fact_key"] = (
            "T.expectation_change" if slot["slot_id"].endswith(".T.expectation_change")
            else "score_leaf"
        )
    linked = descriptor("consensus_snapshot", scope_key="fixture-consensus",
        dataset="fixture-consensus")
    wrapper = documents["scoring"]
    metric = wrapper["scoring"]["templates"]["general_nonfinancial"]["metrics"]["T"][2]
    wrapper["schema_version"] = "formal-scoring-registry-v2"
    wrapper["input_alternatives"] = [dict(
        rule_id="consensus-no-coverage-neutral-v1", template_id="general_nonfinancial",
        metric_id="T.expectation_change", feature_key=metric["required_feature_keys"][0],
        descriptor_id=hashlib.sha256(canonical(linked)).hexdigest())]
    wrapper["descriptors"].append(linked)
    documents["source"]["configs"].extend(
        config(dataset="fixture-consensus", exchange_scope=exchange)
        for exchange in ("BJ", "SH", "SZ")
    )


class FinalScoringFixture(ValuationRuntimeFixture):
    """Genuine producer-backed proofs; no fixture-level proof constructor."""

    put_context = ScoreFixture.put_context
    put_consensus = ScoreFixture.put_consensus

    def _put_policy_quarter(self, sid, values, units, year, kind, end):
        period_end = f"{year}-{end}"
        generation = f"stage-d-policy-quarter-{year}-{kind}"
        raw = canonical(values)
        task = self.store.enqueue_formal_task("formal_statement",
            f"{sid}:{generation}", generation, {})
        leased = self.store.lease_next_formal_task(
            ("formal_statement",), "stage-d-policy-quarter-fixture", 300)
        self.assertEqual(leased["id"], task)
        fetch = OfficialFetch(
            request=OfficialRequest("cninfo", "annual_report", sid, period_end, sid[:2]),
            raw_bytes=raw,
            original_url="https://www.cninfo.com.cn/fixture/annual.json",
            published_at_utc="2026-03-20T08:00:00+00:00",
            published_precision="timestamp",
            source_updated_at_utc=None,
            captured_at_utc="2026-09-04T07:00:00+00:00",
            effective_at_utc="2026-03-20T08:00:00+00:00",
            effective_time_evidence_hash=None,
            refresh_generation=generation,
            parser_id="fixture-annual",
            parser_version="fixture-annual-v1",
            mapping_version="fixture-annual-map-v1",
            declared_security_id=sid,
            declared_period=period_end,
        )
        ref = self.snapshots.persist_verified(fetch, verify_official_fetch(
            fetch, SourcePolicy.cninfo()), producing_task_id=task,
            worker_id="stage-d-policy-quarter-fixture")
        self.store.insert_formal_financial_facts(tuple(formal_fact(
            security_id=sid, statement="income", metric_key=key,
            period_start=f"{year}-01-01", period_end=period_end,
            period_kind=kind, value=value, unit=units[key], nature="duration",
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
            source_field=key,
            raw_value_sha256=hashlib.sha256(canonical(value)).hexdigest(),
            parser_id=ref.parser_id, parser_version=ref.parser_version,
            mapping_version=ref.mapping_version,
        ) for key, value in values.items()))
        self.store.complete_formal_task(task, "stage-d-policy-quarter-fixture",
            {"snapshot": ref.snapshot_id})

    def _populate_policy_quarter_prerequisites(self, sid):
        facts = [fact.to_dict() for fact in self.store.list_formal_financial_facts(
            security_id=sid)]
        for year in (2024, 2025):
            annual = {wire["metric_key"]: wire for wire in facts
                if wire["period_end"] == f"{year}-12-31"
                and wire["period_kind"] == "FY"
                and wire["nature"] == "duration"
                and wire["metric_key"].startswith("fixture.policy.")}
            units = {key: wire["unit"] for key, wire in annual.items()}
            for index, (kind, end) in enumerate((
                    ("Q1", "03-31"), ("H1", "06-30"), ("Q3", "09-30")), 1):
                values = {key: wire["value"] * index / 4
                    for key, wire in annual.items()}
                self._put_policy_quarter(sid, values, units, year, kind, end)
        self.publish_current(sid)

    def __init__(self, *, peer_count=3, pending_ids=None, cap_ids=(FOCAL,),
                 prohibition_ids=(), veto_ids=(), consensus_no_coverage=False,
                 purpose="official"):
        if peer_count not in (3, 20, 23):
            raise ValueError("Stage D fixture supports 3, 20, or 23 members")
        self.date_only = False
        self.calendar_requests = {}
        self.cap_ids = tuple(cap_ids)
        self.prohibition_ids = tuple(prohibition_ids)
        self.veto_ids = tuple(veto_ids)
        self.consensus_no_coverage = consensus_no_coverage
        super().__init__(peer_count=peer_count,
            cyclic_ids=tuple(sorted({FOCAL, *self.cap_ids})),
            signature_documents_configurator=_stage_d_documents,
            purpose=purpose)
        active_by_default = {FOCAL, *self.cap_ids, *self.prohibition_ids, *self.veto_ids}
        self.pending_ids = (tuple(sorted(set(self.templates) - active_by_default))
            if pending_ids is None else tuple(pending_ids))
        known = set(self.templates)
        for group in (self.pending_ids, self.cap_ids, self.prohibition_ids, self.veto_ids):
            if len(group) != len(set(group)) or not set(group) <= known:
                self.close()
                raise ValueError("Stage D scenario IDs must be distinct signed members")
        self.base_repository = FormalScoreInputRepository(self.feature_repository,
            self.context, registry_signature_verifier=self.verifier)

    def populate_final_inputs(self):
        active_policy_ids = set(self.templates) - set(self.pending_ids)
        financial_overrides = {sid: dict(current_roe=1.0, current_margin=1.0,
            current_profit=1.0) for sid in active_policy_ids}
        for sid in set(self.cap_ids) & active_policy_ids:
            financial_overrides[sid].update(current_roe=10.0, current_margin=10.0,
                current_profit=10.0, annual_roe=(4.0, 5.0, 6.0, 7.0, 8.0),
                annual_margin=(4.0, 5.0, 6.0, 7.0, 8.0),
                annual_profit=(4.0, 5.0, 6.0, 7.0, 8.0))
        for sid in set(self.prohibition_ids) & active_policy_ids:
            financial_overrides[sid]["current_equity"] = 0.0
        original_industry = self.industry
        self.industry = dict(original_industry, memberships=[member
            for member in original_industry["memberships"]
            if member["security_id"] in active_policy_ids])
        try:
            self.populate_policy_evidence(financial_overrides=financial_overrides)
        finally:
            self.industry = original_industry
        for sid in sorted(active_policy_ids):
            self._populate_policy_quarter_prerequisites(sid)
        for index, sid in enumerate(sorted(self.templates)):
            if sid not in active_policy_ids:
                self.put_industry(sid)
            self.put_financial(sid, {
                "V.enterprise_value_or_sustainable_roe": 0.1 + index / 1000,
                "V.normalized_earnings_yield": 0.20 if sid == FOCAL else 0.1 + index / 1000,
                "V.normalized_free_cash_flow_yield": 0.08 + index / 1000,
            }, generation="stage-d-valuation", nature="instant")
            score_values = {"score_leaf": index + 10}
            if not (sid == FOCAL and self.consensus_no_coverage):
                score_values["T.expectation_change"] = index + 10
            self.put_financial(sid, score_values,
                generation="stage-d-score", nature="instant")
            if sid == FOCAL:
                for year in range(2021, 2026):
                    self.put_financial(sid, {"history": 1},
                        generation=f"stage-d-history-{year}",
                        period_end=f"{year}-12-31", publish=False)
                for year in (2024, 2025, 2026):
                    for kind, end in (("Q1", "03-31"), ("H1", "06-30"), ("Q3", "09-30")):
                        if year == 2026 and kind == "Q3":
                            continue
                        self.put_financial(sid, {"history": 1},
                            generation=f"stage-d-history-{year}-{kind}",
                            period_end=f"{year}-{end}", period_kind=kind, publish=False)
                self.publish_current(sid)
            self.valuation_feature_bundles[sid] = self.persist_features(sid)
        self.put_consensus(no_coverage=self.consensus_no_coverage)

    def reply(self, wire, **kwargs):
        if wire["security_id"] in self.veto_ids and "range-market" in kwargs.get("original_url", ""):
            wire = dict(wire, rows=[dict(row, volume="0", turnover="0")
                for row in wire["rows"]])
        return super().reply(wire, **kwargs)

    def build_d1_sources(self):
        return D1Sources(
            self.base_repository.build_batch(self.frozen.frozen_input_hash,
                scoring_registry=self.scoring,
                expected_purpose=self.purpose),
            self.build_policy_batch(),
            self.build_adjusted_batch(),
        )
