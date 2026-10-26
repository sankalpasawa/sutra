"""journeys/contract.py -- the law a journey keeps, as twelve cases (PRD A3.6; the style of layers/contract.py).

A journey may add steps, edges, sub-journeys, tests, rulings and quotes. It may not drop, move or re-word a row the site
lists, may not carry a status (the status is computed), and every row either binds to code and to passing tests, or says
it is wanted and names its smallest behaviour. These cases are the static half of that law; each is a function that takes
the journeys ({id: journey}, a list of them, or None for the folder) and returns its faults as plain sentences that name
the journey and the row, [] when the journeys pass. None of them raises.

    JC-1   shape         every file is a journey (or a list of them) that fits the interface; each step is in a lane the journey lists
    JC-2   ids           journey ids, step numbers, edge ids, sub-journey ids and backlog ids are unique and begin as they should
    JC-3   places        inside, children, child, serves and sub resolve; a function journey is bound to a function and a user journey is not
    JC-4   binds         every act is a row of the sends table, every step an engine step, every event a ledger action, every
                         screen symbol and route exists; a journey that is not declared binds every step to something
    JC-5   code          every name in `code` is defined in the code
    JC-6   tests         every test a row, a build row or a scenario lists exists
    JC-7   wanted/proven a row has code, tests and (for an edge) a sentence on what the code does, or has no code and a backlog entry and no tests
    JC-8   the run       dynamic: the runner (qa/journey_status.py) computes the state of every row from the results (journeys/status.py)
    JC-9   fidelity      against the saved copy of the site's own data file: every row the site lists is there, under the same step, in its words
    JC-10  golden leads  the words an edge says to the owner are in the code that says them, and in a test file the journey lists
    JC-11  screen words  the words an owner may read (a golden lead, a reword) hold none of the screen's banned words
    JC-12  functions     a function journey is bound to one of the five, its rows that point at others resolve, and it is declared or proven
"""
import contextlib
import io
import re

import journeys
from journeys import site as SITE
from journeys import status as ST
from layers import R, S

#: the source the owner's words are said from (a golden lead is searched in these and in the layer modules)
GOLDEN_SOURCES = ('engine_runtime.py', 'website_dept.py', 'j2_runtime.py', 'founding.py')
#: an edge that lists tests says, in at least this many characters, what the code does: it is what the tests must assert
CODE_DOES_MIN = 20
_ROUTES = {}


# ---- reading the journeys the cases are given -----------------------------------------------------------------------------
def _list(js):
    """(the journeys as a list, the problems met loading them). None is the folder; a dict is {id: journey}, or one journey."""
    if js is None:
        try:
            return list(journeys.load().values()), []
        except ValueError as exc:
            return [], [str(exc)]
    if isinstance(js, dict):
        return ([js] if ('steps' in js or 'edges' in js) and 'id' in js else list(js.values())), []
    return [j for j in js if isinstance(j, dict)], []


def _map(js):
    return {j.get('id'): j for j in _list(js)[0]}


def _rows(j):
    """The rows of a journey, as [(kind, id, row)], for a journey that may not be whole: a case never raises on one."""
    return [('step', str(r.get('n')), r) for r in j.get('steps') or [] if isinstance(r, dict)] + \
        [('edge', str(r.get('id')), r) for r in j.get('edges') or [] if isinstance(r, dict)]


def _d(value):
    """A value that should be an object and may not be: itself, or {}."""
    return value if isinstance(value, dict) else {}


def _at(j, kind, rid):
    return '%s %s %s' % (j.get('id'), kind, rid)


def _all_rows(j):
    """The rows of a journey and of its earlier version, each with how a sentence names it."""
    out = [(_at(j, kind, rid), kind, row) for kind, rid, row in _rows(j)]
    was = j.get('was') if isinstance(j.get('was'), dict) else {}
    out += [('%s earlier %s %s' % (j.get('id'), kind, rid), kind, row) for kind, rid, row in _rows(was)]
    return out


