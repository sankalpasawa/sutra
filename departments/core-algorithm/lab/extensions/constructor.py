"""Bounded method construction and local artifacts, as action handlers OUTSIDE the kernel (0.7.0-handlers, move-outs M2 + M3).
Importing this module registers the two kinds; a State built from the kernel's own registry rejects packs that use them.
The bodies are the ones that left kernel/core.py: same candidate, same receipts, same hashes.
Handler contract: a handler gets the state, the method, its id and the verified prerequisites; it may write the
evidence of its own method's effect (state.observe) and a PROPOSED_ONLY candidate (state.candidates); it never
touches grants, budget, providers, rules or methods, and it cannot set the receipt's own fields (the kernel refuses)."""
from __future__ import annotations
import hashlib
from kernel.core import register, canonical, digest

@register('compile_candidate')
def compile_candidate(s, m, mid, deps):
    spec=s.constructor_specs.get(m.get('constructor'))
    if not spec:raise RuntimeError('No declared constructor')
    composed=spec.get('components',[])
    if not composed or any(c not in s.methods for c in composed):
        raise RuntimeError('Components unavailable')
    required=set(spec.get('required_effects',[]))
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
    s.observe({'predicate':m['effect'],'truth':'TRUE','verified':True,'source':f'LOCAL_ARTIFACT:{mid}',
               'version':'local-sim-1','evidence_kind':'SIMULATED_LOCAL','depends_on':deps})
    return {'artifact_text':payload,'artifact_sha256':hashlib.sha256(payload.encode()).hexdigest()}
