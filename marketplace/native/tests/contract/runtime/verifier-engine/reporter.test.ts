import { describe, it, expect } from 'vitest'
import { formatReport, formatTranscript } from '../../../../src/runtime/verifier-engine/contract-reporter/reporter.js'
import type { AssertionReport, NativeRun } from '../../../../src/types/assertion-report.js'

const report: AssertionReport = {
  run_id: 'r1', scenario_id: 'pets-site', duration_ms: 142000,
  results: [
    { id: 'tier-1/required-fields', tier: 'schema', axis: 'Outcome-Fidelity', status: 'PASS', message: 'all populated' },
    { id: 'tier-2/non-goal/e-commerce', tier: 'artifact', axis: 'Constraint-Honor', status: 'FAIL', message: 'violated' },
  ],
  summary: { total: 2, pass: 1, fail: 1, skipped: 0 },
  verdict: 'FAIL',
}

describe('reporter', () => {
  it('formatReport produces ASCII table with axis tags + verdict', () => {
    const out = formatReport(report)
    expect(out).toContain('tier-1/required-fields')
    expect(out).toContain('Constraint-Honor')
    expect(out).toContain('PASS')
    expect(out).toContain('FAIL')
    expect(out).toContain('VERDICT: FAIL')
  })

  it('formatTranscript chronologically interleaves USER + NATIVE', () => {
    const run: NativeRun = {
      run_id: 'r1', scenario_id: 'pets-site',
      events: [
        { type: 'utterance', ts: 1000, payload: 'I want a website for my pets' },
        { type: 'trigger_fired', ts: 1100 },
        { type: 'artifact_emitted', ts: 5000, payload: { stage: 'vision', path: 'vision.md' } },
      ],
      artifacts: [],
    }
    const out = formatTranscript('I want a website for my pets', run)
    expect(out).toContain('USER')
    expect(out).toContain('NATIVE')
    expect(out).toContain('I want a website for my pets')
  })
})
