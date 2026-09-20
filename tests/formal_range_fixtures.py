"""Byte-sensitive signed range-catalog fixtures; never production mappings."""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
import tempfile

from ashare_pipeline.formal_policy_registry import load_formal_policy_registry
from ashare_pipeline.formal_range_contract import load_policy_range_bindings
from ashare_pipeline.formal_range_source import FormalRangeSource
from ashare_pipeline.formal_sources import SignedSourceRegistry, TransportResponse
from tests.formal_policy_fixtures import policy_graph, rehash_documents
from tests.test_formal_context_repository import descriptor
from tests.test_formal_scoring_registry import canonical
from tests.test_formal_sources import config


def range_entry(**changes):
    entry = dict(
        schema_version="formal-range-source-config-v1",
        capability="verified_market_window_v1",
        kind="calendar_range",
        anchor_descriptor_id="a" * 64,
        calendar_descriptor_id="a" * 64,
        source="cninfo",
        dataset="fixture-range-calendar",
        endpoint_url="https://www.cninfo.com.cn/fixture/range-calendar.json",
        http_method="GET",
        parser_id="fixture-range-parser",
        parser_version="fixture-range-v1",
        mapping_version="fixture-range-map-v1",
        normalizer_version="fixture-range-normalizer-v1",
        request_version="formal-range-request-v1",
        exchange_scope="SH",
        calendar_anchor_selector=None,
        request_template=dict(
            query={
                "start": "{start_date}",
                "end": "{end_date}",
                "exchange": "{exchange}",
                "page": "{page_index}",
            },
            headers={"accept": "application/json"},
            body=None,
        ),
        pagination="single_response_v1",
        max_pages=1,
        max_calendar_days_per_request=400,
        timeout_seconds=3.0,
        retry_base_seconds=1.0,
        retry_max_attempts=2,
        challenge_cooldown_seconds=15.0,
    )
    entry.update(changes)
    return entry


def _descriptor_id(entry):
    return hashlib.sha256(canonical(entry)).hexdigest()


def add_range_documents(documents):
    """Add only Bx/config/range declarations to an already-complete policy graph."""
    wrapper = documents["scoring"]
    source = documents["source"]

    bootstrap = config(
        dataset="trading_calendar",
        endpoint_url="https://www.cninfo.com.cn/fixture/bootstrap-calendar.json",
        request_template={
            "query": {"date": "{period_or_date}"},
            "headers": {"accept": "application/json"},
            "body": None,
        },
        exchange_scope=None,
        calendar_selector=None,
        bootstrap_calendar=True,
    )
    identities = {
        (item["source"], item["dataset"], item["exchange_scope"])
        for item in source["configs"]
    }
    identity = (bootstrap["source"], bootstrap["dataset"], None)
    if identity not in identities:
        source["configs"].append(bootstrap)

    bootstrap_by_exchange = {}
    for exchange in ("SH", "SZ", "BJ"):
        entry = descriptor(
            "trading_calendar",
            scope_key=f"fixture-range-calendar-{exchange.lower()}",
            security_scope="none",
            request_security="none",
            exchange_rule="fixed_exchange",
            fixed_exchange=exchange,
            source="cninfo",
            dataset="trading_calendar",
            calendar_selector=None,
            bootstrap_calendar=True,
        )
        wrapper["descriptors"].append(entry)
        bootstrap_by_exchange[exchange] = (entry, _descriptor_id(entry))

    policy = documents["status"]
    rule_id = next(
        rule_id
        for rule_id in policy["rules"]["execution_contract"]["rule_ids"]
        if policy["rules"][rule_id]["kind"] == "market_liquidity"
    )
    rule = policy["rules"][rule_id]
    market_selector = rule["inputs"]["market"]
    calendar_selector = rule["inputs"]["calendar"]
    descriptors = {
        _descriptor_id(entry): entry for entry in wrapper["descriptors"]
    }
    market_descriptor = descriptors[market_selector["descriptor_id"]]

    ranges = []
    for exchange in ("SH", "SZ", "BJ"):
        bootstrap_entry, bootstrap_id = bootstrap_by_exchange[exchange]
        ranges.append(
            range_entry(
                anchor_descriptor_id=bootstrap_id,
                calendar_descriptor_id=bootstrap_id,
                source=bootstrap_entry["source"],
                dataset=bootstrap_entry["dataset"],
                exchange_scope=exchange,
            )
        )
        ranges.append(
            range_entry(
                kind="market_range",
                anchor_descriptor_id=market_selector["descriptor_id"],
                calendar_descriptor_id=bootstrap_id,
                source=market_descriptor["source"],
                dataset=market_descriptor["dataset"],
                endpoint_url="https://www.cninfo.com.cn/fixture/range-market.json",
                calendar_anchor_selector={
                    "selector": dict(calendar_selector),
                    "exchange": exchange,
                },
                request_template=dict(
                    query={
                        "symbol": "{security_id}",
                        "start": "{start_date}",
                        "end": "{end_date}",
                        "exchange": "{exchange}",
                        "page": "{page_index}",
                    },
                    headers={"accept": "application/json"},
                    body=None,
                ),
                exchange_scope=exchange,
            )
        )
    source.update(
        schema_version="formal-source-registry-v2",
        range_configs=ranges,
    )


