"""The Shadow graph and the task detail (A5.2, A5.4.1): leaf records, never extended.

Nothing here is stored. `shadow_graph.build()` derives a `ShadowGraph` from the ids that are stored and validates it once before it is
memoised; `detail()` does the same for one task. Every rule of the graph is a validator, so a drawn edge always has two ends, an edge
that says a department is used or spawned always says why, and an id always has the shape of its kind."""
import re

from pydantic import model_validator

from .base import Closed
from .common import B, E, I, L, N, NULLABLE, T
from .a5_depts import DeptDecision, DeptRow
from .a5_types import GID, MID, NODE_ID, NODE_RES, OPEN_REF, TS, fail, rule

NODE_KINDS = ('shadow', 'conversation', 'goal', 'task', 'task_chat', 'worker', 'department')
NODE_STATUS = ('idle', 'draft', 'working', 'waiting', 'blocked', 'done', 'failed', 'stopped', 'off')
EDGE_KINDS = ('has', 'opened', 'attempt', 'steered_by', 'driven_by', 'uses', 'spawned')
OPEN_KINDS = ('task', 'conversation', 'session', 'dept_page', 'goal', 'none')
CONFIDENCE = ('low', 'medium', 'high')
TIMELINE_KINDS = ('said', 'did', 'asked', 'decided', 'state', 'department', 'cost', 'chat')
TIMELINE_BY = ('founder', 'shadow', 'worker', 'department', 'system')
LINK_ROLES = ('shadow_chat', 'conversation', 'worker', 'department_page', 'now')
COST_ROLES = ('now', 'shadow', 'worker', 'department')
#: a mission's states (mission_engine.STATES); test_shadow_graph asserts the two are the same set
TASK_STATES = ('draft', 'brief_confirm', 'running', 'queued', 'paused', 'blocked', 'done', 'failed', 'stopped')
EXECUTORS = ('worker', 'department')
_NODE_RE = {k: re.compile(v) for k, v in NODE_RES.items()}


for _t in ('ref is null exactly when kind is none', 'id %s is not the id of a %s node', 'id is not kind:source>target', 'an edge joins two nodes',
           'a %s edge says why', 'a node id is used twice', 'an edge id is used twice', 'edge %s joins a node that is not drawn',
           'the graph holds exactly one shadow node', 'the focus task is not drawn', 'the graph is not focused on the task',
           'the decision belongs to another task', 'a department listed is not drawn in the graph'):
    rule(_t)                                          # the sentences of the rules below, for qa/a4_equiv.py


class NodeOpen(Closed):
    # What a click on a node opens: the kind, and the id it opens with (none for a node that opens nothing).
    __def__ = 'shadow.open'
    kind: E(*OPEN_KINDS)
    ref: NULLABLE(OPEN_REF) = None

    @model_validator(mode='after')
    def _a_ref_exactly_when_it_opens_something(self):
        if (self.ref is None) != (self.kind == 'none'):
            raise fail('ref is null exactly when kind is none')
        return self


class ShadowGraphNode(Closed):
    __def__ = 'shadow.node'
    id: NODE_ID
    kind: E(*NODE_KINDS)
    label: T(80, 1)
    sub: NULLABLE(T(120)) = None
    status: E(*NODE_STATUS)
    col: I(0, 8)
    row: I(0, 399)
    open: NodeOpen
    since: NULLABLE(TS) = None
    cost_usd: NULLABLE(N(0, 1e6)) = None
    tip: T(240)

    @model_validator(mode='after')
    def _the_id_is_the_id_of_its_kind(self):
        if not _NODE_RE[self.kind].fullmatch(self.id):
            raise fail('id %s is not the id of a %s node' % (self.id, self.kind))
        return self


class ShadowGraphEdge(Closed):
    __def__ = 'shadow.edge'
    id: T(260)
    kind: E(*EDGE_KINDS)
    source: NODE_ID
    target: NODE_ID
    reason: NULLABLE(T(300)) = None
    confidence: NULLABLE(E(*CONFIDENCE)) = None
    live: B
    held: B

    @model_validator(mode='after')
    def _the_edge_is_derived_and_says_why(self):
        out = []
        if self.id != '%s:%s>%s' % (self.kind, self.source, self.target):
            out.append('id is not kind:source>target')
        if self.source == self.target:
            out.append('an edge joins two nodes')
        if (self.kind in ('uses', 'spawned') or self.held) and not self.reason:
            out.append('a %s edge says why' % ('held' if self.held else self.kind))
        if out:
            raise fail(*out)
        return self


class ShadowGraph(Closed):
    __def__ = 'shadow.graph'
    nodes: L(ShadowGraphNode, 400)
    edges: L(ShadowGraphEdge, 800)
    as_of: TS
    focus: NULLABLE(MID) = None
    truncated: B
    shadow_on: B

    @model_validator(mode='after')
    def _the_graph_holds_together(self):
        out = []
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            out.append('a node id is used twice')
        eids = [e.id for e in self.edges]
        if len(set(eids)) != len(eids):
            out.append('an edge id is used twice')
        known = set(ids)
        for e in self.edges:
            if e.source not in known or e.target not in known:
                out.append('edge %s joins a node that is not drawn' % e.id)
                break
        if sum(1 for n in self.nodes if n.kind == 'shadow') != 1:
            out.append('the graph holds exactly one shadow node')
        if self.focus is not None and 'task:' + self.focus not in known:
            out.append('the focus task is not drawn')
        if out:
            raise fail(*out)
        return self


class TimelineRow(Closed):
    __def__ = 'shadow.timeline_row'
    at: TS
    kind: E(*TIMELINE_KINDS)
    by: E(*TIMELINE_BY)
    text: T(300, 1)
    ref: NULLABLE(OPEN_REF) = None


class ChatLink(Closed):
    __def__ = 'shadow.chat_link'
    role: E(*LINK_ROLES)
    label: T(80, 1)
    live: B
    open: NodeOpen
    alt_open: NULLABLE(NodeOpen) = None


class CostLine(Closed):
    __def__ = 'shadow.cost_line'
    role: E(*COST_ROLES)
    usd: N(0, 1e6)
    turns: I(0, 100000)


class TaskHead(Closed):
    __def__ = 'shadow.task_head'
    id: MID
    objective: T(400, 1)
    state: E(*TASK_STATES)
    template: T(40)
    executor: E(*EXECUTORS)
    goal_id: NULLABLE(GID) = None
    created: TS
    updated: TS
    turns_used: I(0, 100000)


class ShadowTaskDetail(Closed):
    __def__ = 'shadow.task_detail'
    task: TaskHead
    graph: ShadowGraph
    decision: NULLABLE(DeptDecision) = None
    departments: L(DeptRow, 8)
    chats: L(ChatLink, 12)
    costs: L(CostLine, 6)
    total_usd: N(0, 1e6)
    timeline: L(TimelineRow, 200)
    as_of: TS

    @model_validator(mode='after')
    def _the_detail_is_of_its_graph(self):
        out = []
        if self.task.id != self.graph.focus:
            out.append('the graph is not focused on the task')
        if self.decision is not None and self.decision.mission_id not in (None, self.task.id):
            out.append('the decision belongs to another task')
        drawn = {n.id for n in self.graph.nodes}
        if any('dept:' + d.ref not in drawn for d in self.departments):
            out.append('a department listed is not drawn in the graph')
        if out:
            raise fail(*out)
        return self


DEFINES = {c.__def__: c for c in (NodeOpen, ShadowGraphNode, ShadowGraphEdge, ShadowGraph, TimelineRow, ChatLink, CostLine, TaskHead,
                                  ShadowTaskDetail)}
