"""Release validation comparisons; no live validator or capability yet.

These private helpers operate on detached data only. The future configured
validator must obtain history through the trusted V8 reader, reload official
sources, replay genuine producers and recheck all live gates. Passing these
comparisons is neither authentication nor permission to publish.
"""
import re
import inspect
from pathlib import Path
from types import MethodType

from .formal_final_repository import FormalFinalRunSnapshot
from .formal_final_score_inputs import (
    FormalFinalScoreInputRepository, PolicyAdjustedScoreInputBatch, _prepare_final_inputs,
)
from .formal_final_scoring import build_final_score_card_batch, FinalScoreCardBatch
from .formal_final_eligibility import build_formal_eligibility_batch, FormalEligibilityBatch
from .formal_pool import select_formal_pools, PoolSelectionBatch
from .formal_scoring_registry import FormalScoringRegistry
from .formal_policy_registry import FormalPolicyRegistry
from .formal_valuation_adapter_contract import FormalValuationAdapterRegistry
from .formal_coverage_manifest import VerifiedCoverageManifest
from .state_store import StateStore


_COMPUTATION_KINDS = ('score_input_batch', 'scorecard_batch',
                      'eligibility_batch', 'pool_selection_batch')
_FREEZE = '2026-08-31T07:00:00+00:00'
_HASH = re.compile(r'[0-9a-f]{64}')
_CODE = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')
_SECURITY = re.compile(r'(?:SH|SZ|BJ)[0-9]{6}')


def _check_candidate_binding(snapshot, *, run_id, code_version, contract_version,
                             registry_manifest_hash, frozen_input_hash,
                             universe_hash, security_ids):
    """Check historical selection data against separately obtained identities.

    Returns None, deliberately not a proof. Expected identities must come from
    the configured validator's trusted reads, never user-supplied overrides.
    """
    if type(snapshot) is not FormalFinalRunSnapshot:
        raise ValueError('candidate requires detached V8 history data')
    if (type(run_id) is not str or not run_id or run_id.strip() != run_id
            or type(contract_version) is not str or not contract_version
            or contract_version.strip() != contract_version
            or type(code_version) is not str or _CODE.fullmatch(code_version) is None):
        raise ValueError('candidate expected run/code/contract identity is invalid')
    for value in (registry_manifest_hash, frozen_input_hash, universe_hash):
        if type(value) is not str or _HASH.fullmatch(value) is None:
            raise ValueError('candidate expected root/frozen/universe identity is invalid')
    if (type(security_ids) is not tuple or not security_ids
            or any(type(sid) is not str or _SECURITY.fullmatch(sid) is None
                   for sid in security_ids)
            or tuple(sorted(set(security_ids))) != security_ids
            or {sid[:2] for sid in security_ids} != {'SH', 'SZ', 'BJ'}):
        raise ValueError('candidate requires exact sorted SH/SZ/BJ frozen members')
    header = snapshot.header
    if header.get('mode') != 'official_candidate' or header.get('status') != 'preview_ready':
        raise ValueError('candidate must be an official preview_ready V8 run')
    expected = dict(run_id=run_id, contract_version=contract_version,
                    registry_manifest_hash=registry_manifest_hash,
                    frozen_input_hash=frozen_input_hash, universe_hash=universe_hash,
                    as_of_utc=_FREEZE)
    for name, value in expected.items():
        if header.get(name) != value:
            raise ValueError('candidate identity mismatch: ' + name)
    if header.get('code_version') != code_version:
        raise ValueError('candidate_changed: current code requires a new Stage D candidate')
    try:
        input_ids = tuple(row['security_id'] for row in snapshot.inputs)
        status_ids = tuple(row['security_id'] for row in snapshot.statuses)
        states = tuple(row['state'] for row in snapshot.statuses)
    except (KeyError, TypeError) as exc:
        raise ValueError('candidate member or classification data is malformed') from exc
    if input_ids != security_ids or status_ids != security_ids:
        raise ValueError('candidate members/classifications differ from the exact frozen universe')
    if any(state not in ('formal_scored', 'pool_vetoed') for state in states):
        raise ValueError('candidate contains pending, out-of-scope or unknown classifications')


