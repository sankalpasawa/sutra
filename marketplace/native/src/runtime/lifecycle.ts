/**
 * lifecycle — D4 SKELETON activation contract (PID file + lock + status).
 *
 * Native runs as a subprocess of either:
 *   - Claude Code session (via `/start-native` slash command → exec sutra-native start)
 *   - Plain shell (sutra-native start)
 *
 * v1.0 lifecycle is foreground: `start` acquires a PID lock, prints the
 * activation banner, then exits (the actual H-Sutra subscriber + router
 * land in D2 and run inside the same process or a forked daemon — TBD
 * during D2). PID lock prevents two concurrent activations from the same
 * tenant.
 *
 * v1.1 will move the long-running watcher into a forked daemon and the
 * lifecycle module gains daemonize() + reapStaleLock() helpers.
 *
 * PID file location:
 *   $SUTRA_NATIVE_HOME/native.pid          (default: ~/.sutra-native/)
 *
 * Lock semantics:
 *   - Atomic create via { flag: 'wx' } (fails if file exists)
 *   - Stale lock detection via kill(pid, 0) — if process gone, reap + retake
 *   - File contents: JSON { pid, started_at_ms, host_kind }
 *
 * Codex master review (D4) gates promotion to v1.1 daemon mode.
 */

import { writeFileSync, readFileSync, existsSync, unlinkSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, dirname } from 'node:path'

export interface PidLockState {
  readonly pid: number
  readonly started_at_ms: number
  readonly host_kind: string
}

export interface AcquireResult {
  readonly acquired: boolean
  readonly reason?: 'lock_held_alive' | 'io_error'
  readonly existing?: PidLockState
}

export function defaultPidPath(): string {
  const home = process.env.SUTRA_NATIVE_HOME ?? join(homedir(), '.sutra-native')
  return join(home, 'native.pid')
}

/**
 * Atomically write the PID file. Fails (acquired=false) if a live process
 * already holds the lock. If the existing PID is stale (process gone), the
 * stale file is reaped and the lock is retaken.
 */
export function acquirePidLock(
  pidPath: string = defaultPidPath(),
  hostKind: string = 'cli',
): AcquireResult {
  ensureDir(pidPath)

  if (existsSync(pidPath)) {
    const existing = readPidLock(pidPath)
    if (existing && isAlive(existing.pid)) {
      return { acquired: false, reason: 'lock_held_alive', existing }
    }
    // Stale lock — reap.
    try {
      unlinkSync(pidPath)
    } catch {
      return { acquired: false, reason: 'io_error' }
    }
  }

  const state: PidLockState = {
    pid: process.pid,
    started_at_ms: Date.now(),
    host_kind: hostKind,
  }

  try {
    writeFileSync(pidPath, JSON.stringify(state, null, 2), { flag: 'wx' })
    return { acquired: true }
  } catch {
    // Race lost between existsSync + writeFileSync. Re-check.
    const racer = readPidLock(pidPath)
    if (racer && isAlive(racer.pid)) {
      return { acquired: false, reason: 'lock_held_alive', existing: racer }
    }
    return { acquired: false, reason: 'io_error' }
  }
}

/**
 * Release the lock at the given path.
 *
 * Default behavior: only release if this process owns the lock (pid match).
 * This protects against accidental cross-process release in a future v1.1
 * daemon mode where multiple processes might coexist.
 *
 * `force: true` releases REGARDLESS of pid ownership. Required for v1.0
 * foreground mode where `start` exits immediately (lock pid is dead by the
 * time `stop` runs). Codex master review 2026-05-03 caught the missing force
 * path — `cmdStop` now uses `force: true`.
 */
export function releasePidLock(
  pidPath: string = defaultPidPath(),
  opts: { force?: boolean } = {},
): void {
  if (!existsSync(pidPath)) return
  if (!opts.force) {
    const state = readPidLock(pidPath)
    if (state && state.pid !== process.pid) {
      // Don't release someone else's lock unless force=true.
      return
    }
  }
  try {
    unlinkSync(pidPath)
  } catch {
    // Best-effort cleanup; not fatal.
  }
}

export function readPidLock(pidPath: string = defaultPidPath()): PidLockState | null {
  if (!existsSync(pidPath)) return null
  try {
    const raw = readFileSync(pidPath, 'utf8')
    const parsed = JSON.parse(raw) as Partial<PidLockState>
    if (
      typeof parsed.pid === 'number' &&
      typeof parsed.started_at_ms === 'number' &&
      typeof parsed.host_kind === 'string'
    ) {
      return parsed as PidLockState
    }
    return null
  } catch {
    return null
  }
}

export interface StatusReport {
  readonly running: boolean
  readonly pid: number | null
  readonly started_at_ms: number | null
  readonly host_kind: string | null
  readonly uptime_ms: number | null
  readonly stale_lock: boolean
}

export function getStatus(pidPath: string = defaultPidPath()): StatusReport {
  const state = readPidLock(pidPath)
  if (!state) {
    return {
      running: false,
      pid: null,
      started_at_ms: null,
      host_kind: null,
      uptime_ms: null,
      stale_lock: false,
    }
  }
  const alive = isAlive(state.pid)
  return {
    running: alive,
    pid: state.pid,
    started_at_ms: state.started_at_ms,
    host_kind: state.host_kind,
    uptime_ms: alive ? Date.now() - state.started_at_ms : null,
    stale_lock: !alive,
  }
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code
    // ESRCH = process gone. EPERM = exists but not ours (still alive).
    return code === 'EPERM'
  }
}

function ensureDir(filePath: string): void {
  const dir = dirname(filePath)
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true })
  }
}
