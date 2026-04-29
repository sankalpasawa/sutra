/**
 * Shared fast-check arbitraries — V2 §1 + §2 schemas.
 *
 * Single source-of-truth for property-test generators across L1-L6 law tests.
 *
 * Notes:
 * - These generate STRUCTURALLY-VALID shapes (TS types satisfied) that may or
 *   may not satisfy higher-level invariants (e.g., a domain id might fail the
 *   D-pattern). Each test composes with positive/negative filters as needed.
 * - Per M3 plan: 1000+ runs per property. Seed locks deferred to M5+.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md
 */

import * as fc from 'fast-check'
import type {
  AclEntry,
  Asset,
  BoundaryEndpoint,
  BoundaryEndpointClass,
  Constraint,
  ConstraintDurability,
  ConstraintOwnerScope,
  ConstraintType,
  DataMutability,
  DataRef,
  Interface,
  InterfaceDirection,
  OverrideAction,
  StepAction,
  StepFailureAction,
  WorkflowStep,
  WorkflowStringency,
} from '../../src/types/index.js'
import type { Charter } from '../../src/primitives/charter.js'
import type { Domain } from '../../src/primitives/domain.js'
import type { Execution } from '../../src/primitives/execution.js'
import type { Workflow } from '../../src/primitives/workflow.js'

// -----------------------------------------------------------------------------
// Primitive enums
// -----------------------------------------------------------------------------

export const constraintDurabilityArb: fc.Arbitrary<ConstraintDurability> =
  fc.constantFrom<ConstraintDurability>('durable', 'episodic')

export const constraintOwnerScopeArb: fc.Arbitrary<ConstraintOwnerScope> =
  fc.constantFrom<ConstraintOwnerScope>('domain', 'charter', 'workflow', 'execution')

export const constraintTypeArb: fc.Arbitrary<ConstraintType> =
  fc.constantFrom<ConstraintType>('predicate', 'obligation', 'invariant', 'reflexive_check')

export const dataMutabilityArb: fc.Arbitrary<DataMutability> =
  fc.constantFrom<DataMutability>('mutable', 'immutable')

export const stringencyArb: fc.Arbitrary<WorkflowStringency> =
  fc.constantFrom<WorkflowStringency>('task', 'process', 'protocol')

export const overrideActionArb: fc.Arbitrary<OverrideAction> =
  fc.constantFrom<OverrideAction>('pause', 'splice', 'restart', 'escalate')

export const stepActionArb: fc.Arbitrary<StepAction> =
  fc.constantFrom<StepAction>('spawn_sub_unit', 'wait', 'terminate')

export const stepFailureActionArb: fc.Arbitrary<StepFailureAction> =
  fc.constantFrom<StepFailureAction>('rollback', 'escalate', 'pause', 'abort', 'continue')

export const interfaceDirectionArb: fc.Arbitrary<InterfaceDirection> =
  fc.constantFrom<InterfaceDirection>('inbound', 'outbound', 'bidirectional')

export const boundaryEndpointClassArb: fc.Arbitrary<BoundaryEndpointClass> =
  fc.constantFrom<BoundaryEndpointClass>(
    'human',
    'model',
    'service',
    'sensor',
    'actuator',
    'physical_process',
  )

// -----------------------------------------------------------------------------
// Constraint
// -----------------------------------------------------------------------------

export interface ConstraintArbOpts {
  forceType?: ConstraintType
  forceDurability?: ConstraintDurability
  forceOwnerScope?: ConstraintOwnerScope
}

export function constraintArb(opts: ConstraintArbOpts = {}): fc.Arbitrary<Constraint> {
  return fc.record({
    name: fc.string({ minLength: 1, maxLength: 30 }),
    predicate: fc.string({ minLength: 1, maxLength: 60 }),
    durability: opts.forceDurability ? fc.constant(opts.forceDurability) : constraintDurabilityArb,
    owner_scope: opts.forceOwnerScope ? fc.constant(opts.forceOwnerScope) : constraintOwnerScopeArb,
    type: opts.forceType ? fc.constant(opts.forceType) : fc.option(constraintTypeArb, { nil: undefined }),
  }) as fc.Arbitrary<Constraint>
}

