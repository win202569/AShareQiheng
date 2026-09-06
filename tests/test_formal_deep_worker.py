"""Contract tests for the Task 6 formal collection worker boundary."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ashare_pipeline.formal_deep_worker import (
    CalendarBindingPending,
    FormalContextTaskPayload,
    FormalFeatureBuildTaskPayload,
    FormalRegistryRuntime,
    FormalRegistryRuntimeLoader,
    FormalStatementTaskPayload,
    FormalTaskSpec,
    FormalUniverseFinalizeTaskPayload,
    FormalUniverseSourceTaskPayload,
    derive_collection_refresh_generation,
    formal_context_task_specs,
    formal_statement_task_specs,
)
from ashare_pipeline.formal_evidence import OfficialRequest, VerifiedCalendarBinding
from ashare_pipeline.formal_registry_manifest import (
    FormalRegistryBundleLoader,
    FormalRegistryManifest,
    VerifiedRegistryBlob,
)
from ashare_pipeline.formal_context_schema import FormalContextRequest, SignedContextRequestResolver
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore
from ashare_pipeline.state_store import StateStore
import tests.test_formal_sources as _formal_source_tests


AS_OF = "2026-08-31T07:00:00+00:00"
ROOT_A = "a" * 64
ROOT_B = "b" * 64
SOURCE_A = "c" * 64
MAPPING_A = "d" * 64
FEATURE_A = "e" * 64


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


class AcceptingVerifier:
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool:
        return signature == hashlib.sha256(payload).hexdigest() and key_id == "fixture-key"


class InMemoryRegistryRepository:
    def __init__(self, manifest: FormalRegistryManifest, blobs: dict[str, VerifiedRegistryBlob]):
        self.manifest = manifest
        self.blobs = blobs

    def get_formal_registry_manifest(self, manifest_hash: str) -> FormalRegistryManifest | None:
        return self.manifest if manifest_hash == self.manifest.manifest_hash else None

    def get_formal_registry_blob(self, registry_hash: str) -> VerifiedRegistryBlob | None:
        return self.blobs.get(registry_hash)


class NoTransport:
    def send(self, _request: object) -> object:
        raise AssertionError("runtime construction must not use transport")


class EffectiveTimeResolver:
    def next_exchange_close(self, *_args: object, **_kwargs: object) -> str:
        return AS_OF


def fixture_bundle_loader(*, scoring_schema: str = "fixture-v1") -> FormalRegistryBundleLoader:
    """Make a real, test-purpose verified root from signed child bytes."""
    roles = ("source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event")
    raw = {
        role: canonical_bytes({"registry_role": role, "schema_version": "fixture-v1"})
        for role in roles
    }
    raw["scoring"] = canonical_bytes({"registry_role": "scoring", "schema_version": scoring_schema})
    raw["source"] = canonical_bytes(
        {"configs": [], "registry_role": "source", "schema_version": "formal-source-registry-v1"}
    )
    raw["mapping"] = canonical_bytes(
        {
            "bindings": [
                {
                    "dataset": "annual_report",
                    "exchange_scope": "BJ",
                    "mapping_ids": ["operating_profit"],
                    "mapping_version": "fixture-map-v1",
                    "parser_id": "fixture-parser",
                    "parser_version": "fixture-v1",
                    "source": "cninfo",
                }
            ],
            "mappings": [
                {
                    "accounting_basis": "consolidated",
                    "mapping_id": "operating_profit",
                    "metric_key": "operating_profit",
                    "nature": "duration",
                    "period_kind": "FY",
                    "source_field": "OPERATING_PROFIT",
                    "statement": "income",
                    "unit": "CNY",
                }
            ],
            "registry_role": "mapping",
            "row_format": "item_value_v1",
            "schema_version": "formal-financial-mapping-registry-v1",
        }
    )
    raw["feature"] = canonical_bytes(
        {
            "contract_version": "formal-features-v1",
            "mapping_registry_hash": hashlib.sha256(raw["mapping"]).hexdigest(),
            "registry_role": "feature",
            "schema_version": "formal-feature-registry-v1",
            "slots": [
                {
                    "dimension": "G",
                    "formula": {"fact_key": "income.revenue", "op": "fact", "period_key": "FY0"},
                    "formula_version": "formula-v1",
                    "required": True,
                    "slot_id": "general_nonfinancial.growth",
                    "template_id": "general_nonfinancial",
                    "unit": "ratio",
                }
            ],
            "source_registry_hash": hashlib.sha256(raw["source"]).hexdigest(),
            "template_ids": ["general_nonfinancial"],
        }
    )
    hashes = {f"{role}_registry_hash": hashlib.sha256(value).hexdigest() for role, value in raw.items()}
    root = canonical_bytes(
        {
            "approval_id": None,
            "purpose": "test",
            "schema_version": "formal-registry-manifest-v1",
            **hashes,
        }
    )
    verifier = AcceptingVerifier()
    manifest = FormalRegistryManifest.from_signed_bytes(
        root, hashlib.sha256(root).hexdigest(), "fixture-key", verifier
    )
    blobs: dict[str, VerifiedRegistryBlob] = {}
    for role, value in raw.items():
        child_hash = hashlib.sha256(value).hexdigest()
        binding = canonical_bytes(
            {
                "child_sha256": child_hash,
                "registry_manifest_hash": manifest.manifest_hash,
                "registry_role": role,
            }
        )
        blobs[child_hash] = VerifiedRegistryBlob(
            registry_role=role,
            registry_hash=child_hash,
            canonical_json=value,
            signature=child_hash,
            key_id="fixture-key",
            approval_id=None,
            declared_registry_manifest_hash=manifest.manifest_hash,
            binding_signature=hashlib.sha256(binding).hexdigest(),
            binding_key_id="fixture-key",
        )
    return FormalRegistryBundleLoader(InMemoryRegistryRepository(manifest, blobs), verifier)


def calendar_binding(*, root: str = ROOT_A, prerequisite: str = "calendar-task") -> VerifiedCalendarBinding:
    selector_hash = hashlib.sha256(canonical_bytes({
        "as_of_rule": "visible_at_freeze", "context_kind": "trading_calendar",
        "exchange": "SZ", "scope_key": "fixture-calendar-SZ",
    })).hexdigest()
    return VerifiedCalendarBinding(
        snapshot_id="snapshot-calendar",
        manifest_sha256="f" * 64,
        exchange="SZ",
        freeze_at_utc=AS_OF,
        registry_manifest_hash=root,
        selector_hash=selector_hash,
        prerequisite_task_id=prerequisite,
    )


def context_payload_from_request(case: unittest.TestCase, request: object) -> FormalContextTaskPayload:
    factory = getattr(FormalContextTaskPayload, "from_request", None)
    case.assertTrue(callable(factory), "FormalContextTaskPayload must expose resolver-minted from_request")
    return factory(request)


def context_payload_kwargs(request: object) -> dict[str, object]:
    return {
        "context_kind": request.context_kind,
        "scope_key": request.scope_key,
        "security_id": request.security_id,
        "as_of_utc": request.as_of_utc,
        "official_request": request.official_request,
        "source": request.official_request.source,
        "request_version": request.request_version,
        "upstream_generation": request.upstream_generation,
        "refresh_generation": request.refresh_generation,
        "registry_manifest_hash": request.registry_manifest_hash,
        "relevant_registry_hashes": request.relevant_registry_hashes,
        "calendar_prerequisite_task_id": (
            None if request.calendar_binding is None else request.calendar_binding.prerequisite_task_id
        ),
        "calendar_binding": request.calendar_binding,
    }


class ContextRequestVerifier:
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool:
        return key_id == "fixture-key" and signature == hashlib.sha256(payload).hexdigest()


class EqualityLiar(str):
    def __eq__(self, _other: object) -> bool:
        return True

    def __ne__(self, _other: object) -> bool:
        return False


def context_descriptor(*, kind: str = "security_state", scope_key: str = "fixture-state", **changes: object) -> dict[str, object]:
    wire: dict[str, object] = {
        "context_kind": kind,
        "scope_key": scope_key,
        "security_scope": "security",
        "request_security": "input_security",
        "period_rule": "freeze_date_cn",
        "exchange_rule": "security_exchange",
        "fixed_exchange": None,
        "source": "cninfo",
        "dataset": "fixture-state",
        "parser_id": "fixture-parser",
        "parser_version": "fixture-v1",
        "mapping_version": "fixture-map-v1",
        "request_version": "formal-context-request-v1",
        "normalizer_version": "fixture-normalizer-v1",
        "generation_namespace": "fixture-context",
        "referenced_roles": ["scoring", "source"],
        "calendar_selector": None,
        "bootstrap_calendar": False,
        "allowed_regulatory_flags": [],
        "allowed_event_codes": [],
    }
    wire.update(changes)
    return wire


def thin_context_resolver(
    case: unittest.TestCase,
    *,
    descriptors: list[dict[str, object]] | None = None,
    configs: list[dict[str, object]] | None = None,
) -> tuple[SignedContextRequestResolver, str]:
    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    verifier = ContextRequestVerifier()
    raw_store = FormalSnapshotStore(root / "raw")
    store = StateStore(root / "state.sqlite", formal_snapshot_store=raw_store, registry_signature_verifier=verifier)
    store.initialize()
    roles = ("source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event")
    raw = {role: canonical_bytes({"registry_role": role, "schema_version": "fixture-v1"}) for role in roles}
    raw["source"] = canonical_bytes({
        "registry_role": "source", "schema_version": "formal-source-registry-v1",
        "configs": configs or [_formal_source_tests.config(dataset="fixture-state", exchange_scope="SZ")],
    })
    raw["scoring"] = canonical_bytes({
        "registry_role": "scoring", "schema_version": "formal-context-registry-v1",
        "descriptors": descriptors or [context_descriptor()],
    })
    hashes = {f"{role}_registry_hash": hashlib.sha256(value).hexdigest() for role, value in raw.items()}
    root_bytes = canonical_bytes({
        "schema_version": "formal-registry-manifest-v1", "purpose": "official", "approval_id": "fixture-approval", **hashes,
    })
    manifest = FormalRegistryManifest.from_signed_bytes(
        root_bytes, hashlib.sha256(root_bytes).hexdigest(), "fixture-key", verifier
    )
    for role, value in raw.items():
        registry_hash = hashlib.sha256(value).hexdigest()
        binding = canonical_bytes({
            "child_sha256": registry_hash, "registry_manifest_hash": manifest.manifest_hash, "registry_role": role,
        })
        store.put_formal_registry_blob(VerifiedRegistryBlob(
            registry_role=role, registry_hash=registry_hash, canonical_json=value, signature=registry_hash,
            key_id="fixture-key", approval_id="fixture-approval", declared_registry_manifest_hash=manifest.manifest_hash,
            binding_signature=hashlib.sha256(binding).hexdigest(), binding_key_id="fixture-key",
        ))
    store.put_formal_registry_manifest(manifest)
    return SignedContextRequestResolver(store, verifier), manifest.manifest_hash


class FormalDeepWorkerContractTests(unittest.TestCase):
    def test_thin_context_resolver_mints_a_sealed_canonical_request(self) -> None:
        resolver, root = thin_context_resolver(self)
        request = resolver.resolve(
            context_kind="security_state", scope_key="fixture-state", security_id="SZ000001",
            as_of_utc=AS_OF, registry_manifest_hash=root, upstream_generation="fixture-upstream-v1",
        )
        self.assertIs(type(request), FormalContextRequest)
        self.assertEqual(request.canonical_bytes(), canonical_bytes(request.to_dict()))

    def test_statement_specs_are_lexical_and_bind_key_to_derived_generation(self) -> None:
        specs = formal_statement_task_specs(
            security_id="SZ000001",
            report_period="2025-12-31",
            as_of_utc=AS_OF,
            source="cninfo",
            source_registry_hash=SOURCE_A,
            mapping_registry_hash=MAPPING_A,
            upstream_generation="discovery-v1",
            registry_manifest_hash=ROOT_A,
        )

        self.assertEqual(
            tuple(spec.payload["dataset"] for spec in specs),
            ("balance_sheet", "cash_flow_sheet", "profit_sheet"),
        )
        self.assertEqual(tuple(spec.kind for spec in specs), ("formal_statement",) * 3)
        self.assertEqual(len({spec.refresh_generation for spec in specs}), 1)
        self.assertTrue(all(spec.refresh_generation in spec.idempotency_key for spec in specs))
        self.assertTrue(all("discovery-v1" not in spec.idempotency_key for spec in specs))

    def test_generation_is_canonical_and_changes_for_root_role_and_calendar_binding(self) -> None:
        base = derive_collection_refresh_generation(
            upstream_generation="discovery-v1",
            registry_manifest_hash=ROOT_A,
            relevant_registry_hashes={"source": SOURCE_A, "mapping": MAPPING_A},
        )
        same_reordered = derive_collection_refresh_generation(
            upstream_generation="discovery-v1",
            registry_manifest_hash=ROOT_A,
            relevant_registry_hashes={"mapping": MAPPING_A, "source": SOURCE_A},
        )
        self.assertEqual(base, same_reordered)
        self.assertNotEqual(
            base,
            derive_collection_refresh_generation(
                upstream_generation="discovery-v1",
                registry_manifest_hash=ROOT_B,
                relevant_registry_hashes={"source": SOURCE_A, "mapping": MAPPING_A},
            ),
        )
        self.assertNotEqual(
            base,
            derive_collection_refresh_generation(
                upstream_generation="discovery-v1",
                registry_manifest_hash=ROOT_A,
                relevant_registry_hashes={"source": SOURCE_A, "mapping": "9" * 64},
            ),
        )

    def test_date_only_generation_requires_an_exact_selector_and_binding_pair(self) -> None:
        from ashare_pipeline.formal_sources import CalendarSelector

        selector = CalendarSelector("trading_calendar", "fixture-calendar-SZ", "SZ", "visible_at_freeze")
        binding = calendar_binding()
        with self.assertRaisesRegex(ValueError, "calendar"):
            derive_collection_refresh_generation(
                upstream_generation="discovery-v1",
                registry_manifest_hash=ROOT_A,
                relevant_registry_hashes={"source": SOURCE_A},
                calendar_selector=selector,
            )
        with self.assertRaisesRegex(ValueError, "calendar"):
            derive_collection_refresh_generation(
                upstream_generation="discovery-v1",
                registry_manifest_hash=ROOT_A,
                relevant_registry_hashes={"source": SOURCE_A},
                calendar_binding=binding,
            )
        date_only = derive_collection_refresh_generation(
            upstream_generation="discovery-v1",
            registry_manifest_hash=ROOT_A,
            relevant_registry_hashes={"source": SOURCE_A},
            calendar_selector=selector,
            calendar_binding=binding,
        )
        self.assertNotEqual(
            date_only,
            derive_collection_refresh_generation(
                upstream_generation="discovery-v1",
                registry_manifest_hash=ROOT_A,
                relevant_registry_hashes={"source": SOURCE_A},
                calendar_selector=selector,
                calendar_binding=calendar_binding(prerequisite="another-calendar-task"),
            ),
        )

    def test_typed_payloads_are_frozen_and_task_spec_only_accepts_closed_kind_payload_pairs(self) -> None:
        statement = FormalStatementTaskPayload(
            security_id="SZ000001", dataset="profit_sheet", report_period="2025-12-31", as_of_utc=AS_OF,
            source="cninfo", request_version="source-v1", source_registry_hash=SOURCE_A,
            mapping_registry_hash=MAPPING_A, upstream_generation="discovery-v1", refresh_generation="2" * 64,
            registry_manifest_hash=ROOT_A, relevant_registry_hashes=(("mapping", MAPPING_A), ("source", SOURCE_A)),
            calendar_prerequisite_task_id=None, calendar_binding=None,
        )
        feature = FormalFeatureBuildTaskPayload(
            security_id="SZ000001", as_of_utc=AS_OF, template_id="general_nonfinancial",
            source_registry_hash=SOURCE_A, mapping_registry_hash=MAPPING_A, feature_registry_hash=FEATURE_A,
            registry_manifest_hash=ROOT_A, source_snapshot_ids=("snapshot-a",), refresh_generation="3" * 64,
        )
        finalizer = FormalUniverseFinalizeTaskPayload(
            as_of_utc=AS_OF, registry_manifest_hash=ROOT_A,
            source_task_ids=("source-bj", "source-sh", "source-sz"), refresh_generation="4" * 64,
        )
        context_resolver, context_root = thin_context_resolver(self)
        context_request = context_resolver.resolve(
            context_kind="security_state", scope_key="fixture-state", security_id="SZ000001",
            as_of_utc=AS_OF, registry_manifest_hash=context_root, upstream_generation="fixture-upstream-v1",
        )
        context = context_payload_from_request(self, context_request)
        universe = FormalUniverseSourceTaskPayload(
            exchange="SZ", as_of_utc=AS_OF,
            official_request=OfficialRequest("szse", "universe_listing", None, "2026-08-31", "SZ"),
            source="szse", request_version="source-v1", upstream_generation="discovery-v1",
            refresh_generation="6" * 64, registry_manifest_hash=ROOT_A,
            relevant_registry_hashes=(("source", SOURCE_A),), calendar_prerequisite_task_id=None, calendar_binding=None,
        )
        payloads = (
            ("formal_statement", statement), ("formal_context", context),
            ("formal_universe_source", universe), ("formal_universe_finalize", finalizer),
            ("formal_feature_build", feature),
        )
        for kind, payload in payloads:
            spec = FormalTaskSpec.from_payload(payload)
            self.assertEqual(spec.kind, kind)
            self.assertEqual(spec.refresh_generation, payload.refresh_generation)
            with self.assertRaisesRegex((AttributeError, TypeError), ""):
                payload.refresh_generation = "7" * 64  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "kind|payload"):
            FormalTaskSpec("deep_statement", "key", "2" * 64, {"anything": "goes"})
        with self.assertRaisesRegex(ValueError, "kind|payload"):
            FormalTaskSpec("formal_statement", "key", "2" * 64, {"job": "generic"})

    def test_date_only_payload_rejects_mismatched_or_partial_prerequisite_binding(self) -> None:
        request = OfficialRequest("szse", "universe_listing", None, "2026-08-31", "SZ")
        common = dict(
            exchange="SZ", as_of_utc=AS_OF, official_request=request, source="szse", request_version="source-v1",
            upstream_generation="discovery-v1", refresh_generation="6" * 64, registry_manifest_hash=ROOT_A,
            relevant_registry_hashes=(("source", SOURCE_A),),
        )
        with self.assertRaisesRegex(ValueError, "calendar"):
            FormalUniverseSourceTaskPayload(**common, calendar_prerequisite_task_id="calendar-task", calendar_binding=None)
        with self.assertRaisesRegex(ValueError, "calendar"):
            FormalUniverseSourceTaskPayload(**common, calendar_prerequisite_task_id=None, calendar_binding=calendar_binding())
        with self.assertRaisesRegex(ValueError, "calendar"):
            FormalUniverseSourceTaskPayload(
                **common, calendar_prerequisite_task_id="calendar-task", calendar_binding=calendar_binding(root=ROOT_B)
            )

    def test_runtime_loader_reloads_verified_bundle_and_rejects_role_hash_disagreement(self) -> None:
        bundle_loader = fixture_bundle_loader()
        manifest_hash = bundle_loader._repository.manifest.manifest_hash  # fixture exposes the requested root.
        runtime_loader = FormalRegistryRuntimeLoader(
            bundle_loader, transport=NoTransport(), policies={}, parsers={}, effective_time_resolver=EffectiveTimeResolver()
        )
        runtime = runtime_loader.load(manifest_hash)
        self.assertEqual(runtime.bundle.manifest.manifest_hash, manifest_hash)
        self.assertEqual(runtime.source_adapter.source_registry_hash, runtime.bundle.blob("source").registry_hash)
        self.assertEqual(runtime.mapping_registry.registry_hash, runtime.bundle.blob("mapping").registry_hash)
        self.assertEqual(runtime.feature_registry.registry_hash, runtime.bundle.blob("feature").registry_hash)
        bad_blob = replace(
            bundle_loader._repository.blobs[runtime.bundle.manifest.mapping_registry_hash],
            registry_hash="0" * 64,
        )
        bundle_loader._repository.blobs[runtime.bundle.manifest.mapping_registry_hash] = bad_blob
        with self.assertRaisesRegex(ValueError, "hash|registry"):
            runtime_loader.load(manifest_hash)

    def test_direct_task_spec_rejects_a_forged_idempotency_key(self) -> None:
        payload = FormalStatementTaskPayload(
            security_id="SZ000001", dataset="profit_sheet", report_period="2025-12-31", as_of_utc=AS_OF,
            source="cninfo", request_version="source-v1", source_registry_hash=SOURCE_A,
            mapping_registry_hash=MAPPING_A, upstream_generation="discovery-v1", refresh_generation="2" * 64,
            registry_manifest_hash=ROOT_A, relevant_registry_hashes=(("mapping", MAPPING_A), ("source", SOURCE_A)),
            calendar_prerequisite_task_id=None, calendar_binding=None,
        )
        with self.assertRaisesRegex(ValueError, "idempotency|canonical"):
            FormalTaskSpec("formal_statement", "forged-key", payload.refresh_generation, payload)

    def test_finalizer_uses_its_three_positional_source_edges_without_lexical_sorting(self) -> None:
        valid_ids = ("z-bj-edge", "a-sh-edge", "m-sz-edge")
        payload = FormalUniverseFinalizeTaskPayload(
            as_of_utc=AS_OF, registry_manifest_hash=ROOT_A, source_task_ids=valid_ids,
            refresh_generation="4" * 64,
        )
        self.assertEqual(FormalTaskSpec.from_payload(payload).prerequisite_task_ids, valid_ids)
        for invalid in ((), ("one", "one", "three"), ["one", "two", "three"]):
            with self.assertRaisesRegex(ValueError, "source task"):
                FormalUniverseFinalizeTaskPayload(
                    as_of_utc=AS_OF, registry_manifest_hash=ROOT_A, source_task_ids=invalid,  # type: ignore[arg-type]
                    refresh_generation="4" * 64,
                )

    def test_task_spec_recursively_freezes_nested_payload_data(self) -> None:
        date_only = FormalUniverseSourceTaskPayload(
            exchange="SZ", as_of_utc=AS_OF,
            official_request=OfficialRequest("szse", "universe_listing", None, "2026-08-31", "SZ"),
            source="szse", request_version="source-v1", upstream_generation="discovery-v1",
            refresh_generation="6" * 64, registry_manifest_hash=ROOT_A,
            relevant_registry_hashes=(("source", SOURCE_A),), calendar_prerequisite_task_id="calendar-task",
            calendar_binding=calendar_binding(),
        )
        spec = FormalTaskSpec.from_payload(date_only)
        key = spec.idempotency_key
        finalizer = FormalTaskSpec.from_payload(FormalUniverseFinalizeTaskPayload(
            as_of_utc=AS_OF, registry_manifest_hash=ROOT_A,
            source_task_ids=("source-bj", "source-sh", "source-sz"), refresh_generation="4" * 64,
        ))
        with self.assertRaises(TypeError):
            spec.payload["relevant_registry_hashes"][0][1] = "0" * 64  # type: ignore[index]
        with self.assertRaises(TypeError):
            spec.payload["official_request"]["source"] = "bse"  # type: ignore[index]
        with self.assertRaises(TypeError):
            spec.payload["calendar_binding"]["freeze_at_utc"] = "2026-08-30T07:00:00+00:00"  # type: ignore[index]
        with self.assertRaises(TypeError):
            finalizer.payload["source_task_ids"][0] = "other"  # type: ignore[index]
        self.assertEqual(spec.idempotency_key, key)

    def test_runtime_direct_construction_rejects_adapter_from_another_root(self) -> None:
        loader_a = fixture_bundle_loader()
        root_a = loader_a._repository.manifest.manifest_hash
        loader_b = fixture_bundle_loader(scoring_schema="fixture-v2")
        root_b = loader_b._repository.manifest.manifest_hash
        runtime_loader_a = FormalRegistryRuntimeLoader(
            loader_a, transport=NoTransport(), policies={}, parsers={}, effective_time_resolver=EffectiveTimeResolver()
        )
        runtime_loader_b = FormalRegistryRuntimeLoader(
            loader_b, transport=NoTransport(), policies={}, parsers={}, effective_time_resolver=EffectiveTimeResolver()
        )
        runtime_a = runtime_loader_a.load(root_a)
        runtime_b = runtime_loader_b.load(root_b)
        with self.assertRaisesRegex(ValueError, "root|manifest|registry"):
            FormalRegistryRuntime(runtime_b.bundle, runtime_a.source_adapter, runtime_b.mapping_registry, runtime_b.feature_registry)

    def test_context_payload_uses_sealed_request_capability_and_keeps_it_unpersisted(self) -> None:
        descriptors = [
            context_descriptor(
                kind="trading_calendar", scope_key="fixture-calendar-SZ", security_scope="none",
                request_security="none", period_rule="none", exchange_rule="fixed_exchange", fixed_exchange="SZ",
                dataset="trading_calendar", bootstrap_calendar=True,
            ),
            context_descriptor(
                kind="market_close", scope_key="market-security", dataset="fixture-market-security",
            ),
        ]
        configs = [
            _formal_source_tests.config(dataset="trading_calendar", bootstrap_calendar=True),
            _formal_source_tests.config(dataset="fixture-market-security", exchange_scope="SZ"),
        ]
        resolver, root = thin_context_resolver(self, descriptors=descriptors, configs=configs)
        calendar_request = resolver.resolve(
            context_kind="trading_calendar", scope_key="fixture-calendar-SZ", security_id=None,
            as_of_utc=AS_OF, registry_manifest_hash=root, upstream_generation="fixture-calendar-v1",
        )
        calendar_payload = context_payload_from_request(self, calendar_request)
        calendar_spec = FormalTaskSpec.from_payload(calendar_payload)
        self.assertEqual(calendar_payload.context_kind, calendar_request.context_kind)
        self.assertEqual(calendar_payload.scope_key, "fixture-calendar-SZ")
        self.assertEqual(calendar_payload.relevant_registry_hashes, calendar_request.relevant_registry_hashes)
        self.assertNotIn("context_request", calendar_spec.payload)
        self.assertEqual(formal_context_task_specs(calendar_request), (calendar_spec,))

        market_request = resolver.resolve(
            context_kind="market_close", scope_key="market-security", security_id="SZ000001",
            as_of_utc=AS_OF, registry_manifest_hash=root, upstream_generation="fixture-market-v1",
        )
        market_payload = context_payload_from_request(self, market_request)
        self.assertEqual(market_payload.official_request.dataset, "fixture-market-security")
        self.assertEqual(market_payload.security_id, "SZ000001")

    def test_context_payload_rejects_raw_or_field_mismatched_construction(self) -> None:
        resolver, root = thin_context_resolver(self)
        request = resolver.resolve(
            context_kind="security_state", scope_key="fixture-state", security_id="SZ000001",
            as_of_utc=AS_OF, registry_manifest_hash=root, upstream_generation="fixture-upstream-v1",
        )
        raw = context_payload_kwargs(request)
        with self.assertRaisesRegex(ValueError, "Context|request|capability"):
            FormalContextTaskPayload(**raw)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "Context|request|context"):
            FormalContextTaskPayload(
                **{**raw, "context_kind": "market_close", "context_request": request}  # type: ignore[arg-type]
            )

    def test_context_payload_keeps_timestamp_only_calendar_shape_empty(self) -> None:
        resolver, root = thin_context_resolver(self)
        request = resolver.resolve(
            context_kind="security_state", scope_key="fixture-state", security_id="SZ000001",
            as_of_utc=AS_OF, registry_manifest_hash=root, upstream_generation="fixture-upstream-v1",
        )
        payload = context_payload_from_request(self, request)
        self.assertIsNone(payload.calendar_binding)
        self.assertIsNone(payload.calendar_prerequisite_task_id)

    def test_context_payload_rejects_hostile_equality_values_before_task_serialization(self) -> None:
        resolver, root = thin_context_resolver(self)
        request = resolver.resolve(
            context_kind="security_state", scope_key="fixture-state", security_id="SZ000001",
            as_of_utc=AS_OF, registry_manifest_hash=root, upstream_generation="fixture-upstream-v1",
        )
        raw = context_payload_kwargs(request)
        for field, hostile in (
            ("context_kind", EqualityLiar("market_close")),
            ("scope_key", EqualityLiar("attacker-scope")),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Context|payload|exact"):
                payload = FormalContextTaskPayload(
                    **{**raw, field: hostile, "context_request": request}  # type: ignore[arg-type]
                )
                FormalTaskSpec.from_payload(payload)

    def test_date_only_payload_binding_freeze_must_equal_payload_as_of(self) -> None:
        with self.assertRaisesRegex(ValueError, "calendar.*freeze|freeze.*calendar"):
            FormalUniverseSourceTaskPayload(
                exchange="SZ", as_of_utc="2026-08-30T07:00:00+00:00",
                official_request=OfficialRequest("szse", "universe_listing", None, "2026-08-31", "SZ"),
                source="szse", request_version="source-v1", upstream_generation="discovery-v1",
                refresh_generation="6" * 64, registry_manifest_hash=ROOT_A,
                relevant_registry_hashes=(("source", SOURCE_A),), calendar_prerequisite_task_id="calendar-task",
                calendar_binding=calendar_binding(),
            )

    def test_statement_roles_must_match_explicit_source_and_mapping_hashes(self) -> None:
        with self.assertRaisesRegex(ValueError, "relevant|source|mapping"):
            FormalStatementTaskPayload(
                security_id="SZ000001", dataset="profit_sheet", report_period="2025-12-31", as_of_utc=AS_OF,
                source="cninfo", request_version="source-v1", source_registry_hash=SOURCE_A,
                mapping_registry_hash=MAPPING_A, upstream_generation="discovery-v1", refresh_generation="2" * 64,
                registry_manifest_hash=ROOT_A, relevant_registry_hashes=(("mapping", "e" * 64), ("source", SOURCE_A)),
                calendar_prerequisite_task_id=None, calendar_binding=None,
            )


if __name__ == "__main__":
    unittest.main()
