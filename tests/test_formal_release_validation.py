"""Detached candidate comparisons are diagnostics, never live capabilities."""
from dataclasses import replace
import unittest
from types import MappingProxyType

from ashare_pipeline.formal_final_repository import FormalFinalRunSnapshot


IDS = ('BJ430001', 'SH600001', 'SZ000001')


def candidate():
    header = dict(run_id='original', mode='official_candidate', status='preview_ready',
                  code_version='a' * 40, contract_version='formal-final-v1',
                  registry_manifest_hash='b' * 64, frozen_input_hash='c' * 64,
                  universe_hash='d' * 64, as_of_utc='2026-08-31T07:00:00+00:00')
    # These deliberately non-proof bytes exercise comparison only. Neither
    # this DTO nor a successful comparison may ever authorize publication.
    artifacts = {name: name.encode() for name in ('coverage_manifest',
                 'score_input_batch', 'scorecard_batch', 'eligibility_batch',
                 'pool_selection_batch')}
    rows = tuple(MappingProxyType(dict(security_id=sid)) for sid in IDS)
    states = tuple(MappingProxyType(dict(security_id=sid, state='formal_scored'))
                   for sid in IDS)
    return FormalFinalRunSnapshot(MappingProxyType(header), MappingProxyType(artifacts),
                                  MappingProxyType({}), rows, (), states, (), (), ())


