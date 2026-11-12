"""Signed audit entry accepts run IDs, never caller-created validation payloads."""
from contextlib import closing
import hashlib
import hmac
import unittest
from tests import test_formal_release_input_refresh as fixtures


class AuditSigner:
    def sign(self, message, *, key_id):
        if key_id != 'isolated-audit':
            raise ValueError('wrong test key')
        return hmac.new(b'isolated-audit-only', message, hashlib.sha256).hexdigest()


class AuditVerifier:
    def verify(self, message, *, signature, key_id):
        return key_id == 'isolated-audit' and hmac.compare_digest(
            signature, AuditSigner().sign(message, key_id=key_id))


class TriggerOnceAuditSigner(AuditSigner):
    """Adversarial isolated fixture: change schema after genuine validation."""
    def __init__(self, store):
        self.store = store
        self.inject = True

    def sign(self, message, *, key_id):
        if self.inject:
            with closing(self.store._connect()) as connection:
                connection.execute("""CREATE TRIGGER erase_audit AFTER INSERT ON formal_release_validation
                    BEGIN DELETE FROM formal_release_validation WHERE validation_hash=NEW.validation_hash; END""")
                connection.commit()
            self.inject = False
        return super().sign(message, key_id=key_id)


class SignedAuditBoundaryTests(unittest.TestCase):
    setUp = fixtures.ReleaseInputRefreshTests.setUp

    def configured(self, **overrides):
        options = dict(release_signer=AuditSigner(), release_signature_verifier=AuditVerifier(),
                       release_key_id='isolated-audit')
        options.update(overrides)
        return self.module._ReleaseInputRefresh(**self.configuration, **options)

    def test_audit_requires_explicit_signing_configuration(self):
        service = self.module._ReleaseInputRefresh(**self.configuration)
        self.assertTrue(callable(getattr(service, 'audit', None)))
        with self.assertRaisesRegex(ValueError, 'signing configuration'):
            service.audit('absent')

    def test_partial_configuration_and_non_owned_methods_rejected(self):
        self.assertTrue(callable(getattr(self.module._ReleaseInputRefresh, 'audit', None)))
        for overrides in ({'release_signer':None}, {'release_signature_verifier':None},
                          {'release_key_id':''}, {'release_key_id':' key '}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.configured(**overrides)
        signer = AuditSigner()
        signer.sign = lambda *a, **k: 'fake'
        with self.assertRaisesRegex(ValueError, 'owned|fixed'):
            self.configured(release_signer=signer)

    def test_missing_candidate_writes_nothing(self):
        self.assertTrue(callable(getattr(self.module._ReleaseInputRefresh, 'audit', None)))
        service = self.configured()
        with self.assertRaisesRegex(ValueError, 'candidate.*not found'):
            service.audit('absent')
        with closing(self.fixture.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_release_validation').fetchone()[0], 0)

    def test_audit_has_no_payload_signature_or_purpose_override(self):
        self.assertTrue(callable(getattr(self.module._ReleaseInputRefresh, 'audit', None)))
        service = self.configured()
        for name in ('payload','signature','purpose','signer','verifier','key_id'):
            with self.subTest(name=name), self.assertRaises(TypeError):
                service.audit('absent', **{name:object()})

    def test_configured_signer_method_replacement_is_rejected(self):
        self.assertTrue(callable(getattr(self.module._ReleaseInputRefresh, 'audit', None)))
        signer = AuditSigner()
        service = self.configured(release_signer=signer)
        signer.sign = lambda *a, **k: 'fake'
        with self.assertRaisesRegex(ValueError, 'sign|owned|fixed|entry point'):
            service.audit('absent')

    def test_configured_verifier_replacement_and_signer_code_mutation_rejected(self):
        verifier = AuditVerifier()
        service = self.configured(release_signature_verifier=verifier)
        verifier.verify = lambda *a, **k: True
        with self.assertRaisesRegex(ValueError, 'entry point'):
            service.audit('absent')
        service = self.configured()
        original = AuditSigner.sign.__code__
        try:
            AuditSigner.sign.__code__ = original.replace(co_consts=original.co_consts + ('changed',))
            with self.assertRaisesRegex(ValueError, 'signing implementation'):
                service.audit('absent')
        finally:
            AuditSigner.sign.__code__ = original

    def test_active_publishing_is_rejected_before_candidate_replay(self):
        from tests.formal_release_refresh_fixtures import put_storage_only_history
        run_id = put_storage_only_history(self.fixture, code_version='a'*40)
        # Storage-only intent tests routing, never supplies validation authority.
        with closing(self.fixture.store._connect()) as connection:
            connection.execute("""INSERT INTO formal_release_validation VALUES
                ('audit',?,'identity','audit',0,'{}','storage-only','fixture','now')""", (run_id,))
            connection.execute("""INSERT INTO formal_release
                (release_id,release_identity_hash,run_id,input_manifest_hash,result_hash,
                 validation_hash,status,release_path,created_at)
                VALUES ('release','identity',?,'input','result','audit','publishing','fixture','now')""", (run_id,))
            connection.commit()
        with self.assertRaisesRegex(ValueError, 'publishing.*recovery'):
            self.configured().audit(run_id)
        with closing(self.fixture.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_release_validation').fetchone()[0], 1)

    def test_wrong_code_history_is_not_signed_or_written(self):
        from tests.formal_release_refresh_fixtures import put_storage_only_history
        run_id = put_storage_only_history(self.fixture, code_version='b'*40)
        with self.assertRaisesRegex(ValueError, 'candidate_changed'):
            self.configured().audit(run_id)
        with closing(self.fixture.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_release_validation').fetchone()[0], 0)

    def test_audit_trigger_rejected_before_replay(self):
        with closing(self.fixture.store._connect()) as connection:
            connection.execute("""CREATE TRIGGER erase_audit AFTER INSERT ON formal_release_validation
                BEGIN DELETE FROM formal_release_validation WHERE validation_hash=NEW.validation_hash; END""")
            connection.commit()
        with self.assertRaisesRegex(ValueError, 'schema'):
            self.configured().audit('absent')

    def test_changed_audit_table_rejected_before_replay(self):
        with closing(self.fixture.store._connect()) as connection:
            connection.execute('ALTER TABLE formal_release_validation ADD COLUMN extra TEXT')
            connection.commit()
        with self.assertRaisesRegex(ValueError, 'schema'):
            self.configured().audit('absent')

    def test_schema_recheck_sees_trigger_added_after_initial_check(self):
        import inspect
        service = self.configured()
        guard = inspect.getclosurevars(type(service).audit).nonlocals['audit_schema']
        with closing(self.fixture.store._connect()) as connection:
            guard(connection)
        with closing(self.fixture.store._connect()) as connection:
            connection.execute("""CREATE TRIGGER erase_audit AFTER INSERT ON formal_release_validation
                BEGIN DELETE FROM formal_release_validation WHERE validation_hash=NEW.validation_hash; END""")
            connection.commit()
        with self.fixture.store._transaction(immediate=True) as connection:
            with self.assertRaisesRegex(ValueError, 'schema'):
                guard(connection)
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_release_validation').fetchone()[0], 0)

    def test_trigger_cleanup_requires_fresh_database_status_before_retry(self):
        import json
        from unittest.mock import patch
        from pathlib import Path
        from ashare_pipeline import formal_coverage_manifest as coverage
        from tests import formal_release_refresh_fixtures as refresh_fixtures
        from tests.test_formal_final_integration import official_context_coverage_configuration
        _, contract, status = official_context_coverage_configuration(self.fixture)
        original_status = json.loads(status.read_text(encoding='utf-8'))
        root = Path(coverage.__file__).resolve().parent.parent
        # Only Git identity is isolated; real schema, DB/WAL and status checks run.
        def environment():
            return coverage._read_environment(root, self.fixture.db_path, status, expected_schema_version=9)
        with patch.object(coverage, '_read_workspace_git_identity', return_value={'workspace_revision':'a'*40}):
            environment()
            TriggerOnceAuditSigner(self.fixture.store).sign(b'isolated-test', key_id='isolated-audit')
            with closing(self.fixture.store._connect()) as connection:
                connection.execute('DROP TRIGGER erase_audit')
                connection.commit()
            with self.assertRaisesRegex(ValueError, 'database status identity mismatch'):
                environment()
            refresh = getattr(refresh_fixtures, 'refresh_status_after_audit_fixture_cleanup', None)
            self.assertTrue(callable(refresh), 'explicit fixture status refresh is missing')
            refresh(self.fixture, contract=contract, status_path=status)
            environment()
        updated = json.loads(status.read_text(encoding='utf-8'))
        self.assertNotEqual(original_status['db_generation_hash'], updated['db_generation_hash'])
        with closing(self.fixture.store._connect()) as connection:
            for table in ('formal_final_run', 'formal_release_validation', 'formal_release'):
                self.assertEqual(connection.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)
