"""The journal: memory across runs, OUTSIDE the kernel (the journal version; matrix gap 1, rows R07 and R11).

The kernel keeps its State in memory, so a new process starts from the packs alone: it forgets a question that is
out and an answer already given, and it runs and pays again. A State that must outlive its process keeps a journal:
every pack handed in, every event row, every look and every answer, in order, each entry hashed over the one before.
Replaying the journal through the kernel's own doors rebuilds the State, and every recorded result is computed again
on the way. A journal that does not reproduce is refused, with the entry named: the record is recomputed, not believed.
No line of kernel/core.py knows about any of this.

  entry    {seq, prev_sha256, kind, body, result, sha256} and, beside the hash, sometimes `stated`.
           body is what was handed in, with exactly the keys of its kind. result is what it did: the digest of the
           State after it, the budget and the provider slots in plain, and for a look, an event or an answer one
           brief per run (what ran, what it cost, what is pending, who was asked what, the receipts in full, the
           lines the kinds wrote when they settled, the trace root). An entry is enough to act on without the kernel.
  kinds    header (entry 0: the action kinds the State may use, the checkers whose rows the event door lets in, a
           name, and the head of the journal it continues, if any), pack, event, look, answer, close (the last
           entry of a journal that another one continues: it names that journal). A later version that adds a kind
           or a door rule widens this reader; it renames nothing, so an older journal stays what it was.
  doors    add() is the only way in. A body is read through the kernel's own plain() and holds exactly its kind's
           keys; `execute` is true or false by exact type, as at the kernel's door. A pack id passes once. An event
           row is verified, is not a decision and comes from a checker the header names. An answer presents the
           receipt it answers. Every entry runs on a new Kernel. Nothing is sealed when the thing is refused, and a
           State that was changed outside the journal is refused at the next add.
  digest   over named views of what a look reads (views), an empty view left out; never over a list of the State's
           field names, so the State may change shape under it. The guard is a mutation test, not a list of names.
  head     {length, sha256}: how many entries, and the hash of the last. It is kept OUTSIDE the journal. replay runs
           exactly the entries its head names and must end on the head's hash; entries past the head are uncommitted:
           reported and cut, never run. A head is quoted only for a journal that replays on a fresh State (a shadow
           run built from the header), so what the digest cannot see still never gets a head.
  keeper   where the text and the head are kept (Keep in memory, FileKeep in a folder). save() is compare-and-append:
           the new entries are taken only while the kept head is the one this run was replayed from, the entry first
           and then the head, in one exclusive step. A second writer is refused, replays and tries again. A keeper
           takes only whole entries of the journal's kinds, each with its keys, that chain onto the head it keeps and
           end on the head handed in with them, and nothing after a closing entry. It checks the chain and the shape,
           not the results: only save() gives a head that replays. What the loser did, it did in memory only.
  stated   the SHA-256 of the code an entry was written under (the kernel, each kind's file, this file), computed
           here from the loaded modules. It stands beside the entry, OUTSIDE its hash: a statement, not a gate. A
           head covers no file hash and no schema name. What refuses a journal is a result that does not reproduce.
  restart  restart(keep) reads the text and the head and replays. It seals nothing: a read is not a write, so the
           head after a restart is the head of a process that never stopped. The promise is: the same journal up to
           its head, the same answer. The packs alone do not give it (a receipt is bound to the State's history).
  chain    continuing a journal is a write to it. start(continues=run, keep=where that journal is kept) seals a
           closing entry that names the new journal (its kinds, its checkers, its name) and saves it by
           compare-and-append; only then does the new header exist, citing that head. So of two runs replayed from
           one head only one continues the journal and the save of the other is refused; a closed journal takes no
           more entries, from a run or at its keeper; and it names the one journal that continues it. The new journal
           starts on its own copy of that State: a continuation that is refused leaves the run handed in as it was.
           A chain of journals reads as one record and a pack id passes once across all of them.

Not sealed: a look that ends in a kernel fault, in `unsettled`, or in a failure of the process itself (a
RecursionError, a MemoryError). Its outcome depends on the process, not on the State, so it would never replay. The
fault goes to the caller (Unsealed), the run stops, and only a replay continues.

Two kinds of failure, never mixed: a ValueError refuses the journal (or the thing handed in), in the journal's words
and by entry number where there is one; a RecursionError or a MemoryError says that the process failed and the same
call may be made again in a healthy process. A line of text that nests deeper than any entry can (DEEPEST) is the
journal's fault, whatever reading it does to the stack; an entry that deep is never sealed.

A chain shows that a journal is whole and in order, not who wrote it: it holds no secret. What replay refuses is a
result that does not come out again: a body changed to another one that gives the same result replays, under another
head, so the head kept outside is what tells the two apart. Replay runs every handler again, which is safe only
while every effect is a local model. One writer is one writer per keeper: where a journal is kept is not in the
journal. extensions/journal_record.py reads ledger rows and counts from the text alone, without this module and
without the kernel. This module registers no action kind; it loads extensions/asks.py for the stamp, which registers
the ask."""
from __future__ import annotations
import copy, hashlib, json, os, re, sys
from pathlib import Path
from kernel.core import State, Kernel, ACTIONS, canonical, digest, plain
from extensions.asks import answer

