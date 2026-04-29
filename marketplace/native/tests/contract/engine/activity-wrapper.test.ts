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

  // Codex master review 2026-04-29 P2.2 (advisory) — broadened gate.
  // Public type is `(...args) => Promise<R>`; the wrapper is itself an
  // `async function` so any sync return is auto-promoted to Promise<R>.
  // We accept any function at registration; misuse surfaces at first call
  // (consumer awaits non-Promise → TypeError) rather than registration.
  it('accepts a Promise-returning arrow (() => Promise.resolve(...)) — codex P2.2', () => {
    const impl = () => Promise.resolve(42)
    const act = asActivity(impl as () => Promise<number>)
    expect(typeof act).toBe('function')
  })

  it('accepts a bound async function (constructor.name degrades to Function) — codex P2.2', async () => {
    const baseAsync = async (n: number) => n * 2
    const bound = baseAsync.bind(null)
    // Bound async functions lose `AsyncFunction` constructor.name — the prior
    // gate rejected these despite the type contract allowing them.
    const act = asActivity(bound)
    expect(typeof act).toBe('function')
    await expect(act(21)).resolves.toBe(42)
  })

  it('accepts a factory-produced Promise-returning callable — codex P2.2', async () => {
    const make = (): ((n: number) => Promise<number>) => (n) => Promise.resolve(n + 1)
    const impl = make()
    const act = asActivity(impl)
    await expect(act(5)).resolves.toBe(6)
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
