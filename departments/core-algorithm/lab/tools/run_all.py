"""Produce all recorded stage results from one UNCHANGED kernel + versioned extension data."""
from __future__ import annotations
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest
from extensions.reflection import Learner   # learning lives in the extension since 0.4.0-shrink (move-out M1)
import extensions.constructor   # registers compile_candidate and emit_artifact (0.7.0-handlers, move-outs M2 + M3)
from extensions.asks import answer,open_asks   # registers ask (0.8.0-ask); answer is the stamp
from kernel.core import ACTIONS
if __name__=='__main__':   # the build (add-on points, 0.10.0): the record and the verdict of an earlier build go first, so a build that stops, at the import below (a kind file or a pack file that is refused) or later, leaves neither behind
    for old in (ROOT/'results'/'actual_run_records.json',ROOT/'qa'/'independent_verification.json'):
        if old.exists():old.unlink()
from tools.make_packs import P,KINDS,PACK,plug,HELD,rebound   # KINDS, PACK, plug, HELD and rebound belong to the add-on points (0.10.0)
import re,ast

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
 ('28_website','A chain of four methods','A website: plan, write, build, check. The methods are authored out of order; the plan comes out in dependency order.',['70_site_goal','71_site_theory','72_site_methods'],False,'Ordering'),
 ('29_ask','A human ask','The approval is unknown and a reviewed method may ask for it: the run asks once, waits, and ships nothing.',['00_goal','01_domain','02_methods','04_admission','80_ask_method'],True,'Asks'),
 ('30_stop','A step that cannot run',"The builder's last step names a constructor that no pack declares: three steps run, the fourth stops, and the run says where and why instead of ending in an error.",['30_build_goal','31_build_theory','82_components_without_constructor'],True,'Stops'),
]
# ---- Add-on point (0.10.0): cases a later version adds live in cases/<id>.json, one file per case, named after its id:
# {id, title, description, packs, execute, area, expected}. This file, the tests' table of expected statuses and the verifier read them there.
def more(folder,taken=tuple(c[0] for c in CASES)):   # when this line runs CASES holds the built-in cases only: their ids are taken
    """The cases of `folder` in file order. A file that is no case stops the build with its name: other keys, a value of another type, a file not named after its id,
    an id that is taken (a built-in case), a pack that is no plain name or no scenario file."""
    out=[]
    for f in plug(folder,'.json'):
        c=json.loads(f.read_text())
        if (type(c) is not dict or set(c)!={'id','title','description','packs','execute','area','expected'} or c['id']!=f.stem or c['id'] in taken or type(c['execute']) is not bool
                or any(type(c[k]) is not str or not c[k] for k in ('title','description','area','expected')) or type(c['packs']) is not list
                or any(type(n) is not str or not re.fullmatch(PACK,n) or not (P/(n+'.json')).is_file() for n in c['packs'])):
            raise ValueError(f'REFUSED cases/{f.name}: not a case file (seven keys, the file named after an id that is not taken, packs that are scenario files)')
        out.append(c)
    return out
def spec(c):return (c['id'],c['title'],c['description'],c['packs'],c['execute'],c['area'])   # an added case in the shape of the built-in ones above
MORE=more(ROOT/'cases')
CASES+=[spec(c) for c in MORE]
ASK=['00_goal','01_domain','02_methods','04_admission','80_ask_method']

