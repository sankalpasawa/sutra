"""layers/contract.py -- the contract every implementation of a layer passes (PRD amendment A1.21).

A version of a layer may change freely behind the interface, so long as it passes these cases, which
test_layer_contracts.py runs on every implementation it discovers (layers/<layer>/v<N>.py):

    1  LAYER, VERSION and IMPLEMENTS are right, and the recipe is there
    2  the recipe handles every HEARS row of its layer, and every handler is a HEARS row
    3  every code, prompt, draft and check name the recipe uses is provided, by the module or the legacy registries
       (how many it provides by reference is reported, not gated)
    4  every check the recipe names is in CHECKS[layer] or SHARED_CHECKS, and each check with CONTRACT_SAMPLES accepts
       every good sample and refuses every bad one
    5  every WORDS value passes S.validate_field, every part with WORDS has a LAYOUT, and each such part compiles with
       sample inputs: its returns verbatim, no marker left, no field unread (layers.prompts.layout_faults); a part with
       no WORDS is a fault: it is on the .md fallback (reported only until 'A1 interface: refuse')
    6  view() on the contract fixture department validates as VIEWS[layer]
    7  no ref_to points at an engine_runtime attribute that is itself a delegate
    8  every OUTPUTS step the recipe provides declares or returns those keys
    14 a function version keeps the function template (A3.4.8): its words, its role block and its boundaries (FT-1 to FT-6,
       FT-9, FT-10)

and, from amendment A2 (design/PRD-FIVE-FUNCTIONS-A2.md A2.7), the cases of a version that extends a version. A version with no
PARENT has nothing to compare, and passes them as it is; a stub with none of the new attributes passes them too:

    9  the lineage is sound: a version above 1 names its PARENT, the same layer's, lower, loading, repeating nowhere, and the version
       holds every name of its parent's four tables and every part of its parent's words and layout
    10 the version publishes every surface function its PARENT does (versions.SURFACE)
    11 the resolved recipe keeps what the parent fixes (lineage.recipe_faults over the recipe the version brings)
    12 every gate or rule whose code or check the version replaces is declared in TIGHTENS, with a test that exists
    13 the assembled definitions validate with this version's resolved recipe in its layer's place (layers.definition_faults)

A case returns its faults as a list of strings, each naming the row or the name at fault; [] when the module passes.
"""
import importlib
import json
import os
import re
from pathlib import Path

import layers
from layers import R, W, S, FV  # noqa: F401 -- lazy proxies: tests reload the runtime
from layers import lineage as L
from layers import prompts as P
from layers import versions as V

HERE = Path(__file__).resolve().parent
MODULE_RE = r'^v[1-9][0-9]*$'


def discover():
    """Every implementation on disk, layers/<layer>/v<N>.py, imported, in LAYER_NAMES then version order."""
    out = []
    for layer in S.LAYER_NAMES:
        found = sorted((p for p in (HERE / layer).glob('v*.py') if re.match(MODULE_RE, p.stem)), key=lambda p: int(p.stem[1:]))
        out += [importlib.import_module('layers.%s.%s' % (layer, p.stem)) for p in found]
    return out


def fixture_department(home, ref='contract-dept', kind='website'):
    """The department the contract reads views of: made with W.create in the records home `home` (the caller has
    pointed SUTRA_NATIVE_DEPT_HOME at it, as test_j2's fixture does), with no model. Returns its ref."""
    if Path(os.environ.get('SUTRA_NATIVE_DEPT_HOME') or '').resolve() != Path(home).resolve():
        raise ValueError('point SUTRA_NATIVE_DEPT_HOME at the contract home first')
    if not W.dept(ref):
        W.create(ref, 'Contract Department', None, kind=kind)
    return ref


def impl_id(module):
    return '%s/v%s' % (getattr(module, 'LAYER', '?'), getattr(module, 'VERSION', '?'))


