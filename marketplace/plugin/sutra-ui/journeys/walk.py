"""journeys/walk.py -- did the journey happen the way its definition says? (PRD A3.6, "The scenario suites")

A scenario drives the real flows (founding, the board, the motor, the runtime) with a model that is a function from a step
id to an answer, reads only the record afterwards, and asks this one question. Two functions:

    trace(W, R, J, *refs)             the record of the departments given, as four lists, each in the order it was written
    follows(journey, trace, walks)    the faults of the walk: [] when the journey was followed

The trace is built from what the runtime already writes and reads nothing else: R.board(ref), R.step_rows(ref), J.events(ref)
and W.asks(ref). Nothing is written to the record by reading it, and the modules are passed in, so the scenario's own (reloaded)
ones are the ones read.

`follows` takes the steps named in `walks` (the first scenario's by default). For each, every bind that is an act, a step or an
event and is not marked `optional` must appear in the trace; at least one of its binds must appear when it has any; and within
one source (the board, the step rows, the ledger) the steps are found in order: a step's binds are looked for from the place
where the step before it was first found, so a word the owner says twice (the first words, then the answer) is two places and
not one. A `ui`, an `api` and a `person` bind are proved by the node and API tests the row lists, not by the trace. An act is matched on its sender, its act, its
word and its receiver; a step on its id, with a status that is not `failed`; an event on its action. A fault names the step and
the bind. A walk may find that the data names a sender or a step the code does not use: then the data is corrected (or the
finding written down), never the walk.
"""

#: the kinds of bind the record can show
TRACED = ('act', 'step', 'event')
#: the trace's lists, and the kind of bind each one answers for
SOURCES = {'board': 'act', 'steps': 'step', 'events': 'event'}
#: what a fault calls each source
PLACES = {'board': 'board', 'steps': 'step rows', 'events': 'ledger'}


def trace(W, R, J, *refs):
    """The record of the departments `refs`, in the order given, as {'board': [{ref, n, src, dst, act, word}], 'steps': [{engine,
    step, status}], 'events': [{action, step}], 'asks': [{kind, status}]}. `dst` is the list the post named. Reads only."""
    out = {'board': [], 'steps': [], 'events': [], 'asks': []}
    for ref in refs:
        for p in R.board(ref):
            payload = p.get('payload') if isinstance(p.get('payload'), dict) else {}
            out['board'].append({'ref': ref, 'n': p.get('n'), 'src': p.get('src'), 'dst': list(p.get('dst') or []),
                                 'act': p.get('msg_type'), 'word': payload.get('word')})
        out['steps'] += [{'engine': s.get('engine'), 'step': s.get('step'), 'status': s.get('status')} for s in R.step_rows(ref)]
        out['events'] += [{'action': e.get('action'), 'step': e.get('step')} for e in J.events(ref)]
        out['asks'] += [{'kind': a.get('kind'), 'status': a.get('status')} for a in W.asks(ref)]
    return out


def _seen(bind, rows, start=0):
    """The place of the first row of the trace, from `start` on, that this bind is; None when there is none."""
    k = bind['kind']
    for i in range(start, len(rows)):
        r = rows[i]
        if k == 'act' and (r['src'], r['act'], r['word']) == (bind.get('src'), bind.get('act'), bind.get('word')) and bind.get('dst') in r['dst']:
            return i
        if k == 'step' and r['step'] == bind.get('id') and r['status'] != 'failed':
            return i
        if k == 'event' and r['action'] == bind.get('action'):
            return i
    return None


def _said(bind):
    """The bind as a fault names it."""
    k = bind['kind']
    if k == 'act':
        return 'the act (%s, %s, %s, %s)' % (bind.get('src'), bind.get('act'), bind.get('word'), bind.get('dst'))
    return 'the %s %s' % (k, bind.get('id') if k == 'step' else bind.get('action'))


def follows(journey, trace, walks=None):
    """The faults of a walk of `journey` against `trace`: [] when it was followed. `walks` names the steps (their n); with none
    given, the steps of the journey's first scenario, or all of its steps when it has none."""
    steps = {str(s.get('n')): s for s in journey.get('steps') or []}
    if walks is None:
        scenario = (journey.get('scenarios') or [{}])[0]
        walks = scenario.get('walks') or [str(s.get('n')) for s in journey.get('steps') or []]
    jid, faults = journey.get('id'), []
    cursor = {source: 0 for source in SOURCES}              # per source: where the step before was first found
    last = {source: None for source in SOURCES}             # and which step that was
    for n in map(str, walks):
        step = steps.get(n)
        if step is None:
            faults.append('%s: the walk names step %s, and the journey has no such step' % (jid, n))
            continue
        binds = [b for b in step.get('binds') or [] if b.get('kind') in TRACED]
        found, happened, said = {source: [] for source in SOURCES}, False, len(faults)
        for b in binds:
            source = next(s for s, k in SOURCES.items() if k == b['kind'])
            rows = trace.get(source) or []
            at = _seen(b, rows, cursor[source])
            happened = happened or at is not None or _seen(b, rows) is not None
            if at is not None:
                found[source].append(at)
            elif not b.get('optional'):
                if _seen(b, rows) is None:
                    faults.append('%s step %s: %s did not happen' % (jid, n, _said(b)))
                else:
                    faults.append('%s step %s: %s happened only before step %s on the %s, and the journey puts step %s first'
                                  % (jid, n, _said(b), last[source], PLACES[source], last[source]))
        if binds and not happened and len(faults) == said:
            faults.append('%s step %s: none of its binds happened' % (jid, n))
        for source, places in found.items():
            if places:
                cursor[source], last[source] = min(places), n
    return faults
