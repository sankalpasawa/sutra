/**
 * F-12 (replay determinism — Workflow code performs I/O) — property test.
 *
 * M5 Group I per holding/plans/native-v1.0/M5-workflow-engine.md.
 *
 * Per codex P2.4 narrow: M5 enforces F-12 as a RUNTIME TRAP only (the Activity
 * wrapper detects when it is invoked inside a Workflow context and throws).
 * The schema-level terminalCheck integration is DEFERRED to M9 once the
 * evidence-input shape is known.
 *
 * Property: for any async impl + arbitrary args + arbitrary "is this Workflow
 * context?" boolean, the wrapper either
 *   (a) returns the impl's result when context=false, OR
 *   (b) throws an F-12 ForbiddenCoupling error when context=true.
 *
 * Positive ∧ negative cases mixed; ≥1000 cases.
 *
 * F-12 enum value asserted present in ForbiddenCouplingId.
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  asActivity,
  F12_ERROR_TAG,
} from '../../src/engine/activity-wrapper.js'
import {
  __setWorkflowContextProbeForTest,
  __resetWorkflowContextProbeForTest,
} from '../../src/engine/_test_seams.js'
import type { ForbiddenCouplingId } from '../../src/laws/l4-terminal-check.js'

const PROP_RUNS = 1000

describe('F-12 — runtime-trap property test (M5)', () => {
  it('F-12 is a valid ForbiddenCouplingId', () => {
    // Compile-time AND runtime: a string typed as ForbiddenCouplingId carrying 'F-12' must be assignable.
    const id: ForbiddenCouplingId = 'F-12'
    expect(id).toBe('F-12')
  })

  it('throws iff probe says inside Workflow context (≥1000 cases)', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.boolean(), // inside-Workflow context?
        fc.integer({ min: -1000, max: 1000 }), // arbitrary input arg
        async (inside, n) => {
          __setWorkflowContextProbeForTest(() => inside)
          try {
            const act = asActivity(async (x: number) => x + 1)
            if (inside) {
              let threw = false
              try {
                await act(n)
              } catch (err) {
                threw = true
                expect(String(err)).toContain(F12_ERROR_TAG)
              }
              expect(threw).toBe(true)
            } else {
              const result = await act(n)
              expect(result).toBe(n + 1)
            }
          } finally {
            __resetWorkflowContextProbeForTest()
          }
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })

  it('positive case: never traps when context=false (≥1000 cases)', async () => {
    __setWorkflowContextProbeForTest(() => false)
    try {
      await fc.assert(
        fc.asyncProperty(fc.string(), async (s) => {
          const act = asActivity(async (v: string) => `wrapped:${v}`)
          const got = await act(s)
          expect(got).toBe(`wrapped:${s}`)
        }),
        { numRuns: PROP_RUNS },
      )
    } finally {
      __resetWorkflowContextProbeForTest()
    }
  })

  it('negative case: always traps when context=true (≥1000 cases)', async () => {
    __setWorkflowContextProbeForTest(() => true)
    try {
      await fc.assert(
        fc.asyncProperty(fc.anything(), async (anything) => {
          const act = asActivity(async () => anything)
          let threw = false
          try {
            await act()
          } catch (err) {
            threw = true
            expect(String(err)).toContain(F12_ERROR_TAG)
          }
          expect(threw).toBe(true)
        }),
        { numRuns: PROP_RUNS },
      )
    } finally {
      __resetWorkflowContextProbeForTest()
    }
  })
})
