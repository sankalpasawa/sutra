/**
 * L4 TERMINAL-CHECK predicates (T1-T6) — V2.4 §A12
 * AND 10 schema-level forbidden couplings (F-1..F-8, F-10, F-11) — D4 §3 (M4.9 + Group G' fix-up)
 *
 * Closes V2 §9 OPEN ("6 terminal-check tests need formal definitions"):
 *
 *   T1. forall p in Workflow.postconditions: p(outputs) == true
 *   T2. forall o in outputs: validate(o, o.schema_ref) == ok
 *   T3. forall s in step_graph:
 *         s.traces_to ⊆ Charter.obligations ∪ Charter.invariants
 *         OR s.gap_status == 'accepted'
 *   T4. forall i in interfaces_with: contract_violations(i) == 0
 *   T5. forall e in children where e.parent_exec_id == self.id:
 *         e.state ∈ {success, declared_gap, escalated}
 *   T6. if Workflow.modifies_sutra:
 *         founder_authorization == true
 *         OR meta_charter_approval == true
 *
 * Workflow Execution reaches `state = success` iff ALL six predicates hold.
 * Any T_i == false → state = failed; failure_reason = `terminal_check_failed:T<i>`.
 *
 * For M3 these are pure predicate functions. The Workflow Engine (M5) will
 * invoke them at the `terminate` stage and route failure_policy + escalation
 * TriggerSpec on T6 failure.
 *
 * M4.9 Group D (D4 §3) — first 4 schema-level forbidden couplings land here:
 * F-1..F-4. Group E (F-5..F-8) and Group F (F-10 + aggregator) follow in
 * subsequent commits. Group G' adds F-11 (extension_ref null in v1.0).
 * F-9 (D38 plugin shipment) is hook-level and DEFERRED to M8 per codex P1.3
 * pre-dispatch.
 *
 * Source-of-truth:
 *  - holding/research/2026-04-28-v2-architecture-spec.md §19 §A12
 *  - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §3
 *  - holding/plans/native-v1.0/M4-schemas-edges.md M4.9
 */
import { l4Commitment } from './l4-commitment.js';
import { ROUTING_GATING_POSITIONS, allRoutingGatingMachineCheckable, } from './routing-gating-positions.js';
// -----------------------------------------------------------------------------
// Individual predicate functions — exported so Workflow Engine can run them
// individually for telemetry granularity.
// -----------------------------------------------------------------------------
/**
 * T1 — forall p in Workflow.postconditions: p(outputs) == true.
 *
 * The base Workflow.postconditions field is a string (per V2.3 §A11). The
 * Workflow Engine compiles it into one or more pure predicates over outputs;
 * we accept those compiled predicates as input.
 *
 * Empty predicate list ⇒ vacuously true (postcondition string was empty).
 */
export function t1Postconditions(predicates, outputs) {
    if (!Array.isArray(predicates))
        return false;
    if (!Array.isArray(outputs))
        return false;
    for (const p of predicates) {
        if (typeof p !== 'function')
            return false;
        let ok;
        try {
            ok = p(outputs) === true;
        }
        catch {
            return false;
        }
        if (!ok)
            return false;
    }
    return true;
}
/**
 * T2 — forall o in outputs: validate(o, o.schema_ref) == ok.
 *
 * `validators[i]` is the compiled validator for `outputs[i]`. Length mismatch
 * is treated as failure (defensive — the Engine MUST provide one validator
 * per output).
 */
export function t2OutputSchemas(outputs, validators) {
    if (!Array.isArray(outputs))
        return false;
    if (!Array.isArray(validators))
        return false;
    if (outputs.length !== validators.length)
        return false;
    for (let i = 0; i < outputs.length; i++) {
        const v = validators[i];
        if (typeof v !== 'function')
            return false;
        try {
            if (v(outputs[i]) !== true)
                return false;
        }
        catch {
            return false;
        }
    }
    return true;
}
/**
 * T3 — forall s in step_graph:
 *        s.traces_to ⊆ Charter.obligations ∪ Charter.invariants
 *        OR s.gap_status == 'accepted'
 *
 * Reuses L4 `tracesAllSteps`.
 */
