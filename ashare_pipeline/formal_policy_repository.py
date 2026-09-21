"""Sole complete-universe policy publication authority.

Detached evaluator dictionaries are data. Eligibility resides only in this
module's closure-owned records and the shared, revocable publication state.
"""

import json
from types import MappingProxyType
import weakref

from . import formal_policy_evaluator as evaluator_module
from . import formal_range_store as range_module
from . import formal_policy_registry as registry_module
from .formal_context_repository import FormalContextRepository
from .formal_feature_repository import FormalFeatureRepository
from .formal_metric_batch_guard import FormalMetricCurrentInputProvider, _metric_batch_guard
from .formal_metric_context import FormalMetricContextRepository, _require_authentic_metric_context_repository
from .formal_policy_financial import FormalPolicyFinancialRepository, PolicyFinancialSelection, _feature_dependencies
from .formal_policy_state import FormalPolicyStateRepository, PolicyStateSelection
from .formal_policy_market import (
    FormalPolicyMarketRepository, MarketSelection, CalendarSelection,
    VerifiedMarketWindowV1, VerifiedCalendarCoverageV1,
)
from .formal_policy_values import PolicyValue, canonical_bytes, digest, _policy_value_operations
from .formal_range_contract import load_policy_range_bindings
from .formal_registry_manifest import FormalRegistryBundleLoader
from .formal_scoring_registry import FormalScoringRegistry