// -----------------------------------------------------------------------------
// DataRef / Asset
// -----------------------------------------------------------------------------

export const dataRefArb: fc.Arbitrary<DataRef> = fc.record({
  kind: fc.string({ minLength: 1, maxLength: 20 }),
  schema_ref: fc.string({ minLength: 1, maxLength: 40 }),
  locator: fc.string({ minLength: 1, maxLength: 40 }),
  version: fc.string({ maxLength: 10 }),
  mutability: dataMutabilityArb,
  retention: fc.string({ maxLength: 20 }),
})

/** A DataRef-shaped record WITHOUT stable_identity / lifecycle_states (negative for L1). */
export const dataRefNoAssetFieldsArb: fc.Arbitrary<DataRef> = dataRefArb

/** A full Asset (extends DataRef + stable_identity + lifecycle_states). */
export const assetArb: fc.Arbitrary<Asset> = fc.record({
  kind: fc.string({ minLength: 1, maxLength: 20 }),
  schema_ref: fc.string({ minLength: 1, maxLength: 40 }),
  locator: fc.string({ minLength: 1, maxLength: 40 }),
  version: fc.string({ maxLength: 10 }),
  mutability: dataMutabilityArb,
  retention: fc.string({ maxLength: 20 }),
  stable_identity: fc.string({ minLength: 1, maxLength: 40 }),
  lifecycle_states: fc.array(fc.string({ minLength: 1, maxLength: 12 }), { minLength: 2, maxLength: 6 }),
})

// -----------------------------------------------------------------------------
// BoundaryEndpoint + Interface
// -----------------------------------------------------------------------------

export const boundaryEndpointArb: fc.Arbitrary<BoundaryEndpoint> = fc.record({
  class: boundaryEndpointClassArb,
  address: fc.string({ minLength: 1, maxLength: 40 }),
  protocol: fc.string({ minLength: 1, maxLength: 20 }),
  trust: fc.string({ minLength: 1, maxLength: 12 }),
  capabilities: fc.array(fc.string({ minLength: 1, maxLength: 12 }), { maxLength: 4 }),
})

/** Interface arbitrary; pass `{ contract_schema: '' }` to force invalid. */
export interface InterfaceArbOpts {
  contract_schema?: fc.Arbitrary<string>
}

export function interfaceArb(opts: InterfaceArbOpts = {}): fc.Arbitrary<Interface> {
  return fc.record({
    endpoint_ref: fc.string({ minLength: 1, maxLength: 30 }),
    workflow_ref: fc.string({ minLength: 1, maxLength: 30 }),
    direction: interfaceDirectionArb,
    contract_schema: opts.contract_schema ?? fc.string({ minLength: 1, maxLength: 60 }),
    qos: fc.string({ maxLength: 16 }),
    failure_modes: fc.array(fc.string({ minLength: 1, maxLength: 16 }), { maxLength: 4 }),
  })
}

// -----------------------------------------------------------------------------
// ACL
// -----------------------------------------------------------------------------

export const aclEntryArb: fc.Arbitrary<AclEntry> = fc.record({
  domain_or_charter_id: fc.string({ minLength: 1, maxLength: 12 }),
  access: fc.constantFrom('read', 'write', 'append', 'none'),
  reason: fc.string({ minLength: 1, maxLength: 30 }),
})

// -----------------------------------------------------------------------------
// WorkflowStep
// -----------------------------------------------------------------------------

/**
 * A workflow step with skill_ref OR action (XOR per V2.3 §A11).
 * Always valid-shape; chooses one branch randomly.
 */
