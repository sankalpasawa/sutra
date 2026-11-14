"""Numbers at the evidence door (matrix gap 9, ruling R22). One test per numbered claim of the README passage (C1 to C13),
one for the limits it lists, a seeded random walk, and one that holds the independent checks to the record on disk. The
kernel is not touched: without the adapter the same goal, rule, number and method end QUERY_EVIDENCE whatever the number
is (see the first-case test). The second round (two refuters on the first build) added, in the test of the claim each
belongs to: a row made two steps below a comparison (c05), the lint on the kernel's own evidence door (c10, c11), a band
whose rows carry two bounds (c06), the next run under the ceiling (c12), and the forgeries made whole (the test of the
independent checks). The last test holds two rules of the next applier: the scene file states its looks and runs, and a
method id names one method in the whole lab."""
# The confirming round (two refuters on the build the second round left) is settled without new code, by rulings R19 and R34 of the program: the tests named
# test_settled_* at the end of this file pin what its findings showed, as the delivery behaves today. Two comments in the tests of C6 and C9 below say more than the
# record does; the passage and test_settled_words_of_c06_c09_c11_and_the_second_half_of_limit_p say it as it is: of the six refusals in the record five are the adapter's
# sentences and one is the kernel's own, and the one look of the sequence that holds no run carries no cost receipts.
from pathlib import Path
import unittest, sys, json, copy, importlib.util
from fractions import Fraction
from decimal import Decimal
import re
def ours(cid, low, high):   # a check of the base (built in; the add-on base and its first case) or of this version: in a lab where other versions are laid, their checks stand beside these and may refuse the same forged record
    n = int(re.match(r'S(\d+)', cid).group(1)); return n < 60 or 200 <= n <= 219 or low <= n <= high
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest,ACTIONS,register
from tools.run_all import CASES,MORE,pack,scenario,extra_events,ask_events
from extensions.asks import answer,open_asks
from extensions.reflection import Learner
from extensions.numbers_lint import problems,ranked,shortfall,attach_shortfall
from extensions.numbers import SOURCE,NEGATED,LIMIT,exact,measured,compared,band,renumber,comparisons,attach,amount,cost_receipts

P2='sutra-extension/2';LOG='adapter:conformance/log@1';POLICY='policy:routine/conformance-band'
BAND=measured('fitness_band','0.9',source=POLICY,label='band-v1',unit='ratio')
BY={c[0]:c for c in CASES}
C63,C64,C65,C66='63_conformance_finding','64_conformance_in_band','65_loan_review_cost','66_review_queue'
OURS=(C63,C64,C65,C66)
CONFORM=['150_conformance_goal','151_conformance_theory','152_run_fitness','153_finding_method']
ALONE=['150_conformance_goal','151_conformance_theory','159_one_row_alone','153_finding_method']   # one comparison row authored alone, against a bound written into the comparison
BARE=['150_conformance_goal','151_conformance_theory','152_number_alone','153_finding_method']     # the number with no comparison row beside it
BLOCKS=('comparisons','comparisons_record','shortfall');W='sutra/workflows|'
def looks_of(seq):
    """Every look of the recorded sequence, in its order: the four cases, the next run of the queue, the number alone (twice), the row authored alone (twice), the events."""
    return ([x['look'] for x in seq['looks'].values()]+[seq['next_run']['look'],seq['bare']['look'],seq['bare']['again'],seq['alone']['look'],seq['alone']['again']]
            +[v for v in seq['events'].values() if isinstance(v,dict) and 'runs' in v])
def reading(value,label='run-0001',scope=None):return measured('run_fitness',value,source=LOG,label=label,unit='ratio',scope=scope)
def step(mid,effect,cost,action='simulate_fact',req=(),grant='g',provider='p',**kw):
    return dict(id=mid,effect=effect,requires=list(req),grant=grant,provider=provider,action=action,cost=dict(cost),approved=True,**kw)
