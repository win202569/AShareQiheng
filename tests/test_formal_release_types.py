"""Canonical release data is validated but never grants publication authority."""
import hashlib
import hmac
import json
import unittest
from dataclasses import replace
from decimal import Decimal

from ashare_pipeline import formal_release_types as release


GATES = ('candidate_identity', 'official_registry', 'workspace_identity',
    'frozen_universe', 'official_coverage', 'source_identity_temporal',
    'replay_equivalence', 'classification_complete', 'score_formula',
    'pool_selection', 'job_quiescence', 'artifact_renderability')


class TestVerifier:
    def verify(self, payload, *, signature, key_id):
        return key_id == 'fixture' and hmac.compare_digest(
            signature, hmac.new(b'test-only', payload, hashlib.sha256).hexdigest())


def validation():
    return release.ReleaseValidationPayload(run_id='run-1', release_identity_hash='a'*64,
        input_manifest_hash='b'*64, result_hash='c'*64, coverage_manifest_hash='d'*64,
        source_dependency_hash='e'*64, registry_manifest_hash='f'*64,
        frozen_input_hash='1'*64, universe_hash='2'*64, code_version='3'*40,
        contract_version='V3', schema_version=9, purpose='publish',
        gates=tuple(release.ValidationGate(name, True, (), ('4'*64,)) for name in GATES))


