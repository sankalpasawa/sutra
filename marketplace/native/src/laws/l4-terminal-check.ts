/**
 * L4 TERMINAL-CHECK predicates (T1-T6) — V2.4 §A12
 * AND schema-level forbidden couplings (F-1..F-8) — D4 §3 (M4.9 Groups D + E)
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
 * subsequent commits. F-9 (D38 plugin shipment) is hook-level and DEFERRED to
 * M8 per codex P1.3 pre-dispatch.
 *
 * Source-of-truth:
 *  - holding/research/2026-04-28-v2-architecture-spec.md §19 §A12
 *  - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §3
 *  - holding/plans/native-v1.0/M4-schemas-edges.md M4.9
 */

import type { Asset, Constraint, DataRef, Interface } from '../types/index.js'
import type { Charter } from '../primitives/charter.js'
import type { Execution } from '../primitives/execution.js'
import type { Workflow } from '../primitives/workflow.js'
import { l4Commitment, type CoverageMatrix } from './l4-commitment.js'
import type { Tenant } from '../schemas/tenant.js'
import type { DelegatesToEdge } from '../types/edges.js'
import type { DecisionProvenance } from '../schemas/decision-provenance.js'

// -----------------------------------------------------------------------------
// Auxiliary types — terminal-check inputs that aren't on V2 base shapes
// -----------------------------------------------------------------------------

/**
 * Per-output schema validator. Workflow Engine (M5) wires Ajv here; M3 accepts
 * any pre-compiled validator function. Returns true on schema match, false
 * (or throws) on mismatch.
 */
export type SchemaValidator = (output: DataRef | Asset) => boolean

/**
 * Interface contract violations counter (V2.4 §A12 T4 source).
 * Workflow Engine maintains this at the dispatch stage; M3 reads only.
 */
export interface InterfaceViolationsView {
  contract_violations: number
}

/**
 * Reflexive auth tokens (V2.4 §A12 T6 + V2.1 §A6 L6).
 * Either flag set to true clears the L6 gate.
 */
export interface ReflexiveAuth {
  founder_authorization: boolean
  meta_charter_approval: boolean
}

/**
 * Inputs to `runAll` — bundles the per-T inputs the Workflow Engine
 * collects at the terminate stage.
 */
export interface TerminalCheckContext {
  workflow: Workflow
  charter: Charter
  /** Per-postcondition predicate functions (T1). */
  postcondition_predicates: Array<(outputs: ReadonlyArray<DataRef | Asset>) => boolean>
  /** Per-output validators keyed by output index (T2). */
  output_validators: SchemaValidator[]
  /** Step + obligation coverage matrix (T3) per L4. */
  coverage: CoverageMatrix
  /** Per-Interface contract-violations view (T4). */
  interface_violations: InterfaceViolationsView[]
  /** Children of this Execution (T5). */
  children: Execution[]
  /** Reflexive auth tokens (T6). */
  reflexive_auth: ReflexiveAuth
  /** This execution's id (used to filter children by parent_exec_id for T5). */
  self_execution_id: string
}

export type TerminalCheckId = 'T1' | 'T2' | 'T3' | 'T4' | 'T5' | 'T6'

export interface TerminalCheckResult {
  pass: boolean
  /** First failing T_i (e.g. 'T2') if pass=false; null if pass=true. */
  failed_at: TerminalCheckId | null
  /** Concise reason string suitable for Execution.failure_reason. */
  failure_reason: string | null
}

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
export function t1Postconditions(
  predicates: ReadonlyArray<(outputs: ReadonlyArray<DataRef | Asset>) => boolean>,
  outputs: ReadonlyArray<DataRef | Asset>,
): boolean {
  if (!Array.isArray(predicates)) return false
  if (!Array.isArray(outputs)) return false
  for (const p of predicates) {
    if (typeof p !== 'function') return false
    let ok: boolean
    try {
      ok = p(outputs) === true
    } catch {
      return false
    }
    if (!ok) return false
  }
  return true
}

