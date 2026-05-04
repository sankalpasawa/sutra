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

import type { HSutraEvent } from './h-sutra-event.js'

export type EngineEventType =
  | 'routing_decision'
  | 'workflow_started'
  | 'workflow_completed'
  | 'workflow_failed'
  | 'artifact_registered'
  | 'policy_decision'
  | 'step_started'
  | 'step_completed'
  | 'pattern_proposed'
  | 'proposal_approved'
  | 'proposal_rejected'
  | 'approval_requested'
  | 'approval_granted'
  | 'approval_denied'
  | 'approval_already_handled'
  | 'workflow_rollback_started'
  | 'step_compensated'
  | 'step_compensation_failed'
  | 'workflow_rollback_complete'
  | 'workflow_rollback_partial'
  | 'workflow_escalated'
  | 'step_paused'

/** Runtime allow-list mirroring EngineEventType — kept in sync. */
export const ENGINE_EVENT_TYPES: ReadonlySet<EngineEventType> = new Set([
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
])

export interface RoutingDecisionEvent {
  readonly type: 'routing_decision'
  readonly ts_ms: number
  readonly turn_id: string | null
  readonly mode: 'exact' | 'llm-fallback' | 'no-match'
  readonly workflow_id: string | null
  readonly trigger_id: string | null
  readonly attempts_count: number
}

export interface WorkflowStartedEvent {
  readonly type: 'workflow_started'
  readonly ts_ms: number
  readonly workflow_id: string
  readonly execution_id: string
}

export interface WorkflowCompletedEvent {
  readonly type: 'workflow_completed'
  readonly ts_ms: number
  readonly workflow_id: string
  readonly execution_id: string
  readonly duration_ms: number
}

export interface WorkflowFailedEvent {
  readonly type: 'workflow_failed'
  readonly ts_ms: number
  readonly workflow_id: string
  readonly execution_id: string
  readonly reason: string
}

export interface ArtifactRegisteredEvent {
  readonly type: 'artifact_registered'
  readonly ts_ms: number
  readonly domain_id: string
  readonly content_sha256: string
  readonly asset_kind: string
  readonly producer_execution_id?: string
}

export interface PolicyDecisionEvent {
  readonly type: 'policy_decision'
  readonly ts_ms: number
  readonly verdict: 'ALLOW' | 'DENY'
  readonly rule_id: string
  readonly workflow_id?: string
  readonly reason?: string
}

export interface StepStartedEvent {
  readonly type: 'step_started'
  readonly ts_ms: number
  readonly workflow_id: string
  readonly execution_id: string
  readonly step_id: string
  readonly step_index: number
  readonly step_count: number
}

export interface StepCompletedEvent {
  readonly type: 'step_completed'
  readonly ts_ms: number
  readonly workflow_id: string
  readonly execution_id: string
  readonly step_id: string
  readonly step_index: number
  readonly step_count: number
  readonly duration_ms: number
}

/**
 * Organic emergence v1 events (SPEC v1.2 §4.6) — emitted when the
 * pattern-detector surfaces a candidate or the founder approves/rejects via
 * the next-utterance command.
 */
export interface PatternProposedEvent {
  readonly type: 'pattern_proposed'
  readonly ts_ms: number
  readonly pattern_id: string
  readonly normalized_phrase: string
  readonly evidence_count: number
  readonly proposed_workflow_id: string
  readonly proposed_trigger_id: string
}

export interface ProposalApprovedEvent {
  readonly type: 'proposal_approved'
  readonly ts_ms: number
  readonly pattern_id: string
  readonly registered_workflow_id: string
  readonly registered_trigger_id: string
}

export interface ProposalRejectedEvent {
  readonly type: 'proposal_rejected'
  readonly ts_ms: number
  readonly pattern_id: string
  readonly reason: string
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
  readonly type: 'approval_requested'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly step_index: number
  /** Truncated step description (action, host if any, first ~200 chars of inputs[0].locator). */
  readonly prompt_summary: string
}

