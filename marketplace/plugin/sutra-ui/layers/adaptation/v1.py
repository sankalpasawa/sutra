"""layers/adaptation/v1.py -- Adaptation, version 1: the implementation behind the interface's adaptation entries (PRD A1.18).

Its recipe is v1.json beside it: the Adaptation engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here (A1 step A1): by reference, to the body
engine_runtime still holds, until this layer moves one in to change it (move on touch, A1.19). WORDS and LAYOUT stay
empty until the words move, so the prompts are still read from the .md bundle. view() returns the pane's read model by
reference.
"""
import os
import re

from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'adaptation'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'

#: what a required engine's check refuses, in the owner's words (J2B-2): Make is told, so it shapes nothing the check fails
REFUSES = (('Check', 'a page with a script, a link to no page, a page with almost no text, a page that breaks one of your rules'),)


def make_on():
    """The make setting (S.SETTINGS['adaptation']['make']): Adaptation makes a line when no template fits. The build flag
    J2_ADAPT_MAKE, in Beta only; not a switch of the interface, so it is read here and nowhere else."""
    return str(os.environ.get('J2_ADAPT_MAKE') or '').strip().lower() in ('1', 'true', 'on', 'yes')


def shipped():
    """The Library's shipped work engines by name, Setup (Root's) left out. An engine born into the records home carries
    the words of the department it was born for, so it is none of these (J2B-2): it is a name that is taken, and no more."""
    return {n: t for n, t in R.engine_templates().items() if t.get('kind') == 'work' and not t.get('made_by') and n != 'Setup'}


def practices(d):
    """The practices in place that Make reads (J2B-2), as names and use cases and never files: the department's rules with
    their tags; the shipped work engines except Setup (a born engine carries another department's words, so it is not
    one), each with its use case, what it reads and writes; the Library's artifacts; each engine the kind requires with
    what its check refuses; and the names already taken. Not the kind's done line, which the done-when items replace, and
    not other departments' workflows."""
    rules = [{'tag': str(r.get('tag') or ''), 'line': str(r.get('line'))} for r in (d or {}).get('rules') or []
             if isinstance(r, dict) and r.get('line')]
    lib = [{'name': n, 'use_case': str(t.get('use_case') or ''), 'reads': t.get('reads') or 'Brief', 'writes': t.get('writes') or n}
           for n, t in shipped().items()]
    import artifacts
    kinds = [k for name, k in (R.defs().get('kinds') or {}).items() if name != 'root']
    names = []
    for k in kinds:
        names += [a for a in k.get('artifacts') or [] if a not in names]
    shelf = [{'name': a, 'use_case': str((artifacts.get(a) or {}).get('use_case') or '')} for a in names]
    refuses = dict(REFUSES)
    known = R.defs()['engines']
    required = [{'name': n, 'use_case': str((known.get(n) or {}).get('use_case') or ''),
                 'refuses': refuses.get(n) or str((known.get(n) or {}).get('description') or '')} for n in R.required_engines(d)]
    return {'rules': rules, 'engines': lib, 'artifacts': shelf, 'required': required, 'taken': sorted(known)}


