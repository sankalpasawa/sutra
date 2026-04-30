/**
 * GovernanceOverhead — property tests (M8 Group AA T-114).
 *
 * Three properties × ≥1000 cases each:
 *
 * Property 1 — Monotonicity:
 *   For any sequence of `track()` calls within one turn, `tokens_governance`
 *   is non-decreasing. (Tokens are non-negative; accumulation never shrinks.)
 *
 * Property 2 — Threshold trip determinism:
 *   For (tokens_total, tokens_governance, threshold):
 *     - if (tokens_governance / tokens_total) > threshold ⇒ threshold_tripped=true
 *     - else                                              ⇒ threshold_tripped=false
 *   The runtime check is strictly greater-than (boundary equality does NOT trip).
 *
 * Property 3 — Turn isolation:
 *   For two distinct turn_ids run interleaved, ending one does not perturb
 *   the other's accumulated state.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group AA T-114
 *   - memory [Speed is core] PS-14
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  GovernanceOverhead,
  type GovernanceCategory,
} from '../../src/engine/governance-overhead.js'

const PROP_RUNS = 1000

const CATEGORIES: ReadonlyArray<GovernanceCategory> = [
  'input_routing',
  'depth_estimation',
  'blueprint',
  'build_layer',
  'codex_review',
  'hook_fire',
]

const categoryArb = fc.constantFrom<GovernanceCategory>(...CATEGORIES)
const trackArb = fc.tuple(
  categoryArb,
  fc.integer({ min: 0, max: 10_000 }),
)

describe('GovernanceOverhead — monotonicity (≥1000 cases)', () => {
  it('tokens_governance never decreases as track() calls accumulate', () => {
    fc.assert(
      fc.property(
        fc.array(trackArb, { minLength: 0, maxLength: 50 }),
        fc.integer({ min: 0, max: 1_000_000 }),
        (tracks, totalEstimate) => {
          const overhead = new GovernanceOverhead()
          overhead.startTurn('mono', totalEstimate)
          let last = 0
          for (const [cat, tokens] of tracks) {
            overhead.track('mono', cat, tokens)
            const peek = overhead.report('mono')
            expect(peek.tokens_governance).toBeGreaterThanOrEqual(last)
            last = peek.tokens_governance
          }
          // Final report from endTurn matches the last peek value.
          const final = overhead.endTurn('mono')
          expect(final.tokens_governance).toBe(last)
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('GovernanceOverhead — threshold trip determinism (≥1000 cases)', () => {
  it('overhead_pct > threshold ⇔ threshold_tripped=true (strict >)', () => {
    fc.assert(
      fc.property(
        // tokens_total ≥ 1 to avoid the div-by-zero short-circuit branch.
        fc.integer({ min: 1, max: 1_000_000 }),
        fc.integer({ min: 0, max: 1_000_000 }),
        fc.float({
          min: Math.fround(0),
          max: Math.fround(1),
          noNaN: true,
        }),
        (tokens_total, tokens_governance, threshold) => {
          const overhead = new GovernanceOverhead({ threshold })
          overhead.startTurn('thresh', tokens_total)
          // Single bucket carries all governance tokens — keeps the property
          // about the ratio, not the per-category split.
          overhead.track('thresh', 'input_routing', tokens_governance)
          const r = overhead.endTurn('thresh')

          const ratio = tokens_governance / tokens_total
          // The implementation MUST use strictly greater-than:
          //   ratio > threshold ⇒ tripped
          //   ratio ≤ threshold ⇒ not tripped
          if (ratio > r.threshold) {
            expect(r.threshold_tripped).toBe(true)
          } else {
            expect(r.threshold_tripped).toBe(false)
          }
          expect(r.overhead_pct).toBeCloseTo(ratio, 5)
          expect(r.threshold).toBe(Math.max(0, Math.min(1, threshold)))
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('GovernanceOverhead — turn isolation (≥1000 cases)', () => {
  it('parallel turns: track on A does not affect endTurn(B) report', () => {
    fc.assert(
      fc.property(
        fc.array(trackArb, { minLength: 0, maxLength: 25 }),
        fc.array(trackArb, { minLength: 0, maxLength: 25 }),
        // Interleave plan: pseudo-random which-turn-tracks-next.
        fc.array(fc.constantFrom<'A' | 'B'>('A', 'B'), {
          minLength: 0,
          maxLength: 50,
        }),
        fc.integer({ min: 1, max: 100_000 }),
        fc.integer({ min: 1, max: 100_000 }),
        (plansA, plansB, interleave, totalA, totalB) => {
          const overhead = new GovernanceOverhead()
          overhead.startTurn('A', totalA)
          overhead.startTurn('B', totalB)

          // Compute expected from the inputs WITHOUT touching the SUT —
          // the property is about: does the SUT's bookkeeping match?
          const expected: Record<'A' | 'B', { gov: number; perCat: Map<GovernanceCategory, number> }> = {
            A: { gov: 0, perCat: new Map() },
            B: { gov: 0, perCat: new Map() },
          }

          let aIdx = 0
          let bIdx = 0
          for (const which of interleave) {
            const plan = which === 'A' ? plansA : plansB
            const idx = which === 'A' ? aIdx : bIdx
            if (idx >= plan.length) continue
            const [cat, tokens] = plan[idx]!
            overhead.track(which, cat, tokens)
            expected[which].gov += tokens
            expected[which].perCat.set(
              cat,
              (expected[which].perCat.get(cat) ?? 0) + tokens,
            )
            if (which === 'A') aIdx++
            else bIdx++
          }
          // Drain any plan entries the interleave didn't reach so we still
          // exercise different sequence shapes.
          while (aIdx < plansA.length) {
            const [cat, tokens] = plansA[aIdx++]!
            overhead.track('A', cat, tokens)
            expected.A.gov += tokens
            expected.A.perCat.set(cat, (expected.A.perCat.get(cat) ?? 0) + tokens)
          }
          while (bIdx < plansB.length) {
            const [cat, tokens] = plansB[bIdx++]!
            overhead.track('B', cat, tokens)
            expected.B.gov += tokens
            expected.B.perCat.set(cat, (expected.B.perCat.get(cat) ?? 0) + tokens)
          }

          // End A first; assert B is still intact.
          const rA = overhead.endTurn('A')
          expect(rA.tokens_governance).toBe(expected.A.gov)
          expect(rA.tokens_total).toBe(totalA)
          for (const cat of CATEGORIES) {
            expect(rA.per_category[cat]).toBe(expected.A.perCat.get(cat) ?? 0)
          }

          // B must STILL match — A's endTurn cleared A's state, not B's.
          const rB = overhead.endTurn('B')
          expect(rB.tokens_governance).toBe(expected.B.gov)
          expect(rB.tokens_total).toBe(totalB)
          for (const cat of CATEGORIES) {
            expect(rB.per_category[cat]).toBe(expected.B.perCat.get(cat) ?? 0)
          }
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})
