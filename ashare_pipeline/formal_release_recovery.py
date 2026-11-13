"""Read-only durable recovery authentication; returned values cannot authorize writes."""
from hashlib import sha256
import json
import re
from .formal_release_rendering import _RENDERER_VERSION
from .formal_release_types import (verify_release_signature, load_preparation_bytes,
    load_validation_bytes, PREPARATION_DOMAIN, VALIDATION_DOMAIN, canonical_release_identity_bytes)


def _signed_record(connection, table, hash_column, digest, domain, loader, verifier, key_id):
    row=connection.execute('SELECT * FROM '+table+' WHERE '+hash_column+'=?',(digest,)).fetchone()
    if row is None:
        raise ValueError('recovery requires durable signed '+table)
    row=dict(row);raw=row['payload_json'].encode('utf-8')
    if sha256(raw).hexdigest()!=digest:
        raise ValueError('recovery signed record hash differs')
    verify_release_signature(raw,signature=row['signature'],key_id=row['key_id'],
        expected_key_id=key_id,domain=domain,verifier=verifier)
    return row,loader(raw)


def _read_recovery_candidate(connection, *, run_id, release_root, verifier, key_id):
    rows=connection.execute('SELECT * FROM formal_release WHERE run_id=?',(run_id,)).fetchall()
    if len(rows)!=1:
        raise ValueError('recovery requires one exact durable release')
    release=dict(rows[0])
    if release['status'] not in ('publishing','published'):
        raise ValueError('blocked release cannot be recovered')
    saved,prepared=_signed_record(connection,'formal_release_preparation','preparation_hash',
        release['active_preparation_hash'],PREPARATION_DOMAIN,load_preparation_bytes,verifier,key_id)
    audit,validation=_signed_record(connection,'formal_release_validation','validation_hash',
        prepared.validation_hash,VALIDATION_DOMAIN,load_validation_bytes,verifier,key_id)
    if (validation.purpose!='publish' or audit['purpose']!='publish' or audit['passed']!=1
            or not all(gate.passed for gate in validation.gates)):
        raise ValueError('recovery rejects audit-only or failed validation')
    historical=connection.execute('SELECT * FROM formal_final_run WHERE run_id=?',(run_id,)).fetchone()
    if (historical is None or any(historical[name]!=getattr(validation,name) for name in
            ('code_version','contract_version','input_manifest_hash','result_hash',
             'registry_manifest_hash','frozen_input_hash','universe_hash'))):
        raise ValueError('recovery validation differs from historical candidate')
    identity=sha256(canonical_release_identity_bytes(contract_version=validation.contract_version,
        input_manifest_hash=validation.input_manifest_hash,result_hash=validation.result_hash,
        renderer_version=prepared.renderer_version)).hexdigest()
    rid='20260831-formal-v3-'+identity
    target=(release_root/rid).as_posix()
    if (release['release_id']!=rid or saved['release_id']!=rid
            or prepared.target_path!=target or release['release_path']!=target
            or release['validation_hash']!=prepared.validation_hash or saved['validation_hash']!=prepared.validation_hash
            or saved['manifest_json']!=prepared.manifest_json or saved['manifest_sha256']!=prepared.manifest_sha256
            or saved['manifest_byte_size']!=prepared.manifest_byte_size
            or type(saved['fencing_generation']) is not int or saved['fencing_generation']<1
            or type(release['fencing_generation']) is not int
            or saved['fencing_generation']>release['fencing_generation']):
        raise ValueError('recovery preparation binding differs')
    if any(row['run_id']!=run_id or row['release_identity_hash']!=identity for row in (release,saved,audit)):
        raise ValueError('recovery record run or root differs')
    if any(value.run_id!=run_id or value.release_identity_hash!=identity
           or value.input_manifest_hash!=release['input_manifest_hash']
           or value.result_hash!=release['result_hash'] for value in (prepared,validation)):
        raise ValueError('recovery candidate binding differs')
    manifest=json.loads(prepared.manifest_json)
    files=sorted((dict(path=item.path,sha256=item.sha256,byte_size=item.byte_size) for item in prepared.files),key=lambda row:row['path'])
    if (manifest.get('schema')!='formal-release-manifest-v1' or manifest.get('release_id')!=rid
            or manifest.get('release_identity_hash')!=identity or manifest.get('renderer_version')!=prepared.renderer_version
            or manifest.get('files')!=files or manifest.get('freeze_at_utc')!='2026-08-31T07:00:00+00:00'
            or any(manifest.get(name)!=getattr(validation,name) for name in
                   ('input_manifest_hash','result_hash','contract_version','registry_manifest_hash','frozen_input_hash','universe_hash'))):
        raise ValueError('recovery manifest differs from signed preparation')
    paths={item.path for item in prepared.files}
    required={'universe_status.csv','scores.csv','strong_attention.csv','waiting_price.csv',
              'evidence_manifest.json','quality_report.md'}
    cards=paths-required
    counts=manifest.get('counts')
    if (prepared.renderer_version!=_RENDERER_VERSION or not required <= paths
            or any(re.fullmatch(r'audit_cards/(SH|SZ|BJ)[0-9]{6}\.json',path) is None for path in cards)
            or type(counts) is not dict or set(counts)!={'universe','scorecards','formal_scored','pool_vetoed','strong','wait','payload_files'}
            or any(type(value) is not int or value<0 for value in counts.values())
            or counts['payload_files']!=len(paths) or counts['scorecards']!=len(cards)
            or counts['formal_scored']+counts['pool_vetoed']!=counts['universe']
            or counts['strong']>20 or counts['wait']>50):
        raise ValueError('recovery manifest payload set or counts are invalid')
    return release,prepared


__all__=[]
