"""layers/adaptation/v1.py -- Adaptation, version 1: the implementation behind the interface's adaptation entries (PRD A1.18).

Its recipe is v1.json beside it: the Adaptation engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here (A1 step A1): by reference, to the body
engine_runtime still holds, until this layer moves one in to change it (move on touch, A1.19). The layer's words are
WORDS and LAYOUT below (A1.16), from the extractor and proved byte for byte against the .md bundle, which is now only the
fallback for a part no layer holds. view() returns the pane's read model.

W2-ADAPT (M5.2, M5.4, M9.1, M9.4, M9.6) adds to the same version, as additions and not a new version: adapt.fit fits the Library's
line to the goal (a note per engine, an engine left out only when the kind does not require it), the two handlers that hear
Priority's no and its ask for less copy the ways out Priority priced into the conflict, and the next round (adapt_hearnext,
adapt.next, adapt_round, and the two handlers for Priority's answer to it) proposes a correction on the registered line, never
the one that already failed, and keeps rounds.jsonl, which view() folds by round.
"""
import os
import re
import types
import unicodedata
import uuid

from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'adaptation'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'

#: what a required engine's check refuses, in the owner's words (J2B-2): Make is told, so it shapes nothing the check fails
REFUSES = (('Check', 'a page with a script, a link to no page, a page with almost no text, a page that breaks one of the owner\'s rules'),)


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


def adapt_source(ctx, step, item, make=None):
    """Where the proposal comes from (J2.b): the Library's template when the department's kind has one, else Adaptation
    shapes the line itself. A line Root's check refused is shaped again, whatever its first source was, unless the
    kind requires engines: then it is the Library's line again, with the engines the kind requires (_library_repair).
    With the make setting on (J2_ADAPT_MAKE), a default department's first line and a line Root sent back are made, not
    taken, and a shaped source (M6.3) also carries the practices in place (J2B-2): in the step's answer, and on the
    request as Adaptation holds it, for the step that shapes. `make` is the setting as this call reads it: the draft asks
    what the setting's absence would have taken (False), and nobody else says."""
    d, pl = ctx['dept'], ctx['post']['payload']
    make, faulted = make_on() if make is None else bool(make), bool(pl.get('faults'))
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
    if shape and make:
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


def fit_name(text):
    """A name as the interface's NAME_RE has it: letters, numbers, spaces and & ' . - only, the first a letter or a number,
    forty at most. A model names an engine 'Facts (web)' or 'Site: 2': the words are its and the characters are the
    interface's, so a character the interface refuses is a space and an accent is dropped ('Cafe' for 'Café'), before the
    line is judged and as it is posted. A name that fits is left as it is, its spaces run together as they always were."""
    kept = ''.join(' ' if not (ch.isascii() and (ch.isalnum() or ch in " &'.-")) else ch
                   for ch in unicodedata.normalize('NFKD', str(text or '')) if not unicodedata.combining(ch))
    return re.sub(r'^[^A-Za-z0-9]+', '', ' '.join(kept.split()))[:40]


def fit_engines(engs):
    """The engines a model answered, each name, reads and writes made to fit (fit_name) and everything else as it came, so
    the check judges the names the line will be posted with (norm_engines posts the same)."""
    return [dict(e, **{k: fit_name(e[k]) for k in ('name', 'reads', 'writes') if isinstance(e.get(k), str)}) if isinstance(e, dict) else e
            for e in engs]


def norm_engines(engs):
    """A line's engines as a proposal carries them (the form adapt_line_offer has always posted): a name of at most forty
    characters, made to fit what the interface lets a name hold (fit_name), what it does in two hundred, what it reads and
    writes, and whether it goes to the internet. Tolerant of what a model might answer, so the check can say what is
    wrong with it."""
    out = []
    for e in engs or []:
        e = e if isinstance(e, dict) else {}
        name = fit_name(e.get('name'))
        out.append({'name': name, 'does': ' '.join(str(e.get('does') or '').split())[:200],
                    'reads': fit_name(e.get('reads') or 'Brief'),
                    'writes': fit_name(e.get('writes') or name), 'internet': bool(e.get('internet'))})
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


def _said(x):
    """Whether a field a made engine must give is there: a string with something in it."""
    return isinstance(x, str) and bool(x.strip())


def made_notes(engs, d):
    """What is wrong with a made line beyond what a shaped one may be (J2B-4, J2B-6), one note each, in the owner-neutral
    words the other checks use: every field given (what it does, reads and writes, and whether it goes to the internet:
    norm_engines fills a missing one for the offline draft, but a made engine that leaves one out is a guess, and a
    missing reads would wire it to the Brief), a level 1 or 2 that code agrees with (an engine named after a shipped
    template is level 1 and keeps its reads and writes; any other is level 2), a confidence from 0 to 1 and a doubt
    below 0.8, covers that are known items, every item covered, every engine covering an item or feeding a later one,
    and every engine the kind requires there, at level 1."""
    notes, rows = [], [e for e in engs if isinstance(e, dict)]
    items, lib, names = [i['id'] for i in items_of(d)], shipped(), []
    covered = set()
    for e in rows:
        n = ' '.join(str(e.get('name') or '').split())[:40]
        names.append(n)
        level, conf = e.get('level'), e.get('confidence')
        given = {f: _said(e.get(f)) for f in ('does', 'reads', 'writes')}
        for field, note in (('does', '%s says nothing of what it does'), ('reads', '%s names nothing it reads'),
                            ('writes', '%s names nothing it writes')):
            if not given[field]:
                notes.append(note % n)
        if not isinstance(e.get('internet'), bool):
            notes.append('%s does not say whether it goes to the internet' % n)
        if isinstance(level, bool) or level not in (1, 2):
            notes.append('%s names no level, 1 or 2' % n)
        elif n in lib:
            if level != 1:
                notes.append('%s is an engine of the Library, so it is level 1' % n)
            elif given['reads'] and given['writes'] and (e['reads'], e['writes']) != (lib[n].get('reads'), lib[n].get('writes')):
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


#: the workflow schema's own row (S.validate_workflow's first): the line fits the form a workflow is kept in. It is no standard of
#: Root's, so owner_words has no id of it to leave out, and the notes say its faults as sentences
SHAPE_ROW = 'workflow_meets_standards'
NAME_USES = "letters, numbers, spaces and & ' . -"       # what a name may hold, NAME_RE in words


