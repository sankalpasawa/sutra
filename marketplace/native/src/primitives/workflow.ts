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
  StepFailureAction,
  WorkflowAutonomyLevel,
  WorkflowStep,
  WorkflowStringency,
} from '../types/index.js'
import {
  EXTENSION_REF_PATTERN,
  type ExtensionRef,
} from '../types/extension.js'

/** Workflow id starts with 'W-' followed by hash/identifier. */
const W_ID_PATTERN = /^W-.+$/

/**
 * Tenant id pattern (must match `src/schemas/tenant.ts` TENANT_ID_PATTERN).
 * Duplicated to keep workflow.ts zero-dependency on zod at the type layer.
 */
const TENANT_ID_PATTERN = /^T-[a-z0-9-]+$/

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

// M8 Group BB (T-115). 'invoke_host_llm' added — host-LLM Activity dispatch.
const VALID_STEP_ACTION: ReadonlySet<StepAction> = new Set([
  'spawn_sub_unit',
  'wait',
  'terminate',
  'invoke_host_llm',
])

// M8 Group BB (T-115; codex pivot review CHANGE #2 fold). Valid HostKind
// values for `step.host` when `step.action === 'invoke_host_llm'`. Mirrored
// at the runtime validator below.
const VALID_HOST_KIND: ReadonlySet<'claude' | 'codex'> = new Set(['claude', 'codex'])

const VALID_STEP_FAILURE_ACTION: ReadonlySet<StepFailureAction> = new Set([
  'rollback',
  'escalate',
  'pause',
  'abort',
  'continue',
])

const VALID_AUTONOMY_LEVEL: ReadonlySet<WorkflowAutonomyLevel> = new Set([
  'manual',
  'semi',
  'autonomous',
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

  // ---- M4.4 — D1 §2 P-A4 ----
  /**
   * Owning Tenant id when this Workflow's state is owned by a specific Tenant.
   * D-NS-11 founder default (c) applied: explicit declaration; required when
   * Workflow crosses 2+ Tenants. Single-tenant v1.0: null is acceptable;
   * runtime will assert non-null at terminal_check (M4.9 chunk 2 enforcement).
   * Pattern: `T-<id>` (must match `src/schemas/tenant.ts` TENANT_ID_PATTERN).
   */
  custody_owner: string | null

  // ---- M4.5 — D4 §7 (D-NS-9 default b: only extension_ref ships) ----
  /**
   * v1.0→v1.x extension seam. v1.0 enforcement (D4 §7.3): MUST be null;
   * forbidden coupling enforced at terminal_check (M4.9). When v1.x supplies a
   * value, MUST match `EXTENSION_REF_PATTERN` (`/^ext-[a-z0-9-]+$/`).
   */
  extension_ref: ExtensionRef

  // ---- M5 Group J / T-045 — A-3 ----
  /**
   * Autonomy level the runtime is permitted to take when executing this
   * Workflow. Default `manual` (safest). Used by step_graph executor (Group K)
   * + failure_policy to gate auto-escalate vs human-loop semantics.
   *
   * `required_capabilities[]` REMOVED per codex P1.2 (D-NS-9 (b)) — deferred
   * to v1.x.
   */
  autonomy_level: WorkflowAutonomyLevel
}

/**
 * The fields a caller may omit; createWorkflow fills sensible V2-compliant defaults.
 */
export type WorkflowSpec = Omit<
  Workflow,
  'expects_response_from' | 'on_override_action' | 'reuse_tag' | 'return_contract' | 'modifies_sutra' | 'custody_owner' | 'extension_ref' | 'autonomy_level'
> &
  Partial<
    Pick<
      Workflow,
      'expects_response_from' | 'on_override_action' | 'reuse_tag' | 'return_contract' | 'modifies_sutra' | 'custody_owner' | 'extension_ref' | 'autonomy_level'
    >
  >

function validateStep(step: WorkflowStep, idx: number): void {
  // Operational mirror of L2 BOUNDARY per codex M6 P2.1 (2026-04-30).
  // Canonical anchor: src/laws/l2-boundary.ts — every step MUST specify a
  // boundary contract for "what it does", which V2.3 §A11 codifies as
  // skill_ref XOR action. This validator + isValidWorkflow are the runtime
  // mirrors; they enforce the rule at primitive-mint + deserialization time.
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
      `Workflow.step_graph[${idx}].action must be one of spawn_sub_unit|wait|terminate|invoke_host_llm; got "${String(step.action)}"`,
    )
  }
  // M8 Group BB (T-115; codex pivot review CHANGE #2 fold). Host-XOR rule —
  // operational mirror of l2-boundary.ts canonical anchor (T-116 comment).
  // `step.host` is REQUIRED iff `action === 'invoke_host_llm'`; FORBIDDEN
  // for any other action AND when `skill_ref` is set. The XOR keeps the step
  // contract canonical: dispatch-target ('what does this DO') is fully
  // specified by `(skill_ref | action [+ host if action=invoke_host_llm])`.
  const hasHost = step.host !== undefined && step.host !== null
  if (step.action === 'invoke_host_llm') {
    if (!hasHost) {
      throw new Error(
        `Workflow.step_graph[${idx}].host is required when action='invoke_host_llm' (M8 Group BB; codex pivot review CHANGE #2 — host-XOR canonical at L2 BOUNDARY)`,
      )
    }
    if (typeof step.host !== 'string' || !VALID_HOST_KIND.has(step.host as 'claude' | 'codex')) {
      throw new Error(
        `Workflow.step_graph[${idx}].host must be 'claude' or 'codex' when action='invoke_host_llm'; got "${String(step.host)}"`,
      )
    }
  } else {
    if (hasHost) {
      throw new Error(
        `Workflow.step_graph[${idx}].host is forbidden unless action='invoke_host_llm' (M8 Group BB; codex pivot review CHANGE #2 — host-XOR canonical at L2 BOUNDARY); got host="${String(step.host)}" with action="${String(step.action)}"`,
      )
    }
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
  if (!VALID_STEP_FAILURE_ACTION.has(step.on_failure as StepFailureAction)) {
    throw new Error(
      `Workflow.step_graph[${idx}].on_failure must be one of rollback|escalate|pause|abort|continue; got "${String(step.on_failure)}"`,
    )
  }
  // M7 Group V (T-093). Defensive runtime check — `policy_check` is optional
  // (default undefined ⇒ no gate); when supplied it MUST be boolean.
  if (step.policy_check !== undefined && typeof step.policy_check !== 'boolean') {
    throw new Error(
      `Workflow.step_graph[${idx}].policy_check must be a boolean when supplied; got "${typeof step.policy_check}"`,
    )
  }
  // M8 codex master review 2026-04-30 P2.1 fold. Step-level `return_contract`
  // is optional; when supplied it MUST be a non-empty SchemaRef string AND
  // the step MUST have action='invoke_host_llm' (other step shapes do not
  // declare an output schema at the step level — Skill outputs use
  // Workflow.return_contract via the SkillEngine path instead).
  if (step.return_contract !== undefined) {
    if (typeof step.return_contract !== 'string' || step.return_contract.length === 0) {
      throw new Error(
        `Workflow.step_graph[${idx}].return_contract must be a non-empty string when supplied; got "${typeof step.return_contract}"`,
      )
    }
    if (step.action !== 'invoke_host_llm') {
      throw new Error(
        `Workflow.step_graph[${idx}].return_contract is only permitted when action='invoke_host_llm' (codex M8 P2.1 fold); got action="${String(step.action)}"`,
      )
    }
  }
}

