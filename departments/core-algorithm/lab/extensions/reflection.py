"""Reflect on immutable local traces, proposing (never installing) new templates and axes.
Since 0.4.0-shrink (program move-out M1) the per-run learning of the kernel lives here too: `Learner`."""
from collections import Counter,defaultdict
from kernel.core import digest

def reflect(runs:list[dict])->dict:
    signatures=Counter(' -> '.join(r.get('actions',[])) for r in runs if r.get('actions'))
    patterns=[]
    for sig,n in sorted(signatures.items()):
        if n>=2:
            relevant=[r for r in runs if ' -> '.join(r['actions'])==sig]
            patterns.append({'kind':'COMPRESSION_CANDIDATE','signature':sig,'support':n,
                             'status':'PROPOSED_ONLY','source_traces':[r['trace_root_sha256'] for r in relevant],
                             'reexpandable':True,'gate':'held-out usefulness, independent checks and external approval'})
    fanins=[]
    for r in runs:
        actions=r.get('actions',[])
        if len(actions)>=3:
            fanins.append({'kind':'DEPENDENCY_PATTERN_CANDIDATE','actions':actions,
                           'status':'PROPOSED_ONLY','source_trace':r['trace_root_sha256'],
                           'gate':'cross-run recurrence, applicability and governance'})
    return {'candidates':patterns+fanins,'candidate_count':len(patterns)+len(fanins),
            'note':'No axis, Method or version is automatically registered.'}

class Learner:
    """Candidate-only learning over run records, outside the kernel (0.4.0-shrink, move-out M1).
    Does what the 0.3.0 kernel's learning block did at the end of resolve: a reuse proposal for an executed
    composition, an investigation proposal for a blocked goal. Enabled by the `learning` flag of the loaded packs
    (the last pack that carries the key wins, as State.apply did; a pack applied to the State later must also be
    given to `apply` here). Contract: ONE Learner per State for the State's whole life, because the repeat count
    lives here now, not on the State. Each list is bound to the kernel's hash-chained record by `learning_record`
    (the run's trace root + the list's sha256). Proposes, never installs."""
    def __init__(self,enabled:bool=True):
        self.enabled=enabled
        self.signatures:dict[str,int]={}

    @classmethod
    def from_packs(cls,packs:list[dict])->'Learner':
        enabled=False
        for p in packs:
            if 'learning' in p:enabled=bool(p['learning'])
        return cls(enabled)

    def apply(self,pack:dict)->None:
        """Follow a pack applied to the State after construction (same last-writer-wins rule)."""
        if 'learning' in pack:self.enabled=bool(pack['learning'])

    def learn(self,result:dict)->list[dict]:
        if not self.enabled:return []
        signature=' -> '.join(result.get('actions',[]))
        if result.get('status')=='LOCAL_MODEL_EFFECTS_RECORDED' and signature:
            n=self.signatures.get(signature,0)+1
            self.signatures[signature]=n
            return [{'kind':'REUSE_COMPOSITION','signature':signature,'observations':n,
                     'status':'PROPOSED_ONLY','gate':'independent held-out verification + approval'}]
        if result.get('work_state')=='blocked':
            return [{'kind':'INVESTIGATE_GAP','gap':result.get('status'),
                     'status':'PROPOSED_ONLY','gate':'independent evidence + authorization'}]
        return []

    def attach(self,run:dict)->dict:
        """Write each run's learning list into the run record, in run order (where the kernel used to put it)."""
        for r in run.get('runs',[]):
            r['learning']=self.learn(r)
            r['learning_record']={'source_trace':r.get('trace_root_sha256'),'learning_sha256':digest(r['learning'])}
        return run

def minimal_graph_diff(before:dict,after:dict)->dict:
    # Design view, NOT real world graph. Stable action IDs support selective comparison.
    b=set(before.get('actions',[]));a=set(after.get('actions',[]))
    return {'retained':sorted(a&b),'added':sorted(a-b),'retired':sorted(b-a),
            'status':'DESIGN_DIFF_ONLY','source_trace_before':before.get('trace_root_sha256'),
            'source_trace_after':after.get('trace_root_sha256')}
