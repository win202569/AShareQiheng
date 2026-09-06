"""Contract tests for the Task 6 formal collection worker boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import ashare_pipeline.formal_deep_worker as _formal_deep_worker
from ashare_pipeline.formal_deep_worker import (
    CalendarBindingPending,
    FormalContextTaskPayload,
    FormalFeatureBuildTaskPayload,
    FormalRegistryRuntime,
    FormalRegistryRuntimeLoader,
    FormalStatementTaskPayload,
    FormalTaskSpec,
    FormalWorkerDependencies,
    FormalUniverseFinalizeTaskPayload,
    FormalUniverseSourceTaskPayload,
    derive_collection_refresh_generation,
    enqueue_formal_feature_build,
    execute_queued_formal_work,
    formal_context_task_specs,
    formal_statement_task_specs,
)
from ashare_pipeline.formal_evidence import OfficialRequest, SourcePolicy, VerifiedCalendarBinding
from ashare_pipeline.formal_financial_schema import (
    FormalFinancialFact,
    extract_formal_financial_facts,
)
from ashare_pipeline.formal_registry_manifest import (
    FormalRegistryBundleLoader,
    FormalRegistryManifest,
    VerifiedRegistryBlob,
)
from ashare_pipeline.formal_context_schema import FormalContextRequest, SignedContextRequestResolver
from ashare_pipeline.formal_snapshot_repository import FormalSnapshotRepository
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore
from ashare_pipeline.formal_sources import (
    CalendarSelector,
    FormalRetryableSourceError,
    FormalSourceBlocked,
    FormalTerminalSourceError,
)
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


def legacy_feature_refresh_generation(
    facts: tuple[object, ...], registry_manifest_hash: str
) -> tuple[str, tuple[str, ...]]:
    """Hand-derived pre-D1 feature-task identity, retained only for migration coverage."""

    snapshots: dict[str, dict[str, str]] = {}
    fact_ids: list[str] = []
    for fact in facts:
        wire = fact.to_dict()
        fact_ids.append(wire["id"])
        snapshot = {
            "content_sha256": wire["source_content_sha256"],
            "refresh_generation": wire["source_refresh_generation"],
            "snapshot_id": wire["source_snapshot_id"],
        }
        prior = snapshots.setdefault(snapshot["snapshot_id"], snapshot)
        if prior != snapshot:
            raise AssertionError("fixture has conflicting legacy snapshot lineage")
    snapshot_ids = tuple(sorted(snapshots))
    wire = {
        "formal_fact_ids": sorted(set(fact_ids)),
        "registry_manifest_hash": registry_manifest_hash,
        "selected_statement_snapshots": [snapshots[item] for item in snapshot_ids],
    }
    return hashlib.sha256(canonical_bytes(wire)).hexdigest(), snapshot_ids


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


class CountingTransport:
    def __init__(self, response: object, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[object] = []

    def send(self, request: object) -> object:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


class PeriodDocumentParser:
    """Return a real parsed statement document for each frozen report period."""

    def __init__(self, documents: dict[str, object]) -> None:
        self.documents = documents
        self.calls: list[tuple[object, object, object]] = []

    def parse(self, raw_bytes: object, *, request: object, config: object) -> object:
        self.calls.append((raw_bytes, request, config))
        return self.documents[getattr(request, "period_or_date")]


class ReplayErrorParser(_formal_source_tests.FixtureParser):
    """Allow a verified fetch, then fail the mandated persisted-raw reparse."""

    def __init__(self, document: object, error: Exception) -> None:
        super().__init__(document)
        self._error = error

    def parse(self, raw_bytes: object, *, request: object, config: object) -> object:
        document = super().parse(raw_bytes, request=request, config=config)
        if len(self.calls) == 2:
            raise self._error
        return document


class InitialErrorParser(_formal_source_tests.FixtureParser):
    """Raise only after the source adapter has performed its real transport."""

    def __init__(self, document: object, error: Exception) -> None:
        super().__init__(document)
        self._error = error

    def parse(self, raw_bytes: object, *, request: object, config: object) -> object:
        super().parse(raw_bytes, request=request, config=config)
        raise self._error


class LeaseLossStore:
    """Delegate real persistence but make the worker lose its next renewal."""

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def __getattr__(self, name: str) -> object:
        return getattr(self._store, name)

    def renew_formal_task_lease(self, *_args: object, **_kwargs: object) -> str:
        raise ValueError("formal task is not held by the current unexpired lease owner")


class PostExtractionLeaseLossStore:
    """Let parsing begin, then lose ownership immediately before fact persistence."""

    def __init__(self, store: StateStore) -> None:
        self._store = store
        self._renewal_count = 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._store, name)

    def renew_formal_task_lease(self, *args: object, **kwargs: object) -> str:
        self._renewal_count += 1
        if self._renewal_count == 2:
            raise ValueError("formal task is not held by the current unexpired lease owner")
        return self._store.renew_formal_task_lease(*args, **kwargs)


class PostFactLeaseLossStore:
    """Make facts durable, then prove no stale feature side effects are possible."""

    def __init__(self, store: StateStore) -> None:
        self._store = store
        self._renewal_count = 0
        self.feature_enqueue_calls = 0
        self.feature_supersede_calls = 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._store, name)

    def renew_formal_task_lease(self, *args: object, **kwargs: object) -> str:
        self._renewal_count += 1
        if self._renewal_count == 3:
            raise ValueError("formal task is not held by the current unexpired lease owner")
        return self._store.renew_formal_task_lease(*args, **kwargs)

    def enqueue_formal_task(self, *args: object, **kwargs: object) -> str:
        if args and args[0] == "formal_feature_build":
            self.feature_enqueue_calls += 1
        return self._store.enqueue_formal_task(*args, **kwargs)

    def supersede_formal_tasks(self, *args: object, **kwargs: object) -> int:
        self.feature_supersede_calls += 1
        return self._store.supersede_formal_tasks(*args, **kwargs)


class TemporarilyUnverifiedSourceStore:
    """Expose a source task's pre-completion state while retaining real evidence."""

    def __init__(self, store: StateStore, source_task_id: str) -> None:
        self._store = store
        self._source_task_id = source_task_id

    def __getattr__(self, name: str) -> object:
        return getattr(self._store, name)

    def get_formal_task(self, task_id: str) -> dict[str, object] | None:
        task = self._store.get_formal_task(task_id)
        if task is None or task_id != self._source_task_id:
            return task
        return {**task, "status": "leased"}


class OrphanFeatureResultStore:
    """Keep the actual source evidence but remove its statement→feature audit edge."""

    def __init__(self, store: StateStore, source_task_id: str) -> None:
        self._store = store
        self._source_task_id = source_task_id

    def __getattr__(self, name: str) -> object:
        return getattr(self._store, name)

    def get_formal_task(self, task_id: str) -> dict[str, object] | None:
        task = self._store.get_formal_task(task_id)
        if task is None or task_id != self._source_task_id:
            return task
        result = dict(task["result"])
        result["feature_task_ids"] = ["orphan-feature-task"]
        return {**task, "result": result}


class RawBytesDriftSnapshots:
    """Leave real source provenance intact but surface changed stored raw bytes."""

    def __init__(self, snapshots: FormalSnapshotRepository) -> None:
        self._snapshots = snapshots

    def read_verified_raw(self, _ref: object) -> bytes:
        return b'{"tampered":true}'


class EffectiveTimeResolver:
    def next_exchange_close(self, *_args: object, **_kwargs: object) -> str:
        return AS_OF


class ExactCalendarBindingRepository:
    def __init__(self, binding: VerifiedCalendarBinding) -> None:
        self.binding = binding
        self.calls: list[tuple[object, object, object, object]] = []

    def resolve_verified_calendar_binding(
        self,
        selector: object,
        exchange: object,
        as_of_utc: object,
        registry_manifest_hash: object,
    ) -> VerifiedCalendarBinding:
        self.calls.append((selector, exchange, as_of_utc, registry_manifest_hash))
        return self.binding


