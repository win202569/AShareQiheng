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
from .formal_valuation_adapter import evaluate_valuation_adjustment
from .formal_batch_read_journal import FormalBatchReadJournal, _issue_current_ticket


_V_METRICS = ("V.enterprise_value_or_sustainable_roe", "V.normalized_earnings_yield",
              "V.normalized_free_cash_flow_yield")
_FREEZE = "2026-08-31T07:00:00+00:00"


def _install_valuation_engine():
    repositories, proofs = {}, {}
    own_members = ()
    json_module, hashlib_module = json, hashlib
    encode, decode, sha256 = json.dumps, json.loads, hashlib.sha256
    guard_factory = _metric_batch_guard
    load_root = FormalRegistryBundleLoader.load
    evaluate = evaluate_valuation_adjustment
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
                or globals().get("evaluate_valuation_adjustment") is not evaluate
                or globals().get("digest") is not digest
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

    def record(proof, cls):
        interfaces()
        saved = proofs.get(id(proof))
        if (type(proof) is not cls or saved is None or saved[0]() is not proof
                or not saved[4][0]):
            raise ValueError("adjusted valuation proof is forged, copied, unpublished or revoked")
        return saved

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
            return json.loads(record(self, type(self))[2])

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
            result = record(self, PolicyAdjustedValuationBatch)[3]["index"].get((security_id, metric_id))
            if result is None:
                raise ValueError("security or V metric is outside complete adjusted batch")
            return result

    def mint(cls, payload, publication, *, attributes=None, private=None):
        proof = object.__new__(cls)
        data = dict(payload)
        data.update(attributes or {})
        wire = json.dumps(payload, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False).encode()
        identity = id(proof)
        proofs[identity] = (weakref.ref(proof, lambda _: proofs.pop(identity, None)),
            freeze(data), wire, private, publication)
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
            row["input_hash"] = digest(row)
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
                    policy, policy_ticket, policy_revoke = policy_build(policy_repo, frozen_input_hash,
                        scoring_registry=scoring_registry, policy_registry=policy_registry,
                        owner_scope=scope)
                    base, metric_ticket, metric_revoke = metric_build(metric_repo, frozen_input_hash,
                        scoring_registry=scoring_registry, metric_ids=_V_METRICS,
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
                        base_batch_canonical_sha256=hashlib.sha256(base_bytes).hexdigest(),
                        policy_batch_hash=policy.batch_hash,
                        policy_batch_canonical_sha256=hashlib.sha256(policy_bytes).hexdigest(),
                        adapter_definition_sha256=digest(adapter_wire),
                        security_ids=list(base.security_ids), metric_ids=list(_V_METRICS),
                        inputs=list(rows))
                    common["batch_hash"] = digest(common)
                    children = tuple(mint(PolicyAdjustedValuationInput,
                        dict(row, batch_hash=common["batch_hash"]), publication,
                        attributes={"adjusted_value": None if row["adjusted_value"] is None
                                    else Decimal(row["adjusted_value"])}) for row in rows)
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
