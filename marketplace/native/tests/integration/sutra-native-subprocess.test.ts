/**
 * Integration / E2E — sutra-native CLI as a real subprocess.
 *
 * Per codex master review 2026-05-03 amendment 3 (ADVISORY): the contract
 * suite tests `main()` in-process and never exercises `isMain`, the bash
 * shim, or process exit semantics. This test fills that gap by spawning
 * the actual `bin/sutra-native` (which execs into the TS via tsx, since
 * dist/ may or may not be present in CI/dev).
 *
 * Validates:
 *   1. `bin/sutra-native start` writes PID file + prints banner + exits 0
 *   2. After exit, the lock PERSISTS (sub-shell reads it back)
 *   3. `bin/sutra-native status` reports "running" after start exits
 *   4. `bin/sutra-native start` again returns 1 with "already running"
 *   5. `bin/sutra-native stop` releases the lock
 *   6. `bin/sutra-native status` after stop reports "stopped"
 *   7. SUTRA_NATIVE_PID env override is honored end-to-end through the shim
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const BIN = resolve(__dirname, '../../bin/sutra-native')

interface RunResult {
  status: number
  stdout: string
  stderr: string
}

function runBin(args: string[], pidPath: string): RunResult {
  const result = spawnSync(BIN, args, {
    encoding: 'utf8',
    env: {
      ...process.env,
      SUTRA_NATIVE_PID: pidPath,
    },
    timeout: 10000,
  })
  return {
    status: result.status ?? -1,
    stdout: result.stdout ?? '',
    stderr: result.stderr ?? '',
  }
}

// v1.1.x: cmdStart now spawns a daemon child + waits for ready marker. The
// D4 SKELETON foreground contract (start exits, lock persists as marker) is
// superseded. L3 harness at tests/integration/l3-daemon-simulation.test.ts
// (gated by RUN_DAEMON_TESTS=1) covers the v1.1.x daemon contract.
describe.skip('sutra-native CLI — subprocess E2E (D4 SKELETON — superseded by L3)', () => {
  let workdir: string
  let pidPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'sutra-native-e2e-'))
    pidPath = join(workdir, 'native.pid')
  })

  afterEach(() => {
    if (existsSync(workdir)) {
      rmSync(workdir, { recursive: true, force: true })
    }
  })

  it('bin/sutra-native exists and is executable', () => {
    expect(existsSync(BIN)).toBe(true)
  })

  it('start: writes PID file, prints banner, exits 0; lock PERSISTS after exit', () => {
    const result = runBin(['start'], pidPath)
    expect(result.status).toBe(0)
    expect(result.stdout).toContain('SUTRA-NATIVE')
    expect(result.stdout).toContain('Activated')
    // Critical: lock persists after subprocess exit (codex master fix).
    expect(existsSync(pidPath)).toBe(true)
    const state = JSON.parse(readFileSync(pidPath, 'utf8'))
    expect(typeof state.pid).toBe('number')
    expect(typeof state.started_at_ms).toBe('number')
  })

  it('status: reports running after start subprocess exits', () => {
    const startResult = runBin(['start'], pidPath)
    expect(startResult.status).toBe(0)

    const statusResult = runBin(['status'], pidPath)
    // The PID in the lock file is now a dead process (the start subprocess
    // already exited). So status reports STALE LOCK, NOT running. That's
    // honest — the v1.0 foreground "start" doesn't keep a process alive,
    // it just registers the activation. Stale-lock detection on next start
    // reaps + retakes.
    //
    // For TRUE running status, D2 will fold the H-Sutra subscriber + router
    // into a forked daemon (or in-process when invoked from CC slash).
    // For now, status correctly reports "STALE LOCK" because the recorded
    // PID is gone.
    expect(statusResult.status).toBe(0)
    expect(statusResult.stdout).toMatch(/STALE LOCK|running/)
  })

  it('start twice: second call detects the existing lock OR reaps stale and re-acquires', () => {
    const first = runBin(['start'], pidPath)
    expect(first.status).toBe(0)

    const second = runBin(['start'], pidPath)
    // Two cases:
    // (a) Original process still alive (improbable in spawnSync — already exited)
    //     → exit 1 + "already running"
    // (b) Stale lock detected + reaped + re-acquired by second invocation
    //     → exit 0 + new banner
    // Both behaviors are CORRECT for D4 SKELETON foreground mode.
    if (second.status === 1) {
      expect(second.stderr).toContain('already running')
    } else {
      expect(second.status).toBe(0)
      expect(second.stdout).toContain('Activated')
    }
  })

  it('stop: releases the foreground lock + PID file is removed', () => {
    runBin(['start'], pidPath)
    expect(existsSync(pidPath)).toBe(true)

    const stopResult = runBin(['stop'], pidPath)
    // Per codex master 2026-05-03 fix: cmdStop uses force=true since v1.0
    // foreground mode means the recorded pid is always dead by the time
    // stop runs. The lock is the activation marker, not a process-resource
    // claim. stop must successfully remove it.
    expect(stopResult.status).toBe(0)
    expect(stopResult.stdout).toContain('stopped')
    expect(existsSync(pidPath)).toBe(false)

    // status after stop must report stopped
    const statusResult = runBin(['status'], pidPath)
    expect(statusResult.status).toBe(0)
    expect(statusResult.stdout).toContain('stopped')
  })

  it('stop: when not running returns 0 + reports not-running', () => {
    expect(existsSync(pidPath)).toBe(false)
    const stopResult = runBin(['stop'], pidPath)
    expect(stopResult.status).toBe(0)
    expect(stopResult.stdout).toContain('not running')
  })

  it('version: prints semver string + exits 0', () => {
    const result = runBin(['version'], pidPath)
    expect(result.status).toBe(0)
    expect(result.stdout.trim()).toMatch(/^\d+\.\d+\.\d+$/)
  })

  it('help: prints usage with all subcommands + exits 0', () => {
    const result = runBin(['help'], pidPath)
    expect(result.status).toBe(0)
    expect(result.stdout).toContain('Usage:')
    expect(result.stdout).toContain('start')
    expect(result.stdout).toContain('stop')
    expect(result.stdout).toContain('status')
    expect(result.stdout).toContain('version')
  })

  it('unknown subcommand: exits 2 + stderr explains', () => {
    const result = runBin(['nonsense-subcommand'], pidPath)
    expect(result.status).toBe(2)
    expect(result.stderr).toContain('unknown subcommand')
  })

  it('SUTRA_NATIVE_PID env honored end-to-end through bash shim', () => {
    // Use a path that defaultPidPath() would NEVER produce.
    const customPidPath = join(workdir, 'custom-location', 'my.pid')
    const result = runBin(['start'], customPidPath)
    expect(result.status).toBe(0)
    expect(existsSync(customPidPath)).toBe(true)
    // And NOT at default path
    expect(existsSync(join(workdir, 'native.pid'))).toBe(false)
  })
})
