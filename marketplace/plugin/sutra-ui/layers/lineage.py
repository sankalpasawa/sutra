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
