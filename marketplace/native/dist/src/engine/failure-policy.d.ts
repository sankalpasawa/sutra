/**
 * failure-policy — M5 Group K (T-050).
 *
 * Routes per `step.on_failure` ∈ {rollback, escalate, pause, abort, continue}
 * (V2 §17 A10; 5-set). Pure function: takes a step + error + context, returns
 * a `FailurePolicyOutcome` describing what the executor should do next.
 *
 * `continue` semantics (codex P1.3, NON-NEGOTIABLE):
 *   - failed step is logged with reason
 *   - executor advances to step[i+1] (does NOT abort Workflow)
 *   - sets `partial=true` on the Workflow execution
 *   - outputs validation is SKIPPED for the failed step
 *   - Workflow continues end-to-end; final state has `partial=true`
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group K T-050
 *  - holding/research/2026-04-28-v2-architecture-spec.md §17 A10
 *  - .enforcement/codex-reviews/2026-04-29-m5-plan-pre-dispatch.md P1.3
 */
import type { WorkflowStep } from '../types/index.js';
import type { AgentIdentity } from '../types/agent-identity.js';
import type { OTelEmitter } from './otel-emitter.js';
/**
 * Context handed to `applyFailurePolicy`. The executor populates this with
 * (a) the steps already completed (for rollback compensation walk),
 * (b) the workflow autonomy_level (auto-escalate vs human-gate),
 * (c) an optional escalation target (BoundaryEndpoint ref, e.g. founder).
 */
export interface ExecutionContext {
    /** Completed step ids in execution order (for rollback compensation walk). */
    completed_step_ids: number[];
    /** Workflow autonomy level — affects escalate/pause routing. */
    autonomy_level: 'manual' | 'semi' | 'autonomous';
    /** Optional escalation BoundaryEndpoint ref. Defaults to 'founder'. */
    escalation_target?: string;
}
/**
 * Discriminated outcome of the policy handler. Each variant encodes:
 *   - the action the executor takes next
 *   - the supporting fields the action needs
 *   - the reason string suitable for `Execution.failure_reason`
 *
 * The 5 variants map 1:1 with `StepFailureAction`.
 */
export type FailurePolicyOutcome = 
/** Reverse-execute completed steps' compensations; then fail Workflow. */
{
    action: 'rollback';
    /** Step ids to compensate, reversed (last-completed first). */
    compensation_order: number[];
    reason: string;
}
/** Hand off to escalation_target; mark workflow escalated. */
 | {
    action: 'escalate';
    escalated: true;
    escalation_target: string;
    reason: string;
}
/** Suspend execution; emit a resume_token. */
 | {
    action: 'pause';
    paused: true;
    resume_token: string;
    reason: string;
}
/** Terminate Workflow immediately. */
 | {
    action: 'abort';
    reason: string;
}
/** Log + advance to step[i+1]; partial=true on execution. */
 | {
    action: 'continue';
    partial: true;
    /** Step id of the failed step (logged + skip-outputs-validation marker). */
    failed_step_id: number;
    reason: string;
};
/**
 * M8 Group Z (T-109). Optional OTel context for emit-on-outcome. Backward-
 * compatible with M5/M6/M7 callers that pass only (step, error, context).
 *
 * When supplied, applyFailurePolicy emits FAILURE_POLICY_<OUTCOME> for the
 * routed outcome carrying trace_id + workflow_id + step_id + agent_identity.
 * The emit is fire-and-forget — applyFailurePolicy stays SYNCHRONOUS and
 * pure-return; the emit promise is not awaited (we don't want to make every
 * caller async to satisfy observability). Errors inside the exporter would
 * surface as unhandled rejections at the runtime — accepted v1.0 risk; the
 * exporters here (in-memory + noop + OTLP-stub) do not throw.
 */
export interface FailurePolicyOTelContext {
    readonly otel_emitter?: OTelEmitter;
    readonly trace_id: string;
    readonly workflow_id?: string;
    readonly agent_identity?: AgentIdentity;
    readonly actor?: string;
}
/**
 * Apply the failure_policy router for a single failed step.
 *
 * Pure function. No I/O. Replay-deterministic given identical inputs.
 *
 * @param step    The Workflow step that failed.
 * @param error   The raised Error (message used in reason + token derivation).
 * @param context Executor-supplied context (completed steps; autonomy_level).
 * @param otelCtx M8 Group Z (T-109). Optional OTel emit context — when
 *                supplied with a non-empty trace_id + emitter, the routing
 *                decision is mirrored to the OTel stream.
 * @returns       A FailurePolicyOutcome encoding the executor's next move.
 */
export declare function applyFailurePolicy(step: WorkflowStep, error: Error, context: ExecutionContext, otelCtx?: FailurePolicyOTelContext): FailurePolicyOutcome;
//# sourceMappingURL=failure-policy.d.ts.map