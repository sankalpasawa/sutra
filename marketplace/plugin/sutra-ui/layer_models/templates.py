"""The templates of the levels below the journey (A3.3, A3.5): the step with its row and start, the kind, the engine and the artifact."""
from typing import Annotated
from pydantic import Field
import layer_consts as K
from .base import Closed, Open
from .types import Law
from .common import SAY, WORD, ANYOF, NULLABLE, ANY, T, I, N, B, E, C, L, M, CheckVerdict, Impl, Name


class Step(Closed):
    __def__ = 'step'
    id: Annotated[WORD(r'^[a-z][a-z0-9]*\.[a-z0-9_.]+$', 60), Law('fixed')]
    name: Annotated[SAY(160, 1), Law('free')]
    nature: Annotated[E(*K.NATURES), Law('fixed')]
    born: Annotated[E(*K.RUNGS), Law('free')]
    check: Annotated[T(60, 1), Law('fixed')]
    ceiling: Annotated[E('C0', 'C1', 'C2'), Law('free')] = None
    below: Annotated[E('P', 'C0', 'C1'), Law('free')] = None
    code: Annotated[T(60, 1), Law('free')] = None
    prompt: Annotated[T(60, 1), Law('free')] = None
    draft: Annotated[T(60, 1), Law('free')] = None
    out: Annotated[M(ANYOF(T(20), L(T(40), 12, 1))), Law('fixed')] = None
    answer: Annotated[T(40, 1), Law('fixed')] = None
    facts: Annotated[L(T(40), 12), Law('free')] = None
    stringency: Annotated[E('high', 'low'), Law('fixed')] = None
    only_if: Annotated[T(120, 1), Law('fixed')] = None
    each: Annotated[T(60, 1), Law('fixed')] = None
    side_by_side: Annotated[I(1, 16), Law('free')] = None
    files: Annotated[B, Law('fixed')] = None
    may_end: Annotated[B, Law('fixed')] = None
    by_hand: Annotated[T(600, 1), Law('fixed')] = None
    tools: Annotated[L(E('WebSearch', 'WebFetch')), Law('free')] = None
    timeout_s: Annotated[N(0), Law('free')] = None
    or_: Annotated[ANY, Law('fixed')] = Field(default=None, alias='or')


class StepRow(Open):
    __def__ = 'step.row'
    id: T(40, 1)
    engine: T(80, 1)
    step: T(60, 1)
    status: T(20, 1)
    mode: E('slot', 'gate', 'mark') = None
    rung: NULLABLE(E(*K.RUNGS)) = None
    check: NULLABLE(CheckVerdict) = None
    impl: NULLABLE(Impl) = None
    usd: N(0) = None
    calls: I(0) = None
    started: T(40) = None
    ended: T(40) = None


class EngineStartOnItem(Open):
    __inline__ = True
    kind: E('version', 'post', 'timer')
    of: ANYOF(Name, C('$deliverable')) = None
    checked: B = None
    every_s: N(1) = None


class EngineStart(Closed):
    __def__ = 'engine.start'
    on: L(EngineStartOnItem, min_items=1)
    unless: L(T(60)) = None


class KindRulesItem(Open):
    __inline__ = True
    tag: E(*K.RULE_TAGS)
    line: T(2000, 1)


class Kind(Closed):
    __def__ = 'kind'
    line: L(Name)
    artifacts: L(Name, 32, 1)
    goal: T(2000, 1)
    rules: L(KindRulesItem)
    use_case: T(400, 1)
    functions_template: WORD('^[a-z][a-z-]*$')
    required: L(Name) = None
    done: T(200) = None
    done_words: L(T(80), 2, 2) = None
    say: T(200) = None


class EngineLibrary(Open):
    __def__ = 'engine.library'
    id: WORD('^engine/[a-z0-9][a-z0-9-]*$', 80)
    name: T(40, 1)
    version: I(1)
    use_case: T(400, 1)
    kind: C('work')
    description: T(400)
    reads: Name
    writes: Name
    start: EngineStart
    steps: L(Step)
    skills: L(T(200)) = None
    instruction: T(4000) = None
    needs: L(T(40)) = None


class ArtifactTemplate(Open):
    __def__ = 'artifact.template'
    id: WORD('^artifact/[a-z0-9-]+$', 60)
    name: Name
    kind: E('text', 'plan', 'pages', 'build', 'site', 'record', 'app')
    use_case: T(400, 1)
    files: L(T(80), 16)
    counts_after: E('filing', 'stamp')
    checks: L(T(60)) = None
    written_by: L(T(60)) = None
    put_back: B = None
    operations: L(Name) = None
    made_from: L(T(80)) = None
    version: I(1) = None
    screen: T(200) = None
    reads: L(Name) = None
    form: T(60) = None


DEFINES = {
    'step': Step,
    'step.row': StepRow,
    'engine.start': EngineStart,
    'kind': Kind,
    'engine.library': EngineLibrary,
    'artifact.template': ArtifactTemplate,
}
__all__ = [
    'ArtifactTemplate', 'EngineLibrary', 'EngineStart', 'Kind', 'Step', 'StepRow', 'DEFINES',
]
