"""Point-in-time financial derivation regression and hostile-boundary tests."""
import hashlib
import itertools
import math
import unittest
from collections import UserDict

from ashare_pipeline.formal_financial_schema import FormalFinancialFact, FormalFactIssue
from ashare_pipeline.formal_feature_contract import FormulaNode, SignedFormalFeatureRegistry
from ashare_pipeline.formal_registry_manifest import FormalRegistryManifest
from ashare_pipeline.formal_financial_features import (
    FormalQuarterFact, select_visible_formal_facts, derive_comparable_quarters,
    require_formal_history, evaluate_formula, build_formal_feature_bundle,
)
from tests.test_formal_feature_contract import (
    formal_fact, canonical_bytes, feature_registry_bytes, registry_manifest,
    load_registry, slot_wire, TEMPLATES,
)

CUTOFF = "2026-08-31T07:00:00+00:00"
WINDOW = ("2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2")
ANNUALS = tuple(f"{year}-12-31" for year in range(2022, 2026))


def fact(kind="FY", value=100.0, year=2025, **changes):
    end = {"Q1": "03-31", "H1": "06-30", "Q3": "09-30", "FY": "12-31", "OTHER": "05-31"}[kind]
    values = dict(period_start=None if kind == "OTHER" else f"{year}-01-01", period_end=f"{year}-{end}", period_kind=kind, value=value)
    values.update(changes)
    return formal_fact(**values)


def leaf(metric="revenue", period="FY2025"):
    return FormulaNode(op="fact", fact_key=metric, period_key=period)


def bundle(facts=(), *, purpose="official", slots=None, issues=(), **changes):
    if slots is None:
        slots = [slot_wire("general_nonfinancial", unit="CNY", formula=leaf().to_dict())]
    all_slots = slots + [slot_wire(template) for template in TEMPLATES if template != "general_nonfinancial"]
    raw = feature_registry_bytes(slots=sorted(all_slots, key=lambda slot: slot["slot_id"]))
    root = registry_manifest(raw, purpose=purpose)
    values = dict(security_id="SH600001", as_of_utc=CUTOFF, template_id="general_nonfinancial", facts=facts, issues=issues, registry=load_registry(raw, root), registry_manifest=root)
    values.update(changes)
    return build_formal_feature_bundle(**values)