def _live(j):
    """A journey whose rows are held to the law of wanted and proven: not declared."""
    return not j.get('declared')


# ---- JC-1: shape ---------------------------------------------------------------------------------------------------------
def _shape(j, fault):
    """A fault of the interface as a sentence that names the row: '$.steps[0].lane: is missing' of J9 is 'J9 step 1 ...'."""
    m = re.match(r'^\$(?:\.(steps|edges)\[(\d+)\])?\.?:? ?(.*)$', fault)
    kind, i, rest = (m.group(1), m.group(2), m.group(3)) if m else (None, None, fault)
    who = j.get('id')
    if kind:
        try:
            row = j[kind][int(i)]
            who = _at(j, 'step' if kind == 'steps' else 'edge', row.get('n') if kind == 'steps' else row.get('id'))
        except (KeyError, IndexError, TypeError, AttributeError):
            who = '%s %s number %s' % (j.get('id'), 'step' if kind == 'steps' else 'edge', int(i) + 1)
    return '%s does not fit the journey definition: %s' % (who, rest)


def case_jc1(js=None):
    items, faults = _list(js)
    for j in items:
        faults += [_shape(j, f) for f in S.validate('journey', j)]
        lanes = {l.get('id') for l in j.get('lanes') or [] if isinstance(l, dict)}
        for kind, rid, row in _rows(j):
            if row.get('lane') and row['lane'] not in lanes:
                faults.append('%s is in the lane %s, and the journey lists no such lane' % (_at(j, kind, rid), row['lane']))
    return faults


# ---- JC-2: ids -----------------------------------------------------------------------------------------------------------
def _twice(ids):
    seen, again = set(), []
    for i in ids:
        if i in seen and i not in again:
            again.append(i)
        seen.add(i)
    return again


def case_jc2(js=None):
    items, faults = _list(js)[0], []
    for i in _twice(j.get('id') for j in items):
        faults.append('%s is the id of more than one journey' % i)
    for j in items:
        jid = j.get('id')
        for label, rows_ in (('', _rows(j)), ('earlier ', _rows(j['was']) if isinstance(j.get('was'), dict) else [])):
            for kind, key in (('step', 'step number'), ('edge', 'edge id')):
                ids = [rid for k, rid, _ in rows_ if k == kind]
                faults += ['%s has the %s%s %s twice' % (jid, label, key, i) for i in _twice(ids)]
            for rid in (rid for k, rid, _ in rows_ if k == 'edge'):
                if not rid.startswith('%s.' % jid):
                    faults.append('%s %sedge %s does not begin with %s.' % (jid, label, rid, jid))
        subs = [s.get('id') for s in j.get('sub') or [] if isinstance(s, dict)]
        faults += ['%s has the sub-journey %s twice' % (jid, i) for i in _twice(subs)]
        faults += ['%s sub-journey %s does not begin with %s.' % (jid, i, jid) for i in subs if not str(i).startswith('%s.' % jid)]
        for key, label in (('build_rows', 'build row'), ('directions', 'direction')):
            ids = [r.get('id') for r in j.get(key) or [] if isinstance(r, dict)]
            faults += ['%s has the %s %s twice' % (jid, label, i) for i in _twice(ids)]
    where = {}
    for j in items:
        for b in j.get('backlog') or []:
            if isinstance(b, dict):
                where.setdefault(b.get('id'), []).append(j.get('id'))
    faults += ['the backlog entry %s is defined more than once (%s)' % (i, ', '.join(map(str, w))) for i, w in where.items() if len(w) > 1]
    return faults


