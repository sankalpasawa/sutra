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
import type { DataRef } from '../types/index.js'
import type { ForbiddenCouplingId } from '../laws/l4-terminal-check.js'
import type { ActivityDescriptor } from './temporal-adapter.js'
import {
  applyFailurePolicy,
  type ExecutionContext,
  type FailurePolicyOutcome,
} from './failure-policy.js'
import type { SkillEngine } from './skill-engine.js'
import { invokeSkill } from './skill-invocation.js'

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
  /**
   * Step ids that produced successful effects in this run. Order = execution
   * order. Failed-continue steps are NOT included — see codex P1.1
   * (2026-04-29 master review). This is the rollback-correct "completed" view.
   */
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
  /**
   * M6 Group P (T-073). When provided, steps with `skill_ref` are dispatched
   * via the child-invocation adapter (`invokeSkill`) instead of the
   * dispatcher. The adapter resolves the Skill, runs an isolated child
   * execution, validates the terminal payload against the cached
   * return_contract, and returns either a validated payload (recorded as the
   * parent step's outputs) or a canonical failure (synthesized as a step
   * failure → routed via M5 failure-policy).
   *
   * If omitted, steps with `skill_ref` continue to flow through the
   * dispatcher unchanged (back-compat with M5 tests + activity-only
   * Workflows that don't use the SkillEngine).
   */
  skill_engine?: SkillEngine
  /**
   * M6 Group P (T-073). Current recursion depth for child Skill invocations.
   * Defaults to 0 at the root invocation. The executor passes this through
   * to `invokeSkill`, which checks it against `SKILL_RECURSION_CAP` before
   * resolution and increments it before re-entering executeStepGraph.
   */
  recursion_depth?: number
}

/**
 * M6 Group P (T-073). One entry per child Skill invocation that succeeded.
 * Surfaced on `ExecutionResult.child_edges` so observability + downstream
 * tooling can reconstruct the parent→child invocation graph WITHOUT having
 * to merge the child's internals into the parent's visited/completed lists
 * (codex P1.3 isolation contract).
 */
export interface ChildEdge {
  /** Parent step that carried `skill_ref`. */
  step_id: number
  /** Resolved Skill ref (== Workflow.id of the registered Skill). */
  skill_ref: string
  /**
   * Deterministic child execution id synthesized by `invokeSkill` from
   * (parent step_id, skill_ref). Replay-stable; no clock dependency.
   */
  child_execution_id: string
  /**
   * The Skill's terminal payload wrapped in a V2 §A11 DataRef envelope after
   * validation against `return_contract`. Codex master review 2026-04-30
   * P1.1 fold: contract drift fix — V2 §A11 says child execution "returns
   * DataRef per `return_contract`", so the parent step's outputs slot carries
   * the DataRef envelope (kind='skill-output', schema_ref=return_contract,
   * locator='inline:<JSON>', version='1', mutability='immutable',
   * retention='session', authoritative_status='authoritative').
   *
   * Same value the executor records into `step_outputs[parent step_id].outputs[0]`.
   */
  validated_dataref: DataRef
}

/**
 * Final state of a Workflow execution.
 */
export interface ExecutionResult {
  workflow_id: string
  /**
   * Step ids visited, in execution order (incl. failed-continue steps + steps
   * up to the abort/rollback/pause/escalate point). Trace-shaped — for
   * observability + debugging. NOT the rollback compensation set; see
   * `completed_step_ids` for that.
   */
  visited_step_ids: number[]
  /**
   * Step ids that produced successful effects, in execution order. Strictly
   * a subset of `visited_step_ids`: a step that failed with `on_failure='continue'`
   * appears in visited but NOT here. Rollback compensation walks reverse this
   * list — never the visited list. Codex P1.1 (2026-04-29 master review).
   */
  completed_step_ids: number[]
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
  /**
   * M6 Group P (T-073). Child Skill invocations triggered via a parent step
   * carrying `skill_ref` while `options.skill_engine` was provided. Empty
   * when no Skill invocations occurred (back-compat with M5 dispatchers).
   * The child's internal step_ids are NOT merged into `visited_step_ids`
   * or `completed_step_ids` (codex P1.3 isolation); only the parent step
   * carrying `skill_ref` appears in those lists.
   */
  child_edges?: ChildEdge[]
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
  // Lexicographic ASCII string-sort (NOT numeric). E.g. ['F-10','F-2','F-1']
  // → 'F-1,F-10,F-2'. Downstream consumers that need numeric ordering must
  // re-sort by parsed integer. The contract pinned by
  // step-graph-executor.test.ts:178-183 is "sorted ASCII"; downstream tooling
  // matches against this string, so we MUST be deterministic. Do NOT "fix"
  // this to numeric sort — that would silently break the contract.
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

