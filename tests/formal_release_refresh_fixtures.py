"""Canonical storage-only history; NEVER a producer-backed official candidate.

This fixture deliberately claims complete classification. It tests that a
read-only input refresh cannot promote such history into release authority.
"""
from contextlib import closing
from copy import deepcopy

from ashare_pipeline import formal_final_repository as history


def put_storage_only_history(fixture, *, code_version):
    from tests.test_formal_final_repository import FormalFinalRecoveryBoundaryTests
    template = FormalFinalRecoveryBoundaryTests()
    template.setUp()
    try:
        old_inputs, old_scores, old_eligible, old_pools = template.wires
        frozen = fixture.frozen
        ids = sorted(member.security_id for member in frozen.members)
        common = dict(registry_manifest_hash=frozen.registry_manifest_hash,
            frozen_input_hash=frozen.frozen_input_hash, universe_hash=frozen.universe_hash,
            as_of_utc=frozen.as_of_utc)

        def seal(payload, key, prior=None):
            unsigned = {name: value for name, value in payload.items() if name != key}
            preimage = dict(unsigned, **{key: prior}) if prior is not None else unsigned
            return dict(unsigned, **{key: history._serialize_payload(preimage)[1]})

        entries = [seal(dict(deepcopy(old_inputs['inputs'][0]), **common, security_id=sid),
                        'entry_hash') for sid in ids]
        inputs = seal(dict(deepcopy(old_inputs), **common, security_ids=ids, inputs=entries), 'batch_hash')
        cards = [seal(dict(deepcopy(old_scores['cards'][0]), security_id=sid,
            source_entry_hash=entry['entry_hash'], source_batch_hash=inputs['batch_hash']), 'card_hash')
            for sid, entry in zip(ids, entries, strict=True)]
        scores = seal(dict(deepcopy(old_scores), **common, security_ids=ids, cards=cards,
            source_batch_hash=inputs['batch_hash']), 'batch_hash', inputs['batch_hash'])
        eligibilities = [seal(dict(deepcopy(old_eligible['eligibilities'][0]), security_id=sid,
            strong_qualified=False, wait_qualified=False, source_entry_hash=entry['entry_hash'],
            source_batch_hash=inputs['batch_hash'], score_batch_hash=scores['batch_hash'],
            card_hash=card['card_hash']), 'eligibility_hash')
            for sid, entry, card in zip(ids, entries, cards, strict=True)]
        eligible = seal(dict(deepcopy(old_eligible), security_ids=ids, eligibilities=eligibilities,
            source_batch_hash=inputs['batch_hash'], score_batch_hash=scores['batch_hash']), 'batch_hash')
        decisions = [seal(dict(deepcopy(old_pools['decisions'][0]), security_id=sid,
            pool=pool, decision='not_qualified', eligibility_hash=item['eligibility_hash'],
            source_batch_hash=eligible['batch_hash']), 'decision_hash')
            for sid, item in zip(ids, eligibilities, strict=True) for pool in ('strong', 'wait')]
        pools = seal(dict(deepcopy(old_pools), security_ids=ids,
            source_batch_hash=eligible['batch_hash'], strong_security_ids=[], wait_security_ids=[],
            counts=dict(strong=0, wait=0), decisions=decisions), 'batch_hash')
        coverage = dict(schema_version='formal-coverage-v1', blockers=[], authenticated_context=False,
            freeze_at_utc=frozen.as_of_utc, rows=[dict(security_id=sid, exchange=sid[:2],
                frozen_input_hash=frozen.frozen_input_hash) for sid in ids])
        run_id = 'storage-only-not-a-live-candidate'
        artifacts = {}
        for kind, wire in zip(history.ARTIFACT_KINDS, (coverage, inputs, scores, eligible, pools), strict=True):
            raw, digest = history._serialize_payload(wire)
            artifacts[kind] = dict(run_id=run_id, artifact_kind=kind, payload_json=raw, artifact_hash=digest)
        header = dict(run_id=run_id, mode='official_candidate', status='preview_ready', **common,
            coverage_manifest_hash=artifacts['coverage_manifest']['artifact_hash'],
            code_version=code_version, contract_version='formal-final-v1', created_at='fixture-only')
        header['input_manifest_hash'] = history._serialize_payload(history._input_identity(header, artifacts))[1]
        header['result_hash'] = history._result_hash(header, artifacts)
        rows = dict(formal_final_run=[header], formal_final_artifact=list(artifacts.values()),
                    **history._project_rows(run_id, (inputs, scores, eligible, pools)))
        with closing(fixture.store._connect()) as connection:
            for table, group in rows.items():
                if group:
                    history._insert_rows(connection, table, group, tuple(group[0]))
            connection.commit()
        return run_id
    finally:
        template.doCleanups()
