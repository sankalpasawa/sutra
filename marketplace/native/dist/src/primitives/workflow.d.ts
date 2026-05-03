/**
 * WORKFLOW — V2 §1 P3 + V2.1 §A4 + V2.2 §A10 + V2.3 §A11 + V2.4 §A12
 *
 * Executable operational recipe. Operationalizes a Charter (per L4 COMMITMENT).
 * A Skill is a Workflow with reuse_tag=true (V2.3 §A11 — Skills are LEAF Workflows).
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md
 */
import type { BoundaryEndpointRef, DataRef, Interface, OverrideAction, SchemaRef, WorkflowAutonomyLevel, WorkflowStep, WorkflowStringency } from '../types/index.js';
import { type ExtensionRef } from '../types/extension.js';
/**
 * Workflow primitive shape — V2 §1 P3 + amendments.
 *
 * V2.3 §A11: a Skill is a Workflow with `reuse_tag=true`. Same primitive — different role.
 * V2.4 §A12: `modifies_sutra` triggers L6 REFLEXIVITY checks at terminal_check.
 */
export interface Workflow {
    id: string;
    preconditions: string;
    step_graph: WorkflowStep[];
    inputs: DataRef[];
    outputs: DataRef[];
    state: DataRef[];
    postconditions: string;
    failure_policy: string;
    stringency: WorkflowStringency;
    /** Edges to BoundaryEndpoints via Interface contract. */
    interfaces_with: Interface[];
    /**
     * If non-null, this Workflow MUST receive a response from the named
     * BoundaryEndpoint before completing. Used with TriggerSpec.pattern=negotiation
     * for codex review loops.
     */
    expects_response_from: BoundaryEndpointRef | null;
    /** Founder mid-flow override semantics. Default 'escalate' (safest). */
    on_override_action: OverrideAction;
    /** Frequent-reuse leaf marker. true => this Workflow IS a Skill. Default false. */
    reuse_tag: boolean;
    /** Typed output schema for parent invocation. Required when reuse_tag=true; null otherwise allowed. */
    return_contract: SchemaRef | null;
    /** True iff this Workflow may modify Sutra structural paths. Triggers L6 + T6 at terminal_check. Default false. */
    modifies_sutra: boolean;
    /**
     * Owning Tenant id when this Workflow's state is owned by a specific Tenant.
     * D-NS-11 founder default (c) applied: explicit declaration; required when
     * Workflow crosses 2+ Tenants. Single-tenant v1.0: null is acceptable;
     * runtime will assert non-null at terminal_check (M4.9 chunk 2 enforcement).
     * Pattern: `T-<id>` (must match `src/schemas/tenant.ts` TENANT_ID_PATTERN).
     */
    custody_owner: string | null;
    /**
     * v1.0→v1.x extension seam. v1.0 enforcement (D4 §7.3): MUST be null;
     * forbidden coupling enforced at terminal_check (M4.9). When v1.x supplies a
     * value, MUST match `EXTENSION_REF_PATTERN` (`/^ext-[a-z0-9-]+$/`).
     */
    extension_ref: ExtensionRef;
    /**
     * Autonomy level the runtime is permitted to take when executing this
     * Workflow. Default `manual` (safest). Used by step_graph executor (Group K)
     * + failure_policy to gate auto-escalate vs human-loop semantics.
     *
     * `required_capabilities[]` REMOVED per codex P1.2 (D-NS-9 (b)) — deferred
     * to v1.x.
     */
    autonomy_level: WorkflowAutonomyLevel;
}
/**
 * The fields a caller may omit; createWorkflow fills sensible V2-compliant defaults.
 */
export type WorkflowSpec = Omit<Workflow, 'expects_response_from' | 'on_override_action' | 'reuse_tag' | 'return_contract' | 'modifies_sutra' | 'custody_owner' | 'extension_ref' | 'autonomy_level'> & Partial<Pick<Workflow, 'expects_response_from' | 'on_override_action' | 'reuse_tag' | 'return_contract' | 'modifies_sutra' | 'custody_owner' | 'extension_ref' | 'autonomy_level'>>;
/**
 * Construct a Workflow with V2.x-compliant defaults applied for omitted optional fields.
 * Returns a frozen object.
 */
export declare function createWorkflow(spec: WorkflowSpec): Workflow;
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
export declare function isValidWorkflow(w: Workflow): boolean;
//# sourceMappingURL=workflow.d.ts.map