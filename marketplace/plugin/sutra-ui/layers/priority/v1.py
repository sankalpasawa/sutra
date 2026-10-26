"""layers/priority/v1.py -- Priority, version 1: the implementation behind the interface's priority entries (PRD A1.18).

Its recipe is v1.json beside it: the Priority engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is registered below. A name is registered by reference to
engine_runtime's own body until the body moves here (move on touch: the body is copied into this module to be changed,
and engine_runtime's copy stays until W3-PROOF deletes the dead copies).

What moved (M5.3: Priority prices from observed spend). priority_read estimates what a proposal would cost as the median
of what each engine's finished runs spent, with a prior for an engine with no runs, and reads the room actually left
today; p_priority_bargain tells the agent both; d_priority_bargain, the offline answer, is the same arithmetic;
priority_post answers and keeps one price row per answer; price_is_observed holds the answer to the facts. WORDS and
LAYOUT hold its words (goal, bargain), so no part of it is read from the .md bundle. view() is functions_view's pane plus
the prices.
"""
import math
import re
import statistics
import types
import uuid

from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'priority'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'

#: what an answer is called to the owner (the screen words: said yes, asked for less, said no; never grant, counter or refuse);
#: read only, since a module holds no state besides its dicts of names (A1.18)
SAID = types.MappingProxyType({'accept': 'said yes', 'counter': 'asked for less', 'reject': 'said no'})
ANSWERS = tuple(SAID)


#: a run that finished is one that spent what it spent: its work ended ok or failed. A skipped run did no work, so it
#: says nothing of what the work costs.
FINISHED = ('ok', 'failed')
#: the prior's price of one model call, when Priority's template names none (v1.json: template.call_usd)
CALL_USD = 0.04
#: an engine shaped on the fly is born from Do (R.born_template), so until it has run it is priced as Do is
PRIOR_ENGINE = 'Do'
#: which proposal a price row is for; any other word is a cost (a trial)
PROPOSALS = types.MappingProxyType({'line': 'line', 'engine': 'engine'})


def _calls(n):
    return '%d call%s' % (int(n), '' if int(n) == 1 else 's')


def _say_cost(calls, usd):
    """An amount as the prompts and the notes say it: '3 calls and 0.12 USD'."""
    return '%s and %.2f USD' % (_calls(calls), float(usd))


# ---- what a proposal would cost, and the room left (M5.3) ------------------------------------------------------------
def _template():
    return dict(((R.engine_def('Priority') or {}).get('template')) or {})


def _call_usd():
    try:
        usd = float(_template().get('call_usd', CALL_USD))
    except (TypeError, ValueError):
        return CALL_USD
    return usd if usd >= 0 else CALL_USD


def _model_steps(name):
    """How many steps of an engine call the model: those with a prompt. An engine not in the definitions is priced as Do."""
    return sum(1 for s in R.all_steps(name if R.engine_def(name) else PRIOR_ENGINE) if s.get('prompt'))


def _finished(ref, name):
    return [r for r in W.runs(ref) if r.get('engine') == name and not r.get('system') and r.get('status') in FINISHED]


def price_of(ref, name):
    """What one run of an engine costs, from what its finished runs spent (runs.json): the median of their calls, rounded
    up to a whole call, and the median of their money. With no finished run, the prior: its model steps, one call each, at
    the template's call_usd (0.04 unless the template says). {calls, usd, basis: median or prior, runs}."""
    runs = _finished(ref, name)
    if runs:
        spent = [(r.get('spend') or {}) for r in runs]
        return {'calls': int(math.ceil(statistics.median(int(x.get('calls') or 0) for x in spent))),
                'usd': round(statistics.median(float(x.get('usd') or 0.0) for x in spent), 4), 'basis': 'median', 'runs': len(runs)}
    n = _model_steps(name)
    return {'calls': n, 'usd': round(n * _call_usd(), 4), 'basis': 'prior', 'runs': 0}


def estimate_of(ref, names, basis=None):
    """priority.estimate for the engines `names`, one run of each: the sum of price_of, with each one's under per_engine."""
    per = {n: price_of(ref, n) for n in names}
    return {'calls': sum(x['calls'] for x in per.values()), 'usd': round(sum(x['usd'] for x in per.values()), 4),
            'basis': basis or (next(iter(per.values()))['basis'] if per else 'prior'), 'runs': sum(x['runs'] for x in per.values()),
            'per_engine': per}


def _limit_of(d, name):
    """An engine's limit a day: the one on the record. A workflow that is not born yet is a work engine, and will be given
    a work engine's limit (engine_runtime.engine_limit): that is the room it brings."""
    env = ((d or {}).get('envelopes') or {}).get(name)
    if isinstance(env, dict) and env:
        return env
    if R.engine_def(name) is None:
        t = R.priority_template()
        return {'calls': int(t.get('work_calls', 8)) * int(t.get('calls', W.ENVELOPE['calls'])), 'usd': float(t.get('usd', W.ENVELOPE['usd']))}
    return W.limit_of(d, name)


