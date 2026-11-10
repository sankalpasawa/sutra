"""Produce all recorded stage results from one UNCHANGED kernel + versioned extension data."""
from __future__ import annotations
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest
from extensions.reflection import Learner   # learning lives in the extension since 0.4.0-shrink (move-out M1)
from tools.make_packs import P

CASES=[
 ('00_goal','Goal alone','Intent exists; domain meaning is absent.',['00_goal'],False,'Foundation'),
 ('01_meaning','Meaning / domain theory','The accepted AND/OR rule derives two possible fulfillment routes.',['00_goal','01_domain'],False,'Condition discovery'),
 ('02_methods','Method discovery','Method preconditions reveal an unknown customer approval.',['00_goal','01_domain','02_methods'],False,'Adaptation'),
 ('03_evidence','Evidence retrieval','Synthetic approval evidence exists, but no execution authorization.',['00_goal','01_domain','02_methods','03_approval'],False,'Evidence'),
 ('04_gates','Provider + authority','Eligible local action may simulate replacement delivery.',['00_goal','01_domain','02_methods','03_approval','04_admission'],True,'Execution'),
 ('05_learn','Terminal learning','The same execution emits a reuse proposal, never self-promotes.',['00_goal','01_domain','02_methods','03_approval','04_admission','05_learning'],True,'Reflection'),
 ('06_nuance','Additional business nuance','A new reviewed notification obligation changes the plan, not the kernel.',['00_goal','01_domain','02_methods','03_approval','04_admission','05_learning','06_notify'],True,'Domain evolution'),
 ('07_gap','Missing capability','A further surveyed-feedback obligation reveals a Method gap.',['00_goal','01_domain','02_methods','03_approval','04_admission','05_learning','06_notify','07_survey_gap'],False,'Capability growth'),
 ('08_method_added','New method extension','Manually authored survey method closes the previously detected local gap.',['00_goal','01_domain','02_methods','03_approval','04_admission','05_learning','06_notify','07_survey_gap','08_survey_authored'],True,'Capability extension'),
 ('09_pareto','Competing methods','Pareto preference chooses a compute-efficient but money-costly valid plan.',['00_goal','01_domain','02_methods','03_approval','04_admission','09_fast_tradeoff'],False,'Priority'),
 ('10_preference','Different selection policy','A money-first preference changes selected plan without code changes.',['00_goal','01_domain','02_methods','03_approval','04_admission','09_fast_tradeoff','10_money_first'],False,'Priority'),
 ('11_knowledge_gap','Unapproved meaning','Unreviewed semantic rule never becomes trusted domain truth.',['50_unapproved_semantics'],False,'Knowledge governance'),
 ('12_enquiry','New domain','The same interpreter solves a simulated enquiry persist/read-back plan.',['20_enquiry_goal','21_enquiry_theory','22_enquiry_methods'],True,'Domain portability'),
 ('13_privacy_gap','Constraint extension','New reviewed privacy constraint reveals a missing Method.',['20_enquiry_goal','21_enquiry_theory','22_enquiry_methods','23_enquiry_extra_knowledge'],False,'Condition discovery'),
 ('14_privacy_method','New constraint handled','A verified local privacy-check Method extends the old enquiry plan.',['20_enquiry_goal','21_enquiry_theory','22_enquiry_methods','23_enquiry_extra_knowledge','24_enquiry_privacy'],True,'Domain evolution'),
 ('15_constructor','Bounded method constructor','Existing reviewed components are combined into candidate capability.',['30_build_goal','31_build_theory','32_builder_components'],True,'Method formation'),
 ('16_bad_constructor','Counterexample to construction','Changed hidden contract demands another component: candidate fails independent gate.',['30_build_goal','31_build_theory','32_builder_components','33_bad_constructor'],True,'Method formation'),
 ('17_reviewed_release','Explicit external registration','A separately supplied reviewed method can be used, not silently promoted.',['20_enquiry_goal','21_enquiry_theory','22_enquiry_methods','34_manually_accepted'],True,'Governance'),
 ('18_self_need','Self-directed improvement goal','Improvement is a normal goal but requires a review grant.',['40_self_goal','41_self_theory','42_self_methods'],False,'Self-application'),
 ('19_self_grant','Governed self-directed work','Review-request step can be locally simulated after explicit grant; no code rewrite.',['40_self_goal','41_self_theory','42_self_methods','43_self_review_grant'],True,'Self-application'),
 ('20_wrong_tenant','Scoped evidence','orgB approval cannot satisfy orgA.',['00_goal','01_domain','02_methods','04_admission','12_other_tenant'],False,'Tenant isolation'),
 ('21_no_goal','No standing obligation','Without standing goal the system schedules nothing.',['00_goal','01_domain','11_no_goal'],False,'Standing goals'),
 ('22_revoke','Revoked authority','Ready Method becomes blocked without the relevant scoped grant.',['00_goal','01_domain','02_methods','03_approval','04_admission','13_revoke_authority'],False,'Governance'),
 ('23_capacity','Provider scarcity','A method exists but no provider slot remains.',['00_goal','01_domain','02_methods','03_approval','04_admission','14_remove_capacity'],False,'Resources'),
 ('24_budget','Insufficient resources','A solution exists but cannot fit the nonfungible budget.',['00_goal','01_domain','02_methods','03_approval','04_admission','15_low_budget'],False,'Resources'),
 ('25_registrable_gap','A standard as a rule','A hand-written workflow fails a reviewed standard: the checker found steps without a check, and no method can add them.',['60_standard_goal','61_standard_theory','62_handwritten_evidence'],False,'Standards'),
 ('26_registrable_repair','Repair to the standard','A reviewed method that adds step checks turns the failed standard into a plan.',['60_standard_goal','61_standard_theory','62_handwritten_evidence','63_repair_method'],True,'Standards'),
 ('27_registrable_generated','Generated work meets the standard','The workflow the implementation generator emits passes the same standard on evidence alone.',['60_standard_goal','61_standard_theory','64_generated_evidence'],True,'Standards'),
]