def shape_say(fault, rows):
    """One fault of the shape row ('<path>: <what is wrong>', the interface's own words) as a sentence the owner can read, by
    the engine's name: its name, what it reads or writes, or the items it covers. A fault with no sentence of its own says
    the plan does not fit the form it is kept in. The deliverable is the last engine's writes, and a key of the covers
    map is an item. The path and the pattern stay in the interface; fit_name has already made what can be made to fit."""
    path, _, why = str(fault).partition(': ')
    at = re.match(r'\$\.engines\[(\d+)\]\.(\w+)', path)
    i, field = (int(at.group(1)), at.group(2)) if at else ((len(rows) - 1, 'writes') if path == '$.deliverable' and rows else (None, None))
    who = (rows[i].get('name') or 'engine %d' % (i + 1)) if i is not None and i < len(rows) else 'the plan'
    if field in ('reads', 'writes') and i is not None and i < len(rows) and not rows[i].get('name'):
        field = 'name'                                    # an engine with no name, whose writes was to be its name, is told so once
    if field == 'name':
        return "%s's name may use only %s (at most 40 characters)" % (who, NAME_USES)
    if field in ('reads', 'writes'):
        return '%s names what it %s with only %s (at most 40 characters)' % (who, field, NAME_USES)
    if field == 'covers' or path.startswith('$.covers'):
        if why == 'holds an item twice':
            return '%s names an item twice' % who
        more = re.match(r'more than (\d+) items', why)
        return '%s names more than %s items' % (who, more.group(1)) if more else '%s names an item in a form done-when does not use' % who
    return '%s does not fit the form a plan is kept in' % who


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
    fitted = fit_engines(engs)                            # today's rules and J2B-4 judge the names the line will be posted with
    drafted = from_library(ctx, out)
    legacy = [] if drafted else R._line_notes(fitted)        # the Library's own names are not 'new to the Library'
    if made:
        # a level-1 engine is the Library's own, kept on its template: it is not 'new to the Library', and need not be
        lib = shipped()
        taken = {' '.join(str(e.get('name') or '').split())[:40] for e in fitted if isinstance(e, dict) and e.get('level') == 1 and e.get('name') in lib}
        legacy = [(c, n) for c, n in legacy if not (c == 'names new to the Library' and any(n == 'the Library already has an engine named %s' % t for t in taken))]
    notes = [n for _, n in legacy]
    if made:
        notes += [n for n in made_notes(fitted, d) if n not in notes]
    source = 'library' if drafted else (((ctx or {}).get('bag') or {}).get('adapt.source') or {}).get('source') or 'shaped'
    rows = made_engines(engs) if made else norm_engines(engs)      # the form the offer posts: what the workflow is judged as
    for row in S.validate_workflow(workflow_of(rows, source, d), 'proposal', d, {}):
        if row['passed']:
            continue                                      # a warning row passes
        for fault in str(row['why']).split('; '):
            if row['check'] == SHAPE_ROW:
                said = shape_say(fault, rows)             # the interface's path and pattern are not for the owner's card
                if said not in notes:
                    notes.append(said)
                continue
            named = '%s: %s' % (row['check'], fault)
            if fault in notes:
                notes[notes.index(fault)] = named        # today's wording, now naming the standard it breaks
            elif named not in notes:
                notes.append(named)
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


def library_draft(ctx):
    """The Library's line, when the setting is on and no agent is there to shape one (J2B-9: a default department keeps Do):
    what the setting's absence would have taken, which adapt_source reads as a Library line, else None. A default
    department's first line is Do, and a website Root sent back has the Library's line again with the Check its kind
    requires (_library_repair); a kind with no line, or a line sent back for a kind that requires nothing, has no such line,
    and its draft is the two engines below."""
    if not make_on() or not (ctx or {}).get('dept'):
        return None
    got = adapt_source(dict(ctx, post=ctx.get('post') or {'payload': {}}), None, None, make=False)
    return None if got['shape'] else {'engines': got['engines'], 'source': 'library'}


def from_library(ctx, out):
    """Whether the answer in hand is the Library's line, taken by the offline draft (library_draft): an agent's own answer
    is never taken for one, whatever it says its source is."""
    return isinstance(out, dict) and out.get('source') == 'library' and ((ctx or {}).get('how') or {}).get('adapt.line') == 'offline draft'


def d_adapt_line(ctx, step, item):
    """The draft, when no agent is there to judge: two engines, the facts from the internet and the site from the facts.
    Their names are ones the Library does not have yet: a second department shaped this way takes Facts 2 and Site 2
    (found 2026-10-07: it took Facts and Site again, its check refused the line, and nothing was said). The site, the last
    engine, covers every done-when item (M5.1); the draft carries no confidence and asks no question (J2B-9). With the make
    setting on, a department the Library has a line for keeps it: a default department's Do, a website's line repaired with
    its Check (library_draft), not a site for a document or a plan with no Check."""
    kept = library_draft(ctx)
    if kept:
        return kept

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


def kind_line(ctx):
    """The names of the line the fit starts from (M5.2): the engines adapt.source took, the department's own or its kind's, in
    the order the Library runs them."""
    src = ((ctx or {}).get('bag') or {}).get('adapt.source') or {}
    return [str(e.get('name')) for e in src.get('engines') or [] if isinstance(e, dict) and e.get('name')]


def p_adapt_fit(ctx, step, item):
    """The prompt that fits the Library's line to the goal (adapt.fit): the typed part make.fit (A1-FIT), given the line as the
    Library has it, each engine with what it reads and writes, and the ones this kind of department requires marked."""
    d, pl = ctx['dept'], ctx['post']['payload']
    required = R.required_engines(d)
    lines = ['- %s%s (reads %s, writes %s): %s' % (e['name'], ' [required: it stays]' if e['name'] in required else '', e.get('reads') or 'Brief',
                                                   e.get('writes') or e['name'], e.get('does') or 'no description')
             for e in ((ctx['bag'].get('adapt.source') or {}).get('engines') or []) if isinstance(e, dict) and e.get('name')]
    rules = '; '.join(str(r.get('line')) for r in d.get('rules') or [] if r.get('line'))
    return R._prompt('adaptation', 'make', 'fit', ctx['ref'], dept=d.get('name'), words=pl.get('words') or d.get('goal'),
                     items=item_lines(d), engines='\n'.join(lines) or 'none', rules=rules or 'none')


def d_adapt_fit(ctx, step, item):
    """The draft, when no agent is there to fit the line: the kind's line as it is, every engine and no note."""
    return {'engines': kind_line(ctx), 'fit': {}, 'why': "no agent was there to fit the line, so the Library's line stands as it is"}


def c_line_is_fitted(ctx, step, item, out):
    """A fitted line is an in-order subsequence of the kind's line that holds every engine the kind requires (M5.2: Adaptation
    may leave out an engine that is not required, and nothing else). Refused: an engine that is not in the kind's line, one
    named twice, a changed order, a required engine left out, a note for an engine the fitted line does not have, and a note
    over 300 characters. Whether the engines left read each other is Root's standards' to say at the proposal and at the
    registration, not this check's."""
    base = kind_line(ctx)
    engs = out.get('engines') if isinstance(out, dict) else None
    if not base:
        return R._verdict(False, '', "there is no line of the kind's to fit")
    if (((ctx or {}).get('post') or {}).get('payload') or {}).get('faults'):
        # Root's check sent the last line back (or this step failed once): the Library's line is taken whole (fitted()), so
        # a fit that is not sound cannot stop the department from getting its line; the repair always converges
        return {'ok': True, 'notes': ["the last line was sent back, so the Library's line is taken whole and nothing is fitted"]}
    if not isinstance(engs, list) or not engs or any(not isinstance(n, str) or not n.strip() for n in engs):
        return R._verdict(False, '', "the engines to run are named, as a list of names")
    names, notes = [' '.join(n.split()) for n in engs], []
    twice = [n for n in dict.fromkeys(names) if names.count(n) > 1]
    if twice:
        notes.append('%s named more than once' % R._names(twice))
    foreign = [n for n in dict.fromkeys(names) if n not in base]
    if foreign:
        notes.append("%s %s not in the kind's line (%s)" % (R._names(foreign), 'is' if len(foreign) == 1 else 'are', ' -> '.join(base)))
    known = [n for n in dict.fromkeys(names) if n in base]
    if [base.index(n) for n in known] != sorted(base.index(n) for n in known):
        notes.append("the Library's order is changed: it runs %s" % ' -> '.join(base))
    gone = [n for n in R.required_engines((ctx or {}).get('dept')) if n in base and n not in names]
    if gone:
        notes.append('the line leaves out %s, which this kind of department requires' % R._names(gone))
    fit = out.get('fit', {})
    if not isinstance(fit, dict):
        notes.append('fit is a note for each engine that needs one, as an object')
    else:
        stray = [str(k) for k in fit if k not in names]
        if stray:
            notes.append('fit has a note for %s, which is no engine of the line' % R._names(stray))
        for k, v in fit.items():
            if not isinstance(v, str):
                notes.append('the note for %s is not words' % k)
            elif len(v.strip()) > 300:
                notes.append('the note for %s is %d characters; at most 300' % (k, len(v.strip())))
    left = [n for n in base if n not in names]
    return {'ok': not notes, 'notes': notes or ["%d of %d engines, in the Library's order%s" % (len(names), len(base),
                                                (', leaving out ' + R._names(left)) if left else '')]}


