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
  ApprovalRequestedEvent,
  StepPausedEvent,
  WorkflowEscalatedEvent,
  WorkflowRollbackStartedEvent,
  WorkflowRollbackCompleteEvent,
  WorkflowRollbackPartialEvent,
  StepCompensatedEvent,
  StepCompensationFailedEvent,
} from '../types/engine-event.js'
import {
  hostLLMActivity,
  HostUnavailableError,
  type HostLLMResult,
} from '../engine/host-llm-activity.js'
import { buildExecutionDecisionProvenance } from './execution-provenance.js'
import { appendDecisionProvenanceLog } from './emergence-provenance.js'
import type { UserKitOptions } from '../persistence/user-kit.js'
import type {
  PolicyDecisionEvent,
  PreconditionCheckEvent,
  PostconditionCheckEvent,
} from '../types/engine-event.js'
import type { ExecutionApprovalRecord } from '../persistence/execution-approval-ledger.js'
import type { ExecutionPauseRecord } from '../persistence/execution-pause-ledger.js'
import type { ExecutionEscalationRecord } from '../persistence/execution-escalation-ledger.js'
import {
  parsePNC,
  evaluatePNC,
  type PredicateRegistry,
} from './pnc-predicate.js'

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
  /**
   * v1.3.0 Wave 2 (codex W2 BLOCKER 3 fold). Optional callback invoked once
   * when the executor pauses at a `step.requires_approval=true` step. The
   * NativeEngine wires this to `persistApproval(record)` so the durable
   * ExecutionApprovalRecord{status:'pending'} survives daemon restart.
   *
   * Default = no-op (preserves "PURE relative to emit()" contract — direct
   * `executeWorkflow` callers without an injected persist callback get the
   * paused ExecutionResult but no on-disk ledger entry. The NativeEngine
   * routed path always supplies this so the founder-facing surface is
   * always durable.)
   */
  readonly approval_persist?: (rec: ExecutionApprovalRecord) => void
  /**
   * v1.3.0 Wave 4 (codex W4 fold). Optional callback invoked once when the
   * executor pauses at a `step.on_failure='pause'` step that FAILED. The
   * NativeEngine wires this to `persistPause(record)` so the durable
   * ExecutionPauseRecord{status:'pending'} survives daemon restart.
   *
   * Default = no-op (preserves "PURE relative to emit()" contract — direct
   * `executeWorkflow` callers without an injected persist callback get the
   * paused ExecutionResult but no on-disk ledger entry).
   */
  readonly pause_persist?: (rec: ExecutionPauseRecord) => void
  /**
   * v1.3.0 Wave 4 (codex W4 fold). Optional callback invoked once when the
   * executor escalates at a `step.on_failure='escalate'` step that FAILED.
   * The NativeEngine wires this to `persistEscalation(record)` so the
   * durable ExecutionEscalationRecord audit trail survives daemon restart.
   */
  readonly escalation_persist?: (rec: ExecutionEscalationRecord) => void
  /**
   * v1.3.0 Wave 2. When set, the executor skips steps whose 1-based
   * step_index is `<= resume_from_step_index` and emits no events for them.
   * Used by NativeEngine.resumeApproved after `approve E-<id>` flips the
   * ledger entry: the original paused step's index is the value here, so
   * the executor resumes at the NEXT step.
   *
   * Required > 0 when set; 0 / undefined ⇒ start from step 1 (normal run).
   * Out-of-range values (e.g., > step_graph.length) cause the run to
   * complete immediately as success with steps_completed=0 — the caller
   * should validate before invoking.
   */
  readonly resume_from_step_index?: number
  /**
   * v1.3.0 Wave 5 (codex W5 BLOCKER 1+2 fold). Optional registry of atom
   * evaluators consulted when parsing wf.preconditions / wf.postconditions
   * as a JSON-shaped PNCPredicate. When the registry is undefined OR the
   * pre/postcondition string is not parseable JSON-Predicate, the gate is
   * SKIPPED (legacy back-compat for free-form preconditions like
   * "is_morning_window AND no_pulse_today" already in the starter kit).
   *
   * When the registry is supplied AND the string IS a parseable PNCPredicate:
   *   - precondition fail ⇒ workflow_failed reason='precondition_failed:<expr>'
   *     emitted instead of workflow_started; NO step events.
   *   - postcondition fail ⇒ workflow_failed reason='postcondition_failed:<expr>'
   *     emitted instead of workflow_completed.
   *
   * NativeEngine wires this for routed runs; direct cmdRun / raw
   * executeWorkflow callers leave it undefined → no PNC gate (preserves
   * v1.2.x admission behavior).
   */
  readonly pnc_registry?: PredicateRegistry
  /**
   * v1.3.0 Wave 5. Frozen evaluation context passed to PNC atom evaluators.
   * Defaults to an empty frozen object. Window markers (e.g.
   * { time_of_day: 'morning', iso_week: '2026-W18' }) belong here, not in
   * the atom evaluator function bodies (codex W5 advisory E: predicate
   * determinism — atoms must not call Date.now/random/I/O; they read
   * pre-computed markers from this snapshot).
   */
  readonly pnc_ctx?: Readonly<Record<string, unknown>>
}

