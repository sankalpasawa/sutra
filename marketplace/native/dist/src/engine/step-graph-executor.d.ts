/**
 * step-graph-executor — M5 Group K (T-049, T-051).
 *
 * Deterministic dispatcher for the Sutra Workflow.step_graph. Replaces the
 * Group I shell `__shell: true` tag with a real executor that:
 *   - dispatches Activities in step_graph order
 *   - collects per-step results
 *   - routes per-step failures via failure-policy.ts
 *   - resolves terminalCheck violations to
 *     `failure_reason = 'forbidden_coupling:F-N,F-M'` (sorted, comma-joined,
 *     no spaces) when the `terminate` stage runs (T-051)
 *   - supports child Workflow invocation per V2.3 §A11 (action='spawn_sub_unit')
 *
 * Replay-determinism rules (final-architecture.md §5):
 *   - All I/O happens in Activities (the dispatcher is pure orchestration).
 *   - The executor calls `dispatch(descriptor, ctx)` — the caller-supplied
 *     dispatcher is the I/O boundary; the executor itself is `Date.now()`-free
 *     and `Math.random()`-free.
 *   - Iteration of step_graph is order-preserving (Array.iteration).
 *   - Same input + same dispatcher ⇒ bit-identical output.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group K T-049 + T-051
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 *  - .enforcement/codex-reviews/2026-04-29-m5-plan-pre-dispatch.md P2.5 + P1.3
 */
import type { Workflow } from '../primitives/workflow.js';
import type { DataRef } from '../types/index.js';
import type { ForbiddenCouplingId } from '../laws/l4-terminal-check.js';
import type { ActivityDescriptor } from './temporal-adapter.js';
import type { SkillEngine } from './skill-engine.js';
import type { CompiledPolicy } from './charter-rego-compiler.js';
import type { PolicyDispatcher } from './policy-dispatcher.js';
import type { AgentIdentity } from '../types/agent-identity.js';
import { OTelEmitter } from './otel-emitter.js';
import { type GovernanceOverhead } from './governance-overhead.js';
/**
 * Test-only seam (M8 Group Z): reset the per-Workflow run counter so
 * back-to-back property-test cases don't accumulate run_seq across runs
 * (which would change the trace_id between identical inputs and break
 * replay-determinism assertions).
 *
 * NOT exported on the engine barrel — internal seam reachable only via
 * direct module import (tests/property/otel-emitter.test.ts).
 */
export declare function __resetWorkflowRunSeqForTest(): void;
/**
 * Test-only seam: reset the host-LLM validator cache. Used by integration
 * tests that exercise multiple distinct return_contract shapes back-to-back.
 * NOT exported on the public engine barrel.
 */
export declare function __resetHostLLMValidatorCacheForTest(): void;
/**
 * Per-step dispatch outcome handed back to the executor by an
 * `ActivityDispatcher`. Discriminated:
 *   - 'ok'           → impl ran, captured outputs
 *   - 'failure'      → impl threw / rejected; executor routes via failure_policy
 *   - 'child_result' → action='spawn_sub_unit' returned a child Execution-like
 *                      summary; outputs propagate per V2.3 §A11.
 */
export type StepDispatchResult = {
    kind: 'ok';
    outputs: ReadonlyArray<unknown>;
} | {
    kind: 'failure';
    error: Error;
} | {
    kind: 'child_result';
    child_workflow_id: string;
    outputs: ReadonlyArray<unknown>;
};
/**
 * Caller-supplied dispatcher. The executor invokes this for every step in
 * order. The dispatcher is the I/O boundary — Activity calls happen here.
 *
 * The executor passes the activity descriptor + a small dispatch context
 * (visited steps so far, autonomy_level). The dispatcher MUST be a pure-ish
 * function from (descriptor, ctx) to a `StepDispatchResult` — it can do I/O,
 * but for replay determinism the same (descriptor, ctx) MUST yield the same
 * result on retry. (Real Temporal Activities provide this guarantee via the
 * Worker; tests pass deterministic mock dispatchers.)
 */
export type ActivityDispatcher = (descriptor: ActivityDescriptor, ctx: DispatchContext) => Promise<StepDispatchResult> | StepDispatchResult;
/** Context passed to each `dispatch(...)` call. */
export interface DispatchContext {
    /**
     * Step ids that produced successful effects in this run. Order = execution
     * order. Failed-continue steps are NOT included — see codex P1.1
     * (2026-04-29 master review). This is the rollback-correct "completed" view.
     */
    completed_step_ids: ReadonlyArray<number>;
    /** Workflow autonomy level — for dispatcher to gate human-loop interruptions. */
    autonomy_level: 'manual' | 'semi' | 'autonomous';
}
/**
 * Optional terminalCheck input passed to `executeStepGraph`. When present and
 * the executor reaches a `terminate` action (or the natural end of the
 * step_graph), the executor evaluates `() => violations` lazily and, if the
 * list is non-empty, sets `failure_reason = 'forbidden_coupling:F-N,F-M'`.
 *
 * Lazy callable so the executor doesn't pay the terminal-check cost when no
 * terminate stage runs.
 */