def fitted(ctx, src):
    """The Library's line as adapt.fit left it (M5.2): the engines it kept, in the Library's order, each with its note
    (`fit`). The line whole when there is nothing to carry: a shaped source, a skipped step, and a line Root's check sent
    back (`faults` on the request), which is taken again whole, as the repair of a refused line has always been."""
    fit = ((ctx or {}).get('bag') or {}).get('adapt.fit')
    pl = (((ctx or {}).get('post') or {}).get('payload')) or {}
    if src.get('shape') or src.get('source') != 'library' or pl.get('faults') or not isinstance(fit, dict):
        return src
    keep = {' '.join(str(n).split()) for n in fit.get('engines') or [] if isinstance(n, str)}
    rows = [dict(e) for e in src.get('engines') or [] if e.get('name') in keep]
    if not rows:
        return src
    notes = {k: ' '.join(v.split()) for k, v in (fit.get('fit') if isinstance(fit.get('fit'), dict) else {}).items()
             if isinstance(v, str) and v.strip() and k in {e['name'] for e in rows}}
    return dict(src, engines=rows, fit=notes, left_out=[e['name'] for e in src.get('engines') or [] if e.get('name') not in keep])


# ---- the next round (W2-ADAPT: M9.1 the round, M9.4 never the same twice, M9.6 the rounds) ---------------------------------
#: a round's statuses, in the order it passes through them (adaptation.round): proposed to Priority, granted or refused by it,
#: filed in the Brief by Identity, read by Audit. Adaptation writes the first three; the others are Identity's and Audit's to
#: move on the record they own, and the fold takes whatever the latest row says.
RAN = ('granted', 'filed', 'read')           # a round that ran: the approach it named was tried
#: what a round says is at most this long (adaptation.round correction); the model's own words are cut to it, never refused for it
SAYS = 600


def clip(text, n=SAYS):
    return ' '.join(str(text or '').split())[:n]


def words_of(text):
    """The words of a line as the repeat guard compares them: lower case, letters and digits only, in order."""
    return ' '.join(re.findall(r'[a-z0-9]+', str(text or '').lower()))


def cycle_of(ref):
    """The cycle the department is in (J2): its id, or None when it has none."""
    try:
        return (J._state(ref) or {}).get('cycle_id')
    except Exception:  # noqa: BLE001 -- no cycle to read: the rounds are the department's own
        return None


def all_rounds(ref):
    """rounds.jsonl folded by round, the latest row of each round winning (M9.6). Rounds of two cycles are two rounds: the
    number starts again with the cycle."""
    folded = {}
    try:
        rows = W.rows(ref, 'rounds.jsonl')
    except (ValueError, OSError):
        rows = []
    for r in rows:
        if isinstance(r, dict) and isinstance(r.get('round'), int) and not isinstance(r.get('round'), bool):
            key = (r.get('cycle_id'), r['round'])
            folded[key] = dict(folded.get(key, {}), **r)
    return list(folded.values())


def rounds_of(ref):
    """The rounds of the cycle the department is in, oldest first; the department's whole record when it has no cycle."""
    cur = cycle_of(ref)
    return sorted((r for r in all_rounds(ref) if cur is None or r.get('cycle_id') == cur), key=lambda r: r['round'])


def failed_round(ref, ids):
    """The latest round that ran for any of these items and did not put them right (M9.4): the reading that asked for the next
    round found them still not met, so the correction it named is the last approach that failed. A round Priority would not pay
    for never ran, so its approach did not fail."""
    for r in reversed(rounds_of(ref)):
        if r.get('status') in RAN and set(r.get('covers') or []) & set(ids):
            return r
    return None


def next_number(ref, pl):
    """The number of the round now asked for: one after the latest of this cycle that Priority did not refuse, or the number
    Identity gave when that is later. A round Priority would not pay for never ran, so it keeps its number: asked for again once
    the ceiling holds it, it is the same round and funded, not a round past the ceiling that is refused again (M9.1, M9.2)."""
    n = max([r['round'] for r in rounds_of(ref) if r.get('status') != 'refused'] or [0]) + 1
    given = pl.get('round')
    if isinstance(given, int) and not isinstance(given, bool) and 1 <= given <= 99:
        n = max(n, given)
    return min(n, 99)


def reading_of(ref, rid=None):
    """The reading a request names (readings.jsonl, by its id); the latest one when it names none; None when Audit has filed none."""
    try:
        rows = [r for r in W.rows(ref, 'readings.jsonl') if isinstance(r, dict)]
    except (ValueError, OSError):
        rows = []
    if rid:
        return next((r for r in reversed(rows) if r.get('id') == rid), None)
    return rows[-1] if rows else None


def line_estimate(ref):
    """Priority's observed cost of the line (M9.1): the estimate on the latest price row for a line, the cost it read from the
    runs that finished. Nothing observed is a zero with the basis 'prior': Priority prices the round itself all the same."""
    try:
        rows = [r for r in W.rows(ref, 'prices.jsonl') if isinstance(r, dict) and r.get('proposal') == 'line' and isinstance(r.get('estimate'), dict)]
    except (ValueError, OSError):
        rows = []
    return dict(rows[-1]['estimate']) if rows else {'calls': 0, 'usd': 0.0, 'basis': 'prior', 'runs': 0}


