"""Time as evidence (0.13.0-time, matrix gap 6, row R58, ruling R23): a clock adapter OUTSIDE the kernel. The kernel has no word of time.

Time moves only at a tick. `tick(kernel, now)` asks `clock_packs` what the clock states, applies it and then looks at the
standing goals. What it states is built from the State, the moment and the caller's label alone (the adapter keeps no
state of its own): the clock's own rows, into every scope that holds rows:
  now          the moment, a whole number in the packs' own unit: a DECISION (final TRUE) whose `at` (and version) is n,
               so no ordinary row written by hand or by a method stands in its place
  until:<n>    a window: an ordinary TRUE row, version `window`, while the moment is not past n; a DECISION (final
               FALSE) once it is, so no ordinary row, no earlier clock pack and no method reopens it
plus `revoke_grants` for every grant past its last box (the clock only takes grants away: its packs never carry
`grants`) and `budget` for an allowance when a new period begins. It never states another source's row again.

The rows go into ONE pack named `<label>clock@<now>` while there are at most ROWS of them. With more, they are cut into
several packs of at most ROWS rows each (`clock@6`, `clock@6.1`, `clock@6.2`, ...), the decisions that close a window
first, so however many windows a row names the clock still states them all: no evidence row makes a pack too large for
the kernel's door. The revoke and budget lines go with the first pack.

The moment of a State is the latest clock pack on its record of packs (`State.loaded`, which only a pack writes): no
evidence row and no event moves it, back or forward, and none stops the clock. The moment of a run is the same reading
of the run's own provenance.

Truth and permission are timed differently, because they enter differently.
Truth is evidence, and it expires by RESTING, with the dependency read the kernel already has. A timed row names the
window it rests on, so it reads UNKNOWN whenever that window is closed or was never published, and its stored row is
never touched:
  timed(row, n)    any evidence row: TRUE until the moment passes n; what was made on it lapses with it
  due(goal, n)     the due row `in-time:<goal>`; a tick reports the goal late when that row no longer reads TRUE and
                   the goal does not hold as the look begins: a read beside the runs, never a status word
Permission and budget enter only through packs, so their time is given there too, as names in the grant set, which no
evidence row and no event can write:
  box(grant, n)                        the name `box:<n>:<grant>`: the grant stands while one of its boxes is open;
                                       past its last box the tick's pack revokes it; what was done under it stands
  allowance(dimension, amount, every)  the name `allowance:<dimension>:<amount>:<every>`: the budget dimension is set
                                       to `amount` by the State's first clock pack and by every tick that enters a
                                       new period of `every` moments (a level, never an increment)
A name that begins `box:` or `allowance:` and is not written plainly is no box and no allowance; `misnamed` finds such
names in a pack before it is applied (an authoring-time check: the kernel takes any name for a grant).
A window is published at the first tick after a stored row, a method's prerequisite or a rule names it; until then what
rests on it reads UNKNOWN. A moment is whatever the caller of `tick` says it is: a local model, like everything here.

The adapter is no action kind: it has no handler, and nothing here enters the kernel's table of kinds. Not here: an ask
that names a window (item 5 of the ruling), so a wait never expires; a goal that waits past its due row is reported late."""
from __future__ import annotations
import itertools
from kernel.core import Kernel, State, canonical

SOURCE = 'adapter:clock@1'
OPEN = 'window'        # the one constant version of an open window: a timed row pins it, so it stays true from tick to tick
DUE = 'in-time:'
MARK = 'clock@'        # a pack whose name ends `clock@<n>` (or `clock@<n>.<i>`) is the clock's; what stands before is the caller's label
ROWS = 64              # at most this many rows in one clock pack (a row is at most 17 values, the kernel's door takes 100000 in one pack)


def _whole(v) -> bool:
    return type(v) is int and 0 <= v < 10 ** 18


def _digits(text) -> bool:   # a whole number written plainly: no sign, no leading zero, ASCII digits only
    return type(text) is str and text.isascii() and text.isdigit() and len(text) <= 18 and str(int(text)) == text


def closes(name):
    """The last moment a window name stands for, or None when the name is not a window (`until:<n>`, n written plainly)."""
    return int(name[6:]) if type(name) is str and name.startswith('until:') and _digits(name[6:]) else None


def window(until: int) -> str:
    if not _whole(until):
        raise ValueError('A moment is a whole number that is not negative')
    return f'until:{until}'


def timed(row: dict, until: int) -> dict:
    """The row, resting on the window that stays open until the moment passes `until`. A decision cannot be timed: it rests on nothing."""
    if type(row) is not dict or type(row.get('depends_on', [])) is not list or row.get('final'):
        raise ValueError('A timed row is an evidence row that is not a decision')
    return dict(row, depends_on=list(row.get('depends_on', [])) + [{'predicate': window(until), 'version': OPEN}])