class SelectionTests(unittest.TestCase):
    def test_generator_mutation_rejected_and_selection_detached(self):
        original = fact()
        result = select_visible_formal_facts([original], CUTOFF)
        self.assertIsNot(original, result.facts[0])
        object.__setattr__(original, "value", 999.0)
        self.assertEqual(result.facts[0].to_dict()["value"], 100.0)
        original = fact()
        def hostile():
            yield original
            object.__setattr__(original, "value", 999.0)
            yield fact(metric_key="profit")
        with self.assertRaises(ValueError):
            select_visible_formal_facts(hostile(), CUTOFF)

    def test_date_only_effective_cutoff_and_future_conflict_exclusion(self):
        delayed = fact(published_precision="date_only", published_at_utc="2026-08-31T00:00:00+00:00", effective_at_utc="2026-09-01T07:00:00+00:00", effective_time_evidence_hash="c" * 64, source_updated_at_utc=None)
        self.assertEqual(select_visible_formal_facts([delayed], CUTOFF).facts, ())
        old = fact()
        future_parser = fact(parser_version="future", source_updated_at_utc="2026-09-01T00:00:00+00:00")
        result = select_visible_formal_facts([old, future_parser], CUTOFF)
        self.assertEqual(result.facts, (old,))
        self.assertEqual(result.blockers, ())

    def test_tied_lineage_not_only_fact_id_and_low_level_forgery(self):
        original = fact()
        later_created = fact(created_at_utc="2026-09-05T00:00:00+00:00")
        self.assertEqual(original.id, later_created.id)
        self.assertIn("fact_selection_tie_conflict", select_visible_formal_facts([original, later_created], CUTOFF).blockers)
        forged = object.__new__(FormalFinancialFact)
        for key, value in original.to_dict().items():
            object.__setattr__(forged, key, value)
        for consumer in (lambda: select_visible_formal_facts([forged], CUTOFF), lambda: derive_comparable_quarters([forged]), lambda: evaluate_formula(leaf(), {("revenue", "FY2025"): forged}), lambda: bundle([forged])):
            with self.assertRaises(ValueError):
                consumer()

    def test_cutoff_revision_capture_and_equality(self):
        at = fact(published_at_utc=CUTOFF, effective_at_utc=CUTOFF, source_updated_at_utc=CUTOFF)
        future = fact(value=999.0, source_updated_at_utc="2026-08-31T07:00:01+00:00")
        self.assertEqual(select_visible_formal_facts([future, at], CUTOFF).facts, (at,))
        self.assertGreater(at.captured_at_utc, CUTOFF)
        later = fact(published_at_utc="2026-08-31T07:00:01+00:00", effective_at_utc="2026-08-31T07:00:01+00:00", source_updated_at_utc=None)
        self.assertEqual(select_visible_formal_facts([later], CUTOFF).facts, ())

    def test_every_version_level_and_permutations(self):
        base = fact(source_updated_at_utc=None)
        updated = fact(source_updated_at_utc="2026-03-20T08:30:00+00:00")
        captured = fact(captured_at_utc="2026-09-05T00:00:00+00:00")
        hashed = fact(captured_at_utc="2026-09-05T00:00:00+00:00", source_content_sha256="0" * 64)
        published = fact(published_at_utc="2026-03-21T08:00:00+00:00", effective_at_utc="2026-03-21T08:00:00+00:00", source_updated_at_utc=None)
        for candidates, winner in (([base, updated], updated), ([updated, captured], captured), ([captured, hashed], hashed), ([hashed, published], published)):
            for order in itertools.permutations(candidates):
                self.assertEqual(select_visible_formal_facts(order, CUTOFF).facts, (winner,))

    def test_mapping_conflicts_tie_and_duplicate(self):
        original = fact()
        for field in ("parser_id", "parser_version", "mapping_version"):
            result = select_visible_formal_facts([original, fact(**{field: "other"})], CUTOFF)
            self.assertEqual(result.facts, ())
            self.assertIn("fact_mapping_version_conflict", result.blockers)
        result = select_visible_formal_facts([original, fact(value=101.0), fact(metric_key="profit")], CUTOFF)
        self.assertEqual(len(result.facts), 1)
        self.assertIn("fact_selection_tie_conflict", result.blockers)
        self.assertEqual(select_visible_formal_facts([original, original], CUTOFF).facts, (original,))

    def test_untrusted_inputs_and_noncanonical_time(self):
        for value in (object(), {}, 1):
            with self.assertRaises(ValueError):
                select_visible_formal_facts([value], CUTOFF)
        mutated = fact()
        object.__setattr__(mutated, "value", 1.0)
        with self.assertRaises(ValueError):
            select_visible_formal_facts([mutated], CUTOFF)
        for cutoff in (CUTOFF.replace("+00:00", "Z"), "2026-08-31T15:00:00+08:00", 1):
            with self.assertRaises(ValueError):
                select_visible_formal_facts([], cutoff)


