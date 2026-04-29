/**
 * skill-invocation — M6 Group P (T-069..T-073).
 *
 * The runtime seam between a parent Workflow step that carries a `skill_ref`
 * and the registered Skill (Workflow with reuse_tag=true). On invocation:
 *
 *   1. Recursion-depth cap check (SKILL_RECURSION_CAP = 8)
 *   2. SkillEngine.resolve(skill_ref) → Workflow | null
 *   3. Run the resolved Workflow as an ISOLATED child Execution via
 *      executeStepGraph(...) carrying recursion_depth+1 in options.
 *   4. Extract the child's terminal-step output (first output of the last
 *      executed step in the child's step_graph).
 *   5. Validate against the cached return_contract via
 *      SkillEngine.validateOutputs(skill_ref, payload).
 *   6. Return a discriminated SkillInvocationResult.
 *
 * Failure paths surface as `kind:'failure'` with one of three canonical
 * errMsg formats so the executor (T-073) can synthesize a step failure that
 * routes through the M5 failure-policy unchanged:
 *
 *   - skill_unresolved:<skill_ref>
 *   - skill_output_validation:<details>
 *   - skill_recursion_cap:<depth>
 *
 * Replay-determinism (codex P1.3, master review 2026-04-29):
 *   - `child_execution_id` is synthesized from (parent step_id, skill_ref) —
 *     NO Date.now() / Math.random() / crypto.randomUUID() — so a replay
 *     produces a bit-identical id.
 *   - Child trace stays ISOLATED from the parent: the parent's
 *     visited_step_ids does NOT include any of the child's internal
 *     step_ids; only the parent step that carried `skill_ref`. The child's
 *     full ExecutionResult is exposed on `SkillInvocationSuccess.child_result`
 *     for diagnostics, but the executor must NOT merge it into parent state.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M6-skill-engine.md Group P
 *   - .enforcement/codex-reviews/2026-04-30-m6-plan-pre-dispatch.md (P1.3)
 *   - holding/research/2026-04-28-v2-architecture-spec.md §A11 (Skill /
 *     return_contract)
 */

import type { SkillEngine } from './skill-engine.js'
import type { WorkflowStep } from '../types/index.js'
import {
  executeStepGraph,
  type ActivityDispatcher,
  type ExecutionResult,
} from './step-graph-executor.js'

/**
 * Maximum chain depth for skill→skill invocation. Eight is the v1.0 ceiling
 * agreed in the M6 plan: deep enough to express realistic Skill composition,
 * shallow enough that a runaway invocation chain fails fast with a stable
 * canonical errMsg the executor can route via M5 failure-policy.
 *
 * Depth 0 = the root Workflow's invocation (the parent calls invokeSkill at
 * its own depth-0 frame; the resolved child runs at depth 1, the
 * grandchild at depth 2, … the 8th descendant attempts to invoke at depth 8
 * and is rejected).
 */
export const SKILL_RECURSION_CAP = 8

/**
 * Context handed to invokeSkill by the executor (T-073). The executor is
 * responsible for plumbing the same `dispatch` it uses for the parent's own
 * steps, plus the SkillEngine instance + the current recursion depth (which
 * starts at 0 at the root invocation and is incremented for each child
 * invocation chain).
 */
export interface SkillInvocationContext {
  /** SkillEngine carrying the registered Skills + cached validators. */
  readonly skill_engine: SkillEngine
  /**
   * Activity dispatcher used by the child executor for its own per-step
   * Activity calls. Same boundary as the parent's executor — simulating
   * Temporal's worker semantics in tests + real boundary semantics in prod.
   */
  readonly dispatch: ActivityDispatcher
  /**
   * Current recursion depth. The root invocation starts at 0; each child
   * frame adds +1 before re-entering executeStepGraph. Cap is checked at
   * the top of invokeSkill against SKILL_RECURSION_CAP.
   */
  readonly recursion_depth: number
}

/**
 * Discriminated success branch. `validated_payload` is the value the parent
 * step's outputs slot will receive (the executor at T-073 records it as
 * step_outputs[parent_step_id]).
 *
 * `child_result` is the FULL ExecutionResult of the isolated child. The
 * executor MUST NOT merge child.visited_step_ids / completed_step_ids into
 * the parent's lists — that is the codex P1.3 isolation contract. Surfacing
 * the result here is for diagnostics + potential cross-cutting tooling
 * (e.g. observability extensions in M9).
 */
export interface SkillInvocationSuccess {
  readonly kind: 'success'
  readonly skill_ref: string
  readonly child_execution_id: string
  readonly validated_payload: unknown
  readonly child_result: ExecutionResult
}

/**
 * Discriminated failure branch. `errMsg` follows the canonical format the
 * executor (T-073) wraps into a synthetic step failure → M5 failure-policy
 * routes via the existing 5-set (rollback / escalate / pause / abort /
 * continue). The format prefix is stable so downstream consumers can lift
 * the failure class without parsing free-form text.
 */
export interface SkillInvocationFailure {
  readonly kind: 'failure'
  readonly skill_ref: string
  readonly errMsg: string
}

