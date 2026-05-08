/**
 * Verifier orchestrator — AC §9.4 anchor.
 *
 * Known-good run with artifacts so all 4 tiers fire and exercise as expected.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */

import { describe, it, expect } from 'vitest'
import { verify } from '../../../../src/runtime/verifier-engine/contract-verifier/verifier.js'
import type { GoalContract } from '../../../../src/types/goal-contract.js'
import type { NativeRun } from '../../../../src/types/assertion-report.js'

const goodC: GoalContract = {
  situation: 'pet owner', motivation: 'showcase pets', outcome: 'public site',
  beneficiary: 'self',
  hard_constraints: [],
  non_goals: ['e-commerce checkout'],
  acceptance_examples: [{ given: 'site live', when: 'visitor opens', then: 'visitor sees pets' }],
  evidence_required: [{ stage: 'tech', field: '§Hosting' }],
  execution_preferences: {},
  confidence: 0.9, ambiguity_flags: [], clarification_required: false,
}

const goodRun: NativeRun = {
  run_id: 'r1', scenario_id: 'pets-site', events: [],
  artifacts: [
    { stage: 'vision',  path: 'vision.md',       sha256: 'x', content: 'A pet showcase site for pet owners. A visitor sees pets.\n\nMore detail.' },
    { stage: 'prd',     path: 'prd.md',          sha256: 'x', content: 'PRD for the pet showcase site. A visitor sees pets on the home page.\n\n(more)' },
    { stage: 'design',  path: 'design.md',       sha256: 'x', content: 'Design brief for pet showcase site. A visitor sees pets above the fold.\n\n(more)' },
    { stage: 'tech',    path: 'tech.md',         sha256: 'x', content: '## §Hosting\nDeploy to Vercel for the pet showcase site so a visitor sees pets quickly.\n\n(more)' },
  ],
}

describe('verify (orchestrator)', () => {
  it('AC §9.4: known-good run yields PASS verdict and exercises all 4 tiers', async () => {
    const judge = async () => JSON.stringify({
      'Outcome-Fidelity':    { score: 4, max: 5, evidence: 'ok' },
      'Constraint-Honor':    { score: 5, max: 5, evidence: 'ok' },
      'Cross-Stage-Drift':   { score: 5, max: 5, evidence: 'ok' },
      'Acceptance-Coverage': { score: 5, max: 5, evidence: 'ok' },
    })
    const r = await verify(goodC, goodRun, { judge })
    expect(r.verdict).toBe('PASS')
    expect(r.results.some(x => x.tier === 'schema')).toBe(true)
    expect(r.results.some(x => x.tier === 'artifact')).toBe(true)
    expect(r.results.some(x => x.tier === 'behavior')).toBe(true)
    expect(r.results.some(x => x.tier === 'rubric')).toBe(true)
    const rubricResults = r.results.filter(x => x.tier === 'rubric')
    expect(rubricResults).toHaveLength(4)
    expect(rubricResults.every(x => x.status === 'PASS')).toBe(true)
  })

  it('verdict FAIL when tier-1 fails', async () => {
    const judge = async () => JSON.stringify({
      'Outcome-Fidelity': { score: 5, max: 5, evidence: '' },
      'Constraint-Honor': { score: 5, max: 5, evidence: '' },
      'Cross-Stage-Drift': { score: 5, max: 5, evidence: '' },
      'Acceptance-Coverage': { score: 5, max: 5, evidence: '' },
    })
    const r = await verify({ ...goodC, confidence: 0.2 }, goodRun, { judge })
    expect(r.verdict).toBe('FAIL')
  })

  it('verdict FAIL when tier-2 non-goal violated', async () => {
    const judge = async () => JSON.stringify({
      'Outcome-Fidelity': { score: 5, max: 5, evidence: '' },
      'Constraint-Honor': { score: 5, max: 5, evidence: '' },
      'Cross-Stage-Drift': { score: 5, max: 5, evidence: '' },
      'Acceptance-Coverage': { score: 5, max: 5, evidence: '' },
    })
    const violatingRun: NativeRun = {
      ...goodRun,
      artifacts: [
        ...goodRun.artifacts.slice(0, 3),
        { stage: 'tech', path: 'tech.md', sha256: 'x', content: 'Add Stripe e-commerce checkout flow. Deploy via §Hosting plan.' },
      ],
    }
    const r = await verify(goodC, violatingRun, { judge })
    expect(r.verdict).toBe('FAIL')
  })
})
