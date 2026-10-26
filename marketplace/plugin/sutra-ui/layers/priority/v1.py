"""layers/priority/v1.py -- Priority, version 1: the implementation behind the interface's priority entries (PRD A1.18).

Its recipe is v1.json beside it: the Priority engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is registered below. A name is registered by reference to
engine_runtime's own body until the body moves here (move on touch: the body is copied into this module to be changed,
and engine_runtime's copy stays until W3-PROOF deletes the dead copies). WORDS and LAYOUT are empty, so its prompts are
still read from the .md bundle. view() returns the pane's read model by reference.
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'priority'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'

#: what an answer is called to the owner (the screen words: said yes, asked for less, said no; never grant, counter or refuse)
SAID = {'accept': 'said yes', 'counter': 'asked for less', 'reject': 'said no'}
ANSWERS = tuple(SAID)


def _say_cost(calls, usd):
    """An amount as the prompts and the notes say it: '3 calls and 0.12 USD'."""
    return '%d calls and %.2f USD' % (int(calls), float(usd))


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
    'priority_read': ref_to('priority_read'),
    'priority_post': ref_to('priority_post'),
    'priority_grant': ref_to('priority_grant'),
}
PROMPT = {
    'priority_bargain': ref_to('p_priority_bargain'),
}
DRAFT = {
    'priority_bargain_draft': ref_to('d_priority_bargain'),
}
CHECK = {
    'gate_answer_is_known': ref_to('c_gate_answer_is_known'),
    'facts_are_closed': ref_to('c_facts_are_closed'),
    'answer_has_its_price': price_is_observed,         # the step keeps its name; its covering holds the answer to its facts
    'price_is_observed': price_is_observed,
    'said_what_it_did': ref_to('c_said_what_it_did'),
}
WORDS, LAYOUT = {}, {}


def view(ref, d, events, asks):
    """Priority's pane (S.VIEWS['priority']): functions_view's read model, by reference until this layer holds its own."""
    return FV._j2_part(ref, d, 'Priority', events, asks)
