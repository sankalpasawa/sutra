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

import type { SkillEngine, ValidateOutputsResult } from './skill-engine.js'
import type { DataRef, WorkflowStep } from '../types/index.js'
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
 * Discriminated success branch. `validated_dataref` is the DataRef envelope the
 * parent step's outputs slot will receive (the executor at T-073 records it as
 * step_outputs[parent_step_id].outputs[0]).
 *
 * Per V2 §A11 (codex master 2026-04-30 P1.1 fold): a Skill returns a DataRef
 * per its `return_contract`. The envelope is built at the invocation boundary
 * after the child's terminal payload validates against return_contract:
 *
 *   {
 *     kind: 'skill-output',
 *     schema_ref: skill.return_contract,        // the JSON Schema string
 *     locator: 'inline:' + JSON.stringify(payload),
 *     version: '1',                              // implicit at v1.0 (one impl per ref)
 *     mutability: 'immutable',                   // outputs are frozen
 *     retention: 'session',                      // in-memory; M11 may extend
 *     authoritative_status: 'authoritative',     // outputs are authoritative
 *   }
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
  readonly validated_dataref: DataRef
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
 * Type guard: is this value a `kind='skill-output'` DataRef envelope (the
 * shape produced by `buildSkillOutputDataRef`)?
 *
 * Codex master 2026-04-30 P1.1 fold support helper: when the OUTER Skill's
 * terminal step is itself a skill_ref step, the outer's terminal payload is
 * the INNER Skill's DataRef envelope (because the executor records the inner
 * envelope into outputs[0]). Without unwrapping, the outer's `return_contract`
 * (which describes the payload shape, e.g. `{type:'integer'}`) would validate
 * against the DataRef object — false negative every time.
 *
 * The unwrap path uses this guard to detect that case and pull the original
 * payload out of `locator='inline:<JSON>'` before validation.
 */
function isSkillOutputDataRef(value: unknown): value is DataRef {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    v.kind === 'skill-output' &&
    typeof v.locator === 'string' &&
    (v.locator as string).startsWith('inline:')
  )
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
 * Codex master 2026-04-30 P1.1 fold transitivity: when the terminal step is
 * itself a `skill_ref` step (Skill-of-Skills composition), the terminal
 * output is the INNER Skill's DataRef envelope. The outer Skill's
 * `return_contract` is declared against the original payload shape (V2 §A11
 * design intent — schema_ref describes what's inside the locator), so we
 * unwrap one level of `kind='skill-output'` envelope before validation.
 * Without this, every chained Skill at depth >= 2 would fail validation
 * against an envelope shape it never declared.
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
  const raw = last.outputs[0]
  // Transitivity unwrap (codex master 2026-04-30 P1.1 fold): if the terminal
  // output is an inner Skill's DataRef envelope, pull the original payload
  // back out so the outer Skill's return_contract validates against the
  // declared payload shape, not the envelope shape.
  if (isSkillOutputDataRef(raw)) {
    const locator = (raw as DataRef).locator
    const innerJson = locator.slice('inline:'.length)
    try {
      return JSON.parse(innerJson) as unknown
    } catch {
      // Malformed locator → fall through with the envelope itself (defensive;
      // in practice the locator is always JSON.stringify(payload) from
      // buildSkillOutputDataRef so JSON.parse should never throw).
      return raw
    }
  }
  return raw
}

/**
 * Wrap a validated terminal payload in the V2 §A11 DataRef envelope.
 *
 * Codex master review 2026-04-30 P1.1 fold: V2 §A11 says child execution
 * "returns DataRef per `return_contract`." This builder produces that envelope
 * at the invocation boundary. Field semantics:
 *
 *   - kind='skill-output'         — discriminator for downstream observability
 *   - schema_ref=return_contract  — the JSON Schema string the Skill declared
 *   - locator='inline:<JSON>'     — v1.0 inline locator (M8+ may upgrade to
 *                                   content-addressed/URI for cross-process
 *                                   passing); JSON-encoded to keep the locator
 *                                   self-describing without ambient context
 *   - version='1'                 — Skill version is implicit at v1.0 (the
 *                                   registry has only one impl per skill_ref)
 *   - mutability='immutable'      — Skill outputs are frozen at completion;
 *                                   downstream consumers MUST NOT mutate
 *   - retention='session'         — in-memory for v1.0; M11 dogfood may
 *                                   promote to durable storage
 *   - authoritative_status='authoritative' — Skill outputs are authoritative
 *                                            by default per D2 §5; advisory
 *                                            tagging is a Skill-author opt-in
 *                                            in v1.x (D-NS future)
 *
 * Pure function — no clock, no random. Replay-deterministic given identical
 * (payload, return_contract).
 */
