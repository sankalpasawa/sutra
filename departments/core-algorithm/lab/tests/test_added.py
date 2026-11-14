"""The add-on points (0.10.0): what a later version adds as files, and what holds it.

These tests read the built record (results/actual_run_records.json), so they run after tools/make_packs.py, tools/run_all.py and
tools/make_extra.py, as the lab's README runs them. Every add-on file used here is made in a temporary folder: nothing is written
into the lab. The whole verifier is run eight times (it takes seconds); every other forgery goes to the function of the one check it
is meant for. A delivered check module runs in a process of its own, so the tests of that start small processes.

Stated limits are pinned here as the base behaves today (rulings R19 and R34 of the program: a review round that does not refute is settled
without new code, by words and by tests that pin what is stated as a limit). A test that begins "Limit N of the README, pinned" shows the
behaviour the README states under that number; where it asserts a sentence of the README, the sentence and the behaviour stay in step.
These tests take some names in every lab (limit 15): test_the_names_these_tests_take_are_taken_in_every_lab lists them."""
from pathlib import Path
import unittest, sys, json, hashlib, importlib.util, tempfile, shutil, subprocess, ast, io, contextlib, re
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,ACTIONS,digest
import tools.make_packs as mp
import tools.run_all as ra

BUILT_IN_IDS=['S01_source_hash_current', 'S02_old_baseline_immutable', 'S03_distinct_cases', 'S04_all_pack_sha_match', 'S05_all_run_chains', 'S06_receipts_local_only', 'S07_all_plan_costs_nonnegative', 'S08_all_candidates_proposed_only', 'S09_missing_semantics_honest', 'S10_unknown_approval_honest', 'S11_authority_gate', 'S12_added_notification_is_action', 'S13_missing_method_and_recovery', 'S14_pareto_policy_flip', 'S15_new_domain_methods', 'S16_construct_candidate_only', 'S17_reject_bad_contract', 'S18_no_spurious_self_authority', 'S19_tenant_isolation', 'S20_no_standing_no_trigger', 'S21_capacity_denied', 'S22_resources_denied', 'S23_unrelated_no_recompute', 'S24_relevant_recompute', 'S25_dep_invalidation', 'S26_immutable_previous_run', 'S27_reviewed_semantics_only', 'S28_reflection_no_promotions', 'S29_j2_projection_not_closed', 'S30_design_diff', 'S32_implementation_proposal_only_right_shape', 'S33_implementation_enquiry_proposal_only_right_shape', 'S38_implementation_website_proposal_only_right_shape', 'S31_reject_tampered_event', 'S34_kernel_source_without_learning', 'S35_learning_recorded_from_extension', 'S36_learning_bound_to_trace_root', 'S37_standard_from_adapter_evidence', 'S39_website_edges_run_forward', 'S40_kernel_source_without_moved_kinds', 'S41_action_handlers_recorded_by_sha', 'S42_every_run_agrees_with_its_trace_and_packs', 'S43_ask_parks_and_ships_nothing', 'S44_open_ask_is_idempotent', 'S45_yes_resumes_no_is_final', 'S46_another_route_leaves_the_question_answerable', 'S47_stamp_cites_the_issued_receipt', 'S48_claims_fail_on_forged_records', 'S49_every_stop_check_refuses_a_forgery_of_its_own_and_only_the_last_forgery_leans_on_the_case_pin', 'S50_a_blocked_reason_and_the_type_of_a_number_each_refuse_a_forgery_of_their_own']   # the checks of the base in their order, read from the base's own verdict when the points were given (the counts taken out of the ids of S03 and S05)
BUILT_IN_CASES=31
S200,S201,S202,S203,S204=POINT_IDS=['S200_added_cases_match_their_files','S201_recorded_sequences_are_the_scene_files_sealed_and_their_runs_agree_with_their_traces','S202_what_an_earlier_version_recorded_has_not_moved',
                                    'S203_every_added_file_is_listed_by_sha_and_nothing_else_was_put_in','S204_every_receipt_names_an_action_kind_the_record_holds_a_handler_for']
FOUR=['simulate_fact','compile_candidate','emit_artifact','ask']
RECORD=ROOT/'results'/'actual_run_records.json'
ORDER=['00_goal','01_domain','02_methods','03_approval','04_admission']   # the packs of built-in case 04: a plan of one step

KIND_SRC="""from kernel.core import register,Stop
@register('demo_stamp')
def demo_stamp(s,m,mid,deps):
    if not s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':'LOCAL_STAMP:'+mid,'version':'local-stamp-1','evidence_kind':'SIMULATED_LOCAL','depends_on':deps}):raise Stop('A decision stands on this effect')
    return {'model_effect':m['effect'],'stamped':True}
"""
PACK_SRC="from kernel.core import ACTIONS\nassert 'demo_stamp' in ACTIONS   # the kinds are loaded before any pack file runs\npack('900_demo',scope='orgA/demo',goals=['stamped'],methods=[method('stamp@1','stamped',action='demo_stamp')],providers={'local-provider':2},grants=['action:stamp@1'])\n"
SCENE_SRC="""import json
from pathlib import Path
LOOKS = 2
RUNS = 2
def scene(lab):
    s=lab['State'].from_packs([json.loads(Path(%r).read_text())])
    first=lab['Kernel'](s).run_standing(execute=True)
    return {'first':first,'after_first':{'budget':dict(s.budget),'providers':dict(s.providers)},'again':lab['Kernel'](s).run_standing(execute=True)}
"""
CHECK_SRC="""import json
def checks(data, ROOT, sha, check_chain):
    run=data['scenes']['demo']['first']['runs'][0]
    data['cases'].clear()   # what a module does to its copy of the record stays with the module
    return [('S150_the_demo_step_was_stamped',run['model_receipts'][0]['action']=='demo_stamp' and check_chain(run['trace']) and len(sha(run))==64,''),
            ('S151_the_demo_pack_is_a_scenario_file',json.loads((ROOT/'scenarios'/'900_demo.json').read_text())['goals']==['stamped'],'')]
"""
CASE=dict(id='900_demo',title='A demo case',description='Case 04 again, from a file.',packs=ORDER,execute=True,area='Demo',expected='LOCAL_MODEL_EFFECTS_RECORDED')
IDLE=dict(id='901_idle',title='A demo case without a goal',description='Case 21 again, from a file.',packs=['00_goal','01_domain','11_no_goal'],execute=False,area='Demo',expected='NO_STANDING_GOAL')
HEAD='def checks(data, ROOT, sha, check_chain):\n'

def verifier(root=None):
    """The independent verifier, loaded from its file (it is a script, not a package); with `root`, looking at that copy of the lab."""
    spec=importlib.util.spec_from_file_location('independent_verify_for_the_points',ROOT/'qa'/'independent_verify.py')
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    if root:v.ROOT=Path(root)
    return v
def sha_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(text if type(text) is bytes else text.encode('utf-8'));return path
def failed(result):return sorted(t['id'] for t in result['checks'] if not t['pass'])
def scenario_shas(root):return {f.stem:sha_file(f) for f in sorted((Path(root)/'scenarios').glob('*.json'))}   # what a build of `root` would list under added.scenarios

class Points(unittest.TestCase):
    """The record, the verifier, and helpers that make temporary folders and a small lab of their own."""
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads(RECORD.read_text());cls.v=verifier()
    @classmethod
    def folder(cls,later=None):
        d=Path(tempfile.mkdtemp(prefix='points-'));(later or cls.addClassCleanup)(shutil.rmtree,d,True);return d
    def tmp(self):return self.folder(self.addCleanup)
    @classmethod
    def lab_copy(cls,extra,later=None):
        """A small lab of its own in a temporary folder, and its record: the base with the add-on points and ONE added version, `extra` (path -> text). Of this lab it
        holds what the verifier reads of the base (the kernel, the baseline, the scenario files, the built-in extensions, the points' own test file) and a book that
        lists `extra` as its only version; the record is this lab's record cut back to the built-in cases, with no sequence and no kind of any other version, and the
        book pins that record as it stands (the names this lab's book pins, the hashes of the copy's own record and files). So what these tests show does not depend
        on the versions this lab holds, nor on what an edit version of this lab declares as moved and the lab's own pins do not hold yet."""
        root=cls.folder(later);book=json.loads((ROOT/'added.json').read_text());data=json.loads(json.dumps(cls.data));sha=cls.v.sha
        keep=['kernel/core.py','release/baseline_v0_1_core.py']+[f.relative_to(ROOT).as_posix() for f in sorted((ROOT/'scenarios').glob('*.json'))]+[rel for rel in book['pinned']['built_in'] if rel.startswith('extensions/')]
        for rel in keep+list(book['points']['files']):write(root/rel,(ROOT/rel).read_bytes())
        for rel,text in extra.items():write(root/rel,text)
        data['cases']=data['cases'][:BUILT_IN_CASES];data.pop('scenes',None);data['action_handlers']={k:v for k,v in data['action_handlers'].items() if k in FOUR}
        book['applied']=[{'label':'0.0.0-test','delivery':'test','files':{rel:sha_file(root/rel) for rel in extra}}]
        book['pinned'].update(kernel_sha256=sha_file(root/'kernel'/'core.py'),scenarios={n:sha_file(root/'scenarios'/(n+'.json')) for n in book['pinned']['scenarios']},cases=[[c['id'],sha(c)] for c in data['cases']],
                              events=sha(data['events']),ask_events=sha(data['ask_events']),scenes={},kinds=[],action_handlers={k:sha(v) for k,v in data['action_handlers'].items()},
                              meta_extensions={k:sha(data['meta_extensions'][k]) for k in book['pinned']['meta_extensions']})   # as the applier pins a built record: before any kind of a later version was declared
        write(root/'added.json',json.dumps(book))
        data['added']={'files':dict(book['points']['files'],**book['applied'][0]['files']),'scenes':{},'scenarios':scenario_shas(root)};data['release']='sutra-kernel-extensions/0.0.0-test'
        return root,data


