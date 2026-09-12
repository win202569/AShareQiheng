"""Authenticated bounded calendar range request, transport, and parser tests."""

import copy
import hashlib
import subprocess
import sys
import textwrap
import unittest

from ashare_pipeline.formal_sources import (
    FormalRetryableSourceError,
    FormalSourceBlocked,
    FormalTerminalSourceError,
    SignedSourceRegistry,
    TransportResponse,
)
from tests.formal_range_fixtures import RangeSourceFixture, range_entry


FREEZE = "2026-08-31T07:00:00+00:00"


def document_wire(request, **changes):
    request_wire = request.to_dict()
    row = {
        "date": "2026-08-29",
        "is_open": False,
        "published_at_utc": "2026-08-29T08:00:00+00:00",
        "published_precision": "timestamp",
        "effective_at_utc": "2026-08-29T08:00:00+00:00",
        "effective_time_evidence_hash": None,
        "captured_at_utc": "2026-08-31T06:59:00+00:00",
    }
    wire = {
        "schema_version": "formal-parsed-range-document-v1",
        "request_fingerprint": request.request_fingerprint,
        "source": request_wire["source"],
        "dataset": request_wire["dataset"],
        "security_id": request_wire["security_id"],
        "exchange": request_wire["exchange"],
        "start_date": request_wire["start_date"],
        "end_date": request_wire["end_date"],
        "parser_id": "fixture-range-parser",
        "parser_version": "fixture-range-v1",
        "mapping_version": "fixture-range-map-v1",
        "normalizer_version": "fixture-range-normalizer-v1",
        "request_version": "formal-range-request-v1",
        "published_at_utc": "2026-08-29T08:00:00+00:00",
        "published_precision": "timestamp",
        "source_updated_at_utc": "2026-08-30T08:00:00+00:00",
        "effective_at_utc": "2026-08-29T08:00:00+00:00",
        "effective_time_evidence_hash": None,
        "captured_at_utc": "2026-08-31T06:59:00+00:00",
        "upstream_generation": "fixture-calendar-release-2026-08-30",
        "pagination_evidence": "signed_single_response_v1",
        "page_index": 1,
        "page_count": 1,
        "record_count": 1,
        "page_record_count": 1,
        "coverage": {
            "start_date": request_wire["start_date"],
            "end_date": request_wire["end_date"],
            "complete": True,
        },
        "rows": [row],
    }
    wire.update(changes)
    return wire


