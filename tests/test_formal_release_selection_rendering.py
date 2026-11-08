"""Selection rendering uses detached fixtures and confers no release authority."""
import copy
import csv
import io
import unittest
from ashare_pipeline.formal_release_types import canonical_release_bytes
from tests.test_formal_release_rendering import card

IDS = ['BJ430001','SH600001','SZ000001']


def fixture():
    cards = [card(sid) for sid in IDS]
    for index, item in enumerate(cards):
        item['card_hash'] = str(index+1)*64
    scores = dict(schema_version='formal-final-score-card-batch-v1', batch_hash='8'*64, cards=cards)
    eligibility = dict(schema_version='formal-eligibility-batch-v1', batch_hash='9'*64,
        security_ids=IDS, score_batch_hash='8'*64, eligibilities=[dict(
            security_id=item['security_id'], state='formal_scored', reason_codes=[],
            secondary_industry=item['secondary_industry'], card_hash=item['card_hash'],
            eligibility_hash=str(index+4)*64, strong_qualified=index!=1,
            wait_qualified=index==1) for index,item in enumerate(cards)])
    pools = dict(schema_version='formal-pool-batch-v1', source_batch_hash='9'*64,
        security_ids=IDS, strong_security_ids=[IDS[2],IDS[0]], wait_security_ids=[IDS[1]],
        counts={'strong':2,'wait':1}, decisions=[dict(security_id=sid,pool=pool,
            decision='selected' if (pool=='strong') == (index!=1) else 'not_qualified',
            eligibility_hash=str(index+4)*64, decision_hash='7'*64)
            for index,sid in enumerate(IDS) for pool in ('strong','wait')])
    return scores,eligibility,pools


class ReleaseSelectionRenderingTests(unittest.TestCase):
    def render(self, wires=None):
        from ashare_pipeline.formal_release_rendering import _render_selection_payloads
        scores, eligibility, pools = wires or fixture()
        return _render_selection_payloads(canonical_release_bytes(scores),
            canonical_release_bytes(eligibility), canonical_release_bytes(pools))

    def rows(self, files, name):
        return list(csv.DictReader(io.StringIO(files[name].decode('utf-8'))))

    def test_universe_sorted_but_pool_order_is_exact_producer_order(self):
        files=self.render()
        self.assertEqual(set(files), {'universe_status.csv','strong_attention.csv','waiting_price.csv'})
        self.assertEqual([r['security_id'] for r in self.rows(files,'universe_status.csv')], IDS)
        rows=self.rows(files,'strong_attention.csv')
        self.assertEqual([r['security_id'] for r in rows], [IDS[2],IDS[0]])
        self.assertEqual([r['selected_ordinal'] for r in rows], ['1','2'])
        self.assertEqual({r['pool'] for r in rows}, {'strong'})
        self.assertEqual(self.rows(files,'waiting_price.csv')[0]['pool'], 'wait')
        self.assertEqual(rows[0]['Sc'],card()['Sc'])

    def test_zero_pool_outputs_headers_without_backfill(self):
        wires=fixture()
        pools=wires[2]
        pools.update(strong_security_ids=[],wait_security_ids=[],counts={'strong':0,'wait':0})
        for row in pools['decisions']:
            row['decision']='not_qualified'
        files=self.render(wires)
        self.assertEqual(self.rows(files,'strong_attention.csv'), [])
        self.assertEqual(self.rows(files,'waiting_price.csv'), [])
        self.assertEqual(len(self.rows(files,'universe_status.csv')),3)

    def test_duplicate_missing_and_foreign_members_rejected(self):
        for mutation in ('duplicate','missing','foreign'):
            wires=fixture()
            if mutation=='duplicate':
                wires[1]['eligibilities'].append(copy.deepcopy(wires[1]['eligibilities'][0]))
            elif mutation=='missing':
                wires[1]['eligibilities'].pop()
            else:
                wires[2]['strong_security_ids'][0]='SH600099'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(wires)

    def test_pending_or_out_of_scope_cannot_be_published(self):
        for state in ('pending_evidence','out_of_scope','unknown'):
            wires=fixture()
            wires[1]['eligibilities'][0]['state']=state
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.render(wires)

    def test_pool_overlap_and_count_mismatch_rejected(self):
        for mutation in ('overlap','count','bool_count'):
            wires=fixture()
            if mutation=='overlap':
                wires[2]['wait_security_ids']=[IDS[0]]
            else:
                wires[2]['counts']['wait']=2 if mutation=='count' else True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(wires)

    def test_selected_decision_missing_or_rebound_is_rejected(self):
        for mutation in ('missing','status','hash'):
            wires=fixture()
            row=wires[2]['decisions'][0]
            if mutation=='missing':
                wires[2]['decisions'].pop(0)
            elif mutation=='status':
                row['decision']='not_qualified'
            else:
                row['eligibility_hash']='f'*64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(wires)

    def test_card_and_batch_lineage_must_match(self):
        for mutation in ('card','scores','eligibility'):
            wires=fixture()
            if mutation=='card':
                wires[1]['eligibilities'][0]['card_hash']='f'*64
            elif mutation=='scores':
                wires[1]['score_batch_hash']='f'*64
            else:
                wires[2]['source_batch_hash']='f'*64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(wires)

    def test_unqualified_or_vetoed_member_cannot_be_selected(self):
        for mutation in ('flag','state'):
            wires=fixture()
            if mutation=='flag':
                wires[1]['eligibilities'][0]['strong_qualified']=False
            else:
                wires[1]['eligibilities'][0]['state']='pool_vetoed'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(wires)

    def large_fixture(self, pool, count, industry_count):
        scores, eligibility, pools = fixture()
        ids = ['SH'+str(600000+i) for i in range(count)]
        scores['cards']=[]
        eligibility.update(security_ids=ids, eligibilities=[])
        pools.update(security_ids=ids, strong_security_ids=ids if pool=='strong' else [],
            wait_security_ids=ids if pool=='wait' else [],
            counts={'strong':count if pool=='strong' else 0,'wait':count if pool=='wait' else 0}, decisions=[])
        for index,sid in enumerate(ids):
            item=card(sid)
            item['secondary_industry']='industry-'+str(index%industry_count)
            scores['cards'].append(item)
            eligibility['eligibilities'].append(dict(security_id=sid,state='formal_scored',
                reason_codes=[],secondary_industry=item['secondary_industry'],card_hash=item['card_hash'],
                eligibility_hash='4'*64,strong_qualified=pool=='strong',wait_qualified=pool=='wait'))
            for kind in ('strong','wait'):
                pools['decisions'].append(dict(security_id=sid,pool=kind,
                    decision='selected' if kind==pool else 'not_qualified',
                    eligibility_hash='4'*64,decision_hash='7'*64))
        return scores,eligibility,pools

    def test_exact_overall_and_industry_caps_are_allowed(self):
        for pool,count in (('strong',20),('wait',50)):
            with self.subTest(pool=pool):
                files=self.render(self.large_fixture(pool,count,5))
                name='strong_attention.csv' if pool=='strong' else 'waiting_price.csv'
                self.assertEqual(len(self.rows(files,name)),count)

    def test_excess_overall_or_industry_capacity_is_rejected(self):
        for pool,count,industries in (('strong',21,21),('wait',51,51),('strong',5,1),('wait',11,1)):
            with self.subTest(pool=pool,count=count), self.assertRaises(ValueError):
                self.render(self.large_fixture(pool,count,industries))

    def test_unknown_nonselected_decision_is_rejected(self):
        wires=fixture()
        wires[2]['decisions'][1]['decision']='unknown'
        with self.assertRaises(ValueError):
            self.render(wires)