def range_graph(*, mutate=None):
    def prepare(documents):
        add_range_documents(documents)
        if mutate is not None:
            mutate(documents)
        rehash_documents(documents)

    return policy_graph(mutate=prepare)


class _CapturingRangeTransport:
    def __init__(self):
        self.requests = []
        self.response = None
        self.error = None
        self.on_send = None

    @property
    def calls(self):
        return self.requests

    def send(self, request):
        self.requests.append(request)
        if self.on_send is not None:
            self.on_send(request)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise RuntimeError("fixture transport has no reply")
        return self.response


class _JsonRangeParser:
    def __init__(self):
        self.calls = []

    def parse(self, raw_bytes, *, request, config):
        self.calls.append((raw_bytes, request, config))
        return json.loads(raw_bytes.decode("utf-8"))


class _IdentityRangeNormalizer:
    def __init__(self):
        self.calls = []

    def normalize(self, wire, *, request, config):
        self.calls.append((wire, request, config))
        return wire


class RangeSourceFixture:
    """A genuine signed binding with only in-memory range bytes and transport."""

    def __init__(self, *, mutate=None, implementations=None):
        bundle, vocabulary, scoring, graph, verifier = range_graph(mutate=mutate)
        self.bundle, self.graph, self.verifier = bundle, graph, verifier
        policy = load_formal_policy_registry(
            bundle, scoring_registry=scoring, feature_registry=vocabulary
        )
        bindings = load_policy_range_bindings(
            bundle, scoring_registry=scoring, policy_registry=policy
        )
        self.binding = bindings.for_rule("bank_no_effective_trade_20d", "SH")
        source_blob = bundle.blob("source")
        self.registry = SignedSourceRegistry.from_signed_bytes(
            source_blob.canonical_json,
            source_blob.signature,
            source_blob.key_id,
            verifier,
        )
        self.transport = _CapturingRangeTransport()
        self.parser = _JsonRangeParser()
        self.normalizer = _IdentityRangeNormalizer()
        calendar_config = self.binding.calendar_config
        market_config = self.binding.market_config
        calendar_key = (
            calendar_config.parser_id,
            calendar_config.parser_version,
            calendar_config.mapping_version,
            calendar_config.normalizer_version,
            calendar_config.request_version,
        )
        market_key = (
            market_config.parser_id,
            market_config.parser_version,
            market_config.mapping_version,
            market_config.normalizer_version,
            market_config.request_version,
        )
        self.market_parser = self.parser if market_key == calendar_key else _JsonRangeParser()
        self.market_normalizer = (self.normalizer if market_key == calendar_key
                                  else _IdentityRangeNormalizer())
        registry = {
            calendar_key: (self.parser, self.normalizer),
            market_key: (self.market_parser, self.market_normalizer),
        }
        if implementations is not None:
            registry = implementations
        self.implementations = registry
        self.source = FormalRangeSource(
            self.binding,
            transport=self.transport,
            implementations=registry,
        )

    def reply(self, wire, *, status_code=200,
              original_url="https://www.cninfo.com.cn/fixture/range-calendar.json",
              headers=None, captured_at_utc="2026-08-31T06:59:00+00:00"):
        self.transport.response = TransportResponse(
            status_code=status_code,
            original_url=original_url,
            headers={} if headers is None else headers,
            raw_bytes=canonical(wire),
            captured_at_utc=captured_at_utc,
        )

    def close(self):
        pass