# ---- JC-3: places --------------------------------------------------------------------------------------------------------
def case_jc3(js=None):
    items, faults = _list(js)[0], []
    by = {j.get('id'): j for j in items}
    steps = {i: {str(s.get('n')) for s in j.get('steps') or [] if isinstance(s, dict)} for i, j in by.items()}
    for j in items:
        jid = j.get('id')
        if j.get('inside') and j['inside'] not in by:
            faults.append('%s is inside %s, and there is no journey %s' % (jid, j['inside'], j['inside']))
        for c in j.get('children') or []:
            if c not in by:
                faults.append('%s lists %s as a child, and there is no journey %s' % (jid, c, c))
            elif by[c].get('inside') != jid:
                faults.append('%s lists %s as a child, and %s is not inside %s' % (jid, c, c, jid))
        chain, at = [jid], j.get('inside')
        while at and at in by and at not in chain[1:]:
            chain.append(at)
            if at == jid:
                faults.append('%s is inside itself (%s)' % (jid, ' > '.join(map(str, chain))))
            at = by[at].get('inside')
        for kind, rid, row in _rows(j):
            if row.get('child') and row['child'] not in by:
                faults.append('%s opens the journey %s, and there is no journey %s' % (_at(j, kind, rid), row['child'], row['child']))
        for ref in j.get('serves') or []:
            other, _, n = str(ref).partition(':')
            if other not in by:
                faults.append('%s serves step %s of %s, and there is no journey %s' % (jid, n, other, other))
            elif n not in steps[other]:
                faults.append('%s serves step %s of %s, and %s has no step %s' % (jid, n, other, other, n))
        for s in j.get('sub') or []:
            if isinstance(s, dict) and str(s.get('step')) not in steps[jid]:
                faults.append('%s sub-journey %s hangs under step %s, and %s has no such step' % (jid, s.get('id'), s.get('step'), jid))
        for kind, rid, row in _rows(j):
            if kind == 'edge' and str(row.get('at')) not in steps[jid] | {'any'}:
                faults.append('%s hangs under step %s, and %s has no such step' % (_at(j, kind, rid), row.get('at'), jid))
        was = j.get('was') if isinstance(j.get('was'), dict) else {}
        old = {str(s.get('n')) for s in was.get('steps') or [] if isinstance(s, dict)}
        for e in was.get('edges') or []:
            if isinstance(e, dict) and str(e.get('at')) not in old:
                faults.append('%s earlier edge %s hangs under step %s, and the earlier version has no such step' % (jid, e.get('id'), e.get('at')))
        if j.get('kind') == 'function' and not j.get('bound_to'):
            faults.append('%s is a function journey and is bound to no function' % jid)
        if j.get('kind') != 'function' and j.get('bound_to'):
            faults.append('%s is a user journey and is bound to %s: only a function journey is' % (jid, j['bound_to']))
    return faults


# ---- JC-4: binds ---------------------------------------------------------------------------------------------------------
def _sent(bind):
    """Whether a row of the sends table (S.SENDS) is this act: the sender, the act, the word (or any word), the receiver."""
    for row in S.SENDS.get(bind.get('src'), ()):
        words = row['words']
        if row['act'] == bind.get('act') and bind.get('dst') in row['to'] and \
                (words == S.ANY or (isinstance(words, (tuple, list)) and (S.ANY in words or bind.get('word') in words))):
            return True
    return False


def _step_ids():
    """The id of every gate, rule, step and handler step of the engine definitions as the runtime assembles them."""
    ids = set()
    for e in R.defs()['engines'].values():
        for group in ('gates', 'rules', 'steps'):
            ids |= {s['id'] for s in e.get(group) or [] if isinstance(s, dict) and s.get('id')}
        for h in e.get('on') or []:
            ids |= {s['id'] for s in h.get('steps') or [] if isinstance(s, dict) and s.get('id')}
    return ids


def _routes():
    """{(METHOD, path template)} of the app, or None when the app does not import (told once)."""
    if 'routes' not in _ROUTES:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                import app
            _ROUTES['routes'] = {(m, r.path) for r in app.app.routes for m in (getattr(r, 'methods', None) or ())}
        except Exception as exc:  # noqa: BLE001 -- a lane that cannot import the app skips the routes, and says so
            print('journeys: the app did not import (%s), so the routes of the api binds are not checked' % exc)
            _ROUTES['routes'] = None
    return _ROUTES['routes']


