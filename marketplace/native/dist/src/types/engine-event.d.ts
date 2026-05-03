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
export type EngineEventType = 'routing_decision' | 'workflow_started' | 'workflow_completed' | 'workflow_failed' | 'artifact_registered' | 'policy_decision' | 'step_started' | 'step_completed' | 'pattern_proposed' | 'proposal_approved' | 'proposal_rejected';
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
export type EngineEvent = RoutingDecisionEvent | WorkflowStartedEvent | WorkflowCompletedEvent | WorkflowFailedEvent | ArtifactRegisteredEvent | PolicyDecisionEvent | StepStartedEvent | StepCompletedEvent | PatternProposedEvent | ProposalApprovedEvent | ProposalRejectedEvent;
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