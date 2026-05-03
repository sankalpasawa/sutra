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
/**
 * Stable tag prefix on every reason string so downstream callers can lift
 * `failure_reason` without parsing free-form text.
 */
function reasonFor(action, stepId, errMsg) {
    return `step:${stepId}:${action}:${errMsg}`;
}
/**
 * Generate a deterministic resume token from step id + error fingerprint.
 *
 * IMPORTANT: must NOT use `Date.now()`, `Math.random()`, or any non-pure
 * source — failure-policy runs inside the deterministic Workflow context.
 * The token is a function of (step_id, error.message). Uniqueness across
 * runs comes from upstream context, not from this function.
 */
function deriveResumeToken(stepId, errMsg) {
    // Deterministic: encode step id + a short hash-like digest of the message.
    // We avoid Node's `crypto` to stay pure-function and zero-dep here; a small
    // FNV-1a is sufficient for token uniqueness within a Workflow run.
    let h = 0x811c9dc5;
    for (let i = 0; i < errMsg.length; i++) {
        h ^= errMsg.charCodeAt(i);
        h = Math.imul(h, 0x01000193) >>> 0;
    }
    return `resume:${stepId}:${h.toString(16)}`;
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
export function applyFailurePolicy(step, error, context, otelCtx) {
    if (typeof step !== 'object' || step === null) {
        throw new TypeError('applyFailurePolicy: step must be a WorkflowStep object');
    }
    if (!(error instanceof Error)) {
        throw new TypeError('applyFailurePolicy: error must be an Error instance');
    }
    if (typeof context !== 'object' || context === null) {
        throw new TypeError('applyFailurePolicy: context must be an ExecutionContext object');
    }
    const errMsg = error.message;
    const stepId = step.step_id;
    let outcome;
    switch (step.on_failure) {
        case 'rollback': {
            // Reverse-execute compensations. Empty completed list ⇒ empty order
            // (no work to undo); still routes as rollback so Workflow fails.
            const completed = Array.isArray(context.completed_step_ids)
                ? [...context.completed_step_ids]
                : [];
            // Defensive — clone before .reverse() to prevent caller mutation even
            // if a future refactor drops the spread above. .slice() is cheap.
            const compensation_order = completed.slice().reverse();
            outcome = {
                action: 'rollback',
                compensation_order,
                reason: reasonFor('rollback', stepId, errMsg),
            };
            break;
        }
        case 'escalate': {
            const escalation_target = context.escalation_target ?? 'founder';
            outcome = {
                action: 'escalate',
                escalated: true,
                escalation_target,
                reason: reasonFor('escalate', stepId, errMsg),
            };
            break;
        }
        case 'pause': {
            outcome = {
                action: 'pause',
                paused: true,
                resume_token: deriveResumeToken(stepId, errMsg),
                reason: reasonFor('pause', stepId, errMsg),
            };
            break;
        }
        case 'abort': {
            outcome = {
                action: 'abort',
                reason: reasonFor('abort', stepId, errMsg),
            };
            break;
        }
        case 'continue': {
            outcome = {
                action: 'continue',
                partial: true,
                failed_step_id: stepId,
                reason: reasonFor('continue', stepId, errMsg),
            };
            break;
        }
        default: {
            // Defensive — Workflow primitive validators reject unknown values at the
            // boundary, but we guard here so failure-policy can be unit-tested
            // independently of the constructor.
            throw new Error(`applyFailurePolicy: unknown on_failure="${String(step.on_failure)}" — must be rollback|escalate|pause|abort|continue`);
        }
    }
    // M8 Group Z (T-109). Mirror the routing decision to OTel if a context is
    // supplied. Fire-and-forget: we do NOT await — applyFailurePolicy stays
    // synchronous (changing the signature would break all M5 callers).
    emitFailurePolicyOutcome(otelCtx, outcome, stepId, errMsg);
    return outcome;
}
/**
 * Map the routed outcome to the canonical FAILURE_POLICY_<OUTCOME> kind +
 * fire the emit. Errors inside the emitter are swallowed inside the
 * try/catch chain at the OTelEmitter layer; this helper is best-effort.
 *
 * Per-outcome attribute schemas:
 *   FAILURE_POLICY_ROLLBACK : { reason, compensation_order, failed_step_id }
 *   FAILURE_POLICY_ESCALATE : { reason, escalation_target, failed_step_id }
 *   FAILURE_POLICY_PAUSE    : { reason, resume_token, failed_step_id }
 *   FAILURE_POLICY_ABORT    : { reason, failed_step_id }
 *   FAILURE_POLICY_CONTINUE : { reason, failed_step_id }
 */
function emitFailurePolicyOutcome(otelCtx, outcome, stepId, errMsg) {
    if (otelCtx === undefined)
        return;
    const { otel_emitter, trace_id } = otelCtx;
    if (otel_emitter === undefined)
        return;
    if (typeof trace_id !== 'string' || trace_id.length === 0)
        return;
    const kind = (() => {
        switch (outcome.action) {
            case 'rollback':
                return 'FAILURE_POLICY_ROLLBACK';
            case 'escalate':
                return 'FAILURE_POLICY_ESCALATE';
            case 'pause':
                return 'FAILURE_POLICY_PAUSE';
            case 'abort':
                return 'FAILURE_POLICY_ABORT';
            case 'continue':
                return 'FAILURE_POLICY_CONTINUE';
        }
    })();
    const baseAttrs = {
        reason: outcome.reason,
        failed_step_id: stepId,
        error_message: errMsg,
    };
    let attributes = baseAttrs;
    if (outcome.action === 'rollback') {
        attributes = { ...baseAttrs, compensation_order: outcome.compensation_order };
    }
    else if (outcome.action === 'escalate') {
        attributes = { ...baseAttrs, escalation_target: outcome.escalation_target };
    }
    else if (outcome.action === 'pause') {
        attributes = { ...baseAttrs, resume_token: outcome.resume_token };
    }
    // Fire-and-forget. A rejected promise becomes an unhandled rejection at
    // most; the in-memory + noop + stub exporters never reject. Catch here
    // defensively so a future custom exporter that throws synchronously cannot
    // crash the failure-policy switch.
    try {
        void otel_emitter
            .emit({
            decision_kind: kind,
            trace_id,
            step_id: stepId,
            ...(otelCtx.workflow_id !== undefined ? { workflow_id: otelCtx.workflow_id } : {}),
            ...(otelCtx.agent_identity !== undefined
                ? { agent_identity: otelCtx.agent_identity }
                : {}),
            ...(otelCtx.actor !== undefined ? { actor: otelCtx.actor } : {}),
            attributes,
        })
            .catch(() => {
            // observability failure must NEVER break execution
        });
    }
    catch {
        // synchronous exporter failure — also dropped silently
    }
}
//# sourceMappingURL=failure-policy.js.map