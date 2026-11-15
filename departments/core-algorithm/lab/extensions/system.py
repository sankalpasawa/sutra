"""The page builder, OUTSIDE the kernel: from a goal in a person's words to a small department folder with a page a
person can open. (The command is extensions/g2.py; the catalogue is the pack 171_domain_catalogue.)

It takes the words, picks one reviewed domain from the catalogue (a closed list; choosing is a judgement an agent or a
person makes, and the word matcher here is only a stand-in that says so on the page and refuses to choose on a tie),
asks the kernel for the plan, turns the plan into the workflow the runtime would run (extensions/implementation.py),
runs the plan in the local model along the path where every question is answered yes, to its end, and at each question
also along the no (extensions/asks.py), compares the steps that ran with the steps of the plan it shows, asks the kernel
once more whether the goal is then held, has the kernel judge the generated workflow against the reviewed standard
(extensions/standards.py), and writes one page that shows all of it.

The verdict is one of five:
  READY      the kernel has a plan, the generated workflow is well formed and meets the standard, the run in the local
             model went through without a question, the steps that ran are the steps of that plan, every step that ran
             left its effect true, and the kernel's next look finds the goal held.
  WAITING    the same, on the path where every question is answered yes; the run parks on a question first.
  NOT_READY  the kernel has a plan and one of those conditions fails. `blocked_at` says which and where: the step the
             kernel recorded as stopped (its own reason), another route than the plan shown, an effect that does not
             hold, a goal that is not held, the kernel's own stop reasons for a look that found no plan after an answer.
  BLOCKED    the kernel has no plan. `blocked_at` holds the rows of its own trace.
             Where the rows are those of a look that found no plan (the first look, or the run after an answer), the
             first sentence names the reason the kernel itself names that look with (its status), not the first row.
  NO_DOMAIN  no reviewed domain was chosen. Nothing is guessed: the page carries the draft a person or an agent has
             to fill in and the kernel's own answer to that draft.

Everything is PROPOSED_ONLY and deterministic: the same words, catalogue, packs and domain give the same bytes. The
action kinds a built system may use are named here, not read from the process, and every function the State will call
for them (the handler and each hook) is recorded in the system by the name of its code, its source file and that file's
digest; every pack a system was built from is recorded by its digest (`pack_digests`). The system says of a look or run
only what its hash chain carries (status, steps, cost, receipts, the stop): what the kernel returns beside its trace
(needs, proof lines, the branch) stays in record.json and is on no page. The folder is named after the manifest's
digest, and the manifest lists the digest of every other file: two builds that differ in one byte are two folders. Text is classed by code point from fixed lists, so no Unicode table of the interpreter is read for the words
(names that come from packs pass through the generator's own slug, which does read it: shipped packs are ASCII).
This module writes no file and calls no runtime; extensions/g2.py writes the files it returns.

A kernel result is never caught as an exception here: a step that cannot run is the kernel's recorded STEP_STOPPED."""
from __future__ import annotations
import copy, hashlib, html, json
from pathlib import Path
from kernel.core import State, Kernel, ACTIONS, digest
from extensions.implementation import to_implementation, validate_workflow
from extensions.standards import workflow_facts
from extensions.asks import answer, open_asks   # importing registers the ask kind
import extensions.constructor                   # registers the constructor kinds, so every catalogue domain loads

LAB = Path(__file__).resolve().parents[1]
SCHEMA = 'core-algorithm/system/4'
RECORD_SCHEMA = 'core-algorithm/system-record/1'
MANIFEST_SCHEMA = 'core-algorithm/system-manifest/1'
KINDS = ('ask', 'compile_candidate', 'emit_artifact', 'simulate_fact')
STANDARD = ('60_standard_goal', '61_standard_theory')
QUESTIONS_SHOWN = 4
BUILT_FILES = ['index.html', 'system.json', 'workflow.json', 'atoms.json', 'scaffold.json', 'record.json', 'manifest.json']
DRAFT_FILES = ['index.html', 'system.json', 'draft-pack.json', 'record.json', 'manifest.json']
PLAIN = {
 'PLAN_READY': 'a plan is ready', 'LOCAL_MODEL_EFFECTS_RECORDED': 'the plan ran through in the local model',
 'SUPPORTED_BY_EVIDENCE': 'the facts already support it', 'WAITING': 'a question is out and the run waits for the answer',
 'STEP_STOPPED': 'a step could not run in the local model, and the run stopped there',
 'REFUSED': 'a decision stands against it, and no method may overturn that', 'SEMANTICS_MISSING': 'nobody has written down what this goal means',
 'SEMANTICS_UNAPPROVED': 'what this goal means is drafted but not reviewed', 'EVIDENCE_CONFLICT': 'the facts contradict each other',
 'QUERY_EVIDENCE': 'a needed fact is unknown and nothing may ask for it', 'AUTHORITY_REQUIRED': 'a step has no permission to run',
 'PROVIDER_REQUIRED': 'nobody is free to do a step', 'RESOURCE_REQUIRED': 'the budget does not cover the plan',
 'METHOD_ABSENT': 'no reviewed way exists to make a needed condition true',
 'CYCLE_LIMIT': 'the conditions depend on each other in a circle',
 'CHAIN_TOO_DEEP': 'the chain of conditions is deeper than the kernel follows',
 'WORKFLOW_PROBLEM': 'the workflow generated from the plan is not well formed',
 'STANDARD_NOT_MET': 'the workflow generated from the plan lacks a part the standard asks for',
 'ROUTE_CHANGED': 'the steps that ran in the local model are not the steps of the plan on this page',
 'EFFECT_NOT_MADE': 'a step ran in the local model and what it should make true does not hold afterwards',
 'GOAL_NOT_HELD': 'every step ran in the local model, and afterwards the goal still does not hold',
 'STILL_WAITING': 'the run in the local model still waits after every question was answered'}
UNBLOCK = {
 'METHOD_ABSENT': 'a reviewed method that makes this condition true', 'QUERY_EVIDENCE': 'a verified fact for this condition, or a reviewed method that may ask for it',
 'AUTHORITY_REQUIRED': 'the grant for the step', 'PROVIDER_REQUIRED': 'a provider with a free slot', 'RESOURCE_REQUIRED': 'a larger budget or a cheaper method',
 'SEMANTICS_MISSING': 'a reviewed rule that says what the goal means', 'SEMANTICS_UNAPPROVED': 'a reviewer approving the drafted rule',
 'EVIDENCE_CONFLICT': 'someone settling which fact is right: the stored row, or the conditions that say otherwise',
 'CYCLE_LIMIT': 'rules and methods that do not depend on each other in a circle', 'CHAIN_TOO_DEEP': 'a shorter chain of conditions',
 'REFUSED': 'nothing here: the decision is final; another route to the goal would have to exist',
 'WORKFLOW_PROBLEM': 'a generator that writes this plan as a well-formed workflow',
 'STANDARD_NOT_MET': 'a workflow that carries the missing part',
 'STEP_STOPPED': 'what the stopped step needs; the reason is in the kernel\'s own words',
 'ROUTE_CHANGED': 'a domain in which one plan stays the cheapest before and after the answers, so that the page shows the steps that run',
 'EFFECT_NOT_MADE': 'a method whose step stores its effect as evidence',
 'GOAL_NOT_HELD': 'a newer observation of the goal, or rules and facts that agree with each other',
 'STILL_WAITING': 'a review of the domain: the model run found no question left to answer'}
TO_WRITE = [
 'What done means: the conditions that must be true, as one or more alternatives.',
 'What is true today: each condition as TRUE or FALSE, or left out when nobody knows. Not the goal itself: the kernel reads the goal from its conditions.',
 'The ways to make each condition true: one method per condition, with what it needs first. No method may make the goal itself.',
 'Who may run each method: a grant and a provider per method. Anything that needs a person is an ask, with the person named.',
 'What it costs: attention, money and compute per method, and the budget they must fit.',
 'A reviewer approves the rules. Until then the kernel plans nothing from them.']


# ---------------------------------------------------------------- text, by code point (no Unicode table of the interpreter is read)
_SPACES = frozenset([0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000] + list(range(0x2000, 0x200b)))
_UNSEEN = frozenset([0xad, 0x34f, 0x61c, 0x115f, 0x1160, 0x17b4, 0x17b5, 0x180e, 0x200b, 0x200e, 0x200f, 0x2800, 0x3164, 0xfeff, 0xffa0])


