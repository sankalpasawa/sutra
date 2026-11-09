"""Independent local trace and artifact verifier. MUST NOT import kernel/core or extensions."""
from __future__ import annotations
import json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'results'/'actual_run_records.json'

def sha(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def check_chain(trace):
    for i,row in enumerate(trace):
        if row['seq']!=i+1:return False
        if row['prev_sha256'] != (trace[i-1]['sha256'] if i else 'GENESIS'):return False
        if row['sha256']!=sha({k:v for k,v in row.items() if k!='sha256'}):return False
    return True

def inspect(data):
    tests=[]
    def check(id,ok,detail=''):
        tests.append({'id':id,'pass':bool(ok),'detail':detail})
    h=hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest()
    check('S01_source_hash_current',data['kernel_sha256']==h)
    baseline=hashlib.sha256((ROOT/'release'/'baseline_v0_1_core.py').read_bytes()).hexdigest()
    check('S02_old_baseline_immutable',data['baseline_v0_1_sha256']==baseline and baseline.startswith('c5a86c28aac'))
    check('S03_25_distinct_cases',len(data['cases'])==25 and len(set(x['id'] for x in data['cases']))==25)
    valid_chains=[];all_model_only=True;all_costs_ok=True;all_governed=True;valid_packs=[]
    for case in data['cases']:
        pack_objs=[json.loads((ROOT/'scenarios'/(n+'.json')).read_text()) for n in case['packs']]
        valid_packs.append(case['pack_digest']==sha(pack_objs))
        outcome=case['outcome']
        if outcome:
            valid_chains.append(check_chain(outcome['trace']) and outcome['trace_root_sha256']==outcome['trace'][-1]['sha256'])
            all_model_only &= all(x['status']=='LOCAL_ONLY' for x in outcome['model_receipts'])
            all_model_only &= 'never external success' in outcome['claim']
            if outcome['cost']:
                for d,cost in outcome['cost'].items():
                    all_costs_ok &= cost>=0
            all_governed &= all(c['status']=='PROPOSED_ONLY' for c in outcome['candidates'])
            all_governed &= all(c['status']=='PROPOSED_ONLY' for c in outcome['learning'])
    check('S04_all_pack_sha_match',all(valid_packs))
    check('S05_all_24_run_chains',len(valid_chains)==24 and all(valid_chains))
    check('S06_receipts_local_only',all_model_only)
    check('S07_all_plan_costs_nonnegative',all_costs_ok)
    check('S08_all_candidates_proposed_only',all_governed)
    m={c['id']:c for c in data['cases']}
    def status(cid):return m[cid]['outcome']['status'] if m[cid]['outcome'] else m[cid]['run']['status']
    check('S09_missing_semantics_honest',status('00_goal')=='SEMANTICS_MISSING')
    check('S10_unknown_approval_honest',status('02_methods')=='QUERY_EVIDENCE')
    check('S11_authority_gate',status('03_evidence')=='AUTHORITY_REQUIRED' and not m['03_evidence']['outcome']['actions'])
    check('S12_added_notification_is_action',m['06_nuance']['outcome']['actions']==['ship-replacement@1','notify-customer@1'])
    check('S13_missing_method_and_recovery',status('07_gap')=='METHOD_ABSENT' and 'record-survey@1' in m['08_method_added']['outcome']['actions'])
    check('S14_pareto_policy_flip',m['09_pareto']['outcome']['actions']==['ship-fast@1'] and m['10_preference']['outcome']['actions']==['ship-economy@1'])
    check('S15_new_domain_methods',m['12_enquiry']['outcome']['actions']==['store-enquiry@1','readback-enquiry@1'])
    check('S16_construct_candidate_only',m['15_constructor']['outcome']['candidates'][0]['status']=='PROPOSED_ONLY' and m['15_constructor']['outcome']['candidates'][0]['valid_contract'])
    check('S17_reject_bad_contract',not m['16_bad_constructor']['outcome']['candidates'][0]['valid_contract'])
    check('S18_no_spurious_self_authority',status('18_self_need')=='AUTHORITY_REQUIRED')
    check('S19_tenant_isolation',status('20_wrong_tenant')=='QUERY_EVIDENCE')
    check('S20_no_standing_no_trigger',status('21_no_goal')=='NO_STANDING_GOAL')
    check('S21_capacity_denied',status('23_capacity')=='PROVIDER_REQUIRED')
    check('S22_resources_denied',status('24_budget')=='RESOURCE_REQUIRED')
    ev=data['events']
    check('S23_unrelated_no_recompute',not ev['unrelated']['affected'] and not ev['cross_tenant']['affected'])
    check('S24_relevant_recompute',ev['approval_revoked']['affected']==['order_complete'])
    check('S25_dep_invalidation',ev['impacted_fact_after_revoke']['truth']=='UNKNOWN')
    check('S26_immutable_previous_run',ev['old_trace_hash_before']==ev['old_trace_hash_after'])
    meta=data['meta_extensions']
    check('S27_reviewed_semantics_only',not meta['knowledge_compiler']['unreviewed_rule']['rules'][0]['approved'] and meta['knowledge_compiler']['reviewed_rule']['rules'][0]['approved'])
    check('S28_reflection_no_promotions',all(x['status']=='PROPOSED_ONLY' for x in meta['reflection']['candidates']))
    check('S29_j2_projection_not_closed',all(x['status']=='open' for x in meta['j2_projection']['atoms']))
    check('S30_design_diff',meta['graph_diff_nuance']['added']==['notify-customer@1'])
    # Deliberate negative: verifier must reject forged edits without breaking JSON shape.
    test_case=next(x for x in data['cases'] if x['id']=='04_gates')
    forged=json.loads(json.dumps(test_case['outcome']['trace']))
    forged[2]['operation']='FORGED_SUCCESS'
    check('S31_reject_tampered_event',not check_chain(forged))
    valid=all(t['pass'] for t in tests)
    return {'verifier':'independent_verify.py: pure JSON/hash verifier, never imports kernel',
            'checks':tests,'passed':sum(t['pass'] for t in tests),'total':len(tests),
            'pass':valid,'claims':'synthetic record consistency only; not external effect verification or J2 integration'}

if __name__=='__main__':
    data=json.loads(DATA.read_text());result=inspect(data)
    (ROOT/'qa'/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['passed'],'/',result['total'],'independent local checks', 'PASS' if result['pass'] else 'FAIL')
    for r in result['checks']:
        if not r['pass']:print('FAIL',r)
    sys.exit(0 if result['pass'] else 1)