export type TerminalCheckProbe = () => ForbiddenCouplingId[];
export interface ExecuteOptions {
    /**
     * Optional terminalCheck probe. If supplied, called at the terminate stage;
     * any violations populate `failure_reason`. T-051: violations sorted ASCII
     * + comma-joined with the prefix `forbidden_coupling:`.
     */
    terminalCheckProbe?: TerminalCheckProbe;
    /** Optional escalation target ref forwarded to failure-policy. */
    escalation_target?: string;
    /**
     * M6 Group P (T-073). When provided, steps with `skill_ref` are dispatched
     * via the child-invocation adapter (`invokeSkill`) instead of the
     * dispatcher. The adapter resolves the Skill, runs an isolated child
     * execution, validates the terminal payload against the cached
     * return_contract, and returns either a validated payload (recorded as the
     * parent step's outputs) or a canonical failure (synthesized as a step
     * failure → routed via M5 failure-policy).
     *
     * If omitted, steps with `skill_ref` continue to flow through the
     * dispatcher unchanged (back-compat with M5 tests + activity-only
     * Workflows that don't use the SkillEngine).
     */
    skill_engine?: SkillEngine;
    /**
     * M6 Group P (T-073). Current recursion depth for child Skill invocations.
     * Defaults to 0 at the root invocation. The executor passes this through
     * to `invokeSkill`, which checks it against `SKILL_RECURSION_CAP` before
     * resolution and increments it before re-entering executeStepGraph.
     */
    recursion_depth?: number;
    /**
     * M7 Group V (T-094). When supplied, the executor evaluates the supplied
     * `compiled_policy` BEFORE dispatching any step that has either
     *   - `step.policy_check === true`, OR
     *   - `workflow.modifies_sutra === true` (V2.4 §A12 — every step in a
     *     reflexive Workflow gets policy-checked, even when the step itself
     *     does not declare policy_check).
     *
     * On `kind: 'allow'` the step proceeds through its normal dispatch path.
     * On `kind: 'deny'` the executor synthesizes a step failure with
     *   `errMsg = 'policy_deny:<rule_name>:<reason>:<policy_version>'`
     * and routes via the existing M5 failure-policy (rollback / escalate /
     * pause / abort / continue per `step.on_failure`).
     *
     * Both fields MUST be supplied together; if `policy_dispatcher` is set
     * without `compiled_policy` (or vice versa), the policy gate is a no-op
     * (defensive default — never block-as-side-effect-of-misconfiguration).
     * Test-time injection: pass a stub PolicyDispatcher to assert allow/deny
     * paths without invoking the real OPA binary.
     */
    policy_dispatcher?: PolicyDispatcher;
    /** M7 Group V (T-094). Compiled policy bound to the Workflow's parent Charter. */
    compiled_policy?: CompiledPolicy;
    /**
     * M7 codex master review 2026-04-30 P2.3 fold (CHANGE). Optional tenant
     * identifier surfaced to policy evaluation via
     * `PolicyInput.execution_context.tenant_id`. Charters that encode tenant
     * isolation (e.g. `input.execution_context.tenant_id == "T-tenant-a"`)
     * read this field directly. Default: undefined; production code populates
     * from process/session context (M11 dogfood will wire). Tests pass an
     * explicit value to exercise cross-tenant deny scenarios (A-7.e).
     */
    tenant_id?: string;
    /**
     * M8 Group Z (T-108). Optional OTel emitter — when supplied, the executor
     * emits STEP_START / STEP_COMPLETE / STEP_FAIL records (and propagates
     * the emitter into invokeSkill + policy_dispatcher) carrying a
     * deterministic trace_id derived from the Workflow + run_seq. Absent ⇒
     * no emission (M5/M6/M7 baseline tests stay clean).
     */
    otel_emitter?: OTelEmitter;
    /**
     * M8 Group Z (T-108). Optional agent_identity carried through to OTel
     * emissions. Production code populates from session/Activity context;
     * tests pass an explicit value when asserting identity in records.
     */
    agent_identity?: AgentIdentity;
    /**
     * M8 Group Z (T-108). Optional actor (authority-holder id, D1 §1) carried
     * through to OTel emissions. Production code populates from policy
     * context; tests pass an explicit value.
     */
    actor?: string;
    /**
     * M8 Group Z (T-108) — child-execution carry-through. The executor
     * derives trace_id deterministically at root invocation; child Skill
     * invocations re-enter executeStepGraph and MUST share the parent's
     * trace_id so all events for one logical run correlate. invokeSkill
     * forwards the parent's trace_id via this option. Direct callers leave
     * this undefined — the executor derives a fresh trace_id.
     */
    trace_id?: string;
    /**
     * M9 Group FF (T-153). The OPERATING tenant id — the tenant whose
     * authority frames this Execution. Compared at every step against the
     * step's resolved effective tenant; mismatch ⇒ TenantIsolation
     * assertion runs (see below). Optional: when undefined the cross-tenant
     * gate is a no-op (single-tenant-by-default v1.0 behaviour).
     *
     * NOT the same as `tenant_id` (M7 P2.3 fold) which feeds OPA via
     * `PolicyInput.execution_context.tenant_id`. The two namespaces are
     * intentionally separate because OPA tenant policy may target a
     * scoping concept (e.g. "is this step authorized for tenant T-asawa")
     * that differs from sovereignty enforcement (cross-tenant move
     * requires delegates_to). Both happen to take a tenant id at v1.0;
     * the names stay distinct so v1.x can evolve them independently.
     */
    tenant_context_id?: string;
    /**
     * M9 Group FF (T-153). Registered D4 §3 typed `delegates_to: Tenant→Tenant`
     * edges available to the runtime. When a step's effective tenant differs
     * from `tenant_context_id`, the executor consults this set via
     * `TenantIsolation.assertCrossTenantAllowed`; the call THROWS
     * `CrossTenantBoundaryError` when no edge grants the operation. The
     * executor catches the throw and synthesizes a step failure with errMsg
     *   `cross_tenant_boundary:<source>:<target>:<operation>`
     * routed via the existing M5 failure-policy (rollback / escalate /
     * pause / abort / continue). Default `[]` — no edges, every cross-tenant
     * op is rejected.
     */
    delegates_to_edges?: ReadonlyArray<import('../types/edges.js').DelegatesToEdge>;
    /**
     * M9 Group HH (T-162). Governance-overhead tracker used by the
     * red-zone HARD-STOP (HS-2: ≥25% overhead halts the run). When supplied
     * AND `turn_id` is also supplied, after every step transition the
     * executor calls `governance_overhead.report(turn_id)` and inspects the
     * threshold-state. If the report's `overhead_pct >= 0.25`, the executor:
     *   1. Emits a TERMINATE DecisionProvenance via OTel (if otel_emitter
     *      supplied) carrying overhead_pct + threshold + reason
     *      'hs2_overhead_exceeded'.
     *   2. Returns an ExecutionResult with state='failed' +
     *      failure_reason='hs2_overhead_exceeded'.
     * Reuses canonical I-4 contract (failed ⇒ failure_reason non-null);
     * no new enums, no new error class. Deferred from M8 per M8 plan
     * "NOT shipping at M8" + folded per codex M9 pre-dispatch P1.1.
     */
    governance_overhead?: GovernanceOverhead;
    /**
     * M9 Group HH (T-162). Turn id keyed in the supplied `governance_overhead`
     * tracker. Required for HS-2 wire-up; when omitted the gate is a no-op
     * even if `governance_overhead` is supplied (defensive — supplying half
     * the wire is operator error; surface it as "no gate" rather than block
     * the workflow on misconfiguration, matching the policy-gate convention).
     */
    turn_id?: string;
}
/**
 * M6 Group P (T-073). One entry per child Skill invocation that succeeded.
 * Surfaced on `ExecutionResult.child_edges` so observability + downstream
 * tooling can reconstruct the parent→child invocation graph WITHOUT having
 * to merge the child's internals into the parent's visited/completed lists
 * (codex P1.3 isolation contract).
 */
