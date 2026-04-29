/**
 * EXECUTION — V2 §1 P4 + V2.4 §A12 (failure_reason)
 *
 * Runtime materialization of one Workflow activation.
 * Triggered by TriggerSpec via `activates` link (per L3 ACTIVATION).
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §1 P4 + §19 A12
 */

import type { Asset, DataRef, ExecutionState } from '../types/index.js'
import {
  isValidAgentIdentity,
  type AgentIdentity,
} from '../types/agent-identity.js'

const E_ID_PATTERN = /^E-.+$/
const W_ID_PATTERN = /^W-.+$/

const VALID_STATES: ReadonlySet<ExecutionState> = new Set([
  'pending',
  'running',
  'success',
  'failed',
  'declared_gap',
  'escalated',
])

/** Terminal states are immutable — once reached, no further transition allowed. */
const TERMINAL_STATES: ReadonlySet<ExecutionState> = new Set([
  'success',
  'failed',
  'declared_gap',
  'escalated',
])

/**
 * Allowed state-transition graph per V2 §1 P4 lifecycle:
 *   pending → running
 *   running → {success, failed, declared_gap, escalated}
 * All terminal states are sinks.
 */
const VALID_TRANSITIONS: Record<ExecutionState, ReadonlySet<ExecutionState>> = {
  pending: new Set<ExecutionState>(['running']),
  running: new Set<ExecutionState>(['success', 'failed', 'declared_gap', 'escalated']),
  success: new Set<ExecutionState>(),
  failed: new Set<ExecutionState>(),
  declared_gap: new Set<ExecutionState>(),
  escalated: new Set<ExecutionState>(),
}

/**
 * One log entry in the Execution event journal. Shape kept open (Record) on purpose:
 * the journal accepts arbitrary structured events; the Workflow Engine writes typed entries
 * downstream, but the primitive itself does not constrain the log schema beyond "object".
 */
export type ExecutionLogEntry = Record<string, unknown>

/**
 * Execution primitive shape — V2 §1 P4 + V2.4 §A12.
 */
export interface Execution {
  id: string
  workflow_id: string
  trigger_event: string
  state: ExecutionState
  logs: ExecutionLogEntry[]
  results: Array<DataRef | Asset>
  parent_exec_id: string | null
  sibling_group: string | null
  fingerprint: string
  /**
   * V2.4 §A12: must be non-null iff state='failed' (e.g., 'terminal_check_failed:T1').
   * For all other states this is null.
   */
  failure_reason: string | null
  /**
   * M4.2 — D1 P-A2 / V2.5 §A14: which LLM/agent made this Execution's decisions.
   * Optional in v1.0 (default null); F-7 (modifies_sutra=true ⇒ agent_identity
   * required) lands at M4.9 chunk 2.
   */
  agent_identity: AgentIdentity | null
}

/** Caller may omit failure_reason and agent_identity; createExecution fills defaults. */
export type ExecutionSpec = Omit<Execution, 'failure_reason' | 'agent_identity'> & {
  failure_reason?: string | null
  agent_identity?: AgentIdentity | null
}

/**
 * Construct an Execution after validating shape + V2.4 failure_reason invariants.
 * Returns a frozen object.
 */
export function createExecution(spec: ExecutionSpec): Execution {
  if (!E_ID_PATTERN.test(spec.id)) {
    throw new Error(`Execution.id must match pattern E-<hash>; got "${spec.id}"`)
  }
  if (!W_ID_PATTERN.test(spec.workflow_id)) {
    throw new Error(`Execution.workflow_id must match pattern W-<hash>; got "${spec.workflow_id}"`)
  }
  if (!VALID_STATES.has(spec.state)) {
    throw new Error(
      `Execution.state must be pending|running|success|failed|declared_gap|escalated; got "${String(spec.state)}"`,
    )
  }
  if (!Array.isArray(spec.logs) || !Array.isArray(spec.results)) {
    throw new Error('Execution.logs and Execution.results must be arrays')
  }
  if (spec.parent_exec_id !== null && !E_ID_PATTERN.test(spec.parent_exec_id)) {
    throw new Error(`Execution.parent_exec_id must be null or match E-<hash>; got "${String(spec.parent_exec_id)}"`)
  }
  if (typeof spec.fingerprint !== 'string' || spec.fingerprint.length === 0) {
    throw new Error('Execution.fingerprint must be a non-empty string')
  }

  // V2.4 §A12 invariant: failure_reason ⟺ state='failed'
  const reason = spec.failure_reason ?? null
  if (spec.state === 'failed' && (reason === null || reason.length === 0)) {
    throw new Error(
      "Execution.failure_reason must be a non-empty string when state='failed' (V2.4 §A12)",
    )
  }
  if (spec.state !== 'failed' && reason !== null) {
    throw new Error(
      `Execution.failure_reason must be null when state!='failed' (V2.4 §A12); got state='${spec.state}', reason='${reason}'`,
    )
  }

  // M4.2 — agent_identity is optional in v1.0; default null. When provided, it
  // MUST satisfy the AgentIdentity discriminated union (D-NS-10 namespace prefix
  // per kind). This raises lying-id rejections at the boundary.
  const agentIdentity = spec.agent_identity ?? null
  if (agentIdentity !== null && !isValidAgentIdentity(agentIdentity)) {
    throw new Error(
      'Execution.agent_identity must be a valid AgentIdentity (M4.2; D-NS-10 namespace prefix per kind)',
    )
  }

  const out: Execution = {
    ...spec,
    logs: [...spec.logs],
    results: [...spec.results],
    failure_reason: reason,
    agent_identity: agentIdentity,
  }
  return Object.freeze(out)
}

/**
 * Predicate: is this Execution shape valid against V2 §1 P4 + V2.4 §A12?
 */
export function isValidExecution(e: Execution): boolean {
  if (typeof e !== 'object' || e === null) return false
  if (typeof e.id !== 'string' || !E_ID_PATTERN.test(e.id)) return false
  if (typeof e.workflow_id !== 'string' || !W_ID_PATTERN.test(e.workflow_id)) return false
  if (!VALID_STATES.has(e.state)) return false
  if (!Array.isArray(e.logs) || !Array.isArray(e.results)) return false
  if (e.parent_exec_id !== null && !E_ID_PATTERN.test(e.parent_exec_id)) return false
  if (typeof e.fingerprint !== 'string' || e.fingerprint.length === 0) return false
  if (e.state === 'failed' && (e.failure_reason === null || e.failure_reason.length === 0)) return false
  if (e.state !== 'failed' && e.failure_reason !== null) return false
  // M4.2 — agent_identity must be null OR a valid AgentIdentity record.
  if (e.agent_identity !== null && !isValidAgentIdentity(e.agent_identity)) return false
  return true
}

/**
 * Predicate: is the proposed state transition allowed by the V2 §1 P4 lifecycle?
 *
 * Used by:
 * - Workflow Engine `dispatch` → `terminate` stage (V2 §16 Layer 2)
 * - audit replay against the JSONL event log
 */
export function isValidStateTransition(
  from: ExecutionState,
  to: ExecutionState,
): boolean {
  if (!VALID_STATES.has(from) || !VALID_STATES.has(to)) return false
  if (TERMINAL_STATES.has(from)) return false
  return VALID_TRANSITIONS[from].has(to)
}
