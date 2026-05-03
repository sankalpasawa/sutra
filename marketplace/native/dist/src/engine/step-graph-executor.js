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
import { createHash } from 'node:crypto';
// Ajv 8.x ships as CJS; under TS NodeNext the default-import resolves
// to the module namespace, not the class. `{ default as Ajv }` peels
// the synthesized CJS default into a named binding so `new Ajv(...)`
// remains constructable. See skill-engine.ts comment for detail.
import { Ajv } from 'ajv';
import { applyFailurePolicy, } from './failure-policy.js';
import { invokeSkill } from './skill-invocation.js';
// M8 Group BB (T-120). Host-LLM Activity dispatch — used when a step has
// action='invoke_host_llm'. Imported as a function (not just type) because
// the executor calls it directly to dispatch the host CLI subprocess.
import { hostLLMActivity, HostUnavailableError, } from './host-llm-activity.js';
// M9 Group FF (T-153). Cross-tenant boundary enforcement runtime-derived
// at every step. Engine reads existing D4 §3 `delegates_to` edges; throws
// CrossTenantBoundaryError when source ≠ target AND no edge grants the
// operation. The executor catches the throw and synthesizes a step failure
// routed via the existing M5 failure-policy.
import { TenantIsolation, CrossTenantBoundaryError, } from './tenant-isolation.js';
// =============================================================================
// trace_id derivation (M8 Group Z T-108; D-NS-26)
// =============================================================================
/**
 * trace_id derivation: per-run correlation only.
 *
 * Codex master review 2026-04-30 P2.2 fold — narrow the determinism claim.
 * The previous comment overstated the contract; the precise semantics are:
 *
 *   trace_id = sha256(workflow.id + ':' + run_seq).slice(0, 32)
 *
 * where `run_seq` is a process-local counter that increments on each
 * `executeStepGraph` invocation. This gives:
 *   - Same trace_id for ALL events of one Workflow run (correlation invariant
 *     across STEP_*, POLICY_*, SKILL_*, HOST_LLM_INVOCATION, GOVERNANCE_OVERHEAD_ALERT).
 *   - DIFFERENT trace_id across runs (even of the same Workflow), because
 *     `run_seq` advances every invocation.
 *   - Counter resets on process restart — the first run after restart
 *     gets run_seq=1, NOT a continuation of pre-restart sequencing.
 *
 * NOT a stable replay key across process boundaries. For audit-grade
 * cross-process replay correlation, see M11 dogfood (D-NS-12 b) — that's
 * where Temporal's own run_id integration lands and lifts trace_id from a
 * per-run identifier to a process-stable replay key.
 *
 * Why `run_seq` rather than a hash of inputs: the M8 Group Z contract is
 * "shared trace_id within one logical run, distinct across runs." A counter
 * gives that with no hidden inputs (no clock, no random) and the test seam
 * `__resetWorkflowRunSeqForTest` lets property tests pin determinism inside
 * one process. Cross-process determinism would require hashing run inputs +
 * process identity — a v1.x decision when the dogfood corpus is in hand.
 */
const workflowRunSeq = new Map();
/**
 * Derive the trace_id for one Workflow execution. Per the comment block
 * above, this is per-run correlation, NOT a cross-process replay key.
 *
 * @param workflow_id — Workflow.id (assumed non-empty per the primitive)
 * @returns 32-char hex string `sha256(workflow_id + ':' + run_seq).slice(0, 32)`
 */
function deriveTraceId(workflow_id) {
    const seq = (workflowRunSeq.get(workflow_id) ?? 0) + 1;
    workflowRunSeq.set(workflow_id, seq);
    const hash = createHash('sha256').update(`${workflow_id}:${seq}`).digest('hex');
    return hash.slice(0, 32);
}
/**
 * M8 Group BB (T-120). Read-only accessor for the current per-Workflow
 * run_seq — used by the host-LLM dispatch branch to feed `workflow_run_seq`
 * into invocation_id derivation so a replay produces the same id.
 *
 * Returns 0 if the Workflow has not been seen yet (defensive; the executor
 * always calls deriveTraceId BEFORE the host-LLM branch fires, so the
 * counter is non-zero by the time this is read in practice).
 */
function getWorkflowRunSeq(workflow_id) {
    return workflowRunSeq.get(workflow_id) ?? 0;
}
/**
 * Test-only seam (M8 Group Z): reset the per-Workflow run counter so
 * back-to-back property-test cases don't accumulate run_seq across runs
 * (which would change the trace_id between identical inputs and break
 * replay-determinism assertions).
 *
 * NOT exported on the engine barrel — internal seam reachable only via
 * direct module import (tests/property/otel-emitter.test.ts).
 */
export function __resetWorkflowRunSeqForTest() {
    workflowRunSeq.clear();
}
// =============================================================================
// Host-LLM output validation (codex master review 2026-04-30 P2.1 fold)
// =============================================================================
/**
 * Per-process Ajv instance used to compile + validate host-LLM `return_contract`
 * schemas. `strict: false` matches SkillEngine — Sutra schemas may be authored
 * against older JSON Schema drafts; permissive compilation is the right v1.0
 * default (strict-mode promotion is a v1.x decision, see SkillEngine comment).
 *
 * Compiled validators are cached by raw schema source to keep the validation
 * hot path O(1) on repeat dispatches of the same return_contract.
 */
const hostLLMAjv = new Ajv({ strict: false });
const hostLLMValidatorCache = new Map();
/**
 * Sanitize host-LLM validation error text for inclusion in the M5
 * canonical `failure_reason` envelope (`step:N:abort:host_llm_output_validation:<details>`).
 *
 * Mirrors the OPA-evaluator `sanitizeReasonForFailureReason` shape (replace `:`
 * with `\:`, collapse newlines/tabs, length cap 256). Kept local rather than
 * imported because the OPA sanitizer is module-scoped to opa-evaluator; both
 * sanitizers MUST stay shape-compatible (codex P1.2 envelope contract).
 */
