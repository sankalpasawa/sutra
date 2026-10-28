"""The six trial definitions of PRD amendment A4 (A4.3.9), written as classes on layer_models: a record (identity.done_item), an
ask with options (identity.ask), a workflow (workflow), an act with a keyword field name (act.conflict), a closed table
(coordination.table) and a ladder (adaptation.ladder), with the definitions they nest. They are the proof's first subjects: A4-CORE's
tests and the equivalence harness read them, and A4-PORT replaces them with the 130 real ones. Field names, bounds and enums are
read from layer_schema's own constants, so a drift would be a bound that moved, not a typo here."""
import sys
from pathlib import Path
from typing import Annotated, Any, Union

from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import layer_schema as S                                                    # noqa: E402  the oracle, and the constants
from layer_models.base import Closed, Open                                   # noqa: E402
from layer_models.types import (AnyOf, Anything, Bare, Bool, Const, DefRef, Enum, Int, Items, MapOf, Num, Str)  # noqa: E402


def T(max_len, min_len=0, **k):
    return Annotated[str, Str(max_len, min_len, **k)]


def SAY(max_len, min_len=0):
    return Annotated[str, Str(max_len, min_len, say=True)]


def WORD(pattern, max_len=40):
    return Annotated[str, Str(max_len, 0, pattern=pattern, word=True)]


def I(lo=None, hi=None):
    return Annotated[int, Int(lo, hi)]


def N(lo=None, hi=None):
    return Annotated[float, Num(lo, hi)]


B = Annotated[bool, Bool()]
ANY = Annotated[Any, Anything()]
BARE = Annotated[dict[str, Any], Bare()]


def E(*values):
    return Annotated[Any, Enum(*values)]


def C(value):
    return Annotated[Any, Const(value)]


def L(of, max_items=None, min_items=0, unique=False):
    return Annotated[list[of], Items(max_items, min_items, unique)]


def M(of, keys=None):
    return Annotated[dict[str, of], MapOf(keys)]


def NULLABLE(of):
    return Annotated[Union[of, None], AnyOf()]


def ANYOF(*of):
    return Annotated[Union[of], AnyOf()]


# ---- common -------------------------------------------------------------------------------------------------------------
Name = Annotated[str, Str(40, 0, pattern=S.NAME_RE, word=True), DefRef('name', S.DEFS['name'])]
IdItem = Annotated[str, Str(3, 0, pattern=S.ITEM_RE, word=True), DefRef('id.item', S.DEFS['id.item'])]


class Envelope(Open):
    calls: I(0)
    usd: N(0)


class Option(Open):
    id: WORD(r'^[a-z][a-z0-9_]*(:[A-Za-z0-9_.-]{1,40})?$', 64)
    label: SAY(120, 1)
    cost: SAY(400)
    kind: E(*S.OPTION_KINDS) = None
    params: BARE = None


class DoneItem(Closed):
    id: IdItem
    text: T(300, 1)
    how: T(200) = None
    level: T(200) = None
    confirm: T(200) = None


class Chosen(Open):
    id: T(64) = None
    label: T(120) = None
    at: T(40) = None
    by: T(80) = None
    words: NULLABLE(T(2000)) = None


class Doubt(Open):
    engine: T(40) = None
    doubt: T(600) = None
    shown: T(600) = None
    fallback: T(600) = None
    line: NULLABLE(I(0)) = None
    answered: ANYOF(I(0), B) = None


class Ask(Open):
    id: T(40, 1)
    kind: E(*S.ASK_KINDS)
    status: E(*S.ASK_STATUSES)
    text: T(4000) = None
    created: T(40) = None
    decided: NULLABLE(T(40)) = None
    by: NULLABLE(T(80)) = None
    engine: NULLABLE(T(60)) = None
    thread: NULLABLE(T(80)) = None
    options: L(Option, S.OPTIONS_MAX) = None
    chosen: NULLABLE(Chosen) = None
    items: L(DoneItem, S.DONE_ITEMS_MAX) = None
    cycle_id: NULLABLE(T(80)) = None
    doubt: Doubt = None


