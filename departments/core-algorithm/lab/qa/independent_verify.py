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
    check('S03_29_distinct_cases',len(data['cases'])==29 and len(set(x['id'] for x in data['cases']))==29)
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
    check('S05_all_28_run_chains',len(valid_chains)==28 and all(valid_chains))
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
    # Implementation versions (rung L1): proposal-only, right shape, hash-stable, never marked executed.
    for key,label in (('implementation','S32'),('implementation_enquiry','S33'),('implementation_website','S38')):
        impl=meta.get(key) or {}
        wf=impl.get('workflow',{})
        shape=all(k in wf for k in ('id','name','version','source','trigger','steps','verify','enforcement'))
        steps_ok=len(wf.get('steps',[]))==len(impl.get('plan',{}).get('actions',[]))+2 and all(s.get('sandbox')=='local-model-only' for s in wf.get('steps',[]) if s.get('method'))
        proposed=impl.get('status')=='PROPOSED_ONLY' and 'PROPOSED_ONLY' in str(wf.get('enforcement',{}).get('current','')) and all(a.get('status')=='open' and a.get('verify',{}).get('met') is False for a in impl.get('atoms',[]))
        stable=impl.get('implementation_sha256')==sha({k:v for k,v in impl.items() if k not in ('ui','ui_sha256','implementation_sha256')}) and impl.get('ui_sha256')==sha(impl.get('ui'))
        check(label+'_'+key+'_proposal_only_right_shape',shape and steps_ok and proposed and stable)
    # Deliberate negative: verifier must reject forged edits without breaking JSON shape.
    test_case=next(x for x in data['cases'] if x['id']=='04_gates')
    forged=json.loads(json.dumps(test_case['outcome']['trace']))
    forged[2]['operation']='FORGED_SUCCESS'
    check('S31_reject_tampered_event',not check_chain(forged))
    # 0.4.0-shrink (move-out M1): learning is an extension over the record; the kernel source carries none of it.
    core_src=(ROOT/'kernel'/'core.py').read_text()
    check('S34_kernel_source_without_learning',all(w not in core_src for w in ('REUSE_COMPOSITION','INVESTIGATE_GAP','learned_signatures','LEARN_CANDIDATE')))
    learned={c['id']:c['outcome']['learning'] for c in data['cases'] if c['outcome']}
    check('S35_learning_recorded_from_extension',learned['05_learn']==[{'kind':'REUSE_COMPOSITION','signature':'ship-replacement@1','observations':1,'status':'PROPOSED_ONLY','gate':'independent held-out verification + approval'}]
          and learned['07_gap'][0]['kind']=='INVESTIGATE_GAP' and learned['04_gates']==[]
          and all(x['kind'] in ('REUSE_COMPOSITION','INVESTIGATE_GAP') for v in learned.values() for x in v))
    # Each learning list is bound to the kernel's hash-chained record: trace root + sha256 of the list.
    check('S36_learning_bound_to_trace_root',all(c['outcome'].get('learning_record')=={'source_trace':c['outcome']['trace_root_sha256'],'learning_sha256':sha(c['outcome']['learning'])} for c in data['cases'] if c['outcome']))
    # 0.5.0-standards: the failed standard rests on adapter evidence; the repair is one reviewed method; generated work passes on evidence alone.
    world={w['predicate']:w for w in m['25_registrable_gap']['four_views']['world']}
    finding=world.get('sutra/workflows|every_step_has_check',{})
    check('S37_standard_from_adapter_evidence',status('25_registrable_gap')=='METHOD_ABSENT' and finding.get('truth')=='FALSE' and str(finding.get('source','')).startswith('adapter:standards/')
          and m['26_registrable_repair']['outcome']['actions']==['add-step-checks@1']
          and status('27_registrable_generated')=='SUPPORTED_BY_EVIDENCE' and not m['27_registrable_generated']['outcome']['actions'] and not m['27_registrable_generated']['outcome']['model_receipts'])
    # 0.6.0-order: in the website implementation every edge runs forward and every prerequisite is a step of the plan.
    site=meta['implementation_website']['workflow'];where={s['id']:i for i,s in enumerate(site['steps'])}
    check('S39_website_edges_run_forward',len(site['edges'])==4 and all(e['from'] in where and e['to'] in where and where[e['from']]<where[e['to']] for e in site['edges'])
          and all(set(s.get('after',[]))=={e['from'] for e in site['edges'] if e['to']==s['id']} for s in site['steps'] if s.get('method'))
          and m['28_website']['outcome']['actions']==['plan-site@1','write-content@1','build-pages@1','check-site@1'])
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
