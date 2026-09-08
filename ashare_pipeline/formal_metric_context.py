"""Authenticated frozen population and signed industry Context prerequisites.

Proofs capture evidence, not indefinite latest-state validity. A metric factory
must call recheck_batch after reading every member's features and before use.
"""

from datetime import date, datetime
import hashlib
from types import MappingProxyType
import weakref

from . import formal_context_repository as context_module
from .formal_context_repository import FormalContextRepository
from .formal_context_schema import FormalContextFact, FormalContextRegistry, SignedContextRequestResolver, _canonical, _load
from .formal_registry_manifest import FormalRegistryBundleLoader, FormalRegistryManifest, VerifiedRegistryBundle
from .formal_repository_identity import _require_repository_initialization
from .formal_scoring_registry import FormalScoringRegistry
from .formal_snapshot_repository import FormalSnapshotRepository
from .formal_snapshot_store import FormalSnapshotStore
from .formal_universe import canonical_security_id
from .state_store import StateStore, _formal_frozen_universe_payload, _plain_formal_universe_json


_FREEZE = "2026-08-31T07:00:00+00:00"


def _text(value):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("industry requires trimmed nonempty strings")
    return value


def _industry(bundle, scoring):
    if type(bundle) is not VerifiedRegistryBundle or type(scoring) is not FormalScoringRegistry:
        raise ValueError("industry requires exact verified registry types")
    bundle.require_official()
    scoring.require_official(bundle)
    wire = _load(bundle.blob("industry").canonical_json)
    if set(wire) != set("registry_role schema_version purpose classification_system source_version effective_date context_scope_key memberships mapping_sha256".split()):
        raise ValueError("industry registry has missing or extra fields")
    if (wire["registry_role"] != "industry" or wire["schema_version"] != "formal-industry-registry-v1"
            or wire["purpose"] != "official" or wire["classification_system"] != "SW2021"):
        raise ValueError("industry registry role/version/purpose/classification mismatch")
    _text(wire["source_version"])
    _text(wire["context_scope_key"])
    effective = wire["effective_date"]
    if type(effective) is not str or date.fromisoformat(effective).isoformat() != effective or effective > "2026-08-31":
        raise ValueError("industry effective date is invalid or future")
    memberships = wire["memberships"]
    if type(memberships) is not list or not memberships:
        raise ValueError("industry memberships must be a nonempty array")
    ids = []
    for member in memberships:
        if type(member) is not dict or set(member) != {"security_id", "template_id", "primary_industry", "secondary_industry"}:
            raise ValueError("industry member has missing or extra fields")
        ids.append(canonical_security_id(member["security_id"]))
        scoring.template_for(_text(member["template_id"]))
        _text(member["primary_industry"])
        _text(member["secondary_industry"])
    if ids != sorted(set(ids)):
        raise ValueError("industry members must be canonical sorted unique securities")
    mapping = {key: wire[key] for key in ("classification_system", "source_version", "effective_date", "memberships")}
    if wire["mapping_sha256"] != hashlib.sha256(_canonical(mapping)).hexdigest():
        raise ValueError("industry mapping digest mismatch")
    return wire


