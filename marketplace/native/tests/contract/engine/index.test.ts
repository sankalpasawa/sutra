/**
 * Engine barrel — surface test (M5 Group I).
 *
 * Asserts the public surface of `src/engine/index.ts` re-exports the three
 * runtime entry points used by downstream engine consumers:
 *  - registerWorkflow
 *  - asActivity
 *  - F12_ERROR_TAG
 *
 * Test seams (`__set/resetWorkflowContextProbeForTest`) are intentionally
 * NOT on the public barrel — they live in `src/engine/_test_seams.ts` so the
 * production surface stays clean. This test asserts both contracts: seams
 * present on `_test_seams`, ABSENT from the barrel.
 *
 * Also exercises the default Workflow-context probe: in pure Node runtime,
 * the probe MUST return `false` (the safe default — Activities run on a
 * Worker outside the Workflow sandbox).
 */

import { describe, it, expect } from 'vitest'
import * as engine from '../../../src/engine/index.js'
import { asActivity } from '../../../src/engine/index.js'
import {
  __setWorkflowContextProbeForTest,
  __resetWorkflowContextProbeForTest,
} from '../../../src/engine/_test_seams.js'

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

  it('re-exports M5 Group K — executeStepGraph + applyFailurePolicy + formatTerminalCheckFailureReason', () => {
    expect(typeof engine.executeStepGraph).toBe('function')
    expect(typeof engine.applyFailurePolicy).toBe('function')
    expect(typeof engine.formatTerminalCheckFailureReason).toBe('function')
  })

  it('re-exports M6 Group O — SkillEngine class', () => {
    expect(typeof engine.SkillEngine).toBe('function') // class is a function
    const e = new engine.SkillEngine()
    expect(typeof e.register).toBe('function')
    expect(typeof e.resolve).toBe('function')
    expect(typeof e.unregister).toBe('function')
    expect(typeof e.validateOutputs).toBe('function')
  })

  it('re-exports M8 Group Z — OTelEmitter + exporters', () => {
    expect(typeof engine.OTelEmitter).toBe('function')
    expect(typeof engine.InMemoryOTelExporter).toBe('function')
    expect(typeof engine.NoopOTelExporter).toBe('function')
    expect(typeof engine.OTLPHttpExporter).toBe('function')
    // Smoke: emitter constructible + emit + flush
    const exporter = new engine.InMemoryOTelExporter()
    const emitter = new engine.OTelEmitter(exporter)
    expect(typeof emitter.emit).toBe('function')
    expect(typeof emitter.flush).toBe('function')
  })

  it('does NOT re-export test seams on the public barrel', () => {
    expect((engine as Record<string, unknown>).__setWorkflowContextProbeForTest).toBeUndefined()
    expect((engine as Record<string, unknown>).__resetWorkflowContextProbeForTest).toBeUndefined()
  })

  it('exposes test seams via src/engine/_test_seams.ts', () => {
    expect(typeof __setWorkflowContextProbeForTest).toBe('function')
    expect(typeof __resetWorkflowContextProbeForTest).toBe('function')
  })
})

describe('asActivity — default probe (pure Node runtime)', () => {
  it('does NOT trap when invoked in pure Node runtime (default probe = false)', async () => {
    // Reset to the default probe to exercise its real return value.
    __resetWorkflowContextProbeForTest()
    const act = asActivity(async (n: number) => n + 1)
    await expect(act(41)).resolves.toBe(42)
  })
})
