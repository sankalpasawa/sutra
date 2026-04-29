/**
 * step-graph-executor — M5 Group K (T-049, T-051).
 *
 * Deterministic dispatcher for the Sutra Workflow.step_graph. Replaces the
 * Group I shell `__shell: true` tag with a real executor that:
 *   - dispatches Activities in step_graph order
 *   - collects per-step results
 *   - routes per-step failures via failure-policy.ts
 *   - resolves terminalCheck violations to
 *     `failure_reason = 'forbidden_coupling:F-N,F-M'` (sorted, comma-joined,
 *     no spaces) when the `terminate` stage runs (T-051)
 *   - supports child Workflow invocation per V2.3 §A11 (action='spawn_sub_unit')
 *
 * Replay-determinism rules (final-architecture.md §5):
 *   - All I/O happens in Activities (the dispatcher is pure orchestration).
 *   - The executor calls `dispatch(descriptor, ctx)` — the caller-supplied
 *     dispatcher is the I/O boundary; the executor itself is `Date.now()`-free
 *     and `Math.random()`-free.
 *   - Iteration of step_graph is order-preserving (Array.iteration).
 *   - Same input + same dispatcher ⇒ bit-identical output.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group K T-049 + T-051
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 *  - .enforcement/codex-reviews/2026-04-29-m5-plan-pre-dispatch.md P2.5 + P1.3
 */

import type { Workflow } from '../primitives/workflow.js'
import type { ForbiddenCouplingId } from '../laws/l4-terminal-check.js'
import type { ActivityDescriptor } from './temporal-adapter.js'
import {
  applyFailurePolicy,
  type ExecutionContext,
  type FailurePolicyOutcome,
} from './failure-policy.js'

// =============================================================================
// Types
// =============================================================================

/**
 * Per-step dispatch outcome handed back to the executor by an
 * `ActivityDispatcher`. Discriminated:
 *   - 'ok'           → impl ran, captured outputs
 *   - 'failure'      → impl threw / rejected; executor routes via failure_policy
 *   - 'child_result' → action='spawn_sub_unit' returned a child Execution-like
 *                      summary; outputs propagate per V2.3 §A11.
 */
export type StepDispatchResult =
  | { kind: 'ok'; outputs: ReadonlyArray<unknown> }
  | { kind: 'failure'; error: Error }
  | { kind: 'child_result'; child_workflow_id: string; outputs: ReadonlyArray<unknown> }

/**
 * Caller-supplied dispatcher. The executor invokes this for every step in
 * order. The dispatcher is the I/O boundary — Activity calls happen here.
 *
 * The executor passes the activity descriptor + a small dispatch context
 * (visited steps so far, autonomy_level). The dispatcher MUST be a pure-ish
 * function from (descriptor, ctx) to a `StepDispatchResult` — it can do I/O,
 * but for replay determinism the same (descriptor, ctx) MUST yield the same
 * result on retry. (Real Temporal Activities provide this guarantee via the
 * Worker; tests pass deterministic mock dispatchers.)
 */
export type ActivityDispatcher = (
  descriptor: ActivityDescriptor,
  ctx: DispatchContext,
) => Promise<StepDispatchResult> | StepDispatchResult

/** Context passed to each `dispatch(...)` call. */
export interface DispatchContext {
  /** Step ids already completed in this run. Order = execution order. */
  completed_step_ids: ReadonlyArray<number>
  /** Workflow autonomy level — for dispatcher to gate human-loop interruptions. */
  autonomy_level: 'manual' | 'semi' | 'autonomous'
}

/**
 * Optional terminalCheck input passed to `executeStepGraph`. When present and
 * the executor reaches a `terminate` action (or the natural end of the
 * step_graph), the executor evaluates `() => violations` lazily and, if the
 * list is non-empty, sets `failure_reason = 'forbidden_coupling:F-N,F-M'`.
 *
 * Lazy callable so the executor doesn't pay the terminal-check cost when no
 * terminate stage runs.
 */
export type TerminalCheckProbe = () => ForbiddenCouplingId[]

export interface ExecuteOptions {
  /**
   * Optional terminalCheck probe. If supplied, called at the terminate stage;
   * any violations populate `failure_reason`. T-051: violations sorted ASCII
   * + comma-joined with the prefix `forbidden_coupling:`.
   */
  terminalCheckProbe?: TerminalCheckProbe
  /** Optional escalation target ref forwarded to failure-policy. */
  escalation_target?: string
}

/**
 * Final state of a Workflow execution.
 */
