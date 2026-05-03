/**
 * LiteExecutor — v1.1.0 synchronous Workflow.step_graph runner.
 *
 * Wave 2 lite path: takes a Workflow + Execution context, walks step_graph
 * in order, emits EngineEvents around each step, and produces a final
 * workflow_completed or workflow_failed. NO Temporal dependency at v1.1.0
 * (full Temporal-backed executor is v1.2+).
 *
 * Step actions supported at v1.1.0:
 *   - 'wait'             — no-op, succeed immediately
 *   - 'spawn_sub_unit'   — no-op stub (logs intent, succeeds)
 *   - 'invoke_host_llm'  — no-op stub (logs intent, succeeds)
 *   - 'terminate'        — emit workflow_completed early, success
 *
 * step.on_failure semantics:
 *   - 'continue' → swallow the error, proceed to next step
 *   - 'abort'    → emit workflow_failed immediately
 *   - 'rollback' → mapped to abort at v1.1.0 (no rollback machinery yet)
 *   - 'pause'    → mapped to abort at v1.1.0 (no pause queue yet)
 *   - 'escalate' → mapped to abort at v1.1.0 (no escalation channel yet)
 *
 * The executor is PURE relative to its emit() callback — it does NO I/O
 * itself. Caller (NativeEngine) wires emit() to the RendererRegistry +
 * audit log.
 */
import type { Workflow } from '../primitives/workflow.js';
import type { EngineEvent } from '../types/engine-event.js';
export interface ExecuteOptions {
    readonly workflow: Workflow;
    readonly execution_id: string;
    /** Called for every EngineEvent emitted during execution. */
    readonly emit: (event: EngineEvent) => void;
    /** Optional clock for deterministic tests. Defaults to Date.now. */
    readonly now?: () => number;
}
export interface ExecutionResult {
    readonly status: 'success' | 'failed';
    readonly steps_completed: number;
    readonly steps_failed: number;
    readonly duration_ms: number;
    readonly reason?: string;
}
/**
 * Execute a Workflow synchronously, emitting events along the way.
 * Returns when the workflow completes (success or failure).
 *
 * Per softened I-NPD-1: every event is emitted via the caller's emit()
 * callback so the audit chain can be hooked from outside (replay-safe).
 */
export declare function executeWorkflow(opts: ExecuteOptions): ExecutionResult;
//# sourceMappingURL=lite-executor.d.ts.map