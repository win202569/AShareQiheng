from dataclasses import replace
import hashlib
import json
from collections.abc import Mapping
import unittest

from ashare_pipeline.formal_evidence import OfficialSnapshotRef
from ashare_pipeline.formal_universe import (
    FormalFrozenUniverseInput,
    FormalUniverseIngestor,
    FormalUniverseSourceDocument,
    build_universe_snapshot,
    canonical_security_id,
    classify_universe_status,
    extract_formal_universe_members,
)


FORMAL_FREEZE_AT_CN = "2026-08-31T15:00:00+08:00"


def canonical_hash(value: object) -> str:
    def plain(item: object) -> object:
        if isinstance(item, Mapping):
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        return item

    payload = json.dumps(
        plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def snapshot_ref(exchange: str) -> OfficialSnapshotRef:
    parser_id = f"{exchange.lower()}-listing-json"
    return OfficialSnapshotRef(
        snapshot_id=f"{exchange.lower()}-listing-1",
        source={"SH": "sse", "SZ": "szse", "BJ": "bse"}[exchange],
        dataset="official_security_listing",
        request_fingerprint="1" * 64,
        security_id=None,
        period_or_date="2026-08-31",
        exchange=exchange,
        content_sha256={"SH": "a", "SZ": "b", "BJ": "c"}[exchange] * 64,
        manifest_sha256={"SH": "d", "SZ": "e", "BJ": "f"}[exchange] * 64,
        content_path=f"formal/{exchange.lower()}/content",
        manifest_path=f"formal/{exchange.lower()}/manifest.json",
        original_url=f"https://official.invalid/{exchange.lower()}/listing",
        published_at_utc="2026-08-31T06:00:00+00:00",
        published_precision="timestamp",
        source_updated_at_utc=None,
        captured_at_utc="2026-08-31T06:30:00+00:00",
        effective_at_utc="2026-08-31T06:00:00+00:00",
        effective_time_evidence_hash=None,
        refresh_generation="formal-freeze-v1",
        producing_task_id="listing-task",
        parser_id=parser_id,
        parser_version=f"{parser_id}-v1",
        mapping_version="listing-map-v1",
        verification_status="verified",
    )


def listing_document(exchange: str, rows: tuple[dict, ...]) -> FormalUniverseSourceDocument:
    snapshot = snapshot_ref(exchange)
    return FormalUniverseSourceDocument(
        exchange=exchange,
        snapshot=snapshot,
        parser_id=snapshot.parser_id,
        parser_version=snapshot.parser_version,
        parsed_rows=rows,
    )


def verified_listing_documents(*exchanges: str) -> tuple[FormalUniverseSourceDocument, ...]:
    codes = {"SH": "600000", "SZ": "000001", "BJ": "430001"}
    return tuple(listing_document(exchange, ({
        "security_id": exchange + codes[exchange],
        "security_type": "ordinary_a",
        "listing_status": "listed",
    },)) for exchange in exchanges)


class FormalUniverseTests(unittest.TestCase):
    def test_ingestor_accepts_signed_universe_listing_without_rewriting_snapshot_identity(self):
        documents = tuple(
            replace(document, snapshot=replace(document.snapshot, dataset="universe_listing"))
            for document in verified_listing_documents("SZ", "BJ", "SH")
        )
        frozen = FormalUniverseIngestor().build(FORMAL_FREEZE_AT_CN, "a" * 64, documents)
        self.assertEqual(tuple(member.security_id for member in frozen.members),
                         ("BJ430001", "SH600000", "SZ000001"))
        for source in frozen.sources:
            original = next(document.snapshot for document in documents if document.exchange == source.exchange)
            self.assertIs(source.snapshot, original)
            self.assertEqual(source.snapshot.dataset, "universe_listing")

    def test_ingestor_accepts_canonical_utc_freeze_and_preserves_task_lineage_representation(self):
        documents = verified_listing_documents("SH", "SZ", "BJ")
        frozen = FormalUniverseIngestor().build("2026-08-31T07:00:00+00:00", "a" * 64, documents)
        self.assertEqual(frozen.as_of_utc, "2026-08-31T07:00:00+00:00")
        self.assertEqual(tuple(member.security_id for member in frozen.members),
                         ("BJ430001", "SH600000", "SZ000001"))
        legacy = FormalUniverseIngestor().build(FORMAL_FREEZE_AT_CN, "a" * 64, documents)
        self.assertEqual(legacy.as_of_utc, FORMAL_FREEZE_AT_CN)
        self.assertEqual(legacy.universe_hash, frozen.universe_hash)
        # Captured from the pre-compatibility HEAD implementation with this fixture.
        self.assertEqual(legacy.frozen_input_hash,
                         "ac8575dab15f28a9c9d032463704565c01ae9ce49f723eac55bd57ebbd2868c9")
        self.assertNotEqual(legacy.frozen_input_hash, frozen.frozen_input_hash)

    def test_ingestor_freeze_remains_exact_and_rejects_other_dates_or_ambiguous_forms(self):
        documents = verified_listing_documents("SH", "SZ", "BJ")
        for invalid in ("2026-08-31T07:00:01+00:00", "2026-08-31T06:59:59+00:00",
                        "2026-09-01T07:00:00+00:00", "2026-08-31T07:00:00",
                        "2026-08-31T07:00:00Z", "2026-08-31T08:00:00+01:00"):
            with self.subTest(freeze=invalid), self.assertRaisesRegex(ValueError, "freeze"):
                FormalUniverseIngestor().build(invalid, "a" * 64, documents)

    def test_bj_identity_uses_ascii_digits_and_status_priority(self):
        self.assertEqual(canonical_security_id(" bj430001 "), "BJ430001")
        with self.assertRaisesRegex(ValueError, "six digits"):
            canonical_security_id("BJ٤٣٠٠٠١")
        self.assertEqual(classify_universe_status(in_scope=False, evidence_complete=False, veto_flags=("ST",)), "out_of_scope")
        self.assertEqual(classify_universe_status(in_scope=True, evidence_complete=False, veto_flags=("ST",)), "pending_evidence")
        self.assertEqual(classify_universe_status(in_scope=True, evidence_complete=True, veto_flags=("ST",)), "pool_vetoed")
        self.assertEqual(classify_universe_status(in_scope=True, evidence_complete=True, veto_flags=()), "formal_scored")

    def test_official_listing_extraction_keeps_ordinary_a_and_audits_excluded_row_content(self):
        first = extract_formal_universe_members(listing_document("BJ", (
            {"security_id": "BJ430001", "security_type": "ordinary_a", "listing_status": "listed", "name": "A"},
            {"security_id": "BJ899001", "security_type": "bond", "listing_status": "listed", "name": "Bond A"},
        )))
        second = extract_formal_universe_members(listing_document("BJ", (
            {"security_id": "BJ430001", "security_type": "ordinary_a", "listing_status": "listed", "name": "A"},
            {"security_id": "BJ899001", "security_type": "bond", "listing_status": "listed", "name": "Bond B"},
        )))
        self.assertEqual([member.security_id for member in first.members], ["BJ430001"])
        self.assertEqual(first.members[0].raw_row["name"], "A")
        self.assertEqual(first.audit.excluded_by_security_type, (("bond", 1),))
        self.assertNotEqual(first.audit.excluded_rows_hash, second.audit.excluded_rows_hash)
        self.assertNotEqual(first.audit.audit_hash, second.audit.audit_hash)

    def test_accepted_raw_json_is_defensively_copied_and_deeply_immutable(self):
        raw_row = {
            "security_id": "BJ430001",
            "security_type": "ordinary_a",
            "listing_status": "listed",
            "metadata": {"aliases": ["alpha"]},
        }
        frozen = FormalUniverseIngestor().build(
            FORMAL_FREEZE_AT_CN,
            "m" * 64,
            (
                listing_document("BJ", (raw_row,)),
                *verified_listing_documents("SH", "SZ"),
            ),
        )
        member = frozen.members[0]
        original_hashes = (member.raw_row_hash, frozen.universe_hash, frozen.frozen_input_hash)

        raw_row["metadata"]["aliases"].append("source-mutation")
        with self.assertRaises(TypeError):
            member.raw_row["metadata"] = {}
        with self.assertRaises(AttributeError):
            member.raw_row["metadata"]["aliases"].append("member-mutation")

        self.assertEqual(member.raw_row["metadata"]["aliases"], ("alpha",))
        self.assertEqual(
            (member.raw_row_hash, frozen.universe_hash, frozen.frozen_input_hash),
            original_hashes,
        )

    def test_extraction_fails_closed_for_bad_rows_and_zero_ordinary_a(self):
        invalid_rows = (
            ({"security_id": "SZ000001", "listing_status": "listed"}, "unknown security_type"),
            ({"security_id": "SZ000001", "security_type": "mystery", "listing_status": "listed"}, "unknown security_type"),
            ({"security_id": "SZ000001", "security_type": "ordinary_a"}, "listing_status"),
            ({"security_id": "SH600000", "security_type": "ordinary_a", "listing_status": "listed"}, "exchange"),
        )
        for row, message in invalid_rows:
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, message):
                extract_formal_universe_members(listing_document("SZ", (row,)))
        duplicate = {"security_id": "SZ000001", "security_type": "ordinary_a", "listing_status": "listed"}
        with self.assertRaisesRegex(ValueError, "duplicate security_id"):
            extract_formal_universe_members(listing_document("SZ", (duplicate, duplicate)))
        with self.assertRaisesRegex(ValueError, "zero ordinary-A"):
            extract_formal_universe_members(listing_document("SZ", (
                {"security_id": "SZ160001", "security_type": "fund", "listing_status": "listed"},
            )))

        document = listing_document("SZ", (duplicate,))
        with self.assertRaisesRegex(ValueError, "snapshot exchange"):
            extract_formal_universe_members(
                replace(document, snapshot=replace(document.snapshot, exchange="SH"))
            )

    def test_build_snapshot_requires_three_extractions_and_is_order_independent(self):
        extractions = tuple(extract_formal_universe_members(document) for document in verified_listing_documents("SH", "SZ", "BJ"))
        members, universe_hash = build_universe_snapshot(reversed(extractions))
        self.assertEqual([member.security_id for member in members], ["BJ430001", "SH600000", "SZ000001"])
        self.assertEqual(len(universe_hash), 64)
        self.assertEqual(build_universe_snapshot(extractions), (members, universe_hash))
        with self.assertRaisesRegex(ValueError, "SH/SZ/BJ"):
            build_universe_snapshot(extractions[:2])

    def test_frozen_input_public_constructor_rejects_bare_members(self):
        with self.assertRaisesRegex(ValueError, "FormalUniverseIngestor"):
            FormalFrozenUniverseInput(
                as_of_utc=FORMAL_FREEZE_AT_CN,
                registry_manifest_hash="m" * 64,
                members=(),
                sources=(),
                universe_hash="u" * 64,
                source_audit_hash="s" * 64,
                frozen_input_hash="f" * 64,
            )

    def test_public_constructor_rejects_a_self_consistent_fabricated_source_graph(self):
        legitimate = FormalUniverseIngestor().build(
            FORMAL_FREEZE_AT_CN,
            "m" * 64,
            verified_listing_documents("SH", "SZ", "BJ"),
        )
        first = legitimate.sources[0]
        forged_audit_fields = {
            "accepted_members_hash": first.extraction.audit.accepted_members_hash,
            "accepted_ordinary_a_count": first.extraction.audit.accepted_ordinary_a_count,
            "exchange": first.extraction.audit.exchange,
            "excluded_by_security_type": first.extraction.audit.excluded_by_security_type,
            "excluded_rows_hash": "9" * 64,
            "parsed_rows_hash": "8" * 64,
            "parser_id": first.extraction.audit.parser_id,
            "parser_version": first.extraction.audit.parser_version,
            "source_content_sha256": first.extraction.audit.source_content_sha256,
            "source_row_count": first.extraction.audit.source_row_count,
        }
        forged_audit = replace(
            first.extraction.audit,
            **forged_audit_fields,
            audit_hash=canonical_hash(forged_audit_fields),
        )
        forged_first = replace(
            first,
            extraction=replace(first.extraction, audit=forged_audit),
        )
        forged_sources = (forged_first, *legitimate.sources[1:])
        member_payloads = [{
            "exchange": member.exchange,
            "listing_status": member.listing_status,
            "raw_row": member.raw_row,
            "raw_row_hash": member.raw_row_hash,
            "security_id": member.security_id,
            "security_type": member.security_type,
        } for member in legitimate.members]
        source_audits = [{
            "exchange": source.exchange,
            "audit_hash": source.extraction.audit.audit_hash,
        } for source in forged_sources]
        forged_universe_hash = canonical_hash({
            "members": member_payloads,
            "source_audits": source_audits,
        })
        source_manifest = [{
            "audit_hash": source.extraction.audit.audit_hash,
            "content_sha256": source.snapshot.content_sha256,
            "exchange": source.exchange,
            "manifest_sha256": source.snapshot.manifest_sha256,
            "parser_id": source.snapshot.parser_id,
            "parser_version": source.snapshot.parser_version,
        } for source in forged_sources]
        forged_source_audit_hash = canonical_hash(source_manifest)
        forged_frozen_input_hash = canonical_hash({
            "as_of_utc": legitimate.as_of_utc,
            "registry_manifest_hash": legitimate.registry_manifest_hash,
            "sources": [{
                "audit_hash": item["audit_hash"],
                "exchange": item["exchange"],
                "manifest_sha256": item["manifest_sha256"],
            } for item in source_manifest],
            "universe_hash": forged_universe_hash,
        })

        with self.assertRaisesRegex(ValueError, "FormalUniverseIngestor"):
            FormalFrozenUniverseInput(
                as_of_utc=legitimate.as_of_utc,
                registry_manifest_hash=legitimate.registry_manifest_hash,
                members=legitimate.members,
                sources=forged_sources,
                universe_hash=forged_universe_hash,
                source_audit_hash=forged_source_audit_hash,
                frozen_input_hash=forged_frozen_input_hash,
            )

    def test_member_constructor_rejects_noncanonical_or_non_ordinary_identity(self):
        frozen = FormalUniverseIngestor().build(
            FORMAL_FREEZE_AT_CN,
            "m" * 64,
            verified_listing_documents("SH", "SZ", "BJ"),
        )
        member = frozen.members[0]

        with self.assertRaisesRegex(ValueError, "ordinary_a"):
            replace(member, security_type="bond")
        with self.assertRaisesRegex(ValueError, "raw row identity"):
            replace(member, security_id="BJ430002")

    def test_ingestor_requires_three_verified_visible_exchange_scoped_documents(self):
        documents = verified_listing_documents("SH", "SZ", "BJ")
        frozen = FormalUniverseIngestor().build(FORMAL_FREEZE_AT_CN, "m" * 64, documents)
        self.assertEqual(tuple(source.exchange for source in frozen.sources), ("BJ", "SH", "SZ"))
        self.assertEqual([member.security_id for member in frozen.members], ["BJ430001", "SH600000", "SZ000001"])
        self.assertEqual(len(frozen.source_audit_hash), 64)
        self.assertEqual(len(frozen.frozen_input_hash), 64)
        with self.assertRaisesRegex(ValueError, "SH/SZ/BJ"):
            FormalUniverseIngestor().build(FORMAL_FREEZE_AT_CN, "m" * 64, documents[:2])
        future = replace(documents[0], snapshot=replace(documents[0].snapshot, effective_at_utc="2026-08-31T15:00:01+08:00"))
        with self.assertRaisesRegex(ValueError, "visible"):
            FormalUniverseIngestor().build(FORMAL_FREEZE_AT_CN, "m" * 64, (future, *documents[1:]))
        scoped = replace(documents[0], snapshot=replace(documents[0].snapshot, security_id="SH600000"))
        with self.assertRaisesRegex(ValueError, "global"):
            FormalUniverseIngestor().build(FORMAL_FREEZE_AT_CN, "m" * 64, (scoped, *documents[1:]))
        parser_mismatch = replace(documents[0], parser_version="other-parser-v2")
        with self.assertRaisesRegex(ValueError, "parser"):
            FormalUniverseIngestor().build(FORMAL_FREEZE_AT_CN, "m" * 64, (parser_mismatch, *documents[1:]))

    def test_ingestor_rejects_verified_non_listing_dataset(self):
        documents = verified_listing_documents("SH", "SZ", "BJ")
        annual_report = replace(
            documents[0],
            snapshot=replace(documents[0].snapshot, dataset="annual_report"),
        )

        with self.assertRaisesRegex(ValueError, "official listing dataset"):
            FormalUniverseIngestor().build(
                FORMAL_FREEZE_AT_CN,
                "m" * 64,
                (annual_report, *documents[1:]),
            )


if __name__ == "__main__":
    unittest.main()
