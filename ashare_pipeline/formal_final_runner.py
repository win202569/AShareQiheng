"""Offline orchestration of the genuine Stage D proof and atomic writer chain.

The repositories own economic computation, proof preparation, and publication.
Diagnostics are detached observations and never confer release authority.
"""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from time import perf_counter
from types import MappingProxyType, MethodType
from pathlib import Path
from sys import _getframe, modules
from weakref import ref

from .formal_coverage_manifest import VerifiedCoverageManifest
from .formal_final_eligibility import build_formal_eligibility_batch
from .formal_final_repository import FormalFinalRunRepository, FormalFinalRunReceipt
from .formal_final_score_inputs import FormalFinalScoreInputRepository
from .formal_final_scoring import build_final_score_card_batch
from .formal_policy_registry import FormalPolicyRegistry
from .formal_pool import select_formal_pools
from .formal_registry_manifest import FormalRegistryBundleLoader
from .formal_scoring_registry import FormalScoringRegistry
from .formal_valuation_adapter_contract import FormalValuationAdapterRegistry
from .state_store import StateStore


def _canonical_freeze(value):
    """Close the fixed instant without rewriting historical frozen proof bytes."""
    canonical = "2026-08-31T07:00:00+00:00"
    if type(value) is not str:
        raise ValueError("runner frozen identity mismatch: as_of_utc")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("runner frozen identity mismatch: as_of_utc") from None
    if instant.tzinfo is None or instant.astimezone(timezone.utc) != datetime.fromisoformat(canonical):
        raise ValueError("runner frozen identity mismatch: as_of_utc")
    return canonical


def _require_d1_identity(expected, actual):
    fields = ("registry_manifest_hash", "frozen_input_hash", "universe_hash",
              "as_of_utc", "security_ids")
    mismatches = [field for field, closed, current in zip(fields, expected, actual)
                  if closed != current]
    if mismatches:
        raise ValueError("runner D1 identity mismatch: " + ", ".join(mismatches))


@dataclass(frozen=True)
class FormalFinalRunDiagnostics:
    mode: str
    status: str
    blockers: tuple
    official_ready: bool
    stage_seconds: MappingProxyType
    counts: MappingProxyType
    status_counts: MappingProxyType
    reason_counts: MappingProxyType
    decision_counts: MappingProxyType
    rebuild_plan: object = None