def room_of(ref, d, names):
    """The room left today across `names`: the sum over them of each one's limit less what it has spent today."""
    calls, usd = 0, 0.0
    for n in names:
        env, (spent_calls, spent_usd) = _limit_of(d, n), W._today_spend(ref, n)
        calls += max(0, int(env.get('calls') or 0) - spent_calls)
        usd += max(0.0, float(env.get('usd') or 0.0) - spent_usd)
    return {'calls': calls, 'usd': round(usd, 4)}


def _within(calls, usd, room):
    return calls <= int(room.get('calls') or 0) and round(usd, 4) <= round(float(room.get('usd') or 0.0), 4)


def fits_of(names, per, room, limit):
    """The longest prefix of the line that fits the room, no longer than the limit of workflows."""
    keep, calls, usd = [], 0, 0.0
    for n in names[:limit]:
        calls, usd = calls + int((per.get(n) or {}).get('calls') or 0), usd + float((per.get(n) or {}).get('usd') or 0.0)
        if not _within(calls, usd, room):
            break
        keep.append(n)
    return keep


def _cost_estimate(pl, eng):
    """A cost the proposal names (a trial: 'one more call a run, for N runs') is priced as what it adds, a call at
    call_usd for each of the N runs it names, and 1 when it names none; not as a whole run of the engine."""
    m = re.search(r'for (\d+) runs?', str(pl.get('cost') or ''))
    n = max(1, int(m.group(1))) if m else 1
    one = {'calls': n, 'usd': round(n * _call_usd(), 4), 'basis': 'prior', 'runs': 0}
    return {'calls': n, 'usd': one['usd'], 'basis': 'prior', 'runs': 0, 'per_engine': {eng: one}}


def priority_read(ctx, step, item):
    """Read what a proposal would cost against the room left (M5.3). The estimate is each engine's median over its
    finished runs, or the prior with none; the room is the sum over the proposal of each engine's limit less today's
    spend; what remains is the room less the estimate; `fits` is the longest prefix of the line that fits the room and the
    limit of workflows. The facts, which a step on the code rung can be taught from, stay closed: the word, and whether the
    whole proposal fits. Moved from engine_runtime.priority_read."""
    ref, pl = ctx['ref'], ctx['post']['payload']
    word, limit = pl.get('word'), int(_template().get('line') or 6)
    if word == 'line':
        # the department's workflows, proposed together: Priority has room for as many work engines as its template says,
        # and as many as the room left holds
        eng = None
        names = list(dict.fromkeys(str(e.get('name')) for e in pl.get('engines') or [] if isinstance(e, dict) and e.get('name')))
        est = estimate_of(ref, names, 'line')
    else:
        eng = pl.get('engine') or 'Write'
        names = [eng]
        est = estimate_of(ref, names) if word == 'engine' else _cost_estimate(pl, eng)
    room = room_of(ref, ctx.get('dept'), names)
    remaining = {'calls': room['calls'] - est['calls'], 'usd': round(room['usd'] - est['usd'], 4)}
    fits = fits_of(names, est['per_engine'], room, limit)
    return {'word': word, 'engine': eng, 'names': names, 'limit': limit, 'estimate': est, 'room': room, 'remaining': remaining,
            'fits': fits, 'facts': {'word': word, 'room': bool(names) and len(names) <= limit and len(fits) == len(names)}}


# ---- the bargain: the words the agent is sent, and the answer offline ---------------------------------------------------
def _say_estimate(read):
    est = read['estimate']
    parts = ['%s: %s, %s' % (n, _say_cost(x['calls'], x['usd']), ('from %d finished runs' % x['runs']) if x['basis'] == 'median' else 'a first guess')
             for n, x in (est.get('per_engine') or {}).items()]
    return '%s (%s)' % (_say_cost(est['calls'], est['usd']), '; '.join(parts))


def _say_remaining(read):
    room, rem = read['room'], read['remaining']
    if rem['calls'] >= 0 and rem['usd'] >= 0:
        return '%s remain of the %s left today' % (_say_cost(rem['calls'], rem['usd']), _say_cost(room['calls'], room['usd']))
    return 'short by %s against the %s left today' % (_say_cost(max(0, -rem['calls']), max(0.0, -rem['usd'])), _say_cost(room['calls'], room['usd']))


def p_priority_bargain(ctx, step, item):
    """The words Priority's agent is sent. The line part is told what the line is likely to cost, from what its engines
    have cost, and what the room left would still hold after it; the engine and cost parts are as they were. Moved from
    engine_runtime.p_priority_bargain."""
    got, pl = ctx['bag']['priority.read'], ctx['post']['payload']
    room = 'yes' if got['facts']['room'] else 'no'
    if pl.get('word') == 'line':
        lines = '\n'.join('- %s: %s' % (e.get('name'), str(e.get('does') or '')) for e in pl.get('engines') or [] if isinstance(e, dict))
        t = R.priority_template()
        return R._prompt('priority', 'bargain', 'line', ctx['ref'], source='from the Library' if pl.get('source') == 'library' else 'shaped for the goal',
                         engines=lines, calls='%d' % (int(t.get('work_calls', 8)) * int(t.get('calls', 30))), usd='%.2f' % float(t.get('usd', 6.0)),
                         room=room, limit=got.get('limit'), estimate=_say_estimate(got), remaining=_say_remaining(got))
    if pl.get('word') == 'engine':
        return R._prompt('priority', 'bargain', 'engine', ctx['ref'], room=room, **R._offer_lines(pl))
    return R._prompt('priority', 'bargain', 'cost', ctx['ref'], word=pl.get('word'), step=pl.get('step'), cost=pl.get('cost'), room=room)


