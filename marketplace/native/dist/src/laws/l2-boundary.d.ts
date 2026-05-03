/**
 * L2 BOUNDARY law — V2 spec §3 row L2
 *
 * Rule: "If you cannot specify a boundary contract, it is not a model element.
 *        'Environment' is not a type."
 *
 * Mechanization: "Every Interface MUST have `contract_schema` (JSON schema)."
 *
 * For Native v1.0 (M3) we check structural validity of the contract_schema
 * field only — non-empty string + parseable as JSON. Full JSON Schema (Draft-7+)
 * compilation via Ajv is deferred to M5 Workflow Engine integration per
 * `holding/plans/native-v1.0/M3-laws.md` M3.2.3.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §3 L2
 *
 * ---------------------------------------------------------------------------
 * Canonical XOR enforcement at L2 BOUNDARY per V2 §A11 + codex M6 P2.1
 * 2026-04-30.
 *
 * V2.3 §A11 mandates that every WorkflowStep specify EITHER `skill_ref` XOR
 * `action` (not both, not neither). That predicate IS a boundary-contract law:
 * a step without exactly one of those two fields has no specified boundary
 * for "what does this step DO". Per codex P2.1, the canonical anchor for the
 * XOR rule is L2 BOUNDARY (this file).
 *
 * Operational mirror: the runtime check ships at the constructor + validator
 * layer in `src/primitives/workflow.ts` (`createWorkflow.validateStep` +
 * `isValidWorkflow`) so the violation surfaces at primitive-mint time and
 * during deserialized-record validation, not at execution time. That mirror
 * has been audited (M6 Group O T-068, 2026-04-30) and is in agreement with
 * the L2 BOUNDARY rule stated here. No new check is added at this layer —
 * the constructor + validator pair is already authoritative; this comment
 * records the canonical anchor relationship.
 *
 * ---------------------------------------------------------------------------
 * M8 Group BB codex pivot review fold #2 — host-LLM step contract canonical
 * at L2 BOUNDARY (2026-04-30; DIRECTIVE-ID 1777521736).
 *
 * The architecture pivot adds a third required structural slot: when
 * `step.action === 'invoke_host_llm'`, the step contract MUST also specify
 * `step.host: 'claude' | 'codex'` (the host CLI to dispatch to). Required
 * iff action='invoke_host_llm'; forbidden otherwise.
 *
 * Why this is an L2 BOUNDARY rule (not a free-form attribute on inputs):
 * "what does this step DO" must be FULLY specified by structural fields the
 * boundary check can read. Burying host selection in `step.inputs` would let
 * a step exist whose dispatch target is opaque until inputs are interpreted
 * — that is exactly the "Environment is not a type" anti-pattern V2 §3 L2
 * forbids. Codex pivot review CHANGE #2 made this canonical: host-XOR is L2
 * BOUNDARY, mirrored at the workflow constructor + validator like the
 * skill_ref/action XOR before it.
 *
 * Operational mirrors:
 *   - `createWorkflow.validateStep` (src/primitives/workflow.ts):
 *       throws when action='invoke_host_llm' && !host
 *       throws when action!='invoke_host_llm' && host!==undefined
 *   - `isValidWorkflow` (same file): defensive return-false on the same
 *     conditions for deserialized records.
 * ---------------------------------------------------------------------------
 */
import type { Interface } from '../types/index.js';
export declare const l2Boundary: {
    /**
     * Is this Interface valid against L2 BOUNDARY?
     *
     * True iff:
     *   - `iface.contract_schema` is a non-empty string, AND
     *   - the string parses as valid JSON.
     *
     * Defensive shape checks for deserialized records (Interface may arrive
     * from a JSONL store).
     */
    isValid(iface: Interface | unknown): boolean;
};
//# sourceMappingURL=l2-boundary.d.ts.map