class PlacesTests(Points):
    """tools/make_packs.py and tools/run_all.py: how the places are read, and what an added pack file, kind, case and scene may do."""
    def test_a_place_is_read_by_its_name_pattern_in_name_order_and_anything_else_found_there_stops_the_build(self):
        d=self.tmp();good=['0_a.py','10_a.py','2_b.py','b.py','c_1.py','z9.py']
        for n in reversed(good):write(d/n,'')
        self.assertEqual(([f.name for f in mp.plug(d,'.py')],mp.plug(d/'absent','.py')),(good,[]))
        self.assertEqual(([f.name for f in self.v.plug(d,'.py')[0]],self.v.plug(d,'.py')[1],self.v.plug(d/'absent','.py')),(good,[],([],[])))
        (d/'__pycache__').mkdir();self.assertEqual((len(mp.plug(d,'.py')),self.v.plug(d,'.py')[1]),(6,[]))   # what Python itself leaves there is passed over
        for odd in ('.hidden.py','_under.py','Draft.py','notes.txt','b.py.bak','a-b.py','.60_draft.json','d.json'):
            write(d/odd,'')
            with self.assertRaises(ValueError,msg=odd):mp.plug(d,'.py')
            self.assertEqual(self.v.plug(d,'.py')[1],[odd]);(d/odd).unlink()
        for odd,make in (('deeper',lambda p:p.mkdir()),('x.py',lambda p:p.mkdir()),('link.py',lambda p:p.symlink_to(d/'b.py'))):   # a folder, a folder named like a file, a link
            make(d/odd)
            with self.assertRaises(ValueError,msg=odd):mp.plug(d,'.py')
            self.assertEqual(self.v.plug(d,'.py')[1],[odd])
            (d/odd).unlink() if (d/odd).is_symlink() else (d/odd).rmdir()
        self.assertEqual(([f.name for f in mp.plug(d,'.py')],mp.PLAIN,self.v.PLAIN,mp.PACK),(good,'[0-9a-z][0-9a-z_]*','[0-9a-z][0-9a-z_]*','[0-9a-z][0-9a-z_@.-]*'))
    def test_a_pack_file_is_handed_a_pack_that_only_creates(self):
        d=self.tmp();packs,out=d/'packs',d/'scenarios';out.mkdir()
        write(packs/'demo.py',"pack('900_demo',scope='orgA/demo',goals=['done'],evidence=[fact('ready','TRUE')],rules=[rule('R-DEMO@1','done',[['made']])],methods=[method('make@1','made',['ready'])],providers={'local-provider':1},grants=['action:make@1'])\n"
                              "pack('901_clock@6',goals=[],note=__name__)\n")
        authored=['00_goal'];mp.added_packs(packs,out,authored);made=json.loads((out/'900_demo.json').read_text())
        self.assertEqual((authored,sorted(f.name for f in out.iterdir()),json.loads((out/'901_clock@6.json').read_text())['note']),(['00_goal','900_demo','901_clock@6'],['900_demo.json','901_clock@6.json'],'tools.packs.demo'))
        self.assertEqual((made['schema'],made['id'],made['goals'],made['evidence'][0]['predicate'],made['rules'][0]['id'],made['methods'][0]['id']),('sutra-extension/2','900_demo',['done'],'ready','R-DEMO@1','make@1'))
        self.assertEqual((out/'900_demo.json').read_text(),json.dumps(made,indent=2,ensure_ascii=False)+'\n')   # the text make_packs writes for a built-in pack
        self.assertEqual(Kernel(State.from_packs([made])).run_standing(execute=True)['runs'][0]['actions'],['make@1'])   # fact, rule and method were handed: the kernel plans with what the file authored
        for src in ("pack('00_goal',goals=['x'])","pack('900_demo')","pack('../x')","pack('.h')","pack('Caps')","pack('')","pack(7)","pack('902_x',id='00_goal')","pack('902_x',schema='sutra-extension/9')"):
            write(packs/'zz.py',src+'\n')   # runs after demo.py: a name authored before it (built in, or by another pack file) and a name that is no plain file name
            with self.assertRaises(ValueError,msg=src):mp.added_packs(packs,out,['00_goal'])
            self.assertEqual(sorted(f.name for f in out.iterdir()),['900_demo.json','901_clock@6.json'],src)
        write(packs/'zz.py',"pack('04_admission',providers={'local-provider':5},grants=['action:ship-original@1','action:ship-replacement@1'],note='x')\n")   # the forgery of the review: a built-in pack authored again
        with self.assertRaises(ValueError):mp.added_packs(packs,out,list(mp.AUTHORED))
        self.assertFalse((out/'04_admission.json').exists())
        # a pack names its methods as a list of objects that each have a text id: the verifier reads every method of every scenario file by its id, so a pack out of that
        # shape, also one that no case loads, would end the whole verification; it is refused before its scenario file is written (round 3, refuter 1, finding 4)
        for src in ("pack('200_draft',methods=[{'effect':'x'}])","pack('201_draft',methods='later')","pack('202_x',methods=['make@1'])","pack('203_x',methods=[{'id':7,'effect':'x'}])",
                    "pack('204_x',methods=None)","pack('205_x',methods={'id':'a@1'})","pack('206_x',methods=[method('a@1','x'),[]])"):
            write(packs/'zz.py',src+'\n')
            with self.assertRaisesRegex(ValueError,r'REFUSED tools/packs: the pack 20\d_\w+ does not name its methods as a list of objects that each have a text id',msg=src):mp.added_packs(packs,out,['00_goal'])
            self.assertEqual(sorted(f.name for f in out.iterdir()),['900_demo.json','901_clock@6.json'],src)
        write(packs/'zz.py',"pack('207_none',goals=['x'])\npack('208_empty',methods=[])\n");mp.added_packs(packs,out,['00_goal'])   # a pack without methods, or with an empty list, names none
        self.assertTrue((out/'207_none.json').is_file() and (out/'208_empty.json').is_file())
        for n in ('207_none','208_empty'):(out/(n+'.json')).unlink()
        # in the lab itself: every scenario file was authored in this run, each name once; a file nobody authored would stop the build
        self.assertEqual((sorted(n+'.json' for n in mp.AUTHORED),len(set(mp.AUTHORED)),mp.unauthored(mp.P,mp.AUTHORED)),(sorted(f.name for f in mp.P.iterdir()),len(mp.AUTHORED),[]))
        self.assertTrue({'00_goal','04_admission','82_components_without_constructor'}<=set(mp.AUTHORED))
        write(out/'999_hand.json','{}');self.assertEqual(mp.unauthored(out,['900_demo','901_clock@6']),['999_hand.json'])
    def test_method_ids_are_one_namespace_across_the_lab(self):
        # The verifier keeps one table of methods over every scenario file. A pack may name a method id that another pack names only with the same method, field for
        # field; a pack that names it with other content is refused before its scenario file is written, so no honest build holds an id with two meanings.
        seed=self.tmp();write(seed/'02_methods.json',(mp.P/'02_methods.json').read_bytes());write(seed/'a.json',json.dumps({'schema':'sutra-extension/2','id':'a','methods':[mp.method('make@1','made',['ready'])]}))
        def author(src,authored=('02_methods','a')):
            d=self.tmp();write(d/'zz.py',src+'\n');mp.added_packs(d,seed,list(authored))
        author("pack('910_same',methods=[method('make@1','made',['ready'])],note='the same method under the same id')");self.assertTrue((seed/'910_same.json').is_file())
        author("pack('911_other_ids',methods=[method('make@2','made',['ready']),method('sell@1','sold')])");self.assertTrue((seed/'911_other_ids.json').is_file())
        with self.assertRaisesRegex(ValueError,'REFUSED tools/packs: the pack 200_shop names the method ship-original@1, which the pack 02_methods names with other content; a method id names one method in the whole lab'):
            author("pack('200_shop',scope='orgB/shop',goals=['parcel_sent'],methods=[method('ship-original@1','parcel_sent',cost={'compute':3,'money':3,'attention':0})])")   # the delivery of the review: an older id at another cost
        for what,src in (('another cost',"pack('920_x',methods=[method('make@1','made',['ready'],cost={'compute':3,'money':3,'attention':0})])"),('another effect',"pack('920_x',methods=[method('make@1','sold',['ready'])])"),
                         ('other prerequisites',"pack('920_x',methods=[method('make@1','made')])"),('another provider',"pack('920_x',methods=[method('make@1','made',['ready'],provider='owner-channel')])"),
                         ('another kind',"pack('920_x',methods=[method('make@1','made',['ready'],action='ask')])"),('a field more',"pack('920_x',methods=[method('make@1','made',['ready'],note='x')])"),
                         ('a method of a pack file before it',"pack('920_x',methods=[method('sell@1','sold',['ready'])])"),('two packs of one file',"pack('921_one',methods=[method('new@1','x')])\npack('920_x',methods=[method('new@1','y')])")):
            with self.assertRaisesRegex(ValueError,'names one method in the whole lab',msg=what):author(src,('02_methods','a','911_other_ids'))
            self.assertFalse((seed/'920_x.json').exists(),what)   # refused before its scenario file is written
        self.assertFalse((seed/'200_shop.json').exists())
        table={}   # in the lab itself: every method id of every scenario file names one method (packs 32 and 82 share four, the same four)
        for f in sorted(mp.P.glob('*.json')):
            for m in json.loads(f.read_text()).get('methods',[]):self.assertEqual(table.setdefault(m['id'],m),m,(f.name,m['id']))
        self.assertTrue(len(table)>=25 and json.loads((mp.P/'32_builder_components.json').read_text())['methods']==json.loads((mp.P/'82_components_without_constructor.json').read_text())['methods'])
    def test_make_packs_itself_loads_the_kinds_runs_the_pack_files_and_stops_on_what_nobody_authored(self):
        # tools/make_packs.py as the build runs it, in a copy that holds only what it needs: the kernel, the built-in extensions, one kind file and one pack file.
        book=json.loads((ROOT/'added.json').read_text());d=self.tmp()
        for rel in ['tools/make_packs.py','kernel/core.py']+[rel for rel in book['pinned']['built_in'] if rel.startswith('extensions/')]:write(d/rel,(ROOT/rel).read_bytes())
        write(d/'kinds'/'demo_stamp.py',KIND_SRC);write(d/'tools'/'packs'/'demo.py',PACK_SRC)
        def run():
            out=subprocess.run([sys.executable,'-I','-B',str(d/'tools'/'make_packs.py')],capture_output=True,text=True);return out.returncode,out.stdout+out.stderr
        code,out=run();made=sorted(f.name for f in (d/'scenarios').iterdir())
        self.assertEqual((code,'900_demo.json' in made,'04_admission.json' in made,'82_components_without_constructor.json' in made,len(made)>=43),(0,True,True,True,True),out)
        self.assertTrue(all((d/'scenarios'/n).read_bytes()==(ROOT/'scenarios'/n).read_bytes() for n in made if n!='900_demo.json'))   # the built-in packs, byte for byte as in the lab
        for what,rel,text,said in (('a scenario file made by hand','scenarios/999_hand.json','{}','REFUSED scenarios/'),('a pack file that authors a built-in pack again','tools/packs/zz.py',"pack('04_admission',providers={'local-provider':9})\n",'already authored'),
                                   ('a hidden pack file','tools/packs/.h.py',"pack('999_h',goals=['x'])\n",'not an add-on file'),('a hidden kind file','kinds/.k.py','','not an add-on file'),
                                   ('a kind file that registers nothing','kinds/idle.py','X=1\n','does not register the action kind idle'),
                                   ('a pack file that names an older method id at another cost','tools/packs/zz.py',"pack('200_shop',methods=[method('ship-original@1','parcel_sent',cost={'compute':3,'money':3,'attention':0})])\n",'which the pack 02_methods names with other content'),
                                   ('a kind file named like a built-in kind','kinds/ask.py',"from kernel.core import register\n@register('ask')\ndef run(s,m,mid,deps):return {}\n",'REFUSED kinds/ask.py: the action kind ask is registered already'),
                                   ('a kind file named like the kernel\'s own kind','kinds/simulate_fact.py','X=1\n','REFUSED kinds/simulate_fact.py: the action kind simulate_fact is registered already'),
                                   ('a kind file that registers two kinds','kinds/two.py',"from kernel.core import register\nregister('two')(print)\nregister('three')(print)\n","it registers or changes other action kinds than its own: ['three']"),
                                   ('a kind file that changes the handler of another kind','kinds/sly.py',"from kernel.core import register,ACTIONS\nACTIONS['ask']=dict(ACTIONS['ask'],run=print)\nregister('sly')(print)\n","it registers or changes other action kinds than its own: ['ask']"),
                                   ('a kind file whose handler is written in another file','kinds/borrowed.py',"from kernel.core import register\nimport json\nregister('borrowed')(json.dumps)\n","REFUSED kinds/borrowed.py: the handler it registers for borrowed is written in another file (it is a function of the module json)"),
                                   ('a pack whose methods are out of shape','tools/packs/zz.py',"pack('999_h',methods=[{'effect':'x'}])\n",'REFUSED tools/packs: the pack 999_h does not name its methods as a list of objects')):
            write(d/rel,text);code,out=run()
            self.assertEqual((code,said in out,(d/'scenarios'/'04_admission.json').read_bytes()==(ROOT/'scenarios'/'04_admission.json').read_bytes(),(d/'scenarios'/'999_h.json').exists(),(d/'scenarios'/'200_shop.json').exists()),(1,True,True,False,False),(what,out[-300:]))
            (d/rel).unlink()
        # tools/run_all.py as the build runs it: the record and the verdict of an earlier build go before the import that can refuse, so a build that stops there leaves neither behind
        write(d/'tools'/'run_all.py',(ROOT/'tools'/'run_all.py').read_bytes());write(d/'kinds'/'ask.py','X=1\n')
        stale=[write(d/'results'/'actual_run_records.json','{"stale":1}'),write(d/'qa'/'independent_verification.json','{"pass":true}')]
        ran=subprocess.run([sys.executable,'-I','-B',str(d/'tools'/'run_all.py')],capture_output=True,text=True)
        self.assertEqual((ran.returncode,'REFUSED kinds/ask.py' in ran.stderr,[p.exists() for p in stale]),(1,True,[False,False]),ran.stderr[-300:])
        (d/'kinds'/'ask.py').unlink()
        # a pack file that re-binds a handler: the registry is held as it stood before the pack files ran, so tools/run_all.py refuses, in words, before it records anything
        write(d/'tools'/'packs'/'zz.py',"from kernel.core import ACTIONS\nACTIONS['ask']=dict(ACTIONS['ask'],run=print)\n")
        ran=subprocess.run([sys.executable,'-I','-B',str(d/'tools'/'run_all.py')],capture_output=True,text=True)
        self.assertEqual((ran.returncode,"REFUSED: the handler or a hook of the action kind(s) ['ask'] is no longer the function that stood when the kinds were loaded" in ran.stderr,(d/'results'/'actual_run_records.json').exists()),(1,True,False),ran.stderr[-300:])
        (d/'tools'/'packs'/'zz.py').unlink()
        (d/'kinds'/'demo_stamp.py').unlink();code,out=run();self.assertEqual((code,'AssertionError' in out),(1,True))   # without its kind file the pack file's own line fails: the kinds come from kinds/, before the pack files
    def test_a_kind_file_registers_the_kind_it_is_named_after_and_no_kind_comes_from_anywhere_else(self):
        d=self.tmp();write(d/'demo_stamp.py',KIND_SRC)
        for name in ('demo_stamp','demo_other'):self.addCleanup(ACTIONS.pop,name,None)
        for name in ('kinds.demo_stamp','kinds.other_name'):self.addCleanup(sys.modules.pop,name,None)
        self.assertEqual(ra.undeclared(),[])
        ACTIONS['demo_elsewhere']=dict(ACTIONS['simulate_fact']);self.addCleanup(ACTIONS.pop,'demo_elsewhere',None)   # a kind registered by other code than a file of kinds/ (an extension, a pack file, a scene)
        self.assertEqual(ra.undeclared(),['demo_elsewhere'])
        with self.assertRaisesRegex(ValueError,'registered outside kinds/'):ra.record()   # the record is refused
        del ACTIONS['demo_elsewhere']
        # a handler or a hook re-bound after the kinds were loaded (by an extension, a pack file, a sequence): the registry is held to what stood then, and the record is refused
        self.assertEqual((mp.rebound(mp.HELD),sorted(mp.HELD),ra.HELD is mp.HELD,all(mp.HELD[k][h] is ACTIONS[k][h] for k in mp.HELD for h in mp.HELD[k])),([],sorted(FOUR+mp.KINDS),True,True))
        keep=ACTIONS['emit_artifact'];self.addCleanup(ACTIONS.__setitem__,'emit_artifact',keep)
        ACTIONS['emit_artifact']=dict(keep,run=lambda *a:keep['run'](*a))   # the extension of the review: a pass-through under the built-in kind's name
        self.assertEqual(mp.rebound(mp.HELD),['emit_artifact'])
        with self.assertRaisesRegex(ValueError,r"the handler or a hook of the action kind\(s\) \['emit_artifact'\] is no longer the function that stood when the kinds were loaded"):ra.record()
        ACTIONS['emit_artifact']=dict(keep,settle=lambda s,r,log:None);self.assertEqual(mp.rebound(mp.HELD),['emit_artifact'])   # a hook more
        keep['run'],real=print,keep['run'];ACTIONS['emit_artifact']=keep;self.assertEqual(mp.rebound(mp.HELD),['emit_artifact']);keep['run']=real   # the handler changed in place
        gone=ACTIONS.pop('ask');self.assertEqual(mp.rebound(mp.HELD),['ask']);ACTIONS['ask']=gone
        self.assertEqual(mp.rebound(mp.HELD),[])
        # the registry is looked at three times, and each look is the one that refuses its own case (the handler is put back here after each):
        said=r"REFUSED: the handler or a hook of the action kind\(s\) \['%s'\] is no longer the function that stood when the kinds were loaded"
        ACTIONS['emit_artifact']=dict(keep,run=print)   # (1) before anything is recorded: a handler that is no function of a lab file is refused in words, before the record's table of handlers is made
        with self.assertRaisesRegex(ValueError,said%'emit_artifact'):ra.record()
        ACTIONS['emit_artifact']=keep
        e=self.tmp();write(e/'puts_back.py',"LOOKS = 0\nRUNS = 0\ndef scene(lab):\n    from kernel.core import ACTIONS\n    from tools.make_packs import HELD\n    ACTIONS['emit_artifact']=dict(HELD['emit_artifact']);return {'n':1}\n")
        real=ra.extra_events
        def during():   # (2) before the sequences run: a handler re-bound while the cases and the event record were made, which a sequence would put back
            ACTIONS['emit_artifact']=dict(keep,run=lambda *a:keep['run'](*a));return real()
        ra.extra_events=during
        try:
            with self.assertRaisesRegex(ValueError,said%'emit_artifact'):ra.record(e)
        finally:ra.extra_events=real
        self.assertEqual(mp.rebound(mp.HELD),['emit_artifact']);ACTIONS['emit_artifact']=keep   # the sequence did not run
        e=self.tmp();write(e/'leaves.py',"LOOKS = 0\nRUNS = 0\ndef scene(lab):\n    from kernel.core import ACTIONS\n    ACTIONS['ask']=dict(ACTIONS['ask'],run=print);return {'n':1}\n")
        gone=ACTIONS['ask'];self.addCleanup(ACTIONS.__setitem__,'ask',gone)
        with self.assertRaisesRegex(ValueError,said%'ask'):ra.record(e)   # (3) after the sequences: one that re-binds a handler and leaves it so
        self.assertEqual(mp.rebound(mp.HELD),['ask']);ACTIONS['ask']=gone;self.assertEqual(mp.rebound(mp.HELD),[])
        for name,src,said in (('ask',KIND_SRC.replace('demo_stamp','ask'),'REFUSED kinds/ask.py: the action kind ask is registered already'),   # a kind file named like a built-in kind is not even loaded
                              ('sly',"from kernel.core import register,ACTIONS\nACTIONS['ask']=dict(ACTIONS['ask'],run=print)\n@register('sly')\ndef sly(s,m,mid,deps):return {}\n",r"it registers or changes other action kinds than its own: \['ask'\]"),
                              # round 3 (refuter 1, finding 6): a kind's handler is a function of its own file, where the record and S41 look for it; one written in another file
                              # (here a function of the kernel's own module) would pass the build and fail S41 after it, so the build stops at the kind file instead
                              ('borrowed',"from kernel.core import register,digest\nregister('borrowed')(digest)\n",r'REFUSED kinds/borrowed.py: the handler it registers for borrowed is written in another file \(it is a function of the module kernel.core\)')):
            e=self.tmp();write(e/(name+'.py'),src)
            with self.assertRaisesRegex(ValueError,said):mp.load_kinds(e)
            self.assertEqual((mp.rebound(mp.HELD),name in ('sly','borrowed') and name in ACTIONS,'kinds.'+name in sys.modules),([],False,False),name)   # what it did to the registry is taken back
        self.assertEqual((mp.load_kinds(d),'demo_stamp' in ACTIONS,sys.modules['kinds.demo_stamp'].__file__),(['demo_stamp'],True,str(d/'demo_stamp.py')))
        self.assertEqual(mp.load_kinds(d),['demo_stamp'])            # a second look loads nothing twice
        self.assertEqual(ra.undeclared(),['demo_stamp'])             # the kind is no file of the lab's kinds/: the record is refused
        kinds=ra.KINDS;ra.KINDS=kinds+['demo_stamp']
        try:self.assertEqual(ra.undeclared(),[])                     # declared, it is one of the lab's kinds
        finally:ra.KINDS=kinds
        e=self.tmp();write(e/'other_name.py',KIND_SRC.replace('demo_stamp','demo_other'))
        with self.assertRaises(ValueError):mp.load_kinds(e)          # a file that registers another kind than its name: the build stops and the kind is taken out again
        self.assertEqual(('kinds.other_name' in sys.modules,'demo_other' in ACTIONS),(False,False))
        e=self.tmp();write(e/'broken.py','raise RuntimeError("boom")\n')
        with self.assertRaises(RuntimeError):mp.load_kinds(e)
        self.assertNotIn('kinds.broken',sys.modules)
        self.assertEqual((mp.load_kinds(self.tmp()),mp.KINDS,ra.KINDS),([],[f.stem for f in mp.plug(ROOT/'kinds','.py')],mp.KINDS))
        self.assertEqual(sorted(ACTIONS),sorted(FOUR+mp.KINDS+['demo_stamp']))
    def test_an_added_case_is_one_file_named_after_its_id_and_is_run_as_its_file_says(self):
        d=self.tmp();case=lambda **k:json.dumps(dict(CASE,**k))
        write(d/'900_demo.json',case());write(d/'901_dry.json',case(id='901_dry',execute=False,expected='PLAN_READY'))
        got=ra.more(d,['00_goal']);self.assertEqual(([c['id'] for c in got],ra.spec(got[0])),(['900_demo','901_dry'],('900_demo',CASE['title'],CASE['description'],ORDER,True,'Demo')))
        for c in got:   # the same packs: executed when the file says so, and only then
            s=ra.scenario(ra.spec(c));self.assertEqual((s['id'],s['title'],s['description'],s['area'],s['packs'],s['outcome']['status'],bool(s['outcome']['model_receipts'])),(c['id'],c['title'],c['description'],c['area'],c['packs'],c['expected'],c['execute']))
        bad={'a file not named after its id':('902_x.json',case(id='902_y')),'an id that is taken':('00_goal.json',case(id='00_goal')),'a key missing':('903_x.json',json.dumps({k:v for k,v in dict(CASE,id='903_x').items() if k!='expected'})),
             'a key too many':('903_x.json',case(id='903_x',note='x')),'execute as text':('903_x.json',case(id='903_x',execute='yes')),'execute as a number':('903_x.json',case(id='903_x',execute=1)),
             'packs as text':('903_x.json',case(id='903_x',packs='00_goal')),'a pack that is a number':('903_x.json',case(id='903_x',packs=[7])),'a pack that is a path':('903_x.json',case(id='903_x',packs=['../cases/50_must_cohere'])),
             'a pack that is no scenario file':('903_x.json',case(id='903_x',packs=['999_absent'])),'no title':('903_x.json',case(id='903_x',title='')),'a description that is a number':('903_x.json',case(id='903_x',description=7)),
             'no area':('903_x.json',case(id='903_x',area='')),'expected as a list':('903_x.json',case(id='903_x',expected=['PLAN_READY'])),'not an object':('903_x.json','[]'),'a hidden draft':('.904_draft.json',case(id='904_draft')),
             'a note that is no case':('_notes.json','{"about":"x"}')}
        for what,(name,text) in bad.items():
            e=self.tmp();write(e/name,text)
            with self.assertRaises(ValueError,msg=what):ra.more(e,['00_goal'])
        e=self.tmp();write(e/'905_a.json',case(id='905_a'));self.assertEqual(len(ra.more(e,['00_goal'])),1)
        with self.assertRaises(ValueError):ra.more(e,['905_a'])   # an id that is taken
        e=self.tmp();write(e/'04_gates.json',case(id='04_gates'))
        with self.assertRaises(ValueError):ra.more(e)             # left to itself, more() takes the built-in ids as taken
        # in the lab itself: the added cases stand after the built-in ones in file order, in the shape of the built-in ones, and each has its expected status and its stage test
        import test_kernel
        self.assertEqual(([m['id'] for m in ra.MORE],ra.CASES[BUILT_IN_CASES:],len(ra.CASES)),([f.stem for f in mp.plug(ROOT/'cases','.json')],[ra.spec(m) for m in ra.MORE],BUILT_IN_CASES+len(ra.MORE)))
        for m in ra.MORE:self.assertEqual((test_kernel.EXPECTED[m['id']],callable(getattr(test_kernel.ContractTests,'test_stage_'+m['id'],None))),(m['expected'],True),m['id'])
        self.assertEqual(len(test_kernel.EXPECTED),len(ra.CASES))
    def test_a_scene_file_is_run_kept_as_plain_data_and_sealed_in_the_record(self):
        d=self.tmp();says='LOOKS = %d\nRUNS = %d\n';init=Kernel.__init__
        write(d/'demo.py',says%(1,1)+"def scene(lab):\n    s=lab['State'].from_packs([lab['pack'](n) for n in %r])\n    look=lab['Kernel'](s).run_standing(execute=True)\n"
                          "    return {'look':look,'after':{'budget':dict(s.budget)},'handed':sorted(lab),'pair':(1,2),'asks':lab['open_asks'](s),'digest':lab['digest']({'a':1}),'name':__name__}\n"%ORDER)
        write(d/'second.py',says%(0,0)+"def scene(lab):\n    lab.clear();return {'n':1}\n")   # what a scene does to what it was handed stays with it
        write(d/'third.py',says%(0,0)+"def scene(lab):return {'handed':sorted(lab)}\n")
        got=ra.scenes(d);run=got['demo']['look']['runs'][0];handed=['Kernel','Learner','State','answer','digest','open_asks','pack']
        self.assertEqual((list(got),got['second'],got['third'],run['status'],[x['method'] for x in run['model_receipts']],got['demo']['after']),(['demo','second','third'],{'n':1},{'handed':handed},'LOCAL_MODEL_EFFECTS_RECORDED',['ship-replacement@1'],{'budget':{'compute':8,'money':8,'attention':3}}))
        self.assertEqual((got['demo']['handed'],got['demo']['pair'],got['demo']['asks'],got['demo']['digest'],got['demo']['name']),(handed,[1,2],{},digest({'a':1}),'tools.scenes.demo'))
        self.assertEqual(got,json.loads(json.dumps(got)))   # plain JSON data: what will stand in the record
        for src in ("X=1","scene=7","def scene(lab):return [1]","def scene(lab):return {'x':{1}}","def scene(lab):return {'x':float('nan')}","def scene(lab):raise RuntimeError('boom')","def scene(lab):return {}"):
            e=self.tmp();write(e/'bad.py',says%(0,0)+src+'\n')
            with self.assertRaises((ValueError,TypeError,RuntimeError),msg=src):ra.scenes(e)
        # the file states how many looks and runs its sequence records, and the build holds the sequence to that: a file that states nothing, or other numbers, stops the build
        look="def scene(lab):\n    s=lab['State'].from_packs([lab['pack'](n) for n in %r]);k=lab['Kernel'](s)\n    return %%s\n"%ORDER
        for what,src,said in (('nothing stated',look%"{'look':k.run_standing()}",'it does not state how many looks and runs it records'),('one number stated','LOOKS = 1\n'+look%"{'look':k.run_standing()}",'it does not state how many looks and runs it records'),
                              ('a look more than stated',says%(1,1)+look%"{'look':k.run_standing(),'again':k.run_standing()}",'it says LOOKS = 1 and RUNS = 1; scene(lab) recorded 2 looks and 2 runs'),
                              ('a run less than stated',says%(1,2)+look%"{'look':k.run_standing()}",'it says LOOKS = 1 and RUNS = 2; scene(lab) recorded 1 looks and 1 runs'),
                              ('a run kept without its trace',says%(1,1)+look%"{'look':k.run_standing(),'short':{'runs':[{'status':'PLAN_READY'}]}}",'recorded 2 looks and 1 runs, and 1 of what looks like a run in it is no whole run'),
                              ('the stated numbers, beside something that looks like a run and is none',says%(1,1)+look%"{'look':k.run_standing(),'extra':{'trace':[]}}",'recorded 1 looks and 1 runs, and 1 of what looks like a run in it is no whole run'),
                              ('an empty sequence',says%(0,0)+"def scene(lab):return {}\n",'scene(lab) returns a dict, and not an empty one')):
            e=self.tmp();write(e/'bad.py',src)
            with self.assertRaisesRegex(ValueError,'REFUSED tools/scenes/bad.py: .*'+re.escape(said),msg=what):ra.scenes(e)
        # the State of a sequence runs its steps by the registered handlers: a State that holds a kind by another handler or hook, or a kind of its own, stops the build,
        # whoever made the Kernel that ran it (the scene through what it was handed, or code it imports); a State that holds fewer kinds, the same functions, is fine
        state="def scene(lab):\n    from kernel.core import State,Kernel,ACTIONS\n    s=%s.from_packs([lab['pack'](n) for n in "+repr(ORDER)+"])\n    %s\n    return {'look':%s(s).run_standing(execute=True)}\n"
        swap="old=s.actions['simulate_fact']['run'];s.actions['simulate_fact']=dict(s.actions['simulate_fact'],run=lambda *a:old(*a))"   # the scene of the review: other code under the built-in kind's name
        for what,src in (('another handler',state%("lab['State']",swap,"lab['Kernel']")),('another handler, the kernel imported',state%('State',swap,'Kernel')),('a hook more',state%("lab['State']","s.actions['simulate_fact']['settle']=lambda s,r,log:None","lab['Kernel']")),
                         ('a kind of its own',state%("lab['State']","s.actions['own']={'run':print}","lab['Kernel']"))):
            e=self.tmp();write(e/'bad.py',says%(1,1)+src)
            with self.assertRaisesRegex(ValueError,'REFUSED tools/scenes/bad.py: a State of this sequence holds the action kind',msg=what):ra.scenes(e)
            self.assertTrue(Kernel.__init__ is init,what)   # the kernel's own class is as it was, also after a scene that was refused
        e=self.tmp();write(e/'fewer.py',says%(1,1)+"def scene(lab):\n    from kernel.core import ACTIONS\n    s=lab['State'](actions={'simulate_fact':dict(ACTIONS['simulate_fact'])})\n    for n in %r:s.apply(lab['pack'](n))\n    return {'look':lab['Kernel'](s).run_standing(execute=True)}\n"%ORDER)
        self.assertEqual((ra.scenes(e)['fewer']['look']['runs'][0]['status'],Kernel.__init__ is init),('LOCAL_MODEL_EFFECTS_RECORDED',True))
        # every State a Kernel is made for is looked at: also the second State of a sequence, and one handed to Kernel by keyword (two lines of the look that no test held)
        two=says%(2,2)+"def scene(lab):\n    a,b=(lab['State'].from_packs([lab['pack'](n) for n in "+repr(ORDER)+"]) for _ in (1,2))\n    %s\n    return {'first':lab['Kernel'](a).run_standing(execute=True),'second':lab['Kernel'](%s).run_standing(execute=True)}\n"
        for what,src in (('the second State of a sequence',two%(swap.replace('s.actions','b.actions'),'b')),('a State handed to Kernel by keyword',two%(swap.replace('s.actions','b.actions'),'state=b'))):
            e=self.tmp();write(e/'bad.py',src)
            with self.assertRaisesRegex(ValueError,'REFUSED tools/scenes/bad.py: a State of this sequence holds the action kind',msg=what):ra.scenes(e)
        e=self.tmp();write(e/'good.py',two%('pass','state=b'));self.assertEqual(sorted(ra.scenes(e)['good']),['first','second'])   # the same sequence with nothing swapped is recorded
        # Limit 1 of the README, pinned (ruling R31): that look is a look for mistakes, not a fence. A scene written to get past it is recorded: here the State's registry
        # is kept in a subclass of dict, or the Kernel is pointed at the State after it was made, and the step of simulate_fact is run by a function of the scene that also
        # writes a row no method names (round 3, refuter 1, finding 3). The receipt says simulate_fact all the same; added code is reviewed code, and the README says so.
        head=says%(1,1)+"class D(dict):pass\ndef scene(lab):\n    s=lab['State'].from_packs([lab['pack'](n) for n in %r]);old=s.actions['simulate_fact']['run']\n    def mine(st,m,mid,deps):\n        st.observe({'predicate':'customer_notified','truth':'TRUE','verified':True,'source':'the scene','version':'1'});return old(st,m,mid,deps)\n    new=dict(s.actions,simulate_fact=dict(s.actions['simulate_fact'],run=mine))\n"%ORDER
        tail="    return {'look':k.run_standing(execute=True),'notified':s.fact('customer_notified')['truth']}\n"
        e=self.tmp();write(e/'subclass.py',head+"    s.actions=D(new);k=lab['Kernel'](s)\n"+tail);write(e/'swapped.py',head+"    k=lab['Kernel'](lab['State']());s.actions=new;k.s=s\n"+tail)
        past=ra.scenes(e)
        self.assertEqual([(n,past[n]['look']['runs'][0]['model_receipts'][0]['action'],past[n]['notified']) for n in ('subclass','swapped')],[('subclass','simulate_fact','TRUE'),('swapped','simulate_fact','TRUE')])
        self.assertTrue(Kernel.__init__ is init and mp.rebound(mp.HELD)==[])
        self.assertIn("a scene that points a Kernel at another State after it was made, keeps a State's registry in another kind of dict, or puts a handler back before it returns is recorded",(ROOT/'README.md').read_text())
        # the two functions that read a scene file's numbers and count a sequence are the verifier's, word for word: they say the same of every text and of every shape
        texts=('LOOKS = 2\nRUNS = 3\n','RUNS = 0\nLOOKS = 0\n','LOOKS = 2\n','LOOKS = 2\nRUNS = 2\nLOOKS = 3\n','LOOKS, RUNS = 2, 2\n','LOOKS = True\nRUNS = 1\n','LOOKS = -1\nRUNS = 1\n','LOOKS = 2.0\nRUNS = 1\n',"LOOKS = '2'\nRUNS = 1\n",
               'def f():\n    LOOKS = 2\n    RUNS = 2\n','LOOKS = RUNS = 2\n','LOOKS = 2\nRUNS = 2\ndef scene(lab):\n    global LOOKS\n    LOOKS = 9\n','def (:\n','')
        self.assertEqual([ra.scene_says(t) for t in texts],[(2,3),(0,0),None,None,None,None,None,None,None,None,None,(2,2),None,None])
        self.assertEqual([self.v.scene_says(t) for t in texts],[ra.scene_says(t) for t in texts])
        whole={'trace':[],'trace_root_sha256':'x'};count=lambda f,v:(f(v)['looks'],len(f(v)['runs']),f(v)['odd'])
        for v,want in (({},(0,0,0)),({'a':{'runs':[whole,whole]},'b':whole},(1,3,0)),({'a':{'runs':[]}},(1,0,0)),({'a':{'runs':[{'status':'x'}]}},(1,0,1)),({'a':{'runs':[[whole]]}},(1,1,1)),({'a':{'runs':['x',7]}},(1,0,2)),
                       ({'a':{'trace':[]}},(0,0,1)),({'a':{'trace_root_sha256':'x','work_state':'ready','model_receipts':[]}},(0,0,0)),({'a':[{'b':dict(whole,inner={'runs':[whole]})}]},(1,2,0)),({'runs':'x'},(0,0,0)),
                       ({'a':dict(whole,trace=[{'data':{'hidden':whole,'status':'x','work_state':'ready'}}])},(0,2,0)),([whole],(0,1,0))):
            self.assertEqual((count(ra.looks_and_runs,v),count(self.v.looks_and_runs,v)),(want,want),v)
        self.assertEqual(self.v.runs_under({'a':{'runs':[whole,{'trace':[]}]},'b':{'trace_root_sha256':'x'}}),[whole])   # a run is a dict with a trace AND a trace root: neither alone makes one
        # the record made with these scene files holds each sequence under its file's name and its seal beside it; made with none, it holds no scenes block
        made=json.loads(json.dumps(ra.record(d)));none=ra.record(self.tmp())
        self.assertTrue(made['scenes']==got and made['added']['scenes']=={name:digest(s) for name,s in got.items()} and list(made)[-2:]==['scenes','added'])
        self.assertEqual(('scenes' in none,none['added']['scenes'],list(none)[-1],list(none['added'])),(False,{},'added',['files','scenes','scenarios']))
    def test_the_record_on_disk_is_what_the_lab_makes_now(self):
        # The one test that runs the kernel again for the whole record: cases, events, the ask record, the recorded sequences. It is what catches a record re-made from end to end.
        made=json.loads(json.dumps(ra.record()));stored=self.data;book=json.loads((ROOT/'added.json').read_text())
        self.assertEqual(sorted(set(stored)-set(made)),['meta_extensions'])   # the lenses are added afterwards by tools/make_extra.py
        for key in made:self.assertTrue(stored[key]==made[key],key)
        listed={rel:h for entry in [book['points']]+book['applied'] for rel,h in entry['files'].items()}
        self.assertEqual((made['added']['files'],made['added']['scenes'],'scenes' in made),(listed,{n:digest(s) for n,s in made.get('scenes',{}).items()},bool(mp.plug(ROOT/'tools'/'scenes','.py'))))
        self.assertEqual({rel:sha_file(ROOT/rel) for rel in listed},listed)
        self.assertEqual((sorted(made['action_handlers']),made['added']['scenarios'],sorted(made['added']['scenarios'])),(sorted(FOUR+mp.KINDS),scenario_shas(ROOT),sorted(mp.AUTHORED)))   # every scenario file this build authored, by sha256
        self.assertEqual((self.v.kinds_why(made['action_handlers'],ROOT),made['release']),([],'sutra-kernel-extensions/'+book['applied'][-1]['label']))   # each kind in the file its handler lives in; the build of the last version in the book
    def test_a_build_that_fails_leaves_no_record_and_no_verdict_of_an_earlier_one(self):
        d=self.tmp();target,verdict=write(d/'record.json','{"stale":1}'),write(d/'verdict.json','{"pass":true}');honest=ra.scenes
        def broken(folder=None):raise TypeError('Object of type set is not JSON serializable')   # what a scene that returns a set ends in
        ra.scenes=broken
        try:
            with self.assertRaises(TypeError),contextlib.redirect_stdout(io.StringIO()):ra.build(target,verdict)
        finally:ra.scenes=honest
        self.assertEqual((target.exists(),verdict.exists()),(False,False))
        write(verdict,'{"pass":true}')
        with contextlib.redirect_stdout(io.StringIO()) as out:made=ra.build(target,verdict)
        self.assertTrue(json.loads(target.read_text())==json.loads(json.dumps(made)) and out.getvalue().startswith('WROTE') and not verdict.exists())
        self.assertEqual(target.read_text(),json.dumps(made,ensure_ascii=False,indent=2)+'\n')   # the text of the record file, byte for byte: indented by two, one line break at its end
        self.assertTrue(RECORD.is_file() and json.loads(RECORD.read_text())==self.data)   # the lab's own record was not touched
    def test_the_page_counts_what_the_test_runner_counts(self):
        # The page takes the count unittest gives, the count the runner step writes into the README: every stage test of a case, built in or added, and every test of a
        # later version's file as unittest loads it (round 3, refuter 1, finding 7: a test in a base class that two classes inherit is three tests; a helper named test_ is none).
        tree=ast.parse((ROOT/'tools'/'build_viewer.py').read_text());source=[ast.get_source_segment((ROOT/'tools'/'build_viewer.py').read_text(),n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='collected'][0]
        ns={'ROOT':ROOT};exec(source,ns)   # the function alone: the script itself reads the record and writes the page
        counted=subprocess.run([sys.executable,'-I','-B','-c',"import unittest;print(unittest.defaultTestLoader.discover('tests').countTestCases())"],cwd=ROOT,capture_output=True,text=True).stdout.split()
        self.assertEqual([str(ns['collected']())],counted[-1:])
        d=self.tmp();write(d/'tests'/'test_later.py',"import unittest\nclass Base(unittest.TestCase):\n    def test_reads_its_case(self):self.assertTrue(True)\nclass One(Base):pass\nclass Two(Base):pass\ndef test_helper():pass\n")
        ns['ROOT']=d;self.assertEqual(ns['collected'](),3)
    def test_the_names_these_tests_take_are_taken_in_every_lab(self):
        # Limit 15 of the README, pinned (round 4, refuter 1, finding 1; settled without new code). These tests make fixtures of their own beside the lab's packs and kinds:
        # VerifierTests authors its fixture pack into a copy that holds EVERY scenario file of the lab, and the fixture kinds are loaded into the registry the lab's own kinds
        # stand in. So some names are taken in every lab. A delivery that uses one passes the applier, the build and the verifier, and then these tests fail; this test says
        # which name it was. The applier does not refuse the names (owed to a later version: fixtures that meet no pack or kind of a version, or the names refused there).
        packs=('900_demo','200_shop','999_absent');kinds=('demo_stamp','demo_other','demo_elsewhere','other_name','sly','borrowed','broken');readme=(ROOT/'README.md').read_text()
        limit='limit 15 of the README: the unit tests of the points take this name in every lab, and a version that uses it fails them'
        fixture=json.loads(json.dumps(mp.method('stamp@1','stamped',action='demo_stamp')))   # the fixture's method, as a scenario file holds it
        self.assertTrue("pack('900_demo'" in PACK_SRC and "method('stamp@1','stamped',action='demo_stamp')" in PACK_SRC and "@register('demo_stamp')" in KIND_SRC)   # the fixtures carry these names
        used=(['the pack '+n for n in sorted(mp.AUTHORED) if n in packs or (re.match('0[01]_',n) and n not in ('00_goal','01_domain'))]   # every taken name this lab uses, in one list
              +['the method id stamp@1, with other content than the fixture\'s, in scenarios/'+f.name for f in sorted(mp.P.glob('*.json')) for m in json.loads(f.read_text()).get('methods',[]) if m.get('id')=='stamp@1' and m!=fixture]
              +['the kind '+f.stem for f in mp.plug(ROOT/'kinds','.py') if f.stem in kinds])
        self.assertEqual((used,{'00_goal','01_domain'}<=set(mp.AUTHORED)),([],True),limit)
        # what a lab that uses one of the three names of the review ends in: the lines of VerifierTests.setUpClass and of the test of S203, run here on small folders
        fixture_packs=self.tmp();write(fixture_packs/'demo.py',PACK_SRC.split('\n')[2]+'\n')   # the fixture's pack() line, without its look at the registry
        seed=self.tmp();write(seed/'310_post.json',json.dumps({'schema':'sutra-extension/2','id':'310_post','goals':['letter_stamped'],'methods':[mp.method('stamp@1','letter_stamped')]}))   # an honest pack of a version: a method of its own under the id stamp@1
        with self.assertRaisesRegex(ValueError,'REFUSED tools/packs: the pack 900_demo names the method stamp@1, which the pack 310_post names with other content'):mp.added_packs(fixture_packs,seed,['310_post'])
        with self.assertRaisesRegex(ValueError,'REFUSED tools/packs: the pack 900_demo is already authored; a pack file only creates'):mp.added_packs(fixture_packs,self.tmp(),['900_demo'])
        root,data=self.lab_copy({},self.addCleanup);at=verifier(root)   # a lab whose build authored a pack named 200_shop
        write(root/'scenarios'/'200_shop.json',json.dumps({'schema':'sutra-extension/2','id':'200_shop','goals':['x']}));data['added']['scenarios']=scenario_shas(root)
        self.assertEqual(at.files_why(data,root),[])
        write(root/'scenarios'/'200_shop.json','{}')   # the line of the test of S203 that writes its file made by hand: in this lab it changes a file the build authored
        self.assertEqual(at.files_why(data,root),['scenarios/200_shop.json is not the file this build authored'])   # and that test expects: is not a scenario file this build authored
        self.assertIn("and then fails those unit tests: the method id `stamp@1` (named with other content than the fixture's), the pack names `900_demo`, `200_shop` and `999_absent`, every pack name that begins with `00_` or `01_`, and the kind names `demo_stamp`, `demo_other`, `demo_elsewhere`, `other_name`, `sly`, `borrowed` and `broken`",readme)
        at=readme.index('(15) the unit tests of the points');stated=readme[at:readme.index('(16) a kind file that imports',at)]
        self.assertEqual([n for n in packs+kinds+('stamp@1','00_','01_') if '`'+n+'`' not in stated],[])   # limit 15 of the README names every name this test holds
    def test_added_code_can_write_files_and_change_the_kernels_classes_and_the_build_takes_it(self):
        # Limit 1 of the README, pinned (ruling R31; round 4, refuter 1, finding 8; settled without new code). The build runs a pack file and a scene with the lab's rights. It
        # looks at the registry and at the States a sequence runs, for mistakes. It does not look for a file that added code writes, for the scenario file of a pack authored
        # before it in the same build that a later pack file rewrites, or for a class of the kernel that added code changes: here a pack file does all three, a scene writes a
        # file and changes a class, and both are taken.
        d=self.tmp();packs,out,note=d/'packs',d/'scenarios',d/'written_by_a_pack_file.txt';out.mkdir()
        self.addCleanup(lambda:[delattr(State,n) for n in ('changed_by_a_pack_file','changed_by_a_scene') if hasattr(State,n)])
        write(packs/'a_first.py',"pack('930_first',goals=['as_authored'])\n")
        write(packs/'b_second.py',"import pathlib\nfrom kernel.core import State\npack('931_second',goals=['y'])\npathlib.Path(%r).write_text('x')\nfirst=pathlib.Path(%r)\nfirst.write_text(first.read_text().replace('as_authored','rewritten'))\nState.changed_by_a_pack_file=True\n"%(str(note),str(out/'930_first.json')))
        authored=[];mp.added_packs(packs,out,authored)
        self.assertEqual((authored,note.read_text(),json.loads((out/'930_first.json').read_text())['goals'],State.changed_by_a_pack_file),(['930_first','931_second'],'x',['rewritten'],True))
        e=self.tmp();seen=d/'written_by_a_scene.txt'
        write(e/'writes.py',"import pathlib\nLOOKS = 0\nRUNS = 0\ndef scene(lab):\n    pathlib.Path(%r).write_text('x');lab['State'].changed_by_a_scene=True;return {'n':1}\n"%str(seen))
        self.assertEqual((ra.scenes(e),seen.read_text(),State.changed_by_a_scene),({'writes':{'n':1}},'x',True))
        self.assertIn("added code can also write files, rewrite the scenario file of a pack authored before it in the same build and change the kernel's classes while it runs, and the points do not look for it",(ROOT/'README.md').read_text())
    def test_a_kind_file_that_imports_another_kind_file_is_refused_or_taken_by_the_order_of_the_two_names(self):
        # Limit 16 of the README, pinned (round 4, refuter 1, finding 6; settled without new code): a kind file imports no other kind file. Loading the importer runs the other
        # file, whose kind then counts as a second kind of the importer: the build stops, in words that name the second kind and not the import. With the names the other way
        # round the helper's file is loaded first, the import finds it loaded, and both kinds are taken. tools/make_packs.py as the build runs it, in a copy that holds what it needs.
        book=json.loads((ROOT/'added.json').read_text());d=self.tmp()
        for rel in ['tools/make_packs.py','kernel/core.py']+[rel for rel in book['pinned']['built_in'] if rel.startswith('extensions/')]:write(d/rel,(ROOT/rel).read_bytes())
        helper="from kernel.core import register\ndef helper(s,m,mid,deps):return {'model_effect':m['effect']}\n@register(%r)\ndef run(s,m,mid,deps):return helper(s,m,mid,deps)\n"
        user="from kernel.core import register\nfrom kinds.%s import helper\n@register(%r)\ndef run(s,m,mid,deps):return helper(s,m,mid,deps)\n"
        def run(files):
            for name,text in files.items():write(d/'kinds'/name,text)
            out=subprocess.run([sys.executable,'-I','-B',str(d/'tools'/'make_packs.py')],capture_output=True,text=True)
            for name in files:(d/'kinds'/name).unlink()
            return out.returncode,out.stdout+out.stderr
        code,out=run({'a_first.py':user%('b_second','a_first'),'b_second.py':helper%'b_second'})   # the importer's name sorts first
        self.assertEqual((code,"REFUSED kinds/a_first.py: it registers or changes other action kinds than its own: ['b_second']" in out,'import' in out.split('REFUSED')[-1]),(1,True,False),out[-400:])
        code,out=run({'a_helper.py':helper%'a_helper','b_user.py':user%('a_helper','b_user')})   # the helper's name sorts first
        self.assertEqual((code,'REFUSED' in out),(0,False),out[-400:])
        self.assertIn('a kind file that imports from another kind file is refused or taken by the order of the two file names',(ROOT/'README.md').read_text())
    def test_two_lines_of_the_base_say_other_than_the_lab_does_and_the_points_leave_them(self):
        # Limit 17 of the README, pinned (round 4: refuter 1, finding 7; refuter 2, finding 6; settled without new code). Two lines the lab had before the points, which the points
        # do not edit: the README asks for Python 3.10 or later, while the lab also runs on Python 3.9 and its own tests carry lines for it; and the verifier's comment lists the
        # release label among what it does not check, while S203 holds it (the test of S203 shows a forged label fail). An edit version can correct both lines; its script then
        # takes limit 17 and this test out as well.
        readme=(ROOT/'README.md').read_text();text=(ROOT/'qa'/'independent_verify.py').read_text()
        self.assertIn('\nRequirements: Python 3.10+ standard library.',readme)
        self.assertTrue(sys.version_info>=(3,9) and 'sys.version_info<(3,10)' in (ROOT/'tests'/'test_kernel.py').read_text())   # these tests run on 3.9 too, and the lab's own tests carry lines for it
        self.assertIn('among them that no step needs; the release label; and an event block',text)   # the base's comment on what the verifier does NOT check
        self.assertIn("data.get('release')!='sutra-kernel-extensions/'+book['applied'][-1]['label']",text)   # the line of S203 that holds the release label
        self.assertIn('this README asks for Python 3.10 or later, while the lab also runs on Python 3.9 and its own tests carry lines for it (`tests/test_kernel.py`); and the verifier\'s comment lists the release label among what it does not check, while S203 holds it from 0.10.0 on',readme)


class VerifierTests(Points):
    """qa/independent_verify.py: the five checks of the points and the delivered check modules, on a small lab that holds one added file of every kind."""
    EXTRA=('kinds/demo_stamp.py','tools/packs/demo.py','tools/scenes/demo.py','qa/checks/demo.py','cases/900_demo.json','cases/901_idle.json')
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        extra={'kinds/demo_stamp.py':KIND_SRC,'tools/packs/demo.py':PACK_SRC,'tools/scenes/demo.py':'','qa/checks/demo.py':CHECK_SRC,'cases/900_demo.json':json.dumps(CASE),'cases/901_idle.json':json.dumps(IDLE)}
        cls.root,cls.demo=cls.lab_copy(extra);root=cls.root
        write(root/'tools'/'scenes'/'demo.py',SCENE_SRC%str(root/'scenarios'/'900_demo.json'));book=json.loads((root/'added.json').read_text())   # the scene reads the pack from the copy's scenario files
        book['applied'][-1]['files']['tools/scenes/demo.py']=cls.demo['added']['files']['tools/scenes/demo.py']=sha_file(root/'tools'/'scenes'/'demo.py');write(root/'added.json',json.dumps(book))
        cls.addClassCleanup(ACTIONS.pop,'demo_stamp',None);cls.addClassCleanup(sys.modules.pop,'kinds.demo_stamp',None)
        cls.only=only=cls.folder();write(only/'kinds'/'demo_stamp.py',KIND_SRC);write(only/'packs'/'demo.py',PACK_SRC);write(only/'scenes'/'demo.py',(root/'tools'/'scenes'/'demo.py').read_text())
        mp.load_kinds(only/'kinds');mp.added_packs(only/'packs',root/'scenarios',list(mp.AUTHORED))   # the kind registered, the pack authored into the copy, the scene run: as a build does it
        mp.HELD['demo_stamp']=dict(ACTIONS['demo_stamp']);cls.addClassCleanup(mp.HELD.pop,'demo_stamp',None)   # a build takes the registry after the kinds are loaded: the demo kind is held like the others
        made=ra.scenes(only/'scenes')['demo'];d=cls.demo
        d['scenes']={'demo':made};d['added']['scenes']['demo']=digest(made);d['added']['scenarios']=scenario_shas(root)
        d['action_handlers']['demo_stamp']={'module':'kinds.demo_stamp','file':'kinds/demo_stamp.py','sha256':sha_file(root/'kinds'/'demo_stamp.py')}
        d['cases']+=[json.loads(json.dumps(ra.scenario(ra.spec(c)))) for c in (CASE,IDLE)]
        cls.at=verifier(root)
    def forged(self,change):
        d=self.copy(self.demo);change(d);return d
    def copy(self,data):return json.loads(json.dumps(data))
    def test_whole_1_the_lab_as_built_passes_and_the_checks_that_ran_are_the_built_in_ones_the_five_of_the_points_and_the_delivered_ones(self):
        res=self.v.inspect(self.copy(self.data));rows=res['checks'];n=len(BUILT_IN_IDS)+len(POINT_IDS);mine=['qa/checks/'+f.name for f in self.v.plug(ROOT/'qa'/'checks','.py')[0]]
        self.assertEqual((failed(res),res['pass'],res['passed'],res['total']),([],True,len(rows),len(rows)))
        self.assertEqual([t['id'] for t in rows[:n]],BUILT_IN_IDS+POINT_IDS)
        self.assertEqual((sorted({t.get('from') for t in rows[n:]}),all('from' not in t for t in rows[:n])),(mine,True))   # every delivered module gave rows, and every other row is a delivered module's
        self.assertTrue(all(self.v.number(t['id'])>=60 and self.v.number(t['id']) not in self.v.RESERVED for t in rows[n:]) and len({self.v.number(t['id']) for t in rows[n:]})==len(rows)-n)
    def test_whole_2_a_lab_with_added_cases_a_pack_a_kind_a_scene_and_a_check_module_passes_and_names_them(self):
        before=self.copy(self.demo);res=self.at.inspect(self.demo);rows=res['checks'];n=len(BUILT_IN_IDS)+len(POINT_IDS)
        self.assertEqual((failed(res),[t['id'] for t in rows[:n]]),([],BUILT_IN_IDS+POINT_IDS))
        self.assertEqual([(t['id'],t['pass'],t['detail'],t['from']) for t in rows[n:]],[('S150_the_demo_step_was_stamped',True,'','qa/checks/demo.py'),('S151_the_demo_pack_is_a_scenario_file',True,'','qa/checks/demo.py')])
        self.assertTrue(self.demo==before)   # the module emptied its copy of the cases; the record itself is as it was
        first=self.demo['scenes']['demo']['first']['runs'][0];self.assertEqual((first['status'],[x['action'] for x in first['model_receipts']],self.demo['scenes']['demo']['after_first']),('LOCAL_MODEL_EFFECTS_RECORDED',['demo_stamp'],{'budget':{'compute':9,'money':9,'attention':3},'providers':{'local-provider':1}}))
        self.assertEqual([(c['id'],(c['outcome'] or c['run'])['status']) for c in self.demo['cases'][BUILT_IN_CASES:]],[('900_demo','LOCAL_MODEL_EFFECTS_RECORDED'),('901_idle','NO_STANDING_GOAL')])   # a case without a standing goal has no chain to count
    def test_whole_3_every_check_of_the_points_and_every_way_a_module_can_fail_shows_as_its_own_row(self):
        mods={'qa/checks/a_fails.py':HEAD+"    return [('S160_a_check_that_fails',False,'as it says')]\n",                                       # a delivered check that fails: one failed row of its own
              'qa/checks/b_same.py':HEAD+"    return [('S160_the_same_number',True,'')]\n",                                                      # a number another module took
              'qa/checks/boom.py':HEAD+"    raise RuntimeError('boom')\n",'qa/checks/c_built_in.py':HEAD+"    return [('S01_source_hash_current',True,'')]\n"}   # one that raises; one that repeats a built-in id
        root,data=self.lab_copy(dict({rel:(self.root/rel).read_bytes() for rel in self.EXTRA},**mods),self.addCleanup)   # every module listed in added.json, so every one is run
        write(root/'scenarios'/'900_demo.json',(self.root/'scenarios'/'900_demo.json').read_bytes());d=self.copy(self.demo);d['added']['files']=data['added']['files'];d['added']['scenarios']=scenario_shas(root)
        d['cases'][-1]['id']='900_demo'                                                                                                     # S03 and S200: the second added case under the id of the first (the count is right, the ids are not distinct)
        again=d['scenes']['demo']['again']['runs'][0];again['status']='LOCAL_MODEL_EFFECTS_RECORDED';d['added']['scenes']['demo']=digest(d['scenes']['demo'])   # S201: a run changed in place and the sequence sealed again: only the run's own check can tell
        d['cases'][3]['description']='Other words.'                                                                                        # S202: an older case moved (in a field no built-in check reads)
        del d['action_handlers']['demo_stamp']                                                                                             # S204 (and S41): the step of the sequence names a kind the record holds no handler for
        write(root/'qa'/'checks'/'.draft.py','X=1\n')                                                                                      # a draft: S203, and a failed row of its own
        write(root/'qa'/'checks'/'demo.py',CHECK_SRC+'# changed after it was listed\n')                                                    # a module that is not the text added.json lists: S203, and it is not run
        res=verifier(root).inspect(d);rows={t['id']:t for t in res['checks']};mine=[t['id'] for t in res['checks'] if 'from' in t]
        self.assertEqual(failed(res),sorted(['S03_distinct_cases','S41_action_handlers_recorded_by_sha',S200,S201,S202,S203,S204,'S160_a_check_that_fails','qa/checks/.draft.py','qa/checks/b_same.py','qa/checks/boom.py','qa/checks/c_built_in.py','qa/checks/demo.py']))
        self.assertEqual((rows[S200]['detail'],rows[S201]['detail'],rows[S202]['detail'],rows[S204]['detail']),("after the built-in cases the record holds ['900_demo', '900_demo'] and the case files are ['900_demo', '901_idle']",
                         'demo: run 2 does not agree with its trace and its packs','case 03_evidence is not the pinned case','a receipt in scenes names the action kind demo_stamp, which the record holds no handler for'))
        self.assertEqual([(i,rows[i]['detail'],rows[i]['from']) for i in mine],[('qa/checks/.draft.py','not a check module: an add-on file is named [0-9a-z][0-9a-z_]*.py','qa/checks/.draft.py'),('S160_a_check_that_fails','as it says','qa/checks/a_fails.py'),
                         ('qa/checks/b_same.py','it returned S160_the_same_number, whose number is reserved or already taken','qa/checks/b_same.py'),('qa/checks/boom.py','it raised RuntimeError','qa/checks/boom.py'),
                         ('qa/checks/c_built_in.py','it returned S01_source_hash_current, whose number is reserved or already taken','qa/checks/c_built_in.py'),
                         ('qa/checks/demo.py','its text is not the text added.json lists for qa/checks/demo.py (by sha256); it was not run','qa/checks/demo.py')])
        self.assertEqual((res['pass'],[t['id'] for t in res['checks']].count('S01_source_hash_current'),rows['S42_every_run_agrees_with_its_trace_and_packs']['pass'],rows['S01_source_hash_current']['pass'],res['total']-res['passed']),(False,1,True,True,13))
        self.assertTrue(rows['S41_action_handlers_recorded_by_sha']['detail'].startswith("the record holds handlers for ['ask', 'compile_candidate', 'emit_artifact', 'simulate_fact'] and the kinds are ['ask', 'compile_candidate', 'demo_stamp',"))
    def test_whole_4_a_kind_that_is_not_declared_and_a_sequence_on_a_pack_that_is_no_scenario_file_fail(self):
        root,data=self.lab_copy({rel:(self.root/rel).read_bytes() for rel in self.EXTRA if rel!='kinds/demo_stamp.py'},self.addCleanup)
        d=self.copy(self.demo);d['added']['files']=data['added']['files'];d['added']['scenarios']=scenario_shas(root)   # the copy holds no kinds/demo_stamp.py and no scenarios/900_demo.json; the record still holds the handler and the sequence
        d['cases'].append(dict(d['cases'][-2]))                             # and the first added case twice: one case and one chain more than there are files (the ids are as many as before), so S03 and S05 count exactly and S200 names it
        res=verifier(root).inspect(d);rows={t['id']:t for t in res['checks']}
        self.assertEqual(failed(res),sorted(['S03_distinct_cases','S05_all_run_chains','S41_action_handlers_recorded_by_sha',S200,S201,S204,'qa/checks/demo.py']))
        self.assertEqual(rows[S201]['detail'],'demo: run 1 does not agree with its trace and its packs; demo: run 2 does not agree with its trace and its packs')   # limit 5 of the README: a sequence may only load packs that are scenario files
        self.assertEqual(rows[S204]['detail'],'a receipt in scenes is for the step stamp@1, which is no method of the packs its run loaded (as the scenario files hold them)')   # and the kind of its step cannot be read either
    def test_added_cases_are_held_to_their_files_column_by_column(self):
        why=lambda d:self.at.added_cases_why(d,self.root,BUILT_IN_CASES);demo=lambda d:d['cases'][-2]
        self.assertEqual(why(self.demo),[])
        changes=[('the id',lambda d:demo(d).update(id='900_other')),('the packs',lambda d:demo(d).update(packs=ORDER[:4])),('the title',lambda d:demo(d).update(title='Another title')),
                 ('the description',lambda d:demo(d).update(description='Other words.')),('the area',lambda d:demo(d).update(area='Other')),
                 ('the status',lambda d:demo(d)['outcome'].update(status='PLAN_READY')),('a case taken out',lambda d:d['cases'].pop()),('a copy put in',lambda d:d['cases'].append(dict(demo(d),id='902_copy'))),
                 ('a built-in case put in its place',lambda d:demo(d).update(id='04_gates')),('no outcome and no run',lambda d:demo(d).update(outcome=None,run=None)),
                 ('a built-in case taken out',lambda d:d['cases'].pop(0)),('the two cases in the other order',lambda d:d['cases'].append(d['cases'].pop(-2))),('the cases put before the built-in ones',lambda d:d.update(cases=d['cases'][-2:]+d['cases'][:-2]))]
        for what,change in changes:self.assertNotEqual(why(self.forged(change)),[],what)
        for cid,column,change in (('900_demo','packs',lambda d:demo(d).update(packs=ORDER[:4])),('900_demo','title',lambda d:demo(d).update(title='Another title')),('900_demo','description',lambda d:demo(d).update(description='Other words.')),
                                  ('900_demo','area',lambda d:demo(d).update(area='Other')),('900_demo','status',lambda d:demo(d)['outcome'].update(status='PLAN_READY')),('901_idle','status',lambda d:d['cases'][-1]['run'].update(status='EVALUATED'))):
            self.assertEqual(why(self.forged(change)),[cid+': the record has another '+column])
        case=lambda **k:json.dumps(dict(CASE,id='902_x',**k))
        for name,text in (('.902_draft.json',json.dumps(dict(CASE,id='902_draft'))),('zz.json',case()),('902_x.json','{"about":"x"}'),('902_x.json','not json'),('902_x.json','[]'),('902_x.json',case(execute='yes')),('902_x.json',case(execute=1)),
                          ('902_x.json',case(packs='00_goal')),('902_x.json',case(packs=[7])),('902_x.json',case(packs=[''])),('902_x.json',case(title='')),('902_x.json',case(description=7)),('902_x.json',case(area=[])),
                          ('902_x.json',case(expected='')),('902_x.json',case(note='a key too many')),('902_x.json',json.dumps({k:v for k,v in dict(CASE,id='902_x').items() if k!='area'}))):
            write(self.root/'cases'/name,text)
            try:self.assertIn('cases/'+name+' is no case file',why(self.demo),(name,text))
            finally:(self.root/'cases'/name).unlink()
        self.assertEqual((why(self.demo),self.at.case_of('902_x',case()),self.at.case_of('902_y',case())),([],dict(CASE,id='902_x'),None))
        # round 3 (refuter 1, finding 1, blocking): each added case is found by its id. A later version's case whose id sorts first (100_ before 900_) stands before the
        # earlier ones in file order, which is the order the build runs them in, and the record holds; the same case at another place than its file order is named
        write(self.root/'cases'/'100_later.json',json.dumps(dict(CASE,id='100_later')));at=lambda n:(lambda d:d['cases'].insert(n,dict(self.copy(demo(d)),id='100_later')))
        try:
            self.assertEqual((why(self.forged(at(BUILT_IN_CASES))),why(self.forged(at(BUILT_IN_CASES+1)))),([],["after the built-in cases the record holds the added cases as ['900_demo', '100_later', '901_idle']; in file order they are ['100_later', '900_demo', '901_idle']"]))
            self.assertEqual(why(self.demo),["after the built-in cases the record holds ['900_demo', '901_idle'] and the case files are ['100_later', '900_demo', '901_idle']"])   # a case file whose case is not in the record
        finally:(self.root/'cases'/'100_later.json').unlink()
    def test_recorded_sequences_are_held_to_their_files_their_seals_their_numbers_and_their_runs(self):
        seen=[];why=lambda d,run_ok=lambda r:True:self.at.scenes_why(d,self.root,run_ok);S=lambda d:d['scenes']['demo'];run=lambda d:S(d)['first']['runs'][0];file=self.root/'tools'/'scenes'/'demo.py'
        def ok(r):seen.append(r['trace_root_sha256']);return True
        mine=[r['trace_root_sha256'] for key in ('first','again') for r in self.demo['scenes']['demo'][key]['runs']]
        self.assertEqual((why(self.demo,ok),seen,len(set(mine)),self.at.scene_says(file.read_text())),([],mine,2,(2,2)))   # every run of the sequence went to the run check, in order; the scene file states two looks and two runs
        def raising(r):raise KeyError('x')
        self.assertEqual((why(self.demo,lambda r:r['trace_root_sha256']!=mine[1]),len(why(self.demo,raising))),(['demo: run 2 does not agree with its trace and its packs'],2))   # a run that fails its check, and one the check cannot read
        sealed=lambda d:d['added']['scenes'].update(demo=digest(S(d)));forged=lambda d:dict(self.copy(run(d)),status='PLAN_READY',trace_root_sha256='forged')
        numbers=lambda looks,runs:'demo: its scene file says LOOKS = 2 and RUNS = 2; the record holds %d looks and %d runs'%(looks,runs)
        odd='demo: 1 of what looks like a run is no whole run (an item of a `runs` list, or a dict with a `trace`, without both `trace` and `trace_root_sha256`)'
        # a rewritten run hidden in the sequence, sealed again: it is found by its shape wherever it sits, goes to the run check, and is one run more than the scene file states
        for what,hide,looks in (('beside the honest list',lambda d:S(d)['first'].update(later={'runs':[forged(d)]}),3),('under any key',lambda d:S(d).update(last_run=forged(d)),2),('in a list of lists',lambda d:S(d).update(more=[[forged(d)]]),2),
                                ('inside another run',lambda d:run(d).update(extra={'inner':[forged(d)]}),2),('inside a row of a trace',lambda d:run(d)['trace'][0]['data'].update(hidden=forged(d)),2)):
            seen.clear();self.assertEqual((why(self.forged(lambda d:(hide(d),sealed(d))),ok),seen.count('forged')),([numbers(looks,3)],1),what)
        # the forgeries of the review and their kin, each with the seal made again (the seal is a checksum in the same record): what is taken out of a sequence, or stripped of what
        # makes it a run, shows against the numbers the scene file states, and what still looks like a run must be a whole one
        def strip(d):
            r=run(d);r['rows']=r.pop('trace');r.update(status='PLAN_READY');r['model_receipts'][0]['action']='send_email'
        for what,change,said in (('a run without its trace, re-told',strip,[numbers(2,1),odd]),('a run without its trace root',lambda d:run(d).pop('trace_root_sha256'),[numbers(2,1),odd]),
                                 ('a stripped run moved out of its list',lambda d:(strip(d),S(d).update(spare=S(d)['first']['runs'].pop())),[numbers(2,1)]),
                                 ('the run of a look taken out',lambda d:S(d)['again'].update(runs=[]),[numbers(2,1)]),('a look taken out',lambda d:S(d).pop('again'),[numbers(1,1)]),
                                 ('a look and its snapshot taken out',lambda d:(S(d).pop('first'),S(d).pop('after_first')),[numbers(1,1)]),('runs renamed',lambda d:S(d)['first'].update(results=S(d)['first'].pop('runs')),[numbers(1,2)]),
                                 ('a look more',lambda d:S(d).update(third=dict(S(d)['again'])),[numbers(3,3)]),('something in a list of runs that is no run',lambda d:S(d)['again']['runs'].append('x'),[odd]),
                                 ('the sequence emptied',lambda d:S(d).clear(),['demo: the sequence holds nothing, or is no object']),('the sequence as a list',lambda d:d['scenes'].update(demo=[S(d)]),['demo: the sequence holds nothing, or is no object'])):
            self.assertEqual(why(self.forged(lambda d:(change(d),sealed(d)))),said,what)
        # without the seal made again the seal says so; the names of the sequences, of the seals and of the scene files are one list
        for what,change in (('the scenes block taken out',lambda d:d.pop('scenes')),('the sequence taken out',lambda d:d['scenes'].pop('demo')),('the sequence renamed',lambda d:d['scenes'].update(other=d['scenes'].pop('demo'))),
                            ('a sequence invented',lambda d:d['scenes'].update(second=S(d))),('a snapshot changed',lambda d:S(d)['after_first']['budget'].update(compute=10)),
                            ('a run swapped for another case',lambda d:S(d)['first'].update(runs=[d['cases'][3]['outcome']])),('a run changed in place',lambda d:run(d).update(status='PLAN_READY')),
                            ('the seal changed',lambda d:d['added']['scenes'].update(demo='0'*64)),('the seal taken out',lambda d:d['added']['scenes'].pop('demo')),('a seal too many',lambda d:d['added']['scenes'].update(other='0'*64)),
                            ('scenes as a list',lambda d:d.update(scenes=[S(d)])),('no seals',lambda d:d['added'].pop('scenes'))):
            self.assertNotEqual(why(self.forged(change)),[],what)
        self.assertEqual(why(self.forged(lambda d:S(d)['first'].update(runs=[]))),['demo: the sequence is not the one that was sealed',numbers(2,1)])
        # the scene file is what states the numbers, outside the record: on the honest record a file that states none, or others, fails the check
        keep=file.read_bytes()
        try:
            for text,said in ((keep.replace(b'LOOKS = 2\n',b''),['demo: its scene file does not state LOOKS and RUNS']),(keep.replace(b'RUNS = 2',b'RUNS = 3'),['demo: its scene file says LOOKS = 2 and RUNS = 3; the record holds 2 looks and 2 runs'])):
                write(file,text);self.assertEqual(why(self.demo),said)
        finally:write(file,keep)
        for name in ('.draft.py','_helper.py','notes.txt'):
            write(self.root/'tools'/'scenes'/name,'')
            try:self.assertIn('tools/scenes/'+name+' is no scene file',why(self.demo),name)
            finally:(self.root/'tools'/'scenes'/name).unlink()
        write(self.root/'tools'/'scenes'/'unrecorded.py','LOOKS = 0\nRUNS = 0\ndef scene(lab):return {}\n')   # a scene file whose sequence is not in the record: a record of before
        try:self.assertNotEqual(why(self.demo),[])
        finally:(self.root/'tools'/'scenes'/'unrecorded.py').unlink()
        file.unlink()   # no scene file: a scenes block is one too many, and no block at all is right
        try:self.assertEqual((why(self.demo)!=[],why(self.forged(lambda d:(d['scenes'].clear(),d['added']['scenes'].clear())))!=[],why(self.forged(lambda d:(d.pop('scenes'),d['added']['scenes'].clear())))),(True,True,[]))
        finally:write(file,keep)
        # Limits 2 and 3 of the README, pinned: a sequence re-made with as many looks and runs passes this check, the seal made again (the seal holds no secret; which run stands
        # where, and a snapshot, are not recomputed). Here a snapshot is changed and the second look is said to have run the first look's step again. The unit test that makes the
        # record again is what catches it.
        remade=self.forged(lambda d:(S(d)['after_first']['budget'].update(compute=10),S(d)['again'].update(runs=[dict(run(d))]),sealed(d)))
        again=ra.scenes(self.only/'scenes')['demo'];self.assertEqual((why(remade),remade['scenes']['demo']==again,self.demo['scenes']['demo']==again),([],False,True))
    def test_what_an_earlier_version_recorded_is_pinned(self):
        why=lambda d:self.at.pinned_why(d,self.root);pin=json.loads((ROOT/'added.json').read_text())['pinned'];case=lambda d,cid:[c for c in d['cases'] if c['id']==cid][0]
        self.assertEqual((why(self.demo),[c[0] for c in pin['cases']][:BUILT_IN_CASES]),([],[c[0] for c in ra.CASES[:BUILT_IN_CASES]]))
        self.assertTrue(len(pin['cases'])>=BUILT_IN_CASES and set(pin['scenarios'])>={'00_goal','04_admission'} and 'reflection' not in pin['meta_extensions'] and len(pin['meta_extensions'])>=7 and '900_demo' not in pin['scenarios'] and set(pin['action_handlers'])>=set(FOUR))
        for what,change,said in (('an older case changed',lambda d:case(d,'04_gates')['outcome'].update(note='x'),['case 04_gates is not the pinned case']),
                                 ('a digest of an older case changed',lambda d:case(d,'04_gates').update(pack_digest='0'*64),['case 04_gates is not the pinned case']),
                                 ('the first case taken out',lambda d:d['cases'].pop(0),None),('the last built-in case changed',lambda d:d['cases'][BUILT_IN_CASES-1].update(area='x'),['case '+ra.CASES[BUILT_IN_CASES-1][0]+' is not the pinned case']),
                                 ('all cases gone',lambda d:d.update(cases=[]),None),('the event record changed',lambda d:d['events']['initial'].update(status='x'),['the events block is not the pinned one']),
                                 ('the ask record changed',lambda d:d['ask_events']['after_first']['budget'].update(attention=3),['the ask_events block is not the pinned one']),
                                 ('a lens changed',lambda d:d['meta_extensions']['j2_projection'].update(note='x'),['the lens j2_projection is not the pinned one']),
                                 ('a lens taken out',lambda d:d['meta_extensions'].pop('graph_diff_nuance'),['the lens graph_diff_nuance is not the pinned one']),
                                 ('a handler entry that names another file',lambda d:d['action_handlers']['ask'].update(file='kernel/core.py',sha256=d['kernel_sha256']),['the handler of ask is not the pinned one']),
                                 ('a handler entry with another sha256',lambda d:d['action_handlers']['emit_artifact'].update(sha256='0'*64),['the handler of emit_artifact is not the pinned one']),
                                 ('a handler taken out',lambda d:d['action_handlers'].pop('simulate_fact'),['the handler of simulate_fact is not the pinned one']),
                                 ('another kernel recorded',lambda d:d.update(kernel_sha256='0'*64),['kernel/core.py is not the pinned kernel'])):
            got=why(self.forged(change));self.assertNotEqual(got,[],what);self.assertTrue(said is None or got==said,(what,got))
        self.assertEqual(why(self.forged(lambda d:(d['cases'][-2].update(note='x'),d['meta_extensions']['reflection'].update(candidate_count=99)))),[])   # an added case is not pinned yet; the reflection summary is by design over all cases and never is
        keep=(self.root/'added.json').read_bytes();book=json.loads(keep);lens=lambda d:d['meta_extensions']['implementation_website'].update(note='x')
        try:   # the three implementation lenses name every registered action kind: they are held while the declared kinds are the pinned ones, and only then
            for kinds,said in ((['demo_stamp'],['the lens implementation_website is not the pinned one']),([],[]),(['demo_stamp','other'],[])):
                book['pinned']['kinds']=kinds;write(self.root/'added.json',json.dumps(book));self.assertEqual(why(self.forged(lens)),said,kinds)
                self.assertEqual(why(self.forged(lambda d:d['meta_extensions']['stage_boundary'].update(note='x'))),['the lens stage_boundary is not the pinned one'],kinds)
            book['pinned'].update(kinds=[],scenes={'demo':self.at.sha(self.demo['scenes']['demo'])});write(self.root/'added.json',json.dumps(book))   # a sequence that was pinned: held like a case
            self.assertEqual((why(self.demo),why(self.forged(lambda d:d['scenes']['demo'].update(note='x'))),why(self.forged(lambda d:d.pop('scenes')))),([],['the sequence demo is not the pinned one'],['the sequence demo is not the pinned one']))
            # round 3 (refuter 1, finding 1, blocking): a pinned case is found by its id, never by its place. With the added cases pinned too, as when the next version is applied
            # to the built record, a case of a later version whose id sorts first stands before them and the record holds; what moves or changes a pinned case is named
            book['pinned'].update(scenes={},cases=[[c['id'],self.at.sha(c)] for c in self.demo['cases']]);write(self.root/'added.json',json.dumps(book))
            later=lambda d:d['cases'].insert(BUILT_IN_CASES,dict(self.copy(case(d,'900_demo')),id='100_later'))
            self.assertEqual((why(self.demo),why(self.forged(later))),([],[]))
            for what,change,said in (('the two pinned added cases swapped',lambda d:d['cases'].append(d['cases'].pop(-2)),['case 901_idle does not stand in the order the pinned cases were pinned in']),
                                     ('a pinned added case twice',lambda d:d['cases'].append(self.copy(case(d,'900_demo'))),['case 900_demo is not the pinned case']),
                                     ('a pinned added case taken out',lambda d:d['cases'].pop(),['case 901_idle is not the pinned case']),
                                     ('a pinned added case changed beside a later one',lambda d:(later(d),case(d,'900_demo').update(title='x')),['case 900_demo is not the pinned case'])):
                self.assertEqual(why(self.forged(change)),said,what)
            P=[['a','1'],['b','2'],['c','3']];X=['x','9']   # the rule itself, the one the applier uses when it pins again (moved_cases): (not the pinned case, out of the pinned order)
            self.assertEqual([self.at.moved_cases(P,now) for now in (P,[X]+P,[P[0],X,P[1],P[2]],P+[X],[P[1],P[0],P[2]],[P[0],P[2]],[P[0],P[1],P[1],P[2]],[P[0],['b','0'],P[2]],[])],
                             [([],[]),([],[]),([],[]),([],[]),([],['b']),(['b'],[]),(['b'],[]),(['b'],[]),(['a','b','c'],[])])
            write(self.root/'added.json','{}');self.assertEqual(why(self.demo),['added.json or the record cannot be read: KeyError'])
        finally:write(self.root/'added.json',keep)
        for rel,text,said in (('scenarios/04_admission.json',json.dumps({'schema':'sutra-extension/2','id':'04_admission','providers':{'local-provider':5},'note':'x'}),'scenarios/04_admission.json is not the pinned file'),
                              ('kernel/core.py',(self.root/'kernel'/'core.py').read_text()+'# x\n','kernel/core.py is not the pinned kernel')):
            keep=(self.root/rel).read_bytes();write(self.root/rel,text)
            try:self.assertEqual(why(self.demo),[said])
            finally:write(self.root/rel,keep)
        keep=(self.root/'scenarios'/'00_goal.json').read_bytes();(self.root/'scenarios'/'00_goal.json').unlink()
        try:self.assertEqual(why(self.demo),['scenarios/00_goal.json is not the pinned file'])
        finally:write(self.root/'scenarios'/'00_goal.json',keep)
        self.assertEqual(why(self.demo),[])
    def test_what_an_edit_version_moves_is_declared_and_named_or_fails(self):
        # Ruling R32. An edit version is a delivery that changes existing files and says so in its manifest. The applier records it in added.json (`edits`: its script and,
        # for every file it changed, the sha256 before and after) and takes the pins of the kernel and of the handler entries again for those files. Every other pin stays:
        # what the edit moves of the things an earlier version recorded fails S202, unless its manifest declares the move (`moves`), each with a reason. A declared move is
        # held to nothing while its version is not pinned yet and is named in the detail of S202; a declared move of a thing that did not move fails.
        why=lambda d:self.at.pinned_why(d,self.root);said=lambda:self.at.edits_said(self.root);keep=(self.root/'added.json').read_bytes();case=lambda d,cid:[c for c in d['cases'] if c['id']==cid][0]
        moved=lambda d:case(d,'04_gates').update(description='Other words.')   # an older case moved, in a field no built-in check reads
        def book(*moves,**pinned):
            b=json.loads(keep);b['pinned'].update(pinned)
            b['applied'].append(dict({'label':'0.0.1-edit','delivery':'edit','files':{},'edits':{'script':'apply.py','sha256':'0'*64,'files':{'tools/run_all.py':['1'*64,'2'*64]}}},**({'moves':[{'what':w,'why':y} for w,y in moves]} if moves else {})))
            write(self.root/'added.json',json.dumps(b))
        changed='the edit version 0.0.1-edit changed tools/run_all.py (added.json records the sha256 of each before and after)'
        named=lambda what,reason:'declared as moved by the edit version 0.0.1-edit, held to nothing until the next version is applied: '+what+' ('+reason+')'
        stale=lambda what:[what+' is declared as moved by the edit version 0.0.1-edit and has not moved']
        try:
            self.assertEqual((why(self.demo),why(self.forged(moved)),said()),([],['case 04_gates is not the pinned case'],[]))   # no edit version in the book: as ever
            book()   # an edit version that declares nothing: what it moves fails as ever, and the detail names the version and the files it changed
            self.assertEqual((why(self.demo),why(self.forged(moved)),said()),([],['case 04_gates is not the pinned case'],[changed]))
            book(('case 04_gates','its description says what the case shows'))   # declared: held to nothing and named with its reason; declared and not moved: a failed check
            self.assertEqual((why(self.forged(moved)),why(self.demo),said()),([],stale('case 04_gates'),[changed,named('case 04_gates','its description says what the case shows')]))
            self.assertEqual(why(self.forged(lambda d:(moved(d),case(d,'03_evidence').update(description='x')))),['case 03_evidence is not the pinned case'])   # a declaration covers the thing it names and no other
            # every kind of thing a manifest may declare: a case (above), the two records, a lens, a sequence, a scenario file
            pinned_scene={'demo':self.at.sha(self.demo['scenes']['demo'])}
            for what,change,sentence in (('events',lambda d:d['events']['initial'].update(status='x'),'the events block is not the pinned one'),
                                         ('ask_events',lambda d:d['ask_events']['after_first']['budget'].update(attention=3),'the ask_events block is not the pinned one'),
                                         ('lens j2_projection',lambda d:d['meta_extensions']['j2_projection'].update(note='x'),'the lens j2_projection is not the pinned one'),
                                         ('sequence demo',lambda d:d['scenes']['demo'].update(note='x'),'the sequence demo is not the pinned one')):
                book(scenes=pinned_scene);self.assertEqual(why(self.forged(change)),[sentence],what)
                book((what,'a reason'),scenes=pinned_scene);self.assertEqual((why(self.forged(change)),why(self.demo)),([],stale(what)),what)
            file=self.root/'scenarios'/'04_admission.json';held=file.read_bytes()
            book(('scenario 04_admission','a reason'));self.assertEqual(why(self.demo),stale('scenario 04_admission'))
            write(file,held+b' ')
            try:
                self.assertEqual(why(self.demo),[])
                book();self.assertEqual(why(self.demo),['scenarios/04_admission.json is not the pinned file'])
            finally:write(file,held)
            # an implementation lens is not compared while the declared kinds are not the pinned ones; declared as moved, it must have moved all the same
            lens=lambda d:d['meta_extensions']['implementation_website'].update(note='x')
            book(kinds=['other']);self.assertEqual(why(self.forged(lens)),[])
            book(('lens implementation_website','a reason'),kinds=['other']);self.assertEqual((why(self.forged(lens)),why(self.demo)),([],stale('lens implementation_website')))
            # the kernel and the handler entries are never declared: the applier takes their pins again for the files an edit version changed, and a book that names them declares nothing
            book(('the kernel','x'),('the handler of ask','x'),kernel_sha256='0'*64)
            self.assertEqual(why(self.forged(lambda d:d['action_handlers']['ask'].update(sha256='0'*64))),['kernel/core.py is not the pinned kernel','the handler of ask is not the pinned one'])
            # a declaration is live while its version is not pinned yet. Once the pins are from that version's build (the next version was applied to its built, verified
            # record), the pins hold the moved thing as it then stood and the declaration is history: it excuses nothing and is no stale declaration
            book(('case 04_gates','a reason'),**{'from':'sutra-kernel-extensions/0.0.1-edit'})
            self.assertEqual((why(self.demo),why(self.forged(moved)),said()),([],['case 04_gates is not the pinned case'],[]))
            U=lambda of,*labels:[e['label'] for e in self.at.unpinned({'pinned':{'from':'sutra-kernel-extensions/'+of},'applied':[{'label':l} for l in labels]})]   # the rule itself: the versions applied after the one the pins are from
            self.assertEqual([U('0.9.0-stop','a','b','c'),U('a','a','b','c'),U('b','a','b','c'),U('c','a','b','c'),U('x')],[['a','b','c'],['b','c'],['c'],[],[]])
            self.assertEqual([bool(re.fullmatch(self.at.WHAT,w)) for w in ('case 04_gates','events','ask_events','scenario 100_delivered_but_open','sequence demo','lens j2_projection','the kernel','handler ask','case','case  x','04_gates','events x')],[True]*6+[False]*6)
            # the whole verifier: S202 holds with the move declared, and its detail names the edit version, the move and the reason (what is wrong, when something is, stands before that)
            book(('case 04_gates','its description says what the case shows'));row=[t for t in self.at.inspect(self.forged(moved))['checks'] if t['id']==S202][0]
            self.assertEqual((row['pass'],row['detail']),(True,changed+'; '+named('case 04_gates','its description says what the case shows')))
        finally:write(self.root/'added.json',keep)
        self.assertEqual((why(self.demo),said()),([],[]))
        self.assertIn('a delivery edits no existing file unless it is an edit version, which says so in its manifest, is recorded as one with the hashes of what it changed, and is reviewed as every kernel version is',(ROOT/'README.md').read_text())
        self.assertIn('a move of a thing S202 holds that is not declared fails S202, and so does a declared move of a thing that did not move',(ROOT/'README.md').read_text())
    def test_every_added_file_is_listed_by_sha_and_nothing_else_may_be_put_in(self):
        why=lambda d=None:self.at.files_why(d or self.demo,self.root)
        self.assertEqual(why(),[])
        for rel,text,said in (('qa/checks/demo.py',CHECK_SRC+'# swapped\n','qa/checks/demo.py is not the file added.json lists'),('kinds/demo_stamp.py',KIND_SRC+'# changed\n','kinds/demo_stamp.py is not the file added.json lists'),
                              ('cases/900_demo.json',json.dumps(dict(CASE,expected='PLAN_READY')),'cases/900_demo.json is not the file added.json lists'),('tests/test_added.py','# gone\n','tests/test_added.py is not the file added.json lists')):
            keep=(self.root/rel).read_bytes();write(self.root/rel,text)
            try:self.assertEqual(why(),[said])
            finally:write(self.root/rel,keep)
            (self.root/rel).unlink()
            try:self.assertEqual(why(),[said])   # a listed file that is gone
            finally:write(self.root/rel,keep)
        for rel,said in (('kernel/__init__.py','kernel/__init__.py is neither built in nor listed in added.json'),('copy.py','copy.py is neither built in nor listed in added.json'),('qa/hashlib.py','qa/hashlib.py is neither built in nor listed in added.json'),
                         ('tools/packs/zz.py','tools/packs/zz.py is neither built in nor listed in added.json'),('cases/902_by_hand.json','cases/902_by_hand.json is neither built in nor listed in added.json'),
                         ('extensions/by_hand.py','extensions/by_hand.py is neither built in nor listed in added.json'),('tests/test_by_hand.py','tests/test_by_hand.py is neither built in nor listed in added.json'),
                         ('kernel/__init__.pyc','kernel/__init__.pyc is neither built in nor listed in added.json'),('copy.pyc','copy.pyc is neither built in nor listed in added.json'),('qa/hashlib.pyc','qa/hashlib.pyc is neither built in nor listed in added.json'),
                         ('kernel/fast.so','kernel/fast.so is neither built in nor listed in added.json'),('site.pth','site.pth is neither built in nor listed in added.json'),('release/old.pyo','release/old.pyo is neither built in nor listed in added.json'),
                         ('extensions/__init__.py','extensions/__init__.py is no add-on file'),('tools/packs/sub/y.py','tools/packs/sub is no add-on file'),('tests/.hidden.py','tests/.hidden.py is no add-on file'),
                         ('cases/notes.txt','cases/notes.txt is no add-on file'),('tools/scenes/a-b.py','tools/scenes/a-b.py is no add-on file'),('kinds/Caps.py','kinds/Caps.py is no add-on file'),('qa/checks/_x.py','qa/checks/_x.py is no add-on file')):
            write(self.root/rel,'')
            try:self.assertIn(said,why(),rel)
            finally:
                (self.root/rel).unlink()
                if rel=='tools/packs/sub/y.py':(self.root/'tools'/'packs'/'sub').rmdir()
        for what,change in (('another sha256 in the record',lambda d:d['added']['files'].update({'qa/checks/demo.py':'0'*64})),('a file less in the record',lambda d:d['added']['files'].pop('qa/checks/demo.py')),
                            ('a file more in the record',lambda d:d['added']['files'].update({'qa/checks/more.py':'0'*64})),('no list in the record',lambda d:d.pop('added')),('no list of scenario files',lambda d:d['added'].pop('scenarios')),
                            ('a scenario file less in the record',lambda d:d['added']['scenarios'].pop('900_demo')),('another sha256 of a scenario file',lambda d:d['added']['scenarios'].update({'00_goal':'0'*64}))):
            self.assertNotEqual(why(self.forged(change)),[],what)
        self.assertEqual(why(self.forged(lambda d:d['added'].update(note='x'))),['the record keeps something else under added than files, scenes and scenarios'])
        self.assertEqual(why(self.forged(lambda d:d.update(release='sutra-kernel-extensions/9.9.9-other'))),['the record says it is the build of sutra-kernel-extensions/9.9.9-other; the last version added.json lists is 0.0.0-test'])
        # the scenario files are the ones the build authored: one made by hand (the file of the review, which made an honest record fail), and one changed by hand, are named
        for name,text,said in (('200_shop.json',json.dumps({'schema':'sutra-extension/2','id':'200_shop','methods':[dict(mp.method('ship-original@1','parcel_sent'),cost={'compute':3,'money':3,'attention':0})]}),'scenarios/200_shop.json is not a scenario file this build authored'),
                               ('900_demo.json',(self.root/'scenarios'/'900_demo.json').read_text()+' ','scenarios/900_demo.json is not the file this build authored')):
            keep=(self.root/'scenarios'/name).read_bytes() if (self.root/'scenarios'/name).exists() else None;write(self.root/'scenarios'/name,text)
            try:self.assertEqual(why(),[said])
            finally:(self.root/'scenarios'/name).unlink() if keep is None else write(self.root/'scenarios'/name,keep)
        keep=(self.root/'added.json').read_bytes();book=json.loads(keep)
        try:
            book['applied'].append({'label':'0.0.1-twice','delivery':'twice','files':{'qa/checks/demo.py':book['applied'][0]['files']['qa/checks/demo.py']}});write(self.root/'added.json',json.dumps(book))
            self.assertIn('added.json lists qa/checks/demo.py twice',why())
            book['applied']=[];write(self.root/'added.json',json.dumps(book));self.assertIn('qa/checks/demo.py is neither built in nor listed in added.json',why())   # a book that lists nothing: every added file was put in by hand
            book['pinned']['built_in']=[];write(self.root/'added.json',json.dumps(book));self.assertIn('kernel/core.py is neither built in nor listed in added.json',why())
        finally:write(self.root/'added.json',keep)
        self.assertEqual((why(),self.at.PLACES,self.at.CODE),([],(('cases','.json'),('tools/packs','.py'),('tools/scenes','.py'),('kinds','.py'),('extensions','.py'),('tests','.py'),('qa/checks','.py')),('.py','.pyc','.pyo','.pyd','.pyw','.pyz','.so','.pth','.dylib','.dll')))
        # Limit 9 of the README, pinned (round 3, refuter 2, finding 6): a file the lab had before the points is held here by its name, not by its content (the kernel, the
        # baseline and the files of the built-in handlers are held by sha256 in S01, S02 and S41)
        rel='extensions/reflection.py';keep=(self.root/rel).read_bytes();write(self.root/rel,keep+b'\n# other code\n')
        try:self.assertEqual(why(),[])
        finally:write(self.root/rel,keep)
        # ... until an edit version changes it (ruling R32): added.json records the sha256 the edit left, and the file is held to it; the last edit of a file is the one
        # that counts; README.md and tools/run_all.py, where the applier places words at every application, are left out
        book_keep=(self.root/'added.json').read_bytes();book=json.loads(book_keep);left=sha_file(self.root/rel)
        edit=lambda label,files:{'label':label,'delivery':'edit','files':{},'edits':{'script':'apply.py','sha256':'0'*64,'files':files}}
        release=lambda label:'the record says it is the build of sutra-kernel-extensions/0.0.0-test; the last version added.json lists is '+label
        try:
            book['applied']+=[edit('0.0.1-edit',{rel:['1'*64,'2'*64]}),edit('0.0.2-edit',{rel:['2'*64,left],'tools/run_all.py':['3'*64,'4'*64],'README.md':['5'*64,'6'*64]})];write(self.root/'added.json',json.dumps(book))
            self.assertEqual(why(),[release('0.0.2-edit')])   # the file is as the last edit left it
            write(self.root/rel,keep+b'\n# other code\n')
            try:self.assertEqual(why(),[rel+' is not the file the edit version 0.0.2-edit left (added.json records its sha256 after the edit)',release('0.0.2-edit')])
            finally:write(self.root/rel,keep)
            book['applied'].pop();write(self.root/'added.json',json.dumps(book))
            self.assertEqual(why(),[rel+' is not the file the edit version 0.0.1-edit left (added.json records its sha256 after the edit)',release('0.0.1-edit')])
        finally:write(self.root/'added.json',book_keep)
        self.assertEqual((why(),self.at.PLACED),([],('README.md','tools/run_all.py')))
        self.assertIn('S203 holds a file the lab had before the points by its name, not by its content',(ROOT/'README.md').read_text())
    def test_every_receipt_names_a_recorded_handler(self):
        why=lambda d:self.at.handlers_why(d,self.root);first=lambda d:d['scenes']['demo']['first']['runs'][0];said=lambda part,kind:['a receipt in '+part+' names the action kind '+kind+', which the record holds no handler for']
        self.assertEqual((why(self.demo),self.at.BUILT_IN_KINDS),([],tuple(FOUR)))
        self.assertEqual(why(self.forged(lambda d:d['action_handlers'].pop('demo_stamp'))),said('scenes','demo_stamp'))   # what a kind handed to one State alone leaves in the record
        self.assertEqual(why(self.forged(lambda d:first(d)['model_receipts'][0].update(action='send_email'))),said('scenes','send_email'))
        self.assertEqual(why(self.forged(lambda d:[e for e in first(d)['trace'] if e['operation']=='LOCAL_EFFECT'][0]['data']['receipt'].update(action='send_email'))),said('scenes','send_email'))   # in the trace alone
        self.assertEqual(why(self.forged(lambda d:[c for c in d['cases'] if c['id']=='04_gates'][0]['run']['runs'][0]['model_receipts'][0].update(action='send_email'))),said('cases','send_email'))
        self.assertEqual(why(self.forged(lambda d:d['events']['initial']['runs'][0]['model_receipts'][0].update(action='send_email'))),said('events','send_email'))
        self.assertEqual(why(self.forged(lambda d:d['ask_events']['first']['runs'][0]['model_receipts'][0].pop('action'))),said('ask_events','None'))
        self.assertEqual(why(self.forged(lambda d:d.pop('action_handlers'))),['the receipts cannot be read: KeyError'])
        # round 3 (refuter 2, finding 2): the kind a receipt names is the kind its method names in the packs its run loaded. Another kind the record holds a handler for fails
        # too, in the run or in its trace alone, whatever checks a version brings of its own; so does a step that is no method of those packs
        kind=lambda part,k,step,want:['a receipt in '+part+' says the action kind '+k+' did the step '+step+', whose method names the kind '+want+' in the packs its run loaded']
        no_method=lambda part,step:['a receipt in '+part+' is for the step '+step+', which is no method of the packs its run loaded (as the scenario files hold them)']
        self.assertEqual(why(self.forged(lambda d:first(d)['model_receipts'][0].update(action='simulate_fact'))),kind('scenes','simulate_fact','stamp@1','demo_stamp'))   # the forgery of the review
        self.assertEqual(why(self.forged(lambda d:[e for e in first(d)['trace'] if e['operation']=='LOCAL_EFFECT'][0]['data']['receipt'].update(action='ask'))),kind('scenes','ask','stamp@1','demo_stamp'))
        self.assertEqual(why(self.forged(lambda d:[c for c in d['cases'] if c['id']=='04_gates'][0]['outcome']['model_receipts'][0].update(action='demo_stamp'))),kind('cases','demo_stamp','ship-replacement@1','simulate_fact'))
        self.assertEqual(why(self.forged(lambda d:[c for c in d['cases'] if c['id']=='900_demo'][0]['run']['runs'][0]['model_receipts'][0].update(action='ask'))),kind('cases','ask','ship-replacement@1','simulate_fact'))   # an added case
        self.assertEqual(why(self.forged(lambda d:first(d)['model_receipts'][0].update(method='stamp@2'))),no_method('scenes','stamp@2'))
        self.assertEqual(why(self.forged(lambda d:first(d).update(provenance=[]))),no_method('scenes','stamp@1'))
        write(self.root/'kinds'/'.draft.py','')
        try:self.assertEqual(why(self.demo),['kinds/.draft.py is no kind file'])
        finally:(self.root/'kinds'/'.draft.py').unlink()
    def test_every_kind_is_held_to_the_file_its_handler_lives_in(self):
        # S41, as the points hold it: the four built-in kinds plus the declared ones, each in its own file. What a record says of a handler is all a record can say: which
        # function ran is held by the build (tools/run_all.py stops at a re-bound handler); a re-bound handler that the build let through would stand here under another file.
        why=lambda d:self.at.kinds_why(d['action_handlers'],self.root);lives=lambda kind,file,module,want:[kind+': the record says its handler lives in '+file+' (module '+module+'), not in '+want]
        self.assertEqual((why(self.demo),self.at.KIND_FILES),([],{'simulate_fact':'kernel/core.py','compile_candidate':'extensions/constructor.py','emit_artifact':'extensions/constructor.py','ask':'extensions/asks.py'}))
        self.assertEqual(why(self.forged(lambda d:d['action_handlers']['ask'].update(file='kernel/core.py',sha256=d['kernel_sha256']))),lives('ask','kernel/core.py','extensions.asks','extensions/asks.py'))   # the forgery of the review
        self.assertEqual(why(self.forged(lambda d:d['action_handlers']['emit_artifact'].update(module='extensions.zz',file='extensions/zz.py'))),lives('emit_artifact','extensions/zz.py','extensions.zz','extensions/constructor.py'))   # what the extension of the review left in the record
        self.assertEqual(why(self.forged(lambda d:d['action_handlers']['compile_candidate'].update(module='extensions.asks'))),lives('compile_candidate','extensions/constructor.py','extensions.asks','extensions/constructor.py'))
        self.assertEqual(why(self.forged(lambda d:d['action_handlers']['demo_stamp'].update(module='extensions.asks',file='extensions/asks.py'))),lives('demo_stamp','extensions/asks.py','extensions.asks','kinds/demo_stamp.py'))   # a declared kind lives in its kind file
        for what,change in (('a handler taken out',lambda d:d['action_handlers'].pop('demo_stamp')),('a handler more',lambda d:d['action_handlers'].update(more=d['action_handlers']['ask'])),('a built-in handler taken out',lambda d:d['action_handlers'].pop('ask'))):
            self.assertTrue(why(self.forged(change))[0].startswith('the record holds handlers for '),what)
        self.assertEqual((self.at.kinds_why({k:1 for k in FOUR+['demo_stamp']},self.root),self.at.kinds_why(None,self.root)),(['the handlers cannot be read: AttributeError'],['the handlers cannot be read: TypeError']))
        write(self.root/'kinds'/'ask.py',KIND_SRC)   # a kind file named like a built-in kind (the applier and the build refuse it; put in by hand, the check names it)
        try:self.assertEqual(why(self.demo),['kinds/ask.py is named like a built-in action kind'])
        finally:(self.root/'kinds'/'ask.py').unlink()
    def test_a_check_module_is_parsed_and_then_run_in_a_process_of_its_own_and_whatever_it_does_is_one_failed_row(self):
        d=self.tmp();data={'cases':[{'id':'x'}],'about':'a small record: the modules of this test read none of the lab\'s'};rows="    return [('S150_a',True,'')]\n";head=HEAD
        def got(src,taken=(),record=None):return self.at.module_rows(write(d/'zz.py',src),data if record is None else record,self.root,set(taken))
        self.assertEqual(got(head+rows),([('S150_a',True,'')],None))
        # (a) refused by its text, and not run: every one of these would raise at its first line if it were
        boom="raise RuntimeError('this module was run')\n"
        for what,src,said in (('an import of the kernel','import kernel.core\n'+head+rows,'it imports kernel.core'),('after a comma','import json,kernel.core\n'+head+rows,'it imports json, kernel.core'),
                              ('after a semicolon','import json;import os\n'+head+rows,'it imports os'),('inside the function',head+'    import tools.run_all\n'+rows,'it imports tools.run_all'),
                              ('under an if','if 1: import extensions.asks\n'+head+rows,'it imports extensions.asks'),('from the lab','from kernel import core\n'+head+rows,'it imports kernel'),
                              ('from an allowed name that is longer','from jsonx import loads\n'+head+rows,'it imports jsonx'),('relative','from . import x\n'+head+rows,'it imports .'),('relative, by a name that is allowed','from .json import x\n'+head+rows,'it imports json'),
                              ('sys','import sys\n'+head+rows,'it imports sys'),('importlib','import importlib\n'+head+rows,'it imports importlib'),('pathlib','from pathlib import Path\n'+head+rows,'it imports pathlib'),
                              ('the built-ins taken from an allowed module','from hashlib import __builtins__ as b\n'+head+rows,'it imports __builtins__ from hashlib'),   # the module of the first refuter
                              ('the same from json','from json import __builtins__ as B\n'+head+rows,'it imports __builtins__ from json'),                                # the module of the second
                              ('the search path of a package','from json import __path__ as w\n'+head+rows,'it imports __path__ from json'),('a private name of a module','from collections import _sys\n'+head+rows,'it imports _sys from collections'),
                              ('a star','from math import *\n'+head+rows,'it imports * from math'),('a refused name from an allowed module','from json import codecs,sys\n'+head+rows,'it imports sys from json'),
                              ('a built-in that opens a file, taken from an allowed module','from json import open\n'+head+rows,'it imports open from json'),
                              ('the loader of the built-ins',head+"    __loader__.load_module('posix')\n"+rows,'it names __loader__'),('the spec of the built-ins',head+'    __spec__\n'+rows,'it names __spec__'),('the maker of classes',head+'    __build_class__\n'+rows,'it names __build_class__'),
                              ('__import__',head+"    __import__('os')\n"+rows,'it names __import__'),('eval',head+"    eval('1')\n"+rows,'it names eval'),('exec',head+"    exec('x=1')\n"+rows,'it names exec'),
                              ('open',head+"    open('x')\n"+rows,'it names open'),('getattr',head+"    getattr(sha,'__globals__')\n"+rows,'it names getattr'),('a built-in under another name',head+"    run=exec\n"+rows,'it names exec'),
                              ('a built-in as an attribute',head+"    data.eval\n"+rows,'it reaches for .eval'),('the globals of a function',head+'    sha.__globals__\n'+rows,'it reaches for .__globals__'),
                              ('a frame',head+'    (x for x in []).gi_frame\n'+rows,'it reaches for .gi_frame'),('a module through a module','import json\n'+head+'    json.codecs.sys\n'+rows,'it reaches for .sys'),
                              ('the class of an object',head+'    ().__class__\n'+rows,'it reaches for .__class__'),('a private attribute',head+'    ROOT._accessor\n'+rows,'it reaches for ._accessor'),
                              ('no checks','X=1\n','it defines no checks'),('checks inside a class','class A:\n    def checks(self):return []\n','it defines no checks'),('checks as a value','checks=lambda *a:[]\n','it defines no checks'),
                              ('not Python','def checks(:\n','it is not Python')):
            out,why=got(boom+src);self.assertTrue(out is None and why.startswith(said) and why.endswith('; it was not run'),(what,why))
        self.assertEqual((self.at.ALLOWED,self.at.FORBIDDEN,self.at.DUNDERS,self.at.REACH),
                         (('__future__','collections','copy','functools','hashlib','html','itertools','json','math','re'),
                          ('__builtins__','__import__','breakpoint','compile','delattr','eval','exec','exit','getattr','globals','input','locals','open','quit','setattr','vars'),
                          ('__contains__','__doc__','__eq__','__getitem__','__init__','__len__','__name__','__setitem__'),
                          ('ag_frame','attrgetter','builtins','cr_frame','f_back','f_builtins','f_globals','f_locals','gi_frame','methodcaller','modules','os','sys','tb_frame')))
        for name in self.at.FORBIDDEN+self.at.REACH:self.assertTrue(self.at.guard(head+'    x.'+name+'\n'+rows).startswith('it reaches for .'+name) and (name in self.at.REACH or self.at.guard(head+'    '+name+'\n'+rows)=='it names '+name),name)
        for name in self.at.ALLOWED:self.assertEqual((self.at.guard('import '+name+'\n'+head+rows),self.at.guard('import '+name+'.sub\n'+head+rows),name=='__future__' or self.at.guard('from '+name+' import x\n'+head+rows)),(None,None,name=='__future__' or None),name)
        for name in self.at.DUNDERS:self.assertEqual(self.at.guard(head+'    data.'+name+'\n'+rows),None,name)
        self.assertEqual((self.at.guard('import re\n'+head+"    re.compile('a')\n"+rows),self.at.guard(head+"    x.compile('a')\n"+rows),self.at.guard(head+'    __name__,__doc__\n'+rows)),(None,'it reaches for .compile',None))   # re.compile names no built-in: it is let through, on re alone
        # run, although it names these words in a comment and in a text; every allowed module can be imported in the module's process; a pattern is compiled
        self.assertEqual(got('"""from tools/packs: open( the file, import kernel"""\nfrom __future__ import annotations\nimport json,hashlib,re,math,collections,itertools,functools,copy,html\nfrom html.parser import HTMLParser\nfrom collections import Counter\n'
                             +head+"    # exec( nothing, eval( nothing\n    x={};x.__setitem__('a',type(x).__name__)\n    return [('S150_a',bool(re.compile('a+').fullmatch('aa')) and x=={'a':'dict'} and Counter('aab')['a']==2,__name__)]\n"),([('S150_a',True,'qa_checks_zz')],None))
        self.assertEqual(got(head.replace('data,','data: NoSuchName,').replace('):',') -> NorThis:')+rows),([('S150_a',True,'')],None))   # annotations are kept as text, with or without the line from __future__
        # (b) run in a process of its own, on its own copy of the record, with a read-only stand-in for the lab's folder that holds the files a module may read
        self.assertEqual(got(head+"    data.clear();return [('S150_a',(ROOT/'kernel'/'core.py').is_file(),str(len(sha({})))),('S151_b',check_chain([]),__name__)]\n"),([('S150_a',True,'64'),('S151_b',True,'qa_checks_zz')],None))
        self.assertEqual(data['cases'],[{'id':'x'}])
        self.assertEqual(got(head+"    return (r for r in [['S150_a',False,'as a list, from a generator']])\n"),([('S150_a',False,'as a list, from a generator')],None))
        probe=('import json,hashlib\n'+head+"    s=ROOT/'scenarios'\n    return [('S150_a',True,json.dumps({'str':str(ROOT),'kernel':hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest(),'pack':json.loads((s/'00_goal.json').read_text())['id'],"
               "'glob':[f.name for f in sorted(s.glob('0[0-1]_*.json'))],'stem':(s/'00_goal.json').stem,'suffix':(s/'00_goal.json').suffix,'record':(ROOT/'results'/'actual_run_records.json').exists(),'verdict':(ROOT/'qa'/'independent_verification.json').exists(),"
               "'own':(ROOT/'qa'/'checks'/'demo.py').is_file(),'book':'pinned' in json.loads((ROOT/'added.json').read_text(encoding='utf-8')),'top':sorted(f.name for f in ROOT.iterdir()),'cases':sorted(f.name for f in (ROOT/'cases').iterdir()),"
               "'deep':[f.as_posix() for f in ROOT.rglob('demo_stamp.py')],'parent':(s/'00_goal.json').parent==s,'joined':ROOT.joinpath('kinds','demo_stamp.py').is_file(),'folder':s.is_dir() and not s.is_file()}))]\n")
        self.assertEqual(json.loads(got(probe)[0][0][2]),{'str':'.','kernel':sha_file(self.root/'kernel'/'core.py'),'pack':'00_goal','glob':['00_goal.json','01_domain.json'],'stem':'00_goal','suffix':'.json','record':False,'verdict':False,'own':True,'book':True,
                         'top':['added.json','cases','extensions','kernel','kinds','qa','release','scenarios','tests','tools'],'cases':['900_demo.json','901_idle.json'],'deep':['kinds/demo_stamp.py'],'parent':True,'joined':True,'folder':True})
        handed=json.loads(self.at.hand_in(data,self.root));book=json.loads((self.root/'added.json').read_text())
        self.assertEqual((sorted(handed),handed['record'],handed['allowed'],handed['forbidden'],all(type(t) is str and (self.root/rel).read_bytes()==t.encode() for rel,t in handed['files'].items())),(['allowed','files','forbidden','record'],data,list(self.at.ALLOWED),list(self.at.FORBIDDEN),True))
        self.assertEqual(sorted(handed['files']),sorted({'kernel/core.py','release/baseline_v0_1_core.py','added.json'}|{'scenarios/'+f.name for f in (self.root/'scenarios').iterdir()}|{rel for rel in book['pinned']['built_in'] if (self.root/rel).is_file()}|set(book['points']['files'])|set(book['applied'][0]['files'])))
        # what is handed is a path of the lab: a book that lists a path which leaves the lab (and comes back), or one from the root of the file system, hands neither; and a
        # handed file reads as Path.read_text gives it (one kind of line end), while its bytes are as they are
        ends=b'A = 1\r\nB = 2\rC = 3\n';root,record=self.lab_copy({'extensions/line_ends.py':ends},self.addCleanup);at=verifier(root);other=json.loads((root/'added.json').read_text())
        other['pinned']['built_in']+=['/etc/hosts','../'+root.name+'/kernel/core.py','kernel\\core.py'];write(root/'added.json',json.dumps(other))
        self.assertEqual((Path('/etc/hosts').is_file(),(root/'..'/root.name/'kernel'/'core.py').is_file(),sorted(set(other['pinned']['built_in'])&set(json.loads(at.hand_in(record,root))['files']))),(True,True,sorted(rel for rel in book['pinned']['built_in'] if (root/rel).is_file())))
        reads=at.module_rows(write(d/'zz.py','import json\n'+head+"    f=ROOT/'extensions'/'line_ends.py';return [('S150_a',True,json.dumps([f.read_text(),len(f.read_bytes())]))]\n"),record,root,set())
        self.assertEqual(json.loads(reads[0][0][2]),[ends.decode().replace('\r\n','\n').replace('\r','\n'),len(ends)])
        # the two functions a module is handed are its process's own copies of the verifier's: they say the same of a record, of an honest trace and of forged ones
        trace=self.demo['cases'][3]['outcome']['trace'];rec={'t':trace,'n':[1,1.0,True,None,'\u00e9\u4e16',{'b':2,'a':1}]};moved=lambda change:(lambda t:(change(t),t)[1])(self.copy(trace))
        forgeries=[trace,moved(lambda t:t[1].update(operation='X')),moved(lambda t:t[0].update(seq=1.0)),moved(lambda t:t[1].update(prev_sha256='0')),moved(lambda t:t.pop(0)),[]]
        said=got('import json\n'+head+"    t=data['t'];f=json.loads(json.dumps(t));f[1]['operation']='X';g=json.loads(json.dumps(t));g[0]['seq']=1.0;h=json.loads(json.dumps(t));h[1]['prev_sha256']='0';i=t[1:]\n"
                 "    return [('S150_a',True,json.dumps([sha(data)]+[check_chain(x) for x in (t,f,g,h,i,[])]))]\n",record=rec)
        self.assertEqual(json.loads(said[0][0][2]),[self.at.sha(rec)]+[self.at.check_chain(x) for x in forgeries]);self.assertEqual([self.at.check_chain(x) for x in forgeries],[True,False,False,False,False,True])
        # (c) whatever goes wrong is the module's one failed row, and nothing else: the verdict is computed from the rows that come back
        for what,body,said in (('it raises',"    raise RuntimeError('boom')\n",'it raised RuntimeError'),('it leaves',"    raise SystemExit(0)\n",'it raised SystemExit'),('it is interrupted',"    raise KeyboardInterrupt\n",'it raised KeyboardInterrupt'),
                               ('a missing row of the record',"    return [('S150_a',data['no_such_block']==1,'')]\n",'it raised KeyError'),('it prints',"    print('S150_a is fine')\n"+rows,'it wrote something else to its output than its rows'),
                               ('it writes through what it was handed',"    (ROOT/'written_by_a_check.txt').write_text('x')\n"+rows,'it raised AttributeError'),('it reads what it was not handed',"    (ROOT/'results'/'actual_run_records.json').read_text()\n"+rows,'it raised FileNotFoundError'),
                               ('it leaves the handed folder',"    (ROOT/'..'/'..'/'etc'/'hosts').read_text()\n"+rows,'it raised FileNotFoundError'),
                               ('no row',"    return []\n",'it returned no row'),('nothing',"    pass\n",'it raised TypeError'),('ok as text',"    return [('S150_a','no','')]\n",'it returned a row that is not'),
                               ('ok as a number',"    return [('S150_a',1,'')]\n",'it returned a row that is not'),('two fields',"    return [('S150_a',True)]\n",'it returned a row that is not'),('four fields',"    return [('S150_a',True,'','')]\n",'it returned a row that is not'),
                               ('a detail that is no text',"    return [('S150_a',True,[])]\n",'it returned a row that is not'),('a detail that is no JSON',"    return [('S150_a',True,{1,2})]\n",'it returned a row that is not'),('an id that is no text',"    return [(150,True,'')]\n",'it returned a row that is not'),
                               ('a row that is a text',"    return ['S150_a']\n",'it returned a row that is not'),('a row that is a dict',"    return [{'id':'S150_a','pass':True,'detail':''}]\n",'it returned a row that is not'),
                               ('a good row and a bad one',"    return [('S150_a',True,''),('S151_b','yes','')]\n",'it returned a row that is not'),
                               ('an id without a number',"    return [('zz_reads_only_the_record',True,'')]\n",'it returned the id zz_reads_only_the_record'),('a built-in id',"    return [('S01_source_hash_current',True,'')]\n",'it returned S01_source_hash_current'),
                               ('a number of the built-in checks',"    return [('S59_x',True,'')]\n",'it returned S59_x'),('the number 0',"    return [('S0_x',True,'')]\n",'it returned S0_x'),('a number of the points',"    return [('S205_x',True,'')]\n",'it returned S205_x'),
                               ('a number twice',"    return [('S150_a',True,''),('S150_b',True,'')]\n",'it returned S150_b')):
            out,why=got(head+body);self.assertTrue(out is None and why.startswith(said),(what,why))
        self.assertFalse((self.root/'written_by_a_check.txt').exists())
        keep=self.at.CHECK_SECONDS;self.at.CHECK_SECONDS=1   # a module that hangs is stopped after the stated time
        try:self.assertEqual(got(head+'    while True:pass\n'),(None,'it did not finish within 1 seconds'))
        finally:self.at.CHECK_SECONDS=keep
        self.assertEqual(keep,120)
        self.assertEqual(got(head+rows,{150})[1],'it returned S150_a, whose number is reserved or already taken')   # taken by a module before it
        self.assertEqual((got(head+"    return [('S60_x',True,''),('S199_y',True,''),('S210_z',True,'')]\n")[1],self.at.number('S60_x'),self.at.number('S060_x'),self.at.number('S01_source_hash_current'),self.at.number('s60_x'),self.at.number('S60'),self.at.number(60),self.at.number('S\u0666\u0660_x')),(None,60,60,1,None,None,None,None))
        self.assertEqual(got(head+"    return [('S60_x',True,''),('S060_y',True,'')]\n")[1],'it returned S060_y, whose number is reserved or already taken')   # 60 written another way is 60
        self.assertEqual((self.at.guard(head+rows),self.at.guard('import json\n'+head+rows),sorted(self.at.RESERVED)==list(range(0,60))+list(range(200,210))),(None,None,True))
        self.assertEqual(self.at.module_rows(d/'absent.py',data,self.root,set()),(None,'it cannot be read: FileNotFoundError'))
    def test_a_check_module_runs_in_a_process_of_its_own_which_is_no_sandbox(self):
        # What the process is for: a module's mistakes stay out of the verifier's rows (it has its own memory, its own json, its own copy of the record). It is no sandbox
        # (ruling R31; the end of this test shows a module the parser passes reaching the disk). The modules of the two refuters of round 1 are handed to a process here
        # although the parser refuses their first line (in_child is what module_rows calls after the parser): they find nothing of the verifier or of the caller there.
        data={'cases':[]};handed=self.at.hand_in(data,self.root);rows="    return [('S150_a',True,'')]\n";child=lambda src,seconds=None:self.at.in_child(src,'zz',handed,Path(self.root).anchor,seconds)
        self.assertEqual(child(HEAD+rows),([['S150_a',True,'']],None))
        frames="from hashlib import __builtins__ as b\n"+HEAD+"    g=b['getattr'];s=b['__import__']('sys')\n    for t in g(g(s,'_getframe')(2),'f_locals')['tests']:t['pass']=True\n"+rows   # every row of the verifier set to passed
        kernel="from json import __builtins__ as B\n"+HEAD+"    B['__import__']('kernel.core')\n"+rows                                                                                   # the kernel imported into the verifier
        path="from json import __path__ as w\n"+HEAD+"    w.append(str(ROOT/'kernel'))\n    import json.core as k\n"+rows                                                                # the kernel loaded as json.core
        self.assertEqual([self.at.guard(m)[:11] for m in (frames,kernel,path)],['it imports ']*3)
        self.assertEqual([child(m) for m in (frames,kernel,path)],[(None,'it raised KeyError'),(None,'it raised ModuleNotFoundError'),(None,'it raised ModuleNotFoundError')])
        # a module the parser passes: it swaps json.dumps for one that sets `pass` on a dict that looks like a verdict. In the verifier's process that turned a failed verdict into a
        # passed one after the fact; in its own process it changes nothing the verifier reads: its row comes back as it is, and the verifier's json is the one it was
        patch="import json\n"+HEAD+"    real=json.dumps\n    def dumps(o,*a,**k):\n        if type(o) is dict and 'checks' in o and 'verifier' in o:o['pass']=True\n        return real(o,*a,**k)\n    json.dumps=dumps\n    return [('S150_a',False,'as it is')]\n"
        d=self.tmp();self.assertEqual((self.at.guard(patch),self.at.module_rows(write(d/'zz.py',patch),data,self.root,set()),json.dumps.__module__,self.at.json is json),(None,([('S150_a',False,'as it is')],None),'json',True))
        # what stands in that process beside the parser: built-ins without the refused names, and an import that takes the allowed modules only
        self.assertEqual([child(m) for m in ('import os\n'+HEAD+rows,HEAD+'    import subprocess\n'+rows,HEAD+"    open('x')\n"+rows,HEAD+"    return [('S150_a',True,str(__loader__))]\n",HEAD+"    eval('1')\n"+rows,HEAD+"    getattr(data,'x')\n"+rows)],
                         [(None,'it raised ImportError')]*2+[(None,'it raised NameError')]*4)
        # what the process is started with: no word of the lab's folder, of this copy or of the caller's environment; isolated, without bytecode, in the root of the file system
        peek="from hashlib import __builtins__ as b\n"+HEAD+("    os=b['__import__']('os');sys=b['__import__']('sys')\n"
              "    return [('S150_a',True,b['__import__']('json').dumps([os.getcwd(),dict(os.environ),sys.argv,sys.flags.isolated,sys.dont_write_bytecode,sys.path,sorted(m for m in sys.modules if m.split('.')[0] in ('kernel','tools','extensions','qa'))]))]\n")
        cwd,env,argv,isolated,nobytecode,paths,lab_modules=json.loads(child(peek)[0][0][2])
        self.assertEqual((Path(cwd),argv,isolated,nobytecode,lab_modules,[v for v in list(env.values())+paths+argv if str(ROOT) in v or str(self.root) in v or 'points-' in v]),(Path(Path(self.root).anchor),['-c'],1,True,[],[]))
        self.assertTrue(set(env)<={'LC_CTYPE','__CF_USER_TEXT_ENCODING'},env)   # what the system itself puts there, and nothing the caller had
        # a process that fails, or writes anything else than the one JSON text of its rows, is the module's one failed row
        self.assertEqual([child(m) for m in ("from hashlib import __builtins__ as b\n"+HEAD+"    b['__import__']('os')._exit(3)\n",HEAD+"    print('x')\n"+rows,"from hashlib import __builtins__ as b\n"+HEAD+"    b['__import__']('sys').stdout.write('{}')\n    b['__import__']('os')._exit(0)\n")],
                         [(None,'its process ended with exit code 3'),(None,'it wrote something else to its output than its rows'),(None,'it wrote something else to its output than its rows')])
        self.assertEqual(child(HEAD+'    while True:pass\n',1),(None,'it did not finish within 1 seconds'))
        # Limit 1 of the README, pinned (ruling R31): the parser reads names, and the process is a process of the same user with the lab's rights. A module that reaches the
        # interpreter through an allowed module passes the parser and holds, in its process, the real built-ins and the disk: here it takes them from the globals of json.dumps
        # through functools.update_wrapper (round 3, refuter 2, finding 1), or through the code of a generator (refuter 1, finding 2), and reads a lab file by its full path.
        kernel=str(self.root/'kernel'/'core.py');size=str(len(Path(kernel).read_bytes()));d=self.tmp()
        wrapper=("import functools, json\nKEEP = []\nclass Box:\n    def __setattr__(self, name, value):\n        KEEP.append(value)\n"+HEAD+"    functools.update_wrapper(Box(), json.dumps, assigned=('__globals__',), updated=())\n"
                 "    B = KEEP[0]['__builtins__']\n    return [('S150_a', True, str(len(B['open'](%r, 'rb').read())))]\n")%kernel
        code=(HEAD+"    def probe(x):\n        yield x.aaaa\n    c=probe(None).gi_code\n    def reach(obj,name):return next(type(probe)(c.replace(co_names=(name,)),{})(obj))\n"
              "    b=reach(sha,'__globals__')['builtins'];opener=reach(b,'open')\n    return [('S150_a', True, str(len(opener(%r,'rb').read())))]\n")%kernel
        for src in (wrapper,code):self.assertEqual((self.at.guard(src),self.at.module_rows(write(d/'zz.py',src),data,self.root,set())),(None,([('S150_a',True,size)],None)))
        where=wrapper.split("    B = KEEP[0]")[0]+"    return [('S150_a', True, KEEP[0]['__builtins__']['__import__']('os').getcwd())]\n"   # the same way in, to ask where the process runs: started by module_rows, it stands in the root of the file system, not in the lab
        self.assertEqual(Path(self.at.module_rows(write(d/'zz.py',where),data,self.root,set())[0][0][2]),Path(Path(self.root).resolve().anchor))
        self.assertIn('a check module that reaches the interpreter through an allowed module (through a function that reads an attribute by a name given as text, say) passes the parser and holds, in its process, the real built-ins and the disk',(ROOT/'README.md').read_text())
        self.assertIn('none of them is a sandbox, and a delivery written to deceive is outside what the points claim',(ROOT/'README.md').read_text())
    def test_a_check_module_runs_from_the_text_added_json_lists_read_once(self):
        # Round 3 (refuter 2, finding 1): a module's text is read once and held to the sha256 added.json lists for it, then parsed and run from that same text, and every
        # module's text is read before the first module runs. So what was parsed is what runs, also when a file changes while the verifier is at work.
        first=HEAD+"    return [('S160_first',True,'the first module')]\n";second=HEAD+"    return [('S161_second',True,'as listed')]\n";swapped=second.replace('as listed','swapped')
        root,data=self.lab_copy({'qa/checks/a_first.py':first,'qa/checks/b_second.py':second},self.addCleanup);at=verifier(root);f=root/'qa'/'checks'/'b_second.py';listed=at.listed_files(root)
        said="its text is not the text added.json lists for qa/checks/b_second.py (by sha256); it was not run"
        self.assertEqual((at.module_text(f,listed),at.module_text(f,None),at.module_text(f,{})),((second,None),(None,said),(None,said)))
        write(f,swapped);self.assertEqual(at.module_text(f,listed),(None,said));write(f,second)
        real=at.hand_in
        def swap_then_hand(*a):   # called once, after every module's text was read and before the first module runs: the second module's file changes here
            write(f,swapped);return real(*a)
        at.hand_in=swap_then_hand
        try:rows=at.delivered_rows(data,root)
        finally:at.hand_in=real
        self.assertEqual(([(r['id'],r['pass'],r['detail'],r['from']) for r in rows],f.read_text()),([('S160_first',True,'the first module','qa/checks/a_first.py'),('S161_second',True,'as listed','qa/checks/b_second.py')],swapped))
        self.assertEqual([(r['id'],r['pass'],r['detail']) for r in at.delivered_rows(data,root)],[('S160_first',True,'the first module'),('qa/checks/b_second.py',False,said)])   # read again, the file is not the listed text: not run
    def test_the_verifier_writes_a_failed_verdict_when_it_has_no_record_to_read(self):
        d=self.tmp();write(d/'qa'/'independent_verify.py',(ROOT/'qa'/'independent_verify.py').read_bytes())
        ran=subprocess.run([sys.executable,'-I','-B',str(d/'qa'/'independent_verify.py')],capture_output=True,text=True);verdict=json.loads((d/'qa'/'independent_verification.json').read_text())
        self.assertEqual((ran.returncode,verdict['pass'],verdict['passed'],verdict['total'],verdict['checks']),(1,False,0,1,[{'id':'the_record_could_not_be_checked','pass':False,'detail':'FileNotFoundError'}]))
        self.assertIn('0 / 1 independent local checks FAIL',ran.stdout)
        write(d/'results'/'actual_run_records.json','{"cases":[]}');write(d/'kernel'/'core.py',(ROOT/'kernel'/'core.py').read_bytes())   # a record the checks cannot read
        ran=subprocess.run([sys.executable,'-I','-B',str(d/'qa'/'independent_verify.py')],capture_output=True,text=True)
        self.assertEqual((ran.returncode,json.loads((d/'qa'/'independent_verification.json').read_text())['checks'][0]['detail'],'Traceback' in ran.stderr),(1,'KeyError',False))
    def test_what_no_pin_and_no_check_holds_passes_the_whole_verifier(self):
        # Limits 3 and 12 of the README, pinned (round 4: refuter 2, findings 1 and 5; refuter 1, finding 3; settled without new code).
        # (a) Checked like the built-in ones, by its letter: S200 holds an added case to its file's packs, words and expected status, and the base's checks read its runs like any
        # other. What those checks leave open for a built-in case (the verifier's own comment lists it) is open for an added case too. (b) S202 holds what is pinned. The
        # reflection summary is never pinned and cannot be declared; the record's scope line and a key added at its top are pinned by nothing; the implementation lenses are
        # compared only while the declared kinds are the pinned ones. So an edit version can move these for the older cases too, without declaring it: here the book holds an
        # edit version the pins do not hold yet, which declares nothing, all of it is moved at once, and the whole verifier passes; S202's detail names the files and no move.
        case=lambda d:[c for c in d['cases'] if c['id']=='900_demo'][0];both=lambda d,**k:(case(d)['outcome'].update(k),case(d)['run']['runs'][-1].update(k))
        open_for_an_added_case=(('its scope',lambda d:case(d).update(scope='orgB/elsewhere')),('a key added to it',lambda d:case(d).update(note='x')),('a key added to its books',lambda d:case(d)['derived_state'].update(note='x')),
                                ('a key added to its views',lambda d:case(d)['four_views'].update(note='x')),('its world and knowledge views',lambda d:case(d)['four_views'].update(world=[],knowledge=[])),
                                ("its run block's own status and goals",lambda d:case(d)['run'].update(status='ALL_GOALS_MET',goals=[])),('the rule ids of its derived state',lambda d:case(d)['derived_state'].update(rule_ids=[])),
                                ('the proof of its run',lambda d:both(d,proof=[{'x':1}])),("the record's scope line",lambda d:d.update(scope='another claim')),('a key added to the record',lambda d:d.update(note='x')))
        beside_the_pins=(('the reflection summary',lambda d:d['meta_extensions']['reflection'].update(note='another summary',candidate_count=99)),("the record's scope line",lambda d:d.update(scope='another claim')),
                         ('a key added at the top of the record',lambda d:d.update(note='x')),('an implementation lens, while the declared kinds are not the pinned ones',lambda d:d['meta_extensions']['implementation_website'].update(note='x')))
        why=lambda d:self.at.pinned_why(d,self.root);keep=(self.root/'added.json').read_bytes();rel='extensions/reflection.py'
        def book(*moves):   # the copy's book with an edit version the pins do not hold yet: it changed two files and declares `moves`
            b=json.loads(keep);b['applied'].append(dict({'label':'0.0.1-edit','delivery':'edit','files':{},'edits':{'script':'apply.py','sha256':'0'*64,'files':{rel:['1'*64,sha_file(self.root/rel)],'tools/run_all.py':['3'*64,'4'*64]}}},**({'moves':[{'what':w,'why':'a reason'} for w in moves]} if moves else {})))
            write(self.root/'added.json',json.dumps(b));return b
        try:
            pin=book()['pinned'];self.assertEqual(('reflection' in pin['meta_extensions'],pin['kinds'],[f.stem for f in self.at.plug(self.root/'kinds','.py')[0]]),(False,[],['demo_stamp']))   # this lab holds a kind the pins do not
            for what,change in beside_the_pins:self.assertEqual(why(self.forged(change)),[],what)   # S202, each alone: it holds, and the edit version in the book declares nothing
            self.assertEqual(why(self.forged(lambda d:d['meta_extensions']['stage_boundary'].update(note='x'))),['the lens stage_boundary is not the pinned one'])   # the control: a lens that is pinned
            moved=self.forged(lambda d:([change(d) for _,change in open_for_an_added_case+beside_the_pins[:1]],d.update(release='sutra-kernel-extensions/0.0.1-edit')))   # all of it at once (an implementation lens with a key more fails its own built-in check: left out here)
            res=self.at.inspect(moved);row=[t for t in res['checks'] if t['id']==S202][0]
            self.assertEqual((failed(res),res['pass'],row['pass'],row['detail']),([],True,True,'the edit version 0.0.1-edit changed extensions/reflection.py, tools/run_all.py (added.json records the sha256 of each before and after)'))
            self.assertEqual(self.at.added_cases_why(self.forged(lambda d:case(d).update(title='Another title')),self.root,BUILT_IN_CASES),['900_demo: the record has another title'])   # the control: what S200 does hold of an added case
            # the reflection summary can be neither held nor declared: the applier refuses `lens reflection` in a manifest (it is not pinned); written into the book by hand,
            # it is a declaration of a thing that has not moved, whatever the summary reads
            book('lens reflection');stale=['lens reflection is declared as moved by the edit version 0.0.1-edit and has not moved']
            self.assertEqual((why(self.demo),why(self.forged(beside_the_pins[0][1]))),(stale,stale))
        finally:write(self.root/'added.json',keep)
        self.assertEqual(why(self.demo),[])
        readme=(ROOT/'README.md').read_text()
        self.assertIn("a case's title, description, area, scope, its run block's own status and",(ROOT/'qa'/'independent_verify.py').read_text())   # the verifier's own comment on what it does not check of a built-in case
        self.assertIn("is open for an added case too: its scope, a key added to it, to its books or to its views, its world and knowledge views, its run block's own status and goals, the rule ids of its derived state and the proof of its run pass every check, and so do the record's scope line and a key added to the record",readme)
        self.assertIn("S202 does not hold three parts of the older record: the reflection summary, which is never pinned (a manifest cannot declare it as moved either); the record's scope line and any key added at the top of the record, which nothing pins; and, when an edit version also brings a kind file, the three implementation lenses, which are compared only while the declared kinds are the pinned ones",readme)
    def test_the_detail_of_S202_is_cut_at_2000_characters_and_names_only_the_first_declared_moves(self):
        # Limit 10 of the README, pinned (round 4, refuter 2, finding 2; settled without new code): the verifier cuts the detail of each of the points' five checks at 2000
        # characters (one line of its tail). The detail of S202 says first what is wrong, then, for every edit version the pins do not hold yet, the files it changed and the moves
        # it declares. An edit version that moves many cases (a kernel version, say) has only the first of its declared moves named in the verdict, and nothing says that the list
        # was cut. added.json holds every move.
        self.assertEqual((ROOT/'qa'/'independent_verify.py').read_text().count("check(cid,not why,'; '.join(why+said)[:2000])"),1)   # the line that cuts: the five checks of the points go through it
        keep=(self.root/'added.json').read_bytes();b=json.loads(keep);ids=[c[0] for c in b['pinned']['cases']];reason='its description is reworded'
        b['applied'].append({'label':'0.0.1-edit','delivery':'edit','files':{},'edits':{'script':'apply.py','sha256':'0'*64,'files':{'tools/run_all.py':['1'*64,'2'*64]}},'moves':[{'what':'case '+cid,'why':reason} for cid in ids]})
        def reworded(d):
            for c in d['cases']:
                if c['id'] in ids:c['description']+=' (reworded)'
        write(self.root/'added.json',json.dumps(b))
        try:
            d=self.forged(reworded);said=self.at.edits_said(self.root);whole='; '.join(said)
            self.assertEqual((self.at.pinned_why(d,self.root),len(said),len(ids),len(whole)>2000),([],1+len(ids),BUILT_IN_CASES,True))   # every pinned case moved and every move is declared: the check holds
            row=[t for t in self.at.inspect(d)['checks'] if t['id']==S202][0];named=[cid for cid in ids if 'applied: case '+cid+' ('+reason+')' in row['detail']]
            self.assertEqual((row['pass'],row['detail'],len(row['detail']),named==ids[:len(named)],0<len(named)<len(ids)),(True,whole[:2000],2000,True,True))   # the first 2000 characters and nothing after them: no word says that the list was cut
            self.assertEqual([m['what'] for m in json.loads((self.root/'added.json').read_text())['applied'][-1]['moves']],['case '+cid for cid in ids])   # the book holds every move
            b['applied'][-1]['moves'].pop(0);write(self.root/'added.json',json.dumps(b))   # one move not declared: what is wrong stands first in the detail, and the detail is cut all the same
            row=[t for t in self.at.inspect(d)['checks'] if t['id']==S202][0];first='case '+ids[0]+' is not the pinned case'
            self.assertEqual((self.at.pinned_why(d,self.root),row['pass'],row['detail'],len(row['detail'])),([first],False,'; '.join([first]+self.at.edits_said(self.root))[:2000],2000))
        finally:write(self.root/'added.json',keep)
        self.assertEqual((self.at.pinned_why(self.demo,self.root),self.at.edits_said(self.root)),([],[]))
        self.assertIn('the detail of S202 is cut at 2000 characters, as the detail of each check of the points is: it says first what is wrong and then, for each edit version the pins do not hold yet, the files it changed and the moves it declares, and it ends there without a word, so of a long list of moves only the first are named in the verdict, and `added.json` holds every one',(ROOT/'README.md').read_text())


if __name__=='__main__':unittest.main()
