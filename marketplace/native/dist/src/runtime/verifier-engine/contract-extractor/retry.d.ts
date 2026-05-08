/**
 * validateAndRetry — Instructor-pattern retry loop.
 *
 * On validation error, append the error message to the next prompt and re-ask.
 *
 * Industry borrow: Instructor (Jason Liu) —
 * https://python.useinstructor.com/learning/validation/retry_mechanisms/
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §6
 */
import { type LLMDispatch } from './extractor.js';
import type { GoalContract } from '../../../types/goal-contract.js';
export declare function validateAndRetry(prompt: string, llm: LLMDispatch, max_retries: number): Promise<GoalContract>;
//# sourceMappingURL=retry.d.ts.map