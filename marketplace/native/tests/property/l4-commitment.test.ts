/**
 * L4 COMMITMENT — property tests (V2 §3)
 *
 * tracesAllSteps + coversAllObligations + operationalizes.
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { l4Commitment, type CoverageMatrix } from '../../src/laws/l4-commitment.js'
import { charterArb, workflowArb, constraintArb } from './arbitraries.js'

/**
 * Build a happy-path coverage matrix for a (workflow, charter) pair:
 * - every step traces to first available obligation/invariant name
 * - every obligation gets a covering step (the first step) decision
 * - if no obligations/invariants exist, every step gets gap_status='accepted'
 */
function happyCoverage(
  w: { step_graph: Array<{ step_id: number }> },
  c: { obligations: Array<{ name: string }>; invariants: Array<{ name: string }> },
): CoverageMatrix {
  const allowed = [...c.obligations.map((o) => o.name), ...c.invariants.map((i) => i.name)]
  const stepCoverage = w.step_graph.map((s) =>
    allowed.length > 0
      ? { step_id: s.step_id, traces_to: [allowed[0]!] }
      : { step_id: s.step_id, traces_to: [], gap_status: 'accepted' as const },
  )
  const firstStepId = w.step_graph[0]?.step_id ?? 0
  const obligationCoverage = c.obligations.map((o) => ({
    obligation_name: o.name,
    covered_by_step: firstStepId,
  }))
  return { step_coverage: stepCoverage, obligation_coverage: obligationCoverage }
}

describe('L4 COMMITMENT — property tests', () => {
  it('forall (W, C) with happy coverage: tracesAllSteps == true', () => {
    fc.assert(
      fc.property(
        workflowArb(),
        charterArb({
          obligations: fc.array(constraintArb({ forceType: 'obligation' }), {
            minLength: 1,
            maxLength: 3,
          }),
        }),
        (w, c) => {
          const cov = happyCoverage(w, c)
          return l4Commitment.tracesAllSteps(w, c, cov) === true
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall (W, C) with happy coverage: coversAllObligations == true', () => {
    fc.assert(
      fc.property(
        workflowArb(),
        charterArb({
          obligations: fc.array(constraintArb({ forceType: 'obligation' }), {
            minLength: 1,
            maxLength: 3,
          }),
        }),
        (w, c) => {
          const cov = happyCoverage(w, c)
          return l4Commitment.coversAllObligations(c, cov) === true
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall (W, C) with missing step coverage entry: tracesAllSteps == false', () => {
    fc.assert(
      fc.property(
        workflowArb(),
        charterArb({
          obligations: fc.array(constraintArb({ forceType: 'obligation' }), {
            minLength: 1,
            maxLength: 3,
          }),
        }),
        (rawW, c) => {
          // Force unique step_ids so that "drop one entry from coverage" creates
          // a real gap. workflowArb() doesn't constrain step_id uniqueness — the
          // base type allows duplicates, and L4 keys coverage by step_id.
          const w = {
            ...rawW,
            step_graph: rawW.step_graph.map((s, i) => ({ ...s, step_id: i })),
          }
          const cov = happyCoverage(w, c)
          // Drop one step's coverage. With unique step_ids, this leaves a real gap.
          const broken: CoverageMatrix = {
            ...cov,
            step_coverage: cov.step_coverage.slice(1),
          }
          if (w.step_graph.length === 1) {
            // Only one step; dropping it always exposes a gap. Verified directly.
            return l4Commitment.tracesAllSteps(w, c, broken) === false
          }
          return l4Commitment.tracesAllSteps(w, c, broken) === false
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall Charter with obligations but missing decision: coversAllObligations == false', () => {
    fc.assert(
      fc.property(
        workflowArb(),
        charterArb({
          obligations: fc.array(constraintArb({ forceType: 'obligation' }), {
            minLength: 1,
            maxLength: 3,
          }),
        }),
        (w, c) => {
          const cov = happyCoverage(w, c)
          const broken: CoverageMatrix = {
            ...cov,
            obligation_coverage: [],
          }
          return l4Commitment.coversAllObligations(c, broken) === false
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall (W, C) with happy coverage: operationalizes == true', () => {
    fc.assert(
      fc.property(
        workflowArb(),
        charterArb({
          obligations: fc.array(constraintArb({ forceType: 'obligation' }), {
            minLength: 1,
            maxLength: 3,
          }),
        }),
        (w, c) => {
          const cov = happyCoverage(w, c)
          return l4Commitment.operationalizes(w, c, cov) === true
        },
      ),
      { numRuns: 1000 },
    )
  })
})
