/**
 * RendererRegistry — D2 step 4 of vertical slice.
 *
 * Maps EngineEventType → Renderer (pure (event, ctx) → string). Defaults
 * are registered in the constructor unless `skip_defaults: true`. Operator
 * overrides via `register(type, fn)` replace the default.
 *
 * Renderers consume EngineEvent + RenderContext and produce a single line
 * of human-readable terminal output. They MUST be pure: no I/O, no closure
 * over mutable state — this matches the engine's replay-safety invariant
 * (replay the JSONL event stream → identical terminal transcript).
 *
 * Per softened I-NPD-1: registry exposes hasOverride() + getRegisteredTypes()
 * so the audit trail can record which event types were rendered with the
 * default vs an operator-supplied function.
 */

import {
  ENGINE_EVENT_TYPES,
  type EngineEvent,
  type EngineEventType,
  type RenderContext,
  type RoutingDecisionEvent,
  type WorkflowStartedEvent,
  type WorkflowCompletedEvent,
  type WorkflowFailedEvent,
  type ArtifactRegisteredEvent,
  type PolicyDecisionEvent,
  type StepStartedEvent,
  type StepCompletedEvent,
  type PatternProposedEvent,
  type ProposalApprovedEvent,
  type ProposalRejectedEvent,
  type ApprovalRequestedEvent,
  type ApprovalGrantedEvent,
  type ApprovalDeniedEvent,
  type ApprovalAlreadyHandledEvent,
  type WorkflowRollbackStartedEvent,
  type StepCompensatedEvent,
  type StepCompensationFailedEvent,
  type WorkflowRollbackCompleteEvent,
  type WorkflowRollbackPartialEvent,
  type WorkflowEscalatedEvent,
  type StepPausedEvent,
} from '../types/engine-event.js'

export type Renderer<T extends EngineEvent = EngineEvent> = (event: T, ctx: RenderContext) => string

/**
 * Map an EngineEventType discriminator to its specific event variant — used
 * by the strongly-typed register() overload (codex P2.1 fold 2026-05-03).
 */
export type EventByType<T extends EngineEventType> = Extract<EngineEvent, { type: T }>

/** Renderer typed against a specific event variant (used by register()). */
export type RendererForType<T extends EngineEventType> = Renderer<EventByType<T>>

export interface RendererRegistryOptions {
  /** Skip default renderer registration. Useful for tests / strict mode. */
  readonly skip_defaults?: boolean
}

/**
 * Sanitize a string before injecting into terminal output. Strips ASCII
 * control bytes (0x00-0x1F, 0x7F) — codex P2.2 fold 2026-05-03 closes the
 * gap where a cell containing `\n`, `\r`, or terminal escapes could split
 * or decorate the founder transcript.
 */
function sanitizeForTerminal(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/[\x00-\x1F\x7F]/g, '?')
}

/** Resolve the H-Sutra cell prefix for an event line — empty string if absent. */
function cellPrefix(ctx: RenderContext): string {
  const cell = ctx.hsutra?.cell
  if (!cell) return ''
  return `[${sanitizeForTerminal(cell)}] `
}

/** Compact 8-char prefix of a sha for human-friendly display. */
function shortSha(sha: string): string {
  return sha.length >= 8 ? sha.slice(0, 8) : sha
}

// -----------------------------------------------------------------------------
// 8 default renderers — pure functions of (event, ctx) → string
// -----------------------------------------------------------------------------

export const defaultRenderRoutingDecision: Renderer<RoutingDecisionEvent> = (e, ctx) => {
  const prefix = cellPrefix(ctx)
  const wf = e.workflow_id ?? '∅'
  const trig = e.trigger_id ? ` trigger=${e.trigger_id}` : ''
  const turn = e.turn_id ? ` turn=${e.turn_id}` : ''
  return `${prefix}[router] ${e.mode} → ${wf}${trig}${turn} (${e.attempts_count} attempt${e.attempts_count === 1 ? '' : 's'})`
}

