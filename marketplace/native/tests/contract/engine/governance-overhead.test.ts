/**
 * GovernanceOverhead contract test (M8 Group AA T-111/T-112/T-113).
 *
 * Asserts:
 *  - startTurn / track / endTurn happy path (no threshold trip)
 *  - threshold trip emits an OTel event ('GOVERNANCE_OVERHEAD_ALERT') when an
 *    OTelEmitter is injected
 *  - threshold trip with no emitter is non-blocking (does not throw)
 *  - track without startTurn throws TurnNotStartedError
 *  - endTurn clears state — subsequent track on same turn_id throws
 *  - all 6 categories accumulate independently
 *  - SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD env override + invalid fallback
 *  - per-turn isolation (T-113): two turns in flight do not cross-contaminate
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group AA
 *   - memory [Speed is core] PS-14 (≤15% governance overhead per turn)
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'

import {
  GovernanceOverhead,
  TurnNotStartedError,
  type GovernanceCategory,
} from '../../../src/engine/governance-overhead.js'
import {
  InMemoryOTelExporter,
  OTelEmitter,
} from '../../../src/engine/otel-emitter.js'

const ALL_CATEGORIES: ReadonlyArray<GovernanceCategory> = [
  'input_routing',
  'depth_estimation',
  'blueprint',
  'build_layer',
  'codex_review',
  'hook_fire',
]

describe('GovernanceOverhead — happy path (T-111)', () => {
  it('startTurn/track/endTurn produces a report with non-tripped threshold', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('turn-1', 1000)
    overhead.track('turn-1', 'input_routing', 50)
    overhead.track('turn-1', 'depth_estimation', 30)
    const r = overhead.endTurn('turn-1')

    expect(r.turn_id).toBe('turn-1')
    expect(r.tokens_total).toBe(1000)
    expect(r.tokens_governance).toBe(80)
    expect(r.overhead_pct).toBeCloseTo(0.08, 5)
    expect(r.threshold).toBe(0.15)
    expect(r.threshold_tripped).toBe(false)
    expect(r.per_category.input_routing).toBe(50)
    expect(r.per_category.depth_estimation).toBe(30)
    // Untouched categories report 0.
    expect(r.per_category.blueprint).toBe(0)
    expect(r.per_category.build_layer).toBe(0)
    expect(r.per_category.codex_review).toBe(0)
    expect(r.per_category.hook_fire).toBe(0)
  })

  it('all 6 categories accumulate independently', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('turn-cats', 10_000)
    for (const cat of ALL_CATEGORIES) {
      overhead.track('turn-cats', cat, 100)
    }
    // Doubling one category to confirm it is per-category, not pooled.
    overhead.track('turn-cats', 'codex_review', 250)
    const r = overhead.endTurn('turn-cats')

    expect(r.per_category.input_routing).toBe(100)
    expect(r.per_category.depth_estimation).toBe(100)
    expect(r.per_category.blueprint).toBe(100)
    expect(r.per_category.build_layer).toBe(100)
    expect(r.per_category.codex_review).toBe(350)
    expect(r.per_category.hook_fire).toBe(100)
    expect(r.tokens_governance).toBe(850)
  })

  it('report() peeks at the in-flight turn without ending it', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('turn-peek', 500)
    overhead.track('turn-peek', 'blueprint', 20)
    const peek = overhead.report('turn-peek')
    expect(peek.tokens_governance).toBe(20)
    // Turn is still live — track again then end.
    overhead.track('turn-peek', 'blueprint', 30)
    const final = overhead.endTurn('turn-peek')
    expect(final.tokens_governance).toBe(50)
  })
})

describe('GovernanceOverhead — threshold alert (T-112)', () => {
  it('emits GOVERNANCE_OVERHEAD_ALERT when overhead exceeds threshold', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const overhead = new GovernanceOverhead({ otelEmitter: emitter })

    overhead.startTurn('turn-trip', 100)
    overhead.track('turn-trip', 'input_routing', 50) // 50% overhead
    const r = overhead.endTurn('turn-trip')

    expect(r.threshold_tripped).toBe(true)
    expect(r.overhead_pct).toBeCloseTo(0.5, 5)
    // Emit is fire-and-forget; drain the microtask queue.
    await new Promise((res) => setImmediate(res))
    expect(exporter.records).toHaveLength(1)
    const rec = exporter.records[0]!
    expect(rec.decision_kind).toBe('GOVERNANCE_OVERHEAD_ALERT')
    expect(rec.trace_id).toBe('turn-trip')
    expect(rec.actor).toBe('sutra-native:governance-overhead')
    expect(rec.attributes).toMatchObject({
      threshold: 0.15,
      overhead_pct: 0.5,
      tokens_total: 100,
      tokens_governance: 50,
    })
    // per_category is carried in attributes (snapshot, not a mutable ref).
    expect(rec.attributes.per_category).toMatchObject({
      input_routing: 50,
      depth_estimation: 0,
      blueprint: 0,
      build_layer: 0,
      codex_review: 0,
      hook_fire: 0,
    })
  })

  it('threshold NOT tripped ⇒ no alert emitted', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const overhead = new GovernanceOverhead({ otelEmitter: emitter })
    overhead.startTurn('turn-ok', 1000)
    overhead.track('turn-ok', 'input_routing', 100) // 10% < 15%
    overhead.endTurn('turn-ok')
    await new Promise((res) => setImmediate(res))
    expect(exporter.records).toHaveLength(0)
  })

  it('threshold trip with no injected emitter is non-blocking (D-NS-27)', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('turn-no-emit', 100)
    overhead.track('turn-no-emit', 'codex_review', 80)
    // Must NOT throw even though threshold trips.
    expect(() => overhead.endTurn('turn-no-emit')).not.toThrow()
  })

  it('exact-threshold ratio does NOT trip (strictly greater-than only)', async () => {
    const exporter = new InMemoryOTelExporter()
    const overhead = new GovernanceOverhead({
      otelEmitter: new OTelEmitter(exporter),
    })
    overhead.startTurn('turn-exact', 1000)
    overhead.track('turn-exact', 'input_routing', 150) // exactly 15%
    const r = overhead.endTurn('turn-exact')
    expect(r.overhead_pct).toBeCloseTo(0.15, 5)
    expect(r.threshold_tripped).toBe(false)
    await new Promise((res) => setImmediate(res))
    expect(exporter.records).toHaveLength(0)
  })

  it('zero tokens_total ⇒ overhead_pct = 0, no trip (avoid div-by-zero)', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('turn-zero', 0)
    overhead.track('turn-zero', 'blueprint', 0)
    const r = overhead.endTurn('turn-zero')
    expect(r.overhead_pct).toBe(0)
    expect(r.threshold_tripped).toBe(false)
  })

  it('emitter rejection on alert is swallowed (non-blocking)', async () => {
    // Build a custom exporter that rejects on export. The emitter call is
    // fire-and-forget — the catch in endTurn() must swallow the rejection
    // so the caller never sees an unhandled promise rejection escape.
    const failingEmitter = new OTelEmitter({
      export: async () => {
        throw new Error('exporter offline')
      },
      flush: async () => {},
    })
    const overhead = new GovernanceOverhead({ otelEmitter: failingEmitter })
    overhead.startTurn('turn-fail', 100)
    overhead.track('turn-fail', 'codex_review', 80) // trips
    expect(() => overhead.endTurn('turn-fail')).not.toThrow()
    // Drain the microtask queue so the .catch() handler runs before
    // vitest tears down the test (otherwise an unhandled rejection here
    // would surface as a test-suite failure).
    await new Promise((res) => setImmediate(res))
  })
})

describe('GovernanceOverhead — turn isolation (T-113)', () => {
  it('two concurrent turns accumulate independently', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('A', 1000)
    overhead.startTurn('B', 2000)
    overhead.track('A', 'input_routing', 50)
    overhead.track('B', 'input_routing', 200)
    overhead.track('A', 'codex_review', 25)
    overhead.track('B', 'codex_review', 100)

    const rA = overhead.endTurn('A')
    expect(rA.tokens_governance).toBe(75)
    expect(rA.tokens_total).toBe(1000)
    expect(rA.per_category.input_routing).toBe(50)
    expect(rA.per_category.codex_review).toBe(25)

    // B is still live and unaffected by A's endTurn.
    overhead.track('B', 'blueprint', 10)
    const rB = overhead.endTurn('B')
    expect(rB.tokens_governance).toBe(310)
    expect(rB.per_category.input_routing).toBe(200)
    expect(rB.per_category.codex_review).toBe(100)
    expect(rB.per_category.blueprint).toBe(10)
  })

  it('track without startTurn throws TurnNotStartedError', () => {
    const overhead = new GovernanceOverhead()
    expect(() => overhead.track('orphan', 'input_routing', 10)).toThrow(
      TurnNotStartedError,
    )
  })

  it('endTurn clears state — subsequent track on same turn_id throws', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('once', 1000)
    overhead.track('once', 'input_routing', 50)
    overhead.endTurn('once')
    expect(() => overhead.track('once', 'input_routing', 1)).toThrow(
      TurnNotStartedError,
    )
  })

  it('endTurn on un-started turn throws TurnNotStartedError', () => {
    const overhead = new GovernanceOverhead()
    expect(() => overhead.endTurn('never-started')).toThrow(TurnNotStartedError)
  })

  it('report() on un-started turn throws TurnNotStartedError', () => {
    const overhead = new GovernanceOverhead()
    expect(() => overhead.report('never-started')).toThrow(TurnNotStartedError)
  })

  it('startTurn twice for the same turn_id resets state (idempotent restart)', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('rerun', 100)
    overhead.track('rerun', 'input_routing', 5)
    // Restart — old accumulation is wiped.
    overhead.startTurn('rerun', 200)
    const r = overhead.endTurn('rerun')
    expect(r.tokens_total).toBe(200)
    expect(r.tokens_governance).toBe(0)
  })
})

describe('GovernanceOverhead — env var threshold override', () => {
  const ORIG = process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD

  beforeEach(() => {
    delete process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD
  })
  afterEach(() => {
    if (ORIG === undefined) {
      delete process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD
    } else {
      process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD = ORIG
    }
  })

  it('env override 0.05 makes 8% overhead trip', () => {
    process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD = '0.05'
    const overhead = new GovernanceOverhead()
    expect(overhead.threshold).toBe(0.05)
    overhead.startTurn('turn-env', 1000)
    overhead.track('turn-env', 'input_routing', 80) // 8%
    const r = overhead.endTurn('turn-env')
    expect(r.threshold).toBe(0.05)
    expect(r.threshold_tripped).toBe(true)
  })

  it('invalid env var falls back to 0.15', () => {
    process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD = 'not-a-number'
    const overhead = new GovernanceOverhead()
    expect(overhead.threshold).toBe(0.15)
  })

  it('out-of-range env var (> 1) clamps to 1', () => {
    process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD = '5'
    const overhead = new GovernanceOverhead()
    expect(overhead.threshold).toBe(1)
  })

  it('out-of-range env var (< 0) clamps to 0', () => {
    process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD = '-0.5'
    const overhead = new GovernanceOverhead()
    expect(overhead.threshold).toBe(0)
  })

  it('explicit threshold ctor option overrides env', () => {
    process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD = '0.05'
    const overhead = new GovernanceOverhead({ threshold: 0.5 })
    expect(overhead.threshold).toBe(0.5)
  })

  it('explicit threshold out-of-range is clamped', () => {
    const overheadHi = new GovernanceOverhead({ threshold: 99 })
    expect(overheadHi.threshold).toBe(1)
    const overheadLo = new GovernanceOverhead({ threshold: -1 })
    expect(overheadLo.threshold).toBe(0)
  })
})

describe('GovernanceOverhead — input validation', () => {
  it('track with negative tokens throws', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('t-neg', 1000)
    expect(() => overhead.track('t-neg', 'input_routing', -1)).toThrow(RangeError)
  })

  it('track with non-finite tokens throws', () => {
    const overhead = new GovernanceOverhead()
    overhead.startTurn('t-nan', 1000)
    expect(() => overhead.track('t-nan', 'input_routing', NaN)).toThrow(RangeError)
    expect(() =>
      overhead.track('t-nan', 'input_routing', Infinity),
    ).toThrow(RangeError)
  })

  it('startTurn with negative tokens_total throws', () => {
    const overhead = new GovernanceOverhead()
    expect(() => overhead.startTurn('t-neg-total', -100)).toThrow(RangeError)
  })

  it('TurnNotStartedError carries turn_id in message', () => {
    const overhead = new GovernanceOverhead()
    try {
      overhead.track('phantom', 'input_routing', 1)
      throw new Error('expected throw')
    } catch (e) {
      expect(e).toBeInstanceOf(TurnNotStartedError)
      expect((e as Error).message).toContain('phantom')
    }
  })
})
