"""Static policy binding tests against real, in-memory signed registry graphs."""

import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_policy_contract import PolicyContractError
from ashare_pipeline.formal_policy_registry import _bind_policy_contract
from tests.formal_policy_fixtures import policy_graph
from tests.test_formal_scoring_registry import canonical


def bind_graph(**kwargs):
    bundle, feature, scoring, _, _ = policy_graph(**kwargs)
    return json.loads(_bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature))


def rule_for(documents, semantic="cyclic_top", role="cyclic", template="bank"):
    return documents[role]["rules"][f"{template}_{semantic}"]


def change_descriptor(documents, kind, **changes):
    entry = next(d for d in documents["scoring"]["descriptors"] if d["context_kind"] == kind)
    old_hash = hashlib.sha256(canonical(entry)).hexdigest()
    entry.update(changes)
    new_hash = hashlib.sha256(canonical(entry)).hexdigest()
    for role in ("cyclic", "redline", "status", "event"):
        for rule in documents[role]["rules"].values():
            for selector in rule.get("inputs", {}).values():
                if selector.get("descriptor_id") == old_hash:
                    selector["descriptor_id"] = new_hash


class PolicySelectorBindingTests(unittest.TestCase):
    def test_unknown_cross_template_unit_version_and_period_feature_fail(self):
        for change in ({"feature_key": "unknown"}, {"feature_key": "broker.policy.roe"},
                {"template_id": "broker"}, {"expected_unit": "CNY"},
                {"formula_version": "other"}, {"period_keys": ["FY1"]}):
            with self.subTest(change=change), self.assertRaises(PolicyContractError):
                bind_graph(mutate=lambda d: rule_for(d)["inputs"]["current_roe"].update(change))

    def test_annual_repeated_slot_fails_even_with_distinct_year_labels(self):
        def mutate(d):
            observations = rule_for(d)["inputs"]["annual_roe"]["observations"]
            observations[1]["selector"] = copy.deepcopy(observations[0]["selector"])
        with self.assertRaisesRegex(PolicyContractError, "annual|repeated"):
            bind_graph(mutate=mutate)

    def test_distinct_slots_with_identical_formula_cannot_fake_five_years(self):
        def mutate(d):
            slots = {s["slot_id"]: s for s in d["feature"]["slots"]}
            slots["bank.policy.roe_2022"]["formula"] = copy.deepcopy(slots["bank.policy.roe_2021"]["formula"])
            rule_for(d)["inputs"]["annual_roe"]["observations"][1]["selector"]["period_keys"] = ["FY2021"]
        with self.assertRaisesRegex(PolicyContractError, "annual|repeated"):
            bind_graph(mutate=mutate)

    def test_annual_cross_year_balance_formula_binds_complete_period_set(self):
        def mutate(d):
            slot = next(s for s in d["feature"]["slots"] if s["slot_id"] == "bank.policy.roe_2021")
            slot["formula"] = dict(op="divide", left=slot["formula"],
                right=dict(op="fact", fact_key="fixture.opening_equity", period_key="FY2020"))
            rule_for(d)["inputs"]["annual_roe"]["observations"][0]["selector"]["period_keys"] = ["FY2020", "FY2021"]
        wire = bind_graph(mutate=mutate)
        match = next(b for b in wire["binding_manifest"] if b["rule_id"] == "bank_cyclic_top"
            and b["input_path"] == "inputs.annual_roe.observations[0].selector")
        self.assertEqual(match["slot"]["formula"]["right"]["period_key"], "FY2020")
        self.assertIs(match["slot"]["required"], False)

    def test_series_units_must_match_current_even_when_each_slot_matches(self):
        def mutate(d):
            for slot in d["feature"]["slots"]:
                if slot["slot_id"].startswith("bank.policy.roe_"):
                    slot["unit"] = "CNY"
            for item in rule_for(d)["inputs"]["annual_roe"]["observations"]:
                item["selector"]["expected_unit"] = "CNY"
        with self.assertRaisesRegex(PolicyContractError, "unit"):
            bind_graph(mutate=mutate)

    def test_wrapper_hash_cannot_impersonate_descriptor_entry(self):
        def mutate(d):
            rule_for(d, "st", "status")["inputs"]["value"]["descriptor_id"] = hashlib.sha256(canonical(d["scoring"])).hexdigest()
        with self.assertRaisesRegex(PolicyContractError, "descriptor"):
            bind_graph(mutate=mutate)

    def test_context_scope_kind_and_field_type_must_match(self):
        for change in ({"scope_key": "other"}, {"context_kind": "regulatory_state"}, {"expected_type": "enum"}):
            with self.subTest(change=change), self.assertRaises(PolicyContractError):
                bind_graph(mutate=lambda d: rule_for(d, "st", "status")["inputs"]["value"].update(change))

    def test_security_market_and_calendar_require_input_security_exchange(self):
        for kind in ("security_state", "regulatory_state", "market_close", "trading_calendar"):
            for changes in (dict(security_scope="none", request_security="none", exchange_rule="none"),
                    dict(exchange_rule="fixed_exchange", fixed_exchange="SZ")):
                with self.subTest(kind=kind, changes=changes), self.assertRaisesRegex(PolicyContractError, "security|exchange"):
                    bind_graph(mutate=lambda d: change_descriptor(d, kind, **changes))

    def test_context_flag_must_be_authorized(self):
        with self.assertRaisesRegex(PolicyContractError, "flag|authorized"):
            bind_graph(mutate=lambda d: rule_for(d, "audit_adverse", "status")["inputs"]["value"].update(entry_id="unapproved"))

    def test_missing_exchange_and_null_plus_exact_source_are_rejected(self):
        def missing(d):
            d["source"]["configs"][:] = [c for c in d["source"]["configs"] if c["exchange_scope"] != "BJ"]
        def ambiguous(d):
            added = copy.deepcopy(d["source"]["configs"][0])
            added["exchange_scope"] = None
            d["source"]["configs"].append(added)
        for mutate in (missing, ambiguous):
            with self.subTest(mutate=mutate), self.assertRaisesRegex(PolicyContractError, "source"):
                bind_graph(mutate=mutate)

    def test_descriptor_source_identity_fields_and_calendar_must_match(self):
        for field, value in (("source", "other"), ("dataset", "other"), ("parser_id", "other"),
                ("parser_version", "other"), ("mapping_version", "other"),
                ("calendar_selector", dict(context_kind="trading_calendar", scope_key="signed-calendar", exchange="SZ", as_of_rule="visible_at_freeze"))):
            with self.subTest(field=field), self.assertRaises(PolicyContractError):
                bind_graph(mutate=lambda d: change_descriptor(d, "security_state", **{field: value}))

    def test_matching_calendar_text_cannot_bind_sz_calendar_for_sh_and_bj(self):
        def mutate(d):
            selector = dict(context_kind="trading_calendar", scope_key="signed-calendar", exchange="SZ", as_of_rule="visible_at_freeze")
            for entry in d["scoring"]["descriptors"]:
                change_descriptor(d, entry["context_kind"], calendar_selector=copy.deepcopy(selector))
            for config in d["source"]["configs"]:
                config["calendar_selector"] = copy.deepcopy(selector)
        # The verified bundle loader validates SourceAdapterConfig before A2 runs.
        with self.assertRaisesRegex(ValueError, "calendar selector exchange must match exchange_scope"):
            bind_graph(mutate=mutate)

    def test_source_identity_mismatch_on_only_bj_is_rejected(self):
        def mutate(d):
            next(c for c in d["source"]["configs"] if c["exchange_scope"] == "BJ")["parser_version"] = "other"
        with self.assertRaisesRegex(PolicyContractError, "parser_version"):
            bind_graph(mutate=mutate)

    def test_input_security_bootstrap_calendar_is_rejected(self):
        with self.assertRaisesRegex(PolicyContractError, "bootstrap"):
            bind_graph(mutate=lambda d: change_descriptor(d, "trading_calendar", bootstrap_calendar=True))

    def test_duplicate_context_descriptor_is_rejected_in_v1(self):
        with self.assertRaisesRegex(PolicyContractError, "duplicate"):
            bind_graph(mutate=lambda d: d["scoring"]["descriptors"].append(copy.deepcopy(d["scoring"]["descriptors"][0])))

    def test_manifest_preserves_full_signed_context_entry_and_identity(self):
        bundle, feature, scoring, _, _ = policy_graph()
        wire = json.loads(_bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature))
        entry = json.loads(bundle.blob("scoring").canonical_json)["descriptors"][0]
        match = next(b for b in wire["binding_manifest"] if b["rule_id"] == "bank_st")
        self.assertEqual(match["descriptor"], entry)
        self.assertEqual(match["descriptor_id"], hashlib.sha256(canonical(entry)).hexdigest())