export const defaultRenderWorkflowStarted: Renderer<WorkflowStartedEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] started ${e.execution_id}`
}

export const defaultRenderWorkflowCompleted: Renderer<WorkflowCompletedEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] completed ${e.execution_id} in ${e.duration_ms}ms`
}

export const defaultRenderWorkflowFailed: Renderer<WorkflowFailedEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] FAILED ${e.execution_id}: ${e.reason}`
}

export const defaultRenderArtifactRegistered: Renderer<ArtifactRegisteredEvent> = (e, ctx) => {
  const producer = e.producer_execution_id ? ` ← ${e.producer_execution_id}` : ''
  return `${cellPrefix(ctx)}[catalog] ${e.domain_id} sha:${shortSha(e.content_sha256)} (${e.asset_kind})${producer}`
}

export const defaultRenderPolicyDecision: Renderer<PolicyDecisionEvent> = (e, ctx) => {
  const wf = e.workflow_id ? ` wf=${e.workflow_id}` : ''
  const reason = e.reason ? ` — ${e.reason}` : ''
  return `${cellPrefix(ctx)}[policy] ${e.verdict} rule=${e.rule_id}${wf}${reason}`
}

export const defaultRenderStepStarted: Renderer<StepStartedEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] step ${e.step_index}/${e.step_count}: ${e.step_id}`
}

export const defaultRenderStepCompleted: Renderer<StepCompletedEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] step ${e.step_index}/${e.step_count} ✓ ${e.step_id} in ${e.duration_ms}ms`
}

// -----------------------------------------------------------------------------
// SPEC v1.2 §4.6 — organic emergence v1 renderers
// -----------------------------------------------------------------------------

export const defaultRenderPatternProposed: Renderer<PatternProposedEvent> = (e, ctx) => {
  const phrase = sanitizeForTerminal(e.normalized_phrase)
  return `${cellPrefix(ctx)}[native] pattern ${e.pattern_id} seen ${e.evidence_count}×: "${phrase}". Type "approve ${e.pattern_id}" to register, or "reject ${e.pattern_id}" to drop.`
}

export const defaultRenderProposalApproved: Renderer<ProposalApprovedEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[native] approved ${e.pattern_id}. Registered ${e.registered_workflow_id} + ${e.registered_trigger_id}. Next match routes deterministically.`
}

export const defaultRenderProposalRejected: Renderer<ProposalRejectedEvent> = (e, ctx) => {
  const reason = e.reason ? `: ${sanitizeForTerminal(e.reason)}` : ''
  return `${cellPrefix(ctx)}[native] rejected ${e.pattern_id}${reason}.`
}

// -----------------------------------------------------------------------------
// v1.3.0 Wave 2 — step-level approval gate renderers (codex W2 fold).
//
// Style consistent with pattern_proposed / proposal_approved / proposal_rejected
// above. The four lifecycle events trace founder-in-the-loop step approval:
// REQUESTED (executor paused) → GRANTED (resume) | DENIED (terminate) | ALREADY_HANDLED
// (stale duplicate approve/reject for an execution past its decision boundary).
// -----------------------------------------------------------------------------

export const defaultRenderApprovalRequested: Renderer<ApprovalRequestedEvent> = (e, ctx) => {
  const summary = sanitizeForTerminal(e.prompt_summary)
  return `${cellPrefix(ctx)}[${e.workflow_id}] PAUSED ${e.execution_id} at step ${e.step_index}: ${summary}. Type "approve ${e.execution_id}" to resume or "reject ${e.execution_id} <reason>" to terminate.`
}

