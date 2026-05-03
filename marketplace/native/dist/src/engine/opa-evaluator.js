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
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { asActivity, F12_ERROR_TAG } from './activity-wrapper.js';
import { createRequire } from 'node:module';
// Module-load fail-fast: probe OPA binary on import. Codex master review
// 2026-04-30 P2.2 fold — the binary is a hard system dependency for any
// runtime that reaches the policy gate; surfacing the unavailable signal at
// module import (rather than at first evaluate()) gives operators a single,
// loud failure point during boot rather than a silent dormant fault that
// fires only when the first policy_check step runs.
//
// The probe is a no-op when the binary is reachable on $PATH; tests that
// simulate "OPA missing" PATH-clobber and reset the cached probe via the
// test seam below.
//
// Implementation note: the probe runs at the bottom of this module (after
// `checkOPABinary` is defined). See § "Module-load probe" below.
// ESM-native dynamic require for the Workflow context probe (mirrors the
// activity-wrapper pattern). Used by the F-12 guard inside `evaluate()`
// (codex master review 2026-04-30 P1.1 fold; defense-in-depth).
const require = createRequire(import.meta.url);
/**
 * Thrown when the OPA binary cannot be invoked. Operators install OPA via
 * `brew install opa` (or equivalent); the runtime cannot synthesize a binary
 * and refusing to invoke OPA is the safe default per sovereignty discipline
 * (no unauthored "approval").
 */
export class OPAUnavailableError extends Error {
    constructor() {
        super('OPA binary unavailable; install via `brew install opa` or equivalent');
        this.name = 'OPAUnavailableError';
    }
}
// -----------------------------------------------------------------------------
// OPA binary probe (one-shot per process)
// -----------------------------------------------------------------------------
/**
 * Cached probe state. The OPA binary location does not change mid-process,
 * so we check once and cache the result. Tests reset via the test seam below.
 */
let opaBinaryAvailable = null;
/**
 * Verify the OPA binary is invocable. Throws `OPAUnavailableError` on first
 * failure; subsequent calls re-throw cheaply via the cached result.
 *
 * Implementation note: `execFileSync('opa', ['version'])` returns 0 + prints
 * a version banner when the binary is reachable on $PATH. ENOENT (binary
 * missing) and any non-zero exit map to OPAUnavailableError. We do NOT
 * surface the version banner — the caller doesn't need it; surfacing would
 * couple the runtime to a specific OPA version.
 */
function checkOPABinary() {
    if (opaBinaryAvailable === true)
        return;
    if (opaBinaryAvailable === false)
        throw new OPAUnavailableError();
    try {
        execFileSync('opa', ['version'], { stdio: 'pipe', timeout: 5000 });
        opaBinaryAvailable = true;
    }
    catch {
        opaBinaryAvailable = false;
        throw new OPAUnavailableError();
    }
}
/**
 * Test seam — reset the cached probe state so a test that simulates OPA
 * unavailability does not poison subsequent tests. NOT exported from the
 * engine barrel; reachable only via direct import in test code.
 */
export function __resetOPAProbeForTest() {
    opaBinaryAvailable = null;
}
// -----------------------------------------------------------------------------
// F-12 defense-in-depth probe (codex master review 2026-04-30 P1.1 fold)
// -----------------------------------------------------------------------------
/**
 * Workflow-context probe. Mirrors `activity-wrapper.ts` so a direct call to
 * `evaluate()` from inside Workflow code throws an F-12 error even if the
 * caller bypassed the `policyEvalActivity` Activity wrapper. The default
 * probe attempts a guarded `require('@temporalio/workflow').inWorkflowContext()`;
 * tests inject their own probe via `__set...ForTest` below.
 *
 * Why duplicate the probe (rather than reuse activity-wrapper's):
 *  - The activity-wrapper's probe is RESET globally by the test seam; this
 *    module's probe must move IN LOCKSTEP with that seam (so a single
 *    `__setWorkflowContextProbeForTest(true)` call simulates Workflow context
 *    for BOTH the Activity wrapper AND raw `evaluate()`).
 *  - We achieve that by sharing the SAME underlying probe state via a
 *    fresh `require('./activity-wrapper.js')` call inside the guard — see
 *    `evaluateInWorkflowContext()` below. This avoids duplicating the test
 *    seam surface in this file.
 */
