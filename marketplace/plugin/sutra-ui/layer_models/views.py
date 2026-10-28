"""The pane views (A1.17): the read models already merged; later steps add fields, never rename them."""
import layer_consts as K
from .base import Closed, Open
from .common import NULLABLE, ANY, T, I, N, B, E, L, M, IdFinding, IdItem, Name
from .audit import AuditFinding
from .coordination import CoordinationQuestion
from .priority import PriorityCeiling, PriorityEstimate


class ViewIdentityStandardRowsItem(Open):
    __inline__ = True
    id: E('goal', 'items', 'rules', 'owner_budget', 'invented')
    says: T(200)
    state: E(*K.ITEM_VERDICTS, 'reading')
    note: T(4000)


class ViewIdentityStandard(Open):
    __inline__ = True
    met: B
    missing: L(E(*K.STANDARD))
    rows: L(ViewIdentityStandardRowsItem)


class ViewIdentityDoneItemsItem(Open):
    __inline__ = True
    id: T(8) = None
    text: NULLABLE(T(300)) = None
    how: NULLABLE(T(200)) = None
    level: NULLABLE(T(200)) = None
    confirm: NULLABLE(T(300)) = None


class ViewIdentityRulesItem(Open):
    __inline__ = True
    tag: NULLABLE(T(20)) = None
    line: T(2000) = None
    by: E('yours', 'the template') = None
    since: NULLABLE(T(40)) = None


class ViewIdentityOpenQuestion(Open):
    __inline__ = True
    id: ANY = None
    text: ANY = None
    why: ANY = None
    missing: ANY = None
    asked: ANY = None
    standard: ANY = None
    points: ANY = None


class ViewIdentityConflictsItem(Open):
    __inline__ = True
    at: NULLABLE(T(40)) = None
    who: T(200) = None
    split: NULLABLE(T(4000)) = None
    plan: NULLABLE(T(2000)) = None
    ruling: T(20) = None
    ruled: T(40) = None
    why: NULLABLE(T(4000)) = None
    asked_you: B = None


class ViewIdentity(Open):
    __def__ = 'view.identity'
    standard: ViewIdentityStandard
    goal: NULLABLE(T(2000))
    done: NULLABLE(T(4000))
    done_items: L(ViewIdentityDoneItemsItem)
    rules: L(ViewIdentityRulesItem)
    open_question: NULLABLE(ViewIdentityOpenQuestion)
    conflicts: L(ViewIdentityConflictsItem, 6)


class ViewAdaptationRound(Open):
    __def__ = 'view.adaptation.round'
    round: I(1, 99)
    correction: T(600)
    covers: L(IdItem)
    status: E('proposed', 'granted', 'refused', 'filed', 'read')
    fixes: L(IdFinding) = None
    said: T(60) = None
    estimate: NULLABLE(PriorityEstimate) = None
    at: NULLABLE(T(40)) = None
    reading: NULLABLE(T(40)) = None
    brief_v: NULLABLE(I(1)) = None


class ViewAdaptationProposal(Open):
    __inline__ = True
    workflow: L(T(80)) = None
    source: NULLABLE(T(40)) = None
    at: NULLABLE(T(40)) = None


class ViewAdaptationRootChecksItemChecksItem(Open):
    __inline__ = True
    check: T(60)
    says: T(300)
    passed: B
    why: T(600)


class ViewAdaptationRootChecksItem(Open):
    __inline__ = True
    summary: NULLABLE(T(4000)) = None
    at: NULLABLE(T(40)) = None
    passed: B = None
    checks: L(ViewAdaptationRootChecksItemChecksItem) = None


class ViewAdaptationCoverage(Open):
    __inline__ = True
    items: L(IdItem)
    uncovered: L(IdItem)
    by: E('adaptation', 'default')


class ViewAdaptation(Open):
    __def__ = 'view.adaptation'
    proposal: NULLABLE(ViewAdaptationProposal)
    root_checks: L(ViewAdaptationRootChecksItem)
    rounds: L(ViewAdaptationRound)
    coverage: NULLABLE(ViewAdaptationCoverage) = None
    round: NULLABLE(ViewAdaptationRound) = None


class ViewPriorityBargainsItem(Open):
    __inline__ = True
    said: E('said yes', 'asked for less', 'said no') = None
    summary: NULLABLE(T(4000)) = None
    at: NULLABLE(T(40)) = None


class ViewPriorityEnvelopesItem(Open):
    __inline__ = True
    engine: T(80) = None
    calls: I(0) = None
    usd: N(0) = None
    calls_limit: I(0) = None
    usd_limit: N(0) = None
    share: N(0, 1) = None


class ViewPriorityPricesItemEstimate(Open):
    __inline__ = True
    calls: I(0)
    usd: N(0)


class ViewPriorityPricesItemRoom(Open):
    __inline__ = True
    calls: I()
    usd: N()


class ViewPriorityPricesItem(Open):
    __inline__ = True
    at: NULLABLE(T(40))
    proposal: E('line', 'round', 'engine', 'cost')
    answer: E('accept', 'counter', 'reject')
    said: E('said yes', 'asked for less', 'said no')
    estimate: ViewPriorityPricesItemEstimate
    room: ViewPriorityPricesItemRoom
    why: T(600)


class ViewPrioritySpendByRoundItem(Open):
    __inline__ = True
    round: I(1)
    calls: I(0)
    usd: N(0)


class ViewPriority(Open):
    __def__ = 'view.priority'
    bargains: L(ViewPriorityBargainsItem)
    envelopes: L(ViewPriorityEnvelopesItem)
    prices: L(ViewPriorityPricesItem) = None
    ceiling: NULLABLE(PriorityCeiling) = None
    spend_by_round: L(ViewPrioritySpendByRoundItem) = None