export const defaultRenderApprovalGranted: Renderer<ApprovalGrantedEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] approved ${e.execution_id} at step ${e.step_index} — resuming.`
}

export const defaultRenderApprovalDenied: Renderer<ApprovalDeniedEvent> = (e, ctx) => {
  const reason = sanitizeForTerminal(e.reason)
  return `${cellPrefix(ctx)}[${e.workflow_id}] DENIED ${e.execution_id} at step ${e.step_index}: ${reason}`
}

export const defaultRenderApprovalAlreadyHandled: Renderer<ApprovalAlreadyHandledEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] approval for ${e.execution_id} (step ${e.step_index}) was already decided at ${e.originally_decided_at_ms} — no-op.`
}

// -----------------------------------------------------------------------------
// v1.3.0 Wave 4 — on_failure machinery renderers (codex W4 fold).
//
// Style consistent with W2 approval-gate renderers above. Seven events trace
// the pause/rollback/escalate lifecycles.
// -----------------------------------------------------------------------------

export const defaultRenderWorkflowRollbackStarted: Renderer<WorkflowRollbackStartedEvent> = (e, ctx) => {
  const reason = sanitizeForTerminal(e.reason)
  return `${cellPrefix(ctx)}[${e.workflow_id}] ROLLBACK ${e.execution_id} started: ${reason}`
}

export const defaultRenderStepCompensated: Renderer<StepCompensatedEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] step ${e.step_index} compensated ✓ in ${e.duration_ms}ms`
}

export const defaultRenderStepCompensationFailed: Renderer<StepCompensationFailedEvent> = (e, ctx) => {
  const reason = sanitizeForTerminal(e.reason)
  return `${cellPrefix(ctx)}[${e.workflow_id}] step ${e.step_index} compensation FAILED: ${reason}`
}

export const defaultRenderWorkflowRollbackComplete: Renderer<WorkflowRollbackCompleteEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] ROLLBACK ${e.execution_id} complete (${e.steps_compensated} compensated)`
}

export const defaultRenderWorkflowRollbackPartial: Renderer<WorkflowRollbackPartialEvent> = (e, ctx) => {
  return `${cellPrefix(ctx)}[${e.workflow_id}] ROLLBACK ${e.execution_id} partial: ${e.steps_compensated} compensated, ${e.steps_failed} failed — review out-of-band`
}

export const defaultRenderWorkflowEscalated: Renderer<WorkflowEscalatedEvent> = (e, ctx) => {
  const reason = sanitizeForTerminal(e.reason)
  return `${cellPrefix(ctx)}[${e.workflow_id}] ESCALATED ${e.execution_id}: ${reason} — terminal, review out-of-band.`
}

export const defaultRenderStepPaused: Renderer<StepPausedEvent> = (e, ctx) => {
  const reason = sanitizeForTerminal(e.reason)
  return `${cellPrefix(ctx)}[${e.workflow_id}] PAUSED ${e.execution_id} at step ${e.step_index}: ${reason}. Call resumeFromPause("${e.execution_id}") to continue.`
}

/** Map of every EngineEventType to its default renderer. Frozen at module load. */
export const DEFAULT_RENDERERS: Readonly<Record<EngineEventType, Renderer>> = Object.freeze({
  routing_decision: defaultRenderRoutingDecision as Renderer,
  workflow_started: defaultRenderWorkflowStarted as Renderer,
  workflow_completed: defaultRenderWorkflowCompleted as Renderer,
  workflow_failed: defaultRenderWorkflowFailed as Renderer,
  artifact_registered: defaultRenderArtifactRegistered as Renderer,
  policy_decision: defaultRenderPolicyDecision as Renderer,
  step_started: defaultRenderStepStarted as Renderer,
  step_completed: defaultRenderStepCompleted as Renderer,
  pattern_proposed: defaultRenderPatternProposed as Renderer,
  proposal_approved: defaultRenderProposalApproved as Renderer,
  proposal_rejected: defaultRenderProposalRejected as Renderer,
  approval_requested: defaultRenderApprovalRequested as Renderer,
  approval_granted: defaultRenderApprovalGranted as Renderer,
  approval_denied: defaultRenderApprovalDenied as Renderer,
  approval_already_handled: defaultRenderApprovalAlreadyHandled as Renderer,
  workflow_rollback_started: defaultRenderWorkflowRollbackStarted as Renderer,
  step_compensated: defaultRenderStepCompensated as Renderer,
  step_compensation_failed: defaultRenderStepCompensationFailed as Renderer,
  workflow_rollback_complete: defaultRenderWorkflowRollbackComplete as Renderer,
  workflow_rollback_partial: defaultRenderWorkflowRollbackPartial as Renderer,
  workflow_escalated: defaultRenderWorkflowEscalated as Renderer,
  step_paused: defaultRenderStepPaused as Renderer,
})

