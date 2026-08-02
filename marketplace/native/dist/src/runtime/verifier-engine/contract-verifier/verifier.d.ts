/**
 * verify — orchestrate the 4-tier verifier stack.
 *
 * Produces AssertionReport with results from each active tier. Verdict FAIL
 * if any tier-1/2/3 assertion FAILs; tier-4 is calibrated backstop.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */
import type { GoalContract } from '../../../types/goal-contract.js';
import type { AssertionReport, NativeRun } from '../../../types/assertion-report.js';
import { type JudgeDispatch } from './layer-rubric.js';
export type { NativeRun } from '../../../types/assertion-report.js';
export interface VerifyOptions {
    readonly judge: JudgeDispatch;
}
export declare function verify(contract: GoalContract, run: NativeRun, opts: VerifyOptions): Promise<AssertionReport>;
//# sourceMappingURL=verifier.d.ts.map