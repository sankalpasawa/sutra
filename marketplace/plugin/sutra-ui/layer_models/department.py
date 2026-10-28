"""The department record (dept.json) and who owns each key (A1.6). Only the keys a save changes are checked (A1.20)."""
from typing import Annotated
from pydantic import ConfigDict
from .base import Closed, Open
from .types import Owner
from .common import keep_order, ISO, BARE, ANYOF, NULLABLE, named, ref_of, T, I, N, B, E, L, M, Envelope, IdItem, Name
from .identity import IdentityDoneItem, IdentityRule
from .priority import PriorityCeiling
from .root import RootPins
from .settings import SettingWindows
from .workflow import WorkflowRegistration


DepartmentSchemaVersionBody = I(0)
DepartmentSchemaVersion = named('department.schema_version', DepartmentSchemaVersionBody)


DepartmentKindBody = T(40)
DepartmentKind = named('department.kind', DepartmentKindBody)


DepartmentRefBody = T(200, 1)
DepartmentRef = named('department.ref', DepartmentRefBody)


DepartmentNameBody = T(200, 1)
DepartmentName = named('department.name', DepartmentNameBody)


DepartmentParentBody = NULLABLE(T(200))
DepartmentParent = named('department.parent', DepartmentParentBody)


DepartmentCreatedBody = ISO
DepartmentCreated = named('department.created', DepartmentCreatedBody)


DepartmentRuntimeBody = E(1, 2)
DepartmentRuntime = named('department.runtime', DepartmentRuntimeBody)


DepartmentControlBody = T(40)
DepartmentControl = named('department.control', DepartmentControlBody)


DepartmentStoppedBody = B
DepartmentStopped = named('department.stopped', DepartmentStoppedBody)


DepartmentEnginesBody = L(Name, 24, 0, True)
DepartmentEngines = named('department.engines', DepartmentEnginesBody)


DepartmentArtifactsBody = L(Name, 32, 0, True)
DepartmentArtifacts = named('department.artifacts', DepartmentArtifactsBody)


DepartmentWorkflowsBody = L(WorkflowRegistration)
DepartmentWorkflows = named('department.workflows', DepartmentWorkflowsBody)


DepartmentLayersBody = ref_of('root.pins', RootPins)
DepartmentLayers = named('department.layers', RootPins)


DepartmentOrgBody = BARE
DepartmentOrg = named('department.org', DepartmentOrgBody)


DepartmentRootBody = NULLABLE(T(200))
DepartmentRoot = named('department.root', DepartmentRootBody)


DepartmentTemplateRefBody = NULLABLE(ANYOF(T(200), BARE))
DepartmentTemplateRef = named('department.template_ref', DepartmentTemplateRefBody)


DepartmentTemplatesBody = M(T(80))
DepartmentTemplates = named('department.templates', DepartmentTemplatesBody)


class DepartmentFounding(Open):
    __def__ = 'department.founding'
    operation_id: T(200) = None
    checkpoints: L(T(40)) = None


class DepartmentEventsShapeItem(Open):
    __inline__ = True
    kind: T(40) = None


DepartmentEventsBody = L(DepartmentEventsShapeItem)
DepartmentEvents = named('department.events', DepartmentEventsBody)


DepartmentPendingFinalTellBody = BARE
DepartmentPendingFinalTell = named('department.pending_final_tell', DepartmentPendingFinalTellBody)


DepartmentGoalBody = T(2000)
DepartmentGoal = named('department.goal', DepartmentGoalBody)


DepartmentDoneBody = T(4000)
DepartmentDone = named('department.done', DepartmentDoneBody)


DepartmentDoneItemsBody = L(IdentityDoneItem, 12)
DepartmentDoneItems = named('department.done_items', DepartmentDoneItemsBody)


class DepartmentToBeConfirmedShapeItem(Open):
    __inline__ = True
    item: IdItem
    why: T(300) = None


DepartmentToBeConfirmedBody = L(DepartmentToBeConfirmedShapeItem)
DepartmentToBeConfirmed = named('department.to_be_confirmed', DepartmentToBeConfirmedBody)


DepartmentRulesBody = L(IdentityRule, 64)
DepartmentRules = named('department.rules', DepartmentRulesBody)


DepartmentOwnerBody = T(200)
DepartmentOwner = named('department.owner', DepartmentOwnerBody)


DepartmentWindowsBody = ref_of('setting.windows', SettingWindows)
DepartmentWindows = named('department.windows', SettingWindows)


DepartmentIdentityRevisionBody = I(1)
DepartmentIdentityRevision = named('department.identity_revision', DepartmentIdentityRevisionBody)


DepartmentInitialGoalContextBody = BARE
DepartmentInitialGoalContext = named('department.initial_goal_context', DepartmentInitialGoalContextBody)


DepartmentPublishAsksFromBody = I(0)
DepartmentPublishAsksFrom = named('department.publish_asks_from', DepartmentPublishAsksFromBody)


