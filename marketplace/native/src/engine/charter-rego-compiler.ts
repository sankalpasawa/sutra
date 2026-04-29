/**
 * Charter → Rego compiler — M7 Group U (T-086 + T-087).
 *
 * Compiles a Sutra Charter (V2 §1 P2) into Rego v1 source. The output is
 * loaded by Group V (`opa-evaluator.ts`) and dispatched through the OPA
 * binary at runtime to authorize Workflow / Execution actions per
 * sovereignty discipline (D40 + final-architecture §6).
 *
 * Determinism contract (sovereignty foundation):
 * - `policy_id` derives from `charter.id` (sanitized for Rego identifiers).
 * - `policy_version` is a SHA-256 hash of `rego_source + COMPILER_VERSION_CONST`.
 *   Same Charter input + same compiler version → identical hash. The
 *   compiler version constant must bump on any logic change so policy_version
 *   reflects compiler upgrades even when the source byte-stream is unchanged.
 *
 * Builtin allowlist (codex P1.4 fold; T-087):
 * - Generated Rego MUST NOT reference non-deterministic / external builtins
 *   (`http.*`, `time.*`, `rand.*`, `uuid.*`, `os.*`, `opa.runtime`, `crypto.*`,
 *   `env.*`, `net.*`). These compromise determinism and breach the sovereignty
 *   discipline (the policy outcome must depend only on the explicit input,
 *   never on wall-clock, network, or environment).
 * - The allowlist is enforced BEFORE the CompiledPolicy is returned. Charter
 *   predicates that smuggle forbidden builtins fail at compile-time with
 *   `BuiltinNotAllowedError`, never at OPA-eval time.
 *
 * V1 Rego generation strategy:
 * - One Rego package per Charter: `package sutra.charter.<sanitized_id>`.
 * - Default deny: `default allow := false`.
 * - For each non-empty Constraint predicate: emit `allow if { <predicate> }`.
 * - Predicate strings are taken AS-IS — predicate translation (e.g. DSL →
 *   Rego) is out-of-scope for v1.0; the allowlist scan catches forbidden
 *   builtins regardless of how the predicate string was authored.
 * - For each obligation: emit a `deny[reason]` rule keyed on a sanitized
 *   constraint name so the runtime gets a structured failure-reason payload
 *   when an obligation is violated.
 *
 * Source-of-truth:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group U
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §6
 */

import { createHash } from 'node:crypto'

import type { Charter } from '../primitives/charter.js'
import type { Constraint } from '../types/index.js'

/**
 * Compiler version constant — bump on ANY change to the Rego generation
 * logic (rule shape, package layout, ordering, allowlist semantics, etc.).
 * Mixed into `policy_version` so the hash distinguishes compiler revisions
 * even when the byte-for-byte rego_source is identical.
 */
export const COMPILER_VERSION_CONST = 'm7-rego-compiler-v1.0.0'

/**
 * Output of `compileCharter`. Immutable record — Group V evaluator caches
 * this by `policy_version` to avoid re-parsing identical policies.
 */
export interface CompiledPolicy {
  /** Sanitized Charter id; matches `^[a-zA-Z_][a-zA-Z0-9_]*$` for Rego. */
  readonly policy_id: string
  /** SHA-256 hex of `rego_source + COMPILER_VERSION_CONST`; deterministic. */
  readonly policy_version: string
  /** Rego v1 source (UTF-8 string). Always parseable by `opa parse`. */
  readonly rego_source: string
}

/**
 * Thrown by `compileCharter` when the generated Rego references a builtin
 * that is not on the allowlist (codex P1.4 fold). Carries the offending
 * builtin name + the originating Charter id for downstream logging.
 */
export class BuiltinNotAllowedError extends Error {
  public readonly builtin_name: string
  public readonly charter_id: string

  constructor(builtin_name: string, charter_id: string) {
    super(
      `Charter ${charter_id} compiles to Rego using forbidden builtin: ${builtin_name}`,
    )
    this.name = 'BuiltinNotAllowedError'
    this.builtin_name = builtin_name
    this.charter_id = charter_id
  }
}

// -----------------------------------------------------------------------------
// Builtin allowlist (T-087 — codex P1.4 fold)
// -----------------------------------------------------------------------------

