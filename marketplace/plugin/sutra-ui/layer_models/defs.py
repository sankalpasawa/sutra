"""Every definition of the interface, registered (A4.3.1): the classes of the layer modules under the names layer_schema.DEFS has.

`NAMES` is the interface's order, the order `export_all()` writes in. A name is registered once, here; a module only declares
`DEFINES = {name: class or annotation}`. Importing this module registers them all."""
from . import registry
from . import acts, adaptation, audit, common, coordination, fields, identity, options, priority, root, settings, workflow

MODULES = (common, identity, root, workflow, options, coordination, adaptation, priority, audit, acts, fields, settings)

NAMES = (
    'name', 'id.item', 'id.finding', 'impl', 'envelope', 'option', 'check.verdict', 'identity.done_item', 'identity.rule',
    'identity.ask', 'root.pins', 'engine.template', 'workflow.engine', 'workflow', 'workflow.check', 'workflow.registration',
    'coordination.slot', 'coordination.left_out', 'coordination.table', 'adaptation.idea', 'adaptation.ladder',
    'priority.estimate', 'priority.price', 'priority.ceiling', 'audit.reading_item', 'audit.finding', 'audit.reading',
    'adaptation.round', 'coordination.question', 'audit.spot_check', 'option.raise', 'option.words', 'option.pin', 'act.any',
    'act.words', 'act.stamp', 'act.tell', 'act.ask', 'act.verdict', 'act.line_request', 'act.line', 'act.conflict',
    'act.finding', 'act.born', 'act.doubt', 'act.reading', 'act.next', 'act.round', 'act.question', 'act.answer', 'field.task',
    'field.guidance', 'field.text', 'field.note', 'field.items', 'instructions', 'setting.windows', 'setting.make',
    'setting.order', 'setting.spot_every_s',
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
