"""layers/versions.py -- a version that extends a version: the registry's helpers for a child (PRD amendment A2, A2-INHERIT;
design/PRD-FIVE-FUNCTIONS-A2.md A2.4 to A2.6).

A new version of a layer names the version it extends (PARENT) and writes only what differs. This module is what turns that into
a version the registry can serve, over the pure law of layers/lineage.py:

    inherit               the child's four registry tables, words, layout and surface functions: the parent's, then the child's over them
    chain                 the version, the one it extends, and so on up to a version with no PARENT
    recipe_of_module      the engine object a version brings: its template, its whole file, its patch over its parent's, or its parent's
    recipe                the same for an implementation id

layers/__init__.py publishes them as thin wrappers (inherit, recipe, chain), so a version module writes
`from layers import inherit` and a caller writes `layers.recipe(impl_id)`.

A malformed lineage or recipe is a lineage.ModelFault, never a bare exception. Nothing here imports the runtime at import time:
engine_runtime is reached through the lazy proxy, inside the functions, because tests reload engine_runtime.
"""
import copy
import json
from pathlib import Path

import layers
from layers import R
from layers import lineage as L

#: the functions a version publishes beside its tables (A1.18); a child that defines none of its own has its parent's
SURFACE = ('view', 'engine_card', 'apply_option', 'standards')
#: how many versions a lineage may hold, the version itself counted
DEPTH = 8
#: (the module's table, the name of its argument in inherit and of the recipe field that names an entry of it)
TABLES = (('CODE', 'code'), ('PROMPT', 'prompt'), ('DRAFT', 'draft'), ('CHECK', 'check'))


def _load(impl_id):
    """The loaded module an id names; ModelFault when the id is not one or the module does not load."""
    module = layers.load(impl_id) if isinstance(impl_id, str) else None
    if module is None:
        raise L.ModelFault('%s does not load' % (impl_id if isinstance(impl_id, str) else repr(impl_id)))
    return module


def inherit(parent_id, code=None, prompt=None, draft=None, check=None, words=None, layout=None):
    """The child's module-level names, merged: {'CODE', 'PROMPT', 'DRAFT', 'CHECK', 'WORDS', 'LAYOUT'} (the parent's entries, then the
    child's over them: fresh dicts holding the parent's very callables, so a ref_to stays a ref_to with its .legacy) and each SURFACE
    function the parent has. Use it once, as a version's tables: `globals().update(inherit(PARENT, code={...}, words={...}))`; a name
    defined after that line overrides it. ModelFault when the parent does not load or an own entry is not callable."""
    parent = _load(parent_id)
    own = {'code': code, 'prompt': prompt, 'draft': draft, 'check': check}
    out = {}
    for attr, key in TABLES:
        table = dict(getattr(parent, attr, None) or {})
        mine = own[key] or {}
        if not isinstance(mine, dict):
            raise L.ModelFault('the %s of a version are a dict of names and what runs them' % key)
        for name, fn in mine.items():
            if not callable(fn):
                raise L.ModelFault('%s %s is not callable' % (key, name))
            table[name] = fn
        out[attr] = table
    out['WORDS'] = L.merge_words(getattr(parent, 'WORDS', None), words)
    out['LAYOUT'] = L.merge_layout(getattr(parent, 'LAYOUT', None), layout)
    for name in SURFACE:
        if callable(getattr(parent, name, None)):
            out[name] = getattr(parent, name)
    return out


def chain(impl_id):
    """[impl_id, its PARENT, that one's PARENT, ...], nearest first. ModelFault on a version that repeats in its own lineage, a
    version that does not load, or a lineage of more than DEPTH versions."""
    out, cur = [], impl_id
    while cur:
        if cur in out:
            raise L.ModelFault('%s repeats in its own lineage' % cur)
        out.append(cur)
        if len(out) > DEPTH:
            raise L.ModelFault('%s: the lineage is deeper than %d versions' % (impl_id, DEPTH))
        cur = getattr(_load(cur), 'PARENT', None)
    return out


def _read(path, what):
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise L.ModelFault('%s is missing: %s' % (what, Path(path).name))
    except (OSError, ValueError) as exc:
        raise L.ModelFault('%s is not JSON: %s (%s)' % (what, Path(path).name, exc))
    if not isinstance(doc, dict):
        raise L.ModelFault('%s is an object: %s' % (what, Path(path).name))
    return doc


def recipe_of_module(module, folder=None):
    """The engine object a version brings, resolved: Root's Library template (RECIPE_TEMPLATE), else its whole file (RECIPE), else
    its patch (RECIPE_PATCH) laid over its PARENT's recipe and held to the substitutability law, else its PARENT's recipe. The file
    is read from the module's folder, or from `folder`. ModelFault in a sentence that names what is wrong; a fresh object each time."""
    template = getattr(module, 'RECIPE_TEMPLATE', None)
    if template:
        found = R.engine_templates().get(template)
        if found is None:
            raise L.ModelFault('the Library has no template named %s' % template)
        return copy.deepcopy(found)
    here = getattr(module, '__file__', None)
    base = Path(folder) if folder else (Path(here).parent if here else None)
    parent_id = getattr(module, 'PARENT', None)
    whole, patch = getattr(module, 'RECIPE', None), getattr(module, 'RECIPE_PATCH', None)
    if (whole or patch) and base is None:
        raise L.ModelFault('there is no folder to read the recipe from')
    if whole:
        return _read(base / str(whole), 'the recipe')
    if patch:
        if not parent_id:
            raise L.ModelFault('a recipe patch lays over the recipe of the version it extends, and this one names no PARENT')
        doc = _read(base / str(patch), 'the recipe patch')
        if 'parent' in doc and doc['parent'] != parent_id:
            raise L.ModelFault('the patch is for %s, not for %s' % (doc['parent'], parent_id))
        parent_recipe = recipe(parent_id)
        merged = L.merge_recipe(parent_recipe, doc, getattr(module, 'LAYER', None))
        faults = L.recipe_faults(parent_recipe, merged, getattr(module, 'LAYER', None))
        if faults:
            raise L.ModelFault('; '.join(faults[:3]))
        return merged
    if parent_id:
        return recipe(parent_id)
    raise L.ModelFault('%s/v%s names no recipe' % (getattr(module, 'LAYER', '?'), getattr(module, 'VERSION', '?')))


def recipe(impl_id, folder=None):
    """recipe_of_module of the implementation an id names; ModelFault when it does not load."""
    return recipe_of_module(_load(impl_id), folder)
