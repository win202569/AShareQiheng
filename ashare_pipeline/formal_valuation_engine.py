"""Complete, atomically published policy-adjusted valuation inputs."""

import hashlib
import json
import time
import weakref
from decimal import Decimal, localcontext
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
    time_module, clock = time, time.perf_counter
    encode, decode, sha256, hash_payload, decimal_type = (
        json.dumps, json.loads, hashlib.sha256, digest, Decimal)
    guard_factory = _metric_batch_guard
    load_root = FormalRegistryBundleLoader.load
    adapter_source = adapter_module
    adapter_owner = adapter_source._require_valuation_adapter_owner
    evaluate = adapter_owner()
    arithmetic_context = adapter_source._arithmetic_context
    local_context = localcontext
    mapping_proxy = MappingProxyType
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
        if type(value) is tuple and all(type(item) is str for item in value):
            return value
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
                or globals().get("localcontext") is not local_context
                or globals().get("MappingProxyType") is not mapping_proxy
                or globals().get("time") is not time_module or time_module.perf_counter is not clock
                or adapter_source._arithmetic_context is not arithmetic_context
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
        elif cls is PolicyAdjustedValuationPeerContext:
            if saved[3]["batch"]() is None:
                raise ValueError("adjusted valuation peer context lost its complete batch")
        elif cls is PolicyAdjustedValuationScore:
            if saved[3]["batch"]() is None or saved[3]["context"]() is None:
                raise ValueError("adjusted valuation score lost its proof chain")
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

    class PolicyAdjustedValuationPeerContext(Proof):
        __slots__ = ()

    class PolicyAdjustedValuationScore(Proof):
        __slots__ = ()

    def mint(cls, payload, publication, *, attributes=None, private=None):
        proof = object.__new__(cls)
        data = dict(payload)
        data.update(attributes or {})
        wire = encode(payload, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False).encode()
        identity = id(proof)
        frozen = freeze(data)
        sealed_private = None if private is None else dict(private)
        if sealed_private is not None and "index" in sealed_private:
            sealed_private["index"] = MappingProxyType(dict(sealed_private["index"]))
        seal = (wire, payload["batch_hash"], payload.get("security_id"),
            payload.get("metric_id"), payload["registry_manifest_hash"],
            payload["frozen_input_hash"], payload.get("adjusted_value"),
            frozen.get("inputs"), None if sealed_private is None else sealed_private.get("index"))
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
            build_started = clock()
            feature, _, _, verifier, metric_repo, policy_repo = dependencies(self)
            if (type(frozen_input_hash) is not str or type(scoring_registry) is not FormalScoringRegistry
                    or type(policy_registry) is not FormalPolicyRegistry
                    or type(valuation_adapter_registry) is not FormalValuationAdapterRegistry):
                raise ValueError("valuation publication requires exact authenticated inputs")
            publication = [False]
            prepared = None
            scope = None
            validation_counts = {"registry_full_parses": 0,
                "base_batch_full_validations": 0, "policy_batch_full_validations": 0}
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
                    validation_counts["base_batch_full_validations"] += 1
                    policy_verify(policy)
                    validation_counts["policy_batch_full_validations"] += 1
                    if policy_ticket.selected() is not policy or metric_ticket.selected() is not base:
                        raise ValueError("valuation component tickets changed")
                    root_hash = base.registry_manifest_hash
                    bundle = load_root(FormalRegistryBundleLoader(feature._store, verifier), root_hash)
                    validation_counts["registry_full_parses"] += 1
                    scoring_verify(scoring_registry, bundle)
                    adapter_verify(valuation_adapter_registry, bundle)
                    validation_done = clock()
                    base_bytes, policy_bytes = base.canonical_bytes(), policy.canonical_bytes()
                    identity_done = clock()
                    rows = prepare_adjusted_rows(base, policy, valuation_adapter_registry)
                    rows_done = clock()
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
                        attributes={"inputs": children}, private={"index": index,
                            "repository": weakref.ref(self),
                            "groups": None, "contexts": {}, "ranks": {}, "scores": {},
                            "group_index_builds": 0, "sorts_by_cohort": {},
                            "validation_counts": dict(validation_counts),
                            "phase_seconds": {
                                "input_registry_validation": validation_done - build_started,
                                "identity_closure": identity_done - validation_done,
                                "row_adjustment": rows_done - identity_done,
                                "peer_grouping": 0.0, "peer_sorting": 0.0,
                                "final_verification": 0.0, "publication": 0.0}})

                    root_wire = tuple((role, bundle.blob(role).canonical_json) for role in bundle.roles)
                    root_ticket = _issue_current_ticket(scope, self, "valuation",
                        (frozen_input_hash, root_hash), bundle.manifest.canonical_json,
                        (root_hash, root_wire, scoring_registry, valuation_adapter_registry,
                         adapter_wire, verifier), (), bundle)
                    if root_ticket.selected() is not bundle:
                        raise ValueError("valuation root ticket changed")

                    def publish():
                        final_started = clock()
                        dependencies(self)
                        metric_verify(base)
                        policy_verify(policy)
                        if base.canonical_bytes() != base_bytes or policy.canonical_bytes() != policy_bytes:
                            raise ValueError("valuation source batches changed before publication")
                        validate_prepared(prepared, children, publication)
                        scope.finalize()
                        prepared_private = proofs[id(prepared)][3]
                        prepared_private["phase_seconds"]["final_verification"] += clock() - final_started
                        publication_started = clock()
                        publication[0] = True
                        prepared_private["phase_seconds"]["publication"] += clock() - publication_started
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

        def diagnostic_report(self, batch):
            dependencies(self)
            saved = record(batch, PolicyAdjustedValuationBatch)
            private = saved[3]
            if private["repository"]() is not self:
                raise ValueError("adjusted batch belongs to another valuation repository")
            canonical_rows = decode(saved[2])["inputs"]
            status_counts = {}
            pending_reason_counts = {}
            for row in canonical_rows:
                status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
                if row["adjusted_value"] is None:
                    pending_reason_counts[row["reason"]] = pending_reason_counts.get(row["reason"], 0) + 1
            contexts = tuple(record(value, PolicyAdjustedValuationPeerContext)[1]
                             for value in private["contexts"].values())
            scored_cohorts = {item["cohort_hash"] for item in contexts if item["reason"] is None}
            scope_counts = {scope: sum(item["scope"] == scope for item in contexts) for scope in
                ("template_secondary_industry", "template_primary_industry")}
            return MappingProxyType(dict(batch_hash=saved[1]["batch_hash"],
                security_count=len(saved[1]["security_ids"]),
                valuation_row_count=len(saved[1]["inputs"]),
                group_index_builds=private["group_index_builds"],
                sorts_by_cohort=MappingProxyType(dict(private["sorts_by_cohort"])),
                cohort_count=len(scored_cohorts), sort_count=sum(private["sorts_by_cohort"].values()),
                scope_counts=MappingProxyType(scope_counts),
                peer_count_below_20=sum(item["reason"] == "peer_count_below_20" for item in contexts),
                status_counts=MappingProxyType(status_counts),
                pending_reason_counts=MappingProxyType(pending_reason_counts),
                phase_seconds=MappingProxyType(dict(private["phase_seconds"])),
                full_financial_rederivations=0, **private["validation_counts"]))

        def __copy__(self):
            raise TypeError("valuation repositories cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("valuation repositories cannot be copied")

    def eligible(item):
        data = record(item, PolicyAdjustedValuationInput)[1]
        return (data["status"] in {"adjusted", "adjusted_no_numeric_change",
                    "passthrough_clear", "passthrough_not_applicable",
                    "passthrough_unaffected"}
                and data["adjusted_value"] is not None
                and data["original_metric"]["invalid_reason"] is None)

    def rank_values(values, direction):
        interfaces()
        if (type(values) is not tuple or not values
                or direction not in ("higher", "lower")
                or any(type(value) is not decimal_type or not value.is_finite()
                       for value in values)):
            raise ValueError("valuation ranks require finite exact Decimal peers and a signed direction")
        ordered = sorted(values)
        ranks = {}
        with local_context(arithmetic_context()):
            first = 0
            while first < len(ordered):
                last = first + 1
                while last < len(ordered) and ordered[last] == ordered[first]:
                    last += 1
                rank = (decimal_type(first + 1) + decimal_type(last)) / decimal_type(2)
                percentile = (decimal_type(100) * (rank - decimal_type("0.5"))
                              / decimal_type(len(ordered)))
                ranks[ordered[first]] = (rank, decimal_type(100) - percentile
                    if direction == "lower" else percentile)
                first = last
        return mapping_proxy(ranks)

    def peer_context(batch, *, metric_id, security_id):
        if type(security_id) is not str or type(metric_id) is not str:
            raise ValueError("valuation selectors require exact strings")
        batch_saved = record(batch, PolicyAdjustedValuationBatch)
        data, private = batch_saved[1], batch_saved[3]
        focal = private["index"].get((security_id, metric_id))
        if focal is None:
            raise ValueError("security or V metric is outside complete adjusted batch")
        key = (security_id, metric_id)
        if key in private["contexts"]:
            return private["contexts"][key]
        if private["groups"] is None:
            grouping_started = clock()
            groups = {}
            for proof in private["index"].values():
                item = record(proof, PolicyAdjustedValuationInput)[1]
                if not eligible(proof):
                    continue
                for scope_name, industry_id in (
                        ("template_secondary_industry", item["secondary_industry"]),
                        ("template_primary_industry", item["primary_industry"])):
                    group = (item["metric_id"], item["template_id"], scope_name, industry_id)
                    groups.setdefault(group, []).append(item["security_id"])
            private["groups"] = {group: tuple(sorted(ids)) for group, ids in groups.items()}
            private["group_index_builds"] += 1
            private["phase_seconds"]["peer_grouping"] += clock() - grouping_started
        focal_data = record(focal, PolicyAdjustedValuationInput)[1]
        original = focal_data["original_metric"]
        reason, scope_name, industry_id, peers = focal_data["reason"], None, None, ()
        if eligible(focal):
            reason = None
            for candidate, industry_id in (
                    ("template_secondary_industry", focal_data["secondary_industry"]),
                    ("template_primary_industry", focal_data["primary_industry"])):
                peers = private["groups"].get(
                    (metric_id, focal_data["template_id"], candidate, industry_id), ())
                if len(peers) >= 20:
                    scope_name = candidate
                    break
            if scope_name is None:
                reason = "peer_count_below_20"
        payload = dict(schema_version="policy-adjusted-valuation-peer-context-v1",
            batch_hash=data["batch_hash"], registry_manifest_hash=data["registry_manifest_hash"],
            frozen_input_hash=data["frozen_input_hash"], universe_hash=data["universe_hash"],
            valuation_adapter_registry_hash=data["valuation_adapter_registry_hash"],
            metric_id=metric_id, security_id=security_id,
            template_id=focal_data["template_id"], industry_id=industry_id,
            primary_industry=focal_data["primary_industry"],
            secondary_industry=focal_data["secondary_industry"],
            definition_hash=original["definition_hash"], direction=original["direction"],
            scope=scope_name, peer_security_ids=peers, peer_count=len(peers), reason=reason)
        payload["cohort_hash"] = hash_payload(dict(batch_hash=data["batch_hash"],
            metric_id=metric_id, definition_hash=payload["definition_hash"],
            valuation_adapter_registry_hash=data["valuation_adapter_registry_hash"],
            direction=payload["direction"], template_id=payload["template_id"],
            scope=scope_name, industry_id=industry_id, peer_security_ids=peers))
        payload["context_hash"] = hash_payload(payload)
        result = mint(PolicyAdjustedValuationPeerContext, payload, batch_saved[4],
            attributes={"peer_security_ids": peers}, private={"batch": weakref.ref(batch)})
        private["contexts"][key] = result
        return result

    def score(batch, context):
        batch_saved = record(batch, PolicyAdjustedValuationBatch)
        context_saved = record(context, PolicyAdjustedValuationPeerContext)
        if context_saved[3]["batch"]() is not batch:
            raise ValueError("valuation peer context belongs to another complete adjusted batch")
        c, private = context_saved[1], batch_saved[3]
        if c["reason"] is not None:
            return None
        if c["peer_count"] < 20:
            raise ValueError("formal valuation percentile requires at least twenty peers")
        score_key = (c["security_id"], c["metric_id"])
        if score_key in private["scores"]:
            return private["scores"][score_key]
        cohort = c["cohort_hash"]
        if cohort not in private["ranks"]:
            sorting_started = clock()
            values = tuple(decimal_type(record(private["index"][(sid, c["metric_id"])] ,
                PolicyAdjustedValuationInput)[1]["adjusted_value"])
                for sid in c["peer_security_ids"])
            private["ranks"][cohort] = rank_values(values, c["direction"])
            private["sorts_by_cohort"][cohort] = 1
            private["phase_seconds"]["peer_sorting"] += clock() - sorting_started
        focal = private["index"][(c["security_id"], c["metric_id"])]
        focal_saved = record(focal, PolicyAdjustedValuationInput)
        value_text = focal_saved[1]["adjusted_value"]
        value = decimal_type(value_text)
        rank, percentile = private["ranks"][cohort][value]
        payload = dict(schema_version="policy-adjusted-valuation-score-v1",
            batch_hash=batch_saved[1]["batch_hash"],
            registry_manifest_hash=batch_saved[1]["registry_manifest_hash"],
            frozen_input_hash=batch_saved[1]["frozen_input_hash"],
            universe_hash=batch_saved[1]["universe_hash"], metric_id=c["metric_id"],
            security_id=c["security_id"], definition_hash=c["definition_hash"],
            valuation_adapter_registry_hash=batch_saved[1]["valuation_adapter_registry_hash"],
            adjusted_input_hash=focal_saved[1]["input_hash"], adjusted_value=value_text,
            average_rank=str(rank), percentile=str(percentile), peer_count=c["peer_count"],
            peer_context=context.to_dict())
        payload["score_hash"] = hash_payload(payload)
        result = mint(PolicyAdjustedValuationScore, payload, batch_saved[4],
            attributes={"adjusted_value": value, "average_rank": rank,
                "percentile": percentile, "peer_context": context},
            private={"batch": weakref.ref(batch), "context": weakref.ref(context)})
        private["scores"][score_key] = result
        return result

    own_members = tuple((cls, tuple(vars(cls).items())) for cls in
        (Proof, PolicyAdjustedValuationInput, PolicyAdjustedValuationBatch,
         PolicyAdjustedValuationPeerContext, PolicyAdjustedValuationScore,
         FormalValuationRepository))
    return (FormalValuationRepository, PolicyAdjustedValuationInput,
        PolicyAdjustedValuationBatch, PolicyAdjustedValuationPeerContext,
        PolicyAdjustedValuationScore, eligible, peer_context, score, rank_values)


(FormalValuationRepository, PolicyAdjustedValuationInput,
 PolicyAdjustedValuationBatch, PolicyAdjustedValuationPeerContext,
 PolicyAdjustedValuationScore, valuation_peer_eligible,
 build_valuation_peer_context, score_valuation_percentile,
 _rank_valuation_values) = _install_valuation_engine()
del _install_valuation_engine

__all__ = ["FormalValuationRepository", "PolicyAdjustedValuationInput",
    "PolicyAdjustedValuationBatch", "PolicyAdjustedValuationPeerContext",
    "PolicyAdjustedValuationScore", "valuation_peer_eligible",
    "build_valuation_peer_context", "score_valuation_percentile"]
