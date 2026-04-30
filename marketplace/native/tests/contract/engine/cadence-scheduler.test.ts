/**
 * CadenceScheduler contract test (M9 Group GG T-159).
 *
 * Asserts:
 *  - register / start / tick / unregister happy path
 *  - tick before start is a no-op
 *  - every_n_minutes period
 *  - every_n_hours period
 *  - every_day_at fires at the expected UTC moment + repeats every 24h
 *  - cron handles never fire at v1.0 (next_fire_at = +Infinity)
 *  - invalid spec inputs throw RangeError / TypeError
 *  - unregister is silent on miss; idempotent
 *  - callback errors surface in TickReport.errors but do not halt other fires
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group GG T-159
 *   - holding/research/2026-04-29-native-d5-invariant-register.md §1 I-12
 */

import { describe, it, expect } from 'vitest'

import {
  CadenceScheduler,
  CADENCE_JITTER_MS,
  type CadenceSpec,
} from '../../../src/engine/cadence-scheduler.js'

/** Build a deterministic clock seam that returns the externally-controlled `now`. */
function makeClock() {
  let now = 0
  return {
    get now() {
      return now
    },
    set: (n: number) => {
      now = n
    },
    advance: (ms: number) => {
      now += ms
    },
    fn: () => now,
  }
}

describe('CadenceScheduler — happy path', () => {
  it('register + start + tick fires the callback', async () => {
    const clk = makeClock()
    const sched = new CadenceScheduler({ clock: clk.fn })
    let fires = 0
    const handle = sched.register(
      { kind: 'every_n_minutes', n: 1 },
      () => {
        fires += 1
      },
    )

    // Before start — tick is a no-op.
    clk.advance(2 * 60 * 1000)
    let report = await sched.tick()
    expect(report.fires).toEqual([])
    expect(fires).toBe(0)

    sched.start()
    // next_fire_at was primed at register-time (now=0): scheduled = 0 + 60_000 = 60_000.
    // Clock has already advanced to 120_000 → tick fires + advances next to 120_000.
    report = await sched.tick()
    expect(report.fires).toHaveLength(1)
    expect(report.fires[0]!.handle).toBe(handle)
    expect(report.fires[0]!.scheduled_at).toBe(60_000)
    expect(report.fires[0]!.fired_at).toBe(120_000)
    expect(fires).toBe(1)
  })

  it('every_n_minutes: subsequent fires happen at scheduled cadence', async () => {
    const clk = makeClock()
    clk.set(0)
    const sched = new CadenceScheduler({ clock: clk.fn })
    sched.start()
    let fires = 0
    sched.register({ kind: 'every_n_minutes', n: 1 }, () => {
      fires += 1
    })

    // Tick at minute 1 — fires.
    clk.set(60_000)
    await sched.tick()
    expect(fires).toBe(1)

    // Tick at minute 1.5 — does not fire (next scheduled = 120_000).
    clk.set(90_000)
    await sched.tick()
    expect(fires).toBe(1)

    // Tick at minute 2 — fires.
    clk.set(120_000)
    await sched.tick()
    expect(fires).toBe(2)
  })

  it('every_n_hours: 6 fires over 6 hours', async () => {
    const clk = makeClock()
    clk.set(0)
    const sched = new CadenceScheduler({ clock: clk.fn })
    sched.start()
    let fires = 0
    sched.register({ kind: 'every_n_hours', n: 1 }, () => {
      fires += 1
    })

    for (let h = 1; h <= 6; h++) {
      clk.set(h * 60 * 60 * 1000)
      await sched.tick()
    }
    expect(fires).toBe(6)
  })
})

