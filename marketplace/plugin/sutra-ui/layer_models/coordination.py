"""Coordination's records (A1.11): the slot, what is left out, the table and the question between engines."""
from pydantic import Field
import layer_consts as K
from .base import Closed, Open
from .common import WORD, BARE, NULLABLE, T, I, N, B, E, C, L, Name


class CoordinationSlot(Closed):
    __def__ = 'coordination.slot'
    engine: Name
    on: T(80)
    of: Name = None
    checked: B = None
    every_s: N(0) = None
    window_min: I(0, 1440) = None
    since: T(40) = None


class CoordinationLeftOut(Closed):
    __def__ = 'coordination.left_out'
    engine: Name
    in_line: C(False) = None
    since: T(40) = None


class CoordinationTable(Closed):
    __def__ = 'coordination.table'
    order: L(E('posts', 'line', 'functions'), 3, 1, True)
    line: L(Name, 24, 0, True)
    schema_version: I(1) = None
    functions: L(E(*K.TITLE.values())) = None
    edges: BARE = None
    left_out: L(CoordinationLeftOut) = None
    grown: L(Name, unique=True) = None
    registered: NULLABLE(I(0)) = None
    timetable: L(CoordinationSlot) = None
    by: E('born', 'Coordination') = None
    since: T(40) = None
    why: T(300) = None


class CoordinationQuestionAnsweredFrom(Open):
    __inline__ = True
    workflow: Name
    version: NULLABLE(I(0)) = None


class CoordinationQuestion(Open):
    __def__ = 'coordination.question'
    schema_: C('board/1') = Field(alias='schema')
    id: WORD('^Q-[1-9][0-9]*$', 8)
    asked_by: Name
    to: Name
    about: T(120)
    question: T(600)
    status: E(*K.QUESTION_STATUSES)
    used_by: L(Name)
    answer: NULLABLE(T(2000)) = None
    answered_by: NULLABLE(Name) = None
    reason: NULLABLE(T(300)) = None
    artifact_update: NULLABLE(BARE) = None
    cycle: NULLABLE(T(80)) = None
    slot: T(160) = None
    attempt: I(1) = None
    run: NULLABLE(T(40)) = None
    answered_from: NULLABLE(CoordinationQuestionAnsweredFrom) = None


DEFINES = {
    'coordination.slot': CoordinationSlot,
    'coordination.left_out': CoordinationLeftOut,
    'coordination.table': CoordinationTable,
    'coordination.question': CoordinationQuestion,
}
__all__ = [
    'CoordinationLeftOut', 'CoordinationQuestion', 'CoordinationSlot', 'CoordinationTable', 'DEFINES',
]