  // Two distinct lists per codex P1.1 (2026-04-29 master review):
  //   visited_step_ids   — every step the executor saw, including failed-continue
  //                        steps (trace-shaped; for observability / debugging)
  //   completed_step_ids — only steps that produced successful effects (for
  //                        rollback compensation walks + dispatch context)
  // Aliasing them was the M5 ship-blocker: rollback would compensate steps
  // that failed-continue (never produced effects).
  const visited_step_ids: number[] = []
  const completed_step_ids: number[] = []
  const step_outputs: ExecutionResult['step_outputs'] = []
  const child_workflows: NonNullable<ExecutionResult['child_workflows']> = []
  // M6 Group P (T-073). Child Skill invocations populate this; merged into
  // ExecutionResult.child_edges at every return point below. Codex P1.3
  // isolation: parent's visited/completed never carry child internals; the
  // edge entries here are the only cross-reference between parent + child.
  const child_edges: NonNullable<ExecutionResult['child_edges']> = []
  let partial = false

  // M6 Group P (T-073). Carry-through for nested Skill invocations.
  // recursion_depth defaults to 0 at the root invocation; invokeSkill
  // increments before re-entering this executor for the resolved Skill.
  const recursion_depth = options.recursion_depth ?? 0
  const skill_engine = options.skill_engine