def pack(n):return json.loads((P/(n+'.json')).read_text())

def scenario(spec):
    cid,title,description,files,execute,area=spec
    packs=[pack(n) for n in files]
    state=State.from_packs(packs)
    run=Learner.from_packs(packs).attach(Kernel(state).run_standing(execute=execute))
    outcome=run['runs'][0] if run['runs'] else None
    return {'id':cid,'title':title,'description':description,'area':area,'packs':files,'pack_digest':digest(packs),
            'scope':state.scope,'run':run,'outcome':outcome,
            'derived_state':{'facts':state.evidence,'rule_ids':[r['id'] for r in state.rules.values()],
                             'candidate_count':len(state.candidates),'budget_after':state.budget,
                             'historical_events':state.event_journal},
            'four_views':{'world':[{'predicate':k,'truth':v['truth'],'source':v.get('source')} for k,v in state.evidence.items()],
                          'knowledge':list(state.rules.values()),
                          'design':outcome['actions'] if outcome else [],
                          'run':outcome['trace'] if outcome else []}}

def extra_events():
    packs=[pack(n) for n in ['00_goal','01_domain','02_methods','03_approval','04_admission','06_notify']]
    s=State.from_packs(packs)
    k=Kernel(s)
    first=k.run_standing(execute=True)
    old_hash=first['runs'][0]['trace_root_sha256']
    irrelevant=k.on_event({'predicate':'marketing_banner','truth':'TRUE','version':'2','verified':True,'source':'fixture/marketing'},execute=False)
    cross_tenant=k.on_event({'predicate':'customer_approved','truth':'TRUE','scope':'orgB/fulfillment','version':'approval-B','verified':True,'source':'fixture/other-tenant'},execute=False)
    revoked=k.on_event({'predicate':'customer_approved','truth':'FALSE','scope':'orgA/fulfillment',
                        'version':'approval-v2','verified':True,'source':'fixture/revoked'},execute=False)
    # Rule update itself is a reviewed new version, rather than mutation of stored old run.
    revised=pack('07_survey_gap');s.apply(revised)
    updated=k.run_standing(execute=False)
    learner=Learner.from_packs(packs)   # one Learner for this State's whole life, fed in run order
    for run in (first,irrelevant,cross_tenant,revoked):learner.attach(run)
    learner.apply(revised);learner.attach(updated)
    return {'initial':first,'unrelated':irrelevant,'cross_tenant':cross_tenant,'approval_revoked':revoked,
            'rule_updated':updated,'old_trace_hash_before':old_hash,'old_trace_hash_after':first['runs'][0]['trace_root_sha256'],
            'impacted_fact_after_revoke':s.fact('replacement_delivered'),
            'journal_count':len(s.event_journal)}

def build():
    result={'release':'sutra-kernel-extensions/0.5.0-standards',
            'kernel_sha256':hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest(),
            'baseline_v0_1_sha256':hashlib.sha256((ROOT/'release'/'baseline_v0_1_core.py').read_bytes()).hexdigest(),
            'scope':'finite synthetic deterministic local simulation; NOT historical Core, current J2, or external outcomes',
            'cases':[scenario(x) for x in CASES],
            'events':extra_events()}
    target=ROOT/'results'/'actual_run_records.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('WROTE',len(result['cases']),'runs to',target)
    for case in result['cases']:
        status=case['outcome']['status'] if case['outcome'] else case['run']['status']
        actions=' '.join(case['outcome']['actions']) if case['outcome'] else '-'
        print(f"{case['id']:<24} {status:<34} {actions[:85]}")
    return result

if __name__=='__main__':build()
