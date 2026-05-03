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
import type { Constraint } from '../types/index.js';
import type { Charter } from '../primitives/charter.js';
import type { Workflow } from '../primitives/workflow.js';
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
    step_id: number;
    traces_to: string[];
    gap_status?: 'accepted' | 'open';
}
/**
 * V2 §3 L4 row: Charter obligation coverage decision.
 *
 * Workflow Engine emits one entry per obligation at terminate stage:
 * either a step (by step_id) covers it, or `gap_status='accepted'` clears it.
 */
export interface CoverageDecision {
    obligation_name: string;
    /** step_id of a step in W.step_graph that traces to this obligation; null when gap declared. */
    covered_by_step: number | null;
    gap_status?: 'accepted' | 'open';
}
export interface CoverageMatrix {
    /** Per-step traces; one entry per step_id in W.step_graph. */
    step_coverage: StepCoverage[];
    /** Per-obligation decisions; one entry per Charter obligation. */
    obligation_coverage: CoverageDecision[];
}
export declare const l4Commitment: {
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
    tracesAllSteps(w: Workflow, charter: Charter, coverage: CoverageMatrix): boolean;
    /**
     * Predicate: every Charter obligation either has a step trace OR has
     * gap_status='accepted'.
     *
     * Codex M3 P1 fix 2026-04-28: shape-check is insufficient. A
     * `covered_by_step` integer that doesn't refer to a real step in
     * `workflow.step_graph` — or refers to a step whose `traces_to` does NOT
     * include this obligation — must be rejected. Otherwise a Workflow can
     * fabricate coverage decisions and pass `operationalizes` with no real
     * coverage edge.
     *
     * `workflow` is OPTIONAL for backwards-compat: when absent we keep the old
     * shape-only behavior (used by tests that exercise charter+coverage in
     * isolation, e.g. "missing decision → false"). `operationalizes` always
     * passes a workflow so the relation-check is enforced for the composed
     * predicate.
     */
    coversAllObligations(charter: Charter, coverage: CoverageMatrix, workflow?: Workflow): boolean;
    /**
     * `operationalizes(W, C)` per V2 §3 L4: AND of the two predicates above.
     *
     * Codex M3 P1 fix 2026-04-28: passes Workflow to coversAllObligations so
     * the relation-check (covered_by_step exists + step.traces_to includes
     * obligation) runs for the composed predicate.
     */
    operationalizes(w: Workflow, charter: Charter, coverage: CoverageMatrix): boolean;
};
export type { Constraint };
//# sourceMappingURL=l4-commitment.d.ts.map