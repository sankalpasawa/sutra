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

import type { StepFailureAction } from '../types/index.js'

// =============================================================================
// Shared error type
// =============================================================================

/**
 * Thrown by both parsers when the input does not satisfy the formal grammar.
 * Carries a `field` tag so call sites can route different rejections to
 * different remediation paths.
 */
export class F10ParseError extends Error {
  public readonly field: 'Workflow.preconditions' | 'Workflow.failure_policy'
  public readonly input: string
  constructor(
    field: 'Workflow.preconditions' | 'Workflow.failure_policy',
    input: string,
    message: string,
  ) {
    super(`[F-10:${field}] ${message} (input="${input.slice(0, 60)}${input.length > 60 ? '…' : ''}")`)
    this.name = 'F10ParseError'
    this.field = field
    this.input = input
  }
}

// =============================================================================
// 1. Workflow.preconditions — boolean expression parser
// =============================================================================

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
export type ParsedPreconditionExpr =
  | { kind: 'identifier'; name: string }
  | { kind: 'comparison'; field: string; op: '==' | '!=' | '<=' | '>=' | '<' | '>'; value: string | number | boolean | null }
  | { kind: 'and'; left: ParsedPreconditionExpr; right: ParsedPreconditionExpr }
  | { kind: 'or'; left: ParsedPreconditionExpr; right: ParsedPreconditionExpr }
  | { kind: 'not'; expr: ParsedPreconditionExpr }

type Token =
  | { kind: '(' }
  | { kind: ')' }
  | { kind: '&&' }
  | { kind: '||' }
  | { kind: '!' }
  | { kind: '==' | '!=' | '<=' | '>=' | '<' | '>' }
  | { kind: 'ident'; value: string }
  | { kind: 'string'; value: string }
  | { kind: 'number'; value: number }
  | { kind: 'true' | 'false' | 'null' }

const IDENT_RE = /^[a-zA-Z_][a-zA-Z0-9_.]*/

