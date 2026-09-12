import copy
from contextlib import closing
import hashlib
import json
import sqlite3
import unittest
from decimal import Decimal, localcontext

from ashare_pipeline.formal_policy_values import (
    PolicyIntegrityError,
    PolicyPreconditionError,
    PolicyValue,
    bridge_v6,
    canonical_bytes,
    decimal_context,
    digest,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def value_wire(**changes):
    wire = {
        "state": "value",
        "value": "4.2",
        "value_type": "decimal",
        "unit": "ratio",
        "evidence_hashes": [HASH_B, HASH_A, HASH_B],
        "pending": [],
    }
    wire.update(changes)
    return wire


def pending_wire(**changes):
    wire = {
        "origin": "runtime",
        "code": "financial_input_missing",
        "rule_id": None,
        "evidence_hashes": [HASH_B, HASH_A, HASH_B],
    }
    wire.update(changes)
    return wire


class DecimalBridgeTests(unittest.TestCase):
    def test_bridge_preserves_v6_float_not_original_decimal(self):
        value = 0.1 + 0.2
        self.assertEqual(bridge_v6(value), Decimal(str(value)))
        self.assertNotEqual(bridge_v6(value), Decimal("0.3"))
        huge_integer = 10 ** 1000
        self.assertEqual(bridge_v6(huge_integer), Decimal(str(huge_integer)))
        with localcontext() as ambient:
            ambient.prec = 2
            with localcontext(decimal_context()):
                self.assertEqual(Decimal("4") + Decimal("0.2"), Decimal("4.2"))
        for bad in (True, float("nan"), float("inf")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bridge_v6(bad)

    def test_decimal_wire_is_fixed_minimal_and_independent_of_ambient_precision(self):
        valid = ("0", "12", "-12", "0.00000000000000000001", "100000000000000000000")
        with localcontext() as ambient:
            ambient.prec = 2
            for text in valid:
                with self.subTest(text=text):
                    item = PolicyValue.from_dict(value_wire(value=text))
                    self.assertEqual(item.value, Decimal(text))
                    self.assertEqual(item.to_dict()["value"], text)

        invalid = (
            "-0", "-0.0", "0.0", "1.0", "1.20", "01", "+1", ".1", "1.",
            "1e2", "1E+2", "NaN", "Infinity", "-Infinity", " 1", "1 ", 1,
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                PolicyValue.from_dict(value_wire(value=value))

    def test_canonical_helpers_are_deterministic_and_reject_nonfinite_json(self):
        wire = {"z": [2, 1], "text": "证据", "a": True}
        expected = b'{"a":true,"text":"\xe8\xaf\x81\xe6\x8d\xae","z":[2,1]}'
        self.assertEqual(canonical_bytes(wire), expected)
        self.assertEqual(digest(wire), hashlib.sha256(expected).hexdigest())
        with self.assertRaises(ValueError):
            canonical_bytes({"value": float("nan")})


class PolicyValueTests(unittest.TestCase):
    def test_scalar_values_use_exact_types_and_normalize_evidence_hashes(self):
        decimal_value = PolicyValue.from_dict(value_wire())
        self.assertEqual(decimal_value.value, Decimal("4.2"))
        self.assertEqual(decimal_value.to_dict()["evidence_hashes"], [HASH_A, HASH_B])

        boolean_value = PolicyValue.from_dict(value_wire(
            value=True, value_type="bool", unit=None, evidence_hashes=[]
        ))
        enum_value = PolicyValue.from_dict(value_wire(
            value="listed", value_type="enum", unit=None, evidence_hashes=[]
        ))
        self.assertIs(boolean_value.value, True)
        self.assertEqual(enum_value.value, "listed")

        invalid = (
            value_wire(value=1, value_type="bool", unit=None),
            value_wire(value=True, value_type="enum", unit=None),
            value_wire(value=" listed", value_type="enum", unit=None),
            value_wire(value="4.2", value_type="wrong"),
            value_wire(value="4.2", unit=None),
            value_wire(value=True, value_type="bool", unit="ratio"),
        )
        for wire in invalid:
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                PolicyValue.from_dict(wire)

    def test_missing_and_domain_conflict_are_typed_records_not_values(self):
        for state, value_type in (
            ("missing", "decimal"),
            ("domain_conflict", "enum"),
            ("missing", "event_record"),
            ("domain_conflict", "calendar_record"),
            ("missing", "market_window"),
        ):
            wire = value_wire(
                state=state,
                value=None,
                value_type=value_type,
                unit="ratio" if value_type == "decimal" else None,
                pending=[pending_wire()],
            )
            with self.subTest(state=state, value_type=value_type):
                item = PolicyValue.from_dict(wire)
                self.assertIsNone(item.value)
                self.assertEqual(item.state, state)
                self.assertEqual(item.to_dict()["pending"][0]["evidence_hashes"], [HASH_A, HASH_B])

        invalid = (
            value_wire(state="missing", value="0", pending=[pending_wire()]),
            value_wire(state="domain_conflict", value=False, value_type="bool", unit=None,
                       pending=[pending_wire()]),
            value_wire(state="missing", value=None, pending=[]),
            value_wire(state="value", pending=[pending_wire()]),
        )
        for wire in invalid:
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                PolicyValue.from_dict(wire)

    def test_nonmissing_compound_records_wait_for_closed_producer_validators(self):
        for value_type in ("event_record", "calendar_record", "market_window"):
            with self.subTest(value_type=value_type), self.assertRaises(ValueError):
                PolicyValue.from_dict(value_wire(
                    value_type=value_type, value={"apparently": "valid"}, unit=None
                ))

    def test_runtime_and_signed_policy_pending_reasons_are_strict(self):
        runtime_codes = (
            "applicability_unresolved", "current_receipt_absent",
            "financial_input_missing", "financial_domain_conflict", "unsupported_unit",
            "invalid_denominator", "visibility_unproven", "state_entry_missing",
            "calendar_coverage_missing", "market_coverage_missing", "market_price_missing",
            "market_domain_conflict", "market_evidence_missing",
        )
        for code in runtime_codes:
            with self.subTest(code=code):
                PolicyValue.from_dict(value_wire(
                    state="missing", value=None, pending=[pending_wire(code=code)]
                ))

        invalid = (
            pending_wire(code="unknown_runtime_reason"),
            pending_wire(rule_id="bank_nonpositive_equity"),
            pending_wire(origin="signed_policy", code="", rule_id="bank_rule"),
            pending_wire(origin="signed_policy", code="bad\nreason", rule_id="bank_rule"),
            pending_wire(origin="signed_policy", code="signed_reason", rule_id=None),
            pending_wire(origin="signed_policy", code="signed_reason", rule_id="bad\nrule"),
            pending_wire(origin="other", code="signed_reason", rule_id="bank_rule"),
            {**pending_wire(), "extra": None},
        )
        for pending in invalid:
            with self.subTest(pending=pending), self.assertRaises(ValueError):
                PolicyValue.from_dict(value_wire(
                    state="missing", value=None, pending=[pending]
                ))

        accepted = PolicyValue.from_dict(value_wire(
            state="missing", value=None,
            pending=[pending_wire(origin="signed_policy", code="signed reason",
                                  rule_id="bank_nonpositive_equity")],
        ))
        self.assertEqual(accepted.to_dict()["pending"][0]["rule_id"], "bank_nonpositive_equity")

    def test_exact_wire_and_hash_shapes_are_required(self):
        invalid = (
            {**value_wire(), "extra": None},
            {key: value for key, value in value_wire().items() if key != "unit"},
            value_wire(state="unknown"),
            value_wire(evidence_hashes=["A" * 64]),
            value_wire(evidence_hashes=["a" * 63]),
            value_wire(evidence_hashes="a" * 64),
            value_wire(pending={}),
        )
        for wire in invalid:
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                PolicyValue.from_dict(wire)

    def test_dto_detaches_input_and_output_containers(self):
        wire = value_wire(
            state="missing", value=None,
            pending=[pending_wire(code="financial_input_missing")],
        )
        original = copy.deepcopy(wire)
        item = PolicyValue.from_dict(wire)
        wire["evidence_hashes"].append("c" * 64)
        wire["pending"][0]["code"] = "market_evidence_missing"
        self.assertEqual(item.to_dict(), PolicyValue.from_dict(original).to_dict())

        exported = item.to_dict()
        exported["evidence_hashes"].append("d" * 64)
        exported["pending"][0]["code"] = "state_entry_missing"
        self.assertEqual(item.to_dict(), PolicyValue.from_dict(original).to_dict())

    def test_terminal_policy_errors_remain_value_errors(self):
        self.assertTrue(issubclass(PolicyPreconditionError, ValueError))
        self.assertTrue(issubclass(PolicyIntegrityError, ValueError))
        self.assertIsNot(PolicyPreconditionError, PolicyIntegrityError)


class PolicyRuntimeFixtureTests(unittest.TestCase):
    def fixture(self, **kwargs):
        from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture

        fixture = PolicyRuntimeFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def test_fixture_builds_one_genuine_signed_policy_runtime_graph(self):
        fixture = self.fixture()
        self.assertNotIsInstance(fixture, unittest.TestCase)
        fixture.policy_registry.require_verified()
        self.assertEqual(fixture.policy_registry.registry_manifest_hash,
                         fixture.bundle.manifest.manifest_hash)
        self.assertEqual(
            {member.security_id for member in fixture.frozen.members},
            {"BJ430001", "SH600000", "SZ000001"},
        )
        for name in (
            "bundle", "scoring", "vocabulary", "provider", "feature_repository",
            "context", "store", "root", "frozen",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(fixture, name))

    def test_fixture_registry_detects_signed_child_mutation(self):
        fixture = self.fixture()
        object.__setattr__(fixture.bundle.blob("event"), "canonical_json", b"{}")
        with self.assertRaises(ValueError):
            fixture.policy_registry.require_verified()

    def test_range_enabled_fixture_integrates_real_signed_range_documents(self):
        fixture = self.fixture(range_enabled=True)
        fixture.policy_registry.require_verified()
        source = json.loads(fixture.bundle.blob("source").canonical_json)
        self.assertEqual(source["schema_version"], "formal-source-registry-v2")
        self.assertEqual(len(source["range_configs"]), 6)

    def test_five_template_mapping_defines_matching_frozen_universe_and_memberships(self):
        templates = {
            "BJ430001": "general_nonfinancial",
            "SH600000": "bank",
            "SH600001": "insurance",
            "SZ000001": "broker",
            "SZ000002": "real_estate",
        }
        fixture = self.fixture(templates=templates)
        fixture.policy_registry.require_verified()
        self.assertEqual(
            {member.security_id for member in fixture.frozen.members}, set(templates)
        )
        self.assertEqual(
            {item["security_id"]: item["template_id"] for item in fixture.industry["memberships"]},
            templates,
        )

    def test_put_policy_financial_requires_explicit_year_and_per_key_units(self):
        fixture = self.fixture()
        sid = "SH600000"
        values = {"fixture.policy.roe": 7.5, "fixture.policy.profit": 80.0}
        units = {"fixture.policy.roe": "ratio", "fixture.policy.profit": "CNY"}
        fixture.put_policy_financial(
            sid, values, fy_end="2024-12-31", units=units, generation="fy2024"
        )
        facts = [fact for fact in fixture.store.list_formal_financial_facts(security_id=sid)
                 if fact.period_end == "2024-12-31"]
        self.assertEqual(
            {(fact.metric_key, fact.value, fact.unit) for fact in facts},
            {("fixture.policy.roe", 7.5, "ratio"),
             ("fixture.policy.profit", 80.0, "CNY")},
        )
        with closing(sqlite3.connect(fixture.db_path)) as connection:
            saved_hashes = [row[0] for row in connection.execute(
                "SELECT input_hash FROM formal_feature_set WHERE security_id=?", (sid,)
            )]
        self.assertEqual(len(saved_hashes), 1)
        saved = fixture.feature_repository._read_authenticated_bundle(
            input_hash=saved_hashes[0], require_complete=False
        )
        self.assertEqual(saved.security_id, sid)
        self.assertTrue(saved.blockers)
        self.assertEqual({item.status for item in saved.values}, {"blocked"})

        invalid = (
            {"fy_end": None, "units": units},
            {"fy_end": "FY2024", "units": units},
            {"fy_end": "2024-12-31", "units": {"fixture.policy.roe": "ratio"}},
            {"fy_end": "2024-12-31", "units": {**units, "extra": "CNY"}},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                fixture.put_policy_financial(
                    sid, values, generation="invalid-" + hashlib.sha256(repr(kwargs).encode()).hexdigest()[:8],
                    **kwargs,
                )

    def test_policy_financial_values_writes_distinct_real_fy_evidence_and_receipt(self):
        fixture = self.fixture()
        sid = "SH600000"
        bundle = fixture.policy_financial_values(
            sid, current_roe=9.0, current_margin=8.0, current_profit=7.0
        )
        facts = fixture.store.list_formal_financial_facts(security_id=sid)
        by_year = {}
        for fact in facts:
            by_year.setdefault(fact.period_end, []).append(fact)
        self.assertEqual({key: len(value) for key, value in by_year.items()}, {
            "2021-12-31": 3,
            "2022-12-31": 3,
            "2023-12-31": 3,
            "2024-12-31": 3,
            "2025-12-31": 7,
        })
        self.assertEqual(
            {(fact.metric_key, fact.unit) for fact in facts},
            {
                ("fixture.policy.current.equity", "CNY"),
                ("fixture.policy.current.roe", "ratio"),
                ("fixture.policy.current.margin", "ratio"),
                ("fixture.policy.current.profit", "CNY"),
                ("fixture.policy.roe", "ratio"),
                ("fixture.policy.margin", "ratio"),
                ("fixture.policy.profit", "CNY"),
            },
        )
        self.assertEqual(len({fact.source_producing_task_id for fact in facts}), 5)
        values = {(fact.metric_key, fact.period_end): fact.value for fact in facts}
        self.assertEqual(values[("fixture.policy.current.roe", "2025-12-31")], 9.0)
        self.assertEqual(values[("fixture.policy.roe", "2025-12-31")], 5.0)
        self.assertEqual(values[("fixture.policy.current.margin", "2025-12-31")], 8.0)
        self.assertEqual(values[("fixture.policy.margin", "2025-12-31")], 5.0)
        self.assertEqual(values[("fixture.policy.current.profit", "2025-12-31")], 7.0)
        self.assertEqual(values[("fixture.policy.profit", "2025-12-31")], 5.0)
        slots = {item.slot_id: item.to_dict()["formula"]
                 for item in fixture.vocabulary.slots_for_template("bank")}
        self.assertEqual(slots["bank.policy.roe"], {
            "op": "fact", "fact_key": "fixture.policy.current.roe", "period_key": "FY2025"
        })
        self.assertEqual(slots["bank.policy.roe_2025"], {
            "op": "fact", "fact_key": "fixture.policy.roe", "period_key": "FY2025"
        })
        self.assertEqual(bundle.security_id, sid)
        authenticated = fixture.feature_repository._read_authenticated_bundle(
            input_hash=bundle.input_hash, require_complete=False
        )
        self.assertEqual(authenticated.canonical_bytes(), bundle.canonical_bytes())


if __name__ == "__main__":
    unittest.main()