class _RunnerOperations:
    """A configured offline runner; callers cannot choose or bypass purpose.

    Incomplete evidence can produce a persisted ``blocked`` preview. A ready
    run is still only ``preview_ready``; V9 validation/publication is separate.
    A rebuild always constructs fresh proofs and an append-only run, even when
    the trusted diff permits reuse. Its plan describes the economic impact.
    """

    __slots__ = ()

    @property
    def last_diagnostics(self):
        return self._last_diagnostics

    def run_preview(self, *, frozen_input_hash, scoring_registry, policy_registry,
                    valuation_adapter_registry, coverage_manifest) -> FormalFinalRunReceipt:
        return self._run(mode="test_preview", frozen_input_hash=frozen_input_hash,
            scoring_registry=scoring_registry, policy_registry=policy_registry,
            valuation_adapter_registry=valuation_adapter_registry, coverage_manifest=coverage_manifest)

    def run_official_candidate(self, *, frozen_input_hash, scoring_registry, policy_registry,
                               valuation_adapter_registry, coverage_manifest) -> FormalFinalRunReceipt:
        return self._run(mode="official_candidate", frozen_input_hash=frozen_input_hash,
            scoring_registry=scoring_registry, policy_registry=policy_registry,
            valuation_adapter_registry=valuation_adapter_registry, coverage_manifest=coverage_manifest)

    def rebuild_affected(self, *, prior_run_id, prior_input_manifest_hash,
                         frozen_input_hash, scoring_registry, policy_registry,
                         valuation_adapter_registry, coverage_manifest,
                         mode="test_preview") -> FormalFinalRunReceipt:
        return self._run(mode=mode, frozen_input_hash=frozen_input_hash,
            scoring_registry=scoring_registry, policy_registry=policy_registry,
            valuation_adapter_registry=valuation_adapter_registry, coverage_manifest=coverage_manifest,
            prior=(prior_run_id, prior_input_manifest_hash))

    def _close_identity(self, *, mode, frozen_input_hash, scoring_registry,
                        policy_registry, valuation_adapter_registry, coverage_manifest):
        if type(mode) is not str or mode not in ("test_preview", "official_candidate"):
            raise ValueError("runner mode must be exact test_preview or official_candidate")
        expected_purpose = "test" if mode == "test_preview" else "official"
        if (type(frozen_input_hash) is not str or not frozen_input_hash
                or type(coverage_manifest) is not VerifiedCoverageManifest
                or type(scoring_registry) is not FormalScoringRegistry
                or type(policy_registry) is not FormalPolicyRegistry
                or type(valuation_adapter_registry) is not FormalValuationAdapterRegistry):
            raise ValueError("runner requires genuine exact frozen, registry and coverage inputs")
        coverage_manifest.require_verified()
        frozen = self._store.get_verified_formal_frozen_universe(frozen_input_hash)
        if frozen is None or frozen.frozen_input_hash != frozen_input_hash:
            raise ValueError("runner exact frozen universe is absent")
        freeze_at_utc = _canonical_freeze(frozen.as_of_utc)
        bundle = self._loader.load(frozen.registry_manifest_hash)
        if bundle.manifest.schema_version != "formal-registry-manifest-v2" or len(bundle.roles) != 10:
            raise ValueError("runner requires the complete ten-role v2 registry root")
        bundle.require_authenticated(expected_purpose=expected_purpose)
        scoring_registry.require_authenticated(bundle, expected_purpose=expected_purpose)
        policy_registry.require_verified()
        valuation_adapter_registry.require_current_bundle(bundle, expected_purpose=expected_purpose)
        if policy_registry.registry_manifest_hash != frozen.registry_manifest_hash:
            raise ValueError("runner policy registry belongs to another root")
        ids = tuple(sorted(member.security_id for member in frozen.members))
        if len(ids) != len(set(ids)):
            raise ValueError("runner frozen universe has duplicate members")
        wire = coverage_manifest.to_dict()
        if (wire["freeze_at_utc"] != freeze_at_utc
                or {row["security_id"] for row in wire["rows"]} != set(ids)
                or any(row["frozen_input_hash"] != frozen_input_hash
                       or row["exchange"] != row["security_id"][:2] for row in wire["rows"])):
            raise ValueError("runner coverage does not match the exact frozen members")
        if wire.get("authenticated_context") and (
                wire["registry_manifest_hash"] != frozen.registry_manifest_hash
                or wire["frozen_input_hash"] != frozen_input_hash
                or wire["universe_records_hash"] != frozen.universe_hash
                or wire["member_count"] != len(ids)):
            raise ValueError("runner coverage root or frozen universe identity mismatch")
        if mode == "official_candidate":
            bundle.require_official()
            coverage_manifest.require_official_ready()
            if {member.exchange for member in frozen.members} != {"SH", "SZ", "BJ"}:
                raise ValueError("official candidate requires complete SH/SZ/BJ frozen coverage")
        elif not coverage_manifest.blockers:
            coverage_manifest.require_preview_ready()
        return (frozen.registry_manifest_hash, frozen_input_hash, frozen.universe_hash,
                freeze_at_utc, ids), expected_purpose

    def _run(self, *, mode, frozen_input_hash, scoring_registry, policy_registry,
             valuation_adapter_registry, coverage_manifest, prior=None):
        # A failed attempt cannot expose diagnostics for an earlier successful run.
        self._last_diagnostics = None
        arguments = dict(mode=mode, frozen_input_hash=frozen_input_hash,
            scoring_registry=scoring_registry, policy_registry=policy_registry,
            valuation_adapter_registry=valuation_adapter_registry, coverage_manifest=coverage_manifest)
        timings = {}
        calls = Counter()
        def timed(stage, operation):
            started = perf_counter()
            calls[stage] += 1
            result = operation()
            timings[stage] = perf_counter() - started
            return result
        identity, purpose = timed("identity", lambda: self._close_identity(**arguments))
        inputs = timed("d1", lambda: self._inputs.build_batch(frozen_input_hash,
            scoring_registry=scoring_registry, policy_registry=policy_registry,
            valuation_adapter_registry=valuation_adapter_registry, expected_purpose=purpose))
        inputs.require_verified()
        _require_d1_identity(identity, (inputs.registry_manifest_hash, inputs.frozen_input_hash,
            inputs.universe_hash, inputs.as_of_utc, tuple(inputs.security_ids)))
        plan = None
        if prior is not None:
            plan = timed("trusted_diff", lambda: self._runs.plan_rebuild(
                prior_run_id=prior[0], prior_input_manifest_hash=prior[1], mode=mode,
                input_batch=inputs, coverage_manifest=coverage_manifest))
        scores = timed("d2", lambda: build_final_score_card_batch(inputs))
        def d3():
            eligibility = build_formal_eligibility_batch(inputs, scores)
            return eligibility, select_formal_pools(eligibility)
        eligibility, pools = timed("d3", d3)
        if mode == "official_candidate" and any(
                row["state"] in ("pending_evidence", "out_of_scope")
                for row in eligibility.to_dict()["eligibilities"]):
            raise ValueError("official candidate requires complete ordinary-A scoring evidence")
        def final_recheck():
            calls["identity"] += 1
            if self._close_identity(**arguments)[0] != identity:
                raise ValueError("runner root or frozen identity changed before commit")
            for batch in (inputs, scores, eligibility, pools):
                batch.require_verified()
                calls["final_batch_rechecks"] += 1
        timed("final_recheck", final_recheck)
        # Read live proofs for diagnostics before entering the durable boundary.
        # No fallible proof access may turn a committed result into a failed run.
        diagnostics = self._diagnostics(mode, inputs, scores, eligibility, pools,
            coverage_manifest, timings, calls, plan)
        # The writer alone prepares and atomically publishes D1/D2/D3 children.
        receipt = timed("commit", lambda: self._runs.commit_complete_run(mode=mode,
            coverage_manifest=coverage_manifest, input_batch=inputs, score_batch=scores,
            eligibility_batch=eligibility, pool_batch=pools))
        self._last_diagnostics = replace(diagnostics, status=receipt.status,
            official_ready=mode == "official_candidate" and receipt.status == "preview_ready")
        return receipt

    @staticmethod
    def _diagnostics(mode, input_batch, score_batch, eligibility_batch, pool_batch,
                     coverage, timings, calls, plan):
        inputs = input_batch.to_dict()
        scores = score_batch.to_dict()
        rows = eligibility_batch.to_dict()["eligibilities"]
        pools = pool_batch.to_dict()
        blockers = set(coverage.blockers)
        if mode == "test_preview":
            blockers.add("test_registry_not_official")
        if any(row["state"] == "pending_evidence" for row in rows):
            blockers.add("pending_evidence")
        blockers.add("v9_release_not_implemented")
        cohorts = set()
        metrics = set()
        for row in inputs["inputs"]:
            for metric, slot in row["slots"].items():
                metrics.add(metric)
                context = slot.get("valuation_context") or (slot.get("metric_score") or {}).get("peer_context")
                if context and context.get("cohort_hash"):
                    cohorts.add(context["cohort_hash"])
        decisions = Counter(row["decision"] for row in pools["decisions"])
        counts = dict(members=len(inputs["security_ids"]), metrics=len(metrics),
            retained_cohorts=len(cohorts),
            metric_slots=sum(len(row["slots"]) for row in inputs["inputs"]),
            scorecards=len(scores["cards"]), eligibilities=len(rows),
            hard_veto=sum(row["hard_veto"] for row in rows),
            strong_qualified=sum(row["strong_qualified"] for row in rows),
            wait_qualified=sum(row["wait_qualified"] for row in rows),
            strong=pools["counts"]["strong"], wait=pools["counts"]["wait"],
            d1_builds=calls["d1"], d2_builds=calls["d2"], d3_builds=calls["d3"],
            pool_orderings=len({row["pool"] for row in pools["decisions"]}),
            identity_rechecks=calls["identity"], final_batch_rechecks=calls["final_batch_rechecks"],
            trusted_diffs=calls["trusted_diff"],
            industry_cap_skips=decisions["industry_cap_reached"],
            capacity_skips=decisions["overall_capacity_reached"],
            rebuilt_members=len(inputs["security_ids"]))
        return FormalFinalRunDiagnostics(mode=mode, status="building",
            blockers=tuple(sorted(blockers)),
            official_ready=False,
            stage_seconds=MappingProxyType(timings), counts=MappingProxyType(counts),
            status_counts=MappingProxyType(dict(Counter(row["state"] for row in rows))),
            reason_counts=MappingProxyType(dict(Counter(reason for row in rows for reason in row["reason_codes"]))),
            decision_counts=MappingProxyType(dict(decisions)),
            rebuild_plan=plan)


