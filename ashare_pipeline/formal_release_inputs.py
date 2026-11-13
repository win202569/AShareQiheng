"""Configured input refresh, validation and signed audit; no publication authority.

This component owns configuration and accepts only a run selector. Existing
repositories/auditor own authentication. Returned history remains detached
data; refreshed registry/coverage proofs are not a release capability.
"""
import inspect
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from hashlib import sha256
from contextlib import closing, contextmanager
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
from .formal_release_types import (canonical_release_bytes, canonical_validation_bytes,
    ReleaseValidationPayload, ValidationGate, REQUIRED_RELEASE_GATE_NAMES,
    signature_message, verify_release_signature, VALIDATION_DOMAIN)
from . import formal_release_types as value_module
from . import formal_release_rendering as render_module
from . import formal_release_recovery as recovery_module
from . import formal_release_tree as tree_module
from .formal_release_validation import (
    _check_candidate_binding, _hold_official_candidate, _hold_official_evidence)
from . import formal_release_jobs as jobs_module
from .formal_release_jobs import _read_job_quiescence
from .state_store import StateStore
from . import state_store as state_module


def _install_inputs():
    configurations = {}
    schema_members = tuple((name, vars(StateStore)[name]) for name in
        ('_assert_v9_objects', '_assert_schema_ddl', '_normalized_ddl'))
    schema_codes = tuple((descriptor.__func__, descriptor.__func__.__code__) for _, descriptor in schema_members)
    assert_objects = vars(StateStore)['_assert_v9_objects'].__func__
    assert_ddl = vars(StateStore)['_assert_schema_ddl'].__func__
    schema_definitions = tuple((name, value, tuple(value.items())) for name, value in
        (('_V9_TABLE_DDL', state_module._V9_TABLE_DDL), ('_V9_INDEX_DDL', state_module._V9_INDEX_DDL)))
    migration_ddl = state_module._MIGRATION_TABLE_DDL
    render = render_module._render_release_package
    gate_names = REQUIRED_RELEASE_GATE_NAMES
    owner = globals()
    input_dependencies = inspect.getclosurevars(_prepare_final_inputs).nonlocals['dependencies']
    registered_runs = inspect.getclosurevars(_register_publication_owner).nonlocals['repositories']
    registry = FormalFeatureRepository._registry
    replay_hold, read_jobs, connect = _hold_official_evidence, _read_job_quiescence, StateStore._connect
    read_run = FormalFinalRunRepository.get_run
    get_frozen = StateStore.get_verified_formal_frozen_universe
    scoring_load, policy_load, valuation_load = (
        load_formal_registry, load_formal_policy_registry, load_formal_valuation_adapter_registry)
    audit = FormalCoverageAuditor.audit
    from .formal_policy_repository import FormalPolicyRepository
    policy_build = FormalPolicyRepository.build_batch
    check, encode, decode, reference = _check_candidate_binding, canonical_release_bytes, json.loads, ref
    methods = tuple((cls, name, getattr(cls, name)) for cls, names in (
        (ReleaseValidationPayload, ('__init__', '__post_init__')),
        (ValidationGate, ('__init__', '__post_init__')),
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
    job_bindings = tuple((name, value) for name, value in vars(jobs_module).items() if callable(value))
    render_bindings = tuple((module,name,value) for module in (render_module,value_module,recovery_module,tree_module)
        for name,value in vars(module).items() if callable(value) or name.isupper())
    functions = (render, canonical_validation_bytes, replay_hold, _hold_official_candidate, read_jobs, input_dependencies, scoring_load, policy_load, valuation_load, check, encode, decode)
    codes = tuple((function, function.__code__) for function in functions if hasattr(function, '__code__'))
    codes += tuple((method, method.__code__) for _, _, method in methods)
    codes += tuple((value, value.__code__) for _, value in job_bindings if hasattr(value, "__code__"))
    codes += tuple((value,value.__code__) for _,_,value in render_bindings if hasattr(value,'__code__'))
    history_codes = tuple((value, value.__code__) for _, value in history_bindings
                          if hasattr(value, '__code__'))
    transaction_wrapper = StateStore._transaction
    transaction_body = inspect.getclosurevars(transaction_wrapper).nonlocals['func']
    transaction_code = transaction_body.__code__
    transaction_cell = transaction_wrapper.__closure__[
        transaction_wrapper.__code__.co_freevars.index('func')]

    def interfaces():
        if (any(vars(StateStore).get(name) is not descriptor for name, descriptor in schema_members)
                or any(function.__code__ is not code for function, code in schema_codes)
                or any(getattr(state_module, name) is not original or tuple(original.items()) != values
                       for name, original, values in schema_definitions)
                or state_module._MIGRATION_TABLE_DDL != migration_ddl
                or transaction_cell.cell_contents is not transaction_body
                or transaction_body.__code__ is not transaction_code
                or any(cell.cell_contents is not body or body.__code__ is not code
                       for cell, body, code in wrapped_bodies)
                or any(vars(module).get(name) is not value for module,name,value in render_bindings)
                or any(vars(jobs_module).get(name) is not value for name, value in job_bindings)
                or any(owner.get(name) is not value for name, value in bindings)
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
        signing = saved[3]
        if signing is not None:
            for instance, name, function, code_object in signing[1]:
                bound(instance, name, function)
                if getattr(function, '__code__', None) is not code_object:
                    raise ValueError('release audit signing implementation changed')
        return saved[1], feature, context

    def job_snapshot(instance):
        config, _, _ = record(instance)
        with closing(connect(config[0])) as connection:
            connection.execute('BEGIN')
            raw, blockers = read_jobs(connection)
        record(instance)
        if blockers:
            raise ValueError('job_quiescence: ' + '; '.join(blockers))
        return raw

    def schema_version(instance):
        config, _, _ = record(instance)
        with closing(connect(config[0])) as connection:
            connection.execute('BEGIN')
            versions = tuple(row[0] for row in connection.execute('SELECT version FROM schema_migration ORDER BY version'))
        record(instance)
        if versions != tuple(range(2,10)) or any(type(value) is not int for value in versions):
            raise ValueError('release validation requires complete schema version 9 ledger')
        return versions[-1]

    def audit_schema(connection):
        interfaces()
        try:
            assert_ddl(StateStore, connection, {'schema_migration':migration_ddl}, {}, 'release audit schema')
            versions = tuple(row[0] for row in connection.execute('SELECT version FROM schema_migration ORDER BY version'))
            if versions != tuple(range(2, 10)) or any(type(value) is not int for value in versions):
                raise ValueError('release audit schema requires complete version 9 ledger')
            assert_objects(StateStore, connection, applied=True)
            assert_ddl(StateStore, connection, dict(schema_definitions[0][2]), dict(schema_definitions[1][2]),
                       'release audit schema')
        except RuntimeError as exc:
            raise ValueError('release audit schema rejected: ' + str(exc)) from exc
        interfaces()

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
                     coverage_contract_verifier, status_path, release_signer=None,
                     release_signature_verifier=None, release_key_id=None, release_root=None):
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
            signing = None
            if any(value is not None for value in
                   (release_signer, release_signature_verifier, release_key_id)):
                if (release_signer is None or release_signature_verifier is None
                        or type(release_key_id) is not str or not release_key_id
                        or release_key_id.strip() != release_key_id):
                    raise ValueError('release audit requires complete explicit signing configuration')
                signing_methods = []
                for instance, name in ((release_signer, 'sign'), (release_signature_verifier, 'verify')):
                    method = getattr(instance, name, None)
                    if type(method) is not MethodType or method.__self__ is not instance:
                        raise ValueError('release audit signing configuration requires fixed owned methods')
                    signing_methods.append((instance, name, method.__func__, getattr(method.__func__, '__code__', None)))
                signing = (release_key_id, tuple(signing_methods))
            target_root = None
            if release_root is not None:
                target_root = Path(release_root)
                if not target_root.is_absolute() or target_root != target_root.resolve():
                    raise ValueError('release root must be an absolute canonical path without aliases')
            key = id(self)
            configurations[key] = (reference(self, lambda _: configurations.pop(key, None)),
                (state_store, input_repository, run_repository, registry_signature_verifier,
                 coverage_contract_verifier, Path(state_store.db_path).resolve(),
                 run_repository._code_version, run_repository._contract_version, detached,
                 Path(status_path).resolve()), verifiers, signing, target_root)
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

        @contextmanager
        def hold_evidence(self, run_id):
            """Configured evidence channel; detached computation and diagnostic bytes only.

            This is not the complete 12-gate validator or publication permission.
            Only a future trusted publisher can act under live pre-write checks.
            """
            config, _, _ = record(self)
            if type(run_id) is not str or not run_id or run_id.strip() != run_id:
                raise ValueError('release replay accepts only an exact nonempty run id')
            initial_jobs = job_snapshot(self)
            snapshot, scoring, policy, valuation, coverage = self.refresh(run_id)
            record(self)
            with replay_hold(snapshot, run_id=run_id, input_repository=config[1],
                    scoring_registry=scoring, policy_registry=policy,
                    valuation_adapter_registry=valuation, coverage_manifest=coverage,
                    contract_version=config[7]) as (raw, changed, replay_evidence):
                if changed:
                    raise ValueError('candidate_changed: replay differs: ' + ', '.join(changed))
                if job_snapshot(self) != initial_jobs:
                    raise ValueError('candidate_changed: job evidence changed during replay')
                replay_wire = decode(replay_evidence)
                coverage_hash = sha256(coverage.canonical_bytes()).hexdigest()
                if replay_wire['coverage_manifest_hash'] != coverage_hash:
                    raise ValueError('candidate_changed: replay coverage commitment differs')
                source_commitment = dict(schema='formal-release-configured-sources-v1',
                    replay_source_dependency_hash=replay_wire['source_dependency_hash'],
                    job_evidence_hash=sha256(initial_jobs).hexdigest())
                evidence = encode(dict(schema='formal-release-configured-evidence-v1',
                    candidate={key:snapshot.header[key] for key in ('run_id','code_version',
                        'contract_version','input_manifest_hash','result_hash','coverage_manifest_hash',
                        'registry_manifest_hash','frozen_input_hash','universe_hash')},
                    coverage_manifest_hash=coverage_hash,
                    source_dependency_hash=sha256(encode(source_commitment)).hexdigest(),
                    source_commitment=source_commitment, replay_evidence=replay_wire,
                    job_evidence=decode(initial_jobs)))
                try:
                    yield dict(raw), evidence
                finally:
                    record(self)
                    if job_snapshot(self) != initial_jobs:
                        raise ValueError('candidate_changed: job evidence changed during held replay')
                    current = read_run(config[2], run_id)
                    if current is None or current.header != snapshot.header or current.artifacts != snapshot.artifacts:
                        raise ValueError('candidate_changed: V8 history changed during held replay')
                    record(self)

        @contextmanager
        def hold_replay(self, run_id):
            """Compatibility view; returned computation/job bytes are not authority."""
            with self.hold_evidence(run_id) as (raw, evidence):
                yield raw, encode(decode(evidence)['job_evidence'])

        def validate(self, run_id):
            """Run all checks for an unsigned audit result; never return live authority.

            Only this configured path assembles successful diagnostics. A failure
            raises before a result is returned; no signing or persistence occurs.
            """
            version = schema_version(self)
            with self.hold_evidence(run_id) as (raw, evidence_bytes):
                record(self)
                evidence = decode(evidence_bytes)
                candidate = evidence['candidate']
                identity = {key:candidate[key] for key in ('contract_version',
                    'input_manifest_hash','result_hash','registry_manifest_hash',
                    'frozen_input_hash','universe_hash')}
                package = render(raw, candidate_identity=identity)
                record(self)
                if schema_version(self) != version:
                    raise ValueError('candidate_changed: release schema changed')
                manifest = decode(package['release_manifest.json'])
                sources = evidence['replay_evidence']['sources']
                batches = sources['computation']
                references = dict(
                    candidate_identity=(candidate['input_manifest_hash'],candidate['result_hash']),
                    official_registry=(sha256(encode(sources['registry'])).hexdigest(),),
                    workspace_identity=(sha256(encode(dict(code_version=candidate['code_version'],schema_version=version))).hexdigest(),
                                        evidence['coverage_manifest_hash']),
                    frozen_universe=(candidate['frozen_input_hash'],candidate['universe_hash']),
                    official_coverage=(evidence['coverage_manifest_hash'],),
                    source_identity_temporal=(evidence['source_dependency_hash'],),
                    replay_equivalence=tuple(batches[name] for name in sorted(batches)),
                    classification_complete=(batches['eligibility_batch'],),
                    score_formula=(batches['score_input_batch'],batches['scorecard_batch']),
                    pool_selection=(batches['pool_selection_batch'],),
                    job_quiescence=(evidence['source_commitment']['job_evidence_hash'],),
                    artifact_renderability=(sha256(package['release_manifest.json']).hexdigest(),))
                # Reaching here requires the genuine configured refresh, producer
                # replay, strict classifications/jobs, and bound renderer above.
                # Merely supplying a similarly shaped evidence dict cannot enter.
                gates = tuple(ValidationGate(name,True,(),tuple(dict.fromkeys(references[name])))
                              for name in gate_names)
                payload = ReleaseValidationPayload(run_id=candidate['run_id'],
                    release_identity_hash=manifest['release_identity_hash'],
                    input_manifest_hash=candidate['input_manifest_hash'],result_hash=candidate['result_hash'],
                    coverage_manifest_hash=evidence['coverage_manifest_hash'],
                    source_dependency_hash=evidence['source_dependency_hash'],
                    registry_manifest_hash=candidate['registry_manifest_hash'],
                    frozen_input_hash=candidate['frozen_input_hash'],universe_hash=candidate['universe_hash'],
                    code_version=candidate['code_version'],contract_version=candidate['contract_version'],
                    schema_version=version,purpose='audit',gates=gates)
                canonical_validation_bytes(payload)
                record(self)
            # The context has rechecked and closed. This DTO cannot authorize a
            # later write and is deliberately not signed or treated as a lease.
            return payload

        def audit(self, run_id):
            """Persist a freshly produced signed audit; return only its content hash.

            A signed audit is historical evidence, never publication authority.
            Caller payloads, signing overrides and purpose overrides are absent.
            """
            config, _, _ = record(self)
            signing = configurations[id(self)][3]
            if signing is None:
                raise ValueError('release audit requires explicit signing configuration')
            if type(run_id) is not str or not run_id or run_id.strip() != run_id:
                raise ValueError('release audit requires an exact run id')
            with closing(connect(config[0])) as connection:
                connection.execute('BEGIN')
                audit_schema(connection)
                if connection.execute("SELECT 1 FROM formal_release WHERE run_id=? AND status='publishing'",
                                      (run_id,)).fetchone() is not None:
                    raise ValueError('active publishing requires publication recovery')
            payload = self.validate(run_id)
            record(self)
            if payload.purpose != 'audit' or not all(gate.passed for gate in payload.gates):
                raise ValueError('release audit requires genuine successful audit validation')
            raw = canonical_validation_bytes(payload)
            key_id, signing_methods = signing
            signer, _, sign, _ = signing_methods[0]
            verifier = signing_methods[1][0]
            signature = sign(signer, signature_message(VALIDATION_DOMAIN, key_id, raw), key_id=key_id)
            record(self)
            verify_release_signature(raw, signature=signature, key_id=key_id,
                expected_key_id=key_id, domain=VALIDATION_DOMAIN, verifier=verifier)
            record(self)
            digest = sha256(raw).hexdigest()
            with transaction_wrapper(config[0], immediate=True) as connection:
                record(self)
                audit_schema(connection)
                if connection.execute("SELECT 1 FROM formal_release WHERE run_id=? AND status='publishing'",
                                      (run_id,)).fetchone() is not None:
                    raise ValueError('active publishing requires publication recovery')
                current = FormalFinalRunRepository._read_run(config[2], connection, run_id)
                if (current is None or current.mode != 'official_candidate' or current.status != 'preview_ready'
                        or any(current.header.get(name) != getattr(payload, name) for name in
                               ('run_id', 'input_manifest_hash', 'result_hash', 'registry_manifest_hash',
                                'frozen_input_hash', 'universe_hash', 'code_version', 'contract_version'))):
                    raise ValueError('candidate_changed: audit candidate changed before persistence')
                expected = (digest, run_id, payload.release_identity_hash, 'audit', 1, raw.decode('utf-8'))
                previous = connection.execute("""SELECT validation_hash,run_id,release_identity_hash,
                    purpose,passed,payload_json,signature,key_id FROM formal_release_validation
                    WHERE validation_hash=?""", (digest,)).fetchone()
                if previous is None:
                    connection.execute("""INSERT INTO formal_release_validation
                        (validation_hash,run_id,release_identity_hash,purpose,passed,payload_json,
                         signature,key_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                        expected + (signature, key_id, datetime.now(timezone.utc).isoformat()))
                else:
                    if tuple(previous[:6]) != expected or previous[7] != key_id:
                        raise ValueError('release audit record conflicts with immutable content')
                    verify_release_signature(raw, signature=previous[6], key_id=previous[7],
                        expected_key_id=key_id, domain=VALIDATION_DOMAIN, verifier=verifier)
                record(self)
            return digest

        def recover(self, run_id):
            """Complete only an already materialized, durably prepared release.

            Missing targets require fresh publication, never a preparation-only
            shortcut. No caller-supplied proofs, paths or verifier are accepted.
            """
            config, _, _ = record(self)
            saved = configurations[id(self)]
            signing, root = saved[3], saved[4]
            if signing is None or root is None:
                raise ValueError('recovery requires fixed signing configuration and release root')
            if type(run_id) is not str or not run_id or run_id.strip() != run_id:
                raise ValueError('recovery requires exact run id')
            key_id, signing_methods = signing
            verifier = signing_methods[1][0]
            with transaction_wrapper(config[0], immediate=True) as connection:
                audit_schema(connection)
                record(self)
                release, prepared = recovery_module._read_recovery_candidate(connection,
                    run_id=run_id,release_root=root,verifier=verifier,key_id=key_id)
                record(self)
                current = FormalFinalRunRepository._read_run(config[2],connection,run_id)
                if (current is None or current.mode != 'official_candidate' or current.status != 'preview_ready'
                        or current.header['input_manifest_hash'] != prepared.input_manifest_hash
                        or current.header['result_hash'] != prepared.result_hash):
                    raise ValueError('recovery historical candidate binding differs')
                manifest = decode(prepared.manifest_json)
                cards = {'audit_cards/'+item['security_id']+'.json' for item in current.scorecards}
                actual_cards = {item.path for item in prepared.files if item.path.startswith('audit_cards/')}
                pools = decode(current.artifacts['pool_selection_batch'])
                counts = dict(universe=len(current.security_ids),scorecards=len(current.scorecards),
                    formal_scored=sum(row['state']=='formal_scored' for row in current.statuses),
                    pool_vetoed=sum(row['state']=='pool_vetoed' for row in current.statuses),
                    strong=pools['counts']['strong'],wait=pools['counts']['wait'],payload_files=len(prepared.files))
                if actual_cards != cards or manifest['counts'] != counts:
                    raise ValueError('recovery manifest cards or counts differ from candidate')
                expected_files = tuple(sorted((item.path,item.sha256,item.byte_size) for item in prepared.files))
                expected_rows = tuple((release['active_preparation_hash'],*item) for item in expected_files)
                persisted = tuple(tuple(row) for row in connection.execute(
                    'SELECT preparation_hash,path,sha256,byte_size FROM formal_release_file WHERE release_id=? ORDER BY path COLLATE BINARY',
                    (release['release_id'],)))
                if release['status'] == 'published':
                    if (persisted != expected_rows or release['manifest_sha256'] != prepared.manifest_sha256
                            or not release['published_at'] or release['attempt_token'] is not None):
                        raise ValueError('published recovery metadata conflicts')
                    tree_module._verify_release_tree(Path(prepared.target_path),prepared)
                    record(self)
                    return dict(status='already_published',release_id=release['release_id'])
                if persisted:
                    raise ValueError('publishing recovery contains premature file rows')
                now = datetime.now(timezone.utc)
                token, expiry = release['attempt_token'], release['attempt_expires_at']
                if (token is None) != (expiry is None):
                    raise ValueError('recovery lease is malformed')
                if token is not None:
                    try:
                        expires = datetime.fromisoformat(expiry)
                    except (TypeError,ValueError) as exc:
                        raise ValueError('recovery lease expiry is malformed') from exc
                    if type(token) is not str or not token or expires.tzinfo is None:
                        raise ValueError('recovery lease is malformed')
                    if expires > now:
                        raise ValueError('recovery is blocked by an active publishing lease')
                owner = uuid4().hex
                generation = release['fencing_generation'] + 1
                deadline = now + timedelta(minutes=5)
                changed = connection.execute("""UPDATE formal_release SET attempt_token=?,attempt_expires_at=?,
                    fencing_generation=? WHERE release_id=? AND status='publishing'
                    AND fencing_generation=? AND attempt_token IS ?""",
                    (owner,deadline.isoformat(),generation,release['release_id'],release['fencing_generation'],token))
                if changed.rowcount != 1:
                    raise ValueError('recovery lease ownership changed')
                tree_module._verify_release_tree(Path(prepared.target_path),prepared)
                record(self)
                if datetime.now(timezone.utc) >= deadline:
                    raise ValueError('recovery lease expired during tree verification')
                audit_schema(connection)
                for path,digest,size in expected_files:
                    connection.execute('INSERT INTO formal_release_file VALUES(?,?,?,?,?)',
                        (release['release_id'],release['active_preparation_hash'],path,digest,size))
                changed = connection.execute("""UPDATE formal_release SET status='published',manifest_sha256=?,
                    published_at=?,attempt_token=NULL,attempt_expires_at=NULL
                    WHERE release_id=? AND status='publishing' AND attempt_token=? AND fencing_generation=?
                    AND active_preparation_hash=?""",
                    (prepared.manifest_sha256,datetime.now(timezone.utc).isoformat(),release['release_id'],owner,
                     generation,release['active_preparation_hash']))
                if changed.rowcount != 1:
                    raise ValueError('recovery preparation or fencing ownership changed')
                record(self)
            return dict(status='recovered',release_id=release['release_id'])

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
    wrapped_bodies = []
    for wrapper in (replay_hold, _hold_official_candidate, refresh_type.hold_evidence, refresh_type.hold_replay):
        cell = wrapper.__closure__[wrapper.__code__.co_freevars.index('func')]
        body = cell.cell_contents
        wrapped_bodies.append((cell, body, body.__code__))
    wrapped_bodies = tuple(wrapped_bodies)
    return refresh_type, reload


_ReleaseInputRefresh, _reload_official_registry_set = _install_inputs()
del _install_inputs

__all__ = []
