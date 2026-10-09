"""Private read-only refresh of release inputs; not publication authority.

This component owns configuration and accepts only a run selector. Existing
repositories/auditor own authentication. Returned history remains detached
data; refreshed registry/coverage proofs are not a release capability.
"""
import inspect
import json
from pathlib import Path
from types import MethodType
from weakref import ref

from . import formal_final_repository as history_module
from .formal_final_repository import FormalFinalRunRepository, _register_publication_owner
from .formal_final_score_inputs import FormalFinalScoreInputRepository, _prepare_final_inputs
from .formal_feature_repository import FormalFeatureRepository
from .formal_registry_manifest import FormalRegistryBundleLoader
from .formal_scoring_registry import RegistryApproval, load_formal_registry
from .formal_policy_registry import load_formal_policy_registry
from .formal_valuation_adapter_contract import load_formal_valuation_adapter_registry
from .formal_coverage_manifest import FormalCoverageAuditor
from .formal_release_types import canonical_release_bytes
from .formal_release_validation import _check_candidate_binding
from .state_store import StateStore


def _install_inputs():
    configurations = {}
    owner = globals()
    input_dependencies = inspect.getclosurevars(_prepare_final_inputs).nonlocals['dependencies']
    registered_runs = inspect.getclosurevars(_register_publication_owner).nonlocals['repositories']
    registry = FormalFeatureRepository._registry
    read_run = FormalFinalRunRepository.get_run
    get_frozen = StateStore.get_verified_formal_frozen_universe
    scoring_load, policy_load, valuation_load = (
        load_formal_registry, load_formal_policy_registry, load_formal_valuation_adapter_registry)
    audit = FormalCoverageAuditor.audit
    from .formal_policy_repository import FormalPolicyRepository
    policy_build = FormalPolicyRepository.build_batch
    check, encode, decode, reference = _check_candidate_binding, canonical_release_bytes, json.loads, ref
    methods = tuple((cls, name, getattr(cls, name)) for cls, names in (
        (FormalFinalRunRepository, ('__init__', 'get_run', '_read_run')),
        (StateStore, ('__init__', '_connect', '_transaction', 'get_verified_formal_frozen_universe')),
        (FormalFeatureRepository, ('_registry',)),
        (FormalCoverageAuditor, ('__init__', 'audit', '_audit_payload')),
        (FormalRegistryBundleLoader, ('__init__', 'load')),
        (FormalPolicyRepository, ('build_batch',)),
    ) for name in names)
    bindings = tuple((name, value) for name, value in owner.items()
                     if callable(value) and name != '_install_inputs')
    history_bindings = tuple((name, value) for name, value in vars(history_module).items()
                             if callable(value))
    history_constants = tuple((name, vars(history_module)[name]) for name in
                              ('ARTIFACT_KINDS', '_TABLES', '_BATCH_TYPES'))
    functions = (input_dependencies, scoring_load, policy_load, valuation_load, check, encode, decode)
    codes = tuple((function, function.__code__) for function in functions if hasattr(function, '__code__'))
    codes += tuple((method, method.__code__) for _, _, method in methods)
    history_codes = tuple((value, value.__code__) for _, value in history_bindings
                          if hasattr(value, '__code__'))

    def interfaces():
        if (any(owner.get(name) is not value for name, value in bindings)
                or any(vars(history_module).get(name) is not value for name, value in history_bindings)
                or any(vars(history_module).get(name) is not value for name, value in history_constants)
                or owner.get('_ReleaseInputRefresh') is not refresh_type
                or owner.get('_reload_official_registry_set') is not reload
                or any(getattr(cls, name) is not method for cls, name, method in methods)
                or any(function.__code__ is not code for function, code in codes + history_codes)
                or tuple(vars(refresh_type).items()) != own_members
                or any(function.__code__ is not code for function, code in own_codes)):
            raise ValueError('release input authority entry point changed')

    def bound(instance, name, expected):
        actual = getattr(instance, name)
        if type(actual) is not MethodType or actual.__self__ is not instance or actual.__func__ is not expected:
            raise ValueError('release input configured entry point changed')

    def verifier_binding(verifier):
        method = getattr(verifier, 'verify', None)
        if type(method) is not MethodType or method.__self__ is not verifier:
            raise ValueError('release input verifier requires a fixed owned verify method')
        return verifier, method.__func__, getattr(method.__func__, '__code__', None)

    def reload(feature, root):
        interfaces()
        if type(feature) is not FormalFeatureRepository:
            raise ValueError('release registry refresh requires the genuine feature repository')
        bound(feature, '_registry', registry)
        bundle, vocabulary = registry(feature, root, expected_purpose='official')
        bundle.require_official()
        if bundle.manifest.schema_version != 'formal-registry-manifest-v2' or len(bundle.roles) != 10:
            raise ValueError('release requires the ten-role official registry')
        scoring = scoring_load(bundle, RegistryApproval('official',
            bundle.manifest.scoring_registry_hash, bundle.manifest.approval_id), feature_registry=vocabulary)
        policy = policy_load(bundle, scoring_registry=scoring,
                             feature_registry=vocabulary, expected_purpose='official')
        valuation = valuation_load(bundle, scoring_registry=scoring,
                                   policy_registry=policy, expected_purpose='official')
        interfaces()
        bundle.require_official()
        scoring.require_authenticated(bundle, expected_purpose='official')
        policy.require_verified()
        valuation.require_current_bundle(bundle, expected_purpose='official')
        return bundle, scoring, policy, valuation

    def record(instance):
        interfaces()
        saved = configurations.get(id(instance))
        if type(instance) is not refresh_type or saved is None or saved[0]() is not instance:
            raise ValueError('release input configuration is unregistered, copied or forged')
        store, inputs, runs, verifier, contract_verifier, path, code, contract, raw_contract, status = saved[1]
        run_owner = registered_runs.get(id(runs))
        if (run_owner is None or run_owner() is not runs or runs._store is not store
                or Path(store.db_path).resolve() != path or runs._path != path
                or runs._code_version != code or runs._contract_version != contract):
            raise ValueError('release input repository constructor/ownership changed')
        feature, context, _, current_verifier, _, _, _ = input_dependencies(inputs)
        if feature._store is not store or current_verifier is not verifier or context._state_store is not store:
            raise ValueError('release input repository ownership differs')
        bound(runs, 'get_run', read_run)
        bound(runs, '_read_run', FormalFinalRunRepository._read_run)
        bound(store, '_connect', StateStore._connect)
        bound(store, '_transaction', StateStore._transaction)
        bound(store, 'get_verified_formal_frozen_universe', get_frozen)
        for current, function, code_object in saved[2]:
            if (verifier_binding(current)[1:] != (function, code_object)
                    or getattr(function, '__code__', None) is not code_object):
                raise ValueError('release input configured verifier changed')
        return saved[1], feature, context

    class Sealed(type):
        def __setattr__(cls, name, value):
            raise TypeError('release input configuration methods are immutable')

        def __delattr__(cls, name):
            raise TypeError('release input configuration methods are immutable')

    class _ReleaseInputRefresh(metaclass=Sealed):
        __slots__ = ('__weakref__',)

        def __init_subclass__(cls, **kwargs):
            raise TypeError('release input configuration cannot be inherited')

        def __getattribute__(self, name):
            record(self)
            return object.__getattribute__(self, name)

        def __init__(self, *, state_store, input_repository, run_repository,
                     registry_signature_verifier, coverage_contract,
                     coverage_contract_verifier, status_path):
            interfaces()
            if type(self) is not refresh_type or id(self) in configurations:
                raise ValueError('release input configuration requires exact single initialization')
            if (type(state_store) is not StateStore or type(input_repository) is not FormalFinalScoreInputRepository
                    or type(run_repository) is not FormalFinalRunRepository):
                raise ValueError('release input configuration requires genuine repository ownership')
            if type(coverage_contract) is not dict or set(coverage_contract) != {'canonical_json', 'signature', 'key_id'}:
                raise ValueError('release coverage configuration has unknown controls or missing fields')
            raw = coverage_contract['canonical_json']
            if (type(raw) is not bytes or any(type(coverage_contract[key]) is not str or not coverage_contract[key]
                                            for key in ('signature', 'key_id'))):
                raise ValueError('release coverage configuration is not detached bytes/signature data')
            try:
                wire = decode(raw)
                if type(wire) is not dict or encode(wire) != raw:
                    raise ValueError('noncanonical contract')
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                raise ValueError('release coverage contract must be canonical JSON') from exc
            detached = (raw, coverage_contract['signature'], coverage_contract['key_id'])
            verifiers = tuple(verifier_binding(item) for item in
                              (registry_signature_verifier, coverage_contract_verifier))
            key = id(self)
            configurations[key] = (reference(self, lambda _: configurations.pop(key, None)),
                (state_store, input_repository, run_repository, registry_signature_verifier,
                 coverage_contract_verifier, Path(state_store.db_path).resolve(),
                 run_repository._code_version, run_repository._contract_version, detached,
                 Path(status_path).resolve()), verifiers)
            try:
                record(self)
            except BaseException:
                configurations.pop(key, None)
                raise

        def refresh(self, run_id):
            config, feature, context = record(self)
            if type(run_id) is not str or not run_id or run_id.strip() != run_id:
                raise ValueError('release input refresh accepts only an exact nonempty run id')
            store, inputs, runs, verifier, contract_verifier, _, code, contract, detached, status = config
            snapshot = read_run(runs, run_id)
            if snapshot is None:
                raise ValueError('release candidate was not found')
            if snapshot.mode != 'official_candidate' or snapshot.status != 'preview_ready':
                raise ValueError('release candidate must be official preview_ready history')
            frozen = get_frozen(store, snapshot.frozen_input_hash)
            if frozen is None:
                raise ValueError('release candidate frozen input was not found')
            ids = tuple(sorted(member.security_id for member in frozen.members))
            check(snapshot, run_id=run_id, code_version=code, contract_version=contract,
                  registry_manifest_hash=frozen.registry_manifest_hash,
                  frozen_input_hash=frozen.frozen_input_hash, universe_hash=frozen.universe_hash,
                  security_ids=ids)
            bundle, scoring, policy, valuation = reload(feature, frozen.registry_manifest_hash)
            raw, signature, key_id = detached
            wire = decode(raw)
            policy_repository = input_dependencies(inputs)[5]
            policy_batch = None
            if 'formal_policy_repository' in wire.get('domain_owners', {}).values():
                policy_batch = policy_build(policy_repository, frozen.frozen_input_hash,
                    scoring_registry=scoring, policy_registry=policy, expected_purpose='official')
            coverage = audit(FormalCoverageAuditor(), wire['requirements'],
                production_contract=dict(canonical_json=raw, signature=signature, key_id=key_id),
                contract_verifier=contract_verifier, registry_bundle=bundle,
                registry_loader=FormalRegistryBundleLoader(store, verifier),
                snapshot_repository=context._snapshots, context_repository=context,
                feature_repository=feature, policy_repository=policy_repository, policy_batch=policy_batch,
                frozen_universe=frozen, workspace_root=Path(__file__).resolve().parent.parent,
                db_path=store.db_path, status_path=status)
            coverage.require_official_ready()
            if coverage.to_dict().get('workspace_revision') != code:
                raise ValueError('candidate_changed: current code requires a new Stage D candidate')
            record(self)
            current = read_run(runs, run_id)
            if current is None or current.header != snapshot.header or current.artifacts != snapshot.artifacts:
                raise ValueError('candidate_changed: V8 history changed during release input refresh')
            coverage.require_official_ready()
            return snapshot, scoring, policy, valuation, coverage

        def __copy__(self):
            raise TypeError('release input configuration cannot be copied')

        def __deepcopy__(self, memo):
            raise TypeError('release input configuration cannot be copied')

        def __reduce_ex__(self, protocol):
            raise TypeError('release input configuration cannot be reconstructed')

    refresh_type = _ReleaseInputRefresh
    own_members = tuple(vars(refresh_type).items())
    own_codes = tuple((function, function.__code__) for _, function in own_members
                      if hasattr(function, '__code__'))
    return refresh_type, reload


_ReleaseInputRefresh, _reload_official_registry_set = _install_inputs()
del _install_inputs

__all__ = []
