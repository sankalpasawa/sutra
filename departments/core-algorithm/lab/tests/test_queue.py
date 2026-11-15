"""0.17.0-queue: rank a queue by impact (matrix row R31b), the decision-provenance row (R91), problem styles (R101).
The kernel is not touched: two extensions (queue_rank, queue_provenance), ten packs (130 to 139), three cases (57 to 59)."""
from pathlib import Path
import unittest, sys, json, copy, importlib.util, ast
from collections import Counter
import re
def ours(cid, low, high):   # a check of the base (built in; the add-on base and its first case) or of this version: in a lab where other versions are laid, their checks stand beside these and may refuse the same forged record
    n = int(re.match(r'S(\d+)', cid).group(1)); return n != 202 and (n < 60 or 200 <= n <= 219 or low <= n <= high)   # S202, the pin of what earlier versions recorded, is left out: once a later version has pinned this version's record, a forged copy of it fails that pin, as it should
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest,plain,ACTIONS
from tools.run_all import pack,CASES   # importing run_all also registers the action kinds the packs use (ask)
from extensions.asks import answer,open_asks
from extensions.reflection import Learner
from extensions.queue_rank import impacts,ranking,rank
from extensions.queue_provenance import books,decisions,FIELDS,VERSION,BOUND,UNEXPLAINED,BROKEN,NOT_KERNEL,NOT_DATA,TOO_LARGE


def state(*names):return State.from_packs([pack(n) for n in names])
def whole(s):   # everything a State holds as data, as one digest
    return digest({'scope':s.scope,'goals':s.goals,'evidence':s.evidence,'rules':s.rules,'proposed':s.proposed_rules,'methods':s.methods,'providers':s.providers,
                   'grants':sorted(s.grants),'budget':s.budget,'preference':s.preference,'constructors':s.constructor_specs,'candidates':s.candidates,
                   'loaded':s.loaded,'journal':s.event_journal,'work':s.active_work})
def rest(s):    # the same without the queue and the list of packs: what a ranking must leave alone
    return digest({'scope':s.scope,'evidence':s.evidence,'rules':s.rules,'proposed':s.proposed_rules,'methods':s.methods,'providers':s.providers,'grants':sorted(s.grants),
                   'budget':s.budget,'preference':s.preference,'constructors':s.constructor_specs,'candidates':s.candidates,'journal':s.event_journal,'work':s.active_work})
