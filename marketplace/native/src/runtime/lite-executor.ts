/**
 * LiteExecutor — v1.2.1 async Workflow.step_graph runner.
 *
 * Wave 2 lite path: takes a Workflow + Execution context, walks step_graph
 * in order, emits EngineEvents around each step, and produces a final
 * workflow_completed or workflow_failed. NO Temporal dependency at v1.1.0
 * (full Temporal-backed executor is v1.2+).
 *
 * Step actions supported at v1.2.1:
 *   - 'wait'             — no-op, succeed immediately
 *   - 'spawn_sub_unit'   — no-op stub (logs intent, succeeds)
 *   - 'invoke_host_llm'  — DISPATCHES into hostLLMActivity (claude --bare /
 *                          codex exec); see v1.2.1 contract block below.
 *   - 'terminate'        — emit workflow_completed early, success
 *
 * v1.2.1 host-LLM contract (DISPATCH-ONLY):
 *   - LiteExecutor invokes hostLLMActivity and forwards the HostLLMResult
 *     via the on_host_llm_result callback (default: no-op, preserving the
 *     "PURE relative to emit()" contract below).
 *   - LiteExecutor does NOT wrap the response in a DataRef envelope and
 *     does NOT validate against step.return_contract. Workflows that need
 *     DataRef wrapping or schema validation must use the full
 *     step-graph-executor (engine/step-graph-executor.ts).
 *   - This DISPATCH-ONLY scope closes P1.2 of DIRECTIVE 1777839055 (post-
 *     approval workflow no longer hollow); broader contract alignment with
 *     step-graph-executor is deferred to v1.x.
 *
 * step.on_failure semantics:
 *   - 'continue' → swallow the error, proceed to next step
 *   - 'abort'    → emit workflow_failed immediately
 *   - 'rollback' → mapped to abort at v1.1.0 (no rollback machinery yet)
 *   - 'pause'    → mapped to abort at v1.1.0 (no pause queue yet)
 *   - 'escalate' → mapped to abort at v1.1.0 (no escalation channel yet)
 *
 * The executor is PURE relative to its emit() callback — it does NO I/O
 * itself except via the host_llm_dispatch hook (default = real
 * hostLLMActivity; tests inject stubs). Caller (NativeEngine / CLI) wires
 * emit() to the RendererRegistry + audit log.
 */

import type { Workflow } from '../primitives/workflow.js'
import type { WorkflowStep } from '../types/index.js'
import type {
  EngineEvent,
  StepCompletedEvent,
  StepStartedEvent,
  WorkflowCompletedEvent,
  WorkflowFailedEvent,
  WorkflowStartedEvent,
} from '../types/engine-event.js'
import {
  hostLLMActivity,
  HostUnavailableError,
  type HostLLMResult,
} from '../engine/host-llm-activity.js'
import { buildExecutionDecisionProvenance } from './execution-provenance.js'
import { appendDecisionProvenanceLog } from './emergence-provenance.js'
import type { UserKitOptions } from '../persistence/user-kit.js'
import type { PolicyDecisionEvent } from '../types/engine-event.js'

export interface ExecuteOptions {
  readonly workflow: Workflow
  readonly execution_id: string
  /** Called for every EngineEvent emitted during execution. */
  readonly emit: (event: EngineEvent) => void
  /** Optional clock for deterministic tests. Defaults to Date.now. */
  readonly now?: () => number
  /**
   * v1.2.1: dispatcher for action='invoke_host_llm'. Defaults to the real
   * hostLLMActivity. Tests inject a stub returning a canned HostLLMResult.
   */
  readonly host_llm_dispatch?: typeof hostLLMActivity
  /**
   * v1.2.1: callback invoked once per successful invoke_host_llm step with
   * the HostLLMResult and the originating WorkflowStep. Default = no-op
   * (preserves "PURE relative to emit()" contract — caller decides what to
   * do with the response).
   */
  readonly on_host_llm_result?: (result: HostLLMResult, step: WorkflowStep) => void
  /**
   * v1.2.1: forwarded to hostLLMActivity as workflow_run_seq for invocation_id
   * derivation (see host-llm-activity.ts D-NS-26). Defaults to 0.
   */
  readonly workflow_run_seq?: number
  /**
   * v1.2.2 (N2): when set, lite-executor writes a DecisionProvenance record
   * to the user-kit DP log on workflow_started + workflow_completed/failed.
   * When unset, no DP records are written (v1.2.1 behavior preserved for
   * raw cmdRun / direct executeWorkflow callers per codex pre-dispatch fold).
   */
  readonly user_kit_options_for_dp?: UserKitOptions
  /**
   * v1.2.2 (N2): optional charter id linking this execution to a Charter
   * for the DP authority_id field. Defaults to 'native-runtime'.
   */
  readonly charter_id?: string
  /**
   * v1.2.2 (N4 narrowed — routed-engine-only OPA gate): callable that
   * adjudicates step.policy_check=true. When set AND a step has
   * policy_check=true, lite-executor calls this and emits a policy_decision
   * event before proceeding. NativeEngine wires this when routing exact-
   * matches a trigger with a charter_id. Direct cmdRun / raw
   * executeWorkflow callers leave this unset → ungated (codex narrowing).
   */
  readonly policy_dispatch?: (step: WorkflowStep) => { allow: boolean; reason: string }
}

export interface ExecutionResult {
  readonly status: 'success' | 'failed'
  readonly steps_completed: number
  readonly steps_failed: number
  readonly duration_ms: number
  readonly reason?: string
}

