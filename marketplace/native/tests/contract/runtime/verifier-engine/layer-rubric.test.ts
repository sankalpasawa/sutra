import { describe, it, expect } from 'vitest'
import { runTier4Rubric, type JudgeDispatch } from '../../../../src/runtime/verifier-engine/contract-verifier/layer-rubric.js'
import type { GoalContract } from '../../../../src/types/goal-contract.js'
import type { NativeRun } from '../../../../src/types/assertion-report.js'

const c: GoalContract = {
  situation: 's', motivation: 'm', outcome: 'pet showcase', beneficiary: 'self',
  hard_constraints: [], non_goals: [], acceptance_examples: [],
  evidence_required: [], execution_preferences: {},
  confidence: 0.9, ambiguity_flags: [], clarification_required: false,
}
const run: NativeRun = { run_id: 'r', scenario_id: 's', events: [], artifacts: [] }

describe('runTier4Rubric (G-Eval)', () => {
  it('returns one result per axis, all PASS at >= threshold', async () => {
    const j: JudgeDispatch = async () => JSON.stringify({
      'Outcome-Fidelity':    { score: 4, max: 5, evidence: '' },
      'Constraint-Honor':    { score: 5, max: 5, evidence: '' },
      'Cross-Stage-Drift':   { score: 5, max: 5, evidence: '' },
      'Acceptance-Coverage': { score: 5, max: 5, evidence: '' },
    })
    const r = await runTier4Rubric(c, run, j)
    expect(r).toHaveLength(4)
    for (const x of r) expect(x.status).toBe('PASS')
  })

  it('FAIL when an axis below threshold', async () => {
    const j: JudgeDispatch = async () => JSON.stringify({
      'Outcome-Fidelity':    { score: 1, max: 5, evidence: 'lost outcome' },
      'Constraint-Honor':    { score: 5, max: 5, evidence: '' },
      'Cross-Stage-Drift':   { score: 5, max: 5, evidence: '' },
      'Acceptance-Coverage': { score: 5, max: 5, evidence: '' },
    })
    const r = await runTier4Rubric(c, run, j)
    expect(r.find(x => x.axis === 'Outcome-Fidelity')!.status).toBe('FAIL')
  })

  it('SKIPPED when judge errors', async () => {
    const j: JudgeDispatch = async () => { throw new Error('llm down') }
    const r = await runTier4Rubric(c, run, j)
    for (const x of r) expect(x.status).toBe('SKIPPED')
  })
})
