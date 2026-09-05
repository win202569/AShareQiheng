import hashlib
import json
import unittest
from dataclasses import replace

from ashare_pipeline.formal_evidence import (
    OfficialRequest,
    OfficialSnapshotRef,
    SourcePolicy,
    VerifiedCalendarBinding,
)
from ashare_pipeline.formal_sources import (
    CalendarSelector,
    FormalOfficialSourceAdapter,
    FormalRetryableSourceError,
    FormalSourceBlocked,
    FormalTerminalSourceError,
    ParsedOfficialDocument,
    SignedSourceRegistry,
    TransportResponse,
)


def canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


class AcceptingVerifier:
    def verify(self, payload, *, signature, key_id):
        return signature == "fixture-signature" and key_id == "fixture-key"


class RaisingVerifier:
    def verify(self, payload, *, signature, key_id):
        raise RuntimeError("unavailable verifier")


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


class FixtureParser:
    def __init__(self, document):
        self.document = document
        self.calls = []

    def parse(self, raw_bytes, *, request, config):
        self.calls.append((raw_bytes, request, config))
        return self.document


class FixtureResolver:
    def __init__(self, close="2026-08-21T15:00:00+08:00"):
        self.close = close
        self.calls = []

    def next_exchange_close(self, *, exchange, disclosure_date_cn, calendar_binding):
        self.calls.append((exchange, disclosure_date_cn, calendar_binding))
        return self.close


def registry_bytes(configs):
    return canonical_bytes(
        {
            "configs": configs,
            "registry_role": "source",
            "schema_version": "formal-source-registry-v1",
        }
    )


def config(**changes):
    value = {
        "source": "cninfo",
        "dataset": "annual_report",
        "endpoint_url": "https://www.cninfo.com.cn/fixture/annual.json",
        "http_method": "GET",
        "parser_id": "fixture-parser",
        "parser_version": "fixture-v1",
        "mapping_version": "fixture-map-v1",
        "request_template": {
            "query": {"period": "{period_or_date}", "symbol": "{security_id}"},
            "headers": {"accept": "application/json"},
            "body": None,
        },
        "timeout_seconds": 3.0,
        "retry_base_seconds": 1.0,
        "retry_max_attempts": 2,
        "challenge_cooldown_seconds": 15.0,
        "exchange_scope": None,
        "calendar_selector": None,
        "bootstrap_calendar": False,
    }
    value.update(changes)
    return value


def binding(**changes):
    value = {
        "snapshot_id": "calendar-snapshot",
        "manifest_sha256": "c" * 64,
        "exchange": "SZ",
        "freeze_at_utc": "2026-08-31T15:00:00+08:00",
        "registry_manifest_hash": "f" * 64,
        "selector_hash": CalendarSelector(
            "trading_calendar", "disclosure", "SZ", "visible_at_freeze"
        ).selector_hash,
        "prerequisite_task_id": "12345678-1234-4234-8234-1234567890ab",
    }
    value.update(changes)
    return VerifiedCalendarBinding(**value)


def timestamp_document(**changes):
    value = {
        "parser_id": "fixture-parser",
        "parser_version": "fixture-v1",
        "declared_security_id": "BJ430001",
        "declared_period": "2025-12-31",
        "published_at_utc": "2026-03-20T08:00:00+00:00",
        "published_precision": "timestamp",
        "source_updated_at_utc": "2026-03-20T08:30:00+00:00",
        "rows": ({"amount": 1},),
        "accounting_basis": "PRC_GAAP",
    }
    value.update(changes)
    return ParsedOfficialDocument(**value)


def response(raw=b'{"fixture":true}', status=200, url="https://www.cninfo.com.cn/fixture/annual.json", **changes):
    value = {
        "status_code": status,
        "original_url": url,
        "headers": {"content-type": "application/json"},
        "raw_bytes": raw,
        "captured_at_utc": "2026-09-04T00:00:00+00:00",
    }
    value.update(changes)
    return TransportResponse(**value)