  for (const step of workflow.step_graph) {
    // Per-step dispatch context — derived snapshot, not a live reference.
    // `completed_step_ids` here is the rollback-correct view (success-only),
    // NOT visited; failed-continue steps are excluded.
    const dispatchCtx: DispatchContext = {
      completed_step_ids: [...completed_step_ids],
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
    // record the visit and break — no dispatcher call (terminate is structural,
    // not an I/O step). T-051: terminalCheck runs after this loop. Terminate
    // is structural, not effect-producing — visited only, NOT completed.
    if (descriptor.action === 'terminate') {
      visited_step_ids.push(step.step_id)
      break
    }

    let result: StepDispatchResult
    // M6 Group P (T-073). Steps with `skill_ref` route through invokeSkill
    // when a SkillEngine is present in options. The adapter resolves the
    // Skill, runs an isolated child execution, validates the payload
    // against the cached return_contract, and returns either a validated
    // payload (translated below into a synthetic 'ok' StepDispatchResult)
    // or a canonical failure (translated into a synthetic 'failure'
    // StepDispatchResult so the existing failure-policy switch routes it
    // unchanged via M5).
    if (skill_engine !== undefined && typeof step.skill_ref === 'string') {
      try {
        const invokeResult = await invokeSkill(step, {
          skill_engine,
          dispatch,
          recursion_depth,
        })
        if (invokeResult.kind === 'success') {
          // Record the cross-reference edge BEFORE pushing visited/completed
          // — keeps the relative order obvious to readers.
          child_edges.push({
            step_id: step.step_id,
            skill_ref: invokeResult.skill_ref,
            child_execution_id: invokeResult.child_execution_id,
            validated_dataref: invokeResult.validated_dataref,
          })
          // Translate to the dispatcher-shaped success result. The DataRef
          // envelope (V2 §A11; codex master 2026-04-30 P1.1 fold) becomes
          // the parent step's outputs[0]; the executor's ok-branch below
          // handles visited/completed bookkeeping uniformly — codex P1.3
          // isolation is preserved because the child's visited/completed
          // lists were captured inside the child's ExecutionResult (NOT
          // mutated into the parent's lists).
          result = { kind: 'ok', outputs: [invokeResult.validated_dataref] }
        } else {
          // Synthesize a step failure with the canonical errMsg. The
          // failure-policy switch downstream will route per step.on_failure
          // exactly as if the dispatcher had thrown — keeping all 5 routes
          // (rollback / escalate / pause / abort / continue) reachable for
          // skill_unresolved / skill_output_validation / skill_recursion_cap.
          result = { kind: 'failure', error: new Error(invokeResult.errMsg) }
        }
      } catch (raw) {
        // Invariant guard: invokeSkill is contracted to never throw for
        // expected failure paths. If it does (programmer error in the
        // adapter), surface it as a step failure so the executor stays
        // crash-free.
        const err = raw instanceof Error ? raw : new Error(String(raw))
        result = { kind: 'failure', error: err }
      }
    } else {
      try {
        result = await Promise.resolve(dispatch(descriptor, dispatchCtx))
      } catch (raw) {
        const err = raw instanceof Error ? raw : new Error(String(raw))
        result = { kind: 'failure', error: err }
      }
    }

    if (result.kind === 'ok') {
      // Successful effect → both visited + completed.
      visited_step_ids.push(step.step_id)
      completed_step_ids.push(step.step_id)
      step_outputs.push({
        step_id: step.step_id,
        outputs: result.outputs,
        output_validation_skipped: false,
      })
      continue
    }

    if (result.kind === 'child_result') {
      // V2.3 §A11 — action='spawn_sub_unit' delegates to a child Workflow.
      // Outputs from the child propagate as this step's outputs. Successful
      // child invocation → both visited + completed.
      visited_step_ids.push(step.step_id)
      completed_step_ids.push(step.step_id)
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

    // Failure — route via failure_policy. Pass success-only completed list,
    // NOT visited (codex P1.1): rollback compensation must reverse only steps
    // that produced effects, never failed-continue steps.
    const policyCtx: ExecutionContext = {
      completed_step_ids: [...completed_step_ids],
      autonomy_level: workflow.autonomy_level,
      escalation_target: options.escalation_target,
    }
    const outcome: FailurePolicyOutcome = applyFailurePolicy(step, result.error, policyCtx)

    switch (outcome.action) {
      case 'continue': {
        // Codex P1.3 — log + advance to step[i+1]; partial=true; skip output validation.
        // Codex P1.1 — push to visited (trace) but NOT completed (no successful
        // effect). Subsequent failure-policy / rollback uses completed_step_ids
        // and therefore correctly excludes this step.
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
        // Failed step → visited only, NOT completed.
        visited_step_ids.push(step.step_id)
        return {
          workflow_id: workflow.id,
          visited_step_ids,
          completed_step_ids,
          step_outputs,
          state: 'failed',
          failure_reason: outcome.reason,
          partial,
          ...(child_workflows.length > 0 ? { child_workflows } : {}),
          ...(child_edges.length > 0 ? { child_edges } : {}),
        }
      }
      case 'rollback': {
        // Failed step → visited only, NOT completed. Compensation_order
        // already came from failure-policy applied to completed-only ctx.
        visited_step_ids.push(step.step_id)
        return {
          workflow_id: workflow.id,
          visited_step_ids,
          completed_step_ids,
          step_outputs,
          state: 'failed',
          failure_reason: outcome.reason,
          partial,
          rollback_compensations: outcome.compensation_order,
          ...(child_workflows.length > 0 ? { child_workflows } : {}),
          ...(child_edges.length > 0 ? { child_edges } : {}),
        }
      }
      case 'pause': {
        // Failed step → visited only, NOT completed.
        visited_step_ids.push(step.step_id)
        return {
          workflow_id: workflow.id,
          visited_step_ids,
          completed_step_ids,
          step_outputs,
          state: 'paused',
          failure_reason: outcome.reason,
          partial,
          resume_token: outcome.resume_token,
          ...(child_workflows.length > 0 ? { child_workflows } : {}),
          ...(child_edges.length > 0 ? { child_edges } : {}),
        }
      }
      case 'escalate': {
        // Failed step → visited only, NOT completed.
        visited_step_ids.push(step.step_id)
        return {
          workflow_id: workflow.id,
          visited_step_ids,
          completed_step_ids,
          step_outputs,
          state: 'escalated',
          failure_reason: outcome.reason,
          partial,
          escalation_target: outcome.escalation_target,
          ...(child_workflows.length > 0 ? { child_workflows } : {}),
          ...(child_edges.length > 0 ? { child_edges } : {}),
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
        completed_step_ids,
        step_outputs,
        state: 'failed',
        failure_reason: reason,
        partial,
        ...(child_workflows.length > 0 ? { child_workflows } : {}),
        ...(child_edges.length > 0 ? { child_edges } : {}),
      }
    }
  }

  // success path — no abort, no rollback, no escalate, no pause, no
  // terminalCheck violation. partial may still be true if any step's
  // on_failure='continue' fired (in which case visited_step_ids ⊃ completed_step_ids).
  return {
    workflow_id: workflow.id,
    visited_step_ids,
    completed_step_ids,
    step_outputs,
    state: 'success',
    failure_reason: null,
    partial,
    ...(child_workflows.length > 0 ? { child_workflows } : {}),
    ...(child_edges.length > 0 ? { child_edges } : {}),
  }
}
