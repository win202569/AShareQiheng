"""State ticket binds actual state selection to current Context tickets."""

import sys
import unittest
from unittest.mock import patch

from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal
from ashare_pipeline.formal_policy_state import FormalPolicyStateRepository
from tests.formal_metric_fixtures import FREEZE
from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture


class PolicyStateTicketTests(unittest.TestCase):
    def setUp(self):
        self.fixture = PolicyRuntimeFixture()
        self.addCleanup(self.fixture.close)

    def test_absent_context_and_late_candidate(self):
        fixture = self.fixture
        repository = FormalPolicyStateRepository(fixture.context)
        root = fixture.bundle.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(repository, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        ticket = repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
            template_id="bank", policy_registry=fixture.policy_registry)
        self.assertTrue(ticket.selected().values)
        banned = {type(repository).select.__code__}
        checked = type(repository)._batch_recheck_ticket.__code__
        calls = []
        checks = []
        def profile(frame, event, arg):
            if event == "call" and frame.f_code in banned:
                calls.append(frame.f_code.co_name)
            if event == "call" and frame.f_code is checked:
                checks.append(1)
        sys.setprofile(profile)
        try:
            journal.checkpoint()
            journal.checkpoint()
            journal.next_phase()
            journal.checkpoint()
        finally:
            sys.setprofile(None)
        self.assertEqual(calls, [])
        self.assertEqual(len(checks), 2)
        fixture.put_policy_context("SH600000", "security_state", dict(
            is_st=False, is_star_st=False, listing_status="listed",
            forced_delist_risk=False, suspended=False))
        journal.next_phase()
        with self.assertRaises(ValueError):
            journal.checkpoint()

    def test_preopen_and_warm_checker_replacement_are_rejected(self):
        fixture = self.fixture
        repository = FormalPolicyStateRepository(fixture.context)
        root = fixture.bundle.manifest.manifest_hash
        args = dict(registry_manifest_hash=root, as_of_utc=FREEZE,
            population=("SH600000",), required_keys=(("SH600000",),))
        with patch.object(type(repository), "_batch_recheck_ticket", lambda *_: None):
            with self.assertRaises(ValueError):
                FormalBatchReadJournal.open(repository, **args)
        journal = FormalBatchReadJournal.open(repository, **args)
        repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
            template_id="bank", policy_registry=fixture.policy_registry)
        journal.checkpoint()
        with patch.object(type(repository), "_batch_recheck_ticket", lambda *_: None):
            with self.assertRaises(ValueError):
                journal.checkpoint()

    def test_two_members_cover_one_frozen_state_scope(self):
        fixture = self.fixture
        repository = FormalPolicyStateRepository(fixture.context)
        members = ("SH600000", "SZ000001")
        journal = FormalBatchReadJournal.open(repository,
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
            as_of_utc=FREEZE, population=members,
            required_keys=tuple((item,) for item in members))
        for member in members:
            repository.select_current_batch_ticket(journal, member, FREEZE,
                template_id="bank", policy_registry=fixture.policy_registry)
        journal.finalize()


if __name__ == "__main__":
    unittest.main()
