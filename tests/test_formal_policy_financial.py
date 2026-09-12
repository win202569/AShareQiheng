"""Authenticate real policy projections without granting metric eligibility."""

import copy
from decimal import Decimal
import unittest
from unittest.mock import patch

from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
from tests.formal_metric_fixtures import FREEZE
from ashare_pipeline.formal_policy_financial import FormalPolicyFinancialRepository
from ashare_pipeline.formal_feature_repository import FormalFeatureRepository
from ashare_pipeline.formal_metric_batch_guard import FormalMetricCurrentInputProvider
from ashare_pipeline.formal_financial_schema import FormalFactIssue, FormalFinancialFact


def change_roe_formula(documents, *, wrong_year=False, repeated_leaf=False):
    slot = next(s for s in documents["feature"]["slots"] if s["slot_id"] == "bank.policy.roe_2021")
    current = documents["cyclic"]["rules"]["bank_cyclic_top"]["inputs"]["annual_roe"]["observations"][0]["selector"]
    if wrong_year:
        slot["formula"]["period_key"] = "FY2020"
        current["period_keys"] = ["FY2020"]
    else:
        numerator = dict(op="fact", fact_key="fixture.policy.profit", period_key="FY2021")
        slot["formula"] = dict(op="divide", left=numerator,
            right=dict(op="fact", fact_key="fixture.policy.current.equity", period_key="FY2020"))
        if repeated_leaf:
            slot["formula"]["right"] = dict(op="add", left=slot["formula"]["right"],
                right=dict(op="fact", fact_key="fixture.policy.current.equity", period_key="FY2020"))
        current["period_keys"] = ["FY2020", "FY2021"]


