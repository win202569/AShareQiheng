# Formal V3 Evidence and Universe Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build an isolated, official-evidence and full-A-share universe foundation for the V3 formal release without changing the legacy V1/V2 prefilter pipeline.

**Architecture:** Add a parallel Formal V3 domain: byte-preserving official snapshots, source-policy verification, a 15:00 Asia/Shanghai time contract, and a full SH/SZ/BJ universe status model. Persist it through an additive SQLite v5 migration; legacy source_snapshot, job, financial_fact, feature-contract-v1, and score_item remain readable but can never become formal evidence.

**Tech Stack:** Python 3.12, Python standard library, SQLite, unittest, existing project SnapshotStore only for legacy data.

**Spec:** docs/superpowers/specs/2026-09-04-formal-scoring-release-contract-design.md

## Global Constraints

- Freeze time is exactly 2026-08-31T15:00:00+08:00; formal code must not reuse legacy 23:59:59 cutoff logic.
- Formal A-share identity accepts SH, SZ, and BJ followed by six digits; B shares, funds, ETFs, bonds, convertibles, and REITs are out of scope.
- Formal evidence must preserve original bytes, original URL, source time precision, parser/mapping version, and verification result.
- AkShare and BaoStock may remain discovery or cross-check sources but must never receive verified formal evidence status.
- A document captured after the freeze can support replay only when published_at and effective_at are independently proven not later than the freeze.
- Every security has exactly one universe_status: out_of_scope, pending_evidence, pool_vetoed, or formal_scored; the priority is listed in the approved spec.
- Preserve all existing data and legacy tables. Do not stage data, SQLite, WAL/SHM, or data/status/pipeline_status.json in code commits.
- Unit tests are hermetic and must inject fake transports; do not require network access.

---

## File Structure

| File | Responsibility |
|---|---|
| ashare_pipeline/formal_evidence.py | Immutable official request/fetch/reference types and source-policy verification |
| ashare_pipeline/formal_snapshot_store.py | Byte-preserving content-addressed raw storage and manifest verification |
| ashare_pipeline/formal_snapshot_repository.py | Formal snapshot persistence, exact lookup, and StateStore integration |
| ashare_pipeline/formal_time.py | Formal 15:00 cutoff, date-only effective time, and deterministic version sort keys |
| ashare_pipeline/formal_universe.py | SH/SZ/BJ identities, universe hash, and mutually exclusive status classification |
| ashare_pipeline/state_store.py | Additive SQLite v5 formal snapshot, task, universe, and status tables plus APIs |
| tests/test_formal_evidence.py | Source-policy, identity, URL, timestamp, and third-party rejection tests |
| tests/test_formal_snapshot_store.py | Raw byte, manifest, hash, and atomic-write tests |
| tests/test_formal_snapshot_repository.py | Repository persistence and exact verified lookup tests |
| tests/test_formal_time.py | Freeze visibility and deterministic sort tests |
| tests/test_formal_universe.py | BJ identity, status priority, duplicate, and hash tests |
| tests/test_state_store.py | v4-to-v5 migration and formal-table persistence tests |

### Task 1: Official Evidence Contract and Source Policy

**Files:**
- Create: ashare_pipeline/formal_evidence.py
- Create: tests/test_formal_evidence.py

**Interfaces:**
- Produces OfficialRequest, OfficialFetch, EvidenceVerification, VerifiedCalendarBinding, OfficialSnapshotRef, SourcePolicy, and verify_official_fetch(fetch, policy, *, calendar_binding: VerifiedCalendarBinding | None = None).
- Consumes only bytes, dataclasses, hashlib, urllib.parse, and timezone-aware ISO timestamps.
- SourcePolicy.verify must return an EvidenceVerification object; it must not raise a third-party fetch into verified status.

- [ ] **Step 1: Write the failing evidence tests**

~~~python
import unittest

from ashare_pipeline.formal_evidence import (
    OfficialFetch, OfficialRequest, SourcePolicy, verify_official_fetch,
)


class FormalEvidenceTests(unittest.TestCase):
    def test_verified_cninfo_pdf_requires_allowlisted_url_identity_and_timestamp(self):
        fetch = OfficialFetch(
            request=OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31"),
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
        result = verify_official_fetch(fetch, SourcePolicy.cninfo())
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.content_sha256, fetch.content_sha256)

    def test_third_party_and_wrong_host_cannot_be_verified(self):
        request = OfficialRequest("akshare", "daily", "SZ000001", "2026-08-31")
        third_party = OfficialFetch.minimal(
            request, b"rows", "https://example.invalid/rows",
            "2026-08-31T07:00:00+00:00", "timestamp", refresh_generation="fixture-index-v1",
        )
        result = verify_official_fetch(third_party, SourcePolicy.cninfo())
        self.assertEqual(result.status, "rejected")
        self.assertIn("source_not_authoritative", result.reasons)

    def test_future_publication_is_not_visible_even_if_captured_later(self):
        fetch = OfficialFetch.minimal(
            OfficialRequest("cninfo", "halfyear_report", "SZ000001", "2026-06-30"),
            b"report", "https://www.cninfo.com.cn/new/disclosure/detail",
            "2026-08-31T07:01:00+00:00", "timestamp", refresh_generation="fixture-index-v1",
        )
        result = verify_official_fetch(fetch, SourcePolicy.cninfo())
        self.assertEqual(result.status, "verified")
        self.assertFalse(result.visible_at("2026-08-31T07:00:00+00:00"))

    def test_date_only_fetch_rejects_a_different_verified_calendar_binding(self):
        binding = verified_calendar_binding(
            manifest_sha256="c" * 64, exchange="SZ",
            freeze_at_utc="2026-08-31T07:00:00+00:00", registry_manifest_hash="r" * 64,
        )
        fetch = date_only_fetch(
            exchange="SZ", effective_time_evidence_hash=binding.manifest_sha256,
        )
        self.assertEqual(
            verify_official_fetch(fetch, SourcePolicy.cninfo(), calendar_binding=binding).status,
            "verified",
        )
        other_verified_calendar = verified_calendar_binding(
            manifest_sha256="d" * 64, exchange="SZ",
            freeze_at_utc=binding.freeze_at_utc, registry_manifest_hash=binding.registry_manifest_hash,
        )
        rejected = verify_official_fetch(
            fetch, SourcePolicy.cninfo(), calendar_binding=other_verified_calendar,
        )
        self.assertEqual(rejected.status, "rejected")
        self.assertIn("calendar_binding_mismatch", rejected.reasons)