class WFEngine(Open):
    name: Name
    reads: Name
    writes: Name
    does: T(300) = None
    covers: L(IdItem, 12, unique=True) = None
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


CHECKS = [s[0] for s in S.WORKFLOW_STANDARDS] + ['workflow_meets_standards']


class WFCheck(Open):
    check: E(*CHECKS)
    passed: B
    why: T(600)


class Workflow(Open):                                   # required first, in the interface's own order
    engines: L(WFEngine, 24)
    source: E(*S.SOURCES)
    schema_version: I(1) = None
    version: I(1) = None
    kind: T(40) = None
    deliverable: NULLABLE(Name) = None
    covers: M(L(Name, None, 1), S.ITEM_RE) = None
    covers_by: E('adaptation', 'default') = None
    left_out: L(Name) = None
    checks: L(WFCheck) = None
    why: T(600) = None
    at: T(40) = None
    by: T(40) = None


class ActConflict(Open):
    word: C('conflict')
    engines: L(ANYOF(Name, WFEngine)) = None
    source: NULLABLE(E(*S.SOURCES)) = None
    words: NULLABLE(T(100000)) = None
    why: T(2000) = None
    bound: NULLABLE(T(40)) = None
    for_: NULLABLE(T(80)) = Field(default=None, alias='for')
    options: L(Option, 3) = None
    round: I(1, 99) = None
    correction: T(600) = None


class Left(Closed):
    engine: Name
    in_line: C(False) = None
    since: T(40) = None


class Slot(Closed):
    engine: Name
    on: T(80)
    of: Name = None
    checked: B = None
    every_s: N(0) = None
    window_min: I(0, 1440) = None
    since: T(40) = None


class Table(Closed):                                    # required first
    order: Annotated[list[E('posts', 'line', 'functions')], Items(3, 1, True)]
    line: L(Name, 24, unique=True)
    schema_version: I(1) = None
    functions: L(E(*S.TITLE.values())) = None
    edges: BARE = None
    left_out: L(Left) = None
    grown: L(Name, unique=True) = None
    registered: NULLABLE(I(0)) = None
    timetable: L(Slot) = None
    by: E('born', 'Coordination') = None
    since: T(40) = None
    why: T(300) = None


class Trial(Open):
    rung: E(*S.RUNGS) = None
    form: NULLABLE(T(40)) = None
    runs: I(0) = None
    agree: I(0) = None
    norule: I(0) = None
    state: E('running', 'done') = None
    started: T(40) = None


class Hist(Open):
    to: E(*S.RUNGS)
    by: T(400)
    at: NULLABLE(T(40)) = None
    from_: NULLABLE(E(*S.RUNGS)) = Field(default=None, alias='from')
    evidence: ANY = None


class Ladder(Open):
    engine: T(80, 1)
    step: T(80, 1)
    rung: E(*S.RUNGS)
    held: B
    history: L(Hist)
    form: NULLABLE(T(40)) = None
    since: NULLABLE(T(40)) = None
    since_row: I(0) = None
    pending: NULLABLE(T(80)) = None
    trial: NULLABLE(Trial) = None


#: definition name -> class, the six trial definitions
TRIAL = {'identity.done_item': DoneItem, 'identity.ask': Ask, 'workflow': Workflow, 'act.conflict': ActConflict,
         'coordination.table': Table, 'adaptation.ladder': Ladder}
#: every class that is a definition of its own in DEFS (the others are written inline where they are used)
NAMES = {'Option': 'option', 'Envelope': 'envelope', 'WFEngine': 'workflow.engine', 'WFCheck': 'workflow.check',
         'DoneItem': 'identity.done_item', 'Left': 'coordination.left_out', 'Slot': 'coordination.slot'}
#: the twelve definitions the trial exports: name -> class
EXPORTED = dict(TRIAL, **{'option': Option, 'envelope': Envelope, 'workflow.engine': WFEngine, 'workflow.check': WFCheck,
                          'coordination.left_out': Left, 'coordination.slot': Slot})
