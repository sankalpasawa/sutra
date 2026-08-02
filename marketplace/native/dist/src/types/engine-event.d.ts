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
import type { HSutraEvent } from './h-sutra-event.js';
export type EngineEventType = 'routing_decision' | 'workflow_started' | 'workflow_completed' | 'workflow_failed' | 'artifact_registered' | 'policy_decision' | 'step_started' | 'step_completed' | 'pattern_proposed' | 'proposal_approved' | 'proposal_rejected' | 'approval_requested' | 'approval_granted' | 'approval_denied' | 'approval_already_handled' | 'workflow_rollback_started' | 'step_compensated' | 'step_compensation_failed' | 'workflow_rollback_complete' | 'workflow_rollback_partial' | 'workflow_escalated' | 'step_paused' | 'precondition_check' | 'postcondition_check' | 'commitment_broken';
/** Runtime allow-list mirroring EngineEventType — kept in sync. */
export declare const ENGINE_EVENT_TYPES: ReadonlySet<EngineEventType>;
export interface RoutingDecisionEvent {
    readonly type: 'routing_decision';
    readonly ts_ms: number;
    readonly turn_id: string | null;
    readonly mode: 'exact' | 'llm-fallback' | 'no-match';
    readonly workflow_id: string | null;
    readonly trigger_id: string | null;
    readonly attempts_count: number;
}
export interface WorkflowStartedEvent {
    readonly type: 'workflow_started';
    readonly ts_ms: number;
    readonly workflow_id: string;
    readonly execution_id: string;
}
export interface WorkflowCompletedEvent {
    readonly type: 'workflow_completed';
    readonly ts_ms: number;
    readonly workflow_id: string;
    readonly execution_id: string;
    readonly duration_ms: number;
}
export interface WorkflowFailedEvent {
    readonly type: 'workflow_failed';
    readonly ts_ms: number;
    readonly workflow_id: string;
    readonly execution_id: string;
    readonly reason: string;
}
export interface ArtifactRegisteredEvent {
    readonly type: 'artifact_registered';
    readonly ts_ms: number;
    readonly domain_id: string;
    readonly content_sha256: string;
    readonly asset_kind: string;
    readonly producer_execution_id?: string;
}
export interface PolicyDecisionEvent {
    readonly type: 'policy_decision';
    readonly ts_ms: number;
    readonly verdict: 'ALLOW' | 'DENY';
    readonly rule_id: string;
    readonly workflow_id?: string;
    readonly reason?: string;
}
export interface StepStartedEvent {
    readonly type: 'step_started';
    readonly ts_ms: number;
    readonly workflow_id: string;
    readonly execution_id: string;
    readonly step_id: string;
    readonly step_index: number;
    readonly step_count: number;
}
export interface StepCompletedEvent {
    readonly type: 'step_completed';
    readonly ts_ms: number;
    readonly workflow_id: string;
    readonly execution_id: string;
    readonly step_id: string;
    readonly step_index: number;
    readonly step_count: number;
    readonly duration_ms: number;
}
/**
 * Organic emergence v1 events (SPEC v1.2 §4.6) — emitted when the
 * pattern-detector surfaces a candidate or the founder approves/rejects via
 * the next-utterance command.
 */
export interface PatternProposedEvent {
    readonly type: 'pattern_proposed';
    readonly ts_ms: number;
    readonly pattern_id: string;
    readonly normalized_phrase: string;
    readonly evidence_count: number;
    readonly proposed_workflow_id: string;
    readonly proposed_trigger_id: string;
}
export interface ProposalApprovedEvent {
    readonly type: 'proposal_approved';
    readonly ts_ms: number;
    readonly pattern_id: string;
    readonly registered_workflow_id: string;
    readonly registered_trigger_id: string;
}
export interface ProposalRejectedEvent {
    readonly type: 'proposal_rejected';
    readonly ts_ms: number;
    readonly pattern_id: string;
    readonly reason: string;
}
/**
 * v1.3.0 Wave 2 — step-level approval gate events (codex W2 BLOCKER 1+3 fold).
 *
 * Founder centerpiece: "workflow is shown, then approval from founder, like
 * how evolved that workflow should be from the steps point of view." The four
 * events below trace the lifecycle:
 *   - approval_requested        → executor paused at a step.requires_approval=true step
 *   - approval_granted          → founder typed `approve E-<id>` (resume)
 *   - approval_denied           → founder typed `reject E-<id> <reason>` (terminalize)
 *   - approval_already_handled  → stale `approve|reject E-<id>` for an already-decided execution
 *
 * Persistence is the canonical source of truth (see
 * src/persistence/execution-approval-ledger.ts mirroring proposal-ledger).
 * These events are the human-facing audit transcript; the ledger record is
 * the durable state machine.
 */
export interface ApprovalRequestedEvent {
    readonly type: 'approval_requested';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly step_index: number;
    /** Truncated step description (action, host if any, first ~200 chars of inputs[0].locator). */
    readonly prompt_summary: string;
}
export interface ApprovalGrantedEvent {
    readonly type: 'approval_granted';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly step_index: number;
}
export interface ApprovalDeniedEvent {
    readonly type: 'approval_denied';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly step_index: number;
    /** Founder-supplied free-form rejection reason. */
    readonly reason: string;
}
export interface ApprovalAlreadyHandledEvent {
    readonly type: 'approval_already_handled';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly step_index: number;
    /** When the original decision (approve/reject) was committed to the ledger. */
    readonly originally_decided_at_ms: number;
}
/**
 * v1.3.0 Wave 4 — on_failure machinery events (codex W4 advisory #2 fold).
 *
 * Seven events trace pause/rollback/escalate lifecycles with explicit failure
 * semantics for compensation. Distinct events (not overloaded workflow_failed)
 * because: (a) operator UX wants to see "rolled back, X compensated, Y failed"
 * separately from "step crashed", (b) replay/audit needs to disambiguate
 * "compensation succeeded but workflow ultimately failed" from "workflow
 * failed without rollback attempted".
 *
 * Mutual exclusion (codex W4 advisory #3): pause/escalate/rollback states are
 * mutually exclusive per execution — resumeFromPause rejects runs already
 * escalated or in rollback (NativeEngine guard, not type-level).
 */
