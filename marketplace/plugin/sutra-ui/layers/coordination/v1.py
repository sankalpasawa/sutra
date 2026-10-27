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

import owner_words
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
    """The words a subject is about: lower case, no stop word and no single letter, a plural said as its singular (pages, page)."""
    words = [w for w in re.findall(r'[a-z0-9]+', str(text or '').lower()) if len(w) > 1 and w not in STOPWORDS]
    return [w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w for w in words]


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


# ---- the target engine answers, in a run of its own ---------------------------------------------------------------------------
#: an answer that is none: the target says the question is not its own, or says nothing
NO_ANSWER = ('', 'not mine', 'n/a', 'none')


def _answer_prompt(ctx, step, item):
    """What an engine is asked when another engine puts it a question: the question, and its own recorded work to answer from."""
    e = ctx['post']['payload']['entry']
    own = ctx['def'].get('writes')
    cur = W.latest(ctx['ref'], own) if own else None
    files = W.read_files(ctx['ref'], own, cur['v']) if cur else {}
    work = json.dumps({'artifact': own, 'version': cur and cur['v'],
                       'files': {k: str(v)[:4000] for k, v in sorted(files.items())[:6]}}, ensure_ascii=False)
    return ('%s ASKS YOU ABOUT %s: %s\nYOUR RECORDED WORK: %s\nAnswer from the record only, in one or two short sentences: say "not recorded" '
            'for anything this department has not recorded, and "not mine" if this is not your area. You may not ask anything back. '
            'Return ONLY a JSON object: {"answer": "plain words; \\"not mine\\" if this is not your area"}.'
            % (e['asked_by'], e['about'], e['question'], work))


def _answer_draft(ctx, step, item):
    """Offline there is nobody to ask: the engine says the question is not its own, and the asker takes its normal path."""
    return {'answer': 'not mine'}


def _answer_check(ctx, step, item, out):
    ok = isinstance(out, dict) and isinstance(out.get('answer'), str)
    return {'ok': ok, 'notes': ['an answer, in words'] if ok else ['no answer in words']}


def _answer_step():
    """The one step of an engine's answer: its agent, run on the rungs like any step (the engine's own card is the agent's), with
    the bodies Coordination brings (run_step runs a step that carries its body)."""
    return {'id': ANSWER_STEP, 'name': 'Answer a question from another engine', 'nature': 'transform', 'born': 'C0',
            'prompt': _answer_prompt, 'draft': _answer_draft, 'out': {'answer': 'str'}, 'answer': 'answer', 'check': _answer_check}


def answer_run(ref, d, e, p2, asker_run):
    """The target engine's run that answers a question (M4.9): in its own slot (Target@board.n<post>), started only when the
    engine's own blockers let it, as any start (the owner's stamps, its envelope, the chain), and charged to its own envelope by the
    spend on its run row. It is the run of one step, its agent given its own recorded work. It starts while the asker's run is open,
    which gave it the turn: the row says which run it answers for (for_run). Returns (the answer, or None; why there is none; the run)."""
    target = e['to']
    tdef = R.engine_def(target)
    art = tdef['reads']
    cur = W.latest(ref, art)
    inp = {'post': p2, 'v': cur['v'] if cur else 0, 'art': art}
    slot = '%s@board.n%d' % (target, p2['n'])
    verdict, why = R.blocked(R._coord_ctx(ref, d), target, tdef, inp, slot)
    if verdict != 'admit':
        return None, 'a run of %s was not let start: %s' % (target, why), None
    row = W._put_run(ref, R._run_row(target, False, slot, 'running', 'answering %s about %s' % (e['asked_by'], e['about']),
                                     chain=W._chain_of(ref, art, inp['v']), answers=e['id'], for_run=asker_run))
    tctx = {'ref': ref, 'dept': d, 'engine': target, 'def': tdef, 'slot': slot, 'inp': inp, 'post': p2, 'run': row['id'], 'bag': {},
            'how': {}, 'spend': {'calls': 0, 'usd': 0.0}}
    R._thread_set(ref, p2['thread'], state='working')
    try:
        srow, out = R.run_step(tctx, _answer_step(), None)
    except Exception as exc:  # noqa: BLE001 -- an answer that breaks is a question unanswered, never a crash of the asker's run
        srow, out = {'status': 'failed', 'why': str(exc)}, None
    said = str((out or {}).get('answer') or '').strip() if srow['status'] == 'ok' and isinstance(out, dict) else ''
    answered = said.rstrip('. ').lower() not in NO_ANSWER
    why_not = None if answered else str(srow.get('why') or 'it says the question is not its own')
    R._thread_set(ref, p2['thread'], spent=tctx['spend']['usd'])
    row = W._put_run(ref, dict(row, status='ok' if answered else 'skipped', ended=W.now(),
                               spend={'calls': tctx['spend']['calls'], 'usd': round(tctx['spend']['usd'], 4)},
                               what=('answered %s about %s' % (e['asked_by'], e['about'])) if answered else
                               ('did not answer %s: %s' % (e['asked_by'], why_not))))
    return (said if answered else None), why_not, row


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
    if ok:
        e = _answered(ref, ctx, item, e)
    try:                      # the answer, or the reason there is none, goes back to the asker (Coordination to Engine, inform)
        R.post(ref, 'Coordination', [e['asked_by']], 'inform', {'word': 'answer', 'entry': e, 'what': _says(e)}, thread=item['thread'])
    except (ValueError, S.SchemaFault):
        pass                  # the board's record holds the answer whether or not the post that says it could be made
    out = {'said': 'took %s: %s' % (e['id'], _says(e)), 'entry': e, 'ref': ref}
    return dict(out, reuse=reuse) if reuse else out


