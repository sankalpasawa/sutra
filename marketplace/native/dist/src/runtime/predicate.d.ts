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
import type { Predicate, TriggerEventType } from '../types/trigger-spec.js';
import type { HSutraEvent } from '../types/h-sutra-event.js';
export interface PredicateContext {
    /** Founder's raw input text. May be derived from HSutraEvent.input_text. */
    readonly input_text?: string;
    /** The event_type from the TriggerSpec being evaluated against. */
    readonly event_type: TriggerEventType;
    /** Optional H-Sutra event (when routing from a CC turn). */
    readonly hsutra?: HSutraEvent;
}
export interface EvaluationResult {
    readonly matched: boolean;
    /** Optional human-readable reason when matched=false (for audit). */
    readonly reason?: string;
}
export declare function evaluate(predicate: Predicate, context: PredicateContext): EvaluationResult;
//# sourceMappingURL=predicate.d.ts.map