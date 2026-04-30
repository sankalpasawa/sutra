/**
 * host-llm-activity — M8 Group BB (T-117..T-119, T-122).
 *
 * Sutra's host-LLM seam. The architecture pivot (founder direction
 * 2026-04-30) replaces the originally-planned Anthropic SDK integration with
 * a CLI shell-out into the host's own LLM runtime — Claude Code's
 * `claude --bare --print` is the FIRST-CLASS dispatch (the canonical host
 * Sutra targets), `codex exec` is supported as ADVISORY (parity with
 * Claude's MCP / config tree is NOT established at v1.0; see "MCP scope"
 * comment block below).
 *
 * Why CLI shell-out over SDK:
 *   - Sovereignty: the host process owns its own permissions, MCP servers,
 *     auto-memory, and skill catalog; embedding the SDK would force Sutra
 *     to re-implement those concerns and silently diverge from the host's
 *     evolving capability set.
 *   - Recursion safety: `claude --bare` (verified on Claude Code 2.1.123)
 *     SKIPS plugin sync, hooks, LSP, attribution, auto-memory, keychain
 *     reads, and CLAUDE.md auto-discovery; sets CLAUDE_CODE_SIMPLE=1. The
 *     `--bare` flag is REQUIRED — without it, a Sutra Workflow invoking
 *     Claude would re-trigger plugin sync + hooks + memory loads and risk
 *     unbounded recursion. Codex pivot review CHANGE #3 made this the
 *     load-bearing safety mechanism.
 *   - Determinism: prompt + host_kind + host_version + workflow_run_seq
 *     hash to a deterministic invocation_id (sha256 truncated to 32 hex
 *     chars; clock-free). Replay produces a bit-identical id and the same
 *     audit trail.
 *
 * MCP scope (codex pivot review fold #4 + #9):
 *   - Claude `--bare` mode: SKIPS plugin sync, CLAUDE.md auto-discovery,
 *     hooks, LSP, attribution, auto-memory, keychain reads, background
 *     prefetches. Sets CLAUDE_CODE_SIMPLE=1. MCP servers from the user's
 *     `.claude/` configuration are NOT inherited by the spawned process.
 *   - `codex exec`: uses `~/.codex/config.toml` (a SEPARATE config tree
 *     from `.claude/`); MCP parity with Claude is NOT established at v1.0.
 *   - Per-invocation MCP context passing is DEFERRED to v1.x. The v1.0
 *     contract is: a host-LLM Activity gets ONLY the prompt that flows
 *     through the explicit step input, plus whatever MCP each host's bare
 *     mode chooses to expose. Sutra does not bridge MCP servers between
 *     hosts in v1.0.
 *
 * Public API:
 *   - `hostLLMActivity(args) -> Promise<HostLLMResult>` — the
 *     asActivity-wrapped form. THIS is what the executor dispatches via
 *     `action='invoke_host_llm'`. F-12 trap from M5 covers it (called from
 *     a Workflow context throws ForbiddenCouplingF12 before any subprocess
 *     spawns).
 *   - `HostKind`, `HostLLMInvokeArgs`, `HostLLMResult`, `HostUnavailableError`.
 *
 * NOT in the public engine barrel (M7 P1.1 lesson; see src/engine/index.ts):
 *   - The raw `invokeHostLLM(args)` function — internal seam used to wrap
 *     via asActivity. External callers MUST go through `hostLLMActivity`.
 *     Codex M8 master review 2026-04-30 P1.1 fold added an F-12 guard
 *     INSIDE `invokeHostLLM` (mirroring the opa-evaluator.evaluate fix) so
 *     a Workflow-side deep import cannot bypass the activity wrapper.
 *   - The test seams `__set/resetHostAvailabilityForTest`,
 *     `__set/resetExecFileSyncStubForTest`,
 *     `__set/resetInvokeHostLLMF12ProbeForTest`. Reachable only by test
 *     code importing this module directly.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group BB
 *   - .enforcement/codex-reviews/2026-04-30-architecture-pivot-review.md
 *   - .enforcement/codex-reviews/2026-04-30-architecture-pivot-rereview.md
 *     (DIRECTIVE-ID 1777521736)
 *   - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 */

