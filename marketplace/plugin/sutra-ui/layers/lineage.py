"""layers/lineage.py -- the law of a child version, as pure functions (PRD amendment A2, A2-LAW; design/PRD-FIVE-FUNCTIONS-A2.md).

A new version of a layer names the version it extends (PARENT) and writes only what differs (A2.4). This module is the law that
decides what "only what differs" may be, over plain dicts, with no file, no clock and no runtime state:

    merge_words, merge_layout   a child's prompt words per (group, part, field) and its layout per (group, part)      A2-R8, A2-D6
    merge_recipe                the parent's recipe with a keyed patch laid over it; ModelFault on a patch that breaks the law   A2.5
    recipe_faults               the substitutability law: a child recipe against its parent (or alone, with no parent)  A2-R4, R5, R7
    rank, tightens              admit below wait below refuse: a replaced gate body lets through nothing its parent held back  A2-R6, D5

Every function leaves its arguments as they were and returns copies that share no dict or list with them. A patch has no way to
drop a step, a gate, a rule or a handler (A2-D3): removing behaviour takes a replacement body. Two laws judge a recipe, one after
the other; this is the first (child against parent). The second, the runtime's own `engine_runtime.validate` with the child in
its layer's place, is `layers.definition_faults` (A2-INHERIT) and is not called here.

Step fields are two lists, and a field in neither is refused: STEP_FIXED (an inherited step keeps the parent's value: changing what
a step is for, how it is judged or when it runs is a new step, not an overlay) and STEP_FREE (a child may change it). A field a
later package adds to a recipe step is classified here, with a reason, the day it is added: test_layer_lineage.py reads every
recipe on disk and fails on one that is in neither list.

Nothing here imports the runtime at import time: engine_runtime (NATURES, RUNGS) and layer_schema (ANY) are reached through the
lazy proxies, inside the functions, because tests reload engine_runtime and a held module object would be a stale one.
"""
import copy

from layers import R, S  # lazy proxies: never a module object held across a reload


class ModelFault(Exception):
    """A patch, a lineage or a recipe that does not hold. Deliberately not a ValueError (like layer_schema.SchemaFault): an
    `except ValueError` path never swallows it."""


#: the only keys a recipe patch holds; `parent` must equal the version's PARENT (A2-INHERIT checks it)
PATCH_KEYS = ('parent', 'set', 'gates', 'rules', 'steps', 'on')
#: what `set` may change; the start, the template and what an engine reads are fixed
TOP_SET = ('description', 'skills')
#: where a new step goes in its list: after or before a step of that list, never both
POSITION = ('after', 'before')
#: step fields a child may not change on a step it inherits: equal to the parent's (`out` may gain keys, every enum keeps its
#: members; see enums_kept)
STEP_FIXED = ('nature', 'check', 'answer', 'out', 'or', 'only_if', 'stringency', 'each', 'files', 'by_hand')
#: step fields a child may change (null deletes one)
STEP_FREE = ('name', 'born', 'code', 'prompt', 'draft', 'ceiling', 'facts', 'tools', 'timeout_s', 'below')
STEP_FIELDS = ('id',) + STEP_FIXED + STEP_FREE
#: a gate's answers, least strict first: a replacement may answer a stricter one than its parent, never a laxer one
GATE_ORDER = ('admit', 'wait', 'refuse')

#: the step fields whose value is a name or a word, a list, or a number; a value of another kind is refused with the step's name
_TEXT = ('nature', 'check', 'answer', 'only_if', 'stringency', 'name', 'born', 'code', 'prompt', 'draft', 'ceiling', 'below')
_LISTS = ('facts', 'tools')
_HANDLER_KEYS = ('when', 'steps')


# ---- reading a recipe ---------------------------------------------------------------------------------------------------
def handler_key(h):
    """(msg_type, word or S.ANY): the pair contract case 2 and S.hears use. A handler's `when` may lack its word."""
    w = (h or {}).get('when') or {}
    return (w.get('msg_type'), w.get('word') or S.ANY)