function buildSkillOutputDataRef(payload: unknown, return_contract: string): DataRef {
  return {
    kind: 'skill-output',
    schema_ref: return_contract,
    locator: `inline:${JSON.stringify(payload)}`,
    version: '1',
    mutability: 'immutable',
    retention: 'session',
    authoritative_status: 'authoritative',
  }
}

/**
 * Strip the M5 failure-policy prefix (`step:<N>:<action>:`) from a
 * `child_result.failure_reason` to recover the canonical inner errMsg.
 *
 * Codex master review 2026-04-30 P2.1 fold: when a child's child fails (e.g.
 * `skill_recursion_cap:8` deep in a chain), the immediate child's
 * failure-policy wraps it as `step:1:abort:skill_recursion_cap:8`. If the
 * outer frame propagated that wrapped string, EACH ancestor would re-wrap,
 * yielding `step:1:abort:step:1:abort:...` chains with N levels of prefix.
 *
 * Solution: strip ONE layer of M5 prefix when propagating. Each ancestor's
 * own failure-policy then re-applies exactly one prefix level, keeping the
 * outermost failure_reason at `step:<N>:<action>:<canonical-errMsg>` shape
 * regardless of nesting depth. The canonical inner errMsg
 * (`skill_recursion_cap:8`, `skill_unresolved:foo`, `skill_output_validation:...`)
 * is preserved for M8/M9 observability.
 *
 * Regex: `^step:\d+:[a-z]+:(.+)$` — captures the inner errMsg. If the input
 * does NOT match (defensive: unexpected shape), return the input unchanged so
 * we never lose information.
 */
function stripFailurePolicyPrefix(reason: string): string {
  const match = /^step:\d+:[a-z]+:(.+)$/.exec(reason)
  return match ? match[1]! : reason
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

  // 3a. Codex master review 2026-04-30 P2.1 fold: when the child execution
  // FAILED, the canonical failure class is already in `child_result.failure_reason`
  // (e.g. `step:1:abort:skill_recursion_cap:8` from M5 failure-policy formatting).
  // Propagate that DIRECTLY rather than running validateOutputs against an
  // undefined terminal payload + synthesizing `skill_output_validation:` from
  // ajv's "expected X, got undefined" error. Strip ONE layer of M5 prefix so
  // each ancestor frame re-applies exactly one prefix, keeping the outermost
  // failure_reason canonically shaped regardless of nesting depth.
  if (child_result.state !== 'success') {
    const childReason = child_result.failure_reason ?? 'child_failed:no_reason'
    const innerErrMsg = stripFailurePolicyPrefix(childReason)
    return {
      kind: 'failure',
      skill_ref,
      errMsg: innerErrMsg,
    }
  }

  // 4. Extract the terminal payload (last completed step's outputs[0]).
  const validated_payload = extractTerminalPayload(child_result)

  // 5. Validate against the cached return_contract. ajv compiled at
  // register-time → O(1) on the validation hot path.
  const validation: ValidateOutputsResult = context.skill_engine.validateOutputs(
    skill_ref,
    validated_payload,
  )
  if (!validation.valid) {
    return {
      kind: 'failure',
      skill_ref,
      errMsg: `skill_output_validation:${validation.errors}`,
    }
  }

  // 6. Success — wrap the validated payload in the V2 §A11 DataRef envelope.
  // The schema_ref is the Skill's return_contract (already on the resolved
  // Workflow). Codex master review 2026-04-30 P1.1 fold.
  const validated_dataref = buildSkillOutputDataRef(
    validated_payload,
    resolved.return_contract!,
  )
  return {
    kind: 'success',
    skill_ref,
    child_execution_id: synthesizeChildExecutionId(parentStep.step_id, skill_ref),
    validated_dataref,
    child_result,
  }
}
