import { describe, it, expect } from 'vitest'
import type { UserProfile, Scenario } from '../../../src/types/user-profile.js'

describe('UserProfile + Scenario type contracts', () => {
  it('UserProfile minimal shape', () => {
    const p: UserProfile = {
      id: 'pet-owner-casual',
      voice: 'first-person-casual',
      communication_style: 'direct, warm, plain-spoken',
      utterance_template: 'I want a {{deliverable}} for my {{subject}}',
    }
    expect(p.id).toBe('pet-owner-casual')
  })

  it('Scenario minimal shape', () => {
    const s: Scenario = {
      id: 'pets-site',
      profile_id: 'pet-owner-casual',
      goal_seed: { deliverable: 'website', subject: 'pets' },
    }
    expect(s.profile_id).toBe('pet-owner-casual')
  })
})
