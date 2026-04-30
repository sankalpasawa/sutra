/**
 * M9 Group GG — CadenceScheduler integration test (T-160).
 *
 * Asserts I-12: Per-hour cadence scheduler fires within ±5min over a 6h
 * simulated run. Pins the behaviour the M9 plan calls out for I-12:
 *   "register cadence; advance clock 1h; assert fired in ±5min;
 *    assert ≥6 fires over 6h sim"
 *
 * Tests use the deterministic clock seam — no sleeps, no real timers.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group GG T-160 (A-2 row I-12)
 *   - holding/research/2026-04-29-native-d5-invariant-register.md §1 I-12
 */

import { describe, it, expect } from 'vitest'

import {
  CadenceScheduler,
  CADENCE_JITTER_MS,
} from '../../src/engine/cadence-scheduler.js'

describe('M9 Group GG — I-12 invariant: per-hour cadence ±5min', () => {
  it('register hourly cadence; advance clock 1h; fired within ±5min', async () => {
    let now = 0
    const sched = new CadenceScheduler({ clock: () => now })
    sched.start()
    let fires = 0
    const handle = sched.register({ kind: 'every_n_hours', n: 1 }, () => {
      fires += 1
    })
    // Advance clock by 1 hour + 30 seconds (well within ±5min jitter band).
    now = 60 * 60 * 1000 + 30 * 1000
    const report = await sched.tick()
    expect(fires).toBe(1)
    expect(report.fires).toHaveLength(1)
    expect(report.fires[0]!.jitter_ms).toBeLessThanOrEqual(CADENCE_JITTER_MS)
    expect(sched.getJitterMs(handle)).toBeLessThanOrEqual(CADENCE_JITTER_MS)
  })

  it('6h simulation: ≥6 hourly fires; each within ±5min of scheduled', async () => {
    let now = 0
    const sched = new CadenceScheduler({ clock: () => now })
    sched.start()
    let fires = 0
    const fire_log: Array<{ scheduled: number; actual: number; jitter: number }> = []
    sched.register({ kind: 'every_n_hours', n: 1 }, () => {
      fires += 1
    })
    // Simulate 6 hours: tick at every hour + small jitter (here 1 second).
    for (let h = 1; h <= 6; h++) {
      now = h * 60 * 60 * 1000 + 1000
      const report = await sched.tick()
      for (const f of report.fires) {
        fire_log.push({
          scheduled: f.scheduled_at,
          actual: f.fired_at,
          jitter: f.jitter_ms,
        })
      }
    }
    expect(fires).toBe(6)
    expect(fire_log).toHaveLength(6)
    for (const f of fire_log) {
      expect(f.jitter).toBeLessThanOrEqual(CADENCE_JITTER_MS)
    }
  })

  it('host process drives time; stop() halts dispatch even when next_fire_at ≤ now', async () => {
    let now = 0
    const sched = new CadenceScheduler({ clock: () => now })
    sched.start()
    let fires = 0
    sched.register({ kind: 'every_n_hours', n: 1 }, () => {
      fires += 1
    })
    sched.stop()
    now = 2 * 60 * 60 * 1000
    const report = await sched.tick()
    expect(fires).toBe(0)
    expect(report.fires).toHaveLength(0)
    // resume + tick — fires.
    sched.start()
    await sched.tick()
    expect(fires).toBe(1)
  })

  it('handle re-registration works after unregister', async () => {
    let now = 0
    const sched = new CadenceScheduler({ clock: () => now })
    sched.start()
    let fires = 0
    const h1 = sched.register({ kind: 'every_n_hours', n: 1 }, () => {
      fires += 1
    })
    sched.unregister(h1)
    expect(sched.size()).toBe(0)
    const h2 = sched.register({ kind: 'every_n_hours', n: 1 }, () => {
      fires += 1
    })
    expect(h2).not.toBe(h1)
    expect(sched.size()).toBe(1)
    now = 60 * 60 * 1000 + 1000
    await sched.tick()
    expect(fires).toBe(1)
  })
})
