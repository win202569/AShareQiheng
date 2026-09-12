"""Real signed runtime fixtures for synthetic policy tests only."""

from __future__ import annotations

from datetime import date
import hashlib
import math

from ashare_pipeline.formal_evidence import (
    OfficialFetch,
    OfficialRequest,
    SourcePolicy,
    verify_official_fetch,
)
from ashare_pipeline.formal_policy_registry import load_formal_policy_registry
from ashare_pipeline.formal_policy_financial import FormalPolicyFinancialRepository
from ashare_pipeline.formal_metric_context import FormalMetricContextRepository
from ashare_pipeline.formal_universe import canonical_security_id
from tests.formal_metric_feature_fixtures import FinancialFixture
from tests.formal_metric_fixtures import FREEZE, update_mapping_digest
from tests.formal_policy_fixtures import add_policy_documents, rehash_documents
from tests.test_formal_context_repository import descriptor
from tests.test_formal_feature_contract import formal_fact
from tests.test_formal_scoring_registry import TEMPLATES, canonical
from tests.test_formal_sources import config


_DEFAULT_TEMPLATES = {
    "BJ430001": "general_nonfinancial",
    "SH600000": "bank",
    "SZ000001": "bank",
}
_POLICY_UNITS = {
    "fixture.policy.current.equity": "CNY",
    "fixture.policy.current.roe": "ratio",
    "fixture.policy.current.margin": "ratio",
    "fixture.policy.current.profit": "CNY",
    "fixture.policy.roe": "ratio",
    "fixture.policy.margin": "ratio",
    "fixture.policy.profit": "CNY",
}


def policy_financial_mapping_documents(documents):
    """Add actual signed mapping capability before the graph is signed."""
    mappings = []
    for key, unit in sorted(_POLICY_UNITS.items()):
        instant = key == "fixture.policy.current.equity"
        mappings.append(dict(mapping_id="map." + key, statement="balance" if instant else "income",
            metric_key=key, source_field=key, unit=unit, nature="instant" if instant else "duration",
            period_kind="FY", accounting_basis="consolidated"))
    documents["mapping"] = dict(schema_version="formal-financial-mapping-registry-v1",
        registry_role="mapping", row_format="item_value_v1", mappings=mappings,
        bindings=[dict(source="cninfo", dataset="annual_report", parser_id="fixture-annual",
            parser_version="fixture-annual-v1", mapping_version="fixture-annual-map-v1",
            exchange_scope=exchange, mapping_ids=sorted(m["mapping_id"] for m in mappings))
            for exchange in ("BJ", "SH", "SZ")])


def _templates(value):
    if value is None:
        return dict(_DEFAULT_TEMPLATES)
    if type(value) is not dict or not value:
        raise ValueError("templates must be a nonempty security-to-template object")
    result = {}
    for security_id, template_id in value.items():
        if (type(security_id) is not str or canonical_security_id(security_id) != security_id
                or type(template_id) is not str or template_id not in TEMPLATES):
            raise ValueError("templates contains an invalid security or template")
        result[security_id] = template_id
    return result


def _exchange_rows(templates):
    result = {exchange: [] for exchange in ("BJ", "SH", "SZ")}
    for security_id in sorted(templates):
        result[security_id[:2]].append({
            "security_id": security_id,
            "listing_status": "listed",
            "security_type": "ordinary_a",
        })
    return result


def _policy_memberships(templates, cyclic):
    return [
        {
            "security_id": security_id,
            "template_id": templates[security_id],
            "primary_industry": "fixture-policy",
            "secondary_industry": "fixture-cyclic" if cyclic else "fixture-noncyclic",
        }
        for security_id in sorted(templates)
    ]


