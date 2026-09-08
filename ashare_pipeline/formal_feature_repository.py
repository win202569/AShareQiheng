"""Verified persisted Formal V3 feature reads and explicit current-input selection.

Historical reads authenticate storage, release configuration and emitted source
evidence. V6 did not persist the complete historical candidate/issue manifest,
so only current selection can rebuild semantics with an injected complete input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import weakref
from typing import Protocol

from .formal_feature_contract import (
    FormalEvidenceRef,
    FormalFeatureBundle,
    FormalFeatureSlot,
    FormalFeatureValue,
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
from .formal_metric_features import evaluate_selected_features
from .formal_registry_manifest import FormalRegistryBundleLoader, VerifiedRegistryBundle
from .formal_snapshot_store import FormalSnapshotStore
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

    def _validate_signed_values(self, bundle: FormalFeatureBundle, registry: SignedFormalFeatureRegistry,
                                *, require_complete: bool = True) -> None:
        wire = bundle.to_dict()
        if wire["feature_registry_hash"] != registry.registry_hash or wire["contract_version"] != registry.contract_version:
            raise ValueError("formal feature registry header mismatch")
        if require_complete and wire["blockers"]:
            raise ValueError("formal feature bundle is blocked")
        slots = registry.slots_for_template(wire["template_id"])
        values = wire["values"]
        if [slot.slot_id for slot in slots] != [value["slot_id"] for value in values]:
            raise ValueError("formal feature signed slots mismatch")
        for slot, value in zip(slots, values, strict=True):
            if value["unit"] != slot.unit or value["formula_version"] != slot.formula_version:
                raise ValueError("formal feature signed unit or formula mismatch")
            if require_complete and (value["status"] not in {"derived", "missing"} or (slot.required and value["status"] != "derived")):
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
        return self._read_authenticated_bundle(input_hash=input_hash, require_complete=True)

    def _read_authenticated_bundle(self, *, input_hash: str, require_complete: bool) -> FormalFeatureBundle | None:
        """Authenticate every persisted byte; completeness is a separate read gate."""
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
        self._validate_signed_values(bundle, registry, require_complete=require_complete)
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


def _install_metric_projection():
    """Close mint authority over the real repository path and instance registry."""
    from . import formal_metric_features as metric_module
    from . import formal_financial_features as financial_module
    repository_type = FormalFeatureRepository
    original_init = repository_type.__init__
    read_bundle = repository_type._read_authenticated_bundle
    read_registry = repository_type._registry
    persisted_facts = repository_type._persisted_facts
    snapshot_identity = repository_type._snapshot_identity
    builder = build_formal_feature_bundle
    evaluator = evaluate_selected_features
    repositories, proofs = {}, {}
    fields = ("security_id", "as_of_utc", "template_id", "registry_manifest_hash",
        "feature_registry_hash", "input_hash", "bundle_hash", "required_feature_keys",
        "slots", "values", "blockers", "fact_snapshot_hash", "issue_snapshot_hash",
        "batch_id", "algorithm_version", "projection_hash")

    def wire(item):
        if type(item) is not VerifiedMetricFeatureProjection:
            raise ValueError("metric projection requires exact proof type")
        record = proofs.get(id(item))
        if record is None or record[0]() is not item:
            raise ValueError("metric projection has no repository proof")
        try:
            result = {field: getattr(item, field) for field in fields}
            for field in ("required_feature_keys", "slots", "values", "blockers"):
                if type(result[field]) is not tuple:
                    raise ValueError("metric projection collections must be immutable tuples")
                expected_type = FormalFeatureSlot if field == "slots" else FormalFeatureValue if field == "values" else str
                if any(type(value) is not expected_type for value in result[field]):
                    raise ValueError("metric projection collection members require exact types")
                result[field] = [x.to_dict() for x in result[field]] if field in {"slots", "values"} else list(result[field])
            if _canonical_json_bytes(result) != record[1]:
                raise ValueError("metric projection proof was mutated")
            return result
        except (AttributeError, TypeError, RecursionError) as error:
            raise ValueError("metric projection proof is malformed") from error

    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
    class VerifiedMetricFeatureProjection:
        """Each value has its own eligibility; blockers aggregate local reasons.

        A blocked/missing sibling slot does not invalidate a derived value.
        Consumers must recheck this seal before reading the requested slots.
        """
        security_id: str
        as_of_utc: str
        template_id: str
        registry_manifest_hash: str
        feature_registry_hash: str
        input_hash: str
        bundle_hash: str
        required_feature_keys: tuple[str, ...]
        slots: tuple[FormalFeatureSlot, ...]
        values: tuple[FormalFeatureValue, ...]
        blockers: tuple[str, ...]
        fact_snapshot_hash: str
        issue_snapshot_hash: str
        batch_id: str
        algorithm_version: str
        projection_hash: str

        def __init__(self, *args, **kwargs):
            raise TypeError("metric projections are created only by verified current repository reads")

        def to_dict(self):
            return wire(self)

        def canonical_bytes(self):
            return _canonical_json_bytes(wire(self))

        def require_verified(self):
            wire(self)

        def __copy__(self):
            raise TypeError("metric projection proof cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("metric projection proof cannot be copied")

    def dependency_state(self):
        store, files = self._store, self._bundle_store
        source = store._formal_snapshot_store
        verifier = store._registry_signature_verifier
        provider = self._current_input_provider
        refs = (source, verifier, store._formal_feature_bundle_store)
        methods = (getattr(self._verifier, "verify", None), getattr(verifier, "verify", None),
            getattr(provider, "resolve_current_inputs", None))
        method_ids = tuple((id(getattr(method, "__self__", None)), id(getattr(method, "__func__", method)))
            for method in methods)
        return (tuple(id(ref) for ref in refs), method_ids, str(store.db_path),
            str(files._root), files._root_fingerprint, str(getattr(source, "root", None)))

    def init(self, *args, **kwargs):
        if id(self) in repositories:
            raise ValueError("metric repository initialization may run only once")
        original_init(self, *args, **kwargs)
        identity = id(self)
        dependencies = (self._store, self._bundle_store, self._verifier, self._current_input_provider)
        repositories[identity] = (weakref.ref(self, lambda _, identity=identity: repositories.pop(identity, None)),
            dependencies, dependency_state(self))

    # Detect substituted public/private read paths as well as instance overrides.
    # Captured real methods make fake exact repository objects insufficient proof.
    checked_methods = tuple((cls, name, method)
        for cls in (StateStore, FormalFeatureBundleStore, FormalSnapshotStore, repository_type)
        for name, method in vars(cls).items()
        if (callable(method) or isinstance(method, (staticmethod, classmethod))) and name != "__init__")
    checked_calculations = tuple((module, name, value)
        for module in (metric_module, financial_module)
        for name, value in vars(module).items() if callable(value))

    def dependencies(self):
        record = repositories.get(id(self))
        if type(self) is not repository_type or record is None or record[0]() is not self:
            raise ValueError("metric repository was not safely initialized")
        current = (self._store, self._bundle_store, self._verifier, self._current_input_provider)
        if any(a is not b for a, b in zip(current, record[1], strict=True)):
            raise ValueError("metric repository dependencies changed")
        if dependency_state(self) != record[2]:
            raise ValueError("metric repository storage trust dependencies changed")
        source = self._store._formal_snapshot_store
        if type(source) is not FormalSnapshotStore:
            raise ValueError("metric repository requires an exact trusted source store")
        for cls, name, method in checked_methods:
            if vars(cls).get(name) is not method:
                raise ValueError("metric repository read dependency changed")
            for instance in (self, self._store, self._bundle_store, source):
                if type(instance) is cls and name in getattr(instance, "__dict__", {}):
                    raise ValueError("metric repository read dependency overridden")
        if build_formal_feature_bundle is not builder or evaluate_selected_features is not evaluator:
            raise ValueError("metric repository calculation dependency changed")
        if any(vars(module).get(name) is not value for module, name, value in checked_calculations):
            raise ValueError("metric repository calculation dependency changed")

    def select(self, security_id: str, as_of_utc: str, *, template_id: str,
               registry_manifest_hash: str, required_feature_keys: tuple[str, ...]) -> VerifiedMetricFeatureProjection | None:
        """Authenticate a current stored bundle and project required signed V6 slots."""
        request = _request(security_id, as_of_utc, template_id, registry_manifest_hash)
        if as_of_utc != "2026-08-31T07:00:00+00:00":
            raise ValueError("metric projection requires the exact frozen cutoff")
        if (type(required_feature_keys) is not tuple or not required_feature_keys
                or any(type(key) is not str for key in required_feature_keys)
                or tuple(sorted(set(required_feature_keys))) != required_feature_keys):
            raise ValueError("metric feature keys must be a nonempty sorted unique exact tuple")
        dependencies(self)
        provider = self._current_input_provider
        if provider is None:
            raise ValueError("formal feature current input provider is required")
        graph, registry = read_registry(self, registry_manifest_hash)
        slots_by_id = {slot.slot_id: slot for slot in registry.slots_for_template(template_id)}
        if any(key not in slots_by_id or not slots_by_id[key].required for key in required_feature_keys):
            raise ValueError("metric feature key is not an applicable required signed slot")
        slots = tuple(FormalFeatureSlot.from_dict(slots_by_id[key].to_dict()) for key in required_feature_keys)
        try:
            supplied = provider.resolve_current_inputs(**request)
        except Exception as error:
            raise ValueError("formal feature current input provider failed") from error
        identity = snapshot_identity(supplied, request)
        facts, fact_records = _fact_snapshot(supplied.facts, security_id)
        issues, issue_records = _issue_snapshot(supplied.issues)

        def check_current():
            dependencies(self)
            if (snapshot_identity(supplied, request) != identity
                    or _fact_snapshot(supplied.facts, security_id)[1] != fact_records
                    or _issue_snapshot(supplied.issues)[1] != issue_records):
                raise ValueError("metric feature current provider input changed")
            if persisted_facts(self, security_id) != fact_records:
                raise ValueError("metric feature persisted inputs changed or provider facts differ")

        check_current()
        expected = builder(security_id=security_id, as_of_utc=as_of_utc, template_id=template_id,
            facts=facts, issues=issues, registry=registry, registry_manifest=graph.manifest)
        if type(expected) is not FormalFeatureBundle:
            raise ValueError("metric feature builder returned an invalid bundle")
        expected_bytes = expected.canonical_bytes()
        check_current()
        stored = read_bundle(self, input_hash=expected.input_hash, require_complete=False)
        if stored is not None and stored.canonical_bytes() != expected_bytes:
            raise ValueError("metric feature stored bundle differs from rebuilt inputs")
        check_current()
        if stored is None:
            return None
        values, blockers = evaluator(slots=slots, facts=facts, issues=issues, as_of_utc=as_of_utc)
        # Re-read source lineage, root and the exact receipt after calculation:
        # a correct early read cannot bless a late SQL/file/source mutation.
        reread = read_bundle(self, input_hash=expected.input_hash, require_complete=False)
        if reread is None or reread.canonical_bytes() != expected_bytes:
            raise ValueError("metric feature persisted receipt changed during projection")
        check_current()
        payload = dict(request, feature_registry_hash=registry.registry_hash,
            input_hash=stored.input_hash, bundle_hash=stored.bundle_hash(),
            required_feature_keys=list(required_feature_keys), slots=[slot.to_dict() for slot in slots],
            values=[value.to_dict() for value in values], blockers=list(blockers),
            fact_snapshot_hash=hashlib.sha256(_canonical_json_bytes([json.loads(record) for record in fact_records])).hexdigest(),
            issue_snapshot_hash=hashlib.sha256(_canonical_json_bytes([json.loads(record) for record in issue_records])).hexdigest(),
            batch_id=identity[-1], algorithm_version="formal-metric-feature-projection-v1")
        payload["projection_hash"] = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
        result = object.__new__(VerifiedMetricFeatureProjection)
        for field in fields:
            value = payload[field]
            if field == "slots":
                value = tuple(FormalFeatureSlot.from_dict(item) for item in value)
            elif field == "values":
                value = tuple(FormalFeatureValue.from_dict(item) for item in value)
            elif field in {"required_feature_keys", "blockers"}:
                value = tuple(value)
            object.__setattr__(result, field, value)
        proof_id = id(result)
        proofs[proof_id] = (weakref.ref(result, lambda _, proof_id=proof_id: proofs.pop(proof_id, None)), _canonical_json_bytes(payload))
        return result

    repository_type.__init__ = init
    repository_type.select_current_verified_metric_features = select
    return VerifiedMetricFeatureProjection


VerifiedMetricFeatureProjection = _install_metric_projection()
del _install_metric_projection

__all__ = ["FormalFeatureRepository", "FormalFeatureCurrentInput", "FormalFeatureCurrentInputProvider", "VerifiedMetricFeatureProjection"]
