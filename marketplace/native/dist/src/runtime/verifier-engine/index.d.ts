/**
 * VerifierEngine — top-level orchestrator. Wires extractor + verifier +
 * reporter. Constructor takes injectable LLM dispatch + judge dispatch
 * for testability and reuse across Sutra surfaces.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §4
 */
import type { GoalContract } from '../../types/goal-contract.js';
import type { AssertionReport, NativeRun } from '../../types/assertion-report.js';
import { type LLMDispatch } from './contract-extractor/extractor.js';
import { type JudgeDispatch } from './contract-verifier/layer-rubric.js';
export interface VerifierEngineConfig {
    readonly llm: LLMDispatch;
    readonly judge: JudgeDispatch;
    readonly max_extract_retries?: number;
}
export declare class VerifierEngine {
    private readonly cfg;
    constructor(cfg: VerifierEngineConfig);
    extract(utterance: string): Promise<GoalContract>;
    verify(contract: GoalContract, run: NativeRun): Promise<AssertionReport>;
    format(report: AssertionReport, utterance: string, run: NativeRun): {
        transcript: string;
        report: string;
    };
}
export type { GoalContract } from '../../types/goal-contract.js';
export type { AssertionReport, AssertionResult, NativeRun } from '../../types/assertion-report.js';
export type { UserProfile, Scenario } from '../../types/user-profile.js';
export type { LLMDispatch, JudgeDispatch };
export { generateUtterance } from './user-simulator/generate-utterance.js';
//# sourceMappingURL=index.d.ts.map