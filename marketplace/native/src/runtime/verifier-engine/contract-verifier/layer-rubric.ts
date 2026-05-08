/**
 * Tier-4 rubric — LLM-judge backstop, calibrated only.
 *
 * Industry borrow: G-Eval (Microsoft) two-step pattern — generate
 * evaluation_steps from criteria via CoT FIRST, then form-fill scores
 * with evidence-before-score JSON.
 *
 * Industry borrow: Agentic Rubrics for SWE Agents (arXiv 2601.04171) —
 * 4 axes scored independently; no aggregate.
 *
 * Reserved as CALIBRATED BACKSTOP only — never sole verdict.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */

import type { GoalContract } from '../../../types/goal-contract.js'
import type { AssertionResult, AssertionAxis, NativeRun } from '../../../types/assertion-report.js'

const AXES: readonly AssertionAxis[] = [
  'Outcome-Fidelity', 'Constraint-Honor', 'Cross-Stage-Drift', 'Acceptance-Coverage',
] as const

const PASS_RATIO = 0.6

export type JudgeDispatch = (prompt: string) => Promise<string>

interface AxisScore { score: number; max: number; evidence: string }

export async function runTier4Rubric(
  contract: GoalContract,
  run: NativeRun,
  judge: JudgeDispatch,
): Promise<AssertionResult[]> {
  let scores: Record<string, AxisScore>
  try {
    scores = JSON.parse(unwrap(await judge(buildRubricPrompt(contract, run))))
  } catch (e) {
    return AXES.map(axis => ({
      id: `tier-4/${axis.toLowerCase()}`,
      tier: 'rubric' as const, axis,
      status: 'SKIPPED' as const,
      message: `judge unavailable: ${e instanceof Error ? e.message : String(e)}`,
    }))
  }
  return AXES.map(axis => {
    const s = scores[axis] ?? { score: 0, max: 5, evidence: 'no score returned' }
    const ratio = s.max === 0 ? 0 : s.score / s.max
    return {
      id: `tier-4/${axis.toLowerCase()}`,
      tier: 'rubric' as const, axis,
      status: ratio >= PASS_RATIO ? ('PASS' as const) : ('FAIL' as const),
      message: `${axis} ${s.score}/${s.max} — ${s.evidence}`,
      evidence: s.evidence,
    }
  })
}

function buildRubricPrompt(contract: GoalContract, run: NativeRun): string {
  const artifacts = run.artifacts.map(a => `[${a.stage}.md]\n${a.content}`).join('\n\n')
  return `
Score the produced artifacts against the GoalContract on 4 axes.
Output JSON only:
{
  "Outcome-Fidelity":    { "score": <0..5>, "max": 5, "evidence": "<...>" },
  "Constraint-Honor":    { "score": <0..5>, "max": 5, "evidence": "<...>" },
  "Cross-Stage-Drift":   { "score": <0..5>, "max": 5, "evidence": "<...>" },
  "Acceptance-Coverage": { "score": <0..5>, "max": 5, "evidence": "<...>" }
}

For each axis: decompose criterion into 2-3 sub-checks (G-Eval two-step),
cite evidence from artifacts BEFORE scoring. 5 = fully honored; 0 = missed.

GoalContract:
${JSON.stringify(contract, null, 2)}

Artifacts:
${artifacts}
`.trim()
}

function unwrap(raw: string): string {
  const t = raw.trim()
  const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/i)
  return fence ? fence[1].trim() : t
}
