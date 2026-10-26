"""journeys/status.py -- what a row has earned (PRD A3.6, "The state of a row: computed, never typed").

Two inputs: the definition (has the row code? tests? a backlog entry?) and the results of the last run of its tests
(`passed`, `failed`, `missing`). The functions here are pure: the same row and the same results give the same state, and
nothing is read from the record, the clock or the disk except the code roots resolve_code scans.

    row_state(row, results, states=None)   one row's state
    row_states(j, results, states=None)    {'step:1': state, 'edge:J1.5': state} for the rows of one journey
    journey_state(j, row_states)           one journey's state from its rows
    site_claim(row, kind), drifts(...)     what the site says of a row, and whether the state disagrees
    resolve_code(name), resolve_test(ref)  whether a name a row lists is defined in the code, and a test exists
    tests_listed(js)                       every test the rows of the (non-declared) journeys list, sorted
    compute(j, results, states=None)       the journey.status document of one journey
    compute_all(js, results)               the documents of all journeys that are not declared
    case_jc8(js, docs, on_disk, ran=True)  contract case JC-8, the one that needs a run: the problems of what the tests gave

The one thing read from the disk is the code the names are looked up in; each file is read once for as long as it does not change.
"""
import ast
import re
from pathlib import Path

from journeys import natural, row_key, rows, sha_of
from layers import S

#: the plugin folder: the code roots and the test files are found beneath it
ROOT = Path(__file__).resolve().parent.parent

#: a bind of these kinds names code a test can reach; a `person` bind is the owner's own act and names none
CODE_BINDS = ('act', 'step', 'event', 'api', 'ui')
#: what the site's word for a row says the state is. The other words (today, open, directed, none) claim nothing
CLAIMS = {'built': ('proven',), 'partly': ('partly',), 'wanted': ('wanted',), 'to_build': ('wanted',), 'not_built': ('wanted',)}
#: a state that is not a verdict about the row: a drift is never reported against it
NO_VERDICT = ('dropped', 'unknown', 'declared')


def has_code(row):
    """The row names code a test can reach: names in `code`, or a bind that is not the owner's own act."""
    return bool(row.get('code')) or any(b.get('kind') in CODE_BINDS for b in row.get('binds') or [])


def row_state(row, results, states=None):
    """The state of one row of a journey that is not declared (the journey's `declared` is the journey's to say):
    dropped    the owner's mark `drop`: it counts for nothing
    (another)  the row has `same_as`: it takes that row's state, found in `states` by row_key
    wanted     no code, a backlog entry, no tests          fault   no code and no backlog entry, or a wanted row lists tests
    unproven   code and no tests                           failing a listed test failed, or the run did not find it
    partly     every listed test passed, and a backlog entry names what is not built
    proven     every listed test passed, and the row has no backlog entry
    unknown    (the read model only) a listed test has no result at all
    `results` is {test: 'passed' | 'failed' | 'missing'}; a test it does not hold has not run."""
    if row.get('disposition') == 'drop':
        return 'dropped'
    if row.get('same_as'):
        jid, kind, rid = row['same_as'].split('/')
        return (states or {}).get(row_key(jid, kind, rid)) or 'fault'
    tests = list(row.get('tests') or [])
    if not has_code(row):
        return 'wanted' if row.get('backlog') and not tests else 'fault'
    if not tests:
        return 'unproven'
    got = [(results or {}).get(t) for t in tests]
    if any(g in ('failed', 'missing') for g in got):
        return 'failing'
    if any(g != 'passed' for g in got):
        return 'unknown'
    return 'partly' if row.get('backlog') else 'proven'


def row_states(j, results, states=None):
    """{'step:1': state, 'edge:J1.5': state} for every row of one journey. A row with `same_as` is read after the others, so
    it finds the state of a row of this journey as well as of another one (`states` holds the others, by row_key)."""
    states = dict(states or {})
    out, later = {}, []
    for kind, rid, row in rows(j):
        if row.get('same_as') and row.get('disposition') != 'drop':
            later.append((kind, rid, row))
            continue
        out['%s:%s' % (kind, rid)] = states[row_key(j['id'], kind, rid)] = row_state(row, results, states)
    for kind, rid, row in later:
        out['%s:%s' % (kind, rid)] = row_state(row, results, states)
    return {'%s:%s' % (kind, rid): out['%s:%s' % (kind, rid)] for kind, rid, _ in rows(j)}


