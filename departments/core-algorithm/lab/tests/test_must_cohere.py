"""Case 50, must-cohere (matrix row R55, 0.10.0): what the case records (claims C1 to C3), the limits of it (a to f), and its two independent checks.
The checks are run here on the built record (results/actual_run_records.json), so these tests run after tools/run_all.py and tools/make_extra.py."""
from pathlib import Path
import unittest, sys, json, importlib.util
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel
from tools.run_all import CASES,pack,scenario

PACKS=['00_goal','01_domain','100_delivered_but_open']
GOAL,SCOPE='order_complete','orgA/fulfillment'
OPS=[('GOAL_ACCEPTED',None),('REFINE','order_complete'),('RETAIN','original_delivered'),('METHOD_ABSENT','replacement_delivered'),('EVIDENCE_CONFLICT','order_complete'),('BLOCK',None),('TERMINAL',None)]

def verifier():
    """The independent verifier, loaded from its file (it is a script, not a package)."""
    spec=importlib.util.spec_from_file_location('independent_verify_for_must_cohere',ROOT/'qa'/'independent_verify.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def module():
    """The check module, loaded the way the verifier loads it: from its text."""
    ns={'__name__':'qa_checks_must_cohere'};exec(compile((ROOT/'qa'/'checks'/'must_cohere.py').read_text(),'qa/checks/must_cohere.py','exec'),ns);return ns
world=lambda *more:State.from_packs([pack(n) for n in PACKS]+list(more))
row=lambda p,t,**kw:{'schema':'sutra-extension/2','id':'t-'+p,'evidence':[dict({'predicate':p,'truth':t,'verified':True,'source':'fixture/test','version':'9'},**kw)]}
step=lambda i,e:{'id':i,'effect':e,'provider':'p','grant':'g','cost':{'compute':1},'action':'simulate_fact'}
more=lambda **k:dict({'schema':'sutra-extension/2','id':'t-more','providers':{'p':5},'grants':['g']},**k)
look=lambda s,execute=True:[(r['status'],r['actions'],r['stop_reasons'],s.budget['compute']) for r in Kernel(s).run_standing(execute=execute)['runs']]


class MustCohereTests(unittest.TestCase):
    def test_c1_c2_a_verified_false_goal_under_a_branch_that_evidence_closes_is_named_as_a_conflict(self):
        spec=[c for c in CASES if c[0]=='50_must_cohere'][0];self.assertEqual((spec[3],spec[4],spec[5]),(PACKS,True,'Evidence'))
        s=world();before=(dict(s.budget),dict(s.providers),json.dumps(s.evidence,sort_keys=True));r=Kernel(s).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'],r['work_state'],r['goal'],r['goal_truth_before'],r['actions'],r['needs'],r['model_receipts'],r['cost'],r['selected_branch'],r['stop_reasons']),
                         ('EVIDENCE_CONFLICT','blocked',GOAL,'FALSE',[],[],[],None,None,['EVIDENCE_CONFLICT','METHOD_ABSENT']))                                   # C1
        self.assertEqual([(e['operation'],e['data'].get('predicate')) for e in r['trace']],OPS)                                                                   # C2: in this order
        self.assertEqual([e['data'] for e in r['trace'] if e['operation'] in ('REFINE','RETAIN')],[{'predicate':GOAL,'rule':'R-ORDER@1','alternatives':2},{'predicate':'original_delivered','source':'fixture/courier-scan','version':'2'}])
        self.assertEqual((dict(s.budget),dict(s.providers),json.dumps(s.evidence,sort_keys=True)),before)                                                         # nothing was paid and no row was written
        self.assertEqual((s.fact(GOAL)['truth'],s.fact(GOAL)['source'],s.fact('original_delivered')['truth'],s.fact('replacement_delivered')['truth']),('FALSE','fixture/order-desk','TRUE','FALSE'))   # ONE part reads TRUE
        # Limit (f): the case holds no method, so its executed look is its dry look. That nothing is paid is true here and shows nothing about paying.
        self.assertEqual(s.methods,{});self.assertTrue(Kernel(world()).run_standing(execute=True)==Kernel(world()).run_standing(execute=False))
    def test_c3_the_books_of_the_case_are_what_its_pack_files_leave(self):
        m=module();spec=[c for c in CASES if c[0]=='50_must_cohere'][0];case=json.loads(json.dumps(scenario(spec)));packs=[pack(n) for n in PACKS];v=verifier()
        self.assertEqual(m['tests'](case,packs,v.sha,v.check_chain),{name:True for name in ('status','nothing_ran','reasons','order','chain','refined','retained','named','pack','rows','budget','journal','place')})   # the case made here, in memory, held by every test of the check module
        facts=case['derived_state']['facts'];self.assertEqual((list(facts),facts),(list(m['left_by'](packs)),m['left_by'](packs)))
        self.assertEqual((facts[SCOPE+'|order_complete'],facts[SCOPE+'|original_delivered']),(dict(m['DESK'],scope=SCOPE),dict(m['SCAN'],scope=SCOPE)))           # both rows whole, as their pack file wrote them
        self.assertEqual((list(facts)[0],list(facts)[-1],len(facts)),(SCOPE+'|original_delivered',SCOPE+'|order_complete',6))                                    # the scan stands where the row it replaced stood
        self.assertEqual((case['derived_state']['budget_after'],len(case['derived_state']['historical_events'])),({'compute':10,'money':10,'attention':3},1))
    def test_the_limits_of_what_the_case_shows(self):
        whole=lambda head,parts='FALSE',**k:more(goals=['whole'],rules=[{'id':'R','head':'whole','branches':[['a','b']],'approved':True}],evidence=[row('whole',head)['evidence'][0],row('a',parts)['evidence'][0],row('b',parts)['evidence'][0]],**k)
        # (a) the conflict is named on any fact whose rule has a branch that closes on evidence; below a goal it blocks that goal only while no other branch offers a plan
        below=lambda *branches,**k:world(more(goals=['closed'],rules=[{'id':'R2','head':'closed','branches':[['order_complete']]+list(branches),'approved':True}],**k))
        self.assertEqual(look(below()),[('EVIDENCE_CONFLICT',[],['EVIDENCE_CONFLICT','METHOD_ABSENT'],10)])
        # (b) under an OR the conflicted fact is planned around: the other branch is taken and paid for, and no stop reason says so
        self.assertEqual(look(below(['by_hand'],methods=[step('by-hand','by_hand')])),[('LOCAL_MODEL_EFFECTS_RECORDED',['by-hand'],[],9)])
        # (c) one direction only: a head that reads TRUE over parts that all read FALSE is supported by evidence
        self.assertEqual(look(State.from_packs([whole('TRUE')])),[('SUPPORTED_BY_EVIDENCE',[],[],10)])
        # (d) the last verified row wins: with the packs loaded as 00, 100, 01 the older FALSE row replaces the scan
        s=State.from_packs([pack(n) for n in ('00_goal','100_delivered_but_open','01_domain')])
        self.assertEqual((look(s),s.fact('original_delivered')['truth'],s.fact('original_delivered')['version']),([('METHOD_ABSENT',[],['METHOD_ABSENT'],10)],'FALSE','1'))
        # (e) two steps make the two parts of a whole whose verified row says FALSE: both run and are paid, and the conflict is named one look later, for good
        s=State.from_packs([whole('FALSE',methods=[step('make-a','a'),step('make-b','b')])])
        self.assertEqual((look(s),look(s),look(s)),([('LOCAL_MODEL_EFFECTS_RECORDED',['make-a','make-b'],[],8)],[('EVIDENCE_CONFLICT',[],['EVIDENCE_CONFLICT'],8)],[('EVIDENCE_CONFLICT',[],['EVIDENCE_CONFLICT'],8)]))
        # what is no conflict: the part no longer known; the row on the head withdrawn, or unverified; a decision on the head (that is a refusal)
        self.assertEqual(look(world(row('original_delivered','UNKNOWN'))),[('QUERY_EVIDENCE',[],['METHOD_ABSENT','QUERY_EVIDENCE'],10)])
        self.assertEqual((look(world(row('order_complete','UNKNOWN'))),look(world(row('order_complete','UNKNOWN')),False)),([('SUPPORTED_BY_EVIDENCE',[],[],10)],[('PLAN_READY',[],[],10)]))
        self.assertEqual(look(State.from_packs([pack('00_goal'),pack('01_domain'),row('original_delivered','TRUE'),row('order_complete','FALSE',verified=False)])),[('SUPPORTED_BY_EVIDENCE',[],[],10)])
        self.assertEqual(look(world(row('order_complete','FALSE',final=True,source='owner'))),[('REFUSED',[],['REFUSED'],10)])
    def test_the_checks_hold_the_stored_rows_whole_and_every_test_refuses_a_forgery_of_its_own(self):
        m=module();v=verifier();data=json.loads((ROOT/'results'/'actual_run_records.json').read_text());S210,S211=m['IDS']
        run=lambda d:m['checks'](d,ROOT,v.sha,v.check_chain);case=lambda d:[c for c in d['cases'] if c['id']=='50_must_cohere'][0];facts=lambda d:case(d)['derived_state']['facts']
        def forged(change):
            d=json.loads(json.dumps(data));change(d);return run(d)
        self.assertEqual((run(data),S210[:5],S211[:5]),([(S210,True,''),(S211,True,'')],'S210_','S211_'))
        # the forgery of the review: the head's row said to be unverified, a decision and of another version, the scan of version 1, the other part TRUE. Every stored row is compared whole with its pack file.
        review=lambda d:(facts(d)[SCOPE+'|order_complete'].update(verified=False,final=True,version='7'),facts(d)[SCOPE+'|original_delivered'].update(version='1'),facts(d)[SCOPE+'|replacement_delivered'].update(truth='TRUE'))
        self.assertEqual(forged(review)[0],(S210,False,'rows'))
        for name,change in (('status',lambda d:case(d)['outcome'].update(status='PLAN_READY')),('nothing_ran',lambda d:case(d)['outcome'].update(actions=['ship-original@1'])),
                            ('rows',lambda d:facts(d).pop(SCOPE+'|customer_notified')),('budget',lambda d:case(d)['derived_state']['budget_after'].update(compute=10.0)),
                            ('chain named order',lambda d:case(d)['outcome']['trace'].pop(3)),('journal',lambda d:case(d)['derived_state']['historical_events'].clear()),('place',lambda d:case(d).update(scope='orgB/fulfillment'))):
            got=forged(change);self.assertEqual((got[0],got[1][:2]),((S210,False,name),(S211,False)),name)   # S211 shows forgeries on an honest record only
        # a record the checks cannot read is two failed rows, not an error that ends the verifier
        for what,change in (('the case taken out',lambda d:d['cases'].remove(case(d))),('the case without its run',lambda d:case(d).update(outcome=None)),('the cases gone',lambda d:d.pop('cases'))):
            got=forged(change);self.assertEqual(([g[0] for g in got],[g[1] for g in got],all(type(g[2]) is str for g in got)),([S210,S211],[False,False],True),what)
        # every test of the module has a forgery of its own, and each forgery is refused by the test it is listed for and by no other
        seen={};names=sorted(m['tests'](case(data),[pack(n) for n in PACKS],v.sha,v.check_chain))
        for target,change in m['FORGERIES']:
            c,p=json.loads(json.dumps(case(data))),[pack(n) for n in PACKS];change(c,p,v.sha)
            self.assertEqual(sorted(k for k,ok in m['tests'](c,p,v.sha,v.check_chain).items() if not ok),[target],target);seen[target]=seen.get(target,0)+1
        self.assertEqual((sorted(seen),len(names),len(m['FORGERIES'])>=26,seen['named']),(names,13,True,3))   # also the two rows that name the conflict and the missing method are held whole
        # S211 itself: a forgery that changes nothing is accepted, one that two tests refuse is not its own test's alone, a test without a forgery is bare. S211 fails on each.
        for what,forgeries in (('accepted',m['FORGERIES']+[('status',lambda c,p,sha:None)]),('refused by two tests',m['FORGERIES']+[('chain',lambda c,p,sha:c['outcome']['trace'].pop(3))]),
                               ('a test without a forgery',[f for f in m['FORGERIES'] if f[0]!='pack'])):
            got=with_forgeries(forgeries,data,v);self.assertEqual(([r[1] for r in got],got[1][2]!=''),([True,False],True),what)
    def test_the_verifier_runs_the_two_checks(self):
        v=verifier();data=json.loads((ROOT/'results'/'actual_run_records.json').read_text());rows={t['id']:t for t in v.inspect(data)['checks']}
        self.assertEqual([(rows[i]['pass'],rows[i]['detail']) for i in module()['IDS']],[(True,''),(True,'')])   # the two rows of this version; what other versions' rows say is theirs to test


def with_forgeries(forgeries,data,v):
    """checks() of the module, run with another list of forgeries in the module's own names."""
    ns=module();ns['FORGERIES']=forgeries;return ns['checks'](data,ROOT,v.sha,v.check_chain)


if __name__=='__main__':unittest.main()
