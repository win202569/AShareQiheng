"""Long offline acceptance: genuine official producers, never DTO authority."""
from contextlib import closing
from datetime import datetime, timezone
import unittest


def phase(name):
    print(datetime.now(timezone.utc).isoformat() + ' V9 equivalence: ' + name, flush=True)


class GenuineOfficialEquivalenceTests(unittest.TestCase):
    def test_fresh_inputs_replay_exact_candidate_without_v8_writes(self):
        from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
        from ashare_pipeline.formal_final_repository import FormalFinalRunRepository
        from ashare_pipeline.formal_release_inputs import _ReleaseInputRefresh
        from ashare_pipeline.formal_release_validation import _replay_official_candidate
        from tests.formal_final_scoring_fixtures import FinalScoringFixture
        from tests.test_formal_final_integration import (
            complete_score_history, official_context_coverage,
            official_context_coverage_configuration)
        from tests.test_formal_final_runner import configured_runner, run_arguments, runner_module

        phase('build signed 20-member official fixture')
        f = FinalScoringFixture(peer_count=20, purpose='official', pending_ids=())
        self.addCleanup(f.close)
        phase('fixture database: ' + str(f.db_path))
        f.populate_final_inputs()
        phase('complete real histories and current feature evidence')
        complete_score_history(f, sorted(f.templates))
        phase('audit original official coverage')
        original_coverage = official_context_coverage(f)
        original_coverage.require_official_ready()
        code = original_coverage.to_dict()['workspace_revision']
        runner, runs = configured_runner(runner_module(self), f, code_version=code)
        phase('produce and persist original Stage D official candidate')
        receipt = runner.run_official_candidate(**run_arguments(f, original_coverage))
        self.assertEqual(receipt.status, 'preview_ready')
        before = runs.get_run(receipt.run_id)
        self.assertEqual(before.mode, 'official_candidate')
        self.assertTrue(all(row['state'] in ('formal_scored', 'pool_vetoed')
                            for row in before.statuses))
        phase('reload configured inputs and fresh coverage')
        inputs = FormalFinalScoreInputRepository(f.feature_repository, f.context,
            f.range_store, registry_signature_verifier=f.verifier)
        fresh_runs = FormalFinalRunRepository(f.store, code_version=code)
        _, contract, status_path = official_context_coverage_configuration(f)
        snapshot, scoring, policy, adapter, coverage = _ReleaseInputRefresh(
            state_store=f.store, input_repository=inputs, run_repository=fresh_runs,
            registry_signature_verifier=f.verifier, coverage_contract=contract,
            coverage_contract_verifier=f.verifier, status_path=status_path).refresh(receipt.run_id)
        self.assertIsNot(coverage, original_coverage)
        phase('recompute genuine D1, D2, D3 and pool without persistence')
        raw, changed = _replay_official_candidate(snapshot, run_id=receipt.run_id,
            input_repository=inputs, scoring_registry=scoring, policy_registry=policy,
            valuation_adapter_registry=adapter, coverage_manifest=coverage)
        self.assertEqual(changed, ())
        self.assertEqual(set(raw), {'score_input_batch', 'scorecard_batch',
                                    'eligibility_batch', 'pool_selection_batch'})
        for name, payload in raw.items():
            self.assertEqual(payload, before.artifacts[name], name)
        self.assertEqual(fresh_runs.get_run(receipt.run_id), before)
        with closing(f.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_final_run').fetchone()[0], 1)
            for table in ('formal_release_validation', 'formal_release',
                          'formal_release_preparation', 'formal_release_file', 'formal_release_event'):
                self.assertEqual(connection.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
        phase('exact four-artifact equivalence; unchanged V8; no V9 authority minted')


if __name__ == '__main__':
    unittest.main()
