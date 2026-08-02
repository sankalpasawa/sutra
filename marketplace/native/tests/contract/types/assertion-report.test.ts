import { describe, it, expect } from 'vitest'
import type {
  AssertionResult, AssertionReport, AssertionAxis, NativeRun,
} from '../../../src/types/assertion-report.js'

describe('AssertionReport type contract', () => {
  it('AssertionResult shape', () => {
    const r: AssertionResult = {
      id: 'tier-2/hard-constraint/no-ads',
      tier: 'artifact', axis: 'Constraint-Honor',
      status: 'PASS', message: 'no ads found',
    }
    expect(r.status).toBe('PASS')
  })

  it('AssertionReport aggregates per tier', () => {
    const r: AssertionReport = {
      run_id: 'r1', scenario_id: 'pets-site', duration_ms: 142000,
      results: [], summary: { total: 0, pass: 0, fail: 0, skipped: 0 },
      verdict: 'PASS',
    }
    expect(r.verdict).toBe('PASS')
  })

  it('axis enum lists all 4 G-Eval-style rubric axes', () => {
    const axes: AssertionAxis[] = [
      'Outcome-Fidelity', 'Constraint-Honor', 'Cross-Stage-Drift', 'Acceptance-Coverage',
    ]
    expect(axes).toHaveLength(4)
  })

  it('NativeRun shape', () => {
    const run: NativeRun = {
      run_id: 'r', scenario_id: 's',
      events: [{ type: 'utterance', ts: 0 }],
      artifacts: [{ stage: 'vision', path: 'vision.md', content: '', sha256: 'x' }],
    }
    expect(run.artifacts).toHaveLength(1)
  })
})
