/**
 * Tier-1 schema checks. If contract is shallow, low-confidence, or flagged
 * for clarification, the pipeline should halt before tier-2/3/4.
 *
 * Pure function over the captured GoalContract; no I/O. Cheap deterministic
 * gate so downstream LLM-driven tiers never run on garbage input.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */

import type { GoalContract } from '../../../types/goal-contract.js'
import type { AssertionResult } from '../../../types/assertion-report.js'

const CONFIDENCE_THRESHOLD = 0.6
const REQUIRED_FIELDS = ['situation', 'motivation', 'outcome', 'beneficiary'] as const

export function runTier1Schema(contract: GoalContract): AssertionResult[] {
  const empty = REQUIRED_FIELDS.filter(f => !contract[f] || contract[f].trim() === '')
  return [
    {
      id: 'tier-1/required-fields',
      tier: 'schema',
      axis: 'Outcome-Fidelity',
      status: empty.length === 0 ? 'PASS' : 'FAIL',
      message:
        empty.length === 0
          ? 'all required fields populated'
          : `empty fields: ${empty.join(', ')}`,
    },
    {
      id: 'tier-1/confidence-threshold',
      tier: 'schema',
      axis: 'Outcome-Fidelity',
      status: contract.confidence >= CONFIDENCE_THRESHOLD ? 'PASS' : 'FAIL',
      message: `confidence=${contract.confidence} threshold=${CONFIDENCE_THRESHOLD}`,
    },
    {
      id: 'tier-1/clarification-not-required',
      tier: 'schema',
      axis: 'Outcome-Fidelity',
      status: contract.clarification_required ? 'FAIL' : 'PASS',
      message: contract.clarification_required
        ? `clarification required; flags: ${contract.ambiguity_flags.join('; ')}`
        : 'no clarification required',
    },
  ]
}