def P(**fields):return dict({'schema':'sutra-extension/2'},**fields)
def R(head,impact,n=1,**more):return dict({'id':f'R-{head}@{n}','head':head,'branches':[[head+'_done']],'approved':True,'impact':impact},**more)
def record():return json.loads((ROOT/'results'/'actual_run_records.json').read_text())   # what tools/run_all.py wrote before the tests ran
def roots(result):return [r['trace_root_sha256'] for r in result['runs']]
def verifier():
    spec=importlib.util.spec_from_file_location('independent_verify_for_queue',ROOT/'qa'/'independent_verify.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def refusal(test,call,message=None):   # the call is refused with ValueError (and, when given, with exactly this message)
    with test.assertRaises(ValueError) as refused:call()
    if message is not None:test.assertEqual(str(refused.exception),message)

QUEUE,RANKED='130_collections_queue','131_queue_ranked'
L41,L42,L43,L44=('loan_%d_promise'%n for n in (1041,1042,1043,1044))


class QueueRankTests(unittest.TestCase):
    """R31b. The order of the queue is the only thing a ranking changes; what the order then does is the kernel's."""
    def _ranked(self):
        s=state(QUEUE);rank(s,RANKED);return s
    def test_the_queue_is_ranked_by_the_impact_each_goals_rule_declares_and_nothing_else_changes(self):
        s=state(QUEUE);left=rest(s);before=whole(s)
        self.assertEqual(impacts(s),[{'goal':L41,'impact':2,'rule':'R-PROMISE-1041@1'},{'goal':L42,'impact':9,'rule':'R-PROMISE-1042@1'},
                                     {'goal':L43,'impact':5,'rule':'R-PROMISE-1043@1'},{'goal':L44,'impact':5,'rule':'R-PROMISE-1044@1'}])
        kept=ranking(s,RANKED);self.assertEqual(whole(s),before)                      # looking at the ranking changes nothing
        self.assertEqual(kept['goals'],[L42,L43,L44,L41])                             # 9, then the two fives in the order the queue listed them, then 2
        self.assertEqual(rank(s,RANKED),kept)
        self.assertEqual((s.goals,rest(s)),([L42,L43,L44,L41],left))                  # the queue is in the new order; everything else is as it was
    def test_the_ranking_is_kept_as_a_pack_that_every_later_run_names_and_ranking_twice_adds_nothing(self):
        s=state(QUEUE);kept=rank(s,RANKED)
        self.assertEqual(set(kept),{'schema','id','goals','ranked_by'})               # the order and its reasons: nothing the planner or the gate reads
        self.assertEqual(kept['ranked_by'][0],{'goal':L42,'impact':9,'rule':'R-PROMISE-1042@1'})
        self.assertEqual(kept,pack(RANKED))                                           # the scenario file (worked out by the authoring code from the rules) is the very pack the extension makes
        named=[{'pack':QUEUE,'sha256':digest(pack(QUEUE))},{'pack':RANKED,'sha256':digest(kept)}]
        self.assertEqual(s.loaded,named)
        for run in Kernel(s).run_standing()['runs']:self.assertEqual(run['provenance'],named)
        self.assertEqual(roots(Kernel(state(QUEUE,RANKED)).run_standing(execute=True)),roots(Kernel(self._ranked()).run_standing(execute=True)))   # the two scenario files build the State a live ranking leaves
        s=self._ranked();once=whole(s)
        self.assertEqual((rank(s,RANKED),whole(s)),(pack(RANKED),once))               # ranked again: the same ranking comes back and nothing is applied, not even to the list of packs
        rank(s,'another-name');self.assertEqual([p['pack'] for p in s.loaded],[QUEUE,RANKED,'another-name'])       # under another name it is another pack
        rank(s,RANKED);self.assertEqual([p['pack'] for p in s.loaded],[QUEUE,RANKED,'another-name',RANKED])        # no longer the State's last pack: applied again
        s=self._ranked();s.goals=list(pack(QUEUE)['goals']);rank(s,RANKED)            # the queue was put back as listed behind the State's door: the ranking is applied again
        self.assertEqual((s.goals,[p['pack'] for p in s.loaded]),(pack(RANKED)['goals'],[QUEUE,RANKED,RANKED]))
    def test_equal_impacts_keep_their_queue_order_and_a_replacing_rule_brings_its_own_impact(self):
        s=State.from_packs([P(id='q',goals=['a','b','c','d'],rules=[R('a',1),R('b',7),R('c',7),R('d',0)])])
        self.assertEqual(ranking(s)['id'],'queue-ranked')
        rank(s);self.assertEqual((s.goals,s.loaded[-1]['pack']),(['b','c','a','d'],'queue-ranked'))   # unnamed, the ranking pack is called queue-ranked
        again=rank(s,'again');self.assertEqual((s.goals,again['goals']),(['b','c','a','d'],['b','c','a','d']))   # ranking a ranked queue keeps it
        s.apply(P(id='q2',rules=[R('a',8,2,replaces='R-a@1')]))                       # a reviewed replacement of a's rule declares another impact
        kept=rank(s,'third');self.assertEqual((s.goals,kept['ranked_by'][0]),(['a','b','c','d'],{'goal':'a','impact':8,'rule':'R-a@2'}))
        s.apply(P(id='owner',goals=['d','c','b','a']));self.assertEqual(s.goals,['d','c','b','a'])   # a person's own order is one more goals pack: it stands until the queue is ranked again
        rank(s,'fourth');self.assertEqual(s.goals,['a','c','b','d'])                  # and then the ties keep the order the person gave them
        empty=State();self.assertEqual((rank(empty)['goals'],empty.goals,Kernel(empty).run_standing()['status']),([],[],'NO_STANDING_GOAL'))   # an empty queue ranks to an empty queue
    def test_a_queue_with_an_undeclared_goal_is_refused_whole_and_the_state_is_as_it_was(self):
        good=R('a',3)
        cases={'no rule at all':[good],'a rule without an impact':[good,{k:v for k,v in R('b',1).items() if k!='impact'}],
               'a negative impact':[good,R('b',-1)],'true is not a number':[good,R('b',True)],'a fraction':[good,R('b',2.0)],'a text':[good,R('b','9')],'nothing':[good,R('b',None)],
               'an impact on a rule that is only proposed':[good,dict(R('b',9),approved=False)]}
        for why,rules in cases.items():
            s=State.from_packs([P(id='q',goals=['a','b'],rules=rules)]);before=whole(s)
            for call in (impacts,ranking,rank):refusal(self,lambda:call(s),'No declared impact for standing goal: b')
            self.assertEqual(whole(s),before,why)
            self.assertEqual(Kernel(s).run_standing()['goals'],['a','b'],why)         # the queue still runs, in the order it was listed
        s=State.from_packs([P(id='q',goals=['a','b'],rules=[good,R('b',1)])]);before=whole(s)
        for bad in ('',None,7,{'a'},object()):refusal(self,lambda:rank(s,bad))        # a name the State's own door refuses: nothing is applied
        self.assertEqual(whole(s),before)
        want=[(['00_goal'],'order_complete'),(['133_complaint_desk'],'complaint_8801_closed'),(['132_loan_desk'],'loan_7001_disbursed')]
        for names,first in want:                                                      # the three recorded refusals, each for another reason
            s=state(*names);before=whole(s)
            refusal(self,lambda:rank(s,'never-applied'),'No declared impact for standing goal: '+first)
            self.assertEqual(whole(s),before,first)
        self.assertNotIn('order_complete',state('00_goal').rules)                                    # a goal with no rule
        self.assertNotIn('impact',state('133_complaint_desk').rules['complaint_8801_closed'])        # a rule that declares no impact
        self.assertEqual(state('132_loan_desk').rules['loan_7001_disbursed']['impact'],'high')       # an impact that is a word
        self.assertEqual([(x['packs'],x['refused']) for x in record()['scenes']['queue_rank']['not_ranked']],[(n,'No declared impact for standing goal: '+g) for n,g in want])
    def test_the_order_decides_which_goals_get_a_budget_that_does_not_cover_all(self):
        s1,s2=state(QUEUE),state(QUEUE,RANKED);listed,ranked=Kernel(s1).run_standing(execute=True),Kernel(s2).run_standing(execute=True)
        called=lambda res:[r['goal'] for r in res['runs'] if [a for a in r['actions'] if a.startswith('call-')]]
        held=lambda res:[(r['goal'],r['status'],r['actions'],r['model_receipts']) for r in res['runs'] if r['work_state']=='blocked']
        self.assertEqual((called(listed),held(listed)),([L41,L42],[(L43,'RESOURCE_REQUIRED',[],[]),(L44,'RESOURCE_REQUIRED',[],[])]))   # as listed: the first two get the desk's two calls
        self.assertEqual((called(ranked),held(ranked)),([L42,L43],[(L44,'RESOURCE_REQUIRED',[],[])]))                                  # ranked: the two that matter most do
        worth={x['goal']:x['impact'] for x in pack(RANKED)['ranked_by']}
        self.assertEqual((sum(worth[g] for g in called(listed)),sum(worth[g] for g in called(ranked))),(11,14))
        for res in (listed,ranked):                                                   # each held goal was turned away by the gate on the attention line: one call asked for, none left
            for r in res['runs']:
                if r['work_state']!='blocked':continue
                gate=[e['data'] for e in r['trace'] if e['operation']=='ADMISSION']
                self.assertEqual([(x['accepted'],x['blockers'],x['cost']['attention']) for x in gate],[(False,['RESOURCE_REQUIRED'],1)])
        self.assertEqual((s1.budget,s2.budget),({'compute':8,'money':10,'attention':0},{'compute':7,'money':9,'attention':0}))
        s3=state(QUEUE);s3.apply(P(id='more',budget={'attention':4}));rank(s3)        # with attention for everyone the order decides nothing but the order
        self.assertEqual([(r['goal'],r['actions']) for r in Kernel(s3).run_standing(execute=True)['runs']],
                         [(L42,['call-1042@1']),(L43,['call-1043@1']),(L44,['call-1044@1']),(L41,['call-1041@1'])])
    def test_ranking_does_not_touch_how_a_goal_is_planned_but_changes_the_books_it_finds(self):
        s=state(QUEUE);kept=rank(s,RANKED);ranked=Kernel(s).run_standing(execute=True)
        k=Kernel(state(QUEUE,RANKED));by_hand=[k.resolve(g,execute=True) for g in kept['goals']]   # the kernel asked goal by goal, in the ranked order
        self.assertEqual(roots(ranked),[r['trace_root_sha256'] for r in by_hand])     # the ranked look is exactly those runs: same hash chains
        listed=Kernel(state(QUEUE)).run_standing(execute=True)
        pick=lambda res:[(r['actions'],r['cost'],r['pareto_options'],r['selected_branch']) for r in res['runs'] if r['goal']==L41][0]
        gate=lambda res:[(e['data']['methods'],e['data']['accepted'],e['data']['blockers']) for r in res['runs'] if r['goal']==L41 for e in r['trace'] if e['operation']=='ADMISSION'][:2]
        self.assertEqual(pick(listed),(['call-1041@1'],{'compute':1,'money':0,'attention':1},2,'R-PROMISE-1041@1/OR1'))    # first as listed: both routes are open and the kernel takes the call
        self.assertEqual(pick(ranked),(['write-1041@1'],{'compute':1,'money':1,'attention':0},1,'R-PROMISE-1041@1/OR2'))   # last when ranked: the same goal, the same rule, another route
        self.assertEqual((gate(listed),gate(ranked)),([(['call-1041@1'],True,[]),(['write-1041@1'],True,[])],
                                                      [(['call-1041@1'],False,['RESOURCE_REQUIRED']),(['write-1041@1'],True,[])]))   # because the gate, asked at its turn, turned the call away
        src=(ROOT/'extensions'/'queue_rank.py').read_text()                           # the extension reads one thing of the kernel: how a pack is named in the list of packs
        self.assertEqual([l.split('#')[0].strip() for l in src.splitlines() if l.startswith(('import ','from '))],['from __future__ import annotations','from kernel.core import digest'])
    def test_known_limit_ranking_by_impact_alone_can_serve_less_impact_than_the_listed_order(self):
        M=lambda i,e,c,a,m=0:{'id':i,'effect':e,'requires':[],'provider':'desk','grant':'g','cost':{'compute':c,'money':m,'attention':a},'action':'simulate_fact'}
        q=lambda:State.from_packs([P(id='q',goals=['small','big'],budget={'compute':9,'money':9,'attention':1},preference=['money','attention','compute'],
            rules=[dict(R('small',1),branches=[['s_called']]),dict(R('big',9),branches=[['b_called'],['b_visited']])],
            methods=[M('call-small','s_called',1,1),M('call-big','b_called',2,1),M('visit-big','b_visited',1,0,4)],providers={'desk':5},grants=['g'])])
        show=lambda s:[(r['goal'],r['status'],r['actions']) for r in Kernel(s).run_standing(execute=True)['runs']]
        a=q();b=q();rank(b)
        self.assertEqual(show(a),[('small','LOCAL_MODEL_EFFECTS_RECORDED',['call-small']),('big','LOCAL_MODEL_EFFECTS_RECORDED',['visit-big'])])   # as listed both goals run (big by its dearer route): impact 10
        self.assertEqual(show(b),[('big','LOCAL_MODEL_EFFECTS_RECORDED',['call-big']),('small','RESOURCE_REQUIRED',[])])                         # ranked, big takes the one call and small is held: impact 9
    def test_known_limit_a_ranking_is_a_snapshot_until_the_queue_is_ranked_again(self):
        s=state(QUEUE,RANKED);named={'pack':RANKED,'sha256':digest(pack(RANKED))}
        s.apply(P(id='reprice',rules=[dict(pack(QUEUE)['rules'][0],id='R-PROMISE-1041@2',replaces='R-PROMISE-1041@1',impact=50)]))   # a reviewed replacement makes loan 1041 the goal worth most
        self.assertEqual(s.goals,pack(RANKED)['goals'])                               # the queue stays as it was ranked, with loan 1041 last
        self.assertTrue(all(named in r['provenance'] for r in Kernel(s).run_standing()['runs']))   # and every run still names that ranking, whose reasons cite a rule the State no longer holds
        self.assertEqual((rank(s,'ranked-again')['goals'],s.goals),([L41,L42,L43,L44],[L41,L42,L43,L44]))
        s=state(RANKED,QUEUE)                                                         # the ranking applied before the queue it ranked: the queue is as listed, and the runs name the ranking all the same
        self.assertEqual((s.goals,[p['pack'] for p in Kernel(s).run_standing()['runs'][0]['provenance']]),(pack(QUEUE)['goals'],[RANKED,QUEUE]))
    def test_the_record_holds_the_two_looks_the_live_ranking_and_the_snapshots_around_it(self):
        data=record();sc=data['scenes']['queue_rank'];case=[c for c in data['cases'] if c['id']=='57_queue_ranked'][0]
        self.assertEqual((sc['ranking'],sc['as_listed']['goals'],sc['as_ranked']['goals']),(pack(RANKED),pack(QUEUE)['goals'],pack(RANKED)['goals']))
        self.assertEqual(roots(sc['as_ranked']),roots(case['run']));self.assertEqual(roots(sc['as_ranked']),roots(Kernel(self._ranked()).run_standing(execute=True)))
        b,a=sc['before_ranking'],sc['after_ranking'];others=lambda x:{k:v for k,v in x.items() if k not in ('goals','loaded')}
        self.assertEqual((others(a),a['loaded'][:-1],a['loaded'][-1]['pack'],a['goals']),(others(b),b['loaded'],RANKED,pack(RANKED)['goals']))   # right after the ranking: the order and one more pack, nothing else
        self.assertEqual(sc['after_ranking_again'],a)


def looked(*names,execute=True):   # the way the extension asks to be used: read the books, look, hand both in
    s=state(*names);k=Kernel(s);before=books(s);result=k.run_standing(execute=execute)
    return s,k,before,result,decisions(result['runs'],before)
def desk():
    s,k,before,result,rows=looked('132_loan_desk')
    asked=next(x for r in result['runs'] for x in r['model_receipts'] if x.get('parked'))
    return s,k,before,result,rows,asked
def said(rows,goal=None):return [(r['phase'],r['authority_verdict']) for r in rows if goal is None or r['work_ref']==goal]
def lines(rows,goal,kind):return [f['value'] for r in rows if r['work_ref']==goal for f in r['factors'] if f['type']==kind]
def kinds(row):return [f['type'] for f in row['factors']]
def rechain(run):   # a forger who also repairs the hash chain
    prev='GENESIS'
    for i,row in enumerate(run['trace']):
        row['seq']=i+1;row['prev_sha256']=prev;row['sha256']=digest({k:v for k,v in row.items() if k!='sha256'});prev=row['sha256']
    run['trace_root_sha256']=prev
def rehash(run):    # a forger who hashes the chain again and leaves each line's number as he set it
    prev='GENESIS'
    for row in run['trace']:
        row['prev_sha256']=prev;row['sha256']=digest({k:v for k,v in row.items() if k!='sha256'});prev=row['sha256']
    run['trace_root_sha256']=prev
STOPPED=('30_build_goal','31_build_theory','82_components_without_constructor')   # case 30_stop
OWN=('57_queue_ranked','58_gate_decisions','59_style_unmatched')
def covered(cid):   # the cases the every-case claim is about: this version's own three and the cases numbered up to 50. A case id is any plain name (another version's 67a_x begins with no whole number): such a case is not one of them
    head=cid.split('_')[0];return cid in OWN or (head.isascii() and head.isdigit() and int(head)<=50)


class DecisionProvenanceTests(unittest.TestCase):
    """R91. One row per gate decision, in the words of the decision-provenance row, with the line that decided."""
    NAMES=['schema_version','turn_id','decision_seq','ts','operator_id','charter_ref','domain_ref','task_tier','phase','intent_type','factors',
        'authority_verdict','reversibility','approval_ref','work_ref','output_ref','channels']   # a hand copy of the required names of decision-provenance-row.schema.json, in its order
    def test_every_admission_reads_as_granted_denied_or_escalated_one_row_each_in_order(self):
        s,k,before,result,rows,asked=desk()
        self.assertEqual({g:[v for _,v in said(rows,g)] for g in s.goals},
            {'loan_7001_disbursed':['granted','granted','granted'],'fee_7002_waived':['denied'],'limit_7003_raised':['granted','escalated'],
             'statement_7004_posted':['denied'],'audit_7005_sampled':['denied'],'writeoff_7006_booked':['not_evaluated']})
        gate=[(r['trace_root_sha256'],e['seq'],e['data']['accepted']) for r in result['runs'] for e in r['trace'] if e['operation']=='ADMISSION']
        at_gate=[r for r in rows if r['phase'] in ('plan','step')]
        self.assertEqual([(r['turn_id'],int(r['factors'][0]['source_ref'].split(':')[1]),r['authority_verdict']!='denied') for r in at_gate],gate)   # one row per ADMISSION line, in the kernel's order
        for run in result['runs']:
            mine=[r for r in rows if r['turn_id']==run['trace_root_sha256']]
            self.assertEqual(([r['decision_seq'] for r in mine],{r['work_ref'] for r in mine}),(list(range(len(mine))),{run['goal']}))
        self.assertEqual(said(rows,'loan_7001_disbursed'),[('plan','granted'),('step','granted'),('step','granted')])   # the plan before it is chosen, then each step before its effect
        mine=books(s);was=whole(s)                                                     # the books are the caller's own plain copy: changing them changes nothing in the State
        self.assertEqual(json.loads(json.dumps(mine)),mine)
        mine['budget']['money']=0;mine['providers']['ops-desk']=0;mine['grants'].append('action:waive-fee-7002@1')
        mine['methods']['verify-kyc-7001@1']['cost']['compute']=99;mine['methods']['update-limit-7003@1']['requires'].append('another_fact');mine['methods'].pop('waive-fee-7002@1')
        self.assertEqual(whole(s),was)
    def test_each_row_names_the_lines_the_gate_read_and_the_failing_ones_are_the_kernels_blockers(self):
        s,k,before,result,rows,asked=desk()
        self.assertEqual(lines(rows,'fee_7002_waived','grant_missing'),['action:waive-fee-7002@1'])
        self.assertEqual(lines(rows,'statement_7004_posted','provider_short'),['print-room: needs 1, has 0'])
        self.assertEqual(lines(rows,'audit_7005_sampled','budget_short'),['money: needs 9, has 8'])   # 8, not 10: what the first goal's receipts left when this gate was asked
        self.assertEqual(lines(rows,'limit_7003_raised','provider_free'),['credit-head: needs 1, has 1','ops-desk: needs 1, has 4','credit-head: needs 1, has 1'])
        self.assertEqual([v for v in lines(rows,'limit_7003_raised','budget_fits') if v.startswith('attention')],['attention: needs 1, has 1']*2)   # a cost equal to what is left fits: the desk had attention for exactly this one question
        self.assertEqual(lines(rows,'statement_7004_posted','budget_fits')[-1],'attention: needs 0, has 0')                                    # and nothing asked of an empty line fits too
        first=rows[0]['factors']
        self.assertEqual([(f['type'],f['value']) for f in first],[('method','verify-kyc-7001@1'),('method','release-funds-7001@1'),('grant_held','action:verify-kyc-7001@1'),
            ('grant_held','action:release-funds-7001@1'),('provider_free','ops-desk: needs 2, has 6'),('budget_fits','compute: needs 2, has 10'),('budget_fits','money: needs 2, has 10'),('budget_fits','attention: needs 0, has 1')])
        self.assertEqual({f['source_ref'] for f in first},{'trace:8'})                # every line cites the gate's own line in the run's hash chain
        fails={'grant_missing':'AUTHORITY_REQUIRED','provider_short':'PROVIDER_REQUIRED','budget_short':'RESOURCE_REQUIRED'}
        by_root={r['trace_root_sha256']:r for r in result['runs']}
        for row in rows:
            if row['phase'] not in ('plan','step'):continue
            line=by_root[row['turn_id']]['trace'][int(row['factors'][0]['source_ref'].split(':')[1])-1]['data']
            self.assertEqual(sorted({fails[f['type']] for f in row['factors'] if f['type'] in fails}),line['blockers'])
        part=State.from_packs([P(id='partial',goals=['g'],rules=[R('g',1)],methods=[{'id':'m','effect':'g_done','provider':'p','grant':'gr','cost':{'compute':1},'action':'simulate_fact'}],
                                 providers={'p':1},grants=['gr'])])                   # a method that names only one of the budget's lines costs nothing on the others
        b=books(part);fits=[[f['value'] for f in r['factors'] if f['type']=='budget_fits'] for r in decisions(Kernel(part).run_standing(execute=True)['runs'],b)]
        self.assertEqual(fits,[['compute: needs 1, has 10','money: needs 0, has 10','attention: needs 0, has 3']]*2)
    def test_an_ask_reads_as_escalated_and_each_answer_cites_who_decided_and_the_question_it_answered(self):
        s,k,before,result,rows,asked=desk()
        esc=[r for r in rows if r['authority_verdict']=='escalated']
        self.assertEqual([(r['phase'],r['approval_ref'],r['output_ref'],r['channels'],r['factors'][-1]) for r in esc],
                         [('step',asked['sha256'],None,['credit-head'],{'type':'asked','value':'credit-head: head_7003_approved','source_ref':'trace:9'})])
        mid=books(s);no=answer(k,asked,'FALSE','credit-head',execute=True);after=decisions(no['runs'],mid)
        self.assertEqual([(r['phase'],r['authority_verdict'],r['channels'],r['factors'],r['approval_ref'],r['output_ref']) for r in after],
                         [('decision','denied',['STAMP:credit-head'],[{'type':'decision','value':'head_7003_approved: FALSE, decided by STAMP:credit-head','source_ref':'trace:3'}],asked['sha256'],None)])
        s2,k2,_,_,_,asked2=desk();mid2=books(s2);yes=answer(k2,asked2,'TRUE','credit-head',execute=True);after2=decisions(yes['runs'],mid2)
        cite={'type':'decision','value':'head_7003_approved: TRUE, decided by STAMP:credit-head','source_ref':'trace:3'}
        self.assertEqual([(r['phase'],r['authority_verdict'],r['approval_ref'],r['channels'],r['factors'][-1],r['output_ref']) for r in after2],
                         [('plan','granted',asked2['sha256'],['STAMP:credit-head'],cite,None),
                          ('step','granted',asked2['sha256'],['STAMP:credit-head'],cite,yes['runs'][0]['model_receipts'][0]['sha256'])])   # the plan and the step that rest on the yes cite it
        line=yes['runs'][0]['trace'][2]                                               # the cited line is where the run read the decided fact
        self.assertEqual((line['operation'],line['data']),('RETAIN',{'predicate':'head_7003_approved','source':'STAMP:credit-head','version':'ask-'+asked2['sha256'][:12]}))
        self.assertEqual([kinds(r).count('decision') for r in after2],[1,1])          # cited once, though the run read the fact twice
        s3,k3,_,_,_,_=desk();b3=books(s3);again=k3.run_standing(execute=True);rows3=decisions(again['runs'],b3)   # a second look only waits: its plan is admitted, and nobody is asked twice
        self.assertEqual(([r['status'] for r in again['runs']][2],said(rows3,'limit_7003_raised')),('WAITING',[('plan','granted')]))
        self.assertNotIn('escalated',[v for _,v in said(rows3)])
    def test_a_yes_is_cited_where_a_chain_handed_in_closes_its_question_and_nowhere_else(self):
        s,k,_,_,_,asked=desk();mid=books(s);dry=answer(k,asked,'TRUE','credit-head')   # the answer arrives while nothing is executed: no chain closes the question yet
        self.assertEqual([(r['authority_verdict'],r['approval_ref'],r['channels'],kinds(r).count('decision')) for r in decisions(dry['runs'],mid)],[('granted',None,[],0)])   # known limit: the dry plan reads granted and cites nothing
        b=books(s);later=k.run_standing(execute=True);rows=decisions(later['runs'],b)
        self.assertEqual([r['goal'] for r in later['runs'] if [e for e in r['trace'] if e['operation']=='ASK_CLOSED']],['loan_7001_disbursed'])   # the first executed run of the look closes the question in its chain, whatever its goal
        mine=[r for r in rows if r['work_ref']=='limit_7003_raised']
        self.assertEqual([(r['phase'],r['authority_verdict'],r['approval_ref'],r['channels'],kinds(r).count('decision')) for r in mine],
                         [('plan','granted',asked['sha256'],['STAMP:credit-head'],1),('step','granted',asked['sha256'],['STAMP:credit-head'],1)])   # so the goal that rests on the yes cites it, two runs later in the same call
        self.assertTrue(all(r['approval_ref'] is None and r['channels']==[] and 'decision' not in kinds(r) for r in rows if r['work_ref']!='limit_7003_raised'))   # and no other row does
        alone=decisions(later['runs'][2:3],b)                                         # the same run handed in without the run that closed the question (the two runs before it paid nothing)
        self.assertEqual([(r['authority_verdict'],r['approval_ref'],r['channels'],kinds(r).count('decision')) for r in alone],[('granted',None,[],0)]*2)   # known limit: nothing handed in proves a decision, so none is cited
        other=State.from_packs([pack('132_loan_desk'),P(id='told',evidence=[{'predicate':'head_7003_approved','truth':'TRUE','verified':True,'source':'memo/somebody','version':'1'}])])
        ko=Kernel(other);bo=books(other);ro=decisions(ko.run_standing(execute=True)['runs'],bo)   # an ordinary row makes the fact true: the step runs, and no decision is cited
        self.assertEqual([(r['phase'],r['authority_verdict'],r['approval_ref'],kinds(r).count('decision')) for r in ro if r['work_ref']=='limit_7003_raised'],[('plan','granted',None,0),('step','granted',None,0)])
    def test_a_row_that_rests_on_two_answers_cites_each_once_names_their_source_once_and_gives_the_first_question(self):
        ask=lambda n:{'id':'ask-'+n,'effect':n+'_ok','provider':'head','grant':'g','cost':{'attention':1},'action':'ask','ask_to':'head','question':'May '+n+' go ahead?'}
        step=lambda i,effect,requires:{'id':i,'effect':effect,'requires':requires,'provider':'desk','grant':'g','cost':{'compute':1},'action':'simulate_fact'}
        s=State.from_packs([P(id='two',goals=['done'],methods=[ask('a'),ask('b'),step('prep','prep_done',['a_ok']),step('do','done',['a_ok','b_ok','prep_done'])],
                              providers={'head':2,'desk':2},grants=['g'])])
        k=Kernel(s);before=books(s);first=k.run_standing(execute=True);qa=first['runs'][0]['model_receipts'][-1]   # the first question is asked and the run parks
        second=answer(k,qa,'TRUE','head',execute=True);qb=second['runs'][0]['model_receipts'][-1]               # yes: this run closes the first question and asks the second
        mid=books(s);third=answer(k,qb,'TRUE','head',execute=True)                                             # yes again: this run closes the second question, and both steps run
        self.assertEqual((third['runs'][0]['status'],third['runs'][0]['actions']),('LOCAL_MODEL_EFFECTS_RECORDED',['prep','do']))
        rows=decisions(first['runs']+second['runs']+third['runs'],before)
        told=lambda rows,run:[(r['phase'],r['authority_verdict'],[f['value'] for f in r['factors'] if f['type']=='decision'],r['approval_ref'],r['channels']) for r in rows if r['turn_id']==run['runs'][0]['trace_root_sha256']]
        yes_a,yes_b,head='a_ok: TRUE, decided by STAMP:head','b_ok: TRUE, decided by STAMP:head',['STAMP:head']
        self.assertEqual(told(rows,first),[('plan','granted',[],None,[]),('step','escalated',[],qa['sha256'],['head'])])
        self.assertEqual(told(rows,second),[('plan','granted',[yes_a],qa['sha256'],head),('step','escalated',[],qb['sha256'],['head'])])   # two steps of the plan require the first yes: it is cited once; an escalated row cites its own question only
        self.assertEqual(told(rows,third),[('plan','granted',[yes_a,yes_b],qa['sha256'],head),('step','granted',[yes_a],qa['sha256'],head),
                                           ('step','granted',[yes_a,yes_b],qa['sha256'],head)])   # both answers, their one source once, the first question; what an earlier step made is not an answer
        self.assertEqual(told(decisions(third['runs'],mid),third),[('plan','granted',[yes_b],qb['sha256'],head),('step','granted',[],None,[]),
                                                                   ('step','granted',[yes_b],qb['sha256'],head)])   # handed in alone, the last run proves only the answer its own chain closes
    def test_a_granted_step_cites_its_receipt_or_the_stop_that_followed_and_a_run_that_never_reached_the_gate_is_not_evaluated(self):
        s,k,before,result,rows,asked=desk()
        steps=[r['output_ref'] for r in rows if r['phase']=='step' and r['authority_verdict']=='granted']
        self.assertEqual(steps,[x['sha256'] for r in result['runs'] for x in r['model_receipts'] if not x.get('parked')])
        self.assertTrue(all(r['output_ref'] is None for r in rows if r['phase']!='step'))
        s2,k2,b2,res2,rows2=looked(*STOPPED)                                          # case 30_stop: three steps run, the fourth is admitted by the gate and then refused by its handler
        run=res2['runs'][0];stop=[e for e in run['trace'] if e['operation']=='STEP_STOPPED'][0]
        self.assertEqual((run['status'],said(rows2)),('STEP_STOPPED',[('plan','granted')]+[('step','granted')]*4))
        self.assertEqual([r['output_ref'] for r in rows2],[None]+[x['sha256'] for x in run['model_receipts']]+[None])
        self.assertEqual(rows2[4]['factors'][-1],{'type':'stopped','value':'Handler refused: No declared constructor','source_ref':'trace:%d'%stop['seq']})   # the row says the step stopped, why, and where the chain says so
        self.assertEqual([kinds(r).count('stopped') for r in rows2],[0,0,0,0,1])
        for r in rows+rows2:                                                          # a granted step has a receipt or a stop: never both, never neither
            if r['phase']=='step' and r['authority_verdict']=='granted':self.assertEqual(r['output_ref'] is None,'stopped' in kinds(r))
        idle=State(actions={'simulate_fact':ACTIONS['simulate_fact'],'test_idle':{'run':lambda s,m,mid,deps:{}}})   # a step whose handler leaves a receipt and makes nothing: the next step's prerequisite is not true
        idle.apply(P(id='idle',goals=['done'],methods=[{'id':'first','effect':'a','provider':'p','grant':'g','cost':{'compute':1},'action':'test_idle'},
                                                      {'id':'second','effect':'done','requires':['a'],'provider':'p','grant':'g','cost':{'compute':1},'action':'simulate_fact'}],providers={'p':2},grants=['g']))
        bi=books(idle);ri=Kernel(idle).run_standing(execute=True)['runs'];rows_i=decisions(ri,bi)
        self.assertEqual((ri[0]['status'],said(rows_i),rows_i[1]['output_ref'],rows_i[2]['output_ref'],rows_i[2]['factors'][-1]['type'],rows_i[2]['factors'][-1]['value']),
                         ('STEP_STOPPED',[('plan','granted'),('step','granted'),('step','granted')],ri[0]['model_receipts'][0]['sha256'],None,'stopped','Prerequisite not true before effect: a'))
        def drops(s,m,mid,deps):s.grants.discard('g2');s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':'LOCAL_MODEL:'+mid,'version':'1'});return {}
        med=State(actions={'simulate_fact':ACTIONS['simulate_fact'],'test_meddle':{'run':drops}})   # a handler that takes a grant away in the middle of a plan: the gate turns the next step away
        med.apply(P(id='med',goals=['done'],methods=[{'id':'first','effect':'a','provider':'p','grant':'g','cost':{'compute':1},'action':'test_meddle'},
                                                    {'id':'second','effect':'done','requires':['a'],'provider':'p','grant':'g2','cost':{'compute':1},'action':'simulate_fact'}],providers={'p':2},grants=['g','g2']))
        bm=books(med);rm=Kernel(med).run_standing(execute=True)['runs']
        self.assertEqual(rm[0]['stopped'],{'method':'second','reason':'Gate changed before effect: AUTHORITY_REQUIRED'})
        refusal(self,lambda:decisions(rm,bm),UNEXPLAINED)                             # books that only receipts change cannot explain a gate a handler changed
        def both(s,m,mid,deps):
            for made in (m['effect'],'done'):s.observe({'predicate':made,'truth':'TRUE','verified':True,'source':'LOCAL_MODEL:'+mid,'version':'1'})
            return {}
        skip=State(actions={'simulate_fact':ACTIONS['simulate_fact'],'test_both':{'run':both}})   # a step whose effect an earlier step already made true is skipped: it never meets the gate, so it has no row
        skip.apply(P(id='skip',goals=['done'],methods=[{'id':'first','effect':'a','provider':'p','grant':'g','cost':{'compute':1},'action':'test_both'},
                                                      {'id':'second','effect':'done','requires':['a'],'provider':'p','grant':'g','cost':{'compute':1},'action':'simulate_fact'}],providers={'p':2},grants=['g']))
        bs=books(skip);rs=Kernel(skip).run_standing(execute=True)['runs']
        self.assertEqual((rs[0]['status'],rs[0]['actions'],rs[0]['skipped'],said(decisions(rs,bs))),('LOCAL_MODEL_EFFECTS_RECORDED',['first'],['second'],[('plan','granted'),('step','granted')]))
        def plan_of_two(kind,handler):   # a plan of two steps on a State of its own, the first step of a kind made here: the run, and its rows
            st=State(actions={'simulate_fact':ACTIONS['simulate_fact'],kind:{'run':handler}})
            st.apply(P(id=kind,goals=['done'],methods=[{'id':'first','effect':'a','provider':'p','grant':'g','cost':{'compute':1},'action':kind},
                                                       {'id':'second','effect':'done','requires':['a'],'provider':'p','grant':'g','cost':{'compute':1},'action':'simulate_fact'}],providers={'p':2},grants=['g']))
            bk=books(st);made=Kernel(st).run_standing(execute=True)['runs'];return made[0],decisions(made,bk)
        def fails(s,m,mid,deps):raise KeyError('the words of an error stay out of the record')
        def no_receipt(s,m,mid,deps):return {'made':{1,2}}
        for kind,handler,reason in (('test_fails',fails,'Handler failed: KeyError'),('test_no_receipt',no_receipt,'Handler returned what cannot be a receipt')):
            rk,rows_k=plan_of_two(kind,handler)                                       # the other ways a step stops after the gate: its handler fails, or returns what cannot be a receipt. The row cites the kernel's phrase
            at=[e['seq'] for e in rk['trace'] if e['operation']=='STEP_STOPPED']
            self.assertEqual((rk['status'],len(at),said(rows_k),rows_k[1]['output_ref'],rows_k[1]['factors'][-1]),('STEP_STOPPED',1,[('plan','granted'),('step','granted')],None,{'type':'stopped','value':reason,'source_ref':'trace:%d'%at[0]}))
        def gone(s,m,mid,deps):s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':'LOCAL_MODEL:'+mid,'version':'1'});del s.methods['second'];return {}
        rg,rows_g=plan_of_two('test_gone',gone)                                       # known limit: a handler takes the next step's method away, and the kernel stops that step before it asks the gate
        self.assertEqual((rg['status'],rg['stopped'],[e['operation'] for e in rg['trace']][-3:]),('STEP_STOPPED',{'method':'second','reason':'Kernel fault: KeyError'},['LOCAL_EFFECT','STEP_STOPPED','TERMINAL']))
        self.assertEqual((said(rows_g),[kinds(x).count('stopped') for x in rows_g],rows_g[1]['output_ref']),([('plan','granted'),('step','granted')],[0,0],rg['model_receipts'][0]['sha256']))   # no gate line, so no row: the rows end with the step that ran, and none says the run stopped
        def rested(*more):   # a step that rests on a rule's head which no stored row makes true: the kernel offers the plan, the gate admits it, and the step stops at its turn
            st=State.from_packs([P(id='rested',goals=['shipped'],rules=[{'id':'R-READY@1','head':'ready','branches':[['packed']],'approved':True}],
                                   methods=[{'id':'pack','effect':'packed','provider':'p','grant':'g','cost':{'compute':1},'action':'simulate_fact'},
                                            {'id':'ship','effect':'shipped','requires':['ready'],'provider':'p','grant':'g','cost':{'compute':1},'action':'simulate_fact'}],providers={'p':2},grants=['g'])]+list(more))
            bk=books(st);made=Kernel(st).run_standing(execute=True)['runs'];return made[0],decisions(made,bk)
        rr,rows_r=rested()
        self.assertEqual((rr['status'],rr['actions'],said(rows_r),[x['output_ref'] is None for x in rows_r],rows_r[2]['factors'][-1]['value']),
                         ('STEP_STOPPED',['pack'],[('plan','granted'),('step','granted'),('step','granted')],[True,False,True],'Prerequisite not true before effect: ready'))
        rn,rows_n=rested(P(id='no',evidence=[{'predicate':'ready','truth':'FALSE','verified':True,'final':True,'source':'STAMP:head','version':'d1'}]))
        self.assertEqual((rn['status'],said(rows_n),rows_n[0]['channels'],rows_n[0]['approval_ref']),('REFUSED',[('decision','denied')],['STAMP:head'],None))   # a decision that says no on that head, answering no question handed in: one denied row, by its source, with no receipt
        last=[r for r in rows if r['work_ref']=='writeoff_7006_booked']
        self.assertEqual([(r['phase'],r['authority_verdict'],r['factors'],r['channels']) for r in last],[(None,'not_evaluated',[{'type':'blocked','value':'SEMANTICS_MISSING','source_ref':'trace:3'}],[])])
        b=books(s);again=k.run_standing(execute=True);rows3=decisions(again['runs'],b)   # the first goal is now true on evidence: an empty plan is admitted, with nothing but the budget lines to read
        done=[r for r in rows3 if r['work_ref']=='loan_7001_disbursed']
        self.assertEqual((again['runs'][0]['status'],said(done),kinds(done[0])),('SUPPORTED_BY_EVIDENCE',[('plan','granted')],['budget_fits']*3))
    def test_the_rows_carry_the_schemas_names_and_leave_null_what_the_lab_cannot_compute(self):
        s,k,before,result,rows,asked=desk()
        self.assertEqual((list(FIELDS),len(FIELDS)),(self.NAMES,17))
        for row in rows+looked(*STOPPED)[4]:
            self.assertEqual((list(row),row['schema_version']),(self.NAMES,VERSION))
            self.assertEqual([row[name] for name in ('ts','operator_id','charter_ref','domain_ref','task_tier','intent_type','reversibility')],[None]*7)
            self.assertIn(row['authority_verdict'],('granted','denied','escalated','not_evaluated'))
            self.assertTrue(all(set(f)=={'type','value','source_ref'} and type(f['value']) is str for f in row['factors']))
    def test_what_does_not_explain_the_trace_is_refused_and_nothing_handed_in_is_changed(self):
        s,k,before,result,rows,asked=desk();runs=result['runs'];held=(whole(s),copy.deepcopy(runs),copy.deepcopy(before))
        vk=before['methods']['verify-kyc-7001@1']
        wrong=[dict(before,budget=dict(before['budget'],money=20)),                   # the audit would have fitted: the trace says it did not
               dict(before,budget=dict(before['budget'],attention=0)),                # the question would not have fitted: the trace says it was asked
               dict(before,grants=before['grants']+['action:waive-fee-7002@1']),      # the fee's grant would have been held
               dict(before,providers=dict(before['providers'],**{'print-room':1})),   # the print room would have had a slot
               dict(before,methods=dict(before['methods'],**{'verify-kyc-7001@1':dict(vk,cost={'compute':5,'money':0,'attention':0})})),   # a cost that is not the method's
               books(s)]                                                              # the books as the look left them
        for b in wrong:refusal(self,lambda:decisions(runs,b),UNEXPLAINED)
        self.assertEqual(record()['scenes']['queue_provenance']['wrong_books_refused'],UNEXPLAINED)
        fee=runs[1:2];moved=dict(before,grants=before['grants']+['action:waive-fee-7002@1'],providers=dict(before['providers'],**{'ops-desk':0}))
        self.assertEqual(said(decisions(fee,before)),[('plan','denied')])
        self.assertEqual(lines(decisions(fee,before),'fee_7002_waived','budget_fits')[:2],['compute: needs 1, has 10','money: needs 1, has 10'])   # known limit: books of an earlier moment that still explain the verdict are printed as handed in (the gate had 8 of each)
        refusal(self,lambda:decisions(fee,moved),UNEXPLAINED)                         # books under which the fee is still turned away, but on another line: the failing line must be the kernel's
        shapeless=[dict(before,methods={m:v for m,v in before['methods'].items() if m!='waive-fee-7002@1'}),dict(before,budget={'compute':10,'money':10}),
                   {key:v for key,v in before.items() if key!='grants'},dict(before,grants={g:1 for g in before['grants']}),dict(before,grants=tuple(before['grants'])),
                   dict(before,methods={m:{key:v for key,v in x.items() if key!='requires'} for m,x in before['methods'].items()}),None,[],dict(before,grants=set(before['grants']))]
        for b in shapeless:refusal(self,lambda:decisions(runs,b),NOT_DATA)
        for junk in (None,'runs',[1],[{}],tuple(runs),(r for r in runs),[tuple(runs[0].items())],[dict(runs[0],trace=tuple(runs[0]['trace']))],
                     [dict(runs[0],extra={1,2})],[dict(runs[0],extra=object())]):
            refusal(self,lambda:decisions(junk,before),NOT_DATA)                      # anything that is not a list of plain run records: a tuple of runs, a run that holds a tuple or an object
        refusal(self,lambda:decisions([{'trace':[]}],before),BROKEN)
        cut=copy.deepcopy(runs);cut[0]['trace_root_sha256']='0'*64
        refusal(self,lambda:decisions(cut,before),BROKEN)                             # a root that is not the last line of its trace
        mended=copy.deepcopy(runs);row=mended[0]['trace'][3];row['data']['edited']=1;row['sha256']=digest({key:v for key,v in row.items() if key!='sha256'})
        refusal(self,lambda:decisions(mended,before),BROKEN)                          # a line edited and hashed again: it holds by itself, and the line after it no longer points at it
        edited=copy.deepcopy(runs);edited[1]['trace'][2]['data'].update(accepted=True,blockers=[])
        refusal(self,lambda:decisions(edited,before),BROKEN)                          # a trace that was edited: its hash chain does not hold
        rechain(edited[1])
        refusal(self,lambda:decisions(edited,before),UNEXPLAINED)                     # the same edit with the chain repaired: now the books do not explain it
        odd=copy.deepcopy(runs);t=odd[0]['trace'];del t[next(i for i,e in enumerate(t) if e['operation']=='LOCAL_EFFECT')];rechain(odd[0])
        refusal(self,lambda:decisions(odd,before),NOT_KERNEL)                         # a step at the gate with no effect and no stop after it
        turned=copy.deepcopy(runs[1]);t=turned['trace'];at=next(i for i,e in enumerate(t) if e['operation']=='ADMISSION')
        t.insert(at,{'operation':'SELECT','data':{'actions':['waive-fee-7002@1']}});t.insert(at+2,{'operation':'STEP_STOPPED','data':{'method':'waive-fee-7002@1','reason':'Gate changed before effect: AUTHORITY_REQUIRED'}});rechain(turned)
        refusal(self,lambda:decisions([turned],before),NOT_KERNEL)                    # a step the gate turned away, on books that agree it would: the kernel never asks about a step of a plan it did not admit
        self.assertEqual((whole(s),runs,before),held)                                 # nothing handed in, and nothing in the State, was changed by any of this
        self.assertEqual(decisions(runs,before),rows)
        again=decisions(runs,before);again[0]['factors'].clear();self.assertEqual(decisions(runs,before),rows)   # and the rows are the caller's own: changing them changes nothing else
    def test_a_long_look_is_read_run_by_run_and_what_is_too_large_says_so(self):
        n=450                                                                         # one copy of a whole look gave out at 426 goals of this shape
        s=State.from_packs([P(id='long',goals=[f'g{i}' for i in range(n)],budget={'compute':n,'money':0,'attention':0},rules=[dict(R(f'g{i}',i),branches=[[f'd{i}']]) for i in range(n)],
                              methods=[{'id':f'm{i}','effect':f'd{i}','provider':'p','grant':'g','cost':{'compute':1},'action':'simulate_fact'} for i in range(n)],providers={'p':n},grants=['g'])])
        rank(s);before=books(s);result=Kernel(s).run_standing(execute=True)           # the look is the caller's: it is in hand before the projection is asked anything
        refusal(self,lambda:plain({'runs':result['runs']}))                           # as one piece of data the look is beyond the kernel's bound for anything handed in
        rows=decisions(result['runs'],before)
        self.assertEqual((len(rows),{r['authority_verdict'] for r in rows},rows[0]['work_ref'],s.budget['compute']),(2*n,{'granted'},f'g{n-1}',0))
        refusal(self,lambda:decisions([dict(result['runs'][0],padding=[0]*BOUND)],before),TOO_LARGE)   # one run beyond the bound says so, in its own words
        refusal(self,lambda:decisions(result['runs'][:1],dict(before,padding=[0]*BOUND)),TOO_LARGE)    # and so do books beyond it
        refusal(self,lambda:decisions([dict(result['runs'][0],padding={0})],before),NOT_DATA)          # which is not what data of the wrong kind is told
        def items(v):return 1+(sum(1+items(x) for x in v.values()) if type(v) is dict else sum(items(x) for x in v) if type(v) is list else 0)   # what the kernel's copy counts: every value and every key
        run=result['runs'][0];room=BOUND-items(run)-2                                  # a key and a list take two: the rest is padding
        self.assertEqual(len(decisions([dict(run,padding=[0]*room)],before)),2)        # exactly at the bound: read
        refusal(self,lambda:decisions([dict(run,padding=[0]*(room+1))],before),TOO_LARGE)        # one item more: too large
        refusal(self,lambda:decisions([dict(run,padding=[0]*(room-1)+[{0}])],before),NOT_DATA)   # at the bound, and its last item is not data: that is what it is told
        deep=lambda n:[deep(n-1)] if n else 0
        self.assertEqual(len(decisions([dict(run,nested=deep(15))],before)),2)         # sixteen levels below the run: read
        refusal(self,lambda:decisions([dict(run,nested=deep(16))],before),NOT_DATA)    # one level more: not plain data
        def returned(levels):                                                          # one step whose handler returns data nested this many levels below its own object: the books before, and the run
            def handler(s,m,mid,deps):
                s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':'LOCAL_MODEL:'+mid,'version':'1'});return {'made':deep(levels-1)}
            st=State(actions={'test_deep':{'run':handler}})
            st.apply(P(id='deep',goals=['done'],methods=[{'id':'make','effect':'done','provider':'p','grant':'g','cost':{'compute':1},'action':'test_deep'}],providers={'p':1},grants=['g']))
            bk=books(st);return bk,Kernel(st).run_standing(execute=True)['runs']
        b12,r12=returned(12);self.assertEqual((r12[0]['status'],len(decisions(r12,b12))),('LOCAL_MODEL_EFFECTS_RECORDED',2))   # a receipt stands four levels down in its run's trace, so twelve levels of its own are read
        b13,r13=returned(13);self.assertEqual((r13[0]['status'],len(r13[0]['model_receipts'])),('LOCAL_MODEL_EFFECTS_RECORDED',1))   # known limit: the kernel takes a deeper return as a receipt and the step runs,
        refusal(self,lambda:decisions(r13,b13),NOT_DATA)                               # and the projection, which copies a run sixteen levels deep, does not read that run
        self.assertEqual((BOUND,TOO_LARGE,NOT_DATA,BROKEN,NOT_KERNEL,UNEXPLAINED),(100000,'Too large to read: one run, or the books, holds more than 100000 items',
            'Not run records and the books they started from','The hash chain of this trace does not hold','This is not a trace the kernel writes','These books do not explain this trace'))
    def test_on_every_case_of_this_version_the_books_explain_every_gate_line(self):
        seen=Counter()
        for cid,_,_,files,execute,_ in CASES:
            if not covered(cid):continue                                              # the lab this version was added to (cases numbered up to 50) and its own three; what another added version brings is its own to check
            s,k,before,result,rows=looked(*files,execute=execute)                     # refused (ValueError) if the books did not explain a line
            gate=sum(1 for r in result['runs'] for e in r['trace'] if e['operation']=='ADMISSION')
            self.assertEqual(sum(1 for r in rows if r['phase'] in ('plan','step')),gate,cid)
            seen.update(r['authority_verdict'] for r in rows);seen.update('factor:'+t for r in rows for t in kinds(r) if t in ('stopped','decision','asked'))
        self.assertEqual(dict(seen),{'granted':61,'denied':10,'escalated':3,'not_evaluated':10,'factor:asked':3,'factor:stopped':1})   # (confirming round) totals written here, not derived: of the covered cases of the lab this version was reviewed on. A lab with another number of cases numbered up to 50 changes them with nothing wrong in the version (S89's count is fixed the same way: test_confirm_s89_holds_a_fixed_count_of_cases)
        self.assertEqual([covered(c) for c in ('50_must_cohere','51_refused_class','57_queue_ranked','57a_another','67a_order_in_time','a_case')],[True,False,True,False,False,False])   # another version's case, whatever its name, is not counted here
    def test_the_record_holds_the_desks_rows_and_they_are_the_cases_runs(self):
        data=record();sc=data['scenes']['queue_provenance'];case=[c for c in data['cases'] if c['id']=='58_gate_decisions'][0]
        s,k,before,result,rows,asked=desk()
        self.assertEqual((sc['decisions'],roots(case['run'])),(rows,roots(result)))
        self.assertEqual(sc['books_before'],{key:before[key] for key in ('grants','providers','budget')})
        self.assertEqual(sc['decisions_of_a_stopped_step'],looked(*STOPPED)[4])
    def test_known_limit_two_runs_with_the_same_hash_chain_give_rows_with_the_same_ids(self):
        s=state('132_loan_desk');k=Kernel(s);b=books(s)
        ids=[(r['turn_id'],r['decision_seq']) for r in decisions(k.run_standing()['runs']+k.run_standing()['runs'],b)]   # two dry looks: the kernel has no clock, so the second look's chains are the first's
        self.assertEqual((len(ids),len(set(ids))),(12,6))


STYLES=['133_complaint_desk','134_style_run_the_book','135_style_incident']
GOAL='complaint_8801_closed'
def styled(*more,execute=True):
    s=state(*STYLES,*more);return s,Kernel(s).run_standing(execute=execute)['runs'][0]
def chosen(r):return next(e['data']['actions'] for e in r['trace'] if e['operation']=='SELECT')
def refined(r):return [e['data']['rule'] for e in r['trace'] if e['operation']=='REFINE']
def asked_for(r):return [(e['operation'],e['data'].get('predicate')) for e in r['trace'] if e['operation'] in ('METHOD_ABSENT','QUERY_EVIDENCE','REFUSED','ADMISSION','SELECT')]
def routers_word(r):return [(e['data']['predicate'],e['data']['source']) for e in r['trace'] if e['operation']=='RETAIN' and e['data']['predicate'].startswith('styled_')]
def own(name):return [m['id'] for m in pack(name)['methods']]
def names(style,source='router/credit-ops'):return {'predicate':'styled_'+style,'truth':'TRUE','verified':True,'source':source,'version':'r2'}   # the router's row, as an event
UNTOUCHED=({'compute':10,'money':10,'attention':2},{'charter-owner':1,'ops-desk':4,'ops-head':1})


class ProblemStyleTests(unittest.TestCase):
    """R101. A style is a card: a pack with its own rule for done-when, its own methods and its own grants."""
    def test_two_styles_give_one_goal_two_plans_each_from_its_own_card(self):
        (sa,a),(sb,b)=styled('136_routed_by_the_book'),styled('137_routed_incident')
        self.assertEqual((a['goal'],b['goal'],sa.goals,sb.goals),(GOAL,GOAL,[GOAL],[GOAL]))
        self.assertEqual((chosen(a),chosen(b)),(own('134_style_run_the_book'),own('135_style_incident')))   # each plan is its own card's methods: all of them, and no others
        self.assertEqual(set(chosen(a))&set(chosen(b)),set())
        self.assertEqual((refined(a),refined(b)),(['R-STYLES@1','R-STYLE-RUN-THE-BOOK@1'],['R-STYLES@1','R-STYLE-INCIDENT@1']))   # the declaration, then the one card the router named
        self.assertEqual((a['selected_branch'],b['selected_branch']),('R-STYLES@1/OR1','R-STYLES@1/OR2'))
        self.assertEqual((routers_word(a),routers_word(b)),([('styled_by_the_book','router/credit-ops')],[('styled_incident','router/credit-ops')]))   # each run read one row of the router: the style it named
        self.assertEqual([[(x['predicate'],x['truth']) for x in pack(n)['evidence']] for n in ('136_routed_by_the_book','137_routed_incident')],
                         [[('styled_by_the_book','TRUE')],[('styled_incident','TRUE')]])   # and one row is all the router wrote: nothing about the other style
        for name,r in (('134_style_run_the_book',a),('135_style_incident',b)):       # each plan makes exactly what its card says done is
            card=pack(name)['rules'][0];made=sorted(m['effect'] for m in pack(name)['methods'] if m['id'] in chosen(r))
            self.assertEqual(made,sorted(card['branches'][0]))
            self.assertEqual(set(card['card']),{'style','what_is_missing','cause_effect','reach','cadence','vehicle','verify','gate','unmatched'})
        self.assertEqual((a['status'],a['actions'],a['cost']),('LOCAL_MODEL_EFFECTS_RECORDED',['match-ledger-8801@1','post-reversal-8801@1'],{'compute':2,'money':1,'attention':0}))
        self.assertEqual((b['status'],b['actions'],b['pending'],b['waits']),('WAITING',['write-cause-8801@1','ask-signoff-8801@1'],['tell-customer-8801@1'],['ask-signoff-8801@1']))
    def test_the_gate_posture_rides_on_the_card_one_style_runs_through_and_one_asks(self):
        (sa,a),(sb,b)=styled('136_routed_by_the_book'),styled('137_routed_incident')
        posture=lambda name:(pack(name)['rules'][0]['card']['gate'],[m['ask_to'] for m in pack(name)['methods'] if m['action']=='ask'])
        self.assertEqual((posture('134_style_run_the_book'),posture('135_style_incident')),(('auto',[]),('ask',['ops-head'])))
        self.assertEqual((open_asks(sa),[v['issued']['ask']['to'] for v in open_asks(sb).values()]),({},['ops-head']))
        self.assertEqual(sb.fact('customer_8801_told')['truth'],'UNKNOWN')            # nothing after the question ran
        refusal(self,lambda:answer(Kernel(sb),b['model_receipts'][-1],'TRUE','ops-desk'))   # only the party the card names may answer
        yes=answer(Kernel(sb),b['model_receipts'][-1],'TRUE','ops-head',execute=True)['runs'][0]
        self.assertEqual((yes['goal'],yes['status'],yes['actions']),(GOAL,'LOCAL_MODEL_EFFECTS_RECORDED',['tell-customer-8801@1']))
    def test_a_problem_the_router_marks_unmatched_asks_the_charter_owner_and_runs_no_card(self):
        s,r=styled('138_routed_unmatched');fallback=pack('133_complaint_desk')['methods'][0]
        self.assertEqual((r['status'],r['work_state'],r['actions'],r['pending'],r['waits'],r['cost'],r['selected_branch']),
                         ('WAITING','waiting',['ask-new-home-8801@1'],[],['ask-new-home-8801@1'],{'compute':0,'money':0,'attention':1},'R-STYLES@1/OR3'))
        cards=set(own('134_style_run_the_book')+own('135_style_incident'))
        self.assertEqual((chosen(r),set(chosen(r))&cards,refined(r)),(['ask-new-home-8801@1'],set(),['R-STYLES@1']))   # no card's method is planned and no card's rule is read
        asked=r['model_receipts'][-1]
        self.assertEqual((len(r['model_receipts']),asked['parked'],asked['ask']['to'],asked['ask']['predicate'],asked['ask']['question']),
                         (1,True,'charter-owner','new_home_8801_agreed',fallback['question']))
        self.assertEqual(routers_word(r),[('styled_unmatched','router/credit-ops')])  # the run cites the router's own row: that row, and no other, is why the owner is asked
        self.assertEqual([(x['predicate'],x['truth']) for x in pack('138_routed_unmatched')['evidence']],[('styled_unmatched','TRUE')])   # one row: the router says nothing about the declared styles
        self.assertEqual((s.budget,s.providers),({'compute':10,'money':10,'attention':1},{'charter-owner':0,'ops-desk':4,'ops-head':1}))   # one question, paid once; no card's provider was used
        self.assertEqual([v['issued']['ask']['to'] for v in open_asks(s).values()],['charter-owner'])
        again=Kernel(s).run_standing(execute=True)['runs'][0]                         # looked at again it waits: nobody is asked twice and nothing more is paid
        self.assertEqual((again['status'],again['actions'],again['model_receipts'],again['waits'],s.budget['attention']),('WAITING',[],[],['ask-new-home-8801@1'],1))
        packs=[pack(n) for n in STYLES+['138_routed_unmatched']]
        learned=Learner.from_packs(packs).attach(Kernel(State.from_packs(packs)).run_standing(execute=True))['runs'][0]['learning']
        self.assertEqual(learned,[])                                                  # a question that is out is not a gap: nothing is proposed
    def test_before_the_router_speaks_and_when_it_names_an_unlisted_style_the_goal_blocks_and_names_the_rows_it_reads(self):
        s0,r0=styled();three=[('QUERY_EVIDENCE','styled_by_the_book'),('QUERY_EVIDENCE','styled_incident'),('QUERY_EVIDENCE','styled_unmatched')]
        self.assertEqual((r0['status'],r0['work_state'],r0['stop_reasons'],asked_for(r0),r0['actions'],r0['model_receipts']),('QUERY_EVIDENCE','blocked',['QUERY_EVIDENCE'],three,[],[]))
        self.assertEqual((s0.budget,s0.providers),UNTOUCHED)
        s=state(*STYLES);k=Kernel(s);told=k.on_event(names('campaign'),execute=True)   # the router names a style the declaration does not list
        self.assertEqual((told['status'],told['affected'],told['runs']),('RECONCILED',[],[]))   # no goal reads that row: nothing is even looked at
        r=k.run_standing(execute=True)['runs'][0]
        self.assertEqual((r['trace_root_sha256'],r['status']),(r0['trace_root_sha256'],'QUERY_EVIDENCE'))   # and the look that follows is, line for line, the look before the router spoke
        self.assertEqual((s.fact('styled_campaign')['truth'],s.fact('styled_campaign')['source'],s.budget,s.providers),('TRUE','router/credit-ops')+UNTOUCHED)   # the name is on the record; no rule reads it
        s.apply(pack('139_style_campaign'));r=k.run_standing(execute=True)['runs'][0]   # the row stays on the books: once a declaration lists that style, the same row routes the goal
        self.assertEqual((r['status'],r['actions'],routers_word(r)),('LOCAL_MODEL_EFFECTS_RECORDED',own('139_style_campaign'),[('styled_campaign','router/credit-ops')]))
        s2=state(*STYLES);s2.apply(P(id='not-these',evidence=[dict(names('by_the_book'),truth='FALSE'),dict(names('incident'),truth='FALSE')]))
        r2=Kernel(s2).run_standing(execute=True)['runs'][0]                           # a router that only says what the problem is not: the goal still asks for the row that says it is unmatched
        self.assertEqual((r2['status'],asked_for(r2)),('QUERY_EVIDENCE',[('METHOD_ABSENT','styled_by_the_book'),('METHOD_ABSENT','styled_incident'),('QUERY_EVIDENCE','styled_unmatched')]))
        s1=state('133_complaint_desk','135_style_incident','136_routed_by_the_book')  # a declared style whose card is not loaded: the run names the card's head
        r1=Kernel(s1).run_standing(execute=True)['runs'][0]
        self.assertEqual((r1['status'],asked_for(r1)),('QUERY_EVIDENCE',[('QUERY_EVIDENCE','resolved_by_the_book'),('QUERY_EVIDENCE','styled_incident'),('QUERY_EVIDENCE','styled_unmatched')]))
    def test_the_owners_no_keeps_the_complaint_until_a_new_style_is_named_and_the_owners_yes_closes_it_with_no_step(self):
        s=state(*STYLES,'138_routed_unmatched');k=Kernel(s);asked=k.run_standing(execute=True)['runs'][0]['model_receipts'][-1]
        refusal(self,lambda:answer(k,asked,'FALSE','ops-head'))                       # only the party the declaration names may answer
        no=answer(k,asked,'FALSE','charter-owner',execute=True)['runs'][0]            # no: it stays here, and a new style is to be declared
        self.assertEqual((no['goal'],no['status'],no['work_state'],no['stop_reasons'],no['actions']),(GOAL,'REFUSED','blocked',['QUERY_EVIDENCE','REFUSED'],[]))
        self.assertIn(('REFUSED','new_home_8801_agreed'),asked_for(no))
        again=k.run_standing(execute=True)['runs'][0];self.assertEqual((again['status'],again['model_receipts'],open_asks(s)),('REFUSED',[],{}))   # the no is a decision: nobody is asked again
        s.apply(pack('139_style_campaign'))                                          # the new style: one more card, and the declaration that replaces the old one
        self.assertEqual(k.run_standing(execute=True)['runs'][0]['status'],'REFUSED')   # declared, and not yet named by the router
        new=k.on_event(names('campaign'),execute=True);r=new['runs'][0]
        self.assertEqual((new['affected'],r['status'],r['actions'],r['selected_branch'],r['cost']),
                         ([GOAL],'LOCAL_MODEL_EFFECTS_RECORDED',own('139_style_campaign'),'R-STYLES@2/OR4',{'compute':2,'money':2,'attention':0}))
        self.assertEqual((chosen(r),refined(r),s.budget),(own('139_style_campaign'),['R-STYLES@2','R-STYLE-CAMPAIGN@1'],{'compute':8,'money':8,'attention':1}))
        s2=state(*STYLES,'138_routed_unmatched');k2=Kernel(s2);asked2=k2.run_standing(execute=True)['runs'][0]['model_receipts'][-1]
        self.assertEqual(asked2,asked)                                                # the same question on a second State
        yes=answer(k2,asked2,'TRUE','charter-owner',execute=True)['runs'][0]         # yes: a new home. The complaint is closed for this desk by the owner's decision
        self.assertEqual((yes['status'],yes['work_state'],yes['actions'],yes['model_receipts'],yes['cost'],yes['selected_branch'],chosen(yes)),
                         ('SUPPORTED_BY_EVIDENCE','completed',[],[],{'compute':0,'money':0,'attention':0},'R-STYLES@1/OR3',[]))
        self.assertEqual((s2.budget,s2.providers),({'compute':10,'money':10,'attention':1},{'charter-owner':0,'ops-desk':4,'ops-head':1}))   # nothing but the question was ever paid, and no card's step ran
    def test_a_new_style_is_one_more_card_and_a_declaration_that_cites_the_one_it_replaces(self):
        d1=pack('133_complaint_desk')['rules'][0];d2=pack('139_style_campaign')['rules'][0]
        self.assertEqual((d2['replaces'],d2['branches'][:3],d2['branches'][3:]),(d1['id'],d1['branches'],[['styled_campaign','resolved_as_campaign']]))   # the older branches as they were, and one more
        for routed,branch in (('136_routed_by_the_book','OR1'),('137_routed_incident','OR2'),('138_routed_unmatched','OR3')):   # the two older cards and the fallback plan as before under the new declaration
            _,old=styled(routed);_,new=styled(routed,'139_style_campaign')
            self.assertEqual((new['status'],new['actions'],new.get('pending'),new.get('waits'),new['cost'],new['selected_branch']),
                             (old['status'],old['actions'],old.get('pending'),old.get('waits'),old['cost'],'R-STYLES@2/'+branch),routed)
            self.assertEqual(new['provenance'][:4],old['provenance'],routed)          # and they are the same files
        s=state(*STYLES,'138_routed_unmatched');before=whole(s)
        uncited=copy.deepcopy(pack('139_style_campaign'));del uncited['rules'][0]['replaces']
        refusal(self,lambda:s.apply(uncited))                                         # a declaration that does not cite the one it replaces is refused, card and all
        self.assertEqual((whole(s),'check-offer-8801@1' in s.methods),(before,False))
    def test_known_limits_any_verified_row_routes_two_true_rows_are_chosen_by_cost_and_an_open_question_outwaits_a_card(self):
        s=state(*STYLES);r=Kernel(s).on_event(names('incident','walk-in/anyone'),execute=True)['runs'][0]   # the row's source is not checked: any verified row on a style's name routes the goal
        self.assertEqual((r['status'],r['actions'],routers_word(r)),('WAITING',['write-cause-8801@1','ask-signoff-8801@1'],[('styled_incident','walk-in/anyone')]))
        s=state(*STYLES);s.apply(P(id='both',evidence=[names('by_the_book'),names('incident')]))
        r=Kernel(s).run_standing()['runs'][0]                                         # two styles marked true: the kernel chooses by cost, not by name
        self.assertEqual((r['status'],r['actions'],r['pareto_options']),('PLAN_READY',['match-ledger-8801@1','post-reversal-8801@1'],2))
        r=styled('136_routed_by_the_book','138_routed_unmatched',execute=False)[1]    # a style and unmatched both marked true: the question is the cheaper plan
        self.assertEqual((r['status'],r['actions'],r['pareto_options']),('PLAN_READY',['ask-new-home-8801@1'],2))
        s=state(*STYLES,'138_routed_unmatched');k=Kernel(s);k.run_standing(execute=True)   # the question is out; the router then names a declared style
        r=k.on_event(names('by_the_book'),execute=True)['runs'][0]
        self.assertEqual((r['status'],r['actions'],r['waits'],s.budget),('WAITING',[],['ask-new-home-8801@1'],{'compute':10,'money':10,'attention':1}))   # waiting costs nothing, so the goal waits for the owner and the card does not run
        back=k.on_event(dict(names('unmatched'),truth='FALSE'),execute=True)['runs'][0]   # until the router takes its unmatched word back: then the card runs, and the question stays answerable
        self.assertEqual((back['status'],back['actions'],[v['issued']['ask']['to'] for v in open_asks(s).values()]),
                         ('LOCAL_MODEL_EFFECTS_RECORDED',['match-ledger-8801@1','post-reversal-8801@1'],['charter-owner']))
    def test_the_record_holds_the_looks_and_the_unmatched_one_is_the_case(self):
        data=record();sc=data['scenes']['queue_styles'];case=[c for c in data['cases'] if c['id']=='59_style_unmatched'][0]
        want={'unrouted':[],'by_the_book':['136_routed_by_the_book'],'incident':['137_routed_incident'],'unmatched':['138_routed_unmatched'],
              'old_style_under_new':['136_routed_by_the_book','139_style_campaign'],'other_old_style_under_new':['137_routed_incident','139_style_campaign']}
        for name,more in want.items():
            self.assertEqual(sc[name]['runs'][0]['trace_root_sha256'],styled(*more)[1]['trace_root_sha256'],name)
        self.assertEqual((case['outcome']['trace_root_sha256'],case['packs'],case['outcome']['learning']),(sc['unmatched']['runs'][0]['trace_root_sha256'],STYLES+['138_routed_unmatched'],[]))
        self.assertEqual(sc['unlisted']['runs'][0]['trace_root_sha256'],sc['unrouted']['runs'][0]['trace_root_sha256'])
        self.assertEqual([sc[key]['runs'][0]['status'] for key in ('answered_no','new_style','answered_yes')],['REFUSED','LOCAL_MODEL_EFFECTS_RECORDED','SUPPORTED_BY_EVIDENCE'])


class SceneFilesTests(unittest.TestCase):
    """Each of the three scene files states, at its top level, how many looks and runs its sequence records."""
    def test_each_scene_file_states_the_looks_and_the_runs_its_sequence_records(self):
        def count(v):   # a look: a dict that holds a list under the key runs. A run: a dict with the keys trace and trace_root_sha256. Counted wherever they stand
            looks,runs=(int(type(v.get('runs')) is list),int('trace' in v and 'trace_root_sha256' in v)) if type(v) is dict else (0,0)
            for x in (v.values() if type(v) is dict else v if type(v) is list else ()):
                a,b=count(x);looks+=a;runs+=b
            return looks,runs
        scenes=record()['scenes']
        for name,want in (('queue_rank',(2,8)),('queue_provenance',(2,2)),('queue_styles',(11,10))):
            body=ast.parse((ROOT/'tools'/'scenes'/(name+'.py')).read_text()).body
            stated=tuple([n.value.value for n in body if isinstance(n,ast.Assign) and len(n.targets)==1 and getattr(n.targets[0],'id',None)==word] for word in ('LOOKS','RUNS'))
            self.assertEqual((stated,count(scenes[name])),(([want[0]],[want[1]]),want),name)   # each stated once, as a number, and the sequence in the built record holds exactly that many


class QueueChecksTests(unittest.TestCase):
    """The independent checks S80 to S89 are run by the verifier, pass on the record and fail on forged copies of it."""
    def test_the_verifier_runs_the_queue_checks_and_each_claim_fails_on_forged_records(self):
        v=verifier();text=(ROOT/'results'/'actual_run_records.json').read_text();data=json.loads(text)
        seen={t['id']:(t['pass'],t['detail']) for t in v.inspect(data)['checks']}
        number=lambda cid:cid.split('_')[0]                                           # S84 of S84_each_row_...: the whole number, so S201 is not read as S20
        mine_numbers=('S80','S81','S82','S83','S84','S85','S86','S87','S88','S89')
        mine={cid:ok for cid,(ok,_) in seen.items() if number(cid) in mine_numbers}
        self.assertEqual((len(mine),all(mine.values())),(10,True),{cid:seen[cid] for cid in mine if not mine[cid]})
        self.assertEqual([seen[cid][1] for cid in sorted(mine) if number(cid) in ('S82','S85','S88')],['[]']*3)   # none of the module's own forgeries survived
        self.assertNotIn('queue_reads_only_the_record',seen)                          # the verifier ran the module: it imports nothing of the lab
        self.assertNotIn('qa/checks/queue.py',seen)                                   # (confirming round) the line above names a refused module as an earlier applier's verifier did, and cannot fail on this one: here a module that is refused, raises or gives no row is one failed row named after its file
        ns={};exec(compile((ROOT/'qa'/'checks'/'queue.py').read_text(),'qa/checks/queue.py','exec'),ns)   # the check module, loaded the way the verifier loads it
        def claims(d):return {**ns['rank_claims'](d,ROOT,v.sha),**ns['provenance_claims'](d,ROOT,v.sha,v.check_chain),**ns['style_claims'](d,ROOT,v.sha),**ns['every_case_claims'](d,ROOT,v.sha,v.check_chain)}
        self.assertEqual((sorted(cid[:3] for cid in claims(data)),set(claims(data).values())),(['S80','S81','S83','S84','S86','S87','S89'],{True}))
        for broken in (lambda d:d.pop('scenes'),lambda d:d.update(cases={}),lambda d:d['scenes'].update(queue_styles=7)):   # a record the claims cannot read: failed rows under the module's own numbers, never an error and never another id
            d=json.loads(text);broken(d);rows=ns['checks'](d,ROOT,v.sha,v.check_chain)
            self.assertTrue(rows and all(type(r) is tuple and len(r)==3 and type(r[1]) is bool and type(r[2]) is str and number(r[0]) in mine_numbers for r in rows) and not all(r[1] for r in rows),rows)
        def failed(change):
            d=json.loads(text);change(d)
            try:return {cid[:3] for cid,ok in claims(d).items() if not ok}
            except Exception:return None   # a record so wrong that the claims cannot be read has failed too
        p=lambda d:d['scenes']['queue_provenance'];case=lambda d,cid:[c for c in d['cases'] if c['id']==cid][0]
        d=json.loads(text);p(d)['answered_yes']['event'].update(source='STAMP:mallory')   # once through the whole verifier: a yes stamped by somebody else
        failing={number(t['id']) for t in v.inspect(d)['checks'] if not t['pass']}
        self.assertTrue({'S84','S85'}<=failing and not failing&{'S80','S81','S82','S83','S86','S87','S88','S89'},failing)   # the claim itself, and the check that says the claims hold before it forges them; no other check of this version. Beside them the add-on base's own check fails: the forged sequence is no longer the one that was sealed (S201)
        for change,expect in ((lambda d:d['scenes']['queue_rank']['ranking']['goals'].reverse(),'S80'),
                              (lambda d:d['scenes']['queue_rank']['before_ranking']['budget'].update(attention=99),'S80'),
                              (lambda d:d['scenes']['queue_rank']['as_ranked']['runs'][3].update(actions=['call-1041@1']),'S81'),
                              (lambda d:p(d)['decisions'][3].update(authority_verdict='granted'),'S83'),
                              (lambda d:case(d,'58_gate_decisions')['derived_state']['budget_after'].update(money=9),'S83'),
                              (lambda d:p(d)['answered_yes']['event'].update(source='STAMP:mallory'),'S84'),
                              (lambda d:p(d)['answered_yes']['event'].update(answers='0'*64,verified=False,final=False),'S84'),
                              (lambda d:p(d)['answered_no']['event'].update(final=1),'S84'),
                              (lambda d:d['scenes']['queue_styles']['after_unmatched']['budget'].update(compute=9),'S87'),
                              (lambda d:d['scenes']['queue_styles']['after_new_style']['budget'].update(money=10),'S87'),
                              (lambda d:case(d,'59_style_unmatched')['run']['runs'].append(dict(case(d,'59_style_unmatched')['run']['runs'][0])),'S87'),
                              (lambda d:case(d,'30_stop')['run']['runs'][0]['stopped'].update(reason='Handler refused: something else'),'S84'),
                              (lambda d:case(d,'23_capacity')['run']['runs'][0]['provenance'][-1].update(sha256='0'*64),'S89')):
            bad=failed(change)
            self.assertTrue(bad is None or expect in bad,(expect,bad))


class ConfirmingRoundTests(unittest.TestCase):
    """What the confirming round found (two refuters, on the promoted base), settled without new code. Each limit the passage states since then is pinned here as it
    stands today, and each one-clause edit of the two extensions that the tests above let live has one assertion here that fails with it. Nothing here changes what
    the version does: a fix that needs new code is the next version's, with its own review."""
    def _checks(self):   # the verifier, the check module loaded the way the verifier loads it, and its claims on a record
        v=verifier();ns={};exec(compile((ROOT/'qa'/'checks'/'queue.py').read_text(),'qa/checks/queue.py','exec'),ns)
        return v,ns,lambda d:{**ns['rank_claims'](d,ROOT,v.sha),**ns['provenance_claims'](d,ROOT,v.sha,v.check_chain),**ns['style_claims'](d,ROOT,v.sha),**ns['every_case_claims'](d,ROOT,v.sha,v.check_chain)}

    # ---- R31b
    def test_confirm_ranking_again_after_another_pack_applies_the_ranking_again(self):
        s=state(QUEUE);rank(s,RANKED);two=[QUEUE,RANKED];named=lambda:[p['pack'] for p in s.loaded]
        rank(s,(RANKED+'x')[:-1]);self.assertEqual(named(),two)                         # ranked again under the same name written anew (an equal text, another object): nothing is applied
        Kernel(s).run_standing(execute=True);rank(s,RANKED);self.assertEqual(named(),two)   # ranked again after a look: nothing is applied
        told=Kernel(s).on_event({'predicate':'desk_open','truth':'TRUE','verified':True,'source':'fixture/desk','version':'1'},execute=True)
        rank(s,RANKED);self.assertEqual((told['status'],named()),('RECONCILED',two))       # and after an event: nothing is applied
        s.apply(P(id='a-note',evidence=[{'predicate':'desk_staffed','truth':'TRUE','verified':True,'source':'fixture/desk','version':'1'}]))
        self.assertEqual(s.goals,pack(RANKED)['goals'])                                 # after any other pack the queue is still in the ranking's order ...
        rank(s,RANKED);self.assertEqual((s.goals,named()),(pack(RANKED)['goals'],two+['a-note',RANKED]))   # ... and the same ranking is applied again all the same: it is no longer the State's last pack
        self.assertEqual([[p['pack'] for p in r['provenance']] for r in Kernel(s).run_standing()['runs']],[two+['a-note',RANKED]]*4)   # so every later run names it twice
    def test_confirm_a_goals_pack_under_the_rankings_name_is_not_the_ranking(self):
        s=state(QUEUE);want=ranking(s)                                                  # unnamed, the ranking is called queue-ranked
        s.apply(P(id='queue-ranked',goals=want['goals']))                               # a person's goals pack under that very name, the goals already in the ranking's order, and no reasons in it
        self.assertEqual((s.goals,s.loaded[-1]['pack'],s.loaded[-1]['sha256']==digest(want)),(want['goals'],'queue-ranked',False))
        kept=rank(s);is_ranking={'pack':'queue-ranked','sha256':digest(want)}           # the last pack bears the name and the queue is in order, but it is not that very pack: the ranking is applied
        self.assertEqual((kept,[p['pack'] for p in s.loaded],s.loaded[-1]),(want,[QUEUE,'queue-ranked','queue-ranked'],is_ranking))
        self.assertTrue(all(r['provenance'][-1]==is_ranking for r in Kernel(s).run_standing()['runs']))   # so the ranking that rank() hands back is one every later run names
    def test_confirm_the_ranking_pack_puts_back_the_queue_it_ranked(self):
        s=state(QUEUE);s.apply(P(id='one-more',goals=pack(QUEUE)['goals']+['loan_1045_promise']))   # the queue changed since it was ranked: a fifth goal
        self.assertEqual((len(s.goals),s.goals[-1]),(5,'loan_1045_promise'))
        s.apply(pack(RANKED))                                                           # known limit: pack 131 is a goals pack like any other
        self.assertEqual(s.goals,pack(RANKED)['goals'])                                 # the four goals it ranked, in its order: the fifth has left the queue
        self.assertEqual([r['goal'] for r in Kernel(s).run_standing()['runs']],pack(RANKED)['goals'])
    def test_confirm_a_held_goal_is_held_again_at_the_next_look(self):
        s=state(QUEUE,RANKED);k=Kernel(s);first=k.run_standing(execute=True);left=dict(s.budget)
        held=lambda res:[(r['goal'],r['status'],[(e['data']['methods'],e['data']['accepted'],e['data']['blockers']) for e in r['trace'] if e['operation']=='ADMISSION']) for r in res['runs'] if r['work_state']=='blocked']
        turned_away=[(L44,'RESOURCE_REQUIRED',[(['call-1044@1'],False,['RESOURCE_REQUIRED'])])]
        self.assertEqual((held(first),left['attention']),(turned_away,0))
        second=k.run_standing(execute=True)                                             # known limit: nothing tries the held goal again but the next look, which asks the gate for it again ...
        self.assertEqual((held(second),s.budget),(turned_away,left))                    # ... and on the same books it is turned away again, on the same line
        self.assertEqual([(r['status'],r['actions']) for r in second['runs'] if r['goal']!=L44],[('SUPPORTED_BY_EVIDENCE',[])]*3)   # the three that ran stand on their evidence and pay nothing more
        s.apply(P(id='one-more-call',budget={'attention':1}));third=k.run_standing(execute=True)   # it runs once the books change: attention for one more call
        self.assertEqual([(r['status'],r['actions']) for r in third['runs'] if r['goal']==L44],[('LOCAL_MODEL_EFFECTS_RECORDED',['call-1044@1'])])

    # ---- R91
    def test_confirm_a_row_gives_the_first_questions_receipt_only(self):
        ask=lambda n,*needs:{'id':'ask-'+n,'effect':n+'_ok','requires':list(needs),'provider':'head','grant':'g','cost':{'attention':1},'action':'ask','ask_to':'head','question':'May '+n+' go ahead?'}
        do=lambda *needs:{'id':'do','effect':'done','requires':list(needs),'provider':'desk','grant':'g','cost':{'compute':1},'action':'simulate_fact'}
        world=lambda *methods:State.from_packs([P(id='asks',goals=['done'],methods=list(methods),providers={'head':2,'desk':1},grants=['g'])])
        cites=lambda r:(r['phase'],r['authority_verdict'],[f['value'] for f in r['factors'] if f['type'] in ('decision','asked')],r['approval_ref'],r['channels'])
        yes_a,yes_b='a_ok: TRUE, decided by STAMP:head','b_ok: TRUE, decided by STAMP:head'
        s=world(ask('a'),ask('b'),do('a_ok','b_ok'));k=Kernel(s);before=books(s)        # one step that needs two answers
        first=k.run_standing(execute=True);qa=first['runs'][0]['model_receipts'][-1]
        second=answer(k,qa,'TRUE','head',execute=True);qb=second['runs'][0]['model_receipts'][-1];third=answer(k,qb,'TRUE','head',execute=True)
        row=decisions(first['runs']+second['runs']+third['runs'],before)[-1]
        self.assertEqual((third['runs'][0]['actions'],cites(row)),(['do'],('step','granted',[yes_a,yes_b],qa['sha256'],['STAMP:head'])))   # the step that ran on both: each decision is listed, and one receipt is given, the first question's
        self.assertNotEqual(qa['sha256'],qb['sha256']);self.assertNotIn(qb['sha256'],json.dumps(row))   # known limit: the receipt of the second question is nowhere on the row
        s=world(ask('a'),ask('b','a_ok'),do('b_ok'));k=Kernel(s);before=books(s)        # a question that may only be asked once another was answered yes
        first=k.run_standing(execute=True);qa=first['runs'][0]['model_receipts'][-1]
        second=answer(k,qa,'TRUE','head',execute=True);qb=second['runs'][0]['model_receipts'][-1]
        self.assertEqual([cites(r) for r in decisions(first['runs']+second['runs'],before)][2:],
                         [('plan','granted',[yes_a],qa['sha256'],['STAMP:head']),('step','escalated',['head: b_ok'],qb['sha256'],['head'])])   # known limit: the ask that rests on the yes reads escalated and cites its own question only; the yes shows on the plan row alone
    def test_confirm_a_yes_that_only_a_rule_reads_is_not_cited(self):
        def owner_says(truth):   # the unmatched complaint (case 59): the charter owner is asked, and answers. The receipt of the question, the run of the answer and that run's rows
            s=state(*STYLES,'138_routed_unmatched');k=Kernel(s);before=books(s);first=k.run_standing(execute=True);asked=first['runs'][0]['model_receipts'][-1]
            run=answer(k,asked,truth,'charter-owner',execute=True)['runs'][0];return asked,run,decisions(first['runs']+[run],before)[2:]
        asked,run,rows=owner_says('TRUE')
        closes=[e['data'] for e in run['trace'] if e['operation']=='ASK_CLOSED'];reads=[e['data'] for e in run['trace'] if e['operation']=='RETAIN' and e['data']['predicate']=='new_home_8801_agreed']
        self.assertEqual((run['status'],closes,reads),('SUPPORTED_BY_EVIDENCE',[{'ask':'lendco/credit-ops|new_home_8801_agreed','receipt':asked['sha256'],'truth':'TRUE','source':'STAMP:charter-owner'}],
                         [{'predicate':'new_home_8801_agreed','source':'STAMP:charter-owner','version':'ask-'+asked['sha256'][:12]}]))   # the run's own chain reads the decided fact and closes its question ...
        self.assertEqual([(r['phase'],r['authority_verdict'],r['approval_ref'],r['channels'],kinds(r)) for r in rows],[('plan','granted',None,[],['budget_fits']*3)])   # ... known limit: but no step requires that fact (a rule reads it), so the one row of the yes names no decider and no receipt
        asked,run,rows=owner_says('FALSE')
        self.assertEqual([(r['phase'],r['authority_verdict'],r['approval_ref'],r['channels'],[f['value'] for f in r['factors']]) for r in rows],
                         [('decision','denied',asked['sha256'],['STAMP:charter-owner'],['new_home_8801_agreed: FALSE, decided by STAMP:charter-owner'])])   # the no on the same question is cited in full
        sc=record()['scenes']['queue_styles'];yes=sc['answered_yes']['runs'][0]         # the recorded owner's yes (C14) is such a yes: projected from the record's own runs it is that one row
        again=decisions(sc['unmatched']['runs']+[yes],books(state(*STYLES,'138_routed_unmatched')))[2:]
        self.assertEqual([(r['turn_id'],r['phase'],r['authority_verdict'],r['approval_ref'],r['channels']) for r in again],[(yes['trace_root_sha256'],'plan','granted',None,[])])
    def test_confirm_a_decision_that_answers_no_ask_cites_no_question(self):
        told=lambda rows:[(r['phase'],r['authority_verdict'],r['approval_ref'],r['channels'],kinds(r).count('decision')) for r in rows if r['work_ref']=='limit_7003_raised']
        final=lambda truth,source,version:{'predicate':'head_7003_approved','truth':truth,'verified':True,'final':True,'source':source,'version':version}
        unsaid=[('plan','granted',None,[],0),('step','granted',None,[],0)]
        s=State.from_packs([pack('132_loan_desk'),P(id='decided',evidence=[final('TRUE','STAMP:credit-head','d1')])])   # a yes that a named party decided with no question out
        k=Kernel(s);b=books(s);rows=decisions(k.run_standing(execute=True)['runs'],b)
        self.assertEqual((told(rows),open_asks(s)),(unsaid,{}))                       # known limit: the step runs on it, nobody is asked, and no row cites it
        s,k,before,result,rows,asked=desk();no=answer(k,asked,'FALSE','credit-head',execute=True)   # the question is closed with a no ...
        yes=k.on_event(final('TRUE','STAMP:credit-head','d2'),execute=True)             # ... and the same party then decides yes, in a row that answers no ask
        self.assertEqual(([r['status'] for r in yes['runs']],told(decisions(result['runs']+no['runs']+yes['runs'],before))[-2:]),(['LOCAL_MODEL_EFFECTS_RECORDED'],unsaid))   # its rows do not cite the question that was answered no
        s,k,before,result,rows,asked=desk();no=answer(k,asked,'FALSE','credit-head',execute=True)
        other=k.on_event(final('FALSE','STAMP:risk-head','d2'),execute=True)            # a second no, from another party, after the question was closed
        self.assertEqual(([r['status'] for r in other['runs']],told(decisions(result['runs']+no['runs']+other['runs'],before))[-2:]),
                         (['REFUSED'],[('decision','denied',asked['sha256'],['STAMP:credit-head'],1),('decision','denied',None,['STAMP:risk-head'],1)]))   # it is denied by its own source and does not cite the credit head's question
    def test_confirm_a_lines_number_is_read_by_value(self):
        s,k,before,result,rows,asked=desk();odd=copy.deepcopy(result['runs'])
        for run in odd:                                                                 # every line numbered again, true for 1 and a fraction for every other number (2.0 for 2), and the chain hashed again
            for i,row in enumerate(run['trace']):row['seq']=True if i==0 else float(i+1)
            rehash(run)
        v=verifier()
        self.assertEqual(([v.check_chain(r['trace']) for r in result['runs']],[v.check_chain(r['trace']) for r in odd]),([True]*6,[False]*6))   # the lab's verifier reads a line's number by type and refuses each such chain
        got=decisions(odd,before)                                                       # known limit: the projection compares by value (true is 1, 2.0 is 2), so the chains hold for it ...
        self.assertEqual([(r['work_ref'],r['phase'],r['authority_verdict']) for r in got],[(r['work_ref'],r['phase'],r['authority_verdict']) for r in rows])
        self.assertEqual(sorted({f['source_ref'] for r in got for f in r['factors']}),['trace:10.0','trace:12.0','trace:3.0','trace:6.0','trace:8.0','trace:9.0'])   # ... and its rows cite the numbers as it found them
    def test_confirm_a_look_read_back_from_the_record_gives_the_rows_of_the_live_look(self):
        data=record();sc=data['scenes']['queue_provenance'];runs=lambda cid:[c for c in data['cases'] if c['id']==cid][0]['run']['runs']
        s,k,before,result,rows,asked=desk();after=books(s)                              # the day, live: its rows, and the books it left
        self.assertEqual(decisions(runs('58_gate_decisions'),before),rows)              # the day's runs as the record holds them (read back from JSON, every text and number a new object) give the live rows
        self.assertEqual(decisions(runs('30_stop'),books(state(*STOPPED))),sc['decisions_of_a_stopped_step'])   # so do the stopped run's ...
        self.assertEqual((decisions(sc['answered_no']['runs'],after),decisions(sc['answered_yes']['runs'],after)),(sc['decisions_after_no'],sc['decisions_after_yes']))   # ... and the runs of the two answers, on the books the day left
    def test_confirm_a_blocked_run_that_read_a_standing_no_has_no_not_evaluated_row(self):
        known=lambda p,truth,**more:dict({'predicate':p,'truth':truth,'verified':True,'version':'1'},**more)
        s=State.from_packs([P(id='blocked',goals=['g'],rules=[{'id':'R1','head':'g','branches':[['a'],['b']],'approved':True},{'id':'R2','head':'b','branches':[['c']],'approved':True}],
                              evidence=[known('a','FALSE',final=True,source='STAMP:head'),known('c','TRUE',source='fixture/x'),known('b','FALSE',source='fixture/x')])])
        b=books(s);run=Kernel(s).run_standing(execute=True)['runs'][0];rows=decisions([run],b)
        self.assertEqual((run['status'],run['stop_reasons'],[e['operation'] for e in run['trace'] if e['operation'] in ('ADMISSION','REFUSED','BLOCK')]),
                         ('EVIDENCE_CONFLICT',['EVIDENCE_CONFLICT','REFUSED'],['REFUSED','BLOCK']))   # the run never reached the gate; on its way it read a standing no
        self.assertEqual([(r['phase'],r['authority_verdict'],r['channels'],r['approval_ref'],r['factors']) for r in rows],
                         [('decision','denied',['STAMP:head'],None,[{'type':'decision','value':'a: FALSE, decided by STAMP:head','source_ref':'trace:3'}])])   # known limit: that no is its one row; there is no not_evaluated row ...
        self.assertNotIn('EVIDENCE_CONFLICT',json.dumps(rows))                          # ... and the reason the run blocked for is on no row
        s=State.from_packs([P(id='unsigned',goals=['g'],rules=[{'id':'R1','head':'g','branches':[['a']],'approved':True}],evidence=[known('a','FALSE',final=True)])])   # a decision row that names no source
        b=books(s);rows=decisions(Kernel(s).run_standing(execute=True)['runs'],b)
        self.assertEqual([(r['authority_verdict'],r['channels'],[f['value'] for f in r['factors']]) for r in rows],[('denied',[],['a: FALSE, decided by None'])])   # known limit: it reads decided by None, with no channel
    def test_confirm_one_unreadable_run_refuses_the_whole_call(self):
        deep=lambda n:[deep(n-1)] if n else 0
        def handler(s,m,mid,deps):
            s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':'LOCAL_MODEL:'+mid,'version':'1'});return {'made':deep(12)}   # thirteen levels below its own object: one more than the projection reads
        st=State(actions={'simulate_fact':ACTIONS['simulate_fact'],'test_deep':{'run':handler}})
        make=lambda goal,kind:{'id':'make-'+goal,'effect':goal,'provider':'p','grant':'g','cost':{'compute':1},'action':kind}
        st.apply(P(id='three',goals=['a','b','c'],budget={'compute':2},methods=[make('a','simulate_fact'),make('b','test_deep'),make('c','simulate_fact')],providers={'p':3},grants=['g']))
        before=books(st);runs=Kernel(st).run_standing(execute=True)['runs'];after=books(st)
        self.assertEqual([r['status'] for r in runs],['LOCAL_MODEL_EFFECTS_RECORDED','LOCAL_MODEL_EFFECTS_RECORDED','RESOURCE_REQUIRED'])   # the second goal's step returns too deep a receipt, and the kernel takes it
        refusal(self,lambda:decisions(runs[1:2],before),NOT_DATA)
        refusal(self,lambda:decisions([[0]*BOUND],before),NOT_DATA)                     # (a run that is no object is not data, however large it is: it is not told it is too large)
        refusal(self,lambda:decisions(runs,before),NOT_DATA)                            # known limit: that one run refuses the whole call: no row for the two runs that can be read
        self.assertEqual(said(decisions(runs[:1],before)),[('plan','granted'),('step','granted')])   # the run before it reads when it is handed in alone
        for later in (runs[2:],[runs[0],runs[2]]):refusal(self,lambda:decisions(later,before),UNEXPLAINED)   # the run after it does not, on books that miss what the unread run paid
        self.assertEqual(said(decisions(runs[2:],after)),[('plan','denied')])           # it reads on the books as the unread run left them: here the books after the look, because it is the last run
    def test_confirm_only_a_receipt_parked_by_exactly_true_reads_escalated(self):
        def tells(detail):   # one step of a kind made here, whose handler makes its effect and returns this detail: the run and its rows
            def handler(s,m,mid,deps):
                s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':'LOCAL_MODEL:'+mid,'version':'1'});return dict(detail)
            st=State(actions={'test_tells':{'run':handler}})
            st.apply(P(id='tells',goals=['done'],methods=[{'id':'make','effect':'done','provider':'p','grant':'g','cost':{'compute':1},'action':'test_tells'}],providers={'p':1},grants=['g']))
            bk=books(st);made=Kernel(st).run_standing(execute=True)['runs'];return made[0],decisions(made,bk)
        ask={'to':'somebody','predicate':'done'}
        for detail in ({'ask':ask},{'ask':ask,'parked':1}):                             # a receipt of another kind that carries an ask and is not parked, or is parked by 1 and not by true
            run,got=tells(detail);receipt=run['model_receipts'][0]
            self.assertEqual((receipt['ask'],receipt.get('parked')),(ask,detail.get('parked')))
            self.assertEqual([(r['phase'],r['authority_verdict'],r['approval_ref'],r['output_ref'],r['channels'],kinds(r).count('asked')) for r in got],
                             [('plan','granted',None,None,[],0),('step','granted',None,receipt['sha256'],[],0)],detail)   # known limit: it reads as a granted step that ran, never as escalated: only a receipt parked by exactly true, as the ask kind's is, reads as a question
    def test_confirm_forged_traces_that_one_clause_each_refuses(self):
        s,k,before,result,rows,asked=desk();runs=result['runs']
        gate=lambda run:[e for e in run['trace'] if e['operation']=='ADMISSION']
        def higher(run):                                                                # every line numbered 100 higher, and the chain hashed again
            for row in run['trace']:row['seq']+=100
            rehash(run)
        def says_yes(run):gate(run)[0]['data'].update(accepted=True);rechain(run)       # the fee's gate line says accepted and still names its blocker
        def says_one(run):gate(run)[0]['data'].update(accepted=1);rechain(run)          # the first goal's plan is accepted by 1, not by true: a verdict is read by its type
        def other_receipt(run):[e for e in run['trace'] if e['operation']=='LOCAL_EFFECT'][0]['data']['receipt'].update(method='release-funds-7001@1');rechain(run)   # the first step is followed by the second step's receipt
        def two_at_once(run):gate(run)[1]['data'].update(methods=['verify-kyc-7001@1','release-funds-7001@1'],cost={'compute':2,'money':2,'attention':0});rechain(run)   # after the plan was chosen the gate is asked about two steps at once, and the first one's receipt follows
        def paid_all_the_same(run):                                                     # the fee, turned away as a plan, dressed as a step the gate turned away and that left a receipt all the same
            t=run['trace'];at=next(i for i,e in enumerate(t) if e['operation']=='ADMISSION')
            t.insert(at,{'operation':'SELECT','data':{'actions':['waive-fee-7002@1']}})
            t.insert(at+2,{'operation':'LOCAL_EFFECT','data':{'receipt':{'method':'waive-fee-7002@1','scope':run['scope'],'action':'simulate_fact','status':'LOCAL_ONLY'}}});rechain(run)
        for at,change,message in ((0,higher,BROKEN),(1,says_yes,UNEXPLAINED),(0,says_one,UNEXPLAINED),(0,other_receipt,NOT_KERNEL),(0,two_at_once,NOT_KERNEL),(1,paid_all_the_same,NOT_KERNEL)):
            f=copy.deepcopy(runs);change(f[at])
            with self.subTest(forged=change.__name__):refusal(self,lambda:decisions(f,before),message)
        s2,k2,b2,res2,rows2=looked(*STOPPED);halted=copy.deepcopy(res2['runs'])        # case 30_stop: the stop that follows the fourth step is made to name the first
        [e for e in halted[0]['trace'] if e['operation']=='STEP_STOPPED'][0]['data'].update(method=halted[0]['actions'][0]);rechain(halted[0])
        refusal(self,lambda:decisions(halted,b2),NOT_KERNEL)
        self.assertEqual((decisions(runs,before),decisions(res2['runs'],b2)),(rows,rows2))   # the day and the stopped run, as they were, still read

    # ---- R101
    def test_confirm_a_card_may_lean_on_another_cards_slots_and_the_router_needs_the_desk_first(self):
        s=state('133_complaint_desk','139_style_campaign');k=Kernel(s)                 # the desk with the campaign card alone, without the two older cards
        self.assertEqual(('providers' in pack('139_style_campaign'),s.providers),(False,{'charter-owner':1}))   # that card declares no provider slot of its own
        r=k.on_event(names('campaign'),execute=True)['runs'][0]
        self.assertEqual((r['status'],r['stop_reasons'],r['actions'],[(e['data']['methods'],e['data']['accepted'],e['data']['blockers']) for e in r['trace'] if e['operation']=='ADMISSION']),
                         ('QUERY_EVIDENCE',['PROVIDER_REQUIRED','QUERY_EVIDENCE'],[],[(own('139_style_campaign'),False,['PROVIDER_REQUIRED'])]))   # known limit: its plan is turned away on the provider line: it runs on the ops-desk slots that cards 134 and 135 declare
        s=state('138_routed_unmatched',*STYLES);r=Kernel(s).run_standing(execute=True)['runs'][0]   # the router's pack applied before the desk pack
        unscoped=[n for n in ('136_routed_by_the_book','137_routed_incident','138_routed_unmatched') if 'scope' not in pack(n)]
        self.assertEqual((len(unscoped),[key for key in s.evidence if key.endswith('|styled_unmatched')],s.scope),(3,[State().scope+'|styled_unmatched'],'lendco/credit-ops'))   # packs 136 to 138 name no scope: the row is stored under the scope a State starts with, not the desk's
        self.assertEqual((r['status'],asked_for(r),r['model_receipts']),('QUERY_EVIDENCE',[('QUERY_EVIDENCE','styled_by_the_book'),('QUERY_EVIDENCE','styled_incident'),('QUERY_EVIDENCE','styled_unmatched')],[]))   # known limit: the goal does not read it, and asks for the router's row
        self.assertEqual(styled('138_routed_unmatched')[1]['status'],'WAITING')         # in case 59's order, the desk first, the same packs wait on the owner

    # ---- the checks and the record
    def test_confirm_s89_holds_a_fixed_count_of_cases(self):
        v,ns,claims=self._checks();data=record();s89=lambda d:list(ns['every_case_claims'](d,ROOT,v.sha,v.check_chain).values())
        tree=ast.parse((ROOT/'qa'/'checks'/'queue.py').read_text())
        written=[n.comparators[0].value for n in ast.walk(tree) if isinstance(n,ast.Compare) and isinstance(n.left,ast.Call) and getattr(n.left.func,'id','')=='len'
                 and [getattr(a,'id','') for a in n.left.args]==['scope'] and len(n.comparators)==1 and isinstance(n.comparators[0],ast.Constant)]
        self.assertEqual((written,s89(data)),([sum(1 for c in data['cases'] if covered(c['id']))],[True]))   # the count is a number written in the check: today it is the number of covered cases the record holds
        more=json.loads(json.dumps(data));twin=json.loads(json.dumps([c for c in more['cases'] if c['id']=='24_budget'][0]));twin['id']='24_budget_again';more['cases'].append(twin)
        self.assertEqual((covered(twin['id']),s89(more)),(True,[False]))                # known limit: one more case numbered up to 50, a copy of an honest one with nothing wrong in it, fails S89 (the totals of test_on_every_case_... above are fixed in the same way)
    def test_confirm_what_no_check_reads_passes_the_verifier(self):
        v,ns,claims=self._checks();text=(ROOT/'results'/'actual_run_records.json').read_text();honest=json.loads(text)
        gate=lambda r:[e for e in r['trace'] if e['operation']=='ADMISSION'][0]['data'];q=lambda d:d['scenes']['queue_rank']
        def cost(d):                                                                    # the gate lines of the two goals held in the listed look say they were short of money, not of attention
            for r in q(d)['as_listed']['runs']:
                if r['work_state']=='blocked':gate(r).update(cost={'compute':1,'money':99,'attention':0});rechain(r)
        def invented(d):q(d)['as_listed'].update(served_impact=99)                      # a number nobody made, inside a look
        def refused_plan(d):r=d['scenes']['queue_styles']['by_the_book']['runs'][0];gate(r).update(accepted=False,blockers=['AUTHORITY_REQUIRED']);rechain(r)   # the plan of the by-the-book look reads refused at the gate, and the run ran
        def needs(d):q(d)['as_listed']['runs'][0]['needs'][0]='another_fact'            # what a run says it needed
        def branch(d):[c for c in d['cases'] if c['id']=='58_gate_decisions'][0]['run']['runs'][2].update(selected_branch='R-LIMIT-7003@1/OR9')   # the branch of a run of case 58
        changes=((cost,'queue_rank'),(invented,'queue_rank'),(refused_plan,'queue_styles'),(needs,'queue_rank'),(branch,None))
        self.assertEqual([v.sha(honest['scenes'][n])==honest['added']['scenes'][n] for n in ('queue_rank','queue_styles')],[True,True])   # each sequence is sealed in the record by its sha256
        for change,sequence in changes:
            d=json.loads(text);change(d)
            self.assertEqual(set(claims(d).values()),{True},change.__name__)            # known limit: S80 to S89 hold on a record with this one change
            if sequence:self.assertNotEqual(v.sha(d['scenes'][sequence]),d['added']['scenes'][sequence],change.__name__)   # what tells it is the seal the add-on base keeps over each sequence, while that seal stands
        d=json.loads(text)
        for change,_ in changes:change(d)
        for sequence in ('queue_rank','queue_styles'):d['added']['scenes'][sequence]=v.sha(d['scenes'][sequence])   # a forger who also makes the seals again
        self.assertEqual([t['id'] for t in v.inspect(d)['checks'] if not t['pass'] and ours(t['id'],80,89)],[])   # known limit: with all five the record passes every check of the base and of this version (a check another version brings may refuse it); only a make of the record tells (the test below)
    def test_confirm_the_sequences_and_own_cases_are_what_the_lab_makes_now(self):
        data=record();lab={'State':State,'Kernel':Kernel,'pack':pack,'answer':answer,'open_asks':open_asks,'Learner':Learner,'digest':digest}
        for name in ('queue_rank','queue_provenance','queue_styles'):                   # each scene file run again, as the lab runs it, and compared whole with the record: every run, gate line, snapshot and row
            ns={'__name__':'tools.scenes.'+name};exec(compile((ROOT/'tools'/'scenes'/(name+'.py')).read_text(),name+'.py','exec'),ns)
            self.assertEqual(json.loads(json.dumps(ns['scene'](dict(lab)))),data['scenes'][name],name)
        for cid,_,_,files,execute,_ in CASES:                                           # and the looks of the three own cases, made again: what each run says beside its trace too (its needs, its proof, its branch)
            if cid not in OWN:continue
            packs=[pack(n) for n in files];made=Learner.from_packs(packs).attach(Kernel(State.from_packs(packs)).run_standing(execute=execute))
            self.assertEqual(json.loads(json.dumps(made)),[c for c in data['cases'] if c['id']==cid][0]['run'],cid)


if __name__=='__main__':unittest.main()