KINDS = ('header', 'pack', 'event', 'look', 'answer', 'close')
KEYS = {'pack': {'pack'}, 'event': {'row', 'execute'}, 'look': {'execute'}, 'answer': {'receipt', 'truth', 'source', 'execute'}, 'close': {'next'}}
COVERED = ('seq', 'prev_sha256', 'kind', 'body', 'result')   # what an entry's hash covers; `stated` stands beside it
DEEPEST = 64   # no entry nests deeper: a body is at most 20 levels at its door, a result what the kernel's bound on a receipt allows; the journal's own entries nest 7
CLOSED = 'its journal is closed and goes on in the journal its last entry names'
PROCESS_FAULTS = ('Handler failed: RecursionError', 'Handler failed: MemoryError')
_PLAN_END = ('BLOCK', 'SELECT', 'ADMISSION', 'LOCAL_EFFECT', 'STEP_ALREADY_TRUE', 'STEP_STOPPED')   # the kernel's last line of a plan is one of these; what follows, up to TERMINAL, the kinds wrote when they settled
_CODE: dict = {}


class Unsealed(ValueError):
    """A look ended in a fault of the process, not in an outcome: nothing was sealed, and only a replay continues."""


# ------------------------------------------------------------------ what a State is, to a journal
def views(s: State) -> dict:
    """What a look reads, by name. Methods, books, kinds and candidates are read in order, so their order is part of
    the view; evidence, rules, providers and the budget are read by key. A view that is empty is left out, so a view
    a later version adds changes no digest made before it."""
    pairs = lambda d: [[k, v] for k, v in d.items()]
    named = {'scope': s.scope, 'goals': s.goals, 'evidence': s.evidence, 'rules': s.rules, 'proposed': s.proposed_rules,
             'methods': pairs(s.methods), 'constructors': s.constructor_specs, 'providers': s.providers, 'grants': sorted(s.grants),
             'budget': s.budget, 'preference': s.preference, 'candidates': pairs(s.candidates), 'loaded': s.loaded,
             'history': s.event_journal, 'books': [[k, pairs(v) if type(v) is dict else v] for k, v in s.active_work.items()],
             'kinds': list(s.actions)}
    return {k: v for k, v in named.items() if v not in ('', [], {})}


def state_digest(s: State) -> str:
    try:
        return digest(views(s))
    except (RecursionError, MemoryError):
        raise   # the process failed, not the State
    except Exception:
        raise ValueError('The State holds what a journal cannot record') from None


def _books(s: State) -> dict:
    return {'budget': dict(s.budget), 'providers': dict(s.providers)}


def _brief(r: dict) -> dict:
    """One run as the ledger needs it, so the ledger is read without the kernel. A part that is empty is left out."""
    b = {'goal': r['goal'], 'scope': r['scope'], 'status': r['status'], 'work_state': r['work_state'], 'actions': r['actions'], 'cost': r['cost'],
         'receipts': r['model_receipts'], 'trace_root_sha256': r['trace_root_sha256']}
    for k in ('stop_reasons', 'pending', 'waits', 'skipped', 'stopped'):
        if r.get(k):
            b[k] = r[k]
    t = r['trace']
    end = max(i for i, e in enumerate(t) if e['operation'] in _PLAN_END)
    settled = [{'operation': e['operation'], 'data': e['data']} for e in t[end + 1:-1]]
    if settled:
        b['settled'] = settled
    return b


def _fault(detail) -> str | None:
    """What makes a look a failure of the process and not an outcome of the State: it would not come out again on replay."""
    for r in (detail or {}).get('runs', []):
        if r.get('unsettled'):
            return 'unsettled: ' + ', '.join(str(k) for k in r['unsettled'])
        why = (r.get('stopped') or {}).get('reason', '')
        if why.startswith('Kernel fault: ') or why in PROCESS_FAULTS:
            return why
    return None