export function t3StepTraces(workflow, charter, coverage) {
    return l4Commitment.tracesAllSteps(workflow, charter, coverage);
}
/**
 * T4 — forall i in interfaces_with: contract_violations(i) == 0.
 *
 * Length must match `workflow.interfaces_with` (one violations view per
 * interface). Any non-zero count → fail.
 */
export function t4InterfaceContracts(workflow, views) {
    if (typeof workflow !== 'object' || workflow === null)
        return false;
    const interfaces = workflow.interfaces_with;
    if (!Array.isArray(interfaces))
        return false;
    if (!Array.isArray(views))
        return false;
    if (interfaces.length !== views.length)
        return false;
    for (const v of views) {
        if (typeof v !== 'object' || v === null)
            return false;
        if (typeof v.contract_violations !== 'number')
            return false;
        if (v.contract_violations !== 0)
            return false;
    }
    return true;
}
/**
 * T5 — forall e in children where e.parent_exec_id == self.id:
 *        e.state ∈ {success, declared_gap, escalated}
 *
 * Children with a different parent_exec_id (or null) are ignored — they
 * weren't spawned by this execution. Note `failed` is NOT a permitted
 * terminal state for a child (V2.4 §A12 T5: no abandoned children).
 * `running`/`pending` children also fail T5 (they're "abandoned" at parent
 * terminate time).
 */
export function t5NoAbandonedChildren(selfExecutionId, children) {
    if (typeof selfExecutionId !== 'string' || selfExecutionId.length === 0)
        return false;
    if (!Array.isArray(children))
        return false;
    const allowed = new Set(['success', 'declared_gap', 'escalated']);
    for (const child of children) {
        if (typeof child !== 'object' || child === null)
            return false;
        if (child.parent_exec_id !== selfExecutionId)
            continue;
        if (!allowed.has(child.state))
            return false;
    }
    return true;
}
/**
 * T6 — if Workflow.modifies_sutra:
 *        founder_authorization == true OR meta_charter_approval == true
 *
 * No-op (always true) when modifies_sutra=false. When true, exactly one auth
 * token must be true.
 */
export function t6ReflexiveAuth(workflow, auth) {
    if (typeof workflow !== 'object' || workflow === null)
        return false;
    if (typeof workflow.modifies_sutra !== 'boolean')
        return false;
    if (!workflow.modifies_sutra)
        return true;
    if (typeof auth !== 'object' || auth === null)
        return false;
    if (typeof auth.founder_authorization !== 'boolean')
        return false;
    if (typeof auth.meta_charter_approval !== 'boolean')
        return false;
    return auth.founder_authorization === true || auth.meta_charter_approval === true;
}
// -----------------------------------------------------------------------------
// Aggregate runner
// -----------------------------------------------------------------------------
export const l4TerminalCheck = {
    /**
     * Run T1-T6 in order; return the first failure or PASS.
     *
     * Workflow Engine maps the result to:
     *   - pass=true  → Execution.state = 'success'
     *   - pass=false → Execution.state = 'failed';
     *                  Execution.failure_reason = `terminal_check_failed:${failed_at}`
     */
    runAll(ctx) {
        if (typeof ctx !== 'object' || ctx === null) {
            return {
                pass: false,
                failed_at: 'T1',
                failure_reason: 'terminal_check_failed:T1 (invalid context)',
            };
        }
        const outputs = ctx.workflow.outputs;
        if (!t1Postconditions(ctx.postcondition_predicates, outputs)) {
            return { pass: false, failed_at: 'T1', failure_reason: 'terminal_check_failed:T1' };
        }
        if (!t2OutputSchemas(outputs, ctx.output_validators)) {
            return { pass: false, failed_at: 'T2', failure_reason: 'terminal_check_failed:T2' };
        }
        if (!t3StepTraces(ctx.workflow, ctx.charter, ctx.coverage)) {
            return { pass: false, failed_at: 'T3', failure_reason: 'terminal_check_failed:T3' };
        }
        if (!t4InterfaceContracts(ctx.workflow, ctx.interface_violations)) {
            return { pass: false, failed_at: 'T4', failure_reason: 'terminal_check_failed:T4' };
        }
        if (!t5NoAbandonedChildren(ctx.self_execution_id, ctx.children)) {
            return { pass: false, failed_at: 'T5', failure_reason: 'terminal_check_failed:T5' };
        }
        if (!t6ReflexiveAuth(ctx.workflow, ctx.reflexive_auth)) {
            return { pass: false, failed_at: 'T6', failure_reason: 'terminal_check_failed:T6' };
        }
        return { pass: true, failed_at: null, failure_reason: null };
    },
    // Direct exports for granular callers (e.g. telemetry per-T).
    t1: t1Postconditions,
    t2: t2OutputSchemas,
    t3: t3StepTraces,
    t4: t4InterfaceContracts,
    t5: t5NoAbandonedChildren,
    t6: t6ReflexiveAuth,
};
/**
 * F-1 — Tenant directly contains Workflow (skips Domain + Charter).
 *
 * D4 §3: L5 META preserves only `Domain.contains.Charter` as a containment
 * edge. Tenant is sovereignty-not-containment; it MUST NOT directly contain a
 * Workflow.
 *
 * v1.0 schema-level enforcement: there is no direct Tenant→Workflow containment
 * edge schema; the edges file ships only `owns` (Tenant→Domain),
 * `delegates_to` (Tenant→Tenant), and `emits` (W/E/Hook→DP). A "containment
 * edge" here means an external graph asserting Tenant.id is the immediate
 * parent of Workflow.id with no intervening Domain + Charter. The predicate
 * accepts the optional `containment_chain` and returns true (VIOLATION) iff
 * the chain skips Domain or Charter.
 *
 * @returns true iff F-1 VIOLATION (Tenant immediately above Workflow with no
 *   Domain + Charter in between)
 */
