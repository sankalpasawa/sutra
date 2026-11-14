"""0.13.0-time: time is evidence a clock adapter states at a tick (extensions/clock.py). The kernel has no word of it and is the file
the lab had before any version was added as files. One test per claim of the version's passage (C1 to C13), one for the stated limits,
one that makes the recorded sequence again, one of random walks beside the independent check's own books (which must make every run,
every pack and every snapshot the kernel and the adapter make, whole), one that shows each independent check refusing forgeries of
its own, one that changes single fields of the record wherever they sit, and one that runs the verifier. The base has no clock: there
a row that rests on a window is never believed, nothing closes, no grant ends and no budget comes back.
Ten more tests (test_confirm_...) pin what the confirming review round found, as the code is today: see the note above them.
These tests read the built record (results/actual_run_records.json), so they run after tools/run_all.py and tools/make_extra.py."""
from pathlib import Path
import unittest, sys, json, copy, hashlib, re, random, collections, importlib.util, ast
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest,ACTIONS
from tools.run_all import MORE,KINDS,pack,ASK,answer,open_asks,Learner,undeclared
import extensions.clock as c

Q='orgA/fulfillment|'
ORDER=('00_goal','01_domain','02_methods','04_admission','160_timed_approval')   # the order of case 02 with an approval that counts until day 3 and a due-by on day 5
GATES=('00_goal','01_domain','02_methods','03_approval','04_admission')          # the order of case 04: the approval does not run out
BLOCKED=('QUERY_EVIDENCE',[],0,['METHOD_ABSENT','QUERY_EVIDENCE']);SHIPPED=('LOCAL_MODEL_EFFECTS_RECORDED',['ship-replacement@1'],1,[]);HOLDS=('SUPPORTED_BY_EVIDENCE',[],0,[])
STOCK={'predicate':'substitute_stock','truth':'TRUE','version':'2','verified':True,'source':'recount'};ZERO={'compute':0,'money':0,'attention':0}
WALKS=['allowance','called_late','crowd','due','late_order','loan','loan_late','offer','order','planted','pulls','refusals','same_moment','two_boxes','two_goals','two_scopes','weekly','withdrawn']
def world(*extra,base=ORDER):
    s=State.from_packs([pack(n) for n in base]+list(extra));return s,Kernel(s)
def books(s):return digest({'e':s.evidence,'g':sorted(s.grants),'b':s.budget,'p':s.providers,'l':s.loaded,'j':s.event_journal,'a':s.active_work})
def brief(r):return (r['status'],r['actions'],len(r['model_receipts']),r['stop_reasons'])
def P(name,**fields):return dict({'schema':'sutra-extension/2','id':name},**fields)
def row(p,t,v,**kw):return dict({'predicate':p,'truth':t,'verified':True,'source':'fx','version':v},**kw)
def M(mid,effect,action='simulate_fact',cost=None,req=(),**kw):
    return dict(id=mid,effect=effect,requires=list(req),provider='prov',grant='g',cost=dict(cost if cost is not None else {'compute':1,'money':0,'attention':0}),action=action,approved=True,**kw)
def plain(v):return json.loads(json.dumps(v))
def stood(s,watch):
    """What stands on a State, as the recorded sequence keeps it after every step (tools/scenes/clock.py)."""
    return plain({'moment':c.moment(s),'scope':s.scope,'budget':s.budget,'grants':sorted(s.grants),'loaded':[e['pack'] for e in s.loaded],'reads':{p:s.fact(p)['truth'] for p in watch},
                  'stored':{p:s.evidence.get(s.key(p)) for p in watch},'turned_away':sum(j.get('status')=='DECISION_STANDS' for j in s.event_journal),'books':books(s)})
