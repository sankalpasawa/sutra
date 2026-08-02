/**
 * LiteExecutor — v1.2.1 async Workflow.step_graph runner.
 *
 * Wave 2 lite path: takes a Workflow + Execution context, walks step_graph
 * in order, emits EngineEvents around each step, and produces a final
 * workflow_completed or workflow_failed. NO Temporal dependency at v1.1.0
 * (full Temporal-backed executor is v1.2+).
 *
 * Step actions supported at v1.2.1:
 *   - 'wait'             — no-op, succeed immediately
 *   - 'spawn_sub_unit'   — no-op stub (logs intent, succeeds)
 *   - 'invoke_host_llm'  — DISPATCHES into hostLLMActivity (claude --bare /
 *                          codex exec); see v1.2.1 contract block below.
 *   - 'terminate'        — emit workflow_completed early, success
 *
 * v1.2.1 host-LLM contract (DISPATCH-ONLY):
 *   - LiteExecutor invokes hostLLMActivity and forwards the HostLLMResult
 *     via the on_host_llm_result callback (default: no-op, preserving the
 *     "PURE relative to emit()" contract below).
 *   - LiteExecutor does NOT wrap the response in a DataRef envelope and
 *     does NOT validate against step.return_contract. Workflows that need
 *     DataRef wrapping or schema validation must use the full
 *     step-graph-executor (engine/step-graph-executor.ts).
 *   - This DISPATCH-ONLY scope closes P1.2 of DIRECTIVE 1777839055 (post-
 *     approval workflow no longer hollow); broader contract alignment with
 *     step-graph-executor is deferred to v1.x.
 *
 * step.on_failure semantics:
 *   - 'continue' → swallow the error, proceed to next step
 *   - 'abort'    → emit workflow_failed immediately
 *   - 'rollback' → mapped to abort at v1.1.0 (no rollback machinery yet)
 *   - 'pause'    → mapped to abort at v1.1.0 (no pause queue yet)
 *   - 'escalate' → mapped to abort at v1.1.0 (no escalation channel yet)
 *
 * The executor is PURE relative to its emit() callback — it does NO I/O
 * itself except via the host_llm_dispatch hook (default = real
 * hostLLMActivity; tests inject stubs). Caller (NativeEngine / CLI) wires
 * emit() to the RendererRegistry + audit log.
 */