import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { asActivity } from './activity-wrapper.js'

// `createRequire` lets this ESM module pull `@temporalio/workflow` for the
// F-12 probe below. We can't `import` it at the top because workflow code
// must be loadable in non-Temporal test contexts (Vitest unit tests do not
// install the workflow runtime); a guarded `require` keeps the load lazy +
// catchable.
const __require = createRequire(import.meta.url)

/**
 * The two host LLMs Sutra targets at v1.0.
 *
 * Mirror of `HostKind` in src/types/index.ts (kept as a separate alias here
 * so engine consumers can import without depending on the types barrel).
 */
export type HostKind = 'claude' | 'codex'

/**
 * Arguments for a host-LLM invocation.
 *
 * `prompt` is the only payload that crosses into the host process; per the
 * MCP-scope comment above, no ambient context is bridged. `timeout_ms`
 * defaults to 60_000 (60 s) — long enough for typical Claude/codex single-
 * shot completions, short enough that a hung subprocess cannot stall the
 * Workflow indefinitely.
 *
 * `model` is an OPTIONAL hint (e.g. 'sonnet') that v1.0 forwards to
 * neither CLI — Claude `--bare --print` does not accept a model flag in
 * 2.1.123, and `codex exec` reads model from its own config.toml. The
 * field is reserved for v1.x when host CLIs expose runtime model
 * selection; today it is recorded for provenance and ignored at dispatch.
 *
 * `workflow_run_seq` is the deterministic per-Workflow run counter
 * supplied by the executor (D-NS-26). It contributes to invocation_id so
 * replays of the same run produce the same id; tests that exercise
 * determinism pass an explicit seq.
 */
export interface HostLLMInvokeArgs {
  readonly prompt: string
  readonly host: HostKind
  readonly timeout_ms?: number
  readonly model?: string
  readonly workflow_run_seq: number
}

/**
 * Result of a successful host-LLM invocation.
 *
 * `host_version` is captured at module-load probe time — same value for
 * every invocation in this process. `invocation_id` is sha256(prompt +
 * host_kind + host_version + workflow_run_seq).slice(0, 32). Provenance
 * stamp emitted by the executor (T-121) carries host_kind + host_version +
 * invocation_id + prompt_hash + response_hash so downstream observability
 * can correlate inputs/outputs without re-storing prompt/response text.
 *
 * `tokens_used` is OPTIONAL — Claude Code 2.1.123 does not surface tokens
 * via `--print` stdout; v1.0 leaves the field undefined. Future host CLIs
 * that report usage may populate it.
 */
export interface HostLLMResult {
  readonly response: string
  readonly host_kind: HostKind
  readonly host_version: string
  readonly exit_code: number
  readonly invocation_id: string
  readonly tokens_used?: number
}

/**
 * Thrown by `invokeHostLLM` when the host CLI is not present on PATH at
 * dispatch time. The runtime probes both hosts at module load and caches
 * availability; an unavailable host throws this error at FIRST DISPATCH —
 * not at module load (D-NS-29: probe failures must be non-throwing so a
 * single missing host doesn't break the whole runtime).
 *
 * The message includes a human-readable install hint per host so the
 * operator can self-recover. Downstream observability sees
 * `host_llm_unavailable:<host>` as the failure_reason (see step-graph-
 * executor T-120 wiring).
 */
export class HostUnavailableError extends Error {
  constructor(public readonly host: HostKind) {
    super(
      `Host LLM '${host}' is unavailable. Install via: ` +
        (host === 'claude'
          ? 'visit claude.com/code'
          : 'visit npmjs.com/@openai/codex'),
    )
    this.name = 'HostUnavailableError'
  }
}

// =============================================================================
// F-12 defense-in-depth probe (codex master review 2026-04-30 P1.1 fold)
// =============================================================================

