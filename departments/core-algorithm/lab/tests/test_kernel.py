from pathlib import Path
import unittest, sys, json, copy, hashlib, importlib.util
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest,ACTIONS,register,Stop
from tools.run_all import CASES,pack,extra_events,ASK,scenario
from extensions.asks import answer,open_asks
from extensions.j2_projection import to_j2_proposed_atom_views as j2_atoms
from extensions.knowledge import compile_pattern,signal_priority
from extensions.reflection import minimal_graph_diff,reflect,Learner
from extensions.j2_projection import to_j2_proposed_atom_views
from extensions.implementation import to_implementation,validate_workflow

def _throw(exc):   # a handler that raises what it is given
    def run(s,m,mid,deps):raise exc
    return run

EXPECTED={
 '00_goal':'SEMANTICS_MISSING','01_meaning':'METHOD_ABSENT',
 '02_methods':'QUERY_EVIDENCE','03_evidence':'AUTHORITY_REQUIRED',
 '04_gates':'LOCAL_MODEL_EFFECTS_RECORDED','05_learn':'LOCAL_MODEL_EFFECTS_RECORDED',
 '06_nuance':'LOCAL_MODEL_EFFECTS_RECORDED','07_gap':'METHOD_ABSENT',
 '08_method_added':'LOCAL_MODEL_EFFECTS_RECORDED',
 '09_pareto':'PLAN_READY','10_preference':'PLAN_READY',
 '11_knowledge_gap':'SEMANTICS_UNAPPROVED',
 '12_enquiry':'LOCAL_MODEL_EFFECTS_RECORDED','13_privacy_gap':'METHOD_ABSENT',
 '14_privacy_method':'LOCAL_MODEL_EFFECTS_RECORDED',
 '15_constructor':'LOCAL_MODEL_EFFECTS_RECORDED',
 '16_bad_constructor':'LOCAL_MODEL_EFFECTS_RECORDED',
 '17_reviewed_release':'LOCAL_MODEL_EFFECTS_RECORDED',
 '18_self_need':'AUTHORITY_REQUIRED','19_self_grant':'LOCAL_MODEL_EFFECTS_RECORDED',
 '20_wrong_tenant':'QUERY_EVIDENCE','21_no_goal':'NO_STANDING_GOAL',
 '22_revoke':'AUTHORITY_REQUIRED','23_capacity':'PROVIDER_REQUIRED','24_budget':'RESOURCE_REQUIRED',
 '25_registrable_gap':'METHOD_ABSENT','26_registrable_repair':'LOCAL_MODEL_EFFECTS_RECORDED',
 '27_registrable_generated':'SUPPORTED_BY_EVIDENCE','28_website':'PLAN_READY','29_ask':'WAITING','30_stop':'STEP_STOPPED'
}
class ContractTests(unittest.TestCase):
    def test_original_baseline_byte_identical(self):
        sha=hashlib.sha256((ROOT/'release'/'baseline_v0_1_core.py').read_bytes()).hexdigest()
        self.assertEqual(sha,'c5a86c28aac5313f7947963c6691f24fe4461107b7dc2a985b5f979249c259f9')
    def test_all_scenarios_same_kernel(self):
        sha=hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest()
        self.assertEqual(len(sha),64)
        for cid,title,description,files,execute,area in CASES:
            c=State.from_packs([pack(n) for n in files]);Kernel(c).run_standing(execute=execute)
            self.assertEqual(hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest(),sha)
    def test_tenant_evidence_isolation(self):
        c=State.from_packs([pack('00_goal'),pack('01_domain'),pack('02_methods'),pack('04_admission'),pack('12_other_tenant')])
        self.assertEqual(c.fact('customer_approved')['truth'],'UNKNOWN')
    def test_unreviewed_rule_not_promoted(self):
        c=State.from_packs([pack('50_unapproved_semantics')]);self.assertNotIn('enquiry_complete',c.rules)
    def test_unknown_does_not_mean_false(self):
        c=State.from_packs([pack('00_goal'),pack('01_domain'),pack('02_methods')])
        self.assertEqual(Kernel(c).run_standing()['runs'][0]['status'],'QUERY_EVIDENCE')
    def test_no_auth_no_effect(self):
        c=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval')])
        r=Kernel(c).run_standing(execute=True)['runs'][0]
        self.assertEqual(r['status'],'AUTHORITY_REQUIRED');self.assertEqual(r['model_receipts'],[])
    def test_negative_resource_provider_rejected(self):
        c=State()
        with self.assertRaises(ValueError):c.apply({'schema':'sutra-extension/2','id':'bad','budget':{'money':-1}})
        with self.assertRaises(ValueError):c.apply({'schema':'sutra-extension/2','id':'bad2','providers':{'p':-1}})
    def test_rule_upgrade_requires_ancestor(self):
        c=State.from_packs([pack('00_goal'),pack('01_domain')])
        with self.assertRaises(ValueError):c.apply({'schema':'sutra-extension/2','id':'upgrade',
         'rules':[{'id':'R-NEW@2','head':'order_complete','approved':True,'branches':[['a']]}]})
    def test_unregistered_action_rejected(self):
        c=State()
        with self.assertRaises(ValueError):c.apply({'schema':'sutra-extension/2','id':'exploit',
         'methods':[{'id':'bad','effect':'x','action':'send_email'}]})
    def test_dedupe_shared_method_within_one_scope(self):
        c=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission','06_notify')])
        r=Kernel(c).run_standing()['runs'][0]
        self.assertEqual(r['actions'].count('ship-replacement@1'),1)
        self.assertEqual(r['cost'],{'compute':3,'money':3,'attention':0})
    def test_cost_pareto_preference_switch(self):
        a=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission','09_fast_tradeoff')]);
        b=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission','09_fast_tradeoff','10_money_first')]);
        self.assertEqual(Kernel(a).run_standing()['runs'][0]['actions'],['ship-fast@1'])
        self.assertEqual(Kernel(b).run_standing()['runs'][0]['actions'],['ship-economy@1'])
    def test_unrelated_event_no_replan(self):
        self.assertEqual(extra_events()['unrelated']['affected'],[])
    def test_cross_tenant_event_no_replan(self):
        self.assertEqual(extra_events()['cross_tenant']['affected'],[])
    def test_relevant_event_selective_replan(self):
        self.assertEqual(extra_events()['approval_revoked']['affected'],['order_complete'])
    def test_transitive_invalidation(self):
        c=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission','06_notify')]);k=Kernel(c)
        k.run_standing(execute=True)
        self.assertEqual(c.fact('customer_notified')['truth'],'TRUE')
        k.on_event({'predicate':'customer_approved','truth':'FALSE','version':'v2','verified':True,'source':'test'})
        self.assertEqual(c.fact('customer_notified')['truth'],'UNKNOWN')
    def test_immutable_record_after_rule_revision(self):
        e=extra_events();self.assertEqual(e['old_trace_hash_before'],e['old_trace_hash_after'])
    def test_candidate_cannot_self_promote(self):
        c=State.from_packs([pack(n) for n in ('30_build_goal','31_build_theory','32_builder_components')]);k=Kernel(c)
        out=k.run_standing(execute=True)['runs'][0];out['candidates'][0]['status']='APPROVED'   # a result's candidates are copies
        self.assertEqual(next(iter(c.candidates.values()))['status'],'PROPOSED_ONLY')
        self.assertNotIn('record_retrievable',[m['effect'] for m in c.methods.values()])
    def test_bad_candidate_contract_rejected(self):
        c=State.from_packs([pack(n) for n in ('30_build_goal','31_build_theory','32_builder_components','33_bad_constructor')]);k=Kernel(c)
        k.run_standing(execute=True)
        self.assertFalse(next(iter(c.candidates.values()))['valid_contract'])
    def test_self_goal_requires_external_grant(self):
        c=State.from_packs([pack(n) for n in ('40_self_goal','41_self_theory','42_self_methods')]);
        r=Kernel(c).run_standing(execute=True)['runs'][0]
        self.assertEqual(r['status'],'AUTHORITY_REQUIRED')
    def test_self_goal_does_not_modify_kernel(self):
        orig=(ROOT/'kernel'/'core.py').read_bytes();c=State.from_packs([pack(n) for n in ('40_self_goal','41_self_theory','42_self_methods','43_self_review_grant')]);Kernel(c).run_standing(execute=True)
        self.assertEqual(orig,(ROOT/'kernel'/'core.py').read_bytes())
    def test_dynamic_vector_dimensions(self):
        c=State();c.apply({'schema':'sutra-extension/2','id':'x','budget':{'compute':5,'money':5,'attention':1,'energy':3},
          'preference':['energy','compute','money','attention']})
        self.assertIn('energy',c.budget)
    def test_knowledge_requires_signoff(self):
        p={'id':'P','slots':['X'],'head':'goal_${X}','branches':[['need_${X}']],
           'source':'reviewed/s','source_version':'1'}
        self.assertFalse(compile_pattern(p,{'X':'a'})['rules'][0]['approved'])
        self.assertTrue(compile_pattern(p,{'X':'a'},
           {'approved':True,'pattern_hash':digest(p),'reviewer':'explicit-reviewer'})['rules'][0]['approved'])
    def test_knowledge_missing_slots_rejected(self):
        p={'id':'P','slots':['A'],'head':'g_${A}','branches':[['a_${A}']],
           'source':'s','source_version':'1'}
        with self.assertRaises(ValueError):compile_pattern(p,{})
    def test_signal_rank_grounded(self):
        s=signal_priority([{'id':'x','source':'s','decision_impact':1,'applicable':True},
                           {'id':'y','source':'s','decision_impact':9,'applicable':True}]);
        self.assertEqual(s[0]['id'],'y')
    def test_reflection_candidates_are_never_promoted(self):
        c=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]);
        r=Kernel(c).run_standing()['runs'][0]
        reflection=reflect([r,r]);self.assertTrue(reflection['candidate_count']>=1)
        self.assertTrue(all(v['status']=='PROPOSED_ONLY' for v in reflection['candidates']))
    def test_j2_projection_is_open_not_falsely_closed(self):
        c=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]);r=Kernel(c).run_standing()['runs'][0]
        proj=to_j2_proposed_atom_views(r)
        self.assertEqual(proj['schema'],'atom/1');self.assertTrue(all(x['status']=='open' for x in proj['atoms']))
    def test_graph_diff_minimal(self):
        d=minimal_graph_diff({'actions':['a','b']},{'actions':['a','c']})
        self.assertEqual(d['retained'],['a']);self.assertEqual(d['added'],['c'])
        self.assertEqual(d['retired'],['b'])
    def test_no_unauthorized_real_action(self):
        c=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]);r=Kernel(c).run_standing(execute=True)['runs'][0]
        self.assertTrue(all(x['status']=='LOCAL_ONLY' for x in r['model_receipts']))
        self.assertIn('never external success',r['claim'])
    # Implementation version (program rung L1): a plan becomes a runnable workflow shape, atoms, a scaffold and a page.
    ORDER=('00_goal','01_domain','02_methods','03_approval','04_admission','06_notify')
    def test_implementation_workflow_shape(self):
        c=State.from_packs([pack(n) for n in self.ORDER]);r=Kernel(c).run_standing()['runs'][0];impl=to_implementation(r,c)
        self.assertEqual(validate_workflow(impl['workflow']),[])
        self.assertEqual([s['method'] for s in impl['workflow']['steps'] if s.get('method')],['ship-replacement@1','notify-customer@1'])
        self.assertEqual(impl['workflow']['steps'][0]['id'],'record-intent');self.assertEqual(impl['workflow']['steps'][-1]['id'],'show-it')
        self.assertEqual(len(impl['atoms']),2);self.assertIn('order_complete',impl['workflow']['verify'])
    def test_implementation_is_proposal_only_and_pure(self):
        c=State.from_packs([pack(n) for n in self.ORDER]);r=Kernel(c).run_standing()['runs'][0]
        before=(digest(c.evidence),digest(c.methods),sorted(c.grants),dict(c.budget))
        a=to_implementation(r,c);b=to_implementation(r,c)
        self.assertEqual(a['implementation_sha256'],b['implementation_sha256']);self.assertEqual(a['ui_sha256'],b['ui_sha256'])
        self.assertEqual(before,(digest(c.evidence),digest(c.methods),sorted(c.grants),dict(c.budget)))
        self.assertEqual(a['status'],'PROPOSED_ONLY')
        self.assertTrue(all(s['sandbox']=='local-model-only' for s in a['workflow']['steps'] if s.get('method')))
        self.assertTrue(all(x['status']=='open' and x['verify']['met'] is False for x in a['atoms']))
        self.assertIn('nothing here has run',a['ui'])
    def test_implementation_scaffold_from_rules_and_grants(self):
        c=State.from_packs([pack(n) for n in self.ORDER]);r=Kernel(c).run_standing()['runs'][0];impl=to_implementation(r,c)
        self.assertEqual(len(impl['scaffold']['done_when']),2);self.assertIn('customer_notified is TRUE',impl['scaffold']['done_when'][1])
        tags={row['line'].split(' ')[0]:row['tag'] for row in impl['scaffold']['rules'] if row['tag'] in ('go','ask')}
        self.assertEqual(tags['ship-replacement@1'],'go')
        revoked=State.from_packs([pack(n) for n in self.ORDER+('13_revoke_authority',)]);impl2=to_implementation(r,revoked)
        tags2={row['line'].split(' ')[0]:row['tag'] for row in impl2['scaffold']['rules'] if row['tag'] in ('go','ask')}
        self.assertEqual(tags2['ship-replacement@1'],'ask');self.assertEqual(tags2['notify-customer@1'],'go')
        self.assertTrue(any(row['tag']=='refuse' for row in impl2['scaffold']['rules']))
    # 0.4.0-shrink, move-out M1: learning left the kernel for extensions/reflection.Learner.
    LEARN=('00_goal','01_domain','02_methods','03_approval','04_admission','05_learning')
    def test_kernel_carries_no_learning_state_or_branch(self):
        # Counterexample: fails on 0.3.0, whose State carried learned_signatures and whose resolve emitted REUSE_COMPOSITION.
        import inspect
        self.assertFalse(hasattr(State(),'learned_signatures'));self.assertFalse(hasattr(State(),'learning'))
        src=inspect.getsource(Kernel.resolve)
        for word in ('REUSE_COMPOSITION','INVESTIGATE_GAP','LEARN_CANDIDATE'):self.assertNotIn(word,src)
        c=State.from_packs([pack(n) for n in self.LEARN]);r=Kernel(c).run_standing(execute=True)['runs'][0]
        self.assertNotIn('learning',r);self.assertEqual(r['status'],'LOCAL_MODEL_EFFECTS_RECORDED')
    def test_learner_reproduces_0_3_0_learning_on_recorded_cases(self):
        # Equivalence: what the 0.3.0 kernel's learning block emitted on cases 05, 06, 07 and 08 (recorded 2026-11-10).
        reuse='independent held-out verification + approval';gap='independent evidence + authorization'
        expect={'05_learn':[{'kind':'REUSE_COMPOSITION','signature':'ship-replacement@1','observations':1,'status':'PROPOSED_ONLY','gate':reuse}],
                '06_nuance':[{'kind':'REUSE_COMPOSITION','signature':'ship-replacement@1 -> notify-customer@1','observations':1,'status':'PROPOSED_ONLY','gate':reuse}],
                '07_gap':[{'kind':'INVESTIGATE_GAP','gap':'METHOD_ABSENT','status':'PROPOSED_ONLY','gate':gap}],
                '08_method_added':[{'kind':'REUSE_COMPOSITION','signature':'ship-replacement@1 -> notify-customer@1 -> record-survey@1','observations':1,'status':'PROPOSED_ONLY','gate':reuse}]}
        for cid,_,_,files,execute,_ in CASES:
            if cid not in expect:continue
            packs=[pack(n) for n in files];k=Kernel(State.from_packs(packs));learner=Learner.from_packs(packs)
            self.assertEqual(learner.attach(k.run_standing(execute=execute))['runs'][0]['learning'],expect[cid],cid)
            again=learner.attach(k.run_standing(execute=execute))['runs'][0]['learning']
            self.assertEqual(again,expect[cid] if cid=='07_gap' else [],cid)   # a second run: evidence holds, nothing to learn; a still-blocked goal proposes again
        self.assertTrue(all(x['status']=='PROPOSED_ONLY' for v in expect.values() for x in v))
    def test_learner_off_without_pack_flag_and_counts_repeats(self):
        packs=[pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]
        self.assertEqual(Learner.from_packs(packs).attach(Kernel(State.from_packs(packs)).run_standing(execute=True))['runs'][0]['learning'],[])
        l=Learner(enabled=True);r={'status':'LOCAL_MODEL_EFFECTS_RECORDED','work_state':'completed','actions':['a@1','b@1']}
        self.assertEqual(l.learn(r)[0]['observations'],1);self.assertEqual(l.learn(r)[0]['observations'],2)
    def test_learner_matches_0_3_0_on_dry_run_recount_and_late_packs(self):
        # Recorded from the 0.3.0 kernel on 2026-11-10 (the points the D79 refuters named): a dry run learns nothing;
        # a re-execution on one State counts 2 even through a second Kernel; a late pack switches learning off or on.
        revoke={'predicate':'customer_approved','truth':'FALSE','version':'v2','verified':True,'source':'t'}
        again={'predicate':'customer_approved','truth':'TRUE','version':'v3','verified':True,'source':'t'}
        kinds=lambda run:[(x['kind'],x.get('observations')) for r in run['runs'] for x in r['learning']]
        packs=[pack(n) for n in self.LEARN]
        s=State.from_packs(packs);l=Learner.from_packs(packs);dry=l.attach(Kernel(s).run_standing(execute=False))
        self.assertEqual(dry['runs'][0]['status'],'PLAN_READY');self.assertEqual(kinds(dry),[])
        s=State.from_packs(packs);l=Learner.from_packs(packs);k=Kernel(s)
        self.assertEqual(kinds(l.attach(k.run_standing(execute=True))),[('REUSE_COMPOSITION',1)])
        self.assertEqual(kinds(l.attach(k.on_event(revoke,execute=True))),[('INVESTIGATE_GAP',None)])
        self.assertEqual(kinds(l.attach(Kernel(s).on_event(again,execute=True))),[('REUSE_COMPOSITION',2)])
        s=State.from_packs(packs);l=Learner.from_packs(packs);k=Kernel(s);l.attach(k.run_standing(execute=True))
        off={'schema':'sutra-extension/2','id':'late-off','learning':False};s.apply(off);l.apply(off)
        self.assertEqual(kinds(l.attach(k.on_event(revoke,execute=True))),[])
        base=[pack(n) for n in self.LEARN[:-1]];s=State.from_packs(base);l=Learner.from_packs(base);k=Kernel(s)
        self.assertEqual(kinds(l.attach(k.run_standing(execute=True))),[])
        on={'schema':'sutra-extension/2','id':'late-on','learning':True};s.apply(on);l.apply(on)
        self.assertEqual(kinds(l.attach(k.on_event(revoke,execute=True))),[('INVESTIGATE_GAP',None)])
        self.assertEqual(kinds(l.attach(k.on_event(again,execute=True))),[('REUSE_COMPOSITION',1)])
    def test_learning_is_bound_to_the_trace_root(self):
        packs=[pack(n) for n in self.LEARN];r=Learner.from_packs(packs).attach(Kernel(State.from_packs(packs)).run_standing(execute=True))['runs'][0]
        self.assertEqual(r['learning_record'],{'source_trace':r['trace_root_sha256'],'learning_sha256':digest(r['learning'])})
    # 0.5.0-standards: a standard is a rule; its facts come from an evidence adapter over a workflow JSON.
    def test_standards_adapter_rows_are_verified_and_versioned(self):
        from extensions.standards import workflow_facts,SOURCE
        bad={'id':'W-x','trigger':{'kind':'intent'},'steps':[{'id':'a','action':'do'}],'verify':'whole'}
        rows={r['predicate']:r for r in workflow_facts(bad)}
        self.assertEqual([rows[p]['truth'] for p in ('has_trigger','every_step_has_check','has_overall_verify')],['TRUE','FALSE','TRUE'])
        self.assertTrue(all(r['verified'] and r['source']==SOURCE and r['version'].startswith('wf-') for r in rows.values()))
        good=dict(bad,steps=[{'id':'a','action':'do','verify':'done'}])
        self.assertTrue(all(r['truth']=='TRUE' for r in workflow_facts(good)))
        self.assertNotEqual(workflow_facts(good)[0]['version'],rows['has_trigger']['version'])
        self.assertEqual(workflow_facts({})[1]['truth'],'FALSE')   # no steps is not "every step has a check"
    def test_standard_blocks_then_repairs_then_generated_work_passes(self):
        by={c[0]:c for c in CASES};out={}
        for cid in ('25_registrable_gap','26_registrable_repair','27_registrable_generated'):
            _,_,_,files,execute,_=by[cid];s=State.from_packs([pack(n) for n in files]);out[cid]=(Kernel(s).run_standing(execute=execute)['runs'][0],s)
        gap,s=out['25_registrable_gap'];self.assertEqual(gap['status'],'METHOD_ABSENT');self.assertEqual(s.fact('every_step_has_check')['truth'],'FALSE')
        rep,s=out['26_registrable_repair'];self.assertEqual(rep['actions'],['add-step-checks@1']);self.assertEqual(s.fact('every_step_has_check')['source'],'LOCAL_MODEL:add-step-checks@1')
        ok,s=out['27_registrable_generated'];self.assertEqual((ok['status'],ok['actions'],ok['model_receipts']),('SUPPORTED_BY_EVIDENCE',[],[]))
        self.assertTrue(s.fact('every_step_has_check')['source'].startswith('adapter:standards/'))
    # 0.6.0-order: the generator emits each step's prerequisites and the plan's edges, and refuses a wrong order.
    SITE=('70_site_goal','71_site_theory','72_site_methods')
    def test_plan_and_edges_follow_the_requires_chain(self):
        c=State.from_packs([pack(n) for n in self.SITE]);r=Kernel(c).run_standing()['runs'][0]
        self.assertEqual(r['actions'],['plan-site@1','write-content@1','build-pages@1','check-site@1'])   # authored in the reverse order
        wf=to_implementation(r,c)['workflow'];self.assertEqual(validate_workflow(wf),[])
        self.assertEqual([(e['from'],e['to'],e['via']) for e in wf['edges']],
            [('plan-site-1','write-content-1','site_planned'),('write-content-1','build-pages-1','content_written'),
             ('plan-site-1','build-pages-1','site_planned'),('build-pages-1','check-site-1','pages_built')])
        after={s['id']:s['after'] for s in wf['steps'] if s.get('method')}
        self.assertEqual(after,{'plan-site-1':[],'write-content-1':['plan-site-1'],'build-pages-1':['write-content-1','plan-site-1'],'check-site-1':['build-pages-1']})
    def test_workflow_with_a_step_before_its_prerequisite_is_refused(self):
        c=State.from_packs([pack(n) for n in self.SITE]);wf=to_implementation(Kernel(c).run_standing()['runs'][0],c)['workflow']
        bad=dict(wf,steps=[wf['steps'][0],wf['steps'][2],wf['steps'][1]]+wf['steps'][3:])
        self.assertTrue(any('comes before its prerequisite' in p for p in validate_workflow(bad)))
        self.assertTrue(any('not in the workflow' in p for p in validate_workflow(dict(wf,edges=[{'from':'nowhere','to':'check-site-1','via':'x'}]))))
    # 0.7.0-handlers: the kernel keeps the gate and gives up the effect (move-outs M2 + M3).
    BUILD=('30_build_goal','31_build_theory','32_builder_components')
    KERNEL_ONLY={'simulate_fact':ACTIONS['simulate_fact']}
    def test_kernel_carries_no_constructor_or_artifact_branch(self):
        # Counterexample: fails on 0.6.0, whose kernel named both kinds and accepted the constructor pack on its own.
        src=(ROOT/'kernel'/'core.py').read_text()
        for word in ('compile_candidate','emit_artifact','LOCAL_ARTIFACT','valid_contract'):self.assertNotIn(word,src)
        import subprocess
        alone=subprocess.run([sys.executable,'-I','-B','-c','import sys;sys.path.insert(0,sys.argv[1]);from kernel.core import ACTIONS;print(sorted(ACTIONS))',str(ROOT)],capture_output=True,text=True)
        self.assertEqual(alone.stdout.strip(),"['simulate_fact']")
        s=State(actions=dict(self.KERNEL_ONLY));s.apply(pack('30_build_goal'));s.apply(pack('31_build_theory'))
        with self.assertRaises(ValueError):s.apply(pack('32_builder_components'))
    def test_registry_refuses_overwrite_and_a_built_state_keeps_its_snapshot(self):
        with self.assertRaises(ValueError):register('simulate_fact')(lambda s,m,mid,deps:{})
        s=State();register('test_only_kind')(lambda s,m,mid,deps:{})
        try:
            self.assertNotIn('test_only_kind',s.actions);self.assertIn('test_only_kind',State().actions)
            with self.assertRaises(ValueError):s.apply({'schema':'sutra-extension/2','id':'late','methods':[{'id':'x','effect':'y','action':'test_only_kind','grant':'g','provider':'p'}]})
        finally:del ACTIONS['test_only_kind']
    def test_handler_cannot_set_receipt_fields_or_run_before_prerequisites(self):
        packs=[pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]
        s=State(actions={'simulate_fact':{'run':lambda s,m,mid,deps:{'status':'EXTERNAL_DONE'}}})
        for p in packs:s.apply(p)
        r=Kernel(s).run_standing(execute=True)['runs'][0]   # a handler that sets a receipt field: a recorded stop, nothing paid, one journal row
        self.assertEqual((r['status'],r['work_state'],r['actions'],r['model_receipts'],r['stopped']['reason'],r['pending'][:1],s.budget,[j['status'] for j in s.event_journal]),
                         ('STEP_STOPPED','stopped',[],[],'Handler returned what cannot be a receipt',[r['stopped']['method']],{'compute':10,'money':10,'attention':3},['STEP_STOPPED']))
        self.assertEqual(s.fact('replacement_delivered')['truth'],'FALSE')
        s=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','04_admission')]);k=Kernel(s)   # approval unknown
        self.assertEqual(k._act({'actions':['ship-replacement@1']}),[]);stop=k.events[-1]   # run by hand before its prerequisite is true: the gate stops the step
        self.assertEqual((stop['operation'],stop['data']['method'],stop['data']['reason'].split(':')[0],'customer_approved' in stop['data']['reason']),('STEP_STOPPED','ship-replacement@1','Prerequisite not true before effect',True))
        self.assertEqual(s.fact('replacement_delivered')['truth'],'FALSE');self.assertEqual(s.budget,{'compute':10,'money':10,'attention':3})
    def test_moved_handlers_reproduce_0_6_0_receipts_and_trace_roots(self):
        # Equivalence fixture recorded from the 0.6.0 kernel (323 lines) on 2026-11-10.
        expect={'04_gates':('fcda9ffe8bd8d90c20cfef5c2381092c06b36923863a0559bdcf755d64489a46',['7598d51d1b92cfb4e724e82326c1214e01fea50cfdc56519b2929cc7148d6092'],'4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'),
                '15_constructor':('3f3766f4c3253f110ae95a7f5060b1c5fee1cc34d44b69d7a02f54563da64f50',['16d1f093ad71613175a161294b18c9175c84b96728729f9fd46fb475b76f103f','6c2479ca235c311dd5a50a932ec3d836664300574308e8eaa599dd3622e8f0b8','2085b32477666baec89212933622a82ca5dab32a6830c2d4e3b0dbaf77cfdfae','9ca25354c4aefab70b578e600b066b276d7d6cbdbf1d4027a3a8b8d8cbba0e09'],'f7d46d0f5ba4d9269c93d06ad0783c8fab3f4e7cd5133fc7fbf13149cf8214bf'),
                '16_bad_constructor':('37b5e5068cf6366779df3b4d53559e7875b441c8f8421d1c95471ea08850e3da',['16d1f093ad71613175a161294b18c9175c84b96728729f9fd46fb475b76f103f','6c2479ca235c311dd5a50a932ec3d836664300574308e8eaa599dd3622e8f0b8','2085b32477666baec89212933622a82ca5dab32a6830c2d4e3b0dbaf77cfdfae','1b54ddfd68490e4ed25491525aa50995f8cf366cf152b014565814f25251c2ad'],'44e458c5220f3ab8d0925b250adf3e6fde9aad36e421e05b9777a5b071938041')}
        for cid,_,_,files,execute,_ in CASES:
            if cid not in expect:continue
            r=Kernel(State.from_packs([pack(n) for n in files])).run_standing(execute=execute)['runs'][0]
            self.assertEqual((r['trace_root_sha256'],[x['sha256'] for x in r['model_receipts']],digest(r['candidates'])),expect[cid],cid)
        s=State();s.apply({'schema':'sutra-extension/2','id':'art','scope':'orgA/website','goals':['report_written'],
            'evidence':[{'predicate':'pages_built','truth':'TRUE','verified':True,'source':'fixture','version':'1'}],
            'methods':[{'id':'write-report@1','effect':'report_written','requires':['pages_built'],'provider':'local-provider',
                        'grant':'action:write-report@1','cost':{'compute':1,'money':0,'attention':0},'action':'emit_artifact','approved':True,'artifact_title':'Site report'}],
            'providers':{'local-provider':1},'grants':['action:write-report@1']})
        r=Kernel(s).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['trace_root_sha256'],r['model_receipts'][0]['sha256'],r['model_receipts'][0]['artifact_sha256'],s.fact('report_written')['source']),
            ('2bc9f551c90d021fcbbd5922ad9d23c98fb3e56dcde32c98edac9593a431f702','d91ddbb68f9681da5157bb05d4f3f906f774ee4dc73a7121bb9ccf58ea994212','538d9715aeedace8b1887e48521b0f116856b048b4a841c2fba5d79f8e7be710','LOCAL_ARTIFACT:write-report@1'))
    def test_handlers_leave_grants_budget_providers_rules_and_methods_alone(self):
        seen=[]
        def watched(fn):
            def run(s,m,mid,deps):
                before=(sorted(s.grants),dict(s.budget),dict(s.providers),digest(s.rules),digest(s.methods));out=fn(s,m,mid,deps)
                seen.append(before==(sorted(s.grants),dict(s.budget),dict(s.providers),digest(s.rules),digest(s.methods)));return out
            return run
        for cid,_,_,files,execute,_ in CASES:
            s=State(actions={k:dict(h,run=watched(h['run'])) for k,h in ACTIONS.items()})
            for n in files:s.apply(pack(n))
            Kernel(s).run_standing(execute=execute)
        self.assertTrue(len(seen)>=20 and all(seen))
    # 0.8.0-ask: a step may ask a person and wait. The kernel knows waiting, parking, decisions and hooks; the ask kind keeps its own
    # books. One test per finding of the four refuter rounds.
    STOCK={'predicate':'substitute_stock','truth':'TRUE','version':'2','verified':True,'source':'recount'}
    REVOKE={'predicate':'customer_approved','truth':'FALSE','version':'approval-v2','verified':True,'source':'fixture/revoked'}
    ZERO={'compute':0,'money':0,'attention':0};ASKS={'compute':0,'money':0,'attention':1};Q='orgA/fulfillment|'
    def _asked(self,extra=()):
        s=State.from_packs([pack(n) for n in ASK]+list(extra));k=Kernel(s);r=k.run_standing(execute=True)['runs'][0];return s,k,r
    def _open(self,s):return sorted(a['method'] for a in open_asks(s).values())
    def _m(self,mid,effect,action='simulate_fact',cost=None,req=(),**kw):
        return dict(id=mid,effect=effect,requires=list(req),provider='prov',grant='g',cost=dict(cost if cost is not None else {'compute':1,'money':0,'attention':0}),action=action,approved=True,**kw)
    def _world(self,goals,rules,methods,facts=()):
        return State.from_packs([{'schema':'sutra-extension/2','id':'t','goals':list(goals),'rules':[{'id':'R-'+h,'head':h,'branches':b,'approved':True} for h,b in rules],
            'methods':list(methods),'evidence':[{'predicate':p,'truth':t,'verified':True,'source':'fx','version':'1'} for p,t in facts],'providers':{'prov':10},'grants':['g']}])
    def _row(self,p,t,v,**kw):return dict({'predicate':p,'truth':t,'verified':True,'source':'fx','version':v},**kw)
    def _spent(self,s):return (dict(s.budget),dict(s.providers))
    def _ops(self,run):return [e['operation'] for e in run['trace']]
    def _asks(self,runs):return [x for r in runs for x in r['model_receipts'] if x['action']=='ask']
    def _kinds(self,**kinds):   # register test kinds for the length of one test: name -> handler, or (handler, hooks)
        for name,fn in kinds.items():
            run,hooks=fn if isinstance(fn,tuple) else (fn,{})
            register(name,**hooks)(run);self.addCleanup(ACTIONS.pop,name,None)
    def test_ask_parks_once_reports_only_what_ran_and_resumes_on_yes(self):
        # Counterexample: on 0.7.0 nothing could wait. The same packs without the ask end QUERY_EVIDENCE, and the kernel alone refuses the ask pack.
        self.assertEqual(Kernel(State.from_packs([pack(n) for n in ASK[:-1]])).run_standing(execute=True)['runs'][0]['status'],'QUERY_EVIDENCE')
        alone=State(actions=dict(self.KERNEL_ONLY))
        for n in ASK[:-1]:alone.apply(pack(n))
        with self.assertRaises(ValueError):alone.apply(pack(ASK[-1]))
        s,k,r=self._asked()
        self.assertEqual((r['status'],r['work_state'],r['actions'],r['pending'],r['waits']),('WAITING','waiting',['ask-customer-approval@1'],['ship-replacement@1'],['ask-customer-approval@1']))
        self.assertEqual(r['cost'],{'compute':0,'money':0,'attention':1});self.assertEqual(r['goal_truth_after'],'UNKNOWN')
        receipt=r['model_receipts'][0];self.assertEqual((len(r['model_receipts']),receipt['status'],receipt['ask']['to']),(1,'LOCAL_ONLY','customer'))
        self.assertEqual(s.fact('replacement_delivered')['truth'],'FALSE');self.assertEqual(s.fact('customer_approved')['truth'],'UNKNOWN')
        spent=self._spent(s);self.assertEqual(spent,({'compute':10,'money':10,'attention':2},{'local-provider':5,'owner-channel':1}))
        self.assertEqual(open_asks(s),{self.Q+'customer_approved':{'method':'ask-customer-approval@1','receipt':receipt['sha256'],'issued':receipt}});books=digest(s.active_work)
        for execute in (True,True,False):                    # looking again asks nothing and costs nothing, on this Kernel or a new one
            again=Kernel(s).run_standing(execute=execute)['runs'][0]
            self.assertEqual((again['status'],again['work_state'],again['model_receipts'],again['actions'],again['pending'],again['waits'],again.get('goal_truth_after'),again['cost']),
                             ('WAITING','waiting',[],[],['ship-replacement@1'],['ask-customer-approval@1'],'UNKNOWN' if execute else None,self.ZERO))
            self.assertEqual([e['data'].get('waits') for e in again['trace'] if e['operation']=='SELECT'],[['ask-customer-approval@1']]);self.assertEqual(digest(s.active_work),books)
        other=k.on_event(self.STOCK,execute=True)['runs'][0]
        self.assertEqual((other['status'],other['model_receipts']),('WAITING',[]));self.assertEqual(self._spent(s),spent)
        for _ in range(3):                                   # a direct look at a goal that does not stand asks nothing either
            direct=k.resolve('replacement_delivered',execute=True);self.assertEqual((direct['status'],direct['model_receipts']),('WAITING',[]))
        self.assertEqual(self._spent(s),spent)
        yes=answer(k,receipt,'TRUE','customer',execute=True)['runs'][0]
        self.assertEqual((yes['status'],yes['actions']),('LOCAL_MODEL_EFFECTS_RECORDED',['ship-replacement@1']))
        self.assertEqual([(e['data']['receipt'],e['data']['source']) for e in yes['trace'] if e['operation']=='ASK_CLOSED'],[(receipt['sha256'],'STAMP:customer')])
        ops=self._ops(yes);self.assertLess(ops.index('ASK_CLOSED'),ops.index('TERMINAL'));self.assertEqual(ops[-1],'TERMINAL')   # the books are settled inside the run's hash chain
        self.assertEqual(open_asks(s),{});self.assertEqual(s.active_work,{'ask':{}});stamp=s.fact('customer_approved')
        self.assertEqual((stamp['source'],stamp['version'],stamp['answers'],stamp['final'],stamp.get('depends_on')),('STAMP:customer','ask-'+receipt['sha256'][:12],receipt['sha256'],True,None))
    def test_a_direct_look_at_a_goal_that_does_not_stand_asks_once(self):
        s=State.from_packs([pack(n) for n in ASK]);k=Kernel(s)
        looks=[k.resolve('replacement_delivered',execute=True) for _ in range(3)]
        self.assertEqual([len(r['model_receipts']) for r in looks],[1,0,0]);self.assertEqual((s.budget['attention'],s.providers['owner-channel'],self._open(s)),(2,1,['ask-customer-approval@1']))
        self.assertEqual(answer(k,looks[0]['model_receipts'][0],'TRUE','customer',execute=True)['runs'][0]['actions'],['ship-replacement@1'])
    def test_a_question_stays_out_until_a_decision(self):
        s,k,r=self._asked();spent=self._spent(s)
        events=({'predicate':'customer_approved','truth':'UNKNOWN','verified':True,'source':'a verified nobody-knows','version':'u1'},
                {'predicate':'customer_approved','truth':'TRUE','verified':True,'source':'a yes resting on a dead dependency','version':'1','depends_on':[{'predicate':'nope','version':'1'}]},
                {'predicate':'customer_approved','truth':'TRUE','scope':'orgB/fulfillment','version':'b','verified':True,'source':'another tenant'},
                {'predicate':'customer_approved','truth':'TRUE','verified':False,'source':'a rumour','version':'r'},
                dict(self.REVOKE,source='the records say not approved'))   # a plain FALSE is a state of the world, not an answer
        for ev in events:
            k.on_event(ev,execute=True)
            self.assertEqual(self._open(s),['ask-customer-approval@1'],ev['source']);self.assertEqual(self._spent(s),spent,ev['source'])
            look=Kernel(s).run_standing(execute=True)['runs'][0];self.assertEqual((look['status'],look['model_receipts']),('WAITING',[]),ev['source'])
        self.assertEqual(answer(k,r['model_receipts'][0],'TRUE','customer',execute=True)['runs'][0]['actions'],['ship-replacement@1'])
    def test_an_ask_on_a_fact_that_reads_false_is_asked_once(self):
        # Round-two blocker: the lab's own approval_revoked event made the second build ask and charge on every look.
        packs=[pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission','80_ask_method')];s=State.from_packs(packs);k=Kernel(s)
        self.assertEqual(k.run_standing(execute=True)['runs'][0]['actions'],['ship-replacement@1'])   # approval on file: no question
        a=k.on_event(self.REVOKE,execute=True)['runs'][0];self.assertEqual((a['status'],a['actions']),('WAITING',['ask-customer-approval@1']))
        for _ in range(3):
            look=k.run_standing(execute=True)['runs'][0];self.assertEqual((look['status'],look['actions'],look['model_receipts']),('WAITING',[],[]))
        self.assertEqual((s.budget['attention'],s.providers['owner-channel'],self._open(s)),(2,1,['ask-customer-approval@1']))
        self.assertEqual(answer(k,a['model_receipts'][0],'TRUE','customer',execute=True)['runs'][0]['actions'],['ship-replacement@1'])
        self.assertEqual(s.budget,{'compute':6,'money':6,'attention':2})
        notyet={'schema':'sutra-extension/2','id':'notyet','evidence':[{'predicate':'customer_approved','truth':'FALSE','verified':True,'source':'fixture/reviewed','version':'1'}]}
        s=State.from_packs([pack(n) for n in ASK]+[notyet]);k=Kernel(s)
        self.assertEqual([k.run_standing(execute=True)['runs'][0]['actions'] for _ in range(3)],[['ask-customer-approval@1'],[],[]]);self.assertEqual(s.budget['attention'],2)
    def test_a_no_is_final_and_stands_against_later_rows(self):
        assume={'schema':'sutra-extension/2','id':'assume','methods':[{'id':'assume-approval@1','effect':'customer_approved','requires':[],'provider':'local-provider',
                'grant':'action:assume-approval@1','cost':{'compute':1,'money':1,'attention':0},'action':'simulate_fact','approved':True}],'grants':['action:assume-approval@1']}
        for extra in ((),(assume,)):
            s,k,r=self._asked(extra);self.assertEqual(r['actions'],['ask-customer-approval@1'])
            no=answer(k,r['model_receipts'][0],'FALSE','customer',execute=True)['runs'][0]
            self.assertEqual((no['status'],no['work_state'],no['model_receipts'],no['actions']),('REFUSED','blocked',[],[]));self.assertIn('ASK_CLOSED',self._ops(no))
            self.assertEqual(open_asks(s),{});self.assertEqual(s.budget,{'compute':10,'money':10,'attention':2})
            for row in (self.REVOKE,{'predicate':'customer_approved','truth':'UNKNOWN','verified':True,'source':'records-lost','version':'u1'},self.STOCK):
                turned=k.on_event(row,execute=True)   # later ordinary rows do not lift a decision, and nothing asks again
                if row is not self.STOCK:self.assertEqual(turned,{'status':'DECISION_STANDS','affected':[],'runs':[]})
            turned_away={'status':'DECISION_STANDS','scope':'orgA/fulfillment','predicate':'customer_approved'}
            self.assertEqual([j for j in s.event_journal if j['status']=='DECISION_STANDS'],[turned_away]*2)           # the journal says what was turned away
            s.apply(pack('03_approval'))                                                                                # nor does an older fixture that says yes: its row is turned away too
            self.assertEqual(([j for j in s.event_journal if j['status']=='DECISION_STANDS'],s.loaded[-1]['pack']),([turned_away]*3,'03_approval'))
            for execute in (False,True):
                later=Kernel(s).run_standing(execute=execute)['runs'][0];self.assertEqual((later['status'],later['actions'],later['model_receipts']),('REFUSED',[],[]))
            fact=s.fact('customer_approved');self.assertEqual((fact['truth'],fact['final'],fact['source'],s.fact('replacement_delivered')['truth'],s.budget['attention']),('FALSE',True,'STAMP:customer','FALSE',2))
            if extra:
                self.assertEqual(k._act({'actions':['assume-approval@1']}),[])   # even run by hand, a method cannot write over a decision: the step stops, unpaid
                self.assertEqual((k.events[-1]['operation'],k.events[-1]['data']['reason']),('STEP_STOPPED','Handler refused: A decision stands on this effect'))
                self.assertEqual((s.fact('customer_approved')['truth'],s.budget['compute']),('FALSE',10))
            lifted=k.on_event({'predicate':'customer_approved','truth':'TRUE','verified':True,'final':True,'source':'owner/reversal','version':'d2'},execute=True)['runs'][0]
            self.assertEqual(lifted['actions'],['ship-replacement@1'])   # only another decision replaces a decision
            self.assertEqual((k.on_event(self.REVOKE)['status'],s.fact('customer_approved')['truth']),('DECISION_STANDS','TRUE'))   # and a yes stands against an ordinary no
        for odd in (dict(final=True,truth='UNKNOWN'),dict(final='yes',truth='TRUE'),dict(final=1,truth='TRUE'),dict(final=0,truth='TRUE'),dict(final=True,truth='TRUE',depends_on=[{'predicate':'x','version':'1'}])):
            with self.assertRaises(ValueError):State().observe(dict({'predicate':'p','verified':True,'source':'fx','version':'1'},**odd))   # a decision is TRUE or FALSE and rests on nothing
        packs=[pack(n) for n in ASK]+[pack('05_learning')];s=State.from_packs(packs);k=Kernel(s);l=Learner.from_packs(packs)
        first=l.attach(k.run_standing(execute=True))['runs'][0];self.assertEqual(first['learning'],[])
        no=l.attach(answer(k,first['model_receipts'][0],'FALSE','customer',execute=True))['runs'][0]
        self.assertEqual((no['stop_reasons'],[(x['kind'],x['gap']) for x in no['learning']]),(['METHOD_ABSENT','REFUSED'],[('INVESTIGATE_GAP','METHOD_ABSENT')]))   # the no is no gap; the other route's gap still is
        s=self._world(['G'],[('G',[['p']])],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner')]);k=Kernel(s);l=Learner(enabled=True)
        only=l.attach(answer(k,k.run_standing(execute=True)['runs'][0]['model_receipts'][0],'FALSE','owner',execute=True))['runs'][0]
        self.assertEqual((only['status'],only['stop_reasons'],only['learning']),('REFUSED',['REFUSED'],[]))
        self.assertEqual([x['gap'] for x in Learner(enabled=True).learn({'status':'REFUSED','work_state':'blocked','stop_reasons':['METHOD_ABSENT','QUERY_EVIDENCE','REFUSED']})],['QUERY_EVIDENCE'])   # by the kernel's rank, not by spelling
        s=self._world(['p'],[],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner')]);k=Kernel(s)                      # a goal that is itself the asked fact
        self.assertEqual(answer(k,k.run_standing(execute=True)['runs'][0]['model_receipts'][0],'FALSE','owner',execute=True)['runs'][0]['status'],'REFUSED')
        again=k.run_standing(execute=True)['runs'][0];self.assertEqual((again['status'],again['model_receipts'],s.budget['attention']),('REFUSED',[],2))
        s=self._world(['G','G2'],[('G',[['p'],['q']]),('G2',[['p'],['h']]),('h',[['t']])],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner')],[('h','FALSE'),('t','TRUE')]);k=Kernel(s)
        runs=answer(k,self._asks(k.run_standing(execute=True)['runs'])[0],'FALSE','owner',execute=True)['runs']        # where a refusal stands in the kernel's rank of stop reasons
        self.assertEqual({r['goal']:(r['status'],r['stop_reasons']) for r in runs},{'G':('REFUSED',['QUERY_EVIDENCE','REFUSED']),'G2':('EVIDENCE_CONFLICT',['EVIDENCE_CONFLICT','REFUSED'])})
    def test_stamp_is_bound_to_the_receipt_the_kernel_issued(self):
        s,k,r=self._asked();receipt=r['model_receipts'][0]
        forged={a:b for a,b in receipt.items() if a!='sha256'};forged['ask']=dict(forged['ask'],to='mallory');forged['sha256']=digest(forged)   # rewritten and re-hashed
        mini={'method':'ask-customer-approval@1','ask':{'predicate':'customer_approved','to':'anyone'}};mini['sha256']=digest(mini)             # never issued
        bare={'ask':{'predicate':'customer_approved','to':'x'}};bare['sha256']=digest(bare)                                                     # no method at all
        fresh=Kernel(State.from_packs([pack(n) for n in ASK]))                                                                                  # nothing was asked there
        other=[pack(n) for n in ASK];other[0]=dict(other[0],scope='orgB/fulfillment');sb=State.from_packs(other);kb=Kernel(sb);kb.run_standing(execute=True)   # another tenant
        m=pack('80_ask_method')['methods'][0]                                                                                                   # the same question in another world
        sc=State.from_packs([{'schema':'sutra-extension/2','id':'refunds','scope':'orgA/fulfillment','goals':['refund_complete'],'rules':[{'id':'R-REFUND@1','head':'refund_complete','branches':[['customer_approved']],'approved':True}],
                              'methods':[m],'providers':{'owner-channel':2},'grants':[m['grant']]}]);elsewhere=Kernel(sc).run_standing(execute=True)['runs'][0]['model_receipts'][0]
        class Sly(str):
            def __str__(self):return 'mallory'
        class Liar(dict):                                                                                                                         # its items are the issued ones; what it answers is not
            def get(self,key,default=None):return {'predicate':'customer_approved','to':'mallory'} if key=='ask' else dict.get(self,key,default)
            def __getitem__(self,key):return self.get(key)
        class Both(str):
            def __eq__(self,other):return True
            __hash__=str.__hash__
        self.assertNotEqual(elsewhere['sha256'],receipt['sha256'])
        for bad in (lambda:answer(k,forged,'TRUE','mallory'),lambda:answer(k,mini,'TRUE','anyone'),lambda:answer(k,bare,'TRUE','x'),lambda:answer(fresh,bare,'TRUE','x'),
                    lambda:answer(k,Liar(receipt),'TRUE','mallory'),lambda:answer(k,receipt,Both('TRUE'),'customer'),lambda:answer(k,receipt,'TRUE',' customer '),
                    lambda:answer(k,dict(receipt,ask=dict(receipt['ask'],to=Sly('customer'))),'TRUE','mallory'),
                    lambda:answer(fresh,receipt,'TRUE','customer'),lambda:answer(kb,receipt,'TRUE','customer'),lambda:answer(k,elsewhere,'TRUE','customer'),
                    lambda:answer(k,receipt,'TRUE','a-stranger'),lambda:answer(k,receipt,'TRUE',Sly('customer')),lambda:answer(k,receipt,'MAYBE','customer'),
                    lambda:answer(k,{},'TRUE','customer'),lambda:answer(k,None,'TRUE','customer'),lambda:answer(k,dict(receipt,method='ship-replacement@1'),'TRUE','customer'),
                    lambda:answer(k,dict(receipt,extra={1,2}),'TRUE','customer'),lambda:answer(k,{**receipt,1:'x'},'TRUE','customer'),lambda:answer(k,dict(receipt,extra='\ud800'),'TRUE','customer')):
            with self.assertRaises(ValueError):bad()
        self.assertEqual((s.fact('customer_approved')['truth'],self._open(s),sb.fact('customer_approved')['truth'],self._open(sb)),('UNKNOWN',['ask-customer-approval@1'],'UNKNOWN',['ask-customer-approval@1']))
        with self.assertRaises(ValueError):answer(k,Liar(receipt),'TRUE','customer')   # a crafted object is refused at the door, whatever it says
        self.assertEqual(answer(k,dict(receipt),'TRUE','customer')['status'],'RECONCILED')   # plain data with the same content is the receipt
        with self.assertRaises(ValueError):answer(k,receipt,'FALSE','customer')   # answered once: the question is closed
        self.assertEqual((s.fact('customer_approved')['truth'],s.fact('customer_approved')['source'],open_asks(s)),('TRUE','STAMP:customer',{}))
        s2,k2,r2=self._asked();rc=r2['model_receipts'][0];books=digest(s2.active_work)
        answer(k2,rc,'FALSE','customer')                                          # a dry no: the decision is stored; the books wait for an executed run
        with self.assertRaises(ValueError):answer(k2,rc,'TRUE','customer')
        self.assertEqual((s2.fact('customer_approved')['truth'],open_asks(s2),digest(s2.active_work)),('FALSE',{},books))
        self.assertIn('ASK_CLOSED',self._ops(k2.run_standing(execute=True)['runs'][0]));self.assertEqual(s2.active_work,{'ask':{}})
        s3,k3,r3=self._asked();s3.observe({'predicate':'customer_approved','truth':'TRUE','verified':True,'source':'crm','version':'c1'})   # a yes by another channel, no run yet
        self.assertEqual((self._open(s3),answer(k3,r3['model_receipts'][0],'FALSE','customer')['status'],s3.fact('customer_approved')['source'],open_asks(s3)),
                         (['ask-customer-approval@1'],'RECONCILED','STAMP:customer',{}))   # other evidence does not close a question: the asked party's no is taken, and it stands
    def test_a_question_can_be_answered_from_the_books_when_its_result_was_lost(self):
        # Round four: a later goal that raises loses the result of an earlier goal that had asked. The receipt itself is on the books.
        def boom(s,m,mid,deps):raise RuntimeError('boom')
        register('test_raising_kind')(boom)
        try:
            s=self._world(['G1','G2'],[('G1',[['p']])],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner'),self._m('break','G2','test_raising_kind')]);k=Kernel(s)
            runs=k.run_standing(execute=True)['runs']   # the later goal's handler raises: a recorded stop, and the earlier goal's question is not lost
            self.assertEqual(([r['status'] for r in runs],runs[1]['stopped'],[j['status'] for j in s.event_journal]),(['WAITING','STEP_STOPPED'],{'method':'break','reason':'Handler failed: RuntimeError'},['WAITING','STEP_STOPPED']))
        finally:del ACTIONS['test_raising_kind']
        issued=open_asks(s)[self.Q+'p']['issued'];self.assertEqual((issued['ask']['to'],issued['method'],s.budget['attention']),('owner','ask-p',2))
        issued['ask']['to']='mallory'                                             # what open_asks hands out is a copy
        self.assertEqual(answer(k,open_asks(s)[self.Q+'p']['issued'],'TRUE','owner')['status'],'RECONCILED');self.assertEqual(s.fact('p')['source'],'STAMP:owner')
        s=self._world(['G'],[('G',[['p']])],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner')]);k=Kernel(s);k.run_standing(execute=True)   # the books are kept per scope
        s.apply({'schema':'sutra-extension/2','id':'elsewhere','scope':'orgB/other'});k.on_event(self._row('p','TRUE','1',scope='orgA/fulfillment',final=True))
        other=k.resolve('nothing_here',execute=True)                             # an executed run in another scope leaves this scope's books alone, answered or not
        self.assertEqual((open_asks(s),other['status'],'ASK_CLOSED' in self._ops(other),list(s.active_work['ask'])),({},'SEMANTICS_MISSING',False,[self.Q+'p']))
        s.apply({'schema':'sutra-extension/2','id':'back','scope':'orgA/fulfillment'})
        self.assertIn('ASK_CLOSED',self._ops(k.run_standing(execute=True)['runs'][0]));self.assertEqual(s.active_work,{'ask':{}})
    def test_other_evidence_lets_the_plan_go_on_and_leaves_the_question_out(self):
        # Round five: a question was also closed by any verified TRUE row, so a row that came back closed a question just asked and the asked party's answer was refused.
        crm={'predicate':'customer_approved','truth':'TRUE','verified':True,'source':'crm','version':'c1'}
        s,k,r=self._asked();old=r['model_receipts'][0]
        went=k.on_event(crm,execute=True)['runs'][0]   # other verified evidence: the plan goes on without the answer, and the question is still out
        self.assertEqual((went['actions'],[e for e in went['trace'] if e['operation']=='ASK_CLOSED'],open_asks(s)[self.Q+'customer_approved']['receipt']),(['ship-replacement@1'],[],old['sha256']))
        spent=self._spent(s)
        back=k.on_event({'predicate':'customer_approved','truth':'UNKNOWN','verified':True,'source':'crm-correction','version':'c2'},execute=True)['runs'][0]
        self.assertEqual((back['status'],back['actions'],back['model_receipts'],back['waits'],self._spent(s)),('WAITING',[],[],['ask-customer-approval@1'],spent))   # nobody knows any more: the same question, nobody asked or charged again
        self.assertEqual(answer(k,old,'TRUE','customer',execute=True)['runs'][0]['status'],'LOCAL_MODEL_EFFECTS_RECORDED');self.assertEqual(open_asks(s),{})
        s,k,r=self._asked();k.on_event(crm,execute=True)
        late=answer(k,r['model_receipts'][0],'FALSE','customer',execute=True)['runs'][0]   # a late no is still a decision: it blocks the fact, also where other evidence had let the plan go on
        self.assertEqual((late['status'],s.fact('customer_approved')['source'],open_asks(s)),('REFUSED','STAMP:customer',{}))
        with self.assertRaises(ValueError):answer(k,r['model_receipts'][0],'TRUE','customer')   # decided: the receipt is dead
        s,k,r=self._asked();k.on_event(crm,execute=True);spent=self._spent(s)   # round six: an honest late yes shipped and charged a second time
        yes=answer(k,r['model_receipts'][0],'TRUE','customer',execute=True)['runs'][0];row=s.fact('customer_approved')   # a late yes keeps the version of the row that already made the fact true
        self.assertEqual((yes['status'],yes['actions'],self._spent(s),row['version'],row['source'],row['final'],s.fact('replacement_delivered')['truth'],open_asks(s)),
                         ('SUPPORTED_BY_EVIDENCE',[],spent,'c1','STAMP:customer',True,'TRUE',{}))   # nothing made on the other evidence is undone or paid twice
    def test_a_question_asked_before_its_plan_is_made_again_is_paid_once_and_stays_answerable(self):
        # Round five: with the approval first among the step's needs and the quote a goal of its own, the ask was issued and paid, the old approval came back
        # with the new quote and closed the question, the customer's no was refused, and every later cycle asked and paid again.
        methods=[self._m('prepare-quote','quote'),self._m('assume-approval','approved',req=['quote'],cost={'compute':3,'money':3,'attention':0}),self._m('ship','shipped',req=['approved','quote'])]
        s=self._world(['shipped','quote'],[],methods);k=Kernel(s);k.run_standing(execute=True)
        s.apply({'schema':'sutra-extension/2','id':'ask','methods':[self._m('ask-approval','approved','ask',self.ASKS,ask_to='customer')]});receipts=[]
        for cycle in range(3):
            k.on_event(self._row('quote','FALSE',str(cycle+2)))   # the quote is withdrawn; the next look makes it again, and the old approval and shipment rows come back with it
            runs=k.run_standing(execute=True)['runs'];receipts+=self._asks(runs)
            self.assertEqual((runs[0]['status'],runs[1]['actions'],s.fact('shipped')['truth'],s.budget['attention'],self._open(s)),('WAITING',['prepare-quote'],'TRUE',2,['ask-approval']),cycle)
        self.assertEqual(len(receipts),1)   # asked once, paid once
        no=answer(k,receipts[0],'FALSE','customer',execute=True)   # the question is still out: the customer's no is a decision, and it stands
        self.assertEqual(([x['status'] for x in no['runs']],s.fact('approved')['source'],self._open(s)),(['REFUSED'],'STAMP:customer',[]))
        w=self._world(['done'],[],[self._m('ask-b','ok','ask',self.ASKS,ask_to='bob'),self._m('ask-a','ok','ask',self.ASKS,ask_to='ann'),self._m('ship','done',req=['ok'])]);kw=Kernel(w)
        first=kw.run_standing(execute=True)['runs'][0];look=kw.run_standing(execute=True)['runs'][0]   # two asks for one fact: the look waits on the one that asked, whichever was written first
        self.assertEqual((first['actions'],look['waits'],look['model_receipts'],w.budget['attention'],self._open(w)),(['ask-a'],['ask-a'],[],2,['ask-a']))
    def test_waiting_is_a_plan_chosen_like_any_other(self):
        ask_p=self._m('ask-p','p','ask',self.ASKS,ask_to='customer')
        s=self._world(['G'],[('G',[['p'],['x']])],[ask_p,self._m('make-x','x',cost={'compute':1,'money':5,'attention':2})]);k=Kernel(s)
        self.assertEqual(k.run_standing(execute=True)['runs'][0]['actions'],['ask-p']);held=self._spent(s)   # asking beats the dear route
        for _ in range(3):                                   # and waiting stays the better plan while the answer is out: the dear route does not run
            r=k.run_standing(execute=True)['runs'][0];self.assertEqual((r['status'],r['actions'],r['model_receipts']),('WAITING',[],[]))
        self.assertEqual(self._spent(s),held);self.assertEqual(s.fact('x')['truth'],'UNKNOWN')
        s,k,r=self._asked()                                  # the order: the question is out when the original item comes back in stock
        other=k.on_event({'predicate':'original_stock','truth':'TRUE','version':'2','verified':True,'source':'recount'},execute=True)['runs'][0]
        self.assertEqual((other['status'],other['actions']),('LOCAL_MODEL_EFFECTS_RECORDED',['ship-original@1']))   # the cheaper route runs
        self.assertEqual(self._open(s),['ask-customer-approval@1'])                                                  # the question stays answerable
        late=answer(k,r['model_receipts'][0],'TRUE','customer',execute=True)['runs'][0]                             # a late yes is one more true fact
        self.assertEqual((late['status'],late['actions'],s.fact('replacement_delivered')['truth'],open_asks(s)),('SUPPORTED_BY_EVIDENCE',[],'FALSE',{}));self.assertIn('ASK_CLOSED',self._ops(late))
        s=self._world(['G'],[('G',[['p','x']])],[ask_p,self._m('make-x','x')]);k=Kernel(s);k.run_standing(execute=True)   # a rule for the asked fact arrives while the question is out
        s.apply({'schema':'sutra-extension/2','id':'late-rule','rules':[{'id':'R-P','head':'p','branches':[['consent']],'approved':True}],'evidence':[self._row('consent','TRUE','1')]})
        done=k.run_standing(execute=True)['runs'][0];self.assertEqual((done['status'],done['actions'],self._open(s),s.budget['attention']),('LOCAL_MODEL_EFFECTS_RECORDED',['make-x'],['ask-p'],2))
        s=self._world(['G'],[('G',[['p']])],[ask_p]);k=Kernel(s);k.run_standing(execute=True)                          # another way to the asked fact arrives: it competes with waiting
        s.apply({'schema':'sutra-extension/2','id':'dear-way','methods':[self._m('sim-p-dear','p')]})
        self.assertEqual(k.run_standing(execute=True)['runs'][0]['status'],'WAITING')                        # dearer than waiting: the run waits
        s.apply({'schema':'sutra-extension/2','id':'free-way','methods':[self._m('sim-p','p',cost=self.ZERO)]})
        free=k.run_standing(execute=True)['runs'][0];self.assertEqual((free['actions'],self._open(s)),(['sim-p'],['ask-p']));self.assertNotIn('ASK_CLOSED',self._ops(free))   # on a tie the plan that does not wait wins, and the question stays out
        s=self._world(['G'],[('G',[['p','y'],['x']])],[ask_p,self._m('make-y','y',cost={'compute':0,'money':5,'attention':0}),self._m('make-x','x')]);k=Kernel(s)   # neither route dominates: the first preference decides
        self.assertEqual(k.run_standing(execute=True)['runs'][0]['actions'],['ask-p'])
        r=k.run_standing(execute=True)['runs'][0];self.assertEqual((r['status'],r['pending'],s.fact('x')['truth']),('WAITING',['make-y'],'UNKNOWN'))   # the wait is still cheaper in compute than the ready route
    def test_two_goals_share_one_question(self):
        for goals in (['G1','G2'],['G2','G1']):
            s=self._world(goals,[('G1',[['p'],['x']]),('G2',[['p']])],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner'),self._m('make-x','x',cost=self.ZERO,req=['x_ready'])]);k=Kernel(s)
            first=k.run_standing(execute=True)['runs'];receipts=self._asks(first);self.assertEqual((len(receipts),{r['goal']:r['status'] for r in first}),(1,{'G1':'WAITING','G2':'WAITING'}),goals)   # asked once; both goals wait on it
            ev=k.on_event(self._row('x_ready','TRUE','1'),execute=True)['runs'][0];self.assertEqual((ev['goal'],ev['actions']),('G1',['make-x']))   # G1 goes another way, looked at alone
            self.assertEqual((self._open(s),s.budget['attention']),(['ask-p'],2),goals)                               # the question is still out for G2: not asked again
            look=k.run_standing(execute=True)['runs'];self.assertEqual(({r['goal']:r['status'] for r in look}['G2'],self._asks(look),s.budget['attention']),('WAITING',[],2))
            done=answer(k,receipts[0],'TRUE','owner',execute=True)['runs'];self.assertEqual({r['goal']:r['status'] for r in done}['G2'],'SUPPORTED_BY_EVIDENCE');self.assertEqual((open_asks(s),s.budget['attention']),({},2))
    def test_one_question_per_fact_while_it_is_open(self):
        # Rounds two and three: a second ask for the same fact, and what the first was asked on, kept breaking the books. Neither matters now.
        s=self._world(['G'],[('G',[['p']])],[self._m('ask-alice','p','ask',self.ASKS,req=['quote'],ask_to='alice'),self._m('ask-bob','p','ask',self.ASKS,ask_to='bob')],[('quote','TRUE')]);k=Kernel(s)
        alice=k.run_standing(execute=True)['runs'][0]['model_receipts'][0];self.assertEqual(alice['method'],'ask-alice')
        self.assertEqual([k.run_standing(execute=True)['runs'][0]['actions'] for _ in range(2)],[[],[]])              # bob is not asked while alice's question is out
        for row in (self._row('quote','FALSE','2'),self._row('quote','UNKNOWN','3'),self._row('quote','TRUE','4')):   # nor when what alice was asked on goes, or comes back
            gone=k.on_event(row,execute=True)['runs'][0]
            self.assertEqual((gone['status'],gone['actions'],gone['pending'],gone['waits'],gone['model_receipts'],self._open(s),s.budget['attention']),('WAITING',[],[],['ask-alice'],[],['ask-alice'],2),row['truth'])
        s.apply({'schema':'sutra-extension/2','id':'carol','methods':[self._m('ask-carol','p','ask',self.ASKS,ask_to='carol')]})   # nor when a third way to ask arrives
        self.assertEqual((k.run_standing(execute=True)['runs'][0]['status'],self._open(s),s.budget['attention']),('WAITING',['ask-alice'],2))
        self.assertEqual((answer(k,alice,'TRUE','alice',execute=True)['runs'][0]['status'],s.budget['attention'],open_asks(s)),('SUPPORTED_BY_EVIDENCE',2,{}))
    def test_an_answer_stands_when_what_it_was_asked_on_is_made_again(self):
        # Round-three blockers: an answer tied to its grounds came back to life when the prerequisite was re-made. A decision now rests on nothing else.
        methods=[self._m('prepare-quote','quote_ready',req=['stock']),self._m('ask-approval','approved','ask',self.ASKS,req=['quote_ready'],ask_to='customer'),self._m('ship','done',req=['approved'])]
        for verdict,after in (('TRUE','SUPPORTED_BY_EVIDENCE'),('FALSE','REFUSED')):
            s=self._world(['done'],[],methods,[('stock','TRUE')]);k=Kernel(s);first=k.run_standing(execute=True)['runs'][0]
            runs=[first]+answer(k,first['model_receipts'][-1],verdict,'customer',execute=True)['runs']
            runs+=k.on_event(self._row('stock','FALSE','2'),execute=True)['runs']+k.on_event(self._row('stock','TRUE','3'),execute=True)['runs']+k.run_standing(execute=True)['runs']
            self.assertEqual((len(self._asks(runs)),s.budget['attention'],runs[-1]['status'],open_asks(s)),(1,2,after,{}),verdict)   # asked once, charged once, whatever the stock does
            self.assertEqual((s.fact('approved')['truth'],s.fact('approved')['final'],s.fact('approved').get('depends_on')),(verdict,True,None))
        for goals in (['done','quoted'],['quoted','done']):                                                           # and the outcome does not depend on the order of the goals
            s=self._world(goals,[('quoted',[['quote_ready']])],methods,[('stock','TRUE')]);k=Kernel(s);old=self._asks(k.run_standing(execute=True)['runs'])[0]
            recount=k.on_event(self._row('stock','TRUE','2'),execute=True)['runs'];self.assertEqual((self._asks(recount),self._open(s),s.budget['attention']),([],['ask-approval'],2),goals)
            self.assertEqual({r['goal']:r['status'] for r in answer(k,old,'TRUE','customer',execute=True)['runs']}['done'],'LOCAL_MODEL_EFFECTS_RECORDED',goals)
    def test_a_waiting_plan_is_not_an_evidence_conflict(self):
        s=self._world(['G'],[('G',[['p']])],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner')],[('G','FALSE')]);k=Kernel(s)
        self.assertEqual([k.run_standing(execute=True)['runs'][0]['status'] for _ in range(3)],['WAITING']*3);self.assertEqual(s.budget['attention'],2)
        s=self._world(['G'],[('G',[['p','p2']]),('p2',[['p']])],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner')]);k=Kernel(s);k.run_standing(execute=True)
        self.assertEqual(k.run_standing(execute=True)['runs'][0]['waits'],['ask-p'])   # one pending step waited through two conditions is listed once
        s=self._world(['G'],[('G',[['t']])],[],[('G','FALSE'),('t','TRUE')])            # the conflict itself, unchanged: evidence says no where the rule already holds
        self.assertEqual(Kernel(s).run_standing(execute=True)['runs'][0]['status'],'EVIDENCE_CONFLICT')
    def test_a_pack_applies_whole_or_not_at_all(self):
        # Counterexample: 0.7.0 kept the goals, evidence and earlier methods of a pack it then refused.
        s,k,r=self._asked();before=(digest(s.evidence),list(s.goals),sorted(s.methods),list(s.loaded),open_asks(s),sorted(s.grants),dict(s.budget));registry=s.actions
        bad={'schema':'sutra-extension/2','id':'rejected-pack','goals':['order_complete','extra_goal'],'budget':{'compute':99},'grants':['action:anything'],
             'evidence':[{'predicate':'customer_approved','truth':'TRUE','verified':True,'source':'a pack that fails its load check','version':'x1'}],
             'methods':[{'id':'ok@1','effect':'e1','requires':[],'provider':'p','grant':'g','action':'simulate_fact'},{'id':'free@1','effect':'e2','requires':[],'action':'simulate_fact'}]}
        with self.assertRaises(ValueError):s.apply(bad)
        self.assertEqual((digest(s.evidence),list(s.goals),sorted(s.methods),list(s.loaded),open_asks(s),sorted(s.grants),dict(s.budget)),before)
        self.assertEqual(k.run_standing(execute=True)['runs'][0]['status'],'WAITING')
        good={'schema':'sutra-extension/2','id':'kept','methods':[self._m('later@1','e9',cost={'compute':1,'money':0,'attention':0})],'providers':{'prov':1},'grants':['g']}
        s.apply(good);good['methods'][0]['cost']['compute']=99;good['methods'][0]['requires'].append('sneaked')        # the State keeps its own copy of what it was given
        self.assertEqual((s.methods['later@1']['cost']['compute'],s.methods['later@1']['requires']),(1,[]));self.assertIs(s.actions,registry)
    def test_methods_and_rows_are_checked_when_their_pack_is_applied(self):
        # Counterexample: 0.7.0 accepted a method with no grant and no provider and ran it; a cost in fractions stopped a run halfway; NaN poisoned a budget.
        base={'id':'m@1','effect':'e','requires':[],'provider':'p','grant':'g','cost':{'compute':0,'money':0,'attention':1},'action':'ask','approved':True,'ask_to':'owner'}
        nan=float('nan');cost=lambda **kw:dict({'compute':0,'money':0,'attention':1},**kw);drop=lambda key:{k:v for k,v in base.items() if k!=key}
        bad=[drop('ask_to'),dict(base,ask_to=''),dict(base,ask_to='  '),dict(base,ask_to=None),dict(base,cost=cost(attention=0)),dict(base,cost=cost(attention=nan)),dict(base,cost=cost(attention=1.0)),
             dict(base,cost=cost(money=float('inf'))),dict(base,cost=cost(compute=-1)),dict(base,cost=cost(compute='1')),dict(base,cost=cost(compute=0.5)),dict(base,cost=cost(compute=True)),
             dict(base,cost=cost(energy=1)),dict(base,grant=['g']),dict(base,provider=7),drop('provider'),drop('grant'),drop('effect'),dict(base,requires='e2'),dict(base,id=''),
             dict(base,cost=[1]),dict(base,requires=[7]),dict(base,question=7),dict(base,approved='no'),dict(base,approved=1),dict(base,action=['ask']),dict(base,requires=('e2',)),
             {'id':'free@1','effect':'e','requires':[],'action':'simulate_fact','approved':True}]
        for i,m in enumerate(bad):
            with self.assertRaises(ValueError,msg=i):State().apply({'schema':'sutra-extension/2','id':'bad','methods':[m]})
        for extra in ({'budget':{'compute':nan}},{'budget':{'money':float('inf')}},{'budget':{'money':2.5}},{'providers':{'p':nan}},{'providers':{'p':1.5}},
                      {'evidence':[{'predicate':'x','truth':'TRUE','verified':True,'depends_on':'y'}]},{'evidence':[{'predicate':'x','truth':'TRUE','verified':True,'depends_on':[{'version':'1'}]}]},
                      {'evidence':[{'predicate':7,'truth':'TRUE','verified':True}]},{'evidence':[{'predicate':'x','truth':'TRUE','verified':'yes'}]},{'evidence':[{'predicate':'x','truth':'TRUE','verified':1}]},
                      {'evidence':[{'predicate':'x','truth':'TRUE','verified':True,'scope':''}]},{'evidence':[{'predicate':'x','truth':'TRUE','verified':True,'scope':'a|b'}]},
                      {'scope':'a|b'},{'scope':''},{'scope':7},{'goals':'abc'},{'goals':[['a']]},{'grants':'abc'},{'revoke_grants':[7]},{'budget':{7:1}},{'providers':{7:1}},
                      {'rules':[{'id':'R','head':'h','branches':[[['x']]],'approved':True}]},{'rules':[{'id':'R','head':'h','branches':'x','approved':True}]},{'rules':[{'id':7,'head':'h','branches':[['x']]}]},
                      {'rules':[{'id':'R','head':7,'branches':[['x']],'approved':True}]},{'rules':[{'id':'R','head':'h','branches':(['x'],),'approved':True}]},{'rules':[{'id':'R','head':'h','branches':['cd'],'approved':True}]},
                      {'rules':[{'id':'R','head':'h','branches':[['x']],'approved':'false'}]},{'rules':[{'id':'R','head':'h','branches':[['x']],'approved':1}]},{'preference':{'compute':1,'money':1,'attention':1}},{'evidence':[{'predicate':'x','truth':'TRUE','verified':True,'depends_on':({'predicate':'y','version':'1'},)}]}):
            with self.assertRaises(ValueError,msg=extra):State().apply(dict({'schema':'sutra-extension/2','id':'bad'},**extra))
        twice=State();twice.apply({'schema':'sutra-extension/2','id':'one','methods':[base]})
        with self.assertRaises(ValueError):twice.apply({'schema':'sutra-extension/2','id':'two','methods':[base]})   # a method id is taken once
        for scope in ('',None,'a|b'):   # 0.7.0 stored such a row under the current scope and reported OUT_OF_SCOPE
            with self.assertRaises(ValueError):Kernel(State()).on_event({'predicate':'x','truth':'TRUE','verified':True,'scope':scope})
        for verified in (None,0,'',1,'yes'):   # only an exact false is "unverified"; anything else that is not true is a malformed row, in an event as in a pack
            with self.assertRaises(ValueError,msg=verified):Kernel(State()).on_event({'predicate':'x','truth':'TRUE','verified':verified})
        self.assertEqual([Kernel(State()).on_event(dict({'predicate':'x','truth':'TRUE'},**kw))['status'] for kw in ({},{'verified':False})],['UNVERIFIED_EVENT_IGNORED']*2)
        for whole in ([1],None,'pack',7,{'schema':'sutra-extension/2','id':7},{'schema':'sutra-extension/2','id':['p']}):   # a pack is an object with a text id, and a refusal is always a ValueError
            with self.assertRaises(ValueError,msg=whole):State().apply(whole)
        for goal in (5,None,('g',),['g']):   # a goal is a name
            with self.assertRaises(ValueError,msg=goal):Kernel(State()).resolve(goal)
        with self.assertRaises(ValueError):register('test_typo_kind',chekc=lambda m:None)   # a hook the kernel does not know is refused, not ignored
        self.assertNotIn('test_typo_kind',ACTIONS)
        State().apply({'schema':'sutra-extension/2','id':'ok','methods':[base]})
        State().apply({'schema':'sutra-extension/2','id':'ok2','budget':{'energy':3},'preference':['energy','compute','money','attention'],'methods':[dict(base,cost=cost(energy=1))]})   # a new dimension arrives with its budget
        seen=[];meddle=lambda m:(seen.append(m['id']),m.update(grant='stolen'),m['cost'].update(compute=99),m['requires'].append('sneaked'))
        register('test_meddling_kind',check=meddle)(lambda s,m,mid,deps:{})   # a check gets a deep copy and runs after the structural checks
        try:
            mine=dict(base,action='test_meddling_kind');s=State();s.apply({'schema':'sutra-extension/2','id':'x','methods':[mine]});kept=s.methods['m@1']
            self.assertEqual((mine['grant'],mine['cost']['compute'],kept['grant'],kept['cost']['compute'],kept['requires'],seen),('g',0,'g',0,[],['m@1']))
            with self.assertRaises(ValueError):State().apply({'schema':'sutra-extension/2','id':'y','methods':[dict(mine,id='n@1'),drop('grant')]})
            self.assertEqual(seen,['m@1'])   # the refused pack's first method never reached the kind's check
        finally:del ACTIONS['test_meddling_kind']
        self.assertEqual(sorted(ACTIONS['ask']),['check','plan','run','settle']);self.assertEqual(sorted(ACTIONS['simulate_fact']),['run'])
        fresh=State();ACTIONS['ask']['plan']=None
        try:self.assertIsNotNone(fresh.actions['ask']['plan'])   # a State built earlier keeps the hooks it was built with
        finally:ACTIONS['ask']['plan']=fresh.actions['ask']['plan']
    def test_a_step_already_true_at_its_turn_is_skipped_and_stored_rows_are_never_handed_out(self):
        # Round four: re-making a prerequisite brought an old approval back in the middle of a plan, and the ask step still ran and was paid.
        methods=[self._m('prepare-quote','quote'),self._m('assume-approval','approved',req=['quote'],cost={'compute':3,'money':3,'attention':0}),self._m('ship','shipped',req=['quote','approved'])]
        s=self._world(['shipped'],[],methods);k=Kernel(s);self.assertEqual(k.run_standing(execute=True)['runs'][0]['actions'],['prepare-quote','assume-approval','ship'])
        s.apply({'schema':'sutra-extension/2','id':'ask','methods':[self._m('ask-approval','approved','ask',self.ASKS,ask_to='customer')]})
        k.on_event(self._row('quote','FALSE','2'));self.assertEqual(k.run_standing()['runs'][0]['actions'],['prepare-quote','ask-approval','ship'])   # the quote is withdrawn: the plan asks
        spent=self._spent(s);r=k.run_standing(execute=True)['runs'][0]             # the new quote brings the old approval and shipment rows back (one constant version): both steps are skipped
        self.assertEqual((r['status'],r['actions'],[x['method'] for x in r['model_receipts']],r['cost'],open_asks(s),s.budget['attention'],s.providers['prov']),
                         ('LOCAL_MODEL_EFFECTS_RECORDED',['prepare-quote'],['prepare-quote'],{'compute':1,'money':0,'attention':0},{},spent[0]['attention'],spent[1]['prov']-1))
        row=s.fact('shipped');row['truth']='FALSE';row['depends_on'].clear();self.assertEqual((s.fact('shipped')['truth'],len(s.fact('shipped')['depends_on'])),('TRUE',2))   # a fact handed out is a copy
        deps=[];k.on_event({'predicate':'approved','truth':'FALSE','verified':True,'final':True,'source':'owner','version':'d1','depends_on':deps});deps.append({'predicate':'quote','version':'0'})
        self.assertEqual((s.fact('approved')['truth'],s.fact('approved')['final']),('FALSE',True))   # a row handed in is copied: the caller's list is not the State's
        look=k.run_standing()['runs'][0];look['provenance'][0]['sha256']='x';self.assertNotEqual(s.loaded[0]['sha256'],'x')
        w=self._world(['shipped'],[('approved',[['manager_ok']])],[self._m('ship','shipped',req=['approved'])],[('manager_ok','TRUE')])
        self.assertEqual(Kernel(w).run_standing()['runs'][0]['status'],'PLAN_READY')   # a known limit kept from 0.7.0: the gate reads stored evidence only, so a step resting on a condition that holds only through a rule is offered
        halt=Kernel(w).run_standing(execute=True)['runs'][0]   # since 0.9.0 the gate's refusal is a recorded stop, unpaid, where 0.8.0 raised
        self.assertEqual((halt['status'],halt['actions'],halt['stopped'],w.budget['compute']),('STEP_STOPPED',[],{'method':'ship','reason':'Prerequisite not true before effect: approved'},10))
        stored=self._world(['shipped'],[('approved',[['manager_ok']])],[self._m('ship','shipped',req=['approved'])],[('manager_ok','TRUE'),('approved','TRUE')])
        self.assertEqual(Kernel(stored).run_standing(execute=True)['runs'][0]['actions'],['ship'])   # with a stored row for the rule's head the step runs
    def test_a_skipped_step_is_on_the_record_and_every_reader_sees_the_whole_plan(self):
        # Round five: a skipped step left no line and no field, so the verifier called an honest run inconsistent and every reader saw a shorter plan.
        methods=[self._m('prepare-quote','quote'),self._m('assume-approval','approved',req=['quote'],cost={'compute':3,'money':3,'attention':0}),self._m('ship','shipped',req=['quote','approved'])]
        s=self._world(['shipped'],[],methods);k=Kernel(s);first=k.run_standing(execute=True)['runs'][0];plan=['prepare-quote','assume-approval','ship']
        k.on_event(self._row('quote','FALSE','2'));dry=k.run_standing()['runs'][0];r=k.run_standing(execute=True)['runs'][0]
        self.assertEqual((first['actions'],'skipped' in first,dry['actions'],'skipped' in dry,r['actions'],r['skipped'],r['cost']),(plan,False,plan,False,['prepare-quote'],['assume-approval','ship'],{'compute':1,'money':0,'attention':0}))
        self.assertEqual([(e['data']['method'],e['data']['effect'],e['data']['source'],e['data']['version']) for e in r['trace'] if e['operation']=='STEP_ALREADY_TRUE'],
                         [('assume-approval','approved','LOCAL_MODEL:assume-approval','local-sim-1'),('ship','shipped','LOCAL_MODEL:ship','local-sim-1')])
        impl=to_implementation(r,s);wf=impl['workflow']
        self.assertEqual(([x['method'] for x in wf['steps'] if x.get('method')],validate_workflow(wf),impl['plan']['actions'],impl['plan']['ran'],impl['plan']['skipped'],impl['plan']['cost']),
                         (plan,[],plan,['prepare-quote'],['assume-approval','ship'],{'compute':5,'money':3,'attention':0}))
        self.assertNotIn('skipped',to_implementation(first,s)['plan'])
        self.assertIn('of which still to pay {"attention":0,"compute":0,"money":0} within',wf['verify']);self.assertNotIn('over_budget',wf)
        self.assertEqual(([x['name'] for x in j2_atoms(r)['atoms']],minimal_graph_diff(first,r)['retired'],minimal_graph_diff(first,r)['added']),(plan,[],[]))
        learner=Learner(True);self.assertEqual([learner.learn(x)[0]['observations'] for x in (first,r)],[1,2])   # the same composition, seen twice
        self.assertEqual(reflect([first,r])['candidates'][0]['signature'],' -> '.join(plan))
        # a skip in front of a park: what ran, what was skipped and what is still to run are three lists, and the plan keeps its order
        steps=[self._m('make-a','a'),self._m('make-b','b',req=['a']),self._m('ship','done',req=['b','p'])]
        w=self._world(['done'],[],steps,[('p','TRUE')]);kw=Kernel(w);kw.run_standing(execute=True)
        w.apply({'schema':'sutra-extension/2','id':'ask','methods':[self._m('ask-p','p','ask',self.ASKS,ask_to='owner')]})
        kw.on_event(self._row('p','UNKNOWN','2'));kw.on_event(self._row('a','FALSE','2'));parked=kw.run_standing(execute=True)['runs'][0]
        self.assertEqual((parked['status'],parked['actions'],parked['skipped'],parked['pending'],parked['waits']),('WAITING',['make-a','ask-p'],['make-b'],['ship'],['ask-p']))
        impl=to_implementation(parked,w);order=['make-a','make-b','ask-p','ship']
        self.assertEqual(([x['method'] for x in impl['workflow']['steps'] if x.get('method')],validate_workflow(impl['workflow']),impl['plan']['cost'],impl['plan']['spent']),
                         (order,[],{'compute':3,'money':0,'attention':1},{'compute':1,'money':0,'attention':1}))
    def test_what_is_handed_in_is_rebuilt_as_plain_data(self):
        # Rounds five and six: a list that copied to itself, a dict that lied about `final`, and an object whose __eq__ kept the copy the State was about to
        # store each let a caller change stored data after the call. The door now reads by exact type and runs no code of the caller: such objects are refused.
        class Same(list):
            def __deepcopy__(self,memo):return self
        class Liar(dict):
            def get(self,key,default=None):return True if key=='final' else dict.get(self,key,default)
        class Keeps(dict):
            got=[]
            def __eq__(self,other):Keeps.got.append(other);return dict.__eq__(self,other)
            __hash__=None
        class KeepsL(list):
            def __eq__(self,other):Keeps.got.append(other);return list.__eq__(self,other)
            __hash__=None
        s,k,r=self._asked();no={'predicate':'customer_approved','truth':'FALSE','verified':True,'final':True,'source':'owner','version':'d1'}
        state=lambda:digest({'e':s.evidence,'j':s.event_journal,'m':s.methods,'l':s.loaded,'r':s.rules});before=state()
        crafted=[dict(no,depends_on=Same()),dict(no,depends_on=KeepsL()),Liar(no),Keeps(no),dict(no,note=Keeps(a=1)),dict(no,source=type('S',(str,),{})('owner')),dict(no,version=type('I',(int,),{})(1))]
        for row in crafted:
            for door in (k.on_event,s.observe,lambda x:s.apply({'schema':'sutra-extension/2','id':'c','evidence':[x]})):
                with self.assertRaises(ValueError):door(row)
        method=dict(self._m('m','e'),cost=Keeps(compute=1,money=0,attention=0),requires=KeepsL())
        for crafted_pack in ({'schema':'sutra-extension/2','id':'c','methods':[method],'providers':{'prov':1},'grants':['g']},Keeps({'schema':'sutra-extension/2','id':'c'}),
                             {'schema':'sutra-extension/2','id':'c','rules':[{'id':'R','head':'h','branches':KeepsL([['x']]),'approved':True}]}):
            with self.assertRaises(ValueError):s.apply(crafted_pack)
        self.assertEqual((Keeps.got,state(),self._open(s)),([],before,['ask-customer-approval@1']))   # no code of the caller ran, and nothing changed
        k.on_event(no,execute=True);no['source']='mallory'   # plain data is copied: the caller's own dict is not the State's
        self.assertEqual((s.fact('customer_approved')['truth'],s.fact('customer_approved')['source'],k.run_standing(execute=True)['runs'][0]['status']),('FALSE','owner','REFUSED'))
        n=len(s.event_journal);rumour={'predicate':'customer_approved','truth':'TRUE','verified':False,'source':'a rumour','version':'r'}
        self.assertEqual((k.on_event(rumour,execute=True)['status'],len(s.event_journal)),('UNVERIFIED_EVENT_IGNORED',n))   # an unverified row is ignored before it meets the decision
        s.apply({'schema':'sutra-extension/2','id':'rumour','evidence':[rumour]});self.assertEqual(len(s.event_journal),n)
        lie=k.on_event({'predicate':'customer_approved','truth':'TRUE','verified':True,'source':'mallory','version':'m'},execute=True)
        self.assertEqual((lie['status'],s.fact('customer_approved')['source'],s.event_journal[-1]['status']),('DECISION_STANDS','owner','DECISION_STANDS'))
        far=k.on_event({'predicate':'x','truth':'TRUE','verified':True,'scope':'orgB/elsewhere','source':'fx','version':'1'})
        self.assertEqual((far['status'],s.evidence['orgB/elsewhere|x']['scope']),('OUT_OF_SCOPE','orgB/elsewhere'))   # a row for another scope is stored under that scope
        row=lambda **kw:{'schema':'sutra-extension/2','id':'bad','evidence':[dict({'predicate':'x','truth':'TRUE','verified':True},**kw)]}
        nest=lambda n,x='x':x if n==0 else [nest(n-1,x)]
        for bad in (row(note=float('nan')),row(note=float('inf')),row(version='\ud800'),row(note={7:1}),row(note=(1,2)),row(note={1,2}),row(note=nest(40)),row(note=nest(16)),row(verified=None),row(final=None),row(version=['1']),
                    {'schema':'sutra-extension/2','id':'bad','evidence':[5]},{'schema':'sutra-extension/2','id':'bad','rules':[7]},{'schema':'sutra-extension/2','id':'bad','methods':'m'},
                    {'schema':'sutra-extension/2','id':'bad','providers':[1]},{'schema':'sutra-extension/2','id':'bad','budget':[1]},{'schema':'sutra-extension/2','id':'bad','preference':5},
                    {'schema':'sutra-extension/2','id':'bad','constructors':[{}]},{'schema':'sutra-extension/2','id':'bad','grants':{'g'}},{'schema':'sutra-extension/2','id':'bad','note':[0]*100001}):
            before=state()
            with self.assertRaises(ValueError):s.apply(bad)
            self.assertEqual(state(),before)   # refused whole, always with the same kind of error
        for n,ok in ((15,True),(16,False)):   # a row may nest sixteen levels: the same in a pack, in an event and handed to observe directly
            for door in (lambda x:State().apply({'schema':'sutra-extension/2','id':'d','evidence':[x]}),Kernel(State()).on_event,State().observe):
                deep={'predicate':'x','truth':'TRUE','verified':True,'note':nest(n)}
                if ok:door(deep)
                else:
                    with self.assertRaises(ValueError,msg=n):door(deep)
        for junk in ([no],'row',None,7,{'predicate':'x','truth':'TRUE','verified':True,'version':'\ud800'},{'predicate':'x','truth':'TRUE','verified':True,'\ud800':1}):   # a row is an object of plain text and numbers
            for door in (k.on_event,s.observe):
                with self.assertRaises(ValueError):door(junk)
    def test_the_stamp_reads_plain_data_and_the_books_keep_their_own_receipt(self):
        # Round five: changes to the stamp's code that passed every test. Each line here fails on one of them.
        class Quiet(dict):
            def __ne__(self,other):return False
        class Word(str):pass
        s,k,r=self._asked();issued=copy.deepcopy(r['model_receipts'][0]);r['model_receipts'][0]['ask']['to']='mallory'   # the caller edits the receipt it was given
        deep=cur=[]
        for _ in range(3000):cur.append([]);cur=cur[0]
        for receipt,truth,source in ((r['model_receipts'][0],'TRUE','mallory'),(Quiet({'ask':{'predicate':'customer_approved'}}),'TRUE','customer'),(issued,Word('TRUE'),'customer'),
                                     ({'ask':deep},'TRUE','customer'),(dict(issued,parked=1),'TRUE','customer'),({'ask':{}},'TRUE','customer'),([issued],'TRUE','customer')):
            with self.assertRaises(ValueError):answer(k,receipt,truth,source)
        self.assertEqual((open_asks(s)[self.Q+'customer_approved']['issued'],answer(k,issued,'TRUE','customer')['status']),(issued,'RECONCILED'))
    def test_books_are_kept_per_scope_and_a_step_never_waits_for_a_later_one(self):
        # Round six. The books: with two scopes whose names have the same length, a decision in one scope must not close the other scope's question.
        s=self._world(['G'],[('G',[['p']])],[self._m('ask-p','p','ask',self.ASKS,ask_to='owner')]);k=Kernel(s);k.run_standing(execute=True)
        s.apply({'schema':'sutra-extension/2','id':'elsewhere','scope':'orgB/fulfillment'});k.on_event(self._row('p','TRUE','1',final=True),execute=True)
        other=k.resolve('nothing_here',execute=True)
        self.assertEqual((open_asks(s),'ASK_CLOSED' in self._ops(other),list(s.active_work['ask'])),({},False,[self.Q+'p']))
        # The generator: two free methods make the same fact. The plan holds both, the second is skipped at its turn, and every step is ordered after the FIRST maker.
        free=lambda mid:self._m(mid,'e',cost=self.ZERO)
        for execute,ran in ((False,['m1','x','m2','y']),(True,['m1','x','y'])):
            w=self._world(['G'],[('G',[['fx','fy']])],[free('m1'),free('m2'),self._m('x','fx',req=['e']),self._m('y','fy',req=['e'])]);r=Kernel(w).run_standing(execute=execute)['runs'][0]
            wf=to_implementation(r,w)['workflow']
            self.assertEqual((r['actions'],[st['method'] for st in wf['steps'] if st.get('method')],validate_workflow(wf),sorted((e['from'],e['to']) for e in wf['edges'])),
                             (ran,['m1','x','m2','y'],[],[('m1','x'),('m1','y')]),execute)
    def test_the_door_compares_types_by_identity_and_reads_each_container_once(self):
        # Round seven. The door asked `t in (int, bool, NoneType)`: `in` compares with ==, and == on a class is answered by its metaclass, so an object whose
        # metaclass said yes was kept as it was, and the State held the caller's own object. Types are now compared by identity: the metaclass is never asked.
        class Yes(type):
            calls=[]
            __hash__=type.__hash__
            def __eq__(c,o):Yes.calls.append(o);return True
        class Box(metaclass=Yes):pass
        class Cost(dict,metaclass=Yes):pass
        class Word(str,metaclass=Yes):pass
        s,k,r=self._asked();state=lambda:digest({'e':s.evidence,'j':s.event_journal,'m':s.methods,'l':s.loaded,'r':s.rules});before=state()
        row={'predicate':'x','truth':'TRUE','verified':True,'source':'fx','version':'1'}
        for crafted in (Box(),Cost(compute=1),Word('fx')):
            for door in (k.on_event,s.observe,lambda x:s.apply({'schema':'sutra-extension/2','id':'c','evidence':[x]})):
                with self.assertRaises(ValueError):door(dict(row,note=crafted))
            with self.assertRaises(ValueError):s.apply({'schema':'sutra-extension/2','id':'c','methods':[dict(self._m('m','e'),cost=crafted)],'providers':{'prov':1},'grants':['g']})
            with self.assertRaises(ValueError):answer(k,dict(r['model_receipts'][0],note=crafted),'TRUE','customer')
        self.assertEqual((Yes.calls,state(),self._open(s)),([],before,['ask-customer-approval@1']))
        # The door read a dict twice (its keys, then its pairs). The caller's own garbage, collected in between, could rewrite the dict, and a number key reached
        # the State. The door now takes one snapshot of the pairs: whatever such code does, what is stored has text keys, and every refusal is a ValueError.
        import gc
        target={'a':[[] for _ in range(40)],'b':2};turn=[0,True]
        class Junk:
            def __del__(self):
                if turn[1]:
                    turn[0]+=1
                    if turn[0]%2:target.pop('b',None);target[5]='five'
                    else:target.pop(5,None);target['b']=2
                    j=Junk();j.me=j   # more garbage, so the next collection runs this again
        old=gc.get_threshold();gc.collect();seen=set()
        try:
            gc.set_threshold(1,100000,100000);j=Junk();j.me=j;del j
            for _ in range(200):
                w=State()
                try:w.observe(dict(row,note=target))
                except ValueError:seen.add('refused');continue
                seen.add('text keys' if all(type(key) is str for key in w.evidence[self.Q+'x']['note']) else 'a number key')
        finally:turn[1]=False;gc.set_threshold(*old);gc.collect()
        self.assertLessEqual(seen,{'refused','text keys'})
        self.assertGreater(turn[0],200)   # the garbage really was collected while the door read
        # Garbage that GROWS the dict at every collection: the dict changes size while the door reads it. That is a refusal like any other, a ValueError
        # (before Python 3.12 the collection runs inside the read; from 3.12 it runs between the door's steps, and the copy is then simply the grown dict).
        grown={'a':1};turn[:]=[0,True];seen=set()
        class Grows:
            def __del__(self):
                if turn[1]:turn[0]+=1;grown['k%d'%turn[0]]=turn[0];g=Grows();g.me=g
        gc.collect()
        try:
            gc.set_threshold(1,100000,100000);g=Grows();g.me=g;del g
            for _ in range(50):
                w=State()
                try:w.observe(dict(row,note=grown));seen.add('text keys' if all(type(key) is str for key in w.evidence[self.Q+'x']['note']) else 'a number key')
                except ValueError:seen.add('refused')
        finally:turn[1]=False;gc.set_threshold(*old);gc.collect()
        self.assertLessEqual(seen,{'refused','text keys'})
        if sys.version_info<(3,12):self.assertIn('refused',seen)
        # A list is read item by item: garbage that empties or refills the list while the door reads it gives a plain copy or a refusal, never anything else.
        items=[[i] for i in range(60)];turn[:]=[0,True];seen=set()
        class Empties:
            def __del__(self):
                if turn[1]:
                    turn[0]+=1
                    if turn[0]%2:del items[:]
                    else:items.extend([i] for i in range(60))
                    e=Empties();e.me=e
        gc.collect()
        try:
            gc.set_threshold(1,100000,100000);e=Empties();e.me=e;del e
            for _ in range(100):
                w=State()
                try:w.observe(dict(row,note=items));seen.add('plain' if all(type(x) is list and all(type(y) is int for y in x) for x in w.evidence[self.Q+'x']['note']) else 'not plain')
                except ValueError:seen.add('refused')
        finally:turn[1]=False;gc.set_threshold(*old);gc.collect()
        self.assertLessEqual(seen,{'refused','plain'})
        # An integer the canonical form could not print on a newer Python (more than 4300 digits) is refused at the door, not after the row is stored.
        big=10**4300;w=State();w.observe(dict(row,note=big-1));self.assertTrue(w.evidence[self.Q+'x']['note']==big-1)
        w=State();w.observe(dict(row,note=1-big));self.assertTrue(w.evidence[self.Q+'x']['note']==1-big)   # the same bound below zero
        for door in (State().observe,Kernel(State()).on_event,lambda x:State().apply({'schema':'sutra-extension/2','id':'c','evidence':[x]})):
            for n in (big,-big):
                with self.assertRaises(ValueError):door(dict(row,note=n))
    def test_a_method_the_door_lets_in_can_run_and_versions_compare_as_json(self):
        # Round seven. The row a step writes names every prerequisite, and it went through the bound meant for callers: a method with about 20000 prerequisites
        # was let in and could never run. A method may now require at most 10000 facts, and the largest one runs.
        def world(n):
            w=self._world(['g'],[],[self._m('m','g',req=['r%d'%i for i in range(n)])])
            for i in range(n):w.observe(self._row('r%d'%i,'TRUE','1'))
            return w
        with self.assertRaises(ValueError):world(10001)
        w=world(10000);self.assertEqual((Kernel(w).resolve('g',execute=True)['status'],len(w.evidence[self.Q+'g']['depends_on'])),('LOCAL_MODEL_EFFECTS_RECORDED',10000))
        # A version is a name or a number and compares as JSON text, as the stamp and the verifier compare: 1 and 1.0 are two versions, and true is not a version.
        w=self._world(['g'],[],[self._m('m','g',req=['p'])]);k=Kernel(w);w.observe(self._row('p','TRUE',1));k.resolve('g',execute=True)
        self.assertEqual((w.fact('g')['truth'],w.evidence[self.Q+'g']['depends_on']),('TRUE',[{'predicate':'p','version':1}]))
        w.observe(self._row('p','TRUE',1.0));self.assertEqual(w.fact('g')['truth'],'UNKNOWN')   # the prerequisite carries another version now
        w.observe(self._row('p','TRUE',1));self.assertEqual(w.fact('g')['truth'],'TRUE')
        for door in (w.observe,k.on_event,lambda x:w.apply({'schema':'sutra-extension/2','id':'v','evidence':[x]})):
            with self.assertRaises(ValueError):door(self._row('p','TRUE',True))
    def test_the_bounds_of_the_door_and_the_versions_of_late_answers_are_pinned(self):
        # Round seven's surviving mutants: changes to these lines that no test noticed.
        row=lambda **kw:dict({'predicate':'x','truth':'TRUE','verified':True},**kw);nest=lambda n,x='x':x if n==0 else [nest(n-1,x)]
        State().observe(row(note=[0]*99991))                                        # 100000 items with the row, its keys and the list: let in
        with self.assertRaises(ValueError):State().observe(row(note=[0]*99992))    # one more is refused
        with self.assertRaises(ValueError):State().observe(row(version={'a':1}))
        State().apply({'schema':'sutra-extension/2','id':'deep','note':nest(17)})   # a pack may nest eighteen levels below its top
        with self.assertRaises(ValueError):State().apply({'schema':'sutra-extension/2','id':'deep','note':nest(18)})
        class Name(str):pass
        with self.assertRaises(ValueError):Kernel(State()).resolve(Name('g'))
        # A late no, and a yes on a fact that other evidence reads FALSE, are new decisions: they carry the question's own version, never the standing row's.
        for standing,truth in (('TRUE','FALSE'),('FALSE','TRUE')):
            s,k,r=self._asked();k.on_event(self._row('customer_approved',standing,'other-1'),execute=True)
            answer(k,r['model_receipts'][0],truth,'customer',execute=True)
            self.assertEqual((s.fact('customer_approved')['truth'],s.fact('customer_approved')['version']),(truth,'ask-'+r['model_receipts'][0]['sha256'][:12]))
    def test_the_generator_gives_every_step_its_own_id_and_one_edge_per_prerequisite(self):
        # Round seven: a prerequisite listed twice gave four equal edges, and two methods whose names give one slug shared a step id, so the edge between them was lost.
        w=self._world(['done'],[],[self._m('make a','a'),self._m('make-b','b',req=['a','a']),self._m('make.b','done',req=['b'])]);r=Kernel(w).run_standing()['runs'][0]
        wf=to_implementation(r,w)['workflow'];steps=[x for x in wf['steps'] if x.get('method')]
        self.assertEqual(([x['id'] for x in steps],[x['after'] for x in steps],validate_workflow(wf)),(['make-a','make-b','make-b-2'],[[],['make-a'],['make-b']],[]))
        self.assertEqual([(e['from'],e['to'],e['via']) for e in wf['edges']],[('make-a','make-b','a'),('make-b','make-b-2','b')])
        self.assertIn('two steps share one id',validate_workflow(dict(wf,steps=wf['steps']+[dict(steps[0])])))
        # Three names of one slug, and two methods named like the workflow's own first and last step: every id is still its own, and a step that needs
        # what a suffixed step makes waits for that step.
        chain=[self._m('x','a'),self._m('x@','b',req=['a']),self._m('x.','c',req=['b']),self._m('show-it','d',req=['c']),self._m('record-intent','done',req=['d'])]
        w=self._world(['done'],[],chain);wf=to_implementation(Kernel(w).run_standing()['runs'][0],w)['workflow'];steps=[x for x in wf['steps'] if x.get('method')]
        self.assertEqual(([x['id'] for x in wf['steps']],[x['after'] for x in steps],validate_workflow(wf)),
                         (['record-intent','x','x-2','x-3','show-it-2','record-intent-2','show-it'],[[],['x'],['x-2'],['x-3'],['show-it-2']],[]))
        self.assertEqual([(e['from'],e['to'],e['via']) for e in wf['edges']],[('x','x-2','a'),('x-2','x-3','b'),('x-3','show-it-2','c'),('show-it-2','record-intent-2','d')])
    def test_what_round_eight_of_the_ask_version_left_is_closed(self):
        # Round eight of 0.8.0 refuted nothing and left three stated limits (a fix that needs new code goes to the next version, R19). 0.9.0 removes them:
        # the build before accepted every call refused below.
        w=State()
        for v in (True,False,{'n':1},[1]):   # a version named inside depends_on is held to the rule for a row's own version
            with self.assertRaises(ValueError):w.observe({'predicate':'z','truth':'TRUE','verified':True,'depends_on':[{'predicate':'q','version':v}]})
        self.assertEqual(w.evidence,{})
        self.assertTrue(w.observe({'predicate':'z','truth':'TRUE','verified':True,'depends_on':[{'predicate':'q','version':None},{'predicate':'r','version':2},{'predicate':'t','version':'v1'},{'predicate':'u'}]}))
        s=self._world(['g'],[],[self._m('m','g')]);k=Kernel(s);books=lambda:digest({'evidence':s.evidence,'journal':s.event_journal,'budget':s.budget,'providers':s.providers})
        before=books();event={'predicate':'q','truth':'TRUE','verified':True,'source':'fx','version':'1'}
        for flag in (1,0,'yes',None,[True]):   # execute is exactly true or false: refused before a row is stored or a step runs
            for call in (lambda:k.resolve('g',execute=flag),lambda:k.run_standing(execute=flag),lambda:k.on_event(event,execute=flag)):
                with self.assertRaises(ValueError):call()
        self.assertEqual(books(),before)
        with self.assertRaises(ValueError):Kernel(State()).run_standing(execute=1)   # with no goal to run as well
        self.assertEqual(k.resolve('g',execute=True)['status'],'LOCAL_MODEL_EFFECTS_RECORDED')
        a,ka,ra=self._asked();asked=digest(open_asks(a))   # the stamp passes the flag on: a wrong one is refused and the question stays out
        with self.assertRaises(ValueError):answer(ka,ra['model_receipts'][0],'TRUE','customer',execute=1)
        self.assertEqual((digest(open_asks(a)),a.fact('customer_approved')['truth']),(asked,'UNKNOWN'))
        base={'schema':'sutra-extension/2','id':'x','goals':['b'],'grants':['g'],'providers':{'prov':2}}
        for bad in (10**18,10**4300-1):   # an amount is below 10**18: a cost, a budget entry, a provider's capacity
            for part in ({'budget':{'compute':bad}},{'providers':{'prov':bad}},{'methods':[self._m('ma','b',cost={'compute':bad})]}):
                with self.assertRaises(ValueError):State().apply(dict(base,**part))
        for part in ({'budget':{'compute':None}},{'providers':{'prov':None}},{'methods':[self._m('ma','b',cost={'compute':None})]}):   # review round three: null is no amount either (a kernel that took it passed every test)
            with self.assertRaises(ValueError):State().apply(dict(base,**part))
        top=10**18-1;w=State();w.apply(dict(base,budget={'compute':top},methods=[self._m('ma','a',cost={'compute':top}),self._m('mb','b',cost={'compute':top},req=['a'])]))
        r=Kernel(w).resolve('b');self.assertEqual(r['status'],'RESOURCE_REQUIRED')   # the two largest amounts add up, and the sum is written down on every Python
        self.assertEqual([e['data']['cost']['compute'] for e in r['trace'] if e['operation']=='ADMISSION'],[2*top])
    def test_the_verifier_holds_a_number_to_its_type_and_a_blocked_run_to_the_ranking(self):
        # Round eight of 0.8.0: a row numbered true or 2.0 passed the chain check, and a BLOCK row was compared with nothing. Both checks are module-level functions.
        spec=importlib.util.spec_from_file_location('independent_verify',ROOT/'qa'/'independent_verify.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
        s=self._world(['g'],[],[self._m('m','g',req=['absent'])]);r=Kernel(s).resolve('g');self.assertEqual(r['work_state'],'blocked')
        def chained(change):   # the trace changed and hashed again, as a forger would
            t=json.loads(json.dumps(r['trace']));change(t);prev='GENESIS'
            for row in t:row['prev_sha256']=prev;row['sha256']=v.sha({k:x for k,x in row.items() if k!='sha256'});prev=row['sha256']
            return t
        self.assertTrue(v.check_chain(chained(lambda t:None)))
        for n in (True,1.0):self.assertFalse(v.check_chain(chained(lambda t:t[0].update(seq=n))))
        block=[e['data'] for e in r['trace'] if e['operation']=='BLOCK'][0];self.assertTrue(v.block_ok(block))
        for forged in (dict(block,reason='LOCAL_MODEL_EFFECTS_RECORDED'),dict(block,reason='CYCLE_LIMIT'),dict(block,all_reasons=block['all_reasons']+['NO_SUCH_REASON']),
                       dict(block,all_reasons=block['all_reasons']*2),dict(block,all_reasons=None),dict(block,all_reasons=[]),{}):
            self.assertFalse(v.block_ok(forged),forged)
        self.assertTrue(v.block_ok({'reason':'METHOD_ABSENT','all_reasons':[]}))   # a known limit (review round three): a blocked run that names no reason at all passes when it is worded METHOD_ABSENT. That is the kernel's own word for it, but the kernel writes it only on a State changed by hand:
        with self.assertRaises(ValueError):self._world(['g'],[('g',[])],[])   # no pack can deliver a rule with no branch,
        self.assertEqual(Kernel(self._world(['g'],[],[])).resolve('g')['stop_reasons'],['SEMANTICS_MISSING'])   # a goal with nothing names its reason,
        hand=self._world(['g'],[],[]);hand.rules['g']={'id':'R-g','head':'g','branches':[]};b=Kernel(hand).resolve('g')   # and only a rule with no branch put into the State by hand gives a blocked look with no reason
        self.assertEqual((b['status'],b['stop_reasons'],[e['data'] for e in b['trace'] if e['operation']=='BLOCK']),('METHOD_ABSENT',[],[{'reason':'METHOD_ABSENT','all_reasons':[]}]))
        for k in Kernel.RANK:self.assertIn(k,v.RANK)   # the verifier's copy is the kernel's list, in its order
        self.assertEqual(list(v.RANK),Kernel.RANK)
    def test_a_step_that_stops_is_on_the_record_and_never_an_exception(self):
        # 0.8.0 and before: a handler, the gate or a settle hook that raised in the middle of a plan ended the run with an exception. The steps before it stayed
        # done and paid, the journal got no row, a second goal never ran. Now the run returns, says where it stopped and why, and pays only what has a receipt.
        packs=[pack(n) for n in ('30_build_goal','31_build_theory','82_components_without_constructor')]
        s=State.from_packs(packs);k=Kernel(s);before=self._spent(s)
        self.assertEqual(k.run_standing()['runs'][0]['status'],'PLAN_READY')   # the dry look cannot tell that the last step has no constructor
        r=k.run_standing(execute=True)['runs'][0];paid=self._spent(s)
        self.assertEqual((r['status'],r['work_state'],len(r['model_receipts']),r['actions'],r['stopped']['reason'],r['pending'],r['goal_truth_after']),
                         ('STEP_STOPPED','stopped',3,[x['method'] for x in r['model_receipts']],'Handler refused: No declared constructor',[r['stopped']['method']],s.fact(r['goal'])['truth']))
        self.assertEqual(self._ops(r)[-2:],['STEP_STOPPED','TERMINAL']);self.assertEqual((s.event_journal[-1]['status'],s.event_journal[-1]['trace_root_sha256']),('STEP_STOPPED',r['trace_root_sha256']))
        cost={d:sum(s.methods[a]['cost'].get(d,0) for a in r['actions']) for d in before[0]}
        self.assertEqual((r['cost'],{d:before[0][d]-paid[0][d] for d in cost},sum(before[1].values())-sum(paid[1].values())),(cost,cost,3))   # paid: exactly the three receipts; the stopped step costs nothing
        again=k.run_standing(execute=True)['runs'][0]   # a second look pays nothing more and names the same step and reason
        self.assertEqual((again['status'],again['stopped'],again['model_receipts'],self._spent(s)),('STEP_STOPPED',r['stopped'],[],paid))
        twin=Kernel(State.from_packs(packs)).run_standing(execute=True)['runs'][0];self.assertEqual(twin['trace_root_sha256'],r['trace_root_sha256'])   # the same stop, the same record
        impl=to_implementation(r,s);self.assertEqual(impl['workflow']['stopped'],r['stopped']);self.assertTrue(any('stopped at' in p for p in validate_workflow(impl['workflow'])))
        self.assertEqual((reflect([r,r])['candidates'],Learner(True).learn(r)),([],[]))   # a stopped run is no composition to reuse
        bad=copy.deepcopy(pack('32_builder_components'));bad['constructors'][0]['components']='abc'   # a constructor spec of the wrong shape stops at its step, on the record, and stores nothing
        w=State.from_packs([pack('30_build_goal'),pack('31_build_theory'),bad]);r2=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r2['status'],r2['stopped']['reason'],w.candidates),('STEP_STOPPED','Handler refused: Components unavailable',{}))
        # every way a step can fail ends the same way: a recorded stop with a fixed reason, and nothing paid for the stopped step
        def wrote_then_failed(s,m,mid,deps):s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':f'LOCAL_MODEL:{mid}','version':'local-sim-1'});raise OSError('disk')
        def drops_grant(s,m,mid,deps):s.grants.discard('g');s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':f'LOCAL_MODEL:{mid}','version':'local-sim-1'});return {}
        def bad_settle(s,result,log):raise KeyError('books')
        kinds={'test_none':lambda s,m,mid,deps:None,'test_list':lambda s,m,mid,deps:['x'],'test_set':lambda s,m,mid,deps:{'x':{1,2}},'test_field':lambda s,m,mid,deps:{'sha256':'0'},
               'test_oserror':wrote_then_failed,'test_meddle':drops_grant}
        for name,fn in kinds.items():register(name)(fn)
        register('test_bad_settle',settle=bad_settle)(lambda s,m,mid,deps:{});register('test_bad_plan',plan=lambda s,m:1/0)(lambda s,m,mid,deps:{})
        try:
            cannot='Handler returned what cannot be a receipt'
            for name,reason,reads in (('test_none',cannot,'UNKNOWN'),('test_list',cannot,'UNKNOWN'),('test_set',cannot,'UNKNOWN'),('test_field',cannot,'UNKNOWN'),('test_oserror','Handler failed: OSError','TRUE')):
                w=self._world(['e'],[],[self._m('m','e',name)]);r=Kernel(w).run_standing(execute=True)['runs'][0];row=[e['data'] for e in r['trace'] if e['operation']=='STEP_STOPPED'][0]
                self.assertEqual((r['status'],r['stopped'],row['effect_reads'],self._spent(w)[0],r['model_receipts']),('STEP_STOPPED',{'method':'m','reason':reason},reads,{'compute':10,'money':10,'attention':3},[]),name)
            w=self._world(['done'],[],[self._m('first','a','test_meddle'),self._m('second','done',req=['a'])]);r=Kernel(w).run_standing(execute=True)['runs'][0]   # the gate changes in the middle of a plan
            self.assertEqual((r['actions'],r['stopped'],r['pending'],w.budget['compute']),(['first'],{'method':'second','reason':'Gate changed before effect: AUTHORITY_REQUIRED'},['second'],9))
            w=self._world(['G1','G2'],[],[self._m('m1','G1','test_oserror'),self._m('m2','G2')]);k=Kernel(w)   # a stop does not take the next goal down with it, and an event returns its runs
            self.assertEqual([x['status'] for x in k.run_standing(execute=True)['runs']],['STEP_STOPPED','LOCAL_MODEL_EFFECTS_RECORDED'])
            self.assertEqual([x['status'] for x in k.on_event(self._row('G1','FALSE','2'),execute=True)['runs']],['STEP_STOPPED'])
            s2,k2,r2=self._asked()   # a kind whose settle fails is named; the run returns, the ask kind has kept its books, the journal has its row
            self.assertEqual((r2['status'],r2['unsettled'],[e['data'] for e in r2['trace'] if e['operation']=='SETTLE_STOPPED'],self._open(s2),len(s2.event_journal)),
                             ('WAITING',['test_bad_settle'],[{'kind':'test_bad_settle','reason':'KeyError'}],['ask-customer-approval@1'],1))
            w=self._world(['e'],[],[self._m('m','e','test_bad_plan')])
            with self.assertRaises(ZeroDivisionError):Kernel(w).run_standing()   # a known limit: a plan hook that raises ends the look before anything runs
            self.assertEqual((w.event_journal,w.budget['compute']),([],10))
        finally:
            for name in list(kinds)+['test_bad_settle','test_bad_plan']:del ACTIONS[name]
    def test_the_planner_offers_what_0_8_0_offered_and_a_plan_that_must_stop_is_recorded(self):
        # Review round one on 0.9.0. Its first build did not offer a step that rests on a rule's head whose row does not read TRUE. That hid plans 0.8.0 completes
        # and worded a person's no, and a row its rule contradicts, as missing evidence. The rule is cut: planning is 0.8.0's again, and a plan that must stop is recorded.
        stale=self._row('approved','TRUE','1',depends_on=[{'predicate':'manager_ok','version':'local-sim-1'}])
        w=self._world(['shipped'],[('approved',[['manager_ok']])],[self._m('get-ok','manager_ok'),self._m('ship','shipped',req=['approved'])]);w.observe(stale)
        r=Kernel(w).run_standing(execute=True)['runs'][0]   # the first step makes the stored row of the rule's head valid again: the plan completes, as on 0.8.0
        self.assertEqual((r['status'],r['actions'],w.fact('shipped')['truth']),('LOCAL_MODEL_EFFECTS_RECORDED',['get-ok','ship'],'TRUE'))
        s=State.from_packs([pack('81_made_again')]);k=Kernel(s);k.run_standing(execute=True)   # the lab's own pack, then a rule for a fact its methods had already made
        s.apply({'schema':'sutra-extension/2','id':'late-rule','rules':[{'id':'R-QUOTE@1','head':'quote_approved','branches':[['quote_ready']],'approved':True}]})
        k.on_event(self._row('quote_ready','FALSE','2'));r=k.run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'],r['actions'],r.get('skipped'),s.fact('order_shipped')['truth']),('LOCAL_MODEL_EFFECTS_RECORDED',['prepare-quote@1'],['ship-quoted@1'],'TRUE'))
        rested=lambda facts:self._world(['x'],[('h',[['c']])],[self._m('A','x',req=['h'])],facts)
        no=rested([]);no.observe(self._row('h','FALSE','d1',final=True));r=Kernel(no).run_standing(execute=True)['runs'][0]   # a decision against the rule's head is a no, not missing evidence
        self.assertEqual((r['status'],r['stop_reasons'],Learner(True).learn(r),'REFUSED' in self._ops(r)),('REFUSED',['REFUSED'],[],True))
        r=Kernel(rested([('h','FALSE'),('c','TRUE')])).run_standing()['runs'][0]   # a stored row that its own rule contradicts is a conflict
        self.assertEqual((r['status'],r['stop_reasons']),('EVIDENCE_CONFLICT',['EVIDENCE_CONFLICT']))
        w=self._world(['shipped'],[('approved',[['manager_ok']])],[self._m('get-ok','manager_ok'),self._m('ship','shipped',req=['approved'])]);k=Kernel(w)
        self.assertEqual(k.run_standing()['runs'][0]['status'],'PLAN_READY')   # the known limit: no step stores a row for the rule's head, so this plan must stop, and it is still offered
        looks=[k.run_standing(execute=True)['runs'][0] for _ in (1,2)]
        self.assertEqual([(x['status'],x['actions'],x['stopped']['reason']) for x in looks]+[self._spent(w)],   # the step before the stop ran and was paid once; the stop itself costs nothing, at every look
                         [('STEP_STOPPED',['get-ok'],'Prerequisite not true before effect: approved'),('STEP_STOPPED',[],'Prerequisite not true before effect: approved'),({'compute':9,'money':10,'attention':3},{'prov':9})])
    def test_whatever_a_handler_raises_or_returns_is_a_receipt_or_one_stop_line(self):
        # Review round one on 0.9.0. The first build worded a stop with text Python made (a RuntimeError's message, an error's str), wrote the stop line and the receipt's
        # line outside the guard, read what a handler returned with the handler's own code, and paid in two statements. Each world below ended a look with an exception,
        # paid a stopped step, or recorded a forged receipt. Review round two: the name of an error's class was still asked of the class, so a class that gave no text
        # for its name ended the look with TypeError or worded its stop with a gate's phrase. The name is read from the type itself now and taken only when it is plain.
        asked=[]   # every call into the code of an error's class, or of a text that is not exact text
        class Liar(type):   # an error class that raises when it is asked for its name
            @property
            def __name__(cls):asked.append(cls);raise SystemExit(3)
        class Says(type):   # an error class that gives a name UTF-8 cannot carry
            __name__=property(lambda cls:asked.append(cls) or 'Caf\udce9Error')
        class Thing:   # no text at all: asked to become text it gives itself, and added to the kernel's phrase it gives a gate's words
            def encode(self,*a):asked.append(self);return self
            def decode(self,*a):asked.append(self);return self
            def __radd__(self,other):asked.append(self);return 'Gate changed before effect: PROVIDER_REQUIRED'
        class Mute(type):   # an error class that gives such a thing for its name
            __name__=property(lambda cls:asked.append(cls) or Thing())
        class Text(str):   # text of a class of its own, with code of its own
            def encode(self,*a):asked.append(self);return Thing()
            def isascii(self):asked.append(self);return True
            def isidentifier(self):asked.append(self);return True
        class Renamed(Exception):pass
        Renamed.__name__=Text('Renamed')   # Python keeps a name as it was given: here, text of that class
        def runaway(s,m,mid,deps):return runaway(s,m,mid,deps)   # a handler that calls itself until the stack is used up
        class Odd(int):
            def __bool__(self):raise KeyError('odd')
        class Lies:   # says it has two keys; iterating it shows none
            def __iter__(self):return iter(())
            def keys(self):return ['status','method']
            def __getitem__(self,key):return {'status':'EXTERNAL_DONE','method':'m2'}[key]
        class Late(dict):
            def keys(self):raise Stop('Gate changed before effect: AUTHORITY_REQUIRED')
        class Sub(Stop):pass
        class Sly(Exception):   # an error that answers Stop when it is asked for its class
            __class__=property(lambda self:asked.append(self) or Stop)
        def deep(n):   # an object holding n levels of lists
            v=[]
            for _ in range(n-1):v=[v]
            return {'x':v}
        def grows(s,m,mid,deps):
            d={'a':1}
            for key in d:d[key+'x']=1
        def pops(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));s.providers.pop(m['provider']);return {}
        def drops(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));s.methods.pop('later');return {}
        cannot='Handler returned what cannot be a receipt'
        worlds=[('its own words',_throw(Stop('no room on the shelf')),'Handler refused: no room on the shelf'),
                ('words UTF-8 cannot carry',_throw(Stop('cannot read caf\udce9.txt')),'Handler refused: cannot read caf\\udce9.txt'),
                ("Python's own RuntimeError",grows,'Handler failed: RuntimeError'),
                ('a RuntimeError with such words',_throw(RuntimeError('cannot read caf\udce9.txt')),'Handler failed: RuntimeError'),
                ('a subclass of Stop',_throw(Sub('words')),'Handler failed: Sub'),
                ('Stop without words',_throw(Stop()),'Handler failed: Stop'),
                ('Stop with words that are not text',_throw(Stop(7)),'Handler failed: Stop'),
                ('Stop with two texts',_throw(Stop('no room','on the shelf')),'Handler failed: Stop'),
                ('Stop with text of a class of its own',_throw(Stop(Text('no room'))),'Handler failed: Stop'),
                ('Stop with the empty text',_throw(Stop('')),'Handler refused: '),   # review round three: the empty text is the handler's own words too
                ('an error that answers Stop when it is asked for its class',_throw(Sly('I am the kernel')),'Handler failed: Sly'),   # review round three: the class is read from the error itself and never asked of it, so this is no refusal and is named by its own class
                ('a class that raises when it is asked for its name',_throw(Liar('Hidden',(Exception,),{})('x')),'Handler failed: Hidden'),
                ('a class that gives a name UTF-8 cannot carry',_throw(Says('Named',(Exception,),{})('x')),'Handler failed: Named'),
                ('a class that gives no text for its name',_throw(Mute('Quiet',(Exception,),{})('x')),'Handler failed: Quiet'),
                ('a class whose name is text of a class of its own',_throw(Renamed('x')),'Handler failed: unreadable'),
                ('a class named in two words',_throw(type('Disk Error',(Exception,),{})('x')),'Handler failed: unreadable'),
                ('a class named in other letters',_throw(type('CaféError',(Exception,),{})('x')),'Handler failed: unreadable'),
                ('a class without a name',_throw(type('',(Exception,),{})('x')),'Handler failed: unreadable'),
                ('a handler that calls itself without end',runaway,'Handler failed: RecursionError'),
                ('984 levels deep',lambda s,m,mid,deps:deep(984),cannot),('17 levels deep',lambda s,m,mid,deps:deep(17),cannot),
                ('a tuple',lambda s,m,mid,deps:{'x':(1,2)},cannot),('parked is no plain value',lambda s,m,mid,deps:{'parked':Odd(1)},cannot),
                ('a mapping that lies about its keys',lambda s,m,mid,deps:Lies(),cannot),('a dict whose keys() raises',lambda s,m,mid,deps:Late(),cannot)]
        worlds+=[(f'sets {field}',(lambda field:lambda s,m,mid,deps:{field:'x'})(field),cannot) for field in ('method','scope','action','status','sha256')]
        for i,(name,fn,reason) in enumerate(worlds):
            self._kinds(**{f'test_w{i}':fn})
            w=self._world(['G1','G2'],[],[self._m('a','A'),self._m('bad','G1',f'test_w{i}',req=['A']),self._m('m2','G2')])
            runs=Kernel(w).run_standing(execute=True)['runs'];r=runs[0];rows=[e['data'] for e in r['trace'] if e['operation']=='STEP_STOPPED']
            self.assertEqual(([x['status'] for x in runs],r['actions'],r['stopped'],rows,r['pending'],r['model_receipts']==[e['data']['receipt'] for e in r['trace'] if e['operation']=='LOCAL_EFFECT'],[j['status'] for j in w.event_journal]),
                             (['STEP_STOPPED','LOCAL_MODEL_EFFECTS_RECORDED'],['a'],{'method':'bad','reason':reason},[{'method':'bad','reason':reason,'effect_reads':'UNKNOWN'}],['bad'],True,['STEP_STOPPED','LOCAL_MODEL_EFFECTS_RECORDED']),name)
            self.assertEqual(self._spent(w),({'compute':8,'money':10,'attention':3},{'prov':8}),name)   # paid: step a and the other goal's step; the stopped step took nothing, from the budget or from the slots
        self.assertEqual(asked,[])   # the kernel named every one of these errors without running any code of its class, and took no text that is not exact text
        roots=lambda kind:[Kernel(self._world(['G'],[],[self._m('bad','G',kind)])).run_standing(execute=True)['runs'][0]['trace_root_sha256'] for _ in (1,2)]
        said=[0]
        def counts(s,m,mid,deps):said[0]+=1;raise Stop(f'refusal number {said[0]}')
        self._kinds(test_counts=counts,test_deep16=lambda s,m,mid,deps:deep(16),test_pops=pops,test_drops=drops)
        self.assertEqual((len(set(roots('test_w0'))),len(set(roots('test_counts')))),(1,2))   # the same words give the same record on two States; a handler that words its refusal anew each time gets a new root each time
        r=Kernel(self._world(['G'],[],[self._m('ok','G','test_deep16')])).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'],len(r['model_receipts'])),('LOCAL_MODEL_EFFECTS_RECORDED',1))   # 16 levels is plain data: a receipt
        kept=[]
        def keeps(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));kept.append(mid);return {'seen':kept}   # hands out a list it keeps, and adds to it at its next call
        self._kinds(test_keeps=keeps);w=self._world(['G'],[],[self._m('one','A','test_keeps'),self._m('two','G','test_keeps',req=['A'])]);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual(([x['seen'] for x in r['model_receipts']],[x['sha256']==digest({key:y for key,y in x.items() if key!='sha256'}) for x in r['model_receipts']],kept),   # review round three: a receipt carries the kernel's own copy of what was returned: a list the handler changes after its return leaves the receipt, and its sha, as they were
                         ([['one'],['one','two']],[True,True],['one','two']))
        w=self._world(['e'],[],[self._m('a','e','test_pops',cost={'compute':2,'money':1,'attention':0})]);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['stopped'],r['cost'],w.budget,r['model_receipts'],[e['data']['effect_reads'] for e in r['trace'] if e['operation']=='STEP_STOPPED']),   # the slot could not be taken, so nothing was: paid in full or not at all. A fault of the kernel's own line is named by its class
                         ({'method':'a','reason':'Kernel fault: KeyError'},self.ZERO,{'compute':10,'money':10,'attention':3},[],['TRUE']))
        self.assertNotIn('LOCAL_EFFECT',self._ops(r))   # review round three: and no receipt's line is in the record: the amounts are read before the line is written, so this step leaves a stop line and no receipt's line
        class Full(Kernel):   # a kernel whose record has no room for a receipt's line
            def log(self,op,**data):
                if op=='LOCAL_EFFECT':raise MemoryError('no room for the line')
                super().log(op,**data)
        w=self._world(['e'],[],[self._m('m','e')]);r=Full(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['stopped'],r['model_receipts'],self._spent(w),w.fact('e')['truth']),   # no line, no payment: a step is paid after its receipt is in the record (the effect the handler wrote stands)
                         ({'method':'m','reason':'Kernel fault: MemoryError'},[],({'compute':10,'money':10,'attention':3},{'prov':10}),'TRUE'))
        for error,name in ((Liar('Hidden',(Exception,),{})('x'),'Hidden'),(Mute('Quiet',(Exception,),{})('x'),'Quiet')):   # review round three: a fault of the kernel's own line is named as a handler's failure is, from the type itself: a class that raises, or gives no text, when it is asked for its name is named all the same, and none of its code runs
            class Fails(Kernel):   # a kernel whose record fails with that error when a receipt's line is written
                def log(self,op,**data):
                    if op=='LOCAL_EFFECT':raise error
                    super().log(op,**data)
            w=self._world(['e'],[],[self._m('m','e')]);r=Fails(w).run_standing(execute=True)['runs'][0]
            self.assertEqual((r['stopped'],asked),({'method':'m','reason':'Kernel fault: '+name},[]),name)
        w=self._world(['e'],[('e',[['x','y']])],[self._m('first','x','test_drops'),self._m('later','y')]);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'],r['actions'],r['stopped'],r['pending'],[e['data']['effect_reads'] for e in r['trace'] if e['operation']=='STEP_STOPPED'],len(w.event_journal)),   # a later step's method is gone: a recorded stop all the same, its effect unreadable
                         ('STEP_STOPPED',['first'],{'method':'later','reason':'Kernel fault: KeyError'},['later'],['UNKNOWN'],1))
        def unplugs(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));s.actions.pop('simulate_fact');return {}
        self._kinds(test_unplugs=unplugs)
        w=self._world(['done'],[],[self._m('first','a','test_unplugs'),self._m('second','done',req=['a'])]);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['actions'],r['stopped']),(['first'],{'method':'second','reason':'Kernel fault: KeyError'}))   # the kind of a later step is gone: no handler ran, so the stop is not worded as a handler's failure
        def blanks(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));s.methods['later']=None;return {}
        self._kinds(test_blanks=blanks)
        w=self._world(['e'],[('e',[['x','y']])],[self._m('first','x','test_blanks'),self._m('later','y')]);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['actions'],r['stopped'],[e['data']['effect_reads'] for e in r['trace'] if e['operation']=='STEP_STOPPED'],len(w.event_journal)),   # a later step's method is no method any more: its effect cannot be read, for another reason than a missing key, and the line is written all the same
                         (['first'],{'method':'later','reason':'Kernel fault: TypeError'},['UNKNOWN'],1))
        import socket
        self._kinds(test_late_answer=_throw(socket.timeout('late')))
        r=Kernel(self._world(['G'],[],[self._m('bad','G','test_late_answer')])).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['stopped']['reason'],socket.timeout.__name__ in ('timeout','TimeoutError')),('Handler failed: '+socket.timeout.__name__,True))   # the name is the one the running Python holds: `timeout` before 3.10, `TimeoutError` from 3.10 on, so two records of this failure compare only on one Python version
        def adds_a_kind(s,result,log):s.actions.setdefault('test_late',{'run':lambda s,m,mid,deps:{}})
        def hides(s,result,log):raise Renamed('x')
        def mutters(s,result,log):raise Mute('Quiet',(Exception,),{})('x')
        def halts(s,result,log):raise Stop('books')
        self._kinds(test_registry=(lambda s,m,mid,deps:{},{'settle':adds_a_kind}),test_hides=(lambda s,m,mid,deps:{},{'settle':hides}),test_mutters=(lambda s,m,mid,deps:{},{'settle':mutters}),test_halts=(lambda s,m,mid,deps:{},{'settle':halts}))
        w=self._world(['G'],[],[self._m('m','G')]);r=Kernel(w).run_standing(execute=True)['runs'][0]   # a settle hook that changes the registry does not end the settling; kinds whose settle fails are one line and one name under unsettled each, in the registry's order, each error named as a step's failure is (a Stop too: from a hook it is the hook's own error)
        self.assertEqual((r['status'],'test_late' in w.actions,[e['data'] for e in r['trace'] if e['operation']=='SETTLE_STOPPED'],r['unsettled'],len(w.event_journal),asked),
                         ('LOCAL_MODEL_EFFECTS_RECORDED',True,[{'kind':'test_hides','reason':'unreadable'},{'kind':'test_mutters','reason':'Quiet'},{'kind':'test_halts','reason':'Stop'}],['test_hides','test_mutters','test_halts'],1,[]))
    def test_a_stop_ends_the_run_there_and_every_part_of_it_is_on_the_record(self):
        # Review round one on 0.9.0: 30 of 87 mutants of the changed kernel lines passed every test. One assertion per survivor that changed behaviour.
        def meddles(s,m,mid,deps):s.grants.discard('g');s.budget['compute']=0;s.observe(self._row(m['effect'],'TRUE','1'));return {}
        def bad_settle(s,result,log):raise KeyError('books')
        self._kinds(test_fail=_throw(OSError('disk')),test_returns_none=lambda s,m,mid,deps:None,test_meddles=meddles)
        w=self._world(['G'],[('G',[['x','y','z']])],[self._m('first','x'),self._m('mid','y','test_fail'),self._m('last','z')]);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['actions'],r['pending'],w.fact('z')['truth'],self._spent(w)),(['first'],['mid','last'],'UNKNOWN',({'compute':9,'money':10,'attention':3},{'prov':9})))   # nothing after the stopped step runs; the rest of the plan is pending
        w=self._world(['e'],[],[self._m('m','e','test_returns_none')]);Kernel(w).run_standing(execute=True)
        self.assertEqual(self._spent(w),({'compute':10,'money':10,'attention':3},{'prov':10}))   # a refused return costs no slot either
        w=self._world(['done'],[],[self._m('first','a','test_meddles',cost=self.ZERO),self._m('second','done',req=['a'])]);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['actions'],r['stopped']),(['first'],{'method':'second','reason':'Gate changed before effect: AUTHORITY_REQUIRED RESOURCE_REQUIRED'}))   # every gate word, in the gate's own order
        w=self._world(['done'],[],[self._m('m','done',req=['p','q'])]);k=Kernel(w);self.assertEqual(k._act({'actions':['m']}),[])
        self.assertEqual(k.events[-1]['data'],{'method':'m','reason':'Prerequisite not true before effect: p q','effect_reads':'UNKNOWN'})   # every missing fact is named
        w=self._world(['done'],[],[self._m('m','done',req=['q','p','q'])]);k=Kernel(w);k._act({'actions':['m']})
        self.assertEqual(k.events[-1]['data']['reason'],'Prerequisite not true before effect: q p q')   # review round three: in the step's own order, a fact the step names twice said twice (neither sorted nor said once)
        w=self._world(['done'],[],[self._m('m','done',req=['q','p','q'])],[('p','TRUE'),('q','TRUE')]);Kernel(w).run_standing(execute=True)
        self.assertEqual(w.evidence[w.key('done')]['depends_on'],[{'predicate':x,'version':'1'} for x in ('q','p','q')])   # review round three: and the row a step writes rests on the step's prerequisites in the same order
        w=self._world(['e'],[],[]);w.methods['free']={'id':'free','effect':'e','requires':[],'grant':'g','cost':{'compute':1},'action':'simulate_fact'}   # put into the State by hand without a provider (no pack can)
        r=Kernel(w).run_standing(execute=True)['runs'][0];self.assertEqual((r['actions'],self._spent(w)),(['free'],({'compute':9,'money':10,'attention':3},{'prov':10})))   # it takes no slot, as in 0.8.0
        s=State(actions={'test_first':{'run':lambda s,m,mid,deps:{},'settle':bad_settle},**{name:dict(kind) for name,kind in ACTIONS.items()}})
        for n in ASK:s.apply(pack(n))
        r=Kernel(s).run_standing(execute=True)['runs'][0]   # the kind whose settle fails comes first in the registry: the ask kind after it still keeps its books
        self.assertEqual((r['status'],r['unsettled'],self._open(s),[op for op in self._ops(r) if op in ('SETTLE_STOPPED','TERMINAL')]),('WAITING',['test_first'],['ask-customer-approval@1'],['SETTLE_STOPPED','TERMINAL']))
    def test_what_the_guard_does_not_cover_is_stated_and_pinned(self):
        # The known limits of 0.9.0, each as the README states it.
        for exc in (SystemExit(3),KeyboardInterrupt(),GeneratorExit()):   # an error that is not an Exception is not a step's failure: it passes through, and the look it interrupts leaves no journal row
            kind='test_'+type(exc).__name__;self._kinds(**{kind:_throw(exc)})
            w=self._world(['G1','G2'],[],[self._m('a','A'),self._m('bad','G1',kind,req=['A']),self._m('m2','G2')])
            with self.assertRaises(type(exc)):Kernel(w).run_standing(execute=True)
            self.assertEqual((w.event_journal,self._spent(w)),([],({'compute':9,'money':10,'attention':3},{'prov':9})))   # step a stays done and paid; no row, no second goal
        def quits(s,result,log):raise SystemExit(3)
        self._kinds(test_quits=(lambda s,m,mid,deps:{},{'settle':quits}));w=self._world(['G'],[],[self._m('m','G')])
        with self.assertRaises(SystemExit):Kernel(w).run_standing(execute=True)   # the same from a settle hook: the run's step is done and paid, its result is lost
        self.assertEqual((w.event_journal,w.budget['compute']),([],9));ACTIONS.pop('test_quits')
        def gone(s,m,mid,deps):s.methods.pop(mid);return {}
        self._kinds(test_gone=gone);w=self._world(['e'],[],[self._m('m','e','test_gone')])
        with self.assertRaises(KeyError):Kernel(w).run_standing(execute=True)   # the guard is around the step, not around the State: this handler removed its own method, and the run's tail cannot price what ran
        self.assertEqual(w.event_journal,[])
        def hoards(s,m,mid,deps):
            v=[]
            for _ in range(sys.getrecursionlimit()):v=[v]
            s.candidates['deep']={'id':'deep','status':'PROPOSED_ONLY','nested':v};raise Stop('no')
        self._kinds(test_hoards=hoards);w=self._world(['e'],[],[self._m('m','e','test_hoards')])
        for execute in (True,False):   # a candidate nested deeper than Python can copy: the stop is recorded in the run, but the kernel cannot hand the candidates out, in this look or in any later one, dry looks too
            with self.assertRaises(RecursionError):Kernel(w).run_standing(execute=execute)
        self.assertEqual(w.event_journal,[])
        self._kinds(test_two_goal_plan=(lambda s,m,mid,deps:{},{'plan':lambda s,m:1/0}))
        w=self._world(['G1','G2'],[],[self._m('m1','G1'),self._m('m2','G2','test_two_goal_plan')])
        with self.assertRaises(ZeroDivisionError):Kernel(w).run_standing(execute=True)   # a plan hook that raises ends the look before any step of its own goal runs
        self.assertEqual(([j['status'] for j in w.event_journal],w.budget['compute']),(['LOCAL_MODEL_EFFECTS_RECORDED'],9))   # the goal before it has run and been paid; its result is lost with the error
        armed=[]
        def trips(s,m):
            if armed:raise Stop('not now')
        def refuses(m):raise Stop('not this method')
        def divides(m):1/0
        self._kinds(test_trips=(lambda s,m,mid,deps:{},{'plan':trips}),test_refuses=(lambda s,m,mid,deps:{},{'check':refuses}),test_divides=(lambda s,m,mid,deps:{},{'check':divides}))
        w=self._world(['G'],[],[self._m('g','G','test_trips',req=['ok'])]);k=Kernel(w);armed.append(1)
        with self.assertRaises(Stop):k.run_standing(execute=True)   # a hook's own error is not the stop of a step: a Stop that a plan hook raises reaches the caller like any other error
        with self.assertRaises(Stop):k.on_event(self._row('ok','TRUE','1'),execute=True)   # through an event the row is stored before the looks run: it stands although the call raised and returned nothing
        self.assertEqual((w.fact('ok')['truth'],w.event_journal),('TRUE',[]))
        armed.clear();a=self._world(['G'],[],[self._m('q','ok','ask',self.ASKS,ask_to='al'),self._m('g','G','test_trips',req=['ok'])]);ka=Kernel(a);out=ka.run_standing(execute=True)['runs'][0];armed.append(1)
        with self.assertRaises(Stop):answer(ka,out['model_receipts'][0],'TRUE','al',execute=True)   # the same through the stamp: the decision is on the fact, the call raised, and the journal has no row for the look the answer caused
        self.assertEqual((a.fact('ok')['truth'],a.fact('ok').get('final'),[j['status'] for j in a.event_journal],open_asks(a)),('TRUE',True,['WAITING'],{}))
        with self.assertRaises(ValueError):answer(ka,out['model_receipts'][0],'TRUE','al',execute=True)   # the question is closed by that decision: its receipt answers nothing more
        armed.clear();s=State()
        for kind,error in (('test_refuses',Stop),('test_divides',ZeroDivisionError)):   # a check hook that raises an error the kernel does not turn into a refusal leaves apply with that error, not with a ValueError; the pack is not applied
            with self.assertRaises(error):s.apply({'schema':'sutra-extension/2','id':'x','goals':['e'],'grants':['g'],'providers':{'prov':2},'methods':[self._m('m','e',kind)]})
        self.assertEqual((s.methods,s.goals,s.loaded),({},[],[]))
        self.assertEqual(Stop.__mro__,(Stop,Exception,BaseException,object))   # review round three: so "instead of a ValueError" holds for a Stop: it is an error of its own kind, neither a ValueError (a refusal of the door) nor a RuntimeError (Python raises those itself)
        self._kinds(test_no_evidence=lambda s,m,mid,deps:{})   # a step that rests on a fact made by a kind that writes no evidence: offered, then recorded as stopped
        w=self._world(['done'],[],[self._m('make','made','test_no_evidence',cost={'compute':3,'money':0,'attention':0}),self._m('use','done',req=['made'])]);k=Kernel(w)
        looks=[k.run_standing()['runs'][0]]+[k.run_standing(execute=True)['runs'][0] for _ in range(4)]
        self.assertEqual([(x['status'],x['actions'],(x.get('stopped') or {}).get('reason')) for x in looks]+[w.budget['compute']],   # the step before the stop leaves no evidence: every executed look runs and pays it again, until the budget is gone
                         [('PLAN_READY',['make','use'],None)]+[('STEP_STOPPED',['make'],'Prerequisite not true before effect: made')]*3+[('RESOURCE_REQUIRED',[],None),1])
        def wrote_then_failed(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','local-sim-1'));raise OSError('disk')
        self._kinds(test_wrote=wrote_then_failed)
        w=self._world(['done'],[],[self._m('first','a','test_wrote',cost={'compute':5,'money':0,'attention':0}),self._m('second','done',req=['a'])]);k=Kernel(w)
        one,two=[k.run_standing(execute=True)['runs'][0] for _ in (1,2)]
        self.assertEqual(((one['status'],one['actions'],[e['data']['effect_reads'] for e in one['trace'] if e['operation']=='STEP_STOPPED']),(two['status'],two['actions']),w.budget['compute']),   # the effect the failed step wrote stands: the next look completes on it, and the 5-compute step is never paid
                         (('STEP_STOPPED',[],['TRUE']),('LOCAL_MODEL_EFFECTS_RECORDED',['second']),9))
        def fails(s,result,log):raise OSError('books')
        s=State.from_packs([pack(n) for n in ASK]);k=Kernel(s);keep=s.actions['ask']['settle'];s.actions['ask']['settle']=fails
        asked=k.run_standing(execute=True)['runs'][0];s.actions['ask']['settle']=keep   # the ask kind's own settle fails once: the run looks like any wait, but the books do not know the question
        self.assertEqual((asked['status'],asked['unsettled'],open_asks(s),s.budget['attention']),('WAITING',['ask'],{},2))
        with self.assertRaises(ValueError):answer(k,asked['model_receipts'][0],'TRUE','customer',execute=True)   # so the asked party's answer is refused
        again=k.run_standing(execute=True)['runs'][0];self.assertEqual((again['actions'],s.budget['attention']),(['ask-customer-approval@1'],1))   # and the next executed look asks and pays again
        def deep(s,m,mid,deps):   # writes its effect, then returns 16 levels of data: the kernel's own work on that return is the deepest part of the look
            s.observe(self._row(m['effect'],'TRUE','1'));v=[]
            for _ in range(15):v=[v]
            return {'x':v}
        def digs(s,m,mid,deps):   # needs 20 calls of stack before it writes its effect
            def down(n):return n and down(n-1)
            down(20);s.observe(self._row(m['effect'],'TRUE','1'));return {}
        self._kinds(test_deep=deep,test_digs=digs)
        def dive(n,call):return call() if n==0 else dive(n-1,call)
        here,frame=0,sys._getframe()
        while frame:here,frame=here+1,frame.f_back
        top=sys.getrecursionlimit()-here;seen=set();lowest=None
        for n in range(top-150,top):   # Python's own limit is not guarded. A look called at every one of the last 150 call depths before the stack is used up:
            w=self._world(['G','H'],[],[self._m('g','G','test_deep',cost={'compute':5,'money':0,'attention':0}),self._m('h','H')]);start=self._spent(w)
            try:runs=dive(n,lambda:Kernel(w).run_standing(execute=True)['runs'])
            except RecursionError:seen.add('ends with RecursionError');continue
            stops=[r['stopped']['reason'] for r in runs if r['status']=='STEP_STOPPED'];paid={d:sum(w.methods[x['method']]['cost'][d] for r in runs for x in r['model_receipts']) for d in start[0]}
            self.assertTrue(set(stops)<={'Kernel fault: RecursionError','Handler failed: RecursionError'} and len(runs)==2,(n,stops))
            self.assertEqual(({d:start[0][d]-w.budget[d] for d in paid},start[1]['prov']-w.providers['prov']),(paid,sum(len(r['model_receipts']) for r in runs)),n)   # in the band too, what is paid is what has a receipt
            seen.add('completes' if not stops else 'a recorded stop, its effect standing unpaid' if runs[0]['status']=='STEP_STOPPED' and w.fact('G')['truth']=='TRUE' else 'a recorded stop');seen.update(stops)
            if runs[0]['status']=='STEP_STOPPED':lowest=n
        self.assertTrue({'completes','ends with RecursionError','a recorded stop, its effect standing unpaid','Kernel fault: RecursionError'}<=seen,seen)   # it ends with the error, or (the stack ran out inside a step) returns with that step recorded as stopped, and an effect its handler had written stands unpaid
        w=self._world(['G','H'],[],[self._m('g','G','test_deep'),self._m('h','H','test_digs')]);first,later=dive(lowest,lambda:Kernel(w).run_standing(execute=True)['runs'])   # the deepest of those depths, and a second goal whose step needs more stack than is left
        self.assertEqual((first['status'],later['status'] in ('LOCAL_MODEL_EFFECTS_RECORDED','STEP_STOPPED')),('STEP_STOPPED',True))   # what the rest of such a look does is Python's own:
        if sys.version_info<(3,10):self.assertEqual(later['status'],'LOCAL_MODEL_EFFECTS_RECORDED')   # Python 3.9 lets the look go on past its limit once the error was caught (and ends the process about fifty calls past it: no test provokes that)
        if sys.version_info>=(3,11):self.assertEqual((later['status'],later['stopped']['reason'][-14:]),('STEP_STOPPED','RecursionError'))   # from 3.11 the later step is recorded as stopped in its turn
    def test_what_review_round_three_left_is_stated_and_pinned(self):
        # Review round three on 0.9.0 (two refuters, eight findings) did not refute the build, and its findings were settled without new code (ruling R19: a fix that needs new
        # code goes to the next version and its own review). The four limits it showed in the kernel are pinned here as the build behaves today, each as the README states it;
        # those of the verifier are pinned in the two verifier tests; NEXT-GATES.md lists the fixes the next version owes.
        import types
        spec=importlib.util.spec_from_file_location('independent_verify',ROOT/'qa'/'independent_verify.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
        def bad_settle(s,result,log):raise KeyError('books')
        two={'schema':'sutra-extension/2','id':'t','goals':['G1','G2'],'methods':[self._m('m1','G1'),self._m('m2','G2')],'providers':{'prov':10},'grants':['g']}   # two goals, one step each
        def named(name):   # a State whose registry holds a kind registered under that name, with a settle hook that fails
            register(name,settle=bad_settle)(lambda s,m,mid,deps:{});self.addCleanup(ACTIONS.pop,name,None)
            w=State.from_packs([two]);ACTIONS.pop(name);return w
        # 1. The name of a kind is taken as it is registered: register() checks a kind's hooks and not its name. With a name the record cannot carry (text that UTF-8 cannot carry;
        #    bytes or a frozenset, which JSON cannot write) the SETTLE_STOPPED line of a settle hook that fails cannot be written, and the look ends with Python's error.
        for name,error in (('caf\udce9',UnicodeEncodeError),(b'k',TypeError),(frozenset('k'),TypeError)):
            w=named(name)
            with self.assertRaises(error):Kernel(w).run_standing(execute=True)
            self.assertEqual((w.event_journal,self._spent(w),w.fact('G1')['truth'],w.fact('G2')['truth']),([],({'compute':9,'money':10,'attention':3},{'prov':9}),'TRUE','UNKNOWN'),repr(name))   # the first goal's step is done and paid, the journal has no row, the second goal never ran
        for name in (7,None,1.5,('a','b')):   # a name that is a number, null or a tuple: the look returns, the line and `unsettled` carry that value, and the verifier refuses the honest run (it wants a kind named by text)
            w=named(name);runs=Kernel(w).run_standing(execute=True)['runs']
            self.assertEqual(([r['status'] for r in runs],[r['unsettled'] for r in runs],[e['data'] for e in runs[0]['trace'] if e['operation']=='SETTLE_STOPPED'],len(w.event_journal),[v.stop_ok(r,w.methods) for r in runs]),
                             (['LOCAL_MODEL_EFFECTS_RECORDED']*2,[[name]]*2,[{'kind':name,'reason':'KeyError'}],2,[False,False]),repr(name))
        s=State(actions={**{kind:dict(hooks) for kind,hooks in ACTIONS.items()},'caf\udce9':{'run':lambda s,m,mid,deps:{},'settle':bad_settle}});s.apply(two)   # a registry handed to State(actions=...) is not checked at all
        with self.assertRaises(UnicodeEncodeError):Kernel(s).run_standing(execute=True)
        self.assertEqual((s.event_journal,s.budget['compute']),([],9))
        def makes(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));return {}
        for name in (7,None):   # and a pack's method can name a kind that is registered under a number or under null: the receipt then carries that value where a kind's name is meant
            register(name)(makes);self.addCleanup(ACTIONS.pop,name,None)
            w=State.from_packs([{'schema':'sutra-extension/2','id':'t','goals':['G'],'methods':[dict(self._m('m','G'),action=name)],'providers':{'prov':10},'grants':['g']}]);ACTIONS.pop(name)
            r=Kernel(w).run_standing(execute=True)['runs'][0];self.assertEqual((r['status'],[x['action'] for x in r['model_receipts']]),('LOCAL_MODEL_EFFECTS_RECORDED',[name]),repr(name))
        # 2. A plan whose step must stop is chosen again at every look, also where a dearer plan that would complete stands beside it: a stop does not feed the next plan.
        cheap,dear=self._m('cheap','G',req=['h']),self._m('dear','G',cost={'compute':5,'money':0,'attention':0},req=['c'])   # `cheap` rests on a rule's head, for which no step stores a row; `dear` rests on the stored row itself
        w=self._world(['G'],[('h',[['c']])],[cheap,dear],[('c','TRUE')]);k=Kernel(w);looks=[k.run_standing()['runs'][0]]+[k.run_standing(execute=True)['runs'][0] for _ in range(3)]
        self.assertEqual([(x['status'],x['actions'],x.get('pending'),x['pareto_options'],(x.get('stopped') or {}).get('reason')) for x in looks]+[w.fact('G')['truth'],self._spent(w),len(w.event_journal)],
                         [('PLAN_READY',['cheap'],None,1,None)]+[('STEP_STOPPED',[],['cheap'],1,'Prerequisite not true before effect: h')]*3+['UNKNOWN',({'compute':10,'money':10,'attention':3},{'prov':10}),4])
        self.assertEqual([(sorted(key for key,val in x.items() if 'dear' in json.dumps(val)),[(e['operation'],e['data'].get('accepted')) for e in x['trace'] if 'dear' in json.dumps(e['data'])]) for x in looks],
                         [(['trace'],[('METHOD_MATCH',None),('ADMISSION',True)])]*4)   # `dear` is dominated on cost: the result offers it nowhere, and only the trace shows that it was matched and admitted
        alone=self._world(['G'],[('h',[['c']])],[dear],[('c','TRUE')]);r=Kernel(alone).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'],r['actions'],alone.fact('G')['truth']),('LOCAL_MODEL_EFFECTS_RECORDED',['dear'],'TRUE'))   # the route that exists: without `cheap` beside it, `dear` completes the goal
        # 3. A chain of stored rows, each resting on the one before, that is long enough to use up the stack. A look that reads it while planning ends with RecursionError, a dry
        #    look too, as on 0.8.0. Where a step reads the chain deeper than planning did, the look returns with that step recorded as stopped, at any depth of the caller.
        def chain(n):   # two goals; the step of the first rests on the last of n+1 stored rows
            w=self._world(['G','H'],[],[self._m('g','G',req=[f'f{n}']),self._m('h','H')],[('f0','TRUE')])
            for i in range(1,n+1):w.observe(self._row(f'f{i}','TRUE','1',depends_on=[{'predicate':f'f{i-1}','version':'1'}]))
            return w
        def look(k,execute):   # what a look ends with: Python's error, or each run's status and the reason of its stop
            try:return [(r['status'],(r.get('stopped') or {}).get('reason')) for r in k.run_standing(execute=execute)['runs']]
            except RecursionError:return 'RecursionError'
        def three(n):   # a dry look and two executed looks at a chain of that length, then the journal's length and the books
            w=chain(n);k=Kernel(w);return [look(k,False),look(k,True),look(k,True)],len(w.event_journal),self._spent(w)
        def planned(n):return look(Kernel(chain(n)),False)   # one dry look at a chain of that length, called as deep as `three` calls its looks
        here,frame=0,sys._getframe()
        while frame:here,frame=here+1,frame.f_back
        low,high=sys.getrecursionlimit()-here-40,sys.getrecursionlimit()-here;ready=[('PLAN_READY',None)]*2   # a chain that planning can read from this depth, and one that it cannot
        self.assertEqual((planned(low),planned(high)),(ready,'RecursionError'))
        while high-low>1:   # the shortest chain that a dry look can no longer read
            n=(low+high)//2;low,high=(low,n) if planned(n)=='RecursionError' else (n,high)
        stop=('STEP_STOPPED','Kernel fault: RecursionError')
        done=([ready,[('LOCAL_MODEL_EFFECTS_RECORDED',None)]*2,[('SUPPORTED_BY_EVIDENCE',None)]*2],6,({'compute':8,'money':10,'attention':3},{'prov':8}))
        halted=([ready,[stop,('LOCAL_MODEL_EFFECTS_RECORDED',None)],[stop,('SUPPORTED_BY_EVIDENCE',None)]],6,({'compute':9,'money':10,'attention':3},{'prov':9}))   # the step is recorded as stopped, unpaid, at every executed look, and the next goal runs
        self.assertEqual((three(high-2),three(high)),(done,(['RecursionError']*3,0,({'compute':10,'money':10,'attention':3},{'prov':10}))))   # two rows shorter the plan completes; from that length on every look ends with the error and leaves no journal row
        edge=three(high-1);self.assertIn(edge,(halted,done))   # the longest chain that planning can read:
        if sys.version_info<(3,12):self.assertEqual(edge,halted)   # on Python 3.9 and 3.11 a step reads the chain one call deeper than planning did, so at exactly this length the step is a recorded stop (0.8.0 ended the look with the error)
        if sys.version_info[:2]==(3,12):self.assertEqual(edge,done)   # on Python 3.12 a step reads no deeper than planning, and no length gives the recorded stop
        # 4. The guard holds against what a handler raises and returns, not against what it does to the State. One that replaces the provider slots by a mapping that cannot be
        #    written leaves a look that returns with its step recorded as stopped although the receipt's line is in the chain and the budget was paid.
        def swaps(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));s.providers=types.MappingProxyType(dict(s.providers));return {}
        self._kinds(test_swaps=swaps);w=self._world(['G'],[],[self._m('g','G','test_swaps',cost={'compute':2,'money':0,'attention':0})]);k=Kernel(w);r=k.run_standing(execute=True)['runs'][0]
        self.assertEqual((self._ops(r)[-4:],[e['data']['receipt']['method'] for e in r['trace'] if e['operation']=='LOCAL_EFFECT'],r['model_receipts'],r['stopped'],r['actions'],r['cost'],w.budget,dict(w.providers),w.fact('G')['truth'],len(w.event_journal),v.stop_ok(r,w.methods)),
                         (['ADMISSION','LOCAL_EFFECT','STEP_STOPPED','TERMINAL'],['g'],[],{'method':'g','reason':'Kernel fault: AttributeError'},[],self.ZERO,{'compute':8,'money':10,'attention':3},{'prov':10},'TRUE',1,True))   # a receipt's line and a stop line for one step; no receipt in the result; 2 compute paid, the slot not taken; the verifier's check of a stop accepts the row
        again=k.run_standing(execute=True)['runs'][0];self.assertEqual((again['status'],again['actions'],w.budget['compute']),('SUPPORTED_BY_EVIDENCE',[],8))   # the effect stands, and what was paid stays paid
    def test_a_stopped_run_is_worded_as_a_stop_outside_the_kernel(self):
        # Review round one on 0.9.0: the viewer worded every run with pending steps as a wait on a person, and the generator's page showed neither the stopped step nor the reason.
        s=State.from_packs([pack(n) for n in ('30_build_goal','31_build_theory','82_components_without_constructor')]);r=Kernel(s).run_standing(execute=True)['runs'][0];ui=to_implementation(r,s)['ui']
        self.assertIn('stopped at <code>construct-enquiry-candidate@1</code>: Handler refused: No declared constructor. Steps that ran there: validate-field@1, store-component@1, read-component@1.',ui)
        done=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]);ok=Kernel(done).run_standing(execute=True)['runs'][0]
        self.assertNotIn('stopped at',to_implementation(ok,done)['ui'])   # a run that did not stop is worded as before
        viewer=(ROOT/'tools'/'build_viewer.py').read_text()   # the viewer's script words pending steps by the run's state: a stop is not a wait on a person
        self.assertIn("`<span class=\"muted\">${r?.stopped?'Nothing ran':'No admitted action'}</span>`",viewer)   # review round two: a stop at the first step is worded as nothing ran, not as no admitted action
        self.assertIn("r?.stopped?`<div class=\"hint\">Stopped at ${escaped(r.stopped.method)}: ${escaped(r.stopped.reason)}.${r.pending?.length>1?` Not reached: ${r.pending.slice(1).map(escaped).join(', ')}`:''}</div>`",viewer)   # the stopped step is named as the step that stopped and is no longer listed among steps that were not run; what comes after it was not reached
        self.assertNotIn('. Not run`',viewer)
    def test_the_verifier_holds_a_stop_to_its_shape_and_a_case_to_its_books(self):
        # Review round one on 0.9.0: forged stops passed the independent verifier (a paid stopped step, a journal row saying completed, a reason outside the list, a stop row in
        # front of its own gate row). Its stop checks are module-level functions: here they run on case 30 made in memory, on forgeries of it, and on honest stops of every kind.
        # Review round two added what follows the list of forgeries: the readings held exactly, the stored facts held to the pack files, honest cases the verifier had refused, and its own limits.
        spec=importlib.util.spec_from_file_location('independent_verify',ROOT/'qa'/'independent_verify.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
        stop=[c for c in CASES if c[0]=='30_stop'][0]   # by its id, not by its place: a later version adds cases after it
        files=[pack(n) for n in stop[3]];methods={m['id']:m for p in files for m in p.get('methods',[])};honest=json.loads(json.dumps(scenario(stop)))
        both=lambda c:(c['outcome'],c['run']['runs'][0]);rows=lambda c:[e['data'] for r in both(c) for e in r['trace'] if e['operation']=='STEP_STOPPED']
        def forged(change):
            c=json.loads(json.dumps(honest));change(c);return v.stop_ok(c['outcome'],methods),v.books_ok(c,methods,files)
        def says(**fields):return lambda c:[row.update(**fields) for row in rows(c)]
        def moved(c):
            for r in both(c):
                t=r['trace'];i=[e['operation'] for e in t].index('STEP_STOPPED');t[i-1],t[i]=t[i],t[i-1]
        def earlier(c):   # the stop moved one step earlier, and every book re-made to agree
            for r in both(c):
                t=r['trace'];i=[e['operation'] for e in t].index('STEP_STOPPED');gone=r['model_receipts'].pop()['method'];del t[i-2:i]
                t[i-2]['data'].update(method=gone,effect_reads='TRUE');r['actions'].pop();r['cost']['compute']-=1;r['pending'].insert(0,gone);r['stopped']['method']=gone
            c['derived_state']['budget_after']['compute']+=1
        self.assertEqual((honest['outcome']['status'],forged(lambda c:None)),('STEP_STOPPED',(True,True)))
        for name,change,want in (('an extra field in the stop row',says(note='x'),(False,True)),('a reason outside the list',says(reason='Because'),(False,True)),
                                 ('a fact the stopped step does not need',says(reason='Prerequisite not true before effect: no_such_fact'),(False,True)),
                                 ('a gate word its gate row does not carry',says(reason='Gate changed before effect: AUTHORITY_REQUIRED'),(False,True)),
                                 ('the stop row in front of its own gate row',moved,(False,True)),('unsettled without a row',lambda c:[r.update(unsettled=['ask']) for r in both(c)],(False,True)),
                                 ('the effect reads TRUE against the stored row',says(effect_reads='TRUE'),(True,False)),
                                 ('the goal reads TRUE against the stored row',lambda c:[r.update(goal_truth_after='TRUE') for r in both(c)],(True,False)),
                                 ('the stopped step was paid',lambda c:c['derived_state']['budget_after'].update(compute=6),(True,False)),
                                 ('nothing was paid',lambda c:c['derived_state']['budget_after'].update(compute=10),(True,False)),
                                 ('the journal says completed',lambda c:c['derived_state']['historical_events'][-1].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),(True,False)),
                                 ('a candidate nobody made',lambda c:c['derived_state'].update(candidate_count=1),(True,False)),
                                 ('the goal reads UNKNOWN against the stored row',lambda c:[r.update(goal_truth_after='UNKNOWN') for r in both(c)],(True,False)),
                                 ('the effect reads UNKNOWN against the stored row',says(effect_reads='UNKNOWN'),(True,False)),
                                 ('a row the packs left, changed',lambda c:c['derived_state']['facts']['orgA/enquiries|source_contract_reviewed'].update(truth='FALSE'),(True,False)),
                                 ('a row the packs left, gone',lambda c:c['derived_state']['facts'].pop('orgA/enquiries|source_contract_reviewed'),(True,False)),
                                 ("the row on the stopped step's effect, gone",lambda c:c['derived_state']['facts'].pop('orgA/enquiries|capability_candidate_created'),(True,False)),
                                 ('that row gone, and what the run says it reads changed to agree',lambda c:(c['derived_state']['facts'].pop('orgA/enquiries|capability_candidate_created'),says(effect_reads='UNKNOWN')(c),[r.update(goal_truth_after='UNKNOWN') for r in both(c)]),(True,False)),
                                 ('that row said to be unverified',lambda c:c['derived_state']['facts']['orgA/enquiries|capability_candidate_created'].update(verified=False),(True,False)),
                                 ('a fact nobody wrote',lambda c:c['derived_state']['facts'].update({'orgA/enquiries|another_fact':{'predicate':'another_fact','truth':'TRUE','verified':True,'scope':'orgA/enquiries'}}),(True,False)),
                                 ('a row turned away by a decision nobody made',lambda c:c['derived_state']['historical_events'].insert(0,{'status':'DECISION_STANDS','scope':'orgA/enquiries','predicate':'source_contract_reviewed'}),(True,False)),
                                 ('words after Handler failed that are no name',says(reason='Handler failed: not a class name at all'),(False,True)),
                                 ('a failed handler named in other letters',says(reason='Handler failed: CaféError'),(False,True)),
                                 ('a kernel fault in several words',says(reason='Kernel fault: the owner said so'),(False,True)),
                                 ('worded as a kernel fault, in front of its own gate row',lambda c:(says(reason='Kernel fault: KeyError')(c),moved(c)),(False,True)),
                                 ('worded as a kernel fault, after the gate row of another step',lambda c:(says(reason='Kernel fault: KeyError')(c),[r['trace'][[e['operation'] for e in r['trace']].index('STEP_STOPPED')-1]['data'].update(methods=['validate-field@1']) for r in both(c)]),(False,True)),
                                 ('its own gate row taken out',lambda c:[r['trace'].pop([e['operation'] for e in r['trace']].index('STEP_STOPPED')-1) for r in both(c)],(False,True)),
                                 ('a row of a step after the stop row',lambda c:[r['trace'].insert(-1,dict(r['trace'][10])) for r in both(c)],(False,True)),
                                 ('a settle row without a reason, before the plan is chosen',lambda c:[(r['trace'].insert(1,{'operation':'SETTLE_STOPPED','data':{'kind':'ask'}}),r.update(unsettled=['ask'])) for r in both(c)],(False,True))):
            self.assertEqual(forged(change),want,name)
        def rewritten(c):   # the stored row on the stopped step's effect replaced by one that reads UNKNOWN, and what the run says it reads changed to agree
            c['derived_state']['facts']['orgA/enquiries|capability_candidate_created'].update(truth='UNKNOWN');says(effect_reads='UNKNOWN')(c);[r.update(goal_truth_after='UNKNOWN') for r in both(c)]
        def ungated(c):   # worded as a kernel fault, its own gate row taken out: what a kernel fault before the gate looks like
            for r in both(c):
                t=r['trace'];i=[e['operation'] for e in t].index('STEP_STOPPED');del t[i-1];t[i-1]['data'].update(reason='Kernel fault: KeyError')
        self.assertEqual((forged(earlier),forged(rewritten),forged(ungated),forged(says(reason='Handler refused: any other words'))),((True,True),)*4)   # the known limits: a run re-made consistently from end to end is not caught, nor a stored row on the effect of a stopped step changed together with what the run says it reads (that row is its handler's), nor a stop re-worded as a kernel fault before its gate, nor a handler's refusal re-worded (the verifier runs neither the kernel nor a handler; the chain holds no secret)
        # Review round three: the limits are wider than the four above, and each is pinned here as the verifier behaves today (holding them needs new code: NEXT-GATES.md). A forgery
        # re-made as a forger would: the run changed in both copies, its chain hashed again, the journal's row following; then the chain, the shape of the stop and the books.
        registry=('simulate_fact','compile_candidate','emit_artifact','ask')   # the kinds the record names
        def remade(change):
            c=json.loads(json.dumps(honest))
            for r in both(c):
                change(r);prev='GENESIS'
                for n,row in enumerate(r['trace']):row.update(seq=n+1,prev_sha256=prev);row['sha256']=v.sha({key:x for key,x in row.items() if key!='sha256'});prev=row['sha256']
                r['trace_root_sha256']=prev
            c['derived_state']['historical_events'][-1].update(status=c['outcome']['status'],trace_root_sha256=c['outcome']['trace_root_sha256'])
            return v.check_chain(c['outcome']['trace']),v.stop_ok(c['outcome'],methods,registry),v.books_ok(c,methods,files)
        at=lambda r:[e['operation'] for e in r['trace']].index('STEP_STOPPED')
        def worded(reason):return lambda r:(r['trace'][at(r)]['data'].update(reason=reason),r['stopped'].update(reason=reason))
        def completed(r):   # the stop re-told as a completed run: the stop row replaced by a STEP_ALREADY_TRUE row for the stopped step, its gate row taken out, pending and stopped gone, no book touched
            i=at(r);mid=r['trace'][i]['data']['method'];r['trace'][i]={'operation':'STEP_ALREADY_TRUE','data':{'method':mid}};del r['trace'][i-1],r['pending'],r['stopped']
            r['trace'][-1]['data']={'status':'LOCAL_MODEL_EFFECTS_RECORDED','work_state':'completed'};r.update(status='LOCAL_MODEL_EFFECTS_RECORDED',work_state='completed',skipped=[mid])
        def unsettled(kind):return lambda r:(r['trace'].insert(-1,{'operation':'SETTLE_STOPPED','data':{'kind':kind,'reason':'unreadable'}}),r.update(unsettled=[kind]))
        halted=honest['outcome']['stopped']['method'];reads=lambda fact:v.reading(honest['derived_state']['facts'],honest['outcome']['scope'],fact)
        self.assertEqual((remade(lambda r:None),'component_validate' in methods[halted]['requires'],reads('component_validate'),reads(methods[halted]['effect'])),((True,True,True),True,'TRUE','FALSE'))   # honest; what the books read for a prerequisite of the stopped step and for its effect
        for name,change in (('re-worded as a kernel fault, its gate row left in',worded('Kernel fault: KeyError')),('re-worded as a failed handler',worded('Handler failed: KeyError')),
                            ('re-worded as a return that cannot be a receipt',worded('Handler returned what cannot be a receipt')),
                            ('re-worded as a prerequisite of the stopped step that the stored rows read TRUE',worded('Prerequisite not true before effect: component_validate')),
                            ("re-told as a completed run, although the stored row of the stopped step's effect reads FALSE",completed),
                            ('a settle failure invented for a kind that has no settle hook',unsettled('compile_candidate'))):
            self.assertEqual(remade(change),(True,True,True),name)   # known limits: a stop whose gate admitted the step can be given any other phrase of the list that is not a gate's; the facts a prerequisite stop names are held to the step's prerequisites, not to the books; a stop can be re-told as completed; a settle failure can be invented
        self.assertEqual(remade(worded('Gate changed before effect: AUTHORITY_REQUIRED')),(True,False,True))   # a gate's phrase is the one such a stop cannot be given: its gate row says the step was admitted
        # On case 30 itself the pinned line refuses a re-wording, but a case 30 re-told as completed gets no failed check: that line reads `stopped` before its check can refuse, and the
        # verifier ends with KeyError. The lab's record made in memory as tools/run_all.py makes it (the lenses of tools/make_extra.py as empty shapes: the checks that read them fail, none raises).
        from tools.run_all import ask_events
        lenses={'knowledge_compiler':{'unreviewed_rule':{'rules':[{'approved':False}]},'reviewed_rule':{'rules':[{'approved':True}]}},'reflection':{'candidates':[]},'j2_projection':{'atoms':[]},'graph_diff_nuance':{'added':[]},'implementation_website':{'workflow':{'steps':[],'edges':[]}}}
        record=json.loads(json.dumps({'kernel_sha256':'','baseline_v0_1_sha256':'','action_handlers':{},'cases':[scenario(x) for x in CASES],'events':extra_events(),'ask_events':ask_events(),'meta_extensions':lenses}))
        c=[c for c in record['cases'] if c['id']=='30_stop'][0];r=c['outcome'];completed(r);prev='GENESIS'   # re-made as a forger would, every copy the record keeps updated
        for n,row in enumerate(r['trace']):row.update(seq=n+1,prev_sha256=prev);row['sha256']=v.sha({key:x for key,x in row.items() if key!='sha256'});prev=row['sha256']
        r['trace_root_sha256']=r['learning_record']['source_trace']=prev;c['derived_state']['historical_events'][-1].update(status=r['status'],trace_root_sha256=prev)
        c['run']['runs'][0]=json.loads(json.dumps(r));c['four_views']['run']=json.loads(json.dumps(r['trace']))
        try:v.inspect(record);where='no error'
        except KeyError as error:
            tb=error.__traceback__
            while tb.tb_next:tb=tb.tb_next
            where=(error.args,tb.tb_frame.f_code.co_name)
        self.assertEqual(where,(('stopped',),'runs_ok'))   # the error is raised in runs_ok, by the line that pins case 30: every check before it took the forged run
        # Review round two. The verifier took UNKNOWN for whatever a stopped run said its goal or its effect reads (the list above), refused two honest cases, held a kernel fault and a
        # SETTLE_STOPPED row to no shape, and refused a prerequisite with the empty name. Cases made in memory as the lab makes its own:
        P={'schema':'sutra-extension/2','providers':{'prov':9},'grants':['g']}
        def case(packs,change=lambda c:None):   # the packs, one executed look at the standing goals, the books; then a change; then what the verifier says of the runs' stops and of the books
            s=State.from_packs(packs);run=Kernel(s).run_standing(execute=True);table={m['id']:m for p in packs for m in p.get('methods',[])}
            c=json.loads(json.dumps({'run':run,'outcome':run['runs'][0] if run['runs'] else None,'derived_state':{'facts':s.evidence,'candidate_count':len(s.candidates),'budget_after':s.budget,'historical_events':s.event_journal}}))
            change(c);return all(v.stop_ok(r,table) for r in c['run']['runs']),v.books_ok(c,table,packs)
        journal=lambda c:c['derived_state']['historical_events']
        turned=[dict(P,id='p',goals=['g'],methods=[self._m('m','g')],evidence=[self._row('x','TRUE','1',final=True),self._row('x','FALSE','2')])]
        self.assertEqual(case(turned),(True,True))   # honest: the journal holds the row the decision turned away, then the run's row
        self.assertEqual(case(turned,lambda c:c['derived_state']['facts']['orgA/fulfillment|g'].update(truth='FALSE')),(True,True))   # a known limit: the stored row on the effect of a step that ran is its handler's to write, and is held to nothing
        for name,change in (('the row turned away, taken out',lambda c:journal(c).pop(0)),('the row turned away, put after the run',lambda c:journal(c).reverse()),
                            ('a row turned away on a fact that carries no decision',lambda c:journal(c).insert(1,{'status':'DECISION_STANDS','scope':'orgA/fulfillment','predicate':'g'})),
                            ('the row turned away, with another status',lambda c:journal(c)[0].update(status='DECISION_LAPSED')),('the row turned away, with one field more',lambda c:journal(c)[0].update(note='x')),
                            ('a second row for the run',lambda c:journal(c).append(dict(journal(c)[-1])))):
            self.assertEqual(case(turned,change),(True,False),name)
        def decides(s,m,mid,deps):s.observe(self._row(m['effect'],'FALSE','d1',final=True));return {}   # a kind that decides no on its own effect
        self._kinds(test_v_decides=decides,test_v_no=_throw(Stop('no')))
        twice=[dict(P,id='p',goals=['G'],methods=[self._m('a1','A','test_v_decides',cost=self.ZERO),self._m('a2','A',cost=self.ZERO),self._m('b','B',cost=self.ZERO,req=['A']),self._m('g','G',cost=self.ZERO,req=['A','B'])])]
        s=State.from_packs(twice);r=Kernel(s).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['actions'],r['stopped'],[j['status'] for j in s.event_journal],case(twice)),   # honest: a plan with two methods for one fact; the first decides no, and the write of the second is turned away in the middle of the run
                         (['a1'],{'method':'a2','reason':'Handler refused: A decision stands on this effect'},['DECISION_STANDS','STEP_STOPPED'],(True,True)))
        for name,change in (('with another status',lambda c:journal(c)[0].update(status='DECISION_LAPSED')),('with one field more',lambda c:journal(c)[0].update(note='x')),('on a fact that carries no decision',lambda c:journal(c)[0].update(predicate='B'))):
            self.assertEqual(case(twice,change),(True,False),name)   # the row turned away during the run is held to its three fields and to the decision on its fact
        self.assertEqual(case(turned,lambda c:journal(c).insert(1,{'status':'DECISION_STANDS','scope':'orgA/fulfillment','predicate':'x'})),(True,True))   # and, a known limit, to nothing more: a row said to be turned away during a run passes when its fact carries a decision
        made=[dict(P,id='p',goals=['g','h'],methods=[self._m('m','g'),self._m('n','h','compile_candidate',constructor='C')],constructors=[{'id':'C','components':['m'],'required_effects':['g'],'target_effect':'h'}])]
        extra=lambda c:c['run']['runs'][-1]['candidates'].append({'id':'D','status':'PROPOSED_ONLY'})
        self.assertEqual((case(made),case(made,extra),case(made,lambda c:(extra(c),c['derived_state'].update(candidate_count=2)))),((True,True),(True,False),(True,False)))   # honest: the candidate is made for the second goal, and the books count what the last run lists; a candidate no receipt cites is refused, counted or not
        two=lambda goals:[dict(P,id='p',goals=goals,methods=[self._m('m','g','test_v_no'),self._m('n','h')],evidence=[self._row('g','FALSE','1')])]
        said_true=lambda c:[r.update(goal_truth_after='TRUE') for r in c['run']['runs'] if r['goal']=='g']
        self.assertEqual((case(two(['g','h'])),case(two(['g','h']),said_true),case(two(['h','g'])),case(two(['h','g']),said_true)),((True,True),(True,True),(True,True),(True,False)))   # a known limit: the books keep the facts as they stood at the end of the case, so a stopped run is held to what it says its effect and its goal read only when it is the case's last run
        tries=[]
        def second_time(s,m,mid,deps):   # refuses when it is first called and makes its effect when it is called again
            tries.append(mid)
            if len(tries)<2:raise Stop('not yet')
            s.observe(self._row(m['effect'],'TRUE','1'));return {}
        def wrote_then_failed(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));raise OSError('disk')
        self._kinds(test_v_second=second_time,test_v_wrote=wrote_then_failed)
        again=[dict(P,id='p',goals=['x','y'],methods=[self._m('e','E','test_v_second'),self._m('mx','x',req=['E']),self._m('my','y',req=['E'])])]
        s=State.from_packs(again);runs=Kernel(s).run_standing(execute=True)['runs'];tries.clear()
        self.assertEqual(([(r['status'],[e['data']['effect_reads'] for e in r['trace'] if e['operation']=='STEP_STOPPED']) for r in runs],s.fact('E')['truth'],case(again)),   # why it is so: honest, and the stop of the first run read UNKNOWN on a fact that the second run then made true
                         ([('STEP_STOPPED',['UNKNOWN']),('LOCAL_MODEL_EFFECTS_RECORDED',[])],'TRUE',(True,True)))
        self.assertEqual(case([dict(P,id='p',goals=['g'],methods=[self._m('m','g','test_v_wrote')])]),(True,True))   # honest: an effect a handler wrote before it failed stands, on the fact it was called to make, and the stop line reads it
        def takes(s,m,mid,deps):s.budget['compute']-=1;s.observe(self._row(m['effect'],'TRUE','1'));return {}
        def writes(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));s.observe(self._row('another_fact','TRUE','1'));return {}
        def hoards(s,m,mid,deps):s.candidates['c']={'id':'c','status':'PROPOSED_ONLY'};s.observe(self._row(m['effect'],'TRUE','1'));return {}
        def halts(s,m,mid,deps):s.candidates['c']={'id':'c','status':'PROPOSED_ONLY'};raise Stop('no')
        def hides(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));s.methods.pop(mid);raise OSError('disk')
        self._kinds(test_v_takes=takes,test_v_writes=writes,test_v_hoards=hoards,test_v_halts=halts,test_v_hides=hides)
        for kind,why in (('test_v_takes','takes budget'),('test_v_writes','writes a fact that is not its own effect'),('test_v_hoards','stores a candidate its receipt does not cite'),
                         ('test_v_halts','stores a candidate and then stops: the candidate stands on no receipt'),('test_v_hides','removes its own method and fails: the stop line says UNKNOWN for an effect that stands')):
            self.assertEqual(case([dict(P,id='p',goals=['g'],methods=[self._m('m','g',kind)])]),(True,False),why)   # known limits: the verifier holds a case to the handler contract, so it refuses these records although the kernel made them
        # the verifier's own copies of two kernel rules, held to the kernel: what packs leave in the books (the rows stored, the rows turned away), and what the stored rows make a fact read
        row=self._row
        packs=[dict(P,id='a',scope='orgA/x',evidence=[row('d','TRUE','1',final=True),row('d','FALSE','2'),row('u','TRUE','1',verified=False),row('e','TRUE','1',depends_on=[{'predicate':'d','version':'1'}]),
                                                      row('f','TRUE','1',depends_on=[{'predicate':'e','version':'2'}]),row('n','TRUE',1,depends_on=[{'predicate':'d','version':'1'}]),row('n2','TRUE','1',depends_on=[{'predicate':'n','version':1.0}]),
                                                      row('n3','TRUE','1',depends_on=[{'predicate':'n','version':1}]),row('c1','TRUE','1',depends_on=[{'predicate':'c2','version':'1'}]),row('c2','TRUE','1',depends_on=[{'predicate':'c1','version':'1'}]),
                                                      row('q','UNKNOWN','1'),row('r','TRUE','1',depends_on=[{'predicate':'q','version':'1'}]),row('z','FALSE','1'),row('y','TRUE','1',depends_on=[{'predicate':'z','version':'1'}]),
                                                      row('nv','TRUE',None),row('m1','TRUE','1',depends_on=[{'predicate':'nv'}]),row('m2','TRUE','1',depends_on=[{'predicate':'missing','version':'1'}]),row('m3','TRUE','1',depends_on=[{'predicate':'e','version':'1'}])]),
               dict(P,id='b',scope='orgB/y',evidence=[row('d','FALSE','3'),row('h','TRUE','1',scope='orgA/x'),row('d','FALSE','9',scope='orgA/x'),row('d','TRUE','1',final=True,source='second',scope='orgA/x'),row('d','TRUE','7')])]
        s=State.from_packs(packs);left,away=v.stored(packs);self.assertEqual((left,away,len(away),s.evidence['orgA/x|d']['source']),(s.evidence,s.event_journal,2,'second'))   # two rows turned away; a decision replaced by a decision
        for scope in ('orgA/x','orgB/y'):
            s.scope=scope
            for key in list(s.evidence)+[scope+'|missing']:
                fact=key.split('|',1)[1];self.assertEqual(v.reading(s.evidence,scope,fact),s.fact(fact)['truth'],(scope,fact))
        self.assertEqual({f:v.reading(s.evidence,'orgA/x',f) for f in ('e','f','n','n2','n3','c1','q','r','z','y','m1','m2','m3','u','h')},   # a version that differs, 1 against 1.0, a circle, a row that reads UNKNOWN or FALSE below, no version on both sides, a row that is not there, a row that was never stored
                         {'e':'TRUE','f':'UNKNOWN','n':'TRUE','n2':'UNKNOWN','n3':'TRUE','c1':'UNKNOWN','q':'UNKNOWN','r':'UNKNOWN','z':'FALSE','y':'UNKNOWN','m1':'TRUE','m2':'UNKNOWN','m3':'TRUE','u':'UNKNOWN','h':'TRUE'})
        for text,needs,want in (('',['a',''],True),(' b',['a','','b'],True),('a ',['a',''],True),(' ',['',''],True),('a  b',['a','','b'],True),('',['a'],False),('a',['a','b'],True),('a b',['a','b'],True),
                                ('b a',['a','b'],False),('a  b',['a','b'],False),('ab',['a','b'],False),('a,b',['a','b'],False),('two words b',['two words','b'],True),('c',['a','b'],False)):
            self.assertEqual(v.said(text,needs),want,(text,needs))   # the facts a prerequisite stop names: some of the step's prerequisites, in order; a fact may have the empty name
        def withdraws(s,m,mid,deps):
            for p,t in ((m['effect'],'TRUE'),('','FALSE')):s.observe(self._row(p,t,'2'))
            return {}
        def loses(s,m,mid,deps):s.observe(self._row(m['effect'],'TRUE','1'));s.methods.pop('later');return {}
        self._kinds(test_v_withdraws=withdraws,test_v_loses=loses)
        w=self._world(['G'],[],[self._m('a','A','test_v_withdraws'),self._m('g','G',req=['A',''])],[('','TRUE')]);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['stopped']['reason'],v.stop_ok(r,w.methods)),('Prerequisite not true before effect: ',True))   # the reason then names nothing, and is still the kernel's own
        w=self._world(['e'],[('e',[['x','y']])],[self._m('first','x','test_v_loses'),self._m('later','y')]);table=dict(w.methods);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['stopped']['reason'],self._ops(r)[-3:],v.stop_ok(r,table)),('Kernel fault: KeyError',['LOCAL_EFFECT','STEP_STOPPED','TERMINAL'],True))   # the exemption: a kernel fault before the step reached its gate stands right after a row of the plan
        done=self._world(['G'],[],[self._m('m','G')]);ok=Kernel(done).run_standing(execute=True)['runs'][0];offered=Kernel(self._world(['G'],[],[self._m('m','G')])).run_standing()['runs'][0]
        def settled(rows,run=ok,at=-1,kinds=None,**fields):   # a run with SETTLE_STOPPED rows put in, before its last row unless said otherwise
            t=list(run['trace']);t[at:at]=[{'operation':'SETTLE_STOPPED','data':x} for x in rows];return v.stop_ok(dict(run,trace=t,**fields),done.methods,kinds)
        one={'kind':'ask','reason':'KeyError'}
        self.assertEqual([settled([one],unsettled=['ask']),settled([one],unsettled=['ask'],kinds={'ask':1}),settled([one,{'kind':'simulate_fact','reason':'unreadable'}],unsettled=['ask','simulate_fact'])],[True,True,True])
        for name,got in (('a kind the registry does not have',settled([one],unsettled=['ask'],kinds={'simulate_fact':1})),('no reason',settled([{'kind':'ask'}],unsettled=['ask'])),
                         ('a reason in two words',settled([{'kind':'ask','reason':'Key Error'}],unsettled=['ask'])),('one field more',settled([dict(one,note='x')],unsettled=['ask'])),
                         ('one kind twice',settled([one,one],unsettled=['ask','ask'])),('not named under unsettled',settled([one])),('named in another order',settled([one,{'kind':'simulate_fact','reason':'KeyError'}],unsettled=['simulate_fact','ask'])),
                         ('before the rows of the plan',settled([one],at=1,unsettled=['ask'])),('on a plan that was only offered',settled([one],run=offered,unsettled=['ask']))):
            self.assertFalse(got,name)   # a SETTLE_STOPPED row is held to its two fields, its kind to the registry, its place to after the plan
        dry=Kernel(self._world(['G'],[],[self._m('m','G',req=['absent'])])).run_standing()['runs'][0]   # review round three, a known limit: a settle failure can be invented for a kind that has no settle hook, and on a blocked look that was dry (the kernel settles on neither): the record says neither which kinds have a settle hook nor whether a blocked look was dry
        self.assertEqual((dry['work_state'],settled([{'kind':'simulate_fact','reason':'KeyError'}],unsettled=['simulate_fact'],kinds={'simulate_fact':1}),settled([one],run=dry,unsettled=['ask'])),('blocked',True,True))
        def drops_grant(s,m,mid,deps):s.grants.discard('g');s.observe(self._row(m['effect'],'TRUE','1'));return {}
        def pops(s,m,mid,deps):s.providers.pop(m['provider']);return {}
        def bad_settle(s,result,log):raise KeyError('books')
        self._kinds(test_v_meddle=drops_grant,test_v_pops=pops,test_v_words=_throw(Stop('no room')),test_v_fail=_throw(OSError('disk')),test_v_none=lambda s,m,mid,deps:None,
                    test_v_settle=(lambda s,m,mid,deps:{},{'settle':bad_settle}))
        worlds={'Gate changed before effect: AUTHORITY_REQUIRED':self._world(['done'],[],[self._m('first','a','test_v_meddle'),self._m('second','done',req=['a'])]),
                'Prerequisite not true before effect: approved':self._world(['shipped'],[('approved',[['manager_ok']])],[self._m('ship','shipped',req=['approved'])],[('manager_ok','TRUE')]),
                'Handler refused: no room':self._world(['e'],[],[self._m('m','e','test_v_words')]),'Handler failed: OSError':self._world(['e'],[],[self._m('m','e','test_v_fail')]),
                'Handler returned what cannot be a receipt':self._world(['e'],[],[self._m('m','e','test_v_none')]),'Kernel fault: KeyError':self._world(['e'],[],[self._m('m','e','test_v_pops')])}
        for reason,w in worlds.items():   # every phrase the kernel can write is a phrase the verifier knows, with its gate row and its unsettled kinds
            r=Kernel(w).run_standing(execute=True)['runs'][0];self.assertEqual((r['stopped']['reason'],r['unsettled'],v.stop_ok(r,w.methods)),(reason,['test_v_settle'],True),reason)
            erased=dict(r,trace=[e for e in r['trace'] if e['operation']!='SETTLE_STOPPED']);del erased['unsettled'];self.assertTrue(v.stop_ok(erased,w.methods),reason)   # review round three, a known limit: a settle failure can be erased as well (its row and its name under unsettled taken out)
    def test_generator_shows_the_whole_plan_of_a_waiting_run_and_words_the_ask(self):
        s,k,r=self._asked();again=k.run_standing(execute=True)['runs'][0];dry=k.run_standing(execute=False)['runs'][0]
        answer(k,r['model_receipts'][0],'FALSE','customer')                                    # the books move on; the results below were made before
        for result in (r,again,dry):                                                           # the run that asked, and every look while it waited, give the same whole plan
            wf=to_implementation(result,s)['workflow'];steps={x['method']:x for x in wf['steps'] if x.get('method')}
            self.assertEqual(list(steps),['ask-customer-approval@1','ship-replacement@1']);self.assertEqual(validate_workflow(wf),[])
            a=steps['ask-customer-approval@1'];b=steps['ship-replacement@1']
            self.assertEqual((a['kind'],a['waits_for'],b['kind'],b['after'],b.get('waits_for')),('ask','customer','simulate_fact',['ask-customer-approval-1'],None))
            self.assertTrue(a['action'].startswith('ask customer: May we send a replacement'));self.assertIn("citing this ask's receipt",a['verify'])
            self.assertEqual([x['name'] for x in j2_atoms(result)['atoms']],['ask-customer-approval@1','ship-replacement@1'])
            plan=to_implementation(result,s)['plan'];self.assertEqual((plan['cost'],plan['waits']),({'compute':2,'money':2,'attention':1},['ask-customer-approval@1']))   # the plan's cost, not only what ran
        self.assertIn('still to pay {"attention":0,"compute":2,"money":2} within {"attention":2,"compute":10,"money":10}',to_implementation(again,s)['workflow']['verify'])   # what is paid is not set against what is left
        tight=State.from_packs([pack(n) for n in ASK]+[{'schema':'sutra-extension/2','id':'cut','budget':{'compute':1}}]);over=to_implementation(again,tight)['workflow']
        self.assertEqual(over['over_budget'],{'compute':2,'money':2,'attention':0});self.assertTrue(any('budget left' in p for p in validate_workflow(over)))
        self.assertEqual([to_implementation(x,s)['plan'][key] for x in (r,again) for key in ('ran','spent')],[['ask-customer-approval@1'],{'compute':0,'money':0,'attention':1},[],self.ZERO])
        self.assertEqual((minimal_graph_diff(r,again)['added'],minimal_graph_diff(r,again)['retired'],reflect([r,again,again])['candidates']),([],[],[]))   # a wait is the same plan, and no composition to reuse
        methods=[self._m('prepare-quote','quote_ready',req=['stock']),self._m('ask-approval','approved','ask',self.ASKS,req=['quote_ready'],ask_to='customer'),self._m('ship','done',req=['approved','quote_ready'])]
        w=self._world(['done'],[],methods,[('stock','TRUE')]);kw=Kernel(w);parked=kw.run_standing(execute=True)['runs'][0];redo=kw.on_event(self._row('stock','TRUE','2'),execute=True)['runs'][0]
        for result,plan,edges in ((parked,['prepare-quote','ask-approval','ship'],[('prepare-quote','ask-approval'),('ask-approval','ship'),('prepare-quote','ship')]),
                                  (redo,['ask-approval','prepare-quote','ship'],[('ask-approval','ship'),('prepare-quote','ship')])):   # the question is already out: the quote to make again comes after it, not before
            wf=to_implementation(result,w)['workflow'];self.assertEqual(([x['method'] for x in wf['steps'] if x.get('method')],validate_workflow(wf)),(plan,[]))
            self.assertEqual(sorted((e['from'],e['to']) for e in wf['edges']),sorted(edges))
        sim=self._world(['e'],[],[self._m('assume','e',ask_to='owner')])                       # a field named ask_to does not make a step an ask
        step=[x for x in to_implementation(Kernel(sim).run_standing()['runs'][0],sim)['workflow']['steps'] if x.get('method')][0]
        self.assertEqual((step['kind'],step.get('waits_for'),step['action'].startswith('make e true')),('simulate_fact',None,True))
        blocked=to_implementation(k.run_standing()['runs'][0],s)['workflow']
        self.assertEqual(blocked['blocked'],'REFUSED');self.assertTrue(any('blocked (REFUSED)' in p for p in validate_workflow(blocked)))
    def test_hash_chain_valid(self):
        c=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]);r=Kernel(c).run_standing(execute=True)['runs'][0]
        for i,x in enumerate(r['trace']):
            self.assertEqual(x['seq'],i+1)
            self.assertEqual(x['prev_sha256'],r['trace'][i-1]['sha256'] if i else 'GENESIS')
            self.assertEqual(x['sha256'],digest({k:v for k,v in x.items() if k!='sha256'}))

# one independently named regression per authored stage
for case in CASES:
    cid,_,_,files,execute,_=case
    def make_test(caseid=cid,fp=list(files),effect=execute):
        def check(self):
            context=State.from_packs([pack(n) for n in fp]);ran=Kernel(context).run_standing(execute=effect)
            status=ran['runs'][0]['status'] if ran['runs'] else ran['status']
            self.assertEqual(status,EXPECTED[caseid]);self.assertTrue(all(x>=0 for x in context.budget.values()))
        return check
    setattr(ContractTests,'test_stage_'+cid,make_test())

if __name__=='__main__':unittest.main()
