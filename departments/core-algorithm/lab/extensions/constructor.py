"""Bounded method construction and local artifacts, as action handlers OUTSIDE the kernel (0.7.0-handlers, move-outs M2 + M3).
Importing this module registers the two kinds; a State built from the kernel's own registry rejects packs that use them.
The bodies are the ones that left kernel/core.py (0.8.0 added a shape guard on the spec): same candidate, same receipts, same hashes.
Handler contract: a handler gets the state, the method, its id and the verified prerequisites; it may write the
evidence of its own method's effect (state.observe) and a PROPOSED_ONLY candidate (state.candidates); it never
touches grants, budget, providers, rules or methods, and it cannot set the receipt's own fields (the kernel refuses).
Since 0.9.0 a handler refuses in its own words by raising the kernel's Stop with one text (any other error is recorded
by its class), and what it returns is rebuilt as plain data before it becomes a receipt."""
from __future__ import annotations
import hashlib
from kernel.core import register, canonical, digest, Stop

@register('compile_candidate')
def compile_candidate(s, m, mid, deps):
    spec=s.constructor_specs.get(m.get('constructor')) if isinstance(m.get('constructor'),str) else None
    if not spec:raise Stop('No declared constructor')
    composed=spec.get('components',[]);wanted=spec.get('required_effects',[])
    if (not isinstance(composed,list) or not composed or any(not isinstance(c,str) or c not in s.methods for c in composed)
            or not isinstance(wanted,list) or any(not isinstance(e,str) for e in wanted) or not isinstance(spec.get('target_effect'),str)):
        raise Stop('Components unavailable')   # also a spec of the wrong shape: it stops here, before anything is stored
    required=set(wanted)
    produced={s.methods[c]['effect'] for c in composed}
    candidate={'id':spec['id'],'components':composed,'effect':spec['target_effect'],
               'required_effects':sorted(required),'observed_effects':sorted(produced),
               'status':'PROPOSED_ONLY','valid_contract':required <= produced,
               'provenance':spec.get('source','fixture')}
    s.candidates[spec['id']]=candidate
    return {'candidate_sha256':digest(candidate),'contract_valid':candidate['valid_contract']}

@register('emit_artifact')
def emit_artifact(s, m, mid, deps):
    payload=canonical({'title':m.get('artifact_title',mid),'scope':s.scope,'method':mid})
    if not s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':f'LOCAL_ARTIFACT:{mid}',
                      'version':'local-sim-1','evidence_kind':'SIMULATED_LOCAL','depends_on':deps}):raise Stop('A decision stands on this effect')
    return {'artifact_text':payload,'artifact_sha256':hashlib.sha256(payload.encode()).hexdigest()}
