/**
 * TemporalAdapter — M5 Group I (T-041, T-042).
 *
 * Maps a Sutra Workflow primitive onto the Temporal SDK execution model.
 *
 * Codex P2.5 — orchestration shape (CRITICAL):
 *   ONE Temporal workflow function orchestrates the ORDERED Sutra step_graph.
 *   Per-step I/O lives in ACTIVITIES — NOT one Temporal workflow per Sutra
 *   step. The Temporal workflow body sequences activity calls in step_graph
 *   order; failure handling per step_graph[i].on_failure routes there.
 *
 * This is the SHELL: the function exists, returns a typed
 * TemporalWorkflowDefinition, and produces Activity descriptors per step. The
 * actual Temporal Worker registration + worker dispatch lands in subsequent
 * Group I tasks (or M5 Group J onward).
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group I T-041, T-042
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5 (wire flow)
 */
import { executeStepGraph, } from './step-graph-executor.js';
/**
 * Slugify a Sutra workflow id into a Temporal task queue name.
 *
 * Convention: lower-case, alphanumeric + dash; collapse runs, strip the
 * `W-` prefix, prepend `sutra-`. Pure function — no I/O, no clock.
 */
function deriveTaskQueue(workflowId) {
    const stripped = workflowId.replace(/^W-/, '');
    const slug = stripped
        .toLowerCase()
        .replace(/[^a-z0-9-]/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
    return `sutra-${slug || 'workflow'}`;
}
/**
 * Map a Sutra Workflow onto a Temporal workflow definition.
 *
 * Per codex P2.5: ONE Temporal workflow orchestrates the ordered Sutra
 * step_graph; per-step I/O lives in Activities. This shell preserves order
 * and wires per-step descriptors; the real activity invocations + retry
 * policies are populated by Group I/J runtime tasks.
 *
 * @param sutraWorkflow  A Sutra Workflow primitive (id starts with `W-`).
 * @returns TemporalWorkflowDefinition shell (workflow_id, task_queue,
 *          activities[], run()).
 * @throws TypeError when input is not a Workflow shape.
 * @throws Error when step_graph is empty (degenerate orchestration —
 *         a Sutra Workflow with no steps cannot be operationalized).
 */
export function registerWorkflow(sutraWorkflow) {
    if (typeof sutraWorkflow !== 'object' ||
        sutraWorkflow === null ||
        typeof sutraWorkflow.id !== 'string' ||
        !Array.isArray(sutraWorkflow.step_graph)) {
        throw new TypeError('registerWorkflow: input must be a Workflow with `id: string` and `step_graph: WorkflowStep[]`');
    }
    if (sutraWorkflow.step_graph.length === 0) {
        throw new Error(`registerWorkflow: Workflow ${sutraWorkflow.id} has empty step_graph — cannot orchestrate`);
    }
    const workflow_id = sutraWorkflow.id;
    const task_queue = deriveTaskQueue(workflow_id);
    // Defensive — Workflow primitive validators run earlier but pre-typeguarded
    // for safety in case of partial input shapes during Group J wiring.
    const activities = sutraWorkflow.step_graph.map((step) => ({
        step_id: step.step_id,
        skill_ref: typeof step.skill_ref === 'string' ? step.skill_ref : null,
        action: typeof step.action === 'string' ? step.action : null,
        inputs: step.inputs,
        outputs: step.outputs,
        on_failure: step.on_failure,
    }));
    // M5 Group K (T-049): real executor wired. The Group I `__shell:true` tag is
    // REMOVED. `run()` delegates to `executeStepGraph` which dispatches
    // Activities in order, routes failures via failure-policy.ts, and folds
    // terminalCheck violations into `failure_reason` per T-051.
    //
    // The default dispatcher returns `{kind:'ok', outputs:[]}` for every step.
    // It exists so `registerWorkflow(...)` is callable without a Worker (e.g.,
    // for adapter-shape contract tests + the registration smoke path). Real
    // dispatchers (Temporal `proxyActivities` or test mocks) are passed via
    // `run({ dispatch })`.
    const defaultDispatcher = () => ({ kind: 'ok', outputs: [] });
    const run = async (input) => {
        const inputObj = typeof input === 'object' && input !== null
            ? input
            : {};
        const dispatch = typeof inputObj.dispatch === 'function' ? inputObj.dispatch : defaultDispatcher;
        const options = inputObj.options ?? {};
        return executeStepGraph(sutraWorkflow, dispatch, options);
    };
    return {
        workflow_id,
        task_queue,
        activities,
        run,
    };
}
//# sourceMappingURL=temporal-adapter.js.map