export interface ChildEdge {
    /** Parent step that carried `skill_ref`. */
    step_id: number;
    /** Resolved Skill ref (== Workflow.id of the registered Skill). */
    skill_ref: string;
    /**
     * Deterministic child execution id synthesized by `invokeSkill` from
     * (parent step_id, skill_ref). Replay-stable; no clock dependency.
     */
    child_execution_id: string;
    /**
     * The Skill's terminal payload wrapped in a V2 §A11 DataRef envelope after
     * validation against `return_contract`. Codex master review 2026-04-30
     * P1.1 fold: contract drift fix — V2 §A11 says child execution "returns
     * DataRef per `return_contract`", so the parent step's outputs slot carries
     * the DataRef envelope (kind='skill-output', schema_ref=return_contract,
     * locator='inline:<JSON>', version='1', mutability='immutable',
     * retention='session', authoritative_status='authoritative').
     *
     * Same value the executor records into `step_outputs[parent step_id].outputs[0]`.
     */
    validated_dataref: DataRef;
}
/**
 * Final state of a Workflow execution.
 */
export interface ExecutionResult {
    workflow_id: string;
    /**
     * Step ids visited, in execution order (incl. failed-continue steps + steps
     * up to the abort/rollback/pause/escalate point). Trace-shaped — for
     * observability + debugging. NOT the rollback compensation set; see
     * `completed_step_ids` for that.
     */
    visited_step_ids: number[];
    /**
     * Step ids that produced successful effects, in execution order. Strictly
     * a subset of `visited_step_ids`: a step that failed with `on_failure='continue'`
     * appears in visited but NOT here. Rollback compensation walks reverse this
     * list — never the visited list. Codex P1.1 (2026-04-29 master review).
     */
    completed_step_ids: number[];
    /** Per-step outputs — one entry per visited step (skipped steps omitted). */
    step_outputs: Array<{
        step_id: number;
        outputs: ReadonlyArray<unknown>;
        /** True iff `continue` policy skipped output validation for this step. */
        output_validation_skipped: boolean;
    }>;
    /**
     * Terminal Workflow state. 'success' iff every step succeeded AND
     * (no terminate stage OR terminalCheck cleared).
     */
    state: 'success' | 'failed' | 'paused' | 'escalated';
    /**
     * V2.4 §A12: non-null iff state='failed' OR a continue policy advanced past
     * a step failure (then `partial=true` flips with state remaining 'success').
     * For terminalCheck violations: 'forbidden_coupling:F-N,F-M' (sorted, comma-joined).
     * For step failure: a step:N:{action}:{message} reason from failure-policy.
     * For pause/escalate: routing reason from failure-policy.
     */
    failure_reason: string | null;
    /**
     * True iff at least one step's `on_failure='continue'` fired during the run.
     * Workflow does NOT abort; execution proceeds past the failed step. Codex P1.3.
     */
    partial: boolean;
    /** Optional resume token if a step's failure_policy was 'pause'. */
    resume_token?: string;
    /** When 'escalated' state, the BoundaryEndpoint ref the workflow was handed to. */
    escalation_target?: string;
    /** Compensations executed when a step's failure_policy was 'rollback'. */
    rollback_compensations?: number[];
    /** Child workflow invocations triggered via action='spawn_sub_unit'. */
    child_workflows?: Array<{
        step_id: number;
        child_workflow_id: string;
    }>;
    /**
     * M6 Group P (T-073). Child Skill invocations triggered via a parent step
     * carrying `skill_ref` while `options.skill_engine` was provided. Empty
     * when no Skill invocations occurred (back-compat with M5 dispatchers).
     * The child's internal step_ids are NOT merged into `visited_step_ids`
     * or `completed_step_ids` (codex P1.3 isolation); only the parent step
     * carrying `skill_ref` appears in those lists.
     */
    child_edges?: ChildEdge[];
}
/**
 * Format terminalCheck violations into the `failure_reason` string
 * per T-051: `forbidden_coupling:F-N,F-M` — sorted ASCII, comma-joined,
 * no spaces. Empty input ⇒ null.
 */
export declare function formatTerminalCheckFailureReason(violations: ReadonlyArray<ForbiddenCouplingId>): string | null;
/**
 * Run the Workflow.step_graph end-to-end through the supplied dispatcher.
 *
 * Pure-orchestration function: no clock, no random, no network. Calls
 * `dispatch(descriptor, ctx)` once per step in order; routes per-step
 * failures via `applyFailurePolicy(...)`; at the natural end of the
 * step_graph (or when a `terminate` action is reached) calls the
 * optional `terminalCheckProbe` and folds violations into `failure_reason`.
 *
 * Replay-determinism: same Workflow + same dispatcher (deterministic) +
 * same options ⇒ deep-equal `ExecutionResult` on every call.
 *
 * @param workflow   Sutra Workflow primitive (constructor-validated).
 * @param dispatch   Caller-supplied I/O boundary; one call per step.
 * @param options    Optional terminalCheck probe + escalation target.
 * @returns          ExecutionResult — terminal state + per-step outputs +
 *                   failure_reason + partial flag.
 */
export declare function executeStepGraph(workflow: Workflow, dispatch: ActivityDispatcher, options?: ExecuteOptions): Promise<ExecutionResult>;
//# sourceMappingURL=step-graph-executor.d.ts.map