def _sum_of(read, names):
    per = read['estimate'].get('per_engine') or {}
    return sum(int((per.get(n) or {}).get('calls') or 0) for n in names), sum(float((per.get(n) or {}).get('usd') or 0.0) for n in names)


def d_priority_bargain(ctx, step, item):
    """The answer offline: the same arithmetic the agent is held to. Yes when the whole proposal fits the room; for a line,
    an ask for less that keeps the longest prefix that fits when only some of it does; no when none of it fits. The why is
    only about money and room. Moved from engine_runtime.d_priority_bargain."""
    read = ctx['bag']['priority.read']
    names, fits, room = read['names'], read['fits'], read['room']
    left = _say_cost(room['calls'], room['usd'])
    if read['word'] == 'line':
        if not names:
            return {'answer': 'reject', 'why': 'the plan names no workflow'}
        if read['facts']['room']:
            return {'answer': 'accept', 'why': 'fits today: about %s of the %s left' % (_say_cost(*_sum_of(read, names)), left)}
        if fits:
            why = 'room for %d of %d today: about %s for these of the %s left' % (len(fits), len(names), _say_cost(*_sum_of(read, fits)), left)
            if len(fits) == read['limit'] < len(names):
                why += ' (the limit is %d workflows)' % read['limit']
            return {'answer': 'counter', 'why': why, 'keep': list(fits)}
        return {'answer': 'reject', 'why': 'no room today: even %s costs about %s against the %s left' % (names[0], _say_cost(*_sum_of(read, names[:1])), left)}
    cost = _say_cost(read['estimate']['calls'], read['estimate']['usd'])
    if read['facts']['room']:
        return {'answer': 'accept', 'why': 'fits today: about %s of the %s left' % (cost, left)}
    return {'answer': 'reject', 'why': 'no room today: about %s against the %s left' % (cost, left)}


# ---- the answer, and the price it leaves ---------------------------------------------------------------------------------
def _check_of(ref, name):
    """The check verdict of an engine's latest finished run, an index of Priority's: ok or failed when the run filed a
    version (its status is that version's check), none when it filed nothing or has not run."""
    runs = _finished(ref, name)
    if not runs or not (runs[-1].get('wrote') or {}).get('art'):
        return 'none'
    return 'ok' if runs[-1].get('status') == 'ok' else 'failed'


def _price_row(ctx, read, answer, keep, why):
    """One priority.price row for an answer given (prices.jsonl, through the interface's journal): what the proposal was,
    what it would cost, the room, what remained, the answer and what it keeps, and the indices (per-run spend and the check
    verdict of each engine)."""
    ref, p = ctx['ref'], ctx['post']
    names = [n for n in read.get('names') or [] if re.match(S.NAME_RE, n)]
    per = read['estimate'].get('per_engine') or {}
    row = {'schema_version': 1, 'id': 'pr-' + uuid.uuid4().hex[:8], 'at': W.now(), 'cycle_id': (J._state(ref) or {}).get('cycle_id'),
           'round': None, 'proposal': PROPOSALS.get((p.get('payload') or {}).get('word'), 'cost'), 'engines': names,
           'estimate': read['estimate'], 'room': read['room'], 'remaining': read['remaining'], 'answer': answer,
           'keep': [n for n in keep if n in names], 'why': str(why or '')[:600],
           'indices': {'spend_per_run': {n: per[n]['usd'] for n in names if n in per}, 'checks': {n: _check_of(ref, n) for n in names}}}
    if p.get('thread'):
        row['thread'] = str(p['thread'])[:80]
    try:
        return W.append_row(ref, 'prices.jsonl', row)
    except S.SchemaFault:
        return None                      # the fault is a row and a count already (A1.20); a price never costs Adaptation its answer