~~~

- [ ] **Step 2: Run the new tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence -v
~~~

Expected: FAIL because ashare_pipeline.formal_evidence does not exist.

- [ ] **Step 3: Implement immutable evidence types and verification**

~~~python
@dataclass(frozen=True)
class OfficialRequest:
    source: str
    dataset: str
    security_id: str | None
    period_or_date: str | None
    exchange: Literal["SH", "SZ", "BJ"] | None = None

    def canonical_json_bytes(self) -> bytes: ...

    @property
    def request_fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json_bytes()).hexdigest()

@dataclass(frozen=True)
class OfficialFetch:
    request: OfficialRequest
    raw_bytes: bytes
    original_url: str
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    source_updated_at_utc: str | None
    captured_at_utc: str
    effective_at_utc: str
    effective_time_evidence_hash: str | None
    refresh_generation: str
    parser_id: str
    parser_version: str
    mapping_version: str
    declared_security_id: str | None
    declared_period: str | None

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()

@dataclass(frozen=True)
class EvidenceVerification:
    status: Literal["verified", "rejected"]
    content_sha256: str
    reasons: tuple[str, ...]
    def visible_at(self, as_of_utc: str) -> bool: ...

@dataclass(frozen=True)
class VerifiedCalendarBinding:
    snapshot_id: str
    manifest_sha256: str
    exchange: Literal["SH", "SZ", "BJ"]
    freeze_at_utc: str
    registry_manifest_hash: str
    selector_hash: str
    prerequisite_task_id: str

@dataclass(frozen=True)
class OfficialSnapshotRef:
    snapshot_id: str
    source: str
    dataset: str
    request_fingerprint: str
    security_id: str | None
    period_or_date: str | None
    exchange: Literal["SH", "SZ", "BJ"] | None
    content_sha256: str
    manifest_sha256: str
    content_path: str
    manifest_path: str
    original_url: str
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    source_updated_at_utc: str | None
    captured_at_utc: str
    effective_at_utc: str
    effective_time_evidence_hash: str | None
    refresh_generation: str
    producing_task_id: str | None
    parser_id: str
    parser_version: str
    mapping_version: str
    verification_status: Literal["verified"]
~~~

Implement SourcePolicy.cninfo(), SourcePolicy.sse(), SourcePolicy.szse(), SourcePolicy.bse(), and SourcePolicy.csrc() with a non-empty authoritative source name and allowlisted HTTPS host names. verify_official_fetch must reject a non-policy source, non-HTTPS URL, off-list host, invalid identity, naive timestamps, an effective time earlier than publication, an empty payload, or an empty parser_id/parser_version. It recomputes OfficialRequest.request_fingerprint from canonical request JSON whenever evidence is persisted or re-read. For a date-only publication it requires a nonnull VerifiedCalendarBinding whose manifest_sha256 exactly equals fetch.effective_time_evidence_hash, whose exchange exactly equals the resolved request exchange, and whose freeze/root/selector/task fields have already been validated by the context resolver; an arbitrary 64-hex string is never a binding. A timestamp publication requires both effective_time_evidence_hash and calendar_binding to be null. Store rejection reasons in sorted deterministic order.

- [ ] **Step 4: Run evidence tests and the existing source tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence tests.test_sources -v
~~~

Expected: PASS; existing FetchBatch behavior is unchanged.

- [ ] **Step 5: Commit the contract**

~~~powershell
git add -- ashare_pipeline/formal_evidence.py tests/test_formal_evidence.py
git commit -m "feat: add formal official evidence contract"
~~~

### Task 2: Byte-Preserving Formal Snapshot Store

**Files:**
- Create: ashare_pipeline/formal_snapshot_store.py
- Create: tests/test_formal_snapshot_store.py

**Interfaces:**
- Consumes OfficialFetch and EvidenceVerification from Task 1.
- Produces FormalStoredSnapshot with content_path, manifest_path, content_sha256, and manifest_sha256.
- FormalSnapshotStore.write_verified(fetch, verification, *, producing_task_id: str | None) must write raw bytes without JSON re-encoding and carries task provenance only in the immutable manifest envelope.

- [ ] **Step 1: Write failing raw-storage tests**

~~~python
class FormalSnapshotStoreTests(unittest.TestCase):
    def test_binary_bytes_round_trip_without_json_reencoding(self):
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch(raw_bytes=b"%PDF\x00\xff\n")
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            self.assertEqual(store.read_verified_raw(stored), b"%PDF\x00\xff\n")
            self.assertEqual(stored.content_sha256, sha256(b"%PDF\x00\xff\n").hexdigest())

    def test_tampered_manifest_or_content_is_rejected_and_part_file_is_cleaned(self):
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            fetch = verified_fetch()
            stored = store.write_verified(fetch, verified(fetch), producing_task_id=None)
            Path(stored.content_path).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "content hash"):
                store.read_verified_raw(stored)
            self.assertFalse(list(Path(root).rglob("*.part")))

    def test_same_bytes_in_new_generation_reuses_bin_but_keeps_two_manifests(self):
        with tempfile.TemporaryDirectory() as root:
            store = FormalSnapshotStore(root)
            first_fetch = verified_fetch(refresh_generation="index-v1")
            second_fetch = verified_fetch(refresh_generation="index-v2")
            first = store.write_verified(first_fetch, verified(first_fetch), producing_task_id=None)
            second = store.write_verified(second_fetch, verified(second_fetch), producing_task_id=None)
            self.assertEqual(first.content_path, second.content_path)
            self.assertNotEqual(first.manifest_sha256, second.manifest_sha256)
            self.assertNotEqual(first.manifest_path, second.manifest_path)
            self.assertEqual(store.read_verified_raw(first), store.read_verified_raw(second))
