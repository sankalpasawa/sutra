/**
 * Engine barrel — surface test (M5 Group I).
 *
 * Asserts the public surface of `src/engine/index.ts` re-exports the four
 * runtime entry points used by the rest of the engine layer + tests:
 *  - registerWorkflow
 *  - asActivity
 *  - F12_ERROR_TAG
 *  - the test seams (so M5 Group J/K integration tests can stub the probe)
 *
 * Also exercises the default Workflow-context probe: in pure Node runtime,
 * the probe MUST return `false` (the safe default — Activities run on a
 * Worker outside the Workflow sandbox).
 */

import { describe, it, expect } from 'vitest'
import * as engine from '../../../src/engine/index.js'
import { asActivity } from '../../../src/engine/index.js'

describe('engine barrel — public surface', () => {
  it('re-exports registerWorkflow', () => {
    expect(typeof engine.registerWorkflow).toBe('function')
  })

  it('re-exports asActivity', () => {
    expect(typeof engine.asActivity).toBe('function')
  })

  it('re-exports F12_ERROR_TAG with stable value "F-12"', () => {
    expect(engine.F12_ERROR_TAG).toBe('F-12')
  })

  it('re-exports the Workflow-context probe test seams', () => {
    expect(typeof engine.__setWorkflowContextProbeForTest).toBe('function')
    expect(typeof engine.__resetWorkflowContextProbeForTest).toBe('function')
  })
})

describe('asActivity — default probe (pure Node runtime)', () => {
  it('does NOT trap when invoked in pure Node runtime (default probe = false)', async () => {
    // Reset to the default probe to exercise its real return value.
    engine.__resetWorkflowContextProbeForTest()
    const act = asActivity(async (n: number) => n + 1)
    await expect(act(41)).resolves.toBe(42)
  })
})