def priority_post(ctx, step, item):
    """Post the answer, and keep its price: one priority.price row per answer given. A line is answered as a whole: yes, no,
    or an ask for less that keeps the workflows the agent named, else the longest prefix that fits. Moved from
    engine_runtime.priority_post; the answers and the words are the same."""
    ref, pl, thread = ctx['ref'], ctx['post']['payload'], ctx['post']['thread']
    read, got = ctx['bag']['priority.read'], ctx['bag']['priority.bargain']
    names, answer, why = list(read.get('names') or []), got.get('answer'), str(got.get('why') or '').strip()
    if pl.get('word') == 'line':
        if answer == 'counter':
            asked = [str(k) for k in got.get('keep') or []]
            keep = [n for n in names if n in asked] or list(read.get('fits') or [])
            if keep and len(keep) < len(names):
                why = why or 'the envelope has room for %d of them' % len(keep)
                row = R.post(ref, 'Priority', 'Adaptation', 'propose', {'word': 'line', 'counter': True, 'keep': keep, 'why': why}, thread=thread)
                if row:
                    _price_row(ctx, read, 'counter', keep, why)
                return {'said': 'asked for less on the line: keep ' + ' -> '.join(keep) if row else 'the bargain reached its bound'}
            answer = 'reject' if not keep else 'accept'
        ok = answer == 'accept'
        why = why or ('the envelope has room' if ok else 'the envelope has no room')
        body = {'word': 'line', 'why': why}
        if not ok:
            # a no carries the ways forward, built by code and priced: raise, leave, stop (M5.4); Adaptation hands them on
            body['options'] = line_options(ref, ctx['dept'], names, _covers_of(ctx['dept'], pl), read['estimate'],
                                           read['room'], read.get('fits'), int(read.get('limit') or 6))
        row = R.post(ref, 'Priority', 'Adaptation', 'accept-proposal' if ok else 'reject-proposal', body, thread=thread)
        if row:
            _price_row(ctx, read, 'accept' if ok else 'reject', names if ok else [], why)
        return {'said': ('said yes to' if ok else 'said no to') + ' the line ' + ' -> '.join(names) if row else 'the bargain reached its bound'}
    ok = answer == 'accept'
    row = R.post(ref, 'Priority', 'Adaptation', 'accept-proposal' if ok else 'reject-proposal',
                 {'word': pl.get('word'), 'step': pl.get('step'), 'to': pl.get('to'), 'form': pl.get('form'), 'why': got.get('why')}, thread=thread)
    if row:
        _price_row(ctx, read, 'accept' if ok else 'reject', names if ok else [], why or ('the envelope has room' if ok else 'the envelope has no room'))
    return {'said': ('said yes to' if ok else 'said no to') + ' a trial of ' + str(pl.get('step'))}


def _fact_notes(ctx, out):
    """What the facts Priority read say against the answer (M5.3): a yes, or an ask for less, never spends what the room
    does not hold. A no, or a smaller yes, always stands: approvals only tighten (S-08). Empty when the step has no facts
    to hold the answer to (the contract's samples, a department's older read)."""
    read = ((ctx or {}).get('bag') or {}).get('priority.read')
    if not isinstance(read, dict) or not isinstance(read.get('estimate'), dict) or not isinstance(read.get('room'), dict):
        return []
    names, answer = list(read.get('names') or []), out.get('answer')
    per = read['estimate'].get('per_engine') or {}
    room, limit = read['room'], int(read.get('limit') or len(names) or 1)
    if answer == 'accept':
        keep = names
    elif answer == 'counter':
        keep = [str(k) for k in out.get('keep') or [] if str(k).strip()]
        strange = [k for k in keep if k not in names]
        if strange:
            return ['an ask for less keeps %s, which the proposal does not name' % ', '.join(strange)]
    else:
        return []
    calls = sum(int((per.get(n) or {}).get('calls') or 0) for n in keep)
    usd = round(sum(float((per.get(n) or {}).get('usd') or 0.0) for n in keep), 4)
    over = []
    if not keep:
        over.append('it keeps nothing to pay for')
    if len(keep) > limit:
        over.append('%d workflows go past the limit of %d' % (len(keep), limit))
    if calls > int(room.get('calls') or 0) or usd > round(float(room.get('usd') or 0.0), 4):
        over.append('%s go past the %s left today' % (_say_cost(calls, usd), _say_cost(room.get('calls') or 0, room.get('usd') or 0.0)))
    if not over:
        return []
    return ['%s what costs more than the room holds: %s' % ('said yes to' if answer == 'accept' else 'asked to keep', '; '.join(over))]


def price_is_observed(ctx, step, item, out):
    """Priority's covering (M2.4, M5.3): yes, less or no, each with its price, and the price held to the facts. The answer
    names its price: the line that says what it costs against the room left; an ask for less names what it keeps. Then the
    facts Priority read stand over it: what a yes or an ask for less keeps costs no more than the room left, and no more
    workflows than the limit. An answer that fails them fails the step; nothing is taken in its place. The body of
    engine_runtime's answer_has_its_price, with the facts added."""
    notes = []
    if out.get('answer') not in ANSWERS:
        notes.append('not an answer: %r' % (out.get('answer'),))
    if not str(out.get('why') or '').strip():
        notes.append('the answer names no price: nothing says what it costs against the room left')
    if out.get('answer') == 'counter' and not [k for k in out.get('keep') or [] if str(k).strip()]:
        notes.append('an ask for less names nothing to keep')
    if not notes:
        notes += _fact_notes(ctx, out)
    # the note is said on Priority's card, so it names the answer in the owner's words (said yes, asked for less, said no)
    return {'ok': not notes, 'notes': notes or ['%s, with its price: %s' % (SAID.get(out.get('answer'), out.get('answer')), str(out['why']).strip())]}