def _hidden(c: int) -> bool:
    """A character that shows nothing or re-orders what is shown: controls, surrogates, direction and format marks."""
    return (c < 0x20 or 0x7f <= c <= 0x9f or c in _UNSEEN or 0x202a <= c <= 0x202e or 0x2060 <= c <= 0x206f or 0xd800 <= c <= 0xdfff
            or 0xfff9 <= c <= 0xfffb or 0x1d173 <= c <= 0x1d17a or 0xe0000 <= c <= 0xe007f)


def _modifier(c: int) -> bool:
    """A character that only changes how its neighbour is drawn: the joiners and the variation selectors."""
    return c in (0x200c, 0x200d) or 0x180b <= c <= 0x180f or 0xfe00 <= c <= 0xfe0f or 0xe0100 <= c <= 0xe01ef


def _mark(c: int) -> bool:
    """A character that separates words without being a letter: ASCII and the common punctuation blocks."""
    return (c < 0x80 and not chr(c).isalnum()) or 0xa1 <= c <= 0xbf or c in (0xd7, 0xf7) or 0x2000 <= c <= 0x206f or 0x3000 <= c <= 0x303f or 0xff00 <= c <= 0xff0f


def _visible(text) -> str:
    """Text as a page may show it: hidden characters dropped; line breaks and tabs stay."""
    return ''.join(ch for ch in str(text) if ch in '\n\t' or not _hidden(ord(ch)))


def _clean(words: str) -> str:
    """The words as they are shown and matched: hidden characters dropped, every run of white space one space."""
    text = ''.join(' ' if ord(ch) in _SPACES else ch for ch in words if ord(ch) in _SPACES or not _hidden(ord(ch)))
    return ' '.join(part for part in text.split(' ') if part)


def _low(text: str) -> str:
    return ''.join(ch.lower() if ch.isascii() else ch for ch in text)


def _tokens(text) -> set:
    """The words of three or more characters, ASCII letters lowered."""
    out = ''.join(' ' if ord(ch) in _SPACES or _hidden(ord(ch)) or _mark(ord(ch)) else ch for ch in _low(str(text)))
    return {t for t in out.split(' ') if len(t) > 2}


def _ascii_slug(text: str, n: int = 40) -> str:
    """A file-safe name from the ASCII letters and digits of a text."""
    out = ''.join(ch.lower() if ch.isascii() and ch.isalnum() else '-' for ch in text)
    while '--' in out:
        out = out.replace('--', '-')
    return out.strip('-')[:n].strip('-') or 'goal'


def _says_something(text: str) -> bool:
    """At least one letter or digit: an ASCII one, or any character above ASCII that is not hidden, not a mark and not a modifier."""
    return any((ch.isascii() and ch.isalnum()) or (ord(ch) > 0xa0 and not _mark(ord(ch)) and not _hidden(ord(ch)) and not _modifier(ord(ch))) for ch in text)


def _text(v) -> bool:
    """A string a catalogue row may carry: text that can be written as UTF-8 and is not blank."""
    try:
        return type(v) is str and bool(_clean(v)) and bool(v.encode('utf-8'))
    except UnicodeError:
        return False


def _sha(text: str) -> str:
    """The SHA-256 of the bytes a file is written with."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _json(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + '\n'


# ---------------------------------------------------------------- the catalogue and the choice
def catalogue_rows(catalogue) -> dict:
    """The catalogue by id, refused (ValueError) unless every row is whole and no id repeats."""
    if type(catalogue) is not list:
        raise ValueError('The catalogue is a list of domains')
    by = {}
    for d in catalogue:
        whole = (type(d) is dict and all(_text(d.get(k)) for k in ('id', 'title', 'goal', 'say'))
                 and all(type(d.get(k)) is list and d[k] and all(_text(x) for x in d[k]) for k in ('words', 'packs'))
                 and type(d.get('labels', {})) is dict and all(_text(k) and _text(v) for k, v in d.get('labels', {}).items()))
        if not whole:
            raise ValueError('A catalogue row needs an id, a title, a goal, an example of what a person would say, words and packs (and labels in plain text)')
        if d['id'] in by:
            raise ValueError('Two catalogue rows share the id ' + d['id'])
        by[d['id']] = d
    return by


def match(words: str, catalogue: list) -> list:
    """A stand-in for the judgement of choosing a domain: the words the ask shares with each domain's reviewed vocabulary."""
    asked = _tokens(words)
    ranked = sorted(((sorted(asked & {_low(w) for w in d['words']}), d['id']) for d in catalogue), key=lambda x: (-len(x[0]), x[1]))
    return [{'domain': i, 'shared_words': len(shared), 'words': shared} for shared, i in ranked]


def _choose(words: str, catalogue: list, domain) -> dict:
    ranked = match(words, catalogue)
    top = ranked[0]['shared_words'] if ranked else 0
    tied = [r['domain'] for r in ranked if r['shared_words'] == top] if top else []
    if domain is not None:
        return {'domain': domain, 'how': 'the caller', 'ranking': ranked, 'tied': []}
    if len(tied) == 1:
        return {'domain': tied[0], 'how': 'a word match on ' + ', '.join(ranked[0]['words']) + ' (a stand-in: a person or an agent should confirm the choice)',
                'ranking': ranked, 'tied': []}
    how = f'nobody: {len(tied)} reviewed domains share the same number of words with the ask' if tied else 'nobody: no reviewed domain shares a word with the ask'
    return {'domain': None, 'how': how, 'ranking': ranked, 'tied': tied}


# ---------------------------------------------------------------- the kernel's looks and runs
def _state(packs: list, kinds: dict) -> State:
    """A State that knows the named action kinds, as this build found them, and nothing else the process may have registered."""
    state = State(actions={k: dict(v) for k, v in kinds.items()})
    for pack in packs:
        state.apply(pack)
    return state


def _code(fn) -> dict:
    """One function the State will call: the name of its code, the file that code was compiled from (inside the lab: its path
    there) and that file's digest. The code of a wrapper is the wrapper's own, whatever name it was given."""
    code = getattr(fn, '__code__', None) or getattr(getattr(type(fn), '__call__', None), '__code__', None)
    if code is None:
        return {'function': type(fn).__name__, 'file': None, 'sha256': None}
    path = Path(code.co_filename)
    try:
        data = path.read_bytes()
    except (OSError, ValueError):
        return {'function': code.co_name, 'file': path.name, 'sha256': None}
    try:
        name = path.resolve().relative_to(LAB).as_posix()
    except ValueError:
        name = path.name
    return {'function': code.co_name, 'file': name, 'sha256': hashlib.sha256(data).hexdigest()}


def _handlers(kinds: dict) -> dict:
    """The code behind each named kind (its handler and each of its hooks): an input of every build, on the record."""
    return {kind: {hook: _code(fn) for hook, fn in sorted(kinds[kind].items()) if callable(fn)} for kind in KINDS}


def _twin(state: State) -> State:
    """A second State with the same books (the registry is shared, as in State.apply)."""
    return copy.deepcopy(state, {id(state.actions): state.actions})


def _brief(r: dict) -> dict:
    """The part of a kernel result the page reads. The whole result, with its hash chain, is in record.json."""
    return {'status': r['status'], 'work_state': r['work_state'], 'actions': list(r['actions']), 'pending': list(r.get('pending', [])),
            'skipped': list(r.get('skipped', [])), 'cost': r.get('cost'), 'stop_reasons': list(r.get('stop_reasons', [])), 'stopped': r.get('stopped'),
            'trace_root_sha256': r['trace_root_sha256'],
            'receipts': [{'method': x['method'], 'action': x['action'], 'status': x['status'], 'sha256': x['sha256'], 'ask': x.get('ask')} for x in r['model_receipts']]}


def _held(look) -> bool:
    """The kernel's dry look finds the goal held: a plan with nothing to do and nothing to wait for."""
    return bool(look) and look['status'] == 'PLAN_READY' and not look['actions']


