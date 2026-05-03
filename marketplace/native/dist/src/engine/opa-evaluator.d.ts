/**
 * OPA evaluator — M7 Group V (T-090, T-091).
 *
 * Invokes the OPA binary to evaluate a `CompiledPolicy` against a
 * `PolicyInput`. The boundary is intentionally narrow: this module shells out
 * to `opa eval --format=json --stdin-input --data <rego file>`, parses the
 * JSON result, and folds the (allow, deny[]) pair into a discriminated
 * `PolicyDecision`.
 *
 * Activity boundary (codex r8 P1.1 fold):
 * - The shell-out IS I/O. `evaluate()` is an Activity-shaped operation and
 *   MUST be exposed to Workflows ONLY through `policyEvalActivity` (the
 *   `asActivity(evaluate)` wrap below). Calling `evaluate()` directly from
 *   Workflow code triggers F-12 at runtime via the activity-wrapper probe.
 * - The dispatcher seam in `policy-dispatcher.ts` routes `policy_eval`
 *   commands through this Activity — Workflow code never invokes the OPA
 *   binary directly, preserving replay determinism.
 *
 * Decision semantics (deny-wins):
 * - The Rego module emits both `allow if {pred}` rules (default false) and
 *   `deny[reason] if {!helper}` rules per Group U.
 * - Group U's `deny[reason]` produces a Rego SET — JSON-serialized as an
 *   object whose KEYS are stringified reason payloads (verified empirically
 *   2026-04-30 against opa 1.15.2; see Group V plan §test-fixture).
 * - A non-empty `deny` set ⇒ deny (carries the first reason). A `deny=={}`
 *   AND `allow==true` ⇒ allow. `deny=={}` AND `allow==false` ⇒ default-deny.
 *
 * Source-of-truth:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group V T-090, T-091
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §6
 *  - .enforcement/codex-reviews/2026-04-30-m7-plan-pre-dispatch.md P1.1
 */
import type { CompiledPolicy } from './charter-rego-compiler.js';
/**
 * Input shape passed to `evaluate()`. Three fields — the step under
 * evaluation, the parent Workflow, and the execution context (visited /
 * completed step ids, recursion depth, autonomy level). The Rego predicates
 * read these via `input.step`, `input.workflow`, `input.execution_context`.
 *
 * `unknown` rather than concrete primitive types: the evaluator is policy-
 * agnostic — Charters declare the shape they expect. Runtime bug-catching
 * for malformed inputs is the policy's job (deny if missing fields).
 */
export interface PolicyInput {
    readonly step: unknown;
    readonly workflow: unknown;
    readonly execution_context: unknown;
}
/** Allow decision — policy passed; carries the policy_version for audit. */
export interface PolicyAllow {
    readonly kind: 'allow';
    readonly policy_version: string;
}
/** Deny decision — policy rejected; carries reason + rule_name + version. */
export interface PolicyDeny {
    readonly kind: 'deny';
    readonly policy_version: string;
    readonly rule_name: string;
    readonly reason: string;
}
export type PolicyDecision = PolicyAllow | PolicyDeny;
/**
 * Thrown when the OPA binary cannot be invoked. Operators install OPA via
 * `brew install opa` (or equivalent); the runtime cannot synthesize a binary
 * and refusing to invoke OPA is the safe default per sovereignty discipline
 * (no unauthored "approval").
 */
export declare class OPAUnavailableError extends Error {
    constructor();
}
/**
 * Test seam — reset the cached probe state so a test that simulates OPA
 * unavailability does not poison subsequent tests. NOT exported from the
 * engine barrel; reachable only via direct import in test code.
 */
export declare function __resetOPAProbeForTest(): void;
export declare function __setEvaluateF12ProbeForTest(probe: () => boolean): void;
export declare function __resetEvaluateF12ProbeForTest(): void;
/**
 * Sanitize a deny-reason string before it is concatenated into the M5
 * canonical `failure_reason` envelope (`step:N:<action>:<errMsg>` →
 * `step:N:abort:policy_deny:<rule_name>:<reason>:<policy_version>`).
 *
 * Codex master review 2026-04-30 P1.2 fold (BLOCKER):
 *  - Obligation denies surface stringified Rego SET keys (e.g.
 *    `'{"obligation":"must_hold"}'`). Raw, those keys contain unescaped `:`
 *    characters that break the colon-delimited audit envelope — downstream
 *    parsers split on `:` and yield garbage. Replace `:` with `\:` (escaped
 *    colon). Length cap at 256 to bound failure_reason size; control chars
 *    (newlines, tabs, CR) collapse to spaces so the envelope stays single-line.
 */
export declare function sanitizeReasonForFailureReason(raw: string): string;
/**
 * Evaluate a compiled policy against a policy input. Synchronous shell-out;
 * O(few-ms) on a warm process. Throws `OPAUnavailableError` when the binary
 * is missing.
 *
 * Decision protocol (deny-wins):
 *   1. Run `opa eval` with the Rego source written to a temp file + the
 *      input JSON on stdin.
 *   2. Query `data.sutra.charter.<sanitized_policy_id>` — returns a Rego
 *      object containing `allow: bool` and `deny: set<reason>` (set-as-object
 *      in JSON).
 *   3. If `deny` set has any entries → return `{kind:'deny', rule_name:'deny',
 *      reason:<first deny entry>, policy_version}`.
 *   4. Else if `allow === true` → return `{kind:'allow', policy_version}`.
 *   5. Else → return `{kind:'deny', rule_name:'default_allow_false',
 *      reason:'default_deny', policy_version}`.
 *
 * Replay determinism (sovereignty foundation):
 *   - Same (policy, input) ⇒ bit-identical decision regardless of when the
 *     evaluation runs. The Rego source is content-hashed via policy_version,
 *     so a policy change forces a new version (and policy_dispatcher will
 *     fetch the new compiled bundle from OPABundleService).
 *   - The temp file is deleted on every call (best-effort cleanup in the
 *     finally block); the OPA binary is stateless across invocations.
 */
export declare function evaluate(policy: CompiledPolicy, input: PolicyInput): PolicyDecision;
/**
 * Activity-wrapped policy evaluator. The dispatcher seam routes
 * `policy_eval` commands through this — Workflows never see the raw
 * `evaluate()` (codex r8 P1.1 fold; F-12 enforced at runtime).
 *
 * Type signature uses tuple-style args so `asActivity<Args, R>` infers
 * correctly: `Args = [CompiledPolicy, PolicyInput]`, `R = PolicyDecision`.
 */
export declare const policyEvalActivity: import("./activity-wrapper.js").ActivityFn<[policy: CompiledPolicy, input: PolicyInput], PolicyDecision>;
//# sourceMappingURL=opa-evaluator.d.ts.map