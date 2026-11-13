"""Author reviewed synthetic fixture packs outside the fixed kernel; NOT automated domain discovery."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'scenarios';P.mkdir(exist_ok=True)
def pack(name,**fields):
    x={'schema':'sutra-extension/2','id':name,**fields}
    (P/(name+'.json')).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def fact(p,t,source='fixture/reviewed',version='1',scope=None):
    x={'predicate':p,'truth':t,'verified':True,'source':source,'version':version}
    if scope:x['scope']=scope
    return x
def rule(id,head,branches,replaces=None,source='fixture/reviewed-domain-theory',**more):
    x={'id':id,'head':head,'branches':branches,'approved':True,'source':source,**more}
    if replaces:x['replaces']=replaces
    return x
def method(id,effect,requires=(),provider='local-provider',grant=None,cost=None,action='simulate_fact',**kw):
    return {'id':id,'effect':effect,'requires':list(requires),'provider':provider,
            'grant':grant or f'action:{id}','cost':cost or {'compute':1,'money':1,'attention':0},
            'action':action,'approved':True,'source':'reviewed/synthetic-method',**kw}
pack('00_goal', scope='orgA/fulfillment',goals=['order_complete'],budget={'compute':10,'money':10,'attention':3},
     preference=['compute','money','attention'])
pack('01_domain',rules=[rule('R-ORDER@1','order_complete',[['original_delivered'],['replacement_delivered']])],
     evidence=[fact('original_delivered','FALSE'),fact('replacement_delivered','FALSE'),
       fact('original_stock','FALSE'),fact('substitute_stock','TRUE'),fact('customer_notified','FALSE')])
pack('02_methods',methods=[
 method('ship-original@1','original_delivered',['original_stock'],cost={'compute':1,'money':1,'attention':0}),
 method('ship-replacement@1','replacement_delivered',['substitute_stock','customer_approved'],cost={'compute':2,'money':2,'attention':0})])
pack('03_approval',evidence=[fact('customer_approved','TRUE',version='approval-v1',source='fixture/customer-approval')])
pack('04_admission',providers={'local-provider':5},grants=['action:ship-original@1','action:ship-replacement@1'])
pack('05_learning',learning=True)
pack('06_notify',rules=[rule('R-ORDER@2','order_complete',[['original_delivered'],['replacement_delivered','customer_notified']],replaces='R-ORDER@1')],
     methods=[method('notify-customer@1','customer_notified',['replacement_delivered'],cost={'compute':1,'money':1,'attention':0})],
     grants=['action:notify-customer@1'])
pack('07_survey_gap',rules=[rule('R-ORDER@3','order_complete',[['original_delivered'],['replacement_delivered','customer_notified','survey_recorded']],replaces='R-ORDER@2')],
     evidence=[fact('survey_recorded','FALSE')])
pack('08_survey_authored',methods=[method('record-survey@1','survey_recorded',['replacement_delivered'],cost={'compute':1,'money':1,'attention':0})],
     grants=['action:record-survey@1'])
pack('09_fast_tradeoff',methods=[method('ship-fast@1','replacement_delivered',['substitute_stock','customer_approved'],
                            cost={'compute':1,'money':4,'attention':0}),
                            method('ship-economy@1','replacement_delivered',['substitute_stock','customer_approved'],
                            cost={'compute':3,'money':1,'attention':0})],
     grants=['action:ship-fast@1','action:ship-economy@1'])
pack('10_money_first',preference=['money','compute','attention'])
pack('11_no_goal',goals=[])
pack('12_other_tenant',evidence=[fact('customer_approved','TRUE',source='orgB/doc',version='orgB-v1',scope='orgB/fulfillment')])
pack('13_revoke_authority',revoke_grants=['action:ship-replacement@1'])
pack('14_remove_capacity',providers={'local-provider':0})
pack('15_low_budget',budget={'compute':0,'money':0,'attention':0})
# Second domain. Existing domain theory is approved; no automatic discovery from natural language.
pack('20_enquiry_goal',scope='orgA/enquiries',goals=['enquiry_complete'],budget={'compute':10,'money':10,'attention':2},
     preference=['money','compute','attention'])
pack('21_enquiry_theory',rules=[rule('R-ENQUIRY@1','enquiry_complete',[['record_stored','record_retrievable'],['support_inbox_retrievable']])],
     evidence=[fact('record_stored','FALSE'),fact('record_retrievable','FALSE'),fact('support_inbox_retrievable','FALSE'),fact('enquiry_valid','TRUE')])
pack('22_enquiry_methods',methods=[
 method('store-enquiry@1','record_stored',['enquiry_valid'],cost={'compute':2,'money':1,'attention':0}),
 method('readback-enquiry@1','record_retrievable',['record_stored'],cost={'compute':1,'money':1,'attention':0})],
 providers={'local-provider':5},grants=['action:store-enquiry@1','action:readback-enquiry@1'])
pack('23_enquiry_extra_knowledge',rules=[rule('R-ENQUIRY@2','enquiry_complete',
     [['record_stored','record_retrievable','privacy_checked'],['support_inbox_retrievable','privacy_checked']],replaces='R-ENQUIRY@1')],
     evidence=[fact('privacy_checked','FALSE')])
pack('24_enquiry_privacy',methods=[method('check-privacy@1','privacy_checked',['enquiry_valid'],cost={'compute':1,'money':1,'attention':0})],
     grants=['action:check-privacy@1'])
# Generic capability construction is a LOCAL contract candidate, never installed by itself.
pack('30_build_goal',scope='orgA/enquiries',goals=['capability_candidate_created'],budget={'compute':10,'money':10,'attention':2},
     preference=['compute','money','attention'])
pack('31_build_theory',evidence=[fact('capability_candidate_created','FALSE'),fact('source_contract_reviewed','TRUE'),
                                fact('component_validate','FALSE'),fact('component_store','FALSE'),fact('component_read','FALSE')])
pack('32_builder_components',methods=[
 method('validate-field@1','component_validate',['source_contract_reviewed'],cost={'compute':1,'money':0,'attention':0}),
 method('store-component@1','component_store',['source_contract_reviewed'],cost={'compute':1,'money':0,'attention':0}),
 method('read-component@1','component_read',['source_contract_reviewed'],cost={'compute':1,'money':0,'attention':0}),
 method('construct-enquiry-candidate@1','capability_candidate_created',
        ['component_validate','component_store','component_read'],action='compile_candidate',
        constructor='C-ENQUIRY@1',cost={'compute':1,'money':0,'attention':0})],
     constructors=[{'id':'C-ENQUIRY@1','target_effect':'record_retrievable',
                    'components':['validate-field@1','store-component@1','read-component@1'],
                    'required_effects':['component_validate','component_store','component_read'],
                    'source':'reviewed/contract-template'}],
     providers={'local-provider':5},grants=['action:validate-field@1','action:store-component@1',
         'action:read-component@1','action:construct-enquiry-candidate@1'])
# Counterexample: supplied composer is invalid, its candidate MUST NOT self-promote.
pack('33_bad_constructor',scope='orgA/enquiries',goals=['capability_candidate_created'],
     evidence=[fact('source_contract_reviewed','TRUE')],
     constructors=[{'id':'C-ENQUIRY@1','target_effect':'record_retrievable',
                    'components':['validate-field@1','store-component@1','read-component@1'],
                    'required_effects':['component_validate','component_store','component_read','component_audit'],
                    'source':'reviewed/contract-template-v2'}])
pack('34_manually_accepted',scope='orgA/enquiries',goals=['enquiry_complete'],
     methods=[method('reviewed-composition@1','support_inbox_retrievable',['enquiry_valid'],
               cost={'compute':1,'money':2,'attention':0})],
     grants=['action:reviewed-composition@1'],providers={'local-provider':4},
     evidence=[fact('enquiry_valid','TRUE')])
# Self-application is goal/work only, not actual rewrite of kernel or validator.
pack('40_self_goal',scope='sutra/core',goals=['better_method_candidate'],budget={'compute':8,'money':5,'attention':1},
     preference=['compute','money','attention'])
pack('41_self_theory',rules=[rule('R-SELF@1','better_method_candidate',
                                  [['benchmark_available','candidate_tested','review_requested']])],
     evidence=[fact('benchmark_available','TRUE'),fact('candidate_tested','FALSE'),fact('review_requested','FALSE')])
pack('42_self_methods',methods=[
 method('run-heldout-test@1','candidate_tested',['benchmark_available'],cost={'compute':2,'money':0,'attention':0}),
 method('request-review@1','review_requested',['candidate_tested'],cost={'compute':1,'money':0,'attention':1})],
 providers={'local-provider':2},grants=['action:run-heldout-test@1'])
pack('43_self_review_grant',grants=['action:request-review@1'])
# Source-backed knowledge pattern meant to become a candidate, not trusted rule.
pack('50_unapproved_semantics',scope='orgA/enquiries',goals=['enquiry_complete'],
     rules=[{'id':'R-ENQUIRY-DRAFT@1','head':'enquiry_complete','branches':[['record_stored']],
             'approved':False,'source':'LLM/candidate-unreviewed'}])
# A standard is a reviewed rule over evidence an adapter produced (0.5.0-standards, program slice S3).
import sys;sys.path.insert(0,str(ROOT))
from extensions.standards import workflow_facts
# The shape of a hand-written intent workflow (as deployed W-start-department.json: steps carry an action, no check of their own).
HANDWRITTEN={'id':'W-handwritten-sample','name':'a hand-written intent workflow','version':'1',
             'trigger':{'kind':'intent','utterance_patterns':['start (a )?(new )?department( .*)?']},
             'steps':[{'id':'record-intent','host':'codex','sandbox':'read-only','action':'log the line to the execution record'},
                      {'id':'create','host':'claude-effector','sandbox':'workspace-write','action':'create the department through the app ask'},
                      {'id':'open','host':'claude-effector','sandbox':'read-only','action':'open the department'}],
             'verify':'the department exists in the tree with its charter'}
def generated_workflow():
    """The workflow the lab's own implementation generator emits for the order plan with the notification rule."""
    from kernel.core import State,Kernel
    from extensions.implementation import to_implementation
    s=State.from_packs([json.loads((P/(n+'.json')).read_text()) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission','06_notify')])
    return to_implementation(Kernel(s).run_standing()['runs'][0],s)['workflow']
pack('60_standard_goal',scope='sutra/workflows',goals=['workflow_registrable'],budget={'compute':5,'money':5,'attention':2},
     preference=['compute','money','attention'])
pack('61_standard_theory',rules=[rule('R-REGISTRABLE@1','workflow_registrable',[['has_trigger','every_step_has_check','has_overall_verify']],
                                      source='reviewed/workflow-standard')])
pack('62_handwritten_evidence',evidence=workflow_facts(HANDWRITTEN))
pack('63_repair_method',methods=[method('add-step-checks@1','every_step_has_check',['has_overall_verify'],cost={'compute':1,'money':0,'attention':1})],
     providers={'local-provider':2},grants=['action:add-step-checks@1'])
pack('64_generated_evidence',evidence=workflow_facts(generated_workflow()))
# A human ask (0.8.0-ask): the customer's approval is unknown; a reviewed method of kind `ask` asks for it and the run waits.
pack('80_ask_method',methods=[method('ask-customer-approval@1','customer_approved',[],provider='owner-channel',
                                     cost={'compute':0,'money':0,'attention':1},action='ask',
                                     question='May we send a replacement for the item that is out of stock?',ask_to='customer')],
     providers={'owner-channel':2},grants=['action:ask-customer-approval@1'])
# A plan made again (0.8.0-ask, round five): when the quote is re-made, the approval and the shipment that rested on it read true again, and their steps are skipped.
pack('81_made_again',scope='orgA/quotes',goals=['order_shipped'],budget={'compute':10,'money':10,'attention':3},
     methods=[method('prepare-quote@1','quote_ready'),method('assume-approval@1','quote_approved',['quote_ready'],cost={'compute':3,'money':3,'attention':0}),
              method('ship-quoted@1','order_shipped',['quote_ready','quote_approved'])],
     providers={'local-provider':6},grants=['action:prepare-quote@1','action:assume-approval@1','action:ship-quoted@1'])
# Fourth domain (0.6.0-order): a website for an organisation. A chain of four methods; the plan must come out in order.
pack('70_site_goal',scope='orgA/website',goals=['site_live'],budget={'compute':10,'money':5,'attention':3},
     preference=['attention','money','compute'])
pack('71_site_theory',rules=[rule('R-SITE@1','site_live',[['site_checked']],source='reviewed/website-department')],
     evidence=[fact('brief_given','TRUE',source='fixture/owner-brief'),fact('site_planned','FALSE'),fact('content_written','FALSE'),
               fact('pages_built','FALSE'),fact('site_checked','FALSE')])
pack('72_site_methods',methods=[
 method('check-site@1','site_checked',['pages_built'],cost={'compute':1,'money':0,'attention':1}),
 method('build-pages@1','pages_built',['content_written','site_planned'],cost={'compute':3,'money':1,'attention':0}),
 method('write-content@1','content_written',['site_planned'],cost={'compute':2,'money':1,'attention':0}),
 method('plan-site@1','site_planned',['brief_given'],cost={'compute':1,'money':0,'attention':1})],
 providers={'local-provider':6},grants=['action:plan-site@1','action:write-content@1','action:build-pages@1','action:check-site@1'])
if __name__=='__main__':print('Generated',len(list(P.glob('*.json'))),'authored data pack fixtures')
