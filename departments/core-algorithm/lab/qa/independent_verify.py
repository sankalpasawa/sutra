"""Independent local trace and artifact verifier. MUST NOT import kernel/core or extensions."""
from __future__ import annotations
import json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'results'/'actual_run_records.json'

def sha(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def check_chain(trace):
    for i,row in enumerate(trace):
        if not held('seq',type(row['seq']) is int) or row['seq']!=i+1:return False   # a whole number by type: true is not 1 and 2.0 is not 2
        if row['prev_sha256'] != (trace[i-1]['sha256'] if i else 'GENESIS'):return False
        if row['sha256']!=sha({k:v for k,v in row.items() if k!='sha256'}):return False
    return True

# 0.9.0-stop: what a stopped run and a case's books are held to. Module level, so the unit tests can run them on stops made in memory.
PHRASES=('Gate changed before effect: ','Prerequisite not true before effect: ','Handler refused: ','Handler failed: ','Kernel fault: ');RETURNED='Handler returned what cannot be a receipt'
RANK=('SEMANTICS_MISSING','SEMANTICS_UNAPPROVED','EVIDENCE_CONFLICT','REFUSED','QUERY_EVIDENCE','AUTHORITY_REQUIRED','PROVIDER_REQUIRED','RESOURCE_REQUIRED','METHOD_ABSENT','CYCLE_LIMIT')   # the verifier's own copy of the kernel's ten stop reasons, in the kernel's order
def block_ok(b):   # a BLOCK row against the ranking: every reason is one of the ten, each once and in order, and the row is named by the first in rank (METHOD_ABSENT when there is none: the kernel's own fallback, which the kernel reaches only on a State changed by hand, so a forged blocked run that names no reason at all passes; a stated limit)
    alls=b.get('all_reasons')
    return held('rank',type(alls) is list and all(type(x) is str and x in RANK for x in alls) and alls==sorted(set(alls)) and b.get('reason')==next((x for x in RANK if x in alls),'METHOD_ABSENT'))
OFF=set()   # checks switched off by name. Only S49 and S50 do that, to show that each check is the one that refuses its forgery
def held(name,ok):return name in OFF or bool(ok)
STEPS=('SELECT','BLOCK','ADMISSION','LOCAL_EFFECT','STEP_ALREADY_TRUE','STEP_STOPPED')   # the rows the kernel writes for a plan and its steps: a stop row is the last of them, and the kinds settle after them
def name_ok(text):return type(text) is str and text.isascii() and text.isidentifier()   # what the kernel writes for an error's class: one plain name of ASCII letters, digits and underscores that does not start with a digit and is not empty ('unreadable' when the class has none)

def said(text,needs):   # the text names one or more of the step's prerequisites, in their order, joined by single spaces (a name may hold a space itself, and may be the empty text)
    ends={(0,False)}   # how far the text is read, and whether a name was read
    for n in needs:ends|={(e+begun+len(n),True) for e,begun in ends if text[e+begun:].startswith(n) and (not begun or text[e:e+1]==' ')}
    return (len(text),True) in ends

def stop_ok(r,methods,kinds=None):
    """A run against the shape of a stop. A SETTLE_STOPPED row has two fields, the kind (one of `kinds`, the registry, when that is given; no kind twice) and one plain name for the
    error; it stands after every row of the plan and its steps; a plan that was only offered has none; and `unsettled` names the kinds of these rows, in their order. A STEP_STOPPED
    row has its three fields; its reason is a phrase of the closed list (the facts of a prerequisite stop are prerequisites of the stopped step; a failed handler and a kernel fault
    are named by one plain name; a handler's own words are held to nothing); it is the last row of the plan and its steps; and it stands right after the stopped step's own gate row,
    whose verdict it repeats. One exemption: a kernel fault may stand right after a row of the plan instead (SELECT, LOCAL_EFFECT, STEP_ALREADY_TRUE), because the kernel can fail
    before a step reaches its gate (its method is gone, say). Not caught here, each a stated limit that a unit test pins: a stop whose gate admitted the step, re-worded with any other phrase of the
    list that is not a gate's, with its gate row left in (the gate row says only that the step was admitted) or, as a kernel fault, taken out; the facts a prerequisite stop names, which
    are held to the step's prerequisites and not to what the stored rows read; a SETTLE_STOPPED row invented for a kind of the registry, or taken out together with its name under
    `unsettled` (the record says neither which kinds have a settle hook nor whether a blocked look was dry); and a stop re-told as a completed run (its stop row replaced by a
    STEP_ALREADY_TRUE row: this function then sees no stop to hold)."""
    t=r['trace'];ops=[e['operation'] for e in t];rows=[e['data'] for e in t if e['operation']=='SETTLE_STOPPED'];names=[x.get('kind') for x in rows];last=max([i for i,op in enumerate(ops) if op in STEPS],default=-1)
    if not held('unsettled',r.get('unsettled',[])==names and ('unsettled' in r)==bool(names) and all(set(x)=={'kind','reason'} and type(x['kind']) is str and (kinds is None or x['kind'] in kinds) and name_ok(x['reason']) for x in rows)
                and len(set(names))==len(names) and (not names or (r.get('work_state')!='ready' and ops.index('SETTLE_STOPPED')>last))):return False
    if 'STEP_STOPPED' not in ops:return True
    i=ops.index('STEP_STOPPED');stop=t[i]['data'];why=stop.get('reason');gate=t[i-1];needs=methods.get(stop.get('method'),{}).get('requires',[])
    if not held('shape',set(stop)=={'method','reason','effect_reads'} and type(why) is str and stop['effect_reads'] in ('TRUE','FALSE','UNKNOWN')):return False
    if not held('reason',why==RETURNED or (any(why.startswith(p) for p in PHRASES) and (not why.startswith(PHRASES[1]) or said(why[len(PHRASES[1]):],needs)) and all(name_ok(why[len(p):]) for p in PHRASES[3:] if why.startswith(p)))):return False
    own=gate['operation']=='ADMISSION' and gate['data'].get('methods')==[stop.get('method')]
    agrees=(gate['data'].get('accepted') is False and why==PHRASES[0]+' '.join(gate['data'].get('blockers',[]))) if why.startswith(PHRASES[0]) else gate['data'].get('accepted') is True
    return held('gate',i==last and ((own and agrees) or (why.startswith(PHRASES[4]) and gate['operation'] in ('SELECT','LOCAL_EFFECT','STEP_ALREADY_TRUE'))))

def stored(packs):
    """What a case's pack files leave in the books before any run: the rows stored (scope|fact -> row) and the rows a standing decision turned away, in order. The verifier's own copy
    of the kernel's rule for a row: a pack names the scope before its rows; a row that is not verified is ignored; a decision stands until another decision replaces it."""
    scope,rows,away='orgA/fulfillment',{},[]
    for p in packs:
        scope=p.get('scope',scope)
        for o in p.get('evidence',[]):
            at=o.get('scope',scope);key=at+'|'+o['predicate']
            if o.get('verified',False) and rows.get(key,{}).get('final') and not o.get('final'):away.append({'status':'DECISION_STANDS','scope':at,'predicate':o['predicate']})
            elif o.get('verified',False):rows[key]=dict(o,scope=at)
    return rows,away

def standing(facts,scope,fact,seen=()):
    """The stored row a fact reads from in a scope, or None when no valid row stands (the fact then reads UNKNOWN). The verifier's own copy of the kernel's rule for a reading:
    a row counts when it is verified and every row it rests on reads TRUE at the version it names (versions compare as JSON text); a fact that rests on itself reads UNKNOWN."""
    row=facts.get(scope+'|'+fact)
    if fact in seen or type(row) is not dict or row.get('verified') is not True:return None
    for dep in row.get('depends_on',[]):
        other=standing(facts,scope,dep['predicate'],seen+(fact,))
        if other is None or other.get('truth')!='TRUE' or sha(other.get('version'))!=sha(dep.get('version')):return None
    return row
def reading(facts,scope,fact):return (standing(facts,scope,fact) or {'truth':'UNKNOWN'})['truth']

def books_ok(case,methods,packs):
    """A case's books against its runs and pack files. The budget left is the packs' budget less the cost of the receipts. The journal begins with the rows the packs turned away
    and holds one row per run, in order, with the run's status and trace root; any other row in it is a row turned away during a run, on a fact that carries a decision. The
    candidates counted are the ones the last run lists, each cited by a receipt. The stored facts are the rows the packs left, except on the effect of a step that ran or stopped:
    that row is its handler's to write (it may not be gone where the packs left one). And what the stop row of the case's last run says its effect reads, and what that run says
    its goal reads, is exactly what the stored rows read. Not held: what an earlier run of the same case says its effect and its goal read (the books keep the facts as they stood
    at the end of the case); the handler's row itself; and whether a row said to be turned away during a run was."""
    runs=case['run']['runs'];book=case['derived_state'];facts=book['facts'];journal=book['historical_events'];left={'compute':10,'money':10,'attention':3};receipts=[x for r in runs for x in r['model_receipts']]
    for p in packs:left.update(p.get('budget',{}))
    for x in receipts:
        for dim,v in methods[x['method']].get('cost',{}).items():left[dim]-=v
    rows,away=stored(packs);made=runs[-1].get('candidates',[]) if runs else [];cited={x.get('candidate_sha256') for x in receipts}
    halts=[(r,e['data']) for r in runs for e in r['trace'] if e['operation']=='STEP_STOPPED'];effect=lambda mid:str(methods.get(mid,{}).get('effect'))
    own={r['scope']+'|'+effect(x['method']) for r in runs for x in r['model_receipts']}|{r['scope']+'|'+effect(stop.get('method')) for r,stop in halts}   # the facts a handler was called to make
    told=all(stop.get('effect_reads')==reading(facts,r['scope'],effect(stop.get('method'))) and r.get('goal_truth_after')==reading(facts,r['scope'],r['goal']) for r,stop in halts if r is runs[-1])
    turned=lambda j:set(j)=={'status','scope','predicate'} and j['status']=='DECISION_STANDS' and type(j['scope']) is str and type(j['predicate']) is str and (facts.get(j['scope']+'|'+j['predicate']) or {}).get('final') is True
    return (held('budget',sha(book['budget_after'])==sha(left))
            and held('journal',sha(journal[:len(away)])==sha(away) and sha([j for j in journal if 'goal' in j])==sha([{'goal':r['goal'],'scope':r['scope'],'status':r['status'],'trace_root_sha256':r['trace_root_sha256']} for r in runs])
                     and all('goal' in j or turned(j) for j in journal))
            and held('candidates',sha(book['candidate_count'])==sha(len(made)) and all(sha(c) in cited for c in made))
            and held('facts',all(key in facts and (key in own or sha(facts[key])==sha(rows.get(key))) for key in set(facts)|set(rows)))
            and held('effect',told))

def inspect(data):
    tests=[]
    def check(id,ok,detail=''):
        tests.append({'id':id,'pass':bool(ok),'detail':detail})
    h=hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest()
    check('S01_source_hash_current',data['kernel_sha256']==h)
    baseline=hashlib.sha256((ROOT/'release'/'baseline_v0_1_core.py').read_bytes()).hexdigest()
    check('S02_old_baseline_immutable',data['baseline_v0_1_sha256']==baseline and baseline.startswith('c5a86c28aac'))
    check('S03_31_distinct_cases',len(data['cases'])==31 and len(set(x['id'] for x in data['cases']))==31)
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
    check('S05_all_30_run_chains',len(valid_chains)==30 and all(valid_chains))
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
    # in a run's cost, in the ask record's snapshots, in the stamp's event and in every case's budget_after and candidate count. A stopped run (0.9.0) must carry one STEP_STOPPED row after its last receipt, the stopped step first under pending, and the same step and reason in its result; the row has its three fields and a reason from the closed list, is the last row of the plan and its steps and stands right after the stopped step's own gate row (a kernel fault may stand right after a row of the plan instead), and `unsettled` names the SETTLE_STOPPED rows, each held to its shape (stop_ok). Every case's books are held to its runs and its pack files: the budget left, the journal rows, the candidates of its last run, the stored facts, and what the stop row of its last run says its effect reads and what that run says its goal reads (books_ok). Not caught (this verifier runs neither the kernel nor a handler, and the chain holds no secret): a run re-made consistently from end to end; a handler's refusal re-worded; a stop whose gate admitted the step re-worded with any other phrase of the list that is not a gate's (a kernel fault with its gate row left in or taken out, a failed handler, a return that cannot be a receipt, a prerequisite of the stopped step, also one that the stored rows read TRUE); a stop re-told as a completed run by a STEP_ALREADY_TRUE row for the stopped step, although the stored row of that step's effect does not read TRUE; a settle failure invented or erased (the record says neither which kinds have a settle hook nor whether a blocked look was dry); a blocked run that names no reason at all, worded METHOD_ABSENT; a row said to be turned away during a run, on a fact that carries a decision; the stored row on the effect of a step that ran or stopped, which is its handler's to write; what an earlier run of a case with several goals says its effect and its goal read. The line that pins case 30 (in runs_ok below) refuses a re-wording of that case's own stop; a forged case 30 that has no `stopped` field ends this function with KeyError there instead of a failed check (the pinned fields are read before the check can refuse). NOT checked here: what a trace
    # does not carry (needs, proof, branch, and the truth of the goal other than what a stopped last run says its goal reads); trace rows that no check reads (an ADMISSION row's own fields, other than the verdict of a stopped step's gate row); a run's candidates (other than the count of a case's last run, and that a receipt cites each) and learning; a key
    # added to a run; the viewer's world and knowledge views; a case's title, description, area, scope, its run block's own status and
    # goals, and of its derived state the rule_ids; the order of the packs an event-block run names, and a pack
    # among them that no step needs; the release label; and an event block's own status, goals and counts beyond what S43 to S47 read.
    # The ask record must show: asked once, nothing
    # shipped, charged once; yes resumes; no is final; another route leaves the question answerable. S48 shows the same
    # claims fail on forged records.
    packs={p['id']:p for p in (json.loads(f.read_text()) for f in sorted((ROOT/'scenarios').glob('*.json')))}
    methods={mth['id']:mth for p in packs.values() for mth in p.get('methods',[])}   # every method of every pack file: the ask books below read their costs here
    loaded={}
    def packs_of(c):   # the pack files a case ran on, each read once
        for n in c['packs']:
            if n not in loaded:loaded[n]=json.loads((ROOT/'scenarios'/(n+'.json')).read_text())
        return [loaded[n] for n in c['packs']]
    CLAIM='LOCAL_REFERENCE_ONLY; never external success or current J2 implementation'   # the kernel's sentence, word for word
    def table(r):   # the methods of the packs this run says it loaded; a pack that is not its file gives no table
        if any(p['pack'] not in packs or sha(packs[p['pack']])!=p['sha256'] for p in r['provenance']):return None
        return {mth['id']:mth for p in r['provenance'] for mth in packs[p['pack']].get('methods',[])}
    rsha=lambda r:sha({k:v for k,v in r.items() if k!='sha256'});same=lambda a,b:sha(a)==sha(b)   # numbers are compared as JSON: 1 is not true and not 1.0
    def run_ok(r):
        t=r['trace'];last=t[-1];receipts=[e['data']['receipt'] for e in t if e['operation']=='LOCAL_EFFECT']
        chosen=[e['data'] for e in t if e['operation']=='SELECT'];skips=[e['data']['method'] for e in t if e['operation']=='STEP_ALREADY_TRUE'];stops=[e['data'] for e in t if e['operation']=='STEP_STOPPED'];ops=[e['operation'] for e in t];block=[e['data'] for e in t if e['operation']=='BLOCK'];waiting=r['work_state']=='waiting'
        mt=table(r);total=lambda acts:{d:sum(mt[a].get('cost',{}).get(d,0) for a in acts) for d in chosen[0]['full_cost']}
        return (check_chain(t) and same(r.get('claim'),CLAIM) and mt is not None and r['trace_root_sha256']==last['sha256'] and last['operation']=='TERMINAL' and last['data']=={'status':r['status'],'work_state':r['work_state']}
                and t[0]['operation']=='GOAL_ACCEPTED' and t[0]['data']=={'goal':r['goal'],'scope':r['scope']}
                and same(receipts,r['model_receipts']) and all(x['sha256']==rsha(x) and x['status']=='LOCAL_ONLY' for x in receipts)
                and len(chosen)+len(block)==1 and ('waits' in r)==waiting and ('pending' in r)==(waiting or bool(stops)) and ('stopped' in r)==bool(stops) and len(stops)<=1 and stop_ok(r,methods,handlers)
                and (not stops or ((r['status'],r['work_state'],r['stopped'],r['pending'][:1])==('STEP_STOPPED','stopped',{'method':stops[0]['method'],'reason':stops[0]['reason']},[stops[0]['method']])
                                   and 'LOCAL_EFFECT' not in ops[ops.index('STEP_STOPPED'):]))
                and ((r['status'],r['stop_reasons'],r['actions'],r['cost'],r['work_state'],receipts)==(block[0]['reason'],block[0]['all_reasons'],[],None,'blocked',[]) and same(r['pareto_options'],0) and not skips and 'skipped' not in r and block_ok(block[0]) if block else
                     r['stop_reasons']==[] and same(r['pareto_options'],chosen[0]['pareto_options']) and held('options',type(r['pareto_options']) is int) and [a for a in chosen[0]['actions'] if a not in skips]==r['actions']+r.get('pending',[]) and r.get('skipped',[])==skips and ('skipped' in r)==bool(skips) and set(skips)<=set(chosen[0]['actions'])
                     and set(chosen[0]['actions'])<=set(mt) and same(total(chosen[0]['actions']),chosen[0]['full_cost']) and same(r['cost'],total(r['actions'])) and [x['method'] for x in receipts]==(r['actions'] if r['work_state']!='ready' else [])
                     and r['status']=={'ready':'PLAN_READY','waiting':'WAITING','stopped':'STEP_STOPPED','completed':'LOCAL_MODEL_EFFECTS_RECORDED' if receipts else 'SUPPORTED_BY_EVIDENCE'}.get(r['work_state'])
                     and (not waiting or (r['status']=='WAITING' and (r['waits']==[receipts[-1]['method']] and receipts[-1].get('parked') is True if receipts else r['actions']==[] and chosen[0].get('waits')==r['waits'])))))
    def every_run(d):
        for c in d['cases']:
            if c['outcome']:yield c['outcome']
            yield from c['run']['runs']   # the same run as recorded under the case's run block: both copies are compared with their trace
        for block in ('events','ask_events'):
            for value in d[block].values():
                if isinstance(value,dict) and 'runs' in value:yield from value['runs']
    def runs_ok(d):   # every run agrees with its trace; the two copies of a case's run are one run; the run that skipped two steps says so in its result and in its chain
        made=d['ask_events']['made_again']['runs'][0];rows=[e['data'] for e in made['trace'] if e['operation']=='STEP_ALREADY_TRUE'];halt=[c for c in d['cases'] if c['id']=='30_stop'][0]['outcome']
        return (all(run_ok(r) for r in every_run(d)) and all(same(c['outcome'],c['run']['runs'][0] if c['run']['runs'] else None) and same([c['four_views']['design'],c['four_views']['run']],[(c['outcome'] or {}).get('actions',[]),(c['outcome'] or {}).get('trace',[])])
                                                         and (not c['outcome'] or [p['pack'] for p in c['outcome']['provenance']]==c['packs']) for c in d['cases'])
                and (made['status'],made['actions'],made.get('skipped'))==('LOCAL_MODEL_EFFECTS_RECORDED',['prepare-quote@1'],['assume-approval@1','ship-quoted@1'])
                and all(books_ok(c,methods,packs_of(c)) for c in d['cases'])
                and held('pin',(halt['status'],halt['stopped']['reason'],len(halt['model_receipts']),halt['pending']==[halt['stopped']['method']],halt['goal_truth_after'])==('STEP_STOPPED','Handler refused: No declared constructor',3,True,'FALSE'))
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
    # The stop forgeries of 0.9.0 (stop_forgeries) change the books of case 30 or re-make its run as a forger would: the run changed, its chain hashed again, every copy
    # of it updated. S49 switches each stop check off in turn and shows that a forgery then passes (each check is the one that refuses a forgery), with the line
    # that pins case 30 switched off throughout (no check leans on it).
    def falsified(change):
        d=json.loads(json.dumps(data));change(d)
        try:return not all(ask_claims(d).values())
        except Exception:return True
    c29=lambda d:[c for c in d['cases'] if c['id']=='29_ask'][0];c30=lambda d:[c for c in d['cases'] if c['id']=='30_stop'][0];r0=lambda d,key:d['ask_events'][key]['runs'][0];ev=lambda d,key:d['ask_events'][key]
    def remake(d,change):   # what a forger can do without any secret: change case 30's run, hash its chain again, and carry the new run to every copy the record keeps
        c=c30(d);r=c['outcome'];change(r);prev='GENESIS'
        for n,row in enumerate(r['trace']):
            row.update(seq=n+1,prev_sha256=prev);row['sha256']=sha({k:v for k,v in row.items() if k!='sha256'});prev=row['sha256']
        r['trace_root_sha256']=r['learning_record']['source_trace']=c['derived_state']['historical_events'][-1]['trace_root_sha256']=prev
        c['run']['runs'][0]=json.loads(json.dumps(r));c['four_views']['run']=json.loads(json.dumps(r['trace']))
    halted=lambda r:[e['data'] for e in r['trace'] if e['operation']=='STEP_STOPPED'][0]
    def reworded(reason):return lambda r:(halted(r).update(reason=reason),r['stopped'].update(reason=reason))
    def moved(r):   # the stop row put in front of its own gate row
        i=[e['operation'] for e in r['trace']].index('STEP_STOPPED');r['trace'][i-1],r['trace'][i]=r['trace'][i],r['trace'][i-1]
    stop_forgeries=[lambda d:c30(d)['derived_state']['budget_after'].update(compute=6),      # the stopped step was paid
                    lambda d:c30(d)['derived_state']['budget_after'].update(compute=10),     # nothing was paid
                    lambda d:[r.update(unsettled=['ask']) for r in (c30(d)['outcome'],c30(d)['run']['runs'][0])],
                    lambda d:c30(d)['derived_state']['historical_events'][-1].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
                    lambda d:c30(d)['derived_state'].update(candidate_count=1),
                    lambda d:[r.update(goal_truth_after='TRUE') for r in (c30(d)['outcome'],c30(d)['run']['runs'][0])],
                    lambda d:remake(d,lambda r:halted(r).update(effect_reads='TRUE')),
                    lambda d:remake(d,lambda r:halted(r).pop('effect_reads')),
                    lambda d:remake(d,lambda r:halted(r).update(note='x')),
                    lambda d:remake(d,reworded('Because')),
                    lambda d:remake(d,reworded('Prerequisite not true before effect: no_such_fact')),
                    lambda d:remake(d,reworded('Gate changed before effect: AUTHORITY_REQUIRED')),
                    lambda d:remake(d,moved),
                    lambda d:remake(d,lambda r:r['trace'].insert(-1,{'operation':'SETTLE_STOPPED','data':{'kind':'ask','reason':'KeyError'}})),
                    # review round two, 14 to 21: what the goal and the stopped step's effect read, said to be UNKNOWN against rows that read FALSE; a row the packs left, changed;
                    # a row said to be turned away by a decision nobody made; words that are no class name; a kernel fault in front of its own gate row; two SETTLE_STOPPED rows out of shape
                    lambda d:[r.update(goal_truth_after='UNKNOWN') for r in (c30(d)['outcome'],c30(d)['run']['runs'][0])],
                    lambda d:remake(d,lambda r:halted(r).update(effect_reads='UNKNOWN')),
                    lambda d:c30(d)['derived_state']['facts'].setdefault('orgA/enquiries|source_contract_reviewed',{}).update(truth='FALSE'),
                    lambda d:c30(d)['derived_state']['historical_events'].insert(0,{'status':'DECISION_STANDS','scope':'orgA/enquiries','predicate':'source_contract_reviewed'}),
                    lambda d:remake(d,reworded('Handler failed: not a class name at all')),
                    lambda d:remake(d,lambda r:(reworded('Kernel fault: KeyError')(r),moved(r))),
                    lambda d:remake(d,lambda r:(r['trace'].insert(-1,{'operation':'SETTLE_STOPPED','data':{'kind':'no_such_kind','reason':'KeyError'}}),r.update(unsettled=['no_such_kind']))),   # well made and well placed, for a kind the registry does not have
                    lambda d:remake(d,lambda r:(r['trace'].insert(1,{'operation':'SETTLE_STOPPED','data':{'kind':'ask'}}),r.update(unsettled=['ask']))),   # no reason, and before the plan is chosen
                    # 22, the last: the stored row on the effect of a step that ran or stopped is its handler's to write, so changing it together with what the run says it reads passes
                    # every check of a stop and of the books (a stated limit). On case 30 the pinned line refuses it, because the goal of that case reads FALSE; S49 shows it is the only one that needs that line.
                    lambda d:(c30(d)['derived_state']['facts'].setdefault('orgA/enquiries|capability_candidate_created',{}).update(truth='UNKNOWN'),remake(d,lambda r:(halted(r).update(effect_reads='UNKNOWN'),r.update(goal_truth_after='UNKNOWN'))))]
    def retold(cid,status,work):   # a case's run re-chained to end with another status and work state: both copies of the run and the viewer's copy of its trace
        def change(d):
            c=[c for c in d['cases'] if c['id']==cid][0]
            for r in (c['outcome'],c['run']['runs'][0]):
                last=r['trace'][-1];last['data']={'status':status,'work_state':work};last['sha256']=sha({k:v for k,v in last.items() if k!='sha256'})
                r.update(status=status,work_state=work,trace_root_sha256=last['sha256'])
            c['four_views']['run']=c['outcome']['trace']
        return change
    # 0.9.0 also holds a trace row's seq and a run's pareto_options to whole numbers by type, and a BLOCK row to the kernel's ranking (block_ok). The four forgeries below
    # re-make a case's run as a forger would (the run changed, its chain hashed again, every copy updated); S50 shows that each of the three checks refuses its own.
    def rechained(cid,change):   # what remake does for case 30, for any case: the journal row follows the run's status too, and a row's seq is left as the change set it
        def go(d):
            c=[c for c in d['cases'] if c['id']==cid][0];r=c['outcome'];change(r);prev='GENESIS'
            for row in r['trace']:
                row['prev_sha256']=prev;row['sha256']=sha({k:v for k,v in row.items() if k!='sha256'});prev=row['sha256']
            r['trace_root_sha256']=r['learning_record']['source_trace']=prev;c['derived_state']['historical_events'][-1].update(status=r['status'],trace_root_sha256=prev)
            c['run']['runs'][0]=json.loads(json.dumps(r));c['four_views']['run']=json.loads(json.dumps(r['trace']))
        return go
    row_of=lambda r,op:[e['data'] for e in r['trace'] if e['operation']==op][0]
    def renamed(r):   # a blocked run that says effects were recorded: the run, its BLOCK row and its last row say the same
        r.update(status='LOCAL_MODEL_EFFECTS_RECORDED');row_of(r,'BLOCK').update(reason='LOCAL_MODEL_EFFECTS_RECORDED');row_of(r,'TERMINAL').update(status='LOCAL_MODEL_EFFECTS_RECORDED')
    def retyped(r):   # the number of options as 3.0, in the run and in its SELECT row
        n=float(r['pareto_options']);r.update(pareto_options=n);row_of(r,'SELECT').update(pareto_options=n)
    hard_forgeries=[rechained('02_methods',renamed),
                    rechained('02_methods',lambda r:(r.update(stop_reasons=['METHOD_ABSENT','NO_SUCH_REASON','QUERY_EVIDENCE']),row_of(r,'BLOCK').update(all_reasons=['METHOD_ABSENT','NO_SUCH_REASON','QUERY_EVIDENCE']))),   # a reason outside the ten, in the run and in its BLOCK row
                    rechained('09_pareto',lambda r:r['trace'][1].update(seq=2.0)),   # a row numbered 2.0
                    rechained('09_pareto',retyped)]
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
               lambda d:r0(d,'answered_no')['provenance'][0].update(sha256='0'*64),   # a blocked run naming a pack that is not its file
               lambda d:c30(d)['outcome'].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
               lambda d:c30(d)['outcome'].update(work_state='completed'),
               lambda d:c30(d)['outcome']['stopped'].update(reason='Handler failed: KeyError'),
               lambda d:c30(d)['outcome'].pop('stopped'),
               lambda d:c30(d)['outcome'].update(pending=[]),
               lambda d:c30(d)['outcome']['model_receipts'].pop(),
               lambda d:c30(d)['run']['runs'][0]['stopped'].update(method='construct-nothing@1')]+stop_forgeries+hard_forgeries
    check('S48_claims_fail_on_forged_records',all(falsified(f) for f in forgeries),detail=str([i for i,f in enumerate(forgeries) if not falsified(f)]))
    def accepted(off):   # the stop forgeries that pass when the named checks are switched off
        OFF.update(off)
        try:return [i for i,f in enumerate(stop_forgeries) if not falsified(f)]
        finally:OFF.difference_update(off)
    alone={name:accepted({'pin',name}) for name in ('unsettled','shape','reason','gate','budget','journal','candidates','facts','effect')}   # each check switched off in turn, the pinned line off throughout: exactly its own forgeries then pass, next to the one that only the pinned line refuses
    check('S49_every_stop_check_refuses_a_forgery_of_its_own_and_only_the_last_forgery_leans_on_the_case_pin',accepted(set())==[] and accepted({'pin'})==[22]
          and alone=={'unsettled':[2,13,20,21,22],'shape':[8,22],'reason':[9,10,18,22],'gate':[11,12,19,22],'budget':[0,1,22],'journal':[3,17,22],'candidates':[4,22],'facts':[16,22],'effect':[5,6,14,15,22]},
          detail=str({'accepted':accepted(set()),'accepted without the pin':accepted({'pin'}),'accepted with one check more off':alone}))
    def passing(off):   # the hardening forgeries that pass when the named check is switched off
        OFF.update(off)
        try:return [i for i,f in enumerate(hard_forgeries) if not falsified(f)]
        finally:OFF.difference_update(off)
    lone={name:passing({name}) for name in ('rank','seq','options')}
    check('S50_a_blocked_reason_and_the_type_of_a_number_each_refuse_a_forgery_of_their_own',not passing(set()) and lone=={'rank':[0,1],'seq':[2],'options':[3]},detail=str({'accepted':passing(set()),'accepted with one check off':lone}))
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
