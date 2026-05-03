/**
 * NativeEngine — v1.1.0 wires the D2 vertical slice into a single
 * subscribable runtime so SessionStart hook → engine.start() → founder
 * input → SUCCESS Execution flows end-to-end.
 *
 * Composition:
 *   HSutraConnector   → reads founder events from Sutra Core JSONL log
 *   Router            → maps events to TriggerSpec → target Workflow
 *   LiteExecutor      → walks the matched Workflow's step_graph
 *   ArtifactCatalog   → records cataloged outputs (optional)
 *   RendererRegistry  → prints terminal lines per EngineEvent
 *
 * Per softened I-NPD-1: every routing decision + workflow event flows
 * through a single emit() pipeline so audit/replay sees the same stream
 * a fresh subscriber would.
 *
 * Failure isolation: any per-event handler throw is caught + logged via
 * the on_error callback (defaults to console.error). The connector's own
 * listener-throw isolation (D2.1) keeps a buggy renderer from killing
 * the whole subscription.
 */
import type { Workflow } from '../primitives/workflow.js';
import type { TriggerSpec } from '../types/trigger-spec.js';
import type { HSutraEvent } from '../types/h-sutra-event.js';
import { HSutraConnector, type HSutraConnectorOptions } from './h-sutra-connector.js';
import { Router } from './router.js';
import { ArtifactCatalog, type ArtifactCatalogOptions } from './artifact-catalog.js';
import { RendererRegistry } from './renderer-registry.js';
import { type UserKitOptions } from '../persistence/user-kit.js';
import { type PatternDetectorOptions } from './pattern-detector.js';
export interface NativeEngineOptions {
    readonly connector_options?: HSutraConnectorOptions;
    readonly catalog_options?: ArtifactCatalogOptions;
    /** Replace the starter triggers + workflows. Default: load the v1.1.0 starter kit. */
    readonly triggers?: ReadonlyArray<TriggerSpec>;
    readonly workflows?: ReadonlyArray<Workflow>;
    /** Sink for rendered lines. Default: console.log. */
    readonly write?: (line: string) => void;
    /** Sink for non-fatal errors. Default: console.error. */
    readonly on_error?: (err: Error) => void;
    /** Enable the no-match → propose loop. Default reads SUTRA_NATIVE_PROPOSER. */
    readonly proposer_enabled?: boolean;
    /** UserKit storage opts (HOME override etc); shared by user-kit + ledger. */
    readonly user_kit_options?: UserKitOptions;
    /** Pattern-detector knobs (k_threshold, window_ms, etc). */
    readonly pattern_detector_options?: Partial<PatternDetectorOptions>;
    /** Skip loading user-kit primitives at boot. Default false. */
    readonly skip_user_kit?: boolean;
    /** Override clock for deterministic tests. */
    readonly now_ms?: () => number;
}
export declare class NativeEngine {
    readonly connector: HSutraConnector;
    readonly router: Router;
    readonly catalog: ArtifactCatalog;
    readonly renderer: RendererRegistry;
    private readonly workflowsById;
    private readonly write;
    private readonly onError;
    private executionCounter;
    private started;
    /**
     * v1.2.1: serialization queue. The connector delivers events synchronously
     * but handleHSutraEvent is now async (host-LLM dispatch may take seconds).
     * Without this chain, two founder turns could overlap and collide on
     * executionCounter / ledger state. Each event is appended to the chain so
     * they run sequentially even when the connector fires faster than dispatch
     * resolves. Codex master review (DIRECTIVE 1777839055) P1 fold.
     */
    private turnQueue;
    private readonly proposerEnabled;
    private readonly userKitOptions;
    private readonly patternDetectorOptions;
    private readonly nowMs;
    constructor(options?: NativeEngineOptions);
    /** Begin watching the H-Sutra log + processing events. Idempotent. */
    start(): void;
    /** Stop watching + release resources. Idempotent. */
    stop(): void;
    /**
     * v1.2.1: await the queue of in-flight turns from the live connector path.
     * Useful for tests that need to assert state after an async dispatch
     * completes (since `handleHSutraEvent` returns immediately to the listener
     * but the work continues on the queue chain).
     */
    drain(): Promise<void>;
    /**
     * Process one founder event end-to-end:
     *   1. Router.route → RoutingDecision
     *   2. Emit routing_decision event → render line
     *   3. If matched: Workflow Engine executes step_graph
     *   4. Emit each workflow/step event → render line
     *
     * Returns the count of EngineEvents emitted (useful for tests + telemetry).
     *
     * v1.2.1: async to support invoke_host_llm dispatch through executeWorkflow.
     */
    handleHSutraEvent(evt: HSutraEvent): Promise<number>;
    /** SPEC v1.2 §4.5(c) — proposer pass. Returns count of events emitted. */
    private runProposerPass;
    /**
     * SPEC v1.2 §4.5(b) — approve a pending proposal by pattern_id.
     *
     * Codex master P2.4 fold: ordering is now atomic-friendly:
     *   (1) Persist Workflow + TriggerSpec to user-kit (durable; survives restart)
     *   (2) Flip ledger status to 'approved' (audit truth)
     *   (3) Register trigger live + add workflow to in-memory map
     *   (4) Emit DecisionProvenance audit (P1.1 fold) + proposal_approved event
     *
     * On failure at any step the engine logs an error and returns early WITHOUT
     * emitting proposal_approved, so the founder never sees a confirmation that
     * is not backed by ledger state.
     */
    private applyApproval;
    /** SPEC v1.2 §4.5(b) — reject a pending proposal by pattern_id. */
    private applyRejection;
    /**
     * Public helper: run a single founder turn (no log file round-trip).
     * Used by tests + the v1.1.0 demo path.
     *
     * v1.2.1: async to forward host-LLM dispatch errors / completion ordering
     * from handleHSutraEvent's executeWorkflow await.
     */
    ingest(evt: HSutraEvent): Promise<number>;
    /** Lookup the Charter that operationalizes a Workflow (v1.1.0 starter map). */
    ownerCharterOf(workflowId: string): string | undefined;
    private emitEvent;
}
/** Convenience builder for the v1.1.0 default engine wiring. */
export declare function createDefaultEngine(options?: NativeEngineOptions): NativeEngine;
//# sourceMappingURL=native-engine.d.ts.map