def journey_state(j, row_states):
    """declared; else failing if any row is; else fault if any row is a fault or unproven; else unknown if a row has no result
    yet (the read model of a journey whose file is stale); else partly if any row is partly or wanted; else proven. A dropped
    row counts for nothing. `row_states` is a dict of row states, or a list of them."""
    if j.get('declared'):
        return 'declared'
    held = set(row_states.values() if isinstance(row_states, dict) else row_states) - {'dropped'}
    for state, said in (('failing', {'failing'}), ('fault', {'fault', 'unproven'}), ('unknown', {'unknown'}),
                        ('partly', {'partly', 'wanted'})):
        if held & said:
            return state
    return 'proven'


def site_claim(row, kind):
    """The site's word for the row (its `site_status` for a step, its `site.status` for an edge), or None when the row has
    none (a row of a journey the site does not list). It is the site's claim, never the state."""
    claim = row.get('site_status') if kind == 'step' else (row.get('site') or {}).get('status')
    return claim or None


def drifts(claim, state):
    """The site says one thing and the state says another: built but not proven, wanted but built. A report, never a fault
    (it is the evidence for re-marking the site, A3.9). The site's words that claim nothing never drift."""
    return claim in CLAIMS and state not in CLAIMS[claim] and state not in NO_VERDICT


# ---- do the names a row lists exist ---------------------------------------------------------------------------------
_PARSED = {}       # path -> (mtime_ns, parsed): a file is parsed again only when it has changed
_JS_NAME = re.compile(r'(?:\bfunction\s*\*?\s+|\b(?:const|let|var)\s+)([A-Za-z_$][\w$]*)')


def _cached(path, parse):
    """What `parse` made of a file, kept while the file does not change; None for a file that is not there or does not parse."""
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return None
    held = _PARSED.get(path)
    if held and held[0] == stamp:
        return held[1]
    try:
        got = parse(path.read_text(encoding='utf-8'))
    except (OSError, SyntaxError, ValueError):
        got = None                                  # not Python (or not text): it defines nothing
    _PARSED[path] = (stamp, got)
    return got


def _py_names(text):
    """The names a Python file defines: every def and class (a method counts), and what its module level assigns."""
    tree = ast.parse(text)
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for n in tree.body:
        targets = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, (ast.AnnAssign, ast.AugAssign)) else []
        for t in targets:
            names |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
    return names


def code_roots():
    """The files a name a row lists may be defined in: the Python files of the plugin folder except the tests, those of
    layers/, and the scripts of static/js. A body that moves from engine_runtime into its layer on touch stays found."""
    py = [p for p in sorted(ROOT.glob('*.py')) if not p.name.startswith('test_')] + sorted(ROOT.glob('layers/**/*.py'))
    return py, sorted(ROOT.glob('static/js/*.js'))


def resolve_code(name, scripts_only=False):
    """Whether `name` (a bare name, or module.name) is defined in the code roots. A bare name is found if any root defines it;
    module.name if a file whose stem is `module` defines `name`. `scripts_only` looks in static/js alone (a name a screen binds)."""
    module, _, bare = name.rpartition('.')
    py, js = code_roots()
    if not scripts_only:
        for path in py:
            if (not module or path.stem == module) and bare in (_cached(path, _py_names) or ()):
                return True
    if module:
        return False
    return any(bare in (_cached(path, lambda t: set(_JS_NAME.findall(t))) or ()) for path in js)


