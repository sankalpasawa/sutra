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
    constructor(options?: NativeEngineOptions);
    /** Begin watching the H-Sutra log + processing events. Idempotent. */
    start(): void;
    /** Stop watching + release resources. Idempotent. */
    stop(): void;
    /**
     * Process one founder event end-to-end:
     *   1. Router.route → RoutingDecision
     *   2. Emit routing_decision event → render line
     *   3. If matched: Workflow Engine executes step_graph
     *   4. Emit each workflow/step event → render line
     *
     * Returns the count of EngineEvents emitted (useful for tests + telemetry).
     */
    handleHSutraEvent(evt: HSutraEvent): number;
    /**
     * Public helper: run a single founder turn synchronously (no log file
     * round-trip). Used by tests + the v1.1.0 demo path.
     */
    ingest(evt: HSutraEvent): number;
    /** Lookup the Charter that operationalizes a Workflow (v1.1.0 starter map). */
    ownerCharterOf(workflowId: string): string | undefined;
    private emitEvent;
}
/** Convenience builder for the v1.1.0 default engine wiring. */
export declare function createDefaultEngine(options?: NativeEngineOptions): NativeEngine;
//# sourceMappingURL=native-engine.d.ts.map