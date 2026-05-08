import { describe, it, expect } from 'vitest'
import { VerifierEngine } from '../../../../src/runtime/verifier-engine/index.js'

describe('VerifierEngine end-to-end with mocks', () => {
  it('extract -> verify -> format produces transcript + report strings', async () => {
    const validJson = JSON.stringify({
      situation: 's', motivation: 'm', outcome: 'o', beneficiary: 'self',
      hard_constraints: [], non_goals: [], acceptance_examples: [], evidence_required: [],
      execution_preferences: {}, confidence: 0.85, ambiguity_flags: [], clarification_required: false,
    })
    const judge = async () => JSON.stringify({
      'Outcome-Fidelity': { score: 4, max: 5, evidence: 'ok' },
      'Constraint-Honor': { score: 5, max: 5, evidence: 'ok' },
      'Cross-Stage-Drift': { score: 5, max: 5, evidence: 'ok' },
      'Acceptance-Coverage': { score: 5, max: 5, evidence: 'ok' },
    })
    const engine = new VerifierEngine({ llm: async () => validJson, judge })

    const c = await engine.extract('I want a website for my pets')
    expect(c.beneficiary).toBe('self')

    const run = { run_id: 'r', scenario_id: 'pets-site', events: [], artifacts: [] }
    const report = await engine.verify(c, run)
    expect(report.verdict).toBe('PASS')

    const out = engine.format(report, 'I want a website for my pets', run)
    expect(out.transcript).toContain('I want a website for my pets')
    expect(out.report).toContain('VERDICT: PASS')
  })
})