// -----------------------------------------------------------------------------
// RendererRegistry
// -----------------------------------------------------------------------------

export class RendererRegistry {
  private readonly map = new Map<EngineEventType, Renderer>()
  private readonly overrides = new Set<EngineEventType>()
  private readonly defaultsEnabled: boolean

  constructor(options: RendererRegistryOptions = {}) {
    this.defaultsEnabled = !options.skip_defaults
    if (this.defaultsEnabled) {
      for (const t of ENGINE_EVENT_TYPES) {
        this.map.set(t, DEFAULT_RENDERERS[t])
      }
    }
  }

  /**
   * Register or override a Renderer for an EngineEventType.
   *
   * Codex P2.1 fold 2026-05-03: the type parameter is the discriminator
   * itself, and the renderer must accept the corresponding event variant
   * (`Renderer<EventByType<T>>`). This is enforced at compile time —
   * `register('workflow_started', routingDecisionRenderer)` is now a TS
   * error rather than silently casting at runtime.
   *
   * Throws TypeError on unknown event_type or non-function renderer.
   */
  register<T extends EngineEventType>(event_type: T, renderer: RendererForType<T>): void {
    if (!ENGINE_EVENT_TYPES.has(event_type)) {
      throw new TypeError(`RendererRegistry.register: unknown event_type "${event_type}"`)
    }
    if (typeof renderer !== 'function') {
      throw new TypeError(`RendererRegistry.register: renderer for "${event_type}" must be a function`)
    }
    this.map.set(event_type, renderer as Renderer)
    this.overrides.add(event_type)
  }

  /**
   * Remove an override. If defaults are enabled, the default for that
   * event_type is restored; otherwise the entry is removed entirely.
   * Returns true iff an override was removed.
   */
  unregister(event_type: EngineEventType): boolean {
    if (!this.overrides.has(event_type)) return false
    this.overrides.delete(event_type)
    if (this.defaultsEnabled) {
      this.map.set(event_type, DEFAULT_RENDERERS[event_type])
    } else {
      this.map.delete(event_type)
    }
    return true
  }

  /** Returns the active Renderer for an event_type (default or override), or null. */
  resolve(event_type: EngineEventType): Renderer | null {
    return this.map.get(event_type) ?? null
  }

  /** Did the operator install an override for this event_type? */
  hasOverride(event_type: EngineEventType): boolean {
    return this.overrides.has(event_type)
  }

  /** All EngineEventTypes with an active renderer (default or override). */
  getRegisteredTypes(): ReadonlyArray<EngineEventType> {
    return [...this.map.keys()]
  }

  /**
   * Render an event. Returns the rendered string, or null if no renderer
   * is registered for that event's type (the engine should treat null as
   * "skip this event" — never throw at the founder's terminal).
   *
   * If the resolved renderer throws, the exception is caught and the event
   * is rendered as a fallback line so a buggy operator override never
   * crashes the engine's render loop.
   */
  render(event: EngineEvent, ctx: RenderContext = {}): string | null {
    const renderer = this.resolve(event.type)
    if (!renderer) return null
    try {
      return renderer(event, ctx)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err)
      return `${cellPrefix(ctx)}[render-error:${event.type}] ${errorMessage}`
    }
  }
}