def _look_after(state: State, goal: str, run: dict):
    """The kernel's next look at the goal, dry, on a twin of the State, when the run completed (else None)."""
    return Kernel(_twin(state)).resolve(goal) if run['work_state'] == 'completed' else None


def _answered(kernel: Kernel, issued: dict, truth: str) -> dict:
    """Give the asked party's answer to the question on the books and return the run that follows."""
    out = answer(kernel, issued, truth, issued['ask']['to'], execute=True)
    return out['runs'][0] if out['runs'] else kernel.run_standing(execute=True)['runs'][0]


def _children(state: State, pred: str) -> list:
    rule = state.rules.get(pred)
    if rule:
        return [c for branch in rule['branches'] for c in branch]
    return [r for m in state.methods.values() if m['effect'] == pred and m.get('approved', True) for r in m.get('requires', [])]


def _in_circle(state: State, pred: str) -> bool:
    """Whether a condition can reach itself through the reviewed rules and methods."""
    seen, todo = set(), _children(state, pred)
    while todo:
        p = todo.pop()
        if p == pred:
            return True
        if p not in seen:
            seen.add(p)
            todo += _children(state, p)
    return False


def _blocked_at(result: dict, state: State) -> list:
    """Where a look of the kernel found no plan, read off its own trace: each stop reason with the conditions, or the steps, it belongs to."""
    out = []
    for e in result.get('trace', []):
        d, rows = e['data'], []
        if e['operation'] in result.get('stop_reasons', []) and type(d.get('predicate')) is str:   # also a condition whose name is the empty string
            reason = e['operation']
            if reason == 'CYCLE_LIMIT' and not _in_circle(state, d['predicate']):   # the kernel logs one word for a circle and for its depth limit
                reason = 'CHAIN_TOO_DEEP'
            rows = [{'reason': reason, 'at': [d['predicate']], 'detail': f'{Kernel(state).limit} levels' if reason == 'CHAIN_TOO_DEEP' else None}]
        elif e['operation'] == 'ADMISSION' and not d.get('accepted', True):
            methods = [state.methods[m] for m in d.get('methods', [])]
            use = {}
            for m in methods:
                use[m['provider']] = use.get(m['provider'], 0) + 1
            short = {p for p, n in use.items() if state.providers.get(p, 0) < n}
            over = [f'{dim}: needs {v}, has {state.budget.get(dim, 0)}' for dim, v in d.get('cost', {}).items() if v > state.budget.get(dim, 0)]
            for b in d.get('blockers', []):
                which = [m['id'] for m in methods if (b == 'AUTHORITY_REQUIRED' and m['grant'] not in state.grants) or (b == 'PROVIDER_REQUIRED' and m['provider'] in short)
                         or b not in ('AUTHORITY_REQUIRED', 'PROVIDER_REQUIRED')]
                rows.append({'reason': b, 'at': which, 'detail': '; '.join(over) if b == 'RESOURCE_REQUIRED' and over else None})
        out += [r for r in rows if r not in out]
    return out


def _model_run(packs: list, goal: str, planned: list, kinds: dict) -> tuple:
    """The plan in the local model, on a fresh State: the path where every question is answered yes, followed to its end,
    and at each question what a no leads to (on a twin of the State). `planned` is the plan the page shows (the steps of
    the kernel's first look). Returns what the page reads (briefs), the kernel's whole results (for record.json) and the
    rows that say why the path did not get there (empty when it did)."""
    state = _state(packs, kinds)
    k = Kernel(state)
    runs, asks, no_runs, no_after = [k.run_standing(execute=True)['runs'][0]], [], [], []
    limit = sum(1 for m in state.methods.values() if m['action'] == 'ask') + 1   # one question per fact and scope: a path cannot ask more often
    while len(asks) < limit:
        out = open_asks(state)
        if not out:
            break
        issued = out[sorted(out)[0]]['issued']
        other = _twin(state)
        no = _answered(Kernel(other), issued, 'FALSE')
        look = _look_after(other, goal, no)
        no_runs.append(no)
        no_after.append(look)
        yes = _answered(k, issued, 'TRUE')
        runs.append(yes)
        asks.append({'fact': issued['ask']['predicate'], 'question': issued['ask']['question'], 'to': issued['ask']['to'], 'asked_by': issued['method'],
                     'receipt_sha256': issued['sha256'], 'if_yes': _brief(yes), 'if_no': dict(_brief(no), goal_held=_held(look) if look else None)})
    last, rows, missing = runs[-1], [], []
    after = _look_after(state, goal, last)
    done = last['work_state'] == 'completed'
    ran = [x['method'] for r in runs for x in r['model_receipts']]
    skipped = [m for r in runs for m in r.get('skipped', [])]
    chosen = list(dict.fromkeys(m for r in runs for m in list(r['actions']) + list(r.get('pending', [])) + list(r.get('skipped', []))))   # every step a run selected: ran, skipped, stopped or still to run
    outside = [m for m in chosen if m not in planned]                                       # chosen by a later look, and no step of the plan the page shows
    unrun = [m for m in planned if m not in ran and m not in skipped] if done else []       # a step of that plan that never ran on a path that completed
    if outside or unrun:   # the kernel plans again after every answer: when its new plan is another one, the page would show steps that did not run
        rows.append({'reason': 'ROUTE_CHANGED', 'at': outside + unrun,
                     'detail': f'chosen outside the plan: {", ".join(outside) or "nothing"}; planned and not run: {", ".join(unrun) or "nothing"}'})
    if last['status'] == 'STEP_STOPPED':   # the kernel's own record of a step that could not run
        rows.append({'reason': 'STEP_STOPPED', 'at': [last['stopped']['method']], 'detail': last['stopped']['reason']})
    elif last['work_state'] == 'blocked':   # after an answer the kernel found no plan: its own trace says why
        rows += _blocked_at(last, state) or [{'reason': last['status'], 'at': [], 'detail': None}]   # a look whose trace names no condition is still a look without a plan: never ready, never waiting
    elif not done:
        rows.append({'reason': 'STILL_WAITING', 'at': list(last.get('waits', [])), 'detail': None})
    else:
        for r in runs:
            for x in r['model_receipts']:
                if not x.get('parked') and x['method'] not in missing and state.fact(state.methods[x['method']]['effect'])['truth'] != 'TRUE':
                    missing.append(x['method'])
        rows += [{'reason': 'EFFECT_NOT_MADE', 'at': [m], 'detail': None} for m in missing]
        if not _held(after):
            rows.append({'reason': 'GOAL_NOT_HELD', 'at': [goal], 'detail': after['status']})
    page = {'path': [_brief(r) for r in runs], 'asks': asks, 'after': _brief(after) if after else None, 'goal_held': _held(after) if after else None,
            'effects_missing': missing}
    return page, {'runs': runs, 'no_runs': no_runs, 'no_after': no_after, 'after': after}, rows


def _standard(workflow: dict, packs: list, kinds: dict) -> tuple:
    """The kernel judges the generated workflow against the reviewed standard: the standard is a rule in its two packs, and the
    checklist is evidence, observed by the State row by row (as a handler's rows are) before the kernel looks once."""
    rows = workflow_facts(workflow)
    s = _state(packs, kinds)
    if len(s.goals) != 1:
        raise ValueError('The standard packs must leave exactly one standing goal')
    for row in rows:
        s.observe(row)
    r = Kernel(s).run_standing(execute=True)['runs'][0]
    return ({'goal': r['goal'], 'rule': s.rules.get(r['goal'], {}).get('id'), 'status': r['status'], 'registrable': r['status'] == 'SUPPORTED_BY_EVIDENCE',
             'workflow': workflow.get('id'), 'evidence': rows, 'checks': [{'check': x['predicate'], 'question': x['question'], 'truth': x['truth']} for x in rows],
             'trace_root_sha256': r['trace_root_sha256']}, r)


