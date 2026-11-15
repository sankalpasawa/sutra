"""The action kind `handoff` (0.18.0-handoff): work handed to a hand and checked by a separate checker, with tries.

A method of this kind does not make its effect true, and it asks nobody a question. Its step records what is handed
over, to whom, and whose rows check it, and parks the run. The hand (a person, a model, an agent, another session)
does the work outside the kernel. The effect becomes true the way every fact does: a verified row says so. This kind
takes a row as the check of a hand-over only when it comes from the checker the method names and names the receipt
of that hand-over under `checks`. There is no stamp for a hand-off: nobody can say "done" for it.

The books, State.active_work['handoff'][scope|fact] = {method, receipt, issued, checker}: the method that handed the
work over last, the sha256 of the receipt the kernel issued for that try, the receipt itself, and the checker.
  out      from the receipt until the fact reads TRUE or carries a decision.
  waiting  while the work is out and the check of its try has not failed, the plan waits on it, so the same work is
           not handed over twice. A hand-off always costs something and a wait costs nothing, so no other hand-off
           of the same fact is chosen over the wait either.
  failed   the fact reads FALSE on a row of the method's checker that names the receipt of the try that is out.
           The work is then open again: its method is planned as a step like any other, and the kernel's own gate
           says whether another try is admitted (the grant, the budget, a slot of the hand's provider). The kernel
           takes a slot for every try and returns none, so the capacity a pack states for the hand's provider is
           the number of tries. The next receipt carries the number of the try and, under `before`, every earlier
           try with what its check said: that is how the next try is told what happened.
  closed   at the end of an executed run in which the fact reads TRUE or carries a decision: one HANDOFF_CLOSED
           line in that run's hash chain. `confirmed` is true only when the fact reads TRUE on a row of the
           method's checker that names the receipt of the try that is out, and that row is no decision.
The kernel reads any verified row. Who may write one is held at the door, not here: the journal's event door lets in
only rows of the checkers its header names, and no decision. Everything here is a local model: the handler writes no
evidence, opens no file and calls nobody."""
from __future__ import annotations
import copy
from kernel.core import register, digest

KIND = 'handoff'
TOLD = ('truth', 'source', 'version', 'why')   # what a later try is told of the check of an earlier one; `why` only when it is one text


def _check(m):
    named = all(type(m.get(k)) is str and m[k].strip() for k in ('handoff_to', 'instruction', 'verified_by'))
    if not named or m['verified_by'] == m['handoff_to'] or sum(m.get('cost', {}).values()) < 1:
        raise ValueError('A hand-off names who does the work, what to do and whose rows check it (not the hand), and costs something')


def _said(s, entry):
    """What the checker said of the try that is out, or None when it has said nothing of it: the row the fact reads
    from, when that row reads TRUE or FALSE, is no decision, comes from the checker the method names and names the
    receipt of this try under `checks`."""
    seen = s.fact(entry['issued'][KIND]['predicate'])
    mine = seen['truth'] in ('TRUE', 'FALSE') and not seen.get('final') and seen.get('source') == entry['checker'] and seen.get('checks') == entry['receipt']
    return seen if mine else None


def _plan(s, m):
    entry = s.active_work.get(KIND, {}).get(s.key(m['effect']))
    if entry is None or entry['method'] != m['id']:
        return None   # this method has no work out on the fact: it is planned as a step like any other
    return 'wait' if _said(s, entry) is None else None   # out and its check has not failed: wait. A check that passed never comes here: the kernel reads a TRUE row before it asks a kind


def _settle(s, result, log):
    """Keep the books at the end of an executed run, inside its hash chain: record work just handed over, close what reads TRUE or carries a decision."""
    last = result['model_receipts'][-1] if result['model_receipts'] else None
    if last is not None and last['action'] == KIND:
        s.active_work.setdefault(KIND, {})[s.key(last[KIND]['predicate'])] = {'method': last['method'], 'receipt': last['sha256'], 'issued': copy.deepcopy(last),
                                                                              'checker': last[KIND]['verified_by']}
    books = s.active_work.get(KIND, {})
    prefix = s.scope + '|'
    for key, entry in list(books.items()):
        if not key.startswith(prefix):
            continue                # another scope's books are not this run's to touch
        seen = s.fact(key[len(prefix):])
        if seen['truth'] == 'TRUE' or seen.get('final'):
            log('HANDOFF_CLOSED', handoff=key, receipt=entry['receipt'], tries=entry['issued'][KIND]['try'], truth=seen['truth'], source=seen.get('source'),
                version=seen.get('version'), checks=seen.get('checks'), confirmed=_said(s, entry) is not None)
            del books[key]


@register('handoff', check=_check, plan=_plan, settle=_settle)   # the name is written out: the installer reads it from this line
def handoff(s, m, mid, deps):
    entry = s.active_work.get(KIND, {}).get(s.key(m['effect']))
    n, before = 1, []
    if entry is not None:   # the work is handed over again: the receipt says which try this is and what happened to the ones before it
        last, said = entry['issued'][KIND], _said(s, entry)
        told = said and {k: said[k] for k in TOLD if k in said and (k != 'why' or type(said[k]) is str)}
        n, before = last['try'] + 1, last['before'] + [{'try': last['try'], 'to': last['to'], 'receipt': entry['receipt'], 'checked': told}]
    return {KIND: {'predicate': m['effect'], 'to': m['handoff_to'], 'instruction': m['instruction'], 'verified_by': m['verified_by'], 'try': n, 'before': before,
                   'handed_in': digest({'packs': s.loaded, 'runs': s.event_journal})},   # binds the receipt to this State's packs and history, as an ask's receipt is
            'parked': True}


def open_handoffs(state) -> dict:
    """The work that is out in this scope: scope|fact -> {method, receipt, issued, checker, failed}. `issued` is the
    receipt of the try that is out. `failed` is what the checker said of that try when its check failed (the work is
    then open for another try), else None."""
    prefix, out = state.scope + '|', {}
    for key, entry in state.active_work.get(KIND, {}).items():
        if key.startswith(prefix):
            seen = state.fact(key[len(prefix):])
            if seen['truth'] != 'TRUE' and not seen.get('final'):
                out[key] = dict(copy.deepcopy(entry), failed=_said(state, entry))
    return out
