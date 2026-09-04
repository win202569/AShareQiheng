# Formal V3 Financial Feature Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build the isolated Formal V3 official-source, financial-fact, comparable-quarter, feature-bundle, and resumable-collection pipeline that supplies auditable point-in-time inputs to the formal scorer.

**Architecture:** This plan consumes the Formal V3 evidence/universe foundation's verified raw snapshots, 15:00 cutoff functions, and V5 formal task table; it never converts legacy FetchBatch, FinancialFact, FeatureBundle, source_snapshot, or job rows into formal evidence. A signed source/mapping/feature registry and injected transport drive all official collection and derivation, while V6 adds immutable formal facts, quarters, features, and source-circuit state. The pipeline persists an original verified snapshot before parsing it, recomputes only the affected security after a changed snapshot, and returns explicit pending-evidence reasons instead of manufacturing values.

**Tech Stack:** Python 3.12, Python standard library, SQLite, unittest, the Formal V3 foundation modules, and dependency-injected test transports.

**Spec:** docs/superpowers/specs/2026-09-04-formal-scoring-release-contract-design.md

## Global Constraints

- Execute this plan only after the Formal V3 Evidence and Universe Foundation plan has supplied schema V5, OfficialFetch, OfficialSnapshotRef, FormalSnapshotRepository, formal_time, formal_universe, and formal_collection_task.
- Freeze time is exactly 2026-08-31T15:00:00+08:00; every formal selector receives an explicit as_of_utc and must use formal_time rather than legacy 23:59:59 logic.
- Formal identities are SH, SZ, or BJ plus six digits. A legacy SH/SZ-only type or ID validator must not be reused for Formal V3 facts or bundles.
- An official raw response is persisted through FormalSnapshotRepository.persist_verified before its parsed facts are written; third-party FetchBatch and legacy source_snapshot can never satisfy this requirement.
- Production source URLs, request shapes, document parsers, raw-field maps, template equivalences, redlines, cyclic industries, and metric definitions are not supplied by the approved contract. Code must accept only a verified, signed registry supplied by its caller and fail closed when it is absent, invalid, or incomplete.
- Do not introduce a production default endpoint, a production default raw-field map, a fallback industry template, or a missing-value imputation rule.
- Duration quarters are Q1 = Q1 cumulative, Q2 = H1 cumulative minus Q1 cumulative, Q3 = Q3 cumulative minus H1 cumulative, and Q4 = FY cumulative minus Q3 cumulative. Instant facts use the quarter-end point directly.
- Duration subtraction requires the same security, accounting basis, unit, mapping version, and selected version lineage. A broken prerequisite produces a pending-evidence reason, not a partial arithmetic result.
- Formal raw snapshots, normalized facts, comparable quarters, and feature bundles are retained under data/; WAL/SHM and process progress files are not evidence. Do not stage data, SQLite, WAL/SHM, or data/status/pipeline_status.json in code commits.
- Unit tests are hermetic: fake transports, fake signature verifiers, and in-memory fixture bytes are required. Tests must not call the network or require AkShare/BaoStock.

---

## File Structure

| File | Responsibility |
|---|---|
| ashare_pipeline/formal_sources.py | Injected HTTP transport, signed official-source registry loading, document parsing boundary, and verified official fetch production |
| ashare_pipeline/formal_registry_manifest.py | Hash-pinned root manifest binding source, mapping, feature, scoring, industry, and policy registries |
| ashare_pipeline/formal_financial_schema.py | Formal-only statement mapping registry, fact identity, extraction result, and validation of source lineage |
| ashare_pipeline/formal_feature_contract.py | Signed feature registry, safe formula AST, formal evidence references, immutable feature values, and canonical feature bundle |
| ashare_pipeline/formal_feature_store.py | Content-addressed, atomic feature-bundle bytes and manifest storage |
| ashare_pipeline/formal_feature_repository.py | Typed V6 bundle lookup with database-to-file hash and manifest re-verification |
| ashare_pipeline/formal_financial_features.py | Point-in-time fact selection, comparable-quarter derivation, history checks, formula evaluation, and bundle construction |
| ashare_pipeline/formal_context_schema.py | Typed market, calendar, industry, regulatory, event, and consensus context facts with verified evidence lineage |
| ashare_pipeline/formal_context_repository.py | Verified context lookup for scoring, policy, source time resolution, and release validation |
| ashare_pipeline/formal_deep_worker.py | Formal task payloads, incremental enqueueing, leased collection execution, retries, source circuit behavior, and per-security rebuilds |
| ashare_pipeline/state_store.py | Additive V6 tables and APIs for formal facts, quarters, features, source circuits, and formal task ownership transitions |
| tests/test_formal_sources.py | Transport injection, raw-byte preservation, signed-registry, parser, and source-policy tests |
| tests/test_formal_registry_manifest.py | Root-manifest signature, hash-binding, approval-purpose, and cross-registry consistency tests |
| tests/test_formal_financial_schema.py | Fact identity, mapping, lineage, BJ identity, and fail-closed extraction tests |
| tests/test_formal_feature_contract.py | Signed registry, AST, evidence, canonical serialization, and bundle validation tests |
| tests/test_formal_feature_store.py | Bundle-byte round trip, manifest hash, idempotence, and atomic-write tests |
| tests/test_formal_feature_repository.py | Verified typed bundle lookup, stale row, and tampered-file rejection tests |
| tests/test_formal_financial_features.py | Visibility, revision choice, quarterly split, history, formula, and bundle-input tests |
| tests/test_formal_context_schema.py | Context identity, no-coverage, time, and source-evidence validation tests |
| tests/test_formal_context_repository.py | Exact frozen-context lookup and tamper/future-data rejection tests |
| tests/test_formal_deep_worker.py | Idempotency, leases, retries, circuit state, snapshot reuse, and affected-security rebuild tests |
| tests/test_state_store.py | V5-to-V6 migration, formal persistence, and formal task ownership tests |

## Execution Preconditions

The evidence/universe foundation plan is an implementation dependency, not a compatibility option. Its V5 migration must be present before V6 runs. The production registry files and their verifier are deliberately outside this plan because the approved V3 contract does not yet provide their endpoints, field mappings, thresholds, or signing authority; the implementation below turns that absence into a deterministic blocked or pending-evidence outcome.

### Task 1: Injected Official Source Adapter and Signed Registry Boundary

**Files:**
- Create: ashare_pipeline/formal_sources.py
- Create: ashare_pipeline/formal_registry_manifest.py
- Create: tests/test_formal_sources.py
- Create: tests/test_formal_registry_manifest.py

**Interfaces:**
- Consumes OfficialRequest, OfficialFetch, EvidenceVerification, VerifiedCalendarBinding, SourcePolicy, and verify_official_fetch from ashare_pipeline.formal_evidence.
- Produces FormalSourceError, FormalRetryableSourceError, FormalSourceBlocked, FormalTerminalSourceError, TransportRequest, TransportResponse, OfficialTransport, RegistrySignatureVerifier, EffectiveTimeResolver, CalendarSelector, SignedSourceRegistry, SourceAdapterConfig, ParsedOfficialDocument, OfficialDocumentParser, FormalOfficialSourceAdapter, FormalRegistryManifest, VerifiedRegistryBlob, VerifiedRegistryBundle, FormalRegistryBundleRepository, and FormalRegistryBundleLoader.
- FormalOfficialSourceAdapter.fetch_verified(request, *, refresh_generation, calendar_binding: VerifiedCalendarBinding | None) returns tuple[OfficialFetch, EvidenceVerification, ParsedOfficialDocument] only when the registry signature, parser identity, response URL, document identity, verified calendar binding when needed, and SourcePolicy verification all pass. FormalOfficialSourceAdapter.parse_verified_snapshot(snapshot_ref, raw_bytes, *, calendar_binding: VerifiedCalendarBinding | None) parses already hash-verified persisted bytes without transport only when the signed parser/source identity and date-only binding still match the snapshot. The supplied immutable generation is provenance from the leased formal task, not part of OfficialRequest identity.
- SignedSourceRegistry.from_signed_bytes(registry_bytes, signature, key_id, verifier) has no no-argument or production-default variant.
- FormalRegistryManifest binds exact source, financial-mapping, feature, scoring, industry, cyclic, redline, status, and event registry hashes into one signed, purpose-labelled canonical object. A test-purpose manifest is permitted for hermetic tests but cannot satisfy an official release gate.

- [ ] **Step 1: Write failing injected-source and registry-boundary tests**

~~~python
import unittest

from ashare_pipeline.formal_evidence import OfficialRequest, SourcePolicy
from ashare_pipeline.formal_sources import (
    FormalOfficialSourceAdapter,
    RegistrySignatureVerifier,
    SignedSourceRegistry,
    TransportResponse,
)


class AcceptingVerifier(RegistrySignatureVerifier):
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool:
        return signature == "fixture-signature" and key_id == "fixture-key"


class FakeTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return TransportResponse(
            status_code=200,
            original_url="https://www.cninfo.com.cn/fixture/annual.json",
            headers={"content-type": "application/json"},
            raw_bytes=self.body,
            captured_at_utc="2026-09-04T00:00:00+00:00",
        )