def adapt_source(ctx, step, item):
    """Where the proposal comes from (J2.b): the Library's template when the department's kind has one, else Adaptation
    shapes the line itself. A line Root's check refused is shaped again, whatever its first source was, unless the
    kind requires engines: then it is the Library's line again, with the engines the kind requires (_library_repair).
    With the make setting on (J2_ADAPT_MAKE), a default department's first line and a line Root sent back are made, not
    taken, and a shaped source (M6.3) also carries the practices in place (J2B-2): in the step's answer, and on the
    request as Adaptation holds it, for the step that shapes."""
    d, pl = ctx['dept'], ctx['post']['payload']
    make, faulted = make_on(), bool(pl.get('faults'))
    lib = list(d.get('engines') or (W.KINDS.get(d.get('kind') or 'website') or {}).get('line') or [])
    # with the make setting on, a line Root's check sent back is shaped, whatever the kind requires: Make keeps the engines
    # the kind requires at level 1 or answers that one cannot serve (J2B-1); the Library's line again is the setting's absence
    repair = R._library_repair(d, lib) if faulted and not make else None
    if repair:
        lib = repair
    # a default department's Do is a fallback, not a fit (J2B-1): with the setting on, its first line is made
    default = make and (d.get('kind') or 'website') == 'default' and not d.get('workflows')
    shape = (faulted and not repair) or not lib or default
    engines = []
    if not shape:
        known = R.defs()['engines']
        for n in lib:
            e = known.get(n) or {}
            engines.append({'name': n, 'does': str(e.get('description') or e.get('use_case') or ''), 'reads': e.get('reads') or 'Brief',
                            'writes': e.get('writes') or n, 'internet': False})
    took = ("takes the Library's line again, with what its kind requires (%s): " % R._names(R.required_engines(d)) if repair
            else "takes the Library's line: ")
    out = {'shape': shape, 'source': 'shaped' if shape else 'library', 'engines': engines,
           'said': 'shapes the line from the goal' if shape else took + ' -> '.join(lib)}
    if shape and make_on():
        out['practices'] = pl['practices'] = practices(d)
    return out


def items_of(d):
    """The department's done-when items as dept.json keeps them: [{id, text, how, level}]."""
    return [i for i in (d or {}).get('done_items') or [] if isinstance(i, dict) and i.get('id')]


def item_lines(d):
    """The done-when items as a prompt names them, one a line ('D1: the site is live'); 'none' when the record has no items."""
    return '\n'.join('%s: %s' % (i['id'], ' '.join(str(i.get('text') or '').split())) for i in items_of(d)) or 'none'


def practices_text(p):
    """The practices in place as the make.shape prompt is given them: names and use cases, never files. The rules and the
    names taken are inputs of their own."""
    lines = ["THE LIBRARY'S ENGINES (level 1 takes one as it is, with the reads and writes shown):"]
    lines += ['- %s: %s (reads %s, writes %s)' % (e['name'], e['use_case'], e['reads'], e['writes']) for e in p.get('engines') or []]
    lines.append("THE LIBRARY'S ARTIFACTS:")
    lines += ['- %s: %s' % (a['name'], a['use_case']) for a in p.get('artifacts') or []]
    if p.get('required'):
        lines.append('THIS KIND OF DEPARTMENT REQUIRES THESE ENGINES, each kept at level 1 (what its check refuses is shown):')
        lines += ['- %s: %s; it refuses %s' % (r['name'], r['use_case'], r['refuses']) for r in p['required']]
    return '\n'.join(lines)


def norm_engines(engs):
    """A line's engines as a proposal carries them (the form adapt_line_offer has always posted): a name of at most forty
    characters, what it does in two hundred, what it reads and writes, and whether it goes to the internet. Tolerant of
    what a model might answer, so the check can say what is wrong with it."""
    out = []
    for e in engs or []:
        e = e if isinstance(e, dict) else {}
        name = ' '.join(str(e.get('name') or '').split())[:40]
        out.append({'name': name, 'does': ' '.join(str(e.get('does') or '').split())[:200],
                    'reads': ' '.join(str(e.get('reads') or 'Brief').split())[:40],
                    'writes': ' '.join(str(e.get('writes') or name).split())[:40], 'internet': bool(e.get('internet'))})
    return out


def covered_engines(engs):
    """The form above, and the items each engine says it covers when it says (M5.1): a model that was not asked may still
    name them, and what it names is kept."""
    rows = norm_engines(engs)
    for row, e in zip(rows, engs or []):
        e = e if isinstance(e, dict) else {}
        row['covers'] = [c for c in e.get('covers') or [] if isinstance(c, str)] if isinstance(e.get('covers'), list) else []
    return rows


def made_engines(engs):
    """A made line's engines (J2B-4): the form above with covers, and what Make adds to it: its level, how sure it is, and
    what it doubts (cut to three hundred, the form the workflow schema has for it)."""
    rows = covered_engines(engs)
    for row, e in zip(rows, engs or []):
        e = e if isinstance(e, dict) else {}
        row['level'], row['confidence'] = e.get('level'), e.get('confidence')
        if str(e.get('doubt') or '').strip():
            row['doubt'] = ' '.join(str(e['doubt']).split())[:300]
    return [{k: v for k, v in row.items() if v is not None} for row in rows]


