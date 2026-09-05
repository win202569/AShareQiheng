"""Security and serialization tests for the Formal V3 feature contract."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
import unittest

from ashare_pipeline.financial_schema import FinancialFact
from ashare_pipeline.formal_financial_schema import FormalFinancialFact
from ashare_pipeline.formal_registry_manifest import FormalRegistryManifest
from ashare_pipeline.formal_feature_contract import (
    FormalEvidenceRef,
    FormalFeatureBundle,
    FormalFeatureSlot,
    FormalFeatureValue,
    FormulaNode,
    SignedFormalFeatureRegistry,
    load_signed_feature_registry,
)


TEMPLATES = ("bank", "broker", "general_nonfinancial", "insurance", "real_estate")


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


class IntegerVerifier:
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> int:
        return 1


class EqualitySpoof:
    def __eq__(self, other: object) -> bool:
        return True


def fact_wire(fact_key: str = "income.revenue", period_key: str = "FY0") -> dict[str, object]:
    return {"op": "fact", "fact_key": fact_key, "period_key": period_key}


def slot_wire(template_id: str, *, suffix: str = "growth", **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "slot_id": f"{template_id}.{suffix}",
        "template_id": template_id,
        "dimension": "G",
        "required": True,
        "unit": "ratio",
        "formula": fact_wire(),
        "formula_version": "formula-v1",
    }
    value.update(changes)
    return value


def feature_registry_bytes(
    *, template_ids: tuple[str, ...] = TEMPLATES, slots: list[dict[str, object]] | None = None,
    **changes: object,
) -> bytes:
    if slots is None:
        slots = sorted((slot_wire(template) for template in template_ids), key=lambda item: item["slot_id"])
    value: dict[str, object] = {
        "schema_version": "formal-feature-registry-v1",
        "registry_role": "feature",
        "contract_version": "formal-features-v1",
        "source_registry_hash": "1" * 64,
        "mapping_registry_hash": "2" * 64,
        "template_ids": list(template_ids),
        "slots": slots,
    }
    value.update(changes)
    return canonical_bytes(value)


def registry_manifest(
    child_bytes: bytes, *, purpose: str = "official", feature_hash: str | None = None,
    source_hash: str = "1" * 64, mapping_hash: str = "2" * 64,
) -> FormalRegistryManifest:
    hashes = {
        "source_registry_hash": source_hash,
        "mapping_registry_hash": mapping_hash,
        "feature_registry_hash": feature_hash or hashlib.sha256(child_bytes).hexdigest(),
        "scoring_registry_hash": "3" * 64,
        "industry_registry_hash": "4" * 64,
        "cyclic_registry_hash": "5" * 64,
        "redline_registry_hash": "6" * 64,
        "status_registry_hash": "7" * 64,
        "event_registry_hash": "8" * 64,
    }
    raw = canonical_bytes(
        {
            "schema_version": "formal-registry-manifest-v1",
            "purpose": purpose,
            "approval_id": "approval-1" if purpose == "official" else None,
            **hashes,
        }
    )
    return FormalRegistryManifest.from_signed_bytes(
        raw, "fixture-signature", "fixture-key", AcceptingVerifier()
    )


def load_registry(raw: bytes, manifest: FormalRegistryManifest | None = None):
    return load_signed_feature_registry(
        raw,
        "fixture-signature",
        "fixture-key",
        AcceptingVerifier(),
        registry_manifest=manifest,
    )


def formal_fact(**changes: object) -> FormalFinancialFact:
    values: dict[str, object] = {
        "security_id": "SH600001",
        "statement": "income",
        "metric_key": "revenue",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "period_kind": "FY",
        "value": 100.0,
        "unit": "CNY",
        "nature": "duration",
        "accounting_basis": "consolidated",
        "published_at_utc": "2026-03-20T08:00:00+00:00",
        "published_precision": "timestamp",
        "effective_at_utc": "2026-03-20T08:00:00+00:00",
        "effective_time_evidence_hash": None,
        "source_updated_at_utc": "2026-03-20T08:30:00+00:00",
        "captured_at_utc": "2026-09-04T00:00:00+00:00",
        "source_snapshot_id": "11111111-1111-4111-8111-111111111111",
        "source_content_sha256": "a" * 64,
        "source_refresh_generation": "refresh-v1",
        "source_producing_task_id": "task-1",
        "source_field": "REVENUE",
        "raw_value_sha256": "b" * 64,
        "parser_id": "parser-v1",
        "parser_version": "parser-version-v1",
        "mapping_version": "mapping-v1",
        "created_at_utc": "2026-09-04T00:00:00+00:00",
    }
    values.update(changes)
    return FormalFinancialFact.create(**values)


def evidence(**fact_changes: object) -> FormalEvidenceRef:
    return FormalEvidenceRef.from_formal_fact(formal_fact(**fact_changes))


def feature_value(**changes: object) -> FormalFeatureValue:
    value: dict[str, object] = {
        "slot_id": "general_nonfinancial.growth",
        "value": 0.25,
        "unit": "ratio",
        "status": "derived",
        "formula_version": "formula-v1",
        "evidence": (evidence(),),
        "missing_reason": None,
    }
    value.update(changes)
    return FormalFeatureValue(**value)


def feature_bundle(**changes: object) -> FormalFeatureBundle:
    values: dict[str, object] = {
        "schema_version": 1,
        "contract_version": "formal-features-v1",
        "security_id": "SH600001",
        "as_of_utc": "2026-09-04T00:00:00+00:00",
        "template_id": "general_nonfinancial",
        "registry_manifest_hash": "c" * 64,
        "feature_registry_hash": "d" * 64,
        "input_hash": "e" * 64,
        "values": (feature_value(),),
        "history_endpoints": ("2024-12-31", "2025-12-31"),
        "comparable_quarter_keys": ("2025Q1", "2025Q2"),
        "blockers": (),
    }
    values.update(changes)
    return FormalFeatureBundle(**values)


class FormalFeatureContractTests(unittest.TestCase):
    def test_registry_requires_canonical_unique_json_and_exact_signature_true(self) -> None:
        raw = feature_registry_bytes(template_ids=("general_nonfinancial",))
        invalid = (
            b" " + raw,
            raw[:-1] + b',"slots":[]}',
            raw.replace(b'"feature"', b'"mapping"'),
            raw.replace(b'"formal-feature-registry-v1"', b'"other"'),
            b'\xff',
            b'{"contract_version":NaN}',
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate[:24]), self.assertRaises(ValueError):
                load_signed_feature_registry(
                    candidate, "fixture-signature", "fixture-key", AcceptingVerifier()
                )
        for verifier in (RejectingVerifier(), RaisingVerifier(), IntegerVerifier()):
            with self.subTest(verifier=type(verifier).__name__), self.assertRaisesRegex(
                ValueError, "signature"
            ):
                load_signed_feature_registry(
                    raw, "fixture-signature", "fixture-key", verifier
                )

    def test_registry_has_no_defaults_and_validates_every_signed_slot(self) -> None:
        one_template = ("general_nonfinancial",)
        valid = load_registry(feature_registry_bytes(template_ids=one_template))
        self.assertFalse(valid.release_eligible)
        self.assertEqual(len(valid.slots_for_template("general_nonfinancial")), 1)
        invalid = (
            feature_registry_bytes(template_ids=()),
            feature_registry_bytes(template_ids=("general_nonfinancial", "general_nonfinancial")),
            feature_registry_bytes(template_ids=("unknown",)),
            feature_registry_bytes(template_ids=one_template, slots=[]),
            feature_registry_bytes(
                template_ids=one_template,
                slots=[slot_wire("general_nonfinancial"), slot_wire("general_nonfinancial")],
            ),
            feature_registry_bytes(template_ids=one_template, slots=[slot_wire("bank")]),
            feature_registry_bytes(template_ids=one_template, slots=[slot_wire("general_nonfinancial", required=1)]),
            feature_registry_bytes(template_ids=one_template, slots=[slot_wire("general_nonfinancial", dimension="X")]),
            feature_registry_bytes(template_ids=one_template, slots=[slot_wire("general_nonfinancial", unit="USD")]),
        )
        for raw in invalid:
            with self.subTest(raw=hashlib.sha256(raw).hexdigest()), self.assertRaises(ValueError):
                load_registry(raw)

    def test_registry_release_eligibility_is_bound_to_exact_official_root(self) -> None:
        raw = feature_registry_bytes()
        official = registry_manifest(raw)
        registry = load_registry(raw, official)
        self.assertTrue(registry.release_eligible)
        registry.require_release_eligible()
        self.assertEqual(tuple(slot.template_id for slot in registry.slots), TEMPLATES)

        roots = (
            None,
            registry_manifest(raw, purpose="test"),
            registry_manifest(raw, feature_hash="f" * 64),
            registry_manifest(raw, source_hash="9" * 64),
            registry_manifest(raw, mapping_hash="9" * 64),
        )
        for root in roots:
            with self.subTest(root=root):
                self.assertFalse(load_registry(raw, root).release_eligible)

        incomplete = feature_registry_bytes(template_ids=("general_nonfinancial",))
        self.assertFalse(load_registry(incomplete, registry_manifest(incomplete)).release_eligible)

    def test_registry_provenance_rejects_direct_forged_mutated_and_spoofed_objects(self) -> None:
        raw = feature_registry_bytes()
        registry = load_registry(raw, registry_manifest(raw))
        with self.assertRaises(TypeError):
            SignedFormalFeatureRegistry()
        forged = object.__new__(SignedFormalFeatureRegistry)
        with self.assertRaises(ValueError):
            forged.slots_for_template("bank")

        object.__setattr__(registry, "contract_version", EqualitySpoof())
        with self.assertRaises(ValueError):
            registry.slots_for_template("bank")
        self.assertFalse(hasattr(registry, "verifier"))

        healthy = load_registry(raw, registry_manifest(raw))
        object.__setattr__(healthy, "release_eligible", False)
        with self.assertRaises(ValueError):
            _ = healthy.release_eligible
        with self.assertRaises(ValueError):
            healthy.require_release_eligible()

    def test_registry_rejects_forged_or_mutated_root_instead_of_downgrading(self) -> None:
        raw = feature_registry_bytes()
        root = registry_manifest(raw)
        forged = object.__new__(FormalRegistryManifest)
        for field in (
            "manifest_hash", "purpose", "approval_id", "canonical_json", "signature", "key_id",
            "source_registry_hash", "mapping_registry_hash", "feature_registry_hash",
            "scoring_registry_hash", "industry_registry_hash", "cyclic_registry_hash",
            "redline_registry_hash", "status_registry_hash", "event_registry_hash",
        ):
            object.__setattr__(forged, field, getattr(root, field))
        with self.assertRaises(ValueError):
            load_registry(raw, forged)
        object.__setattr__(root, "feature_registry_hash", EqualitySpoof())
        with self.assertRaises(ValueError):
            load_registry(raw, root)

    def test_formula_accepts_every_closed_operation_and_roundtrips(self) -> None:
        a = fact_wire("income.a")
        b = fact_wire("income.b")
        wires = (
            a,
            {"op": "add", "left": a, "right": b},
            {"op": "subtract", "left": a, "right": b},
            {"op": "divide", "left": a, "right": b},
            {"op": "cagr", "left": a, "right": b, "intervals": 3},
            {"op": "median", "items": [a, b]},
            {"op": "minimum", "items": [a, b]},
        )
        for wire in wires:
            with self.subTest(op=wire["op"]):
                node = FormulaNode.from_dict(wire)
                self.assertEqual(node.to_dict(), wire)

    def test_formula_rejects_unknown_keys_executable_or_malformed_children(self) -> None:
        a = fact_wire("income.a")
        b = fact_wire("income.b")
        cycle: dict[str, object] = {"op": "add", "right": b}
        cycle["left"] = cycle
        invalid: tuple[object, ...] = (
            "__import__('os').system('x')",
            lambda: None,
            {"op": "unknown"},
            {"op": "fact", "fact_key": " income.a", "period_key": "FY0"},
            {"op": "fact", "fact_key": "income.a", "period_key": "FY0", "extra": 1},
            {"op": "divide", "left": a},
            {"op": "divide", "left": "income.a", "right": b},
            {"op": "cagr", "left": a, "right": b, "intervals": 0},
            {"op": "cagr", "left": a, "right": b, "intervals": True},
            {"op": "cagr", "left": a, "right": b, "intervals": -1},
            {"op": "cagr", "left": a, "right": b, "intervals": math.inf},
            {"op": "median", "items": [a]},
            {"op": "median", "items": [a, a]},
            {"op": "minimum", "items": [b, a]},
            cycle,
        )
        for wire in invalid:
            with self.subTest(wire=repr(wire)[:80]), self.assertRaises(ValueError):
                FormulaNode.from_dict(wire)  # type: ignore[arg-type]

    def test_registry_rejects_equality_spoofed_formula_items_mutation(self) -> None:
        raw = feature_registry_bytes()
        registry = load_registry(raw, registry_manifest(raw))
        formula = registry.slots[0].formula
        object.__setattr__(formula, "items", EqualitySpoof())

        with self.assertRaises(ValueError):
            _ = registry.release_eligible

    def test_evidence_copies_every_sealed_fact_lineage_field(self) -> None:
        fact = formal_fact()
        ref = FormalEvidenceRef.from_formal_fact(fact)
        self.assertEqual(
            ref.to_dict(),
            {
                "formal_fact_id": fact.id,
                "source_snapshot_id": "11111111-1111-4111-8111-111111111111",
                "source_content_sha256": "a" * 64,
                "source_refresh_generation": "refresh-v1",
                "source_field": "REVENUE",
                "raw_value_sha256": "b" * 64,
                "published_at_utc": "2026-03-20T08:00:00+00:00",
                "published_precision": "timestamp",
                "effective_at_utc": "2026-03-20T08:00:00+00:00",
                "mapping_version": "mapping-v1",
            },
        )
        self.assertEqual(FormalEvidenceRef.from_dict(ref.to_dict()), ref)

    def test_evidence_rejects_legacy_generic_fact_and_low_level_mutation(self) -> None:
        with self.assertRaises(ValueError):
            FormalEvidenceRef.from_formal_fact({})
        with self.assertRaises(ValueError):
            FormalEvidenceRef.from_formal_fact(object.__new__(FinancialFact))
        fact = formal_fact()
        object.__setattr__(fact, "source_refresh_generation", "changed")
        with self.assertRaises(ValueError):
            FormalEvidenceRef.from_formal_fact(fact)
        ref = evidence()
        object.__setattr__(ref, "source_field", "OTHER")
        with self.assertRaises(ValueError):
            ref.to_dict()

    def test_evidence_cannot_reseal_after_refresh_generation_mutation(self) -> None:
        ref = evidence()
        original = ref.to_dict()
        object.__setattr__(ref, "source_refresh_generation", "refresh-v2")

        with self.assertRaises(AttributeError):
            ref.__post_init__()
        with self.assertRaises(ValueError):
            FormalEvidenceRef.__init__(ref, **original)
        self.assertEqual(ref.source_refresh_generation, "refresh-v2")
        with self.assertRaises(ValueError):
            ref.to_dict()

    def test_feature_value_enforces_every_status_shape_and_canonical_float_wire(self) -> None:
        derived = feature_value(value=1)
        self.assertIs(type(derived.value), float)
        for status in ("missing", "blocked", "not_applicable"):
            item = feature_value(
                slot_id=f"general_nonfinancial.{status}",
                value=None,
                status=status,
                evidence=(),
                missing_reason="not available",
            )
            self.assertEqual(item.status, status)
        invalid = (
            {"value": None},
            {"evidence": ()},
            {"missing_reason": "reason"},
            {"value": math.nan},
            {"value": math.inf},
            {"value": True},
            {"status": "missing", "value": 1.0, "evidence": (), "missing_reason": "reason"},
            {"status": "blocked", "value": None, "evidence": (evidence(),), "missing_reason": "reason"},
            {"status": "not_applicable", "value": None, "evidence": (), "missing_reason": None},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                feature_value(**changes)
        wire = feature_value(value=1.0).to_dict()
        wire["value"] = 1
        with self.assertRaises(ValueError):
            FormalFeatureValue.from_dict(wire)
        wire["value"] = -0.0
        with self.assertRaises(ValueError):
            FormalFeatureValue.from_dict(wire)

    def test_feature_value_requires_sorted_unique_exact_evidence(self) -> None:
        refs = tuple(sorted(
            (evidence(raw_value_sha256="b" * 64), evidence(raw_value_sha256="c" * 64)),
            key=lambda item: item.formal_fact_id,
        ))
        self.assertEqual(feature_value(evidence=refs).evidence, refs)
        for supplied in ((refs[1], refs[0]), (refs[0], refs[0]), [refs[0]]):
            with self.subTest(supplied=supplied), self.assertRaises(ValueError):
                feature_value(evidence=supplied)

    def test_feature_value_cannot_reseal_after_mutation(self) -> None:
        item = feature_value()
        original = {
            "slot_id": item.slot_id,
            "value": item.value,
            "unit": item.unit,
            "status": item.status,
            "formula_version": item.formula_version,
            "evidence": item.evidence,
            "missing_reason": item.missing_reason,
        }
        object.__setattr__(item, "slot_id", "general_nonfinancial.changed")

        with self.assertRaises(AttributeError):
            item.__post_init__()
        with self.assertRaises(ValueError):
            FormalFeatureValue.__init__(item, **original)
        self.assertEqual(item.slot_id, "general_nonfinancial.changed")
        with self.assertRaises(ValueError):
            item.to_dict()

    def test_bundle_roundtrip_hash_and_exact_non_scoring_wire(self) -> None:
        bundle = feature_bundle()
        wire = bundle.to_dict()
        self.assertEqual(FormalFeatureBundle.from_dict(wire), bundle)
        self.assertEqual(bundle.bundle_hash(), hashlib.sha256(bundle.canonical_bytes()).hexdigest())
        self.assertEqual(bundle.canonical_bytes(), canonical_bytes(wire))
        self.assertTrue({"score", "confidence", "pool", "percentile"}.isdisjoint(wire))

    def test_bundle_validates_identity_time_hashes_order_and_exact_wire_types(self) -> None:
        for security_id in ("SH600001", "SZ000001", "BJ430001"):
            self.assertEqual(feature_bundle(security_id=security_id).security_id, security_id)
        invalid = (
            {"schema_version": True},
            {"schema_version": 2},
            {"security_id": "sh600001"},
            {"security_id": "HK000001"},
            {"as_of_utc": "2026-09-04T08:00:00+08:00"},
            {"template_id": "fallback"},
            {"registry_manifest_hash": "A" * 64},
            {"feature_registry_hash": "d" * 63},
            {"values": [feature_value()]},
            {"values": (feature_value(), feature_value())},
            {"history_endpoints": ("2025-12-31", "2024-12-31")},
            {"history_endpoints": ("2025-12-31", "2025-12-31")},
            {"comparable_quarter_keys": ("2025Q2", "2025Q1")},
            {"comparable_quarter_keys": ("2025Q5",)},
            {"blockers": ("z", "a")},
            {"blockers": ("same", "same")},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                feature_bundle(**changes)

        wire = feature_bundle().to_dict()
        wire["extra"] = None
        with self.assertRaises(ValueError):
            FormalFeatureBundle.from_dict(wire)

    def test_bundle_and_value_detect_valid_looking_low_level_mutation(self) -> None:
        item = feature_value()
        object.__setattr__(item, "slot_id", "general_nonfinancial.changed")
        with self.assertRaises(ValueError):
            item.to_dict()
        bundle = feature_bundle()
        object.__setattr__(bundle, "security_id", "SZ000001")
        for action in (bundle.to_dict, bundle.canonical_bytes, bundle.bundle_hash):
            with self.subTest(action=action.__name__), self.assertRaises(ValueError):
                action()

    def test_bundle_cannot_reseal_after_mutation(self) -> None:
        bundle = feature_bundle()
        original = {
            "schema_version": bundle.schema_version,
            "contract_version": bundle.contract_version,
            "security_id": bundle.security_id,
            "as_of_utc": bundle.as_of_utc,
            "template_id": bundle.template_id,
            "registry_manifest_hash": bundle.registry_manifest_hash,
            "feature_registry_hash": bundle.feature_registry_hash,
            "input_hash": bundle.input_hash,
            "values": bundle.values,
            "history_endpoints": bundle.history_endpoints,
            "comparable_quarter_keys": bundle.comparable_quarter_keys,
            "blockers": bundle.blockers,
        }
        object.__setattr__(bundle, "security_id", "SZ000001")

        with self.assertRaises(AttributeError):
            bundle.__post_init__()
        with self.assertRaises(ValueError):
            FormalFeatureBundle.__init__(bundle, **original)
        self.assertEqual(bundle.security_id, "SZ000001")
        with self.assertRaises(ValueError):
            bundle.to_dict()

    def test_populated_forged_bundle_cannot_run_initialization_or_seal_hook(self) -> None:
        healthy = feature_bundle()
        fields = {
            "schema_version": healthy.schema_version,
            "contract_version": healthy.contract_version,
            "security_id": healthy.security_id,
            "as_of_utc": healthy.as_of_utc,
            "template_id": healthy.template_id,
            "registry_manifest_hash": healthy.registry_manifest_hash,
            "feature_registry_hash": healthy.feature_registry_hash,
            "input_hash": healthy.input_hash,
            "values": healthy.values,
            "history_endpoints": healthy.history_endpoints,
            "comparable_quarter_keys": healthy.comparable_quarter_keys,
            "blockers": healthy.blockers,
        }
        forged = object.__new__(FormalFeatureBundle)
        for name, value in fields.items():
            object.__setattr__(forged, name, value)

        with self.assertRaises(ValueError):
            FormalFeatureBundle.__init__(forged, **fields)
        with self.assertRaises(AttributeError):
            forged.__post_init__()
        with self.assertRaises(ValueError):
            forged.to_dict()


if __name__ == "__main__":
    unittest.main()