def _immutable(value):
    if type(value) is dict:
        return MappingProxyType({key: _immutable(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_immutable(item) for item in value)
    return value


def _metric_context_types():
    """Keep mint authority and all proof state outside publicly writable slots."""
    repositories, proofs = {}, {}
    reader = StateStore.get_verified_formal_frozen_universe
    batch_reader = FormalContextRepository.get_verified_many
    loader = FormalRegistryBundleLoader.load
    parse_industry = _industry
    serialize_universe = _formal_frozen_universe_payload
    require_context = context_module._require_authentic_context_repository
    require_initialized = _require_repository_initialization
    # Only paths consumed by universe, registry and Context/raw verification.
    paths = {
        StateStore: "__init__ _connect _transaction _require_registry_verifier _formal_token _verify_formal_signature _formal_blob_snapshot _formal_blob_from_connection _formal_root_snapshot _formal_root_from_connection get_formal_registry_blob get_formal_registry_manifest _require_formal_snapshot_store _configured_formal_snapshot_store_for_repository get_verified_formal_frozen_universe _formal_universe_from_connection _formal_universe_extraction_from_payload _require_formal_universe_source_lineage _formal_snapshot_row_to_ref _formal_verified_snapshot_ref_from_connection _require_formal_snapshot_receipt_lineage _formal_task_snapshot_receipt_from_connection get_formal_task_snapshot_receipt _formal_task_public _require_formal_verified_task_state _get_formal_snapshot_verified_by_manifest _formal_ref_matches_projection list_formal_context_facts get_formal_snapshot".split(),
        FormalContextRepository: "__init__ _load _candidates _select get_verified_many resolve_verified_calendar_binding".split(),
        FormalSnapshotRepository: "__init__ get_verified_by_manifest read_verified_raw".split(),
        FormalSnapshotStore: "__init__ read_verified_raw validate_stored_snapshot _validate_inspection_inputs _validate_formal_fetch_values _validate_request_values _require_version_identifier _require_recomputed_verification _read_calendar_binding _resolve_calendar_binding _require_calendar_binding_identity _official_request_from_manifest _require_exact_manifest_payload _validate_content_file _read_manifest _require_sha256 _safe_path_component _path_inside_root _require_target_within_root".split(),
        FormalRegistryBundleLoader: ["__init__", "load"],
        VerifiedRegistryBundle: ["require_official", "blob"],
        FormalRegistryManifest: ["from_signed_bytes", "require_official", "assert_member_hashes"],
        FormalScoringRegistry: ["require_official", "template_for"],
        FormalContextRegistry: ["load", "descriptor_for"],
        SignedContextRequestResolver: ["__init__", "resolve", "_resolve", "_resolve_historical"],
        FormalContextFact: ["from_dict", "to_dict", "canonical_bytes"],
    }
    checked = tuple((cls, name, vars(cls)[name]) for cls, names in paths.items() for name in names)
    context_functions = tuple((name, getattr(context_module, name)) for name in
        ("_validate_stored_fact", "_list_context_facts", "_row_fact", "_require_context_producer", "_prove_historical_calendar"))

    def method_identity(method):
        return (id(getattr(method, "__self__", None)), id(getattr(method, "__func__", method)))

    def state(store, context, verifier):
        try:
            require_context(context)
            snapshots = context._snapshots
            raw = store._formal_snapshot_store
            for dependency in (store, snapshots, raw):
                require_initialized(dependency)
            if (type(store) is not StateStore or type(context) is not FormalContextRepository
                    or type(snapshots) is not FormalSnapshotRepository or type(raw) is not FormalSnapshotStore
                    or context._state_store is not store or snapshots._state_store is not store
                    or snapshots._raw_store is not raw or context._verifier is not verifier
                    or store._registry_signature_verifier is not verifier
                    or snapshots.root != raw.root or not callable(getattr(verifier, "verify", None))):
                raise ValueError("metric Context requires exact matching stores, repositories and verifier")
            for cls, name, method in checked:
                if vars(cls).get(name) is not method:
                    raise ValueError("metric Context validation dependency changed")
                for instance in (store, context, snapshots, raw, verifier):
                    if type(instance) is cls and name in vars(instance):
                        raise ValueError("metric Context read dependency overridden")
            if any(getattr(context_module, name) is not function for name, function in context_functions):
                raise ValueError("metric Context source validation dependency changed")
            if _industry is not parse_industry or _formal_frozen_universe_payload is not serialize_universe:
                raise ValueError("metric Context contract dependency changed")
            return (id(store), id(context), id(verifier), id(snapshots), id(raw), str(store.db_path),
                str(raw.root), str(snapshots.root), method_identity(verifier.verify),
                method_identity(getattr(raw, "_calendar_binding_resolver", None)))
        except (AttributeError, TypeError) as error:
            raise ValueError("metric Context trust dependencies are uninitialized") from error

    def dependencies(repository):
        record = repositories.get(id(repository))
        if type(repository) is not FormalMetricContextRepository or record is None or record[0]() is not repository:
            raise ValueError("metric Context repository is uninitialized or copied")
        store, context, verifier, snapshot = record[1:]
        if state(store, context, verifier) != snapshot:
            raise ValueError("metric Context trust dependencies changed")
        return store, context, verifier

    def proof_record(proof, cls, repository=None):
        record = proofs.get(id(proof))
        if type(proof) is not cls or record is None or record[0]() is not proof:
            raise ValueError("metric Context proof is forged or copied")
        if repository is not None and record[1]() is not repository:
            raise ValueError("metric Context proof belongs to another repository")
        return record

    class Proof:
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("metric Context proofs require authenticated repository reads")

        def __getattr__(self, name):
            wire = _load(proof_record(self, type(self))[2])
            if name not in wire:
                raise AttributeError(name)
            return _immutable(wire[name])

        def to_dict(self):
            return _load(proof_record(self, type(self))[2])

        def canonical_bytes(self):
            return proof_record(self, type(self))[2]

        def require_verified(self):
            proof_record(self, type(self))

        def __copy__(self):
            raise TypeError("metric Context proof cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("metric Context proof cannot be copied")

    class VerifiedMetricUniverse(Proof):
        __slots__ = ()

    class VerifiedMetricIndustryBatch(Proof):
        __slots__ = ()

    def mint(repository, cls, payload, scoring=None):
        proof = object.__new__(cls)
        identity = id(proof)
        proofs[identity] = (weakref.ref(proof, lambda _: proofs.pop(identity, None)), weakref.ref(repository),
            _canonical(payload), scoring)
        return proof

    def read_universe(repository, frozen_input_hash, scoring):
        store, _, verifier = dependencies(repository)
        frozen = reader(store, frozen_input_hash)
        if frozen is None:
            dependencies(repository)
            return None
        if datetime.fromisoformat(frozen.as_of_utc) != datetime.fromisoformat(_FREEZE):
            raise ValueError("metric universe requires the fixed freeze instant")
        graph = loader(FormalRegistryBundleLoader(store, verifier), frozen.registry_manifest_hash)
        industry = parse_industry(graph, scoring)
        payload = dict(schema_version="formal-metric-universe-v1", as_of_utc=_FREEZE,
            frozen_as_of_utc=frozen.as_of_utc, registry_manifest_hash=frozen.registry_manifest_hash,
            frozen_input_hash=frozen.frozen_input_hash, universe_hash=frozen.universe_hash,
            source_audit_hash=frozen.source_audit_hash,
            industry_registry_hash=graph.manifest.industry_registry_hash,
            mapping_sha256=industry["mapping_sha256"], industry=industry,
            security_ids=[member.security_id for member in frozen.members],
            frozen_universe=_plain_formal_universe_json(serialize_universe(frozen)),
            source_receipts=[store.get_formal_task_snapshot_receipt(source.snapshot.producing_task_id) for source in frozen.sources])
        payload["population_hash"] = hashlib.sha256(_canonical(payload["security_ids"])).hexdigest()
        dependencies(repository)
        return payload

    def resolve_payload(repository, universe):
        _, context, _ = dependencies(repository)
        signed = universe["industry"]
        ids = tuple(universe["security_ids"])
        facts = batch_reader(context, "industry_snapshot", signed["context_scope_key"], ids,
            _FREEZE, universe["registry_manifest_hash"])
        members = {member["security_id"]: member for member in signed["memberships"]}
        entries, selected = {}, {}
        for sid in ids:
            member, fact = members.get(sid), facts[sid]
            selected[sid] = None if fact is None else dict(id=fact.id, canonical_fact=_load(fact.canonical_bytes()))
            base = dict(security_id=sid, registry_manifest_hash=universe["registry_manifest_hash"],
                universe_hash=universe["universe_hash"], frozen_input_hash=universe["frozen_input_hash"])
            reason = None
            if member is None:
                reason = "signed_membership_absent"
            elif fact is None:
                reason = "context_absent"
            else:
                expected = {key: signed[key] for key in ("classification_system", "source_version", "effective_date", "mapping_sha256")}
                expected.update({key: member[key] for key in ("primary_industry", "secondary_industry")})
                if dict(fact.value) != expected:
                    reason = "context_membership_mismatch"
            if reason is not None:
                entries[sid] = dict(base, status="pending", pending_reason=reason)
            else:
                entries[sid] = dict(base, status="assigned", pending_reason=None,
                    template_id=member["template_id"], primary_industry=member["primary_industry"],
                    secondary_industry=member["secondary_industry"], context_fact_id=fact.id,
                    context_canonical_sha256=hashlib.sha256(fact.canonical_bytes()).hexdigest())
        payload = dict(schema_version="formal-metric-industry-batch-v1", registry_manifest_hash=universe["registry_manifest_hash"],
            frozen_input_hash=universe["frozen_input_hash"], universe_hash=universe["universe_hash"],
            universe_proof_sha256=hashlib.sha256(_canonical(universe)).hexdigest(),
            population_hash=universe["population_hash"], mapping_sha256=universe["mapping_sha256"],
            industry_registry_hash=universe["industry_registry_hash"], entries=entries, selected_context=selected)
        payload["batch_hash"] = hashlib.sha256(_canonical(payload)).hexdigest()
        dependencies(repository)
        return payload

    class FormalMetricContextRepository:
        __slots__ = ("__weakref__",)

        def __init__(self, state_store, context_repository, *, registry_signature_verifier):
            if type(self) is not FormalMetricContextRepository or id(self) in repositories:
                raise ValueError("metric Context repository initialization is exact and single-use")
            snapshot = state(state_store, context_repository, registry_signature_verifier)
            identity = id(self)
            repositories[identity] = (weakref.ref(self, lambda _: repositories.pop(identity, None)),
                state_store, context_repository, registry_signature_verifier, snapshot)

        def load_universe(self, frozen_input_hash, *, scoring_registry):
            payload = read_universe(self, frozen_input_hash, scoring_registry)
            return None if payload is None else mint(self, VerifiedMetricUniverse, payload, scoring_registry)

        def resolve_industries(self, universe_proof):
            dependencies(self)
            record = proof_record(universe_proof, VerifiedMetricUniverse, self)
            payload = resolve_payload(self, _load(record[2]))
            return mint(self, VerifiedMetricIndustryBatch, payload)

        def recheck_batch(self, universe_proof, industry_batch):
            """Final full-population closure check, once after all feature reads."""
            dependencies(self)
            universe_record = proof_record(universe_proof, VerifiedMetricUniverse, self)
            batch_record = proof_record(industry_batch, VerifiedMetricIndustryBatch, self)
            universe = _load(universe_record[2])
            current = read_universe(self, universe["frozen_input_hash"], universe_record[3])
            if current is None or _canonical(current) != universe_record[2]:
                raise ValueError("metric universe or signed mapping changed during batch")
            if _canonical(resolve_payload(self, current)) != batch_record[2]:
                raise ValueError("metric industry Context correction or absence changed during batch")
            dependencies(self)

        def __copy__(self):
            raise TypeError("metric Context repository cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("metric Context repository cannot be copied")

    return FormalMetricContextRepository, VerifiedMetricUniverse, VerifiedMetricIndustryBatch


FormalMetricContextRepository, VerifiedMetricUniverse, VerifiedMetricIndustryBatch = _metric_context_types()
del _metric_context_types

__all__ = ["FormalMetricContextRepository", "VerifiedMetricUniverse", "VerifiedMetricIndustryBatch"]
