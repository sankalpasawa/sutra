"""template_checks.py -- the pure helpers behind the templates at every level (PRD amendment A3).

layer_schema.py holds the definitions (DEFS['step'], DEFS['kind'], ...); what a definition cannot say as a type, a rule
that reads two fields of one record, is written here, once, so a test, a contract case and a screen ask the same
question. Every function is pure: it reads what it is given and the interface, looks up no registry (that is
engine_runtime.validate's, the definition law), writes nothing, never raises on a bad record and returns plain
sentences, one for each thing wrong, that name the thing and what is wrong; [] when it fits.

Nothing is imported here but layer_schema, which imports nothing of the app, so this module may be read by anything.
"""
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
