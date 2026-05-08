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
import { type CutoverContract } from '../schemas/cutover-contract.js';
export interface CutoverValidationResult {
    readonly valid: boolean;
    readonly errors: ReadonlyArray<string>;
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
export declare function validateCutoverContract(contract: unknown): CutoverValidationResult;
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
export declare function isParseableDuration(input: string): boolean;
/**
 * Type-narrowing predicate. Convenience for callers.
 */
export declare function isValidatedCutoverContract(v: unknown): v is CutoverContract;
//# sourceMappingURL=cutover-validator.d.ts.map