export interface ApprovalGrantedEvent {
  readonly type: 'approval_granted'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly step_index: number
}

export interface ApprovalDeniedEvent {
  readonly type: 'approval_denied'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly step_index: number
  /** Founder-supplied free-form rejection reason. */
  readonly reason: string
}

export interface ApprovalAlreadyHandledEvent {
  readonly type: 'approval_already_handled'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly step_index: number
  /** When the original decision (approve/reject) was committed to the ledger. */
  readonly originally_decided_at_ms: number
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
  readonly type: 'workflow_rollback_started'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  /** The originating step failure that triggered the rollback (1-based step_index). */
  readonly reason: string
}

export interface StepCompensatedEvent {
  readonly type: 'step_compensated'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly step_index: number
  readonly duration_ms: number
}

export interface StepCompensationFailedEvent {
  readonly type: 'step_compensation_failed'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly step_index: number
  readonly reason: string
}

export interface WorkflowRollbackCompleteEvent {
  readonly type: 'workflow_rollback_complete'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  /** Number of step compensations that ran successfully (may be 0 — best-effort). */
  readonly steps_compensated: number
}

export interface WorkflowRollbackPartialEvent {
  readonly type: 'workflow_rollback_partial'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly steps_compensated: number
  readonly steps_failed: number
}

export interface WorkflowEscalatedEvent {
  readonly type: 'workflow_escalated'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly reason: string
}

export interface StepPausedEvent {
  readonly type: 'step_paused'
  readonly ts_ms: number
  readonly execution_id: string
  readonly workflow_id: string
  readonly step_index: number
  readonly reason: string
}

export type EngineEvent =
  | RoutingDecisionEvent
  | WorkflowStartedEvent
  | WorkflowCompletedEvent
  | WorkflowFailedEvent
  | ArtifactRegisteredEvent
  | PolicyDecisionEvent
  | StepStartedEvent
  | StepCompletedEvent
  | PatternProposedEvent
  | ProposalApprovedEvent
  | ProposalRejectedEvent
  | ApprovalRequestedEvent
  | ApprovalGrantedEvent
  | ApprovalDeniedEvent
  | ApprovalAlreadyHandledEvent
  | WorkflowRollbackStartedEvent
  | StepCompensatedEvent
  | StepCompensationFailedEvent
  | WorkflowRollbackCompleteEvent
  | WorkflowRollbackPartialEvent
  | WorkflowEscalatedEvent
  | StepPausedEvent

// -----------------------------------------------------------------------------
// Per-variant validators (codex P1 fold 2026-05-03) — guard MUST validate the
// full union shape, not just the discriminator + ts_ms. Failing at intake is
// non-recoverable; render-time TypeError on a bad payload is worse.
// -----------------------------------------------------------------------------

const ROUTING_MODES: ReadonlySet<string> = new Set(['exact', 'llm-fallback', 'no-match'])
const POLICY_VERDICTS: ReadonlySet<string> = new Set(['ALLOW', 'DENY'])

function isStr(v: unknown): v is string { return typeof v === 'string' }
function isNonEmptyStr(v: unknown): v is string { return typeof v === 'string' && v.length > 0 }
function isStrOrNull(v: unknown): boolean { return v === null || typeof v === 'string' }
function isNonNegInt(v: unknown): v is number {
  return typeof v === 'number' && Number.isInteger(v) && v >= 0
}
function isFiniteNonNegNumber(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v) && v >= 0
}

