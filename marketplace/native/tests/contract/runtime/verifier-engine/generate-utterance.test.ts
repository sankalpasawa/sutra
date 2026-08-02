/**
 * Contract tests — generateUtterance (Verifier Engine v1, Wave 2 step 1).
 *
 * Coverage:
 *   - {{var}} substitution from scenario.goal_seed → final utterance string
 *   - determinism: same inputs → same output across calls
 *   - profile_id mismatch throws
 *   - missingSubstitutions reports unfilled placeholders
 *   - missing required substitution throws
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §7
 */

import { describe, it, expect } from 'vitest'
import {
  generateUtterance,
  missingSubstitutions,
} from '../../../../src/runtime/verifier-engine/user-simulator/generate-utterance.js'
import type { UserProfile, Scenario } from '../../../../src/types/user-profile.js'

const profile: UserProfile = {
  id: 'pet-owner-casual',
  voice: 'first-person-casual',
  communication_style: 'direct, warm, plain-spoken',
  utterance_template: 'I want a {{deliverable}} for my {{subject}}',
}

const scenario: Scenario = {
  id: 'pets-site',
  profile_id: 'pet-owner-casual',
  goal_seed: { deliverable: 'website', subject: 'pets' },
}

describe('generateUtterance', () => {
  it('substitutes goal_seed into utterance_template', () => {
    expect(generateUtterance(profile, scenario)).toBe('I want a website for my pets')
  })

  it('is deterministic — same inputs produce same output across calls', () => {
    const a = generateUtterance(profile, scenario)
    const b = generateUtterance(profile, scenario)
    expect(a).toBe(b)
  })

  it('throws when scenario references different profile_id', () => {
    const wrong: Scenario = { ...scenario, profile_id: 'other' }
    expect(() => generateUtterance(profile, wrong)).toThrow(/profile_id mismatch/)
  })

  it('missingSubstitutions reports unfilled placeholders', () => {
    const incomplete: Scenario = { ...scenario, goal_seed: { deliverable: 'website' } }
    expect(missingSubstitutions(profile, incomplete)).toEqual(['subject'])
  })

  it('throws when required substitutions missing', () => {
    const incomplete: Scenario = { ...scenario, goal_seed: { deliverable: 'website' } }
    expect(() => generateUtterance(profile, incomplete)).toThrow(/missing substitution/)
  })
})