def adapt_hearnext(ctx, step, item):
    """Adaptation hears Identity ask for the next round (M9.1): which of the items it names are in done-when and what the reading
    said of each, what Audit found about them, the line that ran, the number of this round and the last approach that failed
    for the same items. The unit starts with code: closed facts."""
    ref, d, p = ctx['ref'], ctx['dept'], ctx['post']
    pl = p.get('payload') or {}
    mine = {i['id']: i for i in items_of(d)}
    ids = [i for i in dict.fromkeys(pl.get('items') or []) if isinstance(i, str) and i in mine]
    reading = reading_of(ref, pl.get('reading'))
    said = {r['id']: r for r in (reading or {}).get('items') or [] if isinstance(r, dict) and r.get('id')}
    items = [{'id': i, 'text': clip(mine[i].get('text'), 300), 'claim': clip((said.get(i) or {}).get('claim'), 300)} for i in ids]
    asked = set(x for x in pl.get('findings') or [] if isinstance(x, str))
    findings = [{'id': f['id'], 'severity': f.get('severity'), 'claim': clip(f.get('claim'), 300), 'where': clip(f.get('where'), 120), 'item': f.get('item')}
                for f in (reading or {}).get('findings') or [] if isinstance(f, dict) and f.get('id') and (f['id'] in asked or f.get('item') in ids)]
    last = failed_round(ref, ids)
    n = next_number(ref, pl)
    out = R.hear(ctx, step, item)
    out['facts'].update({'items': ' '.join(ids), 'repeat': bool(last)})
    wf = (d or {}).get('workflows') or []
    out.update({'items': items, 'findings': findings, 'round': n, 'reading': (reading or {}).get('id') or (str(pl.get('reading'))[:40] if pl.get('reading') else None),
                'line': list((wf[-1] if wf else {}).get('engines') or (d or {}).get('engines') or []),
                'last': {'round': last['round'], 'correction': last.get('correction')} if last else None,
                'said': ('heard that %s does not hold; round %d to propose%s' % (', '.join(ids), n, ' (the last approach failed)' if last else '')) if ids
                else 'heard a request for a round naming no item that done-when has'})
    return out


def p_adapt_next(ctx, step, item):
    """The prompt that says what to correct (adapt.next): the typed part decide.next (A1-NEXT), given the items that do not hold
    with what the reading said of each, what Audit found, the line that ran and, when the same items failed a round already,
    the approach that failed."""
    heard = ctx['bag']['adapt.hearnext']
    items = '\n'.join('%s: %s%s' % (i['id'], i['text'], (' (what the reading says: %s)' % i['claim']) if i['claim'] else '') for i in heard['items']) or 'none'
    found = '\n'.join('%s (%s)%s: %s' % (f['id'], f.get('severity') or 'medium', (', ' + f['where']) if f.get('where') else '', f['claim'])
                      for f in heard['findings']) or 'none'
    last = ('the last approach failed: %s' % heard['last']['correction']) if heard.get('last') else 'none yet; this is the first round for these items'
    return R._prompt('adaptation', 'decide', 'next', ctx['ref'], dept=ctx['dept'].get('name'), items=items, findings=found,
                     line=' -> '.join(heard.get('line') or []) or 'none', last=last)


def d_adapt_next(ctx, step, item):
    """The draft, when no agent is there to say what to correct: the items that do not hold and what Audit found of them, put as
    a correction. When the same items failed a round already it is another try, numbered, so it is never the approach that
    failed (M9.4)."""
    heard = ctx['bag']['adapt.hearnext']
    ids = [i['id'] for i in heard['items']]
    tried = len([r for r in rounds_of(ctx['ref']) if r.get('status') in RAN and set(r.get('covers') or []) & set(ids)])
    what = '; '.join('%s: %s' % (i['id'], i['text'].rstrip('.')) for i in heard['items']) or 'what the reading found'
    found = '; '.join(dict.fromkeys(f['claim'].rstrip('.') for f in heard['findings'] if f['claim']))
    text = 'Put right %s' % what + ('. Audit found: %s' % found if found else '')
    if tried:
        text = 'Try another way, attempt %d. %s. The last approach did not put it right' % (tried + 1, text)
    return {'correction': clip(text), 'fixes': [f['id'] for f in heard['findings']], 'covers': ids,
            'why': 'the reading found %s not met' % (', '.join(ids) or 'an item')}


#: how the covering of a correction begins its reason when the correction repeats the approach that already failed; next_failed reads it back
REPEATS = 'this is the approach that already failed in round '


def c_round_is_new(ctx, step, item, out):
    """A round says what to correct, and says something new (M9.4): a correction equal, word for word, to the one that already
    failed for the same items is refused, naming the round it repeats. What a reading found that no correction answers is
    Identity's to put to the owner, never a round that does it again."""
    heard = ((ctx or {}).get('bag') or {}).get('adapt.hearnext') or {}
    text = out.get('correction') if isinstance(out, dict) else None
    if not isinstance(text, str) or not words_of(text):
        return R._verdict(False, '', 'a round says what to correct')
    last = heard.get('last') or {}
    if last and words_of(text) == words_of(last.get('correction')):
        return R._verdict(False, '', '%s%s (%s); a round says something new' % (REPEATS, last.get('round'), clip(last.get('correction'), 120)))
    named = ', '.join(i['id'] for i in heard.get('items') or []) or 'these items'
    return R._verdict(True, 'a correction that is new for %s' % named, '')


def hears_round():
    """Whether Identity's recipe has a handler for a granted round (A1.14: an act is posted only to a receiver that hears it)."""
    return R._handler(R.engine_def('Identity'), {'msg_type': 'inform', 'payload': {'word': 'round'}}) is not None


def adapt_round(ctx, step, item):
    """The round goes to Priority (M9.1): one propose/round with the correction, the findings it fixes, the items it covers and
    the line's observed cost, in a thread of its own with the board's bounds, and a row in rounds.jsonl, proposed. A round is a
    correction on the line that is registered; it never registers a line. The same reading asked twice is one round."""
    ref, heard, got = ctx['ref'], ctx['bag']['adapt.hearnext'], ctx['bag']['adapt.next']
    ids = [i['id'] for i in heard['items']]
    if not ids:
        return {'said': 'no item the request names is in done-when, so there is no round to propose'}
    reading = heard.get('reading')
    twice = next((r for r in rounds_of(ref) if reading and r.get('reading') == reading and r.get('status') in ('proposed',) + RAN), None)
    if twice:
        return {'said': 'round %d is already with Priority for this reading' % twice['round'], 'round': twice['round']}
    known = {f['id'] for f in heard['findings']}
    covers = [c for c in dict.fromkeys(got.get('covers') or []) if c in ids] or ids
    fixes = [f for f in dict.fromkeys(got.get('fixes') or []) if f in known]
    thread = 'x-' + uuid.uuid4().hex[:8]
    row = {'schema_version': 1, 'round': heard['round'], 'at': W.now(), 'cycle_id': cycle_of(ref), 'correction': clip(got['correction']),
           'fixes': fixes, 'covers': covers, 'estimate': line_estimate(ref), 'status': 'proposed', 'thread': thread}
    if reading:
        row['reading'] = str(reading)[:40]
    W.append_row(ref, 'rounds.jsonl', row)
    body = {'word': 'round', 'round': row['round'], 'correction': row['correction'], 'fixes': fixes, 'covers': covers, 'estimate': row['estimate'],
            'why': clip(got.get('why')) or 'the reading found %s not met' % ', '.join(covers)}
    if R.post(ref, 'Adaptation', 'Priority', 'propose', body, thread=thread) is None:
        round_bound(ref, thread, 'hops')           # refused on the record, and told to Identity unless the runtime did when it closed the thread
        return {'said': 'round %d could not go to Priority: the bargain reached its bound' % row['round'], 'round': row['round']}
    return {'said': 'proposed round %d to Priority: %s' % (row['round'], row['correction']), 'round': row['round']}


def round_of_thread(ref, thread):
    return next((r for r in reversed(all_rounds(ref)) if r.get('thread') == thread), None)


