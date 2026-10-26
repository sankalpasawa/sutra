"""template_checks.py -- the pure helpers behind the templates at every level (PRD amendment A3).

layer_schema.py holds the definitions (DEFS['step'], DEFS['kind'], ...); what a definition cannot say as a type, a rule
that reads two fields of one record, is written here, once, so a test, a contract case and a screen ask the same
question. Every function is pure: it reads what it is given and the interface, looks up no registry (that is
engine_runtime.validate's, the definition law), writes nothing, never raises on a bad record and returns plain
sentences, one for each thing wrong, that name the thing and what is wrong; [] when it fits.

Nothing is imported here but layer_schema, which imports nothing of the app, so this module may be read by anything.
"""
import re

import layer_schema as S


def _named(step):
    return str((step or {}).get('id') or 'a step') if isinstance(step, dict) else 'a step'


def step_law():
    """The law of inheritance for the step's fields, read from DEFS['step'] (every property carries x-law): (fixed, free),
    two tuples of field names in the definition's order, without id, which names the step and never changes (A2's
    STEP_FIXED and STEP_FREE are these two lists, held in the interface so the law reads one source)."""
    props = S.DEFS['step']['properties']
    return (tuple(k for k, v in props.items() if k != 'id' and v.get('x-law') == 'fixed'),
            tuple(k for k, v in props.items() if k != 'id' and v.get('x-law') == 'free'))


def step_faults(step, group='steps'):
    """What is wrong with a step against the step template (A3.3, rules ST-1, ST-3 and ST-4): the shape law,
    S.validate('step', step) (no field outside the classified list), then the body its kind keeps. `group` is where the
    recipe holds the step: 'gates', 'rules' or 'steps' (a handler's steps too). It does not repeat engine_runtime.validate:
    it asks nothing of a registry, and it does not look at a unit's first and last steps.

    A code step has code and is born on code (C2), with no prompt, plain draft or shape of answer. A step with a prompt
    (an AI step, a person's step, a gate that has gone soft) names its plain draft and the shape of its answer. An AI step
    is born on a call or a checklist (C0 or C1) and has no code of its own: a step in steps is by code or by an AI, never
    both. A person step is born P and names what the person is asked (by_hand). A gate or a rule has its rule in code, and
    a rule has no prompt. by_hand is for a step with a prompt, the only kind that can fall to the person."""
    out = S.validate('step', step)
    if not isinstance(step, dict):
        return out
    name, kind = _named(step), None
    try:
        kind = S.step_kind(step, group)
    except ValueError as exc:
        return out + [str(exc)]
    code, prompt = step.get('code'), step.get('prompt')
    if kind in ('gate', 'rule') and not code:
        out.append('%s: a %s has its rule in code, and this one names no code' % (name, kind))
    if kind == 'rule' and prompt:
        out.append('%s: a rule is code only, and this one names a prompt' % name)
    if kind == 'code':
        if not code:
            out.append('%s: a code step names the code it runs, and this one names none' % name)
        if step.get('born') not in (None, 'C2'):
            out.append('%s: a code step is born on code (C2), not on %s' % (name, step.get('born')))
        for key in ('draft', 'out'):
            if key in step:
                out.append('%s: a code step has no %s: that belongs to a step with a prompt' % (name, key))
    if kind in ('ai', 'person') or (kind == 'gate' and prompt):
        if not step.get('draft'):
            out.append('%s: a step with a prompt names its plain draft, the answer when no model is there' % name)
        if not step.get('out'):
            out.append('%s: a step with a prompt names the shape of its answer' % name)
    if kind == 'ai':
        if step.get('born') not in ('C0', 'C1'):
            out.append('%s: an AI step is born on a call or a checklist (C0 or C1), not on %s' % (name, step.get('born')))
    if kind == 'person' and not step.get('by_hand'):
        out.append('%s: a person step is born P and says what the person is asked (by_hand), and this one says nothing' % name)
    if kind in ('ai', 'person') and code and prompt:
        out.append('%s: a step is by code or by an AI, never both, and this one names the code %s and the prompt %s'
                   % (name, code, prompt))
    if step.get('by_hand') and not prompt:
        out.append('%s: by_hand is for a step with a prompt, the only kind that can fall to the person' % name)
    return out


def part_readers(spec):
    """The step ids a prompt part names in read_by: one id, several, or none (a part nothing reads)."""
    read_by = spec.get('read_by') if isinstance(spec, dict) else None
    return [read_by] if isinstance(read_by, str) else [x for x in read_by or () if isinstance(x, str)]