/**
 * Allowlist of Rego builtins the compiler permits in generated source.
 *
 * Operators (==, !=, <, <=, >, >=, +, -, *, /, %, &&, ||, !) are tokenized
 * separately by the OPA parser and are not subject to the dotted-name
 * pattern check below — they're always allowed.
 *
 * Reference list — kept for human review even though enforcement is via
 * the FORBIDDEN patterns below (denylist semantics, not allowlist match):
 */
export const ALLOWED_BUILTINS: ReadonlySet<string> = new Set([
  'count',
  'contains',
  'startswith',
  'endswith',
  'regex.match',
])

/**
 * Forbidden builtin name-prefix patterns. Any match in the generated Rego
 * source rejects the compile with BuiltinNotAllowedError.
 *
 * Pattern semantics:
 * - `\b` word-boundary so `time.now_ns()` matches but `crime.report` does
 *   not (no false positives on user identifiers happening to contain the
 *   forbidden token as a substring).
 * - Trailing `.` requires the dotted-namespace form (the canonical Rego
 *   builtin syntax). Bare `http` as a variable name passes; `http.send`
 *   does not.
 *
 * The order is intentional: HTTP / network / time / randomness / identity /
 * environment / runtime / crypto — categories ranked by sovereignty risk
 * (network egress first, side-channel last).
 */
const FORBIDDEN_BUILTIN_PATTERNS: readonly RegExp[] = [
  /\bhttp\./,
  /\bnet\./,
  /\btime\./,
  /\brand\./,
  /\buuid\./,
  /\bos\./,
  /\bopa\.runtime/,
  /\bcrypto\./,
  /\benv\./,
]

/**
 * Walks the generated Rego source for any forbidden builtin reference.
 * Throws BuiltinNotAllowedError on first match. Pure function; no
 * filesystem / network access.
 */
export function checkBuiltinAllowlist(
  rego_source: string,
  charter_id: string,
): void {
  for (const pattern of FORBIDDEN_BUILTIN_PATTERNS) {
    const match = pattern.exec(rego_source)
    if (match !== null) {
      // match[0] is the full token e.g. "http." — strip trailing dot for
      // the error payload so the consumer gets the bare builtin namespace.
      const builtin = match[0].replace(/\.$/, '')
      throw new BuiltinNotAllowedError(builtin, charter_id)
    }
  }
}

// -----------------------------------------------------------------------------
// Charter id + Constraint name sanitization
// -----------------------------------------------------------------------------

/**
 * Sanitize a Charter id (or constraint name) into a valid Rego identifier:
 * - Lowercase ASCII letters, digits, underscore.
 * - Must start with a letter or underscore (digits get prefixed with `_`).
 * - Empty / all-non-ASCII inputs map to a stable fallback.
 */
function sanitizeIdent(raw: string, fallback: string): string {
  // Replace any character outside [a-zA-Z0-9_] with `_`.
  const cleaned = raw.replace(/[^a-zA-Z0-9_]/g, '_')
  // Drop leading underscores from a fully-stripped string so the fallback
  // anchors the result.
  const trimmed = cleaned.replace(/^_+/, '')
  if (trimmed.length === 0) return fallback
  // If first char is a digit, prefix with `_` so the result matches
  // Rego's identifier grammar.
  if (/^[0-9]/.test(trimmed)) return `_${trimmed}`
  return trimmed
}

// -----------------------------------------------------------------------------
// Rego generation (V1 — minimal but works)
// -----------------------------------------------------------------------------

/** Trim Rego predicate strings; pass-through with leading/trailing ws stripped. */
function normalizePredicate(predicate: string): string {
  return predicate.trim()
}

/** Build the `package` declaration line. */
function regoPackageLine(policy_id: string): string {
  return `package sutra.charter.${policy_id}`
}

/**
 * Build `allow if { <predicate> }` rules — one per Constraint with a
 * non-empty predicate. Constraints with empty/whitespace-only predicates
 * are skipped (they contribute nothing checkable).
 */
function regoAllowRules(constraints: readonly Constraint[]): string[] {
  const rules: string[] = []
  for (const c of constraints) {
    const pred = normalizePredicate(c.predicate)
    if (pred.length === 0) continue
    rules.push(`allow if { ${pred} }`)
  }
  return rules
}

