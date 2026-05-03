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
}
export interface ExecutionResult {
    readonly status: 'success' | 'failed';
    readonly steps_completed: number;
    readonly steps_failed: number;
    readonly duration_ms: number;
    readonly reason?: string;
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
//# sourceMappingURL=lite-executor.d.ts.map