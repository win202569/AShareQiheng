"""Deterministic metric percentiles; raw arithmetic cannot mint formal proofs."""

from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext
from dataclasses import fields
import hashlib
import json
from types import MappingProxyType
import weakref

from .formal_context_repository import FormalContextRepository
from .formal_feature_repository import FormalFeatureRepository, VerifiedMetricFeatureProjection, VerifiedMetricFeatureAbsence
from .formal_feature_repository import _require_authentic_metric_feature_repository
from .formal_metric_context import FormalMetricContextRepository
from .formal_metric_batch_guard import _metric_batch_guard
from .formal_registry_manifest import FormalRegistryBundleLoader
from .formal_scoring_registry import FormalScoringRegistry


def _arithmetic_context():
    # Explicit every context option: neither getcontext nor DefaultContext is
    # authoritative. Recurring division retains 50 deterministic significant
    # digits, without display quantization; it is not claimed to be exact.
    return Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
        capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])


def percentile_rank(raw_value, values, *, direction):
    """Return (average ascending rank, directional percentile), never a proof."""
    if (type(raw_value) is not Decimal or not raw_value.is_finite()
            or type(values) is not tuple or not values
            or any(type(value) is not Decimal or not value.is_finite() for value in values)
            or raw_value not in values or direction not in ("higher", "lower")):
        raise ValueError("percentile requires finite Decimal peers, their focal value and a signed direction")
    with localcontext(_arithmetic_context()):
        below = sum(value < raw_value for value in values)
        tied = sum(value == raw_value for value in values)
        rank = Decimal(below) + (Decimal(tied) + 1) / 2
        percentile = 100 * (rank - Decimal("0.5")) / len(values)
        return rank, 100 - percentile if direction == "lower" else percentile