export const workflowStepArb: fc.Arbitrary<WorkflowStep> = fc.oneof(
  // skill_ref branch
  fc.record({
    step_id: fc.integer({ min: 0, max: 50 }),
    skill_ref: fc.string({ minLength: 1, maxLength: 24 }),
    inputs: fc.array(dataRefArb, { maxLength: 3 }),
    outputs: fc.array(dataRefArb, { maxLength: 3 }),
    on_failure: stepFailureActionArb,
  }),
  // action branch
  fc.record({
    step_id: fc.integer({ min: 0, max: 50 }),
    action: stepActionArb,
    inputs: fc.array(dataRefArb, { maxLength: 3 }),
    outputs: fc.array(dataRefArb, { maxLength: 3 }),
    on_failure: stepFailureActionArb,
  }),
)

// -----------------------------------------------------------------------------
// Workflow (validates createWorkflow defaults)
// -----------------------------------------------------------------------------

export interface WorkflowArbOpts {
  modifies_sutra?: boolean
  reuse_tag?: boolean
  return_contract?: string | null
}

/**
 * Generates a Workflow record with all V2.4 fields. step_graph guaranteed
 * non-empty AND with unique step_ids (codex M3 P1 fix 2026-04-28 — workflow
 * primitive now enforces step_id uniqueness, so the arbitrary must agree to
 * keep property tests realistic instead of relying on test-side renumbering).
 */
export function workflowArb(opts: WorkflowArbOpts = {}): fc.Arbitrary<Workflow> {
  return fc.record({
    id: fc.string({ minLength: 1, maxLength: 16 }).map((s) => `W-${s}`),
    preconditions: fc.string({ maxLength: 30 }),
    step_graph: fc
      .array(workflowStepArb, { minLength: 1, maxLength: 5 })
      .map((steps) => steps.map((s, i) => ({ ...s, step_id: i }))),
    inputs: fc.array(dataRefArb, { maxLength: 3 }),
    outputs: fc.array(dataRefArb, { maxLength: 3 }),
    state: fc.array(dataRefArb, { maxLength: 3 }),
    postconditions: fc.string({ maxLength: 30 }),
    failure_policy: fc.string({ maxLength: 20 }),
    stringency: stringencyArb,
    interfaces_with: fc.array(interfaceArb(), { maxLength: 3 }),
    expects_response_from: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    on_override_action: overrideActionArb,
    reuse_tag: opts.reuse_tag !== undefined ? fc.constant(opts.reuse_tag) : fc.constant(false),
    return_contract:
      opts.return_contract !== undefined
        ? fc.constant(opts.return_contract)
        : fc.constant<string | null>(null),
    modifies_sutra:
      opts.modifies_sutra !== undefined ? fc.constant(opts.modifies_sutra) : fc.boolean(),
  })
}

// -----------------------------------------------------------------------------
// Charter
// -----------------------------------------------------------------------------

export interface CharterArbOpts {
  obligations?: fc.Arbitrary<Constraint[]>
  invariants?: fc.Arbitrary<Constraint[]>
}

export function charterArb(opts: CharterArbOpts = {}): fc.Arbitrary<Charter> {
  return fc.record({
    id: fc.string({ minLength: 1, maxLength: 16 }).map((s) => `C-${s}`),
    purpose: fc.string({ minLength: 1, maxLength: 30 }),
    scope_in: fc.string({ maxLength: 20 }),
    scope_out: fc.string({ maxLength: 20 }),
    obligations:
      opts.obligations ??
      fc.array(constraintArb({ forceType: 'obligation' }), { maxLength: 3 }),
    invariants:
      opts.invariants ??
      fc.array(constraintArb({ forceType: 'invariant' }), { maxLength: 3 }),
    success_metrics: fc.array(fc.string({ minLength: 1, maxLength: 16 }), { maxLength: 3 }),
    authority: fc.string({ maxLength: 16 }),
    termination: fc.string({ maxLength: 16 }),
    constraints: fc.array(constraintArb({ forceDurability: 'episodic' }), { maxLength: 3 }),
    acl: fc.array(aclEntryArb, { maxLength: 3 }),
  })
}

