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

import { buildExtractionPrompt } from './prompt.js'
import { validateAndRetry } from './retry.js'
import type { GoalContract } from '../../../types/goal-contract.js'

export type LLMDispatch = (prompt: string) => Promise<string>

export interface ExtractOptions {
  readonly max_retries?: number
}

export async function extract(
  utterance: string,
  llm: LLMDispatch,
  opts: ExtractOptions = {},
): Promise<GoalContract> {
  const prompt = buildExtractionPrompt(utterance)
  return validateAndRetry(prompt, llm, opts.max_retries ?? 3)
}

export function unwrapJson(raw: string): string {
  const t = raw.trim()
  const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fence) return fence[1].trim()
  const first = t.indexOf('{')
  const last = t.lastIndexOf('}')
  if (first >= 0 && last > first) return t.slice(first, last + 1)
  return t
}
