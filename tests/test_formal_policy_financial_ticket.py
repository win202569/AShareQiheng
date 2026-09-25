"""Financial ticket owns the selected PolicyFeatureState and industry identity."""

import sys
import unittest

from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal
from ashare_pipeline import formal_feature_repository as feature_module
from tests.formal_metric_fixtures import FREEZE
from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture


class PolicyFinancialTicketTests(unittest.TestCase):
    def setUp(self):
        self.fixture = PolicyRuntimeFixture()
        self.addCleanup(self.fixture.close)

    def test_absent_receipt_is_current_and_checkpoint_does_not_rebuild(self):
        fixture = self.fixture
        fixture.put_industry("SH600000")
        universe = fixture.policy_context_repository.load_universe(fixture.frozen.frozen_input_hash,
            scoring_registry=fixture.scoring)
        industry = fixture.policy_context_repository.resolve_industries(universe)
        repository = fixture.policy_financial_repository
        root = fixture.bundle.manifest.manifest_hash
        journal = FormalBatchReadJournal.open(repository, registry_manifest_hash=root,
            as_of_utc=FREEZE, population=("SH600000",),
            required_keys=(("SH600000",),))
        ticket = repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
            template_id="bank", policy_registry=fixture.policy_registry,
            industry_batch=industry)
        self.assertTrue(ticket.selected().values)
        banned = {type(repository).select.__code__,
                  type(fixture.feature_repository).select_current_verified_policy_feature_state.__code__,
                  feature_module.build_formal_feature_bundle.__code__,
                  feature_module.evaluate_selected_features.__code__}
        calls = []
        def profile(frame, event, arg):
            if event == "call" and frame.f_code in banned:
                calls.append(frame.f_code.co_name)
        sys.setprofile(profile)
        try:
            journal.checkpoint()
        finally:
            sys.setprofile(None)
        self.assertEqual(calls, [])
        journal.finalize()

    def test_receipt_inserted_at_financial_return_cannot_be_ticket_baseline(self):
        fixture = self.fixture
        fixture.put_policy_financial("SH600000", {"fixture.policy.current.equity": -1},
            fy_end="2025-12-31", units={"fixture.policy.current.equity": "CNY"},
            persist=False)
        fixture.put_industry("SH600000")
        universe = fixture.policy_context_repository.load_universe(fixture.frozen.frozen_input_hash,
            scoring_registry=fixture.scoring)
        industry = fixture.policy_context_repository.resolve_industries(universe)
        repository = fixture.policy_financial_repository
        journal = FormalBatchReadJournal.open(repository,
            registry_manifest_hash=fixture.bundle.manifest.manifest_hash,
            as_of_utc=FREEZE, population=("SH600000",), required_keys=(("SH600000",),))
        selected_code = type(repository).select.__code__
        def inject(frame, event, arg):
            if event == "return" and frame.f_code is selected_code:
                sys.setprofile(None)
                fixture.persist_features("SH600000")
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                repository.select_current_batch_ticket(journal, "SH600000", FREEZE,
                    template_id="bank", policy_registry=fixture.policy_registry,
                    industry_batch=industry)
        finally:
            sys.setprofile(None)


if __name__ == "__main__":
    unittest.main()
