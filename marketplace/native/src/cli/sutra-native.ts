#!/usr/bin/env node
/**
 * sutra-native CLI — v1.1.1 entrypoint (daemon mode).
 *
 * Subcommands at v1.1.1:
 *   start      — fork a detached daemon child that runs NativeEngine until
 *                SIGTERM; parent acquires PID lock for the DAEMON pid +
 *                returns. Idempotent (lock contention → exit 1).
 *   stop       — read PID file, send SIGTERM to daemon, release lock.
 *   daemon     — INTERNAL: run NativeEngine in foreground until signal.
 *                Spawned by cmdStart; not for direct human use (but valid).
 *   status     — read PID file; report running | stopped | stale-lock
 *   version    — print version
 *   help       — print usage
 *
 * Exit codes:
 *   0 = success
 *   1 = lock contention (already running)
 *   2 = unknown subcommand / usage error
 *   3 = io error
 *
 * v1.1.1 fix: v1.1.0 cmdStart only acquired the PID lock + printed banner;
 * the engine never subscribed to H-Sutra log so "hello" went nowhere.
 * cmdStart now spawns a detached daemon child via child_process.spawn that
 * runs NativeEngine.start() until SIGTERM. PID lock records the DAEMON pid.
 */

import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, openSync, unlinkSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import {
  acquirePidLock,
  defaultPidPath,
  getStatus,
  readPidLock,
  releasePidLock,
  type StatusReport,
} from '../runtime/lifecycle.js'
import { NativeEngine } from '../runtime/native-engine.js'
import { createDomain } from '../primitives/domain.js'
import { createCharter } from '../primitives/charter.js'
import { createWorkflow } from '../primitives/workflow.js'
import { executeWorkflow } from '../runtime/lite-executor.js'
import {
  listCharters,
  listDomains,
  listWorkflows,
  loadWorkflow,
  persistCharter,
  persistDomain,
  persistTrigger,
  persistWorkflow,
} from '../persistence/user-kit.js'
import { formatEvent } from '../renderers/terminal-events.js'
import type { EngineEvent } from '../types/engine-event.js'
import type { StepAction, StepFailureAction, WorkflowStep } from '../types/index.js'
import {
  TRIGGER_EVENT_TYPES,
  type CadenceSpec,
  type Predicate,
  type TriggerEventType,
  type TriggerSpec,
} from '../types/trigger-spec.js'

const VERSION = '1.2.2'

interface CommandContext {
  readonly argv: ReadonlyArray<string>
  readonly env: NodeJS.ProcessEnv
  readonly stdout: (s: string) => void
  readonly stderr: (s: string) => void
}

export async function main(ctx: CommandContext): Promise<number> {
  const sub = ctx.argv[0] ?? 'help'

  // v1.2.1: main is async to allow `await cmdRun(...)` for invoke_host_llm
  // dispatch; sync subcommands auto-wrap in Promise.resolve when returned.
  switch (sub) {
    case 'start':
      return cmdStart(ctx)
    case 'stop':
      return cmdStop(ctx)
    case 'daemon':
      return cmdDaemon(ctx)
    case 'status':
      return cmdStatus(ctx)
    case 'create-domain':
      return cmdCreateDomain(ctx)
    case 'create-charter':
      return cmdCreateCharter(ctx)
    case 'create-workflow':
      return cmdCreateWorkflow(ctx)
    case 'create-trigger':
      return cmdCreateTrigger(ctx)
    case 'list':
      return cmdList(ctx)
    case 'run':
      return await cmdRun(ctx)
    case 'version':
    case '--version':
    case '-v':
      ctx.stdout(`${VERSION}\n`)
      return 0
    case 'help':
    case '--help':
    case '-h':
      ctx.stdout(usage())
      return 0
    default:
      ctx.stderr(`sutra-native: unknown subcommand "${sub}"\n\n${usage()}`)
      return 2
  }
}

// ============================================================================
// Founder-facing create / list / run subcommands (v1.1.2 — runtime kit)
// ============================================================================

/** Minimal --key value flag parser. argv[0] is the subcommand; flags follow. */
function parseFlags(argv: ReadonlyArray<string>): {
  positional: string[]
  flags: Record<string, string>
} {
  const positional: string[] = []
  const flags: Record<string, string> = {}
  for (let i = 1; i < argv.length; i++) {
    const tok = argv[i]!
    if (tok.startsWith('--')) {
      const key = tok.slice(2)
      const next = argv[i + 1]
      if (next === undefined || next.startsWith('--')) {
        flags[key] = 'true'
      } else {
        flags[key] = next
        i++
      }
    } else {
      positional.push(tok)
    }
  }
  return { positional, flags }
}

function require_(flags: Record<string, string>, key: string): string {
  const v = flags[key]
  if (v === undefined || v === '') {
    throw new Error(`--${key} is required`)
  }
  return v
}