class PolicyBindingTests(unittest.TestCase):
    def test_complete_signed_graph_binds_without_runtime_evidence(self):
        # Loading the existing official registries succeeds before the new API is exercised.
        bundle, feature, scoring, _, _ = policy_graph()
        from ashare_pipeline.formal_policy_registry import _bind_policy_contract
        raw = _bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature)
        wire = json.loads(raw)
        self.assertEqual(wire["registry_manifest_hash"], bundle.manifest.manifest_hash)
        self.assertEqual(set(wire["role_hashes"]), set(scoring.role_hashes))
        self.assertEqual(wire["contract_version"], "formal-policy-execution-contract-v1")
        self.assertEqual(len(wire["rules"]), 80)
        self.assertEqual(len(wire["binding_manifest"]), 170)
        self.assertEqual(set(wire), {"schema_version", "contract_version", "registry_manifest_hash",
            "role_hashes", "role_versions", "source_evidence_categories", "rules",
            "valuation_dependencies", "cyclic_secondary_industries", "binding_manifest"})
        self.assertNotIn("security_id", wire)
        self.assertNotIn("pool_eligible", wire)


class PolicyCoverageTests(unittest.TestCase):
    def test_every_mandatory_semantic_is_required_after_valid_signing(self):
        semantics = ("st", "star_st", "delisting_arrangement", "forced_delist_risk",
            "governance_red", "audit_qualified", "audit_adverse", "audit_disclaimer",
            "nonpositive_equity", "no_effective_trade_20d", "governance_orange", "crowding",
            "major_unlock_window", "major_reduction_window", "major_event", "cyclic_top")
        for semantic in semantics:
            def mutate(d):
                role = "cyclic" if semantic == "cyclic_top" else "redline" if semantic == "nonpositive_equity" else "event" if semantic == "major_event" else "status"
                key = f"bank_{semantic}"
                d[role]["rules"]["execution_contract"]["rule_ids"].remove(key)
                for name in ("redlines", "status_rules"):
                    d["scoring"]["scoring"][name][:] = [r for r in d["scoring"]["scoring"][name] if r["rule_id"] != key]
            with self.subTest(semantic=semantic), self.assertRaisesRegex(PolicyContractError, semantic):
                bind_graph(mutate=mutate)

    def test_hard_veto_cannot_be_reduced_to_one_pool(self):
        with self.assertRaisesRegex(PolicyContractError, "both|st"):
            bind_graph(mutate=lambda d: rule_for(d, "st", "status")["outcomes"]["on_match"][0].update(pool="strong"))

    def test_nonpositive_equity_requires_lte_zero(self):
        for change in ({"threshold": "1"}, {"comparator": "lt"}):
            with self.subTest(change=change), self.assertRaisesRegex(PolicyContractError, "nonpositive_equity"):
                bind_graph(mutate=lambda d: rule_for(d, "nonpositive_equity", "redline")["parameters"].update(change))

    def test_st_and_regulatory_rules_cannot_match_false(self):
        for semantic in ("st", "audit_adverse", "governance_orange"):
            with self.subTest(semantic=semantic), self.assertRaisesRegex(PolicyContractError, semantic):
                bind_graph(mutate=lambda d: rule_for(d, semantic, "status")["parameters"].update(expected=False))

    def test_mandatory_security_semantics_cannot_use_another_field(self):
        with self.assertRaisesRegex(PolicyContractError, "st"):
            bind_graph(mutate=lambda d: rule_for(d, "st", "status")["inputs"]["value"].update(field="suspended"))

    def test_delisting_enum_cannot_veto_listed_securities(self):
        with self.assertRaisesRegex(PolicyContractError, "delisting_arrangement"):
            bind_graph(mutate=lambda d: rule_for(d, "delisting_arrangement", "status")["parameters"].update(values=["delisting_arrangement", "listed"]))

    def test_regulatory_semantics_cannot_share_one_generic_flag(self):
        with self.assertRaisesRegex(PolicyContractError, "flag|regulatory"):
            bind_graph(mutate=lambda d: rule_for(d, "audit_adverse", "status")["inputs"]["value"].update(entry_id="governance_red"))

    def test_independent_status_needs_status_and_explicit_pool(self):
        for kept_kind in ("independent_status", "pool_prohibition"):
            def mutate(d):
                outcomes = rule_for(d, "crowding", "status")["outcomes"]
                outcomes["on_match"] = [e for e in outcomes["on_match"] if e["kind"] == kept_kind]
            with self.subTest(kept_kind=kept_kind), self.assertRaisesRegex(PolicyContractError, "crowding"):
                bind_graph(mutate=mutate)

    def test_duplicate_semantic_across_roles_is_rejected(self):
        def mutate(d):
            rule = copy.deepcopy(rule_for(d, "st", "status"))
            d["event"]["rules"]["bank_duplicate_st"] = rule
            d["event"]["rules"]["execution_contract"]["rule_ids"].append("bank_duplicate_st")
            d["event"]["rules"]["execution_contract"]["rule_ids"].sort()
        with self.assertRaisesRegex(PolicyContractError, "semantic"):
            bind_graph(mutate=mutate)

    def test_every_scoring_reference_requires_an_active_rule(self):
        for target in ("redlines", "status_rules", "market_liquidity_rule", "metric"):
            def mutate(d):
                role = "redline" if target in ("redlines", "metric") else "status"
                semantic = "nonpositive_equity" if role == "redline" else "no_effective_trade_20d"
                d[role]["rules"]["inactive_extra"] = copy.deepcopy(rule_for(d, semantic, role))
                ref = dict(policy_role=role, rule_id="inactive_extra")
                scoring = d["scoring"]["scoring"]
                if target == "metric":
                    scoring["templates"]["bank"]["metrics"]["V"][0]["policy_refs"] = [ref]
                elif target == "market_liquidity_rule":
                    scoring[target] = ref
                else:
                    scoring[target].append(ref)
            with self.subTest(target=target), self.assertRaisesRegex(PolicyContractError, "active"):
                bind_graph(mutate=mutate)

    def test_metric_policy_reference_must_belong_to_its_template(self):
        def mutate(d):
            d["scoring"]["scoring"]["templates"]["bank"]["metrics"]["V"][0]["policy_refs"][0]["rule_id"] = "broker_nonpositive_equity"
        with self.assertRaisesRegex(PolicyContractError, "template"):
            bind_graph(mutate=mutate)

    def test_valuation_dependencies_cover_exact_current_template_v_metrics(self):
        for mutation in (lambda deps: deps.pop(),
                lambda deps: deps[0].update(metric_id="V.unknown"),
                lambda deps: deps[0].update(metric_id="V.broker.normalized_earnings_yield")):
            def mutate(d):
                deps = rule_for(d)["parameters"]["valuation_dependencies"]
                mutation(deps)
                deps.sort(key=lambda item: item["metric_id"])
            with self.subTest(mutation=mutation), self.assertRaisesRegex(PolicyContractError, "valuation"):
                bind_graph(mutate=mutate)

    def test_invalid_v_dependency_declarations_fail_with_signed_graph(self):
        for mutation in (lambda deps: deps.append(copy.deepcopy(deps[-1])),
                lambda deps: deps[0].update(metric_id="G.operating_revenue_yoy"),
                lambda deps: deps[0].update(adapter_version=None),
                lambda deps: deps[0].update(profit_semantic_id="other_rule"),
                lambda deps: deps[1].update(adapter_id="not_null")):
            with self.subTest(mutation=mutation), self.assertRaises(PolicyContractError):
                bind_graph(mutate=lambda d: mutation(rule_for(d)["parameters"]["valuation_dependencies"]))


