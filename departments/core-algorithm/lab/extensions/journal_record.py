"""The record read back without the kernel (the journal version; matrix rows R07 and R11).

Ledger rows and counts, read from a journal's text and its head alone. This module imports nothing of the lab: not
the kernel, and not the journal extension that wrote the text. It computes the chain again itself, so what it reads is
whole, in order, of the journal's closed kinds and keys, and ends on the head it was given. It does not replay: a
State digest is checked by replay only, so what this module reads is as true as the journal it was given.

  kept     a list of (text, head), oldest first: one journal, or a chain. In a chain every journal but the last ends
           on a closing entry that names the next one (its kinds, its checkers, its name), and the next header cites
           that head and starts from that State. Exactly the entries each head names are read; what stands past a
           head is not.
  ledger   one row per thing, in journal order. handed_in: a pack or an event row. asked: a question a step sent
           (to whom, what, the receipt). decided: an answer, with the receipt it answers and where that was asked.
           ran: one run of one goal (status, what ran, cost, receipts, trace root, what is pending or stopped).
           Every row cites its entry by number and hash, which is the head right after it: a citation, not an anchor.
           A closing entry is no row: it hands nothing in and runs nothing.
  counts   how often a goal was looked at and a step ran, stopped or was skipped as already true. Every occurrence is
           listed by its position (journal, entry number, entry hash, run). Counted by entry, never by trace root:
           identical hand-overs give identical trace roots. For the counts as of an earlier head, hand in that head.

A run id is <the first 12 characters of its journal's header hash>:<entry number>.<run number>.
Every refusal is a ValueError that names the entry where there is one. A RecursionError means the process ran out of
stack on a line no deeper than an entry can be: the journal is not refused, and the same call may be made again."""
from __future__ import annotations
import hashlib, json, re

COVERED = ('seq', 'prev_sha256', 'kind', 'body', 'result')   # what an entry's hash covers
KEYS = {'pack': {'pack'}, 'event': {'row', 'execute'}, 'look': {'execute'}, 'answer': {'receipt', 'truth', 'source', 'execute'}, 'close': {'next'}}   # the journal's closed kinds, each with its keys
DEEPEST = 64   # no entry of a journal nests deeper


def _canonical(v) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _sha(v) -> str:
    return hashlib.sha256(_canonical(v).encode()).hexdigest()


def _depth(line: str) -> int:
    """How deep a line of text nests: its brackets and braces outside quoted text, counted without recursion."""
    deepest = now = 0
    for c in re.sub(r'[^\[\]{}]', '', re.sub(r'"(?:[^"\\]|\\.)*"', '', line)):
        now += 1 if c in '[{' else -1
        deepest = max(deepest, now)
    return deepest


def _shaped(e: dict, n: int) -> bool:
    """An entry is of a kind the journal has, holds exactly that kind's keys, and a header is entry 0 and nothing else is."""
    body = e['body']
    if type(body) is not dict or type(e['result']) is not dict or (e['kind'] == 'header') != (n == 0):
        return False
    if e['kind'] == 'header':
        return {'kinds', 'checkers'} <= set(body) <= {'kinds', 'checkers', 'name', 'continues'}
    if e['kind'] == 'close':
        return set(body) == {'next'} and type(body['next']) is dict and {'kinds', 'checkers'} <= set(body['next']) <= {'kinds', 'checkers', 'name'}
    return set(body) == KEYS[e['kind']] and ('execute' not in body or type(body['execute']) is bool)   # a kind that is not the journal's has no keys here: KeyError, read as broken


def entries(text: str, head: dict) -> list:
    """The entries a head names: whole lines split on the line feed only, each the canonical text of its entry,
    numbered from 0, each hashed over the one before, the last one carrying the head's hash, nothing after a
    closing entry."""
    if type(head) is not dict or set(head) != {'length', 'sha256'} or type(head['length']) is not int or head['length'] < 1 or type(head['sha256']) is not str:
        raise ValueError('No head, no read: a head is {length, sha256} and is kept outside the journal')
    if type(text) is not str:
        raise ValueError('A journal is read from its text')
    lines = text.split('\n')[:-1]
    if len(lines) < head['length']:
        raise ValueError(f"The journal ends before its head: {len(lines)} entries, the head names {head['length']}")
    out, prev, closed = [], 'GENESIS', False
    for n, line in enumerate(lines[:head['length']]):
        try:
            e = json.loads(line) if _depth(line) <= DEEPEST else None   # a line deeper than any entry is not taken apart at all
            ok = (not closed and _canonical(e) == line and set(e) - {'stated'} == set(COVERED) | {'sha256'} and type(e['seq']) is int and e['seq'] == n
                  and e['prev_sha256'] == prev and _shaped(e, n) and e['sha256'] == _sha({k: e[k] for k in COVERED}))
        except (RecursionError, MemoryError):
            raise   # the process ran out of stack or of memory, on a line no deeper than an entry can be
        except Exception:
            ok = False
        if not ok:
            raise ValueError(f'The journal is broken at entry {n}')
        out.append(e)
        prev, closed = e['sha256'], e['kind'] == 'close'
    if prev != head['sha256']:
        raise ValueError('The journal does not end on the hash its head names')
    return out


