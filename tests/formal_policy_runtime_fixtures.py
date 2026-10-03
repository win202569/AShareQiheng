"""Real signed runtime fixtures for synthetic policy tests only."""

from __future__ import annotations

from datetime import date, timedelta
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
from tests.formal_policy_fixtures import add_policy_documents, add_valuation_adapter_document, rehash_documents
from tests.test_formal_context_repository import descriptor, FixtureNormalizer
from ashare_pipeline.formal_context_schema import FormalContextRegistry
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


def _exchange_rows(templates, extra_members=()):
    result = {exchange: [] for exchange in ("BJ", "SH", "SZ")}
    for security_id in sorted((*templates, *extra_members)):
        result[security_id[:2]].append({
            "security_id": security_id,
            "listing_status": "listed",
            "security_type": "ordinary_a",
        })
    return result


def _policy_memberships(templates, cyclic, noncyclic_ids=()):
    return [
        {
            "security_id": security_id,
            "template_id": templates[security_id],
            "primary_industry": "fixture-policy",
            "secondary_industry": "fixture-cyclic" if cyclic and security_id not in noncyclic_ids else "fixture-noncyclic",
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

    def __init__(self, *, range_enabled=False, templates=None, cyclic=True, mutate=None,
                 extra_members=(), noncyclic_ids=(), valuation_adapter=False,
                 purpose="official"):
        if type(range_enabled) is not bool or type(cyclic) is not bool:
            raise ValueError("range_enabled and cyclic must be exact bool")
        selected_templates = _templates(templates)
        extra_members = tuple(extra_members)
        noncyclic_ids = tuple(noncyclic_ids)
        if (any(type(sid) is not str or canonical_security_id(sid) != sid
                or sid in selected_templates for sid in extra_members)
                or len(set(extra_members)) != len(extra_members)
                or any(sid not in selected_templates for sid in noncyclic_ids)):
            raise ValueError("fixture membership inputs must be distinct canonical securities")

        def configure(documents):
            documents["industry"]["memberships"] = _policy_memberships(selected_templates, cyclic, noncyclic_ids)
            update_mapping_digest(documents["industry"])
            documents["scoring"]["descriptors"].append(descriptor("security_state"))
            documents["source"]["configs"].extend(
                config(dataset="fixture-state", exchange_scope=exchange)
                for exchange in ("BJ", "SH", "SZ")
            )
            add_policy_documents(documents, purpose=purpose)
            if valuation_adapter:
                add_valuation_adapter_document(documents, purpose=purpose)
            _patch_current_policy_periods(documents)
            policy_financial_mapping_documents(documents)
            if range_enabled:
                from tests.formal_range_fixtures import add_range_documents
                add_range_documents(documents)
                # W3 needs a genuine recent window, not a 400-day fixture.
                # Tests needing larger ranges may explicitly override this cap.
                for entry in documents["source"]["range_configs"]:
                    entry["max_calendar_days_per_request"] = 20
            if mutate is not None:
                mutate(documents)
            rehash_documents(documents)

        try:
            super().__init__(
                mutate=configure,
                exchange_rows=_exchange_rows(selected_templates, extra_members),
                manifest_version=("formal-registry-manifest-v2" if valuation_adapter
                                  else "formal-registry-manifest-v1"),
                purpose=purpose,
            )
            self.policy_registry = load_formal_policy_registry(
                self.bundle,
                scoring_registry=self.scoring,
                feature_registry=self.vocabulary,
                expected_purpose=self.purpose,
            )
            if range_enabled:
                from ashare_pipeline.formal_range_contract import load_policy_range_bindings
                from ashare_pipeline.formal_range_source import FormalRangeSource
                from ashare_pipeline.formal_range_store import FormalRangeStore
                from tests.formal_range_fixtures import (
                    _CapturingRangeTransport, _IdentityRangeNormalizer, _JsonRangeParser,
                )
                bindings = load_policy_range_bindings(self.bundle,
                    scoring_registry=self.scoring,
                    policy_registry=self.policy_registry,
                    expected_purpose=self.purpose)
                self.binding = bindings.for_rule("bank_no_effective_trade_20d", "SH")
                self.transport = _CapturingRangeTransport()
                self.parser = _JsonRangeParser()
                self.normalizer = _IdentityRangeNormalizer()
                self.implementations = {}
                for range_config in (self.binding.calendar_config, self.binding.market_config):
                    key = (range_config.parser_id, range_config.parser_version,
                           range_config.mapping_version, range_config.normalizer_version,
                           range_config.request_version)
                    self.implementations[key] = (self.parser, self.normalizer)
                self.source = FormalRangeSource(self.binding, transport=self.transport,
                                                implementations=self.implementations)
                self.range_store = FormalRangeStore(self.store, root=self.root / "range_raw",
                    signature_verifier=self.verifier,
                    source_factory=self.source_factory,
                    expected_purpose=self.purpose)
        except Exception:
            if hasattr(self, "tempdir"):
                self.tempdir.cleanup()
            raise
        self.policy_context_repository = FormalMetricContextRepository(self.store, self.context,
            registry_signature_verifier=self.verifier)
        self.policy_financial_repository = FormalPolicyFinancialRepository(self.feature_repository,
            current_input_provider=self.provider)
        self._valuation_adapter_runtime = valuation_adapter
        self._policy_industry_ids = set()
        self._policy_context_generations = {}
        if range_enabled:
            from ashare_pipeline.formal_policy_repository import FormalPolicyRepository
            self.policy_repository = FormalPolicyRepository(self.feature_repository, self.context,
                self.range_store, registry_signature_verifier=self.verifier)

    def build_policy_batch(self):
        return self.policy_repository.build_batch(self.frozen.frozen_input_hash,
            scoring_registry=self.scoring, policy_registry=self.policy_registry,
            expected_purpose=self.purpose)

    def populate_policy_evidence(self, *, skip_financial=(), security_state_overrides=None,
                                 financial_overrides=None):
        """Populate every frozen security through the genuine temporary producers."""
        from tests.formal_policy_fixtures import REGULATORY_SEMANTICS
        from ashare_pipeline.formal_range_contract import load_policy_range_bindings
        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        from tests.test_formal_range_source import document_wire
        bindings = load_policy_range_bindings(self.bundle, scoring_registry=self.scoring,
            policy_registry=self.policy_registry,
            expected_purpose=self.purpose)
        rules = self.policy_registry.to_dict()["rules"]
        templates = {member["security_id"]: member["template_id"] for member in self.industry["memberships"]}
        shared_calendars = {}
        skip_financial = set(skip_financial)
        security_state_overrides = dict(security_state_overrides or {})
        financial_overrides = dict(financial_overrides or {})
        if not skip_financial <= set(templates) or not set(security_state_overrides) <= set(templates):
            raise ValueError("fixture evidence overrides require known members")
        for member in self.frozen.members:
            sid = member.security_id
            if sid not in templates:
                continue
            self.put_industry(sid)
            self._policy_industry_ids.add(sid)
            state = dict(is_st=False, is_star_st=False, listing_status="listed",
                         forced_delist_risk=False, suspended=False)
            state.update(security_state_overrides.get(sid, {}))
            self.put_policy_context(sid, "security_state", state)
            self.put_policy_context(sid, "regulatory_state", dict(flags=[
                dict(flag_id=flag, active=False) for flag in REGULATORY_SEMANTICS]))
            if sid not in skip_financial:
                self.policy_financial_values(sid, **financial_overrides.get(sid, {}))
            rule = next(rule for rule in rules if rule["template_id"] == templates[sid]
                        and rule["kind"] == "market_liquidity")
            calendar_key = (rule["rule_id"], sid[:2])
            if self._valuation_adapter_runtime and calendar_key in shared_calendars:
                self.binding, calendar = shared_calendars[calendar_key]
                self.source = self.source_factory(self.binding)
            else:
                self.binding = bindings.for_rule(rule["rule_id"], sid[:2])
                self.source = self.source_factory(self.binding)
                first = self.source.first_calendar_request(FREEZE)
                cursor, end = date.fromisoformat(first.start_date), date.fromisoformat(first.end_date)
                days = {}
                while cursor <= end:
                    days[cursor.isoformat()] = cursor >= end - timedelta(days=19)
                    cursor += timedelta(days=1)
                existing = self.range_store.select_current(first.request_fingerprint)
                if existing is None:
                    self.produce_calendar(days=days)
                else:
                    existing.require_current()
                    wire = existing.to_dict()
                    document = wire["document"]
                    if (wire["request"] != first.to_dict()
                            or wire["generation"]["refresh_generation"] != "g1"
                            or document["coverage"] != dict(start_date=first.start_date,
                                                             end_date=first.end_date, complete=True)
                            or {row["date"]: row["is_open"] for row in document["rows"]} != days
                            or len(document["rows"]) != len(days)):
                        raise ValueError("fixture calendar request or current receipt differs")
                calendar = FormalPolicyMarketRepository(self.range_store).select_calendar(
                    self.binding, FREEZE, expected_purpose=self.purpose)
                if calendar.coverage is None:
                    raise ValueError("fixture calendar must have genuine current coverage")
                calendar.coverage.require_current()
                if self._valuation_adapter_runtime:
                    shared_calendars[calendar_key] = (self.binding, calendar)
            _, source = self.range_store.resolve_planning_binding(
                self.binding, expected_purpose=self.purpose
            )
            for request in source.market_requests(sid, calendar_coverage=calendar.coverage):
                rows = []
                sample = document_wire(request)["rows"][0]
                base = {key: sample[key] for key in ("published_at_utc", "published_precision",
                    "effective_at_utc", "effective_time_evidence_hash", "captured_at_utc")}
                for day in calendar.coverage.trading_days:
                    if request.start_date <= day <= request.end_date:
                        rows.append(dict(base, date=day, exchange_allows_trading=True,
                            volume="1", volume_unit="shares", turnover="2", turnover_unit="CNY",
                            close={"state": "positive", "value": "2"}, close_unit="CNY_per_share"))
                config = source.range_config(request)
                wire = document_wire(request, rows=rows, record_count=len(rows), page_record_count=len(rows),
                    coverage=dict(start_date=request.start_date, end_date=request.end_date, complete=True),
                    parser_id=config.parser_id, parser_version=config.parser_version,
                    mapping_version=config.mapping_version, normalizer_version=config.normalizer_version,
                    request_version=config.request_version)
                task = self.range_store.enqueue(request, refresh_generation="g1")
                self.reply(wire, original_url="https://www.cninfo.com.cn/fixture/range-market.json")
                lease = self.range_store.lease_next("policy-market-fixture", lease_seconds=3600)
                self.assertEqual(lease["id"], task["id"])
                self.range_store.persist(task["id"], "policy-market-fixture", lease["attempt_id"],
                                         fetch=source.fetch_verified(request))
            if self._valuation_adapter_runtime and callable(getattr(self, "_valuation_progress", None)):
                self._valuation_progress("policy", sid)

    def source_factory(self, binding):
        from ashare_pipeline.formal_range_source import FormalRangeSource
        return FormalRangeSource(binding, transport=self.transport,
                                 implementations=self.implementations)

    def reply(self, *args, **kwargs):
        from tests.formal_range_fixtures import RangeSourceFixture
        return RangeSourceFixture.reply(self, *args, **kwargs)

    def produce_calendar(self, *args, **kwargs):
        from tests.formal_range_fixtures import RangeStoreFixture
        return RangeStoreFixture.produce_calendar(self, *args, **kwargs)

    def put_window(self, *args, **kwargs):
        from tests.formal_range_fixtures import RangeStoreFixture
        return RangeStoreFixture.put_window(self, *args, **kwargs)

    def put_policy_context(self, security_id, kind, value, *, generation="g1"):
        """Persist only this temporary graph's signed Context producer chain."""
        if (type(security_id) is not str or canonical_security_id(security_id) != security_id
                or security_id not in {member.security_id for member in self.frozen.members}):
            raise ValueError("policy Context security must be a canonical frozen-universe member")
        if kind not in ("security_state", "regulatory_state", "event_calendar"):
            raise ValueError("policy Context fixture supports only state and event kinds")
        if type(generation) is not str or not generation or generation.strip() != generation:
            raise ValueError("generation must be canonical text")
        scope = "fixture-state" if kind == "security_state" else "fixture-policy-" + kind
        request = self.resolver.resolve(context_kind=kind, scope_key=scope, security_id=security_id,
            as_of_utc=FREEZE, registry_manifest_hash=self.bundle.manifest.manifest_hash,
            upstream_generation=generation, expected_purpose=self.purpose)
        # New generations represent later corrections, with deterministic fixture times.
        generations = self._policy_context_generations.setdefault((security_id, kind), {})
        if generation not in generations:
            generations[generation] = len(generations)
        published = (date(2026, 8, 20) + timedelta(days=generations[generation])).isoformat() + "T07:00:00+00:00"
        raw = canonical(dict(value=value, no_coverage=False))
        task = self.store.enqueue_formal_task("formal_context",
            hashlib.sha256(request.canonical_bytes() + raw).hexdigest(), request.refresh_generation, {})
        worker = "policy-context-fixture"
        leased = self.store.lease_next_formal_task(("formal_context",), worker, 300)
        self.assertEqual(leased["id"], task)
        fetch = OfficialFetch(request=request.official_request, raw_bytes=raw,
            original_url="https://www.cninfo.com.cn/fixture/context.json",
            published_at_utc=published, published_precision="timestamp", source_updated_at_utc=None,
            captured_at_utc="2026-09-04T07:00:00+00:00", effective_at_utc=published,
            effective_time_evidence_hash=None, refresh_generation=request.refresh_generation,
            parser_id=request.parser_id, parser_version=request.parser_version, mapping_version=request.mapping_version,
            declared_security_id=security_id, declared_period=request.official_request.period_or_date)
        verification = verify_official_fetch(fetch, SourcePolicy.cninfo())
        self.assertEqual(verification.status, "verified")
        ref = self.snapshots.persist_verified(fetch, verification, producing_task_id=task, worker_id=worker)
        receipt = FormalContextRegistry.load(self.store, self.verifier,
            self.bundle.manifest.manifest_hash,
            expected_purpose=self.purpose).normalize_verified(request, ref, raw,
            FixtureNormalizer(), task_id=task, worker_id=worker)
        self.store.put_formal_context_facts(
            receipt, expected_purpose=self.purpose
        )
        self.store.complete_formal_task(task, worker, {"snapshot": ref.snapshot_id})
        return receipt.facts[0], ref

    def state_selection(self, security_id):
        from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
        member = next(m for m in self.industry["memberships"] if m["security_id"] == security_id)
        return FormalPolicyStateRepository(self.context).select(security_id, FREEZE,
            template_id=member["template_id"],
            policy_registry=self.policy_registry,
            expected_purpose=self.purpose)

    def financial_selection(self, security_id):
        if security_id not in self._policy_industry_ids:
            self.put_industry(security_id)
            self._policy_industry_ids.add(security_id)
        universe = self.policy_context_repository.load_universe(self.frozen.frozen_input_hash,
            scoring_registry=self.scoring, expected_purpose=self.purpose)
        industry = self.policy_context_repository.resolve_industries(universe)
        member = next(m for m in self.industry["memberships"] if m["security_id"] == security_id)
        selected = self.policy_financial_repository.select(security_id, FREEZE,
            template_id=member["template_id"],
            policy_registry=self.policy_registry, industry_batch=industry,
            expected_purpose=self.purpose)
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