#: how a round that reached a limit of its thread is put to the owner (the limit is rule 12's: hops, time or spend), by the limit
BOUND_SAYS = {'seconds': 'Priority had not priced round %d in time', 'usd': 'pricing round %d cost more than it may',
              'hops': 'Priority and Adaptation could not settle round %d between them'}


def round_bound(ref, thread, which):
    """A round's thread was closed at its bound (rule 12; M9.5): the round does not stay proposed for good and does not go quiet.
    The row says refused, so the same reading asked again proposes again, and one conflict goes to Identity with the ways out
    built by code (next_options), once its recipe hears a round. Coordination calls it where it closes the thread (engine_runtime)
    and adapt_round where its own post is stopped. Idempotent: a thread's conflict is filed once. Never raises."""
    try:
        row = round_of_thread(ref, thread)
        if not row:
            return None
        if row.get('status') == 'proposed':
            row = W.append_row(ref, 'rounds.jsonl', dict(row, status='refused', at=W.now()))
        if not hears_round():
            return None
        why = BOUND_SAYS.get(which, 'round %d did not go on in time') % row['round']
        return line_conflict(ref, thread, why, bound=which, src='Coordination', options=next_options(W.dept(ref) or {}, row.get('covers') or []),
                             engines=[], extra={'round': row['round'], 'correction': row['correction']})
    except Exception:  # noqa: BLE001 -- the thread is closed and the round is on the record whether or not the word reached Identity
        return None


def adapt_round_granted(ctx, step, item):
    """Priority said yes to the round (M9.1): the row says granted, and Identity is told to file it as a correction to the Brief.
    A round is never filed by Adaptation, and Identity is told only once its recipe hears a round."""
    ref, p = ctx['ref'], ctx['post']
    row = round_of_thread(ref, p['thread'])
    if not row:
        return {'said': 'heard Priority on a round nobody proposed'}
    if row.get('status') != 'proposed':
        return {'said': 'round %d was already %s' % (row['round'], row.get('status')), 'round': row['round']}
    row = W.append_row(ref, 'rounds.jsonl', dict(row, status='granted', at=W.now()))
    if not hears_round():
        return {'said': 'Priority said yes to round %d; Identity does not take rounds yet, so it stays on the record' % row['round'], 'round': row['round']}
    why = clip((p.get('payload') or {}).get('why')) or 'Priority said yes'
    R.post(ref, 'Adaptation', 'Identity', 'inform', {'word': 'round', 'round': row['round'], 'correction': row['correction'], 'fixes': row.get('fixes') or [],
                                                     'covers': row.get('covers') or [], 'estimate': row.get('estimate') or line_estimate(ref), 'why': why,
                                                     'for': p['thread']})
    return {'said': 'Priority said yes to round %d; Identity is told to file it' % row['round'], 'round': row['round']}


def adapt_round_refused(ctx, step, item):
    """Priority said no to the round (M9.1, M5.4): the row says refused, and it does not go quiet. Identity gets the conflict with
    the ways out Priority priced, once its recipe hears a round, and puts it to the owner."""
    ref, p = ctx['ref'], ctx['post']
    pl = p.get('payload') or {}
    row = round_of_thread(ref, p['thread'])
    if not row:
        return {'said': 'heard Priority on a round nobody proposed'}
    why = clip(pl.get('why'), 300).rstrip('.') or 'no room for it'
    if row.get('status') == 'proposed':
        row = W.append_row(ref, 'rounds.jsonl', dict(row, status='refused', at=W.now()))
    if not hears_round():
        return {'said': 'Priority said no to round %d (%s); Identity does not take rounds yet, so it stays on the record' % (row['round'], why), 'round': row['round']}
    line_conflict(ref, p['thread'], 'Priority said no to round %d: %s' % (row['round'], why), options=options_of(pl), engines=[],
                  extra={'round': row['round'], 'correction': row['correction']})
    return {'said': 'Priority said no to round %d (%s); the conflict goes to Identity, with the ways out' % (row['round'], why), 'round': row['round']}


def next_options(d, ids):
    """The ways out when no round can be said that is new, built by code: the owner's own words, which go into the Brief; leave the
    item out, when done-when has another to keep; stop."""
    opts = [W.option(W.WORDS_OPTION, 'Say how to put it right', 'your words go into the Brief and the line runs again; no round is paid for')]
    items = items_of(d)
    named = next((i for i in items if i['id'] in ids), None)
    if len(items) > 1 and named:
        opts.append(W.option('leave:' + named['id'], 'Leave %s out' % named['id'],
                             '%s is dropped from done-when (%s); nothing more is spent' % (named['id'], str(named.get('text') or '').rstrip('.'))))
    opts.append(W.option(W.STOP_OPTION, 'Stop here', 'the department stops where it is; you can start it again later'))
    return opts


def next_reason(ref, ids, note):
    """Why there is no new round, in words the owner reads (M9.4): the approach that already failed, when that is what the
    covering refused; otherwise that nothing Adaptation could say was new. Never the run's note, which starts with the name of the
    step and holds the covering's inside words."""
    last = failed_round(ref, ids)
    if last and REPEATS in str(note):
        return 'its only idea is the approach that already failed in round %s' % last['round']
    return 'nothing it could say was new'


def next_failed(ref, d, p, note):
    """The step that says what to correct failed (M9.4): its covering refused the correction because it is the approach that
    already failed, or no answer fitted. Nothing is proposed and nothing goes quiet: one conflict goes to Identity, with the ways
    out built by code, once its recipe hears a round. It names the round and carries no correction, which is how Identity knows no
    round was proposed. engine_runtime calls it when the run of a request for the next round fails. Never raises."""
    try:
        if not hears_round():
            return None
        pl = p.get('payload') or {}
        ids = [i for i in pl.get('items') or [] if isinstance(i, str)]
        why = 'Adaptation has no new way to put %s right: %s' % (', '.join(ids) or 'the items', next_reason(ref, ids, note))
        return line_conflict(ref, p['thread'], why[:2000], options=next_options(d, ids), engines=[], extra={'round': next_number(ref, pl)})
    except Exception:  # noqa: BLE001 -- the failed run is a row whether or not the word reached Identity
        return None


def with_covers(engines, d, made=False):
    """Each engine's covers made known and whole (M5.1), and the map of item to engines the proposal carries. Only items
    done-when has stay. Every item no engine names goes to the last engine, as code does for a Library line: a line that
    is not made was never asked for covers, so one that names some has not said the rest are uncovered, and Root's check
    would refuse the line on every reshape. A made line is held to every item by its own check (made_notes), so what its
    engines name is what the proposal carries."""
    ids = [i['id'] for i in items_of(d)]
    for e in engines:
        e['covers'] = [c for c in dict.fromkeys(e.get('covers') or []) if c in ids]
    left = [i for i in ids if not any(i in e['covers'] for e in engines)]
    if left and engines and not made:
        engines[-1]['covers'] = [i for i in ids if i in engines[-1]['covers'] or i in left]
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