// -----------------------------------------------------------------------------
// Domain
// -----------------------------------------------------------------------------

/** Domain arbitrary; produces a valid D0 root by default. */
export const domainArb: fc.Arbitrary<Domain> = fc.record({
  id: fc.constant('D0'),
  name: fc.string({ maxLength: 16 }),
  parent_id: fc.constant<string | null>(null),
  principles: fc.array(constraintArb({ forceDurability: 'durable', forceOwnerScope: 'domain' }), {
    maxLength: 3,
  }),
  intelligence: fc.string({ maxLength: 20 }),
  accountable: fc.array(fc.string({ minLength: 1, maxLength: 12 }), { maxLength: 3 }),
  authority: fc.string({ maxLength: 16 }),
  // M4.1 — tenant_id required; default to 'T-default' for property tests so
  // isValidDomain passes the new D4 §1.1 owner check.
  tenant_id: fc.constant('T-default'),
})

// -----------------------------------------------------------------------------
// Execution
// -----------------------------------------------------------------------------

export const executionArb: fc.Arbitrary<Execution> = fc
  .record({
    id: fc.string({ minLength: 1, maxLength: 16 }).map((s) => `E-${s}`),
    workflow_id: fc.string({ minLength: 1, maxLength: 16 }).map((s) => `W-${s}`),
    trigger_event: fc.string({ minLength: 1, maxLength: 20 }),
    state: fc.constantFrom('success', 'declared_gap', 'escalated') as fc.Arbitrary<
      'success' | 'declared_gap' | 'escalated'
    >,
    logs: fc.array(fc.dictionary(fc.string({ minLength: 1, maxLength: 8 }), fc.anything()), {
      maxLength: 3,
    }),
    results: fc.array(dataRefArb, { maxLength: 3 }),
    parent_exec_id: fc.option(fc.string({ minLength: 1, maxLength: 12 }).map((s) => `E-${s}`), {
      nil: null,
    }),
    sibling_group: fc.option(fc.string({ minLength: 1, maxLength: 12 }), { nil: null }),
    fingerprint: fc.string({ minLength: 1, maxLength: 24 }),
  })
  .map(
    (r) =>
      ({
        ...r,
        failure_reason: null,
      }) as Execution,
  )

// -----------------------------------------------------------------------------
// TriggerSpec / TriggerEvent (M3.3 L3 ACTIVATION inputs)
// -----------------------------------------------------------------------------

/**
 * TriggerSpec shape used by L3 ACTIVATION law.
 * payload_validator: pure predicate against a payload (replaces JSON Schema parse for M3 — full Ajv defer to M5).
 * route_predicate:   pure predicate against the same payload.
 */
export interface L3TriggerSpec {
  id: string
  payload_validator: (payload: unknown) => boolean
  route_predicate: (payload: unknown) => boolean
}

export interface L3TriggerEvent {
  spec_id: string
  payload: unknown
}

/**
 * Generates a (spec, event) pair where (a) the schema match outcome and
 * (b) the route outcome are independently controlled, so property tests can
 * cover the truth-table for L3.
 */
export const triggerPairArb: fc.Arbitrary<{
  spec: L3TriggerSpec
  event: L3TriggerEvent
  schemaMatch: boolean
  routeMatch: boolean
}> = fc
  .record({
    schemaMatch: fc.boolean(),
    routeMatch: fc.boolean(),
    payload: fc.anything(),
    specId: fc.string({ minLength: 1, maxLength: 12 }),
  })
  .map(({ schemaMatch, routeMatch, payload, specId }) => ({
    spec: {
      id: specId,
      payload_validator: () => schemaMatch,
      route_predicate: () => routeMatch,
    },
    event: { spec_id: specId, payload },
    schemaMatch,
    routeMatch,
  }))
