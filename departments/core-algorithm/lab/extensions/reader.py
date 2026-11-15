"""The reader: what repeated across runs, read from a kept journal as proposals (0.19.0-reader; ruling R27 of the
program, tried under ruling R35).

A journal (extensions/journal.py) keeps what a State was handed, asked, decided and ran, and the record adapter
(extensions/journal_record.py) reads ledger rows from its text. This module reads those ledger rows and says what
REPEATED, as a list of proposals that each name the journal entries they rest on. It is a function of the kept text
and its head. It keeps nothing between two calls. It imports the record adapter and nothing else of the lab: no
kernel, no State, not the journal's writer. So it cannot change a State: it never holds one. Like the adapter it
does not replay: what it reads is as true as the journal it was given.

  kept      a list of (text, head), oldest first: one journal or a chain, as the record adapter takes it. For what
            repeated as of an earlier head, hand in that head.
  least     how many times make a repeat: a whole number, 2 or more. The number is the caller's. The reader holds no
            threshold of its own.
  a run     one run of one goal in which a step ran or stopped: a ledger row worded `ran` that holds a receipt or a
            stopped step. A run in which nothing ran and nothing stopped is passed over (a look taken dry, a blocked
            run, a run that waits on a question already out, a goal already done): it neither counts nor breaks a row.
            Runs are counted one by one, by run of an entry: a pack that names a goal twice gives two runs of it in
            one entry, and both count.
  in a row  the newest runs of one goal in one scope, counted back from the head while they are alike. When the
            newest run is of another kind, the row has ended and nothing is proposed for it.

  REPEATED_STOP    the newest `least` or more runs of a goal each stopped at the same step for the same reason (the
                   step's id and the kernel's words for the stop, both compared whole).
  REPEATED_CHAIN   the newest `least` or more runs of a goal each completed by running the same two or more steps in
                   the same order. A run counts by what ran, read from the ledger, not by what was planned: a step
                   skipped as already true is not in the chain. `paid` is what each of these runs cost (a method's
                   cost does not change inside a State, so the same steps cost the same). `as_one` words the chain
                   as one step: the fact its last step makes, and the facts its steps require that no step of it
                   makes. It is there only when the chain is one line: every step but the last makes a fact that
                   another step of the chain requires.
  REPEATED_ANSWER  one question (the same words, put to the same party) was answered `least` times or more, and the
                   same way every time. Every answer in the record counts, not only the newest ones: one other
                   answer, before the repeats or after them, ends the question for good.

Stops and chains are listed first, goal by goal, then answers. A proposal is plain data: {kind, ..., support, at,
status}. `at` cites every run or answer it rests on by journal, entry number and entry hash (a run also by its run
id). `status` is always PROPOSED_ONLY. A proposal changes nothing by being made. What may follow it is done with
parts the lab has: row() words one verified row that says the repeat was read (its version is the proposal's
digest), for the journal's event door; a step that requires that row gives the yes or asks for it. A yes that is a
step rests on the row, and so on the proposal it was given for; a yes that was asked for is a decision of the party
asked and rests on nothing. The change itself is a pack, handed in at the journal's pack door by whoever drives the
run. The reader writes no pack, sets no number and names no fact: fits() only holds a way that a person wrote to the
chain it is said to replace. It is a look and no gate: no door and no step asks it, and the row is a name and a
digest that no door holds to the record. What a kept journal's event door takes under the name SOURCE is any fact."""
from __future__ import annotations
import hashlib, json
from extensions import journal_record as R

SOURCE = 'adapter:reader'   # the name a row of the reader carries; a journal lets it in only when its header names this checker
KINDS = ('REPEATED_STOP', 'REPEATED_CHAIN', 'REPEATED_ANSWER')
NOT_READ = 'The journal does not hold what the reader reads from it'


def digest(v) -> str:
    """The sha256 of a value as canonical JSON (the kernel's own form: sorted keys, no spaces, characters as they are)."""
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _methods(kept: list) -> dict:
    """Every method the journal's packs brought, by its id (a State refuses an id twice)."""
    out = {}
    for j in R.record(kept):
        for e in j['entries']:
            for m in (e['body']['pack'].get('methods', []) if e['kind'] == 'pack' else []):
                out.setdefault(m['id'], m)
    return out


def _as_one(steps: list, methods: dict):
    """The chain worded as one step: {effect, requires}. None when it is not one line: a step before the last makes a
    fact that no step of the chain requires."""
    ms = [methods[s] for s in steps]
    made = [m['effect'] for m in ms]
    needed = {r for m in ms for r in m.get('requires', [])}
    if any(fact not in needed for fact in made[:-1]):
        return None
    return {'effect': made[-1], 'requires': sorted(needed - set(made))}


def _row(runs: list, alike) -> list:
    """The newest runs that are alike, oldest first: counted back from the last run until one differs."""
    out = []
    for r in reversed(runs):
        if not alike(r):
            break
        out.append(r)
    return out[::-1]