def case_jc4(js=None):
    items, faults = _list(js)[0], []
    ids = _step_ids() if any(b.get('kind') == 'step' for j in items for _, _, r in _all_rows(j) for b in r.get('binds') or []) else set()
    for j in items:
        for who, kind, row in _all_rows(j):
            for b in row.get('binds') or []:
                k = b.get('kind')
                need = {'act': ('src', 'act', 'word', 'dst'), 'step': ('id',), 'event': ('action',), 'api': ('method', 'path'), 'ui': ('symbol',)}.get(k, ())
                lack = [f for f in need if not b.get(f)]
                if lack:
                    faults.append('%s binds %s and leaves out its %s' % (who, k, ', '.join(lack)))
                elif k == 'act' and not _sent(b):
                    faults.append('%s binds the act (%s, %s, %s, %s), and no sender sends it' % (who, b['src'], b['act'], b['word'], b['dst']))
                elif k == 'step' and b['id'] not in ids:
                    faults.append('%s binds the step %s, and no engine has a step of that id' % (who, b['id']))
                elif k == 'event' and b['action'] not in S.LEDGER_ACTIONS:
                    faults.append('%s binds the event %s, and the ledger has no such action' % (who, b['action']))
                elif k == 'ui' and not ST.resolve_code(b['symbol'], scripts_only=True):
                    faults.append('%s binds the screen symbol %s, and no script defines it' % (who, b['symbol']))
                elif k == 'api':
                    routes = _routes()
                    if routes is not None and (b['method'], b['path']) not in routes:
                        faults.append('%s binds the route %s %s, and the app has no such route' % (who, b['method'], b['path']))
        if _live(j):
            for kind, rid, row in _rows(j):
                if kind == 'step' and not row.get('binds') and not row.get('same_as') and row.get('disposition') != 'drop':
                    faults.append('%s binds nothing: name the act, the step or the event it is, or the screen, the route or the person' % _at(j, kind, rid))
    return faults


# ---- JC-5, JC-6: the code and the tests ----------------------------------------------------------------------------------
def case_jc5(js=None):
    faults = []
    for j in _list(js)[0]:
        for kind, rid, row in _rows(j):
            faults += ['%s names %s in its code, and no code defines it' % (_at(j, kind, rid), n)
                       for n in row.get('code') or [] if not (isinstance(n, str) and ST.resolve_code(n))]
    return faults


def case_jc6(js=None):
    faults = []
    for j in _list(js)[0]:
        held = [(_at(j, kind, rid), row.get('tests')) for kind, rid, row in _rows(j)] + \
            [('%s build row %s' % (j.get('id'), b.get('id')), b.get('tests')) for b in j.get('build_rows') or [] if isinstance(b, dict)] + \
            [('%s scenario %s' % (j.get('id'), sc.get('id')), [sc.get('test')]) for sc in j.get('scenarios') or [] if isinstance(sc, dict)]
        for who, tests in held:
            faults += ['%s lists the test %s, and there is no such test' % (who, t) for t in tests or [] if not ST.resolve_test(str(t))]
    return faults