def ask_events():
    """One ask on three identical States, then what follows. On the first: a second look, an unrelated event, the answer yes.
    On the second: the answer no, and a look after it. On the third: the original item comes back in stock while the question is out.
    A fourth State (pack 81, no ask in it) records a plan made again: the quote is withdrawn and re-made, and the two steps whose rows come back are skipped."""
    def start():
        s=State.from_packs([pack(n) for n in ASK]);k=Kernel(s);first=k.run_standing(execute=True);return s,k,first
    snap=lambda s:{'budget':dict(s.budget),'providers':dict(s.providers),'open_asks':open_asks(s)}
    s,k,first=start();after_first=snap(s)
    again=k.run_standing(execute=True);after_again=snap(s)
    unrelated=k.on_event({'predicate':'substitute_stock','truth':'TRUE','version':'2','verified':True,'source':'fixture/stock-recount'},execute=True);after_unrelated=snap(s)
    yes=answer(k,first['runs'][0]['model_receipts'][0],'TRUE','customer',execute=True);after_yes=snap(s)
    s2,k2,first_no=start();after_first_no=snap(s2)
    no=answer(k2,first_no['runs'][0]['model_receipts'][0],'FALSE','customer',execute=True);after_no=snap(s2)
    no_again=k2.run_standing(execute=True);after_no_again=snap(s2)
    s3,k3,first_other=start();after_first_other=snap(s3)
    other=k3.on_event({'predicate':'original_stock','truth':'TRUE','version':'2','verified':True,'source':'fixture/stock-recount'},execute=True);after_other=snap(s3)
    s4=State.from_packs([pack('81_made_again')]);k4=Kernel(s4);k4.run_standing(execute=True)
    k4.on_event({'predicate':'quote_ready','truth':'FALSE','version':'2','verified':True,'source':'fixture/quote-withdrawn'})
    made_again=k4.run_standing(execute=True)
    return {'first':first,'after_first':after_first,'again':again,'after_again':after_again,'unrelated':unrelated,'after_unrelated':after_unrelated,
            'answered_yes':yes,'after_yes':after_yes,'first_no':first_no,'after_first_no':after_first_no,'answered_no':no,'after_no':after_no,
            'no_again':no_again,'after_no_again':after_no_again,'first_other':first_other,'after_first_other':after_first_other,'other_route':other,'after_other':after_other,'made_again':made_again}

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

# ---- Add-on points (0.10.0): what a scene file states of its sequence, and how the looks and runs of a sequence are counted. The verifier holds the same two functions, word for word.
def scene_says(src):
    """What a scene file states of the sequence it records: (looks, runs), or None when it does not state both. Two lines at the top level of the file, each once, each a
    whole number written as a number: LOOKS = 3 and RUNS = 4. They are read from the text of the file, which is not run for it. The build stops when scene(lab) records
    other numbers than its file states; the verifier compares the record with the same two lines, so the number of looks and of runs in a recorded sequence is held to
    the scene file, which stands outside the record (and is listed in added.json by sha256)."""
    try:tree=ast.parse(src)
    except (SyntaxError,ValueError,RecursionError,MemoryError):return None
    said={}
    for node in tree.body:
        for target in (node.targets if isinstance(node,ast.Assign) else []):
            if isinstance(target,ast.Name) and target.id in ('LOOKS','RUNS'):
                whole=len(node.targets)==1 and target.id not in said and isinstance(node.value,ast.Constant) and type(node.value.value) is int and node.value.value>=0
                said[target.id]=node.value.value if whole else None
    return (said['LOOKS'],said['RUNS']) if set(said)=={'LOOKS','RUNS'} and None not in said.values() else None

def looks_and_runs(v,found=None,item=False):
    """The looks and the runs of a recorded sequence: {'looks': how many, 'runs': [every run, in the order it stands], 'odd': how many things look like a run and are none}.
    A look is a dict that holds a list under `runs` (what the kernel returns for one look at its goals, for one event, for one answer). What looks like a run: every item
    of such a list, and every dict that carries a `trace`, wherever it sits (under any key, in a list of lists, inside another run or inside a row of its trace). It is a
    run when it is a dict that carries both `trace` and `trace_root_sha256`; anything else that looks like one is counted under `odd`."""
    found={'looks':0,'runs':[],'odd':0} if found is None else found
    if type(v) is dict:
        if 'trace' in v and 'trace_root_sha256' in v:found['runs'].append(v)
        elif 'trace' in v or item:found['odd']+=1
        if type(v.get('runs')) is list:found['looks']+=1
        for key,x in v.items():
            if key=='runs' and type(x) is list:
                for y in x:looks_and_runs(y,found,True)
            else:looks_and_runs(x,found)
    else:
        if item:found['odd']+=1   # an item of a `runs` list that is no dict
        if type(v) is list:
            for x in v:looks_and_runs(x,found)
    return found

