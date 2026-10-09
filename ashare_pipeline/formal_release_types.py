"""Validated release data and domain-separated signatures; no live authority."""
from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import re


REQUIRED_RELEASE_GATE_NAMES = (
    'candidate_identity', 'official_registry', 'workspace_identity',
    'frozen_universe', 'official_coverage', 'source_identity_temporal',
    'replay_equivalence', 'classification_complete', 'score_formula',
    'pool_selection', 'job_quiescence', 'artifact_renderability',
)
VALIDATION_DOMAIN = 'formal-release-validation-v1'
PREPARATION_DOMAIN = 'formal-release-preparation-v1'


def _text(value, name):
    if type(value) is not str or not value or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(name + ' must be nonempty text without control characters')


def _hash(value, name):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError(name + ' must be a lowercase SHA-256')


def _size(value):
    if type(value) is not int or value < 0:
        raise ValueError('byte size must be a nonnegative integer')


def _tuple(value, name):
    if type(value) is not tuple:
        raise ValueError(name + ' must be an immutable tuple')


def _safe_relative_path(value):
    _text(value, 'file path')
    parts = value.split('/')
    if any(part in ('', '.', '..') or part.endswith(('.', ' '))
           or re.fullmatch('[A-Za-z0-9_.-]+', part) is None
           or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', part.split('.')[0], re.I)
           for part in parts):
        raise ValueError('unsafe release file path')


def _json_value(value):
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError('release Decimal must be finite')
        return str(value)
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError('JSON keys must be strings')
        return {key: _json_value(child) for key, child in value.items()}
    if type(value) in (tuple, list):
        return [_json_value(child) for child in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError('unsupported release JSON value')


def canonical_release_bytes(value):
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')


@dataclass(frozen=True)
class ValidationGate:
    name: str
    passed: bool
    reason_codes: tuple
    evidence_hashes: tuple

    def __post_init__(self):
        _text(self.name, 'gate name')
        if type(self.passed) is not bool:
            raise ValueError('gate passed must be a bool')
        _tuple(self.reason_codes, 'reason codes')
        _tuple(self.evidence_hashes, 'evidence hashes')
        for reason in self.reason_codes:
            _text(reason, 'reason')
        for digest in self.evidence_hashes:
            _hash(digest, 'evidence hash')
        if len(set(self.reason_codes)) != len(self.reason_codes) or len(set(self.evidence_hashes)) != len(self.evidence_hashes):
            raise ValueError('duplicate gate reason or evidence')
        if (self.passed and self.reason_codes) or (not self.passed and not self.reason_codes):
            raise ValueError('gate reasons must explain failure')


@dataclass(frozen=True)
class ReleaseValidationPayload:
    run_id: str
    release_identity_hash: str
    input_manifest_hash: str
    result_hash: str
    coverage_manifest_hash: str
    source_dependency_hash: str
    registry_manifest_hash: str
    frozen_input_hash: str
    universe_hash: str
    code_version: str
    contract_version: str
    schema_version: int
    purpose: str
    gates: tuple

    def __post_init__(self):
        _text(self.run_id, 'run id')
        _text(self.contract_version, 'contract version')
        for name in ('release_identity_hash', 'input_manifest_hash', 'result_hash',
                'coverage_manifest_hash', 'source_dependency_hash', 'registry_manifest_hash',
                'frozen_input_hash', 'universe_hash'):
            _hash(getattr(self, name), name)
        if type(self.code_version) is not str or re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', self.code_version) is None:
            raise ValueError('code version must be a full Git revision')
        if type(self.schema_version) is not int or self.schema_version != 9:
            raise ValueError('release requires schema version 9')
        if type(self.purpose) is not str or self.purpose not in ('publish', 'audit'):
            raise ValueError('invalid validation purpose')
        _tuple(self.gates, 'gates')
        if any(type(gate) is not ValidationGate for gate in self.gates):
            raise ValueError('invalid gate type')
        for gate in self.gates:
            gate.__post_init__()
        names = [gate.name for gate in self.gates]
        if len(names) != len(set(names)) or set(names) != set(REQUIRED_RELEASE_GATE_NAMES):
            raise ValueError('required gate set must be exact')


@dataclass(frozen=True)
class ReleaseFile:
    path: str
    sha256: str
    byte_size: int

    def __post_init__(self):
        _safe_relative_path(self.path)
        _hash(self.sha256, 'file hash')
        _size(self.byte_size)


@dataclass(frozen=True)
class ReleasePreparationPayload:
    release_identity_hash: str
    run_id: str
    validation_hash: str
    input_manifest_hash: str
    result_hash: str
    manifest_sha256: str
    manifest_byte_size: int
    renderer_version: str
    target_path: str
    files: tuple
    manifest_json: str

    def __post_init__(self):
        for name in ('release_identity_hash', 'validation_hash', 'input_manifest_hash',
                     'result_hash', 'manifest_sha256'):
            _hash(getattr(self, name), name)
        _text(self.run_id, 'run id')
        _text(self.renderer_version, 'renderer version')
        _size(self.manifest_byte_size)
        if type(self.manifest_json) is not str:
            raise ValueError('manifest raw UTF-8 text required')
        try:
            raw_manifest = self.manifest_json.encode('utf-8')
            manifest = json.loads(self.manifest_json, object_pairs_hook=_pairs)
            if type(manifest) is not dict or canonical_release_bytes(manifest) != raw_manifest:
                raise ValueError('manifest must be a canonical JSON object')
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError('invalid manifest bytes') from exc
        if (hashlib.sha256(raw_manifest).hexdigest() != self.manifest_sha256
                or len(raw_manifest) != self.manifest_byte_size):
            raise ValueError('manifest bytes differ from hash or size')
        _text(self.target_path, 'target path')
        target = self.target_path
        absolute = PureWindowsPath(target).is_absolute() or PurePosixPath(target).is_absolute()
        if not absolute or '\\' in target or '//' in target:
            raise ValueError('target must be an absolute normalized path')
        # The configured root may contain spaces; Windows aliases and device
        # components still cannot identify a second spelling of the same path.
        components = target.split('/')[1:]
        if any(part in ('', '.', '..') or part.endswith(('.', ' '))
               or any(c in part for c in ':<>"|?*')
               or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3])', part.split('.')[0], re.I)
               for part in components):
            raise ValueError('unsafe target component')
        if target.rsplit('/', 1)[-1] != '20260831-formal-v3-' + self.release_identity_hash:
            raise ValueError('target differs from release identity')
        _tuple(self.files, 'files')
        if not self.files or any(type(item) is not ReleaseFile for item in self.files):
            raise ValueError('preparation requires files')
        for item in self.files:
            item.__post_init__()
        paths = [item.path.casefold() for item in self.files]
        if len(set(paths)) != len(paths) or any(
                path == 'release_manifest.json' or path.startswith('release_manifest.json/')
                for path in paths):
            raise ValueError('duplicate or reserved manifest path')
        path_set = set(paths)
        parents = {}
        for item in self.files:
            parts = item.path.split('/')
            for i in range(1, len(parts)):
                parent = '/'.join(parts[:i])
                previous = parents.setdefault(parent.casefold(), parent)
                if previous != parent:
                    raise ValueError('directory case collision')
        for path in paths:
            parts = path.split('/')
            if any('/'.join(parts[:i]) in path_set for i in range(1, len(parts))):
                raise ValueError('file conflicts with a parent directory')