def verifier():
    """The independent verifier, loaded from its file (it is a script, not a package)."""
    spec=importlib.util.spec_from_file_location('independent_verify_for_the_clock',ROOT/'qa'/'independent_verify.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def check_module():
    """The clock's independent check module, run as the verifier runs it (qa/checks/clock.py: it never loads the lab's code)."""
    ns={};exec(compile((ROOT/'qa'/'checks'/'clock.py').read_text(),'clock checks','exec'),ns);return ns
def record():return json.loads((ROOT/'results'/'actual_run_records.json').read_text())

def random_walks(test,worlds,ops,seed):
    """Random small worlds (timed rows, due rows, boxed grants, allowances, methods and a rule that name windows, two scopes) and random walks over
    them: ticks dry and executed, moments that must be refused, rows by event and by `observe`, rows and decisions written by hand on the clock's
    names, packs (a grant given again, a box, an allowance, a top-up, a timed row, a due row, the clock's own earlier pack, a pack named like the
    clock's), changes of scope, looks without a tick. Beside the kernel and the adapter walk the independent check's own books (qa/checks/clock.py),
    fed the same packs and rows and nothing else: every tick, look and event the books make must equal, whole, what the kernel and the adapter
    make (every run with its trace, hash for hash, the clock's packs, the report, the refusal's words), what stands after every step must be equal
    down to the digest of the books, and the claims must hold. Returns what was exercised."""
    mod=check_module();Books,Refusal=mod['Books'],mod['Refusal'];sha=verifier().sha;rnd=random.Random(seed);count=collections.Counter();n=[0]
    FACTS=[f'f{i}' for i in range(5)];GOALS=['g0','g1','g2'];SCOPES=['orgA/one','orgA/two'];DIMS=['compute','money','attention','pulls']
    WATCH=FACTS+GOALS+['now']+[c.DUE+g for g in GOALS]+[c.window(i) for i in range(13)]
    def a_row(pred):
        n[0]+=1;r=row(pred,rnd.choice(['TRUE','TRUE','TRUE','FALSE']),f'v{n[0]}')
        for chance in (0.6,0.15):   # a row may rest on a window, or on two
            if rnd.random()<chance:r=c.timed(r,rnd.randint(0,12))
        return r
    def a_world():
        methods=[dict(id=f'make-{g}',effect=g,requires=rnd.sample(FACTS,rnd.randint(0,2))+([c.window(rnd.randint(0,12))] if rnd.random()<0.25 else []),provider='p',grant=f'grant-{g}',
                      action='simulate_fact',approved=True,cost={'compute':rnd.randint(0,1),'money':0,'attention':0,'pulls':rnd.randint(0,1)}) for g in GOALS]
        if rnd.random()<0.3:methods.append(dict(id='make-f0',effect='f0',requires=[],provider='p',grant='grant-g0',action='simulate_fact',approved=True,cost={'compute':1,'money':0,'attention':0,'pulls':0}))   # a second step, so a plan may have two
        grants=[x for g in GOALS for x in ([f'grant-{g}'] if rnd.random()<0.9 else [])+[c.box(f'grant-{g}',rnd.randint(0,12)) for _ in range(2) if rnd.random()<0.3]]
        grants+=[c.allowance(dim,rnd.randint(0,3),rnd.randint(1,4)) for dim in ('pulls','compute') if rnd.random()<0.6]
        rules=[{'id':'R-G2@1','head':'g2','branches':[['f0',c.window(rnd.randint(0,12))],['g1']],'approved':True}] if rnd.random()<0.3 else []
        evidence=[a_row(f) for f in FACTS if rnd.random()<0.7]+[c.due(g,rnd.randint(0,12)) for g in GOALS if rnd.random()<0.6]
        return P('w',scope=SCOPES[0],goals=rnd.sample(GOALS,rnd.randint(1,3)),methods=methods,rules=rules,evidence=evidence,providers={'p':rnd.choice([60,60,2])},grants=grants,
                 budget={'compute':rnd.randint(0,6),'money':5,'attention':2,'pulls':rnd.randint(0,3)},preference=rnd.choice([DIMS,DIMS[::-1]]))
    for wi in range(worlds):
        w=a_world();s=State.from_packs([w]);k=Kernel(s);b=Books(sha);b.load(w);stated=[]
        def looked(runs,at,where):   # the runs of a look: none carries a word of time, and at a tick no step runs on a window the clock has closed (between ticks a decision written by hand on a closed window is believed: a stated limit)
            for r in runs:
                test.assertFalse('time' in r or 'late' in r,where);count['run']+=1;count[r['status']]+=1
                for x in r['model_receipts']:
                    test.assertTrue(all(c.closes(q) is None or at is None or c.closes(q)>=at for q in s.methods[x['method']]['requires']),where);count['receipt']+=1
        for step in range(ops):
            where=(seed,wi,step);op=rnd.random();at=c.moment(s);was=books(s)
            if op<0.42:   # a tick, at the same moment or a later one
                new=rnd.randint(0,3) if at is None else at+rnd.choice([0,0,1,1,2,5]);execute=rnd.random()<0.6;had=set(s.grants);want=b.says(new,'')
                test.assertEqual((plain(c.clock_packs(s,new)),books(s)),(plain(want),was),where)   # the packs are what the check's books call for, and building them changes nothing
                out=c.tick(k,new,execute=execute);mine=b.tick(new,execute,'');count['tick']+=1;count['clock pack']+='clock_pack' in out
                test.assertEqual(plain(out),plain(mine),where)   # the whole result: the runs with their traces, the report, the pack
                if 'clock_pack' in out:stated.append(out['clock_pack'])
                test.assertEqual((out['time']['as_of'],c.moment(s),set(s.grants)<=had),(new,new,True),where);count['late']+=len(out['time']['late'])
                last={}
                for end,g in filter(None,map(c.boxed,s.grants)):last[g]=max(end,last.get(g,-1))
                test.assertEqual([g for g,end in last.items() if end<new and g in s.grants],[],where)   # no grant past its last box stands
                test.assertTrue(all(s.evidence.get(s.key(r['predicate'],r['scope']))==r for r in want[0]['evidence'] if r.get('final')),where)   # after a tick the clock's decisions are in force, whatever was planted: the moment's row and every closed window, in every scope that holds rows
                for sc in c.scopes(s):   # in every scope that holds rows, nothing that rests on a window the clock has closed reads TRUE
                    t=copy.copy(s);t.scope=sc
                    for key,r in s.evidence.items():
                        if key.startswith(sc+'|') and any(d['predicate'].startswith('until:') and (c.closes(d['predicate']) is None or c.closes(d['predicate'])<new) for d in r.get('depends_on',[])):
                            test.assertNotEqual(t.fact(key[len(sc)+1:])['truth'],'TRUE',where+(key,))
                looked(out['runs'],new,where)
            elif op<0.50:   # a moment, a label or an execute that must be refused: nothing changes, and the books refuse it in the same words
                wrong,label,execute=rnd.choice([(-1,'',True),(2.0,'',False),(True,'',True),('3','',True),(None,'',False),(10**18,'',True),(at or 0,'x clock@1',True),(at or 0,7,False),(at or 0,'','yes'),(at or 0,'',1)]+([(at-1,'',True)] if at else []))
                with test.assertRaises(ValueError,msg=where) as said:c.tick(k,wrong,execute=execute,label=label)
                with test.assertRaises(Refusal,msg=where) as mine:b.tick(wrong,execute,label)
                test.assertEqual((str(said.exception),books(s)),(str(mine.exception),was),where);count['refused']+=1
            elif op<0.62:   # a row arrives, by event or handed to observe
                r=a_row(rnd.choice(FACTS))
                if rnd.random()<0.7:
                    execute=rnd.random()<0.5;out=k.on_event(r,execute=execute);test.assertEqual(plain(out),plain(b.event(r,execute)),where);looked(out['runs'],None,where)
                else:test.assertEqual(s.observe(r),b.observe(r),where)
                count['row']+=1
            elif op<0.70:   # a row written by hand on the clock's own names, ordinary or a decision, by event
                name=rnd.choice(['now',c.window(rnd.randint(0,12)),c.window(rnd.randint(0,12)),'until:999999999999999999'])
                r=dict(row(name,rnd.choice(['TRUE','FALSE']),rnd.choice(['window','closed','x',3])),source=rnd.choice([c.SOURCE,'mallory']),**({'final':True} if rnd.random()<0.5 else {}),**({'at':rnd.choice([0,1,10**17])} if name=='now' else {}))
                out=k.on_event(r);test.assertEqual(plain(out),plain(b.event(r,False)),where);looked(out['runs'],None,where);count['by hand']+=1;count['decision by hand']+=bool(r.get('final'))
            elif op<0.74:   # a box or an allowance named in an event: it changes neither the grants nor the budget
                r=row(rnd.choice([c.box(f'grant-{rnd.choice(GOALS)}',99),c.allowance('pulls',9,1),f'grant-{rnd.choice(GOALS)}']),'TRUE','1');out=k.on_event(r);test.assertEqual(plain(out),plain(b.event(r,False)),where);looked(out['runs'],None,where)
            elif op<0.86:   # a pack: a grant given again, a box, an allowance, a top-up, a timed row, a due row
                g=f'grant-{rnd.choice(GOALS)}'
                p=P(f'p{wi}-{step}',**rnd.choice([{'grants':[g]},{'grants':[c.box(g,rnd.randint(0,20))]},{'grants':[c.allowance(rnd.choice(['pulls','compute','energy']),rnd.randint(0,3),rnd.randint(1,4))]},
                                                 {'budget':{rnd.choice(DIMS):rnd.randint(0,6)}},{'evidence':[a_row(rnd.choice(FACTS))]},{'evidence':[c.due(rnd.choice(GOALS),rnd.randint(0,20))]}]))
                s.apply(p);b.load(p);count['pack']+=1
            elif op<0.89 and stated:   # the clock's own earlier pack, applied again by hand: no moment goes back
                p=rnd.choice(stated);s.apply(p);b.load(p);count['clock pack again']+=1
            elif op<0.90:   # a pack named like the clock's, written by hand: it is taken for one (a stated limit), and the moment only ever goes forward
                p=P(f'by-hand-{wi}-{step} clock@{(at or 0)+rnd.randint(0,2)}');s.apply(p);b.load(p);count['named like the clock']+=1
            elif op<0.94:   # the State moves to another scope, or stays
                p=P(f'scope{wi}-{step}',scope=rnd.choice(SCOPES));s.apply(p);b.load(p);count['scope']+=1
            else:   # a look without a tick
                execute=rnd.random()<0.5;out=k.run_standing(execute=execute);test.assertEqual(plain(out),plain(b.look(execute)),where);looked(out['runs'],None,where);test.assertNotIn('time',out);count['look']+=1
            test.assertGreaterEqual(-1 if c.moment(s) is None else c.moment(s),-1 if at is None else at,where)   # whatever happened, the moment did not go back; only a pack named as the clock's moves it
            if op>=0.50 and not 0.86<=op<0.90:test.assertEqual(c.moment(s),at,where)
            test.assertEqual(stood(s,WATCH),plain(b.stood(WATCH)),where)   # what stands after the step: the same, down to the digest of the books (every stored row, the grants, the budget, the providers, the packs, the journal)
    return count


class ClockTests(unittest.TestCase):
    def test_c1_a_timed_row_expires_by_resting_on_a_window_and_its_stored_row_is_never_touched(self):
        s,k=world();key=Q+'customer_approved';stored=copy.deepcopy(s.evidence[key])
        self.assertEqual((s.fact('customer_approved')['truth'],brief(k.run_standing(execute=True)['runs'][0]),c.moment(s)),('UNKNOWN',BLOCKED,None))   # no tick yet: the window was never published, so the row is not believed
        for now,truth,reason,status in ((0,'TRUE',None,'PLAN_READY'),(2,'TRUE',None,'PLAN_READY'),(3,'TRUE',None,'PLAN_READY'),(4,'UNKNOWN','dependency invalidated','QUERY_EVIDENCE'),(6,'UNKNOWN','dependency invalidated','QUERY_EVIDENCE')):
            s,k=world();look=c.tick(k,now)['runs'][0];r=s.fact('customer_approved')   # the last moment of a window counts: true on day 3, gone on day 4
            self.assertEqual((r['truth'],r.get('reason'),look['status'],s.evidence[key]),(truth,reason,status,stored),now)
        s,k=world();day2=c.tick(k,2,execute=True);day3=c.tick(k,3,execute=True);day6=c.tick(k,6,execute=True);made=s.fact('replacement_delivered')
        # one State: it ships on day 2; on day 3 the window is the same row at the same version, so the approval and the shipment still read true; on day 6 the approval has run out, and what was shipped on it lapses with it
        self.assertEqual((brief(day2['runs'][0]),brief(day3['runs'][0]),brief(day6['runs'][0]),made['truth'],made['reason'],s.evidence[key]),(SHIPPED,HOLDS,BLOCKED,'UNKNOWN','dependency invalidated',stored))
        two=State.from_packs([P('two',evidence=[c.timed(c.timed(row('p','TRUE','1'),8),3)])]);k2=Kernel(two);reads=[]   # a row may rest on two windows: it expires with the earlier one
        for now in (3,4,9):c.tick(k2,now);reads.append((two.fact('p')['truth'],[two.fact(w)['truth'] for w in c.windows(two)]))
        self.assertEqual((c.windows(two),reads),(['until:3','until:8'],[('TRUE',['TRUE','TRUE']),('UNKNOWN',['FALSE','TRUE']),('UNKNOWN',['FALSE','FALSE'])]))
        s,k=world();t=c.tick(k,6,execute=True,label='160_');recorded=pack('160_clock@6')   # case 67 is this tick: its last pack is the pack the clock states on day 6 on the packs before it, name and all, and its run is the same run
        case=State.from_packs([pack(n) for n in ORDER]+[recorded]);said=c.report(case);run=Kernel(case).run_standing(execute=True)['runs'][0]
        self.assertEqual((t['clock_pack'],recorded['id'],t['runs'][0]['trace_root_sha256'],t['runs'][0]['provenance'],brief(run),said,t['time']),
                         (recorded,'160_clock@6',run['trace_root_sha256'],run['provenance'],BLOCKED,{'as_of':6,'late':['order_complete']},{'as_of':6,'late':['order_complete']}))
        # Case 67 alone cannot tell an approval that ran out from one that was never given (the review's finding): its status and its trace are the same without its clock pack, and without the approval.
        # What tells is its twin, case 67a: the same packs with the clock pack of day 2, where the order ships. A clock that published no window fails 67a; a clock that never closed one fails 67.
        cases={m['id']:m for m in MORE};late,twin=cases['67_late_order'],cases['67a_order_in_time'];run_of=lambda names:Kernel(State.from_packs([pack(n) for n in names])).run_standing(execute=True)['runs'][0]
        self.assertEqual((late['packs'][:-1],late['packs'][-1],twin['packs'][-1],late['expected'],twin['expected']),(twin['packs'][:-1],'160_clock@6','160_clock@2','QUERY_EVIDENCE','LOCAL_MODEL_EFFECTS_RECORDED'))
        self.assertEqual((brief(run_of(late['packs'])),brief(run_of(twin['packs'])),brief(run_of(late['packs'][:-1])),brief(run_of(late['packs'][:-2]))),(BLOCKED,SHIPPED,BLOCKED,BLOCKED))
        self.assertEqual(len({run_of(n)['trace_root_sha256'] for n in (late['packs'],late['packs'][:-1],late['packs'][:-2])}),1)
        no_window=dict(pack('160_clock@2'),evidence=pack('160_clock@2')['evidence'][:1]);never_closed=dict(pack('160_clock@6'),evidence=[dict(r,truth='TRUE',version='window',final=False) if r['predicate']=='until:3' else r for r in pack('160_clock@6')['evidence']])
        under=lambda clock_pack:brief(Kernel(State.from_packs([pack(n) for n in ORDER]+[clock_pack])).run_standing(execute=True)['runs'][0])
        self.assertEqual((under(no_window),under(never_closed)),(BLOCKED,SHIPPED))   # the two broken clocks: the one that publishes no window blocks the twin, the one that never closes a window ships the late order; each fails one case of the pair
    def test_c2_what_arrives_after_its_window_closed_is_not_believed(self):
        late=c.timed(row('customer_approved','TRUE','approval-v9'),3)   # an approval that ended on day 3, arriving on day 6
        s,k=world();c.tick(k,6);ev=k.on_event(late,execute=True)   # through the kernel's own event door, which runs the affected goal at once
        self.assertEqual((ev['status'],ev['affected'],brief(ev['runs'][0]),s.fact('customer_approved')['truth'],s.evidence[Q+'customer_approved']['version']),('RECONCILED',['order_complete'],BLOCKED,'UNKNOWN','approval-v9'))
        s,k=world();c.tick(k,6);s.apply(P('late-pack',evidence=[late]))   # in a pack, then a direct look
        self.assertEqual((brief(k.resolve('order_complete',execute=True)),s.fact('customer_approved')['truth']),(BLOCKED,'UNKNOWN'))
        s,k=world();c.tick(k,2);k.on_event(row('customer_approved','FALSE','approval-withdrawn'));c.tick(k,6)   # a window that no other row names any more is still the clock's row, and it closes at its time
        k.on_event(late);self.assertEqual((s.fact('until:3')['truth'],s.fact('customer_approved')['truth']),('FALSE','UNKNOWN'))   # so a row that arrives later resting on it is not believed
        s,k=world();c.tick(k,6);s.observe(late);self.assertEqual(s.fact('customer_approved')['truth'],'UNKNOWN')   # handed to observe
        s.apply(pack('160_timed_approval'));self.assertEqual((s.fact('customer_approved')['truth'],brief(k.run_standing(execute=True)['runs'][0])),('UNKNOWN',BLOCKED))   # and the original pack applied again after its time
        k.on_event(c.timed(row('customer_approved','TRUE','approval-v10'),9))   # a fresh approval that counts until day 9: its window is new, so it is believed from the next tick and not before (a stated limit)
        self.assertEqual((s.fact('customer_approved')['truth'],c.windows(s)),('UNKNOWN',['until:3','until:5','until:9']))
        t=c.tick(k,6,execute=True)   # the same moment and something new: the clock states the new window in a second pack for day 6, and the order ships, late
        self.assertEqual((s.fact('customer_approved')['truth'],t['clock_pack']['id'],brief(t['runs'][0]),t['time']),('TRUE','clock@6.1',SHIPPED,{'as_of':6,'late':['order_complete']}))
    def test_c3_the_clock_states_only_its_own_rows_and_its_packs_follow_from_the_state_the_moment_and_the_label(self):
        s,k=world();mine=lambda key:key.split('|',1)[1]=='now' or c.closes(key.split('|',1)[1]) is not None;others=lambda:digest({a:b for a,b in s.evidence.items() if not mine(a)})
        before=(books(s),others());self.assertEqual((c.clock_pack(s,4),c.clock_packs(s,4),books(s)),(c.clock_pack(s,4),[c.clock_pack(s,4)],before[0]))   # building the pack applies nothing, the same State and moment give the same pack, and while the rows fit there is one
        packs=[c.tick(k,now)['clock_pack'] for now in (2,4,6)];self.assertEqual(others(),before[1])   # three ticks later every row of another source is byte-identical
        packs+=[c.tick(Kernel(State.from_packs([pack('162_loan')])),16)['clock_pack'],c.tick(Kernel(State.from_packs([pack('163_bureau_pulls')])),0)['clock_pack']]
        files=sorted(f.stem for f in (ROOT/'scenarios').glob('16[0-9]_*.json') if c.stated(f.stem) is not None);packs+=[pack(n) for n in files];self.assertEqual(len(files),42)   # and so is every clock pack the record holds as a scenario file
        for p in packs:
            self.assertTrue(set(p)<={'schema','id','evidence','revoke_grants','budget'} and 'grants' not in p and 0<len(p['evidence'])<=c.ROWS,p['id'])   # it takes grants away and never gives one
            self.assertTrue(all(r['source']==c.SOURCE and r['verified'] is True and ((r['predicate']=='now' and r['at']==r['version']==c.stated(p['id']) and r['final'] is True) or c.closes(r['predicate']) is not None) for r in p['evidence']),p['id'])   # its name says its moment
        line=lambda **f:dict(f,verified=True,source=c.SOURCE,scope='orgA/fulfillment')
        self.assertEqual(packs[1],{'schema':'sutra-extension/2','id':'clock@4','evidence':[line(predicate='now',truth='TRUE',final=True,version=4,at=4),line(predicate='until:3',truth='FALSE',final=True,version='closed'),line(predicate='until:5',truth='TRUE',version='window')]})
        self.assertEqual((packs[3]['revoke_grants'],packs[4]['budget'],[r['predicate'] for r in packs[3]['evidence']]),(['action:disburse-loan@1'],{'pulls':2},['now','until:7','until:30']))
        named=c.clock_pack(s,7,'166_');bare=c.clock_pack(s,7)   # the label is the caller's: it stands in front of the clock's own name and changes nothing else
        self.assertEqual((named['id'],bare['id'],{k:v for k,v in named.items() if k!='id'}),('166_clock@7','clock@7',{k:v for k,v in bare.items() if k!='id'}))
        for bad in (5,None,b'x','clock@','day clock@1 '):
            with self.assertRaises(ValueError,msg=repr(bad)):c.clock_pack(s,7,bad)
            with self.assertRaises(ValueError,msg=repr(bad)):c.clock_packs(s,7,bad)
        # the pack file tells the walks a second time (tools/packs/clock.py, `chain`) and the scene must state those very packs: a pack that is not its file stops the scene, so the build
        ns={};exec(compile((ROOT/'tools'/'scenes'/'clock.py').read_text(),'clock scene','exec'),ns);other=lambda n:dict(pack(n),evidence=pack(n)['evidence'][:1]) if n=='160_clock@4' else pack(n)
        with self.assertRaisesRegex(RuntimeError,'the tick stated 160_clock@4, which is not the pack its scenario file holds'):ns['scene']({'State':State,'Kernel':Kernel,'pack':other,'digest':digest})
    def test_c4_a_closed_window_is_a_decision_and_no_ordinary_row_pack_or_method_reopens_it(self):
        s,k=world();early=c.tick(k,2)['clock_pack'];c.tick(k,4);n=len(s.event_journal);turned={'status':'DECISION_STANDS','scope':'orgA/fulfillment','predicate':'until:3'}
        r=s.fact('until:3');self.assertEqual((r['truth'],r['final'],r['source']),('FALSE',True,c.SOURCE))
        ev=k.on_event({'predicate':'until:3','truth':'TRUE','verified':True,'source':'mallory','version':'window'},execute=True)   # an ordinary row that says the window is open again
        self.assertEqual((ev,s.event_journal[n:],s.fact('customer_approved')['truth']),({'status':'DECISION_STANDS','affected':[],'runs':[]},[turned],'UNKNOWN'))
        s.apply(early)   # the clock's own pack of day 2, applied again by hand: its open window is turned away too, and the moment does not go back
        self.assertEqual(([j for j in s.event_journal[n:] if j.get('status')=='DECISION_STANDS'],s.fact('until:3')['truth'],s.fact('customer_approved')['truth'],c.moment(s)),([turned]*2,'FALSE','UNKNOWN',4))
        with self.assertRaises(ValueError):c.tick(k,3)
        again=c.tick(k,4);self.assertEqual((again['time'],again['clock_pack']['id'],s.fact('customer_approved')['truth'],s.fact('now')['at']),({'as_of':4,'late':[]},'clock@4.1','UNKNOWN',4))   # and the next tick states the clock's rows again
        w,kw=world(P('reopen',methods=[M('reopen@1','until:3',cost=ZERO),M('set-now@1','now',cost=ZERO)],providers={'prov':2},grants=['g']));c.tick(kw,4)   # nor a method whose effect is the window, or the moment: refused as a goal, stopped as a step
        self.assertEqual((brief(kw.resolve('until:3',execute=True)),kw._act({'actions':['reopen@1']}),kw.events[-1]['data']['reason'],w.fact('until:3')['truth']),
                         (('REFUSED',[],0,['REFUSED']),[],'Handler refused: A decision stands on this effect','FALSE'))
        self.assertEqual((kw._act({'actions':['set-now@1']}),kw.events[-1]['operation'],w.fact('now')['at'],w.fact('now')['source']),([],'STEP_ALREADY_TRUE',4,c.SOURCE))   # the moment's row reads true already, so that step makes nothing
        o=State.from_packs([pack('167_offer')]);ko=Kernel(o);before=[brief(r) for r in ko.run_standing()['runs']];c.tick(ko,4);after=[brief(r) for r in ko.run_standing(execute=True)['runs']]   # the recorded pack 167 holds such a step (reopen-offer@1, whose effect is the rule's window): past the window no plan runs it
        self.assertEqual((before,after,o.fact('until:3')['source'],[m['id'] for m in o.methods.values() if m['effect']=='until:3']),
                         ([('QUERY_EVIDENCE',[],0,['QUERY_EVIDENCE']),('PLAN_READY',['reopen-offer@1'],0,[])],[('LOCAL_MODEL_EFFECTS_RECORDED',['ship-offer@1'],1,[]),('REFUSED',[],0,['REFUSED'])],c.SOURCE,['reopen-offer@1']))
    def test_c5_a_refused_tick_changes_nothing_and_no_evidence_row_moves_the_moment_or_stops_the_clock(self):
        s,k=world();c.tick(k,4);before=books(s)
        for bad in (1,3,-1,2.0,2.5,True,'5',None,[6],10**18):   # an earlier moment, and what is not a whole number
            with self.assertRaises(ValueError,msg=repr(bad)):c.tick(k,bad)
            with self.assertRaises(ValueError,msg=repr(bad)):c.clock_pack(s,bad)
        for bad in (1,'yes',None):   # an `execute` that is not true or false is refused before the pack is applied, not after
            with self.assertRaises(ValueError,msg=repr(bad)):c.tick(k,5,execute=bad)
        for bad in (5,None,'day clock@1'):
            with self.assertRaises(ValueError,msg=repr(bad)):c.tick(k,5,label=bad)
        self.assertEqual((books(s),c.moment(s)),(before,4))
        for at,source in ((0,c.SOURCE),(10**17,c.SOURCE),(9,'mallory')):   # the moment is read from the record of packs. An ordinary `now` row written by hand, in the clock's name or another, is turned away: the clock's row is a decision
            ev=k.on_event({'predicate':'now','truth':'TRUE','verified':True,'source':source,'version':at,'at':at})
            self.assertEqual((ev['status'],c.moment(s),c.report(s)['as_of'],s.fact('now')['at']),('DECISION_STANDS',4,4,4))
            ev=k.on_event({'predicate':'now','truth':'TRUE','verified':True,'final':True,'source':source,'version':at,'at':at})   # a decision written by hand replaces the row (only a decision replaces a decision) and still moves the moment neither back nor forward
            self.assertEqual((ev['status'],ev['runs'],c.moment(s),c.report(s)['as_of'],s.fact('now')['at']),('RECONCILED',[],4,4,at))
            with self.assertRaises(ValueError):c.tick(k,3)
            t=c.tick(k,4);self.assertEqual((t['time'],s.fact('now')['at'],s.fact('now')['source']),({'as_of':4,'late':[]},4,c.SOURCE))   # and the next tick states the clock's own decision over it
        self.assertEqual([e['pack'] for e in s.loaded[-4:]],['clock@4','clock@4.1','clock@4.2','clock@4.3'])
        k.on_event({'predicate':'now','truth':'TRUE','verified':True,'final':True,'source':c.SOURCE,'version':5,'at':5,'scope':s.scope});ahead=c.tick(k,5)   # a `now` row that says the next moment before the clock does, word for word: the tick still states its pack, so the record carries the moment
        self.assertEqual((ahead['clock_pack']['id'],ahead['time']['as_of'],c.moment(s),s.loaded[-1]['pack']),('clock@5',5,5,'clock@5'))
        # No decision written by hand on one of the clock's names stops the clock (the first refuter's finding on the first build, where every later tick was refused).
        s,k=world(P('boxed',grants=['x',c.box('x',3)]));c.tick(k,2);plant=lambda **f:k.on_event(dict({'verified':True,'final':True,'source':'mallory','version':'x'},**f))
        plant(predicate='now',truth='TRUE',at=2);plant(predicate='now',truth='FALSE',at=2)                 # on the moment's own row, twice over
        plant(predicate='until:999999999999999999',truth='FALSE');plant(predicate='until:5',truth='FALSE')   # on a window no moment can pass, and on the window the due-by rests on
        n=len(s.event_journal);day3=c.tick(k,3,execute=True);stands=lambda:[j['predicate'] for j in s.event_journal[n:] if j.get('status')=='DECISION_STANDS']
        self.assertEqual((day3['clock_pack']['id'],brief(day3['runs'][0]),day3['time'],s.fact('now')['source'],s.fact('now')['at'],stands()),
                         ('clock@3',SHIPPED,{'as_of':3,'late':['order_complete']},c.SOURCE,3,['until:5','until:999999999999999999']))   # the tick goes through: the clock's decision replaces the one on `now`; its ordinary rows for the two windows are turned away, on the record; what rests on a window closed by hand reads no more open than the clock would say (the due-by reads as passed: fail closed)
        self.assertEqual(('clock_pack' in c.tick(k,3),stands()),(False,['until:5','until:999999999999999999']))   # a second look at that moment states nothing: a row the kernel would turn away is nothing new
        day4=c.tick(k,4,execute=True);self.assertEqual((day4['clock_pack']['revoke_grants'],'x' in s.grants,s.fact('customer_approved')['truth'],brief(day4['runs'][0])),(['x'],False,'UNKNOWN',BLOCKED))   # time went on: the boxed grant ended and the approval ran out on their days
        far=c.tick(k,10**6);self.assertEqual((far['time']['as_of'],s.fact('until:5')['source'],s.fact('until:999999999999999999')['source'],c.moment(s)),(10**6,c.SOURCE,'mallory',10**6))   # past a window the clock's own decision takes the place of the one written by hand
        # Nor does a row that names a great many windows (the review's finding on the second build: one event row of 7,689 window names made the clock's one pack larger than the kernel's door takes,
        # every later tick was refused, the moment stood at day 2 and the approval that ended on day 3 was believed from then on). The clock's rows are cut into packs of at most ROWS rows, what closes first.
        s,k=world();c.tick(k,2,execute=True);ev=k.on_event(row('note','TRUE','1',depends_on=[{'predicate':f'until:{100+i}','version':'window'} for i in range(7689)]))
        t=c.tick(k,4,execute=True);more=t['more_clock_packs'];cut=[t['clock_pack']]+more
        self.assertEqual((ev['status'],brief(t['runs'][0]),c.moment(s),s.fact('customer_approved')['truth'],s.fact('replacement_delivered')['truth'],s.fact('note')['truth'],len(cut),sum(len(p['evidence']) for p in cut)),
                         ('RECONCILED',BLOCKED,4,'UNKNOWN','UNKNOWN','TRUE',121,1+2+7689))   # the tick goes through in 121 packs: time moved, the approval ran out, and the note is believed (all its windows are published)
        self.assertEqual(([p['id'] for p in cut[:3]],cut[-1]['id'],{len(p['evidence']) for p in cut[:-1]},len(cut[-1]['evidence']),[r['predicate'] for r in cut[0]['evidence'][:3]],[e['pack'] for e in s.loaded[-2:]]),
                         (['clock@4','clock@4.1','clock@4.2'],'clock@4.120',{c.ROWS},(1+2+7689)%c.ROWS,['until:3','now','until:5'],['clock@4.119','clock@4.120']))   # what closes is stated first; every pack is on the record of packs, so in every later run's provenance
        nxt=c.clock_packs(s,5);self.assertEqual(('clock_pack' in c.tick(k,4),nxt[0]['id'],len(nxt)),(False,'clock@5',121))   # a second look states nothing; the next moment states them all again
        small=State.from_packs([P('small',evidence=[c.timed(row(f'f{i}','TRUE','1'),i) for i in range(c.ROWS-1)])]);self.assertEqual((len(c.clock_packs(small,0)),len(c.clock_packs(small,0)[0]['evidence'])),(1,c.ROWS))   # exactly ROWS rows are one pack, in the usual order: the moment first
        small.observe(c.timed(row('one_more','TRUE','1'),99));two=c.clock_packs(small,3);self.assertEqual(([len(p['evidence']) for p in two],[r['predicate'] for r in two[0]['evidence'][:4]],[r['predicate'] for r in two[1]['evidence']],[p['id'] for p in two]),
                                                                                                    ([c.ROWS,1],['until:0','until:1','until:2','now'],['until:99'],['clock@3','clock@3.1']))   # one row more is two packs, what closes first
        gate=State.from_packs([P('gate',grants=[x for i in range(4) for x in (f'g{i}',c.box(f'g{i}',1))],evidence=[c.timed(row(f'f{i}','TRUE','1'),i+5) for i in range(c.ROWS)])]);both=c.clock_packs(gate,3)
        self.assertEqual((both[0]['revoke_grants'],'revoke_grants' in both[1],len(both)),([f'g{i}' for i in range(4)],False,2))   # the revoke line goes with the first pack
    def test_c6_a_time_boxed_grant_ends_at_a_tick_and_what_was_done_under_it_stands(self):
        G='action:disburse-loan@1';B15,B20,B10=c.box(G,15),c.box(G,20),c.box(G,10);need=('AUTHORITY_REQUIRED',[],0,['AUTHORITY_REQUIRED']);ran=('LOCAL_MODEL_EFFECTS_RECORDED',['disburse-loan@1'],1,[]);ready=('PLAN_READY',['disburse-loan@1'],0,[])
        self.assertEqual((B15,c.boxed(B15),c.boxed(G),c.boxed('box:015:'+G),c.boxed('box:15:'),c.boxed('box:5:'+B15)),('box:15:'+G,(15,G),None,None,None,None))   # the box is a name in the grant set beside the grant: only a pack gives it; a box cannot be boxed
        s=State.from_packs([pack('162_loan')]);k=Kernel(s);day5=c.tick(k,5,execute=True);day15=c.tick(k,15,execute=True);day16=c.tick(k,16,execute=True);p=day16['clock_pack']
        self.assertEqual((brief(day5['runs'][0]),'revoke_grants' in day5['clock_pack'],'revoke_grants' in day15['clock_pack'],G in s.grants,brief(day16['runs'][0]),p['revoke_grants'],sorted(s.grants),s.fact('loan_disbursed')['truth']),
                         (ran,False,False,False,HOLDS,[G],[B15],'TRUE'))   # in its box the grant admits, on its last day too; past it the clock's pack takes it away, and the disbursal made under it still reads true
        self.assertEqual((day16['runs'][0]['provenance'][-1],s.loaded[-1]),({'pack':'clock@16','sha256':digest(p)},)*2)   # the pack that took the grant away is on the record of the run
        self.assertEqual(('clock_pack' in c.tick(k,16),len(s.loaded)),(False,4))   # and a second look on day 16 has nothing more to take away
        s=State.from_packs([pack('162_loan')]);k=Kernel(s);c.tick(k,5);k.on_event({'predicate':B20,'truth':'TRUE','verified':True,'source':'mallory','version':'1'});past=c.tick(k,16)   # no evidence row and no event moves a box
        self.assertEqual((past['clock_pack']['revoke_grants'],sorted(s.grants),brief(past['runs'][0])),([G],[B15],need))
        s=State.from_packs([pack('162_loan')]);k=Kernel(s);first=c.tick(k,16,execute=True,label='162_')   # the same pack first looked at on day 16: no grant, nothing runs. This is case 69, pack and run
        case=Kernel(State.from_packs([pack('162_loan'),pack('162_clock@16')])).run_standing(execute=True)['runs'][0]
        self.assertEqual((brief(first['runs'][0]),sorted(s.grants),first['time'],first['clock_pack'],first['runs'][0]['trace_root_sha256'],first['runs'][0]['provenance']),
                         (need,[B15],{'as_of':16,'late':['loan_disbursed']},pack('162_clock@16'),case['trace_root_sha256'],case['provenance']))
        s.apply(P('again',grants=[G]));self.assertEqual(brief(k.run_standing()['runs'][0]),ready)   # given again with no fresh box, the grant admits until the next tick (a stated limit), and that tick takes it away again: its old box is still on the record
        again=c.tick(k,16,execute=True);self.assertEqual((brief(again['runs'][0]),again['clock_pack']['id'],again['clock_pack']['revoke_grants'],sorted(s.grants)),(need,'clock@16',[G],[B15]))
        s.apply(P('fresh-box',grants=[G,B20]))   # given again with a fresh box, it stands until day 20: the disbursal runs, nine days late
        boxed=c.tick(k,16,execute=True);self.assertEqual((brief(boxed['runs'][0]),sorted(s.grants),boxed['time'],'clock_pack' in boxed),(ran,sorted([G,B15,B20]),{'as_of':16,'late':['loan_disbursed']},False))
        self.assertEqual((c.tick(k,20)['clock_pack'].get('revoke_grants'),c.tick(k,21)['clock_pack']['revoke_grants'],G in s.grants),(None,[G],False))   # of two boxes the later one counts, and its last moment too
        s=State.from_packs([pack('162_loan')]);k=Kernel(s);c.tick(k,16);s.apply(P('past-box',grants=[G,B10]));dry=brief(k.run_standing()['runs'][0])   # a box that had already ended when its pack arrived: the grant admits until the next tick (a stated limit)
        self.assertEqual((dry,brief(c.tick(k,16)['runs'][0]),sorted(s.grants)),(ready,need,sorted([B10,B15])))
        s=State.from_packs([pack('162_loan'),P('nest',grants=['box:5:'+B15])]);k=Kernel(s)   # a name that looks like a box on a box is no box: it lifts nothing
        self.assertEqual((c.tick(k,6)['clock_pack'].get('revoke_grants'),c.tick(k,16)['clock_pack']['revoke_grants'],sorted(s.grants)),(None,[G],sorted([B15,'box:5:'+B15])))
        free=State.from_packs([pack(n) for n in GATES]);kf=Kernel(free);c.tick(kf,10**9)   # a grant that was never boxed has no end
        self.assertEqual((sorted(free.grants),kf.run_standing()['runs'][0]['status']),(['action:ship-original@1','action:ship-replacement@1'],'PLAN_READY'))
        for bad in (('',3),(G,-1),(G,2.0),(G,True),(G,'3'),(3,3),(B15,20),(G,10**18)):
            with self.assertRaises(ValueError,msg=bad):c.box(*bad)
    def test_c7_late_is_a_read_of_the_tick_made_as_the_look_begins_and_never_a_status_word(self):
        due=P('due',evidence=[c.due('order_complete',5)]);plan=('PLAN_READY',['ship-replacement@1'])
        s,k=world(due,base=GATES);at5=c.tick(k,5);at6=c.tick(k,6)   # an approval that does not run out, a due-by on day 5: the last moment counts
        self.assertEqual((at5['time'],brief(at5['runs'][0])[:2],at6['time'],brief(at6['runs'][0])[:2]),({'as_of':5,'late':[]},plan,{'as_of':6,'late':['order_complete']},plan))   # a ready plan past its due-by is late; the status word is the same
        done=c.tick(k,6,execute=True);dry=c.tick(k,7);again=c.tick(k,7,execute=True)   # the tick that completes it past its due-by says so: it was overdue as the look began. Once the goal holds it is not late, on a dry look (which never says SUPPORTED_BY_EVIDENCE) or an executed one
        self.assertEqual((done['time'],done['runs'][0]['status'],dry['time'],dry['runs'][0]['status'],dry['runs'][0]['actions'],again['time'],again['runs'][0]['status']),
                         ({'as_of':6,'late':['order_complete']},'LOCAL_MODEL_EFFECTS_RECORDED',{'as_of':7,'late':[]},'PLAN_READY',[],{'as_of':7,'late':[]},'SUPPORTED_BY_EVIDENCE'))
        s,k=world(pack('164_due_by'),pack('165_two_goals'),base=GATES);both=c.tick(k,6,execute=True)   # two standing goals, where the first run makes the second hold: the order is late all the same, because it did not hold as the look began (the second run alone would say it held)
        self.assertEqual((both['time'],[brief(r) for r in both['runs']],[r['goal'] for r in both['runs']]),({'as_of':6,'late':['order_complete']},[SHIPPED,HOLDS],['replacement_delivered','order_complete']))
        s=State.from_packs([pack(n) for n in ASK]+[due]);k=Kernel(s);early=c.tick(k,2,execute=True);late=c.tick(k,6,execute=True)   # a goal that waits on a question is late past its due-by (held by this test alone: the independent books replay no ask)
        self.assertEqual((early['time'],early['runs'][0]['status'],late['time'],late['runs'][0]['status'],late['runs'][0]['stop_reasons']),({'as_of':2,'late':[]},'WAITING',{'as_of':6,'late':['order_complete']},'WAITING',[]))
        yes=answer(k,early['runs'][0]['model_receipts'][0],'TRUE','customer',execute=True);after=c.tick(k,6)   # a stated limit: the stamp's own run ships the order a day late; it carries the moment in its provenance and no late read, and the next tick finds the goal holding, so this late completion is never reported
        self.assertEqual((yes['runs'][0]['status'],yes['runs'][0]['provenance'][-1]['pack'],'time' in yes,'clock_pack' in after,after['time']),('LOCAL_MODEL_EFFECTS_RECORDED','clock@6',False,False,{'as_of':6,'late':[]}))
        s=State.from_packs([pack(n) for n in ASK]+[P('direct',goals=['customer_approved'],evidence=[c.due('customer_approved',5)])]);k=Kernel(s);c.tick(k,2,execute=True);alone=c.tick(k,6,execute=True)   # also when the goal is the very fact that was asked for: its plan is the wait alone, with nothing to do, and that is not holding
        self.assertEqual((alone['time'],alone['runs'][0]['status'],alone['runs'][0]['actions']),({'as_of':6,'late':['customer_approved']},'WAITING',[]))
        s,k=world();gone=c.tick(k,6,execute=True);run=gone['runs'][0]   # and so is a blocked one; the run, its stop reasons and its trace carry no word of it
        self.assertEqual((gone['time']['late'],run['status'],'late' in run,'time' in run,[e['operation'] for e in run['trace'] if 'LATE' in e['operation']],set(run['stop_reasons'])<=set(Kernel.RANK)),(['order_complete'],'QUERY_EVIDENCE',False,False,[],True))
        self.assertEqual(('time' in k.run_standing(),'time' in k.on_event(STOCK)),(False,False))   # late is the tick's read: a look started any other way reports none
        nodue=State.from_packs([pack(n) for n in ORDER[:-1]]);self.assertEqual(c.tick(Kernel(nodue),99)['time'],{'as_of':99,'late':[]})   # a goal with no due row is never late, whatever it reads
        s,k=world();met=c.tick(k,2,execute=True);lapsed=c.tick(k,4,execute=True);over=c.tick(k,6,execute=True)   # late means overdue now: the order shipped in time on day 2 is not late on day 4, when the approval it was shipped on has run out, and is late on day 6, past its due-by
        self.assertEqual((met['time']['late'],brief(met['runs'][0]),lapsed['time']['late'],brief(lapsed['runs'][0]),over['time']['late'],brief(over['runs'][0])),([],SHIPPED,[],BLOCKED,['order_complete'],BLOCKED))
        nodue.apply(P('missed',evidence=[row('in-time:order_complete','FALSE','1')]));self.assertEqual(c.tick(Kernel(nodue),99)['time'],{'as_of':99,'late':['order_complete']})   # late is whatever the due row says: one that reads FALSE is not in time either
        called=State.from_packs([pack(n) for n in ORDER[:-1]]+[pack('164_called_late')]);self.assertEqual((c.tick(Kernel(called),1,label='164_called_')['time'],pack('164_called_late')['evidence'][0]['truth']),({'as_of':1,'late':['order_complete']},'FALSE'))   # the recorded walk `called_late`
        a,b,d=c.due('g',5,source='s'),c.due('g',5),c.due('g',5,version='7')   # the due row is worded once: its source and version are the author's (the review found `source` held by nothing), and the recorded packs name the owner
        self.assertEqual(((a['source'],a['version'],a['predicate'],a['truth'],a['verified'],a['depends_on']),(b['source'],b['version']),d['version'],[(pack(n)['evidence'][i]['source'],pack(n)['evidence'][i]['version']) for n,i in (('160_timed_approval',1),('162_loan',1),('164_due_by',0))]),
                         (('s','1','in-time:g','TRUE',True,[{'predicate':'until:5','version':'window'}]),('fixture/reviewed','1'),'7',[('fixture/owner-due-by','1'),('fixture/owner-due-by','1'),('fixture/owner-due-by','due-by-1')]))
    def test_c8_the_moment_of_a_run_is_the_latest_clock_pack_in_its_provenance(self):
        s,k=world();a=c.tick(k,0);b=c.tick(k,2);entry={'pack':'clock@2','sha256':digest(b['clock_pack'])}
        looks=[k.run_standing()['runs'][0],k.resolve('replacement_delivered'),k.on_event(STOCK)['runs'][0],Kernel(s).run_standing(execute=True)['runs'][0]]   # however the run is started after the tick
        self.assertEqual([r['provenance'][-1] for r in looks],[entry]*4);self.assertEqual([x['pack'] for x in looks[0]['provenance']],list(ORDER)+['clock@0','clock@2'])
        self.assertEqual([max(m for m in map(c.stated,(x['pack'] for x in r['provenance'])) if m is not None) for r in looks],[2]*4)   # read off the names in the provenance alone
        ra,rb=a['runs'][0],b['runs'][0]   # the moment is in the provenance, not in the hash chain: the same look at two moments has one trace root and two provenances
        self.assertEqual((ra['trace_root_sha256']==rb['trace_root_sha256'],ra['provenance']==rb['provenance'],ra['provenance'][-1]['pack'],b['time']['as_of'],b['clock_pack']['evidence'][0]['at']),(True,False,'clock@0',2,2))
        now=s.fact('now');self.assertEqual((c.report(s)['as_of'],c.moment(s),now['at'],now['version'],now['source'],now['truth'],now['final']),(2,2,2,2,c.SOURCE,'TRUE',True))
        self.assertEqual((c.moment(State.from_packs([pack(n) for n in ORDER]+[pack('160_clock@6')])),c.moment(State.from_packs([pack(n) for n in ORDER]))),(6,None))   # and so has a State rebuilt from the recorded packs
        names=('clock@6','clock@6.1','clock@0','160_clock@6','160_clock@6.2','clock@9 clock@6','clock@06','clock@6.0','clock@6.','clock@','clock@-1','clock@6.1.1','Clock@6','160_day_6','clock@6_160',6,None)
        self.assertEqual([c.stated(n) for n in names],[6,6,0,6,6,6]+[None]*11)   # a clock pack's name ends with the clock's mark and its moment; what stands before is the caller's label
        # A run moved to another moment is refused by the independent check, also with the seal made again (the review's finding and the trigger of ruling R23: 'a swap of time between two run records that the verifier passes').
        v=verifier();data=record();ns=check_module();at=lambda d,walk,key:[st for st in d['scenes']['clock']['walks'][walk]['steps'] if st['key']==key][0]['result']['runs']
        def a_(d):run=copy.deepcopy(at(d,'same_moment','day_2')[0]);run['provenance']=copy.deepcopy(at(d,'order','day_6')[0]['provenance']);at(d,'order','day_6')[0]=run   # the dry look of day 2, which plans on the approval, under the tick of day 6
        def b_(d):x,y=copy.deepcopy(at(d,'order','day_6')[0]),copy.deepcopy(at(d,'same_moment','day_2')[0]);x['provenance'],y['provenance']=y['provenance'],x['provenance'];at(d,'order','day_6')[0],at(d,'same_moment','day_2')[0]=y,x   # the two trade their moments
        def c_(d):run=copy.deepcopy(at(d,'loan_late','day_16')[0]);run['provenance']=copy.deepcopy(at(d,'two_scopes','day_6')[0]['provenance']);at(d,'two_scopes','day_6')[0]=run   # a run that asks for authority, inside the box
        for change in (a_,b_,c_):
            d=copy.deepcopy(data);change(d);self.assertEqual(sorted(cid.split('_')[0] for cid,ok in ns['claims'](d,ROOT,v.sha,v.check_chain).items() if not ok),['S110'],change.__name__)   # each run still agrees with its own chain and names the packs of its new step: only the whole comparison tells
        d=copy.deepcopy(data);a_(d);c_(d);d['added']['scenes']['clock']=v.sha(d['scenes']['clock']);rows,why=v.module_rows(ROOT/'qa'/'checks'/'clock.py',d,ROOT,set())   # two of them at once with the seal of the sequence made again (it holds no secret, so the built-in seal check passes such a record): the module's rows, as the verifier takes them
        self.assertEqual((why,[cid.split('_')[0] for cid,ok,detail in rows if not ok],v.sha(d['scenes']['clock'])==d['added']['scenes']['clock']),(None,['S110','S119'],True))   # the time check refuses it (S119 runs no forgery on a record that does not pass)
    def test_c9_a_second_tick_at_the_same_moment_states_nothing_new(self):
        s,k=world();first=c.tick(k,2);n=len(s.loaded);ev=digest(s.evidence);second=c.tick(k,2)
        self.assertEqual(('clock_pack' in first,'clock_pack' in second,len(s.loaded),digest(s.evidence),second['time'],second['runs'][0]['trace_root_sha256']),(True,False,n,ev,first['time'],first['runs'][0]['trace_root_sha256']))
        self.assertEqual(('clock_pack' in c.tick(k,2,label='another'),len(s.loaded)),(False,n))   # nor under another label: a label names a pack, it is no reason to state one
        k.on_event(c.timed(row('stock_reserved','TRUE','1'),8));third=c.tick(k,2)   # something new arrives at that moment: the next tick states it, in a pack with a name of its own
        self.assertEqual((third['clock_pack']['id'],[r['predicate'] for r in third['clock_pack']['evidence']],s.fact('stock_reserved')['truth'],[e['pack'] for e in s.loaded[-2:]]),('clock@2.1',['now','until:3','until:5','until:8'],'TRUE',['clock@2','clock@2.1']))
        self.assertEqual(len({e['pack'] for e in s.loaded}),len(s.loaded))   # no two loaded packs share a name
        s,k=world();c.tick(k,2,label='168_');s.apply(pack('168_stock_hold'));before=s.fact('stock_reserved')['truth'];t=c.tick(k,2,label='168_')   # the recorded walk `same_moment`: the hold arrives in a pack after the day's tick, and the second pack of day 2 is the one its scenario file holds
        self.assertEqual((before,t['clock_pack'],s.fact('stock_reserved')['truth'],'clock_pack' in c.tick(k,2,label='168_'),[e['pack'] for e in s.loaded[-3:]]),('UNKNOWN',pack('168_clock@2.1'),'TRUE',False,['168_clock@2','168_stock_hold','168_clock@2.1']))
        s=State.from_packs([pack('162_loan'),pack('162_second_box')]);k=Kernel(s);c.tick(k,21,label='162_two_boxes_');s.apply(pack('162_sanction_again'));t=c.tick(k,21,label='162_two_boxes_')   # a grant to take away is something new too (the recorded walk `two_boxes`): the pack carries the revoke, and no row of it changes what is stored
        self.assertEqual((t['clock_pack'],t['clock_pack']['revoke_grants'],[c._lands(s,r) for r in t['clock_pack']['evidence']],'clock_pack' in c.tick(k,21,label='162_two_boxes_')),(pack('162_two_boxes_clock@21.1'),['action:disburse-loan@1'],[False]*3,False))
    def test_c10_an_allowance_comes_back_when_a_new_period_begins_and_by_nothing_else(self):
        R,S,X='LOCAL_MODEL_EFFECTS_RECORDED','SUPPORTED_BY_EVIDENCE','RESOURCE_REQUIRED';s=State.from_packs([pack('163_bureau_pulls')]);k=Kernel(s);seen=[]
        for now in (0,0,1,1,5):
            t=c.tick(k,now,execute=True);seen.append(([r['status'] for r in t['runs']],t.get('clock_pack',{}).get('budget'),s.budget['pulls']))
        self.assertEqual(seen,[([R,R,X],{'pulls':2},0),([S,S,X],None,0),([S,S,R],{'pulls':2},1),([S,S,S],None,1),([S,S,S],{'pulls':2},2)])   # two pulls a day: two run on day 0, a second look on day 0 gives nothing back, the third runs on day 1; a tick that jumps four days fills up once, to the allowance
        s=State.from_packs([pack('163_bureau_pulls')]);k=Kernel(s);c.tick(k,1,execute=True);k.on_event({'predicate':'now','truth':'TRUE','verified':True,'final':True,'source':c.SOURCE,'version':0,'at':0})   # a decision written by hand on `now` that says it is still day 0
        forged=c.tick(k,1,execute=True);s.apply(P('elsewhere',scope='orgB/other'));other=c.tick(k,1,execute=True)   # and the first tick made in another scope of the same State: the moment is the State's, read from its record of packs, so neither gives the allowance again
        self.assertEqual(([t['clock_pack'].get('budget') for t in (forged,other)],[t['clock_pack']['id'] for t in (forged,other)],s.budget['pulls'],[r['status'] for r in forged['runs']],[r['status'] for r in other['runs']]),
                         ([None,None],['clock@1.1','clock@1.2'],0,[S,S,X],[X,X,X]))
        w=State.from_packs([pack('163_weekly_pulls')]);kw=Kernel(w);week=[]   # a period of seven (the recorded walk `weekly`): given at the first clock pack and when a new period begins, not inside one; on day 14 its box has ended, so the clock takes it away and the smaller allowance beside it sets the level
        for now in (6,7,13,14):
            t=c.tick(kw,now,execute=True,label='163_weekly_');week.append(([r['status'] for r in t['runs']],t['clock_pack'].get('budget'),t['clock_pack'].get('revoke_grants')))
        self.assertEqual((week,'energy' in w.budget),([([R,X,X],{'pulls':1},None),([S,R,X],{'pulls':1},None),([S,S,X],None,None),([S,S,X],{'pulls':0},['allowance:pulls:1:7'])],False))
        low=[pack(n) for n in GATES+('15_low_budget',)]   # the recorded case 68: case 24's packs cannot ship on a budget of zero; with an allowance of two a day the clock pack of day 1 sets the level, and the order ships
        self.assertEqual(Kernel(State.from_packs(low)).run_standing(execute=True)['runs'][0]['status'],X)
        w=State.from_packs(low+[pack('161_allowance')]);t=c.tick(Kernel(w),1,execute=True,label='161_')
        self.assertEqual((t['clock_pack'],t['clock_pack']['budget'],brief(t['runs'][0]),w.budget),(pack('161_clock@1'),{'compute':2,'money':2},SHIPPED,ZERO))
        m=State.from_packs(low);km=Kernel(m);c.tick(km,1);m.apply(pack('161_allowance'));same_day=c.tick(km,1,execute=True);next_day=c.tick(km,2,execute=True)   # an allowance given in the middle of a period starts with the next one (a stated limit)
        self.assertEqual((same_day.get('clock_pack'),same_day['runs'][0]['status'],next_day['clock_pack']['budget'],next_day['runs'][0]['status']),(None,X,{'compute':2,'money':2},R))
        big=State.from_packs(low+[pack('06_notify'),pack('161_allowance')]);kb=Kernel(big)   # a plan that costs more than one period's allowance is never admitted: the kernel prices a plan whole (a stated limit)
        self.assertEqual([c.tick(kb,now,execute=True)['runs'][0]['status'] for now in (1,2,3)],[X]*3)
        odd=P('odd',grants=['allowance:energy:5:1','allowance:compute:3:0','allowance:compute:03:1',c.allowance('money',4,1),c.allowance('money',9,7)])   # what the clock does not fill (stated limits): a dimension the budget does not have, a malformed name
        o=State.from_packs([pack('163_bureau_pulls'),odd]);ko=Kernel(o);a=c.tick(ko,0);ko.on_event({'predicate':c.allowance('compute',7,1),'truth':'TRUE','verified':True,'source':'mallory','version':'1'});b=c.tick(ko,1)   # nor an evidence row or an event named like an allowance
        self.assertEqual((a['clock_pack']['budget'],b['clock_pack']['budget'],o.budget),({'money':9,'pulls':2},{'money':4,'pulls':2},{'compute':10,'money':4,'attention':3,'pulls':2}))   # two allowances on one dimension: the larger of those whose period turns sets the level
        o.apply(P('stop-money',revoke_grants=[c.allowance('money',4,1),c.allowance('money',9,7)]));o.budget['money']=0;self.assertEqual(c.tick(ko,2)['clock_pack']['budget'],{'pulls':2})   # an allowance taken away gives nothing more
        self.assertEqual((c.allowed('allowance:pulls:2:1'),c.allowed('allowance:a:b:2:1'),c.allowed('allowance:compute:3:0'),c.allowed('allowance::3:1'),c.allowed('pulls')),(('pulls',2,1),('a:b',2,1),None,None,None))
        o.apply(P('owner',budget={'pulls':9}));same=c.tick(ko,2);held=o.budget['pulls'];nxt=c.tick(ko,3)   # it sets the level: an owner's larger top-up lasts until the period turns
        self.assertEqual(('clock_pack' in same,held,nxt['clock_pack']['budget'],o.budget['pulls']),(False,9,{'pulls':2},2))
        e=State.from_packs([pack('163_bureau_pulls'),P('ends',grants=[c.box(c.allowance('pulls',2,1),0)])]);ke=Kernel(e);d0=c.tick(ke,0,execute=True);d1=c.tick(ke,1,execute=True)   # an allowance may be boxed: past its box the clock takes it away and gives nothing more
        self.assertEqual((d0['clock_pack'].get('budget'),d1['clock_pack'].get('budget'),d1['clock_pack']['revoke_grants'],[r['status'] for r in d1['runs']]),({'pulls':2},None,['allowance:pulls:2:1'],[S,S,X]))
        dims=State.from_packs([P('dims',budget={d:0 for d in 'fedcba'},preference=['compute','money','attention']+list('fedcba'),grants=[c.allowance(d,1,1) for d in 'cafebd']+['x']+[c.box('x',0)]+[y for g in 'qponm' for y in (g,c.box(g,0))])])
        self.assertEqual((list(c.clock_pack(dims,1)['budget']),c.clock_pack(dims,1)['revoke_grants']),(list('abcdef'),list('mnopqx')))   # the budget line and the revoke line are in name order, whatever order the grant set gives them: a clock pack's file is the same bytes on every run
        for bad in ((2,0),(-1,1),(2.0,1),(True,1),(2,'1'),(10**18,1)):
            with self.assertRaises(ValueError,msg=bad):c.allowance('pulls',*bad)
    def test_c11_the_kernel_is_the_pinned_kernel_without_a_word_of_time_and_the_clock_is_no_action_kind(self):
        src=(ROOT/'kernel'/'core.py').read_text();book=json.loads((ROOT/'added.json').read_text());listed={rel for entry in [book['points']]+book['applied'] for rel in entry['files']}
        self.assertEqual((hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest(),'kernel/core.py' in listed),(book['pinned']['kernel_sha256'],False))   # the kernel is the file the lab had before any version was added as files (pinned in added.json), and no added version lists it: this version adds no kernel line
        ns=check_module();self.assertEqual([w for w in ns['WORDS'] if w in src.lower()],[])   # and it holds none of the adapter's words, in any letter case (the review found the test reading small letters only): clock, tick, window, deadline, expire, allowance, overdue, in-time, moment, until:, as_of
        self.assertEqual(ns['WORDS'],('clock','tick','window','deadline','expire','allowance','overdue','in-time','moment','until:','as_of'))
        built_in=['ask','compile_candidate','emit_artifact','simulate_fact'];s,k=world();c.tick(k,2,execute=True)
        self.assertEqual((sorted(ACTIONS),sorted(s.actions),undeclared(),c.SOURCE),(sorted(built_in+KINDS),sorted(built_in+KINDS),[],'adapter:clock@1'))   # with the clock loaded and a tick made, the registry holds the four built-in kinds and the kinds declared in kinds/: the clock is an adapter, not a kind
        self.assertEqual([kind for kind,h in ACTIONS.items() if h['run'].__module__=='extensions.clock'],[])   # no handler is the clock's
        # What the module's text can show is narrow (the review reached the registry through a name built from two halves, past a search of the text), so the passage rests 'no action kind' on the record:
        # the handlers the record holds, the receipts, and the build, which refuses a record when a kind was registered outside kinds/. Here the text is parsed all the same: the adapter imports from the
        # kernel exactly Kernel, State and canonical, imports nothing else of the lab, and names none of the built-ins that reach an attribute by a name given as text.
        tree=ast.parse((ROOT/'extensions'/'clock.py').read_text());imports=[(n.module,sorted(a.name for a in n.names)) if isinstance(n,ast.ImportFrom) else (None,sorted(a.name for a in n.names)) for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
        self.assertEqual((sorted(imports,key=str),sorted({n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}&{'vars','getattr','setattr','globals','locals','eval','exec','compile','__import__','open','register','ACTIONS'})),
                         (sorted([('__future__',['annotations']),(None,['itertools']),('kernel.core',['Kernel','State','canonical'])],key=str),[]))
        data=record();v=verifier();S118=ns['IDS'][8];base=ns['world'](ROOT,v.sha);self.assertIs(ns['claims'](data,ROOT,v.sha,v.check_chain,made=base)[S118],True)
        d=dict(data,action_handlers=dict(data['action_handlers'],sneaked=dict(data['action_handlers']['ask'],module='extensions.clock',file='extensions/clock.py')))   # a handler of the clock's in the record fails the time check
        self.assertIs(ns['claims'](d,ROOT,v.sha,v.check_chain,made=base)[S118],False)
        kernel=(ROOT/'kernel'/'core.py').read_text()+'# TICK: the Clock reads the Deadline, Moment by Moment\n';h=hashlib.sha256(kernel.encode()).hexdigest();pinned=dict(book,pinned=dict(book['pinned'],kernel_sha256=h))   # the review's kernel: the adapter's words in capitals, pinned and recorded as if it were the lab's
        self.assertIs(ns['claims'](dict(data,kernel_sha256=h),ROOT,v.sha,v.check_chain,{'kernel/core.py':kernel,'added.json':json.dumps(pinned)})[S118],False)
    def test_c12_a_rule_and_a_step_that_name_a_window_stop_past_it_while_the_decision_beside_them_stands(self):
        w=State.from_packs([P('w',goals=['shipped'],evidence=[row('approved','TRUE','1',final=True)],methods=[M('ship@1','shipped',req=['approved','until:3'])],providers={'prov':2},grants=['g'])]);k=Kernel(w)
        self.assertEqual(k.run_standing()['runs'][0]['status'],'QUERY_EVIDENCE')   # before any tick the window is not published
        a=c.tick(k,2);b=c.tick(k,4)   # in the window the step is offered; past it the goal stops as REFUSED, and the approval is still decided
        self.assertEqual((brief(a['runs'][0])[:2],brief(b['runs'][0]),w.fact('approved')['truth'],w.fact('approved')['final']),(('PLAN_READY',['ship@1']),('REFUSED',[],0,['REFUSED']),'TRUE',True))
        r=State.from_packs([P('r',goals=['offer_open'],rules=[{'id':'R-OFFER@1','head':'offer_open','branches':[['approved','until:3']],'approved':True}],evidence=[row('approved','TRUE','1',final=True)])]);kr=Kernel(r)   # a rule may name a window as well: the offer holds while the window is open
        self.assertEqual((kr.run_standing()['runs'][0]['status'],brief(c.tick(kr,3)['runs'][0]),brief(c.tick(kr,4)['runs'][0])),('QUERY_EVIDENCE',('PLAN_READY',[],0,[]),('REFUSED',[],0,['REFUSED'])))
        self.assertEqual((c.windows(w),c.windows(r)),(['until:3'],['until:3']))   # a window that only a step names is in use, and so is one that only a rule names
        s=State.from_packs([pack('167_offer')]);ko=Kernel(s);day2=c.tick(ko,2,execute=True);made=copy.deepcopy(s.fact('offer_shipped'));day4=c.tick(ko,4,execute=True);day5=c.tick(ko,5,execute=True)   # the recorded pack, executed: the rule names day 3 and the step day 4, so on day 4 the offer is no longer open and what was shipped still stands; what the step made rests on the window it required, so it lapses with it on day 5 (an effect that must outlive its permission is made under a boxed grant, C6)
        refused=('REFUSED',[],0,['REFUSED'])
        self.assertEqual(([brief(x) for x in day2['runs']],made['truth'],{'predicate':'until:4','version':'window'} in made['depends_on'],[brief(x) for x in day4['runs']],[brief(x) for x in day5['runs']],s.fact('offer_shipped')['truth'],s.fact('offer_approved')['truth'],c.windows(s)),
                         ([('LOCAL_MODEL_EFFECTS_RECORDED',['ship-offer@1'],1,[]),HOLDS],'TRUE',True,[HOLDS,refused],[refused,refused],'UNKNOWN','TRUE',['until:3','until:4']))
        for bad in (row('p','TRUE','1',final=True),None,'row',{'depends_on':'x'}):   # a decision itself cannot be timed: it rests on nothing (the kernel's own rule), so it never lapses
            with self.assertRaises(ValueError,msg=repr(bad)):c.timed(bad,3)
        with self.assertRaises(ValueError):State().observe(dict(row('p','TRUE','1',final=True),depends_on=[{'predicate':'until:3','version':'window'}]))
    def test_c13_one_tick_states_every_scope_that_holds_rows_so_a_scope_the_state_left_does_not_stay_open(self):
        s,k=world();c.tick(k,2);s.apply(pack('162_loan'));there=c.tick(k,6)   # the first refuter's walk on the first build: the order is ticked on day 2, the State moves to the loan and is ticked there on day 6
        self.assertEqual(([(r['scope'],r['predicate'],r['truth']) for r in there['clock_pack']['evidence']],c.scopes(s)),
                         ([('orgA/lending','now','TRUE'),('orgA/lending','until:7','TRUE'),('orgA/lending','until:30','TRUE'),('orgA/fulfillment','now','TRUE'),('orgA/fulfillment','until:3','FALSE'),('orgA/fulfillment','until:5','FALSE')],['orgA/lending','orgA/fulfillment']))
        s.apply(pack('00_goal'));back=k.run_standing(execute=True)['runs'][0]   # back in the order's scope with no further tick: the approval that ended on day 3 is not believed, and nothing ships (the first build shipped here)
        self.assertEqual((brief(back),s.fact('customer_approved')['truth'],s.fact('now')['at'],c.moment(s),back['provenance'][-2]['pack']),(BLOCKED,'UNKNOWN',6,6,'clock@6'))
        s,k=world();c.tick(k,2,execute=True);s.apply(P('elsewhere',scope='orgB/other',evidence=[c.timed(row('x','TRUE','1'),9)]));there=c.tick(k,6)['clock_pack'];s.apply(P('back',scope='orgA/fulfillment'))   # the same with a row of another tenant: one moment for the State, one `now` row for each scope that holds rows
        self.assertEqual(([(r['scope'],r['predicate']) for r in there['evidence']],c.moment(s),s.fact('customer_approved')['truth'],s.fact('replacement_delivered')['truth'],s.fact('now')['at'],'clock_pack' in c.tick(k,6)),
                         ([('orgB/other','now'),('orgB/other','until:9'),('orgA/fulfillment','now'),('orgA/fulfillment','until:3'),('orgA/fulfillment','until:5')],6,'UNKNOWN','UNKNOWN',6,False))
        s.apply(P('third',scope='orgC/else',evidence=[c.timed(row('y','TRUE','1'),7)]));three=c.tick(k,8)['clock_pack']   # three scopes: the one the State is in comes first, then the others by name
        self.assertEqual(([(r['scope'],r['predicate'],r['truth']) for r in three['evidence'] if r['predicate']!='now'],[r['scope'] for r in three['evidence'] if r['predicate']=='now']),
                         ([('orgC/else','until:7','FALSE'),('orgA/fulfillment','until:3','FALSE'),('orgA/fulfillment','until:5','FALSE'),('orgB/other','until:9','TRUE')],['orgC/else','orgA/fulfillment','orgB/other']))
        m=State.from_packs([P('a',scope='orgA/one',methods=[M('m@1','done',req=['until:4'])],providers={'prov':1},grants=['g'],goals=['done'])]);km=Kernel(m);c.tick(km,2);m.apply(P('b',scope='orgA/two'))
        self.assertEqual((m.fact('until:4')['truth'],km.run_standing()['runs'][0]['status']),('UNKNOWN','QUERY_EVIDENCE'))   # a scope the State enters for the first time has no window published: closed until the next tick, which states a method's window there
        self.assertEqual((brief(c.tick(km,2)['runs'][0])[:2],m.fact('until:4')['truth'],c.windows(m,'orgA/one'),c.windows(m)),(('PLAN_READY',['m@1']),'TRUE',['until:4'],['until:4']))
    def test_stated_limits(self):
        s=State.from_packs([pack(n) for n in GATES]);k=Kernel(s);c.tick(k,10**9)
        self.assertEqual((s.fact('customer_approved')['truth'],c.windows(s)),('TRUE',[]))   # a row that names no window never expires
        s,k=world();c.tick(k,6)   # a verified row that writes a window by hand is believed until the next tick, which states the clock's own row over it
        k.on_event({'predicate':'until:1','truth':'TRUE','verified':True,'source':'mallory','version':'window'});k.on_event(c.timed(row('customer_approved','TRUE','x'),1))
        self.assertEqual(s.fact('customer_approved')['truth'],'TRUE');t=c.tick(k,6)
        self.assertEqual((s.fact('customer_approved')['truth'],s.fact('until:1')['source'],s.fact('until:1')['final'],t['clock_pack']['id']),('UNKNOWN',c.SOURCE,True,'clock@6.1'))
        ev=k.on_event({'predicate':'until:3','truth':'TRUE','verified':True,'final':True,'source':'mallory','version':'window'});k.on_event(c.timed(row('customer_approved','TRUE','y'),3))   # and so is a decision written by hand on a closed window: only a decision replaces a decision, and the next tick's is the clock's
        self.assertEqual((ev['status'],s.fact('customer_approved')['truth']),('RECONCILED','TRUE'));t=c.tick(k,6)
        self.assertEqual((s.fact('customer_approved')['truth'],s.fact('until:3')['source'],t['clock_pack']['id']),('UNKNOWN',c.SOURCE,'clock@6.2'))
        s,k=world();c.tick(k,2,execute=True);look=k.run_standing(execute=True)['runs'][0]   # time moves only at a tick: a look made without one reads the windows as the last tick left them
        self.assertEqual((look['status'],c.moment(s),s.fact('customer_approved')['truth']),('SUPPORTED_BY_EVIDENCE',2,'TRUE'))
        s,k=world();ran_out=c.tick(k,6,execute=True)['runs'][0];never=Kernel(State.from_packs([pack(n) for n in ORDER[:3]])).run_standing()['runs'][0]   # the moment and late are not in the hash chain: a run blocked on an approval that ran out has the trace of one blocked on an approval never given (case 02), and only its provenance and the stored rows tell them apart
        self.assertEqual((ran_out['trace_root_sha256'],ran_out['provenance']==never['provenance'],s.evidence[Q+'customer_approved']['truth'],s.fact('customer_approved')['truth']),(never['trace_root_sha256'],False,'TRUE','UNKNOWN'))
        s.apply(P('clock@99'));self.assertEqual(c.moment(s),99)   # a pack named like the clock's is taken for one, under any label: packs are the trusted channel
        with self.assertRaises(ValueError):c.tick(k,98)
        s.apply(P('by-hand clock@120'));self.assertEqual(c.moment(s),120)
        s=State.from_packs([pack('163_bureau_pulls')]);k=Kernel(s);t=c.tick(k,0,execute=True);left=s.budget['pulls'];s.apply(t['clock_pack']);again=k.run_standing(execute=True)   # the clock's own earlier pack applied again reopens nothing and moves no moment (C4), but its budget and revoke lines apply like any pack's: the allowance is handed out twice in one period
        self.assertEqual((left,[r['status'] for r in again['runs']][2],s.budget['pulls'],[e['pack'] for e in s.loaded],c.moment(s)),(0,'LOCAL_MODEL_EFFECTS_RECORDED',1,['163_bureau_pulls','clock@0','clock@0'],0))
        s,k=world();p2=c.tick(k,2)['clock_pack'];s.observe(row('day_pass','TRUE','1',depends_on=[{'predicate':'now','version':2}]));on2=s.fact('day_pass')['truth'];c.tick(k,4);on4=s.fact('day_pass')['truth'];s.apply(p2)   # and its `now` row is stored again until the next tick: a row that rests on `now` reads the earlier moment back (the moment itself does not move). Nothing should rest on `now`: a row is timed by a window
        self.assertEqual((on2,on4,s.fact('day_pass')['truth'],s.fact('now')['at'],c.moment(s),c.tick(k,4)['clock_pack']['id'],s.fact('day_pass')['truth']),('TRUE','UNKNOWN','TRUE',2,4,'clock@4.1','UNKNOWN'))
        boom=State(actions={**ACTIONS,'boom':{'run':lambda s,m,mid,deps:{},'plan':lambda s,m:1/0}});boom.apply(P('b',goals=['e'],methods=[M('m','e',action='boom')],providers={'prov':1},grants=['g']))
        with self.assertRaises(ZeroDivisionError):c.tick(Kernel(boom),3)   # the kernel's own limit: a plan hook that raises ends the look with its error; the clock's pack for that moment is already applied
        self.assertEqual((c.moment(boom),[e['pack'] for e in boom.loaded]),(3,['b','clock@3']))
        for name in ('until:03','until:-1','until:3.5','until:','until:x','Until:3','until:٣','until:²','until:'+'9'*19,'now',7,None):self.assertIsNone(c.closes(name),name)   # a window is named plainly, in ASCII digits; any other name is not one (a digit of another script, a superscript)
        self.assertEqual((c.stated('clock@²'),c.boxed('box:²:g'),c.allowed('allowance:pulls:²:1'),c.allowed('allowance:pulls:2:٣')),(None,None,None,None))   # and so for the moment in a pack's name, a box and an allowance
        self.assertEqual((c.closes('until:0'),c.closes('until:15'),c.window(15),c.timed({'predicate':'p'},3)['depends_on']),(0,15,'until:15',[{'predicate':'until:3','version':'window'}]))
        odd=State.from_packs([P('odd',evidence=[row('p','TRUE','1',depends_on=[{'predicate':'until:03','version':'window'}])])]);c.tick(Kernel(odd),0)
        self.assertEqual(odd.fact('p')['truth'],'UNKNOWN')   # and what rests on such a name is never believed
        G='action:x';names=['box:015:'+G,'box:15 :'+G,'box: 15:'+G,'Box:15:'+G,'box:15.0:'+G,'box:1e1:'+G,'box:5:box:15:'+G,'allowance:pulls:2','allowance:pulls:2:0','Allowance:pulls:2:1','allowance:pulls:02:1']   # a box or an allowance that is not written plainly is none: the grant has no end, the allowance never comes, and no tick says so (the kernel takes any name for a grant)
        w=State.from_packs([P('b',grants=[G]+names,budget={'pulls':0},preference=['compute','money','attention','pulls'])]);t=c.tick(Kernel(w),99);self.assertEqual(('revoke_grants' in t['clock_pack'],'budget' in t['clock_pack'],G in w.grants),(False,False,True))
        self.assertEqual((c.misnamed(P('b',grants=[G]+names)),c.misnamed(P('b',grants=[G,c.box(G,15),c.allowance('pulls',2,1),'boxes:1:g','allowances:1'],revoke_grants=['box:x:g'])),c.misnamed({}),c.misnamed(None),c.misnamed(P('b',grants='box:x'))),
                         (sorted(names),['box:x:g'],[],[],[]))   # what catches it is an authoring-time check: `misnamed` lists such names in a pack before it is applied
        self.assertEqual([n for f in sorted((ROOT/'scenarios').glob('16[0-9]_*.json')) for n in c.misnamed(json.loads(f.read_text()))],[])   # no scenario file of this version holds one (its pack file stops the build on one)
        empty=c.tick(Kernel(State()),3);self.assertEqual((empty['status'],empty['time']),('NO_STANDING_GOAL',{'as_of':3,'late':[]}))   # a State with no goals still has a moment
        many=State.from_packs([P(f'g{i}',grants=[x for j in range(i,i+33400) for x in (f'grant-{j}',c.box(f'grant-{j}',0))]) for i in range(0,100200,33400)]);was=books(many)   # the revoke and budget lines are not cut: a tick that must take away more grants at once than the kernel's door takes in one pack (here 100,200 boxes that ended together; grants come only from packs, the trusted channel) is refused whole, and that State's clock stands still
        with self.assertRaises(ValueError):c.tick(Kernel(many),1)
        self.assertEqual((books(many),c.moment(many)),(was,None))
        ask=lambda:State.from_packs([P('w',goals=['shipped'],methods=[M('ask@1','approved',action='ask',cost={'compute':0,'money':0,'attention':1},req=['until:3'],ask_to='customer',question='ok?'),M('ship@1','shipped',req=['approved'])],providers={'prov':3},grants=['g'])])
        w=ask();kw=Kernel(w);asked=c.tick(kw,2,execute=True)['runs'][0];later=[c.tick(kw,now,execute=True)['runs'][0] for now in (4,9)]   # a wait never expires (item 5 of the ruling, the ask's window, is not in this version): a question asked inside a window stays out after the window closed, because a wait needs none of its step's prerequisites
        self.assertEqual(([brief(asked)]+[brief(r) for r in later],[r['waits'] for r in later],sorted(open_asks(w)),w.fact('until:3')['truth']),([('WAITING',['ask@1'],1,[]),('WAITING',[],0,[]),('WAITING',[],0,[])],[['ask@1']]*2,['orgA/fulfillment|approved'],'FALSE'))
        self.assertEqual(brief(c.tick(Kernel(ask()),4,execute=True)['runs'][0]),('REFUSED',[],0,['REFUSED']))   # the window only gates the asking: past it the question is not put
        head=State.from_packs([P('r',goals=['shipped'],rules=[{'id':'R-OPEN@1','head':'offer_open','branches':[['approved','until:3']],'approved':True}],evidence=[row('approved','TRUE','1',final=True)],methods=[M('ship@1','shipped',req=['offer_open'])],providers={'prov':3},grants=['g'])]);kh=Kernel(head)
        dry=c.tick(kh,2)['runs'][0];ran=c.tick(kh,2,execute=True)['runs'][0];past=c.tick(kh,4,execute=True)['runs'][0]   # the base's own limit, met here: a step cannot rest on a rule's head, so a step that requires a head whose rule names a window is offered inside the window and recorded as stopped when executed. A step names the window among its own prerequisites (C12)
        self.assertEqual((brief(dry),ran['status'],ran['stopped'],ran['model_receipts'],brief(past)),(('PLAN_READY',['ship@1'],0,[]),'STEP_STOPPED',{'method':'ship@1','reason':'Prerequisite not true before effect: offer_open'},[],('REFUSED',[],0,['REFUSED'])))
        d=State.from_packs([P('d',goals=['g'],rules=[{'id':'R1','head':'g','branches':[['until:9']],'approved':True},{'id':'R2','head':'until:9','branches':[['yes']],'approved':True}],evidence=[row('yes','TRUE','1')])]);kd=Kernel(d)
        self.assertEqual((brief(kd.run_standing(execute=True)['runs'][0]),d.fact('until:9')['truth'],brief(c.tick(kd,5,execute=True)['runs'][0]),brief(c.tick(kd,10,execute=True)['runs'][0])),
                         (HOLDS,'UNKNOWN',HOLDS,('REFUSED',[],0,['REFUSED'])))   # packs are the trusted channel: a pack's rule whose head is a window name opens that window for rules that name it before the clock has published it; no stored row rests on it, and the clock's decision closes it at its time
        e=State.from_packs([P('e',goals=['shipped'])]);ke=Kernel(e);c.tick(ke,6)   # and so does a pack's step whose effect is a window name (the review's walk): the clock is at day 6, a pack arrives with a step that makes `until:3` and a step that needs it, and a look with no tick runs both, on a window that ended at 3
        e.apply(P('m',providers={'prov':3},grants=['g'],methods=[M('open@1','until:3',cost=ZERO),M('ship@1','shipped',req=['until:3'],cost=ZERO)]));ran=ke.run_standing(execute=True)['runs'][0];made=e.fact('until:3');nxt=c.tick(ke,6,execute=True)
        self.assertEqual((brief(ran),made['truth'],made['source'],nxt['clock_pack']['id'],brief(nxt['runs'][0]),e.fact('shipped')['truth'],e.fact('until:3')['source']),
                         (('LOCAL_MODEL_EFFECTS_RECORDED',['open@1','ship@1'],2,[]),'TRUE','LOCAL_MODEL:open@1','clock@6.1',('REFUSED',[],0,['REFUSED']),'UNKNOWN',c.SOURCE))   # the next tick states the clock's decision over the step's row, the goal reads REFUSED and what was shipped reads unknown
        # Finished work is done and paid a second time once what it was made on has lapsed and is given again (the review's finding; the recorded walk `loan` shows it). The kernel's built-in step rests its row on every
        # prerequisite, so when a timed prerequisite runs out the goal is open again. Ruling R27's must-hold (a restated guard re-opens no finished goal) is not met by this version: it needs a step kind that keeps
        # its guards out of what its product rests on. Until then a fact that must not undo finished work is given as a boxed grant, never as a timed prerequisite.
        G='action:disburse-loan@1';s=State.from_packs([pack('162_loan')]);k=Kernel(s);seen=[]
        for now in (5,16,31):t=c.tick(k,now,execute=True,label='162_');seen.append((brief(t['runs'][0]),t['time']['late'],s.budget['money'],s.fact('loan_disbursed')['truth']))
        s.apply(pack('162_renewal'));t=c.tick(k,31,execute=True,label='162_');seen.append((brief(t['runs'][0]),t['time']['late'],s.budget['money'],s.fact('loan_disbursed')['truth']))
        paid=('LOCAL_MODEL_EFFECTS_RECORDED',['disburse-loan@1'],1,[])
        self.assertEqual((seen,t['clock_pack']==pack('162_clock@31.1'),sum(j.get('status')=='LOCAL_MODEL_EFFECTS_RECORDED' for j in s.event_journal)),
                         ([(paid,[],9,'TRUE'),(HOLDS,[],9,'TRUE'),(('QUERY_EVIDENCE',[],0,['QUERY_EVIDENCE']),['loan_disbursed'],9,'UNKNOWN'),(paid,['loan_disbursed'],8,'TRUE')],True,2))
        s,k=world();ships=[brief(c.tick(k,2,execute=True)['runs'][0]),brief(c.tick(k,4,execute=True)['runs'][0])];k.on_event(c.timed(row('customer_approved','TRUE','fresh'),9));ships.append(brief(c.tick(k,4,execute=True)['runs'][0]))   # the same on the order: it ships on day 2, the approval runs out, a fresh approval arrives, and it ships again
        self.assertEqual((ships,s.budget['money']),([SHIPPED,BLOCKED,SHIPPED],6))
        boxed=State.from_packs([P('kept',scope='orgA/lending',goals=['loan_disbursed'],methods=[M('disburse@1','loan_disbursed',cost={'compute':1,'money':1,'attention':0})],providers={'prov':3},grants=['g',c.box('g',15)])]);kb=Kernel(boxed)   # under a boxed grant nothing lapses: the report's time is part of the permission, not a prerequisite, and the disbursal reads true for good
        self.assertEqual(([c.tick(kb,now,execute=True)['runs'][0]['status'] for now in (5,16,31,10**6)],boxed.budget['money'],boxed.fact('loan_disbursed')['truth']),(['LOCAL_MODEL_EFFECTS_RECORDED']+['SUPPORTED_BY_EVIDENCE']*3,9,'TRUE'))
        k=Kernel(State())
        for bad in (lambda:c.due(5,3),lambda:c.due('',3),lambda:c.timed(None,3),lambda:c.overdue(State(),5),lambda:c.overdue(None,'g'),lambda:c.window(-1),lambda:c.due('g',2.5),
                    lambda:c.tick(None,3),lambda:c.tick(k.s,3),lambda:c.clock_pack(k,3),lambda:c.clock_pack(None,3),lambda:c.clock_packs(k,3)):   # the helpers refuse what is not theirs with a ValueError, never another error
            with self.assertRaises(ValueError):bad()
        self.assertEqual((c.moment(k.s),k.s.loaded),(None,[]))
    def test_the_recorded_sequence_is_made_again_identically_and_its_cases_are_its_ticks(self):
        data=record();ns={}   # the record is what tools/run_all.py wrote before the tests ran
        exec(compile((ROOT/'tools'/'scenes'/'clock.py').read_text(),'clock scene','exec'),ns)
        lab={'State':State,'Kernel':Kernel,'pack':pack,'answer':answer,'open_asks':open_asks,'Learner':Learner,'digest':digest};live=ns['scene'](lab)
        self.assertEqual(json.loads(json.dumps(live)),data['scenes']['clock'])
        def tally(v):   # (looks, runs) in the record, counted here and not by the scene's own counter: a look is a dict holding a list under runs, a run a dict with trace and trace_root_sha256
            if type(v) is dict:return tuple(map(sum,zip((type(v.get('runs')) is list,'trace' in v and 'trace_root_sha256' in v),*[tally(x) for x in v.values()])))
            return tuple(map(sum,zip((0,0),*[tally(x) for x in v]))) if type(v) is list else (0,0)
        said=[(t.targets[0].id,t.value.value) for t in ast.parse((ROOT/'tools'/'scenes'/'clock.py').read_text()).body if isinstance(t,ast.Assign) and len(t.targets)==1 and isinstance(t.targets[0],ast.Name) and t.targets[0].id in ('LOOKS','RUNS')]
        self.assertEqual((sorted(said),tally(data['scenes']['clock'])),([('LOOKS',66),('RUNS',81)],(66,81)))   # the scene file states its true counts at its top level, once each
        whole=ns['walks'];ns['walks']=lambda clock:whole(clock)[1:2]   # the scene made with one walk alone (late_order: one look, one run): other counts than it states, so it stops
        with self.assertRaisesRegex(RuntimeError,r'the scene states LOOKS = 66 and RUNS = 81 and recorded \(1, 1\)'):ns['scene'](lab)
        ns['walks']=whole
        walks=data['scenes']['clock']['walks'];self.assertEqual((sorted(walks),sum(len(w['steps']) for w in walks.values())),(WALKS,90))
        stated=[p for w in walks.values() for st in w['steps'] if st['kind']=='tick' and 'clock_pack' in st['result'] for p in [st['result']['clock_pack']]+st['result'].get('more_clock_packs',[])]
        files=sorted(f.stem for f in (ROOT/'scenarios').glob('16[0-9]_*.json') if c.stated(f.stem) is not None)   # every clock pack among the scenario files was stated by a recorded tick, and every tick stated the pack its file holds
        self.assertEqual((sorted({p['id'] for p in stated}),all(pack(p['id'])==p for p in stated),len(stated),len(files)),(files,True,47,42))
        self.assertEqual(sorted(f.stem for f in (ROOT/'scenarios').glob('16[0-9]_*.json') if c.stated(f.stem) is None),
                         ['160_timed_approval','161_allowance','162_loan','162_renewal','162_sanction_again','162_second_box','163_branch','163_bureau_pulls','163_lending','163_weekly_pulls','164_called_late','164_due_by','165_two_goals','167_offer','168_stock_hold','169_shipping_pass'])
        cases={x['id']:x for x in data['cases']}
        for cid,walk in (('67_late_order','late_order'),('67a_order_in_time','order'),('68_allowance','allowance'),('69_permission_ran_out','loan_late')):   # each time case is the first tick of its walk: the packs, the pack the tick stated, the run
            tick=walks[walk]['steps'][0]['result'];run=cases[cid]['outcome']
            self.assertEqual((cases[cid]['packs'],run['trace_root_sha256'],run['provenance'],run['status']),(walks[walk]['packs']+[tick['clock_pack']['id']],tick['runs'][0]['trace_root_sha256'],tick['runs'][0]['provenance'],tick['runs'][0]['status']),cid)
        mine={m['id']:m for m in MORE if m['id'][:2] in ('67','68','69')}   # the four case files of this version, as the lab reads them
        self.assertEqual([(i,m['area'],m['execute'],m['expected']) for i,m in sorted(mine.items())],[('67_late_order','Time',True,'QUERY_EVIDENCE'),('67a_order_in_time','Time',True,'LOCAL_MODEL_EFFECTS_RECORDED'),
                                                                                                    ('68_allowance','Time',True,'LOCAL_MODEL_EFFECTS_RECORDED'),('69_permission_ran_out','Time',True,'AUTHORITY_REQUIRED')])
        # The independent check's own books make the same sequence and the same four cases from the pack files, the case files and the check's own script, without the kernel and without the adapter.
        v=verifier();made=check_module()['world'](ROOT,v.sha)
        self.assertEqual((made['walks'],[made['cases'][cid] for cid in sorted(mine)],sorted(p['id'] for p in made['stated'])),(walks,[cases[cid] for cid in sorted(mine)],sorted(p['id'] for p in stated)))
    def test_random_walks_keep_the_claims_and_the_independent_books_make_what_the_kernel_and_the_adapter_make(self):
        count=random_walks(self,120,30,7)   # 3600 random steps on 120 small worlds, the same every time (seed 7): see random_walks above for what is held at every step
        floor={'tick':1000,'clock pack':800,'late':300,'run':3000,'receipt':80,'refused':150,'row':250,'by hand':200,'decision by hand':100,'pack':250,'clock pack again':50,'named like the clock':20,'scope':80,'look':120,
               'PLAN_READY':300,'LOCAL_MODEL_EFFECTS_RECORDED':80,'SUPPORTED_BY_EVIDENCE':100,'QUERY_EVIDENCE':300,'REFUSED':100,'AUTHORITY_REQUIRED':100,'RESOURCE_REQUIRED':50,'METHOD_ABSENT':20}
        self.assertEqual({k:count[k]>=v for k,v in floor.items()},{k:True for k in floor},dict(count))   # and the walks did exercise each of these, not a corner of them
    def test_each_independent_check_refuses_forgeries_of_its_own_and_a_record_that_cannot_be_read_is_ten_failed_rows(self):
        v=verifier();data=record();src=(ROOT/'qa'/'checks'/'clock.py').read_text();ns=check_module();IDS=ns['IDS'];number=lambda cid:cid.split('_')[0]
        # The check module is run here as the verifier runs it: its text passes the verifier's own guard (it imports json, hashlib and re and nothing of the lab), and it is handed the verifier's hash and chain check.
        self.assertEqual((v.guard(src),[v.number(i) for i in IDS]),(None,list(range(110,120))))
        told,refused=ns['survey'](data,ROOT,v.sha,v.check_chain);self.assertEqual(ns['verdict'](told,refused),[(cid,True,'') for cid in IDS])   # what checks() returns: the nine on the record, then every forgery in turn
        seen={};own={}
        for i,((target,change),by) in enumerate(zip(ns['FORGERIES'],refused)):   # every forgery is refused by the check it is listed for
            self.assertIsNotNone(by,i);by=[number(x) for x in by];self.assertIn(target,by,(i,by));seen.setdefault(target,[]).append(by)
            if by==[target]:own.setdefault(target,(target,change))
        self.assertEqual((sorted(seen),sorted(own),len(ns['FORGERIES'])),([number(x) for x in IDS[:9]],[number(x) for x in IDS[:9]],87))   # each of the nine checks has forgeries of its own, and one that it alone refuses: with that check switched off, that forgery would pass the other eight
        self.assertEqual({t:sum(1 for by in seen[t] if 'S110' not in by) for t in sorted(seen) if t not in ('S110','S118')},{'S111':2,'S112':2,'S113':3,'S114':4,'S115':2,'S116':3,'S117':3})   # for S111 to S117 these are worlds made again from end to end, which the whole comparison of S110 passes: only the pins tell
        def with_forgeries(forgeries):   # checks() of the module, run with another list of forgeries in the module's own names
            m=check_module();m['FORGERIES']=forgeries;return m['checks'](data,ROOT,v.sha,v.check_chain)
        least=[own[t] for t in sorted(own)];self.assertEqual(with_forgeries(least),[(cid,True,'') for cid in IDS])   # nine forgeries, one for each check alone, are enough for S119
        for what,forgeries in (('a forgery that changes nothing',least+[('S116',lambda d,f,t,m:None)]),('a forgery listed for a check that does not refuse it',least+[('S117',lambda d,f,t,m:d.update(kernel_sha256='0'*64))]),
                               ('a check without a forgery of its own',[x for x in least if x[0]!='S113']),('a forgery that cannot be made',least+[('S110',lambda d,f,t,m:d['no_such_block'].clear())])):
            got=with_forgeries(forgeries);self.assertEqual(([ok for cid,ok,detail in got],got[-1][0],got[-1][2]!=''),([True]*9+[False],IDS[9],True),what)   # S119 itself fails on each of these
        # a record the checks cannot read is ten failed rows that say why, not an error that ends the verifier; a walk taken out fails the nine and the tenth
        for what,change in (('the sequence taken out',lambda d:d['scenes'].pop('clock')),('no sequences at all',lambda d:d.pop('scenes')),('a walk without its steps',lambda d:d['scenes']['clock']['walks']['order'].pop('steps'))):
            d=json.loads(json.dumps(data));change(d);got=ns['checks'](d,ROOT,v.sha,v.check_chain)
            self.assertEqual(([cid for cid,ok,detail in got],[ok for cid,ok,detail in got],all(type(detail) is str and detail for cid,ok,detail in got)),(list(IDS),[False]*10,True),what)
        d=json.loads(json.dumps(data));d['scenes']['clock']['walks'].pop('planted');got=ns['checks'](d,ROOT,v.sha,v.check_chain)
        self.assertEqual(([cid for cid,ok,detail in got],[ok for cid,ok,detail in got]),(list(IDS),[False]*10))
        # each check stands on its own: a record that one of them cannot read fails that one (and S119, which runs no forgery on a record that does not pass), not its neighbours
        for what,change,fails in (('a time case taken out',lambda d:d['cases'].remove([x for x in d['cases'] if x['id']=='67_late_order'][0]),['S110','S111','S112','S118','S119']),
                                  ('the handlers gone',lambda d:d.pop('action_handlers'),['S118','S119']),('a tick without its report',lambda d:d['scenes']['clock']['walks']['due']['steps'][0]['result'].pop('time'),['S110','S111','S116','S119']),
                                  ('the crowd without its second pack',lambda d:d['scenes']['clock']['walks']['crowd']['steps'][2]['result'].pop('more_clock_packs'),['S110','S114','S119'])):
            d=json.loads(json.dumps(data));change(d);got=ns['checks'](d,ROOT,v.sha,v.check_chain)
            self.assertEqual(([cid for cid,ok,detail in got],[number(cid) for cid,ok,detail in got if not ok]),(list(IDS),fails),what)
        # the books replay the built-in kind only: a pack with a step of another kind, a constructor or the learner switched on is refused by them, so a time walk on such a pack fails every check instead of passing unread
        for bad in (P('x',methods=[M('m','e',action='ask')]),P('x',constructors=[{'id':'C'}]),P('x',learning=True)):
            with self.assertRaises(ValueError,msg=bad):ns['Books'](v.sha).load(bad)
    def test_a_field_of_the_record_changed_anywhere_is_refused(self):
        """The review changed single fields of the recorded sequence and of the time cases and found the ones no check read (a step's execute, the row an event brought, a refused tick's moment and
        words, a run's needs, the digests of the books, a case's scope, its run block, its rule ids, its viewer's views, the stored row of a step that ran). Now every walk and every time case is
        compared whole with what the check's own books make, so there is no field to find. Shown here on 250 places picked the same way on every run, over every walk and all four cases: each is
        changed alone (a text gets a letter more, a number one more, true and false trade places, a list loses its last item or gains one, a key is taken out) and the check must refuse it."""
        v=verifier();data=record();ns=check_module();base=ns['world'](ROOT,v.sha);rnd=random.Random(11);S110=ns['IDS'][0]
        def paths(x,at=()):   # every place in a value: each key of each dict, each item of each list, each leaf
            if isinstance(x,dict):
                for key in x:
                    yield at+(key,);yield from paths(x[key],at+(key,))
            elif isinstance(x,list):
                yield at+('+',)   # the list itself: one item more
                for i in range(len(x)):
                    yield at+(i,);yield from paths(x[i],at+(i,))
        def changed(root,path,how):
            *way,last=path;x=root
            for key in way:x=x[key]
            if last=='+':x.append(copy.deepcopy(x[-1]) if x else 'x');return 'an item more'
            if how=='out' or isinstance(x[last],(dict,list)):
                if isinstance(x,dict):del x[last]
                else:x.pop(last)
                return 'taken out'
            was=x[last];x[last]=(not was) if type(was) is bool else was+1 if type(was) in (int,float) else was+'x' if type(was) is str else 0;return 'changed'
        walks=data['scenes']['clock']['walks'];cases={x['id']:i for i,x in enumerate(data['cases'])};places=[]
        for name in WALKS:places+=[(('scenes','clock','walks',name)+p) for p in paths(walks[name])]
        for cid in ns['CASES']:places+=[(('cases',cases[cid])+p) for p in paths(data['cases'][cases[cid]])]
        self.assertGreater(len(places),20000);picked=rnd.sample(places,250);seen=collections.Counter()
        for path in picked:
            d=dict(data,cases=list(data['cases']),scenes=dict(data['scenes'],clock={'walks':dict(walks)}))
            if path[0]=='cases':d['cases'][path[1]]=copy.deepcopy(data['cases'][path[1]])
            else:d['scenes']['clock']['walks'][path[3]]=copy.deepcopy(walks[path[3]])
            how=changed(d,path,rnd.choice(['change','change','out']));seen[how]+=1;seen[path[0]]+=1
            try:held=ns['claims'](d,ROOT,v.sha,v.check_chain,made=base)[S110]
            except Exception:held=False;seen['could not be read']+=1   # a record the checks cannot read at all is ten failed rows (checks() says why)
            self.assertIs(held,False,(path,how))
        self.assertTrue(seen['changed']>60 and seen['taken out']>40 and seen['cases']>5 and seen['scenes']>120 and seen['could not be read']<25,dict(seen))
    def test_the_verifier_takes_the_ten_rows_of_the_module(self):
        v=verifier();data=record();IDS=check_module()['IDS']
        rows,why=v.module_rows(ROOT/'qa'/'checks'/'clock.py',data,ROOT,set())   # as the verifier runs a delivered module: its text through the guard, a copy of the record, every row held to its shape and its number
        self.assertEqual((rows,why,[v.number(cid) in v.RESERVED for cid in IDS]),([(cid,True,'') for cid in IDS],None,[False]*10))
        self.assertEqual(v.module_rows(ROOT/'qa'/'checks'/'clock.py',{'cases':[]},ROOT,{115})[1],'it returned '+IDS[5]+', whose number is reserved or already taken')   # a number another module took first would be this module's one failed row (shown on a record with no sequence: its ten rows fail, and they are still ten rows of the right shape)
        rows,why=v.module_rows(ROOT/'qa'/'checks'/'clock.py',{'cases':[]},ROOT,set());self.assertEqual((why,[cid for cid,ok,detail in rows],[ok for cid,ok,detail in rows],{detail for cid,ok,detail in rows}),(None,list(IDS),[False]*10,{'the time record or a file it rests on cannot be read: KeyError'}))

    # ---- The confirming round: two refuters on this version applied to the promoted base. No finding blocked release and none is settled with new code. The passage says what the
    # code does, and the tests below pin it as it is today: one test for each finding (ten, counting once what both refuters found), and in the last of them one assertion for each
    # one-line edit of the code that the tests had let live.
    def test_confirm_the_revoking_pack_of_a_cut_tick_is_the_first_pack_of_its_moment(self):
        """Both refuters, C6. The pack that takes a boxed grant away is the last entry of the run's provenance only while the tick states one pack. When the rows are cut, the
        revoke line is in the first pack of that moment and the last entry is a pack of rows alone. The grant is taken away and the run's moment is right either way."""
        ready=('PLAN_READY',['do@1'],0,[]);need=('AUTHORITY_REQUIRED',[],0,['AUTHORITY_REQUIRED']);seen={}
        for n in (10,70):   # ten timed rows fit one pack, seventy do not
            s=State.from_packs([P('w',goals=['done'],methods=[M('do@1','done')],providers={'prov':2},grants=['g',c.box('g',5)],evidence=[c.timed(row(f'f{i}','TRUE','1'),100+i) for i in range(n)])]);k=Kernel(s)
            inside=c.tick(k,5);t=c.tick(k,6,execute=True);stated=[t['clock_pack']]+t.get('more_clock_packs',[]);run=t['runs'][0];names=[e['pack'] for e in run['provenance']]
            seen[n]=(brief(inside['runs'][0]),brief(run),[p['id'] for p in stated],[p['id'] for p in stated if 'revoke_grants' in p],stated[0]['revoke_grants'],names[-len(stated):],'g' in s.grants,
                     max(m for m in map(c.stated,names) if m is not None),run['provenance'][-len(stated)]=={'pack':'clock@6','sha256':digest(stated[0])})
        self.assertEqual(seen[10],(ready,need,['clock@6'],['clock@6'],['g'],['clock@6'],False,6,True))   # one pack: the revoking pack is the last entry of the run's provenance
        self.assertEqual(seen[70],(ready,need,['clock@6','clock@6.1'],['clock@6'],['g'],['clock@6','clock@6.1'],False,6,True))   # two packs: it is the first pack of that moment, and the last entry carries no revoke line
        day6=[st for st in record()['scenes']['clock']['walks']['crowd']['steps'] if st['key']=='day_6'][0]['result']   # the recorded walk `crowd` has the same order, on a run that does not need the grant
        self.assertEqual((day6['clock_pack']['revoke_grants'],'revoke_grants' in day6['more_clock_packs'][0],[e['pack'] for e in day6['runs'][0]['provenance']][-2:],day6['runs'][0]['status']),
                         (['action:ship-replacement@1'],False,['169_crowd_clock@6','169_crowd_clock@6.1'],'QUERY_EVIDENCE'))
    def test_confirm_the_second_disbursal_of_the_loan_is_held_by_no_pin(self):
        """Refuter 1, limit 3 with limit 13. On the record as built S110 holds the walk `loan` to what the check's books make from the pack files, so the second disbursal is held while
        the pack files are the ones the build authored. A world made again from end to end from a renewal pack that gives no grant, or whose report reads FALSE or is named otherwise,
        has no second disbursal, and S110 to S118 all hold on it: no pin names the renewal, the status of that step or the money of the walk. Against the pack file the second
        disbursal is held by unit tests alone: test_stated_limits, and the first assertion here, which reads the record as built."""
        ns=check_module();v=verifier();data=record();base=ns['world'](ROOT,v.sha);loan=data['scenes']['clock']['walks']['loan'];last=lambda walk:[st for st in walk['steps'] if st['key']=='day_31_renewed'][0]
        short=lambda r:(r['status'],r['actions'],[x['method'] for x in r['model_receipts']],r['stop_reasons'])
        self.assertEqual((short(last(loan)['result']['runs'][0]),loan['start']['budget']['money'],[st['after']['budget']['money'] for st in loan['steps']]),
                         (('LOCAL_MODEL_EFFECTS_RECORDED',['disburse-loan@1'],['disburse-loan@1'],[]),10,[9,9,9,9,9,9,8]))   # the record as built: disbursed on day 5 and again on day 31, money 10, 9, 8
        def no_grants(x):x.pop('grants')
        def report_false(x):x['evidence'][0].update(truth='FALSE')
        def report_renamed(x):x['evidence'][0].update(predicate='bureau_report_clear')
        for edit,stop in ((no_grants,'AUTHORITY_REQUIRED'),(report_false,'METHOD_ABSENT'),(report_renamed,'QUERY_EVIDENCE')):
            x=pack('162_renewal');edit(x);made=ns['world'](ROOT,v.sha,{'scenarios/162_renewal.json':json.dumps(x)});step=last(made['walks']['loan'])
            self.assertEqual((short(step['result']['runs'][0]),step['after']['budget']['money'],ns['refusers'](data,ROOT,v.sha,v.check_chain,ns['again']('scenarios/162_renewal.json',edit),base)),
                             ((stop,[],[],[stop]),9,[]),edit.__name__)   # no second disbursal, the money stays at 9, and none of the nine checks refuses that world
    def test_confirm_a_clock_that_says_nothing_about_a_window_passes_both_cases_of_the_pair(self):
        """Refuter 1, the pair of cases 67 and 67a. The pair tells a clock that published no window (it fails 67a) and a clock that still states a closed window open (it fails 67):
        test_c1 shows both. A clock that never closes a window but says nothing about it past its time passes both cases. What tells it is the walk `order` (on a State that saw
        day 2 the approval would stay believed) and the stored row of case 67, the clock's decision, which S112 pins."""
        cases={m['id']:m for m in MORE};late,twin=cases['67_late_order'],cases['67a_order_in_time'];silent=lambda p:dict(p,evidence=[r for r in p['evidence'] if r['truth']!='FALSE'])   # a clock pack without a word on the windows past their time
        run=lambda packs:brief(Kernel(State.from_packs(packs)).run_standing(execute=True)['runs'][0])
        self.assertEqual(([r['predicate'] for r in silent(pack('160_clock@6'))['evidence']],run([pack(n) for n in late['packs'][:-1]]+[silent(pack('160_clock@6'))]),late['expected'],run([pack(n) for n in twin['packs']]),twin['expected']),
                         (['now'],BLOCKED,'QUERY_EVIDENCE',SHIPPED,'LOCAL_MODEL_EFFECTS_RECORDED'))   # case 67 under the silent clock stops exactly as the case expects, and the twin's pack of day 2 has no window past its time to be silent about
        s=State.from_packs([pack(n) for n in twin['packs']]);k=Kernel(s);day2=brief(k.run_standing(execute=True)['runs'][0]);day4=silent(c.clock_pack(s,4));s.apply(day4)   # a State that saw day 2, then the silent clock's pack of day 4
        self.assertEqual((day2,[r['predicate'] for r in day4['evidence']],c.moment(s),s.fact('until:3')['truth'],s.fact('customer_approved')['truth'],brief(k.run_standing(execute=True)['runs'][0])),
                         (SHIPPED,['now','until:5'],4,'TRUE','TRUE',HOLDS))   # the window stays as day 2 stated it, so past its time the approval is still believed and the shipment still stands
        data=record();at4=[st for st in data['scenes']['clock']['walks']['order']['steps'] if st['key']=='day_4'][0]['after']['reads'];kept=[x for x in data['cases'] if x['id']=='67_late_order'][0]['derived_state']['facts'][Q+'until:3']
        self.assertEqual((at4['customer_approved'],at4['until:3'],kept['truth'],kept['final'],kept['source']),('UNKNOWN','FALSE','FALSE',True,c.SOURCE))   # what tells: the walk `order` on day 4, and the row the record keeps for case 67
    def test_confirm_a_window_only_a_goal_a_rule_head_or_a_step_effect_names_is_not_in_use(self):
        """Both refuters, limits 2 and 6. A window is in use, and so stated by the clock, when a stored row is named so or rests on it, when a step requires it or when an approved
        rule names it in one of its alternatives. A window that only a standing goal, a rule's head, a step's effect or a rule that is only proposed names is not in use: no tick
        states it, so it never closes, until a row of that name is stored (the step ran); the tick after that states the clock's decision. Reached only when the window itself is
        the goal: whatever rests on a window names it."""
        d=State.from_packs([P('d',goals=['until:9'],rules=[{'id':'R2','head':'until:9','branches':[['yes']],'approved':True}],evidence=[row('yes','TRUE','1')])]);kd=Kernel(d);seen=[]
        for now in (5,10,50):t=c.tick(kd,now,execute=True);seen.append((brief(t['runs'][0]),[r['predicate'] for r in t['clock_pack']['evidence']],c.windows(d)))
        self.assertEqual(seen,[(HOLDS,['now'],[])]*3)   # only a goal and a rule's head name the window that ended on day 9: every tick states the moment alone, and the goal holds on days 10 and 50
        e=State.from_packs([P('e',goals=['until:3'],methods=[M('open@1','until:3')],providers={'prov':3},grants=['g'])]);ke=Kernel(e);seen=[]
        for now,execute in ((6,False),(7,False),(8,False),(9,True),(10,True)):
            t=c.tick(ke,now,execute=execute);seen.append((brief(t['runs'][0]),[(r['predicate'],r['truth']) for r in t['clock_pack']['evidence']],e.fact('until:3')['truth'],e.fact('until:3').get('source')))
        offered=(('PLAN_READY',['open@1'],0,[]),[('now','TRUE')],'UNKNOWN',None)   # only a goal and a step's effect name the window that ended on day 3: the step is offered on days 6, 7 and 8 and runs on day 9;
        self.assertEqual(seen,[offered]*3+[(('LOCAL_MODEL_EFFECTS_RECORDED',['open@1'],1,[]),[('now','TRUE')],'TRUE','LOCAL_MODEL:open@1'),(('REFUSED',[],0,['REFUSED']),[('now','TRUE'),('until:3','FALSE')],'FALSE',c.SOURCE)])   # only then is a row of that name stored, and the tick of day 10 states the clock's decision
        p=State.from_packs([P('p',goals=['offer_open'],rules=[{'id':'R-P@1','head':'offer_open','branches':[['until:3']],'approved':False}])]);kp=Kernel(p)   # a rule that is only proposed puts no window in use
        self.assertEqual((c.windows(p),[r['predicate'] for r in c.tick(kp,2)['clock_pack']['evidence']],list(p.rules),list(p.proposed_rules)),([],['now'],[],['offer_open']))
    def test_confirm_a_crowd_is_stated_again_at_every_new_moment_one_pack_at_a_time(self):
        """Refuter 1, C5 and limit 8: the cost. A row that names more windows than one pack carries does not stop the clock, and it is paid for at every later moment: each new moment
        states all the packs again, each pack is applied by itself through the kernel's door (which works on a copy of the whole State), and each stays on the record of packs and in
        the provenance of every later run. Pinned here at seventy names, two packs a moment. The seconds the review measured at 7,689 and at 19,990 names are pinned by nothing."""
        s=State.from_packs([P('w',goals=['done'],methods=[M('do@1','done')],providers={'prov':9},grants=['g'],evidence=[row('fleet','TRUE','1',depends_on=[{'predicate':f'until:{n}','version':'window'} for n in range(100,170)])])]);k=Kernel(s)
        applied=[];door=State.apply;seen=[]
        def counted(state,p):applied.append(p['id']);return door(state,p)
        State.apply=counted   # every pack that goes through the door while the ticks are made
        try:
            for now in (1,2,2,3,4,5):
                n=len(applied);t=c.tick(k,now);seen.append((now,applied[n:],len(s.loaded),len(t['runs'][0]['provenance'])))
        finally:State.apply=door
        self.assertEqual(seen,[(1,['clock@1','clock@1.1'],3,3),(2,['clock@2','clock@2.1'],5,5),(2,[],5,5),(3,['clock@3','clock@3.1'],7,7),(4,['clock@4','clock@4.1'],9,9),(5,['clock@5','clock@5.1'],11,11)])
    def test_confirm_a_revoke_line_past_the_door_refuses_the_tick_whatever_the_bound_of_the_door(self):
        """Both refuters, limit 8. The bound is the kernel's door's, not the adapter's, so it is found here by probing and not written down: the size of a revoke list is doubled until
        a pack that carries it is refused. A tick that must take away that many grants at once is refused whole and the State's clock stands still; a revoke line the door takes goes
        through. (test_stated_limits shows the same with a count written for the door as it is today: a kernel version that moves the door has to edit that test.)"""
        def taken(n):
            try:State().apply(P('probe',revoke_grants=['g']*n));return True
            except ValueError:return False
        size=1
        while size<2**24 and taken(size*2):size*=2   # the largest power of two the door takes in one list of names
        self.assertEqual((size>=32,taken(size),taken(size*2)),(True,True,False))
        boxes=lambda a,b:[x for j in range(a,b) for x in (f'grant-{j}',c.box(f'grant-{j}',0))];per=size//2   # grants whose boxes all ended at moment 0, `per` of them in a pack: `size` names, which the door takes
        many=State.from_packs([P(f'g{i}',grants=boxes(i*per,(i+1)*per)) for i in range(4)]);was=books(many)   # four such packs: twice `size` grants to take away at the first tick
        self.assertEqual((len(many.grants),len(c.clock_packs(many,1)[0]['revoke_grants'])),(4*size,2*size))
        with self.assertRaises(ValueError):c.tick(Kernel(many),1)
        self.assertEqual((books(many),c.moment(many)),(was,None))   # refused whole: nothing changed, and that State has no moment
        fits=State.from_packs([P('g',grants=boxes(0,per//2))]);t=c.tick(Kernel(fits),1)   # a quarter of `size` grants: one revoke line, and the tick goes through
        self.assertEqual((len(t['clock_pack']['revoke_grants']),len(fits.grants),c.moment(fits)),(per//2,per//2,1))
    def test_confirm_the_checks_hold_only_while_the_kernel_makes_what_the_books_of_the_check_make(self):
        """Refuter 1, how S110 is held. The check module writes the kernel's and the adapter's rules for the built-in kind a second time, trace line for trace line and stored row for
        stored row. So a kernel that words one line of a run's trace otherwise, or a State that stores a row with one key more, makes a walk the books do not make: S110 fails, and
        S119 with it, until the check module (an added file, listed by its sha256) is edited too. Shown on the walk `late_order`, made here three times by the scene's own code."""
        ns=check_module();v=verifier();data=record();base=ns['world'](ROOT,v.sha);walks=data['scenes']['clock']['walks'];S110,S119=ns['IDS'][0],ns['IDS'][9];sc={}
        exec(compile((ROOT/'tools'/'scenes'/'clock.py').read_text(),'clock scene','exec'),sc);spec=[w for w in sc['walks'](c) if w[0]=='late_order'][0]
        class OtherWords(Kernel):   # the last line of every run under another word
            def log(self,op,**d):super().log('END' if op=='TERMINAL' else op,**d)
        class OtherRows(State):   # every stored row with one key more
            def observe(self,r):
                stored=super().observe(r)
                if stored:self.evidence[self.key(r['predicate'],r.get('scope',self.scope))]['seen']=True
                return stored
        made=lambda S,K:plain(sc['walk'](c,{'State':S,'Kernel':K,'pack':pack,'digest':digest},*spec[1:]));under=lambda walk:dict(data,scenes=dict(data['scenes'],clock={'walks':dict(walks,late_order=walk)}))
        held=lambda walk:ns['claims'](under(walk),ROOT,v.sha,v.check_chain,made=base)[S110];run=lambda walk:walk['steps'][0]['result']['runs'][0]
        honest,words,rows=made(State,Kernel),made(State,OtherWords),made(OtherRows,Kernel)
        self.assertEqual((honest==walks['late_order']==base['walks']['late_order'],held(honest),words==honest,held(words),rows==honest,held(rows)),(True,True,False,False,False,False))
        self.assertEqual((run(words)['trace'][-1]['operation'],run(honest)['trace'][-1]['operation'],brief(run(words))==brief(run(honest))==brief(run(rows)),run(rows)['trace']==run(honest)['trace'],rows['steps'][0]['after']['stored']['customer_approved'].get('seen')),
                         ('END','TERMINAL',True,True,True))   # the same run in another word, and the same trace over rows of another shape
        got={cid:ok for cid,ok,detail in ns['checks'](under(words),ROOT,v.sha,v.check_chain)};self.assertEqual((got[S110],got[S119]),(False,False))   # the module's own rows on such a record: the tenth fails with the first (no forgery is run on a record that does not pass)
    def test_confirm_the_reflection_lens_counts_two_more_runs_of_the_shipping_step(self):
        """Refuter 2, the one number the passage states about the record that no check holds (check S202 leaves the reflection summary out by design, and the clock's checks do not read
        it). Held here: the lens the record keeps is the lens over all recorded cases, and without this version's four cases it counts two runs of ship-replacement@1 fewer, the two
        that ship (cases 67a and 68)."""
        from extensions.reflection import reflect
        data=record();mine=set(check_module()['CASES']);runs=lambda cases:[x['outcome'] for x in cases if x['outcome']];rest=[x for x in data['cases'] if x['id'] not in mine]
        support=lambda lens:{p['signature']:p['support'] for p in lens['candidates'] if p['kind']=='COMPRESSION_CANDIDATE'}.get('ship-replacement@1',0)
        self.assertEqual((data['meta_extensions']['reflection']==plain(reflect(runs(data['cases']))),support(data['meta_extensions']['reflection'])-support(reflect(runs(rest))),sorted(x['id'] for x in data['cases'] if x['id'] in mine and x['outcome']['actions']==['ship-replacement@1'])),
                         (True,2,['67a_order_in_time','68_allowance']))
    def test_confirm_s118_folds_the_kernels_letters_as_lower_does(self):
        """Refuter 2, C11. S118 and test_c11 fold the kernel's text with str.lower(), which folds every ASCII letter case and not every cased form: a capital I with a dot above lowers
        to an i with a combining dot, and a long s is a small letter already. A kernel that carried the adapter's words in such letters passes S118; the same line in ASCII capitals
        is refused. It needs the kernel file, its pin and the record changed together."""
        ns=check_module();v=verifier();data=record();book=json.loads((ROOT/'added.json').read_text());S118=ns['IDS'][8]
        def held(line):
            kernel=(ROOT/'kernel'/'core.py').read_text()+line;h=hashlib.sha256(kernel.encode()).hexdigest();pinned=dict(book,pinned=dict(book['pinned'],kernel_sha256=h))
            return ns['claims'](dict(data,kernel_sha256=h),ROOT,v.sha,v.check_chain,{'kernel/core.py':kernel,'added.json':json.dumps(pinned)})[S118]
        dotted,long_s,dot=chr(0x130),chr(0x17f),chr(0x307);tick,as_of='T'+dotted+'CK','A'+long_s+'_OF'   # a capital I with a dot above, a long s, a combining dot above: written by number, so this file holds no such letter
        self.assertEqual((held('# '+tick+' and '+as_of+'\n'),held('# TICK and AS_OF\n'),held('# nothing of the kind\n')),(True,False,True))
        self.assertEqual((tick.lower(),as_of.lower(),'tick' in tick.lower(),'as_of' in as_of.lower(),as_of.casefold()),('ti'+dot+'ck','a'+long_s+'_of',False,False,'as_of'))
    def test_confirm_one_assertion_for_each_edit_of_the_code_that_survived_the_tests(self):
        """Refuter 2. Fourteen one-line edits of the adapter and of this version's pack file changed what the code does and passed every clock test, with every scenario file and the
        recorded sequence made again to the same bytes, so no independent check can see them. One assertion for each, numbered as the finding lists them (its item 10 is two edits).
        These clauses rest on this unit test alone."""
        # (1) something new at a moment already stated, when the rows are cut (C9): the later packs are read too, and the new window is published in packs with names of their own
        s=State.from_packs([P('w',evidence=[c.timed(row(f'f{i}','TRUE','1'),100+i) for i in range(70)])]);k=Kernel(s);first=c.tick(k,4);k.on_event(c.timed(row('late','TRUE','1'),500));before=s.fact('late')['truth'];t=c.tick(k,4)
        self.assertEqual(([first['clock_pack']['id']]+[p['id'] for p in first['more_clock_packs']],before,t.get('clock_pack',{}).get('id'),[p['id'] for p in t.get('more_clock_packs',[])],s.fact('late')['truth'],'clock_pack' in c.tick(k,4)),
                         (['clock@4','clock@4.1'],'UNKNOWN','clock@4.2',['clock@4.3'],'TRUE',False))
        # (2) the budget line goes with the first pack, like the revoke line
        s=State.from_packs([P('g',budget={'pulls':0},preference=['compute','money','attention','pulls'],grants=[c.allowance('pulls',2,1)],evidence=[c.timed(row(f'f{i}','TRUE','1'),i+5) for i in range(c.ROWS)])]);both=c.clock_packs(s,3)
        self.assertEqual((len(both),both[0].get('budget'),'budget' in both[1]),(2,{'pulls':2},False))
        # (3) a row whose predicate holds the bar that parts a scope from a name does not stop the clock (C5)
        s,k=world();c.tick(k,2,execute=True);ev=k.on_event(c.timed(row('a|b','TRUE','1'),9));t=c.tick(k,4,execute=True)
        self.assertEqual((ev['status'],c.scopes(s),c.moment(s),s.fact('customer_approved')['truth'],s.fact('a|b')['truth'],[r['predicate'] for r in t['clock_pack']['evidence']]),('RECONCILED',['orgA/fulfillment'],4,'UNKNOWN','TRUE',['now','until:3','until:5','until:9']))
        # (4) a window that a rule names in a later alternative is in use (limit 2)
        r=State.from_packs([P('r',goals=['offer_open'],rules=[{'id':'R-TWO@1','head':'offer_open','branches':[['never'],['approved','until:3']],'approved':True}],evidence=[row('approved','TRUE','1')])]);kr=Kernel(r)
        self.assertEqual((c.windows(r),brief(kr.run_standing()['runs'][0]),brief(c.tick(kr,2)['runs'][0]),brief(c.tick(kr,4)['runs'][0])),(['until:3'],('QUERY_EVIDENCE',[],0,['QUERY_EVIDENCE']),('PLAN_READY',[],0,[]),('REFUSED',[],0,['QUERY_EVIDENCE','REFUSED'])))
        # (5) and so is a window that only a step that is not approved requires (limit 2)
        u=State.from_packs([P('u',goals=['shipped'],methods=[dict(M('ship@1','shipped',req=['until:3']),approved=False)],providers={'prov':1},grants=['g'])])
        self.assertEqual((c.windows(u),[x['predicate'] for x in c.tick(Kernel(u),2)['clock_pack']['evidence']],u.fact('until:3')['truth']),(['until:3'],['now','until:3'],'TRUE'))
        # (6) exactly ROWS rows are one pack in the usual order, the moment first, also when windows have closed: what closes is stated first only when the rows are cut
        small=State.from_packs([P('small',evidence=[c.timed(row(f'f{i}','TRUE','1'),i) for i in range(c.ROWS-1)])]);six=c.clock_packs(small,3)
        self.assertEqual((len(six),len(six[0]['evidence']),[(x['predicate'],x['truth']) for x in six[0]['evidence'][:5]]),(1,c.ROWS,[('now','TRUE'),('until:0','FALSE'),('until:1','FALSE'),('until:2','FALSE'),('until:3','TRUE')]))
        # (7) under a cut what closes is stated first across all scopes, not scope by scope
        two=State.from_packs([P('one',scope='orgA/one',evidence=[c.timed(row(f'f{i}','TRUE','1'),i) for i in range(40)]),P('two',scope='orgA/two',evidence=[c.timed(row(f'h{i}','TRUE','1'),i) for i in range(40)])]);cut=c.clock_packs(two,2)
        self.assertEqual((c.scopes(two),[len(p['evidence']) for p in cut],[(x['scope'],x['predicate'],x['truth']) for x in cut[0]['evidence'][:6]]),
                         (['orgA/two','orgA/one'],[c.ROWS,18],[('orgA/two','until:0','FALSE'),('orgA/two','until:1','FALSE'),('orgA/one','until:0','FALSE'),('orgA/one','until:1','FALSE'),('orgA/two','now','TRUE'),('orgA/two','until:2','TRUE')]))
        # (8) what is stored is compared as JSON text: a `now` row written by hand with 2.0 for 2 equals the clock's row for Python and is not that row, so the next tick states it again
        s,k=world();c.tick(k,2);ev=k.on_event({'predicate':'now','truth':'TRUE','verified':True,'final':True,'source':c.SOURCE,'version':2.0,'at':2.0,'scope':s.scope});same=s.evidence[s.key('now')]==c.clock_pack(s,2)['evidence'][0];t=c.tick(k,2)
        self.assertEqual((ev['status'],same,t.get('clock_pack',{}).get('id'),json.dumps(s.fact('now')['at']),json.dumps(s.fact('now')['version']),'clock_pack' in c.tick(k,2)),('RECONCILED',True,'clock@2.1','2','2',False))
        # (9) a timed row names its window after what the row rested on already
        self.assertEqual((c.timed(row('p','TRUE','1',depends_on=[{'predicate':'q','version':'1'}]),3)['depends_on'],c.timed(c.timed(row('p','TRUE','1'),8),3)['depends_on']),
                         ([{'predicate':'q','version':'1'},{'predicate':'until:3','version':'window'}],[{'predicate':'until:8','version':'window'},{'predicate':'until:3','version':'window'}]))
        # (10) two edits: of two things wrong a tick names `execute` first, then the moment (not whole, then earlier), then the label, each in its fixed words
        s,k=world();c.tick(k,4);said=[]
        for now,how in ((-1,{'execute':'yes'}),(5,{'execute':1,'label':7}),(2.5,{'label':5}),(-1,{'label':'x clock@1'}),(3,{'label':5}),(3,{'label':'x clock@1'})):
            with self.assertRaises(ValueError) as refused:c.tick(k,now,**how)
            said.append(str(refused.exception))
        self.assertEqual(said,['A tick is made on a kernel, and execute is true or false']*2+['A moment is a whole number that is not negative']*2+['Time does not go back: the moment is 4']*2)
        # (11) a window has the moment's own upper bound
        for bad in (lambda:c.window(10**18),lambda:c.timed(row('p','TRUE','1'),10**18),lambda:c.due('g',10**18)):
            with self.assertRaises(ValueError):bad()
        self.assertEqual((c.window(10**18-1),c.closes('until:'+str(10**18-1)),c.closes('until:'+str(10**18))),('until:999999999999999999',10**18-1,None))
        # (12), (13) this version's own pack file (tools/packs/clock.py), its three functions run here on names of their own: a grant named like a box that is none stops the build,
        # and so do two walks that state another pack under one name
        tree=ast.parse((ROOT/'tools'/'packs'/'clock.py').read_text());three=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_pack','_read','chain')],type_ignores=[])
        authored=[];ns={'misnamed':c.misnamed,'tick':c.tick,'State':State,'Kernel':Kernel,'json':json,'_OWN':{},'_FILES':ROOT/'scenarios','pack':lambda name,**fields:authored.append(name)}
        exec(compile(three,'the pack file of the clock, three functions','exec'),ns);self.assertEqual(sorted(n.name for n in three.body),['_pack','_read','chain'])
        ns['_pack']('170_plain',grants=['g',c.box('g',15),c.allowance('pulls',2,1)])
        with self.assertRaisesRegex(ValueError,r"REFUSED tools/packs/clock\.py: 170_odd names \['box:015:g'\], which is no box and no allowance"):ns['_pack']('170_odd',grants=['g','box:015:g'])
        self.assertEqual((authored,sorted(ns['_OWN'])),(['170_plain'],['170_plain']))   # the refused pack is not authored
        ns['_pack']('170_a',evidence=[c.timed(row('p','TRUE','1'),3)]);ns['_pack']('170_b',evidence=[c.timed(row('p','TRUE','1'),4)]);ns['chain']('170_',['170_a'],2);ns['chain']('170_',['170_a'],2)   # the same walk twice states the same pack: nothing to refuse
        with self.assertRaisesRegex(ValueError,r'REFUSED tools/packs/clock\.py: two walks state another pack under the name 170_clock@2'):ns['chain']('170_',['170_b'],2)
        self.assertEqual(authored,['170_plain','170_a','170_b','170_clock@2'])


if __name__=='__main__':unittest.main()
