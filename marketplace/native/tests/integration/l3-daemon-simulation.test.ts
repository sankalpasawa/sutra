/**
 * L3 daemon-simulation harness — codex-converged design
 * (2026-05-03, DIRECTIVE-ID 1777802035).
 *
 * Spawns the REAL `bin/sutra-native start` as a child process; tails the
 * daemon log file by byte-offset polling; asserts routing + workflow lines
 * appear after a simulated H-Sutra row is written. Catches the bug class
 * that L1+L2 missed (cmdStart→engine wiring, PID lock plumbing, signal
 * handling — the actual "did the daemon stay alive" question).
 *
 * Test isolation:
 *   - Each test gets a fresh tmpdir
 *   - SUTRA_NATIVE_HOME, SUTRA_NATIVE_PID, SUTRA_NATIVE_READY,
 *     SUTRA_HSUTRA_LOG_PATH all point into tmpdir
 *   - cwd = tmpdir
 *   - Daemon teardown: SIGTERM → 2s grace → SIGKILL fallback
 *
 * Gating: skipped by default; opt in via RUN_DAEMON_TESTS=1.
 *   npm run test:daemon (separate script — see package.json)
 *
 * Per codex: "L3 catches cmdStart→engine wiring (the v1.1.0 bug); does NOT
 * catch Claude Code hook-runner behavior (L4) or packaged-install drift."
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { spawn, type ChildProcess } from 'node:child_process'
import {
  appendFileSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'

// Path to the bin/sutra-native shim — committed in repo
const NATIVE_BIN = resolve(
  __dirname,
  '..',
  '..',
  'bin',
  'sutra-native',
)

interface DaemonSession {
  pid: number
  logPath: string
  awaitLine: (pattern: RegExp, timeoutMs?: number) => Promise<string>
  sendFounderInput: (input_text: string, turn_id?: string) => void
  stop: () => Promise<void>
}

interface StartOptions {
  tmpdir: string
  hsutraLogPath: string
  startupTimeoutMs?: number
  defaultAwaitTimeoutMs?: number
}

async function startDaemonForTest(opts: StartOptions): Promise<DaemonSession> {
  const startupTimeoutMs = opts.startupTimeoutMs ?? 8000
  const defaultAwaitMs = opts.defaultAwaitTimeoutMs ?? 5000

  const pidPath = join(opts.tmpdir, 'native.pid')
  const readyPath = join(opts.tmpdir, 'native.ready')
  const logPath = join(opts.tmpdir, 'native.log')

  // Ensure h-sutra log file exists so the connector can subscribe
  if (!existsSync(opts.hsutraLogPath)) {
    writeFileSync(opts.hsutraLogPath, '')
  }

  const child = spawn(NATIVE_BIN, ['start'], {
    cwd: opts.tmpdir,
    env: {
      ...process.env,
      SUTRA_NATIVE_HOME: opts.tmpdir,
      SUTRA_NATIVE_PID: pidPath,
      SUTRA_NATIVE_READY: readyPath,
      SUTRA_HSUTRA_LOG_PATH: opts.hsutraLogPath,
      SUTRA_NATIVE_STARTUP_TIMEOUT_MS: String(startupTimeoutMs),
      // Suppress claude-session affinity — this is a test, not a Claude Code
      // session
      CLAUDE_SESSION_ID: '',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  let parentStdout = ''
  let parentStderr = ''
  child.stdout?.on('data', (chunk) => { parentStdout += String(chunk) })
  child.stderr?.on('data', (chunk) => { parentStderr += String(chunk) })

  // Wait for the parent CLI process to exit (it returns after readiness)
  const parentExit: number = await new Promise((res) => {
    child.on('exit', (code) => res(code ?? -1))
  })

  if (parentExit !== 0) {
    throw new Error(
      `sutra-native start exited ${parentExit}\n` +
        `stdout: ${parentStdout}\n` +
        `stderr: ${parentStderr}\n` +
        (existsSync(logPath) ? `log:\n${readFileSync(logPath, 'utf8')}` : 'no log'),
    )
  }

  if (!existsSync(pidPath)) {
    throw new Error(`pid file ${pidPath} not written`)
  }

  const lockState = JSON.parse(readFileSync(pidPath, 'utf8'))
  const daemonPid = lockState.pid as number

  // Verify daemon is actually alive
  try {
    process.kill(daemonPid, 0)
  } catch {
    throw new Error(
      `daemon pid ${daemonPid} not alive after start. log:\n${
        existsSync(logPath) ? readFileSync(logPath, 'utf8') : '(no log)'
      }`,
    )
  }

  // ── awaitLine: byte-offset polling tail ─────────────────────────────
  let lastOffset = 0
  let buffer = ''

  async function awaitLine(pattern: RegExp, timeoutMs?: number): Promise<string> {
    const cap = timeoutMs ?? defaultAwaitMs
    const deadline = Date.now() + cap
    while (Date.now() < deadline) {
      if (existsSync(logPath)) {
        const size = statSync(logPath).size
        if (size > lastOffset) {
          const fd = openLogForRead(logPath)
          buffer += fd.slice(lastOffset)
          lastOffset = size
        } else if (size < lastOffset) {
          // truncation — reset
          buffer = ''
          lastOffset = 0
        }
      }
      const lines = buffer.split('\n')
      for (const line of lines) {
        if (pattern.test(line)) return line
      }
      await sleep(40)
    }
    throw new Error(
      `awaitLine timeout (${cap}ms) waiting for ${pattern}. ` +
        `log so far:\n${buffer}`,
    )
  }

  function sendFounderInput(input_text: string, turn_id?: string): void {
    const id = turn_id ?? `turn-${Date.now()}`
    const row = JSON.stringify({ turn_id: id, input_text }) + '\n'
    appendFileSync(opts.hsutraLogPath, row)
  }

  async function stop(): Promise<void> {
    // Try the proper stop path first
    const stopChild = spawn(NATIVE_BIN, ['stop'], {
      cwd: opts.tmpdir,
      env: {
        ...process.env,
        SUTRA_NATIVE_HOME: opts.tmpdir,
        SUTRA_NATIVE_PID: pidPath,
      },
      stdio: 'ignore',
    })
    await new Promise<void>((res) => stopChild.on('exit', () => res()))

    // Verify daemon dead within 2s grace
    const graceDeadline = Date.now() + 2000
    while (Date.now() < graceDeadline) {
      try { process.kill(daemonPid, 0) } catch { return }
      await sleep(50)
    }
    // Fallback: SIGKILL the daemon
    try { process.kill(daemonPid, 'SIGKILL') } catch { /* */ }
  }

  return { pid: daemonPid, logPath, awaitLine, sendFounderInput, stop }
}

