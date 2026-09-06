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

