"""Public audit validation is run-only and cannot grant publication rights."""
import unittest
from unittest.mock import patch
from contextlib import closing
from tests import test_formal_release_input_refresh as fixtures


class ReleaseValidatorBoundaryTests(unittest.TestCase):
    setUp = fixtures.ReleaseInputRefreshTests.setUp

    def validator(self):
        from ashare_pipeline.formal_release_validator import FormalReleaseValidator
        return FormalReleaseValidator(**self.configuration)

    def test_missing_run_does_not_write_audit_or_candidate_rows(self):
        with self.assertRaisesRegex(ValueError,'candidate.*not found'):
            self.validator().validate('absent')
        with closing(self.fixture.store._connect()) as connection:
            for table in ('formal_final_run','formal_release_validation','formal_release'):
                self.assertEqual(connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_validate_has_no_publication_or_evidence_overrides(self):
        service=self.validator()
        for key in ('purpose','gates','renderer','coverage_manifest','source_dependency_hash','skip_gate'):
            with self.subTest(key=key),self.assertRaises(TypeError):
                service.validate('absent',**{key:'caller'})

    def test_replaced_renderer_is_rejected_before_replay(self):
        service=self.validator()
        with patch.object(self.module.render_module,'_render_release_package',return_value={}):
            with self.assertRaisesRegex(ValueError,'authority|entry point'):
                service.validate('absent')

    def test_changed_renderer_version_is_rejected(self):
        service=self.validator()
        with patch.object(self.module.render_module,'_RENDERER_VERSION','caller'):
            with self.assertRaisesRegex(ValueError,'authority|entry point'):
                service.validate('absent')

    def test_renderer_helper_code_mutation_is_rejected(self):
        service=self.validator()
        function=self.module.render_module._render_scorecard_payloads
        original=function.__code__
        def counterfeit(*args):
            return {}
        try:
            function.__code__=counterfeit.__code__
            with self.assertRaisesRegex(ValueError,'authority|entry point'):
                service.validate('absent')
        finally:
            function.__code__=original

    def test_missing_or_future_schema_ledger_is_rejected_without_repair(self):
        service=self.validator()
        with closing(self.fixture.store._connect()) as connection:
            connection.execute('DELETE FROM schema_migration WHERE version=9')
            connection.commit()
        with self.assertRaisesRegex(ValueError,'schema'):
            service.validate('absent')
        with closing(self.fixture.store._connect()) as connection:
            self.assertIsNone(connection.execute('SELECT version FROM schema_migration WHERE version=9').fetchone())
            connection.execute("INSERT INTO schema_migration VALUES(10,'test')")
            connection.commit()
        with self.assertRaisesRegex(ValueError,'schema'):
            service.validate('absent')