function cmdCreateDomain(ctx: CommandContext): number {
  const { flags } = parseFlags(ctx.argv)
  try {
    const id = require_(flags, 'id')
    const name = require_(flags, 'name')
    const parent = flags['parent']
    const d = createDomain({
      id,
      name,
      parent_id: parent && parent !== 'none' ? parent : null,
      principles: [],
      intelligence: flags['intelligence'] ?? `${name} domain — created by founder.`,
      accountable: (flags['accountable'] ?? 'founder').split(',').map((s) => s.trim()),
      authority: flags['authority'] ?? `Decisions within ${name}.`,
      tenant_id: flags['tenant'] ?? 'T-default',
    })
    const path = persistDomain(d, { env: ctx.env })
    ctx.stdout(`+ Domain ${d.id} "${d.name}" created\n  persisted: ${path}\n`)
    return 0
  } catch (err) {
    ctx.stderr(`create-domain failed: ${err instanceof Error ? err.message : String(err)}\n`)
    return 2
  }
}

function cmdCreateCharter(ctx: CommandContext): number {
  const { flags } = parseFlags(ctx.argv)
  try {
    const id = require_(flags, 'id')
    const purpose = require_(flags, 'purpose')
    const domainId = flags['domain']
    const c = createCharter({
      id,
      purpose,
      scope_in: flags['scope-in'] ?? 'all_events',
      scope_out: flags['scope-out'] ?? 'none',
      obligations: [],
      invariants: [],
      success_metrics: flags['metrics'] ? flags['metrics']!.split(',').map((s) => s.trim()) : ['adherence ≥ 1/wk'],
      authority: flags['authority'] ?? 'Decisions within scope.',
      termination: flags['termination'] ?? 'Founder explicitly opts out.',
      constraints: [],
      acl: domainId
        ? [
            {
              domain_or_charter_id: domainId,
              access: 'append',
              reason: `${domainId} is the parent`,
            },
          ]
        : [],
    })
    const path = persistCharter(c, { env: ctx.env })
    ctx.stdout(
      `+ Charter ${c.id} created${domainId ? ` (under ${domainId})` : ''}\n  persisted: ${path}\n`,
    )
    return 0
  } catch (err) {
    ctx.stderr(`create-charter failed: ${err instanceof Error ? err.message : String(err)}\n`)
    return 2
  }
}

// v1.3.0 W1.7 (codex W1.7 fold): CLI now accepts 'invoke_host_llm' steps in
// addition to the v1.1.x trio. invoke_host_llm requires per-step --host-N
// (1-indexed), --prompt-N, and optionally --timeout-N flags. Other step
// actions ignore the per-step host/prompt/timeout flags.
const VALID_STEP_ACTIONS_CLI: ReadonlySet<StepAction> = new Set([
  'wait',
  'terminate',
  'spawn_sub_unit',
  'invoke_host_llm',
])

function cmdCreateWorkflow(ctx: CommandContext): number {
  const { flags } = parseFlags(ctx.argv)
  try {
    const id = require_(flags, 'id')
    const stepsRaw = require_(flags, 'steps')
    const stepNames = stepsRaw.split(',').map((s) => s.trim()).filter((s) => s.length > 0)
    if (stepNames.length === 0) {
      throw new Error('--steps must list at least one action (e.g. wait,terminate)')
    }
    const stepGraph: WorkflowStep[] = stepNames.map((name, idx) => {
      if (!VALID_STEP_ACTIONS_CLI.has(name as StepAction)) {
        throw new Error(
          `--steps[${idx}] "${name}" not one of: wait, terminate, spawn_sub_unit, invoke_host_llm`,
        )
      }
      const isLast = idx === stepNames.length - 1
      const onFailure: StepFailureAction = isLast ? 'abort' : 'continue'
      // v1.3.0 W1.7 (codex W1.7 fold): per-step --host-N / --prompt-N /
      // --timeout-N flags are 1-indexed by step position. Each
      // invoke_host_llm step REQUIRES its own --host-N + --prompt-N pair so
      // multi-step workflows can mix hosts (e.g. step 1 = claude, step 2 =
      // codex). Codex pivot review CHANGE #2 — the step contract for "what
      // does this step DO" must encode the host directly, not as a workflow-
      // wide global, so the CLI scaffolding mirrors the in-memory shape.
      if (name === 'invoke_host_llm') {
        const stepNum = idx + 1
        const hostFlag = `host-${stepNum}`
        const promptFlag = `prompt-${stepNum}`
        const timeoutFlag = `timeout-${stepNum}`
        const host = require_(flags, hostFlag)
        if (host !== 'claude' && host !== 'codex') {
          throw new Error(
            `--${hostFlag} must be 'claude' or 'codex'; got "${host}"`,
          )
        }
        const prompt = require_(flags, promptFlag)
        const step: WorkflowStep = {
          step_id: stepNum,
          action: 'invoke_host_llm',
          host: host as 'claude' | 'codex',
          inputs: [
            {
              kind: 'host-llm-prompt',
              schema_ref: 'prompt/v1',
              locator: prompt,
              version: '1.0.0',
              mutability: 'immutable',
              retention: 'permanent',
            },
          ],
          outputs: [],
          on_failure: onFailure,
        }
        const timeoutRaw = flags[timeoutFlag]
        if (timeoutRaw !== undefined && timeoutRaw !== 'true') {
          const timeout = Number(timeoutRaw)
          if (!Number.isInteger(timeout) || timeout <= 0) {
            throw new Error(
              `--${timeoutFlag} must be a positive integer (ms); got "${timeoutRaw}"`,
            )
          }
          step.timeout_ms = timeout
        }
        return step
      }
      return {
        step_id: idx + 1,
        action: name as StepAction,
        inputs: [],
        outputs: [],
        on_failure: onFailure,
      }
    })

    const w = createWorkflow({
      id,
      preconditions: flags['preconditions'] ?? 'always',
      step_graph: stepGraph,
      inputs: [],
      outputs: [],
      state: [],
      postconditions: flags['postconditions'] ?? 'completed',
      failure_policy: flags['failure-policy'] ?? 'continue',
      stringency: (flags['stringency'] as 'task' | 'process' | 'protocol' | undefined) ?? 'process',
      interfaces_with: [],
    })
    const path = persistWorkflow(w, { env: ctx.env })
    ctx.stdout(
      `+ Workflow ${w.id} created (${stepGraph.length} step${stepGraph.length === 1 ? '' : 's'}: ${stepNames.join(' → ')})\n  persisted: ${path}\n`,
    )
    return 0
  } catch (err) {
    ctx.stderr(`create-workflow failed: ${err instanceof Error ? err.message : String(err)}\n`)
    return 2
  }
}

