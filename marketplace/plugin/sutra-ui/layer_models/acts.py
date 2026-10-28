"""The board's acts and their payloads (A1.13, A1.13b). Every payload is open: unknown keys pass, only the fields named are typed."""
from pydantic import Field
import layer_consts as K
from .base import Open
from .common import SAY, BARE, ANYOF, NULLABLE, ANY, T, I, N, B, E, C, L, M, IdFinding, IdItem, Name, Option
from .coordination import CoordinationQuestion
from .priority import PriorityCeiling, PriorityEstimate
from .workflow import WorkflowEngine


class ActAny(Open):
    __def__ = 'act.any'
    word: T(40)


class ActWords(Open):
    __def__ = 'act.words'
    word: E('front', 'request')
    words: T(8000) = None
    objective: T(8000) = None
    output: T(600) = None
    may_read: L(T(60)) = None
    boundaries: T(8000) = None
    request: ANY = None
    about: ANY = None
    answers: ANY = None


class ActStamp(Open):
    __def__ = 'act.stamp'
    word: T(40) = None
    ask: T(40) = None


class ActTell(Open):
    __def__ = 'act.tell'
    word: T(40)
    done: SAY(8000) = None
    card: T(40) = None


class ActAsk(Open):
    __def__ = 'act.ask'
    word: T(40)
    objective: SAY(4000) = None
    output: T(600) = None
    may_read: L(T(60)) = None
    boundaries: T(8000) = None


class ActVerdict(Open):
    __def__ = 'act.verdict'
    word: C('verdict')
    answer: E(*K.GATE_ANSWERS) = None
    why: NULLABLE(T(600)) = None


class ActLineRequestPractices(Open):
    __inline__ = True
    rules: ANY = None
    engines: ANY = None
    artifacts: ANY = None
    required: ANY = None
    taken: ANY = None


class ActLineRequest(Open):
    __def__ = 'act.line_request'
    word: C('line')
    words: NULLABLE(T(100000)) = None
    objective: T(2000) = None
    faults: L(T(600)) = None
    answer: T(2000) = None
    doubt: T(600) = None
    fallback: T(600) = None
    go_on: B = None
    practices: ActLineRequestPractices = None


class ActLine(Open):
    __def__ = 'act.line'
    word: C('line')
    engines: L(ANYOF(Name, WorkflowEngine), 24) = None
    source: NULLABLE(E(*K.SOURCES)) = None
    words: NULLABLE(T(100000)) = None
    for_: NULLABLE(T(80)) = Field(default=None, alias='for')
    covers: M(L(Name), K.ITEM_RE) = None
    doubt: T(600) = None
    confidence: N(0, 1) = None
    fit: M(T(300)) = None
    keep: L(Name) = None
    why: T(2000) = None


class ActConflict(Open):
    __def__ = 'act.conflict'
    word: C('conflict')
    engines: L(ANYOF(Name, WorkflowEngine)) = None
    source: NULLABLE(E(*K.SOURCES)) = None
    words: NULLABLE(T(100000)) = None
    why: T(2000) = None
    bound: NULLABLE(T(40)) = None
    for_: NULLABLE(T(80)) = Field(default=None, alias='for')
    options: L(Option, 3) = None
    round: I(1, 99) = None
    correction: T(600) = None


class ActFinding(Open):
    __def__ = 'act.finding'
    word: C('finding')
    claim: T(2000) = None
    severity: E(*K.SEVERITIES) = None
    where: T(200) = None
    page: NULLABLE(T(200)) = None
    item: NULLABLE(IdItem) = None
    v: I(1) = None
    findings: L(BARE) = None


class ActBorn(Open):
    __def__ = 'act.born'
    word: C('born')
    engines: L(T(80)) = None
    version: NULLABLE(I(0)) = None
    full: B = None
    grow: T(80) = None
    before: NULLABLE(T(80)) = None


class ActDoubtCannot(Open):
    __inline__ = True
    engine: Name = None
    items: L(IdItem) = None
    why: T(600) = None


class ActDoubt(Open):
    __def__ = 'act.doubt'
    word: C('doubt')
    engine: Name
    doubt: T(600)
    fallback: T(600) = None
    confidence: N(0, 1) = None
    cannot: NULLABLE(ActDoubtCannot) = None


class ActReading(Open):
    __def__ = 'act.reading'
    word: C('reading')
    reading: T(40)
    artifact: Name
    v: I(1)
    read: B
    met: L(IdItem)
    not_met: L(IdItem)
    to_confirm: L(IdItem)
    findings: L(IdFinding) = None
    high: B = None


class ActNext(Open):
    __def__ = 'act.next'
    word: C('next')
    items: L(IdItem, min_items=1)
    reading: T(40)
    findings: L(IdFinding) = None
    round: I(1, 99) = None


class ActRound(Open):
    __def__ = 'act.round'
    word: C('round')
    round: I(1, 99)
    correction: T(600) = None
    fixes: L(IdFinding) = None
    covers: L(IdItem) = None
    estimate: PriorityEstimate = None
    why: T(600) = None
    ceiling: PriorityCeiling = None


class ActQuestion(Open):
    __def__ = 'act.question'
    word: C('question')
    entry: CoordinationQuestion


class ActAnswer(Open):
    __def__ = 'act.answer'
    word: C('answer')
    entry: CoordinationQuestion


DEFINES = {
    'act.any': ActAny,
    'act.words': ActWords,
    'act.stamp': ActStamp,
    'act.tell': ActTell,
    'act.ask': ActAsk,
    'act.verdict': ActVerdict,
    'act.line_request': ActLineRequest,
    'act.line': ActLine,
    'act.conflict': ActConflict,
    'act.finding': ActFinding,
    'act.born': ActBorn,
    'act.doubt': ActDoubt,
    'act.reading': ActReading,
    'act.next': ActNext,
    'act.round': ActRound,
    'act.question': ActQuestion,
    'act.answer': ActAnswer,
}
__all__ = [
    'ActAnswer', 'ActAny', 'ActAsk', 'ActBorn', 'ActConflict', 'ActDoubt', 'ActFinding', 'ActLine', 'ActLineRequest',
    'ActNext', 'ActQuestion', 'ActReading', 'ActRound', 'ActStamp', 'ActTell', 'ActVerdict', 'ActWords', 'DEFINES',
]
