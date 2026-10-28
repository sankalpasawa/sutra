"""Adaptation's records (A1.9): an idea, a step's ladder and a round."""
from pydantic import ConfigDict, Field
import layer_consts as K
from .base import Open
from .common import keep_order, NULLABLE, ANY, T, I, B, E, L, IdFinding, IdItem
from .priority import PriorityEstimate


class AdaptationIdea(Open):
    __def__ = 'adaptation.idea'
    model_config = ConfigDict(json_schema_extra=keep_order(('id', 'words', 'reflected', 'question', 'shapes', 'state', 'at', 'engine', 'priced', 'why')))
    id: T(40, 1)
    reflected: T(8000)
    shapes: L(T(2000), 3)
    state: E('parked', 'built')
    at: T(40)
    words: NULLABLE(T(100000)) = None
    question: NULLABLE(T(2000)) = None
    engine: NULLABLE(T(80)) = None
    priced: T(40) = None
    why: T(2000) = None


class AdaptationLadderHistoryItem(Open):
    __inline__ = True
    model_config = ConfigDict(json_schema_extra=keep_order(('at', 'from', 'to', 'by', 'evidence')))
    to: E(*K.RUNGS)
    by: T(400)
    at: NULLABLE(T(40)) = None
    from_: NULLABLE(E(*K.RUNGS)) = Field(default=None, alias='from')
    evidence: ANY = None


class AdaptationLadderTrial(Open):
    __inline__ = True
    rung: E(*K.RUNGS) = None
    form: NULLABLE(T(40)) = None
    runs: I(0) = None
    agree: I(0) = None
    norule: I(0) = None
    state: E('running', 'done') = None
    started: T(40) = None


class AdaptationLadder(Open):
    __def__ = 'adaptation.ladder'
    model_config = ConfigDict(json_schema_extra=keep_order(('engine', 'step', 'rung', 'form', 'since', 'since_row', 'held', 'pending', 'trial', 'history')))
    engine: T(80, 1)
    step: T(80, 1)
    rung: E(*K.RUNGS)
    held: B
    history: L(AdaptationLadderHistoryItem)
    form: NULLABLE(T(40)) = None
    since: NULLABLE(T(40)) = None
    since_row: I(0) = None
    pending: NULLABLE(T(80)) = None
    trial: NULLABLE(AdaptationLadderTrial) = None


class AdaptationRound(Open):
    __def__ = 'adaptation.round'
    model_config = ConfigDict(json_schema_extra=keep_order(('schema_version', 'round', 'at', 'cycle_id', 'correction', 'fixes', 'covers', 'estimate', 'status', 'reading', 'brief_v', 'thread', 'bound')))
    round: I(1, 99)
    correction: T(600)
    covers: L(IdItem)
    status: E('proposed', 'granted', 'refused', 'filed', 'read')
    schema_version: I(1) = None
    at: T(40) = None
    cycle_id: NULLABLE(T(80)) = None
    fixes: L(IdFinding) = None
    estimate: PriorityEstimate = None
    reading: T(40) = None
    brief_v: I(1) = None
    thread: T(80) = None
    bound: NULLABLE(T(40)) = None


DEFINES = {
    'adaptation.idea': AdaptationIdea,
    'adaptation.ladder': AdaptationLadder,
    'adaptation.round': AdaptationRound,
}
__all__ = [
    'AdaptationIdea', 'AdaptationLadder', 'AdaptationRound', 'DEFINES',
]
