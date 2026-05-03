/**
 * Router — D2 step 2 of vertical slice.
 *
 * Maps events (founder_input via H-Sutra, cron tick, file_drop, webhook)
 * to target Workflows via registered TriggerSpecs. First match wins (in
 * registration order). When no deterministic match, optionally falls back
 * to an LLM classifier (per softened I-NPD-1).
 *
 * Per founder direction 2026-05-02 + C8: LLM fallback uses claude --bare
 * subprocess (subscription auth). Wiring is dependency-injected so tests
 * can stub without spawning subprocess.
 *
 * Every routing decision emits a RoutingDecision audit record. Production
 * wires these into the OpenTelemetry emitter (D2 step 4); v1.0 here just
 * collects in-memory + optionally appends to a JSONL sink.
 *
 * Replay determinism: deterministic matches ARE bit-identical replayable.
 * LLM-fallback decisions ARE replayable IF the LLM provider supports
 * temperature=0 + same prompt_hash → same response. v1.0 stores prompt
 * hash + model id; replay verification is D5 territory.
 */
import { type Predicate, type TriggerEventType, type TriggerSpec } from '../types/trigger-spec.js';
import type { RoutingDecision } from '../types/routing-decision.js';
import type { HSutraEvent } from '../types/h-sutra-event.js';
/**
 * Optional async LLM fallback. Returns the workflow_id to dispatch, or
 * null if the LLM declined. Implementations MUST be deterministic-shaped:
 * call with temperature=0 (or equivalent) so prompt_hash → same response.
 *
 * v1.0 production wiring: a thin adapter that builds the prompt from event
 * + registered triggers, spawns claude --bare, parses the response.
 * Tests inject stubs that map specific events → specific workflow_ids.
 */
export type LLMFallback = (event: HSutraEvent | null, input_text: string, triggers: ReadonlyArray<TriggerSpec>) => Promise<{
    workflow_id: string | null;
    prompt_hash: string;
    model: string;
}>;
export interface RouterOptions {
    /** Inject the LLM fallback. When omitted, no-match returns mode='no-match'. */
    readonly llm_fallback?: LLMFallback;
    /** Optional sink callback for audit records (production: append to JSONL). */
    readonly on_decision?: (decision: RoutingDecision) => void;
}
export interface RouteRequest {
    /** The event_type to route under. */
    readonly event_type: TriggerEventType;
    /** Raw input text — used by predicates like contains/matches. */
    readonly input_text?: string;
    /** Optional full H-Sutra event. */
    readonly hsutra?: HSutraEvent;
}
export declare class Router {
    private triggers;
    private llmFallback;
    private onDecision;
    private decisionLog;
    constructor(options?: RouterOptions);
    /**
     * Register a TriggerSpec. Throws TypeError on malformed input.
     * Order matters — first-match-wins during route().
     * Spec is deep-frozen on registration (caller cannot mutate it later).
     */
    registerTrigger(spec: TriggerSpec): void;
    /**
     * Replace registered triggers wholesale. Used by daemon reload paths.
     * Validates each input AND rejects the whole batch on duplicate ids.
     * Each spec is deep-frozen.
     */
    setTriggers(specs: ReadonlyArray<TriggerSpec>): void;
    unregisterTrigger(trigger_id: string): boolean;
    getRegisteredTriggers(): ReadonlyArray<TriggerSpec>;
    getDecisionLog(): ReadonlyArray<RoutingDecision>;
    /**
     * Run the deterministic predicate loop. Pure — does NOT record. Used by
     * both route() and routeAsync() so each public-method invocation produces
     * exactly one audit record (codex P1 fold 2026-05-03).
     */
    private _evaluateTriggers;
    /**
     * Synchronous deterministic-only route. Returns a decision with mode=
     * 'exact' on match, mode='no-match' otherwise. Does NOT invoke the LLM
     * fallback even if configured (caller must use routeAsync for that).
     * Emits exactly one audit record.
     */
    route(req: RouteRequest): RoutingDecision;
    /**
     * Async route — deterministic match first; if none AND llm_fallback is
     * configured, invoke the fallback. Emits exactly one audit record per
     * call (codex P1 fold 2026-05-03). If the fallback throws, an audit
     * record with mode='no-match' + an error attempt is recorded BEFORE the
     * exception is re-thrown, so replay can see the attempted invocation.
     */
    routeAsync(req: RouteRequest): Promise<RoutingDecision>;
    private recordDecision;
}
/**
 * Helper for LLM-fallback implementations: deterministic prompt hash.
 * Implementations should compute this BEFORE calling claude --bare so the
 * audit record can be written even if the LLM call fails.
 */
export declare function computePromptHash(prompt: string): string;
/**
 * Helper for tests + production: build a deterministic prompt for the LLM
 * fallback. Pinned shape so prompt_hash is stable across runs.
 */
export declare function buildFallbackPrompt(event_summary: string, triggers: ReadonlyArray<TriggerSpec>): string;
export type { Predicate, TriggerSpec, RoutingDecision };
//# sourceMappingURL=router.d.ts.map