def _draft(words: str, kinds: dict) -> tuple:
    """No domain was chosen: the template a person or an agent fills in, and the kernel's own answer to an unreviewed draft."""
    slug = _ascii_slug(words)
    goal = slug.replace('-', '_')
    pack = {'schema': 'sutra-extension/2', 'id': 'draft-' + slug, 'scope': 'draft/unreviewed', 'goals': [goal],
            'rules': [{'id': 'R-DRAFT@1', 'head': goal, 'branches': [['first_condition_to_name']], 'approved': False,
                       'source': 'draft/unreviewed: a template from the page builder, not knowledge'}]}
    r = Kernel(_state([pack], kinds)).run_standing(execute=False)['runs'][0]
    return ({'verdict': 'NO_DOMAIN', 'labels': {}, 'file_names': list(DRAFT_FILES),
             'draft': {'pack': pack, 'kernel_status': r['status'], 'trace_root_sha256': r['trace_root_sha256'], 'to_write': list(TO_WRITE)}},
            {'schema': RECORD_SCHEMA, 'draft': r})


def _built(entry: dict, packs: list, standard_packs: list, kinds: dict) -> tuple:
    """One domain, built: the kernel's plan, the generated workflow, the run in the local model, the standard, the verdict."""
    state = _state(packs, kinds)
    if state.goals != [entry['goal']]:
        raise ValueError(f'The domain {entry["id"]} must leave exactly one standing goal, {entry["goal"]}')
    plan = Kernel(state).run_standing(execute=False)['runs'][0]
    impl = to_implementation(plan, state)
    problems = validate_workflow(impl['workflow'])
    run = {'path': [], 'asks': [], 'after': None, 'goal_held': None, 'effects_missing': []}
    whole = {'runs': [], 'no_runs': [], 'no_after': [], 'after': None}
    standard = {'goal': None, 'rule': None, 'status': 'NOT_APPLICABLE', 'registrable': None, 'workflow': impl['workflow']['id'], 'evidence': [], 'checks': [],
                'trace_root_sha256': None}
    judged = None
    if plan['status'] != 'PLAN_READY':   # the kernel has no plan: nothing is run, and its own trace says where it stopped
        verdict, blocked = 'BLOCKED', _blocked_at(plan, state)
    else:
        run, whole, blocked = _model_run(packs, plan['goal'], list(plan['actions']), kinds)
        blocked = [{'reason': 'WORKFLOW_PROBLEM', 'at': [p], 'detail': None} for p in problems] + blocked
        if not blocked:
            standard, judged = _standard(impl['workflow'], standard_packs, kinds)
            if not standard['registrable']:
                blocked = [{'reason': 'STANDARD_NOT_MET', 'at': [c['check'] for c in standard['checks'] if c['truth'] != 'TRUE'], 'detail': standard['status']}]
        verdict = 'NOT_READY' if blocked else ('WAITING' if run['asks'] else 'READY')
    rule = state.rules.get(plan['goal'])
    body = {'domain': {'id': entry['id'], 'title': entry['title'], 'goal': entry['goal'], 'say': entry['say'], 'packs': list(entry['packs'])},
            'pack_digests': {'domain': copy.deepcopy(state.loaded), 'standard': copy.deepcopy(_state(standard_packs, kinds).loaded)},   # every pack this system was built from, as the State took it in
            'verdict': verdict,
            'labels': dict(entry.get('labels', {})),   # the domain's plain words for its conditions and steps
            'done_when': [list(branch) for branch in rule['branches']] if rule else [[plan['goal']]],
            'plan': dict(_brief(plan), goal=plan['goal'], scope=plan['scope']),   # what the look's hash chain carries; its needs, proof lines and branch stay in record.json
            'blocked_at': blocked, 'implementation': {k: v for k, v in impl.items() if k not in ('ui', 'ui_sha256')},
            'workflow_problems': problems, 'standard': standard, 'model_run': run, 'file_names': list(BUILT_FILES)}
    return body, dict({'schema': RECORD_SCHEMA, 'plan': plan, 'standard': judged}, **whole)


def looks(record: dict) -> list:
    """Every look and run of a built system's record.json, in one fixed order: the first look, the runs along the yes path,
    what each no led to, the look after each no that completed, the last look, the standard's judgement."""
    return ([record['plan']] + list(record['runs']) + list(record['no_runs']) + [x for x in record['no_after'] if x]
            + [x for x in (record['after'], record['standard']) if x])


def build_system(words: str, catalogue: list, load_pack, domain: str | None = None) -> dict:
    """words: what the person asked for. catalogue: the closed list of reviewed domains. load_pack(name) -> pack dict (it
    must also serve the two packs of the workflow standard). domain: the chosen domain id (an agent or a person chooses);
    when absent the stand-in matcher picks by shared words, and picks nothing on a tie.
    Refuses (ValueError) an ask without words, an unknown domain, a catalogue that is not whole, and a domain whose packs
    do not load, do not leave exactly the row's goal standing, or are deeper than this lab follows."""
    by = catalogue_rows(catalogue)
    if type(words) is not str:
        raise ValueError('Say the goal in words')
    asked = _clean(words)
    if not _says_something(asked):
        raise ValueError('Say the goal in words')
    if domain is not None and (type(domain) is not str or domain not in by):
        raise ValueError('Unknown domain: pick one from the catalogue')
    kinds = {k: dict(ACTIONS[k]) for k in KINDS}   # the four kinds as this build finds them: every State below gets these and no other
    choice = _choose(asked, catalogue, domain)
    system = {'schema': SCHEMA, 'status': 'PROPOSED_ONLY', 'asked': asked, 'choice': choice, 'kinds': list(KINDS), 'handlers': _handlers(kinds),
              'catalogue': [{'id': d['id'], 'title': d['title'], 'say': d['say']} for d in catalogue]}
    if choice['domain'] is None:
        body, record = _draft(asked, kinds)
    else:
        entry = by[choice['domain']]
        try:
            packs = [load_pack(n) for n in entry['packs']]
            standard_packs = [load_pack(n) for n in STANDARD]
            _state(packs, kinds), _state(standard_packs, kinds)
        except (OSError, LookupError, TypeError, ValueError, AttributeError, RecursionError) as why:
            raise ValueError(f'The domain {entry["id"]} does not load: {type(why).__name__ if isinstance(why, RecursionError) else why}') from None
        try:
            body, record = _built(entry, packs, standard_packs, kinds)
        except RecursionError:
            raise ValueError(f'The domain {entry["id"]} is deeper than this lab follows') from None
    system.update(body)
    system['system_sha256'] = digest(system)
    files = {'index.html': _page(system, record), 'system.json': _json(system), 'record.json': _json(record)}
    if choice['domain'] is None:
        files['draft-pack.json'] = _json(system['draft']['pack'])
    else:
        impl = system['implementation']
        files['workflow.json'] = _json(impl['workflow'])   # file names are a closed list: no name from a pack ever becomes one
        files['atoms.json'] = _json(impl['atoms'])
        files['scaffold.json'] = _json(impl['scaffold'])
    hashes = {name: _sha(text) for name, text in files.items()}   # what `shasum -a 256 <file>` prints for each written file
    files['manifest.json'] = json.dumps({'schema': MANIFEST_SCHEMA, 'system_sha256': system['system_sha256'], 'files': hashes}, indent=2, sort_keys=True) + '\n'
    hashes = dict(hashes, **{'manifest.json': _sha(files['manifest.json'])})
    folder = _ascii_slug(asked) + '-' + hashes['manifest.json'][:16]   # named after the manifest, which lists the digest of every other file: one name, one set of bytes
    return dict(system, folder=folder, files=files, files_sha256=hashes)