def fixture_bundle_loader(
    *,
    scoring_schema: str = "fixture-v1",
    purpose: str = "test",
    source_configs: list[dict[str, object]] | None = None,
    statement_dataset: str = "annual_report",
    statement_exchange: str = "BJ",
    statement_mappings: list[dict[str, object]] | None = None,
    binding_mapping_ids: list[str] | None = None,
    feature_slots: list[dict[str, object]] | None = None,
    feature_template_ids: list[str] | None = None,
) -> FormalRegistryBundleLoader:
    """Make a real, test-purpose verified root from signed child bytes."""
    roles = ("source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event")
    raw = {
        role: canonical_bytes({"registry_role": role, "schema_version": "fixture-v1"})
        for role in roles
    }
    raw["scoring"] = canonical_bytes({"registry_role": "scoring", "schema_version": scoring_schema})
    raw["source"] = canonical_bytes(
        {
            "configs": [] if source_configs is None else source_configs,
            "registry_role": "source",
            "schema_version": "formal-source-registry-v1",
        }
    )
    mappings = statement_mappings or [
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
    ]
    mapping_ids = binding_mapping_ids or ["operating_profit"]
    raw["mapping"] = canonical_bytes(
        {
            "bindings": [
                {
                    "dataset": statement_dataset,
                    "exchange_scope": statement_exchange,
                    "mapping_ids": mapping_ids,
                    "mapping_version": "fixture-map-v1",
                    "parser_id": "fixture-parser",
                    "parser_version": "fixture-v1",
                    "source": "cninfo",
                }
            ],
            "mappings": mappings,
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
            "slots": feature_slots or [
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
            "template_ids": feature_template_ids or ["general_nonfinancial"],
        }
    )
    hashes = {f"{role}_registry_hash": hashlib.sha256(value).hexdigest() for role, value in raw.items()}
    root = canonical_bytes(
        {
            "approval_id": "fixture-approval" if purpose == "official" else None,
            "purpose": purpose,
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
            approval_id="fixture-approval" if purpose == "official" else None,
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


def statement_execution_fixture(
    case: unittest.TestCase,
    *,
    registry_purpose: str = "official",
    transport_error: Exception | None = None,
    replay_parse_error: Exception | None = None,
    initial_parse_error: Exception | None = None,
    document_rows: tuple[dict[str, object], ...] | None = None,
) -> tuple[
    StateStore,
    FormalSnapshotRepository,
    FormalRegistryRuntimeLoader,
    CountingTransport,
    _formal_source_tests.FixtureParser,
    str,
    FormalStatementTaskPayload,
]:
    """Create one real signed official statement task with local-only evidence."""
    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    raw_store = FormalSnapshotStore(root / "raw")
    store = StateStore(
        root / "state.sqlite",
        formal_snapshot_store=raw_store,
        registry_signature_verifier=AcceptingVerifier(),
    )
    store.initialize()
    bundle_loader = fixture_bundle_loader(
        purpose=registry_purpose,
        source_configs=[_formal_source_tests.config(dataset="profit_sheet")],
        statement_dataset="profit_sheet",
        statement_exchange="SZ",
    )
    manifest_hash = bundle_loader._repository.manifest.manifest_hash
    document = _formal_source_tests.timestamp_document(
        declared_security_id="SZ000001",
        declared_period="2025-12-31",
        accounting_basis="consolidated",
        rows=(
            ({"ITEM": "OPERATING_PROFIT", "VALUE": 100},)
            if document_rows is None
            else document_rows
        ),
    )
    transport = CountingTransport(
        _formal_source_tests.response(raw=b'{"statement":true}'),
        transport_error,
    )
    if initial_parse_error is not None:
        parser = InitialErrorParser(document, initial_parse_error)
    elif replay_parse_error is not None:
        parser = ReplayErrorParser(document, replay_parse_error)
    else:
        parser = _formal_source_tests.FixtureParser(document)
    runtime_loader = FormalRegistryRuntimeLoader(
        bundle_loader,
        transport=transport,
        policies={"cninfo": SourcePolicy.cninfo()},
        parsers={"fixture-parser": parser},
        effective_time_resolver=EffectiveTimeResolver(),
    )
    runtime = runtime_loader.load(manifest_hash)
    generation = derive_collection_refresh_generation(
        upstream_generation="statement-upstream-v1",
        registry_manifest_hash=manifest_hash,
        relevant_registry_hashes={
            "mapping": runtime.bundle.manifest.mapping_registry_hash,
            "source": runtime.bundle.manifest.source_registry_hash,
        },
    )
    payload = FormalStatementTaskPayload(
        security_id="SZ000001",
        dataset="profit_sheet",
        report_period="2025-12-31",
        as_of_utc=AS_OF,
        source="cninfo",
        request_version="formal-v5",
        source_registry_hash=runtime.bundle.manifest.source_registry_hash,
        mapping_registry_hash=runtime.bundle.manifest.mapping_registry_hash,
        upstream_generation="statement-upstream-v1",
        refresh_generation=generation,
        registry_manifest_hash=manifest_hash,
        relevant_registry_hashes=(
            ("mapping", runtime.bundle.manifest.mapping_registry_hash),
            ("source", runtime.bundle.manifest.source_registry_hash),
        ),
        calendar_prerequisite_task_id=None,
        calendar_binding=None,
    )
    return (
        store,
        FormalSnapshotRepository(root / "raw", store),
        runtime_loader,
        transport,
        parser,
        manifest_hash,
        payload,
    )


def history_ready_feature_execution_fixture(
    case: unittest.TestCase,
) -> tuple[
    StateStore,
    FormalSnapshotRepository,
    FormalRegistryRuntimeLoader,
    CountingTransport,
    PeriodDocumentParser,
    str,
    tuple[FormalStatementTaskPayload, ...],
]:
    """Create the exact 4-FY/8-quarter source evidence needed by the D1 gate."""

    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    raw_store = FormalSnapshotStore(root / "raw")
    store = StateStore(
        root / "state.sqlite",
        formal_snapshot_store=raw_store,
        registry_signature_verifier=AcceptingVerifier(),
    )
    store.initialize()
    mapping_ids = [
        "operating_profit_fy",
        "operating_profit_h1",
        "operating_profit_q1",
        "operating_profit_q3",
    ]
    mappings = [
        {
            "accounting_basis": "consolidated",
            "mapping_id": mapping_id,
            "metric_key": "income.operating_profit",
            "nature": "duration",
            "period_kind": period_kind,
            "source_field": f"OPERATING_PROFIT_{period_kind}",
            "statement": "income",
            "unit": "CNY",
        }
        for mapping_id, period_kind in (
            ("operating_profit_fy", "FY"),
            ("operating_profit_h1", "H1"),
            ("operating_profit_q1", "Q1"),
            ("operating_profit_q3", "Q3"),
        )
    ]
    bundle_loader = fixture_bundle_loader(
        purpose="official",
        source_configs=[_formal_source_tests.config(dataset="profit_sheet")],
        statement_dataset="profit_sheet",
        statement_exchange="SZ",
        statement_mappings=mappings,
        binding_mapping_ids=mapping_ids,
        feature_slots=[
            {
                "dimension": "G",
                "formula": {
                    "fact_key": "income.operating_profit",
                    "op": "fact",
                    "period_key": "FY2025",
                },
                "formula_version": "formula-v1",
                "required": True,
                "slot_id": "bank.growth",
                "template_id": "bank",
                "unit": "CNY",
            },
            {
                "dimension": "G",
                "formula": {
                    "fact_key": "income.operating_profit",
                    "op": "fact",
                    "period_key": "FY2025",
                },
                "formula_version": "formula-v1",
                "required": True,
                "slot_id": "broker.growth",
                "template_id": "broker",
                "unit": "CNY",
            },
            {
                "dimension": "G",
                "formula": {
                    "fact_key": "income.operating_profit",
                    "op": "fact",
                    "period_key": "FY2025",
                },
                "formula_version": "formula-v1",
                "required": True,
                "slot_id": "general_nonfinancial.growth",
                "template_id": "general_nonfinancial",
                "unit": "CNY",
            },
            {
                "dimension": "G",
                "formula": {
                    "fact_key": "income.operating_profit",
                    "op": "fact",
                    "period_key": "FY2025",
                },
                "formula_version": "formula-v1",
                "required": True,
                "slot_id": "insurance.growth",
                "template_id": "insurance",
                "unit": "CNY",
            },
            {
                "dimension": "G",
                "formula": {
                    "fact_key": "income.operating_profit",
                    "op": "fact",
                    "period_key": "FY2025",
                },
                "formula_version": "formula-v1",
                "required": True,
                "slot_id": "real_estate.growth",
                "template_id": "real_estate",
                "unit": "CNY",
            },
        ],
        feature_template_ids=[
            "bank",
            "broker",
            "general_nonfinancial",
            "insurance",
            "real_estate",
        ],
    )
    manifest_hash = bundle_loader._repository.manifest.manifest_hash
    cumulative_values = {
        "2022-12-31": 70,
        "2023-12-31": 80,
        "2024-03-31": 20,
        "2024-06-30": 45,
        "2024-09-30": 75,
        "2024-12-31": 110,
        "2025-03-31": 25,
        "2025-06-30": 55,
        "2025-09-30": 90,
        "2025-12-31": 130,
        "2026-03-31": 35,
        "2026-06-30": 75,
    }
    period_kind_by_period = {
        period: (
            "FY"
            if period.endswith("-12-31")
            else "H1"
            if period.endswith("-06-30")
            else "Q1"
            if period.endswith("-03-31")
            else "Q3"
        )
        for period in cumulative_values
    }
    parser = PeriodDocumentParser(
        {
            period: _formal_source_tests.timestamp_document(
                declared_security_id="SZ000001",
                declared_period=period,
                published_at_utc="2026-08-01T00:00:00+00:00",
                source_updated_at_utc="2026-08-01T00:00:00+00:00",
                accounting_basis="consolidated",
                rows=(
                    {
                        "ITEM": f"OPERATING_PROFIT_{period_kind_by_period[period]}",
                        "VALUE": value,
                    },
                ),
            )
            for period, value in cumulative_values.items()
        }
    )
    transport = CountingTransport(_formal_source_tests.response(raw=b'{"history":true}'))
    runtime_loader = FormalRegistryRuntimeLoader(
        bundle_loader,
        transport=transport,
        policies={"cninfo": SourcePolicy.cninfo()},
        parsers={"fixture-parser": parser},
        effective_time_resolver=EffectiveTimeResolver(),
    )
    runtime = runtime_loader.load(manifest_hash)
    generation = derive_collection_refresh_generation(
        upstream_generation="history-upstream-v1",
        registry_manifest_hash=manifest_hash,
        relevant_registry_hashes={
            "mapping": runtime.bundle.manifest.mapping_registry_hash,
            "source": runtime.bundle.manifest.source_registry_hash,
        },
    )
    payloads = tuple(
        FormalStatementTaskPayload(
            security_id="SZ000001",
            dataset="profit_sheet",
            report_period=period,
            as_of_utc=AS_OF,
            source="cninfo",
            request_version="formal-v5",
            source_registry_hash=runtime.bundle.manifest.source_registry_hash,
            mapping_registry_hash=runtime.bundle.manifest.mapping_registry_hash,
            upstream_generation="history-upstream-v1",
            refresh_generation=generation,
            registry_manifest_hash=manifest_hash,
            relevant_registry_hashes=(
                ("mapping", runtime.bundle.manifest.mapping_registry_hash),
                ("source", runtime.bundle.manifest.source_registry_hash),
            ),
            calendar_prerequisite_task_id=None,
            calendar_binding=None,
        )
        for period in cumulative_values
    )
    return (
        store,
        FormalSnapshotRepository(root / "raw", store),
        runtime_loader,
        transport,
        parser,
        manifest_hash,
        payloads,
    )


def replay_receipt_fixture(
    case: unittest.TestCase,
    error: Exception,
) -> tuple[
    StateStore,
    FormalSnapshotRepository,
    FormalRegistryRuntimeLoader,
    CountingTransport,
    ReplayErrorParser,
    FormalStatementTaskPayload,
    str,
]:
    """Persist a real receipt, then arrange exactly its replay parse to fail."""

    (
        store,
        snapshots,
        runtime_loader,
        transport,
        parser,
        manifest_hash,
        payload,
    ) = statement_execution_fixture(case, replay_parse_error=error)
    case.assertIsInstance(parser, ReplayErrorParser)
    spec = FormalTaskSpec.from_payload(payload)
    task_id = store.enqueue_formal_task(
        spec.kind,
        spec.idempotency_key,
        spec.refresh_generation,
        spec.payload,
        spec.prerequisite_task_ids,
    )
    case.assertIsNotNone(
        store.lease_next_formal_task(("formal_statement",), "crashed-owner", 120)
    )
    runtime = runtime_loader.load(manifest_hash)
    fetch, verification, _ = runtime.source_adapter.fetch_verified(
        OfficialRequest("cninfo", "profit_sheet", "SZ000001", "2025-12-31", "SZ"),
        refresh_generation=payload.refresh_generation,
        calendar_binding=None,
    )
    snapshots.persist_verified(
        fetch,
        verification,
        producing_task_id=task_id,
        worker_id="crashed-owner",
    )
    store.fail_formal_task(
        task_id,
        "crashed-owner",
        {"code": "simulated_crash"},
        "retryable_failed",
        datetime.now(timezone.utc).isoformat(),
    )
    return store, snapshots, runtime_loader, transport, parser, payload, task_id


def date_only_statement_execution_fixture(
    case: unittest.TestCase,
) -> tuple[
    StateStore,
    FormalSnapshotRepository,
    FormalRegistryRuntimeLoader,
    CountingTransport,
    str,
    FormalStatementTaskPayload,
    ExactCalendarBindingRepository,
]:
    """Create a canonical UTC date-only statement plus a verified calendar edge."""

    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    binding_holder: dict[str, VerifiedCalendarBinding] = {}

    def resolve_snapshot_binding(_request: object) -> VerifiedCalendarBinding | None:
        return binding_holder.get("binding")

    raw_store = FormalSnapshotStore(
        root / "raw", calendar_binding_resolver=resolve_snapshot_binding
    )
    store = StateStore(
        root / "state.sqlite",
        formal_snapshot_store=raw_store,
        registry_signature_verifier=AcceptingVerifier(),
    )
    store.initialize()
    selector = CalendarSelector(
        "trading_calendar", "fixture-calendar-SZ", "SZ", "visible_at_freeze"
    )
    source_config = _formal_source_tests.config(
        dataset="profit_sheet",
        exchange_scope="SZ",
        calendar_selector={
            "as_of_rule": selector.as_of_rule,
            "context_kind": selector.context_kind,
            "exchange": selector.exchange,
            "scope_key": selector.scope_key,
        },
    )
    bundle_loader = fixture_bundle_loader(
        purpose="official",
        source_configs=[source_config],
        statement_dataset="profit_sheet",
        statement_exchange="SZ",
    )
    manifest_hash = bundle_loader._repository.manifest.manifest_hash
    document = _formal_source_tests.timestamp_document(
        declared_security_id="SZ000001",
        declared_period="2025-12-31",
        published_at_utc="2026-08-20T00:00:00+00:00",
        published_precision="date_only",
        accounting_basis="consolidated",
        rows=({"ITEM": "OPERATING_PROFIT", "VALUE": 100},),
    )
    transport = CountingTransport(_formal_source_tests.response(raw=b'{"date-only":true}'))
    runtime_loader = FormalRegistryRuntimeLoader(
        bundle_loader,
        transport=transport,
        policies={"cninfo": SourcePolicy.cninfo()},
        parsers={"fixture-parser": _formal_source_tests.FixtureParser(document)},
        effective_time_resolver=EffectiveTimeResolver(),
    )
    runtime = runtime_loader.load(manifest_hash)
    prerequisite_payload = FormalFeatureBuildTaskPayload(
        security_id="SZ000001",
        as_of_utc=AS_OF,
        template_id="general_nonfinancial",
        source_registry_hash=runtime.bundle.manifest.source_registry_hash,
        mapping_registry_hash=runtime.bundle.manifest.mapping_registry_hash,
        feature_registry_hash=runtime.bundle.manifest.feature_registry_hash,
        registry_manifest_hash=manifest_hash,
        source_snapshot_ids=("fixture-calendar-snapshot",),
        refresh_generation="a" * 64,
    )
    prerequisite_spec = FormalTaskSpec.from_payload(prerequisite_payload)
    prerequisite_task_id = store.enqueue_formal_task(
        prerequisite_spec.kind,
        prerequisite_spec.idempotency_key,
        prerequisite_spec.refresh_generation,
        prerequisite_spec.payload,
        prerequisite_spec.prerequisite_task_ids,
    )
    case.assertIsNotNone(
        store.lease_next_formal_task(("formal_feature_build",), "calendar-owner", 120)
    )
    store.complete_formal_task(prerequisite_task_id, "calendar-owner", {"fixture": "verified"})
    binding = VerifiedCalendarBinding(
        snapshot_id="fixture-calendar-snapshot",
        manifest_sha256="f" * 64,
        exchange="SZ",
        freeze_at_utc=AS_OF,
        registry_manifest_hash=manifest_hash,
        selector_hash=selector.selector_hash,
        prerequisite_task_id=prerequisite_task_id,
    )
    binding_holder["binding"] = binding
    request = OfficialRequest("cninfo", "profit_sheet", "SZ000001", "2025-12-31", "SZ")
    config = runtime.source_adapter.registry.select(request)
    case.assertEqual(config.calendar_selector, selector)
    generation = derive_collection_refresh_generation(
        upstream_generation="date-only-upstream-v1",
        registry_manifest_hash=manifest_hash,
        relevant_registry_hashes={
            "mapping": runtime.bundle.manifest.mapping_registry_hash,
            "source": runtime.bundle.manifest.source_registry_hash,
        },
        calendar_selector=config.calendar_selector,
        calendar_binding=binding,
    )
    payload = FormalStatementTaskPayload(
        security_id="SZ000001",
        dataset="profit_sheet",
        report_period="2025-12-31",
        as_of_utc=AS_OF,
        source="cninfo",
        request_version="formal-v5",
        source_registry_hash=runtime.bundle.manifest.source_registry_hash,
        mapping_registry_hash=runtime.bundle.manifest.mapping_registry_hash,
        upstream_generation="date-only-upstream-v1",
        refresh_generation=generation,
        registry_manifest_hash=manifest_hash,
        relevant_registry_hashes=(
            ("mapping", runtime.bundle.manifest.mapping_registry_hash),
            ("source", runtime.bundle.manifest.source_registry_hash),
        ),
        calendar_prerequisite_task_id=prerequisite_task_id,
        calendar_binding=binding,
    )
    return (
        store,
        FormalSnapshotRepository(root / "raw", store),
        runtime_loader,
        transport,
        manifest_hash,
        payload,
        ExactCalendarBindingRepository(binding),
    )


class FormalDeepWorkerContractTests(unittest.TestCase):
    def test_statement_receipt_replay_reparses_persisted_raw_without_second_fetch(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            parser,
            manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        leased = store.lease_next_formal_task(
            ("formal_statement",), "crashed-owner", 120
        )
        self.assertIsNotNone(leased)
        runtime = runtime_loader.load(manifest_hash)
        fetch, verification, _ = runtime.source_adapter.fetch_verified(
            OfficialRequest("cninfo", "profit_sheet", "SZ000001", "2025-12-31", "SZ"),
            refresh_generation=payload.refresh_generation,
            calendar_binding=None,
        )
        snapshot = snapshots.persist_verified(
            fetch,
            verification,
            producing_task_id=task_id,
            worker_id="crashed-owner",
        )
        store.fail_formal_task(
            task_id,
            "crashed-owner",
            {"code": "simulated_crash"},
            "retryable_failed",
            datetime.now(timezone.utc).isoformat(),
        )
        parser_calls_before_recovery = len(parser.calls)
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        try:
            summary = execute_queued_formal_work(
                dependencies, worker_id="recovery-worker", max_jobs=1
            )
        except NotImplementedError:
            summary = None

        self.assertIsNotNone(
            summary,
            "a statement receipt must be replayed rather than left as an unimplemented worker path",
        )
        assert summary is not None
        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(summary.verified_statement_count, 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(len(parser.calls), parser_calls_before_recovery + 1)
        self.assertEqual(store.get_formal_task(task_id)["status"], "verified")
        facts = store.list_formal_financial_facts(security_id="SZ000001")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].source_snapshot_id, snapshot.snapshot_id)
        feature_tasks = store.list_formal_tasks(kinds=("formal_feature_build",))
        self.assertEqual(len(feature_tasks), 1)
        self.assertEqual(feature_tasks[0]["payload"]["security_id"], "SZ000001")

    def test_statement_receipt_replay_rejects_a_valid_snapshot_for_another_request(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            parser,
            manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        self.assertIsNotNone(
            store.lease_next_formal_task(("formal_statement",), "crashed-owner", 120)
        )
        parser.document = replace(parser.document, declared_security_id="SZ000002")
        runtime = runtime_loader.load(manifest_hash)
        fetch, verification, _ = runtime.source_adapter.fetch_verified(
            OfficialRequest("cninfo", "profit_sheet", "SZ000002", "2025-12-31", "SZ"),
            refresh_generation=payload.refresh_generation,
            calendar_binding=None,
        )
        snapshots.persist_verified(
            fetch,
            verification,
            producing_task_id=task_id,
            worker_id="crashed-owner",
        )
        store.fail_formal_task(
            task_id,
            "crashed-owner",
            {"code": "simulated_crash"},
            "retryable_failed",
            datetime.now(timezone.utc).isoformat(),
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="wrong-receipt-recovery-worker", max_jobs=1
        )

        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNotNone(store.get_formal_task_snapshot_receipt(task_id))
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000001"), ())
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000002"), ())
        self.assertEqual(store.list_formal_tasks(kinds=("formal_feature_build",)), [])
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "terminal_failed")
        self.assertEqual(task["error"]["code"], "statement_validation_failed")

    def test_statement_replay_retryable_parser_error_keeps_receipt_and_pass_continues(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            parser,
            payload,
            replay_task_id,
        ) = replay_receipt_fixture(self, FormalRetryableSourceError("fixture replay timeout"))
        parser.document = replace(parser.document, declared_security_id="SZ000002")
        other_spec = FormalTaskSpec.from_payload(
            replace(payload, security_id="SZ000002")
        )
        other_task_id = store.enqueue_formal_task(
            other_spec.kind,
            other_spec.idempotency_key,
            other_spec.refresh_generation,
            other_spec.payload,
            other_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        transport_before_recovery = len(transport.requests)

        summary = execute_queued_formal_work(
            dependencies, worker_id="retryable-replay-worker", max_jobs=2
        )

        self.assertEqual(summary.retryable_failed, 1)
        self.assertEqual(summary.verified_statement_count, 1)
        self.assertEqual(summary.remote_attempts, 1)
        self.assertEqual(len(transport.requests), transport_before_recovery + 1)
        self.assertIsNotNone(store.get_formal_task_snapshot_receipt(replay_task_id))
        replay_task = store.get_formal_task(replay_task_id)
        self.assertEqual(replay_task["status"], "retryable_failed")
        self.assertEqual(replay_task["error"]["code"], "source_retryable_failed")
        self.assertEqual(store.get_formal_task(other_task_id)["status"], "verified")
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000001"), ())
        self.assertEqual(len(store.list_formal_financial_facts(security_id="SZ000002")), 1)

    def test_statement_replay_blocked_parser_opens_circuit_and_pass_continues(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            parser,
            payload,
            replay_task_id,
        ) = replay_receipt_fixture(self, FormalSourceBlocked("fixture replay challenge"))
        parser.document = replace(parser.document, declared_security_id="SZ000002")
        other_spec = FormalTaskSpec.from_payload(
            replace(payload, security_id="SZ000002")
        )
        other_task_id = store.enqueue_formal_task(
            other_spec.kind,
            other_spec.idempotency_key,
            other_spec.refresh_generation,
            other_spec.payload,
            other_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        transport_before_recovery = len(transport.requests)

        summary = execute_queued_formal_work(
            dependencies, worker_id="blocked-replay-worker", max_jobs=2
        )

        self.assertEqual(summary.retryable_failed, 2)
        self.assertEqual(summary.verified_statement_count, 0)
        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(summary.open_circuits, ("cninfo",))
        self.assertEqual(len(transport.requests), transport_before_recovery)
        self.assertIsNotNone(store.get_formal_task_snapshot_receipt(replay_task_id))
        replay_task = store.get_formal_task(replay_task_id)
        self.assertEqual(replay_task["status"], "retryable_failed")
        self.assertEqual(replay_task["error"]["code"], "source_blocked")
        other_task = store.get_formal_task(other_task_id)
        self.assertEqual(other_task["status"], "retryable_failed")
        self.assertEqual(other_task["error"]["code"], "source_circuit_open")
        self.assertEqual(store.get_formal_source_circuit("cninfo")["state"], "open")

    def test_statement_lost_lease_after_receipt_never_writes_facts_or_completion(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=LeaseLossStore(store),
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        try:
            summary = execute_queued_formal_work(
                dependencies, worker_id="lost-lease-worker", max_jobs=1
            )
        except ValueError:
            summary = None

        self.assertIsNotNone(
            summary,
            "lost ownership after a raw receipt must stop safely rather than propagate into writes",
        )
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNotNone(store.get_formal_task_snapshot_receipt(task_id))
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000001"), ())
        self.assertNotEqual(store.get_formal_task(task_id)["status"], "verified")

    def test_statement_lost_lease_after_extraction_never_writes_facts_or_feature_task(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=PostExtractionLeaseLossStore(store),
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="post-extraction-loss-worker", max_jobs=1
        )

        self.assertEqual(summary.verified_statement_count, 0)
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNotNone(store.get_formal_task_snapshot_receipt(task_id))
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000001"), ())
        self.assertEqual(store.list_formal_tasks(kinds=("formal_feature_build",)), [])
        self.assertNotEqual(store.get_formal_task(task_id)["status"], "verified")

    def test_statement_lost_lease_after_fact_write_never_schedules_or_supersedes_features(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        lease_loss_store = PostFactLeaseLossStore(store)
        dependencies = FormalWorkerDependencies(
            store=lease_loss_store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="post-fact-loss-worker", max_jobs=1
        )

        self.assertEqual(summary.verified_statement_count, 0)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(len(store.list_formal_financial_facts(security_id="SZ000001")), 1)
        self.assertEqual(lease_loss_store.feature_enqueue_calls, 0)
        self.assertEqual(lease_loss_store.feature_supersede_calls, 0)
        self.assertEqual(store.list_formal_tasks(kinds=("formal_feature_build",)), [])
        self.assertNotEqual(store.get_formal_task(task_id)["status"], "verified")

    def test_statement_runtime_root_mismatch_fails_terminally_before_transport(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        forged_source_hash = "0" * 64
        forged_generation = derive_collection_refresh_generation(
            upstream_generation=payload.upstream_generation,
            registry_manifest_hash=manifest_hash,
            relevant_registry_hashes={
                "mapping": payload.mapping_registry_hash,
                "source": forged_source_hash,
            },
        )
        forged_payload = replace(
            payload,
            source_registry_hash=forged_source_hash,
            relevant_registry_hashes=(
                ("mapping", payload.mapping_registry_hash),
                ("source", forged_source_hash),
            ),
            refresh_generation=forged_generation,
        )
        spec = FormalTaskSpec.from_payload(forged_payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        try:
            summary = execute_queued_formal_work(
                dependencies, worker_id="invalid-root-worker", max_jobs=1
            )
        except ValueError:
            summary = None

        self.assertIsNotNone(
            summary,
            "runtime/root disagreement must become a terminal task result rather than escape the worker",
        )
        assert summary is not None
        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(transport.requests, [])
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "terminal_failed")
        self.assertEqual(task["error"]["code"], "statement_validation_failed")

    def test_statement_stale_refresh_generation_fails_before_receipt_or_transport(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        stale_payload = replace(payload, refresh_generation="f" * 64)
        spec = FormalTaskSpec.from_payload(stale_payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="stale-generation-worker", max_jobs=1
        )

        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(transport.requests, [])
        self.assertIsNone(store.get_formal_task_snapshot_receipt(task_id))
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "terminal_failed")
        self.assertEqual(task["error"]["code"], "statement_validation_failed")

    def test_date_only_statement_uses_canonical_task_freeze_and_rejects_binding_mismatch(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            manifest_hash,
            payload,
            context_repository,
        ) = date_only_statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=context_repository,
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="date-only-worker", max_jobs=1
        )

        self.assertEqual(summary.verified_statement_count, 1)
        self.assertEqual(summary.remote_attempts, 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(store.get_formal_task(task_id)["status"], "verified")
        self.assertEqual(len(context_repository.calls), 1)
        runtime = runtime_loader.load(manifest_hash)
        request = OfficialRequest("cninfo", "profit_sheet", "SZ000001", "2025-12-31", "SZ")
        config = runtime.source_adapter.registry.select(request)
        bad_binding = replace(payload.calendar_binding, manifest_sha256="e" * 64)
        bad_payload = replace(
            payload,
            calendar_binding=bad_binding,
            refresh_generation=derive_collection_refresh_generation(
                upstream_generation=payload.upstream_generation,
                registry_manifest_hash=manifest_hash,
                relevant_registry_hashes={
                    "mapping": payload.mapping_registry_hash,
                    "source": payload.source_registry_hash,
                },
                calendar_selector=config.calendar_selector,
                calendar_binding=bad_binding,
            ),
        )
        bad_spec = FormalTaskSpec.from_payload(bad_payload)
        bad_task_id = store.enqueue_formal_task(
            bad_spec.kind,
            bad_spec.idempotency_key,
            bad_spec.refresh_generation,
            bad_spec.payload,
            bad_spec.prerequisite_task_ids,
        )

        mismatch_summary = execute_queued_formal_work(
            dependencies, worker_id="date-only-mismatch-worker", max_jobs=1
        )

        self.assertEqual(mismatch_summary.terminal_failed, 1)
        self.assertEqual(len(transport.requests), 1)
        bad_task = store.get_formal_task(bad_task_id)
        self.assertEqual(bad_task["status"], "terminal_failed")
        self.assertEqual(bad_task["error"]["code"], "statement_validation_failed")

    def test_date_only_statement_receipt_replay_uses_the_same_canonical_freeze(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            manifest_hash,
            payload,
            context_repository,
        ) = date_only_statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        self.assertIsNotNone(
            store.lease_next_formal_task(("formal_statement",), "crashed-owner", 120)
        )
        runtime = runtime_loader.load(
            manifest_hash, adapter_freeze_at_utc=payload.as_of_utc
        )
        fetch, verification, _ = runtime.source_adapter.fetch_verified(
            OfficialRequest("cninfo", "profit_sheet", "SZ000001", "2025-12-31", "SZ"),
            refresh_generation=payload.refresh_generation,
            calendar_binding=payload.calendar_binding,
        )
        snapshots.persist_verified(
            fetch,
            verification,
            producing_task_id=task_id,
            worker_id="crashed-owner",
        )
        store.fail_formal_task(
            task_id,
            "crashed-owner",
            {"code": "simulated_crash"},
            "retryable_failed",
            datetime.now(timezone.utc).isoformat(),
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=context_repository,
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="date-only-recovery-worker", max_jobs=1
        )

        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(summary.verified_statement_count, 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(store.get_formal_task(task_id)["status"], "verified")
        self.assertEqual(len(store.list_formal_financial_facts(security_id="SZ000001")), 1)

    def test_statement_success_rebuilds_only_its_own_security(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            _transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        foreign_payload = replace(payload, security_id="SZ000002")
        foreign_spec = FormalTaskSpec.from_payload(foreign_payload)
        foreign_task_id = store.enqueue_formal_task(
            foreign_spec.kind,
            foreign_spec.idempotency_key,
            foreign_spec.refresh_generation,
            foreign_spec.payload,
            foreign_spec.prerequisite_task_ids,
        )
        self.assertEqual(
            store.lease_next_formal_task(("formal_statement",), "other-worker", 120)["id"],
            foreign_task_id,
        )
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="source-worker", max_jobs=1
        )

        self.assertEqual(summary.rebuilt_security_ids, ("SZ000001",))
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000002"), ())
        self.assertEqual(store.get_formal_task(foreign_task_id)["status"], "leased")
        feature_tasks = store.list_formal_tasks(kinds=("formal_feature_build",))
        self.assertEqual(
            tuple(task["payload"]["security_id"] for task in feature_tasks),
            ("SZ000001",),
        )

    def test_changed_statement_generation_supersedes_only_unfinished_feature_generation(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        first_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            first_spec.kind,
            first_spec.idempotency_key,
            first_spec.refresh_generation,
            first_spec.payload,
            first_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(dependencies, worker_id="first-worker", max_jobs=1)
        first_feature = store.list_formal_tasks(kinds=("formal_feature_build",))[0]
        self.assertEqual(first_feature["status"], "pending")

        transport.response = _formal_source_tests.response(
            raw=b'{"statement":"corrected"}',
            captured_at_utc="2026-09-04T01:00:00+00:00",
        )
        next_generation = derive_collection_refresh_generation(
            upstream_generation="statement-upstream-v2",
            registry_manifest_hash=manifest_hash,
            relevant_registry_hashes={
                "mapping": payload.mapping_registry_hash,
                "source": payload.source_registry_hash,
            },
        )
        corrected_payload = replace(
            payload,
            upstream_generation="statement-upstream-v2",
            refresh_generation=next_generation,
        )
        corrected_spec = FormalTaskSpec.from_payload(corrected_payload)
        store.enqueue_formal_task(
            corrected_spec.kind,
            corrected_spec.idempotency_key,
            corrected_spec.refresh_generation,
            corrected_spec.payload,
            corrected_spec.prerequisite_task_ids,
        )

        execute_queued_formal_work(dependencies, worker_id="second-worker", max_jobs=1)

        feature_tasks = store.list_formal_tasks(kinds=("formal_feature_build",))
        self.assertEqual(len(feature_tasks), 2)
        by_id = {task["id"]: task for task in feature_tasks}
        self.assertEqual(by_id[first_feature["id"]]["status"], "superseded")
        self.assertEqual(
            [task["status"] for task in feature_tasks if task["id"] != first_feature["id"]],
            ["pending"],
        )

    def test_history_gate_rekeys_legacy_feature_input_and_preserves_verified_history(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            _transport,
            _parser,
            manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(dependencies, worker_id="legacy-source-worker", max_jobs=1)
        facts = store.list_formal_financial_facts(security_id="SZ000001")
        legacy_generation, snapshot_ids = legacy_feature_refresh_generation(facts, manifest_hash)
        post_d1_task = store.list_formal_tasks(kinds=("formal_feature_build",))[0]
        legacy_verified_payload = FormalFeatureBuildTaskPayload(
            security_id="SZ000001",
            as_of_utc=AS_OF,
            template_id="general_nonfinancial",
            source_registry_hash=post_d1_task["payload"]["source_registry_hash"],
            mapping_registry_hash=post_d1_task["payload"]["mapping_registry_hash"],
            feature_registry_hash=post_d1_task["payload"]["feature_registry_hash"],
            registry_manifest_hash=manifest_hash,
            source_snapshot_ids=snapshot_ids,
            refresh_generation=legacy_generation,
        )
        legacy_verified_spec = FormalTaskSpec.from_payload(legacy_verified_payload)
        self.assertNotEqual(post_d1_task["refresh_generation"], legacy_generation)
        self.assertNotEqual(post_d1_task["idempotency_key"], legacy_verified_spec.idempotency_key)
        leased = store.lease_next_formal_task(
            ("formal_feature_build",), "post-d1-feature-worker", 120
        )
        self.assertEqual(leased["id"], post_d1_task["id"])
        store.complete_formal_task(
            post_d1_task["id"], "post-d1-feature-worker", {"outcome": "post-d1"}
        )
        legacy_verified_id = store.enqueue_formal_task(
            legacy_verified_spec.kind,
            legacy_verified_spec.idempotency_key,
            legacy_verified_spec.refresh_generation,
            legacy_verified_spec.payload,
            legacy_verified_spec.prerequisite_task_ids,
        )
        leased = store.lease_next_formal_task(
            ("formal_feature_build",), "legacy-feature-worker", 120
        )
        self.assertEqual(leased["id"], legacy_verified_id)
        store.complete_formal_task(
            legacy_verified_id, "legacy-feature-worker", {"outcome": "legacy"}
        )

        legacy_retry_payload = replace(
            legacy_verified_payload,
            source_snapshot_ids=("legacy-retry-snapshot",),
            refresh_generation=hashlib.sha256(b"legacy-retry-input").hexdigest(),
        )
        legacy_retry_spec = FormalTaskSpec.from_payload(legacy_retry_payload)
        legacy_retry_id = store.enqueue_formal_task(
            legacy_retry_spec.kind,
            legacy_retry_spec.idempotency_key,
            legacy_retry_spec.refresh_generation,
            legacy_retry_spec.payload,
            legacy_retry_spec.prerequisite_task_ids,
        )
        leased = store.lease_next_formal_task(
            ("formal_feature_build",), "legacy-retry-worker", 120
        )
        self.assertEqual(leased["id"], legacy_retry_id)
        store.fail_formal_task(
            legacy_retry_id,
            "legacy-retry-worker",
            {"code": "legacy_retry"},
            "retryable_failed",
            "2026-09-01T00:00:00+00:00",
        )

        legacy_pending_payload = replace(
            legacy_verified_payload,
            source_snapshot_ids=("legacy-other-snapshot",),
            refresh_generation=hashlib.sha256(b"legacy-other-input").hexdigest(),
        )
        legacy_pending_spec = FormalTaskSpec.from_payload(legacy_pending_payload)
        legacy_pending_id = store.enqueue_formal_task(
            legacy_pending_spec.kind,
            legacy_pending_spec.idempotency_key,
            legacy_pending_spec.refresh_generation,
            legacy_pending_spec.payload,
            legacy_pending_spec.prerequisite_task_ids,
        )
        different_template = replace(legacy_pending_payload, template_id="bank")
        different_template_spec = FormalTaskSpec.from_payload(different_template)
        different_template_id = store.enqueue_formal_task(
            different_template_spec.kind,
            different_template_spec.idempotency_key,
            different_template_spec.refresh_generation,
            different_template_spec.payload,
            different_template_spec.prerequisite_task_ids,
        )
        different_security = replace(legacy_pending_payload, security_id="SZ000002")
        different_security_spec = FormalTaskSpec.from_payload(different_security)
        different_security_id = store.enqueue_formal_task(
            different_security_spec.kind,
            different_security_spec.idempotency_key,
            different_security_spec.refresh_generation,
            different_security_spec.payload,
            different_security_spec.prerequisite_task_ids,
        )
        different_as_of = replace(
            legacy_pending_payload, as_of_utc="2026-08-30T07:00:00+00:00"
        )
        different_as_of_spec = FormalTaskSpec.from_payload(different_as_of)
        different_as_of_id = store.enqueue_formal_task(
            different_as_of_spec.kind,
            different_as_of_spec.idempotency_key,
            different_as_of_spec.refresh_generation,
            different_as_of_spec.payload,
            different_as_of_spec.prerequisite_task_ids,
        )

        runtime = runtime_loader.load(manifest_hash)
        task_ids = enqueue_formal_feature_build(
            store,
            security_id="SZ000001",
            as_of_utc=AS_OF,
            runtime=runtime,
            facts=facts,
        )

        rebuilt = store.get_formal_task(task_ids[0])
        self.assertNotEqual(rebuilt["refresh_generation"], legacy_generation)
        self.assertNotEqual(rebuilt["idempotency_key"], legacy_verified_spec.idempotency_key)
        self.assertEqual(store.get_formal_task(legacy_verified_id)["status"], "verified")
        self.assertEqual(store.get_formal_task(legacy_pending_id)["status"], "superseded")
        self.assertEqual(store.get_formal_task(legacy_retry_id)["status"], "superseded")
        self.assertEqual(store.get_formal_task(different_template_id)["status"], "pending")
        self.assertEqual(store.get_formal_task(different_security_id)["status"], "pending")
        self.assertEqual(store.get_formal_task(different_as_of_id)["status"], "pending")

    def test_feature_reconstruction_builds_only_frozen_raw_input_without_transport_or_publication(self) -> None:
        """Removing frozen raw replay would otherwise let current V6 facts become bundle input."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(dependencies, worker_id="source-worker", max_jobs=1)
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        transport_count = len(transport.requests)

        rebuild = getattr(_formal_deep_worker, "reconstruct_formal_feature_bundle", None)
        self.assertTrue(
            callable(rebuild),
            "D3 must expose a pure frozen feature reconstruction helper",
        )
        bundle = rebuild(dependencies, leased_feature)

        self.assertEqual(bundle.security_id, "SZ000001")
        self.assertEqual(bundle.as_of_utc, AS_OF)
        self.assertEqual(bundle.template_id, "general_nonfinancial")
        self.assertTrue(bundle.blockers)
        self.assertTrue(all(value.status == "blocked" for value in bundle.values))
        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_rejects_changed_source_calendar_binding_without_transport(self) -> None:
        """Using the feature cutoff instead of the source binding would admit this replay."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _manifest_hash,
            payload,
            calendar_repository,
        ) = date_only_statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=calendar_repository,
        )
        execute_queued_formal_work(dependencies, worker_id="date-source-worker", max_jobs=1)
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "date-feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        calendar_repository.binding = replace(
            calendar_repository.binding, manifest_sha256="e" * 64
        )
        transport_count = len(transport.requests)

        with self.assertRaisesRegex(ValueError, "calendar binding"):
            _formal_deep_worker.reconstruct_formal_feature_bundle(
                dependencies, leased_feature
            )

        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_fails_closed_when_standard_date_only_raw_reader_loses_binding(self) -> None:
        """A private historical-read bypass must not be needed to reject changed raw evidence."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _manifest_hash,
            payload,
            calendar_repository,
        ) = date_only_statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=calendar_repository,
        )
        execute_queued_formal_work(dependencies, worker_id="date-source-worker", max_jobs=1)
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "date-feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        snapshots._raw_store._calendar_binding_resolver = lambda _request: replace(
            payload.calendar_binding, manifest_sha256="e" * 64
        )
        transport_count = len(transport.requests)

        with self.assertRaisesRegex(ValueError, "calendar.*manifest"):
            _formal_deep_worker.reconstruct_formal_feature_bundle(
                dependencies, leased_feature
            )

        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_reports_unverified_source_as_temporary_hold(self) -> None:
        """Turning an in-flight statement into a terminal feature failure would lose work."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        ready_dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(ready_dependencies, worker_id="source-worker", max_jobs=1)
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        source_task_id = store.list_formal_financial_facts(
            security_id="SZ000001"
        )[0].source_producing_task_id
        self.assertIsInstance(source_task_id, str)
        assert isinstance(source_task_id, str)
        waiting_dependencies = FormalWorkerDependencies(
            store=TemporarilyUnverifiedSourceStore(store, source_task_id),
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        pending_type = getattr(_formal_deep_worker, "FeatureSourcePending", None)
        self.assertTrue(
            isinstance(pending_type, type) and issubclass(pending_type, ValueError),
            "D3 must distinguish a source task that D4 should hold and retry",
        )
        transport_count = len(transport.requests)

        with self.assertRaises(pending_type):
            _formal_deep_worker.reconstruct_formal_feature_bundle(
                waiting_dependencies, leased_feature
            )

        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_requires_a_source_statement_audit_link(self) -> None:
        """An orphan equivalent payload must not bypass the statement→feature audit trail."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        ready_dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(ready_dependencies, worker_id="source-worker", max_jobs=1)
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        source_task_id = store.list_formal_financial_facts(
            security_id="SZ000001"
        )[0].source_producing_task_id
        self.assertIsInstance(source_task_id, str)
        assert isinstance(source_task_id, str)
        orphan_dependencies = FormalWorkerDependencies(
            store=OrphanFeatureResultStore(store, source_task_id),
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        transport_count = len(transport.requests)

        with self.assertRaisesRegex(ValueError, "audit link"):
            _formal_deep_worker.reconstruct_formal_feature_bundle(
                orphan_dependencies, leased_feature
            )

        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_keeps_nonofficial_registry_as_blocked_bundle(self) -> None:
        """D3 replay verifies signed test evidence without treating it as release eligible."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            manifest_hash,
            payload,
        ) = statement_execution_fixture(self, registry_purpose="test")
        source_spec = FormalTaskSpec.from_payload(payload)
        source_task_id = store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        leased_source = store.lease_next_formal_task(
            ("formal_statement",), "nonofficial-source-worker", 120
        )
        self.assertIsNotNone(leased_source)
        runtime = runtime_loader.load(manifest_hash)
        request = OfficialRequest(
            "cninfo", "profit_sheet", "SZ000001", "2025-12-31", "SZ"
        )
        fetch, verification, _document = runtime.source_adapter.fetch_verified(
            request,
            refresh_generation=payload.refresh_generation,
            calendar_binding=None,
        )
        snapshot = snapshots.persist_verified(
            fetch,
            verification,
            producing_task_id=source_task_id,
            worker_id="nonofficial-source-worker",
        )
        document = runtime.source_adapter.parse_verified_snapshot(
            snapshot,
            snapshots.read_verified_raw(snapshot),
            calendar_binding=None,
        )
        extraction = extract_formal_financial_facts(
            document,
            snapshot,
            runtime.mapping_registry,
            snapshot.captured_at_utc,
        )
        store.insert_formal_financial_facts(extraction.facts)
        feature_task_ids = enqueue_formal_feature_build(
            store,
            security_id=payload.security_id,
            as_of_utc=payload.as_of_utc,
            runtime=runtime,
            facts=store.list_formal_financial_facts(security_id=payload.security_id),
        )
        store.complete_formal_task(
            source_task_id,
            "nonofficial-source-worker",
            {
                "fact_ids": [fact.id for fact in extraction.facts],
                "feature_task_ids": list(feature_task_ids),
                "kind": "formal_statement",
                "manifest_sha256": snapshot.manifest_sha256,
                "refresh_generation": payload.refresh_generation,
                "registry_manifest_hash": payload.registry_manifest_hash,
                "security_id": payload.security_id,
                "snapshot_id": snapshot.snapshot_id,
            },
        )
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "nonofficial-feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        transport_count = len(transport.requests)

        bundle = _formal_deep_worker.reconstruct_formal_feature_bundle(
            dependencies, leased_feature
        )

        self.assertIn("feature_registry_not_release_eligible", bundle.blockers)
        self.assertTrue(bundle.values)
        self.assertTrue(all(value.status == "blocked" for value in bundle.values))
        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_rejects_complete_v6_fact_set_drift_before_build(self) -> None:
        """Comparing only selected IDs would silently accept an extra fact in a frozen snapshot."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(dependencies, worker_id="source-worker", max_jobs=1)
        original_fact = store.list_formal_financial_facts(security_id="SZ000001")[0]
        extra_wire = original_fact.to_dict()
        extra_wire.pop("id")
        extra_wire["metric_key"] = "unreplayed_extra_metric"
        store.insert_formal_financial_facts((FormalFinancialFact.create(**extra_wire),))
        runtime = runtime_loader.load(manifest_hash)
        enqueue_formal_feature_build(
            store,
            security_id="SZ000001",
            as_of_utc=AS_OF,
            runtime=runtime,
            facts=store.list_formal_financial_facts(security_id="SZ000001"),
        )
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        transport_count = len(transport.requests)

        with self.assertRaisesRegex(ValueError, "facts do not match V6"):
            _formal_deep_worker.reconstruct_formal_feature_bundle(
                dependencies, leased_feature
            )

        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_rejects_old_generation_before_raw_replay(self) -> None:
        """Reusing a pre-D1-generation task would bypass the frozen history semantics."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(dependencies, worker_id="source-worker", max_jobs=1)
        current_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "current-feature-worker", 120
        )
        self.assertIsNotNone(current_feature)
        assert current_feature is not None
        current_wire = current_feature["payload"]
        stale_payload = FormalFeatureBuildTaskPayload(
            security_id=current_wire["security_id"],
            as_of_utc=current_wire["as_of_utc"],
            template_id=current_wire["template_id"],
            source_registry_hash=current_wire["source_registry_hash"],
            mapping_registry_hash=current_wire["mapping_registry_hash"],
            feature_registry_hash=current_wire["feature_registry_hash"],
            registry_manifest_hash=current_wire["registry_manifest_hash"],
            source_snapshot_ids=tuple(current_wire["source_snapshot_ids"]),
            refresh_generation="0" * 64,
        )
        stale_spec = FormalTaskSpec.from_payload(stale_payload)
        store.enqueue_formal_task(
            stale_spec.kind,
            stale_spec.idempotency_key,
            stale_spec.refresh_generation,
            stale_spec.payload,
            stale_spec.prerequisite_task_ids,
        )
        leased_stale = store.lease_next_formal_task(
            ("formal_feature_build",), "stale-feature-worker", 120
        )
        self.assertIsNotNone(leased_stale)
        assert leased_stale is not None
        transport_count = len(transport.requests)
        parse_count = len(parser.calls)

        with self.assertRaisesRegex(ValueError, "generation no longer matches V6"):
            _formal_deep_worker.reconstruct_formal_feature_bundle(
                dependencies, leased_stale
            )

        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(len(parser.calls), parse_count)
        self.assertEqual(store.get_formal_task(leased_stale["id"])["status"], "leased")

    def test_feature_reconstruction_rejects_parser_fact_drift_before_build(self) -> None:
        """Accepting a changed parser document would make verified raw bytes insufficient evidence."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(dependencies, worker_id="source-worker", max_jobs=1)
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        parser.document = _formal_source_tests.timestamp_document(
            declared_security_id="SZ000001",
            declared_period="2025-12-31",
            accounting_basis="consolidated",
            rows=({"ITEM": "OPERATING_PROFIT", "VALUE": 101},),
        )
        transport_count = len(transport.requests)

        with self.assertRaisesRegex(ValueError, "facts do not match V6"):
            _formal_deep_worker.reconstruct_formal_feature_bundle(
                dependencies, leased_feature
            )

        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_rejects_raw_byte_drift_before_parser_build(self) -> None:
        """Calling a parser on bytes that no longer hash to the frozen snapshot is unsafe."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        ready_dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(ready_dependencies, worker_id="source-worker", max_jobs=1)
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        drift_dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=RawBytesDriftSnapshots(snapshots),
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        transport_count = len(transport.requests)

        with self.assertRaisesRegex(FormalTerminalSourceError, "SHA-256"):
            _formal_deep_worker.reconstruct_formal_feature_bundle(
                drift_dependencies, leased_feature
            )

        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_passes_replayed_issues_to_the_builder(self) -> None:
        """Replacing reconstruction issues with an empty tuple would turn unsafe input into a clean bundle."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(
            self,
            document_rows=(
                {"ITEM": "OPERATING_PROFIT", "VALUE": 100},
                {"ITEM": "UNKNOWN_LINE", "VALUE": 7},
            ),
        )
        source_spec = FormalTaskSpec.from_payload(payload)
        store.enqueue_formal_task(
            source_spec.kind,
            source_spec.idempotency_key,
            source_spec.refresh_generation,
            source_spec.payload,
            source_spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        execute_queued_formal_work(dependencies, worker_id="source-worker", max_jobs=1)
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        transport_count = len(transport.requests)

        bundle = _formal_deep_worker.reconstruct_formal_feature_bundle(
            dependencies, leased_feature
        )

        self.assertIn("formal_fact_issue_unknown_source_field", bundle.blockers)
        self.assertTrue(all(value.status == "blocked" for value in bundle.values))
        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_feature_reconstruction_derives_from_four_fy_and_eight_quarters(self) -> None:
        """Dropping the D1 history gate or a frozen statement would incorrectly change this result."""

        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payloads,
        ) = history_ready_feature_execution_fixture(self)
        for payload in payloads:
            spec = FormalTaskSpec.from_payload(payload)
            store.enqueue_formal_task(
                spec.kind,
                spec.idempotency_key,
                spec.refresh_generation,
                spec.payload,
                spec.prerequisite_task_ids,
            )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )
        summary = execute_queued_formal_work(
            dependencies, worker_id="history-source-worker", max_jobs=len(payloads)
        )
        self.assertEqual(summary.verified_statement_count, len(payloads))
        leased_feature = store.lease_next_formal_task(
            ("formal_feature_build",), "history-feature-worker", 120
        )
        self.assertIsNotNone(leased_feature)
        assert leased_feature is not None
        transport_count = len(transport.requests)

        bundle = _formal_deep_worker.reconstruct_formal_feature_bundle(
            dependencies, leased_feature
        )

        self.assertEqual(bundle.history_endpoints, (
            "2022-12-31",
            "2023-12-31",
            "2024-12-31",
            "2025-12-31",
        ))
        self.assertEqual(bundle.comparable_quarter_keys[:2], ("2024Q1", "2024Q2"))
        self.assertEqual(bundle.comparable_quarter_keys[-8:], (
            "2024Q3",
            "2024Q4",
            "2025Q1",
            "2025Q2",
            "2025Q3",
            "2025Q4",
            "2026Q1",
            "2026Q2",
        ))
        self.assertEqual(bundle.values[0].status, "derived")
        self.assertEqual(bundle.values[0].value, 130.0)
        self.assertEqual(len(transport.requests), transport_count)
        self.assertEqual(store.get_formal_task(leased_feature["id"])["status"], "leased")

    def test_statement_source_block_opens_signed_circuit_and_retries_without_fact_write(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(
            self,
            transport_error=FormalSourceBlocked("fixture challenge"),
        )
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        try:
            summary = execute_queued_formal_work(
                dependencies, worker_id="blocked-source-worker", max_jobs=1
            )
        except FormalSourceBlocked:
            summary = None

        self.assertIsNotNone(
            summary,
            "a blocked signed source must become a retryable task and circuit state",
        )
        assert summary is not None
        self.assertEqual(summary.retryable_failed, 1)
        self.assertEqual(summary.open_circuits, ("cninfo",))
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000001"), ())
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "retryable_failed")
        self.assertEqual(task["error"]["code"], "source_blocked")
        circuit = store.get_formal_source_circuit("cninfo")
        self.assertEqual(circuit["state"], "open")
        self.assertEqual(circuit["failure_count"], 1)

    def test_statement_retryable_source_error_uses_signed_delay_without_opening_circuit(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(
            self,
            transport_error=FormalRetryableSourceError("fixture timeout"),
        )
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="retryable-source-worker", max_jobs=1
        )

        self.assertEqual(summary.retryable_failed, 1)
        self.assertEqual(summary.open_circuits, ())
        self.assertEqual(len(transport.requests), 1)
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "retryable_failed")
        self.assertEqual(task["error"]["code"], "source_retryable_failed")
        self.assertIsNone(store.get_formal_source_circuit("cninfo"))

    def test_statement_open_circuit_retries_without_transport(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        opened_at = datetime.now(timezone.utc)
        store.set_formal_source_circuit(
            "cninfo",
            state="open",
            failure_count=1,
            reason={"code": "prior_challenge"},
            opened_at_utc=opened_at.isoformat(),
            retry_after_utc=(opened_at.replace(microsecond=0) + timedelta(minutes=5)).isoformat(),
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="open-circuit-worker", max_jobs=1
        )

        self.assertEqual(summary.retryable_failed, 1)
        self.assertEqual(summary.open_circuits, ("cninfo",))
        self.assertEqual(transport.requests, [])
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "retryable_failed")
        self.assertEqual(task["error"]["code"], "source_circuit_open")

    def test_statement_terminal_replay_error_retains_receipt_and_terminalizes(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            parser,
            manifest_hash,
            payload,
        ) = statement_execution_fixture(self)
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        leased = store.lease_next_formal_task(
            ("formal_statement",), "crashed-owner", 120
        )
        self.assertIsNotNone(leased)
        runtime = runtime_loader.load(manifest_hash)
        fetch, verification, _ = runtime.source_adapter.fetch_verified(
            OfficialRequest("cninfo", "profit_sheet", "SZ000001", "2025-12-31", "SZ"),
            refresh_generation=payload.refresh_generation,
            calendar_binding=None,
        )
        snapshots.persist_verified(
            fetch,
            verification,
            producing_task_id=task_id,
            worker_id="crashed-owner",
        )
        store.fail_formal_task(
            task_id,
            "crashed-owner",
            {"code": "simulated_crash"},
            "retryable_failed",
            datetime.now(timezone.utc).isoformat(),
        )
        parser.document = replace(parser.document, declared_security_id="SZ000002")
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        try:
            summary = execute_queued_formal_work(
                dependencies, worker_id="terminal-replay-worker", max_jobs=1
            )
        except FormalTerminalSourceError:
            summary = None

        self.assertIsNotNone(
            summary,
            "a terminal reparse error must retain its receipt and terminalize the leased task",
        )
        assert summary is not None
        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNotNone(store.get_formal_task_snapshot_receipt(task_id))
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "terminal_failed")
        self.assertEqual(task["error"]["code"], "statement_terminal_source_error")

    def test_statement_terminal_reparse_after_fetch_retains_remote_attempt_count(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(
            self,
            replay_parse_error=FormalTerminalSourceError("fixture replay parse failure"),
        )
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="terminal-attempt-worker", max_jobs=1
        )

        self.assertEqual(summary.remote_attempts, 1)
        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNotNone(store.get_formal_task_snapshot_receipt(task_id))
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000001"), ())
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "terminal_failed")
        self.assertEqual(task["error"]["code"], "statement_terminal_source_error")

    def test_statement_initial_terminal_parser_error_counts_actual_transport_attempt(self) -> None:
        (
            store,
            snapshots,
            runtime_loader,
            transport,
            _parser,
            _manifest_hash,
            payload,
        ) = statement_execution_fixture(
            self,
            initial_parse_error=FormalTerminalSourceError("fixture initial parser failure"),
        )
        spec = FormalTaskSpec.from_payload(payload)
        task_id = store.enqueue_formal_task(
            spec.kind,
            spec.idempotency_key,
            spec.refresh_generation,
            spec.payload,
            spec.prerequisite_task_ids,
        )
        dependencies = FormalWorkerDependencies(
            store=store,
            snapshots=snapshots,
            registry_runtime_loader=runtime_loader,
            feature_store=object(),
            context_repository=object(),
        )

        summary = execute_queued_formal_work(
            dependencies, worker_id="initial-terminal-attempt-worker", max_jobs=1
        )

        self.assertEqual(summary.remote_attempts, 1)
        self.assertEqual(summary.terminal_failed, 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNone(store.get_formal_task_snapshot_receipt(task_id))
        self.assertEqual(store.list_formal_financial_facts(security_id="SZ000001"), ())
        task = store.get_formal_task(task_id)
        self.assertEqual(task["status"], "terminal_failed")
        self.assertEqual(task["error"]["code"], "statement_terminal_source_error")

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