/**
 * Workflow-context probe for `invokeHostLLM`. Mirrors the same shape used in
 * `opa-evaluator.evaluate` (M7 P1.1 precedent): the Activity wrapper at
 * `activity-wrapper.ts` enforces F-12 on the wrapped form (`hostLLMActivity`),
 * but the raw subprocess seam (`invokeHostLLM`) is reachable via direct module
 * import from test code. Without a probe inside the raw function, a Workflow-
 * side deep import of `src/engine/host-llm-activity.js` would execute
 * subprocess I/O without ever hitting the workflow-context guard.
 *
 * The default probe attempts a guarded `require('@temporalio/workflow')`'s
 * `inWorkflowContext()`; tests inject their own probe via the
 * `__set/resetInvokeHostLLMF12ProbeForTest` seam below to simulate Workflow
 * context (since Vitest unit tests do not install the workflow runtime).
 */
function defaultInvokeHostLLMF12Probe(): boolean {
  try {
    const wfMod: unknown = __require('@temporalio/workflow')
    if (
      typeof wfMod === 'object' &&
      wfMod !== null &&
      'inWorkflowContext' in wfMod &&
      typeof (wfMod as { inWorkflowContext: unknown }).inWorkflowContext === 'function'
    ) {
      return Boolean((wfMod as { inWorkflowContext: () => boolean }).inWorkflowContext())
    }
    return false
  } catch {
    // Not in a Temporal workflow runtime; fall through.
    return false
  }
}

let invokeHostLLMF12Probe: () => boolean = defaultInvokeHostLLMF12Probe

/**
 * Test override for the F-12 guard inside `invokeHostLLM`. Tests that simulate
 * Workflow context use this seam to assert the trap fires even when the
 * subprocess stub would otherwise succeed.
 *
 * NOT exported on the public engine barrel (M7 P1.1 lesson — keep test seams
 * off the production import surface).
 */
export function __setInvokeHostLLMF12ProbeForTest(probe: () => boolean): void {
  invokeHostLLMF12Probe = probe
}

export function __resetInvokeHostLLMF12ProbeForTest(): void {
  invokeHostLLMF12Probe = defaultInvokeHostLLMF12Probe
}

// =============================================================================
// Module-load probe (T-118)
// =============================================================================

/**
 * Per-host availability cache. Populated at module load by `probeHost(host)`
 * for both 'claude' and 'codex'. Non-throwing — if a host's `--version`
 * call fails (binary missing, permissions, timeout), we record
 * `{available: false, version: null}` and the FIRST DISPATCH for that host
 * throws HostUnavailableError. Codex pivot review fold #4 + #6 (the
 * runtime probes ONCE per process; per-dispatch probes would add 5+ ms
 * overhead per Activity invocation and racey re-detection).
 */
const hostAvailability: Map<HostKind, { available: boolean; version: string | null }> = new Map()

/**
 * Probe one host's `--version` output. Pure function — no side effects on
 * cache. Caller (module-load) populates the cache once. Tests can call
 * this directly via the module export to assert probe behavior, but the
 * usual seam for tests is `__setHostAvailabilityForTest(map)`.
 *
 * Timeout 5_000 ms is conservative — both `claude --version` and
 * `codex --version` should return within 100 ms on a healthy machine; the
 * 5 s ceiling guards against a hung binary at module load (which would
 * delay every consumer's first import).
 */
function probeHost(host: HostKind): { available: boolean; version: string | null } {
  try {
    const versionOutput = execFileSync(host, ['--version'], {
      stdio: 'pipe',
      encoding: 'utf-8',
      timeout: 5000,
    }).trim()
    return { available: true, version: versionOutput }
  } catch {
    return { available: false, version: null }
  }
}

// Probe both hosts at module load. Non-throwing per D-NS-29 — if neither
// host is installed, the runtime still loads; only invocations against the
// missing host(s) fail.
hostAvailability.set('claude', probeHost('claude'))
hostAvailability.set('codex', probeHost('codex'))

// =============================================================================
// Test seams — NOT exported on the engine barrel (M7 P1.1 lesson)
// =============================================================================

/**
 * Optional override for host availability at test time. When set, the
 * runtime resolves `getAvailability(host)` against this map instead of the
 * module-load probe cache. Tests use this to:
 *   - Force HostUnavailableError without uninstalling the real CLI
 *   - Pin host_version to a known value for deterministic invocation_id
 *   - Exercise both 'claude' and 'codex' branches without having both
 *     installed
 *
 * Pass `null` (or call `__resetHostAvailabilityForTest()`) to restore the
 * module-load probe cache.
 */