/**
 * v1.3.0 W1.8 (codex W1.8 + W3 fold) — `sutra-native create-trigger`.
 *
 * Mints a TriggerSpec + persists to user-kit/triggers/<T-id>.json.
 *
 * Flags:
 *   --id <T-id>                                      required
 *   --workflow-id <W-id>                             required; verified
 *                                                     against the user-kit
 *                                                     via loadWorkflow
 *   --event-type <founder_input|cron|file_drop|webhook>
 *                                                     required; validated
 *                                                     against TRIGGER_EVENT_TYPES
 *   --match-all "<csv>" XOR --match-any "<csv>"       required when
 *                                                     event-type='founder_input';
 *                                                     mutually exclusive
 *   --cadence-spec <json-string>                      accepted for cron
 *                                                     (W3 fold; W1 just
 *                                                     persists, W3 wires)
 *   --charter-id <C-id>                              optional
 *   --domain-id <D-id>                               optional
 *   --description <text>                             optional
 *
 * Predicate construction (codex W1.8 fold):
 *   - founder_input + --match-all "kw1,kw2"  → AND of contains predicates
 *   - founder_input + --match-any "kw1,kw2"  → OR of contains predicates
 *   - cron                                    → always_true
 *
 * Errors exit 2 (usage error) or 3 (io error). codex W1.8 mandates
 * EXPLICIT errors for the validation paths (workflow not found, both
 * match flags set, neither match flag set).
 */