~~~

- [ ] **Step 2: Run the storage tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_snapshot_store -v
~~~

Expected: FAIL because FormalSnapshotStore is undefined.

- [ ] **Step 3: Implement content and manifest atomic writes**

Write raw content at:

~~~text
data/raw/formal/<source>/<dataset>/<sha256>.bin
data/raw/formal/<source>/<dataset>/<manifest_sha256>.manifest.json
~~~

Raw .bin files are content-addressed and may be shared only when their bytes have the same content SHA-256. Manifests are lineage-addressed: canonicalize a manifest payload containing every OfficialFetch field (including refresh_generation), verification status/reasons, optional producing_task_id, and content SHA-256; calculate manifest_sha256 over that payload excluding the envelope's manifest_sha256 field; then write one canonical envelope named by that hash. This avoids a self-hash and preserves distinct immutable provenance when identical source bytes are re-collected in a later generation or task. Use a sibling file ending in .part, flush and fsync it, validate bytes against OfficialFetch.content_sha256, then replace it atomically. read_verified_raw must re-read the selected .bin and selected manifest envelope, recompute both hashes, require the named manifest hash to match the canonical payload, and reject a non-verified manifest. It must never select a manifest merely by content SHA.

- [ ] **Step 4: Run the focused storage suite**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_snapshot_store tests.test_snapshot_store -v
~~~

Expected: PASS; legacy SnapshotStore remains independent.

- [ ] **Step 5: Commit the formal raw store**

~~~powershell
git add -- ashare_pipeline/formal_snapshot_store.py tests/test_formal_snapshot_store.py
git commit -m "feat: add byte-preserving formal snapshot store"
~~~

### Task 3: Formal Time and Full-Universe Pure Contract

**Files:**
- Create: ashare_pipeline/formal_time.py
- Create: ashare_pipeline/formal_universe.py
- Create: tests/test_formal_time.py
- Create: tests/test_formal_universe.py

**Interfaces:**
- formal_time exports market_close_as_of, resolve_effective_at, is_visible_at, and formal_version_sort_key.
- formal_universe exports canonical_security_id, FormalUniverseMember, FormalUniverseDecision, FormalUniverseSourceAudit, FormalUniverseExtraction, FormalUniverseSourceEvidence, FormalUniverseSourceDocument, FormalFrozenUniverseInput, FormalUniverseIngestor, extract_formal_universe_members, build_universe_snapshot, and classify_universe_status.
- build_universe_snapshot returns members sorted by security_id and a SHA-256 over canonical JSON.

- [ ] **Step 1: Write failing time and universe tests**

~~~python
class FormalTimeTests(unittest.TestCase):
    def test_date_only_same_day_is_not_visible_at_close_but_prior_day_is(self):
        close = market_close_as_of("2026-08-31")
        self.assertFalse(is_visible_at(resolve_effective_at("2026-08-31", "date_only"), close))
        self.assertTrue(is_visible_at(resolve_effective_at("2026-08-28", "date_only"), close))

    def test_version_order_is_published_desc_updated_desc_captured_desc_hash_asc(self):
        rows = [row("b" * 64), row("a" * 64)]
        self.assertEqual([row.content_hash for row in sorted(rows, key=formal_version_sort_key)], ["a" * 64, "b" * 64])

class FormalUniverseTests(unittest.TestCase):
    def test_bj_identity_and_status_priority(self):
        self.assertEqual(canonical_security_id("bj430001"), "BJ430001")
        self.assertEqual(
            classify_universe_status(in_scope=True, evidence_complete=False, veto_flags=("ST",)),
            "pending_evidence",
        )
        self.assertEqual(
            classify_universe_status(in_scope=True, evidence_complete=True, veto_flags=("ST",)),
            "pool_vetoed",
        )

    def test_official_listing_extraction_keeps_sh_sz_bj_and_audits_explicit_exclusions(self):
        extracted = extract_formal_universe_members(
            listing_document(
                exchange="BJ",
                rows=(
                {"security_id": "BJ430001", "security_type": "ordinary_a", "listing_status": "listed"},
                {"security_id": "BJ899001", "security_type": "bond", "listing_status": "listed"},
                ),
            )
        )
        self.assertEqual([member.security_id for member in extracted.members], ["BJ430001"])
        self.assertEqual(extracted.audit.excluded_by_security_type, (("bond", 1),))
        with self.assertRaisesRegex(ValueError, "unknown security_type"):
            extract_formal_universe_members(
                listing_document(
                    exchange="SZ",
                    rows=({"security_id": "SZ000001", "listing_status": "listed"},),
                )
            )

    def test_ingestor_requires_three_verified_exchange_scoped_documents(self):
        frozen = FormalUniverseIngestor().build(
            FORMAL_FREEZE_AT_CN, "m" * 64, verified_listing_documents_for("SH", "SZ", "BJ")
        )
        self.assertEqual(tuple(source.exchange for source in frozen.sources), ("BJ", "SH", "SZ"))
        with self.assertRaisesRegex(ValueError, "SH/SZ/BJ"):
            FormalUniverseIngestor().build(
                FORMAL_FREEZE_AT_CN, "m" * 64, verified_listing_documents_for("SH", "SZ")
            )
~~~

