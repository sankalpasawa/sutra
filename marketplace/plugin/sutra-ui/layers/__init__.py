"""layers -- the implementation of Root and the five layers, one module per version, behind the fixed interface.

PRD amendment A1 (the owner, 2026-10-26: "the functionality of identity or adaptation can change, so we need that
modularization into the layer. But the schema part ... remain[s] the same"). The interface is layer_schema.py; this
package is everything inside a layer that produces it: layers/<layer>/v<N>.py (its CODE, PROMPT, DRAFT and CHECK
dicts, its WORDS and LAYOUT, and view()) and, for a function layer, layers/<layer>/v<N>.json (its recipe: the engine
object the definitions assemble). A version may change freely; the interface changes only with a schema version.

WAVE 0 writes the skeleton: the lazy proxies R, W, J, S and FV (tests reload engine_runtime, so a layer module never
holds a module object), ref_to (a late-bound delegate to a body that has not moved yet) and recipes() (the five
function engines, which engine_runtime.defs() assembles before the Library's templates). W1-CORE adds the registry
(available, load, pins, impl, layer_of, resolve, names, call, view); W3-PINS the pin sets per department.

Nothing here imports engine_runtime at import time.
"""
import importlib
import json
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


def recipes():
    """The five function engines, keyed by engine title, each read from the recipe of the version DEFAULT_PINS names
    (layers/<layer>/v1.json), in RECIPE_ORDER. A recipe that is not there, or is not JSON, refuses the definitions load
    with a named fault, as a template that is not one does."""
    import layer_schema
    out = {}
    for layer in RECIPE_ORDER:
        impl = layer_schema.DEFAULT_PINS[layer]
        title = layer_schema.TITLE[layer]
        p = HERE / layer / (impl.split('/', 1)[1] + '.json')
        try:
            out[title] = json.loads(p.read_text(encoding='utf-8'))
        except FileNotFoundError:
            raise ValueError("the engine definitions are refused: %s's recipe (%s) is missing" % (title, impl))
        except (OSError, ValueError) as exc:
            raise ValueError("the engine definitions are refused: %s's recipe (%s) is not JSON (%s)" % (title, impl, exc))
    return out
