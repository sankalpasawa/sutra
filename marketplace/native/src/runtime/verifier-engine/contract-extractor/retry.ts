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
  if (
    typeof obj.execution_preferences !== 'object' ||
    obj.execution_preferences === null ||
    Array.isArray(obj.execution_preferences)
  ) {
    throw new Error('execution_preferences must be object')
  }

  // Deep validation (codex P1 #2 fold 2026-05-08).
  // String fields must be non-null strings.
  for (const f of ['situation', 'motivation', 'outcome', 'beneficiary'] as const) {
    if (typeof obj[f] !== 'string') throw new Error(`${f} must be string`)
  }

  // confidence must be in [0, 1] and finite.
  if (
    typeof obj.confidence !== 'number' ||
    obj.confidence < 0 ||
    obj.confidence > 1 ||
    !Number.isFinite(obj.confidence)
  ) {
    throw new Error('confidence must be number in [0, 1]')
  }

  // acceptance_examples[i] shape: { given, when, then } all strings.
  for (const [i, ex] of (obj.acceptance_examples as unknown[]).entries()) {
    if (typeof ex !== 'object' || ex === null) throw new Error(`acceptance_examples[${i}] must be object`)
    const e = ex as Record<string, unknown>
    for (const k of ['given', 'when', 'then'] as const) {
      if (typeof e[k] !== 'string') throw new Error(`acceptance_examples[${i}].${k} must be string`)
    }
  }

  // evidence_required[i] shape: { stage, field } both strings.
  for (const [i, ev] of (obj.evidence_required as unknown[]).entries()) {
    if (typeof ev !== 'object' || ev === null) throw new Error(`evidence_required[${i}] must be object`)
    const e = ev as Record<string, unknown>
    for (const k of ['stage', 'field'] as const) {
      if (typeof e[k] !== 'string') throw new Error(`evidence_required[${i}].${k} must be string`)
    }
  }

  // ambiguity_flags elements must be strings.
  for (const [i, f] of (obj.ambiguity_flags as unknown[]).entries()) {
    if (typeof f !== 'string') throw new Error(`ambiguity_flags[${i}] must be string`)
  }
}