def _failed(detail):
    """RecursionError or MemoryError when a look ended in a failure of the process itself, else None. The kernel
    caught it and wrote it down, as the reason a step stopped or as the reason a kind did not settle."""
    for r in detail['runs']:
        reasons = [(r.get('stopped') or {}).get('reason', '')] + [e['data'].get('reason', '') for e in r['trace'] if e['operation'] == 'SETTLE_STOPPED']
        for name, failed in (('RecursionError', RecursionError), ('MemoryError', MemoryError)):
            if any(why == name or why.endswith(': ' + name) for why in reasons):
                return failed
    return None


def code_now(kinds) -> dict:
    """The SHA-256 of the code a journal of these kinds runs on, computed here from the loaded modules and taken from
    no caller: the kernel, each kind's file, this file. Stated beside an entry; never compared as a gate."""
    key = tuple(kinds)
    if key not in _CODE:
        out = {}
        for name in sorted({'kernel.core', __name__} | {ACTIONS[k]['run'].__module__ for k in kinds if k in ACTIONS}):
            path = getattr(sys.modules.get(name), '__file__', None)
            out[name] = hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else 'unknown'
        _CODE[key] = out
    return dict(_CODE[key])


# ------------------------------------------------------------------ how deep, without recursion
def _depth(line: str) -> int:
    """How deep a line of text nests: its brackets and braces outside quoted text, counted without recursion."""
    deepest = now = 0
    for c in re.sub(r'[^\[\]{}]', '', re.sub(r'"(?:[^"\\]|\\.)*"', '', line)):
        now += 1 if c in '[{' else -1
        deepest = max(deepest, now)
    return deepest


def _deeper(v) -> bool:
    """True for data that nests deeper than any entry can, found level by level, without recursion. Data that is
    handed in with one part in many places, so that a level outgrows any entry, is no entry either."""
    level = [v]
    for _ in range(DEEPEST):
        level = [x for c in level if type(c) in (dict, list) for x in (c.values() if type(c) is dict else c)]
        if len(level) > 1000000:
            return True
    return any(type(c) in (dict, list) for c in level)


# ------------------------------------------------------------------ the doors
def _head(head) -> dict:
    if type(head) is not dict or set(head) != {'length', 'sha256'} or type(head['length']) is not int or head['length'] < 1 or type(head['sha256']) is not str:
        raise ValueError('No head, no restart: a head is {length, sha256} and is kept outside the journal')
    return {'length': head['length'], 'sha256': head['sha256']}


def _names(body: dict, may: set, said: str) -> None:
    """What names a journal: its kinds and its checkers (lists of names, none twice) and, where it has one, its name."""
    strings = lambda v: type(v) is list and all(type(x) is str and x for x in v) and len(set(v)) == len(v)
    if (not {'kinds', 'checkers'} <= set(body) or set(body) - may or not strings(body['kinds']) or not body['kinds']
            or not strings(body['checkers']) or ('name' in body and (type(body['name']) is not str or not body['name']))):
        raise ValueError(said)


def _door(kind, body) -> dict:
    """One door for every body: read through the kernel's plain() (no code of the caller runs; a tuple, a number key
    or an object that only looks like a dict is refused as at the kernel's door), exactly the keys of its kind, exact
    types where the kernel's own door asks for them. Returns the journal's own copy, as the saved text gives it back."""
    if type(kind) is not str or kind not in KINDS:
        raise ValueError('Unknown journal entry kind: ' + str(kind)[:40])
    try:
        body = plain(body, 19)   # one level more than a pack gets at the kernel's door: the pack sits one level down
    except ValueError:
        raise ValueError('An entry body is plain data (text, numbers, true, false, null, lists, objects with text keys), at most 19 levels deep and 100000 items') from None
    if kind == 'header':
        _names(body, {'kinds', 'checkers', 'name', 'continues'}, 'A header holds kinds and checkers (lists of names) and may hold a name and the head it continues')
        if 'continues' in body:
            _head(body['continues'])
    else:
        if set(body) != KEYS[kind]:
            raise ValueError(f'The {kind} door takes exactly: ' + ', '.join(sorted(KEYS[kind])))
        if 'execute' in body and type(body['execute']) is not bool:
            raise ValueError('execute is true or false')   # the kernel's own words at its own door
        if kind == 'pack' and type(body['pack']) is not dict:
            raise ValueError('A pack entry holds a pack')
        if kind == 'event' and type(body['row']) is not dict:
            raise ValueError('An event entry holds one row')
        if kind == 'close':
            said = 'A closing entry names the journal that continues this one: its kinds and checkers (lists of names) and, if it has one, its name'
            if type(body['next']) is not dict:
                raise ValueError(said)
            _names(body['next'], {'kinds', 'checkers', 'name'}, said)
    return json.loads(canonical(body))