def recipe_of(module):
    """The engine object the module's version brings, resolved: its v<N>.json beside it, a patch beside it laid over the recipe of the
    version it extends, or that parent's recipe when it names a PARENT and no file (A2.5); for Root the Library template it names
    (RECIPE_TEMPLATE). None when it is not there, or a patch does not merge."""
    if getattr(module, 'RECIPE_TEMPLATE', None):
        return R.engine_templates().get(module.RECIPE_TEMPLATE)
    if getattr(module, 'RECIPE_PATCH', None) or (getattr(module, 'PARENT', None) and not getattr(module, 'RECIPE', None)):
        try:
            return V.recipe_of_module(module)
        except L.ModelFault:
            return None
    p = Path(getattr(module, '__file__', '')).parent / str(getattr(module, 'RECIPE', ''))
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _steps(e):
    e = e or {}
    return list(e.get('gates') or []) + list(e.get('rules') or []) + list(e.get('steps') or []) + \
        [s for h in e.get('on') or [] for s in h.get('steps') or []]


def _dicts(module):
    return {'code': getattr(module, 'CODE', {}) or {}, 'prompt': getattr(module, 'PROMPT', {}) or {},
            'draft': getattr(module, 'DRAFT', {}) or {}, 'check': getattr(module, 'CHECK', {}) or {}}


def _legacy():
    return {'code': R.CODE, 'prompt': R.PROMPT, 'draft': R.DRAFT, 'check': R.CHECK}


def case_1(module, ctx=None):
    """LAYER, VERSION and IMPLEMENTS are right, and the recipe is there."""
    out, layer = [], getattr(module, 'LAYER', None)
    if layer not in S.LAYER_NAMES:
        out.append('%s: LAYER %r is not a layer' % (impl_id(module), layer))
    if Path(module.__file__).stem != 'v%s' % getattr(module, 'VERSION', None):
        out.append('%s: VERSION does not match its file %s' % (impl_id(module), Path(module.__file__).stem))
    if Path(module.__file__).parent.name != layer:
        out.append('%s: it lives under layers/%s' % (impl_id(module), Path(module.__file__).parent.name))
    if getattr(module, 'IMPLEMENTS', None) != S.SCHEMA_VERSION:
        out.append('%s: IMPLEMENTS %r is not schema version %d' % (impl_id(module), getattr(module, 'IMPLEMENTS', None), S.SCHEMA_VERSION))
    if recipe_of(module) is None:
        out.append('%s: its recipe %s is not there' % (impl_id(module), getattr(module, 'RECIPE_TEMPLATE', None) or getattr(module, 'RECIPE', None)))
    return out


def case_2(module, ctx=None):
    """The recipe handles every HEARS row of its layer, and every handler is a HEARS row."""
    e = recipe_of(module) or {}
    rows = {(r['act'], r['word']): r for r in S.hears(module.LAYER)}
    handlers = {(h['when'].get('msg_type'), h['when'].get('word', S.ANY)): h.get('name') for h in e.get('on') or []}
    out = ['%s: no handler hears %s/%s (%s)' % (impl_id(module), act, word, rows[(act, word)]['handler'])
           for act, word in rows if (act, word) not in handlers]
    out += ['%s: the handler %s (%s/%s) is no HEARS row' % (impl_id(module), name, act, word)
            for (act, word), name in handlers.items() if (act, word) not in rows]
    return out


def case_3(module, ctx=None):
    """Every code, prompt, draft and check name the recipe uses is provided, by the module or the legacy registries."""
    mine, legacy, out = _dicts(module), _legacy(), []
    for s in _steps(recipe_of(module)):
        for kind in ('code', 'prompt', 'draft', 'check'):
            name = s.get(kind)
            if name and name not in mine[kind] and name not in legacy[kind]:
                out.append('%s, %s: no %s named %s is provided' % (impl_id(module), s.get('id'), kind, name))
    return out


def by_reference(module):
    """How many names the module provides by reference (ref_to), and how many as bodies of its own: reported, not gated."""
    vals = [v for d in _dicts(module).values() for v in d.values()]
    return {'by_reference': sum(1 for v in vals if hasattr(v, 'legacy')), 'own': sum(1 for v in vals if not hasattr(v, 'legacy'))}


