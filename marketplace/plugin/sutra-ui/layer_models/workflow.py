"""The one workflow schema (A1.14): its engines, checks and registration."""
import layer_consts as K
from .base import Open
from .common import BARE, NULLABLE, T, I, N, B, E, L, M, Envelope, IdItem, Name


WORKFLOW_CHECKS = [s[0] for s in K.WORKFLOW_STANDARDS] + ['workflow_meets_standards']


class WorkflowEngine(Open):
    __def__ = 'workflow.engine'
    name: Name
    reads: Name
    writes: Name
    does: T(300) = None
    covers: L(IdItem, 12, 0, True) = None
    internet: B = None
    start: BARE = None
    check: T(60) = None
    envelope: Envelope = None
    made_by: E('library', 'fitted', 'shaped', 'made') = None
    required: B = None
    fit: T(300) = None
    level: E(1, 2) = None
    confidence: N(0, 1) = None
    doubt: T(300) = None


class WorkflowCheck(Open):
    __def__ = 'workflow.check'
    check: E(*WORKFLOW_CHECKS)
    passed: B
    why: T(600)


class Workflow(Open):
    __def__ = 'workflow'
    engines: L(WorkflowEngine, 24)
    source: E(*K.SOURCES)
    schema_version: I(1) = None
    version: I(1) = None
    kind: T(40) = None
    deliverable: NULLABLE(Name) = None
    covers: M(L(Name, min_items=1), K.ITEM_RE) = None
    covers_by: E('adaptation', 'default') = None
    left_out: L(Name) = None
    checks: L(WorkflowCheck) = None
    why: T(600) = None
    at: T(40) = None
    by: T(40) = None


class WorkflowRegistration(Open):
    __def__ = 'workflow.registration'
    version: I(1)
    engines: L(Name, 24)
    source: E(*K.SOURCES)
    registered: T(40)
    by: T(40) = None
    checks: L(WorkflowCheck) = None
    covers: M(L(Name), K.ITEM_RE) = None
    fit: M(T(300)) = None
    deliverable: NULLABLE(Name) = None
    left_out: L(Name) = None


DEFINES = {
    'workflow.engine': WorkflowEngine,
    'workflow.check': WorkflowCheck,
    'workflow': Workflow,
    'workflow.registration': WorkflowRegistration,
}
__all__ = [
    'Workflow', 'WorkflowCheck', 'WorkflowEngine', 'WorkflowRegistration', 'DEFINES',
]