class QuarterTests(unittest.TestCase):
    def test_missing_h1_preserves_q4_and_year_unit_isolation(self):
        result = derive_comparable_quarters([fact("Q1", 10), fact("Q3", 45), fact("FY", 70)])
        self.assertEqual([(q.quarter_key, q.value) for q in result.facts], [("2025Q1", 10), ("2025Q4", 25)])
        self.assertIn("quarter_missing_prerequisite", result.blockers)
        units = derive_comparable_quarters([fact("Q1", unit="CNY"), fact("H1", unit="shares")])
        self.assertEqual(len(units.facts), 1)
        self.assertIn("quarter_missing_prerequisite", units.blockers)
        years = derive_comparable_quarters([fact("Q1", year=2024), fact("H1", year=2025)])
        self.assertEqual([q.quarter_key for q in years.facts], ["2024Q1"])

    def test_quarter_identity_changes_and_order_is_stable(self):
        raw = [fact("Q1", 10), fact("H1", 30)]
        baseline = derive_comparable_quarters(raw)
        self.assertEqual([q.to_dict() for q in baseline.facts], [q.to_dict() for q in derive_comparable_quarters(raw[::-1]).facts])
        revised = derive_comparable_quarters([raw[0], fact("H1", 30, source_refresh_generation="revision")])
        self.assertNotEqual(baseline.facts[1].id, revised.facts[1].id)
        cash = derive_comparable_quarters([fact("Q1", statement="cash_flow")])
        self.assertEqual(cash.facts[0].statement, "cash_flow")

    def test_quarter_zero_and_exact_wire_boundaries(self):
        q = derive_comparable_quarters([fact("Q1", 0)]).facts[0]
        wire = q.to_dict()
        for change in ({"value": -0.0}, {"value": False}, {"nature": []}, {"unit": []}, {"component_fact_ids": tuple(wire["component_fact_ids"])}, {"evidence": [{**wire["evidence"][0], "mapping_version": "different"}]}):
            with self.assertRaises(ValueError):
                FormalQuarterFact.from_dict({**wire, **change})
        self.assertEqual(math.copysign(1, q.value), 1)
        cycle = {}
        cycle["nested"] = cycle
        with self.assertRaises(ValueError):
            FormalQuarterFact.from_dict(cycle)

    def test_duration_instant_and_full_evidence(self):
        raw = [fact(kind, value) for kind, value in zip(("Q1", "H1", "Q3", "FY"), (10, 30, 45, 70))]
        result = derive_comparable_quarters(raw)
        self.assertEqual([q.value for q in result.facts], [10, 20, 15, 25])
        self.assertEqual([q.quarter_key for q in result.facts], [f"2025Q{i}" for i in range(1, 5)])
        self.assertEqual(result.facts[1].component_fact_ids, tuple(sorted([raw[0].id, raw[1].id])))
        self.assertEqual(tuple(e.formal_fact_id for e in result.facts[1].evidence), result.facts[1].component_fact_ids)
        instant = [fact(kind, value, statement="balance", nature="instant", period_start=None) for kind, value in zip(("Q1", "H1", "Q3", "FY"), (10, 30, 45, 70))]
        self.assertEqual([q.value for q in derive_comparable_quarters(instant).facts], [10, 30, 45, 70])

    def test_mismatches_duplicate_other_missing_and_negative(self):
        for field, reason in (("accounting_basis", "quarter_accounting_basis_mismatch"), ("parser_id", "quarter_parser_version_mismatch"), ("parser_version", "quarter_parser_version_mismatch"), ("mapping_version", "quarter_mapping_version_mismatch")):
            changed = "separate" if field == "accounting_basis" else "different"
            result = derive_comparable_quarters([fact("Q1"), fact("H1", **{field: changed})])
            self.assertEqual(result.facts, ())
            self.assertIn(reason, result.blockers)
        for raw, reason in (([fact("Q1"), fact("Q1")], "quarter_duplicate_period"), ([fact("OTHER")], "quarter_invalid_period"), ([fact("H1")], "quarter_missing_prerequisite")):
            result = derive_comparable_quarters(raw)
            self.assertEqual(result.facts, ())
            self.assertIn(reason, result.blockers)
        result = derive_comparable_quarters([fact("Q1", 30), fact("H1", 10)])
        self.assertEqual(result.facts[1].value, -20.0)
        huge = derive_comparable_quarters([fact("Q1", -1e308), fact("H1", 1e308)])
        self.assertIn("quarter_nonfinite_derivation", huge.blockers)

    def test_roundtrip_identity_and_forgery(self):
        q = derive_comparable_quarters([fact("Q1")]).facts[0]
        wire = q.to_dict()
        self.assertEqual(FormalQuarterFact.from_dict(wire).to_dict(), wire)
        identity = {k: v for k, v in wire.items() if k not in {"id", "evidence"}}
        identity["schema_version"] = "formal-quarter-fact-v1"
        self.assertEqual(q.id, hashlib.sha256(canonical_bytes(identity)).hexdigest())
        with self.assertRaises(TypeError):
            FormalQuarterFact()
        forged = object.__new__(FormalQuarterFact)
        for key in wire:
            object.__setattr__(forged, key, getattr(q, key))
        with self.assertRaises(ValueError):
            forged.to_dict()
        for changed in ({"value": 100}, {"id": "0" * 64}, {"quarter_key": "Q1"}, {"evidence": []}):
            with self.assertRaises(ValueError):
                FormalQuarterFact.from_dict({**wire, **changed})
        object.__setattr__(q, "value", 101.0)
        with self.assertRaises(ValueError):
            q.to_dict()


