"""layers/coordination/v1.py -- Coordination, version 1: the implementation behind the interface's coordination entries (PRD A1.18).

Its recipe is v1.json beside it: the Coordination engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here by reference (A1 K1): a late-bound delegate to
the body in engine_runtime's Coordination region (ref_to), so the module names what its recipe needs and no behaviour
changes. A body moves into this module when this layer changes it (move on touch); engine_runtime's copy stays until W3-PROOF.
WORDS and LAYOUT hold Coordination's two prompt files, goal (does, skills) and tie (tie), so layers.prompt serves them from here
and the .md bundle is read for none of its parts (K2). view() and engine_card() return the pane's and the card's read
models by reference (K4).
"""
import json
import os
import re

from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'coordination'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'
CODE = {name: ref_to(name) for name in (
    'coord_busy', 'coord_pick', 'coord_edge', 'coord_verdict', 'coord_bounds', 'coord_alarm',   # the rules
    'coord_chain',                                                                              # the gate
    'coord_heard', 'coord_table',                                                               # the handlers: a verdict, an engine born
    'coord_ready', 'coord_record',                                                              # the steps
)}
PROMPT = {'coord_tie': ref_to('p_coord_tie')}
DRAFT = {'coord_tie_draft': ref_to('d_coord_tie')}
CHECK = {name: ref_to(body) for name, body in (
    ('one_run_at_a_time', 'c_one_run_at_a_time'),
    ('names_who_goes_first', 'c_names_who_goes_first'),
    ('chain_under_its_limit', 'c_chain_under_its_limit'),
    ('gate_answer_is_known', 'c_gate_answer_is_known'),        # shared (S.SHARED_CHECKS)
    ('said_what_it_did', 'c_said_what_it_did'),
    ('facts_are_closed', 'c_facts_are_closed'),
)}
#: A1.16: the default words of each prompt part and the layout that arranges them, by the split rule (`python -m layers.prompts
#: --extract coordination`); an owner's change is a typed value over these (instructions.json), never an edit here
WORDS = {
    'goal': {
        'does': {
            'text': (
                'keeps what engines share: one run at a time, who goes first when several are ready, who may post '
                "to whom, the chain's limit, a thread's bounds, and the alarm. Its own agent says who goes first "
                'when several functions are ready at once'
            ),
        },
        'skills': {
            'items': [
                'keep one run at a time',
                'say who goes first',
                'check who may post what to whom',
                'stop a chain at its limit',
                'close a thread at its bound',
                'raise an alarm',
                'say who goes first among equals',
            ],
        },
    },
    'tie': {
        'tie': {
            'task': 'Several functions of the department are ready at once, and one runs at a time. Say who goes first.',
        },
    },
}
LAYOUT = {
    'goal': {
        'does': '{text}',
        'skills': '{items}',
    },
    'tie': {
        'tie': (
            '{task}\n'
            'READY NOW: {{ready}}\n'
            'WHAT EACH DOES: {{what}}\n'
            "COORDINATION'S TABLE, THE USUAL ORDER: {{order}}\n"
            'WAITING FOR THE OWNER: {{waiting}}\n'
            '\n'
            '{returns}'
        ),
    },
}

# ---- the function template's words (A3.4.5, A3-FUNCTIONS F1) ---------------------------------------------------------
# Parts of the goal group that S.ADDED_PARTS lists (they have no .md part), and the layout of the role block the card
# carries (A3.4.3). What the function is not, what it never does and who it hands on to are S.FUNCTION_TEMPLATE's, not
# words: no version drops one.
WORDS['goal']['done'] = {'text': (
    'every ready engine had its turn by the rule the table declares, one run at a time, and no chain, '
    'window or lost request went unanswered'
)}
WORDS['goal']['role_is'] = {'text': (
    "the department's operating timetable; it decides which registered engine is ready, what must "
    'happen before it, and how work that happens at the same time stays apart'
)}
WORDS['goal']['role_may'] = {'items': [
    'name which ready engine goes first, and the rule it used',
    'hold a run and say exactly what is missing',
    'schedule another ready engine instead of stopping the department when one is held',
    'give each engine a slot, and record who makes and who reads each thing',
    'raise an alarm to Identity when a run is past its window, and say a request nobody answered back',
]}
WORDS['goal']['role_procedure'] = {'items': [
    'Consider only workflows that are registered and have a limit.',
    'Check their triggers and what they wait for.',
    'Check locks, shared writers and actions that cannot happen together.',
    'Pick the next one by the rule the table declares.',
    'Record its slot, its hand-offs and what blocks it.',
    'If it cannot run, hold it and name the exact condition that is missing.',
    'If another ready workflow exists, schedule it rather than stopping the department.',
]}
WORDS['goal']['role_patterns'] = {'items': [
    'Scheduling something that is not registered.',
    "Taking 'most important' as permission to break a dependency.",
    'Stopping all work because one workflow is held.',
    'Choosing who goes first without saying the rule.',
    'Becoming a project manager who changes scope.',
]}
WORDS['goal']['role_block'] = {}
LAYOUT['goal'].update({'done': '{text}', 'role_is': '{text}', 'role_may': '{items}', 'role_procedure': '{items}',
                      'role_patterns': '{items}', 'role_block': S.ROLE_BLOCK_LAYOUT})