def part_faults(prompts, steps):
    """What is wrong with how the prompt parts of the functions and the steps of their recipes meet (A3.3, rule ST-6). `prompts` is
    laid out as S.PROMPTS, {layer: {group: {part: {read_by, ...}}}}; `steps` is [(layer, group, step)], every step of the recipes of
    the functions (group is where the recipe holds it: 'gates', 'rules' or 'steps'). Two things must hold. Every AI step of a
    function is named in read_by by at least one part of its own layer: its words come from a part, and a step may be read by
    several (adapt.line is read by make.line and make.shape), but never by none. And every read_by names a step of that layer's own
    recipes: a part nothing could read is a part that says nothing. Pure: it reads what it is given and asks nothing of a department."""
    out, ids = [], {}
    for layer, group, step in steps:
        if isinstance(step, dict):
            ids.setdefault(layer, set()).add(step.get('id'))
    for layer, group, step in steps:
        if not isinstance(step, dict):
            continue
        try:
            kind = S.step_kind(step, group)
        except ValueError:
            continue                                 # a step with no kind is step_faults', not this rule's
        if kind != 'ai':
            continue
        parts = prompts.get(layer) or {}
        if not any(step.get('id') in part_readers(spec) for ps in parts.values() for spec in ps.values()):
            out.append('%s: the AI step %s is read by no prompt part of %s, and a function\'s AI step takes its words from a part (S.PROMPTS)'
                       % (S.TITLE.get(layer, layer), step.get('id'), S.TITLE.get(layer, layer)))
    for layer, parts in prompts.items():
        for g, ps in parts.items():
            for p, spec in ps.items():
                for sid in part_readers(spec):
                    if sid not in ids.get(layer, ()):
                        out.append('%s: the part %s.%s is read by %s, which is no step of %s'
                                   % (S.TITLE.get(layer, layer), g, p, sid, S.TITLE.get(layer, layer)))
    return out


def kind_faults(name, kind):
    """What is wrong with a department kind against the kind template (A3.5, rule K-1): the shape law, S.validate('kind', kind),
    and the one rule a type cannot say, that the engines a kind marks required are inside its own line (no engine is mandatory
    unless its template says so, S-06). engine_runtime.validate says the same of the same kind in the same words
    ('kinds, <name>: required names engines of its own line'), and a test holds the two to each other (K-2). It does not ask
    whether a name in line is a work engine, or whether functions_template names a Library template every function has: those
    look names up in the Library, which is the definition law's."""
    out = ['kinds, %s: %s' % (name, f) for f in S.validate('kind', kind)]
    if isinstance(kind, dict) and isinstance(kind.get('required'), list) and isinstance(kind.get('line'), list):
        outside = [n for n in kind['required'] if n not in kind['line']]
        if outside:
            out.append('kinds, %s: required names engines of its own line, and %s %s not in it'
                       % (name, ', '.join(str(n) for n in outside), 'is' if len(outside) == 1 else 'are'))
    return out


def artifact_faults(template):
    """What is wrong with an artifact template against DEFS['artifact.template'] (A3.5, rule AR-1): the shape law, and the one
    rule a type cannot say, that a template of kind app also names the screen it opens and what it reads. A check the template
    names must ship (artifacts.CHECKS, AR-2) and an operation must be an engine: those look names up, and a test holds them."""
    out = S.validate('artifact.template', template)
    if isinstance(template, dict) and template.get('kind') == 'app':
        label = str(template.get('name') or template.get('id') or 'an app template')
        for key in ('screen', 'reads'):
            if not template.get(key):
                out.append('%s: an app template names its %s, and this one names none' % (label, key))
    return out


def _option_kind(option):
    """The kind of one way out on an ask: the kind it carries, else the part of its id before ':' (website_dept.option derives
    it so: leave:D2 is a leave). '' for an option that is not a table or names nothing."""
    if not isinstance(option, dict):
        return ''
    return str(option.get('kind') or str(option.get('id') or '').split(':', 1)[0])


