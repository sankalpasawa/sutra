"""The department listing and the create-or-reuse decision (A5.3, A5.4.1): leaf records, never extended.

A row, a candidate, a choice and a decision are what `dept_read` and `shadow_dept` build; the models are checked where they are written
(the decision before `MissionStore.save`, the request at its route) and on the response of each route, never on a stream."""
from pydantic import Field, model_validator

from .base import Closed
from .common import B, E, I, L, N, NULLABLE, T
from .a5_types import KIND, MID, REF, TS, fail, rule

DEPT_STATES = ('not_started', 'working', 'waiting', 'blocked', 'stopped', 'done', 'idle')
CONFIDENCE = ('low', 'medium', 'high')
ACTIONS = ('use', 'create', 'none')
RULES = ('stopped', 'blocked', 'duplicate', 'not_a_child', 'bad_kind', 'rate', 'no_org', 'bad_output', 'offline', 'founder_rule')
HELD_REASONS = ('stopped', 'blocked', 'founder_rule')
DECIDED_BY = ('agent', 'code', 'stub')
MODES = ('link', 'execute')


for _t in ('a department is listed twice', 'use needs a ref', 'use does not take a %s', 'create needs a %s', 'create does not take a ref',
           'none does not take a %s', 'use needs a final_ref', 'none does not take a final_ref', 'a held decision says why',
           'candidates_seen is fewer than the departments considered', 'a held create has made nothing'):
    rule(_t)                                          # the sentences of the rules below, for qa/a4_equiv.py


class DeptRow(Closed):
    __def__ = 'dept.row'
    ref: REF
    name: T(200, 1)
    kind: KIND
    parent: NULLABLE(REF) = None
    root: NULLABLE(REF) = None
    runtime: E(1, 2)
    stopped: B
    state: E(*DEPT_STATES)
    waiting_on_you: B
    pending_asks: I(0, 99)
    working: L(T(40), 12)
    last_activity: NULLABLE(TS) = None
    created: NULLABLE(TS) = None
    goal: T(240)
    done: T(160)
    done_met: NULLABLE(B) = None
    engines: L(T(40), 32)
    artifacts: L(T(40), 32)
    j2_url: NULLABLE(T(120)) = None


class DeptListing(Closed):
    __def__ = 'dept.listing'
    departments: L(DeptRow, 500)
    root_ref: NULLABLE(REF) = None
    as_of: TS

    @model_validator(mode='after')
    def _refs_are_unique(self):
        refs = [d.ref for d in self.departments]
        if len(set(refs)) != len(refs):
            raise fail('a department is listed twice')
        return self


class DeptCandidate(Closed):
    __def__ = 'dept.candidate'
    ref: REF
    name: T(80, 1)
    kind: KIND
    goal: T(240)
    done: T(160)
    state: E(*DEPT_STATES)
    stopped: B
    blocked: B
    last_activity: NULLABLE(TS) = None
    score: N(0, 1)


class DeptChoice(Closed):
    # What the model answers (`parse_choice` validates it): use a department, create one, or neither.
    __def__ = 'dept.choice'
    action: E(*ACTIONS)
    ref: NULLABLE(REF) = None
    kind: NULLABLE(KIND) = None
    name: NULLABLE(T(80)) = None
    goal: NULLABLE(T(2000)) = None
    done_items: L(T(200), 12) = Field(default_factory=list)
    reason: T(400, 1)
    confidence: E(*CONFIDENCE)

    @model_validator(mode='after')
    def _the_action_takes_what_it_needs(self):
        has = {k: getattr(self, k) is not None for k in ('ref', 'kind', 'name', 'goal')}
        out = []
        if self.action == 'use':
            out += ['use needs a ref'] * (not has['ref'])
            out += ['use does not take a %s' % k for k in ('kind', 'name', 'goal') if has[k]]
        elif self.action == 'create':
            out += ['create needs a %s' % k for k in ('kind', 'name', 'goal') if not has[k]]
            out += ['create does not take a ref'] * has['ref']
        else:
            out += ['none does not take a %s' % k for k in ('ref', 'kind', 'name', 'goal') if has[k]]
        if out:
            raise fail(*out)
        return self


class DeptOverride(Closed):
    __def__ = 'dept.override'
    rule: E(*RULES)
    note: T(200, 1)


class DeptDecision(Closed):
    # The choice, what code did to it, and what came of it: stored on the mission and drawn as an edge.
    __def__ = 'dept.decision'
    choice: DeptChoice
    final_action: E(*ACTIONS)
    final_ref: NULLABLE(REF) = None
    overrides: L(DeptOverride, 6)
    held: B
    held_reason: NULLABLE(E(*HELD_REASONS)) = None
    decided_by: E(*DECIDED_BY)
    mode: E(*MODES)
    considered: L(REF, 8)
    candidates_seen: I(0, 500)
    root_ref: NULLABLE(REF) = None
    result_ref: NULLABLE(REF) = None
    operation_id: NULLABLE(T(80)) = None
    mission_id: NULLABLE(MID) = None
    at: TS
    prompt_version: T(20)

    @model_validator(mode='after')
    def _the_final_action_agrees_with_its_ref(self):
        out = []
        if self.final_action == 'use' and not self.final_ref:
            out.append('use needs a final_ref')
        if self.final_action == 'none' and self.final_ref is not None:
            out.append('none does not take a final_ref')
        if self.held and not self.held_reason:
            out.append('a held decision says why')
        if self.candidates_seen < len(self.considered):
            out.append('candidates_seen is fewer than the departments considered')
        if self.final_action == 'create' and self.result_ref is not None and self.held:
            out.append('a held create has made nothing')
        if out:
            raise fail(*out)
        return self


class DeptRequest(Closed):
    # The body of POST /api/native/{root}/departments.
    __def__ = 'dept.request'
    words: T(4000, 1)
    mission_id: NULLABLE(MID) = None
    apply: B = True
    confirmed: B = False


DEFINES = {c.__def__: c for c in (DeptRow, DeptListing, DeptCandidate, DeptChoice, DeptOverride, DeptDecision, DeptRequest)}
