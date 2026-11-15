"""Independent local trace and artifact verifier. MUST NOT import kernel/core or extensions."""
from __future__ import annotations
import json,hashlib,sys,re,ast,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'results'/'actual_run_records.json'

def sha(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def check_chain(trace):
    for i,row in enumerate(trace):
        if not held('seq',type(row['seq']) is int) or row['seq']!=i+1:return False   # a whole number by type: true is not 1 and 2.0 is not 2
        if row['prev_sha256'] != (trace[i-1]['sha256'] if i else 'GENESIS'):return False
        if row['sha256']!=sha({k:v for k,v in row.items() if k!='sha256'}):return False
    return True

# 0.9.0-stop: what a stopped run and a case's books are held to. Module level, so the unit tests can run them on stops made in memory.
PHRASES=('Gate changed before effect: ','Prerequisite not true before effect: ','Handler refused: ','Handler failed: ','Kernel fault: ');RETURNED='Handler returned what cannot be a receipt'
RANK=('SEMANTICS_MISSING','SEMANTICS_UNAPPROVED','EVIDENCE_CONFLICT','REFUSED','QUERY_EVIDENCE','AUTHORITY_REQUIRED','PROVIDER_REQUIRED','RESOURCE_REQUIRED','METHOD_ABSENT','CYCLE_LIMIT')   # the verifier's own copy of the kernel's ten stop reasons, in the kernel's order
def block_ok(b):   # a BLOCK row against the ranking: every reason is one of the ten, each once and in order, and the row is named by the first in rank (METHOD_ABSENT when there is none: the kernel's own fallback, which the kernel reaches only on a State changed by hand, so a forged blocked run that names no reason at all passes; a stated limit)
    alls=b.get('all_reasons')
    return held('rank',type(alls) is list and all(type(x) is str and x in RANK for x in alls) and alls==sorted(set(alls)) and b.get('reason')==next((x for x in RANK if x in alls),'METHOD_ABSENT'))
OFF=set()   # checks switched off by name. Only S49 and S50 do that, to show that each check is the one that refuses its forgery
def held(name,ok):return name in OFF or bool(ok)
STEPS=('SELECT','BLOCK','ADMISSION','LOCAL_EFFECT','STEP_ALREADY_TRUE','STEP_STOPPED')   # the rows the kernel writes for a plan and its steps: a stop row is the last of them, and the kinds settle after them
def name_ok(text):return type(text) is str and text.isascii() and text.isidentifier()   # what the kernel writes for an error's class: one plain name of ASCII letters, digits and underscores that does not start with a digit and is not empty ('unreadable' when the class has none)

def said(text,needs):   # the text names one or more of the step's prerequisites, in their order, joined by single spaces (a name may hold a space itself, and may be the empty text)
    ends={(0,False)}   # how far the text is read, and whether a name was read
    for n in needs:ends|={(e+begun+len(n),True) for e,begun in ends if text[e+begun:].startswith(n) and (not begun or text[e:e+1]==' ')}
    return (len(text),True) in ends

def stop_ok(r,methods,kinds=None):
    """A run against the shape of a stop. A SETTLE_STOPPED row has two fields, the kind (one of `kinds`, the registry, when that is given; no kind twice) and one plain name for the
    error; it stands after every row of the plan and its steps; a plan that was only offered has none; and `unsettled` names the kinds of these rows, in their order. A STEP_STOPPED
    row has its three fields; its reason is a phrase of the closed list (the facts of a prerequisite stop are prerequisites of the stopped step; a failed handler and a kernel fault
    are named by one plain name; a handler's own words are held to nothing); it is the last row of the plan and its steps; and it stands right after the stopped step's own gate row,
    whose verdict it repeats. One exemption: a kernel fault may stand right after a row of the plan instead (SELECT, LOCAL_EFFECT, STEP_ALREADY_TRUE), because the kernel can fail
    before a step reaches its gate (its method is gone, say). Not caught here, each a stated limit that a unit test pins: a stop whose gate admitted the step, re-worded with any other phrase of the
    list that is not a gate's, with its gate row left in (the gate row says only that the step was admitted) or, as a kernel fault, taken out; the facts a prerequisite stop names, which
    are held to the step's prerequisites and not to what the stored rows read; a SETTLE_STOPPED row invented for a kind of the registry, or taken out together with its name under
    `unsettled` (the record says neither which kinds have a settle hook nor whether a blocked look was dry); and a stop re-told as a completed run (its stop row replaced by a
    STEP_ALREADY_TRUE row: this function then sees no stop to hold)."""
    t=r['trace'];ops=[e['operation'] for e in t];rows=[e['data'] for e in t if e['operation']=='SETTLE_STOPPED'];names=[x.get('kind') for x in rows];last=max([i for i,op in enumerate(ops) if op in STEPS],default=-1)
    if not held('unsettled',r.get('unsettled',[])==names and ('unsettled' in r)==bool(names) and all(set(x)=={'kind','reason'} and type(x['kind']) is str and (kinds is None or x['kind'] in kinds) and name_ok(x['reason']) for x in rows)
                and len(set(names))==len(names) and (not names or (r.get('work_state')!='ready' and ops.index('SETTLE_STOPPED')>last))):return False
    if 'STEP_STOPPED' not in ops:return True
    i=ops.index('STEP_STOPPED');stop=t[i]['data'];why=stop.get('reason');gate=t[i-1];needs=methods.get(stop.get('method'),{}).get('requires',[])
    if not held('shape',set(stop)=={'method','reason','effect_reads'} and type(why) is str and stop['effect_reads'] in ('TRUE','FALSE','UNKNOWN')):return False
    if not held('reason',why==RETURNED or (any(why.startswith(p) for p in PHRASES) and (not why.startswith(PHRASES[1]) or said(why[len(PHRASES[1]):],needs)) and all(name_ok(why[len(p):]) for p in PHRASES[3:] if why.startswith(p)))):return False
    own=gate['operation']=='ADMISSION' and gate['data'].get('methods')==[stop.get('method')]
    agrees=(gate['data'].get('accepted') is False and why==PHRASES[0]+' '.join(gate['data'].get('blockers',[]))) if why.startswith(PHRASES[0]) else gate['data'].get('accepted') is True
    return held('gate',i==last and ((own and agrees) or (why.startswith(PHRASES[4]) and gate['operation'] in ('SELECT','LOCAL_EFFECT','STEP_ALREADY_TRUE'))))

def stored(packs):
    """What a case's pack files leave in the books before any run: the rows stored (scope|fact -> row) and the rows a standing decision turned away, in order. The verifier's own copy
    of the kernel's rule for a row: a pack names the scope before its rows; a row that is not verified is ignored; a decision stands until another decision replaces it."""
    scope,rows,away='orgA/fulfillment',{},[]
    for p in packs:
        scope=p.get('scope',scope)
        for o in p.get('evidence',[]):
            at=o.get('scope',scope);key=at+'|'+o['predicate']
            if o.get('verified',False) and rows.get(key,{}).get('final') and not o.get('final'):away.append({'status':'DECISION_STANDS','scope':at,'predicate':o['predicate']})
            elif o.get('verified',False):rows[key]=dict(o,scope=at)
    return rows,away

def standing(facts,scope,fact,seen=()):
    """The stored row a fact reads from in a scope, or None when no valid row stands (the fact then reads UNKNOWN). The verifier's own copy of the kernel's rule for a reading:
    a row counts when it is verified and every row it rests on reads TRUE at the version it names (versions compare as JSON text); a fact that rests on itself reads UNKNOWN."""
    row=facts.get(scope+'|'+fact)
    if fact in seen or type(row) is not dict or row.get('verified') is not True:return None
    for dep in row.get('depends_on',[]):
        other=standing(facts,scope,dep['predicate'],seen+(fact,))
        if other is None or other.get('truth')!='TRUE' or sha(other.get('version'))!=sha(dep.get('version')):return None
    return row
def reading(facts,scope,fact):return (standing(facts,scope,fact) or {'truth':'UNKNOWN'})['truth']

def books_ok(case,methods,packs):
    """A case's books against its runs and pack files. The budget left is the packs' budget less the cost of the receipts. The journal begins with the rows the packs turned away
    and holds one row per run, in order, with the run's status and trace root; any other row in it is a row turned away during a run, on a fact that carries a decision. The
    candidates counted are the ones the last run lists, each cited by a receipt. The stored facts are the rows the packs left, except on the effect of a step that ran or stopped:
    that row is its handler's to write (it may not be gone where the packs left one). And what the stop row of the case's last run says its effect reads, and what that run says
    its goal reads, is exactly what the stored rows read. Not held: what an earlier run of the same case says its effect and its goal read (the books keep the facts as they stood
    at the end of the case); the handler's row itself; and whether a row said to be turned away during a run was."""
    runs=case['run']['runs'];book=case['derived_state'];facts=book['facts'];journal=book['historical_events'];left={'compute':10,'money':10,'attention':3};receipts=[x for r in runs for x in r['model_receipts']]
    for p in packs:left.update(p.get('budget',{}))
    for x in receipts:
        for dim,v in methods[x['method']].get('cost',{}).items():left[dim]-=v
    rows,away=stored(packs);made=runs[-1].get('candidates',[]) if runs else [];cited={x.get('candidate_sha256') for x in receipts}
    halts=[(r,e['data']) for r in runs for e in r['trace'] if e['operation']=='STEP_STOPPED'];effect=lambda mid:str(methods.get(mid,{}).get('effect'))
    own={r['scope']+'|'+effect(x['method']) for r in runs for x in r['model_receipts']}|{r['scope']+'|'+effect(stop.get('method')) for r,stop in halts}   # the facts a handler was called to make
    told=all(stop.get('effect_reads')==reading(facts,r['scope'],effect(stop.get('method'))) and r.get('goal_truth_after')==reading(facts,r['scope'],r['goal']) for r,stop in halts if r is runs[-1])
    turned=lambda j:set(j)=={'status','scope','predicate'} and j['status']=='DECISION_STANDS' and type(j['scope']) is str and type(j['predicate']) is str and (facts.get(j['scope']+'|'+j['predicate']) or {}).get('final') is True
    return (held('budget',sha(book['budget_after'])==sha(left))
            and held('journal',sha(journal[:len(away)])==sha(away) and sha([j for j in journal if 'goal' in j])==sha([{'goal':r['goal'],'scope':r['scope'],'status':r['status'],'trace_root_sha256':r['trace_root_sha256']} for r in runs])
                     and all('goal' in j or turned(j) for j in journal))
            and held('candidates',sha(book['candidate_count'])==sha(len(made)) and all(sha(c) in cited for c in made))
            and held('facts',all(key in facts and (key in own or sha(facts[key])==sha(rows.get(key))) for key in set(facts)|set(rows)))
            and held('effect',told))

# ---- Add-on points (0.10.0): what a later version adds as files. The verifier's own rules, readers and checks for it; module level, so the unit tests can run them.
PLAIN=r'[0-9a-z][0-9a-z_]*'   # the name of an add-on file before its suffix: digits, small letters and underscores, beginning with a digit or a letter
KIND_FILES={'simulate_fact':'kernel/core.py','compile_candidate':'extensions/constructor.py','emit_artifact':'extensions/constructor.py','ask':'extensions/asks.py'}   # the four action kinds of the lab itself, each with the file its handler lives in
BUILT_IN_KINDS=tuple(KIND_FILES)   # a later version declares more, one file each, in kinds/; no kind file may be named like one of these
ALLOWED=('__future__','collections','copy','functools','hashlib','html','itertools','json','math','re')   # all that a check module may import
FORBIDDEN=('__builtins__','__import__','breakpoint','compile','delattr','eval','exec','exit','getattr','globals','input','locals','open','quit','setattr','vars')   # built-in names a check module may not use: they load or run code, open files, or reach into an object by a name given as text
DUNDERS=('__contains__','__doc__','__eq__','__getitem__','__init__','__len__','__name__','__setitem__')   # the only attribute names beginning with an underscore that it may use
REACH=('ag_frame','attrgetter','builtins','cr_frame','f_back','f_builtins','f_globals','f_locals','gi_frame','methodcaller','modules','os','sys','tb_frame')   # attribute names that lead to frames, to modules, or to an attribute by a name given as text
RESERVED=set(range(0,60))|set(range(200,210))   # S01 to S59 are the numbers of the built-in checks (0 goes with them), S200 to S209 those of the add-on points: no delivered check may use them

def number(cid):   # the number of a check id of the form S<number>_<words>, in ASCII digits; None for any other id
    m=re.fullmatch(r'S([0-9]+)_[A-Za-z0-9_]+',cid) if type(cid) is str else None
    return int(m.group(1)) if m else None

def guard(src):
    """Why the text of a check module is not run, or None when it is. The text is parsed, not searched: a word in a comment or in a string refuses nothing, and an
    import is found wherever it stands (after a comma, a semicolon or a colon, inside a function). Refused: an import of anything outside ALLOWED; from an allowed module, a
    star, a name that begins with an underscore, or a name in FORBIDDEN or REACH (so no `from json import __builtins__`); the built-in names in FORBIDDEN, as a name or as an
    attribute (`re.compile` alone is let through); any other name written with two underscores at both ends, except __name__ and __doc__ (so no __loader__, no __spec__);
    an attribute in REACH; an attribute that begins with an underscore and is not in DUNDERS; a module without a top-level checks(). This is a guard against mistakes (a
    check module that imports the lab, opens a file, prints into the verifier), and NOT a sandbox: it reads NAMES, so a module that reaches the same things without
    naming them (through a function of an allowed module, say) passes it and is run (ruling R31; a unit test of the points pins it)."""
    try:tree=ast.parse(src)
    except (SyntaxError,ValueError,RecursionError,MemoryError):return 'it is not Python that can be parsed'
    only=' (a check module may import only '+', '.join(ALLOWED)+')'
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            names=[a.name for a in node.names]
            if any(n.split('.')[0] not in ALLOWED for n in names):return 'it imports '+', '.join(names)+only
        elif isinstance(node,ast.ImportFrom):
            if node.level or (node.module or '.').split('.')[0] not in ALLOWED:return 'it imports '+(node.module or '.')+only
            odd=[a.name for a in node.names if a.name=='*' or a.name.startswith('_') or a.name in FORBIDDEN or a.name in REACH]
            if odd:return 'it imports '+', '.join(odd)+' from '+node.module+' (from a module it takes public names one by one: no star, no name that begins with an underscore, none of the refused names)'
        elif isinstance(node,ast.Name) and (node.id in FORBIDDEN or (node.id.startswith('__') and node.id.endswith('__') and node.id not in ('__name__','__doc__'))):return 'it names '+node.id
        elif isinstance(node,ast.Attribute) and (node.attr in REACH or node.attr in FORBIDDEN or (node.attr.startswith('_') and node.attr not in DUNDERS)):
            if not (node.attr=='compile' and isinstance(node.value,ast.Name) and node.value.id=='re'):return 'it reaches for .'+node.attr
    if not any(isinstance(n,ast.FunctionDef) and n.name=='checks' for n in tree.body):return 'it defines no checks(data, ROOT, sha, check_chain)'
    return None

def moved_cases(pinned,now):
    """What a record's cases no longer hold of the cases that were pinned: (the ids that are not the pinned case, the ids that stand out of the pinned order). `pinned` is the
    list of [id, sha256] that added.json keeps, in the order the record held the cases when they were pinned; `now` is the same list made of a record's cases. A pinned case
    is found BY ITS ID, never by its place: the record holds that id once, with the pinned sha256. Cases that are not pinned may stand anywhere among the pinned ones: the
    build runs the added cases in file order, so a later version's case stands before an earlier version's whenever its id sorts first (100_x before 50_y, 51_b before 60_a),
    and versions can be applied in any order of case ids. What does stay is the order of the pinned cases among themselves (a part of a list sorted by name is sorted the
    same way): a pinned case that stands before one that was pinned ahead of it is named in the second list."""
    changed=[cid for cid,h in pinned if [h2 for cid2,h2 in now if cid2==cid]!=[h]]
    kept=[(cid,[i for i,(cid2,_) in enumerate(now) if cid2==cid][0]) for cid,h in pinned if cid not in changed]
    return changed,[cid for n,(cid,place) in enumerate(kept) if any(place<before for _,before in kept[:n])]

WHAT=r'(?:case|scenario|sequence|lens) [0-9a-z][0-9a-z_@.-]*|events|ask_events'   # what an edit version may declare as moved: a thing added.json pins, named by its kind and its name (`case 30_stop`, `scenario 04_admission`, `sequence demo`, `lens j2_projection`), or one of the two records

def unpinned(book):
    """The versions the pins do not hold yet: the entries of `applied` in added.json after the one whose built record the pins were taken from (`pinned.from` is that
    record's release label); every entry when the pins are from the base the points were given to. The pins are taken again whenever a version is applied to the built,
    verified record of the version before it, so as a rule this is the one version that is being built."""
    labels=['sutra-kernel-extensions/'+str(e.get('label')) for e in book['applied']];of=book['pinned']['from']
    return book['applied'][len(labels)-labels[::-1].index(of):] if of in labels else list(book['applied'])

def declared_moves(book):
    """What the edit versions the pins do not hold yet declare as moved: {what: (the version's label, the reason it gives)}. An edit version (ruling R32) is a delivery
    that changes existing files and says so in its manifest; what it moves of the things an earlier version recorded, it declares there, each with a reason (`moves`).
    A declared move is held to nothing while its version is not pinned yet; once the next version is applied to the built, verified record, the pins hold the moved
    thing as it then stands and the declaration is history. Only what a manifest may name is taken (WHAT): the kernel and the handler entries are never declared, the
    applier takes their pins again for the files an edit version changed. WHAT is wider than the pins: `lens reflection` reads like a move, but the reflection
    summary is never pinned, so the applier refuses that declaration and S202 would call it a move of a thing that has not moved."""
    return {m['what']:(e['label'],m['why']) for e in unpinned(book) for m in e.get('moves',[]) if type(m.get('what')) is str and re.fullmatch(WHAT,m['what'])}

def case_of(stem,text):
    """The case a file of cases/ holds, or None when it is no case file: a JSON object with exactly the seven keys, each of its type, in a file named after the id."""
    try:c=json.loads(text)
    except (ValueError,RecursionError):return None
    ok=(type(c) is dict and set(c)=={'id','title','description','packs','execute','area','expected'} and c['id']==stem and type(c['execute']) is bool
        and all(type(c[k]) is str and c[k] for k in ('title','description','area','expected')) and type(c['packs']) is list and all(type(n) is str and n for n in c['packs']))
    return c if ok else None

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

PLACES=(('cases','.json'),('tools/packs','.py'),('tools/scenes','.py'),('kinds','.py'),('extensions','.py'),('tests','.py'),('qa/checks','.py'))   # the seven places a later version adds files to
CODE=('.py','.pyc','.pyo','.pyd','.pyw','.pyz','.so','.pth','.dylib','.dll')   # the suffixes of what Python can load as code: a file with one of them, anywhere in the lab, is named like one the lab had before or is one added.json lists
CHECK_SECONDS=120   # how long one delivered check module may take before it is stopped and counted as one failed row
PLACED=('README.md','tools/run_all.py')   # the two files of the lab in which the applier places words at every application (the README's title, label, passage and counts, which the build then fills; the label line of tools/run_all.py): their content moves with every version

def plug(folder,suffix):
    """The add-on files of one place in name order, and the names of everything else found there (a hidden file, a draft, a folder, a link, another suffix). The lab's
    tools refuse to build with such a name; this verifier names it in a failed check."""
    found=sorted(folder.iterdir()) if folder.is_dir() else []
    good=[f for f in found if f.is_file() and not f.is_symlink() and f.suffix==suffix and re.fullmatch(PLAIN,f.stem)]
    return good,[f.name for f in found if f not in good and f.name!='__pycache__']

def added_cases(root):
    """The cases a later version added (cases/<id>.json) in file order, and the names in that folder that are no case file."""
    files,odd=plug(root/'cases','.json');cases=[]
    for f in files:
        try:c=case_of(f.stem,f.read_text(encoding='utf-8'))
        except (OSError,ValueError):c=None
        if c is None:odd.append(f.name)
        else:cases.append(c)
    return cases,odd

def runs_under(v):return looks_and_runs(v)['runs']   # every run under a part of the record, found by its shape (a dict that carries a trace and a trace root) wherever it sits

# The checks of the add-on points. Each returns what is wrong as a list of sentences, empty when the check holds; a record or a file it cannot read is one sentence too.
# What the points claim, and no more (rulings R31 and R32 of the Core Algorithm program): a delivery edits no existing file unless it is an edit version, which says so in
# its manifest, is recorded as one with the hashes of what it changed, and is reviewed as every kernel version is; what earlier versions recorded stays byte-identical,
# pinned by id, except what an edit version declares as moved; every added part is in the record and is checked like the built-in ones. Added files are reviewed code
# that runs with the lab's rights: these checks and the guards beside them are for an honest author's mistakes, and a delivery written to deceive is outside what they claim.
# What the checks leave open is said in the docstring of each (Not held here) and, numbered, among the known limits of the README.
def kinds_why(handlers,root):
    """S41, as the points hold it. The record's handlers are those of the four built-in kinds plus the kinds declared in kinds/ (no kind file is named like a built-in
    kind); each built-in kind is held to the file and module its handler lives in (KIND_FILES), a declared kind to kinds/<kind>.py. The check itself then holds every
    file named to its sha256."""
    try:
        declared=[f.stem for f in plug(root/'kinds','.py')[0]];why=['kinds/'+n+'.py is named like a built-in action kind' for n in declared if n in KIND_FILES]
        want=dict({n:'kinds/'+n+'.py' for n in declared},**KIND_FILES)
        if sorted(handlers)!=sorted(want):return why+['the record holds handlers for '+str(sorted(handlers))[:300]+' and the kinds are '+str(sorted(want))[:300]]
        return why+[k+': the record says its handler lives in '+str(handlers[k].get('file'))[:80]+' (module '+str(handlers[k].get('module'))[:80]+'), not in '+want[k]
                    for k in sorted(want) if handlers[k].get('file')!=want[k] or handlers[k].get('module')!=want[k][:-3].replace('/','.')]
    except Exception as e:return ['the handlers cannot be read: '+type(e).__name__]

def added_cases_why(data,root,built_in):
    """S200. Every added case is one file named after its id. After the built-in cases the record holds exactly the cases of these files, each once and each FOUND BY ITS
    ID, with its file's packs, title, description, area and expected status; and they stand there in file order, which is the order the build runs them in (by file name,
    whatever the order the versions were applied in: a later version's case stands before an earlier version's when its id sorts first).
    Not held here, nor by a built-in check (they read an added case's runs like any other, and leave open for it what they leave open for a built-in case): the case's
    scope, a key added to the case, to its books or to its views, its world and knowledge views, its run block's own status and goals, the rule ids of its derived state
    and the proof of its run; nor the record's scope line or a key added to the record. A version's own checks hold what they name. A unit test of the points pins it."""
    try:
        more,odd=added_cases(root);why=['cases/'+n+' is no case file' for n in odd];cols=('packs','title','description','area','status')
        rest=data['cases'][built_in:];ids=[c['id'] for c in rest];want=[m['id'] for m in more]
        if sorted(ids)!=sorted(want) or len(set(ids))!=len(ids):return why+['after the built-in cases the record holds '+str(ids)[:300]+' and the case files are '+str(want)[:300]]
        by={c['id']:c for c in rest}
        for m in more:
            c=by[m['id']];got=(c['packs'],c['title'],c['description'],c['area'],(c['outcome'] or c['run'])['status'])
            why+=[m['id']+': the record has another '+cols[i] for i,w in enumerate((m['packs'],m['title'],m['description'],m['area'],m['expected'])) if sha(got[i])!=sha(w)]
        if ids!=want:why.append('after the built-in cases the record holds the added cases as '+str(ids)[:300]+'; in file order they are '+str(want)[:300])
        return why
    except Exception as e:return ['the added cases cannot be read: '+type(e).__name__]

def scenes_why(data,root,run_ok):
    """S201. The recorded sequences are the scene files, name for name (tools/scenes/<name>.py -> scenes.<name>), and none is empty. What holds what:
    the SEAL (the sha256 of the sequence as it was recorded, kept in the record) shows a change made to the sequence alone, and no more: it is a checksum in the same
    record, and whoever changes the sequence can make it again; the SCENE FILE states how many looks and how many runs its sequence records (LOOKS, RUNS; scene_says),
    and the record is held to these two numbers, so a look or a run taken out, or a run stripped of what makes it one, shows even with the seal made again; EVERYTHING
    THAT LOOKS LIKE A RUN (an item of a `runs` list, a dict with a `trace`) must be a whole run, and every run, wherever it sits, agrees with its trace and its packs
    like any other run (`run_ok`, the check of S42). Not held here: which run stands where, what a sequence keeps beside its runs (snapshots, labels), and a sequence
    re-made from end to end with as many looks and runs (also one in which a run was swapped for a copy of another recorded run): the unit test that makes the record
    again holds those, and a version's own checks."""
    try:
        files,odd=plug(root/'tools'/'scenes','.py');names=[f.stem for f in files];scenes=data.get('scenes',{});why=['tools/scenes/'+n+' is no scene file' for n in odd]
        if type(scenes) is not dict or sorted(scenes)!=names or ('scenes' in data)!=bool(names):return why+['the record holds the sequences '+str(sorted(scenes) if type(scenes) is dict else type(scenes).__name__)[:300]+' and the scene files are '+str(names)[:300]]
        seals=data['added']['scenes']
        if sorted(seals)!=names:why.append('the record seals '+str(sorted(seals))[:300])
        for f in files:
            n=f.stem;made=scenes[n]
            if seals.get(n)!=sha(made):why.append(n+': the sequence is not the one that was sealed')
            if type(made) is not dict or not made:
                why.append(n+': the sequence holds nothing, or is no object');continue
            found=looks_and_runs(made)
            try:said=scene_says(f.read_text(encoding='utf-8'))
            except (OSError,ValueError):said=None
            if said is None:why.append(n+': its scene file does not state LOOKS and RUNS')
            elif said!=(found['looks'],len(found['runs'])):why.append(n+': its scene file says LOOKS = '+str(said[0])+' and RUNS = '+str(said[1])+'; the record holds '+str(found['looks'])+' looks and '+str(len(found['runs']))+' runs')
            if found['odd']:why.append(n+': '+str(found['odd'])+' of what looks like a run is no whole run (an item of a `runs` list, or a dict with a `trace`, without both `trace` and `trace_root_sha256`)')
            for i,r in enumerate(found['runs']):
                try:ok=run_ok(r)
                except Exception:ok=False
                if not ok:why.append(n+': run '+str(i+1)+' does not agree with its trace and its packs')
        return why
    except Exception as e:return ['the recorded sequences cannot be read: '+type(e).__name__]

def pinned_why(data,root):
    """S202. What an earlier version recorded has not moved. added.json pins, from the record that stood when a version was applied: the kernel, every scenario file,
    every case, the event record, the ask record, every recorded sequence, every handler entry (the kind's module, file and that file's sha256) and every lens of
    meta_extensions. Each is compared here with the rebuilt record and the files, by sha256. A pinned case is found BY ITS ID, never by its place (moved_cases): the
    record holds its id once, with the pinned sha256, and the pinned cases stand in the order they were pinned in; a case that is not pinned may stand anywhere among
    them, so a later version may bring a case whose id sorts before a case an earlier version added. Two kinds of lens are by design about the whole lab, not about an
    earlier version: the reflection summary is a summary over all cases (it moves with an added case that runs a plan) and is never pinned; the three implementation
    lenses name every registered action kind, so they are compared only while the kinds declared in kinds/ are the ones that stood when they were pinned.
    AN EDIT VERSION (ruling R32) is a delivery that changes existing files and says so in its manifest. The applier records it in added.json with the sha256 of every
    file it changed, before and after, and takes the pin of the kernel and the pinned handler entries again for those files; every other pin stays. So this check
    shows that the edit moved nothing of what is compared here, except what its manifest declares as moved, each with a reason (declared_moves): a declared move
    is held to nothing while its version is not pinned yet, and the detail of this check names it (edits_said) as far as its detail reaches (the detail of each of
    the five checks of the points is cut at 2000 characters). A move of a thing compared here that is not declared fails as it always did, and a declared move of
    a thing that has not moved fails too: the declaration would say something false.
    Not held here: the reflection summary (never pinned; a book that declares `lens reflection` as moved fails this check as a declaration of a thing that has not
    moved, so it can be neither held nor declared), the record's scope line and a key added at the top of the record (nothing pins them), and the implementation
    lenses while the declared kinds are not the pinned ones (as when an edit version also brings a kind file). An edit version can move these for the older cases
    too, without declaring it, and this check holds and says nothing of it. They are read in the review of the edit version. A unit test of the points pins it."""
    try:
        book=json.loads((root/'added.json').read_text(encoding='utf-8'));pin=book['pinned'];file_sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        other_kinds=[f.stem for f in plug(root/'kinds','.py')[0]]!=pin['kinds'];declared=declared_moves(book)
        moved=[] if data['kernel_sha256']==pin['kernel_sha256']==file_sha(root/'kernel'/'core.py') else [('the kernel','kernel/core.py is not the pinned kernel')]   # (what moved, the sentence that says so)
        moved+=[('scenario '+n,'scenarios/'+n+'.json is not the pinned file') for n,h in pin['scenarios'].items() if file_sha(root/'scenarios'/(n+'.json'))!=h]
        changed,displaced=moved_cases(pin['cases'],[[c['id'],sha(c)] for c in data['cases']])
        moved+=[('case '+str(cid),'case '+str(cid)+' is not the pinned case') for cid in changed]+[('the order of the cases','case '+str(cid)+' does not stand in the order the pinned cases were pinned in') for cid in displaced]
        moved+=[(k,'the '+k+' block is not the pinned one') for k in ('events','ask_events') if sha(data[k])!=pin[k]]
        moved+=[('sequence '+n,'the sequence '+n+' is not the pinned one') for n,h in pin['scenes'].items() if sha(data.get('scenes',{}).get(n))!=h]
        moved+=[('the handler of '+k,'the handler of '+k+' is not the pinned one') for k,h in pin['action_handlers'].items() if sha(data['action_handlers'].get(k))!=h]
        moved+=[('lens '+k,'the lens '+k+' is not the pinned one') for k,h in pin['meta_extensions'].items() if sha(data['meta_extensions'].get(k))!=h and ('lens '+k in declared or not (other_kinds and k.startswith('implementation')))]
        stale=[what+' is declared as moved by the edit version '+str(label)+' and has not moved' for what,(label,_) in declared.items() if what not in [w for w,_ in moved]]
        return [said for what,said in moved if what not in declared]+stale
    except Exception as e:return ['added.json or the record cannot be read: '+type(e).__name__]

def edits_said(root):
    """What S202 says beside its verdict, whether it holds or not: every edit version the pins do not hold yet (unpinned), with the files it changed (recorded in
    added.json with their sha256 before and after; where the kernel or the file of a handler is among them, its pin was taken again when the version was applied)
    and every move it declares, with the reason it gives. A book that cannot be read says nothing here: S202 itself says so.
    These sentences stand in the detail after what is wrong, and the detail of this check is cut at 2000 characters, without a word: of a long list of declared
    moves only the first are named in the verdict. added.json holds every move. A unit test of the points pins the cut."""
    try:
        said=[]
        for e in unpinned(json.loads((root/'added.json').read_text(encoding='utf-8'))):
            if 'edits' in e:said.append('the edit version '+str(e['label'])+' changed '+', '.join(sorted(e['edits']['files']))+' (added.json records the sha256 of each before and after)')
            said+=['declared as moved by the edit version '+str(e['label'])+', held to nothing until the next version is applied: '+str(m['what'])+' ('+str(m['why'])+')' for m in e.get('moves',[])]
        return said
    except Exception:return []

def files_why(data,root):
    """S203. Every added file is accounted for. added.json lists, for the points and for every version applied, each file laid in with its sha256: every listed file is
    there with that sha256; the seven places hold only add-on files; every file of the lab that Python can load as code (CODE, outside __pycache__) and every file of
    cases/ is named like one the lab had before the points (pinned.built_in) or is one that is listed; the scenario files are the ones this build authored, each with the
    sha256 the record keeps for it (added.scenarios); the record lists the added files with the same sha256 (added.files), holds nothing else under `added` than files,
    scenes and scenarios, and says it is the build of the last version added.json lists (so the release label is held from 0.10.0 on). A file an EDIT VERSION changed
    (ruling R32; added.json records, for every file the version's edit script changed, the sha256 before and after) is the file that edit left, by sha256: for an added
    file through its listing, which the applier renews, for a file the lab had before the points through the record of the last edit version that changed it. The two
    files in which the applier places words at every application (PLACED) are left out of that. Not held here: the CONTENT of a file the lab had before the points
    that no edit version changed (pinned.built_in is a list of names; the kernel, the baseline and the files of the built-in handlers are held by sha256 in S01, S02
    and S41), what Python keeps in __pycache__, and files that are no code (a note)."""
    try:
        book=json.loads((root/'added.json').read_text(encoding='utf-8'));listed={};why=[];edited={}
        for entry in [book['points']]+book['applied']:
            for rel,h in entry['files'].items():
                if rel in listed:why.append('added.json lists '+rel+' twice')
                listed[rel]=h
            for rel,pair in entry.get('edits',{}).get('files',{}).items():edited[rel]=(pair[1],entry['label'])   # the last edit version that changed the file, and the sha256 it left
        why+=[rel+' is not the file added.json lists' for rel,h in listed.items() if not (root/rel).is_file() or hashlib.sha256((root/rel).read_bytes()).hexdigest()!=h]
        why+=[rel+' is not the file the edit version '+str(label)+' left (added.json records its sha256 after the edit)' for rel,(h,label) in edited.items()
              if rel not in listed and rel not in PLACED and (not (root/rel).is_file() or hashlib.sha256((root/rel).read_bytes()).hexdigest()!=h)]
        for place,suffix in PLACES:why+=[place+'/'+n+' is no add-on file' for n in plug(root/place,suffix)[1]]
        there=[f.relative_to(root).as_posix() for f in sorted(root.rglob('*')) if f.suffix in CODE and '__pycache__' not in f.relative_to(root).parts and (f.is_file() or f.is_symlink())]+['cases/'+f.name for f in plug(root/'cases','.json')[0]]
        why+=[rel+' is neither built in nor listed in added.json' for rel in there if rel not in listed and rel not in book['pinned']['built_in']]
        if sha(data['added']['files'])!=sha(listed):why.append('the record lists other files, or other sha256, than added.json')
        authored=data['added']['scenarios'];on_disk={f.stem:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((root/'scenarios').glob('*.json'))}
        why+=['scenarios/'+n+'.json is not a scenario file this build authored' for n in on_disk if n not in authored]
        why+=['scenarios/'+n+'.json is not the file this build authored' for n,h in authored.items() if on_disk.get(n)!=h]
        if set(data['added'])!={'files','scenes','scenarios'}:why.append('the record keeps something else under added than files, scenes and scenarios')
        if book['applied'] and data.get('release')!='sutra-kernel-extensions/'+book['applied'][-1]['label']:why.append('the record says it is the build of '+str(data.get('release'))[:80]+'; the last version added.json lists is '+book['applied'][-1]['label'])
        return why
    except Exception as e:return ['added.json or the record cannot be read: '+type(e).__name__]

def handlers_why(data,root):
    """S204. Every receipt of every recorded run (the cases, the event record, the ask record, the recorded sequences), in the run and in its trace, names an action kind
    whose handler the record holds by sha256 (action_handlers; S41 holds that list to the four built-in kinds plus the kinds declared in kinds/, each kind to its file,
    and each file to its sha), AND that kind is the one the receipt's method names in the packs its run loaded: a method names its kind under `action` in its pack, a run
    names the packs it loaded under `provenance`, and the packs are read here from the scenario files (S42 and S201 hold each of them to the sha256 the run names). So a
    receipt that says another held kind did its step fails here, whatever checks a version brings of its own. What no record can say is which function ran: for that the
    build looks at the registry and at the States a sequence runs (tools/run_all.py), as a guard against mistakes and no more."""
    try:
        held=data['action_handlers'];why=['kinds/'+n+' is no kind file' for n in plug(root/'kinds','.py')[1]];packs={}
        for f in sorted((root/'scenarios').glob('*.json')):
            p=json.loads(f.read_text(encoding='utf-8'));packs[p['id']]=p
        for part in ('cases','events','ask_events','scenes'):
            for r in runs_under(data.get(part,{})):
                named={m['id']:m.get('action') for p in r.get('provenance',[]) for m in packs.get(p.get('pack'),{}).get('methods',[])}   # method id -> the kind its pack names, over the packs this run says it loaded
                for x in list(r.get('model_receipts',[]))+[e['data']['receipt'] for e in r['trace'] if e['operation']=='LOCAL_EFFECT']:
                    kind,step=x.get('action'),x.get('method')
                    if kind not in held:why.append('a receipt in '+part+' names the action kind '+str(kind)[:80]+', which the record holds no handler for')
                    elif step not in named:why.append('a receipt in '+part+' is for the step '+str(step)[:80]+', which is no method of the packs its run loaded (as the scenario files hold them)')
                    elif named[step]!=kind:why.append('a receipt in '+part+' says the action kind '+str(kind)[:80]+' did the step '+str(step)[:80]+', whose method names the kind '+str(named[step])[:80]+' in the packs its run loaded')
        return sorted(set(why))
    except Exception as e:return ['the receipts cannot be read: '+type(e).__name__]

# The delivered check modules. A check module is reviewed code, like every added file. It runs in a process of its own, started for it alone (python -I -B, an empty
# environment, the root of the file system as its working folder), and not inside this verifier: that process is handed, as one JSON text on its input, the record
# and the files of the lab a module reads, and gives back, as one JSON text on its output, the module's rows. The process starts with nothing of this verifier in
# its memory (not its rows, not its functions, not its modules) and without a word of where the lab is. CHILD is the whole program of that process. It has its own
# copies of sha and check_chain (the two functions a module is handed), its own stand-in for the lab's folder (Handed: the handed files by their path in the lab,
# reading only), built-ins without the FORBIDDEN names, and an import that takes the ALLOWED modules only.
# NOT A SANDBOX (ruling R31): the parser (guard), this process and its reduced built-ins stop common mistakes: a check that imports the lab's code, opens a file by
# its path, prints, hangs, or changes the verifier's own rows. The process is a process of the same user with the lab's rights, and a module that reaches the
# interpreter through an allowed module has the real built-ins and the disk. A unit test of the points shows exactly that, so that nobody reads more into this.
CHILD=r"""
import sys,json,hashlib,fnmatch,builtins,__future__
def sha(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def check_chain(trace):
    for i,row in enumerate(trace):
        if type(row['seq']) is not int or row['seq']!=i+1:return False
        if row['prev_sha256']!=(trace[i-1]['sha256'] if i else 'GENESIS'):return False
        if row['sha256']!=sha({k:v for k,v in row.items() if k!='sha256'}):return False
    return True
class Handed:   # what a check module is handed in place of the lab's folder: the handed files, by their path in the lab, as text. It reads only, and only what was handed
    def __init__(self,files,parts=()):self.files,self.parts=files,tuple(parts)
    def __truediv__(self,more):return Handed(self.files,self.parts+tuple(p for p in str(more).split('/') if p not in ('','.')))
    def joinpath(self,*more):
        out=self
        for m in more:out=out/m
        return out
    def as_posix(self):return '/'.join(self.parts) or '.'
    __str__=as_posix
    def __repr__(self):return 'Handed('+repr(self.as_posix())+')'
    def __eq__(self,other):return isinstance(other,Handed) and self.parts==other.parts
    def __hash__(self):return hash(self.parts)
    def __lt__(self,other):return self.parts<other.parts
    @property
    def name(self):return self.parts[-1] if self.parts else ''
    @property
    def suffix(self):
        n=self.name;i=n.rfind('.');return n[i:] if 0<i<len(n)-1 else ''
    @property
    def stem(self):
        n=self.name;i=n.rfind('.');return n[:i] if 0<i<len(n)-1 else n
    @property
    def parent(self):return Handed(self.files,self.parts[:-1])
    def is_file(self):return self.as_posix() in self.files
    def is_dir(self):return not self.parts or any(k.startswith(self.as_posix()+'/') for k in self.files)
    def exists(self):return self.is_file() or self.is_dir()
    def read_bytes(self):
        if not self.is_file():raise FileNotFoundError(self.as_posix())
        return self.files[self.as_posix()].encode('utf-8')
    def read_text(self,encoding=None,errors=None):return self.read_bytes().decode('utf-8').replace('\r\n','\n').replace('\r','\n')
    def iterdir(self):
        if not self.is_dir():raise NotADirectoryError(self.as_posix())
        n=len(self.parts);return [Handed(self.files,p) for p in sorted({tuple(k.split('/'))[:n+1] for k in self.files if len(k.split('/'))>n and tuple(k.split('/'))[:n]==self.parts})]
    def glob(self,pattern):
        found=[self]
        for part in str(pattern).split('/'):
            if '**' in part:raise ValueError('a handed folder is searched level by level')
            found=[c for f in found if f.is_dir() for c in f.iterdir() if fnmatch.fnmatchcase(c.name,part)]
        return found
    def rglob(self,pattern):
        out,todo=[],[self]
        while todo:
            f=todo.pop(0)
            if f.is_dir():
                kids=f.iterdir();out+=[c for c in kids if fnmatch.fnmatchcase(c.name,str(pattern))];todo+=kids
        return sorted(out)
def main():
    job=json.loads(sys.stdin.buffer.read().decode('ascii'));handed=job['handed'];real=builtins.__import__
    def take(name,globals=None,locals=None,fromlist=(),level=0):   # the import of the module's own lines: the allowed modules only
        if level or name.split('.')[0] not in handed['allowed']:raise ImportError('a check module may import only '+', '.join(handed['allowed']))
        return real(name,globals,locals,fromlist,level)
    safe={k:v for k,v in vars(builtins).items() if k not in handed['forbidden'] and k not in ('__loader__','__spec__')};safe['__import__']=take
    try:
        ns={'__name__':job['name'],'__builtins__':safe}
        exec(compile(job['source'],job['file'],'exec',__future__.annotations.compiler_flag,True),ns)   # annotations are kept as text, as they were when a module ran inside the verifier
        out={'rows':[list(r) if type(r) is tuple else r for r in ns['checks'](handed['record'],Handed(handed['files']),sha,check_chain)]}
    except BaseException as e:out={'why':'it raised '+type(e).__name__}
    try:text=json.dumps(out)
    except (TypeError,ValueError,RecursionError):text=json.dumps({'why':'it returned a row that is not (id, true or false, detail as text)'})
    sys.stdout.write(text)
main()
"""

def hand_in(data,root):
    """What every check module of one verification is handed, as one JSON text: the record, and the files of the lab a module reads, each as text under its path in the
    lab: the kernel, the baseline, every scenario file, added.json, every Python file the lab had before the points, and every file added.json lists (the files of the
    versions: cases, pack files, scene files, kinds, extensions, tests, check modules). A file that is not UTF-8 text is not handed. Not handed: the lab's folder itself,
    results/, the verdict, the page."""
    rels={'kernel/core.py','release/baseline_v0_1_core.py','added.json'}|{'scenarios/'+f.name for f in (root/'scenarios').glob('*.json')}
    try:
        book=json.loads((root/'added.json').read_text(encoding='utf-8'))
        rels|={rel for rel in list(book['pinned']['built_in'])+[rel for entry in [book['points']]+book['applied'] for rel in entry['files']] if type(rel) is str}
    except Exception:pass   # no book, or one that cannot be read: S203 says so; a module is still handed the kernel and the scenario files
    files={}
    for rel in sorted(rels):
        if rel.startswith('/') or '..' in rel.split('/') or '\\' in rel:continue   # a path of the lab, never one that leaves it
        try:files[rel]=(root/rel).read_bytes().decode('utf-8')
        except (OSError,ValueError):pass
    return json.dumps({'record':data,'files':files,'allowed':list(ALLOWED),'forbidden':list(FORBIDDEN)})

def in_child(src,stem,handed,cwd=None,seconds=None):
    """One check module run in a process of its own (CHILD): ([row, ...], None), or (None, why it gave no rows). The module is one failed row when its process cannot be
    started, does not finish within `seconds` (CHECK_SECONDS; it is stopped), ends with another exit code than 0, or writes anything else to its output than the one JSON
    text of its rows (a module that prints, say). The verdict is computed from the rows that come back. What else the process did is not looked at: it is no sandbox."""
    seconds=CHECK_SECONDS if seconds is None else seconds
    job='{"name":'+json.dumps('qa_checks_'+stem)+',"file":'+json.dumps('qa/checks/'+stem+'.py')+',"source":'+json.dumps(src)+',"handed":'+handed+'}'
    try:ran=subprocess.run([sys.executable,'-I','-B','-c',CHILD],input=job.encode('ascii'),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=seconds,cwd=cwd,env={})
    except subprocess.TimeoutExpired:return None,'it did not finish within '+str(seconds)+' seconds'
    except OSError as e:return None,'its process could not be started: '+type(e).__name__
    if ran.returncode!=0:return None,'its process ended with exit code '+str(ran.returncode)
    try:out=json.loads(ran.stdout.decode('utf-8'))
    except (ValueError,RecursionError):return None,'it wrote something else to its output than its rows'
    if type(out) is dict and set(out)=={'why'} and type(out['why']) is str:return None,out['why'][:200]
    if type(out) is not dict or set(out)!={'rows'} or type(out['rows']) is not list:return None,'it wrote something else to its output than its rows'
    return out['rows'],None

def listed_files(root):
    """Every file added.json lists (the points' own and those of every version applied), path in the lab -> sha256; None when the book cannot be read."""
    try:
        book=json.loads((root/'added.json').read_text(encoding='utf-8'))
        return {rel:h for entry in [book['points']]+book['applied'] for rel,h in entry['files'].items()}
    except Exception:return None

def module_text(path,listed):
    """The text of one check module, read ONCE: (text, None), or (None, why the module is not run). The bytes read here are the bytes whose sha256 is compared with the
    sha256 the lab lists for the file (`listed`: listed_files), and the text that is then parsed (guard) and run (in_child) is decoded from these same bytes. So the
    text the lab lists is the text that is parsed, and the text that was parsed is the text that runs; the file is not read a second time."""
    rel='qa/checks/'+path.name
    try:raw=path.read_bytes()
    except OSError as e:return None,'it cannot be read: '+type(e).__name__
    if listed is None or listed.get(rel)!=hashlib.sha256(raw).hexdigest():return None,'its text is not the text added.json lists for '+rel+' (by sha256); it was not run'
    try:return raw.decode('utf-8'),None
    except ValueError:return None,'it is not UTF-8 text; it was not run'

def module_rows(path,data,root,taken,handed=None,text=None):
    """The rows of one delivered check module, ([(id, ok, detail)], None), or (None, why it gives none). The module is qa/checks/<name>.py with
    checks(data, ROOT, sha, check_chain) -> [(id, ok, detail)]. Its text is parsed first (guard) and a module the parser refuses is not run. A module that passes runs in
    a process of its own (in_child), on its own copy of the record, with a stand-in for the lab's folder that only reads. Whatever goes wrong is the module's one failed
    row, named after its file: its process fails, hangs or writes something else than rows; it raises; it returns no row, a row that is not (id as S<number>_<words>,
    true or false, detail as text), or an id whose number is reserved or already taken. `text` is the module's text as the verifier read it (module_text: once, held to
    the sha256 the lab lists); without it, for one module on its own (a unit test), the file is read here, once. `handed` is what hand_in made for this verification
    (made here when it is not given)."""
    if text is None:
        try:text=path.read_text(encoding='utf-8')
        except (OSError,ValueError) as e:return None,'it cannot be read: '+type(e).__name__
    why=guard(text)
    if why:return None,why+'; it was not run'
    if handed is None:
        try:handed=hand_in(data,root)
        except Exception as e:return None,'the record could not be handed to it: '+type(e).__name__
    rows,why=in_child(text,path.stem,handed,Path(root).resolve().anchor or None)
    if why:return None,why
    if not rows:return None,'it returned no row'
    seen=set()
    for r in rows:
        if type(r) is not list or len(r)!=3 or type(r[0]) is not str or type(r[1]) is not bool or type(r[2]) is not str:return None,'it returned a row that is not (id, true or false, detail as text)'
        n=number(r[0])
        if n is None:return None,'it returned the id '+r[0][:80]+', which is not S<number>_<words>'
        if n in RESERVED or n in taken or n in seen:return None,'it returned '+r[0][:80]+', whose number is reserved or already taken'
        seen.add(n)
    return [tuple(r) for r in rows],None

def delivered_rows(data,root):
    """The rows of every check module the versions deliver (qa/checks/<name>.py), in the order of their file names: [{'id','pass','detail','from'}]. First every module's
    text is read, once, and held to the sha256 added.json lists for it (module_text), and what the modules are handed is made (hand_in): all of that BEFORE the first
    module runs, and no module's file is read after that. So a module runs from the text the lab lists, whatever happens to its file while another module runs. A
    module that is not the listed text, that the parser refuses, that fails, hangs, writes something else than rows, or returns rows out of shape is one failed row
    named after its file; a name in qa/checks that is no add-on file is one failed row too. Every row says which file it is from."""
    files,odd=plug(root/'qa'/'checks','.py');taken=set()
    rows=[{'id':'qa/checks/'+name,'pass':False,'detail':'not a check module: an add-on file is named '+PLAIN+'.py','from':'qa/checks/'+name} for name in odd]
    if not files:return rows
    listed=listed_files(root);texts=[module_text(f,listed) for f in files]   # every module's text, read once, before the first module runs
    try:handed=hand_in(data,root)   # made once: every module of this verification is handed the same record and the same files
    except Exception:handed=None    # a record that cannot be handed: module_rows says so for each module
    for f,(text,why) in zip(files,texts):
        got,why=(None,why) if text is None else module_rows(f,data,root,taken,handed,text)
        if got is None:rows.append({'id':'qa/checks/'+f.name,'pass':False,'detail':why,'from':'qa/checks/'+f.name})
        else:
            rows+=[{'id':cid,'pass':ok,'detail':detail,'from':'qa/checks/'+f.name} for cid,ok,detail in got];taken|={number(cid) for cid,_,_ in got}
    return rows

def inspect(data):
    tests=[]
    def check(id,ok,detail=''):
        tests.append({'id':id,'pass':bool(ok),'detail':detail})
    h=hashlib.sha256((ROOT/'kernel'/'core.py').read_bytes()).hexdigest()
    check('S01_source_hash_current',data['kernel_sha256']==h)
    baseline=hashlib.sha256((ROOT/'release'/'baseline_v0_1_core.py').read_bytes()).hexdigest()
    check('S02_old_baseline_immutable',data['baseline_v0_1_sha256']==baseline and baseline.startswith('c5a86c28aac'))
    more,_=added_cases(ROOT)   # the cases a later version added, one file each (cases/<id>.json); the record holds them after the 31 built in. The counts are no longer part of the ids of S03 and S05
    check('S03_distinct_cases',len(data['cases'])==31+len(more) and len(set(x['id'] for x in data['cases']))==31+len(more))
    valid_chains=[];all_model_only=True;all_costs_ok=True;all_governed=True;valid_packs=[]
    for case in data['cases']:
        pack_objs=[json.loads((ROOT/'scenarios'/(n+'.json')).read_text()) for n in case['packs']]
        valid_packs.append(case['pack_digest']==sha(pack_objs))
        outcome=case['outcome']
        if outcome:
            valid_chains.append(check_chain(outcome['trace']) and outcome['trace_root_sha256']==outcome['trace'][-1]['sha256'])
            all_model_only &= all(x['status']=='LOCAL_ONLY' for x in outcome['model_receipts'])
            all_model_only &= 'never external success' in outcome['claim']
            if outcome['cost']:
                for d,cost in outcome['cost'].items():
                    all_costs_ok &= cost>=0
            all_governed &= all(c['status']=='PROPOSED_ONLY' for c in outcome['candidates'])
            all_governed &= all(c['status']=='PROPOSED_ONLY' for c in outcome['learning'])
    check('S04_all_pack_sha_match',all(valid_packs))
    check('S05_all_run_chains',len(valid_chains)==30+sum(1 for c in more if c['expected']!='NO_STANDING_GOAL') and all(valid_chains))
    check('S06_receipts_local_only',all_model_only)
    check('S07_all_plan_costs_nonnegative',all_costs_ok)
    check('S08_all_candidates_proposed_only',all_governed)
    m={c['id']:c for c in data['cases']}
    def status(cid):return m[cid]['outcome']['status'] if m[cid]['outcome'] else m[cid]['run']['status']
    check('S09_missing_semantics_honest',status('00_goal')=='SEMANTICS_MISSING')
    check('S10_unknown_approval_honest',status('02_methods')=='QUERY_EVIDENCE')
    check('S11_authority_gate',status('03_evidence')=='AUTHORITY_REQUIRED' and not m['03_evidence']['outcome']['actions'])
    check('S12_added_notification_is_action',m['06_nuance']['outcome']['actions']==['ship-replacement@1','notify-customer@1'])
    check('S13_missing_method_and_recovery',status('07_gap')=='METHOD_ABSENT' and 'record-survey@1' in m['08_method_added']['outcome']['actions'])
    check('S14_pareto_policy_flip',m['09_pareto']['outcome']['actions']==['ship-fast@1'] and m['10_preference']['outcome']['actions']==['ship-economy@1'])
    check('S15_new_domain_methods',m['12_enquiry']['outcome']['actions']==['store-enquiry@1','readback-enquiry@1'])
    check('S16_construct_candidate_only',m['15_constructor']['outcome']['candidates'][0]['status']=='PROPOSED_ONLY' and m['15_constructor']['outcome']['candidates'][0]['valid_contract'])
    check('S17_reject_bad_contract',not m['16_bad_constructor']['outcome']['candidates'][0]['valid_contract'])
    check('S18_no_spurious_self_authority',status('18_self_need')=='AUTHORITY_REQUIRED')
    check('S19_tenant_isolation',status('20_wrong_tenant')=='QUERY_EVIDENCE')
    check('S20_no_standing_no_trigger',status('21_no_goal')=='NO_STANDING_GOAL')
    check('S21_capacity_denied',status('23_capacity')=='PROVIDER_REQUIRED')
    check('S22_resources_denied',status('24_budget')=='RESOURCE_REQUIRED')
    ev=data['events']
    check('S23_unrelated_no_recompute',not ev['unrelated']['affected'] and not ev['cross_tenant']['affected'])
    check('S24_relevant_recompute',ev['approval_revoked']['affected']==['order_complete'])
    check('S25_dep_invalidation',ev['impacted_fact_after_revoke']['truth']=='UNKNOWN')
    check('S26_immutable_previous_run',ev['old_trace_hash_before']==ev['old_trace_hash_after'])
    meta=data['meta_extensions']
    check('S27_reviewed_semantics_only',not meta['knowledge_compiler']['unreviewed_rule']['rules'][0]['approved'] and meta['knowledge_compiler']['reviewed_rule']['rules'][0]['approved'])
    check('S28_reflection_no_promotions',all(x['status']=='PROPOSED_ONLY' for x in meta['reflection']['candidates']))
    check('S29_j2_projection_not_closed',all(x['status']=='open' for x in meta['j2_projection']['atoms']))
    check('S30_design_diff',meta['graph_diff_nuance']['added']==['notify-customer@1'])
    # Implementation versions (rung L1): proposal-only, right shape, hash-stable, never marked executed.
    for key,label in (('implementation','S32'),('implementation_enquiry','S33'),('implementation_website','S38')):
        impl=meta.get(key) or {}
        wf=impl.get('workflow',{})
        shape=all(k in wf for k in ('id','name','version','source','trigger','steps','verify','enforcement'))
        steps_ok=len(wf.get('steps',[]))==len(impl.get('plan',{}).get('actions',[]))+2 and all(s.get('sandbox')=='local-model-only' for s in wf.get('steps',[]) if s.get('method'))
        proposed=impl.get('status')=='PROPOSED_ONLY' and 'PROPOSED_ONLY' in str(wf.get('enforcement',{}).get('current','')) and all(a.get('status')=='open' and a.get('verify',{}).get('met') is False for a in impl.get('atoms',[]))
        stable=impl.get('implementation_sha256')==sha({k:v for k,v in impl.items() if k not in ('ui','ui_sha256','implementation_sha256')}) and impl.get('ui_sha256')==sha(impl.get('ui'))
        check(label+'_'+key+'_proposal_only_right_shape',shape and steps_ok and proposed and stable)
    # Deliberate negative: verifier must reject forged edits without breaking JSON shape.
    test_case=next(x for x in data['cases'] if x['id']=='04_gates')
    forged=json.loads(json.dumps(test_case['outcome']['trace']))
    forged[2]['operation']='FORGED_SUCCESS'
    check('S31_reject_tampered_event',not check_chain(forged))
    # 0.4.0-shrink (move-out M1): learning is an extension over the record; the kernel source carries none of it.
    core_src=(ROOT/'kernel'/'core.py').read_text()
    check('S34_kernel_source_without_learning',all(w not in core_src for w in ('REUSE_COMPOSITION','INVESTIGATE_GAP','learned_signatures','LEARN_CANDIDATE')))
    learned={c['id']:c['outcome']['learning'] for c in data['cases'] if c['outcome']}
    check('S35_learning_recorded_from_extension',learned['05_learn']==[{'kind':'REUSE_COMPOSITION','signature':'ship-replacement@1','observations':1,'status':'PROPOSED_ONLY','gate':'independent held-out verification + approval'}]
          and learned['07_gap'][0]['kind']=='INVESTIGATE_GAP' and learned['04_gates']==[]
          and all(x['kind'] in ('REUSE_COMPOSITION','INVESTIGATE_GAP') for v in learned.values() for x in v))
    # Each learning list is bound to the kernel's hash-chained record: trace root + sha256 of the list.
    check('S36_learning_bound_to_trace_root',all(c['outcome'].get('learning_record')=={'source_trace':c['outcome']['trace_root_sha256'],'learning_sha256':sha(c['outcome']['learning'])} for c in data['cases'] if c['outcome']))
    # 0.5.0-standards: the failed standard rests on adapter evidence; the repair is one reviewed method; generated work passes on evidence alone.
    world={w['predicate']:w for w in m['25_registrable_gap']['four_views']['world']}
    finding=world.get('sutra/workflows|every_step_has_check',{})
    check('S37_standard_from_adapter_evidence',status('25_registrable_gap')=='METHOD_ABSENT' and finding.get('truth')=='FALSE' and str(finding.get('source','')).startswith('adapter:standards/')
          and m['26_registrable_repair']['outcome']['actions']==['add-step-checks@1']
          and status('27_registrable_generated')=='SUPPORTED_BY_EVIDENCE' and not m['27_registrable_generated']['outcome']['actions'] and not m['27_registrable_generated']['outcome']['model_receipts'])
    # 0.6.0-order: in the website implementation every edge runs forward and every prerequisite is a step of the plan.
    site=meta['implementation_website']['workflow'];where={s['id']:i for i,s in enumerate(site['steps'])}
    check('S39_website_edges_run_forward',len(site['edges'])==4 and all(e['from'] in where and e['to'] in where and where[e['from']]<where[e['to']] for e in site['edges'])
          and all(set(s.get('after',[]))=={e['from'] for e in site['edges'] if e['to']==s['id']} for s in site['steps'] if s.get('method'))
          and m['28_website']['outcome']['actions']==['plan-site@1','write-content@1','build-pages@1','check-site@1'])
    # 0.7.0-handlers: the kernel names no constructor or artifact kind; the code that performs effects is recorded by sha.
    check('S40_kernel_source_without_moved_kinds',all(w not in core_src for w in ('compile_candidate','emit_artifact','LOCAL_ARTIFACT','valid_contract')))
    handlers=data.get('action_handlers',{})
    check('S41_action_handlers_recorded_by_sha',not kinds_why(handlers,ROOT)   # add-on points (0.10.0): the four built-in kinds plus the kinds declared in kinds/, each held to the file its handler lives in
          and all(hashlib.sha256((ROOT/h['file']).read_bytes()).hexdigest()==h['sha256'] for h in handlers.values()),'; '.join(kinds_why(handlers,ROOT))[:2000])
    # 0.8.0-ask. Every recorded run is compared with its own trace (status, work state, goal, scope, stop reasons, the selection,
    # actions, skipped steps, cost, receipts; a run that says effects were recorded has receipts, a plan that ran nothing has none),
    # with the packs it says it loaded (each pack's sha against its file; every step is a method of one of them, at that pack's cost;
    # a case's run loaded the case's packs) and with the kernel's claim sentence, word for word; a case's run is recorded twice and
    # both copies are compared, and so are the viewer's copies of its actions and trace; numbers are compared as JSON (1 is not true)
    # in a run's cost, in the ask record's snapshots, in the stamp's event and in every case's budget_after and candidate count. A stopped run (0.9.0) must carry one STEP_STOPPED row after its last receipt, the stopped step first under pending, and the same step and reason in its result; the row has its three fields and a reason from the closed list, is the last row of the plan and its steps and stands right after the stopped step's own gate row (a kernel fault may stand right after a row of the plan instead), and `unsettled` names the SETTLE_STOPPED rows, each held to its shape (stop_ok). Every case's books are held to its runs and its pack files: the budget left, the journal rows, the candidates of its last run, the stored facts, and what the stop row of its last run says its effect reads and what that run says its goal reads (books_ok). Not caught (this verifier runs neither the kernel nor a handler, and the chain holds no secret): a run re-made consistently from end to end; a handler's refusal re-worded; a stop whose gate admitted the step re-worded with any other phrase of the list that is not a gate's (a kernel fault with its gate row left in or taken out, a failed handler, a return that cannot be a receipt, a prerequisite of the stopped step, also one that the stored rows read TRUE); a stop re-told as a completed run by a STEP_ALREADY_TRUE row for the stopped step, although the stored row of that step's effect does not read TRUE; a settle failure invented or erased (the record says neither which kinds have a settle hook nor whether a blocked look was dry); a blocked run that names no reason at all, worded METHOD_ABSENT; a row said to be turned away during a run, on a fact that carries a decision; the stored row on the effect of a step that ran or stopped, which is its handler's to write; what an earlier run of a case with several goals says its effect and its goal read. The line that pins case 30 (in runs_ok below) refuses a re-wording of that case's own stop; a forged case 30 that has no `stopped` field ends this function with KeyError there instead of a failed check (the pinned fields are read before the check can refuse). NOT checked here: what a trace
    # does not carry (needs, proof, branch, and the truth of the goal other than what a stopped last run says its goal reads); trace rows that no check reads (an ADMISSION row's own fields, other than the verdict of a stopped step's gate row); a run's candidates (other than the count of a case's last run, and that a receipt cites each) and learning; a key
    # added to a run; the viewer's world and knowledge views; a case's title, description, area, scope, its run block's own status and
    # goals, and of its derived state the rule_ids; the order of the packs an event-block run names, and a pack
    # among them that no step needs; the release label; and an event block's own status, goals and counts beyond what S43 to S47 read.
    # The ask record must show: asked once, nothing
    # shipped, charged once; yes resumes; no is final; another route leaves the question answerable. S48 shows the same
    # claims fail on forged records.
    packs={p['id']:p for p in (json.loads(f.read_text()) for f in sorted((ROOT/'scenarios').glob('*.json')))}
    methods={mth['id']:mth for p in packs.values() for mth in p.get('methods',[])}   # every method of every pack file: the ask books below read their costs here
    loaded={}
    def packs_of(c):   # the pack files a case ran on, each read once
        for n in c['packs']:
            if n not in loaded:loaded[n]=json.loads((ROOT/'scenarios'/(n+'.json')).read_text())
        return [loaded[n] for n in c['packs']]
    CLAIM='LOCAL_REFERENCE_ONLY; never external success or current J2 implementation'   # the kernel's sentence, word for word
    def table(r):   # the methods of the packs this run says it loaded; a pack that is not its file gives no table
        if any(p['pack'] not in packs or sha(packs[p['pack']])!=p['sha256'] for p in r['provenance']):return None
        return {mth['id']:mth for p in r['provenance'] for mth in packs[p['pack']].get('methods',[])}
    rsha=lambda r:sha({k:v for k,v in r.items() if k!='sha256'});same=lambda a,b:sha(a)==sha(b)   # numbers are compared as JSON: 1 is not true and not 1.0
    def run_ok(r):
        t=r['trace'];last=t[-1];receipts=[e['data']['receipt'] for e in t if e['operation']=='LOCAL_EFFECT']
        chosen=[e['data'] for e in t if e['operation']=='SELECT'];skips=[e['data']['method'] for e in t if e['operation']=='STEP_ALREADY_TRUE'];stops=[e['data'] for e in t if e['operation']=='STEP_STOPPED'];ops=[e['operation'] for e in t];block=[e['data'] for e in t if e['operation']=='BLOCK'];waiting=r['work_state']=='waiting'
        mt=table(r);total=lambda acts:{d:sum(mt[a].get('cost',{}).get(d,0) for a in acts) for d in chosen[0]['full_cost']}
        return (check_chain(t) and same(r.get('claim'),CLAIM) and mt is not None and r['trace_root_sha256']==last['sha256'] and last['operation']=='TERMINAL' and last['data']=={'status':r['status'],'work_state':r['work_state']}
                and t[0]['operation']=='GOAL_ACCEPTED' and t[0]['data']=={'goal':r['goal'],'scope':r['scope']}
                and same(receipts,r['model_receipts']) and all(x['sha256']==rsha(x) and x['status']=='LOCAL_ONLY' for x in receipts)
                and len(chosen)+len(block)==1 and ('waits' in r)==waiting and ('pending' in r)==(waiting or bool(stops)) and ('stopped' in r)==bool(stops) and len(stops)<=1 and stop_ok(r,methods,handlers)
                and (not stops or ((r['status'],r['work_state'],r['stopped'],r['pending'][:1])==('STEP_STOPPED','stopped',{'method':stops[0]['method'],'reason':stops[0]['reason']},[stops[0]['method']])
                                   and 'LOCAL_EFFECT' not in ops[ops.index('STEP_STOPPED'):]))
                and ((r['status'],r['stop_reasons'],r['actions'],r['cost'],r['work_state'],receipts)==(block[0]['reason'],block[0]['all_reasons'],[],None,'blocked',[]) and same(r['pareto_options'],0) and not skips and 'skipped' not in r and block_ok(block[0]) if block else
                     r['stop_reasons']==[] and same(r['pareto_options'],chosen[0]['pareto_options']) and held('options',type(r['pareto_options']) is int) and [a for a in chosen[0]['actions'] if a not in skips]==r['actions']+r.get('pending',[]) and r.get('skipped',[])==skips and ('skipped' in r)==bool(skips) and set(skips)<=set(chosen[0]['actions'])
                     and set(chosen[0]['actions'])<=set(mt) and same(total(chosen[0]['actions']),chosen[0]['full_cost']) and same(r['cost'],total(r['actions'])) and [x['method'] for x in receipts]==(r['actions'] if r['work_state']!='ready' else [])
                     and r['status']=={'ready':'PLAN_READY','waiting':'WAITING','stopped':'STEP_STOPPED','completed':'LOCAL_MODEL_EFFECTS_RECORDED' if receipts else 'SUPPORTED_BY_EVIDENCE'}.get(r['work_state'])
                     and (not waiting or (r['status']=='WAITING' and (r['waits']==[receipts[-1]['method']] and receipts[-1].get('parked') is True if receipts else r['actions']==[] and chosen[0].get('waits')==r['waits'])))))
    def every_run(d):
        for c in d['cases']:
            if c['outcome']:yield c['outcome']
            yield from c['run']['runs']   # the same run as recorded under the case's run block: both copies are compared with their trace
        for block in ('events','ask_events'):
            for value in d[block].values():
                if isinstance(value,dict) and 'runs' in value:yield from value['runs']
    def runs_ok(d):   # every run agrees with its trace; the two copies of a case's run are one run; the run that skipped two steps says so in its result and in its chain
        made=d['ask_events']['made_again']['runs'][0];rows=[e['data'] for e in made['trace'] if e['operation']=='STEP_ALREADY_TRUE'];halt=[c for c in d['cases'] if c['id']=='30_stop'][0]['outcome']
        return (all(run_ok(r) for r in every_run(d)) and all(same(c['outcome'],c['run']['runs'][0] if c['run']['runs'] else None) and same([c['four_views']['design'],c['four_views']['run']],[(c['outcome'] or {}).get('actions',[]),(c['outcome'] or {}).get('trace',[])])
                                                         and (not c['outcome'] or [p['pack'] for p in c['outcome']['provenance']]==c['packs']) for c in d['cases'])
                and (made['status'],made['actions'],made.get('skipped'))==('LOCAL_MODEL_EFFECTS_RECORDED',['prepare-quote@1'],['assume-approval@1','ship-quoted@1'])
                and all(books_ok(c,methods,packs_of(c)) for c in d['cases'])
                and held('pin',(halt['status'],halt['stopped']['reason'],len(halt['model_receipts']),halt['pending']==[halt['stopped']['method']],halt['goal_truth_after'])==('STEP_STOPPED','Handler refused: No declared constructor',3,True,'FALSE'))
                and [(x['method'],x['effect'],x['source']) for x in rows]==[('assume-approval@1','quote_approved','LOCAL_MODEL:assume-approval@1'),('ship-quoted@1','order_shipped','LOCAL_MODEL:ship-quoted@1')])
    def ask_claims(d):
        if not runs_ok(d):return {'runs':False}
        case=[c for c in d['cases'] if c['id']=='29_ask'][0];asked=case['outcome'];ae=d['ask_events'];run=lambda key:ae[key]['runs'][0]
        budget={'compute':10,'money':10,'attention':3};slots={'local-provider':5,'owner-channel':2};ASKED,SHIP='ask-customer-approval@1','ship-replacement@1'
        def books(keys):   # the budget and the provider slots after the runs named, recomputed from the receipts and the pack files
            b,p=dict(budget),dict(slots)
            for key in keys:
                for x in run(key)['model_receipts']:
                    p[methods[x['method']]['provider']]-=1
                    for dim,v in methods[x['method']].get('cost',{}).items():b[dim]-=v
            return {'budget':b,'providers':p}
        def snap_ok(name,keys,open_receipt):
            snap=ae[name];want=books(keys)
            return same(snap['budget'],want['budget']) and same(snap['providers'],want['providers']) and same(snap['open_asks'],{'orgA/fulfillment|customer_approved':{'method':ASKED,'receipt':open_receipt['sha256'],'issued':open_receipt}} if open_receipt else {})
        def parked(r):
            return (r['status'],r['work_state'],r['actions'],r['pending'],r['waits'],r['goal_truth_after'],r['cost'])==('WAITING','waiting',[ASKED],[SHIP],[ASKED],'UNKNOWN',{'compute':0,'money':0,'attention':1})
        def waits(r):
            return (r['status'],r['work_state'],r['actions'],r['pending'],r['waits'],r['model_receipts'],r['cost'])==('WAITING','waiting',[],[SHIP],[ASKED],[],{'compute':0,'money':0,'attention':0})
        def stamp(key,first,truth):
            issued=run(first)['model_receipts'][0];top=ae[key]
            return (top['status'],top['affected'],len(top['runs']))==('RECONCILED',['order_complete'],1) and same(top['event'],{'predicate':'customer_approved','truth':truth,'verified':True,'final':True,
                    'source':'STAMP:'+issued['ask']['to'],'version':'ask-'+issued['sha256'][:12],'answers':issued['sha256'],'scope':issued['scope']})
        row=lambda r,op:[e['data'] for e in r['trace'] if e['operation']==op]
        first,yes,no,other=run('first'),run('answered_yes'),run('answered_no'),run('other_route');issued=first['model_receipts'][0]
        return {
         'S43_ask_parks_and_ships_nothing':parked(asked) and len(asked['model_receipts'])==1 and asked['model_receipts'][0]['ask']['to']=='customer'
          and same(case['derived_state']['budget_after'],books(['first'])['budget']) and all(parked(run(key)) for key in ('first','first_no','first_other')),
         'S44_open_ask_is_idempotent':waits(run('again')) and waits(run('unrelated')) and snap_ok('after_first',['first'],issued) and snap_ok('after_again',['first','again'],issued)
          and snap_ok('after_unrelated',['first','again','unrelated'],issued),
         'S45_yes_resumes_no_is_final':(yes['status'],yes['work_state'],yes['actions'])==('LOCAL_MODEL_EFFECTS_RECORDED','completed',[SHIP])
          and {'predicate':'customer_approved','source':'STAMP:customer','version':'ask-'+issued['sha256'][:12]} in row(yes,'RETAIN')
          and [x['receipt'] for x in row(yes,'ASK_CLOSED')]==[issued['sha256']] and snap_ok('after_yes',['first','again','unrelated','answered_yes'],None)
          and all((run(key)['status'],run(key)['work_state'],run(key)['actions'],run(key)['model_receipts'],run(key)['stop_reasons'])==('REFUSED','blocked',[],[],['METHOD_ABSENT','REFUSED'])
                  and {'predicate':'customer_approved','source':'STAMP:customer'} in row(run(key),'REFUSED') for key in ('answered_no','no_again'))
          and snap_ok('after_first_no',['first_no'],run('first_no')['model_receipts'][0]) and snap_ok('after_no',['first_no','answered_no'],None) and snap_ok('after_no_again',['first_no','answered_no','no_again'],None),
         'S46_another_route_leaves_the_question_answerable':(other['status'],other['work_state'],other['actions'])==('LOCAL_MODEL_EFFECTS_RECORDED','completed',['ship-original@1'])
          and snap_ok('after_first_other',['first_other'],run('first_other')['model_receipts'][0]) and snap_ok('after_other',['first_other','other_route'],run('first_other')['model_receipts'][0])
          and (ae['other_route']['status'],ae['other_route']['affected'],ae['other_route']['event']['predicate'])==('RECONCILED',['order_complete'],'original_stock'),
         'S47_stamp_cites_the_issued_receipt':stamp('answered_yes','first','TRUE') and stamp('answered_no','first_no','FALSE')
          and (ae['unrelated']['status'],ae['unrelated']['event']['predicate'])==('RECONCILED','substitute_stock')}
    claims=ask_claims(data)
    check('S42_every_run_agrees_with_its_trace_and_packs',runs_ok(data))
    for name,ok in claims.items():
        if name!='runs':check(name,ok)
    # The same claims must fail on a falsified record: forgeries of this very record, each changing one thing (two change it in several places at once).
    # The stop forgeries of 0.9.0 (stop_forgeries) change the books of case 30 or re-make its run as a forger would: the run changed, its chain hashed again, every copy
    # of it updated. S49 switches each stop check off in turn and shows that a forgery then passes (each check is the one that refuses a forgery), with the line
    # that pins case 30 switched off throughout (no check leans on it).
    def falsified(change):
        d=json.loads(json.dumps(data));change(d)
        try:return not all(ask_claims(d).values())
        except Exception:return True
    c29=lambda d:[c for c in d['cases'] if c['id']=='29_ask'][0];c30=lambda d:[c for c in d['cases'] if c['id']=='30_stop'][0];r0=lambda d,key:d['ask_events'][key]['runs'][0];ev=lambda d,key:d['ask_events'][key]
    def remake(d,change):   # what a forger can do without any secret: change case 30's run, hash its chain again, and carry the new run to every copy the record keeps
        c=c30(d);r=c['outcome'];change(r);prev='GENESIS'
        for n,row in enumerate(r['trace']):
            row.update(seq=n+1,prev_sha256=prev);row['sha256']=sha({k:v for k,v in row.items() if k!='sha256'});prev=row['sha256']
        r['trace_root_sha256']=r['learning_record']['source_trace']=c['derived_state']['historical_events'][-1]['trace_root_sha256']=prev
        c['run']['runs'][0]=json.loads(json.dumps(r));c['four_views']['run']=json.loads(json.dumps(r['trace']))
    halted=lambda r:[e['data'] for e in r['trace'] if e['operation']=='STEP_STOPPED'][0]
    def reworded(reason):return lambda r:(halted(r).update(reason=reason),r['stopped'].update(reason=reason))
    def moved(r):   # the stop row put in front of its own gate row
        i=[e['operation'] for e in r['trace']].index('STEP_STOPPED');r['trace'][i-1],r['trace'][i]=r['trace'][i],r['trace'][i-1]
    stop_forgeries=[lambda d:c30(d)['derived_state']['budget_after'].update(compute=6),      # the stopped step was paid
                    lambda d:c30(d)['derived_state']['budget_after'].update(compute=10),     # nothing was paid
                    lambda d:[r.update(unsettled=['ask']) for r in (c30(d)['outcome'],c30(d)['run']['runs'][0])],
                    lambda d:c30(d)['derived_state']['historical_events'][-1].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
                    lambda d:c30(d)['derived_state'].update(candidate_count=1),
                    lambda d:[r.update(goal_truth_after='TRUE') for r in (c30(d)['outcome'],c30(d)['run']['runs'][0])],
                    lambda d:remake(d,lambda r:halted(r).update(effect_reads='TRUE')),
                    lambda d:remake(d,lambda r:halted(r).pop('effect_reads')),
                    lambda d:remake(d,lambda r:halted(r).update(note='x')),
                    lambda d:remake(d,reworded('Because')),
                    lambda d:remake(d,reworded('Prerequisite not true before effect: no_such_fact')),
                    lambda d:remake(d,reworded('Gate changed before effect: AUTHORITY_REQUIRED')),
                    lambda d:remake(d,moved),
                    lambda d:remake(d,lambda r:r['trace'].insert(-1,{'operation':'SETTLE_STOPPED','data':{'kind':'ask','reason':'KeyError'}})),
                    # review round two, 14 to 21: what the goal and the stopped step's effect read, said to be UNKNOWN against rows that read FALSE; a row the packs left, changed;
                    # a row said to be turned away by a decision nobody made; words that are no class name; a kernel fault in front of its own gate row; two SETTLE_STOPPED rows out of shape
                    lambda d:[r.update(goal_truth_after='UNKNOWN') for r in (c30(d)['outcome'],c30(d)['run']['runs'][0])],
                    lambda d:remake(d,lambda r:halted(r).update(effect_reads='UNKNOWN')),
                    lambda d:c30(d)['derived_state']['facts'].setdefault('orgA/enquiries|source_contract_reviewed',{}).update(truth='FALSE'),
                    lambda d:c30(d)['derived_state']['historical_events'].insert(0,{'status':'DECISION_STANDS','scope':'orgA/enquiries','predicate':'source_contract_reviewed'}),
                    lambda d:remake(d,reworded('Handler failed: not a class name at all')),
                    lambda d:remake(d,lambda r:(reworded('Kernel fault: KeyError')(r),moved(r))),
                    lambda d:remake(d,lambda r:(r['trace'].insert(-1,{'operation':'SETTLE_STOPPED','data':{'kind':'no_such_kind','reason':'KeyError'}}),r.update(unsettled=['no_such_kind']))),   # well made and well placed, for a kind the registry does not have
                    lambda d:remake(d,lambda r:(r['trace'].insert(1,{'operation':'SETTLE_STOPPED','data':{'kind':'ask'}}),r.update(unsettled=['ask']))),   # no reason, and before the plan is chosen
                    # 22, the last: the stored row on the effect of a step that ran or stopped is its handler's to write, so changing it together with what the run says it reads passes
                    # every check of a stop and of the books (a stated limit). On case 30 the pinned line refuses it, because the goal of that case reads FALSE; S49 shows it is the only one that needs that line.
                    lambda d:(c30(d)['derived_state']['facts'].setdefault('orgA/enquiries|capability_candidate_created',{}).update(truth='UNKNOWN'),remake(d,lambda r:(halted(r).update(effect_reads='UNKNOWN'),r.update(goal_truth_after='UNKNOWN'))))]
    def retold(cid,status,work):   # a case's run re-chained to end with another status and work state: both copies of the run and the viewer's copy of its trace
        def change(d):
            c=[c for c in d['cases'] if c['id']==cid][0]
            for r in (c['outcome'],c['run']['runs'][0]):
                last=r['trace'][-1];last['data']={'status':status,'work_state':work};last['sha256']=sha({k:v for k,v in last.items() if k!='sha256'})
                r.update(status=status,work_state=work,trace_root_sha256=last['sha256'])
            c['four_views']['run']=c['outcome']['trace']
        return change
    # 0.9.0 also holds a trace row's seq and a run's pareto_options to whole numbers by type, and a BLOCK row to the kernel's ranking (block_ok). The four forgeries below
    # re-make a case's run as a forger would (the run changed, its chain hashed again, every copy updated); S50 shows that each of the three checks refuses its own.
    def rechained(cid,change):   # what remake does for case 30, for any case: the journal row follows the run's status too, and a row's seq is left as the change set it
        def go(d):
            c=[c for c in d['cases'] if c['id']==cid][0];r=c['outcome'];change(r);prev='GENESIS'
            for row in r['trace']:
                row['prev_sha256']=prev;row['sha256']=sha({k:v for k,v in row.items() if k!='sha256'});prev=row['sha256']
            r['trace_root_sha256']=r['learning_record']['source_trace']=prev;c['derived_state']['historical_events'][-1].update(status=r['status'],trace_root_sha256=prev)
            c['run']['runs'][0]=json.loads(json.dumps(r));c['four_views']['run']=json.loads(json.dumps(r['trace']))
        return go
    row_of=lambda r,op:[e['data'] for e in r['trace'] if e['operation']==op][0]
    def renamed(r):   # a blocked run that says effects were recorded: the run, its BLOCK row and its last row say the same
        r.update(status='LOCAL_MODEL_EFFECTS_RECORDED');row_of(r,'BLOCK').update(reason='LOCAL_MODEL_EFFECTS_RECORDED');row_of(r,'TERMINAL').update(status='LOCAL_MODEL_EFFECTS_RECORDED')
    def retyped(r):   # the number of options as 3.0, in the run and in its SELECT row
        n=float(r['pareto_options']);r.update(pareto_options=n);row_of(r,'SELECT').update(pareto_options=n)
    hard_forgeries=[rechained('02_methods',renamed),
                    rechained('02_methods',lambda r:(r.update(stop_reasons=['METHOD_ABSENT','NO_SUCH_REASON','QUERY_EVIDENCE']),row_of(r,'BLOCK').update(all_reasons=['METHOD_ABSENT','NO_SUCH_REASON','QUERY_EVIDENCE']))),   # a reason outside the ten, in the run and in its BLOCK row
                    rechained('09_pareto',lambda r:r['trace'][1].update(seq=2.0)),   # a row numbered 2.0
                    rechained('09_pareto',retyped)]
    forgeries=[lambda d:c29(d)['outcome']['model_receipts'][0].update(sha256='0'*64),
               lambda d:c29(d)['outcome']['model_receipts'][0]['ask'].update(to='mallory'),
               lambda d:c29(d)['outcome'].update(waits=['ship-replacement@1']),
               lambda d:c29(d)['derived_state']['budget_after'].update(attention=3),
               lambda d:[ev(d,k)['budget'].update(attention=3) for k in ('after_first','after_again','after_unrelated')],
               lambda d:ev(d,'after_yes')['budget'].update(attention=0),
               lambda d:ev(d,'after_yes')['providers'].update({'owner-channel':0}),
               lambda d:ev(d,'after_other')['budget'].update(money=10),
               lambda d:ev(d,'after_no_again')['budget'].update(attention=1),
               lambda d:ev(d,'after_first_no')['open_asks']['orgA/fulfillment|customer_approved'].update(method='ship-replacement@1'),
               lambda d:ev(d,'after_yes')['open_asks'].update(left={'method':'x','receipt':'y'}),
               lambda d:r0(d,'answered_yes').update(status='PLAN_READY',model_receipts=[]),
               lambda d:r0(d,'answered_yes').update(work_state='waiting'),
               lambda d:r0(d,'answered_no').update(actions=['ship-replacement@1']),
               lambda d:r0(d,'answered_no').update(stop_reasons=['REFUSED']),
               lambda d:r0(d,'no_again').update(status='WAITING'),
               lambda d:r0(d,'no_again').update(pending=['ship-replacement@1']),
               lambda d:r0(d,'again').update(model_receipts=[dict(r0(d,'first')['model_receipts'][0])]),
               lambda d:r0(d,'again').update(cost={'compute':0,'money':0,'attention':1}),
               lambda d:r0(d,'again').update(waits=[]),
               lambda d:r0(d,'first').update(pending=[]),
               lambda d:r0(d,'first').update(cost={'compute':0,'money':0,'attention':0}),
               lambda d:r0(d,'first_other').update(status='PLAN_READY'),
               lambda d:r0(d,'other_route').update(status='WAITING'),
               lambda d:r0(d,'other_route')['trace'].pop(-2),
               lambda d:ev(d,'answered_no')['event'].update(answers='0'*64),
               lambda d:ev(d,'answered_yes')['event'].update(predicate='substitute_stock'),
               lambda d:ev(d,'answered_yes')['event'].update(scope='orgB/fulfillment'),
               lambda d:ev(d,'answered_yes')['event'].update(verified=False),
               lambda d:ev(d,'answered_yes')['event'].update(version='ask-000000000000'),
               lambda d:ev(d,'answered_yes')['event'].update(depends_on=[{'predicate':'x','version':'1'}]),
               lambda d:ev(d,'answered_yes').update(status='OUT_OF_SCOPE'),
               lambda d:ev(d,'answered_no').update(affected=[]),
               lambda d:ev(d,'unrelated')['event'].update(predicate='customer_approved'),
               lambda d:[c for c in d['cases'] if c['id']=='04_gates'][0]['outcome'].update(status='PLAN_READY'),
               lambda d:[c for c in d['cases'] if c['id']=='06_nuance'][0]['outcome']['cost'].update(money=0),
               lambda d:ev(d,'after_first')['open_asks']['orgA/fulfillment|customer_approved']['issued']['ask'].update(to='mallory'),
               lambda d:r0(d,'first').update(goal='another_goal'),
               lambda d:r0(d,'again').update(scope='orgB/fulfillment'),
               lambda d:r0(d,'answered_yes').update(waits=['ask-customer-approval@1']),
               lambda d:r0(d,'answered_yes').update(pareto_options=9),
               lambda d:r0(d,'no_again').update(stop_reasons=['NOT_A_REASON']),
               lambda d:[c for c in d['cases'] if c['id']=='02_methods'][0]['outcome'].update(actions=['ship-replacement@1']),
               lambda d:[c for c in d['cases'] if c['id']=='02_methods'][0]['outcome'].update(stop_reasons=['NOT_A_REASON']),
               lambda d:[c for c in d['cases'] if c['id']=='04_gates'][0]['outcome'].update(stop_reasons=['NOT_A_REASON']),
               lambda d:[c for c in d['cases'] if c['id']=='06_nuance'][0]['outcome'].update(cost={}),
               lambda d:[c for c in d['cases'] if c['id']=='06_nuance'][0]['outcome'].update(goal='another_goal'),
               lambda d:r0(d,'made_again').pop('skipped'),
               lambda d:r0(d,'made_again').update(skipped=['ship-quoted@1']),
               lambda d:r0(d,'made_again').update(actions=['prepare-quote@1','assume-approval@1']),
               lambda d:r0(d,'made_again')['model_receipts'].pop(),
               lambda d:r0(d,'made_again')['trace'][-2]['data'].update(source='fixture/elsewhere'),
               lambda d:c29(d)['run']['runs'][0].update(status='PLAN_READY'),
               lambda d:c29(d)['run']['runs'][0]['model_receipts'][0]['ask'].update(to='mallory'),
               lambda d:c29(d)['run']['runs'][0].update(cost={'compute':0,'money':0,'attention':0}),
               lambda d:c29(d)['run']['runs'][0]['trace'].pop(-2),
               lambda d:[c for c in d['cases'] if c['id']=='02_methods'][0]['outcome'].update(pareto_options=3),
               lambda d:r0(d,'answered_no').update(pareto_options=2),
               lambda d:r0(d,'answered_no').update(skipped=[]),
               lambda d:r0(d,'first').update(cost={'compute':0.0,'money':0,'attention':1}),
               lambda d:r0(d,'first')['model_receipts'][0].update(parked=1),
               lambda d:c29(d)['four_views'].update(design=[]),
               lambda d:r0(d,'no_again').update(claim='EXTERNALLY VERIFIED SUCCESS'),
               lambda d:r0(d,'no_again').update(claim='LOCAL_REFERENCE_ONLY; and verified outside'),
               lambda d:ev(d,'answered_yes')['event'].update(verified=1),
               lambda d:ev(d,'answered_no')['event'].update(final=1),
               lambda d:ev(d,'after_first')['budget'].update(attention=2.0),
               lambda d:ev(d,'after_again')['providers'].update({'owner-channel':1.0}),
               lambda d:c29(d)['derived_state']['budget_after'].update(attention=2.0),
               lambda d:ev(d,'after_first')['open_asks']['orgA/fulfillment|customer_approved']['issued'].update(parked=1),
               lambda d:r0(d,'first')['provenance'].pop(),
               lambda d:r0(d,'first')['provenance'][-1].update(sha256='0'*64),
               lambda d:[x['provenance'].reverse() for x in (c29(d)['outcome'],c29(d)['run']['runs'][0])],
               retold('09_pareto','LOCAL_MODEL_EFFECTS_RECORDED','completed'),   # a plan that ran nothing, said to have recorded effects
               retold('09_pareto','SUPPORTED_BY_EVIDENCE','completed'),          # the same plan said to be complete on evidence, its steps still listed
               retold('09_pareto','WAITING','ready'),                            # a ready plan said to be waiting
               retold('04_gates','SUPPORTED_BY_EVIDENCE','completed'),           # a run with a receipt, said to have run nothing
               lambda d:r0(d,'answered_no')['provenance'][0].update(sha256='0'*64),   # a blocked run naming a pack that is not its file
               lambda d:c30(d)['outcome'].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
               lambda d:c30(d)['outcome'].update(work_state='completed'),
               lambda d:c30(d)['outcome']['stopped'].update(reason='Handler failed: KeyError'),
               lambda d:c30(d)['outcome'].pop('stopped'),
               lambda d:c30(d)['outcome'].update(pending=[]),
               lambda d:c30(d)['outcome']['model_receipts'].pop(),
               lambda d:c30(d)['run']['runs'][0]['stopped'].update(method='construct-nothing@1')]+stop_forgeries+hard_forgeries
    check('S48_claims_fail_on_forged_records',all(falsified(f) for f in forgeries),detail=str([i for i,f in enumerate(forgeries) if not falsified(f)]))
    def accepted(off):   # the stop forgeries that pass when the named checks are switched off
        OFF.update(off)
        try:return [i for i,f in enumerate(stop_forgeries) if not falsified(f)]
        finally:OFF.difference_update(off)
    alone={name:accepted({'pin',name}) for name in ('unsettled','shape','reason','gate','budget','journal','candidates','facts','effect')}   # each check switched off in turn, the pinned line off throughout: exactly its own forgeries then pass, next to the one that only the pinned line refuses
    check('S49_every_stop_check_refuses_a_forgery_of_its_own_and_only_the_last_forgery_leans_on_the_case_pin',accepted(set())==[] and accepted({'pin'})==[22]
          and alone=={'unsettled':[2,13,20,21,22],'shape':[8,22],'reason':[9,10,18,22],'gate':[11,12,19,22],'budget':[0,1,22],'journal':[3,17,22],'candidates':[4,22],'facts':[16,22],'effect':[5,6,14,15,22]},
          detail=str({'accepted':accepted(set()),'accepted without the pin':accepted({'pin'}),'accepted with one check more off':alone}))
    def passing(off):   # the hardening forgeries that pass when the named check is switched off
        OFF.update(off)
        try:return [i for i,f in enumerate(hard_forgeries) if not falsified(f)]
        finally:OFF.difference_update(off)
    lone={name:passing({name}) for name in ('rank','seq','options')}
    check('S50_a_blocked_reason_and_the_type_of_a_number_each_refuse_a_forgery_of_their_own',not passing(set()) and lone=={'rank':[0,1],'seq':[2],'options':[3]},detail=str({'accepted':passing(set()),'accepted with one check off':lone}))
    # Add-on points (0.10.0): what a later version adds as files. First the points' own five checks (the functions above the checks, S200 to S204). The detail of S202
    # also names, whether the check holds or not, every edit version the pins do not hold yet: the files it changed and the moves it declares (ruling R32; edits_said).
    # It names them after what is wrong and as far as 2000 characters reach: the line below cuts the detail of each of these five checks there, without a word, so
    # of a long list of declared moves only the first stand in the verdict (added.json holds every move; a unit test of the points pins the cut).
    for cid,why,said in (('S200_added_cases_match_their_files',added_cases_why(data,ROOT,31),[]),
                         ('S201_recorded_sequences_are_the_scene_files_sealed_and_their_runs_agree_with_their_traces',scenes_why(data,ROOT,run_ok),[]),
                         ('S202_what_an_earlier_version_recorded_has_not_moved',pinned_why(data,ROOT),edits_said(ROOT)),
                         ('S203_every_added_file_is_listed_by_sha_and_nothing_else_was_put_in',files_why(data,ROOT),[]),
                         ('S204_every_receipt_names_an_action_kind_the_record_holds_a_handler_for',handlers_why(data,ROOT),[])):check(cid,not why,'; '.join(why+said)[:2000])
    # Then the checks a version delivers: qa/checks/<name>.py holds checks(data, ROOT, sha, check_chain) -> [(id, ok, detail)]. Like this file, such a module reads the
    # record and the pack files and does not import the lab's code. Its text is read once and held to the sha256 added.json lists, parsed, and then run in a process of
    # its own that is handed the record and the files and gives back rows (delivered_rows). A module that is refused, fails, hangs, writes something else than rows, or
    # returns rows out of shape is one failed row named after its file. The verdict below is computed from rows, and every delivered row says which file it is from.
    tests+=delivered_rows(data,ROOT)
    valid=all(t['pass'] for t in tests)
    return {'verifier':'independent_verify.py: pure JSON/hash verifier, never imports kernel',
            'checks':tests,'passed':sum(t['pass'] for t in tests),'total':len(tests),
            'pass':valid,'claims':'synthetic record consistency only; not external effect verification or J2 integration'}

if __name__=='__main__':
    try:data=json.loads(DATA.read_text());result=inspect(data)
    except Exception as e:   # no record, or one the checks cannot read: a failed verification, written down like any other (add-on points, 0.10.0)
        result={'verifier':'independent_verify.py: pure JSON/hash verifier, never imports kernel','checks':[{'id':'the_record_could_not_be_checked','pass':False,'detail':type(e).__name__}],
                'passed':0,'total':1,'pass':False,'claims':'synthetic record consistency only; not external effect verification or J2 integration'}
    (ROOT/'qa'/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['passed'],'/',result['total'],'independent local checks', 'PASS' if result['pass'] else 'FAIL')
    for r in result['checks']:
        if not r['pass']:print('FAIL',r)
    sys.exit(0 if result['pass'] else 1)