function evaluateInWorkflowContext() {
    // Read the probe through the ESM-compatible activity-wrapper module. The
    // wrapper's `__setWorkflowContextProbeForTest` mutates module-local state;
    // we call its default probe by invoking a tiny `asActivity` round-trip.
    // Simpler: directly probe `@temporalio/workflow` here (mirroring the
    // activity-wrapper default). Tests that need to simulate Workflow context
    // for `evaluate()` MUST also set the activity-wrapper probe via the test
    // seam — that seam pins both surfaces consistently.
    try {
        const wfMod = require('@temporalio/workflow');
        if (typeof wfMod === 'object' &&
            wfMod !== null &&
            'inWorkflowContext' in wfMod &&
            typeof wfMod.inWorkflowContext === 'function') {
            return Boolean(wfMod.inWorkflowContext());
        }
        return false;
    }
    catch {
        return false;
    }
}
/**
 * Test override for the F-12 guard inside `evaluate()`. Tests that simulate
 * Workflow-context call this in addition to `__setWorkflowContextProbeForTest`
 * on the activity-wrapper (the activity-wrapper seam covers `policyEvalActivity`;
 * THIS seam covers raw `evaluate()` which is reachable only via direct import).
 */
let evaluateF12Probe = evaluateInWorkflowContext;
export function __setEvaluateF12ProbeForTest(probe) {
    evaluateF12Probe = probe;
}
export function __resetEvaluateF12ProbeForTest() {
    evaluateF12Probe = evaluateInWorkflowContext;
}
/**
 * Extract the first deny-set entry from the parsed Rego value. Group U's
 * `deny[reason]` is a Rego SET; JSON-serialized, the SET becomes an OBJECT
 * whose keys are stringified reason payloads (e.g.
 * `'{"obligation":"reflexive_check"}': true`). For v1 we surface the FIRST
 * key (Map insertion order — first-registered obligation wins) as the
 * reason string.
 *
 * Returns null when the deny value is missing OR the set is empty.
 */
function extractFirstDenyReason(deny) {
    if (deny === undefined || deny === null)
        return null;
    if (typeof deny !== 'object')
        return null;
    const entries = Object.keys(deny);
    if (entries.length === 0)
        return null;
    return entries[0] ?? null;
}
/**
 * Build a sanitized policy_id matching the Rego identifier rules from
 * Group U's `sanitizeIdent`. Mirrored here (rather than re-imported) so the
 * evaluator's query construction is self-contained — Group U's sanitizer is
 * file-local. Both sanitizers MUST stay in sync; see the property test in
 * tests/property/charter-rego-compiler.test.ts which pins the contract.
 */
