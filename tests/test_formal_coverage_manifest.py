import unittest

from ashare_pipeline.formal_coverage_manifest import (
    COVERAGE_CLASSES, CoverageRequirement, FormalCoverageAuditor,
)


def req(domain="financial", sid="SH600000", exchange="SH"):
    return CoverageRequirement("frozen", sid, domain, "selector", "2025", exchange, ("CNY",))


def good(r, cls="verified_complete", **extra):
    return dict(r.to_dict(), coverage_class=cls, authenticated=True,
                explicit_source_statement=True, units_ok=True,
                parser_mapping_ok=True, evidence_hashes={"content": "h"}, **extra)


class CoverageManifestTests(unittest.TestCase):
    def test_absent_record_is_blocked_not_verified_no_coverage(self):
        m = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True}).audit([req()])
        self.assertEqual(m.rows[0]["coverage_class"], "missing")
        with self.assertRaises(ValueError): m.require_preview_ready()

    def test_verified_no_coverage_requires_authenticated_explicit_source_statement(self):
        r = req(); auditor = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True})
        self.assertEqual(auditor.audit([r], [dict(r.to_dict(), coverage_class="verified_no_coverage")]).rows[0]["coverage_class"], "blocked_integrity")
        row = auditor.audit([r], [good(r, "verified_no_coverage")]).rows[0]
        self.assertEqual(row["coverage_class"], "verified_no_coverage")

    def test_missing_table_is_blocked_schema_not_zero_rows(self):
        r = req(); m = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True}).audit([r], [good(r, table_missing=True)])
        self.assertEqual(m.rows[0]["coverage_class"], "blocked_schema")

    def test_exchange_calendar_cannot_be_reused_across_sh_sz_bj(self):
        r = req("trading_calendar", exchange="SH")
        record = dict(r.to_dict(), exchange="SZ", coverage_class="verified_complete")
        m = FormalCoverageAuditor(repository_validators={"trading_calendar": lambda *_: True}).audit([r], [record])
        self.assertEqual(m.rows[0]["coverage_class"], "blocked_identity")

    def test_every_required_member_domain_key_is_unique_and_enumerated(self):
        r = req()
        with self.assertRaisesRegex(ValueError, "unique"):
            FormalCoverageAuditor().audit([r, r])
        self.assertEqual(len(COVERAGE_CLASSES), 15)
        self.assertEqual(len(set(COVERAGE_CLASSES)), 15)

    def test_sql_counts_are_diagnostic_only_and_never_grant_readiness(self):
        r = req(); m = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True}).audit(
            [r], db_diagnostics={"rows": 999})
        self.assertEqual(m.rows[0]["coverage_class"], "missing")

    def test_audit_time_and_timing_diagnostics_do_not_change_canonical_hash(self):
        r = req(); a = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True})
        x = a.audit([r], [good(r)], audit_at_utc="2026-10-01T00:00:00+00:00", timing_diagnostics={"ms": 1})
        y = a.audit([r], [good(r)], audit_at_utc="2026-10-02T00:00:00+00:00", timing_diagnostics={"ms": 999})
        self.assertEqual(x.manifest_hash, y.manifest_hash)


if __name__ == "__main__": unittest.main()
