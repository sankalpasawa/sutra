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
    """The TypeAdapter of a registered definition, built on first use and kept. KeyError for a name nobody registered."""
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
