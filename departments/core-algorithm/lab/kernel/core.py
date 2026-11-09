"""Sutra One-Kernel Extension Lab 0.2: finite, deterministic, local reference.
The kernel is held constant across scenarios. All external effects are prohibited.
It does NOT implement current production Native/J2 or replace historical Sutra Core.
"""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, field
from typing import Any


def canonical(v: Any) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(v: Any) -> str:
    return hashlib.sha256(canonical(v).encode()).hexdigest()


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
    learning: bool = False
    loaded: list[dict] = field(default_factory=list)
    event_journal: list[dict] = field(default_factory=list)
    learned_signatures: dict[str, int] = field(default_factory=dict)
    active_work: dict[str, str] = field(default_factory=dict)
    goal_history: list[dict] = field(default_factory=list)

    def apply(self, pack: dict) -> None:
        if pack.get('schema') != 'sutra-extension/2' or not pack.get('id'):
            raise ValueError('Invalid extension pack')
        if 'scope' in pack:
            self.scope = str(pack['scope'])
        if 'goals' in pack:
            self.goals = list(pack['goals'])
        for o in pack.get('evidence', []):
            if o.get('truth') not in ('TRUE','FALSE','UNKNOWN'):
                raise ValueError('Invalid truth')
            key = self.key(o['predicate'], o.get('scope',self.scope))
            if o.get('verified', False):
                self.evidence[key] = dict(o, scope=o.get('scope', self.scope))
        for r in pack.get('rules', []):
            if not r.get('id') or not r.get('head') or not r.get('branches') or any(not b for b in r['branches']):
                raise ValueError('Invalid domain rule')
            if not r.get('approved', False):
                self.proposed_rules[r['head']] = dict(r, status='PROPOSED_ONLY')
                continue
            old = self.rules.get(r['head'])
            if old and r.get('replaces') != old['id']:
                raise ValueError('Rules must cite replaced rule ID')
            self.rules[r['head']] = dict(r)
        for m in pack.get('methods', []):
            if m.get('action') not in ('simulate_fact','emit_artifact','compile_candidate'):
                raise ValueError('Untrusted or unknown action kind')
            if m['id'] in self.methods:
                raise ValueError('Duplicate method ID')
            if any(v < 0 for v in m.get('cost',{}).values()):
                raise ValueError('Negative resource cost')
            self.methods[m['id']] = dict(m)
        for cs in pack.get('constructors', []):
            self.constructor_specs[cs['id']] = cs
        if any(v < 0 for v in pack.get('providers', {}).values()):
            raise ValueError('Negative provider capacity')
        self.providers.update(pack.get('providers', {}))
        self.grants.update(pack.get('grants', []))
        self.grants.difference_update(pack.get('revoke_grants', []))
        if 'budget' in pack:
            if any(v < 0 for v in pack['budget'].values()):
                raise ValueError('Negative budget')
            self.budget.update(pack['budget'])
        if 'preference' in pack:
            if set(pack['preference']) != set(self.budget):
                raise ValueError('Preference must cover each resource dimension')
            self.preference = pack['preference']
        if 'learning' in pack:
            self.learning = bool(pack['learning'])
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
                if not other.get('verified',False) or other.get('version')!=required or other.get('truth')!='TRUE':
                    return {'truth':'UNKNOWN','verified':False,'reason':'dependency invalidated'}
            return row
        return inspect(predicate,set())

    def observe(self, row:dict)->None:
        if row.get('truth') not in ('TRUE','FALSE','UNKNOWN'):
            raise ValueError('Invalid observation')
        if row.get('verified',False):
            self.evidence[self.key(row['predicate'],row.get('scope',self.scope))] = dict(row,scope=row.get('scope',self.scope))