def line_conflict(ref, thread, why, bound=None, src='Adaptation', options=None, engines=None, source=None, words=None, extra=None):
    """The bargain did not close (a refusal, or its bound), or no line can be made: it goes to Identity, never silently to
    nothing (J2.2). _line_conflict as engine_runtime has it, with the ways out Adaptation can build (M6.4) or Priority priced (M5.4);
    a conflict raised at a bound that is given none carries the ways Priority prices for a limit (R._limit_ways), as the one the
    runtime raises where it closes the thread does."""
    offer = R._line_proposal(ref, thread) or {}
    if any((x.get('payload') or {}).get('word') == 'conflict' and (x.get('payload') or {}).get('for') == thread for x in R.board(ref)):
        return None
    if bound and not options:
        options = R._limit_ways(ref, thread) or None
    body = {'word': 'conflict', 'engines': engines if engines is not None else offer.get('engines') or [],
            'source': source or offer.get('source'), 'words': words if words is not None else offer.get('words'),
            'why': why, 'bound': bound, 'for': thread}
    if options:
        body['options'] = options
    body.update(extra or {})
    return R.post(ref, src, 'Identity', 'inform', body)


def options_of(payload):
    """The ways out Priority sent with a no or an ask for less (M5.4), as the conflict carries them: at most three, each an
    option the interface types. None when Priority sent none, or sent what is not an option: a way out that does not fit is
    never put to the owner."""
    got = (payload or {}).get('options')
    if not isinstance(got, list):
        return None
    out = [dict(o) for o in got if isinstance(o, dict) and not S.validate('option', o)][:S.OPTIONS_MAX]
    return out or None


def adapt_line_refused(ctx, step, item):
    """Priority said no to the line: Adaptation does not drop it in silence; Identity closes the conflict (step 4), with the
    ways out Priority priced when it sent them (M5.4). Moved from engine_runtime.adapt_line_refused."""
    ref, p = ctx['ref'], ctx['post']
    pl = p.get('payload') or {}
    why = str(pl.get('why') or 'no room in the envelope').strip().rstrip('.')
    line_conflict(ref, p['thread'], 'Priority said no to the plan: %s' % why, options=options_of(pl))
    return {'said': 'Priority said no to the line (%s); the conflict goes to Identity' % why}


