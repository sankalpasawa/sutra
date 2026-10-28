"""Every definition of the interface, registered (A4.3.1): the classes of the layer modules under the names layer_schema.DEFS has.

`NAMES` is the interface's order, the order `export_all()` writes in. A name is registered once, here; a module only declares
`DEFINES = {name: class or annotation}`. Importing this module registers them all."""
from . import registry
from . import common, identity, options, root, workflow

MODULES = (common, identity, root, workflow, options)

NAMES = (
    'name', 'id.item', 'id.finding', 'impl', 'envelope', 'option', 'check.verdict', 'identity.done_item', 'identity.rule',
    'identity.ask', 'root.pins', 'engine.template', 'workflow.engine', 'workflow', 'workflow.check', 'workflow.registration',
    'option.raise', 'option.words', 'option.pin',
)


def register_all():
    """Register every definition of every module; returns {name: registered object}."""
    found = {}
    for mod in MODULES:
        found.update(mod.DEFINES)
    missing = [n for n in NAMES if n not in found]
    extra = sorted(set(found) - set(NAMES))
    if missing or extra:
        raise RuntimeError("the layer modules and NAMES disagree: missing %s, extra %s" % (missing, extra))
    for name in NAMES:
        registry.register(name, found[name])
    return found


register_all()