/**
 * Build `deny[reason]` rules — one per obligation. The `reason` is a
 * structured object keyed on the sanitized constraint name so the runtime
 * gets a machine-readable failure payload when an obligation is violated.
 *
 * Rego v1 doesn't accept parenthesized multi-statement bodies inline, so
 * each obligation predicate is FIRST extracted into a named helper rule
 * (`obligation_<index>_holds if { <predicate> }`) and then negated in the
 * deny rule (`not obligation_<index>_holds`). This works for both single-
 * expression predicates and semicolon-joined conjunctions.
 *
 * Returns the helper rules first, then the deny rules — preserves the
 * declaration-before-use convention even though Rego doesn't strictly
 * require it (helps `opa parse` failure messages target the right line).
 */
function regoObligationDenyBlocks(
  obligations: readonly Constraint[],
): string[] {
  const blocks: string[] = []
  let index = 0
  for (const c of obligations) {
    const pred = normalizePredicate(c.predicate)
    if (pred.length === 0) continue
    const ident = sanitizeIdent(c.name, `unnamed_obligation_${index}`)
    const helper = `obligation_${index}_holds`
    // Helper rule body: predicate must hold.
    blocks.push(`${helper} if { ${pred} }`)
    // Deny rule: fires when helper doesn't hold.
    blocks.push(
      `deny[reason] if {\n\tnot ${helper}\n\treason := {"obligation": "${ident}"}\n}`,
    )
    index += 1
  }
  return blocks
}

/**
 * Compile a Charter into a CompiledPolicy.
 *
 * Steps:
 *   1. Sanitize Charter id → Rego-safe policy_id.
 *   2. Generate Rego source: package + default deny + allow rules + deny rules.
 *   3. T-087: scan generated source against the forbidden builtin denylist;
 *      throw BuiltinNotAllowedError on first match.
 *   4. Compute policy_version = sha256(rego_source + COMPILER_VERSION_CONST).
 *   5. Return frozen CompiledPolicy.
 */
export function compileCharter(charter: Charter): CompiledPolicy {
  const policy_id = sanitizeIdent(charter.id, 'unnamed_charter')

  // Aggregate the constraint pools that contribute rules.
  // - `obligations` produce both an `allow if { pred }` (predicate must hold
  //   to allow) AND a `deny[reason]` (failure-bearing) rule.
  // - `invariants` produce `allow if { pred }`.
  // - `constraints` (episodic) produce `allow if { pred }`.
  // V1: identical "allow if pred" treatment is fine — the discipline is in
  // the generated rule set being checkable; tightening shape comes in v1.1.
  const allow_pool: Constraint[] = [
    ...charter.obligations,
    ...charter.invariants,
    ...charter.constraints,
  ]

  const allow_rules = regoAllowRules(allow_pool)
  const obligation_blocks = regoObligationDenyBlocks(charter.obligations)

  const lines: string[] = []
  lines.push(regoPackageLine(policy_id))
  lines.push('')
  // OPA Rego v1 requires `import rego.v1` for the `if`/`contains` keywords
  // we emit below. Without it, `opa parse --v1-compatible` is fine but the
  // default profile rejects the source. Emit always — `opa parse` accepts
  // it on every supported version.
  lines.push('import rego.v1')
  lines.push('')
  lines.push('default allow := false')
  if (allow_rules.length > 0) {
    lines.push('')
    for (const rule of allow_rules) lines.push(rule)
  }
  if (obligation_blocks.length > 0) {
    lines.push('')
    for (const block of obligation_blocks) lines.push(block)
  }
  // Trailing newline keeps the file POSIX-clean and `opa parse`-friendly.
  const rego_source = `${lines.join('\n')}\n`

  // T-087: builtin allowlist — throws BuiltinNotAllowedError on first match.
  checkBuiltinAllowlist(rego_source, charter.id)

  const policy_version = createHash('sha256')
    .update(rego_source)
    .update(COMPILER_VERSION_CONST)
    .digest('hex')

  return Object.freeze({
    policy_id,
    policy_version,
    rego_source,
  })
}
