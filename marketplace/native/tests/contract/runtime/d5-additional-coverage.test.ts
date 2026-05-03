/**
 * D5.1 + D5.2 + D5.3 + D5.4 — additional edge-case coverage on top of
 * the existing connector + lifecycle contract tests.
 *
 * Existing tests already cover the headline cases:
 *   D5.1 R-WATCHER       — rotation, truncation, partial writes, append
 *                          (h-sutra-connector.test.ts §R-WATCHER)
 *   D5.2 R-IDEMPOTENCY   — duplicate turn_id, multi-poll dedup
 *                          (h-sutra-connector.test.ts §R-IDEMPOTENCY)
 *   D5.3 R-LIFECYCLE     — PID lock + stale + release + status
 *                          (lifecycle.test.ts)
 *
 * This file fills targeted gaps:
 *   D5.1 — file deletion mid-watch + recovery on next start
 *   D5.2 — restart-after-stop preserves dedup state
 *   D5.3 — force-vs-non-force release ownership semantics
 *   D5.4 — listener-throw isolation under burst + documents the v1.0
 *          backpressure invariant
 *
 * v1.0 backpressure model (codified here for future maintainers):
 *   The connector dispatches listeners SYNCHRONOUSLY in registration
 *   order during each readNewBytes pass. There is NO queue, NO async
 *   scheduling, NO backpressure signal. Slow listeners block the next
 *   row's dispatch within the same read pass. Listener throws are
 *   isolated (other listeners still fire) but the throwing listener
 *   misses that row.
 *
 *   Operators who need queued/async fan-out wrap their listener in
 *   queueMicrotask() or push to their own queue. v1.1+ may add a
 *   queue-mode option per founder direction.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  appendFileSync,
  existsSync,
  mkdtempSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { HSutraConnector } from '../../../src/runtime/h-sutra-connector.js'
import {
  acquirePidLock,
  releasePidLock,
  getStatus,
} from '../../../src/runtime/lifecycle.js'
import type { HSutraEvent } from '../../../src/types/h-sutra-event.js'

function row(event: Partial<HSutraEvent> & { turn_id: string }): string {
  return JSON.stringify(event) + '\n'
}

describe('D5.1 R-WATCHER — file deletion mid-watch', () => {
  let workdir: string
  let logPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'd5-watcher-'))
    logPath = join(workdir, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('file deleted mid-watch + recreated → next start picks up new content', () => {
    writeFileSync(logPath, row({ turn_id: 't-1', input_text: 'first' }))
    const conn = new HSutraConnector({ log_path: logPath })
    const seen: string[] = []
    conn.onEvent((e) => seen.push(e.turn_id))
    conn.start()
    conn.stop()
    expect(seen).toEqual(['t-1'])

    // Simulate operator deleting the log
    unlinkSync(logPath)
    expect(existsSync(logPath)).toBe(false)

    // Recreate with a new row (different turn_id)
    writeFileSync(logPath, row({ turn_id: 't-2', input_text: 'second' }))

    // A FRESH connector picks up the new content from byte 0
    const conn2 = new HSutraConnector({ log_path: logPath })
    const seen2: string[] = []
    conn2.onEvent((e) => seen2.push(e.turn_id))
    conn2.start()
    conn2.stop()
    expect(seen2).toEqual(['t-2'])
  })
})

describe('D5.2 R-IDEMPOTENCY — restart-after-stop preserves cache', () => {
  let workdir: string
  let logPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'd5-idempotency-'))
    logPath = join(workdir, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('same connector instance: stop → start → duplicate row is still de-duplicated', () => {
    writeFileSync(logPath, row({ turn_id: 't-1', input_text: 'first' }))
    const conn = new HSutraConnector({ log_path: logPath })
    const events: string[] = []
    conn.onEvent((e) => events.push(e.turn_id))

    conn.start()
    conn.stop()
    expect(events).toEqual(['t-1'])

    // Append the SAME turn_id again (operator replay scenario)
    appendFileSync(logPath, row({ turn_id: 't-1', input_text: 'first-again' }))

    // Restart same instance — cache survived; dup is suppressed
    conn.start()
    conn.stop()
    expect(events).toEqual(['t-1']) // no second emission
  })

  it('cache lookup remains valid across stop/start', () => {
    writeFileSync(logPath, row({ turn_id: 't-cached', input_text: 'cached' }))
    const conn = new HSutraConnector({ log_path: logPath })
    conn.onEvent(() => {})
    conn.start()
    conn.stop()

    const cached = conn.getCachedEvent('t-cached')
    expect(cached).not.toBeNull()
    expect(cached?.turn_id).toBe('t-cached')
  })
})

describe('D5.3 R-LIFECYCLE — force-vs-non-force release semantics', () => {
  let workdir: string
  let pidPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'd5-lifecycle-'))
    pidPath = join(workdir, 'native.pid')
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('non-force release respects pid ownership (own lock removed; foreign lock kept)', () => {
    // Acquire OUR lock
    acquirePidLock(pidPath, 'cli-test')
    expect(existsSync(pidPath)).toBe(true)

    // Non-force release: our pid → succeed
    releasePidLock(pidPath)
    expect(existsSync(pidPath)).toBe(false)

    // Now write a foreign-pid lock (PID 1 — exists, not us)
    writeFileSync(
      pidPath,
      JSON.stringify({ pid: 1, started_at_ms: Date.now(), host_kind: 'foreign' }),
    )

    // Non-force release: foreign pid → keep file
    releasePidLock(pidPath)
    expect(existsSync(pidPath)).toBe(true)

    // Force release: removes regardless of ownership
    releasePidLock(pidPath, { force: true })
    expect(existsSync(pidPath)).toBe(false)
  })

  it('getStatus reflects foreign live lock as running', () => {
    // Foreign lock pointing at our own PID (we know we're alive)
    writeFileSync(
      pidPath,
      JSON.stringify({ pid: process.pid, started_at_ms: Date.now(), host_kind: 'foreign' }),
    )
    const status = getStatus(pidPath)
    expect(status.running).toBe(true)
    expect(status.pid).toBe(process.pid)
    expect(status.stale_lock).toBe(false)
    releasePidLock(pidPath, { force: true })
  })
})

describe('D5.4 R-BACKPRESSURE — listener isolation under burst', () => {
  let workdir: string
  let logPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'd5-backpressure-'))
    logPath = join(workdir, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('5-row burst: throwing listener never blocks the cooperating listener', () => {
    // Pre-populate with 5 rows — connector reads them all on start in one pass
    const rows = Array.from({ length: 5 }, (_, i) => row({ turn_id: `t-${i}` })).join('')
    writeFileSync(logPath, rows)

    const conn = new HSutraConnector({ log_path: logPath })
    const cooperating: string[] = []
    let throwerInvocations = 0
    conn.onEvent(() => {
      throwerInvocations++
      throw new Error('rude listener')
    })
    conn.onEvent((e) => {
      cooperating.push(e.turn_id)
    })

    conn.start()
    conn.stop()

    // Thrower was called for every row (no listener short-circuit)
    expect(throwerInvocations).toBe(5)
    // Cooperating listener received every row (no listener interference)
    expect(cooperating).toEqual(['t-0', 't-1', 't-2', 't-3', 't-4'])
    // Stats reflect every emission
    expect(conn.getStats().events_emitted).toBe(5)
    expect(conn.getStats().malformed_rows).toBe(0)
  })

  it('synchronous fan-out invariant: listeners observe rows in file order', () => {
    const rows = Array.from({ length: 10 }, (_, i) => row({ turn_id: `t-${i}` })).join('')
    writeFileSync(logPath, rows)

    const conn = new HSutraConnector({ log_path: logPath })
    const observed: string[] = []
    conn.onEvent((e) => observed.push(e.turn_id))
    conn.start()
    conn.stop()

    expect(observed).toEqual([
      't-0', 't-1', 't-2', 't-3', 't-4', 't-5', 't-6', 't-7', 't-8', 't-9',
    ])
  })

  it('v1.0 invariant: dispatch is synchronous (no microtask scheduling)', async () => {
    writeFileSync(logPath, row({ turn_id: 't-sync' }))
    const conn = new HSutraConnector({ log_path: logPath })
    let synchronouslyObserved = false
    conn.onEvent(() => {
      synchronouslyObserved = true
    })
    conn.start()
    // Without any await/setImmediate, the listener has already fired:
    expect(synchronouslyObserved).toBe(true)
    conn.stop()
  })
})