function openLogForRead(path: string): string {
  return readFileSync(path, 'utf8')
}

function sleep(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms))
}

const skipUnlessDaemonTests = process.env.RUN_DAEMON_TESTS === '1'
  ? describe
  : describe.skip

skipUnlessDaemonTests('L3 daemon simulation — real bin/sutra-native start', () => {
  let workdir: string
  let hsutraLog: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'l3-daemon-'))
    hsutraLog = join(workdir, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (existsSync(workdir)) {
      try {
        rmSync(workdir, { recursive: true, force: true })
      } catch {
        // best-effort
      }
    }
  })

  it('start → write hello → routing + completion lines appear', async () => {
    const daemon = await startDaemonForTest({ tmpdir: workdir, hsutraLogPath: hsutraLog })
    try {
      daemon.sendFounderInput('hello', 'turn-1')
      const routingLine = await daemon.awaitLine(/\[router\] exact.*W-onboarding-tour/)
      const completionLine = await daemon.awaitLine(/W-onboarding-tour.*completed/)
      expect(routingLine).toBeTruthy()
      expect(completionLine).toBeTruthy()
    } finally {
      await daemon.stop()
    }
  }, 15_000)

  it('start → start again → second start exits with lock-contention error', async () => {
    const daemon1 = await startDaemonForTest({ tmpdir: workdir, hsutraLogPath: hsutraLog })
    try {
      const proc = spawn(NATIVE_BIN, ['start'], {
        cwd: workdir,
        env: {
          ...process.env,
          SUTRA_NATIVE_HOME: workdir,
          SUTRA_NATIVE_PID: join(workdir, 'native.pid'),
          SUTRA_NATIVE_READY: join(workdir, 'native.ready'),
          SUTRA_HSUTRA_LOG_PATH: hsutraLog,
          CLAUDE_SESSION_ID: '',
        },
        stdio: ['ignore', 'pipe', 'pipe'],
      })
      let stderr = ''
      proc.stderr?.on('data', (c) => { stderr += String(c) })
      const code = await new Promise<number>((res) => proc.on('exit', (c) => res(c ?? -1)))
      expect(code).toBe(1)
      expect(stderr).toContain('already running')
    } finally {
      await daemon1.stop()
    }
  }, 15_000)

  it('start → SIGKILL daemon → start again → stale lock reaped + new daemon up', async () => {
    const daemon1 = await startDaemonForTest({ tmpdir: workdir, hsutraLogPath: hsutraLog })
    const firstPid = daemon1.pid

    // Kill the daemon directly (NOT via stop) — leaves stale PID file
    process.kill(firstPid, 'SIGKILL')
    // Wait for it to actually die
    const deadline = Date.now() + 2000
    while (Date.now() < deadline) {
      try { process.kill(firstPid, 0) } catch { break }
      await sleep(50)
    }

    // Verify lock file still there (stale)
    expect(existsSync(join(workdir, 'native.pid'))).toBe(true)

    // Start again — should reap stale lock + succeed
    const daemon2 = await startDaemonForTest({ tmpdir: workdir, hsutraLogPath: hsutraLog })
    try {
      expect(daemon2.pid).not.toBe(firstPid)
      // Verify it works end-to-end
      daemon2.sendFounderInput('hello', 'turn-recovery')
      await daemon2.awaitLine(/\[router\] exact.*W-onboarding-tour/)
    } finally {
      await daemon2.stop()
    }
  }, 20_000)
})
