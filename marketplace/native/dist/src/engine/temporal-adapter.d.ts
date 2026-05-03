/**
 * TemporalAdapter — M5 Group I (T-041, T-042).
 *
 * Maps a Sutra Workflow primitive onto the Temporal SDK execution model.
 *
 * Codex P2.5 — orchestration shape (CRITICAL):
 *   ONE Temporal workflow function orchestrates the ORDERED Sutra step_graph.
 *   Per-step I/O lives in ACTIVITIES — NOT one Temporal workflow per Sutra
 *   step. The Temporal workflow body sequences activity calls in step_graph
 *   order; failure handling per step_graph[i].on_failure routes there.
 *
 * This is the SHELL: the function exists, returns a typed
 * TemporalWorkflowDefinition, and produces Activity descriptors per step. The
 * actual Temporal Worker registration + worker dispatch lands in subsequent
 * Group I tasks (or M5 Group J onward).
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group I T-041, T-042
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5 (wire flow)
 */
import type { Workflow } from '../primitives/workflow.js';
import type { DataRef, StepFailureAction, StepAction } from '../types/index.js';
import { type ActivityDispatcher, type ExecuteOptions, type ExecutionResult } from './step-graph-executor.js';
/**
 * Activity descriptor — one entry per Sutra step in the step_graph.
 *
 * The orchestrating Temporal workflow function reads this list in order and
 * calls each activity (via Temporal's `proxyActivities` pattern at runtime).
 * Per codex P2.5: the Temporal workflow does NOT split into per-step
 * Temporal workflows — it stays as ONE orchestration that sequences
 * activities.
 */
export interface ActivityDescriptor {
    /** Sutra step_id (preserves the source order & identity). */
    step_id: number;
    /** Sutra skill_ref OR action — at least one is set (mutually exclusive per V2.3 §A11). */
    skill_ref: string | null;
    action: StepAction | null;
    inputs: DataRef[];
    outputs: DataRef[];
    on_failure: StepFailureAction;
}
/**
 * The Temporal workflow definition produced by `registerWorkflow`. This is the
 * type the engine layer + Worker registration consume; the real Temporal SDK
 * registration ships at runtime when the Worker is wired up.
 */
export interface TemporalWorkflowDefinition {
    /** Stable id — matches Sutra Workflow.id. */
    workflow_id: string;
    /**
     * Temporal task queue name. Default: derived from workflow_id. Workers poll
     * this queue. Convention: `sutra-<workflow_id_slug>`.
     */
    task_queue: string;
    /**
     * Ordered activity descriptors — one per Sutra step. The orchestrating
     * `run()` function iterates this list in order.
     */
    activities: ActivityDescriptor[];
    /**
     * The orchestrating Temporal workflow function. M5 Group K (T-049):
     * delegates to `executeStepGraph` for deterministic dispatch + failure
     * routing + terminalCheck integration. The Group I shell `__shell:true`
     * tag is REMOVED — `run()` returns the real `ExecutionResult` from the
     * step-graph executor.
     *
     * Caller may supply a `dispatch` function (the I/O boundary; tests inject
     * deterministic mocks; production wires real Temporal `proxyActivities`).
     * When `dispatch` is omitted, a default dispatcher returns
     * `{ kind: 'ok', outputs: [] }` for every step — useful for the
     * "registration smoke" path; the real Worker integration provides the
     * production dispatcher at M11 dogfood entry.
     */
    run: (input?: {
        dispatch?: ActivityDispatcher;
        options?: ExecuteOptions;
    } | Record<string, unknown>) => Promise<ExecutionResult>;
}
/**
 * Map a Sutra Workflow onto a Temporal workflow definition.
 *
 * Per codex P2.5: ONE Temporal workflow orchestrates the ordered Sutra
 * step_graph; per-step I/O lives in Activities. This shell preserves order
 * and wires per-step descriptors; the real activity invocations + retry
 * policies are populated by Group I/J runtime tasks.
 *
 * @param sutraWorkflow  A Sutra Workflow primitive (id starts with `W-`).
 * @returns TemporalWorkflowDefinition shell (workflow_id, task_queue,
 *          activities[], run()).
 * @throws TypeError when input is not a Workflow shape.
 * @throws Error when step_graph is empty (degenerate orchestration —
 *         a Sutra Workflow with no steps cannot be operationalized).
 */
export declare function registerWorkflow(sutraWorkflow: Workflow): TemporalWorkflowDefinition;
//# sourceMappingURL=temporal-adapter.d.ts.map