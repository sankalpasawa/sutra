"""The interface as pydantic classes (PRD amendment A4). This package imports nothing of the app at import time: only pydantic, the
standard library, layer_consts and itself. The definitions (defs.py) load on first use, so `import layer_models.types` stays light.

    validate(name, value)    -> [str]            the faults of a value against a definition: the classes, then (A4-OWN) the hooks
    sentences(name, value)   -> (list, unmapped) the same with the error types no sentence is written for (a gap is never silent)
    export_all()             -> dict             {name: the JSON Schema dict layer_schema.DEFS holds}, in the interface's order
    classes()                -> {name: class}    the definitions that are classes
    adapter(name)            -> TypeAdapter      the one adapter of a definition, built once and kept
    load()                   -> registry         imports the definitions"""
_LOADED = []


def load():
    """Import and register the 130 definitions (once); returns the registry module."""
    from . import registry
    if not _LOADED:
        from . import defs
        _LOADED.append(defs)
    return registry


def adapter(name):
    return load().adapter(name)


def classes():
    return load().classes()


def sentences(name, value):
    """([sentences], [unmapped error types]) of `value` as the definition `name`; ([], []) when it fits."""
    from .faults import sentences_and_unmapped
    reg = load()
    if name not in reg.DEF_CLASS and name not in reg.DEF_TYPE:
        return ['$: no definition named %s' % name], []
    return sentences_and_unmapped(reg.adapter(name), value)


def validate(name, value):
    """What is wrong with `value` as the definition `name`: [] when it fits. Never builds an adapter, a model or a schema per
    call (A4.7.2): the adapter of a name is built the first time and kept."""
    from . import hooks
    if name in hooks.HOOKS:
        routed = hooks.route(name, value)
        if routed is not None:
            return routed
    return sentences(name, value)[0]


def describe_models():
    from .schema import describe_models as _d
    return _d()


def export_all():
    """{name: JSON Schema dict} for the 130 definitions, key for key what layer_schema.DEFS holds, in the same order."""
    from .schema import export
    reg = load()
    from .defs import NAMES
    names = {cls.__name__: n for n, cls in reg.DEF_CLASS.items() if not cls.__dict__.get('__inline__')}
    return {n: export(reg.DEF_CLASS.get(n) or reg.DEF_TYPE[n], names) for n in NAMES}
