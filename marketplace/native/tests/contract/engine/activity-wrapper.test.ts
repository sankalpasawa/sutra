/**
 * Activity wrapper contract test — M5 Group I (T-043, T-044).
 *
 * Asserts:
 *  - asActivity<T>(impl) requires an async impl (rejects sync)
 *  - Returned ActivityFn invokes the impl when called outside Workflow context
 *  - Returned ActivityFn THROWS when called inside Workflow context (F-12
 *    runtime trap — codex P2.4 narrowed M5 scope to runtime-only).
 *
 * The Workflow-context detection is mocked via a context probe — the real
 * Temporal `inWorkflowContext()` from @temporalio/workflow throws when not in
 * a workflow runtime, which we use as our canary.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group I T-043, T-044
 */

import { describe, it, expect } from 'vitest'
import { asActivity } from '../../../src/engine/activity-wrapper.js'
import {
  __setWorkflowContextProbeForTest,
  __resetWorkflowContextProbeForTest,
} from '../../../src/engine/_test_seams.js'

describe('asActivity — wrapper signature', () => {
  it('accepts an async impl and returns an ActivityFn', () => {
    const impl = async () => 42
    const act = asActivity(impl)
    expect(typeof act).toBe('function')
  })

  it('rejects a sync (non-Promise-returning) impl at registration', () => {
    // @ts-expect-error — intentional: sync impl violates ActivityFn contract
    expect(() => asActivity(() => 42)).toThrow(/async/i)
  })

  it('rejects non-function inputs', () => {
    // @ts-expect-error — intentional bad input
    expect(() => asActivity(null)).toThrow()
    // @ts-expect-error — intentional bad input
    expect(() => asActivity('not a function')).toThrow()
  })
})

describe('asActivity — happy-path execution (outside Workflow context)', () => {
  it('invokes the impl when called outside Workflow context', async () => {
    __resetWorkflowContextProbeForTest()
    const act = asActivity(async (n: number) => n * 2)
    const result = await act(21)
    expect(result).toBe(42)
  })

  it('propagates impl errors', async () => {
    __resetWorkflowContextProbeForTest()
    const act = asActivity(async () => {
      throw new Error('impl-failure')
    })
    await expect(act()).rejects.toThrow('impl-failure')
  })
})

describe('asActivity — F-12 runtime trap (inside Workflow context)', () => {
  it('throws ForbiddenCouplingF12 when called inside a Workflow context', async () => {
    // Simulate Workflow context: probe returns true.
    __setWorkflowContextProbeForTest(() => true)
    try {
      const act = asActivity(async () => 'should-not-execute')
      await expect(act()).rejects.toThrow(/F-12/)
    } finally {
      __resetWorkflowContextProbeForTest()
    }
  })

  it('does NOT trap when probe returns false (default behavior)', async () => {
    __setWorkflowContextProbeForTest(() => false)
    try {
      const act = asActivity(async () => 'ok')
      await expect(act()).resolves.toBe('ok')
    } finally {
      __resetWorkflowContextProbeForTest()
    }
  })
})