class Run:
    """One journalled State: the State, its journal, and the only doors that change either. Made by start() or replay()."""
    def __init__(self, header: dict, before: 'Run | None' = None):
        missing = [k for k in header['kinds'] if k not in ACTIONS]
        if missing:
            raise ValueError('The journal names action kinds this process has not loaded: ' + ', '.join(missing))
        registry = {k: dict(ACTIONS[k]) for k in header['kinds']}   # the registry as it was loaded, for this run alone
        cites = header.get('continues')
        if before is None:
            if cites is not None:
                raise ValueError('This journal continues another one: hand that journal in first, replayed to the head this header cites')
            self.state = State(actions=registry)
            self.earlier = []
        else:
            if type(before) is not Run or not before.closed:
                raise ValueError('A journal continues one that is closed: the journal handed in before it does not end on a closing entry')
            at = before.head()   # guarded: the State of the run handed in is the one its closing entry states
            if canonical(cites) != canonical(at):   # also a header that cites nothing
                raise ValueError('The header does not cite the head of the journal handed in before it')
            if canonical(before.base) != canonical(at):
                raise ValueError('The journal before is not saved up to the head this header cites: the entry first, then the head, then the journal that continues it')
            if canonical({k: v for k, v in header.items() if k != 'continues'}) != canonical(before.journal[-1]['body']['next']):
                raise ValueError('The journal handed in before this one names another journal as the one that continues it')
            self.state = copy.deepcopy(before.state, {id(before.state.actions): before.state.actions})   # its own State: whatever this journal does, and a continuation that is refused, leaves the run handed in as it was
            self.state.actions = registry
            self.earlier = before.earlier + [(copy.deepcopy(before.journal), at)]
        self.journal = []
        self.detail = {}       # entry number -> what the kernel returned for it: the detail under the entry
        self.stopped = False   # set to the reason when this run takes no more entries
        self.base = None       # the head this run was replayed from or last saved at: what save() compares
        self.cut = 0           # how many entries stood past the head at the restart: reported, cut, never run
        self.notice = []       # where the code stated in the journal is not the code that replays it: a statement, not a gate
        self._proved = None    # the head up to which this journal has replayed on a fresh State
        self._stated = None    # the code last stated in this journal

    @property
    def closed(self) -> bool:
        """Its last entry is a closing entry: the journal takes no more entries and goes on in the one that entry names."""
        return self.journal[-1]['kind'] == 'close'

    def _seal(self, kind: str, body: dict, result: dict) -> dict:
        entry = json.loads(canonical({'seq': len(self.journal), 'prev_sha256': self.journal[-1]['sha256'] if self.journal else 'GENESIS',
                                      'kind': kind, 'body': body, 'result': result}))   # plain data, the journal's own copy
        if _deeper(entry):
            raise ValueError(f'An entry nests at most {DEEPEST} levels deep: nothing is sealed')   # so no line this journal wrote is refused for its depth when it is read
        entry['sha256'] = digest(entry)
        code = code_now(self.journal[0]['body']['kinds'] if self.journal else body['kinds'])
        if code != self._stated:   # said once, and again only when the code is another
            entry['stated'] = {'code': code}
            self._stated = code
        self.journal.append(entry)
        return entry

    def _moved(self) -> bool:
        try:
            return state_digest(self.state) != self.journal[-1]['result']['state']
        except ValueError:
            return True

    def _guard(self) -> None:
        if self._moved():
            raise ValueError(f'The State was changed outside the journal after entry {len(self.journal) - 1}')

    def _do(self, kind: str, body: dict):
        """Put one body through its door. Returns what the journal records as the result, and the kernel's own answer."""
        s, kernel, detail = self.state, Kernel(self.state), None   # a new Kernel for every entry: nothing set on an earlier one reaches this one
        if kind == 'pack':
            if any(p['pack'] == body['pack'].get('id') for p in s.loaded):
                raise ValueError('A hand-over passes the door once: a pack with the id ' + json.dumps(body['pack'].get('id'), ensure_ascii=False) + ' was already let in')
            s.apply(body['pack'])
            result = {}
        elif kind == 'event':
            row = body['row']
            if row.get('verified') is not True or row.get('final') or row.get('source') not in self.journal[0]['body']['checkers']:   # the checkers are read from the sealed header, nowhere else
                raise ValueError('The event door lets in only verified rows that are not decisions, from a checker the header names')
            detail = kernel.on_event(row, execute=body['execute'])
            result = {'status': detail['status'], 'affected': detail['affected']}
        elif kind == 'look':
            detail = kernel.run_standing(execute=body['execute'])
            result = {'status': detail['status'], 'goals': detail['goals']}
        elif kind == 'answer':
            detail = answer(kernel, body['receipt'], body['truth'], body['source'], execute=body['execute'])   # the stamp: refused unless the receipt presented is the one on the books
            result = {'status': detail['status'], 'affected': detail['affected']}
        elif kind == 'close':
            if body['next']['kinds'] != self.journal[0]['body']['kinds']:
                raise ValueError('A journal that continues another names the same action kinds')
            result = {}   # the State is as it was: the journal named here starts from it
        else:
            raise ValueError('A journal has one header, entry 0')
        if detail is not None:
            result['briefs'] = [_brief(r) for r in detail['runs']]
        return dict(result, state=state_digest(s), **_books(s)), detail

    def add(self, kind: str, body: dict) -> dict:
        """Do one thing to the State through its door and seal it. Nothing is sealed when the thing is refused.
        Returns a copy of the entry: the head it rests on (prev_sha256), what it did (result), the head after (sha256)."""
        if self.stopped:
            raise ValueError(f'This run takes no more entries ({self.stopped})' + ('' if self.closed else ': replay the journal to continue'))
        self._guard()
        body = _door(kind, body)
        try:
            result, detail = self._do(kind, body)
            fault = _fault(detail)
            entry = None if fault else self._seal(kind, body, result)
        except BaseException:
            if self._moved():   # a refusal that changed nothing leaves the run usable
                self.stopped = 'an entry stopped part way'
            raise
        if fault:
            self.stopped = 'a look ended in a fault of the process'
            raise Unsealed(f'The look ended in a fault of the process, not in an outcome ({fault}): nothing is sealed, and only a replay of the journal continues')
        if detail is not None:
            self.detail[entry['seq']] = detail
        if kind == 'close':
            self.stopped = CLOSED
        return copy.deepcopy(entry)

    def _before(self) -> 'Run | None':
        b = None
        for entries, head in self.earlier:
            b = replay(entries, head, before=b)
        return b

    def head(self) -> dict:
        """The head: how many entries, and the hash of the last. Quoted only for a journal that replays on a shadow
        run built from the header: a fresh State, the registry as it was loaded, a new Kernel for every entry.
        A run that takes entries, and one that is closed, is held to its State first. A run that stopped part way
        is not at an entry: what is quoted for it is the head of the journal it sealed, never of its State.
        A failure of the process (RecursionError, MemoryError) goes to the caller and stops nothing."""
        if not self.stopped or self.closed:
            self._guard()
        at = {'length': len(self.journal), 'sha256': self.journal[-1]['sha256']}
        try:
            _chain(self.journal)                                   # whole and in order in memory too: an entry reached into after it was proved is seen here
            if canonical(at) != canonical(self._proved):
                replay(self.journal, at, before=self._before())   # replay works on its own copy
        except ValueError as why:
            self.stopped = 'its journal does not replay'
            raise ValueError(f'No head is quoted: {why}') from None
        self._proved = at
        return dict(at)