def scenes(folder=None):
    """Add-on point (0.10.0): recorded sequences a later version adds. tools/scenes/<name>.py defines scene(lab) -> a dict of runs and snapshots, kept in the record
    under scenes.<name> as plain JSON data and sealed there by its sha256 (lab holds State, Kernel, pack, answer, open_asks, Learner, digest). Every pack a scene loads
    must be a scenario file, so that the verifier can check its runs. The file states, at its top level, how many looks and runs its sequence records (LOOKS = n and
    RUNS = n; scene_says and looks_and_runs above). The build stops at a scene file that does not state them, that has no scene(lab), that returns what is no JSON
    object or an empty one, or whose sequence holds other numbers of looks and runs than the file states or something that looks like a run and is none.
    It also looks, when the scene returns, at every State a Kernel was made for while the scene ran, and stops when one of them holds a kind by another handler or hook
    than the registered one, or a kind that is not registered. That catches the mistake it is there for: a kind handed to one State's registry instead of a kind file.
    It is a look, not a fence: a scene is reviewed code that runs with the lab's rights, and a scene written to get past the look (a Kernel pointed at another State
    after it was made, a registry kept in another kind of dict, a handler put back before the scene returns) is recorded (ruling R31; a unit test of the points pins it).
    Nor does the build look for a scene that writes a file or changes a class of the kernel while it runs: it is recorded too (a unit test of the points pins it)."""
    lab={'State':State,'Kernel':Kernel,'pack':pack,'answer':answer,'open_asks':open_asks,'Learner':Learner,'digest':digest};out={}
    for f in plug(folder or ROOT/'tools'/'scenes','.py'):
        text=f.read_text();said=scene_says(text)
        if said is None:raise ValueError(f'REFUSED tools/scenes/{f.name}: it does not state how many looks and runs it records (two lines at the top of the file: LOOKS = <number> and RUNS = <number>)')
        ns={'__name__':'tools.scenes.'+f.stem};exec(compile(text,str(f),'exec'),ns)
        if not callable(ns.get('scene')):raise ValueError(f'REFUSED tools/scenes/{f.name}: it defines no scene(lab)')
        seen=[];init=Kernel.__init__
        def noting(self,*given,**named):   # only notes the State: the Kernel is made as the kernel makes it
            seen.append(given[0] if given else named.get('state'));init(self,*given,**named)
        Kernel.__init__=noting
        try:made=ns['scene'](dict(lab))
        finally:Kernel.__init__=init
        if type(made) is not dict or not made:raise ValueError(f'REFUSED tools/scenes/{f.name}: scene(lab) returns a dict, and not an empty one')
        registries=[state.actions for state in seen if type(getattr(state,'actions',None)) is dict]
        own=sorted({str(kind) for registry in registries for kind,hooks in registry.items() if kind not in HELD or type(hooks) is not dict or set(hooks)!=set(HELD[kind]) or any(hooks[h] is not HELD[kind][h] for h in hooks)})
        if own:raise ValueError(f'REFUSED tools/scenes/{f.name}: a State of this sequence holds the action kind(s) {own} with another handler or hook than the registered one, or a kind that is not registered; an action kind arrives as a kind file, kinds/<kind>.py')
        kept=json.loads(json.dumps(made,ensure_ascii=False,allow_nan=False))   # as it stands in the record: what is sealed and checked is what was made
        got=looks_and_runs(kept)
        if got['odd'] or (got['looks'],len(got['runs']))!=said:
            raise ValueError(f"REFUSED tools/scenes/{f.name}: it says LOOKS = {said[0]} and RUNS = {said[1]}; scene(lab) recorded {got['looks']} looks and {len(got['runs'])} runs, and {got['odd']} of what looks like a run in it is no whole run")
        out[f.stem]=kept
    return out

