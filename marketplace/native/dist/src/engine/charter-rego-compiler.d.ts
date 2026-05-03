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
import type { Charter } from '../primitives/charter.js';
/**
 * Compiler version constant — bump on ANY change to the Rego generation
 * logic (rule shape, package layout, ordering, allowlist semantics, etc.).
 * Mixed into `policy_version` so the hash distinguishes compiler revisions
 * even when the byte-for-byte rego_source is identical.
 */
export declare const COMPILER_VERSION_CONST = "m7-rego-compiler-v1.0.0";
/**
 * Output of `compileCharter`. Immutable record — Group V evaluator caches
 * this by `policy_version` to avoid re-parsing identical policies.
 */
export interface CompiledPolicy {
    /** Sanitized Charter id; matches `^[a-zA-Z_][a-zA-Z0-9_]*$` for Rego. */
    readonly policy_id: string;
    /** SHA-256 hex of `rego_source + COMPILER_VERSION_CONST`; deterministic. */
    readonly policy_version: string;
    /** Rego v1 source (UTF-8 string). Always parseable by `opa parse`. */
    readonly rego_source: string;
}
/**
 * Thrown by `compileCharter` when the generated Rego references a builtin
 * that is not on the allowlist (codex P1.4 fold). Carries the offending
 * builtin name + the originating Charter id for downstream logging.
 */
export declare class BuiltinNotAllowedError extends Error {
    readonly builtin_name: string;
    readonly charter_id: string;
    constructor(builtin_name: string, charter_id: string);
}
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
export declare const ALLOWED_BUILTINS: ReadonlySet<string>;
/**
 * Walks the generated Rego source for any forbidden builtin reference.
 * Throws BuiltinNotAllowedError on first match. Pure function; no
 * filesystem / network access.
 */
export declare function checkBuiltinAllowlist(rego_source: string, charter_id: string): void;
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
export declare function compileCharter(charter: Charter): CompiledPolicy;
//# sourceMappingURL=charter-rego-compiler.d.ts.map