def all_steps(recipe):
    """Every gate, rule and step of a recipe, in order: gates, rules, steps, then each handler's steps. An item that is not
    an object is not a step and is left out (recipe_faults says so)."""
    r = recipe if isinstance(recipe, dict) else {}
    out = []
    for key in ('gates', 'rules', 'steps'):
        out += _items(r.get(key))
    for h in _items(r.get('on')):
        out += _items(h.get('steps'))
    return out


def step_ids(recipe):
    """The id of every step of all_steps, in order; a step with no id is left out."""
    return [s['id'] for s in all_steps(recipe) if s.get('id')]


def only_if_target(expr):
    """The step an only_if reads: 'adapt.source.source=library' -> 'adapt.source', the part before '=' without its last
    dotted segment."""
    return str(expr).partition('=')[0].rsplit('.', 1)[0]


def _items(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def _handler_keys(recipe):
    return {handler_key(h) for h in _items((recipe or {}).get('on'))}


def _say(key):
    return '%s/%s' % tuple(str(x) for x in key)


def _by_id(steps):
    """{id: step}, the first step of an id when a recipe uses one twice (recipe_faults names that)."""
    out = {}
    for s in steps:
        if s.get('id'):
            out.setdefault(s['id'], s)
    return out


def enums_kept(parent_out, child_out):
    """None when every key of the parent's `out` is in the child's, every list value (an enum) has the same members as a set,
    and every other value (a kind such as 'str') is as it was; else why not, in a sentence that does not name the step. The
    child may add keys."""
    parent = parent_out if isinstance(parent_out, dict) else {}
    child = child_out if isinstance(child_out, dict) else {}
    for k, v in parent.items():
        if k not in child:
            return "the out key %s is gone: a version may add keys to out and never drops one" % k
        c = child[k]
        if isinstance(v, list):
            if not isinstance(c, list) or any(x not in v for x in c) or any(x not in c for x in v):
                return "out.%s has other values than the parent's: an enum keeps the same members" % k
        elif c != v:
            return "out.%s is not what the parent has: a version keeps the kind of every key" % k
    return None


# ---- words and layout (L1) ----------------------------------------------------------------------------------------------
def merge_words(parent, own):
    """A child's WORDS laid over its parent's, per (group, part, field): the child's value replaces, the other fields of the
    part are the parent's, and a new part or a new group is added. A part the child names with no field adds nothing. Both
    arguments may be None or {}; the result is a deep copy that shares nothing with either."""
    out = copy.deepcopy(parent) if parent else {}
    for group, parts in (own or {}).items():
        for part, fields in (parts or {}).items():
            if fields:
                out.setdefault(group, {}).setdefault(part, {}).update(copy.deepcopy(fields))
    return out


def merge_layout(parent, own):
    """A child's LAYOUT laid over its parent's, per (group, part): the child's template replaces the parent's whole, and a part
    the child does not mention keeps the parent's. Both arguments may be None or {}; the result shares nothing with either."""
    out = copy.deepcopy(parent) if parent else {}
    for group, parts in (own or {}).items():
        for part, template in (parts or {}).items():
            out.setdefault(group, {})[part] = copy.deepcopy(template)
    return out


# ---- the recipe patch (L2) ----------------------------------------------------------------------------------------------
def merge_recipe(parent, patch, layer):
    """The parent's recipe with the patch laid over it (A2.5): `set` first, then gates, rules and steps, then each handler's
    steps. The arguments are not changed. ModelFault, in plain words that name the step, on a patch that is not an object, holds
    a key outside PATCH_KEYS, sets more than TOP_SET, or breaks the keyed-list law (see _merge_keyed). `layer` is the layer's
    name, for the faults that name no step."""
    who = 'the %s recipe patch' % layer if layer else 'the recipe patch'
    if not isinstance(patch, dict):
        raise ModelFault('%s is an object that holds %s; this one is not an object' % (who, ', '.join(PATCH_KEYS)))
    if not isinstance(parent, dict):
        raise ModelFault('%s has no recipe to lay over: the parent recipe is not an object' % who)
    bad = sorted(str(k) for k in patch if k not in PATCH_KEYS)
    if bad:
        raise ModelFault('%s holds %s only; it has %s' % (who, ', '.join(PATCH_KEYS), ', '.join(bad)))
    if 'parent' in patch and not (isinstance(patch['parent'], str) and patch['parent']):
        raise ModelFault('%s names its parent as a string such as identity/v1' % who)
    out = copy.deepcopy(parent)
    _set_top(out, patch.get('set'), who)
    for key in ('gates', 'rules', 'steps'):
        items = _patch_list(patch.get(key), '%s, %s' % (who, key))
        if items:
            _merge_keyed(out, out.setdefault(key, []), items, 'the %s' % key)
    handlers = _patch_list(patch.get('on'), '%s, on' % who)
    seen = set()
    for ph in handlers:
        extra = sorted(str(k) for k in ph if k not in _HANDLER_KEYS)
        when = ph.get('when')
        if not isinstance(when, dict) or not when.get('msg_type'):
            raise ModelFault('%s: a handler of the patch names the message it hears, as when with a msg_type and a word' % who)
        key = handler_key(ph)
        if extra:
            raise ModelFault('the handler for %s: a patch carries when and steps for a handler, nothing else (it has %s)'
                             % (_say(key), ', '.join(extra)))
        h = next((x for x in _items(out.get('on')) if handler_key(x) == key), None)
        if h is None:
            raise ModelFault('no handler hears %s: a version hears what its parent hears, and a patch cannot add a handler'
                             % _say(key))
        if key in seen:
            raise ModelFault('the handler for %s is named twice in the patch' % _say(key))
        seen.add(key)
        steps = _patch_list(ph.get('steps'), 'the handler for %s' % _say(key))
        if steps:
            _merge_keyed(out, h.setdefault('steps', []), steps, 'the steps of the handler for %s' % _say(key))
    return out


def _patch_list(items, label):
    if items is None:
        return []
    if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
        raise ModelFault('%s is a list of objects' % label)
    return items


def _set_top(out, change, who):
    """`set`: description and skills only; a null deletes the key."""
    if change is None:
        return
    if not isinstance(change, dict):
        raise ModelFault('%s: set is an object' % who)
    for k, v in change.items():
        if k not in TOP_SET:
            raise ModelFault('%s: set may change %s and nothing else; the start, the template and what an engine reads are '
                             'fixed (it has %s)' % (who, ' and '.join(TOP_SET), k))
        if v is None:
            out.pop(k, None)
        elif k == 'description' and not isinstance(v, str):
            raise ModelFault('%s: the description is words' % who)
        elif k == 'skills' and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise ModelFault('%s: the skills are a list of words' % who)
        else:
            out[k] = copy.deepcopy(v)


def _merge_keyed(recipe, items, patch_items, label):
    """One keyed list (gates, rules, steps, or a handler's steps) of `recipe`, changed in place: an item whose id is in `items`
    overlays that step where it stands; an item whose id is new is inserted after or before a step of `items`, or appended.
    The ids of the recipe's other lists are not new: an inherited step is overlaid in its own list, and an id is used once."""
    elsewhere = {s['id'] for s in all_steps(recipe) if s.get('id') and all(s is not x for x in items)}
    named = set()
    for raw in patch_items:
        sid = raw.get('id')
        if not (isinstance(sid, str) and sid):
            raise ModelFault('%s: an item of the patch has no id' % label)
        if sid in named:
            raise ModelFault('%s: the patch names this step twice' % sid)
        named.add(sid)
        unknown = sorted(str(k) for k in raw if k not in STEP_FIELDS and k not in POSITION)
        if unknown:
            raise ModelFault('%s: %s is no field of a step; a step has %s' % (sid, ', '.join(unknown), ', '.join(STEP_FIELDS)))
        p = copy.deepcopy(raw)
        after, before = (_anchor(p.pop(k, None), sid, k) for k in POSITION)
        cur = next((s for s in items if s.get('id') == sid), None)
        if cur is not None:
            if after or before:
                raise ModelFault('%s: this step is inherited, so it is overlaid where it stands; after and before are for '
                                 'new steps' % sid)
            _overlay(cur, p, sid)
            continue
        if sid in elsewhere:
            raise ModelFault('%s: this id is a step of another list of the recipe; an inherited step is overlaid in its own '
                             'list, and a new step takes an id nothing uses' % sid)
        if after and before:
            raise ModelFault('%s: after and before together; a new step goes after one step or before one' % sid)
        new = {k: v for k, v in p.items() if v is not None}
        _new_step_faults(new, sid)
        anchor = after or before
        if not anchor:
            items.append(new)
            continue
        at = next((i for i, s in enumerate(items) if s.get('id') == anchor), None)
        if at is None:
            raise ModelFault('%s: the step it goes %s, %s, is not in %s' % (sid, 'after' if after else 'before', anchor, label))
        items.insert(at + 1 if after else at, new)


def _anchor(value, sid, which):
    if value is None:
        return None
    if not (isinstance(value, str) and value):
        raise ModelFault('%s: %s names the id of a step' % (sid, which))
    return value


def _overlay(cur, p, sid):
    """The patch's fields laid on an inherited step: a free field replaces (null deletes), a fixed field must be the parent's,
    `out` may gain keys."""
    for k, v in p.items():
        if k == 'id':
            continue
        if k == 'out':
            if v is not None and not isinstance(v, dict):
                raise ModelFault('%s: out is an object of keys and what each holds' % sid)
            why = enums_kept(cur.get('out'), v)
            if why:
                raise ModelFault('%s: %s' % (sid, why))
            if v:
                cur['out'] = v
        elif k in STEP_FIXED:
            if cur.get(k) != v:
                raise ModelFault("%s: %s is the parent's and a version leaves it as it is; changing what a step is for, how it "
                                 "is judged or when it runs makes a new step" % (sid, k))
        elif v is None:
            cur.pop(k, None)
        else:
            _kind_faults(sid, k, v)
            cur[k] = v


def _kind_faults(sid, k, v):
    if k in _TEXT and not (isinstance(v, str) and v):
        raise ModelFault('%s: %s is a word' % (sid, k))
    if k in _LISTS and not isinstance(v, list):
        raise ModelFault('%s: %s is a list' % (sid, k))
    if k == 'timeout_s' and not (isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0):
        raise ModelFault('%s: timeout_s is a number of seconds' % sid)


def _new_step_faults(step, sid):
    """What the definitions require of a step that is new: an id, a name, a nature, a rung it is born at, a check, and either
    code or a prompt with its draft and the shape of its answer. Raises ModelFault; the nature and the rung are read from
    engine_runtime when asked (a reloaded runtime is the one that answers)."""
    need = [k for k in ('name', 'nature', 'born', 'check') if not step.get(k)]
    if need:
        raise ModelFault('%s: a new step needs %s' % (sid, ', '.join(need)))
    for k, v in step.items():
        if k == 'out':
            if not isinstance(v, dict):
                raise ModelFault('%s: out is an object of keys and what each holds' % sid)
        elif k != 'id':
            _kind_faults(sid, k, v)
    if step['nature'] not in R.NATURES:
        raise ModelFault('%s: nature is none of %s' % (sid, ', '.join(R.NATURES)))
    if step['born'] not in R.RUNGS:
        raise ModelFault('%s: born is not a rung (%s)' % (sid, ', '.join(R.RUNGS)))
    if step.get('code'):
        return
    if not step.get('prompt'):
        raise ModelFault('%s: a new step names code, or a prompt with its draft and the shape of its answer' % sid)
    miss = [k for k in ('draft', 'out') if not step.get(k)]
    if miss:
        raise ModelFault('%s: a step with a prompt also names its %s' % (sid, ' and '.join(
            'draft' if k == 'draft' else 'out (the shape of its answer)' for k in miss)))


# ---- the substitutability law (L3) --------------------------------------------------------------------------------------
def recipe_faults(parent, child, layer):
    """The first law over a recipe, child against parent (A2-R4, A2-R5, A2-R7): [] when it holds, else one plain sentence for
    each thing that does not, in the order the checks run:
      1  the handlers are the parent's (a version hears what its parent hears)
      2  every step of the parent is in the child
      3  on each such step every STEP_FIXED field is the parent's (`out` through enums_kept: the child may add keys)
      4  every gate and rule of the parent is still a gate or a rule of the child
      5  ids are used once across gates, rules, steps and handler steps
      6  no only_if points at an id that is no step of the child
    With parent None only the child's own soundness is judged, 5 and 6. A step that is missing altogether is said once, at 2, and
    not again at 4. The runtime's own rules (a unit starts and ends with a step by code, an id another layer uses) are not seen
    here: layers.definition_faults is the second law. `layer` is the layer's name, kept for symmetry with merge_recipe."""
    if not isinstance(child, dict):
        return ['the recipe is not an object']
    if parent is not None and not isinstance(parent, dict):
        return ["the parent's recipe is not an object"]
    out = []
    steps = all_steps(child)
    cmap = _by_id(steps)
    if parent is not None:
        pk, ck = _handler_keys(parent), _handler_keys(child)
        for key in sorted(pk - ck, key=_say):
            out.append('the handler for %s is gone: a version hears what its parent hears' % _say(key))
        for key in sorted(ck - pk, key=_say):
            out.append('the handler for %s is new: a version hears what its parent hears and no more' % _say(key))
        pgr = [s['id'] for key in ('gates', 'rules') for s in _items(parent.get(key)) if s.get('id')]
        for sid, ps in _by_id(all_steps(parent)).items():
            if sid not in cmap:
                out.append('%s: a version keeps every %s of its parent, and this one is gone'
                           % (sid, 'gate and rule' if sid in pgr else 'step'))
        for sid, ps in _by_id(all_steps(parent)).items():
            cs = cmap.get(sid)
            if cs is None:
                continue
            for f in STEP_FIXED:
                if f == 'out':
                    why = enums_kept(ps.get('out'), cs.get('out'))
                    if why:
                        out.append('%s: %s' % (sid, why))
                elif ps.get(f) != cs.get(f):
                    out.append("%s: %s is the parent's and a version leaves it as it is" % (sid, f))
        cgr = {s['id'] for key in ('gates', 'rules') for s in _items(child.get(key)) if s.get('id')}
        for sid in pgr:
            if sid in cmap and sid not in cgr:
                out.append('%s: a gate or a rule of the parent stays a gate or a rule' % sid)
    seen, said = set(), set()
    for s in steps:
        sid = s.get('id')
        if not sid:
            out.append('a step has no id: %s' % (s.get('name') or 'it has no name either'))
        elif sid in seen and sid not in said:
            said.add(sid)
            out.append('%s: this id is used by more than one step' % sid)
        seen.add(sid)
    for s in steps:
        if s.get('only_if'):
            target = only_if_target(s['only_if'])
            if target not in cmap:
                out.append('%s: only_if points at %s, which is no step of this recipe' % (s.get('id') or 'a step', target))
    return out


# ---- gate ranking (L4) --------------------------------------------------------------------------------------------------
def rank(answer):
    """admit 0, wait 1, refuse 2 (A2-R6, A2-D5); ValueError for anything else."""
    if not isinstance(answer, str) or answer not in GATE_ORDER:
        raise ValueError('%r is no answer of a gate; a gate answers %s' % (answer, ', '.join(GATE_ORDER)))
    return GATE_ORDER.index(answer)


def _answer_of(got):
    """The answer of what a gate body returned: (answer, why) or {'answer': ...}."""
    if isinstance(got, (tuple, list)) and got:
        return got[0]
    if isinstance(got, dict):
        return got.get('answer')
    raise ValueError("a gate body returns (answer, why) or {'answer': ...}, not %r" % (got,))


def tightens(parent_fn, child_fn, contexts):
    """[] when the child's body answers at least as strictly as the parent's on every context, else one sentence for each context
    where it answers a laxer one (A2-R6). `contexts` are argument tuples for the body, (ctx, step, item); both bodies are called
    with each. A body that raises, or answers outside GATE_ORDER, raises here: the author's test shows it."""
    out = []
    for i, args in enumerate(contexts):
        p, c = rank(_answer_of(parent_fn(*args))), rank(_answer_of(child_fn(*args)))
        if c < p:
            out.append('context %d: the child answers %s where its parent answers %s' % (i, GATE_ORDER[c], GATE_ORDER[p]))
    return out
