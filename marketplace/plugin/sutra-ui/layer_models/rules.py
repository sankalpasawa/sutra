"""The class rules (A4.4.2), checked on the classes themselves: a core class when it is made (SutraModel.__pydantic_init_subclass__
calls `check_class`), an owner model when it is compiled.

    R1  inherit      a child keeps every field of its base               child_faults
    R2  narrow       an inherited field is as tight or tighter           narrows
    R3  substitute   a value the child takes, the base takes             substitutable
    R5  mixins       two bases that disagree on a field are refused      check_class
    R6  nest         the nest graph has no cycle and is shallow          nest_cycle, nest_depth
    R10 versions     same, tightens, widens or mixed                     compare

The rules read the annotation objects of types.py, which carry their bounds. A sentence names the field and what the child lets
in that the base did not: 'name: allows more than 80 characters'."""
import random
import types as _pytypes
from typing import Annotated, Union, get_args, get_origin

from pydantic import BaseModel, TypeAdapter

from .base import Closed, Mixin, Open, SutraModel, is_abstract
from .types import AnyOf, Anything, Bare, Bool, Enum, Int, Items, MapOf, Num, Str, _same

_ROOTS = (SutraModel, Closed, Open, Mixin, BaseModel)
_KINDS = (Str, Int, Enum, Bool, Items, AnyOf, MapOf, Bare, Anything)
_UNIONS = (Union, getattr(_pytypes, 'UnionType', Union))


# ---- the type of a field, as a small tree --------------------------------------------------------------------------------
def _tree(ann, meta):
    meta = list(meta)
    if get_origin(ann) is Annotated:
        inner, *more = get_args(ann)
        return _tree(inner, more + meta)
    leaf = next((m for m in meta if isinstance(m, _KINDS)), None)
    if isinstance(leaf, AnyOf):
        args = get_args(ann)
        real = [a for a in args if a is not type(None)]
        if len(real) == 1 and len(args) == 2:
            return ('nullable', _tree(real[0], ()))
        return ('anyof', [_tree(a, ()) for a in args])
    if isinstance(leaf, Items):
        args = get_args(ann)
        return ('items', leaf, _tree(args[0], ()) if args else ('any', None))
    if isinstance(leaf, MapOf):
        args = get_args(ann)
        return ('map', leaf, _tree(args[1], ()) if len(args) > 1 else ('any', None))
    if leaf is not None:
        return ('leaf', leaf)
    if ann is type(None):
        return ('none',)
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return ('model', ann)
    return ('any', ann)


def type_tree(field_info):
    """A field's type as a tree: ('leaf', obj), ('items', Items, inner), ('map', MapOf, inner), ('nullable', inner),
    ('anyof', [inner]), ('model', cls), ('none',) or ('any', annotation)."""
    return _tree(field_info.annotation, field_info.metadata)


# ---- R2: narrows ---------------------------------------------------------------------------------------------------------
def _enum_values(o):
    return list(o.values)


def _leaf_faults(a, b, path):
    """The sentences for leaf `a` (child) against leaf `b` (base)."""
    out = []
    if isinstance(b, Anything):
        return out
    if isinstance(b, Enum):
        if not isinstance(a, Enum):
            return ['%s: changes the kind of value' % path]
        extra = [v for v in _enum_values(a) if not any(_same(v, w) for w in _enum_values(b))]
        if extra:
            out.append('%s: adds %s to the choices' % (path, ', '.join(str(v) for v in extra)))
        return out
    if isinstance(b, Str):
        if not isinstance(a, Str):
            return ['%s: changes the kind of value' % path]
        if b.max_len is not None and (a.max_len is None or a.max_len > b.max_len):
            out.append('%s: allows more than %d characters' % (path, b.max_len))
        if a.min_len < b.min_len:
            out.append('%s: allows fewer than %d characters' % (path, b.min_len))
        if b.pattern and a.pattern != b.pattern:
            out.append('%s: %s the pattern' % (path, 'drops' if not a.pattern else 'changes'))
        if b.say and not a.say:
            out.append('%s: drops the control-character rule' % path)
        if b.field and not a.field:
            out.append('%s: drops the prompt-field rule' % path)
        elif b.field and a.field and not b.field.get('multiline') and a.field.get('multiline'):
            out.append('%s: allows line breaks' % path)
        return out
    if isinstance(b, Int):                                     # Int and Num
        if not isinstance(a, Int) or (isinstance(b, Int) and not isinstance(b, Num) and isinstance(a, Num)):
            return ['%s: changes the kind of value' % path]    # a Num child of an Int base lets in 2.5
        if b.minimum is not None and (a.minimum is None or a.minimum < b.minimum):
            out.append('%s: allows below %s' % (path, b.minimum))
        if b.maximum is not None and (a.maximum is None or a.maximum > b.maximum):
            out.append('%s: allows above %s' % (path, b.maximum))
        return out
    if isinstance(b, Bool):
        return [] if isinstance(a, Bool) else ['%s: changes the kind of value' % path]
    if isinstance(b, Bare):
        return [] if isinstance(a, (Bare, MapOf)) else ['%s: changes the kind of value' % path]
    return out


