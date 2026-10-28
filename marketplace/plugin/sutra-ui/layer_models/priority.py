"""Priority's records (A1.13b): the estimate, the price and the ceiling."""
from .base import Open
from .common import BARE, NULLABLE, T, I, N, E, L, M, Name


class PriorityEstimatePerEngineValue(Open):
    __inline__ = True
    calls: I(0) = None
    usd: N(0) = None
    basis: E('median', 'prior') = None
    runs: I(0) = None


class PriorityEstimate(Open):
    __def__ = 'priority.estimate'
    calls: I(0)
    usd: N(0)
    basis: E('median', 'prior', 'line') = None
    runs: I(0) = None
    per_engine: M(PriorityEstimatePerEngineValue) = None


class PriorityPriceRoom(Open):
    __inline__ = True
    calls: I() = None
    usd: N() = None


class PriorityPriceRemaining(Open):
    __inline__ = True
    calls: I() = None
    usd: N() = None


class PriorityPriceIndices(Open):
    __inline__ = True
    spend_per_run: M(N(0)) = None
    checks: M(E('ok', 'failed', 'none')) = None


class PriorityPrice(Open):
    __def__ = 'priority.price'
    at: T(40)
    proposal: E('line', 'round', 'engine', 'cost')
    estimate: PriorityEstimate
    room: PriorityPriceRoom
    answer: E('accept', 'counter', 'reject')
    why: T(600)
    schema_version: I(1) = None
    id: T(40) = None
    cycle_id: NULLABLE(T(80)) = None
    round: NULLABLE(I(1)) = None
    thread: T(80) = None
    engines: L(Name) = None
    remaining: PriorityPriceRemaining = None
    keep: L(Name) = None
    indices: PriorityPriceIndices = None


class PriorityCeilingStart(Open):
    __inline__ = True
    rounds: I(1)
    calls: I(0)
    usd: N(0)


class PriorityCeilingRaisedItem(Open):
    __inline__ = True
    at: T(40) = None
    by: T(80) = None
    to: BARE = None


class PriorityCeiling(Open):
    __def__ = 'priority.ceiling'
    rounds: I(1, 99)
    calls: I(0)
    usd: N(0)
    start: PriorityCeilingStart
    raised: L(PriorityCeilingRaisedItem) = None
    at: T(40) = None


DEFINES = {
    'priority.estimate': PriorityEstimate,
    'priority.price': PriorityPrice,
    'priority.ceiling': PriorityCeiling,
}
__all__ = [
    'PriorityCeiling', 'PriorityEstimate', 'PriorityPrice', 'DEFINES',
]
