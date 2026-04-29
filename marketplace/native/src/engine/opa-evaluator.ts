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

import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import type { CompiledPolicy } from './charter-rego-compiler.js'
import { asActivity } from './activity-wrapper.js'

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
  readonly step: unknown
  readonly workflow: unknown
  readonly execution_context: unknown
}

/** Allow decision — policy passed; carries the policy_version for audit. */
export interface PolicyAllow {
  readonly kind: 'allow'
  readonly policy_version: string
}

/** Deny decision — policy rejected; carries reason + rule_name + version. */
export interface PolicyDeny {
  readonly kind: 'deny'
  readonly policy_version: string
  readonly rule_name: string
  readonly reason: string
}

export type PolicyDecision = PolicyAllow | PolicyDeny

/**
 * Thrown when the OPA binary cannot be invoked. Operators install OPA via
 * `brew install opa` (or equivalent); the runtime cannot synthesize a binary
 * and refusing to invoke OPA is the safe default per sovereignty discipline
 * (no unauthored "approval").
 */
export class OPAUnavailableError extends Error {
  constructor() {
    super('OPA binary unavailable; install via `brew install opa` or equivalent')
    this.name = 'OPAUnavailableError'
  }
}

// -----------------------------------------------------------------------------
// OPA binary probe (one-shot per process)
// -----------------------------------------------------------------------------

/**
 * Cached probe state. The OPA binary location does not change mid-process,
 * so we check once and cache the result. Tests reset via the test seam below.
 */
let opaBinaryAvailable: boolean | null = null

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
function checkOPABinary(): void {
  if (opaBinaryAvailable === true) return
  if (opaBinaryAvailable === false) throw new OPAUnavailableError()
  try {
    execFileSync('opa', ['version'], { stdio: 'pipe', timeout: 5000 })
    opaBinaryAvailable = true
  } catch {
    opaBinaryAvailable = false
    throw new OPAUnavailableError()
  }
}

/**
 * Test seam — reset the cached probe state so a test that simulates OPA
 * unavailability does not poison subsequent tests. NOT exported from the
 * engine barrel; reachable only via direct import in test code.
 */
export function __resetOPAProbeForTest(): void {
  opaBinaryAvailable = null
}

// -----------------------------------------------------------------------------
// OPA result parsing
// -----------------------------------------------------------------------------

/**
 * Shape of the JSON `opa eval --format=json` returns. Defensive parse — we
 * never assume keys exist; missing fields fall through to default-deny.
 */
interface OpaEvalResult {
  result?: Array<{
    expressions?: Array<{
      value?: Record<string, unknown>
    }>
  }>
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
function extractFirstDenyReason(deny: unknown): string | null {
  if (deny === undefined || deny === null) return null
  if (typeof deny !== 'object') return null
  const entries = Object.keys(deny as Record<string, unknown>)
  if (entries.length === 0) return null
  return entries[0] ?? null
}

/**
 * Build a sanitized policy_id matching the Rego identifier rules from
 * Group U's `sanitizeIdent`. Mirrored here (rather than re-imported) so the
 * evaluator's query construction is self-contained — Group U's sanitizer is
 * file-local. Both sanitizers MUST stay in sync; see the property test in
 * tests/property/charter-rego-compiler.test.ts which pins the contract.
 */
function regoSafePackageSegment(policy_id: string): string {
  return policy_id.replace(/[^a-zA-Z0-9_]/g, '_')
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
export function evaluate(policy: CompiledPolicy, input: PolicyInput): PolicyDecision {
  checkOPABinary()

  // Use a per-call temp DIRECTORY (not a fixed file path) to avoid races
  // between concurrent evaluators in the same process. The dir is removed
  // recursively in the finally block.
  const dir = mkdtempSync(join(tmpdir(), 'm7-opa-'))
  const regoFile = join(dir, `${policy.policy_version}.rego`)
  writeFileSync(regoFile, policy.rego_source, 'utf-8')

  try {
    const sanitizedId = regoSafePackageSegment(policy.policy_id)
    const query = `data.sutra.charter.${sanitizedId}`

    const stdout = execFileSync(
      'opa',
      [
        'eval',
        '--format=json',
        '--stdin-input',
        '--data',
        regoFile,
        query,
      ],
      {
        input: JSON.stringify(input),
        stdio: 'pipe',
        timeout: 10_000,
        encoding: 'utf-8',
      },
    )

    const parsed = JSON.parse(stdout) as OpaEvalResult
    const value = parsed.result?.[0]?.expressions?.[0]?.value

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
      }
    }

    // Deny-wins: any entry in the deny set forces deny regardless of allow.
    // Reasoning: obligations are "MUST be delivered"; an unmet obligation is
    // a violation that no allow rule should override.
    const denyReason = extractFirstDenyReason(value['deny'])
    if (denyReason !== null) {
      return {
        kind: 'deny',
        policy_version: policy.policy_version,
        rule_name: 'deny',
        reason: denyReason,
      }
    }

    if (value['allow'] === true) {
      return { kind: 'allow', policy_version: policy.policy_version }
    }

    return {
      kind: 'deny',
      policy_version: policy.policy_version,
      rule_name: 'default_allow_false',
      reason: 'default_deny',
    }
  } finally {
    // Best-effort cleanup. A leaked tmpdir per evaluation is benign (tmp is
    // OS-managed) but the finally guards the common-case happy path.
    try {
      rmSync(dir, { recursive: true, force: true })
    } catch {
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
export const policyEvalActivity = asActivity(
  async (policy: CompiledPolicy, input: PolicyInput): Promise<PolicyDecision> => {
    return evaluate(policy, input)
  },
)