# ---- JC-7: wanted or proven ----------------------------------------------------------------------------------------------
def case_jc7(js=None):
    items, faults = _list(js)[0], []
    defined = {b.get('id') for j in items for b in j.get('backlog') or [] if isinstance(b, dict)}
    for j in items:
        if not _live(j):
            continue
        for kind, rid, row in _rows(j):
            if row.get('same_as') or row.get('disposition') == 'drop':
                continue
            who, tests, backlog = _at(j, kind, rid), row.get('tests') or [], row.get('backlog')
            if backlog and backlog not in defined:
                faults.append('%s names the backlog entry %s, and no journey defines it' % (who, backlog))
            if ST.has_code(row):
                if not tests:
                    faults.append('%s has code and lists no test: it is unproven' % who)
                elif kind == 'edge' and len((row.get('code_does') or '').strip()) < CODE_DOES_MIN:
                    faults.append('%s lists tests and does not say what the code does (at least %d characters): it is what the tests must assert'
                                  % (who, CODE_DOES_MIN))
            elif tests:
                faults.append('%s has no code and lists a test: a wanted row lists none' % who)
            elif not backlog:
                faults.append('%s has no code and no backlog entry: say what is built, or what is wanted and its smallest behaviour' % who)
    return faults


# ---- JC-9: fidelity to the site's own file -------------------------------------------------------------------------------
def _has_row(j, rid):
    """Whether the journey holds the row the site calls `rid` ('step:3', 'edge:J1.5', 'build:B2', 'direction:D-a', 'sub:J2.a',
    'quote:3', 'was:step:0a', 'was:edge:J2.1', 'today')."""
    kind, _, key = rid.partition(':')
    was = j.get('was') if isinstance(j.get('was'), dict) else {}
    if kind == 'was':
        k2, _, key = key.partition(':')
        return any(str(r.get('n' if k2 == 'step' else 'id')) == key for r in was.get(k2 + 's') or [] if isinstance(r, dict))
    if kind == 'today':
        return bool(j.get('today'))
    if kind == 'quote':
        return len(j.get('quotes') or []) >= int(key)
    table = {'step': ('steps', 'n'), 'edge': ('edges', 'id'), 'build': ('build_rows', 'id'), 'direction': ('directions', 'id'),
             'sub': ('sub', 'id')}[kind]
    return any(str(r.get(table[1])) == key for r in j.get(table[0]) or [] if isinstance(r, dict))


def _says(mine, theirs, who, what, faults):
    if not SITE.same(mine, theirs):
        faults.append('%s says its %s differently from the site (the site: %s)' % (who, what, (theirs or '')[:60] + ('...' if len(theirs or '') > 60 else '')))


def _site_step(row, site, who, faults):
    """A step carries the site's words: the text, the function, the status words and the Code column, verbatim. Its short
    label and the normalised status word are the author's (the site's `short` is the picture's four words)."""
    for key, what in (('text', 'text'), ('site_function', 'function'), ('site_says', 'status words'), ('site_code', 'Code column')):
        _says(row.get(key), site[key], who, what, faults)


def _site_edge(row, site, who, faults):
    """An edge hangs under the site's step and carries the site's words: its trigger and the site's text, verbatim."""
    _says(row.get('trigger'), site['trigger'], who, 'trigger', faults)
    _says(_d(row.get('site')).get('text'), site['site']['text'], who, 'status words', faults)
    if str(row.get('at')) != site['at']:
        faults.append('%s hangs under step %s, and the site hangs it under step %s' % (who, row.get('at'), site['at']))


