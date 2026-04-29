/**
 * Shared types — V2.3/V2.4 Sutra Engine spec §1 (Primitives) + §2 (Supporting concepts)
 *
 * Layer 1 (abstraction) — pure type definitions only. No runtime logic. No technology bindings.
 * These are imports for the 4 primitives: Domain, Charter, Workflow, Execution.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md
 */

// -----------------------------------------------------------------------------
// Constraint — V2 §2 supporting schema; sub-types extended in V2.1 §A5
// -----------------------------------------------------------------------------

export type ConstraintDurability = 'durable' | 'episodic'

export type ConstraintOwnerScope = 'domain' | 'charter' | 'workflow' | 'execution'

/**
 * Constraint sub-type per V2.1 §A5.
 * - predicate:        standard "must hold" check
 * - obligation:       must be delivered (Charter-level commitment)
 * - invariant:        must always hold across executions
 * - reflexive_check:  fires when Workflow modifies Sutra primitives (V2.1 §A5 + L6)
 */
export type ConstraintType =
  | 'predicate'
  | 'obligation'
  | 'invariant'
  | 'reflexive_check'

export interface Constraint {
  name: string
  predicate: string
  durability: ConstraintDurability
  owner_scope: ConstraintOwnerScope
  /** Optional sub-type per V2.1 §A5; defaults to 'predicate' semantics when omitted. */
  type?: ConstraintType
}

// -----------------------------------------------------------------------------
// DataRef / Asset — V2 §2 (referenced by Workflow inputs/outputs/state, Execution.results)
// -----------------------------------------------------------------------------

export type DataMutability = 'mutable' | 'immutable'

export interface DataRef {
  kind: string
  schema_ref: string
  locator: string
  version: string
  mutability: DataMutability
  retention: string
}

// M4.3: DataRef zod schema for use by DecisionProvenance.evidence (and other
// new M4 schemas). The TS interface remains the source-of-truth for primitives;
// this schema mirrors it for runtime parsing. Imported here so the dependency
// graph stays acyclic (schemas may import types/, never the reverse).
import { z } from 'zod'

export const DataRefSchema = z.object({
  kind: z.string().min(1),
  schema_ref: z.string().min(1),
  locator: z.string().min(1),
  version: z.string(),
  mutability: z.enum(['mutable', 'immutable']),
  retention: z.string(),
})

export interface Asset extends DataRef {
  /** L1 DATA promotion: stable_identity AND len(lifecycle_states) > 1 */
  stable_identity: string
  lifecycle_states: string[]
}

// -----------------------------------------------------------------------------
// BoundaryEndpoint — V2 §2 (referenced by Workflow.expects_response_from per V2.1 §A4)
// -----------------------------------------------------------------------------

export type BoundaryEndpointClass =
  | 'human'
  | 'model'
  | 'service'
  | 'sensor'
  | 'actuator'
  | 'physical_process'

export interface BoundaryEndpoint {
  class: BoundaryEndpointClass
  address: string
  protocol: string
  trust: string
  capabilities: string[]
}

/** Reference to a registered BoundaryEndpoint by its address. */
export type BoundaryEndpointRef = string

// -----------------------------------------------------------------------------
// Interface — V2 §2 (referenced by Workflow.interfaces_with)
// -----------------------------------------------------------------------------

export type InterfaceDirection = 'inbound' | 'outbound' | 'bidirectional'

export interface Interface {
  endpoint_ref: BoundaryEndpointRef
  workflow_ref: string
  direction: InterfaceDirection
  contract_schema: string
  qos: string
  failure_modes: string[]
}

// -----------------------------------------------------------------------------
// ACL entry — V2.2 §A8 (Charter.acl[])
// -----------------------------------------------------------------------------

export type AclAccess = 'read' | 'write' | 'append' | 'none'

export interface AclEntry {
  domain_or_charter_id: string
  access: AclAccess
  reason: string
}

// -----------------------------------------------------------------------------
// Schema reference — used by Workflow.return_contract per V2.3 §A11
// -----------------------------------------------------------------------------

/** A reference to a JSON-schema document; machine-checkable per V2 §3 HARD. */
export type SchemaRef = string

// -----------------------------------------------------------------------------
// Step graph — V2.3 §A11 (Workflow.step_graph[i])
// -----------------------------------------------------------------------------

export type StepAction = 'spawn_sub_unit' | 'wait' | 'terminate'

export type StepFailureAction =
  | 'rollback'
  | 'escalate'
  | 'pause'
  | 'abort'
  | 'continue'

/**
 * V2.3 §A11: step has either skill_ref OR action (mutually exclusive).
 * Validation per L2 BOUNDARY: a step with neither is invalid.
 */
export interface WorkflowStep {
  step_id: number
  skill_ref?: string
  action?: StepAction
  inputs: DataRef[]
  outputs: DataRef[]
  on_failure: StepFailureAction
}

// -----------------------------------------------------------------------------
// Workflow stringency — V2 §6 codification ladder
// -----------------------------------------------------------------------------

export type WorkflowStringency = 'task' | 'process' | 'protocol'

// -----------------------------------------------------------------------------
// Workflow override action — V2.2 §A10
// -----------------------------------------------------------------------------

export type OverrideAction = 'pause' | 'splice' | 'restart' | 'escalate'

// -----------------------------------------------------------------------------
// Execution state — V2 §1 Primitive 4
// -----------------------------------------------------------------------------

/**
 * V2.4 §A12 failure semantics extends the original §1 set with declared_gap +
 * escalated; both surface from terminal_check predicates and L4/L6 mechanics.
 */
export type ExecutionState =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'declared_gap'
  | 'escalated'
