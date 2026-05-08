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

import { unwrapJson, type LLMDispatch } from './extractor.js'
import type { GoalContract } from '../../../types/goal-contract.js'

const REQUIRED_FIELDS = [
  'situation', 'motivation', 'outcome', 'beneficiary',
  'hard_constraints', 'non_goals', 'acceptance_examples',
  'evidence_required', 'execution_preferences',
  'confidence', 'ambiguity_flags', 'clarification_required',
] as const

export async function validateAndRetry(
  prompt: string,
  llm: LLMDispatch,
  max_retries: number,
): Promise<GoalContract> {
  let last_error = ''
  for (let attempt = 0; attempt <= max_retries; attempt++) {
    const next = attempt === 0
      ? prompt
      : `${prompt}\n\nPREVIOUS ATTEMPT FAILED:\n${last_error}\n\nRetry. Output ONLY valid JSON matching the schema above.`
    const raw = await llm(next)
    try {
      const candidate = JSON.parse(unwrapJson(raw))
      validateContractShape(candidate)
      return candidate as GoalContract
    } catch (e) {
      last_error = e instanceof Error ? e.message : String(e)
    }
  }
  throw new Error(`extraction failed after ${max_retries + 1} attempts: ${last_error}`)
}

function validateContractShape(c: unknown): asserts c is GoalContract {
  if (typeof c !== 'object' || c === null) throw new Error('not an object')
  const obj = c as Record<string, unknown>
  for (const f of REQUIRED_FIELDS) {
    if (!(f in obj)) throw new Error(`missing required field: ${f}`)
  }
  if (typeof obj.confidence !== 'number') throw new Error('confidence must be number')
  if (typeof obj.clarification_required !== 'boolean') throw new Error('clarification_required must be boolean')
  for (const f of ['hard_constraints','non_goals','acceptance_examples','evidence_required','ambiguity_flags']) {
    if (!Array.isArray(obj[f])) throw new Error(`${f} must be array`)
  }
  if (typeof obj.execution_preferences !== 'object') throw new Error('execution_preferences must be object')
}