export function f1Predicate(input) {
    const { tenant, workflow, containment_chain } = input;
    if (!Array.isArray(containment_chain))
        return false;
    if (containment_chain.length < 2)
        return false;
    const head = containment_chain[0];
    const tail = containment_chain[containment_chain.length - 1];
    if (head !== tenant.id)
        return false;
    if (tail !== workflow.id)
        return false;
    // VIOLATION iff chain has length 2 (no Domain + Charter in between)
    if (containment_chain.length === 2)
        return true;
    // Or if chain has any length but no D-* or no C-* between head and tail.
    const middle = containment_chain.slice(1, -1);
    const hasDomain = middle.some((s) => typeof s === 'string' && /^D\d+(\.D\d+)*$/.test(s));
    const hasCharter = middle.some((s) => typeof s === 'string' && /^C-.+$/.test(s));
    return !(hasDomain && hasCharter);
}
/**
 * F-2 — Workflow without operationalizes link to Charter.
 *
 * D4 §3 + L4 COMMITMENT: every Workflow MUST ladder to a Charter
 * obligation/invariant or declared gap. A Workflow with NO operationalizes
 * link to ANY Charter is a forbidden coupling.
 *
 * Inputs: a Workflow + its observed `operationalizes_charters` list (charter
 * ids the Workflow claims to operationalize). Empty list ⇒ VIOLATION.
 *
 * Note: F-2 is a "link exists" check; the deeper "every step traces to a
 * Charter obligation" check is L4 COMMITMENT (already shipped at M3 via
 * `l4Commitment.operationalizes`).
 *
 * @returns true iff F-2 VIOLATION (Workflow has no operationalizes link)
 */
export function f2Predicate(input) {
    const { operationalizes_charters } = input;
    if (!Array.isArray(operationalizes_charters))
        return true;
    return operationalizes_charters.length === 0;
}
/**
 * F-3 — Execution spawned without TriggerEvent.
 *
 * D4 §3 + L3 ACTIVATION: Executions are NOT free-standing; every Execution
 * must reference the TriggerEvent that activated it. The Execution primitive
 * carries `trigger_event` (V2 §1 P4) which MUST be a non-empty string.
 *
 * @returns true iff F-3 VIOLATION (trigger_event missing or empty)
 */
export function f3Predicate(input) {
    const { execution } = input;
    if (typeof execution !== 'object' || execution === null)
        return true;
    if (typeof execution.trigger_event !== 'string')
        return true;
    return execution.trigger_event.length === 0;
}
/**
 * F-4 — step_graph[i] with both skill_ref AND action set.
 *
 * V2.3 §A11: skill_ref XOR action — mutually exclusive. Both set ⇒ VIOLATION.
 *
 * @returns true iff F-4 VIOLATION (some step has both)
 */
