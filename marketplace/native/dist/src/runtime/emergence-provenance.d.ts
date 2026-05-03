/**
 * emergence-provenance — DecisionProvenance emission + JSONL audit log for
 * the v1.2 organic-emergence loop (codex master P1 fold 2026-05-03).
 *
 * The DP schema (D2) requires AgentIdentity, policy_id/version, scope, etc.
 * For the v1 emergence loop:
 *   - actor          = 'founder'
 *   - agent_identity = { kind: 'human', id: 'human:founder' }
 *   - authority_id   = 'founder' (constitutional)
 *   - policy_id      = 'D45' (the scope-split direction governing this path)
 *   - policy_version = '1.0.0'
 *   - scope          = 'WORKFLOW' (each decision is per-Workflow registration)
 *   - confidence     = 1.0 (founder explicit Y/N — no LLM uncertainty)
 *
 * The JSONL log lives at $SUTRA_NATIVE_HOME/user-kit/decision-provenance.jsonl
 * — append-only, mirrors the existing artifact-catalog index.jsonl pattern.
 */
import { type DecisionProvenance } from '../schemas/decision-provenance.js';
import { type UserKitOptions } from '../persistence/user-kit.js';
export interface EmergenceDecisionInput {
    readonly decision_kind: 'APPROVE' | 'REJECT';
    /** Pattern id that drove this decision; goes into evidence locator. */
    readonly pattern_id: string;
    /** Target Workflow id whose registration this decision authorized/rejected. */
    readonly target_workflow_id: string;
    readonly decided_at_ms: number;
    readonly outcome: string;
}
/**
 * Build a DecisionProvenance record for an emergence approve/reject. The id
 * is deterministic so replay produces identical records.
 */
export declare function buildEmergenceDecisionProvenance(input: EmergenceDecisionInput): DecisionProvenance;
/**
 * Append a DecisionProvenance record to the user-kit JSONL log. Creates the
 * directory on first use. JSON serialization is one line per record (POSIX
 * append is atomic for writes <PIPE_BUF; entries stay well under that).
 */
export declare function appendDecisionProvenanceLog(dp: DecisionProvenance, opts?: UserKitOptions): string;
//# sourceMappingURL=emergence-provenance.d.ts.map