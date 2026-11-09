"""Knowledge compiler, intentionally OUTSIDE the stable kernel.
Reuses reviewed/typed patterns to create rule packs, not new truth from raw text.
"""
from __future__ import annotations
from kernel.core import digest

def compile_pattern(pattern:dict, bindings:dict, approval:dict|None=None)->dict:
    """Translate a typed pattern with slots into a candidate/approved rule extension.
    Approval is an external input; this function never invents it.
    """
    variables=set(pattern.get('slots',[]))
    if set(bindings)!=variables:raise ValueError('Complete typed bindings required')
    def subst(s):
        for key,val in bindings.items():s=s.replace('${'+key+'}',str(val))
        if '${' in s:raise ValueError('Unresolved slot')
        return s
    head=subst(pattern['head'])
    branches=[[subst(v) for v in br] for br in pattern['branches']]
    if not pattern.get('source') or not pattern.get('source_version'):
        raise ValueError('Evidence-backed source and version required')
    approved=bool(approval and approval.get('approved') is True and
                  approval.get('pattern_hash')==digest(pattern) and approval.get('reviewer'))
    rule={'id':f"{pattern['id']}@{pattern['source_version']}",'head':head,'branches':branches,
          'approved':approved,'source':pattern['source'],'source_version':pattern['source_version'],
          'bindings':bindings,'review':approval.get('reviewer') if approved else 'REVIEW_REQUIRED'}
    return {'schema':'sutra-extension/2','id':f"compiled-{pattern['id']}",'rules':[rule]}

def signal_priority(facts:list[dict])->list[dict]:
    """Explicit policy: rank sourced signals by declared decision impact/validity, not LLM confidence."""
    for f in facts:
        if not f.get('source') or 'decision_impact' not in f or 'applicable' not in f:
            raise ValueError('Incomplete signal contract')
    return sorted(facts,key=lambda r:(not r['applicable'],-r['decision_impact'],r['id']))