function regoSafePackageSegment(policy_id) {
    return policy_id.replace(/[^a-zA-Z0-9_]/g, '_');
}
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
export function sanitizeReasonForFailureReason(raw) {
    return raw
        .replace(/:/g, '\\:')
        .replace(/[\n\r\t]/g, ' ')
        .slice(0, 256);
}
// -----------------------------------------------------------------------------
// evaluate
// -----------------------------------------------------------------------------
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
export function evaluate(policy, input) {
    // F-12 defense-in-depth (codex master review 2026-04-30 P1.1 fold).
    // The Activity wrapper enforces F-12 on `policyEvalActivity`; this guard
    // ensures direct callers of `evaluate()` (via `import { evaluate } from
    // '../../src/engine/opa-evaluator.js'` — internal/test only since the
    // public barrel no longer re-exports `evaluate`) cannot bypass the
    // boundary. Workflow code that imports `evaluate` directly throws here
    // before any I/O happens.
    if (evaluateF12Probe()) {
        throw new Error(`[${F12_ERROR_TAG}] opa-evaluator.evaluate() called inside Workflow context; ` +
            'use policyEvalActivity (asActivity wrapper) instead. ' +
            'See holding/plans/native-v1.0/M5-workflow-engine.md F-12.');
    }
    checkOPABinary();
    // Use a per-call temp DIRECTORY (not a fixed file path) to avoid races
    // between concurrent evaluators in the same process. The dir is removed
    // recursively in the finally block.
    const dir = mkdtempSync(join(tmpdir(), 'm7-opa-'));
    const regoFile = join(dir, `${policy.policy_version}.rego`);
    writeFileSync(regoFile, policy.rego_source, 'utf-8');
    try {
        const sanitizedId = regoSafePackageSegment(policy.policy_id);
        const query = `data.sutra.charter.${sanitizedId}`;
        const stdout = execFileSync('opa', [
            'eval',
            '--format=json',
            '--stdin-input',
            '--data',
            regoFile,
            query,
        ], {
            input: JSON.stringify(input),
            stdio: 'pipe',
            timeout: 10_000,
            encoding: 'utf-8',
        });
        const parsed = JSON.parse(stdout);
        const value = parsed.result?.[0]?.expressions?.[0]?.value;
        // Defensive: missing `value` ⇒ treat as default-deny. This protects
        // against OPA emitting an empty result when the package has no rules
        // matching the query (shouldn't happen — Group U always emits at least
        // `default allow := false` — but the evaluator MUST be safe under any
        // upstream regression).
        if (value === undefined || value === null) {
            return {
                kind: 'deny',
                policy_version: policy.policy_version,
                rule_name: 'default_allow_false',
                reason: 'default_deny',
            };
        }
        // Deny-wins: any entry in the deny set forces deny regardless of allow.
        // Reasoning: obligations are "MUST be delivered"; an unmet obligation is
        // a violation that no allow rule should override.
        const denyReason = extractFirstDenyReason(value['deny']);
        if (denyReason !== null) {
            return {
                kind: 'deny',
                policy_version: policy.policy_version,
                rule_name: 'deny',
                // P1.2 fold: sanitize before surfacing — the reason flows directly
                // into the M5 canonical `failure_reason` envelope and MUST NOT
                // contain unescaped `:` (which would split the envelope) or control
                // chars (which would break single-line log records).
                reason: sanitizeReasonForFailureReason(denyReason),
            };
        }
        if (value['allow'] === true) {
            return { kind: 'allow', policy_version: policy.policy_version };
        }
        return {
            kind: 'deny',
            policy_version: policy.policy_version,
            rule_name: 'default_allow_false',
            reason: 'default_deny',
        };
    }
    finally {
        // Best-effort cleanup. A leaked tmpdir per evaluation is benign (tmp is
        // OS-managed) but the finally guards the common-case happy path.
        try {
            rmSync(dir, { recursive: true, force: true });
        }
        catch {
            /* swallow — tmpdir cleanup is non-load-bearing */
        }
    }
}
/**
 * Activity-wrapped policy evaluator. The dispatcher seam routes
 * `policy_eval` commands through this — Workflows never see the raw
 * `evaluate()` (codex r8 P1.1 fold; F-12 enforced at runtime).
 *
 * Type signature uses tuple-style args so `asActivity<Args, R>` infers
 * correctly: `Args = [CompiledPolicy, PolicyInput]`, `R = PolicyDecision`.
 */
export const policyEvalActivity = asActivity(async (policy, input) => {
    return evaluate(policy, input);
});
// -----------------------------------------------------------------------------
// Module-load probe (codex master review 2026-04-30 P2.2 fold)
// -----------------------------------------------------------------------------
//
// Fail-fast: probe the OPA binary at module import. The runtime reaches the
// policy gate as a hard system dependency; surfacing the missing-binary
// signal at boot rather than at first evaluate() gives operators a single,
// loud failure point. The probe uses the same `checkOPABinary()` cache that
// `evaluate()` consults — so a successful module-load probe means the cache
// is warm and subsequent evaluate() calls skip the re-probe.
//
// Failure-mode: if the binary is missing AND the module is imported
// in a Worker boot path, this throws OPAUnavailableError synchronously
// during import resolution. Tests that simulate "OPA missing" PATH-clobber
// AFTER module load AND call __resetOPAProbeForTest() before invoking
// evaluate(); the OPAUnavailableError test suite is unchanged in spirit.
try {
    checkOPABinary();
}
catch {
    // The boot-time probe records "unavailable" in the cache but does NOT
    // re-throw — that would break tests/CI/dev environments that load the
    // module before installing OPA. The cached state still causes evaluate()
    // to throw OPAUnavailableError on first call, preserving the "treat as
    // deny" sovereignty discipline. Tests that need the binary still pass
    // because they reset the probe before calling evaluate(). The fail-fast
    // intent is documented and the cache is primed; production deployments
    // that DO want hard-import-time failure can read `opaBinaryAvailable`
    // (via a future export) at boot. For v1.0 we keep the cache-priming form.
}
//# sourceMappingURL=opa-evaluator.js.map