function sanitizeHostLLMValidationError(raw) {
    return raw
        .replace(/:/g, '\\:')
        .replace(/[\n\r\t]/g, ' ')
        .slice(0, 256);
}
/**
 * Validate a host-LLM response string against an optional return_contract
 * (a JSON Schema string). When return_contract is unset, the contract is
 * "no schema declared" → always valid (parallels M6's behavior when a
 * Workflow has no return_contract field).
 *
 * Validation pipeline:
 *   1. JSON.parse the response. If parse fails, validate the raw string
 *      directly (so a Skill author can declare `{"type":"string"}`).
 *   2. ajv.compile the schema (cached by source string). Compile errors
 *      surface as a deterministic 'invalid' outcome — a malformed schema
 *      is a contract violation, not a soft failure.
 *   3. Run the compiled validator. Return errors via ajv.errorsText.
 *
 * All errors are routed through `sanitizeHostLLMValidationError` so the
 * resulting `failure_reason` envelope stays single-line + colon-safe.
 */
function validateHostLLMOutput(response, return_contract) {
    if (return_contract === undefined || return_contract.length === 0) {
        return { kind: 'valid' };
    }
    // Step 1: try JSON.parse. If the response is not JSON, validate the raw
    // string against the schema directly — Skill authors writing
    // `{"type":"string"}` should not need the response to be JSON-encoded.
    let parsed;
    try {
        parsed = JSON.parse(response);
    }
    catch {
        parsed = response;
    }
    // Step 2: compile (or fetch cached compile) the schema. Compile errors
    // surface as 'invalid' — a malformed return_contract is a step failure.
    let validator;
    const cached = hostLLMValidatorCache.get(return_contract);
    if (cached !== undefined) {
        if ('error' in cached) {
            return {
                kind: 'invalid',
                errors: sanitizeHostLLMValidationError(`schema_compile_failed:${cached.error}`),
            };
        }
        validator = cached;
    }
    else {
        try {
            // Cast to AnySchema is safe — JSON.parse can produce any schema shape
            // and ajv's compile rejects invalid shapes via thrown errors.
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const schema = JSON.parse(return_contract);
            validator = hostLLMAjv.compile(schema);
            hostLLMValidatorCache.set(return_contract, validator);
        }
        catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            hostLLMValidatorCache.set(return_contract, { error: msg });
            return {
                kind: 'invalid',
                errors: sanitizeHostLLMValidationError(`schema_compile_failed:${msg}`),
            };
        }
    }
    // Step 3: run the validator.
    if (validator(parsed)) {
        return { kind: 'valid' };
    }
    return {
        kind: 'invalid',
        errors: sanitizeHostLLMValidationError(hostLLMAjv.errorsText(validator.errors)),
    };
}
/**
 * Test-only seam: reset the host-LLM validator cache. Used by integration
 * tests that exercise multiple distinct return_contract shapes back-to-back.
 * NOT exported on the public engine barrel.
 */
export function __resetHostLLMValidatorCacheForTest() {
    hostLLMValidatorCache.clear();
}
// =============================================================================
// Helpers
// =============================================================================
/**
 * Format terminalCheck violations into the `failure_reason` string
 * per T-051: `forbidden_coupling:F-N,F-M` — sorted ASCII, comma-joined,
 * no spaces. Empty input ⇒ null.
 */