def case_jc9(js=None, path=None):
    items, faults = _list(js)[0], []
    try:
        data = SITE.load(path)
    except (OSError, ValueError) as exc:
        return ['the saved copy of the site\'s journeys file cannot be read (%s)' % exc]
    listed, blocks = SITE.rows(data), SITE.blocks(data)
    live = {x['id'].upper(): x for x in data['journeys']}
    for j in items:
        jid = j.get('id')
        if jid not in listed:
            continue                                        # the site does not list this journey: nothing to hold it to
        have = set(j.get('site_ids') or [])
        for rid in listed[jid]['ids']:
            if not _has_row(j, rid):
                faults.append('%s lacks the row %s that the site lists: a row leaves only by the owner\'s mark drop' % (jid, rid))
            elif rid not in have:
                faults.append('%s does not list the row %s among the rows the site lists (site_ids)' % (jid, rid))
        steps = {str(r.get('n')): r for r in j.get('steps') or [] if isinstance(r, dict)}
        edges = {str(r.get('id')): r for r in j.get('edges') or [] if isinstance(r, dict)}
        for s in live[jid]['steps']:
            if str(s['n']) in steps:
                _site_step(steps[str(s['n'])], SITE.step_row(s), _at(j, 'step', s['n']), faults)
        for e in live[jid]['edges']:
            if e['id'] in edges:
                _site_edge(edges[e['id']], SITE.edge_row(e), _at(j, 'edge', e['id']), faults)
        mine, theirs = j, blocks.get(jid, {})
        if 'tag' in theirs:
            _says(mine.get('tag'), theirs['tag'], jid, 'tag', faults)
        if 'today' in theirs:
            _says(_d(mine.get('today')).get('text'), theirs['today']['text'], jid, '"how it runs today" block', faults)
            _says(_d(mine.get('today')).get('sources'), theirs['today']['sources'], jid, 'sources of the "how it runs today" block', faults)
        if 'was' in theirs:
            was = mine.get('was') if isinstance(mine.get('was'), dict) else {}
            _says(was.get('title'), theirs['was']['title'], jid, 'earlier version\'s title', faults)
            old_steps = {str(r.get('n')): r for r in was.get('steps') or [] if isinstance(r, dict)}
            old_edges = {str(r.get('id')): r for r in was.get('edges') or [] if isinstance(r, dict)}
            for s in theirs['was']['steps']:
                if s['n'] in old_steps:
                    _site_step(old_steps[s['n']], s, '%s earlier step %s' % (jid, s['n']), faults)
            for e in theirs['was']['edges']:
                if e['id'] in old_edges:
                    _site_edge(old_edges[e['id']], e, '%s earlier edge %s' % (jid, e['id']), faults)
    return faults


# ---- JC-10, JC-11: what the owner is told --------------------------------------------------------------------------------
_TEXT = {}


def _plain(text):
    """Words as they are compared: lower case, no backslash (a quote or a dot escaped in source), one space between words."""
    return re.sub(r'\s+', ' ', text.replace('\\', '').lower())


def _text_of(path):
    """A file's text as _plain reads it, kept while the file does not change; '' for a file that is not there."""
    try:
        stamp = path.stat().st_mtime_ns
        held = _TEXT.get(path)
        if held and held[0] == stamp:
            return held[1]
        _TEXT[path] = (stamp, _plain(path.read_text(encoding='utf-8')))
        return _TEXT[path][1]
    except OSError:
        return ''


def _sources():
    root = ST.ROOT
    return [root / n for n in GOLDEN_SOURCES] + sorted(root.glob('layers/**/*.py'))


def _test_files(j):
    """The test files that exist among the tests a journey lists anywhere: its rows, its build rows and its scenarios."""
    refs = [t for _, _, row in _rows(j) for t in row.get('tests') or []] + \
        [t for b in j.get('build_rows') or [] if isinstance(b, dict) for t in b.get('tests') or []] + \
        [sc.get('test') for sc in j.get('scenarios') or [] if isinstance(sc, dict)]
    names = {str(t)[3:].partition('#')[0] if str(t).startswith('js:') else str(t).partition('::')[0] for t in refs if t}
    return [ST.ROOT / n for n in sorted(names) if (ST.ROOT / n).is_file()]


def case_jc10(js=None):
    """A declared journey is a design, not built: what it will say is not yet in the code, so it is not searched."""
    faults, said = [], None
    for j in _list(js)[0]:
        if not _live(j):
            continue
        for kind, rid, row in _rows(j):
            out = row.get('outcome') if isinstance(row.get('outcome'), dict) else {}
            golden = (out.get('golden') or '').strip()
            if kind != 'edge' or out.get('kind') not in ('ask', 'tell') or not golden:
                continue
            said = said if said is not None else ' '.join(_text_of(p) for p in _sources())
            who = _at(j, kind, rid)
            golden = _plain(golden)
            if golden not in said:
                faults.append('%s says "%s" to the owner, and no code says it' % (who, out['golden'].strip()))
            files = _test_files(j)
            if files and not any(golden in _text_of(p) for p in files):
                faults.append('%s says "%s" to the owner, and no test file the journey lists asserts it' % (who, out['golden'].strip()))
    return faults