def _plain(value):
    if isinstance(value, (dict, MappingProxyType)):
        return {key: _plain(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_plain(item) for item in value]
    return str(value) if type(value) is Decimal else value


def _canonical(value):
    return json.dumps(_plain(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) in (tuple, list):
        result = tuple(_freeze(item) for item in value)
        return value if type(value) is tuple and all(a is b for a, b in zip(value, result, strict=True)) else result
    return value


def _install_engine():
    repositories, proofs = {}, {}
    context_type = FormalMetricContextRepository
    feature_read = FormalFeatureRepository.select_current_verified_metric_feature_state
    require_feature = _require_authentic_metric_feature_repository
    batch_guard = _metric_batch_guard
    load_root = FormalRegistryBundleLoader.load
    decimal_context = _arithmetic_context
    encode, digest, freeze = _canonical, _digest, _freeze
    checked = tuple((cls, name, method) for cls in (context_type, FormalFeatureRepository,
        FormalContextRepository, FormalRegistryBundleLoader, FormalScoringRegistry)
        for name, method in vars(cls).items() if callable(method) or isinstance(method, (staticmethod, classmethod)))

    def state(feature, context, verifier):
        require_feature(feature)
        if (type(feature) is not FormalFeatureRepository or type(context) is not FormalContextRepository
                or feature._store is not context._state_store or feature._verifier is not verifier
                or context._verifier is not verifier):
            raise ValueError("metric input repository requires exact same-store repositories and verifier")
        for cls, name, method in checked:
            if vars(cls).get(name) is not method:
                raise ValueError("metric input read or registry dependency changed")
            for instance in (feature, context):
                if type(instance) is cls and name in vars(instance):
                    raise ValueError("metric input repository reader overridden")
        return (id(feature), id(context), id(verifier), id(feature._store), id(feature._bundle_store),
            id(feature._current_input_provider), id(context._snapshots))

    def dependencies(repo):
        record = repositories.get(id(repo))
        if type(repo) is not FormalMetricInputRepository or record is None or record[0]() is not repo:
            raise ValueError("metric input repository is uninitialized or copied")
        feature, context, verifier, metric_context, initial = record[1:]
        if state(feature, context, verifier) != initial:
            raise ValueError("metric input repository trust dependencies changed")
        return feature, context, verifier, metric_context

    def record(proof, cls):
        found = proofs.get(id(proof))
        if type(proof) is not cls or found is None or found[0]() is not proof or not found[4][0]:
            raise ValueError("metric proof is forged or copied")
        return found

    class Proof:
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("metric proofs are produced only by authenticated complete batches")

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
            raise TypeError("metric proof cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("metric proof cannot be copied")

    class MetricInput(Proof):
        __slots__ = ()

    class MetricInputBatch(Proof):
        __slots__ = ()

        def input_for(self, security_id, metric_id):
            if type(security_id) is not str or type(metric_id) is not str:
                raise ValueError("metric selectors require exact strings")
            result = record(self, MetricInputBatch)[3]["index"].get((security_id, metric_id))
            if result is None:
                raise ValueError("security or qualified metric is outside this complete batch")
            return result

    class MetricPeerContext(Proof):
        __slots__ = ()

    class MetricScore(Proof):
        __slots__ = ()

    def mint(cls, payload, *, attributes=None, private=None, publication=None):
        proof = object.__new__(cls)
        identity = id(proof)
        data = dict(payload)
        data.update(attributes or {})
        proofs[identity] = (weakref.ref(proof, lambda _: proofs.pop(identity, None)), freeze(data), encode(payload),
            private, [True] if publication is None else publication)
        return proof

    def definitions(scoring):
        result = {}
        for tid in scoring.templates:
            template = scoring.template_for(tid)
            result[tid] = {}
            for dimension, metrics in template.metrics.items():
                for metric in metrics:
                    key = dimension + "." + metric.metric_id
                    definition = {field.name: _plain(getattr(metric, field.name)) for field in fields(metric)}
                    payload = dict(template_id=tid, metric_id=key, definition=definition,
                        registry_manifest_hash=scoring.registry_manifest_hash,
                        scoring_registry_hash=scoring.content_sha256, feature_registry_hash=scoring.role_hashes["feature"])
                    payload["definition_hash"] = digest(payload)
                    result[tid][key] = payload
        return result

    def build(repo, frozen_input_hash, scoring, metric_ids, guard):
        feature, _, verifier, context = dependencies(repo)
        universe = context.load_universe(frozen_input_hash, scoring_registry=scoring)
        if universe is None:
            return None
        universe.require_verified()
        root = load_root(FormalRegistryBundleLoader(feature._store, verifier), universe.registry_manifest_hash)
        scoring.require_official(root)
        defs = definitions(scoring)
        known = set().union(*(set(items) for items in defs.values()))
        selected = tuple(sorted(known)) if metric_ids is None else metric_ids
        if (type(selected) is not tuple or not selected or any(type(mid) is not str for mid in selected)
                or selected != tuple(sorted(set(selected))) or any(mid not in known for mid in selected)):
            raise ValueError("metric IDs must be nonempty sorted unique registered dimension.metric_id strings")
        industry = context.resolve_industries(universe)
        industry.require_verified()
        common = dict(registry_manifest_hash=universe.registry_manifest_hash,
            frozen_input_hash=universe.frozen_input_hash, universe_hash=universe.universe_hash,
            population_hash=universe.population_hash, as_of_utc=universe.as_of_utc,
            industry_batch_hash=industry.batch_hash, registry_hashes=dict(scoring.role_hashes),
            universe_proof_hash=hashlib.sha256(universe.canonical_bytes()).hexdigest())
        rows, markers, requests = [], {}, {}
        for sid in universe.security_ids:
            assignment = industry.entries[sid]
            signed_member = next((m for m in universe.industry["memberships"] if m["security_id"] == sid), None)
            tid = None if signed_member is None else signed_member["template_id"]
            marker = None
            if tid is not None:
                keys = tuple(sorted({key for mid in selected for key in defs[tid][mid]["definition"]["required_feature_keys"]}))
                request = dict(security_id=sid, as_of_utc=universe.as_of_utc, template_id=tid,
                    registry_manifest_hash=universe.registry_manifest_hash, required_feature_keys=keys)
                marker = feature_read(feature, **request)
                if type(marker) not in (VerifiedMetricFeatureProjection, VerifiedMetricFeatureAbsence):
                    raise ValueError("metric feature current state requires a genuine present or absence proof")
                marker.require_verified()
                requests[sid] = request
                markers[sid] = marker.canonical_bytes()
            for mid in selected:
                binding = None if tid is None else defs[tid][mid]
                reason = "invalid_template" if tid is None else assignment["pending_reason"]
                value, refs, projection_hash = None, (), None
                if reason is None:
                    if type(marker) is VerifiedMetricFeatureAbsence:
                        reason = "current_receipt_absent"
                    else:
                        projection_hash = marker.projection_hash
                        definition = binding["definition"]
                        by_id = {item.slot_id: item for item in marker.values}
                        chosen = tuple(by_id[key] for key in definition["required_feature_keys"])
                        for item in chosen:
                            if item.status != "derived":
                                reason = item.missing_reason or "missing_verified_fact"
                                break
                            if item.unit != definition["unit_rule"]:
                                reason = "unsupported_unit"
                                break
                        if reason is None:
                            value = Decimal(str(by_id[definition["field_map"]["value"]].value))
                            if not value.is_finite():
                                raise ValueError("verified metric feature value is not finite")
                            refs = tuple(sorted({e.formal_fact_id for item in chosen for e in item.evidence}))
                            if not refs:
                                raise ValueError("derived metric has no verified evidence")
                payload = dict(common, security_id=sid, metric_id=mid, template_id=tid,
                    primary_industry=assignment.get("primary_industry"), secondary_industry=assignment.get("secondary_industry"),
                    definition_hash=None if binding is None else binding["definition_hash"],
                    direction=None if binding is None else binding["definition"]["direction"],
                    unit=None if binding is None else binding["definition"]["unit_rule"],
                    raw_value=value, verified_feature_refs=refs, invalid_reason=reason,
                    status="eligible" if reason is None else "pending_evidence", projection_hash=projection_hash,
                    feature_state_hash=None if marker is None else hashlib.sha256(markers[sid]).hexdigest())
                payload["input_hash"] = digest(payload)
                rows.append(payload)
        # Cross-member closure: every current state is re-read after the first
        # pass; both absence transitions and numeric corrections invalidate all.
        for sid, request in requests.items():
            current = feature_read(feature, **request)
            current.require_verified()
            if current.canonical_bytes() != markers[sid]:
                raise ValueError("metric feature correction or absence changed during complete batch")
        context.recheck_batch(universe, industry)
        scoring.require_official(root)
        dependencies(repo)
        payload = dict(common, schema_version="formal-metric-input-batch-v1", metric_ids=selected,
            security_ids=tuple(universe.security_ids), definitions=defs, inputs=rows,
            feature_states={sid: json.loads(wire) for sid, wire in markers.items()})
        payload["batch_hash"] = digest(payload)
        # Expensive immutable preparation holds no writer reservation. Every
        # prepared proof shares this closure-private, unpublished capability.
        publication = [False]
        inputs = tuple(mint(MetricInput, dict(row, batch_hash=payload["batch_hash"]),
            publication=publication) for row in rows)
        index = {(row["security_id"], row["metric_id"]): item for row, item in zip(rows, inputs, strict=True)}
        prepared = mint(MetricInputBatch, payload, attributes=dict(inputs=inputs), private=dict(index=index,
            groups=None, ranks={}, contexts={}), publication=publication)

        def publish_complete():
            publication[0] = True
            return prepared

        try:
            return guard.finalize(publish_complete)
        except BaseException:
            publication[0] = False
            raise

    class FormalMetricInputRepository:
        __slots__ = ("__weakref__",)

        def __init__(self, feature_repository, context_repository, *, registry_signature_verifier):
            if type(self) is not FormalMetricInputRepository or id(self) in repositories:
                raise ValueError("metric input repository initialization must be exact and single-use")
            snapshot = state(feature_repository, context_repository, registry_signature_verifier)
            context = context_type(feature_repository._store, context_repository,
                registry_signature_verifier=registry_signature_verifier)
            identity = id(self)
            repositories[identity] = (weakref.ref(self, lambda _: repositories.pop(identity, None)),
                feature_repository, context_repository, registry_signature_verifier, context, snapshot)

        def build_batch(self, frozen_input_hash, *, scoring_registry, metric_ids=None):
            feature, _, _, _ = dependencies(self)
            result = None
            try:
                with batch_guard(feature._current_input_provider, feature._store) as guard:
                    result = build(self, frozen_input_hash, scoring_registry, metric_ids, guard)
            except BaseException:
                # Also revoke if context-manager rollback/close fails after the
                # inner finalizer returned its prepared capability.
                if result is not None:
                    proofs[id(result)][4][0] = False
                raise
            return result

        def __copy__(self):
            raise TypeError("metric input repository cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("metric input repository cannot be copied")

    def eligible(item):
        return record(item, MetricInput)[1]["invalid_reason"] is None

    def peer_context(batch, *, metric_id, security_id):
        if type(security_id) is not str or type(metric_id) is not str:
            raise ValueError("metric selectors require exact strings")
        data, private = record(batch, MetricInputBatch)[1], record(batch, MetricInputBatch)[3]
        focal = private["index"].get((security_id, metric_id))
        if focal is None:
            raise ValueError("security or qualified metric is outside this complete batch")
        security_id, metric_id = focal.security_id, focal.metric_id
        key = (security_id, metric_id)
        if key in private["contexts"]:
            return private["contexts"][key]
        if private["groups"] is None:
            groups = {}
            for item in data["inputs"]:
                if eligible(item):
                    for scope, industry_id in (("template_secondary_industry", item.secondary_industry),
                            ("template_primary_industry", item.primary_industry)):
                        group = (item.metric_id, item.template_id, scope, industry_id)
                        groups.setdefault(group, []).append(item.security_id)
            private["groups"] = {group: tuple(sorted(ids)) for group, ids in groups.items()}
        reason, scope, peers = focal.invalid_reason, None, ()
        if reason is None:
            for candidate_scope, industry_id in (("template_secondary_industry", focal.secondary_industry),
                    ("template_primary_industry", focal.primary_industry)):
                peers = private["groups"].get((metric_id, focal.template_id, candidate_scope, industry_id), ())
                if len(peers) >= 20:
                    scope = candidate_scope
                    break
            if scope is None:
                reason = "peer_count_below_20"
        payload = dict(schema_version="formal-metric-peer-context-v1", batch_hash=data["batch_hash"],
            registry_manifest_hash=data["registry_manifest_hash"], frozen_input_hash=data["frozen_input_hash"],
            universe_hash=data["universe_hash"], metric_id=metric_id, security_id=security_id,
            definition_hash=focal.definition_hash, direction=focal.direction, scope=scope,
            peer_security_ids=peers, peer_count=len(peers), reason=reason)
        payload["cohort_hash"] = digest(dict(batch_hash=data["batch_hash"], metric_id=metric_id,
            definition_hash=focal.definition_hash, direction=focal.direction, scope=scope, peer_security_ids=peers))
        payload["context_hash"] = digest(payload)
        result = mint(MetricPeerContext, payload, attributes=dict(peer_security_ids=peers), private=weakref.ref(batch),
            publication=record(batch, MetricInputBatch)[4])
        private["contexts"][key] = result
        return result

    def score(batch, context):
        batch_record = record(batch, MetricInputBatch)
        context_record = record(context, MetricPeerContext)
        if context_record[3]() is not batch:
            raise ValueError("metric peer context belongs to another complete batch")
        c, private = context_record[1], batch_record[3]
        if c["reason"] is not None:
            return None
        if c["peer_count"] < 20:
            raise ValueError("formal percentile requires at least twenty peers")
        cohort = c["cohort_hash"]
        if cohort not in private["ranks"]:
            values = sorted(private["index"][(sid, c["metric_id"])].raw_value for sid in c["peer_security_ids"])
            ranks = {}
            with localcontext(decimal_context()):
                first = 0
                while first < len(values):
                    last = first + 1
                    while last < len(values) and values[last] == values[first]:
                        last += 1
                    rank = (Decimal(first + 1) + Decimal(last)) / 2
                    percentile = 100 * (rank - Decimal("0.5")) / len(values)
                    ranks[values[first]] = (rank, 100 - percentile if c["direction"] == "lower" else percentile)
                    first = last
            private["ranks"][cohort] = ranks
        focal = private["index"][(c["security_id"], c["metric_id"])]
        rank, percentile = private["ranks"][cohort][focal.raw_value]
        payload = dict(schema_version="formal-metric-score-v1", batch_hash=batch.batch_hash,
            registry_manifest_hash=batch.registry_manifest_hash, frozen_input_hash=batch.frozen_input_hash,
            universe_hash=batch.universe_hash, metric_id=focal.metric_id, security_id=focal.security_id,
            definition_hash=focal.definition_hash, input_hash=focal.input_hash, raw_value=focal.raw_value,
            average_rank=rank, percentile=percentile, peer_count=c["peer_count"], peer_context=context.to_dict())
        payload["score_hash"] = digest(payload)
        return mint(MetricScore, payload, attributes=dict(peer_context=context), publication=batch_record[4])

    return FormalMetricInputRepository, MetricInput, MetricInputBatch, MetricPeerContext, MetricScore, eligible, peer_context, score


(FormalMetricInputRepository, MetricInput, MetricInputBatch, MetricPeerContext, MetricScore,
 metric_peer_eligible, build_metric_peer_context, score_metric_percentile) = _install_engine()
del _install_engine

__all__ = ["FormalMetricInputRepository", "MetricInput", "MetricInputBatch", "MetricPeerContext", "MetricScore",
    "metric_peer_eligible", "build_metric_peer_context", "score_metric_percentile", "percentile_rank"]