# ---- the ways forward at a limit, priced by code (M5.4) ----------------------------------------------------------------------
# A limit reaches the owner as one question with up to three ways forward: raise (add budget, up to RAISE_CAP times where it
# started), leave (give up the done-when item the work was for) and stop. Every word of them is built here by code from the
# prices Priority holds; no model writes an option. Identity puts them to the owner, on the card it files.
#: the least a limit rises by to hold one more run when the run itself is priced at nothing: a call, and a cent
STEP_CALLS, STEP_USD = 1, 0.01


def _slug(name):
    """An engine's name as an option id carries it: the id's tail takes letters, digits, '_', '.' and '-' (S.DEFS['option'])."""
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '-', str(name or '')).strip('-')[:40] or 'engine'
    return slug + '-engine' if slug.lower() == 'ceiling' else slug


def _more(calls, usd):
    """What a raise adds, as the cost line says it: '7 calls and 0.30 USD'."""
    parts = ([_calls(calls)] if calls > 0 else []) + (['%.2f USD' % usd] if usd > 0 else [])
    return ' and '.join(parts) or 'nothing'


def _on_record(d):
    """The engines whose limit is on the department's record: a limit can be raised only for one of them."""
    return {e[0] for e in W.engines_of(d)} | set(W.SYSTEMS)


def _covers_of(d, pl=None):
    """Which engines cover each done-when item, {item: [engine]}: the proposal's own (act.line covers) when it names them,
    else the last registered plan's, else the interface's reading of the engines it names."""
    got = (pl or {}).get('covers')
    if isinstance(got, dict) and got:
        return {str(k): [str(e) for e in v or []] for k, v in got.items()}
    if not (pl or {}).get('engines'):
        wf = [w for w in (d or {}).get('workflows') or [] if isinstance(w, dict)]
        if wf and isinstance(wf[-1].get('covers'), dict):
            return {str(k): [str(e) for e in v or []] for k, v in wf[-1]['covers'].items()}
        return {}
    try:
        return {k: list(v) for k, v in (S.as_workflow(pl['engines'], pl.get('source') or 'library', d).get('covers') or {}).items()}
    except Exception:  # noqa: BLE001 -- a proposal the interface cannot read covers nothing, and no item is offered to leave out
        return {}


def _left_out(d, covered):
    """The done-when item an option may leave out: the last of `covered`, a list of item ids, that done-when holds; none when
    it would be left empty (done-when keeps at least one item)."""
    items = [i for i in W.items_of(d) if i.get('id')]
    pool = [i for i in items if i['id'] in covered]
    return pool[-1] if len(items) > 1 and pool else None


def _only_by(covers, names):
    """The items covered by `names` and by nothing else: what stops being built when they are cut."""
    return [i for i, es in (covers or {}).items() if es and all(e in names for e in es)]


def _leave_option(item):
    return W.option('leave:' + item['id'], 'Leave %s out' % item['id'],
                    '%s is dropped from done-when (%s); nothing more is spent' % (item['id'], str(item.get('text') or '').rstrip('.')[:250]))


def _stop_option():
    return W.option(W.STOP_OPTION, 'Stop here', 'the department stops where it is; you can start it again later')


def _raised(d, name, calls, usd):
    """The limit one engine may be raised to when it needs `calls` and `usd` a day: those, and never less than it has, held to
    RAISE_CAP times where it started. None when that is past the cap, or no raise at all."""
    cur = _limit_of(d, name)
    calls, usd = max(int(calls), int(cur.get('calls') or 0)), round(max(float(usd), float(cur.get('usd') or 0.0)), 4)
    if W.envelope_over(d, name, calls, usd) or (calls, usd) == (int(cur.get('calls') or 0), round(float(cur.get('usd') or 0.0), 4)):
        return None
    return calls, usd


def envelope_option(d, name, calls, usd):
    """The option to raise one engine's limit to `calls` and `usd` a day (option.raise, what 'envelope'): the params carry the
    limits it becomes, so choosing it twice is choosing it once; the cost line says how much more, and what the limit becomes."""
    cur = _limit_of(d, name)
    more_calls, more_usd = int(calls) - int(cur.get('calls') or 0), round(float(usd) - float(cur.get('usd') or 0.0), 4)
    return W.option('raise:' + _slug(name), 'Add budget for %s' % name,
                    "about %s more a day; %s's limit becomes %s a day" % (_more(more_calls, more_usd), name, _say_cost(calls, usd)),
                    {'what': 'envelope', 'engine': name, 'calls': int(calls), 'usd': float(usd)})


def hold_options(ref, d, name, calls, usd, env):
    """The ways forward for an engine held at its limit (J2.5): raise the limit enough to run once more (never past
    RAISE_CAP times where it started), leave out the item only this engine is for, stop. `calls` and `usd` are what it has
    spent today, `env` its limit."""
    price = price_of(ref, name)
    want_calls = int(env.get('calls') or 0) if calls < int(env.get('calls') or 0) else calls + max(int(price['calls']), STEP_CALLS)
    want_usd = float(env.get('usd') or 0.0) if usd < float(env.get('usd') or 0.0) else round(usd + max(float(price['usd']), STEP_USD), 4)
    opts, got = [], _raised(d, name, want_calls, want_usd)
    if got:
        opts.append(envelope_option(d, name, *got))
    item = _left_out(d, _only_by(_covers_of(d), [name]))
    if item:
        opts.append(_leave_option(item))
    return opts + [_stop_option()]


