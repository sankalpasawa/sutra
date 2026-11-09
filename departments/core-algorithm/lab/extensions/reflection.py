"""Reflect on immutable local traces, proposing (never installing) new templates and axes."""
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

def minimal_graph_diff(before:dict,after:dict)->dict:
    # Design view, NOT real world graph. Stable action IDs support selective comparison.
    b=set(before.get('actions',[]));a=set(after.get('actions',[]))
    return {'retained':sorted(a&b),'added':sorted(a-b),'retired':sorted(b-a),
            'status':'DESIGN_DIFF_ONLY','source_trace_before':before.get('trace_root_sha256'),
            'source_trace_after':after.get('trace_root_sha256')}
