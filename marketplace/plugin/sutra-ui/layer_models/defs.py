"""Every definition of the interface, registered (A4.3.1): the classes of the layer modules under the names layer_schema.DEFS has.

`NAMES` is the interface's order of the 130 definitions of schema version 1, the order `export_all()` writes first; `A5_NAMES` are the
17 that schema version 2 added (PRD amendment A5), written after them. A name is registered once, here; a module only declares
`DEFINES = {name: class or annotation}`. Importing this module registers all 147."""
from . import registry
from . import (acts, adaptation, audit, common, coordination, department, fields, identity, options, priority, root, settings,
               templates, views, workflow, journey, a5_words, a5_depts, a5_graph)

MODULES = (common, identity, root, workflow, coordination, adaptation, priority, audit, options, acts, fields, settings, views,
           department, templates, journey, a5_words, a5_depts, a5_graph)

NAMES = (
    'name', 'id.item', 'id.finding', 'impl', 'envelope', 'option', 'check.verdict', 'identity.done_item', 'identity.rule',
    'identity.ask', 'root.pins', 'engine.template', 'workflow.engine', 'workflow', 'workflow.check', 'workflow.registration',
    'coordination.slot', 'coordination.left_out', 'coordination.table', 'adaptation.idea', 'adaptation.ladder',
    'priority.estimate', 'priority.price', 'priority.ceiling', 'audit.reading_item', 'audit.finding', 'audit.reading',
    'adaptation.round', 'coordination.question', 'audit.spot_check', 'option.raise', 'option.words', 'option.pin', 'act.any',
    'act.words', 'act.stamp', 'act.tell', 'act.ask', 'act.verdict', 'act.line_request', 'act.line', 'act.conflict',
    'act.finding', 'act.born', 'act.doubt', 'act.reading', 'act.next', 'act.round', 'act.question', 'act.answer', 'field.task',
    'field.guidance', 'field.text', 'field.note', 'field.items', 'instructions', 'setting.windows', 'setting.make',
    'setting.order', 'setting.spot_every_s', 'view.identity', 'view.adaptation', 'view.adaptation.round', 'view.priority',
    'view.coordination', 'view.engine_card', 'view.audit', 'department.schema_version', 'department.kind', 'department.ref',
    'department.name', 'department.parent', 'department.created', 'department.runtime', 'department.control',
    'department.stopped', 'department.engines', 'department.artifacts', 'department.workflows', 'department.layers',
    'department.org', 'department.root', 'department.template_ref', 'department.templates', 'department.founding',
    'department.events', 'department.pending_final_tell', 'department.goal', 'department.done', 'department.done_items',
    'department.to_be_confirmed', 'department.rules', 'department.owner', 'department.windows', 'department.identity_revision',
    'department.initial_goal_context', 'department.publish_asks_from', 'department.goals', 'department.looked_up',
    'department.host', 'department.ladders', 'department.ladder', 'department.bounds', 'department.envelopes',
    'department.ceiling', 'department', 'step', 'step.row', 'engine.start', 'kind', 'engine.library', 'artifact.template',
    'journey.lane', 'journey.bind', 'journey.branch', 'journey.step', 'journey.outcome', 'journey.edge', 'journey.sub',
    'journey.ruling', 'journey.quote', 'journey.scenario', 'journey.backlog', 'journey.direction', 'journey.build_row',
    'journey.was', 'journey', 'journey.file', 'journey.row_status', 'journey.status',
)

#: schema version 2 (A5.4.1): the page words, the Shadow graph and create-or-reuse
A5_NAMES = (
    'page.words', 'shadow.open', 'shadow.node', 'shadow.edge', 'shadow.graph', 'shadow.timeline_row', 'shadow.chat_link',
    'shadow.cost_line', 'shadow.task_head', 'shadow.task_detail', 'dept.row', 'dept.listing', 'dept.candidate', 'dept.choice',
    'dept.override', 'dept.decision', 'dept.request',
)
ALL_NAMES = NAMES + A5_NAMES


def register_all():
    """Register every definition of every module; returns {name: registered object}."""
    found = {}
    for mod in MODULES:
        found.update(mod.DEFINES)
    missing = [n for n in ALL_NAMES if n not in found]
    extra = sorted(set(found) - set(ALL_NAMES))
    if missing or extra:
        raise RuntimeError("the layer modules and NAMES disagree: missing %s, extra %s" % (missing, extra))
    for name in ALL_NAMES:
        registry.register(name, found[name])
    return found


register_all()