def start(kinds, checkers=(), name: str = '', continues: 'Run | None' = None, keep=None) -> Run:
    """A new journal. `kinds` are the action kinds its State may use, `checkers` the sources whose rows the event door
    lets in. `continues` is the run of the journal before it and `keep` where that journal is kept: continuing is a
    write to it. Its closing entry, which names the new journal, is sealed and saved by compare-and-append first; a
    save that is refused (another writer was there) leaves nothing of the new journal. The header then cites that
    head and the new journal starts from a copy of that State, so no journal that has one before it starts from the
    packs alone. A journal that is closed already is continued only by the journal it names."""
    listed = lambda v: list(v) if type(v) is tuple else v
    body = {'kinds': listed(kinds), 'checkers': listed(checkers)}
    if name:
        body['name'] = name
    body = _door('header', body)
    if continues is None:
        if keep is not None:
            raise ValueError('A keeper is named with the journal that is continued; a new journal is kept by save()')
    else:
        if type(continues) is not Run:
            raise ValueError('A journal continues a run that was replayed or started here')
        if keep is None:
            raise ValueError('Continuing a journal is a write to it: name where it is kept')
        if not continues.closed:
            continues.add('close', {'next': body})
        elif canonical(continues.journal[-1]['body']['next']) != canonical(body):
            raise ValueError('The journal is closed and names another journal as the one that continues it')
        body = dict(body, continues=save(continues, keep))   # compare-and-append on the head kept for the journal that is continued
    run = Run(body, continues)
    run._seal('header', body, dict(_books(run.state), state=state_digest(run.state)))
    return run