export function formatTerminalCheckFailureReason(violations) {
    if (!Array.isArray(violations) || violations.length === 0)
        return null;
    // Lexicographic ASCII string-sort (NOT numeric). E.g. ['F-10','F-2','F-1']
    // → 'F-1,F-10,F-2'. Downstream consumers that need numeric ordering must
    // re-sort by parsed integer. The contract pinned by
    // step-graph-executor.test.ts:178-183 is "sorted ASCII"; downstream tooling
    // matches against this string, so we MUST be deterministic. Do NOT "fix"
    // this to numeric sort — that would silently break the contract.
    const sorted = [...violations].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    return `forbidden_coupling:${sorted.join(',')}`;
}
// =============================================================================
// Executor
// =============================================================================
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
export async function executeStepGraph(workflow, dispatch, options = {}) {
    if (typeof workflow !== 'object' || workflow === null) {
        throw new TypeError('executeStepGraph: workflow must be a Workflow');
    }
    if (typeof dispatch !== 'function') {
        throw new TypeError('executeStepGraph: dispatch must be a function');
    }
    if (!Array.isArray(workflow.step_graph) || workflow.step_graph.length === 0) {
        throw new Error('executeStepGraph: Workflow.step_graph must be a non-empty array');
    }
    // Two distinct lists per codex P1.1 (2026-04-29 master review):
    //   visited_step_ids   — every step the executor saw, including failed-continue
    //                        steps (trace-shaped; for observability / debugging)
    //   completed_step_ids — only steps that produced successful effects (for
    //                        rollback compensation walks + dispatch context)
    // Aliasing them was the M5 ship-blocker: rollback would compensate steps
    // that failed-continue (never produced effects).
    const visited_step_ids = [];
    const completed_step_ids = [];
    const step_outputs = [];
    const child_workflows = [];
    // M6 Group P (T-073). Child Skill invocations populate this; merged into
    // ExecutionResult.child_edges at every return point below. Codex P1.3
    // isolation: parent's visited/completed never carry child internals; the
    // edge entries here are the only cross-reference between parent + child.
    const child_edges = [];
    let partial = false;
    // M6 Group P (T-073). Carry-through for nested Skill invocations.
    // recursion_depth defaults to 0 at the root invocation; invokeSkill
    // increments before re-entering this executor for the resolved Skill.
    const recursion_depth = options.recursion_depth ?? 0;
    const skill_engine = options.skill_engine;
    // M7 Group V (T-094). Policy gate is active iff BOTH a dispatcher AND a
    // compiled policy are supplied — defensive against misconfiguration
    // (one-without-the-other should never silently block-or-pass; the safe
    // default is "no gate", surfaced explicitly to the operator at config
    // time via the type contract).
    const policy_dispatcher = options.policy_dispatcher;
    const compiled_policy = options.compiled_policy;
    const policyGateActive = policy_dispatcher !== undefined && compiled_policy !== undefined;
    // M8 Group Z (T-108). Derive a deterministic trace_id for this run unless
    // the caller (e.g. invokeSkill re-entering for a child Skill) supplied
    // one — child invocations share the parent's trace_id so cross-event
    // correlation traces the full logical execution.
    //
    // D-NS-26: trace_id = sha256(workflow.id + ':' + run_seq).slice(0, 32);
    // clock-free. The run_seq is a per-Workflow module-level counter (see
    // top of file) — the property test (T-110) calls
    // __resetWorkflowRunSeqForTest between cases so back-to-back runs over
    // identical inputs produce identical trace_ids (replay-determinism).
    const trace_id = options.trace_id ?? deriveTraceId(workflow.id);
    const otel_emitter = options.otel_emitter;
    const agent_identity = options.agent_identity;
    const actor = options.actor;
    // M9 Group FF (T-153) + codex master P1.1 fold. Tenant-isolation gate
    // is active iff the caller supplied a `tenant_context_id`. The
    // `delegates_to_edges` set defaults to []; when active and the step's
    // effective tenant differs from the operating tenant,
    // `TenantIsolation.assertCrossTenantAllowed` is called unconditionally
    // — there is no opt-out hint a producer can omit (codex M9 re-review
    // P1 fold: advisory `WorkflowStep.crosses_tenant?` REJECTED).
    const tenant_context_id = options.tenant_context_id;
    const delegates_to_edges = options.delegates_to_edges ?? [];
    const tenantGateActive = typeof tenant_context_id === 'string' && tenant_context_id.length > 0;
    // FAIL-CLOSED gate (codex master P1.1 fold): when the Workflow declares
    // a `custody_owner` (i.e. it is non-trivially tenant-scoped), the caller
    // MUST supply `tenant_context_id`. Omitting it disables the runtime
    // gate — that was the round-3 bypass loophole; explicit option-omission
    // is the same shape as the previously-rejected `WorkflowStep.crosses_tenant?`
    // advisory hint. The fail-closed rule keeps the round-3 contract closed:
    // "runtime-derived enforcement; no opt-out."
    if (typeof workflow.custody_owner === 'string' &&
        workflow.custody_owner.length > 0 &&
        !tenantGateActive) {
        return {
            workflow_id: workflow.id,
            visited_step_ids: [],
            completed_step_ids: [],
            step_outputs: [],
            state: 'failed',
            failure_reason: 'cross_tenant_boundary:tenant_context_required',
            partial: false,
        };
    }
    // M9 Group HH (T-162). HS-2 overhead-termination gate is active iff
    // BOTH a GovernanceOverhead instance AND a turn_id were supplied
    // (defensive: half-wire ⇒ no gate, mirrors policy-gate convention).
    const governance_overhead = options.governance_overhead;
    const turn_id = options.turn_id;
    const overheadGateActive = governance_overhead !== undefined &&
        typeof turn_id === 'string' &&
        turn_id.length > 0;
    // M9 codex master P1.2 fold. Single HS-2 check helper called from
    // BOTH iteration top AND every terminal-return path. Returns either
    // a `'red'` ExecutionResult-shaped halt (caller `return`s it) or
    // `null` when the band is green/yellow / gate inactive.
    const hs2Halt = async (step_id) => {
        if (!overheadGateActive)
            return null;
        const band = governance_overhead.getThresholdState(turn_id);
        if (band !== 'red')
            return null;
        const report = governance_overhead.report(turn_id);
        await emitStepEvent(otel_emitter, 'TERMINATE', {
            trace_id,
            workflow_id: workflow.id,
            step_id,
            agent_identity,
            actor,
            attributes: {
                reason: 'hs2_overhead_exceeded',
                overhead_pct: report.overhead_pct,
                threshold: 0.25,
            },
        });
        return {
            workflow_id: workflow.id,
            visited_step_ids,
            completed_step_ids,
            step_outputs,
            state: 'failed',
            failure_reason: 'hs2_overhead_exceeded',
            partial,
            ...(child_workflows.length > 0 ? { child_workflows } : {}),
            ...(child_edges.length > 0 ? { child_edges } : {}),
        };
    };
    for (const step of workflow.step_graph) {
        // M9 Group HH (T-162). HS-2 overhead-termination — after every step
        // transition (i.e. at the start of every subsequent iteration), check
        // governance overhead. red zone (≥25%) → halt run with state='failed' +
        // failure_reason='hs2_overhead_exceeded' + TERMINATE provenance. We
        // check here (start of iteration) rather than after-success so the
        // current step never starts I/O when the prior step's accumulated
        // overhead already breached the threshold.
        //
        // Codex M9 pre-dispatch P1.1 fold: reuses existing TERMINATE
        // DecisionKind + existing 'failed' Execution state + canonical
        // failure_reason pattern. No new enums (would require coordinated
        // D2/D3/D5 contract change), no new error class (caller already
        // handles failed Execution).
        {
            const halt = await hs2Halt(step.step_id);
            if (halt !== null)
                return halt;
        }
        // Per-step dispatch context — derived snapshot, not a live reference.
        // `completed_step_ids` here is the rollback-correct view (success-only),
        // NOT visited; failed-continue steps are excluded.
        const dispatchCtx = {
            completed_step_ids: [...completed_step_ids],
            autonomy_level: workflow.autonomy_level,
        };
        // Build the descriptor identical to TemporalAdapter's mapping. Inline here
        // (not via registerWorkflow) to keep the executor independent of the
        // adapter's lifecycle; the shapes are coupled via TS types.
        const descriptor = {
            step_id: step.step_id,
            skill_ref: typeof step.skill_ref === 'string' ? step.skill_ref : null,
            action: typeof step.action === 'string' ? step.action : null,
            inputs: step.inputs,
            outputs: step.outputs,
            on_failure: step.on_failure,
        };
        // Special-case: action='terminate' is the V2.3 §A11 terminate stage. We
        // record the visit and break — no dispatcher call (terminate is structural,
        // not an I/O step). T-051: terminalCheck runs after this loop. Terminate
        // is structural, not effect-producing — visited only, NOT completed.
        if (descriptor.action === 'terminate') {
            visited_step_ids.push(step.step_id);
            break;
        }
        // M8 Group Z (T-108). STEP_START emitted before policy gate / dispatch.
        // Carries trace_id + workflow_id + step_id + agent_identity for cross-
        // event correlation. Idempotent — emission failures are swallowed.
        await emitStepEvent(otel_emitter, 'STEP_START', {
            trace_id,
            workflow_id: workflow.id,
            step_id: step.step_id,
            agent_identity,
            actor,
            attributes: {
                action: descriptor.action,
                skill_ref: descriptor.skill_ref,
            },
        });
        let result;
        // M9 Group FF (T-153). Cross-tenant boundary gate — runtime-derived,
        // not annotation-driven (codex re-review P1 fold). Resolve the step's
        // effective tenant and compare against the operating tenant context.
        //
        // Effective-tenant derivation:
        //   - skill_ref step: resolved Skill's `custody_owner` (the tenant
        //     that owns the Skill's state). If the Skill is unregistered or
        //     has no custody_owner, fall through to the workflow's own
        //     custody_owner (defensive — unresolved skill_ref is handled at
        //     T-073 via M5 failure-policy).
        //   - action step: the parent Workflow's own `custody_owner`.
        //   - When neither resolves, no cross-tenant op is possible at this
        //     step (single-tenant default at v1.0).
        //
        // Decision: if effective_tenant !== tenant_context_id AND tenant gate
        // active, call TenantIsolation.assertCrossTenantAllowed. The throw is
        // caught + translated into a synthetic step failure with errMsg
        //   `cross_tenant_boundary:<source>:<target>:<operation>`
        // so the existing M5 failure-policy switch (rollback / escalate /
        // pause / abort / continue per step.on_failure) handles it uniformly.
        let crossTenantDeniedError = null;
        if (tenantGateActive) {
            let effective_tenant = null;
            if (typeof step.skill_ref === 'string' && skill_engine !== undefined) {
                const resolved = skill_engine.resolve(step.skill_ref);
                if (resolved !== null && typeof resolved.custody_owner === 'string') {
                    effective_tenant = resolved.custody_owner;
                }
            }
            if (effective_tenant === null && typeof workflow.custody_owner === 'string') {
                effective_tenant = workflow.custody_owner;
            }
            if (effective_tenant !== null && effective_tenant !== tenant_context_id) {
                try {
                    TenantIsolation.assertCrossTenantAllowed({
                        source_tenant: tenant_context_id,
                        target_tenant: effective_tenant,
                        operation: typeof step.skill_ref === 'string'
                            ? `invoke_skill:${step.skill_ref}`
                            : `step_action:${String(step.action ?? 'unknown')}`,
                        delegates_to_edges,
                    });
                }
                catch (raw) {
                    if (raw instanceof CrossTenantBoundaryError) {
                        crossTenantDeniedError = new Error(`cross_tenant_boundary:${raw.source_tenant}:${raw.target_tenant}:${raw.operation}`);
                    }
                    else {
                        // Non-CrossTenantBoundaryError thrown — surface as step failure
                        // so executor stays crash-free; this should be reachable only
                        // via test-time misuse (passing garbage edges).
                        const msg = raw instanceof Error ? raw.message : String(raw);
                        crossTenantDeniedError = new Error(`cross_tenant_boundary:assertion_error:${msg}`);
                    }
                }
            }
        }
        // M7 Group V (T-094). Policy gate — runs BEFORE the step's normal dispatch.
        //
        // Activation rule:
        //   - step.policy_check === true    (per-step opt-in), OR
        //   - workflow.modifies_sutra === true   (V2.4 §A12 — all steps in a
        //     reflexive Workflow get policy-checked, even when the step itself
        //     does not declare policy_check)
        //
        // Allow path: control falls through to the existing dispatch branch below.
        //
        // Deny path: synthesize a step failure with the canonical errMsg
        //   `policy_deny:<rule_name>:<reason>:<policy_version>`
        // and route via the SAME failure-policy switch the dispatcher uses for
        // step failures (rollback / escalate / pause / abort / continue per
        // step.on_failure). This keeps deny semantics symmetric with arbitrary
        // step failures — the parent Workflow's failure policy is the single
        // place that decides "what happens when something goes wrong".
        //
        // Codex r8 P1.1 fold: the policy_eval Activity runs through the
        // dispatcher seam (PolicyDispatcher), preserving the M5 boundary that
        // I/O happens via Activities. The executor itself remains pure
        // orchestration — no shell-out, no Date.now(), no Math.random().
        let policyDenied = false;
        let policyDenyError = null;
        if (policyGateActive && (step.policy_check === true || workflow.modifies_sutra === true)) {
            const policyInput = {
                step,
                workflow,
                execution_context: {
                    visited_step_ids: [...visited_step_ids],
                    completed_step_ids: [...completed_step_ids],
                    autonomy_level: workflow.autonomy_level,
                    recursion_depth,
                    // P2.3 fold: tenant_id is the cross-tenant decision surface.
                    // Undefined when the operator does not declare a tenant — Charters
                    // that read it then see `null`/missing and can encode their own
                    // policy ("require tenant_id" → deny when absent). Spread-only so
                    // we don't add `tenant_id: undefined` to the JSON (clean OPA input).
                    ...(options.tenant_id !== undefined ? { tenant_id: options.tenant_id } : {}),
                },
            };
            try {
                // Codex master review 2026-04-30 P2.1 fold: the dispatcher now takes
                // a bundle reference (policy_id + optional policy_version) — the
                // bundle service is the live source of truth for the compiled
                // policy. Carry policy_id from the supplied compiled_policy so the
                // executor's existing public surface (compiled_policy in options)
                // stays the operator-facing contract; the dispatcher handles
                // bundle.get() under the hood.
                const decision = await policy_dispatcher.dispatch_policy_eval({
                    kind: 'policy_eval',
                    policy_id: compiled_policy.policy_id,
                    policy_version: compiled_policy.policy_version,
                    input: policyInput,
                    // M8 Group Z (T-108) — propagate trace + identity so the dispatcher
                    // can emit POLICY_ALLOW / POLICY_DENY records sharing this run's
                    // trace_id. Spread-only so undefined fields don't appear on the cmd.
                    trace_id,
                    workflow_id: workflow.id,
                    step_id: step.step_id,
                    ...(agent_identity !== undefined ? { agent_identity } : {}),
                    ...(actor !== undefined ? { actor } : {}),
                });
                if (decision.kind === 'deny') {
                    policyDenied = true;
                    // errMsg format pinned by M7 Group V plan T-094 (P2.1 fold):
                    //   `policy_deny:<rule_name>:<reason>:<policy_version>`
                    // Downstream tools that parse failure_reason MUST match against
                    // this string prefix; do NOT reorder fields without a contract bump.
                    policyDenyError = new Error(`policy_deny:${decision.rule_name}:${decision.reason}:${decision.policy_version}`);
                }
            }
            catch (raw) {
                // Dispatcher itself threw (e.g. OPAUnavailableError). Per sovereignty
                // discipline, an unevaluable policy is treated as deny — the runtime
                // never fabricates an "approval" when authorization cannot be
                // verified. The errMsg surfaces the underlying failure so the operator
                // can diagnose (binary missing, timeout, parse error, etc.).
                policyDenied = true;
                const errMsg = raw instanceof Error ? raw.message : String(raw);
                policyDenyError = new Error(`policy_deny:dispatch_error:${errMsg}:${compiled_policy.policy_version}`);
            }
        }
        if (crossTenantDeniedError !== null) {
            // M9 Group FF (T-153). Cross-tenant boundary deny — synthesized step
            // failure routed via the existing M5 failure-policy switch (dispatcher
            // NOT called; the violating I/O never runs). Per the codex re-review
            // P1 fold convention, this fires BEFORE the policy gate so a charter
            // policy never has to reason about cross-tenant — sovereignty deny is
            // structural, policy is content.
            result = { kind: 'failure', error: crossTenantDeniedError };
        }
        else if (policyDenied) {
            // Synthesize a failure StepDispatchResult and let the existing failure-
            // policy switch route per step.on_failure. The dispatcher is NOT called
            // for this step — policy gate fires before any I/O for the step.
            result = { kind: 'failure', error: policyDenyError };
        }
        else if (step.action === 'invoke_host_llm') {
            // M8 Group BB (T-120). Host-LLM Activity dispatch — Claude --bare
            // first-class + codex advisory. The step contract was validated at
            // primitive-mint (`createWorkflow.validateStep` enforces host-XOR);
            // here we trust step.host is one of 'claude' | 'codex'.
            //
            // Prompt resolution (v1.0): the FIRST step input's `locator` field
            // carries the prompt string. Rationale: DataRef is the shared
            // input/output envelope across the engine; using `locator` keeps the
            // host-LLM step shape uniform with other Activity steps. Steps with no
            // inputs synthesize a step failure (`host_llm_invocation_failed:no_prompt`).
            // Future versions may extend to a typed prompt schema; v1.0 keeps the
            // contract simple — one input, one prompt.
            const host = step.host;
            const prompt = step.inputs.length > 0 && typeof step.inputs[0].locator === 'string'
                ? step.inputs[0].locator
                : null;
            if (prompt === null) {
                result = {
                    kind: 'failure',
                    error: new Error('host_llm_invocation_failed:no_prompt'),
                };
            }
            else {
                try {
                    const hostResult = await hostLLMActivity({
                        prompt,
                        host,
                        workflow_run_seq: getWorkflowRunSeq(workflow.id),
                    });
                    // Provenance stamp (T-121) — emit HOST_LLM_INVOCATION OTel event.
                    // Carries host_kind + host_version + invocation_id +
                    // prompt_hash + response_hash. Replay-determinism: the same
                    // (prompt, host, version, run_seq) yields identical hashes +
                    // invocation_id, so a replay produces a bit-identical event
                    // record (modulo the optional agent_identity / actor surface).
                    await emitHostLLMInvocation(otel_emitter, {
                        trace_id,
                        workflow_id: workflow.id,
                        step_id: step.step_id,
                        agent_identity,
                        actor,
                        host_result: hostResult,
                        prompt,
                    });
                    // Wrap response in V2 §A11 DataRef envelope (codex pivot review
                    // fold #5 alignment with M6 Skill output convention). Downstream
                    // consumers see kind='host-llm-output' and can lift the response
                    // text from locator='inline:<JSON>'.
                    //
                    // Codex master review 2026-04-30 P2.1 fold: schema_ref now uses
                    // `step.return_contract` (the response schema) — NOT the input
                    // prompt's schema_ref (which was a contract drift). When set, we
                    // also validate the response against the schema via ajv; a
                    // validation miss synthesizes a step failure with errMsg
                    // `host_llm_output_validation:<details>`. This parallels M6's
                    // skill-invocation.ts validateOutputs path (skill-invocation.ts:250-279
                    // sets schema_ref=resolved.return_contract and validates via ajv-
                    // backed SkillEngine.validateOutputs).
                    const validation = validateHostLLMOutput(hostResult.response, step.return_contract);
                    if (validation.kind === 'invalid') {
                        result = {
                            kind: 'failure',
                            error: new Error(`host_llm_output_validation:${validation.errors}`),
                        };
                    }
                    else {
                        const dataRef = {
                            kind: 'host-llm-output',
                            schema_ref: step.return_contract ?? '',
                            locator: 'inline:' + JSON.stringify(hostResult.response),
                            version: '1',
                            mutability: 'immutable',
                            retention: 'session',
                            authoritative_status: 'authoritative',
                        };
                        result = { kind: 'ok', outputs: [dataRef] };
                    }
                }
                catch (raw) {
                    // HostUnavailableError → host_llm_unavailable:<host>
                    // Other errors (subprocess failure, timeout) →
                    //   host_llm_invocation_failed:<reason>
                    // The executor synthesizes a step failure; the failure-policy
                    // switch downstream routes per step.on_failure exactly as for any
                    // other Activity failure (rollback / escalate / pause / abort /
                    // continue all reachable).
                    const errMsg = raw instanceof HostUnavailableError
                        ? `host_llm_unavailable:${raw.host}`
                        : raw instanceof Error
                            ? `host_llm_invocation_failed:${raw.message}`
                            : `host_llm_invocation_failed:${String(raw)}`;
                    result = { kind: 'failure', error: new Error(errMsg) };
                }
            }
        }
        else if (skill_engine !== undefined && typeof step.skill_ref === 'string') {
            // M6 Group P (T-073). Steps with `skill_ref` route through invokeSkill
            // when a SkillEngine is present in options. The adapter resolves the
            // Skill, runs an isolated child execution, validates the payload
            // against the cached return_contract, and returns either a validated
            // payload (translated below into a synthetic 'ok' StepDispatchResult)
            // or a canonical failure (translated into a synthetic 'failure'
            // StepDispatchResult so the existing failure-policy switch routes it
            // unchanged via M5).
            try {
                const invokeResult = await invokeSkill(step, {
                    skill_engine,
                    dispatch,
                    recursion_depth,
                    // M8 Group Z (T-108) — propagate trace + identity into invokeSkill
                    // so SKILL_RESOLVED / SKILL_UNRESOLVED / SKILL_RECURSION_CAP
                    // records share the parent run's trace_id + workflow_id.
                    ...(otel_emitter !== undefined ? { otel_emitter } : {}),
                    trace_id,
                    workflow_id: workflow.id,
                    ...(agent_identity !== undefined ? { agent_identity } : {}),
                    ...(actor !== undefined ? { actor } : {}),
                    // M9 codex master P1.1 fold — forward tenant context so the
                    // child re-entry honors the same operating-tenant + edges set.
                    ...(tenant_context_id !== undefined ? { tenant_context_id } : {}),
                    delegates_to_edges,
                });
                if (invokeResult.kind === 'success') {
                    // Record the cross-reference edge BEFORE pushing visited/completed
                    // — keeps the relative order obvious to readers.
                    child_edges.push({
                        step_id: step.step_id,
                        skill_ref: invokeResult.skill_ref,
                        child_execution_id: invokeResult.child_execution_id,
                        validated_dataref: invokeResult.validated_dataref,
                    });
                    // Translate to the dispatcher-shaped success result. The DataRef
                    // envelope (V2 §A11; codex master 2026-04-30 P1.1 fold) becomes
                    // the parent step's outputs[0]; the executor's ok-branch below
                    // handles visited/completed bookkeeping uniformly — codex P1.3
                    // isolation is preserved because the child's visited/completed
                    // lists were captured inside the child's ExecutionResult (NOT
                    // mutated into the parent's lists).
                    result = { kind: 'ok', outputs: [invokeResult.validated_dataref] };
                }
                else {
                    // Synthesize a step failure with the canonical errMsg. The
                    // failure-policy switch downstream will route per step.on_failure
                    // exactly as if the dispatcher had thrown — keeping all 5 routes
                    // (rollback / escalate / pause / abort / continue) reachable for
                    // skill_unresolved / skill_output_validation / skill_recursion_cap.
                    result = { kind: 'failure', error: new Error(invokeResult.errMsg) };
                }
            }
            catch (raw) {
                // Invariant guard: invokeSkill is contracted to never throw for
                // expected failure paths. If it does (programmer error in the
                // adapter), surface it as a step failure so the executor stays
                // crash-free.
                const err = raw instanceof Error ? raw : new Error(String(raw));
                result = { kind: 'failure', error: err };
            }
        }
        else {
            try {
                result = await Promise.resolve(dispatch(descriptor, dispatchCtx));
            }
            catch (raw) {
                const err = raw instanceof Error ? raw : new Error(String(raw));
                result = { kind: 'failure', error: err };
            }
        }
        if (result.kind === 'ok') {
            // Successful effect → both visited + completed.
            visited_step_ids.push(step.step_id);
            completed_step_ids.push(step.step_id);
            step_outputs.push({
                step_id: step.step_id,
                outputs: result.outputs,
                output_validation_skipped: false,
            });
            // M8 Group Z (T-108). STEP_COMPLETE — outputs_hash is a stable digest
            // of the outputs payload for downstream tamper-detection / replay
            // verification. JSON.stringify is order-preserving for arrays (which
            // is what `outputs` is); for objects inside, downstream consumers MUST
            // accept that key order is JS-engine-dependent. v1.0 is fine because
            // emission is informational, not a forensic anchor.
            await emitStepEvent(otel_emitter, 'STEP_COMPLETE', {
                trace_id,
                workflow_id: workflow.id,
                step_id: step.step_id,
                agent_identity,
                actor,
                attributes: {
                    outputs_hash: hashOutputs(result.outputs),
                },
            });
            continue;
        }
        if (result.kind === 'child_result') {
            // V2.3 §A11 — action='spawn_sub_unit' delegates to a child Workflow.
            // Outputs from the child propagate as this step's outputs. Successful
            // child invocation → both visited + completed.
            visited_step_ids.push(step.step_id);
            completed_step_ids.push(step.step_id);
            step_outputs.push({
                step_id: step.step_id,
                outputs: result.outputs,
                output_validation_skipped: false,
            });
            child_workflows.push({
                step_id: step.step_id,
                child_workflow_id: result.child_workflow_id,
            });
            // M8 Group Z (T-108). STEP_COMPLETE for the spawn_sub_unit branch —
            // child_workflow_id surfaces alongside outputs_hash so observability
            // can trace into the child's ExecutionResult.
            await emitStepEvent(otel_emitter, 'STEP_COMPLETE', {
                trace_id,
                workflow_id: workflow.id,
                step_id: step.step_id,
                agent_identity,
                actor,
                attributes: {
                    outputs_hash: hashOutputs(result.outputs),
                    child_workflow_id: result.child_workflow_id,
                },
            });
            continue;
        }
        // Failure — route via failure_policy. Pass success-only completed list,
        // NOT visited (codex P1.1): rollback compensation must reverse only steps
        // that produced effects, never failed-continue steps.
        const policyCtx = {
            completed_step_ids: [...completed_step_ids],
            autonomy_level: workflow.autonomy_level,
            escalation_target: options.escalation_target,
        };
        // M8 Group Z (T-108). STEP_FAIL emitted before failure-policy routing so
        // observability sees the raw failure reason; failure-policy then emits
        // FAILURE_POLICY_<OUTCOME> with the routing decision (T-109).
        await emitStepEvent(otel_emitter, 'STEP_FAIL', {
            trace_id,
            workflow_id: workflow.id,
            step_id: step.step_id,
            agent_identity,
            actor,
            attributes: {
                failure_reason: result.error.message,
                on_failure: step.on_failure,
            },
        });
        const outcome = applyFailurePolicy(step, result.error, policyCtx, {
            ...(otel_emitter !== undefined ? { otel_emitter } : {}),
            trace_id,
            workflow_id: workflow.id,
            ...(agent_identity !== undefined ? { agent_identity } : {}),
            ...(actor !== undefined ? { actor } : {}),
        });
        switch (outcome.action) {
            case 'continue': {
                // Codex P1.3 — log + advance to step[i+1]; partial=true; skip output validation.
                // Codex P1.1 — push to visited (trace) but NOT completed (no successful
                // effect). Subsequent failure-policy / rollback uses completed_step_ids
                // and therefore correctly excludes this step.
                partial = true;
                visited_step_ids.push(step.step_id);
                step_outputs.push({
                    step_id: step.step_id,
                    outputs: [],
                    output_validation_skipped: true,
                });
                // continue loop (advance to step[i+1])
                continue;
            }
            case 'abort': {
                // Failed step → visited only, NOT completed.
                visited_step_ids.push(step.step_id);
                // Codex master P1.2 fold: HS-2 priority over failure-policy reason
                // when the breach happened during this step. The HS-2 helper checks
                // band; only halts when 'red'. Otherwise return the failure-policy
                // outcome unchanged.
                {
                    const halt = await hs2Halt(step.step_id);
                    if (halt !== null)
                        return halt;
                }
                return {
                    workflow_id: workflow.id,
                    visited_step_ids,
                    completed_step_ids,
                    step_outputs,
                    state: 'failed',
                    failure_reason: outcome.reason,
                    partial,
                    ...(child_workflows.length > 0 ? { child_workflows } : {}),
                    ...(child_edges.length > 0 ? { child_edges } : {}),
                };
            }
            case 'rollback': {
                // Failed step → visited only, NOT completed. Compensation_order
                // already came from failure-policy applied to completed-only ctx.
                visited_step_ids.push(step.step_id);
                {
                    const halt = await hs2Halt(step.step_id);
                    if (halt !== null)
                        return halt;
                }
                return {
                    workflow_id: workflow.id,
                    visited_step_ids,
                    completed_step_ids,
                    step_outputs,
                    state: 'failed',
                    failure_reason: outcome.reason,
                    partial,
                    rollback_compensations: outcome.compensation_order,
                    ...(child_workflows.length > 0 ? { child_workflows } : {}),
                    ...(child_edges.length > 0 ? { child_edges } : {}),
                };
            }
            case 'pause': {
                // Failed step → visited only, NOT completed.
                visited_step_ids.push(step.step_id);
                {
                    const halt = await hs2Halt(step.step_id);
                    if (halt !== null)
                        return halt;
                }
                return {
                    workflow_id: workflow.id,
                    visited_step_ids,
                    completed_step_ids,
                    step_outputs,
                    state: 'paused',
                    failure_reason: outcome.reason,
                    partial,
                    resume_token: outcome.resume_token,
                    ...(child_workflows.length > 0 ? { child_workflows } : {}),
                    ...(child_edges.length > 0 ? { child_edges } : {}),
                };
            }
            case 'escalate': {
                // Failed step → visited only, NOT completed.
                visited_step_ids.push(step.step_id);
                {
                    const halt = await hs2Halt(step.step_id);
                    if (halt !== null)
                        return halt;
                }
                return {
                    workflow_id: workflow.id,
                    visited_step_ids,
                    completed_step_ids,
                    step_outputs,
                    state: 'escalated',
                    failure_reason: outcome.reason,
                    partial,
                    escalation_target: outcome.escalation_target,
                    ...(child_workflows.length > 0 ? { child_workflows } : {}),
                    ...(child_edges.length > 0 ? { child_edges } : {}),
                };
            }
        }
    }
    // Codex master P1.2 fold — final HS-2 check at natural end-of-graph
    // before terminalCheckProbe / success exit. If the LAST step pushed
    // overhead into the red zone, HS-2 must take priority over the success
    // path so the run reports `failure_reason='hs2_overhead_exceeded'`
    // rather than `null` (which would lie about the overheaded run).
    {
        const lastStepId = workflow.step_graph[workflow.step_graph.length - 1]?.step_id ?? -1;
        const halt = await hs2Halt(lastStepId);
        if (halt !== null)
            return halt;
    }
    // T-051 — terminate stage (or natural end-of-graph): run terminalCheck probe.
    // The probe is optional; absent ⇒ no failure_reason from F-1..F-12, but step
    // failures (handled above) still set failure_reason via failure-policy.
    if (options.terminalCheckProbe) {
        const violations = options.terminalCheckProbe();
        const reason = formatTerminalCheckFailureReason(violations);
        if (reason !== null) {
            return {
                workflow_id: workflow.id,
                visited_step_ids,
                completed_step_ids,
                step_outputs,
                state: 'failed',
                failure_reason: reason,
                partial,
                ...(child_workflows.length > 0 ? { child_workflows } : {}),
                ...(child_edges.length > 0 ? { child_edges } : {}),
            };
        }
    }
    // success path — no abort, no rollback, no escalate, no pause, no
    // terminalCheck violation. partial may still be true if any step's
    // on_failure='continue' fired (in which case visited_step_ids ⊃ completed_step_ids).
    return {
        workflow_id: workflow.id,
        visited_step_ids,
        completed_step_ids,
        step_outputs,
        state: 'success',
        failure_reason: null,
        partial,
        ...(child_workflows.length > 0 ? { child_workflows } : {}),
        ...(child_edges.length > 0 ? { child_edges } : {}),
    };
}
// =============================================================================
// M8 Group Z (T-108) — emission helpers
// =============================================================================
/**
 * Emit a STEP_* event when an emitter is configured. Errors swallowed —
 * observability failures must not break Workflow execution.
 *
 * Defined as a private module helper (NOT exported on the engine barrel) so
 * the only public emit-surface is via the OTelEmitter passed in via options.
 */