let availabilityOverride: Map<HostKind, { available: boolean; version: string | null }> | null = null

export function __setHostAvailabilityForTest(
  map: Map<HostKind, { available: boolean; version: string | null }> | null,
): void {
  availabilityOverride = map
}

export function __resetHostAvailabilityForTest(): void {
  availabilityOverride = null
}

function getAvailability(host: HostKind): { available: boolean; version: string | null } {
  if (availabilityOverride) {
    const o = availabilityOverride.get(host)
    if (o) return o
  }
  return hostAvailability.get(host) ?? { available: false, version: null }
}

/**
 * Stub for the `execFileSync` subprocess call. Tests that exercise the
 * dispatch path (CLI args, stdin, response capture, exit-code wrapping)
 * inject this stub via `__setExecFileSyncStubForTest(stub)` so no real
 * `claude` or `codex` subprocess is spawned in the test suite.
 *
 * The stub signature mirrors the subset of `execFileSync` options the
 * runtime uses: `input` (stdin payload for codex), `timeout` (defended at
 * dispatch), and `encoding: 'utf-8'`. Returning a string corresponds to a
 * successful invocation; throwing simulates a non-zero exit.
 */
export type ExecFileSyncStub = (
  file: string,
  args: string[],
  options: { input?: string; timeout?: number; encoding: 'utf-8' },
) => string

let execFileSyncStub: ExecFileSyncStub | null = null

export function __setExecFileSyncStubForTest(stub: ExecFileSyncStub | null): void {
  execFileSyncStub = stub
}

export function __resetExecFileSyncStubForTest(): void {
  execFileSyncStub = null
}

// =============================================================================
// Invocation id derivation (deterministic, clock-free)
// =============================================================================

/**
 * Deterministic invocation_id: sha256(prompt + host_kind + host_version +
 * workflow_run_seq).slice(0, 32). 32 hex chars = 128 bits of state, more
 * than sufficient for collision avoidance within a Workflow run.
 *
 * Replay rule (V2 §A11; codex pivot review fold #5): same inputs ⇒ same
 * id. The provenance event emitted by the executor (T-121) carries this id
 * so downstream observability can deduplicate replays + correlate to the
 * underlying response.
 */
function deriveInvocationId(
  prompt: string,
  host_kind: HostKind,
  host_version: string,
  workflow_run_seq: number,
): string {
  const hash = createHash('sha256')
  hash.update(`${prompt}\n${host_kind}\n${host_version}\n${workflow_run_seq}`)
  return hash.digest('hex').slice(0, 32)
}

// Re-exported via `_test_seams.ts` AND for direct unit tests of the
// derivation function. Pure function — no side effects.
export { deriveInvocationId as __deriveInvocationIdForTest }

// =============================================================================
// Raw host-LLM invocation (internal — wrapped via asActivity below)
// =============================================================================

/**
 * RAW host-LLM invocation. Spawns the host CLI subprocess, feeds the
 * prompt, captures stdout, returns a HostLLMResult.
 *
 * NOT exported on the public engine barrel (M7 P1.1 lesson — keep raw I/O
 * functions out of the production import surface; consumers must reach
 * the I/O via the asActivity-wrapped form below to preserve the M5 F-12
 * boundary).
 *
 * Dispatch shapes:
 *   - host='claude':
 *       execFileSync('claude', ['--bare', '--print', prompt], {timeout, encoding: 'utf-8'})
 *     `--bare` is REQUIRED for recursion safety (codex pivot review #3 —
 *     verified on Claude Code 2.1.123). `--print` (-p) prints the response
 *     and exits, suitable for pipes.
 *   - host='codex':
 *       execFileSync('codex', ['exec', '--skip-git-repo-check'], {input: prompt, timeout, encoding: 'utf-8'})
 *     `codex exec` reads the prompt from stdin via the `input` option.
 *     `--skip-git-repo-check` keeps the invocation independent of the
 *     caller's CWD (Sutra Workflows do not require git context for
 *     host-LLM dispatch).
 *
 * Failure handling:
 *   - Host unavailable: throws HostUnavailableError. The executor (T-120)
 *     synthesizes a step failure with `host_llm_unavailable:<host>`.
 *   - Subprocess non-zero exit: throws Error with the exit_code in the
 *     message. The executor synthesizes
 *     `host_llm_invocation_failed:<reason>`.
 *   - Subprocess timeout: same as non-zero exit (Node's execFileSync
 *     surfaces timeout via err.signal/err.status).
 */