- [ ] **Step 2: Run the new tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_time tests.test_formal_universe -v
~~~

Expected: FAIL because the formal modules do not exist.

- [ ] **Step 3: Implement the formal time and universe functions**

Use:

~~~python
FORMAL_FREEZE_AT_CN = "2026-08-31T15:00:00+08:00"

def canonical_security_id(value: str) -> str:
    normalized = value.strip().upper()
    if not re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", normalized):
        raise ValueError("formal security id must be SH/SZ/BJ plus six digits")
    return normalized

def classify_universe_status(*, in_scope: bool, evidence_complete: bool, veto_flags: tuple[str, ...]) -> str:
    if not in_scope:
        return "out_of_scope"
    if not evidence_complete:
        return "pending_evidence"
    if veto_flags:
        return "pool_vetoed"
    return "formal_scored"

@dataclass(frozen=True)
class FormalUniverseSourceAudit:
    exchange: Literal["SH", "SZ", "BJ"]
    source_content_sha256: str
    parser_id: str
    parser_version: str
    source_row_count: int
    accepted_ordinary_a_count: int
    excluded_by_security_type: tuple[tuple[str, int], ...]
    parsed_rows_hash: str
    accepted_members_hash: str
    excluded_rows_hash: str
    audit_hash: str

@dataclass(frozen=True)
class FormalUniverseExtraction:
    exchange: Literal["SH", "SZ", "BJ"]
    members: tuple[FormalUniverseMember, ...]
    audit: FormalUniverseSourceAudit

@dataclass(frozen=True)
class FormalUniverseSourceEvidence:
    exchange: Literal["SH", "SZ", "BJ"]
    snapshot: OfficialSnapshotRef
    extraction: FormalUniverseExtraction

@dataclass(frozen=True)
class FormalUniverseSourceDocument:
    exchange: Literal["SH", "SZ", "BJ"]
    snapshot: OfficialSnapshotRef
    parser_id: str
    parser_version: str
    parsed_rows: tuple[Mapping[str, object], ...]

@dataclass(frozen=True)
class FormalFrozenUniverseInput:
    as_of_utc: str
    registry_manifest_hash: str
    members: tuple[FormalUniverseMember, ...]
    sources: tuple[FormalUniverseSourceEvidence, ...]
    universe_hash: str
    source_audit_hash: str
    frozen_input_hash: str

class FormalUniverseIngestor:
    def build(
        self, as_of_utc: str, registry_manifest_hash: str,
        documents: Sequence[FormalUniverseSourceDocument]
    ) -> FormalFrozenUniverseInput: ...

def extract_formal_universe_members(
    document: FormalUniverseSourceDocument,
) -> FormalUniverseExtraction: ...
~~~

resolve_effective_at must assign date-only disclosures 23:59:59 Asia/Shanghai and move their effective time to the next exchange trading close passed by the caller. formal_version_sort_key must implement published descending, source_updated descending with null last, captured descending, content hash ascending. extract_formal_universe_members accepts one FormalUniverseSourceDocument, derives exchange/content hash/parser identity only from that document, and accepts only rows from its declared exchange. It requires a canonical matching SH/SZ/BJ security ID, explicit known security_type, and explicit listing_status on every row. It accepts only ordinary_a members; B shares, funds, ETFs, bonds, convertibles, REITs, and any other registry-recognized non-A type are excluded only with a deterministic audit count. A missing/unknown type, duplicate security ID, wrong exchange prefix, malformed row, or zero accepted ordinary-A members is a collection error rather than a silent filter. It preserves accepted raw row JSON in FormalUniverseMember and returns a canonical audit hash over source_content_sha256, parser ID/version, canonical parsed-row hashes, canonical accepted-member/raw-row hashes, and canonical excluded-row hashes/counts; counts alone are never sufficient. FormalUniverseIngestor is the only production ingress from official listing documents: it accepts exactly one verified OfficialSnapshotRef plus parser ID/version and parsed rows for each SH/SZ/BJ exchange, requires each ref to be global (security_id null), exchange-scoped, verified, and visible at as_of_utc, requires the document parser ID and version to exactly match the snapshot, calls extract_formal_universe_members for each, rejects cross-exchange duplicates, and emits a FormalFrozenUniverseInput whose universe_hash includes all sorted members and audit hashes, whose source_audit_hash includes all three source manifest/content/parser/extraction pairs, and whose frozen_input_hash is the canonical SHA-256 of freeze, root registry manifest, universe hash, and every source manifest/extraction hash. build_universe_snapshot requires the union of those three nonempty extractions; callers may not construct a frozen universe from bare member rows in production.

- [ ] **Step 4: Run the focused suite**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_time tests.test_formal_universe tests.test_curation -v
~~~

Expected: PASS; legacy SH/SZ-only curation tests remain unchanged.

- [ ] **Step 5: Commit the pure formal domain**

~~~powershell
git add -- ashare_pipeline/formal_time.py ashare_pipeline/formal_universe.py tests/test_formal_time.py tests/test_formal_universe.py
git commit -m "feat: add formal time and universe contracts"
~~~

### Task 4: Additive SQLite V5 Formal Evidence and Universe Tables

**Files:**
- Modify: ashare_pipeline/state_store.py: schema constants, initialize, migrations, and public APIs
- Modify: tests/test_state_store.py: migration fixtures and StateStore tests
- Create: tests/fixtures/schema_v4.sql