def _patch_current_policy_periods(documents):
    for slot in documents["feature"]["slots"]:
        if slot["slot_id"].split(".policy.", 1)[-1] in {
            "equity", "roe", "margin", "profit",
        }:
            slot["formula"]["period_key"] = "FY2025"
            slot["formula"]["fact_key"] = (
                "fixture.policy.current." + slot["slot_id"].rsplit(".", 1)[-1]
            )

    def patch_selector(selector):
        if type(selector) is not dict:
            return
        if selector.get("kind") == "feature" and selector.get("period_keys") == ["FY0"]:
            selector["period_keys"] = ["FY2025"]
        if selector.get("kind") == "annual_series":
            for observation in selector["observations"]:
                patch_selector(observation["selector"])

    for role in ("cyclic", "redline", "status", "event"):
        for rule_id, rule in documents[role]["rules"].items():
            if rule_id == "execution_contract" or "inputs" not in rule:
                continue
            for selector in rule["inputs"].values():
                patch_selector(selector)


class PolicyRuntimeFixture(FinancialFixture):
    """Small producer-backed graph; it does not confer production meaning."""

    def __init__(self, *, range_enabled=False, templates=None, cyclic=True, mutate=None):
        if type(range_enabled) is not bool or type(cyclic) is not bool:
            raise ValueError("range_enabled and cyclic must be exact bool")
        selected_templates = _templates(templates)

        def configure(documents):
            documents["industry"]["memberships"] = _policy_memberships(selected_templates, cyclic)
            update_mapping_digest(documents["industry"])
            documents["scoring"]["descriptors"].append(descriptor("security_state"))
            documents["source"]["configs"].extend(
                config(dataset="fixture-state", exchange_scope=exchange)
                for exchange in ("BJ", "SH", "SZ")
            )
            add_policy_documents(documents)
            _patch_current_policy_periods(documents)
            policy_financial_mapping_documents(documents)
            if range_enabled:
                from tests.formal_range_fixtures import add_range_documents
                add_range_documents(documents)
            if mutate is not None:
                mutate(documents)
            rehash_documents(documents)

        try:
            super().__init__(
                mutate=configure,
                exchange_rows=_exchange_rows(selected_templates),
            )
            self.policy_registry = load_formal_policy_registry(
                self.bundle,
                scoring_registry=self.scoring,
                feature_registry=self.vocabulary,
            )
        except Exception:
            if hasattr(self, "tempdir"):
                self.tempdir.cleanup()
            raise
        self.policy_context_repository = FormalMetricContextRepository(self.store, self.context,
            registry_signature_verifier=self.verifier)
        self.policy_financial_repository = FormalPolicyFinancialRepository(self.feature_repository,
            current_input_provider=self.provider)
        self._policy_industry_ids = set()

    def financial_selection(self, security_id):
        if security_id not in self._policy_industry_ids:
            self.put_industry(security_id)
            self._policy_industry_ids.add(security_id)
        universe = self.policy_context_repository.load_universe(self.frozen.frozen_input_hash,
            scoring_registry=self.scoring)
        industry = self.policy_context_repository.resolve_industries(universe)
        member = next(m for m in self.industry["memberships"] if m["security_id"] == security_id)
        selected = self.policy_financial_repository.select(security_id, FREEZE,
            template_id=member["template_id"], policy_registry=self.policy_registry, industry_batch=industry)
        self.policy_context_repository.recheck_batch(universe, industry)
        return selected

    def put_policy_financial(
        self,
        security_id,
        values,
        *,
        fy_end,
        units,
        generation="g1",
        persist=True,
    ):
        if (type(security_id) is not str or canonical_security_id(security_id) != security_id
                or security_id not in {member.security_id for member in self.frozen.members}):
            raise ValueError("policy financial security must be a canonical frozen-universe member")
        if type(values) is not dict or not values or type(units) is not dict or set(units) != set(values):
            raise ValueError("every policy fact requires one explicit unit")
        if type(fy_end) is not str:
            raise ValueError("fy_end must be an explicit canonical date")
        try:
            parsed_fy_end = date.fromisoformat(fy_end)
        except ValueError as error:
            raise ValueError("fy_end must be an explicit canonical date") from error
        if parsed_fy_end.isoformat() != fy_end:
            raise ValueError("fy_end must be an explicit canonical date")
        if type(generation) is not str or not generation or generation.strip() != generation:
            raise ValueError("generation must be canonical text")
        if type(persist) is not bool:
            raise ValueError("persist must be exact bool")
        for fact_key, value in values.items():
            if (type(fact_key) is not str or fact_key not in _POLICY_UNITS
                    or type(units[fact_key]) is not str or units[fact_key] != _POLICY_UNITS[fact_key]
                    or type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("policy fact value, key or unit is invalid")

        raw = canonical(values)
        task_key = f"{security_id}:{fy_end}:{generation}"
        task = self.store.enqueue_formal_task("formal_statement", task_key, generation, {})
        leased = self.store.lease_next_formal_task(
            ("formal_statement",), "policy-financial-fixture", 300
        )
        self.assertEqual(leased["id"], task)
        fetch = OfficialFetch(
            request=OfficialRequest("cninfo", "annual_report", security_id, fy_end, security_id[:2]),
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
            declared_security_id=security_id,
            declared_period=fy_end,
        )
        verification = verify_official_fetch(fetch, SourcePolicy.cninfo())
        ref = self.snapshots.persist_verified(
            fetch,
            verification,
            producing_task_id=task,
            worker_id="policy-financial-fixture",
        )
        facts = []
        for fact_key, raw_value in values.items():
            instant = fact_key == "fixture.policy.current.equity"
            facts.append(formal_fact(
                security_id=security_id,
                statement="balance" if instant else "income",
                metric_key=fact_key,
                period_start=None if instant else fy_end[:4] + "-01-01",
                period_end=fy_end,
                period_kind="FY",
                value=float(raw_value),
                unit=units[fact_key],
                nature="instant" if instant else "duration",
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
                source_field=fact_key,
                raw_value_sha256=hashlib.sha256(canonical(raw_value)).hexdigest(),
                parser_id=ref.parser_id,
                parser_version=ref.parser_version,
                mapping_version=ref.mapping_version,
            ))
        self.store.insert_formal_financial_facts(tuple(facts))
        self.store.complete_formal_task(
            task, "policy-financial-fixture", {"snapshot": ref.snapshot_id}
        )
        self.publish_current(security_id)
        if persist:
            self.persist_features(security_id)
        return ref

    def policy_financial_values(
        self,
        security_id,
        *,
        current_equity=1.0,
        current_roe=5.0,
        current_margin=5.0,
        current_profit=5.0,
        annual_roe=(1.0, 2.0, 3.0, 4.0, 5.0),
        annual_margin=(1.0, 2.0, 3.0, 4.0, 5.0),
        annual_profit=(1.0, 2.0, 3.0, 4.0, 5.0),
    ):
        annual = (annual_roe, annual_margin, annual_profit)
        if any(type(values) is not tuple or len(values) != 5 for values in annual):
            raise ValueError("annual policy evidence requires five explicit FY values")
        for index, year in enumerate(range(2021, 2026)):
            values = {
                "fixture.policy.roe": annual_roe[index],
                "fixture.policy.margin": annual_margin[index],
                "fixture.policy.profit": annual_profit[index],
            }
            if year == 2025:
                values.update({
                    "fixture.policy.current.equity": current_equity,
                    "fixture.policy.current.roe": current_roe,
                    "fixture.policy.current.margin": current_margin,
                    "fixture.policy.current.profit": current_profit,
                })
            self.put_policy_financial(
                security_id,
                values,
                fy_end=f"{year}-12-31",
                units={key: _POLICY_UNITS[key] for key in values},
                generation=f"g1-fy{year}",
                persist=False,
            )
        self.publish_current(security_id)
        return self.persist_features(security_id)


__all__ = ["PolicyRuntimeFixture"]