def _says(e):
    """What became of a question, as the board's rows say it."""
    if e['status'] == 'answered':
        return '%s answers %s' % (e['to'], e['asked_by'])
    if e['status'] == 'refused':
        return 'said no to %s: %s' % (e['asked_by'], e.get('reason'))
    return 'no answer for %s: %s' % (e['asked_by'], e.get('reason'))


def _answered(ref, ctx, item, e):
    """An open question goes to the engine it names (Coordination to Engine, request), whose run answers it; the entry is filed
    answered, with the run and where the answer came from, or unanswered, with the reason. Returns the entry as filed."""
    d = ctx.get('dept') or W.dept(ref) or {}
    try:
        p2 = R.post(ref, 'Coordination', [e['to']], 'request', {'word': 'question', 'entry': e, 'what': _said(e)}, thread=item['thread'])
    except (ValueError, S.SchemaFault) as exc:
        p2, no = None, 'the board would not carry it: %s' % exc
    else:
        no = 'the board would not carry it'
    answer, why_not, row = answer_run(ref, d, e, p2, item.get('run')) if p2 else (None, no, None)
    with W._lock(ref):
        rows = entries(ref)
        mine = next(x for x in rows if x['id'] == e['id'])
        if answer:
            version = (W.latest(ref, R.engine_def(e['to'])['writes']) or {}).get('v')
            mine.update({'status': 'answered', 'answer': _clip(answer, 2000), 'answered_by': e['to'], 'run': row['id'],
                         'answered_from': {'workflow': e['to'], 'version': version}})
        else:
            mine.update({'status': 'unanswered', 'reason': _clip(why_not, 300), 'run': row['id'] if row else None})
        _save(ref, rows)
    return mine


# ---- the asker's side: the board in the step's prompt, and what its answer says --------------------------------------------------
BOARD_FORMAT = (
    'THE BOARD: if this step cannot be done without a fact that an earlier engine of the line holds, you may add one field to your '
    'JSON object: "question": {"to": the name of that engine, "about": a few words, "text": your question}. Ask at most one question, '
    'only of an engine named below, and never one the BOARD already answers. If you used an answer from the BOARD, add '
    '"board_used": [its ids, such as "Q-1"]. Otherwise leave both out and do the step as asked.')


def board_text(ctx, step):
    """What a work step is given of the board: the questions already answered (every engine reads them before it asks), and, while
    an earlier engine of the line has filed, the format of a question and the engines it may be put to."""
    ref, mine = ctx['ref'], ctx.get('engine')
    answered = [{'id': e['id'], 'to': e.get('to'), 'about': e.get('about'), 'answer': e.get('answer')}
                for e in entries(ref) if e.get('status') == 'answered']
    line = R.coordination(ref).get('line') or []
    askable = [n for n in _filed(ref, line) if mine in line and line.index(n) < line.index(mine)]
    out = ''
    if answered:
        out += '\n\nBOARD (answered questions; check here before asking): ' + json.dumps(answered, ensure_ascii=False)
    if askable:
        out += '\n\n' + BOARD_FORMAT + ' ENGINES YOU MAY ASK: ' + ', '.join(askable) + '.'
    return out