# ---------------------------------------------------------------- the page (no script, nothing loaded from outside; every dynamic string is cleaned and escaped)
CSS = """
:root{--bg:#fbfaf7;--fg:#1c2024;--muted:#5f6b76;--line:#d9dee3;--card:#ffffff;--soft:#eef2f4;--accent:#0b6e75;--warn:#9a4a1e;--ok:#1f7a45;--no:#a3312b}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#14181b;--fg:#e8ecef;--muted:#9aa6b1;--line:#333c44;--card:#1c2226;--soft:#222a2f;--accent:#5cc4cb;--warn:#e0985f;--ok:#6fcf97;--no:#f08a80;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#14181b;--fg:#e8ecef;--muted:#9aa6b1;--line:#333c44;--card:#1c2226;--soft:#222a2f;--accent:#5cc4cb;--warn:#e0985f;--ok:#6fcf97;--no:#f08a80;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:880px;margin:0 auto;overflow-wrap:break-word;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.hint{color:var(--muted);font-size:14px}
h1{font-size:26px;line-height:1.25;margin:10px 0 8px;text-wrap:balance}
h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:34px 0 10px}
p{margin:0 0 12px}.lead{font-size:18px;margin:0}
.tag{display:inline-block;font-size:12px;letter-spacing:.05em;text-transform:uppercase;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--muted);margin-right:6px}
.verdict{border-left:4px solid var(--accent);background:var(--card);padding:12px 14px;margin:14px 0 6px;border-radius:0 8px 8px 0}
.verdict.READY{border-color:var(--ok)}.verdict.WAITING{border-color:var(--warn)}.verdict.BLOCKED,.verdict.NOT_READY,.verdict.NO_DOMAIN{border-color:var(--no)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);padding:14px}
svg.plan{display:block;flex:none}
svg.plan rect{fill:var(--soft);stroke:var(--line);stroke-width:1.2}
svg.plan .ask rect{stroke:var(--warn);stroke-dasharray:6 4}
svg.plan .later rect{stroke-dasharray:2 3}
svg.plan .skipped rect{stroke-dasharray:1 5}
svg.plan .stop rect{stroke:var(--no);stroke-width:2}
svg.plan text{fill:var(--fg);font:12px -apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
svg.plan text.sub{fill:var(--muted);font-size:10.5px}
svg.plan text.mark{fill:var(--muted);font-size:10px;font-style:italic}
svg.plan .edge{stroke:var(--muted);stroke-width:1.3;fill:none}
svg.plan .head{fill:var(--muted)}
details{border:1px solid var(--line);border-radius:10px;background:var(--card);padding:8px 14px;margin:10px 0}
summary{cursor:pointer;font-weight:600}
details>*:not(summary){margin-top:10px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
th{font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--soft);padding:1px 5px;border-radius:4px;overflow-wrap:anywhere}
pre{overflow-x:auto;font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--soft);padding:10px;border-radius:8px}
ul,ol{margin:0 0 12px;padding-left:22px}
a{color:var(--accent)}
.t-go{color:var(--ok)}.t-ask{color:var(--warn)}.t-refuse{color:var(--no)}.t-always{color:var(--muted)}
fieldset.choice{position:relative;border:1px solid var(--line);border-radius:10px;background:var(--card);padding:12px 14px;margin:0 0 8px;min-width:0}
fieldset.choice legend{float:left;width:100%;padding:0;margin:0 0 10px}
.choice input{position:absolute;opacity:0}
.choice label{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:5px 12px;margin:0 6px 8px 0;cursor:pointer;font-size:14px}
.choice input:checked+label{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.choice input:focus-visible+label{outline:2px solid var(--accent);outline-offset:2px}
.choice .panel{display:none;margin-top:4px}
.choice input.w:checked~.panel.w,.choice input.y:checked~.panel.y,.choice input.n:checked~.panel.n{display:block}
footer{margin-top:40px;color:var(--muted);font-size:13px;border-top:1px solid var(--line);padding-top:12px}
"""
VERDICT_WORDS = {'READY': 'Ready', 'WAITING': 'Waiting on an answer', 'NOT_READY': 'Plan found, not ready', 'BLOCKED': 'No plan yet',
                 'NO_DOMAIN': 'Not built: no domain chosen'}
AFTER_WORDS = {'PLAN_READY': 'the kernel would plan the same steps again', 'WAITING': 'the kernel would wait on a question again'}


def _e(x) -> str:
    return html.escape(_visible(x), quote=True)


def _cap(s) -> str:
    s = str(s)
    return (s[:1].upper() if s[:1].isascii() else s[:1]) + s[1:]


def _short(text, n: int) -> str:
    text = str(text)
    return text if len(text) <= n else text[:n - 3] + '...'


def _wrap(text, n: int, lines: int) -> list:
    """Words on at most `lines` lines of at most n characters; what does not fit ends in three dots."""
    out, rest = [], _visible(text).split(' ')
    while rest and len(out) < lines:
        line = rest.pop(0)
        while rest and len(line) + 1 + len(rest[0]) <= n:
            line += ' ' + rest.pop(0)
        out.append(line)
    if rest:   # the last line ends in three dots: whole words go until they fit
        while len(out[-1]) + 3 > n and ' ' in out[-1]:
            out[-1] = out[-1].rsplit(' ', 1)[0]
        out[-1] += '...'
    return [_short(line, n) for line in out]


def _label(system: dict, x) -> str:
    """The plain words for a condition or a step, when the domain gave them; else the identifier itself (a name that shows nothing is said to be one)."""
    return _visible(system.get('labels', {}).get(x, x)).strip() or 'a name that shows nothing'


def _names(system: dict, xs) -> str:
    return ', '.join(_label(system, x) for x in xs)


def _where(system: dict, row: dict) -> str:
    """The plain words for every condition or step a row names."""
    return _names(system, row['at'])


def _steps_of(system: dict) -> list:
    return [s for s in system['implementation']['workflow']['steps'] if s.get('method')]


def _count(n: int) -> str:
    return 'one step' if n == 1 else f'{n} steps in order'


def _parties(asks: list) -> str:
    return ', '.join(dict.fromkeys(a['to'] for a in asks))


def _headline(system: dict):
    """The blocked_at row the first sentence names: the first one. Where the rows are those of a look of the kernel that found
    no plan (the first look of a blocked plan, or the run after an answer), a look can carry several stop reasons and the
    kernel names it with one (its status): the row of that reason is the one named, not the first in the order of the trace."""
    rows = system.get('blocked_at', [])
    if not rows:
        return None
    path = system['model_run']['path']
    look = system['plan'] if system['verdict'] == 'BLOCKED' else path[-1] if path and path[-1]['work_state'] == 'blocked' else None
    if look is None or rows[0]['reason'] in ('WORKFLOW_PROBLEM', 'ROUTE_CHANGED'):   # these two are the builder's own findings and are said first
        return rows[0]
    return next((r for r in rows if r['reason'] == look['status']), rows[0])


def _detail(row: dict) -> str:
    """What a row adds to its reason, in plain words (empty when it adds nothing)."""
    d = row.get('detail')
    return '' if not d else AFTER_WORDS.get(d, PLAIN.get(d, d)) if row['reason'] in ('GOAL_NOT_HELD', 'STANDARD_NOT_MET') else str(d)


def _reason(row: dict) -> str:
    """A blocked_at row in plain words: the reason, then what the row adds to it."""
    return PLAIN.get(row['reason'], row['reason']) + (': ' + _detail(row) if _detail(row) else '')


def _skipped(system: dict) -> list:
    return list(dict.fromkeys(m for r in system['model_run']['path'] for m in r['skipped']))


def _ran_steps(system: dict) -> set:
    return {x['method'] for r in system['model_run']['path'] for x in r['receipts']}


def _changed(system: dict) -> bool:
    """The steps that ran in the local model are not the steps of the plan the page shows."""
    return any(b['reason'] == 'ROUTE_CHANGED' for b in system.get('blocked_at', []))


def _unreached(system: dict) -> set:
    """The steps of the plan shown that neither ran nor were skipped, on a path that did not get there."""
    if system['verdict'] != 'NOT_READY' or not system['model_run']['path']:
        return set()
    return {s['method'] for s in _steps_of(system)} - _ran_steps(system) - set(_skipped(system))