function cmdCreateTrigger(ctx: CommandContext): number {
  const { flags } = parseFlags(ctx.argv)
  try {
    const id = require_(flags, 'id')
    if (!id.startsWith('T-')) {
      throw new Error(`--id must match T-<slug> pattern; got "${id}"`)
    }
    const workflowId = require_(flags, 'workflow-id')
    const eventTypeRaw = require_(flags, 'event-type')
    if (!TRIGGER_EVENT_TYPES.has(eventTypeRaw as TriggerEventType)) {
      throw new Error(
        `--event-type must be one of: ${Array.from(TRIGGER_EVENT_TYPES).join('|')}; got "${eventTypeRaw}"`,
      )
    }
    const eventType = eventTypeRaw as TriggerEventType

    // Verify the target workflow exists. Codex W1.8 fold: --workflow-id
    // is REQUIRED + must reference a real workflow, otherwise the trigger
    // is a dangling reference at runtime.
    const target = loadWorkflow(workflowId, { env: ctx.env })
    if (!target) {
      throw new Error(
        `--workflow-id "${workflowId}" not found in user-kit (try: sutra-native list workflows)`,
      )
    }

    const matchAllRaw = flags['match-all']
    const matchAnyRaw = flags['match-any']
    const hasMatchAll = matchAllRaw !== undefined && matchAllRaw !== 'true'
    const hasMatchAny = matchAnyRaw !== undefined && matchAnyRaw !== 'true'
    // Codex W1.8 fold: XOR with EXPLICIT error messages for both fail
    // modes. Both set / neither set are distinct configuration mistakes
    // and surface different errors.
    if (hasMatchAll && hasMatchAny) {
      throw new Error(
        '--match-all and --match-any are mutually exclusive (pick one)',
      )
    }
    if (eventType === 'founder_input' && !hasMatchAll && !hasMatchAny) {
      throw new Error(
        'event-type=founder_input requires --match-all or --match-any (csv of keywords)',
      )
    }

    let predicate: Predicate
    if (hasMatchAll) {
      const kws = matchAllRaw!.split(',').map((s) => s.trim()).filter((s) => s.length > 0)
      if (kws.length === 0) {
        throw new Error('--match-all must list at least one keyword')
      }
      predicate = {
        type: 'and',
        clauses: kws.map((value) => ({ type: 'contains', value }) as Predicate),
      }
    } else if (hasMatchAny) {
      const kws = matchAnyRaw!.split(',').map((s) => s.trim()).filter((s) => s.length > 0)
      if (kws.length === 0) {
        throw new Error('--match-any must list at least one keyword')
      }
      predicate = {
        type: 'or',
        clauses: kws.map((value) => ({ type: 'contains', value }) as Predicate),
      }
    } else {
      // event-type !== founder_input + neither match flag set → always_true.
      // Cron triggers fire on cadence ticks, not predicate matches.
      predicate = { type: 'always_true' }
    }

    // Codex W3 fold: --cadence-spec accepted for cron triggers; persisted
    // verbatim. W3 wires CadenceScheduler.register-from-trigger; W1 just
    // ships the field so on-disk triggers are forward-compatible.
    let cadenceSpec: CadenceSpec | undefined
    const cadenceRaw = flags['cadence-spec']
    if (cadenceRaw !== undefined && cadenceRaw !== 'true') {
      let parsed: unknown
      try {
        parsed = JSON.parse(cadenceRaw)
      } catch {
        throw new Error(`--cadence-spec must be valid JSON; got "${cadenceRaw}"`)
      }
      if (typeof parsed !== 'object' || parsed === null) {
        throw new Error(`--cadence-spec must be a JSON object; got "${cadenceRaw}"`)
      }
      const kind = (parsed as { kind?: unknown }).kind
      if (
        kind !== 'every_n_minutes' &&
        kind !== 'every_n_hours' &&
        kind !== 'every_day_at' &&
        kind !== 'cron'
      ) {
        throw new Error(
          `--cadence-spec.kind must be every_n_minutes|every_n_hours|every_day_at|cron; got "${String(kind)}"`,
        )
      }
      cadenceSpec = parsed as CadenceSpec
    }

    const charterId = flags['charter-id']
    const domainId = flags['domain-id']
    const description = flags['description']

    const t: TriggerSpec = {
      id,
      event_type: eventType,
      route_predicate: predicate,
      target_workflow: workflowId,
      ...(domainId && domainId !== 'true' ? { domain_id: domainId } : {}),
      ...(charterId && charterId !== 'true' ? { charter_id: charterId } : {}),
      ...(description && description !== 'true' ? { description } : {}),
      ...(cadenceSpec ? { cadence_spec: cadenceSpec } : {}),
    }

    const path = persistTrigger(t, { env: ctx.env })
    ctx.stdout(
      `+ Trigger ${t.id} created (event_type=${t.event_type}, target=${workflowId}, predicate=${predicate.type})\n  persisted: ${path}\n`,
    )
    return 0
  } catch (err) {
    ctx.stderr(`create-trigger failed: ${err instanceof Error ? err.message : String(err)}\n`)
    return 2
  }
}

function cmdList(ctx: CommandContext): number {
  const { positional } = parseFlags(ctx.argv)
  const what = positional[0] ?? 'all'
  const opts = { env: ctx.env }
  try {
    const wantDomains = what === 'all' || what === 'domains'
    const wantCharters = what === 'all' || what === 'charters'
    const wantWorkflows = what === 'all' || what === 'workflows'

    if (!wantDomains && !wantCharters && !wantWorkflows) {
      ctx.stderr(`list: unknown target "${what}" (expected: domains|charters|workflows|all)\n`)
      return 2
    }

    const lines: string[] = []
    if (wantDomains) {
      const ds = listDomains(opts)
      lines.push(`DOMAINS (${ds.length}):`)
      if (ds.length === 0) lines.push('  (none — try: sutra-native create-domain --id D6 --name Health)')
      for (const d of ds) lines.push(`  ${d.id.padEnd(8)} ${d.name}`)
    }
    if (wantCharters) {
      const cs = listCharters(opts)
      lines.push(`CHARTERS (${cs.length}):`)
      if (cs.length === 0) lines.push('  (none)')
      for (const c of cs) {
        const parent = c.acl[0]?.domain_or_charter_id ?? '-'
        lines.push(`  ${c.id.padEnd(28)} under ${parent.padEnd(8)} ${c.purpose}`)
      }
    }
    if (wantWorkflows) {
      const ws = listWorkflows(opts)
      lines.push(`WORKFLOWS (${ws.length}):`)
      if (ws.length === 0) lines.push('  (none)')
      for (const w of ws) {
        const actions = w.step_graph.map((s) => s.action ?? s.skill_ref ?? '?').join('→')
        lines.push(`  ${w.id.padEnd(36)} ${w.step_graph.length} step  [${actions}]`)
      }
    }
    ctx.stdout(lines.join('\n') + '\n')
    return 0
  } catch (err) {
    ctx.stderr(`list failed: ${err instanceof Error ? err.message : String(err)}\n`)
    return 3
  }
}