def one_rule(branch):return {'id':'R-T@1','head':'run_judged','branches':[branch],'approved':True}
def verifier():
    """The independent verifier, loaded from its file (it is a script, not a package)."""
    spec=importlib.util.spec_from_file_location('independent_verify_for_numbers',ROOT/'qa'/'independent_verify.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
_SEQUENCE=[]
def recorded():
    """The recorded sequence of this version (scenes.numbers), made the way tools/run_all.py makes it; once per test run. Read, never changed."""
    if not _SEQUENCE:
        f=ROOT/'tools'/'scenes'/'numbers.py';ns={};exec(compile(f.read_text(),str(f),'exec'),ns)
        _SEQUENCE.append(ns['scene']({'State':State,'Kernel':Kernel,'pack':pack,'answer':answer,'open_asks':open_asks,'Learner':Learner,'digest':digest}))
    return _SEQUENCE[0]

class NumbersTests(unittest.TestCase):
    def _first(self,value='0.8',rows=True):
        """The first case in memory: the goal, the rule, the band kept as policy, one reading with (or without) both rows of the band, the finding method."""
        n=reading(value);ev=[n]+(band(n,'>=',BAND,'fitness_in_band','fitness_below_band') if rows else [])
        return State.from_packs([pack('150_conformance_goal'),pack('151_conformance_theory'),{'schema':P2,'id':'fitness','evidence':ev},pack('153_finding_method')])
    def _books(self,s):return digest({'e':s.evidence,'j':s.event_journal,'b':s.budget,'p':s.providers,'a':s.active_work,'g':s.goals,'m':s.methods,'r':s.rules})
    def _truths(self,s,*names):return [s.fact(p)['truth'] for p in names]

    def test_c01_a_number_is_exact_text_and_its_version_is_the_digest_of_its_reading(self):
        self.assertEqual((exact('0.30'),exact('4/5'),exact('007'),exact('0/5'),exact('9'*64)),(Fraction(3,10),Fraction(4,5),Fraction(7),Fraction(0),Fraction(int('9'*64))))
        junk=(0.8,8,True,None,float('nan'),'','NaN','nan','inf','1e-1','8e-1',' 0.8','0.8 ','0.8\n','+0.8','-0.8','.8','8.','1_0','1_5','15_','_15','1_000','1X5','1x5','1:5','1 5','0.8.1','4/5/6','4/0','4/','/5','0,8','1/2.5','0x10',
              '٠.٨','０.８','9'*65,b'0.8',Decimal('0.8'),Fraction(4,5),['0.8'],type('Text',(str,),{})('0.8'))
        NUMBER='A number is exact text: digits with one optional point, or digits/digits'   # the adapter's one sentence for what is no number
        for bad in junk:
            with self.assertRaises(ValueError,msg=repr(bad)) as refusal:exact(bad)
            self.assertEqual(str(refusal.exception),NUMBER,repr(bad))
        self.assertEqual((int('1_5'),measured('p','1',source='s',label='l')['unit']),(15,'1'))   # an underscore is a digit separator to Python's own parser and no part of a number here; a number with no unit named counts in ones
        self.assertEqual((Fraction('8e-1'),Fraction(' 0.8 '),Fraction('+0.8')),(Fraction(4,5),)*3)   # what the standard library's parser takes and the adapter refuses
        row=reading('0.8','run-1')
        self.assertEqual({k:v for k,v in row.items() if k!='version'},{'predicate':'run_fitness','truth':'TRUE','verified':True,'source':LOG,'value':'0.8','unit':'ratio','label':'run-1','evidence_kind':'NUMBER'})
        self.assertEqual(row['version'],'num-'+digest({'predicate':'run_fitness','value':'4/5','unit':'ratio','label':'run-1','source':LOG})[:16])   # the adapter sets the version: the digest of the reading
        self.assertEqual({reading(v,'run-1')['version'] for v in ('0.8','0.80','4/5','8/10','00.8')},{row['version']})   # one number, one version, however it is spelled
        others=[reading('0.95','run-1'),reading('0.8','run-2'),measured('run_fitness','0.8',source=LOG,label='run-1',unit='percent'),
                measured('run_fitness','0.8',source='another/log',label='run-1',unit='ratio'),measured('other_number','0.8',source=LOG,label='run-1',unit='ratio')]
        self.assertEqual(len({r['version'] for r in others}|{row['version']}),6)   # a new value under a reused label is a new version; so is a new label, unit, source or predicate
        for change,said in ((dict(value=0.8),NUMBER),(dict(value='0.8 '),NUMBER),(dict(source=''),'The source of a number row is a name'),(dict(label=None),'The label of a number row is a name'),(dict(unit=5),'The unit of a number row is a name'),
                            (dict(predicate=''),'The predicate of a number row is a name'),(dict(source=SOURCE),'A number does not come from the comparison adapter'),(dict(scope=''),'The scope of a number row is a name')):
            with self.assertRaises(ValueError,msg=change) as refusal:measured(**dict(dict(predicate='p',value='1',source='s',label='l',unit='u'),**change))
            self.assertEqual(str(refusal.exception),said,change)
        class Liar(dict):
            def get(self,key,default=None):return '0.95' if key=='value' else dict.get(self,key,default)
        forged=(dict(row,value='0.95'),dict(row,value=0.8),dict(row,version='run-1'),dict(row,verified=False),dict(row,verified=1),dict(row,truth='FALSE'),dict(row,final=True),
                dict(row,note='x'),{k:v for k,v in row.items() if k!='unit'},Liar(row),[row],None,'0.8')
        for bad in forged:   # the adapter compares only a row it would write itself: another value under the old version, a float, an added field, a crafted object are refused
            with self.assertRaises(ValueError,msg=repr(bad)[:70]):compared(bad,'>=','0.9','in_band')
        ran=[]
        class Key(str):   # a key that answers to the name 'predicate' and runs the caller's code when it is looked up
            def __hash__(self):return hash('predicate')
            def __eq__(self,other):ran.append(1);return str.__eq__(self,other)
        crafted={(Key('predicate') if k=='predicate' else k):v for k,v in row.items()}
        for use in (lambda:compared(crafted,'>=','0.9','in_band'),lambda:compared(row,'>=',crafted,'in_band'),lambda:renumber(Kernel(State()),crafted)):
            with self.assertRaises(ValueError):use()
        self.assertEqual(ran,[])   # a row with a key that is not plain text is refused before any of its code runs
        s=State();self.assertTrue(s.observe(row));self.assertEqual((s.fact('run_fitness')['truth'],s.fact('run_fitness')['value']),('TRUE','0.8'))   # the kernel stores the row and reads no number

    def test_c02_a_comparison_is_evidence_with_its_own_source_version_and_dependencies(self):
        n=reading('0.8');c=compared(n,'>=','0.9','in_band')
        recipe={'number':{'predicate':'run_fitness','value':'0.8','version':n['version']},'op':'>=','bound':{'literal':'0.9'}}
        lowest={'number':{'predicate':'run_fitness','value':'4/5','version':n['version']},'op':'>=','bound':{'literal':'9/10'}}   # what the version is the digest of: the recipe with every number in lowest terms
        self.assertEqual(c,{'predicate':'in_band','truth':'FALSE','verified':True,'source':SOURCE,'version':'cmp-'+digest(lowest)[:16],
                            'depends_on':[{'predicate':'run_fitness','version':n['version']}],'compares':recipe,'evidence_kind':'COMPARISON'})
        again=compared(reading('0.80'),'>=','9/10','in_band')   # the same numbers spelled another way are the same comparison: one version; the recipe keeps the spelling it was handed
        self.assertEqual((again['version'],again['compares']['number']['value'],again['compares']['bound']),(c['version'],'0.80',{'literal':'9/10'}))
        self.assertNotEqual(compared(n,'>=','0.91','in_band')['version'],c['version']);self.assertNotEqual(compared(n,'>','0.9','in_band')['version'],c['version'])   # another bound or operator is another comparison
        halves=[band(n,'>=','0.9','in_band',other)[0] for other in ('below_band','renamed')]   # the same comparison as a row of a band: the name of the other row is in the recipe and no part of the version
        self.assertEqual(([h['version'] for h in halves],[h['compares']['partner'] for h in halves],compared(n,'>=','0.9','any_name')['version']),([c['version']]*2,['below_band','renamed'],c['version']))
        d=compared(n,'<',BAND,'below')   # the bound is a number row kept as policy: the comparison rests on both rows
        self.assertEqual((d['truth'],d['depends_on'],d['compares']['bound']),
                         ('TRUE',[{'predicate':'run_fitness','version':n['version']},{'predicate':'fitness_band','version':BAND['version']}],{'predicate':'fitness_band','value':'0.9','version':BAND['version']}))
        self.assertNotEqual(compared(reading('0.85'),'>=','0.9','in_band')['version'],c['version'])   # another number, another version, though the verdict is the same
        truth=lambda a,op,b:compared(measured('x',a,source='s',label='l'),op,b,'c')['truth']
        self.assertEqual([truth('0.30','==','0.3'),truth('4/5','==','0.8'),truth('1/3','<','0.3334'),truth('1/3','>','0.3333'),truth('0.1','!=','1/10'),truth('2','<=','2.0'),truth('10','>','9.99'),truth('0.1','<','0.09')],
                         ['TRUE','TRUE','TRUE','TRUE','FALSE','TRUE','TRUE','FALSE'])   # exact ratios: no rounding, and equal numbers are equal however they are spelled
        self.assertEqual(sorted(NEGATED),sorted(['<','<=','>','>=','==','!=']))
        NUMBER='A number is exact text: digits with one optional point, or digits/digits';OWN='A comparison has a predicate of its own';NAME='The predicate of a number row is a name';BOUND='A bound row is another number of the same scope and unit'
        for op in ('=','=>','ge','in',None,['>='],'≥','> '):
            with self.assertRaises(ValueError,msg=repr(op)) as refusal:compared(n,op,'0.9','c')
            self.assertEqual(str(refusal.exception),'An operator is one of < <= > >= == !=',repr(op))
        percent=measured('fitness_band','90',source=POLICY,label='band-v1',unit='percent');elsewhere=measured('fitness_band','0.9',source=POLICY,label='band-v1',unit='ratio',scope='orgB/x')
        for bound,said in ((0.9,NUMBER),(9,NUMBER),(True,NUMBER),('0.9 ',NUMBER),('9e-1',NUMBER),('',NUMBER),(None,NUMBER),(percent,BOUND),(elsewhere,BOUND),(n,BOUND),(dict(BAND,value='0.95'),'Not a number row this adapter made'),([BAND],NUMBER)):
            with self.assertRaises(ValueError,msg=repr(bound)[:60]) as refusal:compared(n,'>=',bound,'c')
            self.assertEqual(str(refusal.exception),said,repr(bound)[:60])
        for name,said in (('run_fitness',OWN),('',NAME),(None,NAME),(7,NAME)):
            with self.assertRaises(ValueError,msg=repr(name)) as refusal:compared(n,'>=','0.9',name)
            self.assertEqual(str(refusal.exception),said,repr(name))
        there=compared(reading('0.8',scope='orgB/workflows'),'>=',measured('fitness_band','0.9',source=POLICY,label='band-v1',unit='ratio',scope='orgB/workflows'),'in_band')
        self.assertEqual((there['scope'],there['version'],'scope' in c),('orgB/workflows',compared(n,'>=',BAND,'in_band')['version'],False))   # a comparison is for the scope of its number, and the scope is no part of what was compared
        with self.assertRaises(ValueError) as refusal:compared(n,'>=',BAND,'fitness_band')
        self.assertEqual(str(refusal.exception),OWN)
        s=State();[s.observe(r) for r in (n,c)]   # the kernel reads the comparison like any row, and stops reading it when its number changes
        self.assertEqual(s.fact('in_band')['truth'],'FALSE');s.observe(reading('0.95','run-0002'))
        self.assertEqual((s.fact('in_band')['truth'],s.fact('in_band')['reason']),('UNKNOWN','dependency invalidated'))

    def test_c03_a_band_is_one_call_and_exactly_one_of_its_rows_is_true(self):
        for op in NEGATED:
            for value in ('0','0.89','0.9','0.90','9/10','0.91','1','17/3'):
                pair=band(reading(value),op,'0.9','inside','outside');a,b=pair[0]['compares'],pair[1]['compares']
                self.assertEqual(sorted(r['truth'] for r in pair),['FALSE','TRUE'],(op,value))   # exactly one of the two, also at the bound itself
                self.assertEqual((a['op'],b['op'],a['partner'],b['partner'],a['bound'],a['number']),(op,NEGATED[op],'outside','inside',b['bound'],b['number']))
        self.assertTrue(all(NEGATED[NEGATED[op]]==op and NEGATED[op]!=op for op in NEGATED))   # the six operators are closed under negation
        apart=[compared(reading('0.85'),'>=','0.9','in_band'),compared(reading('0.85'),'<','0.8','below_band')]
        self.assertEqual([r['truth'] for r in apart],['FALSE','FALSE'])   # the hole two rows authored apart can have, and a band cannot: neither in band nor below it
        alone=recorded()['alone'];told=lambda part:[(x['status'],x['stop_reasons'],x['model_receipts'],[(c['number']['value'],c['bound'],c['verdict']) for c in x['comparisons']]) for x in part['runs']]
        self.assertEqual((alone['packs'],pack('159_one_row_alone')['evidence'],told(alone['look']),alone['again']['remade'],told(alone['again'])),   # the record: one row authored alone (pack 159), below its bound, and no row says so
                         (ALONE,[reading('0.85','run-0004'),compared(reading('0.85','run-0004'),'>=','0.9','fitness_in_band')],[('QUERY_EVIDENCE',['METHOD_ABSENT','QUERY_EVIDENCE'],[],[('0.85',{'literal':'0.9'},'FALSE')])],
                          ['fitness_in_band'],[('QUERY_EVIDENCE',['METHOD_ABSENT','QUERY_EVIDENCE'],[],[('0.7',{'literal':'0.9'},'FALSE')])]))   # the goal asks for evidence and files nothing, also after a new reading made the one row again
        self.assertEqual([sorted(k.split('|')[1] for k in alone[part]['facts']) for part in ('after','after_again')],[['fitness_band','fitness_in_band','run_fitness']]*2)
        BAND_OF='A band is two predicates and one operator of < <= > >= == !='
        for names,said in ((('inside','inside'),BAND_OF),(('','outside'),'The inside of a number row is a name'),((None,'outside'),'The inside of a number row is a name'),(('inside',7),'The outside of a number row is a name')):
            with self.assertRaises(ValueError,msg=names) as refusal:band(reading('0.8'),'>=','0.9',*names)
            self.assertEqual(str(refusal.exception),said,names)
        with self.assertRaises(ValueError) as refusal:band(reading('0.8'),'~','0.9','inside','outside')
        self.assertEqual(str(refusal.exception),BAND_OF)
        self.assertEqual(pack('151_conformance_theory')['evidence'],[BAND])
        for name,value,label in (('152_run_fitness','0.8','run-0001'),('154_run_fitness_in_band','1.0','run-0002')):   # the recorded packs are what one call of the adapter writes
            n=reading(value,label);self.assertEqual(pack(name)['evidence'],[n]+band(n,'>=',BAND,'fitness_in_band','fitness_below_band'))

    def test_c04_a_number_under_its_band_files_a_finding_and_a_number_in_band_runs_nothing(self):
        s=self._first('0.8');r=Kernel(s).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'],r['actions'],r['cost'],len(r['model_receipts']),s.budget),
                         ('LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1'],{'compute':1,'money':0,'attention':1},1,{'compute':4,'money':5,'attention':1}))
        below=s.fact('fitness_below_band')
        self.assertIn({'predicate':'fitness_below_band','source':SOURCE,'version':below['version']},[e['data'] for e in r['trace'] if e['operation']=='RETAIN'])
        self.assertEqual(s.fact('finding_filed')['depends_on'],[{'predicate':'fitness_below_band','version':below['version']}])   # the finding rests on the comparison at its version
        self.assertTrue('Conformance finding' in r['model_receipts'][0]['artifact_text'] and '0.8' not in json.dumps(r['model_receipts']))   # the finding's text carries no number: a method is permanent on a State
        s=self._first('1.0');r=Kernel(s).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'],r['actions'],r['model_receipts'],r['cost'],s.budget),('SUPPORTED_BY_EVIDENCE',[],[],{'compute':0,'money':0,'attention':0},{'compute':5,'money':5,'attention':2}))
        for value in ('0.8','1.0'):   # all the lab could say before: the same goal, rule, number and method without the adapter's rows
            r=Kernel(self._first(value,rows=False)).run_standing(execute=True)['runs'][0];self.assertEqual((r['status'],r['model_receipts']),('QUERY_EVIDENCE',[]),value)
        for cid,status,actions in ((C63,'LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1']),(C64,'SUPPORTED_BY_EVIDENCE',[])):   # the recorded cases, and the same looks in the recorded sequence
            out=scenario(BY[cid])['outcome'];again=recorded()['looks'][cid]['look']['runs'][0]
            self.assertEqual((out['status'],out['actions'],again['trace_root_sha256'],len(again['comparisons'])),(status,actions,out['trace_root_sha256'],2),cid)
        filed=scenario(BY[C63]);row=filed['derived_state']['facts'][W+'finding_filed']   # the finding on the books of the case is the step's row, resting on the comparison at its version
        self.assertEqual((row['truth'],row['verified'],row['source'],row['depends_on'],'final' in row),('TRUE',True,'LOCAL_ARTIFACT:file-finding@1',[{'predicate':'fitness_below_band','version':filed['derived_state']['facts'][W+'fitness_below_band']['version']}],False))
        self.assertTrue(json.loads(filed['outcome']['model_receipts'][0]['artifact_text'])['title'].endswith('the numbers are on the comparison row this finding rests on (fitness_below_band)'))   # the text points at a row that is on the books of every record
        bare=recorded()['bare'];one=lambda part:[(x['status'],x['stop_reasons'],x['model_receipts'],'comparisons' in x) for x in part['runs']];asks=[('QUERY_EVIDENCE',['QUERY_EVIDENCE'],[],False)]
        self.assertEqual((bare['packs'],pack('152_number_alone')['evidence'],one(bare['look']),one(bare['again']),{k:v for k,v in bare['event'].items() if k!='event'}),   # the record: the number with no comparison row beside it, at 0.8 and at 1.0
                         (BARE,[reading('0.8','run-0001')],asks,asks,{'status':'RECONCILED','affected':[],'runs':[],'remade':[]}))
        self.assertEqual([(sorted(k.split('|')[1] for k in bare[part]['facts']),bare[part]['facts'][W+'run_fitness']['value'],bare[part]['budget']) for part in ('after','after_again')],
                         [(['fitness_band','run_fitness'],value,{'compute':5,'money':5,'attention':2}) for value in ('0.8','1.0')])   # the number is on the books, no comparison is, and nothing was paid

    def test_c05_a_comparison_never_outlives_its_number(self):
        s=self._first('0.8');k=Kernel(s);k.run_standing(execute=True)
        out=k.on_event(reading('0.95','run-0002'),execute=True)   # the new reading handed to the kernel alone, without renumber
        self.assertEqual((out['status'],out['affected'],[x['status'] for x in out['runs']]),('RECONCILED',['run_judged'],['QUERY_EVIDENCE']))
        self.assertEqual([(s.fact(p)['truth'],s.fact(p).get('reason')) for p in ('fitness_in_band','fitness_below_band','finding_filed')],[('UNKNOWN','dependency invalidated')]*3)
        s=self._first('0.8');k=Kernel(s);k.run_standing(execute=True);s.apply({'schema':P2,'id':'next-reading','evidence':[reading('0.95','run-0002')]})   # the new reading arrives in a pack
        self.assertEqual((self._truths(s,'fitness_in_band','fitness_below_band','finding_filed'),k.run_standing(execute=True)['runs'][0]['status']),(['UNKNOWN']*3,'QUERY_EVIDENCE'))
        s=self._first('1.0');k=Kernel(s);self.assertEqual(k.run_standing(execute=True)['runs'][0]['status'],'SUPPORTED_BY_EVIDENCE')
        worse=reading('0.5','run-0001');self.assertNotEqual(worse['version'],reading('1.0','run-0001')['version'])   # the caller reuses the label; the version is new all the same
        r=k.on_event(worse,execute=True)['runs'][0];self.assertEqual((r['status'],s.fact('fitness_in_band')['truth']),('QUERY_EVIDENCE','UNKNOWN'))   # never the old TRUE
        s=self._first('1.0');k=Kernel(s)   # the same number under the same label is the same reading: nothing made on it is undone
        self.assertEqual((k.on_event(reading('1.00','run-0001'),execute=True)['runs'][0]['status'],s.fact('fitness_in_band')['truth']),('SUPPORTED_BY_EVIDENCE','TRUE'))
        bare=recorded()['events']['bare_event']   # the record: the look after a reading handed to the kernel alone asks for evidence and reads neither row of the band
        self.assertEqual(([x['status'] for x in bare['runs']],[x['reads'] for x in bare['runs'][0]['comparisons']],'remade' in bare),(['QUERY_EVIDENCE'],['UNKNOWN','UNKNOWN'],False))
        ne=recorded()['events'];late=ne['pack_event']['runs'][0]   # the record: a reading arrives in a pack, with no comparison beside it, on a State whose comparisons were made on 0.95
        self.assertEqual((late['status'],[(x['number']['value'],x['verdict'],x['reads']) for x in late['comparisons']],[p['pack'] for p in late['provenance']][-1],ne['after_pack_event']['facts'][W+'run_fitness']['value']),
                         ('QUERY_EVIDENCE',[('0.95','TRUE','UNKNOWN'),('0.95','FALSE','UNKNOWN')],'152_number_alone','0.8'))   # the look asks for evidence instead of standing on the verdict of 0.95
        # What comes back later (a limit). A row a step made reads again when its prerequisites read TRUE at the versions it cites, and a handler's row carries one constant version.
        # So a row made TWO steps below a comparison comes back when the first step runs again on another number, unless its own step names the comparison too. The lint refuses a step that does not.
        def told(*requires):   # the conformance packs and one step more: the owner is told of the finding
            return [pack(n) for n in CONFORM]+[{'schema':P2,'id':'tell','goals':['run_judged','owner_told'],'providers':{'local-provider':10},
                                               'methods':[step('tell-owner@1','owner_told',{'compute':1},req=requires,grant='action:file-finding@1',provider='local-provider')]}]
        def walk(packs):   # the first look, a reading in band, a reading below the band again: what each look did, and what the owner's row reads after it
            s=State.from_packs(packs);k=Kernel(s);seen=[([(x['goal'],x['status'],x['actions']) for x in k.run_standing(execute=True)['runs']],self._truths(s,'finding_filed','owner_told'))]
            for value,label in (('0.95','run-0002'),('0.7','run-0003')):
                seen.append(([(x['goal'],x['status'],x['actions']) for x in renumber(k,reading(value,label),execute=True)['runs']],self._truths(s,'finding_filed','owner_told')))
            return seen
        first=([('run_judged','LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1']),('owner_told','LOCAL_MODEL_EFFECTS_RECORDED',['tell-owner@1'])],['TRUE','TRUE'])
        gone=([('run_judged','SUPPORTED_BY_EVIDENCE',[]),('owner_told','METHOD_ABSENT',[])],['UNKNOWN','UNKNOWN'])   # when the reading arrives everything made on the old comparison reads UNKNOWN, also two steps below it
        loose=told('finding_filed');named=told('finding_filed','fitness_below_band')
        self.assertEqual(walk(loose),[first,gone,([('run_judged','LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1']),('owner_told','SUPPORTED_BY_EVIDENCE',[])],['TRUE','TRUE'])])   # the limit: the second finding is filed, and the owner's row of the first finding reads again: nobody is told
        self.assertEqual(walk(named),[first,gone,([('run_judged','LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1']),('owner_told','LOCAL_MODEL_EFFECTS_RECORDED',['tell-owner@1'])],['TRUE','TRUE'])])   # the step names the comparison itself: the owner is told of the second finding too
        self.assertEqual((problems(loose),problems(named)),(['tell-owner@1: requires finding_filed, which file-finding@1 makes on fitness_below_band, without requiring fitness_below_band itself; '
                                                              'what it makes would come back when finding_filed is made again on another number'],[]))   # the lint refuses the first and takes the second

    def test_c06_renumber_takes_a_new_number_whole_or_not_at_all(self):
        s=self._first('0.8');k=Kernel(s);k.run_standing(execute=True);before=self._books(s);both=('fitness_in_band','fitness_below_band')
        refused={'for another scope':reading('0.95','run-2',scope='orgB/workflows'),'unverified':dict(reading('0.95','run-2'),verified=False),
                 'not made by the adapter':{'predicate':'run_fitness','truth':'TRUE','verified':True,'source':LOG,'version':'m2','value':'0.95'},
                 'a float':dict(reading('0.95','run-2'),value=0.95),'in another unit':measured('run_fitness','95',source=LOG,label='run-2',unit='percent'),
                 'in the place of a comparison':measured('fitness_in_band','0.95',source=LOG,label='run-2',unit='ratio'),
                 'in the place of a row that is no number':measured('finding_filed','1',source=LOG,label='run-2',unit='ratio'),'not a row':'0.95','a list':[reading('0.95','run-2')]}
        for why,row in refused.items():
            with self.assertRaises(ValueError,msg=why):renumber(k,row,execute=True)
            self.assertEqual(self._books(s),before,why)   # no stored row, no journal row, nothing paid: the goal stands where it stood
        with self.assertRaises(ValueError) as refusal:renumber(None,reading('0.95','run-2'))   # what is handed in as the kernel is no kernel
        self.assertTrue(str(refusal.exception).startswith('Not a number this State can take: AttributeError('))
        for flag in (1,0,None,'yes'):   # execute is exactly true or false: the kernel's own door refuses it on the copy, so nothing is taken
            with self.assertRaises(ValueError,msg=repr(flag)) as refusal:renumber(k,reading('0.95','run-2'),execute=flag)
            self.assertEqual((str(refusal.exception),self._books(s),k.s is s),('execute is true or false',before,True),repr(flag))
        moved=measured('fitness_band','0.6',source=POLICY,label='band-v2',unit='ratio')
        decision,whole,door='A decision stands on this number','A band is made again whole or not at all','The kernel would turn this number or a comparison away'
        for decided,row,why in (('run_fitness',reading('0.95','run-2'),decision),('fitness_in_band',reading('0.95','run-2'),whole),('fitness_below_band',moved,whole),('fitness_band',moved,decision),
                                ('fitness_band',reading('0.95','run-2'),'Not a number row this adapter made')):   # the last: a decision on the bound of the comparisons the new reading feeds
            w=self._first('0.8');kw=Kernel(w);kw.run_standing(execute=True)
            self.assertTrue(w.observe({'predicate':decided,'truth':'TRUE','verified':True,'final':True,'source':'owner','version':'d1'}));held=self._books(w)
            with self.assertRaises(ValueError,msg=decided) as refusal:renumber(kw,row,execute=True)
            self.assertEqual((str(refusal.exception),self._books(w)),(why,held),decided)   # a decision on the number, on a row of its band or on its bound: refused whole, without a DECISION_STANDS row
        there=dict(scope='sutra/workflows');next_row=band(reading('0.95','run-2',**there),'>=',measured('fitness_band','0.9',source=POLICY,label='band-v1',unit='ratio',**there),*both)[1]
        for version in (None,next_row['version']):   # a decision under the adapter's own name on a row of the band, keeping all the row says; the second one already carries the version the next comparison will have
            w=self._first('0.8');kw=Kernel(w);stamped={k:v for k,v in dict(w.fact('fitness_below_band'),final=True).items() if k not in ('depends_on','scope')}
            self.assertTrue(w.observe(dict(stamped,version=version or stamped['version'])));held=self._books(w)
            with self.assertRaises(ValueError,msg=version) as refusal:renumber(kw,reading('0.95','run-2'),execute=True)
            self.assertEqual((str(refusal.exception),self._books(w)),(door,held),version)   # the kernel's own door, tried on the copy, turns the comparison away: nothing is taken
        pair=band(reading('0.8'),'>=',BAND,'fitness_in_band','fitness_below_band');same_way=copy.deepcopy(pair[1]);same_way['compares']['op']='>=';other_bound=copy.deepcopy(pair[1]);other_bound['compares']['bound']={'literal':'0.9'}
        for broken in ([{'predicate':'fitness_band','truth':'TRUE','verified':True,'source':'someone','version':'x'}],   # the bound is no number any more
                       [{'predicate':'junk','truth':'TRUE','verified':True,'source':SOURCE,'version':'x','compares':{'number':'run_fitness'}}],   # a row under the adapter's name that it did not make
                       [{'predicate':'fitness_below_band','truth':'TRUE','verified':True,'source':'someone','version':'x'}],   # half the band is gone
                       [same_way],[other_bound],   # the other row no longer says the opposite of the same comparison: its operator is not the negated one, or its bound is another
                       band(reading('0.8'),'<',BAND,'fitness_below_band','third_row')):   # the other row is now half of another band: it names a third row, not this one
            w=self._first('0.8');kw=Kernel(w);self.assertTrue(all(w.observe(x) for x in broken));held=self._books(w);why=broken[0]['predicate']+' '+str(len(broken))
            with self.assertRaises(ValueError,msg=why):renumber(kw,reading('0.95','run-2'),execute=True)
            self.assertEqual(self._books(w),held,why)
        floor=measured('fitness_floor','0.5',source=POLICY,label='floor-v1',unit='ratio');low=reading('0.8')
        for why,broken in (('the two rows of the band stand against two bound rows',[floor,band(low,'>=',floor,'fitness_in_band','fitness_below_band')[1]]),   # each row names the other and they are opposite: only the bound tells them apart
                           ('the two rows of the band carry two bounds written into them',band(low,'>=','0.9','fitness_in_band','fitness_below_band')[:1]+band(low,'>=','0.8','fitness_in_band','fitness_below_band')[1:])):
            w=self._first('0.8');kw=Kernel(w);self.assertTrue(all(w.observe(x) for x in broken));held=self._books(w)
            with self.assertRaises(ValueError,msg=why) as refusal:renumber(kw,reading('0.95','run-2'),execute=True)
            self.assertEqual((str(refusal.exception),self._books(w)),(whole,held),why)   # no band is made again row by row
        w=self._first('0.8');far=dict(scope='orgB/workflows');rows=[measured('fitness_band','0.9',source=POLICY,label='band-v1',unit='ratio',**far),reading('0.8',**far)];rows+=band(rows[1],'>=',rows[0],*both)
        self.assertTrue(all(w.observe(x) for x in rows));theirs={key:row for key,row in w.evidence.items() if key.startswith('orgB/')};mine=sorted(key for key in w.evidence if key not in theirs)
        out=renumber(Kernel(w),reading('0.95','run-0002'),execute=True)   # the same band stands in another scope of the same State: a reading for this scope makes this scope's two rows again and touches nothing there
        self.assertEqual((out['remade'],sorted(key for key in w.evidence if not key.startswith('orgB/')),{key:row for key,row in w.evidence.items() if key.startswith('orgB/')},len(theirs)),(list(both),mine,theirs,4))
        n=len(s.event_journal);shelf=s.evidence;out=renumber(k,reading('0.95','run-0002'),execute=True)   # a reading in band: both rows made again, one look, one journal row
        self.assertEqual((out['status'],out['affected'],out['remade'],[(x['status'],x['actions']) for x in out['runs']],len(s.event_journal)-n),
                         ('RECONCILED',['run_judged'],['fitness_in_band','fitness_below_band'],[('SUPPORTED_BY_EVIDENCE',[])],1))
        self.assertTrue(k.s is s and s.evidence is not shelf and shelf[s.key('run_fitness')]['value']=='0.8')   # taken on a copy, as `apply` does: the State is the same object, its fields are new ones
        self.assertEqual([s.fact(p) for p in both],band(reading('0.95','run-0002',**there),'>=',measured('fitness_band','0.9',source=POLICY,label='band-v1',unit='ratio',**there),*both))   # on the books is what one call of `band` makes from the numbers on the books: each row still names the other
        self.assertEqual((self._truths(s,'fitness_in_band','fitness_below_band','finding_filed'),s.budget),(['TRUE','FALSE','UNKNOWN'],{'compute':4,'money':5,'attention':1}))   # the earlier finding no longer shows
        out=renumber(k,reading('0.7','run-0003'),execute=True)   # still below the band: the finding is filed again and paid again
        self.assertEqual(([(x['status'],x['actions']) for x in out['runs']],self._truths(s,'finding_filed'),s.budget,len(s.event_journal)-n),
                         ([('LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1'])],['TRUE'],{'compute':3,'money':5,'attention':0},2))
        held=digest(s.evidence);out=renumber(k,reading('0.7','run-0003'),execute=True)   # the same reading again: nothing runs, nothing is paid, no row changes
        self.assertEqual(([(x['status'],x['actions']) for x in out['runs']],digest(s.evidence),s.budget['attention'],len(s.event_journal)-n),([('SUPPORTED_BY_EVIDENCE',[])],held,0,3))
        versions=[s.fact(p)['version'] for p in both]
        out=renumber(k,reading('0.70','run-0003'),execute=True)   # the same number spelled another way: one number, one version, one comparison, so the finding made on it stands and nothing is paid
        self.assertEqual(([(x['status'],x['actions']) for x in out['runs']],[s.fact(p)['version'] for p in both],self._truths(s,'finding_filed'),s.fact('run_fitness')['value'],
                          s.fact('fitness_below_band')['compares']['number']['value'],s.budget['attention']),([('SUPPORTED_BY_EVIDENCE',[])],versions,['TRUE'],'0.70','0.70',0))
        out=renumber(k,moved,execute=True)   # the band itself moves: the comparisons that use it as their bound are made again
        self.assertEqual((out['remade'],[x['status'] for x in out['runs']],self._truths(s,'fitness_in_band','fitness_below_band'),s.fact('fitness_in_band')['compares']['bound']['value']),
                         (['fitness_in_band','fitness_below_band'],['SUPPORTED_BY_EVIDENCE'],['TRUE','FALSE'],'0.6'))
        w=self._first('0.8');w.apply({'schema':P2,'id':'more-goals','goals':['run_judged','also_judged','unrelated'],'rules':[{'id':'R-ALSO@1','head':'also_judged','branches':[['fitness_in_band']],'approved':True},
                                                                                                                  {'id':'R-UN@1','head':'unrelated','branches':[['something_else']],'approved':True}]})
        kw=Kernel(w);kw.run_standing(execute=True);seen=len(w.event_journal);out=renumber(kw,reading('0.95','run-0002'),execute=True)   # three standing goals, two of them rest on the number: one look and one journal row for each of the two, none for the third
        self.assertEqual((out['affected'],[x['goal'] for x in out['runs']],[x['status'] for x in out['runs']],len(w.event_journal)-seen),(['run_judged','also_judged'],['run_judged','also_judged'],['SUPPORTED_BY_EVIDENCE']*2,2))
        w=State();kw=Kernel(w);out=renumber(kw,measured('queue_length','7',source='s',label='l'),execute=True)   # a first reading that nothing compares yet
        self.assertEqual((out['status'],out['affected'],out['remade'],out['runs'],w.fact('queue_length')['value']),('RECONCILED',[],[],[],'7'));held=self._books(w)
        with self.assertRaises(ValueError):renumber(kw,measured('queue_length','7',source='s',label='l',unit='items'),execute=True)   # a new reading keeps the unit, also when nothing compares the number
        self.assertEqual(self._books(w),held)
        w=self._first('0.8');kw=Kernel(w);kw.run_standing(execute=True);kw.on_event(reading('0.95','run-0002'),execute=True)   # handed to the kernel alone first: renumber with the same reading makes the comparisons again
        out=renumber(kw,reading('0.95','run-0002'),execute=True);self.assertEqual(([x['status'] for x in out['runs']],self._truths(w,'fitness_in_band')),(['SUPPORTED_BY_EVIDENCE'],['TRUE']))
        down=[]   # a look that raises (a plan hook that fails while planning: a known limit of the kernel) leaves the State as it was too: the reading is not half taken
        def plan(state,m):
            if down:raise RuntimeError('planner down')
        register('test_plan_fails',plan=plan)(lambda state,m,mid,deps:{})
        try:
            w=self._first('1.0');w.apply({'schema':P2,'id':'other-way','methods':[step('other-way@1','finding_filed',{'compute':1},'test_plan_fails',['fitness_below_band'])],'providers':{'p':1},'grants':['g']})
            kw=Kernel(w);self.assertEqual(kw.run_standing(execute=True)['runs'][0]['status'],'SUPPORTED_BY_EVIDENCE');held=self._books(w);down.append(1)
            with self.assertRaises(RuntimeError):renumber(kw,reading('0.7','run-0002'),execute=True)
            self.assertEqual((self._books(w),kw.s is w,w.fact('run_fitness')['value']),(held,True,'1.0'))
            down.clear();out=renumber(kw,reading('0.7','run-0002'),execute=True)   # the planner is back: the same reading is taken whole
            self.assertEqual(([x['status'] for x in out['runs']],kw.s is w,w.fact('run_fitness')['value'],self._truths(w,*both)),(['LOCAL_MODEL_EFFECTS_RECORDED'],True,'0.7',['FALSE','TRUE']))
        finally:del ACTIONS['test_plan_fails']
        ne=recorded()['events'];look=lambda key:[(x['status'],x['actions']) for x in ne[key]['runs']];filed=[('LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1'])];held=[('SUPPORTED_BY_EVIDENCE',[])]
        self.assertEqual([look(key) for key in ('first','in_band','below_again','same_again','band_moved','first_bare','bare_event','repaired','pack_event')],[filed,held,filed,held,held,filed,[('QUERY_EVIDENCE',[])],held,[('QUERY_EVIDENCE',[])]])
        number_only='A number takes the place of a number only'
        self.assertEqual((ne['refused'],ne['after_refused'],[ne['after_'+key]['journal'] for key in ('first','in_band','below_again','same_again','band_moved')]),
                         ({'another scope':'A number for another scope is not taken here','not a row the adapter made':'Not a number row this adapter made','another unit':'A new reading keeps the unit of the number it replaces',
                           'in the place of a comparison':number_only,'in the place of a row that is no number':number_only,'execute is not true or false':'execute is true or false'},
                          ne['after_bare_event'],[1,2,3,4,5]))   # the record: one journal row per look, and six readings the State could not take, each refused in the adapter's words, leave no mark
        rows=lambda key:ne['after_'+key]['facts'];finding=lambda key:rows(key)[W+'finding_filed']   # the record: the finding is the row of the look that filed it, and the next reading leaves it on the books as it was
        self.assertEqual(([finding(key)==finding('first') for key in ('in_band','below_again')],[finding(key)==finding('below_again') for key in ('same_again','band_moved')],[finding(key)==finding('first_bare') for key in ('bare_event','refused','repaired','pack_event')],
                          [finding(key)['depends_on'][0]['version']==rows(key)[W+'fitness_below_band']['version'] for key in ('first','in_band','below_again','same_again','band_moved','repaired')]),
                         ([True,False],[True,True],[True]*4,[True,False,True,True,False,False]))

    def test_c07_every_comparison_a_trace_names_is_stated_in_a_block_on_its_run(self):
        s=self._first('0.8');r=attach(Kernel(s).run_standing(execute=True),s)['runs'][0];n=reading('0.8')
        number={'predicate':'run_fitness','value':'0.8','version':n['version']};bound={'predicate':'fitness_band','value':'0.9','version':BAND['version']}
        self.assertEqual(r['comparisons'],[
            {'predicate':'fitness_in_band','number':number,'operator':'>=','bound':bound,'verdict':'FALSE','source':SOURCE,'version':s.fact('fitness_in_band')['version'],'reads':'FALSE'},
            {'predicate':'fitness_below_band','number':number,'operator':'<','bound':bound,'verdict':'TRUE','source':SOURCE,'version':s.fact('fitness_below_band')['version'],'reads':'TRUE'}])
        self.assertEqual(r['comparisons_record'],{'source_trace':r['trace_root_sha256'],'comparisons_sha256':digest(r['comparisons'])})   # bound to the kernel's hash-chained trace
        held={e['data']['predicate']:e['data']['version'] for e in r['trace'] if e['operation']=='RETAIN'}
        self.assertEqual({x['predicate']:x['version'] for x in r['comparisons'] if x['reads']=='TRUE'},held)   # for a comparison that held, the version is the one in the trace's RETAIN row
        text=json.dumps(r['trace']);self.assertTrue('0.8' not in text and '0.9' not in text)   # the number is not in the kernel's trace: the block is where a reader finds it
        r['comparisons'][0]['number']['value']='9';self.assertEqual(s.fact('fitness_in_band')['compares']['number']['value'],'0.8')   # the block is a copy
        stale=attach(Kernel(s).on_event(reading('0.95','run-0002'),execute=True),s)['runs'][0]   # a look after the number moved on: the block says the rows no longer read
        self.assertEqual([(x['predicate'],x['verdict'],x['reads'],x['number']['value']) for x in stale['comparisons']],[('fitness_in_band','FALSE','UNKNOWN','0.8'),('fitness_below_band','TRUE','UNKNOWN','0.8')])
        w=self._first('1.0');r=attach(Kernel(w).run_standing(execute=True),w)['runs'][0]
        self.assertEqual([(x['predicate'],x['verdict'],x['reads']) for x in r['comparisons']],[('fitness_in_band','TRUE','TRUE'),('fitness_below_band','FALSE','FALSE')])
        w.observe(compared(reading('1.0'),'>=','0.9','None'));again=attach(Kernel(w).run_standing(execute=True),w)['runs'][0]   # a row of the trace that names no fact names no comparison, also when a comparison is stored under the name 'None'
        self.assertEqual([x['predicate'] for x in again['comparisons']],['fitness_in_band','fitness_below_band'])
        old=State.from_packs([pack(n) for n in BY['04_gates'][3]]);plain_run=attach(Kernel(old).run_standing(execute=True),old)['runs'][0]
        self.assertTrue('comparisons' not in plain_run and 'comparisons_record' not in plain_run)   # a run that names no comparison carries no block
        w.apply({'schema':P2,'id':'moved','scope':'orgB/elsewhere'})
        with self.assertRaises(ValueError) as refusal:comparisons(r,w)   # the block is made on the State the run was made on, in its scope
        self.assertEqual(str(refusal.exception),'The State has moved to another scope since this run')
        for later in (lambda k:k.on_event(reading('0.95','run-0002'),execute=True),lambda k:renumber(k,reading('0.95','run-0002'),execute=True),lambda k:renumber(k,reading('0.7','run-0003'),execute=True)):
            w=self._first('0.8');kw=Kernel(w);run=kw.run_standing(execute=True);later(kw)
            with self.assertRaises(ValueError) as refusal:attach(run,w)   # and right after the run or not at all: once the books have moved on, the run's own trace says so (it held a row that no longer reads TRUE at that version)
            self.assertEqual(str(refusal.exception),'The books have moved on since this run')
            self.assertTrue('comparisons' not in run['runs'][0])
        w=State.from_packs([pack(n) for n in ALONE]);kw=Kernel(w);run=kw.run_standing(execute=True);renumber(kw,reading('0.7','run-0005'),execute=True)   # a limit: this run held no comparison (its one row read FALSE), so its trace cannot tell that the books moved on
        self.assertEqual([(x['number']['value'],x['verdict'],x['reads']) for x in attach(run,w)['runs'][0]['comparisons']],[('0.7','FALSE','FALSE')])   # a block made late states the newer number, not the 0.85 the run read
        def chain(depth):   # a goal that stands over one comparison through a chain of rules
            n=reading('1.0');rules=[{'id':f'R-{i}@1','head':f'level_{i}','branches':[[f'level_{i+1}' if i+1<depth else 'in_band']],'approved':True} for i in range(depth)]
            return State.from_packs([{'schema':P2,'id':'chain','scope':'sutra/workflows','goals':['level_0'],'rules':rules,'evidence':[n,compared(n,'>=','0.9','in_band')]}])
        w=chain(19);r=attach(Kernel(w).run_standing(execute=True),w)['runs'][0];self.assertEqual((r['status'],[x['reads'] for x in r['comparisons']]),('SUPPORTED_BY_EVIDENCE',['TRUE']))
        w=chain(20);r=attach(Kernel(w).run_standing(execute=True),w)['runs'][0]   # one level deeper than the kernel looks: it names the comparison in a CYCLE_LIMIT row and never reads it, so the run neither rested nor stopped on it and carries no block
        self.assertEqual((r['status'],'comparisons' in r,[e['data'] for e in r['trace'] if e['operation']=='CYCLE_LIMIT']),('CYCLE_LIMIT',False,[{'predicate':'in_band'}]))
        strip=lambda x,keys:{k:v for k,v in x.items() if k not in keys}
        for cid in OURS:   # the record: a case is recorded by code that is not this version's, so its run carries no block; the sequence takes the same look again, field for field, and carries it
            case=scenario(BY[cid]);mine=recorded()['looks'][cid]
            self.assertFalse([key for x in case['run']['runs'] for key in BLOCKS if key in x],cid)
            self.assertEqual(([strip(x,BLOCKS) for x in mine['look']['runs']],mine['packs'],mine['after']['facts'],mine['after']['budget'],mine['after']['journal']),
                             ([strip(x,('learning','learning_record')) for x in case['run']['runs']],case['packs'],case['derived_state']['facts'],case['derived_state']['budget_after'],len(case['derived_state']['historical_events'])),cid)
        seq=recorded();seen=[x for part in looks_of(seq) for x in part['runs']]
        self.assertEqual((len(seen),sum('comparisons' in x for x in seen)),(20,13))   # thirteen of the twenty runs of the sequence name a comparison; the loan review, the four queue reviews and the two looks on the number alone name none
        for x in seen:
            if 'comparisons' in x:self.assertEqual(x['comparisons_record'],{'source_trace':x['trace_root_sha256'],'comparisons_sha256':digest(x['comparisons'])})

    def test_c08_fractions_of_cost_travel_as_whole_units(self):
        self.assertEqual((amount('0.42',100),amount('2.00',100),amount('3',1),amount('1/4',100),amount('0',100),type(amount('0.42',100))),(42,200,3,25,0,int))
        NUMBER='A number is exact text: digits with one optional point, or digits/digits';PARTS='A unit is a whole number of parts, one or more';HOLD='The unit cannot hold this amount exactly'
        for value,per,said in (('0.425',100,HOLD),('1/3',100,HOLD),('-0.42',100,NUMBER),(0.42,100,NUMBER),(42,100,NUMBER),('0.42',0,PARTS),('0.42',-100,PARTS),('0.42',100.0,PARTS),('0.42',True,PARTS),('0.42','100',PARTS),('',100,NUMBER)):
            with self.assertRaises(ValueError,msg=(value,per)) as refusal:amount(value,per)
            self.assertEqual(str(refusal.exception),said,(value,per))
        self.assertEqual((LIMIT,amount('9'*18,1),amount('9999999999999999.99',100)),(10**18,10**18-1,10**18-1))   # the largest amount the kernel takes
        for value,per in (('1'+'0'*18,1),('1'+'0'*16,100),('9'*18,2)):   # an amount the kernel would refuse is refused here, in words of its own
            with self.assertRaises(ValueError,msg=(value,per)) as refusal:amount(value,per)
            self.assertEqual(str(refusal.exception),'The kernel takes an amount below 10**18')
        base={'schema':P2,'id':'b','budget':{'usd_cents':200}}
        for cost in (0.42,'0.42',1.0,True,Fraction(21,50),Decimal('0.42'),-1,10**18):   # the kernel still takes whole numbers only, below 10**18: no fraction reaches a cost or a budget
            with self.assertRaises(ValueError,msg=repr(cost)):State().apply(dict(base,methods=[step('m','e',{'usd_cents':cost})]))
        for money in (2.5,'2.00',Fraction(2),True,10**18):
            with self.assertRaises(ValueError,msg=repr(money)):State().apply({'schema':P2,'id':'b','budget':{'usd_cents':money}})
        with self.assertRaises(ValueError):State().apply(dict(base,methods=[step('m','e',{'usd':42})]))   # a cost in a unit the budget does not have: the unit is in the dimension's name
        self.assertEqual((pack('155_loan_goal')['budget'],pack('156_loan_review')['methods'][0]['cost']),({'usd_cents':amount('2.00',100),'tokens':10000},{'usd_cents':amount('0.42',100),'tokens':3340}))
        c=scenario(BY[C65]);r=c['outcome'];cost={'compute':0,'money':0,'attention':0,'usd_cents':42,'tokens':3340}
        self.assertEqual((r['status'],r['cost'],[e['data']['cost'] for e in r['trace'] if e['operation']=='ADMISSION'],[e['data']['full_cost'] for e in r['trace'] if e['operation']=='SELECT'],
                          cost_receipts(r)['steps'][0]['cost'],c['derived_state']['budget_after']),
                         ('LOCAL_MODEL_EFFECTS_RECORDED',cost,[cost,cost],[cost],cost,{'compute':10,'money':10,'attention':3,'usd_cents':158,'tokens':6660}))   # the plan, both admissions, the step's receipt and what is left agree

    def test_c09_every_step_cost_is_read_from_the_gate(self):
        steps=0;seq=recorded();parts=looks_of(seq)
        event_runs=[x for block in (extra_events(),ask_events()) for v in block.values() if isinstance(v,dict) and 'runs' in v for x in v['runs']]+[x for part in parts for x in part['runs']]
        for case in CASES:
            methods={m['id']:m for n in case[3] for m in pack(n).get('methods',[])}
            for r in scenario(case)['run']['runs']:
                got=cost_receipts(r);effects=[(i,e['data']['receipt']) for i,e in enumerate(r['trace']) if e['operation']=='LOCAL_EFFECT'];steps+=len(effects)
                self.assertEqual(got['steps'],[{'method':x['method'],'receipt':x['sha256'],'cost':r['trace'][i-1]['data']['cost']} for i,x in effects],case[0])   # the row directly before the effect
                self.assertTrue(all(r['trace'][i-1]['operation']=='ADMISSION' and r['trace'][i-1]['data']['methods']==[x['method']] for i,x in effects),case[0])
                self.assertTrue(all(x['cost']=={dim:methods[x['method']].get('cost',{}).get(dim,0) for dim in x['cost']} for x in got['steps']),case[0])   # which is the pack's cost of that method
                self.assertEqual(([x['receipt'] for x in got['steps']],got['source_trace'],got['steps_sha256']),([x['sha256'] for x in r['model_receipts']],r['trace_root_sha256'],digest(got['steps'])))
                if got['steps']:self.assertEqual(got['total'],r['cost'],case[0])   # the steps add up to the cost of the run
        self.assertGreaterEqual(steps,25)
        for r in event_runs:cost_receipts(r)   # the pairing also holds through a parked ask, a skipped step and a stopped step
        for part in parts:self.assertEqual(part['cost_receipts'],[cost_receipts(x) for x in part['runs']])   # the record: every look of the sequence carries one cost receipt per run
        self.assertEqual([len(x['steps']) for part in parts for x in part['cost_receipts']],[1,0,1,1,0]+[0,0]+[0,0]+[0,0]+[1,0,1,0,0,1,0,0,0])   # the four cases' looks, the next run of the queue, the two looks on the number alone, the two on the row authored alone, the nine looks of the events
        r=scenario(BY['04_gates'])['outcome'];at=[e['operation'] for e in r['trace']].index('LOCAL_EFFECT')
        self.assertEqual(sorted(r['model_receipts'][0]),['action','method','model_effect','scope','sha256','status'])   # the kernel's own receipt carries no cost
        def sealed(run,first=1,number=int):   # the hash chain made again after a change, so that only the pairing is wrong
            prev='GENESIS'
            for i,e in enumerate(run['trace']):
                e.update(seq=number(i+first),prev_sha256=prev);e['sha256']=digest({k:v for k,v in e.items() if k!='sha256'});prev=e['sha256']
            run['trace_root_sha256']=prev;return run
        bent=[copy.deepcopy(r) for _ in range(11)]
        del bent[0]['trace'][at-1];bent[1]['trace'][at-1]['data']['methods']=['ship-original@1'];bent[2]['trace'][at-1]['data']['accepted']=False
        bent[3]['cost']={'compute':0,'money':0,'attention':0};bent[4]['cost']={dim:float(v) for dim,v in r['cost'].items()};bent[5]['model_receipts']=[]
        bent[6]['trace'][at-1]['data']['cost']['money']=0;bent[7]['trace_root_sha256']='0'*64;bent[8]['trace'][at-1]['data']['cost']['money']=0
        bent[9]['trace'][at-1]['operation']='NOTE'   # the row before the effect says all an admission row says and is none
        for e in bent[10]['trace']:e['prev_sha256']='GENESIS';e['sha256']=digest({k:v for k,v in e.items() if k!='sha256'})   # every row hashes by itself and none is linked to the row before
        bent[10]['trace_root_sha256']=bent[10]['trace'][-1]['sha256']
        said=[]
        for x in [sealed(x) for x in bent[:3]]+bent[3:8]+[sealed(bent[8]),sealed(bent[9]),bent[10],sealed(copy.deepcopy(r),2),sealed(copy.deepcopy(r),1,float)]:   # the last two: a chain that hashes, numbered from 2, and one numbered 1.0, 2.0, ...
            with self.assertRaises(ValueError) as refusal:cost_receipts(x)
            said.append(str(refusal.exception))
        pairing,total,receipts,chain=('No accepted admission row sits directly before this step','The step costs do not add up to the cost of the run',
                                      'The receipts of the run are not the receipts of its trace','The trace does not hash to its root')
        self.assertEqual(said,[pairing]*3+[total,total,receipts,chain,chain,total,pairing,chain,chain,chain])   # it raises when the pairing does not hold, when the steps do not add up (1 is not 1.0), and when the trace does not hash to its root
        self.assertEqual(cost_receipts(sealed(copy.deepcopy(r))),cost_receipts(r))
        thin=copy.deepcopy(r)   # a limit: a run made again whole (a dimension dropped from every statement of its cost, the chain hashed again) reads well to this tool, for the chain holds no secret; the independent check S105 tells it by the pack files
        for e in thin['trace']:
            for key in ('cost','full_cost'):e['data'].get(key,{}).pop('attention',None)
        thin['cost'].pop('attention');self.assertEqual((sorted(cost_receipts(sealed(thin))['total']),sorted(cost_receipts(r)['total'])),(['compute','money'],['attention','compute','money']))
        bare=copy.deepcopy(r);del bare['trace'][at]['data']['receipt']   # a chain that hashes, whose effect row carries no receipt
        first=copy.deepcopy(r);first['trace']=[first['trace'][at],first['trace'][at-1]]   # the step's row put before its own gate row: what stands directly before the first row of a chain is no row, not the last one
        with self.assertRaises(ValueError) as refusal:cost_receipts(sealed(first))
        self.assertEqual(str(refusal.exception),pairing)
        with self.assertRaises(ValueError) as refusal:cost_receipts({'trace':[{}]})   # a row with no fields is a chain that does not hash
        self.assertEqual(str(refusal.exception),chain)
        for junk in (None,[],'run',{'trace':'x','trace_root_sha256':'GENESIS'},{'trace':[7]},sealed(bare)):   # what is no run record is refused in the same way, never with another error
            with self.assertRaises(ValueError,msg=repr(junk)[:60]) as refusal:cost_receipts(junk)
            self.assertIn(str(refusal.exception).split('(')[0],('Not a run record with a trace: AttributeError','Not a run record with a trace: KeyError','Not a run record with a trace: TypeError'),repr(junk)[:60])
        register('test_states_cost')(lambda s,m,mid,deps:{'cost':{'usd_cents':1}})
        try:
            w=State.from_packs([{'schema':P2,'id':'w','goals':['e'],'budget':{'usd_cents':200},'preference':['usd_cents','compute','money','attention'],
                                 'methods':[step('call@1','e',{'usd_cents':42},'test_states_cost')],'providers':{'p':1},'grants':['g']}])
            r=Kernel(w).run_standing(execute=True)['runs'][0]
            self.assertEqual((r['model_receipts'][0]['cost'],cost_receipts(r)['steps'][0]['cost']['usd_cents'],w.budget['usd_cents']),({'usd_cents':1},42,158))   # the handler says 1 cent; the gate charged 42, and that is what is stated
        finally:del ACTIONS['test_states_cost']

    def test_c10_the_authoring_lint_refuses_what_the_kernel_accepts(self):
        good=[pack(n) for n in CONFORM];self.assertEqual(problems(good),[])
        for cid in OURS:self.assertEqual(problems([pack(n) for n in BY[cid][3]]),[],cid)   # the recorded packs are clean
        row=lambda packs,p:[r for r in packs[2]['evidence'] if r['predicate']==p][0];late=lambda packs,*rows:packs.append({'schema':P2,'id':'late','evidence':list(rows)})
        bends={'a flipped verdict':lambda p:row(p,'fitness_in_band').update(truth='TRUE'),
               'a dropped dependency':lambda p:row(p,'fitness_below_band').pop('depends_on'),
               'another version':lambda p:row(p,'fitness_below_band').update(version='cmp-0000000000000000'),
               'half a band':lambda p:p[2]['evidence'].pop(),
               'a number made again without its comparisons':lambda p:late(p,reading('0.95','run-0002')),
               'a float value':lambda p:row(p,'run_fitness').update(value=0.8),
               'another value under the old version':lambda p:row(p,'run_fitness').update(value='0.95'),
               'a value on a row the adapter did not make':lambda p:late(p,{'predicate':'load','truth':'TRUE','verified':True,'source':'x','version':'1','value':'7'}),
               'a number whose version is not the digest of its reading':lambda p:late(p,dict(measured('queue_length','7',source='s',label='l'),version='num-0000000000000000')),
               'a method that makes a comparison':lambda p:p[3]['methods'].append(step('fix-fitness@1','fitness_in_band',{'compute':0})),
               'a method that makes a number':lambda p:p[3]['methods'].append(step('measure-fitness@1','run_fitness',{'compute':1})),
               'a rule that derives a comparison':lambda p:p[1]['rules'].append({'id':'R-WAIVE@1','head':'fitness_in_band','branches':[['waiver_given']],'approved':True}),
               'a rule that derives a number':lambda p:p[1]['rules'].append({'id':'R-FIT@1','head':'run_fitness','branches':[['log_read']],'approved':True}),
               'a step that requires a rule head over a comparison':lambda p:(p[1]['rules'].append({'id':'R-BELOW@1','head':'below_band','branches':[['fitness_below_band']],'approved':True}),
                                                                             p[3]['methods'][0].update(requires=['below_band'])),
               'a budget dimension without a preference':lambda p:(p[0]['budget'].update(tokens=100,calls=3),p[0].pop('preference'))}
        not_it=': is not the comparison the adapter makes from the numbers in these packs';no_number=': compares a number that is not in these packs, or is not a comparison row the adapter made'
        no_row=': carries a value but is not a number row the adapter made (%s)';stale='its version is not the digest of its reading';only=', a row only the adapter makes';both=[W+'fitness_in_band',W+'fitness_below_band']
        words={'a flipped verdict':[x+not_it for x in both],'a dropped dependency':[x+not_it for x in both],'another version':[x+not_it for x in both],'half a band':[both[0]+not_it],   # what the lint says, word for word
               'a number made again without its comparisons':[x+not_it for x in both],
               'a float value':[W+'run_fitness'+no_row%'A number is exact text: digits with one optional point, or digits/digits']+[x+no_number for x in both],
               'another value under the old version':[W+'run_fitness'+no_row%stale]+[x+no_number for x in both],
               'a value on a row the adapter did not make':[W+'load'+no_row%'The label of a number row is a name'],'a number whose version is not the digest of its reading':[W+'queue_length'+no_row%stale],
               'a method that makes a comparison':['fix-fitness@1: makes fitness_in_band'+only],'a method that makes a number':['measure-fitness@1: makes run_fitness'+only],
               'a rule that derives a comparison':['R-WAIVE@1: derives fitness_in_band'+only],'a rule that derives a number':['R-FIT@1: derives run_fitness'+only],
               'a step that requires a rule head over a comparison':['file-finding@1: requires the rule head below_band, which stands over a comparison; a step requires the comparison row itself'],
               'a budget dimension without a preference':['150_conformance_goal: adds the budget dimension calls, tokens without a preference that names it']}
        self.assertEqual(sorted(words),sorted(bends))
        for why,bend in bends.items():
            packs=copy.deepcopy(good);bend(packs)
            self.assertEqual(problems(packs),words[why],why)   # the lint names it, and nothing beside it
            State.from_packs(packs)                            # and the kernel takes the pack
        beside=copy.deepcopy(good);beside[3]['methods'].append(step('archive-log@1','log_archived',{'compute':1},req=['run_log_read']));self.assertEqual(problems(beside),[])   # a step beside the finding step, not below it, is no problem
        count=measured('queue|eu','7',source='s',label='l')   # a fact may carry a bar in its name: the lint reads the name whole
        self.assertEqual(problems([{'schema':P2,'id':'t','evidence':[count],'methods':[step('count@1','queue|eu',{'compute':1})]}]),['count@1: makes queue|eu'+only])
        barred=[{'schema':P2,'id':'t','evidence':[count,compared(count,'>=','5','queue|eu|long')],'rules':[{'id':'R-Q@1','head':'queue_long','branches':[['queue|eu|long']],'approved':True}],'methods':[step('page@1','paged',{'compute':1},req=['queue_long'])]}]
        self.assertEqual(problems(barred),['page@1: requires the rule head queue_long, which stands over a comparison; a step requires the comparison row itself'])
        for dim in ('compute','money','attention'):self.assertEqual(problems([{'schema':P2,'id':'cap','budget':{dim:5}}]),[],dim)   # the three dimensions every State has are no new dimension, also in a first pack with no preference
        # The lint keeps no books of its own: it hands every row to the kernel's evidence door and reads what the door stored. So it holds every row in its own scope, ignores what the door ignores, and sees a decision stand.
        elsewhere=copy.deepcopy(good);late(elsewhere,reading('0.95','run-0002',scope='orgB/workflows'))   # a reading for another scope is another number: it is no problem here, and the look of this scope is what it was
        self.assertEqual((problems(elsewhere),Kernel(State.from_packs(elsewhere)).run_standing(execute=True)['runs'][0]['status']),([],'LOCAL_MODEL_EFFECTS_RECORDED'))
        there=reading('0.8',scope='orgB/x');bound=measured('fitness_band','0.9',source=POLICY,label='band-v1',unit='ratio',scope='orgB/x');hidden=copy.deepcopy(good);row(hidden,'fitness_in_band').update(truth='TRUE')
        late(hidden,bound,there,*band(there,'>=',bound,'fitness_in_band','fitness_below_band'))   # the first build's lint kept one row per name ("the last row wins") and so read only the honest rows of the other scope
        self.assertEqual((problems(hidden),Kernel(State.from_packs(hidden)).run_standing(execute=True)['runs'][0]['status']),
                         ([W+'fitness_in_band: is not the comparison the adapter makes from the numbers in these packs',W+'fitness_below_band: is not the comparison the adapter makes from the numbers in these packs'],'SUPPORTED_BY_EVIDENCE'))   # a row that says TRUE for 0.8 >= 0.9 is not hidden by honest rows of the same names in another scope
        self.assertEqual(problems([dict(p,evidence=[dict(r,scope='orgB/x') for r in p.get('evidence',[])]) for p in good]),[])   # the same case with every row sent to another scope: clean there
        waiver={'predicate':'fitness_in_band','truth':'TRUE','verified':True,'final':True,'source':'owner','version':'waiver-1'};said=W+'fitness_in_band: '
        for why,packs,first in (('a decision made before the band arrives',good[:2]+[{'schema':P2,'id':'waiver','evidence':[waiver]}]+good[2:],said+'the kernel does not store this row of 152_run_fitness (it is not verified, or a decision stands on its fact)'),
                                ('a decision made after it',good+[{'schema':P2,'id':'waiver','evidence':[waiver]}],W+'fitness_below_band: is not the comparison the adapter makes from the numbers in these packs'),
                                ('another writer\'s row in the place of a row of the band',good+[{'schema':P2,'id':'desk','evidence':[{'predicate':'fitness_in_band','truth':'TRUE','verified':True,'source':'desk','version':'1'}]}],
                                 W+'fitness_below_band: is not the comparison the adapter makes from the numbers in these packs')):
            found=problems(packs);w=State.from_packs(packs);self.assertEqual((found[0],self._truths(w,'fitness_in_band','fitness_below_band')),(first,['TRUE','TRUE']),why)   # the kernel takes the packs and reads both rows of the band TRUE at 0.8
            if 'after' in why or 'writer' in why:self.assertEqual(found[1:],[said+"a row the adapter did not make (a decision, or another writer's row) stands where these packs carry a number or a comparison"],why)
            self.assertEqual(Kernel(w).run_standing(execute=True)['runs'][0]['status'],'SUPPORTED_BY_EVIDENCE',why)   # and the goal stands on it, under the band: only the lint says so
        lone=reading('0.85','run-0004');one=[good[0],{'schema':P2,'id':'t','rules':[one_rule(['fitness_in_band'])],'evidence':[lone,compared(lone,'>=','0.9','fitness_in_band')]}]
        self.assertEqual((problems(one),problems(one+[{'schema':P2,'id':'desk','evidence':[{'predicate':'fitness_in_band','truth':'TRUE','verified':True,'source':'desk','version':'1'}]}])),
                         ([],[said+"a row the adapter did not make (a decision, or another writer's row) stands where these packs carry a number or a comparison"]))   # also where the comparison is one row authored alone, with no band to miss it
        unverified=copy.deepcopy(good);late(unverified,dict(reading('0.95','run-0002'),verified=False))
        self.assertEqual(problems(unverified),[W+'run_fitness: the kernel does not store this row of late (it is not verified, or a decision stands on its fact)'])   # a number the door ignores is no new reading
        marks={'the adapter\'s source and no recipe':{'predicate':'x_ok','truth':'TRUE','verified':True,'source':SOURCE,'version':'1'},'a recipe under another source':{'predicate':'x_ok','truth':'TRUE','verified':True,'source':'desk','version':'1','compares':{}},
               'the kind COMPARISON alone':{'predicate':'x_ok','truth':'TRUE','verified':True,'source':'desk','version':'1','evidence_kind':'COMPARISON'},'the kind NUMBER without a value':{'predicate':'x','truth':'TRUE','verified':True,'source':'desk','version':'1','evidence_kind':'NUMBER'},
               'a value alone':{'predicate':'x','truth':'TRUE','verified':True,'source':'desk','version':'1','value':'7'}}
        for why,marked in marks.items():   # a row that carries any one of the adapter's marks is held to be exactly what the adapter makes
            packs=copy.deepcopy(good);late(packs,marked);self.assertEqual(len(problems(packs)),1,why);self.assertIn(W+marked['predicate']+': ',problems(packs)[0],why)
            packs=copy.deepcopy(good);late(packs,dict(marked,verified=False))   # and the same row, not verified: the door ignores it, and one mark is enough for the lint to say so
            self.assertEqual(problems(packs),[W+marked['predicate']+': the kernel does not store this row of late (it is not verified, or a decision stands on its fact)'],why)
        packs=copy.deepcopy(good);late(packs,{'predicate':'x','truth':'TRUE','verified':True,'source':'desk','version':'1','note':'no mark of the adapter'});self.assertEqual(problems(packs),[])
        packs=copy.deepcopy(good);packs[1]['rules'].append({'id':'R-DRAFT@1','head':'fitness_in_band','branches':[['waiver_given']],'approved':False});self.assertEqual(problems(packs),[])   # a rule that is not approved derives nothing: the kernel keeps it as a proposal
        packs=copy.deepcopy(good)+[{'schema':P2,'id':'next-run','budget':{'money':5,'compute':5,'attention':2}}];self.assertEqual(problems(packs),[])   # a pack that sets the three dimensions every State has adds none and needs no preference
        self.assertEqual(problems([{'schema':P2,'id':'bad','evidence':[{'predicate':'x','truth':'MAYBE','verified':True}]}]),['bad: carries a row the kernel refuses'])   # a row the door refuses is named, not passed over
        before=json.dumps(good);problems(good);self.assertEqual(json.dumps(good),before)   # the lint changes nothing it is handed
        packs=copy.deepcopy(good);bends['a step that requires a rule head over a comparison'](packs)   # what the kernel does with that step: the plan is offered, and the executed step stops, because the step's own gate reads stored rows only; nothing is filed or paid
        w=State.from_packs(packs);r=Kernel(w).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'],r['stopped'],r['model_receipts'],w.budget),('STEP_STOPPED',{'method':'file-finding@1','reason':'Prerequisite not true before effect: below_band'},[],{'compute':5,'money':5,'attention':2}))
        self.assertEqual(Kernel(State.from_packs(packs)).run_standing()['runs'][0]['status'],'PLAN_READY')   # and the dry look cannot tell
        def world(preference):   # a new budget dimension: two ways to one effect that differ only in the added dimensions
            p={'schema':P2,'id':'w','goals':['e'],'budget':{'usd_cents':200,'tokens':10000},'providers':{'p':2},'grants':['g'],
               'methods':[step('aaa-dear@1','e',{'usd_cents':90,'tokens':100}),step('zzz-cheap@1','e',{'usd_cents':10,'tokens':200})]}
            return dict(p,preference=preference) if preference else p
        chosen=lambda p:Kernel(State.from_packs([p])).run_standing()['runs'][0]['actions']
        self.assertEqual(chosen(world(['usd_cents','tokens','compute','money','attention'])),['zzz-cheap@1'])   # cheaper in the first-named dimension
        self.assertEqual(chosen(world(['tokens','usd_cents','compute','money','attention'])),['aaa-dear@1'])
        self.assertEqual(chosen(world(None)),['aaa-dear@1'])   # the kernel takes the pack; the added dimensions are in no preference, so the method's name decides: the dearer way
        self.assertEqual(problems([world(['usd_cents','tokens','compute','money','attention'])]),[])
        self.assertEqual([('without a preference' in p) for p in problems([world(None)])],[True])   # the lint asks for the preference
        again=[world(['usd_cents','tokens','compute','money','attention']),{'schema':P2,'id':'next-run','budget':{'usd_cents':200}}]
        self.assertEqual(problems(again),[])   # a later pack that sets a known dimension again adds none, and needs no preference
        import tools.make_packs as mp   # the pack file of this version, run here with a pack() that only notes what would be written: every pack is built and linted before the first one is written
        src=(ROOT/'tools'/'packs'/'numbers.py').read_text();made={}
        def author(method):
            made.clear();exec(compile(src,'tools/packs/numbers.py','exec'),{'__name__':'tools.packs.numbers','pack':lambda name,**fields:made.update({name:fields}),'fact':mp.fact,'rule':mp.rule,'method':method})
        author(mp.method)
        self.assertEqual(list(made),['150_conformance_goal','151_conformance_theory','152_run_fitness','152_number_alone','153_finding_method','154_run_fitness_in_band','155_loan_goal','156_loan_review','157_review_queue','158_queue_reviews',
                                     '158_run_cap_again','159_one_row_alone'])
        for name,fields in made.items():self.assertEqual(json.loads(json.dumps(dict({'schema':P2,'id':name},**fields))),pack(name),name)   # what the file hands to pack() is what the scenario file holds
        def careless(*a,**kw):   # an author who forgets that a method under the ceiling costs it
            m=mp.method(*a,**kw);m['cost'].pop('dept_usd_cents',None);return m
        with self.assertRaises(SystemExit) as stopped:author(careless)
        self.assertEqual((made,str(stopped.exception).startswith('pack lint: '),'without costing the ceiling dept_usd_cents the same' in str(stopped.exception)),({},True,True))   # the lint stops the file, and not one pack was written

    def test_c11_goals_are_ranked_by_impact_when_the_pack_is_authored(self):
        impact={'big_loan_reviewed':'9','small_loan_reviewed':'1'}
        self.assertEqual(ranked(['small_loan_reviewed','big_loan_reviewed'],impact),['big_loan_reviewed','small_loan_reviewed'])
        self.assertEqual(ranked(['c','a','b'],{'a':'1','b':'1','c':'2.5'}),['c','a','b'])   # equal impacts listed by name stay as listed: "by name" and "in the order given" are one order
        self.assertEqual(ranked(['a','b','c'],{'a':'1/2','b':'0.5','c':'0.50'}),['a','b','c'])
        for goals,table in ((['b','a'],{'a':'1','b':'1'}),(['a'],{'a':'1','b':'2'}),(['a','b'],{'a':'1'}),(['a','a'],{'a':'1'}),(['a','b'],{'a':'1','b':'-1'}),(['a','b'],{'a':'1','b':2}),
                            ('ab',{'a':'1','b':'2'}),(['a',1],{'a':'1',1:'2'}),(['a','b'],[('a','1'),('b','2')])):
            with self.assertRaises(ValueError,msg=(goals,table)):ranked(goals,table)
        for goals,table,said in ((['b','a'],{'a':'1','b':'1'},'Goals with equal impact are listed by name'),(['a'],{'a':'1','b':'2'},'Every goal has one impact')):
            with self.assertRaises(ValueError) as refusal:ranked(goals,table)
            self.assertEqual(str(refusal.exception),said,goals)
        self.assertEqual((problems([{'schema':P2,'id':'t','impact':{'a':'1'}}]),problems([{'schema':P2,'id':'t','goals':['b','a'],'impact':{'a':'1','b':'1'}}])),
                         (['t: Every goal has one impact'],['t: Goals with equal impact are listed by name']))   # the lint says the same of a pack: a table with no goals, equal impacts out of the order of their names
        def queue(goals):   # two loan reviews costing 6 each on a budget of 10
            return State.from_packs([{'schema':P2,'id':'q','scope':'orgA/lending','goals':goals,'impact':impact,'budget':{'money':10},'providers':{'p':2},'grants':['g'],
                                      'methods':[step('review-big@1','big_loan_reviewed',{'money':6}),step('review-small@1','small_loan_reviewed',{'money':6})]}])
        order=lambda goals:[(r['goal'],r['status']) for r in Kernel(queue(goals)).run_standing(execute=True)['runs']]
        self.assertEqual(order(ranked(['small_loan_reviewed','big_loan_reviewed'],impact)),[('big_loan_reviewed','LOCAL_MODEL_EFFECTS_RECORDED'),('small_loan_reviewed','RESOURCE_REQUIRED')])
        self.assertEqual(order(['small_loan_reviewed','big_loan_reviewed']),[('small_loan_reviewed','LOCAL_MODEL_EFFECTS_RECORDED'),('big_loan_reviewed','RESOURCE_REQUIRED')])   # the kernel takes goals in the order given and ignores `impact`
        with self.assertRaises(ValueError):State().apply({'schema':P2,'id':'q','goals':[{'goal':'big_loan_reviewed','impact':9}]})   # a number on a goal is refused by the kernel
        q=pack('157_review_queue');self.assertEqual((q['goals'],q['impact']),(['big_loan_reviewed','small_loan_reviewed'],impact))   # the pack carries the table it was ranked from
        self.assertTrue(any('order of their impact' in p for p in problems([dict(q,goals=['small_loan_reviewed','big_loan_reviewed']),pack('158_queue_reviews')])))
        again=[q,pack('158_queue_reviews'),{'schema':P2,'id':'later','goals':['small_loan_reviewed','big_loan_reviewed']}]   # a later pack sets the goals again and carries no table: the kernel takes its order, the lint holds it to the last table
        self.assertEqual((problems(again),[(r['goal'],r['status']) for r in Kernel(State.from_packs(again)).run_standing(execute=True)['runs']]),
                         (['later: the goals are not in the order of their impact'],[('small_loan_reviewed','LOCAL_MODEL_EFFECTS_RECORDED'),('big_loan_reviewed','RESOURCE_REQUIRED')]))
        for goals,said in ((['big_loan_reviewed','small_loan_reviewed'],[]),(['big_loan_reviewed'],['later: Every goal has one impact']),(['big_loan_reviewed','small_loan_reviewed','third_loan_reviewed'],['later: Every goal has one impact'])):
            self.assertEqual(problems([q,pack('158_queue_reviews'),{'schema':P2,'id':'later','goals':goals}]),said,goals)   # the same order again is fine; a goal dropped or added needs its table
        self.assertEqual(problems([q,pack('158_queue_reviews'),{'schema':P2,'id':'later','goals':['small_loan_reviewed','big_loan_reviewed'],'impact':{'small_loan_reviewed':'5','big_loan_reviewed':'2'}}]),[])   # a later pack that brings its own table is held to that one
        self.assertEqual(problems([{'schema':P2,'id':'early','goals':['b','a']},q,pack('158_queue_reviews')]),[])   # goals set before any table are held to none
        c=scenario(BY[C66]);self.assertEqual((c['run']['goals'],[(r['goal'],r['status']) for r in c['run']['runs']]),(q['goals'],[('big_loan_reviewed','LOCAL_MODEL_EFFECTS_RECORDED'),('small_loan_reviewed','RESOURCE_REQUIRED')]))   # the recorded case

    def test_c12_a_ceiling_is_a_second_dimension_held_by_the_lint(self):
        names=BY[C66][3];c=scenario(BY[C66]);big,small=c['run']['runs'];short=[{'methods':['review-small-loan@1'],'dimension':'dept_usd_cents','need':42,'left':18}]
        self.assertEqual((big['goal'],big['status'],small['goal'],small['status'],c['derived_state']['budget_after']['usd_cents'],c['derived_state']['budget_after']['dept_usd_cents']),
                         ('big_loan_reviewed','LOCAL_MODEL_EFFECTS_RECORDED','small_loan_reviewed','RESOURCE_REQUIRED',158,18))   # 42 fits the run cap (158 left) and not the ceiling (18 left)
        again=recorded()['looks'][C66]['look']['runs']
        self.assertEqual((again[1]['shortfall'],'shortfall' in again[0],[x['trace_root_sha256'] for x in again]),(short,False,[big['trace_root_sha256'],small['trace_root_sha256']]))   # the record: the sequence takes the same look and says which dimension, the need and what was left
        s=State.from_packs([pack(n) for n in names]);k=Kernel(s);k.run_standing(execute=True)
        s.apply({'schema':P2,'id':'next-run','budget':{'usd_cents':200}})   # a pack sets the run cap again; the ceiling is not touched
        later=k.run_standing(execute=True)['runs']
        self.assertEqual(([r['status'] for r in later],s.budget['usd_cents'],shortfall(later[1],s.budget)),(['SUPPORTED_BY_EVIDENCE','RESOURCE_REQUIRED'],200,short))
        w=State.from_packs([{'schema':P2,'id':'w','goals':['dear','cheap'],'budget':{'money':10},'providers':{'p':2},'grants':['g'],'methods':[step('dear@1','dear',{'money':12,'compute':10}),step('cheap@1','cheap',{'money':4})]}])   # the dear step needs all the compute there is, which fits, and more money than there is
        run=attach_shortfall(Kernel(w).run_standing(execute=True),w.budget)   # a refused look that came before a paid one is set against what was left when it was made
        self.assertEqual(([r['status'] for r in run['runs']],run['runs'][0]['shortfall'],w.budget['money']),(['RESOURCE_REQUIRED','LOCAL_MODEL_EFFECTS_RECORDED'],[{'methods':['dear@1'],'dimension':'money','need':12,'left':10}],6))
        w=State.from_packs([{'schema':P2,'id':'w','goals':['e'],'budget':{'money':1},'providers':{'p':0},'grants':['g'],'methods':[step('m@1','e',{'money':2})]}])   # a limit: short of a provider and of money, the look stops under the provider's word and no shortfall is written
        run=attach_shortfall(Kernel(w).run_standing(execute=True),w.budget);self.assertEqual((run['runs'][0]['status'],run['runs'][0]['stop_reasons'],'shortfall' in run['runs'][0]),('PROVIDER_REQUIRED',['PROVIDER_REQUIRED','RESOURCE_REQUIRED'],False))
        nxt=recorded()['next_run']   # the record: one run later the run cap is whole again and the review still stops on the ceiling, with the same shortfall. That is what makes the second dimension a ceiling over runs
        self.assertEqual((nxt['packs'],pack('158_run_cap_again'),[(r['goal'],r['status'],r['model_receipts'],r.get('shortfall')) for r in nxt['look']['runs']],nxt['after']['budget']['usd_cents'],nxt['after']['budget']['dept_usd_cents'],nxt['after']['journal']),
                         (names+['158_run_cap_again'],{'schema':P2,'id':'158_run_cap_again','budget':{'usd_cents':200}},[('big_loan_reviewed','SUPPORTED_BY_EVIDENCE',[],None),('small_loan_reviewed','RESOURCE_REQUIRED',[],short)],200,18,4))
        self.assertEqual(problems([pack(n) for n in nxt['packs']]),[])
        packs=[pack(n) for n in names];self.assertEqual(problems(packs),[])
        free=copy.deepcopy(packs);free[1]['methods'].append(step('file-note@1','note_filed',{'compute':1},grant='action:review-big-loan@1',provider='review-model'));self.assertEqual(problems(free),[])   # a method that costs neither the capped dimension nor the ceiling is not under it
        loose=copy.deepcopy(packs);loose[1]['methods'][1]['cost']={'usd_cents':42};raised=packs+[{'schema':P2,'id':'raise','budget':{'dept_usd_cents':500}}]
        self.assertEqual((problems(loose),problems(raised)),(['review-small-loan@1: costs usd_cents without costing the ceiling dept_usd_cents the same'],['raise: sets the ceiling dept_usd_cents again']))
        self.assertEqual(problems([packs[0]]),[])
        own='157_review_queue: a ceiling names its own dimension and the dimension it caps';missing='the ceiling %s over %s names a dimension the budget does not have'
        for ceilings,said in (({'dept_usd_cents':'usd'},missing%('dept_usd_cents','usd')),({'dept':'usd_cents'},missing%('dept','usd_cents')),({'usd_cents':'usd_cents'},own),(['dept_usd_cents'],own),({'dept_usd_cents':5},own)):   # a ceiling is two dimensions of the budget
            self.assertEqual(problems([dict(packs[0],ceilings=ceilings)]),[said],ceilings)
        w=State.from_packs(loose)   # the kernel takes both: the ceiling is a convention the lint holds
        self.assertEqual(([r['status'] for r in Kernel(w).run_standing(execute=True)['runs']],w.budget['dept_usd_cents'],State.from_packs(raised).budget['dept_usd_cents']),
                         (['LOCAL_MODEL_EFFECTS_RECORDED','LOCAL_MODEL_EFFECTS_RECORDED'],18,500))

    def test_c13_the_kernel_reads_no_number_and_no_action_kind_is_added(self):
        text=(ROOT/'kernel'/'core.py').read_text()
        for word in ('Fraction',"'value'",'compares','usd','impact','NUMBER','COMPARISON','renumber','ceiling','shortfall'):self.assertNotIn(word,text)   # no word of this version in the kernel
        import extensions.numbers as adapter,extensions.numbers_lint as lint
        self.assertEqual(sorted(ACTIONS),sorted(State().actions))
        self.assertFalse([k for k,h in ACTIONS.items() if 'number' in k or 'compar' in k or h['run'].__module__.startswith('extensions.numbers')])   # an adapter, not an action kind
        source=lambda mod:Path(mod.__file__).read_text();imports=lambda mod:[l for l in source(mod).splitlines() if l.startswith(('import ','from '))]
        self.assertEqual(imports(adapter),['from __future__ import annotations','import copy','from fractions import Fraction','from kernel.core import digest'])   # the standard library and the kernel's digest
        self.assertEqual(imports(lint),['from __future__ import annotations','from kernel.core import State, digest','from extensions.numbers import SOURCE, exact, measured, compared, band'])   # the lint reads the kernel's own evidence door
        self.assertFalse([mod.__name__ for mod in (adapter,lint) if 'register(' in source(mod) or 'ACTIONS' in source(mod)])
        ours={c['id'] for c in MORE if c['id'] in OURS};self.assertEqual(ours,set(OURS))   # the four cases are added as files
        older=[c for c in CASES if c[0] not in {m['id'] for m in MORE}]   # the cases built into the lab: none of their packs carries a number or a comparison row
        self.assertTrue(len(older)>=31 and not [row for c in older for n in c[3] for row in pack(n).get('evidence',[]) if 'value' in row or 'compares' in row or row.get('source')==SOURCE])
        before=digest(scenario(BY['04_gates']));s=self._first('0.8');k=Kernel(s);k.run_standing(execute=True);renumber(k,reading('0.95','run-0002'),execute=True)
        self.assertEqual(digest(scenario(BY['04_gates'])),before)   # the adapter keeps nothing between calls: a State that carries no number is recorded as it was

    def test_known_limits_of_numbers_at_the_door(self):
        goal=pack('150_conformance_goal');n=reading('0.8');honest=compared(n,'>=','0.9','fitness_in_band')
        world=lambda rule,rows,**more:State.from_packs([goal,dict({'schema':P2,'id':'t','rules':[rule],'evidence':list(rows)},**more)])
        look=lambda w:attach(Kernel(w).run_standing(execute=True),w)['runs'][0]
        self.assertEqual(look(world(one_rule(['run_fitness>=0.9']),[reading('1.0')]))['status'],'QUERY_EVIDENCE')   # the kernel reads no number: a bound written in a rule is a name nothing answers
        for condition in ({'number':'run_fitness','op':'>=','bound':'0.9'},0.9):
            with self.assertRaises(ValueError):State().apply({'schema':P2,'id':'t','rules':[one_rule([condition])]})
        r=look(world(one_rule(['fitness_in_band']),[n,honest]))   # a failed comparison with no other branch stops under the word for a missing method; the block says what was compared
        self.assertEqual((r['status'],[(x['verdict'],x['number']['value'],x['operator'],x['bound']) for x in r['comparisons']]),('METHOD_ABSENT',[('FALSE','0.8','>=',{'literal':'0.9'})]))
        lie=dict(honest,truth='TRUE');w=world(one_rule(['fitness_in_band']),[n,lie])   # a comparison row is trusted like any verified row: the kernel believes TRUE for 0.8 >= 0.9
        self.assertEqual((look(w)['status'],bool(problems([goal,{'schema':P2,'id':'t','evidence':[n,lie]}]))),('SUPPORTED_BY_EVIDENCE',True))   # only the lint (and the independent checks) redo it
        w=State();self.assertTrue(w.observe({'predicate':'load','truth':'TRUE','verified':True,'source':'x','version':'1','value':0.8}))
        self.assertEqual(w.fact('load')['value'],0.8)   # observe still stores any value, also a float, from another writer
        w=world(one_rule(['fitness_in_band']),[n,honest]);kw=Kernel(w)   # a decision on a comparison's predicate outlives the number
        self.assertTrue(w.observe({'predicate':'fitness_in_band','truth':'TRUE','verified':True,'final':True,'source':'owner','version':'waiver-1'}))
        out=renumber(kw,reading('0.5','run-0002'),execute=True)
        self.assertEqual((out['remade'],out['affected'],w.fact('fitness_in_band')['source'],w.fact('fitness_in_band')['truth'],w.fact('run_fitness')['value']),([],[],'owner','TRUE','0.5'))
        measure=step('measure-fitness@1','run_fitness',{'compute':1})   # a number made by a step cannot be judged in the same plan: the look asks for evidence before any step runs
        r=look(world(one_rule(['fitness_in_band']),[],methods=[measure],providers={'p':1},grants=['g']));self.assertEqual((r['status'],r['model_receipts']),('QUERY_EVIDENCE',[]))
        packs=[pack(x) for x in CONFORM];packs[3]=copy.deepcopy(packs[3])   # a method may still make a comparison's predicate true by itself: the kernel runs it, the lint refuses the pack
        packs[3]['methods'].append(step('fix-fitness@1','fitness_in_band',{'compute':0},grant='action:file-finding@1',provider='local-provider'))
        w=State.from_packs(packs);r=look(w)
        self.assertEqual((r['actions'],w.fact('fitness_in_band')['source'],'comparisons' in r,bool(problems(packs))),(['fix-fitness@1'],'LOCAL_MODEL:fix-fitness@1',True,True))
        packs=[copy.deepcopy(pack(x)) for x in CONFORM];packs[1]['rules'].append({'id':'R-WAIVE@1','head':'fitness_in_band','branches':[['waiver_given']],'approved':True})
        packs[1]['evidence'].append({'predicate':'waiver_given','truth':'TRUE','verified':True,'source':'owner-note','version':'1'})
        w=State.from_packs(packs);kw=Kernel(w);dry=kw.run_standing()['runs'][0]   # a rule may still derive a comparison's predicate; the lint refuses the pack. While the comparison reads FALSE the kernel names the conflict on that branch and plans the other one
        self.assertEqual((dry['status'],dry['actions'],('EVIDENCE_CONFLICT','fitness_in_band') in [(e['operation'],e['data'].get('predicate')) for e in dry['trace']],bool(problems(packs))),('PLAN_READY',['file-finding@1'],True,True))
        out=kw.on_event(reading('0.5','run-0002'),execute=True)   # once the comparison is stale the goal stands on the rule
        self.assertEqual(([x['status'] for x in out['runs']],w.fact('fitness_in_band')['truth']),(['SUPPORTED_BY_EVIDENCE'],'UNKNOWN'))
        w=self._first('0.8');forged=dict(reading('0.8'),value='0.95')   # a hand-made row that keeps the old version over another value: the kernel compares versions only, so the old verdict stands
        self.assertTrue(w.observe(forged));self.assertEqual((w.fact('fitness_in_band')['truth'],w.fact('run_fitness')['value']),('FALSE','0.95'))
        self.assertTrue(problems([pack(x) for x in CONFORM]+[{'schema':P2,'id':'late','evidence':[forged]}]))   # the lint sees it, and so does check S100 of the independent checks
        with self.assertRaises(ValueError):renumber(Kernel(w),reading('0.7','run-0002'),execute=True)   # and renumber takes the place of a number the adapter made only
        self.assertEqual(compared(measured('fitness_percent','90',source=LOG,label='run-0001',unit='percent'),'>=','0.9','c')['truth'],'TRUE')   # a literal bound is read in the number's unit and nothing checks that
        w=State.from_packs([goal,{'schema':P2,'id':'t','rules':[one_rule(['queue_length'])],'evidence':[measured('queue_length','0',source=LOG,label='l')]}])
        self.assertEqual(look(w)['status'],'SUPPORTED_BY_EVIDENCE')   # a number row says the number is known, not that it is large: a rule that names the number itself holds for any value, also 0
        r=look(State.from_packs([dict(goal,goals=['fitness_in_band']),{'schema':P2,'id':'t','evidence':[n,honest]}]))   # the goal is the comparison itself: a failed comparison stops under the kernel's word for a missing meaning
        self.assertEqual((r['status'],[(x['verdict'],x['reads']) for x in r['comparisons']]),('SEMANTICS_MISSING',[('FALSE','FALSE')]))
        # the look renumber takes is the kernel's on_event: a goal that rests on the number only through a row made on a comparison (two rows deep, no method between) is not named as affected
        top=reading('1.0');under=compared(top,'>=','0.9','in_band');paper={'predicate':'certificate','truth':'TRUE','verified':True,'source':'desk','version':'1','depends_on':[{'predicate':'in_band','version':under['version']}]}
        w=world(one_rule(['certificate']),[top,under,paper]);kw=Kernel(w);self.assertEqual(kw.run_standing(execute=True)['runs'][0]['status'],'SUPPORTED_BY_EVIDENCE');journal=len(w.event_journal)
        out=renumber(kw,reading('0.5','run-0002'),execute=True)
        self.assertEqual((out['affected'],out['runs'],out['remade'],len(w.event_journal)-journal,w.fact('in_band')['truth'],w.fact('certificate')['truth']),([],[],['in_band'],0,'FALSE','UNKNOWN'))   # no look and no journal row; the certificate reads UNKNOWN, never the old verdict
        self.assertEqual(kw.run_standing(execute=True)['runs'][0]['status'],'QUERY_EVIDENCE')   # the next standing look asks for evidence
        # a run that stands on a row made on a comparison names that row in its trace and not the comparison under it: the block does not carry that comparison (the block of the look that filed the finding does)
        ne=recorded()['events'];r=ne['same_again']['runs'][0];filed=ne['below_again']['runs'][0]
        self.assertEqual((r['status'],[(e['operation'],e['data']['predicate']) for e in r['trace'] if e['operation'] in ('RETAIN','METHOD_ABSENT')],[x['predicate'] for x in r['comparisons']],
                          [d['predicate'] for d in ne['after_same_again']['facts']['sutra/workflows|finding_filed']['depends_on']],[(x['predicate'],x['reads']) for x in filed['comparisons']][1]),
                         ('SUPPORTED_BY_EVIDENCE',[('METHOD_ABSENT','fitness_in_band'),('RETAIN','finding_filed')],['fitness_in_band'],['fitness_below_band'],('fitness_below_band','TRUE')))
        w=self._first('0.8');kw=Kernel(w);purse=dict(w.budget);out=renumber(kw,reading('0.7','run-0002'))   # execute is false unless said: the reading is taken all the same, and the look is dry
        self.assertEqual(([x['status'] for x in out['runs']],w.budget,w.fact('run_fitness')['value'],self._truths(w,'fitness_in_band','fitness_below_band'),len(w.event_journal)),(['PLAN_READY'],purse,'0.7',['FALSE','TRUE'],1))
        # the adapter keeps no order of readings: the one handed in last stands, also an older one delivered late. The comparisons made again carry the versions they had, so the first finding stands again and nothing is paid
        w=self._first('0.8');kw=Kernel(w);kw.run_standing(execute=True);first=w.fact('fitness_below_band')['version'];renumber(kw,reading('0.95','run-0002'),execute=True);purse=dict(w.budget)
        out=renumber(kw,reading('0.8','run-0001'),execute=True)
        self.assertEqual(([(x['status'],x['actions']) for x in out['runs']],w.fact('fitness_below_band')['version'],self._truths(w,'finding_filed'),w.budget),([('SUPPORTED_BY_EVIDENCE',[])],first,['TRUE'],purse))
        # a finding is filed only while the provider slots and the purse last: the recorded packs give two slots and attention 2, and a slot is never returned
        w=self._first('0.8');kw=Kernel(w);kw.run_standing(execute=True);seen=[]
        for value,label in (('0.7','run-0002'),('0.6','run-0003'),('0.5','run-0004')):
            x=renumber(kw,reading(value,label),execute=True)['runs'][0];seen.append((x['status'],x['actions'],self._truths(w,'finding_filed')[0],w.providers['local-provider'],w.budget['attention']))
        self.assertEqual(seen,[('LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1'],'TRUE',0,0),('PROVIDER_REQUIRED',[],'UNKNOWN',0,0),('PROVIDER_REQUIRED',[],'UNKNOWN',0,0)])   # the third and the fourth reading below the band file nothing: the look stops short of a provider, and the old finding no longer reads
        # every finding of one method carries the same receipt: its text names no number and no reading, so only the trace root tells two findings apart
        ne=recorded()['events'];receipts=[ne[key]['runs'][0]['model_receipts'][0]['sha256'] for key in ('first','below_again','first_bare')]
        self.assertEqual((len(set(receipts)),len({ne[key]['runs'][0]['trace_root_sha256'] for key in ('first','below_again')})),(1,2))
        # a row that arrives as an event is not linted: the lint reads packs. The reading that reaches a State alone, as an event or in a pack, is what the kernel answers by reading UNKNOWN (the claim test of C5)
        self.assertEqual(problems([pack(n) for n in CONFORM]+[pack('152_number_alone')]),[])   # the pack that brings the same reading again is no new reading: the comparisons still stand on it

    def test_random_walks_keep_the_books_whole(self):
        import random
        rnd=random.Random(20261113);values=('0','0.5','0.6','0.89','0.9','0.90','9/10','0.91','1','1.0','4/5','17/20');both=('fitness_in_band','fitness_below_band');looks=0
        bad=(dict(reading('0.5'),value=0.5),reading('0.5',scope='orgB/x'),measured('run_fitness','50',source=LOG,label='l',unit='percent'),measured('fitness_in_band','1',source=LOG,label='l',unit='ratio'))
        for walk in range(40):
            s=self._first(rnd.choice(values));k=Kernel(s);k.run_standing(execute=True)
            for turn in range(12):
                op=rnd.choice(('reading','reading','band','bare','refused'));before=self._books(s);journal=len(s.event_journal);runs=[];where=(walk,turn,op)
                if op=='reading':runs=renumber(k,reading(rnd.choice(values),rnd.choice(('run-a','run-b','run-c'))),execute=True)['runs']
                elif op=='band':runs=renumber(k,measured('fitness_band',rnd.choice(values),source=POLICY,label=rnd.choice(('band-a','band-b')),unit='ratio'),execute=True)['runs']
                elif op=='bare':runs=k.on_event(reading(rnd.choice(values),'run-x'),execute=True)['runs']   # past renumber: the comparisons may go stale, never wrong
                else:
                    with self.assertRaises(ValueError):renumber(k,rnd.choice(bad),execute=True)
                    self.assertEqual(self._books(s),before,where)
                number,bound=exact(s.fact('run_fitness')['value']),exact(s.fact('fitness_band')['value']);want={'fitness_in_band':number>=bound,'fitness_below_band':number<bound}
                reads={p:s.fact(p)['truth'] for p in both+('finding_filed',)}
                for p in both:self.assertIn(reads[p],('UNKNOWN','TRUE' if want[p] else 'FALSE'),where)   # a comparison the kernel reads is the comparison of the numbers on the books
                if op in ('reading','band'):   # taken whole: both rows made again, one look, one journal row
                    self.assertEqual(([reads[p] for p in both],len(runs),len(s.event_journal)-journal),(['TRUE' if want[p] else 'FALSE' for p in both],1,1),where)
                for r in runs:
                    looks+=1
                    if r['status']=='SUPPORTED_BY_EVIDENCE':   # the goal never stands on a stale or a wrong verdict
                        self.assertTrue(reads['fitness_in_band']=='TRUE' or (reads['finding_filed'],reads['fitness_below_band'])==('TRUE','TRUE'),where)
                    if r['actions']:self.assertEqual((r['actions'],reads['fitness_below_band']),(['file-finding@1'],'TRUE'),where)   # and a finding is filed only below the band
        self.assertGreater(looks,250)

    def test_the_independent_checks_hold_on_the_record_and_each_refuses_a_forgery_of_its_own(self):
        # The record is what tools/run_all.py wrote before the tests ran. The check module is loaded the way the verifier loads it, and must pass the verifier's own gate on what a check module may do.
        f=ROOT/'qa'/'checks'/'numbers.py';src=f.read_text();ns={'__name__':'qa_checks_numbers'};exec(compile(src,str(f),'exec'),ns);v=verifier();ids=['S10%d'%i for i in range(10)]
        self.assertIsNone(v.guard(src))   # the verifier's gate, on the module's text: it imports json, math and hashlib, and nothing of the lab
        data=json.loads((ROOT/'results'/'actual_run_records.json').read_text());packs={p.stem:json.loads(p.read_text()) for p in sorted((ROOT/'scenarios').glob('*.json'))};core=(ROOT/'kernel'/'core.py').read_text()
        self.assertEqual(data['scenes']['numbers'],json.loads(json.dumps(recorded())))   # the sequence on disk is the sequence the scene makes now (the checks do not run the kernel: this line is what tells a sequence made again from end to end)
        claims,S,nev,seq,lok,out,kept,row_at=(ns[k] for k in ('claims','S','nev','seq','lok','out','kept','row_at'))
        got=claims(data,packs,core);self.assertEqual(([name[:4] for name in got],set(got.values())),(ids[:9],{True}))
        result=ns['checks'](data,ROOT,None,None)
        self.assertEqual(([cid[:4] for cid,_,_ in result],[ok for _,ok,_ in result],result[-1][0],[detail for _,_,detail in result]),(ids,[True]*10,'S109_number_claims_fail_on_forged_records',['']*10))
        rows,why=v.module_rows(f,data,ROOT,set())   # run the way the verifier runs a delivered module: ten rows, numbered S100 to S109, each (id, true or false, text)
        self.assertEqual((why,rows,[v.number(cid) for cid,_,_ in rows]),(None,[tuple(x) for x in result],list(range(100,110))))
        self.assertEqual((len(ns['RECORD_FORGERIES']),len(ns['PACK_FORGERIES']),len(ns['KERNEL_FORGERIES'])),(158,31,3))   # forgeries of the record, of the pack files and of the kernel's source: the numbers the README passage states
        for what,dud in (('a forgery that changes nothing',lambda d:None),('a forgery that cannot be made on this record',lambda d:d['no_such_block'].clear())):   # S109 itself: it fails when a forgery is accepted, and when one shows nothing
            ns['RECORD_FORGERIES'].append(dud)
            try:shown=ns['checks'](data,ROOT,None,None)
            finally:ns['RECORD_FORGERIES'].pop()
            self.assertEqual(([ok for _,ok,_ in shown],shown[-1][2]),([True]*9+[False],'forgeries that no check refused, or that could not be made: record %d'%len(ns['RECORD_FORGERIES'])),what)
        # checks() never raises: a record, a pack file or a kernel source it cannot read is ten failed rows that say so
        gone=lambda *keys:{k:x for k,x in data.items() if k not in keys}
        for what,broken,root in (('no cases',gone('cases'),ROOT),('no sequence',gone('scenes'),ROOT),('not a record',[],ROOT),('a sequence of another shape',dict(data,scenes={'numbers':{'looks':[]}}),ROOT),
                                 ('no pack files and no kernel source',data,ROOT/'no_such_folder')):
            bad=ns['checks'](json.loads(json.dumps(broken)),root,None,None)
            self.assertEqual(([cid[:4] for cid,_,_ in bad],[ok for _,ok,_ in bad],len({detail for _,_,detail in bad}),bad[0][2].startswith('the record, the pack files or the kernel source cannot be read: ')),(ids,[False]*10,1,True),what)
        def refused(change,on_packs=False):   # the checks that refuse a forged copy of the record or of the pack files
            d,p=json.loads(json.dumps(data)),json.loads(json.dumps(packs));change(p if on_packs else d)
            return sorted(name[:4] for name,ok in claims(d,p,core).items() if not ok)
        both=lambda d,change:[change(nev(d,k)['facts'][S+'run_fitness']) for k in ('after_bare_event','after_refused')]
        for change,want,on_packs in (
                (lambda d:both(d,lambda row:row.update(note='reviewed')),['S100','S104'],False),                             # a field more on a number that no comparison still reads (and the row is no longer the reading that arrived)
                (lambda d:nev(d,'after_in_band')['facts'][S+'fitness_in_band'].update(note='reviewed'),['S101'],False),       # a field more on a comparison
                (lambda d:seq(d,C63)['comparisons_record'].update(source_trace='0'*64),['S102'],False),                        # a block bound to another trace
                (lambda d:out(d,C63).update(status='SUPPORTED_BY_EVIDENCE'),['S103'],False),                                   # the finding was not filed
                (lambda d:nev(d,'in_band')['runs'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),['S104'],False),           # the look after a reading in band filed something
                (lambda d:lok(d,C65)['look']['cost_receipts'][0]['steps'][0]['cost'].update(usd_cents=1),['S105'],False),      # a cost receipt a cent off the gate's row
                (lambda d:row_at(out(d,C65),'ADMISSION',0)['cost'].update(usd_cents=41),['S105','S106'],False),                # the plan's admission row, a cent short
                (lambda d:seq(d,C66,1)['shortfall'][0].update(left=60),['S107'],False),                                        # the ceiling had room
                (lambda d:d['action_handlers'].update(compare={'module':'extensions.numbers','file':'extensions/numbers.py','sha256':'0'*64}),['S108'],False),
                (lambda d:d['scenes']['numbers'].update(spare=dict(seq(d,C63),comparisons=[])),['S102'],False),              # a run kept beside the looks of the sequence
                (lambda d:kept(d,'04_gates').update({'orgA/fulfillment|fitness_in_band':dict(kept(d,C63)[S+'fitness_in_band'],truth='TRUE',scope='orgA/fulfillment')}),['S101'],False),   # the adapter's name on a wrong verdict, in the books of an older case
                (lambda d:kept(d,'04_gates').update({'orgA/fulfillment|run_fitness':dict(kept(d,C63)[S+'run_fitness'],value=0.8,scope='orgA/fulfillment')}),['S100'],False),               # a float under the kind NUMBER, in the books of an older case
                (lambda p:p['153_finding_method']['methods'].append(step('fix-fitness@1','fitness_in_band',{'compute':0})),['S101'],True),   # a method that makes a comparison
                (lambda p:p['155_loan_goal'].pop('preference'),['S106'],True),                                                 # a new dimension no preference names
                (lambda p:p['158_queue_reviews']['methods'][1]['cost'].pop('dept_usd_cents'),['S105','S107'],True),            # a method under the ceiling that does not cost it (and the gate of its run charged the ceiling)
                # the second round. Made whole, as a forger would: every statement of a step's cost changed alike, the chain hashed again, the new root carried to every copy and every block bound to it. Only the pack files tell
                (lambda d:ns['recost_case'](d,C66,lambda c:c.pop('dept_usd_cents',None)),['S105'],False),                     # the ceiling is in no statement of the big review's cost
                (lambda d:ns['recost_case'](d,C66,lambda c:c.clear()),['S105'],False),                                        # the big review cost nothing, in no dimension
                (lambda d:ns['recost_event'](d,'below_again',lambda c:c.clear()),['S105'],False),                             # the second finding cost nothing
                (lambda d:ns['recost_event'](d,'below_again',lambda c:c.pop('attention',None)),['S105'],False),               # the second finding's cost names no attention
                (lambda d:ns['recost_case'](d,'04_gates',lambda c:c.pop('attention',None)),['S105'],False),                   # the same in an older case
                (lambda d:nev(d,'after_band_moved')['facts'][S+'finding_filed'].update(depends_on=[]),['S104'],False),        # the finding of an old reading rests on nothing after the band moved, and so reads again
                (lambda d:nev(d,'after_repaired')['facts'].pop(S+'finding_filed'),['S104'],False),                            # the finding of an old reading is gone from the books
                (lambda d:nev(d,'after_first')['facts'][S+'run_fitness'].update(scope='orgB/elsewhere'),['S100','S104'],False),   # a number row that says another scope than its place
                (lambda d:[w.update(truth='TRUE') for w in ns['case'](d,C63)['four_views']['world'] if w['predicate']==S+'fitness_in_band'],['S102'],False),   # the viewer's copy of case 63 says TRUE for 0.8 >= 0.9
                (lambda d:ns['case'](d,C66)['run']['runs'][1]['learning_record'].update(source_trace='0'*64),['S102'],False),   # the learning of the review that stopped on the ceiling, bound to another trace
                (lambda d:ns['part'](d,'bare')['look']['runs'][0].update(status='SUPPORTED_BY_EVIDENCE'),['S103'],False),      # the number alone was enough
                (lambda d:nev(d,'pack_event')['runs'][0].update(status='SUPPORTED_BY_EVIDENCE'),['S104'],False),               # after the reading in a pack the look stood on the old verdict
                (lambda d:ns['part'](d,'next_run')['look']['runs'][1]['shortfall'][0].update(left=60),['S107'],False),         # one run later the ceiling had room again
                (ns['relabelled_whole'],['S104'],False),      # made whole: the reading that arrived carries another label in the event, on the books, in both comparisons, in the block, in the trace and its chain
                (ns['reviewed_false'],['S102','S107'],False), # made whole in its three copies: the row the big review wrote says FALSE
                (ns['on_a_finding'],['S102'],False),          # the look in band says, in its branch and in its proof alike, that it stood on a finding
                (lambda p:p['153_finding_method']['methods'].append(step('tell-owner@1','owner_told',{'compute':1},req=['finding_filed'])),['S101'],True),   # a step two steps below a comparison that does not name it
                (lambda p:p['158_queue_reviews'].update(goals=['small_loan_reviewed','big_loan_reviewed']),['S107'],True),     # a later pack sets the goals again, out of order
                (lambda p:p['04_admission'].update(budget={'tokens':5}),['S105'],True)):                                       # a pack of an older case says its State had a dimension that no gate row names
            self.assertEqual(refused(change,on_packs),want)
        d=json.loads(json.dumps(data));ns['recost_case'](d,C66,lambda c:c.pop('dept_usd_cents',None));d['added']['scenes']['numbers']=v.sha(d['scenes']['numbers'])   # the first of these on the whole verifier, the sequence sealed again: 67 of 67 on the first build
        self.assertIn(sorted(t['id'][:4] for t in v.inspect(d)['checks'] if not t['pass'] and ours(t['id'],100,109)),(['S105','S109'],['S105','S109','S202']))   # only this version's cost check refuses it (and S109, which wants every claim to hold on the record it is given); where a later version has pinned this version's record, the pin (S202) tells it too
        self.assertEqual(refused(lambda d:None),[])
        self.assertEqual(sorted(name[:4] for name,ok in claims(data,packs,core+"\nrow.get('value')").items() if not ok),['S108'])   # a kernel that reads a value is not this version's kernel

    def test_the_scene_states_its_looks_and_runs_and_a_method_id_names_one_method(self):
        # Two rules of the next applier, met now. The scene file states at its top level, once each and as whole numbers read from its text, how many looks
        # (a dict that holds a list under `runs`) and runs (a dict with `trace` and `trace_root_sha256`) its sequence records; nothing else in it looks like a run.
        import ast
        tree=ast.parse((ROOT/'tools'/'scenes'/'numbers.py').read_text())
        said=[(t.id,n.value.value if isinstance(n.value,ast.Constant) else None,len(n.targets)) for n in tree.body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name) and t.id in ('LOOKS','RUNS')]
        self.assertEqual(said,[('LOOKS',19,1),('RUNS',20,1)])
        found={'looks':0,'runs':0,'odd':0}
        def walk(v,item=False):   # the next applier's count: every item of a `runs` list and every dict with a `trace` must be a whole run
            if type(v) is dict:
                if 'trace' in v and 'trace_root_sha256' in v:found['runs']+=1
                elif 'trace' in v or item:found['odd']+=1
                if type(v.get('runs')) is list:found['looks']+=1
                for key,x in v.items():
                    if key=='runs' and type(x) is list:
                        for y in x:walk(y,True)
                    else:walk(x)
            else:
                if item:found['odd']+=1
                if type(v) is list:
                    for x in v:walk(x)
        walk(json.loads(json.dumps(recorded())))
        self.assertEqual(found,{'looks':19,'runs':20,'odd':0})
        self.assertEqual((len(looks_of(recorded())),len([x for x in recorded()['bare'].values() if isinstance(x,dict) and x.get('runs')==[]])),(18,1))   # the eighteen looks with runs, and the reading that nothing compares: a look of no run
        # A method id names one method in the whole lab: a pack may name a method id that another pack names only with the same method, field for field.
        table={}
        for f in sorted((ROOT/'scenarios').glob('*.json')):
            for m in json.loads(f.read_text()).get('methods',[]):table.setdefault(m['id'],set()).add(json.dumps(m,sort_keys=True))
        self.assertEqual(([mid for mid,content in table.items() if len(content)>1],len(table)>=29),([],True))
        ours=[m['id'] for n in ('153_finding_method','156_loan_review','158_queue_reviews') for m in pack(n)['methods']]
        self.assertEqual((ours,[len(table[mid]) for mid in ours]),(['file-finding@1','review-loan-file@1','review-big-loan@1','review-small-loan@1'],[1,1,1,1]))

    # ---- The confirming round: two refuters on the build the second round left. By rulings R19 and R34 of the program none of its findings is settled with new code: the
    # passage was corrected, and the tests below pin what the delivery does today. They hold: three kinds of forged record that every check passes and that only a remake
    # tells (limit v); the answer to a step of kind `ask`, which is a decision and outlives every reading (limit u); the words of C6, C9 and C11 and the second half of
    # limit (p); and one assertion for every mutant of the adapter, of the lint and of the pack file that the tests above let live and that changes what the code does.
    def _checks_on_disk(self):
        """The check module's own names, the verifier, the record on disk, the pack files and the kernel's source, read as the test of the independent checks reads them."""
        f=ROOT/'qa'/'checks'/'numbers.py';ns={'__name__':'qa_checks_numbers'};exec(compile(f.read_text(),str(f),'exec'),ns)
        data=json.loads((ROOT/'results'/'actual_run_records.json').read_text());packs={p.stem:json.loads(p.read_text()) for p in sorted((ROOT/'scenarios').glob('*.json'))}
        return ns,verifier(),data,packs,(ROOT/'kernel'/'core.py').read_text()

    def test_settled_forged_records_that_every_check_passes_are_told_by_the_sequence_made_again(self):
        # Limit (v). The checks do not run the kernel, and of the two rows made again after a reading S104 holds only that the look names both and that both read. Each record
        # below is forged in memory the way a forger would make it: every statement of the thing changed alike, the chain hashed again, the sequence sealed again. The nine
        # claims hold on every one, and the whole verifier passes all of them in one record. What tells each is the line that makes the sequence again and compares it
        # (and, on a lab where a later version has pinned this version's cases and sequence, that pin: check S202 of the add-on base, which reads a book kept beside the record).
        ns,v,data,packs,core=self._checks_on_disk();S,sha,canon,nev=(ns[k] for k in ('S','sha','canon','nev'));both=('fitness_in_band','fitness_below_band')
        made_now=json.loads(json.dumps(recorded()));self.assertEqual(data['scenes']['numbers'],made_now)   # the honest record: the sequence on disk is the sequence made now
        def remade(d,snap,look,change):   # both rows of the band in the snapshot after a reading, changed alike; the block of the look, the row its trace retained, the chain and the cost receipt follow
            facts=nev(d,snap)['facts'];r=nev(d,look)['runs'][0]
            for p in both:
                change(facts[S+p]);facts[S+p]['version']='cmp-'+sha(canon(facts[S+p]['compares']))[:16]
            for x in r['comparisons']:
                row=facts[S+x['predicate']];x.update(number=copy.deepcopy(row['compares']['number']),operator=row['compares']['op'],bound=copy.deepcopy(row['compares']['bound']),version=row['version'])
            for e in r['trace']:
                if e['operation']=='RETAIN' and e['data']['predicate'] in both:e['data']['version']=facts[S+e['data']['predicate']]['version']
            ns['rehash'](r);r['comparisons_record']={'source_trace':r['trace_root_sha256'],'comparisons_sha256':sha(r['comparisons'])};ns['receipt_again'](nev(d,look))
        other_operators=lambda row:row['compares'].update(op={'>=':'>','<':'<='}[row['compares']['op']])
        def written_in(text):return lambda row:(row['compares'].update(bound={'literal':text}),row.update(depends_on=row['depends_on'][:1]))   # a bound written into the row, which then rests on the number alone
        def strangers(d):
            for p in both:del nev(d,'after_band_moved')['facts'][S+p]['compares']['partner']
        def made_its_goal(cid):return lambda d:(ns['out'](d,cid),ns['case'](d,cid)['run']['runs'][0],ns['seq'](d,cid))   # the three copies of the first run of a case: the outcome, the run block, the look the sequence took again
        def keys(d):   # a key more on eight dicts that are no rows
            for where in (nev(d,'after_in_band'),nev(d,'in_band'),nev(d,'in_band')['runs'][0],nev(d,'in_band')['runs'][0]['provenance'][0],ns['part'](d,'alone'),ns['case'](d,C63)['derived_state'],ns['case'](d,C63)['four_views'],d['scenes']['numbers']):
                where['waiver']={'predicate':'fitness_in_band','truth':'TRUE'}
        forged={'after the reading in band the two rows made again say > and <=, where the rows they replace said >= and <':lambda d:remade(d,'after_in_band','in_band',other_operators),
                'after the reading in band the two rows made again stand against 0.5, written into them, and no longer rest on the band':lambda d:remade(d,'after_in_band','in_band',written_in('0.5')),
                'after the band moved to 0.6 the two rows made again judge 0.7 against 0.1':lambda d:remade(d,'after_band_moved','band_moved',written_in('0.1')),
                'after the band moved the two rows made again no longer name each other':strangers,
                'the run that made the loan review says its goal read TRUE before it':lambda d:[r.update(goal_truth_before='TRUE') for r in made_its_goal(C65)(d)],
                'the run that made the big review says the same':lambda d:[r.update(goal_truth_before='TRUE') for r in made_its_goal(C66)(d)],
                'the run that made the loan review argues in other words':lambda d:[r.update(proof=['the owner said so']) for r in made_its_goal(C65)(d)],
                'and so does the run that made the big review':lambda d:[r.update(proof=['the owner said so']) for r in made_its_goal(C66)(d)],
                'a key more on a snapshot, on a look of the events, on its run, on a provenance entry, on a part of the sequence, on the sequence, and on the books and the views of a case':keys}
        def sealed(*changes):   # a copy of the record on disk with the changes made and the sequence sealed again
            d=json.loads(json.dumps(data))
            for change in changes:change(d)
            d['added']['scenes']['numbers']=v.sha(d['scenes']['numbers']);return d
        failing=lambda d:sorted(name[:4] for name,ok in ns['claims'](d,packs,core).items() if not ok)
        for what,change in forged.items():
            d=sealed(change);self.assertEqual((failing(d),d['scenes']['numbers']==made_now),([],False),what)   # the nine claims hold on the forged record, and the sequence made again is not the forged one
        verdict=v.inspect(sealed(*forged.values()))   # all nine in one record, on the whole verifier: the built-in checks, the checks of the add-on base and this version's ten
        self.assertIn([t['id'][:4] for t in verdict['checks'] if not t['pass'] and ours(t['id'],100,109)],([],['S202']))   # every check passes it; where a later version has pinned this version's record, the pin alone tells it
        made=scenario(BY[C65])['outcome'];self.assertEqual((made['goal_truth_before'],made['proof'][0]),('UNKNOWN','review-loan-file@1 would establish loan_file_reviewed'))   # what the case made again says of the two fields no check reads
        def turned(d):   # a bound that turns the verdict round (0.95 against 0.99), every statement of it changed alike
            remade(d,'after_in_band','in_band',lambda row:(written_in('0.99')(row),row.update(truth={'TRUE':'FALSE','FALSE':'TRUE'}[row['truth']])));r=nev(d,'in_band')['runs'][0]
            for x in r['comparisons']:x.update(verdict=nev(d,'after_in_band')['facts'][S+x['predicate']]['truth'],reads=nev(d,'after_in_band')['facts'][S+x['predicate']]['truth'])
            r['comparisons_record']['comparisons_sha256']=sha(r['comparisons'])
        self.assertEqual([failing(sealed(change)) for change in (turned,lambda d:nev(d,'after_band_moved')['facts'][S+both[0]]['compares'].pop('partner'),lambda d:nev(d,'in_band')['runs'][0].update(goal_truth_before='TRUE'),
                                                                 lambda d:nev(d,'after_in_band')['facts'][S+both[0]].update(waiver=True),lambda d:nev(d,'after_in_band')['facts'][S+'run_fitness'].update(waiver=True),
                                                                 lambda d:nev(d,'after_first')['facts'][S+'finding_filed'].update(waiver=True))],
                         [['S102'],['S101'],['S102'],['S101'],['S100','S101','S104'],['S104']])   # where the limit ends: a verdict turned round; one row of the two that no longer names the other; the truth before of a look whose goal is a rule head; a key more on a comparison row, on a number row, on a finding row

    def test_settled_the_answer_to_an_ask_is_a_decision_and_outlives_every_reading(self):
        # Limit (u). A step of kind `ask` is answered by a decision on its effect, and a decision rests on nothing. So what an answer made true stays true whatever the next
        # reading says, also when the ask requires the comparison itself, as the lint asks of a step below a comparison. The lint is silent on both packs below.
        ask=lambda mid,effect,to,req:step(mid,effect,{'attention':1},'ask',req,grant='action:file-finding@1',provider='local-provider',ask_to=to)
        seen=lambda out:[(x['goal'],x['status'],x['actions']) for x in out['runs']]
        packs=[pack(n) for n in CONFORM];packs[3]=dict(packs[3],methods=[ask('confirm-finding@1','finding_filed','reviewer',['fitness_below_band'])])   # (A) the finding itself is confirmed by a reviewer: the ask stands on the comparison
        self.assertEqual(problems(packs),[])
        s=State.from_packs(packs);k=Kernel(s);first=k.run_standing(execute=True)
        self.assertEqual((seen(first),list(open_asks(s)),self._truths(s,'finding_filed'),s.budget['attention']),([('run_judged','WAITING',['confirm-finding@1'])],[W+'finding_filed'],['UNKNOWN'],1))
        out=answer(k,first['runs'][0]['model_receipts'][0],'TRUE','reviewer',execute=True);row=s.fact('finding_filed')
        self.assertEqual((seen(out),row['truth'],row['final'],row['source'],'depends_on' in row),([('run_judged','SUPPORTED_BY_EVIDENCE',[])],'TRUE',True,'STAMP:reviewer',False))   # the answer is a decision, and it rests on nothing
        out=renumber(k,reading('0.95','run-0002'),execute=True)   # the next run is in band: the comparison under the finding says FALSE, and the finding stays TRUE
        self.assertEqual((seen(out),self._truths(s,'fitness_in_band','fitness_below_band','finding_filed')),([('run_judged','SUPPORTED_BY_EVIDENCE',[])],['TRUE','FALSE','TRUE']))
        purse=dict(s.budget);out=renumber(k,reading('0.5','run-0003'),execute=True)   # below the band again, further than the first time: nobody is asked and nothing is filed or paid
        self.assertEqual((seen(out),out['runs'][0]['proof'][-1],list(open_asks(s)),s.budget,self._truths(s,'fitness_below_band','finding_filed')),
                         ([('run_judged','SUPPORTED_BY_EVIDENCE',[])],'finding_filed observed TRUE (STAMP:reviewer)',[],purse,['TRUE','TRUE']))   # the look stands on the stamp given for the reading of 0.8
        packs=[pack(n) for n in CONFORM]+[{'schema':P2,'id':'ack','goals':['run_judged','owner_acknowledged'],'budget':{'attention':9},'providers':{'local-provider':10},   # (B) the owner is asked to acknowledge the finding, one step below it
                                          'methods':[ask('ask-owner@1','owner_acknowledged','owner',['finding_filed','fitness_below_band'])]}]                          # and the ask requires the comparison itself
        self.assertEqual(problems(packs),[])
        s=State.from_packs(packs);k=Kernel(s);first=k.run_standing(execute=True)
        self.assertEqual(seen(first),[('run_judged','LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1']),('owner_acknowledged','WAITING',['ask-owner@1'])])
        out=answer(k,first['runs'][1]['model_receipts'][0],'TRUE','owner',execute=True);self.assertEqual((seen(out),s.fact('owner_acknowledged')['source']),([('owner_acknowledged','SUPPORTED_BY_EVIDENCE',[])],'STAMP:owner'))
        out=renumber(k,reading('0.95','run-0002'),execute=True)   # in band: the finding no longer reads, the acknowledgement of it does
        self.assertEqual((seen(out),self._truths(s,'finding_filed','owner_acknowledged')),([('run_judged','SUPPORTED_BY_EVIDENCE',[]),('owner_acknowledged','SUPPORTED_BY_EVIDENCE',[])],['UNKNOWN','TRUE']))
        out=renumber(k,reading('0.7','run-0003'),execute=True)    # below the band again: a second finding is filed and paid, and the owner is not asked about it
        self.assertEqual((seen(out),list(open_asks(s)),self._truths(s,'finding_filed','owner_acknowledged')),
                         ([('run_judged','LOCAL_MODEL_EFFECTS_RECORDED',['file-finding@1']),('owner_acknowledged','SUPPORTED_BY_EVIDENCE',[])],[],['TRUE','TRUE']))
        # (the same step written as a handler's step is in the test of C5: there the comparison it requires binds its row to a version, and the owner is told of the second finding too)

    def test_settled_words_of_c06_c09_c11_and_the_second_half_of_limit_p(self):
        seq=recorded();ne=seq['events'];adapter=(ROOT/'extensions'/'numbers.py').read_text();kernel=(ROOT/'kernel'/'core.py').read_text()
        # C6: of the six refusals in the record five are sentences of the adapter and one is the kernel's own, passed through: the kernel refuses the flag `execute` on the copy
        self.assertEqual(({why:said for why,said in ne['refused'].items() if said in kernel},[said in adapter for said in ne['refused'].values()]),({'execute is not true or false':'execute is true or false'},[True]*5+[False]))
        with self.assertRaises(ValueError) as refusal:Kernel(State()).on_event(reading('0.95','run-0002'),execute=1)
        self.assertEqual(str(refusal.exception),ne['refused']['execute is not true or false'])
        # C9: a look that holds a run carries one cost receipt per run; the one look that holds none, the reading that nothing compares, carries no cost receipts at all
        self.assertEqual((seq['bare']['event']['runs'],'cost_receipts' in seq['bare']['event'],[('cost_receipts' in x) for x in looks_of(seq)]),([],False,[True]*18))
        # C11: in the recorded case the goal with the higher impact is also the first by name, so the case alone does not tell an order by impact from an order by name.
        # What tells them: `ranked` and the kernel on a queue whose higher impact sorts last by name, and the check S107 on a pack file whose impacts are turned round.
        q=pack('157_review_queue');self.assertEqual((q['goals'],sorted(q['goals']),q['impact']),(['big_loan_reviewed','small_loan_reviewed'],['big_loan_reviewed','small_loan_reviewed'],{'big_loan_reviewed':'9','small_loan_reviewed':'1'}))
        turned={'a_small_reviewed':'1','z_big_reviewed':'9'};order=ranked(sorted(turned),turned);self.assertEqual(order,['z_big_reviewed','a_small_reviewed'])
        w=State.from_packs([{'schema':P2,'id':'q','scope':'orgA/lending','goals':order,'impact':turned,'budget':{'money':10},'providers':{'p':2},'grants':['g'],
                             'methods':[step('review-big@1','z_big_reviewed',{'money':6}),step('review-small@1','a_small_reviewed',{'money':6})]}])
        self.assertEqual([(r['goal'],r['status']) for r in Kernel(w).run_standing(execute=True)['runs']],[('z_big_reviewed','LOCAL_MODEL_EFFECTS_RECORDED'),('a_small_reviewed','RESOURCE_REQUIRED')])
        ns,v,data,packs,core=self._checks_on_disk();p=json.loads(json.dumps(packs));p['157_review_queue']['impact'].update(small_loan_reviewed='10')
        self.assertEqual(sorted(name[:4] for name,ok in ns['claims'](data,p,core).items() if not ok),['S107'])
        # Limit (p), its second half: methods and rules are held by the names of the facts, in whatever scope. A method and a rule of one scope are refused for a number that is on the books of another scope only.
        far=[{'schema':P2,'id':'a','scope':'orgA/here','evidence':[measured('load','7',source='s',label='l',scope='orgB/x')],'methods':[step('make-load@1','load',{'compute':1})],'rules':[{'id':'R-L@1','head':'load','branches':[['x']],'approved':True}]}]
        self.assertEqual((problems(far),problems([dict(far[0],evidence=[])]),sorted(State.from_packs(far).evidence)),(['R-L@1: derives load, a row only the adapter makes','make-load@1: makes load, a row only the adapter makes'],[],['orgB/x|load']))

    def test_settled_the_adapter_one_assertion_for_every_mutant_that_lived(self):
        both=('fitness_in_band','fitness_below_band');whole='A band is made again whole or not at all';load=lambda value,label:measured('queue_load',value,source=LOG,label=label,unit='items')
        # renumber makes again the comparisons that cite the reading and no other: a second number with a band of its own stands on the same books
        s=self._first('0.8');k=Kernel(s);k.run_standing(execute=True);self.assertTrue(all(s.observe(x) for x in [load('7','l-1')]+band(load('7','l-1'),'<=','10','load_ok','load_high')))
        theirs=[s.fact(p) for p in ('load_ok','load_high')];registry=s.actions;out=renumber(k,reading('0.95','run-0002'),execute=True)
        self.assertEqual((out['remade'],[s.fact(p) for p in ('load_ok','load_high')]),(list(both),theirs))   # the band of the other number is neither made again nor named
        self.assertIs(s.actions,registry)   # the State keeps its own registry of action kinds: the copy the reading is tried on shares it, as `apply` does
        out=renumber(k,load('12','l-2'),execute=True);self.assertEqual((out['remade'],out['affected'],self._truths(s,'load_ok','load_high')),(['load_ok','load_high'],[],['FALSE','TRUE']))   # and the other way round
        s=self._first('0.8');k=Kernel(s);self.assertTrue(all(s.observe(x) for x in [load('7','l-1')]+band(load('7','l-1'),'<=','10','load_ok','load_high')[:1]))   # half a band on the other number: its other row was never written
        self.assertEqual(renumber(k,reading('0.95','run-0002'),execute=True)['remade'],list(both));held=self._books(s)   # it does not refuse a reading of this number
        with self.assertRaises(ValueError) as refusal:renumber(k,load('12','l-2'),execute=True)   # a reading of its own number is refused, in the adapter's sentence for a band
        self.assertEqual((str(refusal.exception),self._books(s)),(whole,held))
        # another writer's row that carries a recipe, and a row under the adapter's name that carries none, are no comparisons of the adapter: renumber leaves both as they are, and the block of a run that names them states neither
        s=self._first('0.8');k=Kernel(s);n=reading('0.8');desk=dict(compared(n,'>=','0.5','desk_view'),source='desk');stamp={'predicate':'adapter_stamp','truth':'TRUE','verified':True,'source':SOURCE,'version':'1'}
        s.apply({'schema':P2,'id':'views','goals':['run_judged','views_read'],'rules':[{'id':'R-VIEWS@1','head':'views_read','branches':[['desk_view','adapter_stamp']],'approved':True}],'evidence':[desk,stamp]})
        viewed=attach(k.run_standing(execute=True),s)['runs'][1];stored=lambda:[copy.deepcopy(s.evidence[s.key(p)]) for p in ('desk_view','adapter_stamp')]
        self.assertEqual((viewed['status'],[e['data']['predicate'] for e in viewed['trace'] if e['operation']=='RETAIN'],'comparisons' in viewed),('SUPPORTED_BY_EVIDENCE',['desk_view','adapter_stamp'],False))
        kept=stored();out=renumber(k,reading('0.95','run-0002'),execute=True)
        self.assertEqual((out['remade'],stored(),self._truths(s,'desk_view','adapter_stamp')),(list(both),kept,['UNKNOWN','TRUE']))   # the desk's row rests on the old reading and no longer reads: nobody made it again
        # two rows that name each other and say the opposite against one bound row, each on a number of its own, are no band: when the bound moves nothing is made again row by row
        other=measured('other_fitness','0.8',source=LOG,label='run-0001',unit='ratio');moved=measured('fitness_band','0.6',source=POLICY,label='band-v2',unit='ratio')
        w=self._first('0.8');kw=Kernel(w);self.assertTrue(all(w.observe(x) for x in [other,band(other,'>=',BAND,*both)[1]]));held=self._books(w)   # the row below the band now reads the other number
        with self.assertRaises(ValueError) as refusal:renumber(kw,moved,execute=True)
        self.assertEqual((str(refusal.exception),self._books(w)),(whole,held))
        lacking=copy.deepcopy(band(reading('0.8'),'>=',BAND,*both)[0]);del lacking['compares']['op']   # a row under the adapter's name whose recipe lacks a key: refused with ValueError, never with another error
        w=self._first('0.8');kw=Kernel(w);self.assertTrue(w.observe(lacking));held=self._books(w)
        with self.assertRaises(ValueError) as refusal:renumber(kw,reading('0.95','run-2'),execute=True)
        self.assertEqual((str(refusal.exception).split('(')[0],self._books(w)),('Not a number this State can take: KeyError',held))
        with self.assertRaises(ValueError) as refusal:band(reading('0.8'),['>='],'0.9','inside','outside')   # an operator that is no text, also one that cannot be looked up
        self.assertEqual(str(refusal.exception),'A band is two predicates and one operator of < <= > >= == !=')
        # cost_receipts: what is no run record is refused with ValueError, whatever kind of error reading it gives; what it returns is its own copy; a record with no step needs no list of receipts
        r=scenario(BY['04_gates'])['outcome'];at=[e['operation'] for e in r['trace']].index('LOCAL_EFFECT')
        class Short(list):   # a trace that is a list of another kind and answers no index
            def __getitem__(self,i):raise IndexError('no row')
        for junk,error in ((dict(r,trace=None),'TypeError'),(dict(r,trace=Short(r['trace'])),'IndexError')):
            with self.assertRaises(ValueError,msg=error) as refusal:cost_receipts(junk)
            self.assertEqual(str(refusal.exception).split('(')[0],'Not a run record with a trace: '+error)
        with self.assertRaises(ValueError) as refusal:cost_receipts({})   # a record with no trace hashes to no root
        self.assertEqual(str(refusal.exception),'The trace does not hash to its root')
        self.assertEqual(cost_receipts({'trace_root_sha256':'GENESIS'}),{'steps':[],'total':{},'source_trace':'GENESIS','steps_sha256':digest([])})   # an empty chain that names its root is a run of no step
        got=cost_receipts(r);gate=copy.deepcopy(r['trace'][at-1]['data']['cost']);got['steps'][0]['cost']['compute']+=99
        self.assertEqual(r['trace'][at-1]['data']['cost'],gate)   # the receipt states a copy of the gate's cost: changing the receipt does not change the trace
        self.assertEqual((attach({'status':'NO_STANDING_GOAL'},State()),comparisons({'scope':State().scope},State())),({'status':'NO_STANDING_GOAL'},[]))   # a look that holds no runs gets no block, and a run with no trace names no comparison
        # Two mutants of the adapter that live change nothing: `_mates` is only ever handed, as the second name, the partner its first row names; and the number is stored by the kernel's `on_event` whether or not it is among the rows tried first.

    def test_settled_the_lint_one_assertion_for_every_mutant_that_lived(self):
        good=[pack(n) for n in CONFORM];more=lambda **fields:good+[dict({'schema':P2,'id':'more'},**fields)];rule=lambda rid,head,*branch:{'id':rid,'head':head,'branches':[list(branch)],'approved':True}
        act=[step('act@1','acted',{'compute':1},req=['a_holds'])];OVER=['act@1: requires the rule head a_holds, which stands over a comparison; a step requires the comparison row itself']
        # a rule head stands over a comparison through any chain of rules, and only then; rules that derive each other end
        for why,rules,said in (('two rules that derive each other',[rule('R-A@1','a_holds','b_holds'),rule('R-B@1','b_holds','a_holds')],[]),
                               ('a rule that derives itself',[rule('R-SELF@1','a_holds','a_holds')],[]),
                               ('a head that stands over no comparison',[rule('R-READY@1','a_holds','paper_signed')],[]),
                               ('a head two rules above a comparison',[rule('R-TOP@1','a_holds','middle'),rule('R-MID@1','middle','fitness_below_band')],OVER),
                               ('two rules that derive each other, one of them over a comparison',[rule('R-A@1','a_holds','b_holds'),rule('R-B@1','b_holds','a_holds','fitness_below_band')],OVER)):
            self.assertEqual(problems(more(rules=rules,methods=act)),said,why)
        # steps: an ordinary chain of two steps is no problem, also when the first names no prerequisites; a method that names no cost costs no ceiling; a ceiling whose own name is no text is none
        chain=[step('draft@1','drafted',{'compute':1},req=['paper_signed']),step('send@1','sent',{'compute':1},req=['drafted'])]
        self.assertEqual((problems(more(methods=chain)),problems(more(methods=[{key:x for key,x in chain[0].items() if key!='requires'},chain[1]]))),([],[]))
        queue=[pack(n) for n in BY[C66][3]];free=copy.deepcopy(queue);free[1]['methods'].append({key:x for key,x in step('file-note@1','note_filed',{},grant='action:review-big-loan@1',provider='review-model').items() if key!='cost'})
        self.assertEqual((problems(free),problems([dict(queue[0],ceilings={5:'usd_cents'})])),([],['157_review_queue: a ceiling names its own dimension and the dimension it caps']))
        # rows: what the door ignores and the adapter did not mark is no problem; a place the packs carry twice is named once; a scope that is no name is not taken
        self.assertEqual(problems(more(evidence=[{'predicate':'note_read','truth':'TRUE','verified':False,'source':'desk','version':'1'}])),[])
        twice=good+[pack('152_number_alone'),{'schema':P2,'id':'desk','evidence':[{'predicate':'run_fitness','truth':'TRUE','verified':True,'source':'desk','version':'1'}]}]
        no_number=': compares a number that is not in these packs, or is not a comparison row the adapter made'
        self.assertEqual(problems(twice),[W+'fitness_in_band'+no_number,W+'fitness_below_band'+no_number,W+"run_fitness: a row the adapter did not make (a decision, or another writer's row) stands where these packs carry a number or a comparison"])
        nameless=[dict(good[0],scope='')]+good[1:];self.assertEqual(problems(nameless),[])   # the lint's door stays in the scope it was in and reads the rows there
        with self.assertRaises(ValueError) as refusal:State.from_packs(nameless)             # (the kernel refuses such a pack)
        self.assertEqual(str(refusal.exception),'Invalid scope')
        n=reading('0.8');c=compared(n,'>=','0.9','fitness_ok')   # a recipe the lint cannot redo is named, never raised: one that is no recipe at all, and one whose operator is none of the six
        for why,recipe in (('a text','by hand'),('an operator that is none of the six',dict(c['compares'],op='~'))):
            self.assertEqual(problems([good[0],{'schema':P2,'id':'t','evidence':[n,dict(c,compares=recipe)]}]),[W+'fitness_ok'+no_number],why)
        # ranking and the shortfall
        with self.assertRaises(ValueError) as refusal:ranked(['a','b'],['a','b'])   # an impact table that is no table, though it holds the names of the goals
        self.assertEqual((str(refusal.exception),problems([{'schema':P2,'id':'t','goals':['a','b'],'impact':['a','b']}])),('Every goal has one impact',['t: Every goal has one impact']))
        c66=scenario(BY[C66]);small=c66['run']['runs'][1];gate=[e['data'] for e in small['trace'] if e['operation']=='ADMISSION'];before=copy.deepcopy(gate)
        short=shortfall(small,c66['derived_state']['budget_after']);short[0]['methods'].append('another@1')
        self.assertEqual((gate,shortfall({},{}),attach_shortfall({'status':'NO_STANDING_GOAL'},{})),(before,[],{'status':'NO_STANDING_GOAL'}))   # the shortfall names a copy of the gate row's methods; a look with no trace has no shortfall, and one with no runs gets none
        # Three mutants of the lint that live change nothing: of the four kinds of error the lint catches at the kernel's door, the door raises ValueError alone for every row, also one that is no object.

    def test_settled_the_pack_file_lints_every_look_before_it_writes_and_stops_on_a_pack_left_unwritten(self):
        import tools.make_packs as mp,extensions.numbers_lint as lint
        src=(ROOT/'tools'/'packs'/'numbers.py').read_text();made={};handed=[];real=lint.problems
        def author(text=src,refuse=None):   # the pack file run with a pack() that only notes, and with a lint that notes what it is handed and may refuse one look
            made.clear();handed.clear()
            def noting(packs):
                handed.append((json.loads(json.dumps(packs)),dict(made)));return ['refused for the test'] if refuse==len(handed)-1 else real(packs)
            lint.problems=noting
            try:exec(compile(text,'tools/packs/numbers.py','exec'),{'__name__':'tools.packs.numbers','pack':lambda name,**fields:made.update({name:fields}),'fact':mp.fact,'rule':mp.rule,'method':mp.method})
            finally:lint.problems=real
        queue=BY[C66][3];looks=[CONFORM,BY[C64][3],BARE,ALONE,BY[C65][3],queue,queue+['158_run_cap_again']]
        author();self.assertEqual(handed,[([pack(n) for n in names],{}) for names in looks])   # the seven looks of the record, each handed to the lint as its files read, schema and id included, and all of them before the first pack is written
        self.assertEqual(sorted({n for names in looks for n in names}),sorted(made))   # every pack the file writes is in a look that was linted
        for i in range(len(looks)):   # the lint refuses one look, whichever: the file stops there and not one pack is written
            with self.assertRaises(SystemExit) as stopped:author(refuse=i)
            self.assertEqual((made,len(handed),str(stopped.exception)),({},i+1,'pack lint: refused for the test'),i)
        line="pack('159_one_row_alone', **_PACKS.pop('159_one_row_alone'))\n";self.assertEqual(src.count(line),1)
        with self.assertRaises(SystemExit) as stopped:author(src.replace(line,''))   # a pack that is built and linted and whose line to write it is missing: the file stops and names it
        self.assertEqual((str(stopped.exception),len(made)),('pack file numbers: built and not written: 159_one_row_alone',11))

if __name__=='__main__':unittest.main()
