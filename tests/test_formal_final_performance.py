"""Deterministic structural budgets; timings are diagnostic, never hard limits."""

import sys
import hashlib
import inspect
import json
import unittest
from collections import Counter
from types import CodeType

from ashare_pipeline.formal_financial_features import build_formal_feature_bundle
from ashare_pipeline.formal_final_score_inputs import PolicyAdjustedScoreInputBatch
from ashare_pipeline.formal_registry_manifest import FormalRegistryBundleLoader
from ashare_pipeline import formal_metric_engine, formal_pool, formal_valuation_engine

from tests.test_formal_final_integration import genuine_chain
from tests.test_formal_final_runner import configured_runner, run_arguments, runner_module


class StageDObserver:
    """Read-only profiler: no authority monkeypatching or validity shortcuts."""

    def __init__(self, module, receipt):
        self.module = module
        self.events = Counter()
        self.source_parses = Counter()
        self.cohort_sorts = Counter()
        self.pool_sorts = Counter()
        self.valuation_summary = None
        self.valuation_sources = set()
        record = inspect.getclosurevars(PolicyAdjustedScoreInputBatch.require_verified).nonlocals["record"]
        retained = inspect.getclosurevars(record).nonlocals["proofs"][id(receipt.input_batch)][5]
        self.checkpoint_code = retained[3][0].recheck.__func__.__code__
        self.metric_score_code = formal_metric_engine.score_metric_percentile.__code__
        self.rank_code = formal_valuation_engine._rank_valuation_values.__code__
        self.valuation_code = formal_valuation_engine.FormalValuationRepository.build_batch.__code__
        self.commit_code = module.FormalFinalRunRepository.commit_complete_run.__code__
        self.pool_scan_code = next(code for code in formal_pool._select_detached_rows.__code__.co_consts
            if type(code) is CodeType and code.co_name == "scan")
        self.names = {FormalRegistryBundleLoader.load.__code__: "registry_loads",
            build_formal_feature_bundle.__code__: "financial_rederivations",
            self.checkpoint_code: "source_checkpoint_rechecks"}
        self.codes_by_id = {id(code): (code, name) for code, name in self.names.items()}
        # Zero has meaning here because the exact producer code is observed.
        self.events.update(dict.fromkeys(self.names.values(), 0))

    def phase(self, frame):
        """Producer code locations distinguish construction from final validation."""
        while frame is not None:
            if frame.f_code is self.valuation_code:
                return "stage_c"
            if frame.f_code is self.module.build_final_score_card_batch.__code__:
                return "d2"
            if frame.f_code is self.module.build_formal_eligibility_batch.__code__:
                return "d3"
            if frame.f_code is self.commit_code:
                return "commit"
            frame = frame.f_back
        return "d1_or_orchestration"

    def __call__(self, frame, event, arg):
        if event == "call":
            target = self.codes_by_id.get(id(frame.f_code))
            if target is not None and frame.f_code is target[0]:
                self.events[target[1]] += 1
            if frame.f_code is json.loads.__code__:
                raw = frame.f_locals.get("s")
                if type(raw) is bytes:
                    raw = raw.decode("utf-8")
                if type(raw) is str and any('"schema_version":"' + schema + '"' in raw
                        for schema in ("formal-score-input-batch-v1", "formal-metric-input-batch-v1",
                                       "formal-policy-result-batch-v1", "policy-adjusted-valuation-batch-v1")):
                    digest = hashlib.sha256(raw.encode()).hexdigest()
                    self.source_parses[(self.phase(frame), digest)] += 1
            if frame.f_code is self.rank_code:
                cohort = frame.f_back.f_locals.get("cohort_key")
                self.cohort_sorts[("C", cohort)] += 1
        elif event == "c_call" and arg is sorted:
            if frame.f_code is self.metric_score_code:
                # Cohort hashes already bind canonical batch identity; object
                # IDs would hide duplicate sorts of an equivalent fresh batch.
                self.cohort_sorts[("non_V", frame.f_locals["cohort"])] += 1
            elif frame.f_code is self.pool_scan_code:
                self.pool_sorts[frame.f_locals["pool"]] += 1
        elif event == "return" and frame.f_code is self.valuation_code and arg is not None:
            # Captured return locals are read without calling a producer or verifier.
            summary = frame.f_locals.get("ranking_summary")
            if summary is not None:
                self.valuation_summary = dict(summary)
            for key in ("base_bytes", "policy_bytes"):
                raw = frame.f_locals.get(key)
                if type(raw) is bytes:
                    self.valuation_sources.add(hashlib.sha256(raw).hexdigest())

    def __enter__(self):
        self.previous = sys.getprofile()
        sys.setprofile(self)
        return self

    def __exit__(self, *_):
        sys.setprofile(self.previous)

    def summary(self):
        return dict(events=dict(self.events), source_parse_counts=[
            dict(stage=stage, source_sha256=digest, parses=count)
            for (stage, digest), count in sorted(self.source_parses.items())],
            cohort_sorts=list(self.cohort_sorts.values()), pool_sorts=dict(self.pool_sorts),
            stage_c=self.valuation_summary)


class RunnerPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.module = runner_module(self)

    def test_each_stage_is_built_once_and_diagnostics_do_not_change_result_hash(self):
        fixture, _, _, coverage, prior = genuine_chain(self, 20)
        runner, repository = configured_runner(self.module, fixture)
        from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
        from ashare_pipeline.formal_final_repository import FormalFinalRunRepository
        codes = {FormalFinalScoreInputRepository.build_batch.__code__: "d1",
            self.module.build_final_score_card_batch.__code__: "d2",
            self.module.build_formal_eligibility_batch.__code__: "eligibility",
            self.module.select_formal_pools.__code__: "pools",
            FormalFinalRunRepository.commit_complete_run.__code__: "append"}
        before = repository.list_runs_by_input_manifest(prior.input_manifest_hash)
        calls = dict.fromkeys(codes.values(), 0)
        codes_by_id = {id(code): (code, name) for code, name in codes.items()}
        previous = sys.getprofile()
        def observe(frame, event, arg):
            if event == "call":
                target = codes_by_id.get(id(frame.f_code))
                if target is not None and frame.f_code is target[0]:
                    calls[target[1]] += 1
        sys.setprofile(observe)
        try:
            receipt = runner.run_preview(**run_arguments(fixture, coverage))
        finally:
            sys.setprofile(previous)
        self.assertEqual(calls, dict(d1=1, d2=1, eligibility=1, pools=1, append=1))
        after = repository.list_runs_by_input_manifest(receipt.input_manifest_hash)
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(receipt.result_hash, prior.result_hash)
        diagnostics = runner.last_diagnostics
        self.assertEqual(diagnostics.counts["members"], 20)
        self.assertEqual(diagnostics.counts["pool_orderings"], 2)
        self.assertEqual(diagnostics.counts["d1_builds"], 1)
        self.assertEqual(sum(diagnostics.status_counts.values()), 20)
        self.assertEqual(set(diagnostics.stage_seconds),
            {"identity", "d1", "d2", "d3", "final_recheck", "commit"})
        self.assertTrue(all(value >= 0 for value in diagnostics.stage_seconds.values()))
        self.assertEqual(repository.get_run(receipt.run_id).result_hash, prior.result_hash)

    def test_source_batch_parses_and_cohort_sorts_have_structural_bounds(self):
        fixture, _, _, coverage, prior = genuine_chain(self, 23)
        runner, _ = configured_runner(self.module, fixture)
        with StageDObserver(self.module, prior) as observed:
            receipt = runner.run_preview(**run_arguments(fixture, coverage))
        self.assertEqual(receipt.result_hash, prior.result_hash)
        self.assertIsNotNone(observed.valuation_summary)
        self.assertTrue(observed.cohort_sorts)
        self.assertTrue(all(count <= 1 for count in observed.cohort_sorts.values()))
        self.assertEqual(observed.pool_sorts, {"strong": 1, "wait": 1})
        # Stage C's full input parsing occurs once in prepare_adjusted_rows.
        self.assertEqual(len(observed.valuation_sources), 2)
        for digest in observed.valuation_sources:
            self.assertLessEqual(observed.source_parses[("stage_c", digest)], 1)
        self.assertTrue(observed.source_parses)
        self.assertTrue(all(count <= 1 for count in observed.source_parses.values()),
            observed.summary())
        self.assertTrue(observed.events["registry_loads"])
        self.assertTrue(observed.events["source_checkpoint_rechecks"])
        print("Task 11 profiler:", json.dumps(observed.summary(), sort_keys=True), flush=True)

    def test_rebuild_appends_once_and_revalidates_even_when_no_input_changed(self):
        fixture, _, _, coverage, prior = genuine_chain(self, 23)
        runner, repository = configured_runner(self.module, fixture)
        before = repository.get_run(prior.run_id)
        receipt = runner.rebuild_affected(**run_arguments(fixture, coverage),
            prior_run_id=prior.run_id, prior_input_manifest_hash=prior.input_manifest_hash)
        self.assertNotEqual(receipt.run_id, prior.run_id)
        self.assertEqual(receipt.result_hash, prior.result_hash)
        self.assertEqual(repository.get_run(prior.run_id), before)
        self.assertFalse(runner.last_diagnostics.rebuild_plan.rescan_pools)
        self.assertEqual(runner.last_diagnostics.counts["trusted_diffs"], 1)
        self.assertGreaterEqual(runner.last_diagnostics.counts["identity_rechecks"], 2)


if __name__ == "__main__":
    unittest.main()
