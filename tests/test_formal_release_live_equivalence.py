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
        phase('configure trusted input refresh and held replay')
        inputs = FormalFinalScoreInputRepository(f.feature_repository, f.context,
            f.range_store, registry_signature_verifier=f.verifier)
        fresh_runs = FormalFinalRunRepository(f.store, code_version=code)
        _, contract, status_path = official_context_coverage_configuration(f)
        service = _ReleaseInputRefresh(
            state_store=f.store, input_repository=inputs, run_repository=fresh_runs,
            registry_signature_verifier=f.verifier, coverage_contract=contract,
            coverage_contract_verifier=f.verifier, status_path=status_path)
        import inspect
        from ashare_pipeline.formal_release_validation import _recheck_official_live_evidence
        # Test-only observation of a token minted by genuine replay, not a fixture token.
        active_scopes = inspect.getclosurevars(_recheck_official_live_evidence).nonlocals['active_scopes']
        def owned_token():
            matches = [row[0] for row in active_scopes.values()
                       if row[1] == receipt.run_id and row[2] is inputs]
            self.assertEqual(len(matches), 1)
            return matches[0]
        phase('refresh official coverage and recompute D1, D2, D3 and pool without persistence')
        with service.hold_evidence(receipt.run_id) as (raw, evidence_bytes):
            live_token = owned_token()
            _recheck_official_live_evidence(live_token, run_id=receipt.run_id, input_repository=inputs)
            import json
            import hashlib
            from ashare_pipeline.formal_release_types import canonical_release_bytes
            evidence = json.loads(evidence_bytes)
            self.assertEqual(evidence['schema'], 'formal-release-configured-evidence-v1')
            self.assertEqual(evidence['job_evidence']['schema'], 'formal-release-job-evidence-v1')
            self.assertEqual(evidence['candidate']['run_id'], receipt.run_id)
            self.assertEqual(evidence['candidate']['coverage_manifest_hash'], before.header['coverage_manifest_hash'])
            replay = evidence['replay_evidence']
            self.assertEqual(evidence['coverage_manifest_hash'], replay['coverage_manifest_hash'])
            self.assertEqual(replay['source_dependency_hash'], hashlib.sha256(
                canonical_release_bytes(replay['sources'])).hexdigest())
            self.assertEqual(set(replay['sources']['upstream']), {'base','policy','valuation'})
            self.assertEqual(len(replay['sources']['registry']['roles']), 10)
            self.assertEqual(evidence['source_commitment']['replay_source_dependency_hash'],
                             replay['source_dependency_hash'])
            self.assertEqual(evidence['source_commitment']['job_evidence_hash'], hashlib.sha256(
                canonical_release_bytes(evidence['job_evidence'])).hexdigest())
            self.assertEqual(evidence['source_dependency_hash'], hashlib.sha256(
                canonical_release_bytes(evidence['source_commitment'])).hexdigest())
            for name, payload in raw.items():
                self.assertEqual(replay['sources']['computation'][name], hashlib.sha256(payload).hexdigest())
            phase('fresh coverage and complete source commitments verified')
            self.assertEqual(set(raw), {'score_input_batch', 'scorecard_batch',
                                        'eligibility_batch', 'pool_selection_batch'})
            for name, payload in raw.items():
                self.assertEqual(payload, before.artifacts[name], name)
            phase('render complete deterministic package from genuine replay bytes')
            import hashlib
            from ashare_pipeline.formal_release_rendering import _render_release_package
            from ashare_pipeline.formal_release_types import canonical_release_bytes
            identity = {key: before.header[key] for key in ('contract_version',
                'input_manifest_hash','result_hash','registry_manifest_hash',
                'frozen_input_hash','universe_hash')}
            package = _render_release_package(raw, candidate_identity=identity)
            manifest = json.loads(package['release_manifest.json'])
            self.assertEqual(list(package)[-1], 'release_manifest.json')
            self.assertEqual(manifest['counts']['universe'], 20)
            self.assertEqual(manifest['counts']['payload_files'], len(package)-1)
            self.assertEqual({item['path'] for item in manifest['files']},
                             set(package)-{'release_manifest.json'})
            for item in manifest['files']:
                self.assertEqual(item['sha256'], hashlib.sha256(package[item['path']]).hexdigest())
                self.assertEqual(item['byte_size'], len(package[item['path']]))
            for card in json.loads(raw['scorecard_batch'])['cards']:
                self.assertEqual(package['audit_cards/'+card['security_id']+'.json'],
                                 canonical_release_bytes(card))
            phase('rendered payload hashes and complete audit-card lineage verified')
            # Returned data must not alias the private baseline used on exit.
            raw.clear()
        with self.assertRaisesRegex(ValueError, 'live replay'):
            _recheck_official_live_evidence(live_token, run_id=receipt.run_id, input_repository=inputs)
        self.assertEqual(fresh_runs.get_run(receipt.run_id), before)
        with closing(f.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_final_run').fetchone()[0], 1)
            for table in ('formal_release_validation', 'formal_release',
                          'formal_release_preparation', 'formal_release_file', 'formal_release_event'):
                self.assertEqual(connection.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
        phase('exact four-artifact equivalence; unchanged V8; no V9 authority minted')

        phase('retained source guard rejects a database change before leaving')
        source_change_committed = False
        precheck_rejected = False
        try:
            with self.assertRaisesRegex(ValueError, 'changed|revoked'):
                with service.hold_replay(receipt.run_id):
                    with closing(f.store._connect()) as connection:
                        connection.execute('CREATE TABLE release_guard_source_probe(value TEXT)')
                        connection.commit()
                    source_change_committed = True
                    changed_token = owned_token()
                    with self.assertRaisesRegex(ValueError, 'changed|revoked'):
                        _recheck_official_live_evidence(changed_token, run_id=receipt.run_id,
                                                       input_repository=inputs)
                    precheck_rejected = True
        finally:
            with closing(f.store._connect()) as connection:
                connection.execute('DROP TABLE IF EXISTS release_guard_source_probe')
                connection.commit()
        self.assertTrue(source_change_committed, 'must reject on exit after source mutation')
        self.assertTrue(precheck_rejected, 'must reject before caller can perform a side effect')
        with self.assertRaisesRegex(ValueError, 'live replay'):
            _recheck_official_live_evidence(changed_token, run_id=receipt.run_id, input_repository=inputs)
        self.assertEqual(fresh_runs.get_run(receipt.run_id), before)



    def test_configured_validator_returns_twelve_audit_gates_without_writes(self):
        from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
        from ashare_pipeline.formal_final_repository import FormalFinalRunRepository
        from ashare_pipeline.formal_release_validator import FormalReleaseValidator
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
        phase('configure trusted input refresh and held replay')
        inputs = FormalFinalScoreInputRepository(f.feature_repository, f.context,
            f.range_store, registry_signature_verifier=f.verifier)
        fresh_runs = FormalFinalRunRepository(f.store, code_version=code)
        _, contract, status_path = official_context_coverage_configuration(f)
        service = FormalReleaseValidator(
            state_store=f.store, input_repository=inputs, run_repository=fresh_runs,
            registry_signature_verifier=f.verifier, coverage_contract=contract,
            coverage_contract_verifier=f.verifier, status_path=status_path)
        phase('refresh official coverage and recompute D1, D2, D3 and pool without persistence')
        phase('run configured audit validator including bound renderer and all twelve gates')
        result = service.validate(receipt.run_id)
        import hashlib
        import json
        from ashare_pipeline.formal_release_types import (
            REQUIRED_RELEASE_GATE_NAMES, canonical_validation_bytes)
        from ashare_pipeline.formal_release_rendering import _render_release_package
        self.assertEqual(result.run_id, receipt.run_id)
        self.assertEqual(result.purpose, 'audit')
        self.assertEqual(result.schema_version, 9)
        self.assertEqual(tuple(gate.name for gate in result.gates), REQUIRED_RELEASE_GATE_NAMES)
        self.assertTrue(all(gate.passed and gate.evidence_hashes and not gate.reason_codes for gate in result.gates))
        self.assertEqual(result.input_manifest_hash, before.header['input_manifest_hash'])
        self.assertEqual(result.result_hash, before.header['result_hash'])
        self.assertEqual(result.code_version, code)
        diagnostics = json.loads(canonical_validation_bytes(result))
        self.assertEqual(diagnostics['purpose'], 'audit')
        self.assertNotIn('signature', diagnostics)
        identity = {key:before.header[key] for key in ('contract_version','input_manifest_hash',
            'result_hash','registry_manifest_hash','frozen_input_hash','universe_hash')}
        package = _render_release_package({name:before.artifacts[name] for name in
            ('score_input_batch','scorecard_batch','eligibility_batch','pool_selection_batch')},
            candidate_identity=identity)
        gates = {gate.name:gate for gate in result.gates}
        self.assertEqual(gates['artifact_renderability'].evidence_hashes,
            (hashlib.sha256(package['release_manifest.json']).hexdigest(),))
        self.assertEqual(gates['official_coverage'].evidence_hashes, (result.coverage_manifest_hash,))
        self.assertEqual(gates['source_identity_temporal'].evidence_hashes, (result.source_dependency_hash,))
        self.assertEqual(fresh_runs.get_run(receipt.run_id), before)
        with closing(f.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_final_run').fetchone()[0],1)
            for table in ('formal_release_validation','formal_release','formal_release_preparation',
                          'formal_release_file','formal_release_event'):
                self.assertEqual(connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        phase('all twelve audit gates verified; unchanged V8 and no V9 writes or publication grant')


    def test_configured_audit_persists_independently_verified_signature_without_publication(self):
        from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
        from ashare_pipeline.formal_final_repository import FormalFinalRunRepository
        from ashare_pipeline.formal_release_validator import FormalReleaseValidator
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
        phase('configure trusted input refresh and held replay')
        inputs = FormalFinalScoreInputRepository(f.feature_repository, f.context,
            f.range_store, registry_signature_verifier=f.verifier)
        fresh_runs = FormalFinalRunRepository(f.store, code_version=code)
        _, contract, status_path = official_context_coverage_configuration(f)
        from tests.test_formal_release_audit import TriggerOnceAuditSigner, AuditVerifier
        service = FormalReleaseValidator(
            state_store=f.store, input_repository=inputs, run_repository=fresh_runs,
            registry_signature_verifier=f.verifier, coverage_contract=contract,
            coverage_contract_verifier=f.verifier, status_path=status_path,
            release_signer=TriggerOnceAuditSigner(f.store), release_signature_verifier=AuditVerifier(),
            release_key_id='isolated-audit')
        phase('refresh official coverage and recompute D1, D2, D3 and pool without persistence')
        phase('run configured signed audit and persist only audit evidence')
        with self.assertRaisesRegex(ValueError, 'schema'):
            service.audit(receipt.run_id)
        with closing(f.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_release_validation').fetchone()[0], 0)
            self.assertIsNotNone(connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='erase_audit'").fetchone())
            connection.execute('DROP TRIGGER erase_audit')
            connection.commit()
        self.assertEqual(fresh_runs.get_run(receipt.run_id), before)
        from tests.formal_release_refresh_fixtures import refresh_status_after_audit_fixture_cleanup
        refresh_status_after_audit_fixture_cleanup(f, contract=contract, status_path=status_path)
        phase('signer-installed trigger rejected; fixture status refreshed after cleanup; retry with fresh validation')
        audit_hash = service.audit(receipt.run_id)
        from ashare_pipeline.formal_release_types import (load_validation_bytes,
            verify_release_signature, VALIDATION_DOMAIN)
        with closing(f.store._connect()) as connection:
            row = dict(connection.execute('SELECT * FROM formal_release_validation WHERE validation_hash=?',
                                          (audit_hash,)).fetchone())
        raw_audit = row['payload_json'].encode('utf-8')
        import hashlib
        self.assertEqual(hashlib.sha256(raw_audit).hexdigest(), audit_hash)
        self.assertEqual(row['purpose'], 'audit')
        self.assertEqual(row['passed'], 1)
        self.assertEqual(row['run_id'], receipt.run_id)
        self.assertTrue(row['created_at'])
        verify_release_signature(raw_audit, signature=row['signature'], key_id=row['key_id'],
            expected_key_id='isolated-audit', domain=VALIDATION_DOMAIN, verifier=AuditVerifier())
        result = load_validation_bytes(raw_audit)
        self.assertEqual(row['release_identity_hash'], result.release_identity_hash)
        import hashlib
        import json
        from ashare_pipeline.formal_release_types import (
            REQUIRED_RELEASE_GATE_NAMES, canonical_validation_bytes)
        from ashare_pipeline.formal_release_rendering import _render_release_package
        self.assertEqual(result.run_id, receipt.run_id)
        self.assertEqual(result.purpose, 'audit')
        self.assertEqual(result.schema_version, 9)
        self.assertEqual(tuple(gate.name for gate in result.gates), REQUIRED_RELEASE_GATE_NAMES)
        self.assertTrue(all(gate.passed and gate.evidence_hashes and not gate.reason_codes for gate in result.gates))
        self.assertEqual(result.input_manifest_hash, before.header['input_manifest_hash'])
        self.assertEqual(result.result_hash, before.header['result_hash'])
        self.assertEqual(result.code_version, code)
        diagnostics = json.loads(canonical_validation_bytes(result))
        self.assertEqual(diagnostics['purpose'], 'audit')
        self.assertNotIn('signature', diagnostics)
        identity = {key:before.header[key] for key in ('contract_version','input_manifest_hash',
            'result_hash','registry_manifest_hash','frozen_input_hash','universe_hash')}
        package = _render_release_package({name:before.artifacts[name] for name in
            ('score_input_batch','scorecard_batch','eligibility_batch','pool_selection_batch')},
            candidate_identity=identity)
        gates = {gate.name:gate for gate in result.gates}
        self.assertEqual(gates['artifact_renderability'].evidence_hashes,
            (hashlib.sha256(package['release_manifest.json']).hexdigest(),))
        self.assertEqual(gates['official_coverage'].evidence_hashes, (result.coverage_manifest_hash,))
        self.assertEqual(gates['source_identity_temporal'].evidence_hashes, (result.source_dependency_hash,))
        self.assertEqual(fresh_runs.get_run(receipt.run_id), before)
        with closing(f.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_final_run').fetchone()[0],1)
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_release_validation').fetchone()[0],1)
            for table in ('formal_release','formal_release_preparation',
                          'formal_release_file','formal_release_event'):
                self.assertEqual(connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        phase('signed audit independently verified; unchanged V8; one audit row; zero publication rows')


if __name__ == '__main__':
    unittest.main()