/** Validate expects_response_from is null or a non-empty string (BoundaryEndpointRef). */
function validateExpectsResponseFrom(value: unknown): void {
  if (value === null || value === undefined) return
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(
      'Workflow.expects_response_from must be null or a non-empty BoundaryEndpoint reference string',
    )
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

  // Codex M3 P1 fix 2026-04-28: enforce unique step_id across step_graph.
  // L4/T3 (tracesAllSteps) keys per-step coverage by step_id via Map<number, _>;
  // duplicate ids would silently collapse coverage records and let unsoundness
  // through. Catch at the boundary (createWorkflow) and at the validator
  // (isValidWorkflow) for deserialized records.
  {
    const seen = new Set<number>()
    for (let i = 0; i < spec.step_graph.length; i++) {
      const id = spec.step_graph[i]!.step_id
      if (seen.has(id)) {
        throw new Error(
          `Workflow.step_graph[${i}].step_id=${id} duplicates an earlier step (V2 §1 P3 — step_ids MUST be unique within a Workflow; required for L4/T3 coverage soundness)`,
        )
      }
      seen.add(id)
    }
  }

  const onOverride: OverrideAction = spec.on_override_action ?? 'escalate'
  if (!VALID_OVERRIDE_ACTION.has(onOverride)) {
    throw new Error(
      `Workflow.on_override_action must be pause|splice|restart|escalate; got "${String(onOverride)}"`,
    )
  }

  // V2.1 §A4 — expects_response_from must be null or non-empty string
  validateExpectsResponseFrom(spec.expects_response_from)

  // V2.4 §A12 — modifies_sutra must be boolean (defensive runtime check)
  if (spec.modifies_sutra !== undefined && typeof spec.modifies_sutra !== 'boolean') {
    throw new Error(
      `Workflow.modifies_sutra must be a boolean; got "${typeof spec.modifies_sutra}"`,
    )
  }

  // V2.3 §A11 — reuse_tag must be boolean (defensive runtime check)
  if (spec.reuse_tag !== undefined && typeof spec.reuse_tag !== 'boolean') {
    throw new Error(
      `Workflow.reuse_tag must be a boolean; got "${typeof spec.reuse_tag}"`,
    )
  }

  const reuseTag: boolean = spec.reuse_tag ?? false
  const returnContract: SchemaRef | null = spec.return_contract ?? null

  // V2.3 §A11 HARD — Skill (reuse_tag=true) requires a non-empty return_contract schema-ref
  if (reuseTag) {
    if (
      returnContract === null ||
      returnContract === undefined ||
      typeof returnContract !== 'string' ||
      returnContract.length === 0
    ) {
      throw new Error(
        'Workflow.return_contract is required when reuse_tag=true (V2.3 §A11 — every Skill MUST have a return_contract schema-ref)',
      )
    }
  } else {
    // reuse_tag=false: return_contract may be null OR a non-empty string.
    // Aligns constructor with isValidWorkflow predicate (V2 §3 HARD — boundary
    // must not mint records the validator considers invalid).
    if (
      returnContract !== null &&
      (typeof returnContract !== 'string' || returnContract.length === 0)
    ) {
      throw new Error(
        'Workflow.return_contract must be null OR a non-empty string when reuse_tag=false (constructor/validator alignment per V2 §3 HARD)',
      )
    }
  }

  // M4.4 — D-NS-11 default (c): custody_owner is an explicit declaration.
  // null is acceptable at v1.0 (single-tenant); when supplied, must match
  // T-<id> pattern. Cross-tenant detection (asserting non-null at terminal_check
  // when Workflow crosses 2+ Tenants) lands at M4.9 chunk 2.
  const custodyOwner = spec.custody_owner ?? null
  if (custodyOwner !== null) {
    if (typeof custodyOwner !== 'string' || !TENANT_ID_PATTERN.test(custodyOwner)) {
      throw new Error(
        `Workflow.custody_owner must be null or match T-<id> pattern (M4.4; D-NS-11); got "${String(custodyOwner)}"`,
      )
    }
  }

  // M4.5 — D-NS-9 default (b): only `extension_ref` extension seam ships.
  // v1.0 enforcement (extension_ref MUST be null) is checked at terminal_check
  // (forbidden coupling F-11, Group G' fix-up 2026-04-29). At the constructor
  // we accept null OR a string that matches the EXTENSION_REF_PATTERN;
  // future-format strings are valid shapes here so v1.x extensions can be
  // authored against the same API.
  const extensionRef: ExtensionRef = spec.extension_ref ?? null
  if (extensionRef !== null) {
    if (typeof extensionRef !== 'string' || !EXTENSION_REF_PATTERN.test(extensionRef)) {
      throw new Error(
        `Workflow.extension_ref must be null or match ext-<id> pattern (M4.5; D4 §7); got "${String(extensionRef)}"`,
      )
    }
  }

  // M5 Group J / T-045 — autonomy_level: enum manual|semi|autonomous; default 'manual'.
  // Required by step_graph executor (Group K) + failure_policy. `required_capabilities[]`
  // REMOVED per codex P1.2 (deferred to v1.x; D-NS-9 (b)).
  const autonomyLevel: WorkflowAutonomyLevel = spec.autonomy_level ?? 'manual'
  if (!VALID_AUTONOMY_LEVEL.has(autonomyLevel)) {
    throw new Error(
      `Workflow.autonomy_level must be manual|semi|autonomous; got "${String(autonomyLevel)}"`,
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
    reuse_tag: reuseTag,
    return_contract: returnContract,
    modifies_sutra: spec.modifies_sutra ?? false,
    custody_owner: custodyOwner,
    extension_ref: extensionRef,
    autonomy_level: autonomyLevel,
  }
  return Object.freeze(out)
}

/**
 * Predicate: is this Workflow shape valid against V2 §1 P3 + amendments?
 *
 * Defensively validates deserialized records — TS compile-time types alone are
 * insufficient when records arrive from JSONL stores or external producers.
 *
 * Validates: id, step_graph (incl. on_failure enum, skill_ref XOR action),
 * stringency, on_override_action, expects_response_from shape, modifies_sutra
 * type, reuse_tag type, reuse_tag→return_contract HARD requirement (V2.3 §A11).
 */
export function isValidWorkflow(w: Workflow): boolean {
  if (typeof w !== 'object' || w === null) return false
  if (typeof w.id !== 'string' || !W_ID_PATTERN.test(w.id)) return false
  if (!Array.isArray(w.step_graph) || w.step_graph.length === 0) return false
  if (!VALID_STRINGENCY.has(w.stringency)) return false
  if (!VALID_OVERRIDE_ACTION.has(w.on_override_action)) return false
  // V2.1 §A4 — expects_response_from: null OR non-empty string
  if (
    w.expects_response_from !== null &&
    (typeof w.expects_response_from !== 'string' || w.expects_response_from.length === 0)
  ) {
    return false
  }
  // V2.4 §A12 — modifies_sutra MUST be boolean (defensive)
  if (typeof w.modifies_sutra !== 'boolean') return false
  // V2.3 §A11 — reuse_tag MUST be boolean (defensive)
  if (typeof w.reuse_tag !== 'boolean') return false
  // V2.3 §A11 HARD — when reuse_tag=true, return_contract MUST be a non-empty string
  if (w.reuse_tag) {
    if (
      w.return_contract === null ||
      typeof w.return_contract !== 'string' ||
      w.return_contract.length === 0
    ) {
      return false
    }
  } else {
    // reuse_tag=false: return_contract may be null OR a non-empty string
    if (
      w.return_contract !== null &&
      (typeof w.return_contract !== 'string' || w.return_contract.length === 0)
    ) {
      return false
    }
  }
  // Codex M3 P1 fix 2026-04-28: defensively reject deserialized records that
  // carry duplicate step_ids. Constructor enforces uniqueness; validator must
  // agree (V2 §3 HARD — boundary must not mint records the validator considers
  // invalid; same direction holds for deserialized records).
  const seenStepIds = new Set<number>()
  for (const step of w.step_graph) {
    const hasSkill = typeof step.skill_ref === 'string' && step.skill_ref.length > 0
    const hasAction = typeof step.action === 'string' && step.action.length > 0
    if (hasSkill === hasAction) return false // both true or both false => invalid
    if (hasAction && !VALID_STEP_ACTION.has(step.action as StepAction)) return false
    // V2.3 §A11 — on_failure must be in StepFailureAction enum
    if (typeof step.on_failure !== 'string' || step.on_failure.length === 0) return false
    if (!VALID_STEP_FAILURE_ACTION.has(step.on_failure as StepFailureAction)) return false
    // step_id uniqueness (codex M3 P1)
    if (typeof step.step_id !== 'number' || !Number.isInteger(step.step_id)) return false
    if (seenStepIds.has(step.step_id)) return false
    seenStepIds.add(step.step_id)
    // M8 Group BB (T-115) — host-XOR rule mirror. Required iff action='invoke_host_llm';
    // forbidden otherwise. Defensive validation for deserialized records (constructor
    // enforces the same; validator must agree per V2 §3 HARD).
    const hasHost = step.host !== undefined && step.host !== null
    if (step.action === 'invoke_host_llm') {
      if (!hasHost) return false
      if (typeof step.host !== 'string' || !VALID_HOST_KIND.has(step.host as 'claude' | 'codex')) {
        return false
      }
    } else if (hasHost) {
      return false
    }
    // M8 codex master review 2026-04-30 P2.1 fold. Defensive — step.return_contract
    // is permitted only when action='invoke_host_llm' AND must be a non-empty string.
    if (step.return_contract !== undefined) {
      if (typeof step.return_contract !== 'string' || step.return_contract.length === 0) {
        return false
      }
      if (step.action !== 'invoke_host_llm') {
        return false
      }
    }
  }
  // M4.4 — custody_owner must be null OR match T-<id> pattern.
  if (
    w.custody_owner !== null &&
    (typeof w.custody_owner !== 'string' || !TENANT_ID_PATTERN.test(w.custody_owner))
  ) {
    return false
  }
  // M4.5 — extension_ref must be null OR match ext-<id> pattern.
  if (
    w.extension_ref !== null &&
    (typeof w.extension_ref !== 'string' || !EXTENSION_REF_PATTERN.test(w.extension_ref))
  ) {
    return false
  }
  // M5 Group J / T-045 — autonomy_level MUST be in WorkflowAutonomyLevel enum.
  if (
    typeof w.autonomy_level !== 'string' ||
    !VALID_AUTONOMY_LEVEL.has(w.autonomy_level as WorkflowAutonomyLevel)
  ) {
    return false
  }
  return true
}
