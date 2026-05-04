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

/**
 * M4.6 — D2 §5: explicit authoritative-vs-advisory status per DataRef.
 * Default `authoritative` (safest). Re-exported here as a string-literal type
 * so the TS DataRef interface stays free of zod imports; the runtime schema
 * (DataRefSchema below) uses the zod enum from `./authoritative-status.ts`.
 */
export type AuthoritativeStatus = 'authoritative' | 'advisory'

export interface DataRef {
  kind: string
  schema_ref: string
  locator: string
  version: string
  mutability: DataMutability
  retention: string
  /**
   * M4.6 — D2 §5. Default `authoritative` (safest). Optional on the TS shape
   * because DataRefSchema.parse fills the default; existing callers that omit
   * the field continue to compile. When set, must be `authoritative` or
   * `advisory`.
   */
  authoritative_status?: AuthoritativeStatus
}

// M4.3: DataRef zod schema for use by DecisionProvenance.evidence (and other
// new M4 schemas). The TS interface remains the source-of-truth for primitives;
// this schema mirrors it for runtime parsing. Imported here so the dependency
// graph stays acyclic (schemas may import types/, never the reverse).
import { z } from 'zod'
import { AuthoritativeStatusSchema } from './authoritative-status.js'

// M4.7: re-export CutoverContract type for Charter consumers + downstream
// migration tooling (P-C12 at M10). Schema lives in src/schemas/cutover-contract.ts.
export type { CutoverContract } from '../schemas/cutover-contract.js'