def case_4(module, ctx=None):
    """Every check the recipe names is the layer's or shared, and each with samples judges them as main's bodies do."""
    out, mine = [], _dicts(module)['check']
    allowed = set(S.CHECKS.get(module.LAYER) or {}) | set(S.SHARED_CHECKS)
    for name in sorted({s.get('check') for s in _steps(recipe_of(module)) if s.get('check')}):
        if name not in allowed:
            out.append('%s: the check %s is in neither CHECKS[%s] nor SHARED_CHECKS' % (impl_id(module), name, module.LAYER))
            continue
        samples = S.CONTRACT_SAMPLES.get(name)
        body = mine.get(name) or R.CHECK.get(name)
        if not samples or body is None:
            continue
        for good in samples['good']:
            if body(None, None, None, good).get('ok') is not True:
                out.append('%s: %s refuses the good sample %s' % (impl_id(module), name, json.dumps(good)))
        for bad in samples['bad']:
            if body(None, None, None, bad).get('ok') is not False:
                out.append('%s: %s accepts the bad sample %s' % (impl_id(module), name, json.dumps(bad)))
    return out


def case_5(module, ctx=None):
    """Every WORDS value passes validate_field, every part with WORDS has a LAYOUT, each compiles with sample inputs, and no
    part is left on the .md fallback (strict since 'A1 interface: refuse')."""
    out, words, layout = [], getattr(module, 'WORDS', {}) or {}, getattr(module, 'LAYOUT', {}) or {}
    for group, parts in words.items():
        for part, fields in (parts or {}).items():
            if part not in ((layout.get(group) or {})):
                out.append('%s: %s.%s has WORDS and no LAYOUT' % (impl_id(module), group, part))
            for name, value in (fields or {}).items():
                out += ['%s: %s.%s.%s: %s' % (impl_id(module), group, part, name, f[3:] if f.startswith('$: ') else f)
                        for f in S.validate_field(module.LAYER, group, part, name, value)]
            if part in ((layout.get(group) or {})):
                out += ['%s: %s.%s: %s' % (impl_id(module), group, part, f)
                        for f in P.layout_faults(module.LAYER, group, part, fields or {}, layout[group][part])]
    for group, parts in layout.items():
        out += ['%s: %s.%s has a LAYOUT and no WORDS' % (impl_id(module), group, part) for part in parts
                if part not in ((words.get(group) or {}))]
    return out + ['%s: %s is on the .md fallback: the version holds no WORDS for it' % (impl_id(module), part)
                  for part in on_the_md_fallback(module)]


def on_the_md_fallback(module):
    """The parts of the layer's PROMPTS this version holds no WORDS for: still read from the .md bundle. Reported until the
    integrator's refuse commit at the end of wave 1; from 'A1 interface: refuse', case 5 makes each one a fault. An added part
    (S.ADDED_PARTS) has no .md part to fall back to, so it is never on the list: case 14 names a version that lacks one."""
    words = getattr(module, 'WORDS', {}) or {}
    return ['%s.%s' % (group, part) for group, parts in (S.PROMPTS.get(module.LAYER) or {}).items() for part in parts
            if part not in (words.get(group) or {}) and (module.LAYER, group, part) not in S.ADDED_PARTS]


def case_6(module, ctx=None):
    """view() on the contract fixture department validates as VIEWS[layer]."""
    if module.LAYER not in S.VIEWS:
        return []
    view = getattr(module, 'view', None)
    if not callable(view):
        return ['%s: it has no view()' % impl_id(module)]
    ref = (ctx or {}).get('ref')
    if not ref:
        return ['%s: the contract has no fixture department to read the view of' % impl_id(module)]
    d = W.dept(ref)
    return ['%s: view %s' % (impl_id(module), f) for f in S.validate_view(module.LAYER, view(ref, d, [], W.asks(ref)))]


def case_7(module, ctx=None):
    """No ref_to points at an attribute that is itself a delegate, or at nothing."""
    out = []
    for kind, d in _dicts(module).items():
        for name, fn in d.items():
            target_of = getattr(fn, 'legacy', None)
            if not target_of:
                continue
            mod, attr = target_of
            target = getattr(importlib.import_module(mod), attr, None)
            if target is None:
                out.append('%s: %s %s points at %s.%s, which is not there' % (impl_id(module), kind, name, mod, attr))
            elif hasattr(target, 'legacy'):
                out.append('%s: %s %s points at %s.%s, which is itself a delegate' % (impl_id(module), kind, name, mod, attr))
    return out


