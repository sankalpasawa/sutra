"""journeys/status.py -- what a row has earned (PRD A3.6, "The state of a row: computed, never typed").

Two inputs: the definition (has the row code? tests? a backlog entry?) and the results of the last run of its tests
(`passed`, `failed`, `missing`). The functions here are pure: the same row and the same results give the same state, and
nothing is read from the record, the clock or the disk except the code roots resolve_code scans.

    row_state(row, results, states=None)   one row's state
    row_states(j, results, states=None)    {'step:1': state, 'edge:J1.5': state} for the rows of one journey
    journey_state(j, row_states)           one journey's state from its rows
    site_claim(row, kind), drifts(...)     what the site says of a row, and whether the state disagrees
"""
from journeys import row_key, rows

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
