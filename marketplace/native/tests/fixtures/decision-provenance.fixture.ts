/**
 * DecisionProvenance fixture factories — M4.3 (D2 §2.1).
 */

import type { DecisionProvenance } from '../../src/schemas/decision-provenance.js'

/**
 * Minimal valid DecisionProvenance — required fields populated to spec-minimum,
 * empty evidence array, terminal next_action_ref.
 */
export function validMinimal(): DecisionProvenance {
  return {
    id: 'dp-deadbeef',
    actor: 'asawa-ceo',
    agent_identity: { kind: 'claude-opus', id: 'claude-opus:abc' },
    timestamp: '2026-04-29T00:00:00.000Z',
    evidence: [],
    authority_id: 'A-asawa-ceo',
    policy_id: 'PROTO-019',
    policy_version: 'v1.0',
    confidence: 0.5,
    decision_kind: 'DECIDE',
    scope: 'CONSTITUTIONAL',
    outcome: 'approved native v1.0 M4 plan',
    next_action_ref: null,
  }
}

/**
 * Fully populated valid DecisionProvenance — non-empty evidence,
 * non-null next_action_ref pointing to another DP.
 */
export function validFull(): DecisionProvenance {
  return {
    id: 'dp-cafef00d',
    actor: 'sutra-os-team',
    agent_identity: {
      kind: 'codex',
      id: 'codex:session-xyz',
      version: '0.32',
    },
    timestamp: '2026-04-29T18:42:00.000Z',
    evidence: [
      {
        kind: 'json',
        schema_ref: 'native://schemas/charter',
        locator: '/tmp/charter.json',
        version: '1',
        mutability: 'immutable',
        retention: '180d',
        authoritative_status: 'authoritative',
      },
    ],
    authority_id: 'A-sutra-os-rotation',
    policy_id: 'D38-build-layer',
    policy_version: 'amend-2026-04-28',
    confidence: 0.92,
    decision_kind: 'APPROVE',
    scope: 'WORKFLOW',
    outcome: 'M4.3 schema lands per plan',
    next_action_ref: 'dp-deadbeef',
  }
}

/**
 * Invalid: missing required `policy_version` (forbidden coupling F-8 partial).
 */
export function invalidMissingRequired(): Partial<DecisionProvenance> {
  return {
    id: 'dp-bad',
    actor: 'x',
    agent_identity: { kind: 'human', id: 'human:asawa' },
    timestamp: '2026-04-29T00:00:00.000Z',
    evidence: [],
    authority_id: 'A-x',
    policy_id: 'PROTO-019',
    confidence: 0.5,
    decision_kind: 'DECIDE',
    scope: 'CONSTITUTIONAL',
    outcome: 'no version',
    next_action_ref: null,
  }
}