class PolicyFinancialTests(unittest.TestCase):
    def fixture(self, **kwargs):
        fixture = PolicyRuntimeFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def select(self, fixture):
        self.assertTrue(callable(getattr(fixture, "financial_selection", None)),
                        "independent authenticated financial selection is missing")
        return fixture.financial_selection("SH600000")

    def test_optional_policy_slot_does_not_relax_metric_gate(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000", current_equity=-1.0)
        selected = self.select(fixture)
        self.assertTrue(any(v.state == "value" and v.value == Decimal("-1")
                            for v in selected.values.values()))
        with self.assertRaises(ValueError):
            fixture.feature_repository.select_current_verified_metric_feature_state(
                "SH600000", FREEZE, template_id="bank",
                registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
                required_feature_keys=("bank.policy.equity",))

    def test_five_annual_records_bind_real_fact_paths_and_bridge(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        self.assertEqual(len(selected.annual), 3)
        for records in selected.annual.values():
            self.assertEqual(tuple(r["fy_end"] for r in records),
                             tuple(f"{y}-12-31" for y in range(2021, 2026)))
            self.assertEqual(tuple(r["value"].value for r in records),
                             tuple(Decimal(v) for v in (1, 2, 3, 4, 5)))
            for record in records:
                self.assertEqual(record["bridge_version"], "v6_feature_decimal_bridge_v1")
                self.assertEqual(len(record["facts"]), 1)
                leaf = record["facts"][0]
                self.assertEqual(leaf["ast_path"], "formula")
                self.assertEqual(leaf["period_end"], record["fy_end"])
                self.assertTrue(leaf["formal_fact_id"])
                self.assertTrue(leaf["accounting_basis"])
        selected.recheck()

    def test_receipt_absence_is_bound_and_appearance_invalidates_selection(self):
        fixture = self.fixture()
        fixture.put_policy_financial("SH600000", {"fixture.policy.current.equity": -1},
            fy_end="2025-12-31", units={"fixture.policy.current.equity": "CNY"}, persist=False)
        selected = self.select(fixture)
        self.assertTrue(selected.values)
        for value in selected.values.values():
            self.assertEqual(value.state, "missing")
            self.assertEqual(value.to_dict()["pending"][0]["code"], "current_receipt_absent")
        fixture.persist_features("SH600000")
        with self.assertRaises(ValueError):
            selected.recheck()

    def test_receipt_tamper_is_integrity_failure(self):
        fixture = self.fixture()
        bundle = fixture.policy_financial_values("SH600000")
        self.select(fixture)
        fixture.sql("UPDATE formal_feature_set SET bundle_hash=? WHERE input_hash=?",
                    ("0" * 64, bundle.input_hash))
        with self.assertRaises(ValueError):
            fixture.financial_selection("SH600000")

    def test_missing_fy2021_keeps_target_and_pending(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000")
        fixture.sql("DELETE FROM formal_financial_fact WHERE security_id=? AND period_end=?",
                    ("SH600000", "2021-12-31"))
        fixture.publish_current("SH600000")
        fixture.persist_features("SH600000")
        selected = self.select(fixture)
        for records in selected.annual.values():
            self.assertEqual(records[0]["fy_end"], "2021-12-31")
            self.assertEqual(records[0]["value"].state, "missing")
            self.assertIsNone(records[0]["value"].value)
            self.assertEqual(records[1]["value"].value, Decimal("2"))

    def test_selection_cannot_be_forged_copied_or_shadowed(self):
        fixture = self.fixture()
        selected = self.select(fixture)
        for copier in (copy.copy, copy.deepcopy):
            with self.assertRaises(TypeError):
                copier(selected)
        with self.assertRaises(TypeError):
            type(selected)()
        with self.assertRaises(ValueError):
            object.__new__(type(selected)).recheck()
        with self.assertRaises((AttributeError, TypeError)):
            selected.recheck = lambda: None

    def test_provider_generation_change_invalidates_even_equal_values(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        fixture.set_generation("SH600000", "new-generation")
        with self.assertRaises(ValueError):
            selected.recheck()

    def industry(self, fixture):
        fixture.put_industry("SH600000")
        universe = fixture.policy_context_repository.load_universe(fixture.frozen.frozen_input_hash,
            scoring_registry=fixture.scoring)
        return fixture.policy_context_repository.resolve_industries(universe)

    def test_unpublished_complete_provider_fails(self):
        fixture = self.fixture()
        provider = FormalMetricCurrentInputProvider(fixture.store)
        feature = FormalFeatureRepository(fixture.store, fixture.files,
            registry_signature_verifier=fixture.verifier, current_input_provider=provider)
        repository = FormalPolicyFinancialRepository(feature, current_input_provider=provider)
        industry = self.industry(fixture)
        with self.assertRaises(ValueError):
            repository.select("SH600000", FREEZE, template_id="bank",
                policy_registry=fixture.policy_registry, industry_batch=industry)

    def test_financial_repository_requires_explicit_matching_owned_provider(self):
        fixture = self.fixture()
        for provider in (None, object(), FormalMetricCurrentInputProvider(fixture.store)):
            with self.subTest(provider=type(provider).__name__), self.assertRaises(ValueError):
                FormalPolicyFinancialRepository(fixture.feature_repository, current_input_provider=provider)

    def test_noncyclic_needs_only_equity_and_does_not_require_annual_history(self):
        fixture = self.fixture(cyclic=False)
        fixture.put_policy_financial("SH600000", {"fixture.policy.current.equity": -1},
            fy_end="2025-12-31", units={"fixture.policy.current.equity": "CNY"})
        selected = self.select(fixture)
        self.assertEqual(selected.lineage["applicability"], "not_applicable")
        self.assertEqual(len(selected.annual), 0)
        self.assertEqual([v.value for v in selected.values.values()], [Decimal("-1")])

    def test_unresolved_industry_is_pending_not_noncyclic(self):
        fixture = self.fixture(cyclic=False)
        universe = fixture.policy_context_repository.load_universe(fixture.frozen.frozen_input_hash,
            scoring_registry=fixture.scoring)
        industry = fixture.policy_context_repository.resolve_industries(universe)
        selected = fixture.policy_financial_repository.select("SH600000", FREEZE, template_id="bank",
            policy_registry=fixture.policy_registry, industry_batch=industry)
        self.assertEqual(selected.lineage["applicability"], "applicability_unresolved")

    def test_legitimate_opening_equity_and_repeated_ast_occurrences(self):
        fixture = self.fixture(mutate=lambda docs: change_roe_formula(docs, repeated_leaf=True))
        fixture.put_policy_financial("SH600000", {"fixture.policy.current.equity": 2},
            fy_end="2020-12-31", units={"fixture.policy.current.equity": "CNY"}, persist=False)
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        record = next(records[0] for records in selected.annual.values() if len(records[0]["facts"]) == 3)
        self.assertEqual(record["value"].value, Decimal("0.25"))
        self.assertEqual(tuple(f["ast_path"] for f in record["facts"]),
            ("formula.left", "formula.right.left", "formula.right.right"))
        self.assertEqual(tuple(f["period_end"] for f in record["facts"]),
            ("2021-12-31", "2020-12-31", "2020-12-31"))

    def test_wrong_year_ast_cannot_borrow_observation_label(self):
        fixture = self.fixture(mutate=lambda docs: change_roe_formula(docs, wrong_year=True))
        fixture.put_policy_financial("SH600000", {"fixture.policy.roe": 99},
            fy_end="2020-12-31", units={"fixture.policy.roe": "ratio"}, persist=False)
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        first = [records[0] for records in selected.annual.values()]
        self.assertEqual(sum(r["value"].state == "domain_conflict" for r in first), 1)
        self.assertFalse(any(r["value"].value == Decimal("99") for r in first))

    def test_duplicate_fy_observation_is_rejected_before_read(self):
        def mutate(documents):
            records = documents["cyclic"]["rules"]["bank_cyclic_top"]["inputs"]["annual_roe"]["observations"]
            records[1]["fy_end"] = "2021-12-31"
        with self.assertRaises(ValueError):
            self.fixture(mutate=mutate)

    def test_zero_denominator_is_typed_pending(self):
        fixture = self.fixture(mutate=change_roe_formula)
        fixture.put_policy_financial("SH600000", {"fixture.policy.current.equity": 0},
            fy_end="2020-12-31", units={"fixture.policy.current.equity": "CNY"}, persist=False)
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        pending = [r[0]["value"].to_dict()["pending"] for r in selected.annual.values()]
        self.assertTrue(any(p and p[0]["code"] == "invalid_denominator" for p in pending))

    def test_full_issue_snapshot_blocks_values_and_recheck(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        fixture.issues["SH600000"] = (FormalFactIssue("required_source_field_missing", None,
            "fixture.policy.roe", {"period": "FY2021"}),)
        fixture.publish_current("SH600000")
        fixture.persist_features("SH600000")
        with self.assertRaises(ValueError):
            selected.recheck()
        current = fixture.financial_selection("SH600000")
        self.assertTrue(all(v.state == "domain_conflict" for v in current.values.values()))

    def test_mixed_accounting_basis_cannot_form_roe(self):
        fixture = self.fixture(mutate=change_roe_formula)
        fixture.put_policy_financial("SH600000", {"fixture.policy.current.equity": 2},
            fy_end="2020-12-31", units={"fixture.policy.current.equity": "CNY"}, persist=False)
        facts = fixture.store.list_formal_financial_facts(security_id="SH600000")
        fixture.sql("DELETE FROM formal_financial_fact WHERE security_id=?", ("SH600000",))
        changed = []
        for fact in facts:
            wire = fact.to_dict()
            wire.pop("id")
            wire["accounting_basis"] = "parent"
            changed.append(FormalFinancialFact.create(**wire))
        fixture.store.insert_formal_financial_facts(tuple(changed))
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        self.assertTrue(any(records[0]["value"].state == "domain_conflict" for records in selected.annual.values()))

    def test_cross_security_template_and_root_fail(self):
        fixture = self.fixture()
        industry = self.industry(fixture)
        for sid, template in (("SH600099", "bank"), ("SH600000", "insurance")):
            with self.subTest(sid=sid, template=template), self.assertRaises(ValueError):
                fixture.policy_financial_repository.select(sid, FREEZE, template_id=template,
                    policy_registry=fixture.policy_registry, industry_batch=industry)
        other = self.fixture(cyclic=False)
        with self.assertRaises(ValueError):
            fixture.policy_financial_repository.select("SH600000", FREEZE, template_id="bank",
                policy_registry=other.policy_registry, industry_batch=industry)

    def test_provider_alias_and_method_replacement_before_first_select_fail(self):
        from ashare_pipeline import formal_metric_batch_guard as module
        fixture = self.fixture()
        industry = self.industry(fixture)
        class FakeProvider:
            pass
        for owner, name, substitute in ((module, "FormalMetricCurrentInputProvider", FakeProvider),
                (FormalMetricCurrentInputProvider, "resolve_current_inputs", lambda *_a, **_k: None)):
            with self.subTest(name=name), patch.object(owner, name, substitute), self.assertRaises(ValueError):
                fixture.policy_financial_repository.select("SH600000", FREEZE, template_id="bank",
                    policy_registry=fixture.policy_registry, industry_batch=industry)

    def test_source_correction_invalidates_equal_value_selection(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        fixture.put_policy_financial("SH600000", {"fixture.policy.current.equity": 1},
            fy_end="2025-12-31", units={"fixture.policy.current.equity": "CNY"}, generation="correction")
        with self.assertRaises(ValueError):
            selected.recheck()

    def test_same_leading_fact_versions_fail_integrity(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000")
        fact = next(f for f in fixture.store.list_formal_financial_facts(security_id="SH600000")
            if f.metric_key == "fixture.policy.roe" and f.period_end == "2021-12-31")
        wire = fact.to_dict()
        wire.pop("id")
        wire["value"] = 99.0
        fixture.store.insert_formal_financial_facts((FormalFinancialFact.create(**wire),))
        fixture.publish_current("SH600000")
        fixture.persist_features("SH600000")
        with self.assertRaises(ValueError):
            self.select(fixture)

    def test_duplicate_actual_fy_fact_basis_is_domain_conflict(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000")
        fact = next(f for f in fixture.store.list_formal_financial_facts(security_id="SH600000")
            if f.metric_key == "fixture.policy.roe" and f.period_end == "2021-12-31")
        wire = fact.to_dict()
        wire.pop("id")
        wire["accounting_basis"] = "parent"
        fixture.store.insert_formal_financial_facts((FormalFinancialFact.create(**wire),))
        fixture.publish_current("SH600000")
        fixture.persist_features("SH600000")
        selected = self.select(fixture)
        self.assertEqual(sum(records[0]["value"].state == "domain_conflict" for records in selected.annual.values()), 1)

    def test_unsigned_unit_conversion_is_not_performed(self):
        def mutate(documents):
            slot = next(s for s in documents["feature"]["slots"] if s["slot_id"] == "bank.policy.equity")
            slot["unit"] = "ratio"
            documents["redline"]["rules"]["bank_nonpositive_equity"]["inputs"]["value"]["expected_unit"] = "ratio"
        fixture = self.fixture(cyclic=False, mutate=mutate)
        fixture.put_policy_financial("SH600000", {"fixture.policy.current.equity": -1},
            fy_end="2025-12-31", units={"fixture.policy.current.equity": "CNY"})
        value = next(iter(self.select(fixture).values.values()))
        self.assertEqual(value.state, "missing")
        self.assertEqual(value.to_dict()["pending"][0]["code"], "unsupported_unit")

    def test_fact_publication_mismatch_is_not_receipt_absence(self):
        fixture = self.fixture()
        fixture.policy_financial_values("SH600000")
        selected = self.select(fixture)
        fixture.sql("UPDATE formal_financial_fact SET published_at_utc=? WHERE security_id=?",
                    ("2026-09-01T00:00:00+00:00", "SH600000"))
        with self.assertRaises(ValueError):
            selected.recheck()

    def test_feature_state_rejects_arbitrary_slots_and_shadowed_read_paths(self):
        fixture = self.fixture()
        request = dict(template_id="bank", registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
            policy_registry=fixture.policy_registry, rule_ids=("bank_nonpositive_equity",))
        state = fixture.feature_repository.select_current_verified_policy_feature_state("SH600000", FREEZE, **request)
        with self.assertRaises(TypeError):
            copy.copy(state)
        with self.assertRaises(TypeError):
            copy.deepcopy(state)
        with self.assertRaises(ValueError):
            object.__new__(type(state)).recheck()
        with self.assertRaises(ValueError):
            fixture.feature_repository.select_current_verified_policy_feature_state("SH600000", FREEZE,
                **dict(request, rule_ids=("bank.policy.equity",)))
        with patch.object(fixture.feature_repository, "_read_authenticated_bundle", lambda **_: None):
            with self.assertRaises(ValueError):
                state.recheck()

    def test_state_and_selection_class_lookup_cannot_be_replaced(self):
        fixture = self.fixture()
        selected = self.select(fixture)
        state = fixture.feature_repository.select_current_verified_policy_feature_state("SH600000", FREEZE,
            template_id="bank", registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
            policy_registry=fixture.policy_registry, rule_ids=("bank_nonpositive_equity",))
        for item in (state, selected):
            cls = type(item)
            original = cls.__getattribute__
            try:
                with self.assertRaises(TypeError):
                    cls.__getattribute__ = lambda self, name: {}
            finally:
                if cls.__getattribute__ is not original:
                    cls.__getattribute__ = original
            with patch.object(cls, "values", property(lambda _: {}), create=True):
                with self.assertRaises(ValueError):
                    item.values


if __name__ == "__main__":
    unittest.main()
