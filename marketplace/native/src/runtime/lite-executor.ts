/**
 * LiteExecutor — v1.1.0 synchronous Workflow.step_graph runner.
 *
 * Wave 2 lite path: takes a Workflow + Execution context, walks step_graph
 * in order, emits EngineEvents around each step, and produces a final
 * workflow_completed or workflow_failed. NO Temporal dependency at v1.1.0
 * (full Temporal-backed executor is v1.2+).
 *
 * Step actions supported at v1.1.0:
 *   - 'wait'             — no-op, succeed immediately
 *   - 'spawn_sub_unit'   — no-op stub (logs intent, succeeds)
 *   - 'invoke_host_llm'  — no-op stub (logs intent, succeeds)
 *   - 'terminate'        — emit workflow_completed early, success
 *
 * step.on_failure semantics:
 *   - 'continue' → swallow the error, proceed to next step
 *   - 'abort'    → emit workflow_failed immediately
 *   - 'rollback' → mapped to abort at v1.1.0 (no rollback machinery yet)
 *   - 'pause'    → mapped to abort at v1.1.0 (no pause queue yet)
 *   - 'escalate' → mapped to abort at v1.1.0 (no escalation channel yet)
 *
 * The executor is PURE relative to its emit() callback — it does NO I/O
 * itself. Caller (NativeEngine) wires emit() to the RendererRegistry +
 * audit log.
 */

import type { Workflow } from '../primitives/workflow.js'
import type {
  EngineEvent,
  StepCompletedEvent,
  StepStartedEvent,
  WorkflowCompletedEvent,
  WorkflowFailedEvent,
  WorkflowStartedEvent,
} from '../types/engine-event.js'

export interface ExecuteOptions {
  readonly workflow: Workflow
  readonly execution_id: string
  /** Called for every EngineEvent emitted during execution. */
  readonly emit: (event: EngineEvent) => void
  /** Optional clock for deterministic tests. Defaults to Date.now. */
  readonly now?: () => number
}

export interface ExecutionResult {
  readonly status: 'success' | 'failed'
  readonly steps_completed: number
  readonly steps_failed: number
  readonly duration_ms: number
  readonly reason?: string
}

/**
 * Execute a Workflow synchronously, emitting events along the way.
 * Returns when the workflow completes (success or failure).
 *
 * Per softened I-NPD-1: every event is emitted via the caller's emit()
 * callback so the audit chain can be hooked from outside (replay-safe).
 */
export function executeWorkflow(opts: ExecuteOptions): ExecutionResult {
  const now = opts.now ?? Date.now
  const wf = opts.workflow
  const startTs = now()

  const wfStarted: WorkflowStartedEvent = {
    type: 'workflow_started',
    ts_ms: startTs,
    workflow_id: wf.id,
    execution_id: opts.execution_id,
  }
  opts.emit(wfStarted)

  let stepsCompleted = 0
  let stepsFailed = 0
  let failureReason: string | undefined

  const total = wf.step_graph.length

  for (let i = 0; i < total; i++) {
    const step = wf.step_graph[i]!
    const stepIndex = i + 1
    const stepStartTs = now()
    const stepId = step.skill_ref ?? `step-${step.step_id}`

    const stepStarted: StepStartedEvent = {
      type: 'step_started',
      ts_ms: stepStartTs,
      workflow_id: wf.id,
      execution_id: opts.execution_id,
      step_id: stepId,
      step_index: stepIndex,
      step_count: total,
    }
    opts.emit(stepStarted)

    let stepError: Error | null = null
    try {
      runStepAction(step.action ?? 'wait')
    } catch (err) {
      stepError = err instanceof Error ? err : new Error(String(err))
    }

    const stepEndTs = now()
    if (stepError === null) {
      stepsCompleted++
      const stepCompleted: StepCompletedEvent = {
        type: 'step_completed',
        ts_ms: stepEndTs,
        workflow_id: wf.id,
        execution_id: opts.execution_id,
        step_id: stepId,
        step_index: stepIndex,
        step_count: total,
        duration_ms: stepEndTs - stepStartTs,
      }
      opts.emit(stepCompleted)

      if (step.action === 'terminate') {
        // Early-out: terminate action ends the workflow immediately, success.
        break
      }
    } else {
      stepsFailed++
      const onFailure = step.on_failure ?? 'abort'
      if (onFailure === 'continue') {
        // Swallow + proceed; emit step_completed with the failure-as-duration.
        const stepCompleted: StepCompletedEvent = {
          type: 'step_completed',
          ts_ms: stepEndTs,
          workflow_id: wf.id,
          execution_id: opts.execution_id,
          step_id: stepId,
          step_index: stepIndex,
          step_count: total,
          duration_ms: stepEndTs - stepStartTs,
        }
        opts.emit(stepCompleted)
        continue
      }
      // abort / rollback / pause / escalate — all map to terminate-failed at v1.1.0
      failureReason = `step ${stepIndex}/${total} (${stepId}) failed: ${stepError.message} [on_failure=${onFailure}]`
      break
    }
  }

  const endTs = now()
  if (failureReason) {
    const wfFailed: WorkflowFailedEvent = {
      type: 'workflow_failed',
      ts_ms: endTs,
      workflow_id: wf.id,
      execution_id: opts.execution_id,
      reason: failureReason,
    }
    opts.emit(wfFailed)
    return {
      status: 'failed',
      steps_completed: stepsCompleted,
      steps_failed: stepsFailed,
      duration_ms: endTs - startTs,
      reason: failureReason,
    }
  }

  const wfCompleted: WorkflowCompletedEvent = {
    type: 'workflow_completed',
    ts_ms: endTs,
    workflow_id: wf.id,
    execution_id: opts.execution_id,
    duration_ms: endTs - startTs,
  }
  opts.emit(wfCompleted)
  return {
    status: 'success',
    steps_completed: stepsCompleted,
    steps_failed: stepsFailed,
    duration_ms: endTs - startTs,
  }
}

/** v1.1.0 step action dispatch — all actions are no-op stubs. */
function runStepAction(action: string): void {
  switch (action) {
    case 'wait':
    case 'spawn_sub_unit':
    case 'invoke_host_llm':
    case 'terminate':
      return
    default:
      throw new Error(`unknown step action "${action}"`)
  }
}
