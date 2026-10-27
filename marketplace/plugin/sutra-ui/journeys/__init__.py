"""journeys -- the user journeys as data (PRD amendment A3.6: the template at level L0, and the children that conform).

A journey is a JSON file in this folder (journeys/J1.json), or a file in journeys/functions/ that holds {"journeys": [...]}.
Each one is checked against the interface's DEFS['journey'] when it is loaded; the state of every row is never in the file
but is computed from the last run of the tests the row lists (journeys/status.py), kept one document per journey in
journeys/status/<id>.json, each with the hash of its own journey, so two packages never conflict on one file.

    FOLDER                       the folder the journeys are read from (a test points it at a temp folder)
    load()                       {id: journey}; a file that is not JSON, fits no definition or repeats an id refuses the load
    rows(j)                      [(kind, id, row)]: the steps, then the edges (the rows of `was` are history, not rows)
    row_key(jid, kind, id)       'J1:step:3' | 'J1:edge:J1.5'
    definitions_sha(jid=None)    the sha256 of one journey's canonical JSON, or of all of them
    view(jid=None)               the two read models of the API: the list, and one journey with the state of each row

Nothing here imports the runtime at import time: the interface comes through the lazy proxy of `layers`.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

from layers import S

FOLDER = Path(__file__).resolve().parent
SCHEMA_VERSION = 1

#: what the read model leaves out: the places the code and the tests live (names of acts, symbols, files), the site's Code
#: column, the page's address and the switches. They are for the cases and the walk; a screen reads the words and the
#: state of each row. The journey's own keys and a row's are not the same list: an edge's `site` is the site's words
_DROP_JOURNEY = ('site', 'site_ids', 'helper', 'flag', 'invariants')
_DROP_ROW = ('binds', 'code', 'tests', 'site_code', 'where')


class UnknownJourney(KeyError):
    """No journey has this id (the API answers 404 UNKNOWN_JOURNEY)."""


# ---- the loader ---------------------------------------------------------------------------------------------------------
def _files():
    """The journey files, in a fixed order: journeys/*.json, then journeys/functions/*.json. status/ is not read here."""
    return sorted(FOLDER.glob('*.json')) + sorted((FOLDER / 'functions').glob('*.json'))


def load():
    """Every journey of the folder, {id: journey}, each file checked against the interface (S.validate 'journey', or
    'journey.file' for a file that holds a list). A file that does not parse, fits no definition, or repeats an id refuses
    the load, naming the file, as a bad engine template does. A folder with no journeys is {}."""
    out, where = {}, {}
    for path in _files():
        name = path.relative_to(FOLDER).as_posix()
        try:
            doc = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError('the journey file %s is refused: it is not JSON (%s)' % (name, exc))
        if not isinstance(doc, dict):
            raise ValueError('the journey file %s is refused: it holds one journey, or {"journeys": [...]}' % name)
        found = S.validate('journey.file' if 'journeys' in doc else 'journey', doc)
        if found:
            raise ValueError('the journey file %s is refused: %s' % (name, found[0]))
        for j in doc['journeys'] if 'journeys' in doc else [doc]:
            if j['id'] in out:
                raise ValueError('the journey file %s is refused: %s is already a journey (in %s)' % (name, j['id'], where[j['id']]))
            out[j['id']], where[j['id']] = j, name
    return out


def rows(j):
    """The rows of one journey as [(kind, id, row)]: its steps (by n), then its edges (by id). The rows of `was` are the
    site's earlier version kept as history; they have no state and are not rows."""
    return [('step', s['n'], s) for s in j.get('steps') or []] + [('edge', e['id'], e) for e in j.get('edges') or []]


def row_key(jid, kind, rid):
    """A row across journeys: 'J1:step:3' or 'J1:edge:J1.5' (the key `same_as` is resolved by)."""
    return '%s:%s:%s' % (jid, kind, rid)


def natural(jid):
    """J2 before J10: the order ids are listed in."""
    return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', str(jid))]


# ---- the hash -----------------------------------------------------------------------------------------------------------
def sha_of(value):
    """The sha256 of the canonical JSON of a value: sorted keys, no spaces."""
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def definitions_sha(jid=None):
    """One journey's hash (what its status document is stamped with), or with no id the hash of all of them."""
    js = load()
    if jid is None:
        return sha_of(js)
    if jid not in js:
        raise UnknownJourney(jid)
    return sha_of(js[jid])


# ---- the status documents -----------------------------------------------------------------------------------------------
def status_path(jid):
    return FOLDER / 'status' / (jid + '.json')


def status_doc(jid):
    """The status document of a journey as the runner wrote it, or None when there is none that is whole."""
    try:
        doc = json.loads(status_path(jid).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get('id') != jid or S.validate('journey.status', doc):
        return None
    return doc


# ---- the read model -----------------------------------------------------------------------------------------------------
def _walk(value, fn):
    if isinstance(value, dict):
        return {k: _walk(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    return fn(value) if isinstance(value, str) else value


def _bare(row):
    """A step or an edge as a screen may read it: the words and the places they hang from, not the code and the tests."""
    return {k: v for k, v in row.items() if k not in _DROP_ROW}


def _definition(j):
    """The journey as the API gives it: everything the site lists, without the code-facing parts, `{helper}` said as the
    screen says it (the journey's own `helper.screen`, Root for now)."""
    out = {k: copy.deepcopy(v) for k, v in j.items() if k not in _DROP_JOURNEY}
    if j.get('today'):
        out['today'] = {'text': j['today']['text']}
    for key in ('steps', 'edges'):
        out[key] = [_bare(r) for r in j.get(key) or []]
    if j.get('was'):
        out['was'] = dict(j['was'], steps=[_bare(r) for r in j['was'].get('steps') or []],
                          edges=[_bare(r) for r in j['was'].get('edges') or []])
    out['build_rows'] = [_bare(r) for r in j.get('build_rows') or []]
    out['scenarios'] = [{k: v for k, v in sc.items() if k != 'test'} for sc in j.get('scenarios') or []]
    word = (j.get('helper') or {}).get('screen') or 'Root'
    return _walk(out, lambda s: s.replace('{helper}', word))


def _test_name(ref):
    """A listed test as a screen may name it: the test, never the file (names, never paths)."""
    return re.split(r'::|#', ref)[-1]


def _evaluate(js):
    """Each journey as it reads at rest: {id: {'doc': the fresh status document or None, 'stale': bool, 'rows': {local key:
    state}, 'state': str, 'counts': {state: n}}}. A declared journey has no state to compute. A journey whose status file is
    there and whose hash is the current one reads its file; any other is stale and reads its definition alone, so that a
    row which lists tests reads unknown, and a row which lists none reads what the definition says (wanted, fault ...)."""
    from journeys import status
    states = {}                                        # the rows of other journeys a `same_as` row takes its state from
    out = {}
    for jid in sorted(js, key=natural):
        j = js[jid]
        if j.get('declared'):
            out[jid] = {'doc': None, 'stale': False, 'rows': {'%s:%s' % (k, r): 'declared' for k, r, _ in rows(j)},
                        'state': 'declared', 'counts': {}}
            continue
        doc = status_doc(jid)
        fresh = doc is not None and doc['definitions_sha'] == sha_of(j)
        if fresh:
            got = {key: (doc['rows'].get(key) or {}).get('state', 'unknown') for key in ('%s:%s' % (k, r) for k, r, _ in rows(j))}
            state, counts = doc['state'], dict(doc['counts'])
        else:
            got = status.row_states(j, {}, states)
            state = status.journey_state(j, got)
            counts = {}
            for value in got.values():
                counts[value] = counts.get(value, 0) + 1
        for key, value in got.items():
            states['%s:%s' % (jid, key)] = value
        out[jid] = {'doc': doc if fresh else None, 'stale': not fresh, 'rows': got, 'state': state, 'counts': counts}
    return out


def _one(j, got):
    """The status block of one journey: its state, whether it is stale, each row's state with the tests that proved it and
    the ones that did not (by name), the site's claim for the row, and the drift."""
    from journeys import status
    doc = got['doc']
    block = {}
    for kind, rid, row in rows(j):
        key = '%s:%s' % (kind, rid)
        mine = (doc['rows'].get(key) if doc else None) or {}
        claim = status.site_claim(row, kind)
        block[key] = {'state': got['rows'][key], 'proven_by': [_test_name(t) for t in mine.get('proven_by') or []],
                      'failing': [_test_name(t) for t in mine.get('failing') or []], 'site': claim,
                      'drift': status.drifts(claim, got['rows'][key])}
    drift = [{'row': key, 'site': r['site'], 'state': r['state']} for key, r in block.items() if r['drift']]
    return {'state': got['state'], 'stale': got['stale'], 'rows': block, 'drift': drift, 'counts': got['counts']}


def view(jid=None):
    """The read model of the API (A3.6), built from the loader and the status files, and written to nothing.
    With no id: {schema_version, journeys: [{id, title, kind, inside, bound_to, declared, state, stale, counts}]} in id order.
    With an id: the definition, with `status` {state, stale, rows: {'step:1': {state, proven_by, failing, site, drift}, ...},
    drift}; UnknownJourney for an id that is not a journey. A journey is stale when its status file is missing or carries
    another hash than the journey's now; then every row that lists tests reads unknown."""
    js = load()
    if jid is not None and jid not in js:
        raise UnknownJourney(jid)
    got = _evaluate(js)
    if jid is not None:
        out = _definition(js[jid])
        out['status'] = _one(js[jid], got[jid])
        return out
    word = lambda j: (j.get('helper') or {}).get('screen') or 'Root'          # noqa: E731
    return {'schema_version': SCHEMA_VERSION,
            'journeys': [{'id': i, 'title': js[i]['title'].replace('{helper}', word(js[i])), 'kind': js[i]['kind'],
                          'inside': js[i].get('inside'), 'bound_to': js[i].get('bound_to'), 'declared': bool(js[i].get('declared')),
                          'state': got[i]['state'], 'stale': got[i]['stale'], 'counts': got[i]['counts']}
                         for i in sorted(js, key=natural)]}