def adapt_line_counter(ctx, step, item):
    """Priority asked for less: Adaptation takes that when it leaves a line that still works, and proposes that line
    again in the same thread, each kept engine with its note; what it cannot take goes to Identity, with the ways out
    Priority sent (M5.4). The thread's own bound ends a bargain that will not close. Moved from engine_runtime.adapt_line_counter."""
    ref, p = ctx['ref'], ctx['post']
    pl = p.get('payload') or {}
    offer = R._line_proposal(ref, p['thread']) or {}
    keep = [str(k) for k in pl.get('keep') or []]
    engines = [e for e in offer.get('engines') or [] if e.get('name') in keep]
    why = str(pl.get('why') or 'the envelope has no room for all of it').strip().rstrip('.')
    options = options_of(pl)
    # a counter that drops an engine the kind requires is never taken: Identity closes it (PRD M4.4)
    proposed = [e.get('name') for e in offer.get('engines') or []]
    dropped = [n for n in R.required_engines(ctx['dept']) if n in proposed and n not in keep]
    if dropped:
        line_conflict(ref, p['thread'], 'Priority asked for less (%s) and the line would leave out %s, which this kind of department requires'
                      % (why, R._names(dropped)), options=options)
        return {'said': "could not take Priority's ask for less: it leaves out %s, which is required; the conflict goes to Identity" % R._names(dropped)}
    if not engines or len(engines) == len(offer.get('engines') or []) or R._root_check(ref, ctx['dept'], engines, offer.get('source') or 'shaped'):
        line_conflict(ref, p['thread'], 'Priority asked for less (%s) and the line does not work that way' % why, options=options)
        return {'said': "could not take Priority's ask for less; the conflict goes to Identity"}
    body = {'word': 'line', 'engines': engines, 'source': offer.get('source'), 'words': offer.get('words'), 'for': offer.get('for'),
            'why': "took Priority's ask for less: " + why}
    notes = {e['name']: e['fit'] for e in engines if e.get('fit')}          # M5.2: a kept engine keeps its note
    if notes:
        body['fit'] = notes
    row = R.post(ref, 'Adaptation', 'Priority', 'propose', body, thread=p['thread'])
    if row is None:
        # the thread reached its bound with this post. The runtime raised the conflict where it closed the thread, with the ways
        # Priority prices for a limit (R._line_conflict), and this files it only where it did not (a department off J2), the same
        # and once: line_conflict keeps to one conflict for a thread. Priority's ask for less is no limit, so it brings no ways
        # of its own to a bound.
        line_conflict(ref, p['thread'], 'the bargain reached its bound', bound='hops', src='Coordination')
        return {'said': 'the bargain reached its bound; it goes to Identity'}
    return {'said': "took Priority's ask for less and proposed again: " + ' -> '.join(e['name'] for e in engines)}


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
    with the doubt shown and nobody asked; under 0.6 to Identity as a doubt, and nothing is registered, unless Identity
    has asked what it can and sent the request marked go_on (act.line_request): then the line goes to Priority with the
    doubt named, as for a confidence from 0.6 to under 0.8, and Adaptation does not doubt again. An answer of cannot is
    a conflict, with the ways out built by code."""
    ref, d, pl = ctx['ref'], ctx['dept'], ctx['post']['payload']
    src = ctx['bag'].get('adapt.source') or {'shape': True, 'source': 'shaped'}
    got = ctx['bag']['adapt.line'] if src.get('shape') else fitted(ctx, src)
    if isinstance(got.get('cannot'), dict) and not got.get('engines'):
        return cannot_offer(ctx, got['cannot'])
    made = bool(src.get('shape')) and is_made(ctx)
    engines = (made_engines if made else covered_engines)(got['engines'])
    covers = with_covers(engines, d, made)
    kept = got if got is not src and not src.get('shape') else {}                      # the Library's line, fitted (M5.2)
    notes = kept.get('fit') or {}
    for row in engines:
        if notes.get(row['name']):
            row['fit'] = notes[row['name']]
    source = 'library' if from_library(ctx, got) else src.get('source')
    body = {'word': 'line', 'engines': engines, 'source': source, 'words': pl.get('words'), 'for': pl.get('for'), 'covers': covers}
    if notes:
        body['fit'] = dict(notes)
    names = ' -> '.join(e['name'] for e in engines)
    if notes or kept.get('left_out'):
        names += ' (fitted to the goal%s%s)' % ((', leaving out ' + R._names(kept['left_out'])) if kept.get('left_out') else '',
                                                (', %d note%s' % (len(notes), '' if len(notes) == 1 else 's')) if notes else '')
    if R._j2_live(ref):
        shown = None
        if made:
            low = min(engines, key=lambda e: e['confidence'])
            body['confidence'] = low['confidence']
            if low['confidence'] < S.CONFIDENCE['show_below']:
                shown = (low['name'], low.get('doubt') or '')
        if shown and body['confidence'] < S.CONFIDENCE['ask_below'] and not pl.get('go_on') and hears_doubt():
            # not sure enough to go on: one question, and nothing is registered (the answer opens a new line request)
            doubt, fallback = split_doubt(shown[1])
            says = {'word': 'doubt', 'engine': shown[0], 'doubt': doubt or 'the plan rests on a fact or a decision nobody has given',
                    'confidence': body['confidence'], 'cannot': None, 'words': pl.get('words'), 'for': pl.get('for')}
            if fallback:
                says['fallback'] = fallback           # a doubt that names none leaves the key out: Identity goes on with its default
            R.post(ref, 'Adaptation', 'Identity', 'inform', says)
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
    'adapt_priced', 'adapt_line_granted')}
CODE['adapt_source'] = adapt_source
CODE['adapt_line_offer'] = adapt_line_offer
CODE['adapt_line_refused'] = adapt_line_refused
CODE['adapt_line_counter'] = adapt_line_counter
CODE.update({'adapt_hearnext': adapt_hearnext, 'adapt_round': adapt_round, 'adapt_round_granted': adapt_round_granted,
             'adapt_round_refused': adapt_round_refused})
PROMPT = {'adapt_shape': ref_to('p_adapt_shape'), 'adapt_line': p_adapt_line, 'adapt_fit': p_adapt_fit, 'adapt_next': p_adapt_next}
DRAFT = {'adapt_shape_draft': ref_to('d_adapt_shape'), 'adapt_line_draft': d_adapt_line, 'adapt_fit_draft': d_adapt_fit,
         'adapt_next_draft': d_adapt_next}
CHECK = {name: ref_to('c_' + name) for name in (
    'counted_the_rows', 'moves_name_their_rows', 'said_what_it_did', 'facts_are_closed', 'idea_has_shapes')}
CHECK['line_is_engines'] = c_line_is_engines
CHECK['line_is_fitted'] = c_line_is_fitted
CHECK['round_is_new'] = c_round_is_new
# Adaptation: WORDS and LAYOUT by the split rule of A1.16, from function-prompts/adaptation/*.md
WORDS = {
    'goal': {
        'does': {
            'text': (
                'decides how the department reaches its goal and keeps changing how as it learns: it proposes the '
                "workflows the goal needs, from the Library or shaped fresh, and a step's move up or down the "
                'ladder'
            ),
        },
        'skills': {
            'items': [
                'count from the rows',
                'keep the ladder',
                'propose a change',
                'shape a new idea and park it',
            ],
        },
    },
    'sense': {
        'shape': {},
    },
    'decide': {
        # M9.1 (A1-NEXT): the words of the part adapt.next reads after a reading that is not done
        'next': {
            'task': (
                'A reading of the work found done-when items that do not hold. Say what to correct, in one line the '
                'department can act on: the line runs again with your correction in the Brief, so write it as the '
                'owner would ask for it. Correct only what the items below name, and only when the correction moves '
                'the department toward its goal.'
            ),
            'guidance': (
                'A correction names the item it puts right and the finding it answers. Name the findings it fixes '
                '(fixes) and the items it covers (covers), each from the lists above. Never repeat the approach that '
                'already failed: when the last round failed, say a different thing, and do not ask for more of the '
                'same. State no fact nobody gave: where a fact is missing, say it is to be confirmed.'
            ),
        },
        'note': {
            'text': (
                'In this version the choice is made by code, not by words its agent reads: a step whose answers '
                'agree run after run is proposed one rung up, to a checklist or to code, and is tried beside the '
                'old way first; a step that keeps missing is proposed one rung down. Every move goes to Priority '
                'first, and Adaptation never applies one itself.'
            ),
        },
    },
    'make': {
        'line': {},
        'refused': {},
        # M5.2 (A1-FIT): the words of the part adapt.fit reads when the line is the Library's own
        'fit': {
            'task': (
                "Fit the Library's line to this goal. The line below is what the Library runs for this kind of "
                'department. Keep every engine the goal needs, in the same order, and say, for an engine that '
                'should work differently for this goal, what it does differently. Leave an engine out only when '
                'no done-when item needs what it writes, and never one marked required.'
            ),
            'guidance': (
                'An engine you keep reads what an earlier one wrote, so leave out only an engine that no engine '
                'you keep reads. A note is one line about this goal, at most 300 characters, and says what the '
                'engine does differently; give an engine no note when it does what it always does. Name only '
                'engines of the line above. When nothing needs to change, answer with the whole line and an '
                'empty fit.'
            ),
        },
        # M6.4 (A1-SHAPE): the words of the part adapt.line reads when the make setting is on and no template fits
        'shape': {
            'task': (
                'Shape the workflows this department needs to make every one of its done-when items true. Make '
                'the fewest engines that cover every item, usually two to five, in the order they run. Each '
                "engine reads one thing and writes one thing: the first reads the Brief (the owner's words), and "
                'each later one reads what an earlier one wrote. An engine that covers no item must feed one '
                'that does.'
            ),
            'guidance': (
                'For each engine give its name and what it does, the items it covers (covers), its level (1 or '
                '2), how sure you are (confidence, a number from 0 to 1) and, when you are below 0.8 sure, what '
                'you doubt (doubt).\n'
                'Level 1 takes an engine of the Library as it is, with the reads and writes shown: use it when '
                'its use case fits the goal. Level 2 is a new engine: name it in one or two words none of the '
                'taken names use, and name what it writes in one or two words. Keep every engine this kind of '
                'department requires, at level 1.\n'
                'Confidence is how sure you are that this engine, reading what the plan hands it, can make its '
                'items true without a fact or a decision nobody has given. In doubt write the one question you '
                'would ask the owner, in one sentence; you may add a second sentence that begins "Unless you '
                'say," and says what you will do if they do not answer.\n'
                'An engine can search the web and open pages: say in what it does what it looks up, and mark '
                'internet true.\n'
                'Answer cannot, with no engines, only when an engine this kind of department requires cannot '
                'serve an item: name the engine, the items and why.'
            ),
        },
    },
}
LAYOUT = {
    'goal': {
        'does': '{text}',
        'skills': '{items}',
    },
    'sense': {
        'shape': (
            'The owner floats an idea the department cannot do today. Do not plan a build. Reflect the idea '
            'back in sharper words, name the question underneath it, and give two or three shapes it could '
            'take, smallest first. Then say what engine would do it each time on its own: pick one from the '
            'Library below when its use case fits (pick), else shape one (engine: a name of one or two words, '
            'what it does in one line, and what it needs from this list: {{needs}}); both null when the idea '
            'asks for no engine.\n'
            'THE GOAL: {{goal}}\n'
            'THE IDEA: {{idea}}\n'
            'ENGINES IN THE LIBRARY, NOT YET IN THIS DEPARTMENT: {{library}}\n'
            '\n'
            '{returns}'
        ),
    },
    'decide': {
        'next': (
            '{task}\n'
            'THE DEPARTMENT: {{dept}}\n'
            'THE ITEMS THAT DO NOT HOLD:\n'
            '{{items}}\n'
            '\n'
            'WHAT AUDIT FOUND:\n'
            '{{findings}}\n'
            '\n'
            'THE LINE THAT RAN: {{line}}\n'
            'THE LAST ROUND: {{last}}\n'
            '\n'
            '{returns}\n'
            '\n'
            '{guidance}'
        ),
        'note': '{text}',
    },
    'make': {
        'line': (
            'The department "{{dept}}" was just given its goal, in its owner\'s words:\n'
            '{{words}}\n'
            '\n'
            'WHAT DONE MEANS, ITEM BY ITEM:\n'
            '{{items}}\n'
            '\n'
            'It has no engines yet. Shape the line of engines that gets this done: two to five, in the order '
            "they run, each reading one thing and writing one thing. The first reads the Brief (the owner's "
            'words); each later one reads what an earlier one wrote. An engine can search the web and open '
            'pages: say in what it does what it looks up, and mark internet true. Name each engine in one or '
            'two words none of these already use ({{taken}}), and name what it writes in one or two words '
            '(Facts, Pages, ...). When the goal is something that goes out into the world, the last engine '
            "writes it under the Library's own name for it: {{out}}.\n"
            "THE DEPARTMENT'S RULES: {{rules}}\n"
            '\n'
            '{returns}{{refused}}'
        ),
        'refused': "YOUR LAST LINE WAS REFUSED BY ROOT'S CHECK: {{faults}}. Shape it again without these faults.",
        'fit': (
            '{task}\n'
            'THE DEPARTMENT: {{dept}}\n'
            "THE OWNER'S WORDS:\n"
            '{{words}}\n'
            '\n'
            'WHAT DONE MEANS, ITEM BY ITEM:\n'
            '{{items}}\n'
            '\n'
            "THE LIBRARY'S LINE FOR THIS KIND OF DEPARTMENT, in the order it runs:\n"
            '{{engines}}\n'
            "THE DEPARTMENT'S RULES: {{rules}}\n"
            '\n'
            '{returns}\n'
            '\n'
            '{guidance}'
        ),
        'shape': (
            '{task}\n'
            'THE DEPARTMENT: {{dept}}\n'
            "THE OWNER'S WORDS:\n"
            '{{words}}\n'
            '\n'
            'WHAT DONE MEANS, ITEM BY ITEM:\n'
            '{{items}}\n'
            '\n'
            '{{practices}}\n'
            "THE DEPARTMENT'S RULES: {{rules}}\n"
            'NAMES ALREADY TAKEN: {{taken}}\n'
            "WHAT GOES OUT INTO THE WORLD, written by the last engine under the Library's own name for it: {{out}}\n"
            '\n'
            '{returns}\n'
            '\n'
            '{guidance}{{refused}}'
        ),
    },
}

# ---- the function template's words (A3.4.5, A3-FUNCTIONS F1) ---------------------------------------------------------
# Parts of the goal group that S.ADDED_PARTS lists (they have no .md part), and the layout of the role block the card
# carries (A3.4.3). What the function is not, what it never does and who it hands on to are S.FUNCTION_TEMPLATE's, not
# words: no version drops one.
# Pursue (W2-ADAPT F3, F5: the handler "Propose the next round") is built, so three clauses promise it: "and again after
# each reading until the done-when holds" (role_is), "propose the next round when Audit's reading is not done and the
# correction advances the goal" (role_may) and "When Audit's reading is not done, propose a correction only if it moves
# the goal." (role_procedure). The guard test test_adaptations_role_words_promise_pursue_only_when_it_is_built keeps the
# three in step with the recipe.
WORDS['goal']['done'] = {'text': "Identity's done-when holds on Audit's reading, and Adaptation has nothing more to propose"}
WORDS['goal']['role_is'] = {'text': (
    "the department's intelligence for change; it reads where the department stands against its goal "
    'and proposes the smallest useful workflow or change that closes the gap, and again after each reading until the done-when holds'
)}
WORDS['goal']['role_may'] = {'items': [
    'reuse a workflow of the Library when it fits the goal',
    'propose the smallest new workflow that can be tested, when none fits',
    'accept an ask for less from Priority, or revise the proposal, and say which',
    "correct only what Root's check named, and send the plan again",
    "propose the next round when Audit's reading is not done and the correction advances the goal",
    'leave out an engine its template does not mark required',
    'shape a new idea the owner floats, and park it',
    "propose a step's move up or down the ladder",
]}
WORDS['goal']['role_procedure'] = {'items': [
    'Name the gap between where the department is and its goal, and cite the record that shows it.',
    'Reuse a workflow of the Library when one fits.',
    'Otherwise propose the smallest new workflow that can be tested.',
    'Send it to Priority for its limit and its price.',
    'When Priority asks for less, accept or revise, and say which.',
    "When Root's check names errors, correct only those and send the plan again.",
    "When Audit's reading is not done, propose a correction only if it moves the goal.",
    'Look a fact up before you ask for it; what only the owner knows goes to Identity as a question.',
]}
WORDS['goal']['role_patterns'] = {'items': [
    'Redesigning again and again without testing.',
    'Treating more work as more progress.',
    'Turning down every ask for less from Priority.',
    'Writing a done check nobody can test.',
    'Proposing a workflow that needs access it did not declare.',
]}
WORDS['goal']['role_block'] = {}
LAYOUT['goal'].update({'done': '{text}', 'role_is': '{text}', 'role_may': '{items}', 'role_procedure': '{items}',
                      'role_patterns': '{items}', 'role_block': S.ROLE_BLOCK_LAYOUT})


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


#: what a round's status is called to the owner (never grant or refuse: the bargain's words are said yes and said no)
ROUND_SAID = types.MappingProxyType({'proposed': 'asked Priority', 'granted': 'Priority said yes', 'refused': 'Priority said no',
                                     'filed': 'filed in the Brief', 'read': 'read by Audit'})


def round_view(r):
    """One round as the pane has it (view.adaptation.round): the folded row, with its status in the owner's words."""
    return {'round': r['round'], 'correction': clip(r.get('correction')), 'covers': list(r.get('covers') or []), 'fixes': list(r.get('fixes') or []),
            'status': r.get('status'), 'said': ROUND_SAID.get(r.get('status'), ''), 'estimate': r.get('estimate') if isinstance(r.get('estimate'), dict) else None,
            'at': r.get('at'), 'reading': r.get('reading'), 'brief_v': r.get('brief_v')}