async function cmdRun(ctx: CommandContext): Promise<number> {
  const { positional, flags } = parseFlags(ctx.argv)
  const wfId = positional[0]
  if (!wfId) {
    ctx.stderr('run: workflow id required (e.g. sutra-native run W-evening-checkin)\n')
    return 2
  }
  try {
    const wf = loadWorkflow(wfId, { env: ctx.env })
    if (!wf) {
      ctx.stderr(`run: workflow "${wfId}" not found in user-kit (try: sutra-native list workflows)\n`)
      return 3
    }
    const executionId = flags['execution-id'] ?? `E-${Date.now()}`
    // v1.2.1 codex P2 fold (DIRECTIVE 1777839055): forward a per-run sequence
    // so invocation_id derivation does not collapse across repeated CLI runs
    // (D-NS-26 contract). Founder may pin via --workflow-run-seq for replay
    // determinism; default = high-resolution clock so two consecutive runs
    // with the same prompt produce distinct invocation_ids.
    const seqFlag = flags['workflow-run-seq']
    const workflowRunSeq = seqFlag !== undefined ? Number(seqFlag) : Date.now()
    const events: EngineEvent[] = []
    const result = await executeWorkflow({
      workflow: wf,
      execution_id: executionId,
      workflow_run_seq: workflowRunSeq,
      emit: (e) => {
        events.push(e)
        ctx.stdout(formatEvent(e) + '\n')
      },
      on_host_llm_result: (r) => {
        ctx.stdout(`  host=${r.host_kind} v=${r.host_version} invocation=${r.invocation_id}\n`)
        ctx.stdout(`  response: ${r.response}\n`)
      },
    })
    ctx.stdout(
      `\n${result.status === 'success' ? 'OK' : 'FAIL'}: ${result.steps_completed} step(s) completed, ${result.steps_failed} failed, ${result.duration_ms}ms\n`,
    )
    return result.status === 'success' ? 0 : 1
  } catch (err) {
    ctx.stderr(`run failed: ${err instanceof Error ? err.message : String(err)}\n`)
    return 3
  }
}

/**
 * cmdDaemon — INTERNAL: run NativeEngine in foreground until SIGTERM.
 *
 * Spawned detached by cmdStart. Logs to ~/.sutra-native/native.log via
 * the inherited stdio pipe. SIGTERM/SIGINT trigger a clean shutdown.
 *
 * v1.1.1 fix per founder report 2026-05-03 (sutra-native start did not
 * actually run the engine; this is the missing wire).
 */
function cmdDaemon(ctx: CommandContext): number {
  const nativeHome = ctx.env.SUTRA_NATIVE_HOME ?? `${ctx.env.HOME}/.sutra-native`
  const readyPath = ctx.env.SUTRA_NATIVE_READY ?? `${nativeHome}/native.ready`
  const intakeLog = ctx.env.SUTRA_HSUTRA_LOG_PATH

  const engine = new NativeEngine({
    connector_options: intakeLog ? { log_path: intakeLog } : {},
    write: (line) => ctx.stdout(line + '\n'),
    on_error: (err) => ctx.stderr(`[native-engine] ${err.message}\n`),
  })

  ctx.stdout(`sutra-native daemon: starting (pid=${process.pid}, v=${VERSION})\n`)
  try {
    engine.start()
  } catch (err) {
    ctx.stderr(`sutra-native daemon: engine.start failed: ${err instanceof Error ? err.message : String(err)}\n`)
    return 3
  }
  ctx.stdout(
    `sutra-native daemon: subscribed (intake_log=${intakeLog ?? 'default cwd resolution'})\n`,
  )

  // Codex P1 fold 2026-05-03 (DIRECTIVE-ID: 1777802035): write a readiness
  // marker so the parent cmdStart can detect successful initialization
  // (vs spawning a doomed child). Parent polls existsSync(readyPath); we
  // own writing it. Removed in shutdown() so a fresh start can re-detect.
  try {
    mkdirSync(dirname(readyPath), { recursive: true })
    writeFileSync(readyPath, JSON.stringify({ pid: process.pid, ts_ms: Date.now() }))
  } catch (err) {
    ctx.stderr(`sutra-native daemon: failed to write ready marker at ${readyPath}: ${err instanceof Error ? err.message : String(err)}\n`)
    return 3
  }

  const shutdown = (signal: string) => {
    ctx.stdout(`sutra-native daemon: received ${signal}; tearing down\n`)
    try { engine.stop() } catch { /* best-effort */ }
    try { if (existsSync(readyPath)) unlinkSync(readyPath) } catch { /* best-effort */ }
    process.exit(0)
  }
  process.on('SIGTERM', () => shutdown('SIGTERM'))
  process.on('SIGINT', () => shutdown('SIGINT'))

  // Codex P1 fold 2026-05-03: REFERENCED setInterval (NOT .unref()) so the
  // event loop does NOT exit. Without this, fs.watch persistent:false in
  // the connector lets the loop empty + Node implicitly exits the daemon
  // microseconds after engine.start returns. This timer holds the loop
  // open until SIGTERM/SIGINT calls process.exit.
  setInterval(() => {}, 60_000)

  // Unreachable under normal operation (signal handlers exit). Return 0
  // for type completeness.
  return 0
}