def undeclared():return sorted(set(ACTIONS)-{'simulate_fact','compile_candidate','emit_artifact','ask'}-set(KINDS))   # action kinds registered by anything but a file in kinds/

def registry_held():
    """Stop the build when the registry of action kinds is not the one that stood when the kinds were loaded: a kind registered by anything but a file in kinds/, or a
    kind whose handler or hook is no longer the same function (an extension, a pack file or a sequence that re-binds one and leaves it so). No record can say which
    function ran, so the build looks, three times: before anything is recorded; when the cases, the event record and the ask record are made and before the sequences
    run; and once more after the sequences. A look at those three moments, for mistakes; not a fence (ruling R31)."""
    if undeclared():raise ValueError(f'REFUSED: action kinds registered outside kinds/: {undeclared()}')
    if rebound(HELD):raise ValueError(f'REFUSED: the handler or a hook of the action kind(s) {rebound(HELD)} is no longer the function that stood when the kinds were loaded (an extension, a pack file or a sequence changed the registry)')

def record(scene_folder=None):
    """The record as the lab makes it now, in memory: nothing is written. build() writes it; the unit tests compare the record on disk with it
    (and make one with the scene files of another folder)."""
    registry_held()   # the first of three looks at the registry: before anything is recorded, so a handler re-bound by a pack file or an extension is refused in words, before the table of handlers below is made of it
    handlers={kind:{'module':fn.__module__,'file':str(Path(sys.modules[fn.__module__].__file__).resolve().relative_to(ROOT)),
                     'sha256':hashlib.sha256(Path(sys.modules[fn.__module__].__file__).read_bytes()).hexdigest()} for kind,fn in sorted((k,h['run']) for k,h in ACTIONS.items())}
    result={'release':'sutra-kernel-extensions/0.14.0-pagebuilder','action_handlers':handlers,
            'kernel_sha256':hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest(),
            'baseline_v0_1_sha256':hashlib.sha256((ROOT/'release'/'baseline_v0_1_core.py').read_bytes()).hexdigest(),
            'scope':'finite synthetic deterministic local simulation; NOT historical Core, current J2, or external outcomes',
            'cases':[scenario(x) for x in CASES],
            'events':extra_events(),'ask_events':ask_events()}
    registry_held()   # the second look: before the sequences run (what the cases and the two records ran is held); and once more after them: a sequence may not leave the registry changed either
    sc=scenes(scene_folder)
    if sc:result['scenes']=sc
    book=json.loads((ROOT/'added.json').read_text())   # what the applier laid in, file by file
    result['added']={'files':{rel:hashlib.sha256((ROOT/rel).read_bytes()).hexdigest() for entry in [book['points']]+book['applied'] for rel in entry['files']},
                     'scenes':{name:digest(made) for name,made in sc.items()},   # every added file by sha256, and the seal of every recorded sequence
                     'scenarios':{f.stem:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(P.glob('*.json'))}}   # every scenario file this build authored, by sha256
    registry_held()
    return result

def build(target=None,verdict=None):
    """Write the record. The record and the verdict of an earlier build are removed first, so a build that fails (a scene that raises, say) leaves neither behind."""
    target=target or ROOT/'results'/'actual_run_records.json';verdict=verdict or ROOT/'qa'/'independent_verification.json'
    for old in (target,verdict):
        if old.exists():old.unlink()
    result=record()
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('WROTE',len(result['cases']),'runs to',target)
    for case in result['cases']:
        status=case['outcome']['status'] if case['outcome'] else case['run']['status']
        actions=' '.join(case['outcome']['actions']) if case['outcome'] else '-'
        print(f"{case['id']:<24} {status:<34} {actions[:85]}")
    return result

if __name__=='__main__':build()
