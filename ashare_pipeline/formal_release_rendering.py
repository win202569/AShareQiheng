"""Deterministic rendering of detached score data; no publication authority.

These private functions do not authenticate cards, grant a gate, write files or
recompute scores. The configured validator must supply genuine replayed bytes.
"""
import csv
from decimal import Decimal, InvalidOperation
import io
import json
import re
from .formal_release_types import canonical_release_bytes

_DIMENSIONS = ('G', 'V', 'M', 'EQ', 'FS', 'CA', 'T')
_SCORES = ('S0', 'Sc', 'Sbase', 'B', 'M_persistence', 'CA_downside', 'R_safety')
_SCORE_COLUMNS = ('security_id', 'template_id', 'primary_industry', 'secondary_industry',
    *_DIMENSIONS, 'C', *_SCORES, 'risk_exposure',
    *(key + '_grade' for key in _DIMENSIONS), *(key + '_grade' for key in _SCORES),
    'card_hash', 'source_entry_hash', 'source_batch_hash', 'cohort_references')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate render JSON key')
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError('render JSON cannot contain noninteger numbers')


def _number(value, maximum=100):
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError('render scores require exact decimal strings')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid render decimal') from exc
    if not number.is_finite() or number < 0 or number > maximum:
        raise ValueError('render score is nonfinite or out of range')
    return value


def _render_scorecard_payloads(raw):
    """Render scores.csv and complete audit cards, retaining decimal spellings.

    No timestamp, run selector, rounding or alternative grading enters rendering.
    Empty cards produce a header only; classification validity is a separate gate.
    """
    if type(raw) is not bytes:
        raise ValueError('render requires canonical bytes')
    try:
        wire = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_float=_invalid_number, parse_constant=_invalid_number)
        if (type(wire) is not dict or canonical_release_bytes(wire) != raw
                or wire.get('schema_version') != 'formal-final-score-card-batch-v1'
                or type(wire.get('cards')) is not list):
            raise ValueError('render requires canonical scorecard batch data')
        rows, files, seen = [], {}, set()
        for card in wire['cards']:
            if type(card) is not dict or card['schema_version'] != 'formal-final-score-card-v1':
                raise ValueError('render scorecard schema mismatch')
            sid = card['security_id']
            if type(sid) is not str or re.fullmatch(r'(SH|SZ|BJ)[0-9]{6}', sid) is None or sid in seen:
                raise ValueError('duplicate or unsafe render security id')
            seen.add(sid)
            row = {key: card[key] for key in _SCORE_COLUMNS[:4]}
            if any(type(value) is not str or not value for value in row.values()):
                raise ValueError('render identity fields must be nonempty text')
            if (type(card['dimensions']) is not dict or set(card['dimensions']) != set(_DIMENSIONS)
                    or type(card['dimension_grades']) is not dict
                    or set(card['dimension_grades']) != set(_DIMENSIONS)):
                raise ValueError('render requires exactly seven dimensions and grades')
            row.update({key: _number(card['dimensions'][key]) for key in _DIMENSIONS})
            row.update({key: _number(card[key]) for key in _SCORES})
            row['C'] = _number(card['confidence']['C'], 1)
            row['risk_exposure'] = _number(card['risk_exposure'])
            for key in _DIMENSIONS + _SCORES:
                grade = card['dimension_grades'][key] if key in _DIMENSIONS else card[key + '_grade']
                if type(grade) is not str or not grade:
                    raise ValueError('render grade must be present')
                row[key + '_grade'] = grade
            for key in ('card_hash', 'source_entry_hash', 'source_batch_hash'):
                value = card[key]
                if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
                    raise ValueError('render lineage hash is invalid')
                row[key] = value
            slots = card['source_input']['slots']
            if type(slots) is not dict:
                raise ValueError('render requires original input slots')
            references = {}
            for metric, slot in slots.items():
                if type(slot) is not dict:
                    raise ValueError('render input slot is malformed')
                references[metric] = {key: slot[key] for key in
                    ('metric_score', 'valuation_context', 'valuation_context_hash') if key in slot}
            row['cohort_references'] = canonical_release_bytes(references).decode('utf-8')
            rows.append(row)
            files['audit_cards/' + sid + '.json'] = canonical_release_bytes(card)
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=_SCORE_COLUMNS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row['security_id']))
        files['scores.csv'] = output.getvalue().encode('utf-8')
        return dict(sorted(files.items()))
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ValueError('incomplete or malformed scorecard render data') from exc


__all__ = []
