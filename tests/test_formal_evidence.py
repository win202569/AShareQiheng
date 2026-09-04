import unittest

from ashare_pipeline.formal_evidence import (
    OfficialFetch,
    OfficialRequest,
    SourcePolicy,
    VerifiedCalendarBinding,
    verify_official_fetch,
)


def verified_calendar_binding(
    *, manifest_sha256: str, exchange: str, freeze_at_utc: str, registry_manifest_hash: str
) -> VerifiedCalendarBinding:
    return VerifiedCalendarBinding(
        snapshot_id="calendar-snapshot-1",
        manifest_sha256=manifest_sha256,
        exchange=exchange,
        freeze_at_utc=freeze_at_utc,
        registry_manifest_hash=registry_manifest_hash,
        selector_hash="s" * 64,
        prerequisite_task_id="calendar-task-1",
    )


def timestamp_fetch(*, request: OfficialRequest | None = None) -> OfficialFetch:
    return OfficialFetch(
        request=request
        or OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31"),
        raw_bytes=b"%PDF-1.7 official",
        original_url="https://static.cninfo.com.cn/finalpage/2026-03-20/123.pdf",
        published_at_utc="2026-03-20T08:00:00+00:00",
        published_precision="timestamp",
        source_updated_at_utc=None,
        captured_at_utc="2026-09-04T08:00:00+00:00",
        effective_at_utc="2026-03-20T08:00:00+00:00",
        effective_time_evidence_hash=None,
        refresh_generation="fixture-index-v1",
        parser_id="cninfo-pdf",
        parser_version="cninfo-pdf-v1",
        mapping_version="cninfo-annual-v1",
        declared_security_id="SZ000001",
        declared_period="2025-12-31",
    )


def date_only_fetch(*, exchange: str, effective_time_evidence_hash: str) -> OfficialFetch:
    return OfficialFetch(
        request=OfficialRequest(
            "cninfo", "halfyear_report", "SZ000001", "2026-06-30", exchange=exchange
        ),
        raw_bytes=b"report",
        original_url="https://www.cninfo.com.cn/new/disclosure/detail",
        published_at_utc="2026-08-30T00:00:00+00:00",
        published_precision="date_only",
        source_updated_at_utc=None,
        captured_at_utc="2026-09-04T08:00:00+00:00",
        effective_at_utc="2026-08-30T07:00:00+00:00",
        effective_time_evidence_hash=effective_time_evidence_hash,
        refresh_generation="fixture-index-v1",
        parser_id="cninfo-pdf",
        parser_version="cninfo-pdf-v1",
        mapping_version="cninfo-halfyear-v1",
        declared_security_id="SZ000001",
        declared_period="2026-06-30",
    )


class FormalEvidenceTests(unittest.TestCase):
    def test_verified_cninfo_pdf_requires_allowlisted_url_identity_and_timestamp(self):
        fetch = timestamp_fetch()

        result = verify_official_fetch(fetch, SourcePolicy.cninfo())

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.content_sha256, fetch.content_sha256)

    def test_third_party_and_wrong_host_cannot_be_verified(self):
        request = OfficialRequest("akshare", "daily", "SZ000001", "2026-08-31")
        third_party = OfficialFetch.minimal(
            request,
            b"rows",
            "https://example.invalid/rows",
            "2026-08-31T07:00:00+00:00",
            "timestamp",
            refresh_generation="fixture-index-v1",
        )

        result = verify_official_fetch(third_party, SourcePolicy.cninfo())

        self.assertEqual(result.status, "rejected")
        self.assertIn("source_not_authoritative", result.reasons)

    def test_future_publication_is_not_visible_even_if_captured_later(self):
        fetch = OfficialFetch.minimal(
            OfficialRequest("cninfo", "halfyear_report", "SZ000001", "2026-06-30"),
            b"report",
            "https://www.cninfo.com.cn/new/disclosure/detail",
            "2026-08-31T07:01:00+00:00",
            "timestamp",
            refresh_generation="fixture-index-v1",
        )

        result = verify_official_fetch(fetch, SourcePolicy.cninfo())

        self.assertEqual(result.status, "verified")
        self.assertFalse(result.visible_at("2026-08-31T07:00:00+00:00"))

    def test_date_only_fetch_rejects_a_different_verified_calendar_binding(self):
        binding = verified_calendar_binding(
            manifest_sha256="c" * 64,
            exchange="SZ",
            freeze_at_utc="2026-08-31T07:00:00+00:00",
            registry_manifest_hash="r" * 64,
        )
        fetch = date_only_fetch(
            exchange="SZ", effective_time_evidence_hash=binding.manifest_sha256
        )

        self.assertEqual(
            verify_official_fetch(
                fetch, SourcePolicy.cninfo(), calendar_binding=binding
            ).status,
            "verified",
        )
        other_verified_calendar = verified_calendar_binding(
            manifest_sha256="d" * 64,
            exchange="SZ",
            freeze_at_utc=binding.freeze_at_utc,
            registry_manifest_hash=binding.registry_manifest_hash,
        )
        rejected = verify_official_fetch(
            fetch, SourcePolicy.cninfo(), calendar_binding=other_verified_calendar
        )

        self.assertEqual(rejected.status, "rejected")
        self.assertIn("calendar_binding_mismatch", rejected.reasons)

    def test_rejects_invalid_identity_and_keeps_reasons_sorted(self):
        fetch = timestamp_fetch(
            request=OfficialRequest("cninfo", "annual_report", "SZ00001", "2025-12-31")
        )
        fetch = OfficialFetch(
            **{**fetch.__dict__, "raw_bytes": b"", "parser_id": "", "declared_security_id": "SZ000001"}
        )

        result = verify_official_fetch(fetch, SourcePolicy.cninfo())

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, tuple(sorted(result.reasons)))
        self.assertIn("empty_payload", result.reasons)
        self.assertIn("invalid_security_id", result.reasons)
        self.assertIn("parser_id_missing", result.reasons)

    def test_timestamp_fetch_rejects_calendar_material_and_naive_times(self):
        fetch = timestamp_fetch()
        binding = verified_calendar_binding(
            manifest_sha256="c" * 64,
            exchange="SZ",
            freeze_at_utc="2026-08-31T07:00:00+00:00",
            registry_manifest_hash="r" * 64,
        )
        malformed = OfficialFetch(
            **{
                **fetch.__dict__,
                "published_at_utc": "2026-03-20T08:00:00",
                "effective_time_evidence_hash": binding.manifest_sha256,
            }
        )

        result = verify_official_fetch(
            malformed, SourcePolicy.cninfo(), calendar_binding=binding
        )

        self.assertEqual(result.status, "rejected")
        self.assertIn("naive_timestamp", result.reasons)
        self.assertIn("timestamp_calendar_binding_forbidden", result.reasons)
        self.assertIn("timestamp_effective_time_evidence_forbidden", result.reasons)

    def test_rejects_missing_required_capture_timestamp(self):
        fetch = timestamp_fetch()
        missing_capture_time = OfficialFetch(
            **{**fetch.__dict__, "captured_at_utc": None}
        )

        result = verify_official_fetch(missing_capture_time, SourcePolicy.cninfo())

        self.assertEqual(result.status, "rejected")
        self.assertIn("invalid_timestamp", result.reasons)


if __name__ == "__main__":
    unittest.main()