def _sentence(system: dict) -> str:
    v = system['verdict']
    if v == 'NO_DOMAIN':
        tied = system['choice']['tied']
        if tied:
            titles = ', '.join(c['title'] for c in system['catalogue'] if c['id'] in tied)
            return f'These words fit {len(tied)} reviewed domains equally ({titles}), so nothing was guessed. Someone has to choose one.'
        return 'No reviewed domain shares a word with these words, so nothing was guessed. Below is what someone has to write down first.'
    n, run = len(_steps_of(system)), system['model_run']
    if v == 'READY':
        skipped = len(_skipped(system))
        tail = '' if not skipped else (' One of them is already true at its turn and is skipped.' if skipped == 1 else f' {skipped} of them are already true at their turn and are skipped.')
        return (f'Ready: {_count(n)}, and nothing waits on anyone.' + tail) if n else 'Already true: the facts support the goal and no step is needed.'
    if v == 'WAITING':
        asks = run['asks']
        if len(asks) == 1:
            tail = f'before the rest of the {n} steps can run' if run['path'][0]['pending'] else 'and nothing else is left to run'
            return f'Waiting on {asks[0]["to"]}: one question has to be answered {tail}.'
        return f'Waiting on {_parties(asks)}: {len(asks)} questions have to be answered, one after the other, before the plan is through.'
    row = _headline(system)
    inside = '; '.join(x for x in ((_where(system, row), _detail(row)) if row else ()) if x)
    named = f' ({inside})' if inside else ''
    if v == 'BLOCKED':   # the kernel's own reason, and the condition or the steps its trace names for it
        reason = row['reason'] if row else system['plan']['status']
        return f'Cannot start: {PLAIN.get(reason, reason)}{named}.'
    said = f', after {_parties(run["asks"])} said yes' if run['asks'] else ''
    r = row['reason']
    if r == 'WORKFLOW_PROBLEM':
        return f'A plan was found, but the workflow generated from it is not well formed: {_where(system, row)}.'
    if r == 'STANDARD_NOT_MET':
        return f'A plan was found, but the workflow generated from it lacks a part the standard asks for: {_where(system, row)}.'
    if r == 'ROUTE_CHANGED':
        outside = [x for x in row['at'] if x not in system['plan']['actions']]
        unrun = [x for x in row['at'] if x in system['plan']['actions']]
        parts = ([f'the kernel chose {_names(system, outside)}, {"which is no step" if len(outside) == 1 else "which are no steps"} of the plan on this page'] if outside else []) \
            + ([f'{_names(system, unrun)} {"is a step" if len(unrun) == 1 else "are steps"} of that plan and never ran'] if unrun else [])
        return f'A plan was found, but the local model took another route{said}: {"; ".join(parts)}.'
    if r == 'STEP_STOPPED':
        return f'A plan was found, but it stops in the local model{said}: the step {_where(system, row)} cannot run ({row["detail"]}).'
    if r == 'EFFECT_NOT_MADE':
        return f'A plan was found, but it does not get there in the local model{said}: the step {_where(system, row)} ran, and what it should make true does not hold afterwards.'
    if r == 'GOAL_NOT_HELD':
        return f'A plan was found, but it does not get there in the local model{said}: every step ran, and afterwards it still does not hold that {_where(system, row)} ({_detail(row)}).'
    if r == 'STILL_WAITING':
        return f'A plan was found, but it does not get there in the local model{said}: the run still waits.'
    return f'A plan was found, but it does not get there in the local model{said}: the kernel has no plan left, because {PLAIN.get(r, r)}{named}.'


def _claim(system: dict) -> str:
    plan, v, n = system['plan'], system['verdict'], len(_steps_of(system))
    goal = _label(system, plan['goal'])
    if v == 'BLOCKED':
        return f'No plan can yet make it true that {goal}.'
    if n == 0:
        return f'Nothing needs doing: the facts already support that {goal}.'
    start = 'This one step makes' if n == 1 else f'These {n} steps, in this order, make'
    if v == 'NOT_READY':
        start = 'On paper this one step makes' if n == 1 else f'On paper these {n} steps, in this order, make'
        return f'{start} it true that {goal}. In the local model the plan does not get there; the first lines of this page say where.'
    asks = system['model_run']['asks']
    tail = '' if v != 'WAITING' else f', if {asks[0]["to"]} says yes' if len(asks) == 1 else ', if every question on the way is answered yes'
    return f'{start} it true that {goal}{tail}.'


def _why(system: dict) -> str:
    """One clause per step: what it makes true, and what the local model showed when that differs."""
    run, parts = system['model_run'], []
    last = run['path'][-1] if run['path'] else None
    stopped = last['stopped']['method'] if last and last['stopped'] else None
    unreached, skipped = _unreached(system), set(_skipped(system))
    for s in _steps_of(system):
        step, what, asked = _label(system, s['method']), _label(system, s.get('effect')), s.get('waits_for')
        if s['method'] in skipped:
            parts.append((f'{asked} is not asked' if asked else f'{step} is skipped') + f', because it is already true that {what}')
        elif s['method'] == stopped:
            parts.append(f'{step} should make it true that {what} (in the local model it could not run)')
        elif s['method'] in unreached:
            parts.append((f'{asked} would be asked whether {what}' if asked else f'{step} should make it true that {what}') + ' (not reached in the local model)')
        elif asked:
            parts.append(f'{asked} is asked whether {what}')
        elif s['method'] in run['effects_missing']:
            parts.append(f'{step} should make it true that {what} (in the local model it did not)')
        else:
            parts.append(f'{step} makes it true that {what}')
    return '; '.join(parts) or 'no step is part of a plan'


def _ran(system: dict) -> str:
    """The run in the local model in one line, read off the run itself."""
    run = system['model_run']
    last, said = run['path'][-1], 'with every question answered yes ' if run['asks'] else ''
    if last['stopped']:
        return f'{said}a step could not run, and the run stopped there'
    if last['work_state'] == 'blocked':
        return f'{said}the kernel found no plan: {PLAIN.get(last["status"], last["status"])}'
    if last['work_state'] != 'completed':
        return f'{said}the run still waits'
    if _changed(system):
        return f'{said}the kernel took another route than the plan on this page'
    if not run['goal_held']:
        return f'{said}every step ran, and the goal still does not hold'
    return f'{said}the plan ran through, and the goal is held' if any(r['receipts'] for r in run['path']) else 'nothing had to run: the facts already support the goal'


def _outcome(system: dict, b: dict, held, yes: bool, changed: bool = False) -> str:
    """What one answer leads to, as the kernel ran it."""
    L = lambda x: _label(system, x)
    if b['status'] == 'STEP_STOPPED':
        head = f'The run stops: the step {L(b["stopped"]["method"])} cannot run ({b["stopped"]["reason"]}).'
    elif b['work_state'] == 'blocked':
        head = f'The run ends here: {PLAIN.get(b["status"], b["status"])}.'
    elif b['work_state'] == 'waiting':
        nxt = b['receipts'][-1]['ask'] if b['receipts'] and b['receipts'][-1].get('ask') else None
        head = ('The run goes on' if yes else 'Another route is taken') + (f' and waits again: the next question goes to {nxt["to"]}.' if nxt else ' and waits again.')
    elif yes and changed:
        head = 'The kernel takes another route than the plan on this page' + (', and afterwards the goal holds.' if held else ', and afterwards the goal still does not hold.')
    elif not b['receipts']:
        head = 'With this answer the goal holds; no step is left to run.' if held else 'No step is left to run, and the goal still does not hold.'
    elif yes:
        head = 'The plan runs through in the local model.' if held else 'Every step runs, and afterwards the goal still does not hold.'
    else:
        head = 'Another route is taken and gets there.' if held else 'Another route is taken, and afterwards the goal still does not hold.'
    text = f'<p><b>{_e(head)}</b>'
    if b['receipts']:
        text += f' Ran in the local model: {_e(", ".join(L(r["method"]) for r in b["receipts"]))}.'
    if b['skipped']:
        text += f' Already true at their turn and skipped: {_e(", ".join(L(x) for x in b["skipped"]))}.'
    if b['pending']:
        text += f' Not run: {_e(", ".join(L(x) for x in b["pending"]))}.'
    return text + '</p>'


def _ask_block(system: dict, i: int, a: dict, before: list) -> str:
    n, last = f'ask{i}', i == len(system['model_run']['asks']) - 1
    first = ('The run waits. Nothing after the question has run. Looking again asks nothing and costs nothing, '
             "and a way that costs less in this domain's order of preference is still taken.")
    return ('<fieldset class="choice">'
            f'<legend><b>{_e(_cap(a["to"]))}</b> is asked: {_e(a["question"])}</legend>'
            f'<input class="w" type="radio" name="{n}" id="{n}w" checked><label for="{n}w">Not answered yet</label>'
            f'<input class="y" type="radio" name="{n}" id="{n}y"><label for="{n}y">They say yes</label>'
            f'<input class="n" type="radio" name="{n}" id="{n}n"><label for="{n}n">They say no</label>'
            f'<div class="panel w"><p>{_e(first)}</p></div>'
            f'<div class="panel y">{_outcome(system, a["if_yes"], system["model_run"]["goal_held"] if last else None, True, last and _changed(system))}</div>'
            f'<div class="panel n">{_outcome(system, a["if_no"], a["if_no"]["goal_held"], False)}</div></fieldset>'
            f'<p class="hint">Asked by the step {_e(_label(system, a["asked_by"]))}'
            + (f', only after {_e(", ".join(dict.fromkeys(before)))} said yes' if before else '')
            + f'. The answer must come from {_e(a["to"])} and present the receipt of this question.</p>')