def case_8(module, ctx=None):
    """Every OUTPUTS step the recipe provides declares those keys (a rule or a gate answers answer and why)."""
    out = []
    e = recipe_of(module) or {}
    ruled = {s.get('id') for s in list(e.get('gates') or []) + list(e.get('rules') or [])}
    for s in _steps(e):
        keys = S.OUTPUTS.get(s.get('id'))
        if not keys:
            continue
        has = set(s.get('out') or {}) | ({'answer', 'why'} if s.get('id') in ruled else set())
        out += ['%s, %s: it does not return %s, which code outside the layer reads' % (impl_id(module), s['id'], k)
                for k in keys if k not in has]
    return out


def _version_of(module):
    v = getattr(module, 'VERSION', None)
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _parent_of(module):
    """The loaded module the PARENT names; None when it names none, names no implementation id, or does not load."""
    parent_id = getattr(module, 'PARENT', None)
    return layers.load(parent_id) if isinstance(parent_id, str) else None


def _gates_and_rules(recipe):
    return {s['id']: s for key in ('gates', 'rules') for s in ((recipe or {}).get(key) or []) if isinstance(s, dict) and s.get('id')}


def case_9(module, ctx=None):
    """The lineage is sound.

    A version above 1 names its PARENT: the same layer's, a lower version, one that loads, with no repeat in its lineage and no more
    than versions.DEPTH versions. The version holds every name of its parent's four tables and every (group, part) of its words and
    layout (A2-R1, A2-R2). A lineage that is not sound is reported alone: comparing tables with it would only add noise."""
    me, parent_id = impl_id(module), getattr(module, 'PARENT', None)
    if parent_id is None:
        return ['%s: a version above 1 names the version it extends (PARENT)' % me] if _version_of(module) > 1 else []
    if not isinstance(parent_id, str) or not re.fullmatch(S.IMPL_RE, parent_id):
        return ['%s: PARENT %r is no implementation id' % (me, parent_id)]
    layer, v = parent_id.split('/')
    out = []
    if layer != getattr(module, 'LAYER', None):
        out.append("%s: its PARENT %s is another layer's" % (me, parent_id))
    if int(v[1:]) >= _version_of(module):
        out.append('%s: its PARENT %s is not a lower version' % (me, parent_id))
    if out:
        return out
    parent = layers.load(parent_id)
    if parent is None:
        return ['%s: its PARENT %s does not load' % (me, parent_id)]
    try:
        ids = V.chain(parent_id)
    except L.ModelFault as exc:
        return ['%s: the lineage of its PARENT is not sound: %s' % (me, exc)]
    if me in ids:
        return ['%s: it repeats in its own lineage: %s' % (me, ', '.join(ids))]
    for attr, key in V.TABLES:
        out += ['%s: it drops the %s %s of its parent' % (me, key, name)
                for name in sorted(set(getattr(parent, attr, None) or {}) - set(getattr(module, attr, None) or {}))]
    for attr in ('WORDS', 'LAYOUT'):
        for group, parts in (getattr(parent, attr, None) or {}).items():
            out += ['%s: it drops the %s %s.%s of its parent' % (me, attr.lower(), group, part)
                    for part in parts if part not in ((getattr(module, attr, None) or {}).get(group) or {})]
    return out


def case_10(module, ctx=None):
    """The version publishes every surface function its PARENT does."""
    parent = _parent_of(module)
    if parent is None:
        return []
    return ['%s: it does not publish %s, which its parent does' % (impl_id(module), name) for name in V.SURFACE
            if callable(getattr(parent, name, None)) and not callable(getattr(module, name, None))]


def case_11(module, ctx=None):
    """The resolved recipe keeps what the parent fixes.

    The handlers, every step id, the fixed fields of each step, every gate and rule, unique ids and only_if targets that exist:
    lineage.recipe_faults over the recipe the version brings against its parent's (alone, for a version with no parent). A recipe
    that cannot be read is case 1's to report."""
    mine = recipe_of(module)
    if mine is None:
        return []
    parent = _parent_of(module)
    theirs = recipe_of(parent) if parent is not None else None
    return ['%s: %s' % (impl_id(module), f) for f in L.recipe_faults(theirs, mine, getattr(module, 'LAYER', None))]