export type SkillInvocationResult = SkillInvocationSuccess | SkillInvocationFailure

/**
 * Synthesize the deterministic child_execution_id. Pinned format:
 *   `child-<parent_step_id>-<skill_ref>`
 * Replay rule: same parent step + same skill_ref ⇒ same id (no clock).
 * Tested by tests/contract/engine/skill-invocation.test.ts "deterministic"
 * suite; do NOT introduce a counter / nonce / hash without updating the
 * tests + downstream observability consumers.
 */
function synthesizeChildExecutionId(parent_step_id: number, skill_ref: string): string {
  return `child-${parent_step_id}-${skill_ref}`
}

/**
 * Pull the validated_payload out of a child's ExecutionResult.
 *
 * Convention (V2 §A11): a Skill's `return_contract` describes the shape of
 * a SINGLE payload value emitted by the Skill's terminal step. We pick the
 * last successfully-completed step's `outputs[0]` as that payload. If the
 * child failed (no successful terminal output) or its terminal step
 * produced no outputs, return `undefined` — the validator will catch it
 * (most schemas reject undefined; if a Skill explicitly allows undefined,
 * its schema must declare so).
 *
 * Rationale for outputs[0]: V2 §A11 frames `return_contract` as the
 * Skill's typed return value, not its full per-step output stream. Skills
 * that need to surface multiple outputs should aggregate into a single
 * object payload — same shape downstream consumers expect.
 */
function extractTerminalPayload(child_result: ExecutionResult): unknown {
  const entries = child_result.step_outputs
  if (entries.length === 0) return undefined
  // Last entry corresponds to the last executed step (executor pushes in
  // order). Failed-continue steps push entries with empty outputs; their
  // payload is undefined which the validator will reject. That is the
  // intended behavior: a Skill that fails partway should NOT pass the
  // return_contract gate.
  const last = entries[entries.length - 1]
  if (!last || last.outputs.length === 0) return undefined
  return last.outputs[0]
}

/**
 * Run a registered Skill as an isolated child Execution from a parent step.
 *
 * Async: `executeStepGraph` is async, so this is too. The function does not
 * itself perform I/O — all I/O lives in the dispatcher passed in via the
 * context (same boundary contract as the parent executor).
 *
 * @param parentStep  The parent Workflow step that carries `skill_ref`.
 * @param context     SkillEngine + dispatcher + current recursion depth.
 * @returns           Discriminated SkillInvocationResult; never throws for
 *                    expected failure paths (recursion cap, miss, validation).
 */
export async function invokeSkill(
  parentStep: WorkflowStep,
  context: SkillInvocationContext,
): Promise<SkillInvocationResult> {
  const skill_ref = parentStep.skill_ref
  if (typeof skill_ref !== 'string' || skill_ref.length === 0) {
    // Defensive: caller (executor) is contracted to only call invokeSkill
    // when parentStep.skill_ref is a non-empty string. Surface a clear
    // failure rather than throwing — keeps the executor's branch shape
    // uniform.
    return {
      kind: 'failure',
      skill_ref: '',
      errMsg: 'skill_unresolved:<missing skill_ref on parent step>',
    }
  }

  // 1. Recursion-depth cap (T-072). Check BEFORE resolution so a runaway
  // chain fails fast without touching the registry / dispatcher.
  if (context.recursion_depth >= SKILL_RECURSION_CAP) {
    return {
      kind: 'failure',
      skill_ref,
      errMsg: `skill_recursion_cap:${context.recursion_depth}`,
    }
  }

  // 2. Resolve the Skill. Miss surfaces as canonical skill_unresolved.
  const resolved = context.skill_engine.resolve(skill_ref)
  if (resolved === null) {
    return {
      kind: 'failure',
      skill_ref,
      errMsg: `skill_unresolved:${skill_ref}`,
    }
  }

  // 3. Run the child as an ISOLATED Execution. Pass recursion_depth+1 + the
  // SkillEngine through the executor's options bag (T-073 extends
  // ExecuteOptions to carry these). The child's executor uses these for
  // its OWN children (depth+2, etc.); the parent's executor never sees
  // the child's internals — the only thing it gets back is the validated
  // payload + child_result for diagnostics.
  const child_result = await executeStepGraph(resolved, context.dispatch, {
    recursion_depth: context.recursion_depth + 1,
    skill_engine: context.skill_engine,
  })

  // 4. Extract the terminal payload (last completed step's outputs[0]).
  const validated_payload = extractTerminalPayload(child_result)

  // 5. Validate against the cached return_contract. ajv compiled at
  // register-time → O(1) on the validation hot path.
  const validation = context.skill_engine.validateOutputs(skill_ref, validated_payload)
  if (!validation.valid) {
    return {
      kind: 'failure',
      skill_ref,
      errMsg: `skill_output_validation:${validation.errors}`,
    }
  }

  // 6. Success — synthesize the deterministic child_execution_id, return
  // the typed payload + the child_result for downstream tooling.
  return {
    kind: 'success',
    skill_ref,
    child_execution_id: synthesizeChildExecutionId(parentStep.step_id, skill_ref),
    validated_payload,
    child_result,
  }
}