function tokenizePreconditions(input: string): Token[] {
  const tokens: Token[] = []
  let i = 0
  while (i < input.length) {
    const ch = input[i]!
    // whitespace
    if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') {
      i++
      continue
    }
    // multi-char ops
    if (input.startsWith('&&', i)) {
      tokens.push({ kind: '&&' })
      i += 2
      continue
    }
    if (input.startsWith('||', i)) {
      tokens.push({ kind: '||' })
      i += 2
      continue
    }
    if (input.startsWith('==', i)) {
      tokens.push({ kind: '==' })
      i += 2
      continue
    }
    if (input.startsWith('!=', i)) {
      tokens.push({ kind: '!=' })
      i += 2
      continue
    }
    if (input.startsWith('<=', i)) {
      tokens.push({ kind: '<=' })
      i += 2
      continue
    }
    if (input.startsWith('>=', i)) {
      tokens.push({ kind: '>=' })
      i += 2
      continue
    }
    // single-char ops
    if (ch === '(' || ch === ')' || ch === '!' || ch === '<' || ch === '>') {
      tokens.push({ kind: ch as '(' | ')' | '!' | '<' | '>' })
      i++
      continue
    }
    // string literal: '...'
    if (ch === "'") {
      let end = i + 1
      while (end < input.length && input[end] !== "'") end++
      if (end >= input.length) {
        throw new F10ParseError('Workflow.preconditions', input, 'unterminated string literal')
      }
      tokens.push({ kind: 'string', value: input.slice(i + 1, end) })
      i = end + 1
      continue
    }
    // number
    if ((ch >= '0' && ch <= '9') || (ch === '-' && /[0-9]/.test(input[i + 1] ?? ''))) {
      let end = i + 1
      while (end < input.length && /[0-9.]/.test(input[end]!)) end++
      const numStr = input.slice(i, end)
      const n = Number(numStr)
      if (!Number.isFinite(n)) {
        throw new F10ParseError('Workflow.preconditions', input, `bad number "${numStr}"`)
      }
      tokens.push({ kind: 'number', value: n })
      i = end
      continue
    }
    // identifier or keyword
    const m = input.slice(i).match(IDENT_RE)
    if (m) {
      const word = m[0]
      if (word === 'true' || word === 'false' || word === 'null') {
        tokens.push({ kind: word })
      } else {
        tokens.push({ kind: 'ident', value: word })
      }
      i += word.length
      continue
    }
    throw new F10ParseError(
      'Workflow.preconditions',
      input,
      `unexpected character "${ch}" at position ${i} — English-only prose is rejected; use structured boolean expression`,
    )
  }
  return tokens
}

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
export function parseWorkflowPreconditions(input: string): ParsedPreconditionExpr {
  if (typeof input !== 'string') {
    throw new F10ParseError('Workflow.preconditions', String(input), 'input must be a string')
  }
  if (input.length === 0) {
    throw new F10ParseError('Workflow.preconditions', input, 'empty string')
  }
  const tokens = tokenizePreconditions(input)
  if (tokens.length === 0) {
    throw new F10ParseError('Workflow.preconditions', input, 'no tokens parsed')
  }

  let pos = 0
  const peek = (): Token | undefined => tokens[pos]
  const consume = (): Token => {
    const t = tokens[pos]
    if (!t) throw new F10ParseError('Workflow.preconditions', input, 'unexpected end of input')
    pos++
    return t
  }

  function parseOr(): ParsedPreconditionExpr {
    let left = parseAnd()
    while (peek()?.kind === '||') {
      consume()
      const right = parseAnd()
      left = { kind: 'or', left, right }
    }
    return left
  }

  function parseAnd(): ParsedPreconditionExpr {
    let left = parseUnary()
    while (peek()?.kind === '&&') {
      consume()
      const right = parseUnary()
      left = { kind: 'and', left, right }
    }
    return left
  }

  function parseUnary(): ParsedPreconditionExpr {
    if (peek()?.kind === '!') {
      consume()
      return { kind: 'not', expr: parseUnary() }
    }
    return parseAtom()
  }

  function parseAtom(): ParsedPreconditionExpr {
    const t = peek()
    if (!t) throw new F10ParseError('Workflow.preconditions', input, 'unexpected end of input')
    if (t.kind === '(') {
      consume()
      const inner = parseOr()
      const close = peek()
      if (close?.kind !== ')') {
        throw new F10ParseError('Workflow.preconditions', input, "expected ')'")
      }
      consume()
      return inner
    }
    if (t.kind === 'ident') {
      consume()
      // optional comparison
      const next = peek()
      if (
        next &&
        (next.kind === '==' || next.kind === '!=' ||
          next.kind === '<=' || next.kind === '>=' ||
          next.kind === '<' || next.kind === '>')
      ) {
        const op = next.kind
        consume()
        const lit = peek()
        if (!lit) throw new F10ParseError('Workflow.preconditions', input, 'expected literal after comparison op')
        let value: string | number | boolean | null
        if (lit.kind === 'string') value = lit.value
        else if (lit.kind === 'number') value = lit.value
        else if (lit.kind === 'true') value = true
        else if (lit.kind === 'false') value = false
        else if (lit.kind === 'null') value = null
        else
          throw new F10ParseError(
            'Workflow.preconditions',
            input,
            `expected literal (string/number/bool/null) after "${op}", got ${lit.kind}`,
          )
        consume()
        return { kind: 'comparison', field: t.value, op, value }
      }
      return { kind: 'identifier', name: t.value }
    }
    throw new F10ParseError('Workflow.preconditions', input, `unexpected token ${t.kind}`)
  }

  const ast = parseOr()
  if (pos !== tokens.length) {
    throw new F10ParseError(
      'Workflow.preconditions',
      input,
      `trailing tokens after expression — likely English prose mixed with structured form`,
    )
  }
  return ast
}

// =============================================================================
// 2. Workflow.failure_policy — 5-enum or structured policy parser
// =============================================================================

/**
 * Parsed failure_policy. Two shapes accepted:
 *   - bare enum: "rollback" / "escalate" / "pause" / "abort" / "continue"
 *   - structured JSON: {"policy": "<enum>", "escalation_target"?: string}
 *
 * Free-form prose (e.g., "if this fails, please tell the founder") is rejected.
 */
export type ParsedFailurePolicy = {
  policy: StepFailureAction
  /** Optional BoundaryEndpoint ref — only meaningful when policy='escalate'. */
  escalation_target?: string
}

