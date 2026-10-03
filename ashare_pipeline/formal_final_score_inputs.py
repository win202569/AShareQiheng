"""Complete frozen-universe inputs with Stage C valuation score provenance.

Only this repository can publish D1 proofs. Business gaps remain authenticated
entries; identity mismatches abort the whole publication.
"""

import hashlib
import inspect
import json
import weakref
from contextlib import closing, contextmanager
from types import MappingProxyType

from .formal_final_publication import _claim_preparation

from . import formal_metric_engine as metric_engine
from .formal_metric_batch_guard import _metric_batch_guard, FormalMetricCurrentInputProvider
from .state_store import StateStore
from .formal_metric_engine import _canonical, _digest, _freeze
from .formal_policy_registry import FormalPolicyRegistry
from .formal_policy_repository import FormalPolicyRepository, VerifiedPolicyResultBatch, PolicyResult
from .formal_registry_manifest import FormalRegistryBundleLoader
from .formal_score_inputs import FormalScoreInputRepository, FormalScoreInputBatch, FormalScoreInput
from .formal_scoring_registry import FormalScoringRegistry
from .formal_valuation_adapter_contract import FormalValuationAdapterRegistry
from .formal_valuation_engine import (
    FormalValuationRepository, PolicyAdjustedValuationBatch,
    PolicyAdjustedValuationScore, PolicyAdjustedValuationPeerContext,
    build_valuation_peer_context, score_valuation_percentile,
)


def _install_source_checkpoint():
    # Capture the existing provider's authentication authority, not a caller's
    # replaceable accessor. Like D3's D2 ownership check, no new mint is exposed.
    require = inspect.getclosurevars(FormalMetricCurrentInputProvider.resolve_current_inputs).nonlocals["require"]
    connect = StateStore._connect

    def source_digest(connection):
        digest = hashlib.sha256()
        for name, ddl in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"):
            if name.startswith(("formal_final_", "sqlite_")):
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            # Content, not data_version: our own append-only Stage D history is
            # deliberately excluded. Conservative unrelated-source changes fail
            # closed; no expensive metric/policy/valuation calculations repeat.
            rows = sorted(repr(tuple(row)) for row in connection.execute("SELECT * FROM " + quoted))
            digest.update(repr((name, ddl, rows)).encode())
        return digest.digest()

    def capture(store, provider):
        owned = require(provider, store)
        with owned["lock"], closing(connect(store)) as connection:
            epoch = owned["epoch"]
            connection.execute("BEGIN")
            baseline = source_digest(connection)
        class Checkpoint:
            __slots__ = ()

            def recheck(self, connection=None):
                with owned["lock"]:
                    if require(provider, store) is not owned or owned["epoch"] != epoch:
                        raise ValueError("final current-source provider changed")
                    if connection is None:
                        with closing(connect(store)) as current:
                            current.execute("BEGIN")
                            actual = source_digest(current)
                    else:
                        database = connection.execute("PRAGMA database_list").fetchone()[2]
                        from pathlib import Path
                        if Path(database).resolve() != Path(store.db_path).resolve():
                            raise ValueError("final current-source transaction owner differs")
                        actual = source_digest(connection)
                    if actual != baseline:
                        raise ValueError("final current-source database evidence changed")

            @contextmanager
            def hold(self):
                with owned["lock"]:
                    self.recheck()
                    if owned["finalizing"]:
                        raise ValueError("final current-source provider is already finalizing")
                    owned["finalizing"] = True
                    try:
                        yield
                    finally:
                        owned["finalizing"] = False
        return Checkpoint()
    return capture


_current_source_checkpoint = _install_source_checkpoint()
del _install_source_checkpoint


