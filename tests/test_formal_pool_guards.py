import unittest
from decimal import Decimal
from types import SimpleNamespace

from ashare_pipeline.formal_pool import _select_detached_rows, select_formal_pools


class FormalPoolGuardTests(unittest.TestCase):
    def test_plain_dto_and_detached_rows_are_not_public_inputs(self):
        with self.assertRaises(ValueError):
            select_formal_pools(SimpleNamespace(security_ids=("SH000001",)))
        with self.assertRaises(ValueError):
            _select_detached_rows([{"security_id": "SH000001"}])

    def test_rejects_duplicate_missing_unknown_and_noncanonical_security_ids(self):
        base = {"security_id": "SH000001", "secondary_industry": "i", "state": "formal_scored",
            "strong_qualified": True, "wait_qualified": False,
            "sort_fields": {"Sc": Decimal("70"), "B": Decimal("65"), "C": Decimal(".75"), "R_safety": Decimal("45"), "V": Decimal("45")},
            "eligibility_hash": "h", "source_entry_hash": "e", "source_batch_hash": "b", "score_batch_hash": "s"}
        with self.assertRaises(ValueError):
            _select_detached_rows([base, dict(base)])
        with self.assertRaises(ValueError):
            _select_detached_rows([dict(base, security_id="sh000001")])
        with self.assertRaises(ValueError):
            _select_detached_rows([dict(base, secondary_industry=None)])

    def test_rejects_float_bool_nan_infinity_and_unknown_sort_keys(self):
        base = {"security_id": "SH000001", "secondary_industry": "i", "state": "formal_scored",
            "strong_qualified": True, "wait_qualified": False,
            "sort_fields": {"Sc": Decimal("70"), "B": Decimal("65"), "C": Decimal(".75"), "R_safety": Decimal("45"), "V": Decimal("45")},
            "eligibility_hash": "h", "source_entry_hash": "e", "source_batch_hash": "b", "score_batch_hash": "s"}
        for value in (1.0, True, Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _select_detached_rows([dict(base, sort_fields=dict(base["sort_fields"], Sc=value))])
        with self.assertRaises(ValueError):
            _select_detached_rows([dict(base, sort_fields=dict(base["sort_fields"], X=Decimal("1")))])

    def test_rejects_cross_batch_and_trace_hash_tampering(self):
        base = {"security_id": "SH000001", "secondary_industry": "i", "state": "formal_scored",
            "strong_qualified": True, "wait_qualified": False,
            "sort_fields": {"Sc": Decimal("70"), "B": Decimal("65"), "C": Decimal(".75"), "R_safety": Decimal("45"), "V": Decimal("45")},
            "eligibility_hash": "h", "source_entry_hash": "e", "source_batch_hash": "b", "score_batch_hash": "s"}
        with self.assertRaises(ValueError):
            _select_detached_rows([base, dict(base, security_id="SH000002", source_batch_hash="other")])
        with self.assertRaises(ValueError):
            _select_detached_rows([dict(base, eligibility_hash="")])


if __name__ == "__main__":
    unittest.main()
