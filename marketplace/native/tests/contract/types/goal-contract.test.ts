import { describe, it, expect } from 'vitest'
import type { GoalContract, AcceptanceExample, EvidenceRequirement } from '../../../src/types/goal-contract.js'

describe('GoalContract type contract', () => {
  it('accepts a minimal valid contract', () => {
    const c: GoalContract = {
      situation: 's', motivation: 'm', outcome: 'o', beneficiary: 'self',
      hard_constraints: [], non_goals: [], acceptance_examples: [],
      evidence_required: [], execution_preferences: {},
      confidence: 0.8, ambiguity_flags: [], clarification_required: false,
    }
    expect(c.confidence).toBeGreaterThan(0)
  })

  it('AcceptanceExample shape', () => {
    const ex: AcceptanceExample = { given: 'g', when: 'w', then: 't' }
    expect(ex.given).toBe('g')
  })

  it('EvidenceRequirement shape', () => {
    const r: EvidenceRequirement = { stage: 'tech', field: '§Hosting' }
    expect(r.stage).toBe('tech')
  })
})
