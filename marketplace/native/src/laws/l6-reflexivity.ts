/**
 * L6 REFLEXIVITY law — V2.1 §A6
 *
 * Rule: "Workflows that modify Sutra primitives require an explicit
 *        reflexive_check Constraint with founder OR meta-charter
 *        authorization."
 *
 * Mechanization: reflexive_check Constraint fires before Workflow execution;
 *                founder gate or meta-charter approval blocks until granted.
 *
 * Bound Constraint sub-type per V2.1 §A5:
 *   `Constraint.type = 'reflexive_check'`
 *   triggers_when: target_workflow.modifies_paths ∩ Sutra_structural_paths != ∅
 *   requires:      founder_authorization OR meta_charter_approval
 *
 * Ties to V2.4 §A12 T6 (terminal-check) — L6 fires PRE-execution; T6 verifies
 * AT terminal_check that the auth was actually granted before success state.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §11 A6
 */

import type { Constraint } from '../types/index.js'
import type { Workflow } from '../primitives/workflow.js'

/**
 * Auth-token attachment for a reflexive_check Constraint.
 * The Workflow Engine populates these at the dispatch stage by reading
 * founder gate state and meta-charter approval ledgers.
 */
export interface ReflexiveCheckSatisfaction {
  constraint_name: string
  founder_authorization: boolean
  meta_charter_approval: boolean
}

/**
 * `satisfaction` is keyed by `Constraint.name` so callers can match each
 * reflexive_check Constraint to its auth view.
 */
export type ReflexiveSatisfactionMap = Record<string, ReflexiveCheckSatisfaction>

function isReflexiveCheck(c: Constraint): boolean {
  return c.type === 'reflexive_check'
}

export const l6Reflexivity = {
  /**
   * Predicate: does this Workflow require approval (i.e. is L6 NOT yet
   * cleared)?
   *
   * - If `workflow.modifies_sutra=false`: never requires approval (L6 is
   *   a no-op).
   * - If `workflow.modifies_sutra=true` AND there exists ≥ 1 reflexive_check
   *   Constraint in `constraints`:
   *      requires_approval = NOT(any reflexive_check Constraint has both
   *      its auth tokens populated AND at least one set true).
   * - If `workflow.modifies_sutra=true` AND no reflexive_check Constraint
   *   in `constraints`: requires_approval = true (must declare gate).
   *
   * Defensive shape checks for deserialized Constraints.
   */
  requiresApproval(
    workflow: Workflow,
    constraints: ReadonlyArray<Constraint>,
    satisfaction: ReflexiveSatisfactionMap = {},
  ): boolean {
    if (typeof workflow !== 'object' || workflow === null) return true
    if (typeof workflow.modifies_sutra !== 'boolean') return true
    if (!workflow.modifies_sutra) return false
    if (!Array.isArray(constraints)) return true

    const reflexive = constraints.filter(
      (c) => typeof c === 'object' && c !== null && isReflexiveCheck(c),
    )
    if (reflexive.length === 0) return true

    // Approval is granted iff AT LEAST ONE reflexive_check Constraint has
    // a recorded satisfaction with founder OR meta-charter approval set.
    for (const c of reflexive) {
      if (typeof c.name !== 'string' || c.name.length === 0) continue
      const sat = satisfaction[c.name]
      if (typeof sat !== 'object' || sat === null) continue
      if (typeof sat.founder_authorization !== 'boolean') continue
      if (typeof sat.meta_charter_approval !== 'boolean') continue
      if (sat.founder_authorization === true || sat.meta_charter_approval === true) {
        return false
      }
    }
    return true
  },

  /**
   * Convenience: returns the list of reflexive_check Constraints in a
   * Constraint[] (for engine telemetry / audit).
   */
  reflexiveChecks(constraints: ReadonlyArray<Constraint>): Constraint[] {
    if (!Array.isArray(constraints)) return []
    return constraints.filter(
      (c) => typeof c === 'object' && c !== null && isReflexiveCheck(c),
    )
  },
}
