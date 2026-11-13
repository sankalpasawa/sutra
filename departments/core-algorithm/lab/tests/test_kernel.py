from pathlib import Path
import unittest, sys, json, copy, hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest,ACTIONS,register
from tools.run_all import CASES,pack,extra_events,ASK
from extensions.asks import answer,open_asks
from extensions.j2_projection import to_j2_proposed_atom_views as j2_atoms
from extensions.knowledge import compile_pattern,signal_priority
from extensions.reflection import minimal_graph_diff,reflect,Learner
from extensions.j2_projection import to_j2_proposed_atom_views
from extensions.implementation import to_implementation,validate_workflow

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
 '27_registrable_generated':'SUPPORTED_BY_EVIDENCE','28_website':'PLAN_READY','29_ask':'WAITING'
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
        with self.assertRaises(RuntimeError):Kernel(s).run_standing(execute=True)
        self.assertEqual(s.fact('replacement_delivered')['truth'],'FALSE')
        s=State.from_packs([pack(n) for n in ('00_goal','01_domain','02_methods','04_admission')]);k=Kernel(s)   # approval unknown
        with self.assertRaises(RuntimeError):k._act({'actions':['ship-replacement@1']})
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
                with self.assertRaises(RuntimeError):k._act({'actions':['assume-approval@1']})   # even run by hand, a method cannot write over a decision
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
            with self.assertRaises(RuntimeError):k.run_standing(execute=True)
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
        self.assertEqual(Kernel(w).run_standing()['runs'][0]['status'],'PLAN_READY')
        with self.assertRaises(RuntimeError):Kernel(w).run_standing(execute=True)   # a known limit kept from 0.7.0: the gate reads stored evidence only, so this plan stops at the gate
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
    def test_what_round_eight_left_as_stated_limits_is_pinned(self):
        # Round eight refuted nothing. These are the points it raised that this version states as limits; the next version removes them, and these lines then change.
        w=State();self.assertTrue(w.observe({'predicate':'z','truth':'TRUE','verified':True,'depends_on':[{'predicate':'q','version':True}]}))
        self.assertEqual(w.fact('z')['truth'],'UNKNOWN')   # a version named inside depends_on is not checked: such a row is stored and can never read valid
        s=self._world(['g'],[],[self._m('m','g')]);self.assertEqual(Kernel(s).resolve('g',execute=1)['status'],'LOCAL_MODEL_EFFECTS_RECORDED')   # execute is read as it is given: 1 runs like true
        big=10**4300-1;w=State()   # every amount is inside the bound on integers; the sum of two is not
        w.apply({'schema':'sutra-extension/2','id':'x','goals':['b'],'grants':['g'],'providers':{'prov':2},'budget':{'compute':big},
                 'methods':[self._m('ma','a',cost={'compute':big}),self._m('mb','b',cost={'compute':big},req=['a'])]})
        try:status=Kernel(w).resolve('b')['status']
        except ValueError:status='the sum cannot be written down'   # a Python that limits the text of an integer (3.10.7 and later)
        self.assertIn(status,('RESOURCE_REQUIRED','the sum cannot be written down'))
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
