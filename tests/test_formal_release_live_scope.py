"""Boundary checks for internal replay rechecks; tokens grant no write authority."""
import unittest
import inspect
import threading
from ashare_pipeline import formal_release_validation as module


class LiveReplayBoundaryTests(unittest.TestCase):
    def test_internal_live_recheck_entry_points_exist(self):
        self.assertTrue(callable(getattr(module, '_hold_official_live_evidence', None)))
        self.assertTrue(callable(getattr(module, '_recheck_official_live_evidence', None)))

    def test_forged_or_detached_values_cannot_request_a_recheck(self):
        check = getattr(module, '_recheck_official_live_evidence', None)
        self.assertTrue(callable(check))
        for token in (None, object(), {}, b'proof', 'signed', ('run', 'hash')):
            with self.subTest(token=type(token).__name__):
                with self.assertRaisesRegex(ValueError, 'live replay'):
                    check(token, run_id='run', input_repository=object())

    def test_private_record_checks_owner_run_and_thread_before_recheck(self):
        # White-box predicate test only: this synthetic record is NOT a producer proof.
        check = module._recheck_official_live_evidence
        records = inspect.getclosurevars(check).nonlocals['active_scopes']
        token, owner = object(), object()
        calls = []
        records[id(token)] = (token, 'run', owner, threading.get_ident(), lambda: calls.append(1))
        self.addCleanup(records.pop, id(token), None)
        for run, repository in (('other', owner), ('run', object())):
            with self.assertRaisesRegex(ValueError, 'live replay'):
                check(token, run_id=run, input_repository=repository)
        errors = []
        def other_thread():
            try:
                check(token, run_id='run', input_repository=owner)
            except ValueError as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()
        self.assertEqual(len(errors), 1)
        self.assertEqual(calls, [])
        records.pop(id(token))
        with self.assertRaisesRegex(ValueError, 'live replay'):
            check(token, run_id='run', input_repository=owner)
        self.assertEqual(calls, [])

    def test_replaced_live_generator_body_is_rejected(self):
        body = inspect.getclosurevars(module._hold_official_live_evidence).nonlocals['func']
        original = body.__code__
        body.__code__ = original.replace(co_consts=original.co_consts + ('tampered',))
        try:
            with self.assertRaisesRegex(ValueError, 'authority changed'):
                module._recheck_official_live_evidence(object(), run_id='run', input_repository=object())
        finally:
            body.__code__ = original

    def test_failed_recheck_permanently_revokes_scope(self):
        check = module._recheck_official_live_evidence
        records = inspect.getclosurevars(check).nonlocals['active_scopes']
        token, owner = object(), object()
        def changed():
            raise ValueError('source changed')
        records[id(token)] = (token, 'run', owner, threading.get_ident(), changed)
        self.addCleanup(records.pop, id(token), None)
        with self.assertRaisesRegex(ValueError, 'source changed'):
            check(token, run_id='run', input_repository=owner)
        with self.assertRaisesRegex(ValueError, 'live replay'):
            check(token, run_id='run', input_repository=owner)