def record(kept: list) -> list:
    """A chain of journals as one record: [{journal, entries}], oldest first. The journal before must end on a closing
    entry that names this one, and this header must cite that head and start from the State that journal ended on."""
    out = []
    for text, head in kept:
        es = entries(text, head)
        cites = es[0]['body'].get('continues')
        if out:
            before = out[-1]['entries']
            last = before[-1]
            if (last['kind'] != 'close' or _canonical(last['body']['next']) != _canonical({k: v for k, v in es[0]['body'].items() if k != 'continues'})
                    or _canonical(cites) != _canonical({'length': len(before), 'sha256': last['sha256']})
                    or es[0]['result'].get('state') != last['result'].get('state')):
                raise ValueError('A journal of this record does not continue the one before it')
        elif cites is not None:
            raise ValueError('This record starts in the middle: its first journal continues another')
        out.append({'journal': es[0]['sha256'][:12], 'entries': es})
    return out


def _read(kept: list, each) -> None:
    """Hand every entry of the record to `each`, in order. An entry whose result does not hold what a row needs is named."""
    for j in record(kept):
        for e in j['entries']:
            try:
                each(j['journal'], e)
            except (KeyError, TypeError, AttributeError, IndexError):
                raise ValueError(f"Entry {e['seq']} of journal {j['journal']} does not hold what the record reads from it") from None


def ledger(kept: list) -> list:
    """What was handed in, what was asked, what was decided and what ran, one row each, in journal order."""
    rows, asked = [], {}

    def each(journal, e):
        at = {'journal': journal, 'entry': e['seq'], 'sha256': e['sha256']}
        body, result, new = e['body'], e['result'], []
        if e['kind'] == 'pack':
            new.append(dict(at, what='handed_in', pack=body['pack'].get('id'), pack_sha256=_sha(body['pack'])))
        elif e['kind'] == 'event':
            new.append(dict(at, what='handed_in', row={k: body['row'].get(k) for k in ('predicate', 'truth', 'source', 'version')},
                            status=result['status'], affected=result['affected']))
        elif e['kind'] == 'answer':
            r = body['receipt']
            new.append(dict(at, what='decided', predicate=r['ask']['predicate'], truth=body['truth'], by=body['source'], answers=r['sha256'],
                            asked_at=asked.get(r['sha256']), status=result['status']))
        for i, b in enumerate(result.get('briefs', [])):
            run = f"{journal}:{e['seq']}.{i}"
            row = dict(at, what='ran', run=run, executed=body['execute'], receipts=[x['sha256'] for x in b['receipts']])
            row.update({k: b[k] for k in ('goal', 'scope', 'status', 'work_state', 'actions', 'cost', 'trace_root_sha256')})
            row.update({k: b[k] for k in ('stop_reasons', 'pending', 'waits', 'skipped', 'stopped', 'settled') if k in b})
            new.append(row)
            for x in b['receipts']:
                if type(x.get('ask')) is dict:
                    asked.setdefault(x['sha256'], dict(at, run=run))
                    new.append(dict(at, what='asked', run=run, receipt=x['sha256'], method=x['method'], to=x['ask']['to'],
                                    question=x['ask']['question'], predicate=x['ask']['predicate']))
        rows.extend(new)
    _read(kept, each)
    return rows


def counts(kept: list) -> dict:
    """How often each goal was looked at and each step ran, stopped or was skipped, with every occurrence cited."""
    goals, steps = {}, {}

    def each(journal, e):
        for i, b in enumerate(e['result'].get('briefs', [])):
            at = {'journal': journal, 'entry': e['seq'], 'sha256': e['sha256'], 'run': i}
            seen = ([(x['method'], 'ran') for x in b['receipts']] + ([(b['stopped']['method'], 'stopped')] if 'stopped' in b else [])
                    + [(m, 'skipped') for m in b.get('skipped', [])])
            g = goals.setdefault(b['scope'] + '|' + b['goal'], {'looked': 0, 'executed': 0, 'statuses': {}, 'trace_roots': [], 'at': []})
            g['looked'] += 1
            g['executed'] += 1 if e['body']['execute'] is True else 0
            g['statuses'][b['status']] = g['statuses'].get(b['status'], 0) + 1
            if b['trace_root_sha256'] not in g['trace_roots']:
                g['trace_roots'].append(b['trace_root_sha256'])
            g['at'].append(dict(at, status=b['status']))
            for method, what in seen:
                s = steps.setdefault(b['scope'] + '|' + method, {'ran': 0, 'stopped': 0, 'skipped': 0, 'at': []})
                s[what] += 1
                s['at'].append(dict(at, what=what))
    _read(kept, each)
    return {'goals': goals, 'steps': steps}