export interface ExecutionResult {
  /**
   * v1.3.0 Wave 2 (codex W2 BLOCKER 1 fold). 'paused' is canonical state per
   * the extended ExecutionState union; lite-executor returns it (with
   * steps_completed = step_index BEFORE the paused step) when a step has
   * requires_approval=true and the executor pauses.
   */
  readonly status: 'success' | 'failed' | 'paused'
  readonly steps_completed: number
  readonly steps_failed: number
  readonly duration_ms: number
  readonly reason?: string
  /**
   * v1.3.0 Wave 2. When status='paused', the 1-based step_index of the
   * step the executor paused at (the requires_approval=true step that has
   * NOT YET run). Undefined for non-paused results.
   */
  readonly paused_step_index?: number
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
  const pncCtx: Readonly<Record<string, unknown>> = opts.pnc_ctx ?? Object.freeze({})

  // v1.3.0 W5 (codex W5 BLOCKER 1 fold) — precondition admission gate.
  //
  // Per codex: a failed precondition is "workflow not admitted", NOT "started
  // then failed". The semantic distinction matters for replay/audit (rejected
  // runs never enter the workflow lifecycle) and for the founder UI (no
  // confusing [workflow_started]+[workflow_failed] pair on a rejected gate).
  //
  // Gate skip rules (legacy back-compat):
  //   - opts.pnc_registry undefined ⇒ skip (NativeEngine routed-only feature).
  //   - wf.preconditions parses to JSON-Predicate ⇒ EVALUATE.
  //   - wf.preconditions is empty / free-form / not JSON ⇒ skip silently
  //     (existing starter-kit "is_morning_window AND no_pulse_today" strings
  //     stay valid; admission proceeds without precondition_check emission).
  //
  // When EVALUATED:
  //   - verdict='pass' ⇒ emit precondition_check{verdict:'pass'} THEN
  //     workflow_started, then proceed normally.
  //   - verdict='fail' ⇒ emit precondition_check{verdict:'fail'} THEN
  //     workflow_failed reason='precondition_failed:<expr>'. NO step events.
  //     NO workflow_started. Return ExecutionResult{status:'failed'}.
  if (opts.pnc_registry) {
    const parseResult = parsePNC(wf.preconditions)
    if (parseResult.ok && parseResult.predicate) {
      const evalResult = evaluatePNC(parseResult.predicate, pncCtx, opts.pnc_registry)
      const checkEvt: PreconditionCheckEvent = {
        type: 'precondition_check',
        ts_ms: startTs,
        workflow_id: wf.id,
        verdict: evalResult.verdict ? 'pass' : 'fail',
        expression: wf.preconditions,
        ...(evalResult.reason !== undefined ? { reason: evalResult.reason } : {}),
      }
      opts.emit(checkEvt)
      if (!evalResult.verdict) {
        const failureReason = `precondition_failed:${evalResult.reason ?? 'verdict_false'}`
        const wfFailed: WorkflowFailedEvent = {
          type: 'workflow_failed',
          ts_ms: startTs,
          workflow_id: wf.id,
          execution_id: opts.execution_id,
          reason: failureReason,
        }
        opts.emit(wfFailed)
        // DP-record the rejection so audit captures admission failures the
        // same way as runtime failures.
        if (opts.user_kit_options_for_dp) {
          try {
            appendDecisionProvenanceLog(
              buildExecutionDecisionProvenance({
                workflow_id: wf.id,
                execution_id: opts.execution_id,
                stage: 'FAILED',
                ts_ms: startTs,
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
          steps_completed: 0,
          steps_failed: 0,
          duration_ms: 0,
          reason: failureReason,
        }
      }
    }
  }

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
  let pausedAtStepIndex: number | undefined
  // v1.3.0 W4: track ordered list of completed-step indices (1-based) for
  // rollback reverse-walk. We append on success; rollback iterates this in
  // reverse to find candidates with compensate_action.
  const completedStepIndices: number[] = []
  // v1.3.0 W4: result-status override when on_failure handler short-circuits
  // the loop. 'paused' for on_failure='pause', 'failed' otherwise. Default
  // 'failed' if failureReason set without explicit override.
  let resultStatusOverride: 'success' | 'failed' | 'paused' | undefined
  let pausedFromFailureAtStepIndex: number | undefined

  const total = wf.step_graph.length
  // v1.3.0 W2: resume_from_step_index = N means skip steps with stepIndex <= N
  // (the originally-paused step is N+1's predecessor; resumeApproved passes
  // the paused step's index so the next iteration starts at N+1).
  const resumeFrom = opts.resume_from_step_index ?? 0

  for (let i = 0; i < total; i++) {
    const step = wf.step_graph[i]!
    const stepIndex = i + 1

    // v1.3.0 W2 resume path — skip steps already completed in the original
    // run. No events emitted for skipped steps (they were already audited
    // pre-pause; replaying would corrupt the transcript).
    if (stepIndex <= resumeFrom) {
      continue
    }

    // v1.3.0 W2 (codex W2 BLOCKER 3 fold) — step-level approval gate.
    // BEFORE running step action, check requires_approval. When true:
    //   1. Build prompt_summary (action, host if any, locator first ~200 chars).
    //   2. Build ExecutionApprovalRecord{status:'pending'}.
    //   3. Call opts.approval_persist?.(record) — NativeEngine wires this to
    //      the runtime/pending-approvals ledger via atomic-write.
    //   4. Emit approval_requested event.
    //   5. Return ExecutionResult{status:'paused'} early.
    // The pause point is BEFORE step_started so the founder transcript shows
    // [approval_requested] not [step_started] for the gated step (avoids
    // confusing "started but never completed" lines in the audit log).
    //
    // Resume bypass: the gate fires only when stepIndex > resumeFrom. On
    // resume, executeWorkflowResume passes resume_from_step_index = N-1
    // (skip steps 1..N-1, RUN step N) — but step N still has
    // requires_approval=true. The caller (NativeEngine.resumeApproved) sets
    // resume_from_step_index = paused_step_index (i.e., skip past the paused
    // step too) ONLY if the founder's approval is interpreted as "approve and
    // skip"; otherwise we want the gated step to RUN after approval. The
    // canonical interpretation per founder centerpiece directive: approval
    // means "yes, run this step". So we set resume_from_step_index = N-1
    // (the gated step's predecessor) AND the executor must NOT re-pause on
    // step N. Bypass: when stepIndex === resumeFrom + 1 (the FIRST executed
    // step on resume), skip the requires_approval gate. This matches the
    // semantics: the gate already fired pre-resume; firing again is a bug.
    const isResumeFirstStep = resumeFrom > 0 && stepIndex === resumeFrom + 1
    if (step.requires_approval === true && !isResumeFirstStep) {
      const promptSummary = buildPromptSummary(step)
      const record: ExecutionApprovalRecord = {
        execution_id: opts.execution_id,
        workflow_id: wf.id,
        step_index: stepIndex,
        prompt_summary: promptSummary,
        status: 'pending',
        created_at_ms: now(),
      }
      try {
        opts.approval_persist?.(record)
      } catch (err) {
        // Persist failure is fatal — without a durable ledger entry, the
        // founder's `approve E-<id>` would have nothing to load. Convert to
        // workflow_failed rather than silently dropping the gate.
        failureReason = `approval_persist_failed:${err instanceof Error ? err.message : String(err)}`
        break
      }
      const approvalEvt: ApprovalRequestedEvent = {
        type: 'approval_requested',
        ts_ms: now(),
        execution_id: opts.execution_id,
        workflow_id: wf.id,
        step_index: stepIndex,
        prompt_summary: promptSummary,
      }
      opts.emit(approvalEvt)
      pausedAtStepIndex = stepIndex
      break
    }

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
      completedStepIndices.push(stepIndex)
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
      const baseReason = `step ${stepIndex}/${total} (${stepId}) failed: ${stepError.message}`
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
      if (onFailure === 'abort') {
        failureReason = `${baseReason} [on_failure=abort]`
        break
      }
      if (onFailure === 'pause') {
        // v1.3.0 W4 — on_failure='pause' machinery. Persist a durable
        // ExecutionPauseRecord{status:'pending'} via opts.pause_persist
        // (NativeEngine wires this), emit step_paused, and short-circuit
        // with status='paused'. Resume continues from step_index+1.
        const pauseRec: ExecutionPauseRecord = {
          execution_id: opts.execution_id,
          workflow_id: wf.id,
          step_index: stepIndex,
          status: 'pending',
          reason: stepError.message,
          created_at_ms: now(),
        }
        try {
          opts.pause_persist?.(pauseRec)
        } catch (err) {
          // Persist failure converts to workflow_failed (no silent drop).
          failureReason = `pause_persist_failed:${err instanceof Error ? err.message : String(err)} [orig=${baseReason}]`
          break
        }
        const pausedEvt: StepPausedEvent = {
          type: 'step_paused',
          ts_ms: now(),
          execution_id: opts.execution_id,
          workflow_id: wf.id,
          step_index: stepIndex,
          reason: stepError.message,
        }
        opts.emit(pausedEvt)
        resultStatusOverride = 'paused'
        pausedFromFailureAtStepIndex = stepIndex
        break
      }
      if (onFailure === 'escalate') {
        // v1.3.0 W4 — on_failure='escalate' machinery. Persist a durable
        // ExecutionEscalationRecord via opts.escalation_persist (NativeEngine
        // wires this), emit workflow_escalated, and return failed with
        // reason='escalated:<orig>'.
        const escRec: ExecutionEscalationRecord = {
          execution_id: opts.execution_id,
          workflow_id: wf.id,
          step_index: stepIndex,
          reason: stepError.message,
          created_at_ms: now(),
        }
        try {
          opts.escalation_persist?.(escRec)
        } catch (err) {
          failureReason = `escalation_persist_failed:${err instanceof Error ? err.message : String(err)} [orig=${baseReason}]`
          break
        }
        const escEvt: WorkflowEscalatedEvent = {
          type: 'workflow_escalated',
          ts_ms: now(),
          execution_id: opts.execution_id,
          workflow_id: wf.id,
          reason: stepError.message,
        }
        opts.emit(escEvt)
        failureReason = `escalated:${baseReason}`
        resultStatusOverride = 'failed'
        break
      }
      if (onFailure === 'rollback') {
        // v1.3.0 W4 — on_failure='rollback' machinery (codex W4 advisory #1
        // step-local + #2 best-effort). Emit workflow_rollback_started, then
        // reverse-walk completedStepIndices i-1..0; for each step with
        // compensate_action defined, dispatch via runStepAction-equivalent.
        // Track success/fail counts. After walk: emit
        // workflow_rollback_complete (all attempted compensations succeeded
        // OR there were none) | workflow_rollback_partial (mixed).
        const rollbackStartedEvt: WorkflowRollbackStartedEvent = {
          type: 'workflow_rollback_started',
          ts_ms: now(),
          execution_id: opts.execution_id,
          workflow_id: wf.id,
          reason: stepError.message,
        }
        opts.emit(rollbackStartedEvt)
        const rollbackOutcome = await runRollbackReverseWalk(
          wf,
          opts.execution_id,
          completedStepIndices,
          { dispatch, runSeq, onHostLLMResult, now, emit: opts.emit },
        )
        if (rollbackOutcome.failed === 0) {
          const completeEvt: WorkflowRollbackCompleteEvent = {
            type: 'workflow_rollback_complete',
            ts_ms: now(),
            execution_id: opts.execution_id,
            workflow_id: wf.id,
            steps_compensated: rollbackOutcome.compensated,
          }
          opts.emit(completeEvt)
          failureReason = `rollback_complete:${baseReason} [compensated=${rollbackOutcome.compensated}]`
        } else {
          const partialEvt: WorkflowRollbackPartialEvent = {
            type: 'workflow_rollback_partial',
            ts_ms: now(),
            execution_id: opts.execution_id,
            workflow_id: wf.id,
            steps_compensated: rollbackOutcome.compensated,
            steps_failed: rollbackOutcome.failed,
          }
          opts.emit(partialEvt)
          failureReason = `rollback_partial:${rollbackOutcome.compensated}/${rollbackOutcome.compensated + rollbackOutcome.failed}:${baseReason}`
        }
        resultStatusOverride = 'failed'
        break
      }
      // Defensive: unknown on_failure value (validator should catch first).
      failureReason = `${baseReason} [on_failure=${onFailure}]`
      break
    }
  }

  const endTs = now()

  // v1.3.0 W2: paused short-circuit — pausedAtStepIndex set means the
  // executor hit a requires_approval=true step and broke out of the loop
  // BEFORE running it. Don't emit workflow_completed or workflow_failed;
  // the workflow is suspended awaiting founder approval. Caller (NativeEngine)
  // detects status='paused' and persists the ledger entry via the
  // approval_persist callback already invoked above.
  if (pausedAtStepIndex !== undefined) {
    return {
      status: 'paused',
      steps_completed: stepsCompleted,
      steps_failed: stepsFailed,
      duration_ms: endTs - startTs,
      paused_step_index: pausedAtStepIndex,
    }
  }

  // v1.3.0 W4: paused-from-failure short-circuit — on_failure='pause' handler
  // persisted an ExecutionPauseRecord and emitted step_paused. Don't emit
  // workflow_completed or workflow_failed; the workflow is suspended awaiting
  // founder resume via NativeEngine.resumeFromPause.
  if (resultStatusOverride === 'paused' && pausedFromFailureAtStepIndex !== undefined) {
    return {
      status: 'paused',
      steps_completed: stepsCompleted,
      steps_failed: stepsFailed,
      duration_ms: endTs - startTs,
      paused_step_index: pausedFromFailureAtStepIndex,
    }
  }

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

  // v1.3.0 W5 — postcondition gate. After all steps succeed and BEFORE
  // emitting workflow_completed, evaluate wf.postconditions when a registry
  // is supplied AND the postconditions string parses as JSON-Predicate.
  // verdict='fail' converts the run to workflow_failed reason=
  // 'postcondition_failed:<expr>' INSTEAD of workflow_completed. verdict=
  // 'pass' emits postcondition_check{verdict:'pass'} then proceeds to the
  // normal workflow_completed emission.
  if (opts.pnc_registry) {
    const parseResult = parsePNC(wf.postconditions)
    if (parseResult.ok && parseResult.predicate) {
      const evalResult = evaluatePNC(parseResult.predicate, pncCtx, opts.pnc_registry)
      const checkEvt: PostconditionCheckEvent = {
        type: 'postcondition_check',
        ts_ms: endTs,
        workflow_id: wf.id,
        verdict: evalResult.verdict ? 'pass' : 'fail',
        expression: wf.postconditions,
        ...(evalResult.reason !== undefined ? { reason: evalResult.reason } : {}),
      }
      opts.emit(checkEvt)
      if (!evalResult.verdict) {
        const failureReason = `postcondition_failed:${evalResult.reason ?? 'verdict_false'}`
        const wfFailed: WorkflowFailedEvent = {
          type: 'workflow_failed',
          ts_ms: endTs,
          workflow_id: wf.id,
          execution_id: opts.execution_id,
          reason: failureReason,
        }
        opts.emit(wfFailed)
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
      // v1.3.0 W1.9 (codex W1.9 advisory fold): forward step.timeout_ms only
      // when defined. Undefined leaves host-llm-activity's default (60_000ms)
      // in effect; the args object's optional timeout_ms is omitted entirely
      // (not set to `undefined`) so a callsite that explicitly sets
      // `timeout_ms: undefined` is indistinguishable from "no timeout
      // override declared".
      try {
        const dispatchArgs: {
          prompt: string
          host: 'claude' | 'codex'
          workflow_run_seq: number
          timeout_ms?: number
        } = {
          prompt,
          host,
          workflow_run_seq: ctx.runSeq,
        }
        if (step.timeout_ms !== undefined) {
          dispatchArgs.timeout_ms = step.timeout_ms
        }
        const result = await ctx.dispatch(dispatchArgs)
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

/**
 * v1.3.0 Wave 2 — build a human-friendly summary of a paused step for the
 * founder UI. Truncates inputs[0].locator at 200 chars; includes action + host
 * when present; falls back to skill_ref/step_id when no action.
 *
 * The summary is what the founder sees in the [approval_requested] line and
 * the persisted ExecutionApprovalRecord.prompt_summary field — keep it
 * compact + informative.
 */
function buildPromptSummary(step: WorkflowStep): string {
  const what = step.skill_ref
    ? `skill=${step.skill_ref}`
    : step.action === 'invoke_host_llm'
      ? `invoke_host_llm host=${step.host ?? '?'}`
      : `action=${step.action ?? '?'}`
  const locator = step.inputs?.[0]?.locator ?? ''
  const truncated = locator.length > 200 ? locator.slice(0, 200) + '…' : locator
  return locator ? `${what} input="${truncated}"` : what
}

/**
 * v1.3.0 Wave 4 — reverse-walk over completed step indices, dispatching
 * `compensate_action` on each step that has one defined. Returns counts of
 * successful + failed compensations.
 *
 * Codex W4 advisory #2 best-effort semantics:
 *   - Steps without compensate_action are skipped silently (counted as neither
 *     compensated nor failed).
 *   - A compensate_action that throws produces step_compensation_failed but
 *     does NOT abort the reverse-walk — we keep going and try every remaining
 *     completed step (best-effort).
 */
async function runRollbackReverseWalk(
  wf: Workflow,
  execution_id: string,
  completedStepIndices: number[],
  ctx: StepDispatchContext & { now: () => number; emit: (e: EngineEvent) => void },
): Promise<{ compensated: number; failed: number }> {
  let compensated = 0
  let failed = 0
  // Reverse iteration: i-1 .. 0 over the completed-step list (which is
  // already in ascending step_index order since we appended on success).
  for (let i = completedStepIndices.length - 1; i >= 0; i--) {
    const stepIndex = completedStepIndices[i]!
    // step_index is 1-based; step_graph is 0-based.
    const step = wf.step_graph[stepIndex - 1]
    if (!step || !step.compensate_action) continue
    const ca = step.compensate_action
    const compStartTs = ctx.now()
    try {
      await runCompensateAction(ca, ctx)
      const compEndTs = ctx.now()
      compensated++
      const okEvt: StepCompensatedEvent = {
        type: 'step_compensated',
        ts_ms: compEndTs,
        execution_id,
        workflow_id: wf.id,
        step_index: stepIndex,
        duration_ms: compEndTs - compStartTs,
      }
      ctx.emit(okEvt)
    } catch (err) {
      failed++
      const reason = err instanceof Error ? err.message : String(err)
      const failEvt: StepCompensationFailedEvent = {
        type: 'step_compensation_failed',
        ts_ms: ctx.now(),
        execution_id,
        workflow_id: wf.id,
        step_index: stepIndex,
        reason,
      }
      ctx.emit(failEvt)
      // Best-effort: continue reverse-walk to attempt remaining compensations.
    }
  }
  return { compensated, failed }
}

/**
 * v1.3.0 Wave 4 — dispatch a step's compensate_action. Mirrors runStepAction
 * for the {wait, invoke_host_llm, spawn_sub_unit} subset (no `terminate`).
 */
async function runCompensateAction(
  ca: NonNullable<WorkflowStep['compensate_action']>,
  ctx: StepDispatchContext,
): Promise<void> {
  switch (ca.action) {
    case 'wait':
    case 'spawn_sub_unit':
      return
    case 'invoke_host_llm': {
      const host = ca.host
      if (host !== 'claude' && host !== 'codex') {
        throw new Error(`compensate_invocation_failed:invalid_host:${String(host)}`)
      }
      const prompt = ca.inputs[0]?.locator
      if (!prompt) {
        throw new Error('compensate_invocation_failed:no_prompt')
      }
      try {
        const dispatchArgs: {
          prompt: string
          host: 'claude' | 'codex'
          workflow_run_seq: number
          timeout_ms?: number
        } = {
          prompt,
          host,
          workflow_run_seq: ctx.runSeq,
        }
        if (ca.timeout_ms !== undefined) {
          dispatchArgs.timeout_ms = ca.timeout_ms
        }
        const result = await ctx.dispatch(dispatchArgs)
        // Compensation results are not currently surfaced via on_host_llm_result
        // (the callback is for the primary forward path). We discard `result`
        // here intentionally — the audit trail lives in step_compensated.
        void result
        return
      } catch (err) {
        if (err instanceof HostUnavailableError) {
          throw new Error(`compensate_host_unavailable:${host}`)
        }
        const msg = err instanceof Error ? err.message : String(err)
        throw new Error(`compensate_invocation_failed:${msg}`)
      }
    }
    default: {
      const exhaustive: never = ca.action
      throw new Error(`compensate_unknown_action:${String(exhaustive)}`)
    }
  }
}

/**
 * v1.3.0 Wave 2 — resume an approved-and-paused workflow run.
 *
 * Convenience wrapper that calls executeWorkflow with resume_from_step_index
 * set. Used by NativeEngine.resumeApproved after the founder's `approve E-<id>`
 * utterance has flipped the ledger entry pending → approved.
 *
 * Semantics: the original pause happened BEFORE the gated step ran. To RUN
 * that step on resume, the caller passes
 * `resume_from_step_index = paused_step_index - 1` (skip steps 1..N-1; run
 * starting at step N). The executor's loop logic skips steps with
 * stepIndex <= resumeFrom, so the gated step (N) is the first to execute.
 *
 * The gated step's `requires_approval=true` flag is BYPASSED on the first
 * step of a resume run via the `isResumeFirstStep` guard in executeWorkflow
 * — otherwise the gate would re-fire and the workflow would loop forever.
 *
 * The original execution_id is preserved so the audit transcript ties back
 * to the original workflow_started event.
 */
export async function executeWorkflowResume(
  opts: ExecuteOptions & { resume_from_step_index: number },
): Promise<ExecutionResult> {
  if (
    typeof opts.resume_from_step_index !== 'number' ||
    !Number.isInteger(opts.resume_from_step_index) ||
    opts.resume_from_step_index < 0
  ) {
    throw new Error(
      `executeWorkflowResume: resume_from_step_index must be a non-negative integer; got "${String(opts.resume_from_step_index)}"`,
    )
  }
  return executeWorkflow(opts)
}