def _marks(system: dict) -> dict:
    """What the picture says about a step beyond its name: method -> (class, words)."""
    run, v, marks = system['model_run'], system['verdict'], {}
    kind = {s['method']: s.get('kind') for s in _steps_of(system)}
    if v == 'WAITING':
        for m in run['path'][0]['pending']:
            marks[m] = ('later', 'asked after the answer' if kind.get(m) == 'ask' else 'after the answer')
    if v == 'NOT_READY' and run['path']:
        last = run['path'][-1]
        for m in _unreached(system):
            marks[m] = ('later', 'not reached')
        if last['stopped']:
            marks[last['stopped']['method']] = ('stop', 'stops here')
        for m in run['effects_missing']:
            marks[m] = ('stop', 'effect not made')
    for m in _skipped(system):
        marks.setdefault(m, ('skipped', 'already true: skipped'))
    return marks


def _picture(system: dict, steps: list, edges: list) -> str:
    """The plan as boxes and arrows: one box per method step, one arrow per prerequisite, columns by dependency depth.
    An arrow to the next column is one straight line through the gap between the columns; a longer one runs through the
    gaps between rows and columns and enters its step from above, so no arrow crosses a box that is not one of its ends."""
    nodes = [s for s in steps if s.get('method')]
    if not nodes:
        return ''
    level, columns, marks, cells = {}, {}, _marks(system), {}
    for s in nodes:   # steps arrive in dependency order, so every prerequisite already has its level
        level[s['id']] = 1 + max([level[a] for a in s.get('after', []) if a in level], default=-1)
        columns.setdefault(level[s['id']], []).append(s['id'])
        cls, mark = marks.get(s['method'], ('', ''))
        sub = [_short(f'asks {_visible(s["waits_for"])}', 27)] if s.get('waits_for') else _wrap(_label(system, s.get('effect')), 27, 2)
        cells[s['id']] = (_wrap(_label(system, s['method']), 23, 2), sub, mark, ' '.join(c for c in ('ask' if s.get('waits_for') else '', cls) if c))
    W, GX, GY, TOP = 174, 40, 30, 30   # four columns fit the page without scrolling; every box is as tall as the fullest one
    H = max(56, 19 + 15 * max(len(t) + len(sub) + bool(mark) for t, sub, mark, _ in cells.values()))
    width = (max(columns) + 1) * (W + GX) - GX + 2
    height = TOP + max(len(c) for c in columns.values()) * (H + GY) - GY + 2
    at = {sid: (1 + lv * (W + GX), TOP + i * (H + GY)) for lv, ids in columns.items() for i, sid in enumerate(ids)}
    parts = [f'<svg class="plan" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="The plan as steps and the order they depend on">']
    far = 0
    for ed in edges:
        if ed['from'] not in at or ed['to'] not in at:
            continue
        (x1, y1), (x2, y2) = at[ed['from']], at[ed['to']]
        sy, ey = y1 + H // 2, y2 + H // 2
        if level[ed['to']] - level[ed['from']] == 1:
            parts.append(f'<path class="edge" d="M{x1 + W},{sy} L{x2 - 6},{ey}"/><polygon class="head" points="{x2},{ey} {x2 - 7},{ey - 4} {x2 - 7},{ey + 4}"/>')
        else:   # skips a column: out into the gap, along the gap above the row of its step, down into the step
            off = (far % 5 - 2) * 4
            far += 1
            gx, lane, tx = x1 + W + GX // 2 + off, y2 - GY // 2 + off, x2 + W // 2 + off * 3
            parts.append(f'<path class="edge" d="M{x1 + W},{sy} L{gx},{sy} L{gx},{lane} L{tx},{lane} L{tx},{y2 - 6}"/>'
                         f'<polygon class="head" points="{tx},{y2} {tx - 4},{y2 - 7} {tx + 4},{y2 - 7}"/>')
    for s in nodes:
        x, y = at[s['id']]
        title, sub, mark, cls = cells[s['id']]
        tip = f'{s["method"]} asks {s["waits_for"]} whether {s.get("effect")}' if s.get('waits_for') else f'{s["method"]} makes {s.get("effect")}'
        lines = [('', t) for t in title] + [(' class="sub"', t) for t in sub] + ([(' class="mark"', mark)] if mark else [])
        parts.append(f'<g class="{cls}"><title>{_e(tip)}</title><rect x="{x}" y="{y}" width="{W}" height="{H}" rx="8"/>'
                     + ''.join(f'<text{kind} x="{x + 12}" y="{y + 21 + 15 * i}">{_e(line)}</text>' for i, (kind, line) in enumerate(lines)) + '</g>')
    parts.append('</svg>')
    return ''.join(parts)