/**
 * cmdStop — v1.1.1 daemon mode: send SIGTERM to recorded daemon pid,
 * then release the lock. Falls back to force-release if the daemon is
 * already gone (crash recovery).
 */
function cmdStop(ctx: CommandContext): number {
  const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath()
  const state = readPidLock(pidPath)
  if (!state) {
    ctx.stdout('sutra-native: not running (no PID file)\n')
    return 0
  }

  // Try to terminate the daemon process.
  let signaled = false
  try {
    process.kill(state.pid, 'SIGTERM')
    signaled = true
  } catch {
    // Process already gone — fine, just clean up the lock.
  }

  releasePidLock(pidPath, { force: true })
  const after = readPidLock(pidPath)
  if (after) {
    ctx.stderr(`sutra-native: failed to release lock at ${pidPath} (io error)\n`)
    return 1
  }
  ctx.stdout(
    `sutra-native: stopped (${signaled ? 'SIGTERM sent + ' : ''}released lock pid=${state.pid})\n`,
  )
  return 0
}

/**
 * detectHostKind — classify the runtime context that invoked sutra-native.
 *
 * Returns 'claude-code' when the process is running inside a Claude Code
 * session, 'cli' otherwise. Used as telemetry provenance, not a trust
 * boundary — callers MUST NOT make security decisions on the result.
 *
 * Detection signals (in priority order):
 *   1. CLAUDECODE === '1' — documented Claude Code env flag (v2.x+).
 *      Verified via `env | grep CLAUDE` inside Claude Code Bash tool calls.
 *   2. CLAUDE_SESSION_ID — legacy fallback. Was the v1.1.0-1.1.2 detector
 *      but Claude Code does NOT actually export this var to Bash tool calls
 *      (verified Claude Code v2.1.126); kept for forward compatibility in
 *      case the harness starts setting it, or for hooks/slash invocations
 *      that explicitly inject it.
 *
 * Codex consult 2026-05-03: defer codex-cli host detection to a separate
 * patch — CODEX_HOME / OPENAI_API_KEY are weak, non-canonical signals.
 */
export function detectHostKind(env: NodeJS.ProcessEnv): 'claude-code' | 'cli' {
  if (env.CLAUDECODE === '1') return 'claude-code'
  if (env.CLAUDE_SESSION_ID) return 'claude-code'
  return 'cli'
}

/**
 * cmdStart — v1.1.1 daemon mode: spawn detached child running the engine.
 *
 * The child runs `sutra-native daemon` which calls NativeEngine.start()
 * + blocks until signaled. Parent records the CHILD pid in the lock file
 * so cmdStop can later kill the right process.
 *
 * Stdout/stderr of the child are appended to ~/.sutra-native/native.log
 * so the founder can tail it for telemetry without polluting the Claude
 * Code session output.
 */