**Interfaces:**
- Produces StateStore.put_formal_snapshot, put_formal_snapshot_for_leased_task, get_formal_task_snapshot_receipt, put_formal_universe_snapshot, get_formal_universe_snapshot_by_input_hash, get_formal_universe_snapshot_from_task, list_formal_universe_sources, replace_formal_universe_statuses, list_formal_universe_statuses, enqueue_formal_task, supersede_formal_tasks, lease_next_formal_task, resolve_formal_task_dependencies, complete_formal_task, and fail_formal_task.
- StateStore.put_formal_snapshot(fetch: OfficialFetch, stored: FormalStoredSnapshot, verification: EvidenceVerification) -> OfficialSnapshotRef and put_formal_snapshot_for_leased_task(fetch: OfficialFetch, stored: FormalStoredSnapshot, verification: EvidenceVerification, *, task_id: str, worker_id: str) -> OfficialSnapshotRef are the only V5 formal snapshot writers; they never accept a pre-persistence OfficialSnapshotRef.
- Formal task states are pending, leased, verified, retryable_failed, terminal_failed, and superseded; they are not legacy job states.
- V5 tables are formal_source_snapshot, formal_task_snapshot_receipt, formal_universe_snapshot, formal_universe_source, formal_universe_member, formal_universe_status, formal_collection_task, and formal_collection_task_dependency.

- [ ] **Step 1: Write failing V4-to-V5 migration and status-invariant tests**