def _install_final_inputs():
    repositories, proofs, prepared_gates, prepared_origins = {}, {}, {}, {}
    claim = _claim_preparation
    encode, digest, freeze = _canonical, _digest, _freeze
    decode, sha256, reference = json.loads, hashlib.sha256, weakref.ref
    guard_factory, load_root = _metric_batch_guard, FormalRegistryBundleLoader.load
    base_build = FormalScoreInputRepository.build_batch
    policy_build = FormalPolicyRepository.build_batch
    valuation_build = FormalValuationRepository.build_batch
    scoring_verify = FormalScoringRegistry.require_authenticated
    policy_verify = FormalPolicyRegistry.require_verified
    adapter_verify = FormalValuationAdapterRegistry.require_current_bundle
    peer_context, percentile = build_valuation_peer_context, score_valuation_percentile
    metric_owner = vars(metric_engine)
    metric_dependencies = metric_engine._metric_definition_dependency_changes
    v_metrics = ("V.enterprise_value_or_sustainable_roe", "V.normalized_earnings_yield",
                 "V.normalized_free_cash_flow_yield")
    source_types = (FormalScoreInputBatch, VerifiedPolicyResultBatch, PolicyAdjustedValuationBatch)
    owner = globals()
    captured = tuple((name, value) for name, value in owner.items()
        if callable(value) and name != "_install_final_inputs")
    classes = {base for cls in (*source_types, FormalScoreInput, PolicyResult,
        PolicyAdjustedValuationScore, PolicyAdjustedValuationPeerContext,
        FormalScoreInputRepository, FormalPolicyRepository, FormalValuationRepository,
        FormalScoringRegistry, FormalPolicyRegistry, FormalValuationAdapterRegistry,
        FormalRegistryBundleLoader) for base in cls.__mro__ if base is not object}
    checked = tuple((cls, name, value) for cls in classes for name, value in vars(cls).items()
        if callable(value) or isinstance(value, (staticmethod, classmethod)))

    def interfaces():
        if (owner.get("_prepare_final_inputs") is not prepare
                or metric_owner.get("_freeze") is not freeze
                or metric_owner.get("_metric_definition_dependency_changes") is not metric_dependencies
                or metric_dependencies()
                or FormalScoringRegistry.require_authenticated is not scoring_verify
                or FormalPolicyRegistry.require_verified is not policy_verify
                or FormalValuationAdapterRegistry.require_current_bundle is not adapter_verify
                or any(owner.get(name) is not value for name, value in captured)
                or any(vars(cls).get(name) is not value for cls, name, value in checked)
                or any(tuple(vars(cls).items()) != members for cls, members in own_members)):
            raise ValueError("final score authority dependency changed")

    def dependencies(repository):
        interfaces()
        saved = repositories.get(id(repository))
        if (type(repository) is not FormalFinalScoreInputRepository or saved is None
                or saved[0]() is not repository):
            raise ValueError("final score repository is forged or copied")
        feature, context, ranges, verifier, base, policy, valuation, identity = saved[1:]
        current = (id(feature._store), id(feature._bundle_store),
            id(feature._current_input_provider), id(context._snapshots))
        if (current != identity or feature._store is not context._state_store
                or feature._verifier is not verifier or context._verifier is not verifier):
            raise ValueError("final score repository graph changed")
        return feature, context, ranges, verifier, base, policy, valuation

    def record(proof, cls):
        interfaces()
        saved = proofs.get(id(proof))
        if (type(proof) is not cls or saved is None or saved[0]() is not proof
                or not saved[4][0] or saved[6] is not cls):
            raise ValueError("final score proof is forged, copied, unpublished or revoked")
        gate = prepared_gates.get(id(proof))
        if gate is not None and not gate():
            raise ValueError("final score proof is unpublished or revoked")
        original = prepared_origins.get(id(proof))
        if original is not None:
            record(original, cls)
        if cls is PolicyAdjustedScoreInput and encode(saved[1]) != saved[2]:
            raise ValueError("final score entry differs from its published canonical bytes")
        return saved

    class SealedMeta(type):
        def __setattr__(cls, name, value):
            raise TypeError("final score authority types are immutable")

        def __delattr__(cls, name):
            raise TypeError("final score authority types are immutable")

    subclass_open = [True]

    class Proof(metaclass=SealedMeta):
        __slots__ = ("__weakref__",)

        def __init_subclass__(cls, **kwargs):
            if not subclass_open[0]:
                raise TypeError("final score proof types cannot be inherited")

        def __init__(self, *args, **kwargs):
            raise TypeError("final score proofs require an authenticated complete batch")

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
            raise TypeError("final score proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("final score proofs cannot be copied")

        def __reduce_ex__(self, protocol):
            raise TypeError("final score proofs cannot be reconstructed")

    class PolicyAdjustedScoreInput(Proof):
        __slots__ = ()

    class PolicyAdjustedScoreInputBatch(Proof):
        __slots__ = ()

        def input_for(self, security_id):
            saved = record(self, PolicyAdjustedScoreInputBatch)
            if type(security_id) is not str or security_id not in saved[3]:
                raise ValueError("final score selector is outside the canonical universe")
            child = saved[3][security_id]
            child_state = record(child, PolicyAdjustedScoreInput)
            if (child_state[4] is not saved[4] or child_state[5] is not saved[5]
                    or child_state[1]["security_id"] != security_id
                    or any(child_state[1][key] != saved[1][key] for key in
                        ("batch_hash", "registry_manifest_hash", "frozen_input_hash", "universe_hash"))):
                raise ValueError("final score selector is not bound to this publication")
            return child

    subclass_open[0] = False

    def mint(cls, payload, publication, retention, *, attributes=None, index=None):
        result = object.__new__(cls)
        key = id(result)
        data = dict(payload)
        data.update(attributes or {})
        proofs[key] = (reference(result, lambda _: (proofs.pop(key, None), prepared_gates.pop(key, None),
            prepared_origins.pop(key, None))), freeze(data),
            encode(payload), index, publication, retention, cls)
        return result

    def verify_sources(sources):
        for source, cls in zip(sources, source_types, strict=True):
            if type(source) is not cls:
                raise ValueError("final score requires three genuine source batches")
            source.require_verified()
        return tuple(source.canonical_bytes() for source in sources)

    def registry_snapshot(
        feature, verifier, root, scoring, policy, adapter, *, expected_purpose
    ):
        if (type(expected_purpose) is not str
                or expected_purpose not in {"test", "official"}):
            raise ValueError("expected_purpose must be exact test or official")
        bundle = load_root(FormalRegistryBundleLoader(feature._store, verifier), root)
        if bundle.manifest.schema_version != "formal-registry-manifest-v2":
            raise ValueError("final score requires an authenticated v2 root")
        scoring_verify(
            scoring, bundle, expected_purpose=expected_purpose
        )
        policy_verify(policy)
        adapter_verify(
            adapter, bundle, expected_purpose=expected_purpose
        )
        if (policy.registry_manifest_hash != root or any(
                policy.role_hashes[role] != sha256(bundle.blob(role).canonical_json).hexdigest()
                for role in policy.role_hashes)):
            raise ValueError("final score registries have incompatible roots")
        return bundle, (bundle.manifest.canonical_json,
            tuple((role, bundle.blob(role).canonical_json) for role in bundle.roles),
            policy.canonical_bytes(), encode(adapter.to_dict()))

    def close_identity(frozen, frozen_hash, sources, bundle, policy_registry):
        base, policy, valuation = sources
        ids = tuple(sorted(member.security_id for member in frozen.members))
        if len(ids) != len(set(ids)):
            raise ValueError("final score frozen membership is duplicated")
        for source in sources:
            if (source.registry_manifest_hash != frozen.registry_manifest_hash
                    or source.frozen_input_hash != frozen_hash
                    or source.universe_hash != frozen.universe_hash
                    or source.as_of_utc != "2026-08-31T07:00:00+00:00"
                    or tuple(source.security_ids) != ids):
                raise ValueError("final score source batch identity or membership mismatch")
        if (base.population_hash != valuation.population_hash
                or policy.policy_contract_hash != policy_registry.contract_hash
                or valuation.policy_contract_hash != policy.policy_contract_hash
                or valuation.policy_batch_hash != policy.batch_hash
                or valuation.policy_batch_canonical_sha256 != sha256(policy.canonical_bytes()).hexdigest()
                or valuation.scoring_registry_hash != bundle.manifest.scoring_registry_hash
                or valuation.valuation_adapter_registry_hash != bundle.manifest.valuation_adapter_registry_hash
                or base.metric_batch["industry_batch_hash"] != valuation.industry_batch_hash
                or policy.evidence_batch.industry["batch_hash"] != valuation.industry_batch_hash
                or tuple(row.security_id for row in policy.results) != ids
                or tuple(valuation.metric_ids) != v_metrics
                or tuple((row.security_id, row.metric_id) for row in valuation.inputs)
                    != tuple((sid, mid) for sid in ids for mid in v_metrics)):
            raise ValueError("final score source policy, industry or valuation closure mismatch")
        ready_ids = tuple(row.security_id for row in base.inputs)
        if (len(ready_ids) != len(set(ready_ids)) or ready_ids != tuple(sorted(ready_ids))
                or set(ready_ids) & set(base.pending_reasons)
                or set(ready_ids) | set(base.pending_reasons) != set(ids)):
            raise ValueError("final score base batch membership is incomplete")
        return ids

    def member_identity(sid, industry, valuation_inputs, original):
        fields = ("template_id", "primary_industry", "secondary_industry")
        identity = {field: industry.get(field) for field in fields}
        if industry["security_id"] != sid:
            raise ValueError("final score member identity mismatch")
        inputs = valuation_inputs + (() if original is None else (original,))
        for item in inputs:
            item.require_verified()
            if (any(getattr(item, field) != identity[field] for field in fields)
                    or item.security_id != sid):
                raise ValueError("final score member identity mismatch")
        return identity

    class FormalFinalScoreInputRepository(metaclass=SealedMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, feature_repository, context_repository, range_store,
                     *, registry_signature_verifier):
            if type(self) is not FormalFinalScoreInputRepository or id(self) in repositories:
                raise ValueError("final score repository initialization is exact and single-use")
            interfaces()
            verifier = registry_signature_verifier
            base = FormalScoreInputRepository(feature_repository, context_repository,
                registry_signature_verifier=verifier)
            policy = FormalPolicyRepository(feature_repository, context_repository, range_store,
                registry_signature_verifier=verifier)
            valuation = FormalValuationRepository(feature_repository, context_repository, range_store,
                registry_signature_verifier=verifier)
            key = id(self)
            repositories[key] = (reference(self, lambda _: repositories.pop(key, None)),
                feature_repository, context_repository, range_store, verifier, base, policy, valuation,
                (id(feature_repository._store), id(feature_repository._bundle_store),
                 id(feature_repository._current_input_provider), id(context_repository._snapshots)))
            dependencies(self)

        def build_batch(self, frozen_input_hash, *, scoring_registry, policy_registry,
                        valuation_adapter_registry, expected_purpose="official"):
            feature, _, _, verifier, base_repo, policy_repo, valuation_repo = dependencies(self)
            if (type(frozen_input_hash) is not str or type(scoring_registry) is not FormalScoringRegistry
                    or type(policy_registry) is not FormalPolicyRegistry
                    or type(valuation_adapter_registry) is not FormalValuationAdapterRegistry
                    or type(expected_purpose) is not str
                    or expected_purpose not in {"test", "official"}):
                raise ValueError("final score publication requires exact authenticated inputs")
            publication = [False]
            try:
                with guard_factory(feature._current_input_provider, feature._store) as guard:
                    frozen = feature._store.get_verified_formal_frozen_universe(frozen_input_hash)
                    if frozen is None:
                        raise ValueError("final score frozen input is absent")
                    sources = (
                        base_build(base_repo, frozen_input_hash, scoring_registry=scoring_registry,
                            expected_purpose=expected_purpose),
                        policy_build(policy_repo, frozen_input_hash, scoring_registry=scoring_registry,
                            policy_registry=policy_registry,
                            expected_purpose=expected_purpose),
                        valuation_build(valuation_repo, frozen_input_hash, scoring_registry=scoring_registry,
                            policy_registry=policy_registry,
                            valuation_adapter_registry=valuation_adapter_registry,
                            expected_purpose=expected_purpose),
                    )
                    source_bytes = verify_sources(sources)
                    base, policy, valuation = sources
                    bundle, registry_bytes = registry_snapshot(feature, verifier, frozen.registry_manifest_hash,
                        scoring_registry, policy_registry, valuation_adapter_registry,
                        expected_purpose=expected_purpose)
                    ids = close_identity(frozen, frozen_input_hash, sources, bundle, policy_registry)
                    common = dict(registry_manifest_hash=frozen.registry_manifest_hash,
                        frozen_input_hash=frozen_input_hash, universe_hash=frozen.universe_hash,
                        population_hash=base.population_hash, as_of_utc=base.as_of_utc,
                        scoring_registry_hash=bundle.manifest.scoring_registry_hash,
                        policy_contract_hash=policy.policy_contract_hash,
                        valuation_adapter_registry_hash=valuation.valuation_adapter_registry_hash)
                    for prefix, source, raw in zip(("base", "policy", "valuation"), sources, source_bytes, strict=True):
                        common[prefix + "_batch_hash"] = source.batch_hash
                        common[prefix + "_batch_canonical_sha256"] = sha256(raw).hexdigest()
                    rows, derived = [], []
                    for sid, policy_result in zip(ids, policy.results, strict=True):
                        policy_result.require_verified()
                        original = base.input_for(sid)
                        base_reasons = tuple(base.pending_reasons.get(sid, ()))
                        reasons = {"base:" + reason for reason in base_reasons}
                        policy_pending = policy_result.to_dict()["pending_requirements"]
                        if policy_result.evidence_state == "pending_evidence" or policy_pending:
                            reasons.add("policy:pending_evidence")
                        valuation_reasons, adjusted_slots = {}, {}
                        if original is not None:
                            if type(original) is not FormalScoreInput or original.security_id != sid:
                                raise ValueError("final score base entry identity mismatch")
                            original.require_verified()
                        valuation_inputs = tuple(valuation.input_for(sid, mid) for mid in v_metrics)
                        identity = member_identity(sid, policy.evidence_batch.industry["entries"][sid],
                            valuation_inputs, original)
                        for mid, adjusted in zip(v_metrics, valuation_inputs, strict=True):
                            context = peer_context(valuation, metric_id=mid, security_id=sid)
                            context.require_verified()
                            if adjusted.adjustment["policy_result_hash"] != policy_result.result_hash:
                                raise ValueError("final score valuation policy result mismatch")
                            score = percentile(valuation, context)
                            derived.append(context)
                            if score is None:
                                if context.reason is None:
                                    raise ValueError("final score valuation score absent without a reason")
                                valuation_reasons[mid] = context.reason
                                reasons.add("valuation:" + mid + ":" + context.reason)
                                continue
                            if type(score) is not PolicyAdjustedValuationScore:
                                raise ValueError("final score requires genuine Stage C scores")
                            score.require_verified()
                            if (score.security_id != sid or score.metric_id != mid
                                    or score.batch_hash != valuation.batch_hash
                                    or score.adjusted_input_hash != adjusted.input_hash
                                    or score.peer_context is not context):
                                raise ValueError("final score Stage C score identity mismatch")
                            derived.append(score)
                            if original is not None:
                                slot = dict(original.slots[mid])
                                slot.update(value=score.percentile, evidence_kind="policy_adjusted_valuation",
                                    metric_score=None, valuation_score=score.to_dict(),
                                    valuation_context=context.to_dict(), valuation_input=adjusted.to_dict(),
                                    valuation_score_hash=score.score_hash,
                                    valuation_context_hash=context.context_hash)
                                adjusted_slots[mid] = slot
                        slots = {} if original is None else dict(original.slots)
                        # A pending row must never expose an unadjusted V score as final.
                        for mid in v_metrics:
                            slots.pop(mid, None)
                        slots.update(adjusted_slots)
                        if not reasons and (original is None or len(slots) != 25
                                or len(set(slots) - set(v_metrics)) != 22 or len(adjusted_slots) != 3):
                            raise ValueError("ready final score requires 22 base and three Stage C slots")
                        payload = {} if original is None else original.to_dict()
                        payload.pop("batch_hash", None)
                        payload.pop("input_hash", None)
                        payload.update(identity)
                        payload.update(common, schema_version="policy-adjusted-score-input-v1",
                            security_id=sid, status="pending_evidence" if reasons else "ready",
                            reasons=tuple(sorted(reasons)), slots=slots,
                            base_input_hash=None if original is None else original.input_hash,
                            base_pending_reasons=base_reasons, policy_result=policy_result.to_dict(),
                            policy_result_hash=policy_result.result_hash,
                            policy_pending_requirements=policy_pending,
                            valuation_pending_reasons=valuation_reasons)
                        payload["entry_hash"] = digest(payload)
                        rows.append(payload)
                    payload = dict(common, schema_version="policy-adjusted-score-input-batch-v1",
                        security_ids=ids, inputs=rows)
                    payload["batch_hash"] = digest(payload)
                    # Keep genuine source chains alive, including Stage C's repository owner.
                    checkpoint = [None]
                    retention = (self, sources, tuple(derived), checkpoint,
                        expected_purpose, scoring_registry, policy_registry,
                        valuation_adapter_registry, registry_bytes,
                        frozen.registry_manifest_hash)
                    children = tuple(mint(PolicyAdjustedScoreInput,
                        dict(row, batch_hash=payload["batch_hash"]), publication, retention) for row in rows)
                    index = MappingProxyType(dict(zip(ids, children, strict=True)))
                    prepared = mint(PolicyAdjustedScoreInputBatch, payload, publication, retention,
                        attributes={"inputs": children}, index=index)

                    def publish():
                        dependencies(self)
                        if verify_sources(sources) != source_bytes:
                            raise ValueError("final score source canonical bytes changed")
                        _, current_registry_bytes = registry_snapshot(feature, verifier,
                            frozen.registry_manifest_hash, scoring_registry, policy_registry,
                            valuation_adapter_registry,
                            expected_purpose=expected_purpose)
                        if current_registry_bytes != registry_bytes:
                            raise ValueError("final score registry bytes changed")
                        close_identity(frozen, frozen_input_hash, sources, bundle, policy_registry)
                        for item in derived:
                            item.require_verified()
                        if (proofs[id(prepared)][2] != encode(payload)
                                or any(proofs[id(child)][2] != encode(dict(row,
                                    batch_hash=payload["batch_hash"]))
                                    for child, row in zip(children, rows, strict=True))):
                            raise ValueError("final score prepared canonical bytes changed")
                        checkpoint[0] = _current_source_checkpoint(feature._store, feature._current_input_provider)
                        publication[0] = True
                        return prepared

                    result = guard.finalize(publish)
                dependencies(self)
                return result
            except BaseException:
                publication[0] = False
                raise

        def __copy__(self):
            raise TypeError("final score repositories cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("final score repositories cannot be copied")

    def prepare(source, capability):
        gate = claim(capability, source, "inputs")
        saved = record(source, PolicyAdjustedScoreInputBatch)
        original_rows = {sid: record(source.input_for(sid), PolicyAdjustedScoreInput)
            for sid in saved[3]}
        publication, retention = [True], saved[5]
        index = {}
        for sid, row in original_rows.items():
            child = mint(PolicyAdjustedScoreInput, dict(row[1]), publication, retention)
            prepared_gates[id(child)] = gate
            prepared_origins[id(child)] = source.input_for(sid)
            index[sid] = child
        result = mint(PolicyAdjustedScoreInputBatch, decode(saved[2]), publication, retention,
            attributes={"inputs": tuple(index.values())}, index=MappingProxyType(index))
        prepared_gates[id(result)] = gate
        prepared_origins[id(result)] = source
        source_bytes = verify_sources(retention[1])
        expected_purpose, scoring_registry, policy_registry = retention[4:7]
        valuation_adapter_registry, registry_bytes, root_hash = retention[7:10]
        feature, _, _, verifier, _, _, _ = dependencies(retention[0])
        _, current_registry_bytes = registry_snapshot(
            feature,
            verifier,
            root_hash,
            scoring_registry,
            policy_registry,
            valuation_adapter_registry,
            expected_purpose=expected_purpose,
        )
        if current_registry_bytes != registry_bytes:
            raise ValueError("final input registry bytes changed before preparation")
        checkpoint = retention[3][0]
        checkpoint.recheck()

        def recheck(connection=None):
            record(source, PolicyAdjustedScoreInputBatch)
            feature, _, _, verifier, _, _, _ = dependencies(retention[0])
            if verify_sources(retention[1]) != source_bytes:
                raise ValueError("final input dependencies changed before commit")
            _, current_registry_bytes = registry_snapshot(
                feature,
                verifier,
                root_hash,
                scoring_registry,
                policy_registry,
                valuation_adapter_registry,
                expected_purpose=expected_purpose,
            )
            if current_registry_bytes != registry_bytes:
                raise ValueError("final input registry bytes changed before commit")
            for proof in retention[2]:
                proof.require_verified()
            checkpoint.recheck(connection)

        return result, MappingProxyType(index), recheck, checkpoint.hold

    own_members = tuple((cls, tuple(vars(cls).items())) for cls in
        (Proof, PolicyAdjustedScoreInput, PolicyAdjustedScoreInputBatch, FormalFinalScoreInputRepository))
    return FormalFinalScoreInputRepository, PolicyAdjustedScoreInputBatch, PolicyAdjustedScoreInput, prepare


FormalFinalScoreInputRepository, PolicyAdjustedScoreInputBatch, PolicyAdjustedScoreInput, _prepare_final_inputs = _install_final_inputs()
del _install_final_inputs

__all__ = ["FormalFinalScoreInputRepository", "PolicyAdjustedScoreInputBatch", "PolicyAdjustedScoreInput"]
