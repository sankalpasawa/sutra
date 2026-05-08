/**
 * verify — orchestrate the 4-tier verifier stack.
 *
 * Produces AssertionReport with results from each active tier. Verdict FAIL
 * if any tier-1/2/3 assertion FAILs; tier-4 is calibrated backstop.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */

import type { GoalContract } from '../../../types/goal-contract.js'
import type { AssertionResult, AssertionReport, NativeRun, Verdict } from '../../../types/assertion-report.js'
import { runTier1Schema } from './layer-schema.js'
import { runTier2Artifact } from './layer-artifact.js'
import { runTier3Behavior } from './layer-behavior.js'
import { runTier4Rubric, type JudgeDispatch } from './layer-rubric.js'

export type { NativeRun } from '../../../types/assertion-report.js'

export interface VerifyOptions {
  readonly judge: JudgeDispatch
}

export async function verify(
  contract: GoalContract,
  run: NativeRun,
  opts: VerifyOptions,
): Promise<AssertionReport> {
  const t0 = Date.now()
  const results: AssertionResult[] = [
    ...runTier1Schema(contract),
    ...(run.artifacts.length > 0 ? runTier2Artifact(contract, run) : []),
    ...runTier3Behavior(),
    ...(await runTier4Rubric(contract, run, opts.judge)),
  ]
  const summary = {
    total: results.length,
    pass: results.filter(r => r.status === 'PASS').length,
    fail: results.filter(r => r.status === 'FAIL').length,
    skipped: results.filter(r => r.status === 'SKIPPED').length,
  }
  const hardFail = results.some(r =>
    (r.tier === 'schema' || r.tier === 'artifact' || r.tier === 'behavior') && r.status === 'FAIL'
  )
  const verdict: Verdict = hardFail ? 'FAIL' : (summary.fail > 0 ? 'PARTIAL' : 'PASS')
  return {
    run_id: run.run_id, scenario_id: run.scenario_id,
    duration_ms: Date.now() - t0,
    results, summary, verdict,
  }
}
