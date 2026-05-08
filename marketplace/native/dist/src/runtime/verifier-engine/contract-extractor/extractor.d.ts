/**
 * extract — capture a GoalContract from an utterance.
 *
 * Pure relative to its llm callback. Tests inject a mock; production wires
 * to Native's existing host_llm_dispatch (claude --bare / codex exec) via
 * lite-executor's hostLLMActivity.
 *
 * Industry borrow: Instructor (Jason Liu) — validation-error-as-feedback
 * retry. v1 caps retries at 3.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §4 + §6
 */
import type { GoalContract } from '../../../types/goal-contract.js';
export type LLMDispatch = (prompt: string) => Promise<string>;
export interface ExtractOptions {
    readonly max_retries?: number;
}
export declare function extract(utterance: string, llm: LLMDispatch, opts?: ExtractOptions): Promise<GoalContract>;
export declare function unwrapJson(raw: string): string;
//# sourceMappingURL=extractor.d.ts.map