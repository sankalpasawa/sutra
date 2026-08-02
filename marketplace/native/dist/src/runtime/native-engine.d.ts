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
import type { Charter } from '../primitives/charter.js';
import type { TriggerSpec } from '../types/trigger-spec.js';
import type { HSutraEvent } from '../types/h-sutra-event.js';
import { HSutraConnector, type HSutraConnectorOptions } from './h-sutra-connector.js';
import { Router } from './router.js';
import { ArtifactCatalog, type ArtifactCatalogOptions } from './artifact-catalog.js';
import { RendererRegistry } from './renderer-registry.js';
import { type UserKitOptions } from '../persistence/user-kit.js';
import { type PatternDetectorOptions } from './pattern-detector.js';
import { type PredicateRegistry } from './pnc-predicate.js';
export interface NativeEngineOptions {
    readonly connector_options?: HSutraConnectorOptions;
    readonly catalog_options?: ArtifactCatalogOptions;
    /** Replace the starter triggers + workflows. Default: load the v1.1.0 starter kit. */
    readonly triggers?: ReadonlyArray<TriggerSpec>;
    readonly workflows?: ReadonlyArray<Workflow>;
    /**
     * v1.3.0 W5 (codex W5 BLOCKER 3 fold). Replace the starter charters. Used by
     * the commitment_broken emission path: NativeEngine looks up Charter.obligations
     * by name when a workflow declares obligation_refs and fails. Default:
     * starter-kit charters via loadStarterKit().
     */
    readonly charters?: ReadonlyArray<Charter>;
    /**
     * v1.3.0 W5 — predicate atom registry for the PNC admission gate. Forwarded
     * to lite-executor as `pnc_registry`. Default: `BASELINE_PREDICATE_REGISTRY`
     * (always_true / always_false). Production deployments compose application-
     * specific atoms (`is_morning_window`, `weekly_window`, etc.) via Map
     * extension over the baseline.
     */
    readonly pnc_registry?: PredicateRegistry;
    /**
     * v1.3.0 W5 — frozen evaluation context passed to PNC atom evaluators.
     * Forwarded to lite-executor as `pnc_ctx`. Default: empty frozen object.
     * Window markers (e.g. { time_of_day, iso_week }) belong here, NOT inside
     * atom evaluator function bodies (codex W5 advisory E determinism — atoms
     * read pre-computed markers; never call Date.now/random/I/O).
     */
    readonly pnc_ctx?: Readonly<Record<string, unknown>>;
    /** Sink for rendered lines. Default: console.log. */
    readonly write?: (line: string) => void;
    /** Sink for non-fatal errors. Default: console.error. */
    readonly on_error?: (err: Error) => void;
    /**
     * v1.3.0 W6 — durable telemetry sink. When set, every emitted EngineEvent
     * is also persisted via appendTelemetry as a JSONL line under
     * `<telemetry_sink_path>/runtime/telemetry/events.jsonl` with per-event
     * fsync. Recovers seq monotonically across restart. When unset, behavior
     * is identical to v1.3.0-w5 (renderer-only).
     *
     * The path is the HOME root (NOT the events.jsonl path). Reuses the same
     * resolution as user-kit so a single $SUTRA_NATIVE_HOME drives both
     * primitives + telemetry storage.
     */
    readonly telemetry_sink_path?: string;
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
export interface ApprovalUtterance {
    readonly namespace: 'P' | 'E';
    readonly id: string;
    readonly action: 'approve' | 'reject';
    readonly reason?: string;
}
/**
 * Parse a founder utterance for approve/reject commands across ALL namespaces.
 *
 * Returns null when text doesn't match the approval grammar. Returns parsed
 * components when it does. Caller dispatches based on `namespace`:
 *   - 'P' → applyApproval / applyRejection (proposal-ledger)
 *   - 'E' → applyExecutionApproval / applyExecutionRejection (execution-approval-ledger)
 *
 * Codex W2 advisory C fold (2026-05-04): a single parser keeps the H-Sutra
 * surface coherent and lets unit tests verify "approve P-deadbeef" vs
 * "approve E-t1-1" with one set of regex assertions.
 */
export declare function parseApprovalUtterance(text: string): ApprovalUtterance | null;
export declare class NativeEngine {
    readonly connector: HSutraConnector;
    readonly router: Router;
    readonly catalog: ArtifactCatalog;
    readonly renderer: RendererRegistry;
    private readonly workflowsById;
    /**
     * v1.3.0 W5 — Charter map keyed by Charter.id, populated from starter-kit
     * (or options.charters override). Read by the commitment_broken emission
     * path on workflow_failed: looks up the operating Charter by id, walks its
     * obligations, matches against the failing workflow's obligation_refs, and
     * emits one event per match.
     */
    private readonly chartersById;
    /**
     * v1.3.0 W5 — predicate registry forwarded to lite-executor as `pnc_registry`
     * on every routed run. Default = BASELINE_PREDICATE_REGISTRY.
     */
    private readonly pncRegistry;
    /**
     * v1.3.0 W5 — frozen PNC evaluation context. Default = empty frozen object.
     */
    private readonly pncCtx;
    private readonly write;
    private readonly onError;
    /**
     * v1.3.0 W6 — when set, emitEvent also calls appendTelemetry with this
     * HOME root. Undefined → renderer-only path (v1.3.0-w5 behavior).
     */
    private readonly telemetrySinkPath;
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
     * v1.3.0 W2 (codex W2 BLOCKER 3 + advisory C/D fold) — `approve E-<id>`
     * branch.
     *
     * Loads the ExecutionApprovalRecord; on status='pending' flips to
     * 'approved', emits approval_granted, then resumes the workflow run via
     * resumeApproved. On any other status (already-approved, resumed,
     * rejected, terminal) emits approval_already_handled with the original
     * decided_at_ms — never throws (advisory D: stale approve is no-op,
     * distinguishable from "never existed").
     */
    private applyExecutionApproval;
    /**
     * v1.3.0 W2 — `reject E-<id> <reason>` branch.
     *
     * Loads the record; on pending flips to 'rejected', emits approval_denied
     * AND a workflow_failed (reason='approval_denied:<reason>') so the audit
     * trail shows the workflow terminated. On any other status emits
     * approval_already_handled (advisory D).
     */
    private applyExecutionRejection;
    /**
     * v1.3.0 W2 — resume an approved-and-paused execution.
     *
     * Looks up the original Workflow by workflow_id, then calls
     * executeWorkflowResume with resume_from_step_index = (paused_step_index - 1)
     * so the gated step IS the first step to run. The lite-executor bypass
     * skips its requires_approval gate exactly once.
     *
     * On completion (success or failure), markResumed flips the ledger entry
     * to 'resumed' so subsequent approve/reject for this execution returns
     * approval_already_handled.
     */
    private resumeApproved;
    /**
     * v1.3.0 W4 — programmatic resume of an on_failure='pause' execution.
     *
     * Called by callers / external surfaces (future `resume E-<id>` utterance
     * routing). Loads the ExecutionPauseRecord; on status='pending' continues
     * the workflow run from step_index+1 (the failed step is NOT re-run —
     * pause means "human took over, move on").
     *
     * Codex W4 advisory #3 mutual exclusion guards (CHECKED IN ORDER):
     *   1. No pause record on disk for execId          → throws (caller bug)
     *   2. Pause record status !== 'pending'           → throws (already
     *      resumed/terminalized — distinguishable from #4 case)
     *   3. Escalation record exists for SAME execId    → throws (mutually
     *      exclusive — escalated runs are terminal by design)
     *   4. Approval record exists for SAME execId in non-terminal state
     *      → throws (mixed transition — approval and pause are different
     *      gates and shouldn't combine accidentally)
     *
     * Returns the count of EngineEvents emitted by the resumed run (matches
     * the resumeApproved return contract).
     */
    resumeFromPause(execId: string): Promise<number>;
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
    /**
     * v1.3.0 W5 (codex W5 BLOCKER 3 fold) — emit commitment_broken events when
     * (a) a routed workflow fails AND (b) the workflow declares non-empty
     * obligation_refs AND (c) charter_id is set in execution context AND
     * (d) the named obligation exists on the Charter's obligations list.
     *
     * Per codex: workflow→obligation mapping is DECLARATIVE. We never infer from
     * step text. The match is a literal name comparison: workflow.obligation_refs
     * (Workflow primitive declaration) ∩ charter.obligations[].name (Charter
     * declaration). Each intersection emits one commitment_broken event.
     *
     * Skip rules:
     *   - charterId undefined         → no Charter context for this run; skip.
     *     (cmdRun direct path / no STARTER_WORKFLOW_CHARTER_MAP entry.)
     *   - obligation_refs empty       → workflow makes no Charter-level
     *     commitments; skip silently.
     *   - charter not loaded by id    → cross-reference failure; log + skip.
     *   - obligation_name not on charter → declared but missing from Charter;
     *     log + skip (the workflow promised something the Charter doesn't track).
     */
    private emitCommitmentBrokenIfApplicable;
    private emitEvent;
}
/** Convenience builder for the v1.1.0 default engine wiring. */
export declare function createDefaultEngine(options?: NativeEngineOptions): NativeEngine;
//# sourceMappingURL=native-engine.d.ts.map