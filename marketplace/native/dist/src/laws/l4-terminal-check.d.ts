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
import type { Asset, Constraint, DataRef } from '../types/index.js';
import type { Charter } from '../primitives/charter.js';
import type { Execution } from '../primitives/execution.js';
import type { Workflow } from '../primitives/workflow.js';
import { type CoverageMatrix } from './l4-commitment.js';
import type { Tenant } from '../schemas/tenant.js';
import type { DelegatesToEdge } from '../types/edges.js';
import type { DecisionProvenance } from '../schemas/decision-provenance.js';
import { ROUTING_GATING_POSITIONS, type RoutingGatingPosition } from './routing-gating-positions.js';
/**
 * Per-output schema validator. Workflow Engine (M5) wires Ajv here; M3 accepts
 * any pre-compiled validator function. Returns true on schema match, false
 * (or throws) on mismatch.
 */
export type SchemaValidator = (output: DataRef | Asset) => boolean;
/**
 * Interface contract violations counter (V2.4 §A12 T4 source).
 * Workflow Engine maintains this at the dispatch stage; M3 reads only.
 */
export interface InterfaceViolationsView {
    contract_violations: number;
}
/**
 * Reflexive auth tokens (V2.4 §A12 T6 + V2.1 §A6 L6).
 * Either flag set to true clears the L6 gate.
 */
export interface ReflexiveAuth {
    founder_authorization: boolean;
    meta_charter_approval: boolean;
}
/**
 * Inputs to `runAll` — bundles the per-T inputs the Workflow Engine
 * collects at the terminate stage.
 */
export interface TerminalCheckContext {
    workflow: Workflow;
    charter: Charter;
    /** Per-postcondition predicate functions (T1). */
    postcondition_predicates: Array<(outputs: ReadonlyArray<DataRef | Asset>) => boolean>;
    /** Per-output validators keyed by output index (T2). */
    output_validators: SchemaValidator[];
    /** Step + obligation coverage matrix (T3) per L4. */
    coverage: CoverageMatrix;
    /** Per-Interface contract-violations view (T4). */
    interface_violations: InterfaceViolationsView[];
    /** Children of this Execution (T5). */
    children: Execution[];
    /** Reflexive auth tokens (T6). */
    reflexive_auth: ReflexiveAuth;
    /** This execution's id (used to filter children by parent_exec_id for T5). */
    self_execution_id: string;
}
export type TerminalCheckId = 'T1' | 'T2' | 'T3' | 'T4' | 'T5' | 'T6';
export interface TerminalCheckResult {
    pass: boolean;
    /** First failing T_i (e.g. 'T2') if pass=false; null if pass=true. */
    failed_at: TerminalCheckId | null;
    /** Concise reason string suitable for Execution.failure_reason. */
    failure_reason: string | null;
}
/**
 * T1 — forall p in Workflow.postconditions: p(outputs) == true.
 *
 * The base Workflow.postconditions field is a string (per V2.3 §A11). The
 * Workflow Engine compiles it into one or more pure predicates over outputs;
 * we accept those compiled predicates as input.
 *
 * Empty predicate list ⇒ vacuously true (postcondition string was empty).
 */
export declare function t1Postconditions(predicates: ReadonlyArray<(outputs: ReadonlyArray<DataRef | Asset>) => boolean>, outputs: ReadonlyArray<DataRef | Asset>): boolean;
/**
 * T2 — forall o in outputs: validate(o, o.schema_ref) == ok.
 *
 * `validators[i]` is the compiled validator for `outputs[i]`. Length mismatch
 * is treated as failure (defensive — the Engine MUST provide one validator
 * per output).
 */
export declare function t2OutputSchemas(outputs: ReadonlyArray<DataRef | Asset>, validators: ReadonlyArray<SchemaValidator>): boolean;
/**
 * T3 — forall s in step_graph:
 *        s.traces_to ⊆ Charter.obligations ∪ Charter.invariants
 *        OR s.gap_status == 'accepted'
 *
 * Reuses L4 `tracesAllSteps`.
 */
export declare function t3StepTraces(workflow: Workflow, charter: Charter, coverage: CoverageMatrix): boolean;
/**
 * T4 — forall i in interfaces_with: contract_violations(i) == 0.
 *
 * Length must match `workflow.interfaces_with` (one violations view per
 * interface). Any non-zero count → fail.
 */
export declare function t4InterfaceContracts(workflow: Workflow, views: ReadonlyArray<InterfaceViolationsView>): boolean;
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
export declare function t5NoAbandonedChildren(selfExecutionId: string, children: ReadonlyArray<Execution>): boolean;
/**
 * T6 — if Workflow.modifies_sutra:
 *        founder_authorization == true OR meta_charter_approval == true
 *
 * No-op (always true) when modifies_sutra=false. When true, exactly one auth
 * token must be true.
 */
