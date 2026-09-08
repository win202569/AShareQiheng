"""Repository-owned complete-company inputs; no scorecard or policy arithmetic.

Metric eligibility and complete-company readiness are separate. The inner metric
batch is a historical proof in its own right; every outer proof shares a separate
revocable publication capability until the enclosing current-state guard exits.
"""

from decimal import Decimal
import hashlib
import json
import weakref

from . import formal_metric_engine as metric_module
from . import formal_metric_context as metric_context_module
from . import formal_feature_repository as feature_module
from . import formal_financial_features as financial_module
from . import formal_metric_batch_guard as guard_module
from .formal_context_repository import FormalContextRepository
from .formal_context_schema import FormalContextFact
from .formal_feature_contract import (FormalEvidenceRef, FormalFeatureBundle, FormalFeatureSlot,
    FormalFeatureValue, SignedFormalFeatureRegistry)
from .formal_feature_repository import (FormalFeatureRepository, VerifiedMetricFeatureAbsence,
    VerifiedMetricFeatureProjection)
from .formal_metric_context import (FormalMetricContextRepository, VerifiedMetricUniverse, VerifiedMetricIndustryBatch)
from .formal_metric_engine import (FormalMetricInputRepository, MetricInput, MetricInputBatch,
    MetricPeerContext, MetricScore)
from .formal_scoring_registry import FormalScoringRegistry


_FREEZE = "2026-08-31T07:00:00+00:00"
_EMPTY_ISSUES = hashlib.sha256(b"[]").hexdigest()


def _consensus_branch(link, actual):
    """Classify already-authenticated Context; never grants provenance itself."""
    if link is None:
        return False, ()
    if actual is None:
        return False, ("consensus_context_absent",)
    value = actual["value"]
    if actual["no_coverage"] is True and value["coverage_status"] == "no_valid_coverage" and not value["estimates"]:
        return True, ()
    if actual["no_coverage"] is False and value["coverage_status"] == "covered" and value["estimates"]:
        return False, ()
    raise ValueError("complete score consensus coverage response is malformed")


def _temporal_quality(refs):
    if not refs or any(ref["published_precision"] not in ("timestamp", "date_only") for ref in refs):
        raise ValueError("complete score temporal quality requires actual precision evidence")
    return min(Decimal("1") if ref["published_precision"] == "timestamp" else Decimal("0.8") for ref in refs)


def _full_company_gate(bundle, signed_slots, marker, *, cyclic, exempt_key):
    """Pure readiness diagnostics. This helper never creates an authenticated proof."""
    history = financial_module.require_formal_history(bundle.history_endpoints,
        comparable_quarter_keys=bundle.comparable_quarter_keys[-8:], as_of_utc=_FREEZE, cyclic=cyclic)
    reasons = set(history.blockers)
    if exempt_key is None:
        reasons.update(bundle.blockers)
    elif marker["issue_snapshot_hash"] != _EMPTY_ISSUES:
        reasons.add("nonempty_current_issues")
    values = {value.slot_id: value for value in bundle.values}
    if tuple(values) != tuple(slot.slot_id for slot in signed_slots):
        raise ValueError("complete score full signed slot identities differ")
    nonexempt_derived = False
    for slot in signed_slots:
        value = values[slot.slot_id]
        if value.unit != slot.unit or value.formula_version != slot.formula_version:
            raise ValueError("complete score signed slot unit or formula differs")
        if value.status not in ("derived", "missing"):
            reasons.add("full_slot_blocked:" + slot.slot_id)
        elif slot.required and slot.slot_id != exempt_key:
            if value.status != "derived":
                reasons.add("full_required_slot_missing:" + slot.slot_id)
            else:
                nonexempt_derived = True
    if exempt_key is not None and not nonexempt_derived:
        reasons.add("neutral_requires_nonexempt_derived_slot")
    count = 0
    for year in range(2025, 2020, -1):
        if f"{year}-12-31" not in bundle.history_endpoints:
            break
        count += 1
    return tuple(sorted(reasons)), count