def _chain(entries: list, at: int = 0, prev: str = 'GENESIS') -> None:
    """Whole and in order: every entry has its closed list of keys, is numbered on from `at` and is hashed over the
    one before; the header is entry 0 and nothing else is; nothing follows a closing entry."""
    closed = False
    for i, e in enumerate(entries, at):
        try:
            said = e.get('stated', {'code': {}})
            ok = (not closed and set(e) - {'stated'} == set(COVERED) | {'sha256'} and type(e['seq']) is int and e['seq'] == i and e['prev_sha256'] == prev
                  and e['kind'] in KINDS and (e['kind'] == 'header') == (i == 0) and type(e['body']) is dict and type(e['result']) is dict
                  and e['sha256'] == digest({k: e[k] for k in COVERED})
                  and set(said) == {'code'} and all(type(v) is str for v in said['code'].values()))
        except (RecursionError, MemoryError):
            raise   # the process failed, not the journal
        except Exception:   # what is no entry at all, or states its code in another shape, fails somewhere in the reading above
            ok = False
        if not ok:
            raise ValueError(f'The journal is broken at entry {i}')
        prev, closed = e['sha256'], e['kind'] == 'close'


def replay(journal: list, head: dict, before: 'Run | None' = None) -> Run:
    """Rebuild the State by putting every entry the head names through its door again, on a new State, and compare
    every result with the recorded one as canonical JSON. Runs exactly head.length entries and must end on the head's
    hash; what stands past the head is not run. `before` is the replayed run of the journal this one continues; it is
    read and never changed. Refused (ValueError) with the entry named: a journal that ends before its head or on
    another hash, a broken chain, a body its door refuses, a result that does not reproduce, a look that ends in a
    fault. A failure of the process itself comes out as RecursionError or MemoryError: it refuses nothing."""
    head = _head(head)
    if type(journal) is not list:
        raise ValueError('A journal is a list of entries')
    if len(journal) < head['length']:
        raise ValueError(f"The journal ends before its head: {len(journal)} entries, the head names {head['length']}")
    kept = []
    for n, e in enumerate(journal[:head['length']]):   # the replay's own copy; what stands past the head is not read
        if _deeper(e):   # deeper than any entry: the journal's fault at every depth of the stack, so it is not read at all
            raise ValueError(f'The journal is broken at entry {n}')
        try:
            kept.append(json.loads(canonical(e)))
        except (TypeError, ValueError):
            raise ValueError('The journal is not plain data') from None
    _chain(kept)
    if kept[-1]['sha256'] != head['sha256']:
        raise ValueError('The journal does not end on the hash its head names')
    try:
        header = _door('header', kept[0]['body'])
    except ValueError as why:
        raise ValueError(f'The journal does not replay at entry 0: {why}') from None
    run = Run(header, before)
    differs = lambda a, b: ', '.join(k for k in sorted(set(a) | set(b)) if k not in a or k not in b or canonical(a[k]) != canonical(b[k]))
    first = dict(_books(run.state), state=state_digest(run.state))
    if canonical(first) != canonical(kept[0]['result']):
        raise ValueError(f"The journal does not replay at entry 0: the result differs ({differs(first, kept[0]['result'])})")
    run.journal.append(kept[0])
    for e in kept[1:]:
        try:
            result, detail = run._do(e['kind'], _door(e['kind'], e['body']))
        except (RecursionError, MemoryError):
            raise   # the process failed, not the journal
        except Exception as why:
            raise ValueError(f"The journal does not replay at entry {e['seq']}: {why if type(why) is ValueError else type(why).__name__}") from None
        fault = _fault(detail)
        if fault:
            failed = _failed(detail)
            if failed:   # the kernel caught it and wrote it down: still the process, not the journal
                raise failed(f"The process failed while entry {e['seq']} was replayed ({fault}): the journal is not refused")
            raise ValueError(f"The journal does not replay at entry {e['seq']}: the look ends in a fault ({fault})")
        if canonical(result) != canonical(e['result']):
            raise ValueError(f"The journal does not replay at entry {e['seq']}: the result differs ({differs(result, e['result'])})")
        run.journal.append(e)
        if detail is not None:
            run.detail[e['seq']] = detail
    now = code_now(header['kinds'])
    for e in kept:
        if 'stated' in e:
            run._stated = e['stated']['code']
            other = sorted(k for k in set(now) | set(run._stated) if now.get(k) != run._stated.get(k))
            if other:
                run.notice.append({'entry': e['seq'], 'differs': other})
    run.base, run._proved, run.cut = dict(head), dict(head), len(journal) - head['length']
    if run.closed:
        run.stopped = CLOSED
    return run