def case_jc11(js=None):
    banned, faults = re.compile(S.TEMPLATE_BANNED, re.I), []
    for j in _list(js)[0]:
        for kind, rid, row in _rows(j):
            out = row.get('outcome') if isinstance(row.get('outcome'), dict) else {}
            for what, text in (('golden lead', out.get('golden')), ('reword', row.get('reword'))):
                found = banned.search(text or '')
                if found:
                    faults.append('%s has the word "%s" in its %s: an owner reads it, and the screen does not say that' % (_at(j, kind, rid), found.group(0), what))
    return faults


# ---- JC-12: the functions' own journeys ----------------------------------------------------------------------------------
def case_jc12(js=None):
    items, faults = _list(js)[0], []
    by = {j.get('id'): j for j in items}
    for j in items:
        jid = j.get('id')
        if j.get('kind') == 'function':
            if j.get('bound_to') not in S.FUNCTION_LAYERS:
                faults.append('%s is bound to %s, which is not one of the five functions' % (jid, j.get('bound_to')))
            for ref in j.get('serves') or []:
                other = by.get(str(ref).partition(':')[0])
                if other is not None and other.get('kind') == 'function':
                    faults.append('%s serves a step of %s, which is a function journey: it serves a step of a user journey' % (jid, other.get('id')))
            if _live(j):
                for kind, rid, row in _rows(j):
                    state = None if row.get('same_as') else ST.row_state(row, {t: 'passed' for t in row.get('tests') or []})
                    if state not in (None, 'proven', 'dropped'):
                        faults.append('%s is not declared, and its %s %s would read %s even if every test passed: every row is proven, or the journey is declared'
                                      % (jid, kind, rid, state))
        for kind, rid, row in _rows(j):
            ref = row.get('same_as')
            if not ref:
                continue
            parts, target = str(ref).split('/'), None
            if len(parts) == 3 and parts[0] in by:
                target = {(k, r): held for k, r, held in _rows(by[parts[0]])}.get((parts[1], parts[2]))
            if target is None:
                faults.append('%s is the same row as %s, and there is no such row' % (_at(j, kind, rid), ref))
            elif target.get('same_as'):
                faults.append('%s is the same row as %s, which is itself the same as another: point at the row that holds the proof' % (_at(j, kind, rid), ref))
    return faults


# ---- all of them ---------------------------------------------------------------------------------------------------------
CASES = (('JC-1', case_jc1), ('JC-2', case_jc2), ('JC-3', case_jc3), ('JC-4', case_jc4), ('JC-5', case_jc5), ('JC-6', case_jc6),
         ('JC-7', case_jc7), ('JC-9', case_jc9), ('JC-10', case_jc10), ('JC-11', case_jc11), ('JC-12', case_jc12))


def cases(js=None):
    """Every static case over the journeys given (None: the folder, loaded once): {'JC-1': [faults], ...} for JC-1 to JC-7 and
    JC-9 to JC-12 (JC-8 needs a run: it is in journeys/status.py and the runner). A file that cannot be loaded is JC-1's fault. A
    case that breaks on what it was given says so as its fault instead of raising."""
    items, problems = _list(js)
    out = {}
    for cid, fn in CASES:
        try:
            out[cid] = fn(items)
        except Exception as exc:  # noqa: BLE001 -- a case never raises
            out[cid] = ['%s could not be checked (%s: %s)' % (cid, type(exc).__name__, exc)]
    out['JC-1'] = problems + out['JC-1']
    return out
