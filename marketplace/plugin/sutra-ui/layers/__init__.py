"""layers -- the implementation of Root and the five layers, one module per version, behind the fixed interface.

PRD amendment A1 (the owner, 2026-10-26: "the functionality of identity or adaptation can change, so we need that
modularization into the layer. But the schema part ... remain[s] the same"). The interface is layer_schema.py; this
package is everything inside a layer that produces it: layers/<layer>/v<N>.py (its CODE, PROMPT, DRAFT and CHECK
dicts, its WORDS and LAYOUT, and view()) and, for a function layer, layers/<layer>/v<N>.json (its recipe: the engine
object the definitions assemble). A version may change freely; the interface changes only with a schema version.

WAVE 0 writes the skeleton: the lazy proxies R, W, J, S and FV (tests reload engine_runtime, so a layer module never
holds a module object), ref_to (a late-bound delegate to a body that has not moved yet) and recipes() (the five
function engines, which engine_runtime.defs() assembles before the Library's templates). W1-CORE adds the registry
(available, load, pins, impl, layer_of, resolve, names, call, view) and layers/prompts.py (the typed prompt compiler);
W3-PINS the pin sets per department.

THE REGISTRY (A1.18): engine_runtime asks it, for every step and gate, which function runs a name: the one the layer's
pinned implementation provides in its CODE, PROMPT, DRAFT or CHECK dict, else engine_runtime's own, which is the fallback
until a body has moved. Until W3-PINS every department runs DEFAULT_PINS. A module that does not load runs nothing: the
engine_runtime body is used, so a broken layer file never stops a department.

A VERSION THAT EXTENDS A VERSION (PRD amendment A2): a version above 1 names the one it extends (PARENT) and writes only what
differs. layers/lineage.py is the law (pure functions over dicts); layers/versions.py makes the child: inherit merges its four
tables, words, layout and surface functions over its parent's, recipe resolves its recipe (a whole file, or a keyed patch over
its parent's), chain walks its lineage, definition_faults runs the runtime's own definition law with the child in place, and
unchanged_steps names what it leaves as its parent has it. They are published here as thin wrappers, beside prompt and words,
and recipes() asks recipe() for a default pin that has a patch and no whole file.

Nothing here imports engine_runtime at import time.
"""
import contextlib
import contextvars
import importlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: the function layers in the order engine_defs/website.json held their engines, so defs() keeps that order
RECIPE_ORDER = ('identity', 'priority', 'coordination', 'adaptation', 'audit')


class _Lazy:
    """A module by name, looked up afresh on every use: a test that reloads engine_runtime reaches the reloaded one."""

    def __init__(self, name):
        object.__setattr__(self, '_name', name)

    def __getattr__(self, attr):
        return getattr(importlib.import_module(self._name), attr)

    def __repr__(self):
        return '<lazy %s>' % self._name


R, W, J, S, FV = (_Lazy('engine_runtime'), _Lazy('website_dept'), _Lazy('j2_runtime'), _Lazy('layer_schema'),
                  _Lazy('functions_view'))


def ref_to(name, module='engine_runtime'):
    """A body that has not moved into its layer yet, by reference: a delegate that looks `name` up in `module` each time
    it is called, so a reloaded module's function is the one that runs. Its .legacy says where it points."""
    def delegate(*args, **kwargs):
        return getattr(importlib.import_module(module), name)(*args, **kwargs)
    delegate.legacy = (module, name)
    delegate.__name__ = name
    delegate.__qualname__ = 'ref_to(%s.%s)' % (module, name)
    return delegate


