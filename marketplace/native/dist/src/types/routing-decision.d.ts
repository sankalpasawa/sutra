/**
 * RoutingDecision — audit record for every Router.route() call.
 *
 * Per softened I-NPD-1: every routing decision (deterministic-match OR
 * LLM-fallback OR no-match) gets recorded so replay reproduces the same
 * dispatch graph. LLM-fallback decisions include prompt_hash so the LLM
 * call itself is replayable bit-identically.
 *
 * Append-only to holding/native/audit/<date>.jsonl in production. Tests
 * collect the in-memory sequence via Router.getDecisionLog().
 */
export type RoutingMode = 
/** A deterministic predicate matched a registered TriggerSpec. */
'exact'
/** No predicate matched; LLM fallback was invoked + returned a workflow_id. */
 | 'llm-fallback'
/** No predicate matched + LLM fallback disabled or returned null. */
 | 'no-match';
export interface PredicateAttempt {
    readonly trigger_id: string;
    readonly matched: boolean;
    /** When matched=false, optional one-line reason for the audit. */
    readonly reason?: string;
}
export interface RoutingDecision {
    /** Correlation key (matches HSutraEvent.turn_id when applicable). */
    readonly turn_id: string | null;
    /** When the decision was made (ms since epoch). */
    readonly ts_ms: number;
    /** Outcome category. */
    readonly mode: RoutingMode;
    /** Workflow to dispatch (null when mode='no-match'). */
    readonly workflow_id: string | null;
    /** Which TriggerSpec matched (null when mode='no-match' or 'llm-fallback' without trigger). */
    readonly trigger_id: string | null;
    /** Per-trigger evaluation trace (in registration order). */
    readonly attempts: ReadonlyArray<PredicateAttempt>;
    /** Set only when mode='llm-fallback' — sha256(prompt) for replay. */
    readonly prompt_hash?: string;
    /** Set only when mode='llm-fallback' — model identifier. */
    readonly llm_model?: string;
}
//# sourceMappingURL=routing-decision.d.ts.map