const VARIANT_VALIDATORS: Record<EngineEventType, (v: Record<string, unknown>) => boolean> = {
  routing_decision: (v) =>
    isStrOrNull(v.turn_id) &&
    isStr(v.mode) && ROUTING_MODES.has(v.mode) &&
    isStrOrNull(v.workflow_id) &&
    isStrOrNull(v.trigger_id) &&
    isNonNegInt(v.attempts_count),
  workflow_started: (v) =>
    isNonEmptyStr(v.workflow_id) && isNonEmptyStr(v.execution_id),
  workflow_completed: (v) =>
    isNonEmptyStr(v.workflow_id) &&
    isNonEmptyStr(v.execution_id) &&
    isFiniteNonNegNumber(v.duration_ms),
  workflow_failed: (v) =>
    isNonEmptyStr(v.workflow_id) &&
    isNonEmptyStr(v.execution_id) &&
    isStr(v.reason),
  artifact_registered: (v) =>
    isNonEmptyStr(v.domain_id) &&
    isNonEmptyStr(v.content_sha256) &&
    isNonEmptyStr(v.asset_kind) &&
    (v.producer_execution_id === undefined || isNonEmptyStr(v.producer_execution_id)),
  policy_decision: (v) =>
    isStr(v.verdict) && POLICY_VERDICTS.has(v.verdict) &&
    isNonEmptyStr(v.rule_id) &&
    (v.workflow_id === undefined || isNonEmptyStr(v.workflow_id)) &&
    (v.reason === undefined || isStr(v.reason)),
  step_started: (v) =>
    isNonEmptyStr(v.workflow_id) &&
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.step_id) &&
    isNonNegInt(v.step_index) &&
    isNonNegInt(v.step_count),
  step_completed: (v) =>
    isNonEmptyStr(v.workflow_id) &&
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.step_id) &&
    isNonNegInt(v.step_index) &&
    isNonNegInt(v.step_count) &&
    isFiniteNonNegNumber(v.duration_ms),
  pattern_proposed: (v) =>
    isNonEmptyStr(v.pattern_id) &&
    isNonEmptyStr(v.normalized_phrase) &&
    isNonNegInt(v.evidence_count) &&
    isNonEmptyStr(v.proposed_workflow_id) &&
    isNonEmptyStr(v.proposed_trigger_id),
  proposal_approved: (v) =>
    isNonEmptyStr(v.pattern_id) &&
    isNonEmptyStr(v.registered_workflow_id) &&
    isNonEmptyStr(v.registered_trigger_id),
  proposal_rejected: (v) =>
    isNonEmptyStr(v.pattern_id) &&
    isStr(v.reason),
  approval_requested: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.step_index) &&
    isStr(v.prompt_summary),
  approval_granted: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.step_index),
  approval_denied: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.step_index) &&
    isStr(v.reason),
  approval_already_handled: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.step_index) &&
    isFiniteNonNegNumber(v.originally_decided_at_ms),
  workflow_rollback_started: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isStr(v.reason),
  step_compensated: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.step_index) &&
    isFiniteNonNegNumber(v.duration_ms),
  step_compensation_failed: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.step_index) &&
    isStr(v.reason),
  workflow_rollback_complete: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.steps_compensated),
  workflow_rollback_partial: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.steps_compensated) &&
    isNonNegInt(v.steps_failed),
  workflow_escalated: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isStr(v.reason),
  step_paused: (v) =>
    isNonEmptyStr(v.execution_id) &&
    isNonEmptyStr(v.workflow_id) &&
    isNonNegInt(v.step_index) &&
    isStr(v.reason),
}

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
export function isEngineEvent(value: unknown): value is EngineEvent {
  if (typeof value !== 'object' || value === null) return false
  const v = value as { type?: unknown; ts_ms?: unknown } & Record<string, unknown>
  if (typeof v.type !== 'string' || !ENGINE_EVENT_TYPES.has(v.type as EngineEventType)) return false
  if (typeof v.ts_ms !== 'number' || !Number.isFinite(v.ts_ms) || v.ts_ms < 0) return false
  const validator = VARIANT_VALIDATORS[v.type as EngineEventType]
  return validator(v)
}

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
  readonly now_ms?: number
  /** H-Sutra event for the same turn (when applicable). */
  readonly hsutra?: HSutraEvent | null
}
