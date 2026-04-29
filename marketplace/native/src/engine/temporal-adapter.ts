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

import type { Workflow } from '../primitives/workflow.js'
import type { DataRef, StepFailureAction, StepAction } from '../types/index.js'

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
  step_id: number
  /** Sutra skill_ref OR action — at least one is set (mutually exclusive per V2.3 §A11). */
  skill_ref: string | null
  action: StepAction | null
  inputs: DataRef[]
  outputs: DataRef[]
  on_failure: StepFailureAction
}

/**
 * The Temporal workflow definition produced by `registerWorkflow`. This is the
 * type the engine layer + Worker registration consume; the real Temporal SDK
 * registration ships at runtime when the Worker is wired up.
 */
export interface TemporalWorkflowDefinition {
  /** Stable id — matches Sutra Workflow.id. */
  workflow_id: string
  /**
   * Temporal task queue name. Default: derived from workflow_id. Workers poll
   * this queue. Convention: `sutra-<workflow_id_slug>`.
   */
  task_queue: string
  /**
   * Ordered activity descriptors — one per Sutra step. The orchestrating
   * `run()` function iterates this list in order.
   */
  activities: ActivityDescriptor[]
  /**
   * The orchestrating Temporal workflow function (shell). At runtime, Temporal
   * SDK calls this from inside the Workflow sandbox; it sequences activities
   * via `proxyActivities` and routes per-step failures per `on_failure`.
   *
   * At M5 Group I this is a typed shell: callable, returns a structured
   * trace of step ids visited. The full Temporal-SDK-native body (with
   * `proxyActivities`, retry policies, signals, and timers) lands in
   * subsequent Group I/J tasks.
   */
  run: (input?: Record<string, unknown>) => Promise<{
    workflow_id: string
    visited_step_ids: number[]
    /**
     * Fail-fast shell tag — present (true) until Group J/K replaces this
     * function body with the real Temporal-SDK orchestration. Tests assert
     * this tag is set, so when the real body lands and this field is removed
     * the contract test fails loudly and forces a contract update — preventing
     * downstream groups from getting a fake "success" against the shell.
     */
    __shell?: boolean
  }>
}

/**
 * Slugify a Sutra workflow id into a Temporal task queue name.
 *
 * Convention: lower-case, alphanumeric + dash; collapse runs, strip the
 * `W-` prefix, prepend `sutra-`. Pure function — no I/O, no clock.
 */
function deriveTaskQueue(workflowId: string): string {
  const stripped = workflowId.replace(/^W-/, '')
  const slug = stripped
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
  return `sutra-${slug || 'workflow'}`
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
export function registerWorkflow(
  sutraWorkflow: Workflow,
): TemporalWorkflowDefinition {
  if (
    typeof sutraWorkflow !== 'object' ||
    sutraWorkflow === null ||
    typeof (sutraWorkflow as Workflow).id !== 'string' ||
    !Array.isArray((sutraWorkflow as Workflow).step_graph)
  ) {
    throw new TypeError(
      'registerWorkflow: input must be a Workflow with `id: string` and `step_graph: WorkflowStep[]`',
    )
  }
  if (sutraWorkflow.step_graph.length === 0) {
    throw new Error(
      `registerWorkflow: Workflow ${sutraWorkflow.id} has empty step_graph — cannot orchestrate`,
    )
  }

  const workflow_id = sutraWorkflow.id
  const task_queue = deriveTaskQueue(workflow_id)

  // Defensive — Workflow primitive validators run earlier but pre-typeguarded
  // for safety in case of partial input shapes during Group J wiring.
  const activities: ActivityDescriptor[] = sutraWorkflow.step_graph.map((step) => ({
    step_id: step.step_id,
    skill_ref: typeof step.skill_ref === 'string' ? step.skill_ref : null,
    action: typeof step.action === 'string' ? step.action : null,
    inputs: step.inputs,
    outputs: step.outputs,
    on_failure: step.on_failure,
  }))

  // Snapshot the visited order from the source step_graph. The shell `run`
  // returns this trace; the full implementation will replace this with
  // proxyActivities calls inside the Temporal Workflow sandbox.
  const visited_step_ids = sutraWorkflow.step_graph.map((s) => s.step_id)

  const run: TemporalWorkflowDefinition['run'] = async () => ({
    workflow_id,
    visited_step_ids,
    // Explicit shell tag — Group J/K must remove this when the real
    // Temporal-SDK orchestration body lands. The contract test asserts on it.
    __shell: true,
  })

  return {
    workflow_id,
    task_queue,
    activities,
    run,
  }
}