def recipes(pins=None):
    """The five function engines, keyed by engine title, each read from the recipe of the version `pins` names for its layer
    ({layer: impl id}; DEFAULT_PINS for a layer it leaves out, or for all of them with no `pins`), in RECIPE_ORDER. A default pin
    reads layers/<layer>/v1.json as it always has, or, when it is a child with a patch and no whole file of its own, is resolved
    by recipe() (A2); any other pin is resolved by recipe() too, never by reading a file here (W3-PINS). A recipe that is not
    there, or is not JSON, or does not merge, refuses the definitions load with a named fault, as a template that is not one
    does."""
    import layer_schema
    out = {}
    for layer in RECIPE_ORDER:
        default = layer_schema.DEFAULT_PINS[layer]
        impl = (pins or {}).get(layer) or default
        title = layer_schema.TITLE[layer]
        v = impl.split('/', 1)[1]
        p = HERE / layer / (v + '.json')
        if impl != default or (not p.exists() and (HERE / layer / (v + '.py')).is_file()):
            from layers import lineage, versions
            try:
                out[title] = versions.recipe(impl)
            except lineage.ModelFault as exc:
                raise ValueError("the engine definitions are refused: %s's recipe (%s) does not merge (%s)" % (title, impl, exc))
            continue
        try:
            out[title] = json.loads(p.read_text(encoding='utf-8'))
        except FileNotFoundError:
            raise ValueError("the engine definitions are refused: %s's recipe (%s) is missing" % (title, impl))
        except (OSError, ValueError) as exc:
            raise ValueError("the engine definitions are refused: %s's recipe (%s) is not JSON (%s)" % (title, impl, exc))
    return out


# ---- the registry (A1.18) ---------------------------------------------------------------------------------------------
KINDS = ('code', 'prompt', 'draft', 'check')
#: the implementations loaded and checked, by id: load() caches here, so a layer file is imported and checked once. A test
#: that needs a stub in a layer's place puts it here (monkeypatch.setitem), and what it puts is what the registry serves.
_LOADED = {}
#: the (department, layer, implementation) triples already told in the record, so a pin the registry cannot honour is
#: one row, never one for every lookup
_TOLD = set()
#: set while a read of the department asks (reading()): a read writes nothing (the J2 view's hard rule 4(g)), so a pin the registry
#: cannot honour is left for the next tick to tell
_READING = contextvars.ContextVar('layers_reading', default=False)


@contextlib.contextmanager
def reading():
    """A read of the department, not a tick: pins() tells no unhonourable pin in the record inside it, and does not mark it told,
    so the tick that asks next writes the row, once."""
    token = _READING.set(True)
    try:
        yield
    finally:
        _READING.reset(token)


def available():
    """Every implementation on disk, {layer: [impl id]}, found as layers/<layer>/v<N>.py, in version order."""
    out = {}
    for layer in S.LAYER_NAMES:
        found = [p.stem for p in (HERE / layer).glob('v*.py') if re.fullmatch(r'v[1-9][0-9]*', p.stem)]
        if found:
            out[layer] = ['%s/%s' % (layer, v) for v in sorted(found, key=lambda v: int(v[1:]))]
    return out


def load(impl_id):
    """The module an implementation id names ('identity/v1'), imported, with LAYER, VERSION and IMPLEMENTS checked and
    cached; None when there is no such file, it does not import, or it was written for another schema version."""
    if impl_id in _LOADED:
        return _LOADED[impl_id]
    if not isinstance(impl_id, str) or not re.fullmatch(S.IMPL_RE, impl_id):
        return None
    layer, v = impl_id.split('/')
    if not (HERE / layer / (v + '.py')).is_file():
        return None
    try:
        module = importlib.import_module('layers.%s.%s' % (layer, v))
    except Exception:  # noqa: BLE001 -- a layer that does not import runs nothing; the fallback bodies serve
        return None
    if (getattr(module, 'LAYER', None), getattr(module, 'VERSION', None), getattr(module, 'IMPLEMENTS', None)) != \
            (layer, int(v[1:]), S.SCHEMA_VERSION):
        return None
    _LOADED[impl_id] = module
    return module


def _tell(ref, layer, named, what):
    """One row in the department's record that a pin it names does not run, once for each (department, layer, pin): the
    tick tells it, a read of the department does not (reading()), and a department with no record to write to says nothing."""
    if _READING.get() or (ref, layer, named) in _TOLD:
        return
    _TOLD.add((ref, layer, named))
    try:
        if ref and (W.ddir(ref) / 'dept.json').exists():
            W.system_run(ref, S.TITLE[layer], what)
    except Exception:  # noqa: BLE001 -- the row is a note of the pin, never a second fault
        pass