# ---- questions between engines (board/1, PRD M4.9, W3-BOARD) ------------------------------------------------------------------
# Behind SUTRA_BOARD_QUESTIONS (off unless it is set): a work step's answer may carry a question for an earlier engine of the
# line that has filed. Coordination takes the question in its handler, within the bounds question_is_bounded holds, and files it
# in questions.json, which exists only once a question was put with the flag on.
#: the build flag of the board, read here and nowhere else (the interface has no switch of it)
BOARD_FLAG = 'SUTRA_BOARD_QUESTIONS'
#: the id of the step an engine's answer to another's question is (run_step's row names it; it is no step of any recipe)
ANSWER_STEP = 'coord.answer'
#: a new question whose 'about' shares this much of its content words with an answered one is that question again
DUPLICATE_SHARE = 0.6
STOPWORDS = frozenset(
    'a about already an and any are as at be been being but by can could did do does for from get give got had has have her his '
    'how i if in into is it its me my no not of on one or our out over should so some that the their them then there these they '
    'this those to too us was we were what when where which who whom why will with would you your yours'.split())


def board_on(ctx, step=None):
    """Whether this step may ask or be asked: the flag is set, the department is on the engine runtime and is not Root (Root has
    no line to ask along), and the step is not the answer to a question (an answer asks nothing back)."""
    d = (ctx or {}).get('dept') or {}
    if str(os.environ.get(BOARD_FLAG) or '').strip().lower() not in ('1', 'true', 'on', 'yes'):
        return False
    return d.get('runtime') == 2 and d.get('kind') != 'root' and (step or {}).get('id') != ANSWER_STEP


def _path(ref):
    return W.ddir(ref) / 'questions.json'


def entries(ref):
    """The department's questions, oldest first, as questions.json holds them ([] when the file is not there)."""
    raw = W._read(_path(ref), None)
    rows = raw.get('entries') if isinstance(raw, dict) else raw
    return [dict(e) for e in rows or [] if isinstance(e, dict)]


def _save(ref, rows):
    """questions.json whole, every entry checked as the interface types it first. Written from here only, and only with the flag on."""
    for e in rows:
        S.check_record('coordination', 'question', e, ref=ref)
    W._write(_path(ref), {'schema': 'board/1', 'entries': rows})
    return rows


def _clip(text, n):
    return ' '.join(str(text or '').split())[:n]


def _words(text):
    return [w for w in re.findall(r'[a-z0-9]+', str(text or '').lower()) if len(w) > 1 and w not in STOPWORDS]


def duplicate_of(about, rows):
    """The id of the answered entry whose 'about' this one is again (DUPLICATE_SHARE or more of its content words), else None."""
    words = _words(about)
    for e in rows:
        if e.get('status') == 'answered' and words:
            have = set(_words(e.get('about')))
            if sum(w in have for w in words) / float(len(words)) >= DUPLICATE_SHARE:
                return e.get('id')
    return None


def question_bounds(rows, line, filed, asker, slot, to, about):
    """The bounds of a question between engines (M4.9), a pure judgement over what questions.json and the line say: (ok, why, reuse).
    Refused, with the reason: no engine named, a second question by the engine in this slot, a target not earlier in the line than
    the asker, a target that has not filed, or an about already answered (`reuse` is that entry: its answer is the one to use)."""
    line = list(line or [])
    if not to:
        return False, 'it names no engine to ask', None
    if any(e.get('asked_by') == asker and e.get('slot') == slot for e in rows):
        return False, 'a second question by %s in this slot' % asker, None
    if to not in line or asker not in line or line.index(to) >= line.index(asker):
        return False, '%s is not earlier in the line than %s' % (to, asker), None
    if to not in set(filed or ()):
        return False, '%s has not filed anything yet' % to, None
    dup = duplicate_of(about, rows)
    if dup:
        return False, 'already answered in %s' % dup, dup
    return True, None, None


