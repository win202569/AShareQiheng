"""Manifest bytes are data, never release authority."""
import hashlib
import json
import unittest
from tests import test_formal_release_selection_rendering as fixtures
from ashare_pipeline.formal_release_types import canonical_release_bytes


class ReleaseManifestRenderingTests(unittest.TestCase):
    def setUp(self):
        self.data=fixtures.ReleasePayloadAssemblyTests().data()
        self.identity=dict(contract_version='formal-final-v1',input_manifest_hash='1'*64,
            result_hash='2'*64,registry_manifest_hash='3'*64,frozen_input_hash='4'*64,
            universe_hash='5'*64)
        wire=json.loads(self.data['score_input_batch'])
        wire.update({key:self.identity[key] for key in ('registry_manifest_hash','frozen_input_hash','universe_hash')})
        wire['as_of_utc']='2026-08-31T07:00:00+00:00'
        self.data['score_input_batch']=canonical_release_bytes(wire)

    def render(self, **kwargs):
        from ashare_pipeline.formal_release_rendering import _render_release_package
        return _render_release_package(self.data,candidate_identity=self.identity,**kwargs)

    def test_manifest_is_last_and_binds_every_payload_byte(self):
        files=self.render()
        self.assertEqual(list(files)[-1],'release_manifest.json')
        manifest=json.loads(files['release_manifest.json'])
        self.assertEqual(manifest['schema'],'formal-release-manifest-v1')
        self.assertEqual([row['path'] for row in manifest['files']],sorted(set(files)-{'release_manifest.json'}))
        for row in manifest['files']:
            self.assertEqual(row['sha256'],hashlib.sha256(files[row['path']]).hexdigest())
            self.assertEqual(row['byte_size'],len(files[row['path']]))
        self.assertEqual(manifest['counts'],dict(universe=3,scorecards=3,formal_scored=3,pool_vetoed=0,strong=2,wait=1,payload_files=9))
        self.assertNotIn('run_id',manifest)
        self.assertNotIn('created_at',manifest)

    def test_identity_matches_existing_content_identity_definition(self):
        from ashare_pipeline.formal_release_types import canonical_release_identity_bytes
        files=self.render()
        manifest=json.loads(files['release_manifest.json'])
        raw=canonical_release_identity_bytes(contract_version=self.identity['contract_version'],
            input_manifest_hash=self.identity['input_manifest_hash'],result_hash=self.identity['result_hash'],
            renderer_version=manifest['renderer_version'])
        digest=hashlib.sha256(raw).hexdigest()
        self.assertEqual(manifest['release_identity_hash'],digest)
        self.assertEqual(manifest['release_id'],'20260831-formal-v3-'+digest)
        self.assertEqual(files,self.render())

    def test_root_frozen_and_universe_mismatch_rejected(self):
        for key in ('registry_manifest_hash','frozen_input_hash','universe_hash'):
            saved=self.identity[key]
            try:
                self.identity[key]='f'*64
                with self.subTest(key=key),self.assertRaises(ValueError):
                    self.render()
            finally:
                self.identity[key]=saved

    def test_runtime_and_renderer_overrides_are_not_accepted(self):
        for key in ('run_id','created_at','renderer_version','files','counts'):
            with self.subTest(key=key),self.assertRaises(TypeError):
                self.render(**{key:'caller'})
        self.identity['run_id']='caller'
        with self.assertRaises(ValueError):
            self.render()

    def test_bad_hash_or_wrong_freeze_rejected(self):
        self.identity['result_hash']='not-a-hash'
        with self.assertRaises(ValueError):
            self.render()
        self.identity['result_hash']='2'*64
        wire=json.loads(self.data['score_input_batch'])
        wire['as_of_utc']='2026-08-31T07:00:01+00:00'
        self.data['score_input_batch']=canonical_release_bytes(wire)
        with self.assertRaises(ValueError):
            self.render()
