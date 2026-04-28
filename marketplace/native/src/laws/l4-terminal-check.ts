/**
 * L4 TERMINAL-CHECK predicates (T1-T6) — V2.4 §A12
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
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §19 §A12
 */

import type { Asset, Constraint, DataRef, Interface } from '../types/index.js'
import type { Charter } from '../primitives/charter.js'
import type { Execution } from '../primitives/execution.js'
import type { Workflow } from '../primitives/workflow.js'
import { l4Commitment, type CoverageMatrix } from './l4-commitment.js'

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