class PolicyCompatibilityTests(unittest.TestCase):
    def test_v1_v2_preserve_original_context_entries_and_consensus_links(self):
        from tests.test_formal_context_repository import descriptor
        from tests.test_formal_scoring_consensus_registry import consensus_descriptor
        for version in ("v1", "v2"):
            with self.subTest(version=version):
                bundle, feature, scoring, _, _ = policy_graph(version=version)
                wrapper = json.loads(bundle.blob("scoring").canonical_json)
                wire = json.loads(_bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature))
                self.assertIn(descriptor(), wrapper["descriptors"])
                self.assertEqual(wire["registry_manifest_hash"], bundle.manifest.manifest_hash)
                self.assertEqual(wire["cyclic_secondary_industries"], ["fixture-cyclic"])
                if version == "v2":
                    original = consensus_descriptor()
                    self.assertIn(original, wrapper["descriptors"])
                    self.assertEqual(scoring.consensus_no_coverage_links["bank"]["descriptor_id"], hashlib.sha256(canonical(original)).hexdigest())
                    self.assertEqual(wrapper["input_alternatives"][0]["metric_id"], "T.expectation_change")
                else:
                    self.assertEqual(scoring.consensus_no_coverage_links, {})

    def test_old_signed_graph_remains_loadable_but_has_no_execution_contract(self):
        from ashare_pipeline.formal_scoring_registry import RegistryApproval, load_formal_registry
        from tests.test_formal_scoring_registry import signed_graph
        bundle, feature, _, _ = signed_graph(context=True)
        scoring = load_formal_registry(bundle, RegistryApproval("official", bundle.manifest.scoring_registry_hash,
            bundle.manifest.approval_id), feature_registry=feature)
        scoring.require_official(bundle)
        with self.assertRaisesRegex(PolicyContractError, "execution_contract"):
            _bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature)

    def test_changed_signed_definition_changes_root_bytes_and_rejects_old_scoring(self):
        bundle, feature, scoring, _, _ = policy_graph()
        def mutate(d):
            rule_for(d)["parameters"]["valuation_dependencies"][0]["definition_basis"] = "revised fixture-only basis"
        changed, changed_feature, changed_scoring, _, _ = policy_graph(mutate=mutate)
        first = _bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature)
        second = _bind_policy_contract(changed, scoring_registry=changed_scoring, feature_registry=changed_feature)
        self.assertNotEqual(bundle.manifest.manifest_hash, changed.manifest.manifest_hash)
        self.assertNotEqual(first, second)
        self.assertEqual(second, _bind_policy_contract(changed, scoring_registry=changed_scoring, feature_registry=changed_feature))
        with self.assertRaisesRegex(ValueError, "manifest"):
            _bind_policy_contract(changed, scoring_registry=scoring, feature_registry=changed_feature)
        # The old feature's genuine bytes still belong to the second graph.
        self.assertEqual(feature.canonical_json, changed_feature.canonical_json)
        self.assertEqual(second, _bind_policy_contract(changed, scoring_registry=changed_scoring, feature_registry=feature))

    def test_old_feature_content_cannot_be_mixed_into_changed_feature_graph(self):
        _, old_feature, _, _, _ = policy_graph()
        def mutate(d):
            next(s for s in d["feature"]["slots"] if s["slot_id"] == "bank.policy.equity")["formula"]["fact_key"] = "fixture.revised_equity"
        bundle, feature, scoring, _, _ = policy_graph(mutate=mutate)
        _bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature)
        with self.assertRaisesRegex(PolicyContractError, "feature"):
            _bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=old_feature)

    def test_exact_objects_and_copies_cannot_replace_verified_inputs(self):
        bundle, feature, scoring, _, _ = policy_graph()
        for which, original in (("bundle", bundle), ("feature", feature), ("scoring", scoring)):
            for value in (object(), copy.copy(original)):
                args = dict(bundle=bundle, scoring_registry=scoring, feature_registry=feature)
                args[{"bundle": "bundle", "feature": "feature_registry", "scoring": "scoring_registry"}[which]] = value
                with self.subTest(which=which, value=type(value)), self.assertRaises(ValueError):
                    _bind_policy_contract(**args)

    def test_original_verifiers_cannot_be_shadowed_to_accept_copies(self):
        bundle, feature, scoring, _, _ = policy_graph()
        for original, method, argument in ((bundle, "require_official", "bundle"),
                (feature, "require_release_eligible", "feature_registry"),
                (scoring, "require_official", "scoring_registry")):
            copied = copy.copy(original)
            with self.subTest(argument=argument), patch.object(type(original), method, lambda *args: None):
                args = dict(bundle=bundle, scoring_registry=scoring, feature_registry=feature)
                args[argument] = copied
                with self.assertRaises(ValueError):
                    _bind_policy_contract(**args)

    def test_mutated_verified_child_bytes_are_rejected(self):
        bundle, feature, scoring, _, _ = policy_graph()
        object.__setattr__(bundle.blob("event"), "canonical_json", b"{}")
        with self.assertRaises(ValueError):
            _bind_policy_contract(bundle, scoring_registry=scoring, feature_registry=feature)

    def test_legacy_policy_metadata_mismatch_errors_are_preserved(self):
        from ashare_pipeline.formal_scoring_registry import RegistryApproval, load_formal_registry, RegistryValidationError
        from tests.formal_policy_fixtures import add_policy_documents, rehash_documents
        from tests.test_formal_scoring_registry import signed_graph
        for field, value in (("registry_version", "wrong"), ("source_evidence_categories", ["wrong"]), ("registry_hash", "0" * 64)):
            def mutate(d):
                add_policy_documents(d)
                rehash_documents(d)
                d["scoring"]["scoring"]["policy_contracts"]["event"][field] = value
            bundle, feature, _, _ = signed_graph(context=True, mutate=mutate)
            with self.subTest(field=field), self.assertRaises(RegistryValidationError):
                load_formal_registry(bundle, RegistryApproval("official", bundle.manifest.scoring_registry_hash,
                    bundle.manifest.approval_id), feature_registry=feature)

    def test_classification_metric_reference_remains_the_only_inactive_exception(self):
        def mutate(d):
            scoring = d["scoring"]["scoring"]
            scoring["templates"]["bank"]["metrics"]["V"][0]["policy_refs"].append(copy.deepcopy(scoring["cyclic_rule"]))
        self.assertEqual(len(bind_graph(mutate=mutate)["rules"]), 80)

    def test_additional_signed_regulatory_semantic_cannot_alias_required_flag(self):
        def mutate(d):
            rule = copy.deepcopy(rule_for(d, "governance_red", "status"))
            rule["semantic_id"] = "additional_governance_status"
            d["status"]["rules"]["bank_additional_governance"] = rule
            d["status"]["rules"]["execution_contract"]["rule_ids"].append("bank_additional_governance")
            d["status"]["rules"]["execution_contract"]["rule_ids"].sort()
        with self.assertRaisesRegex(PolicyContractError, "regulatory|flag"):
            bind_graph(mutate=mutate)


if __name__ == "__main__":
    unittest.main()