def narrows(child_tree, base_tree, path):
    """The sentences for a child type against a base type: [] when the child is as tight as the base or tighter."""
    c, p = child_tree, base_tree
    if p[0] == 'nullable':
        return narrows(c[1] if c[0] == 'nullable' else c, p[1], path)
    if c[0] == 'nullable':
        return ['%s: was never empty and now may be' % path]
    if p[0] == 'leaf':
        if isinstance(p[1], Anything):
            return []
        if c[0] != 'leaf':
            return ['%s: changes the kind of value' % path]
        return _leaf_faults(c[1], p[1], path)
    if p[0] == 'items':
        if c[0] != 'items':
            return ['%s: is no longer a list' % path]
        a, b, out = c[1], p[1], []
        if b.max_items is not None and (a.max_items is None or a.max_items > b.max_items):
            out.append('%s: allows more than %d items' % (path, b.max_items))
        if a.min_items < b.min_items:
            out.append('%s: allows fewer than %d items' % (path, b.min_items))
        if b.unique and not a.unique:
            out.append('%s: drops the one-of-each rule' % path)
        return out + narrows(c[2], p[2], path + '[]')
    if p[0] == 'map':
        if c[0] != 'map':
            return ['%s: is no longer a map' % path]
        out = []
        if p[1].keys and c[1].keys != p[1].keys:
            out.append('%s: %s the key pattern' % (path, 'drops' if not c[1].keys else 'changes'))
        return out + narrows(c[2], p[2], path + '{}')
    if p[0] == 'model':
        if c[0] != 'model' or not issubclass(c[1], p[1]):
            return ['%s: is not a kind of %s' % (path, p[1].__name__)]
        return []
    if p[0] == 'anyof':
        if c[0] != 'anyof':
            return ['%s: changes the kind of value' % path] if not any(not narrows(c, b, path) for b in p[1]) else []
        return ['%s: allows a shape the base does not' % path for cb in c[1] if not any(not narrows(cb, b, path) for b in p[1])][:1]
    if p[0] == 'none':
        return [] if c[0] == 'none' else ['%s: changes the kind of value' % path]
    return [] if c == p else ['%s: changes the kind of value' % path]       # ('any', annotation)


def child_faults(child, base):
    """R1 and R2 over a pair of classes: every sentence that says the child is not a kind of the base. [] when it is."""
    if not (isinstance(child, type) and issubclass(child, base)):
        return ['%s is not a kind of %s' % (getattr(child, '__name__', child), base.__name__)]
    out = []
    for name, pf in base.model_fields.items():
        cf = child.model_fields.get(name)
        if cf is None:
            out.append('%s: dropped' % name)
            continue
        if pf.is_required() and not cf.is_required():
            out.append('%s: was required and is now optional' % name)
        out += narrows(type_tree(cf), type_tree(pf), name)
    if base.model_config.get('extra') == 'forbid' and child.model_config.get('extra') != 'forbid':
        out.append('%s: allows keys the base refuses' % child.__name__)
    return out


