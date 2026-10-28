"""The user-journey template (A3.6): a journey file and its parts, and the status document computed for each."""
import layer_consts as K
from .base import Closed
from .common import SAY, WORD, ISO, NULLABLE, T, I, B, E, L, M


class JourneyLane(Closed):
    __def__ = 'journey.lane'
    id: WORD(K.LANE_ID, 16)
    label: SAY(40, 1)
    kind: E(*K.LANE_KINDS)
    function: NULLABLE(E(*K.FUNCTION_LAYERS)) = None


class JourneyBind(Closed):
    __def__ = 'journey.bind'
    kind: E(*K.BIND_KINDS)
    src: E(*K.ACTORS) = None
    act: E(*K.ACTS) = None
    word: T(40) = None
    dst: E(*K.ACTORS) = None
    id: T(60) = None
    action: T(60) = None
    method: E('GET', 'POST') = None
    path: T(120) = None
    symbol: T(80) = None
    what: T(200) = None
    optional: B = None


class JourneyBranch(Closed):
    __def__ = 'journey.branch'
    label: SAY(40, 1)
    to: T(20, 1)


class JourneyStep(Closed):
    __def__ = 'journey.step'
    n: WORD(K.STEP_N, 3)
    lane: WORD(K.LANE_ID, 16)
    short: SAY(60, 1)
    text: SAY(1500, 1)
    site_function: SAY(200) = None
    site_status: E(*K.SITE_STATUS) = None
    site_says: SAY(120) = None
    site_code: SAY(600) = None
    act: E(*K.STEP_ACTS) = None
    binds: L(JourneyBind, 8) = None
    code: L(WORD(K.SYMBOL, 80), 12) = None
    tests: L(WORD(K.TEST_REF, 200), 12) = None
    branches: L(JourneyBranch, 6) = None
    child: NULLABLE(WORD(K.JOURNEY_ID, 6)) = None
    read: B = None
    backlog: NULLABLE(WORD(K.BACKLOG_ID, 6)) = None
    same_as: NULLABLE(WORD(K.SAME_AS, 24)) = None


class JourneyOutcome(Closed):
    __def__ = 'journey.outcome'
    kind: E(*K.OUTCOME_KINDS)
    voice: E(*K.OUTCOME_VOICES) = None
    golden: NULLABLE(T(200)) = None


class JourneyEdgeSite(Closed):
    __inline__ = True
    status: E(*K.SITE_STATUS)
    text: SAY(1500) = None


class JourneyEdge(Closed):
    __def__ = 'journey.edge'
    id: WORD(K.EDGE_ID, 8)
    at: T(20, 1)
    short: SAY(60, 1)
    trigger: SAY(400, 1)
    site: JourneyEdgeSite
    code_does: SAY(1500) = None
    outcome: JourneyOutcome = None
    binds: L(JourneyBind, 8) = None
    code: L(WORD(K.SYMBOL, 80), 12) = None
    tests: L(WORD(K.TEST_REF, 200), 12) = None
    backlog: NULLABLE(WORD(K.BACKLOG_ID, 6)) = None
    disposition: NULLABLE(E(*K.DISPOSITIONS)) = None
    rulings: L(WORD(K.RULING_ID, 8), 8) = None
    read: B = None
    truncated: B = None
    reword: NULLABLE(SAY(700)) = None
    same_as: NULLABLE(WORD(K.SAME_AS, 24)) = None


class JourneySub(Closed):
    __def__ = 'journey.sub'
    id: WORD(K.SUB_ID, 6)
    title: SAY(80, 1)
    step: WORD(K.STEP_N, 3)
    owner: SAY(80) = None
    text: SAY(800) = None
    drawn: SAY(120) = None


class JourneyRuling(Closed):
    __def__ = 'journey.ruling'
    id: WORD(K.RULING_ID, 8)
    status: E(*K.RULING_STATUS)
    text: SAY(700)
    date: NULLABLE(ISO) = None


class JourneyQuote(Closed):
    __def__ = 'journey.quote'
    text: SAY(1500, 1)
    date: NULLABLE(ISO) = None
    on: T(20) = None


class JourneyScenario(Closed):
    __def__ = 'journey.scenario'
    id: T(40, 1)
    lane: T(40, 1)
    test: WORD(K.TEST_REF, 200)
    walks: L(WORD(K.STEP_N, 3), 20) = None
    says: SAY(300) = None


class JourneyBacklog(Closed):
    __def__ = 'journey.backlog'
    id: WORD(K.BACKLOG_ID, 6)
    row: T(20, 1)
    smallest: SAY(700, 1)
    package: T(160, 1)
    decision: T(40) = None


class JourneyDirection(Closed):
    __def__ = 'journey.direction'
    id: T(8, 1)
    direction: SAY(500, 1)
    built: SAY(800) = None
    gap: SAY(500) = None
    mark: NULLABLE(E(*K.DISPOSITIONS)) = None