def _test_exists(where):
    """'file.py::test_name': the file is in the sutra-ui folder and holds a def of that name."""
    file, sep, name = str(where).partition('::')
    base = Path(layers.HERE).parent
    path = base / file
    try:
        return bool(sep and file and re.fullmatch(r'\w+', name) and path.is_file() and base.resolve() in path.resolve().parents
                    and re.search(r'def %s\b' % name, path.read_text(encoding='utf-8')))
    except OSError:
        return False


def case_12(module, ctx=None):
    """Every gate or rule the version replaces is declared in TIGHTENS.

    A gate or rule whose code or check the version holds as something other than its parent's (the same object, or a ref_to to the
    same target) is a key of TIGHTENS, {step id: 'test_file.py::test_name'}, and the test is there, in the sutra-ui folder: it is
    the author's proof that the replacement lets through nothing the parent held back (lineage.tightens, A2-R6). Every key names a
    gate or a rule of the recipe, and a version with no parent tightens nothing."""
    me, tight = impl_id(module), getattr(module, 'TIGHTENS', None) or {}
    if not isinstance(tight, dict):
        return ['%s: TIGHTENS is a dict of a step id and the test that proves it' % me]
    parent = _parent_of(module)
    if parent is None:
        return ['%s: TIGHTENS names %s, and there is no parent to tighten' % (me, ', '.join(sorted(str(k) for k in tight)))] if tight else []
    mine = recipe_of(module)
    if mine is None:
        return []
    ruled, pruled, out = _gates_and_rules(mine), _gates_and_rules(recipe_of(parent)), []
    for sid, step in ruled.items():
        before = pruled.get(sid) or step
        for attr, key in (('CODE', 'code'), ('CHECK', 'check')):
            now = (getattr(module, attr, None) or {}).get(step.get(key))
            was = (getattr(parent, attr, None) or {}).get(before.get(key))
            if not V.same_entry(now, was) and sid not in tight:
                out.append('%s: it replaces the %s of %s and does not list it in TIGHTENS' % (me, key, sid))
    for sid, where in tight.items():
        if sid not in ruled:
            out.append('%s: TIGHTENS names %s, which is no gate or rule of its recipe' % (me, sid))
        if not _test_exists(where):
            out.append('%s: TIGHTENS %s names a test that is not there: %s' % (me, sid, where))
    return out


def case_13(module, ctx=None):
    """The assembled definitions validate with this version's resolved recipe in its layer's place."""
    try:
        return ['%s: %s' % (impl_id(module), f) for f in V.definition_faults(module)]
    except (AttributeError, KeyError, TypeError) as exc:
        return ['%s: the definitions cannot be read with its recipe (%s: %s)' % (impl_id(module), type(exc).__name__, exc)]


def cases():
    """A1.21's cases, A2.7's and A3.4.8's, in order: [(number, what it holds, the function)]."""
    return [(n, fn.__doc__.strip().split('\n')[0], fn) for n, fn in (
        (1, case_1), (2, case_2), (3, case_3), (4, case_4), (5, case_5), (6, case_6), (7, case_7), (8, case_8),
        (9, case_9), (10, case_10), (11, case_11), (12, case_12), (13, case_13),
        (14, case_14_function_template),
    )]


# ---- case 14: the function template (A3.4.8) ---------------------------------------------------------------------------------
#: the words a function's goal group carries in a version (A3.4.2): text parts are one clause of at most 400 characters, item
#: parts one to twelve lines of at most 160. does and skills are older prompt text, the pane's through _plain
_TEXT_PARTS = ('does', 'done', 'role_is')
_ITEM_PARTS = ('skills', 'role_may', 'role_procedure', 'role_patterns')
#: the words that sit beside Priority's answer shape on the agent's side: the screen's words for the same answers, which a model
#: that copies them would answer in outside the contract (accept, counter, reject)
_SCREEN_ANSWERS = re.compile(r'said yes|asked for less|said no', re.I)