function cmdStart(ctx: CommandContext): number {
  const hostKind = detectHostKind(ctx.env)
  const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath()
  const nativeHome = ctx.env.SUTRA_NATIVE_HOME ?? `${ctx.env.HOME}/.sutra-native`
  const logPath = `${nativeHome}/native.log`
  const readyPath = ctx.env.SUTRA_NATIVE_READY ?? `${nativeHome}/native.ready`

  // Pre-flight: refuse early if a live lock already holds (avoids spawning
  // a doomed child that fights for the lock). Stale locks (process gone)
  // are reaped + the start proceeds.
  const existingLock = readPidLock(pidPath)
  if (existingLock) {
    try {
      process.kill(existingLock.pid, 0)
      const ageMin = Math.round((Date.now() - existingLock.started_at_ms) / 60000)
      ctx.stderr(
        `sutra-native: already running (pid=${existingLock.pid}, host=${existingLock.host_kind}, started ${ageMin}m ago)\n` +
          `  PID file: ${pidPath}\n` +
          `  To stop: sutra-native stop\n`,
      )
      return 1
    } catch {
      // Stale — release before re-acquiring
      releasePidLock(pidPath, { force: true })
    }
  }

  // Clear any stale ready marker so the poll below only succeeds on a
  // genuinely fresh daemon start.
  try {
    if (existsSync(readyPath)) unlinkSync(readyPath)
  } catch {
    // best-effort
  }

  const nodeBin = process.execPath
  const selfPath = resolve(process.argv[1] ?? __filename)

  try {
    mkdirSync(nativeHome, { recursive: true })
  } catch {
    // best-effort
  }

  // Codex P1 fold 2026-05-03 (DIRECTIVE-ID: 1777802035): use Node's openSync
  // in append mode + spawn directly (no bash -c). Cleaner than shell
  // redirection + portable.
  let logFd: number
  try {
    logFd = openSync(logPath, 'a')
  } catch (err) {
    ctx.stderr(`sutra-native: failed to open log ${logPath}: ${err instanceof Error ? err.message : String(err)}\n`)
    return 3
  }

  const child = spawn(nodeBin, [selfPath, 'daemon'], {
    detached: true,
    stdio: ['ignore', logFd, logFd],
    env: {
      ...process.env,
      SUTRA_NATIVE_PID: pidPath,
      SUTRA_NATIVE_HOME: nativeHome,
      SUTRA_NATIVE_READY: readyPath,
    },
  })

  if (typeof child.pid !== 'number') {
    ctx.stderr('sutra-native: failed to spawn daemon child\n')
    return 3
  }

  child.unref()

  // Parent owns the PID file (the LOCK).
  const state = {
    pid: child.pid,
    started_at_ms: Date.now(),
    host_kind: hostKind,
  }
  try {
    mkdirSync(dirname(pidPath), { recursive: true })
    writeFileSync(pidPath, JSON.stringify(state, null, 2), { flag: 'w' })
  } catch (err) {
    ctx.stderr(`sutra-native: spawned daemon (pid=${child.pid}) but failed to write PID file: ${err instanceof Error ? err.message : String(err)}\n`)
    return 3
  }

  // Codex P1 fold 2026-05-03: poll for readiness marker (the daemon writes
  // it once engine.start succeeds). 50ms cadence × 100 = 5s timeout.
  const startupTimeoutMs = parseInt(ctx.env.SUTRA_NATIVE_STARTUP_TIMEOUT_MS ?? '5000', 10)
  const pollIntervalMs = 50
  const maxPolls = Math.ceil(startupTimeoutMs / pollIntervalMs)
  let ready = false
  for (let i = 0; i < maxPolls; i++) {
    if (existsSync(readyPath)) {
      ready = true
      break
    }
    // Also check the child hasn't already died
    try {
      process.kill(child.pid, 0)
    } catch {
      ctx.stderr(`sutra-native: daemon child died during startup (pid=${child.pid}). See ${logPath}\n`)
      releasePidLock(pidPath, { force: true })
      return 3
    }
    // Sync sleep via Atomics.wait on a tiny SharedArrayBuffer would be cleanest
    // but adds complexity; busy-poll a date check is sufficient at 50ms.
    const target = Date.now() + pollIntervalMs
    while (Date.now() < target) { /* busy wait */ }
  }

  if (!ready) {
    ctx.stderr(`sutra-native: daemon did not signal ready within ${startupTimeoutMs}ms. Killing pid=${child.pid}. See ${logPath}\n`)
    try { process.kill(child.pid, 'SIGTERM') } catch { /* */ }
    releasePidLock(pidPath, { force: true })
    return 3
  }

  // Suppress unused-import warning — acquirePidLock kept for callers that
  // may want the older single-step behavior.
  void acquirePidLock

  ctx.stdout(formatBanner(hostKind, pidPath, child.pid, logPath))
  return 0
}

function cmdStatus(ctx: CommandContext): number {
  const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath()
  const report = getStatus(pidPath)
  ctx.stdout(formatStatus(report, pidPath))
  return 0
}

function formatBanner(hostKind: string, pidPath: string, daemonPid?: number, logPath?: string): string {
  const pidLine = daemonPid !== undefined
    ? `│ ✓ Activated  v=${VERSION}  host=${hostKind.padEnd(11)}  daemon_pid=${daemonPid}    │`
    : `│ ✓ Activated  v=${VERSION}  host=${hostKind.padEnd(11)}  pid=${process.pid}        │`
  return [
    '┌─ SUTRA-NATIVE ──────────────────────────────────────────────┐',
    pidLine,
    `│ PID file:  ${pidPath.slice(0, 50).padEnd(50)} │`,
    logPath
      ? `│ Log:       ${logPath.slice(0, 50).padEnd(50)} │`
      : '│ Daemon:    runtime-active engine subscribed                  │',
    '│ Surfaces:  /start-native (slash) · sutra-native (CLI)        │',
    '└──────────────────────────────────────────────────────────────┘',
    '',
    'Next: founder input flows through Sutra Core H-Sutra layer →',
    '      Native engine routes via TriggerSpec → executes Workflow.',
    '',
  ].join('\n')
}

function formatStatus(r: StatusReport, pidPath: string): string {
  if (!r.running && !r.stale_lock) {
    return [
      'sutra-native: stopped',
      `  PID file: ${pidPath} (absent)`,
      `  Version: ${VERSION}`,
      '',
    ].join('\n')
  }
  if (r.stale_lock) {
    return [
      'sutra-native: STALE LOCK',
      `  PID file: ${pidPath}`,
      `  Recorded pid: ${r.pid} (process gone — lock will be reaped on next start)`,
      `  Version: ${VERSION}`,
      '',
    ].join('\n')
  }
  const uptimeMin = Math.round((r.uptime_ms ?? 0) / 60000)
  return [
    'sutra-native: running',
    `  pid:        ${r.pid}`,
    `  host:       ${r.host_kind}`,
    `  started:    ${r.started_at_ms ? new Date(r.started_at_ms).toISOString() : '?'}`,
    `  uptime:     ${uptimeMin}m`,
    `  PID file:   ${pidPath}`,
    `  Version:    ${VERSION}`,
    '',
  ].join('\n')
}

