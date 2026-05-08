/**
 * pnc-predicate — v1.3.0 Wave 5 PNC (Pre/Post/Commitment) predicate adapter.
 *
 * Workflow.preconditions / Workflow.postconditions are free-form strings on
 * the primitive (legacy free-form atoms like "is_morning_window AND
 * no_pulse_today" — see starter-kit). For Wave 5 admission gating we layer a
 * parsed JSON predicate language ON TOP of that string slot:
 *
 *   - When the string parses as JSON AND the JSON validates as a PNCPredicate,
 *     the executor evaluates it deterministically against a frozen context.
 *   - When the string does NOT parse / does NOT validate, we treat the
 *     workflow as having no parsed PNC gate and skip the admission check
 *     (legacy back-compat — the existing free-form strings stay valid).
 *
 * Codex W5 BLOCKER 2 fold (2026-05-04): we deliberately do NOT extend
 * `Predicate` in `src/types/trigger-spec.ts` and we do NOT graft into
 * `predicate.ts`'s `evaluate()` function. The TriggerSpec routing predicate
 * engine is fed by HSutra context (cell/verb/direction/risk/event_type +
 * input_text); the PNC gate is fed by an arbitrary key-value `context`
 * snapshot the caller assembles (e.g. `{ time_of_day: 'morning',
 * pulse_today: false }`). Different inputs, different evaluator surface area —
 * but the SHAPE (and/or/not + atom leaf) mirrors `predicate.ts`'s
 * combinator pattern so the cognitive footprint is small.
 *
 * Codex W5 advisory A: minimal grammar — AND / OR / NOT / Atom only.
 * No numeric or temporal operators in the SYNTAX. Time-shaped atoms like
 * `weekly_window` or `is_morning_window` are atom NAMES looked up in the
 * registry; the registry callable computes the boolean from window markers
 * placed in the frozen context by upstream code (NativeEngine, scheduler).
 *
 * Codex W5 advisory B: registry-based atoms via PredicateRegistry. Reuses
 * predicate.ts's combinator shape (and/or/not over leaves; algebraic
 * identities for empty and/or).
 *
 * Codex W5 advisory E: predicate determinism — predicate functions receive
 * a frozen evaluation context snapshot; no Date.now(), no random, no I/O.
 * Time-atoms get window markers placed in the context by callers.
 */
/**
 * The PNCPredicate AST. Discriminated union mirroring predicate.ts's
 * combinator pattern (`and` / `or` / `not`) but with a SINGLE leaf shape
 * (`atom`) that delegates to the registry for evaluation.
 */
export type PNCPredicate = {
    readonly type: 'and';
    readonly clauses: ReadonlyArray<PNCPredicate>;
} | {
    readonly type: 'or';
    readonly clauses: ReadonlyArray<PNCPredicate>;
} | {
    readonly type: 'not';
    readonly clause: PNCPredicate;
} | {
    readonly type: 'atom';
    readonly name: string;
};
/**
 * A registered atom evaluator. Receives a FROZEN context snapshot and returns
 * a boolean. MUST be deterministic — no Date.now(), no random, no I/O.
 *
 * Window markers (e.g. `time_of_day`, `iso_week`) belong in the context, not
 * in the function. The caller (NativeEngine / scheduler) is responsible for
 * placing them before invoking the executor.
 */
export type PredicateAtomFn = (ctx: Readonly<Record<string, unknown>>) => boolean;
/**
 * PredicateRegistry — name → evaluator. Lookup miss is a hard failure
 * surfaced as `precondition_failed:atom_not_registered:<name>` (codex W5
 * advisory F: registry lookup miss is a deterministic test surface).
 */
export type PredicateRegistry = ReadonlyMap<string, PredicateAtomFn>;
export interface PNCParseResult {
    readonly ok: boolean;
    readonly predicate?: PNCPredicate;
    readonly error?: string;
}
/**
 * Parse a PNC string into a PNCPredicate. Accepted forms:
 *
 *   1. Empty / whitespace string ⇒ ok=false (caller treats as legacy).
 *   2. JSON-shaped PNCPredicate (`{"type":"atom","name":"always_true"}`,
 *      `{"type":"and","clauses":[...]}`, etc.) ⇒ ok=true with parsed predicate.
 *   3. Anything else (legacy free-form atoms like "is_morning_window AND
 *      no_pulse_today") ⇒ ok=false. Caller treats as legacy / no PNC gate.
 *
 * Validation is structural (discriminator + required fields). Atom NAME
 * validity (existence in the registry) is checked at evaluate-time, not parse
 * time, so a workflow can declare an atom that the host registers later.
 */
export declare function parsePNC(expr: string): PNCParseResult;
/**
 * Structural type guard for PNCPredicate. Validates discriminator + required
 * fields recursively (and/or clauses must each be valid; not.clause must be
 * valid). Atom validation = name is non-empty string.
 */
export declare function isPNCPredicate(value: unknown): value is PNCPredicate;
export interface PNCEvaluationResult {
    readonly verdict: boolean;
    /** When verdict=false, a stable reason for `precondition_failed:<reason>`. */
    readonly reason?: string;
}
/**
 * Evaluate a PNCPredicate against a frozen context using a registry of atom
 * evaluators. Deterministic — no Date.now(), no random, no I/O.
 *
 * Algebraic identities (mirrors predicate.ts):
 *   - empty AND ⇒ true
 *   - empty OR  ⇒ false
 *
 * Atom miss ⇒ verdict=false, reason='atom_not_registered:<name>' (codex W5
 * advisory F: registry lookup miss is a deterministic test surface — every
 * unknown atom must be auditable, never silently true).
 *
 * Atom evaluator throw ⇒ verdict=false, reason='atom_threw:<name>:<msg>'.
 * (Atoms must be deterministic; if they throw, the gate fails closed.)
 */
export declare function evaluatePNC(predicate: PNCPredicate, ctx: Readonly<Record<string, unknown>>, registry: PredicateRegistry): PNCEvaluationResult;
/**
 * Built-in predicate registry that always-true / always-false atoms come from.
 * Tests + starter workflows can compose against this baseline; production
 * registries layer custom atoms (`is_morning_window`, `weekly_window`, etc.)
 * on top via Map composition.
 */
export declare const BASELINE_PREDICATE_REGISTRY: PredicateRegistry;
//# sourceMappingURL=pnc-predicate.d.ts.map