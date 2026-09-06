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

