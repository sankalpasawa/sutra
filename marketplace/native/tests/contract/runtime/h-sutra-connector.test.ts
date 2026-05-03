/**
 * Contract tests — HSutraConnector (D2 step 1 of vertical slice).
 *
 * Coverage per codex amendment 5 (R-WATCHER + R-IDEMPOTENCY):
 *   - basic catch-up read on start
 *   - listener registration + emission
 *   - cache lookup by turn_id
 *   - log ROTATION (inode change → reset)
 *   - log TRUNCATION (size shrunk → reset)
 *   - DUPLICATE lines (same turn_id) → cache update, no re-emit
 *   - PARTIAL writes (incomplete trailing line buffered)
 *   - RESTART CATCH-UP (start reads from byte 0)
 *   - malformed rows dropped silently with counter
 *   - stop is idempotent
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  appendFileSync,
  writeFileSync,
  unlinkSync,
  existsSync,
  mkdtempSync,
  rmSync,
  mkdirSync,
} from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import {
  HSutraConnector,
  resolveHSutraLogPath,
} from '../../../src/runtime/h-sutra-connector.js'
import type { HSutraEvent } from '../../../src/types/h-sutra-event.js'

function row(event: Partial<HSutraEvent> & { turn_id: string }): string {
  return JSON.stringify(event) + '\n'
}

describe('HSutraConnector — D2 step 1 contract', () => {
  let workdir: string
  let logPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'hsutra-connector-test-'))
    logPath = join(workdir, 'log.jsonl')
  })

  afterEach(() => {
    if (existsSync(workdir)) {
      rmSync(workdir, { recursive: true, force: true })
    }
  })

  describe('basic operation', () => {
    it('start on missing file does not throw', () => {
      const conn = new HSutraConnector({ log_path: logPath })
      expect(() => conn.start()).not.toThrow()
      conn.stop()
    })

    it('start reads existing rows from byte 0 (RESTART CATCH-UP)', () => {
      writeFileSync(logPath, row({ turn_id: 'T-001', verb: 'DIRECT' }) + row({ turn_id: 'T-002', verb: 'QUERY' }))

      const conn = new HSutraConnector({ log_path: logPath })
      const received: HSutraEvent[] = []
      conn.onEvent((e) => received.push(e))
      conn.start()
      conn.stop()

      expect(received).toHaveLength(2)
      expect(received[0].turn_id).toBe('T-001')
      expect(received[1].turn_id).toBe('T-002')
    })

    it('listener can be registered + receives events', () => {
      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()

      writeFileSync(logPath, row({ turn_id: 'T-100' }))
      conn.pollNow()

      expect(received).toContain('T-100')
      conn.stop()
    })

    it('getCachedEvent returns the event by turn_id', () => {
      writeFileSync(logPath, row({ turn_id: 'T-cached', verb: 'DIRECT', risk: 'HIGH' }))

      const conn = new HSutraConnector({ log_path: logPath })
      conn.start()

      const cached = conn.getCachedEvent('T-cached')
      expect(cached?.turn_id).toBe('T-cached')
      expect(cached?.verb).toBe('DIRECT')
      expect(cached?.risk).toBe('HIGH')

      expect(conn.getCachedEvent('T-not-here')).toBeNull()
      conn.stop()
    })

    it('listener unsubscribe stops further notifications', () => {
      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      const unsub = conn.onEvent((e) => received.push(e.turn_id))

      writeFileSync(logPath, row({ turn_id: 'T-before-unsub' }))
      conn.start()
      expect(received).toContain('T-before-unsub')

      unsub()
      appendFileSync(logPath, row({ turn_id: 'T-after-unsub' }))
      conn.pollNow()

      expect(received).not.toContain('T-after-unsub')
      conn.stop()
    })

    it('stop is idempotent', () => {
      const conn = new HSutraConnector({ log_path: logPath })
      conn.start()
      expect(() => {
        conn.stop()
        conn.stop()
        conn.stop()
      }).not.toThrow()
    })
  })

  describe('R-IDEMPOTENCY (same turn_id twice)', () => {
    it('duplicate turn_id → cache update, NO re-emit', () => {
      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))

      writeFileSync(
        logPath,
        row({ turn_id: 'T-dup', verb: 'DIRECT' }) + row({ turn_id: 'T-dup', verb: 'QUERY' }),
      )
      conn.start()

      expect(received).toEqual(['T-dup'])
      expect(conn.getStats().duplicates_skipped).toBe(1)

      // Cache holds the LATEST event payload
      const cached = conn.getCachedEvent('T-dup')
      expect(cached?.verb).toBe('QUERY')
      conn.stop()
    })

    it('duplicate across multiple poll cycles still de-duplicates', () => {
      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()

      writeFileSync(logPath, row({ turn_id: 'T-rep' }))
      conn.pollNow()
      expect(received).toEqual(['T-rep'])

      appendFileSync(logPath, row({ turn_id: 'T-rep' }))
      conn.pollNow()

      expect(received).toEqual(['T-rep']) // still 1
      expect(conn.getStats().duplicates_skipped).toBe(1)
      conn.stop()
    })
  })

  describe('R-WATCHER (rotation, truncation, partial writes)', () => {
    it('LOG ROTATION (inode change) → reset offset', () => {
      writeFileSync(logPath, row({ turn_id: 'T-original' }))

      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()
      expect(received).toContain('T-original')

      // Simulate rotation: delete + recreate (new inode)
      unlinkSync(logPath)
      writeFileSync(logPath, row({ turn_id: 'T-rotated' }))
      conn.pollNow()

      expect(received).toContain('T-rotated')
      conn.stop()
    })

    it('LOG TRUNCATION (size shrunk) → reset offset, re-emits', () => {
      writeFileSync(logPath, row({ turn_id: 'T-pre-truncate-1' }) + row({ turn_id: 'T-pre-truncate-2' }))

      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()
      expect(received).toEqual(['T-pre-truncate-1', 'T-pre-truncate-2'])

      // Truncate via overwrite with shorter content (different turn_id to avoid dedup)
      writeFileSync(logPath, row({ turn_id: 'T-post-truncate' }))
      conn.pollNow()

      expect(received).toContain('T-post-truncate')
      conn.stop()
    })

    it('PARTIAL WRITE (no trailing newline) is buffered until newline', () => {
      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()

      // Write a partial row (no trailing newline)
      const fullRow = JSON.stringify({ turn_id: 'T-partial' })
      writeFileSync(logPath, fullRow.slice(0, fullRow.length - 5)) // chop last 5 chars
      conn.pollNow()
      expect(received).not.toContain('T-partial')

      // Append the rest + newline
      appendFileSync(logPath, fullRow.slice(fullRow.length - 5) + '\n')
      conn.pollNow()

      expect(received).toContain('T-partial')
      conn.stop()
    })

    it('appended rows after start are picked up via pollNow', () => {
      writeFileSync(logPath, row({ turn_id: 'T-initial' }))
      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()

      appendFileSync(logPath, row({ turn_id: 'T-appended-1' }) + row({ turn_id: 'T-appended-2' }))
      conn.pollNow()

      expect(received).toEqual(['T-initial', 'T-appended-1', 'T-appended-2'])
      conn.stop()
    })
  })

  describe('malformed input handling', () => {
    it('malformed JSON line is dropped silently with counter increment', () => {
      writeFileSync(logPath, 'not-json{}{\n' + row({ turn_id: 'T-after-bad' }))

      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()

      expect(received).toEqual(['T-after-bad'])
      expect(conn.getStats().malformed_rows).toBeGreaterThanOrEqual(1)
      conn.stop()
    })

    it('row missing turn_id is dropped as malformed', () => {
      writeFileSync(
        logPath,
        JSON.stringify({ verb: 'DIRECT', cell: 'DIRECT·INBOUND' }) + '\n',
      )

      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()

      expect(received).toHaveLength(0)
      expect(conn.getStats().malformed_rows).toBeGreaterThanOrEqual(1)
      conn.stop()
    })

    it('listener exception does not break the connector or other listeners', () => {
      writeFileSync(logPath, row({ turn_id: 'T-listener-exception' }))

      const conn = new HSutraConnector({ log_path: logPath })
      conn.onEvent(() => {
        throw new Error('listener boom')
      })
      const second: string[] = []
      conn.onEvent((e) => second.push(e.turn_id))

      expect(() => conn.start()).not.toThrow()
      expect(second).toContain('T-listener-exception')
      conn.stop()
    })

    it('empty lines are skipped without counting as malformed', () => {
      writeFileSync(logPath, '\n\n' + row({ turn_id: 'T-after-blanks' }) + '\n')

      const conn = new HSutraConnector({ log_path: logPath })
      const received: string[] = []
      conn.onEvent((e) => received.push(e.turn_id))
      conn.start()

      expect(received).toEqual(['T-after-blanks'])
      expect(conn.getStats().malformed_rows).toBe(0)
      conn.stop()
    })
  })

  describe('stats + cache management', () => {
    it('getStats reports event counters + listener count', () => {
      writeFileSync(logPath, row({ turn_id: 'T-s1' }) + row({ turn_id: 'T-s2' }))

      const conn = new HSutraConnector({ log_path: logPath })
      conn.onEvent(() => {})
      conn.onEvent(() => {})
      conn.start()

      const stats = conn.getStats()
      expect(stats.events_seen).toBe(2)
      expect(stats.events_emitted).toBe(2)
      expect(stats.duplicates_skipped).toBe(0)
      expect(stats.cache_size).toBe(2)
      expect(stats.listener_count).toBe(2)
      conn.stop()
    })

    it('cache evicts entries past TTL', async () => {
      const conn = new HSutraConnector({ log_path: logPath, cache_ttl_ms: 50 })
      writeFileSync(logPath, row({ turn_id: 'T-ephemeral' }))
      conn.start()
      expect(conn.getCachedEvent('T-ephemeral')).not.toBeNull()

      await new Promise((resolve) => setTimeout(resolve, 75))

      // Trigger eviction via getStats() or getCachedEvent()
      expect(conn.getCachedEvent('T-ephemeral')).toBeNull()
      conn.stop()
    })
  })

  describe('resolveHSutraLogPath', () => {
    it('returns Asawa override path when it exists', () => {
      mkdirSync(join(workdir, 'holding/state/interaction'), { recursive: true })
      writeFileSync(join(workdir, 'holding/state/interaction/log.jsonl'), '')

      const resolved = resolveHSutraLogPath(workdir)
      expect(resolved).toBe(join(workdir, 'holding/state/interaction/log.jsonl'))
    })

    it('falls back to default path when Asawa override missing', () => {
      const resolved = resolveHSutraLogPath(workdir)
      expect(resolved).toBe(join(workdir, '.sutra/h-sutra.jsonl'))
    })
  })
})
