/**
 * Contract tests — runtime/lifecycle (D4 SKELETON).
 *
 * R-LIFECYCLE (codex amendment 5):
 *   - acquire on empty path succeeds + writes PID file
 *   - acquire when already-held returns lock_held_alive + existing state
 *   - acquire on stale lock (process gone) reaps + retakes
 *   - release only removes own lock (not someone else's)
 *   - status reports running | stopped | stale_lock correctly
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { writeFileSync, unlinkSync, existsSync, mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import {
  acquirePidLock,
  releasePidLock,
  readPidLock,
  getStatus,
  defaultPidPath,
} from '../../../src/runtime/lifecycle.js'

describe('lifecycle — D4 SKELETON contract', () => {
  let workdir: string
  let pidPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'sutra-native-test-'))
    pidPath = join(workdir, 'native.pid')
  })

  afterEach(() => {
    if (existsSync(workdir)) {
      rmSync(workdir, { recursive: true, force: true })
    }
  })

  it('acquirePidLock on empty path succeeds + writes PID file', () => {
    const result = acquirePidLock(pidPath, 'cli')
    expect(result.acquired).toBe(true)
    expect(existsSync(pidPath)).toBe(true)
    const state = readPidLock(pidPath)
    expect(state).not.toBeNull()
    expect(state?.pid).toBe(process.pid)
    expect(state?.host_kind).toBe('cli')
    expect(typeof state?.started_at_ms).toBe('number')
  })

  it('acquirePidLock when already-held by alive process returns lock_held_alive', () => {
    const first = acquirePidLock(pidPath, 'cli')
    expect(first.acquired).toBe(true)

    const second = acquirePidLock(pidPath, 'cli')
    expect(second.acquired).toBe(false)
    expect(second.reason).toBe('lock_held_alive')
    expect(second.existing).toBeDefined()
    expect(second.existing?.pid).toBe(process.pid)
  })

  it('acquirePidLock on stale lock (impossible PID 1 owned by root, treat as stale via fake) reaps + retakes', () => {
    // Write a PID file claiming a definitely-dead process: PID 999999999
    // (well outside any reasonable PID range; kill(pid, 0) returns ESRCH).
    writeFileSync(
      pidPath,
      JSON.stringify({
        pid: 999999999,
        started_at_ms: Date.now() - 60000,
        host_kind: 'cli',
      }),
    )
    expect(existsSync(pidPath)).toBe(true)

    const result = acquirePidLock(pidPath, 'cli')
    expect(result.acquired).toBe(true)

    // Verify the lock now holds OUR pid, not the stale one.
    const state = readPidLock(pidPath)
    expect(state?.pid).toBe(process.pid)
  })

  it('releasePidLock removes our own lock', () => {
    acquirePidLock(pidPath, 'cli')
    expect(existsSync(pidPath)).toBe(true)

    releasePidLock(pidPath)
    expect(existsSync(pidPath)).toBe(false)
  })

  it('releasePidLock does NOT remove someone else\'s lock', () => {
    // Write a lock file with someone else's PID (PID 1 — likely init/launchd).
    writeFileSync(
      pidPath,
      JSON.stringify({
        pid: 1,
        started_at_ms: Date.now(),
        host_kind: 'cli',
      }),
    )

    releasePidLock(pidPath)
    // PID 1 lock should still be there — we don't own it.
    expect(existsSync(pidPath)).toBe(true)

    // Cleanup for test isolation.
    unlinkSync(pidPath)
  })

  it('getStatus reports stopped when no PID file exists', () => {
    const status = getStatus(pidPath)
    expect(status.running).toBe(false)
    expect(status.stale_lock).toBe(false)
    expect(status.pid).toBeNull()
    expect(status.uptime_ms).toBeNull()
  })

  it('getStatus reports running when PID file holds alive process', () => {
    acquirePidLock(pidPath, 'cli')
    const status = getStatus(pidPath)
    expect(status.running).toBe(true)
    expect(status.pid).toBe(process.pid)
    expect(status.host_kind).toBe('cli')
    expect(status.uptime_ms).toBeGreaterThanOrEqual(0)
    expect(status.stale_lock).toBe(false)
  })

  it('getStatus reports stale_lock when PID file holds dead process', () => {
    writeFileSync(
      pidPath,
      JSON.stringify({
        pid: 999999999,
        started_at_ms: Date.now() - 60000,
        host_kind: 'cli',
      }),
    )
    const status = getStatus(pidPath)
    expect(status.running).toBe(false)
    expect(status.stale_lock).toBe(true)
    expect(status.pid).toBe(999999999)
    expect(status.uptime_ms).toBeNull()
  })

  it('readPidLock returns null on malformed PID file', () => {
    writeFileSync(pidPath, 'not-json{}{')
    const state = readPidLock(pidPath)
    expect(state).toBeNull()
  })

  it('defaultPidPath honors SUTRA_NATIVE_HOME env var', () => {
    const original = process.env.SUTRA_NATIVE_HOME
    process.env.SUTRA_NATIVE_HOME = '/tmp/native-test-env'
    try {
      const path = defaultPidPath()
      expect(path).toBe('/tmp/native-test-env/native.pid')
    } finally {
      if (original === undefined) {
        delete process.env.SUTRA_NATIVE_HOME
      } else {
        process.env.SUTRA_NATIVE_HOME = original
      }
    }
  })
})
