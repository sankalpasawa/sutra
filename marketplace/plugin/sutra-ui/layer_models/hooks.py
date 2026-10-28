"""Where an owner's model is accepted (A4.5.7): five core definitions take a `model` key, and a template's filings are held to it.

    artifact.template, engine.library, engine.template, kind, journey, journey.file

A value that names a model is checked as that model's child of the definition: the base first, on the value without the `model`
key and without the fields the child added (a closed base would turn both away, and the definitions are not changed to know about
them), then the whole value as the child. The child is a narrowing of the base, so the second check can only add faults. A model
that was never made is a fault; one that is off is not (R9): the value passes and `report()` says so.

    route(name, value)        None when `value` names no model; else the faults (a list, [] when it fits)
    validate(name, value)     the faults of `value` as the definition `name`, the hook included
    fits_model(model, files)  artifacts.check's call: each .json file of a version against a model -> {ok, notes}
    report()                  ['Visit note uses Client, which is off', ...]

The registry is imported lazily; the adapters it holds were built when the models were compiled, so nothing here builds one."""
import json

from . import registry
from .faults import sentences

HOOKS = {'artifact.template': '$', 'engine.library': '$', 'engine.template': '$', 'kind': '$', 'journey': '$',
         'journey.file': '$.journeys[*]'}
#: the core definition an owner's model stands on for each name that has a hook
BASE_OF = {'engine.template': 'engine.library', 'journey.file': 'journey'}
_NOTES = {}                  # sentence -> True, in the order seen; the last NOTES_KEEP
NOTES_KEEP = 100


def _note(sentence):
    _NOTES[sentence] = True
    while len(_NOTES) > NOTES_KEEP:
        _NOTES.pop(next(iter(_NOTES)))


def _prefix(faults, prefix):
    return [prefix + f[1:] if f.startswith('$') else f for f in faults]


def _targets(name, value):
    """[(path, dict)]: the dicts of `value` that may hold a `model`."""
    where = HOOKS.get(name)
    if where is None or not isinstance(value, dict):
        return []
    if where == '$':
        return [('$', value)]
    items = value.get('journeys')
    return [('$.journeys[%d]' % i, j) for i, j in enumerate(items) if isinstance(j, dict)] if isinstance(items, list) else []


def _root_of(reg, key):
    """The core definition an exact model key stands on ('artifact.template'), by following its bases."""
    from .owner_rules import ref_key
    fk, seen = key[2:], set()
    while fk and fk not in seen:
        seen.add(fk)
        s = reg.specs.get(fk)
        if s is None:
            return None
        if s['base'].startswith('core:'):
            return s['base'][5:]
        fk = ref_key(s['base'], reg.specs)
    return None


def _label(reg, key):
    s = reg.specs.get(key[2:]) if key else None
    return s['label'] if s else str(key)


def _one(name, path, d, reg):
    """The faults of one dict that names a model, or None when it names none."""
    if 'model' not in d:
        return None
    m = d['model']
    if not isinstance(m, str):
        return ['%s.model: is not a string' % path]
    key = reg.resolve(m)
    if key is None:
        return ['%s.model: %s is no model of yours' % (path, m)]
    if reg.state.get(key) == 'off':
        _note('uses %s, which is off' % _label(reg, key))
        return []
    if reg.state.get(key) != 'on':
        return ['%s.model: %s needs a look' % (path, _label(reg, key))]
    want = BASE_OF.get(name, name)
    if _root_of(reg, key) != want:
        return ['%s.model: %s cannot be used here' % (path, _label(reg, key))]
    base = registry.DEF_CLASS.get(want)
    cls = reg.classes[key]
    added = set(cls.model_fields) - set(base.model_fields if base is not None else ())
    rest = {k: v for k, v in d.items() if k != 'model' and k not in added}
    if base is not None:
        got = sentences(registry.adapter(want), rest)
        if got:
            return _prefix(got, path)
    whole = {k: v for k, v in d.items() if k != 'model'}
    return _prefix(sentences(reg.adapters[key], whole), path)


def route(name, value):
    """None when `value` names no model; else the faults of the whole value (the base's, then the child's)."""
    targets = _targets(name, value)
    if not any('model' in d for _, d in targets):
        return None
    reg = registry.current()
    out = []
    for path, d in targets:
        got = _one(name, path, d, reg)
        if got:
            out += got
    return out


def validate(name, value):
    """The faults of `value` as the definition `name`: the hook for the names that have one, the definition's own adapter else."""
    routed = route(name, value)
    if routed is not None:
        # the rest of the value, which names no model, is the base's own business
        return routed
    return sentences(registry.adapter(name), value)


def fits_model(model, files):
    """artifacts.check's call: each .json file of a version (one value, or a list of them) against the model. {ok, notes}. A model
    that is off or was never made passes with a note: a filing is never failed for a switch."""
    reg = registry.current()
    key = reg.resolve(model)
    if key is None:
        return {'ok': True, 'notes': ['%s is no model of yours' % model]}
    if reg.state.get(key) == 'off':
        return {'ok': True, 'notes': ['%s is off' % _label(reg, key)]}
    try:
        ad = reg.adapter(key)
    except KeyError:
        return {'ok': True, 'notes': ['%s needs a look' % _label(reg, key)]}
    for fname in sorted(files or {}):
        if not str(fname).endswith('.json'):
            continue
        try:
            value = json.loads(files[fname])
        except (TypeError, ValueError):
            return {'ok': False, 'notes': ['%s: is not JSON' % fname]}
        for item in (value if isinstance(value, list) else [value]):
            got = sentences(ad, item)
            if got:
                return {'ok': False, 'notes': ['%s: %s' % (fname, got[0])]}
    return {'ok': True, 'notes': []}


def report():
    """What names a model that is off: every template of the Library, and the checks the routes have met since the app began."""
    out = dict(_NOTES)
    try:
        import artifacts
        reg = registry.current()
        for n, t in sorted(artifacts.templates().items()):
            m = t.get('model')
            key = reg.resolve(m) if m else None
            if key and reg.state.get(key) == 'off':
                out['%s uses %s, which is off' % (n, _label(reg, key))] = True
    except Exception:  # noqa: BLE001 -- a report is a courtesy; it is never the reason something fails
        pass
    return list(out)
