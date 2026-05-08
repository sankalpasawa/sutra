/**
 * Tier-1 schema layer contract tests.
 *
 * Verifies that runTier1Schema returns three AssertionResult rows checking:
 *   - required-fields populated
 *   - confidence >= threshold
 *   - clarification_required is false
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */

import { describe, it, expect } from 'vitest'
import { runTier1Schema } from '../../../../src/runtime/verifier-engine/contract-verifier/layer-schema.js'
import type { GoalContract } from '../../../../src/types/goal-contract.js'

const baseC = (): GoalContract => ({
  situation: 's',
  motivation: 'm',
  outcome: 'o',
  beneficiary: 'self',
  hard_constraints: [],
  non_goals: [],
  acceptance_examples: [],
  evidence_required: [],
  execution_preferences: {},
  confidence: 0.8,
  ambiguity_flags: [],
  clarification_required: false,
})

describe('runTier1Schema', () => {
  it('PASS when populated and confidence>=0.6', () => {
    const r = runTier1Schema(baseC())
    expect(r.find(x => x.id === 'tier-1/required-fields')!.status).toBe('PASS')
    expect(r.find(x => x.id === 'tier-1/confidence-threshold')!.status).toBe('PASS')
    expect(r.find(x => x.id === 'tier-1/clarification-not-required')!.status).toBe('PASS')
  })

  it('FAIL when confidence below threshold', () => {
    const r = runTier1Schema({ ...baseC(), confidence: 0.4 })
    expect(r.find(x => x.id === 'tier-1/confidence-threshold')!.status).toBe('FAIL')
  })

  it('FAIL when clarification_required is true', () => {
    const r = runTier1Schema({ ...baseC(), clarification_required: true, ambiguity_flags: ['ugh'] })
    expect(r.find(x => x.id === 'tier-1/clarification-not-required')!.status).toBe('FAIL')
  })
})
