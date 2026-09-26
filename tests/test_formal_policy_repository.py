"""The policy authority publishes exactly one complete frozen population."""

import copy
import importlib
import sys
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture


class PolicyRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
                             "W3 complete policy publication is missing")
        self.api = importlib.import_module("ashare_pipeline.formal_policy_repository")

    def fixture(self, **kwargs):
        fixture = PolicyRuntimeFixture(range_enabled=True, **kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def test_complete_enumeration_includes_pending_security(self):
        fixture = self.fixture()
        batch = fixture.build_policy_batch()
        batch.require_official()
        self.assertEqual(batch.security_ids, ("BJ430001", "SH600000", "SZ000001"))
        self.assertEqual(tuple(item.security_id for item in batch.results), batch.security_ids)
        self.assertEqual(len(batch.results), 3)
        self.assertTrue(all(item.pending_requirements for item in batch.results))
        self.assertTrue(all(item.decisions == () for item in batch.results))

    def test_genuine_all_member_evidence_reaches_complete_results(self):
        fixture = self.fixture(cyclic=False)
        fixture.populate_policy_evidence()
        batch = fixture.build_policy_batch()
        self.assertEqual(len(batch.results), 3)
        for item in batch.results:
            item.require_verified()
            self.assertEqual(item.evidence_state, "complete")
            self.assertFalse(item.pending_requirements)
            self.assertTrue(item.decisions)
            self.assertEqual(item.batch_hash, batch.batch_hash)
            self.assertTrue(all(decision.security_id == item.security_id for decision in item.decisions))

    def test_public_recheck_independently_reselects_original_inputs(self):
        fixture = self.fixture()
        fixture.put_industry("SH600000")
        batch = fixture.build_policy_batch()
        from ashare_pipeline.formal_policy_financial import FormalPolicyFinancialRepository
        from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
        calls = {FormalPolicyFinancialRepository.select.__code__: 0,
                 FormalPolicyStateRepository.select.__code__: 0}

        def profile(frame, event, result):
            if event == "call" and frame.f_code in calls:
                calls[frame.f_code] += 1

        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            fixture.policy_repository.recheck_current(batch)
        finally:
            sys.setprofile(previous)
        self.assertEqual(list(calls.values()), [1, 1])
        foreign = self.fixture()
        with self.assertRaises(ValueError):
            foreign.policy_repository.recheck_current(batch)
        with self.assertRaises(TypeError):
            copy.copy(batch)

    def test_private_owner_scope_stays_live_for_enclosing_batch_and_rejects_replay(self):
        from ashare_pipeline.formal_batch_read_journal import (
            FormalBatchReadJournal, _require_current_scope,
        )
        from ashare_pipeline.formal_policy_financial import FormalPolicyFinancialRepository
        from ashare_pipeline.formal_policy_repository import FormalPolicyRepository
        fixture = self.fixture()
        fixture.put_industry("SH600000")
        universe = fixture.policy_context_repository.load_universe(
            fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring)
        scope = FormalBatchReadJournal.open(fixture.policy_repository,
            registry_manifest_hash=universe.registry_manifest_hash,
            as_of_utc=universe.as_of_utc,
            population=tuple(universe.security_ids),
            required_keys=tuple((sid,) for sid in universe.security_ids))
        scope_args = dict(root=universe.registry_manifest_hash,
                          as_of_utc=universe.as_of_utc,
                          population=tuple(universe.security_ids))
        stale = FormalBatchReadJournal.open(fixture.policy_repository,
            registry_manifest_hash=universe.registry_manifest_hash,
            as_of_utc=universe.as_of_utc,
            population=tuple(universe.security_ids),
            required_keys=(("SH600000",),))
        with patch.object(FormalPolicyFinancialRepository, "_batch_recheck_ticket", lambda *_: None):
            stale.close()
        with self.assertRaises(ValueError):
            stale.checkpoint()
        with self.assertRaises(TypeError):
            copy.copy(scope)
        with self.assertRaises(ValueError):
            _require_current_scope(scope, fixture.policy_repository,
                **dict(scope_args, root="0" * 64))
        other = FormalPolicyRepository(fixture.feature_repository, fixture.context,
            fixture.range_store, registry_signature_verifier=fixture.verifier)
        with self.assertRaises(ValueError):
            _require_current_scope(scope, other, **scope_args)
        thread_errors = []
        # Keep the exception on the worker thread so the test can assert it.
        def cross_thread_read():
            try:
                _require_current_scope(scope, fixture.policy_repository, **scope_args)
            except ValueError as error:
                thread_errors.append(error)
        thread = threading.Thread(target=cross_thread_read)
        thread.start()
        thread.join()
        self.assertEqual(len(thread_errors), 1)
        args = dict(scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry)
        with self.assertRaises(ValueError):
            fixture.policy_repository._build_batch_in_owner_scope(
                fixture.frozen.frozen_input_hash, owner_scope=object(), **args)
        batch, ticket, revoke = fixture.policy_repository._build_batch_in_owner_scope(
            fixture.frozen.frozen_input_hash, owner_scope=scope, **args)
        batch.require_verified()
        self.assertIs(ticket.selected(), batch)
        scope.finalize()
        with self.assertRaises(ValueError):
            fixture.policy_repository._build_batch_in_owner_scope(
                fixture.frozen.frozen_input_hash, owner_scope=scope, **args)
        revoke(batch)
        with self.assertRaises(ValueError):
            batch.require_verified()

    def test_unknown_membership_never_fabricates_five_template_decisions(self):
        fixture = self.fixture()
        batch = fixture.build_policy_batch()
        for item in batch.results:
            self.assertEqual(item.decisions, ())
            self.assertEqual(item.evidence_state, "pending_evidence")
            self.assertEqual(dict(item.dimension_caps), {})
            self.assertEqual(dict(item.pool_prohibitions), {})

    def test_missing_universe_is_failure(self):
        fixture = self.fixture()
        with self.assertRaises(ValueError):
            fixture.policy_repository.build_batch("0" * 64,
                scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry)

    def test_forged_scoring_and_policy_registries_are_rejected(self):
        fixture = self.fixture()
        for name in ("scoring", "policy_registry"):
            original = getattr(fixture, name)
            for impostor in (object(), object.__new__(type(original))):
                setattr(fixture, name, impostor)
                try:
                    with self.subTest(registry=name), self.assertRaises(ValueError):
                        fixture.build_policy_batch()
                finally:
                    setattr(fixture, name, original)

    def test_same_root_foreign_store_range_and_context_are_rejected(self):
        owner, foreign = self.fixture(), self.fixture()
        for context, ranges in ((foreign.context, owner.range_store),
                                (owner.context, foreign.range_store)):
            with self.assertRaises(ValueError):
                repository = self.api.FormalPolicyRepository(owner.feature_repository, context, ranges,
                    registry_signature_verifier=owner.verifier)
                repository.build_batch(owner.frozen.frozen_input_hash,
                    scoring_registry=owner.scoring, policy_registry=owner.policy_registry)

    def test_foreign_signature_root_rejected(self):
        fixture = self.fixture()
        foreign = self.fixture(cyclic=False)
        with self.assertRaises(ValueError):
            fixture.policy_repository.build_batch(fixture.frozen.frozen_input_hash,
                scoring_registry=foreign.scoring, policy_registry=foreign.policy_registry)

    def test_provider_unpublished_assigned_fails_unknown_membership_does_not_fetch(self):
        from ashare_pipeline.formal_metric_batch_guard import FormalMetricCurrentInputProvider
        from ashare_pipeline.formal_feature_repository import FormalFeatureRepository
        fixture = self.fixture()
        provider = FormalMetricCurrentInputProvider(fixture.store)
        feature = FormalFeatureRepository(fixture.store, fixture.files,
            registry_signature_verifier=fixture.verifier, current_input_provider=provider)
        repository = self.api.FormalPolicyRepository(feature, fixture.context, fixture.range_store,
            registry_signature_verifier=fixture.verifier)
        arguments = dict(scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry)
        repository.build_batch(fixture.frozen.frozen_input_hash, **arguments).require_verified()
        fixture.put_industry("SH600000")
        with self.assertRaises(ValueError):
            repository.build_batch(fixture.frozen.frozen_input_hash, **arguments)

    def test_proofs_reject_construction_copy_shadowing_and_cross_batch_composition(self):
        fixture = self.fixture()
        fixture.put_industry("SH600000")
        batch = fixture.build_policy_batch()
        other = fixture.build_policy_batch()
        proofs = (batch, batch.evidence_batch, *batch.results, *batch.results[1].decisions)
        self.assertTrue(batch.results[1].decisions)
        for proof in proofs:
            with self.subTest(proof=type(proof).__name__):
                for copier in (copy.copy, copy.deepcopy):
                    with self.assertRaises(TypeError):
                        copier(proof)
                with self.assertRaises((ValueError, TypeError)):
                    type(proof)(**proof.to_dict())
                with self.assertRaises(ValueError):
                    type(proof).require_official(object.__new__(type(proof)))
                with self.assertRaises((AttributeError, TypeError)):
                    proof.require_official = lambda: None
                with self.assertRaises((AttributeError, TypeError)):
                    type(proof).require_official = lambda self: None
                with self.assertRaises(ValueError):
                    type(proof).require_official(proof.to_dict())
        with self.assertRaises((TypeError, ValueError)):
            self.api.VerifiedPolicyResultBatch(results=(batch.results[0], *other.results[1:]))
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(batch, "results", other.results)

    def test_entry_and_dependency_replacement_fail_closed(self):
        fixture = self.fixture()
        repository = fixture.policy_repository
        batch = fixture.build_policy_batch()
        with patch.object(self.api, "FormalPolicyRepository", object):
            with self.assertRaises(ValueError):
                repository.build_batch(fixture.frozen.frozen_input_hash,
                    scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry)
            with self.assertRaises(ValueError):
                batch.require_verified()
        with patch.object(type(fixture.context), "get_verified_many", lambda *a, **k: {}):
            with self.assertRaises(ValueError):
                fixture.build_policy_batch()

    def test_configuration_missing_and_ambiguous_fail_before_publication(self):
        def missing(documents):
            documents["source"]["range_configs"] = []
        def ambiguous(documents):
            entry = dict(documents["source"]["range_configs"][0])
            entry["retry_base_seconds"] = 2.0
            documents["source"]["range_configs"].append(entry)
        for mutate in (missing, ambiguous):
            with self.subTest(mutate=mutate.__name__), self.assertRaises(ValueError):
                fixture = self.fixture(mutate=mutate)
                fixture.build_policy_batch()

    def test_whole_dependency_graph_replacement_and_repository_copy_fail(self):
        fixture, foreign = self.fixture(), self.fixture()
        for copier in (copy.copy, copy.deepcopy):
            with self.assertRaises(TypeError):
                copier(fixture.policy_repository)
        forged = object.__new__(self.api.FormalPolicyRepository)
        with self.assertRaises(ValueError):
            forged.build_batch(fixture.frozen.frozen_input_hash,
                scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry)
        with self.assertRaises(AttributeError):
            fixture.policy_repository.build_batch = lambda *a, **k: None
        original_feature = dict(vars(fixture.feature_repository))
        original_context = dict(vars(fixture.context))
        try:
            vars(fixture.feature_repository).clear()
            vars(fixture.feature_repository).update(vars(foreign.feature_repository))
            vars(fixture.context).clear()
            vars(fixture.context).update(vars(foreign.context))
            with self.assertRaises(ValueError):
                fixture.build_policy_batch()
        finally:
            vars(fixture.feature_repository).clear()
            vars(fixture.feature_repository).update(original_feature)
            vars(fixture.context).clear()
            vars(fixture.context).update(original_context)

    def test_provider_security_template_and_freeze_cannot_be_spliced(self):
        from ashare_pipeline.formal_metric_batch_guard import FormalMetricCurrentInputProvider
        from ashare_pipeline.formal_feature_repository import FormalFeatureRepository
        from tests.formal_metric_fixtures import FREEZE
        fixture = self.fixture()
        fixture.put_industry("SH600000")
        snapshot = fixture.provider.resolve_current_inputs(security_id="SH600000", as_of_utc=FREEZE,
            template_id="bank", registry_manifest_hash=fixture.bundle.manifest.manifest_hash)
        for changes in (dict(security_id="SZ000001"), dict(template_id="insurance"),
                        dict(as_of_utc="2026-08-30T07:00:00+00:00")):
            provider = FormalMetricCurrentInputProvider(fixture.store)
            provider.publish(replace(snapshot, **changes))
            feature = FormalFeatureRepository(fixture.store, fixture.files,
                registry_signature_verifier=fixture.verifier, current_input_provider=provider)
            repository = self.api.FormalPolicyRepository(feature, fixture.context, fixture.range_store,
                registry_signature_verifier=fixture.verifier)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                repository.build_batch(fixture.frozen.frozen_input_hash,
                    scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry)

    def test_market_recheck_class_replacement_cannot_disable_final_verification(self):
        from ashare_pipeline.formal_policy_market import MarketSelection
        fixture = self.fixture()
        with patch.object(MarketSelection, "recheck", lambda self: None):
            with self.assertRaises(ValueError):
                fixture.build_policy_batch()

    def test_relabeling_a_minted_proof_class_cannot_change_its_authority(self):
        fixture = self.fixture()
        batch = fixture.build_policy_batch()
        result = batch.results[0]
        object.__setattr__(result, "__class__", self.api.PolicyDecision)
        try:
            with self.assertRaises(ValueError):
                result.require_verified()
        finally:
            object.__setattr__(result, "__class__", self.api.PolicyResult)
        result.require_verified()

    def test_calculation_and_deepcopy_dependencies_cannot_be_replaced(self):
        from ashare_pipeline import formal_policy_evaluator, formal_policy_market, formal_range_store

        fixture = self.fixture()
        for owner, name, replacement in (
            (formal_policy_market, "evaluate_window", lambda *args: {}),
            (formal_range_store, "_digest", lambda *args: "0" * 64),
            (formal_policy_evaluator, "copy", object()),
            (formal_policy_evaluator.copy, "deepcopy", lambda value: value),
        ):
            with self.subTest(name=name), patch.object(owner, name, replacement):
                with self.assertRaises(ValueError):
                    fixture.build_policy_batch()


if __name__ == "__main__":
    unittest.main()