/**
 * T2 — forall o in outputs: validate(o, o.schema_ref) == ok.
 *
 * `validators[i]` is the compiled validator for `outputs[i]`. Length mismatch
 * is treated as failure (defensive — the Engine MUST provide one validator
 * per output).
 */
export function t2OutputSchemas(
  outputs: ReadonlyArray<DataRef | Asset>,
  validators: ReadonlyArray<SchemaValidator>,
): boolean {
  if (!Array.isArray(outputs)) return false
  if (!Array.isArray(validators)) return false
  if (outputs.length !== validators.length) return false
  for (let i = 0; i < outputs.length; i++) {
    const v = validators[i]
    if (typeof v !== 'function') return false
    try {
      if (v(outputs[i] as DataRef | Asset) !== true) return false
    } catch {
      return false
    }
  }
  return true
}

/**
 * T3 — forall s in step_graph:
 *        s.traces_to ⊆ Charter.obligations ∪ Charter.invariants
 *        OR s.gap_status == 'accepted'
 *
 * Reuses L4 `tracesAllSteps`.
 */
export function t3StepTraces(
  workflow: Workflow,
  charter: Charter,
  coverage: CoverageMatrix,
): boolean {
  return l4Commitment.tracesAllSteps(workflow, charter, coverage)
}

/**
 * T4 — forall i in interfaces_with: contract_violations(i) == 0.
 *
 * Length must match `workflow.interfaces_with` (one violations view per
 * interface). Any non-zero count → fail.
 */