const FAILURE_POLICY_VALUES: ReadonlySet<StepFailureAction> = new Set([
  'rollback',
  'escalate',
  'pause',
  'abort',
  'continue',
])

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
export function parseWorkflowFailurePolicy(input: string): ParsedFailurePolicy {
  if (typeof input !== 'string') {
    throw new F10ParseError('Workflow.failure_policy', String(input), 'input must be a string')
  }
  const trimmed = input.trim()
  if (trimmed.length === 0) {
    throw new F10ParseError('Workflow.failure_policy', input, 'empty string')
  }

  // Bare enum form: just the policy keyword.
  if (FAILURE_POLICY_VALUES.has(trimmed as StepFailureAction)) {
    return { policy: trimmed as StepFailureAction }
  }

  // Structured JSON form. Must start with `{` to even attempt JSON parse —
  // anything else is treated as prose and rejected.
  if (trimmed.startsWith('{')) {
    let parsed: unknown
    try {
      parsed = JSON.parse(trimmed)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'unknown'
      throw new F10ParseError(
        'Workflow.failure_policy',
        input,
        `invalid JSON object: ${msg}`,
      )
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      throw new F10ParseError(
        'Workflow.failure_policy',
        input,
        'JSON must be an object with `policy` field',
      )
    }
    const obj = parsed as Record<string, unknown>
    const policyVal = obj.policy
    if (typeof policyVal !== 'string' || !FAILURE_POLICY_VALUES.has(policyVal as StepFailureAction)) {
      throw new F10ParseError(
        'Workflow.failure_policy',
        input,
        `\`policy\` must be one of rollback|escalate|pause|abort|continue; got ${JSON.stringify(policyVal)}`,
      )
    }
    const out: ParsedFailurePolicy = { policy: policyVal as StepFailureAction }
    if ('escalation_target' in obj) {
      const tgt = obj.escalation_target
      if (typeof tgt !== 'string' || tgt.length === 0) {
        throw new F10ParseError(
          'Workflow.failure_policy',
          input,
          '`escalation_target` must be a non-empty string when present',
        )
      }
      out.escalation_target = tgt
    }
    // Reject any extra fields — keeps the parser honest. Callers that need
    // additional data should extend ParsedFailurePolicy + this allow-list.
    for (const k of Object.keys(obj)) {
      if (k !== 'policy' && k !== 'escalation_target') {
        throw new F10ParseError(
          'Workflow.failure_policy',
          input,
          `unexpected field "${k}" — only \`policy\` and \`escalation_target\` are accepted`,
        )
      }
    }
    return out
  }

  // Anything else — English prose, multi-word, not in the enum.
  throw new F10ParseError(
    'Workflow.failure_policy',
    input,
    'expected bare enum (rollback|escalate|pause|abort|continue) or JSON object — English prose rejected',
  )
}

// =============================================================================
// 3. TriggerSpec.pattern — V2 enum parser (M7 Group W T-095)
// =============================================================================

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
const TRIGGER_PATTERN_VALUES = [
  'preprocessor',
  'observer',
  'gate',
  'fan_out',
  'negotiation',
] as const

/** Closed string-literal union for static type narrowing. */
export type TriggerPatternKind = (typeof TRIGGER_PATTERN_VALUES)[number]

const TRIGGER_PATTERN_SET: ReadonlySet<TriggerPatternKind> = new Set(
  TRIGGER_PATTERN_VALUES,
)

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
export class TriggerPatternParseError extends Error {
  public readonly input: string
  constructor(input: string) {
    super(
      `TriggerSpec.pattern must be one of: ${TRIGGER_PATTERN_VALUES.join(
        ', ',
      )}; got: ${safeQuote(input).slice(0, 60)}`,
    )
    this.name = 'TriggerPatternParseError'
    this.input = input
  }
}

/**
 * Best-effort JSON-quoted string for the error payload. JSON.stringify can
 * throw on BigInt + circular structures; this helper falls back to the
 * already-coerced string representation when serialization fails. Pure;
 * does not propagate exceptions.
 */
function safeQuote(s: string): string {
  try {
    return JSON.stringify(s)
  } catch {
    return `"${s}"`
  }
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
export function parseTriggerSpecPattern(input: unknown): TriggerPatternKind {
  if (typeof input !== 'string' || input.length === 0) {
    // Stringify non-strings for the error payload so the operator sees what
    // shape arrived (e.g. `[object Object]`, `null`, `undefined`). Use the
    // safe coercer — naked `String(x)` throws on objects whose `toString` /
    // `valueOf` is overridden to a non-function (e.g. `{toString: ""}`),
    // which would surface as TypeError instead of TriggerPatternParseError.
    throw new TriggerPatternParseError(safeCoerceToString(input))
  }
  if (!TRIGGER_PATTERN_SET.has(input as TriggerPatternKind)) {
    throw new TriggerPatternParseError(input)
  }
  return input as TriggerPatternKind
}

/**
 * Safe `String(x)` replacement. Naked `String(x)` calls `x.toString()` /
 * `x.valueOf()` and propagates anything those throw (TypeError for
 * `{toString: ""}` and similar). The parser guarantees that ANY non-string
 * input throws `TriggerPatternParseError` — so coercion failures must NOT
 * leak as TypeError. This helper traps the failure and falls back to a
 * stable type-tag string.
 */
function safeCoerceToString(x: unknown): string {
  if (x === null) return 'null'
  if (x === undefined) return 'undefined'
  try {
    return String(x)
  } catch {
    // String() threw — fall back to typeof, which never throws.
    return `<${typeof x}>`
  }
}
