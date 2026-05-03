/**
 * DecisionProvenance — D2 §2.1 (HIGHEST-LEVERAGE schema; M4.3).
 *
 * The constitutional decision shape — what every consequential decision in
 * Native attributes itself with. The OTel emission gateway lands at M8;
 * M4 ships the SCHEMA only.
 *
 * Spec source:
 * - holding/research/2026-04-29-native-d2-decision-provenance-spec.md §2.1
 * - holding/plans/native-v1.0/M4-schemas-edges.md §M4.3
 */
import { z } from 'zod';
import { AgentIdentitySchema } from '../types/agent-identity.js';
import { DataRefSchema } from '../types/index.js';
/** Provenance id pattern: `dp-<lowercase-hex>`. */
export const DP_ID_PATTERN = /^dp-[a-f0-9]+$/;
/** Workflow id pattern (mirrors `src/primitives/workflow.ts` W_ID_PATTERN). */
const W_ID_PATTERN = /^W-.+$/;
/**
 * Decision kinds — D1 §2 Authority Map.
 *
 * AUDIT added in Group G' fix-up (2026-04-29) per codex master P2.3:
 * D2 §195 uses `decision_kind=AUDIT` for drift detection / provenance audits.
 */
export const DecisionKindSchema = z.enum([
    'DECIDE',
    'EXECUTE',
    'OVERRIDE',
    'APPROVE',
    'REJECT',
    'DELEGATE',
    'TERMINATE',
    'AUDIT',
]);
/**
 * Decision scopes — D1 §3 Authority Map.
 *
 * PLUGIN + MARKETPLACE added in Group G' fix-up (2026-04-29) per codex master
 * P2.3: D1 §52 lists S-PLUGIN + S-MARKETPLACE as valid scopes.
 */
export const DecisionScopeSchema = z.enum([
    'CONSTITUTIONAL',
    'DOMAIN',
    'CHARTER',
    'TENANT',
    'WORKFLOW',
    'EXECUTION',
    'HOOK',
    'PLUGIN',
    'MARKETPLACE',
]);
/**
 * `next_action_ref` — chain to the next DP, the next Workflow, or null at
 * terminal. Discriminated by string-pattern at parse time.
 */
const NextActionRefSchema = z.union([
    z.string().regex(DP_ID_PATTERN),
    z.string().regex(W_ID_PATTERN),
    z.null(),
]);
/**
 * DecisionProvenance — D2 §2.1 verbatim.
 *
 * Required cross-coupling F-8 (partial in M4): `policy_id` and `policy_version`
 * are both `min(1)` here so neither can be empty. Full F-8 enforcement at
 * terminal_check lives in M4.9 chunk 2.
 */
export const DecisionProvenanceSchema = z.object({
    /** `dp-<hash>` — globally unique. */
    id: z.string().regex(DP_ID_PATTERN),
    /** Authority-holder id (D1 §1). Non-empty. */
    actor: z.string().min(1),
    /** Which LLM/agent (M4.2). */
    agent_identity: AgentIdentitySchema,
    /** ISO-8601 datetime. */
    timestamp: z.string().datetime(),
    /** Inputs the decision rested on. */
    evidence: z.array(DataRefSchema),
    /** Authority.id grounding the decision. Non-empty. */
    authority_id: z.string().min(1),
    /** e.g. "PROTO-019" or "D38-build-layer". Non-empty. */
    policy_id: z.string().min(1),
    /** Version of the policy at time of decision (closes Q8). Non-empty. */
    policy_version: z.string().min(1),
    /** Self-assessed confidence in [0, 1]. */
    confidence: z.number().min(0).max(1),
    /** D1 §2 enum. */
    decision_kind: DecisionKindSchema,
    /** D1 §3 enum. */
    scope: DecisionScopeSchema,
    /** Human-readable outcome statement. Non-empty. */
    outcome: z.string().min(1),
    /** Chain to subsequent DP, Workflow, or null at terminal. */
    next_action_ref: NextActionRefSchema,
});
/**
 * Construct a DecisionProvenance after schema validation. Throws on invalid input.
 */
export function createDecisionProvenance(input) {
    return DecisionProvenanceSchema.parse(input);
}
/**
 * Predicate: is this DecisionProvenance shape valid against D2 §2.1?
 */
export function isValidDecisionProvenance(v) {
    return DecisionProvenanceSchema.safeParse(v).success;
}
//# sourceMappingURL=decision-provenance.js.map