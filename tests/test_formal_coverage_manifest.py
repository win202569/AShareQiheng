import hashlib
import unittest

from ashare_pipeline.formal_coverage_manifest import (
    COVERAGE_CLASSES, CoverageRequirement, FormalCoverageAuditor,
)


def req(domain="financial", sid="SH600000", exchange="SH"):
    return CoverageRequirement("frozen", sid, domain, "selector", "2025", exchange, ("CNY",))


def good(r, cls="verified_complete", **extra):
    return dict(r.to_dict(), coverage_class=cls, authenticated=True,
                explicit_source_statement=True, units_ok=True,
                parser_mapping_ok=True, evidence_hashes={"content": "h"},
                source="official", dataset="annual_report", request_fingerprint="request",
                selected_snapshot_id="snapshot", content_sha256="content",
                manifest_sha256="manifest", parser_id="parser", parser_version="1",
                mapping_version="1", published_at_utc="2026-08-01T00:00:00+00:00",
                effective_at_utc="2026-08-01T00:00:00+00:00",
                verification_state="verified", temporal_state="visible",
                observed_units=list(r.expected_units), **extra)


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
        with self.assertRaisesRegex(ValueError, "nonempty"):
            FormalCoverageAuditor().audit([])
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

    def test_sparse_verified_row_is_blocked_even_when_callback_accepts_it(self):
        r = req(); auditor = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True})
        for absent in ("source", "dataset", "request_fingerprint", "selected_snapshot_id",
                       "content_sha256", "manifest_sha256", "parser_id", "parser_version",
                       "mapping_version", "published_at_utc", "effective_at_utc",
                       "verification_state", "temporal_state", "observed_units"):
            with self.subTest(absent=absent):
                row = good(r)
                row.pop(absent)
                manifest = auditor.audit([r], [row])
                self.assertEqual(manifest.rows[0]["coverage_class"], "blocked_integrity")

    def test_verified_row_contains_required_audit_projection(self):
        r = req(); auditor = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True})
        row = auditor.audit([r], [good(r)]).rows[0]
        for field in ("required", "applicability_rule_hash", "source", "dataset",
                      "request_fingerprint", "refresh_generation", "task_id",
                      "collection_state", "selected_snapshot_id", "content_sha256",
                      "manifest_sha256", "parser_id", "parser_version", "mapping_version",
                      "published_at_utc", "effective_at_utc", "captured_at_utc",
                      "source_updated_at_utc", "expected_units", "observed_units",
                      "missing_units", "verification_state", "temporal_state",
                      "coverage_class", "reason_codes", "evidence_hashes", "rechecked_at_utc"):
            with self.subTest(field=field):
                self.assertIn(field, row)

    def test_manifest_hash_matches_exported_canonical_bytes(self):
        r = req(); auditor = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True})
        manifest = auditor.audit([r], [good(r)])
        self.assertEqual(hashlib.sha256(manifest.canonical_bytes()).hexdigest(), manifest.manifest_hash)

    def test_source_cannot_clear_required_flag_or_hash_recheck_time(self):
        r = req(); auditor = FormalCoverageAuditor(repository_validators={"financial": lambda *_: True})
        first = auditor.audit([r], [good(r, required=False,
                                         rechecked_at_utc="2026-10-01T00:00:00+00:00")])
        second = auditor.audit([r], [good(r, required=False,
                                          rechecked_at_utc="2026-10-02T00:00:00+00:00")])
        self.assertTrue(first.rows[0]["required"])
        self.assertEqual(first.manifest_hash, second.manifest_hash)


if __name__ == "__main__": unittest.main()
