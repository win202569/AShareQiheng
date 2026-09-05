import hashlib
import json
import unittest
from dataclasses import replace

import ashare_pipeline.formal_sources as formal_sources_module
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
    SourceAdapterConfig,
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


class LookupMutatingParser(FixtureParser):
    """Mutates a public registry config only after constructor parser lookup."""

    def __init__(self, document, registry):
        super().__init__(document)
        self.registry = registry
        self.parse_lookups = 0

    @property
    def parse(self):
        self.parse_lookups += 1
        if self.parse_lookups == 2:
            object.__setattr__(
                self.registry.configs[0],
                "endpoint_url",
                "https://evil.example.invalid/unsigned.json",
            )
        return self._parse

    def _parse(self, raw_bytes, *, request, config):
        self.calls.append((raw_bytes, request, config))
        return self.document


class ConfigMutatingParser(FixtureParser):
    def parse(self, raw_bytes, *, request, config):
        object.__setattr__(config, "mapping_version", "unsigned-map")
        return super().parse(raw_bytes, request=request, config=config)


class ResponseMutatingParser(FixtureParser):
    """Keeps the mutable transport object and rewrites it during parsing."""

    def __init__(self, document, mutable_response):
        super().__init__(document)
        self.mutable_response = mutable_response

    def parse(self, raw_bytes, *, request, config):
        object.__setattr__(self.mutable_response, "raw_bytes", b"rewritten-by-parser")
        object.__setattr__(
            self.mutable_response,
            "original_url",
            "https://www.cninfo.com.cn/fixture/rewritten.json",
        )
        object.__setattr__(
            self.mutable_response,
            "captured_at_utc",
            "2026-09-04T01:00:00+00:00",
        )
        object.__setattr__(self.mutable_response, "headers", {"x-rewritten": "true"})
        return super().parse(raw_bytes, request=request, config=config)


class FixtureResolver:
    def __init__(self, close="2026-08-21T15:00:00+08:00"):
        self.close = close
        self.calls = []

    def next_exchange_close(self, *, exchange, disclosure_date_cn, calendar_binding):
        self.calls.append((exchange, disclosure_date_cn, calendar_binding))
        return self.close


