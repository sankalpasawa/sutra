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