export function f4Predicate(input) {
    const { workflow } = input;
    if (typeof workflow !== 'object' || workflow === null)
        return false;
    if (!Array.isArray(workflow.step_graph))
        return false;
    for (const step of workflow.step_graph) {
        const hasSkill = typeof step.skill_ref === 'string' && step.skill_ref.length > 0;
        const hasAction = typeof step.action === 'string' && step.action.length > 0;
        if (hasSkill && hasAction)
            return true;
    }
    return false;
}
/**
 * F-5 — step_graph[i] with neither skill_ref NOR action.
 *
 * L2 BOUNDARY: every step MUST specify what it does — either a skill_ref or
 * an action. Neither set ⇒ VIOLATION.
 *
 * @returns true iff F-5 VIOLATION (some step has neither)
 */
export function f5Predicate(input) {
    const { workflow } = input;
    if (typeof workflow !== 'object' || workflow === null)
        return false;
    if (!Array.isArray(workflow.step_graph))
        return false;
    for (const step of workflow.step_graph) {
        const hasSkill = typeof step.skill_ref === 'string' && step.skill_ref.length > 0;
        const hasAction = typeof step.action === 'string' && step.action.length > 0;
        if (!hasSkill && !hasAction)
            return true;
    }
    return false;
}
/**
 * F-6 — Cross-tenant operation without TenantDelegation.
 *
 * D1 P-B8 + D4 §3: cross-tenant access requires explicit `delegates_to` edge
 * between source and target tenants. A Workflow whose `custody_owner` differs
 * from the operating tenant — without a `delegates_to` edge linking the two —
 * is a forbidden coupling.
 *
 * Inputs: the Workflow + the operating tenant id + the registered
 * delegates_to edge set. If `workflow.custody_owner` is null OR equals
 * `operating_tenant_id`, no cross-tenant op is occurring (no F-6 risk).
 * Otherwise we check for a delegates_to edge with
 * source=operating_tenant_id, target=workflow.custody_owner.
 *
 * @returns true iff F-6 VIOLATION (cross-tenant op without delegates_to edge)
 */
export function f6Predicate(input) {
    const { workflow, operating_tenant_id, delegates_to_edges } = input;
    if (typeof workflow !== 'object' || workflow === null)
        return false;
    // Single-tenant or matching custody — no cross-tenant op.
    if (workflow.custody_owner === null || workflow.custody_owner === undefined)
        return false;
    if (workflow.custody_owner === operating_tenant_id)
        return false;
    // Cross-tenant op detected; require delegates_to edge.
    if (!Array.isArray(delegates_to_edges))
        return true;
    for (const e of delegates_to_edges) {
        if (typeof e === 'object' &&
            e !== null &&
            e.kind === 'delegates_to' &&
            e.source === operating_tenant_id &&
            e.target === workflow.custody_owner) {
            return false;
        }
    }
    return true;
}
/**
 * F-7 — Workflow.modifies_sutra=true without reflexive_check Constraint cleared.
 *
 * V2.1 §A6 L6 REFLEXIVITY: a Workflow that modifies Sutra primitives MUST
 * carry an explicit `reflexive_check` Constraint with founder OR meta-charter
 * authorization. M3 shipped L6 (`l6Reflexivity`) and T6 (in this file).
 *
 * F-7 is the schema-level invariant that mirrors the runtime gate: the
 * Workflow declares modifies_sutra=true AND no reflexive_check Constraint
 * cleared. Cleared = founder_authorization OR meta_charter_approval.
 *
 * @returns true iff F-7 VIOLATION (modifies_sutra=true with no cleared
 *   reflexive_check)
 */
export function f7Predicate(input) {
    const { workflow, reflexive_auth } = input;
    if (typeof workflow !== 'object' || workflow === null)
        return false;
    if (workflow.modifies_sutra !== true)
        return false;
    if (typeof reflexive_auth !== 'object' || reflexive_auth === null)
        return true;
    const cleared = reflexive_auth.founder_authorization === true ||
        reflexive_auth.meta_charter_approval === true;
    return !cleared;
}
/**
 * F-8 — DecisionProvenance without policy_id + policy_version co-present.
 *
 * D2 P-A3 + D4 §3: every consequential decision must reference the policy +
 * version it was made under. The DecisionProvenance schema (M4.3) requires
 * both as `min(1)`; F-8 is the cross-coupling check at terminal_check —
 * if a DP record arrives at terminal time without both fields, VIOLATION.
 *
 * @returns true iff F-8 VIOLATION (policy_id or policy_version missing/empty)
 */