def _page(system: dict, record: dict) -> str:
    e, v = _e, system['verdict']
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">',
           f'<title>{e(_short(system["asked"], 60))}</title><style>{CSS}</style></head><body><main>',
           f'<p><span class="tag">Proposal only</span><span class="tag">{e(VERDICT_WORDS.get(v, v))}</span></p>',
           f'<h1>{e(system["asked"])}</h1>',
           f'<div class="verdict {e(v)}"><p class="lead">{e(_sentence(system))}</p></div>']
    if v == 'NO_DOMAIN':
        d = system['draft']
        if system['choice']['tied']:
            out.append('<p class="hint">To build one of them, name it: ' + ' or '.join(f'<code>--domain {e(i)}</code>' for i in system['choice']['tied']) + '.</p>')
        out += ['<h2>What the builder can build today</h2><div class="scroll"><table><tr><th>Domain</th><th>Its name</th><th>You would say</th></tr>',
                ''.join(f'<tr><td>{e(c["title"])}</td><td><code>{e(c["id"])}</code></td><td>{e(c["say"])}</td></tr>' for c in system['catalogue']), '</table></div>',
                '<h2>What someone has to write down first</h2><ol>', ''.join(f'<li>{e(x)}</li>' for x in d['to_write']), '</ol>',
                f'<h2>What the kernel says about a draft</h2><p><span class="tag">{e(d["kernel_status"])}</span> {e(_cap(PLAIN.get(d["kernel_status"], d["kernel_status"])))}. '
                'A draft is a template, not knowledge: while its rule is unapproved, and no method makes the goal itself, the kernel plans nothing from it.</p>',
                f'<details><summary>The draft pack</summary><pre>{e(json.dumps(d["pack"], indent=2, ensure_ascii=False))}</pre></details>',
                '<details><summary>How a new domain gets in</summary><p>The draft is filled in and authored as packs, recorded as a case, and sent through the loop that tests every version. '
                'The catalogue is a reviewed pack too: the row for the new domain is an edit to that pack, reviewed like the packs it names. Once that version is promoted, the same words build a system.</p></details>']
    else:
        wf, sc, run, plan, st = system['implementation']['workflow'], system['implementation']['scaffold'], system['model_run'], system['plan'], system['standard']
        L = lambda x: _label(system, x)
        n = len(_steps_of(system))
        out.append(f'<p class="hint">Built from the reviewed domain <b>{e(system["domain"]["title"])}</b>, chosen by {e(system["choice"]["how"])}.</p>')
        pic = _picture(system, wf['steps'], wf.get('edges', []))
        cost = f'plan cost {json.dumps(plan["cost"])}; ' if plan['cost'] is not None else ''
        out.append('<h2>The plan</h2>' + (f'<div class="scroll">{pic}</div>' if pic else '<p>No step is needed or possible right now.</p>'))
        out.append(f'<details><summary>{"Why this picture" if pic else "Why there is no picture"}</summary>'
                   f'<p><b>Claim.</b> {e(_claim(system))}</p>'
                   f'<p><b>Why.</b> {e(_cap(_why(system)))}.</p>'
                   f'<p><b>Evidence.</b> Kernel status {e(plan["status"])}; {e(cost)}trace root <code>{e(plan["trace_root_sha256"])}</code>; '
                   f'workflow problems: {e("; ".join(system["workflow_problems"]) or "none")}.</p>'
                   '<p><b>What would change it.</b> A new reviewed rule, a changed fact, a revoked grant, a smaller budget or an answer to an open question: the kernel plans again from the record.</p></details>')
        if v in ('BLOCKED', 'NOT_READY'):
            rows = ''.join(f'<tr><td>{e(_cap(_where(system, b)))} <code>{e(", ".join(b["at"]))}</code></td><td>{e(_cap(_reason(b)))}</td>'
                           f'<td>{e(_cap(UNBLOCK.get(b["reason"], "a reviewed change to the packs")))}</td></tr>' for b in system['blocked_at'])
            out.append(('<h2>Why it cannot start</h2>' if v == 'BLOCKED' else '<h2>What stands in the way</h2>')
                       + '<div class="scroll"><table><tr><th>Where</th><th>Reason</th><th>What would unblock it</th></tr>'
                       + (rows or '<tr><td colspan="3">The kernel recorded no specific condition.</td></tr>') + '</table></div>')
        done = system['done_when']
        out.append('<h2>What done means</h2>' + ('<p class="hint">Any one of these is enough.</p>' if len(done) > 1 else '')
                   + '<ul>' + ''.join(f'<li>{e(_cap(" and ".join(L(c) for c in branch)))}</li>' for branch in done) + '</ul>')
        if run['asks']:
            shown = run['asks'][:QUESTIONS_SHOWN]
            out.append(('<h2>Waiting on an answer</h2>' if v == 'WAITING' else '<h2>The questions on the way</h2>')
                       + ''.join(_ask_block(system, i, a, [x['to'] for x in run['asks'][:i]]) for i, a in enumerate(shown)))
            if len(run['asks']) > len(shown):
                rest = ''.join(f'<li><b>{e(_cap(a["to"]))}</b> is asked: {e(a["question"])}</li>' for a in run['asks'][len(shown):])
                out.append(f'<p class="hint">The plan asks {len(run["asks"])} questions. The first {len(shown)} are shown above with both answers; these follow, each only after every question before it was answered yes:</p><ul>{rest}</ul>')
        # The machinery, folded: each summary line carries the finding, the detail is one click away.
        go = sum(1 for r in sc['rules'] if r['tag'] == 'go')
        need = sum(1 for r in sc['rules'] if r['tag'] == 'ask')
        who = ('no step is planned' if not go and not need else
               ('one step has its grant' if go == 1 else f'{go} steps have their grant') + (f', {need} {"needs" if need == 1 else "need"} one first' if need else ''))
        out.append('<h2>The details</h2>')
        out.append(f'<details><summary>Who may do what: {who}</summary><ul>'
                   + ''.join(f'<li><b class="t-{e(r["tag"])}">{e(r["tag"])}</b> {e(r["line"])}</li>' for r in sc['rules']) + '</ul></details>')
        if st['status'] != 'NOT_APPLICABLE':
            passed = sum(1 for c in st['checks'] if c['truth'] == 'TRUE')
            out.append(f'<details><summary>The workflow generated on this page has the parts the standard asks for: {"yes" if st["registrable"] else "no"}, {passed} of {len(st["checks"])}</summary>'
                       f'<p>The kernel judged the generated workflow <code>{e(st["workflow"])}</code> against the reviewed rule <code>{e(st["rule"])}</code> and answered <code>{e(st["status"])}</code>. '
                       'This is about the shape of the workflow written below, not about the goal above.</p>'
                       '<div class="scroll"><table><tr><th>Check</th><th>Result</th></tr>' + ''.join(f'<tr><td>{e(_cap(c["question"]))}</td><td>{e(c["truth"])}</td></tr>' for c in st['checks']) + '</table></div></details>')
        steps = ''.join(f'<tr><td>{e(_cap(L(s.get("method", s["id"]))))} <code>{e(s["id"])}</code></td><td>{e(", ".join(s.get("after", [])) or "-")}</td><td>{e(s["action"])}</td><td>{e(s["verify"])}</td></tr>' for s in wf['steps'])
        count = 'no method step' if n == 0 else 'one method step' if n == 1 else f'{n} method steps'
        out.append(f'<details><summary>The workflow, step by step: {count}, between a step that records the goal and a step that shows the result</summary>'
                   '<div class="scroll"><table><tr><th>Step</th><th>After</th><th>What it does</th><th>How it is checked</th></tr>' + steps + '</table></div></details>')
        if run['path']:
            how = '' if not run['asks'] else (', with every question answered yes' if v == 'WAITING' else f', with {len(run["asks"])} {"question" if len(run["asks"]) == 1 else "questions"} answered yes before it ended')
            names = lambda xs: e(', '.join(L(x) for x in xs) or '-')
            said = lambda r: ('steps that are not in the plan on this page ran in the local model' if r['status'] == 'LOCAL_MODEL_EFFECTS_RECORDED' and any(x['method'] not in plan['actions'] for x in r['receipts'])
                              else PLAIN.get(r['status'], r['status']))
            what = lambda i, r: e(_cap((f'after {run["asks"][i - 1]["to"]} said yes: ' if i else '') + said(r)
                                       + (f' ({L(r["stopped"]["method"])}: {r["stopped"]["reason"]})' if r['stopped'] else '')))
            runs = ''.join(f'<tr><td>{i + 1}</td><td>{what(i, r)}</td><td>{names(x["method"] for x in r["receipts"])}</td><td>{names(r["skipped"])}</td><td>{names(r["pending"])}</td></tr>'
                           for i, r in enumerate(run['path']))
            held = '' if run['goal_held'] is None else (' The kernel\'s next look finds the goal held.' if run['goal_held'] else ' The kernel\'s next look does not find the goal held.')
            out.append(f'<details><summary>A run in the local model: {e(_ran(system))}</summary><p>The plan executed against a model of the world{e(how)}. '
                       f'Nothing real happened: each receipt is marked local only.{e(held)}</p>'
                       '<div class="scroll"><table><tr><th>Run</th><th>What happened</th><th>Steps that ran</th><th>Already true, skipped</th><th>Not run</th></tr>' + runs + '</table></div></details>')
        out.append(f'<details><summary>The department that would own it</summary><p>{e(_cap(sc["purpose"]))}.</p><div class="scroll"><table><tr><th>Function</th><th>What it holds</th></tr>'
                   + ''.join(f'<tr><td>{e(_cap(k))}</td><td>{e(val)}</td></tr>' for k, val in sc['functions'].items()) + '</table></div></details>')
    trace = (record.get('plan') or record.get('draft'))['trace']
    out.append(f'<details><summary>The record: {len(trace)} decisions in a hash chain</summary><p>The kernel logs every decision in a hash chain; these are the decisions of its first look, in order, each with its own hash. '
               'The last hash is the trace root' + (' quoted under the picture' if v != 'NO_DOMAIN' else '') + '. Every look and run behind this page is in <a href="record.json">record.json</a>, whole, so each chain can be recomputed.</p>'
               '<div class="scroll"><table><tr><th>#</th><th>Decision</th><th>Hash</th></tr>'
               + ''.join(f'<tr><td>{e(r["seq"])}</td><td>{e(r["operation"])}</td><td><code>{e(r["sha256"][:16])}</code></td></tr>' for r in trace) + '</table></div></details>')
    out.append('<h2>Files</h2><ul>' + ''.join(f'<li><a href="{e(n)}">{e(n)}</a></li>' for n in system['file_names'] if n != 'index.html') + '</ul>')
    out.append('<footer>Built by the Core Algorithm lab from the words above' + (f' and the reviewed domain {e(system["domain"]["title"])}' if system.get('domain') else '') + '. '
               f'{e(system["status"])}: nothing on this page has run outside a local model, and running a step for real is outside this lab. '
               f'Domain chosen by {e(system["choice"]["how"])}. System sha256 <code>{e(system["system_sha256"])}</code>; the digest of every other file written beside this page is in manifest.json.</footer></main></body></html>')
    return ''.join(out)
