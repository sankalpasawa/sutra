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
import { type EngineEvent, type EngineEventType, type RenderContext, type RoutingDecisionEvent, type WorkflowStartedEvent, type WorkflowCompletedEvent, type WorkflowFailedEvent, type ArtifactRegisteredEvent, type PolicyDecisionEvent, type StepStartedEvent, type StepCompletedEvent, type PatternProposedEvent, type ProposalApprovedEvent, type ProposalRejectedEvent } from '../types/engine-event.js';
export type Renderer<T extends EngineEvent = EngineEvent> = (event: T, ctx: RenderContext) => string;
/**
 * Map an EngineEventType discriminator to its specific event variant — used
 * by the strongly-typed register() overload (codex P2.1 fold 2026-05-03).
 */
export type EventByType<T extends EngineEventType> = Extract<EngineEvent, {
    type: T;
}>;
/** Renderer typed against a specific event variant (used by register()). */
export type RendererForType<T extends EngineEventType> = Renderer<EventByType<T>>;
export interface RendererRegistryOptions {
    /** Skip default renderer registration. Useful for tests / strict mode. */
    readonly skip_defaults?: boolean;
}
export declare const defaultRenderRoutingDecision: Renderer<RoutingDecisionEvent>;
export declare const defaultRenderWorkflowStarted: Renderer<WorkflowStartedEvent>;
export declare const defaultRenderWorkflowCompleted: Renderer<WorkflowCompletedEvent>;
export declare const defaultRenderWorkflowFailed: Renderer<WorkflowFailedEvent>;
export declare const defaultRenderArtifactRegistered: Renderer<ArtifactRegisteredEvent>;
export declare const defaultRenderPolicyDecision: Renderer<PolicyDecisionEvent>;
export declare const defaultRenderStepStarted: Renderer<StepStartedEvent>;
export declare const defaultRenderStepCompleted: Renderer<StepCompletedEvent>;
export declare const defaultRenderPatternProposed: Renderer<PatternProposedEvent>;
export declare const defaultRenderProposalApproved: Renderer<ProposalApprovedEvent>;
export declare const defaultRenderProposalRejected: Renderer<ProposalRejectedEvent>;
/** Map of every EngineEventType to its default renderer. Frozen at module load. */
export declare const DEFAULT_RENDERERS: Readonly<Record<EngineEventType, Renderer>>;
export declare class RendererRegistry {
    private readonly map;
    private readonly overrides;
    private readonly defaultsEnabled;
    constructor(options?: RendererRegistryOptions);
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
    register<T extends EngineEventType>(event_type: T, renderer: RendererForType<T>): void;
    /**
     * Remove an override. If defaults are enabled, the default for that
     * event_type is restored; otherwise the entry is removed entirely.
     * Returns true iff an override was removed.
     */
    unregister(event_type: EngineEventType): boolean;
    /** Returns the active Renderer for an event_type (default or override), or null. */
    resolve(event_type: EngineEventType): Renderer | null;
    /** Did the operator install an override for this event_type? */
    hasOverride(event_type: EngineEventType): boolean;
    /** All EngineEventTypes with an active renderer (default or override). */
    getRegisteredTypes(): ReadonlyArray<EngineEventType>;
    /**
     * Render an event. Returns the rendered string, or null if no renderer
     * is registered for that event's type (the engine should treat null as
     * "skip this event" — never throw at the founder's terminal).
     *
     * If the resolved renderer throws, the exception is caught and the event
     * is rendered as a fallback line so a buggy operator override never
     * crashes the engine's render loop.
     */
    render(event: EngineEvent, ctx?: RenderContext): string | null;
}
//# sourceMappingURL=renderer-registry.d.ts.map