function usage(): string {
  return [
    'sutra-native — Native productization CLI (v' + VERSION + ')',
    '',
    'Usage:',
    '  sutra-native <subcommand> [options]',
    '',
    'Lifecycle:',
    '  start              Activate Native (acquire PID lock, print banner)',
    '  stop               Deactivate Native (release PID lock)',
    '  status             Report current activation state',
    '  version            Print version',
    '  help               Print this usage',
    '',
    'Runtime kit (founder-facing — v1.1.2+):',
    '  create-domain --id <D-id> --name <name> [--parent <id>] [--accountable <csv>]',
    '                     [--authority <text>] [--intelligence <text>]',
    '                     Mint + persist a Domain in the user-kit.',
    '  create-charter --id <C-id> --purpose <text> [--domain <D-id>]',
    '                     [--scope-in <pred>] [--scope-out <pred>]',
    '                     [--metrics <csv>] [--authority <text>] [--termination <text>]',
    '                     Mint + persist a Charter; --domain links it under a Domain.',
    '  create-workflow --id <W-id> --steps <action[,action...]>',
    '                     [--preconditions <text>] [--postconditions <text>]',
    '                     [--stringency task|process|protocol]',
    '                     [--failure-policy continue|abort]',
    '                     CLI step actions: wait | terminate | spawn_sub_unit | invoke_host_llm',
    '                     For each invoke_host_llm step at position N (1-indexed):',
    '                       --host-N <claude|codex>     required',
    '                       --prompt-N <text>           required',
    '                       --timeout-N <ms>            optional (positive integer)',
    '  create-trigger --id <T-id> --workflow-id <W-id> --event-type <type>',
    '                     [--match-all "<csv>" | --match-any "<csv>"]',
    '                     [--cadence-spec <json>] [--charter-id <C-id>]',
    '                     [--domain-id <D-id>] [--description <text>]',
    '                     event-type: founder_input|cron|file_drop|webhook',
    '                     founder_input requires --match-all XOR --match-any.',
    '                     cron accepts --cadence-spec (W1.8 + W3 fold).',
    '  list [domains|charters|workflows|all]',
    '                     Show what is in the user-kit.',
    '  run <W-id> [--execution-id <E-id>]',
    '                     Load a persisted Workflow + run via LiteExecutor.',
    '                     Each EngineEvent prints one line on stdout.',
    '',
    'Environment:',
    '  SUTRA_NATIVE_HOME  Base dir (default: ~/.sutra-native; user-kit at $HOME/user-kit/)',
    '  SUTRA_NATIVE_PID   Override PID file path entirely',
    '  CLAUDECODE         Set to "1" by Claude Code v2.x; flips host_kind=claude-code',
    '  CLAUDE_SESSION_ID  Legacy fallback (pre-v1.1.3); same effect when set',
    '',
    'See: holding/plans/native-productization-v1.0/SPEC.md',
    '',
  ].join('\n')
}

export {
  cmdStart,
  cmdStatus,
  cmdCreateDomain,
  cmdCreateCharter,
  cmdCreateWorkflow,
  cmdCreateTrigger,
  cmdList,
  cmdRun,
  formatBanner,
  formatStatus,
  usage,
}

// Auto-execute when called as bin (not when imported as a module).
// Detection: process.argv[1] resolves to this file or the .js dist twin.
const isMain =
  process.argv[1] !== undefined &&
  (process.argv[1].endsWith('sutra-native.js') ||
    process.argv[1].endsWith('sutra-native.ts') ||
    process.argv[1].endsWith('/sutra-native'))

if (isMain) {
  const sub = process.argv[2]
  // v1.2.1: main() is async to support invoke_host_llm dispatch through
  // cmdRun → executeWorkflow → hostLLMActivity. Bootstrap awaits via .then.
  main({
    argv: process.argv.slice(2),
    env: process.env,
    stdout: (s) => process.stdout.write(s),
    stderr: (s) => process.stderr.write(s),
  })
    .then((exitCode) => {
      // Codex P1 fold 2026-05-03 (DIRECTIVE-ID: 1777802035): for the `daemon`
      // subcommand, cmdDaemon installs SIGTERM/SIGINT handlers + a referenced
      // setInterval that keeps the event loop alive. Calling process.exit here
      // would kill the daemon microseconds after engine.start. Skip exit for
      // daemon mode; let the signal handlers control teardown.
      if (sub !== 'daemon') {
        process.exit(exitCode)
      }
      // For daemon mode: function returns; event loop stays alive via the
      // ref'd timer in cmdDaemon. process.exit fires from SIGTERM handler.
    })
    .catch((err: unknown) => {
      process.stderr.write(`sutra-native: fatal: ${err instanceof Error ? err.message : String(err)}\n`)
      process.exit(99)
    })
}