def _hold_ask(ref, d, name, slot, calls, usd, env):
    """The ask an engine held at its limit files (J2.5): the limit, what it has used, what happens next, and the ways forward."""
    text = ("%s is out of today's envelope: it has used %d of its %d calls and %.2f of its %.2f USD. It waits until tomorrow, "
            "unless you choose a way forward." % (name, calls, int(env.get('calls') or 0), usd, float(env.get('usd') or 0.0)))
    return W.options_ask('envelope', text, hold_options(ref, d, name, calls, usd, env), engine=name, slot=slot, escalated=True)


def priority_envelope(ctx, step, item):
    """Priority's gate: an engine past its envelope for the day waits (J2.5), and the owner is asked once, on one card that
    names the limit and what the engine has used and carries the ways forward as options built by code (M5.4). The hold is on
    the ledger once for its slot, however often the motor asks again (M0.4). Moved from engine_runtime.priority_envelope; the
    gate's answers are the same."""
    ref, name, slot = ctx['ref'], ctx['engine'], ctx['slot']
    calls, usd = W._today_spend(ref, name)
    env = W.limit_of(ctx['dept'], name)
    if calls >= env.get('calls', 0) or usd >= env.get('usd', 0):
        if not any(x.get('kind') == 'envelope' and x.get('engine') == name and x['status'] == 'pending' for x in W.asks(ref)):
            W._put_ask(ref, _hold_ask(ref, ctx['dept'], name, slot, calls, usd, env))
        if not ctx.get('peek'):
            # a panel read asking the same question writes nothing; Coordination's other waits stay in the status's 'next'
            try:
                J.on_held(ref, name, slot, "%s is out of today's envelope" % name)
            except ImportError:
                pass                              # a department runs without its lifecycle record rather than not at all
        return 'wait', '%s is out of its envelope' % name
    return 'admit', None


def line_options(ref, d, names, covers, est, room, fits, limit):
    """The ways forward for a line Priority said no to (M5.4), at most three. Raise: the first engine of the line the room
    does not reach is given what the line is short of, when that stays inside RAISE_CAP times where it started and money is what
    the line is short of (a line of more workflows than the limit is mended by no raise). Leave: the last done-when item that
    only the cut engines were building. Stop."""
    names, opts = list(names or []), []
    short_calls, short_usd = max(0, int(est['calls']) - int(room['calls'])), max(0.0, round(float(est['usd']) - float(room['usd']), 4))
    if names and len(names) <= limit and (short_calls or short_usd):
        record = _on_record(d)
        for n in [n for n in names if n not in (fits or [])] or names:
            if n not in record:
                continue                          # an engine not born yet has no limit of its own to raise
            spent_calls, spent_usd = W._today_spend(ref, n)
            cur = _limit_of(d, n)
            got = _raised(d, n, max(int(cur['calls']), spent_calls) + short_calls, max(float(cur['usd']), spent_usd) + short_usd)
            if got:
                opts.append(envelope_option(d, n, *got))
                break
    item = _left_out(d, _only_by(covers, [n for n in names if n not in (fits or [])] or names))
    if item:
        opts.append(_leave_option(item))
    return (opts + [_stop_option()])[:S.OPTIONS_MAX]


def limit_options(ref, thread=None):
    """The ways forward for a bargain that reached its limit (hops, time or spend): the options a no would have carried, for
    the line Adaptation last proposed in `thread`, priced from what its engines have cost and the room left today. Built
    by code. [] when no line was proposed there. Called by whoever puts the limit to the owner (the conflict's ask)."""
    offer = (R._line_proposal(ref, thread) if thread else None) or {}
    d = W.dept(ref) or {}
    names = list(dict.fromkeys(str(e.get('name')) for e in offer.get('engines') or [] if isinstance(e, dict) and e.get('name')))
    if not names:
        return []
    est, room = estimate_of(ref, names, 'line'), room_of(ref, d, names)
    limit = int(_template().get('line') or 6)
    return line_options(ref, d, names, _covers_of(d, offer), est, room, fits_of(names, est['per_engine'], room, limit), limit)


def check_raise(ref, option):
    """A raise the owner chose, held to the cap before it is recorded: AskError OVER_CAP when it would take a limit past
    RAISE_CAP times where it started. Nothing is written."""
    p = (option or {}).get('params')
    p = p if isinstance(p, dict) else {}
    d = W.dept(ref)
    if not d:
        raise ValueError('no department at %s' % ref)
    if p.get('what') == 'envelope':
        name = str(p.get('engine') or '')
        if name not in _on_record(d):
            raise ValueError('no engine named %s' % name)
        over = W.envelope_over(d, name, p.get('calls'), p.get('usd'))
    elif p.get('what') == 'ceiling':
        over = _ceiling_over(d, p)
    else:
        raise ValueError('this raise names nothing to raise')
    if over:
        raise W.AskError('OVER_CAP', over)