def due(goal: str, until: int, source: str = 'fixture/reviewed', version='1') -> dict:
    """The due row of a goal: `in-time:<goal>`, TRUE until the moment passes `until`."""
    if type(goal) is not str or not goal:
        raise ValueError('A due row names a goal')
    return timed({'predicate': DUE + goal, 'truth': 'TRUE', 'verified': True, 'source': source, 'version': version}, until)


def box(grant: str, until: int) -> str:
    """The box name of a grant: `box:<until>:<grant>`. A pack gives it in its `grants`, beside the grant or later."""
    if type(grant) is not str or not grant or grant.startswith('box:') or not _whole(until):
        raise ValueError('A box names a grant that is not itself a box, and the last moment it stands')
    return f'box:{until}:{grant}'


def boxed(name):
    """(the last moment, the grant) of a box name, or None when the name is not a box. A box cannot be boxed."""
    n, sep, grant = name[4:].partition(':') if type(name) is str and name.startswith('box:') else ('', '', '')
    return (int(n), grant) if sep and grant and not grant.startswith('box:') and _digits(n) else None


def allowance(dimension: str, amount: int, every: int) -> str:
    """The allowance name of a budget dimension: `allowance:<dimension>:<amount>:<every>`, `amount` for each period of `every` moments."""
    if type(dimension) is not str or not dimension or not (_whole(amount) and _whole(every) and every >= 1):
        raise ValueError('An allowance is a whole amount of a dimension for each period of at least one moment')
    return f'allowance:{dimension}:{amount}:{every}'


def allowed(name):
    """(the dimension, the amount, the period) of an allowance name, or None when the name is not an allowance."""
    parts = name[10:].rsplit(':', 2) if type(name) is str and name.startswith('allowance:') else []
    return (parts[0], int(parts[1]), int(parts[2])) if len(parts) == 3 and parts[0] and _digits(parts[1]) and _digits(parts[2]) and int(parts[2]) >= 1 else None


def misnamed(pack) -> list:
    """Authoring-time check: the names in a pack's `grants` and `revoke_grants` that begin like a box or an allowance and
    are not one (`box:015:g`, `box: 15:g`, `allowance:pulls:2`), in name order. The kernel takes any name for a grant, so
    such a name would silently give a grant with no end or an allowance that never comes. An author runs this on a pack
    before it is applied; the lab's own pack file does."""
    names = [n for key in ('grants', 'revoke_grants') for n in (pack.get(key, []) if type(pack) is dict and type(pack.get(key, [])) is list else [])]
    return sorted({n for n in names if type(n) is str and ((n.lower().startswith('box:') and boxed(n) is None) or (n.lower().startswith('allowance:') and allowed(n) is None))})


def stated(name):
    """The moment a pack name stands for when the pack is one of the clock's: the name ends `clock@<n>`, or `clock@<n>.<i>`
    for a later pack at that moment, after whatever label its caller gave it. Else None."""
    n, dot, i = name.rpartition(MARK)[2].partition('.') if type(name) is str and MARK in name else ('', '', '')
    return int(n) if _digits(n) and (not dot or (_digits(i) and i != '0')) else None


def moment(state):
    """The State's moment: the latest moment among the clock packs on its record, or None when there is none. Read from
    the record of packs, never from an evidence row."""
    seen = [m for m in (stated(entry['pack']) for entry in state.loaded) if m is not None]
    return max(seen) if seen else None


def scopes(state) -> list:
    """The scopes a tick states its rows into: the scope the State is in, then every other scope that holds a stored row, by name."""
    return [state.scope] + sorted({key.split('|', 1)[0] for key in state.evidence} - {state.scope})


def windows(state, scope=None) -> list:
    """Every window name in use in a scope (the State's own when none is named): a stored row there, what a stored row
    there rests on, what a method requires, what a rule names. Methods and rules belong to the State, so to every scope."""
    prefix = (state.scope if scope is None else scope) + '|'
    names = set()
    for key, row in state.evidence.items():
        if key.startswith(prefix):
            names.add(key[len(prefix):])
            names.update(dep['predicate'] for dep in row.get('depends_on', []))
    for m in state.methods.values():
        names.update(m.get('requires', []))
    for rule in state.rules.values():
        names.update(c for branch in rule['branches'] for c in branch)
    return sorted((n for n in names if closes(n) is not None), key=closes)