def _constant_lines(layer):
    """The interface's own words for a function, as (where, text): its role, what it is not, each never line, who it hands on to
    and each line of the working agreement. What the agent is sent beside a version's words."""
    t = S.FUNCTION_TEMPLATE.get(layer) or {}
    out = [('the function template, role', t.get('role')), ('the function template, is_not', t.get('is_not')),
           ('the function template, hands_on', t.get('hands_on'))]
    out += [('the function template, never line %d' % i, x) for i, x in enumerate(t.get('never') or (), 1)]
    return [(w, x) for w, x in out + [('the working agreement, line %d' % i, x) for i, x in enumerate(S.DEPARTMENT_AGREEMENT, 1)]
            if isinstance(x, str)]


def _role_lines(words):
    """The version's role words, as (where, line): goal.role_is, and each line of role_may, role_procedure and role_patterns."""
    out = []
    for part in ('role_is', 'role_may', 'role_procedure', 'role_patterns'):
        got = (words.get(part) or {})
        if part == 'role_is':
            out += [('goal.role_is', got['text'])] if isinstance(got.get('text'), str) else []
        else:
            out += [('goal.%s line %d' % (part, i), x) for i, x in enumerate(got.get('items') if isinstance(got.get('items'), list) else (), 1)
                    if isinstance(x, str)]
    return out


def _word_faults(who, words):
    """FT-2 and FT-6: every word part there, with its layout, within its limit, and one line where one line is required."""
    out = []
    for part in _TEXT_PARTS + _ITEM_PARTS + ('role_block',):
        if part not in words:
            out.append('%s: goal.%s has no words' % (who, part))
    for part in _TEXT_PARTS:
        text = (words.get(part) or {}).get('text') if part in words else None
        if part in words and not isinstance(text, str):
            out.append('%s: goal.%s has no text' % (who, part))
        elif isinstance(text, str):
            if not text.strip():
                out.append('%s: goal.%s is empty' % (who, part))
            if len(text) > 400:
                out.append('%s: goal.%s is %d characters, and at most 400 are allowed' % (who, part, len(text)))
            if '\n' in text:
                out.append('%s: goal.%s is one clause, and this has a line break' % (who, part))
    for part in _ITEM_PARTS:
        lines = (words.get(part) or {}).get('items') if part in words else None
        if part in words and not isinstance(lines, list):
            out.append('%s: goal.%s has no list of lines' % (who, part))
        elif isinstance(lines, list):
            if not lines:
                out.append('%s: goal.%s has no line' % (who, part))
            if len(lines) > 12:
                out.append('%s: goal.%s has %d lines, and at most 12 are allowed' % (who, part, len(lines)))
            for i, x in enumerate(lines, 1):
                if not isinstance(x, str) or not x.strip():
                    out.append('%s: goal.%s line %d is empty' % (who, part, i))
                elif len(x) > 160:
                    out.append('%s: goal.%s line %d is %d characters, and at most 160 are allowed' % (who, part, i, len(x)))
                elif '\n' in x:
                    out.append('%s: goal.%s line %d is one line, and this has a line break' % (who, part, i))
    return out


def _block_faults(who, layer, words, layout):
    """FT-3 and FT-5: the layout places all eight inputs, and the block compiled from this version's own words and the
    interface's constants is at most S.ROLE_BLOCK_MAX characters."""
    text = layout.get('role_block')
    if not isinstance(text, str):
        return ['%s: goal.role_block has no layout' % who]
    out = []
    for name in S.ROLE_INPUTS:
        if '{{%s}}' % name not in text:
            out.append('%s: goal.role_block leaves out {{%s}}, so the agent would not be told %s' % (who, name, R.INPUT_SAYS.get(name, name)))
    try:
        got = [(words.get(p) or {}) for p in ('role_is', 'role_may', 'role_procedure', 'role_patterns')]
        if out or not isinstance(got[0].get('text'), str) or not all(isinstance(g.get('items'), list) for g in got[1:]):
            return out                                                       # the missing or mistyped part is already named
        block = P.compile_layout(text, {}, None, S.role_inputs(layer, got[0]['text'], got[1]['items'], got[2]['items'], got[3]['items']),
                                 'goal.role_block')
    except (ValueError, KeyError, TypeError) as exc:
        return out + ['%s: goal.role_block cannot be compiled (%s)' % (who, exc)]
    if len(block) > S.ROLE_BLOCK_MAX:
        out.append('%s: goal.role_block compiles to %d characters, and at most %d are allowed' % (who, len(block), S.ROLE_BLOCK_MAX))
    return out


