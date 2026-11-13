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
    check('S03_30_distinct_cases',len(data['cases'])==30 and len(set(x['id'] for x in data['cases']))==30)
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
    check('S05_all_29_run_chains',len(valid_chains)==29 and all(valid_chains))
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
    # 0.7.0-handlers: the kernel names no constructor or artifact kind; the code that performs effects is recorded by sha.
    check('S40_kernel_source_without_moved_kinds',all(w not in core_src for w in ('compile_candidate','emit_artifact','LOCAL_ARTIFACT','valid_contract')))
    handlers=data.get('action_handlers',{})
    check('S41_action_handlers_recorded_by_sha',set(handlers)=={'simulate_fact','compile_candidate','emit_artifact','ask'} and handlers['simulate_fact']['file']=='kernel/core.py'
          and all(hashlib.sha256((ROOT/h['file']).read_bytes()).hexdigest()==h['sha256'] for h in handlers.values()))
    # 0.8.0-ask. Every recorded run is compared with its own trace (status, work state, goal, scope, stop reasons, the selection,
    # actions, skipped steps, cost, receipts; a run that says effects were recorded has receipts, a plan that ran nothing has none),
    # with the packs it says it loaded (each pack's sha against its file; every step is a method of one of them, at that pack's cost;
    # a case's run loaded the case's packs) and with the kernel's claim sentence, word for word; a case's run is recorded twice and
    # both copies are compared, and so are the viewer's copies of its actions and trace; numbers are compared as JSON (1 is not true)
    # in a run's cost, in the ask record's snapshots, in the stamp's event and in case 29's budget_after. NOT checked here: what a trace
    # does not carry (needs, proof, branch, the truth of the goal); the type of a trace row's seq and of pareto_options (they are compared
    # by value, so true passes for 1); whether a blocked run's reason is one of the stop reasons (the run is compared with its BLOCK row,
    # the BLOCK row with nothing); trace rows that no check reads (an ADMISSION row's own fields); a run's candidates and learning; a key
    # added to a run; the viewer's world and knowledge views; a case's title, description, area, scope, its run block's own status and
    # goals, and its derived state (budget_after is checked for case 29 only); the order of the packs an event-block run names, and a pack
    # among them that no step needs; the release label; and an event block's own status, goals and counts beyond what S43 to S47 read.
    # The ask record must show: asked once, nothing
    # shipped, charged once; yes resumes; no is final; another route leaves the question answerable. S48 shows the same
    # claims fail on forged records.
    packs={p['id']:p for p in (json.loads(f.read_text()) for f in sorted((ROOT/'scenarios').glob('*.json')))}
    methods={mth['id']:mth for p in packs.values() for mth in p.get('methods',[])}   # every method of every pack file: the ask books below read their costs here
    CLAIM='LOCAL_REFERENCE_ONLY; never external success or current J2 implementation'   # the kernel's sentence, word for word
    def table(r):   # the methods of the packs this run says it loaded; a pack that is not its file gives no table
        if any(p['pack'] not in packs or sha(packs[p['pack']])!=p['sha256'] for p in r['provenance']):return None
        return {mth['id']:mth for p in r['provenance'] for mth in packs[p['pack']].get('methods',[])}
    rsha=lambda r:sha({k:v for k,v in r.items() if k!='sha256'});same=lambda a,b:sha(a)==sha(b)   # numbers are compared as JSON: 1 is not true and not 1.0
    def run_ok(r):
        t=r['trace'];last=t[-1];receipts=[e['data']['receipt'] for e in t if e['operation']=='LOCAL_EFFECT']
        chosen=[e['data'] for e in t if e['operation']=='SELECT'];skips=[e['data']['method'] for e in t if e['operation']=='STEP_ALREADY_TRUE'];block=[e['data'] for e in t if e['operation']=='BLOCK'];waiting=r['work_state']=='waiting'
        mt=table(r);total=lambda acts:{d:sum(mt[a].get('cost',{}).get(d,0) for a in acts) for d in chosen[0]['full_cost']}
        return (check_chain(t) and same(r.get('claim'),CLAIM) and mt is not None and r['trace_root_sha256']==last['sha256'] and last['operation']=='TERMINAL' and last['data']=={'status':r['status'],'work_state':r['work_state']}
                and t[0]['operation']=='GOAL_ACCEPTED' and t[0]['data']=={'goal':r['goal'],'scope':r['scope']}
                and same(receipts,r['model_receipts']) and all(x['sha256']==rsha(x) and x['status']=='LOCAL_ONLY' for x in receipts)
                and len(chosen)+len(block)==1 and ('waits' in r)==waiting and ('pending' in r)==waiting
                and ((r['status'],r['stop_reasons'],r['actions'],r['cost'],r['work_state'],receipts)==(block[0]['reason'],block[0]['all_reasons'],[],None,'blocked',[]) and same(r['pareto_options'],0) and not skips and 'skipped' not in r if block else
                     r['stop_reasons']==[] and same(r['pareto_options'],chosen[0]['pareto_options']) and [a for a in chosen[0]['actions'] if a not in skips]==r['actions']+r.get('pending',[]) and r.get('skipped',[])==skips and ('skipped' in r)==bool(skips) and set(skips)<=set(chosen[0]['actions'])
                     and set(chosen[0]['actions'])<=set(mt) and same(total(chosen[0]['actions']),chosen[0]['full_cost']) and same(r['cost'],total(r['actions'])) and [x['method'] for x in receipts]==(r['actions'] if r['work_state']!='ready' else [])
                     and r['status']=={'ready':'PLAN_READY','waiting':'WAITING','completed':'LOCAL_MODEL_EFFECTS_RECORDED' if receipts else 'SUPPORTED_BY_EVIDENCE'}.get(r['work_state'])
                     and (not waiting or (r['status']=='WAITING' and (r['waits']==[receipts[-1]['method']] and receipts[-1].get('parked') is True if receipts else r['actions']==[] and chosen[0].get('waits')==r['waits'])))))
    def every_run(d):
        for c in d['cases']:
            if c['outcome']:yield c['outcome']
            yield from c['run']['runs']   # the same run as recorded under the case's run block: both copies are compared with their trace
        for block in ('events','ask_events'):
            for value in d[block].values():
                if isinstance(value,dict) and 'runs' in value:yield from value['runs']
    def runs_ok(d):   # every run agrees with its trace; the two copies of a case's run are one run; the run that skipped two steps says so in its result and in its chain
        made=d['ask_events']['made_again']['runs'][0];rows=[e['data'] for e in made['trace'] if e['operation']=='STEP_ALREADY_TRUE']
        return (all(run_ok(r) for r in every_run(d)) and all(same(c['outcome'],c['run']['runs'][0] if c['run']['runs'] else None) and same([c['four_views']['design'],c['four_views']['run']],[(c['outcome'] or {}).get('actions',[]),(c['outcome'] or {}).get('trace',[])])
                                                         and (not c['outcome'] or [p['pack'] for p in c['outcome']['provenance']]==c['packs']) for c in d['cases'])
                and (made['status'],made['actions'],made.get('skipped'))==('LOCAL_MODEL_EFFECTS_RECORDED',['prepare-quote@1'],['assume-approval@1','ship-quoted@1'])
                and [(x['method'],x['effect'],x['source']) for x in rows]==[('assume-approval@1','quote_approved','LOCAL_MODEL:assume-approval@1'),('ship-quoted@1','order_shipped','LOCAL_MODEL:ship-quoted@1')])
    def ask_claims(d):
        if not runs_ok(d):return {'runs':False}
        case=[c for c in d['cases'] if c['id']=='29_ask'][0];asked=case['outcome'];ae=d['ask_events'];run=lambda key:ae[key]['runs'][0]
        budget={'compute':10,'money':10,'attention':3};slots={'local-provider':5,'owner-channel':2};ASKED,SHIP='ask-customer-approval@1','ship-replacement@1'
        def books(keys):   # the budget and the provider slots after the runs named, recomputed from the receipts and the pack files
            b,p=dict(budget),dict(slots)
            for key in keys:
                for x in run(key)['model_receipts']:
                    p[methods[x['method']]['provider']]-=1
                    for dim,v in methods[x['method']].get('cost',{}).items():b[dim]-=v
            return {'budget':b,'providers':p}
        def snap_ok(name,keys,open_receipt):
            snap=ae[name];want=books(keys)
            return same(snap['budget'],want['budget']) and same(snap['providers'],want['providers']) and same(snap['open_asks'],{'orgA/fulfillment|customer_approved':{'method':ASKED,'receipt':open_receipt['sha256'],'issued':open_receipt}} if open_receipt else {})
        def parked(r):
            return (r['status'],r['work_state'],r['actions'],r['pending'],r['waits'],r['goal_truth_after'],r['cost'])==('WAITING','waiting',[ASKED],[SHIP],[ASKED],'UNKNOWN',{'compute':0,'money':0,'attention':1})
        def waits(r):
            return (r['status'],r['work_state'],r['actions'],r['pending'],r['waits'],r['model_receipts'],r['cost'])==('WAITING','waiting',[],[SHIP],[ASKED],[],{'compute':0,'money':0,'attention':0})
        def stamp(key,first,truth):
            issued=run(first)['model_receipts'][0];top=ae[key]
            return (top['status'],top['affected'],len(top['runs']))==('RECONCILED',['order_complete'],1) and same(top['event'],{'predicate':'customer_approved','truth':truth,'verified':True,'final':True,
                    'source':'STAMP:'+issued['ask']['to'],'version':'ask-'+issued['sha256'][:12],'answers':issued['sha256'],'scope':issued['scope']})
        row=lambda r,op:[e['data'] for e in r['trace'] if e['operation']==op]
        first,yes,no,other=run('first'),run('answered_yes'),run('answered_no'),run('other_route');issued=first['model_receipts'][0]
        return {
         'S43_ask_parks_and_ships_nothing':parked(asked) and len(asked['model_receipts'])==1 and asked['model_receipts'][0]['ask']['to']=='customer'
          and same(case['derived_state']['budget_after'],books(['first'])['budget']) and all(parked(run(key)) for key in ('first','first_no','first_other')),
         'S44_open_ask_is_idempotent':waits(run('again')) and waits(run('unrelated')) and snap_ok('after_first',['first'],issued) and snap_ok('after_again',['first','again'],issued)
          and snap_ok('after_unrelated',['first','again','unrelated'],issued),
         'S45_yes_resumes_no_is_final':(yes['status'],yes['work_state'],yes['actions'])==('LOCAL_MODEL_EFFECTS_RECORDED','completed',[SHIP])
          and {'predicate':'customer_approved','source':'STAMP:customer','version':'ask-'+issued['sha256'][:12]} in row(yes,'RETAIN')
          and [x['receipt'] for x in row(yes,'ASK_CLOSED')]==[issued['sha256']] and snap_ok('after_yes',['first','again','unrelated','answered_yes'],None)
          and all((run(key)['status'],run(key)['work_state'],run(key)['actions'],run(key)['model_receipts'],run(key)['stop_reasons'])==('REFUSED','blocked',[],[],['METHOD_ABSENT','REFUSED'])
                  and {'predicate':'customer_approved','source':'STAMP:customer'} in row(run(key),'REFUSED') for key in ('answered_no','no_again'))
          and snap_ok('after_first_no',['first_no'],run('first_no')['model_receipts'][0]) and snap_ok('after_no',['first_no','answered_no'],None) and snap_ok('after_no_again',['first_no','answered_no','no_again'],None),
         'S46_another_route_leaves_the_question_answerable':(other['status'],other['work_state'],other['actions'])==('LOCAL_MODEL_EFFECTS_RECORDED','completed',['ship-original@1'])
          and snap_ok('after_first_other',['first_other'],run('first_other')['model_receipts'][0]) and snap_ok('after_other',['first_other','other_route'],run('first_other')['model_receipts'][0])
          and (ae['other_route']['status'],ae['other_route']['affected'],ae['other_route']['event']['predicate'])==('RECONCILED',['order_complete'],'original_stock'),
         'S47_stamp_cites_the_issued_receipt':stamp('answered_yes','first','TRUE') and stamp('answered_no','first_no','FALSE')
          and (ae['unrelated']['status'],ae['unrelated']['event']['predicate'])==('RECONCILED','substitute_stock')}
    claims=ask_claims(data)
    check('S42_every_run_agrees_with_its_trace_and_packs',runs_ok(data))
    for name,ok in claims.items():
        if name!='runs':check(name,ok)
    # The same claims must fail on a falsified record: forgeries of this very record, each changing one thing (two change it in several places at once).
    def falsified(change):
        d=json.loads(json.dumps(data));change(d)
        try:return not all(ask_claims(d).values())
        except Exception:return True
    c29=lambda d:[c for c in d['cases'] if c['id']=='29_ask'][0];r0=lambda d,key:d['ask_events'][key]['runs'][0];ev=lambda d,key:d['ask_events'][key]
    def retold(cid,status,work):   # a case's run re-chained to end with another status and work state: both copies of the run and the viewer's copy of its trace
        def change(d):
            c=[c for c in d['cases'] if c['id']==cid][0]
            for r in (c['outcome'],c['run']['runs'][0]):
                last=r['trace'][-1];last['data']={'status':status,'work_state':work};last['sha256']=sha({k:v for k,v in last.items() if k!='sha256'})
                r.update(status=status,work_state=work,trace_root_sha256=last['sha256'])
            c['four_views']['run']=c['outcome']['trace']
        return change
    forgeries=[lambda d:c29(d)['outcome']['model_receipts'][0].update(sha256='0'*64),
               lambda d:c29(d)['outcome']['model_receipts'][0]['ask'].update(to='mallory'),
               lambda d:c29(d)['outcome'].update(waits=['ship-replacement@1']),
               lambda d:c29(d)['derived_state']['budget_after'].update(attention=3),
               lambda d:[ev(d,k)['budget'].update(attention=3) for k in ('after_first','after_again','after_unrelated')],
               lambda d:ev(d,'after_yes')['budget'].update(attention=0),
               lambda d:ev(d,'after_yes')['providers'].update({'owner-channel':0}),
               lambda d:ev(d,'after_other')['budget'].update(money=10),
               lambda d:ev(d,'after_no_again')['budget'].update(attention=1),
               lambda d:ev(d,'after_first_no')['open_asks']['orgA/fulfillment|customer_approved'].update(method='ship-replacement@1'),
               lambda d:ev(d,'after_yes')['open_asks'].update(left={'method':'x','receipt':'y'}),
               lambda d:r0(d,'answered_yes').update(status='PLAN_READY',model_receipts=[]),
               lambda d:r0(d,'answered_yes').update(work_state='waiting'),
               lambda d:r0(d,'answered_no').update(actions=['ship-replacement@1']),
               lambda d:r0(d,'answered_no').update(stop_reasons=['REFUSED']),
               lambda d:r0(d,'no_again').update(status='WAITING'),
               lambda d:r0(d,'no_again').update(pending=['ship-replacement@1']),
               lambda d:r0(d,'again').update(model_receipts=[dict(r0(d,'first')['model_receipts'][0])]),
               lambda d:r0(d,'again').update(cost={'compute':0,'money':0,'attention':1}),
               lambda d:r0(d,'again').update(waits=[]),
               lambda d:r0(d,'first').update(pending=[]),
               lambda d:r0(d,'first').update(cost={'compute':0,'money':0,'attention':0}),
               lambda d:r0(d,'first_other').update(status='PLAN_READY'),
               lambda d:r0(d,'other_route').update(status='WAITING'),
               lambda d:r0(d,'other_route')['trace'].pop(-2),
               lambda d:ev(d,'answered_no')['event'].update(answers='0'*64),
               lambda d:ev(d,'answered_yes')['event'].update(predicate='substitute_stock'),
               lambda d:ev(d,'answered_yes')['event'].update(scope='orgB/fulfillment'),
               lambda d:ev(d,'answered_yes')['event'].update(verified=False),
               lambda d:ev(d,'answered_yes')['event'].update(version='ask-000000000000'),
               lambda d:ev(d,'answered_yes')['event'].update(depends_on=[{'predicate':'x','version':'1'}]),
               lambda d:ev(d,'answered_yes').update(status='OUT_OF_SCOPE'),
               lambda d:ev(d,'answered_no').update(affected=[]),
               lambda d:ev(d,'unrelated')['event'].update(predicate='customer_approved'),
               lambda d:[c for c in d['cases'] if c['id']=='04_gates'][0]['outcome'].update(status='PLAN_READY'),
               lambda d:[c for c in d['cases'] if c['id']=='06_nuance'][0]['outcome']['cost'].update(money=0),
               lambda d:ev(d,'after_first')['open_asks']['orgA/fulfillment|customer_approved']['issued']['ask'].update(to='mallory'),
               lambda d:r0(d,'first').update(goal='another_goal'),
               lambda d:r0(d,'again').update(scope='orgB/fulfillment'),
               lambda d:r0(d,'answered_yes').update(waits=['ask-customer-approval@1']),
               lambda d:r0(d,'answered_yes').update(pareto_options=9),
               lambda d:r0(d,'no_again').update(stop_reasons=['NOT_A_REASON']),
               lambda d:[c for c in d['cases'] if c['id']=='02_methods'][0]['outcome'].update(actions=['ship-replacement@1']),
               lambda d:[c for c in d['cases'] if c['id']=='02_methods'][0]['outcome'].update(stop_reasons=['NOT_A_REASON']),
               lambda d:[c for c in d['cases'] if c['id']=='04_gates'][0]['outcome'].update(stop_reasons=['NOT_A_REASON']),
               lambda d:[c for c in d['cases'] if c['id']=='06_nuance'][0]['outcome'].update(cost={}),
               lambda d:[c for c in d['cases'] if c['id']=='06_nuance'][0]['outcome'].update(goal='another_goal'),
               lambda d:r0(d,'made_again').pop('skipped'),
               lambda d:r0(d,'made_again').update(skipped=['ship-quoted@1']),
               lambda d:r0(d,'made_again').update(actions=['prepare-quote@1','assume-approval@1']),
               lambda d:r0(d,'made_again')['model_receipts'].pop(),
               lambda d:r0(d,'made_again')['trace'][-2]['data'].update(source='fixture/elsewhere'),
               lambda d:c29(d)['run']['runs'][0].update(status='PLAN_READY'),
               lambda d:c29(d)['run']['runs'][0]['model_receipts'][0]['ask'].update(to='mallory'),
               lambda d:c29(d)['run']['runs'][0].update(cost={'compute':0,'money':0,'attention':0}),
               lambda d:c29(d)['run']['runs'][0]['trace'].pop(-2),
               lambda d:[c for c in d['cases'] if c['id']=='02_methods'][0]['outcome'].update(pareto_options=3),
               lambda d:r0(d,'answered_no').update(pareto_options=2),
               lambda d:r0(d,'answered_no').update(skipped=[]),
               lambda d:r0(d,'first').update(cost={'compute':0.0,'money':0,'attention':1}),
               lambda d:r0(d,'first')['model_receipts'][0].update(parked=1),
               lambda d:c29(d)['four_views'].update(design=[]),
               lambda d:r0(d,'no_again').update(claim='EXTERNALLY VERIFIED SUCCESS'),
               lambda d:r0(d,'no_again').update(claim='LOCAL_REFERENCE_ONLY; and verified outside'),
               lambda d:ev(d,'answered_yes')['event'].update(verified=1),
               lambda d:ev(d,'answered_no')['event'].update(final=1),
               lambda d:ev(d,'after_first')['budget'].update(attention=2.0),
               lambda d:ev(d,'after_again')['providers'].update({'owner-channel':1.0}),
               lambda d:c29(d)['derived_state']['budget_after'].update(attention=2.0),
               lambda d:ev(d,'after_first')['open_asks']['orgA/fulfillment|customer_approved']['issued'].update(parked=1),
               lambda d:r0(d,'first')['provenance'].pop(),
               lambda d:r0(d,'first')['provenance'][-1].update(sha256='0'*64),
               lambda d:[x['provenance'].reverse() for x in (c29(d)['outcome'],c29(d)['run']['runs'][0])],
               retold('09_pareto','LOCAL_MODEL_EFFECTS_RECORDED','completed'),   # a plan that ran nothing, said to have recorded effects
               retold('09_pareto','SUPPORTED_BY_EVIDENCE','completed'),          # the same plan said to be complete on evidence, its steps still listed
               retold('09_pareto','WAITING','ready'),                            # a ready plan said to be waiting
               retold('04_gates','SUPPORTED_BY_EVIDENCE','completed'),           # a run with a receipt, said to have run nothing
               lambda d:r0(d,'answered_no')['provenance'][0].update(sha256='0'*64)]   # a blocked run naming a pack that is not its file
    check('S48_claims_fail_on_forged_records',all(falsified(f) for f in forgeries),detail=str([i for i,f in enumerate(forgeries) if not falsified(f)]))
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
