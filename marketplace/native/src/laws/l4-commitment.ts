/**
 * L4 COMMITMENT law — V2 spec §3 row L4
 *
 * Rule: "operationalizes(W,C) iff every workflow step traces to an
 *        obligation/invariant AND all charter obligations have explicit
 *        coverage or declared gap."
 *
 * Mechanization: Coverage matrix auto-generated; gaps must be marked
 *                `gap_status='accepted'` to clear.
 *
 * For M3, L4 covers two relations:
 *   1. tracesAllSteps(W, C): every step in W.step_graph either traces to a
 *      Charter obligation/invariant OR declares an accepted gap.
 *   2. coversAllObligations(W, C): every Charter obligation either has a
 *      step that traces to it OR is marked gap_status='accepted'.
 *
 * The two predicates compose into `operationalizes(W, C)`.
 *
 * Tracing requires per-step metadata not on the V2 base Workflow shape — we
 * accept an opt-in extended step shape `WorkflowStepWithCoverage` and a
 * Charter `coverage_decisions` side-table; both are SOFT layers that the
 * Workflow Engine populates pre-terminate (M5).
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §3 L4
 */

import type { Constraint, WorkflowStep } from '../types/index.js'
import type { Charter } from '../primitives/charter.js'
import type { Workflow } from '../primitives/workflow.js'

/**
 * V2.4 §A12 T3 + L4: per-step coverage metadata. The base WorkflowStep is
 * V2.3 §A11 frozen; L4 needs a side-channel for traceability without
 * mutating the base primitive shape.
 *
 * - `traces_to`: Charter obligation/invariant Constraint.name list this step
 *   discharges (forms the coverage edge).
 * - `gap_status`: when `'accepted'`, step is allowed to NOT trace anywhere
 *   (declared gap per V2 §3 L4 row).
 */
export interface StepCoverage {
  step_id: number
  traces_to: string[]
  gap_status?: 'accepted' | 'open'
}

/**
 * V2 §3 L4 row: Charter obligation coverage decision.
 *
 * Workflow Engine emits one entry per obligation at terminate stage:
 * either a step (by step_id) covers it, or `gap_status='accepted'` clears it.
 */
export interface CoverageDecision {
  obligation_name: string
  /** step_id of a step in W.step_graph that traces to this obligation; null when gap declared. */
  covered_by_step: number | null
  gap_status?: 'accepted' | 'open'
}

export interface CoverageMatrix {
  /** Per-step traces; one entry per step_id in W.step_graph. */
  step_coverage: StepCoverage[]
  /** Per-obligation decisions; one entry per Charter obligation. */
  obligation_coverage: CoverageDecision[]
}

function obligationNames(c: Charter): Set<string> {
  const names = new Set<string>()
  for (const o of c.obligations) {
    if (typeof o.name === 'string' && o.name.length > 0) names.add(o.name)
  }
  return names
}

function invariantNames(c: Charter): Set<string> {
  const names = new Set<string>()
  for (const i of c.invariants) {
    if (typeof i.name === 'string' && i.name.length > 0) names.add(i.name)
  }
  return names
}

/** All trace targets a step is allowed to point at: obligations ∪ invariants. */
function allowedTraceNames(c: Charter): Set<string> {
  const out = new Set<string>([...obligationNames(c), ...invariantNames(c)])
  return out
}

function isAcceptedGap(s: StepCoverage): boolean {
  return s.gap_status === 'accepted'
}

function isAcceptedDecision(d: CoverageDecision): boolean {
  return d.gap_status === 'accepted'
}

export const l4Commitment = {
  /**
   * Predicate: every step in W traces to a Charter obligation/invariant
   * OR declares an accepted gap.
   *
   * Inputs:
   * - `w`: the Workflow (used for step_id list)
   * - `charter`: the Charter (provides allowed trace target names)
   * - `coverage`: per-step coverage metadata (one StepCoverage per step_id)
   *
   * Returns false if any step has no entry in `coverage.step_coverage`.
   */
  tracesAllSteps(w: Workflow, charter: Charter, coverage: CoverageMatrix): boolean {
    if (typeof w !== 'object' || w === null) return false
    if (typeof charter !== 'object' || charter === null) return false
    if (!Array.isArray(w.step_graph)) return false
    if (!Array.isArray(coverage.step_coverage)) return false

    const allowed = allowedTraceNames(charter)
    const byStepId = new Map<number, StepCoverage>()
    for (const sc of coverage.step_coverage) {
      if (typeof sc.step_id !== 'number') return false
      byStepId.set(sc.step_id, sc)
    }

    for (const step of w.step_graph as WorkflowStep[]) {
      const sc = byStepId.get(step.step_id)
      if (!sc) return false
      if (isAcceptedGap(sc)) continue
      // Must trace to ≥ 1 allowed name (obligation/invariant).
      if (!Array.isArray(sc.traces_to) || sc.traces_to.length === 0) return false
      const everyTraceAllowed = sc.traces_to.every((t) => allowed.has(t))
      if (!everyTraceAllowed) return false
    }
    return true
  },

  /**
   * Predicate: every Charter obligation either has a step trace OR has
   * gap_status='accepted'.
   */
  coversAllObligations(charter: Charter, coverage: CoverageMatrix): boolean {
    if (typeof charter !== 'object' || charter === null) return false
    if (!Array.isArray(coverage.obligation_coverage)) return false

    const obligations = obligationNames(charter)
    const byName = new Map<string, CoverageDecision>()
    for (const d of coverage.obligation_coverage) {
      if (typeof d.obligation_name !== 'string') return false
      byName.set(d.obligation_name, d)
    }

    for (const oblig of obligations) {
      const decision = byName.get(oblig)
      if (!decision) return false
      if (isAcceptedDecision(decision)) continue
      // Must point at a real step.
      if (typeof decision.covered_by_step !== 'number') return false
    }
    return true
  },

  /**
   * `operationalizes(W, C)` per V2 §3 L4: AND of the two predicates above.
   */
  operationalizes(w: Workflow, charter: Charter, coverage: CoverageMatrix): boolean {
    return (
      this.tracesAllSteps(w, charter, coverage) &&
      this.coversAllObligations(charter, coverage)
    )
  },
}

// Re-export Constraint type for downstream callers convenience.
export type { Constraint }