class JourneyBuildRow(Closed):
    __def__ = 'journey.build_row'
    id: T(8, 1)
    change: SAY(800, 1)
    when: E('v1', 'later') = None
    where: SAY(300) = None
    owner: T(40) = None
    size: E('S', 'M', 'L') = None
    tests: L(WORD(K.TEST_REF, 200), 6) = None
    backlog: NULLABLE(WORD(K.BACKLOG_ID, 6)) = None


class JourneyWas(Closed):
    __def__ = 'journey.was'
    title: SAY(120, 1)
    steps: L(JourneyStep, 24)
    edges: L(JourneyEdge, 30)
    lanes: L(WORD(K.LANE_ID, 16), 10) = None


class JourneyToday(Closed):
    __inline__ = True
    text: SAY(1500, 1)
    sources: T(200) = None


class JourneySite(Closed):
    __inline__ = True
    page: T(200) = None
    data_version: T(8) = None
    as_of: ISO = None


class JourneyHelper(Closed):
    __inline__ = True
    site: T(20) = None
    screen: T(20) = None
    code: T(20) = None


class Journey(Closed):
    __def__ = 'journey'
    schema_version: I(1)
    id: WORD(K.JOURNEY_ID, 6)
    title: SAY(120, 1)
    kind: E(*K.JOURNEY_KINDS)
    goal: SAY(300, 1)
    lanes: L(JourneyLane, 10)
    steps: L(JourneyStep, 24)
    edges: L(JourneyEdge, 24)
    site_ids: L(T(32, 1), 100, 0, True)
    inside: NULLABLE(WORD(K.JOURNEY_ID, 6)) = None
    bound_to: NULLABLE(E(*K.FUNCTION_LAYERS)) = None
    serves: L(WORD(K.STEP_REF, 8), 6) = None
    site_serves: NULLABLE(SAY(40)) = None
    declared: B = None
    lead: SAY(1500) = None
    ends_when: SAY(400) = None
    flag: NULLABLE(T(40)) = None
    tag: SAY(200) = None
    today: JourneyToday = None
    was: JourneyWas = None
    site: JourneySite = None
    helper: JourneyHelper = None
    sub: L(JourneySub, 10) = None
    children: L(WORD(K.JOURNEY_ID, 6), 10) = None
    directions: L(JourneyDirection, 12) = None
    build_rows: L(JourneyBuildRow, 12) = None
    rulings: L(JourneyRuling, 24) = None
    decisions: L(T(12), 24) = None
    quotes: L(JourneyQuote, 12) = None
    scenarios: L(JourneyScenario, 12) = None
    invariants: L(T(60), 8) = None
    backlog: L(JourneyBacklog, 24) = None


class JourneyFile(Closed):
    __def__ = 'journey.file'
    journeys: L(Journey, 8, 1)


class JourneyRowStatus(Closed):
    __def__ = 'journey.row_status'
    state: E(*K.READ_STATES, 'declared')
    proven_by: L(T(200)) = None
    failing: L(T(200)) = None
    site: NULLABLE(E(*K.SITE_STATUS)) = None
    drift: B = None


class JourneyStatusDriftItem(Closed):
    __inline__ = True
    row: T(40, 1)
    site: E(*K.SITE_STATUS)
    state: E(*K.READ_STATES, 'declared')


class JourneyStatus(Closed):
    __def__ = 'journey.status'
    schema_version: I(1)
    id: WORD(K.JOURNEY_ID, 6)
    definitions_sha: T(64, 1)
    state: E(*K.JOURNEY_STATES, 'unknown')
    counts: M(I(0))
    tests: M(E('passed', 'failed', 'missing'))
    rows: M(JourneyRowStatus)
    drift: L(JourneyStatusDriftItem) = None


DEFINES = {
    'journey.lane': JourneyLane,
    'journey.bind': JourneyBind,
    'journey.branch': JourneyBranch,
    'journey.step': JourneyStep,
    'journey.outcome': JourneyOutcome,
    'journey.edge': JourneyEdge,
    'journey.sub': JourneySub,
    'journey.ruling': JourneyRuling,
    'journey.quote': JourneyQuote,
    'journey.scenario': JourneyScenario,
    'journey.backlog': JourneyBacklog,
    'journey.direction': JourneyDirection,
    'journey.build_row': JourneyBuildRow,
    'journey.was': JourneyWas,
    'journey': Journey,
    'journey.file': JourneyFile,
    'journey.row_status': JourneyRowStatus,
    'journey.status': JourneyStatus,
}
__all__ = [
    'Journey', 'JourneyBacklog', 'JourneyBind', 'JourneyBranch', 'JourneyBuildRow', 'JourneyDirection', 'JourneyEdge',
    'JourneyFile', 'JourneyLane', 'JourneyOutcome', 'JourneyQuote', 'JourneyRowStatus', 'JourneyRuling', 'JourneyScenario',
    'JourneyStatus', 'JourneyStep', 'JourneySub', 'JourneyWas', 'DEFINES',
]