def ceiling_of(d):
    """The goal's ceiling on the record (priority.ceiling), or None."""
    c = (d or {}).get('ceiling')
    return c if isinstance(c, dict) and c.get('start') else None


def _ceiling_over(d, p):
    """None, or in words how far the ceiling may be raised, when `p` (what 'ceiling': rounds, calls, usd) takes it past
    RAISE_CAP times where it started."""
    c = ceiling_of(d)
    if not c:
        return None
    start = c['start']
    over = []
    for key, say in (('rounds', 'rounds'), ('calls', 'calls'), ('usd', 'USD')):
        want, now_ = p.get(key), c.get(key)
        cap = S.RAISE_CAP * float(start.get(key) or 0)
        if want is not None and float(want) > float(now_ or 0) and round(float(want), 4) > round(cap, 4):
            over.append(('%d %s' if key != 'usd' else '%.2f %s') % (cap, say))
    return ("the goal's ceiling may be raised to %s, twice where it started, and no further" % ', '.join(over)) if over else None


def _raise_envelope(ref, p):
    d = W.dept(ref) or {}
    name = str(p.get('engine') or '')
    cur = W.limit_of(d, name)
    calls = max(int(p.get('calls') if p.get('calls') is not None else cur.get('calls') or 0), int(cur.get('calls') or 0))
    usd = round(max(float(p.get('usd') if p.get('usd') is not None else cur.get('usd') or 0.0), float(cur.get('usd') or 0.0)), 4)
    if (calls, usd) == (int(cur.get('calls') or 0), round(float(cur.get('usd') or 0.0), 4)):
        return {'what': 'envelope', 'engine': name, 'envelope': dict(cur), 'raised': False}     # already as high: the same choice twice
    env = W.set_envelope(ref, name, calls=calls, usd=usd, by='option')
    return {'what': 'envelope', 'engine': name, 'envelope': env, 'raised': True}


def _raise_ceiling(ref, p):
    with W._lock(ref):
        d = W.dept(ref) or {}
        c = ceiling_of(d)
        if not c:
            raise ValueError('the goal has no ceiling to raise yet')
        over = _ceiling_over(d, p)
        if over:
            raise W.AskError('OVER_CAP', over)
        to = {'rounds': max(int(p.get('rounds') or 0), int(c['rounds'])), 'calls': max(int(p.get('calls') or 0), int(c['calls'])),
              'usd': round(max(float(p.get('usd') or 0.0), float(c['usd'])), 4)}
        if to == {'rounds': c['rounds'], 'calls': c['calls'], 'usd': round(float(c['usd']), 4)}:
            return {'what': 'ceiling', 'ceiling': dict(c), 'raised': False}
        c = dict(c, **to)
        c['raised'] = list(c.get('raised') or []) + [{'at': W.now(), 'by': 'the owner', 'to': dict(to)}]
        d['ceiling'] = c
        W.save_dept(ref, d, by='priority')
    W.system_run(ref, 'Priority', "the owner's choice raised the goal's ceiling: %d rounds, %s" % (to['rounds'], _say_cost(to['calls'], to['usd'])))
    return {'what': 'ceiling', 'ceiling': c, 'raised': True}


def apply_option(ref, ask, option):
    """The owner chose to add budget (raise, option.raise): the limit the option names becomes the engine's envelope, or the
    goal's ceiling, through W.set_envelope with by='option' (past RAISE_CAP times where it started, AskError OVER_CAP). Never
    lowers a limit, and a raise already made is not made again, so Identity's step may apply what the card already did.
    Returns {what, raised, ...}."""
    p = (option or {}).get('params')
    p = p if isinstance(p, dict) else {}
    if p.get('what') == 'envelope':
        return _raise_envelope(ref, p)
    if p.get('what') == 'ceiling':
        return _raise_ceiling(ref, p)
    raise ValueError('this raise names nothing to raise')


def apply_choice(ref, ask, option):
    """What the owner chose on a card Priority filed (the limit card of an engine held at its envelope, which has no thread
    for Identity's step to apply it): a raise is Priority's; leave and stop are the owner's own act, put in place here so
    the card never says 'You chose' over nothing applied. On a card with a thread, only a raise is applied here; Identity
    applies the rest."""
    kind = str((option or {}).get('kind') or str((option or {}).get('id') or '').split(':', 1)[0])
    if kind == 'raise':
        return apply_option(ref, ask, option)
    if (ask or {}).get('kind') != 'envelope' or (ask or {}).get('thread'):
        return {}
    if kind == 'stop':
        if J._state(ref):
            J.stop(ref)
        else:
            W.set_stopped(ref, True)
        return {'stopped': True}
    if kind == 'leave':
        iid = str((option or {}).get('id') or '').split(':', 1)[1] if ':' in str((option or {}).get('id') or '') else ''
        items = W.items_of(W.dept(ref) or {})
        gone = next((i for i in items if i['id'] == iid), None)
        if not gone:
            return {'left_out': None}
        done = W.done_items_ask('Leave %s out of done-when: %s. The goal stays as it is' % (iid, str(gone['text']).rstrip('.')),
                                [i for i in items if i['id'] != iid], 'the engine was held at its limit, and you chose to leave it out',
                                words=(ask.get('chosen') or {}).get('label'))
        done.update({'status': 'stamped', 'decided': W.now(), 'by': 'the owner'})    # the owner's one click is its stamp
        W._put_ask(ref, done)
        W.apply_done_items(ref, done)
        return {'left_out': iid}
    return {}