describe('CadenceScheduler — every_day_at', () => {
  it('fires at next-day HH:MM in UTC; advances 24h', async () => {
    const clk = makeClock()
    // Choose a starting time of 2026-04-30T08:00:00Z.
    const start = Date.UTC(2026, 3, 30, 8, 0, 0)
    clk.set(start)
    const sched = new CadenceScheduler({ clock: clk.fn })
    sched.start()
    let fires = 0
    const handle = sched.register(
      { kind: 'every_day_at', hour_utc: 9, minute_utc: 30 },
      () => {
        fires += 1
      },
    )
    // Next fire scheduled today at 09:30 UTC.
    const expected = Date.UTC(2026, 3, 30, 9, 30, 0)
    expect(sched.getNextFireAt(handle)).toBe(expected)

    // Advance to 09:30 — fires.
    clk.set(expected)
    await sched.tick()
    expect(fires).toBe(1)

    // Next next: tomorrow 09:30.
    expect(sched.getNextFireAt(handle)).toBe(expected + 24 * 60 * 60 * 1000)
  })

  it('schedules tomorrow when current time has passed today HH:MM', async () => {
    const clk = makeClock()
    const start = Date.UTC(2026, 3, 30, 10, 0, 0)
    clk.set(start)
    const sched = new CadenceScheduler({ clock: clk.fn })
    const handle = sched.register(
      { kind: 'every_day_at', hour_utc: 9, minute_utc: 30 },
      () => {},
    )
    expect(sched.getNextFireAt(handle)).toBe(
      Date.UTC(2026, 3, 30, 9, 30) + 24 * 60 * 60 * 1000,
    )
  })
})

describe('CadenceScheduler — cron escape', () => {
  it('cron handles never fire at v1.0 (next_fire_at = +Infinity)', async () => {
    const clk = makeClock()
    clk.set(0)
    const sched = new CadenceScheduler({ clock: clk.fn })
    sched.start()
    let fires = 0
    const handle = sched.register({ kind: 'cron', expression: '*/5 * * * *' }, () => {
      fires += 1
    })
    expect(sched.getNextFireAt(handle)).toBe(Number.POSITIVE_INFINITY)
    clk.set(10 * 60 * 60 * 1000) // 10 hours later
    await sched.tick()
    expect(fires).toBe(0)
  })
})

describe('CadenceScheduler — defensive validation', () => {
  it('rejects every_n_minutes with non-positive n', () => {
    const sched = new CadenceScheduler({ clock: () => 0 })
    expect(() => sched.register({ kind: 'every_n_minutes', n: 0 }, () => {})).toThrow(RangeError)
    expect(() => sched.register({ kind: 'every_n_minutes', n: -1 }, () => {})).toThrow(RangeError)
    expect(() => sched.register({ kind: 'every_n_minutes', n: 1.5 } as unknown as CadenceSpec, () => {})).toThrow(RangeError)
  })

  it('rejects every_day_at out-of-range hour/minute', () => {
    const sched = new CadenceScheduler({ clock: () => 0 })
    expect(() => sched.register({ kind: 'every_day_at', hour_utc: 24, minute_utc: 0 }, () => {})).toThrow(RangeError)
    expect(() => sched.register({ kind: 'every_day_at', hour_utc: 0, minute_utc: 60 }, () => {})).toThrow(RangeError)
  })

  it('rejects cron with empty expression', () => {
    const sched = new CadenceScheduler({ clock: () => 0 })
    expect(() => sched.register({ kind: 'cron', expression: '' }, () => {})).toThrow(TypeError)
  })

  it('rejects non-function callback', () => {
    const sched = new CadenceScheduler({ clock: () => 0 })
    expect(() =>
      sched.register({ kind: 'every_n_minutes', n: 1 }, 'not-a-fn' as unknown as () => void),
    ).toThrow(TypeError)
  })
})

describe('CadenceScheduler — lifecycle', () => {
  it('unregister is silent on miss; idempotent', () => {
    const sched = new CadenceScheduler({ clock: () => 0 })
    expect(() => sched.unregister('cad-doesnt-exist')).not.toThrow()
    const h = sched.register({ kind: 'every_n_minutes', n: 1 }, () => {})
    sched.unregister(h)
    sched.unregister(h)
    expect(sched.size()).toBe(0)
  })

  it('callback errors surface in TickReport.errors; sibling fires continue', async () => {
    const clk = makeClock()
    clk.set(0)
    const sched = new CadenceScheduler({ clock: clk.fn })
    sched.start()
    let okFires = 0
    sched.register({ kind: 'every_n_minutes', n: 1 }, () => {
      throw new Error('boom')
    })
    sched.register({ kind: 'every_n_minutes', n: 1 }, () => {
      okFires += 1
    })
    clk.set(60_000)
    const report = await sched.tick()
    expect(report.errors).toHaveLength(1)
    expect(report.errors[0]!.error_message).toBe('boom')
    expect(report.fires).toHaveLength(1)
    expect(okFires).toBe(1)
  })

  it('CADENCE_JITTER_MS exported as 5 minutes', () => {
    expect(CADENCE_JITTER_MS).toBe(5 * 60 * 1000)
  })
})