class ViewCoordinationTimetableItemLast(Open):
    __inline__ = True
    at: NULLABLE(T(40)) = None
    status: NULLABLE(T(20)) = None
    wrote: NULLABLE(T(120)) = None


class ViewCoordinationTimetableItem(Closed):
    __inline__ = True
    engine: T(80)
    on: NULLABLE(T(80))
    starts: T(200)
    window_min: I(0)
    since: NULLABLE(T(40))
    state: E(*K.SLOT_STATES)
    word: T(40)
    why: NULLABLE(T(600))
    at: NULLABLE(T(40))
    last: NULLABLE(ViewCoordinationTimetableItemLast)


class ViewCoordinationLeftOutItem(Closed):
    __inline__ = True
    engine: NULLABLE(T(80)) = None
    since: NULLABLE(T(40)) = None


class ViewCoordinationHoldsItem(Closed):
    __inline__ = True
    engine: T(80) = None
    why: T(600) = None


class ViewCoordinationHandoffsItem(Open):
    __inline__ = True
    art: T(80) = None
    v: NULLABLE(I(0)) = None
    by: NULLABLE(T(80)) = None
    says: NULLABLE(T(200)) = None
    readers: L(T(80)) = None


class ViewCoordinationChain(Open):
    __inline__ = True
    of: NULLABLE(T(80)) = None
    used: I(0) = None
    limit: I(0) = None
    share: N(0, 1) = None


class ViewCoordinationAlarmsItem(Open):
    __inline__ = True
    engine: NULLABLE(T(80)) = None
    text: NULLABLE(T(600)) = None
    at: NULLABLE(T(40)) = None


class ViewCoordinationTiesItem(Open):
    __inline__ = True
    pick: T(80) = None
    said: T(200) = None
    why: NULLABLE(T(600)) = None
    at: NULLABLE(T(40)) = None
    today: B = None


class ViewCoordination(Closed):
    __def__ = 'view.coordination'
    line: L(T(80))
    registered: NULLABLE(I(0))
    timetable: L(ViewCoordinationTimetableItem)
    left_out: L(ViewCoordinationLeftOutItem)
    holds: L(ViewCoordinationHoldsItem)
    handoffs: L(ViewCoordinationHandoffsItem)
    chain: ViewCoordinationChain
    alarms: L(ViewCoordinationAlarmsItem)
    ties: L(ViewCoordinationTiesItem)
    questions: L(CoordinationQuestion)


class ViewEngineCardHead(Closed):
    __inline__ = True
    state: E(*K.SLOT_STATES, 'left_out', 'quiet')
    word: NULLABLE(T(80))
    why: NULLABLE(T(600))
    at: NULLABLE(T(40))
    round: ANY


class ViewEngineCardMotor(Closed):
    __inline__ = True
    slot: NULLABLE(T(80))
    starts: T(200)
    once: B
    says: T(80)
    window_min: I(0)
    today: N(0, 1)


class ViewEngineCardFiveItem(Closed):
    __inline__ = True
    fn: E(*[K.TITLE[x] for x in K.FUNCTION_LAYERS])
    state: E('ok', 'warn', 'block', 'wait', 'breath', 'off')
    says: T(300)
    at: NULLABLE(T(40))
    share: NULLABLE(N(0, 1))


class ViewEngineCard(Closed):
    __def__ = 'view.engine_card'
    engine: T(80)
    head: ViewEngineCardHead
    motor: ViewEngineCardMotor
    five: L(ViewEngineCardFiveItem, 5, 5)


class ViewAuditReadingsItem(Open):
    __inline__ = True
    summary: NULLABLE(T(4000)) = None
    at: NULLABLE(T(40)) = None
    artifact: Name = None
    v: I(1) = None
    read: B = None
    why_not_read: NULLABLE(T(300)) = None
    verdicts: M(E(*K.ITEM_VERDICTS), K.ITEM_RE) = None


class ViewAuditFindingsItem(Open):
    __inline__ = True
    text: NULLABLE(T(4000)) = None
    at: NULLABLE(T(40)) = None


class ViewAuditSpotChecksItemChecksItem(Open):
    __inline__ = True
    check: T(80)
    ok: B
    why: T(300)


class ViewAuditSpotChecksItem(Open):
    __inline__ = True
    summary: T(1000)
    at: NULLABLE(T(40))
    ok: B
    checks: L(ViewAuditSpotChecksItemChecksItem)
    findings: L(AuditFinding)


class ViewAuditLatestItemsItem(Open):
    __inline__ = True
    id: IdItem
    verdict: E(*K.ITEM_VERDICTS)
    method: E('code', 'model')
    evidence: T(1000)
    claim: T(600)


class ViewAuditLatest(Open):
    __inline__ = True
    artifact: Name
    v: I(1)
    at: NULLABLE(T(40))
    items: L(ViewAuditLatestItemsItem)
    findings: L(AuditFinding) = None


class ViewAudit(Open):
    __def__ = 'view.audit'
    readings: L(ViewAuditReadingsItem)
    findings: L(ViewAuditFindingsItem)
    spot_checks: L(ViewAuditSpotChecksItem)
    latest: NULLABLE(ViewAuditLatest) = None


DEFINES = {
    'view.identity': ViewIdentity,
    'view.adaptation.round': ViewAdaptationRound,
    'view.adaptation': ViewAdaptation,
    'view.priority': ViewPriority,
    'view.coordination': ViewCoordination,
    'view.engine_card': ViewEngineCard,
    'view.audit': ViewAudit,
}
__all__ = [
    'ViewAdaptation', 'ViewAdaptationRound', 'ViewAudit', 'ViewCoordination', 'ViewEngineCard', 'ViewIdentity',
    'ViewPriority', 'DEFINES',
]
