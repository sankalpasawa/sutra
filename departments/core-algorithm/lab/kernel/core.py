"""Sutra One-Kernel Extension Lab: finite, deterministic, local reference (the build label is in lab/README.md).
The kernel is held constant across scenarios. All external effects are prohibited.
It does NOT implement current production Native/J2 or replace historical Sutra Core.
"""
from __future__ import annotations
import copy, hashlib, json
from dataclasses import dataclass, field
from typing import Any


def canonical(v: Any) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(v: Any) -> str:
    return hashlib.sha256(canonical(v).encode()).hexdigest()


BIG=10**4300   # an integer below this prints on every Python the lab runs on (from 3.10.7 the text of an integer stops at 4300 digits)
def plain(v: Any, room: int = 16, left: list = None) -> Any:   # what is handed in, rebuilt as plain data. Types are compared by identity; a dict is read once, as one snapshot of its pairs, and a list item by item, so no code of what is handed in runs: an object at the top, at most 16 levels below it and 100000 items in all (keys and containers count)
    top=left is None;left=[100000] if top else left;left[0]-=1;t=type(v)
    if left[0]>=0 and room>=0 and (t is dict or not top):
        if t is dict:
            try:v=tuple(dict.items(v))   # one snapshot of the pairs, itself unchangeable: what is checked below is what is copied, whatever a finalizer of the caller's garbage does to the dict meanwhile
            except RuntimeError:raise ValueError('Not a plain JSON object') from None   # the dict changed while it was read
            if all(type(k) is str for k,_ in v):return {plain(k,room,left):plain(x,room-1,left) for k,x in v}
        if t is list:return [plain(x,room-1,left) for x in v]   # item by item, each fetched once: the list's own iterator checks its bound at every step
        if t is str:v.encode();return v   # text that is not UTF-8 raises UnicodeEncodeError, which is a ValueError
        if t is bool or v is None or (t is int and -BIG<v<BIG) or (t is float and v-v==0):return v   # v-v==0 leaves out NaN and the infinities
    raise ValueError('Not a plain JSON object')

class Stop(Exception):pass   # a step that cannot run or was refused. A handler refuses in its own words by raising it with one text; Kernel._act records every stop of a step. A Stop that a hook raises is that hook's own error: from check or plan it reaches the caller, from settle it is that kind's SETTLE_STOPPED line
def _named(e) -> str:   # an error's class by the name Python holds for it, read from the type itself so that no code of the class runs; a name that is not plain (exact text of ASCII letters, digits and underscores that does not start with a digit; the empty name is not plain) is 'unreadable'. Never the message of the error
    n=type.__dict__['__name__'].__get__(type(e));return n if type(n) is str and n.isascii() and n.isidentifier() else 'unreadable'


ACTIONS: dict = {}   # action kind -> {'run': handler(state, method, method_id, deps) -> receipt detail, plus optional hooks}. Reviewed code registers; packs cannot.
def register(kind: str, **hooks):   # hooks are reviewed code like handlers. check(method): refuse a malformed method by raising when its pack is applied.
    if set(hooks)-{'check','plan','settle'}:raise ValueError('Unknown hook')   # plan(state, method) -> 'wait' while the method's effect is pending: the plan waits on it instead of running it.
    def add(fn):                                                               # settle(state, result, log): keep the kind's own books at the end of an executed run.
        if kind in ACTIONS:raise ValueError('Action kind already registered')
        ACTIONS[kind]=dict(hooks,run=fn);return fn
    return add

def _amount(v) -> bool:   # a whole number, not negative and below 10**18, so no sum the kernel makes of amounts outgrows what every Python prints (fractions drift between admission and the step-by-step gate; NaN poisons a budget)
    return type(v) is int and 0<=v<10**18

@register('simulate_fact')
def _simulate_fact(s, m, mid, deps):
    if not s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':f'LOCAL_MODEL:{mid}','version':'local-sim-1',
                      'evidence_kind':'SIMULATED_LOCAL', 'depends_on':deps}):raise Stop('A decision stands on this effect')
    return {'model_effect':m['effect']}