export interface ExecutionResult {
  workflow_id: string
  /** Step ids visited, in execution order (incl. failures up to abort point). */
  visited_step_ids: number[]
  /** Per-step outputs — one entry per visited step (skipped steps omitted). */
  step_outputs: Array<{
    step_id: number
    outputs: ReadonlyArray<unknown>
    /** True iff `continue` policy skipped output validation for this step. */
    output_validation_skipped: boolean
  }>
  /**
   * Terminal Workflow state. 'success' iff every step succeeded AND
   * (no terminate stage OR terminalCheck cleared).
   */
  state: 'success' | 'failed' | 'paused' | 'escalated'
  /**
   * V2.4 §A12: non-null iff state='failed' OR a continue policy advanced past
   * a step failure (then `partial=true` flips with state remaining 'success').
   * For terminalCheck violations: 'forbidden_coupling:F-N,F-M' (sorted, comma-joined).
   * For step failure: a step:N:{action}:{message} reason from failure-policy.
   * For pause/escalate: routing reason from failure-policy.
   */
  failure_reason: string | null
  /**
   * True iff at least one step's `on_failure='continue'` fired during the run.
   * Workflow does NOT abort; execution proceeds past the failed step. Codex P1.3.
   */
  partial: boolean
  /** Optional resume token if a step's failure_policy was 'pause'. */
  resume_token?: string
  /** When 'escalated' state, the BoundaryEndpoint ref the workflow was handed to. */
  escalation_target?: string
  /** Compensations executed when a step's failure_policy was 'rollback'. */
  rollback_compensations?: number[]
  /** Child workflow invocations triggered via action='spawn_sub_unit'. */
  child_workflows?: Array<{ step_id: number; child_workflow_id: string }>
}

// =============================================================================
// Helpers
// =============================================================================

/**
 * Format terminalCheck violations into the `failure_reason` string
 * per T-051: `forbidden_coupling:F-N,F-M` — sorted ASCII, comma-joined,
 * no spaces. Empty input ⇒ null.
 */
export function formatTerminalCheckFailureReason(
  violations: ReadonlyArray<ForbiddenCouplingId>,
): string | null {
  if (!Array.isArray(violations) || violations.length === 0) return null
  // ASCII sort — `F-10` sorts AFTER `F-1` AFTER `F-12` (ASCII), so we use a
  // stable string sort. The contract is "sorted ASCII"; downstream tooling
  // matches against this string, so we MUST be deterministic.
  const sorted = [...violations].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
  return `forbidden_coupling:${sorted.join(',')}`
}

// =============================================================================
// Executor
// =============================================================================

/**
 * Run the Workflow.step_graph end-to-end through the supplied dispatcher.
 *
 * Pure-orchestration function: no clock, no random, no network. Calls
 * `dispatch(descriptor, ctx)` once per step in order; routes per-step
 * failures via `applyFailurePolicy(...)`; at the natural end of the
 * step_graph (or when a `terminate` action is reached) calls the
 * optional `terminalCheckProbe` and folds violations into `failure_reason`.
 *
 * Replay-determinism: same Workflow + same dispatcher (deterministic) +
 * same options ⇒ deep-equal `ExecutionResult` on every call.
 *
 * @param workflow   Sutra Workflow primitive (constructor-validated).
 * @param dispatch   Caller-supplied I/O boundary; one call per step.
 * @param options    Optional terminalCheck probe + escalation target.
 * @returns          ExecutionResult — terminal state + per-step outputs +
 *                   failure_reason + partial flag.
 */