export function t4InterfaceContracts(
  workflow: Workflow,
  views: ReadonlyArray<InterfaceViolationsView>,
): boolean {
  if (typeof workflow !== 'object' || workflow === null) return false
  const interfaces = workflow.interfaces_with as Interface[]
  if (!Array.isArray(interfaces)) return false
  if (!Array.isArray(views)) return false
  if (interfaces.length !== views.length) return false
  for (const v of views) {
    if (typeof v !== 'object' || v === null) return false
    if (typeof v.contract_violations !== 'number') return false
    if (v.contract_violations !== 0) return false
  }
  return true
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
export function t5NoAbandonedChildren(
  selfExecutionId: string,
  children: ReadonlyArray<Execution>,
): boolean {
  if (typeof selfExecutionId !== 'string' || selfExecutionId.length === 0) return false
  if (!Array.isArray(children)) return false
  const allowed: ReadonlySet<Execution['state']> = new Set(['success', 'declared_gap', 'escalated'])
  for (const child of children) {
    if (typeof child !== 'object' || child === null) return false
    if (child.parent_exec_id !== selfExecutionId) continue
    if (!allowed.has(child.state)) return false
  }
  return true
}

/**
 * T6 — if Workflow.modifies_sutra:
 *        founder_authorization == true OR meta_charter_approval == true
 *
 * No-op (always true) when modifies_sutra=false. When true, exactly one auth
 * token must be true.
 */
export function t6ReflexiveAuth(workflow: Workflow, auth: ReflexiveAuth): boolean {
  if (typeof workflow !== 'object' || workflow === null) return false
  if (typeof workflow.modifies_sutra !== 'boolean') return false
  if (!workflow.modifies_sutra) return true
  if (typeof auth !== 'object' || auth === null) return false
  if (typeof auth.founder_authorization !== 'boolean') return false
  if (typeof auth.meta_charter_approval !== 'boolean') return false
  return auth.founder_authorization === true || auth.meta_charter_approval === true
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
  runAll(ctx: TerminalCheckContext): TerminalCheckResult {
    if (typeof ctx !== 'object' || ctx === null) {
      return {
        pass: false,
        failed_at: 'T1',
        failure_reason: 'terminal_check_failed:T1 (invalid context)',
      }
    }

    const outputs = ctx.workflow.outputs as ReadonlyArray<DataRef | Asset>

    if (!t1Postconditions(ctx.postcondition_predicates, outputs)) {
      return { pass: false, failed_at: 'T1', failure_reason: 'terminal_check_failed:T1' }
    }
    if (!t2OutputSchemas(outputs, ctx.output_validators)) {
      return { pass: false, failed_at: 'T2', failure_reason: 'terminal_check_failed:T2' }
    }
    if (!t3StepTraces(ctx.workflow, ctx.charter, ctx.coverage)) {
      return { pass: false, failed_at: 'T3', failure_reason: 'terminal_check_failed:T3' }
    }
    if (!t4InterfaceContracts(ctx.workflow, ctx.interface_violations)) {
      return { pass: false, failed_at: 'T4', failure_reason: 'terminal_check_failed:T4' }
    }
    if (!t5NoAbandonedChildren(ctx.self_execution_id, ctx.children)) {
      return { pass: false, failed_at: 'T5', failure_reason: 'terminal_check_failed:T5' }
    }
    if (!t6ReflexiveAuth(ctx.workflow, ctx.reflexive_auth)) {
      return { pass: false, failed_at: 'T6', failure_reason: 'terminal_check_failed:T6' }
    }
    return { pass: true, failed_at: null, failure_reason: null }
  },

  // Direct exports for granular callers (e.g. telemetry per-T).
  t1: t1Postconditions,
  t2: t2OutputSchemas,
  t3: t3StepTraces,
  t4: t4InterfaceContracts,
  t5: t5NoAbandonedChildren,
  t6: t6ReflexiveAuth,
}

// Re-export Constraint to keep downstream barrel imports tidy.
export type { Constraint }

// =============================================================================
// M4.9 — 9 schema-level forbidden couplings (F-1..F-8, F-10) per D4 §3
//
// F-9 (D38 plugin shipment) is hook-level — DEFERRED to M8 per codex P1.3
// pre-dispatch. F-1..F-8 + F-10 are pure-predicate, schema-level checks.
//
// Each predicate returns `true` iff the input SATISFIES the forbidden coupling
// (i.e., violates the rule). The aggregator inverts to {pass, violations[]}.
// =============================================================================

/**
 * Stable id for a schema-level forbidden coupling (D4 §3). F-9 omitted (M8).
 *
 * M4.9 Group D shipped F-1..F-4; Group E (this commit) extends with F-5..F-8;
 * Group F adds F-10 + the terminalCheck aggregator.
 */
export type ForbiddenCouplingId =
  | 'F-1'
  | 'F-2'
  | 'F-3'
  | 'F-4'
  | 'F-5'
  | 'F-6'
  | 'F-7'
  | 'F-8'

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
export function f1Predicate(input: {
  tenant: Pick<Tenant, 'id'>
  workflow: Pick<Workflow, 'id'>
  /**
   * Ordered ids from Tenant down to Workflow as observed in the graph.
   * Well-formed: [Tenant.id, 'D-...', 'C-...', Workflow.id]
   * Violation:    [Tenant.id, Workflow.id]   ← F-1
   */
  containment_chain: string[]
}): boolean {
  const { tenant, workflow, containment_chain } = input
  if (!Array.isArray(containment_chain)) return false
  if (containment_chain.length < 2) return false
  const head = containment_chain[0]
  const tail = containment_chain[containment_chain.length - 1]
  if (head !== tenant.id) return false
  if (tail !== workflow.id) return false
  // VIOLATION iff chain has length 2 (no Domain + Charter in between)
  if (containment_chain.length === 2) return true
  // Or if chain has any length but no D-* or no C-* between head and tail.
  const middle = containment_chain.slice(1, -1)
  const hasDomain = middle.some((s) => typeof s === 'string' && /^D\d+(\.D\d+)*$/.test(s))
  const hasCharter = middle.some((s) => typeof s === 'string' && /^C-.+$/.test(s))
  return !(hasDomain && hasCharter)
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
export function f2Predicate(input: {
  workflow: Pick<Workflow, 'id'>
  /** Charter ids this Workflow operationalizes (must be ≥1). */
  operationalizes_charters: string[]
}): boolean {
  const { operationalizes_charters } = input
  if (!Array.isArray(operationalizes_charters)) return true
  return operationalizes_charters.length === 0
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
export function f3Predicate(input: { execution: Pick<Execution, 'trigger_event'> }): boolean {
  const { execution } = input
  if (typeof execution !== 'object' || execution === null) return true
  if (typeof execution.trigger_event !== 'string') return true
  return execution.trigger_event.length === 0
}

/**
 * F-4 — step_graph[i] with both skill_ref AND action set.
 *
 * V2.3 §A11: skill_ref XOR action — mutually exclusive. Both set ⇒ VIOLATION.
 *
 * @returns true iff F-4 VIOLATION (some step has both)
 */
export function f4Predicate(input: { workflow: Pick<Workflow, 'step_graph'> }): boolean {
  const { workflow } = input
  if (typeof workflow !== 'object' || workflow === null) return false
  if (!Array.isArray(workflow.step_graph)) return false
  for (const step of workflow.step_graph) {
    const hasSkill = typeof step.skill_ref === 'string' && step.skill_ref.length > 0
    const hasAction = typeof step.action === 'string' && step.action.length > 0
    if (hasSkill && hasAction) return true
  }
  return false
}

/**
 * F-5 — step_graph[i] with neither skill_ref NOR action.
 *
 * L2 BOUNDARY: every step MUST specify what it does — either a skill_ref or
 * an action. Neither set ⇒ VIOLATION.
 *
 * @returns true iff F-5 VIOLATION (some step has neither)
 */
export function f5Predicate(input: { workflow: Pick<Workflow, 'step_graph'> }): boolean {
  const { workflow } = input
  if (typeof workflow !== 'object' || workflow === null) return false
  if (!Array.isArray(workflow.step_graph)) return false
  for (const step of workflow.step_graph) {
    const hasSkill = typeof step.skill_ref === 'string' && step.skill_ref.length > 0
    const hasAction = typeof step.action === 'string' && step.action.length > 0
    if (!hasSkill && !hasAction) return true
  }
  return false
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
export function f6Predicate(input: {
  workflow: Pick<Workflow, 'custody_owner'>
  operating_tenant_id: string
  delegates_to_edges: ReadonlyArray<DelegatesToEdge>
}): boolean {
  const { workflow, operating_tenant_id, delegates_to_edges } = input
  if (typeof workflow !== 'object' || workflow === null) return false
  // Single-tenant or matching custody — no cross-tenant op.
  if (workflow.custody_owner === null || workflow.custody_owner === undefined) return false
  if (workflow.custody_owner === operating_tenant_id) return false
  // Cross-tenant op detected; require delegates_to edge.
  if (!Array.isArray(delegates_to_edges)) return true
  for (const e of delegates_to_edges) {
    if (
      typeof e === 'object' &&
      e !== null &&
      e.kind === 'delegates_to' &&
      e.source === operating_tenant_id &&
      e.target === workflow.custody_owner
    ) {
      return false
    }
  }
  return true
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
export function f7Predicate(input: {
  workflow: Pick<Workflow, 'modifies_sutra'>
  reflexive_auth: ReflexiveAuth
}): boolean {
  const { workflow, reflexive_auth } = input
  if (typeof workflow !== 'object' || workflow === null) return false
  if (workflow.modifies_sutra !== true) return false
  if (typeof reflexive_auth !== 'object' || reflexive_auth === null) return true
  const cleared =
    reflexive_auth.founder_authorization === true ||
    reflexive_auth.meta_charter_approval === true
  return !cleared
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
export function f8Predicate(input: {
  dp: Pick<DecisionProvenance, 'policy_id' | 'policy_version'>
}): boolean {
  const { dp } = input
  if (typeof dp !== 'object' || dp === null) return true
  const hasId = typeof dp.policy_id === 'string' && dp.policy_id.length > 0
  const hasVer = typeof dp.policy_version === 'string' && dp.policy_version.length > 0
  return !(hasId && hasVer)
}

// F-10 + routing/gating-positions inventory + terminalCheck aggregator land in
// M4.9 Group F (T-029..T-031).