@dataclass
class State:
    scope: str = 'orgA/fulfillment'
    goals: list[str] = field(default_factory=list)
    evidence: dict[str, dict] = field(default_factory=dict)
    rules: dict[str, dict] = field(default_factory=dict)
    proposed_rules: dict[str, dict] = field(default_factory=dict)
    methods: dict[str, dict] = field(default_factory=dict)
    providers: dict[str, int] = field(default_factory=dict)
    grants: set[str] = field(default_factory=set)
    budget: dict[str, int] = field(default_factory=lambda: {'compute': 10, 'money': 10, 'attention': 3})
    preference: list[str] = field(default_factory=lambda: ['compute', 'money', 'attention'])
    constructor_specs: dict[str, dict] = field(default_factory=dict)
    candidates: dict[str, dict] = field(default_factory=dict)
    loaded: list[dict] = field(default_factory=list)
    event_journal: list[dict] = field(default_factory=list)
    active_work: dict[str, dict] = field(default_factory=dict)   # the books each kind keeps between runs (kind -> its entries)
    actions: dict = field(default_factory=lambda: {k:dict(v) for k,v in ACTIONS.items()})   # the registry as it stood when this State was built

    def apply(self, pack: dict) -> None:
        """All or nothing: a pack that fails any check is refused with ValueError and leaves the State as it was. The State keeps its own plain copy of the pack."""
        trial=copy.deepcopy(self,{id(self.actions):self.actions})   # the registry is shared, never copied
        try:trial._apply(plain(pack,18))   # two levels more than a row gets alone, so a row may nest as deep in a pack as in an event
        except (AttributeError,TypeError,KeyError) as e:raise ValueError(f'Invalid extension pack: {e!r}') from None   # a section or an entry of the wrong shape
        self.__dict__.update(trial.__dict__)

    def _apply(self, pack: dict) -> None:
        if pack.get('schema') != 'sutra-extension/2' or type(pack.get('id')) is not str or not pack['id']:
            raise ValueError('Invalid extension pack')
        if any(not isinstance(pack.get(k,[]),list) or any(not isinstance(x,str) for x in pack.get(k,[])) for k in ('goals','grants','revoke_grants')):
            raise ValueError('Goals and grants are lists of names')
        if 'scope' in pack:
            if not isinstance(pack['scope'],str) or not pack['scope'] or '|' in pack['scope']:raise ValueError('Invalid scope')
            self.scope = pack['scope']
        if 'goals' in pack:
            self.goals = list(pack['goals'])
        for o in pack.get('evidence', []):self.observe(o)
        for r in pack.get('rules', []):
            if (not isinstance(r.get('id'),str) or not r['id'] or not isinstance(r.get('head'),str) or not r['head'] or not isinstance(r.get('branches'),list) or not r['branches']
                    or any(not isinstance(b,list) or not b or any(not isinstance(c,str) for c in b) for b in r['branches']) or type(r.get('approved',False)) is not bool):
                raise ValueError('Invalid domain rule')
            if not r.get('approved', False):
                self.proposed_rules[r['head']] = dict(r, status='PROPOSED_ONLY')
                continue
            old = self.rules.get(r['head'])
            if old and r.get('replaces') != old['id']:
                raise ValueError('Rules must cite replaced rule ID')
            self.rules[r['head']] = dict(r)
        for m in pack.get('methods', []):
            if m.get('action') not in self.actions:
                raise ValueError('Untrusted or unknown action kind')
            if (not all(isinstance(m.get(k),str) and m[k] for k in ('id','effect','grant','provider')) or not isinstance(m.get('cost',{}),dict)
                    or not isinstance(m.get('requires',[]),list) or any(not isinstance(r,str) for r in m.get('requires',[])) or len(m.get('requires',[]))>10000 or type(m.get('approved',True)) is not bool):
                raise ValueError('A method needs an id, an effect, a grant and a provider, and at most 10000 prerequisites')   # so the row its step writes stays inside the door's bound
            if m['id'] in self.methods:
                raise ValueError('Duplicate method ID')
            if any(not _amount(v) for v in m.get('cost',{}).values()):
                raise ValueError('Negative resource cost')
            self.methods[m['id']] = dict(m)
        for cs in pack.get('constructors', []):
            self.constructor_specs[cs['id']] = cs
        if any(not isinstance(k,str) or not _amount(v) for k,v in pack.get('providers', {}).items()):
            raise ValueError('Negative provider capacity')
        self.providers.update(pack.get('providers', {}))
        self.grants.update(pack.get('grants', []))
        self.grants.difference_update(pack.get('revoke_grants', []))
        if 'budget' in pack:
            if any(not isinstance(k,str) or not _amount(v) for k,v in pack['budget'].items()):
                raise ValueError('Negative budget')
            self.budget.update(pack['budget'])
        if 'preference' in pack:
            if type(pack['preference']) is not list or set(pack['preference']) != set(self.budget):
                raise ValueError('Preference must cover each resource dimension')
            self.preference = pack['preference']
        if any(dim not in self.budget for m in self.methods.values() for dim in m.get('cost',{})):
            raise ValueError('A cost names a dimension the budget does not have')
        for m in pack.get('methods', []):   # a kind's own check runs last, on a copy, after every structural check has passed
            if self.actions[m['action']].get('check'):self.actions[m['action']]['check'](copy.deepcopy(m))
        self.loaded.append({'pack':pack['id'],'sha256':digest(pack)})

    @classmethod
    def from_packs(cls, packs:list[dict])->'State':
        state=cls()
        for pack in packs:state.apply(pack)
        return state

    def key(self, predicate: str, scope: str | None = None) -> str:
        return f'{scope or self.scope}|{predicate}'

    def fact(self, predicate: str) -> dict:
        """Versioned, transitively invalidated scoped evidence. Missing proofs stay UNKNOWN."""
        def inspect(p: str, seen: set[str]) -> dict:
            if p in seen:
                return {'truth':'UNKNOWN','verified':False,'reason':'dependency cycle'}
            key=self.key(p)
            row=self.evidence.get(key)
            if row is None:return {'truth':'UNKNOWN','verified':False,'reason':'no evidence'}
            if not row.get('verified',False):return {'truth':'UNKNOWN','verified':False,'reason':'unverified'}
            for dep in row.get('depends_on', []):
                required=dep.get('version')
                other=inspect(dep['predicate'],seen|{p})
                if not other.get('verified',False) or canonical(other.get('version'))!=canonical(required) or other.get('truth')!='TRUE':   # versions compare as JSON text: 1 and 1.0 are two versions
                    return {'truth':'UNKNOWN','verified':False,'reason':'dependency invalidated'}
            return row
        return copy.deepcopy(inspect(predicate,set()))   # a copy: the stored row changes only through observe

    def observe(self, row:dict)->bool:
        row=plain(row);deps=row.get('depends_on',[]);scope=row.get('scope',self.scope)   # the State's own plain copy, made before any check reads it
        if (row.get('truth') not in ('TRUE','FALSE','UNKNOWN') or not isinstance(row.get('predicate'),str) or not isinstance(deps,list)
                or any(not isinstance(d,dict) or not isinstance(d.get('predicate'),str) or isinstance(d.get('version'),(dict,list,bool)) for d in deps) or not isinstance(scope,str) or not scope or '|' in scope
                or type(row.get('verified',False)) is not bool or type(row.get('final',False)) is not bool or isinstance(row.get('version'),(dict,list,bool))):   # a version is a name or a number: the row's own and each one it rests on
            raise ValueError('Invalid observation')
        if row.get('final') and (row['truth']=='UNKNOWN' or deps):
            raise ValueError('A decision is a TRUE or FALSE row that rests on nothing else')
        key=self.key(row['predicate'],scope)
        if not row.get('verified',False):return False   # an unverified row is ignored
        if self.evidence.get(key,{}).get('final') and not row.get('final'):   # a decision stands until another decision replaces it, and the journal says what was turned away
            self.event_journal.append({'status':'DECISION_STANDS','scope':scope,'predicate':row['predicate']});return False
        self.evidence[key] = dict(row,scope=scope);return True