def _compare_candidate_replay(snapshot, computation_bytes):
    """Name changed computation artifacts, excluding operational coverage bytes.

    Input bytes are data, not proofs. The live validator must acquire them from
    authenticated D1/D2/D3/pool producers and retain their source checkpoints.
    An empty tuple means byte equality only; it confers no release authority.
    """
    if type(snapshot) is not FormalFinalRunSnapshot:
        raise ValueError('replay comparison requires detached V8 history data')
    if type(computation_bytes) is not dict or set(computation_bytes) != set(_COMPUTATION_KINDS):
        raise ValueError('replay comparison requires exactly four computation artifacts')
    changed = []
    for name in _COMPUTATION_KINDS:
        current, original = computation_bytes[name], snapshot.artifacts.get(name)
        if type(current) is not bytes or type(original) is not bytes:
            raise ValueError('replay comparison requires immutable raw bytes: ' + name)
        if current != original:
            changed.append(name)
    return tuple(changed)


def _install_official_replay():
    """Capture producers; expose a data-only replay, not their private proofs."""
    authority = inspect.getclosurevars(_prepare_final_inputs).nonlocals
    record, dependencies = authority['record'], authority['dependencies']
    verify_sources, registry_snapshot = authority['verify_sources'], authority['registry_snapshot']
    build_inputs = FormalFinalScoreInputRepository.build_batch
    build_scores, build_eligibility, build_pools = (
        build_final_score_card_batch, build_formal_eligibility_batch, select_formal_pools)
    check, compare = _check_candidate_binding, _compare_candidate_replay
    owner = globals()
    bindings = tuple((name, owner[name]) for name in (
        'FormalFinalRunSnapshot', 'FormalFinalScoreInputRepository',
        'PolicyAdjustedScoreInputBatch', 'FinalScoreCardBatch', 'FormalEligibilityBatch',
        'PoolSelectionBatch', 'FormalScoringRegistry', 'FormalPolicyRegistry',
        'FormalValuationAdapterRegistry', 'VerifiedCoverageManifest',
        'build_final_score_card_batch', 'build_formal_eligibility_batch',
        'select_formal_pools', '_check_candidate_binding', '_compare_candidate_replay',
        'Path', 'MethodType', 'StateStore', '_COMPUTATION_KINDS', '_FREEZE',
        '_HASH', '_CODE', '_SECURITY'))
    methods = tuple((cls, name, getattr(cls, name)) for cls, names in (
        (FormalFinalScoreInputRepository, ('__init__', 'build_batch')),
        (VerifiedCoverageManifest, ('require_verified', 'require_official_ready',
                                   'to_dict', 'canonical_bytes')),
        (StateStore, ('get_verified_formal_frozen_universe',)),
    ) for name in names)
    functions = (build_inputs, build_scores, build_eligibility, build_pools,
                 check, compare, record, dependencies, verify_sources, registry_snapshot)
    codes = tuple((function, function.__code__) for function in functions) + tuple(
        (method, method.__code__) for _, _, method in methods)

    def interfaces():
        if (any(owner.get(name) is not original for name, original in bindings)
                or any(getattr(cls, name) is not original for cls, name, original in methods)
                or any(function.__code__ is not code for function, code in codes)):
            raise ValueError('official replay producer authority changed')

    def replay(snapshot, *, run_id, input_repository, scoring_registry,
               policy_registry, valuation_adapter_registry, coverage_manifest,
               contract_version='formal-final-v1'):
        """Recompute four batches without V8 writes; return only bytes and diff.

        Internal building block. Coverage is a genuine freshly audited proof
        supplied by the future configured validator, never a public override.
        This function cannot sign, mint a release capability or publish files.
        """
        interfaces()
        for value, cls in ((snapshot, FormalFinalRunSnapshot),
                           (input_repository, FormalFinalScoreInputRepository),
                           (scoring_registry, FormalScoringRegistry),
                           (policy_registry, FormalPolicyRegistry),
                           (valuation_adapter_registry, FormalValuationAdapterRegistry),
                           (coverage_manifest, VerifiedCoverageManifest)):
            if type(value) is not cls:
                raise ValueError('official replay requires genuine repository/registry/coverage types')
        feature, _, _, verifier, _, _, _ = dependencies(input_repository)
        method = getattr(input_repository, 'build_batch')
        if (type(method) is not MethodType or method.__self__ is not input_repository
                or method.__func__ is not build_inputs):
            raise ValueError('official replay repository entry point changed')
        coverage_manifest.require_official_ready()
        wire = coverage_manifest.to_dict()
        frozen_hash = snapshot.header.get('frozen_input_hash')
        frozen = feature._store.get_verified_formal_frozen_universe(frozen_hash)
        if frozen is None:
            raise ValueError('official replay frozen candidate was not found')
        ids = tuple(sorted(member.security_id for member in frozen.members))
        check(snapshot, run_id=run_id, code_version=wire.get('workspace_revision'),
              contract_version=contract_version, registry_manifest_hash=frozen.registry_manifest_hash,
              frozen_input_hash=frozen.frozen_input_hash, universe_hash=frozen.universe_hash,
              security_ids=ids)
        if (wire.get('registry_manifest_hash') != frozen.registry_manifest_hash
                or wire.get('frozen_input_hash') != frozen.frozen_input_hash
                or wire.get('universe_records_hash') != frozen.universe_hash
                or wire.get('freeze_at_utc') != _FREEZE
                or wire.get('member_count') != len(ids)
                or Path(wire.get('db_path', '')).resolve() != Path(feature._store.db_path).resolve()
                or {row['security_id'] for row in wire['rows']} != set(ids)):
            raise ValueError('official replay coverage belongs to another candidate/source store')
        bundle, registry_bytes = registry_snapshot(feature, verifier, frozen.registry_manifest_hash,
            scoring_registry, policy_registry, valuation_adapter_registry, expected_purpose='official')
        bundle.require_official()
        inputs = build_inputs(input_repository, frozen_hash, scoring_registry=scoring_registry,
            policy_registry=policy_registry, valuation_adapter_registry=valuation_adapter_registry,
            expected_purpose='official')
        saved = record(inputs, PolicyAdjustedScoreInputBatch)
        retention = saved[5]
        if retention[0] is not input_repository or retention[4] != 'official':
            raise ValueError('official replay input owner or purpose differs')
        checkpoint = retention[3][0]
        with checkpoint.hold():
            source_bytes = verify_sources(retention[1])
            scores = build_scores(inputs)
            eligibility = build_eligibility(inputs, scores)
            pools = build_pools(eligibility)
            batches = (inputs, scores, eligibility, pools)
            for batch, cls in zip(batches, (PolicyAdjustedScoreInputBatch, FinalScoreCardBatch,
                                          FormalEligibilityBatch, PoolSelectionBatch), strict=True):
                if type(batch) is not cls:
                    raise ValueError('official replay producer returned a non-genuine batch')
                batch.require_verified()
            if any(row['state'] not in ('formal_scored', 'pool_vetoed')
                   for row in eligibility.to_dict()['eligibilities']):
                raise ValueError('candidate_changed: official replay has pending scoring evidence')
            raw = dict(zip(_COMPUTATION_KINDS,
                           (batch.canonical_bytes() for batch in batches), strict=True))
            changed = compare(snapshot, raw)
            # Recheck all retained dependencies, not a cached "valid" verdict.
            interfaces()
            dependencies(input_repository)
            if verify_sources(retention[1]) != source_bytes:
                raise ValueError('candidate_changed: official replay sources changed')
            for proof in retention[2]:
                proof.require_verified()
            _, current_registry = registry_snapshot(feature, verifier, frozen.registry_manifest_hash,
                scoring_registry, policy_registry, valuation_adapter_registry, expected_purpose='official')
            if current_registry != registry_bytes:
                raise ValueError('candidate_changed: official replay registry changed')
            for name, batch in zip(_COMPUTATION_KINDS, batches, strict=True):
                batch.require_verified()
                if batch.canonical_bytes() != raw[name]:
                    raise ValueError('candidate_changed: official replay batch changed')
            checkpoint.recheck()
            coverage_manifest.require_official_ready()
            return raw, changed

    return replay


_replay_official_candidate = _install_official_replay()
del _install_official_replay

__all__ = []
