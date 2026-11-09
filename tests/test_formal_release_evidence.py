"""Replay evidence commitments are detached diagnostics, not authority."""
import json
import unittest
from ashare_pipeline.formal_release_types import canonical_release_bytes


class ReplayEvidenceTests(unittest.TestCase):
    def data(self):
        return dict(source_bytes=(b'base',b'policy',b'valuation'),
            registry_bytes=(b'root',(('role_b',b'b'),('role_a',b'a')),b'policy-registry',b'adapter'),
            computation_bytes={name:name.encode() for name in
                ('score_input_batch','scorecard_batch','eligibility_batch','pool_selection_batch')},
            coverage_bytes=canonical_release_bytes({'fresh':True}))

    def evidence(self, **changes):
        from ashare_pipeline.formal_release_validation import _canonical_replay_evidence
        return _canonical_replay_evidence(**dict(self.data(),**changes))

    def test_each_source_and_registry_change_changes_commitment(self):
        baseline=json.loads(self.evidence())['source_dependency_hash']
        original=self.data()
        for index in range(3):
            values=list(original['source_bytes']); values[index]+=b'changed'
            self.assertNotEqual(json.loads(self.evidence(source_bytes=tuple(values)))['source_dependency_hash'],baseline)
        for registry in ((b'other',original['registry_bytes'][1],b'policy-registry',b'adapter'),
                         (b'root',(('role_b',b'changed'),('role_a',b'a')),b'policy-registry',b'adapter'),
                         (b'root',original['registry_bytes'][1],b'other',b'adapter'),
                         (b'root',original['registry_bytes'][1],b'policy-registry',b'other')):
            self.assertNotEqual(json.loads(self.evidence(registry_bytes=registry))['source_dependency_hash'],baseline)

    def test_fresh_coverage_is_separate_from_source_commitment(self):
        import hashlib
        before=json.loads(self.evidence())
        raw=canonical_release_bytes({'fresh':'different'})
        after=json.loads(self.evidence(coverage_bytes=raw))
        self.assertEqual(before['source_dependency_hash'],after['source_dependency_hash'])
        self.assertEqual(after['coverage_manifest_hash'],hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(before['coverage_manifest_hash'],after['coverage_manifest_hash'])

    def test_roles_canonicalized_and_duplicates_rejected(self):
        values=self.data()['registry_bytes']
        self.assertEqual(self.evidence(),self.evidence(registry_bytes=(values[0],tuple(reversed(values[1])),*values[2:])))
        with self.assertRaises(ValueError):
            self.evidence(registry_bytes=(b'root',(('a',b'one'),('a',b'two')),b'p',b'v'))

    def test_missing_source_or_computation_and_mutable_bytes_rejected(self):
        for changes in (dict(source_bytes=(b'base',)),dict(computation_bytes={}),
                        dict(source_bytes=(bytearray(b'base'),b'p',b'v'))):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.evidence(**changes)
