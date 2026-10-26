"""layers/adaptation/v1.py -- Adaptation, version 1: the implementation behind the interface's adaptation entries (PRD A1.18).

Its recipe is v1.json beside it: the Adaptation engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here (A1 step A1): by reference, to the body
engine_runtime still holds, until this layer moves one in to change it (move on touch, A1.19). WORDS and LAYOUT stay
empty until the words move, so the prompts are still read from the .md bundle. view() returns the pane's read model by
reference.
"""
import os

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


def practices(d):
    """The practices in place that Make reads (J2B-2), as names and use cases and never files: the department's rules with
    their tags; the shipped work engines except Setup (a born engine carries another department's words, so it is not
    one), each with its use case, what it reads and writes; the Library's artifacts; each engine the kind requires with
    what its check refuses; and the names already taken. Not the kind's done line, which the done-when items replace, and
    not other departments' workflows."""
    rules = [{'tag': str(r.get('tag') or ''), 'line': str(r.get('line'))} for r in (d or {}).get('rules') or []
             if isinstance(r, dict) and r.get('line')]
    shipped = [{'name': n, 'use_case': str(t.get('use_case') or ''), 'reads': t.get('reads') or 'Brief', 'writes': t.get('writes') or n}
               for n, t in R.engine_templates().items() if t.get('kind') == 'work' and not t.get('made_by') and n != 'Setup']
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
    return {'rules': rules, 'engines': shipped, 'artifacts': shelf, 'required': required, 'taken': sorted(known)}


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


def workflow_of(engines, source, d):
    """The line as a workflow value (DEFS['workflow'], A1.14): S.as_workflow over the engines, which looks up what a name
    reads and writes and inverts each engine's covers, and then the fields of a made engine it does not carry over
    (its level, confidence and doubt)."""
    wf = S.as_workflow(engines, source, d)
    by = {e.get('name'): e for e in engines if isinstance(e, dict)}
    for row in wf['engines']:
        for key in ('level', 'confidence', 'doubt'):
            if by.get(row['name'], {}).get(key) is not None:
                row[key] = by[row['name']][key]
    return wf


def c_line_is_engines(ctx, step, item, out):
    """One to six engines that code finds nothing wrong with: the shape is the agent's, the check is code (today's rules:
    each named once and new to the Library, the first reading the Brief, each reading what one before it wrote and
    writing something new). Then Root's standards at the proposal stage (A4): the line is run as a workflow through
    S.validate_workflow, and a failed row, named by its standard, is a note beside today's wording. A warning row passes."""
    engs = out.get('engines') if isinstance(out, dict) else None
    if not isinstance(engs, list) or not 1 <= len(engs) <= 6:
        return R._verdict(False, '', 'one to six engines')
    notes = list(R._line_faults(engs))
    d = (ctx or {}).get('dept')
    source = (((ctx or {}).get('bag') or {}).get('adapt.source') or {}).get('source') or 'shaped'
    for row in S.validate_workflow(workflow_of(norm_engines(engs), source, d), 'proposal', d, {}):
        note = '%s: %s' % (row['check'], row['why'])
        if not row['passed'] and note not in notes:
            notes.append(note)
    return {'ok': not notes, 'notes': notes or ['%d engines, each reading what one before it wrote' % len(engs)]}


CODE = {name: ref_to(name) for name in (
    'hear', 'adapt_sense', 'adapt_ladder', 'adapt_act', 'adapt_trial', 'adapt_notrial', 'adapt_heard', 'adapt_park', 'adapt_offer',
    'adapt_priced', 'adapt_line_offer', 'adapt_line_granted', 'adapt_line_refused', 'adapt_line_counter')}
CODE['adapt_source'] = adapt_source
PROMPT = {'adapt_shape': ref_to('p_adapt_shape'), 'adapt_line': ref_to('p_adapt_line')}
DRAFT = {'adapt_shape_draft': ref_to('d_adapt_shape'), 'adapt_line_draft': ref_to('d_adapt_line')}
CHECK = {name: ref_to('c_' + name) for name in (
    'counted_the_rows', 'moves_name_their_rows', 'said_what_it_did', 'facts_are_closed', 'idea_has_shapes')}
CHECK['line_is_engines'] = c_line_is_engines
WORDS, LAYOUT = {}, {}


def view(ref, d, events, asks):
    """Adaptation's pane (S.VIEWS['adaptation']): functions_view's read model, by reference until this layer holds its own."""
    return FV._j2_part(ref, d, 'Adaptation', events, asks)
