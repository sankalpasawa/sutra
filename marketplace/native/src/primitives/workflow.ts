/**
 * WORKFLOW — V2 §1 P3 + V2.1 §A4 + V2.2 §A10 + V2.3 §A11 + V2.4 §A12
 *
 * Executable operational recipe. Operationalizes a Charter (per L4 COMMITMENT).
 * A Skill is a Workflow with reuse_tag=true (V2.3 §A11 — Skills are LEAF Workflows).
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md
 */

import type {
  BoundaryEndpointRef,
  DataRef,
  Interface,
  OverrideAction,
  SchemaRef,
  StepAction,
  WorkflowStep,
  WorkflowStringency,
} from '../types/index.js'

/** Workflow id starts with 'W-' followed by hash/identifier. */
const W_ID_PATTERN = /^W-.+$/

const VALID_STRINGENCY: ReadonlySet<WorkflowStringency> = new Set([
  'task',
  'process',
  'protocol',
])

const VALID_OVERRIDE_ACTION: ReadonlySet<OverrideAction> = new Set([
  'pause',
  'splice',
  'restart',
  'escalate',
])

const VALID_STEP_ACTION: ReadonlySet<StepAction> = new Set([
  'spawn_sub_unit',
  'wait',
  'terminate',
])

/**
 * Workflow primitive shape — V2 §1 P3 + amendments.
 *
 * V2.3 §A11: a Skill is a Workflow with `reuse_tag=true`. Same primitive — different role.
 * V2.4 §A12: `modifies_sutra` triggers L6 REFLEXIVITY checks at terminal_check.
 */
export interface Workflow {
  id: string
  preconditions: string
  step_graph: WorkflowStep[]
  inputs: DataRef[]
  outputs: DataRef[]
  state: DataRef[]
  postconditions: string
  failure_policy: string
  stringency: WorkflowStringency
  /** Edges to BoundaryEndpoints via Interface contract. */
  interfaces_with: Interface[]

  // ---- V2.1 §A4 ----
  /**
   * If non-null, this Workflow MUST receive a response from the named
   * BoundaryEndpoint before completing. Used with TriggerSpec.pattern=negotiation
   * for codex review loops.
   */
  expects_response_from: BoundaryEndpointRef | null

  // ---- V2.2 §A10 ----
  /** Founder mid-flow override semantics. Default 'escalate' (safest). */
  on_override_action: OverrideAction

  // ---- V2.3 §A11 ----
  /** Frequent-reuse leaf marker. true => this Workflow IS a Skill. Default false. */
  reuse_tag: boolean
  /** Typed output schema for parent invocation. Required when reuse_tag=true; null otherwise allowed. */
  return_contract: SchemaRef | null

  // ---- V2.4 §A12 ----
  /** True iff this Workflow may modify Sutra structural paths. Triggers L6 + T6 at terminal_check. Default false. */
  modifies_sutra: boolean
}

/**
 * The fields a caller may omit; createWorkflow fills sensible V2-compliant defaults.
 */
export type WorkflowSpec = Omit<
  Workflow,
  'expects_response_from' | 'on_override_action' | 'reuse_tag' | 'return_contract' | 'modifies_sutra'
> &
  Partial<
    Pick<
      Workflow,
      'expects_response_from' | 'on_override_action' | 'reuse_tag' | 'return_contract' | 'modifies_sutra'
    >
  >

function validateStep(step: WorkflowStep, idx: number): void {
  const hasSkill = typeof step.skill_ref === 'string' && step.skill_ref.length > 0
  const hasAction = typeof step.action === 'string' && step.action.length > 0
  if (hasSkill && hasAction) {
    throw new Error(
      `Workflow.step_graph[${idx}]: skill_ref XOR action — both provided (mutually exclusive per V2.3 §A11)`,
    )
  }
  if (!hasSkill && !hasAction) {
    throw new Error(
      `Workflow.step_graph[${idx}]: skill_ref XOR action — must specify exactly one (L2 BOUNDARY)`,
    )
  }
  if (hasAction && !VALID_STEP_ACTION.has(step.action as StepAction)) {
    throw new Error(
      `Workflow.step_graph[${idx}].action must be one of spawn_sub_unit|wait|terminate; got "${String(step.action)}"`,
    )
  }
  if (typeof step.step_id !== 'number' || !Number.isInteger(step.step_id)) {
    throw new Error(`Workflow.step_graph[${idx}].step_id must be an integer`)
  }
  if (!Array.isArray(step.inputs) || !Array.isArray(step.outputs)) {
    throw new Error(`Workflow.step_graph[${idx}].inputs/outputs must be arrays`)
  }
  if (typeof step.on_failure !== 'string' || step.on_failure.length === 0) {
    throw new Error(`Workflow.step_graph[${idx}].on_failure must be a non-empty string`)
  }
}

/**
 * Construct a Workflow with V2.x-compliant defaults applied for omitted optional fields.
 * Returns a frozen object.
 */
export function createWorkflow(spec: WorkflowSpec): Workflow {
  if (!W_ID_PATTERN.test(spec.id)) {
    throw new Error(`Workflow.id must match pattern W-<hash>; got "${spec.id}"`)
  }
  if (!Array.isArray(spec.step_graph) || spec.step_graph.length === 0) {
    throw new Error('Workflow.step_graph must be a non-empty array')
  }
  if (!VALID_STRINGENCY.has(spec.stringency)) {
    throw new Error(
      `Workflow.stringency must be task|process|protocol; got "${String(spec.stringency)}"`,
    )
  }
  spec.step_graph.forEach((s, i) => validateStep(s, i))

  const onOverride: OverrideAction = spec.on_override_action ?? 'escalate'
  if (!VALID_OVERRIDE_ACTION.has(onOverride)) {
    throw new Error(
      `Workflow.on_override_action must be pause|splice|restart|escalate; got "${String(onOverride)}"`,
    )
  }

  const out: Workflow = {
    ...spec,
    step_graph: spec.step_graph.map((s) => ({ ...s, inputs: [...s.inputs], outputs: [...s.outputs] })),
    inputs: [...spec.inputs],
    outputs: [...spec.outputs],
    state: [...spec.state],
    interfaces_with: [...spec.interfaces_with],
    expects_response_from: spec.expects_response_from ?? null,
    on_override_action: onOverride,
    reuse_tag: spec.reuse_tag ?? false,
    return_contract: spec.return_contract ?? null,
    modifies_sutra: spec.modifies_sutra ?? false,
  }
  return Object.freeze(out)
}

/**
 * Predicate: is this Workflow shape valid against V2 §1 P3 + amendments?
 */
export function isValidWorkflow(w: Workflow): boolean {
  if (typeof w !== 'object' || w === null) return false
  if (typeof w.id !== 'string' || !W_ID_PATTERN.test(w.id)) return false
  if (!Array.isArray(w.step_graph) || w.step_graph.length === 0) return false
  if (!VALID_STRINGENCY.has(w.stringency)) return false
  if (!VALID_OVERRIDE_ACTION.has(w.on_override_action)) return false
  for (const step of w.step_graph) {
    const hasSkill = typeof step.skill_ref === 'string' && step.skill_ref.length > 0
    const hasAction = typeof step.action === 'string' && step.action.length > 0
    if (hasSkill === hasAction) return false // both true or both false => invalid
    if (hasAction && !VALID_STEP_ACTION.has(step.action as StepAction)) return false
  }
  return true
}
