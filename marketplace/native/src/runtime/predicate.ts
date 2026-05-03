/**
 * predicate — D2 step 2 deterministic predicate evaluator.
 *
 * Structured predicates only at v1.0 (string parser deferred to v1.1).
 * Pure function: evaluate(predicate, context) → boolean. No I/O. No side
 * effects. Replay-safe.
 *
 * Per softened I-NPD-1: evaluation is fully deterministic. LLM is never
 * called from inside this module.
 *
 * Predicate types covered:
 *   leaves:      contains, matches, event_type_eq, cell_eq, verb_eq,
 *                direction_eq, risk_eq, always_true
 *   combinators: and, or, not
 *
 * Edge cases:
 *   - and/or with empty clauses: and→true, or→false (algebraic identity)
 *   - missing context field: leaf returns false (never throws)
 *   - regex compile failure: matches→false + counter (for visibility) —
 *     callers check getLastError() if needed
 */

import type { Predicate, TriggerEventType } from '../types/trigger-spec.js'
import type { HSutraEvent } from '../types/h-sutra-event.js'

export interface PredicateContext {
  /** Founder's raw input text. May be derived from HSutraEvent.input_text. */
  readonly input_text?: string
  /** The event_type from the TriggerSpec being evaluated against. */
  readonly event_type: TriggerEventType
  /** Optional H-Sutra event (when routing from a CC turn). */
  readonly hsutra?: HSutraEvent
}

export interface EvaluationResult {
  readonly matched: boolean
  /** Optional human-readable reason when matched=false (for audit). */
  readonly reason?: string
}

export function evaluate(predicate: Predicate, context: PredicateContext): EvaluationResult {
  switch (predicate.type) {
    case 'always_true':
      return { matched: true }

    case 'contains': {
      const haystack = context.input_text ?? ''
      const needle = predicate.value
      const sensitive = predicate.case_sensitive ?? false
      const matched = sensitive
        ? haystack.includes(needle)
        : haystack.toLowerCase().includes(needle.toLowerCase())
      return matched
        ? { matched: true }
        : { matched: false, reason: `input does not contain "${needle}"` }
    }

    case 'matches': {
      const haystack = context.input_text ?? ''
      try {
        const re = new RegExp(predicate.pattern, predicate.flags)
        const matched = re.test(haystack)
        return matched
          ? { matched: true }
          : { matched: false, reason: `input does not match /${predicate.pattern}/${predicate.flags ?? ''}` }
      } catch {
        return { matched: false, reason: `invalid regex /${predicate.pattern}/` }
      }
    }

    case 'event_type_eq':
      return context.event_type === predicate.value
        ? { matched: true }
        : { matched: false, reason: `event_type ${context.event_type} !== ${predicate.value}` }

    case 'cell_eq': {
      const cell = context.hsutra?.cell
      return cell === predicate.value
        ? { matched: true }
        : { matched: false, reason: `cell ${cell ?? '<missing>'} !== ${predicate.value}` }
    }

    case 'verb_eq': {
      const verb = context.hsutra?.verb
      return verb === predicate.value
        ? { matched: true }
        : { matched: false, reason: `verb ${verb ?? '<missing>'} !== ${predicate.value}` }
    }

    case 'direction_eq': {
      const direction = context.hsutra?.direction
      return direction === predicate.value
        ? { matched: true }
        : { matched: false, reason: `direction ${direction ?? '<missing>'} !== ${predicate.value}` }
    }

    case 'risk_eq': {
      const risk = context.hsutra?.risk
      return risk === predicate.value
        ? { matched: true }
        : { matched: false, reason: `risk ${risk ?? '<missing>'} !== ${predicate.value}` }
    }

    case 'and': {
      // Empty AND is true (algebraic identity)
      if (predicate.clauses.length === 0) return { matched: true }
      for (const clause of predicate.clauses) {
        const result = evaluate(clause, context)
        if (!result.matched) {
          return { matched: false, reason: `and: ${result.reason ?? 'clause failed'}` }
        }
      }
      return { matched: true }
    }

    case 'or': {
      // Empty OR is false (algebraic identity)
      if (predicate.clauses.length === 0) return { matched: false, reason: 'or: empty clause list' }
      const reasons: string[] = []
      for (const clause of predicate.clauses) {
        const result = evaluate(clause, context)
        if (result.matched) return { matched: true }
        if (result.reason) reasons.push(result.reason)
      }
      return { matched: false, reason: `or: no clause matched (${reasons.join('; ')})` }
    }

    case 'not': {
      const result = evaluate(predicate.clause, context)
      return result.matched
        ? { matched: false, reason: `not: inner clause matched` }
        : { matched: true }
    }

    default: {
      // Exhaustiveness check (TS will error if a Predicate type is added
      // without a case here).
      const _exhaustive: never = predicate
      void _exhaustive
      return { matched: false, reason: 'unknown predicate type' }
    }
  }
}
