"""Rendering tests use data-only cards, not authenticated scoring proofs."""
import csv
import io
import json
import unittest
from ashare_pipeline.formal_release_types import canonical_release_bytes


def card(sid='SH600001'):
    dimensions = {key: '80.12345678901234567890123456789' for key in ('G','V','M','EQ','FS','CA','T')}
    result = dict(schema_version='formal-final-score-card-v1', security_id=sid,
        template_id='industrial', primary_industry='制造业', secondary_industry='设备,"精密"',
        dimensions=dimensions, dimension_grades={key:'A' for key in dimensions},
        confidence={'C':'0.90'}, risk_exposure='20', card_hash='a'*64,
        source_entry_hash='b'*64, source_batch_hash='c'*64,
        source_input={'slots': {'G.growth': {'metric_score': {'context_hash':'d'*64},
                                          'evidence_refs':[{'source_hash':'e'*64}]}}},
        cap_trace=[{'reason':'test cap'}])
    for key in ('S0','Sc','Sbase','B','M_persistence','CA_downside','R_safety'):
        result[key] = '80.12345678901234567890123456789'
        result[key+'_grade'] = 'A'
    return result


class ReleaseScoreRenderingTests(unittest.TestCase):
    def render(self, cards):
        from ashare_pipeline.formal_release_rendering import _render_scorecard_payloads
        return _render_scorecard_payloads(canonical_release_bytes(dict(
            schema_version='formal-final-score-card-batch-v1', cards=cards)))

    def test_exact_decimal_columns_utf8_lf_and_complete_audit(self):
        original = card()
        files = self.render([original])
        raw = files['scores.csv']
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r', raw)
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8')))
        rows = list(reader)
        self.assertEqual(reader.fieldnames[:4], ['security_id','template_id','primary_industry','secondary_industry'])
        for key in ('G','V','M','EQ','FS','CA','T','Sc'):
            self.assertEqual(rows[0][key], '80.12345678901234567890123456789')
        self.assertEqual(rows[0]['secondary_industry'], original['secondary_industry'])
        self.assertEqual(json.loads(files['audit_cards/SH600001.json']), original)
        self.assertEqual(json.loads(rows[0]['cohort_references'])['G.growth']['metric_score'],
                         original['source_input']['slots']['G.growth']['metric_score'])

    def test_security_order_is_deterministic_and_results_are_detached(self):
        first = self.render([card('SZ000001'), card('BJ430001')])
        second = self.render([card('BJ430001'), card('SZ000001')])
        self.assertEqual(first, second)
        rows=list(csv.DictReader(io.StringIO(first['scores.csv'].decode())))
        self.assertEqual([row['security_id'] for row in rows], ['BJ430001','SZ000001'])
        first.clear()
        self.assertEqual(self.render([card('BJ430001'),card('SZ000001')]), second)

    def test_missing_dimension_or_grade_cannot_be_blank_or_defaulted(self):
        for field in ('dimensions','dimension_grades'):
            item=card()
            del item[field]['EQ']
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.render([item])

    def test_missing_lineage_or_score_is_rejected(self):
        for field in ('source_input','source_entry_hash','Sc','R_safety_grade'):
            item=card()
            del item[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.render([item])

    def test_duplicate_and_unsafe_security_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            self.render([card(),card()])
        for sid in ('../SH600001','SH600001/other','sh600001','SH600001.json'):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                self.render([card(sid)])

    def test_nonfinite_and_out_of_range_values_are_rejected(self):
        for value in ('NaN','Infinity','-1','101'):
            item=card()
            item['Sc']=value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.render([item])
        item=card()
        item['confidence']['C']='1.01'
        with self.assertRaises(ValueError):
            self.render([item])

    def test_noncanonical_and_duplicate_key_json_are_rejected(self):
        from ashare_pipeline.formal_release_rendering import _render_scorecard_payloads
        for raw in (b'{ "cards": []}',b'{"cards":[],"cards":[]}',b'{"cards":[],"x":1.5}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                _render_scorecard_payloads(raw)

    def test_empty_scores_emit_header_and_no_audit_cards(self):
        files=self.render([])
        self.assertEqual(set(files), {'scores.csv'})
        self.assertEqual(len(files['scores.csv'].splitlines()), 1)
