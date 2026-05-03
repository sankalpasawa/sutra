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
import { createHash } from 'node:crypto';
import { appendFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { createDecisionProvenance, } from '../schemas/decision-provenance.js';
import { userKitRoot } from '../persistence/user-kit.js';
/**
 * Build a DecisionProvenance record for an emergence approve/reject. The id
 * is deterministic so replay produces identical records.
 */
export function buildEmergenceDecisionProvenance(input) {
    const idSource = `${input.decision_kind}|${input.pattern_id}|${input.target_workflow_id}|${input.decided_at_ms}`;
    const idHash = createHash('sha256').update(idSource).digest('hex').slice(0, 16);
    return createDecisionProvenance({
        id: `dp-${idHash}`,
        actor: 'founder',
        agent_identity: { kind: 'human', id: 'human:founder' },
        timestamp: new Date(input.decided_at_ms).toISOString(),
        evidence: [
            {
                kind: 'json',
                schema_ref: 'native://emergence/proposal-ledger/v1',
                locator: `cas://proposal/${input.pattern_id}`,
                version: '1.0.0',
                mutability: 'immutable',
                retention: 'permanent',
                authoritative_status: 'authoritative',
            },
        ],
        authority_id: 'founder',
        policy_id: 'D45',
        policy_version: '1.0.0',
        confidence: 1.0,
        decision_kind: input.decision_kind,
        scope: 'WORKFLOW',
        outcome: input.outcome,
        next_action_ref: input.decision_kind === 'APPROVE' ? input.target_workflow_id : null,
    });
}
/**
 * Append a DecisionProvenance record to the user-kit JSONL log. Creates the
 * directory on first use. JSON serialization is one line per record (POSIX
 * append is atomic for writes <PIPE_BUF; entries stay well under that).
 */
export function appendDecisionProvenanceLog(dp, opts = {}) {
    const dir = join(userKitRoot(opts), 'user-kit');
    if (!existsSync(dir))
        mkdirSync(dir, { recursive: true });
    const path = join(dir, 'decision-provenance.jsonl');
    appendFileSync(path, JSON.stringify(dp) + '\n', { encoding: 'utf8' });
    return path;
}
//# sourceMappingURL=emergence-provenance.js.map