class ReleaseTypesTests(unittest.TestCase):
    def test_validation_canonical_roundtrip_and_order_independence(self):
        value = validation()
        raw = release.canonical_validation_bytes(value)
        self.assertEqual(release.load_validation_bytes(raw), value)
        self.assertEqual(raw, release.canonical_validation_bytes(replace(value, gates=value.gates[::-1])))
        self.assertEqual(json.loads(raw)['schema'], 'formal-release-validation-v1')
        self.assertFalse(hasattr(value, 'require_verified'))

    def test_gate_set_and_exact_bool_are_enforced(self):
        for gates in (validation().gates[:-1], validation().gates + (validation().gates[0],),
                      (release.ValidationGate('unknown', True, (), ()),) + validation().gates[1:]):
            with self.subTest(gates=gates), self.assertRaises(ValueError):
                release.canonical_validation_bytes(replace(validation(), gates=gates))
        for passed in (1, 0, 'true', None):
            with self.subTest(passed=passed), self.assertRaises(ValueError):
                release.ValidationGate('candidate_identity', passed, (), ())
        with self.assertRaises(ValueError):
            release.ValidationGate('candidate_identity', False, (), ())

    def test_unknown_noncanonical_duplicate_and_nonfinite_json_rejected(self):
        raw = release.canonical_validation_bytes(validation())
        obj = json.loads(raw)
        obj['unknown'] = 1
        malformed = [json.dumps(obj).encode(), b'{"schema":1,"schema":2}',
                     raw + b' ', raw.replace(b'"schema_version":9', b'"schema_version":9.0'),
                     raw.replace(b'"schema_version":9', b'"schema_version":NaN')]
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(ValueError):
                release.load_validation_bytes(data)

    def test_identity_fields_and_frozen_containers_checked(self):
        for changes in ({'input_manifest_hash':'A'*64}, {'code_version':'bad'},
                        {'schema_version':True}, {'purpose':'official'}, {'run_id':''},
                        {'gates':list(validation().gates)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                release.canonical_validation_bytes(replace(validation(), **changes))

    def test_release_file_paths_and_sizes_reject_unsafe_inputs(self):
        for path in ('../a', '/a', 'C:/a', 'a\\b', 'a//b', './a', 'a/',
                     'CON.csv', 'a/NUL.json', 'a.', 'a ', 'a:b', 'a\x00b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                release.ReleaseFile(path, 'a'*64, 1)
        for size in (-1, True, 1.5):
            with self.subTest(size=size), self.assertRaises(ValueError):
                release.ReleaseFile('scores.csv', 'a'*64, size)
        self.assertEqual(release.ReleaseFile('audit_cards/BJ430001.json','a'*64,0).byte_size, 0)

    def test_preparation_roundtrip_and_duplicate_tree_rejected(self):
        value = release.ReleasePreparationPayload(release_identity_hash='a'*64, run_id='run-1',
            validation_hash='b'*64, input_manifest_hash='c'*64, result_hash='d'*64,
            manifest_sha256=hashlib.sha256(b'{}').hexdigest(), manifest_byte_size=2, renderer_version='release-renderer-v1',
            target_path='D:/releases/20260831-formal-v3-'+'a'*64,
            files=(release.ReleaseFile('scores.csv','f'*64,0),), manifest_json='{}')
        raw = release.canonical_preparation_bytes(value)
        self.assertEqual(release.load_preparation_bytes(raw), value)
        for files in ((value.files[0], value.files[0]),
                      (value.files[0], release.ReleaseFile('SCORES.csv','f'*64,0)),
                      (release.ReleaseFile('a','f'*64,0), release.ReleaseFile('a/b','f'*64,0)),
                      (release.ReleaseFile('release_manifest.json','f'*64,0),), ()):
            with self.subTest(files=files), self.assertRaises(ValueError):
                release.canonical_preparation_bytes(replace(value, files=files))

    def test_decimal_serialization_is_finite_and_lossless(self):
        self.assertEqual(release.canonical_release_bytes({'x':Decimal('0.123456789012345678901')}),
                         b'{"x":"0.123456789012345678901"}')
        for value in (1.0, Decimal('NaN'), Decimal('Infinity')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.canonical_release_bytes({'x':value})

    def test_signature_is_bound_to_domain_key_and_canonical_bytes(self):
        raw = release.canonical_validation_bytes(validation())
        signed = release.signature_message('formal-release-validation-v1', 'fixture', raw)
        signature = hmac.new(b'test-only', signed, hashlib.sha256).hexdigest()
        verifier = TestVerifier()
        release.verify_release_signature(raw, signature=signature, key_id='fixture',
            expected_key_id='fixture', domain='formal-release-validation-v1', verifier=verifier)
        for data, domain, key, expected in ((raw,'formal-release-preparation-v1','fixture','fixture'),
                (raw,'formal-release-validation-v1','other','fixture'),
                (raw+b' ','formal-release-validation-v1','fixture','fixture')):
            with self.subTest(domain=domain,key=key), self.assertRaises(ValueError):
                release.verify_release_signature(data, signature=signature, key_id=key,
                    expected_key_id=expected, domain=domain, verifier=verifier)

    def test_nested_tampering_is_rechecked_before_serialization(self):
        value = validation()
        object.__setattr__(value.gates[0], 'passed', 1)
        with self.assertRaises(ValueError):
            release.canonical_validation_bytes(value)
        item = release.ReleaseFile('scores.csv','a'*64,1)
        prepared = release.ReleasePreparationPayload('a'*64,'run-1','b'*64,'c'*64,'d'*64,
            hashlib.sha256(b'{}').hexdigest(),2,'v1','D:/releases/20260831-formal-v3-'+'a'*64,(item,), manifest_json='{}')
        object.__setattr__(item, 'byte_size', -1)
        with self.assertRaises(ValueError):
            release.canonical_preparation_bytes(prepared)

    def test_preparation_target_and_directory_case_are_normalized(self):
        prepared = release.ReleasePreparationPayload('a'*64,'run-1','b'*64,'c'*64,'d'*64,
            hashlib.sha256(b'{}').hexdigest(),2,'v1','D:/releases/20260831-formal-v3-'+'a'*64,
            (release.ReleaseFile('scores.csv','f'*64,1),), manifest_json='{}')
        for target in ('D://releases/20260831-formal-v3-'+'a'*64,
                       'D:/releases./20260831-formal-v3-'+'a'*64):
            with self.subTest(target=target), self.assertRaises(ValueError):
                replace(prepared,target_path=target)
        with self.assertRaises(ValueError):
            replace(prepared,files=(release.ReleaseFile('Audit/a.json','f'*64,1),
                release.ReleaseFile('audit/b.json','f'*64,1)))

    def test_manifest_cannot_be_a_directory_and_windows_device_alias_rejected(self):
        prepared = release.ReleasePreparationPayload('a'*64,'run-1','b'*64,'c'*64,'d'*64,
            hashlib.sha256(b'{}').hexdigest(),2,'v1','D:/releases/20260831-formal-v3-'+'a'*64,
            (release.ReleaseFile('scores.csv','f'*64,1),), manifest_json='{}')
        for path in ('release_manifest.json/a.json','RELEASE_MANIFEST.JSON/a.json'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                replace(prepared,files=(release.ReleaseFile(path,'f'*64,1),))
        for component in ('COM'+chr(185), 'LPT'+chr(178), 'COM'+chr(179)):
            with self.subTest(component=component), self.assertRaises(ValueError):
                replace(prepared,target_path='D:/'+component+'/20260831-formal-v3-'+'a'*64)

    def test_preparation_carries_exact_canonical_manifest_bytes(self):
        prepared = release.ReleasePreparationPayload('a'*64,'run-1','b'*64,'c'*64,'d'*64,
            hashlib.sha256(b'{}').hexdigest(),2,'v1','D:/releases/20260831-formal-v3-'+'a'*64,
            (release.ReleaseFile('scores.csv','f'*64,1),), manifest_json='{}')
        for changes in ({'manifest_json':'{} '}, {'manifest_sha256':'e'*64},
                        {'manifest_byte_size':3}, {'manifest_json':'{"x":1,"x":2}'},
                        {'manifest_json':'[]'}, {'manifest_json':'{"x":NaN}'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(prepared,**changes)


if __name__ == '__main__':
    unittest.main()