async function emitStepEvent(emitter, kind, fields) {
    if (emitter === undefined)
        return;
    try {
        await emitter.emit({
            decision_kind: kind,
            trace_id: fields.trace_id,
            workflow_id: fields.workflow_id,
            step_id: fields.step_id,
            ...(fields.agent_identity !== undefined ? { agent_identity: fields.agent_identity } : {}),
            ...(fields.actor !== undefined ? { actor: fields.actor } : {}),
            attributes: fields.attributes,
        });
    }
    catch {
        // observability failure must NEVER break execution
    }
}
/**
 * M8 Group BB (T-121). Emit a HOST_LLM_INVOCATION OTel event per host-LLM
 * Activity dispatch. Carries host_kind + host_version + invocation_id +
 * prompt_hash + response_hash + tokens_used (when host reports).
 *
 * Provenance contract (codex pivot review fold #5):
 *   - host_kind  + host_version : the FULL host identity at the moment of
 *     the call. Replay verification uses this to detect "we ran the same
 *     prompt against a different host_version" silently.
 *   - invocation_id : sha256(prompt + host + version + run_seq).slice(0,32)
 *     — same id on replay; downstream observability deduplicates.
 *   - prompt_hash + response_hash : sha256 truncated to 32 hex chars.
 *     Storing only hashes (not the text) keeps the OTel event compact and
 *     respects "audit trail without exposing prompt/response surface".
 *
 * Hashes are clock-free + order-deterministic — replay produces a
 * bit-identical event record.
 */