# ---- R10: compare -------------------------------------------------------------------------------------------------------
def compare(old_cls, new_cls):
    """How version `new_cls` stands against `old_cls`: 'same', 'tightens' (accepts less), 'widens' (accepts more) or 'mixed'.
    Not a subclass test: two classes of one family are compared over the fields of the old one."""
    tight = wide = False
    for name, of in old_cls.model_fields.items():
        nf = new_cls.model_fields.get(name)
        if nf is None:
            wide = True                                         # the key is no longer typed
            continue
        if of.is_required() and not nf.is_required():
            wide = True
        elif nf.is_required() and not of.is_required():
            tight = True
        ot, nt = type_tree(of), type_tree(nf)
        if narrows(nt, ot, name):                               # the new type lets in something the old refused
            wide = True
        if narrows(ot, nt, name):                               # the old type lets in something the new refuses
            tight = True
    for name, nf in new_cls.model_fields.items():
        if name in old_cls.model_fields:
            continue
        if nf.is_required():
            tight = True
        if old_cls.model_config.get('extra') == 'forbid':
            wide = True                                         # a key the old class refused
    oe, ne = old_cls.model_config.get('extra'), new_cls.model_config.get('extra')
    if oe == 'forbid' and ne != 'forbid':
        wide = True
    elif ne == 'forbid' and oe != 'forbid':
        tight = True
    return 'mixed' if tight and wide else 'widens' if wide else 'tightens' if tight else 'same'


# ---- R3: substitute -----------------------------------------------------------------------------------------------------
_NONE = object()
_CANDS = ['x', 'Plan', 'D1', 'F1', 'identity/v1', 'r-0123abcd', 'Q-1', '2026-10-27', 'engine/a-b', 'go', 'abc def', 'a_b:c.d', 'a', 'ab',
          'abc', 'client', 'x1', 'c1', 'o1', 'l1', 'gold']


def _concrete(cls):
    """A class a value may be validated against: an abstract one gets a throw-away concrete child (G11)."""
    if not is_abstract(cls):
        return cls
    return type(cls.__name__, (cls,), {'__abstract__': False, '__module__': cls.__module__, '__def__': None})


def _gen_str(leaf, rng):
    ok = [c for c in _CANDS if not _bad(leaf, c)]
    if ok:
        return rng.choice(ok)
    for c in ('a' * max(leaf.min_len, 1), 'a' * leaf.min_len):
        if not _bad(leaf, c):
            return c
    return _NONE


def _bad(leaf, v):
    try:
        leaf.check(v)
        return False
    except Exception:
        return True