export function invokeHostLLM(args: HostLLMInvokeArgs): HostLLMResult {
  // F-12 defense-in-depth (codex master review 2026-04-30 P1.1 fold).
  // The Activity wrapper enforces F-12 on `hostLLMActivity`; this guard
  // prevents direct callers of `invokeHostLLM` from inside Workflow context
  // even when Workflow code does a deep import of this module. Mirrors
  // the M7 P1.1 fix in `opa-evaluator.evaluate` — the public barrel does
  // NOT re-export `invokeHostLLM`, but a deep import from `./host-llm-activity.js`
  // would otherwise reach the raw subprocess seam without hitting the
  // workflow-context guard in `activity-wrapper.ts`. Tests that simulate
  // Workflow context inject `__setInvokeHostLLMF12ProbeForTest(() => true)`
  // and assert this throws BEFORE the subprocess stub runs.
  if (invokeHostLLMF12Probe()) {
    throw new Error(
      'F-12: opa/host LLM invocation in Workflow context. ' +
        'Use hostLLMActivity (asActivity-wrapped) via the dispatcher, ' +
        'not invokeHostLLM directly. ' +
        'See holding/plans/native-v1.0/M5-workflow-engine.md F-12.',
    )
  }

  const avail = getAvailability(args.host)
  if (!avail.available || avail.version === null) {
    throw new HostUnavailableError(args.host)
  }

  const timeout = args.timeout_ms ?? 60000
  const exec = execFileSyncStub ?? (execFileSync as unknown as ExecFileSyncStub)

  let response: string
  let exit_code = 0
  try {
    if (args.host === 'claude') {
      // Claude `--bare --print`: prompt as final positional arg.
      // `--bare` REQUIRED — see module comment "Why CLI shell-out".
      response = exec('claude', ['--bare', '--print', args.prompt], {
        timeout,
        encoding: 'utf-8',
      })
    } else {
      // codex exec: prompt via stdin (verified throughout this session via
      // codex consults — `codex exec --skip-git-repo-check` accepts prompt
      // through the `input` option of execFileSync).
      response = exec('codex', ['exec', '--skip-git-repo-check'], {
        input: args.prompt,
        timeout,
        encoding: 'utf-8',
      })
    }
  } catch (e) {
    const err = e as { status?: number; stderr?: string; message?: string }
    exit_code = typeof err.status === 'number' ? err.status : 1
    throw new Error(
      `Host LLM '${args.host}' invocation failed (exit ${exit_code}): ${err.message ?? 'unknown error'}`,
    )
  }

  const invocation_id = deriveInvocationId(
    args.prompt,
    args.host,
    avail.version,
    args.workflow_run_seq,
  )

  return {
    response,
    host_kind: args.host,
    host_version: avail.version,
    exit_code,
    invocation_id,
  }
}

// =============================================================================
// asActivity-wrapped public API (T-119)
// =============================================================================

/**
 * The Activity-wrapped form. THIS is the public host-LLM API.
 *
 * The wrapper preserves the M5 F-12 boundary: when called from a Workflow
 * context (i.e. inside a Temporal Workflow function), the wrapper throws
 * ForbiddenCouplingF12 BEFORE any subprocess spawns. Activities run on the
 * Worker (ordinary Node runtime) where the probe returns false and the
 * invocation proceeds.
 *
 * Step-graph-executor (T-120) dispatches via this for steps with
 * `action='invoke_host_llm'`. The result's `response` is wrapped in a
 * V2 §A11 DataRef envelope (`kind='host-llm-output'`) before being recorded
 * as the step's outputs[0]; provenance (T-121) emits a
 * `HOST_LLM_INVOCATION` OTel event with host_kind + host_version +
 * invocation_id + prompt_hash + response_hash.
 */
export const hostLLMActivity = asActivity(
  async (args: HostLLMInvokeArgs): Promise<HostLLMResult> => {
    return invokeHostLLM(args)
  },
)
