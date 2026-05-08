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
const AXES = [
    'Outcome-Fidelity', 'Constraint-Honor', 'Cross-Stage-Drift', 'Acceptance-Coverage',
];
const PASS_RATIO = 0.6;
export async function runTier4Rubric(contract, run, judge) {
    let scores;
    try {
        scores = JSON.parse(unwrap(await judge(buildRubricPrompt(contract, run))));
    }
    catch (e) {
        return AXES.map(axis => ({
            id: `tier-4/${axis.toLowerCase()}`,
            tier: 'rubric', axis,
            status: 'SKIPPED',
            message: `judge unavailable: ${e instanceof Error ? e.message : String(e)}`,
        }));
    }
    return AXES.map(axis => {
        const s = scores[axis] ?? { score: 0, max: 5, evidence: 'no score returned' };
        const ratio = s.max === 0 ? 0 : s.score / s.max;
        return {
            id: `tier-4/${axis.toLowerCase()}`,
            tier: 'rubric', axis,
            status: ratio >= PASS_RATIO ? 'PASS' : 'FAIL',
            message: `${axis} ${s.score}/${s.max} — ${s.evidence}`,
            evidence: s.evidence,
        };
    });
}
function buildRubricPrompt(contract, run) {
    const artifacts = run.artifacts.map(a => `[${a.stage}.md]\n${a.content}`).join('\n\n');
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
`.trim();
}
function unwrap(raw) {
    const t = raw.trim();
    const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/i);
    return fence ? fence[1].trim() : t;
}
//# sourceMappingURL=layer-rubric.js.map