# ------------------------------------------------------------------ the text, and where it is kept
def dump(entries: list) -> str:
    """The journal as text: one entry a line, each line the canonical JSON of its entry, a line feed after each."""
    return ''.join(canonical(e) + '\n' for e in entries)


def _line(line: str, n: int) -> dict:
    """One line of a kept text as its entry. A line that nests deeper than any entry can is a broken entry and is
    not taken apart at all, and so is a line that is not the text this journal writes. A reader that fails on a line
    no deeper than an entry failed for want of stack: that is the process, and the RecursionError goes to the caller."""
    try:
        if _depth(line) > DEEPEST:
            raise ValueError
        e = json.loads(line)
        if canonical(e) != line:   # only the text this journal writes: load then save gives back every character
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f'The journal is broken at entry {n}') from None
    return e


def parse(text: str) -> list:
    """The entries of a whole text. Split on the line feed only: a line mark inside a question (U+2028, U+2029,
    U+0085) is part of its line, where str.splitlines would cut the entry in two."""
    lines = text.split('\n')
    if lines[-1] != '':
        raise ValueError(f'The journal is broken at entry {len(lines) - 1}')   # the text ends inside an entry
    return [_line(line, n) for n, line in enumerate(lines[:-1])]


def _committed(text: str, head) -> str:
    """The text up to the head, to append to: what stands past the head is cut here and was never run. Up to its head
    the kept text must still be whole and in order, or nothing is appended to it; and nothing is appended to a journal
    that is closed. A text with no head at all is left alone: its head may be kept somewhere else, so nothing is
    appended to it and nothing replaces it."""
    if head is None:
        if text:
            raise ValueError('A journal stands here without a head: nothing is appended to it and nothing replaces it')
        return ''
    lines = text.split('\n')[:-1]
    if len(lines) < head['length']:
        raise ValueError(f"The journal ends before its head: {len(lines)} entries, the head names {head['length']}")
    kept = [_line(line, n) for n, line in enumerate(lines[:head['length']])]
    _chain(kept)   # appended to only while the kept text is still whole and in order up to its head ...
    if kept[-1]['sha256'] != head['sha256']:   # ... and still ends where the head says
        raise ValueError('The journal does not end on the hash its head names')
    if kept[-1]['kind'] == 'close':   # continuing a journal was a write to it: after that write it takes no other
        raise ValueError('The journal kept here is closed: nothing is appended to it, and it goes on in the journal its last entry names')
    return ''.join(line + '\n' for line in lines[:head['length']])


def _moved_on(now) -> str:
    try:
        said = f"its head names {_head(now)['length']} entries now"
    except ValueError:
        said = 'it has no head now'
    return 'The journal moved on since this run was replayed (' + said + '): replay it and try again'


def _handed(base, lines: str, head) -> dict:
    """What a keeper is handed chains onto the head it keeps and is what the new head names: whole entries of the
    journal's kinds, each with exactly its keys, numbered on from the base, each hashed over the one before, as many
    as the head counts, the last one carrying the head's hash, and nothing after a closing entry. So a kept head never
    names text the keeper did not take with it, or an entry no reader would read, whoever calls the keeper. What an
    entry did (its result) the keeper does not check: only save() hands over a journal that has replayed."""
    head = _head(head)
    try:
        at, prev = (base['length'], base['sha256']) if base else (0, 'GENESIS')
        new = parse(lines)
        ok = len(new) == head['length'] - at > 0 and new[-1]['sha256'] == head['sha256']
        if ok:
            _chain(new, at, prev)
            for e in new:
                _door(e['kind'], e['body'])
    except (ValueError, TypeError, KeyError):
        ok = False
    if not ok:
        raise ValueError('A keeper takes whole entries that chain onto the head it keeps and end on the head handed in with them')
    return head


class Keep:
    """Where a journal's text and its head are kept: two things, the head outside the text. In memory here."""
    def __init__(self, text: str = '', head: dict | None = None):
        self.text, self.head = text, (dict(head) if head else None)

    def read(self):
        return self.text, (dict(self.head) if self.head else None)

    def append(self, base, lines: str, head: dict) -> None:
        """Compare-and-append, one exclusive step: taken only while the kept head is `base`. The entry first, then the head."""
        if canonical(self.head) != canonical(base):
            raise ValueError(_moved_on(self.head))
        head = _handed(base, lines, head)
        self.text = _committed(self.text, base) + lines
        self.head = head


