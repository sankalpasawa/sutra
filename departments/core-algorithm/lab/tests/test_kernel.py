from pathlib import Path
import unittest, sys, json, copy, hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest
from tools.run_all import CASES,pack,extra_events
from extensions.knowledge import compile_pattern,signal_priority
from extensions.reflection import minimal_graph_diff,reflect
from extensions.j2_projection import to_j2_proposed_atom_views

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
 '22_revoke':'AUTHORITY_REQUIRED','23_capacity':'PROVIDER_REQUIRED','24_budget':'RESOURCE_REQUIRED'
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