def _install_runner_authority():
    """Seal configuration without exporting a proof mint or validity cache."""
    configurations = {}
    owner = globals()
    operations = _RunnerOperations
    frame_reader, reference = _getframe, ref
    field_indexes = {"_store": 0, "_inputs": 1, "_runs": 2, "_loader": 3}
    bindings = tuple((name, owner[name]) for name in (
        "StateStore", "FormalFinalScoreInputRepository", "FormalFinalRunRepository",
        "FormalRegistryBundleLoader", "VerifiedCoverageManifest", "FormalScoringRegistry",
        "FormalPolicyRegistry", "FormalValuationAdapterRegistry", "FormalFinalRunReceipt",
        "FormalFinalRunDiagnostics", "build_final_score_card_batch",
        "build_formal_eligibility_batch", "select_formal_pools", "_RunnerOperations",
        "perf_counter", "replace", "_getframe", "modules", "ref",
        "Path", "Counter", "MappingProxyType", "MethodType", "datetime", "timezone",
        "_canonical_freeze", "_require_d1_identity"))
    origins = tuple((value.__module__, modules[value.__module__], name, value)
        for name, value in bindings if hasattr(value, "__module__")
        and value.__module__.startswith("ashare_pipeline.")
        and getattr(modules.get(value.__module__), name, None) is value)
    methods = tuple((cls, name, getattr(cls, name)) for cls, names in (
        (StateStore, ("get_verified_formal_frozen_universe",)),
        (FormalFinalScoreInputRepository, ("__init__", "build_batch")),
        (FormalFinalRunRepository, ("__init__", "commit_complete_run", "plan_rebuild")),
        (FormalRegistryBundleLoader, ("__init__", "load")),
        (VerifiedCoverageManifest, (
            "_data", "require_verified", "require_preview_ready", "require_official_ready",
            "_recheck_official_provenance", "_recheck_official_workspace",
            "canonical_bytes", "to_dict"))) for name in names)
    code_bindings = tuple((value, value.__code__) for _, value in bindings
        if hasattr(value, "__code__")) + tuple((method, method.__code__) for _, _, method in methods)

    def interfaces():
        if (owner.get("FormalFinalScoreRunner") is not runner_type
                or any(owner.get(name) is not value for name, value in bindings)
                or any(modules.get(module_name) is not producer
                       or getattr(producer, name, None) is not value
                       for module_name, producer, name, value in origins)
                or any(getattr(cls, name) is not method for cls, name, method in methods)
                or any(function.__code__ is not code for function, code in code_bindings)
                or any(tuple(vars(cls)) != tuple(name for name, _ in members)
                       or any(vars(cls).get(name) is not value for name, value in members)
                       for cls, members in own_members)
                or any(diagnostic_fields.get(name) is not field
                       or any(getattr(field, attr) is not value for attr, value in attributes)
                       for name, field, attributes in field_members)
                or tuple(diagnostic_fields) != tuple(name for name, _, _ in field_members)):
            raise ValueError("runner authority entry point changed")

    def record(instance):
        interfaces()
        saved = configurations.get(id(instance))
        if type(instance) is not runner_type or saved is None or saved[0]() is not instance:
            raise ValueError("runner configuration is unregistered, copied or forged")
        store, inputs, runs, loader = saved[1]
        path, verifier, code_version, contract_version = saved[2]
        if (type(store) is not StateStore or type(inputs) is not FormalFinalScoreInputRepository
                or type(runs) is not FormalFinalRunRepository
                or type(loader) is not FormalRegistryBundleLoader
                or runs._store is not store or loader._repository is not store
                or loader._verifier is not verifier
                or Path(store.db_path).resolve() != path or runs._path != path
                or runs._code_version != code_version or runs._contract_version != contract_version):
            raise ValueError("runner configuration ownership changed")
        for instance, name, expected in (
                (store, "get_verified_formal_frozen_universe", methods[0][2]),
                (inputs, "build_batch", FormalFinalScoreInputRepository.build_batch),
                (runs, "commit_complete_run", FormalFinalRunRepository.commit_complete_run),
                (runs, "plan_rebuild", FormalFinalRunRepository.plan_rebuild),
                (loader, "load", FormalRegistryBundleLoader.load)):
            current = getattr(instance, name)
            if (type(current) is not MethodType
                    or getattr(current, "__self__", None) is not instance
                    or getattr(current, "__func__", None) is not expected):
                raise ValueError("runner configuration entry point changed")
        return saved

    class SealedMeta(type):
        def __setattr__(cls, name, value):
            raise TypeError("runner authority methods are immutable")

        def __delattr__(cls, name):
            raise TypeError("runner authority methods are immutable")

    class FormalFinalScoreRunner(operations, metaclass=SealedMeta):
        __slots__ = ("__weakref__",)
        __doc__ = operations.__doc__

        def __init__(self, state_store, *, input_repository, run_repository,
                     registry_signature_verifier):
            interfaces()
            if (type(self) is not runner_type or id(self) in configurations
                    or type(state_store) is not StateStore
                    or type(input_repository) is not FormalFinalScoreInputRepository
                    or type(run_repository) is not FormalFinalRunRepository
                    or run_repository._store is not state_store):
                raise ValueError("runner requires exact configured Stage D repositories")
            loader = FormalRegistryBundleLoader(state_store, registry_signature_verifier)
            key = id(self)
            configurations[key] = (reference(self, lambda _: configurations.pop(key, None)),
                (state_store, input_repository, run_repository, loader),
                (Path(state_store.db_path).resolve(), registry_signature_verifier,
                 run_repository._code_version, run_repository._contract_version), [None])
            record(self)

        def __init_subclass__(cls, **kwargs):
            raise TypeError("runner authority cannot be inherited")

        def __getattribute__(self, name):
            record(self)
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            saved = record(self)
            if name in field_indexes:
                return saved[1][field_indexes[name]]
            raise AttributeError(name)

        def __setattr__(self, name, value):
            saved = record(self)
            caller = frame_reader(1)
            if (name != "_last_diagnostics" or caller.f_code is not run_code
                    or caller.f_locals.get("self") is not self):
                raise TypeError("runner configuration and diagnostics are read-only")
            saved[3][0] = value

        def __delattr__(self, name):
            raise TypeError("runner configuration is immutable")

        @property
        def _last_diagnostics(self):
            return record(self)[3][0]

        def __copy__(self):
            raise TypeError("runner cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("runner cannot be copied")

        def __reduce_ex__(self, protocol):
            raise TypeError("runner cannot be pickled")

    runner_type = FormalFinalScoreRunner
    run_code = operations._run.__code__
    own_members = tuple((cls, tuple(vars(cls).items()))
        for cls in (operations, runner_type, FormalFinalRunDiagnostics))
    diagnostic_fields = FormalFinalRunDiagnostics.__dataclass_fields__
    field_members = tuple((name, field,
        tuple((attr, getattr(field, attr)) for attr in type(field).__slots__))
        for name, field in diagnostic_fields.items())
    functions = []
    for cls, _ in own_members:
        for value in vars(cls).values():
            if isinstance(value, (staticmethod, classmethod)):
                functions.append(value.__func__)
            elif isinstance(value, property):
                functions.extend(function for function in (value.fget, value.fset, value.fdel)
                    if function is not None)
            elif hasattr(value, "__code__"):
                functions.append(value)
    code_bindings += tuple((function, function.__code__) for function in functions)
    return runner_type


FormalFinalScoreRunner = _install_runner_authority()
del _install_runner_authority

__all__ = ["FormalFinalScoreRunner", "FormalFinalRunDiagnostics"]