export declare function t6ReflexiveAuth(workflow: Workflow, auth: ReflexiveAuth): boolean;
export declare const l4TerminalCheck: {
    /**
     * Run T1-T6 in order; return the first failure or PASS.
     *
     * Workflow Engine maps the result to:
     *   - pass=true  → Execution.state = 'success'
     *   - pass=false → Execution.state = 'failed';
     *                  Execution.failure_reason = `terminal_check_failed:${failed_at}`
     */
    runAll(ctx: TerminalCheckContext): TerminalCheckResult;
    t1: typeof t1Postconditions;
    t2: typeof t2OutputSchemas;
    t3: typeof t3StepTraces;
    t4: typeof t4InterfaceContracts;
    t5: typeof t5NoAbandonedChildren;
    t6: typeof t6ReflexiveAuth;
};
export type { Constraint };
/**
 * Stable id for a schema-level forbidden coupling (D4 §3). F-9 omitted (M8).
 *
 * Full v1.0 set: F-1..F-8, F-10, F-11, F-12 (11 total). F-9 (D38 plugin shipment)
 * is hook-level — DEFERRED to M8 per codex P1.3 pre-dispatch.
 *
 * F-11 (Group G' fix-up 2026-04-29): Workflow.extension_ref MUST be null in
 * v1.0 per D4 §7.3. Codex master review caught the gap — schema accepts
 * non-null `ext-*` shape, but v1.0 enforcement was missing at terminal_check.
 *
 * F-12 (M5 Group I 2026-04-29): "Workflow code performs I/O" — replay
 * determinism rule. Per codex P2.4 narrowed scope, F-12 enforcement at M5 is
 * RUNTIME-ONLY (Activity wrapper detects Workflow execution context and
 * throws). The schema-level terminalCheck integration is DEFERRED to M9 once
 * the evidence-input shape is known. Enum value present here so downstream
 * tooling (M9 schema integration, error reporting) can name the coupling.
 */
export type ForbiddenCouplingId = 'F-1' | 'F-2' | 'F-3' | 'F-4' | 'F-5' | 'F-6' | 'F-7' | 'F-8' | 'F-10' | 'F-11' | 'F-12';
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
export declare function f1Predicate(input: {
    tenant: Pick<Tenant, 'id'>;
    workflow: Pick<Workflow, 'id'>;
    /**
     * Ordered ids from Tenant down to Workflow as observed in the graph.
     * Well-formed: [Tenant.id, 'D-...', 'C-...', Workflow.id]
     * Violation:    [Tenant.id, Workflow.id]   ← F-1
     */
    containment_chain: string[];
}): boolean;
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
export declare function f2Predicate(input: {
    workflow: Pick<Workflow, 'id'>;
    /** Charter ids this Workflow operationalizes (must be ≥1). */
    operationalizes_charters: string[];
}): boolean;
/**
 * F-3 — Execution spawned without TriggerEvent.
 *
 * D4 §3 + L3 ACTIVATION: Executions are NOT free-standing; every Execution
 * must reference the TriggerEvent that activated it. The Execution primitive
 * carries `trigger_event` (V2 §1 P4) which MUST be a non-empty string.
 *
 * @returns true iff F-3 VIOLATION (trigger_event missing or empty)
 */
export declare function f3Predicate(input: {
    execution: Pick<Execution, 'trigger_event'>;
}): boolean;
/**
 * F-4 — step_graph[i] with both skill_ref AND action set.
 *
 * V2.3 §A11: skill_ref XOR action — mutually exclusive. Both set ⇒ VIOLATION.
 *
 * @returns true iff F-4 VIOLATION (some step has both)
 */
export declare function f4Predicate(input: {
    workflow: Pick<Workflow, 'step_graph'>;
}): boolean;
/**
 * F-5 — step_graph[i] with neither skill_ref NOR action.
 *
 * L2 BOUNDARY: every step MUST specify what it does — either a skill_ref or
 * an action. Neither set ⇒ VIOLATION.
 *
 * @returns true iff F-5 VIOLATION (some step has neither)
 */
export declare function f5Predicate(input: {
    workflow: Pick<Workflow, 'step_graph'>;
}): boolean;
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
export declare function f6Predicate(input: {
    workflow: Pick<Workflow, 'custody_owner'>;
    operating_tenant_id: string;
    delegates_to_edges: ReadonlyArray<DelegatesToEdge>;
}): boolean;
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
export declare function f7Predicate(input: {
    workflow: Pick<Workflow, 'modifies_sutra'>;
    reflexive_auth: ReflexiveAuth;
}): boolean;
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
export declare function f8Predicate(input: {
    dp: Pick<DecisionProvenance, 'policy_id' | 'policy_version'>;
}): boolean;
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
export declare function f10Predicate(): boolean;
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
export declare function f11Predicate(input: {
    workflow: Pick<Workflow, 'extension_ref'>;
}): boolean;
export type { RoutingGatingPosition };
export { ROUTING_GATING_POSITIONS };
export interface TerminalCheckForbiddenCouplingsResult {
    pass: boolean;
    violations: ForbiddenCouplingId[];
}
export interface TerminalCheckForbiddenCouplingsInput {
    workflow: Workflow;
    execution: Execution;
    charter: Charter;
    tenant: Tenant;
    /** Optional DP record — F-8 skipped when not provided. */
    dp?: DecisionProvenance | null;
    /** Tenant-id of the operating context (for F-6). Defaults to `tenant.id`. */
    operating_tenant_id?: string;
    /** Registered delegates_to edges (for F-6). Defaults to []. */
    delegates_to_edges?: ReadonlyArray<DelegatesToEdge>;
    /**
     * Containment chain from Tenant down to Workflow (for F-1). When omitted,
     * F-1 is skipped (no chain to inspect at this terminal_check call site).
     */
    containment_chain?: string[];
    /** Charter ids the Workflow operationalizes (for F-2). Required. */
    operationalizes_charters: string[];
    /** Reflexive auth tokens (for F-7). */
    reflexive_auth: ReflexiveAuth;
}
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
export declare function terminalCheck(input: TerminalCheckForbiddenCouplingsInput): TerminalCheckForbiddenCouplingsResult;
//# sourceMappingURL=l4-terminal-check.d.ts.map