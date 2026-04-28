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
 * - every step traces to ALL obligation/invariant names so that the L4
 *   relation-check (codex M3 P1: step.traces_to MUST include the obligation
 *   it's claimed to cover) holds regardless of which step we point at
 * - every obligation gets a covering step (the first step) decision
 * - if no obligations/invariants exist, every step gets gap_status='accepted'
 *
 * NOTE on step_id uniqueness: workflowArb (post-codex-M3-P1) renumbers steps
 * so step_id matches array index — duplicates are no longer possible. This
 * helper relies on that invariant.
 */
function happyCoverage(
  w: { step_graph: Array<{ step_id: number }> },
  c: { obligations: Array<{ name: string }>; invariants: Array<{ name: string }> },
): CoverageMatrix {
  const allowed = [...c.obligations.map((o) => o.name), ...c.invariants.map((i) => i.name)]
  const stepCoverage = w.step_graph.map((s) =>
    allowed.length > 0
      ? { step_id: s.step_id, traces_to: [...allowed] }
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
        (w, c) => {
          // workflowArb (post-codex-M3-P1) guarantees unique step_ids, so
          // dropping the first coverage entry leaves a real (un-aliased) gap.
          const cov = happyCoverage(w, c)
          const broken: CoverageMatrix = {
            ...cov,
            step_coverage: cov.step_coverage.slice(1),
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

  // ---------------------------------------------------------------------------
  // Codex M3 P1 #3 (2026-04-28) — coversAllObligations relation-check:
  // forall fabricated covered_by_step (disagreeing with step.traces_to or
  // missing from step_graph): operationalizes(W,C) === false.
  // ---------------------------------------------------------------------------

  it('P1.3: forall (W, C) with covered_by_step pointing to non-existent step: operationalizes == false', () => {
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
          // Replace ALL covered_by_step with an id outside step_graph.
          // workflowArb renumbers step_ids 0..n-1, so n+9999 is guaranteed absent.
          const offset = w.step_graph.length + 9999
          const broken: CoverageMatrix = {
            ...cov,
            obligation_coverage: cov.obligation_coverage.map((d) => ({
              ...d,
              covered_by_step: offset,
            })),
          }
          return l4Commitment.operationalizes(w, c, broken) === false
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('P1.3: forall (W, C) with covered_by_step real but step.traces_to missing the obligation: operationalizes == false', () => {
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
          // Wipe traces_to on every step, but pretend the first obligation is
          // still covered. Relation-check must catch the disagreement.
          const broken: CoverageMatrix = {
            step_coverage: cov.step_coverage.map((sc) => ({
              ...sc,
              traces_to: [],
              gap_status: 'accepted' as const,
            })),
            // Re-claim coverage on a real step (id=0) that no longer traces.
            obligation_coverage: c.obligations.map((o) => ({
              obligation_name: o.name,
              covered_by_step: w.step_graph[0]!.step_id,
            })),
          }
          // operationalizes also calls tracesAllSteps; with all gaps accepted
          // tracesAllSteps passes, so the FALSE outcome must come from the
          // relation-check inside coversAllObligations (codex M3 P1 #3).
          return l4Commitment.operationalizes(w, c, broken) === false
        },
      ),
      { numRuns: 1000 },
    )
  })
})
