"""Closed signed range catalog and active-policy binding tests."""

import copy
import hashlib
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_evidence import OfficialRequest
from ashare_pipeline.formal_policy_registry import load_formal_policy_registry
from ashare_pipeline.formal_sources import SignedSourceRegistry
from tests.formal_range_fixtures import range_entry, range_graph
from tests.test_formal_scoring_registry import HmacVerifier, canonical
from tests.test_formal_sources import config


class FormalRangeContractTests(unittest.TestCase):
    def _registry(self, wire):
        verifier = HmacVerifier()
        raw = canonical(wire)
        return SignedSourceRegistry.from_signed_bytes(
            raw, verifier.sign(raw), "scoring-test-key", verifier
        )

    def _load(self, mutate=None):
        from ashare_pipeline.formal_range_contract import load_policy_range_bindings

        bundle, vocabulary, scoring, repository, verifier = range_graph(mutate=mutate)
        policy = load_formal_policy_registry(
            bundle, scoring_registry=scoring, feature_registry=vocabulary
        )
        bindings = load_policy_range_bindings(
            bundle, scoring_registry=scoring, policy_registry=policy
        )
        return bindings, bundle, vocabulary, scoring, policy, repository, verifier

    def test_closed_range_contract(self):
        from ashare_pipeline.formal_range_contract import parse_range_entry

        self.assertEqual(parse_range_entry(range_entry()).to_dict(), range_entry())
        for changes in (
            {"max_pages": True},
            {"max_pages": 2},
            {"exchange_scope": None},
            {"unapproved": 1},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                parse_range_entry(range_entry(**changes))

    def test_range_format_rejects_wrong_types_versions_templates_and_bridge_shapes(self):
        from ashare_pipeline.formal_range_contract import parse_range_entry

        invalid = (
            {"schema_version": "other"},
            {"capability": "other"},
            {"kind": "other"},
            {"anchor_descriptor_id": "A" * 64},
            {"source": "blog"},
            {"endpoint_url": "http://www.cninfo.com.cn/range.json"},
            {"http_method": "PATCH"},
            {"normalizer_version": ""},
            {"request_version": "formal-context-request-v1"},
            {"pagination": "unknown"},
            {"max_calendar_days_per_request": 0},
            {"timeout_seconds": float("nan")},
            {"retry_max_attempts": True},
            {"calendar_anchor_selector": {}},
            {
                "request_template": {
                    "query": {"date": "{period_or_date}"},
                    "headers": {},
                    "body": None,
                }
            },
            {
                "request_template": {
                    "query": {"symbol": "{security_id}"},
                    "headers": {},
                    "body": None,
                }
            },
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                parse_range_entry(range_entry(**changes))

        bridge = {
            "selector": {
                "kind": "context",
                "descriptor_id": "b" * 64,
                "context_kind": "trading_calendar",
                "scope_key": "calendar",
                "field": "record",
                "entry_id": None,
                "expected_type": "calendar_record",
                "expected_unit": None,
            },
            "exchange": "SH",
        }
        market = range_entry(
            kind="market_range",
            calendar_anchor_selector=bridge,
            request_template={
                "query": {"symbol": "{security_id}"},
                "headers": {},
                "body": None,
            },
        )
        self.assertEqual(parse_range_entry(market).to_dict(), market)
        for bad_bridge in (
            None,
            {**bridge, "extra": 1},
            {**bridge, "exchange": "SZ"},
            {"selector": {**bridge["selector"], "descriptor_id": "bad"}, "exchange": "SH"},
        ):
            with self.subTest(bridge=bad_bridge), self.assertRaises(ValueError):
                parse_range_entry({**market, "calendar_anchor_selector": bad_bridge})

    def test_source_registry_versions_are_closed_and_old_configs_stay_closed(self):
        v1 = {
            "registry_role": "source",
            "schema_version": "formal-source-registry-v1",
            "configs": [config()],
        }
        self.assertEqual(self._registry(v1).range_configs, ())
        for bad in (
            {**v1, "range_configs": []},
            {
                "registry_role": "source",
                "schema_version": "formal-source-registry-v2",
                "configs": [config()],
            },
            {
                "registry_role": "source",
                "schema_version": "formal-source-registry-v2",
                "configs": [{**config(), "max_pages": 1}],
                "range_configs": [range_entry()],
            },
        ):
            with self.subTest(wire=bad), self.assertRaises(ValueError):
                self._registry(bad)

    def test_v2_registry_keeps_legacy_selection_separate_and_seals_range_snapshots(self):
        wire = {
            "registry_role": "source",
            "schema_version": "formal-source-registry-v2",
            "configs": [config()],
            "range_configs": [range_entry()],
        }
        registry = self._registry(wire)
        self.assertIsInstance(registry.range_configs, tuple)
        self.assertEqual(len(registry.range_configs), 1)
        selected = registry.select(OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ"))
        self.assertEqual(selected.dataset, "annual_report")
        snapshot = SignedSourceRegistry._trusted_range_config_snapshots(registry)[0]
        self.assertIsNot(snapshot, registry.range_configs[0])
        self.assertEqual(snapshot.entry_id, registry.range_configs[0].entry_id)

        original = registry.range_configs[0]
        with patch.object(type(original), "to_dict", return_value={"forged": True}):
            self.assertEqual(
                SignedSourceRegistry._trusted_range_config_snapshots(registry)[0].dataset,
                "fixture-range-calendar",
            )

        object.__setattr__(original, "dataset", "unsigned-dataset")
        with self.assertRaises(ValueError):
            registry._require_verified()

        registry = self._registry(wire)
        object.__setattr__(registry, "range_configs", ())
        with self.assertRaises(ValueError):
            registry._require_verified()

    def test_complete_graph_binds_every_active_market_rule_for_every_exchange(self):
        bindings, bundle, _, _, policy, *_ = self._load()
        market_rules = [rule for rule in policy.rules if rule["kind"] == "market_liquidity"]
        self.assertEqual(len(market_rules), 5)
        checked_current = False
        for rule in market_rules:
            for exchange in ("SH", "SZ", "BJ"):
                binding = bindings.for_rule(rule["rule_id"], exchange)
                if not checked_current:
                    binding.require_current()
                    checked_current = True
                self.assertEqual(binding.registry_manifest_hash, bundle.manifest.manifest_hash)
                self.assertEqual(binding.market_config.kind, "market_range")
                self.assertEqual(binding.calendar_config.kind, "calendar_range")
                self.assertEqual(binding.market_config.exchange_scope, exchange)
                self.assertEqual(binding.calendar_config.exchange_scope, exchange)
                self.assertEqual(binding.market_config.calendar_descriptor_id,
                                 binding.calendar_config.calendar_descriptor_id)
                self.assertEqual(binding.policy_calendar_selector["exchange"], exchange)
                self.assertEqual(len(binding.binding_hash), 64)
        with self.assertRaises(ValueError):
            bindings.for_rule("unknown", "SH")
        with self.assertRaises(ValueError):
            bindings.for_rule(market_rules[0]["rule_id"], "HK")

    def test_absent_and_duplicate_pairs_are_contract_failures(self):
        def absent(documents):
            ranges = documents["source"]["range_configs"]
            ranges[:] = [item for item in ranges
                         if not (item["kind"] == "market_range" and item["exchange_scope"] == "SH")]

        def duplicate(documents):
            item = next(item for item in documents["source"]["range_configs"]
                        if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            documents["source"]["range_configs"].append(copy.deepcopy(item))

        for mutate in (absent, duplicate):
            with self.subTest(mutate=mutate.__name__), self.assertRaises(ValueError):
                self._load(mutate)

    def test_wrong_source_exchange_and_active_capability_are_rejected(self):
        def wrong_source(documents):
            item = next(item for item in documents["source"]["range_configs"]
                        if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            item["source"] = "sse"

        def wrong_exchange(documents):
            item = next(item for item in documents["source"]["range_configs"]
                        if item["kind"] == "calendar_range" and item["exchange_scope"] == "SH")
            item["exchange_scope"] = "SZ"

        def unauthorized_capability(documents):
            for rule_id in documents["status"]["rules"]["execution_contract"]["rule_ids"]:
                rule = documents["status"]["rules"][rule_id]
                if rule["kind"] == "market_liquidity":
                    rule["parameters"]["required_evidence_capability"] = "unapproved-capability"
                    break

        for mutate in (wrong_source, wrong_exchange, unauthorized_capability):
            with self.subTest(mutate=mutate.__name__), self.assertRaises(ValueError):
                self._load(mutate)

    def test_market_calendar_and_bootstrap_identities_cannot_be_mixed(self):
        def context_and_bootstrap(documents):
            descriptors = documents["scoring"]["descriptors"]
            context = next(item for item in descriptors
                           if item["context_kind"] == "trading_calendar" and not item["bootstrap_calendar"])
            bootstrap = {item["fixed_exchange"]: item for item in descriptors
                         if item["context_kind"] == "trading_calendar" and item["bootstrap_calendar"]}
            return context, bootstrap

        def c_as_bx(documents):
            context, _ = context_and_bootstrap(documents)
            context_id = hashlib.sha256(canonical(context)).hexdigest()
            calendar = next(item for item in documents["source"]["range_configs"]
                            if item["kind"] == "calendar_range" and item["exchange_scope"] == "SH")
            market = next(item for item in documents["source"]["range_configs"]
                          if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            calendar["anchor_descriptor_id"] = context_id
            calendar["calendar_descriptor_id"] = context_id
            market["calendar_descriptor_id"] = context_id

        def bx_as_c(documents):
            _, bootstrap = context_and_bootstrap(documents)
            bootstrap_entry = bootstrap["SH"]
            bootstrap_id = hashlib.sha256(canonical(bootstrap_entry)).hexdigest()
            for rule_id in documents["status"]["rules"]["execution_contract"]["rule_ids"]:
                rule = documents["status"]["rules"][rule_id]
                if rule["kind"] == "market_liquidity":
                    selector = rule["inputs"]["calendar"]
                    selector["descriptor_id"] = bootstrap_id
                    selector["scope_key"] = bootstrap_entry["scope_key"]
                    break

        def sh_uses_sz_bx(documents):
            _, bootstrap = context_and_bootstrap(documents)
            sz_id = hashlib.sha256(canonical(bootstrap["SZ"])).hexdigest()
            market = next(item for item in documents["source"]["range_configs"]
                          if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            market["calendar_descriptor_id"] = sz_id

        def same_text_wrong_descriptor(documents):
            item = next(item for item in documents["source"]["range_configs"]
                        if item["kind"] == "market_range" and item["exchange_scope"] == "SH")
            item["calendar_anchor_selector"]["selector"]["descriptor_id"] = "f" * 64

        for mutate in (c_as_bx, bx_as_c, sh_uses_sz_bx, same_text_wrong_descriptor):
            with self.subTest(mutate=mutate.__name__), self.assertRaises(ValueError):
                self._load(mutate)

    def test_wrong_root_and_mutated_returned_binding_fail_current_validation(self):
        from ashare_pipeline.formal_range_contract import load_policy_range_bindings

        bindings, _, _, _, _, *_ = self._load()
        binding = bindings.for_rule("bank_no_effective_trade_20d", "SH")
        object.__setattr__(binding.market_config, "dataset", "unsigned-dataset")
        with self.assertRaises(ValueError):
            binding.require_current()

        _, bundle1, _, scoring1, policy1, *_ = self._load()

        def changed_root(documents):
            documents["source"]["range_configs"][0]["endpoint_url"] = (
                "https://www.cninfo.com.cn/fixture/changed-range.json"
            )

        _, bundle2, _, scoring2, _, *_ = self._load(changed_root)
        with self.assertRaises(ValueError):
            load_policy_range_bindings(
                bundle2, scoring_registry=scoring2, policy_registry=policy1
            )
        # The original genuine trio remains valid; this guards against a shared global seal.
        load_policy_range_bindings(
            bundle1, scoring_registry=scoring1, policy_registry=policy1
        ).for_rule("bank_no_effective_trade_20d", "SH").require_current()


if __name__ == "__main__":
    unittest.main()
