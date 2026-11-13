"""A human ask as an action kind OUTSIDE the kernel (0.8.0-ask, matrix gap 3).

A method of kind `ask` does not make its effect true. Its step records who is asked and what, and parks the run.
This module keeps the books in State.active_work['ask'][scope|fact] = {method, receipt, issued}: the asking method, the
sha256 of the receipt the kernel issued, and that receipt itself (so a question can always be answered from the books).
  out      a question is out from the receipt the kernel issued until a decision (a final row) is on its fact: the
           stamp (`answer`), or a decision from any other channel. No other evidence closes it. A verified TRUE row
           lets the plan go on without the answer; when that row goes, the plan waits on the same question again.
  waiting  while it is out and its fact does not read TRUE the plan waits on it. The wait needs nothing else (what
           the question was asked on may change or go: the question is still out) and costs nothing, and an ask always
           costs attention, so the kernel's own preference rule never chooses to ask again: one question per fact and
           scope, asked once and paid once. Other ways to the fact that are not asks compete with the wait as any plan does.
  closed   by a decision only: a line in the hash chain of the next executed run in that scope. Until that run the
           entry stays on the books, and the decision already keeps the question from being answered twice.
A question is never withdrawn: it stays answerable whatever the goals and the other evidence do. An answer is a decision
on the fact and takes effect wherever the fact is used: a late yes is one more true fact, a late no blocks the fact for
every route, also one that other evidence had opened. A late yes on a fact that other evidence already made true keeps
that evidence's version, so nothing made on it is undone or paid twice; a late no undoes it.
The stamp is accepted only when the receipt presented equals the one on the books for a question open in the current
scope, and the answer comes from the party that was asked. The answer is a decision (final evidence): a yes lets the
plan continue; a no is a decision no method and no later ordinary row may overturn (the goal takes another route or
stops as REFUSED); only another decision replaces it. A decision rests on nothing else, so it does not lapse when what
the question was asked on changes (a known limit of this version).
An ask needs a grant and a provider like every method, names who is asked, and costs attention, paid once per
question; the provider slot it took is not returned. Dry looks never change the books.
All of this is local simulation: the stamp is an equality check against a deterministic receipt, not an authentication
of the answering party."""
from __future__ import annotations
import copy
from kernel.core import register, digest, canonical, plain


def _check(m):
    attention = m.get('cost', {}).get('attention')
    if (type(m.get('ask_to')) is not str or not m['ask_to'].strip() or type(attention) is not int or attention < 1
            or not isinstance(m.get('question', ''), str)):
        raise ValueError('An ask names who is asked and costs attention')


def _open(s, fact):
    """The question out on a fact in this scope, or None: out from its receipt until a decision is on the fact."""
    entry = s.active_work.get('ask', {}).get(s.key(fact))
    return None if entry is None or s.fact(fact).get('final') else entry


def _plan(s, m):
    entry = _open(s, m['effect'])
    return 'wait' if entry is not None and entry['method'] == m['id'] else None   # asked and not answered: wait, do not ask again


def _settle(s, result, log):
    """Keep the books at the end of an executed run, inside its hash chain: record a question just asked, close the decided ones."""
    last = result['model_receipts'][-1] if result['model_receipts'] else None
    if last is not None and last.get('parked') and isinstance(last.get('ask'), dict):
        s.active_work.setdefault('ask', {})[s.key(last['ask']['predicate'])] = {'method': last['method'], 'receipt': last['sha256'], 'issued': copy.deepcopy(last)}
    books = s.active_work.get('ask', {})
    prefix = s.scope + '|'
    for key, entry in list(books.items()):
        if not key.startswith(prefix):
            continue                # another scope's books are not this run's to touch
        seen = s.fact(key[len(prefix):])
        if seen.get('final'):
            log('ASK_CLOSED', ask=key, receipt=entry['receipt'], truth=seen['truth'], source=seen.get('source'))
            del books[key]


@register('ask', check=_check, plan=_plan, settle=_settle)
def ask(s, m, mid, deps):
    return {'ask': {'predicate': m['effect'], 'question': m.get('question') or f"is {m['effect']} true?", 'to': m['ask_to'],
                    'asked_in': digest({'packs': s.loaded, 'runs': s.event_journal})},   # binds the receipt to this State's packs and history
            'parked': True}


def open_asks(state) -> dict:
    """The questions still out in this scope: scope|fact -> {method, receipt, issued}. `issued` is the receipt to answer with."""
    prefix = state.scope + '|'
    return {k: copy.deepcopy(v) for k, v in state.active_work.get('ask', {}).items() if k.startswith(prefix) and _open(state, k[len(prefix):])}


def answer(kernel, receipt, truth, source, execute: bool = False) -> dict:
    """The stamp. Refused (ValueError) unless the receipt equals the one on the books for a question still open in this
    scope and the answer comes from the party that was asked."""
    try:
        presented = plain(receipt)   # plain data only: what the receipt says, not what a crafted object answers
    except ValueError:
        presented = {}
    asked = presented.get('ask')
    if type(truth) is not str or truth not in ('TRUE', 'FALSE') or type(source) is not str or not isinstance(asked, dict) or type(asked.get('predicate')) is not str:
        raise ValueError('An answer is TRUE or FALSE, from a named party, to an ask receipt')
    entry = _open(kernel.s, asked['predicate'])
    if entry is None or canonical(presented) != canonical(entry['issued']):   # the same JSON, not only equal in Python (1 is not true)
        raise ValueError('No open ask matches this receipt')
    issued = entry['issued']
    if source != issued['ask']['to']:
        raise ValueError('The answer does not come from the party that was asked')
    seen = kernel.s.fact(issued['ask']['predicate'])   # a late yes on a fact other evidence already made true keeps that row's version: nothing made on it is undone
    version = seen.get('version') if truth == 'TRUE' and seen['truth'] == 'TRUE' else 'ask-' + issued['sha256'][:12]
    return kernel.on_event({'predicate': issued['ask']['predicate'], 'truth': truth, 'verified': True, 'final': True, 'source': 'STAMP:' + issued['ask']['to'],
                            'version': version, 'answers': issued['sha256'], 'scope': kernel.s.scope}, execute=execute)
