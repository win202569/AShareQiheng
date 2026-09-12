"""Byte-sensitive signed range-catalog fixtures; never production mappings."""

import hashlib

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