def ask_faults(ask):
    """What is wrong with an ask against the ask template (A3.5, rules AS-1 and AS-2): the shape law, S.validate('identity.ask', ask)
    (a kind and a status from the lists, at most S.OPTIONS_MAX options, each of a known kind), then the form of its kind. S.ASK_FORMS
    names the kinds of way out its writers attach to each kind of ask; an ask offers no kind its form does not name, and a kind whose
    form names none is stamped yes or no and offers no way out at all. An ask of a kind with no form, and an option of a kind the
    interface does not know, are the shape law's faults already, so the form is not asked of them. Pure: it asks nothing of a
    department."""
    out = S.validate('identity.ask', ask)
    if not isinstance(ask, dict) or ask.get('kind') not in S.ASK_FORMS or not isinstance(ask.get('options'), list):
        return out
    name, kind = str(ask.get('id') or 'an ask'), ask['kind']
    allowed = tuple(S.ASK_FORMS[kind]['options'])
    outside = []
    for option in ask['options']:
        got = _option_kind(option)
        if got in S.OPTION_KINDS and got not in allowed and got not in outside:
            outside.append(got)
    if outside:
        offers = 'offers %s' % ', '.join(outside)
        the = ('an' if kind[:1] in 'aeiou' else 'a') + ' ' + kind
        if allowed:
            out.append('%s: %s ask offers only %s, and this one %s' % (name, the, ', '.join(allowed), offers))
        else:
            out.append('%s: %s ask is stamped yes or no and offers no way out, and this one %s' % (name, the, offers))
    return out


_LEVEL_KEYS = ('level', 'name', 'base', 'children', 'keeps', 'rules')
_RULE_ID = r'^(JC|K|FT|E|ST|AR|AS)-[1-9][0-9]?$'


def levels_faults():
    """What is wrong with the table of levels, S.TEMPLATE_LEVELS (A3.1): seven levels, L0 to L6, once each and in order; each
    names its six parts; its base is a definition of the interface or a table of it; and each rule id belongs to one level
    and is spelled as the rules of A3.1 are (JC-1, K-1, FT-10 ...). [] when it is sound."""
    import re
    out, levels = [], S.TEMPLATE_LEVELS
    ids = [l.get('level') if isinstance(l, dict) else None for l in levels]
    if ids != ['L%d' % i for i in range(7)]:
        out.append('the levels are L0 to L6, once each and in that order, and the table holds %s' % ', '.join(str(i) for i in ids))
    owner = {}
    for l in levels:
        if not isinstance(l, dict):
            out.append('a level is a table of its parts, and %r is not one' % (l,))
            continue
        label = '%s (%s)' % (l.get('level'), l.get('name'))
        for key in _LEVEL_KEYS:
            if not l.get(key):
                out.append('level %s names no %s' % (label, key))
        for key in sorted(set(l) - set(_LEVEL_KEYS)):
            out.append('level %s holds %s, which is not one of its parts: %s' % (label, key, ', '.join(_LEVEL_KEYS)))
        base = l.get('base')
        if base and base not in S.DEFS and not isinstance(getattr(S, str(base), None), (dict, tuple, list)):
            out.append('level %s names the base %s, which is neither a definition nor a table of the interface' % (label, base))
        for rule in l.get('rules') or ():
            if not re.match(_RULE_ID, str(rule)):
                out.append('level %s names the rule %s, which is not spelled as the rules of A3.1 are' % (label, rule))
            elif owner.setdefault(rule, l.get('level')) != l.get('level'):
                out.append('the rule %s is held by %s and by %s: a rule belongs to one level' % (rule, owner[rule], l.get('level')))
    return out


_FT_KEYS = ('role', 'is_not', 'never', 'hands_on', 'in_card')
_FT_LIMITS = {'role': 80, 'is_not': 600, 'hands_on': 400}                # characters; the never lines have their own (160)


def function_template_faults(layer, entry):
    """What is wrong with one function's constants against the function template (A3.4.2, rule FT-1): a role phrase of at most 80
    characters, an 'is not' of at most 600, a 'hands on to' of at most 400, three to ten 'never' lines of at most 160, and whether
    the role block is sent in its card. Adaptation may also carry reserved, the site's parts that are placeholders; no other key is
    the template's. Whether a 'hands on to' names only actors the layer sends to (FT-10) is checked against S.SENDS by its test."""
    label = S.TITLE.get(layer, layer)
    if not isinstance(entry, dict):
        return ['%s has no entry in the function template' % label]
    out = ['%s: the template names no %s' % (label, key) for key in _FT_KEYS if key not in entry]
    for key, longest in _FT_LIMITS.items():
        value = entry.get(key)
        if key in entry and (not isinstance(value, str) or not value.strip() or '\n' in value):
            out.append('%s: %s is one line of words, and this is not' % (label, key))
        elif isinstance(value, str) and len(value) > longest:
            out.append('%s: %s is %d characters, and the limit is %d' % (label, key, len(value), longest))
    never = entry.get('never')
    if 'never' in entry:
        if not isinstance(never, (list, tuple)) or not 3 <= len(never) <= 10:
            out.append('%s: never holds three to ten lines, and this holds %s' % (label, len(never) if isinstance(never, (list, tuple)) else 'none'))
        for i, line in enumerate(never if isinstance(never, (list, tuple)) else (), 1):
            if not isinstance(line, str) or not line.strip() or len(line) > 160:
                out.append('%s: never line %d is a line of words of at most 160 characters, and this is not' % (label, i))
    if 'in_card' in entry and not isinstance(entry['in_card'], bool):
        out.append('%s: in_card is true or false' % label)
    extra = sorted(set(entry) - set(_FT_KEYS) - ({'reserved'} if layer == 'adaptation' else set()))
    out += ['%s: %s is not a part of the function template' % (label, key) for key in extra]
    if 'reserved' in entry and (not isinstance(entry['reserved'], (list, tuple)) or not all(isinstance(x, str) for x in entry['reserved'])):
        out.append('%s: reserved is a list of names' % label)
    return out


