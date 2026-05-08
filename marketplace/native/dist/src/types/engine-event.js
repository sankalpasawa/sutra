/**
 * EngineEvent — D2 step 4 of vertical slice.
 *
 * The discriminated union of events the Native engine emits to its terminal
 * (and, in v1.1+, to OpenTelemetry sinks). Renderers in renderer-registry.ts
 * consume these to produce human-readable lines for the founder.
 *
 * v1.0 ships 8 event types covering the founder's "what's happening" view:
 *   1. routing_decision     — Router.route() emitted a decision
 *   2. workflow_started     — Workflow execution began
 *   3. workflow_completed   — Workflow execution finished successfully
 *   4. workflow_failed      — Workflow execution terminated with failure
 *   5. artifact_registered  — ArtifactCatalog.register() persisted an asset
 *   6. policy_decision      — OPA POLICY_ALLOW or POLICY_DENY emission
 *   7. step_started         — Workflow step (within an execution) began
 *   8. step_completed       — Workflow step finished
 *
 * Per softened I-NPD-1: events are pure data — no closures, no mutable
 * references — so they can be JSONL-serialized for replay. Renderers are
 * pure functions of (event, ctx) → string; the registry lets operators
 * override per-event_type.
 */
/** Runtime allow-list mirroring EngineEventType — kept in sync. */
export const ENGINE_EVENT_TYPES = new Set([
    'routing_decision',
    'workflow_started',
    'workflow_completed',
    'workflow_failed',
    'artifact_registered',
    'policy_decision',
    'step_started',
    'step_completed',
    'pattern_proposed',
    'proposal_approved',
    'proposal_rejected',
    'approval_requested',
    'approval_granted',
    'approval_denied',
    'approval_already_handled',
    'workflow_rollback_started',
    'step_compensated',
    'step_compensation_failed',
    'workflow_rollback_complete',
    'workflow_rollback_partial',
    'workflow_escalated',
    'step_paused',
    'precondition_check',
    'postcondition_check',
    'commitment_broken',
]);
// -----------------------------------------------------------------------------
// Per-variant validators (codex P1 fold 2026-05-03) — guard MUST validate the
// full union shape, not just the discriminator + ts_ms. Failing at intake is
// non-recoverable; render-time TypeError on a bad payload is worse.
// -----------------------------------------------------------------------------
const ROUTING_MODES = new Set(['exact', 'llm-fallback', 'no-match']);
const POLICY_VERDICTS = new Set(['ALLOW', 'DENY']);
function isStr(v) { return typeof v === 'string'; }
function isNonEmptyStr(v) { return typeof v === 'string' && v.length > 0; }
function isStrOrNull(v) { return v === null || typeof v === 'string'; }
function isNonNegInt(v) {
    return typeof v === 'number' && Number.isInteger(v) && v >= 0;
}
function isFiniteNonNegNumber(v) {
    return typeof v === 'number' && Number.isFinite(v) && v >= 0;
}
const VARIANT_VALIDATORS = {
    routing_decision: (v) => isStrOrNull(v.turn_id) &&
        isStr(v.mode) && ROUTING_MODES.has(v.mode) &&
        isStrOrNull(v.workflow_id) &&
        isStrOrNull(v.trigger_id) &&
        isNonNegInt(v.attempts_count),
    workflow_started: (v) => isNonEmptyStr(v.workflow_id) && isNonEmptyStr(v.execution_id),
    workflow_completed: (v) => isNonEmptyStr(v.workflow_id) &&
        isNonEmptyStr(v.execution_id) &&
        isFiniteNonNegNumber(v.duration_ms),
    workflow_failed: (v) => isNonEmptyStr(v.workflow_id) &&
        isNonEmptyStr(v.execution_id) &&
        isStr(v.reason),
    artifact_registered: (v) => isNonEmptyStr(v.domain_id) &&
        isNonEmptyStr(v.content_sha256) &&
        isNonEmptyStr(v.asset_kind) &&
        (v.producer_execution_id === undefined || isNonEmptyStr(v.producer_execution_id)),
    policy_decision: (v) => isStr(v.verdict) && POLICY_VERDICTS.has(v.verdict) &&
        isNonEmptyStr(v.rule_id) &&
        (v.workflow_id === undefined || isNonEmptyStr(v.workflow_id)) &&
        (v.reason === undefined || isStr(v.reason)),
    step_started: (v) => isNonEmptyStr(v.workflow_id) &&
        isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.step_id) &&
        isNonNegInt(v.step_index) &&
        isNonNegInt(v.step_count),
    step_completed: (v) => isNonEmptyStr(v.workflow_id) &&
        isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.step_id) &&
        isNonNegInt(v.step_index) &&
        isNonNegInt(v.step_count) &&
        isFiniteNonNegNumber(v.duration_ms),
    pattern_proposed: (v) => isNonEmptyStr(v.pattern_id) &&
        isNonEmptyStr(v.normalized_phrase) &&
        isNonNegInt(v.evidence_count) &&
        isNonEmptyStr(v.proposed_workflow_id) &&
        isNonEmptyStr(v.proposed_trigger_id),
    proposal_approved: (v) => isNonEmptyStr(v.pattern_id) &&
        isNonEmptyStr(v.registered_workflow_id) &&
        isNonEmptyStr(v.registered_trigger_id),
    proposal_rejected: (v) => isNonEmptyStr(v.pattern_id) &&
        isStr(v.reason),
    approval_requested: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.step_index) &&
        isStr(v.prompt_summary),
    approval_granted: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.step_index),
    approval_denied: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.step_index) &&
        isStr(v.reason),
    approval_already_handled: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.step_index) &&
        isFiniteNonNegNumber(v.originally_decided_at_ms),
    workflow_rollback_started: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isStr(v.reason),
    step_compensated: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.step_index) &&
        isFiniteNonNegNumber(v.duration_ms),
    step_compensation_failed: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.step_index) &&
        isStr(v.reason),
    workflow_rollback_complete: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.steps_compensated),
    workflow_rollback_partial: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.steps_compensated) &&
        isNonNegInt(v.steps_failed),
    workflow_escalated: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isStr(v.reason),
    step_paused: (v) => isNonEmptyStr(v.execution_id) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonNegInt(v.step_index) &&
        isStr(v.reason),
    precondition_check: (v) => isNonEmptyStr(v.workflow_id) &&
        isStr(v.verdict) && (v.verdict === 'pass' || v.verdict === 'fail') &&
        isStr(v.expression) &&
        (v.reason === undefined || isStr(v.reason)),
    postcondition_check: (v) => isNonEmptyStr(v.workflow_id) &&
        isStr(v.verdict) && (v.verdict === 'pass' || v.verdict === 'fail') &&
        isStr(v.expression) &&
        (v.reason === undefined || isStr(v.reason)),
    commitment_broken: (v) => isNonEmptyStr(v.charter_id) &&
        isNonEmptyStr(v.obligation_name) &&
        isNonEmptyStr(v.workflow_id) &&
        isNonEmptyStr(v.execution_id) &&
        (v.evidence === undefined || isStr(v.evidence)),
};
/**
 * Sound type guard for the EngineEvent discriminated union. Validates:
 *   - type ∈ ENGINE_EVENT_TYPES
 *   - ts_ms is a finite non-negative number
 *   - the per-variant required fields are present + correctly typed
 *
 * Codex P1 fold 2026-05-03: previously this guard only validated type +
 * ts_ms, so payloads like `{ type: 'workflow_started', ts_ms: 1 }` (missing
 * workflow_id + execution_id) passed as EngineEvent. That was unsound —
 * downstream renderers crash when reading missing fields. The variant
 * validator above closes the hole.
 */
export function isEngineEvent(value) {
    if (typeof value !== 'object' || value === null)
        return false;
    const v = value;
    if (typeof v.type !== 'string' || !ENGINE_EVENT_TYPES.has(v.type))
        return false;
    if (typeof v.ts_ms !== 'number' || !Number.isFinite(v.ts_ms) || v.ts_ms < 0)
        return false;
    const validator = VARIANT_VALIDATORS[v.type];
    return validator(v);
}
//# sourceMappingURL=engine-event.js.map