class FormalSourceTests(unittest.TestCase):
    def make_adapter(self, configs, document, *, transport=None, resolver=None):
        registry = SignedSourceRegistry.from_signed_bytes(
            registry_bytes(configs), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        transport = transport or FakeTransport(response())
        parser = FixtureParser(document)
        adapter = FormalOfficialSourceAdapter(
            transport=transport,
            registry=registry,
            policies={"cninfo": SourcePolicy.cninfo()},
            parsers={"fixture-parser": parser},
            effective_time_resolver=resolver or FixtureResolver(),
            source_registry_hash=registry.registry_hash,
            registry_manifest_hash="f" * 64,
        )
        return adapter, transport, parser

    def test_timestamp_fetch_preserves_raw_bytes_signed_identity_and_generation(self):
        raw = b"\x00fixture\xff"
        document = timestamp_document()
        adapter, transport, parser = self.make_adapter(
            [config()], document, transport=FakeTransport(response(raw))
        )

        fetch, verification, parsed = adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
            refresh_generation="fixture-generation",
            calendar_binding=None,
        )

        self.assertEqual(fetch.raw_bytes, raw)
        self.assertEqual(fetch.parser_id, "fixture-parser")
        self.assertEqual(fetch.parser_version, "fixture-v1")
        self.assertEqual(fetch.mapping_version, "fixture-map-v1")
        self.assertEqual(fetch.refresh_generation, "fixture-generation")
        self.assertEqual(fetch.original_url, "https://www.cninfo.com.cn/fixture/annual.json")
        self.assertEqual(transport.requests[0].url, "https://www.cninfo.com.cn/fixture/annual.json?period=2025-12-31&symbol=BJ430001")
        self.assertEqual(parser.calls[0][0], raw)
        self.assertIs(parsed, document)
        self.assertEqual(verification.status, "verified")

    def test_registry_verification_and_preflight_errors_never_call_transport(self):
        bytes_ = registry_bytes([config()])
        with self.assertRaisesRegex(ValueError, "registry signature"):
            SignedSourceRegistry.from_signed_bytes(
                bytes_, "wrong", "fixture-key", AcceptingVerifier()
            )
        with self.assertRaisesRegex(ValueError, "signature"):
            SignedSourceRegistry.from_signed_bytes(
                bytes_, "fixture-signature", "fixture-key", RaisingVerifier()
            )
        with self.assertRaisesRegex(ValueError, "canonical"):
            SignedSourceRegistry.from_signed_bytes(
                json.dumps(json.loads(bytes_), indent=2).encode(),
                "fixture-signature",
                "fixture-key",
                AcceptingVerifier(),
            )
        duplicate = bytes_.replace(b'"configs":', b'"configs":[],"configs":', 1)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            SignedSourceRegistry.from_signed_bytes(
                duplicate, "fixture-signature", "fixture-key", AcceptingVerifier()
            )

        registry = SignedSourceRegistry.from_signed_bytes(
            bytes_, "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        transport = FakeTransport(response())
        with self.assertRaisesRegex(ValueError, "parser is not registered"):
            FormalOfficialSourceAdapter(
                transport=transport,
                registry=registry,
                policies={"cninfo": SourcePolicy.cninfo()},
                parsers={},
                effective_time_resolver=FixtureResolver(),
                source_registry_hash=registry.registry_hash,
                registry_manifest_hash="f" * 64,
            )
        self.assertEqual(transport.requests, [])

    def test_signed_registry_cannot_be_constructed_without_its_signature_loader(self):
        with self.assertRaisesRegex(ValueError, "from_signed_bytes"):
            SignedSourceRegistry(b"{}", "0" * 64, "signature", "fixture-key", ())

    def test_adapter_requires_the_loaded_root_source_registry_hash(self):
        registry = SignedSourceRegistry.from_signed_bytes(
            registry_bytes([config()]), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        with self.assertRaisesRegex(ValueError, "source_registry_hash"):
            FormalOfficialSourceAdapter(
                transport=FakeTransport(response()),
                registry=registry,
                policies={"cninfo": SourcePolicy.cninfo()},
                parsers={"fixture-parser": FixtureParser(timestamp_document())},
                effective_time_resolver=FixtureResolver(),
                source_registry_hash="0" * 64,
                registry_manifest_hash="f" * 64,
            )

    def test_unknown_or_ambiguous_config_and_timestamp_binding_fail_before_transport(self):
        document = timestamp_document()
        adapter, transport, _ = self.make_adapter([config()], document)
        with self.assertRaises(FormalTerminalSourceError):
            adapter.fetch_verified(
                OfficialRequest("cninfo", "unknown_dataset", "BJ430001", "2025-12-31"),
                refresh_generation="generation",
                calendar_binding=None,
            )
        with self.assertRaises(FormalTerminalSourceError):
            adapter.fetch_verified(
                OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
                refresh_generation="generation",
                calendar_binding=binding(),
            )
        self.assertEqual(transport.requests, [])

        scoped = config(exchange_scope="BJ")
        ambiguous, ambiguous_transport, _ = self.make_adapter([config(), scoped], document)
        with self.assertRaises(FormalTerminalSourceError):
            ambiguous.fetch_verified(
                OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31", "BJ"),
                refresh_generation="generation",
                calendar_binding=None,
            )
        self.assertEqual(ambiguous_transport.requests, [])

    def test_invalid_signed_endpoint_template_and_rate_values_are_rejected_at_registry_load(self):
        invalids = (
            config(endpoint_url="http://www.cninfo.com.cn/plain"),
            config(request_template={"query": {"q": "{unknown}"}, "headers": {}, "body": None}),
            config(request_template={"query": {}, "headers": {}, "body": {"x": 1}}),
            config(timeout_seconds=0),
            config(retry_base_seconds=float("inf")),
            config(retry_max_attempts=False),
            config(challenge_cooldown_seconds=-1),
            config(parser_version=" not-trimmed "),
        )
        for invalid in invalids:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    SignedSourceRegistry.from_signed_bytes(
                        registry_bytes([invalid]),
                        "fixture-signature",
                        "fixture-key",
                        AcceptingVerifier(),
                    )
        registry = SignedSourceRegistry.from_signed_bytes(
            registry_bytes([config(endpoint_url="https://evil.example.invalid/fixture")]),
            "fixture-signature",
            "fixture-key",
            AcceptingVerifier(),
        )
        transport = FakeTransport(response())
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            FormalOfficialSourceAdapter(
                transport=transport,
                registry=registry,
                policies={"cninfo": SourcePolicy.cninfo()},
                parsers={"fixture-parser": FixtureParser(timestamp_document())},
                effective_time_resolver=FixtureResolver(),
                source_registry_hash=registry.registry_hash,
                registry_manifest_hash="f" * 64,
            )
        self.assertEqual(transport.requests, [])

    def test_signed_templates_reject_dynamic_keys_controls_and_unbound_calendar_configs(self):
        invalids = (
            config(
                request_template={"query": {"{security_id}": "value"}, "headers": {}, "body": None}
            ),
            config(
                request_template={"query": {}, "headers": {"x-{security_id}": "value"}, "body": None}
            ),
            config(
                request_template={"query": {"q": "raw&injected=true"}, "headers": {}, "body": None}
            ),
            config(
                request_template={"query": {"q": "raw\r\nvalue"}, "headers": {}, "body": None}
            ),
            config(
                request_template={"query": {}, "headers": {"x-safe": "raw\x7fvalue"}, "body": None}
            ),
            config(
                dataset="trading_calendar",
                request_template={"query": {}, "headers": {}, "body": None},
            ),
        )
        for invalid in invalids:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    SignedSourceRegistry.from_signed_bytes(
                        registry_bytes([invalid]),
                        "fixture-signature",
                        "fixture-key",
                        AcceptingVerifier(),
                    )

    def test_url_controls_are_rejected_before_parser_or_snapshot_verification(self):
        invalid_endpoint = config(
            endpoint_url="https://www.cninfo.com.cn/fixture/annual\r\nredirect"
        )
        transport = FakeTransport(response())
        with self.assertRaises(ValueError):
            SignedSourceRegistry.from_signed_bytes(
                registry_bytes([invalid_endpoint]),
                "fixture-signature",
                "fixture-key",
                AcceptingVerifier(),
            )
        self.assertEqual(transport.requests, [])

        raw = b"snapshot-raw"
        document = timestamp_document()
        adapter, response_transport, parser = self.make_adapter(
            [config()], document,
            transport=FakeTransport(
                response(raw, url="https://www.cninfo.com.cn/fixture/annual\r\nredirect")
            ),
        )
        request = OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31")
        with self.assertRaises(FormalTerminalSourceError):
            adapter.fetch_verified(
                request, refresh_generation="generation", calendar_binding=None
            )
        self.assertEqual(len(response_transport.requests), 1)
        self.assertEqual(parser.calls, [])

        replay_adapter, replay_transport, replay_parser = self.make_adapter([config()], document)
        ref = OfficialSnapshotRef(
            snapshot_id="snapshot",
            source=request.source,
            dataset=request.dataset,
            request_fingerprint=request.request_fingerprint,
            security_id=request.security_id,
            period_or_date=request.period_or_date,
            exchange=request.exchange,
            content_sha256=hashlib.sha256(raw).hexdigest(),
            manifest_sha256="a" * 64,
            content_path="unused.bin",
            manifest_path="unused.manifest.json",
            original_url="https://www.cninfo.com.cn/fixture/annual\x7fredirect",
            published_at_utc=document.published_at_utc,
            published_precision="timestamp",
            source_updated_at_utc=document.source_updated_at_utc,
            captured_at_utc="2026-09-04T00:00:00+00:00",
            effective_at_utc=document.published_at_utc,
            effective_time_evidence_hash=None,
            refresh_generation="generation",
            producing_task_id=None,
            parser_id="fixture-parser",
            parser_version="fixture-v1",
            mapping_version="fixture-map-v1",
            verification_status="verified",
        )
        with self.assertRaises(FormalTerminalSourceError):
            replay_adapter.parse_verified_snapshot(ref, raw, calendar_binding=None)
        self.assertEqual(replay_transport.requests, [])
        self.assertEqual(replay_parser.calls, [])

    def test_status_challenge_and_timeout_are_classified_without_parsing(self):
        document = timestamp_document()
        cases = (
            (response(status=403), FormalSourceBlocked),
            (response(status=429), FormalSourceBlocked),
            (response(raw=b"CAPTCHA challenge", status=200), FormalSourceBlocked),
            (response(status=408), FormalRetryableSourceError),
            (response(status=503), FormalRetryableSourceError),
            (response(status=404), FormalTerminalSourceError),
        )
        request = OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31")
        for item, error_type in cases:
            with self.subTest(status=item.status_code, error=error_type.__name__):
                adapter, transport, parser = self.make_adapter(
                    [config()], document, transport=FakeTransport(item)
                )
                with self.assertRaises(error_type):
                    adapter.fetch_verified(
                        request, refresh_generation="generation", calendar_binding=None
                    )
                self.assertEqual(len(transport.requests), 1)
                self.assertEqual(parser.calls, [])
        adapter, transport, parser = self.make_adapter(
            [config()], document, transport=FakeTransport(error=TimeoutError())
        )
        with self.assertRaises(FormalRetryableSourceError):
            adapter.fetch_verified(request, refresh_generation="generation", calendar_binding=None)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(parser.calls, [])

    def test_date_only_requires_a_canonical_signed_binding_before_transport(self):
        selector = {
            "context_kind": "trading_calendar",
            "scope_key": "disclosure",
            "exchange": "SZ",
            "as_of_rule": "visible_at_freeze",
        }
        date_config = config(calendar_selector=selector, exchange_scope="SZ")
        document = timestamp_document(
            declared_security_id="SZ000001",
            published_at_utc="2026-08-20T00:00:00+00:00",
            published_precision="date_only",
        )
        resolver = FixtureResolver()
        request = OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ")
        adapter, transport, _ = self.make_adapter(
            [date_config], document, resolver=resolver
        )

        fetch, verification, _ = adapter.fetch_verified(
            request, refresh_generation="generation", calendar_binding=binding()
        )

        self.assertEqual(fetch.effective_at_utc, "2026-08-21T15:00:00+08:00")
        self.assertEqual(fetch.effective_time_evidence_hash, "c" * 64)
        self.assertEqual(resolver.calls[0][0:2], ("SZ", "2026-08-20"))
        self.assertEqual(verification.status, "verified")
        self.assertEqual(len(transport.requests), 1)

        for invalid in (
            None,
            binding(manifest_sha256="D" * 64),
            binding(registry_manifest_hash="0" * 64),
            binding(freeze_at_utc="2026-08-31T07:00:00+00:00"),
            binding(exchange="SH"),
            binding(selector_hash="e" * 64),
            binding(prerequisite_task_id="not-a-uuid"),
        ):
            with self.subTest(binding=invalid):
                fresh, blocked_transport, _ = self.make_adapter(
                    [date_config], document, resolver=resolver
                )
                with self.assertRaises(FormalTerminalSourceError):
                    fresh.fetch_verified(
                        request, refresh_generation="generation", calendar_binding=invalid
                    )
                self.assertEqual(blocked_transport.requests, [])

    def test_date_only_anchor_and_resolver_close_must_be_real_calendar_evidence(self):
        selector = {
            "context_kind": "trading_calendar",
            "scope_key": "disclosure",
            "exchange": "SZ",
            "as_of_rule": "visible_at_freeze",
        }
        date_config = config(calendar_selector=selector, exchange_scope="SZ")
        with self.assertRaisesRegex(ValueError, "day anchor"):
            timestamp_document(
                declared_security_id="SZ000001",
                published_precision="date_only",
                published_at_utc="2026-08-20T08:00:00+00:00",
            )
        document = timestamp_document(
            declared_security_id="SZ000001",
            published_precision="date_only",
            published_at_utc="2026-08-20T00:00:00+00:00",
        )
        adapter, transport, _ = self.make_adapter(
            [date_config], document, resolver=FixtureResolver("2026-08-20T15:00:00+08:00")
        )
        with self.assertRaises(FormalTerminalSourceError):
            adapter.fetch_verified(
                OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ"),
                refresh_generation="generation",
                calendar_binding=binding(),
            )
        self.assertEqual(len(transport.requests), 1)

    def test_bootstrap_calendar_is_timestamp_only_and_surfaces_the_signed_fact(self):
        bootstrap = config(
            dataset="trading_calendar",
            bootstrap_calendar=True,
            request_template={"query": {}, "headers": {}, "body": None},
        )
        document = timestamp_document(
            declared_security_id=None,
            declared_period=None,
            bootstrap_calendar=True,
        )
        adapter, _, _ = self.make_adapter([bootstrap], document)
        fetch, verification, parsed = adapter.fetch_verified(
            OfficialRequest("cninfo", "trading_calendar", None, None),
            refresh_generation="calendar-bootstrap",
            calendar_binding=None,
        )
        self.assertEqual(fetch.effective_at_utc, document.published_at_utc)
        self.assertIsNone(fetch.effective_time_evidence_hash)
        self.assertTrue(parsed.bootstrap_calendar)
        self.assertEqual(verification.status, "verified")

        invalid_document = replace(document, published_precision="date_only", published_at_utc="2026-08-20T00:00:00+00:00")
        invalid, transport, _ = self.make_adapter([bootstrap], invalid_document)
        with self.assertRaises(FormalTerminalSourceError):
            invalid.fetch_verified(
                OfficialRequest("cninfo", "trading_calendar", None, None),
                refresh_generation="calendar-bootstrap",
                calendar_binding=None,
            )
        self.assertEqual(len(transport.requests), 1)

    def test_bootstrap_calendar_config_and_request_cannot_carry_an_exchange_scope(self):
        invalid = config(
            dataset="trading_calendar",
            bootstrap_calendar=True,
            exchange_scope="SZ",
            request_template={"query": {}, "headers": {}, "body": None},
        )
        with self.assertRaisesRegex(ValueError, "bootstrap"):
            SignedSourceRegistry.from_signed_bytes(
                registry_bytes([invalid]), "fixture-signature", "fixture-key", AcceptingVerifier()
            )

        bootstrap = config(
            dataset="trading_calendar",
            bootstrap_calendar=True,
            request_template={"query": {}, "headers": {}, "body": None},
        )
        document = timestamp_document(
            declared_security_id=None,
            declared_period=None,
            bootstrap_calendar=True,
        )
        adapter, transport, _ = self.make_adapter([bootstrap], document)
        with self.assertRaises(FormalTerminalSourceError):
            adapter.fetch_verified(
                OfficialRequest("cninfo", "trading_calendar", None, None, "SZ"),
                refresh_generation="calendar-bootstrap",
                calendar_binding=None,
            )
        self.assertEqual(transport.requests, [])

    def test_universe_listing_requires_global_explicit_typed_status_rows(self):
        listing = config(
            dataset="universe_listing",
            exchange_scope="BJ",
            request_template={"query": {}, "headers": {}, "body": None},
        )
        bad_document = timestamp_document(
            declared_security_id=None,
            declared_period=None,
            rows=({"security_id": "BJ430001"},),
        )
        adapter, _, _ = self.make_adapter([listing], bad_document)
        with self.assertRaises(FormalTerminalSourceError):
            adapter.fetch_verified(
                OfficialRequest("cninfo", "universe_listing", None, None, "BJ"),
                refresh_generation="generation",
                calendar_binding=None,
            )

    def test_universe_listing_rejects_non_global_identity_before_transport_or_parser(self):
        listing = config(
            dataset="universe_listing",
            exchange_scope="BJ",
            request_template={"query": {}, "headers": {}, "body": None},
        )
        document = timestamp_document(declared_security_id=None, declared_period=None)
        adapter, transport, parser = self.make_adapter([listing], document)
        with self.assertRaises(FormalTerminalSourceError):
            adapter.fetch_verified(
                OfficialRequest("cninfo", "universe_listing", "BJ430001", None, "BJ"),
                refresh_generation="generation",
                calendar_binding=None,
            )
        self.assertEqual(transport.requests, [])
        self.assertEqual(parser.calls, [])

    def test_parser_identity_and_declared_publication_mismatches_fail_closed(self):
        request = OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31")
        cases = (
            replace(timestamp_document(), parser_version="other-v1"),
            replace(timestamp_document(), declared_security_id="BJ430002"),
            replace(timestamp_document(), declared_period="2024-12-31"),
        )
        for document in cases:
            with self.subTest(document=document):
                adapter, transport, _ = self.make_adapter([config()], document)
                with self.assertRaises(FormalTerminalSourceError):
                    adapter.fetch_verified(
                        request, refresh_generation="generation", calendar_binding=None
                    )
                self.assertEqual(len(transport.requests), 1)

    def test_replay_never_transports_and_rejects_lineage_tampering(self):
        raw = b"raw"
        document = timestamp_document()
        adapter, transport, _ = self.make_adapter([config()], document)
        request = OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31")
        ref = OfficialSnapshotRef(
            snapshot_id="snapshot",
            source=request.source,
            dataset=request.dataset,
            request_fingerprint=request.request_fingerprint,
            security_id=request.security_id,
            period_or_date=request.period_or_date,
            exchange=request.exchange,
            content_sha256=hashlib.sha256(raw).hexdigest(),
            manifest_sha256="a" * 64,
            content_path="unused.bin",
            manifest_path="unused.manifest.json",
            original_url="https://www.cninfo.com.cn/fixture/annual.json",
            published_at_utc=document.published_at_utc,
            published_precision="timestamp",
            source_updated_at_utc=document.source_updated_at_utc,
            captured_at_utc="2026-09-04T00:00:00+00:00",
            effective_at_utc=document.published_at_utc,
            effective_time_evidence_hash=None,
            refresh_generation="generation",
            producing_task_id=None,
            parser_id="fixture-parser",
            parser_version="fixture-v1",
            mapping_version="fixture-map-v1",
            verification_status="verified",
        )

        parsed = adapter.parse_verified_snapshot(ref, raw, calendar_binding=None)

        self.assertIs(parsed, document)
        self.assertEqual(transport.requests, [])

    def test_date_only_replay_rechecks_binding_effective_time_and_all_signed_lineage(self):
        selector = {
            "context_kind": "trading_calendar",
            "scope_key": "disclosure",
            "exchange": "SZ",
            "as_of_rule": "visible_at_freeze",
        }
        raw = b"date-only-raw"
        document = timestamp_document(
            declared_security_id="SZ000001",
            published_at_utc="2026-08-20T00:00:00+00:00",
            published_precision="date_only",
        )
        adapter, transport, _ = self.make_adapter(
            [config(calendar_selector=selector, exchange_scope="SZ")],
            document,
            resolver=FixtureResolver(),
        )
        request = OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ")
        ref = OfficialSnapshotRef(
            snapshot_id="date-snapshot",
            source=request.source,
            dataset=request.dataset,
            request_fingerprint=request.request_fingerprint,
            security_id=request.security_id,
            period_or_date=request.period_or_date,
            exchange=request.exchange,
            content_sha256=hashlib.sha256(raw).hexdigest(),
            manifest_sha256="b" * 64,
            content_path="unused.bin",
            manifest_path="unused.manifest.json",
            original_url="https://www.cninfo.com.cn/fixture/annual.json",
            published_at_utc=document.published_at_utc,
            published_precision="date_only",
            source_updated_at_utc=document.source_updated_at_utc,
            captured_at_utc="2026-09-04T00:00:00+00:00",
            effective_at_utc="2026-08-21T15:00:00+08:00",
            effective_time_evidence_hash="c" * 64,
            refresh_generation="generation",
            producing_task_id=None,
            parser_id="fixture-parser",
            parser_version="fixture-v1",
            mapping_version="fixture-map-v1",
            verification_status="verified",
        )

        self.assertIs(adapter.parse_verified_snapshot(ref, raw, calendar_binding=binding()), document)
        self.assertEqual(transport.requests, [])
        tampered = (
            (replace(ref, source="sse"), binding()),
            (replace(ref, dataset="other_dataset"), binding()),
            (replace(ref, request_fingerprint="0" * 64), binding()),
            (replace(ref, parser_id="other-parser"), binding()),
            (replace(ref, parser_version="other-v1"), binding()),
            (replace(ref, mapping_version="other-map"), binding()),
            (replace(ref, effective_at_utc="2026-08-22T15:00:00+08:00"), binding()),
            (ref, binding(manifest_sha256="d" * 64)),
        )
        for forged_ref, forged_binding in tampered:
            with self.subTest(ref=forged_ref, binding=forged_binding):
                with self.assertRaises(FormalTerminalSourceError):
                    adapter.parse_verified_snapshot(
                        forged_ref, raw, calendar_binding=forged_binding
                    )
        self.assertEqual(transport.requests, [])
        with self.assertRaises(FormalTerminalSourceError):
            adapter.parse_verified_snapshot(replace(ref, mapping_version="other"), raw, calendar_binding=None)
        with self.assertRaises(FormalTerminalSourceError):
            adapter.parse_verified_snapshot(ref, b"other", calendar_binding=None)
        self.assertEqual(transport.requests, [])

    def test_template_substitution_is_canonical_and_rejects_header_or_body_injection(self):
        post = config(
            http_method="POST",
            request_template={
                "query": {"q": "prefix-{security_id}"},
                "headers": {"x-period": "{period_or_date}"},
                "body": {"security": "{security_id}", "period": "{period_or_date}"},
            },
        )
        document = timestamp_document()
        adapter, transport, _ = self.make_adapter([post], document)
        adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
            refresh_generation="generation",
            calendar_binding=None,
        )
        sent = transport.requests[0]
        self.assertEqual(sent.method, "POST")
        self.assertEqual(sent.url, "https://www.cninfo.com.cn/fixture/annual.json?q=prefix-BJ430001")
        self.assertEqual(sent.body, b'{"period":"2025-12-31","security":"BJ430001"}')

        bad = config(
            request_template={"query": {}, "headers": {"x": "bad\nvalue"}, "body": None}
        )
        with self.assertRaisesRegex(ValueError, "header"):
            SignedSourceRegistry.from_signed_bytes(
                registry_bytes([bad]), "fixture-signature", "fixture-key", AcceptingVerifier()
            )

    def test_signed_endpoint_query_and_templated_query_are_joined_without_rewriting_the_endpoint(self):
        signed = config(endpoint_url="https://www.cninfo.com.cn/fixture/annual.json?fixed=yes")
        adapter, transport, _ = self.make_adapter([signed], timestamp_document())

        adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
            refresh_generation="generation",
            calendar_binding=None,
        )

        self.assertEqual(
            transport.requests[0].url,
            "https://www.cninfo.com.cn/fixture/annual.json?fixed=yes&period=2025-12-31&symbol=BJ430001",
        )


if __name__ == "__main__":
    unittest.main()