import type { Workflow } from '../primitives/workflow.js';
import type { WorkflowStep } from '../types/index.js';
import type { EngineEvent } from '../types/engine-event.js';
import { hostLLMActivity, type HostLLMResult } from '../engine/host-llm-activity.js';
import type { UserKitOptions } from '../persistence/user-kit.js';
import type { ExecutionApprovalRecord } from '../persistence/execution-approval-ledger.js';
import type { ExecutionPauseRecord } from '../persistence/execution-pause-ledger.js';
import type { ExecutionEscalationRecord } from '../persistence/execution-escalation-ledger.js';
import { type PredicateRegistry } from './pnc-predicate.js';
export interface ExecuteOptions {
    readonly workflow: Workflow;
    readonly execution_id: string;
    /** Called for every EngineEvent emitted during execution. */
    readonly emit: (event: EngineEvent) => void;
    /** Optional clock for deterministic tests. Defaults to Date.now. */
    readonly now?: () => number;
    /**
     * v1.2.1: dispatcher for action='invoke_host_llm'. Defaults to the real
     * hostLLMActivity. Tests inject a stub returning a canned HostLLMResult.
     */
    readonly host_llm_dispatch?: typeof hostLLMActivity;
    /**
     * v1.2.1: callback invoked once per successful invoke_host_llm step with
     * the HostLLMResult and the originating WorkflowStep. Default = no-op
     * (preserves "PURE relative to emit()" contract — caller decides what to
     * do with the response).
     */
    readonly on_host_llm_result?: (result: HostLLMResult, step: WorkflowStep) => void;
    /**
     * v1.2.1: forwarded to hostLLMActivity as workflow_run_seq for invocation_id
     * derivation (see host-llm-activity.ts D-NS-26). Defaults to 0.
     */
    readonly workflow_run_seq?: number;
    /**
     * v1.2.2 (N2): when set, lite-executor writes a DecisionProvenance record
     * to the user-kit DP log on workflow_started + workflow_completed/failed.
     * When unset, no DP records are written (v1.2.1 behavior preserved for
     * raw cmdRun / direct executeWorkflow callers per codex pre-dispatch fold).
     */
    readonly user_kit_options_for_dp?: UserKitOptions;
    /**
     * v1.2.2 (N2): optional charter id linking this execution to a Charter
     * for the DP authority_id field. Defaults to 'native-runtime'.
     */
    readonly charter_id?: string;
    /**
     * v1.2.2 (N4 narrowed — routed-engine-only OPA gate): callable that
     * adjudicates step.policy_check=true. When set AND a step has
     * policy_check=true, lite-executor calls this and emits a policy_decision
     * event before proceeding. NativeEngine wires this when routing exact-
     * matches a trigger with a charter_id. Direct cmdRun / raw
     * executeWorkflow callers leave this unset → ungated (codex narrowing).
     */
    readonly policy_dispatch?: (step: WorkflowStep) => {
        allow: boolean;
        reason: string;
    };
    /**
     * v1.3.0 Wave 2 (codex W2 BLOCKER 3 fold). Optional callback invoked once
     * when the executor pauses at a `step.requires_approval=true` step. The
     * NativeEngine wires this to `persistApproval(record)` so the durable
     * ExecutionApprovalRecord{status:'pending'} survives daemon restart.
     *
     * Default = no-op (preserves "PURE relative to emit()" contract — direct
     * `executeWorkflow` callers without an injected persist callback get the
     * paused ExecutionResult but no on-disk ledger entry. The NativeEngine
     * routed path always supplies this so the founder-facing surface is
     * always durable.)
     */
    readonly approval_persist?: (rec: ExecutionApprovalRecord) => void;
    /**
     * v1.3.0 Wave 4 (codex W4 fold). Optional callback invoked once when the
     * executor pauses at a `step.on_failure='pause'` step that FAILED. The
     * NativeEngine wires this to `persistPause(record)` so the durable
     * ExecutionPauseRecord{status:'pending'} survives daemon restart.
     *
     * Default = no-op (preserves "PURE relative to emit()" contract — direct
     * `executeWorkflow` callers without an injected persist callback get the
     * paused ExecutionResult but no on-disk ledger entry).
     */
    readonly pause_persist?: (rec: ExecutionPauseRecord) => void;
    /**
     * v1.3.0 Wave 4 (codex W4 fold). Optional callback invoked once when the
     * executor escalates at a `step.on_failure='escalate'` step that FAILED.
     * The NativeEngine wires this to `persistEscalation(record)` so the
     * durable ExecutionEscalationRecord audit trail survives daemon restart.
     */
    readonly escalation_persist?: (rec: ExecutionEscalationRecord) => void;
    /**
     * v1.3.0 Wave 2. When set, the executor skips steps whose 1-based
     * step_index is `<= resume_from_step_index` and emits no events for them.
     * Used by NativeEngine.resumeApproved after `approve E-<id>` flips the
     * ledger entry: the original paused step's index is the value here, so
     * the executor resumes at the NEXT step.
     *
     * Required > 0 when set; 0 / undefined ⇒ start from step 1 (normal run).
     * Out-of-range values (e.g., > step_graph.length) cause the run to
     * complete immediately as success with steps_completed=0 — the caller
     * should validate before invoking.
     */
    readonly resume_from_step_index?: number;
    /**
     * v1.3.0 Wave 5 (codex W5 BLOCKER 1+2 fold). Optional registry of atom
     * evaluators consulted when parsing wf.preconditions / wf.postconditions
     * as a JSON-shaped PNCPredicate. When the registry is undefined OR the
     * pre/postcondition string is not parseable JSON-Predicate, the gate is
     * SKIPPED (legacy back-compat for free-form preconditions like
     * "is_morning_window AND no_pulse_today" already in the starter kit).
     *
     * When the registry is supplied AND the string IS a parseable PNCPredicate:
     *   - precondition fail ⇒ workflow_failed reason='precondition_failed:<expr>'
     *     emitted instead of workflow_started; NO step events.
     *   - postcondition fail ⇒ workflow_failed reason='postcondition_failed:<expr>'
     *     emitted instead of workflow_completed.
     *
     * NativeEngine wires this for routed runs; direct cmdRun / raw
     * executeWorkflow callers leave it undefined → no PNC gate (preserves
     * v1.2.x admission behavior).
     */
    readonly pnc_registry?: PredicateRegistry;
    /**
     * v1.3.0 Wave 5. Frozen evaluation context passed to PNC atom evaluators.
     * Defaults to an empty frozen object. Window markers (e.g.
     * { time_of_day: 'morning', iso_week: '2026-W18' }) belong here, not in
     * the atom evaluator function bodies (codex W5 advisory E: predicate
     * determinism — atoms must not call Date.now/random/I/O; they read
     * pre-computed markers from this snapshot).
     */
    readonly pnc_ctx?: Readonly<Record<string, unknown>>;
}
export interface ExecutionResult {
    /**
     * v1.3.0 Wave 2 (codex W2 BLOCKER 1 fold). 'paused' is canonical state per
     * the extended ExecutionState union; lite-executor returns it (with
     * steps_completed = step_index BEFORE the paused step) when a step has
     * requires_approval=true and the executor pauses.
     */
    readonly status: 'success' | 'failed' | 'paused';
    readonly steps_completed: number;
    readonly steps_failed: number;
    readonly duration_ms: number;
    readonly reason?: string;
    /**
     * v1.3.0 Wave 2. When status='paused', the 1-based step_index of the
     * step the executor paused at (the requires_approval=true step that has
     * NOT YET run). Undefined for non-paused results.
     */
    readonly paused_step_index?: number;
}
/**
 * Execute a Workflow async, emitting events along the way.
 * Returns when the workflow completes (success or failure).
 *
 * v1.2.1: invoke_host_llm steps await hostLLMActivity dispatch.
 *
 * Per softened I-NPD-1: every event is emitted via the caller's emit()
 * callback so the audit chain can be hooked from outside (replay-safe).
 */
