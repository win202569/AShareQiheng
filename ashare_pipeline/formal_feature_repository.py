"""Verified persisted Formal V3 feature reads and explicit current-input selection.

Historical reads authenticate storage, release configuration and emitted source
evidence. V6 did not persist the complete historical candidate/issue manifest,
so only current selection can rebuild semantics with an injected complete input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .formal_feature_contract import (
    FormalEvidenceRef,
    FormalFeatureBundle,
    SignedFormalFeatureRegistry,
    _canonical_json_bytes,
    _require_hash,
    _require_text,
    _require_utc,
    _snapshot_json,
    load_signed_feature_registry,
)
from .formal_feature_store import FormalFeatureBundleStore
from .formal_financial_features import build_formal_feature_bundle
from .formal_financial_schema import FormalFactIssue, FormalFinancialFact
from .formal_registry_manifest import FormalRegistryBundleLoader, VerifiedRegistryBundle
from .formal_universe import canonical_security_id
from .state_store import StateStore


_TEMPLATES = frozenset({"bank", "broker", "general_nonfinancial", "insurance", "real_estate"})
_IDENTITY = ("security_id", "as_of_utc", "template_id", "registry_manifest_hash")
_METADATA_ONLY = frozenset({
    "id", "bundle_hash", "bundle_manifest_hash", "bundle_path", "manifest_path", "created_at_utc",
})


@dataclass(frozen=True, slots=True)
class FormalFeatureCurrentInput:
    """One complete provider-owned generation; batch_id is an audit label."""

    security_id: str
    as_of_utc: str
    template_id: str
    registry_manifest_hash: str
    batch_id: str
    facts: tuple[FormalFinancialFact, ...]
    issues: tuple[FormalFactIssue, ...]
    complete: bool


class FormalFeatureCurrentInputProvider(Protocol):
    """Explicit trust dependency responsible for exhaustive current issues."""

    def resolve_current_inputs(
        self, *, security_id: str, as_of_utc: str, template_id: str,
        registry_manifest_hash: str,
    ) -> FormalFeatureCurrentInput: ...


def _request(security_id: str, as_of_utc: str, template_id: str, root_hash: str) -> dict[str, str]:
    if type(template_id) is not str or template_id not in _TEMPLATES:
        raise ValueError("invalid formal feature template")
    if type(security_id) is not str or canonical_security_id(security_id) != security_id:
        raise ValueError("formal feature security must be canonical")
    _require_utc(as_of_utc, "formal feature cutoff")
    _require_hash(root_hash, "formal feature root hash")
    return dict(zip(_IDENTITY, (security_id, as_of_utc, template_id, root_hash), strict=True))


def _fact_snapshot(facts: object, security_id: str) -> tuple[tuple[FormalFinancialFact, ...], tuple[bytes, ...]]:
    if type(facts) is not tuple:
        raise ValueError("formal feature facts must be an exact finite tuple")
    detached = []
    records = []
    for fact in facts:
        if type(fact) is not FormalFinancialFact:
            raise ValueError("formal feature facts require exact sealed formal facts")
        wire = fact.to_dict()
        if wire["security_id"] != security_id:
            raise ValueError("formal feature fact security mismatch")
        records.append(_canonical_json_bytes(wire))
        detached.append(FormalFinancialFact.from_dict(wire))
    return tuple(detached), tuple(sorted(records))


def _issue_snapshot(issues: object) -> tuple[tuple[FormalFactIssue, ...], tuple[bytes, ...]]:
    if type(issues) is not tuple:
        raise ValueError("formal feature issues must be an exact finite tuple")
    detached = []
    records = []
    for issue in issues:
        if type(issue) is not FormalFactIssue:
            raise ValueError("formal feature issues require exact sealed formal issues")
        wire = issue.to_dict()
        records.append(_canonical_json_bytes(wire))
        detached.append(FormalFactIssue(**wire))
    return tuple(detached), tuple(sorted(records))


class FormalFeatureRepository:
    def __init__(
        self, store: StateStore, bundle_store: FormalFeatureBundleStore, *,
        registry_signature_verifier: object,
        current_input_provider: FormalFeatureCurrentInputProvider | None = None,
    ) -> None:
        if type(store) is not StateStore or type(bundle_store) is not FormalFeatureBundleStore:
            raise ValueError("formal feature repository requires exact stores")
        if not callable(getattr(registry_signature_verifier, "verify", None)):
            raise ValueError("formal feature registry signature verifier is required")
        if current_input_provider is not None and not callable(getattr(current_input_provider, "resolve_current_inputs", None)):
            raise ValueError("formal feature current input provider is invalid")
        self._store = store
        self._bundle_store = bundle_store
        self._verifier = registry_signature_verifier
        self._current_input_provider = current_input_provider

    def _registry(self, root_hash: str) -> tuple[VerifiedRegistryBundle, SignedFormalFeatureRegistry]:
        graph = FormalRegistryBundleLoader(self._store, self._verifier).load(root_hash)
        graph.require_official()
        child = graph.blob("feature")
        registry = load_signed_feature_registry(
            child.canonical_json, child.signature, child.key_id, self._verifier,
            registry_manifest=graph.manifest,
        )
        registry.require_release_eligible()
        if (graph.manifest.manifest_hash != root_hash
                or graph.manifest.feature_registry_hash != child.registry_hash
                or registry.registry_hash != child.registry_hash
                or registry.source_registry_hash != graph.manifest.source_registry_hash
                or registry.mapping_registry_hash != graph.manifest.mapping_registry_hash):
            raise ValueError("formal feature registry root/child binding mismatch")
        return graph, registry

    def _metadata(self, input_hash: str) -> dict[str, object] | None:
        row = self._store.get_formal_feature_bundle_row(input_hash)
        if row is None:
            return None
        if type(row) is not dict:
            raise ValueError("formal feature metadata must be a detached dictionary")
        return _snapshot_json(row, label="formal feature metadata")

    def _validate_signed_values(self, bundle: FormalFeatureBundle, registry: SignedFormalFeatureRegistry) -> None:
        wire = bundle.to_dict()
        if wire["feature_registry_hash"] != registry.registry_hash or wire["contract_version"] != registry.contract_version:
            raise ValueError("formal feature registry header mismatch")
        if wire["blockers"]:
            raise ValueError("formal feature bundle is blocked")
        slots = registry.slots_for_template(wire["template_id"])
        values = wire["values"]
        if [slot.slot_id for slot in slots] != [value["slot_id"] for value in values]:
            raise ValueError("formal feature signed slots mismatch")
        for slot, value in zip(slots, values, strict=True):
            if value["unit"] != slot.unit or value["formula_version"] != slot.formula_version:
                raise ValueError("formal feature signed unit or formula mismatch")
            if value["status"] not in {"derived", "missing"} or (slot.required and value["status"] != "derived"):
                raise ValueError("formal feature slot is not score eligible")
            # The exact FormalFeatureValue boundary already enforces null value,
            # empty evidence and canonical missing reason for a missing slot.

    def _validate_evidence(self, bundle: FormalFeatureBundle) -> None:
        wire = bundle.to_dict()
        facts, _ = _fact_snapshot(
            self._store.list_formal_financial_facts(security_id=wire["security_id"]),
            wire["security_id"],
        )
        by_id = {}
        for fact in facts:
            fact_wire = fact.to_dict()
            if fact_wire["id"] in by_id:
                raise ValueError("formal feature evidence facts are duplicated")
            by_id[fact_wire["id"]] = (fact, fact_wire)
        cutoff = datetime.fromisoformat(wire["as_of_utc"])
        for value in wire["values"]:
            for evidence in value["evidence"]:
                found = by_id.get(evidence["formal_fact_id"])
                if found is None:
                    raise ValueError("formal feature evidence fact is missing")
                fact, fact_wire = found
                expected = FormalEvidenceRef.from_formal_fact(fact).to_dict()
                if _canonical_json_bytes(expected) != _canonical_json_bytes(evidence):
                    raise ValueError("formal feature evidence lineage mismatch")
                for field in ("published_at_utc", "effective_at_utc", "source_updated_at_utc"):
                    if fact_wire[field] is not None and datetime.fromisoformat(fact_wire[field]) > cutoff:
                        raise ValueError("formal feature evidence is after cutoff")

    def get_verified_formal_feature_bundle(self, *, input_hash: str) -> FormalFeatureBundle | None:
        """Read an exact historical receipt; this does not rebuild historical inputs."""
        _require_hash(input_hash, "formal feature input hash")
        row = self._metadata(input_hash)
        if row is None:
            return None
        before = _canonical_json_bytes(row)
        receipt_fields = {"bundle_path", "manifest_path", "bundle_hash", "bundle_manifest_hash"}
        if not receipt_fields <= row.keys():
            raise ValueError("formal feature receipt metadata is incomplete")
        receipt = self._bundle_store.recover_verified_receipt(
            bundle_path=row["bundle_path"], manifest_path=row["manifest_path"],
            bundle_hash=row["bundle_hash"], manifest_hash=row["bundle_manifest_hash"],
        )
        bundle = self._bundle_store.read_verified(receipt)
        if type(bundle) is not FormalFeatureBundle:
            raise ValueError("formal feature repository requires an exact formal bundle")
        wire = bundle.to_dict()
        if set(row) != set(wire) | _METADATA_ONLY:
            raise ValueError("formal feature metadata keys mismatch")
        _require_utc(row["created_at_utc"], "formal feature creation time")
        expected = {**wire, "id": receipt.bundle_hash, "bundle_hash": receipt.bundle_hash,
            "bundle_manifest_hash": receipt.manifest_hash, "bundle_path": receipt.bundle_path,
            "manifest_path": receipt.manifest_path, "created_at_utc": row["created_at_utc"]}
        if (wire["input_hash"] != input_hash or bundle.bundle_hash() != receipt.bundle_hash
                or _canonical_json_bytes(expected) != before):
            raise ValueError("formal feature database/file projection mismatch")
        _, registry = self._registry(wire["registry_manifest_hash"])
        self._validate_signed_values(bundle, registry)
        self._validate_evidence(bundle)
        if _canonical_json_bytes(self._metadata(input_hash)) != before:
            raise ValueError("formal feature metadata changed while reading")
        return bundle

    def _persisted_facts(self, security_id: str) -> tuple[bytes, ...]:
        return _fact_snapshot(self._store.list_formal_financial_facts(security_id=security_id), security_id)[1]

    @staticmethod
    def _snapshot_identity(snapshot: object, request: dict[str, str]) -> tuple[str, ...]:
        if type(snapshot) is not FormalFeatureCurrentInput:
            raise ValueError("formal feature provider must return an exact current input")
        try:
            identity = tuple(getattr(snapshot, key) for key in _IDENTITY)
            batch_id = snapshot.batch_id
            complete = snapshot.complete
        except AttributeError as error:
            raise ValueError("formal feature current input is incomplete") from error
        if any(type(value) is not str for value in identity) or identity != tuple(request.values()):
            raise ValueError("formal feature current input request mismatch")
        _require_text(batch_id, "formal feature current batch id")
        if any(127 <= ord(character) <= 159 for character in batch_id):
            raise ValueError("formal feature current batch id must be control-free")
        if complete is not True:
            raise ValueError("formal feature current input must be explicitly complete")
        return (*identity, batch_id)

    def select_current_verified_formal_feature_bundle(
        self, security_id: str, as_of_utc: str, *, template_id: str, registry_manifest_hash: str,
    ) -> FormalFeatureBundle | None:
        """Rebuild current semantics from a trusted complete finite provider snapshot."""
        request = _request(security_id, as_of_utc, template_id, registry_manifest_hash)
        provider = self._current_input_provider
        if provider is None:
            raise ValueError("formal feature current input provider is required")
        graph, registry = self._registry(registry_manifest_hash)
        try:
            supplied = provider.resolve_current_inputs(**request)
        except Exception as error:
            raise ValueError("formal feature current input provider failed") from error
        identity = self._snapshot_identity(supplied, request)
        facts, fact_records = _fact_snapshot(supplied.facts, security_id)
        issues, issue_records = _issue_snapshot(supplied.issues)
        if fact_records != self._persisted_facts(security_id):
            raise ValueError("formal feature provider facts do not match persisted inputs")
        if (self._snapshot_identity(supplied, request) != identity
                or _fact_snapshot(supplied.facts, security_id)[1] != fact_records
                or _issue_snapshot(supplied.issues)[1] != issue_records):
            raise ValueError("formal feature current input changed while snapshotting")
        expected = build_formal_feature_bundle(
            security_id=security_id, as_of_utc=as_of_utc, template_id=template_id,
            facts=facts, issues=issues, registry=registry, registry_manifest=graph.manifest,
        )
        if type(expected) is not FormalFeatureBundle:
            raise ValueError("formal feature builder returned an invalid bundle")
        expected_bytes = expected.canonical_bytes()
        if self._persisted_facts(security_id) != fact_records:
            raise ValueError("formal feature persisted inputs changed during construction")
        result = self.get_verified_formal_feature_bundle(input_hash=expected.input_hash)
        if result is not None and (type(result) is not FormalFeatureBundle or result.canonical_bytes() != expected_bytes):
            raise ValueError("formal feature current bundle differs from rebuilt inputs")
        if self._persisted_facts(security_id) != fact_records:
            raise ValueError("formal feature persisted inputs changed during lookup")
        return result


__all__ = ["FormalFeatureRepository", "FormalFeatureCurrentInput", "FormalFeatureCurrentInputProvider"]