class ReleasePayloadAssemblyTests(unittest.TestCase):
    def data(self):
        scores, eligibility, pools=fixture()
        scores['source_batch_hash']='c'*64
        eligibility['source_batch_hash']='c'*64
        inputs=dict(schema_version='policy-adjusted-score-input-batch-v1',batch_hash='c'*64,
            security_ids=IDS, inputs=[dict(item['source_input'],security_id=item['security_id'],
                entry_hash=item['source_entry_hash']) for item in scores['cards']])
        return {name:canonical_release_bytes(value) for name,value in zip(
            ('score_input_batch','scorecard_batch','eligibility_batch','pool_selection_batch'),
            (inputs,scores,eligibility,pools))}

    def test_complete_fixed_payload_set_and_original_evidence(self):
        import json
        from ashare_pipeline.formal_release_rendering import _render_computation_payloads
        data=self.data()
        files=_render_computation_payloads(data)
        expected={'scores.csv','universe_status.csv','strong_attention.csv','waiting_price.csv',
                  'evidence_manifest.json','quality_report.md'}|{'audit_cards/'+sid+'.json' for sid in IDS}
        self.assertEqual(set(files),expected)
        evidence=json.loads(files['evidence_manifest.json'])
        self.assertEqual(evidence['score_inputs'],json.loads(data['score_input_batch']))
        self.assertEqual(evidence['pool_selection'],json.loads(data['pool_selection_batch']))
        self.assertEqual(files,_render_computation_payloads(dict(reversed(list(data.items())))))
        self.assertIn(b'| strong | 2 |',files['quality_report.md'])
        self.assertIn(b'| wait | 1 |',files['quality_report.md'])

    def test_missing_extra_or_rebound_computation_rejected(self):
        import json
        from ashare_pipeline.formal_release_rendering import _render_computation_payloads
        for mutation in ('missing','extra','binding'):
            data=self.data()
            if mutation=='missing':
                data.pop('score_input_batch')
            elif mutation=='extra':
                data['coverage_manifest']=b'{}'
            else:
                value=json.loads(data['score_input_batch'])
                value['batch_hash']='f'*64
                data['score_input_batch']=canonical_release_bytes(value)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                _render_computation_payloads(data)
