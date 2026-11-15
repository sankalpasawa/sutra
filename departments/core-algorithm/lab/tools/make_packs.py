"""Author reviewed synthetic fixture packs outside the fixed kernel; NOT automated domain discovery."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'scenarios';P.mkdir(exist_ok=True);AUTHORED=[]   # every pack authored in this run, in order (the add-on points at the end read it)
def pack(name,**fields):
    x={'schema':'sutra-extension/2','id':name,**fields}
    (P/(name+'.json')).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n');AUTHORED.append(name)
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
# A step that cannot run (the recorded stop): the builder's components without the constructor its last step names. The dry look cannot tell; the executed look stops at that step, on the record.
_c=json.loads((P/'32_builder_components.json').read_text());pack('82_components_without_constructor',**{k:v for k,v in _c.items() if k not in ('schema','id','constructors')})
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
# ---- Add-on points (0.10.0): what a later version adds as files, each in its own place; nothing above changes. ----
# Added files are reviewed code that runs with the lab's rights. What follows refuses an honest author's mistakes (a stray file, a pack authored twice, a method id with
# two meanings, a kind registered in the wrong place) with REFUSED and a reason; it is not a fence around code written to deceive (ruling R31).
# Not looked for here: a pack file, a kind or an extension that writes files, rewrites the scenario file of a pack authored before it in the same run, or changes the
# kernel's classes while it runs (a unit test of the points shows a pack file that does all three and is taken).
import re,importlib.util
import extensions.constructor,extensions.asks   # the lab's own action kinds are registered before a kind file is read, so a kind file named like one of them is refused before it is loaded
from kernel.core import ACTIONS
PLAIN=r'[0-9a-z][0-9a-z_]*';PACK=r'[0-9a-z][0-9a-z_@.-]*'   # the name of an add-on file before its suffix; the name of a pack
def plug(folder,suffix):
    """The add-on files of one place in name order (tools/packs, cases, tools/scenes, kinds). Only a plain file counts: digits, small letters and underscores, beginning
    with a digit or a letter, then the suffix. Anything else found there (a hidden file, a draft, a folder, a link, another suffix) stops the build with its name."""
    found=[f for f in (sorted(folder.iterdir()) if folder.is_dir() else []) if f.name!='__pycache__']
    odd=[f.name for f in found if not (f.is_file() and not f.is_symlink() and f.suffix==suffix and re.fullmatch(PLAIN,f.stem))]
    if odd:raise ValueError(f'REFUSED {folder.name}/: not an add-on file: {odd}')
    return found
def held():return {kind:dict(hooks) for kind,hooks in ACTIONS.items()}   # the registry as it stands: for every kind, its handler and its hooks (the functions themselves)
def rebound(was):
    """The kinds of `was` (a copy of the registry taken earlier, held()) that are gone, or whose handler or hooks are no longer the same functions."""
    return sorted(k for k,hooks in was.items() if k not in ACTIONS or set(ACTIONS[k])!=set(hooks) or any(ACTIONS[k][h] is not fn for h,fn in hooks.items()))
def load_kinds(folder):
    """Action kinds a later version adds: kinds/<kind>.py is reviewed code that registers, with the kernel's register, the one kind its file is named after, with a
    handler written in that file. The kinds are loaded here, before any pack file runs. The build stops at a kind file that is named like a kind that is registered
    already (a built-in kind), that does not register its kind, that registers it with a handler written in another file (the record names a kind's handler by the
    module the function says it is of and holds that file by sha256; the check S41 holds a declared kind to kinds/<kind>.py, so such a kind would fail the verifier
    after the build), that registers a second kind, or that has changed the handler or a hook of another kind when it is loaded; what it did to the registry is taken
    back first.
    A KIND FILE IMPORTS NO OTHER KIND FILE. Loading the importer runs the other file, and the kind that file registers then counts as a second kind of the importer:
    a_first.py that imports from b_second.py is refused (the words name the second kind, not the import). With the names the other way round (a_helper.py, b_user.py)
    the helper's file is loaded first, the import finds it loaded, and both kinds are taken. So the pair is refused or taken by the order of the two file names. A
    helper two kinds share lives in extensions/<name>.py. A unit test of the points pins both orders."""
    names=[]
    for f in plug(folder,'.py'):
        name='kinds.'+f.stem;before=held()
        if name not in sys.modules:
            if f.stem in ACTIONS:raise ValueError(f'REFUSED kinds/{f.name}: the action kind {f.stem} is registered already (a built-in kind, or a kind other code registered); a kind file brings a kind of its own')
            spec=importlib.util.spec_from_file_location(name,f);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod
            try:spec.loader.exec_module(mod)
            except BaseException:del sys.modules[name];raise
        more=sorted(set(ACTIONS)-set(before)-{f.stem});moved=rebound(before)
        lives=getattr(ACTIONS[f.stem].get('run'),'__module__',None) if f.stem in ACTIONS else name   # the module the kind's handler says it is written in
        if f.stem not in ACTIONS or more or moved or lives!=name:   # what it registered or changed is taken back and the build stops
            for kind in set(ACTIONS)-set(before):del ACTIONS[kind]
            for kind in moved:ACTIONS[kind]=dict(before[kind])
            sys.modules.pop(name,None)
            if more or moved:raise ValueError(f'REFUSED kinds/{f.name}: it registers or changes other action kinds than its own: {more+moved}')
            if lives!=name:raise ValueError(f"REFUSED kinds/{f.name}: the handler it registers for {f.stem} is written in another file (it is a function of the module {lives}); a kind's handler is a function of its own file, kinds/{f.stem}.py, where the record and the check S41 look for it")
            raise ValueError(f'REFUSED kinds/{f.name}: it does not register the action kind {f.stem}')
        names.append(f.stem)
    return names
def added_packs(folder,into,authored):
    """Scenario packs a later version adds: tools/packs/<name>.py is authoring code like the calls above, handed fact, rule, method and a pack() that only creates. A name
    already authored in this run (built in, or by another pack file) is refused, and so is a name that is no plain file name: a pack file that authors a pack again is
    stopped, with the name. A PACK NAMES ITS METHODS AS A LIST OF OBJECTS THAT EACH HAVE A TEXT ID (under `methods`; a pack without methods names none): the independent
    verifier keeps one table of methods over every scenario file, read by each method's id, so a pack out of that shape, also one that no case loads, would end the whole
    verification; it is refused here, before its scenario file is written. (A pack that shows what the kernel refuses of a malformed method is made in a unit test,
    in memory, not as a scenario file.) METHOD IDS ARE ONE NAMESPACE ACROSS THE LAB: a method id names one method, in every pack that names it. A pack may name a method
    id that another pack names (built in, or added) only with the same method, field for field; a pack that names it with other content is refused before its scenario
    file is written. (With one meaning per id the verifier's table says the same for every run.)"""
    known={}   # method id -> (the pack that named it first, the method as that pack's scenario file holds it)
    def note(name,x):
        named=x.get('methods',[]) if type(x) is dict else None
        if type(named) is not list or any(type(m) is not dict or type(m.get('id')) is not str for m in named):
            raise ValueError(f"REFUSED tools/packs: the pack {name} does not name its methods as a list of objects that each have a text id (`methods`); the verifier reads every method of every scenario file by its id")
        for m in named:
            first,method=known.setdefault(m['id'],(name,m))
            if json.dumps(method,sort_keys=True)!=json.dumps(m,sort_keys=True):
                raise ValueError(f"REFUSED tools/packs: the pack {name} names the method {m['id']}, which the pack {first} names with other content; a method id names one method in the whole lab (give the new method an id of its own)")
    for name in authored:
        if (into/(name+'.json')).is_file():note(name,json.loads((into/(name+'.json')).read_text()))
    def create(name,**fields):
        if type(name) is not str or not re.fullmatch(PACK,name) or {'schema','id'}&set(fields):raise ValueError(f'REFUSED tools/packs: {name!r} is no plain pack name, or the pack sets its own schema or id')
        if name in authored:raise ValueError(f'REFUSED tools/packs: the pack {name} is already authored; a pack file only creates')
        text=json.dumps({'schema':'sutra-extension/2','id':name,**fields},indent=2,ensure_ascii=False)+'\n'
        note(name,json.loads(text))   # as the scenario file will hold it
        authored.append(name);(into/(name+'.json')).write_text(text)
    for f in plug(folder,'.py'):exec(compile(f.read_text(),str(f),'exec'),{'__name__':'tools.packs.'+f.stem,'pack':create,'fact':fact,'rule':rule,'method':method})
def unauthored(into,authored):return sorted(f.name for f in into.iterdir() if f.name not in {n+'.json' for n in authored})   # what stands in scenarios/ that nobody authored in this run
KINDS=load_kinds(ROOT/'kinds')
HELD=held()   # the registry when the kinds were loaded: before any pack file, extension of a version, or sequence ran. tools/run_all.py compares the registry with it before it records anything, before the sequences run and after them
added_packs(ROOT/'tools'/'packs',P,AUTHORED)
if unauthored(P,AUTHORED):raise ValueError(f'REFUSED scenarios/: not authored in this run (made by hand, or left by a pack file that is gone): {unauthored(P,AUTHORED)}')
if __name__=='__main__':print('Generated',len(list(P.glob('*.json'))),'authored data pack fixtures')