def workflow_of(engines, source, d):
    """The line as a workflow value (DEFS['workflow'], A1.14): S.as_workflow over the engines, which looks up what a name
    reads and writes and inverts each engine's covers, and then the fields of a made engine it does not carry over
    (its level, confidence and doubt), and the engines the kind requires marked so."""
    wf = S.as_workflow(engines, source, d)
    by = {e.get('name'): e for e in engines if isinstance(e, dict)}
    required = R.required_engines(d)
    for row in wf['engines']:
        for key in ('level', 'confidence', 'doubt'):
            if by.get(row['name'], {}).get(key) is not None:
                row[key] = by[row['name']][key]
        if row['name'] in required:
            row['required'] = True
    return wf


def is_made(ctx):
    """Whether the answer in hand is a made one (J2B-4): the make setting is on and an agent gave it. The offline draft
    keeps being the draft, with no confidence and no question (J2B-9)."""
    return make_on() and (((ctx or {}).get('how') or {}).get('adapt.line') in ('model', 'checklist'))


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def made_notes(engs, d):
    """What is wrong with a made line beyond what a shaped one may be (J2B-4, J2B-6), one note each, in the owner-neutral
    words the other checks use: a level 1 or 2 that code agrees with (an engine named after a shipped template is level 1
    and keeps its reads and writes; any other is level 2), a confidence from 0 to 1 and a doubt below 0.8, covers that
    are known items, every item covered, every engine covering an item or feeding a later one, and every engine the kind
    requires there, at level 1."""
    notes, rows = [], [e for e in engs if isinstance(e, dict)]
    items, lib, names = [i['id'] for i in items_of(d)], shipped(), []
    covered = set()
    for e in rows:
        n = ' '.join(str(e.get('name') or '').split())[:40]
        names.append(n)
        level, conf = e.get('level'), e.get('confidence')
        if isinstance(level, bool) or level not in (1, 2):
            notes.append('%s names no level, 1 or 2' % n)
        elif n in lib:
            if level != 1:
                notes.append('%s is an engine of the Library, so it is level 1' % n)
            elif (e.get('reads') or 'Brief', e.get('writes') or n) != (lib[n].get('reads'), lib[n].get('writes')):
                notes.append('%s is level 1, so it keeps its Library reads (%s) and writes (%s)' % (n, lib[n].get('reads'), lib[n].get('writes')))
        elif level == 1:
            notes.append('%s is level 1, and the Library has no engine of that name' % n)
        if not _number(conf) or not 0 <= conf <= 1:
            notes.append('%s names no confidence from 0 to 1' % n)
        elif conf < S.CONFIDENCE['show_below'] and not str(e.get('doubt') or '').strip():
            notes.append('%s is not sure (below %s) and names no doubt' % (n, S.CONFIDENCE['show_below']))
        cv = e.get('covers')
        if not isinstance(cv, list) or any(not isinstance(c, str) for c in cv):
            notes.append('%s names the items it covers as a list' % n)
            continue
        unknown = [c for c in cv if items and c not in items]
        if unknown:
            notes.append('%s covers %s, which done-when does not have' % (n, ', '.join(unknown)))
        covered |= set(cv)
    left = [i for i in items if i not in covered]
    if left:
        notes.append('%s %s covered by no engine' % (', '.join(left), 'is' if len(left) == 1 else 'are'))
    for i, e in enumerate(rows):
        if isinstance(e.get('covers'), list) and not e['covers'] and not any(l.get('reads') == e.get('writes') for l in rows[i + 1:]):
            notes.append('%s covers no item and feeds no engine after it' % ' '.join(str(e.get('name') or '').split())[:40])
    gone = [r for r in R.required_engines(d) if r not in names]
    if gone:
        notes.append('the plan leaves out %s, which this kind of department requires' % R._names(gone))
    return notes


