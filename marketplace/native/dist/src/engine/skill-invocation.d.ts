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
import type { SkillEngine } from './skill-engine.js';
import type { DataRef, WorkflowStep } from '../types/index.js';
import { type ActivityDispatcher, type ExecutionResult } from './step-graph-executor.js';
import type { AgentIdentity } from '../types/agent-identity.js';
import type { OTelEmitter } from './otel-emitter.js';
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
export declare const SKILL_RECURSION_CAP = 8;
/**
 * Context handed to invokeSkill by the executor (T-073). The executor is
 * responsible for plumbing the same `dispatch` it uses for the parent's own
 * steps, plus the SkillEngine instance + the current recursion depth (which
 * starts at 0 at the root invocation and is incremented for each child
 * invocation chain).
 */
export interface SkillInvocationContext {
    /** SkillEngine carrying the registered Skills + cached validators. */
    readonly skill_engine: SkillEngine;
    /**
     * Activity dispatcher used by the child executor for its own per-step
     * Activity calls. Same boundary as the parent's executor — simulating
     * Temporal's worker semantics in tests + real boundary semantics in prod.
     */
    readonly dispatch: ActivityDispatcher;
    /**
     * Current recursion depth. The root invocation starts at 0; each child
     * frame adds +1 before re-entering executeStepGraph. Cap is checked at
     * the top of invokeSkill against SKILL_RECURSION_CAP.
     */
    readonly recursion_depth: number;
    /**
     * M8 Group Z (T-107). Optional OTel emitter — when supplied, invokeSkill
     * emits SKILL_RESOLVED / SKILL_UNRESOLVED / SKILL_RECURSION_CAP records
     * carrying the trace_id + workflow_id + step_id + agent_identity for
     * cross-correlation. Absent ⇒ no emission (M6 baseline tests stay clean).
     */
    readonly otel_emitter?: OTelEmitter;
    /** M8 Group Z (T-107). trace_id propagated from the parent executor. */
    readonly trace_id?: string;
    /** M8 Group Z (T-107). workflow_id of the parent execution. */
    readonly workflow_id?: string;
    /** M8 Group Z (T-107). agent_identity carried from the executor caller. */
    readonly agent_identity?: AgentIdentity;
    /** M8 Group Z (T-107). actor (authority-holder id, D1 §1) when known. */
    readonly actor?: string;
    /**
     * M9 Group FF + codex master P1.1 fold. Tenant context propagated into
     * child invocations so the executor's fail-closed gate sees the same
     * `tenant_context_id` the parent supplied. Without this, a child Skill
     * with a non-null `custody_owner` (e.g. cross-tenant grants via
     * delegates_to) would trip fail-closed because the child re-entry got
     * no tenant context.
     */
    readonly tenant_context_id?: string;
    /**
     * M9 Group FF + codex master P1.1 fold. Delegates_to edge set
     * propagated alongside tenant_context_id so child cross-tenant
     * decisions consult the same edges.
     */
    readonly delegates_to_edges?: ReadonlyArray<import('../types/edges.js').DelegatesToEdge>;
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
    readonly kind: 'success';
    readonly skill_ref: string;
    readonly child_execution_id: string;
    readonly validated_dataref: DataRef;
    readonly child_result: ExecutionResult;
}
/**
 * Discriminated failure branch. `errMsg` follows the canonical format the
 * executor (T-073) wraps into a synthetic step failure → M5 failure-policy
 * routes via the existing 5-set (rollback / escalate / pause / abort /
 * continue). The format prefix is stable so downstream consumers can lift
 * the failure class without parsing free-form text.
 */
export interface SkillInvocationFailure {
    readonly kind: 'failure';
    readonly skill_ref: string;
    readonly errMsg: string;
}
export type SkillInvocationResult = SkillInvocationSuccess | SkillInvocationFailure;
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
export declare function invokeSkill(parentStep: WorkflowStep, context: SkillInvocationContext): Promise<SkillInvocationResult>;
//# sourceMappingURL=skill-invocation.d.ts.map