def clock_packs(state, now, label: str = '') -> list:
    """What the clock states at moment `now` on this State: its packs in the order they are applied, built from the State,
    the moment and the label alone. Nothing is applied. One pack while there are at most ROWS rows; with more, the rows
    are cut into packs of at most ROWS, the decisions that close a window first. Refused (ValueError): a moment that is
    not a whole number or is earlier than the State's, and a label that is not text or holds the clock's own mark."""
    if not isinstance(state, State):
        raise ValueError('The clock states its pack on a State')
    if not _whole(now):
        raise ValueError('A moment is a whole number that is not negative')
    before = moment(state)
    if before is not None and now < before:
        raise ValueError(f'Time does not go back: the moment is {before}')
    if type(label) is not str or MARK in label:
        raise ValueError('A label is text without the mark of the clock')
    rows = []
    for scope in scopes(state):
        rows.append({'predicate': 'now', 'truth': 'TRUE', 'verified': True, 'final': True, 'source': SOURCE, 'version': now, 'at': now, 'scope': scope})
        for w in windows(state, scope):
            rows.append({'predicate': w, 'truth': 'TRUE', 'verified': True, 'source': SOURCE, 'version': OPEN, 'scope': scope} if now <= closes(w) else
                        {'predicate': w, 'truth': 'FALSE', 'verified': True, 'final': True, 'source': SOURCE, 'version': 'closed', 'scope': scope})
    if len(rows) > ROWS:                                                # more than one pack: what closes is stated first
        rows = [r for r in rows if r['truth'] == 'FALSE'] + [r for r in rows if r['truth'] != 'FALSE']
    taken = {entry['pack'] for entry in state.loaded}                   # names of their own: `clock@6`, then `clock@6.1`, `clock@6.2` for later packs at that moment
    free = (n for n in (f'{label}{MARK}{now}' + (f'.{i}' if i else '') for i in itertools.count()) if n not in taken)
    packs = [{'schema': 'sutra-extension/2', 'id': next(free), 'evidence': rows[i:i + ROWS]} for i in range(0, len(rows), ROWS)]
    last = {}                                                           # grant -> the last moment of its latest box
    for n, grant in filter(None, map(boxed, state.grants)):
        last[grant] = max(n, last.get(grant, -1))
    gone = sorted(g for g, n in last.items() if n < now and g in state.grants)
    if gone:
        packs[0]['revoke_grants'] = gone
    top = {}
    for dimension, amount, every in sorted(filter(None, map(allowed, state.grants - set(gone)))):   # an allowance this pack revokes gives nothing
        if dimension in state.budget and (before is None or now // every > before // every):
            top[dimension] = max(amount, top.get(dimension, 0))
    if top:
        packs[0]['budget'] = top
    return packs


def clock_pack(state, now, label: str = '') -> dict:
    """The first pack the clock states at moment `now` on this State: the only one while its rows fit one pack."""
    return clock_packs(state, now, label)[0]


def _lands(state, row) -> bool:
    """Would this row of the clock change what is stored? Not when the same row is stored already, and not when a decision
    stands there that an ordinary row cannot replace (the kernel turns such a row away and its journal says so)."""
    stored = state.evidence.get(state.key(row['predicate'], row['scope']))
    return canonical(stored) != canonical(row) and not (stored is not None and stored.get('final') and not row.get('final'))


def overdue(state, goal: str) -> bool:
    """Overdue now: the goal has a due row that no longer reads TRUE, and the goal does not hold on the evidence."""
    if not isinstance(state, State) or type(goal) is not str:
        raise ValueError('A goal is a name, read on a State')
    if state.key(DUE + goal) not in state.evidence or state.fact(DUE + goal)['truth'] == 'TRUE':
        return False
    plans, _ = Kernel(state).expand(goal, root=True)   # the kernel's own derivation, read only: never the status word of a run
    return not any(not p['actions'] and not p.get('waits') for p in plans)


def report(state) -> dict:
    """What a tick reports beside its runs: the moment, and the standing goals that are overdue as the look begins."""
    return {'as_of': moment(state), 'late': [g for g in state.goals if overdue(state, g)]}


def tick(kernel, now, execute: bool = False, label: str = '') -> dict:
    """The only way time moves. State the moment (the clock's packs, each whole), read which standing goals are overdue,
    then look at them, dry or executed. A second tick at the same moment with nothing new states nothing. The result is
    `run_standing`'s, plus `time` (the moment and the goals overdue as the look began), `clock_pack` (the first pack this
    tick applied, when it applied one) and `more_clock_packs` (the others, when the rows were cut). Every refusal (a
    moment that is not a whole number or goes back, a label, an `execute` that is not true or false, a first pack the
    kernel's door turns away) is a ValueError raised before anything is applied, so it leaves the State as it was."""
    if not isinstance(kernel, Kernel) or type(execute) is not bool:
        raise ValueError('A tick is made on a kernel, and execute is true or false')
    s = kernel.s
    packs = clock_packs(s, now, label)
    new = moment(s) != now or 'revoke_grants' in packs[0] or any(_lands(s, row) for pack in packs for row in pack['evidence'])   # a budget line comes only with a new moment
    if new:
        for pack in packs:      # otherwise the same moment and nothing new: one look, nothing stated
            s.apply(pack)       # only the first can be refused (its revoke and budget lines have no bound of their own): every later pack is rows alone, at most ROWS of them
    time = report(s)
    out = kernel.run_standing(execute=execute)
    out['time'] = time
    if new:
        out['clock_pack'] = packs[0]
        if len(packs) > 1:
            out['more_clock_packs'] = packs[1:]
    return out