def _filed(ref, line):
    """The engines of the line that have filed a version of what they write."""
    return [n for n in line if (R.engine_def(n) or {}).get('writes') and W.versions(ref, R.engine_def(n)['writes'])]


def question_is_bounded(ctx, step, item, out):
    """Coordination's covering of a question it took (M4.9): the entry it filed is within the bounds, read again over the board
    as it stood before it. An entry let through that the bounds refuse fails, and so does one refused that the bounds let through; a refusal
    always gives its reason. Pure over questions.json and the line (the rule's answer names the department: `ref`)."""
    e = (out or {}).get('entry') if isinstance(out, dict) else None
    if not e:
        return {'ok': True, 'notes': [str((out or {}).get('said') or 'there was nothing to file')]}
    ref = (ctx or {}).get('ref') or out.get('ref')
    if not ref:
        return {'ok': False, 'notes': ['no department to read the board of']}
    rows = []
    for x in entries(ref):                      # what the board held when it took the question: the entries before it
        if x.get('id') == e.get('id'):
            break
        rows.append(x)
    line = R.coordination(ref).get('line') or []
    ok, why, _ = question_bounds(rows, line, _filed(ref, line), e.get('asked_by'), e.get('slot'), e.get('to'), e.get('about'))
    if e.get('status') == 'refused':
        if not str(e.get('reason') or '').strip():
            return {'ok': False, 'notes': ['a refused question gives its reason']}
        return {'ok': False, 'notes': ['a question within its bounds was refused: %s' % e['reason']]} if ok else \
            {'ok': True, 'notes': ['refused: %s' % e['reason']]}
    if not ok:
        return {'ok': False, 'notes': ['a question past its bounds was let through: %s' % why]}
    return {'ok': True, 'notes': ['within its bounds']}


def coord_question(ctx, step, item):
    """Coordination's handler for a question between engines (M4.9). Run in place (`item`: the entry as the asker put it, its
    thread and the run that asked): the bounds judge it and it is filed on the board, open when it is within them and refused,
    with the reason, when it is not. Heard from the board (the asker's post, `item` None, after the asker's run): the question
    was taken in place, and one still open is a question whose asker has moved on, noted as unanswered."""
    ref = ctx['ref']
    if item is None:
        pl = (ctx.get('post') or {}).get('payload')
        eid = ((pl if isinstance(pl, dict) else {}).get('entry') or {}).get('id')
        rows = entries(ref)
        mine = next((x for x in rows if x.get('id') == eid), None)
        if mine is None:
            return {'said': 'nothing to do: the board holds no such question', 'entry': None}
        if mine.get('status') == 'open':
            mine.update({'status': 'unanswered', 'reason': 'the asker had moved on'})
            _save(ref, rows)
        return {'said': 'nothing to do: %s is %s' % (mine['id'], mine['status']), 'entry': mine, 'ref': ref}
    e = dict(item['entry'])
    with W._lock(ref):
        rows = entries(ref)
        line = R.coordination(ref).get('line') or []
        ok, why, reuse = question_bounds(rows, line, _filed(ref, line), e['asked_by'], e['slot'], e['to'], e['about'])
        if any(x.get('id') == e['id'] for x in rows):
            e['id'] = 'Q-%d' % (len(rows) + 1)
        if ok:
            e['status'] = 'open'
        else:
            e.update({'status': 'refused', 'reason': _clip(why, 300)})
            for x in rows:
                if reuse and x['id'] == reuse and e['asked_by'] not in x.get('used_by', []):
                    x['used_by'] = list(x.get('used_by') or []) + [e['asked_by']]
        _save(ref, rows + [e])
    out = {'said': 'took %s: %s' % (e['id'], 'a question for %s' % e['to'] if ok else 'said no, %s' % e['reason']), 'entry': e, 'ref': ref}
    return dict(out, reuse=reuse) if reuse else out


CODE['coord_question'] = coord_question
CHECK['question_is_bounded'] = question_is_bounded


def view(ref, d, events, asks):
    """Coordination's pane (S.VIEWS['coordination'], screen S7): functions_view's read model of its own state, by reference
    (A1.11, A1.17). It reads the record and the table, never the events, and writes nothing."""
    return FV.coordination(ref, d, ak=asks)


def engine_card(ref, name):
    """One engine's card (S.VIEWS['engine_card'], screen S17): its place in the timetable, the motor's facts and one row for
    each of the five, by reference (A1.17). None for a department not on the engine runtime."""
    return FV.engine_card(ref, name)