class HistoryTests(unittest.TestCase):
    def test_shanghai_date_boundary_and_extra_history(self):
        result = require_formal_history(("2020-12-31", "2021-12-31") + ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=False)
        self.assertEqual(result.annual_endpoints, ANNUALS)
        at_quarter_end = require_formal_history(ANNUALS, comparable_quarter_keys=WINDOW[1:] + ("2026Q3",), as_of_utc="2026-09-29T16:00:00+00:00", cyclic=False)
        self.assertTrue(at_quarter_end.eligible)
        for quarters in (WINDOW + WINDOW[-1:], WINDOW[::-1], ("2024Q0",) + WINDOW[1:], (1,) + WINDOW[1:]):
            self.assertFalse(require_formal_history(ANNUALS, comparable_quarter_keys=quarters, as_of_utc=CUTOFF, cyclic=False).eligible)

    def test_current_four_and_five_year_windows(self):
        self.assertTrue(require_formal_history(ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=False).eligible)
        self.assertFalse(require_formal_history(ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=True).eligible)
        self.assertTrue(require_formal_history(("2021-12-31",) + ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=True).eligible)
        for annuals, quarters in ((ANNUALS[::-1], WINDOW), (ANNUALS + ANNUALS[-1:], WINDOW), (ANNUALS, WINDOW[:-1]), (ANNUALS, ("2024Q2",) + WINDOW[:-1]), (ANNUALS + ("2026-12-31",), WINDOW), (("invalid",), WINDOW)):
            result = require_formal_history(annuals, comparable_quarter_keys=quarters, as_of_utc=CUTOFF, cyclic=False)
            self.assertFalse(result.eligible)
            self.assertIn("pending_evidence/history_not_mature", result.blockers)
        with self.assertRaises(ValueError):
            require_formal_history(ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=1)


