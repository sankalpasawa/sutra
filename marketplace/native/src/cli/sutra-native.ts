#!/usr/bin/env node
/**
 * sutra-native CLI — D4 SKELETON entrypoint.
 *
 * Subcommands at v1.0 (D4 SKELETON):
 *   start      — acquire PID lock + print activation banner (foreground exit;
 *                D2 will fold the H-Sutra subscriber + router into the same
 *                process or fork a daemon)
 *   status     — read PID file; report running | stopped | stale-lock
 *   version    — print version from package.json
 *   help       — print usage
 *
 * Exit codes:
 *   0 = success
 *   1 = lock contention (already running)
 *   2 = unknown subcommand / usage error
 *   3 = io error
 *
 * Per founder direction 2026-05-02: when "start Native" fires, both the
 * slash command (/start-native) and the CLI (sutra-native start) execute
 * the same activation path. Slash command lives at
 * .claude-plugin/commands/start-native.md.
 *
 * Per codex master review cadence (post-D4 wiring): this file's PID/lock +
 * banner contract is gated by a master review before D2 begins.
 */

import {
  acquirePidLock,
  defaultPidPath,
  getStatus,
  readPidLock,
  releasePidLock,
  type StatusReport,
} from '../runtime/lifecycle.js'

const VERSION = '1.0.2'

interface CommandContext {
  readonly argv: ReadonlyArray<string>
  readonly env: NodeJS.ProcessEnv
  readonly stdout: (s: string) => void
  readonly stderr: (s: string) => void
}

export function main(ctx: CommandContext): number {
  const sub = ctx.argv[0] ?? 'help'

  switch (sub) {
    case 'start':
      return cmdStart(ctx)
    case 'stop':
      return cmdStop(ctx)
    case 'status':
      return cmdStatus(ctx)
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

function cmdStop(ctx: CommandContext): number {
  const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath()
  const state = readPidLock(pidPath)
  if (!state) {
    ctx.stdout('sutra-native: not running (no PID file)\n')
    return 0
  }
  // v1.0 foreground mode: `start` exits immediately so the recorded pid is
  // dead by the time `stop` runs. Use force=true to release regardless of
  // pid ownership — the lock is the activation marker, not a process-resource
  // claim. v1.1 daemon mode will use `kill -TERM` first, then release on
  // confirmed teardown. Codex master review 2026-05-03.
  releasePidLock(pidPath, { force: true })
  const after = readPidLock(pidPath)
  if (after) {
    ctx.stderr(
      `sutra-native: failed to release lock at ${pidPath} (io error)\n`,
    )
    return 1
  }
  ctx.stdout(`sutra-native: stopped (released lock pid=${state.pid})\n`)
  return 0
}

function cmdStart(ctx: CommandContext): number {
  const hostKind = ctx.env.CLAUDE_SESSION_ID ? 'claude-code' : 'cli'
  const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath()

  const result = acquirePidLock(pidPath, hostKind)

  if (!result.acquired) {
    if (result.reason === 'lock_held_alive' && result.existing) {
      const ageMin = Math.round((Date.now() - result.existing.started_at_ms) / 60000)
      ctx.stderr(
        `sutra-native: already running (pid=${result.existing.pid}, host=${result.existing.host_kind}, started ${ageMin}m ago)\n` +
          `  PID file: ${pidPath}\n` +
          `  To stop: kill ${result.existing.pid}\n`,
      )
      return 1
    }
    ctx.stderr(`sutra-native: failed to acquire lock (reason=${result.reason ?? 'unknown'})\n`)
    return 3
  }

  ctx.stdout(formatBanner(hostKind, pidPath))

  return 0
}

function cmdStatus(ctx: CommandContext): number {
  const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath()
  const report = getStatus(pidPath)
  ctx.stdout(formatStatus(report, pidPath))
  return 0
}

function formatBanner(hostKind: string, pidPath: string): string {
  return [
    '┌─ SUTRA-NATIVE ──────────────────────────────────────────────┐',
    `│ ✓ Activated  v=${VERSION}  host=${hostKind.padEnd(11)}  pid=${process.pid}        │`,
    `│ PID file:  ${pidPath.slice(0, 50).padEnd(50)} │`,
    '│ Daemon:    stub (D4 SKELETON) — H-Sutra subscriber + router │',
    '│            land in D2 vertical slice                         │',
    '│ Surfaces:  /start-native  (slash) · sutra-native (CLI)       │',
    '└──────────────────────────────────────────────────────────────┘',
    '',
    'Next: any founder input flows through Sutra Core H-Sutra layer →',
    '      Native consumes the classified-input event downstream.',
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
    'Subcommands:',
    '  start      Activate Native (acquire PID lock, print banner)',
    '  stop       Deactivate Native (release PID lock)',
    '  status     Report current activation state',
    '  version    Print version',
    '  help       Print this usage',
    '',
    'Environment:',
    '  SUTRA_NATIVE_HOME  Base dir for PID file (default: ~/.sutra-native)',
    '  SUTRA_NATIVE_PID   Override PID file path entirely',
    '  CLAUDE_SESSION_ID  Auto-set when invoked from /start-native slash',
    '',
    'See: holding/plans/native-productization-v1.0/SPEC.md',
    '',
  ].join('\n')
}

export { cmdStart, cmdStatus, formatBanner, formatStatus, usage }

// Auto-execute when called as bin (not when imported as a module).
// Detection: process.argv[1] resolves to this file or the .js dist twin.
const isMain =
  process.argv[1] !== undefined &&
  (process.argv[1].endsWith('sutra-native.js') ||
    process.argv[1].endsWith('sutra-native.ts') ||
    process.argv[1].endsWith('/sutra-native'))

if (isMain) {
  const exitCode = main({
    argv: process.argv.slice(2),
    env: process.env,
    stdout: (s) => process.stdout.write(s),
    stderr: (s) => process.stderr.write(s),
  })
  // NOTE: do NOT release the lock on process exit. At v1.0 the lock is the
  // activation marker — `start` returns after acquiring + announcing it; the
  // lock persists across the foreground exit so `status` continues to report
  // running. Use `sutra-native stop` to release explicitly. Stale-lock
  // detection on the next `start` reaps abandoned locks (crash recovery).
  // Codex master review 2026-05-03 caught the prior auto-release bug.
  process.exit(exitCode)
}
