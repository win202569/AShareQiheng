"""Current range absence must remain tied to its genuine request."""

import unittest

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


if __name__ == "__main__":
    unittest.main()