class CandidateComparisonTests(unittest.TestCase):
    def setUp(self):
        import ashare_pipeline.formal_release_validation as module
        self.module = module
        self.snapshot = candidate()
        self.binding = dict(run_id='original', code_version='a' * 40,
                            contract_version='formal-final-v1',
                            registry_manifest_hash='b' * 64, frozen_input_hash='c' * 64,
                            universe_hash='d' * 64, security_ids=IDS)

    def check(self, snapshot=None, **changes):
        return self.module._check_candidate_binding(
            self.snapshot if snapshot is None else snapshot, **dict(self.binding, **changes))

    def changed_header(self, **changes):
        return replace(self.snapshot, header=MappingProxyType(dict(self.snapshot.header, **changes)))

    def test_matching_detached_data_returns_no_authority(self):
        self.assertIsNone(self.check())

    def test_test_preview_and_blocked_candidates_are_rejected(self):
        for changes in (dict(mode='test_preview'), dict(status='blocked'),
                        dict(mode='legacy'), dict(status='published')):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'candidate'):
                self.check(self.changed_header(**changes))

    def test_cross_run_root_freeze_universe_and_contract_are_rejected(self):
        for field, value in (('run_id', 'another'), ('registry_manifest_hash', 'e' * 64),
                             ('frozen_input_hash', 'f' * 64), ('universe_hash', 'e' * 64),
                             ('contract_version', 'another-contract'),
                             ('as_of_utc', '2026-08-31T07:00:01+00:00')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(self.changed_header(**{field: value}))

    def test_old_code_requires_new_candidate(self):
        with self.assertRaisesRegex(ValueError, 'candidate_changed'):
            self.check(self.changed_header(code_version='e' * 40))

    def test_short_code_and_invalid_expected_bindings_are_rejected(self):
        for changes in (dict(code_version='a' * 7), dict(code_version='A' * 40),
                        dict(registry_manifest_hash='root'), dict(run_id=''),
                        dict(contract_version=''), dict(security_ids=IDS + IDS[:1]),
                        dict(security_ids=IDS[::-1]), dict(security_ids=IDS[1:]),
                        dict(security_ids=('BJ430001', 'SH600001', 'SZwrong'))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.check(**changes)

    def test_missing_duplicate_and_foreign_members_are_rejected(self):
        for rows in (self.snapshot.inputs[:-1], self.snapshot.inputs + self.snapshot.inputs[:1],
                     self.snapshot.inputs + (MappingProxyType(dict(security_id='SH600999')),)):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.check(replace(self.snapshot, inputs=rows))

    def test_each_member_must_have_exactly_one_final_classification(self):
        for states in (self.snapshot.statuses[:-1],
                       self.snapshot.statuses + self.snapshot.statuses[:1],
                       self.snapshot.statuses + (MappingProxyType(dict(
                           security_id='SH600999', state='formal_scored')),)):
            with self.subTest(states=states), self.assertRaises(ValueError):
                self.check(replace(self.snapshot, statuses=states))

    def test_pending_out_of_scope_and_unknown_classifications_are_rejected(self):
        for state in ('pending_evidence', 'out_of_scope', 'ready', 'scored'):
            rows = (MappingProxyType(dict(security_id=IDS[0], state=state)),) + self.snapshot.statuses[1:]
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.check(replace(self.snapshot, statuses=rows))

    def test_vetoed_zero_pool_is_not_mistaken_for_pending(self):
        rows = tuple(MappingProxyType(dict(security_id=sid, state='pool_vetoed')) for sid in IDS)
        self.assertIsNone(self.check(replace(self.snapshot, statuses=rows)))

    def test_duck_typed_data_and_snapshot_as_run_selector_are_rejected(self):
        with self.assertRaises(ValueError):
            self.check(object())
        with self.assertRaises(ValueError):
            self.check(run_id=self.snapshot)

    def test_matching_four_replay_bytes_returns_no_authority(self):
        replay = {kind: raw for kind, raw in self.snapshot.artifacts.items()
                  if kind != 'coverage_manifest'}
        self.assertEqual(self.module._compare_candidate_replay(self.snapshot, replay), ())

    def test_every_changed_computation_is_named(self):
        replay = {kind: raw for kind, raw in self.snapshot.artifacts.items()
                  if kind != 'coverage_manifest'}
        for kind in replay:
            with self.subTest(kind=kind):
                self.assertEqual(self.module._compare_candidate_replay(
                    self.snapshot, dict(replay, **{kind: b'corrected'})), (kind,))

    def test_coverage_is_not_an_equality_target_for_computation_replay(self):
        replay = {kind: raw for kind, raw in self.snapshot.artifacts.items()
                  if kind != 'coverage_manifest'}
        snapshot = replace(self.snapshot, artifacts=MappingProxyType(dict(
            self.snapshot.artifacts, coverage_manifest=b'new operational DB/WAL hash')))
        self.assertEqual(self.module._compare_candidate_replay(snapshot, replay), ())
        with self.assertRaises(ValueError):
            self.module._compare_candidate_replay(snapshot, dict(replay, coverage_manifest=b'current'))

    def test_missing_extra_mutable_and_non_byte_replay_data_are_rejected(self):
        replay = {kind: raw for kind, raw in self.snapshot.artifacts.items()
                  if kind != 'coverage_manifest'}
        for changed in ({}, dict(replay, extra=b''),
                        dict(replay, score_input_batch=bytearray(b'input')),
                        dict(replay, score_input_batch='input')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.module._compare_candidate_replay(self.snapshot, changed)


class OfficialReplayBoundaryTests(unittest.TestCase):
    def test_real_preview_coverage_cannot_enter_official_replay(self):
        import ashare_pipeline.formal_release_validation as module
        from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
        from tests.formal_final_scoring_fixtures import FinalScoringFixture
        from tests.test_formal_final_runner import coverage_for
        from contextlib import closing

        fixture = FinalScoringFixture(peer_count=3, purpose='test')
        self.addCleanup(fixture.close)
        repository = FormalFinalScoreInputRepository(fixture.feature_repository, fixture.context,
            fixture.range_store, registry_signature_verifier=fixture.verifier)
        coverage = coverage_for(fixture)
        with self.assertRaisesRegex(ValueError, 'official|authenticated'):
            module._replay_official_candidate(candidate(), run_id='original',
                input_repository=repository, scoring_registry=fixture.scoring,
                policy_registry=fixture.policy_registry,
                valuation_adapter_registry=fixture.valuation_registry, coverage_manifest=coverage)
        with closing(fixture.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_final_run').fetchone()[0], 0)

    def test_replaced_producer_function_is_rejected_before_any_caller_object(self):
        import ashare_pipeline.formal_release_validation as module
        from unittest.mock import patch
        with patch.object(module, 'build_final_score_card_batch', lambda *args: None):
            with self.assertRaisesRegex(ValueError, 'authority changed'):
                module._replay_official_candidate(candidate(), run_id='original',
                    input_repository=object(), scoring_registry=object(), policy_registry=object(),
                    valuation_adapter_registry=object(), coverage_manifest=object())

    def test_changed_coverage_method_code_is_rejected_before_any_caller_object(self):
        import ashare_pipeline.formal_release_validation as module
        from ashare_pipeline.formal_coverage_manifest import VerifiedCoverageManifest
        original = VerifiedCoverageManifest.require_official_ready.__code__

        def replacement():
            first, second, third = None, None, None

            def counterfeit(self):
                return first, second, third

            return counterfeit

        try:
            VerifiedCoverageManifest.require_official_ready.__code__ = replacement().__code__
            with self.assertRaisesRegex(ValueError, 'authority changed'):
                module._replay_official_candidate(candidate(), run_id='original',
                    input_repository=object(), scoring_registry=object(), policy_registry=object(),
                    valuation_adapter_registry=object(), coverage_manifest=object())
        finally:
            VerifiedCoverageManifest.require_official_ready.__code__ = original

    def test_replay_rejects_caller_objects_without_executing_them(self):
        import ashare_pipeline.formal_release_validation as module

        class Tripwire:
            def __getattr__(self, name):
                raise AssertionError('caller object was executed: ' + name)

        with self.assertRaisesRegex(ValueError, 'genuine'):
            module._replay_official_candidate(candidate(), run_id='original',
                input_repository=Tripwire(), scoring_registry=Tripwire(),
                policy_registry=Tripwire(), valuation_adapter_registry=Tripwire(),
                coverage_manifest=Tripwire())

    def test_exact_type_without_constructor_cannot_replay(self):
        import ashare_pipeline.formal_release_validation as module
        from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
        from ashare_pipeline.formal_scoring_registry import FormalScoringRegistry
        from ashare_pipeline.formal_policy_registry import FormalPolicyRegistry
        from ashare_pipeline.formal_valuation_adapter_contract import FormalValuationAdapterRegistry
        from ashare_pipeline.formal_coverage_manifest import VerifiedCoverageManifest
        with self.assertRaisesRegex(ValueError, 'forged|unpublished|copied|constructor'):
            module._replay_official_candidate(candidate(), run_id='original',
                input_repository=object.__new__(FormalFinalScoreInputRepository),
                scoring_registry=object.__new__(FormalScoringRegistry),
                policy_registry=object.__new__(FormalPolicyRegistry),
                valuation_adapter_registry=object.__new__(FormalValuationAdapterRegistry),
                coverage_manifest=object.__new__(VerifiedCoverageManifest))


class GenuineOfficialReplayRejectionTests(unittest.TestCase):
    def test_real_official_producers_reject_pending_without_creating_a_v8_run(self):
        import ashare_pipeline.formal_release_validation as module
        from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
        from tests.formal_final_scoring_fixtures import FinalScoringFixture
        from tests.test_formal_final_integration import official_context_coverage
        from contextlib import closing

        print('V9 replay rejection: genuine signed three-member official fixture', flush=True)
        fixture = FinalScoringFixture(peer_count=3, purpose='official')
        self.addCleanup(fixture.close)
        fixture.populate_final_inputs()
        coverage = official_context_coverage(fixture)
        coverage.require_official_ready()
        frozen = fixture.frozen
        snapshot = candidate()
        ids = tuple(sorted(member.security_id for member in frozen.members))
        snapshot = replace(snapshot, header=MappingProxyType(dict(snapshot.header,
            code_version=coverage.to_dict()['workspace_revision'],
            registry_manifest_hash=frozen.registry_manifest_hash,
            frozen_input_hash=frozen.frozen_input_hash, universe_hash=frozen.universe_hash)),
            inputs=tuple(MappingProxyType(dict(security_id=sid)) for sid in ids),
            statuses=tuple(MappingProxyType(dict(security_id=sid, state='formal_scored')) for sid in ids))
        repository = FormalFinalScoreInputRepository(fixture.feature_repository, fixture.context,
            fixture.range_store, registry_signature_verifier=fixture.verifier)
        print('V9 replay rejection: D1/D2/D3/pools, strict pending gate', flush=True)
        # The synthetic historical data deliberately CLAIMS formal classification.
        # Actual producers cannot satisfy it with only three peers. This checks
        # the live rejection path, not official-candidate acceptance or a mint.
        with self.assertRaisesRegex(ValueError, 'candidate_changed:.*pending'):
            module._replay_official_candidate(snapshot, run_id='original',
                input_repository=repository, scoring_registry=fixture.scoring,
                policy_registry=fixture.policy_registry,
                valuation_adapter_registry=fixture.valuation_registry, coverage_manifest=coverage)
        with closing(fixture.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_final_run').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