class Kernel:
    """Stable recursive evaluator: observe -> derive -> compare -> plan -> gate -> act -> verify record."""
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
        return self._single(actions, list(dict.fromkeys(a['needs']+b['needs'])),
                            a['proof']+b['proof'],a['branch'] or b['branch'])

    def expand(self, pred:str, ancestors=(), depth=0, root=False):
        if pred in ancestors or depth >= self.limit:
            self.log('CYCLE_LIMIT',predicate=pred)
            return [], ['CYCLE_LIMIT']
        evidence=self.s.fact(pred)
        if evidence['truth']=='TRUE':
            self.log('RETAIN',predicate=pred,source=evidence.get('source'),version=evidence.get('version'))
            return [self._single(proof=[f'{pred} observed TRUE ({evidence.get("source")})'])], []
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
            if evidence['truth']=='FALSE' and any(not p['actions'] for p in all_plans):
                self.log('EVIDENCE_CONFLICT',predicate=pred)
                return [], blocks+['EVIDENCE_CONFLICT']
            return all_plans,blocks
        if root and pred not in {m['effect'] for m in self.s.methods.values()}:
            kind='SEMANTICS_UNAPPROVED' if pred in self.s.proposed_rules else 'SEMANTICS_MISSING'
            self.log(kind,predicate=pred)
            return [], [kind]
        matches=[m for m in self.s.methods.values() if m['effect']==pred and m.get('approved',True)]
        if not matches:
            reason='QUERY_EVIDENCE' if evidence['truth']=='UNKNOWN' else 'METHOD_ABSENT'
            self.log(reason,predicate=pred)
            return [],[reason]
        plans=[]; blocks=[]
        for m in matches:
            self.log('METHOD_MATCH',predicate=pred,method=m['id'])
            partial=[self._single(needs=[pred],proof=[f'{m["id"]} would establish {pred}'])]
            for req in m.get('requires',[]):
                sub,bb=self.expand(req,next_path,depth+1)
                blocks+=bb
                partial=[self._merge(a,b) for a in partial for b in sub]
                if not partial:break
            for plan in partial:
                if m['id'] not in plan['actions']:plan['actions'].append(m['id'])
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

    def _act(self, plan):
        receipts=[]
        for mid in plan['actions']:
            m=self.s.methods[mid]
            only=self._single(actions=[mid])
            if self.admissible(only):
                raise RuntimeError('Gate changed before effect')
            action=m['action']
            deps=[{'predicate':pre,'version':self.s.fact(pre).get('version')} for pre in m.get('requires',[]) if self.s.fact(pre)['truth']=='TRUE']
            if action=='compile_candidate':
                spec=self.s.constructor_specs.get(m.get('constructor'))
                if not spec:raise RuntimeError('No declared constructor')
                composed=spec.get('components',[])
                if not composed or any(c not in self.s.methods for c in composed):
                    raise RuntimeError('Components unavailable')
                required=set(spec.get('required_effects',[]))
                produced={self.s.methods[c]['effect'] for c in composed}
                candidate={'id':spec['id'],'components':composed,'effect':spec['target_effect'],
                           'required_effects':sorted(required),'observed_effects':sorted(produced),
                           'status':'PROPOSED_ONLY','valid_contract':required <= produced,
                           'provenance':spec.get('source','fixture')}
                self.s.candidates[spec['id']]=candidate
                detail={'candidate_sha256':digest(candidate),'contract_valid':candidate['valid_contract']}
            elif action=='emit_artifact':
                payload=canonical({'title':m.get('artifact_title',mid),'scope':self.s.scope,'method':mid})
                detail={'artifact_text':payload,'artifact_sha256':hashlib.sha256(payload.encode()).hexdigest()}
                self.s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':f'LOCAL_ARTIFACT:{mid}',
                                'version':'local-sim-1','evidence_kind':'SIMULATED_LOCAL', 'depends_on':deps})
            else:
                self.s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,
                                'source':f'LOCAL_MODEL:{mid}','version':'local-sim-1',
                                'evidence_kind':'SIMULATED_LOCAL', 'depends_on':deps})
                detail={'model_effect':m['effect']}
            for dim,v in m.get('cost',{}).items():self.s.budget[dim]-=v
            if m.get('provider'):self.s.providers[m['provider']]-=1
            rec={'method':mid,'scope':self.s.scope,'action':action,'status':'LOCAL_ONLY',**detail}
            rec['sha256']=digest(rec)
            self.log('LOCAL_EFFECT',receipt=rec)
            receipts.append(rec)
        return receipts

    def resolve(self, goal:str, execute=False)->dict:
        self.events=[];self.log('GOAL_ACCEPTED',goal=goal,scope=self.s.scope)
        plans, blockers=self.expand(goal,root=True)
        eligible=[]
        for p in plans:
            blocked=self.admissible(p)
            if not blocked:eligible.append(p)
            else:blockers+=blocked
        result={'goal':goal,'scope':self.s.scope,'goal_truth_before':self.s.fact(goal)['truth'],
                'work_state':'blocked','actions':[],'needs':[],'cost':None,'proof':[],
                'model_receipts':[],'learning':[],'candidates':[],'selected_branch':None,
                'stop_reasons':sorted(set(blockers)), 'provenance':list(self.s.loaded)}
        if eligible:
            frontier=[p for p in eligible if not any(self._dominates(q,p) for q in eligible)]
            selected=min(frontier,key=lambda p:tuple(self.cost(p)[dim] for dim in self.s.preference)+(tuple(p['actions']),))
            self.log('SELECT',actions=selected['actions'],full_cost=self.cost(selected),pareto_options=len(frontier))
            result.update(status='PLAN_READY',work_state='ready',actions=selected['actions'],
                          needs=selected['needs'],cost=self.cost(selected),proof=selected['proof'],
                          selected_branch=selected['branch'],stop_reasons=[],pareto_options=len(frontier))
            if execute:
                result['model_receipts']=self._act(selected)
                result['status']='LOCAL_MODEL_EFFECTS_RECORDED' if selected['actions'] else 'SUPPORTED_BY_EVIDENCE'
                result['work_state']='completed'
                # Results are not independently certified external business outcomes.
                if selected['actions']:
                    result['goal_truth_after']='MODEL_DERIVABLE_NOT_EXTERNAL_PROOF'
                else:result['goal_truth_after']=self.s.fact(goal)['truth']
        else:
            rank=['SEMANTICS_MISSING','SEMANTICS_UNAPPROVED','EVIDENCE_CONFLICT','QUERY_EVIDENCE',
                  'AUTHORITY_REQUIRED','PROVIDER_REQUIRED','RESOURCE_REQUIRED','METHOD_ABSENT','CYCLE_LIMIT']
            status=next((x for x in rank if x in blockers),'METHOD_ABSENT')
            self.log('BLOCK',reason=status,all_reasons=sorted(set(blockers)))
            result.update(status=status,pareto_options=0)
        if self.s.learning:
            signature=' -> '.join(result['actions'])
            if result.get('status')=='LOCAL_MODEL_EFFECTS_RECORDED' and signature:
                n=self.s.learned_signatures.get(signature,0)+1
                self.s.learned_signatures[signature]=n
                candidate={'kind':'REUSE_COMPOSITION','signature':signature,'observations':n,
                           'status':'PROPOSED_ONLY','gate':'independent held-out verification + approval'}
                self.log('LEARN_CANDIDATE',**candidate)
                result['learning']=[candidate]
            elif result['work_state']=='blocked':
                candidate={'kind':'INVESTIGATE_GAP','gap':result['status'],
                           'status':'PROPOSED_ONLY','gate':'independent evidence + authorization'}
                self.log('LEARN_CANDIDATE',**candidate)
                result['learning']=[candidate]
        result['candidates']=list(self.s.candidates.values())
        self.log('TERMINAL',status=result['status'],work_state=result['work_state'])
        result['trace']=list(self.events)
        result['trace_root_sha256']=self.events[-1]['sha256']
        result['claim']='LOCAL_REFERENCE_ONLY; never external success or current J2 implementation'
        self.s.event_journal.append({'goal':goal,'scope':self.s.scope,'status':result['status'],
                                    'trace_root_sha256':result['trace_root_sha256']})
        self.s.goal_history.append({'goal':goal,'status':result['status'],'actions':list(result['actions'])})
        return result

    def on_event(self, observation:dict, execute=False):
        if not observation.get('verified',False):
            return {'status':'UNVERIFIED_EVENT_IGNORED','affected':[],'runs':[]}
        event_scope=observation.get('scope',self.s.scope)
        self.s.observe(observation)
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
        return {'status':'EVALUATED' if self.s.goals else 'NO_STANDING_GOAL',
                'goals':list(self.s.goals),'runs':[self.resolve(g,execute=execute) for g in self.s.goals]}
