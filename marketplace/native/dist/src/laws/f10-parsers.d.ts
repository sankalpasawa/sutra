/**
 * F-10 typed parsers — M5 Group K (T-052).
 *
 * Parser-bound representations for routing/gating fields whose schema-level
 * type is "string" but whose value DECIDES which branch executes. M5 binds
 * 2 fields per codex P2.6 (D-NS-13 default flipped to (b) 2026-04-29):
 *
 *   1. Workflow.preconditions  — boolean expression
 *   2. Workflow.failure_policy — 5-enum or structured policy descriptor
 *
 * Bound at M7 Group W (T-095):
 *   - TriggerSpec.pattern                 — V2 enum (preprocessor / observer /
 *                                          gate / fan_out / negotiation).
 *
 * Deferred to v1.x (per codex M7 P1.3):
 *   - Charter.obligations[i].mechanization (Constraint schema doesn't expose
 *                                          this typed field today)
 *
 * Both parsers reject English-only prose (the F-10 violation) and accept
 * structured forms. Parser failures throw a typed `ParseError`; success
 * returns a typed AST.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group K T-052
 *  - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §3 F-10
 *  - .enforcement/codex-reviews/2026-04-29-m5-plan-pre-dispatch.md P2.6
 */
import type { StepFailureAction } from '../types/index.js';
/**
 * Thrown by both parsers when the input does not satisfy the formal grammar.
 * Carries a `field` tag so call sites can route different rejections to
 * different remediation paths.
 */
export declare class F10ParseError extends Error {
    readonly field: 'Workflow.preconditions' | 'Workflow.failure_policy';
    readonly input: string;
    constructor(field: 'Workflow.preconditions' | 'Workflow.failure_policy', input: string, message: string);
}
/**
 * Boolean expression AST. Structural; intentionally narrow.
 *
 *   Expr := Or
 *   Or   := And ('||' And)*
 *   And  := Unary ('&&' Unary)*
 *   Unary:= '!' Unary | Atom
 *   Atom := '(' Expr ')' | Comparison | Identifier
 *   Comparison := Identifier (('==' | '!=' | '<=' | '>=' | '<' | '>') Literal)?
 *   Identifier := [a-zA-Z_][a-zA-Z0-9_.]*
 *   Literal    := SingleQuotedString | Number | 'null' | 'true' | 'false'
 */
export type ParsedPreconditionExpr = {
    kind: 'identifier';
    name: string;
} | {
    kind: 'comparison';
    field: string;
    op: '==' | '!=' | '<=' | '>=' | '<' | '>';
    value: string | number | boolean | null;
} | {
    kind: 'and';
    left: ParsedPreconditionExpr;
    right: ParsedPreconditionExpr;
} | {
    kind: 'or';
    left: ParsedPreconditionExpr;
    right: ParsedPreconditionExpr;
} | {
    kind: 'not';
    expr: ParsedPreconditionExpr;
};
/**
 * Parse a Workflow.preconditions string into a typed boolean-expression AST.
 *
 * Rejects English-only prose: any input containing words/punctuation outside
 * the formal grammar throws `F10ParseError`.
 *
 * Empty string is REJECTED — preconditions is optional at the schema level
 * (caller passes "" to mean "no preconditions" — caller decides not to call
 * the parser). The parser itself requires non-empty input.
 *
 * @throws F10ParseError on any deviation from the grammar.
 */
export declare function parseWorkflowPreconditions(input: string): ParsedPreconditionExpr;
/**
 * Parsed failure_policy. Two shapes accepted:
 *   - bare enum: "rollback" / "escalate" / "pause" / "abort" / "continue"
 *   - structured JSON: {"policy": "<enum>", "escalation_target"?: string}
 *
 * Free-form prose (e.g., "if this fails, please tell the founder") is rejected.
 */
export type ParsedFailurePolicy = {
    policy: StepFailureAction;
    /** Optional BoundaryEndpoint ref — only meaningful when policy='escalate'. */
    escalation_target?: string;
};
/**
 * Parse a Workflow.failure_policy string into a typed `ParsedFailurePolicy`.
 *
 * Accepted forms:
 *   - bare enum string: "abort"
 *   - JSON object: {"policy": "escalate", "escalation_target": "founder"}
 *
 * Rejected:
 *   - empty string
 *   - JSON whose `policy` value is outside the 5-enum
 *   - English prose (e.g., "ask the founder to look at this")
 *
 * @throws F10ParseError on any deviation from the accepted forms.
 */
export declare function parseWorkflowFailurePolicy(input: string): ParsedFailurePolicy;
/**
 * V2 §A11 enum for TriggerSpec.pattern. The 5 values pin the recognized
 * routing/gating shapes for trigger composition:
 *
 *   - preprocessor : transforms input before the next workflow stage
 *   - observer     : taps an event stream without back-pressure on producers
 *   - gate         : binary go/no-go based on a guard predicate
 *   - fan_out      : duplicates one input across multiple downstream workflows
 *   - negotiation  : multi-party request/response that expects a reply
 *
 * IMPORTANT — this enum is NOT the older M5-era cron/dependency/threshold
 * triplet. Codex M5 P2.6 caught the V2 spec mismatch and deferred binding
 * until M7. M7 Group W ships the parser; downstream consumers can rely on
 * `parseTriggerSpecPattern` to reject anything outside the closed set.
 */
declare const TRIGGER_PATTERN_VALUES: readonly ["preprocessor", "observer", "gate", "fan_out", "negotiation"];
/** Closed string-literal union for static type narrowing. */
export type TriggerPatternKind = (typeof TRIGGER_PATTERN_VALUES)[number];
/**
 * Thrown by `parseTriggerSpecPattern` when the input does not match one of
 * the 5 V2 enum values. Carries the offending input (truncated for log
 * sanity) so downstream telemetry can surface what slipped past the schema.
 *
 * Distinct error type (not F10ParseError) because the parser's domain is
 * a single enum field — there is no `field` discriminator to carry. Keeping
 * it separate also lets callers route TriggerSpec.pattern rejections to a
 * different remediation path (TriggerSpec authors get a different message
 * from Workflow authors).
 */
export declare class TriggerPatternParseError extends Error {
    readonly input: string;
    constructor(input: string);
}
/**
 * Parse a TriggerSpec.pattern value against the V2 §A11 5-enum.
 *
 * Accepts: any of the 5 enum strings, EXACTLY (no leading/trailing
 * whitespace, no case folding — V2 enums are tokens, not human-readable
 * labels).
 *
 * Rejects:
 *   - non-string inputs (numbers, objects, null, undefined, arrays)
 *   - empty string
 *   - any string outside the 5-enum (including near-miss casings like
 *     'Preprocessor' or 'fan-out')
 *
 * Round-trip identity: `parseTriggerSpecPattern(v) === v` for every v in the
 * enum (the parser does NOT canonicalize — it validates).
 *
 * @throws TriggerPatternParseError on any deviation from the closed enum.
 */
export declare function parseTriggerSpecPattern(input: unknown): TriggerPatternKind;
export {};
//# sourceMappingURL=f10-parsers.d.ts.map