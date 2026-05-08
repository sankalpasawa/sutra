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
import type { GoalContract } from '../../../types/goal-contract.js';
import type { AssertionResult, NativeRun } from '../../../types/assertion-report.js';
export type JudgeDispatch = (prompt: string) => Promise<string>;
export declare function runTier4Rubric(contract: GoalContract, run: NativeRun, judge: JudgeDispatch): Promise<AssertionResult[]>;
//# sourceMappingURL=layer-rubric.d.ts.map