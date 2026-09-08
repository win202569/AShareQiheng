"""Review regressions for complete-read interval, exact identity and ownership."""

import gc
import copy
import importlib
from dataclasses import replace
from decimal import Decimal
import sqlite3
import sys
import unittest
import weakref

from tests.formal_metric_feature_fixtures import FinancialFixture, METRICS
from tests.formal_metric_fixtures import FREEZE
from ashare_pipeline.formal_feature_repository import FormalFeatureRepository


class Spoof(str):
    def __new__(cls, target):
        result = super().__new__(cls, "forged-selector")
        result.target = target
        return result

    def __eq__(self, other):
        return other == self.target

    def __hash__(self):
        return hash(self.target)


class MetricBatchReviewTests(unittest.TestCase):
    def fixture(self, *, missing=True):
        fixture = FinancialFixture(missing_memberships=missing)
        self.addCleanup(fixture.close)
        api = importlib.import_module("ashare_pipeline.formal_metric_engine")
        repo = api.FormalMetricInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        return fixture, api, repo

    def test_security_and_metric_selectors_reject_hostile_string_subclasses(self):
        fixture, api, repo = self.fixture()
        batch = repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        for sid, mid in ((Spoof("BJ430001"), METRICS[0]), ("BJ430001", Spoof(METRICS[0]))):
            with self.subTest(selector=str(sid)), self.assertRaises(ValueError):
                batch.input_for(sid, mid)
            with self.subTest(selector=str(mid)), self.assertRaises(ValueError):
                api.build_metric_peer_context(batch, security_id=sid, metric_id=mid)

    def test_cached_contexts_do_not_root_their_batch_or_input_proofs(self):
        fixture, api, repo = self.fixture()
        batch = repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        context = api.build_metric_peer_context(batch, security_id="BJ430001", metric_id=METRICS[0])
        batch_ref, context_ref, input_ref = weakref.ref(batch), weakref.ref(context), weakref.ref(batch.inputs[0])
        self.assertIs(context, api.build_metric_peer_context(batch, security_id="BJ430001", metric_id=METRICS[0]))
        del batch
        gc.collect()
        self.assertIsNone(batch_ref())
        self.assertIsNone(input_ref())
        # A detached context remains a historical proof, but cannot score a new batch.
        other = repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        with self.assertRaises(ValueError):
            api.score_metric_percentile(other, context)
        del context
        gc.collect()
        self.assertIsNone(context_ref())

    def test_earlier_member_provider_change_during_final_sweep_rejects_then_recovers(self):
        fixture, api, repo = self.fixture(missing=False)
        count = 0
        def profile(frame, event, result):
            nonlocal count
            if event == "return" and frame.f_code.co_name == "resolve_current_inputs" and getattr(result, "security_id", None) == "SH600000":
                count += 1
                if count == 3:
                    fixture.set_generation("BJ430001", "changed-during-final-sweep")
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(ValueError, "changed during complete batch"):
                repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        finally:
            sys.setprofile(previous)
        self.assertGreaterEqual(count, 3)
        batch = repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        self.assertEqual(batch.feature_states["BJ430001"]["batch_id"], "changed-during-final-sweep")

    def test_earlier_member_database_correction_during_final_sweep_rejects_then_recovers(self):
        fixture, api, repo = self.fixture(missing=False)
        fixture.put_financial("BJ430001", {METRICS[0]: 1})
        count = 0
        def profile(frame, event, result):
            nonlocal count
            if event == "return" and frame.f_code.co_name == "resolve_current_inputs" and getattr(result, "security_id", None) == "SH600000":
                count += 1
                if count == 3:
                    fixture.put_financial("BJ430001", {METRICS[0]: 2}, generation="final-db-correction",
                        updated="2026-04-01T00:00:00+00:00", publish=False)
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(ValueError, "database changed during complete batch"):
                repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        finally:
            sys.setprofile(previous)
        self.assertGreaterEqual(count, 3)
        fixture.publish_current("BJ430001")
        batch = repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        self.assertEqual(batch.feature_states["BJ430001"]["status"], "current_receipt_absent")

    def test_all_pending_factory_rejects_generic_and_copied_providers_but_old_reads_work(self):
        fixture, api, _ = self.fixture()
        for provider in (fixture, object.__new__(type(fixture.provider))):
            feature = FormalFeatureRepository(fixture.store, fixture.files,
                registry_signature_verifier=fixture.verifier, current_input_provider=provider)
            repo = api.FormalMetricInputRepository(feature, fixture.context,
                registry_signature_verifier=fixture.verifier)
            with self.assertRaisesRegex(ValueError, "genuine owned current-input provider"):
                repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
            if provider is fixture:
                self.assertIsNone(feature.select_current_verified_metric_features("BJ430001", FREEZE,
                    template_id="general_nonfinancial", registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
                    required_feature_keys=("general_nonfinancial." + METRICS[0],)))

    def test_canonical_preparation_does_not_hold_the_writer_reservation(self):
        fixture, api, repo = self.fixture()
        observed = 0
        def profile(frame, event, result):
            nonlocal observed
            if (event == "call" and frame.f_code.co_name == "_canonical"
                    and frame.f_code.co_filename.endswith("formal_metric_engine.py")):
                observed += 1
                connection = sqlite3.connect(fixture.db_path, timeout=0, isolation_level=None)
                try:
                    try:
                        connection.execute("BEGIN IMMEDIATE")
                    except sqlite3.OperationalError:
                        self.fail("expensive canonical preparation held the metric writer reservation")
                    connection.rollback()
                finally:
                    connection.close()
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            batch = repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        finally:
            sys.setprofile(previous)
        self.assertGreater(observed, 0)
        batch.require_verified()

    def test_prepared_metric_rows_are_unusable_until_the_complete_batch_is_published(self):
        fixture, api, repo = self.fixture()
        captured = []
        def profile(frame, event, result):
            if event == "return" and frame.f_code.co_name == "mint" and type(result) is api.MetricInput:
                captured.append(result)
                with self.assertRaises(ValueError):
                    result.require_verified()
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            batch = repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        finally:
            sys.setprofile(previous)
        self.assertEqual(len(captured), 3)
        for proof in captured:
            proof.require_verified()
        self.assertIs(batch.inputs[0], captured[0])

    def test_failed_finalization_revokes_prepared_proofs_and_recovers_publication(self):
        for failure in ("provider", "closed_connection"):
            fixture, api, repo = self.fixture()
            captured = []
            def profile(frame, event, result):
                if (event == "return" and type(result) is api.MetricInputBatch and frame.f_back is not None
                        and frame.f_back.f_code.co_name == "finalize" and not captured):
                    captured.append(result)
                    if failure == "provider":
                        with self.assertRaises(ValueError):
                            fixture.set_generation("SH600099", "during-publication")
                    else:
                        # Close the actual observer to exercise a real SQLite
                        # rollback failure, without replacing a trusted reader.
                        frame.f_back.f_locals["observer"].close()
            previous = sys.getprofile()
            try:
                sys.setprofile(profile)
                with self.subTest(failure=failure), self.assertRaises((ValueError, sqlite3.Error)):
                    repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
            finally:
                sys.setprofile(previous)
            self.assertEqual(len(captured), 1)
            with self.assertRaises(ValueError):
                captured[0].require_verified()
            fixture.set_generation("SH600099", "recovered-publication")
            repo.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],)).require_verified()


class DerivedProofPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = FinancialFixture(population=True)
        cls.addClassCleanup(cls.fixture.close)
        # Genuine complete population with one independently controlled selected
        # FY2025 metric; every source/industry/feature receipt is persisted.
        for index, member in enumerate(cls.fixture.industry["memberships"]):
            sid = member["security_id"]
            cls.fixture.put_industry(sid)
            cls.fixture.put_financial(sid, {METRICS[0]: index - 1})
            cls.fixture.persist_features(sid)
        cls.api = importlib.import_module("ashare_pipeline.formal_metric_engine")
        cls.repo = cls.api.FormalMetricInputRepository(cls.fixture.feature_repository, cls.fixture.context,
            registry_signature_verifier=cls.fixture.verifier)

    def build(self):
        return self.repo.build_batch(self.fixture.frozen.frozen_input_hash,
            scoring_registry=self.fixture.scoring, metric_ids=(METRICS[0],))

    def test_failed_finalization_revokes_derived_context_and_actual_score(self):
        captured = []
        snapshot = self.fixture.provider.resolve_current_inputs(security_id="BJ430001", as_of_utc=FREEZE,
            template_id="general_nonfinancial", registry_manifest_hash=self.fixture.bundle.manifest.manifest_hash)
        def profile(frame, event, result):
            if (event == "return" and type(result) is self.api.MetricInputBatch and frame.f_back is not None
                    and frame.f_back.f_code.co_name == "finalize" and not captured):
                context = self.api.build_metric_peer_context(result, security_id="BJ430001", metric_id=METRICS[0])
                score = self.api.score_metric_percentile(result, context)
                self.assertEqual((context.peer_count, score.percentile), (20, Decimal("2.5")))
                captured.extend((result, context, score))
                with self.assertRaises(ValueError):
                    self.fixture.provider.publish(replace(snapshot, batch_id="revoked-publication"))
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(ValueError, "changed during complete batch finalization"):
                self.build()
        finally:
            sys.setprofile(previous)
        self.assertEqual(len(captured), 3)
        for proof in captured:
            for method in ("require_verified", "canonical_bytes", "to_dict"):
                with self.subTest(proof=type(proof).__name__, method=method), self.assertRaises(ValueError):
                    getattr(proof, method)()

    def test_successful_detached_context_score_and_cohort_cache_remain_valid(self):
        batch = self.build()
        context = self.api.build_metric_peer_context(batch, security_id="BJ430001", metric_id=METRICS[0])
        other = self.api.build_metric_peer_context(batch, security_id="SH600000", metric_id=METRICS[0])
        self.assertIs(context, self.api.build_metric_peer_context(batch, security_id="BJ430001", metric_id=METRICS[0]))
        self.assertIs(context.peer_security_ids, other.peer_security_ids)
        score = self.api.score_metric_percentile(batch, context)
        self.assertEqual((score.peer_count, score.percentile), (20, Decimal("2.5")))
        context_bytes, score_bytes = context.canonical_bytes(), score.canonical_bytes()
        owner = weakref.ref(batch)
        del batch
        gc.collect()
        self.assertIsNone(owner())
        for proof, canonical in ((context, context_bytes), (score, score_bytes)):
            proof.require_verified()
            self.assertEqual(proof.canonical_bytes(), canonical)
            self.assertEqual(proof.to_dict()["security_id"], "BJ430001")


class OwnedProviderGuardTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_metric_batch_guard"), "owned batch guard is missing")
        self.api = importlib.import_module("ashare_pipeline.formal_metric_batch_guard")
        self.fixture = FinancialFixture(missing_memberships=True)
        self.addCleanup(self.fixture.close)
        self.provider = self.api.FormalMetricCurrentInputProvider(self.fixture.store)

    def test_published_complete_inputs_are_detached_and_unknown_requests_fail(self):
        request = dict(security_id="BJ430001", as_of_utc=FREEZE, template_id="general_nonfinancial",
            registry_manifest_hash=self.fixture.bundle.manifest.manifest_hash)
        snapshot = self.fixture.resolve_current_inputs(**request)
        with self.assertRaises(ValueError):
            self.provider.resolve_current_inputs(**request)
        with self.assertRaises(ValueError):
            self.provider.publish(replace(snapshot, complete=False))
        self.provider.publish(snapshot)
        object.__setattr__(snapshot, "batch_id", "mutated-after-publication")
        result = self.provider.resolve_current_inputs(**request)
        self.assertEqual(result.batch_id, "generation-1")
        object.__setattr__(result, "batch_id", "mutated-read")
        self.assertEqual(self.provider.resolve_current_inputs(**request).batch_id, "generation-1")

    def test_generic_and_copied_provider_cannot_open_a_guard(self):
        for candidate in (self.fixture, object.__new__(type(self.provider))):
            with self.assertRaises(ValueError):
                with self.api._metric_batch_guard(candidate, self.fixture.store):
                    self.fail("a forged provider opened a guard")
        with self.assertRaises(TypeError):
            copy.copy(self.provider)

    def test_guard_observes_other_connection_commits_and_releases_after_rejection(self):
        called = []
        with self.api._metric_batch_guard(self.provider, self.fixture.store) as guard:
            self.fixture.sql("UPDATE formal_collection_task SET updated_at='2026-09-08T00:00:00+00:00'")
            with self.assertRaisesRegex(ValueError, "database changed during complete batch"):
                guard.finalize(lambda: called.append(True))
        self.assertEqual(called, [])
        with self.api._metric_batch_guard(self.provider, self.fixture.store) as guard:
            self.assertEqual(guard.finalize(lambda: "stable"), "stable")

    def test_finalization_fences_writers_and_always_releases_the_connection(self):
        def while_fenced():
            connection = sqlite3.connect(self.fixture.db_path, timeout=0, isolation_level=None)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("BEGIN IMMEDIATE")
            finally:
                connection.close()
            return "minted"
        with self.api._metric_batch_guard(self.provider, self.fixture.store) as guard:
            self.assertEqual(guard.finalize(while_fenced), "minted")
        connection = sqlite3.connect(self.fixture.db_path, timeout=0, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
        finally:
            connection.close()

    def test_reentrant_publication_cannot_be_swallowed_inside_finalization(self):
        snapshot = self.fixture.resolve_current_inputs(security_id="BJ430001", as_of_utc=FREEZE,
            template_id="general_nonfinancial", registry_manifest_hash=self.fixture.bundle.manifest.manifest_hash)
        self.provider.publish(snapshot)
        def intercepted_mint():
            with self.assertRaises(ValueError):
                self.provider.publish(replace(snapshot, batch_id="reentrant"))
            return "must-not-escape"
        with self.api._metric_batch_guard(self.provider, self.fixture.store) as guard:
            with self.assertRaisesRegex(ValueError, "changed during complete batch finalization"):
                guard.finalize(intercepted_mint)
        with self.api._metric_batch_guard(self.provider, self.fixture.store) as guard:
            self.assertEqual(guard.finalize(lambda: "recovered"), "recovered")


if __name__ == "__main__":
    unittest.main()