def view(ref, d, events, asks):
    """Adaptation's pane (S.VIEWS['adaptation']): what it has always shown (the latest proposal, and the last Root reviews),
    with the coverage of that proposal (M5.1) and, on each review, the checks that ran, each with what the standard says,
    whether it held and why (M7.3). The words are the owner's: the bargain's inside words are put right on the way out."""
    import owner_words
    plain = owner_words.plain
    says = {i: text for i, text, _, _ in S.WORKFLOW_STANDARDS}
    prop = next((e for e in reversed(events or []) if e.get('action') == 'proposal.created'), None)
    reviews = [e for e in events or [] if e.get('action') in ('workflow.validated', 'workflow.blocked')][-4:]
    rounds = [round_view(r) for r in rounds_of(ref) if r.get('status') in ROUND_SAID]               # M9.6: rounds.jsonl, folded by round
    return {'proposal': prop and {'workflow': (prop.get('payload') or {}).get('workflow') or [],
                                  'source': (prop.get('payload') or {}).get('source'), 'at': prop.get('occurred_at')},
            'root_checks': [{'summary': plain(e.get('summary')), 'at': e.get('occurred_at'), 'passed': e.get('action') == 'workflow.validated',
                             'checks': [{'check': str(c.get('check'))[:60], 'says': plain(says.get(c.get('check')) or c.get('check'))[:300],
                                         'passed': bool(c.get('passed')), 'why': plain(c.get('why'))[:600]}
                                        for c in (e.get('payload') or {}).get('checks') or [] if isinstance(c, dict) and c.get('check')]}
                            for e in reviews],
            'coverage': coverage(ref, d, prop),
            'round': rounds[-1] if rounds else None,
            'rounds': rounds}