DepartmentGoalsBody = L(BARE)
DepartmentGoals = named('department.goals', DepartmentGoalsBody)


DepartmentLookedUpBody = L(T(2000))
DepartmentLookedUp = named('department.looked_up', DepartmentLookedUpBody)


DepartmentHostBody = T(200)
DepartmentHost = named('department.host', DepartmentHostBody)


DepartmentLaddersBody = M(BARE)
DepartmentLadders = named('department.ladders', DepartmentLaddersBody)


DepartmentLadderBody = M(I(0))
DepartmentLadder = named('department.ladder', DepartmentLadderBody)


class DepartmentBounds(Open):
    __def__ = 'department.bounds'
    hops: I(0) = None
    seconds: N(0) = None
    usd: N(0) = None


DepartmentEnvelopesBody = M(Envelope)
DepartmentEnvelopes = named('department.envelopes', DepartmentEnvelopesBody)


DepartmentCeilingBody = ref_of('priority.ceiling', PriorityCeiling)
DepartmentCeiling = named('department.ceiling', PriorityCeiling)


class Department(Closed):
    __def__ = 'department'
    model_config = ConfigDict(json_schema_extra=keep_order(('schema_version', 'kind', 'ref', 'name', 'parent', 'created', 'runtime', 'control', 'stopped', 'engines', 'artifacts', 'workflows', 'layers', 'org', 'root', 'template_ref', 'templates', 'founding', 'events', 'pending_final_tell', 'goal', 'done', 'done_items', 'to_be_confirmed', 'rules', 'owner', 'windows', 'identity_revision', 'initial_goal_context', 'publish_asks_from', 'goals', 'looked_up', 'host', 'ladders', 'ladder', 'bounds', 'envelopes', 'ceiling')))
    kind: Annotated[DepartmentKind, Owner('root')]
    ref: Annotated[DepartmentRef, Owner('root')]
    name: Annotated[DepartmentName, Owner('root')]
    schema_version: Annotated[DepartmentSchemaVersion, Owner('root')] = None
    parent: Annotated[DepartmentParent, Owner('root')] = None
    created: Annotated[DepartmentCreated, Owner('root')] = None
    runtime: Annotated[DepartmentRuntime, Owner('root')] = None
    control: Annotated[DepartmentControl, Owner('root')] = None
    stopped: Annotated[DepartmentStopped, Owner('root')] = None
    engines: Annotated[DepartmentEngines, Owner('root')] = None
    artifacts: Annotated[DepartmentArtifacts, Owner('root')] = None
    workflows: Annotated[DepartmentWorkflows, Owner('root')] = None
    layers: Annotated[DepartmentLayers, Owner('root')] = None
    org: Annotated[DepartmentOrg, Owner('root')] = None
    root: Annotated[DepartmentRoot, Owner('root')] = None
    template_ref: Annotated[DepartmentTemplateRef, Owner('root')] = None
    templates: Annotated[DepartmentTemplates, Owner('root')] = None
    founding: Annotated[DepartmentFounding, Owner('root')] = None
    events: Annotated[DepartmentEvents, Owner('root')] = None
    pending_final_tell: Annotated[DepartmentPendingFinalTell, Owner('root')] = None
    goal: Annotated[DepartmentGoal, Owner('identity')] = None
    done: Annotated[DepartmentDone, Owner('identity')] = None
    done_items: Annotated[DepartmentDoneItems, Owner('identity')] = None
    to_be_confirmed: Annotated[DepartmentToBeConfirmed, Owner('identity')] = None
    rules: Annotated[DepartmentRules, Owner('identity')] = None
    owner: Annotated[DepartmentOwner, Owner('identity')] = None
    windows: Annotated[DepartmentWindows, Owner('identity')] = None
    identity_revision: Annotated[DepartmentIdentityRevision, Owner('identity')] = None
    initial_goal_context: Annotated[DepartmentInitialGoalContext, Owner('identity')] = None
    publish_asks_from: Annotated[DepartmentPublishAsksFrom, Owner('identity')] = None
    goals: Annotated[DepartmentGoals, Owner('identity')] = None
    looked_up: Annotated[DepartmentLookedUp, Owner('identity')] = None
    host: Annotated[DepartmentHost, Owner('identity')] = None
    ladders: Annotated[DepartmentLadders, Owner('identity')] = None
    ladder: Annotated[DepartmentLadder, Owner('identity')] = None
    bounds: Annotated[DepartmentBounds, Owner('identity')] = None
    envelopes: Annotated[DepartmentEnvelopes, Owner('priority')] = None
    ceiling: Annotated[DepartmentCeiling, Owner('priority')] = None


def _owner(field):
    owners = [m.layer for m in field.metadata if isinstance(m, Owner)]
    if len(owners) != 1:
        raise TypeError('a key of the department record has one owner, not %d' % len(owners))
    return owners[0]


