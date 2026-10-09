"""Trusted input refresh is read-only and cannot authorize publication."""
from contextlib import closing
import copy
import unittest

from tests.formal_final_scoring_fixtures import FinalScoringFixture
from ashare_pipeline.formal_final_repository import FormalFinalRunRepository, _insert_rows
from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
from tests.test_formal_scoring_registry import canonical


class ReleaseInputRefreshTests(unittest.TestCase):
    def setUp(self):
        import ashare_pipeline.formal_release_inputs as module
        self.module = module
        self.fixture = FinalScoringFixture(peer_count=3, purpose='official')
        self.addCleanup(self.fixture.close)
        f = self.fixture
        self.inputs = FormalFinalScoreInputRepository(f.feature_repository, f.context,
            f.range_store, registry_signature_verifier=f.verifier)
        self.runs = FormalFinalRunRepository(f.store, code_version='a' * 40)
        raw = canonical(dict(schema_version='formal-coverage-contract-v1', purpose='official',
            registry_manifest_hash=f.frozen.registry_manifest_hash,
            frozen_input_hash=f.frozen.frozen_input_hash, requirements=[]))
        self.configuration = dict(state_store=f.store, input_repository=self.inputs,
            run_repository=self.runs, registry_signature_verifier=f.verifier,
            coverage_contract=dict(canonical_json=raw, signature=f.verifier.sign(raw),
                                   key_id=f.bundle.manifest.key_id),
            coverage_contract_verifier=f.verifier, status_path=f.root / 'not-created.json')

    def service(self, **changes):
        return self.module._ReleaseInputRefresh(**dict(self.configuration, **changes))

    def test_missing_run_is_rejected_without_writes_or_status_creation(self):
        with self.assertRaisesRegex(ValueError, 'candidate.*not found'):
            self.service().refresh('absent')
        self.assertFalse(self.configuration['status_path'].exists())
        with closing(self.fixture.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_final_run').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_release_validation').fetchone()[0], 0)

    def test_test_preview_is_rejected_through_real_historical_reader(self):
        from tests.test_formal_final_repository import FormalFinalRecoveryBoundaryTests
        fixture = FormalFinalRecoveryBoundaryTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with closing(self.fixture.store._connect()) as connection:
            for name, rows in fixture.expected.items():
                if rows:
                    _insert_rows(connection, name, rows, tuple(rows[0]))
            connection.commit()
        with self.assertRaisesRegex(ValueError, 'official.*preview_ready'):
            self.service().refresh('test')

    def test_selector_is_only_nonempty_run_id_and_has_no_evidence_overrides(self):
        service = self.service()
        for selector in ('', ' ', object(), {'run_id': 'original'}):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                service.refresh(selector)
        with self.assertRaises(TypeError):
            service.refresh('original', coverage_manifest=object())
        with self.assertRaises(TypeError):
            service.refresh('original', skip_official=True)

    def test_copied_repository_and_foreign_store_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'constructor|registered|ownership'):
            self.service(run_repository=copy.copy(self.runs))
        other = FinalScoringFixture(peer_count=3, purpose='official')
        self.addCleanup(other.close)
        with self.assertRaisesRegex(ValueError, 'ownership'):
            self.service(state_store=other.store)

    def test_service_cannot_be_copied_reconstructed_or_reconfigured(self):
        service = self.service()
        with self.assertRaises(TypeError):
            copy.copy(service)
        forged = object.__new__(type(service))
        with self.assertRaisesRegex(ValueError, 'configuration'):
            forged.refresh('absent')
        with self.assertRaises(ValueError):
            service.__init__(**self.configuration)

    def test_instance_reader_replacement_is_rejected(self):
        service = self.service()
        self.runs.get_run = lambda run_id: None
        with self.assertRaisesRegex(ValueError, 'entry point'):
            service.refresh('absent')

    def test_configuration_method_code_replacement_is_rejected(self):
        service = self.service()
        method = type(service).refresh
        original = method.__code__

        def counterfeit(self, run_id):
            return None

        try:
            method.__code__ = counterfeit.__code__.replace(co_freevars=original.co_freevars)
            with self.assertRaisesRegex(ValueError, 'authority|entry point'):
                service.refresh('absent')
        finally:
            method.__code__ = original

    def test_configured_verifier_replacement_is_rejected(self):
        service = self.service()
        verifier = self.fixture.verifier
        try:
            verifier.verify = lambda *args, **kwargs: True
            with self.assertRaisesRegex(ValueError, 'verifier'):
                service.refresh('absent')
        finally:
            del verifier.verify

    def test_contract_is_detached_and_noncanonical_or_extra_controls_are_rejected(self):
        contract = dict(self.configuration['coverage_contract'])
        service = self.service(coverage_contract=contract)
        contract['canonical_json'] = b'{}'
        with self.assertRaisesRegex(ValueError, 'candidate.*not found'):
            service.refresh('absent')
        for changed in (dict(contract, canonical_json=b'{ "purpose": "official" }'),
                        dict(contract, skip_gate=True), dict(contract, canonical_json=bytearray(b'{}'))):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.service(coverage_contract=changed)

    def test_official_registries_are_reloaded_not_reused_from_caller(self):
        f = self.fixture
        bundle, scoring, policy, adapter = self.module._reload_official_registry_set(
            f.feature_repository, f.frozen.registry_manifest_hash)
        bundle.require_official()
        scoring.require_authenticated(bundle, expected_purpose='official')
        policy.require_verified()
        adapter.require_current_bundle(bundle, expected_purpose='official')
        self.assertIsNot(scoring, f.scoring)
        self.assertIsNot(policy, f.policy_registry)
        self.assertIsNot(adapter, f.valuation_registry)
        self.assertEqual(policy.contract_hash, f.policy_registry.contract_hash)

    def test_test_registry_root_cannot_be_reloaded_as_official(self):
        f = FinalScoringFixture(peer_count=3, purpose='test')
        self.addCleanup(f.close)
        with self.assertRaisesRegex(ValueError, 'purpose|official'):
            self.module._reload_official_registry_set(f.feature_repository,
                                                      f.frozen.registry_manifest_hash)


if __name__ == '__main__':
    unittest.main()
