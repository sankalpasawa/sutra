/**
 * CutoverValidator — v1.3.0 W6 (final wave production hardening).
 *
 * Validates the structural integrity of a CutoverContract beyond the zod
 * schema. Schema parse already catches missing fields / wrong types; this
 * validator catches semantic / structural defects:
 *
 *   1. source_engine === target_engine          → "no-op cutover" — refused
 *   2. behavior_invariants[] contains duplicates  → ambiguous gate semantics
 *   3. behavior_invariants[] contains empty/whitespace strings (post-trim)
 *   4. canary_window doesn't parse as a duration (PT-prefix ISO-8601, simple
 *      "Nd"/"Nh"/"Nm"/"Ns", or numeric seconds)
 *   5. rollback_gate is empty (post-trim) — but this is also caught by the
 *      schema's min(1); we double-check post-trim
 *
 * Per plan §6 + codex implicit advisory: APPLY-WITH-ROLLBACK is DEFERRED to
 * v1.x.1. This validator + the dryRunApplyCutover sibling cover the v1.3.0
 * surface — observe the contract, plan the mutations, but never mutate.
 */

import {
  CutoverContractSchema,
  type CutoverContract,
} from '../schemas/cutover-contract.js'

export interface CutoverValidationResult {
  readonly valid: boolean
  readonly errors: ReadonlyArray<string>
}

/**
 * Validate a CutoverContract for structural integrity. Returns
 * `{valid: true, errors: []}` for a fully-validated contract OR for the
 * `null` no-cutover case. Otherwise returns `{valid: false, errors: [...]}`.
 *
 * The validator is pure — no I/O, no side effects. Callers that need
 * cross-primitive validation (e.g. "source_engine exists in user-kit")
 * wrap this with their own checks.
 */
export function validateCutoverContract(
  contract: unknown,
): CutoverValidationResult {
  const errors: string[] = []

  // Schema parse first — catches missing fields, wrong types, empty strings
  // via .min(1).
  const parse = CutoverContractSchema.safeParse(contract)
  if (!parse.success) {
    for (const issue of parse.error.issues) {
      const path = issue.path.length > 0 ? issue.path.join('.') : '(root)'
      errors.push(`schema: ${path}: ${issue.message}`)
    }
    return { valid: false, errors }
  }

  // null = no cutover required; valid by definition.
  const c = parse.data
  if (c === null) {
    return { valid: true, errors: [] }
  }

  // (1) Source/target identity — refuse no-op cutover.
  if (c.source_engine === c.target_engine) {
    errors.push(
      `source_engine === target_engine ("${c.source_engine}") — cutover would be a no-op`,
    )
  }

  // (2) Duplicate invariants — each invariant predicate should be distinct
  //     so the gate semantics are unambiguous.
  const seenInvariants = new Set<string>()
  for (const inv of c.behavior_invariants) {
    const trimmed = inv.trim()
    // (3) Empty after trim
    if (trimmed.length === 0) {
      errors.push('behavior_invariants[]: empty/whitespace-only entry')
      continue
    }
    if (seenInvariants.has(trimmed)) {
      errors.push(
        `behavior_invariants[]: duplicate entry "${trimmed}" — each invariant must be unique`,
      )
    }
    seenInvariants.add(trimmed)
  }

  // (4) canary_window must parse as a recognized duration.
  if (!isParseableDuration(c.canary_window)) {
    errors.push(
      `canary_window: "${c.canary_window}" not a recognized duration — expected ISO-8601 "PT72H"/"P7D", short-form "7d"/"60s", or integer seconds`,
    )
  }

  // (5) rollback_gate post-trim non-empty (schema catches pre-trim).
  if (c.rollback_gate.trim().length === 0) {
    errors.push('rollback_gate: empty/whitespace-only')
  }

  return { valid: errors.length === 0, errors }
}

/**
 * Lightweight duration parser for the cutover canary_window field.
 *
 * Accepts:
 *   - ISO-8601 "PT<N>S" / "PT<N>M" / "PT<N>H" / "P<N>D"
 *   - Short-form "<N>s" / "<N>m" / "<N>h" / "<N>d"
 *   - Plain integer (seconds): "60", "3600"
 *
 * Returns true when the input parses to a positive duration; false otherwise.
 * Pure — no I/O.
 */
export function isParseableDuration(input: string): boolean {
  const s = input.trim()
  if (s.length === 0) return false
  // Plain integer
  if (/^\d+$/.test(s)) return Number(s) > 0
  // ISO-8601 PT/P forms
  const iso = /^P(?:T)?(\d+)([SMHD])$/i.exec(s)
  if (iso) return Number(iso[1]) > 0
  // Short form
  const short = /^(\d+)([smhd])$/.exec(s)
  if (short) return Number(short[1]) > 0
  return false
}

/**
 * Type-narrowing predicate. Convenience for callers.
 */
export function isValidatedCutoverContract(
  v: unknown,
): v is CutoverContract {
  const r = validateCutoverContract(v)
  return r.valid
}