def board_step(ctx, step):
    """The step with the board in its prompt (run_step's hook): the step's own builder, and the board's text after it. The prompt
    reads questions.json each time it is built, so the run of the step that follows an answer holds the answer."""
    base = step['prompt']

    def prompt(c, s, item):
        return R._resolve(c, 'prompt', base)(c, s, item) + board_text(c, s)
    return dict(step, prompt=prompt)


def _credit(ref, who, used):
    """The answered entries a step names (board_used) are used by it: used_by gains the engine, once. Returns the ids credited."""
    ids = [str(i) for i in used if isinstance(i, (str, int))] if isinstance(used, list) else []
    with W._lock(ref):
        rows, read = entries(ref), []
        for e in rows:
            if e.get('id') in ids and e.get('status') == 'answered':
                read.append(e['id'])
                if who and who not in e.get('used_by', []):
                    e['used_by'] = list(e.get('used_by') or []) + [who]
        if read:
            _save(ref, rows)
    return read


def _depends(ref):
    """What the prompt held of the board, as the step's row records what it read: each answered entry, with the artifact and the
    version of the engine that answered it (the step depends on them)."""
    out = []
    for e in entries(ref):
        if e.get('status') == 'answered':
            row = {'board': e['id']}
            art = (R.engine_def(e.get('to')) or {}).get('writes')
            version = (e.get('answered_from') or {}).get('version')
            if art and version:
                row.update({'art': art, 'v': version})
            out.append(row)
    return out


def _asked(ctx, step, item, raw, attempt):
    """ask(), without ever failing the asker's step: a board that breaks leaves the question unasked and the step on its normal path."""
    try:
        return ask(ctx, step, item, raw, attempt)
    except Exception:  # noqa: BLE001 -- the board never fails the step that asked
        return None


def board_turn(ctx, step, item, out, again):
    """run_step's hook after a work step's answer (M4.9): the board's two fields are taken out of the answer (a question, and the ids
    it used), the ids are credited, and a question goes to Coordination. When it was answered (or the board answered it already) the
    step is run once more, `again()`, with the board in its prompt; an answer that does not come, or a run that does not fit, leaves
    the asker's own answer, which takes its normal path. Returns (the answer, {usd, calls, read})."""
    ref, who = ctx['ref'], ctx.get('engine')
    out = dict(out)
    asked, used = out.pop('question', None), out.pop('board_used', None)
    more = {'usd': 0.0, 'calls': 0, 'read': []}
    if isinstance(asked, dict) and str(asked.get('to') or '').strip():
        e = _asked(ctx, step, item, asked, 1)
        if e and (e.get('status') == 'answered' or e.get('reuse')):
            got, cost, how, n = again()
            more['usd'] += float(cost or 0)
            more['calls'] += int(n or 0)
            if isinstance(got, dict) and how in ('model', 'checklist'):
                out = dict(got)
                again_asked, again_used = out.pop('question', None), out.pop('board_used', None)
                used = again_used if again_used is not None else used
                if isinstance(again_asked, dict) and str(again_asked.get('to') or '').strip():
                    _asked(ctx, step, item, again_asked, 2)      # a second question in the slot: the board says no, with its reason
            if e.get('reuse'):
                used = list(used if isinstance(used, list) else []) + [e['reuse']]
    _credit(ref, who, used)
    more['read'] = _depends(ref)
    return out, more


def _cycle(ref):
    try:
        return J.status(ref).get('cycle_id')
    except Exception:  # noqa: BLE001 -- a question with no cycle to name is still a question
        return None