export async function executeStepGraph(
  workflow: Workflow,
  dispatch: ActivityDispatcher,
  options: ExecuteOptions = {},
): Promise<ExecutionResult> {
  if (typeof workflow !== 'object' || workflow === null) {
    throw new TypeError('executeStepGraph: workflow must be a Workflow')
  }
  if (typeof dispatch !== 'function') {
    throw new TypeError('executeStepGraph: dispatch must be a function')
  }
  if (!Array.isArray(workflow.step_graph) || workflow.step_graph.length === 0) {
    throw new Error('executeStepGraph: Workflow.step_graph must be a non-empty array')
  }

  const visited_step_ids: number[] = []
  const step_outputs: ExecutionResult['step_outputs'] = []
  const child_workflows: NonNullable<ExecutionResult['child_workflows']> = []
  let partial = false
  let reachedTerminate = false

  const completedView = (): ReadonlyArray<number> => visited_step_ids

  for (const step of workflow.step_graph) {
    // Per-step dispatch context — derived snapshot, not a live reference.
    const dispatchCtx: DispatchContext = {
      completed_step_ids: [...completedView()],
      autonomy_level: workflow.autonomy_level,
    }

    // Build the descriptor identical to TemporalAdapter's mapping. Inline here
    // (not via registerWorkflow) to keep the executor independent of the
    // adapter's lifecycle; the shapes are coupled via TS types.
    const descriptor: ActivityDescriptor = {
      step_id: step.step_id,
      skill_ref: typeof step.skill_ref === 'string' ? step.skill_ref : null,
      action: typeof step.action === 'string' ? step.action : null,
      inputs: step.inputs,
      outputs: step.outputs,
      on_failure: step.on_failure,
    }

    // Special-case: action='terminate' is the V2.3 §A11 terminate stage. We
    // mark the flag and break — no dispatcher call (terminate is structural,
    // not an I/O step). T-051: terminalCheck runs after this loop.
    if (descriptor.action === 'terminate') {
      reachedTerminate = true
      visited_step_ids.push(step.step_id)
      break
    }

    let result: StepDispatchResult
    try {
      result = await Promise.resolve(dispatch(descriptor, dispatchCtx))
    } catch (raw) {
      const err = raw instanceof Error ? raw : new Error(String(raw))
      result = { kind: 'failure', error: err }
    }

    if (result.kind === 'ok') {
      visited_step_ids.push(step.step_id)
      step_outputs.push({
        step_id: step.step_id,
        outputs: result.outputs,
        output_validation_skipped: false,
      })
      continue
    }

    if (result.kind === 'child_result') {
      // V2.3 §A11 — action='spawn_sub_unit' delegates to a child Workflow.
      // Outputs from the child propagate as this step's outputs.
      visited_step_ids.push(step.step_id)
      step_outputs.push({
        step_id: step.step_id,
        outputs: result.outputs,
        output_validation_skipped: false,
      })
      child_workflows.push({
        step_id: step.step_id,
        child_workflow_id: result.child_workflow_id,
      })
      continue
    }

    // Failure — route via failure_policy.
    const policyCtx: ExecutionContext = {
      completed_step_ids: [...completedView()],
      autonomy_level: workflow.autonomy_level,
      escalation_target: options.escalation_target,
    }
    const outcome: FailurePolicyOutcome = applyFailurePolicy(step, result.error, policyCtx)

    switch (outcome.action) {
      case 'continue': {
        // Codex P1.3 — log + advance to step[i+1]; partial=true; skip output validation.
        partial = true
        visited_step_ids.push(step.step_id)
        step_outputs.push({
          step_id: step.step_id,
          outputs: [],
          output_validation_skipped: true,
        })
        // continue loop (advance to step[i+1])
        continue
      }
      case 'abort': {
        visited_step_ids.push(step.step_id)
        return {
          workflow_id: workflow.id,
          visited_step_ids,
          step_outputs,
          state: 'failed',
          failure_reason: outcome.reason,
          partial,
          ...(child_workflows.length > 0 ? { child_workflows } : {}),
        }
      }
      case 'rollback': {
        visited_step_ids.push(step.step_id)
        return {
          workflow_id: workflow.id,
          visited_step_ids,
          step_outputs,
          state: 'failed',
          failure_reason: outcome.reason,
          partial,
          rollback_compensations: outcome.compensation_order,
          ...(child_workflows.length > 0 ? { child_workflows } : {}),
        }
      }
      case 'pause': {
        visited_step_ids.push(step.step_id)
        return {
          workflow_id: workflow.id,
          visited_step_ids,
          step_outputs,
          state: 'paused',
          failure_reason: outcome.reason,
          partial,
          resume_token: outcome.resume_token,
          ...(child_workflows.length > 0 ? { child_workflows } : {}),
        }
      }
      case 'escalate': {
        visited_step_ids.push(step.step_id)
        return {
          workflow_id: workflow.id,
          visited_step_ids,
          step_outputs,
          state: 'escalated',
          failure_reason: outcome.reason,
          partial,
          escalation_target: outcome.escalation_target,
          ...(child_workflows.length > 0 ? { child_workflows } : {}),
        }
      }
    }
  }

  // T-051 — terminate stage (or natural end-of-graph): run terminalCheck probe.
  // The probe is optional; absent ⇒ no failure_reason from F-1..F-12, but step
  // failures (handled above) still set failure_reason via failure-policy.
  if (options.terminalCheckProbe) {
    const violations = options.terminalCheckProbe()
    const reason = formatTerminalCheckFailureReason(violations)
    if (reason !== null) {
      return {
        workflow_id: workflow.id,
        visited_step_ids,
        step_outputs,
        state: 'failed',
        failure_reason: reason,
        partial,
        ...(child_workflows.length > 0 ? { child_workflows } : {}),
      }
    }
  }

  // success path — no abort, no rollback, no escalate, no pause, no
  // terminalCheck violation. partial may still be true if any step's
  // on_failure='continue' fired.
  return {
    workflow_id: workflow.id,
    visited_step_ids,
    step_outputs,
    state: 'success',
    failure_reason: null,
    partial,
    ...(child_workflows.length > 0 ? { child_workflows } : {}),
    // intentionally drop `reachedTerminate` from the surface — it's an internal
    // signal that the loop hit a terminate action. Tests can infer from
    // visited_step_ids if needed.
    ...(reachedTerminate ? {} : {}),
  }
}