/**
 * Execute a Workflow async, emitting events along the way.
 * Returns when the workflow completes (success or failure).
 *
 * v1.2.1: invoke_host_llm steps await hostLLMActivity dispatch.
 *
 * Per softened I-NPD-1: every event is emitted via the caller's emit()
 * callback so the audit chain can be hooked from outside (replay-safe).
 */
export async function executeWorkflow(opts: ExecuteOptions): Promise<ExecutionResult> {
  const now = opts.now ?? Date.now
  const wf = opts.workflow
  const startTs = now()
  const dispatch = opts.host_llm_dispatch ?? hostLLMActivity
  const onHostLLMResult = opts.on_host_llm_result ?? (() => {})
  const runSeq = opts.workflow_run_seq ?? 0

  const wfStarted: WorkflowStartedEvent = {
    type: 'workflow_started',
    ts_ms: startTs,
    workflow_id: wf.id,
    execution_id: opts.execution_id,
  }
  opts.emit(wfStarted)

  // v1.2.2 N2 — write execution DP-record if user-kit configured.
  if (opts.user_kit_options_for_dp) {
    try {
      appendDecisionProvenanceLog(
        buildExecutionDecisionProvenance({
          workflow_id: wf.id,
          execution_id: opts.execution_id,
          stage: 'STARTED',
          ts_ms: startTs,
          outcome: 'execution started',
          charter_id: opts.charter_id,
        }),
        opts.user_kit_options_for_dp,
      )
    } catch {
      /* DP write failure is non-fatal; log silently to avoid cascading executor failure */
    }
  }

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

    // v1.2.2 N4 (narrowed) — when step.policy_check=true AND a policy_dispatch
    // is supplied by the caller (NativeEngine for routed turns), evaluate the
    // gate and emit policy_decision. Direct cmdRun / raw callers leave
    // policy_dispatch unset → step proceeds ungated (documented behavior).
    let stepError: Error | null = null
    if (step.policy_check === true && opts.policy_dispatch) {
      try {
        const verdict = opts.policy_dispatch(step)
        const policyEvt: PolicyDecisionEvent = {
          type: 'policy_decision',
          ts_ms: now(),
          workflow_id: wf.id,
          rule_id: `step-policy:${stepId}`,
          verdict: verdict.allow ? 'ALLOW' : 'DENY',
          reason: verdict.reason,
        }
        opts.emit(policyEvt)
        if (!verdict.allow) {
          stepError = new Error(`policy_denied:${verdict.reason}`)
        }
      } catch (err) {
        stepError = err instanceof Error ? err : new Error(String(err))
      }
    }
    if (stepError === null) {
      try {
        await runStepAction(step, { dispatch, runSeq, onHostLLMResult })
      } catch (err) {
        stepError = err instanceof Error ? err : new Error(String(err))
      }
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
    // v1.2.2 N2 — DP-record at failure
    if (opts.user_kit_options_for_dp) {
      try {
        appendDecisionProvenanceLog(
          buildExecutionDecisionProvenance({
            workflow_id: wf.id,
            execution_id: opts.execution_id,
            stage: 'FAILED',
            ts_ms: endTs,
            outcome: failureReason,
            failure_reason: failureReason,
            charter_id: opts.charter_id,
          }),
          opts.user_kit_options_for_dp,
        )
      } catch { /* non-fatal */ }
    }
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
  // v1.2.2 N2 — DP-record at success
  if (opts.user_kit_options_for_dp) {
    try {
      appendDecisionProvenanceLog(
        buildExecutionDecisionProvenance({
          workflow_id: wf.id,
          execution_id: opts.execution_id,
          stage: 'COMPLETED',
          ts_ms: endTs,
          outcome: `success: ${stepsCompleted} step(s) completed in ${endTs - startTs}ms`,
          charter_id: opts.charter_id,
        }),
        opts.user_kit_options_for_dp,
      )
    } catch { /* non-fatal */ }
  }
  return {
    status: 'success',
    steps_completed: stepsCompleted,
    steps_failed: stepsFailed,
    duration_ms: endTs - startTs,
  }
}

/** Dispatch context plumbed through executeWorkflow → runStepAction. */
interface StepDispatchContext {
  readonly dispatch: typeof hostLLMActivity
  readonly runSeq: number
  readonly onHostLLMResult: (result: HostLLMResult, step: WorkflowStep) => void
}

/**
 * v1.2.1 step action dispatch.
 *
 * Preserves the v1.1.0 `step.action ?? 'wait'` fallback for steps without
 * an explicit action (e.g. skill_ref-only steps).
 */
async function runStepAction(step: WorkflowStep, ctx: StepDispatchContext): Promise<void> {
  const action = step.action ?? 'wait'
  switch (action) {
    case 'wait':
    case 'spawn_sub_unit':
    case 'terminate':
      return
    case 'invoke_host_llm': {
      const host = step.host
      if (host !== 'claude' && host !== 'codex') {
        throw new Error(`host_llm_invocation_failed:invalid_host:${String(host)}`)
      }
      const prompt = step.inputs[0]?.locator
      if (!prompt) {
        throw new Error('host_llm_invocation_failed:no_prompt')
      }
      try {
        const result = await ctx.dispatch({
          prompt,
          host,
          workflow_run_seq: ctx.runSeq,
        })
        ctx.onHostLLMResult(result, step)
        return
      } catch (err) {
        if (err instanceof HostUnavailableError) {
          throw new Error(`host_llm_unavailable:${host}`)
        }
        const msg = err instanceof Error ? err.message : String(err)
        throw new Error(`host_llm_invocation_failed:${msg}`)
      }
    }
    default:
      throw new Error(`unknown step action "${action}"`)
  }
}
