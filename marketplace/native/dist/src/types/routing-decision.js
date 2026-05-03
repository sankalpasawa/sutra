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
export {};
//# sourceMappingURL=routing-decision.js.map