def cannot_notes(cannot, d):
    """A cannot answer (J2B-4): it names an engine the kind requires, items done-when has, and why."""
    if not isinstance(cannot, dict):
        return ['cannot names the engine, the items and why']
    notes, items = [], [i['id'] for i in items_of(d)]
    if cannot.get('engine') not in R.required_engines(d):
        notes.append('%s is not an engine this kind of department requires, so it cannot be the reason there is no plan' % cannot.get('engine'))
    named = cannot.get('items')
    if not isinstance(named, list) or not named or any(not isinstance(i, str) or (items and i not in items) for i in named):
        notes.append('cannot names items that done-when has')
    if not str(cannot.get('why') or '').strip():
        notes.append('cannot says no why')
    return notes


def c_line_is_engines(ctx, step, item, out):
    """One to six engines that code finds nothing wrong with: the shape is the agent's, the check is code (today's rules:
    each named once and new to the Library, the first reading the Brief, each reading what one before it wrote and
    writing something new). Then Root's standards at the proposal stage (A4): the line is run as a workflow through
    S.validate_workflow, and a failed row, named by its standard, is a note beside today's wording. A warning row passes.
    A made line (M6.4) is also held to J2B-4 and J2B-6, and may answer cannot instead, for an engine the kind requires."""
    d = (ctx or {}).get('dept')
    made = is_made(ctx)
    engs = out.get('engines') if isinstance(out, dict) else None
    if made and isinstance(out, dict) and out.get('cannot') is not None and not engs:
        notes = cannot_notes(out['cannot'], d)
        if notes:
            return {'ok': False, 'notes': notes}
        c = out['cannot']
        return {'ok': True, 'notes': ['%s cannot serve %s' % (c['engine'], ', '.join(c['items']))]}
    if not isinstance(engs, list) or not 1 <= len(engs) <= 6:
        return R._verdict(False, '', 'one to six engines')
    legacy = R._line_notes(engs)
    if made:
        # a level-1 engine is the Library's own, kept on its template: it is not 'new to the Library', and need not be
        lib = shipped()
        taken = {' '.join(str(e.get('name') or '').split())[:40] for e in engs if isinstance(e, dict) and e.get('level') == 1 and e.get('name') in lib}
        legacy = [(c, n) for c, n in legacy if not (c == 'names new to the Library' and any(n == 'the Library already has an engine named %s' % t for t in taken))]
    notes = [n for _, n in legacy]
    if made:
        notes += [n for n in made_notes(engs, d) if n not in notes]
    source = (((ctx or {}).get('bag') or {}).get('adapt.source') or {}).get('source') or 'shaped'
    rows = made_engines(engs) if made else norm_engines(engs)
    for row in S.validate_workflow(workflow_of(rows, source, d), 'proposal', d, {}):
        note = '%s: %s' % (row['check'], row['why'])
        if not row['passed'] and note not in notes:
            notes.append(note)
    return {'ok': not notes, 'notes': notes or ['%d engines, each reading what one before it wrote' % len(engs)]}


def p_adapt_line(ctx, step, item):
    """The prompt that shapes the line (adapt.line). Each part names the department's done-when items (M5.1). With the make
    setting on and the practices in place on the request (M6.3), it is the typed part make.shape (A1-SHAPE, M6.4), which
    asks for each engine's level, covers, confidence and doubt, or for cannot; otherwise make.line, as it has always been."""
    d, pl = ctx['dept'], ctx['post']['payload']
    rules = '; '.join(str(r.get('line')) for r in d.get('rules') or [] if r.get('line'))
    taken = ', '.join(sorted(R.defs()['engines']))
    refused = ('\n\n' + R._prompt('adaptation', 'make', 'refused', ctx['ref'], faults='; '.join(str(f) for f in pl['faults']))) if pl.get('faults') else ''
    slots = dict(dept=d.get('name'), words=pl.get('words') or d.get('goal'), items=item_lines(d), taken=taken,
                 out=R._out_artifacts() or 'none', rules=rules or 'none', refused=refused)
    prac = ((ctx.get('bag') or {}).get('adapt.source') or {}).get('practices') or pl.get('practices')
    if make_on() and prac:
        return R._prompt('adaptation', 'make', 'shape', ctx['ref'], practices=practices_text(prac), **slots)
    return R._prompt('adaptation', 'make', 'line', ctx['ref'], **slots)