class FileKeep:
    """The same keeper in a folder: journal.jsonl (the text), journal.head (the head, outside the text) and, while one
    writer appends, journal.lock. The lock is made by exclusive create, so of two writers one is refused."""
    def __init__(self, folder):
        self.folder = Path(folder)
        self.text_file, self.head_file, self.lock = self.folder / 'journal.jsonl', self.folder / 'journal.head', self.folder / 'journal.lock'

    def _read(self):
        """The text, the head, and how many bytes the text file holds. Only what stands under the head must be text:
        the bytes of the lines the head names are read strictly as UTF-8. What stands past them is uncommitted (a
        writer may have died inside a character): it is read for the report only, whatever its bytes are."""
        head = None
        if self.head_file.exists():   # the head first: a writer that appends meanwhile only adds what stands past it
            try:
                head = _head(json.loads(self.head_file.read_bytes().decode('utf-8')))
            except ValueError:
                raise ValueError('No head, no restart: what is kept as the head here is not a head') from None
        data = self.text_file.read_bytes() if self.text_file.exists() else b''
        under = 0
        if head is not None:
            for _ in range(head['length']):   # a line feed is one byte in UTF-8 and stands inside no other character
                under = data.find(b'\n', under) + 1
                if not under:
                    under = len(data)   # fewer lines than the head names: all of it is read strictly, and load() says how many there are
                    break
        try:
            text = data[:under].decode('utf-8')
        except ValueError:
            raise ValueError('The journal is broken: its text is not UTF-8') from None
        return text + data[under:].decode('utf-8', 'replace'), head, len(data)

    def read(self):
        return self._read()[:2]

    def append(self, base, lines: str, head: dict) -> None:
        try:
            lock = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ValueError('Another writer holds this journal: replay it and try again') from None
        try:
            text, now, size = self._read()
            if canonical(now) != canonical(base):
                raise ValueError(_moved_on(now))
            head = _handed(base, lines, head)
            kept = _committed(text, base).encode('utf-8')
            if size != len(kept):
                os.truncate(str(self.text_file), len(kept))   # entries past the head are cut here
            with open(self.text_file, 'ab') as f:   # bytes, so no character is translated on the way
                f.write(lines.encode('utf-8'))       # the entry first
                f.flush()
                os.fsync(f.fileno())
            new = self.folder / 'journal.head.new'
            with open(new, 'wb') as f:
                f.write(canonical(head).encode('utf-8'))
                f.flush()
                os.fsync(f.fileno())
            os.replace(new, self.head_file)          # then the head
        finally:
            os.close(lock)
            os.unlink(str(self.lock))


def save(run: Run, keep) -> dict:
    """Commit what this run added: quoted only after it replayed on a shadow run, taken by the keeper only while the
    kept head is the one this run was replayed from. Returns the head that is kept: with nothing new to hand over,
    the keeper's own head is still compared, so no head is returned for a keeper that does not hold it. A refused
    save changes nothing that is kept."""
    head = run.head()
    if canonical(head) != canonical(run.base):
        keep.append(run.base, dump(run.journal[run.base['length'] if run.base else 0:]), head)
        run.base = dict(head)
    else:
        now = keep.read()[1]
        if canonical(now) != canonical(head):
            raise ValueError(_moved_on(now))
    return dict(head)


def load(keep):
    """What a restart reads: the entries the head names, the head, and apart from them what stands past the head
    (uncommitted: reported and cut, never run). No head, no restart."""
    text, head = keep.read()
    if head is None:
        raise ValueError('No head, no restart: the head is kept outside the journal, and none is kept here')
    head = _head(head)
    lines = text.split('\n')
    whole = lines[:-1]
    if len(whole) < head['length']:
        raise ValueError(f"The journal ends before its head: {len(whole)} entries, the head names {head['length']}")
    return [_line(line, n) for n, line in enumerate(whole[:head['length']])], head, whole[head['length']:] + ([lines[-1]] if lines[-1] else [])


def restart(keep, before: Run | None = None) -> Run:
    """What a new process does: read the text and the head from where they are kept, and replay. Seals nothing.
    A journal that is closed comes back as a run that takes no entries."""
    entries, head, past = load(keep)
    run = replay(entries, head, before)
    run.cut = len(past)
    return run