def _py_tests(text):
    """{(class or None, name)}: the functions at the top of a test file, and the methods of the classes at its top."""
    out = set()
    for n in ast.parse(text).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add((None, n.name))
        elif isinstance(n, ast.ClassDef):
            out |= {(n.name, m.name) for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return out


def resolve_test(ref):
    """Whether a listed test exists. `file.py::test` and `file.py::Class::test` by the file's syntax tree (a function at its
    top, or a method of a class at its top); `js:file.js#W45` when the node file has a test whose name begins `W45:` or
    `W45 `. A test beside the plugin folder's own files only."""
    if ref.startswith('js:'):
        name, _, wid = ref[3:].partition('#')
        try:
            text = (ROOT / name).read_text(encoding='utf-8')
        except OSError:
            return False
        return bool(wid) and bool(re.search(r'\btest\(\s*["\'`]%s[: ]' % re.escape(wid), text))
    parts = ref.split('::')
    if len(parts) not in (2, 3) or not parts[0].endswith('.py'):
        return False
    held = _cached(ROOT / parts[0], _py_tests) or ()
    return (parts[1] if len(parts) == 3 else None, parts[-1]) in held


# ---- the tests a run has to run, and the document it gives -----------------------------------------------------------
def tests_listed(js):
    """Every test the rows (steps and edges) of the journeys list, sorted: one journey, or {id: journey}, or a list of them.
    A declared journey is not run, so it lists none."""
    if isinstance(js, dict) and 'steps' not in js:
        js = list(js.values())
    elif isinstance(js, dict):
        js = [js]
    return sorted({t for j in js if not j.get('declared') for _, _, row in rows(j) for t in row.get('tests') or []})


def compute(j, results, states=None):
    """The journey.status document of one journey: the hash of the journey as it is, each row's state with the tests that
    proved it and the ones that did not, the journey's state, the counts, and the drift. `results` is {test: 'passed' |
    'failed' | 'missing'}; a listed test it does not hold counts as missing. `states` holds the rows of other journeys (by
    row_key) a `same_as` row takes its state from. The same journey and the same results give the same document: no clock."""
    listed = tests_listed(j)
    held = {t: (results or {}).get(t) if (results or {}).get(t) in ('passed', 'failed') else 'missing' for t in listed}
    if j.get('declared'):
        got = {'%s:%s' % (kind, rid): 'declared' for kind, rid, _ in rows(j)}
    else:
        got = row_states(j, held, states)
    docs, drift = {}, []
    for kind, rid, row in rows(j):
        key = '%s:%s' % (kind, rid)
        tests = row.get('tests') or []
        claim = site_claim(row, kind)
        gone = drifts(claim, got[key])
        docs[key] = {'state': got[key], 'proven_by': [t for t in tests if held.get(t) == 'passed'],
                     'failing': [t for t in tests if held.get(t) in ('failed', 'missing')], 'site': claim, 'drift': gone}
        if gone:
            drift.append({'row': key, 'site': claim, 'state': got[key]})
    counts = {state: 0 for state in S.ROW_STATES}
    for state in got.values():
        if state in counts:
            counts[state] += 1
    return {'schema_version': 1, 'id': j['id'], 'definitions_sha': sha_of(j), 'state': journey_state(j, got), 'counts': counts,
            'tests': held, 'rows': docs, 'drift': drift}


def compute_all(js, results):
    """The documents of every journey that is not declared, {id: document}: two passes, so a `same_as` row finds the state of
    the row of another journey it points at whichever one is read first."""
    states = {}
    live = [js[i] for i in sorted(js, key=natural) if not js[i].get('declared')]
    for j in live:
        for key, state in row_states(j, {t: (results or {}).get(t) for t in tests_listed(j)}, states).items():
            states['%s:%s' % (j['id'], key)] = state
    return {j['id']: compute(j, results, states) for j in live}


# ---- JC-8: the run ---------------------------------------------------------------------------------------------------------
def _name(key):
    """'step:1' is 'step 1'."""
    return key.replace(':', ' ', 1)


def case_jc8(js, docs, on_disk, ran=True):
    """The dynamic case (JC-8), as the sentences of the problems it finds: the state of each row is computed from the results,
    a failing row fails the lane, and so does an unproven or fault row of a journey that is not declared; and each status file is
    the document the tests give now. `docs` is {id: the computed document}, `on_disk` {id: the document of the file, or None}.
    A file is missing, stale (its hash is not its journey's), different from what the tests give now, or of no journey that has
    one. With ran=False (no test was run) a file is compared by its hash only."""
    out = []
    for jid in sorted(js, key=natural):
        if js[jid].get('declared'):
            continue
        for key, row in docs[jid]['rows'].items():
            if row['state'] == 'failing':
                out.append('%s %s is failing: %s' % (jid, _name(key), ', '.join(row['failing']) or 'a test it lists did not pass'))
            elif row['state'] == 'unproven':
                out.append('%s %s is unproven: it has code and lists no test' % (jid, _name(key)))
            elif row['state'] == 'fault':
                out.append('%s %s is a fault: it has no code and no backlog entry, or a wanted row lists a test' % (jid, _name(key)))
        disk = on_disk.get(jid)
        if disk is None:
            out.append('%s has no status file: run qa/journey_status.py --write %s' % (jid, jid))
        elif disk.get('definitions_sha') != docs[jid]['definitions_sha']:
            out.append('the status file of %s is stale (the journey changed after it was written): run qa/journey_status.py --write %s' % (jid, jid))
        elif ran and disk != docs[jid]:
            out.append('the status file of %s differs from what the tests give now: run qa/journey_status.py --write %s' % (jid, jid))
    out += ['the status file %s.json belongs to no journey that has one (a journey that is not declared does): run qa/journey_status.py --write' % i
            for i in sorted(on_disk) if i not in js]
    return out