CODE = {
    'priority_envelope': priority_envelope,
    'priority_read': priority_read,
    'priority_post': priority_post,
    'priority_grant': ref_to('priority_grant'),
}
PROMPT = {
    'priority_bargain': p_priority_bargain,
}
DRAFT = {
    'priority_bargain_draft': d_priority_bargain,
}
CHECK = {
    'gate_answer_is_known': ref_to('c_gate_answer_is_known'),
    'facts_are_closed': ref_to('c_facts_are_closed'),
    'answer_has_its_price': price_is_observed,         # the step keeps its name; its covering holds the answer to its facts
    'price_is_observed': price_is_observed,
    'said_what_it_did': ref_to('c_said_what_it_did'),
}
# Priority's words (A1.16): what `python -m layers.prompts --extract priority` makes of the .md bundle by the split rule,
# byte for byte (test_layer_prompts and the M2.1a snapshot prove it). The bargain line part has no field the owner may change,
# so its words stay in the layout; engine and cost have a task each.
WORDS = {
    'goal': {
        'does': {
            'text': 'grants each engine its envelope and answers proposals that cost something',
        },
        'skills': {
            'items': [
                'hold an engine to its envelope',
                'answer a proposal that costs something',
            ],
        },
    },
    'bargain': {
        'line': {},
        'engine': {
            'task': 'Adaptation proposes an engine for this department, from an idea the owner floated.',
        },
        'cost': {
            'task': 'Adaptation proposes something that costs.',
        },
    },
}
LAYOUT = {
    'goal': {
        'does': '{text}',
        'skills': '{items}',
    },
    'bargain': {
        'line': (
            'Adaptation proposes the workflows this department runs to reach its goal, {{source}}:\n'
            '{{engines}}\n'
            'WHAT EACH COSTS: up to {{calls}} calls and {{usd}} USD a day.\n'
            'ROOM FOR THIS MANY WORKFLOWS: {{room}} (the limit is {{limit}})\n'
            'WHAT THE LINE IS LIKELY TO COST, from what each has cost before: {{estimate}}\n'
            "WHAT REMAINS OF TODAY'S ROOM AFTER IT: {{remaining}}\n"
            '\n'
            'accept: grant them all. counter: grant only some, and name which to keep, in order. reject: grant '
            'none. Give your reason in money and room, from the figures above.\n'
            '{returns}'
        ),
        'engine': (
            '{task}\n'
            'THE ENGINE: {{engine}}\n'
            'WHAT IT DOES: {{does}}\n'
            'WHAT IT NEEDS: {{needs}}\n'
            'WHAT IT COSTS: {{calls}} calls and {{usd}} USD a day, the envelope of one more work engine\n'
            'ROOM IN THE ENVELOPE TODAY: {{room}}\n'
            '\n'
            '{returns}'
        ),
        'cost': (
            '{task}\n'
            'THE PROPOSAL: {{word}}, for the step {{step}}\n'
            'WHAT IT COSTS: {{cost}}\n'
            'ROOM IN THE ENVELOPE TODAY: {{room}}\n'
            '\n'
            '{returns}'
        ),
    },
}


#: the most prices the pane carries: the newest, as the bargains it sits beside are the newest few
PRICES_SHOWN = 12


def _prices(ref):
    """What Priority priced and answered, newest first, from prices.jsonl and in the owner's words: the answer as said yes,
    asked for less or said no, the estimate and the room as two amounts each, and the why as Priority gave it. A row that
    holds no answer is not shown."""
    out = []
    for r in reversed([r for r in W.rows(ref, 'prices.jsonl') if isinstance(r, dict)]):
        if r.get('answer') not in SAID:
            continue
        est, room = r.get('estimate') or {}, r.get('room') or {}
        out.append({'at': r.get('at'), 'proposal': r.get('proposal'), 'answer': r['answer'], 'said': SAID[r['answer']],
                    'estimate': {'calls': int(est.get('calls') or 0), 'usd': float(est.get('usd') or 0.0)},
                    'room': {'calls': int(room.get('calls') or 0), 'usd': float(room.get('usd') or 0.0)},
                    'why': str(FV._plain(r.get('why')) or '')[:600]})
    return FV._clean(out[:PRICES_SHOWN])


def view(ref, d, events, asks):
    """Priority's pane (S.VIEWS['priority']): the bargains and the envelopes, as functions_view reads them from the record,
    and the prices, from prices.jsonl (M5.3). Nothing is written."""
    part = FV._j2_part(ref, d, 'Priority', events, asks)
    part['prices'] = _prices(ref)
    return part