def d_adapt_line(ctx, step, item):
    """The draft, when no agent is there to judge: two engines, the facts from the internet and the site from the facts.
    Their names are ones the Library does not have yet: a second department shaped this way takes Facts 2 and Site 2
    (found 2026-10-07: it took Facts and Site again, its check refused the line, and nothing was said). The site, the last
    engine, covers every done-when item (M5.1); the draft carries no confidence and asks no question (J2B-9)."""
    def line(n):
        tag = '' if n == 1 else ' %d' % n
        return [{'name': 'Facts' + tag, 'does': 'finds on the internet what the goal names, each fact with its source', 'reads': 'Brief',
                 'writes': 'Facts' + tag, 'internet': True},
                {'name': 'Site' + tag, 'does': "writes the site's pages from the facts, each with its source", 'reads': 'Facts' + tag,
                 'writes': 'Live site', 'internet': False}]
    engines = next((line(n) for n in range(1, 50) if not R._line_faults(line(n))), line(1))
    ids = [i['id'] for i in items_of((ctx or {}).get('dept'))]
    for e in engines:
        e['covers'] = []
    if ids:
        engines[-1]['covers'] = ids
    return {'engines': engines}


def with_covers(engines, d):
    """Each engine's covers made known and whole (M5.1), and the map of item to engines the proposal carries. Only items
    done-when has stay. When no engine names any, code maps every item to the last engine, as it does for a Library line."""
    ids = [i['id'] for i in items_of(d)]
    for e in engines:
        e['covers'] = [c for c in dict.fromkeys(e.get('covers') or []) if c in ids]
    if ids and engines and not any(e['covers'] for e in engines):
        engines[-1]['covers'] = list(ids)
    out = {}
    for e in engines:
        for c in e['covers']:
            out.setdefault(c, []).append(e['name'])
    return out


def split_doubt(text):
    """A doubt as an engine states it, and what to do unless the owner says: 'Unless you say, ...' begins the second
    sentence, which Identity's question puts after the doubt (J2B-8). Returns (doubt, fallback or None)."""
    parts = re.split(r'(?i)\bunless you say,?\s*', ' '.join(str(text or '').split()), maxsplit=1)
    head, tail = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else '')
    return head[:600], (tail[:600] or None)


def hears_doubt():
    """Whether Identity's recipe has a handler for a doubt (A1.14: an act is posted only to a receiver that hears it)."""
    return R._handler(R.engine_def('Identity'), {'msg_type': 'inform', 'payload': {'word': 'doubt'}}) is not None


def line_conflict(ref, thread, why, bound=None, src='Adaptation', options=None, engines=None, source=None, words=None):
    """The bargain did not close (a refusal, or its bound), or no line can be made: it goes to Identity, never silently to
    nothing (J2.2). _line_conflict as engine_runtime has it, with the ways out Adaptation can build (M6.4)."""
    offer = R._line_proposal(ref, thread) or {}
    if any((x.get('payload') or {}).get('word') == 'conflict' and (x.get('payload') or {}).get('for') == thread for x in R.board(ref)):
        return None
    body = {'word': 'conflict', 'engines': engines if engines is not None else offer.get('engines') or [],
            'source': source or offer.get('source'), 'words': words if words is not None else offer.get('words'),
            'why': why, 'bound': bound, 'for': thread}
    if options:
        body['options'] = options
    return R.post(ref, src, 'Identity', 'inform', body)