class Kernel:
    """Stable recursive evaluator: observe -> derive -> compare -> plan -> gate -> act -> verify record."""
    RANK=['SEMANTICS_MISSING','SEMANTICS_UNAPPROVED','EVIDENCE_CONFLICT','REFUSED','QUERY_EVIDENCE',   # which stop reason names a blocked run
          'AUTHORITY_REQUIRED','PROVIDER_REQUIRED','RESOURCE_REQUIRED','METHOD_ABSENT','CYCLE_LIMIT']
    def __init__(self,state:State):
        self.s=state
        self.events=[]
        self.limit=20

    def log(self, op:str, **data)->None:
        prev = self.events[-1]['sha256'] if self.events else 'GENESIS'
        row={'seq':len(self.events)+1,'prev_sha256':prev,'operation':op,'data':data}
        row['sha256']=digest(row)
        self.events.append(row)

    def _single(self, actions=(), needs=(), proof=(), branch='', scope=None):
        return {'actions':list(actions),'needs':list(needs),'proof':list(proof),'branch':branch,
                'scope':scope or self.s.scope}

    def _merge(self, a, b):
        actions=list(dict.fromkeys(a['actions']+b['actions']))
        return dict(self._single(actions, list(dict.fromkeys(a['needs']+b['needs'])),
                            a['proof']+b['proof'],a['branch'] or b['branch']),waits=list(dict.fromkeys(a.get('waits',[])+b.get('waits',[]))))

    def expand(self, pred:str, ancestors=(), depth=0, root=False):
        if pred in ancestors or depth >= self.limit:
            self.log('CYCLE_LIMIT',predicate=pred)
            return [], ['CYCLE_LIMIT']
        evidence=self.s.fact(pred)
        if evidence['truth']=='TRUE':
            self.log('RETAIN',predicate=pred,source=evidence.get('source'),version=evidence.get('version'))
            return [self._single(proof=[f'{pred} observed TRUE ({evidence.get("source")})'])], []
        if evidence['truth']=='FALSE' and evidence.get('final'):   # a decision, not a state of the world: no rule and no method may overturn it
            self.log('REFUSED',predicate=pred,source=evidence.get('source'))
            return [], ['REFUSED']
        next_path=ancestors+(pred,)
        rule=self.s.rules.get(pred)
        if rule:
            self.log('REFINE',predicate=pred,rule=rule['id'],alternatives=len(rule['branches']))
            all_plans=[]; blocks=[]
            for i, children in enumerate(rule['branches']):
                partial=[self._single(proof=[f'{pred} ⇐ {rule["id"]}: alternative {i+1}'],branch=f'{rule["id"]}/OR{i+1}')]
                for child in children:
                    pp, bb=self.expand(child,next_path,depth+1)
                    blocks+=bb
                    partial=[self._merge(a,b) for a in partial for b in pp]
                    if not partial:break
                all_plans+=partial
            if evidence['truth']=='FALSE' and any(not p['actions'] and not p.get('waits') for p in all_plans):
                self.log('EVIDENCE_CONFLICT',predicate=pred)
                return [], blocks+['EVIDENCE_CONFLICT']
            return all_plans,blocks
        if root and pred not in {m['effect'] for m in self.s.methods.values()}:
            kind='SEMANTICS_UNAPPROVED' if pred in self.s.proposed_rules else 'SEMANTICS_MISSING'
            self.log(kind,predicate=pred)
            return [], [kind]
        matches=[(m,(self.s.actions[m['action']].get('plan') or (lambda s,m:None))(self.s,m)) for m in self.s.methods.values() if m['effect']==pred and m.get('approved',True)]
        if not matches:
            reason='QUERY_EVIDENCE' if evidence['truth']=='UNKNOWN' else 'METHOD_ABSENT'
            self.log(reason,predicate=pred)
            return [],[reason]
        plans=[]; blocks=[]
        for m,how in matches:   # how=='wait': the kind says this method's effect is pending, so the plan waits on it and needs none of its prerequisites
            self.log('METHOD_PENDING' if how=='wait' else 'METHOD_MATCH',predicate=pred,method=m['id'])
            partial=[self._single(needs=[pred],proof=[f'{m["id"]} is pending for {pred}' if how=='wait' else f'{m["id"]} would establish {pred}'])]
            for req in ([] if how=='wait' else m.get('requires',[])):
                sub,bb=self.expand(req,next_path,depth+1)
                blocks+=bb
                partial=[self._merge(a,b) for a in partial for b in sub]
                if not partial:break
            for plan in partial:
                if how=='wait':plan['waits']=list(dict.fromkeys(plan.get('waits',[])+[m['id']]))
                elif m['id'] not in plan['actions']:plan['actions'].append(m['id'])
                plans.append(plan)
        return plans,blocks

    def cost(self,p):
        costs={k:0 for k in self.s.budget}
        for mid in p['actions']:
            m=self.s.methods[mid]
            for k in costs:costs[k]+=m.get('cost',{}).get(k,0)
        return costs

    def admissible(self, p):
        reason=[]; cost=self.cost(p)
        for k,v in cost.items():
            if v > self.s.budget[k]:reason.append('RESOURCE_REQUIRED')
        use={}
        for mid in p['actions']:
            m=self.s.methods[mid]
            if m.get('grant') and m['grant'] not in self.s.grants:reason.append('AUTHORITY_REQUIRED')
            if m.get('provider'):
                provider=m['provider'];use[provider]=use.get(provider,0)+1
        for provider,n in use.items():
            if self.s.providers.get(provider,0)<n:reason.append('PROVIDER_REQUIRED')
        self.log('ADMISSION',methods=p['actions'],accepted=not reason,blockers=sorted(set(reason)),cost=cost)
        return sorted(set(reason))

    def _dominates(self,p,q):
        a=self.cost(p);b=self.cost(q)
        return all(a[k]<=b[k] for k in a) and any(a[k]<b[k] for k in a)

    def _step(self, mid, m):   # one step: the gate, the handler's effect, the kernel's receipt and its line in the record, the payment. What stops it raises Stop with a phrase from the closed list; a fault of the kernel's own lines here leaves as its own error, and _act words it
        if (gate:=self.admissible(self._single(actions=[mid]))):raise Stop('Gate changed before effect: '+' '.join(gate))
        if (missing:=[p for p in m.get('requires',[]) if self.s.fact(p)['truth']!='TRUE']):raise Stop('Prerequisite not true before effect: '+' '.join(missing))
        deps=[{'predicate':pre,'version':self.s.fact(pre).get('version')} for pre in m.get('requires',[])];run=self.s.actions[m['action']]['run']
        try:detail=run(self.s,m,mid,deps)   # the effect is the handler's; the gate above and the record below are the kernel's
        except Exception as e:raise Stop('Handler refused: '+e.args[0].encode('utf-8','backslashreplace').decode() if type(e) is Stop and len(e.args)==1 and type(e.args[0]) is str else 'Handler failed: '+_named(e)) from None   # its own words only when it raised Stop with one text
        try:
            detail=plain(detail)   # rebuilt as plain data like everything that is handed in: no code of the handler runs after it returned
            if set(detail)&{'method','scope','action','status','sha256'}:raise ValueError
        except ValueError:raise Stop('Handler returned what cannot be a receipt') from None
        rec={'method':mid,'scope':self.s.scope,'action':m['action'],'status':'LOCAL_ONLY',**detail};rec['sha256']=digest(rec)
        left={d:self.s.budget[d]-v for d,v in m.get('cost',{}).items()};slot={p:self.s.providers[p]-1 for p in [m.get('provider')] if p}   # every entry is read before one is written: a step is paid in full or not at all
        self.log('LOCAL_EFFECT',receipt=rec);self.s.budget.update(left);self.s.providers.update(slot)   # paid after its receipt is in the record: a stopped step is never paid
        return rec

    def _act(self, plan):
        receipts=[]
        for mid in plan['actions']:
            try:
                m=self.s.methods[mid];seen=self.s.fact(m['effect'])
                if seen['truth']=='TRUE':   # already true at its turn (an earlier step brought its row back): nothing to make, nothing to pay, one line in the record
                    self.log('STEP_ALREADY_TRUE',method=mid,effect=m['effect'],source=seen.get('source'),version=seen.get('version'));continue
                receipts.append(self._step(mid,m))
            except Exception as e:   # a step that stops is an outcome, not an exception: one line in the record, and the run ends here
                try:reads=self.s.fact(self.s.methods[mid]['effect'])['truth']
                except Exception:reads='UNKNOWN'   # the effect cannot be read (its method is gone, say): the line is written all the same
                self.log('STEP_STOPPED',method=mid,reason=e.args[0] if type(e) is Stop else 'Kernel fault: '+_named(e),effect_reads=reads);break
            if receipts[-1].get('parked'):break   # the step parked (its effect is pending): nothing after it runs
        return receipts

    def resolve(self, goal:str, execute=False)->dict:
        if type(goal) is not str or type(execute) is not bool:raise ValueError('A goal is a name, and execute is true or false')
        self.events=[];self.log('GOAL_ACCEPTED',goal=goal,scope=self.s.scope)
        plans, blockers=self.expand(goal,root=True)
        eligible=[]
        for p in plans:
            blocked=self.admissible(p)
            if not blocked:eligible.append(p)
            else:blockers+=blocked
        result={'goal':goal,'scope':self.s.scope,'goal_truth_before':self.s.fact(goal)['truth'],
                'work_state':'blocked','actions':[],'needs':[],'cost':None,'proof':[],
                'model_receipts':[],'candidates':[],'selected_branch':None,
                'stop_reasons':sorted(set(blockers)), 'provenance':copy.deepcopy(self.s.loaded)}
        if eligible:
            frontier=[p for p in eligible if not any(self._dominates(q,p) for q in eligible)]
            selected=min(frontier,key=lambda p:tuple(self.cost(p)[dim] for dim in self.s.preference)+(len(p.get('waits',())),tuple(p['actions'])))
            self.log('SELECT',actions=selected['actions'],full_cost=self.cost(selected),pareto_options=len(frontier),**({'waits':selected['waits']} if selected.get('waits') else {}))
            result.update(status='PLAN_READY',work_state='ready',actions=selected['actions'],
                          needs=selected['needs'],cost=self.cost(selected),proof=selected['proof'],
                          selected_branch=selected['branch'],stop_reasons=[],pareto_options=len(frontier))
            if selected.get('waits'):   # the best plan is to keep waiting for what is pending: nothing runs
                result.update(status='WAITING',work_state='waiting',actions=[],pending=selected['actions'],cost=self.cost({'actions':[]}),
                              waits=selected['waits'],**({'goal_truth_after':self.s.fact(goal)['truth']} if execute else {}))
            elif execute:
                receipts=result['model_receipts']=self._act(selected);ran=[x['method'] for x in receipts]   # what ran: the plan, less any step already true at its turn
                skipped=[e['data']['method'] for e in self.events if e['operation']=='STEP_ALREADY_TRUE']
                result.update(status='LOCAL_MODEL_EFFECTS_RECORDED' if ran else 'SUPPORTED_BY_EVIDENCE',work_state='completed',actions=ran,cost=self.cost({'actions':ran}),**({'skipped':skipped} if skipped else {}))
                # Results are not independently certified external business outcomes.
                stop=next((e['data'] for e in self.events if e['operation']=='STEP_STOPPED'),None)
                if stop:   # a step stopped: what ran is reported and paid; the stopped step and the rest of the plan are pending
                    result.update(status='STEP_STOPPED',work_state='stopped',pending=selected['actions'][selected['actions'].index(stop['method']):],
                                  goal_truth_after=self.s.fact(goal)['truth'],stopped={'method':stop['method'],'reason':stop['reason']})
                elif receipts and receipts[-1].get('parked'):   # a step parked: only what ran is reported; the rest of the plan is pending
                    result.update(status='WAITING',work_state='waiting',pending=selected['actions'][selected['actions'].index(ran[-1])+1:],
                                  goal_truth_after=self.s.fact(goal)['truth'],waits=[ran[-1]])
                else:result['goal_truth_after']='MODEL_DERIVABLE_NOT_EXTERNAL_PROOF' if ran else self.s.fact(goal)['truth']
        else:
            status=next((x for x in self.RANK if x in blockers),'METHOD_ABSENT')
            self.log('BLOCK',reason=status,all_reasons=sorted(set(blockers)))
            result.update(status=status,pareto_options=0)
        if execute:   # each kind settles its own books inside this run's hash chain; a kind whose settle fails is named, and the others still settle
            for name,kind in list(self.s.actions.items()):   # a list: a hook that changes the registry does not end the settling
                try:kind.get('settle') and kind['settle'](self.s,result,self.log)
                except Exception as e:self.log('SETTLE_STOPPED',kind=name,reason=_named(e));result.setdefault('unsettled',[]).append(name)
        result['candidates']=copy.deepcopy(list(self.s.candidates.values()))
        self.log('TERMINAL',status=result['status'],work_state=result['work_state'])
        result['trace']=list(self.events)
        result['trace_root_sha256']=self.events[-1]['sha256']
        result['claim']='LOCAL_REFERENCE_ONLY; never external success or current J2 implementation'
        self.s.event_journal.append({'goal':goal,'scope':self.s.scope,'status':result['status'],
                                    'trace_root_sha256':result['trace_root_sha256']})
        return result

    def on_event(self, observation:dict, execute=False):
        if type(execute) is not bool:raise ValueError('execute is true or false')   # refused before the row is stored
        observation=plain(observation)
        if not self.s.observe(observation):   # ignored as unverified, or turned away by a standing decision (State.observe wrote that journal row); a malformed row is refused, as in a pack
            return {'status':'DECISION_STANDS' if observation.get('verified') else 'UNVERIFIED_EVENT_IGNORED','affected':[],'runs':[]}
        event_scope=observation.get('scope',self.s.scope)
        if event_scope!=self.s.scope:
            return {'status':'OUT_OF_SCOPE','affected':[],'runs':[]}
        changed=observation['predicate']
        def depends(p,seen):
            if p==changed:return True
            if p in seen:return False
            seen.add(p)
            r=self.s.rules.get(p)
            if r and any(depends(ch,set(seen)) for branch in r['branches'] for ch in branch):return True
            if any(depends(pre,set(seen)) for m in self.s.methods.values() if m['effect']==p for pre in m.get('requires',[])):
                return True
            evidence=self.s.evidence.get(self.s.key(p))
            return bool(evidence and any(dep.get('predicate')==changed for dep in evidence.get('depends_on',[])))
        affected=[g for g in self.s.goals if depends(g,set())]
        return {'status':'RECONCILED','event':observation,'affected':affected,
                'runs':[self.resolve(g,execute=execute) for g in affected]}

    def run_standing(self,execute=False):
        if type(execute) is not bool:raise ValueError('execute is true or false')
        return {'status':'EVALUATED' if self.s.goals else 'NO_STANDING_GOAL',
                'goals':list(self.s.goals),'runs':[self.resolve(g,execute=execute) for g in self.s.goals]}
