"""Closed Context records: mutations must never cross the audit boundary."""

import hashlib
import importlib
import importlib.util
import json
import unittest


FREEZE = "2026-08-31T07:00:00+00:00"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fact_wire(kind="security_state", value=None, **changes):
    wire = dict(context_kind=kind, scope_key="fixture-state", security_id="SZ000001",
        as_of_utc=FREEZE, value=value if value is not None else dict(is_st=False,
        is_star_st=False, listing_status="listed", forced_delist_risk=False, suspended=False),
        no_coverage=False, published_at_utc="2026-08-20T07:00:00+00:00",
        effective_at_utc="2026-08-20T07:00:00+00:00", source_updated_at_utc=None,
        captured_at_utc="2026-09-04T07:00:00+00:00", refresh_generation="a" * 64,
        source_snapshot_id="00000000-0000-4000-8000-000000000001",
        source_content_sha256="b" * 64, parser_id="fixture-parser", parser_version="fixture-v1",
        mapping_version="fixture-map-v1", registry_manifest_hash="c" * 64,
        evidence=dict(descriptor_id="d" * 64, normalizer_version="fixture-normalizer-v1", normalization_input_hash="2" * 64, upstream_generation="fixture-upstream-v1", relevant_registry_hashes=[["scoring", "e" * 64],
        ["source", "f" * 64]], request_fingerprint="0" * 64, calendar_binding=None))
    wire.update(changes)
    return wire


class ContextSchemaTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_context_schema"),
            "Context schema must enforce sealed canonical records")
        self.api = importlib.import_module("ashare_pipeline.formal_context_schema")

    def test_fact_id_detachment_and_creation_time_exclusion(self):
        wire = fact_wire()
        fact = self.api.FormalContextFact.create(**wire)
        self.assertEqual(fact.id, hashlib.sha256(canonical(wire)).hexdigest())
        wire["value"]["is_st"] = True
        self.assertFalse(fact.to_dict()["value"]["is_st"])
        detached = fact.to_dict()
        detached["evidence"]["relevant_registry_hashes"].clear()
        self.assertEqual(len(fact.to_dict()["evidence"]["relevant_registry_hashes"]), 2)
        self.assertEqual(self.api.FormalContextFact.from_dict(fact.to_dict()).id, fact.id)

    def test_forgery_and_mutation_are_rejected(self):
        fact = self.api.FormalContextFact.create(**fact_wire())
        forged = object.__new__(self.api.FormalContextFact)
        with self.assertRaises(ValueError):
            forged.to_dict()
        with self.assertRaises((ValueError, AttributeError, TypeError)):
            fact.value = {}
        object.__setattr__(fact, "_canonical", canonical(fact_wire(no_coverage=True)))
        with self.assertRaises(ValueError):
            fact.to_dict()

    def test_aliases_non_json_and_nonfinite_values_are_rejected(self):
        shared = {"estimate": 1}
        for estimates in ([shared, shared], [{"x": float("nan")}], [{"x": object()}], [{1: 2}]):
            with self.subTest(estimates=repr(estimates)), self.assertRaises(ValueError):
                self.api.FormalContextFact.create(**fact_wire("consensus_snapshot",
                    dict(coverage_status="covered", estimates=estimates)))

    def test_closed_per_kind_values(self):
        good = {
            "trading_calendar": dict(exchange="SZ", calendar_version="fixture-v1", trading_days=["2026-08-31", "2026-09-02"]),
            "market_close": dict(exchange="SZ", exchange_allows_trading=True, volume="10", turnover="100", is_effective_trade=True, valid_close="10", valid_close_date="2026-08-31", stale_trading_days=0),
            "security_state": fact_wire()["value"],
            "industry_snapshot": dict(classification_system="SW2021", primary_industry="bank", secondary_industry="regional", source_version="fixture-v1", effective_date="2026-08-20", mapping_sha256="1" * 64),
            "regulatory_state": dict(flags=[dict(flag_id="fixture-flag", active=True)]),
            "event_calendar": dict(events=[dict(event_id="fixture-event", event_date="2026-09-01", quantified_value="1", unit="CNY")]),
            "consensus_snapshot": dict(coverage_status="covered", estimates=[dict(value="10", period="2026")]),
        }
        for kind, value in good.items():
            with self.subTest(kind=kind):
                fact = self.api.FormalContextFact.create(**fact_wire(kind, value))
                self.assertEqual(fact.value, value)
                with self.assertRaises(ValueError):
                    self.api.FormalContextFact.create(**fact_wire(kind, {**value, "extra": 1}))
                for field in value:
                    bad = dict(value)
                    del bad[field]
                    with self.assertRaises(ValueError):
                        self.api.FormalContextFact.create(**fact_wire(kind, bad))

    def test_cutoffs_are_inclusive_and_late_capture_is_allowed(self):
        for field in ("published_at_utc", "effective_at_utc", "source_updated_at_utc"):
            self.api.FormalContextFact.create(**fact_wire(**{field: FREEZE}))
            for invalid in ("2026-08-31T07:00:01+00:00", "2026-08-30T07:00:00", 0):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    self.api.FormalContextFact.create(**fact_wire(**{field: invalid}))

    def test_market_stale_rules_and_exact_types(self):
        base = dict(exchange="SZ", exchange_allows_trading=False, volume="0", turnover="0", is_effective_trade=False, valid_close="10.5", valid_close_date="2026-08-28", stale_trading_days=1)
        self.api.FormalContextFact.create(**fact_wire("market_close", base))
        for change in (dict(valid_close="0"), dict(valid_close=None), dict(volume="1.0"),
            dict(stale_trading_days=True), dict(stale_trading_days=0), dict(valid_close_date="2026-08-31"),
            dict(is_effective_trade=1), dict(turnover="NaN")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.api.FormalContextFact.create(**fact_wire("market_close", {**base, **change}))

    def test_no_coverage_is_explicit_and_consensus_only(self):
        for kind, value in (("security_state", fact_wire()["value"]),
            ("consensus_snapshot", dict(coverage_status="covered", estimates=[])),
            ("consensus_snapshot", dict(coverage_status="no_valid_coverage", estimates=[{"x": 1}]))):
            with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                self.api.FormalContextFact.create(**fact_wire(kind, value, no_coverage=True))
        with self.assertRaises(ValueError):
            self.api.FormalContextFact.create(**fact_wire("consensus_snapshot", dict(coverage_status="covered", estimates=[])))

    def test_event_quantity_is_signed_but_market_volume_is_nonnegative(self):
        value = dict(events=[dict(event_id="fixture-change", event_date="2026-09-01",
            quantified_value="-1.25", unit="CNY")])
        self.assertEqual(self.api.FormalContextFact.create(**fact_wire("event_calendar", value)).value, value)
        market = dict(exchange="SZ", exchange_allows_trading=True, volume="-1.25", turnover="100",
            is_effective_trade=True, valid_close="10", valid_close_date="2026-08-31", stale_trading_days=0)
        with self.assertRaises(ValueError):
            self.api.FormalContextFact.create(**fact_wire("market_close", market))

    def test_malformed_calendar_industry_and_allowlist_entry_values(self):
        for days in ([], ["2026-09-02", "2026-08-31"], ["2026-08-31", "2026-08-31"], ["not-a-day"]):
            with self.subTest(days=days), self.assertRaises(ValueError):
                self.api.FormalContextFact.create(**fact_wire("trading_calendar", dict(exchange="SZ", calendar_version="v1", trading_days=days)))
        for kind, value in (("industry_snapshot", dict(classification_system="SW2008", primary_industry="bank", secondary_industry="regional", source_version="v1", effective_date="2026-08-20", mapping_sha256="1" * 64)),
            ("regulatory_state", dict(flags=[dict(flag_id="x", active=True), dict(flag_id="x", active=False)])),
            ("event_calendar", dict(events=[dict(event_id="x", event_date="not-a-date", quantified_value="1", unit="CNY")])),
            ("security_state", {**fact_wire()["value"], "listing_status": "unknown"})):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.api.FormalContextFact.create(**fact_wire(kind, value))

    def test_issue_is_sealed_detached_audit_data(self):
        details = {"reason": ["missing_source"]}
        issue = self.api.FormalContextIssue.create(code="pending", context_kind="security_state",
            scope_key="fixture-state", security_id="SZ000001", as_of_utc=FREEZE, details=details)
        details["reason"].clear()
        self.assertEqual(issue.to_dict()["details"], {"reason": ["missing_source"]})
        with self.assertRaises(ValueError):
            object.__new__(self.api.FormalContextIssue).to_dict()