def _draft(ref, ctx, raw, attempt):
    """The question as the asker put it, as a board/1 entry, still open: the next id on the board, who asked it and in which slot."""
    to = re.sub(r"[^A-Za-z0-9 &'.-]", '', str(raw.get('to') or '')).strip()[:40]
    return {'schema': 'board/1', 'id': 'Q-%d' % (len(entries(ref)) + 1), 'asked_by': ctx['engine'], 'to': to or 'nobody',
            'about': _clip(raw.get('about'), 120) or 'this step', 'question': _clip(raw.get('text'), 600) or _clip(raw.get('about'), 600),
            'answer': None, 'answered_by': None, 'status': 'open', 'reason': None, 'artifact_update': None, 'used_by': [],
            'cycle': _cycle(ref), 'slot': str(ctx.get('slot') or '')[:160], 'attempt': int(attempt), 'run': None}


def _said(e):
    """A question as the board's rows say it: 'Write asks Plan about the page list'."""
    return '%s asks %s about %s' % (e['asked_by'], e['to'], e['about'])


def ask(ctx, step, item, raw, attempt):
    """An engine's question reaches Coordination (M4.9): the asker posts it (Engine to Coordination, request) and Coordination takes
    it in its handler, in place; the entry it filed comes back, whatever became of it, with `reuse` set (on the copy returned, never
    on the board) when the board answered the question already. A board that would not carry the post leaves the entry
    refused, with the reason."""
    ref = ctx['ref']
    draft = _draft(ref, ctx, raw if isinstance(raw, dict) else {}, attempt)
    try:
        p1 = R.post(ref, ctx['engine'], ['Coordination'], 'request', {'word': 'question', 'entry': draft, 'what': _said(draft)},
                    about={'art': (ctx.get('def') or {}).get('reads'), 'v': (ctx.get('inp') or {}).get('v')})
        if p1 is None:
            raise ValueError('the thread was closed')
    except (ValueError, S.SchemaFault) as exc:
        with W._lock(ref):
            rows = entries(ref)
            draft.update({'id': 'Q-%d' % (len(rows) + 1), 'status': 'refused', 'reason': _clip('the board would not carry it: %s' % exc, 300)})
            _save(ref, rows + [draft])
        return draft
    got = R._ask_rule(ref, 'coord.question', {'entry': draft, 'thread': p1['thread'], 'run': ctx.get('run')},
                      key='question@%s@%s' % (ctx.get('slot'), draft['id']))
    return dict(got['entry'], reuse=got['reuse']) if got.get('reuse') else got['entry']


CODE['coord_question'] = coord_question
CHECK['question_is_bounded'] = question_is_bounded


def view(ref, d, events, asks):
    """Coordination's pane (S.VIEWS['coordination'], screen S7): functions_view's read model of its own state, by reference
    (A1.11, A1.17). It reads the record and the table, never the events, and writes nothing."""
    return FV.coordination(ref, d, ak=asks)


#: what became of a question, in the owner's words, after "asked <engine> about <about>" (screens S13 and S17)
QUESTION_ENDS = {'answered': 'answered', 'unanswered': 'no answer', 'refused': 'said no', 'open': 'waiting'}


def engine_card(ref, name):
    """One engine's card (S.VIEWS['engine_card'], screen S17): its place in the timetable, the motor's facts and one row for
    each of the five, by reference (A1.17). None for a department not on the engine runtime. Coordination's row also says the
    question this engine asked last, 'asked Plan about the page list (answered)', and the last it answered for another engine,
    from the board (M4.9); an engine that put and was put no question has its row as it was."""
    card = FV.engine_card(ref, name)
    rows = entries(ref) if card else []
    asked = next((e for e in reversed(rows) if e.get('asked_by') == name), None)
    answered = next((e for e in reversed(rows) if e.get('to') == name and e.get('status') == 'answered'), None)
    if not asked and not answered:
        return card
    keep = set(R.defs()['engines']) | set((W.dept(ref) or {}).get('engines') or [])       # an engine called Grant is not said yes to
    plain = lambda text: owner_words.said_plainly(text, keep=keep)                       # noqa: E731 -- about is a model's words
    said = ([plain('asked %s about %s (%s)' % (asked['to'], asked['about'], QUESTION_ENDS.get(asked['status'], asked['status'])))] if asked else []) + \
        ([plain('answered %s about %s' % (answered['asked_by'], answered['about']))] if answered else [])
    for row in card['five']:
        if row['fn'] == 'Coordination':
            row['says'] = _clip('; '.join([row['says']] + said), 300)
    return card