def cannot_options(d, cannot, words=None):
    """The ways out of a plan no engine can serve, built by code (J2B-7): set the department up again, done its own way (a
    Root request in the goal's words, for the owner's stamp); leave the item out of done-when, when done-when has another
    to keep; stop."""
    opts = [W.option('root_setup', 'Set it up again, done its own way',
                     'Root sets this department up again, done its own way, for your stamp; nothing is set up here')]
    opts[0].update({'kind': 'root_setup', 'params': {'words': (str(d.get('goal') or '') or str(words or ''))[:4000]}})
    items = items_of(d)
    named = [i for i in items if i['id'] in (cannot.get('items') or [])]
    if len(items) > 1 and named:
        i = named[0]
        opts.append(dict(W.option('leave:' + i['id'], 'Leave %s out' % i['id'],
                                  '%s is dropped from done-when (%s); nothing more is spent' % (i['id'], str(i.get('text') or '').rstrip('.'))), kind='leave'))
    opts.append(dict(W.option(W.STOP_OPTION, 'Stop here', 'the department stops where it is; you can start it again later'), kind='stop'))
    return opts


def cannot_offer(ctx, cannot):
    """No line can be made (M6.4): an engine the kind requires cannot serve an item. Nothing is proposed and nothing
    registered; one conflict goes to Identity with the ways out, which the owner chooses between."""
    ref, d, pl = ctx['ref'], ctx['dept'], ctx['post']['payload']
    named = ', '.join(cannot.get('items') or [])
    why = ('%s cannot serve %s: %s' % (cannot.get('engine'), named, str(cannot.get('why') or '').strip().rstrip('.')))[:2000]
    line_conflict(ref, ctx['post']['thread'], why, options=cannot_options(d, cannot, pl.get('words')), engines=[], source='shaped', words=pl.get('words'))
    return {'said': 'could not make a line: %s; the conflict goes to Identity, with the ways out' % why, 'cannot': cannot}


def adapt_line_offer(ctx, step, item):
    """The line goes on. Each engine names the items it covers, and the proposal carries the map (M5.1). A made line
    (M6.4) is sent by how sure it is (J2B-7, S.CONFIDENCE): at 0.8 or more to Priority; from 0.6 to under 0.8 to Priority
    with the doubt shown and nobody asked; under 0.6 to Identity as a doubt, and nothing is registered. An answer of
    cannot is a conflict, with the ways out built by code."""
    ref, d, pl = ctx['ref'], ctx['dept'], ctx['post']['payload']
    src = ctx['bag'].get('adapt.source') or {'shape': True, 'source': 'shaped'}
    got = ctx['bag']['adapt.line'] if src.get('shape') else src
    if isinstance(got.get('cannot'), dict) and not got.get('engines'):
        return cannot_offer(ctx, got['cannot'])
    made = bool(src.get('shape')) and is_made(ctx)
    engines = (made_engines if made else covered_engines)(got['engines'])
    covers = with_covers(engines, d)
    body = {'word': 'line', 'engines': engines, 'source': src.get('source'), 'words': pl.get('words'), 'for': pl.get('for'), 'covers': covers}
    names = ' -> '.join(e['name'] for e in engines)
    if R._j2_live(ref):
        shown = None
        if made:
            low = min(engines, key=lambda e: e['confidence'])
            body['confidence'] = low['confidence']
            if low['confidence'] < S.CONFIDENCE['show_below']:
                shown = (low['name'], low.get('doubt') or '')
        if shown and body['confidence'] < S.CONFIDENCE['ask_below'] and hears_doubt():
            # not sure enough to go on: one question, and nothing is registered (the answer opens a new line request)
            doubt, fallback = split_doubt(shown[1])
            R.post(ref, 'Adaptation', 'Identity', 'inform', {'word': 'doubt', 'engine': shown[0], 'doubt': doubt or 'the plan rests on a fact or a decision nobody has given',
                                                            'fallback': fallback, 'confidence': body['confidence'], 'cannot': None,
                                                            'words': pl.get('words'), 'for': pl.get('for')})
            return {'said': 'was not sure of the line (%s -> doubt: %s) and asked Identity; nothing is registered' % (names, shown[0]),
                    'engines': engines, 'doubt': shown[0]}
        if shown:
            body['doubt'] = shown[1][:600]
        # J2 step 3: the proposal goes to Priority, on the board, in a thread of its own with the board's bounds
        body['why'] = 'the goal needs these workflows'
        R.post(ref, 'Adaptation', 'Priority', 'propose', body)
        return {'said': 'proposed the line to Priority: ' + names, 'engines': engines}
    body['why'] = 'the goal needs a line and the department was born with none'
    R.post(ref, 'Adaptation', 'Identity', 'propose', body)
    return {'said': 'shaped the line from the words: ' + names, 'engines': engines}