~~~python
def test_v4_migration_preserves_legacy_rows_and_adds_formal_tables(self):
    migrate_fixture("schema_v4.sql", self.db_path)
    store = StateStore(self.db_path)
    store.initialize()
    with sqlite3.connect(self.db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    self.assertTrue({"formal_source_snapshot", "formal_universe_source", "formal_universe_status", "formal_collection_task"} <= tables)
    self.assertIn("request_fingerprint", table_columns(self.db_path, "formal_source_snapshot"))
    self.assertEqual(legacy_score_run_count(self.db_path), 1)

def test_universe_status_requires_one_row_per_member(self):
    snapshot_id = self.store.put_formal_universe_snapshot(frozen_universe_input())
    with self.assertRaisesRegex(ValueError, "exactly one status"):
        self.store.replace_formal_universe_statuses(snapshot_id, decisions()[:-1])

def test_frozen_universe_requires_one_verified_visible_source_for_each_exchange(self):
    with self.assertRaisesRegex(ValueError, "SH/SZ/BJ"):
        self.store.put_formal_universe_snapshot(
            FormalUniverseIngestor().build(
                FORMAL_FREEZE_AT_CN, "m" * 64, verified_listing_documents_for("SH", "SZ")
            )
        )

def test_same_frozen_input_recovers_the_existing_snapshot_without_duplicate_members(self):
    frozen = frozen_universe_input()
    first_id = self.store.put_formal_universe_snapshot(frozen)
    second_id = self.store.put_formal_universe_snapshot(frozen)
    self.assertEqual(second_id, first_id)
    self.assertEqual(
        self.store.get_formal_universe_snapshot_by_input_hash(frozen.frozen_input_hash)["id"],
        first_id,
    )

def test_frozen_input_hash_cannot_alias_different_root_or_source_lineage(self):
    frozen = frozen_universe_input()
    self.store.put_formal_universe_snapshot(frozen)
    conflicting = replace(frozen, registry_manifest_hash="n" * 64)
    with self.assertRaisesRegex(ValueError, "frozen_input_hash"):
        self.store.put_formal_universe_snapshot(conflicting)

def test_task_prerequisite_is_not_leased_early_and_terminal_parent_cascades(self):
    calendar_id = self.store.enqueue_formal_task(
        "formal_context", "calendar-v1", "calendar-v1", {"kind": "trading_calendar"}
    )
    dependent_id = self.store.enqueue_formal_task(
        "formal_statement", "statement-v1", "discovery-v1", {"kind": "profit_sheet"},
        prerequisite_task_ids=(calendar_id,),
    )
    self.assertIsNone(
        self.store.lease_next_formal_task(("formal_statement",), "worker-a", 30)
    )
    leased_calendar = self.store.lease_next_formal_task(("formal_context",), "worker-calendar", 30)
    self.assertEqual(leased_calendar["id"], calendar_id)
    self.store.fail_formal_task(calendar_id, "worker-calendar", {"code": "calendar_failed"}, "terminal_failed", None)
    self.store.resolve_formal_task_dependencies()
    self.assertEqual(self.store.get_formal_task(dependent_id)["status"], "terminal_failed")
    self.assertEqual(self.store.get_formal_task(dependent_id)["error"]["code"], "prerequisite_terminal_failed")

def test_verified_raw_receipt_survives_later_terminal_parse_failure(self):
    task_id = self.store.enqueue_formal_task(
        "formal_statement", "statement-v1", "discovery-v1", {"kind": "profit_sheet"}
    )
    self.store.lease_next_formal_task(("formal_statement",), "worker-a", 30)
    fetch, stored, verification = written_verified_formal_snapshot(
        refresh_generation="discovery-v1", producing_task_id=task_id
    )
    snapshot = self.store.put_formal_snapshot_for_leased_task(
        fetch, stored, verification, task_id=task_id, worker_id="worker-a"
    )
    self.store.fail_formal_task(
        task_id, "worker-a", {"code": "fact_schema_invalid", "snapshot_id": snapshot.snapshot_id},
        "terminal_failed", None,
    )
    self.assertEqual(self.store.get_formal_task_snapshot_receipt(task_id)["snapshot_id"], snapshot.snapshot_id)
    self.assertEqual(self.store.get_formal_snapshot(snapshot.snapshot_id)["verification_status"], "verified")

def test_snapshot_recomputes_request_fingerprint_from_canonical_request_json(self):
    fetch, stored, verification = written_verified_formal_snapshot(
        refresh_generation="bootstrap-v1", producing_task_id=None
    )
    ref = self.store.put_formal_snapshot(fetch, stored, verification)
    self.assertEqual(ref.request_fingerprint, fetch.request.request_fingerprint)
    mismatched_fetch = replace(
        fetch, request=OfficialRequest(fetch.request.source, fetch.request.dataset, "SZ000002", fetch.request.period_or_date)
    )
    with self.assertRaisesRegex(ValueError, "request_fingerprint"):
        self.store.put_formal_snapshot(mismatched_fetch, stored, verification)

def test_retryable_and_expired_leased_tasks_are_reclaimed_only_when_ready(self):
    task_id = self.store.enqueue_formal_task(
        "formal_statement", "statement-v1", "root-aware-v1", {"kind": "profit_sheet"}
    )
    first = self.store.lease_next_formal_task(
        ("formal_statement",), "worker-a", 30, now_utc="2026-09-04T00:00:00+00:00"
    )
    self.store.fail_formal_task(
        task_id, "worker-a", {"code": "timeout"}, "retryable_failed",
        "2026-09-04T00:01:00+00:00",
    )
    self.assertIsNone(self.store.lease_next_formal_task(
        ("formal_statement",), "worker-b", 30, now_utc="2026-09-04T00:00:59+00:00"
    ))
    retry = self.store.lease_next_formal_task(
        ("formal_statement",), "worker-b", 30, now_utc="2026-09-04T00:01:00+00:00"
    )
    self.assertEqual(retry["id"], task_id)
    reclaimed = self.store.lease_next_formal_task(
        ("formal_statement",), "worker-c", 30, now_utc="2026-09-04T00:01:31+00:00"
    )
    self.assertEqual(reclaimed["id"], task_id)

def test_same_key_with_changed_canonical_payload_is_rejected(self):
    self.store.enqueue_formal_task(
        "formal_statement", "statement-v1", "root-aware-v1", {"root_manifest": "a" * 64}
    )
    with self.assertRaisesRegex(ValueError, "idempotency_payload_conflict"):
        self.store.enqueue_formal_task(
            "formal_statement", "statement-v1", "root-aware-v1", {"root_manifest": "b" * 64}
        )
~~~

- [ ] **Step 2: Run migration tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_v4_migration_preserves_legacy_rows_and_adds_formal_tables -v
~~~

Expected: FAIL because schema v5 and APIs do not exist.

- [ ] **Step 3: Implement V5 migration and persistence APIs**

Set SCHEMA_VERSION to 5. Add _V5_TABLE_DDL, _V5_INDEX_DDL, _apply_v5_migration, and extend initialize() so only continuous migrations 2,3,4,5 are accepted. Use these core columns:

~~~text
formal_source_snapshot:
  id, source, dataset, request_json, request_fingerprint, content_sha256, manifest_sha256,
  content_path, manifest_path, original_url, published_at_utc,
  published_precision, source_updated_at_utc, captured_at_utc,
  effective_at_utc, effective_time_evidence_hash, parser_id, parser_version, mapping_version,
  refresh_generation, producing_task_id, verification_json, created_at

formal_task_snapshot_receipt:
  task_id PRIMARY KEY, snapshot_id UNIQUE, manifest_sha256 UNIQUE, refresh_generation, recorded_at

formal_universe_snapshot:
  id, as_of_utc, registry_manifest_hash, universe_hash, source_audit_hash,
  frozen_input_hash UNIQUE, created_at

formal_universe_source:
  universe_snapshot_id, exchange, source_snapshot_id, manifest_sha256,
  source_content_sha256, parser_id, parser_version,
  extraction_audit_hash, extraction_json, created_at
  PRIMARY KEY (universe_snapshot_id, exchange)

formal_universe_member:
  snapshot_id, security_id, exchange, code6, security_type, listing_status, raw_json

formal_universe_status:
  snapshot_id, security_id, status, reasons_json, veto_flags_json, evidence_hash, updated_at

formal_collection_task:
  id, kind, idempotency_key, refresh_generation, payload_json, payload_sha256, status, lease_worker,
  lease_expires_at, next_retry_at, result_json, error_json, created_at, updated_at

formal_collection_task_dependency:
  task_id, prerequisite_task_id, created_at
  PRIMARY KEY (task_id, prerequisite_task_id)
~~~

Require all formal status rows to reference an existing member, reject duplicate member/status rows, and reject a source snapshot whose verification JSON is not verified. formal_source_snapshot is lineage-addressed by manifest_sha256, not merely raw content_sha256: identical bytes from different refresh generations or producing tasks create separate snapshot rows that may share only the immutable .bin path. On every write and read, recompute request_fingerprint from canonical request_json and reject a mismatch; add a unique expression index over (request_fingerprint, refresh_generation, COALESCE(producing_task_id, 'bootstrap')) plus an index for exact request lookup. Every formal source snapshot has a nonempty immutable refresh_generation; producing_task_id is either null for an explicitly verified bootstrap/discovery snapshot or foreign-references formal_collection_task.id. A nonnull producing_task_id must be paired with exactly one formal_task_snapshot_receipt for the same task/snapshot in the same transaction; do not create a circular source-snapshot-to-receipt foreign key. The snapshot write APIs accept OfficialFetch, FormalStoredSnapshot, and EvidenceVerification—not OfficialSnapshotRef—and return an OfficialSnapshotRef only after the row and signed manifest have been stored and re-read. put_formal_snapshot accepts only a stored manifest whose producing_task_id is null. put_formal_snapshot_for_leased_task atomically inserts the snapshot row and its receipt while the named task is leased by the named worker; it requires the task generation, snapshot generation, signed manifest linkage, request fingerprint, and receipt manifest_sha256 to agree. The receipt proves a verified raw fetch even if a later parse/feature step changes that task to terminal_failed; no source snapshot may claim a task merely because that task later became verified. complete_formal_task for a source-fetch task requires its exact receipt, while fail_formal_task may retain that receipt together with a deterministic downstream parse/build error. put_formal_universe_snapshot(frozen: FormalFrozenUniverseInput) accepts only the typed output of FormalUniverseIngestor and recomputes frozen_input_hash from its freeze instant, registry_manifest_hash, canonical member set, and exact source manifest/extraction lineage. For every source it requires a nonnull producing_task_id whose receipt points back to that snapshot, then requires that task to be a verified formal_universe_source task whose canonical payload and result both carry the same registry_manifest_hash and declared exchange as frozen; bootstrap/discovery snapshots are never eligible as universe sources. It rechecks the root/task linkage, member set, every extraction JSON/hash, source content hash, parser ID/version, and source manifest against those linked verified formal snapshots and task receipts. In one transaction it either returns the one pre-existing row with the identical frozen_input_hash and byte-equivalent canonical frozen input, or inserts a frozen snapshot, all members, one formal_universe_source row for exactly each SH/SZ/BJ exchange, and an initial full pending_evidence collection-status ledger; an equal input hash paired with any different canonical field raises frozen_input_hash_conflict. Each source must resolve to a verified formal snapshot visible at the freeze, have the matching exchange and nonempty audited ordinary-A extraction, and have a manifest/audit hash equal to its row. It rejects missing/duplicate exchanges, duplicate cross-exchange member IDs, or any source/member/audit mismatch. get_formal_universe_snapshot_by_input_hash returns only that immutable row. get_formal_universe_snapshot_from_task(finalizer_task_id) requires a verified formal_universe_finalize task whose canonical result_json names the snapshot ID, frozen_input_hash, universe_hash, and registry_manifest_hash, then rechecks all four against formal_universe_snapshot before returning it; it never infers a universe from a bare task ID. formal_collection_task.payload_sha256 is the SHA-256 of canonical payload JSON and is immutable after creation. formal_collection_task_dependency rejects self-edges, missing tasks, duplicate edges, and cycles. Do not copy any legacy source_snapshot into formal_source_snapshot.

The formal-task idempotency key is the canonical hash of kind, security ID, category, report period or market date, source, freeze instant, request version, and refresh_generation; prerequisite edges are not part of that key. refresh_generation is an immutable identifier derived from an authoritative discovery/index snapshot hash or explicitly persisted source revision; it is never a wall-clock retry number. For every registry-governed task, including timestamp-only statement and context collection, it is the canonical SHA-256 of the authoritative discovery/index generation, the root registry manifest hash, and the task's relevant signed role hashes. A date-only downstream task additionally includes the signed calendar selector and selected calendar manifest hash. Thus either a root/role configuration change or a calendar-binding change necessarily creates a new key. enqueue_formal_task canonicalizes the payload, stores payload_sha256, and accepts a same-key replay only when refresh_generation, canonical payload, and the full prerequisite-edge set are identical; any other same-key replay raises idempotency_payload_conflict rather than reusing an old verified task. A later verified discovery/index or configuration lineage generation produces a new task key, marks unfinished older tasks superseded through supersede_formal_tasks, and leaves verified old snapshots immutable for historical selection.

Task states are pending, leased, verified, retryable_failed, terminal_failed, and superseded. lease_next_formal_task may atomically acquire only a dependency-satisfied pending row, a retryable_failed row with non-null next_retry_at at or before now_utc, or a leased row whose lease_expires_at is at or before now_utc. It chooses candidates deterministically by ready time, created_at, and ID, then performs one compare-and-set UPDATE which sets the new worker and expiry; it never first rewrites an expired lease or retryable failure to pending. A retryable failure must carry a finite non-null next_retry_at, and terminal_failed, verified, superseded, and unexpired leased rows are never leaseable. resolve_formal_task_dependencies turns an unleased pending or retryable_failed dependent whose parent is terminal_failed or superseded into terminal_failed with prerequisite_terminal_failed; a worker that discovers that condition after an expired-lease takeover performs the same terminal transition before transport. Add tests that equal generations deduplicate while a changed discovery or root-registry generation creates a new task and preserves both audit records, that a same-key payload mismatch is rejected, that a dependent cannot lease before its calendar prerequisite verifies, that a retryable failure leases exactly once after next_retry_at, and that an expired lease can be reclaimed to parse its stored receipt without a second transport call.

- [ ] **Step 4: Run migration and regression suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store tests.test_snapshot_repository -v
~~~

Expected: PASS; v2-v4 migration and legacy job tests continue to pass.

- [ ] **Step 5: Commit the schema foundation**

~~~powershell
git add -- ashare_pipeline/state_store.py tests/test_state_store.py tests/fixtures/schema_v4.sql
git commit -m "feat: add formal evidence and universe schema"
~~~

### Task 5: Verified Formal Snapshot Repository

**Files:**
- Create: ashare_pipeline/formal_snapshot_repository.py
- Create: tests/test_formal_snapshot_repository.py
- Modify: ashare_pipeline/state_store.py: formal snapshot lookup helper only

**Interfaces:**
- FormalSnapshotRepository.persist_verified(fetch, verification, *, producing_task_id: str | None, worker_id: str | None) returns OfficialSnapshotRef with the exact immutable field contract from Task 1.
- FormalSnapshotRepository.find_exact_verified(request, *, parser_id, parser_version, mapping_version, content_sha256, manifest_sha256) returns OfficialSnapshotRef or None.
- FormalSnapshotRepository.find_visible_verified(request, *, parser_id, parser_version, mapping_version, as_of_utc) returns the one point-in-time visible OfficialSnapshotRef or None; get_verified_by_manifest(manifest_sha256) returns one immutable ref or raises.
- FormalSnapshotRepository.read_verified_raw(ref) returns original bytes only after re-checking the ref's immutable content and manifest hashes.
- A legacy SnapshotRef or legacy source_snapshot ID is never accepted by this repository.

- [ ] **Step 1: Write failing repository tests**

~~~python
class FormalSnapshotRepositoryTests(unittest.TestCase):
    def test_persisted_verified_fetch_can_be_found_by_exact_request(self):
        repository = FormalSnapshotRepository(self.root, self.store)
        fetch = cninfo_fetch("SZ000001", "2025-12-31")
        ref = repository.persist_verified(
            fetch, verify_official_fetch(fetch, SourcePolicy.cninfo()), producing_task_id=None, worker_id=None
        )
        self.assertEqual(
            repository.find_exact_verified(
                fetch.request,
                parser_id=fetch.parser_id,
                parser_version=fetch.parser_version,
                mapping_version=fetch.mapping_version,
                content_sha256=fetch.content_sha256,
                manifest_sha256=ref.manifest_sha256,
            ),
            ref,
        )

    def test_leased_persist_writes_raw_then_returns_row_derived_ref_and_receipt(self):
        task_id = lease_fixture_formal_task(self.store, worker_id="worker-a")
        fetch = cninfo_fetch("SZ000001", "2025-12-31", producing_task_id=task_id)
        ref = repository.persist_verified(
            fetch, verify_official_fetch(fetch, SourcePolicy.cninfo()),
            producing_task_id=task_id, worker_id="worker-a",
        )
        self.assertEqual(
            self.store.get_formal_task_snapshot_receipt(task_id)["snapshot_id"], ref.snapshot_id
        )
        self.assertEqual(
            self.store.get_formal_snapshot(ref.snapshot_id)["request_fingerprint"],
            fetch.request.request_fingerprint,
        )

    def test_rejected_or_legacy_evidence_cannot_be_found_as_formal(self):
        repository = FormalSnapshotRepository(self.root, self.store)
        with self.assertRaisesRegex(ValueError, "verified"):
            repository.persist_verified(
                third_party_fetch(), rejected_verification(), producing_task_id=None, worker_id=None
            )
        self.assertIsNone(
            repository.find_exact_verified(
                OfficialRequest("cninfo", "annual_report", "SZ000001", "2025-12-31"),
                parser_id="cninfo-pdf",
                parser_version="cninfo-pdf-v1",
                mapping_version="cninfo-annual-v1",
                content_sha256="0" * 64,
                manifest_sha256="0" * 64,
            )
        )

    def test_visible_lookup_selects_corrected_version_only_at_explicit_as_of(self):
        first = persist_fixture_version(repository, published_at="2026-08-20T00:00:00+00:00")
        second = persist_fixture_version(repository, published_at="2026-08-21T00:00:00+00:00")
        selected = repository.find_visible_verified(
            first.request, parser_id=first.parser_id, parser_version=first.parser_version,
            mapping_version=first.mapping_version,
            as_of_utc="2026-08-31T07:00:00+00:00",
        )
        self.assertEqual(selected.manifest_sha256, second.manifest_sha256)
~~~

- [ ] **Step 2: Run repository tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_snapshot_repository -v
~~~

Expected: FAIL because FormalSnapshotRepository is undefined.

- [ ] **Step 3: Implement repository ordering and persistence**

Call FormalSnapshotStore.write_verified(fetch, verification, producing_task_id=...) first. persist_verified requires fetch.refresh_generation and paired producing_task_id/worker_id arguments: both null invokes StateStore.put_formal_snapshot(fetch, stored, verification) for a verified bootstrap/discovery row, while both nonnull invokes StateStore.put_formal_snapshot_for_leased_task(fetch, stored, verification, task_id, worker_id) in one short transaction and atomically records its raw-fetch receipt. StateStore validates the raw-store manifest against fetch/verification, recomputes request_fingerprint from canonical request JSON, inserts the formal row, then re-reads that row and manifest to return OfficialSnapshotRef; no caller can pass a pre-persistence OfficialSnapshotRef. The signed manifest, receipt, and snapshot row must carry the same task linkage, generation, parser_id, parser_version, and request fingerprint. This keeps verified raw evidence durable when later fact parsing fails, without allowing an unleased task to claim a snapshot. Construct OfficialSnapshotRef only from the stored formal row plus re-read verified manifest; never synthesize it from a legacy SnapshotRef, a bare hash, or a mutable request object. read_verified_raw delegates to FormalSnapshotStore.read_verified_raw and rejects any ref/path/hash mismatch before a recovery parser receives bytes. find_exact_verified first recomputes the canonical request fingerprint and requires it plus exact canonical request JSON, source, dataset, security ID, period/date, parser ID/version, mapping version, content SHA, and manifest SHA; it does not choose a version. find_visible_verified first recomputes the canonical request fingerprint and requires an explicit as_of_utc, then chooses only matching request/parser/mapping candidates visible then with formal_version_sort_key; never select by global dataset latest. get_verified_by_manifest is the only calendar/root-lineage lookup and never accepts a bare content hash.

- [ ] **Step 4: Run repository, store, and evidence tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_snapshot_repository tests.test_formal_snapshot_store tests.test_formal_evidence tests.test_state_store -v
~~~

Expected: PASS.

- [ ] **Step 5: Commit the repository**

~~~powershell
git add -- ashare_pipeline/formal_snapshot_repository.py ashare_pipeline/state_store.py tests/test_formal_snapshot_repository.py
git commit -m "feat: persist verified formal snapshots"
~~~

## Plan Self-Review

- Spec coverage: Tasks 1-2 implement official source metadata, verification, original-byte preservation, and post-freeze historical replay rules. Task 3 implements the formal 15:00 cutoff, SH/SZ/BJ identity, and universe-status priority. Tasks 4-5 persist the separate formal domain, resumable task state, complete universe rows, and verified evidence without altering V1/V2 records.
- Placeholder scan: no task delegates a rule to an unnamed future component; every introduced class, table, state, and test command is named here.
- Type consistency: OfficialFetch flows from formal_evidence to FormalSnapshotStore and FormalSnapshotRepository; OfficialSnapshotRef is the only repository return type; VerifiedCalendarBinding is the only date-only evidence input accepted by V6 source resolution; FormalUniverseDecision flows into StateStore.replace_formal_universe_statuses.