async function emitHostLLMInvocation(emitter, fields) {
    if (emitter === undefined)
        return;
    const prompt_hash = createHash('sha256').update(fields.prompt).digest('hex').slice(0, 32);
    const response_hash = createHash('sha256').update(fields.host_result.response).digest('hex').slice(0, 32);
    try {
        await emitter.emit({
            decision_kind: 'HOST_LLM_INVOCATION',
            trace_id: fields.trace_id,
            workflow_id: fields.workflow_id,
            step_id: fields.step_id,
            ...(fields.agent_identity !== undefined ? { agent_identity: fields.agent_identity } : {}),
            // Host-LLM provenance default actor — when caller did not supply one,
            // tag with the activity's stable identifier so downstream observability
            // can filter HOST_LLM_INVOCATION events without an explicit actor field
            // on every executor caller.
            actor: fields.actor ?? 'sutra-native:host-llm-activity',
            attributes: {
                host_kind: fields.host_result.host_kind,
                host_version: fields.host_result.host_version,
                invocation_id: fields.host_result.invocation_id,
                prompt_hash,
                response_hash,
                tokens_used: fields.host_result.tokens_used ?? null,
            },
        });
    }
    catch {
        // observability failure must NEVER break execution
    }
}
/**
 * Stable, deterministic digest of a step's outputs payload. Pure function —
 * no clock, no random. Uses sha256 over JSON.stringify; truncated to 16 hex
 * chars for compactness (collision probability is acceptable for an
 * informational tag, not a forensic anchor).
 *
 * `JSON.stringify` is order-preserving for arrays and follows insertion order
 * for plain objects — sufficient for v1.0. If forensic-grade hashing is
 * required at M11, swap to a canonicalizing serializer (e.g. JCS).
 */
function hashOutputs(outputs) {
    const json = JSON.stringify(outputs);
    return createHash('sha256').update(json).digest('hex').slice(0, 16);
}
//# sourceMappingURL=step-graph-executor.js.map