def _install_score_inputs():
    repositories, proofs = {}, {}
    require_feature = feature_module._require_authentic_metric_feature_repository
    require_context = metric_context_module._require_authentic_metric_context_repository
    batch_guard = guard_module._metric_batch_guard
    metric_build = FormalMetricInputRepository.build_batch
    peer_context = metric_module.build_metric_peer_context
    percentile = metric_module.score_metric_percentile
    full_read = FormalFeatureRepository._read_authenticated_bundle
    registry_read = FormalFeatureRepository._registry
    consensus_read = FormalContextRepository.get_verified_many
    encode, digest, freeze = metric_module._canonical, metric_module._digest, metric_module._freeze
    full_gate = _full_company_gate
    consensus_branch, temporal_quality = _consensus_branch, _temporal_quality
    checked_functions = tuple((module, name, getattr(module, name)) for module, names in (
        (metric_module, ("build_metric_peer_context", "score_metric_percentile", "_plain", "_canonical",
            "_digest", "_freeze", "_arithmetic_context", "FormalMetricInputRepository")),
        (feature_module, ("_require_authentic_metric_feature_repository",)),
        (metric_context_module, ("_require_authentic_metric_context_repository", "FormalMetricContextRepository")),
        (financial_module, ("require_formal_history",)),
        (guard_module, ("_metric_batch_guard",))) for name in names)
    classes = {base for cls in (FormalMetricInputRepository, MetricInput, MetricInputBatch, MetricPeerContext,
        MetricScore, FormalMetricContextRepository, VerifiedMetricUniverse, VerifiedMetricIndustryBatch,
        VerifiedMetricFeatureAbsence, VerifiedMetricFeatureProjection, FormalFeatureRepository, FormalContextRepository,
        FormalContextFact, FormalFeatureBundle, FormalEvidenceRef, FormalFeatureValue, FormalFeatureSlot,
        SignedFormalFeatureRegistry, FormalScoringRegistry) for base in cls.__mro__ if base is not object}

    def resolved_method(cls, name):
        return next((vars(base)[name] for base in cls.__mro__ if name in vars(base)), None)

    def capture_methods(types):
        return tuple((cls, name, resolved_method(cls, name)) for cls in types
            for name in sorted({name for base in cls.__mro__ if base is not object
                for name, value in vars(base).items()
                if callable(value) or isinstance(value, (staticmethod, classmethod))}))

    checked_methods = capture_methods(classes)

    def methods_unchanged(checks):
        if any(resolved_method(cls, name) is not value for cls, name, value in checks):
            raise ValueError("complete score proof or read dependency changed")

    def dependencies(repository):
        record = repositories.get(id(repository))
        if type(repository) is not FormalScoreInputRepository or record is None or record[0]() is not repository:
            raise ValueError("complete score repository is uninitialized or copied")
        feature, context, verifier, metrics, contexts = record[1:]
        methods_unchanged(checked_methods)
        methods_unchanged(own_methods)
        if (_full_company_gate is not full_gate or _consensus_branch is not consensus_branch
                or _temporal_quality is not temporal_quality or any(getattr(module, name) is not value
                for module, name, value in checked_functions)):
            raise ValueError("complete score calculation dependency changed")
        require_feature(feature)
        store, actual_context, actual_verifier = require_context(contexts)
        if (actual_context is not context or actual_verifier is not verifier or feature._store is not store
                or feature._verifier is not verifier or context._verifier is not verifier):
            raise ValueError("complete score repository trust dependencies changed")
        return feature, context, verifier, metrics, contexts

    def proof_record(proof, cls):
        record = proofs.get(id(proof))
        if (type(proof) is not cls or record is None or record[0]() is not proof or not record[4][0]):
            raise ValueError("complete score proof is forged, copied, unpublished or revoked")
        methods_unchanged(own_methods)
        return record

    class Proof:
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("complete score proofs require an authenticated repository batch")

        def __getattr__(self, name):
            data = proof_record(self, type(self))[1]
            if name not in data:
                raise AttributeError(name)
            return data[name]

        def require_verified(self):
            proof_record(self, type(self))

        def canonical_bytes(self):
            return proof_record(self, type(self))[2]

        def to_dict(self):
            return json.loads(proof_record(self, type(self))[2])

        def __copy__(self):
            raise TypeError("complete score proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("complete score proofs cannot be copied")

    class FormalScoreInput(Proof):
        __slots__ = ()

    class FormalScoreInputBatch(Proof):
        __slots__ = ()

        def input_for(self, security_id):
            record = proof_record(self, FormalScoreInputBatch)
            if type(security_id) is not str or security_id not in record[3]:
                raise ValueError("complete score selector is outside the canonical universe")
            return record[3][security_id]

    def mint(cls, payload, publication, *, attributes=None, index=None):
        result = object.__new__(cls)
        identity = id(result)
        data = dict(payload)
        data.update(attributes or {})
        proofs[identity] = (weakref.ref(result, lambda _: proofs.pop(identity, None)),
            freeze(data), encode(payload), index, publication)
        return result

    def read_full(repository, batch, sid):
        feature, _, _, _, _ = dependencies(repository)
        marker = batch.feature_states[sid]
        result = full_read(feature, input_hash=marker["input_hash"], require_complete=False)
        dependencies(repository)
        if type(result) is not FormalFeatureBundle or result.bundle_hash() != marker["bundle_hash"]:
            raise ValueError("complete score current full bundle disappeared or changed")
        for field in ("input_hash", "registry_manifest_hash", "feature_registry_hash", "security_id", "template_id", "as_of_utc"):
            if getattr(result, field) != marker[field]:
                raise ValueError("complete score current full bundle identity mismatch")
        if result.as_of_utc != _FREEZE:
            raise ValueError("complete score full bundle cutoff mismatch")
        return result

    def read_consensus(repository, batch, groups, links):
        _, context, _, _, _ = dependencies(repository)
        result = {}
        for scope, ids in sorted(groups.items()):
            dependencies(repository)
            facts = consensus_read(context, "consensus_snapshot", scope, tuple(sorted(ids)),
                _FREEZE, batch.registry_manifest_hash)
            dependencies(repository)
            for sid in ids:
                fact = facts[sid]
                if fact is None:
                    result[sid] = None
                    continue
                if type(fact) is not FormalContextFact:
                    raise ValueError("complete score consensus requires actual authenticated Context")
                wire = json.loads(fact.canonical_bytes())
                if (wire["security_id"] != sid or wire["as_of_utc"] != _FREEZE
                        or wire["registry_manifest_hash"] != batch.registry_manifest_hash
                        or wire["scope_key"] != scope or wire["context_kind"] != "consensus_snapshot"
                        or wire["evidence"]["descriptor_id"] != links[sid]["descriptor_id"]):
                    raise ValueError("complete score linked consensus identity mismatch")
                result[sid] = wire
        return result

    def build(repository, frozen_input_hash, scoring, guard, publication):
        feature, _, _, metrics, _ = dependencies(repository)
        batch = metric_build(metrics, frozen_input_hash, scoring_registry=scoring, metric_ids=None)
        dependencies(repository)
        if batch is None:
            return guard.finalize(lambda: dependencies(repository) and None)
        if type(batch) is not MetricInputBatch:
            raise ValueError("complete score requires the owned genuine metric batch")
        batch.require_verified()
        graph, vocabulary = registry_read(feature, batch.registry_manifest_hash)
        scoring.require_official(graph)
        full, links, groups = {}, {}, {}
        for sid in batch.security_ids:
            marker = batch.feature_states.get(sid)
            if marker is not None and marker.get("status") != "current_receipt_absent":
                full[sid] = read_full(repository, batch, sid)
            # Link follows genuine signed template classification, including
            # pending members: selected Context absence participates in closure.
            tid = batch.input_for(sid, batch.metric_ids[0]).template_id
            link = scoring.consensus_no_coverage_links.get(tid)
            if link is not None:
                links[sid] = link
                groups.setdefault(link["scope_key"], []).append(sid)
        consensus = read_consensus(repository, batch, groups, links)
        common = dict(registry_manifest_hash=batch.registry_manifest_hash, registry_hashes=dict(scoring.role_hashes),
            frozen_input_hash=batch.frozen_input_hash, universe_hash=batch.universe_hash,
            population_hash=batch.population_hash, metric_batch_hash=batch.batch_hash, as_of_utc=_FREEZE)
        ready, pending = [], {}
        for sid in batch.security_ids:
            first = batch.input_for(sid, batch.metric_ids[0])
            reasons = set()
            if first.template_id is None:
                reasons.add("invalid_template")
            if first.secondary_industry is None:
                reasons.add("invalid_industry")
            bundle = full.get(sid)
            if bundle is None and first.template_id is not None:
                reasons.add("current_receipt_absent")
            actual, link = consensus.get(sid), links.get(sid)
            neutral, consensus_reasons = consensus_branch(link, actual)
            reasons.update(consensus_reasons)
            cyclic = first.secondary_industry in scoring.cyclic_secondary_industries
            if bundle is not None:
                full_reasons, count = full_gate(bundle, vocabulary.slots_for_template(bundle.template_id),
                    batch.feature_states[sid], cyclic=cyclic, exempt_key=link["feature_key"] if neutral else None)
                reasons.update(full_reasons)
            if reasons:
                pending[sid] = tuple(sorted(reasons))
                continue
            slots = {}
            full_values = {value.slot_id: value for value in bundle.values}
            for mid, definition in batch.definitions[bundle.template_id].items():
                bound = definition["definition"]
                feature_values = tuple(full_values[key] for key in bound["required_feature_keys"])
                refs = {ref.formal_fact_id: ref.to_dict() for value in feature_values for ref in value.evidence}
                is_neutral = neutral and mid == link["metric_id"]
                context = None if is_neutral else peer_context(batch, metric_id=mid, security_id=sid)
                score = None if is_neutral else percentile(batch, context)
                if not is_neutral and score is None:
                    reasons.add("metric_pending:" + mid + ":" + context.reason)
                    continue
                if is_neutral:
                    quality = Decimal("0.8") if actual["evidence"]["calendar_binding"] is not None else Decimal("1")
                else:
                    score.require_verified()
                    quality = temporal_quality(tuple(refs.values()))
                slots[mid] = dict(metric_id=mid, definition=definition,
                    dimension_weight=scoring.dimension_weights[bound["dimension"]], internal_weight=Decimal(bound["internal_weight"]),
                    value=Decimal("50") if is_neutral else Decimal(score.percentile),
                    evidence_kind="registered_consensus_no_coverage" if is_neutral else "metric_percentile",
                    temporal_quality=quality, evidence_refs=tuple(refs[key] for key in sorted(refs)),
                    full_feature_values=tuple(value.to_dict() for value in feature_values),
                    metric_score=None if score is None else score.to_dict(),
                    context_fact=actual if is_neutral else None, registered_rule=link if is_neutral else None)
            if reasons:
                pending[sid] = tuple(sorted(reasons))
                continue
            if len(slots) != 25:
                raise ValueError("complete score input requires exactly all 25 qualified slots")
            payload = dict(common, schema_version="formal-score-input-v1", security_id=sid,
                template_id=bundle.template_id, primary_industry=first.primary_industry,
                secondary_industry=first.secondary_industry, cyclic=cyclic, continuous_fy_count=count,
                history_endpoints=bundle.history_endpoints, comparable_quarter_keys=bundle.comparable_quarter_keys,
                feature_state=batch.feature_states[sid], full_feature_bundle=bundle.to_dict(),
                full_feature_bundle_hash=bundle.bundle_hash(), slots=slots,
                consensus_context=actual, consensus_rule=link, confidence_cap=Decimal("0.90") if neutral else None)
            payload["input_hash"] = digest(payload)
            ready.append(payload)
        # Authenticate immutable files again after all calculations and Context
        # reads, outside the short writer fence. DB/provider changes are caught
        # by the enclosing guard, including missing-to-present transitions.
        for sid, earlier in full.items():
            if read_full(repository, batch, sid).canonical_bytes() != earlier.canonical_bytes():
                raise ValueError("complete score full bundle changed during final sweep")
        if encode(read_consensus(repository, batch, groups, links)) != encode(consensus):
            raise ValueError("complete score consensus correction or absence changed during batch")
        scoring.require_official(graph)
        dependencies(repository)
        payload = dict(common, schema_version="formal-score-input-batch-v1", security_ids=batch.security_ids,
            inputs=ready, pending_reasons=pending, metric_batch=batch.to_dict(),
            registry_manifest=json.loads(graph.manifest.canonical_json),
            consensus_facts=consensus)
        payload["batch_hash"] = digest(payload)
        inputs = tuple(mint(FormalScoreInput, dict(row, batch_hash=payload["batch_hash"]), publication)
            for row in ready)
        index = dict.fromkeys(batch.security_ids)
        index.update({row["security_id"]: item for row, item in zip(ready, inputs, strict=True)})
        result = mint(FormalScoreInputBatch, payload, publication, attributes=dict(inputs=inputs), index=index)

        def publish_complete():
            dependencies(repository)
            publication[0] = True
            return result

        return guard.finalize(publish_complete)

    class FormalScoreInputRepository:
        __slots__ = ("__weakref__",)

        def __init__(self, feature_repository, context_repository, *, registry_signature_verifier):
            if type(self) is not FormalScoreInputRepository or id(self) in repositories:
                raise ValueError("complete score repository initialization is exact and single-use")
            require_feature(feature_repository)
            contexts = FormalMetricContextRepository(feature_repository._store, context_repository,
                registry_signature_verifier=registry_signature_verifier)
            metrics = FormalMetricInputRepository(feature_repository, context_repository,
                registry_signature_verifier=registry_signature_verifier)
            identity = id(self)
            repositories[identity] = (weakref.ref(self, lambda _: repositories.pop(identity, None)),
                feature_repository, context_repository, registry_signature_verifier, metrics, contexts)
            dependencies(self)

        def build_batch(self, frozen_input_hash, *, scoring_registry):
            feature, _, _, _, _ = dependencies(self)
            publication = [False]
            try:
                with batch_guard(feature._current_input_provider, feature._store) as guard:
                    result = build(self, frozen_input_hash, scoring_registry, guard, publication)
                dependencies(self)
                return result
            except BaseException:
                publication[0] = False
                raise

        def __copy__(self):
            raise TypeError("complete score repository cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("complete score repository cannot be copied")

    own_methods = capture_methods((Proof, FormalScoreInput, FormalScoreInputBatch, FormalScoreInputRepository))
    return FormalScoreInputRepository, FormalScoreInputBatch, FormalScoreInput


FormalScoreInputRepository, FormalScoreInputBatch, FormalScoreInput = _install_score_inputs()
del _install_score_inputs

__all__ = ["FormalScoreInputRepository", "FormalScoreInputBatch", "FormalScoreInput"]
