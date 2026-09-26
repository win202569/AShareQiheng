"""Complete, atomically published policy-adjusted valuation inputs."""

import hashlib
import json
import weakref
from decimal import Decimal
from types import MappingProxyType

from .formal_context_repository import FormalContextRepository
from .formal_feature_repository import FormalFeatureRepository
from .formal_metric_batch_guard import _metric_batch_guard
from .formal_metric_engine import FormalMetricInputRepository, MetricInputBatch
from .formal_policy_repository import FormalPolicyRepository, VerifiedPolicyResultBatch
from .formal_policy_values import digest
from .formal_range_store import FormalRangeStore
from .formal_registry_manifest import FormalRegistryBundleLoader
from .formal_scoring_registry import FormalScoringRegistry
from .formal_policy_registry import FormalPolicyRegistry
from .formal_valuation_adapter_contract import FormalValuationAdapterRegistry
from . import formal_valuation_adapter as adapter_module
from .formal_batch_read_journal import FormalBatchReadJournal, _issue_current_ticket


_V_METRICS = ("V.enterprise_value_or_sustainable_roe", "V.normalized_earnings_yield",
              "V.normalized_free_cash_flow_yield")
_FREEZE = "2026-08-31T07:00:00+00:00"


def _install_valuation_engine():
    repositories, proofs = {}, {}
    own_members = ()
    json_module, hashlib_module = json, hashlib
    encode, decode, sha256, hash_payload, decimal_type = (
        json.dumps, json.loads, hashlib.sha256, digest, Decimal)
    guard_factory = _metric_batch_guard
    load_root = FormalRegistryBundleLoader.load
    adapter_source = adapter_module
    adapter_owner = adapter_source._require_valuation_adapter_owner
    evaluate = adapter_owner()
    metric_build = FormalMetricInputRepository._build_batch_in_owner_scope
    policy_build = FormalPolicyRepository._build_batch_in_owner_scope
    metric_verify = MetricInputBatch.require_verified
    policy_verify = VerifiedPolicyResultBatch.require_verified
    adapter_verify = FormalValuationAdapterRegistry.require_current_bundle
    scoring_verify = FormalScoringRegistry.require_official
    checked = tuple((cls, name, value) for cls in
        (FormalFeatureRepository, FormalContextRepository, FormalRangeStore,
         FormalMetricInputRepository, FormalPolicyRepository, MetricInputBatch,
         VerifiedPolicyResultBatch, FormalValuationAdapterRegistry,
         FormalScoringRegistry, FormalPolicyRegistry, FormalRegistryBundleLoader,
         FormalBatchReadJournal)
        for name, value in vars(cls).items() if callable(value))

    def freeze(value):
        if type(value) is dict:
            return MappingProxyType({key: freeze(item) for key, item in value.items()})
        if type(value) in (list, tuple):
            return tuple(freeze(item) for item in value)
        return value

    def interfaces():
        if any(vars(cls).get(name) is not value for cls, name, value in checked):
            raise ValueError("valuation publication dependency changed")
        if any(set(vars(cls)) != {name for name, _ in members} or any(
                vars(cls)[name] is not value for name, value in members)
                for cls, members in own_members):
            raise ValueError("valuation authority interface changed")
        if (globals().get("_metric_batch_guard") is not guard_factory
                or globals().get("adapter_module") is not adapter_source
                or adapter_source._require_valuation_adapter_owner is not adapter_owner
                or adapter_owner() is not evaluate
                or globals().get("digest") is not hash_payload
                or globals().get("Decimal") is not decimal_type
                or globals().get("json") is not json_module or json_module.dumps is not encode
                or json_module.loads is not decode or globals().get("hashlib") is not hashlib_module
                or hashlib_module.sha256 is not sha256):
            raise ValueError("valuation publication dependency changed")

    def dependencies(repository):
        interfaces()
        saved = repositories.get(id(repository))
        if (type(repository) is not FormalValuationRepository or saved is None
                or saved[0]() is not repository):
            raise ValueError("valuation repository is forged or copied")
        feature, context, ranges, verifier, metric_repo, policy_repo, original = saved[1:]
        current = (id(feature), id(context), id(ranges), id(verifier), id(feature._store),
            id(feature._bundle_store), id(feature._current_input_provider), id(context._snapshots))
        if current != original or feature._store is not context._state_store:
            raise ValueError("valuation repository graph changed")
        # Both authenticated repositories recheck their own provider, context,
        # range and verifier dependencies when called below.
        return feature, context, ranges, verifier, metric_repo, policy_repo

    def check_decimal(saved):
        canonical = saved[5][6]
        public = saved[1]["adjusted_value"]
        if canonical is None:
            valid = public is None
        else:
            try:
                valid = (type(canonical) is str and type(public) is decimal_type
                    and public.is_finite()
                    and public.as_tuple() == decimal_type(canonical).as_tuple())
            except (ArithmeticError, TypeError, ValueError):
                valid = False
        if not valid:
            raise ValueError("adjusted valuation proof Decimal differs from canonical value")

    def saved_proof(proof, cls, publication=None):
        saved = proofs.get(id(proof))
        if (type(proof) is not cls or saved is None or saved[0]() is not proof
                or (not saved[4][0] if publication is None else saved[4] is not publication)):
            raise ValueError("adjusted valuation proof is forged, copied, unpublished or revoked")
        seal = saved[5]
        if (saved[2] is not seal[0] or saved[1]["batch_hash"] != seal[1]
                or saved[1]["registry_manifest_hash"] != seal[4]
                or saved[1]["frozen_input_hash"] != seal[5]):
            raise ValueError("adjusted valuation proof canonical binding changed")
        if cls is PolicyAdjustedValuationInput:
            if (saved[1]["security_id"] != seal[2]
                    or saved[1]["metric_id"] != seal[3]):
                raise ValueError("adjusted valuation proof row identity changed")
            check_decimal(saved)
        elif cls is PolicyAdjustedValuationBatch:
            if (saved[1]["inputs"] is not seal[7]
                    or saved[3]["index"] is not seal[8]):
                raise ValueError("adjusted valuation proof batch index changed")
        return saved

    def record(proof, cls):
        interfaces()
        return saved_proof(proof, cls)

    def validate_prepared(batch, children, publication):
        """Close the whole unpublished child set before final source checkpoint."""
        interfaces()
        saved = saved_proof(batch, PolicyAdjustedValuationBatch, publication)
        batch_wire = decode(saved[2])
        index = saved[3]["index"]
        if (saved[1]["inputs"] != children or len(children) != len(batch_wire["inputs"])
                or len(index) != len(children)):
            raise ValueError("adjusted valuation proof children differ from canonical batch")
        for child, row in zip(children, batch_wire["inputs"], strict=True):
            child_saved = saved_proof(child, PolicyAdjustedValuationInput, publication)
            if (child_saved[2] != encode(dict(row, batch_hash=batch_wire["batch_hash"]),
                    sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                    allow_nan=False).encode()
                    or index.get((row["security_id"], row["metric_id"])) is not child):
                raise ValueError("adjusted valuation proof children differ from canonical batch")

    class SealedMeta(type):
        def __setattr__(cls, name, value):
            raise TypeError("valuation authority types are immutable")

        def __delattr__(cls, name):
            raise TypeError("valuation authority types are immutable")

    class Proof(metaclass=SealedMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("adjusted valuation proofs require a complete publication")

        def __getattribute__(self, name):
            record(self, type(self))
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            data = record(self, type(self))[1]
            if name not in data:
                raise AttributeError(name)
            return data[name]

        def require_verified(self):
            record(self, type(self))

        def canonical_bytes(self):
            return record(self, type(self))[2]

        def to_dict(self):
            return decode(record(self, type(self))[2])

        def __copy__(self):
            raise TypeError("adjusted valuation proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("adjusted valuation proofs cannot be copied")

    class PolicyAdjustedValuationInput(Proof):
        __slots__ = ()

    class PolicyAdjustedValuationBatch(Proof):
        __slots__ = ()

        def input_for(self, security_id, metric_id):
            if type(security_id) is not str or type(metric_id) is not str:
                raise ValueError("valuation selectors require exact strings")
            batch = record(self, PolicyAdjustedValuationBatch)
            result = batch[3]["index"].get((security_id, metric_id))
            if result is None:
                raise ValueError("security or V metric is outside complete adjusted batch")
            row = record(result, PolicyAdjustedValuationInput)
            if (row[4] is not batch[4] or row[1]["security_id"] != security_id
                    or row[1]["metric_id"] != metric_id
                    or row[1]["batch_hash"] != batch[1]["batch_hash"]
                    or row[1]["registry_manifest_hash"] != batch[1]["registry_manifest_hash"]
                    or row[1]["frozen_input_hash"] != batch[1]["frozen_input_hash"]):
                raise ValueError("adjusted valuation proof index differs from bound row")
            return result

    def mint(cls, payload, publication, *, attributes=None, private=None):
        proof = object.__new__(cls)
        data = dict(payload)
        data.update(attributes or {})
        wire = encode(payload, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False).encode()
        identity = id(proof)
        frozen = freeze(data)
        sealed_private = None if private is None else {
            "index": MappingProxyType(dict(private["index"]))}
        seal = (wire, payload["batch_hash"], payload.get("security_id"),
            payload.get("metric_id"), payload["registry_manifest_hash"],
            payload["frozen_input_hash"], payload.get("adjusted_value"),
            frozen.get("inputs"), None if sealed_private is None else sealed_private["index"])
        proofs[identity] = (weakref.ref(proof, lambda _: proofs.pop(identity, None)),
            frozen, wire, sealed_private, publication, seal)
        return proof

    def prepare_adjusted_rows(base_batch, policy_batch, adapter_registry):
        """Prepare canonical rows from authenticated batch wires; mint no authority."""
        base, policy, adapter = base_batch.to_dict(), policy_batch.to_dict(), adapter_registry.to_dict()
        security_ids = base["security_ids"]
        if (security_ids != sorted(set(security_ids))
                or tuple(base["metric_ids"]) != _V_METRICS
                or policy["security_ids"] != security_ids
                or base["as_of_utc"] != _FREEZE
                or any(base[key] != policy[key] for key in
                    ("registry_manifest_hash", "frozen_input_hash", "universe_hash", "as_of_utc"))
                or base["registry_manifest_hash"] != adapter["registry_manifest_hash"]
                or base["registry_hashes"] != policy["role_hashes"]
                or any(adapter["role_hashes"].get(role) != value for role, value in base["registry_hashes"].items())
                or policy["evidence_batch"]["universe"]["population_hash"] != base["population_hash"]
                or policy["evidence_batch"]["industry"]["batch_hash"] != base["industry_batch_hash"]):
            raise ValueError("valuation input batches have incompatible frozen or registry identities")
        if (len(base["inputs"]) != len(security_ids) * 3
                or [(row["security_id"], row["metric_id"]) for row in base["inputs"]]
                    != [(sid, mid) for sid in security_ids for mid in _V_METRICS]
                or [result["security_id"] for result in policy["results"]] != security_ids):
            raise ValueError("valuation input batches are incomplete or unordered")
        coverage = {(row["template_id"], row["metric_id"]): row for row in adapter["coverage"]}
        adapters = {(row["template_id"], row["metric_id"]): row for row in adapter["adapters"]}
        policy_by_sid = {row["security_id"]: row for row in policy["results"]}
        rows = []
        for metric in base["inputs"]:
            sid, mid, tid = metric["security_id"], metric["metric_id"], metric["template_id"]
            result = policy_by_sid[sid]
            if tid is None or not result["decisions"]:
                if (result["decisions"] or not result["pending_requirements"]
                        or (tid is None and metric["invalid_reason"] != "invalid_template")):
                    raise ValueError("unassigned valuation member has inconsistent policy evidence")
                adjustment = dict(status="pending_policy_evidence",
                    reason="invalid_template" if tid is None else "applicability_unresolved",
                    adjusted_value=None, metric_input_hash=metric["input_hash"],
                    policy_result_hash=result["result_hash"], decision_hash=None,
                    adapter_definition_hash=None, policy_dependency=None, operation=None,
                    original_metric_value=None, original_current_profit=None,
                    normalized_profit=None)
            else:
                decisions = [item for item in result["decisions"] if item["role"] == "cyclic"]
                if len(decisions) != 1 or result["security_id"] != sid:
                    raise ValueError("valuation member lacks a unique genuine cyclic decision")
                decision = decisions[0]
                dependencies = decision["parameters"].get("valuation_dependencies", [])
                selected = [item for item in dependencies if item["metric_id"] == mid]
                if len(selected) != 1 or coverage.get((tid, mid), {}).get("policy_dependency") != selected[0]["policy_dependency"]:
                    raise ValueError("signed adapter coverage differs from policy decision")
                adjustment = evaluate(metric=metric, policy_result=result,
                    cyclic_decision=decision, dependency=selected[0], adapter=adapters.get((tid, mid)))
            row = dict(registry_manifest_hash=base["registry_manifest_hash"],
                frozen_input_hash=base["frozen_input_hash"], universe_hash=base["universe_hash"],
                population_hash=base["population_hash"], as_of_utc=base["as_of_utc"],
                industry_batch_hash=base["industry_batch_hash"], security_id=sid,
                metric_id=mid, template_id=tid, primary_industry=metric["primary_industry"],
                secondary_industry=metric["secondary_industry"],
                original_metric=metric, policy_result=result, adjustment=adjustment,
                status=adjustment["status"], reason=adjustment["reason"],
                adjusted_value=adjustment["adjusted_value"])
            row["input_hash"] = hash_payload(row)
            rows.append(row)
        return tuple(rows)

    class FormalValuationRepository(metaclass=SealedMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, feature_repository, context_repository, range_store, *, registry_signature_verifier):
            if type(self) is not FormalValuationRepository or id(self) in repositories:
                raise ValueError("valuation repository initialization must be exact and single-use")
            interfaces()
            metric_repo = FormalMetricInputRepository(feature_repository, context_repository,
                registry_signature_verifier=registry_signature_verifier)
            policy_repo = FormalPolicyRepository(feature_repository, context_repository, range_store,
                registry_signature_verifier=registry_signature_verifier)
            original = (id(feature_repository), id(context_repository), id(range_store),
                id(registry_signature_verifier), id(feature_repository._store),
                id(feature_repository._bundle_store), id(feature_repository._current_input_provider),
                id(context_repository._snapshots))
            identity = id(self)
            repositories[identity] = (weakref.ref(self, lambda _: repositories.pop(identity, None)),
                feature_repository, context_repository, range_store, registry_signature_verifier,
                metric_repo, policy_repo, original)

        def build_batch(self, frozen_input_hash, *, scoring_registry, policy_registry,
                        valuation_adapter_registry):
            feature, _, _, verifier, metric_repo, policy_repo = dependencies(self)
            if (type(frozen_input_hash) is not str or type(scoring_registry) is not FormalScoringRegistry
                    or type(policy_registry) is not FormalPolicyRegistry
                    or type(valuation_adapter_registry) is not FormalValuationAdapterRegistry):
                raise ValueError("valuation publication requires exact authenticated inputs")
            publication = [False]
            prepared = None
            scope = None
            try:
                with guard_factory(feature._current_input_provider, feature._store) as guard:
                    frozen = feature._store.get_verified_formal_frozen_universe(frozen_input_hash)
                    if frozen is None:
                        raise ValueError("valuation frozen input is absent")
                    population = tuple(sorted(member.security_id for member in frozen.members))
                    required = tuple((sid, mid) for sid in population for mid in _V_METRICS) + tuple(
                        (sid,) for sid in population)
                    scope = FormalBatchReadJournal.open(self,
                        registry_manifest_hash=frozen.registry_manifest_hash,
                        as_of_utc=_FREEZE, population=population, required_keys=required,
                        frozen_input_hash=frozen_input_hash)
                    base, metric_ticket, metric_revoke = metric_build(metric_repo, frozen_input_hash,
                        scoring_registry=scoring_registry, metric_ids=_V_METRICS,
                        owner_scope=scope)
                    policy, policy_ticket, policy_revoke = policy_build(policy_repo, frozen_input_hash,
                        scoring_registry=scoring_registry, policy_registry=policy_registry,
                        owner_scope=scope)
                    metric_verify(base)
                    policy_verify(policy)
                    if policy_ticket.selected() is not policy or metric_ticket.selected() is not base:
                        raise ValueError("valuation component tickets changed")
                    root_hash = base.registry_manifest_hash
                    bundle = load_root(FormalRegistryBundleLoader(feature._store, verifier), root_hash)
                    scoring_verify(scoring_registry, bundle)
                    adapter_verify(valuation_adapter_registry, bundle)
                    base_bytes, policy_bytes = base.canonical_bytes(), policy.canonical_bytes()
                    rows = prepare_adjusted_rows(base, policy, valuation_adapter_registry)
                    adapter_wire = valuation_adapter_registry.to_dict()
                    common = dict(schema_version="policy-adjusted-valuation-batch-v1",
                        registry_manifest_hash=root_hash,
                        frozen_input_hash=frozen_input_hash, universe_hash=base.universe_hash,
                        population_hash=base.population_hash, as_of_utc=base.as_of_utc,
                        industry_batch_hash=base.industry_batch_hash,
                        scoring_registry_hash=bundle.manifest.scoring_registry_hash,
                        policy_contract_hash=policy.policy_contract_hash,
                        valuation_adapter_registry_hash=bundle.manifest.valuation_adapter_registry_hash,
                        base_batch_hash=base.batch_hash,
                        base_batch_canonical_sha256=sha256(base_bytes).hexdigest(),
                        policy_batch_hash=policy.batch_hash,
                        policy_batch_canonical_sha256=sha256(policy_bytes).hexdigest(),
                        adapter_definition_sha256=hash_payload(adapter_wire),
                        security_ids=list(base.security_ids), metric_ids=list(_V_METRICS),
                        inputs=list(rows))
                    common["batch_hash"] = hash_payload(common)
                    children = tuple(mint(PolicyAdjustedValuationInput,
                        dict(row, batch_hash=common["batch_hash"]), publication,
                        attributes={"adjusted_value": None if row["adjusted_value"] is None
                                    else decimal_type(row["adjusted_value"])}) for row in rows)
                    index = {(row["security_id"], row["metric_id"]): item
                             for row, item in zip(rows, children, strict=True)}
                    prepared = mint(PolicyAdjustedValuationBatch, common, publication,
                        attributes={"inputs": children}, private={"index": index})

                    root_wire = tuple((role, bundle.blob(role).canonical_json) for role in bundle.roles)
                    root_ticket = _issue_current_ticket(scope, self, "valuation",
                        (frozen_input_hash, root_hash), bundle.manifest.canonical_json,
                        (root_hash, root_wire, scoring_registry, valuation_adapter_registry,
                         adapter_wire, verifier), (), bundle)
                    if root_ticket.selected() is not bundle:
                        raise ValueError("valuation root ticket changed")

                    def publish():
                        dependencies(self)
                        metric_verify(base)
                        policy_verify(policy)
                        if base.canonical_bytes() != base_bytes or policy.canonical_bytes() != policy_bytes:
                            raise ValueError("valuation source batches changed before publication")
                        validate_prepared(prepared, children, publication)
                        scope.finalize()
                        publication[0] = True
                        return prepared

                    result = guard.finalize(publish)
                return result
            except BaseException:
                publication[0] = False
                if scope is not None:
                    try:
                        scope.close()
                    except ValueError:
                        pass
                raise

        def _batch_journal_identity(self):
            feature, _, _, _, metric_repo, policy_repo = dependencies(self)
            return feature._store, (metric_repo, policy_repo)

        def _batch_recheck_ticket(self, evidence):
            root_hash, root_wire, scoring_registry, adapter_registry, adapter_wire, verifier = evidence
            feature, _, _, original_verifier, _, _ = dependencies(self)
            if verifier is not original_verifier:
                raise ValueError("valuation verifier changed")
            current = load_root(FormalRegistryBundleLoader(feature._store, verifier), root_hash)
            scoring_verify(scoring_registry, current)
            adapter_verify(adapter_registry, current)
            if (tuple((role, current.blob(role).canonical_json) for role in current.roles) != root_wire
                    or adapter_registry.to_dict() != adapter_wire):
                raise ValueError("valuation signed root or adapter changed")

        def __copy__(self):
            raise TypeError("valuation repositories cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("valuation repositories cannot be copied")

    own_members = tuple((cls, tuple(vars(cls).items())) for cls in
        (Proof, PolicyAdjustedValuationInput, PolicyAdjustedValuationBatch,
         FormalValuationRepository))
    return FormalValuationRepository, PolicyAdjustedValuationInput, PolicyAdjustedValuationBatch


(FormalValuationRepository, PolicyAdjustedValuationInput,
 PolicyAdjustedValuationBatch) = _install_valuation_engine()
del _install_valuation_engine

__all__ = ["FormalValuationRepository", "PolicyAdjustedValuationInput", "PolicyAdjustedValuationBatch"]