class RangeStoreFixture(RangeSourceFixture):
    """Temporary V7 state populated only through genuine producer operations."""

    def __init__(self, **kwargs):
        from ashare_pipeline.state_store import StateStore
        from ashare_pipeline.formal_range_store import FormalRangeStore
        self.temp = tempfile.TemporaryDirectory()
        try:
            super().__init__(**kwargs)
            self.root = Path(self.temp.name)
            self.store = StateStore(self.root / "state.sqlite", registry_signature_verifier=self.verifier)
            self.store.initialize()
            for blob in self.graph.blobs.values():
                self.store.put_formal_registry_blob(blob)
            self.store.put_formal_registry_manifest(self.graph.manifest)
            self.range_store = FormalRangeStore(self.store, root=self.root,
                signature_verifier=self.verifier, source_factory=self.source_factory)
        except BaseException:
            self.temp.cleanup()
            raise

    def source_factory(self, binding):
        return FormalRangeSource(binding, transport=self.transport, implementations=self.implementations)

    def produce_calendar(self, *, days, generation="g1", omit_pages=()):
        from tests.test_formal_range_source import document_wire
        if type(days) is not dict or not days or any(type(value) is not bool for value in days.values()):
            raise ValueError("fixture days require explicit nonempty boolean mapping")
        request = self.source.first_calendar_request("2026-08-31T07:00:00+00:00")
        observations = []
        while request is not None:
            rows = []
            base_row = document_wire(request)["rows"][0]
            for day, opened in sorted(days.items()):
                if request.start_date <= day <= request.end_date:
                    row = dict(base_row, date=day, is_open=opened)
                    rows.append(row)
            config = self.binding.calendar_config
            count = min(config.max_pages, max(1, len(rows))) if config.pagination != "single_response_v1" else 1
            pages = [rows[index::count] for index in range(count)]
            last = None
            for index in range(1, count + 1):
                task = self.range_store.enqueue(request, refresh_generation=generation)
                if index in omit_pages:
                    return tuple(observations)
                wire = document_wire(request, rows=pages[index - 1], record_count=len(rows), page_record_count=len(pages[index - 1]),
                    page_count=count, page_index=index,
                    parser_id=config.parser_id, parser_version=config.parser_version,
                    mapping_version=config.mapping_version,
                    normalizer_version=config.normalizer_version,
                    request_version=config.request_version,
                    pagination_evidence="signed_single_response_v1" if count == 1 and config.pagination == "single_response_v1" else "source_declared_numbered_pages_v1",
                    coverage=dict(start_date=request.start_date, end_date=request.end_date, complete=bool(rows)))
                self.reply(wire)
                lease = self.range_store.lease_next("fixture-worker", lease_seconds=3600)
                if lease is None:
                    last = self.range_store.read_verified(task["id"])
                else:
                    if lease["id"] != task["id"]:
                        raise ValueError("fixture has an unrelated pending task")
                    last = self.range_store.persist(task["id"], "fixture-worker", lease["attempt_id"], fetch=self.source.fetch_verified(request))
                observations.append(last)
                if index < count:
                    request = self.source.next_page(last)
            if request.start_date <= min(days):
                break
            request = self.source.previous_calendar_request(last)
        return tuple(observations)

    def put_window(self, security_id, *, trading_days, rows, generation="g1",
                   missing_calendar_dates=(), omit_pages=()):
        """Persist a genuine explicit calendar and raw daily market rows."""
        if (type(security_id) is not str or not security_id.startswith("SH")
                or type(trading_days) is not tuple or not trading_days
                or tuple(sorted(set(trading_days))) != trading_days
                or type(rows) is not dict or not set(rows) <= set(trading_days)):
            raise ValueError("fixture market window inputs are invalid")
        forbidden = {"stale_days", "veto", "confirmed_no_price"}
        expected = {"exchange_allows_trading", "volume", "turnover", "close"}
        conflict = {"coverage", "reason"}
        if any(type(value) is not dict or set(value) not in (expected, conflict)
               or forbidden & set(value)
               or (set(value) == conflict and (value["coverage"] != "domain_conflict"
                   or type(value["reason"]) is not str or not value["reason"]))
               for value in rows.values()):
            raise ValueError("fixture rows must contain raw market operands or a typed domain conflict")
        missing_calendar_dates = tuple(missing_calendar_dates)
        omit_pages = tuple(omit_pages)
        if any(type(item) is not str for item in (*missing_calendar_dates,)) or any(
                type(item) is not int or item <= 0 for item in omit_pages):
            raise ValueError("fixture omissions are invalid")

        first_request = self.source.first_calendar_request("2026-08-31T07:00:00+00:00")
        start = date.fromisoformat(first_request.start_date)
        end = date.fromisoformat(first_request.end_date)
        explicit = {}
        cursor = start
        trading = set(trading_days)
        missing_calendar = set(missing_calendar_dates)
        while cursor <= end:
            text = cursor.isoformat()
            if text not in missing_calendar:
                explicit[text] = text in trading
            cursor += timedelta(days=1)
        self.produce_calendar(days=explicit, generation=generation)

        from ashare_pipeline.formal_policy_market import FormalPolicyMarketRepository
        from tests.test_formal_range_source import document_wire
        repository = FormalPolicyMarketRepository(self.range_store)
        calendar = repository.select_calendar(self.binding, "2026-08-31T07:00:00+00:00")
        if calendar.coverage is None:
            return ()
        _, source = self.range_store.resolve_planning_binding(self.binding)
        requests = source.market_requests(security_id, calendar_coverage=calendar.coverage)
        observations = []
        for request in requests:
            config = source.range_config(request)
            selected = [(day, rows[day]) for day in trading_days
                        if request.start_date <= day <= request.end_date and day in rows]
            count = (min(config.max_pages, max(1, len(selected)))
                     if config.pagination != "single_response_v1" else 1)
            pages = [selected[index::count] for index in range(count)]
            current = request
            for index in range(1, count + 1):
                task = self.range_store.enqueue(current, refresh_generation=generation)
                if index in omit_pages:
                    return tuple(observations)
                market_rows = []
                base = document_wire(current)["rows"][0]
                for day, raw in pages[index - 1]:
                    visibility = {key: base[key] for key in (
                        "published_at_utc", "published_precision", "effective_at_utc",
                        "effective_time_evidence_hash", "captured_at_utc")}
                    if raw.get("coverage") == "domain_conflict":
                        market_rows.append({"date": day, "coverage": "domain_conflict",
                                            "reason": raw["reason"], **visibility})
                    else:
                        market_rows.append({
                            "date": day,
                            "exchange_allows_trading": raw["exchange_allows_trading"],
                            "volume": raw["volume"],
                            "volume_unit": "shares",
                            "turnover": raw["turnover"],
                            "turnover_unit": "CNY",
                            "close": dict(raw["close"]),
                            "close_unit": "CNY_per_share",
                            **visibility,
                        })
                wire = document_wire(current, rows=market_rows, record_count=len(selected),
                    page_record_count=len(market_rows), page_count=count, page_index=index,
                    upstream_generation=f"fixture-market-{generation}",
                    parser_id=config.parser_id, parser_version=config.parser_version,
                    mapping_version=config.mapping_version,
                    normalizer_version=config.normalizer_version,
                    request_version=config.request_version,
                    pagination_evidence="signed_single_response_v1" if count == 1 and config.pagination == "single_response_v1" else "source_declared_numbered_pages_v1",
                    coverage={"start_date": current.start_date, "end_date": current.end_date,
                              "complete": bool(market_rows)})
                self.reply(wire,
                    original_url="https://www.cninfo.com.cn/fixture/range-market.json")
                lease = self.range_store.lease_next("fixture-market-worker", lease_seconds=3600)
                if lease is None:
                    observation = self.range_store.read_verified(task["id"])
                else:
                    observation = self.range_store.persist(task["id"], "fixture-market-worker",
                        lease["attempt_id"], fetch=source.fetch_verified(current))
                observations.append(observation)
                if index < count:
                    current = source.next_page(observation)
        return tuple(observations)

    def close(self):
        self.temp.cleanup()


class RangeWorkerFixture(RangeStoreFixture):
    """Real worker/store/source with an in-memory, countable fake transport."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from ashare_pipeline.formal_range_worker import FormalRangeWorker
        self.worker = FormalRangeWorker(self.range_store,
            source_factory=self.source_factory, worker_id="fixture-worker")

    def enqueue_calendar(self, *, refresh_generation="g1"):
        from tests.test_formal_range_source import document_wire
        request = self.source.first_calendar_request("2026-08-31T07:00:00+00:00")
        self.reply(document_wire(request))
        self.range_store.enqueue(request, refresh_generation=refresh_generation)
        return request

    def restart_worker(self):
        from ashare_pipeline.state_store import StateStore
        from ashare_pipeline.formal_range_store import FormalRangeStore
        from ashare_pipeline.formal_range_worker import FormalRangeWorker
        self.store = StateStore(self.root / "state.sqlite", registry_signature_verifier=self.verifier)
        self.store.initialize()
        self.range_store = FormalRangeStore(self.store, root=self.root,
            signature_verifier=self.verifier, source_factory=self.source_factory)
        self.source = self.source_factory(self.binding)
        self.worker = FormalRangeWorker(self.range_store,
            source_factory=self.source_factory, worker_id="restarted-worker")