#: {key: layer that owns it}, read from the Owner annotation of each field of Department: the only source of DEPARTMENT_KEYS
OWNERS = {name: _owner(f) for name, f in Department.model_fields.items()}
KEYS = tuple(OWNERS)


DEFINES = {
    'department': Department,
    'department.schema_version': DepartmentSchemaVersionBody,
    'department.kind': DepartmentKindBody,
    'department.ref': DepartmentRefBody,
    'department.name': DepartmentNameBody,
    'department.parent': DepartmentParentBody,
    'department.created': DepartmentCreatedBody,
    'department.runtime': DepartmentRuntimeBody,
    'department.control': DepartmentControlBody,
    'department.stopped': DepartmentStoppedBody,
    'department.engines': DepartmentEnginesBody,
    'department.artifacts': DepartmentArtifactsBody,
    'department.workflows': DepartmentWorkflowsBody,
    'department.layers': DepartmentLayersBody,
    'department.org': DepartmentOrgBody,
    'department.root': DepartmentRootBody,
    'department.template_ref': DepartmentTemplateRefBody,
    'department.templates': DepartmentTemplatesBody,
    'department.founding': DepartmentFounding,
    'department.events': DepartmentEventsBody,
    'department.pending_final_tell': DepartmentPendingFinalTellBody,
    'department.goal': DepartmentGoalBody,
    'department.done': DepartmentDoneBody,
    'department.done_items': DepartmentDoneItemsBody,
    'department.to_be_confirmed': DepartmentToBeConfirmedBody,
    'department.rules': DepartmentRulesBody,
    'department.owner': DepartmentOwnerBody,
    'department.windows': DepartmentWindowsBody,
    'department.identity_revision': DepartmentIdentityRevisionBody,
    'department.initial_goal_context': DepartmentInitialGoalContextBody,
    'department.publish_asks_from': DepartmentPublishAsksFromBody,
    'department.goals': DepartmentGoalsBody,
    'department.looked_up': DepartmentLookedUpBody,
    'department.host': DepartmentHostBody,
    'department.ladders': DepartmentLaddersBody,
    'department.ladder': DepartmentLadderBody,
    'department.bounds': DepartmentBounds,
    'department.envelopes': DepartmentEnvelopesBody,
    'department.ceiling': DepartmentCeilingBody,
    'department': Department,
}
__all__ = [
    'Department', 'DepartmentArtifacts', 'DepartmentArtifactsBody', 'DepartmentBounds', 'DepartmentCeiling',
    'DepartmentCeilingBody', 'DepartmentControl', 'DepartmentControlBody', 'DepartmentCreated', 'DepartmentCreatedBody',
    'DepartmentDone', 'DepartmentDoneBody', 'DepartmentDoneItems', 'DepartmentDoneItemsBody', 'DepartmentEngines',
    'DepartmentEnginesBody', 'DepartmentEnvelopes', 'DepartmentEnvelopesBody', 'DepartmentEvents', 'DepartmentEventsBody',
    'DepartmentFounding', 'DepartmentGoal', 'DepartmentGoalBody', 'DepartmentGoals', 'DepartmentGoalsBody',
    'DepartmentHost', 'DepartmentHostBody', 'DepartmentIdentityRevision', 'DepartmentIdentityRevisionBody',
    'DepartmentInitialGoalContext', 'DepartmentInitialGoalContextBody', 'DepartmentKind', 'DepartmentKindBody',
    'DepartmentLadder', 'DepartmentLadderBody', 'DepartmentLadders', 'DepartmentLaddersBody', 'DepartmentLayers',
    'DepartmentLayersBody', 'DepartmentLookedUp', 'DepartmentLookedUpBody', 'DepartmentName', 'DepartmentNameBody',
    'DepartmentOrg', 'DepartmentOrgBody', 'DepartmentOwner', 'DepartmentOwnerBody', 'DepartmentParent',
    'DepartmentParentBody', 'DepartmentPendingFinalTell', 'DepartmentPendingFinalTellBody', 'DepartmentPublishAsksFrom',
    'DepartmentPublishAsksFromBody', 'DepartmentRef', 'DepartmentRefBody', 'DepartmentRoot', 'DepartmentRootBody',
    'DepartmentRules', 'DepartmentRulesBody', 'DepartmentRuntime', 'DepartmentRuntimeBody', 'DepartmentSchemaVersion',
    'DepartmentSchemaVersionBody', 'DepartmentStopped', 'DepartmentStoppedBody', 'DepartmentTemplateRef',
    'DepartmentTemplateRefBody', 'DepartmentTemplates', 'DepartmentTemplatesBody', 'DepartmentToBeConfirmed',
    'DepartmentToBeConfirmedBody', 'DepartmentWindows', 'DepartmentWindowsBody', 'DepartmentWorkflows',
    'DepartmentWorkflowsBody', 'DEFINES',
]