class FormulaTests(unittest.TestCase):
    def test_economic_units_and_arithmetic_failure(self):
        left, right = leaf("revenue"), leaf("shares")
        mapping = {("revenue", "FY2025"): fact(value=100), ("shares", "FY2025"): fact(metric_key="shares", unit="shares", value=20)}
        result = evaluate_formula(FormulaNode(op="divide", left=left, right=right), mapping)
        self.assertEqual((result.value, result.unit, result.time_reliability), (5.0, "CNY_per_share", 1.0))
        for op in ("add", "subtract", "cagr", "median", "minimum"):
            node = FormulaNode(op=op, items=(left, right)) if op in {"median", "minimum"} else FormulaNode(op=op, left=left, right=right, **({"intervals": 2} if op == "cagr" else {}))
            result = evaluate_formula(node, mapping)
            self.assertEqual(result.missing_reason, "formula_unit_mismatch")
            self.assertEqual((result.value, result.unit, result.evidence, result.time_reliability), (None, None, (), None))
        reverse = evaluate_formula(FormulaNode(op="divide", left=right, right=left), mapping)
        self.assertEqual(reverse.missing_reason, "formula_unit_mismatch")
        huge = {("revenue", "FY2024"): fact(year=2024, value=1e308), ("revenue", "FY2025"): fact(value=1e308)}
        result = evaluate_formula(FormulaNode(op="add", left=leaf(period="FY2024"), right=leaf()), huge)
        self.assertEqual(result.missing_reason, "formula_nonfinite_result")

    def test_cagr_direction_and_negative_endpoints(self):
        node = FormulaNode(op="cagr", left=leaf(period="FY2023"), right=leaf(), intervals=2)
        mapping = {("revenue", "FY2023"): fact(year=2023, value=100), ("revenue", "FY2025"): fact(value=121)}
        self.assertAlmostEqual(evaluate_formula(node, mapping).value, .1)
        for start, end in ((-100, 121), (100, -121), (0, 121), (100, 0)):
            mapping[("revenue", "FY2023")] = fact(year=2023, value=start)
            mapping[("revenue", "FY2025")] = fact(value=end)
            self.assertEqual(evaluate_formula(node, mapping).missing_reason, "formula_nonpositive_cagr")

    def test_quarter_reliability_all_operands_and_malformed_nodes(self):
        date_q1 = fact("Q1", 10, published_precision="date_only", published_at_utc="2026-03-20T00:00:00+00:00", effective_at_utc="2026-03-21T07:00:00+00:00", effective_time_evidence_hash="c" * 64)
        q2 = derive_comparable_quarters([date_q1, fact("H1", 30)]).facts[1]
        result = evaluate_formula(leaf(period="2025Q2"), {("revenue", "2025Q2"): q2})
        self.assertEqual((result.value, result.time_reliability, len(result.evidence)), (20, .8, 2))
        cyclic = FormulaNode(op="add", left=leaf(), right=leaf())
        object.__setattr__(cyclic, "left", cyclic)
        with self.assertRaises(ValueError):
            evaluate_formula(cyclic, {})
        with self.assertRaises(ValueError):
            evaluate_formula({}, {})
        self.assertEqual(evaluate_formula(leaf(period="FY0"), {}).missing_reason, "formula_fact_missing")

    def test_custom_keys_and_mutated_quarters_rejected(self):
        class Text(str):
            pass
        class Pair(tuple):
            pass
        for key in ((Text("revenue"), "FY2025"), Pair(("revenue", "FY2025"))):
            with self.assertRaises(ValueError):
                evaluate_formula(leaf(), {key: fact()})
        q = derive_comparable_quarters([fact("Q1")]).facts[0]
        object.__setattr__(q, "component_fact_ids", ())
        with self.assertRaises(ValueError):
            evaluate_formula(leaf(period="2025Q1"), {("revenue", "2025Q1"): q})

    def test_binary_operations_cagr_and_units(self):
        mapping = {("revenue", "FY2024"): fact(year=2024, value=100), ("revenue", "FY2025"): fact(value=200)}
        left, right = leaf(period="FY2024"), leaf()
        for op, expected in (("add", 300), ("subtract", -100), ("divide", .5), ("cagr", 1.0)):
            node = FormulaNode(op=op, left=left, right=right, **({"intervals": 1} if op == "cagr" else {}))
            result = evaluate_formula(node, mapping)
            self.assertEqual(result.value, expected)
            self.assertEqual(len(result.evidence), 2)
        mapping[("revenue", "FY2025")] = fact(value=0)
        for op in ("divide", "cagr"):
            result = evaluate_formula(FormulaNode(op=op, left=left, right=right, **({"intervals": 1} if op == "cagr" else {})), mapping)
            self.assertIsNone(result.value)
            self.assertEqual(result.evidence, ())

    def test_aggregate_evidence_and_reliability(self):
        date_fact = fact(value=40, published_precision="date_only", published_at_utc="2026-03-20T00:00:00+00:00", effective_at_utc="2026-03-21T07:00:00+00:00", effective_time_evidence_hash="c" * 64)
        mapping = {("revenue", "FY2024"): fact(year=2024, value=10), ("revenue", "FY2025"): date_fact}
        nodes = (leaf(period="FY2024"), leaf())
        for op, value in (("median", 25), ("minimum", 10)):
            result = evaluate_formula(FormulaNode(op=op, items=nodes), mapping)
            self.assertEqual(result.value, value)
            self.assertEqual(result.time_reliability, .8)
            self.assertEqual(len(result.evidence), 2)

    def test_namespace_and_hostile_mapping(self):
        q = derive_comparable_quarters([fact("Q1", 10)]).facts[0]
        self.assertEqual(evaluate_formula(leaf(period="2025Q1"), {("revenue", "2025Q1"): q}).value, 10)
        for mapping in (UserDict(), {("profit", "FY2025"): fact()}, {("revenue", "2025Q1"): fact("Q1")}, {("revenue", "FY2024"): fact(year=2024), ("profit", "FY2025"): fact(metric_key="profit", security_id="SZ000001")}):
            with self.assertRaises(ValueError):
                evaluate_formula(leaf(), mapping)
        missing = evaluate_formula(FormulaNode(op="add", left=leaf(), right=leaf("absent")), {("revenue", "FY2025"): fact()})
        self.assertEqual(missing.missing_reason, "formula_fact_missing")
        self.assertEqual(missing.evidence, ())