export declare function executeWorkflow(opts: ExecuteOptions): Promise<ExecutionResult>;
/**
 * v1.3.0 Wave 2 — resume an approved-and-paused workflow run.
 *
 * Convenience wrapper that calls executeWorkflow with resume_from_step_index
 * set. Used by NativeEngine.resumeApproved after the founder's `approve E-<id>`
 * utterance has flipped the ledger entry pending → approved.
 *
 * Semantics: the original pause happened BEFORE the gated step ran. To RUN
 * that step on resume, the caller passes
 * `resume_from_step_index = paused_step_index - 1` (skip steps 1..N-1; run
 * starting at step N). The executor's loop logic skips steps with
 * stepIndex <= resumeFrom, so the gated step (N) is the first to execute.
 *
 * The gated step's `requires_approval=true` flag is BYPASSED on the first
 * step of a resume run via the `isResumeFirstStep` guard in executeWorkflow
 * — otherwise the gate would re-fire and the workflow would loop forever.
 *
 * The original execution_id is preserved so the audit transcript ties back
 * to the original workflow_started event.
 */
export declare function executeWorkflowResume(opts: ExecuteOptions & {
    resume_from_step_index: number;
}): Promise<ExecutionResult>;
//# sourceMappingURL=lite-executor.d.ts.map