"""Current range absence must remain tied to its genuine request."""

import unittest
import sys

from ashare_pipeline.formal_batch_read_journal import FormalBatchReadJournal
from tests.formal_range_fixtures import RangeStoreFixture


FREEZE = "2026-08-31T07:00:00+00:00"


class RangeAbsenceTicketTests(unittest.TestCase):
    def setUp(self):
        self.fixture = RangeStoreFixture()
        self.addCleanup(self.fixture.close)

    def test_genuine_absence_is_covered_and_new_candidate_revokes_it(self):
        fixture = self.fixture
        request = fixture.source.first_calendar_request(FREEZE)
        fingerprint = request.request_fingerprint
        journal = FormalBatchReadJournal.open(fixture.range_store,
            registry_manifest_hash=request.registry_manifest_hash, as_of_utc=FREEZE,
            population=(fingerprint,), required_keys=((fingerprint,),))
        ticket = fixture.range_store.select_current_batch_ticket(journal, fingerprint,
            request=request)
        self.assertIsNone(ticket.selected())
        journal.checkpoint()
        fixture.produce_calendar(days={"2026-08-31": True})
        journal.next_phase()
        with self.assertRaises(ValueError):
            journal.checkpoint()

    def test_absent_continuation_binds_parent_candidate_and_source(self):
        fixture = self.fixture
        parent = fixture.produce_calendar(days={"2026-08-31": True})[0]
        request = fixture.source.previous_calendar_request(parent)
        fingerprint = request.request_fingerprint
        journal = FormalBatchReadJournal.open(fixture.range_store,
            registry_manifest_hash=request.registry_manifest_hash, as_of_utc=FREEZE,
            population=(fingerprint,), required_keys=((fingerprint,),))
        ticket = fixture.range_store.select_current_batch_ticket(journal, fingerprint,
            request=request)
        self.assertIsNone(ticket.selected())
        journal.checkpoint()
        fixture.produce_calendar(days={"2026-08-31": True}, generation="g2")
        journal.next_phase()
        with self.assertRaises(ValueError):
            journal.checkpoint()

    def test_parent_conflict_at_execution_return_cannot_become_absence_baseline(self):
        fixture = self.fixture
        parent = fixture.produce_calendar(days={"2026-08-31": True}, generation="g1")[0]
        request = fixture.source.previous_calendar_request(parent)
        fingerprint = request.request_fingerprint
        journal = FormalBatchReadJournal.open(fixture.range_store,
            registry_manifest_hash=request.registry_manifest_hash, as_of_utc=FREEZE,
            population=(fingerprint,), required_keys=((fingerprint,),))
        def inject(frame, event, arg):
            if (event == "return" and frame.f_code.co_name == "require_execution"
                    and frame.f_code.co_filename.endswith("formal_range_source.py")):
                sys.setprofile(None)
                fixture.produce_calendar(days={"2026-08-31": False}, generation="g2")
        sys.setprofile(inject)
        try:
            with self.assertRaises(ValueError):
                fixture.range_store.select_current_batch_ticket(journal, fingerprint,
                    request=request)
        finally:
            sys.setprofile(None)
        with self.assertRaises(ValueError):
            parent.require_current()


if __name__ == "__main__":
    unittest.main()