class BundleTests(unittest.TestCase):
    def test_issue_iterator_cannot_mutate_facts_or_registry_snapshots(self):
        slots = sorted([slot_wire(template, unit="CNY", formula=leaf().to_dict()) for template in TEMPLATES], key=lambda item: item["slot_id"])
        raw = feature_registry_bytes(slots=slots)
        root = registry_manifest(raw)
        registry = load_registry(raw, root)
        original = fact()
        expected = bundle([original], registry=registry, registry_manifest=root)
        def hostile():
            object.__setattr__(original, "value", 999.0)
            object.__setattr__(root, "manifest_hash", "e" * 64)
            object.__setattr__(registry, "contract_version", "tampered")
            return
            yield
        result = bundle([original], registry=registry, registry_manifest=root, issues=hostile())
        self.assertEqual(result.to_dict(), expected.to_dict())

    def test_official_child_with_test_root_and_unbound_child_blocks(self):
        slots = sorted([slot_wire(template, unit="CNY", formula=leaf().to_dict()) for template in TEMPLATES], key=lambda item: item["slot_id"])
        raw = feature_registry_bytes(slots=slots)
        official = registry_manifest(raw)
        test = registry_manifest(raw, purpose="test")
        registry = load_registry(raw, official)
        self.assertTrue(registry.release_eligible)
        result = bundle([fact()], registry=registry, registry_manifest=test)
        self.assertEqual(result.values[0].status, "blocked")
        self.assertIn("feature_registry_not_release_eligible", result.blockers)
        self.assertEqual(bundle([fact()], registry=load_registry(raw), registry_manifest=official).values[0].status, "blocked")

    def test_ambiguous_metric_fact_is_missing_and_others_survive(self):
        raw = [fact(), fact(statement="cash_flow", value=80), fact(metric_key="profit", value=20)]
        slots = [slot_wire("general_nonfinancial", suffix="a", unit="CNY", formula=leaf().to_dict()), slot_wire("general_nonfinancial", suffix="b", unit="CNY", formula=leaf("profit").to_dict())]
        result = bundle(raw, slots=slots)
        self.assertEqual(result.values[0].missing_reason, "formula_fact_ambiguous")
        self.assertEqual((result.values[1].status, result.values[1].value), ("derived", 20))
        self.assertEqual(result.input_hash, bundle(raw[::-1], slots=slots).input_hash)

    def test_quarter_blocker_propagation_and_slot_unit_binding(self):
        result = bundle([fact("H1")])
        self.assertIn("quarter_missing_prerequisite", result.blockers)
        self.assertEqual(result.values[0].status, "missing")
        result = bundle([fact()], slots=[slot_wire("general_nonfinancial", unit="ratio", formula=leaf().to_dict())])
        self.assertEqual(result.values[0].missing_reason, "formula_unit_mismatch")

    def test_root_registry_and_issue_low_level_forgery(self):
        for target in ("registry", "registry_manifest"):
            forged = object.__new__(SignedFormalFeatureRegistry if target == "registry" else FormalRegistryManifest)
            with self.assertRaises(ValueError):
                bundle(**{target: forged})
        issue = FormalFactIssue("nonnumeric_value", None, None, {})
        object.__setattr__(issue, "code", "unknown_source_field")
        with self.assertRaises(ValueError):
            bundle(issues=[issue])

    def test_derived_required_optional_and_nonrelease(self):
        result = bundle([fact()])
        self.assertEqual(result.values[0].status, "derived")
        self.assertEqual(result.history_endpoints, ("2025-12-31",))
        self.assertNotIn("feature_required_slot_missing", result.blockers)
        for purpose in ("test",):
            result = bundle([fact()], purpose=purpose)
            self.assertEqual(result.values[0].status, "blocked")
            self.assertIn("feature_registry_not_release_eligible", result.blockers)
        self.assertIn("feature_required_slot_missing", bundle().blockers)
        optional = [slot_wire("general_nonfinancial", required=False, unit="CNY", formula=leaf().to_dict())]
        self.assertNotIn("feature_required_slot_missing", bundle(slots=optional).blockers)

    def test_issues_conflicts_and_hash_inputs(self):
        issue = FormalFactIssue("nonnumeric_value", None, None, {})
        result = bundle([fact()], issues=[issue])
        self.assertEqual(result.values[0].status, "blocked")
        self.assertIn("formal_fact_issue_nonnumeric_value", result.blockers)
        with self.assertRaises(ValueError):
            bundle(issues=[FormalFactIssue("arbitrary", None, None, {})])
        a, b = fact(), fact(value=101)
        result = bundle([a, b])
        self.assertEqual(result.values[0].status, "blocked")
        self.assertEqual(result.input_hash, bundle([b, a]).input_hash)
        self.assertNotEqual(result.input_hash, bundle([a]).input_hash)
        self.assertNotEqual(bundle([a]).input_hash, bundle([fact(source_refresh_generation="new")]).input_hash)
        future = fact(source_updated_at_utc="2026-09-01T00:00:00+00:00")
        self.assertEqual(bundle([a]).input_hash, bundle([a, future]).input_hash)

    def test_root_binding_and_foreign_facts(self):
        raw = feature_registry_bytes(template_ids=("general_nonfinancial",))
        with self.assertRaises(ValueError):
            bundle([fact()], registry_manifest=registry_manifest(raw))
        with self.assertRaises(ValueError):
            bundle([fact(security_id="SZ000001")])
        with self.assertRaises(ValueError):
            bundle(registry=object())


if __name__ == "__main__":
    unittest.main()