def canonical_validation_bytes(payload):
    if type(payload) is not ReleaseValidationPayload:
        raise ValueError('validation payload type required')
    payload.__post_init__()
    wire = asdict(payload)
    gates = {gate.name: gate for gate in payload.gates}
    wire['gates'] = [asdict(gates[name]) for name in REQUIRED_RELEASE_GATE_NAMES]
    return canonical_release_bytes(dict(schema=VALIDATION_DOMAIN, **wire))


def canonical_preparation_bytes(payload):
    if type(payload) is not ReleasePreparationPayload:
        raise ValueError('preparation payload type required')
    payload.__post_init__()
    wire = asdict(payload)
    wire['files'] = sorted(wire['files'], key=lambda item: item['path'])
    return canonical_release_bytes(dict(schema=PREPARATION_DOMAIN, **wire))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _load(raw, domain):
    if type(raw) is not bytes:
        raise ValueError('canonical bytes required')
    def invalid_number(value):
        raise ValueError('noninteger JSON number')
    try:
        wire = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=invalid_number, parse_float=invalid_number)
        if type(wire) is not dict or wire.pop('schema', None) != domain:
            raise ValueError('payload schema mismatch')
        if domain == VALIDATION_DOMAIN:
            gates = wire['gates']
            if type(gates) is not list:
                raise ValueError('gate array required')
            wire['gates'] = tuple(ValidationGate(**dict(item,
                reason_codes=tuple(item['reason_codes']), evidence_hashes=tuple(item['evidence_hashes'])))
                for item in gates)
            payload = ReleaseValidationPayload(**wire)
            expected = canonical_validation_bytes(payload)
        else:
            if type(wire['files']) is not list:
                raise ValueError('file array required')
            wire['files'] = tuple(ReleaseFile(**item) for item in wire['files'])
            payload = ReleasePreparationPayload(**wire)
            expected = canonical_preparation_bytes(payload)
        if expected != raw:
            raise ValueError('payload is not canonical')
        return payload
    except (TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid release payload') from exc


def load_validation_bytes(raw):
    return _load(raw, VALIDATION_DOMAIN)


def load_preparation_bytes(raw):
    return _load(raw, PREPARATION_DOMAIN)


def signature_message(domain, key_id, raw):
    _text(key_id, 'key id')
    if domain == VALIDATION_DOMAIN:
        load_validation_bytes(raw)
    elif domain == PREPARATION_DOMAIN:
        load_preparation_bytes(raw)
    else:
        raise ValueError('unknown signature domain')
    return b'AShareQiheng\x00' + domain.encode() + b'\x00' + key_id.encode() + b'\x00' + raw


def verify_release_signature(raw, *, signature, key_id, expected_key_id, domain, verifier):
    """Cryptographic data check only; caller must still enforce live authority."""
    _text(expected_key_id, 'trusted key id')
    _text(signature, 'signature')
    if key_id != expected_key_id:
        raise ValueError('signature key differs from configured identity')
    message = signature_message(domain, key_id, raw)
    if verifier.verify(message, signature=signature, key_id=key_id) is not True:
        raise ValueError('release signature rejected')