class BindingMutatingResolver(FixtureResolver):
    def next_exchange_close(self, *, exchange, disclosure_date_cn, calendar_binding):
        object.__setattr__(calendar_binding, "manifest_sha256", "0" * 64)
        return super().next_exchange_close(
            exchange=exchange,
            disclosure_date_cn=disclosure_date_cn,
            calendar_binding=calendar_binding,
        )


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
        self.assertIsNot(parsed, document)
        self.assertEqual(parsed.rows, document.rows)
        self.assertEqual(verification.status, "verified")

    def test_verified_document_rows_are_detached_and_recursively_immutable(self):
        parser_rows = (
            {
                "amount": 1,
                "details": {"history": ["CNY", {"currency": "CNY"}]},
            },
        )
        document = timestamp_document()
        object.__setattr__(document, "rows", parser_rows)
        adapter, _, _ = self.make_adapter([config()], document)

        _, verification, parsed = adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
            refresh_generation="generation",
            calendar_binding=None,
        )

        self.assertIsNot(parsed, document)
        self.assertEqual(parsed.rows[0].get("amount"), 1)
        self.assertEqual(parsed.rows[0]["details"]["history"][1]["currency"], "CNY")
        with self.assertRaises(TypeError):
            parsed.rows[0]["amount"] = 2
        with self.assertRaises(AttributeError):
            parsed.rows[0]["details"]["history"].append("USD")
        with self.assertRaises(TypeError):
            parsed.rows[0]["details"]["history"][1]["currency"] = "USD"
        parser_rows[0]["details"]["history"][1]["currency"] = "USD"
        self.assertEqual(parsed.rows[0]["details"]["history"][1]["currency"], "CNY")
        self.assertEqual(verification.status, "verified")

    def test_verified_document_copy_snapshots_metadata_before_row_callbacks(self):
        document = timestamp_document()

        class MetadataMutatingRow(dict):
            def items(self):
                object.__setattr__(document, "parser_id", "rewritten-parser")
                return super().items()

        object.__setattr__(document, "rows", (MetadataMutatingRow({"amount": 1}),))
        adapter, _, _ = self.make_adapter([config()], document)

        try:
            _, verification, parsed = adapter.fetch_verified(
                OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
                refresh_generation="generation",
                calendar_binding=None,
            )
        except FormalTerminalSourceError as error:
            self.fail(f"row callbacks must not rewrite verified document metadata: {error}")

        self.assertEqual(parsed.parser_id, "fixture-parser")
        self.assertEqual(parsed.rows[0]["amount"], 1)
        self.assertEqual(verification.status, "verified")

    def test_request_exchange_and_document_precision_require_exact_strings(self):
        class PretendString:
            def __init__(self, value):
                self.value = value

            def __hash__(self):
                return hash(self.value)

            def __eq__(self, other):
                return type(other) is str and other == self.value

            def __ne__(self, other):
                return not self.__eq__(other)

        with self.assertRaisesRegex(ValueError, "published_precision"):
            timestamp_document(published_precision=PretendString("timestamp"))

        document = timestamp_document(declared_security_id="SH600000")
        adapter, transport, _ = self.make_adapter([config()], document)
        with self.assertRaisesRegex(FormalTerminalSourceError, "request exchange"):
            adapter.fetch_verified(
                OfficialRequest(
                    "cninfo",
                    "annual_report",
                    "SH600000",
                    "2025-12-31",
                    PretendString("SH"),
                ),
                refresh_generation="generation",
                calendar_binding=None,
            )
        self.assertEqual(transport.requests, [])

    def test_immediate_source_config_enums_require_exact_strings(self):
        class PretendString:
            def __init__(self, value):
                self.value = value

            def __hash__(self):
                return hash(self.value)

            def __eq__(self, other):
                return type(other) is str and other == self.value

            def __ne__(self, other):
                return not self.__eq__(other)

        with self.assertRaisesRegex(ValueError, "context_kind"):
            CalendarSelector(PretendString("trading_calendar"), "disclosure", "SZ", "visible_at_freeze")
        with self.assertRaisesRegex(ValueError, "as_of_rule"):
            CalendarSelector("trading_calendar", "disclosure", "SZ", PretendString("visible_at_freeze"))
        direct_config = config(http_method=PretendString("GET"))
        direct_config["registry_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "http_method"):
            SourceAdapterConfig(**direct_config)

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

    def test_registry_provenance_blocks_forgery_and_config_mutation_before_network(self):
        for name in (
            "_REGISTRY_CONSTRUCTION_TOKEN",
            "_make_signed_source_registry_type",
            "_seal_formal_official_source_adapter_type",
        ):
            with self.subTest(module_capability=name):
                self.assertFalse(hasattr(formal_sources_module, name))
        document = timestamp_document()
        registry = SignedSourceRegistry.from_signed_bytes(
            registry_bytes([config()]), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        forged = object.__new__(SignedSourceRegistry)
        for field in ("canonical_json", "registry_hash", "signature", "key_id", "configs"):
            object.__setattr__(forged, field, getattr(registry, field))
        object.__setattr__(forged, "_require_verified", lambda: None)
        object.__setattr__(forged, "select", lambda _request: registry.configs[0])
        forged_transport = FakeTransport(response())
        forged_parser = FixtureParser(document)
        with self.assertRaisesRegex(ValueError, "verified"):
            FormalOfficialSourceAdapter(
                transport=forged_transport,
                registry=forged,
                policies={"cninfo": SourcePolicy.cninfo()},
                parsers={"fixture-parser": forged_parser},
                effective_time_resolver=FixtureResolver(),
                source_registry_hash=registry.registry_hash,
                registry_manifest_hash="f" * 64,
            )
        self.assertEqual(forged_transport.requests, [])
        self.assertEqual(forged_parser.calls, [])

        request = OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31")
        mutations = (
            ("endpoint_url", "https://www.cninfo.com.cn/fixture/mutated.json"),
            (
                "request_template",
                {"query": {"fixed": "yes"}, "headers": {"accept": "application/json"}, "body": None},
            ),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                signed = SignedSourceRegistry.from_signed_bytes(
                    registry_bytes([config()]),
                    "fixture-signature",
                    "fixture-key",
                    AcceptingVerifier(),
                )
                transport = FakeTransport(response())
                parser = FixtureParser(document)
                adapter = FormalOfficialSourceAdapter(
                    transport=transport,
                    registry=signed,
                    policies={"cninfo": SourcePolicy.cninfo()},
                    parsers={"fixture-parser": parser},
                    effective_time_resolver=FixtureResolver(),
                    source_registry_hash=signed.registry_hash,
                    registry_manifest_hash="f" * 64,
                )
                object.__setattr__(signed.configs[0], field, value)
                with self.assertRaisesRegex(FormalTerminalSourceError, "registry.*verified"):
                    adapter.fetch_verified(
                        request, refresh_generation="generation", calendar_binding=None
                    )
                self.assertEqual(transport.requests, [])
                self.assertEqual(parser.calls, [])

    def test_parser_lookup_cannot_redirect_the_operation_from_its_signed_endpoint(self):
        document = timestamp_document()
        registry = SignedSourceRegistry.from_signed_bytes(
            registry_bytes([config()]), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        transport = FakeTransport(response())
        parser = LookupMutatingParser(document, registry)
        adapter = FormalOfficialSourceAdapter(
            transport=transport,
            registry=registry,
            policies={"cninfo": SourcePolicy.cninfo()},
            parsers={"fixture-parser": parser},
            effective_time_resolver=FixtureResolver(),
            source_registry_hash=registry.registry_hash,
            registry_manifest_hash="f" * 64,
        )

        adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
            refresh_generation="generation",
            calendar_binding=None,
        )

        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(
            transport.requests[0].url,
            "https://www.cninfo.com.cn/fixture/annual.json?period=2025-12-31&symbol=BJ430001",
        )

    def test_parser_config_mutation_cannot_change_fetch_mapping_identity(self):
        document = timestamp_document()
        registry = SignedSourceRegistry.from_signed_bytes(
            registry_bytes([config()]), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        transport = FakeTransport(response())
        parser = ConfigMutatingParser(document)
        adapter = FormalOfficialSourceAdapter(
            transport=transport,
            registry=registry,
            policies={"cninfo": SourcePolicy.cninfo()},
            parsers={"fixture-parser": parser},
            effective_time_resolver=FixtureResolver(),
            source_registry_hash=registry.registry_hash,
            registry_manifest_hash="f" * 64,
        )

        fetch, _, _ = adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
            refresh_generation="generation",
            calendar_binding=None,
        )

        self.assertEqual(fetch.mapping_version, "fixture-map-v1")
        self.assertEqual(registry.configs[0].mapping_version, "fixture-map-v1")
        self.assertEqual(parser.calls[0][2].mapping_version, "unsigned-map")

    def test_parser_cannot_rewrite_captured_transport_response_evidence(self):
        original_raw = b"original-response-bytes"
        original_url = "https://www.cninfo.com.cn/fixture/original.json"
        original_capture = "2026-09-04T00:00:00+00:00"
        mutable_response = response(
            original_raw,
            url=original_url,
            captured_at_utc=original_capture,
        )
        document = timestamp_document()
        registry = SignedSourceRegistry.from_signed_bytes(
            registry_bytes([config()]), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        transport = FakeTransport(mutable_response)
        parser = ResponseMutatingParser(document, mutable_response)
        adapter = FormalOfficialSourceAdapter(
            transport=transport,
            registry=registry,
            policies={"cninfo": SourcePolicy.cninfo()},
            parsers={"fixture-parser": parser},
            effective_time_resolver=FixtureResolver(),
            source_registry_hash=registry.registry_hash,
            registry_manifest_hash="f" * 64,
        )

        fetch, verification, _ = adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
            refresh_generation="generation",
            calendar_binding=None,
        )

        self.assertEqual(parser.calls[0][0], original_raw)
        self.assertEqual(fetch.raw_bytes, original_raw)
        self.assertEqual(fetch.original_url, original_url)
        self.assertEqual(fetch.captured_at_utc, original_capture)
        self.assertEqual(verification.status, "verified")

    def test_parser_config_mutation_cannot_reject_or_rewrite_replay_identity(self):
        raw = b"replay-config-mutation"
        document = timestamp_document()
        registry = SignedSourceRegistry.from_signed_bytes(
            registry_bytes([config()]), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        transport = FakeTransport(response())
        parser = ConfigMutatingParser(document)
        adapter = FormalOfficialSourceAdapter(
            transport=transport,
            registry=registry,
            policies={"cninfo": SourcePolicy.cninfo()},
            parsers={"fixture-parser": parser},
            effective_time_resolver=FixtureResolver(),
            source_registry_hash=registry.registry_hash,
            registry_manifest_hash="f" * 64,
        )
        request = OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31")
        ref = OfficialSnapshotRef(
            snapshot_id="snapshot-config-mutation",
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
        self.assertIsNot(parsed, document)
        self.assertEqual(parsed.rows, document.rows)
        self.assertEqual(registry.configs[0].mapping_version, "fixture-map-v1")
        self.assertEqual(parser.calls[0][2].mapping_version, "unsigned-map")
        self.assertEqual(transport.requests, [])

    def test_adapter_anchor_mutation_rejects_fake_root_binding_before_transport(self):
        selector = {
            "context_kind": "trading_calendar",
            "scope_key": "disclosure",
            "exchange": "SZ",
            "as_of_rule": "visible_at_freeze",
        }
        document = timestamp_document(
            declared_security_id="SZ000001",
            published_at_utc="2026-08-20T00:00:00+00:00",
            published_precision="date_only",
        )
        date_config = config(calendar_selector=selector, exchange_scope="SZ")
        request = OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ")
        cases = (
            ("registry_manifest_hash", "0" * 64, binding(registry_manifest_hash="0" * 64)),
            ("freeze_at_utc", "2026-08-30T15:00:00+08:00", binding(freeze_at_utc="2026-08-30T15:00:00+08:00")),
            (
                "registry",
                SignedSourceRegistry.from_signed_bytes(
                    registry_bytes([date_config]),
                    "fixture-signature",
                    "fixture-key",
                    AcceptingVerifier(),
                ),
                binding(),
            ),
        )
        for field, value, forged_binding in cases:
            with self.subTest(field=field):
                adapter, transport, _ = self.make_adapter(
                    [date_config], document, resolver=FixtureResolver()
                )
                object.__setattr__(adapter, field, value)
                with self.assertRaisesRegex(FormalTerminalSourceError, "adapter.*verified"):
                    adapter.fetch_verified(
                        request,
                        refresh_generation="generation",
                        calendar_binding=forged_binding,
                    )
                self.assertEqual(transport.requests, [])

    def test_adapter_operation_record_cannot_be_reused_to_reanchor_a_date_only_fetch(self):
        selector = {
            "context_kind": "trading_calendar",
            "scope_key": "disclosure",
            "exchange": "SZ",
            "as_of_rule": "visible_at_freeze",
        }
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
        leaked_record = FormalOfficialSourceAdapter._trusted_operation_record(adapter)
        object.__setattr__(leaked_record, "registry_manifest_hash", "0" * 64)
        object.__setattr__(adapter, "registry_manifest_hash", "0" * 64)

        with self.assertRaisesRegex(FormalTerminalSourceError, "adapter.*verified"):
            adapter.fetch_verified(
                OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ"),
                refresh_generation="generation",
                calendar_binding=binding(registry_manifest_hash="0" * 64),
            )
        self.assertEqual(transport.requests, [])

    def test_directly_forged_adapter_cannot_operate(self):
        legitimate, _, _ = self.make_adapter([config()], timestamp_document())
        forged = object.__new__(FormalOfficialSourceAdapter)
        for field in (
            "registry",
            "_transport",
            "_effective_time_resolver",
            "_policies",
            "_parsers",
            "_policy_specs",
            "source_registry_hash",
            "registry_manifest_hash",
            "freeze_at_utc",
        ):
            object.__setattr__(forged, field, getattr(legitimate, field))
        object.__setattr__(forged, "_trusted_operation_record", lambda _adapter: None)

        with self.assertRaisesRegex(FormalTerminalSourceError, "adapter.*verified"):
            forged.fetch_verified(
                OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
                refresh_generation="generation",
                calendar_binding=None,
            )

    def test_adapter_rejects_mutated_public_policy_snapshot_before_transport(self):
        adapter, transport, _ = self.make_adapter([config()], timestamp_document())
        object.__setattr__(adapter._policy_specs["cninfo"], "allowed_hosts", frozenset({"evil.example.invalid"}))

        with self.assertRaisesRegex(FormalTerminalSourceError, "adapter.*verified"):
            adapter.fetch_verified(
                OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
                refresh_generation="generation",
                calendar_binding=None,
            )
        self.assertEqual(transport.requests, [])

    def test_resolver_receives_an_isolated_calendar_binding_copy(self):
        selector = {
            "context_kind": "trading_calendar",
            "scope_key": "disclosure",
            "exchange": "SZ",
            "as_of_rule": "visible_at_freeze",
        }
        document = timestamp_document(
            declared_security_id="SZ000001",
            published_at_utc="2026-08-20T00:00:00+00:00",
            published_precision="date_only",
        )
        signed_binding = binding()
        adapter, transport, _ = self.make_adapter(
            [config(calendar_selector=selector, exchange_scope="SZ")],
            document,
            resolver=BindingMutatingResolver(),
        )

        fetch, verification, _ = adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ"),
            refresh_generation="generation",
            calendar_binding=signed_binding,
        )

        self.assertEqual(fetch.effective_time_evidence_hash, "c" * 64)
        self.assertEqual(signed_binding.manifest_sha256, "c" * 64)
        self.assertEqual(verification.status, "verified")
        self.assertEqual(len(transport.requests), 1)

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

        self.assertIsNot(parsed, document)
        self.assertEqual(parsed.rows, document.rows)
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

        parsed = adapter.parse_verified_snapshot(ref, raw, calendar_binding=binding())
        self.assertIsNot(parsed, document)
        self.assertEqual(parsed.rows, document.rows)
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