def proposals(kept: list, least: int) -> list:
    """What repeated in the record up to its head: stops and chains goal by goal, in the order the goals first ran,
    then answers, in the order the questions were first answered. The same text, head and number give the same list.
    A journal the record adapter refuses is refused in the adapter's words; one that is whole and in order and still
    does not hold what is read from it is refused in the reader's words where a pack entry or an answer was forged,
    in the adapter's where its ledger cannot read a look entry, and in Python's own where a run's cost is no object:
    a ValueError each time. No journal at all (an empty list) is no refusal: nothing repeated."""
    if type(least) is not int or least < 2:
        raise ValueError('A repeat is two times or more: `least` is a whole number, 2 or more')
    rows = R.ledger(kept)
    try:
        goals, asked, answers = {}, {}, {}
        for r in rows:
            if r['what'] == 'ran' and (r['receipts'] or 'stopped' in r):
                goals.setdefault((r['scope'], r['goal']), []).append(r)
            elif r['what'] == 'asked':
                asked[r['receipt']] = (r['to'], r['question'])
            elif r['what'] == 'decided':
                answers.setdefault(asked[r['answers']], []).append(r)
        out, methods = [], None
        for (scope, goal), runs in goals.items():
            last = runs[-1]
            if 'stopped' in last:
                row = _row(runs, lambda r: r.get('stopped') == last['stopped'])
            else:
                row = _row(runs, lambda r: r['work_state'] == 'completed' and r['actions'] == last['actions'])
            if len(row) < least or ('stopped' not in last and len(last['actions']) < 2):
                continue
            if 'stopped' in last:
                p = {'kind': 'REPEATED_STOP', 'scope': scope, 'goal': goal, 'step': last['stopped']['method'], 'reason': last['stopped']['reason']}
            else:
                methods = _methods(kept) if methods is None else methods
                p = {'kind': 'REPEATED_CHAIN', 'scope': scope, 'goal': goal, 'steps': list(last['actions']), 'paid': dict(last['cost'])}
                one = _as_one(last['actions'], methods)
                if one is not None:
                    p['as_one'] = one
            p.update(support=len(row), at=[{'journal': r['journal'], 'entry': r['entry'], 'sha256': r['sha256'], 'run': r['run']} for r in row], status='PROPOSED_ONLY')
            out.append(p)
        for (to, question), given in answers.items():
            ways = {a['truth'] for a in given}
            if len(given) >= least and len(ways) == 1:
                out.append({'kind': 'REPEATED_ANSWER', 'to': to, 'question': question, 'truth': ways.pop(), 'support': len(given),
                            'at': [{'journal': a['journal'], 'entry': a['entry'], 'sha256': a['sha256']} for a in given], 'status': 'PROPOSED_ONLY'})
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError(NOT_READ) from None
    return out


def row(proposal: dict, predicate: str) -> dict:
    """One verified row that says the repeat was read from the record, for the journal's event door. Its version is the
    proposal's digest, so the yes of a step that requires this row and makes the yes itself rests on that proposal and
    on no other; a yes that such a step asks another party for is a decision and rests on nothing. The name of the
    fact is the caller's. The row is no decision, and the proposal itself is not in it."""
    if (type(proposal) is not dict or proposal.get('kind') not in KINDS or proposal.get('status') != 'PROPOSED_ONLY'
            or type(proposal.get('at')) is not list or not proposal['at'] or type(predicate) is not str or not predicate):
        raise ValueError('A row is worded for one proposal of the reader and one named fact')
    return {'predicate': predicate, 'truth': 'TRUE', 'verified': True, 'source': SOURCE, 'version': digest(proposal)}


def fits(proposal: dict, method: dict) -> list:
    """Why a method that a person wrote is NOT the proposed chain as one cheaper step: a list of reasons, empty when it
    is. It must make the fact the chain's last step makes, require exactly the facts the chain requires from outside
    (as a set, in any order), cost no more than each run of the chain was paid on any line of the budget, and less on
    one. A line that the method's cost does not name costs nothing. A look, not a gate: whoever hands the way in
    reads this list or does not, and a way that names no input, once handed in, runs once and then stands as done."""
    if type(proposal) is not dict or proposal.get('kind') != 'REPEATED_CHAIN' or type(method) is not dict:
        raise ValueError('A way is held to a proposal of the kind REPEATED_CHAIN')
    one, paid, cost = proposal.get('as_one'), proposal['paid'], method.get('cost', {})
    if one is None:
        return ['the chain is not one line: no single step stands for it']
    why = []
    if method.get('effect') != one['effect']:
        why.append('it makes another fact')
    if set(method.get('requires', [])) != set(one['requires']):
        why.append('it requires other facts')
    more = {line: cost.get(line, 0) - paid.get(line, 0) for line in sorted(set(paid) | set(cost))}
    why += [f'it is dearer on {line}' for line in more if more[line] > 0]
    if not any(more[line] < 0 for line in more):
        why.append('it is cheaper on no line')
    return why
