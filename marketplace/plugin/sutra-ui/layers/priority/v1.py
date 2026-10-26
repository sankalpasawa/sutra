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
        row = R.post(ref, 'Priority', 'Adaptation', 'accept-proposal' if ok else 'reject-proposal', {'word': 'line', 'why': why}, thread=thread)
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


CODE = {
    'priority_envelope': ref_to('priority_envelope'),
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

# ---- the function template's words (A3.4.5, A3-FUNCTIONS F1) ---------------------------------------------------------
# Parts of the goal group that S.ADDED_PARTS lists (they have no .md part), and the layout of the role block the card
# carries (A3.4.3). What the function is not, what it never does and who it hands on to are S.FUNCTION_TEMPLATE's, not
# words: no version drops one.
WORDS['goal']['done'] = {'text': 'every proposal has an answer with its price, and no run went past its limit without a hold and an ask'}
WORDS['goal']['role_is'] = {'text': (
    "the department's keeper of the budget; it decides whether a proposal deserves resources now, and "
    'the limit inside which each engine may run'
)}
WORDS['goal']['role_may'] = {'items': [
    'accept a proposal, counter it with a smaller limit or scope, or reject it, always with its price',
    'give an engine the limit it runs within: calls and money a day',
    'hold a run that is over its limit, and say what is over',
    'price a proposal from what runs have really cost, and say on what it rests',
    'bargain with Adaptation for up to four exchanges',
    'send an unsettled disagreement to Identity with both final positions',
]}
WORDS['goal']['role_procedure'] = {'items': [
    'Check that the proposal says what it costs and what it will make.',
    'Compare it with what is already committed.',
    'Think about what accepting it would push out.',
    (
        'Give exactly one answer: accept, with its limit; counter, with a smaller limit or scope; or '
        'reject, with a reason about the room.'
    ),
    'Bargain with Adaptation for at most four exchanges.',
    'If you cannot agree, send the disagreement to Identity with both final positions.',
]}
WORDS['goal']['role_patterns'] = {'items': [
    'Rejecting by habit to save everything.',
    'Treating an estimated cost as a known cost.',
    'Making it cheap instead of making it move the goal.',
    'Managing the steps of a workflow.',
    'Forgetting what accepting a proposal pushes out.',
]}
WORDS['goal']['role_block'] = {}
LAYOUT['goal'].update({'done': '{text}', 'role_is': '{text}', 'role_may': '{items}', 'role_procedure': '{items}',
                      'role_patterns': '{items}', 'role_block': S.ROLE_BLOCK_LAYOUT})


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