export interface WorkflowRollbackStartedEvent {
    readonly type: 'workflow_rollback_started';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    /** The originating step failure that triggered the rollback (1-based step_index). */
    readonly reason: string;
}
export interface StepCompensatedEvent {
    readonly type: 'step_compensated';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly step_index: number;
    readonly duration_ms: number;
}
export interface StepCompensationFailedEvent {
    readonly type: 'step_compensation_failed';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly step_index: number;
    readonly reason: string;
}
export interface WorkflowRollbackCompleteEvent {
    readonly type: 'workflow_rollback_complete';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    /** Number of step compensations that ran successfully (may be 0 — best-effort). */
    readonly steps_compensated: number;
}
export interface WorkflowRollbackPartialEvent {
    readonly type: 'workflow_rollback_partial';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly steps_compensated: number;
    readonly steps_failed: number;
}
export interface WorkflowEscalatedEvent {
    readonly type: 'workflow_escalated';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly reason: string;
}
export interface StepPausedEvent {
    readonly type: 'step_paused';
    readonly ts_ms: number;
    readonly execution_id: string;
    readonly workflow_id: string;
    readonly step_index: number;
    readonly reason: string;
}
/**
 * v1.3.0 Wave 5 — admission + commitment gate events (codex W5 fold).
 *
 * Three events trace the PNC (Pre/Post/Commitment) axis:
 *
 *   - precondition_check  — emitted BEFORE workflow_started when the workflow
 *                           declares parseable preconditions. verdict='pass'
 *                           admits the run; verdict='fail' rejects WITHOUT
 *                           emitting workflow_started or any step events;
 *                           workflow_failed reason='precondition_failed:<expr>'
 *                           is emitted INSTEAD (codex W5 BLOCKER 1: failed
 *                           precondition is "not admitted", not "started then
 *                           failed").
 *
 *   - postcondition_check — emitted AFTER all steps complete and BEFORE
 *                           workflow_completed when the workflow declares
 *                           parseable postconditions. verdict='fail' converts
 *                           the run to workflow_failed reason=
 *                           'postcondition_failed:<expr>' INSTEAD of
 *                           workflow_completed.
 *
 *   - commitment_broken   — emitted when (a) workflow_failed fires AND
 *                           (b) the workflow declares non-empty obligation_refs
 *                           AND (c) the execution context has a charter_id
 *                           AND (d) the named obligation exists on the Charter.
 *                           NativeEngine looks up the Charter (it has charter
 *                           context for routed runs) and emits one event per
 *                           matched obligation (codex W5 BLOCKER 3: explicit
 *                           workflow→obligation mapping; no heuristics on step
 *                           text).
 */
export interface PreconditionCheckEvent {
    readonly type: 'precondition_check';
    readonly ts_ms: number;
    readonly workflow_id: string;
    readonly verdict: 'pass' | 'fail';
    readonly expression: string;
    readonly reason?: string;
}
export interface PostconditionCheckEvent {
    readonly type: 'postcondition_check';
    readonly ts_ms: number;
    readonly workflow_id: string;
    readonly verdict: 'pass' | 'fail';
    readonly expression: string;
    readonly reason?: string;
}
export interface CommitmentBrokenEvent {
    readonly type: 'commitment_broken';
    readonly ts_ms: number;
    readonly charter_id: string;
    readonly obligation_name: string;
    readonly workflow_id: string;
    readonly execution_id: string;
    /** Optional human-readable evidence (e.g. failure_reason) for audit. */
    readonly evidence?: string;
}
export type EngineEvent = RoutingDecisionEvent | WorkflowStartedEvent | WorkflowCompletedEvent | WorkflowFailedEvent | ArtifactRegisteredEvent | PolicyDecisionEvent | StepStartedEvent | StepCompletedEvent | PatternProposedEvent | ProposalApprovedEvent | ProposalRejectedEvent | ApprovalRequestedEvent | ApprovalGrantedEvent | ApprovalDeniedEvent | ApprovalAlreadyHandledEvent | WorkflowRollbackStartedEvent | StepCompensatedEvent | StepCompensationFailedEvent | WorkflowRollbackCompleteEvent | WorkflowRollbackPartialEvent | WorkflowEscalatedEvent | StepPausedEvent | PreconditionCheckEvent | PostconditionCheckEvent | CommitmentBrokenEvent;
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
export declare function isEngineEvent(value: unknown): value is EngineEvent;
/**
 * RenderContext — passed to every Renderer alongside the event so renderers
 * can include H-Sutra cell tags, pull a clock from the host, etc.
 *
 * Per founder direction "I want all telemetry": the H-Sutra event tied to
 * the same turn_id is available to renderers so they can prefix terminal
 * output with the cell coordinate ("[DIRECT·INBOUND] ...").
 */
export interface RenderContext {
    /** Host clock — pass a fixed value from tests for stable rendering. */
    readonly now_ms?: number;
    /** H-Sutra event for the same turn (when applicable). */
    readonly hsutra?: HSutraEvent | null;
}
//# sourceMappingURL=engine-event.d.ts.map