CODE = {name: ref_to(name) for name in (
    'hear', 'adapt_sense', 'adapt_ladder', 'adapt_act', 'adapt_trial', 'adapt_notrial', 'adapt_heard', 'adapt_park', 'adapt_offer',
    'adapt_priced', 'adapt_line_granted', 'adapt_line_refused', 'adapt_line_counter')}
CODE['adapt_source'] = adapt_source
CODE['adapt_line_offer'] = adapt_line_offer
PROMPT = {'adapt_shape': ref_to('p_adapt_shape'), 'adapt_line': p_adapt_line}
DRAFT = {'adapt_shape_draft': ref_to('d_adapt_shape'), 'adapt_line_draft': d_adapt_line}
CHECK = {name: ref_to('c_' + name) for name in (
    'counted_the_rows', 'moves_name_their_rows', 'said_what_it_did', 'facts_are_closed', 'idea_has_shapes')}
CHECK['line_is_engines'] = c_line_is_engines
WORDS, LAYOUT = {}, {}


def proposal_post(ref, prop):
    """The line Adaptation last proposed in the thread a proposal.created event names, as the board has it (its payload is
    act.line, with the covers); the latest one Adaptation proposed when the event names none."""
    mine = [x for x in R.board(ref) if x['src'] == 'Adaptation' and x['msg_type'] == 'propose' and (x.get('payload') or {}).get('word') == 'line']
    here = [x for x in mine if prop and x['thread'] == prop.get('proposal_ref')]
    return (here or mine or [None])[-1]


def coverage(ref, d, prop):
    """Which done-when items the latest proposal covers (M5.1): {items, uncovered, by}, or None when nothing was proposed.
    The covers are the proposal's own, by Adaptation; a proposal that names none (one made before covers) is read the way
    the workflow schema reads it, every item the last engine's, by default."""
    post = proposal_post(ref, prop) if prop else None
    if post is None:
        return None
    ids = [i['id'] for i in items_of(d)]
    covers = (post.get('payload') or {}).get('covers') or {}
    if not covers:
        return {'items': ids, 'uncovered': [], 'by': 'default'}
    return {'items': ids, 'uncovered': [i for i in ids if i not in covers], 'by': 'adaptation'}


def view(ref, d, events, asks):
    """Adaptation's pane (S.VIEWS['adaptation']): what it has always shown (the latest proposal, and the last Root reviews),
    with the coverage of that proposal (M5.1) and, on each review, the checks that ran, each with what the standard says,
    whether it held and why (M7.3). The words are the owner's: the bargain's inside words are put right on the way out."""
    import owner_words
    plain = owner_words.plain
    says = {i: text for i, text, _, _ in S.WORKFLOW_STANDARDS}
    prop = next((e for e in reversed(events or []) if e.get('action') == 'proposal.created'), None)
    reviews = [e for e in events or [] if e.get('action') in ('workflow.validated', 'workflow.blocked')][-4:]
    return {'proposal': prop and {'workflow': (prop.get('payload') or {}).get('workflow') or [],
                                  'source': (prop.get('payload') or {}).get('source'), 'at': prop.get('occurred_at')},
            'root_checks': [{'summary': plain(e.get('summary')), 'at': e.get('occurred_at'), 'passed': e.get('action') == 'workflow.validated',
                             'checks': [{'check': str(c.get('check'))[:60], 'says': plain(says.get(c.get('check')) or c.get('check'))[:300],
                                         'passed': bool(c.get('passed')), 'why': plain(c.get('why'))[:600]}
                                        for c in (e.get('payload') or {}).get('checks') or [] if isinstance(c, dict) and c.get('check')]}
                            for e in reviews],
            'coverage': coverage(ref, d, prop),
            'rounds': []}
