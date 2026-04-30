/**
 * CadenceScheduler jitter property test (M9 Group GG T-159).
 *
 * Property: for every cadence whose tick happens within the ±5min jitter
 * band of the scheduled time, the scheduler reports `jitter_ms` ≤
 * CADENCE_JITTER_MS.
 *
 * fast-check pins the assertion across ≥1000 randomly-generated cases:
 *   - period: 1..6 hours (typical cadence range)
 *   - tick offset within each period: ±0 to ±5min
 *
 * No real clocks; the test uses a counter-based clock seam so it runs in
 * milliseconds and never sleeps.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group GG T-159
 *   - holding/research/2026-04-29-native-d5-invariant-register.md §1 I-12
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

import {
  CadenceScheduler,
  CADENCE_JITTER_MS,
} from '../../src/engine/cadence-scheduler.js'

describe('CadenceScheduler — jitter property (≥1000 cases)', () => {
  it('every fire within the configured jitter band reports jitter_ms ≤ CADENCE_JITTER_MS', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 6 }), // hours
        fc.integer({ min: -CADENCE_JITTER_MS, max: CADENCE_JITTER_MS }), // tick offset (ms)
        async (n_hours, jitter_offset_ms) => {
          let now = 0
          const sched = new CadenceScheduler({ clock: () => now })
          sched.start()
          let fires = 0
          const handle = sched.register(
            { kind: 'every_n_hours', n: n_hours },
            () => {
              fires += 1
            },
          )
          const period_ms = n_hours * 60 * 60 * 1000
          const scheduled = period_ms
          // tick at scheduled + jitter (within ±5min)
          now = scheduled + jitter_offset_ms
          // For negative offsets, the scheduler wouldn't fire (next_fire_at > now).
          // We only assert positive-or-zero offsets here; negative offsets are a
          // distinct property (no fire when not yet due).
          if (jitter_offset_ms < 0) {
            await sched.tick()
            expect(fires).toBe(0)
            return
          }
          const report = await sched.tick()
          expect(fires).toBe(1)
          expect(report.fires).toHaveLength(1)
          expect(report.fires[0]!.jitter_ms).toBeLessThanOrEqual(CADENCE_JITTER_MS)
          expect(sched.getJitterMs(handle)).toBeLessThanOrEqual(CADENCE_JITTER_MS)
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('outside jitter band: tick still fires (period elapsed); recorded jitter > CADENCE_JITTER_MS surfaces deterministically', async () => {
    // Property: when the host tick lags BEYOND the jitter band, the
    // scheduler still fires (it's the period elapsing that matters, not the
    // band — band is observed lag-tolerance, not a refusal-to-fire band).
    // The recorded jitter_ms reports the actual lag so the operator can
    // see the band breach in observability.
    await fc.assert(
      fc.asyncProperty(
        fc.integer({
          min: CADENCE_JITTER_MS + 1,
          max: CADENCE_JITTER_MS * 10,
        }),
        async (extra_lag_ms) => {
          let now = 0
          const sched = new CadenceScheduler({ clock: () => now })
          sched.start()
          sched.register({ kind: 'every_n_hours', n: 1 }, () => {})
          const scheduled = 60 * 60 * 1000
          now = scheduled + extra_lag_ms
          const report = await sched.tick()
          expect(report.fires).toHaveLength(1)
          expect(report.fires[0]!.jitter_ms).toBe(extra_lag_ms)
          // The band-breach is observable via the comparison; no automatic
          // halt at v1.0 (the runtime decides what to do with the breach).
          expect(report.fires[0]!.jitter_ms).toBeGreaterThan(CADENCE_JITTER_MS)
        },
      ),
      { numRuns: 1000 },
    )
  })
})
