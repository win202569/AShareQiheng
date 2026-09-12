"""Real Context state evidence must preserve absence, identity and explicit false."""

import copy
import importlib.util
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_policy_values import PolicyValue, digest
from tests.formal_metric_fixtures import FREEZE
from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
from tests.formal_policy_fixtures import context_selector


SECURITY = dict(is_st=False, is_star_st=False, listing_status="listed",
                forced_delist_risk=False, suspended=False)


class PolicyStateTests(unittest.TestCase):
    def test_value_alias_replacement_before_state_import_cannot_invent_flags(self):
        script = textwrap.dedent('''
            from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
            from ashare_pipeline import formal_policy_values as owner
            fixture = PolicyRuntimeFixture()
            try:
                original = owner.PolicyValue
                class ForgedValue:
                    @classmethod
                    def from_dict(cls, wire):
                        wire = dict(wire)
                        if wire["value_type"] == "bool":
                            wire.update(state="value", value=True, pending=[])
                        return original.from_dict(wire)
                    def to_dict(self):
                        return {}
                owner.PolicyValue = ForgedValue
                from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
                try:
                    selected = fixture.state_selection("SH600000")
                    selected.recheck()
                except ValueError:
                    pass
                else:
                    raise AssertionError("public value alias invented observed flags from absence")
            finally:
                fixture.close()
        ''')
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_value_methods_replaced_before_state_import_are_rejected(self):
        for method in ("from_dict", "to_dict", "__getattribute__"):
            script = textwrap.dedent('''
                import sys
                from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
                from ashare_pipeline import formal_policy_values as owner
                fixture = PolicyRuntimeFixture()
                try:
                    parser, serializer = owner.PolicyValue.from_dict, owner.PolicyValue.to_dict
                    if sys.argv[1] == "from_dict":
                        def replacement(cls, wire):
                            wire = dict(wire)
                            if wire["value_type"] == "bool":
                                wire.update(state="value", value=True, pending=[])
                            return parser(wire)
                        owner.PolicyValue.from_dict = classmethod(replacement)
                    elif sys.argv[1] == "to_dict":
                        def replacement(self):
                            wire = serializer(self)
                            if wire["value_type"] == "bool":
                                wire.update(state="value", value=True, pending=[])
                            return wire
                        owner.PolicyValue.to_dict = replacement
                    else:
                        original_lookup = owner.PolicyValue.__getattribute__
                        def replacement(self, name):
                            if original_lookup(self, "value_type") == "bool":
                                if name == "state":
                                    return "value"
                                if name == "value":
                                    return True
                                if name == "_pending":
                                    return ()
                            return original_lookup(self, name)
                        owner.PolicyValue.__getattribute__ = replacement
                    from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
                    try:
                        selected = fixture.state_selection("SH600000")
                        selected.recheck()
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("replaced value method manufactured current evidence")
                finally:
                    fixture.close()
            ''')
            result = subprocess.run([sys.executable, "-c", script, method], capture_output=True, text=True)
            with self.subTest(method=method):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_registry_alias_replacement_before_state_import_cannot_mint_evidence(self):
        script = textwrap.dedent('''
            from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
            from ashare_pipeline import formal_policy_registry as owner
            fixture = PolicyRuntimeFixture()
            try:
                wire = fixture.policy_registry.to_dict()
                class ForgedPolicy:
                    def require_verified(self):
                        return self
                    def to_dict(self):
                        return wire
                owner.FormalPolicyRegistry = ForgedPolicy
                from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
                try:
                    selected = FormalPolicyStateRepository(fixture.context).select(
                        "SH600000", "2026-08-31T07:00:00+00:00", template_id="bank", policy_registry=ForgedPolicy())
                    selected.recheck()
                except ValueError:
                    pass
                else:
                    raise AssertionError("public registry alias minted a state selection")
            finally:
                fixture.close()
        ''')
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_state_first_import_preserves_genuine_registry_reads(self):
        script = textwrap.dedent('''
            from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
            from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
            fixture = PolicyRuntimeFixture()
            try:
                selected = fixture.state_selection("SH600000")
                assert selected.values
                selected.recheck()
            finally:
                fixture.close()
        ''')
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_state"),
                             "authenticated policy state selection is missing")
        from ashare_pipeline import formal_policy_state
        return formal_policy_state

    def fixture(self, **kwargs):
        self.api()
        fixture = PolicyRuntimeFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def selected_value(self, fixture, selection, semantic):
        rule = next(r for r in fixture.policy_registry.to_dict()["rules"]
                    if r["template_id"] == "bank" and r["semantic_id"] == semantic)
        return selection.values[digest(rule["inputs"]["value"])], rule

    def test_false_flag_is_not_missing_flag(self):
        read_flag = self.api().read_flag
        self.assertIs(read_flag(({"flag_id": "audit", "active": False},), "audit"), False)
        self.assertIsNone(read_flag((), "audit"))
        for flags in (({"flag_id": "audit", "active": 0},),
                      ({"flag_id": "audit", "active": True},) * 2):
            with self.assertRaises(ValueError):
                read_flag(flags, "audit")

    def test_real_false_matches_signed_expected_false(self):
        def configure(documents):
            descriptor = next(d for d in documents["scoring"]["descriptors"]
                              if d["context_kind"] == "regulatory_state")
            descriptor["allowed_regulatory_flags"] = sorted([*descriptor["allowed_regulatory_flags"], "fixture_false"])
            for role in ("status", "event"):
                for rule in documents[role]["rules"].values():
                    for selector in rule.get("inputs", {}).values():
                        if selector.get("context_kind") == "regulatory_state":
                            selector["descriptor_id"] = digest(descriptor)
            rule = copy.deepcopy(documents["status"]["rules"]["bank_audit_qualified"])
            rule["semantic_id"] = "fixture_false"
            rule["inputs"]["value"]["entry_id"] = "fixture_false"
            rule["parameters"]["expected"] = False
            documents["status"]["rules"]["bank_fixture_false"] = rule
            active = documents["status"]["rules"]["execution_contract"]["rule_ids"]
            active.append("bank_fixture_false")
            active.sort()
            documents["scoring"]["scoring"]["status_rules"].append(
                dict(policy_role="status", rule_id="bank_fixture_false"))
        fixture = self.fixture(mutate=configure)
        fact, ref = fixture.put_policy_context("SH600000", "regulatory_state",
            {"flags": [{"flag_id": "fixture_false", "active": False}]})
        selected = fixture.state_selection("SH600000")
        value, rule = self.selected_value(fixture, selected, "fixture_false")
        self.assertEqual(value.state, "value")
        self.assertIs(value.value, False)
        self.assertIs(value.value, rule["parameters"]["expected"])
        self.assertIn(fact.id, str(selected.lineage))
        self.assertIn(ref.snapshot_id, str(selected.lineage))
        selected.recheck()

    def test_missing_flag_is_pending_and_keeps_whole_factor(self):
        fixture = self.fixture()
        fixture.put_policy_context("SH600000", "regulatory_state",
            {"flags": [{"flag_id": "governance_red", "active": False}]})
        selected = fixture.state_selection("SH600000")
        value, _ = self.selected_value(fixture, selected, "audit_qualified")
        self.assertIsNone(value.value)
        self.assertEqual(value.to_dict()["pending"][0]["code"], "state_entry_missing")
        self.assertIn("governance_red", str(selected.lineage))

    def test_absent_factor_is_bound_pending_and_late_factor_invalidates(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        value, _ = self.selected_value(fixture, selected, "st")
        self.assertEqual(value.state, "missing")
        self.assertEqual(value.to_dict()["pending"][0]["origin"], "runtime")
        self.assertTrue(value.evidence_hashes)
        selected.recheck()
        fixture.put_policy_context("SH600000", "security_state", SECURITY)
        with self.assertRaises(ValueError):
            selected.recheck()

    def test_security_flags_and_enum_are_projected_without_suspension_veto(self):
        fixture = self.fixture()
        fixture.put_policy_context("SH600000", "security_state", {**SECURITY, "suspended": True})
        selected = fixture.state_selection("SH600000")
        for semantic in ("st", "star_st", "forced_delist_risk"):
            value, _ = self.selected_value(fixture, selected, semantic)
            self.assertIs(value.value, False)
        value, _ = self.selected_value(fixture, selected, "delisting_arrangement")
        self.assertEqual(value.value, "listed")
        self.assertNotIn("suspended", [entry["selector"]["field"]
            for entry in selected.lineage["entries"].values()])
        self.assertFalse(hasattr(selected, "effects"))

    def test_unapproved_flag_or_event_id_fails_producer_contract(self):
        for kind, value in (("regulatory_state", {"flags": [{"flag_id": "invented", "active": False}]}),
            ("event_calendar", {"events": [dict(event_id="invented", event_date="2026-08-31",
                quantified_value="2", unit="ratio")]})):
            fixture = self.fixture()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                fixture.put_policy_context("SH600000", kind, value)

    def test_current_correction_invalidates_even_same_value(self):
        fixture = self.fixture()
        fixture.put_policy_context("SH600000", "security_state", SECURITY)
        selected = fixture.state_selection("SH600000")
        fixture.put_policy_context("SH600000", "security_state", SECURITY, generation="g2")
        with self.assertRaises(ValueError):
            selected.recheck()
        self.assertNotEqual(selected.selection_hash, fixture.state_selection("SH600000").selection_hash)

    def test_registered_raw_loss_is_failure_not_pending(self):
        fixture = self.fixture()
        _, ref = fixture.put_policy_context("SH600000", "security_state", SECURITY)
        selected = fixture.state_selection("SH600000")
        # This path is owned by this fixture's TemporaryDirectory only.
        paths = list((fixture.root / "raw").rglob(ref.content_sha256 + ".bin"))
        self.assertTrue(paths)
        paths[0].unlink()
        with self.assertRaises(ValueError):
            selected.recheck()

    def test_copied_selection_or_repository_has_no_authority(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        for clone in (copy.copy, copy.deepcopy):
            with self.assertRaises(TypeError):
                clone(selected)
        fake = object.__new__(type(selected))
        with self.assertRaises(ValueError):
            fake.recheck()
        context = copy.copy(fixture.context)
        with self.assertRaises(ValueError):
            self.api().FormalPolicyStateRepository(context)
        repository = self.api().FormalPolicyStateRepository(fixture.context)
        for clone in (copy.copy, copy.deepcopy):
            with self.assertRaises(TypeError):
                clone(repository)
        forged = object.__new__(type(repository))
        with self.assertRaises(ValueError):
            forged.select("SH600000", FREEZE, template_id="bank", policy_registry=fixture.policy_registry)
        repository.select("SH600000", FREEZE, template_id="bank", policy_registry=fixture.policy_registry).recheck()

    def test_context_method_shadow_is_rejected_before_and_after_selection(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        with patch.object(fixture.context, "get_verified_many", lambda *a: {}):
            with self.assertRaises(ValueError):
                selected.recheck()
            with self.assertRaises(ValueError):
                self.api().FormalPolicyStateRepository(fixture.context)

    def test_selection_method_shadow_is_rejected(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        with patch.object(type(selected), "recheck", lambda self: None):
            with self.assertRaises(ValueError):
                selected.recheck()

    def test_value_validator_replacement_is_an_integrity_failure(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        with patch.object(PolicyValue, "from_dict", lambda wire: wire):
            try:
                with self.assertRaises(ValueError):
                    selected.recheck()
            except AttributeError as error:
                self.fail(f"validator substitution requires an integrity error: {error}")

    def test_value_serializer_replacement_cannot_forge_selected_values(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        with patch.object(PolicyValue, "to_dict", lambda self: {}):
            with self.assertRaises(ValueError):
                fixture.state_selection("SH600000")
            with self.assertRaises(ValueError):
                selected.recheck()

    def test_wrong_freeze_template_and_registry_fail(self):
        fixture = self.fixture()
        repository = self.api().FormalPolicyStateRepository(fixture.context)
        for security, freeze, template, registry in (("sh600000", FREEZE, "bank", fixture.policy_registry),
            ("SH600000", "2026-08-30T07:00:00+00:00", "bank", fixture.policy_registry),
            ("SH600000", FREEZE, "invented", fixture.policy_registry),
            ("SH600000", FREEZE, "bank", object.__new__(type(fixture.policy_registry)))):
            with self.subTest(security=security, freeze=freeze, template=template), self.assertRaises(ValueError):
                repository.select(security, freeze, template_id=template, policy_registry=registry)

    def test_equal_leading_versions_are_not_pending(self):
        fixture = self.fixture()
        fixture.put_policy_context("SH600000", "security_state", SECURITY)
        selected = fixture.state_selection("SH600000")
        # Test-only fixture timestamps deliberately create a genuine leading tie.
        fixture._policy_context_generations[("SH600000", "security_state")]["tie"] = 0
        fixture.put_policy_context("SH600000", "security_state", SECURITY, generation="tie")
        with self.assertRaises(ValueError):
            fixture.state_selection("SH600000")
        with self.assertRaises(ValueError):
            selected.recheck()

    def test_receipt_loss_revokes_current_selection(self):
        fixture = self.fixture()
        _, ref = fixture.put_policy_context("SH600000", "regulatory_state", {"flags": []})
        selected = fixture.state_selection("SH600000")
        fixture.sql("DELETE FROM formal_task_snapshot_receipt WHERE task_id=?", (ref.producing_task_id,))
        with self.assertRaises(ValueError):
            selected.recheck()

    def test_signed_major_event_flag_remains_boolean_not_quantified_zero(self):
        fixture = self.fixture()
        fixture.put_policy_context("SH600000", "regulatory_state",
            {"flags": [{"flag_id": "major_event", "active": False}]})
        selected = fixture.state_selection("SH600000")
        value, _ = self.selected_value(fixture, selected, "major_event")
        self.assertIs(value.value, False)
        self.assertEqual(value.value_type, "bool")
        self.assertIsNone(value.unit)

    def test_unquantified_context_event_cannot_be_zero_filled(self):
        fixture = self.fixture()
        with self.assertRaises(ValueError):
            fixture.put_policy_context("SH600000", "event_calendar", {"events": [dict(
                event_id="fixture_quantified_event", event_date="2026-08-31", quantified_value=None, unit="ratio")]})

    def test_v1_genuine_registry_rejects_quantified_event_rule_input(self):
        def configure(documents):
            entry = next(d for d in documents["scoring"]["descriptors"] if d["context_kind"] == "event_calendar")
            selector = context_selector("event_calendar", "event", "event_record",
                entry_id="fixture_quantified_event", expected_unit="ratio")
            selector.update(descriptor_id=digest(entry), scope_key=entry["scope_key"])
            documents["event"]["rules"]["bank_major_event"]["inputs"]["value"] = selector
        with self.assertRaises(ValueError):
            self.fixture(mutate=configure)

    def test_unrequested_event_factor_is_not_read_or_given_policy_authority(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        fixture.put_policy_context("SH600000", "event_calendar", {"events": [dict(
            event_id="fixture_quantified_event", event_date="2026-08-31", quantified_value="2", unit="ratio")]})
        selected.recheck()
        self.assertEqual(selected.selection_hash, fixture.state_selection("SH600000").selection_hash)
        self.assertNotIn("event_calendar", [entry["selector"]["context_kind"]
                         for entry in selected.lineage["entries"].values()])

    def test_audit_views_are_detached_and_read_only(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        with self.assertRaises(TypeError):
            selected.values["invented"] = None
        with self.assertRaises(TypeError):
            selected.lineage["security_id"] = "SZ000001"
        value, _ = self.selected_value(fixture, selected, "st")
        for clone in (copy.copy(value), copy.deepcopy(value)):
            self.assertEqual(clone.to_dict(), value.to_dict())
        wire = value.to_dict()
        wire["pending"][0]["code"] = "unsupported_unit"
        self.assertEqual(self.selected_value(fixture, selected, "st")[0].to_dict()["pending"][0]["code"],
                         "state_entry_missing")
        selected.recheck()

    def test_replaced_raw_store_or_verifier_invalidates_retained_repository(self):
        fixture = self.fixture()
        selected = fixture.state_selection("SH600000")
        for target, name, replacement in ((fixture.context, "_verifier", object()),
                                          (fixture.snapshots, "_raw_store", copy.copy(fixture.raw))):
            with self.subTest(name=name), patch.object(target, name, replacement), self.assertRaises(ValueError):
                selected.recheck()


if __name__ == "__main__":
    unittest.main()
