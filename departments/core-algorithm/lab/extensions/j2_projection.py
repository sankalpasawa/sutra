"""Read-only J2-shaped proposal for later adapter development; NEVER calls or modifies J2."""
from kernel.core import digest

def to_j2_proposed_atom_views(result:dict)->dict:
    items=[]
    for i,method_id in enumerate(result.get('actions',[]),1):
        items.append({'id':f'EXPERIMENT-A{i}', 'workflow':'EXPERIMENT-W1', 'name':method_id,
            'owner':'experimental-kernel','status':'open','attempt':0,
            'goal':{'text':result['goal']},'how':{'method':method_id},
            'constraints':['LOCAL_REFERENCE_ONLY','NOT_J2_EXECUTED'],
            'context':{'scope':result['scope'],'source_trace':result.get('trace_root_sha256')},
            'defined_output':{'predicate':method_id},
            'verification':[{'check':'independent-J2-verification-NOT_RUN','applies_to':method_id,
                             'method':'future adapter','met':False,'evidence':None}],
            'output':[], 'depends_on':[], 'used_by':[],
            'notes':'Planning projection only. Not an observed J2 Work-Atom.'})
    return {'schema':'atom/1','atoms':items,'warnings':['EXPERIMENTAL PROJECTION; NOT J2 generated data'],
            'projection_sha256':digest(items)}
