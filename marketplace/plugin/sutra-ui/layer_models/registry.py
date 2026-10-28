"""What is registered: definition names to classes (or to the annotation of a non-class definition), the bodies of named
scalars (DefRef), and one cached TypeAdapter per name. An adapter is built once and kept, never built per call (A4.7)."""
import threading
from pydantic import BaseModel, TypeAdapter

DEF_CLASS = {}            # 'identity.ask' -> the class
DEF_TYPE = {}             # 'name' -> the annotation of a definition that is not a class
ALIASES = {}              # 'name' -> the body of a named scalar, written by DefRef
_ADAPTERS = {}
_LOCK = threading.Lock()


def register(name, obj):
    """Make `obj` (a class, or an annotation) the definition `name`. A second registration of a name replaces the first and
    drops its adapter."""
    with _LOCK:
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            DEF_CLASS[name] = obj
            DEF_TYPE.pop(name, None)
        else:
            DEF_TYPE[name] = obj
            DEF_CLASS.pop(name, None)
        _ADAPTERS.pop(name, None)
    return obj


def adapter(name):
    """The TypeAdapter of a registered definition, built on first use and kept. KeyError for a name nobody registered. A name
    that begins 'x.' is a model of the owner's (A4.5): its adapter was built when the registry was compiled."""
    if isinstance(name, str) and name.startswith('x.') and name not in DEF_CLASS and name not in DEF_TYPE:
        return current().adapter(name)
    ad = _ADAPTERS.get(name)
    if ad is None:
        with _LOCK:
            ad = _ADAPTERS.get(name)
            if ad is None:
                target = DEF_CLASS.get(name)
                if target is None:
                    target = DEF_TYPE[name]
                ad = _ADAPTERS[name] = TypeAdapter(target)
    return ad


def classes():
    """{name: class} of the registered classes."""
    return dict(DEF_CLASS)


# ---- the owner side (A4.5.4): an immutable registry of the owner's models, replaced whole ---------------------------------------
import time as _time
from types import MappingProxyType as _Frozen


class Registry:
    """What the owner's models compile to, as one immutable object. A reader that holds one keeps it: a stream, a validation in
    flight and a screen's 'try a sample' pin the registry they began with (STR-7). Keys are exact: 'x.client/v1'."""
    __slots__ = ('core', 'classes', 'adapters', 'specs', 'state', 'why', 'families', 'faults', '_frozen')

    def __init__(self, core=None, classes=None, adapters=None, specs=None, state=None, why=None, families=None, faults=None):
        s = object.__setattr__
        s(self, 'core', _Frozen(dict(core or {})))
        s(self, 'classes', _Frozen(dict(classes or {})))
        s(self, 'adapters', _Frozen(dict(adapters or {})))
        s(self, 'specs', _Frozen(dict(specs or {})))              # file key 'client/v1' -> the spec as saved
        s(self, 'state', _Frozen(dict(state or {})))              # exact key -> 'on' | 'off' | 'needs_a_look'
        s(self, 'why', _Frozen(dict(why or {})))                  # exact key -> the first sentence, for a model that needs a look
        s(self, 'families', _Frozen(dict(families or {})))        # exact key of an abstract base -> the adapter of its children
        s(self, 'faults', _Frozen(dict(faults or {})))            # exact key -> [(code, sentence)]
        s(self, '_frozen', True)

    def __setattr__(self, name, value):
        raise AttributeError('a Registry is not changed; swap a new one in')

    def resolve(self, key):
        """The exact key 'x.name/vN' of `key` ('x.name' is the latest version that is on, else the latest), or None."""
        if not isinstance(key, str) or not key.startswith('x.'):
            return None
        if '/v' in key:
            return key if key in self.state else None
        rows = sorted(((k, self.specs[k[2:]]['version']) for k in self.state if k[2:].split('/')[0] == key[2:] and k[2:] in self.specs),
                      key=lambda r: r[1])
        on = [k for k, _ in rows if self.state[k] == 'on']
        return (on or [k for k, _ in rows] or [None])[-1]

    def effective(self, key):
        k = self.resolve(key)
        return k is not None and self.state.get(k) == 'on'

    def adapter(self, key):
        """The adapter of a model: a family's for an abstract base that has children, a class's otherwise; KeyError if none."""
        k = self.resolve(key)
        if k is None:
            raise KeyError(key)
        return self.families.get(k) or self.adapters[k]

    def keys(self):
        return sorted(self.state)


_CURRENT = None
_SOURCE = None                    # (path, stamp) the current registry was built from
_CHECKED = 0.0
_RELOAD = threading.Lock()
RECHECK_SECONDS = 1.0


def empty():
    return Registry()


def core_map():
    """{'core:record': class, ...}: the core models an owner may build on or hold. The registered definitions win; `record` falls
    back to OwnerRecord until A4-PORT registers its own."""
    from .owner_base import OwnerRecord
    from .spec import EXTENSIBLE_CORE, NESTABLE_CORE
    out = {'core:' + n: DEF_CLASS[n] for n in EXTENSIBLE_CORE + NESTABLE_CORE if n in DEF_CLASS}
    out.setdefault('core:record', OwnerRecord)
    return out


def current():
    """The registry now. It is rebuilt from the file when the file (or the home it lives in) changed, looked at most once a
    second; never built by a read that has one."""
    global _CURRENT, _CHECKED
    from . import store
    src = store.source()
    now = _time.monotonic()
    if _CURRENT is not None and (_SOURCE is None or (src[0] == _SOURCE[0] and now - _CHECKED < RECHECK_SECONDS)):
        return _CURRENT
    with _RELOAD:
        if _CURRENT is None or _SOURCE is None or src != _SOURCE:
            store.reload()
        _CHECKED = now
    return _CURRENT


def swap(reg, source=None):
    """Replace the registry as a whole. `source` is what it was built from (store.source())."""
    global _CURRENT, _SOURCE, _CHECKED
    _CURRENT, _SOURCE, _CHECKED = reg, source, _time.monotonic()
    return reg


def reset():
    """No registry: the next current() builds one. For tests."""
    global _CURRENT, _SOURCE
    _CURRENT = _SOURCE = None


def effective(key):
    """R9: is the model on, and is its base?"""
    return current().effective(key)


def links_report():
    """R7: every link of the owner's models with the state of its target: [{from, field, to, status}]. A link to a model that is
    off, missing or retired is listed and never raises."""
    from .owner_rules import ref_key
    reg = current()
    out = []
    for fk, s in sorted(reg.specs.items()):
        for l in s.get('links') or []:
            to = l.get('to') or ''
            if to.startswith('core:'):
                status = 'ok'
            else:
                tk = ref_key(to, reg.specs)
                status = 'missing' if tk is None else 'ok' if reg.state.get('x.' + tk) == 'on' else 'off'
            if status == 'ok' and l.get('enabled') is False:
                status = 'retired'
            out.append({'from': 'x.' + fk, 'field': l['name'], 'to': to.replace('x:', 'x.').replace('core:', 'core:'), 'status': status})
    return out