export function f8Predicate(input) {
    const { dp } = input;
    if (typeof dp !== 'object' || dp === null)
        return true;
    const hasId = typeof dp.policy_id === 'string' && dp.policy_id.length > 0;
    const hasVer = typeof dp.policy_version === 'string' && dp.policy_version.length > 0;
    return !(hasId && hasVer);
}
/**
 * F-10 — English-only fields in routing/gating positions.
 *
 * V2 §3 HARD: every routing/gating field decides which branch executes; it
 * MUST have a typed representation OR a typed parser. The 10 positions are
 * inventoried in `routing-gating-positions.ts`. F-10 VIOLATION = any position
 * lacks a registered representation kind.
 *
 * Inverted from `allRoutingGatingMachineCheckable` which returns true when
 * all 10 positions register a representation kind.
 *
 * @returns true iff F-10 VIOLATION (any position is English-only / unregistered)
 */
export function f10Predicate() {
    return !allRoutingGatingMachineCheckable();
}
/**
 * F-11 — Workflow.extension_ref non-null in v1.0.
 *
 * D4 §7.3: `extension_ref MUST be null in v1.0`. The schema-level
 * ExtensionRefSchema accepts both null AND well-formed `ext-<id>` strings (so
 * v1.x callers compile); the v1.0-only "must be null" gate lives here at
 * terminal_check.
 *
 * Source comments at `src/types/extension.ts:9-16` and
 * `src/primitives/workflow.ts:282-285` say enforcement happens at
 * terminal_check; codex M4 master review (2026-04-29) caught that the
 * predicate was missing — added here in Group G' fix-up.
 *
 * @returns true iff F-11 VIOLATION (extension_ref is non-null)
 */
export function f11Predicate(input) {
    const { workflow } = input;
    if (typeof workflow !== 'object' || workflow === null)
        return false;
    return workflow.extension_ref !== null;
}
export { ROUTING_GATING_POSITIONS };
/**
 * Aggregate F-1..F-8, F-10, F-11 forbidden-coupling check.
 *
 * Returns `{ pass: true, violations: [] }` iff ALL 10 predicates clear; otherwise
 * `pass: false` with the full list of `ForbiddenCouplingId` values that fired.
 *
 * Caller integration (M5 Workflow Engine):
 *  - on `pass: false`, dispatch fails the Workflow with
 *    `failure_reason = 'forbidden_coupling:F-N,F-M'` (joined) and routes per
 *    `Workflow.failure_policy`.
 */
export function terminalCheck(input) {
    const violations = [];
    if (Array.isArray(input.containment_chain)) {
        if (f1Predicate({
            tenant: input.tenant,
            workflow: input.workflow,
            containment_chain: input.containment_chain,
        })) {
            violations.push('F-1');
        }
    }
    if (f2Predicate({
        workflow: input.workflow,
        operationalizes_charters: input.operationalizes_charters,
    })) {
        violations.push('F-2');
    }
    if (f3Predicate({ execution: input.execution })) {
        violations.push('F-3');
    }
    if (f4Predicate({ workflow: input.workflow })) {
        violations.push('F-4');
    }
    if (f5Predicate({ workflow: input.workflow })) {
        violations.push('F-5');
    }
    if (f6Predicate({
        workflow: input.workflow,
        operating_tenant_id: input.operating_tenant_id ?? input.tenant.id,
        delegates_to_edges: input.delegates_to_edges ?? [],
    })) {
        violations.push('F-6');
    }
    if (f7Predicate({ workflow: input.workflow, reflexive_auth: input.reflexive_auth })) {
        violations.push('F-7');
    }
    if (input.dp !== null && input.dp !== undefined) {
        if (f8Predicate({ dp: input.dp })) {
            violations.push('F-8');
        }
    }
    if (f10Predicate()) {
        violations.push('F-10');
    }
    if (f11Predicate({ workflow: input.workflow })) {
        violations.push('F-11');
    }
    return {
        pass: violations.length === 0,
        violations,
    };
}
//# sourceMappingURL=l4-terminal-check.js.map