class FormalSourceTests(unittest.TestCase):
    def test_verified_fetch_preserves_transport_bytes_and_parser_identity(self):
        registry = SignedSourceRegistry.from_signed_bytes(
            fixture_registry_bytes(), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        raw = b'{"security_id":"BJ430001","period":"2025-12-31","published_at":"2026-03-20T08:00:00+00:00","rows":[]}'
        adapter = FormalOfficialSourceAdapter(
            transport=FakeTransport(raw),
            registry=registry,
            policies={"cninfo": SourcePolicy.cninfo()},
            parsers={"fixture-json-v1": FixtureDocumentParser()},
        )
        fetch, verification, document = adapter.fetch_verified(
            OfficialRequest("cninfo", "annual_report", "BJ430001", "2025-12-31"),
            refresh_generation="fixture-index-v1",
            calendar_binding=None,
        )
        self.assertEqual(fetch.raw_bytes, raw)
        self.assertEqual(fetch.parser_id, "fixture-json-v1")
        self.assertEqual(fetch.declared_security_id, "BJ430001")
        self.assertEqual(document.parser_id, "fixture-json-v1")
        self.assertEqual(verification.status, "verified")

    def test_unsigned_registry_or_missing_parser_fails_before_collection(self):
        with self.assertRaisesRegex(ValueError, "registry signature"):
            SignedSourceRegistry.from_signed_bytes(
                fixture_registry_bytes(), "wrong", "fixture-key", AcceptingVerifier()
            )
        registry = SignedSourceRegistry.from_signed_bytes(
            fixture_registry_bytes(), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        with self.assertRaisesRegex(ValueError, "parser is not registered"):
            FormalOfficialSourceAdapter(
                transport=FakeTransport(b"{}"),
                registry=registry,
                policies={"cninfo": SourcePolicy.cninfo()},
                parsers={},
            )
~~~

Add a date-only fixture whose parser emits only the disclosure date and precision. Inject a resolver returning the next verified exchange close, pass a VerifiedCalendarBinding from the fake context repository, and assert that the resulting OfficialFetch records that exact effective instant and binding manifest hash. Pass a second, independently verified but non-selected calendar manifest with the same exchange/freeze/root and assert it fails before the response can become verified or transport is called; omitting the binding must fail likewise.

In tests/test_formal_registry_manifest.py, define an InMemoryFormalRegistryBundleRepository fixture that returns exact stored envelopes. Add one test that mutates the stored root signature and one that mutates a child blob signature after construction; FormalRegistryBundleLoader.load must reject both. Add one test that changes the scoring child hash while retaining otherwise valid source/mapping/feature blobs; the bundle load must reject it before a source adapter, feature builder, or scorer can be constructed.

- [ ] **Step 2: Run the source tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_sources tests.test_formal_registry_manifest -v
~~~

Expected: FAIL because ashare_pipeline.formal_sources and ashare_pipeline.formal_registry_manifest do not exist.

- [ ] **Step 3: Implement the signed-registry, transport, and parser contracts**

~~~python
@dataclass(frozen=True)
class TransportRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout_seconds: float

@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    original_url: str
    headers: Mapping[str, str]
    raw_bytes: bytes
    captured_at_utc: str

class OfficialTransport(Protocol):
    def send(self, request: TransportRequest) -> TransportResponse: ...

class RegistrySignatureVerifier(Protocol):
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool: ...

class EffectiveTimeResolver(Protocol):
    def next_exchange_close(
        self, *, exchange: str, disclosure_date_cn: str,
        calendar_binding: VerifiedCalendarBinding,
    ) -> str: ...

@dataclass(frozen=True)
class CalendarSelector:
    context_kind: Literal["trading_calendar"]
    scope_key: str
    exchange: Literal["SH", "SZ", "BJ"]
    as_of_rule: Literal["visible_at_freeze"]

@dataclass(frozen=True)
class SourceAdapterConfig:
    source: str
    dataset: str
    endpoint_url: str
    http_method: Literal["GET", "POST"]
    parser_id: str
    parser_version: str
    mapping_version: str
    request_template: Mapping[str, object]
    timeout_seconds: float
    retry_base_seconds: float
    retry_max_attempts: int
    challenge_cooldown_seconds: float
    registry_hash: str
    exchange_scope: Literal["SH", "SZ", "BJ"] | None
    calendar_selector: CalendarSelector | None
    bootstrap_calendar: bool = False

@dataclass(frozen=True)
class ParsedOfficialDocument:
    parser_id: str
    declared_security_id: str | None
    declared_period: str | None
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    source_updated_at_utc: str | None
    rows: tuple[Mapping[str, object], ...]
    accounting_basis: str

class OfficialDocumentParser(Protocol):
    def parse(
        self, raw_bytes: bytes, *, request: OfficialRequest, config: "SourceAdapterConfig"
    ) -> ParsedOfficialDocument: ...
~~~

Parse registry bytes as canonical JSON and require a valid verifier result before constructing a SignedSourceRegistry. CalendarSelector and SourceAdapterConfig are signed canonical configuration rather than dynamic task metadata. exchange_scope is null only for a timestamp-only configuration or when every request supplies its own exchange; a date-only configuration must resolve exactly one exchange from OfficialRequest.exchange or its signed exchange_scope, and it rejects a disagreement between them. A task payload supplies a VerifiedCalendarBinding—not a bare calendar hash—constructed by the context repository from one verified calendar context/source snapshot. The adapter requires binding.manifest_sha256, exchange, freeze_at_utc, registry_manifest_hash, selector_hash, and prerequisite_task_id to exactly match the selected context, signed selector, task root/freeze, and prerequisite edge before transport; it then writes binding.manifest_sha256 to OfficialFetch.effective_time_evidence_hash. Reject an unknown source/dataset pair, an endpoint whose host is not allowed by that source's SourcePolicy, an empty endpoint, a non-HTTPS endpoint, a missing parser, a non-positive timeout, a non-positive retry interval, a non-positive retry limit, a non-positive challenge cooldown, an ambiguous date-only exchange, a missing binding for a date-only task, or a binding that does not resolve to the selector's exact verified calendar manifest.

A signed universe_listing configuration is a global request with security_id null and one non-null exchange_scope; the scheduler must create a separate request for each SH/SZ/BJ exchange. Its registered parser must emit an explicit security_id, security_type, and listing_status for every listing row and may not synthesize a member from a display name or code fragment. A configuration that returns an aggregate multi-exchange list, lacks an explicit type/status field, or cannot bind its parser ID/version to its stored result is terminally unusable for formal universe collection.

The only bootstrap exception is a signed configuration whose dataset is trading_calendar and whose bootstrap_calendar flag is true. It may omit calendar_selector and calendar_binding only when its parser returns an exact timestamp publication, never date_only; the adapter sets effective_at equal to that timestamp and records bootstrap_calendar=true in the snapshot metadata. A non-calendar configuration, or a date-only trading-calendar response, with no verified calendar binding is terminally invalid. Once the bootstrap calendar context is stored, the scheduling coordinator asks FormalContextRepository.resolve_verified_calendar_binding to resolve each signed selector to a specific verified calendar snapshot and writes that immutable binding into every downstream task payload; no post-bootstrap registry rewrite is needed. FormalOfficialSourceAdapter receives an EffectiveTimeResolver. A parser reports publication time/precision but does not decide effective time: the adapter preserves an exact publication timestamp when present, and for a date-only disclosure calls next_exchange_close using the one resolved request/config exchange and the full selector-validated calendar_binding. It passes the same binding to verify_official_fetch, which compares its manifest to OfficialFetch.effective_time_evidence_hash; a different otherwise-valid calendar manifest is rejected. A global context request with security_id null may be date-only only when the signed resolver emits a single exchange-scoped request; a multi-exchange global request must be split before collection. fetch_verified requires a nonempty refresh_generation passed verbatim by its leased task; it copies it together with the signed config.parser_id/config.parser_version into OfficialFetch but never adds it to OfficialRequest, URL construction, or source-document identity. For every parser result, declared_security_id and declared_period must exactly equal the corresponding OfficialRequest fields, including null: a global request accepts only a parser-declared null security identity, while a global period/date may be null or must match its explicit request value. Financial statement extraction then separately requires nonnull canonical security and period; global contexts are normalized only by the context path. parse_verified_snapshot receives raw bytes already re-read and verified by FormalSnapshotRepository plus the task's calendar_binding, requires the stored snapshot parser_id/parser_version to exactly equal the loaded signed config and ParsedOfficialDocument.parser_id, rechecks source/mapping identity, and for a date-only snapshot rechecks its effective_time_evidence_hash against the binding's manifest/root/exchange/selector/prerequisite through the effective-time resolver; timestamp snapshots require no binding. It makes no network call. It must build a TransportRequest only from the signed config and OfficialRequest, call the injected transport once, preserve TransportResponse.raw_bytes exactly in OfficialFetch, and verify the parser-reported security, period, publication time, adapter-resolved effective time, final URL, and calendar binding through verify_official_fetch. It maps HTTP 403/429 or a challenge-page marker to FormalSourceBlocked, HTTP 408/425/5xx and injected transport timeouts to FormalRetryableSourceError, and every other non-2xx response to FormalTerminalSourceError without parsing its body. It must not import requests, urllib networking, AKShare, BaoStock, or sources.FetchBatch.

Implement FormalRegistryManifest in its own module:

~~~python
@dataclass(frozen=True)
class FormalRegistryManifest:
    manifest_hash: str
    purpose: Literal["test", "official"]
    approval_id: str | None
    canonical_json: bytes
    signature: str
    key_id: str
    source_registry_hash: str
    mapping_registry_hash: str
    feature_registry_hash: str
    scoring_registry_hash: str
    industry_registry_hash: str
    cyclic_registry_hash: str
    redline_registry_hash: str
    status_registry_hash: str
    event_registry_hash: str

    def require_official(self) -> None: ...
    def assert_member_hashes(self, **hashes: str) -> None: ...
    @classmethod
    def from_signed_bytes(
        cls, canonical_json: bytes, signature: str, key_id: str,
        verifier: RegistrySignatureVerifier,
    ) -> "FormalRegistryManifest": ...

@dataclass(frozen=True)
class VerifiedRegistryBlob:
    registry_role: str
    registry_hash: str
    canonical_json: bytes
    signature: str
    key_id: str
    approval_id: str | None

@dataclass(frozen=True)
class VerifiedRegistryBundle:
    manifest: FormalRegistryManifest
    blobs: Mapping[str, VerifiedRegistryBlob]

    def require_official(self) -> None: ...
    def blob(self, role: str) -> VerifiedRegistryBlob: ...

class FormalRegistryBundleRepository(Protocol):
    def get_formal_registry_manifest(self, manifest_hash: str) -> FormalRegistryManifest | None: ...
    def get_formal_registry_blob(self, registry_hash: str) -> VerifiedRegistryBlob | None: ...

class FormalRegistryBundleLoader:
    def __init__(
        self, repository: FormalRegistryBundleRepository, verifier: RegistrySignatureVerifier
    ) -> None: ...

    def load(self, manifest_hash: str) -> VerifiedRegistryBundle: ...

~~~

The manifest hash is the SHA-256 of its canonical JSON and its signature/key_id signs that exact canonical JSON through the injected verifier; the signature is not folded into the content hash. Task 1 is deliberately a pure boundary: its test suite uses an InMemoryFormalRegistryBundleRepository and proves that the loader re-reads, signature-verifies, and re-hashes the exact canonical root and child bytes before matching every named root-manifest role. The production StateStore persistence implementation is added in Task 5 after its complete V6 migration; it satisfies FormalRegistryBundleRepository and makes a root visible only after every signed child blob is durable. FormalRegistryBundleLoader returns a VerifiedRegistryBundle only if all roles are present. The root rejects absent role hashes, duplicate role names, a test purpose in require_official, an invalid root signature, or a child registry hash/signature that differs from its repository blob or manifest declaration. Task 6 builds the typed runtime only after the mapping and feature registry types exist; it receives this loader and creates every runtime component only from matching bundle blobs. Add a test where a valid source/mapping/feature triple paired with a different scoring-registry hash fails before feature construction or scoring. Every V6 feature set carries manifest_hash, and V7/V8 must consume one loaded VerifiedRegistryBundle rather than independently combining registry files.

- [ ] **Step 4: Run focused source and evidence regression tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_sources tests.test_formal_registry_manifest tests.test_formal_evidence tests.test_sources -v
~~~

Expected: PASS; all fixture transport calls remain local and existing third-party source behavior is unchanged.

- [ ] **Step 5: Commit the source boundary**

~~~powershell
git add -- ashare_pipeline/formal_sources.py ashare_pipeline/formal_registry_manifest.py tests/test_formal_sources.py tests/test_formal_registry_manifest.py
git commit -m "feat: add injected formal official source adapter"
~~~

### Task 2: Formal Financial Fact Schema and Fail-Closed Extraction

**Files:**
- Create: ashare_pipeline/formal_financial_schema.py
- Create: tests/test_formal_financial_schema.py

**Interfaces:**
- Consumes ParsedOfficialDocument from Task 1, OfficialSnapshotRef from ashare_pipeline.formal_evidence, canonical_security_id from ashare_pipeline.formal_universe, and canonical JSON/hash helpers from ashare_pipeline.feature_contract only for serialization.
- Produces FormalFactMapping, SignedFinancialMappingRegistry, FormalFinancialFact, FormalFactIssue, FormalFactExtraction, and extract_formal_financial_facts(document, snapshot_ref, registry, created_at_utc).
- A FormalFinancialFact always references a formal_source_snapshot ID and source content SHA-256; it cannot be constructed from a legacy FinancialFact or source_snapshot row.

- [ ] **Step 1: Write failing formal-fact tests**

~~~python
import unittest

from ashare_pipeline.formal_financial_schema import (
    FormalFinancialFact,
    SignedFinancialMappingRegistry,
    extract_formal_financial_facts,
)


class FormalFinancialSchemaTests(unittest.TestCase):
    def test_extracts_bj_duration_fact_with_verified_snapshot_lineage(self):
        registry = signed_fixture_mapping_registry()
        extraction = extract_formal_financial_facts(
            fixture_document(
                security_id="BJ430001",
                period="2025-12-31",
                rows=({"ITEM": "OPERATING_PROFIT", "VALUE": "120.0"},),
            ),
            fixture_snapshot_ref(content_sha256="a" * 64),
            registry,
            "2026-09-04T00:00:00+00:00",
        )
        fact = extraction.facts[0]
        self.assertIsInstance(fact, FormalFinancialFact)
        self.assertEqual(fact.security_id, "BJ430001")
        self.assertEqual(fact.nature, "duration")
        self.assertEqual(fact.source_content_sha256, "a" * 64)
        self.assertEqual(fact.source_refresh_generation, "fixture-index-v1")
        self.assertEqual(fact.accounting_basis, "consolidated")

    def test_unknown_field_or_identity_mismatch_never_falls_back_to_legacy_mapping(self):
        extraction = extract_formal_financial_facts(
            fixture_document(rows=({"ITEM": "UNMAPPED", "VALUE": "1"},)),
            fixture_snapshot_ref(),
            signed_fixture_mapping_registry(),
            "2026-09-04T00:00:00+00:00",
        )
        self.assertEqual(extraction.facts, ())
        self.assertEqual(extraction.issues[0].code, "required_source_field_missing")
        with self.assertRaisesRegex(ValueError, "snapshot identity"):
            extract_formal_financial_facts(
                fixture_document(security_id="BJ430001"),
                fixture_snapshot_ref(security_id="SZ000001"),
                signed_fixture_mapping_registry(),
                "2026-09-04T00:00:00+00:00",
            )
~~~

- [ ] **Step 2: Run formal-fact tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v
~~~

Expected: FAIL because ashare_pipeline.formal_financial_schema does not exist.

- [ ] **Step 3: Implement formal mapping, fact identity, and extraction**

~~~python
@dataclass(frozen=True)
class FormalFactMapping:
    mapping_id: str
    statement: Literal["income", "balance", "cash_flow"]
    metric_key: str
    source_field: str
    unit: Literal["CNY", "shares", "ratio", "CNY_per_share"]
    nature: Literal["instant", "duration"]
    period_kind: Literal["FY", "H1", "Q1", "Q3", "OTHER"]
    accounting_basis: str

@dataclass(frozen=True)
class FormalFinancialFact:
    id: str
    security_id: str
    statement: str
    metric_key: str
    period_start: str | None
    period_end: str
    period_kind: str
    value: float
    unit: str
    nature: str
    accounting_basis: str
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    effective_at_utc: str
    effective_time_evidence_hash: str | None
    source_updated_at_utc: str | None
    captured_at_utc: str
    source_snapshot_id: str
    source_content_sha256: str
    source_refresh_generation: str
    source_producing_task_id: str | None
    source_field: str
    raw_value_sha256: str
    parser_id: str
    parser_version: str
    mapping_version: str
    created_at_utc: str

@dataclass(frozen=True)
class FormalFactExtraction:
    facts: tuple[FormalFinancialFact, ...]
    issues: tuple[FormalFactIssue, ...]
~~~

SignedFinancialMappingRegistry must be loaded through the Task 1 signature-verifier protocol and contain every mapping used in an extraction. FormalFinancialFact.create must normalize its SH/SZ/BJ identity, validate finite numeric values, canonical dates, timezone-aware times, published_precision, statement/nature compatibility, source content SHA-256, source snapshot ID, source_refresh_generation, optional source_producing_task_id, parser ID/version, non-empty accounting basis, and an identity hash over all scientific/evidence fields excluding created_at_utc. extract_formal_financial_facts requires nonnull canonical statement document/snapshot security and period before it copies refresh generation and producing-task linkage, requires the document and snapshot security/period/parser ID/version/source lineage to agree, resolves a raw field only through the signed mapping registry, uses the document's official published/effective time and precision, and emits sorted FormalFactIssue records for unrecognized, conflicting, nonnumeric, or missing required fields. It must not infer a source field from a nearby name, alter a period, use a third-party mapping, or change an issue into a numeric fact.

- [ ] **Step 4: Run formal-fact and legacy schema regression tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema tests.test_financial_schema tests.test_financial_features -v
~~~

Expected: PASS; legacy FinancialFact remains SH/SZ-only and retains its existing mapping version behavior.

- [ ] **Step 5: Commit the formal fact schema**

~~~powershell
git add -- ashare_pipeline/formal_financial_schema.py tests/test_formal_financial_schema.py
git commit -m "feat: add formal financial fact schema"
~~~

### Task 3: Signed Feature Contract and Immutable Feature Bundle Storage

**Files:**
- Create: ashare_pipeline/formal_feature_contract.py
- Create: ashare_pipeline/formal_feature_store.py
- Create: tests/test_formal_feature_contract.py
- Create: tests/test_formal_feature_store.py

**Interfaces:**
- Consumes FormalFinancialFact from Task 2 and RegistrySignatureVerifier from Task 1.
- Produces FormalEvidenceRef, FormulaNode, FormalFeatureSlot, SignedFormalFeatureRegistry, FormalFeatureValue, FormalFeatureBundle, load_signed_feature_registry, and FormalFeatureBundleStore.
- SignedFormalFeatureRegistry exposes only configuration that passed the injected verifier and has no built-in production slots, template substitutions, redlines, or source mappings.
- FormalFeatureBundleStore.write(bundle) returns FormalStoredFeatureBundle with bundle_path, manifest_path, bundle_hash, and manifest_hash.

- [ ] **Step 1: Write failing feature-contract and store tests**

~~~python
import tempfile
import unittest
from pathlib import Path

from ashare_pipeline.formal_feature_contract import (
    FormalEvidenceRef,
    FormalFeatureBundle,
    FormulaNode,
    load_signed_feature_registry,
)
from ashare_pipeline.formal_feature_store import FormalFeatureBundleStore


class FormalFeatureContractTests(unittest.TestCase):
    def test_unsigned_or_incomplete_registry_cannot_be_release_eligible(self):
        with self.assertRaisesRegex(ValueError, "registry signature"):
            load_signed_feature_registry(
                fixture_feature_registry_bytes(), "bad", "fixture-key", AcceptingVerifier()
            )
        registry = load_signed_feature_registry(
            fixture_feature_registry_bytes(), "fixture-signature", "fixture-key", AcceptingVerifier()
        )
        self.assertFalse(registry.release_eligible)
        self.assertEqual(
            FormulaNode.from_dict({"op": "divide", "left": fact_node("income.profit"), "right": fact_node("balance.equity")}).op,
            "divide",
        )

    def test_feature_bundle_bytes_are_content_addressed_and_tamper_detected(self):
        bundle = fixture_feature_bundle()
        with tempfile.TemporaryDirectory() as root:
            store = FormalFeatureBundleStore(root)
            saved = store.write(bundle)
            self.assertEqual(store.read_verified(saved), bundle)
            Path(saved.bundle_path).write_bytes(b'{"tampered":true}')
            with self.assertRaisesRegex(ValueError, "bundle hash"):
                store.read_verified(saved)
~~~

- [ ] **Step 2: Run feature-contract and store tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store -v
~~~

Expected: FAIL because formal feature modules do not exist.

- [ ] **Step 3: Implement signed slots, safe formula AST, bundle validation, and atomic storage**

~~~python
@dataclass(frozen=True)
class FormulaNode:
    op: Literal["fact", "add", "subtract", "divide", "cagr", "median", "minimum"]
    fact_key: str | None = None
    period_key: str | None = None
    left: "FormulaNode | None" = None
    right: "FormulaNode | None" = None
    items: tuple["FormulaNode", ...] = ()
    intervals: int | None = None

@dataclass(frozen=True)
class FormalFeatureSlot:
    slot_id: str
    template_id: str
    dimension: Literal["G", "V", "M", "EQ", "FS", "CA", "T"]
    required: bool
    unit: str
    formula: FormulaNode
    formula_version: str

@dataclass(frozen=True)
class FormalEvidenceRef:
    formal_fact_id: str
    source_snapshot_id: str
    source_content_sha256: str
    source_refresh_generation: str
    source_field: str
    raw_value_sha256: str
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    effective_at_utc: str
    mapping_version: str

@dataclass(frozen=True)
class FormalFeatureValue:
    slot_id: str
    value: float | None
    unit: str
    status: Literal["derived", "missing", "blocked", "not_applicable"]
    formula_version: str
    evidence: tuple[FormalEvidenceRef, ...]
    missing_reason: str | None

@dataclass(frozen=True)
class FormalFeatureBundle:
    schema_version: int
    contract_version: str
    security_id: str
    as_of_utc: str
    template_id: str
    registry_manifest_hash: str
    feature_registry_hash: str
    input_hash: str
    values: tuple[FormalFeatureValue, ...]
    history_endpoints: tuple[str, ...]
    comparable_quarter_keys: tuple[str, ...]
    blockers: tuple[str, ...]

    def canonical_bytes(self) -> bytes: ...
    def bundle_hash(self) -> str: ...

@dataclass(frozen=True)
class FormalStoredFeatureBundle:
    bundle_path: str
    manifest_path: str
    bundle_hash: str
    manifest_hash: str
~~~

FormulaNode.from_dict must accept only the listed operations and exact required child shapes; it must reject executable strings, arbitrary code, a divide node without left/right, a cagr node without a positive interval, duplicate slot IDs, duplicate feature values, and non-finite operands. load_signed_feature_registry must canonicalize its JSON, verify the signature, expose its registry hash, and set release_eligible only when its declared template IDs are exactly general_nonfinancial, bank, broker, insurance, and real_estate and all required slot IDs and source/mapping registry hashes are explicitly present in the same FormalRegistryManifest. The test fixture registry is allowed to be structurally valid but must declare release_eligible false, so it can exercise the engine without being mistaken for a production contract.

FormalFeatureBundle.validate must require a valid FormalEvidenceRef for each derived value, a reason and no numeric value for missing/blocked/not_applicable values, canonical SH/SZ/BJ identity, an explicit frozen template ID drawn from exactly {general_nonfinancial, bank, broker, insurance, real_estate}, a root registry_manifest_hash, and a bundle input hash. Every evidence ref must repeat the exact source refresh generation re-read from its formal financial fact; a snapshot ID/content SHA pair cannot substitute for it. FormalFeatureBundleStore must write canonical JSON bytes and a manifest at:

~~~text
data/formal/features/<bundle_hash>.json
data/formal/features/<bundle_hash>.manifest.json
~~~

Write each file through a same-directory .part file, flush and fsync it, verify the SHA-256, then atomically replace the final file. An existing target succeeds only when bytes and hashes match; otherwise raise a deterministic conflict. read_verified must validate both hashes and reconstruct the exact FormalFeatureBundle.

- [ ] **Step 4: Run focused formal feature tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_feature_contract tests.test_snapshot_store -v
~~~

Expected: PASS; FeatureBundle V1 and its storage remain independent.

- [ ] **Step 5: Commit the feature contract and storage**

~~~powershell
git add -- ashare_pipeline/formal_feature_contract.py ashare_pipeline/formal_feature_store.py tests/test_formal_feature_contract.py tests/test_formal_feature_store.py
git commit -m "feat: add formal feature contract and storage"
~~~

### Task 4: Point-in-Time Fact Selection, Comparable Quarters, and Feature Evaluation

**Files:**
- Create: ashare_pipeline/formal_financial_features.py
- Create: tests/test_formal_financial_features.py

**Interfaces:**
- Consumes FormalFinancialFact and FormalFactIssue from Task 2; FormalFeatureBundle, FormalFeatureValue, FormalEvidenceRef, FormulaNode, and SignedFormalFeatureRegistry from Task 3; and formal_version_sort_key and is_visible_at from ashare_pipeline.formal_time.
- Produces FormalFactVersionView, FormalFactSelection, FormalQuarterFact, FormalQuarterDerivation, select_visible_formal_facts, derive_comparable_quarters, require_formal_history, evaluate_formula, and build_formal_feature_bundle.
- build_formal_feature_bundle returns a bundle with explicit missing/blocked values and blockers; it does not assign formal_scored or a seven-dimension score.

- [ ] **Step 1: Write failing selection, quarter, and formula tests**

~~~python
import unittest

from ashare_pipeline.formal_financial_features import (
    build_formal_feature_bundle,
    derive_comparable_quarters,
    require_formal_history,
    select_visible_formal_facts,
)


class FormalFinancialFeatureTests(unittest.TestCase):
    def test_visible_selector_prefers_latest_preclose_version_not_postclose_revision(self):
        selection = select_visible_formal_facts(
            [fact(version="preclose", effective_at="2026-08-31T06:59:59+00:00", value=100.0),
             fact(version="postclose", effective_at="2026-08-31T07:01:00+00:00", value=999.0)],
            "2026-08-31T07:00:00+00:00",
        )
        self.assertEqual(selection.facts[0].value, 100.0)
        self.assertNotIn("future_fact", selection.blockers)

    def test_duration_quarters_follow_chinese_cumulative_rules_and_reject_mixed_basis(self):
        quarters = derive_comparable_quarters(
            [duration_fact("Q1", 10.0), duration_fact("H1", 30.0),
             duration_fact("Q3", 45.0), duration_fact("FY", 70.0)]
        )
        self.assertEqual([item.value for item in quarters.facts], [10.0, 20.0, 15.0, 25.0])
        broken = derive_comparable_quarters(
            [duration_fact("Q1", 10.0, basis="consolidated"),
             duration_fact("H1", 30.0, basis="parent")]
        )
        self.assertEqual(broken.facts, ())
        self.assertIn("quarter_accounting_basis_mismatch", broken.blockers)

    def test_history_requires_four_endpoints_eight_quarters_and_cyclic_five_endpoints(self):
        quarters = ("2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2")
        self.assertTrue(require_formal_history(
            ("2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"),
            comparable_quarter_keys=quarters,
            as_of_utc="2026-08-31T07:00:00+00:00",
            cyclic=False,
        ).eligible)
        self.assertFalse(require_formal_history(
            ("2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"),
            comparable_quarter_keys=quarters,
            as_of_utc="2026-08-31T07:00:00+00:00",
            cyclic=True,
        ).eligible)
        self.assertFalse(require_formal_history(
            ("2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"),
            comparable_quarter_keys=quarters[:-1],
            as_of_utc="2026-08-31T07:00:00+00:00",
            cyclic=False,
        ).eligible)

    def test_unsigned_registry_yields_blocked_bundle_instead_of_derived_score_input(self):
        bundle = build_formal_feature_bundle(
            security_id="SZ000001",
            as_of_utc="2026-08-31T07:00:00+00:00",
            template_id="general_nonfinancial",
            facts=[fact()],
            quarters=[],
            registry=unsigned_fixture_registry(),
        )
        self.assertIn("feature_registry_not_release_eligible", bundle.blockers)
        self.assertEqual({value.status for value in bundle.values}, {"blocked"})
~~~

- [ ] **Step 2: Run formal financial feature tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_features -v
~~~

Expected: FAIL because ashare_pipeline.formal_financial_features does not exist.

- [ ] **Step 3: Implement deterministic selection, quarter derivation, history, and safe evaluation**

~~~python
@dataclass(frozen=True)
class FormalFactSelection:
    facts: tuple[FormalFinancialFact, ...]
    blockers: tuple[str, ...]

@dataclass(frozen=True)
class FormalQuarterFact:
    id: str
    security_id: str
    statement: str
    metric_key: str
    quarter_end: str
    quarter_key: Literal["Q1", "Q2", "Q3", "Q4"]
    value: float
    unit: str
    nature: Literal["instant", "duration"]
    accounting_basis: str
    mapping_version: str
    component_fact_ids: tuple[str, ...]
    evidence: tuple[FormalEvidenceRef, ...]
    derivation_version: str

@dataclass(frozen=True)
class FormalQuarterDerivation:
    facts: tuple[FormalQuarterFact, ...]
    blockers: tuple[str, ...]

@dataclass(frozen=True)
class FormalHistoryResult:
    eligible: bool
    annual_endpoints: tuple[str, ...]
    blockers: tuple[str, ...]

@dataclass(frozen=True)
class FormalFormulaResult:
    value: float | None
    unit: str | None
    evidence: tuple[FormalEvidenceRef, ...]
    time_reliability: float | None
    missing_reason: str | None

@dataclass(frozen=True)
class FormalFactVersionView:
    published_at_utc: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    content_hash: str

def select_visible_formal_facts(
    facts: Iterable[FormalFinancialFact], as_of_utc: str
) -> FormalFactSelection: ...

def derive_comparable_quarters(
    facts: Iterable[FormalFinancialFact]
) -> FormalQuarterDerivation: ...

def require_formal_history(
    annual_endpoints: Iterable[str],
    *,
    comparable_quarter_keys: Iterable[str],
    as_of_utc: str,
    cyclic: bool,
) -> FormalHistoryResult: ...

def evaluate_formula(
    node: FormulaNode,
    facts: Mapping[tuple[str, str], FormalFinancialFact | FormalQuarterFact],
) -> FormalFormulaResult: ...
~~~

select_visible_formal_facts must discard each fact whose published_at_utc or effective_at_utc is after as_of_utc, group remaining versions by security, statement, metric, period, unit, nature, and accounting basis, and choose with formal_version_sort_key. It must first project every FormalFinancialFact into FormalFactVersionView with published_at_utc, source_updated_at_utc, captured_at_utc, and content_hash equal to source_content_sha256. This explicit adapter is the only object passed to the V5 sort helper; no caller may assume that a differently named source-content field is implicitly compatible. A logical group containing different parser or mapping versions is a mapping conflict rather than an opportunity to select whichever version arrived most recently. If the same selected logical fact has non-identical raw values without a deterministic winning version, it must return the conflict blocker rather than selecting by arrival order.

derive_comparable_quarters must first validate all component facts by security, statement, metric, unit, nature, mapping version, accounting basis, and selected-version lineage. It must derive duration Q2/H1-Q1, Q3/Q3-H1, and Q4/FY-Q3 only when both required cumulative inputs are present and compatible; Q1 duration uses Q1 cumulative; instant values use their quarter-end fact directly. A quarter fact must carry the complete sorted operand fact IDs and the union of their evidence. Missing Q1, H1, Q3, FY, a non-consecutive sequence, or a mixed accounting basis produces explicit blockers and no fabricated quarter.

require_formal_history must require four consecutive FY endpoints for non-cyclic securities and five consecutive FY endpoints for cyclic securities. It must require exactly eight consecutive comparable quarter keys ending no later than as_of_utc; a missing endpoint returns a pending-evidence reason rather than shortening a CAGR or persistence window.

evaluate_formula must recursively evaluate only the FormulaNode operations defined in Task 3. A fact node resolves by exact metric/period key; add/subtract require equal units; divide rejects zero denominators; cagr requires start and end values of the same economic unit and its exact registry interval count; median and minimum require homogeneous finite operands. Each result returns the sorted de-duplicated FormalEvidenceRef union and the lowest source time-reliability among operands. build_formal_feature_bundle must create exactly one FormalFeatureValue for every registry slot applicable to the chosen template, preserve each missing reason, calculate canonical input_hash from selected fact IDs, selected source snapshot IDs/content hashes/refresh generations, quarter IDs, registry hash, template ID, and as_of_utc, and mark the bundle blocked when the signed registry is not release eligible. It must never set a score, peer percentile, pool membership, or confidence C.

- [ ] **Step 4: Run formal feature, time, and legacy financial regression suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_features tests.test_formal_financial_schema tests.test_formal_feature_contract tests.test_formal_time tests.test_financial_features -v
~~~

Expected: PASS; old build_feature_bundle continues to use its own V1-only rules.

- [ ] **Step 5: Commit the point-in-time feature engine**

~~~powershell
git add -- ashare_pipeline/formal_financial_features.py tests/test_formal_financial_features.py
git commit -m "feat: derive formal point-in-time financial features"
~~~

### Task 5: Additive SQLite V6 Formal Facts, Quarters, Features, Registry, and Task Ownership

**Files:**
- Modify: ashare_pipeline/state_store.py: schema constants, initialize(), V6 DDL, formal persistence APIs, and formal task ownership APIs
- Modify: tests/test_state_store.py: V5-to-V6 migration, fact/quarter/feature persistence, and task-transition tests

**Interfaces:**
- Consumes formal_source_snapshot and formal_collection_task created by V5, FormalFinancialFact from Task 2, FormalQuarterFact from Task 4, and FormalFeatureBundle and FormalStoredFeatureBundle from Task 3.
- Produces StateStore.put_formal_snapshot_for_leased_task, get_formal_task_snapshot_receipt, insert_formal_financial_facts, list_formal_financial_facts, insert_formal_quarter_facts, list_formal_quarter_facts, put_formal_feature_bundle, get_formal_feature_bundle_row, put_formal_registry_blob, get_formal_registry_blob, put_formal_registry_manifest, get_formal_registry_manifest, enqueue_formal_task, renew_formal_task_lease, complete_formal_task, fail_formal_task, resolve_formal_task_dependencies, get_formal_task, list_formal_tasks, get_formal_source_circuit, and set_formal_source_circuit. Task 5 creates the empty formal_context_fact table only; Task 5B owns its typed put/list APIs after FormalContextFact exists.
- V6 must not rename, mutate, or read legacy financial_fact, feature_set, feature_value, source_snapshot, job, score_run, or score_item as formal evidence.

- [ ] **Step 1: Write failing V5-to-V6 migration and persistence tests**

~~~python
def test_initialize_migrates_complete_v5_ledger_to_v6_without_touching_legacy_rows(self):
    with sqlite3.connect(self.db_path) as connection:
        StateStore._create_v2_schema(connection)
        connection.execute("CREATE TABLE schema_migration(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_migration VALUES (2, ?)", (utc_at(0),))
        StateStore._apply_v3_migration(connection)
        StateStore._apply_v4_migration(connection)
        StateStore._apply_v5_migration(connection)
        connection.commit()
    StateStore(self.db_path).initialize()
    with sqlite3.connect(self.db_path) as connection:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migration ORDER BY version")]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    self.assertEqual(versions, [2, 3, 4, 5, 6])
    self.assertTrue({"formal_financial_fact", "formal_quarter_fact", "formal_feature_set", "formal_feature_value", "formal_context_fact", "formal_registry_blob", "formal_registry_manifest", "formal_source_circuit"} <= tables)
    self.assertEqual(legacy_score_run_count(self.db_path), 1)

def test_formal_fact_and_bundle_reject_legacy_snapshot_or_tampered_evidence(self):
    fact = formal_fact(snapshot_id=verified_formal_snapshot_id(self.store))
    self.store.insert_formal_financial_facts((fact,))
    self.store.insert_formal_quarter_facts((formal_quarter_fact(fact),))
    bundle = fixture_feature_bundle_for(fact)
    stored = self.feature_store.write(bundle)
    self.assertEqual(self.feature_store.read_verified(stored), bundle)
    self.store.put_formal_feature_bundle(bundle, stored)
    with self.assertRaisesRegex(ValueError, "formal source snapshot"):
        self.store.insert_formal_financial_facts((formal_fact(snapshot_id=legacy_snapshot_id(self.store)),))
~~~

- [ ] **Step 2: Run V6 migration tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_initialize_migrates_complete_v5_ledger_to_v6_without_touching_legacy_rows -v
~~~

Expected: FAIL because schema V6 and V6 persistence APIs do not exist.

- [ ] **Step 3: Implement V6 DDL, continuous migration checks, and persistence invariants**

Set SCHEMA_VERSION to 6. Add _V6_TABLE_DDL, _V6_INDEX_DDL, _apply_v6_migration, and continuous initialize() validation for only these migration ledgers:

~~~text
{2}
{2,3}
{2,3,4}
{2,3,4,5}
{2,3,4,5,6}
~~~

Add these V6 tables and indexes:

~~~text
formal_financial_fact:
  id, security_id, statement, metric_key, period_start, period_end, period_kind,
  value, unit, nature, accounting_basis, published_at_utc, published_precision, effective_at_utc,
  effective_time_evidence_hash, source_updated_at_utc, captured_at_utc, source_snapshot_id, source_content_sha256,
  source_refresh_generation, source_producing_task_id, source_field,
  raw_value_sha256, parser_id, parser_version, mapping_version, created_at_utc

formal_quarter_fact:
  id, security_id, statement, metric_key, quarter_end, quarter_key, value, unit,
  nature, accounting_basis, mapping_version, component_fact_ids_json, evidence_json,
  derivation_version, created_at_utc

formal_feature_set:
  id, security_id, as_of_utc, template_id, registry_manifest_hash, feature_registry_hash, input_hash UNIQUE,
  history_endpoints_json, comparable_quarter_keys_json, blockers_json, bundle_hash, bundle_manifest_hash, bundle_path, manifest_path,
  created_at_utc

formal_feature_value:
  feature_set_id, slot_id, value, unit, status, formula_version, evidence_json,
  missing_reason

formal_context_fact:
  id, context_kind, scope_key, security_id, as_of_utc, value_json,
  no_coverage, published_at_utc, effective_at_utc, source_updated_at_utc,
  captured_at_utc, refresh_generation, source_snapshot_id,
  source_content_sha256, parser_id, parser_version, mapping_version, registry_manifest_hash,
  evidence_json, created_at_utc

formal_registry_manifest:
  manifest_hash PRIMARY KEY, purpose, approval_id, canonical_json, signature, key_id,
  source_registry_hash, mapping_registry_hash, feature_registry_hash,
  scoring_registry_hash, industry_registry_hash, cyclic_registry_hash,
  redline_registry_hash, status_registry_hash, event_registry_hash, created_at_utc

formal_registry_blob:
  registry_hash PRIMARY KEY, registry_role, canonical_json, signature, key_id,
  approval_id, created_at_utc

formal_source_circuit:
  source, state, failure_count, reason_json, opened_at_utc, retry_after_utc,
  updated_at_utc
~~~

formal_financial_fact.source_snapshot_id must reference formal_source_snapshot, and insertion must re-read that snapshot's verification JSON, content hash, refresh generation, producing-task linkage, parser ID/version, and immutable formal_task_snapshot_receipt when a producing task exists, plus recomputed canonical request fingerprint/request security/period, mapping version, published precision, effective-time evidence hash, captured time, and source identity before accepting the fact. It rejects a copied or substituted source_refresh_generation/source_producing_task_id/parser ID/version. A terminal parse/build outcome after a verified raw receipt is valid forensic evidence but cannot be promoted to a usable fact unless the individual fact insertion succeeds. insert_formal_quarter_facts must verify every component ID belongs to stored formal facts, has matching value/evidence metadata, and produces its canonical quarter ID. It is append-only and idempotent: an existing quarter ID is accepted only when every content field matches, while a changed source fact produces a new quarter ID and leaves the earlier derived quarter available for historical audit. formal_feature_set is likewise append-only by input_hash: multiple rows for the same security/as-of/template/root are legal when a later authoritative fact/snapshot lineage changes; an equal input hash is idempotent only when every stored field matches. StateStore implements Task 1's FormalRegistryBundleRepository only after this V6 migration. put_formal_registry_blob accepts the signed child envelope plus an injected RegistrySignatureVerifier, re-hashes canonical_json, verifies signature/key_id, and saves role/hash/signature/key/approval identity append-only. put_formal_registry_manifest accepts the signed FormalRegistryManifest plus that verifier, re-hashes and verifies its canonical_json/signature/key_id, and rejects any child hash whose already persisted registry blob does not match its declared role, signature, or canonical bytes. The loader re-verifies both root and child signatures on every read; no cached write-time result is trusted. Define the bundle API exactly as put_formal_feature_bundle(self, bundle: FormalFeatureBundle, stored: FormalStoredFeatureBundle) -> tuple[str, bool]. It must call FormalFeatureBundle.validate, require bundle.registry_manifest_hash to resolve to the persisted manifest and agree with every child registry hash, require stored.bundle_hash to equal bundle.bundle_hash(), require the persisted bundle_manifest_hash to equal stored.manifest_hash, revalidate each derived evidence reference and its generation against formal_financial_fact and formal_source_snapshot, validate that stored paths stay below data/formal/features, and treat an existing identical input hash as idempotent only when every stored header/value/path/hash field is equal. The worker must call FormalFeatureBundleStore.read_verified(stored) immediately before this database call; release validation will independently re-read the stored bytes.

Use V5 formal_collection_task, formal_collection_task_dependency, and formal_task_snapshot_receipt rather than altering their state model. Define the ownership APIs exactly as enqueue_formal_task(kind: str, idempotency_key: str, refresh_generation: str, payload: Mapping[str, object], prerequisite_task_ids: Sequence[str] = ()) -> str, supersede_formal_tasks(scope: Mapping[str, object], before_generation: str) -> int, lease_next_formal_task(kinds: Sequence[str], worker_id: str, lease_seconds: int, now_utc: str | None = None) -> dict[str, object] | None, resolve_formal_task_dependencies() -> int, put_formal_snapshot_for_leased_task(fetch: OfficialFetch, stored: FormalStoredSnapshot, verification: EvidenceVerification, task_id: str, worker_id: str) -> OfficialSnapshotRef, renew_formal_task_lease(task_id: str, worker_id: str, lease_seconds: int, now_utc: str | None = None) -> str, complete_formal_task(task_id: str, worker_id: str, result: Mapping[str, object]) -> None, and fail_formal_task(task_id: str, worker_id: str, error: Mapping[str, object], status: Literal["retryable_failed", "terminal_failed"], next_retry_at: str | None) -> None. FormalSnapshotRepository writes the raw manifest first and calls this API with the fetch, stored manifest, and verification; StateStore revalidates those inputs, inserts the row/receipt, and only then re-reads and returns OfficialSnapshotRef, so a caller cannot supply a pre-persistence ref. Lease, snapshot receipt, completion, and failure must perform a compare-and-set transition from the named leased owner; failure accepts only the two stated terminal/retry states and serializes a deterministic error object. complete_formal_task for a source-fetch task requires its already recorded raw snapshot receipt; fail_formal_task permits an existing receipt and records a downstream error without deleting it. lease_next_formal_task must use V5's deterministic ready/retry/expired-lease reclaim semantics and ignore any task until every dependency is verified; resolve_formal_task_dependencies turns an unleased pending or retryable_failed dependent whose parent is terminal_failed or superseded into terminal_failed without a network attempt. The worker, rather than SQL, checks source-circuit state after leasing because V5's generic task table does not add a source column. set_formal_source_circuit must be idempotent for equal state and must not alter another source's tasks. No V6 query may join a legacy source_snapshot or job table to satisfy formal evidence.

- [ ] **Step 4: Run V6 migration, formal persistence, and legacy StateStore suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store tests.test_formal_financial_schema tests.test_formal_feature_contract tests.test_formal_feature_store -v
~~~

Expected: PASS; V2-V5 migration behavior and all legacy StateStore contracts remain intact.

- [ ] **Step 5: Commit the V6 storage layer**

~~~powershell
git add -- ashare_pipeline/state_store.py tests/test_state_store.py
git commit -m "feat: persist formal v3 facts and features"
~~~

### Task 5A: Verified Typed Formal Feature Repository

**Files:**
- Create: ashare_pipeline/formal_feature_repository.py
- Create: tests/test_formal_feature_repository.py

**Interfaces:**
- Produces FormalFeatureRepository, get_verified_formal_feature_bundle, and select_current_verified_formal_feature_bundle.
- Consumes StateStore V6 feature-set rows, FormalFeatureBundleStore, and the Task 4 point-in-time financial-fact/quarter selection routines.
- Returns a typed FormalFeatureBundle only after re-reading the stored bytes and checking database bundle hash, manifest hash, input hash, security ID, as-of instant, and registry-manifest hash. Exact historical lookup and current-lineage selection are deliberately separate.

- [ ] **Step 1: Write the failing verified-bundle tests**

~~~python
class FormalFeatureRepositoryTests(unittest.TestCase):
    def test_returns_typed_bundle_only_when_row_and_stored_bytes_match(self):
        repository = FormalFeatureRepository(self.store, self.bundle_store)
        bundle = repository.select_current_verified_formal_feature_bundle(
            "BJ430001", AS_OF, template_id="general_nonfinancial", registry_manifest_hash="m" * 64
        )
        self.assertEqual(bundle.security_id, "BJ430001")

    def test_tampered_bundle_or_registry_manifest_mismatch_is_rejected(self):
        repository = FormalFeatureRepository(self.store, self.bundle_store)
        tamper_bundle_bytes(self.bundle_path)
        with self.assertRaisesRegex(ValueError, "bundle hash"):
            repository.select_current_verified_formal_feature_bundle(
                "BJ430001", AS_OF, template_id="general_nonfinancial", registry_manifest_hash="m" * 64
            )

    def test_authoritative_correction_selects_new_bundle_but_old_input_stays_readable(self):
        repository = FormalFeatureRepository(self.store, self.bundle_store)
        old = repository.select_current_verified_formal_feature_bundle(
            "BJ430001", AS_OF, template_id="general_nonfinancial", registry_manifest_hash="m" * 64
        )
        insert_corrected_visible_fact_and_rebuild_feature_bundle()
        current = repository.select_current_verified_formal_feature_bundle(
            "BJ430001", AS_OF, template_id="general_nonfinancial", registry_manifest_hash="m" * 64
        )
        self.assertNotEqual(current.input_hash, old.input_hash)
        self.assertEqual(
            repository.get_verified_formal_feature_bundle(input_hash=old.input_hash).bundle_hash(),
            old.bundle_hash(),
        )

    def test_non_v3_template_id_is_rejected_before_bundle_lookup(self):
        with self.assertRaisesRegex(ValueError, "template_id"):
            FormalFeatureRepository(self.store, self.bundle_store).select_current_verified_formal_feature_bundle(
                "BJ430001", AS_OF, template_id="industrial", registry_manifest_hash="m" * 64
            )
~~~

- [ ] **Step 2: Run repository tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_repository -v
~~~

Expected: FAIL because the verified formal feature repository does not exist.

- [ ] **Step 3: Implement verified lookup**

get_verified_formal_feature_bundle(input_hash: str) selects exactly that V6 row and rejects blocked bundles, missing paths, files outside data/formal/features, a mismatched bundle_hash, a mismatched bundle_manifest_hash, stale manifest hashes, and bundle headers that disagree with the stored row. select_current_verified_formal_feature_bundle(security_id: str, as_of_utc: str, template_id: str, registry_manifest_hash: str) first rejects a template_id outside exactly {general_nonfinancial, bank, broker, insurance, real_estate}, then uses the same Task 4 visible-fact/version and comparable-quarter routines as feature construction to derive the one current canonical expected input_hash, then delegates to exact lookup. It never treats two rows with different input_hash values in the same security/as-of/template/root scope as duplicates: they are immutable historical lineages. It invokes FormalFeatureBundleStore.read_verified and returns the reconstructed immutable object; it never reconstructs a typed bundle directly from SQLite JSON. V7 records both selected feature input_hash and bundle_hash in its input manifest, uses exact lookup to read a prior run, and uses current-lineage selection only when creating a new run. The V7 score runner must receive this repository as a dependency rather than reading feature rows or paths itself.

- [ ] **Step 4: Run repository and formal-feature suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_repository tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_state_store -v
~~~

Expected: PASS; a V1 FeatureBundle cannot be returned by this repository.

- [ ] **Step 5: Commit verified feature access**

~~~powershell
git add -- ashare_pipeline/formal_feature_repository.py tests/test_formal_feature_repository.py
git commit -m "feat: read verified formal feature bundles"
~~~

### Task 5B: Official Market, Industry, Status, Event, and Consensus Context

**Files:**
- Create: ashare_pipeline/formal_context_schema.py
- Create: ashare_pipeline/formal_context_repository.py
- Create: tests/test_formal_context_schema.py
- Create: tests/test_formal_context_repository.py
- Modify: ashare_pipeline/state_store.py: typed V6 context persistence APIs over the table created in Task 5

**Interfaces:**
- Produces FormalContextRequest, SignedContextRequestResolver, FormalContextFact, FormalContextIssue, FormalContextRepository.resolve_verified_calendar_binding, build_effective_time_resolver, StateStore.put_formal_context_facts, and StateStore.list_formal_context_facts.
- Consumes verified formal source snapshots, one VerifiedRegistryBundle, and signed source/parser/mapping configurations loaded only from that bundle.
- Owns the frozen trading calendar, market close/effective-trade evidence, exchange state, frozen industry mapping, regulatory/delisting state, registered event calendar, and verified consensus/no-coverage context that V7 requires.

- [ ] **Step 1: Write failing context contract tests**

~~~python
class FormalContextSchemaTests(unittest.TestCase):
    def test_context_request_resolves_to_one_signed_official_request(self):
        request = fixture_context_resolver().resolve(
            context_kind="market_close", scope_key="freeze-close", security_id="BJ430001",
            as_of_utc=AS_OF, registry_manifest_hash="m" * 64,
        )
        self.assertEqual(request.official_request.dataset, "bse_market_close")
        self.assertEqual(request.official_request.period_or_date, "2026-08-31")
        self.assertEqual(request.calendar_binding.manifest_sha256, "c" * 64)
        with self.assertRaisesRegex(ValueError, "context request"):
            fixture_context_resolver().resolve(
                context_kind="unregistered", scope_key="x", security_id=None,
                as_of_utc=AS_OF, registry_manifest_hash="m" * 64,
            )

    def test_market_context_requires_exchange_status_volume_turnover_and_valid_close_date(self):
        fact = formal_context_fact(
            kind="market_close",
            security_id="BJ430001",
            value={
                "exchange_allows_trading": False,
                "volume": "0",
                "turnover": "0",
                "valid_close": "12.34",
                "valid_close_date": "2026-08-28",
                "stale_trading_days": 1,
            },
        )
        self.assertTrue(fact.validate())

    def test_only_verified_explicit_no_coverage_can_be_neutral_consensus(self):
        no_coverage = formal_context_fact(
            kind="consensus_snapshot", security_id="SZ000001", no_coverage=True,
            value={"coverage_status": "no_valid_coverage"},
        )
        self.assertTrue(no_coverage.validate())
        with self.assertRaisesRegex(ValueError, "no coverage"):
            formal_context_fact(kind="consensus_snapshot", security_id="SZ000001", no_coverage=True, value={})

    def test_context_after_freeze_or_wrong_industry_snapshot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "effective"):
            formal_context_fact(kind="industry_snapshot", as_of_utc=AFTER_FREEZE)

    def test_effective_time_resolver_rejects_another_verified_calendar_manifest(self):
        binding = self.repository.resolve_verified_calendar_binding(
            selector=fixture_calendar_selector(), exchange="SZ", as_of_utc=AS_OF,
            registry_manifest_hash="m" * 64,
        )
        other_verified_binding = verified_calendar_binding(
            manifest_sha256=other_verified_calendar_manifest(), exchange="SZ",
            freeze_at_utc=AS_OF, registry_manifest_hash="m" * 64,
            selector_hash=binding.selector_hash, prerequisite_task_id=binding.prerequisite_task_id,
        )
        with self.assertRaisesRegex(ValueError, "calendar binding"):
            build_effective_time_resolver(self.repository).next_exchange_close(
                exchange="SZ", disclosure_date_cn="2026-08-28",
                calendar_binding=other_verified_binding,
            )

class FormalContextRepositoryTests(unittest.TestCase):
    def test_exact_frozen_context_lookup_rechecks_snapshot_and_manifest(self):
        context = self.repository.get_verified(
            kind="industry_snapshot", scope_key="sw2021", security_id="BJ430001", as_of_utc=AS_OF,
            registry_manifest_hash="m" * 64,
        )
        self.assertEqual(context.value["secondary_industry"], "fixture-secondary")

    def test_new_refresh_generation_selects_latest_visible_context_without_erasing_old_audit_row(self):
        write_context_version(self.store, generation="index-v1", updated_at="2026-08-20T00:00:00+00:00")
        write_context_version(self.store, generation="index-v2", updated_at="2026-08-21T00:00:00+00:00")
        context = self.repository.get_verified(
            kind="industry_snapshot", scope_key="sw2021", security_id="BJ430001", as_of_utc=AS_OF,
            registry_manifest_hash="m" * 64,
        )
        self.assertEqual(context.refresh_generation, "index-v2")
        self.assertEqual(self.store.count_context_versions("industry_snapshot", "BJ430001"), 2)

    def test_typed_context_insert_rejects_unverified_or_wrong_lineage_before_lookup(self):
        with self.assertRaisesRegex(ValueError, "formal source snapshot"):
            self.store.put_formal_context_facts((formal_context_fact(source_snapshot_id=legacy_snapshot_id()),))
        self.store.put_formal_context_facts((formal_context_fact(source_snapshot_id=verified_snapshot_id()),))
        self.assertEqual(len(self.store.list_formal_context_facts()), 1)
~~~

- [ ] **Step 2: Run context tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_context_schema tests.test_formal_context_repository -v
~~~

Expected: FAIL because formal context types and repository do not exist.

- [ ] **Step 3: Implement typed context evidence and exact lookup**

Use this contract:

~~~python
CONTEXT_KINDS = (
    "trading_calendar", "market_close", "security_state", "industry_snapshot",
    "regulatory_state", "event_calendar", "consensus_snapshot",
)

@dataclass(frozen=True)
class FormalContextRequest:
    context_kind: str
    scope_key: str
    security_id: str | None
    as_of_utc: str
    official_request: OfficialRequest
    request_version: str
    upstream_generation: str
    refresh_generation: str
    registry_manifest_hash: str
    relevant_registry_hashes: tuple[tuple[str, str], ...]
    calendar_binding: VerifiedCalendarBinding | None

class SignedContextRequestResolver(Protocol):
    def resolve(
        self, *, context_kind: str, scope_key: str, security_id: str | None,
        as_of_utc: str, registry_manifest_hash: str
    ) -> FormalContextRequest: ...

@dataclass(frozen=True)
class FormalContextFact:
    id: str
    context_kind: str
    scope_key: str
    security_id: str | None
    as_of_utc: str
    value: Mapping[str, object]
    no_coverage: bool
    published_at_utc: str
    effective_at_utc: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    refresh_generation: str
    source_snapshot_id: str
    source_content_sha256: str
    parser_id: str
    parser_version: str
    mapping_version: str
    registry_manifest_hash: str

@dataclass(frozen=True)
class FormalContextVersionView:
    published_at_utc: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    content_hash: str

class FormalContextRepository:
    def __init__(self, store: StateStore, snapshots: FormalSnapshotRepository) -> None: ...

    def get_verified(
        self, *, kind: str, scope_key: str, security_id: str | None,
        as_of_utc: str, registry_manifest_hash: str
    ) -> FormalContextFact: ...

    def resolve_verified_calendar_binding(
        self, *, selector: CalendarSelector, exchange: Literal["SH", "SZ", "BJ"],
        as_of_utc: str, registry_manifest_hash: str,
    ) -> VerifiedCalendarBinding: ...
~~~

SignedContextRequestResolver is constructed from one VerifiedRegistryBundle plus FormalContextRepository and maps each permitted context kind/scope/security/as-of combination to exactly one OfficialRequest source, dataset, security_id, period_or_date, parser, mapping, request version, signed calendar_selector, authoritative upstream_generation, and a sorted exact relevant_registry_hashes tuple. After the bootstrap calendar is verified, it calls FormalContextRepository.resolve_verified_calendar_binding(selector, exchange, as_of_utc, registry_manifest_hash). That method re-reads the selected trading_calendar FormalContextFact, its verified FormalSnapshotRepository source ref, and its raw receipt when present; it requires the exact signed selector, exchange, freeze, root hash, source snapshot manifest, and verified prerequisite task to match, then returns a VerifiedCalendarBinding. FormalContextRequest and FormalContextTaskPayload store that complete immutable binding rather than a raw manifest hash. They derive refresh_generation from upstream_generation, the root registry manifest hash, relevant signed role hashes, and, when date-only, the canonical signed selector plus every immutable VerifiedCalendarBinding field. They reject a missing mapping, source/dataset mismatch, request security mismatch, unexpected period/date, a non-bootstrap date-only configuration with no selector or resolved binding, a binding that does not match the selector/root/exchange/freeze/prerequisite, a noncanonical relevant-role tuple, or a context request whose registry manifest hash differs from the current root bundle.

market_close must state the freeze-date exchange trade state, volume, turnover, whether the day is an effective trade, the most recent valid-close price/date when stale, and stale_trading_days. security_state covers ST/star-ST, listing/delisting arrangement, forced-delist risk, and suspension state. industry_snapshot is the frozen SW2021 mapping with primary/secondary industry, source version, effective date, and complete mapping hash. regulatory_state and event_calendar keep source-backed flags separate from scores; only a registry-listed quantified/date-verifiable event entry may expose a T input. consensus_snapshot distinguishes verified coverage, explicit verified no valid coverage, and pending evidence.

build_effective_time_resolver is constructed with FormalContextRepository, which owns the FormalSnapshotRepository used to re-read source refs. Its next_exchange_close(exchange, disclosure_date_cn, calendar_binding) revalidates the binding through resolve_verified_calendar_binding: the binding's manifest must be the selected verified trading-calendar source snapshot under the same signed selector, exchange, freeze, root, and prerequisite task. It then returns the next exchange close only when that calendar context itself is visible at the requested freeze. Another otherwise verified calendar manifest, a mismatched exchange/root/selector/task, or an unavailable calendar returns an explicit pending/error reason; it does not guess a weekday.

Task 5B implements StateStore.put_formal_context_facts and list_formal_context_facts over the V6 table. put_formal_context_facts accepts only a verified formal source snapshot and, when it has a producing task, its immutable raw-fetch receipt, plus a context kind declared in the persisted root registry manifest. It validates scope/security identity, exact as-of instant, source content hash, parser ID/version, mapping version, and publication/effective cutoff. It stores an explicit no_coverage flag only for a verified consensus response declaring no valid coverage; a failed, absent, or time-unverifiable consensus response is never converted to no coverage.

FormalContextRepository re-reads the linked formal source snapshot verification, content hash, refresh generation, and producing-task linkage; it requires FormalContextFact.refresh_generation to equal that snapshot generation, checks the root manifest hash, and rejects future published/effective instants, source identity mismatch, or an unregistered context kind. It retains every version generated by a distinct refresh_generation. For one logical context key, it selects the visible version through a FormalContextVersionView using the V5 order: published descending, source_updated descending with null last, captured descending, and content hash ascending. It reports a deterministic conflict only when the selected version's context value cannot be normalized or source identity cannot be verified; it does not reject a legitimate official correction merely because an earlier logical version exists. The selected generation, snapshot ID, and content hash are included in V7 input_hash and V8 evidence manifest. It returns no fallback to third-party market data, legacy industry templates, or an inferred consensus state.

- [ ] **Step 4: Run context, source, and time suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_context_schema tests.test_formal_context_repository tests.test_formal_sources tests.test_formal_time -v
~~~

Expected: PASS; date-only resolver behavior is backed by verified calendar context.

- [ ] **Step 5: Commit formal context evidence**

~~~powershell
git add -- ashare_pipeline/formal_context_schema.py ashare_pipeline/formal_context_repository.py tests/test_formal_context_schema.py tests/test_formal_context_repository.py ashare_pipeline/state_store.py
git commit -m "feat: add verified formal market and policy context"
~~~

### Task 6: Resumable Formal Collection and Per-Security Feature Rebuild Worker

**Files:**
- Create: ashare_pipeline/formal_deep_worker.py
- Create: tests/test_formal_deep_worker.py

**Interfaces:**
- Consumes StateStore's V5/V6 formal task APIs, FormalRegistryBundleLoader from Task 1, FormalSnapshotRepository and FormalUniverseIngestor/FormalUniverseSourceDocument from the foundation plan, extract_formal_financial_facts from Task 2, FormalContextFact from Task 5B, select_visible_formal_facts/derive_comparable_quarters/build_formal_feature_bundle from Task 4, FormalFeatureBundleStore from Task 3, and no independently injected child registry.
- Produces CalendarBindingPending, FormalRegistryRuntime, FormalRegistryRuntimeLoader, derive_collection_refresh_generation, FormalStatementTaskPayload, FormalContextTaskPayload, FormalUniverseSourceTaskPayload, FormalUniverseFinalizeTaskPayload, FormalFeatureBuildTaskPayload, formal_statement_task_specs, formal_context_task_specs, formal_universe_task_specs, enqueue_frozen_formal_universe, enqueue_formal_feature_build, execute_queued_formal_work, and FormalCollectionSummary.
- The worker accepts only formal_statement, formal_context, formal_universe_source, formal_universe_finalize, and formal_feature_build task kinds. It rejects a legacy deep_statement, deep_financial, feature_build, generic job payload, or an unscoped universe import at its entry boundary.

- [ ] **Step 1: Write failing resumability and circuit tests**

~~~python
import unittest

from ashare_pipeline.formal_deep_worker import (
    CalendarBindingPending,
    execute_queued_formal_work,
    formal_statement_task_specs,
)
from ashare_pipeline.formal_sources import FormalSourceBlocked


class FormalDeepWorkerTests(unittest.TestCase):
    def test_same_generation_is_reused_and_new_authoritative_generation_rebuilds_only_one_security(self):
        specs = formal_statement_task_specs(
            security_id="BJ430001",
            report_period="2025-12-31",
            as_of_utc="2026-08-31T07:00:00+00:00",
            source="cninfo",
            source_registry_hash="a" * 64,
            mapping_registry_hash="b" * 64,
            upstream_generation="discovery-v1",
            registry_manifest_hash="m" * 64,
        )
        enqueue_all(self.store, specs)
        first = execute_queued_formal_work(fixture_dependencies(self.store), worker_id="worker-a")
        self.assertEqual(first.remote_attempts, 3)
        second = execute_queued_formal_work(fixture_dependencies(self.store), worker_id="worker-b")
        self.assertEqual(second.remote_attempts, 0)
        replace_one_official_response("BJ430001", "profit_sheet")
        enqueue_all(self.store, formal_statement_task_specs(
            security_id="BJ430001",
            report_period="2025-12-31",
            as_of_utc="2026-08-31T07:00:00+00:00",
            source="cninfo",
            source_registry_hash="a" * 64,
            mapping_registry_hash="b" * 64,
            upstream_generation="discovery-v2",
            registry_manifest_hash="m" * 64,
        ))
        third = execute_queued_formal_work(fixture_dependencies(self.store), worker_id="worker-c")
        self.assertEqual(third.rebuilt_security_ids, ("BJ430001",))

    def test_same_upstream_generation_with_new_root_manifest_creates_new_collection_lineage(self):
        before = formal_statement_task_specs(
            "BJ430001", "2025-12-31", AS_OF, "cninfo", "a" * 64, "b" * 64,
            "discovery-v1", "m" * 64,
        )
        after = formal_statement_task_specs(
            "BJ430001", "2025-12-31", AS_OF, "cninfo", "a" * 64, "c" * 64,
            "discovery-v1", "n" * 64,
        )
        self.assertNotEqual(
            tuple(spec.idempotency_key for spec in before),
            tuple(spec.idempotency_key for spec in after),
        )
        enqueue_all(self.store, before)
        execute_queued_formal_work(fixture_dependencies(self.store), worker_id="worker-a")
        enqueue_all(self.store, after)
        replay = execute_queued_formal_work(fixture_dependencies_for_root("n" * 64), worker_id="worker-b")
        self.assertEqual(replay.remote_attempts, 3)
        self.assertEqual(replay.rebuilt_security_ids, ("BJ430001",))

    def test_verified_official_universe_sources_freeze_full_sh_sz_bj_universe(self):
        dependencies = fixture_dependencies(self.store)
        finalizer_id = enqueue_frozen_formal_universe(
            self.store,
            as_of_utc=AS_OF,
            upstream_generation="official-list-index-v1",
            registry_manifest_hash="m" * 64,
            registry_runtime_loader=dependencies.registry_runtime_loader,
            universe_request_resolver=fixture_universe_request_resolver(self.store),
        )
        summary = execute_queued_formal_work(dependencies, worker_id="worker-a")
        self.assertEqual(summary.remote_attempts, 3)
        frozen = self.store.get_formal_universe_snapshot_from_task(finalizer_id)
        self.assertEqual(
            tuple(source["exchange"] for source in self.store.list_formal_universe_sources(frozen["id"])),
            ("BJ", "SH", "SZ"),
        )
        self.assertEqual(frozen["universe_hash"], recompute_universe_hash_from_verified_raw(frozen["id"]))

    def test_universe_finalizer_rejects_rows_not_reparsed_from_verified_raw(self):
        dependencies = fixture_dependencies(self.store)
        finalizer_id = enqueue_frozen_formal_universe(
            self.store,
            as_of_utc=AS_OF,
            upstream_generation="official-list-index-v1",
            registry_manifest_hash="m" * 64,
            registry_runtime_loader=dependencies.registry_runtime_loader,
            universe_request_resolver=fixture_universe_request_resolver(self.store),
        )
        first = execute_queued_formal_work(dependencies, worker_id="worker-a", max_jobs=3)
        self.assertEqual(first.remote_attempts, 3)
        replace_fixture_listing_parser_rows_without_changing_raw_bytes("BJ")
        summary = execute_queued_formal_work(dependencies, worker_id="worker-a", max_jobs=1)
        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(self.store.get_formal_task(finalizer_id)["status"], "terminal_failed")
        self.assertIn("universe_raw_parser_binding", self.store.get_formal_task(finalizer_id)["error"]["code"])

    def test_date_only_universe_finalizer_replays_receipts_with_their_bound_calendar(self):
        dependencies = fixture_dependencies(self.store)
        calendar_task_id = enqueue_calendar_bootstrap(self.store, AS_OF, generation="calendar-v1")
        execute_queued_formal_work(dependencies, worker_id="calendar-worker", max_jobs=1)
        finalizer_id = enqueue_frozen_formal_universe(
            self.store, as_of_utc=AS_OF, upstream_generation="official-list-index-v1",
            registry_manifest_hash="m" * 64,
            registry_runtime_loader=dependencies.registry_runtime_loader,
            universe_request_resolver=date_only_universe_request_resolver(
                self.store, calendar_task_id=calendar_task_id
            ),
        )
        source_pass = execute_queued_formal_work(dependencies, worker_id="source-worker", max_jobs=3)
        self.assertEqual(source_pass.remote_attempts, 3)
        finalizer_pass = execute_queued_formal_work(
            dependencies, worker_id="finalizer-worker", max_jobs=1
        )
        self.assertEqual(finalizer_pass.remote_attempts, 0)
        self.assertEqual(self.store.get_formal_task(finalizer_id)["status"], "verified")

    def test_source_block_opens_only_that_source_circuit_and_other_security_continues(self):
        enqueue_all(self.store, (
            *formal_statement_task_specs("SZ000001", "2025-12-31", AS_OF, "cninfo", "a" * 64, "b" * 64, "discovery-v1", "m" * 64),
            *formal_statement_task_specs("SH600001", "2025-12-31", AS_OF, "sse", "a" * 64, "b" * 64, "discovery-v1", "m" * 64),
        ))
        dependencies = fixture_dependencies(
            self.store, blocked_sources={"cninfo": FormalSourceBlocked("HTTP 429")}
        )
        summary = execute_queued_formal_work(dependencies, worker_id="worker-a")
        self.assertIn("cninfo", summary.open_circuits)
        self.assertEqual(summary.verified_statement_count, 3)
        self.assertEqual(self.store.get_formal_source_circuit("cninfo")["state"], "open")

    def test_unapproved_registry_is_terminal_not_a_network_attempt(self):
        enqueue_all(self.store, formal_statement_task_specs("SZ000001", "2025-12-31", AS_OF, "cninfo", "a" * 64, "b" * 64, "discovery-v1", "m" * 64))
        summary = execute_queued_formal_work(unapproved_dependencies(self.store), worker_id="worker-a")
        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(summary.terminal_failed, 3)

    def test_date_only_task_cannot_reach_transport_before_calendar_prerequisite_verifies(self):
        calendar_task_id = enqueue_calendar_bootstrap(self.store, AS_OF, generation="calendar-v1")
        with self.assertRaisesRegex(CalendarBindingPending, "calendar"):
            fixture_context_resolver(self.store).resolve_date_only_market_context_before_calendar()
        first = execute_queued_formal_work(fixture_dependencies(self.store), worker_id="worker-a", max_jobs=1)
        self.assertEqual(first.remote_attempts, 1)  # bootstrap calendar only
        bound_request = fixture_context_resolver(self.store).resolve_date_only_market_context_after_calendar()
        dependent_specs = formal_context_task_specs(
            bound_request,
            calendar_prerequisite_task_id=calendar_task_id,
        )
        enqueue_all(self.store, dependent_specs)
        second = execute_queued_formal_work(fixture_dependencies(self.store), worker_id="worker-b")
        self.assertEqual(second.retryable_failed, 0)
        self.assertEqual(fixture_transport(self.store).date_only_request_count, 1)

    def test_lost_lease_after_verified_raw_receipt_replays_without_second_transport(self):
        task_ids = enqueue_all(self.store, formal_statement_task_specs(
            "SZ000001", "2025-12-31", AS_OF, "cninfo", "a" * 64, "b" * 64,
            "discovery-v1", "m" * 64,
        ))
        task_id = task_ids[0]
        first = execute_queued_formal_work(
            dependencies_that_lose_lease_after_raw_receipt(self.store), worker_id="worker-a", max_jobs=1
        )
        self.assertEqual(first.remote_attempts, 1)
        advance_fixture_clock_past_lease(self.store)
        second = execute_queued_formal_work(
            fixture_dependencies(self.store), worker_id="worker-b", max_jobs=1
        )
        self.assertEqual(second.remote_attempts, 0)
        self.assertEqual(second.verified_statement_count, 1)
        self.assertTrue(self.store.get_formal_task_snapshot_receipt(task_id))
~~~

- [ ] **Step 2: Run formal worker tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_deep_worker -v
~~~

Expected: FAIL because ashare_pipeline.formal_deep_worker does not exist.

- [ ] **Step 3: Implement task payloads, lease execution, retries, and incremental rebuild**

~~~python
class CalendarBindingPending(ValueError):
    pass

@dataclass(frozen=True)
class FormalStatementTaskPayload:
    security_id: str
    dataset: Literal["balance_sheet", "profit_sheet", "cash_flow_sheet"]
    report_period: str
    as_of_utc: str
    source: str
    request_version: str
    source_registry_hash: str
    mapping_registry_hash: str
    upstream_generation: str
    refresh_generation: str
    registry_manifest_hash: str
    relevant_registry_hashes: tuple[tuple[str, str], ...]
    calendar_prerequisite_task_id: str | None
    calendar_binding: VerifiedCalendarBinding | None

@dataclass(frozen=True)
class FormalContextTaskPayload:
    context_kind: Literal[
        "trading_calendar", "market_close", "security_state", "industry_snapshot",
        "regulatory_state", "event_calendar", "consensus_snapshot"
    ]
    scope_key: str
    security_id: str | None
    as_of_utc: str
    official_request: OfficialRequest
    source: str
    request_version: str
    upstream_generation: str
    refresh_generation: str
    registry_manifest_hash: str
    relevant_registry_hashes: tuple[tuple[str, str], ...]
    calendar_prerequisite_task_id: str | None
    calendar_binding: VerifiedCalendarBinding | None

@dataclass(frozen=True)
class FormalUniverseSourceTaskPayload:
    exchange: Literal["SH", "SZ", "BJ"]
    as_of_utc: str
    official_request: OfficialRequest
    source: str
    request_version: str
    upstream_generation: str
    refresh_generation: str
    registry_manifest_hash: str
    relevant_registry_hashes: tuple[tuple[str, str], ...]
    calendar_prerequisite_task_id: str | None
    calendar_binding: VerifiedCalendarBinding | None

@dataclass(frozen=True)
class FormalUniverseFinalizeTaskPayload:
    as_of_utc: str
    registry_manifest_hash: str
    source_task_ids: tuple[str, str, str]
    refresh_generation: str

@dataclass(frozen=True)
class FormalFeatureBuildTaskPayload:
    security_id: str
    as_of_utc: str
    template_id: str
    source_registry_hash: str
    mapping_registry_hash: str
    feature_registry_hash: str
    registry_manifest_hash: str
    source_snapshot_ids: tuple[str, ...]
    refresh_generation: str

@dataclass(frozen=True)
class FormalTaskSpec:
    kind: Literal[
        "formal_statement", "formal_context", "formal_universe_source",
        "formal_universe_finalize", "formal_feature_build",
    ]
    idempotency_key: str
    refresh_generation: str
    payload: Mapping[str, object]
    prerequisite_task_ids: tuple[str, ...] = ()

@dataclass(frozen=True)
class FormalRegistryRuntime:
    bundle: VerifiedRegistryBundle
    source_adapter: FormalOfficialSourceAdapter
    mapping_registry: SignedFinancialMappingRegistry
    feature_registry: SignedFormalFeatureRegistry

class FormalRegistryRuntimeLoader:
    def __init__(
        self, bundle_loader: FormalRegistryBundleLoader, *, transport: OfficialTransport,
        policies: Mapping[str, SourcePolicy], parsers: Mapping[str, OfficialDocumentParser],
        effective_time_resolver: EffectiveTimeResolver,
    ) -> None: ...

    def load(self, manifest_hash: str) -> FormalRegistryRuntime: ...

@dataclass(frozen=True)
class FormalUniverseSourceResolution:
    payload: FormalUniverseSourceTaskPayload
    prerequisite_task_ids: tuple[str, ...]

class SignedUniverseRequestResolver(Protocol):
    def resolve(
        self, *, exchange: Literal["SH", "SZ", "BJ"], as_of_utc: str,
        upstream_generation: str, runtime: FormalRegistryRuntime,
    ) -> FormalUniverseSourceResolution: ...

def derive_collection_refresh_generation(
    *, upstream_generation: str, registry_manifest_hash: str,
    relevant_registry_hashes: Mapping[str, str],
    calendar_selector: CalendarSelector | None = None,
    calendar_binding: VerifiedCalendarBinding | None = None,
) -> str: ...

@dataclass(frozen=True)
class FormalWorkerDependencies:
    store: StateStore
    snapshots: FormalSnapshotRepository
    registry_runtime_loader: FormalRegistryRuntimeLoader
    feature_store: FormalFeatureBundleStore
    context_repository: FormalContextRepository

@dataclass(frozen=True)
class FormalCollectionSummary:
    remote_attempts: int
    verified_statement_count: int
    frozen_universe_snapshot_ids: tuple[str, ...]
    retryable_failed: int
    terminal_failed: int
    feature_bundles_written: int
    open_circuits: tuple[str, ...]
    rebuilt_security_ids: tuple[str, ...]

def formal_statement_task_specs(
    security_id: str,
    report_period: str,
    as_of_utc: str,
    source: str,
    source_registry_hash: str,
    mapping_registry_hash: str,
    upstream_generation: str,
    registry_manifest_hash: str,
    calendar_prerequisite_task_id: str | None = None,
    calendar_binding: VerifiedCalendarBinding | None = None,
) -> tuple[FormalTaskSpec, ...]: ...

def formal_context_task_specs(
    request: FormalContextRequest,
    calendar_prerequisite_task_id: str | None = None,
) -> tuple[FormalTaskSpec, ...]: ...

def formal_universe_task_specs(
    *, as_of_utc: str, upstream_generation: str, runtime: FormalRegistryRuntime,
    universe_request_resolver: SignedUniverseRequestResolver,
) -> tuple[FormalTaskSpec, ...]: ...

def enqueue_frozen_formal_universe(
    store: StateStore, *, as_of_utc: str, upstream_generation: str,
    registry_manifest_hash: str, registry_runtime_loader: FormalRegistryRuntimeLoader,
    universe_request_resolver: SignedUniverseRequestResolver,
) -> str: ...

def execute_queued_formal_work(
    dependencies: FormalWorkerDependencies, *, worker_id: str, max_jobs: int | None = None
) -> FormalCollectionSummary: ...
~~~

The idempotency key for a formal statement, context, universe-source, universe-finalize, or feature-build task follows the V5 canonical fields only: kind, security ID, category, report period or market date, source, freeze instant, request version, and refresh_generation. Prerequisite task IDs are stored and replay-checked as immutable edges rather than hashed into the key. formal_statement_task_specs, formal_context_task_specs, and formal_universe_task_specs never accept a completed task generation from a caller: they accept an authoritative upstream_generation and calculate refresh_generation with derive_collection_refresh_generation. For every timestamp-only or date-only collection task, including one exchange-scoped global universe_listing request per SH/SZ/BJ exchange, that hash includes upstream_generation, registry_manifest_hash, and the exact relevant root-role hashes; a date-only task additionally includes its canonical signed selector and every immutable VerifiedCalendarBinding field (snapshot manifest, exchange, freeze, root, selector, and prerequisite task). The universe-finalize generation is the canonical SHA-256 of its root manifest, freeze, and sorted three source-task IDs/generations. The typed payload retains both upstream_generation and resulting refresh_generation, and the worker recomputes the result from the loaded bundle before any receipt reuse or transport. Thus a changed source/mapping/root configuration cannot parse or reuse a prior task's raw receipt under new rules, even if the discovery generation is unchanged. A feature-build refresh_generation is the canonical SHA-256 of the sorted selected financial-statement snapshot IDs, their selected refresh generations, their content hashes, selected financial fact IDs, and the root registry manifest hash. Market/industry/policy contexts are deliberately not V6 feature-bundle inputs: V7 owns their dependency tracking and score-run rebuild. An equal generation reuses its verified task; a changed generation creates a new task and invokes supersede_formal_tasks only for unfinished older-generation tasks in the same logical scope. FormalTaskSpec carries the same generation and prerequisite_task_ids passed to enqueue_formal_task; the worker rejects a mismatch between the typed payload, task row, canonical payload hash, or stored dependency edges. formal_statement_task_specs must emit the three statement datasets in fixed lexical order and must not use legacy JobSpec or a prefilter candidate set. formal_universe_task_specs receives only a preloaded FormalRegistryRuntime and a SignedUniverseRequestResolver; it never accepts a source name, endpoint, parser, request version, root-role hash map, calendar prerequisite map, or calendar-binding map from its caller. enqueue_frozen_formal_universe first loads the requested root through FormalRegistryRuntimeLoader, requires the loaded manifest hash to equal its registry_manifest_hash argument and require_official to pass, then calls that spec builder. The resolver is constructed from the verified bundle plus the persisted calendar/context repositories. For each of BJ, SH, and SZ it obtains exactly one eligible signed universe_listing SourceAdapterConfig, requires a global null-security request and an exact matching exchange scope, derives the OfficialRequest, parser/source identity, relevant root-role tuple, and refresh generation solely from that signed configuration, and returns FormalUniverseSourceResolution. For a date-only configuration it also resolves the signed CalendarSelector to the one matching verified calendar context/source snapshot under the same root, returns that prerequisite task ID and immutable VerifiedCalendarBinding, and raises CalendarBindingPending rather than fabricating either value; for a timestamp-only configuration both the prerequisite task ID and calendar_binding are null. The returned payload's calendar_prerequisite_task_id must exactly equal its sole prerequisite edge when nonnull, and its calendar_binding.prerequisite_task_id, exchange, freeze, root, selector, and manifest must exactly match that edge and signed configuration; otherwise both edge and binding must be absent. A resolver rejects an aggregate multi-exchange listing configuration, ambiguous/absent signed configuration, a root/role mismatch, or a calendar binding from another root. formal_universe_task_specs emits exactly those three source requests in lexical BJ/SH/SZ order, then one finalizer whose immutable prerequisite edges are their task IDs. The scheduling coordinator first enqueues the exact trading-calendar bootstrap task and receives its task ID. After the bootstrap is verified, the resolver may bind date-only configurations to that calendar; no downstream task is leaseable before that edge verifies. enqueue_frozen_formal_universe enqueues those source/finalize specs before financial scoring work and returns the finalizer ID; V7 cannot start without its verified frozen-universe result. formal_context_task_specs then requests the frozen industry, regulatory, event, and consensus contexts in deterministic context-kind/scope/security order.

At the beginning of each worker pass, call resolve_formal_task_dependencies; a task with an unverified calendar prerequisite is not leaseable, and a task whose prerequisite is terminal_failed or superseded is terminal_failed with prerequisite_terminal_failed before any transport call. FormalRegistryRuntimeLoader re-loads and re-hashes the verified bundle, then constructs the signed source adapter, mapping registry, and feature registry solely from the matching source/mapping/feature blobs plus injected transport, policies, parsers, and effective-time resolver; it rejects any compiled/runtime role hash that differs from the bundle. For every leased formal task, including feature-build and universe-finalize, load runtime = dependencies.registry_runtime_loader.load(payload.registry_manifest_hash) outside a database transaction. Require runtime.bundle.manifest.manifest_hash to equal the payload hash and reject any standalone source adapter, mapping, or feature registry. For statement/context/universe-source collection, verify each typed relevant role/hash against the loaded root bundle and recompute payload.refresh_generation from payload.upstream_generation, the loaded root/relevant-role hashes, and any bound calendar selector/VerifiedCalendarBinding (including its manifest, root, exchange, freeze, and prerequisite task) before considering a receipt; a mismatch is terminal_failed with zero transport. For an official collection invocation call runtime.bundle.require_official. A feature-build task then requires its source/mapping/feature registry hashes to match runtime.bundle, loads only persisted V6 financial facts/snapshots, and passes runtime.feature_registry into build_formal_feature_bundle; it has no OfficialRequest, calendar binding, raw snapshot receipt, or transport call. A universe-finalize task has no transport: it reads only its three prerequisite receipts and verified raw files.

For a leased statement, context, or universe-source task, check source registry approval, source circuit state, and for a date-only-capable configuration require payload.calendar_binding to be revalidated through FormalContextRepository.resolve_verified_calendar_binding against the signed selector, resolved OfficialRequest exchange, as_of_utc, root, and exact prerequisite edge; require its manifest_sha256 to equal the selected formal_source_snapshot manifest. Timestamp-only configurations require both binding and calendar prerequisite edge to be null. An absent/invalid runtime, parser, mapping, source policy, calendar edge/binding, or identity is terminal_failed with a machine-readable reason and zero network attempt. Before transport, look up get_formal_task_snapshot_receipt(leased_task_id). If a receipt exists, re-read its OfficialSnapshotRef by manifest SHA through FormalSnapshotRepository, re-read verified raw bytes, and call runtime.source_adapter.parse_verified_snapshot(ref, raw_bytes, calendar_binding=payload.calendar_binding); it must make zero network requests. If no receipt exists, construct the request from the typed payload, call runtime.source_adapter.fetch_verified(request, refresh_generation=payload.refresh_generation, calendar_binding=payload.calendar_binding), then call FormalSnapshotRepository.persist_verified(fetch, verification, producing_task_id=leased_task_id, worker_id=worker_id) to atomically record the raw receipt while this lease is owned. Before writing facts/context and again before final completion, renew/check the lease owner; after a lost lease write no further facts/context or completion, so the next owner recovers from the receipt. For a statement snapshot, extract facts with runtime.mapping_registry, write facts through V6, and enqueue the affected security's financial feature-build task idempotently. For a context snapshot, normalize exactly one FormalContextFact per declared context identity with the payload refresh_generation and write it through V6; it does not enqueue a V6 feature build because V7 score-run input manifests own all context references and refresh generations. For a universe-source snapshot, require the signed dataset to be universe_listing, request.security_id and declared_security_id to be null, request.exchange to equal the payload exchange, and the parser to expose explicit security_type/listing_status rows. Before completing it, persist an immutable canonical result containing the receipt snapshot ID/manifest, source content hash, parser ID/version, canonical rows hash, declared exchange, payload registry_manifest_hash, and payload refresh_generation; each must agree with the stored task payload and raw receipt. A later unrecoverable fact/context/universe schema failure calls fail_formal_task with its raw snapshot receipt retained for audit; only a successful downstream source path calls complete_formal_task with the receipt identity.

For a leased universe-finalize task, perform zero transport. Require exactly the three dependency task IDs in canonical BJ/SH/SZ exchange order, each a verified formal_universe_source task with a verified raw receipt, and require each source task payload/result registry_manifest_hash to equal the finalizer payload registry_manifest_hash. For every receipt, re-read that source task's typed FormalUniverseSourceTaskPayload, require its root/exchange/prerequisite edge to match the finalizer and stored dependency, revalidate its calendar_binding through FormalContextRepository when date-only (or require both binding and edge null when timestamp-only), re-read its snapshot by manifest and verified bytes, then call the same loaded signed universe_listing adapter.parse_verified_snapshot(ref, raw_bytes, calendar_binding=source_payload.calendar_binding). Require its parser ID/version, source content hash, declared exchange, effective-time evidence hash/binding manifest when date-only, and canonical parsed-row hash to equal the immutable parsed-document result recorded by that source task. Build three FormalUniverseSourceDocument values only from those re-parsed bytes, call FormalUniverseIngestor.build(payload.as_of_utc, payload.registry_manifest_hash, documents), and call StateStore.put_formal_universe_snapshot(frozen_input). The store rechecks the three source tasks' receipts/payload roots as well as source/extraction/member hashes, then atomically writes or recovers the one frozen-input snapshot, three source links, all members, and the initial full status ledger. Record the returned universe snapshot ID, frozen_input_hash, universe_hash, and registry_manifest_hash in the finalizer result and complete it only after renewing the lease. A parser/raw/calendar-binding mismatch, root mismatch, missing exchange, unknown type, source-audit mismatch, or conflicting existing frozen input is terminal_failed with code universe_raw_parser_binding or universe_incomplete and creates no partial universe snapshot. If a process crashed after the atomic universe insert but before task completion, the next owner recomputes the identical frozen input, obtains it by frozen_input_hash, and completes the same finalizer without transport.

Map a FormalSourceBlocked result, HTTP 403, HTTP 429, CAPTCHA marker, or challenge-page parse result to retryable_failed and set the matching formal_source_circuit to open using the signed source registry's cooldown. Map FormalRetryableSourceError, a timeout, or a temporary empty response to retryable_failed using the signed registry's finite retry delay. Map FormalTerminalSourceError, a malformed verified document, source/policy mismatch, invalid signed configuration, or an unrecoverable fact schema violation to terminal_failed. The worker must continue leasing other source/security tasks after one failure and must not sleep while holding a transaction.

For a feature-build task, load only V6 financial facts and verified financial-statement snapshots visible at its as_of_utc, select versions through FormalFactVersionView, derive quarters, enforce history, build the formal bundle, write it atomically, and persist it through V6. Reuse an existing verified identical snapshot and identical bundle input without a remote fetch or duplicate bundle write. The formal feature bundle input hash must contain the exact root registry manifest hash, child registry hashes, selected financial-statement snapshot IDs/content hashes/refresh generations, selected financial fact IDs, selected quarter IDs, template ID, and as_of_utc. It must not include market, industry, regulatory, event, consensus, or calendar context; V7 separately fingerprints those inputs in its score-run manifest. If a financial-statement snapshot content hash or generation changes under a new authoritative refresh generation, rebuild only the corresponding security's facts, quarters, and feature bundle; never rewrite another security's bundle. A feature registry that is structurally valid but not release eligible must write a blocked feature bundle with its explicit blocker so the universe can remain pending_evidence.

- [ ] **Step 4: Run worker, persistence, and full regression suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_deep_worker tests.test_formal_financial_features tests.test_formal_sources tests.test_state_store -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
~~~

Expected: PASS; all formal tests run without network access and all legacy V1/V2 tests remain green.

- [ ] **Step 5: Commit the resumable formal worker**

~~~powershell
git add -- ashare_pipeline/formal_deep_worker.py tests/test_formal_deep_worker.py
git commit -m "feat: add resumable formal financial collection"
~~~

## Plan Self-Review

- Spec coverage: Task 1 covers authoritative-source transport isolation, original bytes, parser/source identity, root registry binding, and a fail-closed signed source boundary from sections 4.1, 4.2, and 5. Task 2 covers normalized official financial facts and evidence lineage. Tasks 3 and 5A establish immutable, signed, configuration-driven feature inputs and a verified typed-bundle boundary with no default production metrics. Task 4 implements the V3 15:00 visibility rule, exact Chinese cumulative-quarter conversion, four/five annual endpoint gates, eight-quarter prerequisite handling, and point-in-time derivation from sections 3.1 and 6.1. Task 5 makes facts, quarters, registry blobs/manifests, feature bundles, source circuits, and formal leases durable through V6. Task 5B assigns market, calendar, industry, regulatory, event, and consensus evidence to typed official collection and persistence. Task 6 implements the incremental/restart/circuit/context requirements in section 5 and the database/recovery verification required by section 10.
- Intentional release gate: The approved V3 contract does not provide signed production endpoint definitions, document parsers, raw-field mappings, five-template equivalences, or the complete scoring registry. The plan implements their verified loading and explicit blocked outcomes; no code path may promote a fixture or third-party response to official production evidence.
- Placeholder scan: The plan names every created class, table, method, task state, storage path, test module, and test command. There are no unspecified error-handling steps or unnamed implementation components.
- Type consistency: Task 1 produces ParsedOfficialDocument, OfficialFetch, VerifiedCalendarBinding, EffectiveTimeResolver, and FormalRegistryManifest; Task 2 turns them into FormalFinancialFact; Tasks 3 and 5A define/retrieve a verified FormalFeatureBundle and its evidence references; Task 4 consumes those exact types to derive quarters and feature values; Task 5 persists the types and formal lease states; Task 5B produces verified FormalContextFact; Task 6 is the only collection orchestrator that combines them.
- Scope boundary: Peer percentiles, five-template score weights, C/S0/Sc/B/R calculations, redline/cycle/pool policy, release validation, and reports are deliberately owned by the separate scoring and release plans. This plan creates auditable inputs for them but cannot by itself produce a formal score, pool, or official release.