class FormalRangeSourceTests(unittest.TestCase):
    def fixture(self, **kwargs):
        fixture = RangeSourceFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def test_first_calendar_request_needs_no_existing_calendar(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        wire = request.to_dict()
        self.assertEqual(wire["end_date"], "2026-08-31")
        self.assertEqual(wire["start_date"], "2025-07-28")
        self.assertEqual(wire["page_index"], 1)
        self.assertIsNone(wire["security_id"])
        self.assertIsNone(wire["calendar_coverage_hash"])
        self.assertEqual(len(request.request_fingerprint), 64)

    def test_backward_interval_is_inclusive_and_stops_at_iso_floor(self):
        from ashare_pipeline.formal_range_source import backward_interval

        self.assertEqual(backward_interval("2026-08-31", 400), ("2025-07-28", "2026-08-31"))
        self.assertEqual(backward_interval("0001-01-03", 10), ("0001-01-01", "0001-01-03"))
        for bad in (True, 1.0, 0, -1):
            with self.subTest(limit=bad), self.assertRaises(ValueError):
                backward_interval("2026-08-31", bad)
        for bad in (None, "2026-8-31", "2026-02-30"):
            with self.subTest(end=bad), self.assertRaises((TypeError, ValueError)):
                backward_interval(bad, 1)

    def test_page_successor_requires_source_backed_exact_page_identity(self):
        from ashare_pipeline.formal_range_source import page_successor

        self.assertEqual(page_successor({"page_index": 1, "page_count": 2}, 2), 2)
        self.assertIsNone(page_successor({"page_index": 2, "page_count": 2}, 2))
        for document, maximum in (
            ({"page_index": True, "page_count": 1}, 1),
            ({"page_index": 0, "page_count": 1}, 1),
            ({"page_index": 2, "page_count": 1}, 2),
            ({"page_index": 1, "page_count": 3}, 2),
            ({"page_index": 1, "page_count": 1}, True),
        ):
            with self.subTest(document=document, maximum=maximum), self.assertRaises(ValueError):
                page_successor(document, maximum)

    def test_request_dates_and_freeze_are_closed(self):
        fixture = self.fixture()
        for bad in (
            "2026-08-31",
            "2026-08-31T07:00:01+00:00",
            "2026-08-31T15:00:00+07:00",
            True,
        ):
            with self.subTest(as_of=bad), self.assertRaises(ValueError):
                fixture.source.first_calendar_request(bad)

    def test_request_cannot_be_constructed_copied_or_mutated_into_authority(self):
        from ashare_pipeline.formal_range_source import FormalRangeRequestV1

        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        with self.assertRaises(ValueError):
            FormalRangeRequestV1(**request.to_dict())
        forged = object.__new__(FormalRangeRequestV1)
        for key, value in request.to_dict().items():
            object.__setattr__(forged, key, value)
        with self.assertRaises(FormalTerminalSourceError):
            fixture.source.fetch_verified(forged)
        with self.assertRaises(TypeError):
            copy.copy(request)
        object.__setattr__(request, "page_index", 2)
        with self.assertRaises(FormalTerminalSourceError):
            fixture.source.fetch_verified(request)

    def test_module_private_mint_cannot_authorize_arbitrary_bounds_or_boolean_page(self):
        import ashare_pipeline.formal_range_request as request_module

        fixture = self.fixture()
        config = fixture.binding.calendar_config
        genuine = fixture.source.first_calendar_request(FREEZE)
        wire = genuine.to_dict()
        wire.update(
            as_of_utc="9999-12-31T23:59:59+00:00",
            start_date="0001-01-01",
            end_date="9999-12-31",
            page_index=True,
        )
        mint = getattr(request_module, "_mint_range_request", None)
        if not callable(mint):
            return
        with self.assertRaises((ValueError, FormalTerminalSourceError)):
            forged = mint(
                wire,
                config.to_dict(),
                source_registry_hash=fixture.binding.source_registry_hash,
                root_guard=lambda: True,
            )
            fixture.registry.select_range(forged)

    def test_genuine_request_seal_rejects_every_out_of_contract_bound(self):
        fixture = self.fixture()
        mutations = (
            ("page_index", True),
            ("as_of_utc", "2026-09-01T07:00:00+00:00"),
            ("start_date", "0001-01-01"),
            ("end_date", "9999-12-31"),
        )
        for field, value in mutations:
            request = fixture.source.first_calendar_request(FREEZE)
            object.__setattr__(request, field, value)
            with self.subTest(field=field), self.assertRaises(FormalTerminalSourceError):
                fixture.source.fetch_verified(request)

    def test_select_range_accepts_only_matching_genuine_request(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        selected = fixture.registry.select_range(request)
        self.assertEqual(selected.entry_id, request.to_dict()["range_config_id"])
        self.assertEqual(selected.anchor_descriptor_id, request.to_dict()["anchor_descriptor_id"])
        with self.assertRaises(FormalTerminalSourceError):
            fixture.registry.select_range(object())

    def test_select_range_rejects_different_config_and_root_identity(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)

        def changed(documents):
            entry = next(item for item in documents["source"]["range_configs"]
                         if item["kind"] == "calendar_range" and item["exchange_scope"] == "SH")
            entry["endpoint_url"] = "https://www.cninfo.com.cn/fixture/other-range.json"

        other = self.fixture(mutate=changed)
        with self.assertRaises(FormalTerminalSourceError):
            other.registry.select_range(request)

    def test_select_range_rejects_changed_source_blob_even_when_entry_is_identical(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)

        def changed_unrelated_entry(documents):
            entry = next(item for item in documents["source"]["range_configs"]
                         if item["kind"] == "calendar_range" and item["exchange_scope"] == "SZ")
            entry["endpoint_url"] = "https://www.cninfo.com.cn/fixture/changed-sz.json"

        other = self.fixture(mutate=changed_unrelated_entry)
        self.assertEqual(
            other.binding.calendar_config.entry_id,
            fixture.binding.calendar_config.entry_id,
        )
        with self.assertRaises(FormalTerminalSourceError):
            other.registry.select_range(request)

    def test_identical_source_blob_can_be_reused_by_a_different_manifest_root(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)

        def changed_other_role(documents):
            documents["event"]["rules"]["event"]["evidence_kind"] = "fixture-event-v2"

        other = self.fixture(mutate=changed_other_role)
        self.assertNotEqual(
            other.binding.registry_manifest_hash, fixture.binding.registry_manifest_hash
        )
        self.assertEqual(other.registry.registry_hash, fixture.registry.registry_hash)
        selected = other.registry.select_range(request)
        self.assertEqual(selected.entry_id, fixture.binding.calendar_config.entry_id)

    def test_source_instance_rejects_other_manifest_root_even_for_shared_source_blob(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        fetch = fixture.source.fetch_verified(request)

        def changed_other_role(documents):
            documents["event"]["rules"]["event"]["evidence_kind"] = "fixture-event-v2"

        other = self.fixture(mutate=changed_other_role)
        self.assertEqual(other.registry.registry_hash, fixture.registry.registry_hash)
        other.reply(document_wire(request))
        with self.subTest(operation="fetch"), self.assertRaises(FormalTerminalSourceError):
            other.source.fetch_verified(request)
        self.assertEqual(other.transport.requests, [])
        with self.subTest(operation="replay"), self.assertRaises(FormalTerminalSourceError):
            other.source.parse_verified_snapshot(
                request, raw_bytes=fetch.raw_bytes, manifest=fetch.to_manifest()
            )

    def test_source_instance_rejects_other_complete_source_blob_with_same_selected_entry(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        fetch = fixture.source.fetch_verified(request)

        def changed_unrelated_entry(documents):
            entry = next(item for item in documents["source"]["range_configs"]
                         if item["kind"] == "calendar_range" and item["exchange_scope"] == "SZ")
            entry["endpoint_url"] = "https://www.cninfo.com.cn/fixture/changed-sz.json"

        other = self.fixture(mutate=changed_unrelated_entry)
        self.assertEqual(other.binding.calendar_config.entry_id,
                         fixture.binding.calendar_config.entry_id)
        other.reply(document_wire(request))
        with self.subTest(operation="fetch"), self.assertRaises(FormalTerminalSourceError):
            other.source.fetch_verified(request)
        self.assertEqual(other.transport.requests, [])
        with self.subTest(operation="replay"), self.assertRaises(FormalTerminalSourceError):
            other.source.parse_verified_snapshot(
                request, raw_bytes=fetch.raw_bytes, manifest=fetch.to_manifest()
            )

    def test_import_orders_have_no_registration_hook_or_partial_cycle(self):
        modules = (
            "ashare_pipeline.formal_sources",
            "ashare_pipeline.formal_range_request",
            "ashare_pipeline.formal_range_source",
            "ashare_pipeline.formal_range_contract",
            "ashare_pipeline.formal_context_schema",
            "ashare_pipeline.formal_registry_manifest",
        )
        for module in modules:
            code = textwrap.dedent(f"""
                import {module}
                import ashare_pipeline.formal_sources as sources
                import ashare_pipeline.formal_range_source as ranges
                assert not hasattr(sources, '_register_range_request')
                forged = object.__new__(ranges.FormalRangeRequestV1)
                try:
                    sources.SignedSourceRegistry.select_range(object(), forged)
                except Exception:
                    pass
                else:
                    raise AssertionError('forged request accepted')
            """)
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
            with self.subTest(first=module):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_source_initialization_uses_genuine_registry_and_binding_anchors(self):
        code = textwrap.dedent("""
            import ashare_pipeline.formal_sources as sources
            import ashare_pipeline.formal_range_contract as contract

            genuine_registry = sources.SignedSourceRegistry
            genuine_binding = contract.RangeBinding
            sources.SignedSourceRegistry = type('FakeRegistry', (), {})
            contract.RangeBinding = type('FakeBinding', (), {})
            genuine_registry.select_range = lambda self, request: 'forged-selection'
            genuine_binding.require_current = lambda self: None

            import ashare_pipeline.formal_range_source

            sources.SignedSourceRegistry = genuine_registry
            contract.RangeBinding = genuine_binding
            from tests.formal_range_fixtures import RangeSourceFixture
            fixture = RangeSourceFixture()
            try:
                request = fixture.source.first_calendar_request(
                    '2026-08-31T07:00:00+00:00')
                selected = fixture.registry.select_range(request)
                assert selected.entry_id == fixture.binding.calendar_config.entry_id
                try:
                    fixture.registry.select_range(object())
                except Exception:
                    pass
                else:
                    raise AssertionError('forged request accepted')
            finally:
                fixture.close()
        """)
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_transport_request_uses_only_new_placeholders_and_signed_bounds(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        fetch = fixture.source.fetch_verified(request)
        sent = fixture.transport.requests[0]
        self.assertEqual(
            sent.url,
            "https://www.cninfo.com.cn/fixture/range-calendar.json?end=2026-08-31&exchange=SH&page=1&start=2025-07-28",
        )
        self.assertEqual(sent.method, "GET")
        self.assertIsNone(sent.body)
        self.assertEqual(fetch.request_fingerprint, request.request_fingerprint)
        self.assertEqual(fetch.raw_bytes, fixture.transport.response.raw_bytes)

    def test_old_and_new_request_placeholders_cannot_cross(self):
        from ashare_pipeline.formal_range_contract import parse_range_entry

        with self.assertRaises(ValueError):
            parse_range_entry(range_entry(request_template={
                "query": {"date": "{period_or_date}"}, "headers": {}, "body": None
            }))

    def test_redirect_challenge_and_blocking_statuses_are_not_evidence(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        for status, url, headers, error in (
            (200, "https://evil.example.invalid/range.json", {}, FormalTerminalSourceError),
            (403, "https://www.cninfo.com.cn/fixture/range-calendar.json", {}, FormalSourceBlocked),
            (429, "https://www.cninfo.com.cn/fixture/range-calendar.json", {}, FormalSourceBlocked),
            (200, "https://www.cninfo.com.cn/fixture/range-calendar.json", {"x-page": "captcha"}, FormalSourceBlocked),
            (503, "https://www.cninfo.com.cn/fixture/range-calendar.json", {}, FormalRetryableSourceError),
        ):
            fixture.reply(document_wire(request), status_code=status, original_url=url, headers=headers)
            with self.subTest(status=status, url=url, headers=headers), self.assertRaises(error):
                fixture.source.fetch_verified(request)

    def test_fetch_and_snapshot_parse_bind_content_and_manifest(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        fetch = fixture.source.fetch_verified(request)
        parsed = fixture.source.parse_verified_snapshot(
            request, raw_bytes=fetch.raw_bytes, manifest=fetch.to_manifest()
        )
        self.assertEqual(parsed.to_dict(), document_wire(request))
        detached = parsed.to_dict()
        detached["rows"][0]["is_open"] = True
        self.assertFalse(parsed.to_dict()["rows"][0]["is_open"])
        bad = fetch.to_manifest()
        bad["content_sha256"] = "0" * 64
        with self.assertRaises(FormalTerminalSourceError):
            fixture.source.parse_verified_snapshot(request, raw_bytes=fetch.raw_bytes, manifest=bad)

    def test_parser_output_identity_page_and_counts_must_match(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        cases = (
            {"request_fingerprint": "0" * 64},
            {"source": "sse"},
            {"dataset": "other"},
            {"security_id": "SH600000"},
            {"exchange": "SZ"},
            {"start_date": "2025-07-29"},
            {"end_date": "2026-08-30"},
            {"parser_version": "other-v1"},
            {"page_index": 2},
            {"page_count": 2},
            {"record_count": 0},
            {"page_record_count": 0},
            {"pagination_evidence": "source_declared_numbered_pages_v1"},
        )
        for changes in cases:
            fixture.reply(document_wire(request, **changes))
            with self.subTest(changes=changes), self.assertRaises(FormalTerminalSourceError):
                fixture.source.fetch_verified(request)

    def test_empty_response_does_not_claim_complete_coverage(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request, record_count=0, page_record_count=0, rows=[]))
        with self.assertRaises(FormalTerminalSourceError):
            fixture.source.fetch_verified(request)

    def test_late_capture_and_late_publication_are_preserved_as_observations(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        late = "2026-09-01T01:00:00+00:00"
        wire = document_wire(
            request,
            published_at_utc=late,
            source_updated_at_utc=late,
            effective_at_utc=late,
            captured_at_utc=late,
        )
        wire["rows"][0].update(
            published_at_utc=late, effective_at_utc=late, captured_at_utc=late
        )
        fixture.reply(wire, captured_at_utc=late)
        fetch = fixture.source.fetch_verified(request)
        self.assertEqual(fetch.captured_at_utc, late)
        self.assertEqual(fetch.to_manifest()["published_at_utc"], late)
        self.assertEqual(
            fixture.source.parse_verified_snapshot(
                request, raw_bytes=fetch.raw_bytes, manifest=fetch.to_manifest()
            ).to_dict()["published_at_utc"],
            late,
        )

    def test_unproven_date_only_effective_time_stays_explicitly_unresolved(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        wire = document_wire(
            request,
            published_at_utc="2026-08-29T00:00:00+00:00",
            published_precision="date_only",
            effective_at_utc=None,
            effective_time_evidence_hash=None,
        )
        wire["rows"][0].update(
            published_at_utc="2026-08-29T00:00:00+00:00",
            published_precision="date_only",
            effective_at_utc=None,
            effective_time_evidence_hash=None,
        )
        fixture.reply(wire)
        fetch = fixture.source.fetch_verified(request)
        parsed = fixture.source.parse_verified_snapshot(
            request, raw_bytes=fetch.raw_bytes, manifest=fetch.to_manifest()
        )
        self.assertIsNone(parsed.to_dict()["effective_at_utc"])
        self.assertIsNone(parsed.to_dict()["rows"][0]["effective_at_utc"])

    def test_rows_require_visibility_fields_and_forbid_policy_conclusions(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        for mutation in ("missing_time", "effective_trade", "stale_days", "pool_veto"):
            wire = document_wire(request)
            if mutation == "missing_time":
                del wire["rows"][0]["published_at_utc"]
            else:
                wire["rows"][0][mutation] = False if mutation == "pool_veto" else 0
            fixture.reply(wire)
            with self.subTest(mutation=mutation), self.assertRaises(FormalTerminalSourceError):
                fixture.source.fetch_verified(request)

    def test_implementation_key_and_method_identities_are_sealed(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        key = next(iter(fixture.implementations))
        fixture.implementations[key] = (object(), object())
        with self.assertRaises(FormalTerminalSourceError):
            fixture.source.fetch_verified(request)

        second = self.fixture()
        request = second.source.first_calendar_request(FREEZE)
        second.reply(document_wire(request))
        second.normalizer.normalize = lambda wire, **kwargs: wire
        with self.assertRaises(FormalTerminalSourceError):
            second.source.fetch_verified(request)

        third = self.fixture()
        request = third.source.first_calendar_request(FREEZE)
        third.reply(document_wire(request))
        key = next(iter(third.implementations))
        third.implementations[key] = (third.parser, third.normalizer)
        with self.assertRaises(FormalTerminalSourceError):
            third.source.fetch_verified(request)

    def test_unregistered_or_self_reported_implementation_is_rejected(self):
        fixture = RangeSourceFixture.__new__(RangeSourceFixture)
        with self.assertRaises(ValueError):
            RangeSourceFixture(implementations={})

        class ClaimsVersions:
            parser_id = "fixture-range-parser"
            parser_version = "fixture-range-v1"
            mapping_version = "fixture-range-map-v1"
            normalizer_version = "fixture-range-normalizer-v1"
            request_version = "formal-range-request-v1"

            def parse(self, raw_bytes, **kwargs):
                return {}

            def normalize(self, wire, **kwargs):
                return wire

        with self.assertRaises(ValueError):
            RangeSourceFixture(implementations={"fixture-range-parser": ClaimsVersions()})

    def test_parser_cannot_mutate_config_or_request_during_execution(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        original_parse = fixture.parser.parse

        def mutating_parse(raw_bytes, *, request, config):
            config["mapping_version"] = "unsigned-map"
            return original_parse(raw_bytes, request=request, config=config)

        fixture.parser.parse = mutating_parse
        with self.assertRaises(FormalTerminalSourceError):
            fixture.source.fetch_verified(request)

    def test_instance_parse_shadow_cannot_bypass_registered_fetch_implementation(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        fixture.source._parse = lambda *args, **kwargs: None
        fetch = fixture.source.fetch_verified(request)
        self.assertEqual(fetch.request_fingerprint, request.request_fingerprint)
        self.assertEqual(len(fixture.parser.calls), 1)
        self.assertEqual(len(fixture.normalizer.calls), 1)

    def test_instance_parse_shadow_cannot_bypass_registered_replay_implementation(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        fetch = fixture.source.fetch_verified(request)
        fixture.parser.calls.clear()
        fixture.normalizer.calls.clear()
        fixture.source._parse = lambda *args, **kwargs: None
        parsed = fixture.source.parse_verified_snapshot(
            request, raw_bytes=fetch.raw_bytes, manifest=fetch.to_manifest()
        )
        self.assertEqual(parsed.to_dict(), document_wire(request))
        self.assertEqual(len(fixture.parser.calls), 1)
        self.assertEqual(len(fixture.normalizer.calls), 1)

    def test_range_fetch_cannot_be_externally_minted(self):
        import ashare_pipeline.formal_range_source as source_module
        from ashare_pipeline.formal_range_source import RangeFetch

        with self.assertRaises(ValueError):
            RangeFetch()
        self.assertFalse(callable(getattr(source_module, "_mint_fetch", None)))
        self.assertFalse(
            callable(getattr(source_module, "_mint_first_calendar_request", None))
        )

    def test_range_fetch_seal_distinguishes_boolean_from_every_integer_manifest_field(self):
        fixture = self.fixture()
        request = fixture.source.first_calendar_request(FREEZE)
        fixture.reply(document_wire(request))
        for field in ("record_count", "page_record_count", "page_count"):
            fetch = fixture.source.fetch_verified(request)
            object.__setattr__(fetch, field, True)
            with self.subTest(field=field), self.assertRaises(ValueError):
                fetch.to_manifest()


if __name__ == "__main__":
    unittest.main()
