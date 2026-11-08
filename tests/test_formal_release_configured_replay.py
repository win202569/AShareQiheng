"""Configured replay cannot accept caller-provided evidence or skip controls."""
from contextlib import closing
import unittest
from unittest.mock import patch
from tests import test_formal_release_input_refresh as fixtures


class ConfiguredReleaseReplayTests(unittest.TestCase):
    setUp = fixtures.ReleaseInputRefreshTests.setUp
    service = fixtures.ReleaseInputRefreshTests.service

    def test_missing_history_rejected_without_writes(self):
        with self.assertRaisesRegex(ValueError, 'candidate.*not found'):
            with self.service().hold_replay('absent'):
                self.fail('missing history entered replay')
        with closing(self.fixture.store._connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_final_run').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM formal_release_validation').fetchone()[0], 0)

    def test_only_run_selector_is_accepted(self):
        service = self.service()
        for selector in ('', ' ', object(), {'run_id': 'original'}):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                with service.hold_replay(selector):
                    self.fail('invalid selector accepted')
        for override in ('coverage_manifest', 'skip_official', 'source_guard', 'callback'):
            with self.subTest(override=override), self.assertRaises(TypeError):
                service.hold_replay('absent', **{override: object()})

    def test_open_circuit_rejected_before_expensive_refresh(self):
        self.fixture.store.set_formal_source_circuit('probe', state='open', failure_count=1,
            reason={'code': 'source_failed'}, opened_at_utc='2026-08-30T00:00:00+00:00',
            retry_after_utc='2026-08-30T01:00:00+00:00')
        with self.assertRaisesRegex(ValueError, 'job_quiescence.*open'):
            with self.service().hold_replay('absent'):
                self.fail('open circuit accepted')

    def test_job_reader_replacement_rejected(self):
        service = self.service()
        with patch.object(self.module, '_read_job_quiescence', return_value=(b'{}', ())):
            with self.assertRaisesRegex(ValueError, 'authority|entry point'):
                with service.hold_replay('absent'):
                    self.fail('counterfeit job reader accepted')

    def test_replay_entry_replacement_rejected(self):
        service = self.service()
        with patch.object(self.module, '_hold_official_candidate', return_value=None):
            with self.assertRaisesRegex(ValueError, 'authority|entry point'):
                with service.hold_replay('absent'):
                    self.fail('counterfeit replay accepted')

    def test_delayed_entry_rechecks_configuration(self):
        service = self.service()
        context = service.hold_replay('absent')
        self.runs.get_run = lambda run_id: None
        with self.assertRaisesRegex(ValueError, 'entry point'):
            with context:
                self.fail('changed repository accepted')

    def test_held_generator_body_replacement_rejected(self):
        service = self.service()
        body = type(service).hold_replay.__wrapped__
        original = body.__code__
        def counterfeit(*args):
            raise AssertionError('counterfeit executed')
            yield
        try:
            body.__code__ = counterfeit.__code__.replace(co_freevars=original.co_freevars)
            with self.assertRaisesRegex(ValueError, 'authority|entry point'):
                service.hold_replay('absent')
        finally:
            body.__code__ = original

    def test_held_generator_closure_rebinding_rejected(self):
        service = self.service()
        wrapper = type(service).hold_replay
        cell = wrapper.__closure__[wrapper.__code__.co_freevars.index('func')]
        original = cell.cell_contents
        try:
            cell.cell_contents = lambda *args: None
            with self.assertRaisesRegex(ValueError, 'authority|entry point'):
                service.hold_replay('absent')
        finally:
            cell.cell_contents = original

    def test_job_reader_code_mutation_rejected(self):
        service = self.service()
        function = self.module._read_job_quiescence
        original = function.__code__
        def counterfeit(*args):
            return b'{}', ()
        try:
            function.__code__ = counterfeit.__code__
            with self.assertRaisesRegex(ValueError, 'authority|entry point'):
                service.hold_replay('absent')
        finally:
            function.__code__ = original

    def test_replay_generator_body_mutation_rejected(self):
        service = self.service()
        body = self.module._hold_official_candidate.__wrapped__
        original = body.__code__
        def counterfeit(*args):
            yield {}, ()
        try:
            body.__code__ = counterfeit.__code__.replace(co_freevars=original.co_freevars)
            with self.assertRaisesRegex(ValueError, 'authority|entry point'):
                service.hold_replay('absent')
        finally:
            body.__code__ = original

    def test_job_encoder_replacement_rejected(self):
        service = self.service()
        with patch.object(self.module.jobs_module, 'canonical_release_bytes', return_value=b'{}'):
            with self.assertRaisesRegex(ValueError, 'authority|entry point'):
                service.hold_replay('absent')