def _banned_faults(who, layer, words):
    """FT-4: the screen's banned words in goal.done (the owner reads it); the agent's in every role word and every constant (not
    in goal.does or goal.skills, older prompt text); for Priority, nothing that says it orders, and none of the screen's words
    for its answers beside the answer shape."""
    out = []
    done = (words.get('done') or {}).get('text')
    m = re.search(S.TEMPLATE_BANNED, done, re.I) if isinstance(done, str) else None
    if m:
        out.append('%s: goal.done says "%s", a word the owner\'s screen does not use' % (who, m.group(0)))
    agent = _role_lines(words) + _constant_lines(layer)
    for where, text in agent:
        m = re.search(S.TEMPLATE_BANNED_AGENT, text, re.I)
        if m:
            out.append('%s: %s says "%s", a word this department does not use' % (who, where, m.group(0)))
    never_say = S.TEMPLATE_NEVER_SAY.get(layer)
    if never_say:
        for where, text in agent + ([('goal.done', done)] if isinstance(done, str) else []):
            m = re.search(never_say, text, re.I)
            if m:
                out.append('%s: %s says "%s", and %s never says which work runs next' % (who, where, m.group(0), S.TITLE[layer]))
    if layer == 'priority':
        for where, text in _role_lines(words):
            m = _SCREEN_ANSWERS.search(text)
            if m:
                out.append('%s: %s says "%s", the screen\'s word; beside the answer shape it says accept, counter or reject' % (who, where, m.group(0)))
    return out


def case_14_function_template(module, ctx=None):
    """A function version keeps the function template: its words, its role block and its boundaries (FT-1 to FT-6, FT-9, FT-10)."""
    out = []
    try:
        if isinstance(module, str):                                          # an implementation id, as W3-PINS reads a pin
            module = importlib.import_module('layers').load(module)
        layer = getattr(module, 'LAYER', None)
        if module is None or layer not in S.FUNCTION_LAYERS:
            return []                                                         # Root, and an id that loads nothing
        words, layout = getattr(module, 'WORDS', None) or {}, getattr(module, 'LAYOUT', None) or {}
        if not words:
            return []                                                         # a stub with no words of its own: nothing to compare
        who, title = impl_id(module), S.TITLE[layer]
        from template_checks import agreement_faults, function_template_faults, hands_on_faults
        entry = S.FUNCTION_TEMPLATE.get(layer)
        # FT-1 and FT-10: the interface's entry for this function is sound, and its hands_on names only whom it sends to
        out += ['%s: the function template of %s: %s' % (who, title, f[len(title) + 2:] if f.startswith(title + ': ') else f)
                for f in function_template_faults(layer, entry)]
        out += ['%s: %s' % (who, f) for f in agreement_faults(S.DEPARTMENT_AGREEMENT)]
        if isinstance(entry, dict):
            out += ['%s: hands_on of %s: %s' % (who, title, f) for f in hands_on_faults(layer, entry.get('hands_on'))]
        goal, form = words.get('goal') or {}, layout.get('goal') or {}
        out += _word_faults(who, goal)                                        # FT-2, FT-6
        out += _block_faults(who, layer, goal, form)                          # FT-3, FT-5
        out += _banned_faults(who, layer, goal)                               # FT-4
        for part in ('role_may', 'role_procedure'):                           # FT-9
            lines = (goal.get(part) or {}).get('items')
            for i, line in enumerate(lines if isinstance(lines, list) else (), 1):
                never = S.says_a_never(layer, line) if isinstance(line, str) else None
                if never:
                    out.append('%s: goal.%s line %d says what %s never does: %s' % (who, part, i, title, never))
    except Exception as exc:  # noqa: BLE001 -- a case never raises on a stub: it says what it could not read
        out.append('%s: the function template could not be read (%s)' % (impl_id(module) if module is not None and not isinstance(module, str) else module, exc))
    return out
