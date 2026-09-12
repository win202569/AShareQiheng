"""Byte-sensitive signed range-catalog fixtures; never production mappings."""

import hashlib
import json
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

    def send(self, request):
        self.requests.append(request)
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
        config = self.binding.calendar_config
        key = (
            config.parser_id,
            config.parser_version,
            config.mapping_version,
            config.normalizer_version,
            config.request_version,
        )
        registry = {key: (self.parser, self.normalizer)}
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
            for day, opened in sorted(days.items()):
                if request.start_date <= day <= request.end_date:
                    row = dict(document_wire(request)["rows"][0], date=day, is_open=opened)
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

    def close(self):
        self.temp.cleanup()
