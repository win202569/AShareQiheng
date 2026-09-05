"""Contract tests for the isolated Formal V3 financial-fact boundary."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
import unittest

import ashare_pipeline.formal_financial_schema as formal_financial_schema
from ashare_pipeline.feature_contract import canonical_json_bytes
from ashare_pipeline.financial_schema import FinancialFact, MAPPING_VERSION
from ashare_pipeline.formal_evidence import OfficialSnapshotRef
from ashare_pipeline.formal_sources import ParsedOfficialDocument
from ashare_pipeline.formal_financial_schema import (
    FormalFactExtraction,
    FormalFactIssue,
    FormalFactMapping,
    FormalFinancialFact,
    SignedFinancialMappingRegistry,
    extract_formal_financial_facts,
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


class AcceptingVerifier:
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool:
        return signature == "fixture-signature" and key_id == "fixture-key"


class RejectingVerifier:
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool:
        return False


class RaisingVerifier:
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool:
        raise RuntimeError("fixture verifier unavailable")


class EqualitySpoof:
    """A hostile replacement that claims equality with every original field."""

    def __eq__(self, other: object) -> bool:
        return True


def mapping(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "mapping_id": "operating_profit",
        "statement": "income",
        "metric_key": "operating_profit",
        "source_field": "OPERATING_PROFIT",
        "unit": "CNY",
        "nature": "duration",
        "period_kind": "FY",
        "accounting_basis": "consolidated",
    }
    value.update(changes)
    return value


def binding(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "source": "cninfo",
        "dataset": "annual_report",
        "parser_id": "fixture-parser",
        "parser_version": "fixture-v1",
        "mapping_version": "fixture-map-v1",
        "exchange_scope": "BJ",
        "mapping_ids": ["operating_profit"],
    }
    value.update(changes)
    return value


def registry_bytes(
    *,
    mappings: list[dict[str, object]] | None = None,
    bindings: list[dict[str, object]] | None = None,
    **changes: object,
) -> bytes:
    value: dict[str, object] = {
        "schema_version": "formal-financial-mapping-registry-v1",
        "registry_role": "mapping",
        "row_format": "item_value_v1",
        "mappings": mappings if mappings is not None else [mapping()],
        "bindings": bindings if bindings is not None else [binding()],
    }
    value.update(changes)
    return canonical_bytes(value)


def signed_registry(**changes: object) -> SignedFinancialMappingRegistry:
    return SignedFinancialMappingRegistry.from_signed_bytes(
        registry_bytes(**changes),
        signature="fixture-signature",
        key_id="fixture-key",
        verifier=AcceptingVerifier(),
    )


def request_fingerprint(
    *,
    source: str,
    dataset: str,
    security_id: str | None,
    period_or_date: str | None,
    exchange: str | None,
) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "dataset": dataset,
                "exchange": exchange,
                "period_or_date": period_or_date,
                "security_id": security_id,
                "source": source,
            }
        )
    ).hexdigest()


def fixture_document(**changes: object) -> ParsedOfficialDocument:
    value: dict[str, object] = {
        "parser_id": "fixture-parser",
        "parser_version": "fixture-v1",
        "declared_security_id": "BJ430001",
        "declared_period": "2025-12-31",
        "published_at_utc": "2026-03-20T08:00:00+00:00",
        "published_precision": "timestamp",
        "source_updated_at_utc": "2026-03-20T08:30:00+00:00",
        "rows": ({"ITEM": "OPERATING_PROFIT", "VALUE": "120.0"},),
        "accounting_basis": "consolidated",
        "bootstrap_calendar": False,
    }
    value.update(changes)
    return ParsedOfficialDocument(**value)


def fixture_snapshot(document: ParsedOfficialDocument, **changes: object) -> OfficialSnapshotRef:
    value: dict[str, object] = {
        "snapshot_id": "11111111-1111-4111-8111-111111111111",
        "source": "cninfo",
        "dataset": "annual_report",
        "security_id": document.declared_security_id,
        "period_or_date": document.declared_period,
        "exchange": "BJ",
        "content_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "content_path": "unused.bin",
        "manifest_path": "unused.manifest.json",
        "original_url": "https://www.cninfo.com.cn/fixture/annual.json",
        "published_at_utc": document.published_at_utc,
        "published_precision": document.published_precision,
        "source_updated_at_utc": document.source_updated_at_utc,
        "captured_at_utc": "2026-09-04T00:00:00+00:00",
        "effective_at_utc": document.published_at_utc,
        "effective_time_evidence_hash": None,
        "refresh_generation": "fixture-index-v1",
        "producing_task_id": None,
        "parser_id": document.parser_id,
        "parser_version": document.parser_version,
        "mapping_version": "fixture-map-v1",
        "verification_status": "verified",
    }
    value.update(changes)
    if "request_fingerprint" not in value:
        value["request_fingerprint"] = request_fingerprint(
            source=value["source"],
            dataset=value["dataset"],
            security_id=value["security_id"],
            period_or_date=value["period_or_date"],
            exchange=value["exchange"],
        )
    return OfficialSnapshotRef(**value)


def extract(
    document: ParsedOfficialDocument | None = None,
    snapshot: OfficialSnapshotRef | None = None,
    registry: SignedFinancialMappingRegistry | None = None,
    created_at_utc: str = "2026-09-04T00:00:00+00:00",
) -> FormalFactExtraction:
    document = fixture_document() if document is None else document
    snapshot = fixture_snapshot(document) if snapshot is None else snapshot
    registry = signed_registry() if registry is None else registry
    return extract_formal_financial_facts(document, snapshot, registry, created_at_utc)


class FormalFinancialSchemaTests(unittest.TestCase):
    def test_signed_canonical_mapping_registry_loads_only_after_signature_verification(self) -> None:
        raw = registry_bytes()
        registry = SignedFinancialMappingRegistry.from_signed_bytes(
            raw,
            signature="fixture-signature",
            key_id="fixture-key",
            verifier=AcceptingVerifier(),
        )

        self.assertEqual(registry.registry_hash, hashlib.sha256(raw).hexdigest())
        self.assertEqual(registry.mappings[0], FormalFactMapping(**mapping()))
        self.assertEqual(registry.bindings[0].exchange_scope, "BJ")
        for verifier in (RejectingVerifier(), RaisingVerifier()):
            with self.subTest(verifier=type(verifier).__name__), self.assertRaises(ValueError):
                SignedFinancialMappingRegistry.from_signed_bytes(
                    raw,
                    signature="fixture-signature",
                    key_id="fixture-key",
                    verifier=verifier,
                )

    def test_mapping_registry_rejects_noncanonical_duplicate_or_wrong_wire(self) -> None:
        duplicate_keys = (
            b'{"bindings":[],"bindings":[],"mappings":[],"registry_role":"mapping",'
            b'"row_format":"item_value_v1","schema_version":"formal-financial-mapping-registry-v1"}'
        )
        noncanonical = b" " + registry_bytes()
        invalid_wires = (
            duplicate_keys,
            noncanonical,
            registry_bytes(registry_role="source"),
            registry_bytes(schema_version="other"),
            registry_bytes(row_format="display_value_v1"),
        )
        for raw in invalid_wires:
            with self.subTest(raw=raw[:32]), self.assertRaises(ValueError):
                SignedFinancialMappingRegistry.from_signed_bytes(
                    raw,
                    signature="fixture-signature",
                    key_id="fixture-key",
                    verifier=AcceptingVerifier(),
                )

    def test_mapping_registry_rejects_duplicate_ambiguous_or_uncovered_entries(self) -> None:
        alternate = mapping(
            mapping_id="other_profit",
            metric_key="other_profit",
            source_field="OTHER_PROFIT",
        )
        invalid = (
            registry_bytes(mappings=[mapping(), mapping()]),
            registry_bytes(bindings=[binding(), binding()]),
            registry_bytes(mappings=[mapping(), alternate]),
            registry_bytes(
                mappings=[mapping(), mapping(mapping_id="second_profit", metric_key="second_profit")],
                bindings=[binding(mapping_ids=["operating_profit", "second_profit"])],
            ),
            registry_bytes(bindings=[binding(mapping_ids=["missing_mapping"])]),
            registry_bytes(bindings=[binding(mapping_ids=[])]),
        )
        for raw in invalid:
            with self.subTest(raw_hash=hashlib.sha256(raw).hexdigest()), self.assertRaises(ValueError):
                SignedFinancialMappingRegistry.from_signed_bytes(
                    raw,
                    signature="fixture-signature",
                    key_id="fixture-key",
                    verifier=AcceptingVerifier(),
                )

    def test_mapping_registry_provenance_rejects_direct_forgery_and_public_mutation(self) -> None:
        registry = signed_registry()
        with self.assertRaises(TypeError):
            SignedFinancialMappingRegistry()
        forged = object.__new__(SignedFinancialMappingRegistry)
        for field in ("canonical_json", "registry_hash", "signature", "key_id", "mappings", "bindings"):
            object.__setattr__(forged, field, getattr(registry, field))
        with self.assertRaises(ValueError):
            extract(registry=forged)
        self.assertFalse(hasattr(formal_financial_schema, "_make_signed_financial_mapping_registry_type"))

        object.__setattr__(registry.mappings[0], "source_field", "EVIL_FIELD")
        with self.assertRaises(ValueError):
            extract(registry=registry)

    def test_mapping_registry_rejects_equality_spoofed_public_mutation(self) -> None:
        registry = signed_registry()
        object.__setattr__(registry.mappings[0], "source_field", EqualitySpoof())

        with self.assertRaises(ValueError):
            extract(registry=registry)

    def test_extracts_bj_duration_fact_with_verified_snapshot_lineage_and_raw_hash(self) -> None:
        document = fixture_document(rows=({"ITEM": "OPERATING_PROFIT", "VALUE": "120.0"},))
        result = extract(document=document, snapshot=fixture_snapshot(document))

        self.assertEqual(result.issues, ())
        self.assertEqual(len(result.facts), 1)
        fact = result.facts[0]
        self.assertIsInstance(fact, FormalFinancialFact)
        self.assertEqual(fact.security_id, "BJ430001")
        self.assertEqual(fact.statement, "income")
        self.assertEqual(fact.nature, "duration")
        self.assertEqual(fact.period_start, "2025-01-01")
        self.assertEqual(fact.value, 120.0)
        self.assertEqual(fact.source_content_sha256, "a" * 64)
        self.assertEqual(fact.source_refresh_generation, "fixture-index-v1")
        self.assertEqual(fact.accounting_basis, "consolidated")
        self.assertEqual(fact.raw_value_sha256, hashlib.sha256(b'"120.0"').hexdigest())

    def test_extraction_requires_an_exact_signed_binding_for_source_parser_versions_and_exchange(self) -> None:
        document = fixture_document()
        registry = signed_registry()
        parser_document = fixture_document(parser_id="other-parser")
        version_document = fixture_document(parser_version="other-v1")
        exchange_document = fixture_document(declared_security_id="SH600001")
        cases = (
            (document, fixture_snapshot(document, source="sse")),
            (document, fixture_snapshot(document, dataset="other_report")),
            (parser_document, fixture_snapshot(parser_document)),
            (version_document, fixture_snapshot(version_document)),
            (document, fixture_snapshot(document, mapping_version="other-map")),
            (exchange_document, fixture_snapshot(exchange_document, exchange="SH")),
        )
        for changed_document, changed_snapshot in cases:
            with self.subTest(snapshot=changed_snapshot):
                with self.assertRaises(ValueError):
                    extract(document=changed_document, snapshot=changed_snapshot, registry=registry)

    def test_extraction_hard_fails_on_document_snapshot_identity_and_lineage_mismatch(self) -> None:
        document = fixture_document()
        valid = fixture_snapshot(document)
        date_document = fixture_document(
            published_at_utc="2026-03-20T00:00:00+00:00",
            published_precision="date_only",
        )
        date_snapshot = fixture_snapshot(
            date_document,
            effective_at_utc="2026-03-21T07:00:00+00:00",
            effective_time_evidence_hash="c" * 64,
        )
        cases = (
            (fixture_document(declared_security_id="BJ430002"), valid, "identity"),
            (fixture_document(declared_period="2024-12-31"), valid, "identity"),
            (document, replace(valid, request_fingerprint="0" * 64), "fingerprint"),
            (document, replace(valid, parser_id="other-parser"), "parser"),
            (document, replace(valid, source_updated_at_utc=None), "lineage"),
            (fixture_document(bootstrap_calendar=True), valid, "bootstrap"),
            (document, replace(valid, effective_at_utc="2026-03-21T08:00:00+00:00"), "effective"),
            (date_document, replace(date_snapshot, effective_time_evidence_hash=None), "evidence"),
        )
        for changed_document, changed_snapshot, label in cases:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    extract(document=changed_document, snapshot=changed_snapshot)
        with self.assertRaises(ValueError):
            extract(created_at_utc="2026-09-04T00:00:00")

    def test_item_value_rows_emit_sorted_issues_without_fuzzy_or_legacy_fallback(self) -> None:
        cases = (
            (
                ({"ITEM": "UNMAPPED", "VALUE": "1"},),
                ("required_source_field_missing", "unknown_source_field"),
            ),
            (
                (
                    {"ITEM": "OPERATING_PROFIT", "VALUE": "1"},
                    {"ITEM": "OPERATING_PROFIT", "VALUE": "2"},
                ),
                ("duplicate_source_field",),
            ),
            (({"ITEM": "OPERATING_PROFIT", "VALUE": "1,000"},), ("nonnumeric_value",)),
            (
                ({"ITEM": "OPERATING_PROFIT", "VALUE": "1", "display": "profit"},),
                ("required_source_field_missing", "invalid_row_shape"),
            ),
            (
                ({"ITEM": "OPERATING PROFIT", "VALUE": "1"},),
                ("required_source_field_missing", "unknown_source_field"),
            ),
        )
        for rows, expected_codes in cases:
            with self.subTest(rows=rows):
                document = fixture_document(rows=rows)
                result = extract(document=document, snapshot=fixture_snapshot(document))
                self.assertEqual(result.facts, ())
                self.assertEqual(tuple(issue.code for issue in result.issues), expected_codes)

    def test_nonapplicable_mapping_is_not_reported_as_missing(self) -> None:
        document = fixture_document(accounting_basis="separate")
        result = extract(document=document, snapshot=fixture_snapshot(document))

        self.assertEqual(result.facts, ())
        self.assertEqual(tuple(issue.code for issue in result.issues), ("mapping_not_applicable",))

    def test_numeric_scalar_rules_preserve_raw_value_identity_and_normalize_zero(self) -> None:
        raw_values = ("1", 1, 1.0)
        facts = []
        for raw in raw_values:
            document = fixture_document(rows=({"ITEM": "OPERATING_PROFIT", "VALUE": raw},))
            facts.append(extract(document=document, snapshot=fixture_snapshot(document)).facts[0])
        self.assertEqual(tuple(fact.value for fact in facts), (1.0, 1.0, 1.0))
        self.assertEqual(len({fact.raw_value_sha256 for fact in facts}), 3)
        self.assertEqual(len({fact.id for fact in facts}), 3)

        zero_document = fixture_document(rows=({"ITEM": "OPERATING_PROFIT", "VALUE": "-0"},))
        zero_fact = extract(document=zero_document, snapshot=fixture_snapshot(zero_document)).facts[0]
        self.assertEqual(zero_fact.value, 0.0)
        self.assertEqual(math.copysign(1.0, zero_fact.value), 1.0)

        for raw in (True, math.nan, math.inf, "NaN", " 1", "1,000"):
            with self.subTest(raw=raw):
                document = fixture_document(rows=({"ITEM": "OPERATING_PROFIT", "VALUE": raw},))
                result = extract(document=document, snapshot=fixture_snapshot(document))
                self.assertEqual(result.facts, ())
                self.assertEqual(result.issues[0].code, "nonnumeric_value")

        arabic_indic = fixture_document(rows=({"ITEM": "OPERATING_PROFIT", "VALUE": "١٢"},))
        arabic_result = extract(document=arabic_indic, snapshot=fixture_snapshot(arabic_indic))
        self.assertEqual(arabic_result.facts, ())
        self.assertEqual(arabic_result.issues[0].code, "nonnumeric_value")

    def test_malformed_duplicate_mapped_item_blocks_a_valid_numeric_fact(self) -> None:
        document = fixture_document(
            rows=(
                {"ITEM": "OPERATING_PROFIT", "VALUE": "120.0"},
                {"ITEM": "OPERATING_PROFIT", "VALUE": {"nested": 1}},
            )
        )
        result = extract(document=document, snapshot=fixture_snapshot(document))

        self.assertEqual(result.facts, ())
        self.assertIn("duplicate_source_field", tuple(issue.code for issue in result.issues))
        self.assertIn("invalid_row_shape", tuple(issue.code for issue in result.issues))

    def test_malformed_duplicate_row_indices_preserve_source_order(self) -> None:
        document = fixture_document(
            rows=(
                {"ITEM": "OPERATING_PROFIT", "VALUE": {"nested": 1}},
                {"ITEM": "OPERATING_PROFIT", "VALUE": "120.0"},
            )
        )

        result = extract(document=document, snapshot=fixture_snapshot(document))

        duplicate = next(issue for issue in result.issues if issue.code == "duplicate_source_field")
        self.assertEqual(result.facts, ())
        self.assertEqual(duplicate.details["row_indices"], (0, 1))

    def test_all_malformed_duplicate_mapped_items_are_a_conflict_not_missing(self) -> None:
        document = fixture_document(
            rows=(
                {"ITEM": "OPERATING_PROFIT", "VALUE": {"bad": 1}},
                {"ITEM": "OPERATING_PROFIT", "VALUE": {"bad": 2}},
            )
        )

        result = extract(document=document, snapshot=fixture_snapshot(document))

        self.assertEqual(result.facts, ())
        self.assertIn("duplicate_source_field", tuple(issue.code for issue in result.issues))
        self.assertNotIn("required_source_field_missing", tuple(issue.code for issue in result.issues))

    def test_date_only_lineage_requires_utc_anchor_evidence_and_later_effective_time(self) -> None:
        document = fixture_document(
            published_at_utc="2026-03-20T00:00:00+00:00",
            published_precision="date_only",
        )
        snapshot = fixture_snapshot(
            document,
            effective_at_utc="2026-03-21T07:00:00+00:00",
            effective_time_evidence_hash="c" * 64,
        )
        fact = extract(document=document, snapshot=snapshot).facts[0]

        self.assertEqual(fact.published_precision, "date_only")
        self.assertEqual(fact.effective_time_evidence_hash, "c" * 64)
        self.assertEqual(fact.effective_at_utc, "2026-03-21T07:00:00+00:00")
        for changed in (
            replace(snapshot, effective_time_evidence_hash=None),
            replace(snapshot, effective_at_utc=document.published_at_utc),
            replace(snapshot, published_at_utc="2026-03-20T01:00:00+00:00"),
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    extract(document=document, snapshot=changed)

    def test_fact_identity_excludes_created_time_and_covers_scientific_and_evidence_values(self) -> None:
        fact = extract().facts[0]
        fields = dict(fact.to_dict())
        fields.pop("id")
        later = FormalFinancialFact.create(
            **{**fields, "created_at_utc": "2026-09-05T00:00:00+00:00"}
        )
        revised = FormalFinancialFact.create(**{**fields, "raw_value_sha256": "d" * 64})
        expected_identity = {
            key: value for key, value in fields.items() if key != "created_at_utc"
        }

        self.assertEqual(fact.id, hashlib.sha256(canonical_json_bytes(expected_identity)).hexdigest())
        self.assertEqual(fact.id, later.id)
        self.assertNotEqual(fact.id, revised.id)

    def test_fact_serialization_recomputes_identity_and_rejects_direct_or_mutated_objects(self) -> None:
        fact = extract().facts[0]
        record = fact.to_dict()

        self.assertIs(type(record), dict)
        self.assertEqual(canonical_json_bytes(record), canonical_bytes(record))
        self.assertEqual(FormalFinancialFact.from_dict(record), fact)
        with self.assertRaises(ValueError):
            FormalFinancialFact.from_dict({key: value for key, value in record.items() if key != "unit"})
        with self.assertRaises(ValueError):
            FormalFinancialFact.from_dict({**dict(record), "id": "0" * 64})
        with self.assertRaises(ValueError):
            FormalFinancialFact.from_dict({**dict(record), "value": "120.0"})
        with self.assertRaises(ValueError):
            FormalFinancialFact.from_dict({**dict(record), "value": int(record["value"])})
        zero_fields = dict(record)
        zero_fields.pop("id")
        zero_fields["value"] = 0.0
        zero = FormalFinancialFact.create(**zero_fields)
        zero_record = zero.to_dict()
        for noncanonical_zero in (-0.0, 0):
            with self.subTest(noncanonical_zero=noncanonical_zero), self.assertRaises(ValueError):
                FormalFinancialFact.from_dict(
                    {**zero_record, "value": noncanonical_zero}
                )
        with self.assertRaises(TypeError):
            FormalFinancialFact()

        object.__setattr__(fact, "value", 999.0)
        with self.assertRaises(ValueError):
            fact.to_dict()
        forged = object.__new__(FormalFinancialFact)
        for field, value in record.items():
            object.__setattr__(forged, field, value)
        with self.assertRaises(ValueError):
            forged.to_dict()
        self.assertFalse(hasattr(formal_financial_schema, "_make_formal_financial_fact_type"))

    def test_fact_seal_rejects_type_equivalent_numeric_mutation(self) -> None:
        fact = extract().facts[0]
        self.assertIs(type(fact.value), float)

        object.__setattr__(fact, "value", int(fact.value))

        with self.assertRaises(ValueError):
            fact.to_dict()

    def test_extraction_rejects_nonexact_snapshot_and_document_boundary_values(self) -> None:
        document = fixture_document()
        snapshot = fixture_snapshot(document)
        for changed in (
            replace(snapshot, verification_status="rejected"),
            replace(snapshot, content_sha256="A" * 64),
            replace(snapshot, security_id="bj430001"),
            replace(snapshot, snapshot_id="not-a-uuid"),
            replace(snapshot, refresh_generation=""),
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    extract(document=document, snapshot=changed)
        with self.assertRaises(ValueError):
            extract(document=fixture_document(declared_period=None), snapshot=snapshot)

    def test_issue_details_are_immutable_detached_and_legacy_facts_are_not_sources(self) -> None:
        raw_row = {"ITEM": "UNMAPPED", "VALUE": "1"}
        document = fixture_document(rows=(raw_row,))
        result = extract(document=document, snapshot=fixture_snapshot(document))
        unknown = next(issue for issue in result.issues if issue.code == "unknown_source_field")

        self.assertIsInstance(unknown, FormalFactIssue)
        self.assertIsNot(unknown.details, raw_row)
        self.assertNotIn("VALUE", unknown.details)
        with self.assertRaises(TypeError):
            unknown.details["tampered"] = True
        serialized = unknown.to_dict()
        self.assertEqual(
            canonical_json_bytes(serialized),
            canonical_bytes(
                {
                    "code": "unknown_source_field",
                    "details": {"row_index": 0, "source_field": "UNMAPPED"},
                    "mapping_id": None,
                    "source_field": "UNMAPPED",
                }
            ),
        )
        assert isinstance(serialized["details"], dict)
        serialized["details"]["row_index"] = 99
        self.assertEqual(unknown.details["row_index"], 0)
        raw_row["ITEM"] = "ALTERED"
        self.assertEqual(unknown.source_field, "UNMAPPED")

        legacy = FinancialFact.create(
            security_id="SH600000",
            statement="income",
            metric_key="revenue",
            period_start="2025-01-01",
            period_end="2025-12-31",
            period_kind="FY",
            value=1.0,
            unit="CNY",
            nature="duration",
            announced_at_utc="2026-03-20T08:00:00+00:00",
            effective_at_utc="2026-03-20T08:00:00+00:00",
            source_updated_at_utc=None,
            source_snapshot_id="legacy",
            source_field="OPERATING_PROFIT",
            raw_row_hash="e" * 64,
            mapping_version=MAPPING_VERSION,
            created_at="2026-09-04T00:00:00+00:00",
        )
        with self.assertRaises(ValueError):
            extract_formal_financial_facts(
                legacy,
                fixture_snapshot(fixture_document()),
                signed_registry(),
                "2026-09-04T00:00:00+00:00",
            )

    def test_issue_serialization_rejects_low_level_field_mutation(self) -> None:
        issue = FormalFactIssue(
            "sample_issue", None, None, {"nested": [{"answer": 1}]}
        )
        self.assertEqual(issue.to_dict()["details"], {"nested": [{"answer": 1}]})

        object.__setattr__(issue, "details", {"nested": [{"answer": 99}]})

        with self.assertRaises(ValueError):
            issue.to_dict()


if __name__ == "__main__":
    unittest.main()