def _install_repository():
    repositories, proofs = {}, {}
    owner = globals()
    encode, hash_payload = canonical_bytes, digest
    parse_value, serialize_value, check_values = _policy_value_operations()
    read_policy = registry_module._read_authenticated_policy_registry
    range_identity = range_module._require_range_store_identity
    feature_check = _feature_dependencies
    context_check = _require_authentic_metric_context_repository
    guard_factory = _metric_batch_guard
    load_root = FormalRegistryBundleLoader.load
    load_bindings = load_policy_range_bindings
    evaluate, aggregate = evaluator_module.evaluate_rule, evaluator_module.aggregate_decisions
    roles = ("source", "mapping", "feature", "scoring", "industry", "cyclic", "redline", "status", "event")
    captured = tuple((owner, name, value) for name, value in owner.items()
                     if callable(value) and name != "_install_repository")
    captured += tuple((vars(evaluator_module), name, value)
                      for name, value in vars(evaluator_module).items()
                      if callable(value) or name.startswith("_DECISION"))
    captured += ((vars(range_module), "_require_range_store_identity", range_identity),
                 (vars(registry_module), "_read_authenticated_policy_registry", read_policy),
                 (vars(range_module), "FormalRangeStore", range_module.FormalRangeStore),
                 (owner, "range_module", range_module), (owner, "registry_module", registry_module),
                 (owner, "evaluator_module", evaluator_module))
    dependencies_classes = (FormalFeatureRepository, FormalContextRepository,
        FormalMetricCurrentInputProvider, FormalMetricContextRepository,
        FormalPolicyFinancialRepository, PolicyFinancialSelection,
        FormalPolicyStateRepository, PolicyStateSelection, FormalPolicyMarketRepository,
        MarketSelection, CalendarSelection, VerifiedMarketWindowV1, VerifiedCalendarCoverageV1,
        range_module.FormalRangeStore, FormalRegistryBundleLoader, FormalScoringRegistry)
    checked = tuple((cls, name, value) for cls in dependencies_classes
                    for name, value in vars(cls).items()
                    if callable(value) or isinstance(value, (staticmethod, classmethod)))

    def interfaces():
        check_values()
        if any(namespace.get(name) is not original for namespace, name, original in captured):
            raise ValueError("policy publication dependency changed")
        if any(vars(cls).get(name) is not original for cls, name, original in checked):
            raise ValueError("policy publication reader interface changed")
        if any(owner.get(name) is not original for name, original in entries):
            raise ValueError("policy publication entry point changed")

    def state(feature, context, ranges, verifier, companion):
        interfaces()
        if (type(feature) is not FormalFeatureRepository or type(context) is not FormalContextRepository
                or feature._store is not context._state_store or feature._verifier is not verifier
                or context._verifier is not verifier):
            raise ValueError("policy repository requires exact same-Store repositories and verifier")
        feature_check(feature, feature._current_input_provider)
        context_check(companion)
        range_identity(ranges, feature._store, verifier)
        for cls, name, _ in checked:
            for instance in (feature, context, ranges):
                if type(instance) is cls and name in vars(instance):
                    raise ValueError("policy repository dependency has an instance override")
        return (id(feature), id(context), id(ranges), id(verifier), id(feature._store),
                id(feature._bundle_store), id(feature._current_input_provider), id(context._snapshots))

    def dependencies(repository):
        interfaces()
        saved = repositories.get(id(repository))
        if type(repository) is not FormalPolicyRepository or saved is None or saved[0]() is not repository:
            raise ValueError("policy repository is forged or copied")
        feature, context, ranges, verifier, companion, original = saved[1:7]
        if state(feature, context, ranges, verifier, companion) != original:
            raise ValueError("policy repository graph changed")
        return saved

    def freeze(value):
        if type(value) is dict:
            return MappingProxyType({key: freeze(item) for key, item in value.items()})
        if type(value) in (list, tuple):
            return tuple(freeze(item) for item in value)
        return value

    def plain(value):
        if type(value) is PolicyValue:
            return serialize_value(value)
        if isinstance(value, (dict, MappingProxyType)):
            return {key: plain(item) for key, item in value.items()}
        if type(value) in (list, tuple):
            return [plain(item) for item in value]
        return value

    def record(proof):
        interfaces()
        saved = proofs.get(id(proof))
        if (type(proof) not in proof_types or saved is None or saved[0]() is not proof
                or not saved[3]["published"] or saved[4] is not saved[3]["parent_link"]
                or saved[5] != saved[3]["batch_hash"]):
            raise ValueError("policy proof is forged, copied, unpublished or revoked")
        return saved

    class SealedMeta(type):
        def __setattr__(cls, name, value):
            raise TypeError("policy authority types are immutable")

        def __delattr__(cls, name):
            raise TypeError("policy authority types are immutable")

    class Proof(metaclass=SealedMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("policy proofs require a complete authenticated publication")

        def __getattribute__(self, name):
            record(self)
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            saved = record(self)
            if name not in saved[1]:
                raise AttributeError(name)
            return saved[1][name]

        def require_verified(self):
            record(self)

        require_official = require_verified

        def to_dict(self):
            return json.loads(record(self)[2])

        def canonical_bytes(self):
            return record(self)[2]

        def __copy__(self):
            raise TypeError("policy proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("policy proofs cannot be copied")

    class VerifiedPolicyEvidenceBatch(Proof):
        __slots__ = ()

    class PolicyDecision(Proof):
        __slots__ = ()

    class PolicyResult(Proof):
        __slots__ = ()

    class VerifiedPolicyResultBatch(Proof):
        __slots__ = ()

    proof_types = (VerifiedPolicyEvidenceBatch, PolicyDecision, PolicyResult, VerifiedPolicyResultBatch)

    def mint(cls, payload, publication, attributes=None):
        proof = object.__new__(cls)
        key = id(proof)
        wire = dict(payload, batch_hash=publication["batch_hash"])
        data = dict(wire)
        data.update(attributes or {})
        proofs[key] = (weakref.ref(proof, lambda _: proofs.pop(key, None)), freeze(data), encode(wire),
                       publication, publication["parent_link"], publication["batch_hash"])
        return proof

    class FormalPolicyRepository(metaclass=SealedMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, feature_repository, context_repository, range_store, *, registry_signature_verifier):
            if type(self) is not FormalPolicyRepository or id(self) in repositories:
                raise ValueError("policy repository initialization must be exact and single-use")
            if type(feature_repository) is not FormalFeatureRepository:
                raise ValueError("policy repository needs a genuine feature repository")
            companion = FormalMetricContextRepository(feature_repository._store, context_repository,
                registry_signature_verifier=registry_signature_verifier)
            original = state(feature_repository, context_repository, range_store,
                             registry_signature_verifier, companion)
            financial = FormalPolicyFinancialRepository(feature_repository,
                current_input_provider=feature_repository._current_input_provider)
            states = FormalPolicyStateRepository(context_repository)
            market = FormalPolicyMarketRepository(range_store)
            key = id(self)
            repositories[key] = (weakref.ref(self, lambda _: repositories.pop(key, None)),
                feature_repository, context_repository, range_store, registry_signature_verifier,
                companion, original, financial, states, market)

        def __copy__(self):
            raise TypeError("policy repositories cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("policy repositories cannot be copied")

        def build_batch(self, frozen_input_hash, *, scoring_registry, policy_registry):
            saved = dependencies(self)
            feature, _, ranges, verifier, context = saved[1:6]
            financial, states, market = saved[7:]
            if type(frozen_input_hash) is not str or type(scoring_registry) is not FormalScoringRegistry:
                raise ValueError("policy publication requires exact frozen and registry identities")
            prepared = None
            selections = []
            market_markers = []
            publication = dict(published=False, parent_link=object(), batch_hash=None)

            def registry_snapshot(root_hash):
                dependencies(self)
                bundle = load_root(FormalRegistryBundleLoader(feature._store, verifier), root_hash)
                scoring_registry.require_official(bundle)
                policy = read_policy(policy_registry)
                role_bytes = {role: bundle.blob(role).canonical_json for role in roles}
                if (policy["registry_manifest_hash"] != root_hash
                        or any(policy["role_hashes"][role] != hash_payload(json.loads(raw))
                               for role, raw in role_bytes.items())):
                    raise ValueError("policy and scoring signature roots differ")
                return bundle, policy, role_bytes

            def prepare():
                nonlocal universe, industry, policy_wire, source_bytes, root_hash
                universe = context.load_universe(frozen_input_hash, scoring_registry=scoring_registry)
                if universe is None:
                    raise ValueError("policy frozen universe is absent")
                root_hash = universe.registry_manifest_hash
                bundle, policy_wire, source_bytes = registry_snapshot(root_hash)
                bindings = load_bindings(bundle, scoring_registry=scoring_registry, policy_registry=policy_registry)
                industry = context.resolve_industries(universe)
                common = dict(registry_manifest_hash=root_hash, frozen_input_hash=frozen_input_hash,
                    universe_hash=universe.universe_hash, as_of_utc=universe.as_of_utc,
                    policy_contract_hash=policy_wire["contract_hash"], role_hashes=policy_wire["role_hashes"])
                evidence = dict(common, schema_version="formal-policy-evidence-batch-v1",
                    universe=universe.to_dict(), industry=industry.to_dict(),
                    source_specification=json.loads(source_bytes["source"]), selections={}, rule_inputs={})
                result_wires = []
                for sid in universe.security_ids:
                    entry = industry.entries[sid]
                    decisions, evidence_selections, inputs = [], {}, {}
                    if entry["status"] == "assigned":
                        template = entry["template_id"]
                        args = dict(template_id=template, policy_registry=policy_registry)
                        fin = financial.select(sid, universe.as_of_utc, industry_batch=industry, **args)
                        state_selection = states.select(sid, universe.as_of_utc, **args)
                        selections.extend((fin, state_selection))
                        values = dict(fin.values)
                        values.update(dict(state_selection.values))
                        annual = {key: tuple(dict(item) for item in series) for key, series in fin.annual.items()}
                        evidence_selections.update(financial=dict(values=plain(fin.values), annual=plain(fin.annual),
                            lineage=plain(fin.lineage), selection_hash=fin.selection_hash),
                            state=dict(values=plain(state_selection.values), lineage=plain(state_selection.lineage),
                                       selection_hash=state_selection.selection_hash))
                        for rule in policy_wire["rules"]:
                            if rule["template_id"] != template:
                                continue
                            applicability = "applicable"
                            if rule["kind"] == "cyclic_protection" and entry["secondary_industry"] not in policy_wire["cyclic_secondary_industries"]:
                                applicability = "not_applicable"
                            market_wire = None
                            if rule["kind"] == "market_liquidity":
                                binding = bindings.for_rule(rule["rule_id"], sid[:2])
                                selected = market.select(sid, universe.as_of_utc, binding=binding)
                                if type(selected) is not MarketSelection:
                                    raise ValueError("market repository returned an unknown selection")
                                market_markers.append((selected, selected.window, selected.pending,
                                    selected.lineage, selected.selection_hash, selected._check))
                                selections.append(selected)
                                market_wire = None if selected.window is None else selected.window.to_dict()
                                evidence_selections[rule["rule_id"]] = dict(window=market_wire,
                                    pending=list(selected.pending), lineage=list(selected.lineage), selection_hash=selected.selection_hash)
                                if market_wire is not None and any(market_wire[key] != expected for key, expected in
                                    (("security_id", sid), ("as_of_utc", universe.as_of_utc), ("registry_manifest_hash", root_hash),
                                     ("rule_id", rule["rule_id"]), ("exchange", sid[:2]))):
                                    raise ValueError("market selection identity differs from policy request")
                            inputs[rule["rule_id"]] = dict(rule=rule, applicability=applicability,
                                values=plain(values), annual=plain(annual), market=market_wire)
                            decisions.append(evaluate(rule, security_id=sid, applicability=applicability,
                                values=values, annual=annual, market=market_wire))
                    result = dict(common, security_id=sid, **aggregate(tuple(decisions)))
                    if entry["status"] != "assigned":
                        result["pending_requirements"].append(dict(origin="runtime", code="applicability_unresolved",
                            security_id=sid, reason=entry["pending_reason"], evidence_hashes=[industry.batch_hash]))
                        result["evidence_state"] = "pending_evidence"
                    for decision in result["decisions"]:
                        decision["decision_hash"] = hash_payload(decision)
                    result["result_hash"] = hash_payload(result)
                    result_wires.append(result)
                    evidence["selections"][sid] = evidence_selections
                    evidence["rule_inputs"][sid] = inputs
                evidence["evidence_hash"] = hash_payload(evidence)
                payload = dict(common, schema_version="formal-policy-result-batch-v1",
                    security_ids=list(universe.security_ids), evidence_batch=evidence, results=result_wires)
                publication["batch_hash"] = hash_payload(payload)
                evidence_proof = mint(VerifiedPolicyEvidenceBatch, evidence, publication)
                results = []
                for wire in result_wires:
                    children = tuple(mint(PolicyDecision, decision, publication) for decision in wire["decisions"])
                    results.append(mint(PolicyResult, wire, publication, dict(decisions=children)))
                return mint(VerifiedPolicyResultBatch, payload, publication,
                            dict(results=tuple(results), evidence_batch=evidence_proof))

            def read_and_recheck(batch):
                dependencies(self)
                _, current_policy, current_bytes = registry_snapshot(root_hash)
                if current_policy != policy_wire or current_bytes != source_bytes:
                    raise ValueError("policy signed source configuration changed")
                context.recheck_batch(universe, industry)
                for selected, window, pending, lineage, selection_hash, check in market_markers:
                    if (selected.window is not window or selected._check is not check
                            or selected.pending != pending or selected.lineage != lineage
                            or selected.selection_hash != selection_hash):
                        raise ValueError("market selection identity changed")
                for selection in selections:
                    selection.recheck()
                dependencies(self)

            def mark_published(batch):
                publication["published"] = True

            def revoke(batch):
                publication["published"] = False

            universe = industry = policy_wire = source_bytes = root_hash = None
            try:
                with guard_factory(feature._current_input_provider, feature._store) as guard:
                    prepared = prepare()
                    read_and_recheck(prepared)
                    def finalize():
                        read_and_recheck(prepared)
                        mark_published(prepared)
                        return prepared
                    result = guard.finalize(finalize)
                return result
            except BaseException:
                # Also revoke children if prepare failed after its first mint.
                revoke(prepared)
                raise

    entries = tuple((cls.__name__, cls) for cls in (FormalPolicyRepository, *proof_types))
    return FormalPolicyRepository, *proof_types


(FormalPolicyRepository, VerifiedPolicyEvidenceBatch, PolicyDecision, PolicyResult,
 VerifiedPolicyResultBatch) = _install_repository()
del _install_repository

__all__ = ["FormalPolicyRepository", "VerifiedPolicyEvidenceBatch", "PolicyDecision",
           "PolicyResult", "VerifiedPolicyResultBatch"]
