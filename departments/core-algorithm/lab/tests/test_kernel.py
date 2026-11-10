from pathlib import Path
import unittest, sys, json, copy, hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest,ACTIONS,register
from tools.run_all import CASES,pack,extra_events
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
 '27_registrable_generated':'SUPPORTED_BY_EVIDENCE','28_website':'PLAN_READY'
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
        k.run_standing(execute=True)
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
            with self.assertRaises(ValueError):s.apply({'schema':'sutra-extension/2','id':'late','methods':[{'id':'x','effect':'y','action':'test_only_kind'}]})
        finally:del ACTIONS['test_only_kind']
    def test_handler_cannot_set_receipt_fields_or_run_before_prerequisites(self):
        packs=[pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]
        s=State(actions={'simulate_fact':lambda s,m,mid,deps:{'status':'EXTERNAL_DONE'}})
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
            s=State(actions={k:watched(f) for k,f in ACTIONS.items()})
            for n in files:s.apply(pack(n))
            Kernel(s).run_standing(execute=execute)
        self.assertTrue(len(seen)>=20 and all(seen))
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