def pins(ref=None, d=None):
    """The implementation each layer runs for a department, {layer: impl id}: DEFAULT_PINS, and while S.PER_DEPARTMENT the
    department's own record laid over them (W3-PINS): each version its `layers` names that the registry can load. A pin it
    cannot honour runs that layer's default, and the record says so, once."""
    out = dict(S.DEFAULT_PINS)
    if d is None and ref:
        try:
            d = W.dept(ref)
        except Exception:  # noqa: BLE001 -- no records home to read it from: every layer runs its default
            d = None
    named = (d or {}).get('layers') if isinstance((d or {}).get('layers'), dict) else {}
    for layer, want in named.items():
        if layer not in out or want is None or want == out[layer]:
            continue
        if not S.PER_DEPARTMENT:
            _tell(ref, layer, want, 'runs the default: per-department versions are not on')
        elif isinstance(want, str) and want.startswith(layer + '/') and load(want) is not None:
            out[layer] = want
        else:
            _tell(ref, layer, want, 'runs the default: its per-department version cannot run here')
    return out


def impl(ref, layer, d=None):
    """The module a department runs for a layer: the one its pin names, else the layer's default version; None when
    neither loads."""
    pinned, default = pins(ref, d).get(layer), S.DEFAULT_PINS.get(layer)
    return load(pinned) or (load(default) if default != pinned else None)


def layer_of(engine):
    """The layer an engine is (Identity, Setup, ...); None for a work engine."""
    return S.ENGINE_LAYER.get(engine)


def resolve(ref, engine, kind, name, legacy, d=None):
    """The callable that runs `name` of `kind` ('code', 'prompt', 'draft' or 'check') for an engine of a department: the
    engine's layer's pinned implementation, when it provides the name in its dict, else `legacy[name]`, engine_runtime's
    own (the fallback until the body has moved into its layer)."""
    layer = layer_of(engine)
    if layer:
        module = impl(ref, layer, d)
        got = (getattr(module, kind.upper(), None) or {}).get(name) if module is not None else None
        if got is not None:
            return got
    return legacy[name]


def names(kind):
    """Every name of `kind` that any implementation on disk provides in its dict."""
    out = set()
    for ids in available().values():
        for impl_id in ids:
            module = load(impl_id)
            if module is not None:
                out |= set(getattr(module, kind.upper(), None) or {})
    return out


def call(ref, layer, name, *args, **kwargs):
    """A function of the layer's pinned implementation, called; engine_runtime's own of that name when the
    implementation does not hold one."""
    module = impl(ref, layer)
    fn = getattr(module, name, None) if module is not None else None
    return (fn if callable(fn) else getattr(R, name))(*args, **kwargs)


def view(ref, layer, d, events, asks):
    """The layer's pane as its pinned implementation reads it, or None when the implementation has no view()."""
    module = impl(ref, layer, d)
    fn = getattr(module, 'view', None) if module is not None else None
    return fn(ref, d, events, asks) if callable(fn) else None


def prompt(ref, layer, group, part, **inputs):
    """layers.prompts.prompt: one part of a layer's instructions, compiled; the words code sends an agent."""
    from layers import prompts
    return prompts.prompt(ref, layer, group, part, **inputs)


def words(ref, layer, group, part):
    """layers.prompts.words: a part's fields as the department reads them now."""
    from layers import prompts
    return prompts.words(ref, layer, group, part)


def inherit(parent_id, **own):
    """layers.versions.inherit: a version's tables, words, layout and surface functions, its parent's with its own over them."""
    from layers import versions
    return versions.inherit(parent_id, **own)


def recipe(impl_id, folder=None):
    """layers.versions.recipe: the engine object a version brings, resolved (its whole file, its patch over its parent's, or its parent's)."""
    from layers import versions
    return versions.recipe(impl_id, folder)


def chain(impl_id):
    """layers.versions.chain: [impl_id, the version it extends, ...], nearest first."""
    from layers import versions
    return versions.chain(impl_id)


def definition_faults(impl, provided=None):
    """layers.versions.definition_faults: what engine_runtime.validate finds with this version's recipe in its layer's place."""
    from layers import versions
    return versions.definition_faults(impl, provided)


def unchanged_steps(impl_id):
    """layers.versions.unchanged_steps: the steps a version leaves exactly as the version it extends has them."""
    from layers import versions
    return versions.unchanged_steps(impl_id)
