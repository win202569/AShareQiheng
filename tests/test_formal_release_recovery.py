"""Recovery accepts durable signed preparation, never an audit DTO or loose files."""
from contextlib import closing
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import unittest
from tests import test_formal_release_audit as audit_fixtures
from tests.test_formal_release_audit import AuditSigner, AuditVerifier
from tests.formal_release_refresh_fixtures import put_storage_only_history
from tests.test_formal_release_types import validation
from ashare_pipeline.formal_release_types import (canonical_validation_bytes, canonical_preparation_bytes,
    canonical_release_bytes, canonical_release_identity_bytes, signature_message,
    VALIDATION_DOMAIN, PREPARATION_DOMAIN, ReleaseFile, ReleasePreparationPayload)


class ReleaseRecoveryTests(unittest.TestCase):
    setUp = audit_fixtures.SignedAuditBoundaryTests.setUp

    def records(self, purpose='publish', omit=None):
        f=self.fixture
        run_id=put_storage_only_history(f,code_version='a'*40)
        header=self.runs.get_run(run_id).header
        identity=hashlib.sha256(canonical_release_identity_bytes(contract_version=header['contract_version'],
            input_manifest_hash=header['input_manifest_hash'],result_hash=header['result_hash'],
            renderer_version='formal-release-renderer-v1')).hexdigest()
        rid='20260831-formal-v3-'+identity
        self.release_root=f.root/'releases'
        target=self.release_root/rid
        target.mkdir(parents=True)
        value=replace(validation(),run_id=run_id,release_identity_hash=identity,purpose=purpose,
            **{name:header[name] for name in ('input_manifest_hash','result_hash','registry_manifest_hash',
                 'frozen_input_hash','universe_hash','code_version','contract_version')})
        raw=canonical_validation_bytes(value); vh=hashlib.sha256(raw).hexdigest()
        contents={name:b'test' for name in ('universe_status.csv','scores.csv','strong_attention.csv',
            'waiting_price.csv','evidence_manifest.json','quality_report.md')}
        contents.update({'audit_cards/'+member.security_id+'.json':b'{}' for member in f.frozen.members})
        if omit is not None: contents.pop(omit)
        files=tuple(ReleaseFile(name,hashlib.sha256(raw).hexdigest(),len(raw)) for name,raw in sorted(contents.items()))
        snapshot=self.runs.get_run(run_id)
        n=len(f.frozen.members)
        manifest=dict(schema='formal-release-manifest-v1',release_id=rid,release_identity_hash=identity,
            renderer_version='formal-release-renderer-v1',freeze_at_utc='2026-08-31T07:00:00+00:00',
            files=[dict(path=item.path,sha256=item.sha256,byte_size=item.byte_size) for item in files],
            counts=dict(universe=n,scorecards=n,formal_scored=sum(row['state']=='formal_scored' for row in snapshot.statuses),
                pool_vetoed=sum(row['state']=='pool_vetoed' for row in snapshot.statuses),strong=0,wait=0,payload_files=len(files)),
            **{name:getattr(value,name) for name in ('contract_version','input_manifest_hash','result_hash',
                'registry_manifest_hash','frozen_input_hash','universe_hash')})
        mr=canonical_release_bytes(manifest)
        prepared=ReleasePreparationPayload(identity,run_id,vh,header['input_manifest_hash'],header['result_hash'],
            hashlib.sha256(mr).hexdigest(),len(mr),'formal-release-renderer-v1',target.as_posix(),files,mr.decode())
        pr=canonical_preparation_bytes(prepared); ph=hashlib.sha256(pr).hexdigest()
        signer=AuditSigner()
        vs=signer.sign(signature_message(VALIDATION_DOMAIN,'isolated-audit',raw),key_id='isolated-audit')
        ps=signer.sign(signature_message(PREPARATION_DOMAIN,'isolated-audit',pr),key_id='isolated-audit')
        with f.store._transaction(immediate=True) as c:
            c.execute('INSERT INTO formal_release_validation VALUES(?,?,?,?,?,?,?,?,?)',
                (vh,run_id,identity,purpose,1,raw.decode(),vs,'isolated-audit','fixture'))
            c.execute('''INSERT INTO formal_release(release_id,release_identity_hash,run_id,input_manifest_hash,
                result_hash,validation_hash,status,release_path,fencing_generation,created_at)
                VALUES(?,?,?,?,?,?,'publishing',?,1,'fixture')''',
                (rid,identity,run_id,header['input_manifest_hash'],header['result_hash'],vh,target.as_posix()))
            c.execute('INSERT INTO formal_release_preparation VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ph,rid,run_id,identity,vh,pr.decode(),ps,'isolated-audit',mr.decode(),prepared.manifest_sha256,len(mr),1,'fixture'))
            c.execute('UPDATE formal_release SET active_preparation_hash=? WHERE release_id=?',(ph,rid))
        for name,content in contents.items():
            path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        (target/'release_manifest.json').write_bytes(mr)
        self.run_id,self.release_id,self.prepared=run_id,rid,prepared
        return run_id

    def reader(self):
        self.assertIsNotNone(importlib.util.find_spec('ashare_pipeline.formal_release_recovery'))
        from ashare_pipeline.formal_release_recovery import _read_recovery_candidate
        with closing(self.fixture.store._connect()) as c:
            c.execute('BEGIN')
            return _read_recovery_candidate(c,run_id=self.run_id,release_root=self.release_root,
                                           verifier=AuditVerifier(),key_id='isolated-audit')

    def test_durable_signed_record_is_read_without_writes(self):
        self.records(); row,prepared=self.reader()
        self.assertEqual(row['status'],'publishing');self.assertEqual(prepared,self.prepared)

    def test_audit_signature_never_authorizes_recovery(self):
        self.records('audit')
        with self.assertRaisesRegex(ValueError,'audit'): self.reader()

    def test_tampered_signature_and_wrong_root_rejected(self):
        self.records()
        with self.fixture.store._transaction() as c:
            c.execute("UPDATE formal_release_preparation SET signature='bad'")
        with self.assertRaises(ValueError): self.reader()

    def test_missing_preparation_rejected(self):
        self.records()
        with self.fixture.store._transaction() as c:
            c.execute('UPDATE formal_release SET active_preparation_hash=NULL')
        with self.assertRaisesRegex(ValueError,'preparation'): self.reader()

    def test_wrong_target_root_rejected(self):
        self.records();self.release_root=self.fixture.root/'other'
        with self.assertRaises(ValueError): self.reader()


class ConfiguredRecoveryTests(ReleaseRecoveryTests):
    def service(self):
        self.assertTrue(callable(getattr(self.module._ReleaseInputRefresh,'recover',None)), 'configured recovery entry is missing')
        return self.module._ReleaseInputRefresh(**self.configuration,release_signer=AuditSigner(),
            release_signature_verifier=AuditVerifier(),release_key_id='isolated-audit',release_root=self.release_root)

    def test_recovery_completes_existing_tree_and_repeated_call_is_read_only(self):
        self.records(); before=self.runs.get_run(self.run_id)
        service=self.service()
        self.assertEqual(service.recover(self.run_id)['status'],'recovered')
        with closing(self.fixture.store._connect()) as c:
            row=dict(c.execute('SELECT * FROM formal_release').fetchone())
            self.assertEqual(row['status'],'published');self.assertEqual(row['fencing_generation'],2)
            self.assertIsNone(row['attempt_token'])
            files=[tuple(item) for item in c.execute('SELECT path,sha256,byte_size FROM formal_release_file')]
            self.assertEqual(files,[(item.path,item.sha256,item.byte_size) for item in self.prepared.files])
        self.assertEqual(service.recover(self.run_id)['status'],'already_published')
        self.assertEqual(self.runs.get_run(self.run_id),before)
        with closing(self.fixture.store._connect()) as c:
            self.assertEqual(dict(c.execute('SELECT * FROM formal_release').fetchone()),row)

    def test_missing_or_corrupt_tree_does_not_change_release(self):
        self.records();service=self.service()
        (Path(self.prepared.target_path)/'scores.csv').unlink()
        with self.assertRaises(ValueError): service.recover(self.run_id)
        with closing(self.fixture.store._connect()) as c:
            row=c.execute('SELECT status,fencing_generation,attempt_token FROM formal_release').fetchone()
            self.assertEqual(tuple(row),('publishing',1,None))
            self.assertEqual(c.execute('SELECT count(*) FROM formal_release_file').fetchone()[0],0)

    def test_live_attempt_blocks_recovery_and_expired_attempt_is_fenced(self):
        self.records();service=self.service()
        with self.fixture.store._transaction() as c:
            c.execute("UPDATE formal_release SET attempt_token='old',attempt_expires_at='2999-01-01T00:00:00+00:00'")
        with self.assertRaisesRegex(ValueError,'active|lease'): service.recover(self.run_id)
        with self.fixture.store._transaction() as c:
            c.execute("UPDATE formal_release SET attempt_expires_at='2000-01-01T00:00:00+00:00'")
        self.assertEqual(service.recover(self.run_id)['status'],'recovered')

    def test_audit_only_record_cannot_complete_release(self):
        self.records('audit')
        with self.assertRaisesRegex(ValueError,'audit'): self.service().recover(self.run_id)

    def test_recovery_has_no_path_proof_or_verifier_overrides(self):
        self.records();service=self.service()
        for name in ('target_path','preparation','validation_hash','verifier','skip_gate'):
            with self.subTest(name=name),self.assertRaises(TypeError):
                service.recover(self.run_id,**{name:object()})

    def test_published_file_rows_must_reference_active_preparation(self):
        self.records();service=self.service();service.recover(self.run_id)
        with self.fixture.store._transaction() as c:
            row=dict(c.execute('SELECT * FROM formal_release_preparation').fetchone())
            row['preparation_hash']='e'*64
            c.execute('INSERT INTO formal_release_preparation VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
            c.execute('UPDATE formal_release_file SET preparation_hash=?',('e'*64,))
        with self.assertRaisesRegex(ValueError,'metadata|preparation'): service.recover(self.run_id)

    def test_changed_v8_history_cannot_be_recovered(self):
        self.records();service=self.service()
        with self.fixture.store._transaction() as c:
            c.execute("UPDATE formal_final_run SET result_hash=? WHERE run_id=?",('0'*64,self.run_id))
        with self.assertRaises(ValueError): service.recover(self.run_id)

    def test_database_write_failure_rolls_back_recovery(self):
        import sqlite3
        from unittest.mock import patch
        self.records();service=self.service()
        original=sqlite3.connect
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql.startswith('INSERT INTO formal_release_file'):
                    raise sqlite3.OperationalError('injected write failure')
                return super().execute(sql,parameters)
        def connect(*args,**kwargs):
            return original(*args,**dict(kwargs,factory=FailingConnection))
        with patch.object(sqlite3,'connect',connect):
            with self.assertRaisesRegex(sqlite3.OperationalError,'injected'): service.recover(self.run_id)
        with closing(self.fixture.store._connect()) as c:
            self.assertEqual(tuple(c.execute('SELECT status,fencing_generation,attempt_token FROM formal_release').fetchone()),
                             ('publishing',1,None))
            self.assertEqual(c.execute('SELECT count(*) FROM formal_release_file').fetchone()[0],0)
        self.assertEqual(service.recover(self.run_id)['status'],'recovered')

    def test_recovery_does_not_require_current_source_generation(self):
        self.records();service=self.service()
        with self.fixture.store._transaction() as c:
            c.execute('CREATE TABLE later_source_correction(value TEXT)')
            c.execute("INSERT INTO later_source_correction VALUES('new source generation')")
        self.assertEqual(service.recover(self.run_id)['status'],'recovered')

    def test_replaced_tree_checker_cannot_authorize_recovery(self):
        from unittest.mock import patch
        self.records();service=self.service()
        with patch.object(self.module.tree_module,'_verify_release_tree',return_value=()):
            with self.assertRaisesRegex(ValueError,'authority'): service.recover(self.run_id)
        with closing(self.fixture.store._connect()) as c:
            self.assertEqual(c.execute('SELECT status FROM formal_release').fetchone()[0],'publishing')

    def test_signed_but_incomplete_payload_set_is_rejected(self):
        self.records(omit='quality_report.md')
        with self.assertRaisesRegex(ValueError,'payload|manifest'): self.service().recover(self.run_id)