def _gen(tree, rng, depth):
    kind = tree[0]
    if depth > 5:
        return _NONE
    if kind == 'nullable':
        return None if rng.random() < 0.2 else _gen(tree[1], rng, depth + 1)
    if kind == 'none':
        return None
    if kind == 'anyof':
        order = list(tree[1])
        rng.shuffle(order)
        for b in order:
            g = _gen(b, rng, depth + 1)
            if g is not _NONE:
                return g
        return _NONE
    if kind == 'leaf':
        o = tree[1]
        if isinstance(o, Enum):
            return rng.choice(o.values)
        if isinstance(o, Str):
            return _gen_str(o, rng)
        if isinstance(o, Bool):
            return rng.choice([True, False])
        if isinstance(o, Bare):
            return rng.choice([{}, {'a': 1}])
        if isinstance(o, Int):
            lo = o.minimum if o.minimum is not None else 0
            hi = o.maximum if o.maximum is not None else lo + 100
            if isinstance(o, Num):
                return rng.choice([lo, hi, lo + (hi - lo) / 2.0])
            return rng.choice([lo, hi, (lo + hi) // 2, rng.randint(int(lo), int(hi))]) if hi >= lo else _NONE
        return rng.choice([None, 1, 'x', [1], {'a': 1}])
    if kind == 'items':
        o = tree[1]
        top = o.max_items if o.max_items is not None else o.min_items + 3
        n = rng.randint(o.min_items, max(o.min_items, min(top, o.min_items + 3)))
        out = []
        for _ in range(n * 4 if o.unique else n):
            g = _gen(tree[2], rng, depth + 1)
            if g is _NONE:
                return _NONE if n else []
            if o.unique and g in out:
                continue
            out.append(g)
            if len(out) == n:
                break
        return out if len(out) == n else _NONE
    if kind == 'map':
        keys = [c for c in _CANDS + ['k', 'key'] if not tree[1].keys or __import__('re').search(tree[1].keys, c)]
        out = {}
        for k in keys[:rng.randint(0, 2)]:
            g = _gen(tree[2], rng, depth + 1)
            if g is not _NONE:
                out[k] = g
        return out
    if kind == 'model':
        return _gen_model(tree[1], rng, depth + 1)
    return rng.choice([None, 1, 'x'])


def _gen_model(cls, rng, depth=0):
    out = {}
    for name, f in cls.model_fields.items():
        if f.is_required() or rng.random() < 0.6:
            g = _gen(type_tree(f), rng, depth)
            if g is _NONE:
                if f.is_required():
                    return _NONE
                continue
            out[f.alias or name] = g
    return out


def substitutable(child, base, n=200, seed=1):
    """R3 by run: values made from the child (fit to it), with the fields the child added taken out, are validated by the base.
    The sentences of the first values the base refused; [] when it takes them all."""
    rng = random.Random(seed)
    own, base_adapter = TypeAdapter(_concrete(child)), TypeAdapter(_concrete(base))
    base_keys = {f.alias or name for name, f in base.model_fields.items()}
    out = []
    for _ in range(n):
        v = _gen_model(child, rng)
        if v is _NONE:
            continue
        try:
            own.validate_python(v)
        except Exception:
            continue                                           # the generator did not fit: not a finding
        shown = {k: x for k, x in v.items() if k in base_keys}
        try:
            base_adapter.validate_python(shown)
        except Exception as e:
            from .faults import sentences
            got = sentences(base_adapter, shown) or [str(type(e).__name__)]
            out.append('%s takes a value that %s refuses: %s' % (child.__name__, base.__name__, got[0]))
            if len(out) >= 5:
                break
    return out


# ---- R6: nest -----------------------------------------------------------------------------------------------------------
def nest_cycle(graph):
    """A circle in {name: [names it nests]} as the walk that closes it (['order', 'line', 'order']), or None."""
    state = {}

    def visit(n, trail):
        if state.get(n) == 1:
            return trail[trail.index(n):] + [n]
        if state.get(n) == 2 or n not in graph:
            return None
        state[n] = 1
        for m in graph[n]:
            r = visit(m, trail + [n])
            if r:
                return r
        state[n] = 2
        return None
    for n in graph:
        r = visit(n, [])
        if r:
            return r
    return None


def nest_depth(graph):
    """The most models on one path of the nest graph (a model that nests nothing is 1). A circle is cut where it closes."""
    memo = {}

    def depth(n, seen):
        if n in memo:
            return memo[n]
        if n in seen or n not in graph:
            return 1 if n not in seen else 0
        best = 1 + max([depth(m, seen | {n}) for m in graph[n]] or [0])
        memo[n] = best
        return best
    return max([depth(n, frozenset()) for n in graph] or [0])


# ---- the check a class gets when it is made -----------------------------------------------------------------------------
def _sig(f):
    """What makes two fields the same type: the annotation and the bounds of every annotation object."""
    return (repr(f.annotation), f.is_required(), tuple((type(m).__name__, repr(sorted(m.bounds().items(), key=lambda kv: kv[0])))
                                                      for m in f.metadata if hasattr(m, 'bounds')))


def check_class(cls):
    """R1, R2 and R5 on a class that has just been made; TypeError names the first fault. R5 runs on every class; R1 and R2 on a
    class that is a definition (it has a `__def__`, its own or its base's)."""
    name = cls.__name__
    own = cls.__dict__.get('__annotations__', {})
    if issubclass(cls, Mixin) and cls.__dict__.get('__def__'):
        raise TypeError('%s is a mixin and cannot be a definition' % name)
    bases = [b for b in cls.__bases__ if isinstance(b, type) and issubclass(b, SutraModel) and b not in _ROOTS]
    seen = {}
    for b in bases:                                            # R5: two bases that disagree on a field
        for fname, f in b.model_fields.items():
            if fname in own:
                continue
            if fname in seen and _sig(seen[fname][1]) != _sig(f):
                raise TypeError('%s: %s: the bases disagree (%s and %s)' % (name, fname, seen[fname][0].__name__, b.__name__))
            seen.setdefault(fname, (b, f))
    if getattr(cls, '__def__', None):
        for b in bases:
            faults = child_faults(cls, b)
            if faults:
                raise TypeError('%s is not a kind of %s: %s' % (name, b.__name__, '; '.join(faults)))