export const DataRefSchema = z.object({
  kind: z.string().min(1),
  schema_ref: z.string().min(1),
  locator: z.string().min(1),
  version: z.string(),
  mutability: z.enum(['mutable', 'immutable']),
  retention: z.string(),
  // M4.6 — default `authoritative` per D2 §5; explicit `advisory` allowed.
  authoritative_status: AuthoritativeStatusSchema.default('authoritative'),
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

// M8 Group BB (T-115; codex pivot review 2026-04-30 fold). Extended with
// `'invoke_host_llm'` so a Workflow step can dispatch into a host-LLM Activity
// (Claude `--bare` first-class; codex advisory). The host CLI selection lives
// on a DEDICATED step contract field `WorkflowStep.host` (NOT step.inputs and
// NOT an orthogonal step.host_kind tag): codex pivot review CHANGE #2 — the
// step contract MUST be canonical at L2 BOUNDARY, not buried in inputs.
export type StepAction = 'spawn_sub_unit' | 'wait' | 'terminate' | 'invoke_host_llm'

/**
 * M8 Group BB (T-115). Host-LLM kind selector for `action='invoke_host_llm'`
 * steps. Two values at v1.0:
 *   - 'claude' — Anthropic's Claude Code CLI (`claude --bare --print`); the
 *     first-class host per the architecture pivot.
 *   - 'codex' — OpenAI's codex CLI (`codex exec`); advisory at v1.0 — MCP
 *     parity with Claude is NOT established (see host-llm-activity.ts module
 *     comment for scope details).
 *
 * Required iff `step.action === 'invoke_host_llm'`; forbidden otherwise. The
 * XOR rule is enforced at the L2 BOUNDARY law (canonical anchor) and mirrored
 * at the constructor + validator (`createWorkflow.validateStep` +
 * `isValidWorkflow`) per codex pivot review CHANGE #2.
 */
export type HostKind = 'claude' | 'codex'

export type StepFailureAction =
  | 'rollback'
  | 'escalate'
  | 'pause'
  | 'abort'
  | 'continue'

/**
 * V2.3 §A11: step has either skill_ref OR action (mutually exclusive).
 * Validation per L2 BOUNDARY: a step with neither is invalid.
 *
 * M7 Group V (T-093): `policy_check?: boolean` is ORTHOGONAL to the
 * skill_ref XOR action discipline — when true, the executor dispatches the
 * Charter's compiled policy through the OPAEvaluator BEFORE this step's
 * Activity runs. Workflow.modifies_sutra=true also implicitly enables
 * policy_check at every step (per V2.4 §A12 + M7 sovereignty discipline).
 * Default `undefined` ⇒ false (no policy gate).
 */
export interface WorkflowStep {
  step_id: number
  skill_ref?: string
  action?: StepAction
  inputs: DataRef[]
  outputs: DataRef[]
  on_failure: StepFailureAction
  policy_check?: boolean
  /**
   * M8 Group BB (T-115; codex pivot review CHANGE #2 fold). Host-LLM kind
   * selector for `action='invoke_host_llm'`. Required iff action is
   * 'invoke_host_llm'; forbidden for any other action and forbidden when
   * skill_ref is set. Enforced at L2 BOUNDARY (canonical anchor) +
   * createWorkflow.validateStep / isValidWorkflow (operational mirrors).
   *
   * NOT modeled as an orthogonal `host_kind` tag — codex pivot review #2:
   * the step contract for "what does this step DO" must encode the host
   * directly so L2 BOUNDARY captures the full dispatch decision in one
   * structural check (no bury-in-inputs anti-pattern).
   */
  host?: HostKind
  /**
   * M8 codex master review 2026-04-30 P2.1 fold. Optional JSON-Schema
   * string declaring the expected shape of the host-LLM response. When set
   * AND `action === 'invoke_host_llm'`, the executor:
   *   1. Stamps the response DataRef envelope's `schema_ref` with this value
   *      (parallels M6 `buildSkillOutputDataRef` in skill-invocation.ts which
   *      sets `schema_ref = Workflow.return_contract`).
   *   2. Validates the response against the schema via ajv. A validation
   *      miss synthesizes a step failure with errMsg
   *      `host_llm_output_validation:<details>` (sanitized via the same
   *      `sanitizeReasonForFailureReason` pipeline used for policy denies).
   *
   * When unset, the envelope's schema_ref defaults to '' (empty string —
   * "no contract declared") and no output validation runs.
   *
   * SchemaRef is a JSON Schema STRING (parsed lazily; ajv compile happens at
   * step-dispatch time, not at primitive-mint, since host-LLM steps are
   * synthesized in many places that should not need to compile schemas just
   * to construct the workflow). Codex P2.1 alignment with M6 contract drift —
   * the envelope MUST advertise the response schema, not the prompt schema.
   */
  return_contract?: SchemaRef
  /**
   * v1.3.0 W1.9 (codex W1.9 advisory fold). Optional per-step timeout (ms)
   * for action='invoke_host_llm'. Forwarded to hostLLMActivity. Defaults to
   * host-llm-activity default (60_000ms) when unset. Ignored for non-
   * invoke_host_llm steps.
   *
   * Additive field — no breaking change to existing serialized Workflows;
   * `createWorkflow` propagates it via the spec spread, validators ignore
   * unknown keys, and the dispatch site forwards `timeout_ms` only when
   * defined (undefined ⇒ host-llm-activity default).
   */
  timeout_ms?: number
}

// -----------------------------------------------------------------------------
// Workflow stringency — V2 §6 codification ladder
// -----------------------------------------------------------------------------

export type WorkflowStringency = 'task' | 'process' | 'protocol'

// -----------------------------------------------------------------------------
// Workflow autonomy_level — M5 Group J / T-045 / A-3
//
// V2 §17 routing — declares the level of autonomy the runtime is permitted to
// take when executing this Workflow. Default `manual` (safest). Required by
// step_graph executor (Group K) + failure_policy handler to gate auto-escalate
// vs human-loop semantics.
//
// `required_capabilities[]` REMOVED per codex P1.2 (deferred to v1.x; D-NS-9 (b)).
// -----------------------------------------------------------------------------

export type WorkflowAutonomyLevel = 'manual' | 'semi' | 'autonomous'

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
