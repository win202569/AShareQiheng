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



def _render_batch(raw, schema):
    if type(raw) is not bytes:
        raise ValueError('render requires canonical bytes')
    wire = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                      parse_float=_invalid_number, parse_constant=_invalid_number)
    if type(wire) is not dict or wire.get('schema_version') != schema or canonical_release_bytes(wire) != raw:
        raise ValueError('render batch schema or canonical bytes differ')
    return wire


def _csv_payload(columns, rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def _render_selection_payloads(score_raw, eligibility_raw, pool_raw):
    """Render detached selection data without reranking, rounding or filling pools.

    Structural checks are not authentication or a fresh eligibility decision.
    The trusted validator must bind all three genuine producer batches first.
    """
    try:
        scores = _render_batch(score_raw, 'formal-final-score-card-batch-v1')
        eligibility = _render_batch(eligibility_raw, 'formal-eligibility-batch-v1')
        pools = _render_batch(pool_raw, 'formal-pool-batch-v1')
        score_csv = _render_scorecard_payloads(score_raw)['scores.csv']
        cards = {row['security_id']: row for row in csv.DictReader(io.StringIO(score_csv.decode('utf-8')))}
        ids = eligibility['security_ids']
        if (type(ids) is not list or any(type(sid) is not str or re.fullmatch(r'(SH|SZ|BJ)[0-9]{6}', sid) is None for sid in ids)
                or ids != sorted(set(ids)) or pools['security_ids'] != ids
                or not set(cards) <= set(ids)):
            raise ValueError('render selection universe differs')
        if (eligibility['score_batch_hash'] != scores['batch_hash']
                or pools['source_batch_hash'] != eligibility['batch_hash']):
            raise ValueError('render selection batch lineage differs')
        entries = eligibility['eligibilities']
        if type(entries) is not list or [row['security_id'] for row in entries] != ids:
            raise ValueError('render requires exact per-member classifications')
        by_id = {row['security_id']: row for row in entries}
        for row in entries:
            if row['state'] not in ('formal_scored', 'pool_vetoed'):
                raise ValueError('render refuses pending or out-of-scope classifications')
            if type(row['reason_codes']) is not list or any(type(reason) is not str for reason in row['reason_codes']):
                raise ValueError('render classification reasons malformed')
            for key in ('strong_qualified', 'wait_qualified'):
                if type(row[key]) is not bool:
                    raise ValueError('render qualification flag must be bool')
            card = cards.get(row['security_id'])
            if (row['state'] == 'formal_scored' and card is None
                    or card is not None and (row['card_hash'] != card['card_hash']
                    or row['secondary_industry'] != card['secondary_industry'])):
                raise ValueError('render classification card lineage differs')
        decisions = {}
        for row in pools['decisions']:
            if row['decision'] not in ('selected', 'not_qualified', 'industry_cap_reached', 'overall_capacity_reached'):
                raise ValueError('render pool decision is unknown')
            pair = (row['security_id'], row['pool'])
            if pair in decisions or pair[0] not in by_id or pair[1] not in ('strong', 'wait'):
                raise ValueError('render pool decision universe differs')
            if row['eligibility_hash'] != by_id[pair[0]]['eligibility_hash']:
                raise ValueError('render pool decision lineage differs')
            decisions[pair] = row
        if set(decisions) != {(sid, pool) for sid in ids for pool in ('strong', 'wait')}:
            raise ValueError('render requires both decisions for every security')
        files, selected = {}, set()
        for pool, filename, limit, industry_limit in (
                ('strong', 'strong_attention.csv', 20, 4), ('wait', 'waiting_price.csv', 50, 10)):
            chosen = pools[pool + '_security_ids']
            count = pools['counts'][pool]
            if (type(chosen) is not list or any(type(sid) is not str for sid in chosen)
                    or len(chosen) != len(set(chosen)) or not set(chosen) <= set(ids)
                    or type(count) is not int or count != len(chosen) or count > limit
                    or selected.intersection(chosen)):
                raise ValueError('render pool membership, capacity or count differs')
            if {sid for sid in ids if decisions[(sid,pool)]['decision'] == 'selected'} != set(chosen):
                raise ValueError('render pool list differs from selected decisions')
            rows, industries = [], {}
            for ordinal, sid in enumerate(chosen, 1):
                entry = by_id[sid]
                if entry['state'] != 'formal_scored' or not entry[pool + '_qualified'] or sid not in cards:
                    raise ValueError('render selected member is not qualified')
                industry = entry['secondary_industry']
                industries[industry] = industries.get(industry, 0) + 1
                if industries[industry] > industry_limit:
                    raise ValueError('render industry capacity exceeded')
                rows.append(dict(cards[sid], pool=pool, selected_ordinal=ordinal,
                    eligibility_hash=entry['eligibility_hash'], decision_hash=decisions[(sid,pool)]['decision_hash']))
            files[filename] = _csv_payload(('pool','selected_ordinal', *_SCORE_COLUMNS,
                                            'eligibility_hash','decision_hash'), rows)
            selected.update(chosen)
        states = [dict(security_id=row['security_id'], state=row['state'],
            reason_codes=canonical_release_bytes(row['reason_codes']).decode('utf-8'),
            strong_qualified=str(row['strong_qualified']).lower(),
            wait_qualified=str(row['wait_qualified']).lower(),
            card_hash=row['card_hash'], eligibility_hash=row['eligibility_hash']) for row in entries]
        files['universe_status.csv'] = _csv_payload(('security_id','state','reason_codes',
            'strong_qualified','wait_qualified','card_hash','eligibility_hash'), states)
        return dict(sorted(files.items()))
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ValueError('incomplete or malformed selection render data') from exc



def _render_computation_payloads(computation_bytes):
    """Build six fixed payloads plus audit cards from detached computation bytes.

    Original candidate evidence only: no live coverage, timestamps, run selectors
    or validation signatures are accepted. Release manifest and filesystem commit
    belong to the later authenticated publication boundary.
    """
    import hashlib
    schemas = dict(score_input_batch='policy-adjusted-score-input-batch-v1',
        scorecard_batch='formal-final-score-card-batch-v1',
        eligibility_batch='formal-eligibility-batch-v1', pool_selection_batch='formal-pool-batch-v1')
    if type(computation_bytes) is not dict or set(computation_bytes) != set(schemas):
        raise ValueError('render requires exactly four computation batches')
    try:
        wires = {name: _render_batch(computation_bytes[name], schema) for name,schema in schemas.items()}
        inputs, scores, eligibility, pools = (wires[name] for name in schemas)
        ids = inputs['security_ids']
        if (ids != eligibility['security_ids'] or type(inputs['inputs']) is not list
                or [row['security_id'] for row in inputs['inputs']] != ids
                or scores['source_batch_hash'] != inputs['batch_hash']
                or eligibility['source_batch_hash'] != inputs['batch_hash']):
            raise ValueError('render computation source lineage differs')
        entries = {row['security_id']: row for row in inputs['inputs']}
        for card in scores['cards']:
            if (card['security_id'] not in entries
                    or card['source_entry_hash'] != entries[card['security_id']]['entry_hash']
                    or card['source_batch_hash'] != inputs['batch_hash']):
                raise ValueError('render card input lineage differs')
        files = _render_scorecard_payloads(computation_bytes['scorecard_batch'])
        files.update(_render_selection_payloads(computation_bytes['scorecard_batch'],
            computation_bytes['eligibility_batch'], computation_bytes['pool_selection_batch']))
        evidence = dict(schema='formal-release-evidence-v1', score_inputs=inputs,
            scorecards=scores, classifications=eligibility, pool_selection=pools,
            artifact_hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in computation_bytes.items()})
        files['evidence_manifest.json'] = canonical_release_bytes(evidence)
        counts = dict(universe=len(ids), scorecards=len(scores['cards']),
            formal_scored=sum(row['state']=='formal_scored' for row in eligibility['eligibilities']),
            pool_vetoed=sum(row['state']=='pool_vetoed' for row in eligibility['eligibilities']),
            strong=pools['counts']['strong'], wait=pools['counts']['wait'])
        report = '# Candidate payload quality\n\n'
        report += 'Deterministic candidate counts; this file does not grant publication authority.\n\n'
        report += '| item | count |\n| --- | ---: |\n'
        report += ''.join('| '+name+' | '+str(count)+' |\n' for name,count in counts.items())
        files['quality_report.md'] = report.encode('utf-8')
        return dict(sorted(files.items()))
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ValueError('incomplete or malformed computation render data') from exc


__all__ = []