def agreement_faults(lines):
    """What is wrong with the working agreement every function keeps (A3.4.2): four to eight lines, each one line of at most 200
    characters, the first saying that only Identity speaks to the owner."""
    if not isinstance(lines, (list, tuple)) or not 4 <= len(lines) <= 8:
        return ['the working agreement holds four to eight lines, and this holds %s' % (len(lines) if isinstance(lines, (list, tuple)) else 'none')]
    out = ['agreement line %d is one line of words of at most 200 characters, and this is not' % i
           for i, x in enumerate(lines, 1) if not isinstance(x, str) or not x.strip() or '\n' in x or len(x) > 200]
    if not out and not lines[0].startswith('Only Identity speaks to the owner'):
        out.append('the first line of the working agreement says that only Identity speaks to the owner')
    return out


_ACTORS = ('The owner', 'Root', 'Identity', 'Adaptation', 'Priority', 'Coordination', 'Audit')
#: what a layer calls in process that is no post and no row of S.CALLS: Adaptation runs Root's standards on the line it shapes
#: before it sends it (adapt_source calls S.validate_workflow, stage 'proposal'); a test reads the source for the call
_IN_PROCESS = {'adaptation': ('Root',)}


def hands_on_actors(text):
    """The actors a 'hands on to' line names, with what it hands each: [(actor, clause)], read from the clauses that begin
    'Name: ' or 'Name and Name: ' or 'Name only: ' (a name inside a clause is not named). The owner is 'The owner'."""
    names = '|'.join(re.escape(a) for a in _ACTORS)
    head = re.compile(r'(?:^|(?<=\. ))((?:%s)(?: and (?:%s))*)(?: only)?: ' % (names, names))
    heads = list(head.finditer(str(text or '')))
    out = []
    for i, m in enumerate(heads):
        clause = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        out += [(actor, clause.strip()) for actor in m.group(1).split(' and ')]
    return out


def hands_on_faults(layer, text):
    """What is wrong with a function's 'hands on to' line (A3.4.2, rule FT-10): it names only layers, Root or the owner; each is
    a destination of that layer's S.SENDS rows, a callee of its S.CALLS rows or of the calls it makes in process, or is reached
    through a destination the clause names ('Identity: through Adaptation's conflict'); the owner is 'the owner', never 'You';
    and a function does not hand on to itself."""
    title = S.TITLE.get(layer, layer)
    out = []
    if re.search(r'\bYou\b', str(text or '')):
        out.append("%s hands on to the owner, who is 'the owner' in these words and never 'You'" % title)
    actors = hands_on_actors(text)
    if not actors:
        return out + ['%s names no one it hands on to' % title]
    direct = {('The owner' if d == 'Owner' else d) for row in S.SENDS.get(title, []) for d in row['to']}
    direct |= {c['to'] for c in S.CALLS if c['from'] == title} | set(_IN_PROCESS.get(layer, ()))
    for actor, clause in actors:
        if actor == title:
            out.append('%s hands on to itself' % title)
            continue
        if actor in direct:
            continue
        via = re.search(r"\bthrough (\w+)'s\b", clause)
        relay = via.group(1) if via else None
        if relay in direct and any(actor == ('The owner' if d == 'Owner' else d)
                                   for row in S.SENDS.get(relay, []) for d in row['to']):
            continue
        out.append('%s hands on to %s, and the interface gives %s no row to %s (S.SENDS) and no call to it (S.CALLS)'
                   % (title, actor, title, actor))
    return out
